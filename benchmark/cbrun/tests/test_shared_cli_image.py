from __future__ import annotations

import argparse
import subprocess
import threading
from pathlib import Path

import pytest

from cbrun import agent_spec, agents, cli, images
from cbrun.docker_env import image_build_lock

PINNED = {"CBRUN_CLAUDE_VERSION": "2.1.280"}


def test_cli_image_tag_carries_the_pinned_version() -> None:
    assert images.cli_image_tag("claude-code", PINNED) == "codingbench-cli/claude-code:2.1.280"


def test_agent_dockerfile_copies_the_shared_cli_instead_of_installing_it() -> None:
    shared = images._build_dockerfile(
        "c:deliverable", PINNED, backend="claude-code", cli_image="codingbench-cli/claude-code:2.1.280"
    )
    assert "COPY --from=codingbench-cli/claude-code:2.1.280 /opt/cbrun/runtime/node /opt/cbrun/runtime/node" in shared
    assert "npm" not in shared
    assert "ln -sfn /opt/cbrun/runtime/node/bin/claude /usr/local/bin/claude" in shared

    installed = images._build_dockerfile("c:deliverable", PINNED, backend="claude-code")
    assert "COPY --from" not in installed
    assert "npm" in installed


def test_ensure_cli_image_reuses_an_existing_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(images, "image_exists", lambda tag: True)

    def no_build(*args, **kwargs):
        raise AssertionError("an existing CLI image must not be rebuilt")

    monkeypatch.setattr(images.subprocess, "run", no_build)
    assert images.ensure_cli_image("claude-code", PINNED) == "codingbench-cli/claude-code:2.1.280"


def test_concurrent_callers_build_the_cli_image_once(monkeypatch: pytest.MonkeyPatch) -> None:
    built: set[str] = set()
    builds: list[list[str]] = []
    monkeypatch.setattr(images, "image_exists", lambda tag: tag in built)

    def fake_build(argv, **kwargs):
        builds.append(argv)
        built.add(argv[argv.index("-t") + 1])
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(images.subprocess, "run", fake_build)
    threads = [threading.Thread(target=images.ensure_cli_image, args=("claude-code", PINNED)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(builds) == 1


def test_only_npm_backends_have_a_shared_cli_image() -> None:
    with pytest.raises(ValueError):
        images.ensure_cli_image("cursor", {"CBRUN_CURSOR_VERSION": "1"})


def test_build_lock_serialises_holders() -> None:
    order: list[str] = []

    def hold(name: str) -> None:
        with image_build_lock("codingbench-cli/test:lock"):
            order.append(f"{name}-in")
            order.append(f"{name}-out")

    threads = [threading.Thread(target=hold, args=(n,)) for n in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Each holder's in/out pair is adjacent: no two were inside at once.
    for i in range(0, len(order), 2):
        assert order[i].split("-")[0] == order[i + 1].split("-")[0]


def test_build_images_builds_the_cli_image_once_before_any_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    lock = threading.Lock()

    def record(event: str) -> None:
        with lock:
            events.append(event)

    monkeypatch.setattr(images, "ensure_cli_image", lambda backend, force=False: record(f"cli:{backend}") or "cli")

    class Built:
        def __init__(self, tag: str) -> None:
            self.agent_image = tag

    monkeypatch.setattr(
        images, "ensure_agent_image", lambda case_id, **kw: record(f"case:{case_id}") or Built(f"{case_id}:agent")
    )
    case_dirs = [tmp_path / f"case{i:03d}" for i in range(1, 6)]
    args = argparse.Namespace(
        backend=["claude-code"], jobs=4, force_image=False, cache_root=tmp_path, enforce_denylist=True
    )
    assert cli._build_images(args, case_dirs) == 0

    shared = [e for e in events if not e.startswith("case:")]
    first_case = min(i for i, e in enumerate(events) if e.startswith("case:"))
    assert all(events.index(e) < first_case for e in shared)
    assert events.count("cli:claude-code") == 1
    assert sorted(e for e in events if e.startswith("case:")) == [f"case:{d.name}" for d in case_dirs]


def _claude_command(environ: dict[str, str]) -> str:
    return agent_spec.resolve_agent(
        backend="claude-code", model="m", instruction_path="/tmp/i.md", log_path="/tmp/l.log",
        environ={"ANTHROPIC_API_KEY": "k", **environ},
    ).command


def test_claude_effort_becomes_the_cli_flag() -> None:
    assert _claude_command({"CBRUN_CLAUDE_EFFORT": "high"}).endswith("--effort high")
    assert "--effort" not in _claude_command({})


def test_unknown_claude_effort_is_refused() -> None:
    with pytest.raises(ValueError, match="CBRUN_CLAUDE_EFFORT"):
        _claude_command({"CBRUN_CLAUDE_EFFORT": "ultra"})


def test_npm_install_runs_lifecycle_scripts_with_the_same_node() -> None:
    # claude-code's postinstall runs `node install.cjs`; on an image without a
    # system node that lookup must find the private node.
    cmd = agents.cli_install_command("claude-code", PINNED)
    assert 'ln -sfn "$NODE" /usr/local/bin/node' in cmd
    assert 'PATH="$(dirname "$NODE"):$PATH" "$NODE" "$NPM" install -g' in cmd
