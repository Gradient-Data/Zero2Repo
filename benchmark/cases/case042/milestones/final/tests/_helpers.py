# feature: F00
"""Shared execution machinery, with no product imports or behavior checks.

Callers import documented public entries with ordinary Python imports and pass
them to ``invoke``. For import isolation, pass source containing those same plain
imports to ``run_python``. No entry point or product configuration is inferred.
In-process capture is for Python streams and is main-thread-only; use a child
process for native output, concurrent execution, or process-global isolation.
"""

import asyncio as _asyncio
import contextlib as _contextlib
import inspect as _inspect
import io as _io
import json as _json
import math as _math
import os as _os
import signal as _signal
import socket as _socket
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import threading as _threading
import time as _time
from dataclasses import dataclass as _dataclass
from pathlib import Path as _Path


class ExecutionTimeout(AssertionError):
    """A suite execution deadline, distinct from a product exception."""


@_dataclass(frozen=True)
class CallResult:
    """Return value and Python stdout/stderr from a completed call.

    There is no process exit status. Exceptions, including SystemExit, propagate
    unchanged with captured streams attached as an exception note.
    """

    value: object
    stdout: str
    stderr: str


def _seconds(value):
    value = float(value)
    if not _math.isfinite(value) or value <= 0:
        raise ValueError("Timeout must be finite and positive")
    return value


@_contextlib.contextmanager
def _deadline(timeout):
    timeout = _seconds(timeout)
    if _threading.current_thread() is not _threading.main_thread():
        raise RuntimeError("Use a subprocess for calls outside the main thread")
    previous_timer = _signal.getitimer(_signal.ITIMER_REAL)
    if previous_timer[1] != 0:
        raise RuntimeError("A periodic real-time timer prevents bounded execution")
    if previous_timer[0] and previous_timer[0] <= timeout:
        # The surrounding deadline is already stricter and remains active.
        yield
        return

    def expired(signum, frame):
        raise ExecutionTimeout(f"Execution exceeded {timeout} seconds")

    previous = _signal.signal(_signal.SIGALRM, expired)
    started = _time.monotonic()
    _signal.setitimer(_signal.ITIMER_REAL, timeout)
    try:
        yield
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, previous)
        if previous_timer[0]:
            remaining = previous_timer[0] - (_time.monotonic() - started)
            _signal.setitimer(_signal.ITIMER_REAL, max(remaining, 0.000001))


async def _resolve(value, consume, max_items):
    if _inspect.isawaitable(value):
        value = await value
    if not consume:
        return value
    items = []
    if hasattr(value, "__aiter__"):
        async for item in value:
            if len(items) >= max_items:
                raise AssertionError("Result consumption exceeded max_items")
            items.append(item)
    else:
        for item in value:
            if len(items) >= max_items:
                raise AssertionError("Result consumption exceeded max_items")
            items.append(item)
    return items


def invoke(entry, *args, timeout=30, consume=False, max_items=10000,
           input_text="", call_kwargs=None):
    """Return CallResult for a supplied synchronous or asynchronous callable.

    Pass product keyword arguments in call_kwargs. With consume=True, exhaust a
    finite sync/async iterable into a list within the same capture and deadline.
    stdin is input_text; Python stdout/stderr are captured. Original exceptions
    propagate with output notes; time/item limits raise AssertionError. No exit
    status is manufactured. An active event loop requires a subprocess instead.
    The deadline uses POSIX signals; uninterruptible native calls need a process.
    """
    if not isinstance(max_items, int) or isinstance(max_items, bool) or max_items < 0:
        raise ValueError("max_items must be a nonnegative integer")
    try:
        _asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("Use a subprocess when an event loop is already running")
    out, err = _io.StringIO(), _io.StringIO()
    previous_stdin = _sys.stdin
    with _contextlib.redirect_stdout(out), _contextlib.redirect_stderr(err):
        try:
            _sys.stdin = _io.StringIO(input_text)
            with _deadline(timeout):
                value = entry(*args, **({} if call_kwargs is None else call_kwargs))
                if _inspect.isawaitable(value) or consume:
                    value = _asyncio.run(_resolve(value, consume, max_items))
        except BaseException as exc:
            exc.add_note(f"Captured stdout:\n{out.getvalue()}\nCaptured stderr:\n{err.getvalue()}")
            raise
        finally:
            _sys.stdin = previous_stdin
    return CallResult(value, out.getvalue(), err.getvalue())


