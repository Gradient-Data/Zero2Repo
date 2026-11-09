# feature: F00
"""Shared Python-library driving machinery; no feature expectations live here.

Product calls use callables supplied by tests. Only process-wide isolation uses
Velnora's package-root API. There is no subprocess exit status for Python calls:
normal returns and explicitly allowed exceptions are represented by CallResult;
all other exceptions propagate. Calls and consumers run in the main thread of
this Linux pytest environment, with a finite wall-clock deadline.
"""

import contextlib as _contextlib
import dataclasses as _dataclasses
import io as _io
import json as _json
import math as _math
import os as _os
from pathlib import Path as _Path
import random as _random
import signal as _signal
import sys as _sys
import tempfile as _tempfile
import threading as _threading
import warnings as _warnings

import numpy as _numpy
import pytest as _pytest
import torch as _torch
import velnora as _velnora

__all__ = [
    "CallResult", "environment_info", "isolated_state", "invoke",
    "consume_iterable", "temporary_environment", "temporary_directory",
    "read_json", "save_and_load",
]


class _DrivingFailure(AssertionError):
    pass


@_dataclasses.dataclass(frozen=True)
class CallResult:
    """Return record with stdout, stderr, WarningMessages and original exception.

    ``exception`` is None on success; otherwise it is an explicitly allowed
    exception, including its traceback. ``value`` returns the actual Python
    result on success and re-raises that exception on failure. There is no exit
    code. Unknown exceptions and helper failures never produce this record.
    """

    _value: object
    stdout: str
    stderr: str
    warnings: tuple
    exception: object = None

    @property
    def value(self):
        """Return the actual result, or re-raise the recorded original exception.

        Python calls have no exit status. A successful None return is preserved.
        """
        if self.exception is not None:
            raise self.exception.with_traceback(self.exception.__traceback__)
        return self._value


def environment_info():
    """Return loaded pytest, NumPy, Torch and product modules by package name.

    Imports are plain imports at module load; missing dependencies raise their
    original import errors. No versions, devices or product behavior are judged,
    and no process exit status is involved.
    """
    return {"pytest": _pytest, "numpy": _numpy, "torch": _torch, "velnora": _velnora}


@_contextlib.contextmanager
def _deadline(seconds):
    if not _math.isfinite(seconds) or seconds <= 0:
        raise ValueError("timeout must be finite and positive")
    if _threading.current_thread() is not _threading.main_thread():
        raise RuntimeError("Bounded library calls require the main thread")
    if _signal.getitimer(_signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError("A real-time alarm is already active; deadlines cannot nest")
    previous = _signal.getsignal(_signal.SIGALRM)

    def expired(signum, frame):
        raise _DrivingFailure("Python invocation exceeded its wall-clock deadline")

    _signal.signal(_signal.SIGALRM, expired)
    try:
        _signal.setitimer(_signal.ITIMER_REAL, seconds)
        yield
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, previous)


def invoke(entry, *args, kwargs=None, consume=None, allowed_exceptions=(),
           timeout=60.0, stdin=None):
    """Return CallResult from a caller-supplied public callable and its consumer.

    ``kwargs`` goes only to the callable. Optional ``consume(result)`` runs in
    the same warning/output/deadline scope; its return becomes the result.
    Use it for lazy results or explicit public-field reading. Without a consumer
    the actual object is returned untouched, including tensors and mappings.
    ``stdin`` optionally supplies text via Python's stdin; stdout/stderr capture
    covers Python streams, not native file-descriptor writes.

    Only classes in ``allowed_exceptions`` are recorded, without text matching.
    Unknown errors propagate unchanged; deadline failures always raise an
    AssertionError. Warnings are recorded as original WarningMessage objects;
    callers decide which categories are permitted. Python has no exit status.
    This process-global capture is for serial main-thread pytest execution.
    """
    if not isinstance(allowed_exceptions, tuple) or any(
        not isinstance(cls, type) or not issubclass(cls, Exception)
        for cls in allowed_exceptions
    ):
        raise TypeError("allowed_exceptions must be a tuple of Exception classes")
    output, errors = _io.StringIO(), _io.StringIO()
    result, caught = None, None
    with _deadline(timeout), _contextlib.ExitStack() as stack:
        stack.enter_context(_contextlib.redirect_stdout(output))
        stack.enter_context(_contextlib.redirect_stderr(errors))
        recorded = stack.enter_context(_warnings.catch_warnings(record=True))
        _warnings.simplefilter("always")
        if stdin is not None:
            previous_stdin = _sys.stdin
            stack.callback(setattr, _sys, "stdin", previous_stdin)
            _sys.stdin = stack.enter_context(_io.StringIO(stdin))
        try:
            result = entry(*args, **({} if kwargs is None else kwargs))
            if consume is not None:
                result = consume(result)
        except _DrivingFailure:
            raise
        except allowed_exceptions as exc:
            caught = exc
    return CallResult(result, output.getvalue(), errors.getvalue(),
                      tuple(recorded), caught)


