# feature: F13
"""Acceptance of complete hierarchy snapshots and consolidation policies."""
import numpy as np
import numcodecs
import pytest
import velnora
from velnora.codecs import (
    BytesCodec, GzipCodec
)
from velnora.storage import MemoryStore

from _helpers import invoke
from F03_helpers import read_bytes
from F07_helpers import assert_array_definition, array_properties, array_storage_bytes
from F13_helpers import MetadataAccessStore


def test_f13_t01():
    for version in (2, 3):
        store = MemoryStore()
        root = velnora.create_group(store, zarr_format=version, attributes={'survey': [3, 'north']})
        branch = root.create_group('branch', attributes={'units': {'distance': 'm'}})
        branch.create_group('deep/empty', attributes={'purpose': 'empty'})
        options = (dict(compressors=numcodecs.Zlib(level=2)) if version == 2 else
                   dict(shards=(4, 6), serializer=BytesCodec(endian='big'),
                        compressors=GzipCodec(level=2), dimension_names=('row', 'column')))
        a = branch.create_array('deep/values', shape=(6, 9), chunks=(2, 3),
                                dtype='int32', fill_value=-37,
                                attributes={'labels': ['a', 'b'], 'enabled': True}, **options)
        initial = np.arange(54, dtype='int32').reshape(6, 9) * 7 - 83
        a[:] = initial
        consolidated = velnora.consolidate_metadata(store)
        assert isinstance(consolidated, velnora.Group)
        # Metadata is a snapshot; the array payload is deliberately changed later.
        current = initial[::-1].copy() + 101
        a[:] = current
        for view in (consolidated, velnora.open_group(store, mode='r', use_consolidated=True)):
            assert dict(view.attrs) == {'survey': [3, 'north']}
            members = dict(invoke(view.members, call_kwargs={'max_depth': None}, consume=True).value)
            expected = {'branch': velnora.Group, 'branch/deep': velnora.Group,
                        'branch/deep/empty': velnora.Group, 'branch/deep/values': velnora.Array}
            assert set(members) == set(expected)
            for path, kind in expected.items():
                assert isinstance(members[path], kind)
                assert isinstance(view[path], kind)
            assert dict(view['branch'].attrs) == {'units': {'distance': 'm'}}
            assert dict(view['branch/deep/empty'].attrs) == {'purpose': 'empty'}
            observed = view['branch/deep/values']
            assert_array_definition(observed, shape=(6, 9), dtype='int32', chunks=(2, 3),
                                    fill_value=-37, version=version)
            properties = array_properties(observed)
            assert properties['shards'] == ((4, 6) if version == 3 else None)
            assert properties['dimension_names'] == (('row', 'column') if version == 3 else None)
            assert properties['filters'] == ()
            assert len(properties['compressors']) == 1
            if version == 2:
                assert properties['serializer'] is None
                assert properties['compressors'][0].get_config() == numcodecs.Zlib(level=2).get_config()
            else:
                assert properties['serializer'].to_dict() == BytesCodec(endian='big').to_dict()
                assert properties['compressors'][0].to_dict() == GzipCodec(level=2).to_dict()
            assert dict(observed.attrs) == {'labels': ['a', 'b'], 'enabled': True}
            np.testing.assert_array_equal(observed[:], current)
            for depth, names in ((0, {'branch'}), (1, {'branch', 'branch/deep'}),
                                 (2, set(expected))):
                assert {name for name, _ in view.members(max_depth=depth)} == names
                assert view.nmembers(max_depth=depth) == len(names)
            assert view.nmembers(max_depth=None) == len(expected)
            with pytest.raises(ValueError):
                view.nmembers(max_depth=-1)
            with pytest.raises(ValueError):
                invoke(view.members, call_kwargs={'max_depth': -1}, consume=True)
            assert set(view) == {'branch'} and len(view) == 1
            assert 'branch/deep/values' in view and 'branch/absent' not in view
            assert {name for name, _ in view['branch'].members(max_depth=None)} == {
                'deep', 'deep/empty', 'deep/values'}
            assert view['branch/deep/empty'].nmembers() == 0


