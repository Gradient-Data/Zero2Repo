# feature: F11
"""Acceptance checks for hierarchical groups through public entries."""
import numpy as np
import pytest
import velnora
from velnora.core.group import GroupMetadata
from velnora.errors import (
    ArrayNotFoundError, ContainsArrayError, ContainsGroupError, GroupNotFoundError,
)
from velnora.storage import MemoryStore

from _helpers import invoke
from F02_helpers import assert_dtype_meaning
from F03_helpers import SQLiteStore, read_bytes
from F07_helpers import array_storage_bytes
from F11_helpers import read_group_tree


def test_f11_t01():
    for version in (2, 3):
        store = MemoryStore()
        root = velnora.create_group(store, zarr_format=version)
        root.create_group('catalog/empty')
        root.create_array('catalog/run/values', data=np.array([13, -6, 28], dtype='int16'))
        reopened = velnora.open_group(store, mode='r')
        assert reopened.metadata.zarr_format == version
        for path in ('catalog', 'catalog/empty', 'catalog/run'):
            assert isinstance(reopened[path], velnora.Group)
            assert isinstance(reopened.get_group(path), velnora.Group)
        for entry in (reopened.__getitem__, reopened.get_array):
            node = entry('catalog/run/values')
            assert isinstance(node, velnora.Array)
            np.testing.assert_array_equal(node[:], [13, -6, 28])
        with pytest.raises(KeyError):
            reopened['absent']
        with pytest.raises(ArrayNotFoundError):
            reopened.get_array('absent')
        with pytest.raises(GroupNotFoundError):
            reopened.get_group('absent')
        with pytest.raises(ContainsGroupError):
            reopened.get_array('catalog/run')
        with pytest.raises(ContainsArrayError):
            reopened.get_group('catalog/run/values')


def test_f11_t02():
    for version in (2, 3):
        store = MemoryStore()
        root = velnora.create_group(store, zarr_format=version)
        root.create_group('branch/deep/empty')
        root.create_array('branch/deep/leaf', data=np.array([8, -3], dtype='int16'))
        root.create_array('branch/middle', data=np.array([21], dtype='int16'))
        root.create_array('top', data=np.array([7], dtype='int16'))
        root = velnora.open_group(store, mode='r')
        all_kinds = {'branch': velnora.Group, 'top': velnora.Array,
                     'branch/deep': velnora.Group, 'branch/middle': velnora.Array,
                     'branch/deep/empty': velnora.Group, 'branch/deep/leaf': velnora.Array}
        assert set(root) == {'branch', 'top'}
        assert len(root) == 2
        assert {name for name, _ in root.members()} == {'branch', 'top'}
        assert root.nmembers() == 2
        for path in all_kinds:
            assert path in root
        assert 'branch/missing' not in root
        for depth in (0, 1, 2, None):
            expected = {name: kind for name, kind in all_kinds.items()
                        if depth is None or name.count('/') <= depth}
            observed = dict(invoke(root.members, call_kwargs={'max_depth': depth}, consume=True).value)
            assert set(observed) == set(expected)
            for name, kind in expected.items():
                assert isinstance(observed[name], kind)
            assert root.nmembers(max_depth=depth) == len(expected)
        with pytest.raises(ValueError):
            invoke(root.members, call_kwargs={'max_depth': -1}, consume=True)
        with pytest.raises(ValueError):
            root.nmembers(max_depth=-1)


def test_f11_t03(tmp_path):
    for version in (2, 3):
        store = MemoryStore()
        root = velnora.create_group(store, zarr_format=version)
        root.create_array('cut/nested/data', data=np.array([12, -9, 31], dtype='int16'), chunks=(2,))
        root.create_array('cutlery/keep', data=np.array([4, 19], dtype='int16'))
        root.create_array('single', data=np.array([23, -5], dtype='int16'))
        before = array_storage_bytes(store)
        target_keys = {k for k in before if k.startswith('cut/')}
        assert target_keys
        assert any(k.startswith('cut/nested/data/') and
                   k.rsplit('/', 1)[-1] not in {'.zarray', '.zattrs', 'zarr.json'}
                   for k in target_keys)
        np.testing.assert_array_equal(root['cut/nested/data'][:], [12, -9, 31])
        # Both refusal paths start with actual stored data and must leave it intact.
        readonly = velnora.open_group(store, mode='r')
        with pytest.raises(ValueError):
            del readonly['cut']
        assert array_storage_bytes(store) == before
        unsupported = SQLiteStore(tmp_path / f'no-delete-{version}.sqlite', supports_deletes=False)
        try:
            other = velnora.create_group(unsupported, zarr_format=version)
            other.create_array('data', data=np.array([6, -2], dtype='int16'))
            snapshot = array_storage_bytes(unsupported)
            with pytest.raises(NotImplementedError):
                del other['data']
            assert array_storage_bytes(unsupported) == snapshot
        finally:
            unsupported.close()
        del root['cut']
        assert array_storage_bytes(store) == {k: v for k, v in before.items() if k not in target_keys}
        for key in target_keys:
            assert read_bytes(store, key) is None
        reopened = velnora.open_group(store, mode='r+')
        with pytest.raises(KeyError):
            reopened['cut']
        np.testing.assert_array_equal(reopened['cutlery/keep'][:], [4, 19])
        before_single = array_storage_bytes(store)
        del reopened['single']
        assert array_storage_bytes(store) == {k: v for k, v in before_single.items()
                                             if not k.startswith('single/')}
        with pytest.raises(KeyError):
            velnora.open_group(store, mode='r')['single']


