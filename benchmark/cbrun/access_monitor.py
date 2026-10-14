"""Host side of the solve-time access monitor.

Invariant: while the agent solves, only allowlisted toolchain processes may
open the files of a banned implementation. Any reuse of an existing
implementation (importing it as a dependency or an oracle, reading, copying,
grepping or disassembling it) has to open those files first, so one check
covers all of them. Writing an implementation from memory is allowed and is
not detected.

The container side (``denylist._ACCESS_MONITOR``) finds the protected files by
name hash, watches them with inotify ``IN_OPEN`` and streams one JSON event per
line. Every Python interpreter in the agent image also loads an audit hook
that reports its own opens of those files with the opener's pid; the monitor
takes argv from ``/proc``. Here each inotify open is matched against those
reports: an open with no report came from a non-Python tool (or Python without
the hook), and a report from a process off the allowlist is a direct use.
Stopping, freezing or tampering with the monitor is interference and counts
the same as an access.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from .denylist import CONTAINER_ACCESS_MONITOR_PATH

__all__ = [
    "AccessMonitor",
    "AccessMonitorError",
    "Reconciler",
    "allowlist_rule",
    "python_entry",
]

# An inotify open with no matching hook report after this many monitor seconds
# is unexplained. Reports are sent before the open, so matches are near-instant.
GRACE_SEC = 3.0
HEARTBEAT_TIMEOUT_SEC = 30.0
READY_TIMEOUT_SEC = 300.0
_MAX_PATHS_PER_EVENT = 50

_SITE = r"/(?:site|dist)-packages/"
_PIP_ENTRY = re.compile(r"(?:.*/)?bin/pip(?:3(?:\.\d+)?)?")
_BUILD_ENTRY = re.compile(r"(?:.*/)?bin/pyproject-build")
_PIP_RUNNER = re.compile(rf".*{_SITE}pip/__pip-runner__\.py")
_IN_PROCESS = re.compile(
    rf".*{_SITE}(?:pip/_vendor/)?pyproject_hooks/_in_process/_in_process\.py"
)
_OPENHANDS_TOOL = "/root/.local/share/uv/tools/openhands/"
_OPENHANDS_ENTRIES = ("/usr/local/bin/openhands", "/root/.local/bin/openhands")
# ``ensurepip`` (and so ``python -m venv``) runs pip from its bundled wheel.
_ENSUREPIP = re.compile(
    r"\s*import runpy\s+import sys\s+"
    r"sys\.path = \[(?:'[^'\n]*'(?:, )?)*\] \+ sys\.path\s+"
    r"sys\.argv\[1:\] = \[(?:'[^'\n]*'(?:, )?)*\]\s+"
    r'runpy\.run_module\("pip", run_name="__main__", alter_sys=True\)\s*'
)
_UV_BUILD_HOOKS = ("build_wheel", "build_editable", "prepare_metadata_for_build", "get_requires_for_build")


class AccessMonitorError(RuntimeError):
    """The monitor could not start; the round must not run unmonitored."""


def python_entry(argv: list[str]) -> tuple[str, str] | None:
    """Return ``(mode, value)`` for a Python argv: script path, ``-m`` module or ``-c`` code."""
    if not argv or not os.path.basename(argv[0]).startswith("python"):
        return None
    i = 1
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            return ("script", argv[i + 1]) if i + 1 < len(argv) else None
        if tok.startswith("--"):
            i += 1
            continue
        if tok.startswith("-") and len(tok) > 1:
            for j, ch in enumerate(tok[1:], start=1):
                rest = tok[j + 1 :]
                if ch in "cm":
                    value = rest or (argv[i + 1] if i + 1 < len(argv) else "")
                    return ("module" if ch == "m" else "code", value)
                if ch in "WX":
                    if not rest:
                        i += 1
                    break
            i += 1
            continue
        return ("script", tok)
    return None


def allowlist_rule(
    argv: list[str],
    *,
    main: str | None = None,
    parent_exe: str | None = None,
    tool_entry: bool = False,
    tool_importer: bool = False,
) -> str | None:
    """Name of the toolchain rule that lets this process open banned files, if any.

    Besides the named package-manager and build processes, a tool may load a
    banned module for its own work (pytest reads ``pyproject.toml`` with the
    stdlib TOML parser): allowed when the process entry is a tool and the code
    that caused the open is stdlib or installed-package code, as classified by
    the container monitor. The agent's own code (``/app``, ``/tmp`` scripts,
    ``-c``, packages installed from a local path) never qualifies.
    """
    entry = python_entry(argv)
    if entry is None:
        return None
    mode, value = entry
    if tool_entry and tool_importer and mode != "code":
        return "tool-internal import"
    if mode == "module":
        if value in ("pip", "build"):
            # ``python -m pip`` from a directory with its own ``pip/`` runs that code.
            if main and not re.search(_SITE, main):
                return None
            return f"-m {value}"
        if value.startswith("openhands") and main and main.startswith(_OPENHANDS_TOOL):
            return "agent runtime"
        return None
    if mode == "script":
        if _PIP_ENTRY.fullmatch(value) or _BUILD_ENTRY.fullmatch(value):
            return "pip/build entry script"
        if _PIP_RUNNER.fullmatch(value):
            return "pip build-env installer"
        if _IN_PROCESS.fullmatch(value):
            return "build backend hook"
        if value in _OPENHANDS_ENTRIES or value.startswith(_OPENHANDS_TOOL):
            return "agent runtime"
        return None
    if _ENSUREPIP.fullmatch(value):
        return "ensurepip"
    if (
        parent_exe
        and os.path.basename(parent_exe) == "uv"
        and any(hook in value for hook in _UV_BUILD_HOOKS)
    ):
        return "uv build backend"
    return None


def _paths_text(paths: list[str]) -> str:
    shown = ", ".join(f"`{p}`" for p in paths[:3])
    if len(paths) > 3:
        shown += f" and {len(paths) - 3} more file(s)"
    return shown


@dataclass
class _Pending:
    opens: deque = field(default_factory=deque)  # monitor ts
    reports: deque = field(default_factory=deque)  # (monitor ts, allowlisted)


class Reconciler:
    """Match inotify opens with hook reports; pure, so it is unit-testable."""

    def __init__(self, protected: list[str], *, grace_sec: float = GRACE_SEC, round_index: int = 0):
        self.protected = list(protected)
        self.grace_sec = grace_sec
        self.round_index = round_index
        self.opens = [0] * len(self.protected)
        self.excused = [0] * len(self.protected)
        self.events: list[dict] = []
        self._pending: dict[int, _Pending] = {}
        self._by_pid: dict[int, dict] = {}
        self._last_ts = 0.0

    def _path(self, index: int) -> str:
        if 0 <= index < len(self.protected):
            return self.protected[index]
        return f"<protected file #{index}>"

    def _add(self, event: dict) -> dict:
        event.setdefault("round", self.round_index)
        self.events.append(event)
        return event

    def interference(self, message: str, *, ts: float | None = None, **extra) -> dict:
        return self._add({"kind": "interference", "message": message, "ts": ts, **extra})

    def feed(self, event: dict) -> list[dict]:
        """Apply one monitor event; return the violation events it produced."""
        kind = event.get("t")
        ts = float(event.get("ts") or self._last_ts)
        self._last_ts = max(self._last_ts, ts)
        new: list[dict] = []
        if kind == "open":
            index = int(event["f"])
            self.opens[index] += 1
            pending = self._pending.setdefault(index, _Pending())
            if pending.reports:
                _ts, allowed = pending.reports.popleft()
                if allowed:
                    self.excused[index] += 1
            else:
                pending.opens.append(ts)
        elif kind == "attr":
            new.extend(self._report(event, ts))
        elif kind == "tamper":
            new.append(self.interference(
                f"`{event.get('path')}` was {event.get('detail') or 'changed'}; "
                "the access monitor relies on it",
                ts=ts, path=event.get("path"),
            ))
        elif kind == "forged":
            new.append(self.interference(
                f"a process sent a forged access report ({event.get('detail')})",
                ts=ts, pid=event.get("pid"),
            ))
        elif kind == "overflow":
            new.append(self.interference(
                "protected files were opened faster than the monitor could count "
                "(inotify queue overflow)",
                ts=ts,
            ))
        new.extend(self.expire(self._last_ts))
        return new

    def _report(self, event: dict, ts: float) -> list[dict]:
        index = int(event["f"])
        argv = [str(a) for a in (event.get("argv") or [])]
        rule = allowlist_rule(
            argv,
            main=event.get("main"),
            parent_exe=event.get("parent_exe"),
            tool_entry=bool(event.get("tool_entry")),
            tool_importer=bool(event.get("tool_importer")),
        )
        pending = self._pending.setdefault(index, _Pending())
        if pending.opens:
            pending.opens.popleft()
            if rule:
                self.excused[index] += 1
        else:
            pending.reports.append((ts, bool(rule)))
        if rule:
            return []
        path = self._path(index)
        pid = int(event.get("pid") or 0)
        existing = self._by_pid.get(pid)
        if existing is not None:
            if path not in existing["paths"] and len(existing["paths"]) < _MAX_PATHS_PER_EVENT:
                existing["paths"].append(path)
                existing["message"] = self._python_message(existing)
            return []
        record = {
            "kind": "access",
            "opener": "python",
            "pid": pid,
            "argv": argv,
            "argv_source": event.get("argv_source"),
            "importer": event.get("importer"),
            "paths": [path],
            "ts": ts,
        }
        record["message"] = self._python_message(record)
        self._by_pid[pid] = record
        return [self._add(record)]

    @staticmethod
    def _python_message(record: dict) -> str:
        cmd = shlex.join(record["argv"])[:300] or "<unknown>"
        return f"`{cmd}` (pid {record['pid']}) opened {_paths_text(record['paths'])}"

    def expire(self, now: float, *, final: bool = False) -> list[dict]:
        """Report opens nobody explained; drop reports whose open never came."""
        cutoff = now - self.grace_sec
        stale: list[str] = []
        first_ts: float | None = None
        for index, pending in self._pending.items():
            while pending.opens and (final or pending.opens[0] < cutoff):
                opened = pending.opens.popleft()
                first_ts = opened if first_ts is None else min(first_ts, opened)
                path = self._path(index)
                if path not in stale:
                    stale.append(path)
            while pending.reports and (final or pending.reports[0][0] < cutoff):
                pending.reports.popleft()
        if not stale:
            return []
        record = {
            "kind": "access",
            "opener": "unattributed",
            "argv": None,
            "paths": stale[:_MAX_PATHS_PER_EVENT],
            "ts": first_ts,
            "message": (
                f"{_paths_text(stale)} opened by a process the Python audit hook did "
                "not see (a non-Python tool such as cat, od, cp or grep, or Python "
                "started without the hook)"
            ),
        }
        return [self._add(record)]

    def pending_open_ts(self) -> float | None:
        stamps = [p.opens[-1] for p in self._pending.values() if p.opens]
        return max(stamps) if stamps else None

    def stats(self) -> list[dict]:
        return [
            {"path": path, "opens": self.opens[i], "excused": self.excused[i]}
            for i, path in enumerate(self.protected)
            if self.opens[i]
        ]


class AccessMonitor:
    """Run the in-container monitor for one solve round and reconcile its stream."""

    def __init__(
        self,
        container_id: str,
        *,
        round_index: int = 0,
        log_path: Path | None = None,
        grace_sec: float = GRACE_SEC,
        heartbeat_timeout_sec: float = HEARTBEAT_TIMEOUT_SEC,
    ):
        self.container_id = container_id
        self.round_index = round_index
        self.log_path = Path(log_path) if log_path else None
        self.grace_sec = grace_sec
        self.heartbeat_timeout_sec = heartbeat_timeout_sec
        self.violated = threading.Event()
        self.reconciler: Reconciler | None = None
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._exited = threading.Event()
        self._stopping = False
        self._start_error: str | None = None
        self._last_line = time.monotonic()
        self._last_ts = 0.0
        self._log = None
        self._threads: list[threading.Thread] = []

    def argv(self) -> list[str]:
        return [
            "docker", "exec", "-i", "-u", "root", self.container_id,
            "python3", "-I", "-S", CONTAINER_ACCESS_MONITOR_PATH,
        ]

    def start(self, timeout_sec: float = READY_TIMEOUT_SEC) -> None:
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = open(self.log_path, "w", encoding="utf-8")
        try:
            self._proc = subprocess.Popen(
                self.argv(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise AccessMonitorError(f"cannot run docker exec: {exc}") from exc
        for target in (self._read_stdout, self._read_stderr, self._watchdog):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)
        deadline = time.monotonic() + timeout_sec
        while not self._ready.is_set():
            if self._exited.is_set() or time.monotonic() > deadline:
                reason = self._start_error or (
                    "monitor exited before it was ready"
                    if self._exited.is_set()
                    else f"no ready signal within {timeout_sec:g}s"
                )
                self._stopping = True
                self._terminate()
                raise AccessMonitorError(reason)
            self._ready.wait(0.2)

    def _write_log(self, line: str) -> None:
        if self._log is not None:
            self._log.write(line + "\n")
            self._log.flush()

    def _read_stdout(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for raw in self._proc.stdout:
            self._last_line = time.monotonic()
            line = raw.strip()
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get("t")
            if kind != "hb":
                self._write_log(line if kind != "ready" else json.dumps(
                    {k: v for k, v in event.items() if k != "guarded"}))
            if kind == "ready":
                self.reconciler = Reconciler(
                    [str(p) for p in event.get("protected") or []],
                    grace_sec=self.grace_sec,
                    round_index=self.round_index,
                )
                self._ready.set()
                continue
            if kind == "error":
                self._start_error = str(event.get("detail") or "monitor error")
                continue
            if self.reconciler is None or kind == "bye":
                continue
            with self._lock:
                self._last_ts = max(self._last_ts, float(event.get("ts") or 0.0))
                new = self.reconciler.feed(event)
            if new:
                self.violated.set()
        self._exited.set()
        if self._ready.is_set() and not self._stopping:
            self._flag("the access monitor process exited while the agent was running")

    def _read_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        tail: list[str] = []
        for raw in self._proc.stderr:
            tail = (tail + [raw.rstrip()])[-20:]
            self._write_log(json.dumps({"t": "stderr", "line": raw.rstrip()}))
        if tail and not self._start_error:
            self._start_error = " | ".join(tail)[-500:]

    def _watchdog(self) -> None:
        while not self._exited.wait(1.0):
            if self._stopping or not self._ready.is_set():
                continue
            silent = time.monotonic() - self._last_line
            if silent > self.heartbeat_timeout_sec:
                self._flag(f"the access monitor stopped responding for {silent:.0f}s")
                return

    def _flag(self, message: str) -> None:
        if self.reconciler is None:
            return
        with self._lock:
            self.reconciler.interference(message, ts=self._last_ts)
        self.violated.set()

    def stop(self) -> list[dict]:
        """Let late opens settle, report the unexplained ones, stop the monitor."""
        if self.reconciler is not None and not self._exited.is_set():
            deadline = time.monotonic() + self.grace_sec + 5.0
            while time.monotonic() < deadline and not self._exited.is_set():
                with self._lock:
                    pending = self.reconciler.pending_open_ts()
                    now = self._last_ts
                if pending is None or now >= pending + self.grace_sec:
                    break
                time.sleep(0.2)
        self._stopping = True
        events: list[dict] = []
        if self.reconciler is not None:
            with self._lock:
                if self.reconciler.expire(self._last_ts, final=True):
                    self.violated.set()
                events = list(self.reconciler.events)
                stats = self.reconciler.stats()
            self._write_log(json.dumps({"t": "summary", "files": stats, "violations": len(events)}))
        self._terminate()
        if self._log is not None:
            self._log.close()
            self._log = None
        return events

    def _terminate(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            subprocess.run(
                ["docker", "exec", self.container_id, "pkill", "-f", CONTAINER_ACCESS_MONITOR_PATH],
                capture_output=True,
                timeout=30,
            )
        for thread in self._threads:
            thread.join(timeout=5)
