"""Agent backend command templates and provider env for cbrun.

Built-in backends are defined as :class:`~cbrun.agent_spec.AgentSpec` records.
This module keeps the historical function names used by tests and Harbor-adjacent
code; new code should prefer :func:`cbrun.agent_spec.resolve_agent`.
"""

from __future__ import annotations

import os
import shlex

from .agent_spec import (
    BACKENDS,
    AgentInvocation,
    builtin_spec,
    resolve_agent,
)

__all__ = [
    "BACKENDS",
    "AgentInvocation",
    "build_agent_command",
    "provider_env",
    "cli_version_spec",
    "cli_install_command",
    "resolve_invocation",
]

# CLI npm packages. Versions must be pinned for reproducible runs.
# CBRUN_ALLOW_UNPINNED_CLI=1 is a local-smoke escape hatch only.
_UNPINNED_OK = "CBRUN_ALLOW_UNPINNED_CLI"
_CLI_PACKAGES = {
    "codex": ("@openai/codex", "CBRUN_CODEX_VERSION"),
    "opencode": ("opencode-ai", "CBRUN_OPENCODE_VERSION"),
    "claude-code": ("@anthropic-ai/claude-code", "CBRUN_CLAUDE_VERSION"),
}
_CLI_BINS = {
    "codex": "codex",
    "opencode": "opencode",
    "claude-code": "claude",
    "cursor": "cursor-agent",
}
_CURSOR_INSTALL_URL = "https://cursor.com/install"
_CURSOR_VERSION_ENV = "CBRUN_CURSOR_VERSION"
OPENHANDS_VERSION = "1.16.0"
OPENHANDS_CLI_IMAGE = f"codingbench-agent/openhands:{OPENHANDS_VERSION}"


def cli_version_spec(backend: str, environ: dict[str, str] | None = None) -> str:
    """Return the version pin suffix used by the backend installer."""
    _require_backend(backend)
    environ = os.environ if environ is None else environ
    allow_unpinned = (environ.get(_UNPINNED_OK, "") or "").strip() == "1"
    if backend == "openhands":
        return OPENHANDS_VERSION
    if backend == "cursor":
        pinned = (environ.get(_CURSOR_VERSION_ENV, "") or "").strip()
        if pinned:
            return pinned
        if allow_unpinned:
            return "latest"
        raise RuntimeError(
            f"cbrun: {_CURSOR_VERSION_ENV} is unset; pin the CLI version. "
            f"Set {_CURSOR_VERSION_ENV}=<version> or {_UNPINNED_OK}=1 "
            "for local smoke tests."
        )
    _pkg, env_key = _CLI_PACKAGES[backend]
    pinned = (environ.get(env_key, "") or "").strip()
    if pinned:
        return f"@{pinned}"
    if allow_unpinned:
        return "@latest"
    raise RuntimeError(
        f"cbrun: {env_key} is unset; pin the CLI version. "
        f"Set {env_key}=<version> or {_UNPINNED_OK}=1 for local smoke tests."
    )


def _cursor_install_command(environ: dict[str, str] | None) -> str:
    environ = os.environ if environ is None else environ
    pinned = (environ.get(_CURSOR_VERSION_ENV, "") or "").strip()
    version_export = f"export CURSOR_VERSION={shlex.quote(pinned)}; " if pinned else ""
    return (
        "set -eu; "
        "if command -v cursor-agent >/dev/null 2>&1; then cursor-agent --version; exit 0; fi; "
        "if command -v agent >/dev/null 2>&1; then "
        "  ln -sfn \"$(command -v agent)\" /usr/local/bin/cursor-agent; "
        "  cursor-agent --version; exit 0; "
        "fi; "
        "command -v curl >/dev/null 2>&1 || { "
        "  if command -v apt-get >/dev/null 2>&1; then "
        "    apt-get update && apt-get install -y --no-install-recommends curl ca-certificates; "
        "  elif command -v apk >/dev/null 2>&1; then apk add --no-cache curl; "
        "  else echo 'cbrun: curl required to install Cursor CLI' >&2; exit 1; fi; "
        "}; "
        f"{version_export}"
        f"curl -fsSL {_CURSOR_INSTALL_URL} | bash; "
        "if [ -x \"$HOME/.local/bin/agent\" ]; then "
        "  ln -sfn \"$HOME/.local/bin/agent\" /usr/local/bin/agent; "
        "  ln -sfn \"$HOME/.local/bin/agent\" /usr/local/bin/cursor-agent; "
        "elif [ -x \"$HOME/.local/bin/cursor-agent\" ]; then "
        "  ln -sfn \"$HOME/.local/bin/cursor-agent\" /usr/local/bin/cursor-agent; "
        "  ln -sfn \"$HOME/.local/bin/cursor-agent\" /usr/local/bin/agent; "
        "fi; "
        "command -v cursor-agent >/dev/null 2>&1 || { "
        "echo 'cbrun: Cursor CLI install did not produce cursor-agent' >&2; exit 1; }; "
        "cursor-agent --version"
    )


