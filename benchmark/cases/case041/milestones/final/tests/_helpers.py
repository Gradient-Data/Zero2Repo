# feature: F00
"""Shared driving machinery, with no product imports or expected answers.

Feature modules use ordinary public imports and pass callables to observe.
Consumers explicitly read public fields/properties, serialize or exhaust lazy
results. The shared conftest.py adds the runtime candidate product directory to
the collecting interpreter's import path before feature imports. For global
registrations and optional integration imports, run_python provides a fresh
interpreter in that same product directory. Import failures are never hidden.
No reference-repository paths or installation are used.
"""

import base64 as _base64
import codecs as _codecs
import contextlib as _contextlib
import dataclasses as _dataclasses
import hashlib as _hashlib
import io as _io
import ipaddress as _ipaddress
import json as _json
import math as _math
import os as _os
from pathlib import Path as _Path
import signal as _signal
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import threading as _threading
import time as _time
from types import SimpleNamespace as _Namespace
from urllib import parse as _urlparse
import zlib as _zlib

__all__ = [
    'HelperError', 'HelperTimeout', 'CallObservation', 'RunRecord', 'observe',
    'exhaust', 'run_process', 'run_python', 'read_public', 'read_json',
    'support_path', 'temporary_directory', 'temporary_environment',
    'standard_tools',
]

_PRODUCT_DIRECTORY = _Path.cwd().resolve()
_SUPPORT_DIRECTORY = _Path(__file__).resolve().parent


class HelperError(AssertionError):
    """Driving failure; always raised, never a product result or exit status."""


class HelperTimeout(HelperError):
    """Deadline failure; raised without fabricating an exit status.

    Child-process timeouts retain TimeoutExpired and partial output as cause.
    """


@_dataclasses.dataclass(frozen=True)
class CallObservation:
    """Raw call evidence without a numeric process exit status.

    value is the original return; consumed holds completed consumer results.
    stdout/stderr are text. error is an explicitly requested product exception
    or None. stage is 'call', 'consumer:N' (zero based), or 'complete'. On call
    failure value is None: inspect error to distinguish a returned None.
    Unexpected errors and helper failures raise instead of returning a record.
    """

    value: object
    consumed: tuple
    stdout: str
    stderr: str
    error: object
    stage: str


@_dataclasses.dataclass(frozen=True)
class RunRecord:
    """Caller-labelled raw evidence, with no inferred success or defect count.

    result retains a CallObservation, CompletedProcess or original exception;
    its exit status/errors are unchanged. purpose identifies maintenance versus
    contestant assessment as supplied by the caller. unobserved names downstream
    operations the caller did not reach; it neither skips tests nor invents
    their results. Construction does not evaluate the product.
    """

    label: str
    purpose: str
    result: object
    unobserved: tuple = ()


def _seconds(timeout):
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not _math.isfinite(timeout) or timeout <= 0):
        raise HelperError('timeout must be a finite positive number of seconds')
    return timeout


@_contextlib.contextmanager
def _deadline(timeout):
    timeout = _seconds(timeout)
    if _threading.current_thread() is not _threading.main_thread():
        raise HelperError('In-process deadlines require the main thread; use run_python')
    handler = _signal.getsignal(_signal.SIGALRM)
    delay, interval = _signal.getitimer(_signal.ITIMER_REAL)
    if interval:
        raise HelperError('In-process deadlines cannot replace a periodic alarm')
    started = _time.monotonic()

    def expired(signum, frame):
        raise HelperTimeout('In-process observation exceeded its deadline')

    _signal.signal(_signal.SIGALRM, expired)
    _signal.setitimer(_signal.ITIMER_REAL, min(timeout, delay) if delay else timeout)
    try:
        yield
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, handler)
        if delay:
            remaining = delay - (_time.monotonic() - started)
            _signal.setitimer(_signal.ITIMER_REAL, max(remaining, 0.000001))


def observe(entry_point, *, args=(), kwargs=None, consumers=(),
            expected_exceptions=(), timeout=10.0):
    """Return CallObservation for a call and explicit consumers under one deadline.

    Each consumer receives the original returned value. Callers explicitly read
    native/parsed fields, serialize and exhaust generators in these callbacks.
    Only exceptions in expected_exceptions are recorded; unexpected exceptions
    propagate with their traceback. HelperError always raises. Capture restores
    Python stdout/stderr on every exit; file-descriptor output requires a child.
    No process exit status exists. Requires a POSIX main thread; use run_python
    for global-state isolation. Consumers must be a finite sequence of callables.
    """
    if not isinstance(expected_exceptions, tuple) or any(
        not isinstance(kind, type) or not issubclass(kind, Exception)
        for kind in expected_exceptions
    ):
        raise HelperError('expected_exceptions must be a tuple of Exception classes')
    if not isinstance(consumers, (tuple, list)):
        raise HelperError('consumers must be a finite tuple or list')
    output, errors = _io.StringIO(), _io.StringIO()
    value, consumed, error, stage = None, [], None, 'call'
    with _contextlib.redirect_stdout(output), _contextlib.redirect_stderr(errors):
        with _deadline(timeout):
            try:
                value = entry_point(*args, **({} if kwargs is None else kwargs))
                for index, consumer in enumerate(consumers):
                    stage = 'consumer:%d' % index
                    consumed.append(consumer(value))
                stage = 'complete'
            except HelperError:
                raise
            except expected_exceptions as caught:
                error = caught
    return CallObservation(value, tuple(consumed), output.getvalue(),
                           errors.getvalue(), error, stage)


