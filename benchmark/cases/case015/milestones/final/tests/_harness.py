# feature: F00
"""Shared machinery for driving the product through its public surface.

Suites import from this module (``from _harness import ...``). Importing it
performs no I/O, starts no processes, and opens no sockets. Process spawn,
filesystem writes, and environment replacement happen only when a caller
invokes a function or enters a context manager below.

The product is a compiled C99 command-line program, not an importable
Python package. Python tests reach it by spawning the recipe-built
binary with caller-controlled argv, cwd, stdin, and environment, then
observing exit status, standard streams, and destination files.

Surfaces
--------
* Direct binary — ``<root>/oggrepack …`` with caller-controlled argv,
  stdin, cwd, and env. Verbs, options, and paths are whatever the
  caller supplies; this module does not decide which verb is valid.

Missing substrate (no recipe binary) raises ``FileNotFoundError``. A
product non-zero exit is a classified outcome on :class:`RunResult`,
not a harness failure. Observation failures this module cannot
classify raise :class:`HarnessError`.
"""

from __future__ import annotations

import os
import secrets
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, Sequence

# ---------------------------------------------------------------------------
# Public entry defaults (PRD: one CLI binary, seekable file operands)
# ---------------------------------------------------------------------------

DEFAULT_CHARSET = "utf-8"
DEFAULT_TIMEOUT = 120.0

# Autotools ``bin_PROGRAMS`` artifact, relative to the built repository root.
BIN_RELPATH = Path("oggrepack")

# Environment override for the product binary (absolute path).
PRODUCT_BIN_ENV = "PRODUCT_BIN"

# Public environment overrides the product reads. Isolated calls unset
# these unless the caller puts them back through *updates*.
MEMCAP_ENV = "ORP_MEMCAP"
SIMD_ENV = "ORP_SIMD"

# Isolated child environments start from this Unicode locale.
_DEFAULT_LOCALE = "C.UTF-8"

# Substrate keys copied from the caller when building an isolated env.
_KEEP_ENV_KEYS = (
    "PATH",
    "USER",
    "LOGNAME",
    "USERNAME",
    "TMPDIR",
    "TEMP",
    "TMP",
    "TZ",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "TERM",
    "HOME",
    "LD_LIBRARY_PATH",
)

# TTY / pager / proxy / product side-channels stripped even if they
# appear in the keep list or the parent environment.
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
    "FTP_PROXY",
    "ftp_proxy",
    MEMCAP_ENV,
    SIMD_ENV,
)

# Any leftover in-tree test or product override under this prefix.
_ISOLATE_PREFIXES = ("ORP_",)


# ---------------------------------------------------------------------------
# Errors / result types
# ---------------------------------------------------------------------------


class HarnessError(RuntimeError):
    """Raised when an observation cannot be classified.

    Used for a missing or unreadable destination, a workspace path that
    escapes its root, a timeout, and I/O failures that are not a
    documented product outcome. Never used to mean "the product returned
    a non-zero exit the PRD describes".
    """


def decode_utf8(data: bytes, *, what: str) -> str:
    """Decode *data* as UTF-8.

    Raises:
        HarnessError: if *data* is not valid UTF-8. Never replaces
            undecodable bytes with a sentinel that could pass for text.
    """
    try:
        return data.decode(DEFAULT_CHARSET)
    except UnicodeDecodeError as exc:
        raise HarnessError(f"{what} is not valid UTF-8: {exc}") from exc


