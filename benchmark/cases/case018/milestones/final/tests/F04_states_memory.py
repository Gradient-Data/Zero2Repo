# feature: F04
"""Observable execution-state and memory acceptance tests."""
import pytest
from _helpers import import_product
from F01_helpers import fresh_state, expression_api
from F04_helpers import build_state_program, reach_address


def test_state_factories_and_process_inputs(tmp_path):
    velnora, c = expression_api()
    path = build_state_program(tmp_path)
    project = velnora.Project(str(path), auto_load_libs=True,
                           ld_path=[str(tmp_path)], use_system_libs=False)
    observed = project.loader.find_symbol("observed").rebased_addr
    compute = project.loader.find_symbol("compute").rebased_addr
    marker = project.loader.find_symbol("initialized").rebased_addr
    blank = project.factory.blank_state(addr=compute)
    assert blank.addr == compute
    # Both concrete and symbolic values must travel through process setup and instructions.
    for symbolic in (False, True):
        arg = c.BVS("process_argument", 8) if symbolic else b"M"
        env = c.BVS("process_environment", 8) if symbolic else b"N"
        kwargs = dict(args=[b"program", arg], env={b"KEY": env})
        for factory, initialized in ((project.factory.entry_state, 0),
                                     (project.factory.full_init_state, 0x6942)):
            state = factory(**kwargs)
            if factory == project.factory.entry_state:
                assert state.addr == project.entry
            result = reach_address(project, state, observed)
            assert result.solver.eval(result.regs.rax) == 2
            assert result.solver.eval(result.memory.load(marker, 8,
                                      endness=result.arch.memory_endness)) == initialized
            if symbolic:
                assert not result.solver.satisfiable(extra_constraints=[result.regs.bl != arg])
                assert not result.solver.satisfiable(extra_constraints=[result.regs.cl != env])
                assert set(result.solver.eval_upto(arg, 257)) == set(range(256))
                assert set(result.solver.eval_upto(env, 257)) == set(range(256))
            else:
                assert result.solver.eval(result.regs.bl) == ord("M")
                assert result.solver.eval(result.regs.cl) == ord("N")
    call = project.factory.call_state(compute, 17, 29,
                                     prototype="unsigned long f(unsigned long, unsigned long)",
                                     ret_addr=observed)
    assert call.addr == compute
    returned = reach_address(project, call, observed)
    assert returned.solver.eval(returned.regs.rax) == 75


def test_raw_register_and_memory_access():
    _, c = expression_api()
    state = fresh_state()
    # The split crosses a page boundary and overlaps a prior multi-byte value.
    address = 0x30FFD
    state.memory.store(address, c.BVV(0x123456789ABCDEF0, 64))
    assert state.solver.eval(state.memory.load(address, 8), cast_to=bytes) == bytes.fromhex("123456789abcdef0")
    state.memory.store(address + 2, b"XYZ")
    assert state.solver.eval(state.memory.load(address, 8), cast_to=bytes) == bytes.fromhex("1234") + b"XYZ" + bytes.fromhex("bcdef0")
    state.memory.store(address + 8, bytes.fromhex("10203040"))
    assert state.solver.eval_one(state.memory.load(address + 8, 4)) == 0x10203040
    state.memory.store(address + 16, c.BVV(0x12345678, 32), endness="Iend_LE")
    assert state.solver.eval(state.memory.load(address + 16, 4), cast_to=bytes) == bytes.fromhex("78563412")
    assert state.solver.eval(state.memory.load(address + 16, 4, endness="Iend_LE")) == 0x12345678
    value = c.BVS("stored_value", 32)
    state.solver.add(c.Or(value == 0x12345678, value == 0xAABBCCDD))
    state.memory.store(address + 32, value)
    state.registers.store("rax", value.zero_extend(32))
    assert set(state.solver.eval_upto(state.memory.load(address + 32, 4), 3)) == {0x12345678, 0xAABBCCDD}
    assert not state.solver.satisfiable(extra_constraints=[state.memory.load(address + 32, 4) != value])
    assert not state.solver.satisfiable(extra_constraints=[state.regs.rax != value.zero_extend(32)])
    offset, _ = state.arch.registers["rax"]
    state.registers.store(offset, c.BVV(0x1020304050607080, 64))
    assert state.solver.eval(state.registers.load(offset, 8, endness="Iend_BE")) == 0x8070605040302010
    state.registers.store(offset, bytes.fromhex("0123456789abcdef"), endness="Iend_BE")
    assert state.solver.eval(state.registers.load(offset, 8)) == 0xefcdab8967452301
    state.registers.store(offset, c.BVV(0x1122334455667788, 64), endness="Iend_BE")
    assert state.solver.eval(state.registers.load(offset, 8, endness="Iend_BE")) == 0x1122334455667788
    state.registers.store(offset + 2, b"AB", endness="Iend_BE")
    assert state.solver.eval(state.registers.load(offset, 8, endness="Iend_BE"), cast_to=bytes) == bytes.fromhex("1122") + b"AB" + bytes.fromhex("55667788")
    state.registers.store(offset + 16, c.BVV(0x12345678, 32), endness="Iend_LE")
    assert state.solver.eval(state.registers.load(offset + 16, 4, endness="Iend_BE")) == 0x78563412


