# feature: F00
"""Pytest fixtures and import-path setup for the shared suite harness.

Reusable invocation / isolation machinery lives in ``_harness``; this
module only wires pytest to that machinery and ensures
``from _harness import ...`` resolves when tests are collected from the
repository root.

B-run passes this file and ``_harness.py`` as pytest targets together
with every feature file. They are support modules, not test modules:
collecting them as tests would import a second harness copy and leak
cwd/env across features that only stay green when sealed alone.

Collected F00 assertions live in ``F00_acceptance.py``, which the F00
group names on its pytest file list. These support modules stay
uncollected. This module does not append that file onto later
invocations, and a run that collects 0 tests is left as a failure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

# Support module: never collected as tests, even when named on the CLI.
__test__ = False

from _harness import (  # noqa: E402
    OXLINT_BIN_RELPATH,
    PRODUCT_ROOT_ENV,
    HarnessError,
    copy_script,
    host_modules_root,
    node_executable,
    node_modules_path,
    oxlint_executable,
    repo_root,
    workspace,
)

_SUPPORT_BASENAMES = frozenset({"_harness.py", "conftest.py"})
_SESSION_CWD = os.getcwd()
_SESSION_PRODUCT_ROOT: str | None = None
# Set when the host linter cannot be located or materialized at configure
# time. Every collected test then fails with this reason instead of the
# whole session aborting before any test runs.
_HOST_SETUP_ERROR: str | None = None

# pytest consults these for directory collection. CLI-named initial paths
# still need pytest_ignore_collect below.
collect_ignore = ["_harness.py", "conftest.py"]
collect_ignore_glob = ["_harness.py", "conftest.py"]


def _path_name(loc: object) -> str:
    name = getattr(loc, "name", None)
    if isinstance(name, str) and name:
        return name
    text = str(loc).replace("\\", "/")
    return text.rsplit("/", 1)[-1]


def pytest_ignore_collect(collection_path=None, path=None, config=None):
    """Do not collect support modules even when they are CLI pytest targets.

    Per-feature seals import ``_harness``; they do not collect it. Combined
    original-name pytest includes these paths. Importing them as test
    modules creates a second harness identity and is the isolation hole.
    """
    loc = collection_path if collection_path is not None else path
    if loc is None:
        return None
    if _path_name(loc) in _SUPPORT_BASENAMES:
        return True
    return None


def pytest_configure(config):
    """Pin the product root before collection, while cwd is still the repo.

    Also expose the host-linter ``node_modules/.bin`` on PATH. Judge-profile
    overlays source without that tree; env-warm or a lockfile materialize
    still has it.
    """
    global _SESSION_PRODUCT_ROOT, _HOST_SETUP_ERROR
    root = repo_root()
    os.environ.setdefault(PRODUCT_ROOT_ENV, str(root))
    _SESSION_PRODUCT_ROOT = os.environ[PRODUCT_ROOT_ENV]
    try:
        modules_root = host_modules_root(root=root)
    except HarnessError as exc:
        _HOST_SETUP_ERROR = f"host-linter setup failed for product root {root}: {exc}"
        print(f"[conftest] {_HOST_SETUP_ERROR}", file=sys.stderr, flush=True)
        return
    print(
        f"[conftest] product_root={root} host_linter={modules_root}",
        flush=True,
    )
    bin_dir = str((modules_root / OXLINT_BIN_RELPATH).parent)
    path_value = os.environ.get("PATH", "")
    parts = [part for part in path_value.split(os.pathsep) if part]
    if bin_dir not in parts:
        os.environ["PATH"] = os.pathsep.join([bin_dir, *parts]) if parts else bin_dir
    os.environ.setdefault("NODE_PATH", str(node_modules_path(root=root)))


def pytest_collection_modifyitems(session, config, items):
    """Fail every collected test with the stored host-linter setup error.

    The error is recorded in ``pytest_configure``. Each test keeps its own
    node id and is reported as failed with that reason; fixture setup is
    skipped because every fixture here depends on the host linter.
    """
    if _HOST_SETUP_ERROR is None:
        return
    reason = _HOST_SETUP_ERROR

    def _fail() -> None:
        pytest.fail(reason, pytrace=False)

    for item in items:
        item.setup = lambda: None
        item.runtest = _fail


def pytest_sessionstart(session):
    """Re-pin after collection so a leaked chdir cannot retarget the product."""
    global _SESSION_PRODUCT_ROOT
    if _SESSION_PRODUCT_ROOT:
        os.environ[PRODUCT_ROOT_ENV] = _SESSION_PRODUCT_ROOT
        return
    root = repo_root()
    os.environ.setdefault(PRODUCT_ROOT_ENV, str(root))
    _SESSION_PRODUCT_ROOT = os.environ[PRODUCT_ROOT_ENV]


def _restore_environ(previous_env: dict[str, str]) -> None:
    """Replace the process environment without clearing the C environ first.

    ``os.environ.clear()`` empties the native environ; a child spawned in
    that window, or a C extension that re-reads PATH, sees a hollow
    process. Drop keys that were not in the snapshot, then write the
    snapshot back. Re-apply the session product root last so a test that
    unset it cannot retarget later features. Re-apply the host-linter
    bin on PATH so a test that stripped PATH cannot hide oxlint from a
    later feature in the combined run.
    """
    for key in list(os.environ.keys()):
        if key not in previous_env:
            del os.environ[key]
    for key, value in previous_env.items():
        os.environ[key] = value
    if _SESSION_PRODUCT_ROOT:
        os.environ[PRODUCT_ROOT_ENV] = _SESSION_PRODUCT_ROOT
    try:
        modules_root = host_modules_root()
        bin_dir = str((modules_root / OXLINT_BIN_RELPATH).parent)
    except OSError:
        return
    path_value = os.environ.get("PATH", "")
    parts = [part for part in path_value.split(os.pathsep) if part]
    if bin_dir not in parts:
        os.environ["PATH"] = os.pathsep.join([bin_dir, *parts]) if parts else bin_dir
    os.environ.setdefault("NODE_PATH", str(node_modules_path()))


def _restore_cwd(previous_cwd: str) -> None:
    """Restore cwd; if that directory was torn down, fall back to session cwd."""
    target = previous_cwd
    if not os.path.isdir(target):
        target = _SESSION_CWD
    try:
        os.chdir(target)
    except OSError:
        if os.path.isdir(_SESSION_CWD):
            os.chdir(_SESSION_CWD)


@pytest.fixture
def workspace_root() -> Path:
    """Absolute path of the built repository root (pytest process cwd)."""
    return repo_root()


@pytest.fixture
def product_copy_script(workspace_root: Path) -> Path:
    """Absolute path of the skill-copy entry script.

    Raises ``FileNotFoundError`` at fixture setup if the script is
    missing — that is a substrate gap, not a product-behavior judgment.
    """
    return copy_script(root=workspace_root)


@pytest.fixture
def oxlint_bin(workspace_root: Path) -> str:
    """Absolute path of the host-linter executable.

    Raises ``FileNotFoundError`` if oxlint is not in the built tree or
    on ``PATH``.
    """
    return oxlint_executable(root=workspace_root)


@pytest.fixture
def node_bin() -> str:
    """Absolute path of the Node interpreter used to run the copy entry.

    Raises ``FileNotFoundError`` if ``node`` is not on ``PATH``.
    """
    return node_executable()


@pytest.fixture
def isolated_ws():
    """Yield an ephemeral work directory with isolated HOME; tear down after."""
    with workspace() as ws:
        yield ws


@pytest.fixture(autouse=True)
def _restore_process_state():
    """Restore cwd, environ, argv, and stdio after each test.

    Isolation helpers push those values for the duration of a call; this
    fixture still resets them if a test mutates them directly. Combined
    original-name pytest shares one process across F01–F07: a leaked
    cwd or PRODUCT_ROOT would make a later feature observe the wrong tree.
    """
    previous_cwd = os.getcwd()
    previous_env = os.environ.copy()
    previous_argv = list(sys.argv)
    previous_stdin = sys.stdin
    previous_stdout = sys.stdout
    previous_stderr = sys.stderr
    try:
        yield
    finally:
        _restore_cwd(previous_cwd)
        _restore_environ(previous_env)
        sys.argv = previous_argv
        sys.stdin = previous_stdin
        sys.stdout = previous_stdout
        sys.stderr = previous_stderr
