"""Run Claude Code and resume its session when it ends before a submit.

In print mode Claude Code exits as soon as one request fails: the stream
closes mid-response, the gateway answers 5xx, or a reply hits the output cap.
It then writes a synthetic assistant message holding the error text and a
final ``result`` with ``is_error`` set. That exit is the transport failing,
not the model ending its turn, so this runner resumes the same session in the
same container with a neutral message. Nothing is reset: the workspace stays
in place and the solve's wall clock keeps running across resumes.

Client errors (4xx other than 408 and 429) are not retried because sending
the same request again cannot succeed. After ``MAX_IDLE_RESUMES`` resumes in a
row that produce no model message, the runner stops and the run ends on the
last error.

Print mode also exits when the model ends its turn, even when the model only
meant to wait for background work it started; that work never reports back.
A turn that ends with no valid submit file is resumed with a message saying
so, at most ``MAX_NO_SUBMIT_RESUMES`` times. The wall clock still bounds the
whole solve.

Each resume is recorded in the log as a ``cbrun_resume`` system event.

This file runs inside the solve container with only the standard library.
Agent setup copies it to ``/tmp/cbrun/claude_resume.py``.

Usage: ``python3 claude_resume.py LOG INSTRUCTION SUBMIT_FILE SUBMIT_TOKEN -- claude ARGS...``
"""

from __future__ import annotations

import ctypes
import json
import signal
import subprocess
import sys
import time
from typing import BinaryIO

CONTAINER_PATH = "/tmp/cbrun/claude_resume.py"
RESUME_EVENT = "cbrun_resume"
SYNTHETIC_MODEL = "<synthetic>"
RESUME_PROMPT = (
    "Your previous response was interrupted by an API error. "
    "Continue the task from where you left off."
)
NO_SUBMIT_PROMPT = (
    "Your turn ended without submitting, and the session exited. Background "
    "tasks started in that session will not report back to you. Check the "
    "current state of the workspace, continue the task, and submit as the "
    "instructions describe once it is complete."
)
MAX_IDLE_RESUMES = 3
MAX_NO_SUBMIT_RESUMES = 3
_RETRYABLE_CLIENT_STATUS = frozenset({408, 429})
_PR_SET_PDEATHSIG = 1


class Outcome:
    """What one Claude Code process reported before it exited."""

    def __init__(self) -> None:
        self.result: dict | None = None
        self.last_model: str | None = None
        self.model_messages = 0

    def feed(self, line: bytes) -> None:
        if not line.startswith(b"{"):
            return
        try:
            event = json.loads(line)
        except ValueError:
            return
        if not isinstance(event, dict):
            return
        if event.get("type") == "result":
            self.result = event
        elif event.get("type") == "assistant" and isinstance(event.get("message"), dict):
            self.last_model = str(event["message"].get("model") or "")
            if self.last_model != SYNTHETIC_MODEL:
                self.model_messages += 1


def resumable(outcome: Outcome) -> bool:
    """True when the process ended on an API failure a resend can recover from."""
    result = outcome.result
    if not result or not result.get("is_error") or not result.get("session_id"):
        return False
    if outcome.last_model != SYNTHETIC_MODEL:
        return False
    status = result.get("api_error_status")
    if isinstance(status, int) and 400 <= status < 500 and status not in _RETRYABLE_CLIENT_STATUS:
        return False
    return True


def ended_without_submit(outcome: Outcome, submit_file: str, token: str) -> bool:
    """True when the model ended its own turn and no valid submit file exists."""
    result = outcome.result
    if not result or result.get("is_error") or not result.get("session_id"):
        return False
    return not submitted(submit_file, token)


def submitted(submit_file: str, token: str) -> bool:
    """The host's submit rule: the file holds exactly the token (blank lines ignored)."""
    try:
        with open(submit_file, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except FileNotFoundError:
        return False
    return [ln.strip() for ln in text.splitlines() if ln.strip()] == [token]


def backoff_sec(idle: int) -> int:
    return min(15 * 2 ** idle, 240)


def _die_with_parent() -> None:
    # The watchdog kills this runner by its command line; Claude Code must not
    # outlive it and keep editing the workspace while the judge runs.
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL)


def _run(argv: list[str], stdin: BinaryIO | int, log: BinaryIO) -> tuple[int, Outcome]:
    outcome = Outcome()
    proc = subprocess.Popen(
        argv, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        preexec_fn=_die_with_parent,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
        log.write(line)
        log.flush()
        outcome.feed(line)
    return proc.wait(), outcome


def _record(log: BinaryIO, event: dict) -> None:
    line = (json.dumps(event) + "\n").encode()
    sys.stdout.buffer.write(line)
    sys.stdout.buffer.flush()
    log.write(line)
    log.flush()


def main(argv: list[str]) -> int:
    if len(argv) < 6 or argv[4] != "--":
        print(
            "usage: claude_resume.py LOG INSTRUCTION SUBMIT_FILE SUBMIT_TOKEN -- claude ARGS...",
            file=sys.stderr,
        )
        return 2
    log_path, instruction, submit_file, token, cmd = argv[0], argv[1], argv[2], argv[3], argv[5:]
    with open(log_path, "wb") as log:
        with open(instruction, "rb") as stdin:
            code, outcome = _run(cmd, stdin, log)
        attempt = 0
        idle = 0
        no_submit = 0
        while True:
            result = outcome.result or {}
            if resumable(outcome) and idle < MAX_IDLE_RESUMES:
                reason, prompt, wait = "api_error", RESUME_PROMPT, backoff_sec(idle)
            elif ended_without_submit(outcome, submit_file, token) and no_submit < MAX_NO_SUBMIT_RESUMES:
                no_submit += 1
                reason, prompt, wait = "no_submit", NO_SUBMIT_PROMPT, 0
            else:
                return code
            attempt += 1
            _record(log, {
                "type": "system",
                "subtype": RESUME_EVENT,
                "reason": reason,
                "attempt": attempt,
                "session_id": result["session_id"],
                "api_error_status": result.get("api_error_status"),
                "error": str(result.get("result") or "") if reason == "api_error" else "",
                "wait_sec": wait,
            })
            if wait:
                time.sleep(wait)
            code, outcome = _run(
                [*cmd, "--resume", str(result["session_id"]), prompt],
                subprocess.DEVNULL,
                log,
            )
            if reason == "api_error":
                idle = 0 if outcome.model_messages else idle + 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
