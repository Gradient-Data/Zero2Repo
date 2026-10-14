"""Optional Python hooks for built-in AgentSpec env/setup customization.

Hooks are invoked only for trusted built-in specs shipped with cbrun. Custom
user specs loaded from local files use declarative fields only unless they
explicitly reference a hook (discouraged for external specs).
"""

from __future__ import annotations

import os
import re
from typing import Any

# Mirrors agents._CLAUDE_OAUTH_STRIP_KEYS
_CLAUDE_OAUTH_STRIP_KEYS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
)

_OPENCODE_PROVIDER_KEYS = {
    "amazon-bedrock": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"],
    "anthropic": ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"],
    "azure": ["AZURE_RESOURCE_NAME", "AZURE_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "github-copilot": ["GITHUB_TOKEN"],
    "google": [
        "GEMINI_API_KEY",
        "GOOGLE_GENERATIVE_AI_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_API_KEY",
    ],
    "groq": ["GROQ_API_KEY"],
    "huggingface": ["HF_TOKEN"],
    "llama": ["LLAMA_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "openai": ["OPENAI_API_KEY", "OPENAI_BASE_URL"],
    "opencode": ["OPENCODE_API_KEY"],
    "xai": ["XAI_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
}


def claude_code_env(*, model: str, environ: dict[str, str], spec: Any) -> dict[str, str]:
    """OAuth unless ANTHROPIC_API_KEY is explicitly set."""
    del model, spec
    out: dict[str, str] = {}
    use_api_key = bool((environ.get("ANTHROPIC_API_KEY", "") or "").strip())
    if use_api_key:
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"):
            if environ.get(key):
                out[key] = environ[key]
    else:
        token = (environ.get("CLAUDE_CODE_OAUTH_TOKEN", "") or "").strip()
        if token:
            out["CLAUDE_CODE_OAUTH_TOKEN"] = token
        for key in _CLAUDE_OAUTH_STRIP_KEYS:
            out.pop(key, None)
    # Claude Code caps each reply at 32000 output tokens unless this is raised;
    # a reply that hits the cap ends the session before it can submit.
    output_max = (environ.get("CLAUDE_CODE_MAX_OUTPUT_TOKENS") or "").strip()
    if output_max:
        if not output_max.isdigit() or int(output_max) <= 0:
            raise RuntimeError(
                "cbrun: CLAUDE_CODE_MAX_OUTPUT_TOKENS must be a positive integer, "
                f"got {output_max!r}"
            )
        out["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = output_max
    return out


def opencode_env(*, model: str, environ: dict[str, str], spec: Any) -> dict[str, str]:
    del spec
    out: dict[str, str] = {}
    provider = model.split("/", 1)[0] if "/" in model else ""
    for key in _OPENCODE_PROVIDER_KEYS.get(provider, []):
        if environ.get(key):
            out[key] = environ[key]
    # A custom provider (e.g. an OpenAI-compatible gateway) is declared in
    # OPENCODE_CONFIG_CONTENT; pass it and the {env:NAME} keys it references.
    config = (environ.get("OPENCODE_CONFIG_CONTENT") or "").strip()
    if config:
        out["OPENCODE_CONFIG_CONTENT"] = config
        for key in re.findall(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}", config):
            if not environ.get(key):
                raise RuntimeError(f"cbrun: OPENCODE_CONFIG_CONTENT references unset {key}")
            out[key] = environ[key]
    # OpenCode caps each reply at 32000 output tokens unless this is raised;
    # the per-model limit.output in the config still applies on top of it.
    output_max = (environ.get("OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX") or "").strip()
    if output_max:
        if not output_max.isdigit() or int(output_max) <= 0:
            raise RuntimeError(
                "cbrun: OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX must be a positive integer, "
                f"got {output_max!r}"
            )
        out["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] = output_max
    out["OPENCODE_FAKE_VCS"] = "git"
    return out
