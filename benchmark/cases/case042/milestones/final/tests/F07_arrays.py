# feature: F07
"""Acceptance of array definitions, opening, failures and storage inspection."""
import json
import warnings
import numpy as np
import pytest
import velnora
from velnora.api import asynchronous
from velnora.storage import MemoryStore
from velnora.errors import ArrayNotFoundError, NodeTypeValidationError, VelnoraUserWarning
from _helpers import invoke
from F02_helpers import assert_dtype_meaning
from F03_helpers import put_bytes, listed, read_bytes
from F05_helpers import reopened_values
from F07_helpers import (assert_array_definition, array_properties,
                         array_storage_bytes, array_data_keys)


def test_f07_t01():
    for factory in (velnora.create_array, asynchronous.create_array):
        for version in (2, 3):
            for shape, chunks in (((5, 7), (2, 3)), ((), ()), ((0, 4), (2, 2))):
                store = MemoryStore()
                a = invoke(factory, store, call_kwargs=dict(
                    shape=shape, dtype='int16', chunks=chunks, fill_value=-13,
                    zarr_format=version)).value
                assert_array_definition(a, shape=shape, dtype='int16', chunks=chunks,
                                        fill_value=-13, version=version)
                b = velnora.open_array(store, mode='r')
                assert_array_definition(b, shape=shape, dtype='int16', chunks=chunks,
                                        fill_value=-13, version=version)
                np.testing.assert_array_equal(b[...], np.full(shape, -13, dtype='int16'))
            for changes in ({'shape': (-1, 4)}, {'chunks': (2,)}):
                options = dict(shape=(3, 4), chunks=(2, 2), dtype='int16', zarr_format=version)
                options.update(changes)
                with pytest.raises(ValueError):
                    invoke(factory, MemoryStore(), call_kwargs=options)
            for chunks in ((0, 2), (2, 0), (-2, 2), (1.5, 2)):
                with pytest.raises((TypeError, ValueError)):
                    invoke(factory, MemoryStore(), call_kwargs=dict(
                        shape=(3, 4), chunks=chunks, dtype='int16', zarr_format=version))
            # Full-span selection remains available beside strict explicit sizes.
            a = invoke(factory, MemoryStore(), call_kwargs=dict(
                shape=(3, 4), chunks=(-1, 2), dtype='int16', zarr_format=version)).value
            assert a.chunks == (3, 2)
            np.testing.assert_array_equal(reopened_values(a), np.zeros((3, 4), dtype='int16'))
        a = invoke(factory, MemoryStore(), call_kwargs=dict(
            shape=(3, 4), dtype='float32', dimension_names=('latitude', None),
            zarr_format=3)).value
        assert a.metadata.dimension_names == ('latitude', None)
        assert velnora.open_array(a.store, mode='r').metadata.dimension_names == ('latitude', None)
        with pytest.raises(ValueError):
            invoke(factory, MemoryStore(), call_kwargs=dict(
                shape=(3, 4), dtype='float32', dimension_names=('latitude',), zarr_format=3))


def test_f07_t02():
    data = np.array([[9, -4, 72], [13, 5, -18]], dtype='int32')
    for version in (2, 3):
        for factory in (velnora.create_array, asynchronous.create_array):
            a = invoke(factory, MemoryStore(), call_kwargs=dict(data=data, zarr_format=version)).value
            assert a.shape == data.shape
            assert_dtype_meaning(a.dtype, data.dtype)
            np.testing.assert_array_equal(reopened_values(a), data)
            for conflict in ({'shape': data.shape}, {'dtype': data.dtype}):
                with pytest.raises(ValueError):
                    invoke(factory, MemoryStore(), call_kwargs=dict(data=data, zarr_format=version, **conflict))
            with pytest.raises(ValueError):
                invoke(factory, MemoryStore(), call_kwargs=dict(shape=(2, 3), zarr_format=version))
            a = invoke(factory, MemoryStore(), call_kwargs=dict(shape=(2, 3), dtype='int32',
                       fill_value=17, zarr_format=version)).value
            np.testing.assert_array_equal(reopened_values(a), np.full((2, 3), 17))
        shape_only = velnora.create(shape=(2, 3), store=MemoryStore(), zarr_format=version)
        assert_dtype_meaning(shape_only.dtype, 'float64')
        for factory, options, fill in ((velnora.zeros, {}, 0), (velnora.ones, {}, 1),
                                       (velnora.full, {'fill_value': -23}, -23)):
            a = factory((2, 3), store=MemoryStore(), dtype='int16', zarr_format=version, **options)
            assert a.shape == (2, 3)
            assert_dtype_meaning(a.dtype, 'int16')
            np.testing.assert_array_equal(reopened_values(a), np.full((2, 3), fill))


