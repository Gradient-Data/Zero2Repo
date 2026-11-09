# feature: F08
"""Acceptance of public array selections, assignments and configured views."""
from pathlib import Path
import json
import warnings

import numpy as np
import pytest
import velnora
from velnora.buffer import cpu
from velnora.errors import ChunkNotFoundError, VelnoraUserWarning

from F05_helpers import reopened_values
from F03_helpers import put_bytes, read_bytes
from F07_helpers import array_data_keys, array_storage_bytes
from F08_helpers import selection_array, legacy_selection_store
from _helpers import run_python


def test_f08_t01():
    a, expected = selection_array()
    selections = [(0, 0), (4, 6), (-5, -7), (0,), (Ellipsis, 0),
                  (-1, slice(None)), (2,), (Ellipsis, -2),
                  (slice(-20, 20, 2), slice(1, 30, 3)),
                  (slice(3, 1), slice(None)), (1, 4)]
    for selection in selections:
        for actual in (a[selection], a.get_basic_selection(selection)):
            assert np.shape(actual) == np.shape(expected[selection])
            np.testing.assert_array_equal(actual, expected[selection])
    for selection, value in [((-1, Ellipsis), 19),
                             ((slice(-20, 20, 2), slice(1, 30, 3)), -27),
                             ((1,), np.arange(7))]:
        a[selection] = value
        expected[selection] = value
        np.testing.assert_array_equal(reopened_values(a), expected)
    for selection, error in [((5, 0), IndexError), ((-6, 0), IndexError),
                             ((0, 0, 0), IndexError),
                             ((Ellipsis, Ellipsis), IndexError),
                             ((slice(None, None, 0),), ValueError),
                             ((slice(None, None, -1),), IndexError)]:
        with pytest.raises(error):
            a.get_basic_selection(selection)
        with pytest.raises(error):
            a[selection] = 7


def test_f08_t02():
    a, expected = selection_array()
    rows, cols = np.array([3, 1, 3, 4]), np.array([5, 0, 2])
    outer = np.ix_(rows, cols)
    np.testing.assert_array_equal(a.oindex[rows, cols], expected[outer])
    np.testing.assert_array_equal(a.get_orthogonal_selection((rows, cols)), expected[outer])
    mask = np.array([True, False, False, True, True])
    np.testing.assert_array_equal(a.oindex[mask, 1:7:2], expected[mask, 1:7:2])
    np.testing.assert_array_equal(a.oindex[4, cols], expected[4, cols])
    a.set_orthogonal_selection((rows, cols), -8)
    expected[outer] = -8
    a.oindex[mask, 1:7:2] = 29
    expected[np.ix_(np.flatnonzero(mask), np.array([1, 3, 5]))] = 29
    np.testing.assert_array_equal(reopened_values(a), expected)
    for selection in [(np.ones(4, dtype=bool), slice(None)),
                      (np.array([[0, 1]]), slice(None)),
                      ([5], [1]), ([-6], [1])]:
        with pytest.raises(IndexError):
            a.get_orthogonal_selection(selection)
        with pytest.raises(IndexError):
            a.set_orthogonal_selection(selection, 4)


def test_f08_t03():
    a, expected = selection_array()
    coordinates = (np.array([[4], [1]]), np.array([[6, 0, 2]]))
    np.testing.assert_array_equal(a.get_coordinate_selection(coordinates), expected[coordinates])
    np.testing.assert_array_equal(a.vindex[coordinates], expected[coordinates])
    repeated = (np.array([3, 1, 3, 4]), np.array([2, 6, 2, 0]))
    np.testing.assert_array_equal(a.vindex[repeated], expected[repeated])
    # Writes have no conflicting values at repeated destinations.
    a.set_coordinate_selection(coordinates, np.array([[11, 12, 13], [21, 22, 23]]))
    expected[coordinates] = [[11, 12, 13], [21, 22, 23]]
    a.vindex[repeated] = -17
    expected[repeated] = -17
    np.testing.assert_array_equal(reopened_values(a), expected)
    for selection, error in [(([0, 1], [0, 1, 2]), ValueError),
                             (([5], [0]), IndexError), (([0], [-8]), IndexError)]:
        with pytest.raises(error):
            a.get_coordinate_selection(selection)
        with pytest.raises(error):
            a.set_coordinate_selection(selection, 8)