@dataclass(frozen=True)
class RunResult:
    """Outcome of one subprocess invocation.

    Attributes:
        returncode: Process exit status. The harness does not interpret it.
        stdout: Raw standard output bytes (no decoding applied).
        stderr: Raw standard error bytes (no decoding applied).
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
        return decode_utf8(self.stdout, what="stdout")

    @property
    def stderr_text(self) -> str:
        """Stderr decoded as UTF-8. Raises :class:`HarnessError` if not."""
        return decode_utf8(self.stderr, what="stderr")


@dataclass
class Workspace:
    """Ephemeral work directory plus the isolated environment bound to it.

    ``path`` is the working directory for invokes. ``home`` is used as
    ``HOME`` (and the XDG roots live under it) so ``~`` expansion cannot
    see the caller's home. Both trees are removed when the allocating
    context exits.
    """

    path: Path
    home: Path
    env: dict[str, str]

    def resolve(self, relpath: str | Path) -> Path:
        """Return *relpath* resolved under this workspace.

        An absolute *relpath* is accepted only when it already lives
        under this workspace. Raises :class:`HarnessError` when the
        resolved path escapes the workspace.
        """
        base = self.path.resolve()
        candidate = Path(relpath)
        target = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
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
        """Read a text file under this workspace.

        Raises:
            HarnessError: if *relpath* escapes the workspace, or if the
                path exists but is not a regular file.
            FileNotFoundError: if the file does not exist — never returns
                an empty string or ``None`` to mean "missing".
        """
        return read_file(self.resolve(relpath), encoding=encoding)

    def read_bytes(self, relpath: str | Path) -> bytes:
        """Read a binary file under this workspace.

        Raises ``FileNotFoundError`` if the file does not exist — never
        returns empty bytes to mean "missing". Raises :class:`HarnessError`
        if the path exists but is not a regular file.
        """
        return read_bytes(self.resolve(relpath))

    def read_bytes_if_present(self, relpath: str | Path) -> bytes | None:
        """Return file bytes, or ``None`` if the path is absent.

        ``None`` means classified absence only. Raises :class:`HarnessError`
        if the path exists but is not a regular file, or on I/O errors
        other than absence.
        """
        return read_bytes_if_present(self.resolve(relpath))

    def file_size(self, relpath: str | Path) -> int:
        """Return the size in bytes of a regular file under this workspace.

        Raises ``FileNotFoundError`` if the file does not exist — never
        returns ``0`` to mean "missing".
        """
        return file_size(self.resolve(relpath))

    def path_is_file(self, relpath: str | Path) -> bool:
        """Return whether *relpath* is an existing regular file."""
        return path_is_file(self.resolve(relpath))

    def mkdir(self, relpath: str | Path) -> Path:
        """Create a directory (and parents) under this workspace."""
        dest = self.resolve(relpath)
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def make_fifo(self, relpath: str | Path) -> Path:
        """Create a named pipe under this workspace and return its path.

        Opening the pipe for write without a reader can block; callers
        that feed it to the product must bound the invoke with a timeout.
        """
        dest = self.resolve(relpath)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.mkfifo(dest)
        except OSError as exc:
            raise HarnessError(f"cannot create fifo {dest}: {exc}") from exc
        return dest

    def copy_file(self, src: str | Path, relpath: str | Path) -> Path:
        """Copy an existing regular file into this workspace.

        *src* may live outside the workspace (a fixture the caller already
        holds). *relpath* is the destination under this workspace.
        """
        data = read_bytes(src)
        return self.write(relpath, data)

    def remove_file(self, relpath: str | Path) -> None:
        """Remove a regular file. No-op if the path is absent."""
        remove_file(self.resolve(relpath))

    def invoke(
        self,
        args: Sequence[str] | None = None,
        *,
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
        root: Path | None = None,
        binary: str | Path | None = None,
    ) -> RunResult:
        """Run the product binary with this workspace as cwd and env.

        *env_updates* are applied on a copy of :attr:`env` (``None``
        unsets). Does not raise on a non-zero product exit.
        """
        env = _apply_updates(self.env, env_updates)
        return invoke(
            args,
            cwd=cwd if cwd is not None else self.path,
            env=env,
            stdin=stdin,
            timeout=timeout,
            root=root,
            binary=binary,
            isolate=False,
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


def _normalize_args(args: Sequence[str] | None) -> tuple[str, ...]:
    if args is None:
        return ()
    return tuple(str(a) for a in args)


def _stat_regular_file(src: Path) -> os.stat_result:
    """Return ``stat`` for a regular file, or raise a classified error."""
    try:
        info = src.stat()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise HarnessError(f"path exists but is not a regular file: {src}")
    return info


def token(nbytes: int = 6) -> str:
    """Return a fresh lowercase hex token for runtime-unique fixtures.

    Uses :func:`secrets.token_hex`. Does not contact the product.
    """
    if nbytes < 1:
        raise ValueError("nbytes must be >= 1")
    return secrets.token_hex(nbytes)


# ---------------------------------------------------------------------------
# Paths / discovery
# ---------------------------------------------------------------------------


def repo_root() -> Path:
    """Return the built repository root.

    Tests run with the repository root as the pytest process cwd (recipe
    build artifacts such as ``oggrepack`` are available there). Returns
    ``Path.cwd()`` resolved; does not search the filesystem.
    """
    return Path.cwd().resolve()


def _require_executable(path: Path, *, origin: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"{origin} does not point to a file: {path}")
    if not os.access(path, os.X_OK):
        raise FileNotFoundError(f"{origin} is not executable: {path}")
    return path.resolve()


def product_bin(*, root: Path | None = None) -> Path:
    """Locate the recipe-built product binary and return its absolute path.

    Resolution order:
      1. ``PRODUCT_BIN`` environment variable, if set.
      2. ``<root>/oggrepack`` (Autotools ``bin_PROGRAMS`` default).

    Does not fall back to ``PATH``. A system-installed binary would hide a
    recipe-build shortfall.

    Raises:
        FileNotFoundError: when no executable exists at the resolved path.
            That is a substrate gap, not a product-behavior judgment.
    """
    override = os.environ.get(PRODUCT_BIN_ENV)
    if override:
        return _require_executable(
            Path(override).expanduser(), origin=PRODUCT_BIN_ENV
        )

    base = root if root is not None else repo_root()
    path = (Path(base) / BIN_RELPATH).resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"product binary not found at {path}; "
            "the runner build must produce oggrepack before tests run"
        )
    if not os.access(path, os.X_OK):
        raise FileNotFoundError(f"product binary is not executable: {path}")
    return path


# ---------------------------------------------------------------------------
# Environment / workspace isolation
# ---------------------------------------------------------------------------


def isolated_environ(
    home: Path | str,
    *,
    updates: Mapping[str, str | None] | None = None,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build an environment that does not inherit the caller's product state.

    Starts from a whitelist of substrate keys in *base* (or
    ``os.environ``), points ``HOME`` and the XDG dirs at *home*, unsets
    product overrides (``ORP_MEMCAP``, ``ORP_SIMD``) and TTY/proxy
    side-channels, forces a ``C.UTF-8`` locale, and applies *updates*
    last (``None`` unsets). Does not mutate ``os.environ``.

    Returns a new ``dict``.
    """
    home_path = Path(home).resolve()
    cfg_dir = home_path / ".config"
    cache_dir = home_path / ".cache"
    data_dir = home_path / ".local" / "share"
    for directory in (home_path, cfg_dir, cache_dir, data_dir):
        directory.mkdir(parents=True, exist_ok=True)

    source = base if base is not None else os.environ
    env: dict[str, str] = {}
    for key in _KEEP_ENV_KEYS:
        value = source.get(key)
        if value is not None:
            env[key] = value

    for key in _ISOLATE_UNSET:
        env.pop(key, None)
    for key in list(env):
        if key.startswith(_ISOLATE_PREFIXES):
            env.pop(key, None)

    env["HOME"] = str(home_path)
    env["XDG_CONFIG_HOME"] = str(cfg_dir)
    env["XDG_CACHE_HOME"] = str(cache_dir)
    env["XDG_DATA_HOME"] = str(data_dir)
    env["LANG"] = _DEFAULT_LOCALE
    env["LC_ALL"] = _DEFAULT_LOCALE

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
def workspace(
    *,
    updates: Mapping[str, str | None] | None = None,
    prefix: str = "harness-ws-",
) -> Iterator[Workspace]:
    """Allocate an ephemeral work directory and isolated HOME; clean up.

    Yields a :class:`Workspace`. Both directory trees are removed when
    the context exits, including on exception. The product tree is never
    used as the default cwd.
    """
    work = Path(tempfile.mkdtemp(prefix=prefix))
    home = Path(tempfile.mkdtemp(prefix="harness-home-"))
    try:
        env = isolated_environ(home, updates=updates)
        yield Workspace(path=work, home=home, env=env)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# File observation
