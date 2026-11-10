# feature: F16
"""Acceptance of finite domains, selection algebra and selection messages."""
from itertools import product

import numpy as np
import pytest
from F16_helpers import (
    NDSEL_SLICE_VECTORS, assert_coordinate_mapping, coordinate_points,
    executable_message, ndsel_refused,
)
from velnora_indexing import (
    ArrayMap, BoundsCheckError, ConstantMap, DimensionMap, IndexDomain,
    IndexTransform, NdselError, normalize_ndsel, parse_ndsel,
)
from _helpers import invoke



def test_f16_t01():
    domain = IndexDomain((-3, 4), (2, 7), labels=('row', 'column'))
    assert domain.inclusive_min == (-3, 4)
    assert domain.exclusive_max == (2, 7)
    assert domain.origin == (-3, 4)
    assert domain.shape == (5, 3)
    assert domain.ndim == 2
    assert domain.labels == ('row', 'column')
    plain = IndexDomain((-3, 4), (2, 7))
    for point, contained in [((-3, 4), True), ((1, 6), True),
                             ((2, 4), False), ((-4, 4), False),
                             ((0, 7), False), ((0,), False)]:
        assert domain.contains(point) is contained
        assert plain.contains(point) is contained
    for subdomain, contained in [
        (IndexDomain((-2, 5), (1, 7)), True),
        (IndexDomain((-3, 4), (2, 7)), True),
        (IndexDomain((2, 4), (2, 7)), True),
        (IndexDomain((3, 4), (3, 7)), False),
        (IndexDomain((-4, 4), (0, 5)), False),
        (IndexDomain((0,), (1,)), False),
    ]:
        assert domain.contains_domain(subdomain) is contained
    scalar = IndexDomain((), ())
    assert scalar.shape == () and scalar.ndim == 0
    assert scalar.contains(()) is True
    empty = IndexDomain((8,), (8,))
    assert empty.shape == (0,)
    assert empty.contains((8,)) is False
    for lower, upper, labels in [((0,), (1, 2), None), ((2,), (1,), None),
                                 ((0, 0), (1, 1), ('only-one',))]:
        with pytest.raises(ValueError):
            IndexDomain(lower, upper, labels)


