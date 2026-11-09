# feature: F15
"""Acceptance of metadata migration, removal, and mutation guards."""
import lzma
import numpy as np
import numcodecs
import pytest
import velnora
from velnora.metadata.migrate_v3 import migrate_v2_to_v3, remove_metadata
from velnora.storage import LocalStore, MemoryStore

from _helpers import invoke
from F03_helpers import SQLiteStore
from F07_helpers import array_storage_bytes
from F14_helpers import assert_saved_values
from F15_helpers import (migration_cli, require_cli, metadata_keys, payloads,
                         migration_hierarchy, check_migrated_hierarchy, reported_local_paths)


def test_f15_t01(tmp_path):
    # Both public entry paths must preserve the original hierarchy and payloads.
    for command_line in (False, True):
        location = tmp_path / ('cli' if command_line else 'python')
        store, expected = migration_hierarchy(location)
        before = array_storage_bytes(store)
        assert payloads(before), 'Fixture must contain real written chunks'
        if command_line:
            require_cli(migration_cli('migrate', 'v3', location))
        else:
            invoke(migrate_v2_to_v3, call_kwargs={'input_store': store})
        after = array_storage_bytes(store)
        assert {key: after[key] for key in before} == before
        assert payloads(after) == payloads(before)
        check_migrated_hierarchy(store, expected)

    # Separate destinations receive only metadata, with the source untouched.
    for command_line in (False, True):
        source = tmp_path / ('separate-cli' if command_line else 'separate-python')
        destination = tmp_path / (source.name + '-output')
        store, expected = migration_hierarchy(source)
        before = array_storage_bytes(store)
        output = LocalStore(destination)
        if command_line:
            require_cli(migration_cli('migrate', 'v3', source, destination, '--remove-v2-metadata'))
        else:
            invoke(migrate_v2_to_v3, call_kwargs={'input_store': store, 'output_store': output})
        assert array_storage_bytes(store) == before
        check_migrated_hierarchy(output, expected, with_values=False)
        saved = array_storage_bytes(output)
        assert set(saved) == metadata_keys(saved, 3)


def test_f15_t02(tmp_path):
    from velnora.codecs import BytesCodec, BloscCodec, ZstdCodec, GzipCodec
    from velnora.codecs.numcodecs import Delta, LZMA

    conversions = [
        (None, None, (BytesCodec(endian='little'),)),
        (numcodecs.Blosc(cname='zstd', clevel=3, shuffle=2), None,
         (BytesCodec(endian='little'), BloscCodec(typesize=2, cname='zstd', clevel=3,
                                                shuffle='bitshuffle', blocksize=0))),
        (numcodecs.Zstd(level=5, checksum=True), None,
         (BytesCodec(endian='little'), ZstdCodec(level=5, checksum=True))),
        (numcodecs.GZip(level=4), None,
         (BytesCodec(endian='little'), GzipCodec(level=4))),
        (numcodecs.LZMA(format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=2),
         numcodecs.Delta(dtype='<u2', astype='<u2'),
         (Delta(dtype='<u2', astype='<u2'), BytesCodec(endian='little'),
          LZMA(format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=2))),
    ]
    for compressor, filter_codec, expected_codecs in conversions:
        store = MemoryStore()
        array = velnora.create_array(store, shape=(4, 6), chunks=(2, 3), dtype='<u2',
                                  zarr_format=2, compressors=compressor, filters=filter_codec,
                                  fill_value=17)
        values = (np.arange(24).reshape(4, 6) * 19 + 3).astype('<u2')
        array[:] = values
        before = array_storage_bytes(store)
        invoke(migrate_v2_to_v3, call_kwargs={'input_store': store})
        migrated = velnora.open_array(store, mode='r', zarr_format=3)
        actual_codecs = migrated.metadata.codecs
        assert len(actual_codecs) == len(expected_codecs)
        for actual, expected in zip(actual_codecs, expected_codecs, strict=True):
            actual_doc, expected_doc = actual.to_dict(), expected.to_dict()
            assert actual_doc['name'] == expected_doc['name']
            for key, value in expected_doc.get('configuration', {}).items():
                assert actual_doc['configuration'][key] == value
        assert_saved_values(migrated, values)
        assert payloads(array_storage_bytes(store)) == payloads(before)

    # Every rejection has a valid migration baseline above, and a specific
    # public Python failure carrier, without pinning English error sentences.
    invalid = []
    for kind in ('array', 'group'):
        store = MemoryStore()
        if kind == 'array':
            velnora.create_array(store, shape=(3,), dtype='int16', zarr_format=3)
        else:
            velnora.create_group(store, zarr_format=3)
        invalid.append((store, TypeError))
    store = MemoryStore()
    group = velnora.create_group(store, zarr_format=2)
    group.create_array('a', shape=(2,), dtype='uint8')
    velnora.consolidate_metadata(store)
    invalid.append((store, NotImplementedError))
    for compressor, filters, error in [
        (None, [numcodecs.Categorize(labels=['red', 'blue'], dtype=object)], ValueError),
        (None, [numcodecs.Zstd(level=3)], TypeError),
        (numcodecs.Delta(dtype='<u2', astype='<u2'), None, TypeError),
    ]:
        store = MemoryStore()
        velnora.create_array(store, shape=(2,), dtype='<u2', zarr_format=2,
                          compressors=compressor, filters=filters, fill_value=0)
        invalid.append((store, error))
    for store, error in invalid:
        with pytest.raises(error):
            invoke(migrate_v2_to_v3, call_kwargs={'input_store': store})