def make_env(updates=None, *, base=None):
    """Return a new environment mapping; None values remove named variables.

    base=None copies the current environment; base={} requests a clean one.
    Invalid mappings raise; this does not execute a process or return a status.
    """
    result = dict(_os.environ if base is None else base)
    for key, value in ({} if updates is None else updates).items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


@_contextlib.contextmanager
def temporary_env(updates):
    """Yield the modified process environment and restore it on every exit.

    None removes a named variable. Exceptions propagate, with no exit status.
    This changes process-global state; concurrent callers need subprocesses.
    """
    original = dict(_os.environ)
    replacement = make_env(updates)
    try:
        _os.environ.clear()
        _os.environ.update(replacement)
        yield _os.environ
    finally:
        _os.environ.clear()
        _os.environ.update(original)


@_contextlib.contextmanager
def temporary_directory(*, parent=None):
    """Yield a fresh Path and remove only that directory on exit.

    Creation, cleanup, and body errors propagate; no exit status is returned.
    """
    with _tempfile.TemporaryDirectory(dir=parent, prefix="suite-") as directory:
        yield _Path(directory)


def _argv(command):
    if isinstance(command, (str, bytes, _os.PathLike)):
        raise TypeError("Pass an argument sequence, not a shell command string")
    result = list(command)
    if not result:
        raise ValueError("Command must not be empty")
    return result


def _stop(process, timeout):
    # Each child is started in its own session. No unrelated process is targeted.
    try:
        _os.killpg(process.pid, _signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=timeout)
    except _subprocess.TimeoutExpired:
        _os.killpg(process.pid, _signal.SIGKILL)
        try:
            process.wait(timeout=timeout)
        except _subprocess.TimeoutExpired as exc:
            raise AssertionError("Owned child did not exit after forced shutdown") from exc
    # Also release descendants if the group leader exited before them.
    try:
        _os.killpg(process.pid, _signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_command(command, *, input_text=None, cwd=None, env=None,
                timeout=30, cleanup_timeout=5):
    """Return CompletedProcess with UTF-8 stdout, stderr, and returncode.

    command is an argv sequence, never shell text. env is the complete child
    environment (None inherits); use make_env for overlays. Nonzero product exits
    are returned unchanged, not asserted. Launch/decoding errors raise; a time
    limit raises AssertionError chained from TimeoutExpired with partial output.
    Children run in a new session; timeout cleanup targets only that session.
    """
    timeout, cleanup_timeout = _seconds(timeout), _seconds(cleanup_timeout)
    argv = _argv(command)
    with _subprocess.Popen(argv, stdin=_subprocess.PIPE, stdout=_subprocess.PIPE,
                           stderr=_subprocess.PIPE, text=True, encoding="utf-8",
                           cwd=cwd, env=env, start_new_session=True) as process:
        try:
            stdout, stderr = process.communicate(input=input_text, timeout=timeout)
        except _subprocess.TimeoutExpired as exc:
            _stop(process, cleanup_timeout)
            raise AssertionError(f"Command exceeded {timeout} seconds: {argv!r}") from exc
        except BaseException:
            _stop(process, cleanup_timeout)
            raise
        _stop(process, cleanup_timeout)
        return _subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def effective_import_paths():
    """Return the parent's ordered import roots, independent of a child's cwd.

    Relative entries (including the empty cwd entry) are made absolute before
    launch. Metadata directories travel with their containing import roots.
    """
    return list(dict.fromkeys(_os.path.abspath(path) for path in _sys.path
                              if isinstance(path, str)))


def python_command(source, args=(), *, executable=None):
    """Prepare a fresh Python command using the evaluated parent's import roots.

    Keep interpreter startup, explicit environment overlays and cwd available,
    but give the parent's effective roots priority over startup-only entries.
    No product module, installed replacement or forked module state is injected.
    The original source is compiled separately so future imports remain valid.
    """
    paths = effective_import_paths()
    bootstrap = (f"import sys; sys.path[:] = {paths!r} + "
                 f"[p for p in sys.path if p not in {paths!r}]; "
                 f"exec(compile({source!r}, '<string>', 'exec'))")
    return [_sys.executable if executable is None else executable,
            "-c", bootstrap, *args]


def run_python(source, args=(), *, executable=None, **options):
    """Return run_command's result from a prepared fresh Python interpreter.

    Preserve the parent's effective import layout, including distribution
    metadata. args follow source as argv; explicit env and cwd pass unchanged
    to run_command. Nonzero exits remain results; launch/time/capture errors
    propagate exactly as documented for run_command.
    """
    return run_command(python_command(source, args, executable=executable), **options)


def run_python_report(source, args=(), *, executable=None, **options):
    """Return (CompletedProcess, decoded JSON) from a fresh interpreter.

    Test-side protocol: argv[1] is a new absolute report filename; subsequent
    arguments are args. The caller's source writes exactly one JSON document to
    that file. stdout/stderr remain separate diagnostics, never parsed as JSON.
    Nonzero exits raise CalledProcessError carrying both streams. Missing or
    invalid reports raise with diagnostics; JSON null remains a valid value.
    Execution and cleanup limits are forwarded to run_command.
    """
    with temporary_directory() as directory:
        report = directory / "report.json"
        completed = run_python(source, [str(report), *args],
                               executable=executable, **options)
        completed.check_returncode()
        try:
            value = read_json(report)
        except Exception as exc:
            exc.add_note(f"Child stdout:\n{completed.stdout}\nChild stderr:\n{completed.stderr}")
            raise
        return completed, value


def parse_json(document):
    """Return json.loads(document); malformed input raises its original error.

    No fields or status are inferred, and valid JSON null is returned as None.
    """
    return _json.loads(document)


def read_json(path):
    """Return the parsed JSON document at path; I/O and parse errors propagate.

    Reads the explicitly named UTF-8 file; it does not infer an exit status.
    """
    with _Path(path).open(encoding="utf-8") as stream:
        return _json.load(stream)


def parse_yaml(document):
    """Return yaml.safe_load(document), without field or status inference.

    Missing parser dependencies and malformed YAML raise their original errors;
    a valid empty YAML document returns None according to the parser's semantics.
    """
    import yaml

    return yaml.safe_load(document)


def read_yaml(path):
    """Return parsed YAML from the explicit UTF-8 path; all read errors raise.

    Parser/dependency errors propagate; no process exit status is inferred.
    """
    return parse_yaml(_Path(path).read_text(encoding="utf-8"))


def wait_until(probe, *, timeout=10, interval=0.05):
    """Return the first truthy probe result within a monotonic deadline.

    A false result means retry, never success. Probe exceptions propagate without
    retry; exhaustion raises AssertionError. The entire loop, including probe
    calls, is signal-bounded and main-thread-only like invoke. No status is
    inferred. Callers must explicitly handle any expected transient probe errors.
    """
    timeout, interval = _seconds(timeout), _seconds(interval)
    stop = _time.monotonic() + timeout
    with _deadline(timeout):
        while True:
            result = probe()
            if result:
                return result
            remaining = stop - _time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"Probe did not succeed within {timeout} seconds")
            _time.sleep(min(interval, remaining))


