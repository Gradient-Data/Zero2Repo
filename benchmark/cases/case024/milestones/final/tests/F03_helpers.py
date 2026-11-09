# feature: F03
"""Independent disk observations and real loopback HTTP service for file tests.

Object-storage services live in F03_services.object_store."""
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import os
import ssl
import subprocess


def disk_contents(root):
    """Read relative file locations and bytes independently of the product."""
    root = Path(root)
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob('*') if path.is_file()}


def move_mtime(path):
    """Change only modification time by a representable interval."""
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000_000))
    assert path.stat().st_mtime_ns != stat.st_mtime_ns


@contextmanager
def serve_files(root, *, certificate=None, key=None):
    """Serve actual disk files through the standard library HTTP server."""
    server = ThreadingHTTPServer(('127.0.0.1', 0),
                                 partial(SimpleHTTPRequestHandler, directory=str(root)))
    if certificate is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        scheme = 'https' if certificate is not None else 'http'
        yield scheme + '://127.0.0.1:' + str(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), 'HTTP service did not terminate'


def create_tls_certificate(root):
    """Create a real, independently trusted certificate for the loopback server."""
    certificate, key = root / 'certificate.pem', root / 'key.pem'
    subprocess.run([
        'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
        '-keyout', str(key), '-out', str(certificate), '-days', '1',
        '-subj', '/CN=127.0.0.1', '-addext', 'subjectAltName=IP:127.0.0.1',
    ], check=True, capture_output=True, timeout=30)
    return certificate, key
