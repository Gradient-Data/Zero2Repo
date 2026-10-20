"""Usage collection, including Cursor lines written during the solve."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from cbrun.agent_spec import resolve_agent
from cbrun.pricing import lookup_model, trial_cost
from cbrun.usage import collect_trial_usage


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_cursor_hook_lines_sum_when_the_result_line_is_missing(tmp_path: Path):
    _write(tmp_path / "agent.log", '{"type":"thinking","text":"still going"}\n')
    rows = [
        {"generation_id": "g1", "input_tokens": 10, "output_tokens": 4, "cache_read_tokens": 100, "cache_write_tokens": 0},
        {"generation_id": "g1", "input_tokens": 12, "output_tokens": 5, "cache_read_tokens": 100, "cache_write_tokens": 1},
        {"generation_id": "g2", "input_tokens": 8, "output_tokens": 3, "cache_read_tokens": 40, "cache_write_tokens": 2},
        {"input_tokens": 1, "output_tokens": 1, "cache_read_tokens": 0, "cache_write_tokens": 0},
    ]
    _write(
        tmp_path / "container_logs" / "cursor_usage.jsonl",
        "".join(json.dumps(row) + "\n" for row in rows),
    )
    usage = collect_trial_usage(tmp_path)
    assert usage["input_tokens"] == 21
    assert usage["output_tokens"] == 9
    assert usage["cache_read_tokens"] == 140
    assert usage["cache_write_tokens"] == 3
    assert usage["total_tokens"] == 173
    assert usage["sources"] == ["cursor_response_hooks"]
    assert usage["complete"] is True
    assert usage["missing"] == []


def test_cursor_result_is_kept_when_hook_lines_also_exist(tmp_path: Path):
    _write(
        tmp_path / "agent.log",
        json.dumps(
            {
                "type": "result",
                "usage": {
                    "inputTokens": 100,
                    "outputTokens": 20,
                    "cacheReadTokens": 400,
                    "cacheWriteTokens": 0,
                },
            }
        )
        + "\n",
    )
    _write(
        tmp_path / "container_logs" / "cursor_usage.jsonl",
        json.dumps({"generation_id": "g1", "input_tokens": 1, "output_tokens": 1}) + "\n",
    )
    usage = collect_trial_usage(tmp_path)
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 20
    assert usage["cache_read_tokens"] == 400
    assert usage["sources"] == ["cursor_result"]
    assert usage["complete"] is True


def test_cursor_setup_writes_turn_ended_usage():
    invocation = resolve_agent(backend="cursor", model="grok-4.7")
    script = invocation.setup_script or ""
    assert 'case"turnEnded"' in script
    assert "/logs/agent/cursor_usage.jsonl" in script
    assert "/app" not in script


def test_openhands_jsonl_sums_completed_calls(tmp_path: Path):
    _write(tmp_path / "agent.log", "no usage here\n")
    rows = [
        {
            "model": "openai/gpt-6-sol",
            "prompt_tokens": 100,
            "completion_tokens": 7,
            "cache_read_tokens": 40,
            "cache_write_tokens": 10,
            "reasoning_tokens": 3,
            "response_id": "r1",
        },
        {
            "model": "openai/gpt-6-sol",
            "prompt_tokens": 20,
            "completion_tokens": 4,
            "cache_read_tokens": 5,
            "cache_write_tokens": 0,
            "reasoning_tokens": 1,
            "response_id": "r1",
        },
        {
            "model": "openai/gpt-6-sol",
            "prompt_tokens": 30,
            "completion_tokens": 2,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "response_id": "",
        },
    ]
    _write(
        tmp_path / "container_logs" / "openhands_usage.jsonl",
        "".join(json.dumps(row) + "\n" for row in rows),
    )
    usage = collect_trial_usage(tmp_path)
    # r1 keeps the later line (15 uncached + 5 cache + 4 output); the blank id adds 30 + 2.
    assert usage["input_tokens"] == 45
    assert usage["cache_read_tokens"] == 5
    assert usage["cache_write_tokens"] == 0
    assert usage["output_tokens"] == 6
    assert usage["reasoning_tokens"] == 1
    assert usage["sources"] == ["openhands_usage_log"]
    assert usage["complete"] is True
    assert usage["missing"] == []


def test_openhands_state_snapshot_fills_in_when_the_log_is_smaller(tmp_path: Path):
    _write(tmp_path / "agent.log", "killed\n")
    _write(
        tmp_path / "container_logs" / "openhands_usage.jsonl",
        json.dumps(
            {
                "prompt_tokens": 10,
                "completion_tokens": 1,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "response_id": "early",
            }
        )
        + "\n",
    )
    state = {
        "stats": {
            "usage_to_metrics": {
                "agent": {
                    "accumulated_token_usage": {
                        "prompt_tokens": 80,
                        "completion_tokens": 20,
                        "cache_read_tokens": 30,
                        "cache_write_tokens": 0,
                        "reasoning_tokens": 4,
                    }
                }
            }
        }
    }
    _write(
        tmp_path / "container_logs" / "usage" / "0" / "conversations" / "abc" / "base_state.json",
        json.dumps(state),
    )
    usage = collect_trial_usage(tmp_path)
    assert usage["input_tokens"] == 50
    assert usage["cache_read_tokens"] == 30
    assert usage["output_tokens"] == 20
    assert usage["sources"] == ["openhands_base_state"]


def test_openhands_setup_appends_each_completion():
    invocation = resolve_agent(
        backend="openhands",
        model="openai/gpt-6-sol",
        environ={"LLM_API_KEY": "test-key", "LLM_BASE_URL": "https://example.invalid/v1"},
    )
    script = invocation.setup_script or ""
    assert "self.token_usages.append(usage)" in script
    assert "/logs/agent/openhands_usage.jsonl" in script
    assert "/app" not in script


def test_prices_cover_sol_deepseek_and_kimi():
    sol_id, sol = lookup_model("openai/gpt-6-sol")
    assert sol_id == "openai/gpt-6-sol"
    assert sol["input_per_m"] == 2.0
    assert sol["cache_read_per_m"] == 0.2
    assert sol["output_per_m"] == 10.0
    assert lookup_model("deepseek-v4-pro-0813")[1].get("currency", "USD") == "USD"
    buckets = {
        "input_tokens": 1_000_000,
        "cache_read_tokens": 1_000_000,
        "cache_write_tokens": 0,
        "output_tokens": 1_000_000,
    }
    kimi = trial_cost(buckets, "bailian/kimi-k3")
    assert kimi["cost_cny"] is None
    assert kimi["cost_usd"] == round(0.67 + 0.66 + 14.0, 6)
    assert kimi["unpriced_models"] == []
    deepseek = trial_cost(buckets, "bailian/deepseek-v4-pro-0813")
    assert deepseek["cost_usd"] == round(0.1901 + 0.19 + 4.2, 6)
    glm_id, glm_price = lookup_model("bailian/glm-5.3")
    assert glm_id == "z-ai/glm-5.3"
    assert glm_price["cache_write_per_m"] == glm_price["input_per_m"]
    glm = trial_cost(buckets, "bailian/glm-5.3")
    assert glm["cost_usd"] == round(0.06 + 0.03 + 4.4, 6)
    qwen_id, qwen_price = lookup_model("bailian/qwen3.8-max-0902")
    assert qwen_id == "qwen/qwen3.8-max"
    assert lookup_model("qwen3.8-max")[0] == "qwen/qwen3.8-max"
    assert qwen_price["cache_read_5m_per_m"] == 0.17
    assert qwen_price["cache_write_per_m"] == 2.5
    qwen = trial_cost(buckets, "bailian/qwen3.8-max-0902")
    assert qwen["cost_usd"] == round(2.0 + 0.25 + 6.0, 6)
    qwen_write = trial_cost({**buckets, "cache_write_tokens": 1_000_000}, "qwen3.8-max-0902")
    assert qwen_write["cost_usd"] == round(2.0 + 0.25 + 2.5 + 6.0, 6)
    gemini_id, gemini_price = lookup_model("anthropic/google/gemini-4-argon")
    assert gemini_id == "google/gemini-4-argon"
    assert gemini_price["cache_write_per_m"] == gemini_price["input_per_m"]
    gemini = trial_cost(buckets, "google/gemini-4-argon")
    assert gemini["cost_usd"] == round(2.0 + 0.1 + 10.0, 6)
    gemini_write = trial_cost({**buckets, "cache_write_tokens": 1_000_000}, "gemini-4-argon")
    assert gemini_write["cost_usd"] == round(2.0 + 0.1 + 2.0 + 10.0, 6)
    flash_id, flash_price = lookup_model("openrouter/deepseek/deepseek-v4.1-flash-1017")
    assert flash_id == "deepseek/deepseek-v4.1-flash-1017"
    assert flash_price["cache_write_per_m"] == flash_price["input_per_m"]
    flash = trial_cost(buckets, "openrouter/deepseek/deepseek-v4.1-flash-1017")
    assert flash["cost_usd"] == round(0.08 + 0.008 + 0.50, 6)
    flash_write = trial_cost({**buckets, "cache_write_tokens": 1_000_000}, "deepseek-v4.1-flash-1017")
    assert flash_write["cost_usd"] == round(0.08 + 0.008 + 0.08 + 0.50, 6)


def _step_finish(inp: int, read: int, write: int, output: int, reasoning: int, cost: float) -> str:
    tokens = {"input": inp, "output": output, "reasoning": reasoning, "cache": {"read": read, "write": write}}
    return json.dumps({"type": "step_finish", "part": {"type": "step-finish", "tokens": tokens, "cost": cost}}) + "\n"


def test_opencode_step_finish_bills_reasoning_as_output(tmp_path: Path):
    # OpenCode subtracts reasoning from output; the billed output includes it.
    _write(tmp_path / "agent.log", _step_finish(10, 100, 20, 30, 7, 0.1) + _step_finish(5, 50, 0, 3, 2, 0.2))
    usage = collect_trial_usage(tmp_path)
    assert usage["output_tokens"] == 42
    assert usage["reasoning_tokens"] == 9
    assert usage["total_tokens"] == 15 + 150 + 20 + 42
    assert usage["sources"] == ["opencode_step_finish"]
    cost = trial_cost(usage, "anthropic/claude-sonnet-5-5")
    assert cost["cost_usd"] == round((15 * 2.0 + 150 * 0.2 + 20 * 2.5 + 42 * 10.0) / 1e6, 6)


def _opencode_db(path: Path, rows: list[tuple]) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        "CREATE TABLE session (id TEXT PRIMARY KEY, parent_id TEXT, cost REAL, tokens_input INTEGER, "
        "tokens_output INTEGER, tokens_reasoning INTEGER, tokens_cache_read INTEGER, tokens_cache_write INTEGER)"
    )
    con.executemany("INSERT INTO session VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return con


def test_opencode_db_adds_subagent_sessions_the_stream_omits(tmp_path: Path):
    # The stream only shows the top-level session's steps.
    _write(tmp_path / "agent.log", _step_finish(10, 100, 20, 30, 7, 0.1))
    archive = tmp_path / "container_logs" / "usage"
    # Kept open so the rows stay in the WAL, as in a container snapshot.
    first = _opencode_db(
        archive / "0" / "opencode.db",
        [("root", None, 0.1, 10, 30, 7, 100, 20), ("child", "root", 0.05, 4, 6, 1, 40, 0)],
    )
    # A later archive repeats the root session with a larger total.
    second = _opencode_db(
        archive / "1" / "opencode.db",
        [("root", None, 0.3, 15, 33, 9, 150, 20), ("fix", None, 0.01, 1, 1, 0, 0, 0)],
    )
    try:
        assert (archive / "0" / "opencode.db-wal").is_file()
        usage = collect_trial_usage(tmp_path)
    finally:
        first.close()
        second.close()
    # root (latest) + child + fix; output includes reasoning.
    assert usage["input_tokens"] == 15 + 4 + 1
    assert usage["cache_read_tokens"] == 150 + 40
    assert usage["cache_write_tokens"] == 20
    assert usage["output_tokens"] == (33 + 9) + (6 + 1) + 1
    assert usage["reasoning_tokens"] == 10
    assert usage["sources"] == ["opencode_session_db"]
    assert usage["harness_cost_usd"] == 0.36
    assert usage["complete"] is True


def test_opencode_db_is_ignored_for_claude_logs(tmp_path: Path):
    _write(
        tmp_path / "agent.log",
        json.dumps({"type": "result", "usage": {"input_tokens": 5, "output_tokens": 1}}) + "\n",
    )
    con = _opencode_db(tmp_path / "container_logs" / "usage" / "0" / "opencode.db", [("s", None, 1.0, 99, 99, 0, 0, 0)])
    try:
        usage = collect_trial_usage(tmp_path)
    finally:
        con.close()
    assert usage["sources"] == ["claude_result"]
    assert usage["input_tokens"] == 5


def test_opencode_spec_archives_its_data_dir():
    invocation = resolve_agent(backend="opencode", model="bailian/kimi-k3")
    assert invocation.spec.usage_paths == ("${XDG_DATA_HOME:-$HOME/.local/share}/opencode",)


def test_opencode_output_cap_reaches_the_container():
    invocation = resolve_agent(
        backend="opencode",
        model="anthropic/claude-sonnet-5-5",
        environ={"OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX": "128000"},
    )
    assert invocation.env["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] == "128000"
    try:
        resolve_agent(backend="opencode", model="anthropic/claude-sonnet-5-5", environ={"OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX": "lots"})
    except RuntimeError as exc:
        assert "positive integer" in str(exc)
    else:
        raise AssertionError("a non-numeric cap must be rejected")


def test_claude_code_output_cap_reaches_the_container():
    env = {"ANTHROPIC_API_KEY": "k", "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "128000"}
    invocation = resolve_agent(backend="claude-code", model="anthropic/claude-opus-5-5", environ=env)
    assert invocation.env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "128000"
    try:
        resolve_agent(backend="claude-code", model="anthropic/claude-opus-5-5",
                      environ={**env, "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "lots"})
    except RuntimeError as exc:
        assert "positive integer" in str(exc)
    else:
        raise AssertionError("a non-numeric cap must be rejected")


def test_opencode_zero_self_cost_is_not_recorded(tmp_path: Path):
    # A custom provider has no price in OpenCode, so its self-reported cost is 0.
    _write(tmp_path / "agent.log", _step_finish(10, 100, 0, 30, 7, 0.0))
    con = _opencode_db(tmp_path / "container_logs" / "usage" / "0" / "opencode.db", [("root", None, 0.0, 10, 30, 7, 100, 0)])
    try:
        usage = collect_trial_usage(tmp_path)
    finally:
        con.close()
    assert usage["sources"] == ["opencode_session_db"]
    assert "harness_cost_usd" not in usage
    assert trial_cost(usage, "bailian/kimi-k3")["cost_usd"] > 0
