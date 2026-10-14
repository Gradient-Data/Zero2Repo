#!/usr/bin/env python3
"""Extract harness usage and compute USD cost via CalLLMCost."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
VENDOR_CALLLMCOST = ROOT / "vendor" / "CalLLMCost" / "src"
DEFAULT_PRICING_PATH = Path(__file__).resolve().parent / "data" / "model_pricing.json"

DEFAULT_PRICING_MODELS = (
    "anthropic/claude-opus-4.6",
    "anthropic/claude-opus-4-8",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-haiku-4.5",
    "anthropic/claude-3.5-haiku",
)

# Harness / API slugs that share pricing with another catalog model_id.
PRICING_MODEL_ALIASES: dict[str, str] = {
    "anthropic/claude-opus-4-8": "anthropic/claude-opus-4.6",
}

# First path segment of a catalog pricing key. Any other prefix is a gateway
# alias and is removed before pricing lookup.
_PRICING_VENDORS = frozenset(
    {
        "anthropic",
        "bytedance-seed",
        "cohere",
        "deepseek",
        "gemini",
        "google",
        "meta-llama",
        "mistralai",
        "moonshot",
        "openai",
        "qwen",
        "stepfun",
        "tencent",
        "x-ai",
        "z-ai",
    }
)


def _ensure_calllmcost_importable() -> None:
    vendor = str(VENDOR_CALLLMCOST)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)


@dataclass
class AgentCostRecord:
    """Cost summary for one harness invocation."""

    cost_usd: float | None = None
    harness_cost_usd: float | None = None
    model_id: str | None = None
    provider: str | None = None
    usage_buckets: dict[str, int] = field(default_factory=dict)
    raw_usage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_meta(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.cost_usd is not None:
            out["cost_usd"] = round(self.cost_usd, 6)
        if self.harness_cost_usd is not None:
            out["harness_cost_usd"] = round(self.harness_cost_usd, 6)
        if self.model_id:
            out["cost_model_id"] = self.model_id
        if self.provider:
            out["cost_provider"] = self.provider
        if self.usage_buckets:
            out["usage_buckets"] = self.usage_buckets
        if self.error:
            out["cost_error"] = self.error
        return out


def normalize_pricing_model_id(model: str | None, backend: str = "") -> str:
    """Map harness model slug to OpenRouter-style pricing key."""
    if not model or not str(model).strip():
        return "anthropic/claude-sonnet-4.6"
    slug = str(model).strip()
    if "/" in slug:
        vendor, rest = slug.split("/", 1)
        if vendor in _PRICING_VENDORS:
            normalized = slug
            return PRICING_MODEL_ALIASES.get(normalized, normalized)
        slug = rest
    slug = slug.replace("claude-opus-4-6", "claude-opus-4.6")
    slug = slug.replace("claude-opus-4-8", "claude-opus-4.6")
    slug = slug.replace("claude-sonnet-4-6", "claude-sonnet-4.6")
    slug = slug.replace("claude-haiku-4-5-20251001", "claude-haiku-4.5")
    if slug.startswith("claude-"):
        normalized = f"anthropic/{slug}"
    elif backend == "opencode" and "/" not in slug:
        normalized = f"anthropic/{slug}"
    else:
        normalized = slug
    return PRICING_MODEL_ALIASES.get(normalized, normalized)


def load_default_pricing(*, refresh: bool = False) -> Any:
    """Load pricing table from cache file or OpenRouter (when API key set)."""
    _ensure_calllmcost_importable()
    from calllmcost import fetch_pricing_table_from_openrouter, load_pricing_table

    if DEFAULT_PRICING_PATH.is_file() and not refresh:
        try:
            return load_pricing_table(DEFAULT_PRICING_PATH)
        except Exception:
            pass

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if api_key:
        try:
            table = fetch_pricing_table_from_openrouter(
                list(DEFAULT_PRICING_MODELS),
                api_key=api_key,
            )
            DEFAULT_PRICING_PATH.parent.mkdir(parents=True, exist_ok=True)
            from calllmcost import dump_pricing_table

            dump_pricing_table(table, DEFAULT_PRICING_PATH)
            return table
        except Exception:
            pass

    if DEFAULT_PRICING_PATH.is_file():
        return load_pricing_table(DEFAULT_PRICING_PATH)

    raise FileNotFoundError(
        f"No pricing table at {DEFAULT_PRICING_PATH} and OpenRouter fetch failed. "
        "Set OPENROUTER_API_KEY or add tools/data/model_pricing.json."
    )


def _parse_claude_result_payload(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _anthropic_usage_from_claude_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage")
    if isinstance(usage, Mapping):
        return dict(usage)
    return {}


def _primary_model_from_claude_payload(payload: Mapping[str, Any], fallback: str | None) -> str:
    model_usage = payload.get("modelUsage")
    if isinstance(model_usage, Mapping) and model_usage:
        best_model = None
        best_cost = -1.0
        for name, info in model_usage.items():
            if not isinstance(info, Mapping):
                continue
            cost = info.get("costUSD")
            if isinstance(cost, (int, float)) and float(cost) >= best_cost:
                best_cost = float(cost)
                best_model = str(name)
        if best_model:
            return normalize_pricing_model_id(best_model)
    return normalize_pricing_model_id(fallback)


def _aggregate_opencode_stdout(stdout: str) -> tuple[dict[str, Any], float | None]:
    """Aggregate OpenCode JSONL into one usage blob and optional harness cost sum."""
    harness_cost = 0.0
    saw_cost = False
    last_tokens: dict[str, Any] | None = None

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        if event.get("type") == "result" and isinstance(event.get("usage"), Mapping):
            usage = dict(event["usage"])
            total = event.get("total_cost_usd")
            if isinstance(total, (int, float)):
                return usage, float(total)
            return usage, None

        if event.get("type") != "step_finish":
            continue
        part = event.get("part")
        if not isinstance(part, Mapping):
            continue
        cost = part.get("cost")
        if isinstance(cost, (int, float)) and float(cost) > 0:
            harness_cost += float(cost)
            saw_cost = True
        tokens = part.get("tokens")
        if isinstance(tokens, Mapping):
            last_tokens = dict(tokens)

    if last_tokens is None:
        return {}, harness_cost if saw_cost else None

    cache = last_tokens.get("cache") if isinstance(last_tokens.get("cache"), Mapping) else {}
    cache_read = int(cache.get("read") or 0)
    cache_write = int(cache.get("write") or 0)
    input_tokens = int(last_tokens.get("input") or 0)
    output_tokens = int(last_tokens.get("output") or 0)
    billed_prefix = cache_read + cache_write
    if billed_prefix > input_tokens:
        billed_prefix = 0

    raw_usage = {
        "input_tokens": max(0, input_tokens - billed_prefix),
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_write,
        "output_tokens": output_tokens,
    }
    return raw_usage, harness_cost if saw_cost else None


def extract_agent_cost(
    stdout: str | None,
    *,
    backend: str,
    model: str | None = None,
    pricing: Any | None = None,
) -> AgentCostRecord:
    """Parse harness stdout and compute USD cost when usage is available."""
    text = stdout or ""
    record = AgentCostRecord(model_id=normalize_pricing_model_id(model, backend))

    if backend == "claude-code":
        payload = _parse_claude_result_payload(text)
        if payload is None:
            record.error = "no_claude_result_json"
            return record
        raw_usage = _anthropic_usage_from_claude_payload(payload)
        record.raw_usage = raw_usage
        record.provider = "anthropic"
        record.model_id = _primary_model_from_claude_payload(payload, model)
        harness_total = payload.get("total_cost_usd")
        if isinstance(harness_total, (int, float)):
            record.harness_cost_usd = float(harness_total)
    elif backend == "opencode":
        raw_usage, harness_total = _aggregate_opencode_stdout(text)
        record.raw_usage = raw_usage
        record.provider = "anthropic" if raw_usage else None
        record.model_id = normalize_pricing_model_id(model, backend)
        if harness_total is not None:
            record.harness_cost_usd = harness_total
        if not raw_usage:
            record.error = "no_opencode_usage"
            return record
    else:
        record.error = f"unsupported_backend:{backend}"
        return record

    if not record.raw_usage:
        record.error = record.error or "empty_usage"
        return record

    try:
        _ensure_calllmcost_importable()
        from calllmcost import compute_step_cost_usd, normalize_usage

        table = pricing if pricing is not None else load_default_pricing()
        provider = record.provider or "anthropic"
        buckets = normalize_usage(provider, record.raw_usage)
        record.usage_buckets = {
            "input_tokens": buckets.input_tokens,
            "cache_read_tokens": buckets.cache_read_tokens,
            "cache_write_tokens": buckets.cache_write_tokens,
            "output_tokens": buckets.output_tokens,
        }
        record.cost_usd = compute_step_cost_usd(
            provider=provider,
            raw_usage=record.raw_usage,
            model_id=record.model_id or normalize_pricing_model_id(model, backend),
            pricing=table,
        )
    except Exception as exc:
        record.error = str(exc)
        if record.harness_cost_usd is not None and record.cost_usd is None:
            record.cost_usd = record.harness_cost_usd

    if record.cost_usd is None and record.harness_cost_usd is not None:
        record.cost_usd = record.harness_cost_usd

    return record


def agent_cost_meta(
    stdout: str | None,
    backend: str,
    model: str | None = None,
    pricing: Any | None = None,
) -> dict[str, Any]:
    """Return run_meta-friendly cost fields for one agent invocation."""
    return extract_agent_cost(stdout, backend=backend, model=model, pricing=pricing).to_meta()


def build_agent_run_meta(
    proc: Any,
    *,
    backend: str,
    model: str | None,
    extra: dict[str, Any] | None = None,
    pricing: Any | None = None,
) -> dict[str, Any]:
    """Merge exit/status fields with cost metadata for run_meta.json."""
    from opencode_utils import _ensure_text

    meta: dict[str, Any] = dict(extra or {})
    rc = proc.returncode
    stderr = _ensure_text(getattr(proc, "stderr", None))
    timed_out = rc == -1 or "TIMEOUT after" in stderr
    if timed_out:
        status = "timeout"
    elif rc == 0:
        status = "success"
    elif rc is None:
        status = "unknown"
    else:
        status = "nonzero_exit"
    meta.setdefault("agent_exit_code", rc)
    meta.setdefault("agent_timed_out", timed_out)
    meta.setdefault("agent_status", status)
    tail = stderr.strip()
    if tail and "stderr_tail" not in meta:
        meta["stderr_tail"] = tail[-2000:]
    meta.update(agent_cost_meta(proc.stdout, backend, model, pricing=pricing))
    return meta


def _read_run_meta_cost(run_meta_path: Path) -> float:
    if not run_meta_path.is_file():
        return 0.0
    try:
        data = json.loads(run_meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0.0
    for key in ("cost_usd", "harness_cost_usd"):
        val = data.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    return 0.0


def aggregate_run_dirs(run_dirs: list[Path]) -> dict[str, Any]:
    """Sum cost from multiple agent_runs/*/run_meta.json files."""
    total = 0.0
    stages: list[dict[str, Any]] = []
    for run_dir in sorted(run_dirs):
        meta_path = run_dir / "run_meta.json"
        cost = _read_run_meta_cost(meta_path)
        if cost <= 0:
            continue
        stage = run_dir.name
        stages.append({"run_dir": str(run_dir), "stage": stage, "cost_usd": round(cost, 6)})
        total += cost
    return {
        "cost_usd": round(total, 6),
        "stage_count": len(stages),
        "stages": stages,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _milestone_step_run_prefixes(step_num: int) -> tuple[str, ...]:
    """Run-dir name prefixes that belong to one P3 milestone step."""
    n = step_num
    return (
        f"02_milestone_step_{n}",
        f"03_interface_contract_step_{n}",
        f"04_milestone_step_{n}",
    )


def aggregate_milestone_step_costs(case_dir: Path, step_num: int) -> dict[str, Any]:
    """Sum all P3 stage costs for one milestone step."""
    from case_layout import resolve_agent_runs_dir

    runs_root = resolve_agent_runs_dir(case_dir)
    if runs_root is None:
        return {"step": step_num, "cost_usd": 0.0, "stages": []}
    prefixes = _milestone_step_run_prefixes(step_num)
    run_dirs = [
        p for p in runs_root.iterdir()
        if p.is_dir() and any(
            p.name == pref or p.name.startswith(pref + "_") for pref in prefixes
        )
    ]
    summary = aggregate_run_dirs(run_dirs)
    summary["step"] = step_num
    return summary


def aggregate_case_pipeline_costs(case_dir: Path) -> dict[str, Any]:
    """Sum costs across all harness runs under a case (P2 + P3)."""
    from case_layout import resolve_agent_runs_dir

    runs_root = resolve_agent_runs_dir(case_dir)
    if runs_root is None:
        return {"case_id": case_dir.name, "cost_usd": 0.0, "stages": []}
    run_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
    summary = aggregate_run_dirs(run_dirs)
    summary["case_id"] = case_dir.name

    milestones: dict[str, Any] = {}
    for step_dir in sorted((case_dir / "milestones").glob("step_*")):
        try:
            step_num = int(step_dir.name.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        step_cost = aggregate_milestone_step_costs(case_dir, step_num)
        if step_cost.get("cost_usd", 0) > 0:
            milestones[f"step_{step_num}"] = step_cost
    if milestones:
        summary["milestones"] = milestones
    return summary


def enrich_harbor_agent_result(
    agent_result: Mapping[str, Any],
    *,
    model_name: str | None,
    backend: str,
    log_text: str | None = None,
    pricing: Any | None = None,
) -> dict[str, Any]:
    """Fill ``cost_usd`` on a Harbor ``agent_result`` object when missing."""
    out = dict(agent_result)
    if isinstance(out.get("cost_usd"), (int, float)):
        return out

    raw_usage: dict[str, Any] = {}
    n_in = out.get("n_input_tokens")
    n_cache = out.get("n_cache_tokens")
    n_out = out.get("n_output_tokens")
    if isinstance(n_in, int) and isinstance(n_out, int):
        cache = int(n_cache or 0)
        raw_usage = {
            "input_tokens": max(0, n_in - cache),
            "cache_read_input_tokens": cache,
            "cache_creation_input_tokens": 0,
            "output_tokens": n_out,
        }

    record = AgentCostRecord(model_id=normalize_pricing_model_id(model_name, backend))
    if log_text:
        record = extract_agent_cost(log_text, backend=backend, model=model_name, pricing=pricing)
    elif raw_usage:
        record.raw_usage = raw_usage
        record.provider = "anthropic"
        try:
            _ensure_calllmcost_importable()
            from calllmcost import compute_step_cost_usd

            table = pricing if pricing is not None else load_default_pricing()
            record.cost_usd = compute_step_cost_usd(
                provider="anthropic",
                raw_usage=raw_usage,
                model_id=record.model_id or normalize_pricing_model_id(model_name, backend),
                pricing=table,
            )
        except Exception as exc:
            record.error = str(exc)
    else:
        record.error = "no_usage_for_benchmark_trial"
        return out

    if record.cost_usd is not None:
        out["cost_usd"] = round(record.cost_usd, 6)
    meta = record.to_meta()
    if meta:
        out["cost_meta"] = meta
    return out


def enrich_trial_result_json(trial_dir: Path, *, backend: str = "opencode") -> dict[str, Any]:
    """Update ``result.json`` in a Harbor trial directory with computed agent cost."""
    result_path = trial_dir / "result.json"
    if not result_path.is_file():
        raise FileNotFoundError(result_path)

    data = json.loads(result_path.read_text(encoding="utf-8"))
    agent_result = data.get("agent_result") or {}
    config = data.get("config") or {}
    agent_cfg = config.get("agent") or {}
    model_name = agent_cfg.get("model_name") or (data.get("agent_info") or {}).get("model_info", {}).get("name")

    log_path = trial_dir / "agent" / "opencode.txt"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else None
    if backend == "claude-code":
        traj = trial_dir / "agent" / "trajectory.json"
        if traj.is_file() and not log_text:
            log_text = traj.read_text(encoding="utf-8", errors="replace")

    enriched = enrich_harbor_agent_result(
        agent_result,
        model_name=str(model_name) if model_name else None,
        backend=backend,
        log_text=log_text,
    )
    data["agent_result"] = enriched
    result_path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
    return enriched


def backfill_run_dir_cost(
    run_dir: Path,
    *,
    backend: str,
    default_model: str | None = None,
    pricing: Any | None = None,
) -> float:
    """Recompute cost from saved harness stdout and merge into run_meta.json."""
    meta_path = run_dir / "run_meta.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}

    stdout = ""
    for candidate in ("output.jsonl", "output_initial.jsonl"):
        path = run_dir / candidate
        if path.is_file():
            stdout = path.read_text(encoding="utf-8", errors="replace")
            break
    if not stdout:
        for path in sorted(run_dir.glob("output*.jsonl")):
            stdout = path.read_text(encoding="utf-8", errors="replace")
            if stdout.strip():
                break
    if not stdout.strip():
        return 0.0

    model = meta.get("model") or default_model
    if isinstance(model, str) and ":" in model:
        model = model.split(":", 1)[1]

    cost_meta = agent_cost_meta(stdout, backend, str(model) if model else None, pricing=pricing)
    meta.update(cost_meta)
    meta.setdefault("backend", backend)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return float(cost_meta.get("cost_usd") or 0.0)


def backfill_case_run_costs(
    case_dir: Path,
    *,
    backend: str = "opencode",
    pricing: Any | None = None,
) -> dict[str, Any]:
    """Backfill per-stage costs under ``agent_runs/`` for an existing case."""
    from case_layout import resolve_agent_runs_dir

    runs_root = resolve_agent_runs_dir(case_dir)
    if runs_root is None:
        return {"case_id": case_dir.name, "cost_usd": 0.0, "stages": []}

    total = 0.0
    stages: list[dict[str, Any]] = []
    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        cost = backfill_run_dir_cost(
            run_dir, backend=backend, pricing=pricing,
        )
        if cost <= 0:
            continue
        stages.append({"run_dir": str(run_dir), "stage": run_dir.name, "cost_usd": round(cost, 6)})
        total += cost

    summary = {
        "case_id": case_dir.name,
        "cost_usd": round(total, 6),
        "stage_count": len(stages),
        "stages": stages,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "backfilled": True,
    }
    milestones: dict[str, Any] = {}
    for step_dir in sorted((case_dir / "milestones").glob("step_*")):
        try:
            step_num = int(step_dir.name.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        step_cost = aggregate_milestone_step_costs(case_dir, step_num)
        if step_cost.get("cost_usd", 0) > 0:
            milestones[f"step_{step_num}"] = step_cost
            meta_path = step_dir / "run_meta.json"
            if meta_path.is_file():
                try:
                    step_meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    step_meta = {"step": step_num}
                step_meta["cost"] = step_cost
                meta_path.write_text(json.dumps(step_meta, indent=2) + "\n", encoding="utf-8")
    if milestones:
        summary["milestones"] = milestones
    return summary


def enrich_job_result_jsons(job_dir: Path, *, backend: str = "opencode") -> dict[str, Any]:
    """Enrich every trial ``result.json`` under a Harbor job directory."""
    trials: list[dict[str, Any]] = []
    total = 0.0
    for trial_dir in sorted(job_dir.iterdir()):
        if not trial_dir.is_dir():
            continue
        result_path = trial_dir / "result.json"
        if not result_path.is_file():
            continue
        enriched = enrich_trial_result_json(trial_dir, backend=backend)
        cost = enriched.get("cost_usd")
        if isinstance(cost, (int, float)):
            total += float(cost)
        trials.append({"trial": trial_dir.name, "cost_usd": cost})
    return {
        "job_dir": str(job_dir),
        "cost_usd": round(total, 6),
        "trial_count": len(trials),
        "trials": trials,
    }


def _cli_report_case(case_dir: Path) -> int:
    summary = aggregate_case_pipeline_costs(case_dir)
    print(json.dumps(summary, indent=2))
    cost = summary.get("cost_usd", 0)
    if isinstance(cost, (int, float)) and cost > 0:
        print(f"\nTotal pipeline cost for {case_dir.name}: ${cost:.4f}", file=sys.stderr)
    return 0


def _cli_enrich_trial(trial_dir: Path, backend: str) -> int:
    enriched = enrich_trial_result_json(trial_dir, backend=backend)
    print(json.dumps(enriched, indent=2))
    return 0


def _cli_enrich_job(job_dir: Path, backend: str) -> int:
    summary = enrich_job_result_jsons(job_dir, backend=backend)
    print(json.dumps(summary, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Report or enrich LLM harness costs (CalLLMCost)")
    sub = parser.add_subparsers(dest="command", required=True)

    case_p = sub.add_parser("case", help="Summarize pipeline costs for a CodingBench case")
    case_p.add_argument("--case-dir", type=Path, required=True)

    trial_p = sub.add_parser("trial", help="Fill cost_usd in a Harbor trial result.json")
    trial_p.add_argument("--trial-dir", type=Path, required=True)
    trial_p.add_argument(
        "--backend",
        choices=("opencode", "claude-code"),
        default="opencode",
    )

    job_p = sub.add_parser("job", help="Enrich all trials under a Harbor job directory")
    job_p.add_argument("--job-dir", type=Path, required=True)
    job_p.add_argument(
        "--backend",
        choices=("opencode", "claude-code"),
        default="opencode",
    )

    backfill_p = sub.add_parser("backfill", help="Recompute costs from saved harness stdout")
    backfill_p.add_argument("--case-dir", type=Path, required=True)
    backfill_p.add_argument(
        "--backend",
        choices=("opencode", "claude-code"),
        default="claude-code",
    )

    args = parser.parse_args(argv)
    if args.command == "case":
        return _cli_report_case(args.case_dir)
    if args.command == "trial":
        return _cli_enrich_trial(args.trial_dir, args.backend)
    if args.command == "job":
        return _cli_enrich_job(args.job_dir, args.backend)
    if args.command == "backfill":
        summary = backfill_case_run_costs(args.case_dir, backend=args.backend)
        print(json.dumps(summary, indent=2))
        cost = summary.get("cost_usd", 0)
        if isinstance(cost, (int, float)) and cost > 0:
            print(f"\nBackfilled case cost for {args.case_dir.name}: ${cost:.4f}", file=sys.stderr)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
