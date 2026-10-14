"""Single-trial orchestration for cbrun.

A trial: derive/reuse the ``:agent`` image, start a GT-free container (GPU +
host network only as needed, never the Docker socket), inject the instruction,
let the agent develop freely under a wall-clock limit, require an explicit
submit file, then copy only ``/app`` into a fresh ``:agent`` container and
judge. Missing submit is a failed attempt and skips the hidden tests.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from coding_bench_harbor._leakage import scan_leakage

from .agent_spec import (
    CODEX_REASONING_EFFORT_ENV,
    CONTAINER_AGENT_LOG,
    CONTAINER_INSTRUCTION_PATH,
    CONTAINER_WORKDIR,
    AgentInvocation,
    resolve_agent,
)
from .access_monitor import AccessMonitor, AccessMonitorError
from .assets import AdapterError, CaseSpec, load_case
from .denylist import (
    DEFAULT_FIX_RETRIES,
    CODE_HOST_BLOCK_HOSTS,
    ScanResult,
    build_access_fix_instruction,
    build_fix_instruction,
    load_denylist,
    require_denylist,
    scan_installed_warnings,
    scan_workspace_imports,
)
from .docker_env import Container, ExecResult
from .images import AgentImage, ensure_agent_image
from .infra_signals import count_infra_signals, invalid_reason
from .state import (
    file_manifest,
    host_arch,
    image_identity,
    is_emulated,
    normalize_arch,
    platform_name,
    source_identity,
    utc_now,
)
from .instruction import build_instruction
from .isolation import merge_runner, synthesize_task_toml, test_command_env
from .judge import JudgeOutcome, run_isolated_judge
from .limits import (
    Limits,
    TerminalStatus,
    case_test_timeout_sec,
    classify_terminal,
    resolve_limits,
)
from .results import TrialResult
from .steps import Step, discover_steps
from .submit import CONTAINER_SUBMIT_PATH, NO_SUBMIT_ERROR, is_valid_submit
from .pricing import trial_cost
from .usage import AGENT_LOG_NAMES, USAGE_ARCHIVE_DIR, collect_trial_usage
from .transcript_scan import scan_trial as scan_transcript
from .transcript_scan import summarize as summarize_transcript_scan
from .transcript_scan import write_report as write_transcript_report

__all__ = ["run_trial"]


_CLI_BIN = {
    "codex": "codex",
    "opencode": "opencode",
    "claude-code": "claude",
    "cursor": "cursor-agent",
    "openhands": "openhands",
}


def _probe_cli_version(container: Container, spec_name: str) -> str | None:
    bin_name = _CLI_BIN.get(spec_name)
    if not bin_name:
        return None
    probe = container.exec(
        f"command -v {bin_name} >/dev/null && {bin_name} --version",
        timeout_sec=30.0,
    )
    if probe.exit_code != 0:
        path_probe = container.exec("printf '%s' \"$PATH\"", timeout_sec=10.0)
        path_text = (path_probe.tail or "").strip()
        detail = (probe.tail or "").strip()
        extra = f": {detail}" if detail else ""
        raise RuntimeError(
            f"cbrun: {bin_name} not found in login-shell PATH={path_text!r}{extra}"
        )
    return (probe.tail or "").strip() or None


def require_native_or_allowed(
    *,
    allow_emulated: bool,
    test_manifest: dict | None,
    emulated: bool | None = None,
    target_platform: str | None = None,
) -> None:
    """Refuse silent emulation and a judge budget measured on another arch."""
    platform = target_platform or platform_name()
    target_arch = platform.rsplit("/", 1)[-1]
    if (is_emulated(platform) if emulated is None else emulated) and not allow_emulated:
        raise RuntimeError(
            f"cbrun: container platform {platform} differs from host arch "
            f"{host_arch()}; pass --allow-emulated (emulated results are not "
            "comparable to native runs)."
        )
    measured = (test_manifest or {}).get("suite_wall_measured_on")
    if not isinstance(measured, dict):
        return
    raw = str(measured.get("arch") or "").strip()
    if not raw:
        return
    measured_arch = normalize_arch(raw)
    if measured_arch != target_arch:
        raise RuntimeError(
            f"cbrun: suite wall was measured on {measured_arch} but the "
            f"container platform is {platform}."
        )


def _check_public_leakage(case: CaseSpec, *, allow_leakage: bool) -> None:
    """Fail fast when public PRD/Contract/build_command contain sensitive terms."""
    full_text = f"{case.prd_text}\n{case.contract_text}\n{case.build_command}"
    hits = scan_leakage(full_text, case.sensitive_terms)
    if not hits or allow_leakage:
        return
    summary = ", ".join(f"{hit.term} (x{hit.occurrences})" for hit in hits)
    raise AdapterError(
        f"Case '{case.case_id}' leaks source-identity terms: {summary}. "
        "Sanitize public/ documents or pass --allow-leakage to override."
    )


def run_trial(
    case_dir: Path | str,
    *,
    backend: str | None = None,
    agent_spec_path: Path | str | None = None,
    model: str,
    out_dir: Path,
    cache_root: Path,
    limits: Limits | None = None,
    timeout_multiplier: float = 1.0,
    force_image: bool = False,
    allow_leakage: bool = False,
    enforce_denylist: bool = True,
    denylist_fix_retries: int = DEFAULT_FIX_RETRIES,
    block_github: bool = True,
    allow_emulated: bool = False,
) -> TrialResult:
    """Run one (case, backend/spec, model) trial and return its result."""
    case_dir = Path(case_dir)
    case = load_case(case_dir)
    _check_public_leakage(case, allow_leakage=allow_leakage)
    steps = discover_steps(case)
    require_native_or_allowed(
        allow_emulated=allow_emulated,
        test_manifest=steps[0].test_manifest if steps else None,
    )
    limits = limits or resolve_limits(multiplier=timeout_multiplier)
    per_case = case_test_timeout_sec(steps[0].test_manifest) if steps else None
    limits = limits.for_case(per_case)
    denylist = require_denylist(case_dir) if enforce_denylist else None

    out_dir = Path(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(exist_ok=False)

    image = ensure_agent_image(
        case.case_id,
        cache_root=Path(cache_root),
        case_dir=case_dir,
        force=force_image,
        backend=backend,
        enforce_denylist=enforce_denylist,
    )

    gpus = case.docker_gpus or None
    invocation = resolve_agent(
        backend=backend,
        agent_spec_path=agent_spec_path,
        model=model,
        instruction_path=CONTAINER_INSTRUCTION_PATH,
        log_path=CONTAINER_AGENT_LOG,
    )
    resolved_backend = invocation.spec.name

    result = TrialResult(
        case_id=case.case_id,
        backend=resolved_backend,
        model=model,
        reward=0.0,
        terminal_status=TerminalStatus.ERROR.value,
        deliverable_image=image.deliverable_image,
        agent_image=image.agent_image,
        agent_spec_name=invocation.spec.name,
        agent_spec_hash=invocation.spec_hash,
        resolved_model=invocation.resolved_model,
        run_as=invocation.run_as or "root",
        model_prefix=invocation.spec.model_prefix,
        env_keys=list(invocation.env_keys),
        denylist_enforced=enforce_denylist,
        started_at=utc_now(),
        platform=platform_name(),
        provenance=source_identity(case_dir),
        test_files=file_manifest(image.tests_cache_dir / "final"),
        reasoning_effort=(os.environ.get(CODEX_REASONING_EFFORT_ENV) or "").strip() or None,
        judge_timeout_sec=limits.max_test_timeout_sec,
        agent_timeout_sec=limits.max_agent_timeout_sec,
        host_arch=host_arch(),
        emulated=is_emulated(),
    )
    try:
        result.agent_image_id = image_identity(image.agent_image)["id"]
        result.deliverable_image_id = image_identity(image.deliverable_image)["id"]
    except (RuntimeError, OSError, ValueError):
        pass
    result.provenance["agent_image"] = result.agent_image_id
    result.provenance["deliverable_image"] = result.deliverable_image_id

    block_hosts = CODE_HOST_BLOCK_HOSTS if block_github else None
    result.blocked_hosts = list(block_hosts or ())
    container = Container.start(
        image.agent_image,
        gpus=gpus,
        network="host",
        block_hosts=block_hosts,
    )
    try:
        result.cli_version = _probe_cli_version(container, invocation.spec.name)
        passed_steps: list[int] = []
        for step in steps:
            step_outcome = _run_step(
                container,
                case=case,
                case_dir=case_dir,
                step=step,
                image=image,
                invocation=invocation,
                limits=limits,
                out_dir=out_dir,
                result=result,
                denylist=denylist,
                denylist_fix_retries=denylist_fix_retries,
            )
            if step_outcome:
                passed_steps.append(step.index)
            else:
                result.failed_step = step.index
                break
        result.passed_steps = passed_steps
    finally:
        _archive_trial(container, out_dir=out_dir, result=result, invocation=invocation)
        _record_token_usage(out_dir, result)
        _record_transcript_scan(out_dir, result, case_dir)
        result.finished_at = utc_now()

    return result


def _harvest_usage_files(container: Container, invocation: AgentInvocation) -> str | None:
    """Copy the CLI's session files into ``/logs/agent/usage`` before archiving."""
    paths = invocation.spec.usage_paths
    if not paths:
        return None
    dest = f"/logs/agent/{USAGE_ARCHIVE_DIR}"
    lines = [f"mkdir -p {dest}"]
    for index, raw in enumerate(paths):
        lines.append(
            f'src="{raw}"; if [ -d "$src" ]; then mkdir -p {dest}/{index} && cp -a "$src"/. {dest}/{index}/; fi'
        )
    res = container.exec(
        "; ".join(lines),
        env=invocation.env,
        timeout_sec=120.0,
        user=invocation.run_as,
    )
    if res.exit_code != 0:
        return f"usage files: exit {res.exit_code}: {(res.tail or '').strip()[-200:]}"
    return None


