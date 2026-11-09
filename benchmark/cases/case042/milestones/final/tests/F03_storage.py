# feature: F03
"""Acceptance of storage persistence, byte access, and extension boundaries."""
import sqlite3
import urllib.request
import zipfile
import uuid

import numpy as np
import pytest
import velnora
from velnora.abc.store import RangeByteRequest, OffsetByteRequest, SuffixByteRequest
from velnora.core.buffer import default_buffer_prototype
from velnora.storage import MemoryStore, LocalStore, ZipStore, FsspecStore, ObjectStore

from _helpers import invoke, run_python, run_python_report, bound_tcp_socket, ExecutionTimeout
from F03_helpers import put_bytes, read_bytes, listed, served_directory, s3_service, SQLiteStore


def test_f03_t01(tmp_path):
    memory = MemoryStore()
    try:
        put_bytes(memory, 'message', b'\x00memory\xff')
        assert read_bytes(memory, 'message') == b'\x00memory\xff'
        a = velnora.create_array(store=memory, name='numbers', shape=(5,), chunks=(2,),
                              dtype='int32', compressors=None)
        a[:] = [19, -7, 42, 8, 13]
        np.testing.assert_array_equal(velnora.open_array(memory, path='numbers')[:], [19, -7, 42, 8, 13])
    finally:
        memory.close()

    # The writer exits before a separately started reader knows the location.
    writer = '''
import sys, velnora
from velnora.storage import LocalStore, ZipStore
from velnora.core.buffer import default_buffer_prototype
from velnora.core.sync import sync
kind, path = sys.argv[1:]
store = LocalStore(path) if kind == 'local' else sync(ZipStore.open(path, mode='w'))
sync(store.set('payload/raw', default_buffer_prototype().buffer.from_bytes(b'persist\\x00\\xff')))
a = velnora.create_array(store=store, name='numbers', shape=(5,), chunks=(2,), dtype='int32', compressors=None)
a[:] = [19, -7, 42, 8, 13]
store.close()
'''
    reader = '''
import sys, json, velnora
from velnora.storage import LocalStore, ZipStore
from velnora.core.buffer import default_buffer_prototype
from velnora.core.sync import sync
report, kind, path = sys.argv[1:]
store = LocalStore(path, read_only=True) if kind == 'local' else sync(ZipStore.open(path, mode='r'))
raw = sync(store.get('payload/raw', default_buffer_prototype()))
a = velnora.open_array(store, path='numbers', mode='r')
with open(report, 'w') as f:
    json.dump({'bytes': list(raw.to_bytes()), 'values': a[:].tolist()}, f)
store.close()
'''
    for kind in ('local', 'zip'):
        path = tmp_path / (kind + ('.zip' if kind == 'zip' else ''))
        result = run_python(writer, [kind, str(path)])
        result.check_returncode()
        _, report = run_python_report(reader, [kind, str(path)])
        assert report == {'bytes': list(b'persist\x00\xff'), 'values': [19, -7, 42, 8, 13]}
        if kind == 'zip':
            with zipfile.ZipFile(path) as archive:
                assert archive.read('payload/raw') == b'persist\x00\xff'
            # Caller owns the open file for the entire access lifetime.
            with path.open('rb') as stream:
                store = invoke(ZipStore.open, stream, call_kwargs={'mode': 'r'}).value
                try:
                    assert read_bytes(store, 'payload/raw') == b'persist\x00\xff'
                    np.testing.assert_array_equal(velnora.open_array(store, path='numbers')[:], [19, -7, 42, 8, 13])
                finally:
                    store.close()
    binary_path = tmp_path / 'binary.zip'
    with binary_path.open('w+b') as stream:
        store = invoke(ZipStore.open, stream, call_kwargs={'mode': 'w'}).value
        put_bytes(store, 'file/value', b'caller-owned-file')
        store.close()
    with binary_path.open('rb') as stream:
        store = invoke(ZipStore.open, stream, call_kwargs={'mode': 'r'}).value
        try:
            assert read_bytes(store, 'file/value') == b'caller-owned-file'
        finally:
            store.close()


