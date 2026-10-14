# feature: F00
"""Shared machinery for driving the product through its public surfaces.

Suites import from this module (``from _harness import ...``). Importing it
performs no I/O, starts no processes, and opens no sockets. Process spawn,
filesystem writes, and environment replacement happen only when a caller
invokes a function or enters a context manager below.

The product is a command-line detector plus companion agent-plugin
hooks. It is not an importable Python package. Python tests reach it by
spawning the recipe-provided interpreter against the detector script,
and reach the plugin by spawning Node against the shipped hook files
with the JSON payloads a host agent sends.

Surfaces
--------
* Detector command — :func:`invoke`. ``python scripts/detect.py`` with
  caller-controlled arguments, stdin, cwd, and env. A file path or
  empty argv (stdin) in; a structured report, scrubbed text, usage, or
  a structured error out.
* Plugin hooks — :func:`invoke_hook`. ``node hooks/<entry>.js`` with
  JSON on stdin. Named entries are the host events the PRD attaches
  behaviour to: session-start, prompt-submit, subagent-start,
  post-tool-use, and stats.

Each isolated call starts from a whitelist of substrate environment
keys. Host-plugin and mode-flag names that are not on that list are
dropped so a stored level, a plugin-root override, or any other process
binding the suite did not name cannot leak in from the parent.

A product non-zero exit is a classified outcome on :class:`RunResult`,
not a harness failure. Observation failures this module cannot classify
raise :class:`HarnessError`.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

# ---------------------------------------------------------------------------
# Public entry defaults (PRD: detector command + plugin hooks)
# ---------------------------------------------------------------------------

DEFAULT_CHARSET = "utf-8"
DEFAULT_TIMEOUT = 60.0

PRODUCT_ROOT_ENV = "PRODUCT_ROOT"
PRODUCT_PYTHON_ENV = "PRODUCT_PYTHON"
PRODUCT_NODE_ENV = "PRODUCT_NODE"
PRODUCT_DETECTOR_ENV = "PRODUCT_DETECTOR"

DETECTOR_RELPATH = Path("scripts") / "detect.py"
HOOKS_RELPATH = Path("hooks")

# Host-event names the PRD uses for the plugin surface. Values are the
# shipped hook files under hooks/.
HOOK_FILES = {
    "session-start": "prosecheck-activate.js",
    "prompt-submit": "prosecheck-tracker.js",
    "subagent-start": "prosecheck-subagent.js",
    "post-tool-use": "prosecheck-guard.js",
    "stats": "prosecheck-stats.js",
}

# Config filenames the plugin reads and writes under CLAUDE_CONFIG_DIR.
MODE_FLAG_NAME = ".prosecheck-active"
LEDGER_PREFIX = ".prosecheck-ledger"

# Host environment the plugin documents.
ENV_CONFIG_DIR = "CLAUDE_CONFIG_DIR"
ENV_PLUGIN_ROOT = "CLAUDE_PLUGIN_ROOT"
ENV_DEFAULT_MODE = "PROSECHECK_DEFAULT_MODE"

# Isolated child environments start from this Unicode locale.
_DEFAULT_LOCALE = "C.UTF-8"

# Substrate keys copied from the caller when building an isolated env.
# Everything else is dropped so a stored level, a plugin-root override,
# or an incidental parent variable cannot fill a condition the suite
# did not name.
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
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "HOME",
)

# TTY / pager / editor / proxy / Node / plugin side-channels stripped
# even if they appear in the keep list or the parent environment.
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
    "NODE_OPTIONS",
    "NODE_PATH",
    "NODE_REPL_HISTORY",
    ENV_CONFIG_DIR,
    ENV_PLUGIN_ROOT,
    ENV_DEFAULT_MODE,
)


# ---------------------------------------------------------------------------
# Errors / result types
# ---------------------------------------------------------------------------


class HarnessError(RuntimeError):
    """Raised when an observation cannot be classified.

    Used for a missing interpreter or detector script, a JSON probe that
    is not well-formed, a workspace path that escapes its root, a
    timeout, and I/O failures that are not a documented product outcome.
    Never used to mean "the product returned a non-zero exit the PRD
    describes".
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
class Workspace:
    """Ephemeral work directory plus the isolated environment bound to it.

    ``path`` is the working directory for invokes. ``home`` is used as
    ``HOME`` so ``~`` expansion cannot see the caller's home.
    ``config_dir`` is the plugin settings folder (mode flag and session
    ledger). ``root`` is the built repository root used to locate the
    detector and hooks. Trees under ``path`` and ``home`` are removed
    when the allocating context exits; the product tree is not.
    """

    path: Path
    home: Path
    config_dir: Path
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
            HarnessError: if *relpath* escapes the workspace, if the
                path exists but is not a regular file, or if the bytes
                are not valid in *encoding*.
            FileNotFoundError: if the file does not exist — never
                returns an empty string or ``None`` to mean "missing".
        """
        return read_file(self.resolve(relpath), encoding=encoding)

    def read_bytes(self, relpath: str | Path) -> bytes:
        """Read a binary file under this workspace.

        Raises ``FileNotFoundError`` if the file does not exist — never
        returns empty bytes to mean "missing".
        """
        return read_bytes(self.resolve(relpath))

    def mkdir(self, relpath: str | Path) -> Path:
        """Create a directory under this workspace (parents included)."""
        dest = self.resolve(relpath)
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def chmod(self, relpath: str | Path, mode: int) -> Path:
        """Set permission bits on a path under this workspace.

        Raises ``FileNotFoundError`` if the path does not exist.
        Raises :class:`HarnessError` on other ``OSError`` outcomes.
        """
        dest = self.resolve(relpath)
        try:
            os.chmod(dest, mode)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise HarnessError(f"cannot chmod {dest}: {exc}") from exc
        return dest

    def invoke(
        self,
        args: Sequence[str] | None = None,
        *,
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
        root: Path | None = None,
    ) -> RunResult:
        """Run the detector command with this workspace as cwd and env.

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
            root=root if root is not None else self.root,
            isolate=False,
        )

    def invoke_hook(
        self,
        entry: str,
        *,
        payload: Mapping[str, Any] | None = None,
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
        root: Path | None = None,
    ) -> RunResult:
        """Fire a plugin hook with this workspace as cwd and env.

        Does not raise on a non-zero product exit.
        """
        env = _apply_updates(self.env, env_updates)
        return invoke_hook(
            entry,
            payload=payload,
            stdin=stdin,
            cwd=cwd if cwd is not None else self.path,
            env=env,
            timeout=timeout,
            root=root if root is not None else self.root,
            isolate=False,
        )

    def write_mode_flag(self, text: str) -> Path:
        """Write the one-word level flag in this workspace's config dir."""
        return write_mode_flag(self.config_dir, text)

    def read_mode_flag(self) -> str | None:
        """Read the stored level flag, or ``None`` if no flag file exists."""
        return read_mode_flag(self.config_dir)


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
        if not src.is_file():
            raise HarnessError(f"path exists but is not a regular file: {src}")
    except FileNotFoundError:
        raise
    except HarnessError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc


