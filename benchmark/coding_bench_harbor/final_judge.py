#!/usr/bin/env python3
"""In-container final-step judge for zero2repo / Harbor.

When ``/tests/final/run_acceptance.sh`` is present it is the authoritative
entry (workspace prep + hidden acceptance in one script). Otherwise falls
back to ``test_manifest.json`` plus ``task.toml`` runner metadata.

Reward is 1.0 only after the judge proves the hidden suite was collected
and executed (parseable summary, total > 0, optional frozen count) and
every executed test passed. An exit code of 0 is not evidence by itself.
"""

from __future__ import annotations

import json
import os
import pwd
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_counts import parse_pytest_outcomes, parse_test_counts

WORKSPACE = Path(os.environ.get("CODING_BENCH_WORKSPACE", "/app"))
TESTS_FINAL = Path(os.environ.get("CODING_BENCH_TESTS_FINAL", "/tests/final"))
CONTAINER_TESTS_PREFIX = "/tests/final"
VERIFIER_DIR = Path(os.environ.get("CODING_BENCH_VERIFIER_DIR", "/logs/verifier"))
TASK_TOML = Path(os.environ.get("CODING_BENCH_TASK_TOML", "/task.toml"))
ACCEPTANCE_SCRIPT_NAME = "run_acceptance.sh"
LAUNCHER_PATH = Path(
    os.environ.get("CODING_BENCH_PYTEST_LAUNCHER", "/tests/pytest_launcher.py")
)
PYTEST_USER = os.environ.get("CODING_BENCH_PYTEST_USER", "cbagent")

_PYTEST_LAUNCH = re.compile(
    r"(?:(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*)"
    r"(?:(?:python3?|py)\s+-m\s+pytest|\bpytest)\b"
    r"(.*)$",
    re.DOTALL,
)
_SHADOW_PYTEST = (
    "pytest.py",
    "pytest/__init__.py",
    "src/pytest.py",
    "src/pytest/__init__.py",
)


class JudgeError(RuntimeError):
    """Raised when the judge cannot prove the hidden suite ran."""


def _load_runner_metadata() -> dict:
    """Load runner metadata from task.toml metadata.runner."""
    candidates = [
        TASK_TOML,
        WORKSPACE / "task.toml",
        Path.cwd() / "task.toml",
        Path("/tests") / "task.toml",
    ]
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib
        except ModuleNotFoundError:
            return {}
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            with open(candidate, "rb") as f:
                data = tomllib.load(f)
            runner = data.get("metadata", {}).get("runner", {})
            if runner:
                if "test_command_template" not in runner and "test_command" in runner:
                    runner = {**runner, "test_command_template": runner["test_command"]}
                return runner
        except Exception:
            continue
    return {}


def _load_final_manifest() -> tuple[Path, dict]:
    manifest_path = TESTS_FINAL / "test_manifest.json"
    if not manifest_path.is_file():
        raise JudgeError(f"missing final test_manifest.json at {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JudgeError(f"invalid test_manifest.json: {exc}") from exc
    if not manifest.get("test_files"):
        raise JudgeError("final test_manifest.json has empty test_files")
    if not str(manifest.get("test_command", "")).strip():
        raise JudgeError("final test_manifest.json missing test_command")
    return manifest_path, manifest


def _skip_install_build(runner: dict) -> dict:
    """Never execute candidate install/build inside the judge container."""
    return {
        "install_command": runner.get("install_command", ""),
        "install_command_status": "skipped",
        "build_command": runner.get("build_command", ""),
        "build_command_status": "skipped",
        "reason": "judge does not execute candidate install/build",
    }


def _reject_shadowed_pytest(workspace: Path) -> None:
    for rel in _SHADOW_PYTEST:
        if (workspace / rel).exists():
            raise JudgeError(f"candidate shadowed pytest at {workspace / rel}")


def _pytest_user() -> str | None:
    override = os.environ.get("CODING_BENCH_PYTEST_USER")
    if override is not None and not override.strip():
        return None
    name = (override or PYTEST_USER).strip()
    if not name:
        return None
    try:
        pwd.getpwnam(name)
    except KeyError:
        return None
    return name


def _product_paths(cmd: str, workspace: Path, workdir: Path) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path)
        if key not in seen:
            seen.add(key)
            paths.append(key)

    match = re.search(r"(?:^|\s)PYTHONPATH=(\S+)", cmd)
    if match:
        for part in match.group(1).split(":"):
            if not part:
                continue
            add(Path(part) if part.startswith("/") else workspace / part)
        return paths
    add(workdir)
    if workdir != workspace:
        add(workspace)
    return paths


def _pytest_rest_args(cmd: str) -> list[str] | None:
    match = _PYTEST_LAUNCH.search(cmd.strip())
    if match is None:
        return None
    rest = match.group(1).strip()
    return shlex.split(rest) if rest else []


def _resolve_test_files(step_dir: Path, manifest: dict) -> list[Path]:
    files: list[Path] = []
    for rel in manifest.get("test_files", []):
        p = step_dir / rel
        if not p.is_file():
            p = step_dir / "tests" / Path(rel).name
        if p.is_file():
            files.append(p)
    if not files:
        raise JudgeError(
            f"no test files found under {step_dir} for {manifest.get('test_files')}"
        )
    return files


