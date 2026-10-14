# feature: F00
"""Pytest fixtures and import-path setup for the shared suite harness.

Reusable invocation / isolation machinery lives in ``_harness``; this
module only wires pytest to that machinery and ensures
``from _harness import ...`` resolves when tests are collected from the
repository root.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from _harness import product_bin, repo_root, workspace  # noqa: E402


@pytest.fixture
def workspace_root() -> Path:
    """Absolute path of the built repository root (pytest process cwd)."""
    return repo_root()


@pytest.fixture
def product_binary(workspace_root: Path) -> Path:
    """Absolute path of the recipe-built product binary.

    Raises ``FileNotFoundError`` at fixture setup if the binary is missing
    — that is a build/substrate gap, not a product-behavior judgment.
    """
    return product_bin(root=workspace_root)


@pytest.fixture
def isolated_ws():
    """Yield an ephemeral work directory with isolated HOME; tear down after."""
    with workspace() as ws:
        yield ws


@pytest.fixture(autouse=True)
def _restore_process_state():
    """Restore cwd and environ after each test.

    Isolation helpers push those values for the duration of a call; this
    fixture still resets them if a test mutates them directly.
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
        os.chdir(previous_cwd)
        os.environ.clear()
        os.environ.update(previous_env)
        sys.argv = previous_argv
        sys.stdin = previous_stdin
        sys.stdout = previous_stdout
        sys.stderr = previous_stderr
