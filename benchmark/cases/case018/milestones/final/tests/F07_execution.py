# feature: F07
"""Observable execution, invocation, and argument placement acceptance checks."""
import velnora

# The documented expression namespace is the velnora.claripy attribute.
claripy = velnora.claripy
from _helpers import import_product, capture_call
from F04_helpers import reach_address
from F07_helpers import execution_program, symbol_address


def test_native_effects_calls_and_returns(tmp_path):
    p = execution_program(tmp_path)
    for initial, increment, expected in ((6, 3, 138), (48, 6, 0)):
        s = p.factory.blank_state(addr=p.entry)
        s.regs.rdi, s.regs.rsi = 0x700000, increment
        s.regs.rsp = 0x7fff0000
        s.memory.store(0x700000, initial, size=8, endness=p.arch.memory_endness)
        # Observe final effects without prescribing basic-block partitioning.
        stepped = s.step().flat_successors
        assert len(stepped) == 1
        partial = stepped[0]
        stored = (initial + increment) ^ 0x35
        end = reach_address(p, partial, symbol_address(p, 'finished'))
        assert end.solver.eval_one(end.memory.load(0x700000, 8, endness=p.arch.memory_endness)) == stored
        assert end.solver.eval_one(end.regs.rax) == expected
        assert end.solver.eval_one(end.regs.rsp) == 0x7fff0000
        assert end.addr == symbol_address(p, 'finished')


def test_instruction_and_address_stops(tmp_path):
    # Two counts and two stopping addresses: a fixed stop after one instruction
    # or at one hard-coded label does not satisfy every request. Each request
    # uses a freshly loaded project so no earlier request's lifted extent is reused.
    for option, value, label, expected in (('num_inst', 1, 'stop1', 16),
                                           ('num_inst', 2, 'stop2', 69),
                                           ('extra_stop_points', 'stop2', 'stop2', 69),
                                           ('extra_stop_points', 'stop1', 'stop1', 16)):
        p = execution_program(tmp_path)
        options = {option: {symbol_address(p, value)} if option == 'extra_stop_points' else value}
        s = p.factory.blank_state(addr=symbol_address(p, 'limits'))
        s.regs.rax = 13
        out = p.factory.successors(s, **options).flat_successors
        assert len(out) == 1
        assert out[0].addr == symbol_address(p, label)
        assert out[0].solver.eval_one(out[0].regs.rax) == expected


def test_symbolic_branch_constraints_and_infeasible_arm(tmp_path):
    p = execution_program(tmp_path)
    x = claripy.BVS('branch_input', 64)
    s = p.factory.blank_state(addr=symbol_address(p, 'branch'))
    s.regs.rdi = x
    s.add_constraints(claripy.Or(x == 0, x == 4, x == 9))
    result = p.factory.successors(s)
    assert len(result.flat_successors) == 2
    observed = set()
    for branch in result.flat_successors:
        values = frozenset(branch.solver.eval_upto(x, 4))
        observed.add(values)
        assert branch.solver.satisfiable()
        assert not branch.solver.satisfiable(extra_constraints=[x == 1])
    assert observed == {frozenset({0}), frozenset({4, 9})}
    constrained = s.copy()
    constrained.add_constraints(x == 0)
    result = constrained.step()
    assert len(result.flat_successors) == 1
    assert result.flat_successors[0].solver.eval_one(x) == 0
    assert len(result.unsat_successors) == 1
    assert not result.unsat_successors[0].solver.satisfiable()


def test_computed_destinations_and_bounds(tmp_path):
    p = execution_program(tmp_path)
    for bound, count, resolved in ((None, 256, True), (None, 257, False),
                                    (3, 3, True), (3, 4, False)):
        s = p.factory.blank_state(addr=symbol_address(p, 'indirect'))
        target = claripy.BVS('destination', 64)
        s.regs.rax = target
        s.add_constraints(target >= 0x800000, target < 0x800000 + count)
        if bound is not None:
            s.options.symbolic_ip_max_targets = bound
        result = s.step()
        if resolved:
            assert {state.addr for state in result.flat_successors} == set(range(0x800000, 0x800000 + count))
            assert not result.unconstrained_successors
            for state in result.flat_successors:
                assert state.solver.eval_one(target) == state.addr
        else:
            assert not result.flat_successors
            assert len(result.unconstrained_successors) == 1
            retained = result.unconstrained_successors[0]
            assert set(retained.solver.eval_upto(retained.regs.ip, count + 1)) == set(range(0x800000, 0x800000 + count))


