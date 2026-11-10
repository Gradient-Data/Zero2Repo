# feature: F00
"""Public-interface machinery with no product expectations.

velnora is the normally installed public package root, shared by feature suites.
In-process deadlines require POSIX timers and the main thread. Use isolated
processes for native blocking calls or other platforms. Byte offsets in canvas
observations are not screen columns; geometry is read directly from the canvas.
"""
import contextlib as _contextlib
import io as _io
import math as _math
import os as _os
import signal as _signal
import subprocess as _subprocess
import tempfile as _tempfile
import threading as _threading
import time as _time
from dataclasses import dataclass as _dataclass
from pathlib import Path as _Path

import velnora


class HelperFailure(AssertionError):
    """Driver failure, never a product answer or exit status; causes are chained."""


class _DeadlineEscalation(BaseException):
    """Repeated expiry after a suppressed one; converted to HelperFailure."""


def _seconds(value):
    value = float(value)
    if not _math.isfinite(value) or value <= 0:
        raise ValueError("timeout or interval must be finite and positive")
    return value


@_contextlib.contextmanager
def deadline(timeout=5.0):
    """Yield None; expiry raises HelperFailure and other errors propagate.

    No exit status is produced. Requires POSIX interval timers on the main
    thread; existing timers are refused, not displaced. Restores the prior
    handler. Native calls that cannot be interrupted require process isolation.
    """
    timeout = _seconds(timeout)
    if not hasattr(_signal, "setitimer"):
        raise RuntimeError("In-process deadlines require POSIX timers")
    if _threading.current_thread() is not _threading.main_thread():
        raise RuntimeError("In-process deadlines require the main thread")
    if _signal.getitimer(_signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError("An interval timer is active; avoid nested deadlines")
    previous = _signal.getsignal(_signal.SIGALRM)
    fired = []

    def expired(signum, frame):
        # Product code may catch Exception around a blocking call and swallow
        # the first expiry; the timer repeats and later expiries are raised as
        # a BaseException so the deadline still ends the scope.
        fired.append(True)
        if len(fired) == 1:
            raise HelperFailure("Operation exceeded its wall-clock deadline")
        raise _DeadlineEscalation()

    _signal.signal(_signal.SIGALRM, expired)
    try:
        _signal.setitimer(_signal.ITIMER_REAL, timeout, 0.5)
        yield
    except _DeadlineEscalation as exc:
        raise HelperFailure("Operation exceeded its wall-clock deadline; "
                            "an earlier expiry was suppressed") from exc
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, previous)


@_dataclass(frozen=True)
class CallResult:
    """Value, Python stdout/stderr strings and original captured exception.

    error is None on success; value is None on captured failure. There is no
    exit status. Only caller-selected product exceptions are captured.
    """
    value: object
    stdout: str
    stderr: str
    error: object


def capture_call(entry, *args, consume=None, catch=(), timeout=5.0, **kwargs):
    """Return CallResult, optionally consuming a lazy result within the capture.

    Pass list as consume to exhaust an iterator, or a caller-defined consumer
    for nested lazy values. Only exception types explicitly listed in catch
    are returned as original exception objects; other exceptions propagate.
    HelperFailure always propagates. Captures Python streams, not native file
    descriptor writes. No process exit status is synthesized.
    """
    stdout, stderr = _io.StringIO(), _io.StringIO()
    value, error = None, None
    with deadline(timeout):
        with _contextlib.redirect_stdout(stdout), _contextlib.redirect_stderr(stderr):
            try:
                value = entry(*args, **kwargs)
                if consume is not None:
                    value = consume(value)
            except HelperFailure:
                raise
            except catch as exc:
                value, error = None, exc
    return CallResult(value, stdout.getvalue(), stderr.getvalue(), error)


def run_process(command, *, input=None, cwd=None, env=None, timeout=10.0):
    """Return CompletedProcess with byte stdout/stderr and actual returncode.

    command is an argv sequence, never shell code; input is bytes or None for
    EOF. cwd defaults to the product working directory. env is a full mapping
    or None to inherit. Nonzero exits remain results. Launch, timeout or cleanup
    failures raise HelperFailure with the original cause. Cleanup kills only
    this child, bounds reaping to two seconds and closes its captured pipes.
    """
    timeout = _seconds(timeout)
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be an argv sequence")
    command = tuple(command)
    if not command:
        raise ValueError("command must not be empty")
    if input is not None and not isinstance(input, bytes):
        raise TypeError("input must be bytes or None")
    try:
        process = _subprocess.Popen(command, stdin=_subprocess.PIPE,
                                    stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
                                    cwd=cwd, env=env)
    except OSError as exc:
        raise HelperFailure("Unable to launch requested command") from exc
    try:
        try:
            stdout, stderr = process.communicate(input=input, timeout=timeout)
        except _subprocess.TimeoutExpired as exc:
            raise HelperFailure("Command exceeded its wall-clock deadline") from exc
        return _subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        try:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2.0)
        except (OSError, _subprocess.TimeoutExpired) as exc:
            raise HelperFailure("Unable to terminate or reap requested command") from exc
        finally:
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()