def test_f07_t03():
    for version in (2, 3):
        store = MemoryStore()
        a = velnora.create_array(store, shape=(3,), dtype='int16', chunks=(2,),
                              fill_value=-9, zarr_format=version)
        a[:] = [4, -12, 33]
        for opener in (velnora.open, velnora.open_array):
            b = opener(store, mode='r')
            assert isinstance(b, velnora.Array)
            assert_array_definition(b, shape=(3,), dtype='int16', chunks=(2,), fill_value=-9, version=version)
            np.testing.assert_array_equal(b[:], [4, -12, 33])
        group_store = MemoryStore()
        velnora.create_group(group_store, zarr_format=version)
        assert isinstance(velnora.open(group_store, mode='r'), velnora.Group)
        with pytest.raises(ArrayNotFoundError if version == 2 else NodeTypeValidationError):
            velnora.open_array(group_store, mode='r')
    # Assemble coexisting formats from separate real creations; no invented documents.
    combined = MemoryStore()
    for version, fill, shape in ((2, 11, (3,)), (3, -7, (4,))):
        a = velnora.create_array(MemoryStore(), shape=shape, dtype='int16', fill_value=fill,
                              zarr_format=version)
        for key, value in array_storage_bytes(a.store).items():
            put_bytes(combined, key, value)
    for opener in (velnora.open, velnora.open_array):
        for version in (None, 2, 3):
            b = opener(combined, mode='r', zarr_format=version)
            selected = 3 if version is None else version
            assert b.metadata.zarr_format == selected
            np.testing.assert_array_equal(b[:], np.full((3,) if selected == 2 else (4,),
                                                       11 if selected == 2 else -7))
    b = invoke(asynchronous.open_array, call_kwargs=dict(store=combined, mode='r', zarr_format=2)).value
    np.testing.assert_array_equal(invoke(b.getitem, slice(None)).value, [11, 11, 11])

    # Start with real, valid stored documents and alter only their chunk sizes.
    # Empty axes, nonempty axes, and inner shard units exercise different
    # compatibility decisions without prescribing warning prose.
    for version, shape, stored_chunks, shards in (
        (2, (0, 5), (0, 0), None),
        (2, (4, 5), (2, 0), None),
        (3, (0, 5), (0, 3), None),
        (3, (4, 5), (0, 0), None),
        (3, (0, 5), (0, 6), (4, 6)),
        (3, (4, 5), (0, 0), (4, 6)),
    ):
        store = MemoryStore()
        velnora.create_array(store, shape=shape, chunks=(2, 3), shards=shards,
                          dtype='int16', fill_value=17, zarr_format=version)
        key = '.zarray' if version == 2 else 'zarr.json'
        document = json.loads(read_bytes(store, key))
        if version == 2:
            document['chunks'] = list(stored_chunks)
        else:
            document['chunk_grid']['configuration']['chunk_shape'] = list(stored_chunks)
        put_bytes(store, key, json.dumps(document).encode())
        units = (1, 1) if shards is None else (2, 3)
        expected = tuple(unit if size == 0 else size
                         for size, unit in zip(stored_chunks, units))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            opened = velnora.open_array(store, mode='r+')
        if any(size == 0 and span > 0 for size, span in zip(stored_chunks, shape)):
            assert any(issubclass(item.category, VelnoraUserWarning) for item in caught)
        assert opened.shape == shape
        assert opened.chunks == (expected if shards is None else (2, 3))
        assert opened.shards == (None if shards is None else expected)
        np.testing.assert_array_equal(opened[:], np.full(shape, 17, dtype='int16'))
        if all(shape):
            values = np.arange(np.prod(shape), dtype='int16').reshape(shape) + 31
            opened[:] = values
            np.testing.assert_array_equal(velnora.open_array(store, mode='r')[:], values)

    for version in (2, 3):
        store = MemoryStore()
        velnora.create_array(store, shape=(4, 5), chunks=(2, 3), dtype='int16', zarr_format=version)
        key = '.zarray' if version == 2 else 'zarr.json'
        original = read_bytes(store, key)
        for invalid in ((-1, 3), (2,)):
            document = json.loads(original)
            if version == 2:
                document['chunks'] = list(invalid)
            else:
                document['chunk_grid']['configuration']['chunk_shape'] = list(invalid)
            put_bytes(store, key, json.dumps(document).encode())
            with pytest.raises(ValueError):
                velnora.open_array(store, mode='r')
    store = MemoryStore()
    velnora.create_array(store, shape=(4, 5), chunks=(2, 3), shards=(4, 6), dtype='int16')
    document = json.loads(read_bytes(store, 'zarr.json'))
    document['chunk_grid']['configuration']['chunk_shape'] = [0, 6]
    sharding = next(codec for codec in document['codecs'] if codec['name'] == 'sharding_indexed')
    sharding['configuration']['chunk_shape'] = [0, 3]
    put_bytes(store, 'zarr.json', json.dumps(document).encode())
    with pytest.raises(ValueError):
        velnora.open_array(store, mode='r')


