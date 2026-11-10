# feature: F00
"""Shared driving machinery; feature expectations belong in the calling tests.

Public product callables, resource factories, commands, and format parsers are
supplied by callers. No product modules are imported here. External SSH peers,
agents, token providers, realms, and independent oracles use the same command
and service lifecycle helpers. Environment mappings passed to subprocesses are
complete environments; use environment() to derive one from the current host.
"""

import asyncio as _asyncio
import contextlib as _contextlib
import hashlib as _hashlib
import inspect as _inspect
import io as _io
import math as _math
import os as _os
import pathlib as _pathlib
import socket as _socket
import stat as _stat
import subprocess as _subprocess
import tempfile as _tempfile
import time as _time
from dataclasses import dataclass as _dataclass


__all__ = [
    'CommandResult', 'CapturedCall', 'FileState', 'Service', 'environment',
    'temporary_environment', 'isolated_directory', 'run_command', 'run_module',
    'capture_call', 'parse_output', 'run_async', 'bounded', 'consume',
    'managed_resource', 'managed_service', 'wait_until', 'tcp_server',
    'unix_server', 'open_stream', 'close_stream', 'socket_pair', 'exchange',
    'read_exactly', 'read_until', 'write_stream', 'observe_path', 'observe_tree',
    'digest',
]


def _timeout(value):
    if not _math.isfinite(value) or value <= 0:
        raise ValueError('Timeout must be finite and positive')
    return value


@_dataclass(frozen=True)
class CommandResult:
    """Command argv, raw stdout/stderr bytes, and unmodified returncode.

    Negative returncodes denote POSIX signals. Nonzero status is data unless
    run_command(check=True) was requested; launch and timeout failures raise.
    """

    args: tuple
    returncode: int
    stdout: bytes
    stderr: bytes


@_dataclass(frozen=True)
class CapturedCall:
    """A synchronous call's return value and captured Python stdout/stderr text.

    There is no process status. Call exceptions propagate without conversion;
    capture does not include native file-descriptor or subprocess output.
    """

    value: object
    stdout: str
    stderr: str


@_dataclass(frozen=True)
class FileState:
    """Filesystem lstat metadata plus file bytes or the literal symlink target.

    Non-files have no contents; non-links have no target. Observation errors
    raise their original filesystem exception. There is no exit status.
    """

    metadata: object
    contents: object
    target: object


@_dataclass
class Service:
    """A live child and its seekable binary stdout/stderr captures.

    poll()/returncode on process expose status, including POSIX negative signal
    codes. output() reads snapshots. Lifecycle and readiness errors raise.
    Captures remain readable until the managed_service context exits.
    """

    process: object
    stdout: object
    stderr: object

    def output(self):
        """Return (stdout, stderr) bytes so far; file read failures raise.

        This does not wait for exit or interpret the child's exit status.
        """
        return (_os.pread(self.stdout.fileno(), _os.fstat(self.stdout.fileno()).st_size, 0),
                _os.pread(self.stderr.fileno(), _os.fstat(self.stderr.fileno()).st_size, 0))


def environment(updates=None, *, base=None, remove=()):
    """Return a new subprocess environment; do not change the host environment.

    Inherit os.environ only when base is None. Remove named keys and then apply
    updates. Invalid inputs raise normally; there is no process exit status.
    """
    result = dict(_os.environ if base is None else base)
    for name in remove:
        result.pop(name, None)
    if updates is not None:
        result.update(updates)
    return result


@_contextlib.contextmanager
def temporary_environment(updates=None, *, remove=()):
    """Yield the temporarily changed process environment and restore it on exit.

    Errors propagate; there is no exit status. This process-global context is
    unsuitable for overlapping concurrent callers; prefer subprocess env maps.
    """
    previous = dict(_os.environ)
    try:
        _os.environ.clear()
        _os.environ.update(environment(updates, base=previous, remove=remove))
        yield _os.environ
    finally:
        _os.environ.clear()
        _os.environ.update(previous)


