"""Official isolated-judge canaries. No agent is started.

Pass contract: hidden tests must be collected and executed; only then may
exit 0 count. Unproven collection is ``judge_error`` and reward stays 0.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import sys
from dataclasses import dataclass
from pathlib import Path

from .assets import load_case
from .docker_env import Container, _shq, docker_available, image_exists
from .images import deliverable_tag
from .isolation import synthesize_task_toml
from .judge import JudgeOutcome, run_isolated_judge
from .steps import discover_steps

CONTAINER_APP = "/app"


@dataclass(frozen=True)
class CanaryResult:
    name: str
    ok: bool
    reward: float
    judge_error: str | None
    total: int | None
    detail: str = ""


def _total(outcome: JudgeOutcome) -> int | None:
    final = outcome.report.get("final")
    if not isinstance(final, dict):
        return None
    raw = final.get("total_count")
    try:
        total = int(raw)
    except (TypeError, ValueError):
        return None
    return total if total > 0 else None


def _overlay_tree(container: Container, host_dir: Path) -> None:
    container.exec(f"rm -rf {CONTAINER_APP} && mkdir -p {CONTAINER_APP}")
    if not host_dir.is_dir():
        return
    for child in sorted(host_dir.iterdir()):
        container.cp_to(child, f"{CONTAINER_APP}/")


class _BuildFailed(RuntimeError):
    pass


def _build_app(container: Container, case_dir: Path, timeout_sec: float) -> None:
    """Leave build outputs in ``/app`` the way a solving agent must.

    The judge never builds and runs pytest as ``cbagent``, which cannot write
    ``/app``. A GT tree without outputs would only pass by building as root.
    """
    case = load_case(case_dir)
    command = (case.build_command or "").strip()
    if not command:
        return
    workdir = posixpath.normpath(f"{CONTAINER_APP}/{case.workdir or '.'}")
    res = container.exec(f"cd {_shq(workdir)} && {command}", timeout_sec=timeout_sec)
    if res.exit_code != 0:
        raise _BuildFailed(
            f"gt build failed (exit {res.exit_code}): {(res.tail or '').strip()[-400:]}"
        )


def _run(
    *,
    image: str,
    case_dir: Path,
    tests_final_dir: Path,
    artifacts_dir: Path,
    test_timeout_sec: float,
    prepare,
) -> JudgeOutcome:
    case = load_case(case_dir)
    step = discover_steps(case)[0]
    gpus = case.docker_gpus or None
    solve = Container.start(image, gpus=gpus, network="none")
    try:
        prepare(solve)
        return run_isolated_judge(
            solve,
            image=image,
            tests_final_dir=tests_final_dir,
            task_toml=synthesize_task_toml(case, step),
            test_timeout_sec=test_timeout_sec,
            artifacts_dir=artifacts_dir,
            workspace_export_dir=artifacts_dir / "judge_workspace",
            gpus=gpus,
        )
    finally:
        solve.remove()


def canary_gt_overlay(
    *,
    image: str,
    case_dir: Path,
    tests_final_dir: Path,
    gt_dir: Path,
    artifacts_dir: Path,
    test_timeout_sec: float,
) -> CanaryResult:
    if not gt_dir.is_dir():
        return CanaryResult("gt_overlay", False, 0.0, "gt missing", None, str(gt_dir))

    def prepare(container: Container) -> None:
        _overlay_tree(container, gt_dir)
        _build_app(container, case_dir, test_timeout_sec)

    try:
        outcome = _run(
            image=image,
            case_dir=case_dir,
            tests_final_dir=tests_final_dir,
            artifacts_dir=artifacts_dir / "gt_overlay",
            test_timeout_sec=test_timeout_sec,
            prepare=prepare,
        )
    except _BuildFailed as exc:
        return CanaryResult("gt_overlay", False, 0.0, str(exc), None, str(gt_dir))
    total = _total(outcome)
    ok = (
        outcome.judge_error is None
        and outcome.reward == 1.0
        and total is not None
    )
    return CanaryResult(
        name="gt_overlay",
        ok=ok,
        reward=outcome.reward,
        judge_error=outcome.judge_error,
        total=total,
        detail="need reward=1 and parseable total>0",
    )


def canary_workspace(
    *,
    image: str,
    case_dir: Path,
    tests_final_dir: Path,
    workspace_dir: Path,
    artifacts_dir: Path,
    test_timeout_sec: float,
) -> CanaryResult:
    """Judge a delivered ``/app`` exactly as a trial judge would: no build step."""
    if not workspace_dir.is_dir():
        return CanaryResult("workspace", False, 0.0, "workspace missing", None, str(workspace_dir))

    def prepare(container: Container) -> None:
        _overlay_tree(container, workspace_dir)

    outcome = _run(
        image=image,
        case_dir=case_dir,
        tests_final_dir=tests_final_dir,
        artifacts_dir=artifacts_dir / "workspace",
        test_timeout_sec=test_timeout_sec,
        prepare=prepare,
    )
    return CanaryResult(
        name="workspace",
        ok=outcome.judge_error is None and _total(outcome) is not None,
        reward=outcome.reward,
        judge_error=outcome.judge_error,
        total=_total(outcome),
        detail="a judged workspace needs a parseable total",
    )


def canary_empty_app(
    *,
    image: str,
    case_dir: Path,
    tests_final_dir: Path,
    artifacts_dir: Path,
    test_timeout_sec: float,
) -> CanaryResult:
    def prepare(container: Container) -> None:
        container.exec(f"rm -rf {CONTAINER_APP} && mkdir -p {CONTAINER_APP}")

    outcome = _run(
        image=image,
        case_dir=case_dir,
        tests_final_dir=tests_final_dir,
        artifacts_dir=artifacts_dir / "empty_app",
        test_timeout_sec=test_timeout_sec,
        prepare=prepare,
    )
    ok = outcome.reward != 1.0
    return CanaryResult(
        name="empty_app",
        ok=ok,
        reward=outcome.reward,
        judge_error=outcome.judge_error,
        total=_total(outcome),
        detail="empty /app must not score 1",
    )


def canary_shadow_pytest(
    *,
    image: str,
    case_dir: Path,
    tests_final_dir: Path,
    artifacts_dir: Path,
    test_timeout_sec: float,
) -> CanaryResult:
    def prepare(container: Container) -> None:
        container.exec(f"rm -rf {CONTAINER_APP} && mkdir -p {CONTAINER_APP}")
        container.exec(
            "printf '%s\\n' 'import sys' 'print(\"FAKE_PYTEST_EXECUTED\")' "
            f"'sys.exit(0)' > {CONTAINER_APP}/pytest.py"
        )

    outcome = _run(
        image=image,
        case_dir=case_dir,
        tests_final_dir=tests_final_dir,
        artifacts_dir=artifacts_dir / "shadow_pytest",
        test_timeout_sec=test_timeout_sec,
        prepare=prepare,
    )
    ok = outcome.reward != 1.0 and bool(outcome.judge_error)
    return CanaryResult(
        name="shadow_pytest",
        ok=ok,
        reward=outcome.reward,
        judge_error=outcome.judge_error,
        total=_total(outcome),
        detail="shadow /app/pytest.py must be judge_error and not score 1",
    )


def run_canaries(
    *,
    case_dir: Path,
    image: str,
    tests_final_dir: Path,
    gt_dir: Path,
    artifacts_dir: Path,
    test_timeout_sec: float = 900.0,
) -> list[CanaryResult]:
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return [
        canary_gt_overlay(
            image=image,
            case_dir=case_dir,
            tests_final_dir=tests_final_dir,
            gt_dir=gt_dir,
            artifacts_dir=artifacts_dir,
            test_timeout_sec=test_timeout_sec,
        ),
        canary_empty_app(
            image=image,
            case_dir=case_dir,
            tests_final_dir=tests_final_dir,
            artifacts_dir=artifacts_dir,
            test_timeout_sec=test_timeout_sec,
        ),
        canary_shadow_pytest(
            image=image,
            case_dir=case_dir,
            tests_final_dir=tests_final_dir,
            artifacts_dir=artifacts_dir,
            test_timeout_sec=test_timeout_sec,
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the three isolated-judge canaries (no agent)."
    )
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--gt-dir", type=Path, required=True)
    parser.add_argument("--image", default="")
    parser.add_argument("--tests-final-dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--test-timeout-sec", type=float, default=900.0)
    args = parser.parse_args(argv)

    if not docker_available():
        print("error: docker unavailable", file=sys.stderr)
        return 2

    case_dir = args.case_dir.resolve()
    image = args.image.strip() or deliverable_tag(case_dir.name)
    if not image_exists(image):
        print(f"error: image not found: {image}", file=sys.stderr)
        return 2

    tests_dir = args.tests_final_dir
    if tests_dir is None:
        tests_dir = case_dir / "milestones" / "final"
    tests_dir = tests_dir.resolve()
    if not (tests_dir / "test_manifest.json").is_file():
        print(f"error: hidden tests missing: {tests_dir}", file=sys.stderr)
        return 2

    results = run_canaries(
        case_dir=case_dir,
        image=image,
        tests_final_dir=tests_dir,
        gt_dir=args.gt_dir.resolve(),
        artifacts_dir=args.out,
        test_timeout_sec=args.test_timeout_sec,
    )
    payload = [
        {
            "name": item.name,
            "ok": item.ok,
            "reward": item.reward,
            "judge_error": item.judge_error,
            "total": item.total,
            "detail": item.detail,
        }
        for item in results
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "canaries.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    failed = 0
    for item in results:
        status = "OK" if item.ok else "FAIL"
        print(
            f"[canary] {status} {item.name} reward={item.reward} "
            f"total={item.total} error={item.judge_error}"
        )
        if not item.ok:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
