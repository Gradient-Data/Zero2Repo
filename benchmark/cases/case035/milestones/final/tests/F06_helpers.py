# feature: F06
"""Release-policy metadata for real artifacts and semantic lock observations."""
from contextlib import contextmanager
from F00_transport import ClientDisconnects
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import sys
import threading
from urllib.parse import urlsplit

from packaging.markers import default_environment
from packaging.utils import canonicalize_name, parse_wheel_filename

from F01_helpers import succeeded, project_cli
from F04_helpers import dependency_lock, locked_by_name, lock_marker_applies


@contextmanager
def release_policy_repository(entries):
    """Serve real wheels with repository-authored withdrawal and upload metadata.

    Each entry is (wheel, metadata); multiple artifacts per release are retained.
    No product responses are fabricated or product functions replaced.
    """
    artifacts = {}
    projects = {}
    for wheel, metadata in entries:
        name, _, _, _ = parse_wheel_filename(wheel.name)
        payload = wheel.read_bytes()
        artifacts[wheel.name] = payload
        projects.setdefault(str(name), []).append({
            'filename': wheel.name, 'url': '/files/' + wheel.name,
            'hashes': {'sha256': hashlib.sha256(payload).hexdigest()}, **metadata})
    errors = []

    class Handler(ClientDisconnects, BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            parts = path.strip('/').split('/')
            if len(parts) == 2 and parts[0] == 'simple' and parts[1] in projects:
                payload = json.dumps({'meta': {'api-version': '1.0'}, 'name': parts[1],
                                      'files': projects[parts[1]]}).encode()
                status, kind = 200, 'application/vnd.pypi.simple.v1+json'
            elif len(parts) == 2 and parts[0] == 'files' and parts[1] in artifacts:
                payload = artifacts[parts[1]]
                status, kind = 200, 'application/octet-stream'
            else:
                payload, status, kind = b'Not found', 404, 'text/plain'
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        def handle_error(self, request, address):
            errors.append(sys.exception())

    server = Server(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), 'Repository failed to stop'
        assert not errors, errors


def applicable_records(records, *, python, platform='linux', group='main'):
    """Evaluate the public lock's per-group marker with independent PEP 508 tools."""
    target = {**default_environment(), 'python_version': python,
              'python_full_version': python + '.0', 'sys_platform': platform, 'extra': ''}
    selected = {}
    for record in records:
        if group not in record['groups']:
            continue
        if not lock_marker_applies(record, target, group=group):
            continue
        name = canonicalize_name(record['name'])
        assert name not in selected, records
        selected[name] = record
    return selected


def configured_age(path, env, days, *, setting=None, exemption=None):
    succeeded(project_cli(path, env, 'config', '--local', 'solver.min-release-age', str(days)))
    if setting is not None:
        succeeded(project_cli(path, env, 'config', '--local', setting, exemption))
    return locked_by_name(dependency_lock(path, env))
