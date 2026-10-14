# feature: F00
"""Shared machinery for driving the product through its public surface.

Suites import from this module (``from _harness import ...``). Importing it
performs no I/O, starts no processes, and opens no sockets. Stream capture,
environment replacement, cwd changes, clock replacement, timezone
changes, file opens, and child processes happen only when a caller
invokes a function or enters a context manager below.

The product is an importable Python library (src layout). There is no
command-line program and no network service. This module is the one
canonical way to reach the public entries. It does not import the
product and does not know what any feature expects.

Surfaces
--------
* Library call — :func:`call` runs a caller-supplied public callable
  (imported by the suite from the package root) with caller-controlled
  arguments, stdin, environment, and working directory. A product
  exception is a classified outcome on :class:`CallResult`, not a
  harness failure. Extra keyword arguments (digit count, digest,
  account name, issuer, starting counter, time-step length, extra
  query fields) are forwarded unchanged.
* Bound-method call — :func:`call_method` looks up a named callable
  attribute on a value a public constructor returned and drives it
  through the same capture path. The attribute name is supplied by the
  suite.
* Process clock — :func:`frozen_clock` replaces ``time.time``,
  ``time.time_ns`` and ``datetime.datetime.now`` / ``utcnow`` / ``today``
  for the duration of a block so
  a current-clock entry and an explicit-instant entry can be compared
  at the same Unix epoch without sleeping. This module does not
  interpret time-step length or acceptance windows.
* Instant construction — :func:`utc_datetime` and :func:`local_datetime`
  build the two instant kinds a public time entry accepts (timezone-aware
  UTC, and naive host-local). A naive datetime is refused as an input
  epoch: it is not a classified absolute instant.
* Child interpreter — :func:`run_python` / :func:`run_script` /
  :func:`run_command` for observations that need a separate process,
  including the library-substrate negative control (package removed
  from the import path).

Each isolated call starts from a whitelist of substrate environment
keys. Names that are not on that list are dropped so an incidental
parent variable cannot fill a condition the suite did not name.

A failure this module cannot classify raises :class:`HarnessError`.
"""

from __future__ import annotations

import datetime as datetime_module
import inspect
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time as time_module
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import TracebackType
from typing import Any, Callable, Iterator, Mapping, Sequence
from warnings import WarningMessage, catch_warnings, simplefilter

# ---------------------------------------------------------------------------
# Public defaults
# ---------------------------------------------------------------------------

DEFAULT_CHARSET = "utf-8"
DEFAULT_TIMEOUT = 30.0

# Isolated child / in-process environments start from this Unicode locale.
_DEFAULT_LOCALE = "C.UTF-8"

# Substrate keys copied from the caller when building an isolated env.
# Everything else is dropped so an incidental parent variable cannot
# fill a condition the suite did not name.
_KEEP_ENV_KEYS = (
    "PATH",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSAFEPATH",
    "PYTHONNOUSERSITE",
    "PYTHONHASHSEED",
    "PYTHONUNBUFFERED",
    "PYTHONWARNINGS",
    "PYTHONDONTWRITEBYTECODE",
    "TMPDIR",
    "TEMP",
    "TMP",
    "TZ",
    "USER",
    "LOGNAME",
    "USERNAME",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "TERM",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
)

# TTY / pager / editor / proxy side-channels stripped even if kept above.
_ISOLATE_UNSET = (
    "COLUMNS",
    "LINES",
    "PAGER",
    "EDITOR",
    "VISUAL",
    "BROWSER",
    "NO_COLOR",
    "FORCE_COLOR",
    "CLICOLOR",
    "CLICOLOR_FORCE",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "DBUS_SESSION_BUS_ADDRESS",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
)

# Directory names that are never the importable product package.
_PACKAGE_SKIP = {
    "tests",
    "test",
    "docs",
    "doc",
    "examples",
    "example",
    "build",
    "dist",
    "extra",
    "extras",
    "scripts",
    "script",
    "bin",
    "perf",
    "legacy",
    "benchmarks",
    "benchmark",
}


# ---------------------------------------------------------------------------
# Errors / result types
# ---------------------------------------------------------------------------


class HarnessError(RuntimeError):
    """Raised when an observation cannot be classified.

    Used for a missing substrate, a path that escapes its workspace, a
    timeout, a stream that is not valid in the requested encoding, a
    clock instant that cannot be converted, a missing callable
    attribute, and I/O failures that are not a documented product
    outcome. Never used to mean "the product raised the exception the
    PRD describes".
    """


def _decode_utf8(data: bytes, *, stream: str) -> str:
    """Decode *data* as UTF-8.

    Raises:
        HarnessError: if *data* is not valid UTF-8. Never replaces
            undecodable bytes with a sentinel that could pass for text.
    """
    try:
        return data.decode(DEFAULT_CHARSET)
    except UnicodeDecodeError as exc:
        raise HarnessError(f"{stream} is not valid UTF-8: {exc}") from exc


def as_bytes(content: str | bytes, *, encoding: str = DEFAULT_CHARSET) -> bytes:
    """Return *content* as bytes.

    ``bytes`` is returned unchanged. ``str`` is encoded with *encoding*.
    Raises :class:`HarnessError` if the text cannot be encoded — never
    replaces unencodable characters with a sentinel. An integer or
    other non-text value is refused: never ``str()``-converted.
    """
    if isinstance(content, bytes):
        return content
    if not isinstance(content, str):
        raise HarnessError(
            f"cannot encode {type(content).__name__} as {encoding}; "
            "only str or bytes are accepted"
        )
    try:
        return content.encode(encoding)
    except (LookupError, UnicodeEncodeError) as exc:
        raise HarnessError(f"cannot encode text as {encoding}: {exc}") from exc


