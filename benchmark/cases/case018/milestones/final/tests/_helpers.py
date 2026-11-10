# feature: F00
"""Shared invocation machinery, without feature expectations.

Callers supply public callables, command lines, parsers, and error-type maps.
Nonzero product statuses and product exceptions are observations, not assertions.
Infrastructure, decoding, missing dependencies, and deadline failures raise.
In-process capture and temporary_environment are process-global: use them only
from the main thread, without concurrent product calls. Use run_python for isolation.
No proposed CLI schema or source-language grammar is assumed here.
"""
from __future__ import annotations

import asyncio as _asyncio
import contextlib as _contextlib
import dataclasses as _dataclasses
import io as _io
import math as _math
import os as _os
from pathlib import Path as _Path
import shutil as _shutil
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import threading as _threading
import time as _time


class HelperTimeout(AssertionError):
    """A helper deadline expired; no result or successful status is returned."""


@_dataclasses.dataclass(frozen=True)
class ProcessResult:
    """Command observation: argv, integer returncode, raw stdout/stderr bytes.

    Negative returncode denotes a terminating signal on POSIX. Nonzero status
    is preserved. Launch, timeout, and capture errors raise instead of returning.
    """

    argv: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes


@_dataclasses.dataclass(frozen=True)
class CallResult:
    """Python observation: value, exception, exit_code, and text stdout/stderr.

    A normal return has exception=None and exit_code=None. A product exception
    retains its original object and traceback. SystemExit additionally exposes
    its original code. Deadline and capture failures raise, never become results.
    A partial value from failed consumption is not returned.
    """

    value: object
    exception: BaseException | None
    exit_code: object
    stdout: str
    stderr: str


def _seconds(timeout):
    timeout = float(timeout)
    if not _math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    return timeout


def _main_thread():
    if _threading.current_thread() is not _threading.main_thread():
        raise RuntimeError("Process-global helpers require the main thread")


@_contextlib.contextmanager
def _deadline(timeout):
    timeout = _seconds(timeout)
    _main_thread()
    if _signal.getitimer(_signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError("An existing real-time alarm prevents safe capture")
    previous = _signal.getsignal(_signal.SIGALRM)

    def expired(signum, frame):
        raise HelperTimeout(f"Python invocation exceeded {timeout} seconds")

    _signal.signal(_signal.SIGALRM, expired)
    _signal.setitimer(_signal.ITIMER_REAL, timeout)
    try:
        yield
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, previous)


def import_product():
    """Return the public velnora package using a plain import.

    Import/dependency errors propagate unchanged; this has no process exit status.
    For bounded import and isolated initialization, use run_python with a script
    containing a plain public import instead.
    """
    import velnora

    return velnora


def capture_call(call, *args, consume=None, timeout=30, **kwargs):
    """Return CallResult for a supplied public callable and optional consumer.

    consume(value), such as list or a stream-reading callable, runs before capture
    ends and within the same deadline. Python and native fd 1/2 output are captured
    as UTF-8 text (invalid UTF-8 raises). Product Exception/SystemExit is retained;
    KeyboardInterrupt, deadline, and capture errors propagate. No product status
    or exception is interpreted as correct. Main-thread POSIX use only.
    """
    _main_thread()
    value = error = exit_code = None
    with _tempfile.TemporaryFile(mode="w+", encoding="utf-8") as out, \
            _tempfile.TemporaryFile(mode="w+", encoding="utf-8") as err:
        _sys.stdout.flush()
        _sys.stderr.flush()
        with _contextlib.ExitStack() as stack:
            for fd, stream in ((1, out), (2, err)):
                saved = _os.dup(fd)
                stack.callback(_os.close, saved)
                stack.callback(_os.dup2, saved, fd)
                _os.dup2(stream.fileno(), fd)
            with _contextlib.redirect_stdout(out), _contextlib.redirect_stderr(err):
                with _deadline(timeout):
                    try:
                        value = call(*args, **kwargs)
                        if consume is not None:
                            value = consume(value)
                    except HelperTimeout:
                        raise
                    except (Exception, SystemExit) as exc:
                        value, error = None, exc
                        if isinstance(exc, SystemExit):
                            exit_code = exc.code
                out.flush()
                err.flush()
        out.seek(0)
        err.seek(0)
        return CallResult(value, error, exit_code, out.read(), err.read())


