# feature: F00
"""Shared machinery for driving the product through its public surfaces.

Suites import from this module (``from _harness import ...``). Importing it
performs no I/O, starts no processes, and opens no sockets. Process spawn,
filesystem writes, and environment replacement happen only when a caller
invokes a function or enters a context manager below.

The product is a pair of Oxlint JavaScript plugins plus a copy entry that
vendors them. It is not an importable Python package. Python tests reach
it by spawning Node against the copy script, and by spawning the host
linter (oxlint) with a configuration that registers one or both plugins
and enables named rules.

Surfaces
--------
* Copy entry — :func:`copy`. ``node skills/install-lint-policy/scripts/install.mjs``
  with caller-controlled arguments, cwd, and env. A relative destination
  and optional ``--force`` in; success text or a refusal on stderr out.
* Host linter — :func:`lint`. ``oxlint --config <generated> --format json``
  against caller-chosen source files. Plugins and rules are whatever the
  caller registers; this module does not decide which rules should fire.

Each isolated call starts from a whitelist of substrate environment
keys. Host-linter and Node side-channels that are not on that list are
dropped so a parent ``NODE_OPTIONS``, an oxlint config path, or any
other process binding the suite did not name cannot leak in.

A product non-zero exit is a classified outcome on :class:`RunResult`,
not a harness failure. Observation failures this module cannot classify
raise :class:`HarnessError`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

# Support module, not a test module. B-run may pass this file as a pytest
# target alongside every feature; without this marker pytest still imports
# a second copy and the suite no longer shares one harness identity.
__test__ = False


def _share_canonical_module() -> None:
    """Keep one module object when pytest also imports this file as a target.

    Combined-suite pytest names this path on the CLI. importlib may load it
    under a second name, or replace ``sys.modules['_harness']`` with a new
    object, while suites do ``from _harness import ...``. Both must be the
    first module so a pinned product root, host-modules root, and PluginSpec
    identity survive that run. A private alias keeps the first object even
    when the public name is overwritten before exec. importlib re-reads
    ``sys.modules[name]`` after exec, so replacing the extra name here is
    the identity.
    """
    canonical = "_harness"
    sentinel = "_harness_canonical"
    current = sys.modules.get(__name__)
    if current is None:
        return
    existing = sys.modules.get(sentinel) or sys.modules.get(canonical)
    if existing is not None and existing is not current:
        sys.modules[__name__] = existing
        sys.modules[canonical] = existing
        sys.modules[sentinel] = existing
        return
    sys.modules[canonical] = current
    sys.modules[sentinel] = current


_share_canonical_module()

# ---------------------------------------------------------------------------
# Public entry defaults (PRD: copy entry + host-linter plugins)
# ---------------------------------------------------------------------------

DEFAULT_CHARSET = "utf-8"
DEFAULT_TIMEOUT = 60.0

PRODUCT_ROOT_ENV = "PRODUCT_ROOT"
PRODUCT_NODE_ENV = "PRODUCT_NODE"
PRODUCT_OXLINT_ENV = "PRODUCT_OXLINT"
PRODUCT_COPY_ENV = "PRODUCT_COPY"

GENERIC_PLUGIN_NAME = "lint-policy"
EFFECT_PLUGIN_NAME = "lint-policy-effect"

DEFAULT_COPY_DEST = Path("tools") / "oxlint" / "lint-policy"
COPY_SCRIPT_RELPATH = (
    Path("skills") / "install-lint-policy" / "scripts" / "install.mjs"
)
GENERIC_ENTRY_RELPATH = Path("src") / "index.ts"
EFFECT_ENTRY_RELPATH = Path("src") / "effect" / "index.ts"
COPIED_GENERIC_ENTRY = Path("index.ts")
COPIED_EFFECT_ENTRY = Path("effect") / "index.ts"

OXLINT_BIN_RELPATH = Path("node_modules") / ".bin" / "oxlint"
NODE_MODULES_RELPATH = Path("node_modules")

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
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "HOME",
)

# TTY / pager / editor / proxy / Node / linter side-channels stripped
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
    "OXLINT_CONFIG",
    "ESLINT_USE_FLAT_CONFIG",
)

# Host built-in categories turned off in a generated config so a snippet
# is observed through the plugins the caller registered, not through
# oxlint's default correctness rules.
_HOST_CATEGORIES_OFF = {
    "correctness": "off",
    "suspicious": "off",
    "pedantic": "off",
    "perf": "off",
    "style": "off",
    "restriction": "off",
    "nursery": "off",
}



# ---------------------------------------------------------------------------
# Errors / result types
# ---------------------------------------------------------------------------


class HarnessError(RuntimeError):
    """Raised when an observation cannot be classified.

    Used for a missing interpreter, copy script, or oxlint binary; a JSON
    probe that is not well-formed; a workspace path that escapes its
    root; a timeout; and I/O failures that are not a documented product
    outcome. Never used to mean "the product returned a non-zero exit
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

    @property
    def combined_text(self) -> str:
        """Stdout then stderr, each decoded as UTF-8."""
        return self.stdout_text + self.stderr_text


