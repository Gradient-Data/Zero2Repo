# feature: F14
"""Independent OS observations and external events for keyword workflows."""
from _helpers import write_file
from F07_helpers import utility_run

OS_OBSERVER = r'''
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from velun.api.deco import keyword
VELUN_AUTO_KEYWORDS = False
_events = ThreadPoolExecutor(max_workers=1)

@keyword(types=None)
def disk_bytes(path):
    return Path(path).read_bytes()

@keyword(types=None)
def disk_tree(path):
    root = Path(path)
    return {str(p.relative_to(root)): (None if p.is_dir() else p.read_bytes())
            for p in root.rglob('*')}

@keyword(types=None)
def disk_exists(path):
    return Path(path).exists()

@keyword(types=None)
def child_environment(name):
    result = subprocess.run([sys.executable, '-c',
        'import os,sys,json; print(json.dumps(os.environ.get(sys.argv[1])))', name],
        capture_output=True, text=True, timeout=10, check=True)
    import json
    return json.loads(result.stdout)

@keyword(types=None)
def begin_event(path, action, delay):
    target = Path(path)
    assert target.exists() == (action == 'remove')
    def change():
        time.sleep(float(delay))
        started = time.monotonic()
        if action == 'create':
            target.write_bytes(b'external event')
        elif action == 'remove':
            target.unlink()
        else:
            raise ValueError(action)
        return started
    return _events.submit(change)

@keyword(types=None)
def event_completed(future, path, action):
    returned = time.monotonic()
    # The filesystem transition can be visible before the worker publishes its
    # result. Check state before joining, so joining cannot conceal an early wait.
    assert Path(path).exists() == (action == 'create'), 'Wait returned before the requested filesystem state.'
    # Timestamp before the operation: its return and Future completion can both
    # follow a correct wait's return. Reap the worker and propagate its errors.
    assert future.result(timeout=5) <= returned, 'Wait returned before the external event began.'

@keyword(types=None)
def clock_now():
    return time.monotonic()

@keyword(types=None)
def elapsed_at_least(start, duration):
    assert time.monotonic() - start >= float(duration)

@keyword(types=None)
def elapsed_at_most(start, duration):
    assert time.monotonic() - start <= float(duration)

@keyword(types=None)
def mtime_is(path, expected):
    # Compare with the same filesystem's representation of the requested time.
    path = Path(path)
    probe = path.parent / 'timestamp-resolution-probe'
    probe.write_bytes(b'probe')
    try:
        os.utime(probe, (float(expected), float(expected)))
        assert path.stat().st_mtime_ns == probe.stat().st_mtime_ns
    finally:
        probe.unlink()

@keyword(types=None)
def begin_touch():
    return time.time()

@keyword(types=None)
def touched_since(path, before):
    stamp = Path(path).stat().st_mtime
    # Whole-second tolerance permits filesystems with coarse timestamp storage.
    assert int(before) - 1 <= stamp <= time.time() + 1
'''


def os_run(directory, cases, failures=()):
    write_file(directory / 'OSObserver.py', OS_OBSERVER)
    names = [line for line in cases.splitlines() if line and not line[0].isspace()]
    root = utility_run(
        directory, cases.replace('@ROOT@', str(directory)),
        {name: 'FAIL' if name in failures else 'PASS' for name in names},
        settings='Library    OperatingSystem\nLibrary    OSObserver.py\n')
    # Every declared case was executed and recorded exactly once.
    assert sorted(t.attrib['name'] for t in root.findall('.//test')) == sorted(names)
    return root
