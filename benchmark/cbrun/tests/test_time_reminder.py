"""Wall-clock reminders: schedule, delivery state, and the per-agent install."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from cbrun import time_reminder as tr
from cbrun.agent_spec import _TIME_REMINDER_SETUPS, BACKENDS, CONTAINER_WORKDIR, resolve_agent
from cbrun.docker_env import Container, ExecResult
from cbrun.run_case import _run_agent_setup
from cbrun.submit import CONTAINER_SUBMIT_PATH, SUBMIT_TOKEN

_ENV = {
    "OPENAI_API_KEY": "k",
    "ANTHROPIC_API_KEY": "k",
    "CURSOR_API_KEY": "k",
    "LLM_API_KEY": "k",
    "LLM_BASE_URL": "http://gateway",
    "OPENROUTER_API_KEY": "k",
}


def _invocation(backend: str):
    model = "openrouter/vendor/model" if backend == "opencode" else "vendor/model"
    return resolve_agent(backend=backend, model=model, environ=_ENV)


@pytest.fixture
def state(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tr, "STATE_DIR", tmp_path / "cbrun")
    monkeypatch.setattr(tr, "DEADLINE_FILE", tmp_path / "cbrun" / "deadline.json")
    monkeypatch.setattr(tr, "SENT_FILE", tmp_path / "cbrun" / "sent.json")
    monkeypatch.setattr(tr, "LOCK_FILE", tmp_path / "cbrun" / "lock")
    monkeypatch.setattr(tr, "AUDIT_LOG", tmp_path / "logs" / "time_reminders.jsonl")
    return tmp_path


def test_schedule_follows_the_remaining_time():
    assert tr.reminder_points(21600) == [
        21600, 18000, 14400, 10800, 7200, 3600,
        1800, 1200, 600, 300, 240, 180, 120, 60, 30,
    ]
    assert tr.reminder_points(7200) == [7200, 3600, 1800, 1200, 600, 300, 240, 180, 120, 60, 30]
    # Odd budgets still land on every interval boundary.
    assert tr.reminder_points(5000) == [5000, 3600, 1800, 1200, 600, 300, 240, 180, 120, 60, 30]
    assert tr.reminder_points(150) == [150, 90, 60, 30]


def test_reminder_names_the_real_submit_contract():
    assert (tr.SUBMIT_PATH, tr.SUBMIT_TOKEN, tr.WORKDIR) == (
        CONTAINER_SUBMIT_PATH, SUBMIT_TOKEN, CONTAINER_WORKDIR,
    )
    text = tr.reminder_text(3725, 7200)
    assert text.startswith("Time check: 1h 2m 5s of this session's wall-clock budget remain (budget 2h).")
    assert f"{CONTAINER_SUBMIT_PATH} with the single line {SUBMIT_TOKEN}" in text


def test_each_due_point_reaches_each_agent_once(state: Path):
    tr.init(300, now=1000.0)
    first = tr.due_reminder("main", event="start", now=1000.0)
    assert first and first.startswith("Time check: 5m ")
    assert tr.due_reminder("main", event="tool", now=1030.0) is None
    # A subagent has its own delivery state.
    assert tr.due_reminder("sub", event="start", now=1030.0).startswith("Time check: 4m 30s")
    assert tr.due_reminder("main", event="tool", now=1059.0) is None
    assert tr.due_reminder("main", event="tool", now=1061.0).startswith("Time check: 3m 59s")
    # A long gap delivers only the latest point that is due.
    assert tr.due_reminder("main", event="tool", now=1250.0).startswith("Time check: 50s")
    assert tr.due_reminder("main", event="tool", now=1255.0) is None
    audit = [json.loads(line) for line in (state / "logs" / "time_reminders.jsonl").read_text().splitlines()]
    assert [(row["agent"], row["point"]) for row in audit] == [
        ("main", 300), ("sub", 300), ("main", 240), ("main", 60),
    ]


def test_init_rejects_a_missing_budget(state: Path):
    with pytest.raises(SystemExit):
        tr.init(0)


def test_hook_output_matches_each_agent_contract():
    text = "Time check: 1m"
    assert json.loads(tr.render("claude", "PostToolUse", text)) == {
        "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text},
    }
    assert json.loads(tr.render("codex", "UserPromptSubmit", text))["hookSpecificOutput"] == {
        "hookEventName": "UserPromptSubmit", "additionalContext": text,
    }
    assert json.loads(tr.render("openhands", "UserPromptSubmit", text)) == {"additionalContext": text}
    assert json.loads(tr.render("cursor", "postToolUse", text)) == {"additional_context": text}
    assert tr.render("claude", "PostToolUse", None) == ""
    assert json.loads(tr.render("cursor", "postToolUse", None)) == {}


@pytest.mark.parametrize("backend", BACKENDS)
def test_every_builtin_agent_installs_and_arms_the_reminder(backend: str, tmp_path: Path):
    inv = _invocation(backend)
    assert _TIME_REMINDER_SETUPS[backend] in inv.setup_script
    assert inv.command.startswith(f'python3 {tr.CONTAINER_PATH} init "$CBRUN_WALL_SEC" && ')

    class FakeContainer:
        def __init__(self):
            self.files: dict[str, bytes] = {}

        def exec(self, command, **kwargs):
            return ExecResult(exit_code=0, timed_out=False, seconds=0.0, tail="")

        def write_file(self, path, data):
            self.files[path] = data

    container = FakeContainer()
    _run_agent_setup(container, inv, out_dir=tmp_path)
    assert container.files[tr.CONTAINER_PATH] == Path(tr.__file__).read_bytes()


def test_codex_runs_the_hooks_cbrun_installed():
    assert "--dangerously-bypass-hook-trust" in _invocation("codex").command


def _run_hook_install(backend: str, home: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        ["bash", "-c", _TIME_REMINDER_SETUPS[backend]],
        check=True,
        capture_output=True,
        env={"PATH": os.environ["PATH"], "HOME": str(home), **(env or {})},
    )


def test_claude_hooks_merge_into_existing_settings(tmp_path: Path):
    config = tmp_path / ".claude"
    config.mkdir()
    (config / "settings.json").write_text(json.dumps({"model": "keep-me", "hooks": {"Stop": [{"hooks": []}]}}))
    _run_hook_install("claude-code", tmp_path)
    _run_hook_install("claude-code", tmp_path)
    settings = json.loads((config / "settings.json").read_text())
    assert settings["model"] == "keep-me"
    assert settings["hooks"]["Stop"] == [{"hooks": []}]
    assert settings["hooks"]["PostToolUse"] == [{
        "matcher": "*",
        "hooks": [{"type": "command", "command": f"python3 {tr.CONTAINER_PATH} hook claude PostToolUse"}],
    }]
    assert len(settings["hooks"]["UserPromptSubmit"]) == 1


def test_cursor_and_codex_hook_files(tmp_path: Path):
    _run_hook_install("cursor", tmp_path)
    cursor = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
    assert cursor["version"] == 1
    assert set(cursor["hooks"]) == {"sessionStart", "beforeSubmitPrompt", "postToolUse"}
    codex_home = tmp_path / "codex-home"
    _run_hook_install("codex", tmp_path, {"CODEX_HOME": str(codex_home)})
    codex = json.loads((codex_home / "hooks.json").read_text())
    assert set(codex["hooks"]) == {"UserPromptSubmit", "PostToolUse"}


def test_openhands_relies_on_the_patch_for_tool_results(tmp_path: Path):
    # Its PostToolUse context never reaches the model, and a hook there would
    # use up reminders the patched tool results should carry.
    script = _TIME_REMINDER_SETUPS["openhands"]
    hooks_part = script.split("python3 - << 'PY'\nimport os", 1)[0]
    subprocess.run(
        ["bash", "-c", hooks_part],
        check=True,
        capture_output=True,
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
    )
    hooks = json.loads((tmp_path / ".openhands" / "hooks.json").read_text())
    assert set(hooks["hooks"]) == {"UserPromptSubmit"}
    assert "_cbrun_time_reminder(self.id)" in script


def test_opencode_plugin_hooks_prompt_and_tool_results():
    script = _invocation("opencode").setup_script
    assert '"chat.message"' in script and '"tool.execute.after"' in script
    assert "/opencode/plugin\"" in script and "cbrun-time-reminder.js" in script


def test_solve_exec_exposes_the_wall_budget(monkeypatch, tmp_path: Path):
    seen = {}

    class Stop(Exception):
        pass

    def fake_popen(argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs["env"]
        raise Stop

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    with pytest.raises(Stop):
        Container("cid").exec_solve(
            "true", workdir="/app", env={"A": "1"}, wall_timeout_sec=7200.0,
            stall_window_sec=0, log_path=tmp_path / "agent.log", stall_marker="/x",
        )
    assert seen["env"]["CBRUN_WALL_SEC"] == "7200"
    assert "CBRUN_WALL_SEC" in seen["argv"]
