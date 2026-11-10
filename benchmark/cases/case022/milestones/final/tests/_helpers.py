# feature: F00
"""Shared invocation machinery; expected product behavior belongs in tests.

Callers import public product entries with ordinary imports and pass the callable
to observe(), or supply Python source containing ordinary imports to run_python().
No product module is imported here. Entry names, fields, cache environment
variables and failure carriers come from the public Interface Contract;
prerequisite-removal scenarios use independently installed runtime environments.
Missing contract details require a specification/environment handoff; these helpers
neither simulate unavailable capabilities nor mark an unobserved branch successful.

In-process deadlines use POSIX alarms on the main thread. Use a fresh process for
native code that may block signal delivery, threaded work, or environment isolation.
"""

import contextlib as _contextlib
import dataclasses as _dataclasses
import io as _io
import json as _json
import math as _math
import os as _os
import pathlib as _pathlib
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import threading as _threading
import time as _time
import warnings as _warnings


class HarnessError(AssertionError):
    """Represent a machinery failure, never a product result or exit status."""


class HarnessTimeout(HarnessError):
    """Represent an expired deadline; no product success or exit status is implied."""


@_dataclasses.dataclass(frozen=True)
class ProcessResult:
    """Return command, numeric exit status, text streams and elapsed seconds.

    Nonzero status is retained for the test to interpret. Launch, decoding and
    supervision failures raise instead of constructing this record.
    """

    command: tuple
    returncode: int
    stdout: str
    stderr: str
    elapsed: float


@_dataclasses.dataclass(frozen=True)
class Observation:
    """Return a call's value, exception, Python streams, warnings and elapsed time.

    error is None on success, including a successful None value. Ordinary product
    exceptions are retained in error; machinery failures and BaseException control
    signals propagate. There is no process exit status for an in-process call.
    """

    value: object
    error: object
    stdout: str
    stderr: str
    warnings: tuple
    elapsed: float


def _seconds(timeout):
    if not _math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    return timeout


def run_command(command, *, timeout, cwd=None, env=None, input_text=None):
    """Return ProcessResult for an argv sequence, without a shell.

    cwd defaults to the harness working directory; env is a complete environment
    when supplied. Input and captured streams use strict UTF-8. Nonzero exits are
    returned unchanged. Launch/read errors raise HarnessError with their cause;
    timeout raises HarnessTimeout after killing this invocation's process group.
    """
    _seconds(timeout)
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be an argv sequence")
    command = tuple(_os.fspath(part) for part in command)
    if not command:
        raise ValueError("command must not be empty")
    started = _time.monotonic()
    try:
        process = _subprocess.Popen(
            command, cwd=cwd, env=env, stdin=_subprocess.PIPE,
            stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
            text=True, encoding="utf-8", errors="strict", start_new_session=True,
        )
    except OSError as exc:
        raise HarnessError("Unable to launch command") from exc
    try:
        stdout, stderr = process.communicate(input_text, timeout=timeout)
    except BaseException as exc:
        try:
            _os.killpg(process.pid, _signal.SIGKILL)
        except ProcessLookupError:
            pass  # The owned group already exited; there is nothing left to kill.
        try:
            process.wait(timeout=5)
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        if isinstance(exc, _subprocess.TimeoutExpired):
            raise HarnessTimeout("Command exceeded its deadline") from exc
        if isinstance(exc, (OSError, UnicodeError)):
            raise HarnessError("Unable to read command output") from exc
        raise
    return ProcessResult(command, process.returncode, stdout, stderr,
                         _time.monotonic() - started)


def run_python(source, *, timeout, args=(), python=None, cwd=None, env=None,
               input_text=None):
    """Run caller-supplied source in a fresh interpreter; return ProcessResult.

    Product imports must be explicit public imports in source. The interpreter
    defaults to the current one. Exit/error semantics match run_command; neither
    installation nor import-path modification is performed.
    """
    executable = _sys.executable if python is None else python
    return run_command((executable, "-c", source, *args), timeout=timeout,
                       cwd=cwd, env=env, input_text=input_text)


def run_pytest(args, *, timeout, python=None, cwd=None, env=None):
    """Invoke the project's Python pytest entry and return ProcessResult.

    Pass test paths and options explicitly. All pytest exit codes are retained;
    machinery failures raise as in run_command. No tests or flags are injected.
    """
    executable = _sys.executable if python is None else python
    return run_command((executable, "-m", "pytest", *args), timeout=timeout,
                       cwd=cwd, env=env)


