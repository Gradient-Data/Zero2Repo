# feature: F00
"""Shared machinery for driving the product through its public Zig module.

Suites import from this module (``from _helpers import ...``). Importing it
performs no I/O, starts no processes, and opens no sockets. Filesystem
writes, environment replacement, cwd changes, and child processes happen
only when a caller invokes a function or enters a context manager below.

The product is a Zig library. There is no command-line program and no
network service. Integrators reach it by compiling a Zig program that
imports the library module and then running that program. This module is
the one canonical way to do that. It does not import the product and
does not know what any feature expects.

Surfaces
--------
* Compiler — :func:`run_zig` / :func:`run_zig_source` / :func:`compile_zig`
  invoke the Zig 0.16 toolchain. The import name and the module root
  source file are parameters (see :func:`product_module_source`). A
  compile-time or run-time non-zero exit is a classified outcome on
  :class:`RunResult`, not a harness failure.
* Child process — :func:`run_command` for an already-built binary, or
  for any other argv the suite supplies.
* Files / environment — :class:`Workspace` for ephemeral cwd, HOME, and
  probe sources; :func:`write_file` / :func:`read_file` / :func:`read_bytes`
  for buffers a probe emits or consumes.

Each isolated call starts from a whitelist of substrate environment
keys. Names that are not on that list are dropped so an incidental
parent variable cannot fill a condition the suite did not name.

A failure this module cannot classify raises :class:`HarnessError`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

# ---------------------------------------------------------------------------
# Public defaults
# ---------------------------------------------------------------------------

DEFAULT_CHARSET = "utf-8"
"""Text encoding for stdin strings and for decoding captured streams."""

DEFAULT_TIMEOUT = 120.0
"""Seconds to wait for a child (compile + run of a small Zig program)."""

DEFAULT_ZIG = "zig"
"""Zig 0.16 compiler looked up on ``PATH`` unless the caller passes a path."""

PRODUCT_MODULE_NAME = "klyvmap"
"""Import name of the product Zig module, as the PRD names the library."""

# Isolated child environments start from this Unicode locale.
_DEFAULT_LOCALE = "C.UTF-8"

# Substrate keys copied from the caller when building an isolated env.
# Everything else is dropped so an incidental parent variable cannot
# fill a condition the suite did not name.
_KEEP_ENV_KEYS = (
    "PATH",
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
    "ZIG_GLOBAL_CACHE_DIR",
    "ZIG_LOCAL_CACHE_DIR",
    "ZIG_LIB_DIR",
    "ZIG_TOOLCHAIN_PATH",
    "CC",
    "CXX",
    "AR",
    "LD_LIBRARY_PATH",
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

_ZIG_ACTIONS = frozenset({"run", "build-exe", "test"})


# ---------------------------------------------------------------------------
# Errors / result types
# ---------------------------------------------------------------------------


class HarnessError(RuntimeError):
    """Raised when an observation cannot be classified.

    Used for a missing toolchain, a path that escapes its workspace, a
    timeout, a stream that is not valid in the requested encoding, JSON
    that cannot be parsed, and I/O failures that are not a documented
    product outcome. Never used to mean "the compiler or the program
    exited non-zero".
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
    replaces unencodable characters with a sentinel.
    """
    if isinstance(content, bytes):
        return content
    try:
        return content.encode(encoding)
    except (LookupError, UnicodeEncodeError) as exc:
        raise HarnessError(f"cannot encode text as {encoding}: {exc}") from exc


@dataclass(frozen=True)
class RunResult:
    """Outcome of one subprocess invocation (compiler or compiled program).

    Attributes:
        returncode: Process exit status. The harness does not interpret it.
            ``0`` is success of that argv, not a product-behavior judgment.
        stdout: Raw standard output bytes.
        stderr: Raw standard error bytes.
        argv: Exact argument vector that was executed.
        cwd: Working directory used for the process, as a string.
        environ: Environment mapping passed to the child. Always a dict
            — never ``None``. This is the mapping the child started
            with, not a probe of the child's later state.
        phase: ``"compile"`` when the argv was the Zig compiler writing
            an executable; ``"run"`` when the argv was ``zig run``,
            ``zig test``, or a compiled binary. Compile failure is
            still a :class:`RunResult` with a non-zero ``returncode``.
        binary: Path the caller asked the compiler to emit, or ``None``
            when this invocation did not request an emit-bin. Presence
            of the path does not imply the file exists — check
            ``returncode`` first.
    """

    returncode: int
    stdout: bytes
    stderr: bytes
    argv: tuple[str, ...]
    cwd: str
    environ: dict[str, str]
    phase: str = "run"
    binary: Path | None = None

    @property
    def stdout_text(self) -> str:
        """Stdout decoded as UTF-8. Raises :class:`HarnessError` if not."""
        return _decode_utf8(self.stdout, stream="stdout")

    @property
    def stderr_text(self) -> str:
        """Stderr decoded as UTF-8. Raises :class:`HarnessError` if not."""
        return _decode_utf8(self.stderr, stream="stderr")

    def stdout_json(self) -> Any:
        """Parse stdout as one UTF-8 JSON value.

        Returns the decoded object, including JSON ``null`` (Python
        ``None``) when that is what was written. Raises
        :class:`HarnessError` if stdout is empty or is not valid JSON
        — never treats empty output as ``null``.
        """
        text = self.stdout_text
        if text.strip() == "":
            raise HarnessError("stdout is empty; not a JSON value")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise HarnessError(f"stdout is not valid JSON: {exc}") from exc


@dataclass
class Workspace:
    """Ephemeral work directory plus the isolated environment bound to it.

    ``path`` is the working directory for compiles and child processes.
    ``home`` is used as ``HOME`` so ``~`` expansion cannot see the
    caller's home. ``root`` is the built repository root used to locate
    the product module (captured when the workspace was allocated, not
    looked up from the then-current cwd). All workspace trees are
    removed when the allocating context exits.
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
        """Create a directory under this workspace (parents included).

        Returns the absolute path created. Raises :class:`HarnessError`
        if *relpath* escapes the workspace.
        """
        dest = self.resolve(relpath)
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def run_command(
        self,
        argv: Sequence[str],
        *,
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
    ) -> RunResult:
        """Run *argv* with this workspace as cwd and environment.

        Returns a :class:`RunResult`. Does not interpret the exit status.
        """
        merged = _apply_updates(self.env, env)
        return run_command(
            argv,
            cwd=cwd if cwd is not None else self.path,
            env=merged,
            stdin=stdin,
            timeout=timeout,
        )

    def compile_zig(
        self,
        source: str | Path,
        *,
        output: str | Path = "probe",
        deps: Mapping[str, str | Path] | None = None,
        include_product: bool = True,
        zig: str = DEFAULT_ZIG,
        optimize: str | None = None,
        extra: Sequence[str] = (),
        link_libc: bool = False,
        timeout: float | None = DEFAULT_TIMEOUT,
        env: Mapping[str, str | None] | None = None,
    ) -> RunResult:
        """Compile a Zig program under this workspace.

        *source* is a path relative to the workspace, or an absolute
        path. *output* is the emit-bin path, likewise. Returns a
        :class:`RunResult` with ``phase="compile"``. ``returncode == 0``
        means the binary was written; a non-zero compiler exit is a
        classified outcome, not a harness failure.
        """
        src = source if Path(source).is_absolute() else self.resolve(source)
        out = output if Path(output).is_absolute() else self.resolve(output)
        merged = _apply_updates(self.env, env)
        resolved = _resolve_deps(
            deps, include_product=include_product, root=self.root
        )
        return compile_zig(
            src,
            output=out,
            deps=resolved,
            zig=zig,
            optimize=optimize,
            extra=extra,
            link_libc=link_libc,
            cwd=self.path,
            env=merged,
            timeout=timeout,
            isolate=False,
        )

    def run_zig(
        self,
        source: str | Path,
        *,
        argv: Sequence[str] = (),
        stdin: bytes | str | None = None,
        deps: Mapping[str, str | Path] | None = None,
        include_product: bool = True,
        zig: str = DEFAULT_ZIG,
        optimize: str | None = None,
        extra: Sequence[str] = (),
        link_libc: bool = False,
        timeout: float | None = DEFAULT_TIMEOUT,
        env: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
        action: str = "run",
    ) -> RunResult:
        """``zig run`` (or ``zig test``) a source file with this workspace as cwd/env.

        Returns a :class:`RunResult`. Does not raise on a non-zero
        compiler or program exit.
        """
        src = source if Path(source).is_absolute() else self.resolve(source)
        merged = _apply_updates(self.env, env)
        resolved = _resolve_deps(
            deps, include_product=include_product, root=self.root
        )
        return run_zig(
            src,
            argv=argv,
            stdin=stdin,
            deps=resolved,
            zig=zig,
            optimize=optimize,
            extra=extra,
            link_libc=link_libc,
            cwd=cwd if cwd is not None else self.path,
            env=merged,
            timeout=timeout,
            isolate=False,
            action=action,
        )

    def run_zig_source(
        self,
        source: str,
        *,
        relpath: str = "probe.zig",
        argv: Sequence[str] = (),
        stdin: bytes | str | None = None,
        deps: Mapping[str, str | Path] | None = None,
        include_product: bool = True,
        zig: str = DEFAULT_ZIG,
        optimize: str | None = None,
        extra: Sequence[str] = (),
        link_libc: bool = False,
        timeout: float | None = DEFAULT_TIMEOUT,
        env: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
        action: str = "run",
    ) -> RunResult:
        """Write *source* under this workspace and ``zig run`` (or ``zig test``) it.

        Returns a :class:`RunResult`. Does not raise on a non-zero
        compiler or program exit.
        """
        path = self.write(relpath, source)
        return self.run_zig(
            path,
            argv=argv,
            stdin=stdin,
            deps=deps,
            include_product=include_product,
            zig=zig,
            optimize=optimize,
            extra=extra,
            link_libc=link_libc,
            timeout=timeout,
            env=env,
            cwd=cwd,
            action=action,
        )


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