def _encode_stdin(stdin: bytes | str | None) -> bytes:
    if stdin is None:
        return b""
    if isinstance(stdin, str):
        return stdin.encode(DEFAULT_CHARSET)
    return stdin


def _python() -> str:
    override = os.environ.get(PRODUCT_PYTHON_ENV)
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"{PRODUCT_PYTHON_ENV} does not point to a file: {path}"
            )
        return str(path.resolve())
    python = sys.executable
    if not python:
        raise HarnessError("sys.executable is empty; cannot spawn an interpreter")
    return python


# ---------------------------------------------------------------------------
# Paths / discovery
# ---------------------------------------------------------------------------


def repo_root() -> Path:
    """Return the built repository root.

    Tests run with the repository root as the pytest process cwd. Returns
    ``Path.cwd()`` resolved; does not search the filesystem. ``PRODUCT_ROOT``
    overrides the cwd when set.
    """
    override = os.environ.get(PRODUCT_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return Path.cwd().resolve()


def detector_script(*, root: Path | None = None) -> Path:
    """Locate the detector command script and return its absolute path.

    Resolution order:
      1. ``PRODUCT_DETECTOR`` environment variable, if set.
      2. ``<root>/scripts/detect.py``.

    Does not import the script. A missing file is a substrate gap.

    Raises:
        FileNotFoundError: when no regular file exists at the resolved path.
    """
    override = os.environ.get(PRODUCT_DETECTOR_ENV)
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(
                f"{PRODUCT_DETECTOR_ENV} does not point to a file: {path}"
            )
        return path

    base = root if root is not None else repo_root()
    path = (Path(base) / DETECTOR_RELPATH).resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"detector command not found at {path}; "
            "the runner must expose scripts/detect.py in the built tree"
        )
    return path


