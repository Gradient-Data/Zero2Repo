# feature: F00
"""Shared, product-agnostic machinery for every trisift feature suite.

This module knows *how to drive* the product and nothing about what the
product *should* do: it runs the ``trisift`` executable, captures its exit
status and output streams, runs it under a pseudo-terminal, keeps it running
in the background, talks to a line-oriented TCP endpoint, and builds
temporary fixture trees and git repositories.  It contains no tests and no
assertions about product behaviour.  Exit-status values, output layouts,
message labels, file names inside the index directory and protocol method
names all belong to the feature suites and the Interface Contract, so every
such value is a parameter here.

Conventions shared by every helper:

* Exit status is reported as an ``int`` exactly as the OS reports it.  A
  negative value ``-N`` means the process was terminated by signal ``N``.
  Helpers never interpret it.
* Output is reported as raw ``bytes``.  Decode only where needed, with
  :func:`decode` (strict UTF-8, raises on invalid data).
* Harness failures (binary missing, timeout, a process dying early, a wait
  that never succeeds, a permission change that has no effect, a closed
  socket, a failing git command) raise a subclass of :class:`HarnessError`
  carrying the original cause.  Nothing is swallowed and nothing is retried
  silently.
* ``env=None`` always means "inherit ``os.environ`` unchanged"; a mapping is
  used verbatim as the complete environment.  Use :func:`hermetic_env` to
  build one that hides the user's personal git/ignore configuration.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import pty
import secrets
import hashlib
import random
import sys
import select
import shutil
import signal
import socket
import stat
import string
import struct
import subprocess
import tempfile
import termios
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence, Union

__all__ = [
    "PRODUCT_COMMAND",
    "DEFAULT_TIMEOUT",
    "HarnessError",
    "ProductNotFound",
    "ProductTimeout",
    "ProcessExited",
    "ProcessStopTimeout",
    "WaitTimeout",
    "PermissionNotEffective",
    "ConnectionClosed",
    "GitError",
    "RunResult",
    "trisift_binary",
    "decode",
    "run_trisift",
    "run_in_pty",
    "BackgroundProcess",
    "wait_until",
    "wait_for_json_file",
    "wait_for_tcp",
    "pid_alive",
    "LineConnection",
    "line_request",
    "jsonrpc_request",
    "unique_token",
    "make_tree",
    "make_text_file",
    "make_sparse_file",
    "hermetic_env",
    "git",
    "git_init",
    "git_add",
    "make_unreadable",
]

PathArg = Union[str, "os.PathLike[str]"]
Arg = Union[str, bytes, "os.PathLike[str]"]

#: Executable name from the Interface Contract. Explicit configuration and
#: the judge's build artifact take precedence over an installed command.
PRODUCT_COMMAND = "trisift"
_JUDGE_BUILD_ROOT = Path("/app")

#: Default number of seconds a single product invocation may run before the
#: harness kills it and raises :class:`ProductTimeout`.
DEFAULT_TIMEOUT = 120.0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class HarnessError(Exception):
    """Base class for every failure raised by the harness itself.

    A ``HarnessError`` means the test could not observe the product as
    intended; it is never a statement about whether the product behaved
    correctly.
    """


class ProductNotFound(HarnessError):
    """Raised when the product executable cannot be located or started."""


class ProductTimeout(HarnessError):
    """Raised when a product invocation exceeds its timeout.

    The process has already been killed and reaped.  ``argv``, ``stdout`` and
    ``stderr`` (bytes captured before the kill) are kept as attributes.
    """

    def __init__(self, argv: Sequence[Arg], timeout: float, stdout: bytes, stderr: bytes):
        self.argv = list(argv)
        self.timeout = timeout
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"{_show_argv(argv)} did not finish within {timeout}s; "
            f"stdout so far={_clip(stdout)!r} stderr so far={_clip(stderr)!r}"
        )


class ProcessExited(HarnessError):
    """Raised when a background process exits while the caller expected it alive.

    ``code`` is its exit status (negative for a signal); ``stdout`` and
    ``stderr`` hold everything it wrote.
    """

    def __init__(self, argv: Sequence[Arg], code: int, stdout: bytes, stderr: bytes):
        self.argv = list(argv)
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"{_show_argv(argv)} exited early with status {code}; "
            f"stdout={_clip(stdout)!r} stderr={_clip(stderr)!r}"
        )


class ProcessStopTimeout(HarnessError):
    """Raised when a background process ignores its stop signal.

    The process has been killed with SIGKILL and reaped before this is raised.
    """


class WaitTimeout(HarnessError):
    """Raised by :func:`wait_until` when the condition never held.

    ``last_value`` is the predicate's last return value and ``last_error`` the
    last exception it raised from the caller's ``retry_on`` set (or ``None``).
    """

    def __init__(self, message: str, last_value: Any, last_error: Optional[BaseException]):
        self.last_value = last_value
        self.last_error = last_error
        super().__init__(
            f"{message}; last value={last_value!r}; last error={last_error!r}"
        )


class PermissionNotEffective(HarnessError):
    """Raised when a permission change does not actually deny access.

    Typical cause: the suite runs as root, so mode bits are not enforced.  The
    test cannot construct its precondition and must fail, not pass or skip.
    """


class ConnectionClosed(HarnessError):
    """Raised when the peer closes a TCP connection before a full line arrived."""


class GitError(HarnessError):
    """Raised when git is missing or a git command exits non-zero (stderr kept)."""


# ---------------------------------------------------------------------------
# Running the product
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunResult:
    """Outcome of one finished product invocation.

    ``code`` is the exit status as reported by the OS (negative ``-N`` when
    killed by signal ``N``).  ``stdout`` and ``stderr`` are the raw bytes the
    process wrote.  When the run merged stderr into stdout, ``stderr`` is
    ``b""``.  ``argv`` and ``cwd`` record what was executed, for messages.

    Unpacks as a 3-tuple: ``code, out, err = run_trisift(...)``.
    """

    argv: tuple
    cwd: str
    code: int
    stdout: bytes
    stderr: bytes

    def __iter__(self) -> Iterator[Any]:
        return iter((self.code, self.stdout, self.stderr))

    @property
    def out(self) -> str:
        """``stdout`` decoded as strict UTF-8 (raises ``UnicodeDecodeError``)."""
        return decode(self.stdout)

    @property
    def err(self) -> str:
        """``stderr`` decoded as strict UTF-8 (raises ``UnicodeDecodeError``)."""
        return decode(self.stderr)

    def describe(self) -> str:
        """Return a one-paragraph human summary for assertion messages."""
        return (
            f"argv={_show_argv(self.argv)} cwd={self.cwd} code={self.code}\n"
            f"stdout={_clip(self.stdout)!r}\nstderr={_clip(self.stderr)!r}"
        )


def trisift_binary(binary: Optional[PathArg] = None) -> str:
    """Return the absolute path of the product executable to run.

    Precedence: explicit ``binary=``, runner ``TRISIFT_BINARY``, Cargo debug
    artifact in the runner's cwd, the judge's /app artifact, then PATH.
    Resolve relative paths in the runner, before a child enters its fixture
    cwd. Configuration is a path, never a shell command. An invalid selected
    path is a setup error, not permission to fall back to a different build.

    Selection uses the runner's environment; a launcher's ``env=`` controls
    the child's environment only, including hermetic HOME/PATH settings.
    """
    if binary is None and "TRISIFT_BINARY" in os.environ:
        binary = os.environ["TRISIFT_BINARY"]
    if binary is None:
        for root in (Path.cwd(), _JUDGE_BUILD_ROOT):
            artifact = root / "target" / "debug" / PRODUCT_COMMAND
            if os.path.lexists(artifact):
                binary = artifact
                break
    if binary is None:
        binary = shutil.which(PRODUCT_COMMAND)
    if binary is None:
        raise ProductNotFound(
            f"{PRODUCT_COMMAND!r} has no build artifact and was not found on PATH; "
            "set TRISIFT_BINARY or pass binary=..."
        )
    path = os.path.abspath(os.fspath(binary))
    if not (os.path.isfile(path) and os.access(path, os.X_OK)):
        raise ProductNotFound(f"product binary {path!r} is not an executable file")
    return path


def decode(data: bytes) -> str:
    """Decode ``data`` as strict UTF-8 and return the text.

    Raises ``UnicodeDecodeError`` on invalid input; no replacement characters
    are ever introduced by the harness.
    """
    return data.decode("utf-8", errors="strict")


def run_trisift(
    args: Sequence[Arg],
    *,
    cwd: PathArg,
    stdin: Union[bytes, str, None] = None,
    env: Optional[Mapping[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    binary: Optional[PathArg] = None,
    merge_stderr: bool = False,
) -> RunResult:
    """Run the product once to completion and return a :class:`RunResult`.

    ``args`` is the argument list after the program name (subcommand, options,
    pattern, paths — exactly as a user would type them, no shell involved).
    ``cwd`` is required so no run ever touches the suite's own directory.
    Standard output and standard error are pipes, never a terminal.
    ``stdin`` bytes (or UTF-8 encoded str) are fed on standard input; with
    ``None`` standard input is ``/dev/null``.  ``env`` follows the module
    convention (``None`` inherits ``os.environ``).  With ``merge_stderr`` the
    two streams share one pipe, so ``stdout`` holds both in write order and
    ``stderr`` is ``b""``.

    The exit status is returned, never checked.  Raises
    :class:`ProductNotFound` if the binary cannot be started and
    :class:`ProductTimeout` (after killing the process) if it runs longer
    than ``timeout`` seconds.
    """
    argv = _argv(args, binary)
    data = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
    try:
        proc = subprocess.Popen(
            argv,
            cwd=os.fspath(cwd),
            env=_env(env),
            stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        )
    except OSError as exc:
        raise ProductNotFound(f"cannot start {_show_argv(argv)}: {exc}") from exc
    try:
        out, err = proc.communicate(input=data, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        out, err = proc.communicate()
        raise ProductTimeout(argv, timeout, out or b"", err or b"") from exc
    return RunResult(tuple(argv), os.fspath(cwd), proc.returncode, out or b"", err or b"")


def run_in_pty(
    args: Sequence[Arg],
    *,
    cwd: PathArg,
    env: Optional[Mapping[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    binary: Optional[PathArg] = None,
    rows: int = 24,
    cols: int = 80,
) -> RunResult:
    """Run the product with standard output on a pseudo-terminal.

    Returns a :class:`RunResult` whose ``stdout`` is every byte the process
    wrote to the terminal and whose ``stderr`` comes from a separate,
    non-terminal capture.  Standard input is ``/dev/null``.  Output
    post-processing on the terminal is switched off, so ``stdout`` holds the
    bytes as written (no ``\\n`` to ``\\r\\n`` translation).  The terminal
    reports a ``rows`` x ``cols`` window.  ``env`` is used as given; set
    ``TERM`` there if a test depends on it.

    The exit status is returned, never checked.  Raises
    :class:`ProductNotFound` if the binary cannot be started and
    :class:`ProductTimeout` (after killing the process) on timeout.
    """
    argv = _argv(args, binary)
    master, slave = pty.openpty()
    try:
        attrs = termios.tcgetattr(slave)
        attrs[1] &= ~termios.OPOST
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        with tempfile.TemporaryFile() as err_file:
            try:
                proc = subprocess.Popen(
                    argv,
                    cwd=os.fspath(cwd),
                    env=_env(env),
                    stdin=subprocess.DEVNULL,
                    stdout=slave,
                    stderr=err_file,
                    start_new_session=True,
                )
            except OSError as exc:
                raise ProductNotFound(f"cannot start {_show_argv(argv)}: {exc}") from exc
            os.close(slave)
            slave = -1
            chunks = []
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    proc.kill()
                    proc.wait()
                    err_file.seek(0)
                    raise ProductTimeout(argv, timeout, b"".join(chunks), err_file.read())
                ready, _, _ = select.select([master], [], [], min(remaining, 0.1))
                if not ready:
                    continue
                try:
                    chunk = os.read(master, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:  # every slave end closed
                        break
                    raise
                if not chunk:
                    break
                chunks.append(chunk)
            try:
                code = proc.wait(timeout=max(deadline - time.monotonic(), 0.1))
            except subprocess.TimeoutExpired as exc:
                proc.kill()
                proc.wait()
                err_file.seek(0)
                raise ProductTimeout(argv, timeout, b"".join(chunks), err_file.read()) from exc
            err_file.seek(0)
            err = err_file.read()
    finally:
        os.close(master)
        if slave != -1:
            os.close(slave)
    return RunResult(tuple(argv), os.fspath(cwd), code, b"".join(chunks), err)


class BackgroundProcess:
    """A product process kept running while the test interacts with it.

    Use as a context manager::

        with BackgroundProcess(["serve", str(root)], cwd=root) as proc:
            ...
        proc.result  # RunResult once stopped

    ``args``/``cwd``/``env``/``binary`` mean the same as for
    :func:`run_trisift`.  Standard input is ``/dev/null``; stdout and stderr go
    to temporary files that can be read at any time with
    :meth:`read_stdout` / :meth:`read_stderr` (they show every write the
    process has made so far).  The process runs in its own session, so
    signals sent to the test runner's terminal do not reach it.

    Leaving the ``with`` block stops the process with ``stop_signal`` (see
    :meth:`stop`).  If it does not exit within ``stop_timeout`` seconds it is
    killed and :class:`ProcessStopTimeout` is raised, unless another
    exception is already propagating out of the block (that one is kept).
    """

    def __init__(
        self,
        args: Sequence[Arg],
        *,
        cwd: PathArg,
        env: Optional[Mapping[str, str]] = None,
        binary: Optional[PathArg] = None,
        stop_signal: int = signal.SIGINT,
        stop_timeout: float = 30.0,
    ):
        self.argv = _argv(args, binary)
        self.cwd = os.fspath(cwd)
        self._env = _env(env)
        self.stop_signal = stop_signal
        self.stop_timeout = stop_timeout
        self.proc: Optional[subprocess.Popen] = None
        self.result: Optional[RunResult] = None
        self._out = None
        self._err = None

    def start(self) -> "BackgroundProcess":
        """Spawn the process and return ``self``.

        Raises :class:`ProductNotFound` if it cannot be started.  Calling it
        twice raises ``RuntimeError``.
        """
        if self.proc is not None:
            raise RuntimeError("BackgroundProcess already started")
        self._out = tempfile.TemporaryFile()
        self._err = tempfile.TemporaryFile()
        try:
            self.proc = subprocess.Popen(
                self.argv,
                cwd=self.cwd,
                env=self._env,
                stdin=subprocess.DEVNULL,
                stdout=self._out,
                stderr=self._err,
                start_new_session=True,
            )
        except OSError as exc:
            self._out.close()
            self._err.close()
            raise ProductNotFound(f"cannot start {_show_argv(self.argv)}: {exc}") from exc
        return self

    @property
    def pid(self) -> int:
        """Process id of the spawned process (``RuntimeError`` if not started)."""
        return self._require().pid

    def poll(self) -> Optional[int]:
        """Return the exit status if the process has exited, else ``None``."""
        return self._require().poll()

    def read_stdout(self) -> bytes:
        """Return every byte written to stdout so far."""
        return _read_all(self._out)

    def read_stderr(self) -> bytes:
        """Return every byte written to stderr so far."""
        return _read_all(self._err)

    def raise_if_exited(self) -> None:
        """Return ``None`` while the process runs; raise :class:`ProcessExited` once it has exited."""
        code = self.poll()
        if code is not None:
            raise ProcessExited(self.argv, code, self.read_stdout(), self.read_stderr())

    def signal(self, sig: int) -> None:
        """Send ``sig`` to the process.  Raises ``ProcessLookupError`` if it is gone."""
        os.kill(self.pid, sig)

    def wait(self, timeout: float) -> RunResult:
        """Wait up to ``timeout`` seconds for the process to exit by itself.

        Returns the :class:`RunResult` (also stored in ``self.result``).
        Raises :class:`ProductTimeout` if it is still running; the process is
        left running in that case.
        """
        proc = self._require()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ProductTimeout(self.argv, timeout, self.read_stdout(), self.read_stderr()) from exc
        return self._finish()

    def stop(self, sig: Optional[int] = None, timeout: Optional[float] = None) -> RunResult:
        """Stop the process and return its :class:`RunResult`.

        Sends ``sig`` (default ``stop_signal``) unless the process already
        exited, then waits up to ``timeout`` seconds (default
        ``stop_timeout``).  If it is still alive it is killed with SIGKILL,
        reaped, and :class:`ProcessStopTimeout` is raised.  The exit status is
        returned, never checked.
        """
        proc = self._require()
        sig = self.stop_signal if sig is None else sig
        timeout = self.stop_timeout if timeout is None else timeout
        if proc.poll() is None:
            try:
                os.kill(proc.pid, sig)
            except ProcessLookupError:
                pass  # exited between poll() and kill(); reaped below
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                self._finish()
                raise ProcessStopTimeout(
                    f"{_show_argv(self.argv)} ignored signal {sig} for {timeout}s and was killed; "
                    f"stderr={_clip(self.read_stderr())!r}"
                )
        return self._finish()

    def __enter__(self) -> "BackgroundProcess":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.proc is None:
            return
        try:
            if self.result is None:
                self.stop()
        except ProcessStopTimeout:
            if exc_type is None:
                raise
        finally:
            for f in (self._out, self._err):
                if f is not None and not f.closed:
                    f.close()

    def _require(self) -> subprocess.Popen:
        if self.proc is None:
            raise RuntimeError("BackgroundProcess not started")
        return self.proc

    def _finish(self) -> RunResult:
        if self.result is None:
            self.result = RunResult(
                tuple(self.argv), self.cwd, self._require().returncode,
                self.read_stdout(), self.read_stderr(),
            )
        return self.result


# ---------------------------------------------------------------------------
# Waiting
# ---------------------------------------------------------------------------


def wait_until(
    predicate: Callable[[], Any],
    *,
    timeout: float,
    interval: float = 0.05,
    message: str = "condition not met",
    process: Optional[BackgroundProcess] = None,
    retry_on: tuple = (),
) -> Any:
    """Call ``predicate`` until it returns a truthy value and return that value.

    Polls every ``interval`` seconds for at most ``timeout`` seconds.
    Exceptions of the types in ``retry_on`` count as "not yet" and are kept
    for the error message; any other exception propagates immediately.  If
    ``process`` is given and it has exited, :class:`ProcessExited` is raised
    at once.  On timeout :class:`WaitTimeout` is raised with ``message`` and
    the last value/exception.
    """
    deadline = time.monotonic() + timeout
    last_value: Any = None
    last_error: Optional[BaseException] = None
    while True:
        if process is not None:
            process.raise_if_exited()
        try:
            last_value = predicate()
            last_error = None
            if last_value:
                return last_value
        except retry_on as exc:  # type: ignore[misc]
            last_error = exc
        if time.monotonic() >= deadline:
            raise WaitTimeout(f"{message} within {timeout}s", last_value, last_error)
        time.sleep(interval)


def wait_for_json_file(
    path: PathArg,
    *,
    timeout: float,
    process: Optional[BackgroundProcess] = None,
) -> Any:
    """Wait until ``path`` exists and holds a complete JSON document; return it parsed.

    A missing, empty or partially written file counts as "not yet".  Raises
    :class:`WaitTimeout` (with the last read error) or, when ``process`` has
    exited meanwhile, :class:`ProcessExited`.
    """
    p = Path(path)

    def read() -> Any:
        doc = json.loads(p.read_bytes())
        return (doc,)  # wrapped so a falsy document still ends the wait

    return wait_until(
        read, timeout=timeout, message=f"no complete JSON document at {p}",
        process=process, retry_on=(FileNotFoundError, ValueError),
    )[0]


def wait_for_tcp(
    port: int,
    *,
    host: str = "127.0.0.1",
    timeout: float,
    process: Optional[BackgroundProcess] = None,
) -> None:
    """Wait until a TCP connection to ``host:port`` succeeds; return ``None``.

    The probe connection is closed immediately without sending anything.
    Raises :class:`WaitTimeout` (with the last connection error) or, when
    ``process`` has exited meanwhile, :class:`ProcessExited`.
    """

    def probe() -> bool:
        with socket.create_connection((host, port), timeout=1.0):
            return True

    wait_until(
        probe, timeout=timeout, message=f"no TCP listener at {host}:{port}",
        process=process, retry_on=(OSError,),
    )


def pid_alive(pid: int) -> bool:
    """Return whether a process with ``pid`` exists (signal-0 probe).

    An exited child of this test process that has not been reaped yet still
    counts as existing.  A process owned by another user counts as existing.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------------------
