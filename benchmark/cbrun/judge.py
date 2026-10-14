"""Hidden-gate judging for cbrun.

After the solve phase ends, the runner copies only the candidate ``/app``
tree into a fresh ``:agent`` container (image defaults, no solve env),
injects the cached hidden tests, and runs the Harbor-shared ``final_judge.py``.
Reward is binary; a harness failure is reported as ``judge_error``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .docker_env import Container, _shq
from .images import _agent_user_snippet

__all__ = [
    "JudgeOutcome",
    "FINAL_JUDGE_SRC",
    "LAUNCHER_SRC",
    "run_judge",
    "run_isolated_judge",
    "export_app",
    "import_app",
    "validate_judge_report",
]

# The judge script is shared with the Harbor adapter (single source of truth).
_HARBOR = Path(__file__).resolve().parent.parent / "coding_bench_harbor"
FINAL_JUDGE_SRC = _HARBOR / "final_judge.py"
TEST_COUNTS_SRC = _HARBOR / "test_counts.py"
LAUNCHER_SRC = _HARBOR / "pytest_launcher.py"
NODE_BLOCK_SRC = _HARBOR / "_cb_import_block.cjs"

CONTAINER_TESTS_FINAL = "/tests/final"
CONTAINER_TASK_TOML = "/task.toml"
CONTAINER_JUDGE_PATH = "/tests/final_judge.py"
CONTAINER_LAUNCHER_PATH = "/tests/pytest_launcher.py"
CONTAINER_NODE_BLOCK_PATH = "/tests/_cb_import_block.cjs"
NODE_BLOCK_ESM_SRC = _HARBOR / "_cb_import_block_esm.mjs"
NODE_BLOCK_HOOKS_SRC = _HARBOR / "_cb_import_block_hooks.mjs"
CONTAINER_NODE_BLOCK_ESM_PATH = "/tests/_cb_import_block_esm.mjs"
CONTAINER_NODE_BLOCK_HOOKS_PATH = "/tests/_cb_import_block_hooks.mjs"
# A `node` wrapper first on PATH. Hidden-test harnesses commonly rebuild the
# child environment from a keep-list (PATH survives, NODE_OPTIONS does not),
# so the ban must ride on the executable, not on inherited variables.
CONTAINER_NODE_SHIM_DIR = "/tests/bin"
CONTAINER_NODE_SHIM_PATH = f"{CONTAINER_NODE_SHIM_DIR}/node"
NODE_SHIM_DIR_ENV = "CODING_BENCH_NODE_SHIM_DIR"
CONTAINER_VERIFIER_DIR = "/logs/verifier"
CONTAINER_APP = "/app"

_PYTHON_BAN_ECOSYSTEMS = frozenset({"pip", "conda", "source"})
_NODE_BAN_ECOSYSTEMS = frozenset({"npm"})
_NODE_PRELOAD_FLAGS = (
    f"--require {CONTAINER_NODE_BLOCK_PATH} --import {CONTAINER_NODE_BLOCK_ESM_PATH}"
)


@dataclass
class JudgeOutcome:
    reward: float
    judge_error: str | None
    exit_code: int
    seconds: float
    report: dict = field(default_factory=dict)
    substrates_missing: list[str] = field(default_factory=list)
    completed: bool = True
    incomplete_reason: str | None = None


def validate_judge_report(report: dict | None) -> tuple[float, str | None]:
    """Return ``(reward, judge_error)`` from a final_judge report.

    Reward must be 0 or 1. A passing reward without verified counts, or
    with failed/error tests, is a harness error and scores 0.
    """
    if not isinstance(report, dict) or not report:
        return 0.0, "final_judge produced no report"
    raw_reward = report.get("reward")
    reward = (
        float(raw_reward)
        if isinstance(raw_reward, (int, float)) and not isinstance(raw_reward, bool)
        else -1.0
    )
    judge_error = report.get("judge_error")
    if judge_error:
        return 0.0, str(judge_error)
    final = report.get("final")
    if reward not in (0.0, 1.0):
        return 0.0, "invalid non-binary reward in judge report"
    if not isinstance(final, dict) or final.get("counts_parsed") is not True or not final.get("total_count"):
        return 0.0, "judge report has no verified test counts"
    if reward == 1.0 and (
        final.get("failed_count", 0) or final.get("error_count", 0) or not final.get("passed_count")
    ):
        return 0.0, "passing reward contradicts test counts"
    return reward, None


def export_app(container: Container, dest: Path) -> Path:
    """Copy ``/app`` files out of *container* onto the host. No env is copied."""
    dest = Path(dest)
    if dest.exists():
        import shutil

        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    ok = container.cp_from(CONTAINER_APP, dest)
    if not ok:
        raise RuntimeError("could not export candidate /app; refusing to judge an empty replacement")
    workspace = dest / "app"
    return workspace if workspace.is_dir() else dest


def import_app(container: Container, host_app: Path) -> None:
    """Copy a host ``/app`` tree into *container* at ``/app``."""
    container.exec(f"mkdir -p {CONTAINER_APP}")
    host_app = Path(host_app)
    if not host_app.is_dir():
        return
    for child in sorted(host_app.iterdir()):
        container.cp_to(child, f"{CONTAINER_APP}/")
    container.exec(f"chmod -R a+rX {CONTAINER_APP}")


def _denylist_ecosystem(denylist) -> str:
    return str(getattr(denylist, "ecosystem", "") or "").strip().lower()


def _import_ban_env(denylist) -> dict[str, str]:
    """Process-level import ban, routed by ecosystem. Never enable both blindly."""
    if denylist is None:
        return {}
    tokens = [str(x).strip() for x in getattr(denylist, "import_ban", ()) if str(x).strip()]
    if not tokens:
        return {}
    eco = _denylist_ecosystem(denylist)
    env = {"CODING_BENCH_IMPORT_BAN": ",".join(tokens)}
    if eco in _PYTHON_BAN_ECOSYSTEMS:
        return env
    if eco in _NODE_BAN_ECOSYSTEMS:
        env["NODE_OPTIONS"] = _NODE_PRELOAD_FLAGS
        return env
    return env


def _node_gate_files() -> tuple[tuple[Path, str], ...]:
    files = (
        (NODE_BLOCK_SRC, CONTAINER_NODE_BLOCK_PATH),
        (NODE_BLOCK_ESM_SRC, CONTAINER_NODE_BLOCK_ESM_PATH),
        (NODE_BLOCK_HOOKS_SRC, CONTAINER_NODE_BLOCK_HOOKS_PATH),
    )
    for src, _dst in files:
        if not src.is_file():
            raise RuntimeError(f"Node import-ban preload not found at {src}")
    return files


def _shell_export(name: str, value: str) -> str:
    return f"export {name}={_shq(value)}"


def _install_node_gate(container: Container, env: dict[str, str]) -> None:
    """Install the Node import ban so it survives a harness that scrubs env.

    Copies the preload scripts, writes ``/tests/bin/node`` (a wrapper that
    bakes the ban variables and the preload flags in front of the real
    interpreter), points ``CODING_BENCH_NODE_SHIM_DIR`` at it for the pytest
    launcher to prepend to ``PATH``, and probes that both the CJS and the
    ESM hook actually refuse a banned import on this image's Node. A probe
    failure raises: the gate must never be silently absent.
    """
    for src, dst in _node_gate_files():
        container.cp_to(src, dst)
        container.exec(f"chmod 644 {_shq(dst)}")
    real = container.exec('readlink -f "$(command -v node)" 2>/dev/null || true')
    found = (real.tail or "").strip().splitlines()
    real_node = found[-1].strip() if found else ""
    if real.exit_code != 0 or not real_node.startswith("/"):
        raise RuntimeError(
            "denylist ecosystem needs a Node import ban but no `node` is on PATH "
            "in the judge image"
        )
    if real_node == CONTAINER_NODE_SHIM_PATH:
        raise RuntimeError("judge image already carries the cbrun node shim on PATH")
    lines = ["#!/bin/sh", "# cbrun judge gate: baked ban env + preload hooks."]
    for key in ("CODING_BENCH_WORKSPACE", "CODING_BENCH_IMPORT_BAN", "CODING_BENCH_JUDGE_BANS"):
        if env.get(key):
            lines.append(_shell_export(key, env[key]))
    lines.append(f'exec {_shq(real_node)} {_NODE_PRELOAD_FLAGS} "$@"')
    container.write_file(CONTAINER_NODE_SHIM_PATH, ("\n".join(lines) + "\n").encode())
    container.exec(f"chmod 755 {CONTAINER_NODE_SHIM_PATH} && chmod a+rX {CONTAINER_NODE_SHIM_DIR}")
    env[NODE_SHIM_DIR_ENV] = CONTAINER_NODE_SHIM_DIR
    _probe_node_gate(container, env, real_node)


def _node_gate_probe_script(token: str | None, real_node: str) -> str:
    """Shell that exits non-zero unless both hooks refuse *token* and the shim wins PATH.

    The banned import is expected to make node exit 1, so the probe captures
    output instead of relying on pipeline status (the exec shell runs with
    ``pipefail``).
    """
    lines = [
        "set -u",
        'D="$(mktemp -d)"',
        "trap 'rm -rf \"$D\"' EXIT",
        'mkdir -p "$D/app"',
    ]
    if token is not None:
        node = f"{_shq(real_node)} {_NODE_PRELOAD_FLAGS}"
        lines += [
            f'printf \'import "%s";\\n\' {_shq(token)} > "$D/app/p.mjs"',
            f'printf \'require("%s");\\n\' {_shq(token)} > "$D/app/p.cjs"',
            f'export CODING_BENCH_WORKSPACE="$D/app" CODING_BENCH_IMPORT_BAN={_shq(token)}',
            f'out="$({node} "$D/app/p.mjs" 2>&1 || true)"',
            'case "$out" in *CODING_BENCH_IMPORT_BAN*) ;; *) echo "esm hook inactive: $out"; exit 3;; esac',
            f'out="$({node} "$D/app/p.cjs" 2>&1 || true)"',
            'case "$out" in *CODING_BENCH_IMPORT_BAN*) ;; *) echo "cjs hook inactive: $out"; exit 4;; esac',
        ]
    lines += [
        f'found="$(PATH={CONTAINER_NODE_SHIM_DIR}:$PATH command -v node)"',
        f'[ "$found" = {_shq(CONTAINER_NODE_SHIM_PATH)} ] || {{ echo "node shim not first on PATH: $found"; exit 5; }}',
        f'{_shq(CONTAINER_NODE_SHIM_PATH)} -e "process.exit(0)" || {{ echo "node shim not executable"; exit 6; }}',
    ]
    return "\n".join(lines) + "\n"


def _pytest_user() -> str:
    return (os.environ.get("CODING_BENCH_PYTEST_USER") or "cbagent").strip() or "cbagent"


def _ensure_pytest_user(container: Container) -> None:
    """Create ``cbagent`` when the judged image lacks it.

    final_judge.py drops pytest to that user only if it exists. A bare
    ``:deliverable`` (canaries, pipeline probes) would otherwise run the suite
    as root and pass tests that every ``:agent`` trial fails.
    """
    res = container.exec(_agent_user_snippet(), timeout_sec=60.0)
    if res.exit_code != 0:
        raise RuntimeError(
            f"cannot create judge user cbagent (exit {res.exit_code}): "
            f"{(res.tail or '').strip()[-400:]}"
        )


def _probe_pip_gate(container: Container) -> None:
    """Refuse to judge when the site .pth hook is unread for the pytest user."""
    user = _pytest_user()
    check = container.exec(f"id -u {_shq(user)}")
    kwargs: dict = {"timeout_sec": 30.0}
    if check.exit_code == 0:
        kwargs["user"] = user
    res = container.exec(
        "python3 -I -c "
        "'import sys; sys.exit(0 if \"cbrun_denylist_hook\" in sys.modules else 7)'",
        **kwargs,
    )
    tail = res.tail or ""
    if res.exit_code != 0 or "Error processing line" in tail:
        who = user if check.exit_code == 0 else "default"
        raise RuntimeError(
            f"pip denylist hook not loaded for judge user {who} "
            f"(exit {res.exit_code}): {tail.strip()[-400:]}"
        )


def _probe_node_gate(container: Container, env: dict[str, str], real_node: str) -> None:
    banned = [x for x in env.get("CODING_BENCH_IMPORT_BAN", "").split(",") if x and not x.endswith("/")]
    token = banned[0] if banned else None
    res = container.exec(_node_gate_probe_script(token, real_node), timeout_sec=120.0)
    if res.exit_code != 0:
        raise RuntimeError(
            f"Node import-ban gate probe failed (exit {res.exit_code}): {(res.tail or '').strip()[-400:]}"
        )


def run_judge(
    container: Container,
    *,
    tests_final_dir: Path,
    task_toml: bytes,
    test_timeout_sec: float,
    artifacts_dir: Path,
    denylist=None,
    judge_bans: list[str] | tuple[str, ...] = (),
    test_seed: str | None = None,
) -> JudgeOutcome:
    """Inject hidden tests + task.toml, run final_judge, parse the reward.

    *test_seed* pins the hidden tests' runtime randomisation (``CB_TEST_SEED``),
    so a rejudge can replay the scenario values of an earlier judge. Trials leave
    it unset and the tests draw a fresh seed.
    """
    if not (Path(tests_final_dir) / "test_manifest.json").is_file():
        raise RuntimeError(f"hidden tests cache invalid: {tests_final_dir}")
    if not FINAL_JUDGE_SRC.is_file():
        raise RuntimeError(f"final_judge.py not found at {FINAL_JUDGE_SRC}")
    if not LAUNCHER_SRC.is_file():
        raise RuntimeError(f"pytest_launcher.py not found at {LAUNCHER_SRC}")

    container.exec(f"rm -rf {CONTAINER_TESTS_FINAL} && mkdir -p {CONTAINER_TESTS_FINAL}")
    for child in sorted(Path(tests_final_dir).iterdir()):
        container.cp_to(child, f"{CONTAINER_TESTS_FINAL}/")

    container.write_file(CONTAINER_TASK_TOML, task_toml)
    container.cp_to(FINAL_JUDGE_SRC, CONTAINER_JUDGE_PATH)
    container.cp_to(TEST_COUNTS_SRC, "/tests/test_counts.py")
    container.cp_to(LAUNCHER_SRC, CONTAINER_LAUNCHER_PATH)
    ban_env = _import_ban_env(denylist)
    container.exec(f"mkdir -p {CONTAINER_VERIFIER_DIR}")
    _ensure_pytest_user(container)

    env = {
        "CODING_BENCH_WORKSPACE": CONTAINER_APP,
        "CODING_BENCH_TESTS_FINAL": CONTAINER_TESTS_FINAL,
        "CODING_BENCH_TASK_TOML": CONTAINER_TASK_TOML,
        "CODING_BENCH_VERIFIER_DIR": CONTAINER_VERIFIER_DIR,
        "CODING_BENCH_PYTEST_LAUNCHER": CONTAINER_LAUNCHER_PATH,
        **ban_env,
    }
    if test_seed is not None:
        env["CB_TEST_SEED"] = str(test_seed)
    bans = [str(x).strip() for x in judge_bans if str(x).strip()]
    if bans:
        env["CODING_BENCH_JUDGE_BANS"] = ",".join(bans)
        if "NODE_OPTIONS" not in env and _denylist_ecosystem(denylist) in _NODE_BAN_ECOSYSTEMS:
            env["NODE_OPTIONS"] = _NODE_PRELOAD_FLAGS
    if "NODE_OPTIONS" in env:
        _install_node_gate(container, env)
    elif (
        _denylist_ecosystem(denylist) in _PYTHON_BAN_ECOSYSTEMS
        and env.get("CODING_BENCH_IMPORT_BAN")
    ):
        _probe_pip_gate(container)
    res = container.exec(
        f"PYTHONPATH=/tests python3 {CONTAINER_JUDGE_PATH}",
        env=env,
        timeout_sec=test_timeout_sec,
    )

    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_local = artifacts_dir / "final_report.json"
    got_report = container.cp_from(
        f"{CONTAINER_VERIFIER_DIR}/final_report.json", report_local
    )
    container.cp_from(
        f"{CONTAINER_VERIFIER_DIR}/final_tests.log", artifacts_dir / "final_tests.log"
    )
    (artifacts_dir / "judge.log").write_text(res.tail, encoding="utf-8")

    report: dict = {}
    if got_report and report_local.is_file():
        try:
            report = json.loads(report_local.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}

    if not isinstance(report, dict):
        report = {}
    reward, judge_error = validate_judge_report(report)
    completed = bool(report)
    incomplete_reason: str | None = None
    if res.timed_out:
        judge_error = f"judge timed out after {test_timeout_sec}s"
        reward = 0.0
        if not completed:
            incomplete_reason = "judge:timeout"
    elif not report:
        judge_error = (
            f"final_judge produced no report (exit {res.exit_code}); "
            f"tail: {res.tail[-800:]}"
        )
        reward = 0.0
        incomplete_reason = (
            "judge:killed" if res.exit_code == 137 else "judge:no_report"
        )
    elif res.exit_code and not judge_error:
        judge_error = f"judge process failed (exit {res.exit_code})"
        reward = 0.0

    return JudgeOutcome(
        reward=reward,
        judge_error=judge_error,
        exit_code=res.exit_code,
        seconds=res.seconds,
        report=report,
        completed=completed,
        incomplete_reason=incomplete_reason,
    )


def run_isolated_judge(
    solve_container: Container,
    *,
    image: str,
    tests_final_dir: Path,
    task_toml: bytes,
    test_timeout_sec: float,
    artifacts_dir: Path,
    workspace_export_dir: Path,
    gpus: str | None = None,
    denylist=None,
    judge_bans: list[str] | tuple[str, ...] = (),
) -> JudgeOutcome:
    """Judge ``/app`` from *solve_container* inside a fresh copy of *image*.

    Only files under ``/app`` cross the boundary. The judge container is
    started from the image default environment (no solve env) and
    ``--network none``.
    """
    host_app = export_app(solve_container, workspace_export_dir)
    from .substrates import SubstrateUnavailable, mounted_substrates

    manifest = _test_manifest(tests_final_dir)
    scratch = Path(artifacts_dir) / "substrates"
    try:
        with mounted_substrates(manifest, scratch) as mounts:
            judge_container = Container.start(
                image,
                gpus=gpus,
                network="none",
                mounts=[(str(item.host), item.container) for item in mounts],
            )
            try:
                import_app(judge_container, host_app)
                return run_judge(
                    judge_container,
                    tests_final_dir=tests_final_dir,
                    task_toml=task_toml,
                    test_timeout_sec=test_timeout_sec,
                    artifacts_dir=artifacts_dir,
                    denylist=denylist,
                    judge_bans=judge_bans,
                )
            finally:
                judge_container.remove()
    except SubstrateUnavailable as exc:
        return JudgeOutcome(
            reward=0.0,
            judge_error=f"substrate {exc.name} unavailable",
            exit_code=0,
            seconds=0.0,
            report={"substrates_missing": [exc.name]},
            substrates_missing=[exc.name],
        )


def _test_manifest(tests_final_dir: Path) -> dict:
    path = Path(tests_final_dir) / "test_manifest.json"
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