def as_text(content: str | bytes, *, encoding: str = DEFAULT_CHARSET) -> str:
    """Return *content* as text.

    ``str`` is returned unchanged. ``bytes`` is decoded with *encoding*.
    Raises :class:`HarnessError` if the bytes are not valid in
    *encoding*, or if *content* is neither str nor bytes — never
    converts an integer (or any other type) with ``str()``. A numeric
    code is not text.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, (bytes, bytearray)):
        raise HarnessError(
            f"cannot decode {type(content).__name__} as {encoding}; "
            "only str or bytes are accepted"
        )
    try:
        return bytes(content).decode(encoding)
    except (LookupError, UnicodeDecodeError) as exc:
        raise HarnessError(f"cannot decode bytes as {encoding}: {exc}") from exc


@dataclass(frozen=True)
class CallResult:
    """Outcome of one in-process library call.

    Attributes:
        value: Whatever the callable returned. ``None`` when an
            exception was captured — never a stand-in for "the call
            could not be performed". A successful host-none return is
            distinguished by ``exception is None``. A successful
            boolean false is a real ``False`` on ``value``.
        exception: The exception that ended the call, if any. ``None``
            when the callable returned. ``SystemExit`` is recorded here
            the same way as any other product exception.
        exc_info: ``sys.exc_info()`` triple matching ``exception``, or
            ``None``.
        stdout: Raw standard output bytes captured for the duration.
        stderr: Raw standard error bytes captured for the duration.
        cwd: Working directory used for the call, as a string.
        environ: Process environment mapping as it stood when the
            callable returned or raised, still inside the isolated
            environment. Always a dict — never ``None``. Absence of a
            name is ``name not in environ``, not a failed observation.
        warnings: Warning records captured for the duration of the call.
            Empty when none were emitted — never ``None``.
    """

    value: Any
    exception: BaseException | None
    exc_info: tuple[type[BaseException], BaseException, TracebackType] | None
    stdout: bytes
    stderr: bytes
    cwd: str
    environ: dict[str, str]
    warnings: tuple[WarningMessage, ...] = field(default_factory=tuple)

    @property
    def stdout_text(self) -> str:
        """Stdout decoded as UTF-8. Raises :class:`HarnessError` if not."""
        return _decode_utf8(self.stdout, stream="stdout")

    @property
    def stderr_text(self) -> str:
        """Stderr decoded as UTF-8. Raises :class:`HarnessError` if not."""
        return _decode_utf8(self.stderr, stream="stderr")


@dataclass(frozen=True)
class RunResult:
    """Outcome of one subprocess invocation.

    Attributes:
        returncode: Process exit status. The harness does not interpret it.
        stdout: Raw standard output bytes.
        stderr: Raw standard error bytes.
        argv: Exact argument vector that was executed.
        cwd: Working directory used for the process, as a string.
        environ: Environment mapping passed to the child. Always a dict
            — never ``None``. This is the mapping the child started
            with, not a probe of the child's later state.
    """

    returncode: int
    stdout: bytes
    stderr: bytes
    argv: tuple[str, ...]
    cwd: str
    environ: dict[str, str]

    @property
    def stdout_text(self) -> str:
        """Stdout decoded as UTF-8. Raises :class:`HarnessError` if not."""
        return _decode_utf8(self.stdout, stream="stdout")

    @property
    def stderr_text(self) -> str:
        """Stderr decoded as UTF-8. Raises :class:`HarnessError` if not."""
        return _decode_utf8(self.stderr, stream="stderr")


@dataclass
class FrozenClock:
    """A process clock whose current instant the caller controls.

    ``epoch`` is seconds since the Unix epoch. Advancing the clock with
    :meth:`tick` does not sleep. Does not interpret time-step length.
    """

    epoch: float

    @property
    def instant(self) -> datetime:
        """Timezone-aware UTC datetime of the current frozen epoch."""
        try:
            return datetime.fromtimestamp(self.epoch, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise HarnessError(
                f"frozen epoch {self.epoch!r} is not a calendar datetime: {exc}"
            ) from exc

    def tick(self, seconds: float | timedelta = 1.0) -> float:
        """Advance the clock by *seconds* and return the new epoch.

        *seconds* may be a number or a ``timedelta``. A negative value
        moves the clock backwards. Does not sleep.
        """
        if isinstance(seconds, timedelta):
            delta = seconds.total_seconds()
        else:
            try:
                delta = float(seconds)
            except (TypeError, ValueError) as exc:
                raise HarnessError(
                    f"clock tick is not a number of seconds: {seconds!r}"
                ) from exc
        self.epoch += delta
        return self.epoch


@dataclass
class Workspace:
    """Ephemeral work directory plus the isolated environment bound to it.

    ``path`` is the working directory for calls and child processes.
    ``home`` is used as ``HOME`` so ``~`` expansion cannot see the
    caller's home. ``root`` is the built repository root used to locate
    ``src/`` (captured when the workspace was allocated, not looked up
    from the then-current cwd). All workspace trees are removed when
    the allocating context exits.
    """

    path: Path
    home: Path
    env: dict[str, str]
    root: Path

    def resolve(self, relpath: str | Path) -> Path:
        """Return *relpath* resolved under this workspace.

        Raises:
            HarnessError: when the resolved path escapes the workspace.
        """
        base = self.path.resolve()
        target = (base / relpath).resolve()
        if not _is_relative_to(target, base):
            raise HarnessError(f"path {relpath!r} escapes workspace {base}")
        return target

    def write(
        self,
        relpath: str | Path,
        content: str | bytes,
        *,
        encoding: str = DEFAULT_CHARSET,
    ) -> Path:
        """Write *content* under this workspace, creating parents.

        Returns the absolute path written. Raises ``OSError`` on I/O
        failure and :class:`HarnessError` if *relpath* escapes the
        workspace or text cannot be encoded.
        """
        dest = self.resolve(relpath)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            dest.write_bytes(content)
        else:
            dest.write_bytes(as_bytes(content, encoding=encoding))
        return dest

    def read(self, relpath: str | Path, *, encoding: str = DEFAULT_CHARSET) -> str:
        """Read a text file under this workspace.

        Raises:
            HarnessError: if *relpath* escapes the workspace, if the
                path exists but is not a regular file, or if the bytes
                are not valid in *encoding*.
            FileNotFoundError: if the file does not exist — never
                returns an empty string or ``None`` to mean "missing".
            OSError: on other I/O failures.
        """
        return read_file(self.resolve(relpath), encoding=encoding)

    def read_bytes(self, relpath: str | Path) -> bytes:
        """Read a binary file under this workspace.

        Raises ``FileNotFoundError`` if the file does not exist — never
        returns empty bytes to mean "missing". Raises :class:`HarnessError`
        if the path exists but is not a regular file.
        """
        return read_bytes(self.resolve(relpath))

    def mkdir(self, relpath: str | Path) -> Path:
        """Create a directory under this workspace (parents included)."""
        dest = self.resolve(relpath)
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def call(
        self,
        fn: Callable[..., Any],
        /,
        *args: Any,
        stdin: str | bytes | None = None,
        env: Mapping[str, str | None] | None = None,
        catch: bool = True,
        charset: str = DEFAULT_CHARSET,
        **kwargs: Any,
    ) -> CallResult:
        """Call *fn* with this workspace as cwd and environment."""
        merged = _apply_updates(self.env, env)
        return call(
            fn,
            *args,
            stdin=stdin,
            env=merged,
            cwd=self.path,
            isolate=False,
            catch=catch,
            charset=charset,
            **kwargs,
        )

    def call_method(
        self,
        obj: Any,
        name: str,
        /,
        *args: Any,
        stdin: str | bytes | None = None,
        env: Mapping[str, str | None] | None = None,
        catch: bool = True,
        charset: str = DEFAULT_CHARSET,
        **kwargs: Any,
    ) -> CallResult:
        """Call attribute *name* of *obj* with this workspace as cwd/env."""
        merged = _apply_updates(self.env, env)
        return call_method(
            obj,
            name,
            *args,
            stdin=stdin,
            env=merged,
            cwd=self.path,
            isolate=False,
            catch=catch,
            charset=charset,
            **kwargs,
        )

    def run_command(
        self,
        argv: Sequence[str],
        *,
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
    ) -> RunResult:
        """Run *argv* with this workspace as cwd and environment."""
        merged = _apply_updates(self.env, env)
        return run_command(
            argv,
            cwd=cwd if cwd is not None else self.path,
            env=merged,
            stdin=stdin,
            timeout=timeout,
        )

    def run_python(
        self,
        *,
        code: str | None = None,
        argv: Sequence[str] | None = None,
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
        include_product: bool = True,
    ) -> RunResult:
        """Run this process's interpreter with this workspace as cwd/env."""
        merged = _apply_updates(self.env, env)
        if not include_product:
            merged = _environ_without_product(merged, root=self.root)
        return run_python(
            code=code,
            argv=argv,
            cwd=cwd if cwd is not None else self.path,
            env=merged,
            stdin=stdin,
            timeout=timeout,
            isolate=False,
            root=self.root,
            include_product=include_product,
        )

    def run_script(
        self,
        source: str,
        *,
        relpath: str = "caller.py",
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
        include_product: bool = True,
    ) -> RunResult:
        """Write *source* under this workspace and run it as a script."""
        merged = _apply_updates(self.env, env)
        if not include_product:
            merged = _environ_without_product(merged, root=self.root)
        script = self.write(relpath, source)
        work = cwd if cwd is not None else self.path
        return run_python(
            argv=[str(script)],
            cwd=work,
            env=merged,
            stdin=stdin,
            timeout=timeout,
            isolate=False,
            root=self.root,
            include_product=include_product,
        )


