# feature: F13
"""Real transfer fixtures and transparent HTTP write observations."""
import contextlib
import http.client
import http.server
from pathlib import Path
import threading
from urllib.parse import urlsplit

from _helpers import read_bytes, write_file
from F01_helpers import cli_success, named_node
from F02_helpers import recipe_client, recipe_file
from F03_helpers import attach_repositories, recipe_repository, revision_publisher
from F04_helpers import protected_repository
from F06_helpers import binary_reference
from F12_helpers import selection, saved_selection


@contextlib.contextmanager
def transfer_observer(upstream):
    target = urlsplit(upstream)
    records, failures = [], []

    class Forward(http.server.BaseHTTPRequestHandler):
        def forward(self):
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=120)
            try:
                if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
                    chunks = []
                    while True:
                        size = int(self.rfile.readline().split(b';', 1)[0], 16)
                        if size == 0:
                            while True:
                                trailer = self.rfile.readline()
                                assert trailer, 'Truncated HTTP trailers'
                                if trailer == b'\r\n':
                                    break
                            break
                        chunk = self.rfile.read(size)
                        assert len(chunk) == size, 'Truncated HTTP chunk'
                        assert self.rfile.read(2) == b'\r\n', 'Malformed HTTP chunk'
                        chunks.append(chunk)
                    body = b''.join(chunks)
                else:
                    body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                headers = {key: value for key, value in self.headers.items()
                           if key.lower() not in ('transfer-encoding', 'content-length')}
                headers['Content-Length'] = str(len(body))
                headers['Host'] = target.netloc
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse()
                received = response.read()
                records.append(dict(method=self.command, path=self.path, status=response.status,
                                    sent=body, received=received))
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in ('connection', 'transfer-encoding', 'content-length'):
                        self.send_header(key, value)
                self.send_header('Content-Length', str(len(received)))
                self.end_headers()
                self.wfile.write(received)
            except BaseException as exc:
                failures.append(exc)
                raise
            finally:
                connection.close()

        do_GET = do_POST = do_PUT = do_DELETE = forward

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Forward)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), 'Transfer observer did not stop'
        assert not failures, failures


@contextlib.contextmanager
def transfer_world(root, count=1, protected=False):
    root = Path(root)
    seed = recipe_client(root / 'seed')
    with contextlib.ExitStack() as stack:
        upstreams = [stack.enter_context((protected_repository if protected else recipe_repository)(
            root / f'server-{i}', seed.env)) for i in range(count)]
        observed = [stack.enter_context(transfer_observer(url)) for url in upstreams]
        repositories = [(f'store{i}', entry[0]) for i, entry in enumerate(observed)]
        publisher = revision_publisher(root / 'publisher', repositories)
        yield publisher, repositories, [entry[1] for entry in observed]


def transfer_reader(root, repositories):
    client = recipe_client(root)
    attach_repositories(client, repositories)
    return client


def transfer_package(client, root, *, name='freight', build_type='Release', extra='', prefix=''):
    source = recipe_file(root, '''    settings = "build_type"
    exports_sources = "source.txt"
    exports = "recipe-data.txt"
    def build(self):
        import os
        if os.environ.get("F13_FORBID_BUILD"):
            raise RuntimeError("Unexpected build")
    def package(self):
        from velmora.tools.files import copy
        copy(self, "source.txt", self.source_folder, self.package_folder)
''' + extra, name=name, version='1.0')
    if prefix:
        write_file(source, prefix + source.read_text())
    write_file(source.parent / 'source.txt', name + ' source material\n')
    write_file(source.parent / 'recipe-data.txt', name + ' recipe material\n')
    report = cli_success(client, 'create', source.parent, '-nr', '-s',
                         'build_type=' + build_type, '--format=json').json('stdout')
    return named_node(report, name)


def transfer_path(client, reference, folder=None):
    flags = ('--folder=' + folder,) if folder else ()
    return Path(cli_success(client, 'cache', 'path', reference, *flags,
                            '--format=json').json('stdout')['cache_path'])


def assert_transferred(client, node, remote='store0', *, sources=True):
    cli_success(client, 'download', binary_reference(node), '-r', remote)
    name = node['name']
    assert read_bytes(transfer_path(client, binary_reference(node)) / 'source.txt') == (
        name + ' source material\n').encode()
    assert read_bytes(transfer_path(client, node['ref']) / 'recipe-data.txt') == (
        name + ' recipe material\n').encode()
    if sources:
        assert read_bytes(transfer_path(client, node['ref'], 'export_source') / 'source.txt') == (
            name + ' source material\n').encode()


def upload_report(client, *args, remote='store0'):
    return cli_success(client, 'upload', *args, '-r', remote, '-c', '--format=json').json('stdout')


def prepare_transfer(client, path, pattern='*', *, remote='store0'):
    report = upload_report(client, pattern, '--dry-run', remote=remote)
    saved_selection(path, report)
    return report


def artifact_writes(records):
    return [r for r in records if r['method'] == 'PUT' and r['sent'] and 200 <= r['status'] < 300]


def remote_snapshot(client, remote='store0'):
    return selection(client, '*#*:*#*', '-r', remote)[remote]


def recipe_bundle(report, node, remote='store0'):
    ref, revision = node['ref'].split('#')
    return report[remote][ref]['revisions'][revision]