def test_callable_concrete_symbolic_and_conventions(tmp_path):
    p = execution_program(tmp_path)
    from velnora.calling_conventions import SimCCSystemVAMD64, SimCCMicrosoftAMD64
    for cc, code in ((SimCCSystemVAMD64(p.arch), b'\x48\x8d\x04\x77\xc3'),
                     (SimCCMicrosoftAMD64(p.arch), b'\x48\x8d\x04\x51\xc3')):
        q = import_product().load_shellcode(code, arch='amd64', load_address=0x400000)
        f = q.factory.callable(0x400000, prototype='long f(long, long)', cc=cc)
        for a, b in ((7, 11), (-3, 5)):
            returned = f(a, b)
            assert f.result_state.solver.eval_one(returned) == (a + 2*b) % (1 << 64)
            assert len(f.result_path_group.active) == 1
        x = claripy.BVS('argument', 64)
        base = q.factory.blank_state()
        base.add_constraints(claripy.Or(x == 2, x == 19))
        f.set_base_state(base)
        returned = f(x, 6)
        assert set(f.result_state.solver.eval_upto(returned, 3)) == {14, 31}
        assert not f.result_state.solver.satisfiable(extra_constraints=[returned != x + 12])


def test_callable_multiple_paths_and_no_return(tmp_path):
    p = execution_program(tmp_path)
    velnora = import_product()
    f = p.factory.callable(symbol_address(p, 'branch'), prototype='long f(long)', concrete_only=True)
    for argument, expected in ((0, 29), (5, 17)):
        returned = f(argument)
        assert f.result_state.solver.eval_one(returned) == expected
    result = capture_call(f, claripy.BVS('split', 64))
    assert isinstance(result.exception, velnora.errors.VelnoraCallableMultistateError)
    # An unresolved computed jump yields no returning function state.
    f = p.factory.callable(symbol_address(p, 'indirect'), prototype='void f(void)')
    result = capture_call(f)
    assert isinstance(result.exception, velnora.errors.VelnoraCallableError)
    assert not isinstance(result.exception, velnora.errors.VelnoraCallableMultistateError)


def test_execution_errors_are_not_successors():
    velnora = import_product()
    p = velnora.load_shellcode(b'\xb8\x2a\x00\x00\x00\x0f\x0b', arch='amd64', load_address=0x400000)
    s = p.factory.blank_state(addr=0x400000)
    baseline = p.factory.successors(s, num_inst=1).flat_successors
    assert len(baseline) == 1
    assert baseline[0].solver.eval_one(baseline[0].regs.rax) == 42
    for state, error in ((baseline[0], velnora.errors.SimIRSBNoDecodeError),
                         (p.factory.blank_state(addr=0x900000), velnora.errors.SimEngineError)):
        failure = capture_call(p.factory.successors, state)
        assert isinstance(failure.exception, error)
        assert failure.value is None


