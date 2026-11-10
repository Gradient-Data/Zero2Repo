# feature: F00
"""Product-independent process and Java-driver machinery for feature suites.

Callers supply build commands, public-API Java source files, classpaths and entry
points. No product bindings, routes, expected results or artifact paths are
embedded here. Driver sources must use ordinary imports of public symbols; this
module does not generate bindings or inspect product implementation code.

Commands are argument sequences, never shell strings. Paths are relative to the
explicit cwd. Environment arguments are complete environments, or None to inherit;
make_environment creates overrides without changing the current process.

A driver can reserve a caller-selected stdout/stderr channel for UTF-8 JSON Lines
and flush each readiness/reply record. No log lines are skipped or interpreted.
Alternatively, parse a whole captured channel or an explicitly named report file.
Application exceptions remain in driver reports/stderr, without classification.

Ordinary nonzero product exits are returned unless check=True. Build, compiler,
launch, protocol and deadline failures raise HarnessError, never substitute data.
All timeouts are finite positive seconds. This module installs no tests/fixtures
and creates no resources at import time. ManagedProcess targets the Linux harness.
"""

import contextlib as _contextlib
import dataclasses as _dataclasses
import json as _json
import math as _math
import os as _os
from pathlib import Path as _Path
import select as _select
import signal as _signal
import subprocess as _subprocess
import tempfile as _tempfile
import time as _time

__all__ = (
    "HarnessError", "CommandResult", "ManagedProcess", "make_environment",
    "temporary_directory", "parse_json", "read_json_file", "run_command",
    "build_product", "compile_java", "java_command", "start_java", "run_java",
)


class HarnessError(AssertionError):
    """Construct a machinery exception, never a product result.

    result is the available CommandResult (possibly still running), or None if
    unavailable. Original errors are chained; stdout/stderr and status are retained.
    """

    def __init__(self, message, *, result=None):
        self.result = result
        if result is not None:
            message += (
                f"\ncommand: {result.command!r}\nreturncode: {result.returncode!r}"
                f"\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}"
            )
        super().__init__(message)


@_dataclasses.dataclass(frozen=True)
class CommandResult:
    """Construct a record containing command, returncode, stdout bytes and stderr bytes.

    returncode is None while running, an integer on exit, or negative for a POSIX
    signal. Construction does not check status or interpret stderr as an error.
    """

    command: tuple
    returncode: object
    stdout: bytes
    stderr: bytes

    def check_returncode(self):
        """Return self on exit zero; otherwise raise HarnessError with this record."""
        if self.returncode != 0:
            raise HarnessError("Command did not complete successfully", result=self)
        return self

    def json(self, *, channel):
        """Return whole-document JSON from the explicit stdout/stderr channel.

        Status is not checked. Invalid channel names raise ValueError; decoding
        errors raise HarnessError with this record. No lines or fields are guessed.
        """
        _check_channel(channel)
        try:
            return parse_json(getattr(self, channel))
        except HarnessError as exc:
            raise HarnessError(f"Cannot parse {channel} as JSON", result=self) from exc


def _duration(value):
    if isinstance(value, bool) or not _math.isfinite(value) or value <= 0:
        raise ValueError("Timeout must be finite and positive")
    return float(value)


def _arguments(values):
    if isinstance(values, (str, bytes, _os.PathLike)):
        raise TypeError("Arguments must be a sequence, not a shell string")
    return tuple(_os.fspath(value) for value in values)


def _argv(command):
    args = _arguments(command)
    if not args:
        raise ValueError("Command cannot be empty")
    return args


def _check_channel(channel):
    if channel not in ("stdout", "stderr"):
        raise ValueError("Channel must be stdout or stderr")


def make_environment(overrides=None, *, base=None):
    """Return an independent environment dictionary without changing os.environ.

    base=None copies os.environ; otherwise only base is copied. Overrides replace
    strings and None removes a name. Invalid names/values raise TypeError or
    ValueError. There is no exit status or implicit Java/tool configuration.
    """
    env = dict(_os.environ if base is None else base)
    if overrides is not None:
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("Environment keys and values must be strings")
        if not key or "=" in key or "\0" in key or "\0" in value:
            raise ValueError("Invalid environment name or value")
    return env


@_contextlib.contextmanager
def temporary_directory(*, parent=None, prefix="suite-"):
    """Return a context manager yielding an isolated absolute Path, removed on exit.

    No exit status exists; allocation/cleanup errors propagate. Close processes
    before leaving the context. Observe product file cleanup before this helper
    performs its own cleanup, so the helper cannot manufacture product evidence.
    """
    with _tempfile.TemporaryDirectory(dir=parent, prefix=prefix) as directory:
        yield _Path(directory).resolve()