# Line-oriented TCP client
# ---------------------------------------------------------------------------


class LineConnection:
    """One TCP connection that exchanges newline-terminated messages.

    Use as a context manager; the socket is closed on exit.  ``host``
    defaults to the IPv4 loopback address.  ``timeout`` bounds every
    connect, send and receive; exceeding it raises ``socket.timeout``
    (``TimeoutError``).  Several requests may be sent on one connection.
    """

    def __init__(self, port: int, *, host: str = "127.0.0.1", timeout: float = 30.0):
        self.port = port
        self.host = host
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buf = b""

    def send(self, message: Union[bytes, str, Mapping, list]) -> None:
        """Send one message; return ``None``.

        A mapping or list is encoded as compact UTF-8 JSON.  ``bytes`` and
        ``str`` are sent verbatim (str as UTF-8), which lets a test send a
        line that is not JSON.  A trailing newline is appended when the
        message does not already end with one.
        """
        if isinstance(message, (Mapping, list)):
            data = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        elif isinstance(message, str):
            data = message.encode("utf-8")
        elif isinstance(message, bytes):
            data = message
        else:
            raise TypeError(f"cannot send {type(message).__name__}")
        if not data.endswith(b"\n"):
            data += b"\n"
        self.sock.sendall(data)

    def recv_line(self) -> bytes:
        """Return the next received line without its trailing ``\\n``.

        Raises :class:`ConnectionClosed` (with any partial data) if the peer
        closes first, and ``socket.timeout`` if nothing complete arrives in
        time.
        """
        while b"\n" not in self._buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionClosed(
                    f"{self.host}:{self.port} closed the connection; partial data={self._buf!r}"
                )
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line

    def request(self, message: Union[bytes, str, Mapping, list]) -> Any:
        """Send ``message`` (see :meth:`send`), read one line, return it parsed as JSON.

        Raises ``json.JSONDecodeError`` (a ``ValueError``) whose message
        includes the raw line if the reply is not JSON, plus the errors of
        :meth:`recv_line`.  The reply's content is not inspected.
        """
        self.send(message)
        line = self.recv_line()
        try:
            return json.loads(line)
        except ValueError as exc:
            raise json.JSONDecodeError(f"reply is not JSON: {line!r}", exc.doc, exc.pos) from exc

    def close(self) -> None:
        """Close the socket; return ``None``.  Safe to call twice."""
        self.sock.close()

    def __enter__(self) -> "LineConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def line_request(
    port: int,
    message: Union[bytes, str, Mapping, list],
    *,
    host: str = "127.0.0.1",
    timeout: float = 30.0,
) -> Any:
    """Open a fresh :class:`LineConnection`, send one message, return the parsed JSON reply.

    Same encoding and error semantics as :meth:`LineConnection.request`;
    socket errors (``OSError``) propagate unchanged.
    """
    with LineConnection(port, host=host, timeout=timeout) as conn:
        return conn.request(message)


