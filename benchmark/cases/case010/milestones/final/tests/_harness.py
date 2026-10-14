# feature: F00
"""Shared machinery for driving the product through its public surface.

Suites import from this module (``from _harness import ...``). Importing it
performs no I/O, starts no processes, and opens no sockets. Stream capture,
environment replacement, and cwd changes happen only when a caller invokes
a function or enters a context manager below.

The product is an importable Python library with a flat package layout at
the repository root, plus a command-line group whose tokenize command
applies the recommended word tokenizer to each line of a text stream.
This module is the one canonical way to reach those surfaces. It does
not import the product and does not know what any feature expects.

Surfaces
--------
* Library call — :func:`call` runs a caller-supplied public callable
  (imported by the suite from the package root or from the submodule
  the PRD names) with caller-controlled arguments, stdin, environment,
  and working directory. A product exception is a classified outcome on
  :class:`CallResult`, not a harness failure.
* Command-line group — :func:`invoke` drives a public ``main`` entry
  (the documented Click-style program entry) with argument tokens and
  stdin, the same way a console script would. A non-zero exit is a
  classified outcome on :class:`InvokeResult`.
* Child interpreter — :func:`run_python` / :func:`run_command` for
  observations that need a separate process: the library-substrate
  negative control (package removed from the import path), or a
  resource-search environment that must be bound before import.

Each isolated call starts from a whitelist of substrate environment
keys. The product's packaged-resource search variable is pointed at
the workspace so a host-installed model cannot satisfy a "resource
absent" arm, and cannot hide a "resource present" arm that never
provisioned one. :func:`replace_list` is the in-process counterpart
for a mutable search-path list that was already populated at import.

A failure this module cannot classify raises :class:`HarnessError`.
"""

from __future__ import annotations

import inspect
import io
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, Callable, Iterator, Mapping, Sequence
from warnings import WarningMessage, catch_warnings, simplefilter

# ---------------------------------------------------------------------------
# Public defaults
# ---------------------------------------------------------------------------

DEFAULT_CHARSET = "utf-8"
DEFAULT_TIMEOUT = 30.0
DEFAULT_PROG_NAME = "cli"

# Isolated child / in-process environments start from this Unicode locale.
_DEFAULT_LOCALE = "C.UTF-8"

# Product resource-search environment variable. Isolated environments never
# set it; any inherited value is dropped (see _ISOLATE_UNSET). Tests choose
# resource locations through the public search list instead.
RESOURCE_PATH_ENV = "LINGORA_DATA"

# Substrate keys copied from the caller when building an isolated env.
# Everything else is dropped so a resource path or incidental parent
# variable cannot fill a condition the suite did not name.
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
    RESOURCE_PATH_ENV,
)


# ---------------------------------------------------------------------------
# Errors / result types
# ---------------------------------------------------------------------------


class HarnessError(RuntimeError):
    """Raised when an observation cannot be classified.

    Used for a missing substrate, a path that escapes its workspace, a
    command object without a public ``main`` entry, a timeout, and I/O
    failures that are not a documented product outcome. Never used to
    mean "the product returned a non-zero exit or raised the exception
    the PRD describes".
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


@dataclass(frozen=True)
class CallResult:
    """Outcome of one in-process library call.

    Attributes:
        value: Whatever the callable returned. ``None`` when an
            exception was captured — never a stand-in for "the call
            could not be performed".
        exception: The exception that ended the call, if any. ``None``
            when the callable returned. ``SystemExit`` is recorded here
            the same way as any other product exception.
        exc_info: ``sys.exc_info()`` triple matching ``exception``, or
            ``None``.
        stdout: Raw standard output bytes captured for the duration.
        stderr: Raw standard error bytes captured for the duration.
        cwd: Working directory used for the call, as a string.
        warnings: Warning records captured for the duration of the call.
            Empty when none were emitted — never ``None``.
    """

    value: Any
    exception: BaseException | None
    exc_info: tuple[type[BaseException], BaseException, TracebackType] | None
    stdout: bytes
    stderr: bytes
    cwd: str
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
class InvokeResult:
    """Outcome of one in-process command-line invocation.

    Attributes:
        exit_code: Process-style status. In standalone mode this is the
            ``SystemExit`` code (``None`` treated as 0). In
            non-standalone mode this is 0 when ``main`` returned, or 1
            when an exception was captured; the callback's return value
            is in ``return_value`` and is not reinterpreted as a status.
        stdout: Raw standard output bytes.
        stderr: Raw standard error bytes.
        return_value: Whatever ``main`` returned. ``None`` in standalone
            mode after a ``SystemExit``.
        exception: The exception that ended the invocation, if any
            (including ``SystemExit`` when the status is non-zero).
        exc_info: ``sys.exc_info()`` triple matching ``exception``, or
            ``None``.
        args: Argument tokens passed to ``main``.
        cwd: Working directory used for the call, as a string.
        warnings: Warning records captured for the duration of the call.
            Empty when none were emitted — never ``None``.
    """

    exit_code: int
    stdout: bytes
    stderr: bytes
    return_value: Any
    exception: BaseException | None
    exc_info: tuple[type[BaseException], BaseException, TracebackType] | None
    args: tuple[str, ...]
    cwd: str
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
    """

    returncode: int
    stdout: bytes
    stderr: bytes
    argv: tuple[str, ...]
    cwd: str

    @property
    def stdout_text(self) -> str:
        """Stdout decoded as UTF-8. Raises :class:`HarnessError` if not."""
        return _decode_utf8(self.stdout, stream="stdout")

    @property
    def stderr_text(self) -> str:
        """Stderr decoded as UTF-8. Raises :class:`HarnessError` if not."""
        return _decode_utf8(self.stderr, stream="stderr")


