# feature: F19
"""Acceptance of store HTTP scope, bytes, permissions and managed serving."""
import hashlib
import signal
import ssl
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import velnora
from velnora.storage import MemoryStore, LocalStore
from velnora_http_server import CorsOptions, node_app, store_app, serve_background

from _helpers import (invoke, bound_tcp_socket, run_command, run_python,
                      running_process, wait_until, python_command)
from F03_helpers import put_bytes, read_bytes
from F07_helpers import array_storage_bytes
from F19_helpers import (http_exchange, live_http, assert_endpoint_released,
                         header_members)


def test_store_and_node_scope():
    store = MemoryStore()
    root = velnora.open_group(store, mode='w')
    group = root.create_group('selected')
    array = group.create_array('data', shape=(6,), chunks=(3,), dtype='i4')
    array[:] = [11, 12, 13, 21, 22, 23]
    root.create_group('sibling')
    for key in ('secret', 'selected/notes', 'selected/data/c/9',
                'selected/data/c/0/0'):
        put_bytes(store, key, b'protected:' + key.encode())
    with live_http(store_app(store)) as server:
        for key, expected in array_storage_bytes(store).items():
            status, _, body = http_exchange(server.url, '/' + key)
            assert (status, body) == (200, expected)
    for node, valid, invalid in (
        (group, 'data/c/0', ('notes', 'data/c/9', 'data/c/0/0',
                             'sibling/zarr.json', '..%2fsibling/zarr.json',
                             'data/..%2fnotes', 'data/c/7')),
        (array, 'c/0', ('notes', 'c/9', 'c/0/0', '..%2fnotes', 'c/7')),
    ):
        with live_http(node_app(node, methods={'GET', 'HEAD', 'PUT'})) as server:
            prefix = node.store_path.path
            for key in ('zarr.json', valid):
                assert http_exchange(server.url, '/' + key)[::2] == (
                    200, read_bytes(store, prefix + '/' + key))
            assert http_exchange(server.url, '/' + valid, 'PUT', b'new valid chunk')[0] == 204
            assert read_bytes(store, prefix + '/' + valid) == b'new valid chunk'
            before = array_storage_bytes(store)
            for key in invalid:
                assert http_exchange(server.url, '/' + key)[0] == 404
                assert http_exchange(server.url, '/' + key, 'HEAD')[0] == 404
                assert http_exchange(server.url, '/' + key, 'PUT', b'forbidden')[0] == 404
                assert array_storage_bytes(store) == before


def test_read_methods_and_write_permissions():
    store = MemoryStore()
    payload = b'bytes with\x00a non-text end\xff'
    put_bytes(store, 'payload', payload)
    with live_http(store_app(store)) as server:
        assert http_exchange(server.url)[::2] == (200, payload)
        status, headers, body = http_exchange(server.url, method='HEAD')
        assert status == 200 and body == b''
        assert int(headers['content-length']) == len(payload)
        for method in ('PUT', 'POST', 'DELETE', 'PATCH'):
            assert http_exchange(server.url, method=method, body=b'refused')[0] == 405
            assert read_bytes(store, 'payload') == payload
        assert http_exchange(server.url, '/missing')[0] == 404
    with live_http(store_app(store, methods={'GET', 'HEAD', 'PUT'})) as server:
        assert http_exchange(server.url, method='PUT', body=b'replaced')[0] == 204
        assert read_bytes(store, 'payload') == b'replaced'
        assert http_exchange(server.url)[::2] == (200, b'replaced')
    readonly = store.with_read_only(True)
    with pytest.raises(ValueError):
        store_app(readonly, methods={'GET', 'PUT'})
    with live_http(store_app(readonly)) as server:
        assert http_exchange(server.url)[::2] == (200, b'replaced')
    # Invalid configuration must be refused, including an unsupported operation
    # mixed into otherwise valid choices. No exception wording is prescribed.
    for factory, target in ((store_app, store), (node_app, velnora.create_group(MemoryStore()))):
        for methods in (set(), {'POST'}, {'GET', 'DELETE'}, {'HEAD', 'PATCH', 'PUT'}):
            with pytest.raises(ValueError):
                factory(target, methods=methods)
    # Each independent allowed operation works without implicitly enabling GET
    # or PUT. GET's documented implicit HEAD is checked in the same workload.
    for methods in ({'HEAD'}, {'GET'}, {'PUT'}, {'HEAD', 'PUT'}):
        put_bytes(store, 'payload', payload)
        with live_http(store_app(store, methods=methods)) as server:
            status, headers, body = http_exchange(server.url, method='HEAD')
            if methods & {'HEAD', 'GET'}:
                assert status == 200 and body == b''
                assert int(headers['content-length']) == len(payload)
            else:
                assert status == 405
            status, _, body = http_exchange(server.url)
            assert status == (200 if 'GET' in methods else 405)
            if 'GET' in methods:
                assert body == payload
            status, _, _ = http_exchange(server.url, method='PUT', body=b'only enabled writes')
            assert status == (204 if 'PUT' in methods else 405)
            assert read_bytes(store, 'payload') == (b'only enabled writes' if 'PUT' in methods else payload)


