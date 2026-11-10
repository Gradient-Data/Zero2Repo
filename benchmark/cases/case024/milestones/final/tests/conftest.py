# feature: F00
"""Run each complete pytest node in a bounded, forked process tree.

Forking the whole setup/call/teardown protocol preserves local definitions,
fixture objects, mutations and exception identity inside the test. Only pytest
reports cross the boundary, never product objects or exceptions. The existing
per-invocation deadlines still apply. A ten-minute node ceiling also bounds
native calls, fixture hangs and code that catches the invocation timeout.
"""
import ctypes
import os
import pickle
import select
import signal
import tempfile
import time
import traceback

import pytest
from _pytest.runner import runtestprotocol
from _pytest.reports import TestReport

_NODE_TIMEOUT = 600.0
_CLEANUP_TIMEOUT = 5.0


def _processes():
    """Read Linux parent relationships; tolerate only processes exiting mid-read."""
    parents = {}
    for name in os.listdir('/proc'):
        if name.isdecimal():
            try:
                with open('/proc/' + name + '/stat') as stream:
                    fields = stream.read().rsplit(')', 1)[1].split()
                parents[int(name)] = int(fields[1])
            except (FileNotFoundError, ProcessLookupError):
                continue
    return parents


def _kill_tree(worker, existing_children):
    """Kill/reap only this node's descendants, including adopted session leaders."""
    deadline = time.monotonic() + _CLEANUP_TIMEOUT
    owned = {worker}
    while True:
        parents = _processes()
        # Subreaper adoption retains ownership when a product parent exits first.
        owned.update(pid for pid, parent in parents.items()
                     if parent == os.getpid() and pid not in existing_children)
        while True:
            descendants = {pid for pid, parent in parents.items() if parent in owned}
            if descendants <= owned:
                break
            owned.update(descendants)
        for pid in owned:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for pid in owned:
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass  # Descendants are reaped only after adoption by this process.
        remaining = _processes()
        if not (owned & remaining.keys()):
            return
        if time.monotonic() >= deadline:
            raise RuntimeError('Test worker process-tree cleanup exceeded five seconds')
        time.sleep(0.01)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    # Linux is the benchmark runtime. Failure to establish containment is fatal.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    existing = {pid for pid, parent in _processes().items() if parent == os.getpid()}
    item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
    with tempfile.TemporaryFile() as payload:
        reader, writer = os.pipe()
        worker = os.fork()
        if worker == 0:
            os.close(reader)
            try:
                os.setsid()
                # nextitem=None ensures even session fixtures finalize in this node.
                reports = runtestprotocol(item, log=False, nextitem=None)
                pickle.dump(reports, payload)
                payload.flush()
                os.write(writer, b'R')
                # Keep ancestry intact until the coordinator cleans up the tree.
                while True:
                    signal.pause()
            except BaseException:
                # Serialize infrastructure diagnostics too; never turn them into
                # an empty or successful test outcome. Keep descendants owned.
                payload.seek(0)
                payload.truncate()
                pickle.dump([TestReport(
                    nodeid=item.nodeid, location=item.location, keywords={},
                    outcome='failed', longrepr=traceback.format_exc(),
                    when='call', sections=[], duration=0.0)], payload)
                payload.flush()
                os.write(writer, b'R')
                while True:
                    signal.pause()
        os.close(writer)
        started = time.monotonic()
        try:
            ready = select.select([reader], [], [], _NODE_TIMEOUT)[0]
            status = os.read(reader, 1) if ready else b''
            if status == b'R':
                payload.seek(0)
                reports = pickle.load(payload)
            else:
                reason = ('Test node exceeded its process deadline' if not ready
                          else 'Test worker exited before returning pytest reports')
                reports = [TestReport(
                    nodeid=item.nodeid, location=item.location, keywords={},
                    outcome='failed', longrepr=reason, when='call',
                    sections=[], duration=time.monotonic() - started)]
        finally:
            os.close(reader)
            _kill_tree(worker, existing)
        for report in reports:
            item.ihook.pytest_runtest_logreport(report=report)
    item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
    return True
