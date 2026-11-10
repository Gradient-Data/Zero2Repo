# feature: F00
"""Shared transport and observation machinery; no product behavior is specified here.

Entry points, protocol parsers, public field names and deadlines belong to the
caller. In-process synchronous code must cooperate with the event loop; use a
fresh process for code that may block it. No product modules are imported here.
"""
from __future__ import annotations

import asyncio as _asyncio
import contextlib as _contextlib
import dataclasses as _dataclasses
import io as _io
import json as _json
import math as _math
import os as _os
import shutil as _shutil
import socket as _socket
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
from collections.abc import Mapping as _Mapping
from pathlib import Path as _Path

__all__ = [
    "ProcessResult", "Observation", "CapturedOutput", "ResourceRegistry",
    "run_process", "run_python", "run_module", "run_pytest", "bounded",
    "invoke", "consume", "invoke_and_consume", "capture_output",
    "temporary_directory", "environment", "read_field", "parse_json",
    "read_json", "parse_jsonl", "read_jsonl", "parse_protocol", "parse_dot",
    "read_dot", "require_executable", "require_environment", "probe_tcp",
]


def _seconds(value):
    if not _math.isfinite(value) or value <= 0:
        raise ValueError("Timeout must be positive and finite.")
    return value


@_dataclasses.dataclass(frozen=True)
class ProcessResult:
    """Completed command, byte stdout/stderr and integer returncode.

    Nonzero exits (negative for POSIX signals) are observations, not exceptions.
    Launch and deadline failures are raised by the runner, never stored here.
    """

    args: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes


@_dataclasses.dataclass
class Observation:
    """Mutable ledger of a call's returned value and delivered stream items.

    Pass an instance to retain partial delivery when a call raises. Exceptions
    propagate unchanged; returned=False distinguishes failure from a None value.
    This object has no process exit status and never stores an error as a result.
    """

    value: object = None
    returned: bool = False
    items: list = _dataclasses.field(default_factory=list)


@_dataclasses.dataclass
class CapturedOutput:
    """Text buffers populated by capture_output, including before a failure.

    Read each buffer with getvalue(). Exceptions propagate; no exit status exists.
    """

    stdout: _io.StringIO = _dataclasses.field(default_factory=_io.StringIO)
    stderr: _io.StringIO = _dataclasses.field(default_factory=_io.StringIO)


def run_process(command, *, input=None, cwd=None, env=None, timeout=30.0):
    """Return ProcessResult from an argv sequence without a shell.

    input is bytes or None (closed stdin); env is the complete child environment
    or None to inherit. All exit codes are returned. Launch errors propagate;
    deadline expiry raises AssertionError chained from TimeoutExpired, retaining
    its captured bytes. A fresh POSIX process group is killed on expiry so child
    descendants cannot keep output pipes open; every reap is bounded.
    """
    timeout = _seconds(timeout)
    if isinstance(command, (str, bytes)):
        raise TypeError("Command must be an argv sequence, not shell text.")
    args = tuple(_os.fspath(part) for part in command)
    if not args:
        raise ValueError("Command cannot be empty.")
    process = _subprocess.Popen(
        args, stdin=_subprocess.PIPE, stdout=_subprocess.PIPE,
        stderr=_subprocess.PIPE, cwd=cwd, env=env,
        start_new_session=(_os.name == "posix"),
    )
    try:
        stdout, stderr = process.communicate(input=input, timeout=timeout)
    except BaseException as primary:
        try:
            if _os.name == "posix":
                import signal
                try:
                    _os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    if process.poll() is None:
                        raise
            elif process.poll() is None:
                process.kill()
            process.communicate(timeout=timeout)
        except BaseException as cleanup:
            if isinstance(primary, _subprocess.TimeoutExpired):
                raise AssertionError(f"Command exceeded {timeout}s: {args!r}") from primary
            raise primary from cleanup
        if isinstance(primary, _subprocess.TimeoutExpired):
            raise AssertionError(f"Command exceeded {timeout}s: {args!r}") from primary
        raise
    return ProcessResult(args, process.returncode, stdout, stderr)


def run_python(source, *, interpreter=None, args=(), **options):
    """Return ProcessResult for source in a new interpreter, without fork state.

    Interpreter defaults to the pytest interpreter; args follow -c source.
    Byte input, environment, nonzero exit and raised errors follow run_process.
    Child source must use plain imports of the product's documented public API.
    """
    return run_process([interpreter or _sys.executable, "-c", source, *args], **options)


def run_module(module, *, interpreter=None, args=(), **options):
    """Return ProcessResult from a caller-selected public module via python -m.

    The default interpreter is pytest's; exits and failures follow run_process.
    """
    return run_process([interpreter or _sys.executable, "-m", module, *args], **options)


def run_pytest(args=(), *, interpreter=None, **options):
    """Return ProcessResult from the existing pytest module entry point.

    No installation or path mutation occurs. Collection/test exit codes are
    returned verbatim; process launch and deadlines follow run_process.
    """
    return run_module("pytest", interpreter=interpreter, args=args, **options)


