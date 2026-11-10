# CalLLMCost

Small, dependency-free Python library to **normalize LLM `usage` payloads** from different providers into four canonical token buckets, then **compute USD cost** from a **pinned per-model price table** (USD per 1M tokens for input, cache read, cache write, and output).

The logic is extracted from an earlier routing benchmark and used in **MiniSWERouterBench**, where it was validated to track the provider’s own `usage.cost` within about **1%** on real traces when the JSON price snapshot matches the provider.

## Install

From this directory:

```bash
pip install -e .
```

Or copy the `src/calllmcost` package into your project (respect the Apache-2.0 license).

## Quick start

```python
from calllmcost import compute_step_cost_usd, load_pricing_table

pricing = load_pricing_table("model_pricing.json")

# After an OpenRouter / OpenAI-style chat completion:
raw_usage = response["usage"]  # dict
cost_usd = compute_step_cost_usd(
    provider="openai",  # or "openai_compat" for LiteLLM-style aliases
    raw_usage=raw_usage,
    model_id="anthropic/claude-opus-4.6",
    pricing=pricing,
)
```

Lower-level pieces:

- `normalize_usage(provider, raw_usage)` → `UsageBuckets`
- `pricing.get(model_id)` → `ModelPricing`
- `step_real_cost_usd(buckets, model_pricing)` → `float`

## Live prices from OpenRouter (startup refresh)

OpenRouter exposes current list prices on **`GET https://openrouter.ai/api/v1/models`**
(USD per **token** in string form). CalLLMCost maps that to the same four
**per 1M tokens** fields as the hand-maintained JSON. Typical usage at process
start:

```python
import os
from calllmcost import fetch_pricing_table_from_openrouter, dump_pricing_table

MODELS = [
    "anthropic/claude-opus-4.6",
    "google/gemini-3-flash-preview",
    "deepseek/deepseek-v3.2",
]

pricing = fetch_pricing_table_from_openrouter(
    MODELS,
    api_key=os.environ.get("OPENROUTER_API_KEY"),  # optional but recommended
)
# Optionally persist for debugging or offline replay:
# dump_pricing_table(pricing, "build/model_pricing.openrouter.json")
```

Notes:

- One HTTP call returns the full catalog; CalLLMCost keeps only the `model_ids` you pass.
- If OpenRouter omits `input_cache_write`, **cache_write_per_m** is set to **input_per_m** (same rule as the SWERouterBench snapshot).
- Listing often works **without** an API key; pass a key if you see **401/403** or rate limits.

## Pricing file

Load a JSON document with:

- Top-level: `schema_version`, `fetched_at`, `currency`, `unit`, `pricing`
- `pricing`: map of `model_id` → `{ input_per_m, output_per_m, cache_read_per_m, cache_write_per_m, source_url }`

All rates are **USD per 1 million tokens**. A reference file used in the benchmark lives at `SWERouterBench/data/model_pricing.json` in the CommonRouterBench monorepo.

## Supported `provider` values

`anthropic`, `openai`, `openai_compat`, `deepseek`, `gemini` — each maps vendor-specific usage fields into the same four buckets.

## Trace audit helper

If you log `step_cost_usd` and `raw_usage` per step (e.g. JSONL traces), you can compare your table-based sum to the aggregator’s `raw_usage.cost`:

```python
from pathlib import Path
from calllmcost import audit_trace_cost_metrics

print(audit_trace_cost_metrics(Path("./run_output")))
```

## License

Apache-2.0 — see `LICENSE`. Derived from SWERouterBench pricing/usage modules; copyright belongs to the respective contributors.

## Contributing

Issues and PRs welcome if you publish this as its own repository: bump `schema_version` support in `pricing.py` when extending the JSON schema, and add tests for new provider mappings in `usage.py`.
