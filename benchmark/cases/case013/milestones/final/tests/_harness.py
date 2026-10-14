# feature: F00
"""Shared machinery for driving the product through its public surfaces.

Suites import from this module (``from _harness import ...``). Importing it
performs no I/O, starts no processes, and opens no sockets. All process,
filesystem, and protocol side effects happen only when a caller invokes a
function or enters a context manager below.

The product is a compiled command-line tool, not an importable Python
package. Python tests reach it by spawning the recipe-built binary. This
module is the one canonical way to do that.

Surfaces
--------
* Direct binary — ``<root>/bin/membundle <command> …`` with caller-controlled
  argv, stdin, cwd, and env. Every documented command (init, bootstrap,
  show, search, create, update, relate, validate, agents, mcp, version,
  help) is driven this way.
* Stdio protocol server — ``membundle mcp [bundle]``. The process reads
  newline-delimited JSON-RPC from stdin and writes newline-delimited
  JSON-RPC to stdout until stdin ends. :func:`mcp_batch` feeds a complete
  transcript and waits for exit; :func:`mcp_session` keeps the process
  alive for turn-by-turn exchange.

Missing substrate (no recipe binary) raises ``FileNotFoundError``. A
product non-zero exit is a classified outcome on :class:`RunResult` or
:class:`McpBatchResult`, not a harness failure. Observation failures this
module cannot classify raise :class:`HarnessError`.
"""

from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

# ---------------------------------------------------------------------------
# Public entry defaults
# ---------------------------------------------------------------------------

# Recipe ``make build`` artifact (Makefile BIN).
BIN_RELPATH = Path("bin") / "membundle"

# Environment override for the product binary.
PRODUCT_BIN_ENV = "PRODUCT_BIN"

# Product env that names the MCP workspace root. Isolated calls drop it
# unless the caller puts it back through *updates*.
MCP_ROOT_ENV = "MEMBUNDLE_MCP_ROOT"

DEFAULT_TIMEOUT = 30.0
DEFAULT_CHARSET = "utf-8"
MCP_SILENCE_TIMEOUT = 0.4

# Caller-environment keys that couple a child to the parent product /
# editor / pager / proxy / TTY state. Isolated calls unset these unless
# the caller puts them back through *updates*.
_ISOLATE_UNSET = (
    MCP_ROOT_ENV,
    "MEMBUNDLE_BIN",
    "EDITOR",
    "VISUAL",
    "PAGER",
    "BROWSER",
    "COLUMNS",
    "LINES",
    "NO_COLOR",
    "FORCE_COLOR",
    "CLICOLOR",
    "CLICOLOR_FORCE",
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
)

# Prefixes stripped in full (product env leaks).
_ISOLATE_PREFIXES = ("MEMBUNDLE_",)


# ---------------------------------------------------------------------------
# Errors / result types
# ---------------------------------------------------------------------------


class HarnessError(RuntimeError):
    """Raised when an observation cannot be classified.

    Used for missing substrate, a JSON parse that fails, a workspace path
    that escapes its root, a protocol session that dies mid-exchange, a
    timeout, and I/O failures that are not a documented product outcome.
    Never used to mean "the product returned a non-zero exit the PRD
    describes".
    """


