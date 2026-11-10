# feature: F00
"""Shared execution and transport machinery, without product expectations.

Callers supply public commands or callables and all contract paths and parsers.
Use ordinary public imports in Python drivers or before passing a callable.
No product modules are imported here. Process results retain nonzero statuses;
launch, transport, parsing and deadline failures raise instead of becoming data.
"""

from __future__ import annotations

import contextlib as _contextlib
import ctypes as _ctypes
import dataclasses as _dataclasses
import math as _math
import multiprocessing as _multiprocessing
import os as _os
from pathlib import Path as _Path
import pickle as _pickle
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import threading as _threading
import time as _time
import traceback as _traceback
import json as _json

__all__ = [
    "ExecutionTimeout", "ProcessResult", "CallResult", "run_command",
    "run_python", "observe_call", "temporary_workspace", "make_environment",
    "write_text", "write_json", "read_json", "read_output", "read_artifacts",
]


class ExecutionTimeout(AssertionError):
    """Raised when an execution exceeds its finite deadline; never a result.

    The message preserves captured stdout/stderr. There is no success status.
    """


@_dataclasses.dataclass(frozen=True)
class ProcessResult:
    """Raw process observation: argv, returncode, stdout, stderr, elapsed seconds.

    A zero returncode means process success, a positive value is its exit code,
    and a negative value denotes a POSIX signal. No status is asserted here.
    Launch, decoding and timeout failures raise and do not produce this object.
    """

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    elapsed: float


@_dataclasses.dataclass(frozen=True)
class CallResult:
    """Isolated call observation, including consumption and captured channels.

    On completion, value holds the consumed result and exception is None. For
    an explicitly requested exception type, value is None and exception holds
    the original exception, with remote_traceback preserving its traceback.
    There is no product exit code: worker crashes and all unrequested exceptions
    raise. Returned values and explicitly requested exceptions must be
    pickleable for transport. Unexpected exceptions cross as text records,
    retaining their qualified type, message, and original worker traceback.
    Child mutations are observed only through the caller's consumer result.
    """

    value: object
    exception: BaseException | None
    remote_traceback: str
    stdout: str
    stderr: str
    elapsed: float


def _deadline(timeout):
    if isinstance(timeout, bool) or not _math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    return float(timeout)


def make_environment(overrides=None, *, base=None):
    """Return a copied environment, applying text values and None deletions.

    Omitted base copies the current environment; base={} creates an empty one.
    No parent environment is changed. Invalid values raise; no exit status is
    involved and no product-specific environment settings are supplied.
    """
    result = dict(_os.environ if base is None else base)
    for name, value in ({} if overrides is None else overrides).items():
        if value is None:
            result.pop(name, None)
        else:
            result[name] = value
    if any(not isinstance(k, str) or not isinstance(v, str)
           for k, v in result.items()):
        raise TypeError("environment names and values must be strings")
    return result


def _kill_owned_process(process):
    # Every runner starts its own session. Never signal an inherited group.
    try:
        if _os.getpgid(process.pid) == process.pid:
            _os.killpg(process.pid, _signal.SIGKILL)
        elif hasattr(process, "kill"):
            process.kill()
    except ProcessLookupError:
        pass  # The owned process exited between the status check and signal.


def run_command(command, *, cwd, env=None, input_text=None, timeout=120.0,
                encoding="utf-8"):
    """Run an explicit argv without a shell and return ProcessResult.

    cwd is required. env=None inherits the environment; a mapping replaces it.
    input_text is sent to stdin, which is closed even when no input is supplied.
    stdout and stderr remain separate and unfiltered. Nonzero exits are data.
    Missing executables and decoding errors raise; deadlines raise
    ExecutionTimeout after bounded cleanup of this runner's process group.
    """
    limit = _deadline(timeout)
    if isinstance(command, (str, bytes, _os.PathLike)):
        raise TypeError("command must be an argv sequence, not shell text")
    argv = tuple(_os.fsdecode(part) for part in command)
    if not argv:
        raise ValueError("command must not be empty")
    payload = None if input_text is None else input_text.encode(encoding)
    started = _time.monotonic()
    with _tempfile.TemporaryFile() as out, _tempfile.TemporaryFile() as err:
        process = _subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=_subprocess.PIPE,
            stdout=out, stderr=err, start_new_session=True,
        )
        try:
            process.communicate(input=payload, timeout=limit)
        except BaseException as failure:
            _kill_owned_process(process)
            try:
                process.communicate(timeout=5.0)
            except _subprocess.TimeoutExpired as cleanup_failure:
                raise ExecutionTimeout("Owned process could not be reaped") from cleanup_failure
            if isinstance(failure, _subprocess.TimeoutExpired):
                out.seek(0)
                err.seek(0)
                raise ExecutionTimeout(
                    f"Command exceeded {limit}s: {argv!r}\n"
                    f"stdout: {out.read()!r}\nstderr: {err.read()!r}"
                ) from failure
            raise
        out.seek(0)
        err.seek(0)
        return ProcessResult(argv, process.returncode, out.read().decode(encoding),
                             err.read().decode(encoding), _time.monotonic() - started)


