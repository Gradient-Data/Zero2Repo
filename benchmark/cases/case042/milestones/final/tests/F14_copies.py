# feature: F14
"""Acceptance checks for array-source creation and native-array saving."""
import numpy as np
import pytest
import velnora
from velnora.codecs import BytesCodec, GzipCodec, TransposeCodec
from velnora.errors import ContainsArrayError
from velnora.storage import LocalStore, MemoryStore

from F07_helpers import array_properties
from F14_helpers import assert_copy_choices, assert_saved_members, assert_saved_values


def test_f14_t01(tmp_path):
    native = (np.arange(48, dtype='int32').reshape(6, 8) * 9 - 71)
    for index, data in enumerate((native, [[13, -8, 24], [5, 17, -9]], 37)):
        destination = tmp_path / f'native-{index}'
        velnora.from_array(destination, data=data)
        assert_saved_values(velnora.open_array(destination, mode='r'), np.asarray(data))
    for version in (2, 3):
        options = dict(chunks=(2, 2), fill_value=-43, zarr_format=version,
                       attributes={'units': 'm', 'nested': {'runs': [2, 7]}})
        if version == 3:
            options.update(shards=(4, 4), filters=[TransposeCodec(order=(1, 0))],
                           serializer=BytesCodec(endian='big'), compressors=[GzipCodec(level=2)],
                           dimension_names=('row', 'sample'))
        else:
            from numcodecs import Zlib
            options.update(compressors=Zlib(level=3))
        source = velnora.create_array({}, data=native, **options)
        destination = tmp_path / f'keep-{version}'
        velnora.from_array(destination, data=source)
        copied = velnora.open_array(destination, mode='r')
        assert_saved_values(copied, native)
        assert_copy_choices(copied, source)
        destination = tmp_path / f'convert-{version}'
        overrides = dict(zarr_format=3, chunks=(3, 4), shards=None,
                         filters=[], serializer=BytesCodec(endian='little'),
                         compressors=None, fill_value=29, dimension_names=('x', 'y'),
                         attributes={'replacement': True})
        velnora.from_array(destination, data=source, **overrides)
        converted = velnora.open_array(destination, mode='r')
        assert_saved_values(converted, native)
        chosen = array_properties(converted)
        assert chosen['zarr_format'] == 3
        assert chosen['chunks'] == (3, 4)
        assert chosen['shards'] is None
        assert chosen['filters'] == ()
        assert chosen['serializer'].to_dict() == BytesCodec(endian='little').to_dict()
        assert chosen['compressors'] == ()
        assert chosen['fill_value'] == 29
        assert chosen['dimension_names'] == ('x', 'y')
        assert dict(converted.attrs) == {'replacement': True}


def test_f14_t02(tmp_path):
    values = np.arange(24, dtype='int16').reshape(4, 6) + 50
    for version in (2, 3):
        source = velnora.create_array({}, data=values, chunks=(2, 3), fill_value=-19,
                                   zarr_format=version,
                                   attributes={'nested': {'items': [4, 8]}, 'tags': ['source']})
        destination = tmp_path / f'metadata-{version}'
        copied = velnora.from_array(destination, data=source, write_data=False)
        assert_copy_choices(velnora.open_array(destination, mode='r'), source)
        assert_saved_values(velnora.open_array(destination, mode='r'), np.full_like(values, -19))
        nested = copied.attrs['nested']
        nested['items'].append(99)
        copied.attrs['tags'].append('copy')
        assert source.attrs['nested'] == {'items': [4, 8]}
        assert source.attrs['tags'] == ['source']
        copied.attrs['nested'] = nested
        source.attrs['nested'] = {'items': [-2]}
        assert velnora.open_array(destination, mode='r').attrs['nested'] == {'items': [4, 8, 99]}
        for index, replacement in enumerate(({}, {'new': [6]})):
            target = tmp_path / f'replaced-{version}-{index}'
            velnora.from_array(target, data=source, write_data=False,
                            attributes=replacement, fill_value=31)
            reopened = velnora.open_array(target, mode='r')
            assert dict(reopened.attrs) == replacement
            assert_saved_values(reopened, np.full_like(values, 31))
        copied[1:3, 2:5] = values[1:3, 2:5]
        expected = np.full_like(values, -19)
        expected[1:3, 2:5] = values[1:3, 2:5]
        assert_saved_values(velnora.open_array(destination, mode='r'), expected)
        assert_saved_values(source, values)