def jsonrpc_request(method: str, params: Any = None, id: Union[int, str] = 1) -> dict:
    """Return a JSON-RPC 2.0 request object (a dict) for ``method``.

    ``params`` is included only when not ``None``.  The method names and
    parameter shapes are the caller's; this only builds the standard envelope.
    """
    req: dict = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        req["params"] = params
    return req


# ---------------------------------------------------------------------------
# Fixtures on disk
# ---------------------------------------------------------------------------

# One printed, overridable seed controls every authored random choice.
TEST_SEED = os.environ.get("TRISIFT_TEST_SEED", str(secrets.randbits(64)))
print(f"TRISIFT_TEST_SEED={TEST_SEED}", file=sys.stderr, flush=True)
_random_streams = {}


def fixture_random(label="fixtures"):
    """A reproducible stream for this test and purpose, independent of test order."""
    node = os.environ.get("PYTEST_CURRENT_TEST", "collection")
    key = (node, label)
    if key not in _random_streams:
        seed = hashlib.sha256((TEST_SEED + "\0" + node + "\0" + label).encode()).digest()
        _random_streams[key] = random.Random(seed)
    return _random_streams[key]


_issued_tokens: set = set()


def unique_token(prefix: str = "tk", length: int = 12) -> str:
    """Return a fresh random marker word: ``prefix`` + ``length`` lowercase ASCII letters.

    Letters only, so the token is a single regex word, has no
    metacharacters and no case variants inside it.  No token is returned
    twice in one test process.
    """
    while True:
        tok = prefix + "".join(fixture_random("markers").choice(string.ascii_lowercase) for _ in range(length))
        if tok not in _issued_tokens:
            _issued_tokens.add(tok)
            return tok


