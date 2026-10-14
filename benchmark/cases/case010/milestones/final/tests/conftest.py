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

from _harness import repo_root, workspace  # noqa: E402


@pytest.fixture
def workspace_root() -> Path:
    """Absolute path of the built repository root (pytest process cwd)."""
    return repo_root()


@pytest.fixture
def isolated_ws():
    """Yield an ephemeral work directory with isolated HOME; tear down after."""
    with workspace() as ws:
        yield ws


@pytest.fixture(autouse=True)
def _restore_process_state():
    """Restore cwd, environ, and argv after each test.

    Isolation helpers push those values for the duration of a call; this
    fixture still resets them if a test mutates them directly.
    """
    previous_cwd = os.getcwd()
    previous_env = os.environ.copy()
    previous_argv = list(sys.argv)
    try:
        yield
    finally:
        os.chdir(previous_cwd)
        os.environ.clear()
        os.environ.update(previous_env)
        sys.argv = previous_argv


# Each test body runs in its own fresh interpreter. Product state (a loaded
# model, a cached corpus) therefore never carries from one test into the
# next, and no test needs to reach into the product to reset it. The parent
# pytest process only reports the child's outcome.
_FRESH_CHILD_FLAG = "CB_FRESH_INTERPRETER_CHILD"
_FRESH_CHILD_TIMEOUT = 600


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    if os.environ.get(_FRESH_CHILD_FLAG) == "1":
        return None
    import subprocess

    env = dict(os.environ)
    env[_FRESH_CHILD_FLAG] = "1"
    target = f"{pyfuncitem.path}::{pyfuncitem.name}"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--rootdir",
        str(pyfuncitem.config.rootpath),
        target,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=os.getcwd(),
            env=env,
            capture_output=True,
            text=True,
            timeout=_FRESH_CHILD_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(f"fresh-interpreter run of {target} timed out") from exc
    output = (proc.stdout or "") + (proc.stderr or "")
    print(output[-20000:], flush=True)
    if proc.returncode != 0:
        raise AssertionError(
            f"{target} failed in a fresh interpreter (exit {proc.returncode})"
        )
    if " passed" not in proc.stdout or " failed" in proc.stdout or " error" in proc.stdout:
        raise AssertionError(f"{target}: fresh-interpreter run did not pass cleanly")
    return True