@dataclass(frozen=True)
class Diagnostic:
    """One host-linter finding parsed from JSON output.

    ``rule`` is the finding's ``code`` exactly as the host's JSON report
    gives it (for a plugin finding ``<plugin>(<rule>)``, for example
    ``lint-policy(no-array-filter-map)``), or ``""`` when the host gives no
    code. ``line`` / ``column`` are the 1-based position of the first
    label's span. A host parse failure still produces a Diagnostic; it is
    not turned into ``None``. ``raw`` is the original JSON object.
    """

    rule: str
    message: str
    severity: str
    filename: str
    line: int | None
    column: int | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PluginSpec:
    """One JavaScript plugin registration for the host-linter config."""

    name: str
    specifier: str

    def as_config(self) -> dict[str, str]:
        return {"name": self.name, "specifier": self.specifier}


@dataclass
class Workspace:
    """Ephemeral work directory plus the isolated environment bound to it.

    ``path`` is the working directory for copy and lint. ``home`` is used
    as ``HOME`` so ``~`` expansion cannot see the caller's home. ``root``
    is the built repository root used to locate the copy script, the
    canonical plugin entries, and oxlint. Trees under ``path`` and
    ``home`` are removed when the allocating context exits; the product
    tree is not.
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

    def exists(self, relpath: str | Path) -> bool:
        """Return whether *relpath* exists under this workspace.

        ``False`` means the path is absent. Raises :class:`HarnessError`
        on an ``OSError`` other than classified absence.
        """
        return path_exists(self.resolve(relpath))

    def snapshot(self, relpath: str | Path = ".") -> dict[str, bytes]:
        """Return a map of relative posix paths to file bytes under *relpath*."""
        return snapshot_files(self.resolve(relpath))

    def copy(
        self,
        args: Sequence[str] | None = None,
        *,
        timeout: float | None = DEFAULT_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
        root: Path | None = None,
    ) -> RunResult:
        """Run the copy entry with this workspace as cwd and env.

        Does not raise on a non-zero product exit.
        """
        env = _apply_updates(self.env, env_updates)
        return copy(
            args,
            cwd=cwd if cwd is not None else self.path,
            env=env,
            timeout=timeout,
            root=root if root is not None else self.root,
            isolate=False,
        )

    def lint(
        self,
        files: Sequence[str | Path],
        *,
        plugins: Sequence[PluginSpec | Mapping[str, str]] | None = None,
        rules: Mapping[str, Any] | None = None,
        config: str | Path | None = None,
        fix: bool = False,
        extra_args: Sequence[str] | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
        root: Path | None = None,
    ) -> RunResult:
        """Run the host linter with this workspace as cwd and env.

        Relative *files* resolve under this workspace. Does not raise on
        a non-zero product exit.
        """
        env = _apply_updates(self.env, env_updates)
        resolved: list[str] = []
        for item in files:
            path = Path(item)
            if path.is_absolute():
                resolved.append(str(path))
            else:
                resolved.append(str(self.resolve(path)))
        return lint(
            resolved,
            plugins=plugins,
            rules=rules,
            config=config,
            fix=fix,
            extra_args=extra_args,
            cwd=cwd if cwd is not None else self.path,
            env=env,
            timeout=timeout,
            root=root if root is not None else self.root,
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


# ---------------------------------------------------------------------------
# Paths / discovery
# ---------------------------------------------------------------------------


# First resolved product root this process observed. Combined-suite runs
# share one pytest process; a later test that leaves cwd on a torn-down
# workspace must not make copy/lint look for the product under that path.
_PINNED_REPO_ROOT: Path | None = None

# Host-linter tree (node_modules + oxlint). Distinct from the source overlay
# when judge-profile copies the repo without node_modules.
_PINNED_MODULES_ROOT: Path | None = None

# Prepared product tree in the recipe image. Judge-profile wipes /app and
# copies a source overlay; this path is a source copy and often has no
# host modules. The env-warm install lives under ``_IMAGE_WARM_ROOT``.
_IMAGE_PRODUCT_ROOT = Path("/opt/codingbench/repo")
_IMAGE_WARM_ROOT = Path("/opt/cb-warm")
_PNPM_STORE_DIR = Path("/opt/pnpm-store")
_HOST_LINTER_CACHE = Path("/tmp/cb-host-linter")
_LOCKFILE_NAME = "pnpm-lock.yaml"
_PACKAGE_JSON_NAME = "package.json"


def _has_host_modules(root: Path) -> bool:
    """True when *root* has a node_modules the host linter can use."""
    modules = root / NODE_MODULES_RELPATH
    try:
        if not modules.is_dir():
            return False
    except OSError:
        return False
    try:
        if (modules / ".bin" / "oxlint").is_file():
            return True
    except OSError:
        return False
    try:
        return (modules / "@oxlint").is_dir()
    except OSError:
        return False


def _modules_root_candidates(source: Path) -> tuple[Path, ...]:
    seen: set[Path] = set()
    ordered: list[Path] = []

    def _add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        if resolved in seen:
            return
        seen.add(resolved)
        ordered.append(resolved)

    _add(source)
    node_path = os.environ.get("NODE_PATH", "")
    for part in node_path.split(os.pathsep):
        if not part:
            continue
        entry = Path(part)
        _add(entry.parent if entry.name == "node_modules" else entry)
    for part in os.environ.get("PATH", "").split(os.pathsep):
        if not part:
            continue
        entry = Path(part)
        if entry.name == ".bin" and entry.parent.name == "node_modules":
            _add(entry.parent.parent)
    found = shutil.which("oxlint")
    if found:
        loc = Path(found)
        try:
            loc = loc.resolve()
        except OSError:
            loc = Path(found)
        if loc.parent.name == ".bin" and loc.parent.parent.name == "node_modules":
            _add(loc.parent.parent.parent)
    # Env-warm install (pnpm) lands here. /opt/codingbench/repo is a source
    # copy and typically has no node_modules after judge-profile wipes /app.
    _add(_IMAGE_WARM_ROOT)
    try:
        if _IMAGE_WARM_ROOT.is_dir():
            for child in _IMAGE_WARM_ROOT.iterdir():
                if child.is_dir():
                    _add(child)
    except OSError:
        pass
    _add(_IMAGE_PRODUCT_ROOT)
    _add(_HOST_LINTER_CACHE)
    return tuple(ordered)


def _pnpm_executable() -> str:
    found = shutil.which("pnpm")
    if found:
        return found
    for candidate in (
        Path("/usr/local/bin/pnpm"),
        Path("/opt/nodejs/bin/pnpm"),
    ):
        try:
            if candidate.is_file():
                return str(candidate.resolve())
        except OSError:
            continue
    raise FileNotFoundError(
        "pnpm executable not found on PATH or under /opt/nodejs; "
        "cannot materialize host-linter modules from the overlay lockfile"
    )


def _copy_overlay_lockfile(source: Path, dest: Path) -> None:
    """Copy the overlay's install manifests into *dest*.

    Raises:
        HarnessError: when a required manifest is missing or cannot be copied.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for name in (_PACKAGE_JSON_NAME, _LOCKFILE_NAME):
        src = source / name
        try:
            if not src.is_file():
                raise FileNotFoundError(f"file does not exist: {src}")
        except FileNotFoundError:
            raise HarnessError(
                f"overlay lockfile materialize needs {name} at {src}"
            ) from None
        except OSError as exc:
            raise HarnessError(f"cannot stat {src}: {exc}") from exc
        try:
            shutil.copy2(src, dest / name)
        except OSError as exc:
            raise HarnessError(f"cannot copy {src} -> {dest}: {exc}") from exc
    for name in (".npmrc", "pnpm-workspace.yaml", ".pnpmfile.cjs"):
        src = source / name
        try:
            present = src.is_file()
        except OSError as exc:
            raise HarnessError(f"cannot stat {src}: {exc}") from exc
        if not present:
            continue
        try:
            shutil.copy2(src, dest / name)
        except OSError as exc:
            raise HarnessError(f"cannot copy {src} -> {dest}: {exc}") from exc


