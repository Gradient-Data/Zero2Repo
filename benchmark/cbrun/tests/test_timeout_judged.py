"""A solve the wall clock cuts off is judged; one that ends early unsubmitted is not."""

from __future__ import annotations

from pathlib import Path

from cbrun.docker_env import ExecResult
from cbrun.results import TrialResult
from cbrun.run_case import _record_submit_outcome
from cbrun.submit import NO_SUBMIT_ERROR


class _NoSubmitContainer:
    def exec(self, command: str, **_kwargs) -> ExecResult:
        return ExecResult(exit_code=1)


def _outcome(tmp_path: Path, solve: ExecResult) -> tuple[bool, TrialResult]:
    result = TrialResult(case_id="c", backend="codex", model="m", reward=0.0, terminal_status="error")
    judge = _record_submit_outcome(
        _NoSubmitContainer(),  # type: ignore[arg-type]
        result,
        solve=solve,
        solve_start=0.0,
        out_dir=tmp_path,
    )
    return judge, result


def test_unsubmitted_timeout_is_judged(tmp_path: Path) -> None:
    judge, result = _outcome(tmp_path, ExecResult(exit_code=137, timed_out=True))
    assert judge
    assert result.terminal_status == "timeout"
    assert result.error is None


def test_unsubmitted_early_exit_is_not_judged(tmp_path: Path) -> None:
    judge, result = _outcome(tmp_path, ExecResult(exit_code=0))
    assert not judge
    assert result.terminal_status == "error"
    assert result.error == NO_SUBMIT_ERROR