def _invalid_constant(value):
    raise ValueError(f"Non-JSON numeric constant: {value}")


def parse_json(data):
    """Return a parsed whole JSON value from str or UTF-8 bytes, including null.

    No exit status is inferred. Invalid encoding, syntax, trailing content or
    non-JSON numeric constants raise HarnessError with the original cause.
    Callers access their documented fields directly from the returned value.
    """
    try:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        if not isinstance(data, str):
            raise TypeError("JSON input must be str or bytes")
        return _json.loads(data, parse_constant=_invalid_constant)
    except (ValueError, TypeError) as exc:
        raise HarnessError("Cannot decode a complete JSON document") from exc


def read_json_file(path):
    """Return JSON from the exact file, without inferring any process exit status.

    Read only after completion or atomic publication. Missing/unreadable files
    and malformed JSON raise HarnessError, retaining the filesystem/parser cause.
    """
    try:
        return parse_json(_Path(path).read_bytes())
    except (OSError, HarnessError) as exc:
        raise HarnessError(f"Cannot read JSON report: {path}") from exc


class ManagedProcess:
    """Launch and own one explicit process; return a context-manageable handle.

    Launch errors raise HarnessError. Status is observed through poll/snapshot/
    wait, not interpreted as a feature outcome. stdout/stderr use temporary files
    to avoid pipe-buffer deadlocks. One controlling thread must own this handle.

    Use a with block or call close. Cleanup signals only the still-live POSIX
    process group started by this handle, with bounded terminate/kill waits.
    No process discovery, global registry, or automatic atexit action is used.
    """

    def __init__(self, command, *, cwd, env=None, cleanup_timeout=5.0):
        self.command = _argv(command)
        environment = make_environment(base=env)
        self._cleanup_timeout = _duration(cleanup_timeout)
        self._closed = False
        self._final = None
        self._close_error = None
        self._offsets = {"stdout": 0, "stderr": 0}
        self._pending = {"stdout": b"", "stderr": b""}
        self._resources = _contextlib.ExitStack()
        try:
            self._streams = {
                name: self._resources.enter_context(_tempfile.TemporaryFile())
                for name in ("stdout", "stderr")
            }
            self._process = _subprocess.Popen(
                self.command, cwd=cwd, env=environment, stdin=_subprocess.PIPE,
                stdout=self._streams["stdout"], stderr=self._streams["stderr"],
                start_new_session=True, bufsize=0,
            )
        except BaseException as exc:
            self._resources.close()
            if isinstance(exc, (OSError, ValueError)):
                raise HarnessError(f"Cannot launch command: {self.command!r}") from exc
            raise
        try:
            _os.set_blocking(self._process.stdin.fileno(), False)
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        """Return this handle; raise HarnessError if already closed, regardless of status."""
        if self._closed:
            raise HarnessError("Process handle is closed", result=self._final)
        return self

    def __exit__(self, exc_type, exc, traceback):
        """Close owned resources and return False, preserving errors from the body.

        Cleanup errors raise HarnessError with any body error retained as context.
        Nonzero process exits alone are not cleanup errors.
        """
        self.close()
        return False

    def poll(self):
        """Return None while alive, otherwise integer exit/signal status, without waiting.

        Observation errors propagate; no product behavior is asserted.
        """
        return self._process.poll()

    def snapshot(self):
        """Return CommandResult with current status and bytes captured so far.

        After successful close, return the saved result. Capture/cleanup errors
        raise HarnessError; a running snapshot may contain partial output records.
        """
        if self._closed:
            if self._close_error is not None:
                raise self._close_error
            return self._final
        try:
            captures = {}
            for name, stream in self._streams.items():
                fd = stream.fileno()
                size = _os.fstat(fd).st_size
                chunks = []
                offset = 0
                while offset < size:
                    chunk = _os.pread(fd, min(1024 * 1024, size - offset), offset)
                    if not chunk:
                        raise OSError("Capture ended before its recorded size")
                    chunks.append(chunk)
                    offset += len(chunk)
                captures[name] = b"".join(chunks)
            return CommandResult(self.command, self.poll(), **captures)
        except OSError as exc:
            raise HarnessError("Cannot read captured process output") from exc

    def _remaining(self, deadline, operation):
        remaining = deadline - _time.monotonic()
        if remaining <= 0:
            raise HarnessError(f"Timed out while {operation}", result=self.snapshot())
        return remaining

    def send(self, data, *, timeout):
        """Write all supplied bytes to stdin within timeout and return None.

        No newline is added and exit status is not interpreted. Wrong input type
        raises TypeError; closed input, I/O failures and timeout raise HarnessError
        with captured output. Partial writes are never reported as success.
        """
        deadline = _time.monotonic() + _duration(timeout)
        if not isinstance(data, bytes):
            raise TypeError("Process input must be bytes")
        if self._closed or self._process.stdin.closed:
            raise HarnessError("Process stdin is closed", result=self.snapshot())
        fd = self._process.stdin.fileno()
        pending = memoryview(data)
        try:
            while pending:
                remaining = self._remaining(deadline, "writing process input")
                _, writable, _ = _select.select([], [fd], [], remaining)
                if not writable:
                    raise HarnessError("Timed out writing input", result=self.snapshot())
                count = _os.write(fd, pending[:4096])
                if count == 0:
                    raise OSError("Process input write made no progress")
                pending = pending[count:]
        except OSError as exc:
            raise HarnessError("Cannot write process input", result=self.snapshot()) from exc

    def close_stdin(self):
        """Send EOF and return None; repeated calls are harmless and status is unchecked.

        Input-close failures raise HarnessError with captured output.
        """
        try:
            self._process.stdin.close()
        except OSError as exc:
            raise HarnessError("Cannot close process input", result=self.snapshot()) from exc

    def read_json_line(self, *, channel, timeout):
        """Return exactly the next newline-terminated JSON value on the selected channel.

        Intended for explicit driver readiness/reply protocols; fields are not
        interpreted and lines are not skipped. Invalid JSON, EOF before a complete
        record, I/O errors and deadline expiry raise HarnessError. Invalid channel
        names raise ValueError. Emitted records remain readable after process exit;
        the exit status itself is not checked. Each channel has its own cursor.
        """
        _check_channel(channel)
        deadline = _time.monotonic() + _duration(timeout)
        if self._closed:
            raise HarnessError("Process handle is closed", result=self.snapshot())
        fd = self._streams[channel].fileno()
        while True:
            self._remaining(deadline, f"reading JSON from {channel}")
            pending = self._pending[channel]
            if b"\n" in pending:
                line, self._pending[channel] = pending.split(b"\n", 1)
                try:
                    return parse_json(line)
                except HarnessError as exc:
                    raise HarnessError("Invalid JSON protocol record", result=self.snapshot()) from exc
            # Poll before reading: drain output emitted just before exit before
            # deciding that the protocol ended without a complete record.
            exited = self.poll() is not None
            try:
                chunk = _os.pread(fd, 65536, self._offsets[channel])
            except OSError as exc:
                raise HarnessError("Cannot read protocol channel", result=self.snapshot()) from exc
            if chunk:
                self._offsets[channel] += len(chunk)
                self._pending[channel] += chunk
            elif exited:
                raise HarnessError("Process exited before a complete JSON record", result=self.snapshot())
            else:
                _time.sleep(min(0.01, self._remaining(deadline, "waiting for JSON")))

    def wait(self, *, timeout, check=False):
        """Wait boundedly and return CommandResult, preserving nonzero exits by default.

        check=True raises HarnessError for nonzero exit. Timeout raises HarnessError
        with a live snapshot, without claiming shutdown. The owning context remains
        responsible for bounded cleanup after a failed wait.
        """
        try:
            self._process.wait(timeout=_duration(timeout))
        except _subprocess.TimeoutExpired as exc:
            raise HarnessError("Timed out waiting for process exit", result=self.snapshot()) from exc
        result = self.snapshot()
        return result.check_returncode() if check else result

    def _signal_group(self, signum):
        try:
            _os.killpg(self._process.pid, signum)
        except ProcessLookupError:
            # Exit between poll and signal is normal; reap only the owned PID.
            if self._process.poll() is None:
                raise

    def close(self):
        """Return final CommandResult after bounded cleanup; repeated calls reuse it.

        Close stdin, then terminate a still-live owned group, escalating to kill
        after cleanup_timeout. Each wait is bounded by cleanup_timeout. Nonzero/
        signal exits remain data; cleanup failures raise HarnessError, also on
        repeated calls. This cleanup proves no product shutdown/durability rule.
        """
        if self._closed:
            return self.snapshot()
        try:
            try:
                self.close_stdin()
            finally:
                if self.poll() is None:
                    self._signal_group(_signal.SIGTERM)
                    try:
                        self._process.wait(timeout=self._cleanup_timeout)
                    except _subprocess.TimeoutExpired:
                        self._signal_group(_signal.SIGKILL)
                        self._process.wait(timeout=self._cleanup_timeout)
            self._final = self.snapshot()
        except BaseException as exc:
            self._close_error = HarnessError(f"Cannot clean up owned command: {self.command!r}")
            raise self._close_error from exc
        finally:
            try:
                self._resources.close()
            finally:
                self._closed = True
        return self._final