def materialize_host_modules(source: Path) -> Path:
    """Install host-linter modules from *source*'s lockfile into a cache tree.

    Judge-profile copies the overlay without ``node_modules``. The image
    product path is a source copy; env-warm modules may be absent after
    ``/app`` is wiped. This uses the overlay's own lockfile against the
    recipe pnpm store (no registry fetch). Does not rewrite product files
    under *source*.

    Raises:
        HarnessError: when the lockfile is missing, pnpm is missing, or
            the install does not produce a usable host-linter tree.
    """
    cache = _HOST_LINTER_CACHE
    if _has_host_modules(cache):
        print(f"[harness] host-linter cache already present at {cache}", flush=True)
        return cache.resolve()
    _copy_overlay_lockfile(source, cache)
    try:
        pnpm = _pnpm_executable()
    except FileNotFoundError as exc:
        raise HarnessError(str(exc)) from exc
    store = _PNPM_STORE_DIR
    argv = [
        pnpm,
        "install",
        "--frozen-lockfile",
        "--prefer-offline",
        "--offline",
        "--store-dir",
        str(store),
        "--config.confirmModulesPurge=false",
    ]
    print(
        f"[harness] materialize host-linter cwd={cache} argv={argv!r}",
        flush=True,
    )
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cache),
            env=dict(os.environ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(
            f"pnpm install timed out materializing host-linter modules at {cache}"
        ) from exc
    except OSError as exc:
        raise HarnessError(
            f"cannot run pnpm install for host-linter modules: {exc}"
        ) from exc
    stdout = completed.stdout or b""
    stderr = completed.stderr or b""
    if completed.returncode != 0:
        raise HarnessError(
            "pnpm install failed materializing host-linter modules from the "
            f"overlay lockfile; exit={completed.returncode}; "
            f"stdout={stdout!r}; stderr={stderr!r}"
        )
    if not _has_host_modules(cache):
        raise HarnessError(
            "pnpm install exited 0 but host-linter modules are still missing "
            f"at {cache / NODE_MODULES_RELPATH}; "
            f"stdout={stdout!r}; stderr={stderr!r}"
        )
    print(
        f"[harness] materialized host-linter at {cache} "
        f"stdout_len={len(stdout)} stderr_len={len(stderr)}",
        flush=True,
    )
    return cache.resolve()


def host_modules_root(*, root: Path | None = None) -> Path:
    """Return the tree whose ``node_modules`` holds the host linter.

    The pytest cwd is the product source. An isolated judge overlay may
    copy that source without ``node_modules``. Discovery order: the
    overlay itself, PATH/NODE_PATH, the env-warm tree, the image product
    copy. If none of those has host modules, materialize them from the
    overlay's own lockfile against the recipe pnpm store.

    Raises:
        HarnessError: when materialize is required and cannot produce a
            usable host-linter tree. Never returns a hollow overlay and
            pretends the host linter is present.
    """
    global _PINNED_MODULES_ROOT
    source = (root if root is not None else repo_root()).resolve()
    if _PINNED_MODULES_ROOT is not None and _has_host_modules(_PINNED_MODULES_ROOT):
        return _PINNED_MODULES_ROOT
    if _has_host_modules(source):
        _PINNED_MODULES_ROOT = source
        return source
    chosen: Path | None = None
    for candidate in _modules_root_candidates(source):
        if _has_host_modules(candidate):
            chosen = candidate
            break
    if chosen is None:
        chosen = materialize_host_modules(source)
    _PINNED_MODULES_ROOT = chosen
    print(f"[harness] host-linter root={chosen}", flush=True)
    return chosen


def repo_root() -> Path:
    """Return the product source root (copy entry + plugin sources).

    Tests run with the repository root as the pytest process cwd. Returns
    ``Path.cwd()`` resolved; does not search the filesystem for a different
    source. ``PRODUCT_ROOT`` overrides the cwd when set. After the first
    resolution, later calls reuse that path unless ``PRODUCT_ROOT`` is set,
    so a leaked chdir cannot retarget the product tree.

    Host-linter binaries live under :func:`host_modules_root`, which may
    be a different tree when the cwd overlay has no ``node_modules``.
    """
    global _PINNED_REPO_ROOT
    override = os.environ.get(PRODUCT_ROOT_ENV)
    if override:
        resolved = Path(override).expanduser().resolve()
        _PINNED_REPO_ROOT = resolved
        return resolved
    if _PINNED_REPO_ROOT is not None:
        return _PINNED_REPO_ROOT
    resolved = Path.cwd().resolve()
    _PINNED_REPO_ROOT = resolved
    return resolved


def node_executable(*, env: Mapping[str, str] | None = None) -> str:
    """Locate the Node interpreter used to run the copy entry.

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
            "node executable not found on PATH; the copy entry requires Node.js"
        )
    return found


def oxlint_executable(
    *,
    root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Locate the host-linter executable.

    Resolution order:
      1. ``PRODUCT_OXLINT`` environment variable, if set.
      2. ``<root>/node_modules/.bin/oxlint``.
      3. ``oxlint`` on ``PATH``.

    Raises:
        FileNotFoundError: when no executable exists at the resolved path.
    """
    override = os.environ.get(PRODUCT_OXLINT_ENV)
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"{PRODUCT_OXLINT_ENV} does not point to a file: {path}"
            )
        return str(path.resolve())

    base = root if root is not None else repo_root()
    bundled = (host_modules_root(root=base) / OXLINT_BIN_RELPATH).resolve()
    if bundled.is_file():
        return str(bundled)

    search_path = (env or os.environ).get("PATH")
    found = shutil.which("oxlint", path=search_path)
    if found is None:
        raise FileNotFoundError(
            f"oxlint executable not found at {bundled} or on PATH; "
            "the runner must expose oxlint in the built tree"
        )
    return found


