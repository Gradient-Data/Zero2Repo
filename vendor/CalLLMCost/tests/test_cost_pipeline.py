"""Regression tests for usage normalization + 4-bucket pricing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from calllmcost import (
    compute_step_cost_usd,
    load_pricing_table,
    normalize_usage,
    step_real_cost_usd,
)


MINIMAL_PRICING_DOC = {
    "schema_version": 12,
    "fetched_at": "2099-01-01",
    "currency": "USD",
    "unit": "per_1M_tokens",
    "pricing": {
        "openai/gpt-test": {
            "input_per_m": 1.0,
            "output_per_m": 2.0,
            "cache_read_per_m": 0.1,
            "cache_write_per_m": 1.5,
            "source_url": "https://example.invalid/openai/gpt-test",
        }
    },
}


@pytest.fixture
def pricing_path(tmp_path: Path) -> Path:
    p = tmp_path / "pricing.json"
    p.write_text(json.dumps(MINIMAL_PRICING_DOC), encoding="utf-8")
    return p


def test_openai_cache_buckets_and_cost(pricing_path: Path) -> None:
    table = load_pricing_table(pricing_path)
    raw = {
        "prompt_tokens": 1000,
        "completion_tokens": 50,
        "prompt_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 100},
    }
    buckets = normalize_usage("openai", raw)
    assert buckets.input_tokens == 700
    assert buckets.cache_read_tokens == 200
    assert buckets.cache_write_tokens == 100
    assert buckets.output_tokens == 50
    mp = table.get("openai/gpt-test")
    cost = step_real_cost_usd(buckets, mp)
    expected = (700 * 1.0 + 200 * 0.1 + 100 * 1.5 + 50 * 2.0) / 1_000_000.0
    assert cost == pytest.approx(expected)


def test_openai_litellm_alias_zero_prompt_completion(pricing_path: Path) -> None:
    table = load_pricing_table(pricing_path)
    raw = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "input_tokens": 10,
        "output_tokens": 3,
    }
    cost = compute_step_cost_usd(
        provider="openai_compat",
        raw_usage=raw,
        model_id="openai/gpt-test",
        pricing=table,
    )
    expected = (10 * 1.0 + 3 * 2.0) / 1_000_000.0
    assert cost == pytest.approx(expected)


def test_loads_swerouterbench_fixture_if_present() -> None:
    """Optional: run from monorepo checkout with SWERouterBench sibling data."""

    repo_root = Path(__file__).resolve().parents[2]
    bundled = repo_root.parent / "SWERouterBench" / "data" / "model_pricing.json"
    if not bundled.is_file():
        pytest.skip("SWERouterBench/data/model_pricing.json not in tree")
    table = load_pricing_table(bundled)
    assert "anthropic/claude-opus-4.6" in table
