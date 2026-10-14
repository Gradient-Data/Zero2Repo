# feature: F00
"""Shared machinery for driving the product through its public surface.

Suites import from this module (``from _harness import ...``). Importing it
performs no I/O, starts no processes, and opens no sockets. Compilation,
process spawn, filesystem writes, and environment replacement happen only
when a caller invokes a function or enters a context manager below.

The product is a C11 navigation library with a ctypes Python package and
dataset-replay programs. It is not a network service. Python tests reach
the library by:

* compiling a short C probe against the recipe-built shared object and
  running that probe as a child process (the C instance API);
* running a child interpreter with the package on ``PYTHONPATH`` (the
  Python INS wrapper, navigator, and YAML runner);
* spawning the Python or C dataset-replay program on a directory of CSV
  streams plus ``config.yaml``.

This module knows how to reach those entries. It does not know what any
feature expects from them.

Surfaces
--------
* Library probe — :func:`invoke` / :func:`compile_probe`. Caller supplies
  source that includes the public headers under ``src/`` and links the
  recipe-built shared library. Stdin, argv, cwd, and environment of the
  resulting binary are caller-controlled. Each probe is a fresh
  process, so filter state inside one probe cannot leak into another.
* Python child — :func:`run_python` / :func:`run_runner`. A separate
  interpreter with the package directory on ``PYTHONPATH``. The harness
  does not import the product in this process.
* Replay — :func:`run_replay` (Python replay program) and
  :func:`run_c_replay` (C regression harness). ``make replay`` writes
  ``build/replay``.

Missing substrate (no public header, no built library, no compiler, no
replay program) raises :class:`FileNotFoundError` or :class:`HarnessError`.
A product non-zero exit recorded on :class:`RunResult` is a classified
outcome, not a harness failure. Observation failures this module cannot
classify raise :class:`HarnessError`.
"""

from __future__ import annotations

import atexit
import hashlib
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, Sequence

# ---------------------------------------------------------------------------
# Reproducible runtime randomisation
# ---------------------------------------------------------------------------
#
# Scenario parameters (sites, offsets, headings, unknown-key tokens) are drawn
# at runtime so a fixed expected table cannot be memorised. Every draw comes
# from one RNG. The session seed is printed in the pytest header; each test
# reseeds from (session seed, test id) and prints that seed, so any single
# test is reproduced with ``CB_TEST_SEED=<seed>`` regardless of test order.

TEST_SEED_ENV = "CB_TEST_SEED"


def _initial_session_seed() -> int:
    raw = os.environ.get(TEST_SEED_ENV, "").strip()
    if raw:
        return int(raw, 0)
    return random.SystemRandom().randrange(1, 2**63)


_SESSION_SEED = _initial_session_seed()
_TEST_RNG = random.Random(_SESSION_SEED)


def session_seed() -> int:
    """Seed of this pytest session (``CB_TEST_SEED`` or a fresh random one)."""
    return _SESSION_SEED


def reseed_for_test(test_id: str) -> None:
    """Restart the runtime RNG for *test_id* from the session seed."""
    global _TEST_RNG
    _TEST_RNG = random.Random(f"{_SESSION_SEED}:{test_id}")
    print(f"[seed] {TEST_SEED_ENV}={_SESSION_SEED} test={test_id}", flush=True)


def runtime_uuid_int() -> int:
    """128 random bits from the seeded runtime RNG (replaces ``uuid4().int``)."""
    return _TEST_RNG.getrandbits(128)


def runtime_hex(n: int) -> str:
    """*n* lowercase hex digits from the seeded runtime RNG."""
    return f"{_TEST_RNG.getrandbits(128):032x}"[:n]


# ---------------------------------------------------------------------------
# Product-behaviour invariants seen while parsing probe output
# ---------------------------------------------------------------------------
#
# A parser raises HarnessError only for probe output it cannot read (a missing
# token, text where a number belongs). A product value that breaks a published
# invariant -- a non-finite published value, a counter below zero, a dead-
# reckoning age published by an uninitialized INS -- is recorded here under
# the feature group that parsed it. Each group has a dedicated test that fails
# when anything was recorded, so one such value fails that test instead of
# aborting every test whose run happens to contain the snapshot.

_PRODUCT_ISSUES: dict[str, list[str]] = {}
_PRODUCT_ISSUE_COUNTS: dict[str, int] = {}


def note_product_issue(group: str, message: str) -> None:
    """Record one product-invariant violation under *group* (never raises)."""
    _PRODUCT_ISSUE_COUNTS[group] = _PRODUCT_ISSUE_COUNTS.get(group, 0) + 1
    kept = _PRODUCT_ISSUES.setdefault(group, [])
    if len(kept) < 25:
        kept.append(message)


def product_issues(group: str) -> tuple[int, list[str]]:
    """(count, first messages) recorded under *group* in this pytest process."""
    return _PRODUCT_ISSUE_COUNTS.get(group, 0), list(_PRODUCT_ISSUES.get(group, ()))


def nonfinite_fields(fields: Mapping[str, str]) -> list[str]:
    """``key=value`` of every snapshot token holding a NaN / infinite number."""
    out: list[str] = []
    for key, raw in fields.items():
        for part in raw.split(","):
            try:
                value = float(part)
            except ValueError:
                continue
            if not math.isfinite(value):
                out.append(f"{key}={raw}")
                break
    return out


def require_no_product_issues(group: str, what: str) -> None:
    """Dedicated-test assertion: nothing was recorded under *group*."""
    count, sample = product_issues(group)
    assert count == 0, (
        f"{what}: {count} snapshot value(s) broke a published invariant; "
        f"first: {sample[:6]}"
    )


# ---------------------------------------------------------------------------
# Public defaults / recipe artifact names
# ---------------------------------------------------------------------------

DEFAULT_CHARSET = "utf-8"
DEFAULT_TIMEOUT = 30.0
DEFAULT_REPLAY_TIMEOUT = 180.0
DEFAULT_C_STD = "c11"

# Public C headers shipped under src/ (relative to include_dir()).
PUBLIC_HEADER = "ins.h"
PUBLIC_HEADERS = (
    "ins.h",
    "ahrs.h",
    "baro_alt.h",
    "nav_suite.h",
    "geodetic_toolbox.h",
    "magnetic_model.h",
)

# ctypes ABI header, relative to capi_include_dir().
CAPI_HEADER = "ins_capi.h"