@dataclass(frozen=True)
class RunResult:
    """Outcome of one subprocess invocation.

    Attributes:
        returncode: Process exit status. ``0`` is POSIX success; the
            harness does not interpret any other code.
        stdout: Raw standard output bytes (no decoding applied).
        stderr: Raw standard error bytes (no decoding applied).
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
        """Stdout decoded as UTF-8.

        Raises:
            HarnessError: if stdout is not valid UTF-8. Never replaces
                undecodable bytes — replacement would turn a decode
                failure into a legitimate-looking string.
        """
        return decode_utf8(self.stdout, what="stdout")

    @property
    def stderr_text(self) -> str:
        """Stderr decoded as UTF-8.

        Raises:
            HarnessError: if stderr is not valid UTF-8.
        """
        return decode_utf8(self.stderr, what="stderr")


@dataclass(frozen=True)
class McpBatchResult:
    """Outcome of one stdio-protocol batch: stdin closed, process exited.

    Attributes:
        returncode: Process exit status. The harness does not interpret it.
        messages: JSON values parsed from each non-empty stdout line, in
            order. Empty when the process emitted no protocol lines — never
            ``None``.
        stdout: Raw standard output bytes.
        stderr: Raw standard error bytes.
        argv: Exact argument vector that was executed.
        cwd: Working directory used for the process, as a string.
    """

    returncode: int
    messages: tuple[Any, ...]
    stdout: bytes
    stderr: bytes
    argv: tuple[str, ...]
    cwd: str

    @property
    def stdout_text(self) -> str:
        """Stdout decoded as UTF-8. Raises :class:`HarnessError` if invalid."""
        return decode_utf8(self.stdout, what="stdout")

    @property
    def stderr_text(self) -> str:
        """Stderr decoded as UTF-8. Raises :class:`HarnessError` if invalid."""
        return decode_utf8(self.stderr, what="stderr")


@dataclass
class Workspace:
    """Ephemeral work directory plus the isolated environment bound to it.

    ``path`` is the working directory for invokes. ``home`` is used as
    ``HOME`` (and the XDG roots live under it) so ``~`` expansion and
    default ``AGENTS.md`` lookup cannot see the caller's home. Both trees
    are removed when the allocating context exits.
    """

    path: Path
    home: Path
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

    def read_symlink(self, relpath: str | Path) -> str:
        """Return the raw symlink target under this workspace.

        Raises ``FileNotFoundError`` if the path does not exist. Raises
        :class:`HarnessError` if the path exists but is not a symlink.
        Never returns ``None`` to mean "not a link".
        """
        return read_symlink(self.resolve(relpath))

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

    def mcp_batch(
        self,
        lines: Sequence[str | Mapping[str, Any]],
        *,
        args: Sequence[str] | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
        root: Path | None = None,
        binary: str | Path | None = None,
    ) -> McpBatchResult:
        """Run ``membundle mcp`` to completion with *lines* as stdin.

        See :func:`mcp_batch`. Does not raise on a non-zero product exit.
        """
        env = _apply_updates(self.env, env_updates)
        return mcp_batch(
            lines,
            args=args,
            cwd=cwd if cwd is not None else self.path,
            env=env,
            timeout=timeout,
            root=root,
            binary=binary,
            isolate=False,
        )

    @contextmanager
    def mcp_session(
        self,
        *,
        args: Sequence[str] | None = None,
        env_updates: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
        root: Path | None = None,
        binary: str | Path | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
    ) -> Iterator[McpSession]:
        """Start ``membundle mcp`` bound to this workspace; stop it on exit.

        Does not raise on a later non-zero product exit. The workspace
        directory remains until the outer :func:`workspace` context ends,
        so files the server wrote stay observable after the session.
        """
        env = _apply_updates(self.env, env_updates)
        with mcp_session(
            args=args,
            cwd=cwd if cwd is not None else self.path,
            env=env,
            root=root,
            binary=binary,
            timeout=timeout,
            isolate=False,
        ) as session:
            yield session


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


def _read_regular_file(src: Path) -> None:
    """Raise a classified error when *src* is missing or not a regular file."""
    try:
        if not src.exists():
            raise FileNotFoundError(f"file does not exist: {src}")
        if src.is_symlink():
            # Followed existence was already checked; a dangling link is
            # not a regular file.
            if not src.is_file():
                raise HarnessError(
                    f"path exists but is not a regular file: {src}"
                )
        elif not src.is_file():
            raise HarnessError(f"path exists but is not a regular file: {src}")
    except FileNotFoundError:
        raise
    except HarnessError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc


def decode_utf8(data: bytes, *, what: str = "bytes") -> str:
    """Decode *data* as UTF-8.

    Raises:
        HarnessError: if *data* is not valid UTF-8. Never returns a
            replacement-character string that could be mistaken for a
            successful decode.
    """
    try:
        return data.decode(DEFAULT_CHARSET)
    except UnicodeDecodeError as exc:
        raise HarnessError(
            f"{what} is not valid UTF-8 ({exc}); inspect the raw bytes"
        ) from exc


def encode_utf8(text: str, *, what: str = "text") -> bytes:
    """Encode *text* as UTF-8.

    Raises:
        HarnessError: if *text* cannot be encoded. Never replaces
            unencodable characters.
    """
    try:
        return text.encode(DEFAULT_CHARSET)
    except UnicodeEncodeError as exc:
        raise HarnessError(f"{what} cannot be encoded as UTF-8: {exc}") from exc


def _diagnostic_text(data: bytes) -> str:
    """Decode for harness logs only; replacement is not a test observation."""
    return data.decode(DEFAULT_CHARSET, errors="replace")


def utc_today_iso() -> str:
    """Return today's UTC calendar date as ISO 8601 ``YYYY-MM-DD``.

    Uses the host clock, not the product. Does not contact the binary.
    """
    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# JSON observation
# ---------------------------------------------------------------------------


def parse_json(text: str | bytes, *, what: str = "json") -> Any:
    """Parse *text* as JSON.

    Raises:
        HarnessError: if *text* is not valid JSON. Never returns ``None``
            to mean "could not parse" — a JSON ``null`` is a parsed value
            and is returned as the host ``None`` only after a successful
            parse of the token ``null``.
    """
    if isinstance(text, bytes):
        payload = decode_utf8(text, what=what)
    else:
        payload = text
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        snippet = payload if len(payload) <= 500 else payload[:500] + "…"
        raise HarnessError(
            f"{what} is not valid JSON ({exc}): {snippet!r}"
        ) from exc


def json_stdout(result: RunResult, *, what: str = "stdout") -> Any:
    """Parse a CLI run's stdout as a JSON value.

    Raises:
        HarnessError: if stdout is empty, not UTF-8, or not valid JSON.
            Empty stdout is not mapped to ``None``; inspect
            ``result.stdout`` first when absence of output is itself the
            observation.
    """
    raw = result.stdout
    if not raw.strip():
        raise HarnessError(
            f"{what} is empty; cannot parse JSON "
            f"(exit {result.returncode}, stderr={_diagnostic_text(result.stderr)!r})"
        )
    return parse_json(raw, what=what)


def parse_json_lines(text: str | bytes, *, what: str = "stdout") -> list[Any]:
    """Parse each non-empty line of *text* as a JSON value.

    Blank lines are skipped (the protocol ignores empty input lines and
    does not emit empty output lines as messages). A non-empty line that
    is not JSON raises :class:`HarnessError` — never omitted, never
    returned as ``None``.
    """
    if isinstance(text, bytes):
        payload = decode_utf8(text, what=what)
    else:
        payload = text
    messages: list[Any] = []
    for index, line in enumerate(payload.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            messages.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise HarnessError(
                f"{what} line {index} is not valid JSON ({exc}): {stripped!r}"
            ) from exc
    return messages


def rpc_request(
    method: str,
    params: Mapping[str, Any] | None = None,
    *,
    id: int | str = 1,
    jsonrpc: str = "2.0",
) -> dict[str, Any]:
    """Build a JSON-RPC request object (has an id; expects a reply).

    Does not send anything. *params* is omitted from the object when
    ``None`` so a caller can distinguish "no params member" from ``{}``.
    """
    message: dict[str, Any] = {
        "jsonrpc": jsonrpc,
        "id": id,
        "method": method,
    }
    if params is not None:
        message["params"] = dict(params)
    return message


def rpc_notification(
    method: str,
    params: Mapping[str, Any] | None = None,
    *,
    jsonrpc: str = "2.0",
) -> dict[str, Any]:
    """Build a JSON-RPC notification object (no id; no reply expected).

    Does not send anything.
    """
    message: dict[str, Any] = {
        "jsonrpc": jsonrpc,
        "method": method,
    }
    if params is not None:
        message["params"] = dict(params)
    return message


def encode_rpc_line(message: Mapping[str, Any] | str | bytes) -> str:
    """Return a single protocol line (no trailing newline).

    A mapping is serialized with UTF-8 JSON (``ensure_ascii=False`` so a
    Unicode argument survives). A ``str`` is used as-is so a caller can
    feed a deliberately malformed line. Bytes are decoded as UTF-8.
    """
    if isinstance(message, bytes):
        return decode_utf8(message, what="rpc line")
    if isinstance(message, str):
        return message
    try:
        return json.dumps(dict(message), ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise HarnessError(f"cannot encode JSON-RPC message: {exc}") from exc


# ---------------------------------------------------------------------------
# Paths / discovery
# ---------------------------------------------------------------------------


def repo_root() -> Path:
    """Return the built repository root.

    Tests run with the repository root as the pytest process cwd (recipe
    build artifacts such as ``bin/membundle`` are available there). Returns
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
      2. ``<root>/bin/membundle`` (Makefile ``BIN``).

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
            "the runner build must produce bin/membundle before tests run"
        )
    if not os.access(path, os.X_OK):
        raise FileNotFoundError(f"product binary is not executable: {path}")
    return path


