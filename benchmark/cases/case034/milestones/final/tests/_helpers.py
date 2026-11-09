# feature: F00
"""Shared machinery, with no product expectations or inferred result schemas.

Callers use ordinary public imports and pass entry points and field names here.
Product options, including explicit squeeze options, are passed unchanged.
In-process capture and process-global isolation require serial use.
"""

import contextlib as _contextlib
import copy as _copy
import dataclasses as _dataclasses
import io as _io
import math as _math
import os as _os
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import threading as _threading
import warnings as _warnings


@_dataclasses.dataclass(frozen=True)
class CallResult:
    """Return value, raw warning records, streams, and expected exception.

    returned distinguishes a normal None return from an exception. exception
    retains its original traceback and is None on return. No process exit status
    is invented. Unexpected exceptions and machinery failures raise instead.
    """

    returned: bool
    value: object
    warnings: tuple
    stdout: str
    stderr: str
    exception: object


class _DeadlineExpired(BaseException):
    pass


@_contextlib.contextmanager
def _deadline(seconds):
    if not _math.isfinite(seconds) or seconds <= 0:
        raise ValueError("timeout must be finite and positive")
    if _threading.current_thread() is not _threading.main_thread():
        raise RuntimeError("in-process deadlines require the main thread")
    if _signal.getitimer(_signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError("an existing timer prevents deadline isolation")
    previous = _signal.getsignal(_signal.SIGALRM)

    def expire(signum, frame):
        raise _DeadlineExpired()

    _signal.signal(_signal.SIGALRM, expire)
    try:
        _signal.setitimer(_signal.ITIMER_REAL, seconds)
        try:
            yield
        except _DeadlineExpired as error:
            raise AssertionError("public call exceeded its deadline") from error
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, previous)


def invoke(entry_point, args=(), kwargs=None, *, expected_exceptions=(),
           timeout=None, stdin=None):
    """Return CallResult after calling the supplied public callable unchanged.

    Only explicitly listed exception classes are recorded; other errors raise.
    Warning records retain category, message, and location. Capture covers
    Python streams, not native file descriptors. Optional stdin is text.
    There is no process exit status or default per-call deadline. An explicitly
    requested POSIX main-thread deadline raises AssertionError on expiry. Native code can delay Python signal delivery: use
    run_command when an externally enforced process deadline is necessary.
    """
    if not isinstance(expected_exceptions, tuple):
        raise TypeError("expected_exceptions must be a tuple")
    for kind in expected_exceptions:
        if not isinstance(kind, type) or not issubclass(kind, Exception):
            raise TypeError("expected exceptions must be Exception subclasses")
        if kind is Exception:
            raise ValueError("name specific expected exceptions")
    stdout, stderr = _io.StringIO(), _io.StringIO()
    deadline = _contextlib.nullcontext() if timeout is None else _deadline(timeout)
    with deadline, _contextlib.ExitStack() as stack:
        stack.enter_context(_contextlib.redirect_stdout(stdout))
        stack.enter_context(_contextlib.redirect_stderr(stderr))
        if stdin is not None:
            replacement = _io.StringIO(stdin)
            stack.callback(setattr, _sys, "stdin", _sys.stdin)
            _sys.stdin = replacement
        recorded = stack.enter_context(_warnings.catch_warnings(record=True))
        _warnings.simplefilter("always")
        try:
            value = entry_point(*args, **({} if kwargs is None else kwargs))
        except expected_exceptions as error:
            return CallResult(False, None, tuple(recorded), stdout.getvalue(),
                              stderr.getvalue(), error)
        return CallResult(True, value, tuple(recorded), stdout.getvalue(),
                          stderr.getvalue(), None)


def user_warnings(result, category):
    """Return the CallResult warning records of the caller-named category.

    Subclasses of category count; records of other categories, such as
    deprecation or numerical runtime warnings, are neither counted nor judged.
    """
    if not isinstance(category, type) or not issubclass(category, Warning):
        raise TypeError("category must be a Warning subclass")
    return tuple(record for record in result.warnings
                 if issubclass(record.category, category))


