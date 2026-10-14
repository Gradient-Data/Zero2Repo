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
    """Restore cwd, environ, argv, and stdio after each test.

    Isolation helpers push those values for the duration of a call; this
    fixture still resets them if a test mutates them directly.
    """
    previous_cwd = os.getcwd()
    previous_env = os.environ.copy()
    previous_argv = list(sys.argv)
    previous_stdin = sys.stdin
    previous_stdout = sys.stdout
    previous_stderr = sys.stderr
    previous_time = sys.modules.get("time")
    previous_time_fn = getattr(previous_time, "time", None) if previous_time else None
    previous_time_ns_fn = (
        getattr(previous_time, "time_ns", None) if previous_time else None
    )
    previous_datetime_mod = sys.modules.get("datetime")
    previous_datetime_cls = (
        getattr(previous_datetime_mod, "datetime", None)
        if previous_datetime_mod
        else None
    )
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
        time_mod = sys.modules.get("time")
        if previous_time is not None and previous_time_fn is not None and time_mod is previous_time:
            time_mod.time = previous_time_fn
        if (
            previous_time is not None
            and previous_time_ns_fn is not None
            and time_mod is previous_time
        ):
            time_mod.time_ns = previous_time_ns_fn
        datetime_mod = sys.modules.get("datetime")
        if (
            previous_datetime_mod is not None
            and previous_datetime_cls is not None
            and datetime_mod is previous_datetime_mod
        ):
            datetime_mod.datetime = previous_datetime_cls