# ---------------------------------------------------------------------------


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
    _stat_regular_file(src)
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
    _stat_regular_file(src)
    try:
        return src.read_bytes()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot read {src}: {exc}") from exc


def read_bytes_if_present(path: str | Path) -> bytes | None:
    """Return file bytes, or ``None`` if *path* is absent.

    ``None`` maps only classified absence (the path does not exist).
    Raises :class:`HarnessError` if the path exists but is not a regular
    file, or on an ``OSError`` other than absence — never treats a
    permission or I/O failure as "not written".
    """
    src = Path(path)
    try:
        exists = src.exists()
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc
    if not exists:
        return None
    return read_bytes(src)


def path_is_file(path: str | Path) -> bool:
    """Return whether *path* is an existing regular file.

    ``False`` means the path is absent or is not a regular file after a
    successful lookup. Raises :class:`HarnessError` on an ``OSError``
    other than classified absence — never treats a permission or I/O
    failure as "not a file".
    """
    src = Path(path)
    try:
        return src.is_file()
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc


def file_size(path: str | Path) -> int:
    """Return the size in bytes of a regular file.

    Raises ``FileNotFoundError`` if the file does not exist — never
    returns ``0`` to mean "missing". Raises :class:`HarnessError` if the
    path exists but is not a regular file.
    """
    return int(_stat_regular_file(Path(path)).st_size)


