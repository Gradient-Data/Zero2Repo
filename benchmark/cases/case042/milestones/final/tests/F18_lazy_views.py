# feature: F18
"""Acceptance observations for lazy views, partitions and source writes."""
import numpy as np
import pytest
import velnora

from _helpers import invoke
from F17_helpers import assert_projected_coordinates
from F18_helpers import (
    F18Source, F18DelegatingReader, F18ReaderFailure,
    assert_coordinate_mapping, coordinate_points,
)
from velnora_indexing import BoundsCheckError, LazyArray, IndexDomain, IndexTransform, DimensionMap


def test_f18_t01():
    """Selection metadata is available before any source value can be read."""
    for dtype in (np.int16, np.float32):
        data = (np.arange(48).reshape(6, 8) - 21).astype(dtype)
        source = F18Source(data, readable=False)
        # First establish that this real source refuses value access.
        with pytest.raises(PermissionError):
            source[:]
        base = LazyArray(source)
        basic = base[1:6:2, ::-2]
        outer = basic.oindex[[2, 0, 2], [3, 1]]
        paired = outer.vindex[[2, 0, 1, 2], [1, 0, 1, 1]]
        basic_values = data[1:6:2, ::-2]
        outer_values = basic_values[np.ix_([2, 0, 2], [3, 1])]
        paired_values = outer_values[[2, 0, 1, 2], [1, 0, 1, 1]]
        # Check the composed coordinate meaning without evaluating source values.
        labels = np.arange(data.size).reshape(data.shape)
        selected_labels = labels[1:6:2, ::-2][np.ix_([2, 0, 2], [3, 1])]
        selected_labels = selected_labels[[2, 0, 1, 2], [1, 0, 1, 1]]
        assert basic.shape == basic_values.shape
        assert outer.shape == outer_values.shape
        assert paired.shape == paired_values.shape
        domain = paired.transform.domain
        assert_coordinate_mapping(
            paired.transform, domain.inclusive_min, domain.exclusive_max,
            [np.unravel_index(int(label), data.shape) for label in selected_labels.flat],
        )
        source.readable = True
        for view, expected in ((basic, basic_values), (outer, outer_values),
                               (paired, paired_values)):
            actual = invoke(view.result).value
            assert isinstance(actual, np.ndarray)
            assert actual.dtype == data.dtype
            assert actual.shape == expected.shape
            np.testing.assert_array_equal(actual, expected)
        converted = invoke(np.asarray, paired, call_kwargs={"dtype": np.float64}).value
        assert converted.dtype == np.dtype(np.float64)
        np.testing.assert_array_equal(converted, paired_values.astype(np.float64))
        # Scalar and empty selections retain their requested shapes and dtype.
        for view, expected in ((base[-1, 2], data[-1, 2]),
                               (base[2:2, :], data[2:2, :])):
            actual = invoke(view.result).value
            assert actual.dtype == data.dtype
            assert actual.shape == np.shape(expected)
            np.testing.assert_array_equal(actual, expected)


def test_f18_t02():
    """Relative positions and absolute keys compose in the same view."""
    data = np.arange(80, dtype=np.int32).reshape(10, 8) * 3 - 9
    view = LazyArray(data)[2:9, 1:7][1:6, 1:5]
    assert_coordinate_mapping(view.transform, (3, 2), (8, 6),
                              coordinate_points((3, 2), (8, 6)))
    np.testing.assert_array_equal(invoke(view[-1, -2].result).value, data[7, 4])
    np.testing.assert_array_equal(invoke(view[-99:99, -99:99].result).value,
                                  data[3:8, 2:6])
    restricted = view[IndexDomain((4, 3), (7, 6))]
    assert_coordinate_mapping(restricted.transform, (4, 3), (7, 6),
                              coordinate_points((4, 3), (7, 6)))
    np.testing.assert_array_equal(invoke(restricted.result).value, data[4:7, 3:6])
    # The key maps a different absolute input frame into the existing frame.
    key = IndexTransform(IndexDomain((20, 30), (22, 32)),
                         (DimensionMap(0, offset=-15), DimensionMap(1, offset=-27)))
    composed = restricted[key]
    assert_coordinate_mapping(composed.transform, (20, 30), (22, 32),
                              [(5, 3), (5, 4), (6, 3), (6, 4)])
    np.testing.assert_array_equal(invoke(composed.result).value, data[5:7, 3:5])
    base = LazyArray(data)
    for actual, expected in ((base.oindex[[-1, 0, -1], [-2, 1]], data[np.ix_([-1, 0, -1], [-2, 1])]),
                             (base.vindex[[-1, 0], [-8, 7]], data[[-1, 0], [-8, 7]]),
                             (base[..., -1], data[..., -1]), (base[None, 1:3], data[None, 1:3]),
                             (base[::-1, ::2].oindex[[0, 3], [3, 0]], data[::-1, ::2][np.ix_([0, 3], [3, 0])]),
                             (base[1:6, 2:].vindex[[3, 0, 4], [1, 5, 0]], data[1:6, 2:][[3, 0, 4], [1, 5, 0]]),
                             (base.vindex[data % 7 == 0], data[data % 7 == 0]),
                             (base[2:5, 1:6].oindex[[-1, 0], [-2]], data[2:5, 1:6][np.ix_([-1, 0], [-2])])):
        result = invoke(actual.result).value
        assert result.shape == expected.shape
        np.testing.assert_array_equal(result, expected)
    for refused in (lambda: base[10, 0], lambda: base.oindex[[10], [0]], lambda: base.vindex[[10], [0]],
                    lambda: base.vindex[[-11], [0]], lambda: base[1:3, :][2, 0],
                    lambda: base[..., ...], lambda: base[1, 1, 1]):
        with pytest.raises(IndexError):
            invoke(refused().result)
    with pytest.raises(BoundsCheckError):
        view[IndexDomain((0, 2), (4, 6))]
    with pytest.raises(ValueError):
        view[IndexDomain((3,), (8,))]
    tail = composed[-1:, :][IndexDomain((21, 30), (22, 32))]
    assert_coordinate_mapping(tail.transform, (21, 30), (22, 32), [(6, 3), (6, 4)])
    np.testing.assert_array_equal(invoke(tail.result).value, data[6:7, 3:5])