def test_f16_t02():
    raw = np.array([7, -2, 7, 4])
    selected = IndexTransform(IndexDomain((-2,), (2,)), (
        ConstantMap(11), DimensionMap(0), ArrayMap(raw),
        ArrayMap(raw, offset=3, stride=-2), DimensionMap(0, offset=5, stride=3),
    ))
    expected = [(11, -2, 7, -11, -1), (11, -1, -2, 7, 2),
                (11, 0, 7, -11, 5), (11, 1, 4, -5, 8)]
    assert_coordinate_mapping(selected, (-2,), (2,), expected)
    raw[:] = 100
    assert_coordinate_mapping(selected, (-2,), (2,), expected)
    inner = IndexTransform(IndexDomain((3,), (8,)),
                           (DimensionMap(0, offset=2, stride=-3), ConstantMap(-4)))
    outer = IndexTransform(IndexDomain((0,), (3,)), (ArrayMap(np.array([7, 3, 7])),))
    composed = invoke(outer.compose, inner).value
    assert_coordinate_mapping(composed, (0,), (3,), [(-19, -4), (-7, -4), (-19, -4)])
    # Every pairing of relationship kinds, against arithmetic done here.
    inner_rules = {'constant': (ConstantMap(-4), lambda v: -4),
                   'affine': (DimensionMap(0, offset=2, stride=-3), lambda v: 2 - 3 * v),
                   'explicit': (ArrayMap(np.array([9, 4, 7, 1, 6]), offset=5, stride=2),
                                lambda v: 5 + 2 * [9, 4, 7, 1, 6][v - 3])}
    outer_rules = ((ConstantMap(5), lambda i: 5),
                   (DimensionMap(0, offset=3, stride=2), lambda i: 3 + 2 * i),
                   (ArrayMap(np.array([7, 3, 7])), lambda i: [7, 3, 7][i]))
    for inner_map, inner_value in inner_rules.values():
        second = IndexTransform(IndexDomain((3,), (8,)), (inner_map,))
        for outer_map, outer_value in outer_rules:
            first = IndexTransform(IndexDomain((0,), (3,)), (outer_map,))
            assert_coordinate_mapping(first.compose(second), (0,), (3,),
                                      [(inner_value(outer_value(i)),) for i in range(3)])
    # Several request axes, an explicit rule addressed by both of them.
    table = np.arange(6).reshape(2, 3) * 5 - 4
    second = IndexTransform(IndexDomain((1, 2), (3, 5)),
                            (ArrayMap(table, offset=3, stride=2), DimensionMap(1, offset=-1), ConstantMap(9)))
    first = IndexTransform(IndexDomain((0, 0), (2, 2)),
                           (ArrayMap(np.array([[1], [2]])), DimensionMap(1, offset=2, stride=2)))
    assert_coordinate_mapping(first.compose(second), (0, 0), (2, 2),
                              [(3 + 2 * int(table[r - 1, c - 2]), c - 1, 9) for r in (1, 2) for c in (2, 4)])
    # Nothing selected, so nothing is outside the source.
    empty = IndexTransform(IndexDomain((0,), (0,)), (DimensionMap(0, offset=99),)).compose(
        IndexTransform(IndexDomain((3,), (8,)), (DimensionMap(0),)))
    assert_coordinate_mapping(empty, (0,), (0,), [])
    moved = selected.translate_domain_by((9,))
    assert_coordinate_mapping(moved, (7,), (11,), expected)
    translated_domain = IndexDomain((-2, 4), (3, 8)).translate((6, -7))
    assert translated_domain.inclusive_min == (4, -3)
    assert translated_domain.exclusive_max == (9, 1)
    # Axis permutation is expressed through public dimension mappings.
    swap = IndexTransform(IndexDomain((4, -2), (8, 3)), (DimensionMap(1), DimensionMap(0)))
    assert_coordinate_mapping(swap, (4, -2), (8, 3),
                              [(j, i) for i, j in coordinate_points((4, -2), (8, 3))])
    for entry, argument in [(selected.translate_domain_by, (1, 2)),
                            (IndexDomain((0,), (2,)).translate, (1, 2)),
                            (outer.compose, IndexTransform.from_shape((2, 2)))]:
        with pytest.raises(ValueError):
            invoke(entry, argument)


def test_f16_t03():
    source = IndexTransform(IndexDomain((10, 20), (14, 24)), (
        ArrayMap(np.array([[8], [2], [9], [2]])),
        DimensionMap(1, offset=-60, stride=3), ConstantMap(5),
    ))
    assert_coordinate_mapping(source, (10, 20), (14, 24),
        [(x, y, 5) for x in (8, 2, 9, 2) for y in (0, 3, 6, 9)])
    narrowed = source[11:14, 21:23]
    assert_coordinate_mapping(narrowed, (11, 21), (14, 23),
                              [(x, y, 5) for x in (2, 9, 2) for y in (3, 6)])
    result = invoke(source.intersect, IndexDomain((2, 2, 5), (9, 8, 6))).value
    assert result is not None
    retained, _ = result
    # Dropping position 12 renumbers the first axis; the documents leave its new
    # origin open, so it is checked relative to its own lower bound.
    start = retained.domain.inclusive_min[0]
    assert_coordinate_mapping(retained, (start, 21), (start + 3, 23),
                              [(x, y, 5) for x in (8, 2, 2) for y in (3, 6)])
    assert source.intersect(IndexDomain((30, 2, 5), (40, 8, 6))) is None
    assert source.intersect(IndexDomain((2, 2, 6), (9, 8, 7))) is None
    with pytest.raises(ValueError):
        source.intersect(IndexDomain.from_shape((3,)))
    outer = IndexTransform(IndexDomain.from_shape((2,)), (ArrayMap(np.array([3, 8])),))
    with pytest.raises(BoundsCheckError):
        outer.compose(IndexTransform.identity(IndexDomain((3,), (8,))))
    with pytest.raises(BoundsCheckError):
        source[9:12, :]