def _resolve_deps(
    deps: Mapping[str, str | Path] | None,
    *,
    include_product: bool,
    root: Path | None,
) -> dict[str, Path]:
    if deps is not None:
        return {str(name): Path(path) for name, path in deps.items()}
    if include_product:
        return default_deps(root=root)
    return {}


# ---------------------------------------------------------------------------
# Paths / discovery
# ---------------------------------------------------------------------------


def repo_root() -> Path:
    """Return the built repository root.

    Tests run with the repository root as the pytest process cwd. Returns
    ``Path.cwd()`` resolved; does not search the filesystem.
    """
    return Path.cwd().resolve()


def product_module_source(
    *,
    name: str = PRODUCT_MODULE_NAME,
    root: Path | None = None,
    relpath: str | Path | None = None,
) -> Path:
    """Return the product Zig module's root source file.

    The compiler flag this path is for is ``-M<name>=<path>``. Default
    *relpath* is ``src/<name>.zig`` under *root* (the repository root
    when omitted). Raises :class:`HarnessError` when that path is not a
    regular file — a substrate gap, not a product-behavior judgment.
    """
    base = (root if root is not None else repo_root()).resolve()
    relative = Path(relpath) if relpath is not None else Path("src") / f"{name}.zig"
    src = (base / relative).resolve() if not relative.is_absolute() else relative.resolve()
    try:
        if not src.is_file():
            raise HarnessError(
                f"product Zig module root not found at {src}; "
                "pass relpath= or deps= to name a different root source"
            )
    except HarnessError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot stat product module {src}: {exc}") from exc
    return src