def test_f08_t04():
    a, expected = selection_array()
    mask = (expected % 4 == 0)
    selected = a.get_mask_selection(mask)
    assert np.shape(selected) == (np.count_nonzero(mask),)
    np.testing.assert_array_equal(selected, expected[mask])
    np.testing.assert_array_equal(a.vindex[mask], expected[mask])
    values = np.arange(np.count_nonzero(mask), dtype='int32') + 70
    a.set_mask_selection(mask, values)
    expected[mask] = values
    np.testing.assert_array_equal(reopened_values(a), expected)
    empty = np.zeros(expected.shape, dtype=bool)
    selected_empty = a.get_mask_selection(empty)
    assert np.shape(selected_empty) == (0,)
    np.testing.assert_array_equal(selected_empty, np.array([], dtype='int32'))
    with pytest.raises(IndexError):
        a.get_mask_selection(np.ones((5, 6), dtype=bool))
    with pytest.raises(IndexError):
        a.set_mask_selection(np.ones((5, 6), dtype=bool), 3)


def test_f08_t05():
    a, expected = selection_array()
    for blocks, region in [((1, 0), (slice(2, 4), slice(0, 3))),
                           ((slice(1, 8), slice(1, 9)), (slice(2, 5), slice(3, 7))),
                           ((2, 2), (slice(4, 5), slice(6, 7)))]:
        np.testing.assert_array_equal(a.blocks[blocks], expected[region])
        np.testing.assert_array_equal(a.get_block_selection(blocks), expected[region])
    a.blocks[1, 0] = -33
    expected[2:4, 0:3] = -33
    a.set_block_selection((slice(1, 8), slice(1, 9)), 54)
    expected[2:5, 3:7] = 54
    np.testing.assert_array_equal(reopened_values(a), expected)


def test_f08_t06():
    a, expected = selection_array()
    for selection, value in [((slice(1, 4), slice(2, 6)), 6.75),
                             ((slice(None), slice(1, 7, 2)), np.arange(15).reshape(5, 3) + 0.75)]:
        a[selection] = value
        expected[selection] = value
        np.testing.assert_array_equal(reopened_values(a), expected)
    with pytest.raises(ValueError):
        a[1:4, 2:6] = np.ones((2, 3))
    # Singleton broadcasting is exercised within one chunk at matching rank.
    b = velnora.create_array({}, data=expected, chunks=expected.shape, compressors=None)
    for selection, value in [((slice(1, 4), slice(2, 6)), np.array([[-4.5, 9.5, 12.5, 15.5]])),
                             ((slice(1, 5), slice(0, 2)), np.array([[7], [8], [9], [10]]))]:
        b[selection] = value
        expected[selection] = value
        np.testing.assert_array_equal(reopened_values(b), expected)

    with pytest.raises(ValueError):
        a.set_coordinate_selection(([0, 1, 4], [1, 3, 6]), [8, 9])

    # Each history starts with a separate legacy store. Metadata changes and
    # element writes are sequential; no atomic cross-writer guarantee is assumed.
    for version, inner in ((2, None), (3, None), (3, 2)):
        store, key = legacy_selection_store(version, inner=inner)
        with pytest.warns(VelnoraUserWarning):
            legacy = velnora.open_array(store, mode='r+')
        values = np.array([11, -7, 24, 19, -3, 6], dtype='int16')
        legacy[:] = values
        document = json.loads(read_bytes(store, key))
        extents = (document['chunks'] if version == 2 else
                   document['chunk_grid']['configuration']['chunk_shape'])
        assert all(extent > 0 for extent in extents)
        with warnings.catch_warnings():
            warnings.simplefilter('error', VelnoraUserWarning)
            reopened = velnora.open_array(store, mode='r')
            np.testing.assert_array_equal(reopened[:], values)

        # A newer compatible document must survive a stale handle's first write.
        store, key = legacy_selection_store(version, inner=inner)
        with pytest.warns(VelnoraUserWarning):
            stale = velnora.open_array(store, mode='r+')
        with pytest.warns(VelnoraUserWarning):
            other = velnora.open_array(store, mode='r+')
        other.append(np.array([31, 42], dtype='int16'))
        other.attrs['units'] = 'seconds'
        stale[1] = -18
        with warnings.catch_warnings():
            warnings.simplefilter('error', VelnoraUserWarning)
            reopened = velnora.open_array(store, mode='r')
            assert reopened.shape == (8,)
            assert reopened.attrs.asdict() == {'units': 'seconds'}
            np.testing.assert_array_equal(reopened[:], [0, -18, 0, 0, 0, 0, 31, 42])

        # The same stale write must refuse a changed chunk or inner-shard layout.
        store, key = legacy_selection_store(version, inner=inner)
        with pytest.warns(VelnoraUserWarning):
            stale = velnora.open_array(store, mode='r+')
        document = json.loads(read_bytes(store, key))
        if inner:
            document['chunk_grid']['configuration']['chunk_shape'] = [2]
            document['codecs'][0]['configuration']['chunk_shape'] = [1]
        elif version == 2:
            document['chunks'] = [3]
        else:
            document['chunk_grid']['configuration']['chunk_shape'] = [3]
        put_bytes(store, key, json.dumps(document).encode())
        before = array_storage_bytes(store)
        with pytest.raises(ValueError):
            stale[:3] = [7, 8, 9]
        assert array_storage_bytes(store) == before


