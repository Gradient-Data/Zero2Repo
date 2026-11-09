# feature: F15
"""Isolated CLI invocations using the existing build and process drivers."""

import pytest

from _helpers import isolated_workspace, run_process, write_files
from F10_helpers import f10_cli


@pytest.fixture(scope="module")
def f15_run(f10_cli):
    binary, built = f10_cli

    def run(arguments, *, files=None, proxy="off", input=b"", unreadable=()):
        with isolated_workspace(base_env=built.env,
                                overrides={"GOPROXY": proxy, "ZELVIROCACHE": "off"}) as work:
            paths = write_files(work.cwd, files or {})
            for name in unreadable:
                paths[name].chmod(0)
            try:
                return run_process([binary, *arguments], cwd=work.cwd, env=work.env,
                                   input=input, timeout=45)
            finally:
                for name in unreadable:
                    paths[name].chmod(0o600)

    return run


def f15_output(result, expected):
    assert result.returncode == 0, result
    assert result.stdout == expected, result
