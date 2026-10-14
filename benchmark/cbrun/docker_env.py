"""Thin Docker lifecycle helpers for cbrun.

cbrun manages its own short-lived per-trial container (``docker run -d`` + a
sleep keepalive, then ``docker exec``), so the solver harness stays
self-contained. The solve exec
enforces a server-side wall clock with the ``timeout`` coreutil and a local
stall watchdog; both guarantee the in-container agent is stopped before the
judge runs against the final workspace.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .state import platform_name

__all__ = [
    "docker_available",
    "image_exists",
    "ExecResult",
    "Container",
    "CONTAINER_MEMORY",
]

# Hard memory cap for every container cbrun starts (solve, judge, scans). The
# host runs several trials side by side; without a cap one runaway program can
# exhaust host memory and stall every other trial with it. Swap is capped to the
# same value so the limit is not bypassed through swap.
CONTAINER_MEMORY = "16g"


def docker_available() -> bool:
    try:
        proc = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def image_exists(tag: str) -> bool:
    proc = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


@dataclass
class ExecResult:
    exit_code: int
    timed_out: bool = False
    stall_killed: bool = False
    aborted: bool = False
    seconds: float = 0.0
    tail: str = ""


class Container:
    """A running container the runner controls for one trial."""

    def __init__(self, container_id: str):
        self.container_id = container_id
        self.paused = False

    @staticmethod
    def build_run_argv(
        image: str,
        *,
        gpus: str | None = None,
        network: str | None = "host",
        env: dict[str, str] | None = None,
        name: str | None = None,
        block_hosts: tuple[str, ...] | None = None,
        mounts: list[tuple[str, str]] | None = None,
    ) -> list[str]:
        """Build the ``docker run`` argv (pure, for testing).

        ``--gpus`` is only added when requested (CPU cases pass ``gpus=None``),
        and the Docker socket is never mounted, so a solving agent cannot reach
        the host daemon.
        """
        argv = ["docker", "run", "--platform", platform_name(), "-d", "--rm"]
        argv += ["--memory", CONTAINER_MEMORY, "--memory-swap", CONTAINER_MEMORY]
        if name:
            argv += ["--name", name]
        if gpus:
            argv += ["--gpus", gpus]
        if network:
            argv += ["--network", network]
        for host in block_hosts or ():
            argv += ["--add-host", f"{host}:0.0.0.0"]
        for host_path, container_path in mounts or []:
            argv += ["-v", f"{host_path}:{container_path}"]
        for key in (env or {}):
            argv += ["-e", key]
        argv += [image, "sleep", "infinity"]
        return argv

    @classmethod
    def start(
        cls,
        image: str,
        *,
        gpus: str | None = None,
        network: str | None = "host",
        env: dict[str, str] | None = None,
        name: str | None = None,
        block_hosts: tuple[str, ...] | None = None,
        mounts: list[tuple[str, str]] | None = None,
    ) -> "Container":
        """Start a detached keepalive container."""
        argv = cls.build_run_argv(
            image,
            gpus=gpus,
            network=network,
            env=env,
            name=name,
            block_hosts=block_hosts,
            mounts=mounts,
        )
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env={**os.environ, **(env or {})},
        )
        if proc.returncode != 0:
            raise RuntimeError(f"docker run failed: {proc.stderr.strip()}")
        return cls(proc.stdout.strip())

    def exec(
        self,
        command: str,
        *,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: float | None = None,
        user: str | None = None,
    ) -> ExecResult:
        """Run a bounded command, capturing output (used for install/judge)."""
        if timeout_sec is not None:
            if timeout_sec <= 0:
                raise ValueError("command timeout must be positive")
            command = f"timeout --signal=KILL {timeout_sec:g} bash -o pipefail -lc {_shq(command)}"
        argv = self._exec_argv(command, workdir=workdir, env=env, user=user)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                errors="replace",
                env={**os.environ, **(env or {})},
                timeout=timeout_sec + 5 if timeout_sec is not None else 60,
            )
        except subprocess.TimeoutExpired as exc:
            tail = _as_text(exc.stdout) + _as_text(exc.stderr)
            return ExecResult(
                exit_code=124,
                timed_out=True,
                seconds=time.monotonic() - start,
                tail=_tail(tail),
            )
        seconds = time.monotonic() - start
        return ExecResult(
            exit_code=proc.returncode,
            timed_out=_exec_hit_wall(timeout_sec, proc.returncode, seconds),
            seconds=seconds,
            tail=_tail(proc.stdout + proc.stderr),
        )

    def exec_solve(
        self,
        command: str,
        *,
        workdir: str,
        env: dict[str, str] | None,
        wall_timeout_sec: float,
        stall_window_sec: float,
        log_path: Path,
        stall_marker: str,
        user: str | None = None,
        activity_path: str | None = None,
        abort: threading.Event | None = None,
    ) -> ExecResult:
        """Run the agent solve with a wall clock + stall watchdog.

        The wall clock is enforced server-side via ``timeout`` so the agent is
        stopped inside the container even if the local client is interrupted.
        The stall watchdog stops the agent when stdout and ``activity_path``
        (typically ``/app``) both stay quiet for ``stall_window_sec``.
        Setting ``abort`` stops the agent the same way (used by the access monitor).
        """
        wrapped = (
            f"timeout --signal=KILL {int(wall_timeout_sec)} "
            f"bash -o pipefail -lc {_shq(command)}"
        )
        argv = self._exec_argv(wrapped, workdir=workdir, env=env, user=user)

        log_path.parent.mkdir(parents=True, exist_ok=True)
        start = time.monotonic()
        last_activity = [start]
        last_mtime = [self._latest_mtime(activity_path) if activity_path else None]
        stall_killed = [False]
        aborted = False

        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            env={**os.environ, **(env or {})},
            bufsize=1,
        )

        def _pump() -> None:
            with open(log_path, "w", encoding="utf-8") as fh:
                assert proc.stdout is not None
                for line in proc.stdout:
                    fh.write(line)
                    fh.flush()
                    last_activity[0] = time.monotonic()

        pump = threading.Thread(target=_pump, daemon=True)
        pump.start()

        while True:
            try:
                proc.wait(timeout=2.0)
                break
            except subprocess.TimeoutExpired:
                pass
            now = time.monotonic()
            if abort is not None and abort.is_set():
                aborted = True
                self._stop_agent(stall_marker)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break
            if activity_path:
                current_mtime = self._latest_mtime(activity_path)
                if (
                    current_mtime is not None
                    and (last_mtime[0] is None or current_mtime > last_mtime[0])
                ):
                    last_mtime[0] = current_mtime
                    last_activity[0] = now
            if stall_window_sec > 0 and (now - last_activity[0]) > stall_window_sec:
                stall_killed[0] = True
                self._stop_agent(stall_marker)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break
            # Wall clock is enforced by container-side `timeout`; this is a safety
            # net in case the client outlives it.
            if (now - start) > (wall_timeout_sec + 120):
                self._stop_agent(stall_marker)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break

        pump.join(timeout=10)
        exit_code = proc.returncode if proc.returncode is not None else -1
        # `timeout` exits 124 (TERM) / 137 (KILL) when the wall clock fires.
        timed_out = exit_code in (124, 137) and not stall_killed[0] and not aborted
        # Defensive sweep so no lingering agent process mutates /app during judge.
        self._stop_agent(stall_marker)
        tail = _tail(log_path.read_text(encoding="utf-8", errors="replace")) if log_path.is_file() else ""
        return ExecResult(
            exit_code=exit_code,
            timed_out=timed_out,
            stall_killed=stall_killed[0],
            aborted=aborted,
            seconds=time.monotonic() - start,
            tail=tail,
        )

    def _latest_mtime(self, path: str) -> float | None:
        """Newest file mtime under *path*, or None when the tree is empty."""
        cmd = (
            f"find {_shq(path)} -type f -printf '%T@\\n' 2>/dev/null | sort -n | tail -1"
        )
        try:
            res = self.exec(cmd, timeout_sec=15.0)
        except (OSError, RuntimeError):
            return None
        text = (res.tail or "").strip().splitlines()
        if not text:
            return None
        try:
            return float(text[-1].strip())
        except ValueError:
            return None

    def _stop_agent(self, marker: str) -> None:
        """Best-effort kill of the agent process tree by a unique marker."""
        cmd = f"pkill -9 -f {_shq(marker)} 2>/dev/null || true"
        try:
            subprocess.run(
                ["docker", "exec", self.container_id, "bash", "-lc", cmd],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def cp_to(self, src: Path, dst: str) -> None:
        proc = subprocess.run(
            ["docker", "cp", str(src), f"{self.container_id}:{dst}"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"docker cp into container failed: {proc.stderr.strip()}")

    def cp_from(self, src: str, dst: Path) -> bool:
        dst.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["docker", "cp", f"{self.container_id}:{src}", str(dst)],
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0

    def write_file(self, path: str, content: bytes) -> None:
        """Write bytes to a path inside the container via a temp file + cp."""
        parent = path.rsplit("/", 1)[0] or "/"
        self.exec(f"mkdir -p {_shq(parent)}")
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            self.cp_to(tmp_path, path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def path_exists(self, path: str) -> bool:
        res = self.exec(f"test -e {_shq(path)}")
        return res.exit_code == 0

    def pause(self) -> None:
        """Freeze candidate processes before copying a snapshot."""
        if self.paused:
            return
        proc = subprocess.run(
            ["docker", "pause", self.container_id],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode:
            raise RuntimeError(f"cannot freeze candidate container: {proc.stderr.strip()}")
        self.paused = True

    def remove(self) -> None:
        subprocess.run(
            ["docker", "rm", "-f", self.container_id],
            capture_output=True,
            text=True,
        )

    def _exec_argv(
        self,
        command: str,
        *,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
        user: str | None = None,
    ) -> list[str]:
        argv = ["docker", "exec"]
        if workdir:
            argv += ["-w", workdir]
        if user:
            argv += ["-u", user]
        for key in (env or {}):
            argv += ["-e", key]
        argv += [self.container_id, "bash", "-o", "pipefail", "-lc", command]
        return argv

    def __enter__(self) -> "Container":
        return self

    def __exit__(self, *exc) -> None:
        self.remove()


def _exec_hit_wall(timeout_sec: float | None, exit_code: int, seconds: float) -> bool:
    """True when the container-side ``timeout --signal=KILL`` fired.

    Exit 137 below the budget is a kill (OOM or explicit), not a wall hit.
    """
    return timeout_sec is not None and exit_code == 137 and seconds >= timeout_sec


def _shq(text: str) -> str:
    import shlex

    return shlex.quote(text)


def _as_text(value: str | bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def _tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if text else ""
