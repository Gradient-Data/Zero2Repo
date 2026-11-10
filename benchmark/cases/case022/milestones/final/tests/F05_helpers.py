# feature: F05
"""Real local repositories and loopback HTTP file transport."""
import contextlib
import functools
import http.server
import json
import threading
import time
import traceback
from pathlib import Path

import yaml
from velnora import load_dataset

from _helpers import deadline


def write_records(root, relative, values):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps({'value': value}) + '\n' for value in values), encoding='utf-8')
    return str(path)


def write_card(root, configs, *, dataset_info=None):
    root.mkdir(parents=True, exist_ok=True)
    metadata = {'configs': configs}
    if dataset_info is not None:
        metadata['dataset_info'] = dataset_info
    (root / 'README.md').write_text('---\n' + yaml.safe_dump(metadata) + '---\n', encoding='utf-8')


def loaded_members(path, **kwargs):
    with deadline(60):
        result = load_dataset(str(path), **kwargs)
        return {name: sorted(row['value'] for row in split) for name, split in result.items()}


@contextlib.contextmanager
def serve_files(root, *, authorization=None, transfers=None):
    server_errors = []

    class FileServer(http.server.ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            server_errors.append(traceback.format_exc())

    class FileHandler(http.server.SimpleHTTPRequestHandler):
        def authorized(self):
            if authorization is None or self.headers.get('Authorization') == authorization:
                return True
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="dataset"')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return False

        def do_HEAD(self):
            if self.authorized():
                super().do_HEAD()

        def do_GET(self):
            if self.authorized():
                super().do_GET()

        def copyfile(self, source, outputfile):
            if transfers is None:
                return super().copyfile(source, outputfile)
            name = Path(self.translate_path(self.path)).name
            try:
                while chunk := source.read(16384):
                    outputfile.write(chunk)
                    transfers[name] = transfers.get(name, 0) + len(chunk)
                    outputfile.flush()
                    # Pace real transfers so a headers-only client can close
                    # without the server queuing the entire source in advance.
                    time.sleep(0.001)
            except (BrokenPipeError, ConnectionResetError):
                return

    handler = functools.partial(FileHandler, directory=str(root))
    server = FileServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), 'HTTP server did not stop'
        assert not server_errors, '\n'.join(server_errors)