def files_identical(left: str | Path, right: str | Path) -> bool:
    """Return whether two existing regular files have identical bytes.

    Raises ``FileNotFoundError`` if either path is missing — never
    treats absence as "not identical". Both files are read; a read
    failure raises :class:`HarnessError`.
    """
    return read_bytes(left) == read_bytes(right)


def stored_copy(dest: bytes, src: bytes) -> bool:
    """Return whether *dest* carries every byte of *src* verbatim, in order.

    Equality is the degenerate case. A compress destination that wraps
    the whole input (header, trailer, or both) is a stored copy, not a
    recompression (PRD capability discrimination). Type errors raise.
    """
    for name, value in (("dest", dest), ("src", src)):
        if not isinstance(value, (bytes, bytearray)):
            raise HarnessError(f"stored_copy {name} expected bytes, got {type(value)!r}")
    if not src:
        raise HarnessError("stored_copy source is empty")
    return bytes(src) in bytes(dest)


# ---------------------------------------------------------------------------
# Host side state (the archive alone must carry what expand needs)
# ---------------------------------------------------------------------------

_WRITABLE_ROOTS: tuple[str, ...] | None = None
_PRUNE_TOPS = ("/proc", "/sys", "/dev")
_EXTRA_ROOTS = ("/dev/shm", "/dev/mqueue")
_SYSVIPC = (("shm", 7), ("sem", 4), ("msg", 7))


def _writable_roots() -> tuple[str, ...]:
    """Directories this user can create entries in. Computed once per session."""
    global _WRITABLE_ROOTS
    if _WRITABLE_ROOTS is not None:
        return _WRITABLE_ROOTS
    found: list[str] = []
    for top, dirs, _files in os.walk("/", topdown=True, followlinks=False):
        if top in _PRUNE_TOPS:
            dirs[:] = []
            continue
        if os.access(top, os.W_OK | os.X_OK):
            found.append(top)
            dirs[:] = []
    for extra in _EXTRA_ROOTS:
        if os.path.isdir(extra) and os.access(extra, os.W_OK | os.X_OK):
            found.append(extra)
    _WRITABLE_ROOTS = tuple(found)
    print(f"[harness] writable roots={list(_WRITABLE_ROOTS)!r}", flush=True)
    return _WRITABLE_ROOTS


def _own_pids() -> frozenset[int]:
    uid = os.getuid()
    pids: set[int] = set()
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/status", encoding="ascii", errors="replace") as fh:
                for line in fh:
                    if line.startswith("Uid:"):
                        if int(line.split()[1]) == uid:
                            pids.add(int(name))
                        break
        except (OSError, ValueError, IndexError):
            continue
    return frozenset(pids)


