"""Rejudge a host workspace against a case image. No agent run.

Used by ``doc/rejudge.py`` and ``tools/run_controls.py``. Docker is only
required when actually scoring a workspace; reward comparison is pure.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .assets import load_case
from .denylist import require_denylist, scan_workspace_imports
from .docker_env import Container
from .images import ensure_agent_image
from .isolation import synthesize_task_toml
from .judge import import_app, run_judge
from .limits import DEFAULT_TEST_TIMEOUT_SEC, case_test_timeout_sec, resolve_limits
from .steps import discover_steps

__all__ = [
    "check_must_fail_tests",
    "parse_expect_reward",
    "reward_matches",
    "iter_controls",
    "static_scan_violation",
    "main",
]

DENYLIST_SCAN_REPORT = "denylist_scan.json"


def parse_expect_reward(value: str | int | float | None) -> float | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if text not in {"0", "1", "0.0", "1.0"}:
        raise ValueError(f"--expect-reward must be 0 or 1, got {value!r}")
    return float(int(float(text)))


def reward_matches(actual: float, expect: float | None) -> bool:
    if expect is None:
        return True
    return float(actual) == float(expect)


def _suffix_match(required: str, names: list[str]) -> bool:
    needle = required.strip()
    if not needle:
        return False
    for name in names:
        if name == needle or name.endswith(needle) or name.endswith("::" + needle):
            return True
    return False


def check_must_fail_tests(
    *,
    must_fail_tests: list[str] | None,
    failed_tests: list[str],
    error_tests: list[str],
    failed_count: int | None,
    error_count: int | None,
) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for an optional named-failure check.

    Hard errors only when ``must_fail_tests`` is non-empty. Collection-only
    failures stay warnings under the reward-only path.
    """
    errors: list[str] = []
    warnings: list[str] = []
    required = [str(item).strip() for item in (must_fail_tests or []) if str(item).strip()]
    if not required:
        if (error_count or 0) > 0 and not (failed_count or 0):
            warnings.append("control produced collection/errors only; reward-only check")
        return errors, warnings
    for item in required:
        if _suffix_match(item, failed_tests):
            continue
        if _suffix_match(item, error_tests):
            errors.append(f"must_fail_tests {item!r} hit ERROR, not FAILED")
        else:
            errors.append(f"must_fail_tests {item!r} not in failed_tests")
    return errors, warnings


def iter_controls(cases_root: Path | str):
    """Yield ``(case_id, control_name, control_dir, expect_reward)``."""
    root = Path(cases_root)
    if not root.is_dir():
        return
    for case_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        controls = case_dir / "controls"
        if not controls.is_dir():
            continue
        for control in sorted(p for p in controls.iterdir() if p.is_dir()):
            expect_path = control / "expect.json"
            expect = 0.0
            if expect_path.is_file():
                payload = json.loads(expect_path.read_text(encoding="utf-8"))
                expect = parse_expect_reward(payload.get("reward"))
                if expect is None:
                    expect = 0.0
            yield case_dir.name, control.name, control, expect


def _workspace_dir(control_or_app: Path) -> Path:
    app = control_or_app / "app"
    return app if app.is_dir() else control_or_app


def static_scan_violation(workspace: Path, denylist, out_dir: Path) -> str | None:
    """Run the same post-submit source scan a trial applies before judging.

    Writes ``denylist_scan.json`` next to the judge artifacts. Returns the
    violation summary when a banned import is present, else ``None``. A
    trial scores such a workspace 0 without judging; rejudge must not be
    more lenient than that.
    """
    if denylist is None:
        return None
    hits = scan_workspace_imports(workspace, denylist)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / DENYLIST_SCAN_REPORT).write_text(
        json.dumps({"import_hits": [hit.__dict__ for hit in hits]}, indent=2) + "\n",
        encoding="utf-8",
    )
    if not hits:
        return None
    summary = "; ".join(f"{hit.token}@{hit.path}:{hit.line}" for hit in hits[:5])
    return f"upstream import/symbol present in workspace: {summary}"


