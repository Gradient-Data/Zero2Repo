"""Wall-clock reminders delivered into a running agent session.

The shared instruction states only that the session has a wall-clock budget;
it never says how much is left. During the solve, each agent's own hook or
plugin point calls this script, which returns a reminder only when a scheduled
point is due:

* at the start, then every hour while more than an hour remains
* every 30 minutes in the last hour
* every 10 minutes in the last 30 minutes
* every 5 minutes in the last 10 minutes
* every minute in the last 5 minutes
* every 30 seconds in the last minute

Delivery happens at the agent's next hook point (a tool returning or a prompt
being submitted), so a long model turn or a command that has not returned
delays it. Each agent (main session or subagent) gets every due point once.

This file runs inside the solve container with only the standard library.
Agent setup copies it to ``/tmp/cbrun/time_reminder.py``; the solve command runs
``init`` with the round's wall budget before the agent starts.
"""

from __future__ import annotations

import fcntl
import json
import sys
import time
from pathlib import Path

STATE_DIR = Path("/tmp/cbrun")
DEADLINE_FILE = STATE_DIR / "deadline.json"
SENT_FILE = STATE_DIR / "time_reminders.json"
LOCK_FILE = STATE_DIR / "time_reminders.lock"
AUDIT_LOG = Path("/logs/agent/time_reminders.jsonl")
SUBMIT_PATH = "/logs/agent/submit"
SUBMIT_TOKEN = "CODINGBENCH_SUBMIT"
WORKDIR = "/app"
CONTAINER_PATH = "/tmp/cbrun/time_reminder.py"

# Interval boundaries, largest first. A countdown never steps over one of them.
_BOUNDS = (3600, 1800, 600, 300, 60)
# Hook output shapes: Claude Code and Codex read hookSpecificOutput, OpenHands
# a top-level additionalContext, Cursor a top-level additional_context.
FORMATS = ("claude", "codex", "cursor", "openhands")


def interval(left: int) -> int:
    if left > 3600:
        return 3600
    if left > 1800:
        return 1800
    if left > 600:
        return 600
    if left > 300:
        return 300
    if left > 60:
        return 60
    return 30


def reminder_points(total: int) -> list[int]:
    """Seconds remaining at each reminder, starting with the full budget."""
    points: list[int] = []
    left = int(total)
    while left > 0:
        points.append(left)
        step = left - interval(left)
        lower = [bound for bound in _BOUNDS if bound < left]
        left = max(step, lower[0]) if lower else step
    return points


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def reminder_text(left: float, total: int) -> str:
    return (
        f"Time check: {format_duration(left)} of this session's wall-clock budget "
        f"remain (budget {format_duration(total)}). When the budget runs out the "
        "session is killed and the attempt is recorded as a timeout. To be scored, "
        f"write the submit file {SUBMIT_PATH} with the single line {SUBMIT_TOKEN} "
        f"and finish the session before then; the hidden tests run against "
        f"{WORKDIR} as you leave it."
    )


def init(total: int, *, now: float | None = None) -> None:
    total = int(total)
    if total <= 0:
        raise SystemExit(f"cbrun time_reminder: wall budget must be positive, got {total}")
    start = time.time() if now is None else now
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEADLINE_FILE.write_text(
        json.dumps({"start": start, "deadline": start + total, "total": total}),
        encoding="utf-8",
    )
    SENT_FILE.write_text("{}", encoding="utf-8")


def due_reminder(agent: str, *, event: str, now: float | None = None) -> str | None:
    """Return the reminder for the latest due point ``agent`` has not seen."""
    budget = json.loads(DEADLINE_FILE.read_text(encoding="utf-8"))
    now = time.time() if now is None else now
    total = int(budget["total"])
    elapsed = now - float(budget["start"])
    points = reminder_points(total)
    due = [index for index, point in enumerate(points) if total - point <= elapsed]
    if not due:
        return None
    latest = due[-1]
    with LOCK_FILE.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        sent = json.loads(SENT_FILE.read_text(encoding="utf-8"))
        if int(sent.get(agent, -1)) >= latest:
            return None
        sent[agent] = latest
        SENT_FILE.write_text(json.dumps(sent), encoding="utf-8")
    left = float(budget["deadline"]) - now
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "at": now,
            "event": event,
            "agent": agent,
            "point": points[latest],
            "left": round(left, 1),
        }) + "\n")
    return reminder_text(left, total)


def render(fmt: str, event: str, text: str | None) -> str:
    """Hook stdout for ``fmt``; empty means nothing to add."""
    if fmt == "cursor":
        return json.dumps({"additional_context": text}) if text else "{}"
    if not text:
        return ""
    if fmt == "openhands":
        return json.dumps({"additionalContext": text})
    if fmt in ("claude", "codex"):
        return json.dumps({
            "hookSpecificOutput": {"hookEventName": event, "additionalContext": text},
        })
    raise SystemExit(f"cbrun time_reminder: unknown hook format {fmt!r}")


def _hook(fmt: str, event: str) -> None:
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    agent = str(data.get("agent_id") or "main") if isinstance(data, dict) else "main"
    out = render(fmt, event, due_reminder(agent, event=event))
    if out:
        print(out)


def main(argv: list[str]) -> None:
    if len(argv) == 2 and argv[0] == "init":
        init(int(argv[1]))
    elif len(argv) == 3 and argv[0] == "hook" and argv[1] in FORMATS:
        _hook(argv[1], argv[2])
    elif len(argv) == 3 and argv[0] == "text":
        text = due_reminder(argv[1], event=argv[2])
        if text:
            sys.stdout.write(text)
    else:
        raise SystemExit(
            "usage: time_reminder.py init SECONDS | hook {"
            + ",".join(FORMATS)
            + "} EVENT | text AGENT EVENT"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