def test_f03_t02(tmp_path):
    # Real HTTP resources with independent clients.
    import obstore
    from obstore.store import HTTPStore

    for directory, payload in [('first', b'first-remote\x00\xff'), ('second', b'other-remote-value')]:
        root = tmp_path / directory
        root.mkdir()
        (root / 'data').mkdir()
        (root / 'data' / 'item').write_bytes(payload)
        (root / 'item').write_bytes(b'outside-selected-location')
        headers = {'X-Storage-Token': directory}
        with served_directory(root, required_headers=headers) as endpoint:
            url = endpoint + '/data'
            request = urllib.request.Request(url + '/item', headers=headers)
            with urllib.request.urlopen(request, timeout=10) as response:
                assert response.read() == payload
            upstream = HTTPStore(url, client_options={'allow_http': True, 'default_headers': headers})
            assert bytes(obstore.get(upstream, 'item').bytes()) == payload
            stores = [FsspecStore.from_url(url, storage_options={'skip_instance_cache': True, 'headers': headers}, read_only=True), ObjectStore(upstream, read_only=True)]
            async def check_remote():
                from velnora.core.buffer import default_buffer_prototype
                for store in stores:
                    try:
                        value = await store.get('item', default_buffer_prototype())
                        assert value is not None
                        assert value.to_bytes() == payload
                        assert await store.exists('item') is True
                        assert await store.get('absent', default_buffer_prototype()) is None
                    finally:
                        store.close()
            invoke(check_remote)


def test_f03_t03(tmp_path):
    stores = [MemoryStore(), LocalStore(tmp_path / 'local'), invoke(ZipStore.open, tmp_path / 'ranges.zip', call_kwargs={'mode': 'w'}).value]
    values = {'root': b'ROOT', 'data/one': b'0123456789abcdef', 'data/empty': b'',
              'data/nested/two': b'other', 'data/nested/four': b'more', 'database/three': b'sibling'}
    for store in stores:
        try:
            for key, data in values.items():
                put_bytes(store, key, data)
            for key, data in values.items():
                assert read_bytes(store, key) == data
                assert invoke(store.exists, key).value is True
                assert invoke(store.getsize, key).value == len(data)
            assert read_bytes(store, 'absent') is None
            assert invoke(store.exists, 'absent').value is False
            requests = [(RangeByteRequest(2, 7), b'23456'), (RangeByteRequest(12, 80), b'cdef'),
                        (OffsetByteRequest(5), b'56789abcdef'), (SuffixByteRequest(4), b'cdef'),
                        (SuffixByteRequest(80), values['data/one']),
                        (RangeByteRequest(80, 90), b''), (OffsetByteRequest(80), b'')]
            for request, expected in requests:
                assert read_bytes(store, 'data/one', request) == expected
            assert listed(store.list) == set(values)
            assert listed(store.list_prefix, 'data/') == {k for k in values if k.startswith('data/')}
            assert listed(store.list_dir, '') == {'root', 'data', 'database'}
            # A child with several descendants is still one directory entry.
            assert sorted(invoke(store.list_dir, 'data', consume=True).value) == ['empty', 'nested', 'one']
            assert listed(store.list_dir, 'data/nested') == {'two', 'four'}
            # Several requests answer in request order; only existing keys are asked here.
            parts = invoke(store.get_partial_values, default_buffer_prototype(), [
                ('data/one', RangeByteRequest(2, 5)), ('root', None), ('data/one', SuffixByteRequest(2)),
                ('data/one', OffsetByteRequest(14)), ('data/empty', None)]).value
            assert [part.to_bytes() for part in parts] == [b'234', b'ROOT', b'ef', b'ef', b'']
            # LocalStore's missing-key batch bug is recorded in the ledger.
            if not isinstance(store, LocalStore):
                parts = invoke(store.get_partial_values, default_buffer_prototype(), [
                    ('absent', None), ('data/empty', None),
                    ('data/one', RangeByteRequest(1, 4)), ('absent', None),
                    ('root', None)]).value
                assert [None if part is None else part.to_bytes() for part in parts] == [
                    None, b'', b'123', None, b'ROOT']
        finally:
            store.close()


