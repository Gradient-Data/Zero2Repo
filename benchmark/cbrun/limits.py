"""Time limits and solve terminal-status model for cbrun.

Development is free: no step/turn/cost cap. The only hard ceiling is a
wall-clock ``max_agent_timeout_sec`` for the solve phase and a separate
``max_test_timeout_sec`` for the judge phase. A conservative stall window guards
against a wedged CLI without prematurely killing an agent that is legitimately
compiling or thinking for a long time.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

__all__ = [
    "TerminalStatus",
    "Limits",
    "case_test_timeout_sec",
    "classify_terminal",
    "resolve_limits",
]

# Final-stage cases (a single acceptance milestone) get a uniform 2h solve
# budget. References: Terminal-Bench defaults agent 180/360s + test 30/60s for
# small terminal tasks; SWE-bench / mini-swe-agent default to step_limit=250 +
# cost $3 with no wall clock. Our tasks build a whole project from scratch
# (some with GPU compilation), so a uniform 2h is the stable choice.
DEFAULT_AGENT_TIMEOUT_SEC: float = 7200.0
DEFAULT_TEST_TIMEOUT_SEC: float = 7200.0
# Stall watchdog: kill the solve only after this many seconds with no new agent
# output. Set above the 1800s OpenHands request timeout so a silent thinking
# turn can return and log a line before the watchdog fires. 0 disables the
# stall guard (rely on the wall clock only).
DEFAULT_STALL_WINDOW_SEC: float = 2100.0
SUITE_WALL_HEADROOM: float = 2.0


class TerminalStatus(str, enum.Enum):
    """How the solve phase ended.

    ``completed`` requires a valid submit file and a clean CLI exit. The
    isolated judge runs only after a valid submit (and a clean denylist
    scan). Missing submit is a failed attempt: reward stays 0.
    """

    COMPLETED = "completed"  # Valid submit file and CLI exited 0.
    TIMEOUT = "timeout"      # Wall-clock max_agent_timeout_sec was hit.
    ERROR = "error"          # Stall, nonzero exit, setup failure, or no submit.

    @classmethod
    def from_run(cls, *, exit_code: int, timed_out: bool, stall_killed: bool) -> "TerminalStatus":
        """Classify how the CLI process stopped (ignores the submit file)."""
        if timed_out:
            return cls.TIMEOUT
        if stall_killed:
            return cls.ERROR
        return cls.COMPLETED if exit_code == 0 else cls.ERROR


def classify_terminal(
    *,
    exit_code: int,
    timed_out: bool,
    stall_killed: bool,
    submitted: bool,
) -> TerminalStatus:
    """Classify the solve using CLI stop reason plus the explicit submit file.

    No valid submit: ``timeout`` if the wall clock fired, otherwise ``error``.
    Valid submit: same as ``from_run`` (``completed`` only on a clean exit 0).
    """
    if not submitted:
        return TerminalStatus.TIMEOUT if timed_out else TerminalStatus.ERROR
    return TerminalStatus.from_run(
        exit_code=exit_code,
        timed_out=timed_out,
        stall_killed=stall_killed,
    )


@dataclass(frozen=True)
class Limits:
    """Resolved wall-clock limits for one trial."""

    max_agent_timeout_sec: float = DEFAULT_AGENT_TIMEOUT_SEC
    max_test_timeout_sec: float = DEFAULT_TEST_TIMEOUT_SEC
    stall_window_sec: float = DEFAULT_STALL_WINDOW_SEC
    multiplier: float = 1.0
    base_agent_timeout_sec: float = DEFAULT_AGENT_TIMEOUT_SEC
    base_test_timeout_sec: float = DEFAULT_TEST_TIMEOUT_SEC

    def for_case(self, per_case: float | None) -> "Limits":
        """Widen the judge budget from a per-case measurement. Never tighten."""
        if per_case is None or per_case <= 0:
            return self
        test = max(self.base_test_timeout_sec, float(per_case))
        return Limits(
            max_agent_timeout_sec=self.max_agent_timeout_sec,
            max_test_timeout_sec=test * self.multiplier,
            stall_window_sec=self.stall_window_sec,
            multiplier=self.multiplier,
            base_agent_timeout_sec=self.base_agent_timeout_sec,
            base_test_timeout_sec=self.base_test_timeout_sec,
        )


def case_test_timeout_sec(test_manifest: dict | None) -> float | None:
    """Per-case judge budget from the sealed suite, or None to keep the default."""
    if not isinstance(test_manifest, dict):
        return None
    raw = test_manifest.get("judge_timeout_sec")
    if raw not in (None, ""):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None
    wall = test_manifest.get("suite_wall_seconds")
    if wall not in (None, ""):
        try:
            value = float(wall) * SUITE_WALL_HEADROOM
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None
    return None


def resolve_limits(
    *,
    agent_timeout_sec: float | None = None,
    test_timeout_sec: float | None = None,
    stall_window_sec: float | None = None,
    multiplier: float = 1.0,
) -> Limits:
    """Resolve per-trial limits.

    ``multiplier`` mirrors Terminal-Bench's ``global_timeout_multiplier`` and is
    applied to both wall-clock budgets (but not the stall window). Per-case
    overrides take precedence over the defaults before the multiplier.
    """
    if multiplier <= 0:
        raise ValueError(f"timeout multiplier must be positive, got {multiplier}")

    agent = agent_timeout_sec if agent_timeout_sec is not None else DEFAULT_AGENT_TIMEOUT_SEC
    test = test_timeout_sec if test_timeout_sec is not None else DEFAULT_TEST_TIMEOUT_SEC
    stall = stall_window_sec if stall_window_sec is not None else DEFAULT_STALL_WINDOW_SEC

    if agent <= 0:
        raise ValueError(f"agent timeout must be positive, got {agent}")
    if test <= 0:
        raise ValueError(f"test timeout must be positive, got {test}")
    if stall < 0:
        raise ValueError(f"stall window must be non-negative, got {stall}")

    return Limits(
        max_agent_timeout_sec=agent * multiplier,
        max_test_timeout_sec=test * multiplier,
        stall_window_sec=stall,
        multiplier=multiplier,
        base_agent_timeout_sec=agent,
        base_test_timeout_sec=test,
    )
