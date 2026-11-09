# feature: F05
"""Offline repositories serving real built distributions through public protocols."""
from contextlib import contextmanager
from F00_transport import ClientDisconnects
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import html
import json
import ssl
import sys
import threading
from urllib.parse import urlsplit

from packaging.utils import canonicalize_name, parse_wheel_filename

from _helpers import parse_metadata, read_zip, run_cli
from F01_helpers import BUILD_SYSTEM, succeeded, write_project
from F04_helpers import dependency_lock, locked_by_name


def source_project(path, sources=(), *, dependencies=(), bindings=""):
    document = ('[project]\nname="source-consumer"\nversion="1.0"\n'
                'requires-python=">=3.9"\ndependencies=' + json.dumps(list(dependencies)) + '\n'
                '[tool.<legacy>]\npackage-mode=false\n')
    if bindings:
        document += '[tool.<legacy>.dependencies]\n' + bindings + '\n'
    for name, url, priority in sources:
        document += '\n[[tool.<legacy>.source]]\nname=' + json.dumps(name) + '\n'
        if url is not None:
            document += 'url=' + json.dumps(url) + '\n'
        if priority is not None:
            document += 'priority=' + json.dumps(priority) + '\n'
    return write_project(path, document + BUILD_SYSTEM)


def source_lock(path, env):
    return locked_by_name(dependency_lock(path, env))


def source_rows(text):
    """Read blank-separated source records by their labels."""
    rows = []
    current = {}
    for line in (*text.splitlines(), ""):
        if not line.strip():
            if current:
                assert {"name", "priority"} <= current.keys(), text
                rows.append(current)
                current = {}
            continue
        label, separator, value = line.strip().partition(":")
        label = label.strip()
        if separator and label in {"name", "url", "priority"}:
            assert label not in current, text
            current[label] = value.strip()
    return rows


@contextmanager
def source_repository(wheels, *, style="html", python_requirements=None, tls=None):
    """Serve HTML/JSON simple, single-page and PyPI JSON APIs from wheel metadata.

    With tls, accept HTTPS CONNECT for the fixed PyPI origin. No outbound network
    connection is made; all package metadata describes the artifacts served here.
    """
    artifacts = {}
    releases = {}
    python_requirements = python_requirements or {}
    for wheel in wheels:
        payload = wheel.read_bytes()
        name, version, _, _ = parse_wheel_filename(wheel.name)
        members = read_zip(wheel)
        metadata, = [parse_metadata(value) for key, value in members.items()
                     if key.endswith('.dist-info/METADATA')]
        entry = {"filename": wheel.name, "payload": payload,
                 "sha256": hashlib.sha256(payload).hexdigest(),
                 "requires-python": python_requirements.get(wheel.name, metadata['Requires-Python']),
                 "metadata": metadata, "version": str(version), "name": str(name)}
        artifacts[wheel.name] = entry
        releases.setdefault(str(name), []).append(entry)
    errors = []
    state = {"requests": []}

    class Handler(ClientDisconnects, BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def respond(self, status, content, kind):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_CONNECT(self):
            assert tls is not None and self.path == 'pypi.org:443', self.path
            self.send_response(200)
            self.end_headers()
            self.connection = tls.wrap_socket(self.connection, server_side=True)
            self.rfile = self.connection.makefile('rb')
            self.wfile = self.connection.makefile('wb')
            self.close_connection = True
            self.handle_one_request()

        def do_GET(self):
            path = urlsplit(self.path).path
            state['requests'].append(path)
            base = 'https://pypi.org' if tls else state['url']

            def file_record(entry):
                return {'filename': entry['filename'], 'url': base + '/files/' + entry['filename'],
                        'hashes': {'sha256': entry['sha256']},
                        'requires-python': entry['requires-python'], 'yanked': False}

            if path.startswith('/files/') and path[7:] in artifacts:
                self.respond(200, artifacts[path[7:]]['payload'], 'application/octet-stream')
                return
            parts = path.strip('/').split('/')
            if len(parts) == 4 and parts[0] == 'pypi' and parts[3] == 'json':
                entries = [e for e in releases.get(parts[1], []) if e['version'] == parts[2]]
                if entries:
                    entry = entries[0]
                    metadata = entry['metadata']
                    content = {'info': {'name': metadata['Name'], 'version': metadata['Version'],
                               'summary': metadata['Summary'] or '',
                               'requires_python': metadata['Requires-Python'],
                               'requires_dist': metadata.get_all('Requires-Dist', []), 'yanked': False},
                               'urls': [dict(file_record(e), packagetype='bdist_wheel',
                                             digests={'sha256': e['sha256']}, size=len(e['payload']))
                                        for e in entries]}
                    self.respond(200, json.dumps(content).encode(), 'application/json')
                    return
            if path == '/links.html':
                entries = list(artifacts.values())
            elif len(parts) == 2 and parts[0] == 'simple':
                entries = releases.get(canonicalize_name(parts[1]), [])
            else:
                entries = []
            if not entries:
                self.respond(404, b'Not found', 'text/plain')
            elif style == 'json' and path != '/links.html':
                content = {'meta': {'api-version': '1.0'}, 'name': parts[1],
                           'files': [file_record(e) for e in entries]}
                self.respond(200, json.dumps(content).encode(), 'application/vnd.pypi.simple.v1+json')
            else:
                content = '\n'.join('<a href="' + html.escape(base + '/files/' + e['filename'])
                    + '#sha256=' + e['sha256'] + '" data-requires-python="'
                    + html.escape(e['requires-python'] or '', quote=True) + '">' + e['filename'] + '</a>'
                    for e in entries)
                self.respond(200, content.encode(), 'text/html')

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        def handle_error(self, request, address):
            errors.append(sys.exception())

    server = Server(('127.0.0.1', 0), Handler)
    state['url'] = f'http://127.0.0.1:{server.server_port}'
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), 'Repository failed to stop'
        assert not errors, errors


@contextmanager
def pypi_transport(root, env, wheels):
    """Trust a temporary certificate and route the public PyPI origin locally."""
    root.mkdir()
    succeeded(run_cli(('openssl',), ('req', '-x509', '-newkey', 'rsa:2048', '-nodes',
        '-days', '2', '-subj', '/CN=pypi.org', '-keyout', 'server.key', '-out', 'server.pem',
        '-addext', 'subjectAltName=DNS:pypi.org', '-addext', 'basicConstraints=critical,CA:TRUE'),
        cwd=root, env=env, timeout=30))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(root / 'server.pem', root / 'server.key')
    with source_repository(wheels, style='json', tls=context) as repository:
        routed = dict(env)
        for key in ('HTTP_PROXY', 'http_proxy', 'ALL_PROXY', 'all_proxy', 'https_proxy'):
            routed.pop(key, None)
        routed.update(HTTPS_PROXY=repository['url'], NO_PROXY='127.0.0.1,localhost',
                      no_proxy='127.0.0.1,localhost', REQUESTS_CA_BUNDLE=str(root / 'server.pem'))
        yield routed, repository