def test_f16_t04():
    base = IndexTransform.from_shape((5, 6))
    basic = base[None, 3, 1:6:2]
    assert_coordinate_mapping(basic, (0, 0), (1, 3), [(3, 1), (3, 3), (3, 5)])
    reverse = base[::-2, 2]
    assert_coordinate_mapping(reverse, (-2,), (1,), [(4, 2), (2, 2), (0, 2)])
    scalar = base[2, 4]
    assert_coordinate_mapping(scalar, (), (), [(2, 4)])
    outer = base.oindex[[4, 1, 1], [5, 0]]
    assert_coordinate_mapping(outer, (0, 0), (3, 2),
                              [(i, j) for i in (4, 1, 1) for j in (5, 0)])
    paired = base.vindex[np.array([4, 1, 1]), np.array([5, 0, 5])]
    assert_coordinate_mapping(paired, (0,), (3,), [(4, 5), (1, 0), (1, 5)])
    broadcast = base.vindex[np.array([[4], [1]]), np.array([[5, 0, 5]])]
    assert_coordinate_mapping(broadcast, (0, 0), (2, 3),
                              [(i, j) for i in (4, 1) for j in (5, 0, 5)])
    mask = np.zeros((5, 6), dtype=bool)
    mask[0, 5] = mask[2, 1] = mask[4, 0] = True
    assert_coordinate_mapping(base.vindex[mask], (0,), (3,), [(0, 5), (2, 1), (4, 0)])
    mask[:] = False
    assert_coordinate_mapping(base.vindex[mask], (0,), (0,), [])
    assert_coordinate_mapping(base.oindex[np.array([True, False, True, False, False]), 3:4],
                              (0, 3), (2, 4), [(0, 3), (2, 3)])