def test_f18_t03():
    """Part contributions and placements reconstruct repeated, ordered values."""
    data = (np.arange(48).reshape(6, 8) * 0.5 - 7).astype(np.float32)
    source = F18Source(data)
    reader = F18DelegatingReader()
    base = LazyArray(source).with_reader(reader)
    # Verify the selected reader actually delivers data before testing failure.
    for partitioned, edges in (
        (base.with_parts((2, 3)), ((0, 2, 4, 6), (0, 3, 6, 8))),
        (base.with_parts_per_axis(((1, 3, 2), (2, 1, 5))),
         ((0, 1, 4, 6), (0, 2, 3, 8))),
    ):
        view = partitioned.oindex[[5, 0, 5, 2], [7, 1, 4]][1:, :]
        expected = data[np.ix_([5, 0, 5, 2], [7, 1, 4])][1:, :]
        labels = np.arange(data.size).reshape(data.shape)
        selected = labels[np.ix_([5, 0, 5, 2], [7, 1, 4])][1:, :]
        parts = invoke(view.parts, consume=True, max_items=100).value
        expected_map = {p: tuple(np.unravel_index(int(selected[p]), data.shape))
                        for p in np.ndindex(expected.shape)}
        assert_projected_coordinates([part.projection for part in parts], edges, expected_map)
        assembled = np.empty(expected.shape, dtype=data.dtype)
        coverage = np.zeros(expected.shape, dtype=np.int32)
        for part in reversed(parts):
            values = invoke(part.view.result).value
            # Check actual types before assigning into a typed assembly buffer.
            assert isinstance(values, np.ndarray)
            assert values.dtype == data.dtype
            assert values.shape == part.view.shape
            np.testing.assert_array_equal(values, expected[part.out_selection])
            assembled[part.out_selection] = values
            np.add.at(coverage, part.out_selection, 1)
        np.testing.assert_array_equal(coverage, np.ones(expected.shape, dtype=np.int32))
        np.testing.assert_array_equal(assembled, expected)
        actual = invoke(view.result).value
        assert actual.dtype == data.dtype
        np.testing.assert_array_equal(actual, expected)
        # Reversal, paired coordinates and dropped axes also reassemble exactly once.
        for other, wanted in ((partitioned[::-1, ::2], data[::-1, ::2]),
                              (partitioned.vindex[[5, 0, 5, 2], [7, 1, 1, 4]], data[[5, 0, 5, 2], [7, 1, 1, 4]]),
                              (partitioned[2, 1:7], data[2, 1:7])):
            rebuilt = np.empty(wanted.shape, dtype=data.dtype)
            hits = np.zeros(wanted.shape, dtype=np.int32)
            for part in invoke(other.parts, consume=True, max_items=100).value:
                rebuilt[part.out_selection] = invoke(part.view.result).value
                np.add.at(hits, part.out_selection, 1)
            np.testing.assert_array_equal(hits, np.ones(wanted.shape, dtype=np.int32))
            np.testing.assert_array_equal(rebuilt, wanted)
        reader.fail = True
        with pytest.raises(F18ReaderFailure):
            invoke(view.result)
        with pytest.raises(F18ReaderFailure):
            invoke(parts[0].view.result)
        reader.fail = False
        np.testing.assert_array_equal(invoke(view.result).value, expected)