# ---------------------------------------------------------------------------
# Stream helpers
# ---------------------------------------------------------------------------


class _KeepOpenTextIO(io.TextIOWrapper):
    """TextIOWrapper that does not close its underlying buffer."""

    def close(self) -> None:
        try:
            self.flush()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _apply_updates(
    env: Mapping[str, str],
    updates: Mapping[str, str | None] | None,
) -> dict[str, str]:
    merged = dict(env)
    if updates:
        for key, value in updates.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = str(value)
    return merged


def _read_regular_file(src: Path) -> None:
    """Raise a classified error when *src* is missing or not a regular file.

    Follows a symlink to a regular file (the same as ``open()``). A
    directory or other non-file is a harness failure, not an empty read.
    """
    try:
        if not src.exists():
            raise FileNotFoundError(f"file does not exist: {src}")
        if not src.is_file():
            raise HarnessError(f"path exists but is not a regular file: {src}")
    except FileNotFoundError:
        raise
    except HarnessError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc


def _require_callable(fn: Any, *, label: str) -> Callable[..., Any]:
    if not callable(fn):
        raise HarnessError(f"{label} is not callable; got {type(fn)!r}")
    return fn


def _capture_exc_info() -> (
    tuple[type[BaseException], BaseException, TracebackType] | None
):
    info = sys.exc_info()
    if info[0] is not None and info[1] is not None and info[2] is not None:
        return (info[0], info[1], info[2])
    return None


def _open_text(buffer: Any, *, charset: str) -> _KeepOpenTextIO:
    return _KeepOpenTextIO(
        buffer,
        encoding=charset,
        line_buffering=True,
        write_through=True,
    )


def _python() -> str:
    python = sys.executable
    if not python:
        raise HarnessError("sys.executable is empty; cannot spawn an interpreter")
    return python


def _as_epoch(instant: datetime | int | float) -> float:
    if isinstance(instant, datetime):
        if instant.tzinfo is None:
            raise HarnessError(
                "clock instant datetime must be timezone-aware; "
                "a naive datetime is not a classified absolute instant"
            )
        try:
            return instant.timestamp()
        except (OverflowError, OSError, ValueError) as exc:
            raise HarnessError(
                f"cannot convert datetime {instant!r} to an epoch: {exc}"
            ) from exc
    try:
        return float(instant)
    except (TypeError, ValueError) as exc:
        raise HarnessError(
            f"clock instant is not a datetime or epoch: {instant!r}"
        ) from exc


# ---------------------------------------------------------------------------
# Observation helpers (Rule 1: unclassifiable lookup raises)
# ---------------------------------------------------------------------------


def require_value(result: CallResult) -> Any:
    """Return the value of a call that returned.

    Raises:
        HarnessError: if an exception was captured — never returns
            ``None`` to mean "the call failed". A successful return of
            ``None`` is a real ``None`` value and is returned as such.
            A successful return of ``False`` is a real ``False``.
    """
    if result.exception is not None:
        raise HarnessError(
            "call raised "
            f"{type(result.exception).__name__}: {result.exception!r}; "
            "there is no return value to observe"
        )
    return result.value


def require_exception(result: CallResult) -> BaseException:
    """Return the exception captured from a call.

    Raises:
        HarnessError: if the callable returned — never returns ``None``
            to mean "no exception".
    """
    if result.exception is None:
        raise HarnessError(
            "call returned a value; there is no exception to observe "
            f"(value type={type(result.value)!r})"
        )
    return result.exception


def require_text(result: CallResult) -> str:
    """Return the call value as a text string.

    Raises :class:`HarnessError` if the call raised, or if the value is
    not a ``str``. An integer is refused — never converted — so a
    numeric code cannot pass as the text string a public entry publishes.
    """
    value = require_value(result)
    if not isinstance(value, str):
        raise HarnessError(
            f"call returned {type(value).__name__}, not text; "
            "there is no text string to observe"
        )
    return value


def require_bool(result: CallResult) -> bool:
    """Return the call value as a boolean.

    Raises :class:`HarnessError` if the call raised, or if the value is
    not ``True`` or ``False``. An integer 0/1 is refused — never treated
    as a boolean outcome.
    """
    value = require_value(result)
    if type(value) is not bool:
        raise HarnessError(
            f"call returned {type(value).__name__}, not bool; "
            "there is no boolean outcome to observe"
        )
    return value


def require_int(result: CallResult) -> int:
    """Return the call value as an integer.

    Raises :class:`HarnessError` if the call raised, or if the value is
    not an ``int``. ``True`` / ``False`` are refused — they are bools,
    not a matching step number. A failed matching-step check that
    returns ``False`` has no integer to observe.
    """
    value = require_value(result)
    if type(value) is not int:
        raise HarnessError(
            f"call returned {type(value).__name__}, not int; "
            "there is no integer to observe"
        )
    return value