def _localize_command(cmd: str, step_dir: Path) -> str:
    """Map adapter-written /tests/final paths to the real tests directory on disk."""
    if CONTAINER_TESTS_PREFIX not in cmd:
        return cmd
    prefix = str(TESTS_FINAL.resolve())
    return cmd.replace(CONTAINER_TESTS_PREFIX, prefix)


def _expand_manifest_command(
    cmd: str, step_dir: Path, manifest: dict, test_files: list[Path]
) -> str:
    cmd = _localize_command(cmd, step_dir)
    for rel in manifest.get("test_files", []):
        rel_norm = Path(rel).as_posix()
        if rel_norm in cmd and str(step_dir / rel_norm) not in cmd:
            cmd = cmd.replace(rel_norm, "")
    cmd = " ".join(cmd.split())
    files_str = " ".join(str(p) for p in test_files)
    test_dir = str(step_dir / "tests")
    if "{test_files}" in cmd or "{test_dir}" in cmd:
        cmd = cmd.replace("{test_files}", files_str).replace("{test_dir}", test_dir)
    elif files_str:
        cmd = f"{cmd} {files_str}"
    return cmd


def _launcher_env(product_paths: list[str]) -> dict[str, str]:
    env = os.environ.copy()
    env["CODING_BENCH_WORKSPACE"] = str(WORKSPACE)
    env["CODING_BENCH_TESTS_FINAL"] = str(TESTS_FINAL)
    env["CODING_BENCH_PRODUCT_PATHS"] = ":".join(product_paths)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONSTARTUP", None)
    env.pop("PYTEST_ADDOPTS", None)
    return env


