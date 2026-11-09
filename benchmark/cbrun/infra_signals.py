"""Scan agent logs for infrastructure failures that are not model skill.

Patterns are conservative and backend-agnostic. A run is invalid only when
there is no valid submit and a terminating signal appears near the end of
the log. Recovered ``content_filter`` events are counted but do not invalidate
a submitted trial.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .claude_resume import RESUME_EVENT, SYNTHETIC_MODEL

__all__ = [
    "count_infra_signals",
    "invalid_reason",
    "scan_log_text",
]

_COUNT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("content_filter", re.compile(r"content_filter", re.I)),
    ("incomplete_response", re.compile(r"Incomplete response returned", re.I)),
    (
        "rate_limit",
        re.compile(
            r"rate_limit_exceeded|RateLimitError|Too Many Requests|HTTP\s+429|status\s+429",
            re.I,
        ),
    ),
    (
        "auth",
        re.compile(
            r"invalid_api_key|AuthenticationError|HTTP\s+401|status\s+401",
            re.I,
        ),
    ),
    ("retry_exhausted", re.compile(r"exceeded retry limit", re.I)),
    ("conn_refused", re.compile(r"ECONNREFUSED", re.I)),
    # Codex gave up after its reconnect attempts: the reply stream kept breaking.
    (
        "stream_disconnected",
        re.compile(r'"type"\s*:\s*"turn\.failed".{0,400}?stream disconnected before completion'),
    ),
    # Cursor could not reach its API, or its connection died mid-session.
    ("cursor_unreachable", re.compile(r"Failed to reach the Cursor API")),
    ("cursor_connection_lost", re.compile(r"RetriableError: \[internal\] HTTP/2 keepalive ping timed out")),
    ("cursor_gave_up", re.compile(r"RetriableError: Agent turn stopped after repeated resume attempts")),
    # The CLI gave up on a server-side API failure (Claude Code stream-json).
    (
        "api_error",
        re.compile(r'"terminal_reason"\s*:\s*"api_error"|"api_error_status"\s*:\s*5\d\d'),
    ),
)

_TERMINATING = frozenset({"auth", "retry_exhausted", "conn_refused", "api_error", "stream_disconnected",
                          "cursor_unreachable", "cursor_connection_lost", "cursor_gave_up"})
_TAIL_LINES = 200
# A final ``result`` with one of these stop reasons means the CLI exited while
# the model's turn was still open (the response stream was cut off).
_OPEN_TURN_STOPS = frozenset({None, "tool_use", "pause_turn"})
_THINKING_BLOCKS = frozenset({"thinking", "redacted_thinking"})


def scan_log_text(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not text:
        return counts
    for name, pattern in _COUNT_PATTERNS:
        n = len(pattern.findall(text))
        if n:
            counts[name] = n
    return counts


def count_infra_signals(*paths: Path | str | None) -> dict[str, int]:
    totals: dict[str, int] = {}
    for raw in paths:
        if raw is None:
            continue
        path = Path(raw)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for key, value in scan_log_text(text).items():
            totals[key] = totals.get(key, 0) + value
    return totals


def _json_lines(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _final_exit(events: list[dict]) -> tuple[dict, dict] | None:
    """The last Claude Code ``result`` and the assistant message before it."""
    results = [e for e in events if e.get("type") == "result" and "subtype" in e]
    assistants = [
        e["message"] for e in events
        if e.get("type") == "assistant" and isinstance(e.get("message"), dict)
    ]
    if not results or not assistants:
        return None
    return results[-1], assistants[-1]


def _truncated_stream(final: tuple[dict, dict]) -> bool:
    """Claude Code stream-json that ends on a cut-off turn.

    The CLI can report ``subtype: success`` after the API stream breaks
    mid-message: the last assistant event holds only thinking, or the final
    ``result`` carries an open-turn stop reason.
    """
    result, message = final
    blocks = {b.get("type") for b in message.get("content") or [] if isinstance(b, dict)}
    return blocks <= _THINKING_BLOCKS or result.get("stop_reason") in _OPEN_TURN_STOPS


def _api_failure_exit(final: tuple[dict, dict]) -> bool:
    """Claude Code gave up on a failed request.

    The CLI then writes a synthetic assistant message holding the error text and
    a final ``result`` with ``is_error``, whatever its ``terminal_reason`` says.
    """
    result, message = final
    return bool(result.get("is_error")) and message.get("model") == SYNTHETIC_MODEL


def _still_reconnecting(event: dict) -> bool:
    """Codex's last event says it was still reconnecting a broken reply stream."""
    message = str(event.get("message") or "")
    return event.get("type") == "error" and message.startswith("Reconnecting...") \
        and "stream disconnected" in message


def _last_process(text: str) -> str:
    """Log text written by the agent process that ended the solve."""
    lines = text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if RESUME_EVENT in lines[i]:
            try:
                event = json.loads(lines[i])
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("subtype") == RESUME_EVENT:
                return "\n".join(lines[i + 1:])
    return text


def invalid_reason(*, submitted: bool, log_text: str) -> str | None:
    """Return ``infra:<signal>`` when the trial is not a valid model result."""
    if submitted:
        return None
    tail = "\n".join(_last_process(log_text or "").splitlines()[-_TAIL_LINES:])
    for name, pattern in _COUNT_PATTERNS:
        if name not in _TERMINATING:
            continue
        if pattern.search(tail):
            return f"infra:{name}"
    events = _json_lines(tail)
    if events and _still_reconnecting(events[-1]):
        return "infra:stream_reconnecting"
    final = _final_exit(events)
    if final is None:
        return None
    if _api_failure_exit(final):
        return "infra:api_error"
    if _truncated_stream(final):
        return "infra:truncated_stream"
    return None