def _record_token_usage(out_dir: Path, result: TrialResult) -> None:
    try:
        usage = collect_trial_usage(out_dir)
        usage.update(trial_cost(usage, result.resolved_model or result.model))
        result.token_usage = usage
    except Exception as exc:  # noqa: BLE001
        result.token_usage = {"complete": False, "error": f"{type(exc).__name__}: {exc}"}


def _record_transcript_scan(out_dir: Path, result: TrialResult, case_dir: Path) -> None:
    """Scan the archived transcript; flag the trial for review, never rescore it."""
    try:
        report = scan_transcript(out_dir, case_dir)
        path = write_transcript_report(out_dir, report)
        result.logs["transcript_scan"] = str(path)
        result.transcript_scan = summarize_transcript_scan(report, report_path=str(path))
        result.needs_review = bool(report.get("needs_review"))
    except Exception as exc:  # noqa: BLE001
        result.transcript_scan = {"verdict": "error", "error": f"{type(exc).__name__}: {exc}"}


def _archive_trial(
    container: Container,
    *,
    out_dir: Path,
    result: TrialResult,
    invocation: AgentInvocation | None = None,
) -> None:
    """Freeze the container, archive ``/app`` and ``/logs/agent``, then remove it.

    Every failure is recorded on ``result.artifact_errors``; nothing raises.
    """
    try:
        if invocation is not None and not container.paused:
            try:
                harvest_error = _harvest_usage_files(container, invocation)
            except Exception as exc:  # noqa: BLE001
                harvest_error = f"usage files: {type(exc).__name__}: {exc}"
            if harvest_error:
                result.artifact_errors.append(harvest_error)
        # ``docker exec`` is refused on a paused container, so probe the log
        # directory before pausing; ``docker cp`` still works afterwards.
        has_agent_logs = False if container.paused else container.path_exists("/logs/agent")
        if not container.paused:
            try:
                container.pause()
            except RuntimeError:
                pass
        workspace = out_dir / "workspace"
        if not container.cp_from(CONTAINER_WORKDIR, workspace):
            result.artifact_errors.append("could not archive /app")
        else:
            result.logs["workspace"] = str(workspace)
        if has_agent_logs or container.paused:
            logs_dir = out_dir / "container_logs"
            if container.cp_from("/logs/agent", logs_dir):
                result.logs["container_logs"] = str(logs_dir)
            elif has_agent_logs:
                result.artifact_errors.append("could not archive /logs/agent")
    except Exception as exc:  # noqa: BLE001
        result.artifact_errors.append(f"archive: {type(exc).__name__}: {exc}")
    finally:
        try:
            container.remove()
        except Exception as exc:  # noqa: BLE001
            result.artifact_errors.append(f"container cleanup: {exc}")