def product_bin_dir(*, root: Path | None = None) -> Path:
    """Return the directory that must precede ``PATH`` so ``membundle`` resolves.

    Uses the parent of :func:`product_bin` when that file exists; otherwise
    ``<root>/bin`` so an isolated environment can still be built before a
    caller attempts an invoke.
    """
    override = os.environ.get(PRODUCT_BIN_ENV)
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path.resolve().parent
        return path.resolve() if path.suffix == "" else path.parent.resolve()
    base = root if root is not None else repo_root()
    return (Path(base) / BIN_RELPATH.parent).resolve()


# ---------------------------------------------------------------------------
# Environment / workspace isolation
# ---------------------------------------------------------------------------


def isolated_environ(
    home: Path | str,
    *,
    updates: Mapping[str, str | None] | None = None,
    base: Mapping[str, str] | None = None,
    root: Path | None = None,
) -> dict[str, str]:
    """Build an environment that does not inherit the caller's home/product state.

    Copies *base* (or ``os.environ``), points ``HOME`` and the XDG dirs at
    *home*, prepends the product ``bin/`` directory to ``PATH``, unsets the
    product / editor / proxy keys that would couple a child to the parent
    (including ``MEMBUNDLE_MCP_ROOT``), sets ``TZ=UTC`` and a UTF-8 locale, and
    applies *updates* last (``None`` unsets). Does not mutate ``os.environ``.

    Returns a new ``dict``.
    """
    home_path = Path(home).resolve()
    cfg_dir = home_path / ".config"
    cache_dir = home_path / ".cache"
    data_dir = home_path / ".local" / "share"
    for directory in (home_path, cfg_dir, cache_dir, data_dir):
        directory.mkdir(parents=True, exist_ok=True)

    env = dict(base) if base is not None else dict(os.environ)
    for key in _ISOLATE_UNSET:
        env.pop(key, None)
    for key in list(env):
        if key.startswith(_ISOLATE_PREFIXES):
            env.pop(key, None)

    bin_dir = str(product_bin_dir(root=root))
    path_entries = [bin_dir]
    existing_path = env.get("PATH", "")
    if existing_path:
        path_entries.extend(
            part
            for part in existing_path.split(os.pathsep)
            if part and part != bin_dir
        )
    env["PATH"] = os.pathsep.join(path_entries)

    env["HOME"] = str(home_path)
    env["XDG_CONFIG_HOME"] = str(cfg_dir)
    env["XDG_CACHE_HOME"] = str(cache_dir)
    env["XDG_DATA_HOME"] = str(data_dir)
    env["TZ"] = "UTC"
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")

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
    root: Path | None = None,
) -> Iterator[Workspace]:
    """Allocate an ephemeral work directory and isolated HOME; clean up.

    Yields a :class:`Workspace`. Both directory trees are removed when
    the context exits, including on exception. The product tree is never
    used as the default cwd.
    """
    work = Path(tempfile.mkdtemp(prefix=prefix))
    home = Path(tempfile.mkdtemp(prefix="harness-home-"))
    try:
        env = isolated_environ(home, updates=updates, root=root)
        yield Workspace(path=work, home=home, env=env)
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