def command_environment(updates=None, *, inherit=True):
    """Return a new environment dict; None values remove keys.

    inherit=False starts empty. Does not mutate the process or interpret status;
    invalid environment values raise when passed to the operating system.
    """
    result = dict(_os.environ) if inherit else {}
    for key, value in ({} if updates is None else updates).items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


@_contextlib.contextmanager
def temporary_environment(updates, *, cwd=None):
    """Yield None with temporary environment updates and optional working directory.

    Restores both on all exits; operation and restoration errors propagate. There
    is no exit-status conversion. Main-thread, nonconcurrent use only.
    """
    _main_thread()
    original, directory = dict(_os.environ), _os.getcwd()
    try:
        replacement = command_environment(updates)
        _os.environ.clear()
        _os.environ.update(replacement)
        if cwd is not None:
            _os.chdir(cwd)
        yield
    finally:
        _os.chdir(directory)
        _os.environ.clear()
        _os.environ.update(original)


@_contextlib.contextmanager
def isolated_workspace(*, parent=None):
    """Yield an empty temporary Path and remove it on exit, without changing cwd.

    Creation/cleanup errors propagate; no product status is represented.
    """
    with _tempfile.TemporaryDirectory(prefix="suite-", dir=parent) as directory:
        yield _Path(directory)


def require_tools(*names, env=None):
    """Return name-to-executable paths resolved in the specified environment PATH.

    Missing tools raise FileNotFoundError; nothing is installed or substituted.
    No commands are run and no product exit status is implied.
    """
    environment = dict(_os.environ) if env is None else env
    found = {}
    for name in names:
        path = _shutil.which(name, path=environment.get("PATH", ""))
        if path is None:
            raise FileNotFoundError(f"Required executable is unavailable: {name}")
        found[name] = path
    return found


def _kill_group(process):
    try:
        _os.killpg(process.pid, _signal.SIGKILL)
    except ProcessLookupError:
        pass  # The owned process group has already exited.


def run_command(command, *, input_bytes=None, cwd=None, env=None, timeout=30):
    """Return ProcessResult after a shell-free command, with optional stdin bytes.

    env is a complete environment or None to inherit. All return codes are kept.
    Launch/read failures propagate. Timeout kills the owned POSIX process group,
    reaps it with a bounded wait, and raises HelperTimeout with partial bytes.
    """
    timeout = _seconds(timeout)
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be an argument sequence, not shell text")
    argv = tuple(_os.fspath(arg) for arg in command)
    with _subprocess.Popen(argv, cwd=cwd, env=env, start_new_session=True,
                           stdin=_subprocess.PIPE, stdout=_subprocess.PIPE,
                           stderr=_subprocess.PIPE) as process:
        try:
            out, err = process.communicate(input=input_bytes, timeout=timeout)
        except _subprocess.TimeoutExpired as exc:
            _kill_group(process)
            try:
                out, err = process.communicate(timeout=5)
            except _subprocess.TimeoutExpired as cleanup:
                raise HelperTimeout("Process group did not close captured streams") from cleanup
            raise HelperTimeout(
                f"Command exceeded {timeout} seconds: {argv!r}; "
                f"stdout={out!r}; stderr={err!r}"
            ) from exc
        return ProcessResult(argv, process.returncode, out, err)


def run_python(source, *, interpreter=None, args=(), **kwargs):
    """Return ProcessResult for source executed by the chosen Python interpreter.

    Defaults to the running suite's interpreter, never searches alternatives.
    Source must use plain public imports. Status/errors follow run_command.
    """
    executable = _sys.executable if interpreter is None else interpreter
    return run_command((executable, "-c", source, *args), **kwargs)


def parse_output(data, parser, *, encoding="utf-8"):
    """Return parser(text) for a documented format, decoding bytes strictly.

    The caller supplies the actual format parser; decoding/parser errors propagate.
    No field, grammar, product success, or exit status is inferred.
    """
    return parser(data.decode(encoding) if isinstance(data, bytes) else data)


def parse_labeled_json(data, *, label, encoding="utf-8"):
    """Return JSON values from lines beginning with the caller's exact label.

    Uses JSON parsing, preserving all fields and unrelated stderr lines untouched.
    No matching line raises ValueError; malformed JSON/encoding raises directly.
    Neither exit codes nor required product error fields are asserted here.
    """
    import json

    if not label or "\n" in label:
        raise ValueError("label must be a nonempty single-line prefix")
    text = data.decode(encoding) if isinstance(data, bytes) else data
    values = [json.loads(line[len(label):]) for line in text.splitlines()
              if line.startswith(label)]
    if not values:
        raise ValueError(f"No JSON record with label {label!r}")
    return values