def _own_ipc() -> frozenset[tuple[str, int]]:
    uid = os.getuid()
    objs: set[tuple[str, int]] = set()
    for kind, uid_col in _SYSVIPC:
        try:
            with open(f"/proc/sysvipc/{kind}", encoding="ascii", errors="replace") as fh:
                rows = fh.read().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            cols = row.split()
            try:
                if int(cols[uid_col]) == uid:
                    objs.add((kind, int(cols[1])))
            except (ValueError, IndexError):
                continue
    return frozenset(objs)


@dataclass(frozen=True)
class SideState:
    """Snapshot of host state a product process could leave behind."""

    entries: Mapping[str, tuple[int, int, int, int, int]]
    pids: frozenset[int]
    ipc: frozenset[tuple[str, int]]


def side_state_snapshot() -> SideState:
    """Record entries under every writable root, own processes, own SysV IPC."""
    entries: dict[str, tuple[int, int, int, int, int]] = {}
    for root in _writable_roots():
        for top, dirs, files in os.walk(root, followlinks=False):
            for name in (*dirs, *files):
                path = os.path.join(top, name)
                try:
                    st = os.lstat(path)
                except OSError:
                    continue
                entries[path] = (
                    st.st_mode, st.st_ino, st.st_size, st.st_mtime_ns, st.st_uid
                )
    return SideState(entries=entries, pids=_own_pids(), ipc=_own_ipc())


def purge_side_state(before: SideState, keep: Sequence[str | Path]) -> list[str]:
    """Remove host state created since *before*, except the *keep* paths.

    Kills this user's processes started since the snapshot, removes SysV
    IPC objects it created, and deletes every new file, directory, socket,
    or link under the writable roots. Returns this user's pre-existing
    regular files (outside *keep*) whose inode, size, or mtime changed:
    a product that parks state in an existing file is reported, not
    silently accepted. Nothing here is a public entry.
    """
    import ctypes
    import signal

    keep_set = {os.path.realpath(str(p)) for p in keep}
    for pid in sorted(_own_pids() - before.pids - {os.getpid(), os.getppid()}):
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"[harness] killed stray process pid={pid}", flush=True)
        except OSError:
            pass
    new_ipc = _own_ipc() - before.ipc
    if new_ipc:
        libc = ctypes.CDLL(None, use_errno=True)
        for kind, ident in sorted(new_ipc):
            if kind == "shm":
                libc.shmctl(ident, 0, None)
            elif kind == "sem":
                libc.semctl(ident, 0, 0)
            else:
                libc.msgctl(ident, 0, None)
            print(f"[harness] removed SysV {kind} id={ident}", flush=True)
    after = side_state_snapshot()
    removed = 0
    for path in sorted(set(after.entries) - set(before.entries), key=len):
        if os.path.realpath(path) in keep_set or not os.path.lexists(path):
            continue
        try:
            if stat.S_ISDIR(after.entries[path][0]) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.unlink(path)
            removed += 1
        except OSError as exc:
            raise HarnessError(f"cannot remove side state {path}: {exc}") from exc
    uid = os.getuid()
    changed: list[str] = []
    for path, old in before.entries.items():
        new = after.entries.get(path)
        if new is None or not stat.S_ISREG(old[0]) or old[4] != uid:
            continue
        if os.path.realpath(path) in keep_set:
            continue
        if new[1:4] != old[1:4]:
            changed.append(path)
    print(
        f"[harness] side state purge removed={removed} changed={len(changed)}",
        flush=True,
    )
    return changed


def same_existing_file(left: str | Path, right: str | Path) -> bool:
    """Return whether two paths name the same existing regular file.

    ``False`` if either path is absent or is not a regular file after a
    successful lookup. Raises :class:`HarnessError` on an ``OSError``
    other than classified absence.
    """
    a = Path(left)
    b = Path(right)
    if not path_is_file(a) or not path_is_file(b):
        return False
    try:
        return a.samefile(b)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise HarnessError(f"cannot compare {a} and {b}: {exc}") from exc


def remove_file(path: str | Path) -> None:
    """Remove a regular file. No-op if the path is absent.

    Absence is a classified outcome (nothing to remove). Raises
    :class:`HarnessError` if the path exists and is not a regular file,
    or if unlink fails for a reason other than absence.
    """
    src = Path(path)
    try:
        exists = src.exists()
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc
    if not exists:
        return
    if not path_is_file(src):
        raise HarnessError(f"path exists but is not a regular file: {src}")
    try:
        src.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise HarnessError(f"cannot remove {src}: {exc}") from exc