def read_symlink(path: str | Path) -> str:
    """Return the raw target of a symbolic link (not resolved).

    Raises:
        FileNotFoundError: if *path* does not exist.
        HarnessError: if *path* exists but is not a symlink, or on an
            ``OSError`` other than classified absence. Never returns
            ``None`` to mean "not a link".
    """
    src = Path(path)
    try:
        if not src.exists() and not src.is_symlink():
            raise FileNotFoundError(f"file does not exist: {src}")
        if not src.is_symlink():
            raise HarnessError(f"path exists but is not a symbolic link: {src}")
        return os.readlink(src)
    except FileNotFoundError:
        raise
    except HarnessError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot read symlink {src}: {exc}") from exc


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


def path_is_dir(path: str | Path) -> bool:
    """Return whether *path* is an existing directory.

    Raises :class:`HarnessError` on an ``OSError`` other than classified
    absence.
    """
    src = Path(path)
    try:
        return src.is_dir()
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc


def path_is_symlink(path: str | Path) -> bool:
    """Return whether *path* is a symbolic link (dangling links count).

    Raises :class:`HarnessError` on an ``OSError`` other than classified
    absence.
    """
    src = Path(path)
    try:
        return src.is_symlink()
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc


def list_dir(path: str | Path) -> list[str]:
    """Return sorted entry names of directory *path* (not recursive).

    Raises:
        FileNotFoundError: if *path* does not exist.
        HarnessError: if *path* exists but is not a directory, or on an
            ``OSError`` other than classified absence. Never returns an
            empty list to mean "could not list".
    """
    src = Path(path)
    try:
        if not src.exists():
            raise FileNotFoundError(f"directory does not exist: {src}")
        if not src.is_dir():
            raise HarnessError(f"path exists but is not a directory: {src}")
        return sorted(entry.name for entry in src.iterdir())
    except FileNotFoundError:
        raise
    except HarnessError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot list {src}: {exc}") from exc


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
    When *cwd* is ``None``, the current process cwd is used. Raises
    ``FileNotFoundError`` if the executable cannot be found; raises
    ``subprocess.TimeoutExpired`` on timeout. Does not interpret the
    exit status.
    """
    if not argv:
        raise ValueError("argv must be non-empty")
    workdir = str(Path(cwd).resolve()) if cwd is not None else str(repo_root())
    if stdin is None:
        input_bytes: bytes = b""
    elif isinstance(stdin, str):
        input_bytes = encode_utf8(stdin, what="stdin")
    else:
        input_bytes = stdin

    print(
        f"[harness] run cwd={workdir!r} argv={list(argv)!r}",
        flush=True,
    )
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
        print(f"[harness] stderr={_diagnostic_text(result.stderr)!r}", flush=True)
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
    """Invoke the product binary as ``membundle *args``.

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

    with workspace(root=root) as ws:
        return run_command(
            argv, cwd=ws.path, env=ws.env, stdin=stdin, timeout=timeout
        )