def default_deps(
    *,
    name: str = PRODUCT_MODULE_NAME,
    root: Path | None = None,
    relpath: str | Path | None = None,
) -> dict[str, Path]:
    """Return ``{name: product_module_source(...)}`` for compiler ``--dep``.

    Raises :class:`HarnessError` when the module root source is missing.
    """
    return {name: product_module_source(name=name, root=root, relpath=relpath)}


def zig_executable(*, zig: str = DEFAULT_ZIG) -> str:
    """Return the Zig compiler path that child processes will exec.

    *zig* is used as-is when it contains a path separator. Otherwise it
    is resolved on ``PATH``. Raises :class:`HarnessError` if no
    executable is found — a missing toolchain, not a product outcome.
    """
    if os.path.sep in zig or (os.path.altsep and os.path.altsep in zig):
        path = Path(zig)
        if not path.is_file():
            raise HarnessError(f"zig executable not found: {zig!r}")
        return str(path.resolve())
    found = shutil.which(zig)
    if not found:
        raise HarnessError(
            f"zig executable {zig!r} is not on PATH; "
            "the runner must provide Zig 0.16"
        )
    return found


def zig_dep_flags(deps: Mapping[str, str | Path]) -> list[str]:
    """Return ``--dep name -Mname=abs-path`` flags for *deps*.

    Each value is the module root source file. Paths are resolved to
    absolute so the compiler cwd need not be the repository root.
    An empty mapping returns an empty list (no product module).
    """
    flags: list[str] = []
    for name, path in deps.items():
        resolved = Path(path).resolve()
        flags.extend(["--dep", str(name), f"-M{name}={resolved}"])
    return flags