# ---------------------------------------------------------------------------
# Process invocation
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
    When *cwd* is ``None``, the current process cwd is used.

    Raises ``FileNotFoundError`` if the executable cannot be found.
    Raises :class:`HarnessError` on timeout or on an ``OSError`` other
    than a missing executable. Does not interpret the exit status.
    """
    if not argv:
        raise ValueError("argv must be non-empty")
    workdir = str(Path(cwd).resolve()) if cwd is not None else str(repo_root())
    if stdin is None:
        input_bytes: bytes = b""
    elif isinstance(stdin, str):
        input_bytes = stdin.encode(DEFAULT_CHARSET)
    else:
        input_bytes = stdin

    child_env = dict(env) if env is not None else dict(os.environ)
    argv_list = [str(a) for a in argv]
    print(
        f"[harness] run cwd={workdir!r} argv={argv_list!r}",
        flush=True,
    )
    try:
        completed = subprocess.run(
            argv_list,
            cwd=workdir,
            env=child_env,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        raise
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(
            f"command timed out after {timeout}s: {argv_list!r}"
        ) from exc
    except OSError as exc:
        raise HarnessError(f"failed to execute {argv_list[0]!r}: {exc}") from exc

    result = RunResult(
        returncode=completed.returncode,
        stdout=completed.stdout or b"",
        stderr=completed.stderr or b"",
        argv=tuple(argv_list),
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


def invoke(
    args: Sequence[str] | None = None,
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: bytes | str | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    root: Path | None = None,
    binary: str | Path | None = None,
    isolate: bool = True,
) -> RunResult:
    """Invoke the product binary as ``oggrepack *args``.

    When *binary* is omitted, uses :func:`product_bin`. When *isolate* is
    true (the default) and *cwd* / *env* are omitted, the process runs in
    a fresh :func:`workspace` so it cannot see the caller's cwd or HOME.
    Pass ``isolate=False`` (and optionally *cwd* / *env*) to inherit the
    caller's process state, or to reuse a :class:`Workspace`.

    Returns a :class:`RunResult`. Does not raise on a non-zero product
    exit — that status is the observation.
    """
    exe = Path(binary) if binary is not None else product_bin(root=root)
    argv = [str(exe), *_normalize_args(args)]

    if cwd is not None or env is not None or not isolate:
        return run_command(
            argv, cwd=cwd, env=env, stdin=stdin, timeout=timeout
        )

    with workspace() as ws:
        return run_command(
            argv, cwd=ws.path, env=ws.env, stdin=stdin, timeout=timeout
        )


__all__ = (
    "BIN_RELPATH",
    "DEFAULT_CHARSET",
    "DEFAULT_TIMEOUT",
    "MEMCAP_ENV",
    "PRODUCT_BIN_ENV",
    "SIMD_ENV",
    "HarnessError",
    "RunResult",
    "SideState",
    "Workspace",
    "decode_utf8",
    "file_size",
    "files_identical",
    "in_directory",
    "invoke",
    "isolated_environ",
    "path_is_file",
    "product_bin",
    "purge_side_state",
    "read_bytes",
    "read_bytes_if_present",
    "read_file",
    "remove_file",
    "repo_root",
    "run_command",
    "same_existing_file",
    "side_state_snapshot",
    "stored_copy",
    "token",
    "workspace",
    "write_file",
)


def test_no_arguments_invokes_product_and_exits_usage():
    """No operands is a usage error from the product binary itself."""
    result = invoke([])
    # TEST-FIX(F00): upstream src/main.c:581 shows no positional args
    # return exit 2 (src/common.h:77).
    assert result.returncode == 2, (
        f"no arguments must be a usage error; exit={result.returncode} "
        f"stderr={result.stderr!r}"
    )
    # TEST-FIX(F00): upstream src/main.c:581 shows a diagnostic written to
    # stderr via usage(); the banner spelling at src/main.c:57 is not scored.
    assert result.stderr, (
        f"usage error must write a non-empty diagnostic to stderr; "
        f"stdout={result.stdout!r}"
    )
