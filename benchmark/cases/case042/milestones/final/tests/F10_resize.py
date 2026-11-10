# feature: F10
"""Acceptance of resizing, retained storage regions and axis appends."""
import numpy as np
import pytest
import velnora
from velnora.api import asynchronous
from velnora.storage import ZipStore

from _helpers import invoke
from F05_helpers import reopened_values
from F07_helpers import array_data_keys


def test_f10_t01():
    data = np.arange(35, dtype='int32').reshape(5, 7) * 9 - 83
    for version in (2, 3):
        a = velnora.create_array({}, data=data, chunks=(2, 3), fill_value=-19,
                              zarr_format=version, compressors=None)
        a.resize((8, 9))
        expected = np.full((8, 9), -19, dtype='int32')
        expected[:5, :7] = data
        assert a.shape == (8, 9)
        b = velnora.open_array(a.store, mode='r+')
        assert b.shape == (8, 9)
        np.testing.assert_array_equal(b[:], expected)
        b.resize((3, 4))
        assert velnora.open_array(a.store).shape == (3, 4)
        np.testing.assert_array_equal(reopened_values(b), data[:3, :4])
        for bad in ((12,), (3, 4, 1), (-1, 4)):
            with pytest.raises(ValueError):
                b.resize(bad)
        b.resize((0, 4))
        assert velnora.open_array(a.store).shape == (0, 4)
        np.testing.assert_array_equal(reopened_values(b), np.empty((0, 4), dtype='int32'))


def test_f10_t02():
    data = np.arange(12, dtype='int32') * 11 + 7
    # Each row isolates an object unit or a retention choice; no encoding-byte oracle.
    for chunks, shards, preserve, retained, object_count in (
        ((2,), None, False, 4, 2),
        ((2,), (6,), False, 6, 1),
        ((2,), None, True, 12, 6),
        ((2,), (6,), True, 12, 2),
    ):
        a = velnora.create_array({}, data=data, chunks=chunks, shards=shards,
                              fill_value=-29, compressors=None)
        before = array_data_keys(a.store, 3)
        assert len(before) == (6 if shards is None else 2)
        async_array = invoke(asynchronous.open_array, call_kwargs=dict(store=a.store, mode='r+')).value
        kwargs = {'delete_outside_chunks': False} if preserve else {}
        invoke(async_array.resize, (3,), call_kwargs=kwargs)
        after = array_data_keys(a.store, 3)
        assert len(after) == object_count
        assert after <= before
        np.testing.assert_array_equal(reopened_values(a), data[:3])
        # A real write inside a surviving object must also preserve its hidden cells.
        b = velnora.open_array(a.store, mode='r+')
        b[1] = -101
        b.resize((12,))
        expected = np.full(12, -29, dtype='int32')
        expected[:retained] = data[:retained]
        expected[1] = -101
        np.testing.assert_array_equal(reopened_values(b), expected)
    # Any axis can put a chunk outside: it survives only if inside on every axis.
    table = np.arange(24, dtype='int32').reshape(4, 6)
    for version, key in ((3, 'c/{}/{}'), (2, '{}.{}')):
        for new_shape in ((3, 2), (1, 6), (1, 2), (2, 3)):
            a = velnora.create_array({}, data=table, chunks=(2, 3), fill_value=-1,
                                  zarr_format=version, compressors=None)
            a.resize(new_shape)
            assert array_data_keys(a.store, version) == {
                key.format(i, j) for i in range(2) for j in range(2)
                if i * 2 < new_shape[0] and j * 3 < new_shape[1]}
            np.testing.assert_array_equal(reopened_values(a), table[:new_shape[0], :new_shape[1]])