def test_f07_t04():
    for version in (2, 3):
        missing = MemoryStore()
        with pytest.raises(ArrayNotFoundError):
            velnora.open_array(missing, shape=(3,), dtype='int16', zarr_format=version)
        created = velnora.open_array(missing, mode='a', shape=(3,), dtype='int16',
                                   zarr_format=version)
        created[:] = [19, -4, 73]
        np.testing.assert_array_equal(velnora.open_array(missing, mode='r')[:], [19, -4, 73])
        default_created = velnora.open(MemoryStore(), shape=(2,), dtype='int16', zarr_format=version)
        default_created[:] = [16, -7]
        np.testing.assert_array_equal(reopened_values(default_created), [16, -7])
        for opener in (velnora.open, velnora.open_array):
            with pytest.raises(FileNotFoundError):
                opener(MemoryStore().with_read_only(True))
            for mode in ('r', 'r+'):
                with pytest.raises(FileNotFoundError):
                    opener(MemoryStore(), mode=mode, zarr_format=version)
            for mode in ('a', 'w-'):
                store = MemoryStore()
                options = {} if mode is None else {'mode': mode}
                a = opener(store, shape=(4,), dtype='int16', zarr_format=version, **options)
                a[:] = [8, -2, 19, 31]
                for reuse in ('a', None, 'r', 'r+'):
                    b = opener(store, **({} if reuse is None else {'mode': reuse}))
                    np.testing.assert_array_equal(b[:], [8, -2, 19, 31])
                    assert b.read_only == (reuse == 'r')
                b = opener(store, mode='r+')
                b[1] = 42
                np.testing.assert_array_equal(velnora.open_array(store, mode='r')[:], [8, 42, 19, 31])
                with pytest.raises(FileExistsError):
                    opener(store, mode='w-', shape=(4,), dtype='int16', zarr_format=version)
                ro = opener(store.with_read_only(True))
                assert ro.read_only
                np.testing.assert_array_equal(ro[:], [8, 42, 19, 31])
            store = MemoryStore()
            g = velnora.create_group(store, zarr_format=version)
            g.create_array('old', data=np.array([6, 17], dtype='int16'))
            assert any('old/' in key for key in listed(store.list))
            b = opener(store, mode='w', shape=(2,), dtype='int16', fill_value=-6, zarr_format=version)
            np.testing.assert_array_equal(b[:], [-6, -6])
            assert not any(key.startswith('old/') for key in listed(store.list))
            np.testing.assert_array_equal(velnora.open_array(store, mode='r')[:], [-6, -6])
        # The same access modes on groups; with no array properties a generic
        # open-or-create can only make a group.
        assert isinstance(velnora.open(MemoryStore(), zarr_format=version), velnora.Group)
        for mode in ('r', 'r+'):
            with pytest.raises(FileNotFoundError):
                velnora.open_group(MemoryStore(), mode=mode, zarr_format=version)
        for mode in ('a', 'w-'):
            assert velnora.open_group(MemoryStore(), mode=mode, zarr_format=version).metadata.zarr_format == version
        store = MemoryStore()
        group = velnora.create_group(store, zarr_format=version, attributes={'kept': 1})
        group.create_array('old', data=np.array([6, 17], dtype='int16'))
        assert dict(velnora.open_group(store, mode='a').attrs) == {'kept': 1}
        np.testing.assert_array_equal(velnora.open_group(store, mode='a')['old'][:], [6, 17])
        with pytest.raises(FileExistsError):
            velnora.open_group(store, mode='w-', zarr_format=version)
        assert dict(velnora.open_group(store, mode='r').attrs) == {'kept': 1}
        assert dict(velnora.open_group(store, mode='w', zarr_format=version).attrs) == {}
        assert not any(key.startswith('old/') for key in listed(store.list))


