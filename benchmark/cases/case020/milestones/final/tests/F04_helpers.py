# feature: F04
"""Real repository observations for remote selection and authentication."""
import configparser
import contextlib
import http.client
import http.server
from pathlib import Path
import ssl
import threading
from urllib.parse import urlsplit

from _helpers import PRODUCT_PYTHON, environment, read_bytes, run, service_process, write_file
from F01_helpers import cli_rejection, cli_success, named_node
from F02_helpers import recipe_file
from F03_helpers import recipe_repository


def remote_rows(client):
    return cli_success(client, 'remote', 'list', '--format=json').json('stdout')


def remote_users(client):
    rows = cli_success(client, 'remote', 'list-users', '--format=json').json('stdout')
    return {row['name']: row for row in rows}


def remote_graph(client, reference, *args, operation='graph', rejected=False):
    command = ('graph', 'info') if operation == 'graph' else ('install',)
    invoke = cli_rejection if rejected else cli_success
    result = invoke(client, *command, '--requires=' + reference, '--format=json', *args)
    return result.json('stdout')


def missing_remote_recipe(client, reference, *args):
    report = remote_graph(client, reference, *args, rejected=True)
    error = report['graph']['error']
    assert error['type'] == 'missing', error
    assert error['require']['ref'].partition('#')[0] == reference.partition('#')[0], error
    return report


def publish_remote_package(client, root, remote, *, name='cargo', marker='payload'):
    source = recipe_file(root,
                         f'    description = {marker!r}\n'
                         '    exports_sources = "payload.txt"\n'
                         '    def package(self):\n'
                         '        from velmora.tools.files import copy\n'
                         '        copy(self, "payload.txt", self.source_folder, self.package_folder)\n',
                         name=name, version='1.0')
    write_file(source.parent / 'payload.txt', marker)
    cli_success(client, 'create', source.parent, '-nr')
    cli_success(client, 'upload', name + '/1.0', '-r', remote, '-c')
    return name + '/1.0'


def assert_remote_install(client, reference, marker, *args):
    report = remote_graph(client, reference, *args, operation='install')
    node = named_node(report, reference.split('/')[0])
    assert node['description'] == marker
    assert read_bytes(Path(node['package_folder']) / 'payload.txt') == marker.encode()
    return node


@contextlib.contextmanager
def protected_repository(root, env):
    """Reuse the existing server fixture's configuration, then restart with ACLs."""
    root = Path(root)
    with recipe_repository(root, env) as url:
        pass
    parser = configparser.ConfigParser()
    parser.read(root / 'server.conf')
    parser['read_permissions']['*/*@*/*'] = 'publisher'
    parser['users']['outsider'] = 'outsider-password'
    with (root / 'server.conf').open('w') as stream:
        parser.write(stream)
    address = urlsplit(url)

    def ready(remaining):
        connection = http.client.HTTPConnection(address.hostname, address.port,
                                                timeout=min(remaining, 1))
        try:
            try:
                connection.request('GET', '/v1/ping')
                response = connection.getresponse()
                response.read()
                return response.status == 200
            except (ConnectionRefusedError, TimeoutError, http.client.RemoteDisconnected):
                return False
        finally:
            connection.close()

    with service_process('F04-protected-' + root.name,
                         (PRODUCT_PYTHON, '-m', 'velmoras.server.server_launcher'),
                         cwd=root, env=environment(env, updates={'VELMORA_SERVER_HOME': str(root)}),
                         probe=ready):
        yield url


@contextlib.contextmanager
def repository_observer(upstream, *, certificate=None, key=None):
    """Forward actual HTTP requests unchanged and retain real protocol outcomes."""
    target = urlsplit(upstream)
    records = []
    failures = []

    class Forward(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=120)
            try:
                headers = dict(self.headers)
                headers['Host'] = target.netloc
                connection.request(self.command, self.path, headers=headers)
                response = connection.getresponse()
                body = response.read()
                records.append({'path': self.path, 'status': response.status, 'body': body})
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in ('connection', 'transfer-encoding', 'content-length'):
                        self.send_header(name, value)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except BaseException as exc:
                failures.append(exc)
                raise
            finally:
                connection.close()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Forward)
    server.daemon_threads = True
    if certificate is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
    thread.start()
    try:
        scheme = 'https' if certificate is not None else 'http'
        yield f'{scheme}://127.0.0.1:{server.server_port}', records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), 'Repository observer failed to stop'
        assert not failures, failures


def tls_certificate(root, env):
    root = Path(root)
    root.mkdir(parents=True)
    cert, key = root / 'certificate.pem', root / 'key.pem'
    result = run(('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
                  '-keyout', str(key), '-out', str(cert), '-subj', '/CN=127.0.0.1',
                  '-addext', 'subjectAltName=IP:127.0.0.1'), cwd=root, env=env)
    assert result.returncode == 0, result
    return cert, key