def test_uninitialized_and_zero_policies():
    velnora, _ = expression_api()
    project = velnora.load_shellcode(b"\x90", arch="AMD64")
    for options in (set(), {velnora.options.ZERO_FILL_UNCONSTRAINED_MEMORY},
                    {velnora.options.ZERO_FILL_UNCONSTRAINED_REGISTERS}):
        state = project.factory.blank_state(add_options=options)
        for expression, zero_option in (
                (state.memory.load(0x420000, 3), velnora.options.ZERO_FILL_UNCONSTRAINED_MEMORY),
                (state.registers.load("r12"), velnora.options.ZERO_FILL_UNCONSTRAINED_REGISTERS)):
            assert expression.size() == (24 if zero_option == velnora.options.ZERO_FILL_UNCONSTRAINED_MEMORY else 64)
            if zero_option in options:
                assert state.solver.eval_one(expression) == 0
            else:
                assert expression.symbolic
                for value in (0, 1, (1 << expression.size()) - 1, 0x5A39):
                    assert state.solver.satisfiable(extra_constraints=[expression == value])


def test_copy_isolation():
    _, c = expression_api()
    original = fresh_state()
    variable = c.BVS("copy_constraint", 8)
    original.solver.add(c.Or(variable == 3, variable == 9, variable == 21))
    original.memory.store(0x450000, b"abcdef")
    original.regs.r12 = 42
    original.regs.r13 = 57
    copied = original.copy()
    assert copied.solver.eval(copied.memory.load(0x450000, 6), cast_to=bytes) == b"abcdef"
    assert copied.solver.eval(copied.regs.r12) == 42
    assert set(copied.solver.eval_upto(variable, 4)) == {3, 9, 21}
    original.memory.store(0x450000, b"XY")
    original.regs.r12 = 81
    original.solver.add(variable != 3)
    assert copied.solver.eval(copied.memory.load(0x450000, 6), cast_to=bytes) == b"abcdef"
    assert copied.solver.eval(copied.regs.r12) == 42
    copied.memory.store(0x450004, b"QR")
    copied.regs.r13 = 93
    copied.solver.add(variable == 3)
    assert original.solver.eval(original.memory.load(0x450000, 6), cast_to=bytes) == b"XYcdef"
    assert copied.solver.eval(copied.memory.load(0x450000, 6), cast_to=bytes) == b"abcdQR"
    assert original.solver.eval(original.regs.r13) == 57
    assert original.solver.eval(original.regs.r12) == 81
    assert copied.solver.eval(copied.regs.r13) == 93
    assert set(original.solver.eval_upto(variable, 4)) == {9, 21}
    assert copied.solver.eval_one(variable) == 3


