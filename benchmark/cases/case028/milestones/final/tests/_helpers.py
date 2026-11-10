# feature: F00
"""Shared, assertion-free drivers for the Linux pytest harness.

Commands are argument sequences, never shell text. Paths to product binaries,
Go build targets, observer sources, and protocol labels belong to callers.
Use build_go for the CLI, generator, Go observer, or independent native Go
program; use run_process or Process for the resulting executable. Observer
sources must use documented public imports and serialize their own observations
without replacing invalid values, dynamic types, or errors with guessed values.

All captured streams are bytes. Product failures remain raw exit statuses;
helper failures raise HelperError with the original exception chained when
available. No product success condition, diagnostic schema, or expected result
is supplied here. Protocol schemas that the plan marks as unpublished must be
settled by the public contract before callers use them.
"""

import contextlib as _contextlib
import dataclasses as _dataclasses
import http.server as _http_server
import json as _json
import math as _math
import os as _os
from pathlib import Path as _Path
import re as _re
import selectors as _selectors
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import threading as _threading
import time as _time

_go_build_cache = _tempfile.TemporaryDirectory(prefix="suite-go-build-")


__all__ = (
    "HelperError", "HelperTimeout", "ProcessResult", "Process", "run_process",
    "monotonic", "Workspace", "isolated_workspace", "write_files",
    "read_bytes", "BuildResult", "build_go", "parse_json", "parse_json_lines",
    "parse_events", "HTTPService", "serve_directory",
)


class HelperError(AssertionError):
    """Infrastructure failure, not a product outcome.

    Construction returns an exception; result is an optional ProcessResult
    containing raw output and the observed exit status (None if still running).
    Filesystem, launch, and parser exceptions are retained through chaining.
    """

    def __init__(self, message, *, result=None):
        self.result = result
        if result is not None:
            message += (
                f"\ncommand: {result.argv!r}\ncwd: {result.cwd}"
                f"\nreturncode: {result.returncode!r}"
                f"\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
            )
        super().__init__(message)


class HelperTimeout(HelperError):
    """A helper deadline expired; partial bytes/status are in result, not returned.

    This is a failed observation, never a synthetic product timeout status.
    """


def monotonic():
    """Return monotonic seconds for external intervals; no process status applies."""
    return _time.monotonic()


def _seconds(value):
    value = float(value)
    if not _math.isfinite(value) or value <= 0:
        raise ValueError("Timeout must be finite and greater than zero")
    return value


def _command(argv):
    if isinstance(argv, (str, bytes, _os.PathLike)):
        raise TypeError("Command must be an argument sequence, not shell text")
    argv = tuple(_os.fspath(arg) for arg in argv)
    if not argv or not all(isinstance(arg, str) for arg in argv):
        raise ValueError("Command must contain text arguments and an executable")
    return argv


def _bytes(value):
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, bytes):
        return value
    raise TypeError("Input must be bytes or UTF-8 text")


@_dataclasses.dataclass(frozen=True)
class ProcessResult:
    """Raw process observation with separate bytes and a monotonic elapsed time.

    returncode is the OS status: zero, positive exit code, or negative signal.
    Only partial results attached to exceptions/snapshot() may have None.
    argv, cwd, and env record the invocation; no status implies helper success.
    """

    argv: tuple
    cwd: _Path
    env: dict = _dataclasses.field(repr=False)
    returncode: object
    stdout: bytes
    stderr: bytes
    elapsed: float