def zig_argv(
    action: str,
    source: str | Path,
    *,
    zig: str = DEFAULT_ZIG,
    deps: Mapping[str, str | Path] | None = None,
    optimize: str | None = None,
    emit_bin: str | Path | None = None,
    name: str | None = None,
    link_libc: bool = False,
    extra: Sequence[str] = (),
    program_args: Sequence[str] = (),
) -> list[str]:
    """Build a Zig compiler argv. Does not run it.

    *action* is ``run``, ``build-exe``, or ``test``. *deps* maps import
    names to module root source files. *optimize* is a mode name
    (``Debug``, ``ReleaseSafe``, ``ReleaseFast``, ``ReleaseSmall``);
    omitted means the compiler default. *emit_bin* is only used with
    ``build-exe``. *program_args* are placed after ``--`` for ``run``
    and ``test`` so they reach the program, not the compiler.

    Raises :class:`HarnessError` if *action* is not one of the three
    compiler actions above.
    """
    if action not in _ZIG_ACTIONS:
        raise HarnessError(
            f"zig action must be one of {sorted(_ZIG_ACTIONS)}; got {action!r}"
        )
    cmd: list[str] = [zig, action]
    if optimize is not None:
        cmd.extend(["-O", str(optimize)])
    cmd.append(str(source))
    if action == "build-exe":
        if emit_bin is None:
            raise HarnessError("compile_zig / zig_argv build-exe requires emit_bin=")
        cmd.append(f"-femit-bin={emit_bin}")
        bin_name = name if name is not None else Path(str(emit_bin)).name
        if bin_name:
            cmd.extend(["--name", bin_name])
    if link_libc:
        cmd.append("-lc")
    if deps:
        cmd.extend(zig_dep_flags(deps))
    if extra:
        cmd.extend(str(item) for item in extra)
    if program_args:
        if action == "build-exe":
            raise HarnessError(
                "program_args are not passed to build-exe; run the binary instead"
            )
        cmd.append("--")
        cmd.extend(str(item) for item in program_args)
    return cmd


# ---------------------------------------------------------------------------
# Environment / workspace isolation
# ---------------------------------------------------------------------------


