"""Per-case ``:deliverable`` / ``:agent`` image derivation.

When ``:deliverable`` is missing, cbrun rebuilds it from the recipe base
(``codingbench-base/<public>``, built FROM the matching public image such as
Docker Hub ``ubuntu:24.04`` using ``cbrun/base_image/Dockerfile``) plus
``source/recipe.lock.json`` (env-install-only: toolchain, public specs,
hidden tests, empty ``/app``). If the local base tag is missing, cbrun pulls
the public image and builds the toolchain image once. Callers that clone the
repo therefore do not need a per-case image tarball.

From that ``:deliverable``, cbrun derives an ``:agent`` image by (1) extracting
``/tests/final`` to a host-side cache, (2) installing the requested backend
CLI (or all built-in CLIs when no backend is given), and (3) physically
removing ``/tests/final`` in a new image layer. Per-backend images are tagged
``:agent-<backend>`` so a Cursor trial does not pull unused npm CLIs. The solve container is started from this ``:agent`` image, so the hidden
tests are absent from the solve filesystem entirely (not merely deleted at
runtime), and are re-injected only for the judge phase.

Note on a shared CLI base: the published ``:deliverable`` images have
heterogeneous bases (e.g. ``python:3.13-slim`` vs ``cuda:13.0-devel-ubuntu24.04``),
so a single shared ``FROM`` base cannot be overlaid onto all of them. cbrun
instead installs pinned CLI versions per case with idempotent caching (skip when
the ``:agent`` image already exists), which gives the same reproducibility goal
without an impossible image merge.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import agents
from .denylist import (
    log_probe_result,
    probe_agent_runtime_leak,
    probe_banned_imports,
    write_shim_assets,
)
from .docker_env import image_exists
from .state import FINGERPRINT_LABEL, digest, file_manifest, image_identity, image_matches, platform_name

# Defense in depth when :deliverable was built before workspace sanitization existed.
_AGENT_APP_SANITIZE = (
    "rm -rf /app /opt/codingbench/repo /opt/cb-warm && mkdir -p /app"
)

__all__ = [
    "AgentImage",
    "deliverable_tag",
    "agent_tag",
    "extract_hidden_tests",
    "ensure_agent_image",
]

CONTAINER_TESTS_FINAL = "/tests/final"


def deliverable_tag(case_id: str) -> str:
    return f"codingbench-benchmark/{case_id}:deliverable"


def agent_tag(case_id: str, backend: str | None = None) -> str:
    if backend:
        return f"codingbench-benchmark/{case_id}:agent-{backend}"
    return f"codingbench-benchmark/{case_id}:agent"


@dataclass(frozen=True)
class AgentImage:
    case_id: str
    deliverable_image: str
    agent_image: str
    tests_cache_dir: Path  # host dir holding the extracted /tests/final


def extract_hidden_tests(deliverable_image: str, dest_dir: Path) -> Path:
    """Copy ``/tests/final`` out of the deliverable image into ``dest_dir``.

    Returns the path to the extracted ``final`` directory. Raises if the
    deliverable image has no hidden tests (an invalid benchmark image).
    """
    dest_dir = Path(dest_dir)
    if dest_dir.exists():
        _rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    create = subprocess.run(
        ["docker", "create", "--platform", platform_name(), deliverable_image],
        capture_output=True,
        text=True,
    )
    if create.returncode != 0:
        raise RuntimeError(f"docker create {deliverable_image} failed: {create.stderr.strip()}")
    container_id = create.stdout.strip()
    try:
        cp = subprocess.run(
            ["docker", "cp", f"{container_id}:{CONTAINER_TESTS_FINAL}", str(dest_dir / "final")],
            capture_output=True,
            text=True,
        )
        if cp.returncode != 0:
            raise RuntimeError(
                f"deliverable image {deliverable_image} is missing {CONTAINER_TESTS_FINAL}: "
                f"{cp.stderr.strip()}"
            )
    finally:
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, text=True)

    final_dir = dest_dir / "final"
    if not (final_dir / "test_manifest.json").is_file():
        raise RuntimeError(
            f"extracted hidden tests for {deliverable_image} lack test_manifest.json"
        )
    return final_dir


_NODE_VERSION = "22.20.0"
_NODE_TARBALL_SHA256 = {
    "x64": "eeaccb0378b79406f2208e8b37a62479c70595e20be6b659125eb77dd1ab2a29",
    "arm64": "4181609e03dcb9880e7e5bf956061ecc0503c77a480c6631d868cb1f65a2c7dd",
}


def _node_install_snippet() -> str:
    """Install Node for CLIs under a private prefix when the image has none.

    Deliverable images that already ship ``node`` (declared runtimes) are
    left alone. The private tree is never added to ``ENV PATH``.
    """
    prefix = agents.NODE_RUNTIME_PREFIX
    sha_x64 = _NODE_TARBALL_SHA256["x64"]
    sha_arm64 = _NODE_TARBALL_SHA256["arm64"]
    return (
        f"if ! command -v node >/dev/null 2>&1; then "
        f"  prefix={prefix}; "
        "  mkdir -p \"$prefix\"; "
        "  command -v curl >/dev/null 2>&1 || { "
        "    if command -v apt-get >/dev/null 2>&1; then "
        "      apt-get update && apt-get install -y --no-install-recommends curl ca-certificates xz-utils && "
        "      rm -rf /var/lib/apt/lists/*; "
        "    elif command -v apk >/dev/null 2>&1; then apk add --no-cache curl ca-certificates xz; "
        "    else echo 'cbrun: curl required to install Node.js' >&2; exit 1; fi; "
        "  }; "
        "  arch=$(uname -m); "
        "  case \"$arch\" in "
        "    x86_64) node_arch=x64; sha=" + sha_x64 + " ;; "
        "    aarch64) node_arch=arm64; sha=" + sha_arm64 + " ;; "
        "    *) echo \"cbrun: unsupported arch $arch for Node.js\" >&2; exit 1 ;; "
        "  esac; "
        f"  tarball=node-v{_NODE_VERSION}-linux-$node_arch.tar.gz; "
        f"  curl -fsSL https://nodejs.org/dist/v{_NODE_VERSION}/$tarball -o /tmp/$tarball; "
        "  echo \"$sha  /tmp/$tarball\" | sha256sum -c -; "
        f"  tar -xzf /tmp/$tarball -C \"$prefix\" --strip-components=1; "
        "  rm -f /tmp/$tarball; "
        "  test -x \"$prefix/bin/node\"; "
        "fi"
    )


def _cli_install_snippet(environ: dict[str, str] | None, backend: str | None = None) -> str:
    if backend == "cursor":
        return agents.cli_install_command("cursor", environ)
    if backend is not None:
        return agents.cli_install_command(backend, environ)
    npm_clis = " && ".join(
        agents.cli_install_command(name, environ) for name in agents._CLI_PACKAGES
    )
    return f"{npm_clis} && {agents.cli_install_command('cursor', environ)}"


def _agent_user_snippet() -> str:
    """Create the fixed non-root user used by the judge and by specs that opt into it."""
    return (
        "if ! id -u cbagent >/dev/null 2>&1; then "
        "  command -v useradd >/dev/null 2>&1 || { "
        "echo 'cbrun: useradd not found; cannot create cbagent for non-root agents' >&2; exit 1; "
        "}; "
        "useradd -m -s /bin/bash -u 1001 cbagent 2>/dev/null || "
        "useradd -m -s /bin/bash cbagent; "
        "fi"
    )


def _build_dockerfile(
    deliverable_image: str,
    environ: dict[str, str] | None,
    *,
    denylist_snippet: str = "",
    backend: str | None = None,
    openhands_patch: bool = False,
) -> str:
    denylist_block = ""
    if denylist_snippet:
        denylist_block = f"RUN mkdir -p /opt/cbrun/bin\n{denylist_snippet}"
    cli = _cli_install_snippet(environ, backend)
    # Cursor installs from the official script; OpenHands is copied from a
    # prebuilt Python 3.12 image (the CLI pins 3.12, case images are 3.13);
    # other backends need npm.
    if backend == "openhands":
        image = agents.OPENHANDS_CLI_IMAGE
        install = f"COPY --from={image} /root/.local /root/.local\n"
        if openhands_patch:
            install += "COPY openhands_llm_timeout.py /tmp/openhands_llm_timeout.py\n"
        install += (
            "RUN ln -sfn /root/.local/bin/openhands /usr/local/bin/openhands "
            "&& /usr/local/bin/openhands --version"
        )
        if openhands_patch:
            install += (
                " && /root/.local/share/uv/tools/openhands/bin/python "
                "/tmp/openhands_llm_timeout.py "
                "&& rm -f /tmp/openhands_llm_timeout.py"
            )
        install += f"\nRUN set -eux; {_agent_user_snippet()}\n"
    elif backend == "cursor":
        install = f"RUN set -eux; {cli}; {_agent_user_snippet()}\n"
    else:
        install = (
            f"RUN set -eux; {_node_install_snippet()}; {cli}; "
            f"{_agent_user_snippet()}\n"
        )
    return (
        f"FROM {deliverable_image}\n"
        "USER root\n"
        f"{install}"
        f"{denylist_block}"
        f"RUN set -eux; {_AGENT_APP_SANITIZE}; rm -rf {CONTAINER_TESTS_FINAL}\n"
    )


def ensure_agent_image(
    case_id: str,
    *,
    cache_root: Path,
    case_dir: Path | None = None,
    deliverable_image: str | None = None,
    force: bool = False,
    environ: dict[str, str] | None = None,
    backend: str | None = None,
    enforce_denylist: bool = True,
) -> AgentImage:
    """Build (or reuse) the ``:agent`` image and extract hidden tests.

    Idempotent: when the ``:agent`` image and the tests cache already exist and
    ``force`` is False, returns immediately.
    """
    if enforce_denylist and case_dir is not None:
        from .denylist import require_denylist

        require_denylist(case_dir)

    deliverable = deliverable_image or deliverable_tag(case_id)
    # With the case at hand, always go through ensure_deliverable_image: it
    # reuses the tag only while its staged docs and hidden tests still match.
    if case_dir is not None and deliverable_image is None:
        from .recipe_image import ensure_deliverable_image

        deliverable = ensure_deliverable_image(case_dir, force=force)
    elif not image_exists(deliverable) or (force and case_dir is not None):
        if case_dir is None:
            raise RuntimeError(
                f"deliverable image not found: {deliverable}. Pass case_dir so "
                "cbrun can rebuild it from recipe.lock + the shared base image."
            )
        from .recipe_image import ensure_deliverable_image

        deliverable = ensure_deliverable_image(case_dir, force=force)

    tag = agent_tag(case_id, backend)
    try:
        deliverable_id = image_identity(deliverable)["id"]
    except (RuntimeError, OSError, ValueError):
        deliverable_id = deliverable
    tests_cache = Path(cache_root) / case_id / deliverable_id.replace("sha256:", "") / "tests"
    final_dir = tests_cache / "final"
    cached_ready = (final_dir / "test_manifest.json").is_file()

    with tempfile.TemporaryDirectory() as ctx:
        build_ctx = Path(ctx)
        denylist_snippet = ""
        if case_dir is not None:
            denylist_snippet = write_shim_assets(
                build_ctx,
                case_dir / "source" / "denylist.json",
                required=enforce_denylist,
            )
        openhands_patch = False
        if backend == "openhands":
            patch = Path(__file__).resolve().parent / "openhands_cli" / "apply_llm_timeout.py"
            if patch.is_file():
                (build_ctx / "openhands_llm_timeout.py").write_text(
                    patch.read_text(encoding="utf-8"), encoding="utf-8"
                )
                openhands_patch = True
        dockerfile = _build_dockerfile(
            deliverable,
            environ,
            denylist_snippet=denylist_snippet,
            backend=backend,
            openhands_patch=openhands_patch,
        )
        fingerprint = digest(
            {
                "deliverable_id": deliverable_id,
                "dockerfile": dockerfile,
                "platform": platform_name(),
                "backend": backend,
                "shim_assets": file_manifest(build_ctx),
            }
        )
        if (
            not force
            and image_exists(tag)
            and image_matches(tag, fingerprint)
            and cached_ready
        ):
            if case_dir is None:
                return AgentImage(case_id, deliverable, tag, tests_cache)
            probe = probe_banned_imports(tag, case_dir / "source" / "denylist.json")
            log_probe_result(probe)
            leak = _runtime_leak_probe(tag, deliverable, backend)
            log_probe_result(leak)
            if not probe.errors and not leak.errors:
                return AgentImage(case_id, deliverable, tag, tests_cache)
            print(
                f"[cbrun] cached agent image {tag} failed denylist probe; rebuilding",
                flush=True,
            )
            return ensure_agent_image(
                case_id,
                cache_root=cache_root,
                case_dir=case_dir,
                deliverable_image=deliverable_image,
                force=True,
                environ=environ,
                backend=backend,
                enforce_denylist=enforce_denylist,
            )

        extract_hidden_tests(deliverable, tests_cache)
        df_path = build_ctx / "Dockerfile"
        df_path.write_text(dockerfile, encoding="utf-8")
        print(
            f"[cbrun] building agent image {tag} (cli={backend or 'all'})",
            flush=True,
        )
        build = subprocess.run(
            [
                "docker", "build", "--platform", platform_name(),
                "--label", f"{FINGERPRINT_LABEL}={fingerprint}",
                "-t", tag, "-f", str(df_path), ctx,
            ],
        )
        if build.returncode != 0:
            raise RuntimeError(f"docker build of {tag} failed (exit {build.returncode})")
        if case_dir is not None:
            probe = probe_banned_imports(tag, case_dir / "source" / "denylist.json")
            log_probe_result(probe)
            leak = _runtime_leak_probe(tag, deliverable, backend)
            log_probe_result(leak)
            errors = probe.errors + leak.errors
            if errors:
                raise RuntimeError("; ".join(errors))
    return AgentImage(case_id, deliverable, tag, tests_cache)


def _runtime_leak_probe(
    agent_image: str, deliverable_image: str, backend: str | None
):
    if backend == "cursor":
        return probe_agent_runtime_leak(agent_image, deliverable_image, [])
    return probe_agent_runtime_leak(agent_image, deliverable_image, ["node"])


def _rmtree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
