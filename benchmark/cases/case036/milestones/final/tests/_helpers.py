# feature: F00
"""Shared driving machinery; callers own product expectations and selectors.

Processes always run in the product directory captured when this module is
imported. Relative artifact paths are relative to that directory. Pass absolute
paths for inputs beside the tests or in a temporary workspace. No helper probes
entry points, selects an output format, or interprets a product exit category.
"""

from __future__ import annotations

import contextlib as _contextlib
import dataclasses as _dataclasses
import io as _io
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
import xml.etree.ElementTree as _ET


_PRODUCT_DIR = _Path.cwd().resolve()

__all__ = [
    "ProcessResult", "CallResult", "run_command", "run_module", "call_public",
    "temporary_workspace", "environment", "write_file", "read_xml", "read_json",
    "select_one", "required_field", "index_by_identity", "json_messages",
    "wait_until", "browser_page", "require_python", "keyword_calls",
]


def _seconds(value):
    value = float(value)
    if not _math.isfinite(value) or value <= 0:
        raise ValueError("A finite, positive timeout is required.")
    return value


def _env(base, overrides):
    result = dict(_os.environ if base is None else base)
    for name, value in (overrides or {}).items():
        if value is None:
            result.pop(name, None)
        else:
            result[name] = value
    return result


@_dataclasses.dataclass(frozen=True)
class ProcessResult:
    """Completed command, exact byte streams, raw returncode and clock bounds.

    Negative returncode denotes an OS signal; nonzero codes are not errors in
    this container. Launch, timeout and capture failures raise instead of
    producing a ProcessResult. started/finished are monotonic seconds.
    """

    command: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes
    started: float
    finished: float


@_dataclasses.dataclass(frozen=True)
class CallResult:
    """Public call's value, captured text streams and monotonic clock bounds.

    value is unchanged unless the caller supplied a consumer. There is no
    synthesized exit status: inspect the returned public value. Exceptions,
    including SystemExit, propagate with captured streams attached as a note.
    """

    value: object
    stdout: str
    stderr: str
    started: float
    finished: float