def _run_logged(command, *, log_path: Path, **kwargs) -> subprocess.CompletedProcess:
    """Write output as it arrives so an outer timeout preserves diagnostics."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as output:
        proc = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, **kwargs)
        captured = getattr(proc, "stdout", None) or getattr(proc, "stderr", None)
        if captured and output.tell() == 0:
            output.write(captured if isinstance(captured, bytes) else str(captured).encode())
    return subprocess.CompletedProcess(
        command,
        proc.returncode,
        stdout=log_path.read_text(encoding="utf-8", errors="replace"),
        stderr="",
    )


def _run_pytest_launcher(
    rest_args: list[str],
    *,
    cwd: Path,
    product_paths: list[str],
) -> subprocess.CompletedProcess:
    if not LAUNCHER_PATH.is_file():
        raise JudgeError(f"pytest launcher missing: {LAUNCHER_PATH}")
    argv = ["python3", "-u", "-I", str(LAUNCHER_PATH), *rest_args]
    user = _pytest_user()
    if user:
        argv = ["runuser", "-u", user, "--", *argv]
    try:
        return _run_logged(
            argv,
            log_path=VERIFIER_DIR / "final_tests.log",
            cwd=str(cwd),
            env=_launcher_env(product_paths),
        )
    except FileNotFoundError as exc:
        raise JudgeError(f"pytest launcher not runnable: {exc}") from exc


def _run_shell(command: str, cwd: Path) -> subprocess.CompletedProcess:
    try:
        return _run_logged(
            "set -o pipefail; " + command,
            log_path=VERIFIER_DIR / "final_tests.log",
            shell=True,
            executable="/bin/bash",
            cwd=str(cwd),
        )
    except FileNotFoundError as exc:
        raise JudgeError(f"test command not available: {exc}") from exc


def _frozen_expected_count(manifest: dict | None) -> int | None:
    if not manifest:
        return None
    raw = manifest.get("expected_test_count", manifest.get("test_count"))
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise JudgeError(f"invalid frozen test count {raw!r}") from exc


def _apply_collection_gate(result: dict, manifest: dict | None = None) -> None:
    """Require a parseable executed-test summary; exit 0 is not enough."""
    if result.get("exit_code") == 86:
        raise JudgeError("pytest execution was incomplete; see the collection audit in final_tests.log")
    if result.get("skipped_count"):
        raise JudgeError("acceptance contains skipped, deselected, or nonstandard test outcomes")
    total = result.get("total_count")
    if not result.get("counts_parsed") or not total:
        raise JudgeError(
            "acceptance did not produce a parseable executed-test summary "
            "(empty output, total=0, or unparsed runner log)"
        )
    expected = _frozen_expected_count(manifest)
    if expected is not None and int(total) != expected:
        raise JudgeError(
            f"executed test count {total} != frozen expected_test_count {expected}"
        )
    failed = int(result.get("failed_count") or 0)
    errors = int(result.get("error_count") or 0)
    passed = int(result.get("passed_count") or 0)
    all_pass = (
        result.get("exit_code") == 0
        and passed == int(total)
        and failed == 0
        and errors == 0
    )
    result["status"] = "passed" if all_pass else "failed"


def _result_from_proc(
    proc: subprocess.CompletedProcess,
    *,
    log_path: Path,
    test_command: str,
    framework_label: str = "",
    extra: dict | None = None,
) -> dict:
    output = (proc.stdout or "") + (proc.stderr or "")
    log_path.write_text(output, encoding="utf-8")
    counts = parse_test_counts(
        output,
        framework_label=framework_label,
        test_command=test_command,
    )
    outcomes = parse_pytest_outcomes(output)
    result = {
        "final_step": None,
        "status": "failed",
        "exit_code": proc.returncode,
        "log": str(log_path),
        "passed_count": counts.passed if counts else None,
        "failed_count": counts.failed if counts else None,
        "error_count": counts.errors if counts else None,
        "skipped_count": counts.skipped if counts else None,
        "total_count": counts.total if counts else None,
        "pass_rate": counts.pass_rate if counts else None,
        "test_framework": counts.framework if counts else None,
        "counts_parsed": counts is not None,
        "passed": counts.passed if counts else 0,
        "failed": (counts.failed + counts.errors) if counts else (0 if proc.returncode == 0 else 1),
        "total": counts.total if counts else 0,
        "failed_tests": list(outcomes["failed"]) if outcomes else [],
        "error_tests": list(outcomes["errors"]) if outcomes else [],
    }
    if extra:
        result.update(extra)
    return result


def _acceptance_script_path() -> Path | None:
    script = TESTS_FINAL / ACCEPTANCE_SCRIPT_NAME
    return script if script.is_file() else None


def _run_acceptance(script_path: Path, workspace: Path) -> dict:
    _reject_shadowed_pytest(workspace)
    cmd = f"bash {script_path}"
    env = os.environ.copy()
    env["PYTHONSAFEPATH"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    try:
        proc = _run_logged(
            "set -o pipefail; " + cmd,
            log_path=VERIFIER_DIR / "run_acceptance.log",
            shell=True,
            executable="/bin/bash",
            cwd=str(workspace),
            env=env,
        )
    except FileNotFoundError as exc:
        raise JudgeError(f"acceptance script not runnable: {exc}") from exc
    result = _result_from_proc(
        proc,
        log_path=VERIFIER_DIR / "run_acceptance.log",
        test_command=cmd,
        extra={"acceptance_script": str(script_path)},
    )
    _apply_collection_gate(result)
    return result


def _run_final(step_dir: Path, manifest: dict, workspace: Path) -> dict:
    _reject_shadowed_pytest(workspace)
    workdir_rel = manifest.get("workdir", ".")
    workdir = workspace if workdir_rel == "." else workspace / workdir_rel
    test_files = _resolve_test_files(step_dir, manifest)
    cmd = _expand_manifest_command(
        manifest.get("test_command", ""), step_dir, manifest, test_files
    )
    if not cmd.strip():
        raise JudgeError("empty test_command in final manifest")

    rest = _pytest_rest_args(cmd)
    if rest is not None:
        proc = _run_pytest_launcher(
            rest,
            cwd=workdir,
            product_paths=_product_paths(cmd, workspace, workdir),
        )
        ran = f"python3 -I {LAUNCHER_PATH} " + " ".join(rest)
    else:
        proc = _run_shell(cmd, workdir)
        ran = cmd

    result = _result_from_proc(
        proc,
        log_path=VERIFIER_DIR / "final_tests.log",
        test_command=ran,
        framework_label=str(manifest.get("framework_label", "")),
        extra={
            "final_step": manifest.get("step"),
            "test_files": [str(p) for p in test_files],
            "test_command_ran": ran,
        },
    )
    _apply_collection_gate(result, manifest)
    return result


def main() -> int:
    VERIFIER_DIR.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "reward": 0.0,
        "judge_error": None,
        "judge_mode": "final_tests",
        "final": None,
    }

    try:
        if not WORKSPACE.is_dir():
            raise JudgeError(f"workspace not found: {WORKSPACE}")
        if not TESTS_FINAL.is_dir():
            raise JudgeError(f"final tests directory not found: {TESTS_FINAL}")

        acceptance_script = _acceptance_script_path()
        if acceptance_script is not None:
            report["judge_mode"] = "run_acceptance"
            result = _run_acceptance(acceptance_script, WORKSPACE)
            report["final"] = result
            report["reward"] = 1.0 if result["status"] == "passed" else 0.0
        else:
            _, manifest = _load_final_manifest()
            runner = _load_runner_metadata()
            report["runner"] = runner
            report["install"] = _skip_install_build(runner)
            result = _run_final(TESTS_FINAL, manifest, WORKSPACE)
            report["final"] = result
            report["reward"] = 1.0 if result["status"] == "passed" else 0.0
    except JudgeError as exc:
        report["judge_error"] = str(exc)
        report["reward"] = 0.0
        print(f"JUDGE ERROR: {exc}", file=sys.stderr)

    (VERIFIER_DIR / "final_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (VERIFIER_DIR / "reward.json").write_text(
        json.dumps({"reward": report["reward"]}), encoding="utf-8"
    )
    (VERIFIER_DIR / "reward.txt").write_text(str(report["reward"]), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 1 if report["judge_error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