# ---------------------------------------------------------------------------
# MCP stdio protocol
# ---------------------------------------------------------------------------


def _mcp_argv(
    args: Sequence[str] | None,
    *,
    root: Path | None,
    binary: str | Path | None,
) -> list[str]:
    exe = Path(binary) if binary is not None else product_bin(root=root)
    return [str(exe), "mcp", *_normalize_args(args)]


def _stdin_from_rpc_lines(lines: Sequence[str | Mapping[str, Any]]) -> str:
    encoded = [encode_rpc_line(line) for line in lines]
    if not encoded:
        return ""
    return "\n".join(encoded) + "\n"


def mcp_batch(
    lines: Sequence[str | Mapping[str, Any]],
    *,
    args: Sequence[str] | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    root: Path | None = None,
    binary: str | Path | None = None,
    isolate: bool = True,
) -> McpBatchResult:
    """Run ``membundle mcp *args`` with *lines* as stdin, then close stdin.

    The product reads until input ends. Each *line* is a mapping (encoded
    as JSON) or a raw string (fed verbatim, including malformed JSON).
    Every non-empty stdout line is parsed as JSON; a non-JSON line raises
    :class:`HarnessError` and is never dropped. An empty transcript is a
    classified empty ``messages`` tuple, not a failure.

    Does not raise on a non-zero product exit. Raises
    ``subprocess.TimeoutExpired`` if the process does not exit in time.
    """

    def _run(
        child_cwd: str | Path | None, child_env: Mapping[str, str] | None
    ) -> McpBatchResult:
        argv = _mcp_argv(args, root=root, binary=binary)
        result = run_command(
            argv,
            cwd=child_cwd,
            env=child_env,
            stdin=_stdin_from_rpc_lines(lines),
            timeout=timeout,
        )
        messages = tuple(parse_json_lines(result.stdout, what="mcp stdout"))
        print(
            f"[harness] mcp_batch messages={len(messages)}",
            flush=True,
        )
        return McpBatchResult(
            returncode=result.returncode,
            messages=messages,
            stdout=result.stdout,
            stderr=result.stderr,
            argv=result.argv,
            cwd=result.cwd,
        )

    if cwd is not None or env is not None or not isolate:
        return _run(cwd, env)

    with workspace(root=root) as ws:
        return _run(ws.path, ws.env)