async def bounded(awaitable, *, timeout=30.0):
    """Return an awaitable's value; propagate its original exception unchanged.

    Deadline expiry raises AssertionError and requests cancellation without an
    unbounded cancellation join. The event loop must remain cooperative. There
    is no exit code. Caller-owned resources still require explicit cleanup.
    """
    timeout = _seconds(timeout)
    task = _asyncio.ensure_future(awaitable)
    try:
        done, _ = await _asyncio.wait({task}, timeout=timeout)
        if not done:
            raise AssertionError(f"Operation exceeded {timeout}s.")
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            task.add_done_callback(_retrieve_cancelled_task)


def _retrieve_cancelled_task(task):
    # Retrieve late failures without replacing the already raised deadline.
    if not task.cancelled():
        error = task.exception()
        if error is not None:
            task.get_loop().call_exception_handler(
                {"message": "Operation failed after deadline cancellation.",
                 "exception": error, "task": task}
            )


async def invoke(entry, *args, timeout=30.0, observation=None, **kwargs):
    """Return the result of a caller-supplied async public entry point.

    Records successful return in an optional Observation. Original failures
    propagate; a helper deadline raises AssertionError. No exit status exists.
    """
    async def operation():
        value = await entry(*args, **kwargs)
        if observation is not None:
            observation.value, observation.returned = value, True
        return value
    return await bounded(operation(), timeout=timeout)


async def consume(stream, *, timeout=30.0, observation=None):
    """Return all items from a caller-supplied async iterable within one deadline.

    Optional Observation retains partial items on failure. Iteration errors
    propagate unchanged; deadline raises AssertionError, never an empty success.
    There is no exit status; the caller owns closing the stream/session.
    """
    ledger = observation if observation is not None else Observation()
    async def operation():
        items = []
        async for item in stream:
            ledger.items.append(item)
            items.append(item)
        return items
    return await bounded(operation(), timeout=timeout)


async def invoke_and_consume(entry, *args, stream_from, timeout=30.0,
                             observation=None, **kwargs):
    """Return (call result, items) under one invocation-and-consumption deadline.

    entry is an async callable; stream_from selects its documented async stream.
    An optional Observation keeps the returned result and all delivered items
    even if iteration fails. Original errors propagate; deadline raises
    AssertionError. No error is returned as a successful value or exit code.
    """
    ledger = observation if observation is not None else Observation()
    async def operation():
        result = await entry(*args, **kwargs)
        ledger.value, ledger.returned = result, True
        items = []
        async for item in stream_from(result):
            ledger.items.append(item)
            items.append(item)
        return result, items
    return await bounded(operation(), timeout=timeout)


@_contextlib.contextmanager
def capture_output():
    """Yield CapturedOutput for Python stdout/stderr; propagate original errors.

    This process-global redirection is for serial in-process calls, not native
    file descriptors or concurrent calls. Use run_process for isolated capture.
    No exit status is generated.
    """
    output = CapturedOutput()
    with _contextlib.redirect_stdout(output.stdout), _contextlib.redirect_stderr(output.stderr):
        yield output


@_contextlib.contextmanager
def temporary_directory(*, parent=None, prefix="suite-"):
    """Yield a fresh Path and remove it on exit; filesystem failures raise.

    No product state or exit code is inferred from the directory's contents.
    """
    with _tempfile.TemporaryDirectory(dir=parent, prefix=prefix) as directory:
        yield _Path(directory)


@_contextlib.contextmanager
def environment(changes):
    """Yield the temporary environment; restore changed keys even on errors.

    Values are strings or None to remove a key. Original exceptions propagate;
    no exit status exists. This process-global operation requires serial use.
    """
    before = {key: _os.environ.get(key) for key in changes}
    try:
        for key, value in changes.items():
            if value is None:
                _os.environ.pop(key, None)
            else:
                _os.environ[key] = value
        yield _os.environ
    finally:
        for key, value in before.items():
            if value is None:
                _os.environ.pop(key, None)
            else:
                _os.environ[key] = value


def read_field(value, name):
    """Return an exact public mapping key or attribute, without guessing aliases.

    Missing fields raise KeyError/AttributeError; accessor errors propagate.
    name must be public. No exit status or default answer is manufactured.
    """
    if not isinstance(name, str) or name.startswith("_"):
        raise ValueError("A public field name is required.")
    return value[name] if isinstance(value, _Mapping) else getattr(value, name)


def parse_json(data):
    """Return parsed JSON from text/bytes; decoding/parsing errors propagate.

    Reads the entire payload, never searches logs; no exit status is inferred.
    """
    return _json.loads(data)


def read_json(path):
    """Return JSON from the exact file path; I/O and parsing errors propagate.

    No exit status is inferred from file presence or contents.
    """
    return parse_json(_Path(path).read_bytes())