def copy_script(*, root: Path | None = None) -> Path:
    """Locate the skill-copy entry script and return its absolute path.

    Resolution order:
      1. ``PRODUCT_COPY`` environment variable, if set.
      2. ``<root>/skills/install-lint-policy/scripts/install.mjs``.

    Raises:
        FileNotFoundError: when no regular file exists at the resolved path.
    """
    override = os.environ.get(PRODUCT_COPY_ENV)
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(
                f"{PRODUCT_COPY_ENV} does not point to a file: {path}"
            )
        return path

    base = root if root is not None else repo_root()
    path = (Path(base) / COPY_SCRIPT_RELPATH).resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"copy entry not found at {path}; "
            "the runner must expose skills/install-lint-policy/scripts/install.mjs"
        )
    return path


def generic_plugin_path(*, root: Path | None = None) -> Path:
    """Absolute path of the canonical generic plugin entry (``src/index.ts``).

    Raises:
        FileNotFoundError: when the entry is not a regular file.
    """
    base = root if root is not None else repo_root()
    path = (Path(base) / GENERIC_ENTRY_RELPATH).resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"generic plugin entry not found at {path}; "
            "the runner must expose src/index.ts in the built tree"
        )
    return path


def effect_plugin_path(*, root: Path | None = None) -> Path:
    """Absolute path of the canonical Effect plugin entry.

    Raises:
        FileNotFoundError: when the entry is not a regular file.
    """
    base = root if root is not None else repo_root()
    path = (Path(base) / EFFECT_ENTRY_RELPATH).resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"Effect plugin entry not found at {path}; "
            "the runner must expose src/effect/index.ts in the built tree"
        )
    return path