def consume_iterable(iterable, *, max_items):
    """Return all items as a list, requiring exhaustion within max_items items.

    Pass this as an invoke consumer (usually via a lambda) so each next call is
    also under its wall-clock deadline. One extra next detects overflow, which
    raises AssertionError rather than returning a truncated success. Iterator
    exceptions propagate unchanged; this has no process exit status.
    """
    if not isinstance(max_items, int) or isinstance(max_items, bool) or max_items < 0:
        raise ValueError("max_items must be a nonnegative integer")
    if _signal.getitimer(_signal.ITIMER_REAL)[0] <= 0:
        raise RuntimeError("consume_iterable must run inside invoke's deadline")
    iterator = iter(iterable)
    result = []
    for index in range(max_items + 1):
        try:
            item = next(iterator)
        except StopIteration:
            return result
        if index == max_items:
            raise _DrivingFailure("Iterable exceeded the declared item budget")
        result.append(item)


@_contextlib.contextmanager
def isolated_state(*, seed=None, validation=True, dtype=None, device=None):
    """Yield a fresh public parameter scope and restore surrounding global state.

    Saves Python, NumPy, Torch CPU and already-initialized CUDA RNG states;
    seed is optional and uses the package-root seeding API. Validation, default
    dtype and default device are scoped. Optional dtype/device are passed to
    Torch without guessing environment defaults. Each arm should enter this
    context separately; no trained state is shared. Errors propagate, including
    restoration errors; there is no exit status. CUDA must be initialized before
    entry if its RNG is to be used and restored in this context.
    """
    python_rng = _random.getstate()
    numpy_rng = _numpy.random.get_state()
    cpu_rng = _torch.get_rng_state()
    cuda_rng = _torch.cuda.get_rng_state_all() if _torch.cuda.is_initialized() else None
    old_dtype = _torch.get_default_dtype()
    old_device = _torch.get_default_device()
    with _contextlib.ExitStack() as stack:
        stack.callback(_random.setstate, python_rng)
        stack.callback(_numpy.random.set_state, numpy_rng)
        stack.callback(_torch.set_rng_state, cpu_rng)
        if cuda_rng is not None:
            stack.callback(_torch.cuda.set_rng_state_all, cuda_rng)
        stack.callback(_torch.set_default_dtype, old_dtype)
        stack.callback(_torch.set_default_device, old_device)
        scope = stack.enter_context(_velnora.get_param_store().scope())
        stack.enter_context(_velnora.validation_enabled(validation))
        if dtype is not None:
            _torch.set_default_dtype(dtype)
        if device is not None:
            _torch.set_default_device(device)
        if seed is not None:
            _velnora.set_rng_seed(seed)
        yield scope


@_contextlib.contextmanager
def temporary_environment(changes):
    """Yield None with specified environment keys changed, then restore them.

    String values set keys; None removes keys temporarily. Unmentioned keys are
    untouched. Setup, body and cleanup errors propagate; no exit status exists.
    This is process-global and intended for serial execution.
    """
    previous = {key: _os.environ.get(key) for key in changes}
    try:
        for key, value in changes.items():
            if value is None:
                _os.environ.pop(key, None)
            else:
                _os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                _os.environ.pop(key, None)
            else:
                _os.environ[key] = value


@_contextlib.contextmanager
def temporary_directory(*, parent=None):
    """Yield a Path to a unique directory, removing it on exit.

    Creation and cleanup errors propagate rather than signaling success. No
    product file layout or process exit status is assumed.
    """
    with _tempfile.TemporaryDirectory(dir=parent) as directory:
        yield _Path(directory)


def read_json(path):
    """Return the JSON value parsed from the explicitly supplied UTF-8 file.

    File, decoding and JSON parser errors propagate unchanged. No fields are
    guessed and no process exit status is involved.
    """
    with _Path(path).open(encoding="utf-8") as stream:
        return _json.load(stream)


def save_and_load(save, load, *, suffix="", timeout=60.0, consume=None):
    """Return (save_result, load_result) using public path-taking callables.

    Each callable receives the same temporary Path, with its own finite timeout
    and CallResult capture. The optional consumer runs on the loaded result
    before cleanup. Exceptions propagate; neither phase allows exceptions or
    checks product behavior. Tests must exercise the restored object themselves
    (or via consume); file existence/bytes are not treated as evidence. The path
    is removed before return. Neither Python call has a process exit status.
    """
    if "/" in suffix or "\\" in suffix:
        raise ValueError("suffix must not contain path separators")
    with temporary_directory() as directory:
        path = directory / ("artifact" + suffix)
        saved = invoke(save, path, timeout=timeout)
        loaded = invoke(load, path, timeout=timeout, consume=consume)
        return saved, loaded
