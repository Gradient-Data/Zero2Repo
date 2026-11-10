from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from cbrun import claude_resume as cr

# Prints the scripted outcome for this call and records its argv.
FAKE_CLAUDE = r"""
import json, sys
from pathlib import Path
state = Path(sys.argv[1])
calls = json.loads(state.read_text())
n = len(calls["argv"])
calls["argv"].append(sys.argv[2:])
state.write_text(json.dumps(calls))
kind = calls["script"][n]
def emit(e):
    print(json.dumps(e), flush=True)
if kind in ("cut", "work", "client"):
    emit({"type": "assistant", "message": {"id": f"m{n}", "model": "hy4", "content": [{"type": "text", "text": "working"}]}})
if kind == "submit":
    Path(calls["submit_file"]).write_text(calls["token"] + "\n")
if kind in ("cut", "idle", "client"):
    status = 402 if kind == "client" else None
    emit({"type": "assistant", "message": {"id": f"e{n}", "model": "<synthetic>", "content": [{"type": "text", "text": "API Error: stream closed before completion"}]}})
if kind == "cut_bg":
    status = None
    emit({"type": "assistant", "message": {"id": f"e{n}", "model": "<synthetic>", "content": [{"type": "text", "text": "API Error: stream closed before completion"}]}})
    emit({"type": "assistant", "parent_tool_use_id": "t1", "message": {"id": f"b{n}", "model": "hy4", "content": [{"type": "text", "text": "background work"}]}})
if kind in ("cut", "idle", "client", "cut_bg"):
    emit({"type": "result", "subtype": "success", "is_error": True, "api_error_status": status, "session_id": "s1", "result": "API Error: stream closed before completion"})
    sys.exit(1)
emit({"type": "result", "subtype": "success", "is_error": False, "stop_reason": "end_turn", "session_id": "s1", "result": "Done."})
"""


TOKEN = "SUBMIT_ME"


def _run(
    tmp_path: Path, script: list[str], monkeypatch: pytest.MonkeyPatch, *, submitted: bool = True
) -> tuple[int, list[list[str]], list[dict], list[int]]:
    """Run the scripted calls. ``submitted`` writes the submit file up front."""
    fake = tmp_path / "fake_claude.py"
    fake.write_text(FAKE_CLAUDE)
    submit = tmp_path / "submit"
    if submitted:
        submit.write_text(TOKEN + "\n")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"script": script, "argv": [], "submit_file": str(submit), "token": TOKEN}))
    instruction = tmp_path / "instruction.md"
    instruction.write_text("Build it.")
    log = tmp_path / "agent.log"
    waits: list[int] = []
    monkeypatch.setattr(cr.time, "sleep", waits.append)
    code = cr.main([
        str(log), str(instruction), str(submit), TOKEN, "--",
        sys.executable, str(fake), str(state), "--print",
    ])
    argv = json.loads(state.read_text())["argv"]
    events = [json.loads(line) for line in log.read_text().splitlines()]
    return code, argv, events, waits


def test_stream_cut_resumes_the_same_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, argv, events, waits = _run(tmp_path, ["cut", "done"], monkeypatch)
    assert code == 0
    assert argv == [["--print"], ["--print", "--resume", "s1", cr.RESUME_PROMPT]]
    resumes = [e for e in events if e.get("subtype") == cr.RESUME_EVENT]
    assert len(resumes) == 1
    assert resumes[0]["session_id"] == "s1"
    assert resumes[0]["error"] == "API Error: stream closed before completion"
    assert waits == [15]
    assert events[-1]["result"] == "Done."


def test_background_subagent_after_the_error_does_not_hide_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, argv, _events, _waits = _run(tmp_path, ["cut_bg", "done"], monkeypatch)
    assert code == 0
    assert argv == [["--print"], ["--print", "--resume", "s1", cr.RESUME_PROMPT]]


@pytest.mark.parametrize("script", [["done"], ["client"]])
def test_own_end_and_client_errors_are_not_resumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: list[str]
) -> None:
    _code, argv, events, _waits = _run(tmp_path, script, monkeypatch)
    assert len(argv) == 1
    assert not [e for e in events if e.get("subtype") == cr.RESUME_EVENT]


def test_resumes_stop_after_repeated_failures_without_model_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, argv, _events, waits = _run(tmp_path, ["cut", "idle", "cut", "idle", "idle", "idle", "done"], monkeypatch)
    # The model answered on the third call, so the idle count restarts there.
    assert len(argv) == 6
    assert code == 1
    assert waits == [15, 30, 15, 30, 60]


def _resumes(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("subtype") == cr.RESUME_EVENT]


def test_turn_ended_without_submit_resumes_until_submitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, argv, events, waits = _run(tmp_path, ["done", "submit"], monkeypatch, submitted=False)
    assert code == 0
    assert argv == [["--print"], ["--print", "--resume", "s1", cr.NO_SUBMIT_PROMPT]]
    assert [e["reason"] for e in _resumes(events)] == ["no_submit"]
    assert waits == []


def test_no_submit_resumes_are_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _code, argv, events, _waits = _run(tmp_path, ["done"] * 10, monkeypatch, submitted=False)
    assert len(argv) == 1 + cr.MAX_NO_SUBMIT_RESUMES
    assert len(_resumes(events)) == cr.MAX_NO_SUBMIT_RESUMES


def test_a_wrong_submit_token_counts_as_no_submit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "submit").write_text("done\n")
    _code, argv, _events, _waits = _run(tmp_path, ["done", "submit"], monkeypatch, submitted=False)
    assert len(argv) == 2


def test_api_error_then_unsubmitted_end_resumes_each_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _code, argv, events, waits = _run(tmp_path, ["cut", "done", "submit"], monkeypatch, submitted=False)
    assert [a[-1] for a in argv[1:]] == [cr.RESUME_PROMPT, cr.NO_SUBMIT_PROMPT]
    assert [e["reason"] for e in _resumes(events)] == ["api_error", "no_submit"]
    assert waits == [15]


def test_unrecoverable_api_error_is_not_resumed_for_a_missing_submit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _code, argv, _events, _waits = _run(tmp_path, ["client"], monkeypatch, submitted=False)
    assert len(argv) == 1