def run_python(source, *, cwd, python=None, env=None, input_text=None,
               timeout=120.0):
    """Execute a Python driver in a fresh interpreter; return ProcessResult.

    source supplies plain public imports and actual calls, including any lazy
    result consumption. python defaults to the current interpreter. Its normal
    import rules apply, with cwd as the driver directory; no import path is
    patched. Unhandled exceptions retain their stderr traceback and nonzero
    status. Infrastructure failures and deadlines raise as in run_command.
    """
    executable = _sys.executable if python is None else _os.fspath(python)
    return run_command((executable, "-c", source), cwd=cwd, env=env,
                       input_text=input_text, timeout=timeout)


def observe_call(entry_point, *args, cwd, kwargs=None, consume=None,
                 exception_types=(), env=None, timeout=120.0, encoding="utf-8"):
    """Call a supplied public callable in a bounded POSIX fork worker.

    Return CallResult after optionally applying consume(value) in that same
    worker and capture scope. A consumer can call a returned extension, exhaust
    a lazy result, or include mutated inputs in a pickleable observation.
    Only exception_types are returned as exceptions; unlisted exceptions raise
    RuntimeError with their qualified type, message, and worker traceback.
    SystemExit is returned
    only if explicitly listed. Timeouts, crashes and transport errors raise.

    This main-thread-only helper inherits initial imports and objects but
    isolates subsequent import, cwd, environment and object mutations. Use
    run_python for a completely fresh interpreter or alternate dependencies.
    No compiled callable or module can be transported unless it is pickleable;
    consume it inside the worker instead. POSIX fork is required, never emulated.
    """
    limit = _deadline(timeout)
    if _threading.current_thread() is not _threading.main_thread():
        raise RuntimeError("observe_call requires the main thread")
    if not isinstance(exception_types, tuple) or any(
        not isinstance(kind, type) or not issubclass(kind, BaseException)
        for kind in exception_types
    ):
        raise TypeError("exception_types must be a tuple of exception classes")
    started = _time.monotonic()
    _sys.stdout.flush()
    _sys.stderr.flush()
    with (_tempfile.TemporaryFile() as out,
          _tempfile.TemporaryFile() as err,
          _tempfile.TemporaryFile() as transport):
        def worker():
            _os.setsid()
            _os.dup2(out.fileno(), 1)
            _os.dup2(err.fileno(), 2)
            with (_os.fdopen(_os.dup(1), "w", encoding=encoding) as stdout,
                  _os.fdopen(_os.dup(2), "w", encoding=encoding) as stderr,
                  _contextlib.redirect_stdout(stdout),
                  _contextlib.redirect_stderr(stderr)):
                _os.chdir(cwd)
                if env is not None:
                    _os.environ.clear()
                    _os.environ.update(env)
                try:
                    value = entry_point(*args, **({} if kwargs is None else kwargs))
                    if consume is not None:
                        value = consume(value)
                except BaseException as failure:
                    # Classification is a caller decision; unknown errors stay errors.
                    if isinstance(failure, exception_types):
                        record = ("expected", failure, _traceback.format_exc())
                    else:
                        # Reconstructing a product exception in the parent
                        # imports its defining module and breaks isolation.
                        failure_type = type(failure)
                        description = (f"{failure_type.__module__}."
                                       f"{failure_type.__qualname__}: {failure}")
                        record = ("unexpected", description, _traceback.format_exc())
                else:
                    record = ("value", value, "")
                # multiprocessing exits without flushing C stdio buffers.
                flush = _ctypes.CDLL(None, use_errno=True).fflush
                flush.argtypes = [_ctypes.c_void_p]
                flush.restype = _ctypes.c_int
                if flush(None) != 0:
                    raise OSError(_ctypes.get_errno(), "Could not flush native output")
                _pickle.dump(record, transport)
                transport.flush()

        process = _multiprocessing.get_context("fork").Process(target=worker)
        process.start()
        try:
            process.join(limit)
            if process.is_alive():
                _kill_owned_process(process)
                process.join(5.0)
                out.seek(0)
                err.seek(0)
                raise ExecutionTimeout(
                    f"Call exceeded {limit}s\nstdout: {out.read()!r}\n"
                    f"stderr: {err.read()!r}"
                )
            out.seek(0)
            err.seek(0)
            stdout, stderr = out.read().decode(encoding), err.read().decode(encoding)
            if process.exitcode != 0:
                raise RuntimeError(
                    f"Call worker exited with status {process.exitcode}\n"
                    f"stdout: {stdout}\nstderr: {stderr}"
                )
            transport.seek(0)
            kind, value, remote_traceback = _pickle.load(transport)
            if kind == "unexpected":
                raise RuntimeError(
                    f"Call worker raised {value}\nstdout: {stdout}\nstderr: {stderr}"
                ) from RuntimeError(remote_traceback)
            return CallResult(value if kind == "value" else None,
                              value if kind == "expected" else None,
                              remote_traceback, stdout, stderr,
                              _time.monotonic() - started)
        finally:
            if process.is_alive():
                _kill_owned_process(process)
                process.join(5.0)
            if process.is_alive():
                raise ExecutionTimeout("Owned call worker could not be reaped")
            process.close()


