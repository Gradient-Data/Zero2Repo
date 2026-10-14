"""Exercise completeness through real pytest processes, without synthetic logs."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

HARBOR = Path(__file__).resolve().parents[1] / "coding_bench_harbor"
sys.path.insert(0, str(HARBOR))
import final_judge as fj


def run_suite(tmp_path, body, *args, conftest=None):
    suite = tmp_path / "suite"
    workspace = tmp_path / "app"
    suite.mkdir()
    workspace.mkdir()
    test_file = suite / "test_arithmetic.py"
    test_file.write_text(body, encoding="utf-8")
    if conftest is not None:
        (suite / "conftest.py").write_text(conftest, encoding="utf-8")
    env = os.environ.copy()
    env.update(CODING_BENCH_WORKSPACE=str(workspace),
               CODING_BENCH_TESTS_FINAL=str(suite))
    proc = subprocess.run(
        [sys.executable, "-I", str(HARBOR / "pytest_launcher.py"),
         str(test_file), "-q", *args], env=env, capture_output=True, text=True,
    )
    result = fj._result_from_proc(proc, log_path=tmp_path / "output.log",
                                  test_command="python -m pytest")
    receipts = [line.split("=", 1)[1] for line in proc.stdout.splitlines()
                if line.startswith("CODING_BENCH_COLLECTION_AUDIT=")]
    assert len(receipts) == 1, proc.stdout + proc.stderr
    return result, json.loads(receipts[0])


def test_full_parameterized_execution_is_accepted(tmp_path):
    result, receipt = run_suite(tmp_path, "import pytest\n"
        "@pytest.mark.parametrize('n', range(3))\n"
        "def test_square(n): assert n*n >= 0\n")
    fj._apply_collection_gate(result)
    assert result["status"] == "passed"
    assert len(receipt["collected"]) == 3
    assert not receipt["issues"]


@pytest.mark.parametrize("option", ["-k", "-m"])
def test_filtered_execution_is_incomplete(tmp_path, option):
    result, receipt = run_suite(tmp_path,
        "import pytest\n@pytest.mark.selected\n"
        "def test_selected(): assert 2+2 == 4\n"
        "def test_other(): assert 3*3 == 9\n", option, "selected")
    with pytest.raises(fj.JudgeError, match="incomplete"):
        fj._apply_collection_gate(result)
    assert len(receipt["collected"]) == 2
    assert len(receipt["selected"]) == 1


@pytest.mark.parametrize("decoration,body", [
    ("@pytest.mark.skip(reason='deliberate completeness probe')", "assert True"),
    ("@pytest.mark.xfail", "assert 1 == 2"),
    ("@pytest.mark.xfail", "assert 1 == 1"),
])
def test_nonstandard_outcomes_are_incomplete(tmp_path, decoration, body):
    result, receipt = run_suite(tmp_path, "import pytest\n"
        "def test_normal(): assert 2+2 == 4\n"
        f"{decoration}\ndef test_exceptional(): {body}\n")
    with pytest.raises(fj.JudgeError, match="incomplete"):
        fj._apply_collection_gate(result)
    assert receipt["issues"]
    assert result["skipped_count"] == 1


def test_stop_after_failure_is_incomplete(tmp_path):
    result, receipt = run_suite(tmp_path,
        "def test_first(): assert 1 == 2\n"
        "def test_later(): assert 2+2 == 4\n", "-x")
    with pytest.raises(fj.JudgeError, match="incomplete"):
        fj._apply_collection_gate(result)
    assert len(receipt["reports"]) < len(receipt["collected"])


def test_complete_failure_remains_test_failure(tmp_path):
    result, receipt = run_suite(tmp_path,
        "def test_first(): assert 1 == 2\n"
        "def test_later(): assert 2+2 == 4\n")
    fj._apply_collection_gate(result)
    assert result["status"] == "failed"
    assert not receipt["issues"]


def test_setup_error_remains_test_error(tmp_path):
    result, receipt = run_suite(tmp_path,
        "import pytest\n@pytest.fixture\ndef broken(): raise ValueError('setup failed')\n"
        "def test_first(broken): assert broken\n"
        "def test_later(): assert 2+2 == 4\n")
    fj._apply_collection_gate(result)
    assert result["status"] == "failed"
    assert result["error_count"] == 1
    assert not receipt["issues"]


def test_silent_collection_removal_is_incomplete(tmp_path):
    result, receipt = run_suite(tmp_path,
        "def test_first(): assert 1+1 == 2\n"
        "def test_later(): assert 2+2 == 4\n",
        conftest="def pytest_collection_modifyitems(items): items.pop()\n")
    with pytest.raises(fj.JudgeError, match="incomplete"):
        fj._apply_collection_gate(result)
    assert "selected tests differ from collected tests" in receipt["issues"]


def test_collection_level_skip_is_incomplete(tmp_path):
    result, receipt = run_suite(tmp_path,
        "import pytest\npytest.skip('collection probe', allow_module_level=True)\n"
        "def test_first(): assert 1+1 == 2\n")
    with pytest.raises(fj.JudgeError, match="incomplete"):
        fj._apply_collection_gate(result)
    assert any(issue.startswith("skipped collection") for issue in receipt["issues"])