def test_merge_retains_correlated_alternatives():
    _, c = expression_api()
    base = fresh_state()
    variable = c.BVS("merge_path", 8)
    branches = []
    alternatives = ((2, 17, 0x31), (7, 28, 0x62), (11, 39, 0x93))
    for path, register, memory in alternatives:
        branch = base.copy()
        branch.solver.add(variable == path)
        branch.regs.r12 = register
        branch.memory.store(0x460000, bytes([memory]))
        branches.append(branch)
    merged, conditions, changed = branches[0].merge(*branches[1:])
    assert changed
    assert len(conditions) == len(branches)
    byte = merged.memory.load(0x460000, 1)
    valid = c.Or(*(c.And(variable == path, merged.regs.r12 == register, byte == memory)
                   for path, register, memory in alternatives))
    assert not merged.solver.satisfiable(extra_constraints=[c.Not(valid)])
    for condition, (path, register, memory) in zip(conditions, alternatives):
        assert merged.solver.satisfiable(extra_constraints=[condition])
        assert merged.solver.eval_one(variable, extra_constraints=[condition]) == path
        assert merged.solver.eval_one(merged.regs.r12, extra_constraints=[condition]) == register
        assert merged.solver.eval_one(byte, extra_constraints=[condition]) == memory


def test_mapping_and_access_permissions():
    velnora = import_product()
    state = fresh_state()
    state.options.add(velnora.options.STRICT_PAGE_ACCESS)
    address = 0x70000000
    for operation in (lambda: state.memory.load(address, 1),
                      lambda: state.memory.store(address, b"A")):
        with pytest.raises(velnora.errors.SimSegfaultException):
            operation()
    state.memory.map_region(address, 0x2000, 3)
    assert state.solver.eval(state.memory.permissions(address)) == 3
    state.memory.store(address + 0xFFF, b"mapped")
    assert state.solver.eval(state.memory.load(address + 0xFFF, 6), cast_to=bytes) == b"mapped"
    state.memory.permissions(address, 1)
    assert state.solver.eval(state.memory.permissions(address)) == 1
    assert state.solver.eval(state.memory.load(address + 0xFFF, 1), cast_to=bytes) == b"m"
    with pytest.raises(velnora.errors.SimSegfaultException):
        state.memory.store(address, b"B")
    state.memory.permissions(address + 0x1000, 2)
    state.memory.store(address + 0x1000, b"C")
    with pytest.raises(velnora.errors.SimSegfaultException):
        state.memory.load(address + 0x1000, 1)
    state.memory.permissions(address + 0x1000, 3)
    assert state.solver.eval(state.memory.load(address + 0x1000, 1), cast_to=bytes) == b"C"
    state.memory.unmap_region(address, 0x2000)
    for operation in (lambda: state.memory.load(address + 0x1000, 1),
                      lambda: state.memory.store(address, b"D")):
        with pytest.raises(velnora.errors.SimSegfaultException):
            operation()


def test_execute_permission_enforcement():
    velnora = import_product()
    project = velnora.load_shellcode(b"\x90", arch="AMD64")
    for permissions in (7, 3):
        state = project.factory.blank_state(addr=0x71000000,
            add_options={velnora.options.STRICT_PAGE_ACCESS, velnora.options.ENABLE_NX})
        state.memory.map_region(0x71000000, 0x1000, permissions)
        # mov eax, 0x12345678; jmp +0
        state.memory.store(0x71000000, bytes.fromhex("b878563412eb00"))
        if permissions == 7:
            successors = project.factory.successors(state).flat_successors
            assert len(successors) == 1
            assert successors[0].addr == 0x71000007
            assert successors[0].solver.eval(successors[0].regs.rax) == 0x12345678
        else:
            with pytest.raises(velnora.errors.SimSegfaultException):
                project.factory.successors(state)