def exhaust(iterable, *, max_items, timeout=10.0):
    """Return iterator items as a tuple within explicit count/time bounds.

    Reads at most max_items + 1 items to detect overflow, which raises
    HelperError. Expiry raises HelperTimeout; iteration errors propagate
    unchanged. No truncation or exit status is supplied. Can be an observe
    consumer; nested deadlines retain the earlier outer deadline.
    """
    if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 0:
        raise HelperError('max_items must be a nonnegative integer')
    items = []
    with _deadline(timeout):
        iterator = iter(iterable)
        for index in range(max_items + 1):
            try:
                item = next(iterator)
            except StopIteration:
                return tuple(items)
            if index == max_items:
                raise HelperError('Iterator exceeded the explicit item bound')
            items.append(item)


def run_process(command, *, input_bytes=None, environment=None, timeout=10.0):
    """Return CompletedProcess with byte stdout/stderr and actual returncode.

    command is a finite argument sequence with an absolute executable path;
    no shell or PATH-based package-manager lookup is used. The child always
    runs in the product directory captured at module import. environment
    overlays inherited variables; None unsets a variable. stdin is input_bytes
    or immediate EOF. Nonzero status is returned for the caller to assess.
    Launch errors propagate; expiry kills/reaps the direct child and raises
    HelperTimeout from TimeoutExpired, preserving its captured partial output.
    """
    timeout = _seconds(timeout)
    if not isinstance(command, (tuple, list)):
        raise HelperError('command must be a finite tuple or list of arguments')
    if not command or not _Path(command[0]).is_absolute():
        raise HelperError('command executable must be an absolute path')
    if input_bytes is not None and not isinstance(input_bytes, bytes):
        raise HelperError('input_bytes must be bytes or None')
    child_environment = _os.environ.copy()
    if environment is not None:
        for name, value in environment.items():
            if value is None:
                child_environment.pop(name, None)
            else:
                child_environment[name] = value
    try:
        return _subprocess.run(
            command, input=b'' if input_bytes is None else input_bytes,
            stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
            cwd=str(_PRODUCT_DIRECTORY), env=child_environment,
            timeout=timeout, check=False,
        )
    except _subprocess.TimeoutExpired as error:
        raise HelperTimeout('Child process exceeded its deadline') from error


def run_python(source, *, arguments=(), input_bytes=None, environment=None,
               timeout=10.0):
    """Run supplied source in a fresh interpreter in the product directory.

    Return run_process's byte-output CompletedProcess, including nonzero status
    and original stderr for import/product errors. Launch errors raise; timeout
    raises HelperTimeout. Source uses ordinary public imports; arguments appear
    after '-c' in sys.argv. No sys.path edits, installation or registry access.
    """
    if not isinstance(arguments, (tuple, list)):
        raise HelperError('arguments must be a finite tuple or list')
    return run_process(
        (_sys.executable, '-c', source, *arguments), input_bytes=input_bytes,
        environment=environment, timeout=timeout,
    )


def read_public(value, *steps):
    """Return an explicitly selected public value; product read errors propagate.

    Each step is ('item', key) for a documented field/tuple position or
    ('attr', name) for a documented property. Private attributes and unknown
    modes raise HelperError. No guessing, normalization, implicit recursive
    consumption, exception classification or exit status is involved.
    """
    for mode, key in steps:
        if mode == 'item':
            value = value[key]
        elif mode == 'attr':
            if not isinstance(key, str) or key.startswith('_'):
                raise HelperError('Only public attribute names may be read')
            value = getattr(value, key)
        else:
            raise HelperError('Selection mode must be item or attr')
    return value


def read_json(data):
    """Return parsed JSON from supplied text/bytes; decoding errors propagate.

    No channel, field, success condition or exit status is inferred. The caller
    selects the documented channel explicitly before calling.
    """
    return _json.loads(data)


def support_path(relative_path):
    """Return an existing Path explicitly anchored beside this helper module.

    Absolute paths and escapes from the tests directory raise HelperError;
    missing paths raise FileNotFoundError. Filesystem errors propagate. No exit
    status is involved, and no reference-repository files are copied.
    """
    relative_path = _Path(relative_path)
    if relative_path.is_absolute():
        raise HelperError('Support paths must be relative to the tests directory')
    path = (_SUPPORT_DIRECTORY / relative_path).resolve(strict=True)
    if _SUPPORT_DIRECTORY not in path.parents and path != _SUPPORT_DIRECTORY:
        raise HelperError('Support path escapes the tests directory')
    return path


@_contextlib.contextmanager
def temporary_directory():
    """Yield a temporary Path and remove it on exit without changing cwd.

    Creation/cleanup and body errors propagate; no exit status or product result
    is supplied. Pass absolute filenames to the product.
    """
    with _tempfile.TemporaryDirectory() as directory:
        yield _Path(directory)


@_contextlib.contextmanager
def temporary_environment(changes):
    """Yield None with environment changes applied, then restore original values.

    None unsets a variable. Errors propagate; no exit status is supplied. This
    affects process-wide state and is not thread-safe; prefer run_python's
    environment argument for modules that cache settings.
    """
    original = {name: _os.environ.get(name) for name in changes}
    try:
        for name, value in changes.items():
            if value is None:
                _os.environ.pop(name, None)
            else:
                _os.environ[name] = value
        yield
    finally:
        for name, value in original.items():
            if value is None:
                _os.environ.pop(name, None)
            else:
                _os.environ[name] = value


def standard_tools():
    """Return standard modules for independent caller-defined readings.

    Fields are hashlib, base64, zlib, codecs, ipaddress and urlparse. Native
    results/errors are unchanged. No expected behavior or exit status is
    computed; schemas, inputs and comparisons belong to callers.
    """
    return _Namespace(hashlib=_hashlib, base64=_base64, zlib=_zlib,
                      codecs=_codecs, ipaddress=_ipaddress, urlparse=_urlparse)