def test_call_state_structured_arguments_and_locations():
    velnora = import_product()
    from velnora.calling_conventions import SimCCSystemVAMD64, SimCCUsercall, SimRegArg, SimStackArg
    p = velnora.load_shellcode(b'\xc3', arch='amd64', load_address=0x400000)
    cc = SimCCSystemVAMD64(p.arch)
    struct = velnora.types.parse_type('struct F07Pair { long a; long b; }')
    from velnora.sim_type import SimTypeFunction, SimTypePointer, SimTypeChar, SimTypeLong
    prototype = SimTypeFunction([SimTypePointer(SimTypeChar()), SimTypePointer(SimTypeLong()),
                                SimTypePointer(struct)], SimTypeLong()).with_arch(p.arch)
    s = p.factory.call_state(0x400000, 'seventh', [12, 37, 8],
                             velnora.PointerWrapper((23, 41)), prototype=prototype, cc=cc,
                             stack_base=0x7fff0000, alloc_base=0x900000000, grow_like_stack=False)
    assert s.solver.eval_one(s.regs.rsp) == 0x7fff0000
    pointers = [s.solver.eval_one(value) for value in cc.get_args(s, prototype)]
    assert all(pointer >= 0x900000000 for pointer in pointers)
    assert s.solver.eval_one(s.memory.load(pointers[0], 8), cast_to=bytes) == b'seventh\x00'
    assert [s.solver.eval_one(s.memory.load(pointers[1]+8*i, 8, endness=p.arch.memory_endness)) for i in range(3)] == [12, 37, 8]
    bound = struct.with_arch(p.arch)
    for field, expected in (('a', 23), ('b', 41)):
        assert s.solver.eval_one(s.memory.load(pointers[2]+bound.offsets[field], 8, endness=p.arch.memory_endness)) == expected
    # Scalar locations are selected by the caller, including an explicit stack slot.
    custom = SimCCUsercall(p.arch, [SimRegArg('r10', 8), SimStackArg(16, 8)], SimRegArg('r11', 8))
    ty = SimTypeFunction([SimTypeLong(), SimTypeLong()], SimTypeLong()).with_arch(p.arch)
    state = p.factory.call_state(0x400000, 51, 73, cc=custom, prototype=ty, stack_base=0x7ffe0000)
    assert state.solver.eval_one(state.regs.r10) == 51
    assert state.solver.eval_one(state.memory.load(0x7ffe0010, 8, endness=p.arch.memory_endness)) == 73
    assert [state.solver.eval_one(v) for v in custom.get_args(state, ty)] == [51, 73]
    custom.set_return_val(state, claripy.BVV(93, 64), ty.returnty)
    assert state.solver.eval_one(state.regs.r11) == 93
    assert state.solver.eval_one(custom.return_val(ty.returnty).get_value(state)) == 93


def test_java_execution_and_jni_updates(tmp_path):
    from F07_helpers import java_native_program
    from archinfo.arch_soot import SootMethodDescriptor, SootArgument, SootAddressTerminator
    from velnora.engines.soot.values import SimSootValue_StaticFieldRef, SimSootValue_ArrayRef
    pth, library = java_native_program(tmp_path)
    p = import_product().Project(str(pth), auto_load_libs=True,
        main_opts={'entry_point': 'F07Java.main', 'entry_point_params': ('java.lang.String[]',),
                   'jni_libs': [library.name], 'jni_libs_ld_path': [str(tmp_path)]})
    method = SootMethodDescriptor.from_soot_method(p.loader.main_object.get_soot_method('F07Java.run', params=('int',)))
    x = claripy.BVS('java_argument', 32)
    s = p.factory.call_state(method.address(), SootArgument(x, 'int'), ret_addr=SootAddressTerminator())
    s.add_constraints(claripy.Or(x == 2, x == 8))
    manager = p.factory.simulation_manager(s)
    manager.run(n=100)
    assert not manager.errored, [record.error for record in manager.errored]
    assert not manager.active, 'Java/JNI execution did not finish within the step bound'
    assert len(manager.deadended) == 2
    results = set()
    for state in manager.deadended:
        argument = state.solver.eval_one(x)
        returned = state.solver.eval_one(state.regs.invoke_return_value)
        results.add((argument, returned))
        adjusted = {2: 1, 8: 16}[argument]
        obj = state.memory.load(SimSootValue_StaticFieldRef('F07Java', 'savedObject', 'F07Java'))
        array = state.memory.load(SimSootValue_StaticFieldRef('F07Java', 'savedArray', 'int[]'))
        assert state.solver.eval_one(obj.get_field(state, 'value', 'int')) == adjusted + 4
        assert state.solver.eval_one(state.memory.load(SimSootValue_ArrayRef(array, 0))) == adjusted + 3
        assert state.solver.eval_one(state.memory.load(SimSootValue_ArrayRef(array, 1))) == adjusted + 10
    assert results == {(2, 19), (8, 94)}