@dataclass
class McpSession:
    """A live ``membundle mcp`` process speaking newline-delimited JSON-RPC.

    Constructed by :func:`mcp_session` / :func:`start_mcp_session`. The
    allocating context kills the process on exit. Importing this module
    does not start a session.
    """

    argv: tuple[str, ...]
    cwd: str
    env: dict[str, str]
    timeout: float
    _proc: subprocess.Popen[bytes] = field(repr=False, compare=False)
    _stderr_chunks: list[bytes] = field(default_factory=list, repr=False, compare=False)
    _stderr_thread: threading.Thread | None = field(
        default=None, repr=False, compare=False
    )
    _stdout_buf: bytes = field(default=b"", repr=False, compare=False)
    _closed: bool = field(default=False, repr=False, compare=False)

    @property
    def pid(self) -> int | None:
        """Operating-system pid, or ``None`` after the process has been reaped."""
        return self._proc.pid

    @property
    def returncode(self) -> int | None:
        """Exit status if the process has exited, else ``None``."""
        return self._proc.poll()

    @property
    def stderr_bytes(self) -> bytes:
        """Stderr captured so far (drained on a background thread)."""
        return b"".join(self._stderr_chunks)

    def _ensure_running(self, *, context: str) -> None:
        code = self._proc.poll()
        if code is None:
            return
        leftover = self._stdout_buf
        raise HarnessError(
            f"mcp process exited during {context} "
            f"(exit {code}, leftover_stdout={leftover!r}, "
            f"stderr={_diagnostic_text(self.stderr_bytes)!r})"
        )

    def send_line(self, message: str | Mapping[str, Any] | bytes) -> None:
        """Write one protocol line and flush. Does not wait for a reply."""
        self._ensure_running(context="send")
        line = encode_rpc_line(message)
        payload = encode_utf8(line, what="rpc line") + b"\n"
        stdin = self._proc.stdin
        if stdin is None:
            raise HarnessError("mcp session stdin is closed")
        try:
            stdin.write(payload)
            stdin.flush()
        except BrokenPipeError as exc:
            self._ensure_running(context="send")
            raise HarnessError(f"mcp stdin closed while sending: {exc}") from exc
        print(f"[harness] mcp send {line[:200]!r}", flush=True)

    def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        id: int | str = 1,
        timeout: float | None = None,
    ) -> Any:
        """Send a JSON-RPC request and return the next stdout JSON value.

        Waits for one complete protocol line. Does not interpret JSON-RPC
        ``error`` vs ``result`` — that is the caller's observation. Raises
        :class:`HarnessError` if the process exits, times out, or emits a
        non-JSON line. Never returns ``None`` to mean "no reply".
        """
        self.send_line(rpc_request(method, params, id=id))
        return self.read_json(timeout=timeout, required=True)

    def notify(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        """Send a JSON-RPC notification (no id). Does not wait for output."""
        self.send_line(rpc_notification(method, params))

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        id: int | str = 1,
        timeout: float | None = None,
    ) -> Any:
        """Send ``tools/call`` for *name* and return the next JSON value.

        Does not interpret tool-level ``isError`` vs protocol errors.
        """
        params: dict[str, Any] = {"name": name}
        if arguments is not None:
            params["arguments"] = dict(arguments)
        return self.request("tools/call", params, id=id, timeout=timeout)

    def read_json(self, *, timeout: float | None = None, required: bool = True) -> Any:
        """Read one newline-delimited JSON value from stdout.

        When *required* is true (the default), a timeout with the process
        still alive, a process crash, a truncated line, or a non-JSON line
        raises :class:`HarnessError`. When *required* is false, a timeout
        with the process still alive and no complete line is the documented
        "no protocol line arrived" outcome and returns ``None``. A crash
        still raises — silence and death are not the same observation.
        """
        wait = self.timeout if timeout is None else timeout
        line = self._readline(timeout=wait)
        if line is None:
            if self._proc.poll() is not None:
                self._ensure_running(context="read")
            leftover = self._stdout_buf
            if leftover:
                raise HarnessError(
                    "mcp stdout ended with a truncated line "
                    f"(no newline): {leftover!r} "
                    f"stderr={_diagnostic_text(self.stderr_bytes)!r}"
                )
            if required:
                raise HarnessError(
                    f"mcp stdout produced no protocol line within {wait}s "
                    f"(stderr={_diagnostic_text(self.stderr_bytes)!r})"
                )
            return None
        text = decode_utf8(line, what="mcp stdout line").strip()
        if not text:
            # The protocol skips empty input lines; an empty output line
            # is not a classified message. Recurse for the next one.
            return self.read_json(timeout=timeout, required=required)
        return parse_json(text, what="mcp stdout line")

    def close_stdin(self) -> None:
        """Close the process stdin so the server can reach end-of-input."""
        stdin = self._proc.stdin
        if stdin is not None and not stdin.closed:
            stdin.close()

    def wait(self, *, timeout: float | None = None) -> int:
        """Wait for the process to exit and return its status.

        Raises ``subprocess.TimeoutExpired`` if it does not exit in time.
        """
        wait = self.timeout if timeout is None else timeout
        return self._proc.wait(timeout=wait)

    def close(self) -> int | None:
        """Close stdin, wait briefly, then terminate if still running.

        Returns the exit status when known. Always safe to call twice.
        """
        if self._closed:
            return self._proc.poll()
        self._closed = True
        try:
            self.close_stdin()
        except OSError:
            pass
        try:
            return self._proc.wait(timeout=min(2.0, self.timeout))
        except subprocess.TimeoutExpired:
            self._proc.kill()
            try:
                return self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                return self._proc.poll()

    def _readline(self, *, timeout: float) -> bytes | None:
        """Return one stdout line including the newline, or ``None`` on idle timeout.

        Partial data stays in ``_stdout_buf``. A process that exits with a
        complete line still returns that line; an idle timeout with the
        process alive returns ``None``.
        """
        stdout = self._proc.stdout
        if stdout is None:
            raise HarnessError("mcp session stdout is closed")
        deadline = time.monotonic() + timeout
        while True:
            newline_at = self._stdout_buf.find(b"\n")
            if newline_at >= 0:
                line = self._stdout_buf[: newline_at + 1]
                self._stdout_buf = self._stdout_buf[newline_at + 1 :]
                return line
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            if self._proc.poll() is not None:
                rest = stdout.read() or b""
                self._stdout_buf += rest
                newline_at = self._stdout_buf.find(b"\n")
                if newline_at >= 0:
                    line = self._stdout_buf[: newline_at + 1]
                    self._stdout_buf = self._stdout_buf[newline_at + 1 :]
                    return line
                return None
            ready, _, _ = select.select([stdout], [], [], remaining)
            if not ready:
                continue
            try:
                chunk = os.read(stdout.fileno(), 4096)
            except OSError as exc:
                raise HarnessError(f"cannot read mcp stdout: {exc}") from exc
            if not chunk:
                rest = stdout.read() or b""
                self._stdout_buf += rest
                newline_at = self._stdout_buf.find(b"\n")
                if newline_at >= 0:
                    line = self._stdout_buf[: newline_at + 1]
                    self._stdout_buf = self._stdout_buf[newline_at + 1 :]
                    return line
                return None
            self._stdout_buf += chunk


