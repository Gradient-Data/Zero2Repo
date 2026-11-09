# feature: F11
"""Acceptance checks for state groups and bounded or guided exploration."""
import pytest
import velnora

# The documented expression namespace is the velnora.claripy attribute.
claripy = velnora.claripy
from _helpers import import_product
from F07_helpers import symbol_address
from F11_helpers import (exploration_program, exploration_state, branch_input,
                         assert_branch_results)


def test_selected_groups_and_state_operations(tmp_path):
    p = exploration_program(tmp_path)
    a = exploration_state(p, 'chain')
    b = exploration_state(p, 'chain1')
    parked = exploration_state(p, 'chain2')
    m = p.factory.simulation_manager([a, b], stashes={'parked': [parked]})
    m.step(selector_func=lambda s: s.addr == symbol_address(p, 'chain'))
    assert [s.addr for s in m.active] == [symbol_address(p, 'chain1')] * 2
    assert sorted(s.solver.eval_one(s.regs.rax) for s in m.active) == [0, 1]
    assert m.parked[0].addr == symbol_address(p, 'chain2')
    assert m.parked[0].history.block_count == 0
    m.move(from_stash='active', to_stash='selected',
           filter_func=lambda s: s.solver.eval_one(s.regs.rax) == 1)
    assert len(m.selected) == len(m.active) == 1
    m.step(stash='selected')
    assert m.selected[0].addr == symbol_address(p, 'chain2')
    assert m.selected[0].solver.eval_one(m.selected[0].regs.rax) == 3
    assert m.active[0].addr == symbol_address(p, 'chain1')
    m.step(filter_func=lambda s: 'filtered')
    assert not m.active
    assert len(m.filtered) == 1
    assert m.filtered[0].addr == symbol_address(p, 'chain1')
    m.drop(stash='selected')
    assert not m.selected
    assert len(m.filtered) == len(m.parked) == 1
    m.move(from_stash='filtered', to_stash='active')
    m.move(from_stash='parked', to_stash='active')
    m.step()
    assert {s.addr for s in m.active} == {symbol_address(p, 'chain2'), symbol_address(p, 'chain3')}
    assert sorted(s.solver.eval_one(s.regs.rax) for s in m.active) == [2, 4]


def test_merge_preserves_feasible_correlations(tmp_path):
    p = exploration_program(tmp_path)
    state, x = branch_input(p)
    m = p.factory.simulation_manager(state)
    m.explore(find=symbol_address(p, 'join'), num_find=3, n=12)
    assert len(m.found) == 2
    assert not m.active and not m.errored
    m.merge(stash='found')
    assert len(m.found) == 1
    assert_branch_results(m.found, x)


def test_execution_outcome_groups_and_error_records(tmp_path):
    p = exploration_program(tmp_path)
    state, x = branch_input(p)
    state.add_constraints(x == 0)
    m = p.factory.simulation_manager(state, save_unsat=True)
    m.step()
    assert len(m.active) == len(m.unsat) == 1
    assert m.active[0].addr == symbol_address(p, 'left')
    assert m.active[0].solver.satisfiable()
    assert m.unsat[0].addr == symbol_address(p, 'right')
    assert not m.unsat[0].solver.satisfiable()
    indirect = exploration_state(p, 'indirect')
    indirect.regs.rax = claripy.BVS('destination', 64)
    m = p.factory.simulation_manager(indirect, save_unconstrained=True)
    m.step()
    assert not m.active and not m.errored
    assert len(m.unconstrained) == 1
    assert len(m.unconstrained[0].solver.eval_upto(m.unconstrained[0].regs.rip, 3)) == 3
    m = p.factory.simulation_manager(exploration_state(p, 'terminate'))
    m.run(n=8)
    assert not m.active and not m.errored
    assert len(m.deadended) == 1
    assert m.deadended[0].solver.satisfiable()
    m = p.factory.simulation_manager(exploration_state(p, 'bad'))
    m.step()
    assert not m.active and not m.deadended
    assert len(m.errored) == 1
    assert m.errored[0].state.addr == symbol_address(p, 'bad')
    assert m.errored[0].state.history.block_count == 0
    assert isinstance(m.errored[0].error, import_product().errors.SimIRSBNoDecodeError)


def test_search_conditions_counts_and_precedence(tmp_path):
    p = exploration_program(tmp_path)
    # Staggered arrivals expose stopping without assuming an order among ties.
    def candidates():
        result = []
        for label in ('chain', 'chain1', 'chain2'):
            result.append(exploration_state(p, label))
        return p.factory.simulation_manager(result)
    addresses = {symbol_address(p, 'chain3')}
    for count, expected in ((None, 1), (2, 2), (5, 3)):
        m = candidates()
        options = {} if count is None else {'num_find': count}
        m.explore(find=lambda s: s.addr in addresses, n=10, **options)
        assert len(m.found) == expected
        assert len(m.active) == 3 - expected
        assert all(s.addr in addresses for s in m.found)
    state, x = branch_input(p)
    m = p.factory.simulation_manager(state)
    m.explore(find=symbol_address(p, 'left'),
              avoid=lambda s: s.addr == symbol_address(p, 'right'), num_find=2, n=12)
    assert len(m.found) == len(m.avoid) == 1
    assert m.found[0].solver.eval_one(x) == 0
    assert set(m.avoid[0].solver.eval_upto(x, 3)) == {4, 9}
    assert not m.active and not m.errored
    for priority in (False, True):
        m = p.factory.simulation_manager(exploration_state(p, 'chain'))
        options = {'avoid_priority': True} if priority else {}
        m.explore(find=symbol_address(p, 'chain'), avoid=symbol_address(p, 'chain'),
                  n=5, **options)
        assert len(m.avoid) == int(priority)
        assert len(m.found) == int(not priority)
        retained = m.avoid if priority else m.found
        assert retained[0].addr == symbol_address(p, 'chain')
        assert not m.active