def copied_generic_path(dest: str | Path) -> Path:
    """Generic plugin entry under a vendored destination directory."""
    return Path(dest).resolve() / COPIED_GENERIC_ENTRY


def copied_effect_path(dest: str | Path) -> Path:
    """Effect plugin entry under a vendored destination directory."""
    return Path(dest).resolve() / COPIED_EFFECT_ENTRY


def generic_plugin(
    *,
    specifier: str | Path | None = None,
    root: Path | None = None,
) -> PluginSpec:
    """Registration for the generic plugin.

    *specifier* defaults to the canonical ``src/index.ts`` entry in the
    built tree. Pass a copied-tree entry to lint through a vendored copy.
    """
    path = Path(specifier) if specifier is not None else generic_plugin_path(root=root)
    return PluginSpec(name=GENERIC_PLUGIN_NAME, specifier=str(Path(path).resolve()))


def effect_plugin(
    *,
    specifier: str | Path | None = None,
    root: Path | None = None,
) -> PluginSpec:
    """Registration for the opt-in Effect plugin.

    *specifier* defaults to the canonical ``src/effect/index.ts`` entry.
    """
    path = Path(specifier) if specifier is not None else effect_plugin_path(root=root)
    return PluginSpec(name=EFFECT_PLUGIN_NAME, specifier=str(Path(path).resolve()))