def node_executable(*, env: Mapping[str, str] | None = None) -> str:
    """Locate the Node interpreter used to fire plugin hooks.

    Returns:
        Absolute path to the executable, as a string.

    Raises:
        FileNotFoundError: when ``node`` is not on ``PATH``. That is a
            substrate gap, not a product-behavior judgment.
    """
    override = os.environ.get(PRODUCT_NODE_ENV)
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"{PRODUCT_NODE_ENV} does not point to a file: {path}"
            )
        return str(path.resolve())
    search_path = (env or os.environ).get("PATH")
    found = shutil.which("node", path=search_path)
    if found is None:
        raise FileNotFoundError(
            "node executable not found on PATH; plugin hooks require Node.js"
        )
    return found


def hook_script(entry: str, *, root: Path | None = None) -> Path:
    """Return the absolute path of the hook file for a named public entry.

    *entry* is a PRD host-event name (``session-start``, ``prompt-submit``,
    ``subagent-start``, ``post-tool-use``, ``stats``) or a filename under
    ``hooks/``.

    Raises:
        HarnessError: when *entry* is not a known event and is not a
            ``.js`` filename.
        FileNotFoundError: when the resolved file does not exist.
    """
    if entry in HOOK_FILES:
        name = HOOK_FILES[entry]
    elif entry.endswith(".js") and "/" not in entry and "\\" not in entry:
        name = entry
    else:
        known = ", ".join(sorted(HOOK_FILES))
        raise HarnessError(
            f"unknown hook entry {entry!r}; expected one of {known} "
            "or a hooks/*.js filename"
        )
    base = root if root is not None else repo_root()
    path = (Path(base) / HOOKS_RELPATH / name).resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"plugin hook not found at {path}; "
            "the runner must expose the Node hook files under hooks/"
        )
    return path


# ---------------------------------------------------------------------------
# Environment / workspace isolation
# ---------------------------------------------------------------------------


def isolated_environ(
    home: Path | str,
    *,
    updates: Mapping[str, str | None] | None = None,
    base: Mapping[str, str] | None = None,
    root: Path | None = None,
    config_dir: Path | str | None = None,
) -> dict[str, str]:
    """Build an environment that does not inherit the caller's plugin/home state.

    Copies a whitelist from *base* (or ``os.environ``), points ``HOME`` at
    *home*, points the plugin config dir at *config_dir* (default
    ``<home>/.claude``), points the plugin root at the built repository,
    unsets host / Node / mode-flag keys that would couple a child to the
    parent, forces a UTF-8 locale for the detector, and applies *updates*
    last (``None`` unsets). Does not mutate ``os.environ``.

    Returns a new ``dict``.
    """
    home_path = Path(home).resolve()
    cfg = (
        Path(config_dir).resolve()
        if config_dir is not None
        else (home_path / ".claude")
    )
    plugin_root = (root if root is not None else repo_root()).resolve()
    for directory in (home_path, cfg):
        directory.mkdir(parents=True, exist_ok=True)

    source = base if base is not None else os.environ
    env: dict[str, str] = {}
    for key in _KEEP_ENV_KEYS:
        if key in source:
            env[key] = source[key]
    for key in _ISOLATE_UNSET:
        env.pop(key, None)

    env["HOME"] = str(home_path)
    env[ENV_CONFIG_DIR] = str(cfg)
    env[ENV_PLUGIN_ROOT] = str(plugin_root)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("LANG", _DEFAULT_LOCALE)
    env.setdefault("LC_ALL", _DEFAULT_LOCALE)

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

    Yields a :class:`Workspace`. Work and home trees are removed when
    the context exits, including on exception. The product tree is never
    used as the default cwd.
    """
    product_root = (root if root is not None else repo_root()).resolve()
    work = Path(tempfile.mkdtemp(prefix=prefix))
    home = Path(tempfile.mkdtemp(prefix="harness-home-"))
    config_dir = home / ".claude"
    try:
        env = isolated_environ(
            home, updates=updates, root=product_root, config_dir=config_dir
        )
        yield Workspace(
            path=work,
            home=home,
            config_dir=config_dir,
            env=env,
            root=product_root,
        )
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
    if the bytes are not valid in *encoding*, or on an ``OSError`` other
    than classified absence.
    """
    src = Path(path)
    _read_regular_file(src)
    try:
        data = src.read_bytes()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot read {src}: {exc}") from exc
    try:
        return data.decode(encoding)
    except UnicodeDecodeError as exc:
        raise HarnessError(f"{src} is not valid {encoding}: {exc}") from exc


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