def test_f11_t04():
    for version in (2, 3):
        store = MemoryStore()
        root = velnora.create_group(store, zarr_format=version)
        group = root.require_group('reused/nested')
        group.attrs['purpose'] = 'retained'
        group.create_array('child', data=np.array([9, -4], dtype='int16'))
        reused = root.require_group('reused/nested')
        assert isinstance(reused, velnora.Group)
        assert reused.attrs['purpose'] == 'retained'
        np.testing.assert_array_equal(reused['child'][:], [9, -4])
        a = root.require_array('values', shape=(3,), dtype='int16', fill_value=-11,
                               attributes={'source': 'caller'})
        np.testing.assert_array_equal(a[:], [-11, -11, -11])
        a[:] = [17, -8, 41]
        for requested, options in (('int16', {}), ('int16', {'exact': True}), ('int32', {})):
            b = root.require_array('values', shape=(3,), dtype=requested, **options)
            assert b.shape == (3,)
            assert_dtype_meaning(b.dtype, 'int16')
            assert b.attrs['source'] == 'caller'
            np.testing.assert_array_equal(b[:], [17, -8, 41])
        before = array_storage_bytes(store)
        for options in ({'shape': (4,), 'dtype': 'int16'},
                        {'shape': (3,), 'dtype': 'int8'},
                        {'shape': (3,), 'dtype': 'int32', 'exact': True}):
            with pytest.raises(TypeError):
                root.require_array('values', **options)
        with pytest.raises(TypeError):
            root.require_group('values')
        with pytest.raises(TypeError):
            root.require_array('reused', shape=(3,), dtype='int16')
        assert array_storage_bytes(store) == before
        np.testing.assert_array_equal(velnora.open_group(store, mode='r')['values'][:], [17, -8, 41])


def test_f11_t05():
    for version in (2, 3):
        # Descriptions come from a real public array definition; batch creation
        # creates metadata, so unwritten elements must have the caller's fill.
        description = velnora.create_array(MemoryStore(), shape=(3,), dtype='int16',
                                        fill_value=-14, zarr_format=version).metadata
        store = MemoryStore()
        nodes = {'branch/deep/values': description,
                 'empty': GroupMetadata(zarr_format=version, attributes={'role': 'empty'})}
        created = dict(invoke(velnora.create_hierarchy, call_kwargs={'store': store, 'nodes': nodes},
                              consume=True).value)
        assert {'', 'branch', 'branch/deep', 'branch/deep/values', 'empty'} <= set(created)
        root = velnora.open_group(store, mode='r+')
        for path in ('branch', 'branch/deep', 'empty'):
            assert isinstance(root[path], velnora.Group)
        assert root['empty'].attrs['role'] == 'empty'
        np.testing.assert_array_equal(root['branch/deep/values'][:], [-14, -14, -14])
        root['branch/deep/values'][:] = [5, -7, 22]
        before = array_storage_bytes(store)
        for path, metadata, error in (
            ('branch/deep/values', description, ContainsArrayError),
            ('empty', GroupMetadata(zarr_format=version), ContainsGroupError),
        ):
            with pytest.raises(error):
                invoke(velnora.create_hierarchy, call_kwargs={'store': store, 'nodes': {path: metadata}},
                       consume=True)
            assert array_storage_bytes(store) == before
        replacement = velnora.create_array(MemoryStore(), shape=(2,), dtype='int16',
                                         fill_value=26, zarr_format=version).metadata
        invoke(velnora.create_hierarchy, call_kwargs={'store': store,
               'nodes': {'branch/deep/values': replacement}, 'overwrite': True}, consume=True)
        np.testing.assert_array_equal(velnora.open_group(store, mode='r')['branch/deep/values'][:], [26, 26])
        for child in (description, GroupMetadata(zarr_format=version)):
            with pytest.raises(ValueError):
                invoke(velnora.create_hierarchy, call_kwargs={'store': MemoryStore(),
                       'nodes': {'array': description, 'array/child': child}}, consume=True)
        with pytest.raises(ValueError):
            invoke(velnora.create_hierarchy, call_kwargs={'store': MemoryStore(), 'nodes': {
                'old': GroupMetadata(zarr_format=2), 'new': GroupMetadata(zarr_format=3)}}, consume=True)


def test_f11_t06():
    for version in (2, 3):
        store = MemoryStore()
        root = velnora.create_group(store, zarr_format=version)
        display = root.create_group('display')
        display.create_group('branch/deep/empty')
        display.create_group('other')
        display.create_array('branch/data', data=np.array([12, -5], dtype='int16'))
        display.create_array('other/data', data=np.array([7], dtype='int32'))
        display.create_array('branch/deep/data', data=np.array([31, 9], dtype='int16'))
        display = velnora.open_group(store, mode='r')['display']
        expected = {'': 'group', 'branch': 'group', 'branch/deep': 'group',
                    'branch/deep/empty': 'group', 'other': 'group',
                    'branch/data': 'array', 'other/data': 'array',
                    'branch/deep/data': 'array'}
        # A complete live display precedes the depth-limited observations.
        assert read_group_tree(display) == expected
        for depth in (0, 1, 2):
            visible = {path: kind for path, kind in expected.items()
                       if path == '' or path.count('/') <= depth}
            assert read_group_tree(display, level=depth) == visible
        with pytest.raises(ValueError):
            read_group_tree(display, level=-1)