def test_f15_t03(tmp_path):
    # Retention by default and removal of either version after migration.
    for version in (2, 3):
        location = tmp_path / f'remove-{version}'
        store, expected = migration_hierarchy(location)
        before = array_storage_bytes(store)
        invoke(migrate_v2_to_v3, call_kwargs={'input_store': store})
        assert metadata_keys(array_storage_bytes(store), 2) == metadata_keys(before, 2)
        if version == 2:
            velnora.consolidate_metadata(store, zarr_format=2)
        both = array_storage_bytes(store)
        if version == 2:
            invoke(remove_metadata, store, version)
        else:
            require_cli(migration_cli('remove-metadata', 'v3', location))
        after = array_storage_bytes(store)
        assert after == {key: value for key, value in both.items()
                         if key not in metadata_keys(both, version)}
        if version == 2:
            check_migrated_hierarchy(store, expected)
        else:
            group = velnora.open_group(store, mode='r', zarr_format=2)
            for path, (values, _) in expected.items():
                assert_saved_values(group[path], values)

    # The migration option removes source metadata only at the output location.
    location = tmp_path / 'migration-removes'
    store, expected = migration_hierarchy(location)
    before = array_storage_bytes(store)
    require_cli(migration_cli('migrate', 'v3', location, '--remove-v2-metadata'))
    after = array_storage_bytes(store)
    assert not metadata_keys(after, 2)
    assert payloads(after) == payloads(before)
    check_migrated_hierarchy(store, expected)

    for version in (2, 3):
        location = tmp_path / f'force-{version}'
        store, _ = migration_hierarchy(location)
        if version == 3:
            invoke(migrate_v2_to_v3, call_kwargs={'input_store': store})
            invoke(remove_metadata, store, 2)
        before = array_storage_bytes(store)
        with pytest.raises(ValueError):
            invoke(remove_metadata, store, version)
        assert array_storage_bytes(store) == before
        require_cli(migration_cli('remove-metadata', f'v{version}', location), success=False)
        require_cli(migration_cli('remove-metadata', f'v{version}', location, '--force'))
        assert array_storage_bytes(store) == payloads(before)

    # An alternate at the root cannot authorize deletion at an unpaired child.
    store, _ = migration_hierarchy(tmp_path / 'per-node')
    invoke(migrate_v2_to_v3, call_kwargs={'input_store': store})
    invoke(store.delete, 'branch/deep/zarr.json')
    with pytest.raises(ValueError):
        invoke(remove_metadata, store, 2)
    # No transaction guarantee is assumed for the rest of the hierarchy.
    assert 'branch/deep/.zarray' in array_storage_bytes(store)

    limited = SQLiteStore(tmp_path / 'no-deletion.sqlite', supports_deletes=False)
    try:
        velnora.create_array(limited, shape=(2,), dtype='int16', zarr_format=2, compressors=None)
        before = array_storage_bytes(limited)
        with pytest.raises(ValueError):
            invoke(remove_metadata, limited, 2, call_kwargs={'force': True})
        assert array_storage_bytes(limited) == before
    finally:
        limited.close()


