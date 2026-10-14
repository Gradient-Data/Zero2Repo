"""Declarative agent specifications for cbrun.

Users bring their own credentials and may supply a local AgentSpec file
(``.json`` or ``.yaml`` when PyYAML is installed). Built-in backends
(``codex``, ``opencode``, ``claude-code``, ``cursor``, ``openhands``) are predefined specs.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .agent_hooks import claude_code_env, opencode_env
from .codex_config import (
    CODEX_GATEWAY_WEBSOCKETS_ENV,
    GATEWAY_MODEL_PROVIDER_LINE,
    GATEWAY_PROVIDER_TABLE,
)

__all__ = [
    "AGENT_USER",
    "AGENT_USER_HOME",
    "CONTAINER_WORKDIR",
    "AgentInvocation",
    "AgentSpec",
    "BACKENDS",
    "builtin_spec",
    "load_agent_spec",
    "resolve_agent",
]

BACKENDS = ("codex", "opencode", "claude-code", "cursor", "openhands")
CODEX_REASONING_EFFORT_ENV = "CBRUN_CODEX_REASONING_EFFORT"
CODEX_REASONING_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh"})

AGENT_USER = "cbagent"
AGENT_USER_HOME = "/home/cbagent"
# Claude Code stores its session/config under CLAUDE_CONFIG_DIR. Some
# published images pin this to a root-owned path (``/claude-home``)
# that a non-root solve agent cannot write, which
# breaks the Bash tool at init (it mkdir's ``$CLAUDE_CONFIG_DIR/session-env``).
# cbrun therefore repoints it into the agent's own writable HOME.
AGENT_CLAUDE_CONFIG_DIRNAME = ".claude"
CONTAINER_WORKDIR = "/app"
CONTAINER_INSTRUCTION_PATH = "/tmp/cbrun/instruction.md"
CONTAINER_AGENT_LOG = "/logs/agent/agent.txt"
CONTAINER_AGENT_SETUP_LOG = "/logs/agent/agent_setup.log"

RunAs = Literal["root", "nonroot"]
ModelPrefix = Literal["keep", "strip"]

_HOOKS: dict[str, Any] = {
    "cbrun.agent_hooks:claude_code_env": claude_code_env,
    "cbrun.agent_hooks:opencode_env": opencode_env,
}


@dataclass(frozen=True)
class AgentSpec:
    name: str
    command: str
    env_passthrough: tuple[str, ...] = ()
    setup_script: str | None = None
    install_script: str | None = None
    run_as: RunAs = "root"
    model_prefix: ModelPrefix = "keep"
    home: str | None = None
    setup_timeout_sec: float = 120.0
    python_hook: str | None = None
    runtime: str | None = None
    # Container directories where the CLI writes session files with token
    # usage. Shell-expanded in the solve env; archived after every trial so
    # usage survives a killed process.
    usage_paths: tuple[str, ...] = ()

    def spec_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "command": self.command,
            "env_passthrough": list(self.env_passthrough),
            "setup_script": self.setup_script,
            "install_script": self.install_script,
            "run_as": self.run_as,
            "model_prefix": self.model_prefix,
            "home": self.home,
            "setup_timeout_sec": self.setup_timeout_sec,
            "python_hook": self.python_hook,
            "runtime": self.runtime,
        }
        if self.usage_paths:
            out["usage_paths"] = list(self.usage_paths)
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentSpec:
        name = str(data.get("name") or "").strip()
        command = str(data.get("command") or "").strip()
        if not name:
            raise ValueError("AgentSpec requires 'name'")
        if not command:
            raise ValueError(f"AgentSpec {name!r} requires 'command'")
        run_as = str(data.get("run_as") or "root").strip()
        if run_as not in ("root", "nonroot"):
            raise ValueError(f"AgentSpec {name!r}: run_as must be 'root' or 'nonroot'")
        model_prefix = str(data.get("model_prefix") or "keep").strip()
        if model_prefix not in ("keep", "strip"):
            raise ValueError(f"AgentSpec {name!r}: model_prefix must be 'keep' or 'strip'")
        passthrough = data.get("env_passthrough") or []
        if not isinstance(passthrough, list):
            raise ValueError(f"AgentSpec {name!r}: env_passthrough must be a list")
        usage_paths = data.get("usage_paths") or []
        if not isinstance(usage_paths, list):
            raise ValueError(f"AgentSpec {name!r}: usage_paths must be a list")
        return cls(
            name=name,
            command=command,
            env_passthrough=tuple(str(k) for k in passthrough),
            setup_script=_optional_str(data.get("setup_script")),
            install_script=_optional_str(data.get("install_script")),
            run_as=run_as,  # type: ignore[arg-type]
            model_prefix=model_prefix,  # type: ignore[arg-type]
            home=_optional_str(data.get("home")),
            setup_timeout_sec=float(data.get("setup_timeout_sec") or 120.0),
            python_hook=_optional_str(data.get("python_hook")),
            runtime=_optional_str(data.get("runtime")),
            usage_paths=tuple(str(p) for p in usage_paths if str(p).strip()),
        )


@dataclass(frozen=True)
class AgentInvocation:
    """Fully-resolved agent invocation for one solve phase."""

    spec: AgentSpec
    model: str
    resolved_model: str
    command: str
    env: dict[str, str]
    env_keys: tuple[str, ...]
    setup_script: str | None
    install_script: str | None
    prepare_workspace: str
    run_as: str | None  # docker exec -u value; None => root
    home: str
    setup_timeout_sec: float
    spec_hash: str = field(repr=False, default="")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _load_spec_file(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"agent spec not found: {path}")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                f"PyYAML is required to load {path.name}; use a .json spec or "
                "pip install pyyaml"
            ) from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"agent spec must be a mapping: {path}")
    return data


def load_agent_spec(path: Path | str) -> AgentSpec:
    """Load an AgentSpec from a local trusted file (JSON or YAML)."""
    return AgentSpec.from_dict(_load_spec_file(Path(path)))


def builtin_spec(name: str) -> AgentSpec:
    if name not in BACKENDS:
        raise ValueError(f"unknown built-in backend {name!r}; choose from {BACKENDS}")
    return _BUILTIN_SPECS[name]


def resolve_agent(
    *,
    backend: str | None = None,
    agent_spec_path: Path | str | None = None,
    spec: AgentSpec | None = None,
    model: str,
    instruction_path: str = CONTAINER_INSTRUCTION_PATH,
    log_path: str = CONTAINER_AGENT_LOG,
    environ: dict[str, str] | None = None,
) -> AgentInvocation:
    if sum(x is not None for x in (backend, agent_spec_path, spec)) != 1:
        raise ValueError("pass exactly one of backend=, agent_spec_path=, or spec=")
    if spec is not None:
        resolved_spec = spec
    elif agent_spec_path is not None:
        resolved_spec = load_agent_spec(agent_spec_path)
    else:
        resolved_spec = builtin_spec(backend)  # type: ignore[arg-type]

    if not model:
        raise ValueError("model is required")
    if resolved_spec.name == "opencode" and "/" not in model:
        raise ValueError(
            "opencode model must be in 'provider/model' form, got " + repr(model)
        )

    environ = os.environ if environ is None else environ
    _validate_codex_effort(resolved_spec, environ)
    env, env_keys = _resolve_env(resolved_spec, model=model, environ=environ)
    resolved_model = _resolve_model(resolved_spec, model)
    ctx = {
        "model": resolved_model,
        "model_quoted": shlex.quote(resolved_model),
        "raw_model": model,
        "instruction": instruction_path,
        "instruction_quoted": shlex.quote(instruction_path),
        "log": log_path,
        "log_quoted": shlex.quote(log_path),
        "workdir": CONTAINER_WORKDIR,
        "workdir_quoted": shlex.quote(CONTAINER_WORKDIR),
        "home": _home_for(resolved_spec),
    }
    command = _render_template(resolved_spec.command, ctx)
    setup = _render_optional(resolved_spec.setup_script, ctx)
    install = resolved_spec.install_script
    prepare = _prepare_workspace_script(resolved_spec)
    run_as = AGENT_USER if resolved_spec.run_as == "nonroot" else None
    return AgentInvocation(
        spec=resolved_spec,
        model=model,
        resolved_model=resolved_model,
        command=command,
        env=env,
        env_keys=env_keys,
        setup_script=setup,
        install_script=install,
        prepare_workspace=prepare,
        run_as=run_as,
        home=_home_for(resolved_spec),
        setup_timeout_sec=resolved_spec.setup_timeout_sec,
        spec_hash=resolved_spec.spec_hash(),
    )


def _validate_codex_effort(spec: AgentSpec, environ: dict[str, str]) -> None:
    if spec.name != "codex":
        return
    raw = (environ.get(CODEX_REASONING_EFFORT_ENV) or "").strip()
    if not raw:
        return
    if raw not in CODEX_REASONING_EFFORTS:
        allowed = ", ".join(sorted(CODEX_REASONING_EFFORTS))
        raise ValueError(
            f"{CODEX_REASONING_EFFORT_ENV} must be one of {allowed}, got {raw!r}"
        )


def _home_for(spec: AgentSpec) -> str:
    if spec.home:
        return spec.home
    if spec.run_as == "nonroot":
        return AGENT_USER_HOME
    if spec.name == "codex":
        return "/root/.codex"
    return "/root"


def _resolve_model(spec: AgentSpec, model: str) -> str:
    if spec.model_prefix == "strip" and "/" in model:
        return model.split("/")[-1]
    return model


def _resolve_env(
    spec: AgentSpec,
    *,
    model: str,
    environ: dict[str, str],
) -> tuple[dict[str, str], tuple[str, ...]]:
    out: dict[str, str] = {}
    keys: list[str] = []
    for key in spec.env_passthrough:
        if environ.get(key):
            out[key] = environ[key]
            keys.append(key)
    if spec.python_hook:
        hook = _load_hook(spec.python_hook)
        extra = hook(model=model, environ=environ, spec=spec)
        for key, value in extra.items():
            if value:
                out[key] = value
                if key not in keys:
                    keys.append(key)
    if spec.name == "codex":
        out.setdefault("CODEX_HOME", _home_for(spec))
        if "CODEX_HOME" not in keys:
            keys.append("CODEX_HOME")
    if spec.name == "claude-code" and spec.run_as == "nonroot":
        # Override any image-baked (root-owned) CLAUDE_CONFIG_DIR with a path the
        # non-root agent can write, so the Bash tool can create its session dir.
        out["CLAUDE_CONFIG_DIR"] = _claude_config_dir(spec)
        if "CLAUDE_CONFIG_DIR" not in keys:
            keys.append("CLAUDE_CONFIG_DIR")
    if spec.name == "claude-code" and spec.run_as == "root":
        # bypassPermissions is refused for a real root login. Claude Code allows
        # it when the process identifies itself as a harness sandbox.
        out["IS_SANDBOX"] = "1"
        if "IS_SANDBOX" not in keys:
            keys.append("IS_SANDBOX")
    if spec.name == "openhands":
        if not (environ.get("LLM_API_KEY") or "").strip() or not (environ.get("LLM_BASE_URL") or "").strip():
            raise RuntimeError(
                "cbrun: OpenHands needs LLM_API_KEY and LLM_BASE_URL "
                "(OpenAI-compatible endpoint) in the environment"
            )
        out["LLM_MODEL"] = model
        out["OPENHANDS_SUPPRESS_BANNER"] = "1"
        # Library default is 300s. DeepSeek thinking turns stay silent well past
        # that, so one request may run for 30 minutes before it is abandoned.
        raw_timeout = (environ.get("LLM_TIMEOUT") or "").strip() or "1800"
        if not raw_timeout.isdigit() or int(raw_timeout) <= 0:
            raise RuntimeError(
                "cbrun: LLM_TIMEOUT must be a positive integer number of seconds, "
                f"got {raw_timeout!r}"
            )
        out["LLM_TIMEOUT"] = raw_timeout
        effort = (environ.get("LLM_REASONING_EFFORT") or "").strip()
        if effort:
            out["LLM_REASONING_EFFORT"] = effort
        for key in ("LLM_MODEL", "OPENHANDS_SUPPRESS_BANNER", "LLM_TIMEOUT", "LLM_REASONING_EFFORT"):
            if key not in keys and key in out:
                keys.append(key)
    if spec.run_as == "nonroot":
        home = _home_for(spec)
        out.setdefault("HOME", home)
        if "HOME" not in keys:
            keys.append("HOME")
    return out, tuple(keys)


def _load_hook(path: str):
    if path in _HOOKS:
        return _HOOKS[path]
    module_name, _, attr = path.partition(":")
    if not attr:
        raise ValueError(f"invalid python_hook (expected module:callable): {path!r}")
    module = importlib.import_module(module_name)
    fn = getattr(module, attr, None)
    if not callable(fn):
        raise ValueError(f"python_hook {path!r} is not callable")
    return fn


def _render_optional(template: str | None, ctx: dict[str, str]) -> str | None:
    if not template:
        return None
    return _render_template(template, ctx)


def _render_template(template: str, ctx: dict[str, str]) -> str:
    """Substitute ``{key}`` placeholders without interpreting other braces."""
    out = template
    for key, value in ctx.items():
        out = out.replace("{" + key + "}", value)
    return out


def _prepare_workspace_script(spec: AgentSpec) -> str:
    workdir = CONTAINER_WORKDIR
    if spec.run_as == "nonroot":
        home = _home_for(spec)
        paths = [workdir, home, "/tmp/cbrun", "/logs/agent"]
        if spec.name == "claude-code":
            # Ensure the repointed CLAUDE_CONFIG_DIR exists and is agent-owned so
            # Claude Code's Bash tool can initialize its session directory.
            paths.append(_claude_config_dir(spec))
        quoted = " ".join(shlex.quote(p) for p in paths)
        return (
            f"set -eu; "
            f"mkdir -p {quoted}; "
            f"chown -R {AGENT_USER}:{AGENT_USER} {quoted}"
        )
    return f"set -eu; mkdir -p {shlex.quote(workdir)} /logs/agent"


def _claude_config_dir(spec: AgentSpec) -> str:
    """Writable CLAUDE_CONFIG_DIR under the agent HOME (posix join)."""
    home = _home_for(spec).rstrip("/")
    return f"{home}/{AGENT_CLAUDE_CONFIG_DIRNAME}"


_CODEX_GATEWAY_TABLE = GATEWAY_PROVIDER_TABLE.format(
    base_url="${OPENAI_BASE_URL}", websockets="${CBRUN_GATEWAY_WS}"
)

# Top-level keys first, the provider table last: TOML attaches every key after
# a ``[table]`` header to that table.
_CODEX_SETUP = f"""set -eu
mkdir -p "$CODEX_HOME"
if [ -n "${{OPENAI_API_KEY:-}}" ]; then
  printf '%s\\n' "{{\\"OPENAI_API_KEY\\": \\"${{OPENAI_API_KEY}}\\"}}" > "$CODEX_HOME/auth.json"