@_contextlib.contextmanager
def isolated_directory(*, parent=None):
    """Yield a unique Path, removing its tree on exit without changing cwd.

    Creation, caller, and cleanup errors propagate. There is no exit status.
    """
    with _tempfile.TemporaryDirectory(dir=parent) as directory:
        yield _pathlib.Path(directory)


def run_command(command, *, input=None, cwd=None, env=None, timeout=10.0,
                check=False):
    """Return CommandResult from an argv sequence with separate byte captures.

    Input is bytes or None (closed stdin). Nonzero status is returned unless
    check=True, which raises CalledProcessError with both captures. Launch
    errors and TimeoutExpired raise; subprocess.run kills and reaps on timeout.
    No shell is used and no decoding or output normalization is performed.
    """
    if isinstance(command, (str, bytes)):
        raise TypeError('Command must be an argv sequence, not shell text')
    args = tuple(_os.fspath(arg) for arg in command)
    result = _subprocess.run(args, input=input, stdin=None if input is not None
                             else _subprocess.DEVNULL,
                             stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
                             cwd=cwd, env=env, timeout=_timeout(timeout), check=check)
    return CommandResult(args, result.returncode, result.stdout, result.stderr)


def run_module(python, module, arguments=(), **options):
    """Return run_command's result for a caller-selected Python -m entry point.

    Exit status, byte captures, and exceptions have run_command semantics.
    """
    return run_command([python, '-m', module, *arguments], **options)


def capture_call(entry_point, *args, **kwargs):
    """Return CapturedCall for a synchronous public callable; errors propagate.

    This changes process-global Python streams temporarily. It neither imposes
    a timeout nor captures native writes; use run_command for blocking calls.
    """
    stdout, stderr = _io.StringIO(), _io.StringIO()
    with _contextlib.redirect_stdout(stdout), _contextlib.redirect_stderr(stderr):
        value = entry_point(*args, **kwargs)
    return CapturedCall(value, stdout.getvalue(), stderr.getvalue())


def parse_output(data, parser, *args, **kwargs):
    """Return parser(data, ...), preserving all parsing exceptions.

    Supply the format's real parser (e.g. json.loads, an ASN.1 decoder, a PEM
    loader, or a terminal emulator adapter). No fields, labels, status, or
    alternate formats are guessed, and no parse failure becomes an answer.
    """
    return parser(data, *args, **kwargs)


@_contextlib.asynccontextmanager
async def opened_connection(awaitable):
    """Await a connection and close it on exit through close() and wait_closed()."""
    connection = await awaitable
    try:
        yield connection
    finally:
        connection.close()
        await connection.wait_closed()


async def bounded(awaitable, *, timeout=10.0):
    """Return an awaitable's result with a finite deadline; errors propagate.

    Expiry raises TimeoutError and requests cancellation. Like asyncio timeouts,
    this requires cooperative cancellation; blocking code belongs in a child
    process. There is no product exit-status conversion.
    """
    return await _asyncio.wait_for(awaitable, _timeout(timeout))


def run_async(awaitable, *, timeout=10.0):
    """Return an awaitable's result on a fresh, subsequently closed event loop.

    Use from synchronous tests without a running loop. Exceptions, including
    TimeoutError, propagate; product return values and statuses are unchanged.
    """
    return _asyncio.run(bounded(awaitable, timeout=timeout))


async def consume(iterable, *, timeout=10.0):
    """Return a list after fully consuming an async iterable under one deadline.

    Iteration and finalization errors propagate inside the caller's await
    scope, so callers can capture streaming failures around this single call.
    """
    async def collect():
        return [item async for item in iterable]
    return await bounded(collect(), timeout=timeout)


async def _resolve(value, timeout):
    if _inspect.isawaitable(value):
        return await bounded(value, timeout=timeout)
    return value


