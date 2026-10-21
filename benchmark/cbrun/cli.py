"""``cbrun`` command-line entry point.

Examples
--------
Run one case with one backend::

    cbrun --case <case_id> --backend codex --model openai/gpt-5.5

Run with a custom local AgentSpec::

    cbrun --case <case_id> --agent-spec ./my-agent.json --model my/model
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .agent_spec import BACKENDS, CODEX_REASONING_EFFORT_ENV, CODEX_REASONING_EFFORTS
from .agents import NPM_BACKENDS, cli_version_spec
from .assets import AdapterError
from .limits import DEFAULT_AGENT_TIMEOUT_SEC, DEFAULT_TEST_TIMEOUT_SEC, resolve_limits
from .results import TrialResult, format_reward_matrix, write_summary
from .run_case import run_trial

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _default_cases_root() -> Path:
    bench_cases = _REPO_ROOT / "benchmark" / "cases"
    if bench_cases.is_dir() and any(bench_cases.iterdir()):
        return bench_cases
    return _REPO_ROOT / "cases"


def _print_token_usage(usage: dict) -> None:
    if not usage:
        return
    line = (
        f"  tokens: input={usage.get('input_tokens', 0)} "
        f"cache_read={usage.get('cache_read_tokens', 0)} "
        f"cache_write={usage.get('cache_write_tokens', 0)} "
        f"output={usage.get('output_tokens', 0)}"
    )
    print(line, file=sys.stderr)
    if not usage.get("complete"):
        detail = usage.get("error") or f"no usage in {usage.get('missing') or 'agent logs'}"
        print(f"  WARNING: token usage incomplete: {detail}", file=sys.stderr)


def _build_images(args: argparse.Namespace, case_dirs: list[Path]) -> int:
    """Build each npm backend's shared CLI image once, then each case's images,
    up to ``--jobs`` at once.

    The CLI image is built first so ``--force-image`` rebuilds it once, not once
    per case. Recipe base images need no separate step: the first case to need
    one builds it under a host-wide lock while the others wait and then reuse it.
    """
    from concurrent.futures import ThreadPoolExecutor

    from .images import ensure_agent_image, ensure_cli_image
    from .recipe_image import ensure_deliverable_image

    backends = list(args.backend)
    try:
        for backend in backends:
            if backend in NPM_BACKENDS:
                tag = ensure_cli_image(backend, force=args.force_image)
                print(f"[cbrun] shared CLI image ready: {tag}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - no case can build its agent image without it
        print(f"error: shared CLI image: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    def build_case(case_dir: Path) -> list[str]:
        if not backends:
            return [ensure_deliverable_image(case_dir, force=args.force_image)]
        return [
            ensure_agent_image(
                case_dir.name,
                cache_root=args.cache_root,
                case_dir=case_dir,
                force=args.force_image,
                environ=os.environ,
                backend=backend,
                enforce_denylist=args.enforce_denylist,
            ).agent_image
            for backend in backends
        ]

    failed = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(build_case, case_dir): case_dir for case_dir in case_dirs}
        for future, case_dir in futures.items():
            try:
                for tag in future.result():
                    print(tag)
            except Exception as exc:  # noqa: BLE001 - keep the matrix going
                print(f"[cbrun] build-images {case_dir.name} FAILED: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
                failed += 1
    return 1 if failed else 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cbrun",
        description="Solver benchmark runner: develop from PRD+Contract, score with hidden tests.",
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case", action="append", default=[], help="Case id (repeatable).")
    selection.add_argument("--all", action="store_true", help="Run every case under --cases-root.")

    agent = parser.add_mutually_exclusive_group()
    agent.add_argument(
        "--backend",
        action="append",
        default=[],
        choices=BACKENDS,
        help="Built-in agent backend (repeatable). Default: codex.",
    )
    agent.add_argument(
        "--agent-spec",
        type=Path,
        help="Path to a local AgentSpec file (.json or .yaml). Mutually exclusive with --backend.",
    )
    parser.add_argument("--model", help="Model id (e.g. openai/gpt-5.5). Required unless --build-images.")
    parser.add_argument(
        "--build-images",
        action="store_true",
        help="Build images, then exit. Without --backend: each case's :deliverable. "
        "With --backend: the shared CLI image first, then each case's "
        ":deliverable and :agent-<backend>.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="With --build-images, build this many cases' images at once (default: 1). "
        "Shared images are built once: the CLI image before any case, a recipe "
        "base image by the first case that needs it while the others wait.",
    )
    parser.add_argument("--cases-root", type=Path, default=_default_cases_root())
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="New output directory. Defaults to a unique timestamped directory.",
    )
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / ".cbrun_cache",
        help="Host cache for :agent images' extracted hidden tests.",
    )
    parser.add_argument("--agent-timeout-sec", type=float, default=DEFAULT_AGENT_TIMEOUT_SEC)
    parser.add_argument("--test-timeout-sec", type=float, default=DEFAULT_TEST_TIMEOUT_SEC)
    parser.add_argument("--timeout-multiplier", type=float, default=1.0)
    parser.add_argument(
        "--allow-emulated",
        action="store_true",
        help="Allow a container platform that differs from the host arch. "
        "Emulated trials are excluded from reward_mean_valid.",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=sorted(CODEX_REASONING_EFFORTS),
        default=None,
        help="Write CBRUN_CODEX_REASONING_EFFORT for the Codex backend.",
    )
    parser.add_argument(
        "--force-image",
        action="store_true",
        help="Rebuild :deliverable (from recipe) and :agent images.",
    )
    parser.add_argument(
        "--allow-leakage",
        action="store_true",
        help="Skip public PRD/Contract sensitive-term leakage gate.",
    )
    parser.add_argument(
        "--enforce-denylist",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable upstream denylist scan (default: on).",
    )
    parser.add_argument(
        "--denylist-fix-retries",
        type=int,
        default=1,
        help="Fix retries after denylist import/symbol hits (default: 1).",
    )
    parser.add_argument(
        "--block-github",
        "--block-code-hosts",
        dest="block_github",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Block GitHub, other code hosts and GitHub mirrors in the solve "
        "container via /etc/hosts (default: on). Package registries stay reachable.",
    )
    return parser.parse_args(argv)


def _iter_case_dirs(cases_root: Path, cases: list[str], run_all: bool) -> list[Path]:
    if not cases_root.is_dir():
        raise AdapterError(f"cases root not found: {cases_root}")
    if run_all:
        dirs = []
        for child in sorted(cases_root.iterdir()):
            if (child / "source" / "manifest.json").is_file():
                dirs.append(child)
        return dirs
    out = []
    for case_id in cases:
        case_dir = cases_root / case_id
        if not (case_dir / "source" / "manifest.json").is_file():
            raise AdapterError(f"case not found: {case_dir}")
        out.append(case_dir)
    return out


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.agent_spec is not None and args.backend:
        print("error: --agent-spec and --backend are mutually exclusive", file=sys.stderr)
        return 2

    backends: list[str | None]
    if args.agent_spec is not None:
        backends = [None]
    else:
        backends = args.backend or ["codex"]

    # Deliverable images contain no agent CLI, so the pin check applies to
    # trial runs and to building agent images.
    if not args.build_images or args.backend:
        for backend in backends:
            if backend is None:
                continue
            try:
                spec = cli_version_spec(backend)
            except RuntimeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            if spec in ("@latest", "latest"):
                print(
                    f"warning: {backend} CLI is unpinned ({spec}); set "
                    f"CBRUN_{backend.upper().replace('-', '_')}_VERSION for reproducible runs.",
                    file=sys.stderr,
                )

    try:
        case_dirs = _iter_case_dirs(args.cases_root, args.case, args.all)
    except AdapterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not case_dirs:
        print(f"error: no cases found under {args.cases_root}", file=sys.stderr)
        return 2

    if args.build_images:
        if args.jobs < 1:
            print("error: --jobs must be at least 1", file=sys.stderr)
            return 2
        return _build_images(args, case_dirs)

    if args.out is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.out = (
            Path(__file__).resolve().parent.parent
            / "output"
            / "cbrun"
            / f"{stamp}-{uuid.uuid4().hex[:8]}"
        )
    args.out = args.out.resolve()
    try:
        args.out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(
            f"error: output directory already exists; choose a new --out: {args.out}",
            file=sys.stderr,
        )
        return 2

    if not args.model:
        print("error: --model is required unless --build-images", file=sys.stderr)
        return 2

    limits = resolve_limits(
        agent_timeout_sec=args.agent_timeout_sec,
        test_timeout_sec=args.test_timeout_sec,
        multiplier=args.timeout_multiplier,
    )
    if args.reasoning_effort:
        os.environ[CODEX_REASONING_EFFORT_ENV] = args.reasoning_effort
    if "codex" in [b for b in backends if b] and not (
        os.environ.get(CODEX_REASONING_EFFORT_ENV) or ""
    ).strip():
        print(
            "warning: Codex effort unset; CLI default applies "
            "(observed low on 0.153.x). Set --reasoning-effort or "
            f"{CODEX_REASONING_EFFORT_ENV}.",
            file=sys.stderr,
        )
    from .state import is_emulated

    if is_emulated() and not args.allow_emulated:
        print(
            "error: container platform differs from host arch; "
            "pass --allow-emulated (emulated results are not comparable "
            "to native runs).",
            file=sys.stderr,
        )
        return 2
    if is_emulated():
        print(
            "warning: container platform differs from host arch; "
            "emulated trials are excluded from reward_mean_valid.",
            file=sys.stderr,
        )

    results: list[TrialResult] = []
    write_summary(results, args.out)
    for case_dir in case_dirs:
        trial_labels = backends if args.agent_spec is None else [Path(args.agent_spec).stem]
        for label, backend in zip(trial_labels, backends):
            trial_out = args.out / case_dir.name / str(label)
            backend_label = backend or f"spec:{args.agent_spec.name}"
            print(f"[cbrun] {case_dir.name} / {backend_label} / {args.model} ...", file=sys.stderr)
            try:
                result = run_trial(
                    case_dir,
                    backend=backend,
                    agent_spec_path=args.agent_spec,
                    model=args.model,
                    out_dir=trial_out,
                    cache_root=args.cache_root,
                    limits=limits,
                    force_image=args.force_image,
                    allow_leakage=args.allow_leakage,
                    enforce_denylist=args.enforce_denylist,
                    denylist_fix_retries=args.denylist_fix_retries,
                    block_github=args.block_github,
                    allow_emulated=args.allow_emulated,
                )
            except Exception as exc:  # noqa: BLE001 - record, never crash the matrix
                result = TrialResult(
                    case_id=case_dir.name,
                    backend=backend or Path(args.agent_spec).stem,
                    model=args.model,
                    reward=0.0,
                    terminal_status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
                print(f"  FAILED: {result.error}", file=sys.stderr)
            _print_token_usage(result.token_usage)
            if result.needs_review:
                counts = (result.transcript_scan or {}).get("counts") or {}
                print(
                    f"  NEEDS REVIEW: transcript scan flagged high={counts.get('high', 0)} "
                    f"medium={counts.get('medium', 0)}; see {result.logs.get('transcript_scan')}",
                    file=sys.stderr,
                )
            results.append(result)
            write_summary(results, args.out)

    summary_path = write_summary(results, args.out)
    print(format_reward_matrix(results))
    print(f"\nsummary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