def environment(overrides=None, *, remove=(), base=None):
    """Return a copied child environment without modifying this process.

    Copy os.environ or explicit base, remove names, then apply overrides.
    Missing removal targets are harmless; invalid mappings raise normally.
    No process is run and no exit status is produced.
    """
    result = dict(_os.environ if base is None else base)
    for name in remove:
        result.pop(name, None)
    if overrides is not None:
        result.update(overrides)
    return result


@_contextlib.contextmanager
def temporary_directory(*, parent=None):
    """Yield a new Path, deleting only that directory on scope exit.

    Creation, body and cleanup errors propagate. No exit status is produced;
    files and their contents are supplied by the caller.
    """
    with _tempfile.TemporaryDirectory(dir=parent) as path:
        yield _Path(path)


@_contextlib.contextmanager
def resource_scope(*, cleanup_timeout=5.0):
    """Yield an ExitStack for cleanup callbacks on caller-owned resources.

    Cleanup runs in reverse registration order within a deadline. Failures
    propagate with exception context; no exit status is invented. Use outside
    other deadline scopes and register only resources created by the caller.
    """
    cleanup_timeout = _seconds(cleanup_timeout)
    stack = _contextlib.ExitStack()
    try:
        yield stack
    finally:
        with deadline(cleanup_timeout):
            stack.close()


def canvas_snapshot(canvas, *, timeout=5.0):
    """Return public text, content, cols, rows, cursor and expanded byte runs.

    The dict's text and content are fully materialized tuples, preserving all
    whitespace and original segments. attributes and charsets contain one
    value per content byte, independent of equivalent run segmentation. These
    are byte offsets, not screen columns. Geometry comes directly from public
    fields. Read errors propagate; expiry raises HelperFailure. No exit status.
    """
    with deadline(timeout):
        text = tuple(canvas.text)
        content = tuple(tuple(row) for row in canvas.content())
        attributes = tuple(tuple(attr for attr, cs, data in row for _ in data)
                           for row in content)
        charsets = tuple(tuple(cs for attr, cs, data in row for _ in data)
                         for row in content)
        return dict(text=text, content=content, attributes=attributes,
                    charsets=charsets, cols=canvas.cols(), rows=canvas.rows(),
                    cursor=canvas.cursor)


def send_keys(widget, size, keys, *, timeout=5.0):
    """Return sequential keypress results, including unhandled keys, as a tuple.

    No extra rendering or focus manipulation occurs. Product and iteration
    errors propagate; expiry raises HelperFailure. No exit status is produced.
    """
    with deadline(timeout):
        return tuple(widget.keypress(size, key) for key in keys)


def send_mouse(widget, size, events, *, focus, timeout=5.0):
    """Return sequential mouse_event results as a tuple without interpretation.

    Each event is (event_name, button, column, row); focus is caller-supplied.
    Product and iteration errors propagate; expiry raises HelperFailure.
    No exit status is produced.
    """
    with deadline(timeout):
        return tuple(widget.mouse_event(size, event, button, col, row, focus)
                     for event, button, col, row in events)


class CallbackRecorder:
    """Record actual callback invocations, returning a caller-supplied value.

    calls holds (args_tuple, kwargs_dict) entries, retaining argument identities.
    Nothing invokes callbacks artificially. Errors propagate; no exit status.
    """
    def __init__(self, *, return_value=None):
        """Initialize an empty record; return None and propagate allocation errors."""
        self.calls = []
        self.return_value = return_value

    def __call__(self, *args, **kwargs):
        """Record an invocation and return return_value; errors propagate unchanged."""
        self.calls.append((args, dict(kwargs)))
        return self.return_value


def wait_until(probe, *, timeout=5.0, interval=0.01):
    """Return the first truthy probe result within a bounded polling period.

    The caller defines readiness. False results are retried, never returned as
    success. Probe errors propagate immediately; expiry raises HelperFailure.
    No exit status is synthesized. Has deadline's platform/no-nesting limits.
    """
    interval = _seconds(interval)
    with deadline(timeout):
        while True:
            result = probe()
            if result:
                return result
            _time.sleep(interval)