def node_modules_path(*, root: Path | None = None) -> Path:
    """Return the host ``node_modules`` directory.

    When the source overlay has no ``node_modules`` (judge-profile copies
    omit it), this is the env-warm tree or a lockfile-materialized cache.
    Does not require that the directory exists — a missing tree is a
    classified gap after materialize has already been attempted.
    """
    return (host_modules_root(root=root) / NODE_MODULES_RELPATH).resolve()


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
    """Build an environment that does not inherit the caller's home/linter state.

    Copies a whitelist from *base* (or ``os.environ``), points ``HOME`` at
    *home*, prepends the host-linter ``node_modules/.bin`` to ``PATH``, points
    ``NODE_PATH`` at that ``node_modules`` so a copied plugin can still
    resolve ``@oxlint/plugins``, unsets host / Node keys that would couple
    a child to the parent, and applies *updates* last (``None`` unsets).
    Does not mutate ``os.environ``.

    Returns a new ``dict``.
    """
    home_path = Path(home).resolve()
    product_root = (root if root is not None else repo_root()).resolve()
    modules_root = host_modules_root(root=product_root)
    home_path.mkdir(parents=True, exist_ok=True)

    source = base if base is not None else os.environ
    env: dict[str, str] = {}
    for key in _KEEP_ENV_KEYS:
        if key in source:
            env[key] = source[key]
    for key in _ISOLATE_UNSET:
        env.pop(key, None)

    env["HOME"] = str(home_path)
    env.setdefault("LANG", _DEFAULT_LOCALE)
    env.setdefault("LC_ALL", _DEFAULT_LOCALE)

    bin_dir = str((modules_root / OXLINT_BIN_RELPATH).parent)
    path_value = env.get("PATH", "")
    path_parts = [part for part in path_value.split(os.pathsep) if part]
    if bin_dir not in path_parts:
        env["PATH"] = os.pathsep.join([bin_dir, *path_parts]) if path_parts else bin_dir

    modules = node_modules_path(root=product_root)
    env["NODE_PATH"] = str(modules)

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
    try:
        env = isolated_environ(home, updates=updates, root=product_root)
        yield Workspace(
            path=work,
            home=home,
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


def path_exists(path: str | Path) -> bool:
    """Return whether *path* exists.

    ``False`` means the path is absent. Raises :class:`HarnessError` on
    an ``OSError`` other than classified absence — never treats a
    permission or I/O failure as "missing".
    """
    src = Path(path)
    try:
        return src.exists()
    except OSError as exc:
        raise HarnessError(f"cannot stat {src}: {exc}") from exc


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

    ``False`` means the path is absent or is not a directory. Raises
    :class:`HarnessError` on an ``OSError`` other than classified
    absence.
    """
    src = Path(path)
    try:
        return src.is_dir()
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


def file_digest(path: str | Path) -> str:
    """Return the SHA-256 hex digest of a regular file.

    Raises ``FileNotFoundError`` if the file does not exist. Never
    returns an empty string to mean "missing".
    """
    data = read_bytes(path)
    return hashlib.sha256(data).hexdigest()


def snapshot_files(root: str | Path) -> dict[str, bytes]:
    """Return a map of relative posix paths to file bytes under *root*.

    Raises ``FileNotFoundError`` if *root* does not exist. Raises
    :class:`HarnessError` if *root* exists but is not a directory, or if
    the tree cannot be listed. An empty dict means the directory
    contained no files — never a failed walk.
    """
    base = Path(root)
    try:
        if not base.exists():
            raise FileNotFoundError(f"directory does not exist: {base}")
        if not base.is_dir():
            raise HarnessError(f"path exists but is not a directory: {base}")
    except FileNotFoundError:
        raise
    except HarnessError:
        raise
    except OSError as exc:
        raise HarnessError(f"cannot stat {base}: {exc}") from exc

    collected: dict[str, bytes] = {}
    try:
        for dirpath, _dirnames, filenames in os.walk(base, followlinks=False):
            for name in filenames:
                src = Path(dirpath) / name
                if not src.is_file():
                    continue
                rel = src.relative_to(base).as_posix()
                collected[rel] = src.read_bytes()
    except OSError as exc:
        raise HarnessError(f"cannot walk {base}: {exc}") from exc
    return collected


def list_files(root: str | Path) -> tuple[str, ...]:
    """Return sorted relative posix paths of files under *root*.

    Raises the same errors as :func:`snapshot_files`. An empty tuple
    means no files were present.
    """
    return tuple(sorted(snapshot_files(root)))


def tree_digest(root: str | Path) -> str:
    """Return a SHA-256 hex digest of file paths and contents under *root*.

    Raises ``FileNotFoundError`` if *root* does not exist. Two trees
    with the same relative files and bytes compare equal.
    """
    snapshot = snapshot_files(root)
    hasher = hashlib.sha256()
    for rel in sorted(snapshot):
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(snapshot[rel])
        hasher.update(b"\0")
    return hasher.hexdigest()


# ---------------------------------------------------------------------------
# Host-linter configuration
# ---------------------------------------------------------------------------


def _plugin_as_config(plugin: PluginSpec | Mapping[str, str]) -> dict[str, str]:
    # Duck-type as_config: a second import of this module (pytest collecting
    # _harness.py as a test path) yields a distinct PluginSpec class, and
    # isinstance against this copy would then fall through and crash.
    as_config = getattr(plugin, "as_config", None)
    if callable(as_config):
        return as_config()
    try:
        name = plugin.get("name")  # type: ignore[union-attr]
        specifier = plugin.get("specifier")  # type: ignore[union-attr]
    except AttributeError as exc:
        raise HarnessError(
            f"plugin registration requires 'name' and 'specifier', got {plugin!r}"
        ) from exc
    if not name or not specifier:
        raise HarnessError(
            f"plugin registration requires 'name' and 'specifier', got {plugin!r}"
        )
    return {"name": str(name), "specifier": str(specifier)}


def make_oxlint_config(
    *,
    plugins: Sequence[PluginSpec | Mapping[str, str]] | None = None,
    rules: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a host-linter config that registers *plugins* and *rules*.

    Built-in host categories are turned off so a snippet is observed
    through the plugins the caller named. Does not interpret rule names
    or options.
    """
    config: dict[str, Any] = {
        "plugins": [],
        "categories": dict(_HOST_CATEGORIES_OFF),
        "jsPlugins": [_plugin_as_config(item) for item in (plugins or ())],
        "rules": dict(rules) if rules is not None else {},
    }
    if extra:
        for key, value in extra.items():
            config[key] = value
    return config


def write_oxlint_config(
    path: str | Path,
    *,
    plugins: Sequence[PluginSpec | Mapping[str, str]] | None = None,
    rules: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> Path:
    """Write a host-linter JSON config to *path* and return the resolved path."""
    config = make_oxlint_config(plugins=plugins, rules=rules, extra=extra)
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding=DEFAULT_CHARSET,
    )
    return dest.resolve()


def rule_key(plugin: str, rule: str) -> str:
    """Return the host-linter rule id ``<plugin>/<rule>``.

    If *rule* is already qualified with a slash, it is returned unchanged
    so a caller can pass either a local name or a full id.
    """
    if "/" in rule:
        return rule
    return f"{plugin}/{rule}"


# ---------------------------------------------------------------------------
# JSON / diagnostic observation (Rule 1: unclassified failure must raise)
# ---------------------------------------------------------------------------


def parse_json_value(text: str, *, source: str = "payload") -> Any:
    """Parse *text* as one JSON document.

    The whole text must be the document. Leading or trailing non-JSON text
    is not skipped: the Interface Contract states that the host's standard
    output under ``--format json`` is the JSON report and nothing else.

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


def _rule_code(raw: Mapping[str, Any]) -> str:
    """The finding's ``code`` string; ``""`` when the host gives none.

    A host parse failure carries no ``code``. Plugin findings carry
    ``<plugin>(<rule>)`` (Interface Contract, "Observing findings").
    """
    code = raw.get("code")
    if code is None:
        return ""
    if not isinstance(code, str):
        raise HarnessError(f"finding 'code' is {type(code).__name__}, not a string: {raw!r}")
    return code


def _severity_of(raw: Mapping[str, Any]) -> str:
    value = raw.get("severity")
    if value is None:
        return ""
    return str(value)


def _filename_of(raw: Mapping[str, Any]) -> str:
    value = raw.get("filename")
    return value if isinstance(value, str) else ""


def _line_column(raw: Mapping[str, Any]) -> tuple[int | None, int | None]:
    """1-based ``line`` and ``column`` of the first label's ``span``."""
    labels = raw.get("labels")
    if not isinstance(labels, list) or not labels:
        return None, None
    first = labels[0]
    span = first.get("span") if isinstance(first, Mapping) else None
    if not isinstance(span, Mapping):
        return None, None
    line = span.get("line")
    column = span.get("column")
    line_n = line if isinstance(line, int) and not isinstance(line, bool) else None
    col_n = column if isinstance(column, int) and not isinstance(column, bool) else None
    return line_n, col_n


def _diagnostic_from_object(raw: Mapping[str, Any]) -> Diagnostic:
    rule = _rule_code(raw)
    message = raw.get("message")
    if message is None:
        message = ""
    elif not isinstance(message, str):
        message = str(message)
    if not rule and not message:
        raise HarnessError(
            f"diagnostic JSON has neither a rule code nor a message: {raw!r}"
        )
    line, column = _line_column(raw)
    return Diagnostic(
        rule=rule,
        message=message,
        severity=_severity_of(raw),
        filename=_filename_of(raw),
        line=line,
        column=column,
        raw=dict(raw),
    )


def _diagnostics_from_value(value: Any, *, source: str) -> list[Diagnostic]:
    """Read the host report: an object whose ``diagnostics`` is a list of findings."""
    if not isinstance(value, Mapping):
        raise HarnessError(
            f"{source} JSON is {type(value).__name__}, not the report object"
        )
    if "diagnostics" not in value:
        raise HarnessError(
            f"{source} JSON object has no 'diagnostics' field: keys={sorted(value)!r}"
        )
    inner = value["diagnostics"]
    if not isinstance(inner, list):
        raise HarnessError(
            f"{source}.diagnostics is {type(inner).__name__}, not a list"
        )
    found: list[Diagnostic] = []
    for item in inner:
        if not isinstance(item, Mapping):
            raise HarnessError(
                f"{source} diagnostic is {type(item).__name__}, not an object"
            )
        found.append(_diagnostic_from_object(item))
    return found


def lint_json(result: RunResult) -> Any:
    """Parse host-linter stdout as JSON.

    Does not inspect :attr:`RunResult.returncode`. Empty stdout, non-JSON
    stdout, or undecodable bytes raise :class:`HarnessError` with stderr
    in the message — never returns ``[]`` or ``None`` to mean "the
    probe crashed".
    """
    try:
        text = result.stdout_text
    except HarnessError as exc:
        raise HarnessError(
            f"{exc}; exit={result.returncode}; stderr={result.stderr!r}"
        ) from exc
    if text.strip() == "":
        stderr = result.stderr_text
        raise HarnessError(
            "host-linter stdout is empty; expected JSON diagnostics; "
            f"exit={result.returncode}; stderr={stderr!r}"
        )
    try:
        return parse_json_value(text, source="oxlint stdout")
    except HarnessError as exc:
        stderr = result.stderr_text
        raise HarnessError(
            f"{exc}; exit={result.returncode}; stderr={stderr!r}"
        ) from exc


def diagnostics(result: RunResult) -> tuple[Diagnostic, ...]:
    """Return host-linter findings from a :func:`lint` result.

    An empty tuple means the JSON payload contained no findings — that
    is a classified observation, not a failed parse. A crash, empty
    stdout, or a payload this helper cannot read as diagnostics raises
    :class:`HarnessError`.
    """
    payload = lint_json(result)
    try:
        found = _diagnostics_from_value(payload, source="oxlint stdout")
    except HarnessError as exc:
        raise HarnessError(
            f"{exc}; exit={result.returncode}; stderr={result.stderr_text!r}"
        ) from exc
    return tuple(found)


def diagnostics_for(
    findings: Sequence[Diagnostic],
    plugin: str,
) -> tuple[Diagnostic, ...]:
    """Return findings whose rule is published under *plugin*.

    Matches the host code ``<plugin>(<rule>)`` only. ``lint-policy`` does
    not match ``lint-policy-effect``. An empty tuple means none of the findings
    belonged to that plugin — not a failed filter.
    """
    prefix = f"{plugin}("
    return tuple(
        item
        for item in findings
        if item.rule.startswith(prefix) and item.rule.endswith(")")
    )


def rule_ids(findings: Sequence[Diagnostic]) -> tuple[str, ...]:
    """Return the rule ids from *findings*, in encounter order.

    Empty strings (a host finding with no code) are kept; they are
    classified observations, not parse failures.
    """
    return tuple(item.rule for item in findings)


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
        preview = result.stderr.decode(DEFAULT_CHARSET, errors="replace")
        print(f"[harness] stderr={preview!r}", flush=True)
    return result


def copy(
    args: Sequence[str] | None = None,
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: bytes | str | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    root: Path | None = None,
    isolate: bool = True,
) -> RunResult:
    """Invoke the skill copy as ``node install.mjs *args``.

    *args* are passed through (a relative destination and/or ``--force``).
    When *isolate* is true (the default) and *cwd* / *env* are omitted,
    the process runs in a fresh :func:`workspace` so it cannot see the
    caller's cwd or HOME. Pass ``isolate=False`` (and optionally *cwd*
    / *env*) to inherit the caller's process state, or to reuse a
    :class:`Workspace`.

    Returns a :class:`RunResult`. Does not raise on a non-zero product
    exit — that status is the observation.
    """
    script = copy_script(root=root)

    def _run(
        child_cwd: str | Path | None,
        child_env: Mapping[str, str] | None,
    ) -> RunResult:
        node = node_executable(env=child_env)
        argv = [node, str(script), *_normalize_args(args)]
        return run_command(
            argv,
            cwd=child_cwd,
            env=child_env,
            stdin=stdin,
            timeout=timeout,
        )

    if cwd is not None or env is not None or not isolate:
        return _run(cwd, env)

    with workspace(root=root) as ws:
        return _run(ws.path, ws.env)


def lint(
    files: Sequence[str | Path],
    *,
    plugins: Sequence[PluginSpec | Mapping[str, str]] | None = None,
    rules: Mapping[str, Any] | None = None,
    config: str | Path | None = None,
    fix: bool = False,
    extra_args: Sequence[str] | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    root: Path | None = None,
    isolate: bool = True,
) -> RunResult:
    """Invoke the host linter as ``oxlint --config <cfg> --format json *files``.

    *plugins* and *rules* are written into a generated config unless
    *config* is given. Built-in host categories are off in a generated
    config. Always requests JSON output so :func:`diagnostics` can
    classify findings. ``--no-ignore`` and ``--disable-nested-config``
    keep a parent ignore file or the product's own oxlintrc from
    changing the observation.

    When *isolate* is true (the default) and *cwd* / *env* are omitted,
    the process runs in a fresh :func:`workspace`. Source *files* are
    not copied; pass absolute paths, or reuse a :class:`Workspace`.

    Returns a :class:`RunResult`. Does not raise on a non-zero product
    exit.
    """
    paths = [str(Path(item)) for item in files]
    if not paths:
        raise ValueError("lint requires at least one source path")

    def _run(
        child_cwd: str | Path | None,
        child_env: Mapping[str, str] | None,
        config_path: str,
    ) -> RunResult:
        oxlint = oxlint_executable(root=root, env=child_env)
        argv = [
            oxlint,
            "--config",
            config_path,
            "--format",
            "json",
            "--no-ignore",
            "--disable-nested-config",
            "--threads=1",
        ]
        if fix:
            argv.append("--fix")
        argv.extend(_normalize_args(extra_args))
        argv.extend(paths)
        return run_command(
            argv,
            cwd=child_cwd,
            env=child_env,
            timeout=timeout,
        )

    def _with_config(
        child_cwd: str | Path | None,
        child_env: Mapping[str, str] | None,
    ) -> RunResult:
        if config is not None:
            config_path = str(Path(config).resolve())
            if not Path(config_path).is_file():
                raise FileNotFoundError(
                    f"host-linter config is not a file: {config_path}"
                )
            return _run(child_cwd, child_env, config_path)
        cfg_dir = Path(tempfile.mkdtemp(prefix="harness-oxlint-cfg-"))
        try:
            written = write_oxlint_config(
                cfg_dir / "oxlint.json",
                plugins=plugins,
                rules=rules,
            )
            return _run(child_cwd, child_env, str(written))
        finally:
            shutil.rmtree(cfg_dir, ignore_errors=True)

    if cwd is not None or env is not None or not isolate:
        return _with_config(cwd, env)

    with workspace(root=root) as ws:
        return _with_config(ws.path, ws.env)