def read_fields(result, *names):
    """Return a dictionary of caller-named public attributes without conversion.

    Missing fields and property errors propagate. None and failure status values
    remain unchanged; no success or exit status is inferred. This reader serves
    models, time/frequency responses, optimization results, and plot objects.
    """
    for name in names:
        if not isinstance(name, str) or name.startswith("_"):
            raise ValueError("field names must identify public attributes")
    return {name: getattr(result, name) for name in names}


@_contextlib.contextmanager
def isolated_mapping(mapping, updates=None):
    """Yield a public configuration mapping and restore deep-copied contents.

    Optional updates apply inside the context. Copy, update, body, and cleanup
    errors propagate; no exit status is produced or interpreted.
    """
    saved = _copy.deepcopy(dict(mapping))
    try:
        if updates is not None:
            mapping.update(updates)
        yield mapping
    finally:
        mapping.clear()
        mapping.update(saved)


@_contextlib.contextmanager
def isolated_environment(updates):
    """Yield None with environment updates, then restore the saved environment.

    None removes a variable during the context. All errors propagate; there is
    no process exit-status conversion. This context changes process-global state.
    """
    saved = dict(_os.environ)
    try:
        for name, value in updates.items():
            if value is None:
                _os.environ.pop(name, None)
            else:
                _os.environ[name] = value
        yield
    finally:
        _os.environ.clear()
        _os.environ.update(saved)


@_contextlib.contextmanager
def temporary_directory(*, parent=None):
    """Yield a temporary directory path string and remove only that directory.

    Creation, body, and cleanup errors propagate; no exit status is produced.
    """
    with _tempfile.TemporaryDirectory(dir=parent) as directory:
        yield directory


def run_command(command, *, stdin=None, cwd=None, env=None, timeout=30.0):
    """Return CompletedProcess with text streams and the actual returncode.

    command is an argument sequence, never shell code. env is a complete child
    environment or None to inherit. stdin is text or None for immediate EOF.
    Nonzero exits are observations. Launch and decoding errors propagate.
    Expiry kills and reaps the direct child, then raises AssertionError chained
    from TimeoutExpired. Commands must not launch persistent descendants.
    """
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be an argument sequence")
    if not _math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    try:
        return _subprocess.run(command, input="" if stdin is None else stdin,
                               cwd=cwd, env=env, timeout=timeout,
                               capture_output=True, text=True, check=False)
    except _subprocess.TimeoutExpired as error:
        raise AssertionError("public command exceeded its deadline") from error


@_contextlib.contextmanager
def headless_figures():
    """Yield Agg pyplot and close only figures created during this context.

    Restore backend and interactive mode. A backend switch with existing figures
    raises instead of destroying them. Import, plotting, body, and cleanup errors
    propagate. Figure creation implies neither product success nor exit status.
    """
    import matplotlib as _matplotlib
    import matplotlib.pyplot as _plt

    backend = _matplotlib.get_backend()
    existing = set(_plt.get_fignums())
    interactive = _plt.isinteractive()
    switch = backend.lower() != "agg"
    if switch and existing:
        raise RuntimeError("cannot switch backend with existing figures")
    if switch:
        _plt.switch_backend("Agg")
    try:
        _plt.ioff()
        yield _plt
    finally:
        for number in set(_plt.get_fignums()) - existing:
            _plt.close(number)
        if switch:
            _plt.switch_backend(backend)
        _plt.interactive(interactive)


def labeled_artists(axes, label):
    """Return all direct Matplotlib artists with the caller's exact label.

    Duplicates remain; an empty tuple means no match, not product success.
    Access errors propagate. Read coordinates using public artist methods or
    read_fields. No roles, ordering, coordinates, or exit status are inferred.
    """
    return tuple(artist for artist in axes.get_children()
                 if artist.get_label() == label)