@_contextlib.asynccontextmanager
async def managed_resource(factory, *args, close, wait_closed=None,
                           timeout=10.0, **kwargs):
    """Yield a resource made by a supplied public sync/async factory.

    close(resource) is always invoked on exit; optional wait_closed(resource)
    follows it. Async startup and cleanup each have a finite deadline. Values
    and statuses are untouched, and startup/body/cleanup failures propagate.
    Sync callbacks must be nonblocking; use managed_service for subprocesses.
    """
    _timeout(timeout)
    resource = await _resolve(factory(*args, **kwargs), timeout)
    try:
        yield resource
    finally:
        await _resolve(close(resource), timeout)
        if wait_closed is not None:
            await _resolve(wait_closed(resource), timeout)


async def wait_until(probe, *, timeout=10.0, interval=0.01):
    """Return the first truthy sync/async probe result before a deadline.

    A false result means not ready; probe exceptions are never retried or
    hidden. Expiry raises TimeoutError. Sync probes must be nonblocking.
    """
    deadline = _time.monotonic() + _timeout(timeout)
    _timeout(interval)
    while True:
        remaining = deadline - _time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Readiness deadline expired')
        result = await _resolve(probe(), remaining)
        if result:
            return result
        remaining = deadline - _time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Readiness deadline expired')
        await _asyncio.sleep(min(interval, remaining))


@_contextlib.asynccontextmanager
async def managed_service(command, *, ready, cwd=None, env=None,
                          timeout=10.0, interval=0.01):
    """Yield Service after a caller-supplied readiness probe returns truthy.

    Run any real external peer/provider in foreground mode using argv. The
    probe receives Service, may await, and must not block synchronously. Launch,
    early exit, probe and timeout errors raise. On exit terminate this child,
    then kill/reap it if necessary, each with a finite deadline. Shutdown signal
    status remains on process; no successful service result is fabricated.
    """
    _timeout(timeout)
    if isinstance(command, (str, bytes)):
        raise TypeError('Command must be an argv sequence, not shell text')
    with _tempfile.TemporaryFile() as stdout, _tempfile.TemporaryFile() as stderr:
        process = _subprocess.Popen(command, cwd=cwd, env=env,
                                    stdin=_subprocess.DEVNULL,
                                    stdout=stdout, stderr=stderr)
        service = Service(process, stdout, stderr)
        try:
            async def probe():
                status = process.poll()
                if status is not None:
                    out, err = service.output()
                    raise _subprocess.CalledProcessError(status, command, out, err)
                return await _resolve(ready(service), timeout)
            await wait_until(probe, timeout=timeout, interval=interval)
            yield service
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    await _asyncio.to_thread(process.wait, timeout=timeout)
                except _subprocess.TimeoutExpired:
                    process.kill()
                    await _asyncio.to_thread(process.wait, timeout=timeout)


@_contextlib.asynccontextmanager
async def tcp_server(handler, *, host, port=0, timeout=10.0, **options):
    """Yield an asyncio TCP server; sockets expose the actual bound addresses.

    Handler is caller supplied. Startup/close errors propagate; close waiting
    is bounded. The caller owns accepted streams and handler task failures;
    manage those explicitly in the same test scope. No status is interpreted.
    """
    server = await bounded(_asyncio.start_server(handler, host, port, **options),
                           timeout=timeout)
    try:
        yield server
    finally:
        server.close()
        await bounded(server.wait_closed(), timeout=timeout)


@_contextlib.asynccontextmanager
async def unix_server(handler, *, path, timeout=10.0, **options):
    """Yield an asyncio UNIX server at a caller-owned temporary path.

    Startup/close errors propagate and close waiting is bounded. The caller
    owns the socket path, accepted streams, and handler tasks. No exit status.
    """
    server = await bounded(_asyncio.start_unix_server(handler, path, **options),
                           timeout=timeout)
    try:
        yield server
    finally:
        server.close()
        await bounded(server.wait_closed(), timeout=timeout)


@_contextlib.asynccontextmanager
async def open_stream(opener, *args, timeout=10.0, **kwargs):
    """Yield (reader, writer) from a public async opener, then close the writer.

    TCP, UNIX and public product openers are caller-selected. Connection and
    cleanup have deadlines; their errors propagate, with no status conversion.
    """
    reader, writer = await bounded(opener(*args, **kwargs), timeout=timeout)
    try:
        yield reader, writer
    finally:
        await close_stream(writer, timeout=timeout)