def test_symbolic_address_policies():
    velnora, c = expression_api()
    from velnora.concretization_strategies import SimConcretizationStrategyRange, SimConcretizationStrategyAny
    addresses = (0x480000, 0x480002, 0x480005)
    for single in (False, True):
        for write in (False, True):
            state = fresh_state()
            pointer = c.BVS("selected_address", 64)
            state.solver.add(c.Or(*(pointer == address for address in addresses)))
            state.memory.store(addresses[0], b"abcdef")
            strategy = SimConcretizationStrategyAny() if single else SimConcretizationStrategyRange(8)
            if write:
                state.memory.write_strategies = [strategy]
                state.memory.store(pointer, b"Z")
            else:
                state.memory.read_strategies = [strategy]
                result = state.memory.load(pointer, 1)
            feasible = set(state.solver.eval_upto(pointer, 4))
            assert feasible <= set(addresses)
            assert len(feasible) == (1 if single else len(addresses))
            for selected in feasible:
                constraints = [pointer == selected]
                if write:
                    expected = bytearray(b"abcdef")
                    expected[selected - addresses[0]] = ord("Z")
                    assert state.solver.eval_one(state.memory.load(addresses[0], 6),
                                                extra_constraints=constraints, cast_to=bytes) == bytes(expected)
                else:
                    assert state.solver.eval_one(result, extra_constraints=constraints) == b"abcdef"[selected - addresses[0]]


def test_typed_memory_views():
    velnora, c = expression_api()
    for architecture, order in (("AMD64", "little"), ("MIPS32", "big")):
        project = velnora.load_shellcode(b"\x00" * 4, arch=architecture)
        state = project.factory.blank_state()
        struct = velnora.types.parse_type("struct F04Record { unsigned char tag; unsigned int count; unsigned short samples[3]; }").with_arch(state.arch)
        address = 0x490000
        size = struct.size // 8
        raw = bytearray(b"\xCC" * (size + 2))
        raw[1 + struct.offsets["tag"]] = 0x39
        count_size = struct.fields["count"].size // 8
        count_offset = 1 + struct.offsets["count"]
        raw[count_offset:count_offset + count_size] = (0x12345678).to_bytes(count_size, order)
        element_size = struct.fields["samples"].elem_type.size // 8
        array_offset = 1 + struct.offsets["samples"]
        for index, value in enumerate((0x1234, 0x5678, 0x9ABC)):
            raw[array_offset + index * element_size:array_offset + (index + 1) * element_size] = value.to_bytes(element_size, order)
        state.memory.store(address - 1, bytes(raw))
        view = state.mem[address].with_type(struct)
        assert view.tag.concrete == b"9"
        assert view.count.concrete == 0x12345678
        assert state.solver.eval_one(view.count.resolved) == 0x12345678
        assert view.samples.concrete == [0x1234, 0x5678, 0x9ABC]
        assert view.samples[1].concrete == 0x5678
        view.count = 0x10203040
        raw[count_offset:count_offset + count_size] = (0x10203040).to_bytes(count_size, order)
        view.samples[2] = 0x3142
        raw[array_offset + 2 * element_size:array_offset + 3 * element_size] = (0x3142).to_bytes(element_size, order)
        assert state.solver.eval_one(state.memory.load(address - 1, len(raw)), cast_to=bytes) == bytes(raw)
        pointer_type = velnora.types.parse_type("unsigned int *").with_arch(state.arch)
        pointer_address = address + 0x100
        target = address + struct.offsets["count"]
        state.memory.store(pointer_address, target.to_bytes(pointer_type.size // 8, order))
        dereference = state.mem[pointer_address].with_type(pointer_type).deref
        assert dereference.concrete == 0x10203040
        dereference.store(0x55667788)
        raw[count_offset:count_offset + count_size] = (0x55667788).to_bytes(count_size, order)
        assert state.solver.eval_one(state.memory.load(address - 1, len(raw)), cast_to=bytes) == bytes(raw)
        symbolic = c.BVS("typed_scalar", count_size * 8)
        view.count = symbolic
        assert not state.solver.satisfiable(extra_constraints=[view.count.resolved != symbolic])
        other = state.copy()
        other.mem[address].with_type(struct).tag = 0x72
        assert view.tag.concrete == b"9"
        assert other.mem[address].with_type(struct).tag.concrete == b"r"