def run_command(command, *, cwd, timeout, env=None, input=b"", check=False):
    """Return captured CommandResult after feeding bytes, sending EOF and waiting.

    timeout bounds input/wait with a deadline started before launch. OS process
    creation itself is synchronous; cleanup can add two five-second waits.
    Nonzero status is data unless check=True. Launch, capture, input and timeout
    failures raise HarnessError. No shell, retry or output inference is used.
    """
    deadline = _time.monotonic() + _duration(timeout)
    with ManagedProcess(command, cwd=cwd, env=env) as process:
        process.send(input, timeout=process._remaining(deadline, "starting command"))
        process.close_stdin()
        return process.wait(timeout=process._remaining(deadline, "running command"), check=check)


def build_product(command, *, cwd, timeout, env=None):
    """Run the supported build command supplied by the caller; return CommandResult.

    Nonzero build status or machinery failure raises HarnessError. No tool,
    installation, output location or test-skipping flag is selected implicitly.
    Call only in an authorized writable build directory.
    """
    return run_command(command, cwd=cwd, timeout=timeout, env=env, check=True)


def _classpath(paths):
    return _os.pathsep.join(_os.fsdecode(entry) for entry in _argv(paths))


def compile_java(sources, *, javac, classpath, output_dir, cwd, timeout,
                 options=(), env=None):
    """Compile caller-owned Java source files; return successful compiler CommandResult.

    javac is explicit; classpath is a nonempty sequence of paths. Paths are relative
    to cwd. output_dir is created as needed; language/module options are explicit.
    No product source is discovered or modified. Nonzero compilation and machinery
    failures raise HarnessError; invalid arguments and mkdir errors propagate.
    """
    source_args = _argv(sources)
    cp = _classpath(classpath)
    destination = _Path(output_dir)
    if not destination.is_absolute():
        destination = _Path(cwd) / destination
    destination.mkdir(parents=True, exist_ok=True)
    command = [_os.fspath(javac), *_arguments(options), "-classpath", cp,
               "-d", str(destination.resolve()), *source_args]
    return run_command(command, cwd=cwd, timeout=timeout, env=env, check=True)