fi
if [ -n "${{OPENAI_BASE_URL:-}}" ]; then
  printf '%s' '{GATEWAY_MODEL_PROVIDER_LINE}' >> "$CODEX_HOME/config.toml"
fi
if [ -n "${{CBRUN_CODEX_REASONING_EFFORT:-}}" ]; then
  printf '%s\\n' "model_reasoning_effort = \\"${{CBRUN_CODEX_REASONING_EFFORT}}\\"" >> "$CODEX_HOME/config.toml"
fi
if [ -n "${{OPENAI_BASE_URL:-}}" ]; then
  case "${{{CODEX_GATEWAY_WEBSOCKETS_ENV}:-}}" in
    1|true|yes|TRUE|YES) CBRUN_GATEWAY_WS=true ;;
    *) CBRUN_GATEWAY_WS=false ;;
  esac
  cat >> "$CODEX_HOME/config.toml" <<TOML
{_CODEX_GATEWAY_TABLE}TOML
fi
if [ -f "$CODEX_HOME/config.toml" ]; then
  cat "$CODEX_HOME/config.toml"
fi
"""

# Cursor's headless CLI reports the billed total on one turnEnded message and
# prints it on the result line only if the process then exits. This patches
# that handler so the total is appended under /logs/agent the moment it
# arrives. The patch is inside the CLI bundle, not under /app.
_CURSOR_USAGE_HOOK_SETUP = r"""set -eu
mkdir -p /logs/agent
python3 - << 'PY'
import os
from pathlib import Path
marker = 'case"turnEnded":{const e=n.message.value;'
needle = "/logs/agent/cursor_usage.jsonl"
inject = (
    marker
    + 'try{var _cbv=e;if(_cbv.inputTokens!=null||_cbv.outputTokens!=null||_cbv.cacheReadTokens!=null||_cbv.cacheWriteTokens!=null){'
    + 'require("fs").appendFileSync("/logs/agent/cursor_usage.jsonl",JSON.stringify({'
    + 'input_tokens:Math.max(Number(_cbv.inputTokens??0)-Number(_cbv.cacheReadTokens??0)-Number(_cbv.cacheWriteTokens??0),0),'
    + 'output_tokens:Number(_cbv.outputTokens??0),'
    + 'cache_read_tokens:Number(_cbv.cacheReadTokens??0),'
    + 'cache_write_tokens:Number(_cbv.cacheWriteTokens??0)})+"\\n")}}catch(_cb){}'
)
roots = [Path("/root/.local/share/cursor-agent/versions"), Path("/usr/local/share/cursor-agent/versions")]
found = []
for root in roots:
    if not root.is_dir():
        continue
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            if not name.endswith(".js"):
                continue
            path = Path(dirpath) / name
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if marker in text:
                found.append(path)
