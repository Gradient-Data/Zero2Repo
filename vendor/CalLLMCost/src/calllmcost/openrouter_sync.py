"""Fetch live per-model prices from OpenRouter's public models API.

OpenRouter publishes USD **per token** strings under each model's ``pricing``
object (``prompt``, ``completion``, ``input_cache_read``, ``input_cache_write``).
This module converts them to the four **per 1M tokens** rates used by
:class:`~calllmcost.pricing.ModelPricing`, matching the snapshot workflow in
``SWERouterBench/data/model_pricing.json``.

When ``input_cache_write`` is absent (common for some providers), ``cache_write_per_m``
is set equal to ``input_per_m``, consistent with the benchmark's pricing file
governance (no silent zero for billed cache-write tokens).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from calllmcost.pricing import ModelPricing, PricingTable, make_pricing_table

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _usd_per_million_from_token_price(value: object) -> float:
    """OpenRouter returns USD per token; we store USD per 1M tokens."""

    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        raise TypeError("token price must not be a boolean")
    if isinstance(value, (int, float)):
        per_tok = Decimal(str(value))
    elif isinstance(value, str):
        per_tok = Decimal(value)
    else:
        raise TypeError(f"token price must be str or number, got {type(value).__name__}")
    if per_tok < 0:
        raise ValueError(f"negative per-token price: {value!r}")
    return float(per_tok * Decimal(1_000_000))


def model_pricing_from_openrouter_record(
    model_id: str, record: Mapping[str, Any]
) -> ModelPricing:
    """Map one OpenRouter ``/models`` list entry to :class:`ModelPricing`."""

    pricing = record.get("pricing")
    if not isinstance(pricing, Mapping):
        raise ValueError(f"OpenRouter model {model_id!r}: missing or invalid pricing object")

    prompt = pricing.get("prompt")
    completion = pricing.get("completion")
    if prompt in (None, "") or completion in (None, ""):
        raise ValueError(
            f"OpenRouter model {model_id!r}: pricing.prompt and pricing.completion are required"
        )

    input_per_m = _usd_per_million_from_token_price(prompt)
    output_per_m = _usd_per_million_from_token_price(completion)

    cache_read_raw = pricing.get("input_cache_read")
    cache_read_per_m = (
        _usd_per_million_from_token_price(cache_read_raw)
        if cache_read_raw not in (None, "")
        else 0.0
    )

    cache_write_raw = pricing.get("input_cache_write")
    if cache_write_raw in (None, ""):
        cache_write_per_m = input_per_m
    else:
        cache_write_per_m = _usd_per_million_from_token_price(cache_write_raw)

    source_url = f"https://openrouter.ai/{model_id}"
    return ModelPricing(
        model_id=model_id,
        input_per_m=input_per_m,
        output_per_m=output_per_m,
        cache_read_per_m=cache_read_per_m,
        cache_write_per_m=cache_write_per_m,
        source_url=source_url,
    )


def _models_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/models"
    if root.endswith("/api/v1"):
        return f"{root}/models"
    return f"{root}/models"


def fetch_openrouter_models_payload(
    *,
    base_url: str = DEFAULT_OPENROUTER_BASE_URL,
    api_key: str | None = None,
    timeout_sec: float = 120.0,
) -> dict[str, Any]:
    """GET ``/models`` and return the parsed JSON object."""

    url = _models_url(base_url)
    headers: dict[str, str] = {}
    key = (api_key or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read()
    except HTTPError as ex:
        raise RuntimeError(
            f"OpenRouter GET {url!r} failed with HTTP {ex.code}: {ex.reason}"
        ) from ex
    except URLError as ex:
        raise RuntimeError(f"OpenRouter GET {url!r} failed: {ex.reason!r}") from ex

    try:
        doc = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as ex:
        raise ValueError("OpenRouter /models response is not valid JSON") from ex
    if not isinstance(doc, dict):
        raise ValueError("OpenRouter /models root must be a JSON object")
    return doc


def fetch_pricing_table_from_openrouter(
    model_ids: Sequence[str],
    *,
    base_url: str = DEFAULT_OPENROUTER_BASE_URL,
    api_key: str | None = None,
    timeout_sec: float = 120.0,
    schema_version: int = 12,
    fetched_at: str | None = None,
) -> PricingTable:
    """Load current OpenRouter prices for the given ``model_id`` strings.

    One HTTP request fetches the full model list (OpenRouter does not expose a
    narrower endpoint in the public reference). Results are filtered to
    ``model_ids`` only.

    Parameters
    ----------
    model_ids
        OpenRouter model ids, e.g. ``anthropic/claude-opus-4.6``.
    api_key
        Optional bearer token. Listing models often works without a key; pass
        your OpenRouter key if you hit rate limits or HTTP 401/403.
    """

    wanted = [
        m.strip()
        for m in dict.fromkeys(model_ids)
        if isinstance(m, str) and m.strip()
    ]
    if not wanted:
        raise ValueError("model_ids must contain at least one non-empty model id string")
    doc = fetch_openrouter_models_payload(
        base_url=base_url, api_key=api_key, timeout_sec=timeout_sec
    )
    data = doc.get("data")
    if not isinstance(data, list):
        raise ValueError("OpenRouter /models response missing data array")

    by_id: dict[str, Mapping[str, Any]] = {}
    for row in data:
        if isinstance(row, dict):
            mid = row.get("id")
            if isinstance(mid, str) and mid:
                by_id[mid] = row

    entries: dict[str, ModelPricing] = {}
    missing: list[str] = []
    for mid in wanted:
        row = by_id.get(mid)
        if row is None:
            missing.append(mid)
            continue
        entries[mid] = model_pricing_from_openrouter_record(mid, row)

    if missing:
        raise KeyError(
            "OpenRouter /models response contained no pricing for: "
            + ", ".join(repr(m) for m in missing)
        )

    day = fetched_at if fetched_at is not None else date.today().isoformat()
    return make_pricing_table(
        schema_version=schema_version,
        fetched_at=day,
        entries=entries,
    )