def constrained_streaming_prefixes(root):
    """Read real HTTP sources larger than the chosen temporary filesystem.

    The reader uses a separate process and a real limited-capacity filesystem;
    the source server counts bytes externally and aborts excessive transfers.
    No product counters, logs or prepared-cache layout are observed.
    Original calibration on a 64 MiB temporary filesystem transferred about
    40.3 MiB of 256 MiB raw JSONL, 30.1 MiB of 195.4 MiB gzip JSONL, and
    15.1 MiB of that same gzip stream as text, below the quarter-source bound.
    This calibrates reserve only; every run measures its own real sources.
    """
    import base64
    import gzip
    import os
    import subprocess
    import sys
    import tempfile
    import time
    import traceback
    from pathlib import Path

    temporary_root = Path('/dev/shm')
    assert temporary_root.is_dir(), 'Streaming resource check requires /dev/shm'
    volume = os.statvfs(temporary_root)
    capacity = volume.f_blocks * volume.f_frsize
    available = volume.f_bavail * volume.f_frsize
    assert 16 * 1024**2 <= available and capacity <= 128 * 1024**2, (
        'Streaming resource check requires at least 16 MiB free on a filesystem of at most 128 MiB')
    # A block exceeds compression history size; repeating it does not turn the
    # compressed source into a tiny file that a valid prefetch could read whole.
    records = [{'value': index, 'text': base64.b64encode(os.urandom(1024)).decode('ascii')}
               for index in range(256)]
    block = ''.join(json.dumps(row) + '\n' for row in records).encode('utf-8')
    repetitions = (256 * 1024**2 + len(block) - 1) // len(block)
    raw = root / 'large.jsonl'
    with raw.open('wb') as stream:
        for _ in range(repetitions):
            stream.write(block)
    compressed = root / 'large.jsonl.gz'
    with gzip.open(compressed, 'wb', compresslevel=1) as stream, raw.open('rb') as source:
        while chunk := source.read(1024**2):
            stream.write(chunk)
    assert min(raw.stat().st_size, compressed.stat().st_size) > capacity
    # The same compressed byte stream is also a valid line-oriented text input.
    expected = {'json': records[:3], 'text': [
        {'text': json.dumps(row)} for row in records[:3]]}
    observations = []
    for reader, source in [('json', raw), ('json', compressed), ('text', compressed)]:
        observed = {'bytes': 0}
        server_errors = []

        class MeteredServer(http.server.ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                server_errors.append(traceback.format_exc())

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_HEAD(self, source=source):
                self.send_response(200)
                self.send_header('Content-Length', str(source.stat().st_size))
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()

            def do_GET(self, source=source, observed=observed):
                size = source.stat().st_size
                start, stop = 0, size
                requested = self.headers.get('Range')
                if requested:
                    unit, bounds = requested.split('=', 1)
                    assert unit == 'bytes' and ',' not in bounds
                    first, last = bounds.split('-', 1)
                    if first:
                        start = int(first)
                        if last:
                            stop = min(size, int(last) + 1)
                    else:
                        start = max(0, size - int(last))
                    if not 0 <= start < stop <= size:
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{size}')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                self.send_response(206 if requested else 200)
                self.send_header('Content-Length', str(stop - start))
                self.send_header('Accept-Ranges', 'bytes')
                if requested:
                    self.send_header('Content-Range', f'bytes {start}-{stop - 1}/{size}')
                self.end_headers()
                try:
                    with source.open('rb') as stream:
                        stream.seek(start)
                        remaining = stop - start
                        while remaining:
                            chunk = stream.read(min(64 * 1024, remaining))
                            assert chunk, 'Source ended before its declared byte range'
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            observed['bytes'] += len(chunk)
                            remaining -= len(chunk)
                            time.sleep(0.001)
                except (BrokenPipeError, ConnectionResetError):
                    # Clients may close a genuine HTTP response after a prefix.
                    return

        server = MeteredServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix='F05-stream-', dir=temporary_root) as scratch:
                directory = Path(scratch)
                environment = dict(os.environ, TMPDIR=scratch, TMP=scratch, TEMP=scratch,
                                   HF_HOME=str(directory / 'home'),
                                   HF_VELNORA_CACHE=str(directory / 'cache'),
                                   HF_HUB_CACHE=str(directory / 'hub'),
                                   XDG_CACHE_HOME=str(directory / 'xdg'))
                program = '''
import faulthandler, itertools, json, sys
faulthandler.dump_traceback_later(30, repeat=True)
from velnora import load_dataset
result = load_dataset(sys.argv[1], data_files=sys.argv[2], split='train', streaming=True,
                      cache_dir=sys.argv[3])
print(json.dumps(list(itertools.islice(result, 3))))
'''
                with tempfile.TemporaryFile(mode='w+') as output, tempfile.TemporaryFile(mode='w+') as errors:
                    process = subprocess.Popen([sys.executable, '-c', program, reader,
                        f'http://127.0.0.1:{server.server_port}/{source.name}', str(directory / 'cache')],
                        stdout=output, stderr=errors, env=environment)
                    expires = time.monotonic() + 180
                    try:
                        while process.poll() is None:
                            assert observed['bytes'] <= source.stat().st_size / 4, (
                                'Incremental prefix retrieval exceeded a quarter of the full source', observed)
                            if time.monotonic() >= expires:
                                errors.seek(0)
                                raise AssertionError('Incremental reader exceeded its observation interval: '
                                                     + errors.read())
                            time.sleep(0.005)
                        output.seek(0)
                        errors.seek(0)
                        content, diagnostics = output.read(), errors.read()
                        assert process.returncode == 0, content + diagnostics
                        assert json.loads(content) == expected[reader]
                        assert observed['bytes'] <= source.stat().st_size / 4, observed
                        observations.append({'reader': reader, 'source_bytes': source.stat().st_size,
                                             'transferred_bytes': observed['bytes'],
                                             'filesystem_capacity': capacity, 'initial_free': available})
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=10)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            assert not thread.is_alive(), 'Streaming source server did not stop'
            assert not server_errors, '\n'.join(server_errors)
    return observations