def test_f03_t04(tmp_path):
    for store in (MemoryStore(), LocalStore(tmp_path / 'mutable')):
        view = None
        try:
            put_bytes(store, 'tree/key', b'old')
            assert read_bytes(store, 'tree/key') == b'old'
            put_bytes(store, 'tree/key', b'replaced')
            put_bytes(store, 'tree/nested/value', b'child')
            put_bytes(store, 'treehouse/key', b'sibling')
            assert read_bytes(store, 'tree/key') == b'replaced'
            view = store.with_read_only(True)
            assert view.read_only is True
            assert store.read_only is False
            assert read_bytes(view, 'tree/key') == b'replaced'
            for entry, args in [(put_bytes, (view, 'tree/key', b'bad')),
                                (put_bytes, (view, 'new', b'bad')),
                                (view.delete, ('tree/key',)), (view.delete_dir, ('tree',))]:
                with pytest.raises(ValueError):
                    invoke(entry, *args)
                assert read_bytes(store, 'tree/key') == b'replaced'
                assert read_bytes(store, 'tree/nested/value') == b'child'
                assert read_bytes(store, 'new') is None
            put_bytes(store, 'later', b'still writable')
            assert read_bytes(view, 'later') == b'still writable'
            invoke(store.delete, 'tree/key')
            assert read_bytes(store, 'tree/key') is None
            assert read_bytes(store, 'tree/nested/value') == b'child'
            invoke(store.delete_dir, 'tree')
            assert listed(store.list) == {'treehouse/key', 'later'}
            assert read_bytes(store, 'treehouse/key') == b'sibling'
            assert read_bytes(store, 'later') == b'still writable'
        finally:
            if view is not None:
                view.close()
            store.close()


def test_f03_t05(tmp_path):
    path = tmp_path / 'no-deletes.zip'
    store = invoke(ZipStore.open, path, call_kwargs={'mode': 'w'}).value
    try:
        put_bytes(store, 'keep/item', b'archive-data')
        assert read_bytes(store, 'keep/item') == b'archive-data'
        assert store.supports_deletes is False
        a = velnora.create_array(store=store, name='numbers', shape=(2,), chunks=(2,),
                              dtype='int32', fill_value=0, compressors=None)
        a[:] = [5, 8]
        np.testing.assert_array_equal(a[:], [5, 8])
        for entry, args in [(store.delete, ('keep/item',)), (store.delete_dir, ('keep',)),
                            (a.__setitem__, (slice(None), [0, 0]))]:
            with pytest.raises(NotImplementedError):
                invoke(entry, *args)
            assert read_bytes(store, 'keep/item') == b'archive-data'
            np.testing.assert_array_equal(a[:], [5, 8])
    finally:
        store.close()
    with zipfile.ZipFile(path) as archive:
        assert archive.read('keep/item') == b'archive-data'
    reopened = invoke(ZipStore.open, path, call_kwargs={'mode': 'r'}).value
    try:
        np.testing.assert_array_equal(velnora.open_array(reopened, path='numbers')[:], [5, 8])
        assert reopened.read_only is True
        with pytest.raises(ValueError):
            put_bytes(reopened, 'keep/other', b'refused')
        assert read_bytes(reopened, 'keep/other') is None
    finally:
        reopened.close()


def test_f03_t06(tmp_path):
    path = tmp_path / 'custom.sqlite'
    store = SQLiteStore(path)
    try:
        put_bytes(store, 'raw/value', b'custom-0123456789')
        assert read_bytes(store, 'raw/value', RangeByteRequest(7, 11)) == b'0123'
        assert read_bytes(store, 'raw/value', OffsetByteRequest(12)) == b'56789'
        assert read_bytes(store, 'raw/value', SuffixByteRequest(3)) == b'789'
        assert listed(store.list_prefix, 'raw/') == {'raw/value'}
        assert listed(store.list_dir, '') == {'raw'}
        a = velnora.create_array(store=store, name='numbers', shape=(5,), chunks=(2,),
                              dtype='int32', compressors=None)
        a[:] = [9, -12, 27, 3, 16]
        np.testing.assert_array_equal(velnora.open_array(store, path='numbers')[:], [9, -12, 27, 3, 16])
        with sqlite3.connect(path) as independent:
            assert independent.execute('SELECT value FROM entries WHERE key = ?', ('raw/value',)).fetchone()[0] == b'custom-0123456789'
        limited = SQLiteStore(path, supports_deletes=False)
        try:
            with pytest.raises(NotImplementedError):
                invoke(limited.delete_dir, 'raw')
            restricted = velnora.open_array(limited, path='numbers')
            np.testing.assert_array_equal(restricted[:], [9, -12, 27, 3, 16])
            with pytest.raises(NotImplementedError):
                restricted[:] = [0, 0, 0, 0, 0]
            np.testing.assert_array_equal(a[:], [9, -12, 27, 3, 16])
        finally:
            limited.close()
        # A real database failure must reach callers on both public paths.
        store.connection.close()
        with pytest.raises(sqlite3.ProgrammingError):
            read_bytes(store, 'raw/value')
        with pytest.raises(sqlite3.ProgrammingError):
            a[:]
    finally:
        store.close()