def _run_agent_setup(
    container: Container,
    invocation: AgentInvocation,
    *,
    out_dir: Path,
) -> ExecResult | None:
    container.exec(invocation.prepare_workspace, timeout_sec=60.0)

    if invocation.install_script:
        install = container.exec(
            invocation.install_script,
            workdir=CONTAINER_WORKDIR,
            env=invocation.env,
            timeout_sec=300.0,
            user=invocation.run_as,
        )
        if install.exit_code != 0:
            return install

    if not invocation.setup_script:
        container.exec("mkdir -p /logs/agent", timeout_sec=10.0)
        return None

    container.exec("mkdir -p /logs/agent", timeout_sec=10.0)
    setup = container.exec(
        invocation.setup_script,
        workdir=CONTAINER_WORKDIR,
        env=invocation.env,
        timeout_sec=invocation.setup_timeout_sec,
        user=invocation.run_as,
    )
    setup_log = out_dir / "agent_setup.log"
    setup_log.write_text(setup.tail or "", encoding="utf-8")
    return setup


def _list_installed_packages(container: Container) -> list[str]:
    packages: list[str] = []
    pip_res = container.exec("pip list --format=freeze 2>/dev/null || true", timeout_sec=60.0)
    for line in (pip_res.tail or "").splitlines():
        name = line.split("==", 1)[0].strip()
        if name:
            packages.append(name)
    conda_res = container.exec(
        "command -v conda >/dev/null 2>&1 && conda list --json || true",
        timeout_sec=120.0,
    )
    if conda_res.exit_code == 0 and (conda_res.tail or "").strip().startswith("["):
        try:
            entries = json.loads(conda_res.tail or "[]")
            for entry in entries:
                name = str(entry.get("name") or "").strip()
                if name:
                    packages.append(name)
        except json.JSONDecodeError:
            pass
    return packages