async def close_stream(writer, *, timeout=10.0):
    """Close a public stream writer and return None after bounded wait_closed.

    All close errors propagate; no exit status is inferred from stream EOF.
    """
    writer.close()
    await bounded(writer.wait_closed(), timeout=timeout)


@_contextlib.contextmanager
def socket_pair():
    """Yield two connected nonblocking sockets; close both on context exit.

    Socket errors propagate. No product status or packet interpretation occurs.
    """
    left, right = _socket.socketpair()
    try:
        left.setblocking(False)
        right.setblocking(False)
        yield left, right
    finally:
        left.close()
        right.close()


async def write_stream(writer, data, *, eof=False, timeout=10.0):
    """Write data and await public drain; optionally half-close using write_eof.

    Return None; unsupported half-close, flow-control errors, and deadlines
    raise unchanged. Data and stream exit statuses are never synthesized.
    """
    writer.write(data)
    await bounded(writer.drain(), timeout=timeout)
    if eof:
        writer.write_eof()
        await bounded(writer.drain(), timeout=timeout)


async def read_exactly(reader, size, *, timeout=10.0):
    """Return exactly size bytes/text units using public readexactly.

    Short input raises the reader's exception with its original partial data;
    timeout raises TimeoutError. EOF is not treated as a process exit status.
    """
    return await bounded(reader.readexactly(size), timeout=timeout)


async def read_until(reader, separator, *, timeout=10.0):
    """Return public readuntil(separator) data, retaining its documented framing.

    Reader errors and timeout propagate, including partial data on short input;
    no protocol field, success condition, or exit status is inferred.
    """
    return await bounded(reader.readuntil(separator), timeout=timeout)


async def exchange(reader, writer, data, receive, *, eof=False, timeout=10.0):
    """Concurrently send data and return await receive(reader) under one deadline.

    receive is caller-selected framing/consumption, not a guessed read length.
    Both tasks finish in this scope; either failure cancels the other and
    propagates. No product status is interpreted and streams stay caller-owned.
    """
    async def perform():
        tasks = [_asyncio.create_task(write_stream(writer, data, eof=eof,
                                                   timeout=timeout)),
                 _asyncio.create_task(receive(reader))]
        try:
            results = await _asyncio.gather(*tasks)
            return results[1]
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await _asyncio.gather(*tasks, return_exceptions=True)
    return await bounded(perform(), timeout=timeout)


def observe_path(path):
    """Return FileState using lstat; read regular files and never follow links.

    Absent/unreadable paths raise original errors. Other node kinds have None
    contents and target. This observes filesystem state, not durable commit.
    """
    path = _pathlib.Path(path)
    metadata = path.lstat()
    contents = path.read_bytes() if _stat.S_ISREG(metadata.st_mode) else None
    target = _os.readlink(path) if _stat.S_ISLNK(metadata.st_mode) else None
    return FileState(metadata, contents, target)


def observe_tree(root):
    """Return a mapping of relative Paths to FileState, including root as '.'.

    Traverse directories without following symlinks. All filesystem errors
    propagate; no missing tree becomes an empty successful observation. This
    is a non-atomic snapshot and makes no durability claim or status inference.
    """
    root = _pathlib.Path(root)
    result = {}
    pending = [root]
    while pending:
        path = pending.pop()
        state = observe_path(path)
        result[path.relative_to(root)] = state
        if _stat.S_ISDIR(state.metadata.st_mode):
            pending.extend(path.iterdir())
    return result


def digest(data, algorithm):
    """Return raw hashlib digest bytes for caller-selected data and algorithm.

    Unsupported algorithms and invalid inputs raise; no product digest choice,
    signature expectation, or success status is embedded in this helper.
    """
    return _hashlib.new(algorithm, data).digest()