def classify_exception(error, mapping):
    """Return the first label matching (public exception type, label) pairs.

    Unmapped exceptions are re-raised with their original traceback. This maps
    supplied public types only, never message text; process status is not inferred.
    """
    for exception_type, label in mapping:
        if isinstance(error, exception_type):
            return label
    raise error.with_traceback(error.__traceback__)


@_contextlib.contextmanager
def managed_server(command, *, cwd=None, env=None, shutdown_timeout=5):
    """Yield (Popen, stdout_file, stderr_file) for an owned network server.

    Output is captured in binary temporary files; read it before leaving the
    context. Caller supplies readiness checks via wait_until and inspects poll()
    for status. Teardown kills only this process group and waits a bounded time;
    launch/cleanup errors propagate. This does not claim server readiness.
    """
    shutdown_timeout = _seconds(shutdown_timeout)
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be an argument sequence")
    with _tempfile.TemporaryFile() as out, _tempfile.TemporaryFile() as err:
        process = _subprocess.Popen(command, cwd=cwd, env=env,
                                    stdin=_subprocess.DEVNULL, stdout=out,
                                    stderr=err, start_new_session=True)
        try:
            yield process, out, err
        finally:
            _kill_group(process)
            process.wait(timeout=shutdown_timeout)


async def wait_until(probe, *, timeout=30, interval=0.05):
    """Return the first truthy result of an async probe within a total deadline.

    False means explicitly not ready; probe exceptions propagate unchanged.
    Timeout raises HelperTimeout. The probe must use asynchronous bounded I/O;
    there is no product status interpretation or exception-based retry.
    """
    timeout, interval = _seconds(timeout), _seconds(interval)
    async with _asyncio.timeout(timeout):
        try:
            deadline = _time.monotonic() + timeout
            while True:
                result = await probe()
                if result:
                    return result
                remaining = deadline - _time.monotonic()
                if remaining <= 0:
                    raise HelperTimeout("Readiness probe exceeded its deadline")
                await _asyncio.sleep(min(interval, remaining))
        except _asyncio.CancelledError:
            if _time.monotonic() >= deadline:
                raise HelperTimeout("Readiness probe exceeded its deadline") from None
            raise


@_contextlib.asynccontextmanager
async def mcp_client(*, transport="stdio", command=None, args=(), url=None,
                     cwd=None, env=None, timeout=30):
    """Yield a real initialized MCP ClientSession over stdio, SSE, or HTTP.

    command/args select the stdio entry; URL selects an already managed network
    server. No server command, address, or tool name is assumed. The whole context
    including handshake, requests, and teardown has a total deadline. Dependency,
    protocol, and connection errors propagate; timeout raises HelperTimeout.
    Use call_tool for bounded tool calls. Product tool errors remain responses.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamable_http_client

    timeout = _seconds(timeout)
    try:
        async with _asyncio.timeout(timeout):
            async with _contextlib.AsyncExitStack() as stack:
                if transport == "stdio":
                    if command is None or url is not None:
                        raise ValueError("stdio requires command and no URL")
                    parameters = StdioServerParameters(
                        command=_os.fspath(command), args=list(args), env=env, cwd=cwd)
                    streams = await stack.enter_async_context(stdio_client(parameters))
                elif transport in ("sse", "http"):
                    if url is None or command is not None:
                        raise ValueError("Network transport requires URL and no command")
                    connection = sse_client(url) if transport == "sse" else streamable_http_client(url)
                    streams = await stack.enter_async_context(connection)
                else:
                    raise ValueError(f"Unknown MCP transport: {transport!r}")
                session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
                await session.initialize()
                yield session
    except TimeoutError as exc:
        raise HelperTimeout(f"MCP context exceeded {timeout} seconds") from exc


async def call_tool(session, name, arguments=None, *, timeout=30):
    """Return the unmodified MCP CallToolResult for a caller-named tool.

    structuredContent and isError remain directly available, including product
    failure responses. No text-content fallback, field defaults, or schema guesses
    are used. Transport/protocol errors propagate; timeout raises HelperTimeout.
    """
    timeout = _seconds(timeout)
    try:
        async with _asyncio.timeout(timeout):
            return await session.call_tool(name, arguments=arguments)
    except TimeoutError as exc:
        raise HelperTimeout(f"MCP tool call exceeded {timeout} seconds") from exc