def rejudge_workspace(
    *,
    case_dir: Path,
    workspace: Path,
    out_dir: Path,
    cache_root: Path,
    test_timeout_sec: float = DEFAULT_TEST_TIMEOUT_SEC,
    force_image: bool = False,
    enforce_denylist: bool = True,
    image: str | None = None,
    tests_dir: Path | None = None,
    test_seed: str | None = None,
) -> float:
    case = load_case(case_dir)
    # Same import ban as a real trial; otherwise a control that delegates to
    # a banned module would be judged more leniently than an agent run.
    denylist = require_denylist(case_dir) if enforce_denylist else None
    if image is None:
        resolved = ensure_agent_image(
            case.case_id,
            case_dir=case_dir,
            cache_root=cache_root,
            force=force_image,
            enforce_denylist=enforce_denylist,
        )
        agent_image = resolved.agent_image
        tests_final_dir = resolved.tests_cache_dir / "final"
    else:
        agent_image = image
        tests_final_dir = Path(tests_dir)
    step = discover_steps(case)[0]
    limits = resolve_limits(test_timeout_sec=test_timeout_sec).for_case(
        case_test_timeout_sec(getattr(step, "test_manifest", None))
    )
    test_timeout_sec = limits.max_test_timeout_sec
    task_toml = synthesize_task_toml(case, step)
    out_dir.mkdir(parents=True, exist_ok=True)
    violation = static_scan_violation(_workspace_dir(workspace), denylist, out_dir)
    if violation is not None:
        (out_dir / "rejudge.json").write_text(
            json.dumps(
                {
                    "reward": 0.0,
                    "judge_error": None,
                    "denylist_violation": violation,
                    "failed_tests": [],
                    "error_tests": [],
                    "failed_count": None,
                    "error_count": None,
                    "total_count": None,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return 0.0
    from .substrates import SubstrateUnavailable, mounted_substrates

    manifest = getattr(step, "test_manifest", None) or {}
    try:
        with mounted_substrates(manifest, out_dir / "substrates") as mounts:
            container = Container.start(
                agent_image,
                network="none",
                mounts=[(str(item.host), item.container) for item in mounts],
            )
            try:
                import_app(container, _workspace_dir(workspace))
                outcome = run_judge(
                    container,
                    tests_final_dir=tests_final_dir,
                    task_toml=task_toml,
                    test_timeout_sec=test_timeout_sec,
                    artifacts_dir=out_dir,
                    denylist=denylist,
                    judge_bans=case.judge_bans,
                    test_seed=test_seed,
                )
            finally:
                container.remove()
    except SubstrateUnavailable as exc:
        raise RuntimeError(f"substrate {exc.name} unavailable") from exc
    report = getattr(outcome, "report", None)
    final = report.get("final") if isinstance(report, dict) else {}
    if not isinstance(final, dict):
        final = {}
    payload = {
        "reward": outcome.reward,
        "judge_error": outcome.judge_error,
        "completed": getattr(outcome, "completed", True),
        "incomplete_reason": getattr(outcome, "incomplete_reason", None),
        "failed_tests": list(final.get("failed_tests") or []),
        "error_tests": list(final.get("error_tests") or []),
        "failed_count": final.get("failed_count"),
        "error_count": final.get("error_count"),
        "total_count": final.get("total_count"),
    }
    (out_dir / "rejudge.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    if outcome.judge_error:
        raise RuntimeError(outcome.judge_error)
    return float(outcome.reward)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rejudge a workspace against hidden tests.")
    parser.add_argument("--case", required=True, help="Case id under --cases-root.")
    parser.add_argument("--workspace", type=Path, required=True, help="Host /app tree or control dir.")
    parser.add_argument("--cases-root", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=None)
    parser.add_argument("--expect-reward", default=None, help="Require reward 0 or 1.")
    parser.add_argument("--test-timeout-sec", type=float, default=DEFAULT_TEST_TIMEOUT_SEC)
    parser.add_argument("--force-image", action="store_true")
    parser.add_argument(
        "--enforce-denylist",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--image",
        default=None,
        help="Use this image instead of building an agent image from the deliverable.",
    )
    parser.add_argument(
        "--tests-dir",
        type=Path,
        default=None,
        help="Host milestones/final directory copied into the container as /tests/final.",
    )
    parser.add_argument(
        "--test-seed",
        default=None,
        help="Pin the hidden tests' runtime randomisation (CB_TEST_SEED), e.g. to replay an earlier judge.",
    )
    args = parser.parse_args(argv)

    expect = parse_expect_reward(args.expect_reward)
    repo = Path(__file__).resolve().parent.parent
    cases_root = args.cases_root or repo / "cases"
    cache_root = args.cache_root or repo / ".cbrun_cache"
    case_dir = cases_root / args.case
    if not (case_dir / "source" / "manifest.json").is_file():
        print(f"error: case not found: {case_dir}", flush=True)
        return 2
    if args.out.exists():
        print(f"error: output directory already exists: {args.out}", flush=True)
        return 2
    if (args.image is None) != (args.tests_dir is None):
        print("error: --image and --tests-dir must be given together", flush=True)
        return 2
    if args.tests_dir is not None and not (args.tests_dir / "test_manifest.json").is_file():
        print(f"error: tests dir missing test_manifest.json: {args.tests_dir}", flush=True)
        return 2
    try:
        reward = rejudge_workspace(
            case_dir=case_dir,
            workspace=args.workspace,
            out_dir=args.out,
            cache_root=cache_root,
            test_timeout_sec=args.test_timeout_sec,
            force_image=args.force_image,
            enforce_denylist=args.enforce_denylist,
            image=args.image,
            tests_dir=args.tests_dir,
            test_seed=args.test_seed,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", flush=True)
        return 2
    print(f"reward={reward}")
    if not reward_matches(reward, expect):
        print(f"error: expected reward {expect}, got {reward}", flush=True)
        return 1
    expect_path = _expect_path(args.workspace)
    must_fail: list[str] = []
    if expect_path is not None:
        try:
            expect_payload = json.loads(expect_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            expect_payload = {}
        raw = expect_payload.get("must_fail_tests") or []
        if isinstance(raw, list):
            must_fail = [str(item) for item in raw]
    report_path = args.out / "rejudge.json"
    report: dict = {}
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            report = {}
    violation = report.get("denylist_violation")
    if violation:
        print(f"denylist_violation: {violation}", flush=True)
    if violation and must_fail:
        # The judge never ran, so a named-failure expectation cannot be met.
        issues = ["must_fail_tests set but the static denylist scan preempted the judge"]
        warnings = []
    else:
        issues, warnings = check_must_fail_tests(
            must_fail_tests=must_fail,
            failed_tests=[str(x) for x in (report.get("failed_tests") or [])],
            error_tests=[str(x) for x in (report.get("error_tests") or [])],
            failed_count=report.get("failed_count"),
            error_count=report.get("error_count"),
        )
    if report_path.is_file():
        report["warnings"] = warnings
        report["must_fail_ok"] = not issues
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for item in warnings:
        print(f"warning: {item}", flush=True)
    if issues:
        for item in issues:
            print(f"error: {item}", flush=True)
        return 1
    return 0


def _expect_path(workspace: Path) -> Path | None:
    for candidate in (workspace / "expect.json", workspace.parent / "expect.json"):
        if candidate.is_file():
            return candidate
    return None


if __name__ == "__main__":
    raise SystemExit(main())