def run_command(command, *, input=None, env=None, env_overrides=None, timeout=120):
    """Return ProcessResult for an explicit argv, without a shell.

    input is bytes or None (closed stdin). env replaces the environment when
    supplied; overrides then set entries or remove them with None. Streams stay
    bytes, including final newlines. Nonzero exits return normally. Start/read
    errors propagate; deadline expiry raises AssertionError chained from
    TimeoutExpired, retaining partial streams. The owned process group is killed
    on timeout/interruption and reaped with a separate five-second bound.
    """
    timeout = _seconds(timeout)
    if isinstance(command, (str, bytes)):
        raise TypeError("command must be an argv sequence, not shell text.")
    argv = tuple(_os.fspath(arg) for arg in command)
    if not argv:
        raise ValueError("command cannot be empty.")
    if input is not None and not isinstance(input, bytes):
        raise TypeError("input must be bytes or None.")
    started = _time.monotonic()
    process = _subprocess.Popen(
        argv, cwd=_PRODUCT_DIR, env=_env(env, env_overrides),
        stdin=_subprocess.PIPE, stdout=_subprocess.PIPE,
        stderr=_subprocess.PIPE, start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(input=input, timeout=timeout)
    except BaseException as error:
        try:
            _os.killpg(process.pid, _signal.SIGKILL)
        except ProcessLookupError:
            pass  # The owned group already exited; communicate still reaps it.
        try:
            process.communicate(timeout=5)
        except BaseException as cleanup_error:
            error.add_note(f"Process cleanup failed: {cleanup_error!r}")
        if isinstance(error, _subprocess.TimeoutExpired):
            raise AssertionError(
                f"Command exceeded {timeout}s: {argv!r}; "
                f"stdout={error.output!r}; stderr={error.stderr!r}"
            ) from error
        raise
    return ProcessResult(argv, process.returncode, stdout, stderr,
                         started, _time.monotonic())


def run_module(module, arguments=(), **options):
    """Return ProcessResult from the current Python's explicit module entry.

    module is required (e.g. a documented CLI module). arguments are separate
    argv values; options and all error/exit semantics are those of run_command.
    No import-path changes or alternate entry-point attempts are made.
    """
    return run_command((_sys.executable, "-m", module, *arguments), **options)


@_contextlib.contextmanager
def environment(overrides=None, *, base=None):
    """Yield the installed environment mapping and restore it even on error.

    base=None copies the current environment; an explicit mapping replaces it.
    overrides set entries or remove them with None. No exit status is produced;
    exceptions propagate. This process-global context must not run concurrently.
    It does not change the product working directory.
    """
    previous = dict(_os.environ)
    selected = _env(base, overrides)
    try:
        _os.environ.clear()
        _os.environ.update(selected)
        yield _os.environ
    finally:
        _os.environ.clear()
        _os.environ.update(previous)


@_contextlib.contextmanager
def _deadline(timeout):
    timeout = _seconds(timeout)
    if _threading.current_thread() is not _threading.main_thread():
        raise RuntimeError("Bounded in-process calls require the main thread.")
    if _signal.getitimer(_signal.ITIMER_REAL) != (0.0, 0.0):
        raise RuntimeError("An existing real-time alarm prevents deadline isolation.")
    previous = _signal.getsignal(_signal.SIGALRM)

    def expired(signum, frame):
        raise AssertionError(f"Public call exceeded {timeout}s.")

    _signal.signal(_signal.SIGALRM, expired)
    _signal.setitimer(_signal.ITIMER_REAL, timeout)
    try:
        yield
    finally:
        _signal.setitimer(_signal.ITIMER_REAL, 0)
        _signal.signal(_signal.SIGALRM, previous)


def call_public(entry, *args, consume=None, env_overrides=None, timeout=120,
                **kwargs):
    """Return CallResult from a caller-supplied public callable, such as run.

    Pass a bound suite.run to drive the public suite API. consume, when supplied,
    is called on the return value inside the same capture/deadline scope (use
    list for lazy iterators). Python stdout/stderr are captured; native fd writes
    require run_command instead. Product exceptions and SystemExit propagate
    unchanged, with captured text as an exception note. Timeout raises
    AssertionError. Linux main-thread use only; environment is restored.
    """
    stdout, stderr = _io.StringIO(), _io.StringIO()
    started = _time.monotonic()
    with environment(env_overrides), _contextlib.redirect_stdout(stdout), \
            _contextlib.redirect_stderr(stderr):
        try:
            with _deadline(timeout):
                value = entry(*args, **kwargs)
                if consume is not None:
                    value = consume(value)
        except BaseException as error:
            error.add_note(f"Captured stdout:\n{stdout.getvalue()}\n"
                           f"Captured stderr:\n{stderr.getvalue()}")
            raise
    return CallResult(value, stdout.getvalue(), stderr.getvalue(),
                      started, _time.monotonic())


@_contextlib.contextmanager
def temporary_workspace(*, parent=None):
    """Yield an absolute temporary Path without changing the working directory.

    Contents survive until context exit, including failed runs, and are then
    removed. No exit status is produced; allocation/cleanup and body errors
    propagate. Pass paths from this workspace explicitly to product entries.
    """
    with _tempfile.TemporaryDirectory(prefix="suite-", dir=parent) as directory:
        yield _Path(directory).resolve()


def write_file(path, content, *, encoding="utf-8"):
    """Write caller-supplied text or bytes, creating parents; return absolute Path.

    No content is generated or interpreted. Bytes bypass encoding. Existing
    files are replaced. I/O and encoding errors propagate; no exit status exists.
    """
    path = _Path(path).absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding=encoding)
    return path


def read_xml(path):
    """Return an ElementTree parsed from the explicit file, honoring XML encoding.

    I/O and XML parser errors propagate; missing or malformed files never become
    empty trees. No product status or output-format inference is performed.
    """
    return _ET.parse(path)


def read_json(path, *, encoding="utf-8"):
    """Return the JSON value in an explicit file; decoding/I/O/parse errors raise.

    No result status is inferred and no alternate format or file is attempted.
    """
    with _Path(path).open(encoding=encoding) as stream:
        return _json.load(stream)


