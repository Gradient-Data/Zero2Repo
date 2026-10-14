"""Summary-format compatibility, including real pytest through the judge."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import final_judge as fj
from test_counts import parse_test_counts


@pytest.mark.parametrize("bordered", [False, True])
@pytest.mark.parametrize("colored", [False, True])
@pytest.mark.parametrize("body, expected", [
    ("7 passed in 0.12s", (7, 0, 0, 0)),
    ("2 failed, 7 passed, 3 skipped, 4 deselected, 1 error, 2 warnings in 61.25s (0:01:01)",
     (7, 2, 1, 7)),
    ("2 errors in 0.12s", (0, 0, 2, 0)),
    ("1 passed, 1 xfailed, 1 xpassed, 1 rerun, 1 warning in 3601.25s (1:00:01)",
     (1, 0, 0, 0)),
])
def test_pytest_summary_formats(body, expected, bordered, colored):
    summary = f"===== {body} =====" if bordered else body
    if colored:
        summary = "\x1b[32m" + summary.replace(" in ", "\x1b[0m\x1b[32m in ") + "\x1b[0m"
    c = parse_test_counts(summary + "\n", test_command="python3 -m pytest -q")
    assert c is not None
    assert (c.passed, c.failed, c.errors, c.skipped) == expected
    assert c.framework == "pytest"


@pytest.mark.parametrize("output", [
    "no tests ran in 0.01s",
    "4 skipped in 0.01s",
    "4 deselected in 0.01s",
    "2 xfailed in 0.01s",
    "1 passed",
    "collected 7 items",
    "Expected 7 passed in 0.12s",
    "E   AssertionError: 7 passed in 0.12s",
    "7 passed in 0.12s (truncated",
    "7 passed in 0.12s trailing text",
])
def test_pytest_rejects_missing_or_non_summary_counts(output):
    assert parse_test_counts(output, test_command="pytest -q") is None


def test_pytest_last_summary_preserves_failures():
    output = "===== 7 passed in 0.12s =====\n2 failed, 1 passed in 0.14s\n"
    c = parse_test_counts(output, test_command="pytest -q")
    assert c is not None
    assert (c.passed, c.failed, c.total) == (1, 2, 3)
    assert c.pass_rate == 1 / 3


@pytest.mark.parametrize("options", [[], ["-q"], ["-q", "--color=yes"]])
@pytest.mark.parametrize("source, expected, exit_code", [
    ("def test_addition(): assert 1 + 2 == 3\n", (1, 0, 0), 0),
    ("def test_addition(): assert 1 + 2 == 3\n"
     "def test_wrong_addition(): assert 1 + 2 == 4\n", (1, 1, 0), 1),
    ("import pytest\n@pytest.fixture\ndef resource(): raise RuntimeError('setup failed')\n"
     "def test_resource(resource): assert resource\n", (0, 0, 1), 1),
    ("import pytest\n@pytest.mark.skip(reason='not executed')\n"
     "def test_skipped(): assert False\n", None, 0),
    ("", None, 5),
])
def test_real_pytest_output_through_collection_gate(tmp_path, options, source, expected, exit_code):
    """Run real pytest, then feed its unmodified output through the judge."""
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(source, encoding="utf-8")
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    command = [sys.executable, "-m", "pytest", "-c", str(config), *options, str(test_file)]
    proc = subprocess.run(
        command, cwd=tmp_path, capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTEST_ADDOPTS": "", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
    )
    assert proc.returncode == exit_code, proc.stdout + proc.stderr
    result = fj._result_from_proc(
        proc, log_path=tmp_path / "judge.log", test_command="python3 -m pytest",
        framework_label="pytest",
    )
    if expected is None:
        with pytest.raises(fj.JudgeError, match="parseable executed-test summary"):
            fj._apply_collection_gate(result)
        return
    passed, failed, errors = expected
    assert (result["passed_count"], result["failed_count"], result["error_count"]) == expected
    total = passed + failed + errors
    fj._apply_collection_gate(result, {"expected_test_count": total})
    assert result["status"] == ("passed" if exit_code == 0 else "failed")
    with pytest.raises(fj.JudgeError, match="executed test count"):
        fj._apply_collection_gate(result, {"expected_test_count": total + 1})