# Environment overrides (absolute paths). Never fall back to PATH for the
# library — a system-installed copy would hide a recipe shortfall.
PRODUCT_ROOT_ENV = "PRODUCT_ROOT"
PRODUCT_LIB_ENV = "PRODUCT_LIB"
PRODUCT_INCLUDE_ENV = "PRODUCT_INCLUDE"
PRODUCT_BIN_ENV = "PRODUCT_BIN"
PRODUCT_PYTHON_ENV = "PRODUCT_PYTHON"
CC_ENV = "CC"

# C regression replay. ``make replay`` writes this binary.
_C_REPLAY_RELPATHS = (
    Path("build") / "replay",
)


# Python replay program, relative to the repository root.
_PYTHON_REPLAY_RELPATHS = (
    Path("python") / "replay.py",
)

# Keys stripped so a child does not inherit the caller's locale / proxy /
# display / pager side channels unless the caller puts them back.
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
)

_KEEP_ENV_KEYS = (
    "PATH",
    "HOME",
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
    "LD_LIBRARY_PATH",
    "LIBRARY_PATH",
    "CPATH",
    "C_INCLUDE_PATH",
    "CPLUS_INCLUDE_PATH",
    "CC",
    "CXX",
    "COMPILER_PATH",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSAFEPATH",
    "PYTHONNOUSERSITE",
    "PYTHONHASHSEED",
    "PYTHONUNBUFFERED",
    "PYTHONWARNINGS",
    "PYTHONDONTWRITEBYTECODE",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
)


# ---------------------------------------------------------------------------
# Errors / result types
# ---------------------------------------------------------------------------


