# feature: F09
"""Acceptance observations for sharded and variable-boundary arrays."""
import numpy as np
import pytest
import velnora

from velnora.codecs import GzipCodec

from F03_helpers import SQLiteStore, read_bytes, put_bytes
from F07_helpers import array_data_keys
from F08_helpers import concurrent_calls
from velnora.errors import ChunkNotFoundError
from velnora.core.metadata.v3 import RectilinearChunksDisabledError


def test_f09_t01(tmp_path):
    data = np.arange(99, dtype='int32').reshape(9, 11) * 7 - 31
    patch = np.arange(42, dtype='int32').reshape(6, 7) - 301
    custom = SQLiteStore(tmp_path / 'shards.sqlite')
    try:
        # Encoded inner chunks, and a store of the caller's own.
        for store, shards, compressors in (({}, (4, 6), None), ({}, (4, 6), GzipCodec(level=2)),
                                           (custom, (4, 6), GzipCodec(level=2))):
            a = velnora.create_array(store, data=data, chunks=(2, 3), shards=shards, compressors=compressors)
            expected = data.copy()
            a[1:7, 2:9] = patch
            expected[1:7, 2:9] = patch
            np.testing.assert_array_equal(a[1:8, 1:10], expected[1:8, 1:10])
            np.testing.assert_array_equal(velnora.open_array(a.store, mode='r')[:], expected)
            assert a.chunks == (2, 3)
            assert a.shards == (4, 6)
    finally:
        custom.close()
    for outer in ((5, 6), (4, 7)):
        with pytest.raises(ValueError):
            velnora.create_array({}, shape=data.shape, dtype='int32', chunks=(2, 3), shards=outer)


def test_f09_t02():
    a = velnora.create_array({}, shape=(12, 8), dtype='int32', chunks=(2, 2),
                          shards=(4, 4), fill_value=-17, compressors=None)
    expected = np.full((12, 8), -17, dtype='int32')
    # Three occupied inner chunks, two occupied shards.
    for region, value in (((slice(0, 2), slice(0, 2)), 43),
                          ((slice(2, 4), slice(2, 4)), 91),
                          ((slice(8, 10), slice(4, 6)), -62)):
        a[region] = value
        expected[region] = value
    assert len(array_data_keys(a.store, 3)) == 2
    np.testing.assert_array_equal(velnora.open_array(a.store)[:], expected)
    with velnora.config.set({'array.read_missing_chunks': False}):
        reopened = velnora.open_array(a.store, mode='r')
        assert reopened.chunks == (2, 2)
        assert reopened.shards == (4, 4)
        np.testing.assert_array_equal(reopened[:4, :4], expected[:4, :4])
        np.testing.assert_array_equal(reopened[8:12, 4:8], expected[8:12, 4:8])
        with pytest.raises(ChunkNotFoundError):
            reopened[4:8, :4]


def test_f09_t03():
    data = np.arange(8, dtype='int32') + 23
    a = velnora.create_array({}, data=data, chunks=(2,),
                          shards={'shape': (8,), 'index_location': 'end'}, compressors=None)
    np.testing.assert_array_equal(a[:], data)
    keys = array_data_keys(a.store, 3)
    assert len(keys) == 1
    key, = keys
    original = read_bytes(a.store, key)
    # The explicitly selected end index ends with its CRC32C checksum.
    damaged = original[:-1] + bytes([original[-1] ^ 1])
    index_body = original[:-5] + bytes([original[-5] ^ 1]) + original[-4:]
    for payload in (damaged, index_body, original[:3], original[:-8], b''):
        put_bytes(a.store, key, payload)
        with pytest.raises(ValueError):
            velnora.open_array(a.store, mode='r')[1:3]
        put_bytes(a.store, key, original)
        np.testing.assert_array_equal(velnora.open_array(a.store, mode='r')[:], data)