@_contextlib.contextmanager
def running_process(command, *, stdout, stderr, cwd=None, env=None,
                    lifetime=30, cleanup_timeout=5):
    """Yield an owned Popen with a bounded managed lifetime and shutdown.

    stdout/stderr must be caller-owned files, not pipes, avoiding buffer stalls.
    Read logs from those explicit files; read status via poll()/returncode. No
    readiness or successful exit is inferred. The body is main-thread signal-
    bounded; timeout raises AssertionError, body/launch errors propagate. Leaving
    the scope terminates only this child's session with bounded forced cleanup.
    stdin is closed; use run_command for request/response input. For Python
    children, prepare command with python_command to preserve import context.
    """
    cleanup_timeout = _seconds(cleanup_timeout)
    lifetime = _seconds(lifetime)
    if not hasattr(stdout, "fileno") or not hasattr(stderr, "fileno"):
        raise TypeError("stdout and stderr must be open files")
    process = None
    try:
        with _deadline(lifetime):
            process = _subprocess.Popen(_argv(command), stdin=_subprocess.DEVNULL,
                                        stdout=stdout, stderr=stderr, cwd=cwd, env=env,
                                        start_new_session=True)
            yield process
    finally:
        if process is not None:
            _stop(process, cleanup_timeout)


@_contextlib.contextmanager
def bound_tcp_socket(host, port=0):
    """Yield a real bound IPv4 TCP socket, then close only that socket.

    getsockname() returns its actual endpoint. Bind errors propagate, including
    occupied ports; no alternate port or status is fabricated. The socket stays
    reserved until scope exit, so hand it to a server accepting sockets rather
    than closing it and assuming the same port remains free.
    """
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
        sock.bind((host, port))
        yield sock
