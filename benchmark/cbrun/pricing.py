"""Cost of a trial's token usage from the bundled list-price table.

``model_pricing.json`` holds per-1M-token prices for the evaluated models.
A model string such as ``gateway/claude-opus-5-5-20260921`` or
``grok-4.7-high`` is matched by its last path segment, with any date suffix
and reasoning-effort suffix removed, against each entry's aliases. The
unstripped leaf is also tried, so a model whose name itself ends in ``-max``
(``qwen3.8-max``) still matches.
An entry's ``currency`` is ``USD`` when omitted. Yuan prices stay in
``cost_cny`` and are not folded into ``cost_usd``.

``cache_write_1h_tokens`` is the part of ``cache_write_tokens`` written with a
one-hour TTL; it uses ``cache_write_1h_per_m`` when the model has one.
``uncached_input_is_cache_write`` marks models whose provider caches every
eligible prompt automatically and bills the write: when the log reports no
cache writes, uncached input is priced as cache writes.
``cache_read_5m_per_m`` records an explicit 5-minute cache-read rate. Trial
logs have one cache-read bucket, so those tokens use ``cache_read_per_m``.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

__all__ = ["PRICING_PATH", "lookup_model", "trial_cost"]

PRICING_PATH = Path(__file__).with_name("model_pricing.json")

_DATE_SUFFIX = re.compile(r"-\d{8}$")
_EFFORT_SUFFIX = re.compile(r"-(minimal|low|medium|high|xhigh|max)$")


@lru_cache(maxsize=1)
def _table() -> dict[str, Any]:
    return json.loads(PRICING_PATH.read_text(encoding="utf-8"))


def _candidates(model: str) -> list[str]:
    leaf = model.strip().lower().rsplit("/", 1)[-1]
    dated = _DATE_SUFFIX.sub("", leaf)
    stripped = _EFFORT_SUFFIX.sub("", dated)
    found: list[str] = []
    for item in (leaf, dated, stripped):
        if item and item not in found:
            found.append(item)
    return found


def lookup_model(model: str | None) -> tuple[str, dict[str, Any]] | None:
    if not model or not model.strip():
        return None
    candidates = _candidates(model)
    for model_id, entry in _table()["models"].items():
        names = {model_id.rsplit("/", 1)[-1], *entry.get("aliases", ())}
        if any(candidate in names for candidate in candidates):
            return model_id, entry
    return None


def _count(buckets: Mapping[str, Any], key: str) -> int:
    value = buckets.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _price(buckets: Mapping[str, Any], entry: Mapping[str, Any]) -> float:
    uncached = _count(buckets, "input_tokens")
    read = _count(buckets, "cache_read_tokens")
    write = _count(buckets, "cache_write_tokens")
    write_1h = min(_count(buckets, "cache_write_1h_tokens"), write)
    output = _count(buckets, "output_tokens")
    if entry.get("uncached_input_is_cache_write") and write == 0:
        uncached, write = 0, uncached
    write_rate = entry["cache_write_per_m"]
    return (
        uncached * entry["input_per_m"]
        + read * entry["cache_read_per_m"]
        + (write - write_1h) * write_rate
        + write_1h * entry.get("cache_write_1h_per_m", write_rate)
        + output * entry["output_per_m"]
    ) / 1_000_000


def trial_cost(usage: Mapping[str, Any], model: str | None) -> dict[str, Any]:
    """Return cost fields for one ``token_usage`` record.

    Per-model usage (``by_model``) is priced model by model; otherwise the
    totals are priced as ``model``. Both cost fields are None when any model
    with usage has no price. ``cost_usd`` sums USD entries and ``cost_cny``
    sums CNY entries.
    """
    by_model = usage.get("by_model")
    parts: list[tuple[str | None, Mapping[str, Any]]] = (
        list(by_model.items()) if isinstance(by_model, Mapping) and by_model else [(model, usage)]
    )
    usd = 0.0
    cny = 0.0
    saw_usd = False
    saw_cny = False
    priced: list[str] = []
    unpriced: list[str] = []
    for name, buckets in parts:
        found = lookup_model(name)
        if found is None:
            unpriced.append(str(name))
            continue
        model_id, entry = found
        amount = _price(buckets, entry)
        currency = str(entry.get("currency") or "USD").upper()
        if currency == "USD":
            usd += amount
            saw_usd = True
        elif currency == "CNY":
            cny += amount
            saw_cny = True
        else:
            unpriced.append(str(name))
            continue
        if model_id not in priced:
            priced.append(model_id)
    return {
        "cost_usd": None if unpriced or not saw_usd else round(usd, 6),
        "cost_cny": None if unpriced or not saw_cny else round(cny, 6),
        "priced_models": priced,
        "unpriced_models": unpriced,
        "pricing_fetched_at": _table()["fetched_at"],
    }