class HarnessError(RuntimeError):
    """Raised when an observation cannot be classified.

    Used for a missing compiler, a probe that failed to compile or link,
    a workspace path that escapes its root, a timeout, and I/O failures
    that are not a documented product outcome. Never used to mean "the
    product returned a non-zero exit the PRD describes".
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

    def compile_probe(
        self,
        source: str | bytes,
        *,
        language: str = "c",
        extra_args: Sequence[str] | None = None,
        output: str | Path = "probe",
        root: Path | None = None,
    ) -> Path:
        """Compile *source* into this workspace and return the binary path."""
        return compile_probe(
            source,
            language=language,
            extra_args=extra_args,
            output=self.resolve(output),
            root=root,
        )

    def invoke(
        self,
        source: str | bytes,
        args: Sequence[str] | None = None,
        *,
        language: str = "c",
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        extra_args: Sequence[str] | None = None,
        root: Path | None = None,
    ) -> RunResult:
        """Compile *source* and run it with this workspace as cwd and env.

        Does not raise on a non-zero product exit.
        """
        env = _apply_updates(self.env, env_updates)
        return invoke(
            source,
            args,
            language=language,
            cwd=self.path,
            env=env,
            stdin=stdin,
            timeout=timeout,
            extra_args=extra_args,
            root=root,
            isolate=False,
        )

    def run_python(
        self,
        source: str | bytes,
        args: Sequence[str] | None = None,
        *,
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        root: Path | None = None,
    ) -> RunResult:
        """Run a Python snippet with this workspace as cwd and env."""
        env = _apply_updates(self.env, env_updates)
        return run_python(
            source,
            args,
            cwd=self.path,
            env=env,
            stdin=stdin,
            timeout=timeout,
            root=root,
            isolate=False,
        )

    def run_replay(
        self,
        dataset: str | Path,
        args: Sequence[str] | None = None,
        *,
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_REPLAY_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        root: Path | None = None,
    ) -> RunResult:
        """Run the Python replay program with this workspace as cwd and env."""
        env = _apply_updates(self.env, env_updates)
        return run_replay(
            dataset,
            args,
            cwd=self.path,
            env=env,
            stdin=stdin,
            timeout=timeout,
            root=root,
            isolate=False,
        )

    def run_c_replay(
        self,
        dataset: str | Path,
        args: Sequence[str] | None = None,
        *,
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_REPLAY_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        root: Path | None = None,
    ) -> RunResult:
        """Run the C replay binary with this workspace as cwd and env."""
        env = _apply_updates(self.env, env_updates)
        return run_c_replay(
            dataset,
            args,
            cwd=self.path,
            env=env,
            stdin=stdin,
            timeout=timeout,
            root=root,
            isolate=False,
        )

    def run_runner(
        self,
        config: str | Path,
        args: Sequence[str] | None = None,
        *,
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_REPLAY_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        root: Path | None = None,
    ) -> RunResult:
        """Run the YAML CSV runner with this workspace as cwd and env."""
        env = _apply_updates(self.env, env_updates)
        return run_runner(
            config,
            args,
            cwd=self.path,
            env=env,
            stdin=stdin,
            timeout=timeout,
            root=root,
            isolate=False,
        )

    def run_command(
        self,
        argv: Sequence[str],
        *,
        stdin: bytes | str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        env_updates: Mapping[str, str | None] | None = None,
        cwd: str | Path | None = None,
    ) -> RunResult:
        """Run *argv* with this workspace as cwd and env.

        Does not raise on a non-zero child exit.
        """
        env = _apply_updates(self.env, env_updates)
        return run_command(
            argv,
            cwd=cwd if cwd is not None else self.path,
            env=env,
            stdin=stdin,
            timeout=timeout,
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


def _as_bytes(data: str | bytes, *, encoding: str = DEFAULT_CHARSET) -> bytes:
    if isinstance(data, bytes):
        return data
    return data.encode(encoding)


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


def _diagnostic_text(data: bytes) -> str:
    """Decode for harness logs only; replacement is not a test observation."""
    return data.decode(DEFAULT_CHARSET, errors="replace")


def _normalize_language(language: str) -> str:
    key = language.strip().lower()
    if key in ("c++", "cpp", "cxx", "cc"):
        return "c++"
    if key == "c":
        return "c"
    raise ValueError(f"unsupported probe language: {language!r} (use 'c' or 'c++')")


def python_exe() -> str:
    """Return the Python interpreter used for child-process product entry.

    Uses ``sys.executable`` so the child matches the pytest interpreter.
    Does not spawn the interpreter.
    """
    return sys.executable or "python3"


# ---------------------------------------------------------------------------
# Paths / discovery
# ---------------------------------------------------------------------------


def repo_root() -> Path:
    """Return the built repository root.

    Tests run with the repository root as the pytest process cwd (the
    shared library ``make pylib`` writes under ``python/`` is available
    there). ``PRODUCT_ROOT`` overrides cwd. Does not search parents.
    """
    override = os.environ.get(PRODUCT_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return Path.cwd().resolve()


def include_dir(*, root: Path | None = None) -> Path:
    """Return the public C include directory (``src/``).

    Resolution order:
      1. ``PRODUCT_INCLUDE`` if set.
      2. ``<root>/src`` containing the public INS header.

    Raises:
        FileNotFoundError: when the directory or public header is missing.
            That is a substrate gap, not a product-behavior judgment.
    """
    override = os.environ.get(PRODUCT_INCLUDE_ENV)
    if override:
        path = Path(override).expanduser().resolve()
        if path.is_file():
            path = path.parent
        header = path / PUBLIC_HEADER
        if not header.is_file():
            raise FileNotFoundError(
                f"{PRODUCT_INCLUDE_ENV} does not contain {PUBLIC_HEADER}: {path}"
            )
        return path

    base = root if root is not None else repo_root()
    path = (Path(base) / "src").resolve()
    header = path / PUBLIC_HEADER
    if not header.is_file():
        raise FileNotFoundError(
            f"public header not found at {header}; the repository src "
            "tree must be present before tests run"
        )
    return path


def navcore_include_dir(*, root: Path | None = None) -> Path:
    """Return the linear-algebra include directory (``NavCore/c``).

    Raises:
        FileNotFoundError: when the directory is missing. The recipe
            workspace contract includes this tree.
    """
    base = Path(root) if root is not None else repo_root()
    path = (base / "NavCore" / "c").resolve()
    if not path.is_dir():
        raise FileNotFoundError(
            f"linear-algebra include directory not found at {path}; "
            "the workspace contract requires this tree before tests run"
        )
    return path


def capi_include_dir(*, root: Path | None = None) -> Path:
    """Return the ctypes ABI include directory (``python/csrc``).

    Raises:
        FileNotFoundError: when the directory or ABI header is missing.
    """
    base = Path(root) if root is not None else repo_root()
    path = (base / "python" / "csrc").resolve()
    header = path / CAPI_HEADER
    if not header.is_file():
        raise FileNotFoundError(
            f"ctypes ABI header not found at {header}"
        )
    return path


def include_dirs(*, root: Path | None = None) -> tuple[Path, ...]:
    """Return include directories passed to a library probe, in order.

    Always includes :func:`include_dir`. Appends the linear-algebra and
    ctypes-ABI directories when they exist. Does not invent a path for
    a missing tree.
    """
    dirs = [include_dir(root=root)]
    base = Path(root) if root is not None else repo_root()
    navcore = (base / "NavCore" / "c").resolve()
    if navcore.is_dir():
        dirs.append(navcore)
    capi = (base / "python" / "csrc").resolve()
    if (capi / CAPI_HEADER).is_file():
        dirs.append(capi)
    return tuple(dirs)


@dataclass(frozen=True)
class ProductIdentity:
    """Package directory discovered under ``python/`` and its shared object.

    ``library`` is ``None`` when the package tree is present but ``make pylib``
    has not left a shared object in it. ``library_stem`` is parsed from the
    shared-object filename (the ``lib`` prefix and the platform suffix
    removed). Callers assert that it equals ``package_name``.
    """

    package_dir: Path
    package_name: str
    library: Path | None
    library_stem: str | None


def shared_object_stem(filename: str) -> str | None:
    """Return the stem of a shared-library filename, or ``None``.

    ``libfoo.so``, ``libfoo.so.1``, ``libfoo.dylib``, and ``libfoo.dll``
    all yield ``foo``. Other names yield ``None``.
    """
    name = filename
    if name.startswith("lib") and ".so." in name:
        name = name.split(".so.", 1)[0] + ".so"
    for suffix in (".so", ".dylib", ".dll"):
        prefix = "lib"
        if (
            name.startswith(prefix)
            and name.endswith(suffix)
            and len(name) > len(prefix) + len(suffix)
        ):
            return name[len(prefix) : -len(suffix)]
    return None


def _native_library_rank(filename: str) -> int:
    if sys.platform == "win32":
        order = (".dll", ".so", ".dylib")
    elif sys.platform == "darwin":
        order = (".dylib", ".so", ".dll")
    else:
        order = (".so", ".dylib", ".dll")
    for index, suffix in enumerate(order):
        if filename.endswith(suffix) or (suffix == ".so" and ".so." in filename):
            return index
    return len(order)


def _child_packages(python_dir: Path) -> list[Path]:
    """Return direct children of *python_dir* that contain ``__init__.py``."""
    if not python_dir.is_dir():
        return []
    try:
        children = sorted(python_dir.iterdir(), key=lambda entry: entry.name)
    except OSError as exc:
        raise HarnessError(f"cannot list {python_dir}: {exc}") from exc
    return [
        child
        for child in children
        if child.is_dir() and (child / "__init__.py").is_file()
    ]


def _shared_libraries(package_dir: Path) -> list[Path]:
    try:
        entries = list(package_dir.iterdir())
    except OSError as exc:
        raise HarnessError(f"cannot list {package_dir}: {exc}") from exc
    libs = [
        entry
        for entry in entries
        if entry.is_file() and shared_object_stem(entry.name) is not None
    ]
    libs.sort(key=lambda entry: (_native_library_rank(entry.name), entry.name))
    return libs


def _select_package(base: Path) -> Path | None:
    """Return the one importable package under ``python/``.

    When several packages exist, keep the single one that contains a
    shared object whose stem equals the directory name. Otherwise return
    ``None`` so a caller can fail an assertion instead of guessing a name.
    """
    packages = _child_packages(base / "python")
    if not packages:
        return None
    if len(packages) == 1:
        return packages[0]
    matched: list[Path] = []
    for package in packages:
        for lib in _shared_libraries(package):
            if shared_object_stem(lib.name) == package.name:
                matched.append(package)
                break
    if len(matched) == 1:
        return matched[0]
    return None


def _choose_library(package_dir: Path) -> Path | None:
    libs = _shared_libraries(package_dir)
    if not libs:
        return None
    matched = [
        lib
        for lib in libs
        if shared_object_stem(lib.name) == package_dir.name
    ]
    pool = matched or libs
    return pool[0]


def product_identity(*, root: Path | None = None) -> ProductIdentity | None:
    """Resolve the package directory and the shared object ``make pylib`` wrote.

    Does not raise :class:`FileNotFoundError`. Returns ``None`` when no
    package directory can be resolved. ``library`` is ``None`` when that
    directory does not yet contain a shared object — absence before
    ``make pylib`` is not an error by itself.
    """
    base = Path(root) if root is not None else repo_root()
    package = _select_package(base)
    if package is None:
        return None
    library = _choose_library(package)
    stem = shared_object_stem(library.name) if library is not None else None
    return ProductIdentity(
        package_dir=package.resolve(),
        package_name=package.name,
        library=library.resolve() if library is not None else None,
        library_stem=stem,
    )


def importable_package_name(*, root: Path | None = None) -> str:
    """Return the discovered package directory name.

    Raises:
        FileNotFoundError: when the package directory cannot be resolved.
    """
    ident = product_identity(root=root)
    if ident is None:
        base = Path(root) if root is not None else repo_root()
        raise FileNotFoundError(
            "Python package not found under "
            f"{(base / 'python').resolve()}; expected one directory "
            "containing __init__.py"
        )
    return ident.package_name


def python_package_dir(*, root: Path | None = None) -> Path:
    """Return the directory that must be on ``PYTHONPATH`` (``python/``).

    That directory contains the importable package. Does not load the
    package and does not require the shared library to be present.
    The package name is whatever directory ``make pylib`` wraps; it is
    not a hardcoded token.

    Raises:
        FileNotFoundError: when no package ``__init__.py`` is present.
    """
    override = os.environ.get(PRODUCT_PYTHON_ENV)
    if override:
        path = Path(override).expanduser().resolve()
        if path.is_file():
            path = path.parent
        if (path / "__init__.py").is_file():
            return path.parent
        if _child_packages(path):
            return path
        raise FileNotFoundError(
            f"{PRODUCT_PYTHON_ENV} does not contain a Python package: {path}"
        )

    base = Path(root) if root is not None else repo_root()
    path = (base / "python").resolve()
    if not _child_packages(path):
        raise FileNotFoundError(
            f"Python package not found under {path}; the python/ tree "
            "must contain one package directory before tests run"
        )
    return path


def ensure_import_path(*, root: Path | None = None) -> Path:
    """Insert the package directory at the front of ``sys.path``.

    Does not import the product. Returns the directory inserted.
    Idempotent: if the directory is already first, it is left there;
    if it is present later, it is moved to index 0.

    Raises:
        FileNotFoundError: when the package tree is missing.
    """
    path = python_package_dir(root=root)
    as_str = str(path)
    if as_str in sys.path:
        sys.path.remove(as_str)
    sys.path.insert(0, as_str)
    return path


def library_file(*, root: Path | None = None) -> Path:
    """Locate the recipe-built shared library.

    Resolution order:
      1. ``PRODUCT_LIB`` if set.
      2. Known ``make pylib`` output paths under ``<root>/python``.

    Does not fall back to a system-installed library.

    Raises:
        FileNotFoundError: when no library file exists at a resolved path.
    """
    override = os.environ.get(PRODUCT_LIB_ENV)
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(
                f"{PRODUCT_LIB_ENV} does not point to a file: {path}"
            )
        return path

    base = Path(root) if root is not None else repo_root()
    ident = product_identity(root=base)
    if ident is not None and ident.library is not None and ident.library.is_file():
        if ident.library_stem == ident.package_name:
            return ident.library
    searched: list[str] = []
    python_dir = (base / "python").resolve()
    if ident is not None:
        for suffix in (".so", ".dylib", ".dll"):
            searched.append(
                str(ident.package_dir / f"lib{ident.package_name}{suffix}")
            )
    else:
        searched.append(str(python_dir))
    raise FileNotFoundError(
        "recipe-built shared library not found; searched "
        + ", ".join(searched)
        + ". make pylib must produce it before the library is loaded."
    )


def python_replay_script(*, root: Path | None = None) -> Path:
    """Locate the Python dataset-replay program.

    Raises:
        FileNotFoundError: when the script is missing.
    """
    base = Path(root) if root is not None else repo_root()
    searched: list[str] = []
    for rel in _PYTHON_REPLAY_RELPATHS:
        path = (base / rel).resolve()
        searched.append(str(path))
        if path.is_file():
            return path
    raise FileNotFoundError(
        "Python replay program not found; searched " + ", ".join(searched)
    )


def c_replay_bin(*, root: Path | None = None) -> Path:
    """Locate the C dataset-replay binary and return its path.

    Resolution order:
      1. ``PRODUCT_BIN`` if set.
      2. ``build/replay``, which ``make replay`` writes.

    Raises:
        FileNotFoundError: when the binary is missing.
    """
    override = os.environ.get(PRODUCT_BIN_ENV)
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(
                f"{PRODUCT_BIN_ENV} does not point to a file: {path}"
            )
        if not os.access(path, os.X_OK):
            raise FileNotFoundError(f"{PRODUCT_BIN_ENV} is not executable: {path}")
        return path

    base = Path(root) if root is not None else repo_root()
    searched: list[str] = []
    for rel in _C_REPLAY_RELPATHS:
        path = (base / rel).resolve()
        searched.append(str(path))
        if path.is_file() and os.access(path, os.X_OK):
            return path
    raise FileNotFoundError(
        "C replay binary not found; searched "
        + ", ".join(searched)
        + ". make replay writes build/replay."
    )


def c_compiler() -> str:
    """Return the C compiler used to link probes.

    Uses ``$CC`` when set, otherwise ``cc``. Does not spawn the compiler.
    A missing binary is reported when :func:`compile_probe` runs, not
    here.
    """
    override = os.environ.get(CC_ENV)
    if override:
        return override
    return "cc"


def compile_repository(*, root: Path | None = None) -> RunResult | None:
    """Run ``make pylib replay`` in the repository.

    A missing Makefile returns ``None``: an empty tree has nothing to
    compile, and that absence is not itself a failure. A non-zero make
    status is returned on the :class:`RunResult` and is not raised;
    callers assert on the artifacts the command wrote.
    """
    base = Path(root) if root is not None else repo_root()
    if not (base / "Makefile").is_file():
        print(
            f"[harness] no Makefile at {base}; skip make pylib replay",
            flush=True,
        )
        return None
    print("[harness] make pylib replay", flush=True)
    return run_command(
        ["make", "pylib", "replay"],
        cwd=base,
        timeout=DEFAULT_REPLAY_TIMEOUT,
    )


def _is_shared_library(path: Path) -> bool:
    name = path.name
    return (
        name.endswith(".so")
        or ".so." in name
        or name.endswith(".dylib")
        or name.endswith(".dll")
    )


def _prepend_path(env: dict[str, str], key: str, directory: str) -> None:
    existing = env.get(key, "")
    parts = [directory]
    if existing:
        parts.extend(
            part for part in existing.split(os.pathsep) if part and part != directory
        )
    env[key] = os.pathsep.join(parts)


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
    """Build an environment that does not inherit the caller's home/proxy state.

    Starts from a small keep-list of substrate keys (PATH, locale, compiler,
    loader, Python) taken from *base* or ``os.environ``, points ``HOME``
    and the XDG dirs at *home*, unsets proxy / TTY keys, prepends the
    package directory to ``PYTHONPATH``, and applies *updates* last
    (``None`` unsets). When the recipe library is shared, prepends its
    directory to ``LD_LIBRARY_PATH``. Does not mutate ``os.environ``.

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

    env["HOME"] = str(home_path)
    env["XDG_CONFIG_HOME"] = str(cfg_dir)
    env["XDG_CACHE_HOME"] = str(cache_dir)
    env["XDG_DATA_HOME"] = str(data_dir)
    env.setdefault("LANG", "C.UTF-8")
    env.setdefault("LC_ALL", "C.UTF-8")
    env["TMPDIR"] = str(home_path / "tmp")
    Path(env["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    try:
        pkg = python_package_dir(root=root)
    except FileNotFoundError:
        pkg = None
    if pkg is not None:
        _prepend_path(env, "PYTHONPATH", str(pkg))

    try:
        lib = library_file(root=root)
    except FileNotFoundError:
        lib = None
    if lib is not None and _is_shared_library(lib):
        _prepend_path(env, "LD_LIBRARY_PATH", str(lib.parent))

    if updates:
        env = _apply_updates(env, updates)
    return env


def _with_product_paths(
    env: Mapping[str, str] | None,
    *,
    root: Path | None,
) -> dict[str, str]:
    """Copy *env* (or ``os.environ``) and prepend product PYTHONPATH / loader paths."""
    merged = dict(os.environ) if env is None else dict(env)
    try:
        pkg = python_package_dir(root=root)
    except FileNotFoundError:
        pkg = None
    if pkg is not None:
        _prepend_path(merged, "PYTHONPATH", str(pkg))
    try:
        lib = library_file(root=root)
    except FileNotFoundError:
        lib = None
    if lib is not None and _is_shared_library(lib):
        _prepend_path(merged, "LD_LIBRARY_PATH", str(lib.parent))
    return merged


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

    Raises:
        FileNotFoundError: if the executable cannot be found.
        HarnessError: on timeout or an OSError other than classified
            absence. Does not interpret the exit status.
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
    except FileNotFoundError:
        raise
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(
            f"command timed out after {timeout}s: {list(argv)!r}"
        ) from exc
    except OSError as exc:
        raise HarnessError(f"failed to execute {argv[0]!r}: {exc}") from exc

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


# ---------------------------------------------------------------------------
# Library probes (canonical public C entry)
# ---------------------------------------------------------------------------

_PROBE_CACHE: Path | None = None


def _probe_cache_dir() -> Path:
    """Return a process-lifetime directory for compiled probes.

    Created on first compile, not at import. Removed at interpreter exit.
    """
    global _PROBE_CACHE
    if _PROBE_CACHE is None:
        _PROBE_CACHE = Path(tempfile.mkdtemp(prefix="libprobe-"))
        atexit.register(shutil.rmtree, _PROBE_CACHE, True)
    return _PROBE_CACHE


def _compile_argv(
    source_path: Path,
    output: Path,
    *,
    language: str,
    includes: Sequence[Path],
    lib: Path,
    extra_args: Sequence[str],
) -> list[str]:
    compiler = c_compiler()
    argv = [compiler, f"-std={DEFAULT_C_STD}", "-D_GNU_SOURCE"]
    if language == "c++":
        argv = [compiler, "-std=c++17", "-D_GNU_SOURCE"]
    for inc in includes:
        argv.append(f"-I{inc}")
    argv.extend(str(a) for a in extra_args)
    argv.extend(
        [
            str(source_path),
            str(lib),
            "-lm",
            f"-Wl,-rpath,{lib.parent}",
            "-o",
            str(output),
        ]
    )
    return argv


def compile_probe(
    source: str | bytes,
    *,
    language: str = "c",
    extra_args: Sequence[str] | None = None,
    output: str | Path | None = None,
    root: Path | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> Path:
    """Compile *source* against the recipe-built library and return the binary.

    *language* is ``c`` (public C headers; the default) or ``c++``. Extra
    compiler/linker tokens go in *extra_args*. When *output* is omitted,
    the binary is written to a process-lifetime cache keyed by source,
    language, flags, and library identity.

    This is compile-and-link of a caller-supplied probe, not a product
    rebuild: it does not run make, fetch, or rewrite library sources.

    Raises:
        FileNotFoundError: missing header, library, or compiler.
        HarnessError: compiler non-zero exit, timeout, or I/O failure.
            Compiler stderr is included in the message. A compile failure
            is never returned as a :class:`RunResult`.
    """
    lang = _normalize_language(language)
    extra = tuple(str(a) for a in extra_args) if extra_args else ()
    base = root if root is not None else repo_root()
    includes = include_dirs(root=base)
    lib = library_file(root=base)
    src_bytes = _as_bytes(source)

    if output is None:
        try:
            st = lib.stat()
        except OSError as exc:
            raise HarnessError(f"cannot stat library {lib}: {exc}") from exc
        digest = hashlib.sha256()
        digest.update(src_bytes)
        digest.update(b"\0")
        digest.update(lang.encode())
        digest.update(b"\0")
        digest.update(str(lib).encode())
        digest.update(b"\0")
        digest.update(str(st.st_mtime_ns).encode())
        digest.update(b"\0")
        digest.update(str(st.st_size).encode())
        digest.update(b"\0")
        digest.update(b"\0".join(a.encode() for a in extra))
        digest.update(b"\0")
        digest.update(c_compiler().encode())
        out_path = _probe_cache_dir() / f"probe-{digest.hexdigest()[:20]}"
        if out_path.is_file() and os.access(out_path, os.X_OK):
            print(f"[harness] reuse probe {out_path}", flush=True)
            return out_path
    else:
        out_path = Path(output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = ".c" if lang == "c" else ".cpp"
    work = Path(tempfile.mkdtemp(prefix="libprobe-src-"))
    try:
        source_path = work / f"probe{suffix}"
        source_path.write_bytes(src_bytes)
        argv = _compile_argv(
            source_path,
            out_path,
            language=lang,
            includes=includes,
            lib=lib,
            extra_args=extra,
        )
        print(f"[harness] compile argv={argv!r}", flush=True)
        try:
            completed = subprocess.run(
                argv,
                cwd=str(work),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"C compiler {c_compiler()!r} not found; a C11 toolchain "
                "is required to link probes against the library"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise HarnessError(
                f"compile timed out after {timeout}s: {argv!r}"
            ) from exc
        except OSError as exc:
            raise HarnessError(f"failed to spawn compiler: {exc}") from exc
        if completed.returncode != 0:
            err = _diagnostic_text((completed.stderr or b"") + (completed.stdout or b""))
            raise HarnessError(
                f"probe failed to compile or link (exit {completed.returncode}): {err}"
            )
        if not out_path.is_file():
            raise HarnessError(f"compiler exited 0 but produced no binary at {out_path}")
        out_path.chmod(out_path.stat().st_mode | 0o111)
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)


def invoke(
    source: str | bytes,
    args: Sequence[str] | None = None,
    *,
    language: str = "c",
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: bytes | str | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    extra_args: Sequence[str] | None = None,
    root: Path | None = None,
    isolate: bool = True,
) -> RunResult:
    """Compile *source* against the library and run the resulting binary.

    This is the canonical way to reach the C public entries. The probe
    is a child process: instance state, and any other process-wide
    library state, cannot leak into the pytest process or a later probe.

    When *isolate* is true (the default) and *cwd* / *env* are omitted,
    the process runs in a fresh :func:`workspace` so it cannot see the
    caller's cwd or HOME. Pass ``isolate=False`` (and optionally *cwd* /
    *env*) to inherit the caller's process state, or to reuse a
    :class:`Workspace`.

    Returns a :class:`RunResult`. Does not raise on a non-zero product
    exit — that status is the observation. Compile/link failures raise
    :class:`HarnessError` before the probe is started.
    """
    binary = compile_probe(
        source,
        language=language,
        extra_args=extra_args,
        root=root,
        timeout=timeout,
    )
    argv = [str(binary), *_normalize_args(args)]

    if cwd is not None or env is not None or not isolate:
        run_env = dict(env) if env is not None else None
        if run_env is not None:
            try:
                lib = library_file(root=root)
            except FileNotFoundError:
                lib = None
            if lib is not None and _is_shared_library(lib):
                _prepend_path(run_env, "LD_LIBRARY_PATH", str(lib.parent))
        return run_command(
            argv,
            cwd=cwd,
            env=run_env,
            stdin=stdin,
            timeout=timeout,
        )

    with workspace(root=root) as ws:
        return run_command(
            argv,
            cwd=ws.path,
            env=ws.env,
            stdin=stdin,
            timeout=timeout,
        )


# ---------------------------------------------------------------------------
# Python package / replay / YAML runner
# ---------------------------------------------------------------------------


def run_python(
    source: str | bytes,
    args: Sequence[str] | None = None,
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: bytes | str | None = None,
    timeout: float | None = DEFAULT_TIMEOUT,
    root: Path | None = None,
    isolate: bool = True,
) -> RunResult:
    """Run *source* in a child Python interpreter with the package on the path.

    Writes the snippet to a temporary ``.py`` file and executes
    ``<python> probe.py *args``. The package directory is prepended to
    ``PYTHONPATH`` so importing the package resolves to the tree
    ``make pylib`` built. Does not import the product in this process.

    Isolation rules match :func:`invoke`. Does not raise on a non-zero
    child exit.

    Raises:
        FileNotFoundError: if the package directory is missing.
        HarnessError: on timeout or spawn failure.
    """
    # Force the package tree to exist up front (classified absence).
    python_package_dir(root=root)
    src_bytes = _as_bytes(source)

    def _execute(script: Path, workdir: str | Path | None, run_env: Mapping[str, str] | None) -> RunResult:
        argv = [python_exe(), str(script), *_normalize_args(args)]
        return run_command(
            argv,
            cwd=workdir,
            env=run_env,
            stdin=stdin,
            timeout=timeout,
        )

    if cwd is not None or env is not None or not isolate:
        work = Path(tempfile.mkdtemp(prefix="pyprobe-"))
        try:
            script = work / "probe.py"
            script.write_bytes(src_bytes)
            run_env = _with_product_paths(env, root=root)
            return _execute(script, cwd, run_env)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    with workspace(root=root) as ws:
        script = ws.write("probe.py", src_bytes)
        return _execute(script, ws.path, ws.env)


def run_replay(
    dataset: str | Path,
    args: Sequence[str] | None = None,
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: bytes | str | None = None,
    timeout: float | None = DEFAULT_REPLAY_TIMEOUT,
    root: Path | None = None,
    isolate: bool = True,
) -> RunResult:
    """Invoke the Python dataset-replay program as ``replay.py <dataset> *args``.

    *dataset* is a directory containing ``config.yaml`` (or the path of
    that file). Pass an absolute path: a default isolated run uses an
    ephemeral cwd, so a bare relative name would look in that tree, not
    the repository. Isolation rules match :func:`invoke`. Does not
    raise on a non-zero product exit.

    Raises:
        FileNotFoundError: if the replay script or package tree is missing.
    """
    script = python_replay_script(root=root)
    python_package_dir(root=root)
    argv = [python_exe(), str(script), str(dataset), *_normalize_args(args)]
    return _run_product_argv(
        argv,
        cwd=cwd,
        env=env,
        stdin=stdin,
        timeout=timeout,
        root=root,
        isolate=isolate,
    )


def run_c_replay(
    dataset: str | Path,
    args: Sequence[str] | None = None,
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: bytes | str | None = None,
    timeout: float | None = DEFAULT_REPLAY_TIMEOUT,
    root: Path | None = None,
    isolate: bool = True,
) -> RunResult:
    """Invoke the C dataset-replay binary as ``replay <dataset> *args``.

    Isolation rules match :func:`invoke`. Does not raise on a non-zero
    product exit.

    Raises:
        FileNotFoundError: if the C replay binary was not built.
    """
    exe = c_replay_bin(root=root)
    argv = [str(exe), str(dataset), *_normalize_args(args)]
    return _run_product_argv(
        argv,
        cwd=cwd,
        env=env,
        stdin=stdin,
        timeout=timeout,
        root=root,
        isolate=isolate,
    )


def run_runner(
    config: str | Path,
    args: Sequence[str] | None = None,
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    stdin: bytes | str | None = None,
    timeout: float | None = DEFAULT_REPLAY_TIMEOUT,
    root: Path | None = None,
    isolate: bool = True,
) -> RunResult:
    """Invoke the YAML-configured CSV runner as ``python -m <package> <config> *args``.

    Isolation rules match :func:`invoke`. Does not raise on a non-zero
    product exit.

    Raises:
        FileNotFoundError: if the package directory is missing.
    """
    python_package_dir(root=root)
    argv = [
        python_exe(),
        "-m",
        importable_package_name(root=root),
        str(config),
        *_normalize_args(args),
    ]
    return _run_product_argv(
        argv,
        cwd=cwd,
        env=env,
        stdin=stdin,
        timeout=timeout,
        root=root,
        isolate=isolate,
    )


def _run_product_argv(
    argv: Sequence[str],
    *,
    cwd: str | Path | None,
    env: Mapping[str, str] | None,
    stdin: bytes | str | None,
    timeout: float | None,
    root: Path | None,
    isolate: bool,
) -> RunResult:
    if cwd is not None or env is not None or not isolate:
        run_env = _with_product_paths(env, root=root)
        return run_command(
            argv,
            cwd=cwd,
            env=run_env,
            stdin=stdin,
            timeout=timeout,
        )
    with workspace(root=root) as ws:
        return run_command(
            argv,
            cwd=ws.path,
            env=ws.env,
            stdin=stdin,
            timeout=timeout,
        )


# ---------------------------------------------------------------------------
# F00 recertification — collected only when pytest is pointed at this file.
# Importing this module still does no I/O. These tests prove the compile /
# invoke isolation machinery is live, not a stamp on an empty pin.
# ---------------------------------------------------------------------------

_LINK_PROBE = r"""
#include "ins.h"
#include "geodetic_toolbox.h"
#include <stdio.h>
int main(void) {
    float q[4];
    ins_quat_from_rpy(0.0f, 0.0f, 0.0f, q);
    printf("harness-link %.8f %.8f %.8f %.8f\n", q[0], q[1], q[2], q[3]);
    return 0;
}
"""


def _assert_compiled_library() -> ProductIdentity:
    """Fail the calling test when the post-compile shared object is absent.

    A missing library is an assertion failure. Lookup does not raise
    :class:`FileNotFoundError` before that assertion.
    """
    ident = product_identity()
    assert ident is not None, "python package directory was not found"
    assert ident.library is not None and ident.library.is_file(), (
        "shared library is missing after make pylib"
    )
    assert ident.library_stem == ident.package_name, (
        f"package directory {ident.package_name!r} and shared-object stem "
        f"{ident.library_stem!r} differ"
    )
    return ident

_CWD_PROBE = r"""
#include "ins.h"
#include <stdio.h>
#include <unistd.h>
int main(void) {
    char buf[4096];
    if (getcwd(buf, sizeof buf) == NULL) {
        return 2;
    }
    puts(buf);
    return 0;
}
"""

_ARG_PROBE = r"""
#include "ins.h"
#include <stdio.h>
int main(int argc, char **argv) {
    int i;
    for (i = 1; i < argc; ++i) {
        if (i > 1) {
            putchar(' ');
        }
        fputs(argv[i], stdout);
    }
    putchar('\n');
    return 0;
}
"""


def test_invoke_links_public_header_and_returns_classified_result():
    """Link a C caller to the shared library and run a public conversion."""
    ident = _assert_compiled_library()
    result = invoke(_LINK_PROBE)
    print(
        f"returncode={result.returncode} stdout={result.stdout!r} "
        f"stderr={result.stderr!r} argv={result.argv!r} cwd={result.cwd!r} "
        f"library={ident.library}",
        flush=True,
    )
    assert isinstance(result, RunResult)
    assert result.returncode == 0
    text = result.stdout_text.strip()
    assert text.startswith("harness-link "), text
    parts = text.split()
    assert len(parts) == 5, text
    w, x, y, z = (float(part) for part in parts[1:])
    assert abs(w - 1.0) < 1e-5
    assert abs(x) < 1e-5 and abs(y) < 1e-5 and abs(z) < 1e-5
    assert result.argv, "RunResult.argv must record the executed probe"
    assert Path(result.argv[0]).is_file()
    assert result.cwd
    assert Path(result.cwd).resolve() != repo_root()


def test_default_invoke_cwd_is_not_the_repository_root():
    """Default isolation runs the probe in an ephemeral directory."""
    _assert_compiled_library()
    result = invoke(_CWD_PROBE)
    print(
        f"returncode={result.returncode} stdout={result.stdout!r}",
        flush=True,
    )
    assert result.returncode == 0
    probe_cwd = Path(result.stdout_text.strip()).resolve()
    root = repo_root()
    print(f"probe_cwd={probe_cwd} repo_root={root}", flush=True)
    assert probe_cwd != root
    assert not _is_relative_to(probe_cwd, root)
    assert Path(result.cwd).resolve() == probe_cwd


def test_invoke_forwards_argv_and_does_not_raise_on_nonzero_exit():
    """Argv is the probe's, and a non-zero product exit is a classified result."""
    _assert_compiled_library()
    ok = invoke(_ARG_PROBE, ["alpha", "beta"])
    print(
        f"ok returncode={ok.returncode} stdout={ok.stdout!r} argv={ok.argv!r}",
        flush=True,
    )
    assert ok.returncode == 0
    assert ok.stdout_text.strip() == "alpha beta"
    assert ok.argv[-2:] == ("alpha", "beta")

    fail_src = r"""
#include "ins.h"
int main(void) { return 7; }
"""
    failed = invoke(fail_src)
    print(
        f"fail returncode={failed.returncode} argv={failed.argv!r}",
        flush=True,
    )
    assert isinstance(failed, RunResult)
    assert failed.returncode == 7
    assert failed.argv, "a classified non-zero exit still records argv"


def test_compile_probe_uncompilable_source_is_harness_error_not_runresult():
    """A compile failure is not a product RunResult."""
    _assert_compiled_library()
    try:
        binary = compile_probe("this is not valid C source")
    except HarnessError as exc:
        print(f"HarnessError: {exc}", flush=True)
        assert str(exc)
        assert "RunResult" not in type(exc).__name__
        return
    raise AssertionError(
        f"compile_probe accepted uncompilable source and returned {binary!r}"
    )


def test_library_file_missing_override_raises_not_none():
    """Absence of the recipe library is FileNotFoundError, never a sentinel."""
    previous = os.environ.get(PRODUCT_LIB_ENV)
    missing = "/no/such/recipe-built/libmissing.so"
    os.environ[PRODUCT_LIB_ENV] = missing
    try:
        try:
            path = library_file()
        except FileNotFoundError as exc:
            print(f"FileNotFoundError: {exc}", flush=True)
            assert missing in str(exc)
            return
        raise AssertionError(
            f"library_file returned {path} for a missing PRODUCT_LIB override"
        )
    finally:
        if previous is None:
            os.environ.pop(PRODUCT_LIB_ENV, None)
        else:
            os.environ[PRODUCT_LIB_ENV] = previous


def test_run_python_child_imports_package():
    """The Python child imports the package and that import loads the shared object."""
    ident = _assert_compiled_library()
    assert ident.library is not None
    src = "\n".join(
        [
            "import os",
            f"import {ident.package_name} as pkg",
            "print(pkg.__name__)",
            "print(os.getcwd())",
            "print(pkg.__file__)",
            "maps = open('/proc/self/maps', encoding='utf-8', errors='replace').read()",
            f"print('LOADED' if {ident.library.name!r} in maps else 'NOT-LOADED')",
        ]
    )
    result = run_python(src)
    print(
        f"returncode={result.returncode} stdout={result.stdout!r} "
        f"stderr={result.stderr!r}",
        flush=True,
    )
    assert result.returncode == 0, result.stderr_text
    lines = result.stdout_text.strip().splitlines()
    assert len(lines) >= 4, f"child stdout missing name/cwd/file/load: {lines!r}"
    assert lines[0] == ident.package_name
    child_cwd = Path(lines[1]).resolve()
    pkg_file = Path(lines[2]).resolve()
    root = repo_root()
    print(f"child_cwd={child_cwd} pkg_file={pkg_file} repo_root={root}", flush=True)
    assert child_cwd != root
    assert not _is_relative_to(child_cwd, root)
    assert _is_relative_to(pkg_file, python_package_dir(root=root))
    assert lines[3] == "LOADED"


def test_c_replay_runs_dataset_of_csv_and_config():
    """Run the replay binary from ``make replay`` on CSV streams plus config.yaml.

    The dataset (IMU, reference trajectory, GNSS on a static pad, and a
    config.yaml) is written here with the suite's own dataset writer. The
    public spec requires the replay program, not any committed dataset tree,
    so the probe does not look for one in the candidate repository.
    """
    ident = _assert_compiled_library()
    try:
        exe = c_replay_bin()
    except FileNotFoundError:
        exe = None
    assert exe is not None and exe.is_file() and os.access(exe, os.X_OK)
    from F02_helpers import runtime_site
    from F10_helpers import write_replay_dataset

    lat, lon, h = runtime_site()
    with workspace() as ws:
        dataset = write_replay_dataset(
            ws, lat_deg=lat, lon_deg=lon, h_m=h, relpath="f00-static-pad"
        )
        assert (dataset / "config.yaml").is_file()
        csv_files = sorted(dataset.glob("*.csv"))
        assert {c.name for c in csv_files} >= {"imu.csv", "ref.csv", "gnss.csv"}, csv_files
        result = run_c_replay(dataset)
    print(
        f"library={ident.library} replay={exe} dataset={dataset} "
        f"csv={len(csv_files)} returncode={result.returncode} "
        f"stdout_tail={result.stdout_text[-400:]!r}",
        flush=True,
    )
    assert result.returncode == 0, result.stderr_text[-1500:]
    assert Path(result.argv[0]).resolve() == exe.resolve()
    assert str(dataset) in result.argv


def test_isolated_workspace_home_is_ephemeral(isolated_ws):
    """conftest isolated_ws binds HOME to a tree that is not the caller."""
    process_home = os.environ.get("HOME")
    print(
        f"ws.home={isolated_ws.home} env HOME={isolated_ws.env.get('HOME')!r} "
        f"process HOME={process_home!r} proxies="
        f"{ {k: isolated_ws.env.get(k) for k in ('HTTP_PROXY', 'http_proxy')} }",
        flush=True,
    )
    assert isolated_ws.env["HOME"] == str(isolated_ws.home)
    assert isolated_ws.env["HOME"] != process_home
    assert isolated_ws.path.resolve() != repo_root()
    assert not _is_relative_to(isolated_ws.path.resolve(), repo_root())
    for proxy_key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        assert proxy_key not in isolated_ws.env
    marker = isolated_ws.write("marker.txt", "workspace-only\n")
    assert marker.is_file()
    assert isolated_ws.read("marker.txt") == "workspace-only\n"
    if process_home:
        leaked = Path(process_home) / "marker.txt"
        print(f"caller_home_marker_exists={leaked.is_file()}", flush=True)
        assert not leaked.is_file()
    try:
        isolated_ws.resolve("../escape")
    except HarnessError as exc:
        print(f"escape HarnessError: {exc}", flush=True)
        assert str(exc)
    else:
        raise AssertionError(
            "workspace.resolve allowed a path that escapes the workspace"
        )


def test_workspace_root_fixture_is_built_repository(workspace_root):
    """conftest workspace_root is the recipe-built tree with public headers."""
    print(f"workspace_root={workspace_root} repo_root={repo_root()}", flush=True)
    assert workspace_root == repo_root()
    header = workspace_root / "src" / PUBLIC_HEADER
    print(f"public_header={header} is_file={header.is_file()}", flush=True)
    assert header.is_file()
    ident = product_identity(root=workspace_root)
    assert ident is not None
    assert ident.library is not None and ident.library.is_file()
    assert ident.library_stem == ident.package_name
    print(
        f"library={ident.library} package={ident.package_dir} "
        f"stem={ident.library_stem}",
        flush=True,
    )
    assert (ident.package_dir / "__init__.py").is_file()