def test_deferred_paths_and_block_length_limits(tmp_path):
    p = exploration_program(tmp_path)
    velnora = import_product()
    state, x = branch_input(p)
    m = p.factory.simulation_manager(state)
    m.use_technique(velnora.exploration_techniques.DFS())
    m.step()
    assert len(m.active) == len(m.deferred) == 1
    assert {s.addr for s in m.active + m.deferred} == {symbol_address(p, 'left'), symbol_address(p, 'right')}
    m.explore(find=symbol_address(p, 'join'), num_find=2, n=15)
    assert len(m.found) == 2
    assert_branch_results(m.found, x)
    assert not m.deferred
    for drop in (False, True):
        m = p.factory.simulation_manager(exploration_state(p, 'chain'))
        m.use_technique(velnora.exploration_techniques.LengthLimiter(max_length=2, drop=drop))
        m.step(n=2)
        assert len(m.active) == 1
        assert m.active[0].addr == symbol_address(p, 'chain2')
        assert m.active[0].history.block_count == 2
        assert list(m.active[0].history.bbl_addrs) == [symbol_address(p, 'chain'), symbol_address(p, 'chain1')]
        m.step()
        assert not m.active
        if not drop:
            assert len(m.cut) == 1
            assert m.cut[0].addr == symbol_address(p, 'chain3')
            assert m.cut[0].history.block_count == 3
            assert m.cut[0].solver.eval_one(m.cut[0].regs.rax) == 7
        else:
            assert sum(len(states) for states in m.stashes.values()) == 0
        assert not m.errored


def test_loop_bounds_use_execution_history(tmp_path):
    p = exploration_program(tmp_path)
    velnora = import_product()
    cfg = p.analyses.CFGFast(normalize=True)
    for use_header in (False, True):
        for bound in (1, 3):
            state = exploration_state(p, 'loop_start')
            state.regs.rdi = 20
            m = p.factory.simulation_manager(state)
            options = {'use_header': True} if use_header else {}
            m.use_technique(velnora.exploration_techniques.LoopSeer(
                cfg=cfg, functions=symbol_address(p, 'loop_start'), bound=bound, **options))
            m.run(n=40)
            assert not m.active and not m.errored
            assert len(m.spinning) == 1
            cut = m.spinning[0]
            traversals = bound if use_header else bound + 1
            assert cut.addr == symbol_address(p, 'header')
            assert cut.solver.eval_one(cut.regs.rax) == traversals
            history = list(cut.history.bbl_addrs)
            assert history.count(symbol_address(p, 'body')) == traversals
            assert history.count(symbol_address(p, 'header')) == traversals
    # A loop that exits within the bound must still achieve its result.
    state = exploration_state(p, 'loop_start')
    state.regs.rdi = 2
    m = p.factory.simulation_manager(state)
    m.populate('spinning', [])
    m.use_technique(velnora.exploration_techniques.LoopSeer(cfg=cfg, bound=3))
    m.explore(find=symbol_address(p, 'finish'), n=20)
    assert len(m.found) == 1
    assert m.found[0].solver.eval_one(m.found[0].regs.rax) == 2
    assert not m.spinning


def test_concrete_trace_and_mismatch(tmp_path):
    p = exploration_program(tmp_path)
    velnora = import_product()
    from velnora.exploration_techniques.tracer import TracerDesyncError
    trace = [symbol_address(p, name) for name in ('chain', 'chain1', 'chain2', 'chain3')]
    m = p.factory.simulation_manager(exploration_state(p, 'chain'))
    m.use_technique(velnora.exploration_techniques.Tracer(trace=trace, fast_forward_to_entry=False, aslr=False))
    m.run(n=12)
    assert len(m.traced) == 1
    final = m.traced[0]
    assert final.addr == trace[-1]
    assert list(final.history.bbl_addrs) == trace[:-1]
    assert final.solver.eval_one(final.regs.rax) == 7
    m = p.factory.simulation_manager(exploration_state(p, 'chain'))
    m.use_technique(velnora.exploration_techniques.Tracer(
        trace=[trace[0], trace[2], trace[1], trace[3]], fast_forward_to_entry=False, aslr=False))
    with pytest.raises(TracerDesyncError):
        m.run(n=12)
    assert not m.traced


def test_combined_exploration_preserves_downstream_solutions(tmp_path):
    p = exploration_program(tmp_path)
    state, x = branch_input(p)
    m = p.factory.simulation_manager(state, veritesting=True)
    m.explore(find=symbol_address(p, 'finish'), num_find=3, n=15)
    assert not m.errored and not m.active
    assert_branch_results(m.found, x, increment=3)
    # One recovered state carries every feasible alternative across the region.
    assert any(set(found.solver.eval_upto(x, 4)) == {0, 4, 9} for found in m.found)
    solutions = set()
    for state in m.found:
        selected = state.copy()
        selected.add_constraints(selected.regs.rax == 26)
        if selected.solver.satisfiable():
            solutions.update(selected.solver.eval_upto(x, 4))
    assert solutions == {4, 9}
