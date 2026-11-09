# feature: F15
"""Acceptance checks for abstract integer sets and native value flow."""
import operator
from F01_helpers import expression_api
from F07_helpers import symbol_address
from F15_helpers import valueflow_program, analyze_values, exit_values


def test_strided_sets_singletons_and_empty_intersection():
    _, c = expression_api()
    for bits, lower, upper, stride in ((8, 5, 29, 4), (16, 301, 343, 7)):
        value = c.SI(bits=bits, lower_bound=lower, upper_bound=upper, stride=stride)
        assert c.vsa.min(value) == lower
        assert c.vsa.max(value) == upper
        for candidate in range(lower - 1, upper + 2):
            assert (candidate in c.vsa.eval(value, 1 << bits)) == (candidate in range(lower, upper + 1, stride))
        single = c.SI(bits=bits, lower_bound=upper, upper_bound=upper, stride=0)
        assert set(c.vsa.eval(single, 2)) == {upper}
        empty = single.intersection(c.SI(bits=bits, lower_bound=lower, upper_bound=lower, stride=0))
        assert tuple(c.vsa.eval(empty, 2)) == ()
        assert not (lower in c.vsa.eval(empty, 2))
        assert not (upper in c.vsa.eval(empty, 2))
        # Disjoint multi-valued sets also have an empty intersection.
        disjoint = value.intersection(c.SI(bits=bits, lower_bound=upper + 11,
                                           upper_bound=upper + 11 + 5 * stride, stride=stride))
        assert tuple(c.vsa.eval(disjoint, 2)) == ()


def test_operations_retain_feasible_values():
    _, c = expression_api()
    a_values, b_values = range(6, 19, 3), range(2, 9, 2)
    a = c.SI(bits=8, stride=3, lower_bound=6, upper_bound=18)
    b = c.SI(bits=8, stride=2, lower_bound=2, upper_bound=8)
    for operation in (operator.add, operator.sub, operator.mul, operator.floordiv, operator.mod,
                      operator.and_, operator.or_):
        result = operation(a, b)
        feasible = {operation(x, y) & 255 for x in a_values for y in b_values}
        assert feasible <= set(c.vsa.eval(result, 256))
    high = c.SI(bits=8, stride=0, lower_bound=128, upper_bound=128)
    xor_result = a ^ high
    assert {x ^ y for x in a_values for y in (128,)} <= set(c.vsa.eval(xor_result, 256))
    for result, feasible in ((a.union(b), set(a_values) | set(b_values)),
                             (a.intersection(b), set(a_values) & set(b_values))):
        assert feasible <= set(c.vsa.eval(result, 256))
    for result, feasible in ((a << 1, {x * 2 & 255 for x in a_values}),
                             (c.LShR(a, 1), {x >> 1 for x in a_values}),
                             (~a, {~x & 255 for x in a_values}),
                             (-a, {-x & 255 for x in a_values})):
        assert feasible <= set(c.vsa.eval(result, 256))


def test_valueflow_preserves_branches_memory_and_call_scope(tmp_path):
    _, c = expression_api()
    project = valueflow_program(tmp_path)
    argument = c.SI(bits=32, stride=1, lower_bound=0, upper_bound=1)
    full = analyze_values(project, '_start', 4, argument)
    reached = {node.addr for node in full.graph.nodes()}
    assert {symbol_address(project, name) for name in
            ('_start', 'choose', 'arm_zero', 'arm_one', 'joined', 'after_choose')} <= reached
    for entry, feasible in (('choose', {12, 24}), ('_start', {15, 27})):
        states = exit_values(full, symbol_address(project, entry))
        assert all(any(c.SolverVSA().solution(state.regs.eax, value) for state in states)
                   for value in feasible)
        address = symbol_address(project, 'datum')
        assert all(any(c.SolverVSA().solution(state.memory.load(address, 4, endness='Iend_LE'), value)
                       for state in states) for value in (23, 41))
    shallow = analyze_values(project, '_start', 0, argument)
    assert symbol_address(project, '_start') in {node.addr for node in shallow.graph.nodes()}
    assert symbol_address(project, 'choose') not in {node.addr for node in shallow.graph.nodes()}
    direct = analyze_values(project, 'choose', 0, argument)
    states = exit_values(direct, symbol_address(project, 'choose'))
    assert all(any(c.SolverVSA().solution(state.regs.eax, value) for state in states) for value in (12, 24))


def test_resetting_accumulator_exit_bounds(tmp_path):
    _, c = expression_api()
    for bound in (4, 9):
        directory = tmp_path / str(bound)
        directory.mkdir()
        project = valueflow_program(directory, bound=bound)
        analysis = analyze_values(project, 'reset_loop', 0,
            c.SI(bits=32, stride=1, lower_bound=0, upper_bound=30),
            max_iterations_before_widening=64, max_iterations=100)
        node = analysis.get_any_node(symbol_address(project, 'loop_exit'))
        assert node is not None
        assert node.final_states
        for state in node.final_states:
            assert 0 <= c.vsa.min(state.regs.eax) <= c.vsa.max(state.regs.eax) <= bound
        assert all(any(c.SolverVSA().solution(state.regs.eax, value) for state in node.final_states)
                   for value in range(bound + 1))


def test_nonwrapping_interval_add_subtract_exact_extrema():
    _, c = expression_api()
    for bits, left, right in ((8, (31, 46), (3, 12)),
                              (16, (1200, 1251), (400, 417)),
                              (32, (100000, 102000), (700, 730))):
        a = c.SI(bits=bits, stride=1, lower_bound=left[0], upper_bound=left[1])
        b = c.SI(bits=bits, stride=1, lower_bound=right[0], upper_bound=right[1])
        for result, bounds in ((a + b, (left[0] + right[0], left[1] + right[1])),
                               (a - b, (left[0] - right[1], left[1] - right[0]))):
            assert c.vsa.min(result) == bounds[0]
            assert c.vsa.max(result) == bounds[1]
