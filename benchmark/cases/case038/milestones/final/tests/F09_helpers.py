# feature: F09
"""Real offline loopback file services for resource acceptance tests.

F09_pyftpdlib.zip vendors unmodified pyftpdlib 2.1.0 Python sources and license
from https://files.pythonhosted.org/packages/source/p/pyftpdlib/pyftpdlib-2.1.0.tar.gz.
The archive also includes unmodified pyasyncore 1.0.4 and pyasynchat 1.0.4
wheels (including licenses), its Python 3.12+ compatibility dependencies.
The archive is a test dependency, never a substitute product implementation.
"""
import contextlib
import functools
import http.server
import pathlib
import sys
import threading


def xpath_string(text):
    """Encode a Python string as an XPath string literal without changing it."""
    return "'" + text.replace("'", "''") + "'"


@contextlib.contextmanager
def http_files(directory):
    """Serve actual files and record each received GET path, including failures."""
    requests = []

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            super().do_GET()

        def log_message(self, format, *args):
            pass

    handler = functools.partial(Handler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .03})
    thread.start()
    try:
        yield 'http://127.0.0.1:%d/' % server.server_port, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
        assert not thread.is_alive(), 'HTTP server failed to stop'


@contextlib.contextmanager
def ftp_files(directory):
    """Serve actual files with the vendored, unmodified FTP server library."""
    archive = str(pathlib.Path(__file__).with_name('F09_pyftpdlib.zip'))
    sys.path.insert(0, archive)
    try:
        from pyftpdlib.authorizers import DummyAuthorizer
        from pyftpdlib.handlers import FTPHandler
        from pyftpdlib.ioloop import IOLoop
        from pyftpdlib.servers import FTPServer
    finally:
        sys.path.remove(archive)

    authorizer = DummyAuthorizer()
    authorizer.add_anonymous(str(directory), perm='elr')

    class Handler(FTPHandler):
        pass

    Handler.authorizer = authorizer
    loop = IOLoop()
    server = FTPServer(('127.0.0.1', 0), Handler, ioloop=loop)
    port = server.socket.getsockname()[1]
    stop = threading.Event()
    errors = []

    def run():
        try:
            while not stop.is_set():
                server.serve_forever(timeout=.03, blocking=False, handle_exit=False)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        yield 'ftp://127.0.0.1:%d/' % port
    finally:
        stop.set()
        thread.join(5)
        assert not thread.is_alive(), 'FTP server failed to stop'
        server.close_all()
        loop.close()
        if errors:
            raise errors[0]