class Process:
    """Own one POSIX process group with pipes and an overall finite deadline.

    Use as a context manager. Output is byte-exact and never merged; input is
    UTF-8 text or bytes. Nonzero exits are returned by finish(), not raised.
    Launch/I/O failures raise HelperError, waits raise HelperTimeout. Cleanup
    kills only this invocation's process group and has a separate finite bound.
    This is a pipe driver, not a pseudo-terminal or a protocol implementation.
    """

    def __init__(self, argv, *, cwd, env=None, timeout=30.0, cleanup_timeout=5.0):
        self.argv = _command(argv)
        self.cwd = _Path(cwd).resolve()
        self.env = dict(_os.environ if env is None else env)
        timeout = _seconds(timeout)
        self._cleanup_timeout = _seconds(cleanup_timeout)
        self._started = monotonic()
        self._deadline = self._started + timeout
        self._ended = None
        self._output = {"stdout": bytearray(), "stderr": bytearray()}
        self._pending = memoryview(b"")
        self._closed = False
        self._selector = _selectors.DefaultSelector()
        try:
            self._process = _subprocess.Popen(
                self.argv, cwd=self.cwd, env=self.env,
                stdin=_subprocess.PIPE, stdout=_subprocess.PIPE,
                stderr=_subprocess.PIPE, bufsize=0, start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            self._selector.close()
            raise HelperError(f"Cannot launch {self.argv!r} in {self.cwd}") from exc
        try:
            for channel in ("stdin", "stdout", "stderr"):
                stream = getattr(self._process, channel)
                _os.set_blocking(stream.fileno(), False)
                if channel != "stdin":
                    self._selector.register(stream, _selectors.EVENT_READ, channel)
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False

    def snapshot(self):
        """Return captured bytes/status so far; None means running, not success.

        Does not wait or consume output. A closed handle remains inspectable.
        """
        return ProcessResult(
            self.argv, self.cwd, dict(self.env), self._process.poll(),
            bytes(self._output["stdout"]), bytes(self._output["stderr"]),
            (self._ended if self._ended is not None else monotonic()) - self._started,
        )

    def _limit(self, timeout):
        if self._closed:
            raise HelperError("Process handle is closed", result=self.snapshot())
        if timeout is None:
            return self._deadline
        return min(self._deadline, monotonic() + _seconds(timeout))

    def _pump(self, deadline):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise HelperTimeout("Process observation deadline expired", result=self.snapshot())
        try:
            events = self._selector.select(min(remaining, 0.1))
            for key, _ in events:
                if key.data == "stdin":
                    try:
                        count = _os.write(key.fd, self._pending[:65536])
                    except BlockingIOError:
                        continue
                    self._pending = self._pending[count:]
                    if not self._pending:
                        self._selector.unregister(key.fileobj)
                else:
                    try:
                        chunk = _os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    if chunk:
                        self._output[key.data].extend(chunk)
                    else:
                        self._selector.unregister(key.fileobj)
                        key.fileobj.close()
        except OSError as exc:
            raise HelperError("Process pipe operation failed", result=self.snapshot()) from exc

    def send(self, data, *, timeout=None):
        """Write all data while draining both outputs; return None, not a status.

        Does not add a newline or close input. Broken pipes raise HelperError;
        blocked writes raise HelperTimeout with bytes observed so far.
        """
        deadline = self._limit(timeout)
        data = _bytes(data)
        if self._process.stdin.closed:
            raise HelperError("Process input is closed", result=self.snapshot())
        if self._pending:
            raise HelperError("A previous input write is incomplete", result=self.snapshot())
        if not data:
            return
        self._pending = memoryview(data)
        self._selector.register(self._process.stdin, _selectors.EVENT_WRITE, "stdin")
        while self._pending:
            self._pump(deadline)

    def eof(self):
        """Close stdin and return None; does not wait or infer an exit status.

        Repeated EOF is harmless; unfinished writes and close failures raise.
        """
        if self._pending:
            raise HelperError("Cannot close input during an incomplete write", result=self.snapshot())
        try:
            self._process.stdin.close()
        except OSError as exc:
            raise HelperError("Cannot close process input", result=self.snapshot()) from exc

    def send_signal(self, signum, *, group=False):
        """Send an explicit signal; return None without fabricating an exit code.

        By default signal only the child; group=True addresses its owned group.
        Signaling an exited child or an OS delivery failure raises HelperError.
        """
        self._limit(None)
        if self._process.poll() is not None:
            raise HelperError("Cannot signal an exited process", result=self.snapshot())
        try:
            if group:
                _os.killpg(self._process.pid, signum)
            else:
                _os.kill(self._process.pid, signum)
        except OSError as exc:
            raise HelperError("Signal delivery failed", result=self.snapshot()) from exc

    def read_until(self, marker, *, channel="stdout", start=0, timeout=None):
        """Return bytes from start through a caller-specified literal marker.

        Does not consume stored output or parse a result. Use explicit public
        prompt/delimiter bytes, not inferred positions. Early EOF raises
        HelperError; missing markers at the deadline raise HelperTimeout.
        Status and the complete transcript remain available through snapshot().
        """
        deadline = self._limit(timeout)
        marker = _bytes(marker)
        if not marker or channel not in self._output or start < 0:
            raise ValueError("Expected a nonempty marker, stdout/stderr, and nonnegative start")
        while True:
            captured = self._output[channel]
            position = captured.find(marker, start)
            if position >= 0:
                return bytes(captured[start:position + len(marker)])
            if getattr(self._process, channel).closed:
                raise HelperError("Output ended before the requested marker", result=self.snapshot())
            self._pump(deadline)

    def finish(self, *, timeout=None, close_stdin=True):
        """Wait for exit and both output EOFs; return ProcessResult at any status.

        Closes input by default. Timeouts include inherited pipes that never
        close; they raise HelperTimeout rather than returning partial success.
        """
        deadline = self._limit(timeout)
        if close_stdin:
            self.eof()
        while self._process.poll() is None or self._selector.get_map():
            self._pump(deadline)
        if self._ended is None:
            self._ended = monotonic()
        return self.snapshot()

    def close(self):
        """Kill the owned group, reap the child, and close pipes; return None.

        Idempotent; no unrelated processes are addressed. Cleanup errors raise
        HelperError and cleanup timeouts raise HelperTimeout, never a status.
        """
        if self._closed:
            return
        self._closed = True
        try:
            try:
                _os.killpg(self._process.pid, _signal.SIGKILL)
            except ProcessLookupError:
                # Absence of this owned group is the requested cleanup state.
                pass
            self._process.wait(timeout=self._cleanup_timeout)
        except _subprocess.TimeoutExpired as exc:
            raise HelperTimeout("Process cleanup deadline expired", result=self.snapshot()) from exc
        except OSError as exc:
            raise HelperError("Process cleanup failed", result=self.snapshot()) from exc
        finally:
            self._selector.close()
            for channel in ("stdin", "stdout", "stderr"):
                getattr(self._process, channel).close()


def run_process(argv, *, cwd, env=None, input=b"", timeout=30.0, cleanup_timeout=5.0):
    """Send input, send EOF, and return ProcessResult, including nonzero status.

    The deadline covers input and output together. Launch, I/O, and deadline
    failures raise with available raw output; the owned group is always cleaned.
    env is a complete environment when supplied, not an implicit overlay.
    """
    with Process(argv, cwd=cwd, env=env, timeout=timeout,
                 cleanup_timeout=cleanup_timeout) as process:
        process.send(input)
        return process.finish()


@_dataclasses.dataclass(frozen=True)
class Workspace:
    """Temporary root, program cwd, and isolated environment; no exit status.

    Paths live only inside isolated_workspace(). env is a caller-editable copy;
    changing it never changes the parent process environment or HOME.
    """

    root: _Path
    cwd: _Path
    env: dict = _dataclasses.field(repr=False)


@_contextlib.contextmanager
def isolated_workspace(*, parent=None, base_env=None, overrides=None):
    """Yield Workspace with real empty directories, removing it on context exit.

    Isolates XDG_CACHE_HOME, GOMODCACHE, GOPATH, and TMPDIR. Go compilation
    uses a fresh cache shared only within this test process. Go uses
    the local toolchain, ignores user Go settings/workspaces, and receives no
    inherited GOFLAGS. HOME is preserved. Product-specific variables and proxy
    policy are supplied explicitly in overrides; None removes an env key.
    Filesystem/setup/cleanup failures raise HelperError; no exit status applies.
    """
    try:
        temporary = _tempfile.TemporaryDirectory(prefix="suite-", dir=parent)
    except OSError as exc:
        raise HelperError("Cannot create isolated workspace") from exc
    try:
        root = _Path(temporary.name).resolve()
        cwd = root / "work"
        env = dict(_os.environ if base_env is None else base_env)
        try:
            cwd.mkdir()
            for variable, directory in (
                ("XDG_CACHE_HOME", "xdg-cache"), ("GOMODCACHE", "go-modules"),
                ("GOPATH", "go-path"), ("TMPDIR", "tmp"),
            ):
                location = root / directory
                location.mkdir()
                env[variable] = str(location)
            env.update(GOTOOLCHAIN="local", GOENV="off", GOWORK="off", GOFLAGS="",
                       GOCACHE=_go_build_cache.name)
            for name, value in (overrides or {}).items():
                if name == "HOME":
                    raise ValueError("Workspace isolation must not replace HOME")
                if value is None:
                    env.pop(name, None)
                else:
                    env[name] = _os.fspath(value)
        except OSError as exc:
            raise HelperError("Cannot initialize isolated workspace") from exc
        yield Workspace(root, cwd, env)
    finally:
        try:
            temporary.cleanup()
        except OSError as exc:
            raise HelperError("Cannot remove isolated workspace") from exc


def write_files(root, files):
    """Write caller-supplied relative paths to bytes/text; return name-to-Path map.

    Creates parent directories, but refuses existing files, absolute paths and
    paths escaping root. Text is UTF-8 without newline conversion. Does not
    synthesize sources/data. Invalid arguments or I/O raise; no status applies.
    Earlier writes remain visible if a later write fails.
    """
    root = _Path(root).resolve()
    written = {}
    for name, contents in files.items():
        relative = _Path(name)
        target = (root / relative).resolve()
        if relative.is_absolute() or not target.is_relative_to(root) or target == root:
            raise ValueError(f"File path must stay below the workspace: {name!r}")
        payload = _bytes(contents)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(payload)
        except OSError as exc:
            raise HelperError(f"Cannot write input file {target}") from exc
        written[name] = target
    return written


def read_bytes(path):
    """Return exact file bytes; missing/unreadable files raise HelperError.

    No default, empty substitute, or process exit status is supplied.
    """
    try:
        return _Path(path).read_bytes()
    except OSError as exc:
        raise HelperError(f"Cannot read output file {path}") from exc


@_dataclasses.dataclass(frozen=True)
class BuildResult:
    """Fresh artifact path and raw version/build ProcessResults.

    Returned only after successful toolchain discovery and build; those statuses
    remain in toolchain and process. Failure raises with the failed transcript.
    No guarantee about product behavior or generated code semantics is implied.
    """

    artifact: _Path
    toolchain: ProcessResult
    process: ProcessResult


def build_go(go, target, *, cwd, output, env=None, flags=(), timeout=180.0,
             required_version=(1, 26)):
    """Build an explicit Go target/source with local Go; return BuildResult.

    go is an argument sequence (e.g. a caller-selected toolchain executable).
    cwd selects the module context, including for an external observer source.
    target is a package/file or sequence of files. No product import is generated.
    Use the same driver for an independent standard-library-only Go oracle.
    flags are Go build flags excluding -o; output must not exist. Existing
    artifacts, wrong Go version, tool failures, and missing output raise, with
    raw failed subprocess results attached. One deadline covers both commands.
    """
    command = _command(go)
    cwd = _Path(cwd).resolve()
    output = _Path(output)
    output = (cwd / output).resolve() if not output.is_absolute() else output.resolve()
    if output.exists() or output.is_symlink():
        raise HelperError(f"Build output must be fresh: {output}")
    if isinstance(flags, (str, bytes)):
        raise TypeError("Build flags must be an argument sequence")
    flags = tuple(flags)
    if any(flag == "-o" or flag.startswith("-o=") for flag in flags):
        raise ValueError("Use output to select the build destination")
    targets = (target,) if isinstance(target, (str, _os.PathLike)) else tuple(target)
    if not targets:
        raise ValueError("At least one explicit build target is required")
    build_env = dict(_os.environ if env is None else env)
    build_env["GOTOOLCHAIN"] = "local"
    # Ambient GOFLAGS could redirect output or silently select another build.
    build_env["GOFLAGS"] = ""
    build_env["GOENV"] = "off"
    build_env["GOWORK"] = "off"
    deadline = monotonic() + _seconds(timeout)

    def remaining():
        seconds = deadline - monotonic()
        if seconds <= 0:
            raise HelperTimeout("Go build deadline expired")
        return seconds

    version = run_process(command + ("env", "GOVERSION"), cwd=cwd,
                          env=build_env, timeout=remaining())
    if version.returncode != 0:
        raise HelperError("Cannot read local Go version", result=version)
    match = _re.fullmatch(rb"go([0-9]+)\.([0-9]+)(?:\.[0-9]+)?\s*", version.stdout)
    if match is None or tuple(map(int, match.groups())) != tuple(required_version):
        raise HelperError(f"Required local Go release is {required_version!r}", result=version)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HelperError(f"Cannot create build destination {output.parent}") from exc
    result = run_process(
        command + ("build",) + flags + ("-o", str(output)) + tuple(map(_os.fspath, targets)),
        cwd=cwd, env=build_env, timeout=remaining(),
    )
    if result.returncode != 0:
        raise HelperError("Go build failed", result=result)
    if not output.is_file():
        raise HelperError("Go build produced no artifact at the requested path", result=result)
    return BuildResult(output, version, result)


def _object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Duplicate JSON object field: {key!r}")
        obj[key] = value
    return obj


def _invalid_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


def parse_json(data):
    """Return a full JSON value without guessing fields or converting statuses.

    UTF-8, JSON syntax, duplicate-field, and nonstandard-number failures raise
    HelperError with their original cause. No substring extraction or defaults.
    """
    try:
        text = data.decode("utf-8") if isinstance(data, bytes) else data
        return _json.loads(text, object_pairs_hook=_object, parse_constant=_invalid_constant)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise HelperError("Cannot parse complete JSON payload") from exc


def parse_json_lines(data):
    """Return one parsed value per JSON line, in order; empty input returns [].

    Only a final newline is optional. Blank/malformed records raise HelperError;
    absent records are not invented. Exit statuses remain the caller's separate
    ProcessResult; semantic assertions and record schemas belong to callers.
    """
    text = _bytes(data)
    if not text:
        return []
    lines = text.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    result = []
    for number, line in enumerate(lines, 1):
        try:
            result.append(parse_json(line))
        except HelperError as exc:
            raise HelperError(f"Invalid JSON record on line {number}") from exc
    return result


def parse_events(data, *, prefix, event_field, allowed_events):
    """Return JSON event objects on explicitly labeled lines of the given channel.

    Caller supplies the public line prefix, field, and allowed event names.
    Unlabeled text is untouched in the original ProcessResult. No matching
    events returns []; malformed labeled JSON, missing fields, or unknown event
    names raise HelperError. Does not synthesize events from exit status/text.
    """
    prefix = _bytes(prefix)
    if not prefix or b"\n" in prefix:
        raise ValueError("Event prefix must be a nonempty single-line label")
    if isinstance(allowed_events, (str, bytes)):
        raise TypeError("Allowed event names must be a collection")
    allowed = frozenset(allowed_events)
    events = []
    for number, line in enumerate(_bytes(data).split(b"\n"), 1):
        if not line.startswith(prefix):
            continue
        event = parse_json(line[len(prefix):])
        if not isinstance(event, dict) or event_field not in event:
            raise HelperError(f"Missing event field on line {number}")
        name = event[event_field]
        if not isinstance(name, str) or name not in allowed:
            raise HelperError(f"Unknown event name on line {number}: {name!r}")
        events.append(event)
    return events


@_dataclasses.dataclass
class HTTPService:
    """Real file-server address and observed HTTP request/log records.

    url includes its bound port. requests contains method, path, response status,
    and request headers; logs contains server messages. Neither is an expected
    product result. Server errors raise when its context exits; no process status.
    Read records after requests complete or after the server context exits.
    """

    url: str
    requests: list
    logs: list


@_contextlib.contextmanager
def serve_directory(directory, *, host="127.0.0.1", port=0,
                    request_timeout=5.0, shutdown_timeout=10.0):
    """Yield HTTPService serving actual files from directory, then stop it.

    A real HTTP server binds the supplied interface (port 0 asks the OS for a
    free port); no canned responses, proxy emulation, or fabricated observations.
    Each socket and shutdown have finite bounds. Bind, handler, thread, and
    cleanup failures raise HelperError; HTTP response statuses remain records.
    """
    directory = _Path(directory).resolve()
    if not directory.is_dir():
        raise HelperError(f"HTTP input directory does not exist: {directory}")
    request_timeout = _seconds(request_timeout)
    shutdown_timeout = _seconds(shutdown_timeout)
    records, logs, errors = [], [], []
    stop = _threading.Event()

    class Handler(_http_server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def setup(self):
            self.request.settimeout(request_timeout)
            super().setup()

        def log_request(self, code="-", size="-"):
            records.append({"method": self.command, "path": self.path,
                            "status": int(code), "headers": tuple(self.headers.items())})

        def log_message(self, format, *args):
            logs.append(format % args)

        def log_error(self, format, *args):
            message = format % args
            logs.append(message)
            errors.append(HelperError(f"HTTP handler error: {message}"))

    class Server(_http_server.HTTPServer):
        def handle_error(self, request, client_address):
            errors.append(_sys.exc_info()[1])

    try:
        server = Server((host, port), Handler)
    except OSError as exc:
        raise HelperError("Cannot bind real HTTP file server") from exc
    server.timeout = 0.1

    def serve():
        try:
            while not stop.is_set():
                server.handle_request()
        except BaseException as exc:
            errors.append(exc)

    thread = _threading.Thread(target=serve, name="suite-file-server", daemon=True)
    try:
        thread.start()
    except BaseException:
        server.server_close()
        raise
    try:
        address, bound_port = server.server_address[:2]
        yield HTTPService(f"http://{address}:{bound_port}", records, logs)
    finally:
        stop.set()
        thread.join(shutdown_timeout)
        server.server_close()
        if thread.is_alive():
            raise HelperTimeout("HTTP server cleanup deadline expired")
        if errors:
            raise HelperError(f"HTTP file server failed: {errors!r}") from errors[0]