def test_single_byte_ranges():
    # Known RFC 9110 single-range examples on caller-owned bytes; no product parser.
    store = MemoryStore()
    payload = b'0123456789abcdefghij'
    put_bytes(store, 'payload', payload)
    put_bytes(store, 'empty', b'')
    with live_http(store_app(store)) as server:
        for header, start, end in (('bytes=3-7', 3, 7), ('bytes=12-', 12, 19),
                                   ('bytes=-4', 16, 19), ('bytes=17-99', 17, 19),
                                   ('bytes=-99', 0, 19)):
            status, headers, body = http_exchange(server.url, headers={'Range': header})
            assert status == 206
            assert body == payload[start:end + 1]
            assert int(headers['content-length']) == end - start + 1
            # The total length may be known or unknown in a single-part response.
            assert headers['content-range'] in (
                f'bytes {start}-{end}/*', f'bytes {start}-{end}/{len(payload)}')
        for path, header in (('/payload', 'bytes=20-'), ('/payload', 'bytes=-0'),
                             ('/empty', 'bytes=0-0'), ('/empty', 'bytes=-1')):
            assert http_exchange(server.url, path, headers={'Range': header})[0] == 416
        for header in ('items=0-3', 'bytes=nonsense', 'bytes=0-2,5-7'):
            status, headers, body = http_exchange(server.url, headers={'Range': header})
            assert (status, body) == (200, payload)
            assert int(headers['content-length']) == len(payload)


def test_body_size_limits(tmp_path):
    store = LocalStore(tmp_path / 'body-store')
    chunk = bytes(range(256)) * 4096
    limit = 268435456
    # Exact default boundary is exercised, rather than reading a reported constant.
    with live_http(store_app(store, methods={'GET', 'PUT'})) as server:
        status, _, _ = http_exchange(server.url, method='PUT',
            body=(chunk for _ in range(256)), headers={'Content-Length': str(limit)})
        assert status == 204
        actual = read_bytes(store, 'payload')
        expected_hash = hashlib.sha256()
        for _ in range(256):
            expected_hash.update(chunk)
        assert len(actual) == limit
        assert hashlib.sha256(actual).digest() == expected_hash.digest()
        del actual
        # Actual over-limit streamed bodies must not replace the old value.
        put_bytes(store, 'payload', b'preserve')
        assert http_exchange(server.url, method='PUT', body=iter([chunk] * 256 + [b'!']),
                             chunked=True)[0] == 413
        assert read_bytes(store, 'payload') == b'preserve'
    for maximum in (13, None):
        with live_http(store_app(store, methods={'GET', 'PUT'}, max_body_size=maximum)) as server:
            for chunked in (False, True):
                accepted = b'boundary-data'  # Thirteen request-body bytes.
                body = iter((accepted[:5], accepted[5:])) if chunked else accepted
                assert http_exchange(server.url, method='PUT', body=body, chunked=chunked)[0] == 204
                assert read_bytes(store, 'payload') == accepted
                oversized = accepted + b'!'
                body = iter((oversized[:5], oversized[5:])) if chunked else oversized
                expected_status = 204 if maximum is None else 413
                assert http_exchange(server.url, method='PUT', body=body, chunked=chunked)[0] == expected_status
                assert read_bytes(store, 'payload') == (oversized if maximum is None else accepted)
    # Lifting the cap must also lift the default, not merely a small custom cap.
    with live_http(store_app(store, methods={'PUT'}, max_body_size=None)) as server:
        assert http_exchange(server.url, method='PUT', body=(
            part for part in [chunk] * 256 + [b'!']), chunked=True)[0] == 204
        actual = read_bytes(store, 'payload')
        expected_hash.update(b'!')
        assert len(actual) == limit + 1
        assert hashlib.sha256(actual).digest() == expected_hash.digest()