def select_one(root, path, *, namespaces=None):
    """Return the unique XML element at caller-supplied ElementTree path.

    Zero or multiple matches raise ValueError; invalid selectors propagate.
    This is an observation-integrity check, not a product status assertion.
    """
    matches = root.findall(path, namespaces=namespaces)
    if len(matches) != 1:
        raise ValueError(f"Expected one element at {path!r}, found {len(matches)}.")
    return matches[0]


def keyword_calls(root, name, *, owner=None, recursive=False):
    """Select ordinary keyword identities, independent of display qualification.

    Results carry a name and, when known, an owner. A displayed name may
    also contain that owner as a qualifier. Compare the operation using ordinary
    keyword matching rules, retaining the owner separately when the caller requests it. Missing
    names raise; no missing operation or provider is synthesized.
    """
    def identity(value):
        return value.casefold().replace(" ", "").replace("_", "")

    expected = identity(name)
    selected = []
    for call in root.findall(".//kw" if recursive else "kw"):
        provider = call.attrib.get("owner")
        actual = call.attrib["name"]
        if provider:
            prefix = provider + "."
            if actual[:len(prefix)].casefold() == prefix.casefold():
                actual = actual[len(prefix):]
        if identity(actual) == expected and (owner is None or provider == owner):
            selected.append(call)
    return selected


def required_field(mapping, key):
    """Return an explicitly named mapping field, preserving its value including None.

    Missing fields raise KeyError; invalid carriers raise their original error.
    No product status interpretation or replacement value is supplied.
    """
    return mapping[key]


def index_by_identity(items, identity):
    """Return items indexed by a caller-defined complete, hashable identity.

    Duplicate identities raise ValueError rather than overwrite observations;
    identity extraction errors propagate. No status or hierarchy is inferred.
    """
    result = {}
    for item in items:
        key = identity(item)
        if key in result:
            raise ValueError(f"Duplicate observation identity: {key!r}")
        result[key] = item
    return result


def json_messages(messages, *, prefix):
    """Return JSON records from explicit text messages bearing a required prefix.

    Callers select the documented message channel before calling this helper.
    Nonmatching messages are unrelated and omitted; malformed matching JSON
    raises its original parser error. No records returns [], not proof of success.
    """
    if not prefix:
        raise ValueError("An explicit nonempty message prefix is required.")
    return [_json.loads(message[len(prefix):]) for message in messages
            if message.startswith(prefix)]


def wait_until(probe, *, timeout, interval=0.02):
    """Return the first truthy probe value within a finite monotonic deadline.

    False values cause bounded retries; probe errors propagate immediately.
    Expiration raises AssertionError. The probe itself is also bounded by a
    Linux main-thread alarm; this helper cannot nest inside call_public.
    """
    timeout, interval = _seconds(timeout), _seconds(interval)
    with _deadline(timeout):
        end = _time.monotonic() + timeout
        while True:
            value = probe()
            if value:
                return value
            remaining = end - _time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"Observation did not arrive within {timeout}s.")
            _time.sleep(min(interval, remaining))


@_contextlib.contextmanager
def browser_page(browser, target, *, timeout=30):
    """Yield a rendered Playwright page using a supplied real browser instance.

    target is an explicit URL or Path (converted to a file URL). Navigation and
    subsequent page actions use finite default timeouts. Callers own selectors
    and interactions. Browser errors propagate; no skip, source-text substitute,
    status interpretation or browser installation is attempted. The owned
    context closes on exit; the caller's browser remains open.
    """
    milliseconds = _seconds(timeout) * 1000
    context = browser.new_context()
    try:
        page = context.new_page()
        page.set_default_timeout(milliseconds)
        page.set_default_navigation_timeout(milliseconds)
        url = target.resolve().as_uri() if isinstance(target, _Path) else target
        page.goto(url, wait_until="load", timeout=milliseconds)
        yield page
    finally:
        context.close()


def require_python(version):
    """Return interpreter version information if its major/minor matches version.

    version is an explicit (major, minor) pair for independent semantic oracles.
    Mismatch raises RuntimeError, never skips tests or substitutes another
    interpreter. This checks environment only and conveys no product exit code.
    """
    if _sys.version_info[:2] != tuple(version):
        raise RuntimeError(f"Required Python {tuple(version)!r}; "
                           f"running {_sys.version_info[:2]!r}.")
    return _sys.version_info
