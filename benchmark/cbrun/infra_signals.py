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
    # The CLI gave up on a server-side API failure (Claude Code stream-json).
    (
        "api_error",
        re.compile(r'"terminal_reason"\s*:\s*"api_error"|"api_error_status"\s*:\s*5\d\d'),
    ),
)

_TERMINATING = frozenset({"auth", "retry_exhausted", "conn_refused", "api_error"})
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


def _truncated_stream(tail: str) -> bool:
    """Claude Code stream-json that ends on a cut-off turn.

    The CLI can report ``subtype: success`` after the API stream breaks
    mid-message: the last assistant event holds only thinking, or the final
    ``result`` carries an open-turn stop reason. Other log shapes never match.
    """
    events = []
    for line in tail.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    results = [e for e in events if e.get("type") == "result" and "subtype" in e]
    assistants = [
        e["message"] for e in events
        if e.get("type") == "assistant" and isinstance(e.get("message"), dict)
    ]
    if not results or not assistants:
        return False
    blocks = {
        b.get("type") for b in assistants[-1].get("content") or [] if isinstance(b, dict)
    }
    return blocks <= _THINKING_BLOCKS or results[-1].get("stop_reason") in _OPEN_TURN_STOPS


def invalid_reason(*, submitted: bool, log_text: str) -> str | None:
    """Return ``infra:<signal>`` when the trial is not a valid model result."""
    if submitted:
        return None
    tail = "\n".join((log_text or "").splitlines()[-_TAIL_LINES:])
    for name, pattern in _COUNT_PATTERNS:
        if name not in _TERMINATING:
            continue
        if pattern.search(tail):
            return f"infra:{name}"
    if _truncated_stream(tail):
        return "infra:truncated_stream"
    return None