if len(found) != 1:
    raise SystemExit("cbrun: cursor usage patch matched %d files" % len(found))
path = found[0]
text = path.read_text(encoding="utf-8")
if needle in text:
    raise SystemExit(0)
if text.count(marker) != 1:
    raise SystemExit("cbrun: cursor usage marker count %d" % text.count(marker))
path.write_text(text.replace(marker, inject, 1), encoding="utf-8")
PY
"""

# OpenHands adds each completion to an in-memory Metrics object and only
# rewrites base_state.json when some other conversation field changes. A kill
# therefore leaves the startup snapshot, whose counters are still zero. This
# appends the completion inside add_token_usage, before the process can exit.
_OPENHANDS_USAGE_SETUP = r"""set -eu
mkdir -p /logs/agent
python3 - << 'PY'
import os
from pathlib import Path
marker = "        self.token_usages.append(usage)\n"
needle = "/logs/agent/openhands_usage.jsonl"
inject = marker + (
    "        try:\n"
    "            import json as _cb_json\n"
    "            import os as _cb_os\n"
    "            _cb_os.makedirs(\"/logs/agent\", exist_ok=True)\n"
    "            with open(\"/logs/agent/openhands_usage.jsonl\", \"a\", encoding=\"utf-8\") as _cb_fh:\n"
    "                _cb_fh.write(_cb_json.dumps({\n"
    "                    \"model\": usage.model,\n"
    "                    \"prompt_tokens\": int(usage.prompt_tokens),\n"
    "                    \"completion_tokens\": int(usage.completion_tokens),\n"
    "                    \"cache_read_tokens\": int(usage.cache_read_tokens),\n"
    "                    \"cache_write_tokens\": int(usage.cache_write_tokens),\n"
    "                    \"reasoning_tokens\": int(usage.reasoning_tokens),\n"
    "                    \"response_id\": usage.response_id,\n"
    "                }) + \"\\n\")\n"
    "                _cb_fh.flush()\n"
    "                _cb_os.fsync(_cb_fh.fileno())\n"
    "        except Exception:\n"
    "            pass\n"
)
roots = [
    Path("/root/.local/share/uv/tools/openhands/lib"),
    Path("/usr/local/lib"),
]
found = []
for root in roots:
    if not root.is_dir():
        continue
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            if name != "metrics.py":
                continue
            path = Path(dirpath) / name
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if marker in text:
                found.append(path)