def attr(obj: Any, name: str) -> Any:
    """Read attribute *name* from *obj*.

    Raises:
        HarnessError: if *obj* is ``None``, or if *name* is not present
            on *obj*. A present attribute whose value is ``None`` is
            returned as ``None`` — that is classified absence of the
            field, not a failed lookup.
    """
    if obj is None:
        raise HarnessError(f"cannot read {name!r} from None")
    try:
        present = hasattr(obj, name)
    except Exception as exc:
        raise HarnessError(
            f"cannot probe attribute {name!r} on {type(obj).__name__}: {exc}"
        ) from exc
    if not present:
        raise HarnessError(f"{type(obj).__name__} has no attribute {name!r}")
    return getattr(obj, name)


def require_callable_attr(obj: Any, name: str) -> Callable[..., Any]:
    """Return callable attribute *name* of *obj*.

    Raises :class:`HarnessError` if the attribute is missing or is not
    callable — never returns ``None`` to mean "no such method".
    """
    value = attr(obj, name)
    return _require_callable(value, label=f"attribute {name!r}")


def exception_type_name(exc: BaseException) -> str:
    """Return the class name of *exc*.

    Raises :class:`HarnessError` if *exc* is not an exception instance.
    """
    if not isinstance(exc, BaseException):
        raise HarnessError(
            f"exception_type_name expected an exception; got {type(exc)!r}"
        )
    return type(exc).__name__


def exception_text(exc: BaseException) -> str:
    """Return ``str(exc)`` for a captured exception.

    Raises :class:`HarnessError` if *exc* is not an exception instance.
    An empty string is a real empty message, not a stand-in for "the
    exception could not be read".
    """
    if not isinstance(exc, BaseException):
        raise HarnessError(
            f"exception_text expected an exception; got {type(exc)!r}"
        )
    return str(exc)


# ---------------------------------------------------------------------------
# Instant construction (timezone-aware UTC vs naive local)
# ---------------------------------------------------------------------------


def utc_datetime(instant: datetime | int | float) -> datetime:
    """Return a timezone-aware UTC datetime for *instant*.

    *instant* is a timezone-aware ``datetime`` or a Unix epoch. A naive
    datetime is refused: it is not a classified absolute instant.
    """
    epoch = _as_epoch(instant)
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise HarnessError(
            f"cannot convert epoch {epoch!r} to a UTC datetime: {exc}"
        ) from exc