def test_f18_t04():
    """Writes affect exactly the original source's selected coordinates."""
    initial = np.arange(48, dtype=np.int32).reshape(6, 8)
    source = initial.copy()
    expected = initial.copy()
    base = LazyArray(source)
    view = base[::-1, ::2][1:4, 1:]
    values = np.array([[101, 102, 103]], dtype=np.int32)
    invoke(view.write, values)
    expected[::-1, ::2][1:4, 1:] = values
    np.testing.assert_array_equal(source, expected)
    np.testing.assert_array_equal(invoke(view.result).value, expected[::-1, ::2][1:4, 1:])
    base[1:3, 3:5] = -8
    expected[1:3, 3:5] = -8
    base.oindex[[0, 4], [1, 6]] = [[201], [202]]
    expected[np.ix_([0, 4], [1, 6])] = [[201], [202]]
    base.vindex[[5, 1, 3], [7, 0, 5]] = [301, 302, 303]
    expected[[5, 1, 3], [7, 0, 5]] = [301, 302, 303]
    # Repeated destinations receive equal values, leaving conflict order free.
    invoke(base.oindex[[2, 2], [0, 7]].write, 404)
    expected[np.ix_([2, 2], [0, 7])] = 404
    np.testing.assert_array_equal(source, expected)
    np.testing.assert_array_equal(invoke(base.result).value, expected)
    with pytest.raises(ValueError):
        invoke(view.write, np.arange(5))
    # A stored array is a source too, whether or not its writes span objects.
    for options in ({'chunks': (2, 3)}, {'chunks': (2, 2), 'shards': (4, 4)}):
        stored = velnora.create_array({}, data=initial, compressors=None, **options)
        current = initial.copy()
        lazy = LazyArray(stored)
        np.testing.assert_array_equal(invoke(lazy[1:5, 2:7].result).value, current[1:5, 2:7])
        np.testing.assert_array_equal(invoke(lazy.oindex[[5, 0, 5], [7, 1]].result).value,
                                      current[np.ix_([5, 0, 5], [7, 1])])
        np.testing.assert_array_equal(invoke(lazy.vindex[[5, 0, 3], [7, 1, 4]].result).value,
                                      current[[5, 0, 3], [7, 1, 4]])
        lazy[1:5, 2:7] = -3
        current[1:5, 2:7] = -3
        lazy.oindex[[0, 4], [1, 6]] = [[201], [202]]
        current[np.ix_([0, 4], [1, 6])] = [[201], [202]]
        lazy.vindex[[5, 1, 3], [7, 0, 5]] = [301, 302, 303]
        current[[5, 1, 3], [7, 0, 5]] = [301, 302, 303]
        invoke(lazy[::-1, ::2][1:4, 1:].write, np.array([[9, 8, 7]]))
        current[::-1, ::2][1:4, 1:] = np.array([[9, 8, 7]])
        np.testing.assert_array_equal(velnora.open_array(stored.store, mode='r')[:], current)
    readonly = LazyArray(F18Source(initial.copy()))
    np.testing.assert_array_equal(invoke(readonly.result).value, initial)
    with pytest.raises(TypeError):
        invoke(readonly[1:3, 2:5].write, 12)
    np.testing.assert_array_equal(invoke(readonly.result).value, initial)


def test_f18_t05():
    """Result edits do not write back, and later results see current data."""
    source = (np.arange(35).reshape(5, 7) - 12).astype(np.int16)
    initial = source.copy()
    base = LazyArray(source)
    # Both a basic memory-view opportunity and a repeated gather must be owned.
    for view, expected in ((base[1:4, 2:6], initial[1:4, 2:6]),
                           (base.oindex[[4, 0, 4], [6, 1]],
                            initial[np.ix_([4, 0, 4], [6, 1])])):
        result = invoke(view.result).value
        np.testing.assert_array_equal(result, expected)
        result[...] = -999
        np.testing.assert_array_equal(source, initial)
        np.testing.assert_array_equal(invoke(view.result).value, expected)
    view = base[1:4, 2:6]
    old_result = invoke(view.result).value
    source[2, 3] = 777
    current = initial.copy()
    current[2, 3] = 777
    np.testing.assert_array_equal(old_result, initial[1:4, 2:6])
    np.testing.assert_array_equal(invoke(view.result).value, current[1:4, 2:6])
    converted = invoke(np.asarray, view).value
    converted[...] = -555
    np.testing.assert_array_equal(source, current)