def test_f15_t04(tmp_path, caplog):
    import logging

    # Compare every reported target with independently enumerated source metadata.
    # The path carrier is public; human sentence wording is not an oracle.
    caplog.set_level(logging.INFO)
    for operation in ('migrate', 'remove-metadata'):
        location = tmp_path / (operation + ' space')
        store, expected = migration_hierarchy(location)
        before = array_storage_bytes(store)
        if operation == 'migrate':
            expected_paths = {location / key.rpartition('/')[0] / 'zarr.json'
                                     for key in before
                                     if key.rpartition('/')[2] in ('.zarray', '.zgroup')}
            caplog.clear()
            invoke(migrate_v2_to_v3, call_kwargs={'input_store': store, 'dry_run': True})
            assert reported_local_paths(record.getMessage() for record in caplog.records) == expected_paths
            assert array_storage_bytes(store) == before
            completed = migration_cli('migrate', 'v3', location, '--dry-run')
            require_cli(completed)
            assert reported_local_paths(completed.stderr.splitlines()) == expected_paths
            assert array_storage_bytes(store) == before
            require_cli(migration_cli('migrate', 'v3', location))
            check_migrated_hierarchy(store, expected)
        else:
            expected_paths = {location / key for key in metadata_keys(before, 2)}
            caplog.clear()
            invoke(remove_metadata, store, 2, call_kwargs={'force': True, 'dry_run': True})
            assert reported_local_paths(record.getMessage() for record in caplog.records) == expected_paths
            assert array_storage_bytes(store) == before
            completed = migration_cli('remove-metadata', 'v2', location, '--force', '--dry-run')
            require_cli(completed)
            assert reported_local_paths(completed.stderr.splitlines()) == expected_paths
            assert array_storage_bytes(store) == before
            require_cli(migration_cli('remove-metadata', 'v2', location, '--force'))
            assert array_storage_bytes(store) == payloads(before)
    location = tmp_path / 'invalid-dry'
    store = LocalStore(location)
    velnora.create_group(store, zarr_format=3)
    before = array_storage_bytes(store)
    with pytest.raises(TypeError):
        invoke(migrate_v2_to_v3, call_kwargs={'input_store': store, 'dry_run': True})
    require_cli(migration_cli('migrate', 'v3', location, '--dry-run'), success=False)
    assert array_storage_bytes(store) == before


def test_f15_t05(tmp_path):
    location = tmp_path / 'in-place'
    store, expected = migration_hierarchy(location)
    require_cli(migration_cli('migrate', 'v3', location))
    before = array_storage_bytes(store)
    # Make regeneration observable rather than repeating identical metadata.
    group = velnora.open_group(store, zarr_format=2, mode='r+', use_consolidated=False)
    group['direct'].attrs['revision'] = 8
    expected['direct'][1]['revision'] = 8
    protected = array_storage_bytes(store)
    require_cli(migration_cli('migrate', 'v3', location), success=False)
    assert array_storage_bytes(store) == protected
    with pytest.raises((TypeError, ValueError)):
        invoke(migrate_v2_to_v3, call_kwargs={'input_store': store})
    assert array_storage_bytes(store) == protected
    require_cli(migration_cli('migrate', 'v3', location, '--overwrite'))
    check_migrated_hierarchy(store, expected)
    assert payloads(array_storage_bytes(store)) == payloads(before)

    # A metadata-only destination lacks the alternate needed for replacement.
    source = tmp_path / 'source'
    destination = tmp_path / 'destination'
    source_store, expected = migration_hierarchy(source)
    require_cli(migration_cli('migrate', 'v3', source, destination))
    destination_store = LocalStore(destination)
    before = array_storage_bytes(destination_store)
    source_group = velnora.open_group(source_store, mode='r+', zarr_format=2)
    source_group['direct'].attrs['revision'] = 11
    expected['direct'][1]['revision'] = 11
    source_before = array_storage_bytes(source_store)
    require_cli(migration_cli('migrate', 'v3', source, destination), success=False)
    assert array_storage_bytes(destination_store) == before
    require_cli(migration_cli('migrate', 'v3', source, destination, '--overwrite'), success=False)
    assert array_storage_bytes(destination_store) == before
    require_cli(migration_cli('migrate', 'v3', source, destination, '--overwrite', '--force'))
    check_migrated_hierarchy(destination_store, expected, with_values=False)
    assert set(array_storage_bytes(destination_store)) == metadata_keys(before, 3)
    assert array_storage_bytes(source_store) == source_before
