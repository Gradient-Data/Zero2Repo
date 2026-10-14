# feature: F00
"""Pytest fixtures and import-path setup for the shared suite harness.

Reusable invocation / isolation machinery lives in ``_harness``; this
module only wires pytest to that machinery and ensures
``from _harness import ...`` resolves when tests are collected from the
repository root. A session fixture runs ``make pylib replay`` and then
places the package directory on ``sys.path`` so a suite that imports the
documented Python surface can do so. That call is not made at import, so
collection succeeds when the package tree is absent. This module itself
does not import the product.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from _harness import (  # noqa: E402
    TEST_SEED_ENV,
    Workspace,
    compile_repository,
    ensure_import_path,
    repo_root,
    reseed_for_test,
    session_seed,
    workspace,
)


def pytest_report_header(config):
    """Print the runtime-randomisation seed; rerun with it to reproduce."""
    return f"runtime randomisation: {TEST_SEED_ENV}={session_seed()}"


@pytest.fixture(autouse=True)
def _reseed_runtime_rng(request):
    """Reseed per test from (session seed, file::test) so one test reproduces alone."""
    reseed_for_test(f"{Path(str(request.node.fspath)).name}::{request.node.name}")
    yield


@pytest.fixture(scope="session", autouse=True)
def _compile_pylib_and_replay():
    """Compile the shared library and replay before tests load them.

    The review judge records ``make pylib replay`` and then skips it.
    The suite runs that command itself. A missing shared object before
    the command is not a failure, and a missing package does not abort
    collection.
    """
    compile_repository()
    try:
        ensure_import_path()
    except FileNotFoundError:
        return


@pytest.fixture
def workspace_root() -> Path:
    """Absolute path of the built repository root (pytest process cwd)."""
    return repo_root()


@pytest.fixture
def isolated_ws() -> Iterator[Workspace]:
    """Yield an ephemeral work directory with isolated HOME; tear down after.

    F00 recertification tests consume this fixture so the autouse isolation
    wiring is in the same collected suite as the compile/invoke machinery.
    """
    with workspace() as ws:
        yield ws


@pytest.fixture(autouse=True)
def _restore_process_state():
    """Restore cwd, environ, argv, import path, and stdio after each test.

    Isolation helpers push those values for the duration of a call; this
    fixture still resets them if a test mutates them directly. ``sys.path``
    is restored so a test that calls ``ensure_import_path`` cannot leak a
    mutated import order into the next collected item.
    """
    previous_cwd = os.getcwd()
    previous_env = os.environ.copy()
    previous_argv = list(sys.argv)
    previous_path = list(sys.path)
    previous_stdin = sys.stdin
    previous_stdout = sys.stdout
    previous_stderr = sys.stderr
    try:
        yield
    finally:
        os.chdir(previous_cwd)
        os.environ.clear()
        os.environ.update(previous_env)
        sys.argv = previous_argv
        sys.path[:] = previous_path
        sys.stdin = previous_stdin
        sys.stdout = previous_stdout
        sys.stderr = previous_stderr