def parse_jsonl(data):
    """Return one parsed JSON value per line; malformed/blank records raise.

    An empty document returns []; a final newline adds no record. UTF-8 decode
    and JSON errors propagate, and no product exit status is inferred.
    """
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return [parse_json(line) for line in data.splitlines()]


def read_jsonl(path):
    """Return JSONL records from an exact file; I/O and parse errors propagate.

    No missing file or malformed record is converted to an empty result.
    """
    return parse_jsonl(_Path(path).read_bytes())


def parse_protocol(payload, *, parser):
    """Return the caller-selected protocol parser's result for a full payload.

    Framing belongs to that parser; all parser errors propagate. No result or
    exit status is guessed from log text, labels or byte positions.
    """
    return parser(payload)


def parse_dot(source, *, parser):
    """Return a real DOT parser's result; parser and dependency errors propagate.

    Pass an independent DOT parser callable, not a regex or product parser.
    Graph semantics and validity assertions belong to callers; no exit exists.
    """
    return parser(source)


def read_dot(path, *, parser):
    """Return parsed UTF-8 DOT from a stated path; I/O/parser errors propagate.

    Uses the caller's independent DOT parser and infers no exit status.
    """
    return parse_dot(_Path(path).read_text(encoding="utf-8"), parser=parser)


def require_executable(name):
    """Return an executable's resolved path or raise FileNotFoundError.

    Absence means the dependent capability is unobserved, never skipped or
    successful. This preflight does not execute it or manufacture an exit code.
    """
    path = _shutil.which(name)
    if path is None:
        raise FileNotFoundError(f"Required executable unavailable; capability unobserved: {name}")
    return path


def require_environment(names):
    """Return required environment values; missing/empty values raise RuntimeError.

    Errors list names only, never secrets; dependent capability is unobserved.
    No exit status is returned.
    """
    values = {name: _os.environ[name] for name in names if name in _os.environ}
    missing = [name for name in names if not values.get(name)]
    if missing:
        raise RuntimeError(f"Required environment missing; capability unobserved: {missing!r}")
    return values


def probe_tcp(host, port, *, timeout=5.0):
    """Return None after one TCP connection; connection/dependency errors raise.

    This checks reachability only, not protocol health. A literal IP address is
    required to avoid unbounded system DNS resolution. No retries or exit code.
    """
    import ipaddress
    address = str(ipaddress.ip_address(host))
    with _socket.create_connection((address, port), timeout=_seconds(timeout)):
        pass


class ResourceRegistry:
    """Context manager registering only explicitly owned, named cleanup commands.

    register returns the resource name; close returns cleanup ProcessResults.
    Cleanup is LIFO with a per-command deadline. Launch, deadline and nonzero
    cleanup exits raise; an existing body failure stays primary with cleanup
    failure chained. This class never discovers or bulk-cleans resources and
    never starts containers. Container startup must use the bound casebox entry.
    """

    def __init__(self, *, timeout=30.0):
        """Create an empty registry; invalid cleanup deadlines raise ValueError."""
        self._timeout = _seconds(timeout)
        self._resources = []
        self._names = set()

    def register(self, name, *, cleanup_command, cwd=None, env=None):
        """Return a unique owned name after recording its explicit cleanup argv.

        Register immediately after acquisition. Duplicate/empty names and shell
        strings raise; no acquisition, cleanup or exit status occurs here.
        """
        if not name or name in self._names:
            raise ValueError("Resource name must be nonempty and unique.")
        if isinstance(cleanup_command, (str, bytes)) or not cleanup_command:
            raise TypeError("Cleanup must be a nonempty explicit argv sequence.")
        command = tuple(cleanup_command)
        self._resources.append((name, command, cwd, env))
        self._names.add(name)
        return name

    def close(self):
        """Return cleanup results; attempt every registered cleanup, then raise errors.

        Nonzero cleanup status raises CalledProcessError with captured bytes.
        Multiple errors are available on the first error's cleanup_errors tuple.
        Successful close empties the pending registry; no retry is implicit.
        """
        results, errors = [], []
        while self._resources:
            name, command, cwd, env = self._resources.pop()
            try:
                result = run_process(command, cwd=cwd, env=env, timeout=self._timeout)
                results.append(result)
                if result.returncode:
                    raise _subprocess.CalledProcessError(
                        result.returncode, result.args, output=result.stdout, stderr=result.stderr
                    )
            except Exception as error:
                errors.append(error)
        if errors:
            errors[0].cleanup_errors = tuple(errors)
            raise errors[0]
        return results

    def __enter__(self):
        """Return this registry; performs no acquisition and generates no exit code."""
        return self

    def __exit__(self, exc_type, exc, traceback):
        """Clean registered resources; propagate body/cleanup errors, never suppress.

        A body error remains primary if cleanup also fails, with cleanup chained.
        Returns False only when cleanup succeeds; no process status is invented.
        """
        try:
            self.close()
        except Exception as cleanup:
            if exc is not None:
                raise exc.with_traceback(traceback) from cleanup
            raise
        return False