@_contextlib.contextmanager
def isolated_environment(*, base, overrides=None, remove=(), cache_variables=(),
                         parent=None):
    """Yield (temporary Path, environment dict) without changing this process.

    base is explicit: pass os.environ to inherit or {} for an empty environment.
    Each caller-named cache variable receives a separate empty directory. Other
    values are preserved except explicit removals/overrides. Directory creation
    and cleanup errors propagate; no exit status or capability verdict is made.
    """
    environment = dict(base)
    for name in remove:
        environment.pop(name, None)
    if overrides is not None:
        environment.update(overrides)
    with _tempfile.TemporaryDirectory(dir=parent, prefix="suite-") as directory:
        root = _pathlib.Path(directory)
        for index, name in enumerate(cache_variables):
            cache = root / str(index)
            cache.mkdir()
            environment[name] = str(cache)
        yield root, environment


@_contextlib.contextmanager
def deadline(timeout):
    """Yield None within a POSIX main-thread time limit; expiry raises.

    Raises HarnessError if an existing alarm would be displaced or this thread
    cannot use alarms. Restores the previous signal handler on exit. No product
    exception is suppressed and no exit status is produced. Not nestable.
    """
    _seconds(timeout)
    if _threading.current_thread() is not _threading.main_thread():
        raise HarnessError("Use a supervised process outside the main thread")
    if _signal.getitimer(_signal.ITIMER_REAL) != (0.0, 0.0):
        raise HarnessError("An existing real-time alarm is active")
    previous = _signal.getsignal(_signal.SIGALRM)

    def expired(signum, frame):
        raise HarnessTimeout("In-process operation exceeded its deadline")

    _signal.signal(_signal.SIGALRM, expired)
    try:
        _signal.setitimer(_signal.ITIMER_REAL, timeout)
        yield
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, previous)


def observe(operation, *, timeout, consume=None):
    """Return Observation for a zero-argument public call and optional consumer.

    consume(value) executes within the same deadline and exception scope, allowing
    lazy failures to be observed. Its return value becomes the observed value.
    Ordinary call/consumer exceptions are recorded, not classified as expected.
    Consumers must only drive the product; parsing and assertions belong outside
    this scope so helper failures cannot masquerade as product failures. Python
    streams and warnings are captured; native streams require run_command.
    """
    stdout, stderr = _io.StringIO(), _io.StringIO()
    value, error = None, None
    started = _time.monotonic()
    with deadline(timeout), _contextlib.redirect_stdout(stdout), \
            _contextlib.redirect_stderr(stderr), _warnings.catch_warnings(record=True) as records:
        _warnings.simplefilter("always")
        try:
            value = operation()
            if consume is not None:
                value = consume(value)
        except HarnessError:
            raise
        except Exception as exc:
            value, error = None, exc
    return Observation(value, error, stdout.getvalue(), stderr.getvalue(),
                       tuple(records), _time.monotonic() - started)


def consume_prefix(iterable, *, limit):
    """Return at most limit items, without probing beyond the requested prefix.

    Works equally for public rows, columns or batches; values are unchanged.
    Exhaustion ends the prefix, other errors propagate. This does not claim full
    consumption. Use inside observe or deadline to bound a blocking next call;
    use run_python for code that cannot be interrupted by Python signals.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit must be a nonnegative integer")
    result = []
    iterator = iter(iterable)
    for _ in range(limit):
        try:
            item = next(iterator)
        except StopIteration:
            break
        result.append(item)
    return result


def read_fields(value, names, *, access):
    """Return a dict of explicitly named public fields without normalization.

    access must be 'mapping' (also for split names) or 'attribute' (for public
    metadata/result objects). Missing fields and read errors raise HarnessError
    with the original cause, never a missing-value sentinel. No exit status is
    involved. Read potentially lazy fields within an explicit deadline.
    """
    if access not in ("mapping", "attribute"):
        raise ValueError("access must be 'mapping' or 'attribute'")
    try:
        return {name: value[name] if access == "mapping" else getattr(value, name)
                for name in names}
    except Exception as exc:
        raise HarnessError("Unable to read the requested public fields") from exc


def read_json(path):
    """Return parsed JSON from the explicitly selected UTF-8 file.

    File, decoding and JSON errors propagate; missing output never becomes None
    or an empty result. There is no process exit status and no schema assertion.
    """
    with open(path, encoding="utf-8") as stream:
        return _json.load(stream)


def parse_json(text):
    """Return parsed JSON from an explicitly selected complete text channel.

    Invalid JSON raises the parser's error. No log searching, field guessing,
    exit-status interpretation or behavior validation is performed.
    """
    return _json.loads(text)