def local_datetime(instant: datetime | int | float) -> datetime:
    """Return a naive host-local datetime for *instant*.

    *instant* is a timezone-aware ``datetime`` or a Unix epoch. The
    result is ``datetime.fromtimestamp(epoch)`` with no ``tzinfo`` — the
    same civil time the host local timezone assigns to that instant. A
    naive datetime is refused: it is not a classified absolute instant.
    """
    epoch = _as_epoch(instant)
    try:
        return datetime.fromtimestamp(epoch)
    except (OverflowError, OSError, ValueError) as exc:
        raise HarnessError(
            f"cannot convert epoch {epoch!r} to a local datetime: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Paths / discovery
# ---------------------------------------------------------------------------


def repo_root() -> Path:
    """Return the built repository root.

    Tests run with the repository root as the pytest process cwd. Returns
    ``Path.cwd()`` resolved; does not search the filesystem.
    """
    return Path.cwd().resolve()


def product_import_root(*, root: Path | None = None) -> Path:
    """Return the directory that must be on ``PYTHONPATH`` to import the product.

    Prefers ``<root>/src`` when that directory exists (src layout).
    Otherwise the repository root itself (flat layout). Raises
    :class:`HarnessError` on a stat failure — never returns a missing
    path as if it were the import root.
    """
    base = (root if root is not None else repo_root()).resolve()
    src = base / "src"
    try:
        if src.is_dir():
            return src.resolve()
    except OSError as exc:
        raise HarnessError(f"cannot stat product import root {src}: {exc}") from exc
    return base


def product_src_dir(*, root: Path | None = None) -> Path:
    """Alias of :func:`product_import_root` (src layout or flat layout)."""
    return product_import_root(root=root)


def product_package_dir(*, root: Path | None = None) -> Path:
    """Return the single top-level package directory under the import root.

    Discovery is filesystem-only and does not import the product.

    Raises:
        HarnessError: when zero or several candidate package directories
            exist. That is a substrate gap, not a product-behavior
            judgment.
    """
    import_root = product_import_root(root=root)
    candidates: list[Path] = []
    try:
        children = list(import_root.iterdir())
    except OSError as exc:
        raise HarnessError(f"cannot list {import_root}: {exc}") from exc
    for child in children:
        try:
            if not child.is_dir() or child.name.startswith(".") or child.name in _PACKAGE_SKIP:
                continue
            if child.name.startswith("_"):
                continue
            marker = child / "__init__.py"
            if marker.is_file():
                candidates.append(child)
        except OSError as exc:
            raise HarnessError(f"cannot stat {child}: {exc}") from exc
    if len(candidates) != 1:
        names = [c.name for c in candidates]
        raise HarnessError(
            "expected exactly one top-level package directory under "
            f"{import_root}; found {names!r}"
        )
    return candidates[0].resolve()


def product_package_name(*, root: Path | None = None) -> str:
    """Return the importable package name (the directory under the import root)."""
    return product_package_dir(root=root).name


def _pythonpath_parts(env: Mapping[str, str]) -> list[str]:
    raw = env.get("PYTHONPATH", "")
    return [part for part in raw.split(os.pathsep) if part]


def _environ_with_product(env: Mapping[str, str], *, root: Path) -> dict[str, str]:
    merged = dict(env)
    import_root = product_import_root(root=root)
    root_s = str(import_root)
    parts = [root_s]
    parts.extend(part for part in _pythonpath_parts(merged) if part != root_s)
    merged["PYTHONPATH"] = os.pathsep.join(parts)
    return merged


def _blocked_product_paths(*, root: Path) -> set[Path]:
    blocked = {root.resolve()}
    try:
        blocked.add(product_import_root(root=root))
    except HarnessError:
        pass
    try:
        blocked.add(product_package_dir(root=root))
    except HarnessError:
        pass
    return blocked


def _environ_without_product(
    env: Mapping[str, str], *, root: Path | None = None
) -> dict[str, str]:
    merged = dict(env)
    base = (root if root is not None else repo_root()).resolve()
    blocked = _blocked_product_paths(root=base)
    kept: list[str] = []
    for part in _pythonpath_parts(merged):
        try:
            resolved = Path(part).resolve()
        except OSError:
            kept.append(part)
            continue
        if resolved in blocked:
            continue
        kept.append(part)
    if kept:
        merged["PYTHONPATH"] = os.pathsep.join(kept)
    else:
        merged.pop("PYTHONPATH", None)
    return merged


def _product_scrub_preamble(*, root: Path | None = None) -> str:
    """Python source that drops the product from a child's import path.

    Used only in a child interpreter so the library-substrate negative
    control does not accidentally import through cwd, a leftover
    ``PYTHONPATH`` entry, or an editable install that still points at
    the product tree. Does not run at harness import time.
    """
    base = (root if root is not None else repo_root()).resolve()
    import_root = product_import_root(root=base)
    package = product_package_dir(root=base)
    pkg_name = package.name
    return (
        "import sys\n"
        "from pathlib import Path\n"
        f"_ROOT = Path({str(base)!r}).resolve()\n"
        f"_IMPORT_ROOT = Path({str(import_root)!r}).resolve()\n"
        f"_PKG = Path({str(package)!r}).resolve()\n"
        f"_PKG_NAME = {pkg_name!r}\n"
        "def _keep(entry):\n"
        "    try:\n"
        "        p = Path(entry).resolve()\n"
        "    except OSError:\n"
        "        return True\n"
        "    return p not in {_ROOT, _IMPORT_ROOT, _PKG}\n"
        "sys.path[:] = [e for e in sys.path if _keep(e)]\n"
        "for _key in list(sys.modules):\n"
        "    if _key == _PKG_NAME or _key.startswith(_PKG_NAME + '.'):\n"
        "        del sys.modules[_key]\n"
        "class _BlockProduct:\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        head = fullname.split('.', 1)[0]\n"
        "        if head == _PKG_NAME:\n"
        "            raise ImportError(\n"
        "                'product package is not importable in this child'\n"
        "            )\n"
        "        return None\n"
        "sys.meta_path.insert(0, _BlockProduct())\n"
    )


# ---------------------------------------------------------------------------
# Environment / workspace isolation
# ---------------------------------------------------------------------------


def isolated_environ(
    home: Path | str,
    *,
    updates: Mapping[str, str | None] | None = None,
    base: Mapping[str, str] | None = None,
    root: Path | None = None,
    include_product: bool = True,
) -> dict[str, str]:
    """Build an environment that does not inherit the caller's extras.

    Copies a whitelist of substrate keys from *base* (or ``os.environ``),
    points ``HOME`` and the XDG dirs at *home*, prepends or strips the
    product import root on ``PYTHONPATH`` according to *include_product*,
    unsets pager/editor/proxy side-channels, sets a Unicode locale, and
    applies *updates* last (``None`` unsets). Does not mutate
    ``os.environ``.

    Returns a new ``dict``.
    """
    home_path = Path(home).resolve()
    cfg_dir = home_path / ".config"
    cache_dir = home_path / ".cache"
    data_dir = home_path / ".local" / "share"
    state_dir = home_path / ".local" / "state"
    for directory in (home_path, cfg_dir, cache_dir, data_dir, state_dir):
        directory.mkdir(parents=True, exist_ok=True)

    source = base if base is not None else os.environ
    env: dict[str, str] = {}
    for key in _KEEP_ENV_KEYS:
        value = source.get(key)
        if value is not None:
            env[key] = value
    for key in _ISOLATE_UNSET:
        env.pop(key, None)

    repo = (root if root is not None else repo_root()).resolve()
    if include_product:
        env = _environ_with_product(env, root=repo)
    else:
        env = _environ_without_product(env, root=repo)

    env["HOME"] = str(home_path)
    env["XDG_CONFIG_HOME"] = str(cfg_dir)
    env["XDG_CACHE_HOME"] = str(cache_dir)
    env["XDG_DATA_HOME"] = str(data_dir)
    env["XDG_STATE_HOME"] = str(state_dir)
    env.setdefault("LANG", _DEFAULT_LOCALE)
    env.setdefault("LC_ALL", _DEFAULT_LOCALE)
    env.setdefault("TERM", "dumb")

    if updates:
        env = _apply_updates(env, updates)
    return env


@contextmanager
def in_directory(path: str | Path) -> Iterator[Path]:
    """Change the process cwd to *path* and restore it on exit.

    Restores the previous cwd even if the block raises. Does not create
    or delete *path*.
    """
    dest = Path(path).resolve()
    if not dest.is_dir():
        raise HarnessError(f"in_directory target is not a directory: {dest}")
    previous = Path.cwd()
    os.chdir(dest)
    try:
        yield dest
    finally:
        os.chdir(previous)


@contextmanager
def _push_environ(new_env: Mapping[str, str]) -> Iterator[None]:
    """Replace ``os.environ`` with *new_env* and restore it on exit."""
    old = os.environ.copy()
    os.environ.clear()
    os.environ.update(new_env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old)


@contextmanager
def isolated_filesystem(
    path: str | Path | None = None,
    *,
    prefix: str = "harness-fs-",
) -> Iterator[Path]:
    """Temporarily ``chdir`` into an empty directory.

    When *path* is omitted, a new directory is created and removed on
    exit (including on exception). A caller-supplied *path* is created
    if missing and is left in place.
    """
    if path is None:
        dest = Path(tempfile.mkdtemp(prefix=prefix))
        remove = True
    else:
        dest = Path(path)
        dest.mkdir(parents=True, exist_ok=True)
        dest = dest.resolve()
        if not dest.is_dir():
            raise HarnessError(f"isolated_filesystem target is not a directory: {dest}")
        remove = False
    try:
        with in_directory(dest):
            yield dest
    finally:
        if remove:
            shutil.rmtree(dest, ignore_errors=True)


@contextmanager
def workspace(
    *,
    updates: Mapping[str, str | None] | None = None,
    prefix: str = "harness-ws-",
    root: Path | None = None,
    include_product: bool = True,
) -> Iterator[Workspace]:
    """Allocate an ephemeral work directory and isolated HOME; clean up.

    Yields a :class:`Workspace`. Both directory trees are removed when
    the context exits, including on exception. The product tree is never
    used as the default cwd. *root* is captured now, while the process
    cwd is still the repository root.
    """
    repo = (root if root is not None else repo_root()).resolve()
    work = Path(tempfile.mkdtemp(prefix=prefix))
    home = Path(tempfile.mkdtemp(prefix="harness-home-"))
    try:
        env = isolated_environ(
            home,
            updates=updates,
            root=repo,
            include_product=include_product,
        )
        yield Workspace(path=work, home=home, env=env, root=repo)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


@contextmanager
def process_timezone(name: str | None) -> Iterator[str | None]:
    """Set the process timezone to *name* (or unset) and restore it.

    Writes ``TZ`` and calls ``time.tzset()`` so naive-local conversions
    follow *name*. Restores the previous ``TZ`` and calls ``tzset``
    again on exit, including on exception. Does not sleep.
    """
    previous = os.environ.get("TZ")
    if name is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = name
    try:
        time_module.tzset()
    except AttributeError as exc:
        raise HarnessError(
            "process_timezone requires time.tzset (Unix); "
            f"this interpreter does not provide it: {exc}"
        ) from exc
    try:
        print(f"[harness] timezone_set tz={name!r}", flush=True)
        yield name
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time_module.tzset()
        print(f"[harness] timezone_restore tz={previous!r}", flush=True)


def _patch_datetime_now(clock: FrozenClock) -> tuple[type, list[tuple[Any, str, Any]]]:
    """Replace ``datetime.datetime.now`` / ``utcnow`` / ``today`` for the current process.

    The C ``datetime.datetime`` type cannot have its methods assigned, so
    the datetime module's ``datetime`` attribute is replaced with a
    subclass that overrides ``now`` / ``utcnow`` / ``today``. Already-imported
    ``from datetime import datetime`` bindings that still point at the
    real class are updated the same way.

    ``isinstance(real_dt, datetime.datetime)`` stays true for real
    datetime instances via the subclass metaclass.

    Returns ``(real_cls, restorations)`` so the caller can undo the
    patch. Does not run at import time.
    """
    real_cls = datetime_module.datetime

    class _FrozenDateTimeMeta(type(real_cls)):
        def __instancecheck__(cls, instance: Any) -> bool:
            return isinstance(instance, real_cls)

        def __subclasscheck__(cls, subclass: type) -> bool:
            try:
                return issubclass(subclass, real_cls)
            except TypeError:
                return False

    class FrozenDateTime(real_cls, metaclass=_FrozenDateTimeMeta):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return real_cls.fromtimestamp(clock.epoch, tz)

        @classmethod
        def utcnow(cls) -> datetime:
            return real_cls.fromtimestamp(clock.epoch, tz=timezone.utc).replace(
                tzinfo=None
            )

        @classmethod
        def today(cls) -> datetime:
            return real_cls.fromtimestamp(clock.epoch)

    restorations: list[tuple[Any, str, Any]] = []
    datetime_module.datetime = FrozenDateTime
    restorations.append((datetime_module, "datetime", real_cls))

    for _name, mod in list(sys.modules.items()):
        if mod is None or mod is datetime_module:
            continue
        try:
            bound = getattr(mod, "datetime", None)
        except Exception:
            continue
        if bound is real_cls:
            try:
                setattr(mod, "datetime", FrozenDateTime)
            except Exception:
                continue
            restorations.append((mod, "datetime", real_cls))
    # Product modules may bind the class under another name
    # (``from datetime import datetime as dt``); rebind those too.
    try:
        pkg = product_package_name()
    except Exception:
        pkg = None
    if pkg:
        for mod_name, mod in list(sys.modules.items()):
            if mod is None or not (mod_name == pkg or mod_name.startswith(pkg + ".")):
                continue
            for attr_name, value in list(vars(mod).items()):
                if attr_name == "datetime" or value is not real_cls:
                    continue
                try:
                    setattr(mod, attr_name, FrozenDateTime)
                except Exception:
                    continue
                restorations.append((mod, attr_name, real_cls))
    return real_cls, restorations


@contextmanager
def frozen_clock(instant: datetime | int | float) -> Iterator[FrozenClock]:
    """Replace the process clock with a caller-controlled epoch for a block.

    Current-clock public entries read the standard-library wall clock
    (``time.time``, ``time.time_ns``, ``datetime.datetime.now`` /
    ``utcnow`` / ``today``). All of them are replaced for the duration,
    including names a product module bound from ``time`` at import. The originals
    are restored when the block exits, including on exception. Does not
    sleep. Does not interpret time-step length or acceptance windows.

    *instant* is a timezone-aware ``datetime`` or a Unix epoch
    (int/float). A naive datetime is refused: it is not a classified
    absolute instant.
    """
    clock = FrozenClock(_as_epoch(instant))
    original_time = time_module.time
    original_time_ns = time_module.time_ns

    def _frozen_time() -> float:
        return clock.epoch

    def _frozen_time_ns() -> int:
        return int(round(clock.epoch * 1_000_000_000))

    _real_cls, restorations = _patch_datetime_now(clock)
    time_module.time = _frozen_time  # type: ignore[method-assign]
    time_module.time_ns = _frozen_time_ns  # type: ignore[method-assign]
    # Product modules that bound the wall-clock functions by name at
    # import time (``from time import time``) read the same frozen clock.
    try:
        pkg = product_package_name()
    except Exception:
        pkg = None
    if pkg:
        for mod_name, mod in list(sys.modules.items()):
            if mod is None or not (
                mod_name == pkg or mod_name.startswith(pkg + ".")
            ):
                continue
            for attr_name, value in list(vars(mod).items()):
                if value is original_time:
                    replacement: Any = _frozen_time
                elif value is original_time_ns:
                    replacement = _frozen_time_ns
                else:
                    continue
                try:
                    setattr(mod, attr_name, replacement)
                except Exception:
                    continue
                restorations.append((mod, attr_name, value))
    try:
        print(
            f"[harness] clock_freeze epoch={clock.epoch!r} "
            f"instant={clock.instant.isoformat()}",
            flush=True,
        )
        yield clock
    finally:
        time_module.time = original_time
        time_module.time_ns = original_time_ns
        for owner, attr_name, previous in reversed(restorations):
            try:
                setattr(owner, attr_name, previous)
            except Exception:
                pass
        print(
            f"[harness] clock_restore epoch={clock.epoch!r}",
            flush=True,
        )


def write_file(
    path: str | Path,
    content: str | bytes,
    *,
    encoding: str = DEFAULT_CHARSET,
) -> Path:
    """Write *content* to *path*, creating parent directories.

    Returns the resolved path. Raises ``OSError`` on I/O failure and
    :class:`HarnessError` if text cannot be encoded.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        dest.write_bytes(content)
    else:
        dest.write_bytes(as_bytes(content, encoding=encoding))
    return dest.resolve()


def read_file(path: str | Path, *, encoding: str = DEFAULT_CHARSET) -> str:
    """Read *path* as text.

    Raises ``FileNotFoundError`` if the file does not exist — never
    returns an empty string or ``None`` to mean "missing". Raises
    :class:`HarnessError` if the path exists but is not a regular file,
    if the bytes are not valid in *encoding*, or on an ``OSError`` other
    than classified absence.
    """
    src = Path(path)
    _read_regular_file(src)
    try:
        return src.read_text(encoding=encoding)
    except FileNotFoundError:
        raise
    except LookupError as exc:
        raise HarnessError(f"unknown text encoding {encoding!r}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise HarnessError(f"cannot decode {src} as {encoding}: {exc}") from exc
    except OSError as exc:
        raise HarnessError(f"cannot read {src}: {exc}") from exc


def read_bytes(path: str | Path) -> bytes:
    """Read *path* as bytes.

    Raises ``FileNotFoundError`` if the file does not exist — never
    returns empty bytes to mean "missing". Raises :class:`HarnessError`
    if the path exists but is not a regular file, or on an ``OSError``
    other than classified absence.
    """
    src = Path(path)
    _read_regular_file(src)
    try:
        return src.read_bytes()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot read {src}: {exc}") from exc


def path_is_file(path: str | Path) -> bool:
    """Return whether *path* is an existing regular file.

    ``False`` means the path is absent or is not a regular file. Raises
    :class:`HarnessError` on an ``OSError`` other than a classified
    absence — never treats a permission or I/O failure as "not a file".
    """
    src = Path(path)
    try:
        return src.is_file() and not src.is_symlink()
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc


# ---------------------------------------------------------------------------
# In-process library call
# ---------------------------------------------------------------------------


def _run_captured(
    body: Callable[[], Any],
    *,
    stdin: str | bytes | None,
    env: Mapping[str, str],
    cwd: Path,
    charset: str,
    catch: bool,
) -> tuple[
    Any,
    BaseException | None,
    tuple | None,
    bytes,
    bytes,
    dict[str, str],
    tuple[WarningMessage, ...],
]:
    if stdin is None:
        input_bytes = b""
    elif isinstance(stdin, str):
        input_bytes = as_bytes(stdin, encoding=charset)
    else:
        input_bytes = stdin

    stdout_buf = io.BytesIO()
    stderr_buf = io.BytesIO()
    raw_in: Any = io.BytesIO(input_bytes)

    old_stdin = sys.stdin
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    value: Any = None
    exception: BaseException | None = None
    exc_info: tuple | None = None
    captured: list[WarningMessage] = []
    environ_after: dict[str, str] = {}

    try:
        sys.stdin = _open_text(raw_in, charset=charset)
        sys.stdout = _open_text(stdout_buf, charset=charset)
        sys.stderr = _open_text(stderr_buf, charset=charset)
        with _push_environ(env), in_directory(cwd):
            with catch_warnings(record=True) as captured:
                simplefilter("always")
                try:
                    value = body()
                    if inspect.isgenerator(value):
                        value = list(value)
                except (KeyboardInterrupt, GeneratorExit):
                    raise
                except BaseException as exc:
                    if not catch:
                        raise
                    exception = exc
                    exc_info = _capture_exc_info()
                finally:
                    environ_after = dict(os.environ)
                    try:
                        sys.stdout.flush()
                    except OSError:
                        pass
                    try:
                        sys.stderr.flush()
                    except OSError:
                        pass
    finally:
        sys.stdin = old_stdin
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return (
        value,
        exception,
        exc_info,
        stdout_buf.getvalue(),
        stderr_buf.getvalue(),
        environ_after,
        tuple(captured),
    )


def call(
    fn: Callable[..., Any],
    /,
    *args: Any,
    stdin: str | bytes | None = None,
    env: Mapping[str, str | None] | None = None,
    cwd: str | Path | None = None,
    isolate: bool = True,
    catch: bool = True,
    charset: str = DEFAULT_CHARSET,
    **kwargs: Any,
) -> CallResult:
    """Call a public library entry and capture its outcome.

    This is the canonical in-process path for a function, class, or
    bound method the suite imported from the public surface. Extra
    positional and keyword arguments are forwarded to *fn* unchanged.

    When *isolate* is true (the default) the call runs in a fresh
    :func:`workspace` so it cannot see the caller's cwd, HOME, or
    incidental environment variables. Pass ``isolate=False`` (and
    optionally *cwd* / *env*) to inherit the caller's process state, or
    to reuse a :class:`Workspace`. *env* is a complete mapping when
    supplied with ``isolate=False``; with ``isolate=True`` it is applied
    as updates on the isolated environment (``None`` unsets).

    A product exception is recorded on the result when *catch* is true
    (the default) and is never turned into ``value is None`` as a
    success. ``KeyboardInterrupt`` and ``GeneratorExit`` always
    propagate. Does not raise on a product exception when *catch* is
    true.
    """
    target = _require_callable(fn, label="call target")

    def _run(child_cwd: Path, child_env: Mapping[str, str]) -> CallResult:
        print(
            f"[harness] call fn={getattr(target, '__qualname__', type(target).__name__)!r} "
            f"cwd={str(child_cwd)!r}",
            flush=True,
        )
        value, exception, exc_info, stdout, stderr, environ_after, warns = _run_captured(
            lambda: target(*args, **kwargs),
            stdin=stdin,
            env=child_env,
            cwd=child_cwd,
            charset=charset,
            catch=catch,
        )
        result = CallResult(
            value=value if exception is None else None,
            exception=exception,
            exc_info=exc_info,
            stdout=stdout,
            stderr=stderr,
            cwd=str(child_cwd),
            environ=environ_after,
            warnings=warns,
        )
        print(
            f"[harness] call_done exception="
            f"{type(result.exception).__name__ if result.exception else None} "
            f"value_is_none={result.value is None} "
            f"stdout_len={len(result.stdout)} stderr_len={len(result.stderr)} "
            f"environ_keys={len(result.environ)}",
            flush=True,
        )
        if result.exception is not None and 0 < len(result.stderr) <= 2000:
            print(f"[harness] stderr={result.stderr_text!r}", flush=True)
        return result

    if isolate:
        with workspace(updates=env) as ws:
            work = Path(cwd).resolve() if cwd is not None else ws.path
            return _run(work, ws.env)

    if env is not None:
        child_env = {k: v for k, v in env.items() if v is not None}
    else:
        child_env = dict(os.environ)
    work = Path(cwd).resolve() if cwd is not None else Path.cwd()
    if not work.is_dir():
        raise HarnessError(f"call cwd is not a directory: {work}")
    return _run(work, child_env)


def call_method(
    obj: Any,
    name: str,
    /,
    *args: Any,
    stdin: str | bytes | None = None,
    env: Mapping[str, str | None] | None = None,
    cwd: str | Path | None = None,
    isolate: bool = True,
    catch: bool = True,
    charset: str = DEFAULT_CHARSET,
    **kwargs: Any,
) -> CallResult:
    """Call attribute *name* of *obj* through :func:`call`.

    Used after a public constructor returns a helper: the suite looks
    up the documented emit / check / URI-build method by name. A
    missing or non-callable attribute is a harness failure, not a
    product exception and not a successful none.
    """
    target = require_callable_attr(obj, name)
    return call(
        target,
        *args,
        stdin=stdin,
        env=env,
        cwd=cwd,
        isolate=isolate,
        catch=catch,
        charset=charset,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Subprocess invocation
# ---------------------------------------------------------------------------


def run_command(
    argv: Sequence[str],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: bytes | str | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> RunResult:
    """Run an arbitrary argv and capture exit status plus stdout/stderr.

    *stdin* may be ``str`` (encoded as UTF-8) or ``bytes``. ``None`` is
    treated as empty stdin (EOF), not as inheriting the caller's stream.
    When *env* is ``None``, the current process environment is inherited.
    When *cwd* is ``None``, the current process cwd is used. Raises
    :class:`HarnessError` if the executable cannot be found or the child
    times out. Does not interpret the exit status.
    """
    if not argv:
        raise HarnessError("argv must be non-empty")
    workdir = str(Path(cwd).resolve()) if cwd is not None else str(repo_root())
    if stdin is None:
        input_bytes: bytes = b""
    elif isinstance(stdin, str):
        input_bytes = as_bytes(stdin)
    else:
        input_bytes = stdin

    child_env = dict(env) if env is not None else dict(os.environ)

    print(
        f"[harness] run cwd={workdir!r} argv={list(argv)!r}",
        flush=True,
    )
    try:
        completed = subprocess.run(
            list(argv),
            cwd=workdir,
            env=child_env,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HarnessError(f"executable not found: {argv[0]!r}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(
            f"command timed out after {timeout}s: {list(argv)!r}"
        ) from exc
    result = RunResult(
        returncode=completed.returncode,
        stdout=completed.stdout or b"",
        stderr=completed.stderr or b"",
        argv=tuple(str(a) for a in argv),
        cwd=workdir,
        environ=child_env,
    )
    print(
        f"[harness] exit={result.returncode} "
        f"stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}",
        flush=True,
    )
    if result.returncode != 0 and 0 < len(result.stderr) <= 2000:
        print(f"[harness] stderr={result.stderr_text!r}", flush=True)
    return result


def run_python(
    *,
    code: str | None = None,
    argv: Sequence[str] | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: bytes | str | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    isolate: bool = True,
    root: Path | None = None,
    include_product: bool = True,
) -> RunResult:
    """Run this process's interpreter as a child.

    *code* is passed as ``python -c <code>``. *argv* are extra arguments
    after ``-c`` (or, when *code* is omitted, the arguments after the
    interpreter — for example a script path). At least one of *code* or
    *argv* must be supplied.

    When *include_product* is false, the product tree is removed from
    the child's ``PYTHONPATH`` and a preamble drops that tree from
    ``sys.path`` and blocks the package name before *code* runs. Combined
    with an isolated cwd that is not the product tree, this is the
    library-substrate negative control: the package is not importable.
    The preamble is applied only when *code* is supplied.

    When *isolate* is true (the default) and *cwd* / *env* are omitted,
    the child runs in a fresh :func:`workspace`. Does not raise on a
    non-zero child exit.
    """
    if code is None and not argv:
        raise HarnessError("run_python requires code= or a non-empty argv")

    python = _python()
    repo = (root if root is not None else repo_root()).resolve()

    child_code = code
    if child_code is not None and not include_product:
        child_code = _product_scrub_preamble(root=repo) + child_code

    child_argv: list[str] = [python]
    if child_code is not None:
        child_argv.extend(["-c", child_code])
    if argv:
        child_argv.extend(str(a) for a in argv)

    if cwd is not None or env is not None or not isolate:
        child_env = dict(env) if env is not None else None
        if child_env is not None and not include_product:
            child_env = _environ_without_product(child_env, root=repo)
        return run_command(
            child_argv, cwd=cwd, env=child_env, stdin=stdin, timeout=timeout
        )

    with workspace(root=repo, include_product=include_product) as ws:
        return run_command(
            child_argv,
            cwd=ws.path,
            env=ws.env,
            stdin=stdin,
            timeout=timeout,
        )


def run_script(
    source: str,
    *,
    relpath: str = "caller.py",
    stdin: bytes | str | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    env: Mapping[str, str | None] | None = None,
    cwd: str | Path | None = None,
    isolate: bool = True,
    root: Path | None = None,
    include_product: bool = True,
) -> RunResult:
    """Write *source* to a ``.py`` file and run it as this interpreter's program.

    The child is ordinary script execution: ``__main__.__file__`` is set,
    the session is not interactive, and no test-runner tracer is
    attached.

    When *isolate* is true the script is written inside a fresh
    :func:`workspace`. With ``isolate=False``, *cwd* is required so the
    script is not written into the product tree.
    """
    repo = (root if root is not None else repo_root()).resolve()

    if isolate:
        with workspace(updates=env, root=repo, include_product=include_product) as ws:
            script = ws.write(relpath, source)
            work = Path(cwd).resolve() if cwd is not None else ws.path
            merged = ws.env
            if not include_product:
                merged = _environ_without_product(merged, root=repo)
            return run_python(
                argv=[str(script)],
                cwd=work,
                env=merged,
                stdin=stdin,
                timeout=timeout,
                isolate=False,
                root=repo,
                include_product=include_product,
            )

    if cwd is None:
        raise HarnessError(
            "run_script with isolate=False requires cwd so the script "
            "is not written into the product tree"
        )
    work = Path(cwd).resolve()
    if not work.is_dir():
        raise HarnessError(f"run_script cwd is not a directory: {work}")
    script = write_file(work / relpath, source)
    if env is not None:
        child_env = {k: v for k, v in env.items() if v is not None}
    else:
        child_env = dict(os.environ)
    if not include_product:
        child_env = _environ_without_product(child_env, root=repo)
    return run_python(
        argv=[str(script)],
        cwd=work,
        env=child_env,
        stdin=stdin,
        timeout=timeout,
        isolate=False,
        root=repo,
        include_product=include_product,
    )


__all__ = (
    "DEFAULT_CHARSET",
    "DEFAULT_TIMEOUT",
    "CallResult",
    "FrozenClock",
    "HarnessError",
    "RunResult",
    "Workspace",
    "as_bytes",
    "as_text",
    "attr",
    "call",
    "call_method",
    "exception_text",
    "exception_type_name",
    "frozen_clock",
    "in_directory",
    "isolated_environ",
    "isolated_filesystem",
    "local_datetime",
    "path_is_file",
    "process_timezone",
    "product_import_root",
    "product_package_dir",
    "product_package_name",
    "product_src_dir",
    "read_bytes",
    "read_file",
    "repo_root",
    "require_bool",
    "require_callable_attr",
    "require_exception",
    "require_int",
    "require_text",
    "require_value",
    "run_command",
    "run_python",
    "run_script",
    "utc_datetime",
    "workspace",
    "write_file",
)
