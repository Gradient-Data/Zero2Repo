"""Token usage recorded for every trial, whatever agent CLI produced the log.

Every JSON line in the agent logs (and in the CLI session files archived under
``container_logs/usage``) is matched against the usage shapes the built-in CLIs
emit. Nothing is keyed on the backend name, so a custom AgentSpec that wraps one
of these CLIs is covered too.

Buckets follow the Anthropic convention: ``input_tokens`` excludes cached
prompt tokens, so input + cache_read + cache_write is the full prompt.

Sources, per log:

* final summary: Cursor ``result.usage``, Claude Code ``result`` (``modelUsage``
  when present), Codex ``turn.completed``, Codex ``token_count`` totals.
* per-call records: Claude Code ``assistant`` messages (deduplicated by
  message id), OpenCode ``step_finish`` parts.

A process killed by the wall clock or the stall watchdog never writes its final
summary. Codex and Claude Code session files are written as the run goes, so
they are used when any log lacks a summary. Cursor's headless stream reports
the billed total once, on ``turnEnded``, which is also what ``result.usage``
contains. The Cursor setup writes that message to
``container_logs/cursor_usage.jsonl`` as soon as it arrives, and that file is
used when the process dies before the result line. A kill while the model is
still generating happens before ``turnEnded``; the CLI has not reported a
bill yet. OpenHands keeps its total in memory and rewrites ``base_state.json``
only when conversation state changes, so a kill leaves that file at the empty
startup snapshot. The OpenHands setup appends each returned completion to
``container_logs/openhands_usage.jsonl`` inside ``add_token_usage``. Those
lines are summed when the logs have no usage. A finished run's
``base_state.json`` total is used when it is larger than the appended lines.
OpenCode prints ``step_finish`` only for the top-level session; its archived
database also holds subagent sessions and is used when it records more.
OpenCode reports output with reasoning subtracted, so reasoning is added back.
``complete`` is False when some log produced no usage at all;
``missing`` names those logs.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .pricing import trial_cost

__all__ = [
    "AGENT_LOG_NAMES",
    "USAGE_ARCHIVE_DIR",
    "collect_trial_usage",
    "parse_usage_text",
]

# Solve rounds in order: the first, then fix rounds after a denylist finding.
AGENT_LOG_NAMES = ("agent.log", "agent_fix.log", "agent_fix_2.log")
USAGE_ARCHIVE_DIR = "usage"
# Written by the Cursor turnEnded patch as soon as the billed total arrives.
CURSOR_USAGE_LOG = "cursor_usage.jsonl"
# One JSON line per OpenHands completion, written inside add_token_usage.
OPENHANDS_USAGE_LOG = "openhands_usage.jsonl"

_BUCKETS = ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens")


@dataclass
class Buckets:
    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    # Part of cache_write_tokens written with a one-hour TTL.
    cache_write_1h_tokens: int = 0

    def add(self, other: "Buckets") -> None:
        for name in (*_BUCKETS, "reasoning_tokens", "cache_write_1h_tokens"):
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def total(self) -> int:
        return sum(getattr(self, name) for name in _BUCKETS)


@dataclass
class LogUsage:
    summary: Buckets | None = None
    summary_source: str | None = None
    calls: Buckets | None = None
    calls_source: str | None = None
    harness_cost_usd: float | None = None
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)
    calls_by_model: dict[str, Buckets] = field(default_factory=dict)

    @property
    def found(self) -> bool:
        return self.summary is not None or self.calls is not None

    def best(self) -> tuple[Buckets, str] | None:
        if self.summary is not None:
            return self.summary, self.summary_source or "summary"
        if self.calls is not None:
            return self.calls, self.calls_source or "calls"
        return None


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return 0


def _json_events(text: str) -> Iterable[dict]:
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def _cursor_result(usage: dict) -> Buckets:
    return Buckets(
        input_tokens=_int(usage.get("inputTokens")),
        cache_read_tokens=_int(usage.get("cacheReadTokens")),
        cache_write_tokens=_int(usage.get("cacheWriteTokens")),
        output_tokens=_int(usage.get("outputTokens")),
    )


def _anthropic(usage: dict) -> Buckets:
    creation = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
    write = _int(usage.get("cache_creation_input_tokens"))
    return Buckets(
        input_tokens=_int(usage.get("input_tokens")),
        cache_read_tokens=_int(usage.get("cache_read_input_tokens")),
        cache_write_tokens=write,
        output_tokens=_int(usage.get("output_tokens")),
        cache_write_1h_tokens=min(_int(creation.get("ephemeral_1h_input_tokens")), write),
    )


def _claude_model_usage(model_usage: dict) -> tuple[Buckets, dict[str, dict[str, int]]]:
    total = Buckets()
    by_model: dict[str, dict[str, int]] = {}
    for name, info in model_usage.items():
        if not isinstance(info, dict):
            continue
        b = Buckets(
            input_tokens=_int(info.get("inputTokens")),
            cache_read_tokens=_int(info.get("cacheReadInputTokens")),
            cache_write_tokens=_int(info.get("cacheCreationInputTokens")),
            output_tokens=_int(info.get("outputTokens")),
        )
        total.add(b)
        by_model[str(name)] = {k: getattr(b, k) for k in _BUCKETS}
    return total, by_model


def _openai(usage: dict) -> Buckets:
    """OpenAI counts cached tokens inside ``input_tokens``; split them out."""
    cached = _int(usage.get("cached_input_tokens"))
    return Buckets(
        input_tokens=max(0, _int(usage.get("input_tokens")) - cached),
        cache_read_tokens=cached,
        output_tokens=_int(usage.get("output_tokens")),
        reasoning_tokens=_int(usage.get("reasoning_output_tokens")),
    )


def _codex_token_count_total(event: dict) -> dict | None:
    payload = event.get("payload") if event.get("type") == "event_msg" else event.get("msg")
    if not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    total = info.get("total_token_usage")
    return total if isinstance(total, dict) else None


def parse_usage_text(text: str) -> LogUsage:
    """Extract usage from one log or session file."""
    out = LogUsage()
    claude_msgs: dict[str, tuple[str, Buckets]] = {}
    opencode_calls: Buckets | None = None
    opencode_cost = 0.0
    saw_opencode_cost = False

    for event in _json_events(text):
        etype = event.get("type")
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else None

        if etype == "result" and usage is not None:
            if "inputTokens" in usage:
                out.summary, out.summary_source = _cursor_result(usage), "cursor_result"
                continue
            model_usage = event.get("modelUsage")
            if isinstance(model_usage, dict) and model_usage:
                out.summary, out.by_model = _claude_model_usage(model_usage)
            else:
                out.summary = _anthropic(usage)
            out.summary_source = "claude_result"
            cost = event.get("total_cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                out.harness_cost_usd = float(cost)
            continue

        if etype == "turn.completed" and usage is not None:
            out.summary, out.summary_source = _openai(usage), "codex_turn_completed"
            continue

        total = _codex_token_count_total(event)
        if total is not None:
            if out.summary_source != "codex_turn_completed":
                out.summary, out.summary_source = _openai(total), "codex_token_count"
            continue

        message = event.get("message")
        if etype == "assistant" and isinstance(message, dict) and isinstance(message.get("usage"), dict):
            key = str(message.get("id") or event.get("requestId") or event.get("uuid") or len(claude_msgs))
            claude_msgs[key] = (str(message.get("model") or ""), _anthropic(message["usage"]))
            continue

        part = event.get("part")
        if etype == "step_finish" and isinstance(part, dict) and isinstance(part.get("tokens"), dict):
            tokens = part["tokens"]
            cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
            step = _opencode_buckets(
                input_tokens=tokens.get("input"),
                cache_read=cache.get("read"),
                cache_write=cache.get("write"),
                output=tokens.get("output"),
                reasoning=tokens.get("reasoning"),
            )
            opencode_calls = opencode_calls or Buckets()
            opencode_calls.add(step)
            cost = part.get("cost")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                opencode_cost += float(cost)
                saw_opencode_cost = True

    if claude_msgs:
        out.calls = Buckets()
        for model, b in claude_msgs.values():
            out.calls.add(b)
            out.calls_by_model.setdefault(model, Buckets()).add(b)
        out.calls_source = "claude_assistant_messages"
        # modelUsage in the final result does not split cache writes by TTL.
        if out.summary is not None and not out.summary.cache_write_1h_tokens:
            out.summary.cache_write_1h_tokens = min(
                out.calls.cache_write_1h_tokens, out.summary.cache_write_tokens
            )
        for model, slot in out.by_model.items():
            calls = out.calls_by_model.get(model)
            if calls is not None:
                slot["cache_write_1h_tokens"] = min(calls.cache_write_1h_tokens, slot["cache_write_tokens"])
    elif opencode_calls is not None:
        out.calls, out.calls_source = opencode_calls, "opencode_step_finish"
        if saw_opencode_cost and out.harness_cost_usd is None:
            out.harness_cost_usd = opencode_cost
    return out


def _session_usage(usage_dir: Path) -> LogUsage | None:
    """Combine archived CLI session files, one session per file."""
    if not usage_dir.is_dir():
        return None
    total = Buckets()
    sources: set[str] = set()
    claude_msgs: dict[str, Buckets] = {}
    for path in sorted(usage_dir.rglob("*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parsed = parse_usage_text(text)
        if parsed.summary_source == "codex_token_count" and parsed.summary is not None:
            total.add(parsed.summary)
            sources.add("codex_session")
            continue
        for event in _json_events(text):
            message = event.get("message")
            if event.get("type") == "assistant" and isinstance(message, dict) and isinstance(message.get("usage"), dict):
                key = str(message.get("id") or event.get("requestId") or event.get("uuid"))
                claude_msgs[key] = _anthropic(message["usage"])
    for b in claude_msgs.values():
        total.add(b)
    if claude_msgs:
        sources.add("claude_session")
    if not sources:
        return None
    return LogUsage(summary=total, summary_source="+".join(sorted(sources)))


def _cursor_hook_buckets(out_dir: Path) -> Buckets | None:
    """Sum Cursor ``turnEnded`` totals written before the process exits.

    One JSON line per turn. The CLI adds those turns to produce
    ``result.usage``, so the lines are summed the same way. The same
    ``generation_id`` keeps its last line. Lines without an id each count.
    """
    path = out_dir / "container_logs" / CURSOR_USAGE_LOG
    if not path.is_file():
        return None
    latest: dict[str, Buckets] = {}
    anonymous: list[Buckets] = []
    found = False
    text = path.read_text(encoding="utf-8", errors="replace")
    for event in _json_events(text):
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else event
        if not isinstance(usage, dict):
            continue
        buckets = Buckets(
            input_tokens=_int(usage.get("input_tokens", usage.get("inputTokens"))),
            cache_read_tokens=_int(usage.get("cache_read_tokens", usage.get("cacheReadTokens"))),
            cache_write_tokens=_int(usage.get("cache_write_tokens", usage.get("cacheWriteTokens"))),
            output_tokens=_int(usage.get("output_tokens", usage.get("outputTokens"))),
        )
        if buckets.total() == 0:
            continue
        found = True
        generation = event.get("generation_id") or event.get("generationId")
        if isinstance(generation, str) and generation:
            latest[generation] = buckets
        else:
            anonymous.append(buckets)
    if not found:
        return None
    total = Buckets()
    for buckets in latest.values():
        total.add(buckets)
    for buckets in anonymous:
        total.add(buckets)
    return total


def _openhands_call_buckets(usage: dict) -> Buckets | None:
    """Convert one OpenHands usage object.

    ``prompt_tokens`` includes cache read and cache write. ``completion_tokens``
    includes reasoning, so reasoning is kept aside and not added again.
    """
    prompt = _int(usage.get("prompt_tokens"))
    completion = _int(usage.get("completion_tokens"))
    cache_read = _int(usage.get("cache_read_tokens"))
    cache_write = _int(usage.get("cache_write_tokens"))
    if prompt == 0 and completion == 0 and cache_read == 0 and cache_write == 0:
        return None
    return Buckets(
        input_tokens=max(prompt - cache_read - cache_write, 0),
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        output_tokens=completion,
        reasoning_tokens=_int(usage.get("reasoning_tokens")),
    )


def _openhands_jsonl_buckets(out_dir: Path) -> Buckets | None:
    path = out_dir / "container_logs" / OPENHANDS_USAGE_LOG
    if not path.is_file():
        return None
    latest: dict[str, Buckets] = {}
    anonymous: list[Buckets] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for event in _json_events(text):
        buckets = _openhands_call_buckets(event)
        if buckets is None:
            continue
        response_id = event.get("response_id")
        if isinstance(response_id, str) and response_id:
            latest[response_id] = buckets
        else:
            anonymous.append(buckets)
    if not latest and not anonymous:
        return None
    total = Buckets()
    for buckets in latest.values():
        total.add(buckets)
    for buckets in anonymous:
        total.add(buckets)
    return total


def _opencode_buckets(*, input_tokens: Any, cache_read: Any, cache_write: Any, output: Any, reasoning: Any) -> Buckets:
    """OpenCode reports output with reasoning subtracted; billed output includes it."""
    return Buckets(
        input_tokens=_int(input_tokens),
        cache_read_tokens=_int(cache_read),
        cache_write_tokens=_int(cache_write),
        output_tokens=_int(output) + _int(reasoning),
        reasoning_tokens=_int(reasoning),
    )


def _opencode_db_usage(out_dir: Path) -> tuple[Buckets, float] | None:
    """Sum the per-session totals OpenCode keeps in its archived database.

    Every session counts, including subagent sessions, which ``run --format
    json`` does not print. Totals grow as each step finishes, so a killed run
    keeps its finished steps. A session found in several archives keeps its
    largest total.
    """
    root = out_dir / "container_logs" / USAGE_ARCHIVE_DIR
    if not root.is_dir():
        return None
    sessions: dict[str, tuple[Buckets, float]] = {}
    for path in sorted(root.rglob("opencode*.db")):
        with tempfile.TemporaryDirectory() as tmp:
            # Copy with the WAL so rows not yet checkpointed are read too.
            for src in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
                if src.is_file():
                    shutil.copy2(src, Path(tmp) / src.name)
            con = sqlite3.connect(Path(tmp) / path.name)
            try:
                rows = con.execute(
                    "SELECT id, tokens_input, tokens_cache_read, tokens_cache_write, "
                    "tokens_output, tokens_reasoning, cost FROM session"
                ).fetchall()
            except sqlite3.Error as exc:
                raise RuntimeError(f"cbrun: cannot read OpenCode usage from {path}: {exc}") from exc
            finally:
                con.close()
        for sid, inp, read, write, output, reasoning, cost in rows:
            buckets = _opencode_buckets(
                input_tokens=inp, cache_read=read, cache_write=write, output=output, reasoning=reasoning
            )
            prior = sessions.get(sid)
            if prior is None or buckets.total() > prior[0].total():
                sessions[sid] = (buckets, float(cost or 0.0))
    if not sessions:
        return None
    total = Buckets()
    cost = 0.0
    for buckets, session_cost in sessions.values():
        total.add(buckets)
        cost += session_cost
    return total, cost


def _openhands_state_buckets(out_dir: Path) -> Buckets | None:
    """Sum accumulated usage from every archived ``base_state.json``."""
    root = out_dir / "container_logs" / USAGE_ARCHIVE_DIR
    if not root.is_dir():
        return None
    total = Buckets()
    found = False
    for path in sorted(root.rglob("base_state.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        metrics = ((data.get("stats") or {}).get("usage_to_metrics") or {})
        if not isinstance(metrics, dict):
            continue
        for slot in metrics.values():
            if not isinstance(slot, dict):
                continue
            usage = slot.get("accumulated_token_usage")
            if not isinstance(usage, dict):
                continue
            buckets = _openhands_call_buckets(usage)
            if buckets is None:
                continue
            total.add(buckets)
            found = True
    return total if found else None


def _openhands_buckets(out_dir: Path) -> tuple[Buckets, str] | None:
    """Live completion lines, or the state snapshot when it recorded more."""
    logged = _openhands_jsonl_buckets(out_dir)
    state = _openhands_state_buckets(out_dir)
    if logged is None and state is None:
        return None
    if state is None or (logged is not None and logged.total() >= state.total()):
        return logged, "openhands_usage_log"  # type: ignore[return-value]
    if logged is None or state.total() > logged.total():
        return state, "openhands_base_state"
    return logged, "openhands_usage_log"


def collect_trial_usage(out_dir: Path | str) -> dict[str, Any]:
    """Return the ``token_usage`` record for one trial directory."""
    out_dir = Path(out_dir)
    per_log: dict[str, LogUsage] = {}
    for name in AGENT_LOG_NAMES:
        path = out_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            per_log[name] = parse_usage_text(text)

    sessions = _session_usage(out_dir / "container_logs" / USAGE_ARCHIVE_DIR)
    hook = _cursor_hook_buckets(out_dir)
    openhands = _openhands_buckets(out_dir)
    opencode_db = _opencode_db_usage(out_dir)
    record: dict[str, Any] = {name: 0 for name in _BUCKETS}
    record.update({"reasoning_tokens": 0, "total_tokens": 0, "sources": [], "complete": False, "missing": []})

    if not per_log and sessions is None and hook is None and openhands is None and opencode_db is None:
        record["missing"] = ["agent.log"]
        return record

    total = Buckets()
    sources: list[str] = []
    missing = [name for name, log in per_log.items() if not log.found]
    all_summarized = bool(per_log) and all(log.summary is not None for log in per_log.values())

    if all_summarized or sessions is None:
        for log in per_log.values():
            best = log.best()
            if best is None:
                continue
            total.add(best[0])
            if best[1] not in sources:
                sources.append(best[1])
        complete = not missing and bool(per_log)
    else:
        total.add(sessions.summary)  # type: ignore[arg-type]
        sources.append(sessions.summary_source or "session")
        complete = True
        missing = []

    for name in _BUCKETS:
        record[name] = getattr(total, name)
    record["cache_write_1h_tokens"] = total.cache_write_1h_tokens
    record["reasoning_tokens"] = total.reasoning_tokens
    record["total_tokens"] = total.total()
    record["sources"] = sources
    record["complete"] = complete
    record["missing"] = missing

    costs = [log.harness_cost_usd for log in per_log.values() if log.harness_cost_usd is not None]
    if costs:
        record["harness_cost_usd"] = round(sum(costs), 6)
    by_model = _by_model(per_log.values()) if all_summarized or sessions is None else None
    if by_model:
        record["by_model"] = by_model

    has_cursor_result = any(log.summary_source == "cursor_result" for log in per_log.values())
    if openhands is not None and record["total_tokens"] == 0 and not has_cursor_result:
        buckets, source = openhands
        for name in _BUCKETS:
            record[name] = getattr(buckets, name)
        record["cache_write_1h_tokens"] = buckets.cache_write_1h_tokens
        record["reasoning_tokens"] = buckets.reasoning_tokens
        record["total_tokens"] = buckets.total()
        record["sources"] = [source]
        record["complete"] = True
        record["missing"] = []
        record.pop("by_model", None)
    # The database also holds subagent sessions the JSON stream leaves out.
    if (
        opencode_db is not None
        and set(record["sources"]) <= {"opencode_step_finish"}
        and opencode_db[0].total() >= record["total_tokens"]
    ):
        buckets, db_cost = opencode_db
        for name in _BUCKETS:
            record[name] = getattr(buckets, name)
        record["cache_write_1h_tokens"] = 0
        record["reasoning_tokens"] = buckets.reasoning_tokens
        record["total_tokens"] = buckets.total()
        record["sources"] = ["opencode_session_db"]
        record["complete"] = True
        record["missing"] = []
        # A custom provider has no price in OpenCode, which then reports 0.
        if db_cost > 0:
            record["harness_cost_usd"] = round(db_cost, 6)
        else:
            record.pop("harness_cost_usd", None)
        record.pop("by_model", None)
    if hook is not None and not has_cursor_result:
        for name in _BUCKETS:
            record[name] = getattr(hook, name)
        record["cache_write_1h_tokens"] = 0
        record["reasoning_tokens"] = 0
        record["total_tokens"] = hook.total()
        record["sources"] = ["cursor_response_hooks"]
        record["complete"] = True
        record["missing"] = []
        record.pop("by_model", None)
    return record


def _log_by_model(log: LogUsage) -> dict[str, dict[str, int]] | None:
    if log.by_model:
        return log.by_model
    best = log.best()
    if best is not None and best[1] == "claude_assistant_messages" and "" not in log.calls_by_model:
        return {
            model: {k: getattr(b, k) for k in (*_BUCKETS, "cache_write_1h_tokens")}
            for model, b in log.calls_by_model.items()
        }
    return None


def _by_model(logs: Iterable[LogUsage]) -> dict[str, dict[str, int]] | None:
    """Per-model usage summed over logs, or None unless every log with usage has it."""
    keys = (*_BUCKETS, "cache_write_1h_tokens")
    out: dict[str, dict[str, int]] = {}
    for log in logs:
        if not log.found:
            continue
        per_model = _log_by_model(log)
        if per_model is None:
            return None
        for model, buckets in per_model.items():
            slot = out.setdefault(model, {k: 0 for k in keys})
            for k in keys:
                slot[k] += buckets.get(k, 0)
    return out or None


def _backfill(out_root: Path) -> int:
    """Recompute ``token_usage`` for every trial in ``out_root/summary.json``."""
    summary_path = out_root / "summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    changed = 0
    for trial in payload.get("trials", []):
        agent_log = (trial.get("logs") or {}).get("agent_log")
        trial_dir = Path(agent_log).parent if agent_log else out_root / trial["case_id"] / trial["backend"]
        if not trial_dir.is_dir():
            print(f"skip {trial['case_id']}/{trial['backend']}: {trial_dir} missing", file=sys.stderr)
            continue
        usage = collect_trial_usage(trial_dir)
        usage.update(trial_cost(usage, trial.get("resolved_model") or trial.get("model")))
        trial["token_usage"] = usage
        changed += 1
        state = "complete" if usage["complete"] else f"INCOMPLETE missing={usage['missing']}"
        cost = "unpriced" if usage["cost_usd"] is None else f"${usage['cost_usd']:.2f}"
        print(f"{trial['case_id']}/{trial['backend']}: total={usage['total_tokens']} cost={cost} {state}")
    from .results import _aggregate_usage
    from .state import atomic_json

    payload.setdefault("aggregate", {})["token_usage"] = _aggregate_usage(
        [t.get("token_usage") or {} for t in payload.get("trials", [])]
    )
    atomic_json(summary_path, payload)
    return 0 if changed else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m cbrun.usage <cbrun output dir with summary.json>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(_backfill(Path(sys.argv[1])))