@dataclass
class Workspace:
    """Ephemeral work directory plus the isolated environment bound to it.

    ``path`` is the working directory for invokes. ``home`` is used as
    ``HOME`` so ``~`` expansion cannot see the caller's home. ``data``
    is the packaged-resource search directory (the product's resource
    path environment variable points here). All three trees are removed
    when the allocating context exits.
    """

    path: Path
    home: Path
    data: Path
    env: dict[str, str]

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
        workspace.
        """
        dest = self.resolve(relpath)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            dest.write_bytes(content)
        else:
            dest.write_text(content, encoding=encoding)
        return dest

    def read(self, relpath: str | Path, *, encoding: str = DEFAULT_CHARSET) -> str:
        """Read a UTF-8 text file under this workspace.

        Raises:
            HarnessError: if *relpath* escapes the workspace, or if the
                path exists but is not a regular file.
            FileNotFoundError: if the file does not exist — never returns
                an empty string or ``None`` to mean "missing".
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

    def invoke(
        self,
        cli: Any,
        args: Sequence[str] | str | None = None,
        *,
        stdin: str | bytes | None = None,
        env: Mapping[str, str | None] | None = None,
        standalone_mode: bool = True,
        catch_exceptions: bool | None = None,
        charset: str = DEFAULT_CHARSET,
        prog_name: str | None = None,
        **extra: Any,
    ) -> InvokeResult:
        """Invoke *cli* with this workspace as cwd and environment."""
        merged = _apply_updates(self.env, env)
        return invoke(
            cli,
            args,
            stdin=stdin,
            env=merged,
            cwd=self.path,
            isolate=False,
            standalone_mode=standalone_mode,
            catch_exceptions=catch_exceptions,
            charset=charset,
            prog_name=prog_name,
            **extra,
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
            merged = _environ_without_product(merged)
        return run_python(
            code=code,
            argv=argv,
            cwd=cwd if cwd is not None else self.path,
            env=merged,
            stdin=stdin,
            timeout=timeout,
            isolate=False,
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
        except Exception:
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


def _normalize_args(args: Sequence[str] | str | None) -> tuple[str, ...]:
    if args is None:
        return ()
    if isinstance(args, str):
        return tuple(shlex.split(args))
    return tuple(str(a) for a in args)


def _read_regular_file(src: Path) -> None:
    """Raise a classified error when *src* is missing or not a regular file."""
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


def _exit_code_from_system_exit(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    sys.stdout.write(str(code))
    sys.stdout.write("\n")
    return 1


def _require_callable(fn: Any, *, label: str) -> Callable[..., Any]:
    if not callable(fn):
        raise HarnessError(f"{label} is not callable; got {type(fn)!r}")
    return fn


def _require_main(cli: Any) -> Callable[..., Any]:
    main = getattr(cli, "main", None)
    if not callable(main):
        raise HarnessError(
            "invoke target has no callable public main entry; "
            f"got {type(cli)!r}"
        )
    return main


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


# ---------------------------------------------------------------------------
# Paths / discovery
# ---------------------------------------------------------------------------


def repo_root() -> Path:
    """Return the built repository root.

    Tests run with the repository root as the pytest process cwd. Returns
    ``Path.cwd()`` resolved; does not search the filesystem.
    """
    return Path.cwd().resolve()


def product_package_dir(*, root: Path | None = None) -> Path:
    """Return the single top-level package directory of the built tree.

    The product uses a flat package layout: one importable package
    directory next to the packaging files. Discovery is filesystem-only
    and does not import the product.

    Raises:
        HarnessError: when zero or several candidate package directories
            exist. That is a substrate gap, not a product-behavior
            judgment.
    """
    base = root if root is not None else repo_root()
    skip = {"tests", "test", "docs", "doc", "examples", "build", "dist"}
    candidates: list[Path] = []
    try:
        children = list(base.iterdir())
    except OSError as exc:
        raise HarnessError(f"cannot list repository root {base}: {exc}") from exc
    for child in children:
        if not child.is_dir() or child.name.startswith(".") or child.name in skip:
            continue
        if child.name.startswith("_"):
            continue
        marker = child / "__init__.py"
        try:
            if marker.is_file():
                candidates.append(child)
        except OSError as exc:
            raise HarnessError(f"cannot stat {marker}: {exc}") from exc
    if len(candidates) != 1:
        names = [c.name for c in candidates]
        raise HarnessError(
            "expected exactly one top-level package directory under "
            f"{base}; found {names!r}"
        )
    return candidates[0].resolve()


def _pythonpath_parts(env: Mapping[str, str]) -> list[str]:
    raw = env.get("PYTHONPATH", "")
    return [part for part in raw.split(os.pathsep) if part]


def _environ_with_product(env: Mapping[str, str], *, root: Path) -> dict[str, str]:
    merged = dict(env)
    root_s = str(root.resolve())
    parts = [root_s]
    parts.extend(part for part in _pythonpath_parts(merged) if part != root_s)
    merged["PYTHONPATH"] = os.pathsep.join(parts)
    return merged


def _environ_without_product(env: Mapping[str, str], *, root: Path | None = None) -> dict[str, str]:
    merged = dict(env)
    base = (root if root is not None else repo_root()).resolve()
    try:
        package = product_package_dir(root=base)
    except HarnessError:
        package = None
    blocked = {base}
    if package is not None:
        blocked.add(package)
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
    """Python source that drops the product tree from ``sys.path``.

    Used only in a child interpreter so the library-substrate negative
    control does not accidentally import through cwd or a leftover
    ``PYTHONPATH`` entry. Does not run at harness import time.
    """
    base = (root if root is not None else repo_root()).resolve()
    package = product_package_dir(root=base)
    return (
        "import sys\n"
        "from pathlib import Path\n"
        f"_ROOT = Path({str(base)!r}).resolve()\n"
        f"_PKG = Path({str(package)!r}).resolve()\n"
        "def _keep(entry):\n"
        "    try:\n"
        "        p = Path(entry).resolve()\n"
        "    except OSError:\n"
        "        return True\n"
        "    return p not in {_ROOT, _PKG}\n"
        "sys.path[:] = [e for e in sys.path if _keep(e)]\n"
    )


# ---------------------------------------------------------------------------
# Environment / workspace isolation
# ---------------------------------------------------------------------------


def isolated_environ(
    home: Path | str,
    data: Path | str,
    *,
    updates: Mapping[str, str | None] | None = None,
    base: Mapping[str, str] | None = None,
    root: Path | None = None,
    include_product: bool = True,
) -> dict[str, str]:
    """Build an environment that does not inherit the caller's extras.

    Copies a whitelist of substrate keys from *base* (or ``os.environ``),
    points ``HOME`` and the XDG dirs at *home*, leaves the product's
    resource-search variable unset, creates *data*, prepends or strips the repository
    root on ``PYTHONPATH`` according to *include_product*, unsets
    pager/editor/proxy side-channels, sets a Unicode locale, and applies
    *updates* last (``None`` unsets). Does not mutate ``os.environ``.

    Returns a new ``dict``.
    """
    home_path = Path(home).resolve()
    data_path = Path(data).resolve()
    cfg_dir = home_path / ".config"
    cache_dir = home_path / ".cache"
    data_xdg = home_path / ".local" / "share"
    state_dir = home_path / ".local" / "state"
    for directory in (home_path, data_path, cfg_dir, cache_dir, data_xdg, state_dir):
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
    env["XDG_DATA_HOME"] = str(data_xdg)
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
def replace_list(target: list[Any], items: Sequence[Any]) -> Iterator[list[Any]]:
    """Temporarily replace the contents of a mutable list.

    Use this on a product search-path list that was populated at import
    (the packaged-resource finder is the usual case) so an in-process
    call cannot see host-installed data. Restores the previous contents
    even if the block raises.

    Raises:
        HarnessError: if *target* is not a list. A tuple or other
            sequence cannot be rewritten in place, and returning a new
            list would silently leave the product looking at the old one.
    """
    if not isinstance(target, list):
        raise HarnessError(
            f"replace_list requires a list that can be rewritten in place; "
            f"got {type(target)!r}"
        )
    saved = list(target)
    target.clear()
    target.extend(items)
    try:
        yield target
    finally:
        target.clear()
        target.extend(saved)


@contextmanager
def workspace(
    *,
    updates: Mapping[str, str | None] | None = None,
    prefix: str = "harness-ws-",
    root: Path | None = None,
    include_product: bool = True,
) -> Iterator[Workspace]:
    """Allocate an ephemeral work directory and isolated HOME; clean up.

    Yields a :class:`Workspace`. All three directory trees are removed
    when the context exits, including on exception. The product tree is
    never used as the default cwd.
    """
    work = Path(tempfile.mkdtemp(prefix=prefix))
    home = Path(tempfile.mkdtemp(prefix="harness-home-"))
    data = Path(tempfile.mkdtemp(prefix="harness-data-"))
    try:
        env = isolated_environ(
            home,
            data,
            updates=updates,
            root=root,
            include_product=include_product,
        )
        yield Workspace(path=work, home=home, data=data, env=env)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(data, ignore_errors=True)


def write_file(
    path: str | Path,
    content: str | bytes,
    *,
    encoding: str = DEFAULT_CHARSET,
) -> Path:
    """Write *content* to *path*, creating parent directories.

    Returns the resolved path. Raises ``OSError`` on I/O failure.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        dest.write_bytes(content)
    else:
        dest.write_text(content, encoding=encoding)
    return dest.resolve()


def read_file(path: str | Path, *, encoding: str = DEFAULT_CHARSET) -> str:
    """Read *path* as text.

    Raises ``FileNotFoundError`` if the file does not exist — never
    returns an empty string or ``None`` to mean "missing". Raises
    :class:`HarnessError` if the path exists but is not a regular file,
    or on an ``OSError`` other than classified absence.
    """
    src = Path(path)
    _read_regular_file(src)
    try:
        return src.read_text(encoding=encoding)
    except FileNotFoundError:
        raise
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
        return src.is_file()
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
) -> tuple[Any, BaseException | None, tuple | None, bytes, bytes, tuple[WarningMessage, ...]]:
    if stdin is None:
        input_bytes = b""
    elif isinstance(stdin, str):
        input_bytes = stdin.encode(charset)
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
                    try:
                        sys.stdout.flush()
                    except Exception:
                        pass
                    try:
                        sys.stderr.flush()
                    except Exception:
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

    This is the canonical in-process path for a function or bound method
    the suite imported from the public surface. Extra positional and
    keyword arguments are forwarded to *fn* unchanged.

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

    Changing the process environment after the product has already been
    imported does not rewrite a search-path list populated at import.
    Use :func:`replace_list` on that list, or :func:`run_python` so the
    child binds the environment before import.
    """
    target = _require_callable(fn, label="call target")

    def _run(child_cwd: Path, child_env: Mapping[str, str]) -> CallResult:
        print(
            f"[harness] call fn={getattr(target, '__qualname__', type(target).__name__)!r} "
            f"cwd={str(child_cwd)!r}",
            flush=True,
        )
        value, exception, exc_info, stdout, stderr, warns = _run_captured(
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
            warnings=warns,
        )
        print(
            f"[harness] call_done exception="
            f"{type(result.exception).__name__ if result.exception else None} "
            f"stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}",
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


# ---------------------------------------------------------------------------
# In-process command-line invocation
# ---------------------------------------------------------------------------


def invoke(
    cli: Any,
    args: Sequence[str] | str | None = None,
    *,
    stdin: str | bytes | None = None,
    env: Mapping[str, str | None] | None = None,
    cwd: str | Path | None = None,
    isolate: bool = True,
    standalone_mode: bool = True,
    catch_exceptions: bool | None = None,
    charset: str = DEFAULT_CHARSET,
    prog_name: str | None = None,
    **extra: Any,
) -> InvokeResult:
    """Invoke a command through its public ``main`` entry.

    This is the canonical in-process path for the command-line group:
    argument tokens, stdin, and environment are those of a program
    invocation. Extra keywords are forwarded to ``main``.

    When *isolate* is true (the default) the call runs in a fresh
    :func:`workspace`. *catch_exceptions* defaults to true in standalone
    mode (a crash becomes ``exit_code == 1``) and false otherwise.
    A ``SystemExit`` is always recorded as ``exit_code``, never raised
    out of this function.

    Returns an :class:`InvokeResult`. Does not raise on a non-zero
    product exit.
    """
    tokens = _normalize_args(args)
    main = _require_main(cli)
    if catch_exceptions is None:
        catch_exceptions = bool(standalone_mode)
    if prog_name is None:
        name = getattr(cli, "name", None)
        prog_name = name if isinstance(name, str) and name else DEFAULT_PROG_NAME

    def _body() -> Any:
        return main(
            args=list(tokens),
            prog_name=prog_name,
            standalone_mode=standalone_mode,
            **extra,
        )

    def _run(child_cwd: Path, child_env: Mapping[str, str]) -> InvokeResult:
        print(
            f"[harness] invoke prog={prog_name!r} args={list(tokens)!r} "
            f"standalone={standalone_mode} cwd={str(child_cwd)!r}",
            flush=True,
        )
        old_argv = sys.argv
        sys.argv = [prog_name, *tokens]
        try:
            value, exception, exc_info, stdout, stderr, warns = _run_captured(
                _body,
                stdin=stdin,
                env=child_env,
                cwd=child_cwd,
                charset=charset,
                catch=True,
            )
        finally:
            sys.argv = old_argv

        exit_code = 0
        return_value = value
        recorded_exc = exception
        recorded_info = exc_info
        if isinstance(exception, SystemExit):
            exit_code = _exit_code_from_system_exit(exception)
            if exit_code == 0:
                recorded_exc = None
                recorded_info = None
        elif exception is not None:
            if not catch_exceptions:
                raise exception
            exit_code = 1

        result = InvokeResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            return_value=return_value if recorded_exc is None else None,
            exception=recorded_exc,
            exc_info=recorded_info,
            args=tokens,
            cwd=str(child_cwd),
            warnings=warns,
        )
        print(
            f"[harness] exit={result.exit_code} "
            f"stdout_len={len(result.stdout)} stderr_len={len(result.stderr)} "
            f"exception={type(result.exception).__name__ if result.exception else None}",
            flush=True,
        )
        if result.exit_code != 0 and 0 < len(result.stderr) <= 2000:
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
        raise HarnessError(f"invoke cwd is not a directory: {work}")
    return _run(work, child_env)


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
        input_bytes = stdin.encode(DEFAULT_CHARSET)
    else:
        input_bytes = stdin

    print(
        f"[harness] run cwd={workdir!r} argv={list(argv)!r}",
        flush=True,
    )
    try:
        completed = subprocess.run(
            list(argv),
            cwd=workdir,
            env=dict(env) if env is not None else None,
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
    interpreter — for example ``['-m', 'pkg']``). At least one of *code*
    or *argv* must be supplied.

    When *include_product* is false, the repository root is removed from
    the child's ``PYTHONPATH`` and a preamble drops that tree from
    ``sys.path`` before *code* runs. Combined with an isolated cwd that
    is not the product tree, this is the library-substrate negative
    control: the package is not importable through the path. The
    preamble is applied only when *code* is supplied.

    When *isolate* is true (the default) and *cwd* / *env* are omitted,
    the child runs in a fresh :func:`workspace`. Does not raise on a
    non-zero child exit.
    """
    if code is None and not argv:
        raise HarnessError("run_python requires code= or a non-empty argv")

    python = sys.executable
    if not python:
        raise HarnessError("sys.executable is empty; cannot spawn an interpreter")

    child_code = code
    if child_code is not None and not include_product:
        child_code = _product_scrub_preamble(root=root) + child_code

    child_argv: list[str] = [python]
    if child_code is not None:
        child_argv.extend(["-c", child_code])
    if argv:
        child_argv.extend(str(a) for a in argv)

    if cwd is not None or env is not None or not isolate:
        child_env = dict(env) if env is not None else None
        if child_env is not None and not include_product:
            child_env = _environ_without_product(child_env, root=root)
        return run_command(
            child_argv, cwd=cwd, env=child_env, stdin=stdin, timeout=timeout
        )

    with workspace(root=root, include_product=include_product) as ws:
        return run_command(
            child_argv,
            cwd=ws.path,
            env=ws.env,
            stdin=stdin,
            timeout=timeout,
        )


__all__ = (
    "DEFAULT_CHARSET",
    "DEFAULT_PROG_NAME",
    "DEFAULT_TIMEOUT",
    "RESOURCE_PATH_ENV",
    "CallResult",
    "HarnessError",
    "InvokeResult",
    "RunResult",
    "Workspace",
    "call",
    "in_directory",
    "invoke",
    "isolated_environ",
    "isolated_filesystem",
    "path_is_file",
    "product_package_dir",
    "read_bytes",
    "read_file",
    "replace_list",
    "repo_root",
    "run_command",
    "run_python",
    "workspace",
    "write_file",
)