@_contextlib.contextmanager
def temporary_workspace(*, parent=None):
    """Yield an exclusive Path, then remove only that temporary directory.

    No environment or import state is changed. Filesystem and cleanup errors
    propagate; this context manager has no exit-status result.
    """
    with _tempfile.TemporaryDirectory(prefix="suite-", dir=parent) as directory:
        yield _Path(directory)


def write_text(root, relative_path, text, *, encoding="utf-8"):
    """Write caller-provided text below root and return its absolute Path.

    Parent directories are created; existing files are replaced. Paths escaping
    root, including through symlinks, raise ValueError. I/O errors propagate;
    no product exit status is involved and source content is never fabricated.
    """
    root = _Path(root).resolve(strict=True)
    relative = _Path(relative_path)
    destination = (root / relative).resolve()
    if relative.is_absolute() or not destination.is_relative_to(root):
        raise ValueError("relative_path must stay within root")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding=encoding)
    return destination


def write_json(root, relative_path, value):
    """Serialize value as JSON below root and return the written Path.

    Serialization and filesystem errors propagate; no status is interpreted.
    Paths and replacement semantics are those of write_text.
    """
    return write_text(root, relative_path, _json.dumps(value, allow_nan=False))


def read_json(path):
    """Return the JSON document at the exact path using the standard parser.

    Missing files, invalid encoding and malformed JSON raise their original
    exceptions. No schema, product behavior or process status is assumed.
    """
    with _Path(path).open(encoding="utf-8") as stream:
        return _json.load(stream)


def read_output(result, *, channel, parser):
    """Return parser(full channel text), without filtering or guessing fields.

    channel must be stdout or stderr. The caller supplies the published format's
    parser, which must reject invalid input. Parser errors propagate, and this
    helper never interprets or changes the process returncode.
    """
    if channel not in ("stdout", "stderr"):
        raise ValueError("channel must be stdout or stderr")
    return parser(getattr(result, channel))


def read_artifacts(paths):
    """Return label-to-bytes records from an explicit label-to-path mapping.

    Callers provide the contract's paths and category labels. No paths or
    categories are inferred from logs, suffixes or directory ordering. Missing
    and unreadable files raise; contents alone imply no usability or exit
    status. Actual execution can be observed with run_command or run_python.
    """
    return {label: _Path(path).read_bytes() for label, path in paths.items()}
