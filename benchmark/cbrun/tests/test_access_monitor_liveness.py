"""A silent monitor stream is judged by the monitor's process state, not by silence alone."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cbrun import access_monitor as am
from cbrun.access_monitor import AccessMonitor, monitor_process_state
from cbrun.denylist import CONTAINER_ACCESS_MONITOR_PATH

_HEADER = "PID                 STAT                COMMAND\n"
_MON = f"python3 -I -S {CONTAINER_ACCESS_MONITOR_PATH}"


@pytest.mark.parametrize(
    "rows, state, needle",
    [
        ([("101", "Ss", _MON)], "alive", "state Ss"),
        ([("101", "R+", _MON)], "alive", "state R+"),
        ([("101", "D", _MON)], "alive", "state D"),
        ([("101", "Ts", _MON)], "interference", "stopped"),
        ([("101", "t", _MON)], "interference", "stopped"),
        ([("101", "Z", _MON)], "interference", "exited"),
        ([("7", "Ss", "sleep infinity")], "interference", "gone"),
        ([], "interference", "gone"),
        # A copy the agent starts cannot cover for a stopped monitor.
        ([("101", "Ts", _MON), ("102", "S", _MON)], "interference", "stopped"),
        # Other invocations of the same script are not the monitor.
        ([("101", "S", f"{_MON} --list"), ("102", "S", f"pkill -f {CONTAINER_ACCESS_MONITOR_PATH}")],
         "interference", "gone"),
        ([("101", "W", _MON)], "unknown", "unrecognized"),
    ],
)
def test_monitor_process_state(rows: list[tuple[str, str, str]], state: str, needle: str) -> None:
    text = _HEADER + "".join(f"{pid:<20}{stat:<20}{args}\n" for pid, stat, args in rows)
    got, detail = monitor_process_state(text)
    assert got == state
    assert needle in detail


# A stand-in for the container monitor's stream, driven by its first argument.
FAKE_STREAM = r"""
import json, select, sys, time
mode = sys.argv[1]
start = time.monotonic()
def emit(**e):
    e.setdefault("ts", round(time.monotonic() - start, 3))
    print(json.dumps(e), flush=True)
def stdin_closed(wait):
    ready, _, _ = select.select([sys.stdin], [], [], wait)
    return bool(ready) and not sys.stdin.buffer.raw.read(4096)
emit(t="ready", pid=1, protected=["/x/pkg/__init__.py"], guarded=[])
emit(t="hb")
if mode == "stall":
    time.sleep(3.5)
while not stdin_closed(0.2):
    if mode != "silent":
        emit(t="hb")
if mode == "late_open":
    emit(t="open", f=0)
if mode != "no_bye":
    emit(t="bye")
"""


class _LocalMonitor(AccessMonitor):
    def __init__(self, script: Path, mode: str, probes: list[tuple[str, str]], **kwargs):
        self.calls: list[str] = []
        answers = iter(probes)

        def probe(container_id: str) -> tuple[str, str]:
            self.calls.append(container_id)
            return next(answers)

        super().__init__("cid", grace_sec=0.5, heartbeat_timeout_sec=1.0, probe=probe, **kwargs)
        self._argv = [sys.executable, str(script), mode]

    def argv(self) -> list[str]:
        return self._argv


def _monitor(tmp_path: Path, mode: str, probes: list[tuple[str, str]], **kwargs) -> _LocalMonitor:
    script = tmp_path / "fake_stream.py"
    script.write_text(FAKE_STREAM)
    monitor = _LocalMonitor(script, mode, probes, log_path=tmp_path / "monitor.jsonl", **kwargs)
    monitor.start(timeout_sec=30)
    return monitor


def test_late_stream_with_live_process_is_not_a_violation(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, "stall", [("alive", "pid 9 state S")] * 5)
    time.sleep(5.0)
    events = monitor.stop()
    assert monitor.calls, "the watchdog never probed the silent stream"
    assert events == []
    assert not monitor.abort.is_set()
    assert monitor.infra_error is None


def test_stopped_monitor_process_is_interference(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, "silent", [("interference", "the access monitor process is stopped (pid 9 state T)")])
    assert monitor.violated.wait(10)
    events = monitor.stop()
    assert monitor.abort.is_set()
    assert [e["kind"] for e in events] == ["interference"]
    assert "stopped" in events[0]["message"]
    assert monitor.infra_error is None


def test_failed_probe_is_an_infrastructure_failure(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, "silent", [("unknown", "docker top gave no answer within 30s")])
    assert monitor.abort.wait(10)
    events = monitor.stop()
    assert not monitor.violated.is_set()
    assert events == []
    assert "docker top gave no answer" in (monitor.infra_error or "")


def test_silence_past_the_stall_limit_is_an_infrastructure_failure(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, "silent", [("alive", "pid 9 state S")] * 10, stall_limit_sec=3.0)
    assert monitor.abort.wait(10)
    events = monitor.stop()
    assert not monitor.violated.is_set()
    assert events == []
    assert "limit 3s" in (monitor.infra_error or "")


def test_opens_delivered_at_shutdown_are_reconciled(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, "late_open", [])
    time.sleep(0.5)
    events = monitor.stop()
    assert [e.get("opener") for e in events] == ["unattributed"]
    assert monitor.violated.is_set()
    assert monitor.infra_error is None


def test_stream_without_final_report_is_an_infrastructure_failure(tmp_path: Path) -> None:
    monitor = _monitor(tmp_path, "no_bye", [])
    time.sleep(0.5)
    assert monitor.stop() == []
    assert "final report" in (monitor.infra_error or "")


# The monitor's stand-in inside a real container; the probe reads it through docker top.
CONTAINER_STREAM = r"""
import json, os, select, sys, time
open("/tmp/monitor.pid", "w").write(str(os.getpid()))
start = time.monotonic()
def emit(**e):
    e.setdefault("ts", round(time.monotonic() - start, 3))
    print(json.dumps(e), flush=True)