def java_command(main_class, *, java, classpath, args=(), jvm_args=()):
    """Return a Java argv tuple for the explicit main class and classpath.

    Nothing is launched, so no exit status exists. Invalid argument/path types
    raise TypeError or ValueError. Heap limits, modules and JVM properties remain
    caller-controlled; there is no embedded product class or default classpath.
    """
    return _argv([_os.fspath(java), *_arguments(jvm_args), "-classpath",
                  _classpath(classpath), main_class, *_arguments(args)])


def start_java(main_class, *, java, classpath, cwd, args=(), jvm_args=(),
               env=None, cleanup_timeout=5.0):
    """Return a live ManagedProcess for the explicitly selected Java driver.

    Use it as a context manager or close it. Launch failures raise HarnessError;
    readiness/status are not assumed. Read readiness from the caller-designated
    JSON channel and access the driver's documented fields directly.
    """
    command = java_command(main_class, java=java, classpath=classpath,
                           args=args, jvm_args=jvm_args)
    return ManagedProcess(command, cwd=cwd, env=env, cleanup_timeout=cleanup_timeout)


def run_java(main_class, *, java, classpath, cwd, timeout, args=(), jvm_args=(),
             env=None, input=b"", check=False):
    """Return CommandResult from an explicit Java driver with bounded input/wait.

    Nonzero exits remain data unless check=True; machinery failures raise
    HarnessError. Capture, environment and cleanup follow run_command. Feature
    timings must be measured inside the ready Java driver; process wall time
    includes startup/communication and is not a query-performance measurement.
    """
    command = java_command(main_class, java=java, classpath=classpath,
                           args=args, jvm_args=jvm_args)
    return run_command(command, cwd=cwd, timeout=timeout, env=env, input=input, check=check)
