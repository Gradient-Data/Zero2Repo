# feature: F19
"""Bounded real HTTP clients and caller-owned server lifecycle probes."""
import http.client
import socket
import ssl
import threading
from contextlib import contextmanager
from urllib.parse import urlsplit

from _helpers import invoke, bound_tcp_socket
from F03_helpers import put_bytes
from velnora.storage import MemoryStore
from velnora_http_server import serve_background, store_app


def http_exchange(url, path='/payload', method='GET', body=None, headers=None,
                  *, chunked=False, tls_context=None):
    address = urlsplit(url)
    if address.scheme == 'https':
        connection = http.client.HTTPSConnection(address.hostname, address.port,
                                                 timeout=20, context=tls_context)
    else:
        assert address.scheme == 'http', 'Expected an HTTP endpoint'
        connection = http.client.HTTPConnection(address.hostname, address.port, timeout=20)
    try:
        connection.request(method, path, body=body, headers=headers or {}, encode_chunked=chunked)
        response = connection.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        connection.close()


@contextmanager
def live_http(app, **options):
    server = invoke(serve_background, app, call_kwargs={'port': 0, **options}).value
    try:
        yield server
    finally:
        invoke(server.shutdown, timeout=20)


def assert_endpoint_released(url):
    address = urlsplit(url)
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((address.hostname, address.port))
        sock.listen(1)


def header_members(headers, name):
    return {part.strip().lower() for part in headers[name].split(',')}


def stalled_shutdown_probe():
    """A blocked ASGI exit must stop serving or report a visible failure."""
    store = MemoryStore()
    put_bytes(store, 'payload', b'live before shutdown')
    product = store_app(store)
    release = threading.Event()

    async def application(scope, receive, send):
        if scope['type'] != 'lifespan':
            return await product(scope, receive, send)
        assert (await receive())['type'] == 'lifespan.startup'
        await send({'type': 'lifespan.startup.complete'})
        assert (await receive())['type'] == 'lifespan.shutdown'
        release.wait(15)
        await send({'type': 'lifespan.shutdown.complete'})

    server = serve_background(application, port=0, shutdown_timeout=1)
    try:
        assert http_exchange(server.url)[::2] == (200, b'live before shutdown')
        try:
            result = server.shutdown()
        except RuntimeError:
            # A visible inability to stop is a supported failure form.
            pass
        else:
            # A server able to force shutdown has fulfilled the same promise.
            assert result is None
            assert_endpoint_released(server.url)
    finally:
        release.set()
        server.shutdown()
    assert_endpoint_released(server.url)