def test_f08_t07():
    for version in (2, 3):
        a = velnora.create_array({}, shape=(4, 6), chunks=(2, 3), dtype='int32',
                              fill_value=-13, zarr_format=version)
        np.testing.assert_array_equal(a[:], np.full((4, 6), -13))
        strict = a.with_config({'read_missing_chunks': False})
        with pytest.raises(ChunkNotFoundError):
            strict[0:2, 0:3]
        a[0:2, 0:3] = 27
        assert len(array_data_keys(a.store, version)) == 1
        np.testing.assert_array_equal(strict[0:2, 0:3], np.full((2, 3), 27))
        a[0:2, 0:3] = -13
        assert array_data_keys(a.store, version) == set()
        with pytest.raises(ChunkNotFoundError):
            strict[0:2, 0:3]
        retained = a.with_config({'write_empty_chunks': True})
        retained[0:2, 0:3] = -13
        assert len(array_data_keys(a.store, version)) == 1
        np.testing.assert_array_equal(strict[0:2, 0:3], np.full((2, 3), -13))
        np.testing.assert_array_equal(a[:], np.full((4, 6), -13))


def test_f08_t08():
    a, expected = selection_array()
    for method, selection, values in [
        (a.get_basic_selection, (slice(1, 5, 2), slice(0, 6, 2)), expected[1:5:2, 0:6:2]),
        (a.get_orthogonal_selection, ([3, 0], [6, 2]), expected[np.ix_([3, 0], [6, 2])]),
        (a.get_coordinate_selection, ([4, 0, 2], [1, 3, 5]), expected[[4, 0, 2], [1, 3, 5]]),
        (a.get_mask_selection, expected < -10, expected[expected < -10]),
        (a.get_block_selection, (1, 0), expected[2:4, :3])]:
        destination = np.full(values.shape, 12345, dtype='float64')
        out = cpu.NDBuffer.from_numpy_array(destination)
        result = method(selection, out=out)
        np.testing.assert_array_equal(destination, values)
        np.testing.assert_array_equal(result, values)
        with pytest.raises(ValueError):
            method(selection, out=cpu.NDBuffer.from_numpy_array(np.empty((1,), dtype='int32')))
    np.testing.assert_array_equal(np.asarray(a), expected)