def test_f07_t05():
    for version in (2, 3):
        store = MemoryStore()
        a = velnora.create_array(store, shape=(3,), dtype='int16', zarr_format=version)
        a[:] = [12, -4, 9]
        a.attrs['meaning'] = 'original'
        with pytest.raises(ValueError):
            velnora.create_array(store, name='child', shape=(2,), dtype='int16', zarr_format=version)
        with pytest.raises(ValueError):
            velnora.create_array(store, name='deep/child', shape=(2,), dtype='int16', zarr_format=version)
        with pytest.raises(ValueError):
            velnora.open_group(store, path='child', mode='a', zarr_format=version)
        assert not any(key.startswith(('child/', 'deep/')) for key in listed(store.list))
        with pytest.raises(ArrayNotFoundError):
            velnora.open_array(MemoryStore(), mode='r', zarr_format=version)
        malformed = MemoryStore()
        put_bytes(malformed, '.zarray' if version == 2 else 'zarr.json', b'{broken json')
        with pytest.raises(json.JSONDecodeError):
            velnora.open_array(malformed, mode='r', zarr_format=version)
        before = array_storage_bytes(store)
        ro = velnora.open_array(store, mode='r')
        np.testing.assert_array_equal(ro[:], [12, -4, 9])
        with pytest.raises(ValueError):
            ro[:] = [1, 2, 3]
        with pytest.raises(ValueError):
            ro.attrs['meaning'] = 'changed'
        with pytest.raises(ValueError):
            ro.resize((7,))
        assert array_storage_bytes(store) == before
        b = velnora.open_array(store, mode='r')
        assert b.shape == (3,)
        assert b.attrs['meaning'] == 'original'
        np.testing.assert_array_equal(b[:], [12, -4, 9])


def test_f07_t06():
    for version in (2, 3):
        options = {} if version == 2 else {'serializer': velnora.codecs.BytesCodec(endian='little')}
        a = velnora.create_array(MemoryStore(), shape=(5, 7), chunks=(2, 3), dtype='int32',
                              fill_value=-1, filters=None, compressors=None,
                              zarr_format=version, **options)
        assert_array_definition(a, shape=(5, 7), dtype='int32', chunks=(2, 3), fill_value=-1, version=version)
        properties = array_properties(a)
        assert properties['shards'] is None
        assert properties['filters'] == ()
        assert properties['compressors'] == ()
        if version == 3:
            assert a.serializer.to_dict() == {'name': 'bytes', 'configuration': {'endian': 'little'}}
        assert a.nbytes == 140
        for dtype in ('bool', 'int8', 'float16', 'complex64', 'U3', 'S2', 'M8[s]'):
            sized = velnora.create_array(MemoryStore(), shape=(3, 2), chunks=(3, 2), dtype=dtype, zarr_format=version)
            assert sized.nbytes == 6 * np.dtype(dtype).itemsize
        assert a.nchunks == 9
        assert a.nchunks_initialized == 0
        assert array_data_keys(a.store, version) == set()
        assert a.nbytes_stored() == sum(len(value) for value in array_storage_bytes(a.store).values())
        expected = np.full((5, 7), -1, dtype='int32')
        for selection, value, initialized in (((slice(0, 2), slice(0, 3)), 37, 1),
                                             ((slice(4, 5), slice(6, 7)), -29, 2)):
            a[selection] = value
            expected[selection] = value
            b = velnora.open_array(a.store, mode='r')
            assert b.nchunks == 9
            assert b.nchunks_initialized == initialized
            assert len(array_data_keys(b.store, version)) == initialized
            assert b.nbytes == 140
            assert b.nbytes_stored() == sum(len(v) for v in array_storage_bytes(b.store).values())
            np.testing.assert_array_equal(b[:], expected)


def test_f07_t07():
    for version in (2, 3):
        a = velnora.create_array(MemoryStore(), shape=(13, 17), dtype='int16', zarr_format=version)
        chosen = a.chunks
        assert len(chosen) == 2
        assert all(isinstance(n, int) and n > 0 for n in chosen)
        b = velnora.open_array(a.store, mode='r')
        assert b.chunks == chosen
        np.testing.assert_array_equal(b[:], np.zeros((13, 17), dtype='int16'))
        for dtype in ('int16', 'float32', 'bool'):
            for explicit in (False, True):
                options = {'fill_value': None} if explicit else {}
                a = velnora.create_array(MemoryStore(), shape=(3,), dtype=dtype, zarr_format=version, **options)
                b = velnora.open_array(a.store, mode='r')
                if explicit and version == 2:
                    assert a.fill_value is None
                    assert b.fill_value is None
                    assert json.loads(read_bytes(a.store, '.zarray'))['fill_value'] is None
                else:
                    assert a.fill_value == np.zeros((), dtype=dtype)[()]
                    assert b.fill_value == a.fill_value
                    np.testing.assert_array_equal(b[:], np.zeros((3,), dtype=dtype))
        a = velnora.create(store=MemoryStore(), shape=(13, 17), dtype='int16', chunks=False,
                        zarr_format=version)
        assert a.chunks == (13, 17)
        assert velnora.open_array(a.store, mode='r').chunks == (13, 17)