def isolated_environ(
    home: Path | str,
    *,
    updates: Mapping[str, str | None] | None = None,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build an environment that does not inherit the caller's extras.

    Copies a whitelist of substrate keys from *base* (or ``os.environ``),
    points ``HOME`` and the XDG dirs at *home*, unsets pager/editor/proxy
    side-channels, sets a Unicode locale, and applies *updates* last
    (``None`` unsets). Does not mutate ``os.environ``. Zig cache
    directories present on the parent are kept so compiles reuse the
    toolchain cache.

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
    or delete *path*. Raises :class:`HarnessError` if *path* is not a
    directory.
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
        env = isolated_environ(home, updates=updates)
        yield Workspace(path=work, home=home, env=env, root=repo)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


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
        return src.is_file()
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc


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
    phase: str = "run",
    binary: Path | None = None,
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
        phase=phase,
        binary=binary,
    )
    print(
        f"[harness] phase={result.phase} exit={result.returncode} "
        f"stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}",
        flush=True,
    )
    if result.returncode != 0 and 0 < len(result.stderr) <= 2000:
        print(f"[harness] stderr={result.stderr_text!r}", flush=True)
    return result


def compile_zig(
    source: str | Path,
    *,
    output: str | Path,
    deps: Mapping[str, str | Path] | None = None,
    include_product: bool = True,
    zig: str = DEFAULT_ZIG,
    optimize: str | None = None,
    extra: Sequence[str] = (),
    link_libc: bool = False,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    isolate: bool = True,
    root: Path | None = None,
) -> RunResult:
    """Compile *source* to *output* with ``zig build-exe``.

    *deps* maps import names to module root source files. When *deps* is
    omitted and *include_product* is true, the product Zig module is
    attached. ``include_product=False`` with omitted *deps* attaches
    nothing (the library-substrate negative control).

    Returns a :class:`RunResult` with ``phase="compile"`` and ``binary``
    set to the requested *output* path. ``returncode == 0`` means that
    file was written; a non-zero compiler exit is a classified outcome.
    Does not run the binary.

    When *isolate* is true (the default) and *cwd* / *env* are omitted,
    the compiler runs in a fresh :func:`workspace`.
    """
    src = Path(source).resolve()
    out = Path(output)
    repo = (root if root is not None else repo_root()).resolve()
    resolved = _resolve_deps(deps, include_product=include_product, root=repo)

    def _run(work: str | Path | None, child_env: Mapping[str, str] | None) -> RunResult:
        workdir = Path(work).resolve() if work is not None else Path.cwd()
        dest = out if out.is_absolute() else workdir / out
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = zig_argv(
            "build-exe",
            src,
            zig=zig,
            deps=resolved,
            optimize=optimize,
            emit_bin=dest,
            extra=extra,
            link_libc=link_libc,
        )
        return run_command(
            cmd,
            cwd=work,
            env=child_env,
            timeout=timeout,
            phase="compile",
            binary=dest.resolve(),
        )

    if cwd is not None or env is not None or not isolate:
        return _run(cwd, dict(env) if env is not None else None)

    with workspace(root=repo) as ws:
        return _run(ws.path, ws.env)


def run_zig(
    source: str | Path,
    *,
    argv: Sequence[str] = (),
    stdin: bytes | str | None = None,
    deps: Mapping[str, str | Path] | None = None,
    include_product: bool = True,
    zig: str = DEFAULT_ZIG,
    optimize: str | None = None,
    extra: Sequence[str] = (),
    link_libc: bool = False,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    isolate: bool = True,
    root: Path | None = None,
    action: str = "run",
) -> RunResult:
    """Compile and run a Zig source file in one child (``zig run``).

    *source* is an existing ``.zig`` file. *argv* are arguments to the
    program (placed after ``--``). *deps* / *include_product* follow
    :func:`compile_zig`. *action* may be ``run`` or ``test``.

    Returns a :class:`RunResult` with ``phase="run"``. Does not raise on
    a non-zero compiler or program exit. Raises :class:`HarnessError` if
    the compiler is missing or the child times out.

    When *isolate* is true (the default) and *cwd* / *env* are omitted,
    the child runs in a fresh :func:`workspace`. The module root paths
    in *deps* are absolute, so the isolated cwd is not the product tree.
    """
    if action not in {"run", "test"}:
        raise HarnessError(f"run_zig action must be 'run' or 'test'; got {action!r}")
    src = Path(source).resolve()
    repo = (root if root is not None else repo_root()).resolve()
    resolved = _resolve_deps(deps, include_product=include_product, root=repo)
    cmd = zig_argv(
        action,
        src,
        zig=zig,
        deps=resolved,
        optimize=optimize,
        extra=extra,
        link_libc=link_libc,
        program_args=argv,
    )

    def _run(work: str | Path | None, child_env: Mapping[str, str] | None) -> RunResult:
        return run_command(
            cmd,
            cwd=work,
            env=child_env,
            stdin=stdin,
            timeout=timeout,
            phase="run",
        )

    if cwd is not None or env is not None or not isolate:
        return _run(cwd, dict(env) if env is not None else None)

    with workspace(root=repo) as ws:
        return _run(ws.path, ws.env)