def file_mode(path: str | Path) -> int:
    """Return the permission bits of *path* (``stat.S_IMODE``).

    Raises ``FileNotFoundError`` if the path does not exist — never
    returns ``0`` to mean "missing". Raises :class:`HarnessError` on
    other ``OSError`` outcomes.
    """
    src = Path(path)
    try:
        return stat.S_IMODE(src.stat().st_mode)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc


# ---------------------------------------------------------------------------
# Plugin config observation (mode flag / ledger files)
# ---------------------------------------------------------------------------


def mode_flag_path(config_dir: str | Path) -> Path:
    """Return the path of the one-word level flag under *config_dir*."""
    return Path(config_dir) / MODE_FLAG_NAME


def write_mode_flag(config_dir: str | Path, text: str) -> Path:
    """Write *text* as the stored level flag.

    Creates *config_dir* if needed. Does not interpret *text*; storing
    an invalid word is a fixture the product must classify. Returns the
    flag path.
    """
    dest = mode_flag_path(config_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding=DEFAULT_CHARSET)
    return dest


def read_mode_flag(config_dir: str | Path) -> str | None:
    """Return the stored level-flag contents, or ``None`` if it is absent.

    Maps a missing file to ``None`` (no flag has been stored). Any other
    outcome — permission error, not a regular file, undecodable bytes —
    raises :class:`HarnessError`. Never returns ``None`` to mean "the
    probe crashed".
    """
    src = mode_flag_path(config_dir)
    try:
        if not src.exists():
            return None
        if not src.is_file():
            raise HarnessError(f"mode flag exists but is not a regular file: {src}")
        return src.read_text(encoding=DEFAULT_CHARSET)
    except FileNotFoundError:
        return None
    except HarnessError:
        raise
    except UnicodeDecodeError as exc:
        raise HarnessError(f"mode flag {src} is not valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise HarnessError(f"cannot read mode flag {src}: {exc}") from exc


def ledger_paths(config_dir: str | Path) -> tuple[Path, ...]:
    """Return ledger files under *config_dir*, sorted by name.

    Raises :class:`HarnessError` if *config_dir* cannot be listed. An
    empty tuple means no ledger files were present — never a failed
    listing.
    """
    directory = Path(config_dir)
    try:
        if not directory.exists():
            return ()
        names = sorted(
            name
            for name in os.listdir(directory)
            if name == f"{LEDGER_PREFIX}.json" or name.startswith(f"{LEDGER_PREFIX}-")
        )
    except FileNotFoundError:
        return ()
    except OSError as exc:
        raise HarnessError(f"cannot list config dir {directory}: {exc}") from exc
    return tuple(directory / name for name in names)


def read_json_file(path: str | Path) -> Any:
    """Read *path* as a JSON value.

    Raises ``FileNotFoundError`` if the file does not exist. Raises
    :class:`HarnessError` if the file is not regular, is not UTF-8, or
    is not JSON. Never returns ``None`` to mean "the probe crashed".
    """
    text = read_file(path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HarnessError(f"{path} is not JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# JSON observation helpers (Rule 1: unclassified failure must raise)
# ---------------------------------------------------------------------------


def parse_json_value(text: str, *, source: str = "payload") -> Any:
    """Parse *text* as JSON.

    Raises:
        HarnessError: if *text* is empty or is not JSON. Never returns
            ``None`` to mean "the parse failed".
    """
    if text == "":
        raise HarnessError(f"{source} is empty; expected JSON")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        excerpt = text if len(text) <= 500 else text[:500] + "…"
        raise HarnessError(
            f"{source} is not JSON: {exc}; text={excerpt!r}"
        ) from exc


def parse_json_object(text: str, *, source: str = "payload") -> dict[str, Any]:
    """Parse *text* as a JSON object.

    Raises :class:`HarnessError` if the parse fails or the value is not
    an object. Never returns ``{}`` to mean "the parse failed".
    """
    value = parse_json_value(text, source=source)
    if not isinstance(value, dict):
        raise HarnessError(
            f"{source} JSON is {type(value).__name__}, not an object"
        )
    return value


def parse_json_object_or_empty(
    text: str, *, source: str = "payload"
) -> dict[str, Any] | None:
    """Parse *text* as a JSON object, or ``None`` when *text* is empty.

    Empty output is a documented product outcome on several hooks (level
    ``off``, an unflagged save). Non-empty text that is not a JSON
    object raises :class:`HarnessError` — never returns ``None`` to mean
    "the parse failed".
    """
    if text == "":
        return None
    return parse_json_object(text, source=source)


def encode_payload(obj: Mapping[str, Any]) -> bytes:
    """Serialize *obj* as UTF-8 JSON for hook stdin.

    Raises :class:`HarnessError` if *obj* cannot be serialized.
    """
    try:
        return json.dumps(obj, ensure_ascii=False).encode(DEFAULT_CHARSET)
    except (TypeError, ValueError) as exc:
        raise HarnessError(f"cannot encode hook payload as JSON: {exc}") from exc


def report_from_stdout(result: RunResult) -> dict[str, Any]:
    """Parse detector stdout as a JSON object (the structured report).

    Does not inspect :attr:`RunResult.returncode`. Raises
    :class:`HarnessError` if stdout is empty, is not JSON, or is not an
    object. Include stderr in the message so a traceback is visible.
    """
    try:
        return parse_json_object(result.stdout_text, source="detector stdout")
    except HarnessError as exc:
        stderr = result.stderr_text
        raise HarnessError(
            f"{exc}; exit={result.returncode}; stderr={stderr!r}"
        ) from exc


def structured_error(result: RunResult) -> str:
    """Return the ``error`` field from detector stderr JSON.

    The PRD's failing detector paths print a structured error object on
    the error stream. Maps only a JSON object that contains ``error``.
    Empty stderr, non-JSON stderr, or a JSON object without ``error``
    raises :class:`HarnessError` with the raw stderr in the message —
    never returns ``None`` or ``""`` to mean "no error object".
    """
    text = result.stderr_text
    try:
        obj = parse_json_object(text, source="detector stderr")
    except HarnessError as exc:
        raise HarnessError(
            f"{exc}; exit={result.returncode}; stderr={text!r}"
        ) from exc
    if "error" not in obj:
        raise HarnessError(
            f"detector stderr JSON has no 'error' field: {obj!r}; "
            f"exit={result.returncode}"
        )
    err = obj["error"]
    if not isinstance(err, str):
        raise HarnessError(
            f"detector stderr 'error' is {type(err).__name__}, not a string: "
            f"{err!r}"
        )
    return err


def report_metrics(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the ``_metrics`` object from a detector report.

    Raises :class:`HarnessError` if ``_metrics`` is missing or is not an
    object. Never returns ``{}`` to mean "metrics were absent".
    """
    if "_metrics" not in report:
        raise HarnessError("detector report has no _metrics object")
    metrics = report["_metrics"]
    if not isinstance(metrics, dict):
        raise HarnessError(
            f"detector _metrics is {type(metrics).__name__}, not an object"
        )
    return metrics


def report_findings(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return finding entries from a detector report (keys without a ``_`` prefix).

    An empty dict means the report contained no finding keys — that is a
    classified observation, not a failed parse.
    """
    if not isinstance(report, Mapping):
        raise HarnessError(
            f"detector report is {type(report).__name__}, not an object"
        )
    return {str(key): value for key, value in report.items() if not str(key).startswith("_")}


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
    input_bytes = _encode_stdin(stdin)
    child_env = dict(env) if env is not None else None

    print(
        f"[harness] run cwd={workdir!r} argv={list(argv)!r}",
        flush=True,
    )
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
    result = RunResult(
        returncode=completed.returncode,
        stdout=completed.stdout or b"",
        stderr=completed.stderr or b"",
        argv=tuple(str(a) for a in argv),
        cwd=workdir,
        environ=dict(child_env) if child_env is not None else dict(os.environ),
    )
    print(
        f"[harness] exit={result.returncode} "
        f"stdout_len={len(result.stdout)} stderr_len={len(result.stderr)}",
        flush=True,
    )
    if result.returncode != 0 and 0 < len(result.stderr) <= 2000:
        # Diagnostic only: do not use the strict decoder here, or a
        # non-UTF-8 error stream would hide the RunResult itself.
        preview = result.stderr.decode(DEFAULT_CHARSET, errors="replace")
        print(f"[harness] stderr={preview!r}", flush=True)
    return result


def invoke(
    args: Sequence[str] | None = None,
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: bytes | str | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    root: Path | None = None,
    isolate: bool = True,
) -> RunResult:
    """Invoke the detector command as ``python scripts/detect.py *args``.

    When *isolate* is true (the default) and *cwd* / *env* are omitted,
    the process runs in a fresh :func:`workspace` so it cannot see the
    caller's cwd, HOME, or plugin config. Pass ``isolate=False`` (and
    optionally *cwd* / *env*) to inherit the caller's process state, or
    to reuse a :class:`Workspace`.

    Returns a :class:`RunResult`. Does not raise on a non-zero product
    exit — that status is the observation.
    """
    script = detector_script(root=root)
    argv = [_python(), str(script), *_normalize_args(args)]

    if cwd is not None or env is not None or not isolate:
        return run_command(
            argv, cwd=cwd, env=env, stdin=stdin, timeout=timeout
        )

    with workspace(root=root) as ws:
        return run_command(
            argv, cwd=ws.path, env=ws.env, stdin=stdin, timeout=timeout
        )


def invoke_hook(
    entry: str,
    *,
    payload: Mapping[str, Any] | None = None,
    stdin: bytes | str | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    root: Path | None = None,
    isolate: bool = True,
) -> RunResult:
    """Fire a plugin hook: ``node hooks/<entry>.js`` with JSON on stdin.

    *entry* is a PRD host-event name or a ``hooks/*.js`` filename. When
    *payload* is given it is serialized as UTF-8 JSON and becomes stdin;
    *stdin* is then ignored. When both are omitted, stdin is empty
    (EOF), which the plugin treats as an empty object.

    Isolated calls point ``CLAUDE_PLUGIN_ROOT`` at the built repository
    and ``CLAUDE_CONFIG_DIR`` at a fresh config directory so a mode flag
    written by one call cannot leak into another.

    Returns a :class:`RunResult`. Does not raise on a non-zero product
    exit.
    """
    if payload is not None and stdin is not None:
        raise ValueError("pass payload or stdin, not both")
    stdin_bytes: bytes | str | None
    if payload is not None:
        stdin_bytes = encode_payload(payload)
    else:
        stdin_bytes = stdin

    def _run(
        child_cwd: str | Path | None,
        child_env: Mapping[str, str] | None,
    ) -> RunResult:
        node = node_executable(env=child_env)
        script = hook_script(entry, root=root)
        argv = [node, str(script)]
        return run_command(
            argv,
            cwd=child_cwd,
            env=child_env,
            stdin=stdin_bytes,
            timeout=timeout,
        )

    if cwd is not None or env is not None or not isolate:
        return _run(cwd, env)

    with workspace(root=root) as ws:
        return _run(ws.path, ws.env)