def start_mcp_session(
    *,
    args: Sequence[str] | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    root: Path | None = None,
    binary: str | Path | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> McpSession:
    """Spawn ``membundle mcp *args`` and return a live :class:`McpSession`.

    Caller must :meth:`McpSession.close` (or use :func:`mcp_session`).
    Does not send initialize. Raises ``FileNotFoundError`` if the binary
    is missing.
    """
    argv = _mcp_argv(args, root=root, binary=binary)
    workdir = str(Path(cwd).resolve()) if cwd is not None else str(repo_root())
    child_env = dict(env) if env is not None else None
    wait = DEFAULT_TIMEOUT if timeout is None else timeout
    print(
        f"[harness] mcp start cwd={workdir!r} argv={argv!r}",
        flush=True,
    )
    try:
        proc = subprocess.Popen(
            argv,
            cwd=workdir,
            env=child_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot spawn mcp process {argv!r}: {exc}") from exc

    session = McpSession(
        argv=tuple(argv),
        cwd=workdir,
        env=dict(child_env) if child_env is not None else dict(os.environ),
        timeout=wait,
        _proc=proc,
    )

    def _drain_stderr() -> None:
        stream = proc.stderr
        if stream is None:
            return
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                session._stderr_chunks.append(chunk)
        except OSError:
            return

    thread = threading.Thread(
        target=_drain_stderr, name="harness-mcp-stderr", daemon=True
    )
    session._stderr_thread = thread
    thread.start()
    return session


@contextmanager
def mcp_session(
    *,
    args: Sequence[str] | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    root: Path | None = None,
    binary: str | Path | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    isolate: bool = True,
    updates: Mapping[str, str | None] | None = None,
) -> Iterator[McpSession]:
    """Start ``membundle mcp`` and stop it on exit, including on exception.

    When *isolate* is true (the default) and *cwd* / *env* are omitted,
    the process runs in a fresh :func:`workspace`. The workspace stays
    alive for the duration of the session so on-disk writes remain
    observable until the ``with`` block ends.
    """

    def _enter(
        child_cwd: str | Path | None, child_env: Mapping[str, str] | None
    ) -> Iterator[McpSession]:
        session = start_mcp_session(
            args=args,
            cwd=child_cwd,
            env=child_env,
            root=root,
            binary=binary,
            timeout=timeout,
        )
        try:
            yield session
        finally:
            session.close()
            thread = session._stderr_thread
            if thread is not None:
                thread.join(timeout=1.0)

    if cwd is not None or env is not None or not isolate:
        child_env = _apply_updates(env, updates) if env is not None else (
            dict(os.environ) if updates else None
        )
        if env is None and updates:
            child_env = _apply_updates(os.environ, updates)
        yield from _enter(cwd, child_env)
        return

    with workspace(updates=updates, root=root) as ws:
        yield from _enter(ws.path, ws.env)