def test_browser_cross_origin_policy():
    store = MemoryStore()
    put_bytes(store, 'payload', b'cors payload')
    origin = 'https://reader.example'
    def preflight(url, method='GET', header='Range', source=origin):
        return http_exchange(url, method='OPTIONS', headers={
            'Origin': source, 'Access-Control-Request-Method': method,
            'Access-Control-Request-Headers': header})
    options = CorsOptions(allow_origins=[origin], allow_credentials=True)
    with live_http(store_app(store, cors_options=options)) as server:
        status, headers, body = http_exchange(server.url, headers={'Origin': origin})
        assert (status, body) == (200, b'cors payload')
        assert headers['access-control-allow-origin'] == origin
        assert headers['access-control-allow-credentials'] == 'true'
        assert 'content-range' in header_members(headers, 'access-control-expose-headers')
        status, headers, _ = preflight(server.url)
        assert status == 200
        assert headers['access-control-allow-origin'] == origin
        assert 'range' in header_members(headers, 'access-control-allow-headers')
        assert preflight(server.url, source='https://other.example')[0] == 400
        assert preflight(server.url, method='PUT')[0] == 400
    for methods in ({'GET'}, {'GET', 'HEAD', 'PUT'}):
        with live_http(store_app(store, methods=methods, cors_options=CorsOptions(
            allow_origins=[origin], allow_methods=['*'], allow_headers=['X-Token'],
            expose_headers=['X-Result']))) as server:
            status, headers, _ = preflight(server.url, header='X-Token')
            assert status == 200
            assert header_members(headers, 'access-control-allow-methods') == {
                m.lower() for m in methods | {'HEAD'}}
            assert 'x-token' in header_members(headers, 'access-control-allow-headers')
            assert preflight(server.url)[0] == 400
            status, headers, body = http_exchange(server.url, headers={'Origin': origin})
            assert (status, body) == (200, b'cors payload')
            assert header_members(headers, 'access-control-expose-headers') == {'x-result'}
    with pytest.raises(ValueError):
        store_app(store, cors_options=CorsOptions(allow_methods=['PUT']))


def test_foreground_and_background_lifetime(tmp_path):
    store = MemoryStore()
    put_bytes(store, 'payload', b'background live')
    server = invoke(serve_background, store_app(store), call_kwargs={'port': 0}).value
    try:
        assert http_exchange(server.url)[::2] == (200, b'background live')
    finally:
        assert invoke(server.shutdown).value is None
    assert_endpoint_released(server.url)
    with bound_tcp_socket('127.0.0.1') as reservation:
        port = reservation.getsockname()[1]
    report = tmp_path / 'returned'
    code = '''import sys, signal
signal.signal(signal.SIGTERM, lambda signum, frame: None)
from velnora.storage import MemoryStore
from velnora.buffer import cpu
from velnora.core.sync import sync
from velnora_http_server import store_app, serve
store = MemoryStore()
sync(store.set('payload', cpu.buffer_prototype.buffer.from_bytes(b'foreground live')))
serve(store_app(store), port=int(sys.argv[1]))
open(sys.argv[2], 'w').write('returned')
'''
    with (tmp_path / 'stdout').open('w') as out, (tmp_path / 'stderr').open('w') as err:
        with running_process(python_command(code, [str(port), str(report)]),
                             stdout=out, stderr=err) as process:
            url = f'http://127.0.0.1:{port}'
            def ready():
                assert process.poll() is None, (
                    'Foreground server exited before stopping:\n' +
                    (tmp_path / 'stderr').read_text())
                try:
                    return http_exchange(url)[::2] == (200, b'foreground live')
                except ConnectionRefusedError:
                    return False
            try:
                wait_until(ready)
            except BaseException as exc:
                exc.add_note('Foreground stderr:\n' + (tmp_path / 'stderr').read_text())
                raise
            assert not report.exists()
            process.send_signal(signal.SIGTERM)
            assert process.wait(timeout=15) == 0
            assert report.read_text() == 'returned'
    assert_endpoint_released(url)