def test_f16_t05():
    messages = [
        ({'kind': 'point', 'coords': [-4, 9]}, (), (), [(-4, 9)]),
        ({'kind': 'box', 'inclusive_min': [-2], 'exclusive_max': [2]},
         (-2,), (2,), [(-2,), (-1,), (0,), (1,)]),
        ({'kind': 'slice', 'start': [3], 'stop': [6]}, (3,), (6,), [(3,), (4,), (5,)]),
        ({'kind': 'points', 'coords': [[4, 8], [-1, 2], [4, 8]]},
         (0,), (3,), [(4, 8), (-1, 2), (4, 8)]),
        ({'kind': 'transform', 'input_shape': [3],
          'output': [{'input_dimension': 0, 'offset': 7, 'stride': -2}]},
         (0,), (3,), [(7,), (5,), (3,)]),
    ]
    for message, lower, upper, expected in messages:
        validated = invoke(parse_ndsel, message).value
        assert_coordinate_mapping(executable_message(validated), lower, upper, expected)
    failures = [
        ({'kind': 'unsupported'}, 'unknown_kind'),
        ({'kind': 'point', 'coords': [1], 'extra': 2}, 'unknown_field'),
        ({'kind': 'slice', 'start': [0, 1], 'stop': [3]}, 'rank_mismatch'),
        ({'kind': 'box', 'shape': [3], 'exclusive_max': [3]}, 'multiple_upper_bounds'),
        ({'kind': 'box', 'inclusive_min': [3], 'exclusive_max': [2]}, 'bounds_out_of_order'),
        ({'kind': 'slice', 'start': [3], 'stop': [2]}, 'bounds_out_of_order'),
        ({'kind': 'slice', 'start': [2], 'stop': [3], 'step': [-1]}, 'bounds_out_of_order'),
        ({'kind': 'slice', 'start': [0], 'stop': [3], 'step': [0]}, 'step_zero'),
        ({'kind': 'transform', 'input_shape': [2],
          'output': [{'input_dimension': 0, 'index_array': [0, 1]}]}, 'output_map_conflict'),
        ({'kind': 'transform', 'input_rank': 1, 'input_shape': [2, 3]}, 'rank_mismatch'),
        ({'kind': 'transform', 'input_rank': 1, 'output': [{'input_dimension': 1}]},
         frozenset({'rank_mismatch', 'invalid_json'})),
    ]
    for value in (True, 1.5, '3', -(2**63)-1, 2**63):
        failures.append(({'kind': 'point', 'coords': [value]}, 'invalid_json'))
    for member in ('box', 'slice', 'points', 'transform'):
        extra = {'box': {}, 'slice': {'start': [0], 'stop': [1]},
                 'points': {'coords': [[1]]}, 'transform': {}}[member]
        failures.append(({'kind': member, **extra, 'extra': 1}, 'unknown_field'))
    failures += [({'kind': 'points', 'coords': [[1], [1, 2]]}, 'rank_mismatch'),
                 ({'kind': 'box', 'inclusive_min': [0], 'labels': ['a', 'b']}, 'rank_mismatch'),
                 ({'kind': 'slice', 'start': [0], 'stop': [1], 'step': [True]}, 'invalid_json'),
                 ({'kind': 'box', 'inclusive_min': [True]}, 'invalid_json'),
                 ({'kind': 'transform', 'output': [{'offset': True}]}, 'invalid_json')]
    for rank in (-1, 33):
        failures.append(({'kind': 'transform', 'input_rank': rank}, 'invalid_json'))
    for entry in (parse_ndsel, normalize_ndsel):
        for message, reason in failures:
            ndsel_refused(entry, message, reason)
    # Missing required members are refused; their reason label is not promised.
    for message in ({'kind': 'point'}, {'kind': 'slice', 'start': [1]}, {'kind': 'slice', 'stop': [1]},
                    {'kind': 'points'}, {'kind': 'points', 'coords': [1]}):
        for entry in (parse_ndsel, normalize_ndsel):
            with pytest.raises(NdselError):
                invoke(entry, message)
    for rank in (0, 32):
        body = normalize_ndsel({'kind': 'transform', 'input_rank': rank})
        assert body['input_rank'] == rank
        assert len(body['input_inclusive_min']) == rank
    extremes = [-(2**63), 2**63-1]
    assert_coordinate_mapping(executable_message({'kind': 'point', 'coords': extremes}),
                              (), (), [tuple(extremes)])
    for step in (1, -2):
        empty = executable_message({'kind': 'slice', 'start': [0], 'stop': [0], 'step': [step]})
        assert_coordinate_mapping(empty, (0,), (0,), [])