if len(found) != 1:
    raise SystemExit("cbrun: openhands usage patch matched %d files" % len(found))
path = found[0]
text = path.read_text(encoding="utf-8")
if needle in text:
    raise SystemExit(0)
if text.count(marker) != 1:
    raise SystemExit("cbrun: openhands usage marker count %d" % text.count(marker))
path.write_text(text.replace(marker, inject, 1), encoding="utf-8")
PY
"""

_BUILTIN_SPECS: dict[str, AgentSpec] = {
    "codex": AgentSpec(
        name="codex",
        env_passthrough=(
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "CBRUN_CODEX_REASONING_EFFORT",
            CODEX_GATEWAY_WEBSOCKETS_ENV,
        ),
        setup_script=_CODEX_SETUP,
        run_as="root",
        model_prefix="keep",
        home="/root/.codex",
        runtime="node",
        usage_paths=("$CODEX_HOME/sessions",),
        command=(
            "codex exec "
            "--dangerously-bypass-approvals-and-sandbox "
            "--skip-git-repo-check "
            "--cd {workdir_quoted} "
            "--model {model_quoted} "
            "--json "
            "--enable unified_exec "
            "- < {instruction_quoted} "
            "2>&1 | stdbuf -oL tee {log_quoted}"
        ),
    ),
    "opencode": AgentSpec(
        name="opencode",
        env_passthrough=(),
        python_hook="cbrun.agent_hooks:opencode_env",
        run_as="root",
        model_prefix="keep",
        runtime="node",
        # Session totals, subagents included, written as each step finishes.
        usage_paths=("${XDG_DATA_HOME:-$HOME/.local/share}/opencode",),
        command=(
            "opencode --model={model_quoted} run "
            "--format=json --thinking --auto "
            "< {instruction_quoted} "
            "2>&1 | stdbuf -oL tee {log_quoted}"
        ),
    ),
    "claude-code": AgentSpec(
        name="claude-code",
        env_passthrough=(),
        python_hook="cbrun.agent_hooks:claude_code_env",
        run_as="root",
        model_prefix="keep",
        home="/root",
        runtime="node",
        usage_paths=("${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects",),
        command=(
            "cat {instruction_quoted} | claude --print --verbose --output-format stream-json "
            "--permission-mode bypassPermissions "
            "--model {model_quoted} "
            # Stream thinking summaries: a gateway that forwards nothing while the
            # model thinks otherwise outlasts Claude Code's stream idle timeout.
            "--thinking-display summarized "
            "2>&1 | stdbuf -oL tee {log_quoted}"
        ),
    ),
    "cursor": AgentSpec(
        name="cursor",
        env_passthrough=("CURSOR_API_KEY",),
        run_as="root",
        model_prefix="keep",
        home="/root",
        # The billed total arrives on turnEnded and is otherwise printed only
        # on the final result line. The setup writes that total to
        # /logs/agent immediately, so a crash after the server has reported
        # it still leaves a usage file for the archive to copy.
        setup_script=_CURSOR_USAGE_HOOK_SETUP,
        command=(
            "cursor-agent -p --force --trust --sandbox disabled "
            "--model {model_quoted} --workspace {workdir_quoted} "
            "--output-format stream-json "
            "< {instruction_quoted} "
            "2>&1 | stdbuf -oL tee {log_quoted}"
        ),
    ),
    "openhands": AgentSpec(
        name="openhands",
        env_passthrough=("LLM_API_KEY", "LLM_BASE_URL"),
        run_as="root",
        model_prefix="keep",
        home="/root",
        # Each completion is appended under /logs/agent as add_token_usage
        # returns, so a kill does not lose the calls already billed.
        setup_script=_OPENHANDS_USAGE_SETUP,
        usage_paths=("/root/.openhands",),
        command=(
            "openhands --headless --json --always-approve "
            "--exit-without-confirmation --override-with-envs "
            "-f {instruction_quoted} "
            "2>&1 | stdbuf -oL tee {log_quoted}"
        ),
    ),
}