def test_f10_t03():
    initial = np.arange(15, dtype='int32').reshape(3, 5) * 3 - 61
    for version in (2, 3):
        a = velnora.create_array({}, data=initial, chunks=(2, 3),
                              zarr_format=version, compressors=None)
        rows = np.arange(10, dtype='int32').reshape(2, 5) + 201
        assert a.append(rows) == (5, 5)
        expected = np.concatenate((initial, rows), axis=0)
        np.testing.assert_array_equal(reopened_values(a), expected)
        columns = np.arange(10, dtype='int32').reshape(5, 2) - 301
        assert a.append(columns, axis=1) == (5, 7)
        expected = np.concatenate((expected, columns), axis=1)
        assert velnora.open_array(a.store).shape == expected.shape
        np.testing.assert_array_equal(reopened_values(a), expected)
        for bad, axis in ((np.ones((2, 6), dtype='int32'), 0),
                          (np.ones((4, 2), dtype='int32'), 1),
                          (np.ones(7, dtype='int32'), 0),
                          (np.ones((2, 7, 1), dtype='int32'), 0)):
            with pytest.raises(ValueError):
                a.append(bad, axis=axis)


def test_f10_t04():
    with velnora.config.set({'array.rectilinear_chunks': True}):
        data = np.arange(10, dtype='int32') * 7 - 31
        a = velnora.create_array({}, data=data, chunks=([2, 5, 3],),
                              fill_value=-43, compressors=None)
        assert a.read_chunk_sizes == ((2, 5, 3),)
        a.resize((4,))
        b = velnora.open_array(a.store, mode='r+')
        assert b.read_chunk_sizes == ((2, 2),)
        np.testing.assert_array_equal(b[:], data[:4])
        b.resize((9,))
        b = velnora.open_array(a.store, mode='r+')
        assert b.read_chunk_sizes == ((2, 5, 2),)
        expected = np.full(9, -43, dtype='int32')
        expected[:7] = data[:7]
        np.testing.assert_array_equal(b[:], expected)
        b.resize((13,))
        b = velnora.open_array(a.store, mode='r+')
        assert b.read_chunk_sizes == ((2, 5, 3, 3),)
        expected = np.concatenate((expected, np.full(4, -43, dtype='int32')))
        np.testing.assert_array_equal(b[:], expected)
        tail = np.array([109, -208], dtype='int32')
        assert b.append(tail) == (15,)
        b = velnora.open_array(a.store, mode='r+')
        assert b.read_chunk_sizes == ((2, 5, 3, 3, 2),)
        np.testing.assert_array_equal(b[:], np.concatenate((expected, tail)))
        # An append inside declared coverage must reuse, rather than subdivide, it.
        c = velnora.create_array({}, data=data, chunks=([2, 5, 3],), compressors=None)
        c.resize((4,))
        assert c.append(tail) == (6,)
        c = velnora.open_array(c.store)
        assert c.read_chunk_sizes == ((2, 4),)
        np.testing.assert_array_equal(c[:], np.concatenate((data[:4], tail)))


def test_f10_t05(tmp_path):
    data = np.arange(12, dtype='int32') * 13 + 17
    for version in (2, 3):
        path = tmp_path / f'resize-{version}.zip'
        with ZipStore(path, mode='w') as store:
            a = velnora.create_array(store, data=data, chunks=(4,),
                                  zarr_format=version, fill_value=-59, compressors=None)
            np.testing.assert_array_equal(a[:], data)
            with pytest.raises(NotImplementedError):
                a.resize((4,))
            assert a.shape == (12,)
        with ZipStore(path, mode='r') as store:
            b = velnora.open_array(store, mode='r')
            assert b.shape == (12,)
            np.testing.assert_array_equal(b[:], data)
        with ZipStore(path, mode='a') as store:
            b = velnora.open_array(store, mode='r+')
            b.resize((10,))
        with ZipStore(path, mode='a') as store:
            b = velnora.open_array(store, mode='r+')
            assert b.shape == (10,)
            np.testing.assert_array_equal(b[:], data[:10])
            b.resize((15,))
        with ZipStore(path, mode='r') as store:
            b = velnora.open_array(store, mode='r')
            assert b.shape == (15,)
            np.testing.assert_array_equal(b[:], np.concatenate((data, np.full(3, -59, dtype='int32'))))