def test_f16_t06():
    for kind, prefix in [('box', ''), ('transform', 'input_')]:
        for upper_key, value in [('exclusive_max', [5]), ('inclusive_max', [4]), ('shape', [3])]:
            message = {'kind': kind, prefix+'inclusive_min': [2], prefix+upper_key: value}
            body = normalize_ndsel(message)
            assert body['input_rank'] == 1
            assert body['input_labels'] == ['']
            assert body['input_inclusive_min'] == [2]
            assert body['input_exclusive_max'] == [5]
            assert normalize_ndsel({'kind': 'transform', **body}) == body
            loaded = IndexTransform.from_json(body)
            assert_coordinate_mapping(loaded, (2,), (5,), [(2,), (3,), (4,)])
            restored = IndexTransform.from_json(loaded.to_json())
            assert_coordinate_mapping(restored, (2,), (5,), [(2,), (3,), (4,)])
        defaulted = normalize_ndsel({'kind': kind, prefix+'shape': [2]})
        # An omitted lower bound is zero; whether it normalizes as explicit or implicit is open.
        assert defaulted['input_inclusive_min'] in ([0], [[0]])
        assert defaulted['input_labels'] == ['']
        assert_coordinate_mapping(IndexTransform.from_json(defaulted), (0,), (2,), [(0,), (1,)])
        for first, second in [('exclusive_max', 'inclusive_max'), ('shape', 'exclusive_max'),
                              ('shape', 'inclusive_max')]:
            ndsel_refused(normalize_ndsel,
                          {'kind': kind, prefix+first: [2], prefix+second: [2]},
                          'multiple_upper_bounds')
        empty_description = normalize_ndsel({'kind': kind})
        assert empty_description == {'input_rank': 0, 'input_inclusive_min': [],
                                     'input_exclusive_max': [], 'input_labels': [], 'output': []}
        for rank_source in ({prefix+'labels': ['axis']}, {prefix+'inclusive_min': [0]}):
            unbounded = normalize_ndsel({'kind': kind, **rank_source})
            assert unbounded['input_rank'] == 1
            assert unbounded['input_inclusive_min'] in (([0], [[0]]) if prefix + 'labels' in rank_source else ([0],))
            assert unbounded['input_exclusive_max'] == [['+inf']]
            assert normalize_ndsel({'kind': 'transform', **unbounded}) == unbounded
            ndsel_refused(IndexTransform.from_json, unbounded, 'invalid_json')
        implicit = normalize_ndsel({'kind': kind, prefix+'inclusive_min': [[2]],
                                    prefix+'inclusive_max': [[4]]})
        assert implicit['input_inclusive_min'] == [[2]]
        assert implicit['input_exclusive_max'] == [[5]]
        assert normalize_ndsel({'kind': 'transform', **implicit}) == implicit
        assert_coordinate_mapping(IndexTransform.from_json(implicit), (2,), (5,), [(2,), (3,), (4,)])
    full = {'kind': 'transform', 'input_shape': [3], 'input_labels': ['axis'],
            'output': [{'index_array': [9, -2, 4], 'offset': 7, 'stride': 0}]}
    body = normalize_ndsel(full)
    assert body['input_labels'] == ['axis']
    assert normalize_ndsel({'kind': 'transform', **body}) == body
    loaded = IndexTransform.from_json(body)
    assert_coordinate_mapping(loaded, (0,), (3,), [(7,), (7,), (7,)])
    assert_coordinate_mapping(IndexTransform.from_json(loaded.to_json()), (0,), (3,), [(7,), (7,), (7,)])
    for message in ({'kind': 'point', 'coords': [2, -3]},
                    {'kind': 'slice', 'start': [5], 'stop': [10], 'step': [2]},
                    {'kind': 'points', 'coords': [[3, 5], [-2, 1], [3, 5]]}):
        normalized = normalize_ndsel(message)
        assert normalize_ndsel({'kind': 'transform', **normalized}) == normalized
    # Omitted output rules, offsets and strides, for both varying kinds.
    for output, expected in (({'input_dimension': 0}, [0, 1, 2]), ({'input_dimension': 0, 'offset': 4}, [4, 5, 6]),
                             ({'input_dimension': 0, 'stride': 2}, [0, 2, 4]), ({'index_array': [5, 6, 7]}, [5, 6, 7]),
                             ({'index_array': [5, 6, 7], 'offset': 1}, [6, 7, 8]),
                             ({'index_array': [5, 6, 7], 'stride': 2}, [10, 12, 14])):
        loaded = executable_message({'kind': 'transform', 'input_shape': [3], 'output': [output]})
        assert_coordinate_mapping(loaded, (0,), (3,), [(value,) for value in expected])
    assert_coordinate_mapping(executable_message({'kind': 'transform', 'input_shape': [3]}),
                              (0,), (3,), [(0,), (1,), (2,)])
    # An explicit rule varying along part of a two-axis request.
    loaded = IndexTransform.from_json({'input_shape': [2, 3], 'output': [{'index_array': [[7], [8]]}]})
    assert_coordinate_mapping(loaded, (0, 0), (2, 3), [(7,)] * 3 + [(8,)] * 3)
    # Refused as invalid exchange data; which reason label each gets is not promised.
    for output in ({'index_array': [True, False]}, {'index_array': [1.5, 2]}, {'index_array': [[1], [1, 2]]},
                   {'index_array': [1, 2, 3]}, {'index_array': 3}, {'input_dimension': 5}):
        with pytest.raises(NdselError):
            IndexTransform.from_json({'input_shape': [2], 'output': [output]})
    # Exchange also preserves a nondegenerate explicit-coordinate relationship.
    loaded = executable_message({'kind': 'points', 'coords': [[3, 5], [-2, 1], [3, 5]]})
    assert_coordinate_mapping(IndexTransform.from_json(loaded.to_json()), (0,), (3,),
                              [(3, 5), (-2, 1), (3, 5)])


