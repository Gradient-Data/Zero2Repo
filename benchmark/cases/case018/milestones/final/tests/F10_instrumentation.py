# feature: F10
"""Acceptance observations for execution instrumentation and path history."""
import velnora

# The documented expression namespace is the velnora.claripy attribute.
claripy = velnora.claripy
from _helpers import import_product
from F07_helpers import symbol_address
from F10_helpers import (instrumentation_program, instrumentation_state,
                         single_successor, walk_to, concrete_value)


def test_event_callbacks_expose_execution(tmp_path):
    velnora = import_product()
    project = instrumentation_program(tmp_path)
    state = instrumentation_state(project)
    events = {name: [] for name in ('mem_read', 'mem_write', 'reg_read', 'reg_write',
                                   'instruction', 'call', 'return', 'syscall',
                                   'exit', 'constraints', 'symbolic_variable')}
    fields = {
        'mem_read': ('mem_read_address', 'mem_read_expr'),
        'mem_write': ('mem_write_address', 'mem_write_expr'),
        'reg_read': ('reg_read_offset', 'reg_read_expr'),
        'reg_write': ('reg_write_offset', 'reg_write_expr'),
        'instruction': ('instruction',), 'call': ('function_address',),
        'return': ('function_address',), 'syscall': ('syscall_name',),
        'exit': ('exit_target', 'exit_guard', 'exit_jumpkind'),
        'symbolic_variable': ('symbolic_name', 'symbolic_size', 'symbolic_expr'),
    }

    def record(name):
        def callback(current):
            attrs = current.inspect.attrs
            if name == 'constraints':
                events[name].append((current, tuple(attrs.added_constraints)))
            elif name == 'symbolic_variable':
                events[name].append((current, attrs.symbolic_name, attrs.symbolic_size,
                                     attrs.symbolic_expr))
            else:
                events[name].append(tuple(concrete_value(current, getattr(attrs, field))
                                          for field in fields[name]))
        return callback

    for name in events:
        state.inspect.b(name, when=velnora.BP_BEFORE if name == 'instruction' else velnora.BP_AFTER, action=record(name))
    token = state.solver.BVS('instrumented_input', 8)
    state.add_constraints(token == 41)
    assert any(size == 8 and name in token.variables
               and not claripy.Solver().satisfiable(extra_constraints=[expr != token])
               for _, name, size, expr in events['symbolic_variable'])
    assert any(constraints and not claripy.Solver().satisfiable(
                   extra_constraints=[claripy.And(*constraints) != (token == 41)])
               for current, constraints in events['constraints'])
    assert state.solver.eval_one(token) == 41
    final = walk_to(project, state, symbol_address(project, 'done'))
    assert final.solver.eval_one(final.regs.rax) == 23
    assert final.solver.eval_one(final.memory.load(0x600000, 8, endness='Iend_LE')) == 18
    assert (0x600000, 11) in events['mem_read']
    assert (0x600000, 18) in events['mem_write']
    assert (project.arch.registers['rax'][0], 18) in events['reg_write']
    assert (project.arch.registers['rdi'][0], 0x600000) in events['reg_read']
    assert (symbol_address(project, 'write_site'),) in events['instruction']
    for function in ('outer', 'inner'):
        assert (symbol_address(project, function),) in events['call']
        assert (symbol_address(project, function),) in events['return']
    assert (symbol_address(project, 'outer'), True, 'Ijk_Call') in events['exit']
    syscall_state = instrumentation_state(project, 'syscall_start')
    syscall_state.inspect.b('syscall', when=velnora.BP_AFTER, action=record('syscall'))
    syscall_state = single_successor(project, syscall_state)
    syscall_state = single_successor(project, syscall_state)
    assert syscall_state.addr == symbol_address(project, 'syscall_end')
    assert syscall_state.solver.eval_one(syscall_state.regs.rax) == 0
    assert syscall_state.posix.get_fd(2) is None
    assert ('close',) in events['syscall']


def test_filters_timing_and_removal(tmp_path):
    velnora = import_product()
    project = instrumentation_program(tmp_path)
    seen = {}
    # Every arm starts from identical program state; only registration differs.
    for mode in ('before', 'after', 'wrong_address', 'predicate_true', 'predicate_false', 'removed'):
        state = instrumentation_state(project)
        observations = []

        def callback(current):
            observations.append((concrete_value(current, current.inspect.attrs.mem_write_address),
                                 current.solver.eval_one(current.memory.load(
                                     0x600000, 8, endness='Iend_LE', inspect=False))))

        kwargs = {'mem_write_address': 0x600008 if mode == 'wrong_address' else 0x600000}
        if mode.startswith('predicate_'):
            kwargs['condition'] = lambda current: current.solver.eval_one(current.regs.rdi) == (
                0x600000 if mode == 'predicate_true' else 0x600008)
        bp = state.inspect.b('mem_write', when=velnora.BP_BEFORE if mode == 'before' else velnora.BP_AFTER,
                             action=callback, **kwargs)
        if mode == 'removed':
            state.inspect.remove_breakpoint('mem_write', bp=bp)
        final = walk_to(project, state, symbol_address(project, 'done'))
        assert final.solver.eval_one(final.memory.load(0x600000, 8, endness='Iend_LE', inspect=False)) == 18
        seen[mode] = observations
    assert seen['before'] and set(seen['before']) == {(0x600000, 11)}
    for mode in ('after', 'predicate_true'):
        assert seen[mode] and set(seen[mode]) == {(0x600000, 18)}
    for mode in ('wrong_address', 'predicate_false', 'removed'):
        assert seen[mode] == []