emit(t="ready", pid=os.getpid(), protected=["/x/pkg/__init__.py"], guarded=[])
quiet = os.path.exists("/tmp/quiet")
while True:
    ready, _, _ = select.select([sys.stdin], [], [], 0.5)
    if ready and not sys.stdin.buffer.raw.read(4096):
        emit(t="bye")
        break
    if not quiet:
        emit(t="hb")
"""
TEST_IMAGE = "python:3.13-slim-bookworm"


@pytest.fixture
def container(tmp_path: Path):
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("docker not available")
    if subprocess.run([docker, "image", "inspect", TEST_IMAGE], capture_output=True).returncode != 0:
        pytest.skip(f"{TEST_IMAGE} not present locally")
    script = tmp_path / "access_monitor.py"
    script.write_text(CONTAINER_STREAM)
    cid = subprocess.run(
        [docker, "run", "-d", "--rm", "--pull", "never", "--network", "none", TEST_IMAGE, "sleep", "infinity"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    try:
        parent = CONTAINER_ACCESS_MONITOR_PATH.rsplit("/", 1)[0]
        subprocess.run([docker, "exec", cid, "mkdir", "-p", parent], check=True)
        subprocess.run([docker, "cp", str(script), f"{cid}:{CONTAINER_ACCESS_MONITOR_PATH}"], check=True)
        yield cid
    finally:
        subprocess.run([docker, "rm", "-f", cid], capture_output=True)


def _in_container(cid: str, command: str) -> None:
    subprocess.run(["docker", "exec", cid, "sh", "-c", command], check=True, timeout=60)


@pytest.mark.parametrize("signal_name, needle", [("STOP", "stopped"), ("KILL", "exited")])
def test_agent_stopping_or_killing_the_monitor_in_docker(
    container: str, tmp_path: Path, signal_name: str, needle: str
) -> None:
    monitor = AccessMonitor(container, log_path=tmp_path / "monitor.jsonl", grace_sec=0.5, heartbeat_timeout_sec=3.0)
    monitor.start(timeout_sec=60)
    _in_container(container, f"kill -{signal_name} $(cat /tmp/monitor.pid)")
    assert monitor.violated.wait(20)
    events = monitor.stop()
    assert monitor.abort.is_set()
    assert needle in events[0]["message"]


def test_quiet_live_monitor_in_docker_is_waited_on(container: str, tmp_path: Path) -> None:
    _in_container(container, "touch /tmp/quiet")
    monitor = AccessMonitor(
        container, log_path=tmp_path / "monitor.jsonl", grace_sec=0.5,
        heartbeat_timeout_sec=2.0, stall_limit_sec=8.0,
    )
    monitor.start(timeout_sec=60)
    assert monitor.abort.wait(20)
    events = monitor.stop()
    assert events == []
    assert not monitor.violated.is_set()
    assert "silent" in (monitor.infra_error or "")
    probes = [line for line in (tmp_path / "monitor.jsonl").read_text().splitlines() if '"probe"' in line]
    assert probes and all('"alive"' in line for line in probes)


def test_probe_reports_a_missing_container_as_unknown() -> None:
    if not shutil.which("docker"):
        pytest.skip("docker not available")
    state, detail = am.probe_monitor("cbrun-no-such-container", timeout_sec=30)
    assert state == "unknown"
    assert "docker top exited" in detail
