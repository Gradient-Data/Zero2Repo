"""dsh as a built-in harness, and what a full-suite run prepares for it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cbrun import agents, images, supply
from cbrun.agent_spec import BACKENDS, resolve_agent
from cbrun.supply_proxy import Entry
from cbrun.usage import parse_usage_text


def test_dsh_is_an_npm_harness_with_a_required_pin() -> None:
    assert "dsh" in BACKENDS
    assert "dsh" in agents.NPM_BACKENDS
    with pytest.raises(RuntimeError, match="CBRUN_DSH_VERSION"):
        agents.cli_version_spec("dsh", {})
    assert agents.cli_version_spec("dsh", {"CBRUN_DSH_VERSION": "0.2.1-rc.2"}) == "@0.2.1-rc.2"
    assert images.cli_image_tag("dsh", {"CBRUN_DSH_VERSION": "0.2.1-rc.2"}) == (
        "codingbench-cli/dsh:0.2.1-rc.2"
    )


def test_dsh_lands_on_the_default_path_in_the_case_image() -> None:
    link = agents.cli_link_command("dsh")
    assert "ln -sfn /opt/cbrun/runtime/node/bin/dsh /usr/local/bin/dsh" in link
    dockerfile = images._build_dockerfile("deliverable", {}, backend="dsh", cli_image="cli")
    assert "COPY --from=cli /opt/cbrun/runtime/node /opt/cbrun/runtime/node" in dockerfile
    assert link in dockerfile


def test_dsh_spec_runs_headless_without_prompts() -> None:
    inv = resolve_agent(
        backend="dsh",
        model="deepseek/deepseek-v4.1-flash",
        environ={"DEEPSEEK_API_KEY": "k", "DEEPSEEK_BASE_URL": "https://example.test/api"},
    )
    assert inv.command.startswith("dsh --profile headless --patch /tmp/cbrun/dsh-model.yml --json")
    assert inv.env["DSH_PERMISSION_MODE"] == "danger-full-access"
    assert inv.env["DSH_HOME"] == "/root/.dsh"
    assert "deepseek/deepseek-v4.1-flash" in (inv.setup_script or "")
    assert inv.spec.usage_paths == ("/root/.dsh",)


def test_dsh_step_usage_is_summed_from_its_event_stream() -> None:
    lines = [
        {"type": "status", "phase": "step_end", "usage": {
            "inputTokens": 844, "outputTokens": 132, "cacheReadTokens": 5376, "cacheWriteTokens": 0}},
        {"type": "status", "phase": "step_end", "usage": {
            "inputTokens": 10, "outputTokens": 5, "cacheReadTokens": 100, "reasoningTokens": 3}},
        {"type": "status", "phase": "step_start"},
    ]
    parsed = parse_usage_text("\n".join(json.dumps(line) for line in lines))
    assert parsed.calls_source == "dsh_step_end"
    assert parsed.calls.input_tokens == 854
    assert parsed.calls.output_tokens == 137
    assert parsed.calls.cache_read_tokens == 5476
    assert parsed.calls.reasoning_tokens == 3


def _write_lock(locks: Path, segment: str, name: str, digest: str, entries: list[Entry]) -> None:
    sub = {"base": locks, "case": locks / "cases", "harness": locks / "harnesses"}[segment]
    sub.mkdir(parents=True, exist_ok=True)
    payload = {"inputs_digest": digest, "entries": [e.to_dict() for e in entries]}
    if segment == "base":
        payload["from_image"] = "ubuntu:24.04@sha256:" + "0" * 64
    (sub / f"{'base' if segment == 'base' else name}.json").write_text(json.dumps(payload))


def test_a_dsh_run_prepares_only_the_dsh_harness_entry(tmp_path, monkeypatch) -> None:
    from cbrun import docker_env, recipe
    from cbrun.supply_store import Store
    from cbrun.supply_proxy import ProxyHub

    locks = tmp_path / "locks"
    monkeypatch.setattr(supply, "LOCKS_DIR", locks)
    environ = {
        "CBRUN_DSH_VERSION": "0.2.1-rc.2",
        "CBRUN_CLAUDE_VERSION": "2.1.280",
        "CBRUN_CODEX_VERSION": "0.160.0",
    }
    dsh_entry = Entry("GET", "https://registry.npmjs.org/@deepseek-ai/dsh/-/dsh-0.2.1-rc.2.tgz",
                      "", 200, "a" * 64, 3)
    claude_entry = Entry("GET", "https://registry.npmjs.org/claude.tgz", "", 200, "b" * 64, 3)
    _write_lock(locks, "harness", "dsh-0.2.1-rc.2",
                supply.harness_inputs_digest("dsh", environ), [dsh_entry])
    _write_lock(locks, "harness", "claude-code-2.1.280",
                supply.harness_inputs_digest("claude-code", environ), [claude_entry])
    _write_lock(locks, "base", "base", supply.base_inputs_digest(), [])

    # Every image exists except the dsh shared CLI image.
    monkeypatch.setattr(docker_env, "image_exists", lambda tag: tag != "codingbench-cli/dsh:0.2.1-rc.2")
    fetched: list[str] = []
    monkeypatch.setattr(
        supply, "_fetch_all",
        lambda store, hub, entries: (fetched.extend(e.url for e in entries) or (0, [])),
    )
    store = Store(tmp_path / "store")
    run = supply.SupplyRun(
        environ=environ, store=store, hub=ProxyHub(store), manifest=supply.load_manifest()
    )
    case_dir = Path(__file__).resolve().parents[2] / "cases" / "case001"
    run.prepare([case_dir], ["dsh"])
    assert fetched == [dsh_entry.url]
    assert recipe.env_recipe_tag("case001")  # env image exists: case001 needs no lock


def test_a_run_without_a_lock_fails_before_downloading(tmp_path, monkeypatch) -> None:
    from cbrun import docker_env
    from cbrun.supply_store import Store
    from cbrun.supply_proxy import ProxyHub

    monkeypatch.setattr(supply, "LOCKS_DIR", tmp_path / "locks")
    monkeypatch.setattr(docker_env, "image_exists", lambda tag: False)
    store = Store(tmp_path / "store")
    run = supply.SupplyRun(
        environ={"CBRUN_DSH_VERSION": "9.9.9"}, store=store, hub=ProxyHub(store),
        manifest=supply.load_manifest(),
    )
    case_dir = Path(__file__).resolve().parents[2] / "cases" / "case003"
    with pytest.raises(supply.SupplyError) as info:
        run.prepare([case_dir], ["dsh"])
    message = str(info.value)
    assert "case case003: no supply lock" in message
    assert "harness dsh: version 9.9.9 is not listed" in message