def test_before_callbacks_change_execution(tmp_path):
    velnora = import_product()
    project = instrumentation_program(tmp_path)
    results = []
    for altered in (False, True):
        state = instrumentation_state(project)
        state.memory.store(0x600008, (37).to_bytes(8, 'little'))
        if altered:
            def redirect_write(current):
                current.inspect.attrs.mem_write_address = 0x600008
                current.inspect.attrs.mem_write_expr = claripy.BVV(79, 64)
            state.inspect.b('mem_write', when=velnora.BP_BEFORE, mem_write_address=0x600000,
                            action=redirect_write)
        result = single_successor(project, state)
        results.append(tuple(result.solver.eval_one(result.memory.load(address, 8, endness='Iend_LE'))
                             for address in (0x600000, 0x600008)))
    assert results == [(18, 37), (11, 79)]
    for altered in (False, True):
        state = instrumentation_state(project, 'resumed')
        if altered:
            def redirect_exit(current):
                current.inspect.attrs.exit_target = claripy.BVV(symbol_address(project, 'left'), 64)
            state.inspect.b('exit', when=velnora.BP_BEFORE, action=redirect_exit)
        result = single_successor(project, state)
        assert result.addr == symbol_address(project, 'left' if altered else 'done')


def test_history_forks_hooks_and_accesses(tmp_path):
    velnora = import_product()
    project = instrumentation_program(tmp_path)
    def replacement(current):
        current.regs.rax = current.regs.rax + 100
    project.hook(symbol_address(project, 'modeled'), replacement, length=5)
    state = instrumentation_state(project, 'branch_start', add_options={
        velnora.options.TRACK_MEMORY_ACTIONS, velnora.options.TRACK_REGISTER_ACTIONS})
    choice = claripy.BVS('history_choice', 64)
    state.regs.rdi = choice
    forks = project.factory.successors(state).flat_successors
    assert {fork.addr for fork in forks} == {symbol_address(project, name) for name in ('left', 'right')}
    frozen = [list(fork.history.bbl_addrs) for fork in forks]
    for fork in forks:
        branch = 'left' if fork.addr == symbol_address(project, 'left') else 'right'
        final = walk_to(project, fork, symbol_address(project, 'done'))
        assert list(final.history.bbl_addrs) == [symbol_address(project, name)
            for name in ('branch_start', branch, 'modeled', 'modeled_end')]
        guards = list(final.history.jump_guards)
        kinds = list(final.history.jumpkinds)
        assert kinds[-4:] == ['Ijk_Boring'] * 4
        assert not claripy.Solver().satisfiable(extra_constraints=[
            guards[-4] != (choice == 0 if branch == 'left' else choice != 0)])
        assert not final.solver.satisfiable(extra_constraints=[choice != 0 if branch == 'left' else choice == 0])
        assert final.solver.eval_one(final.regs.rax) == (117 if branch == 'left' else 123)
    assert [list(fork.history.bbl_addrs) for fork in forks] == frozen
    assert all(past == [symbol_address(project, 'branch_start')] for past in frozen)
    state = instrumentation_state(project, add_options={
        velnora.options.TRACK_MEMORY_ACTIONS, velnora.options.TRACK_REGISTER_ACTIONS})
    final = single_successor(project, state)
    actions = list(final.history.actions)
    for kind, direction, address, value in (
            ('mem', 'read', 0x600000, 11), ('mem', 'write', 0x600000, 18),
            ('reg', 'read', project.arch.registers['rdi'][0], 0x600000),
            ('reg', 'write', project.arch.registers['rax'][0], 18)):
        assert any(action.type == kind and action.action == direction
                   and final.solver.eval_one(action.addr.ast) == address
                   and final.solver.eval_one(action.data.ast) == value for action in actions)
    final = walk_to(project, final, symbol_address(project, 'done'))
    assert list(final.history.bbl_addrs) == [symbol_address(project, name)
        for name in ('_start', 'outer', 'inner', 'outer_resume', 'resumed')]
    assert list(final.history.jumpkinds)[-5:] == [
        'Ijk_Call', 'Ijk_Call', 'Ijk_Ret', 'Ijk_Ret', 'Ijk_Boring']
    assert all(not claripy.Solver().satisfiable(extra_constraints=[~guard])
               for guard in list(final.history.jump_guards)[-5:])


def test_nested_call_frames_restore_caller(tmp_path):
    project = instrumentation_program(tmp_path)
    state = instrumentation_state(project, 'call_site')
    original = tuple((frame.func_addr, frame.call_site_addr, frame.ret_addr, frame.stack_ptr)
                     for frame in state.callstack)
    outer = single_successor(project, state)
    inner = single_successor(project, outer)
    for current, function, callsite, returnsite, stack in (
            (outer, 'outer', 'call_site', 'resumed', 0x7ffefff8),
            (inner, 'inner', 'outer', 'outer_resume', 0x7ffefff0)):
        frame = current.callstack
        assert (frame.func_addr, frame.call_site_addr, frame.ret_addr, frame.stack_ptr) == (
            symbol_address(project, function), symbol_address(project, callsite),
            symbol_address(project, returnsite), stack)
        assert current.solver.eval_one(current.regs.rsp) == stack
    restored = single_successor(project, inner)
    assert restored.addr == symbol_address(project, 'outer_resume')
    assert tuple((frame.func_addr, frame.call_site_addr, frame.ret_addr, frame.stack_ptr)
                 for frame in restored.callstack) == tuple(
                     (frame.func_addr, frame.call_site_addr, frame.ret_addr, frame.stack_ptr)
                     for frame in outer.callstack)
    returned = single_successor(project, restored)
    assert returned.addr == symbol_address(project, 'resumed')
    assert returned.solver.eval_one(returned.regs.rsp) == 0x7fff0000
    assert tuple((frame.func_addr, frame.call_site_addr, frame.ret_addr, frame.stack_ptr)
                 for frame in returned.callstack) == original