def _copy_workspace(container: Container, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    ok = container.cp_from(CONTAINER_WORKDIR, dest)
    if not ok:
        raise RuntimeError(f"failed to copy workspace from container {CONTAINER_WORKDIR}")
    workspace = dest / "app"
    return workspace if workspace.is_dir() else dest


def _scan_denylist(
    container: Container,
    *,
    case_dir: Path,
    spec,
    scratch: Path,
) -> ScanResult:
    workspace = _copy_workspace(container, scratch / "workspace")
    import_hits = scan_workspace_imports(workspace, spec)
    installed = _list_installed_packages(container)
    host_spec = load_denylist(case_dir)
    if host_spec is None:
        return ScanResult(import_hits=import_hits)
    warnings = scan_installed_warnings(installed, host_spec)
    return ScanResult(import_hits=import_hits, installed_warnings=warnings)


def _write_scan_report(out_dir: Path, scan: ScanResult, *, label: str) -> None:
    payload = {
        "label": label,
        "import_hits": [hit.__dict__ for hit in scan.import_hits],
        "installed_warnings": [hit.__dict__ for hit in scan.installed_warnings],
    }
    (out_dir / f"denylist_scan_{label}.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _run_solve(
    container: Container,
    invocation: AgentInvocation,
    *,
    limits: Limits,
    out_dir: Path,
    log_name: str,
    wall_timeout_sec: float | None = None,
    abort=None,
) -> ExecResult:
    log_path = out_dir / log_name
    return container.exec_solve(
        invocation.command,
        workdir=CONTAINER_WORKDIR,
        env=invocation.env,
        wall_timeout_sec=wall_timeout_sec or limits.max_agent_timeout_sec,
        stall_window_sec=limits.stall_window_sec,
        log_path=log_path,
        stall_marker=CONTAINER_AGENT_LOG,
        activity_path=CONTAINER_WORKDIR,
        user=invocation.run_as,
        abort=abort,
    )


def _round_log_name(index: int) -> str:
    return AGENT_LOG_NAMES[index] if index < len(AGENT_LOG_NAMES) else f"agent_fix_{index}.log"


def _run_round(
    container: Container,
    invocation: AgentInvocation,
    *,
    limits: Limits,
    out_dir: Path,
    round_index: int,
    wall_timeout_sec: float | None,
    monitored: bool,
) -> tuple[ExecResult, list[dict]]:
    """One solve round, under the access monitor when the case has a denylist.

    The monitor must be ready before the agent starts; a monitor that cannot
    start raises ``AccessMonitorError`` so no round ever runs unmonitored. An
    access or interference event stops the agent at once.
    """
    log_name = _round_log_name(round_index)
    if not monitored:
        solve = _run_solve(
            container, invocation, limits=limits, out_dir=out_dir,
            log_name=log_name, wall_timeout_sec=wall_timeout_sec,
        )
        return solve, []
    monitor = AccessMonitor(
        container.container_id,
        round_index=round_index,
        log_path=out_dir / f"access_monitor_{round_index}.jsonl",
    )
    monitor.start()
    try:
        solve = _run_solve(
            container, invocation, limits=limits, out_dir=out_dir,
            log_name=log_name, wall_timeout_sec=wall_timeout_sec, abort=monitor.violated,
        )
    finally:
        events = monitor.stop()
    if events:
        state = "stopped" if solve.aborted else "ended"
        print(
            f"[cbrun] access monitor: round {round_index} {state} with "
            f"{len(events)} event(s): {events[0].get('message')}",
            flush=True,
        )
    return solve, events


def _fail_denylist(result: TrialResult, message: str, solve_start: float) -> bool:
    print(f"[cbrun] denylist violation: {message}", flush=True)
    result.denylist_violation = message
    result.reward = 0.0
    result.terminal_status = TerminalStatus.ERROR.value
    result.error = message
    result.solve_seconds = round(time.monotonic() - solve_start, 2)
    return False


def _read_submit_text(container: Container) -> str | None:
    res = container.exec(f"test -f {CONTAINER_SUBMIT_PATH} && cat {CONTAINER_SUBMIT_PATH}")
    if res.exit_code != 0:
        return None
    return res.tail


def _clear_submit(container: Container) -> None:
    container.exec(f"rm -f {CONTAINER_SUBMIT_PATH}", timeout_sec=10.0)


def _record_submit_outcome(
    container: Container,
    result: TrialResult,
    *,
    solve: ExecResult,
    solve_start: float,
    out_dir: Path,
) -> bool:
    """Apply terminal status from this CLI + submit file. False means stop (no judge)."""
    submitted = is_valid_submit(_read_submit_text(container))
    result.terminal_status = classify_terminal(
        exit_code=solve.exit_code,
        timed_out=solve.timed_out,
        stall_killed=solve.stall_killed,
        submitted=submitted,
    ).value
    result.solve_seconds = round(time.monotonic() - solve_start, 2)
    if submitted:
        return True
    result.reward = 0.0
    result.error = NO_SUBMIT_ERROR
    _record_infra_signals(out_dir, result, submitted=False)
    return False


def _inject_instruction(
    container: Container,
    instruction: str,
    invocation: AgentInvocation,
) -> None:
    container.write_file(CONTAINER_INSTRUCTION_PATH, instruction.encode("utf-8"))
    if invocation.run_as:
        container.exec(
            f"chown {invocation.run_as} {CONTAINER_INSTRUCTION_PATH}",
            timeout_sec=10.0,
        )


def _run_step(
    container: Container,
    *,
    case: CaseSpec,
    case_dir: Path,
    step: Step,
    image: AgentImage,
    invocation: AgentInvocation,
    limits: Limits,
    out_dir: Path,
    result: TrialResult,
    denylist,
    denylist_fix_retries: int,
) -> bool:
    """Run the solve+judge for one step; return True iff its gate passed."""
    merged = merge_runner(case, step)
    base_instruction = build_instruction(
        has_hardware=bool((case.hardware_text or "").strip()),
        build_command=case.build_command,
        workdir=merged["workdir"],
        test_env=test_command_env(merged["test_command"]),
    )
    _inject_instruction(container, base_instruction, invocation)

    setup_outcome = _run_agent_setup(container, invocation, out_dir=out_dir)
    result.setup_ok = setup_outcome is None or setup_outcome.exit_code == 0
    setup_log = out_dir / "agent_setup.log"
    if setup_log.is_file():
        result.logs["agent_setup_log"] = str(setup_log)
    if setup_outcome is not None and setup_outcome.exit_code != 0:
        result.terminal_status = TerminalStatus.ERROR.value
        result.error = f"agent setup failed (exit {setup_outcome.exit_code})"
        result.logs["agent_log"] = str(out_dir / "agent.log")
        result.reward = 0.0
        return False

    monitored = denylist is not None and denylist.enabled
    solve_start = time.monotonic()
    round_index = 0
    access_offenses = 0
    import_retries_left = denylist_fix_retries
    wall: float | None = None
    while True:
        try:
            solve, access = _run_round(
                container,
                invocation,
                limits=limits,
                out_dir=out_dir,
                round_index=round_index,
                wall_timeout_sec=wall,
                monitored=monitored,
            )
        except AccessMonitorError as exc:
            message = f"access monitor failed to start before round {round_index}: {exc}"
            print(f"[cbrun] {message}", flush=True)
            result.error = message
            result.run_valid = False
            result.invalid_reason = f"access_monitor: {exc}"
            result.reward = 0.0
            result.terminal_status = TerminalStatus.ERROR.value
            return False
        log_name = _round_log_name(round_index)
        result.logs[log_name.removesuffix(".log") + "_log"] = str(out_dir / log_name)
        result.agent_exit_code = solve.exit_code
        round_index += 1
        remaining = limits.max_agent_timeout_sec - (time.monotonic() - solve_start)

        if access:
            result.access_events.extend(access)
            result.access_rounds_stopped += 1
            access_offenses += 1
            first = access[0].get("message") or access[0].get("kind")
            if access_offenses > denylist_fix_retries:
                return _fail_denylist(
                    result,
                    f"access monitor violation after {access_offenses - 1} warning(s): "
                    f"{first}; see access_events",
                    solve_start,
                )
            if remaining < 60:
                return _fail_denylist(
                    result,
                    "access monitor violation with no wall-clock budget left for another "
                    f"round: {first}; see access_events",
                    solve_start,
                )
            _inject_instruction(container, build_access_fix_instruction(base_instruction, access), invocation)
            _clear_submit(container)
            wall = remaining
            continue

        if not _record_submit_outcome(
            container, result, solve=solve, solve_start=solve_start, out_dir=out_dir
        ):
            return False
        if not monitored:
            break

        first_scan = import_retries_left == denylist_fix_retries
        scan = _scan_denylist(container, case_dir=case_dir, spec=denylist, scratch=out_dir / "denylist_scratch")
        _write_scan_report(out_dir, scan, label="initial" if first_scan else "rescan")
        result.denylist_warnings = [f"installed:{hit.package}" for hit in scan.installed_warnings]
        if not scan.has_hard_violation:
            break
        if import_retries_left <= 0:
            summary = "; ".join(f"{hit.token}@{hit.path}:{hit.line}" for hit in scan.import_hits[:5])
            result.logs["denylist_scan"] = str(out_dir / "denylist_scan_rescan.json")
            return _fail_denylist(
                result,
                f"upstream import/symbol still present after {denylist_fix_retries} fix attempt(s): {summary}",
                solve_start,
            )
        if remaining < 60:
            return _fail_denylist(
                result,
                "upstream import/symbol detected but insufficient wall-clock budget for fix retry",
                solve_start,
            )
        _inject_instruction(container, build_fix_instruction(base_instruction, scan.import_hits), invocation)
        _clear_submit(container)
        result.denylist_fix_attempts += 1
        import_retries_left -= 1
        wall = remaining

    task_toml = synthesize_task_toml(case, step)
    outcome = run_isolated_judge(
        container,
        image=image.agent_image,
        tests_final_dir=image.tests_cache_dir / "final",
        task_toml=task_toml,
        test_timeout_sec=limits.max_test_timeout_sec,
        artifacts_dir=out_dir,
        workspace_export_dir=out_dir / "judge_workspace",
        gpus=case.docker_gpus or None,
        denylist=denylist,
        judge_bans=case.judge_bans,
    )
    _apply_judge_outcome(result, outcome)
    result.judge_exit_code = outcome.exit_code
    result.judge_seconds = round(outcome.seconds, 2)
    result.logs["judge_report"] = str(out_dir / "final_report.json")
    result.logs["judge_log"] = str(out_dir / "judge.log")
    tests_log = out_dir / "final_tests.log"
    if tests_log.is_file():
        result.logs["final_tests_log"] = str(tests_log)
    final = outcome.report.get("final") if isinstance(outcome.report, dict) else None
    if isinstance(final, dict):
        total = final.get("total_count")
        if isinstance(total, int):
            result.test_count = total
        failed = final.get("failed_tests") or []
        if isinstance(failed, list):
            result.failed_tests = [str(item) for item in failed]
    _record_infra_signals(out_dir, result, submitted=True)

    return outcome.reward >= 1.0 and not outcome.judge_error


def _apply_judge_outcome(result: TrialResult, outcome: JudgeOutcome) -> None:
    """Copy judge fields. An incomplete judge is not a valid model score."""
    result.reward = outcome.reward
    result.judge_error = outcome.judge_error
    result.substrates_missing = list(outcome.substrates_missing)
    if outcome.substrates_missing:
        result.run_valid = False
        result.invalid_reason = outcome.judge_error
    elif not outcome.completed:
        result.run_valid = False
        result.invalid_reason = outcome.incomplete_reason


def _record_infra_signals(out_dir: Path, result: TrialResult, *, submitted: bool) -> None:
    logs = [out_dir / name for name in AGENT_LOG_NAMES if (out_dir / name).is_file()]
    result.infra_signals = count_infra_signals(*logs)
    text = "\n".join(log.read_text(encoding="utf-8", errors="replace") for log in logs)
    reason = invalid_reason(submitted=submitted, log_text=text)
    if reason:
        result.run_valid = False
        result.invalid_reason = reason