# Private prefix used when the deliverable image has no Node. Must not land
# on the default PATH (Codex/Claude Bash inherits the CLI process env).
NODE_RUNTIME_PREFIX = "/opt/cbrun/runtime/node"


def cli_install_command(backend: str, environ: dict[str, str] | None = None) -> str:
    """Idempotent in-container install command for a backend's CLI."""
    _require_backend(backend)
    if backend == "openhands":
        return (
            "set -eu; "
            "command -v openhands >/dev/null 2>&1 || { "
            "echo 'cbrun: openhands is missing; build "
            f"{OPENHANDS_CLI_IMAGE} first' >&2; exit 1; }}; "
            "openhands --version"
        )
    if backend == "cursor":
        return _cursor_install_command(environ)
    pkg, _env_key = _CLI_PACKAGES[backend]
    spec = cli_version_spec(backend, environ)
    bin_name = _CLI_BINS[backend]
    verify = shlex.quote(f"command -v {bin_name} && {bin_name} --version")
    dest_bin = f"/usr/local/bin/{bin_name}"
    prefix = NODE_RUNTIME_PREFIX
    return (
        "set -eu; "
        f"if [ -x {dest_bin} ]; then bash -lc {verify}; exit 0; fi; "
        f'if [ -x {prefix}/bin/npm ]; then '
        f'  NPM={prefix}/bin/npm; NODE={prefix}/bin/node; NPM_PREFIX={prefix}; '
        "elif command -v npm >/dev/null 2>&1 && command -v node >/dev/null 2>&1; then "
        '  NPM="$(command -v npm)"; NODE="$(command -v node)"; '
        '  NPM_PREFIX="$("$NPM" prefix -g)"; '
        "else "
        "  echo 'cbrun: npm/node not found in agent image' >&2; exit 1; "
        "fi; "
        # npm's shebang is `#!/usr/bin/env node`. The private prefix is not
        # on PATH, so invoke the script with the absolute node binary.
        f'"$NODE" "$NPM" install -g --prefix "$NPM_PREFIX" {shlex.quote(pkg + spec)}; '
        f'CBRUN_CLI_PATH="$NPM_PREFIX/bin/{bin_name}"; '
        '[ -x "$CBRUN_CLI_PATH" ] || { '
        f'echo "cbrun: {pkg} installed but $CBRUN_CLI_PATH missing" >&2; '
        "exit 1; }; "
        'if [ -n "$NODE" ] && [ -x "$NODE" ]; then '
        '  tmp="$(mktemp)"; '
        '  if head -n 1 "$CBRUN_CLI_PATH" | grep -q "/usr/bin/env node"; then '
        '    { printf "#!%s\\n" "$NODE"; tail -n +2 "$CBRUN_CLI_PATH"; } > "$tmp"; '
        '    cat "$tmp" > "$CBRUN_CLI_PATH"; '
        '    chmod +x "$CBRUN_CLI_PATH"; '
        "  fi; "
        '  rm -f "$tmp"; '
        "fi; "
        "mkdir -p /usr/local/bin; "
        f'if [ "$CBRUN_CLI_PATH" != {dest_bin} ]; then '
        f'ln -sfn "$CBRUN_CLI_PATH" {dest_bin}; '
        "fi; "
        f"bash -lc {verify}"
    )


def resolve_invocation(
    backend: str,
    *,
    model: str,
    instruction_path: str,
    log_path: str,
    environ: dict[str, str] | None = None,
    model_prefix: str | None = None,
) -> AgentInvocation:
    """Resolve a built-in backend to a full :class:`AgentInvocation`."""
    spec = builtin_spec(backend)
    if model_prefix is not None:
        from dataclasses import replace

        if model_prefix not in ("keep", "strip"):
            raise ValueError("model_prefix must be 'keep' or 'strip'")
        spec = replace(spec, model_prefix=model_prefix)  # type: ignore[arg-type]
    return resolve_agent(
        spec=spec,
        model=model,
        instruction_path=instruction_path,
        log_path=log_path,
        environ=environ,
    )


def build_agent_command(
    backend: str,
    *,
    model: str,
    instruction_path: str,
    log_path: str,
    workdir: str = "/app",
    codex_profile: str = "",
    preserve_model_provider_prefix: bool = False,
) -> str:
    """Build the in-container shell command that runs one solve."""
    del workdir, codex_profile  # workdir is fixed /app; profiles are user-owned
    prefix = "keep" if preserve_model_provider_prefix else None
    inv = resolve_invocation(
        backend,
        model=model,
        instruction_path=instruction_path,
        log_path=log_path,
        model_prefix=prefix,
    )
    return inv.command


def provider_env(
    backend: str,
    model: str,
    environ: dict[str, str] | None = None,
) -> dict[str, str]:
    """Select auth/provider env vars to forward into the container."""
    inv = resolve_invocation(
        backend,
        model=model,
        instruction_path="/tmp/unused",
        log_path="/tmp/unused.log",
        environ=environ,
    )
    return inv.env


def _require_backend(backend: str) -> None:
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend {backend!r}; choose from {BACKENDS}")
