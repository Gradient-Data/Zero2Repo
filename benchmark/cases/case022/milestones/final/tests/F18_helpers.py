# feature: F18
"""Fresh product sessions and independently metered source transport."""
import contextlib
import functools
import http.server
import threading
import time
import traceback
from pathlib import Path

from F17_helpers import persistence_session
from _helpers import run_python


def reuse_source_test(function):
    @functools.wraps(function)
    def execute(tmp_path):
        persistence_session(
            'from pathlib import Path\n'
            f'from F18_reuse import {function.__name__}\n'
            f'{function.__name__}.__wrapped__(Path(sys.argv[2]))\n', tmp_path)
    return execute


@contextlib.contextmanager
def metered_records_server(path):
    """Record completed full-body transfers, excluding disconnected probes.

    Large bodies sent in paced chunks distinguish clients consuming the file
    from existence probes closing after receiving response headers.
    """
    transfers = []
    server_errors = []

    class MeteredServer(http.server.ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            server_errors.append(traceback.format_exc())

    class RecordsHandler(http.server.BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.send_response(200)
            self.send_header('Content-Length', str(path.stat().st_size))
            self.end_headers()

        def do_GET(self):
            contents = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Length', str(len(contents)))
            self.end_headers()
            try:
                for start in range(0, len(contents), 16384):
                    time.sleep(0.001)
                    self.wfile.write(contents[start:start + 16384])
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                # HTTP clients may close without consuming a response body.
                return
            transfers.append(len(contents))

    server = MeteredServer(('127.0.0.1', 0), RecordsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/records.jsonl', transfers
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), 'Metered source server did not stop'
        assert not server_errors, '\n'.join(server_errors)


def recorded_affine(row, *, journal, factor, offset):
    with open(journal, 'a', encoding='utf-8') as stream:
        stream.write(str(row['value']) + '\n')
    return {'value': row['value'] * factor + offset}


def recorded_square(row, *, journal, factor, offset):
    with open(journal, 'a', encoding='utf-8') as stream:
        stream.write(str(row['value']) + '\n')
    return {'value': row['value'] ** 2 * factor + offset}


def prepared_result_effect(root):
    """Observe the preparation effect with source bytes already locally available.

    Initial same-process calibration on the read-only original: medians were
    0.719 s / 0.0104 s (ratio 0.0145), well below the public 0.5 threshold.
    The actual observation below uses fresh processes in both arms and passed
    original/reference runs. Absolute calibration times are not limits.
    """
    import json
    import statistics
    from velnora import load_dataset
    source = root / 'preparation-source.jsonl'
    payload = 'Field data: ' + 'r' * 244
    count = 400_000
    with source.open('w', encoding='utf-8') as stream:
        for index in range(count):
            stream.write(json.dumps({'id': index, 'payload': payload}) + '\n')
    probe = """
import json, sys, time
from velnora import load_dataset
started = time.perf_counter()
data = load_dataset('json', data_files=sys.argv[1], split='train', cache_dir=sys.argv[2])
elapsed = time.perf_counter() - started
count = len(data)
print(json.dumps({'elapsed': elapsed, 'count': count,
                  'rows': [data[index] for index in (0, count // 2, count - 1)]}))
"""
    samples = []
    for repeat in range(3):
        arguments = (str(source), str(root / f'preparation-cache-{repeat}'))
        pair = []
        for _ in range(2):
            result = run_python(probe, args=arguments, timeout=30)
            assert result.returncode == 0, result.stdout + result.stderr
            observation = json.loads(result.stdout)
            assert observation['count'] == count
            assert observation['rows'] == [
                {'id': index, 'payload': payload} for index in (0, count // 2, count - 1)]
            pair.append(observation['elapsed'])
        samples.append(pair)
    first, repeated = [statistics.median(pair[index] for pair in samples) for index in (0, 1)]
    print(json.dumps({'preparation_seconds': samples, 'median_first': first,
                      'median_repeated': repeated}), flush=True)
    assert repeated <= 0.5 * first, samples