def test_f08_t09(tmp_path):
    # Bound the complete threaded workload, including executor shutdown.
    source = '''
import sys
import numpy as np
import velnora
from velnora.storage import LocalStore
from F08_helpers import concurrent_calls
store = LocalStore(sys.argv[1])
expected = np.arange(72, dtype='int32').reshape(8, 9) - 15
a = velnora.create_array(store, data=expected, chunks=(2, 3), compressors=None)
readers = [velnora.open_array(store, mode='r') for _ in range(3)]
for actual in concurrent_calls([lambda r=r: r[:] for r in readers]):
    np.testing.assert_array_equal(actual, expected)
writers = [velnora.open_array(store, mode='r+') for _ in range(3)]
selections = [(slice(0, 2), slice(0, 3)), (slice(2, 4), slice(3, 6)),
              (slice(6, 8), slice(6, 9))]
calls = []
for i, (writer, selection) in enumerate(zip(writers, selections)):
    value = np.arange(6, dtype='int32').reshape(2, 3) + 100 * (i + 1)
    expected[selection] = value
    calls.append(lambda w=writer, s=selection, v=value: w.set_basic_selection(s, v))
concurrent_calls(calls)
np.testing.assert_array_equal(velnora.open_array(store, mode='r')[:], expected)
'''
    result = run_python(source, [str(tmp_path / 'concurrent')],
                        cwd=Path(__file__).parent, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_f08_t11():
    a, expected = selection_array()
    assert a[:].flags.c_contiguous
    np.testing.assert_array_equal(a[:], expected)
    with velnora.config.set({'array.order': 'F', 'array.write_empty_chunks': True,
                          'array.read_missing_chunks': False}):
        inherited = velnora.create_array({}, shape=(4, 6), chunks=(2, 3), dtype='int32', fill_value=-9)
        with pytest.raises(ChunkNotFoundError):
            inherited[:]
        inherited[:] = -9
        assert len(array_data_keys(inherited.store, 3)) == 4
        assert inherited[:].flags.f_contiguous
        np.testing.assert_array_equal(inherited[:], np.full((4, 6), -9))
        overridden = velnora.create_array({}, shape=(4, 6), chunks=(2, 3), dtype='int32',
                                       fill_value=-9, config={'order': 'C', 'write_empty_chunks': False,
                                                              'read_missing_chunks': True})
        assert overridden[:].flags.c_contiguous
        np.testing.assert_array_equal(overridden[:], np.full((4, 6), -9))
        overridden[:] = -9
        assert array_data_keys(overridden.store, 3) == set()
        opened = velnora.open_array(a.store)
        assert opened[:].flags.f_contiguous
        np.testing.assert_array_equal(opened[:], expected)
        opened = opened.with_config({'order': 'C'})
        assert opened[:].flags.c_contiguous
        opened[:] = 0
        assert len(array_data_keys(opened.store, 3)) == 9
        view = opened.with_config({'order': 'F'})
        assert view[:].flags.f_contiguous
        np.testing.assert_array_equal(view[:], np.zeros(expected.shape))
        # Global changes must not replace unspecified options of an existing view.
        with velnora.config.set({'array.order': 'C', 'array.write_empty_chunks': False,
                              'array.read_missing_chunks': True}):
            view[:] = 0
            assert len(array_data_keys(view.store, 3)) == 9
            view[1, 2] = 91
            expected.fill(0)
            expected[1, 2] = 91
            np.testing.assert_array_equal(opened[:], expected)
            np.testing.assert_array_equal(reopened_values(a), expected)
            # An inherited strict read observes external removal, while the default view fills it.
            sparse = velnora.create_array({}, shape=(4, 6), chunks=(2, 3), dtype='int32', fill_value=-7,
                                       config={'read_missing_chunks': False, 'write_empty_chunks': True})
            sparse_view = sparse.with_config({'order': 'F'})
            sparse_view[:] = -7
            assert len(array_data_keys(sparse.store, 3)) == 4
            sparse.with_config({'write_empty_chunks': False})[:] = -7
            with pytest.raises(ChunkNotFoundError):
                sparse_view[:]
            filled_view = sparse_view.with_config({'read_missing_chunks': True, 'write_empty_chunks': False})
            assert filled_view[:].flags.f_contiguous
            np.testing.assert_array_equal(filled_view[:], np.full((4, 6), -7))
    for operation in [lambda: velnora.create_array({}, shape=(2,), dtype='int32', config={'unknown_choice': True}),
                      lambda: a.with_config({'unknown_choice': True})]:
        with pytest.raises(TypeError):
            operation()