def make_tree(root: PathArg, files: Mapping[str, Union[bytes, str]]) -> Path:
    """Create the files in ``files`` under ``root`` and return ``root`` as a ``Path``.

    Keys are ``/``-separated paths relative to ``root``; parent directories
    are created.  ``bytes`` values are written verbatim; ``str`` values are
    written as UTF-8 with no newline translation.  A key that is absolute or
    climbs out of ``root`` raises ``ValueError``; existing files are
    overwritten.
    """
    base = Path(root)
    base.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        parts = Path(rel).parts
        if Path(rel).is_absolute() or ".." in parts or not parts:
            raise ValueError(f"fixture path {rel!r} must be relative and stay inside the root")
        target = base.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return base


def make_text_file(
    path: PathArg,
    size: int,
    token: Optional[str] = None,
    *,
    line_width: int = 100,
) -> Path:
    """Write a text file of exactly ``size`` bytes and return its ``Path``.

    Content is ASCII lines of at most ``line_width`` bytes (newline
    included) containing no NUL byte; the file is fully written, never
    sparse.  When ``size`` > 0 the last byte is ``\\n``.  If ``token`` is
    given, the first line is ``token`` followed by ``\\n``; the filler lines
    consist of ``x`` characters only.  Raises ``ValueError`` if ``size`` is
    negative or too small for the token line.
    """
    if size < 0:
        raise ValueError("size must be >= 0")
    if line_width < 2:
        raise ValueError("line_width must be >= 2")
    head = (token + "\n").encode("ascii") if token is not None else b""
    if len(head) > size:
        raise ValueError(f"size {size} cannot hold the token line ({len(head)} bytes)")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = b"x" * (line_width - 1) + b"\n"
    block = line * max(1, (1 << 20) // line_width)
    remaining = size - len(head)
    with open(p, "wb") as f:
        f.write(head)
        while remaining >= len(block):
            f.write(block)
            remaining -= len(block)
        while remaining >= len(line):
            f.write(line)
            remaining -= len(line)
        if remaining:
            f.write(b"x" * (remaining - 1) + b"\n")
    actual = p.stat().st_size
    if actual != size:
        raise HarnessError(f"wrote {actual} bytes to {p}, wanted {size}")
    return p


def make_sparse_file(path: PathArg, size: int) -> Path:
    """Create a sparse file of exactly ``size`` bytes (all holes) and return its ``Path``.

    Its content reads as NUL bytes.  Use it only where content is never
    read; size-boundary tests on searched content need :func:`make_text_file`.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.truncate(size)
    return p


# ---------------------------------------------------------------------------
# Environment and git
# ---------------------------------------------------------------------------

_GIT_IDENTITY = (
    "-c", "user.name=trisift-tests",
    "-c", "user.email=trisift-tests@example.invalid",
    "-c", "commit.gpgsign=false",
    "-c", "init.defaultBranch=main",
)


def hermetic_env(home: PathArg, extra: Optional[Mapping[str, str]] = None) -> dict:
    """Return a complete environment dict that hides the user's personal configuration.

    Starts from ``os.environ``, points ``HOME`` at ``home`` (created if
    missing) and ``XDG_CONFIG_HOME`` at ``home/.config``, sets
    ``GIT_CONFIG_NOSYSTEM=1``, and removes every other ``GIT_*`` variable,
    so neither git nor the product sees a global or system git config or
    global ignore file unless the test writes one under ``home``.  ``extra``
    entries are applied last.
    """
    h = Path(home)
    h.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["HOME"] = str(h)
    env["XDG_CONFIG_HOME"] = str(h / ".config")
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    if extra:
        env.update(extra)
    return env


def git(root: PathArg, *args: str, env: Optional[Mapping[str, str]] = None) -> RunResult:
    """Run ``git -C root <args>`` and return its :class:`RunResult`.

    A fixed test identity, unsigned commits and branch name ``main`` are
    passed with ``-c``.  With ``env=None`` git sees ``os.environ`` plus
    ``GIT_CONFIG_NOSYSTEM=1`` and ``GIT_CONFIG_GLOBAL`` pointing at an empty
    file, so personal config cannot leak in; a given ``env`` is used verbatim.
    Raises :class:`GitError` if git is not installed or exits non-zero.
    """
    exe = shutil.which("git")
    if exe is None:
        raise GitError("git is not installed but the test needs a real git repository")
    if env is None:
        e = dict(os.environ)
        e["GIT_CONFIG_NOSYSTEM"] = "1"
        e["GIT_CONFIG_GLOBAL"] = os.devnull
    else:
        e = dict(env)
    argv = [exe, "-C", os.fspath(root), *_GIT_IDENTITY, *args]
    proc = subprocess.run(argv, env=e, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    result = RunResult(tuple(argv), os.fspath(root), proc.returncode, proc.stdout, proc.stderr)
    if proc.returncode != 0:
        raise GitError(f"git failed: {result.describe()}")
    return result


def git_init(
    root: PathArg,
    config: Optional[Mapping[str, str]] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> Path:
    """Make ``root`` (created if missing) a git repository and return it as a ``Path``.

    Each ``config`` item is written to the repository's local config with
    ``git config key value``.  ``env`` as for :func:`git`.  Raises
    :class:`GitError` on any git failure.
    """
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    git(p, "init", "-q", env=env)
    for key, value in (config or {}).items():
        git(p, "config", key, value, env=env)
    return p


def git_add(
    root: PathArg,
    paths: Sequence[PathArg],
    *,
    force: bool = False,
    env: Optional[Mapping[str, str]] = None,
) -> None:
    """Stage ``paths`` (relative to ``root``) in the index of the repository at ``root``.

    ``force`` passes ``-f`` so ignored paths can be tracked.  Returns
    ``None``; raises :class:`GitError` on failure.
    """
    args = ["add"] + (["-f"] if force else []) + ["--"] + [os.fspath(x) for x in paths]
    git(root, *args, env=env)


@contextmanager
def make_unreadable(path: PathArg, mode: int = 0) -> Iterator[Path]:
    """Temporarily chmod ``path`` to ``mode`` and prove the denial is real.

    Yields ``path`` as a ``Path``.  After the chmod, every access the mode
    removes from the owner is attempted: read (list a directory / open a
    file for reading), write (create a file in a directory / open a file
    for appending) and, for directories, search (stat an entry inside).  If
    any of them still succeeds — e.g. when running as root —
    :class:`PermissionNotEffective` is raised.  The original mode is
    restored on exit, also when the probe or the test fails.
    """
    p = Path(path)
    original = stat.S_IMODE(p.stat().st_mode)
    is_dir = p.is_dir()
    os.chmod(p, mode)
    try:
        leaks = []
        if not mode & stat.S_IRUSR and _access_works(lambda: os.listdir(p) if is_dir else open(p, "rb").close()):
            leaks.append("read")
        if not mode & stat.S_IWUSR and _access_works(lambda: _probe_write(p, is_dir)):
            leaks.append("write")
        if is_dir and not mode & stat.S_IXUSR and _access_works(lambda: os.stat(os.path.join(p, "perm-probe-entry"))):
            leaks.append("search")
        if leaks:
            raise PermissionNotEffective(
                f"chmod {oct(mode)} on {p} did not deny {', '.join(leaks)} access "
                f"(euid={os.geteuid()}); the test precondition cannot be built"
            )
        yield p
    finally:
        os.chmod(p, original)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _argv(args: Sequence[Arg], binary: Optional[PathArg]) -> list:
    if isinstance(args, (str, bytes)):
        raise TypeError("args must be a sequence of arguments, not a single string")
    return [trisift_binary(binary), *args]


def _env(env: Optional[Mapping[str, str]]) -> Optional[dict]:
    return None if env is None else dict(env)


def _read_all(f) -> bytes:
    if f is None:
        raise RuntimeError("BackgroundProcess not started")
    f.flush()
    return os.pread(f.fileno(), os.fstat(f.fileno()).st_size, 0)


def _probe_write(p: Path, is_dir: bool) -> None:
    if is_dir:
        probe = p / f".perm-probe-{fixture_random("permissions").getrandbits(32):08x}"
        probe.touch()
        probe.unlink()
    else:
        open(p, "ab").close()


def _access_works(*attempts: Callable[[], Any]) -> bool:
    """True if any attempt completes without a permission error."""
    for attempt in attempts:
        try:
            attempt()
        except PermissionError:
            continue
        except FileNotFoundError:
            # Reaching "no such entry" means the directory was searchable.
            return True
        return True
    return False


def _show_argv(argv: Sequence[Arg]) -> str:
    return " ".join(repr(os.fsdecode(a)) if isinstance(a, bytes) else repr(os.fspath(a)) for a in argv)


def _clip(data: bytes, limit: int = 2000) -> bytes:
    return data if len(data) <= limit else data[:limit] + b"...[%d more bytes]" % (len(data) - limit)


def lf_lines(text, keepends=False):
    """Split declared LF records without treating Unicode text as separators."""
    if not text:
        return []
    sep = b"\n" if isinstance(text, bytes) else "\n"
    parts = text.split(sep)
    lines = [part + sep if keepends else part for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines
