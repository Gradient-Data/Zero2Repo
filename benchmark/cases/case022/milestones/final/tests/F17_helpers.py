# feature: F17
"""Fresh-session persistence observations and logical export sources."""
from pathlib import Path
from contextlib import contextmanager

from _helpers import run_python
from F04_helpers import iterable_records


def persistence_session(source, *args):
    result = run_python(
        "import sys\nsys.path.insert(0, '/app/src')\n"
        "sys.path.insert(0, sys.argv[1])\n" + source,
        args=(str(Path(__file__).parent), *map(str, args)), timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def export_records():
    return [
        {'id': 31, 'text': 'cedar,river', 'value': 1.25},
        {'id': 7, 'text': 'a "quoted" line\nnext', 'value': -2.5},
        {'id': 23, 'text': '你好', 'value': 0.0},
        {'id': 11, 'text': 'last', 'value': 8.75},
    ]


def csv_values(rows):
    """Read CSV cells as export_records() values; numeric spelling is free."""
    return [{'id': int(row['id']), 'text': row['text'], 'value': float(row['value'])} for row in rows]


def export_sources(records):
    from velnora import Dataset
    # A non-contiguous view tests logical order rather than physical storage.
    physical = records[1:] + records[:1]
    finite = Dataset.from_list(physical).select([len(records) - 1, *range(len(records) - 1)])
    return finite, iterable_records(records)


@contextmanager
def authenticated_ftp(root):
    """Run a real FTP server with a private account and independent client."""
    import ftplib
    import socket
    import subprocess
    import sys
    import time
    import uuid
    username, password = 'acceptance', uuid.uuid4().hex
    wheel = Path(__file__).parent / 'resources' / 'F17' / 'F17_pyftpdlib.whl'
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    source = '''
import sys
from pathlib import Path
assets = Path(sys.argv[1]).parent
sys.path[:0] = [str(assets / name) for name in ('F17_pyftpdlib.whl', 'F17_pyasynchat.whl', 'F17_pyasyncore.whl')]
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
authorizer = DummyAuthorizer()
authorizer.add_user(sys.argv[4], sys.argv[5], sys.argv[2], perm='elradfmwMT')
FTPHandler.authorizer = authorizer
FTPHandler.auth_failed_timeout = 0
FTPServer(('127.0.0.1', int(sys.argv[3])), FTPHandler).serve_forever()
'''
    with (root / 'ftp-server.log').open('w+') as log:
        process = subprocess.Popen([sys.executable, '-c', source, str(wheel), str(root),
                                    str(port), username, password], stdout=log, stderr=log)
        client = ftplib.FTP()
        try:
            expires = time.monotonic() + 15
            while True:
                if process.poll() is not None or time.monotonic() >= expires:
                    log.seek(0)
                    raise AssertionError('FTP server did not start:\n' + log.read())
                try:
                    client.connect('127.0.0.1', port, timeout=2)
                    break
                except ConnectionRefusedError:
                    time.sleep(0.05)
            client.login(username, password)
            yield f'ftp://127.0.0.1:{port}', {'host': '127.0.0.1', 'port': port, 'username': username, 'password': password, 'timeout': 10}, client
        finally:
            client.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def prepare_memory_dataset(root, count, payload_size=8192):
    """Prepare a real saved dataset outside the measured reader process."""
    import numpy as np
    import pyarrow as pa
    from velnora import Dataset
    path = root / f'input-{payload_size}-{count}.arrow'
    schema = pa.schema([('id', pa.int64()), ('payload', pa.binary(payload_size))])
    with pa.OSFile(str(path), 'wb') as sink:
        with pa.ipc.new_stream(sink, schema) as writer:
            for start in range(0, count, 64000):
                stop = min(start + 64000, count)
                writer.write_batch(pa.record_batch([
                    pa.array(np.arange(start, stop, dtype=np.int64())),
                    pa.array([b'x' * payload_size] * (stop - start), type=pa.binary(payload_size)),
                ], schema=schema))
    source = Dataset.from_file(str(path))
    destination = root / f'saved-{payload_size}-{count}'
    source.save_to_disk(destination, num_shards=1)
    del source
    path.unlink()
    return destination


def measure_disk_reader(path, count, resident_budget, payload_size=8192):
    """Enforce a resident-memory budget externally and sample live reader RSS.

    The child waits at both ends of the public operation, so even very short
    calls have an external resident observation. All errors and exits fail.
    The budget is a sampled RSS watchdog, not Linux's unenforced RLIMIT_RSS.
    """
    import os
    import selectors
    import subprocess
    import sys
    import tempfile
    import time
    import psutil
    source = '''
import sys
sys.path.insert(0, '/app/src')
from velnora import load_from_disk
print('ready', flush=True)
assert sys.stdin.readline() == 'go\\n'
data = load_from_disk(sys.argv[1])
count = int(sys.argv[2])
for start in (0, count // 2, count - 4):
    rows = data[start:start + 4]
    assert rows == {'id': list(range(start, start + 4)), 'payload': [b'x' * int(sys.argv[3])] * 4}
assert len(data) == count
print('done', flush=True)
assert sys.stdin.readline() == 'exit\\n'
'''
    # Readiness and completion are harness synchronization, never evidence of
    # dataset content; the child asserts every requested row independently.
    with tempfile.TemporaryFile(mode='w+') as errors:
        process = subprocess.Popen([sys.executable, '-c', source, str(path), str(count), str(payload_size)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=errors, text=True, bufsize=1,
                                   env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'))
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        probe = psutil.Process(process.pid)
        baseline = None
        anonymous_baseline = None
        anonymous_peak = 0
        peak = 0
        finished = False
        expires = time.monotonic() + 90
        try:
            while not finished:
                if process.poll() is not None:
                    errors.seek(0)
                    raise AssertionError('Reader exited before completion:\n' + errors.read())
                if time.monotonic() >= expires:
                    raise AssertionError('Reader exceeded the bounded observation interval')
                rss = probe.memory_info().rss
                if rss > resident_budget:
                    raise AssertionError(f'Reader exceeded resident budget: {rss} > {resident_budget}; baseline={baseline}, rows={count}')
                if baseline is not None:
                    peak = max(peak, rss)
                for key, _ in selector.select(timeout=0.002):
                    line = key.fileobj.readline()
                    anonymous = next(int(line.split()[1]) * 1024 for line in Path(f'/proc/{process.pid}/smaps_rollup').read_text().splitlines() if line.startswith('Anonymous:'))
                    if baseline is None:
                        anonymous_baseline = anonymous
                        assert line == 'ready\n', repr(line)
                        baseline = probe.memory_info().rss
                        peak = baseline
                        process.stdin.write('go\n')
                        process.stdin.flush()
                    else:
                        assert line == 'done\n', repr(line)
                        peak = max(peak, probe.memory_info().rss)
                        anonymous_peak = anonymous
                        finished = True
            process.stdin.write('exit\n')
            process.stdin.flush()
            process.wait(timeout=10)
            errors.seek(0)
            assert process.returncode == 0, errors.read()
            return {'baseline': baseline, 'peak': peak, 'growth': peak - baseline,
                    'anonymous_growth': max(0, anonymous_peak - anonymous_baseline)}
        finally:
            selector.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            process.stdin.close()
            process.stdout.close()
