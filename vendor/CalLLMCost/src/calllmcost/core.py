"""High-level API: one call from raw usage + pricing table to USD."""

from __future__ import annotations

from typing import Any, Mapping

from calllmcost.pricing import PricingTable, step_real_cost_usd
from calllmcost.usage import normalize_usage


def compute_step_cost_usd(
    *,
    provider: str,
    raw_usage: Mapping[str, Any],
    model_id: str,
    pricing: PricingTable,
) -> float:
    """Normalize ``raw_usage`` for ``provider`` and return USD for ``model_id``.

    This is the same pipeline used in MiniSWERouterBench's router-aware model
    (``normalize_usage`` + per-model rates from ``pricing``).
    """

    buckets = normalize_usage(provider, raw_usage)
    mp = pricing.get(model_id)
    return step_real_cost_usd(buckets, mp)
