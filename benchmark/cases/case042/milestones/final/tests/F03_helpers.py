# feature: F03
"""Real storage adapters and bounded observations for storage acceptance."""
import functools
import http.server
import sqlite3
import threading
import urllib.error
import urllib.request
import uuid
from contextlib import closing, contextmanager

from _helpers import invoke, bound_tcp_socket, make_env, running_process, wait_until
from velnora.abc.store import Store, RangeByteRequest, OffsetByteRequest, SuffixByteRequest
from velnora.core.buffer import default_buffer_prototype


def put_bytes(store, key, data):
    return invoke(store.set, key, default_buffer_prototype().buffer.from_bytes(data)).value


def read_bytes(store, key, request=None):
    value = invoke(store.get, key, default_buffer_prototype(),
                   call_kwargs={'byte_range': request}).value
    return None if value is None else value.to_bytes()


def listed(entry, *args):
    return set(invoke(entry, *args, consume=True).value)


@contextmanager
def s3_service(directory):
    """Run an isolated real MinIO service backed by a caller-owned directory."""
    from botocore.config import Config
    from botocore.exceptions import ClientError
    from botocore.session import get_session

    directory.mkdir()
    access_key = 'suite-' + uuid.uuid4().hex
    secret_key = uuid.uuid4().hex
    # MinIO accepts a port number, not an inherited listening socket. Each test
    # container has its own network namespace; a bind conflict still fails.
    with bound_tcp_socket('127.0.0.1') as reservation:
        port = reservation.getsockname()[1]
    endpoint = f'http://127.0.0.1:{port}'
    environment = make_env({
        'MINIO_ROOT_USER': access_key, 'MINIO_ROOT_PASSWORD': secret_key,
        'MINIO_BROWSER': 'off', 'MINIO_UPDATE': 'off',
    })
    with (directory / 'server.log').open('w+') as log:
        with running_process(
            ['minio', 'server', str(directory / 'objects'),
             '--address', f'127.0.0.1:{port}', '--console-address', '127.0.0.1:0'],
            stdout=log, stderr=log, env=environment, lifetime=180,
        ) as process:
            def ready():
                if process.poll() is not None:
                    raise RuntimeError('Owned S3 service exited: ' +
                                       (directory / 'server.log').read_text())
                try:
                    with urllib.request.urlopen(endpoint + '/minio/health/ready', timeout=1) as response:
                        return response.status == 200
                except urllib.error.HTTPError as exc:
                    if exc.code != 503:
                        raise
                    return False
                except urllib.error.URLError as exc:
                    if not isinstance(exc.reason, ConnectionRefusedError):
                        raise
                    return False
            wait_until(ready, timeout=30)
            with closing(get_session().create_client(
                's3', endpoint_url=endpoint, aws_access_key_id=access_key,
                aws_secret_access_key=secret_key, region_name='us-east-1',
                config=Config(connect_timeout=2, read_timeout=5, retries={'max_attempts': 0}),
            )) as client:
                def storage_ready():
                    try:
                        client.list_buckets()
                    except ClientError as exc:
                        if exc.response['Error']['Code'] != 'XMinioServerNotInitialized':
                            raise
                        return False
                    return True
                wait_until(storage_ready, timeout=30)
                yield endpoint, access_key, secret_key, client


@contextmanager
def served_directory(directory, *, required_headers=None):
    class HeaderCheckedHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if any(self.headers.get(name) != value
                   for name, value in (required_headers or {}).items()):
                self.send_error(403)
                return
            super().do_GET()

        def do_HEAD(self):
            if any(self.headers.get(name) != value
                   for name, value in (required_headers or {}).items()):
                self.send_error(403)
                return
            super().do_HEAD()

    handler = functools.partial(HeaderCheckedHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), 'Owned HTTP server did not stop'


class SQLiteStore(Store):
    """A caller-owned, durable SQL byte store implementing the public protocol.

    This adapter really saves payloads in SQLite. It is not a simulated product
    store, and its database can be queried independently of Velnora.
    """
    supports_writes = True
    supports_deletes = True
    supports_listing = True

    def __init__(self, path, *, read_only=False, supports_deletes=True):
        super().__init__(read_only=read_only)
        self.path = path
        self.supports_deletes = supports_deletes
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute('CREATE TABLE IF NOT EXISTS entries (key TEXT PRIMARY KEY, value BLOB NOT NULL)')
        self.connection.commit()

    def __eq__(self, other):
        return isinstance(other, SQLiteStore) and self.path == other.path

    def with_read_only(self, read_only=False):
        return type(self)(self.path, read_only=read_only, supports_deletes=self.supports_deletes)

    async def get(self, key, prototype, byte_range=None):
        row = self.connection.execute('SELECT value FROM entries WHERE key = ?', (key,)).fetchone()
        if row is None:
            return None
        data = row[0]
        if isinstance(byte_range, RangeByteRequest):
            data = data[byte_range.start:byte_range.end]
        elif isinstance(byte_range, OffsetByteRequest):
            data = data[byte_range.offset:]
        elif isinstance(byte_range, SuffixByteRequest):
            data = data[-byte_range.suffix:]
        elif byte_range is not None:
            raise TypeError('Unsupported byte request')
        return prototype.buffer.from_bytes(data)

    async def get_partial_values(self, prototype, key_ranges):
        return [await self.get(key, prototype, request) for key, request in key_ranges]

    async def exists(self, key):
        return self.connection.execute('SELECT 1 FROM entries WHERE key = ?', (key,)).fetchone() is not None

    async def set(self, key, value):
        if self.read_only:
            raise ValueError('Store is read-only')
        self.connection.execute('INSERT OR REPLACE INTO entries VALUES (?, ?)', (key, value.to_bytes()))
        self.connection.commit()

    async def delete(self, key):
        if self.read_only:
            raise ValueError('Store is read-only')
        if not self.supports_deletes:
            raise NotImplementedError('Deletion is unsupported')
        self.connection.execute('DELETE FROM entries WHERE key = ?', (key,))
        self.connection.commit()

    async def list(self):
        for (key,) in self.connection.execute('SELECT key FROM entries').fetchall():
            yield key

    async def list_prefix(self, prefix):
        async for key in self.list():
            if key.startswith(prefix):
                yield key

    async def list_dir(self, prefix):
        prefix = prefix.rstrip('/')
        prefix = prefix + '/' if prefix else ''
        children = set()
        async for key in self.list_prefix(prefix):
            children.add(key[len(prefix):].split('/')[0])
        for child in children:
            yield child

    def close(self):
        self.connection.close()