def test_f16_t07():
    for values, bounds, offset, stride, expected in [
        ([-3, 0, 4], [-3, 4], 10, -2, [(16,), (10,), (2,)]),
        ([2], [2, 2], -8, 0, [(-8,)]),
        ([], [2, 2], 0, 1, []),
        ([-3, 4], ['-inf', '+inf'], 0, 1, [(-3,), (4,)]),
    ]:
        body = {'input_shape': [len(values)], 'output': [
            {'index_array': values, 'index_array_bounds': bounds, 'offset': offset, 'stride': stride}]}
        assert_coordinate_mapping(IndexTransform.from_json(body), (0,), (len(values),), expected)
    # The invalid coordinate would be omitted by a later selection, and scaling
    # would hide its value; loading must reject before either can do so.
    for values, bounds, offset, stride, reason in [
        ([-1, 1], [0, 2], 1, 1, 'invalid_json'),
        ([1, 3], [0, 2], 0, 0, 'invalid_json'),
        ([1, 3], ['-inf', 2], 0, -1, 'invalid_json'),
        ([-1, 1], [0, '+inf'], 0, 1, 'invalid_json'),
        ([], [3, 2], 0, 1, 'bounds_out_of_order'),
    ]:
        ndsel_refused(IndexTransform.from_json, {'input_shape': [len(values)], 'output': [
            {'index_array': values, 'index_array_bounds': bounds, 'offset': offset, 'stride': stride}]}, reason)


def test_f16_t08():
    source = IndexTransform.identity(IndexDomain((-12,), (22,)))
    for start, stop, step, lower, upper, values in NDSEL_SLICE_VECTORS:
        expected = [(value,) for value in values]
        direct = source[slice(start, stop, step)]
        message = executable_message({'kind': 'slice', 'start': [start], 'stop': [stop], 'step': [step]})
        assert_coordinate_mapping(direct, (lower,), (upper,), expected)
        assert_coordinate_mapping(message, (lower,), (upper,), expected)
    def truncated(value, divisor):
        quotient = abs(value) // abs(divisor)
        return quotient if (value < 0) == (divisor < 0) else -quotient
    for start, stop, step in product(range(-7, 8, 2), range(-8, 9, 3), (-3, -2, -1, 1, 2, 3)):
        against = (step > 0 and stop < start) or (step < 0 and stop > start)
        message = {'kind': 'slice', 'start': [start], 'stop': [stop], 'step': [step]}
        if against:
            ndsel_refused(normalize_ndsel, message, 'bounds_out_of_order')
            continue
        values = list(range(start, stop, step))
        lower = truncated(start, step)
        expected = [(value,) for value in values]
        assert_coordinate_mapping(source[slice(start, stop, step)], (lower,), (lower + len(values),), expected)
        assert_coordinate_mapping(executable_message(message), (lower,), (lower + len(values),), expected)
    defaults = IndexTransform.identity(IndexDomain((-3,), (4,)))
    assert_coordinate_mapping(defaults[:], (-3,), (4,), [(i,) for i in range(-3, 4)])
    assert_coordinate_mapping(defaults[::-1], (-3,), (4,), [(i,) for i in range(3, -4, -1)])
    for selection in (slice(-4, 2), slice(-2, 5), slice(-4, None), slice(None, 5)):
        with pytest.raises(BoundsCheckError):
            defaults[selection]
    for step, origin in [(1, 100), (-1, -100)]:
        assert_coordinate_mapping(defaults[slice(100, 100, step)], (origin,), (origin,), [])