def test_f14_t03(tmp_path):
    first = np.array([[17, -4, 91], [6, 38, -27]], dtype='int16')
    second = np.array([1.25, -7.5, 4.75, 0.5], dtype='float64')
    named = {'measurements': np.array([True, False, True], dtype='bool'),
             'offset': np.array(-13, dtype='int32')}
    for version in (2, 3):
        for index, saver in enumerate((velnora.save_array, velnora.save)):
            target = tmp_path / f'single-{version}-{index}'
            saver(target, first, zarr_format=version)
            assert_saved_values(velnora.open_array(target, mode='r'), first)
            np.testing.assert_array_equal(velnora.load(target), first)
        for index, saver in enumerate((velnora.save_group, velnora.save)):
            target = tmp_path / f'group-{version}-{index}'
            saver(target, first, second, path='collection', zarr_format=version, **named)
            group = velnora.open_group(target, path='collection', mode='r')
            assert_saved_members(group, [first, second], named)
            for name, array in group.arrays():
                np.testing.assert_array_equal(velnora.load(target, path=f'collection/{name}'), array[...])
        # One positional array next to a named one is still a group of two.
        for index, saver in enumerate((velnora.save_group, velnora.save)):
            target = tmp_path / f'mixed-{version}-{index}'
            saver(target, first, only=second, zarr_format=version)
            assert_saved_members(velnora.open_group(target, mode='r'), [first], {'only': second})
            target = tmp_path / f'named-{version}-{index}'
            saver(target, only=second, zarr_format=version)
            assert_saved_members(velnora.open_group(target, mode='r'), [], {'only': second})
    for saver in (velnora.save_group, velnora.save):
        with pytest.raises(ValueError):
            saver({})
    with pytest.raises(TypeError):
        velnora.save_array({})


def test_f14_t04(tmp_path):
    old = np.array([18, -5, 77, 2], dtype='int16')
    new = np.array([[1.5, -4.25], [9.75, 2.5], [8.5, -7.0]], dtype='float64')
    for index, operation in enumerate(('save_array', 'save', 'copy')):
        target = tmp_path / f'protected-{index}'
        velnora.save_array(target, old)
        with pytest.raises(ContainsArrayError):
            if operation == 'copy':
                velnora.from_array(target, data=new)
            else:
                getattr(velnora, operation)(target, new)
        assert_saved_values(velnora.open_array(target, mode='r'), old)
        if operation == 'copy':
            velnora.from_array(target, data=new, overwrite=True)
        else:
            velnora.save_array(target, new, overwrite=True)
        assert_saved_values(velnora.open_array(target, mode='r'), new)


def test_f14_t05(tmp_path):
    values = np.arange(15, dtype='int32').reshape(3, 5) * 11 - 7
    for source_name, target_name in (('a', 'a'), ('group/a', 'group'),
                                      ('group/a', ''), ('a', 'a/child')):
        for readonly in (False, True):
            store = MemoryStore()
            velnora.create_array(store, name=source_name, data=values, chunks=(2, 3),
                              fill_value=-31, attributes={'units': 's'})
            source_store = store.with_read_only(True) if readonly else store
            source = velnora.open_array(source_store, path=source_name, mode='r' if readonly else 'r+')
            with pytest.raises(ValueError):
                velnora.from_array(store, name=target_name, data=source, overwrite=True)
            assert_saved_values(velnora.open_array(store, path=source_name, mode='r'), values)
            # Metadata-only copying removes the overlap constraint, but cannot
            # create children of an array under the public hierarchy rules.
            if target_name.startswith(source_name + '/'):
                continue
            velnora.from_array(store, name=target_name, data=source, overwrite=True, write_data=False)
            result = velnora.open_array(store, path=target_name, mode='r')
            assert_saved_values(result, np.full_like(values, -31))
            assert result.chunks == (2, 3)
            assert dict(result.attrs) == {'units': 's'}
    # The same location reached through a separately opened handle is the same data.
    for readonly in (False, True):
        location = tmp_path / f'overlap-{readonly}'
        velnora.create_array(LocalStore(location), name='group/a', data=values, chunks=(2, 3))
        source = velnora.open_array(LocalStore(location, read_only=readonly), path='group/a',
                                 mode='r' if readonly else 'r+')
        with pytest.raises(ValueError):
            velnora.from_array(LocalStore(location), name='group', data=source, overwrite=True)
        assert_saved_values(velnora.open_array(LocalStore(location), path='group/a', mode='r'), values)
    store = MemoryStore()
    source = velnora.create_array(store, name='ab', data=values)
    velnora.create_array(store, name='a', data=np.array([8]))
    velnora.from_array(store, name='a', data=source, overwrite=True)
    assert_saved_values(velnora.open_array(store, path='a'), values)
    assert_saved_values(velnora.open_array(store, path='ab'), values)