def test_f13_t02():
    for version in (2, 3):
        store = MemoryStore()
        root = velnora.create_group(store, zarr_format=version)
        a = root.create_array('branch/values', shape=(4, 6), chunks=(2, 3), dtype='int16',
                              fill_value=-11, attributes={'revision': 'old'})
        a[:] = np.arange(24, dtype='int16').reshape(4, 6)
        # A live ordinary view works before requiring the absent snapshot.
        assert velnora.open_group(store, mode='r')['branch/values'].shape == (4, 6)
        with pytest.raises(ValueError):
            velnora.open_group(store, mode='r', use_consolidated=True)
        velnora.consolidate_metadata(store)
        direct = velnora.open_group(store, mode='r+', use_consolidated=False)
        direct['branch'].attrs['revision'] = 'new-group'
        changed = direct['branch/values']
        # Grow rather than shrink, preserving old chunks for readers of the old shape.
        changed.resize((6, 6))
        changed.attrs['revision'] = 'new-array'
        direct.create_array('branch/added', data=np.array([71, -8], dtype='int16'))
        for policy in ({}, {'use_consolidated': True}, {'use_consolidated': False}):
            view = velnora.open_group(store, mode='r', **policy)
            fresh = policy.get('use_consolidated') is False
            members = dict(invoke(view.members, call_kwargs={'max_depth': None}, consume=True).value)
            assert set(members) == ({'branch', 'branch/values', 'branch/added'} if fresh else
                                    {'branch', 'branch/values'})
            assert view['branch/values'].shape == ((6, 6) if fresh else (4, 6))
            assert dict(view['branch/values'].attrs) == {'revision': 'new-array' if fresh else 'old'}
            assert dict(view['branch'].attrs) == ({'revision': 'new-group'} if fresh else {})
            if fresh:
                np.testing.assert_array_equal(view['branch/added'][:], [71, -8])
        velnora.consolidate_metadata(store)
        for policy in ({}, {'use_consolidated': True}):
            refreshed = velnora.open_group(store, mode='r', **policy)
            assert {name for name, _ in invoke(refreshed.members,
                    call_kwargs={'max_depth': None}, consume=True).value} == {
                'branch', 'branch/values', 'branch/added'}
            assert refreshed['branch/values'].shape == (6, 6)
            assert dict(refreshed['branch/values'].attrs) == {'revision': 'new-array'}
            assert dict(refreshed['branch'].attrs) == {'revision': 'new-group'}
            np.testing.assert_array_equal(refreshed['branch/added'][:], [71, -8])


def test_f13_t03(tmp_path):
    for version in (2, 3):
        store = MetadataAccessStore(tmp_path / f'metadata-{version}.sqlite')
        try:
            root = velnora.create_group(store, zarr_format=version)
            root.create_group('branch/deep/empty', attributes={'role': 'leaf'})
            root.create_array('branch/deep/data', shape=(5,), chunks=(2,), dtype='int16',
                              fill_value=-19, attributes={'unit': 'm'})
            velnora.consolidate_metadata(store)
            view = velnora.open_group(store, mode='r', use_consolidated=True)
            # Prove the restriction is active on a real, previously readable document.
            key = 'branch/deep/data/' + ('.zarray' if version == 2 else 'zarr.json')
            assert read_bytes(store, key) is not None
            store.block_descendant_metadata = True
            with pytest.raises(AssertionError):
                read_bytes(store, key)
            members = dict(invoke(view.members, call_kwargs={'max_depth': None}, consume=True).value)
            assert set(members) == {'branch', 'branch/deep', 'branch/deep/empty', 'branch/deep/data'}
            assert isinstance(view['branch/deep/empty'], velnora.Group)
            assert dict(view['branch/deep/empty'].attrs) == {'role': 'leaf'}
            a = view['branch/deep/data']
            assert_array_definition(a, shape=(5,), dtype='int16', chunks=(2,),
                                    fill_value=-19, version=version)
            assert dict(a.attrs) == {'unit': 'm'}
            np.testing.assert_array_equal(a[:], [-19] * 5)
            store.block_descendant_metadata = False
            # Existing snapshot bytes remain, but the store opts out of using them.
            direct = velnora.open_group(store, mode='r+', use_consolidated=False)
            direct['branch/deep/data'].attrs['unit'] = 'cm'
            direct.create_group('later', attributes={'visible': True})
            store.supports_consolidated_metadata = False
            before = array_storage_bytes(store)
            with pytest.raises(TypeError):
                velnora.consolidate_metadata(store)
            with pytest.raises(ValueError):
                velnora.open_group(store, mode='r', use_consolidated=True)
            assert array_storage_bytes(store) == before
            ordinary = velnora.open_group(store, mode='r')
            assert dict(ordinary['branch/deep/data'].attrs) == {'unit': 'cm'}
            assert dict(ordinary['later'].attrs) == {'visible': True}
            assert {name for name, _ in invoke(ordinary.members, consume=True).value} == {'branch', 'later'}
        finally:
            store.close()