def test_f09_t04():
    # Disabled unless enabled, with nothing configured at all.
    with pytest.raises(RectilinearChunksDisabledError):
        velnora.create_array({}, shape=(7,), dtype='int32', chunks=([2, 5],))
    with velnora.config.set({'array.rectilinear_chunks': True}):
        data = np.arange(63, dtype='int32').reshape(7, 9) - 41
        a = velnora.create_array({}, data=data, chunks=([2, 1, 4], [4, 2, 3]), compressors=None)
        a.resize((6, 8))
        expected = data[:6, :8].copy()
        patch = np.arange(24, dtype='int32').reshape(4, 6) + 201
        a[1:5, 1:7] = patch
        expected[1:5, 1:7] = patch
        reopened = velnora.open_array(a.store, mode='r')
        np.testing.assert_array_equal(reopened[:], expected)
        np.testing.assert_array_equal(reopened[1:6, 3:8], expected[1:6, 3:8])
        assert reopened.read_chunk_sizes == ((2, 1, 3), (4, 2, 2))
        with pytest.raises(NotImplementedError):
            _ = reopened.chunks
        for bad in (([], [9]), ([0, 7], [9]), ([-1, 8], [9]), ([2, 3], [9]), ([7],)):
            with pytest.raises(ValueError):
                velnora.create_array({}, shape=(7, 9), dtype='int32', chunks=bad)
    with velnora.config.set({'array.rectilinear_chunks': False}):
        with pytest.raises(RectilinearChunksDisabledError):
            velnora.create_array({}, shape=(7,), dtype='int32', chunks=([2, 5],))
        with pytest.raises(RectilinearChunksDisabledError):
            velnora.open_array(a.store)


def test_f09_t05():
    with velnora.config.set({'array.rectilinear_chunks': True}):
        data = np.arange(120, dtype='int32').reshape(12, 10) * 5 - 27
        a = velnora.create_array({}, data=data, chunks=(2, 2), shards=([4, 8], [6, 4]), compressors=None)
        expected = data.copy()
        a[3:9, 3:8] = -81
        expected[3:9, 3:8] = -81
        reopened = velnora.open_array(a.store, mode='r')
        np.testing.assert_array_equal(reopened[:], expected)
        np.testing.assert_array_equal(reopened[2:10, 4:9], expected[2:10, 4:9])
        assert reopened.chunks == (2, 2)
        assert len(array_data_keys(a.store, 3)) == 4
        with pytest.raises(ValueError):
            velnora.create_array({}, shape=(12, 10), dtype='int32', chunks=(2, 2), shards=([5, 7], [6, 4]))
        with pytest.raises(ValueError):
            velnora.create_array({}, shape=(12, 10), dtype='int32', chunks=([4, 8], [6, 4]), shards=(12, 10))
        empty = velnora.create_array({}, shape=(0,), chunks=([2, 5, 3],), dtype='int32', compressors=None)
        empty = velnora.open_array(empty.store, mode='r+')
        empty.resize((8,))
        values = np.arange(8, dtype='int32') * 13 - 4
        empty[:] = values
        grown = velnora.open_array(empty.store, mode='r')
        np.testing.assert_array_equal(grown[:], values)
        assert grown.read_chunk_sizes == ((2, 5, 1),)


def test_f09_t06(tmp_path):
    data = np.arange(192, dtype='int32').reshape(16, 12) - 73
    path = tmp_path / 'shards'
    a = velnora.create_array(path, data=data, chunks=(2, 2), shards=(4, 6), compressors=None)
    handles = [velnora.open_array(path, mode='r+') for _ in range(3)]
    regions = [(slice(1, 4), slice(1, 5)), (slice(5, 8), slice(7, 11)),
               (slice(12, 15), slice(2, 5))]
    patches = [np.full(data[r].shape, 101 + i * 37, dtype='int32') for i, r in enumerate(regions)]
    concurrent_calls([lambda h=h, r=r, p=p: h.__setitem__(r, p)
                      for h, r, p in zip(handles, regions, patches)])
    expected = data.copy()
    for region, patch in zip(regions, patches):
        expected[region] = patch
    np.testing.assert_array_equal(velnora.open_array(a.store, mode='r')[:], expected)