def run_zig_source(
    source: str,
    *,
    relpath: str = "probe.zig",
    argv: Sequence[str] = (),
    stdin: bytes | str | None = None,
    deps: Mapping[str, str | Path] | None = None,
    include_product: bool = True,
    zig: str = DEFAULT_ZIG,
    optimize: str | None = None,
    extra: Sequence[str] = (),
    link_libc: bool = False,
    timeout: float | None = DEFAULT_TIMEOUT,
    env: Mapping[str, str | None] | None = None,
    cwd: str | Path | None = None,
    isolate: bool = True,
    root: Path | None = None,
    action: str = "run",
) -> RunResult:
    """Write *source* to a ``.zig`` file and ``zig run`` (or ``zig test``) it.

    The child is ordinary program execution: no test-runner tracer is
    attached by this harness (``action="test"`` uses Zig's own test
    runner). Returns a :class:`RunResult`. Does not raise on a non-zero
    compiler or program exit.

    When *isolate* is true the file is written inside a fresh
    :func:`workspace`. With ``isolate=False``, *cwd* is required so the
    file is not written into the product tree.
    """
    repo = (root if root is not None else repo_root()).resolve()

    if isolate:
        with workspace(updates=env, root=repo) as ws:
            return ws.run_zig_source(
                source,
                relpath=relpath,
                argv=argv,
                stdin=stdin,
                deps=deps,
                include_product=include_product,
                zig=zig,
                optimize=optimize,
                extra=extra,
                link_libc=link_libc,
                timeout=timeout,
                cwd=cwd,
                action=action,
            )

    if cwd is None:
        raise HarnessError(
            "run_zig_source with isolate=False requires cwd so the source "
            "is not written into the product tree"
        )
    work = Path(cwd).resolve()
    if not work.is_dir():
        raise HarnessError(f"run_zig_source cwd is not a directory: {work}")
    path = write_file(work / relpath, source)
    if env is not None:
        child_env = {k: v for k, v in env.items() if v is not None}
    else:
        child_env = dict(os.environ)
    return run_zig(
        path,
        argv=argv,
        stdin=stdin,
        deps=deps,
        include_product=include_product,
        zig=zig,
        optimize=optimize,
        extra=extra,
        link_libc=link_libc,
        cwd=work,
        env=child_env,
        timeout=timeout,
        isolate=False,
        root=repo,
        action=action,
    )


__all__ = (
    "DEFAULT_CHARSET",
    "DEFAULT_TIMEOUT",
    "DEFAULT_ZIG",
    "PRODUCT_MODULE_NAME",
    "HarnessError",
    "RunResult",
    "Workspace",
    "as_bytes",
    "compile_zig",
    "default_deps",
    "in_directory",
    "isolated_environ",
    "isolated_filesystem",
    "path_is_file",
    "product_module_source",
    "read_bytes",
    "read_file",
    "repo_root",
    "run_command",
    "run_zig",
    "run_zig_source",
    "workspace",
    "write_file",
    "zig_argv",
    "zig_dep_flags",
    "zig_executable",
)