def test_f03_t07(tmp_path):
    import obstore
    from obstore.store import S3Store
    from velnora.core.sync import sync

    # Remote sessions and synchronous array operations share one live loop.
    def read(store, key):
        value = sync(store.get(key, default_buffer_prototype()))
        return None if value is None else value.to_bytes()

    def write(store, key, payload):
        sync(store.set(key, default_buffer_prototype().buffer.from_bytes(payload)))

    # Distinct service lifetimes and locations make endpoint and prefix selection
    # observable without depending on the product's reported configuration.
    for service_number in range(2):
        with s3_service(tmp_path / f's3-{service_number}') as (endpoint, access_key, secret_key, independent):
            connection = {
                'endpoint_url': endpoint, 'key': access_key, 'secret': secret_key,
                'client_kwargs': {'region_name': 'us-east-1'},
                'config_kwargs': {'connect_timeout': 2, 'read_timeout': 5,
                                  'retries': {'max_attempts': 0}},
                'skip_instance_cache': True,
            }
            bucket = 'suite-' + uuid.uuid4().hex
            independent.create_bucket(Bucket=bucket)
            for adapter in ('filesystem', 'object'):
                prefix = adapter + '-' + uuid.uuid4().hex
                location = bucket + '/' + prefix
                payload = bytes([service_number, 0, 255]) + uuid.uuid4().bytes
                independent.put_object(Bucket=bucket, Key=prefix + '/seed', Body=payload[::-1])

                def provider(*, target=endpoint, anonymous=False):
                    return S3Store(
                        bucket, prefix=prefix, endpoint=target,
                        access_key_id=access_key, secret_access_key=secret_key,
                        region='us-east-1', skip_signature=anonymous,
                        client_options={'allow_http': True, 'connect_timeout': '2s', 'timeout': '5s'},
                        retry_config={'max_retries': 0},
                    )

                def open_store(*, target=endpoint, anonymous=False):
                    if adapter == 'filesystem':
                        options = dict(connection, endpoint_url=target, anon=anonymous)
                        return FsspecStore.from_url('s3://' + location, storage_options=options, read_only=False)
                    return ObjectStore(provider(target=target, anonymous=anonymous), read_only=False)

                def independently_read(key):
                    # Use the other implementation of the S3 client protocol.
                    if adapter == 'filesystem':
                        return bytes(obstore.get(provider(), key).bytes())
                    response = independent.get_object(Bucket=bucket, Key=prefix + '/' + key)
                    with response['Body'] as body:
                        return body.read()

                writer = open_store()
                try:
                    assert read(writer, 'seed') == payload[::-1]
                    write(writer, 'written', payload)
                    array = velnora.create_array(
                        writer, name='array', shape=(5,), chunks=(2,),
                        dtype='int32', compressors=None,
                    )
                    expected = np.array([17, -23, 41, service_number + 6, 12], dtype='int32')
                    array[:] = expected
                finally:
                    writer.close()
                assert independently_read('written') == payload

                reader = open_store()
                try:
                    assert read(reader, 'written') == payload
                    np.testing.assert_array_equal(velnora.open_array(reader, path='array', mode='r')[:], expected)
                finally:
                    reader.close()

                # A bound, non-listening socket gives a known unreachable local
                # endpoint without depending on any unrelated service or network.
                with bound_tcp_socket('127.0.0.1') as unavailable:
                    wrong_endpoint = f'http://127.0.0.1:{unavailable.getsockname()[1]}'
                    for options in ({'target': wrong_endpoint}, {'anonymous': True}):
                        failed_store = None
                        try:
                            with pytest.raises(Exception) as failure:
                                failed_store = open_store(**options)
                                write(failed_store, 'written', b'must-not-replace')
                            # An execution watchdog is an environment/test failure,
                            # never evidence of the product reporting a refusal.
                            assert not isinstance(failure.value, ExecutionTimeout)
                        finally:
                            if failed_store is not None:
                                failed_store.close()
                        assert independently_read('written') == payload
