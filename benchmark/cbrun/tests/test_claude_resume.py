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
if kind in ("cut", "idle", "client"):
    status = 402 if kind == "client" else None
    emit({"type": "assistant", "message": {"id": f"e{n}", "model": "<synthetic>", "content": [{"type": "text", "text": "API Error: stream closed before completion"}]}})
    emit({"type": "result", "subtype": "success", "is_error": True, "api_error_status": status, "session_id": "s1", "result": "API Error: stream closed before completion"})
    sys.exit(1)
emit({"type": "result", "subtype": "success", "is_error": False, "stop_reason": "end_turn", "session_id": "s1", "result": "Done."})
"""


def _run(tmp_path: Path, script: list[str], monkeypatch: pytest.MonkeyPatch) -> tuple[int, list[list[str]], list[dict], list[int]]:
    fake = tmp_path / "fake_claude.py"
    fake.write_text(FAKE_CLAUDE)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"script": script, "argv": []}))
    instruction = tmp_path / "instruction.md"
    instruction.write_text("Build it.")
    log = tmp_path / "agent.log"
    waits: list[int] = []
    monkeypatch.setattr(cr.time, "sleep", waits.append)
    code = cr.main([str(log), str(instruction), "--", sys.executable, str(fake), str(state), "--print"])
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