def test_port_selection_and_conflict():
    # casebox gives this test an isolated container network namespace.
    store = MemoryStore()
    put_bytes(store, 'payload', b'port selection live')
    with bound_tcp_socket('127.0.0.1') as occupied:
        occupied.listen(1)
        port = occupied.getsockname()[1]
        with pytest.raises(RuntimeError):
            invoke(serve_background, store_app(store), call_kwargs={'port': port})
    with live_http(store_app(store), port=port) as server:
        assert urlsplit(server.url).port == port
        assert http_exchange(server.url)[::2] == (200, b'port selection live')
    with live_http(store_app(store), port='auto') as server:
        assert urlsplit(server.url).port == 8000
        assert http_exchange(server.url)[::2] == (200, b'port selection live')
    with bound_tcp_socket('127.0.0.1', 8000) as occupied:
        occupied.listen(1)
        with live_http(store_app(store), port='auto') as server:
            assert urlsplit(server.url).port != 8000
            assert http_exchange(server.url)[::2] == (200, b'port selection live')
    with live_http(store_app(store), port=0) as server:
        assert 1 <= urlsplit(server.url).port <= 65535
        assert http_exchange(server.url)[::2] == (200, b'port selection live')


def test_tls_and_non_network_socket(tmp_path):
    cert, key = tmp_path / 'cert.pem', tmp_path / 'key.pem'
    result = run_command(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                          '-keyout', str(key), '-out', str(cert), '-days', '1',
                          '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1'])
    result.check_returncode()
    store = MemoryStore()
    put_bytes(store, 'payload', b'encrypted and unix socket bytes')
    context = ssl.create_default_context(cafile=str(cert))
    with live_http(store_app(store), uvicorn_options={
            'ssl_certfile': str(cert), 'ssl_keyfile': str(key)}) as server:
        assert urlsplit(server.url).scheme == 'https'
        assert http_exchange(server.url, tls_context=context)[::2] == (
            200, b'encrypted and unix socket bytes')
    import httpx
    path = str(tmp_path / 'http.sock')
    with live_http(store_app(store), uvicorn_options={'uds': path}) as server:
        assert server.url is None
        with httpx.Client(transport=httpx.HTTPTransport(uds=path), timeout=10) as client:
            response = client.get('http://localhost/payload')
            assert (response.status_code, response.content) == (200, b'encrypted and unix socket bytes')


def test_context_exit_and_stalled_shutdown():
    store = MemoryStore()
    put_bytes(store, 'payload', b'context managed bytes')
    with serve_background(store_app(store), port=0) as server:
        assert http_exchange(server.url)[::2] == (200, b'context managed bytes')
        url = server.url
    assert_endpoint_released(url)
    with pytest.raises(LookupError):
        with serve_background(store_app(store), port=0) as server:
            assert http_exchange(server.url)[::2] == (200, b'context managed bytes')
            url = server.url
            raise LookupError('Caller failure')
    assert_endpoint_released(url)
    result = run_python('from F19_helpers import stalled_shutdown_probe\nstalled_shutdown_probe()', timeout=25, cwd=Path(__file__).parent)
    result.check_returncode()
