"""Rebuild ``:deliverable`` from a pipeline base image + recipe.lock.

Clone-and-eval hosts should not download a multi-GB image per case. cbrun
replays the same env-install-only path as CodingBench-1.6
(``build_deliverable_env_install_only``):

1. Resolve ``recipe.lock.json`` ``base_image``. Tags under
   ``codingbench-base/`` are a local toolchain image built FROM the matching
   public image (Docker Hub ``ubuntu:24.04`` for the current suite). If the
   local tag is missing, pull the public image and ``docker build``
   ``cbrun/base_image/Dockerfile`` once.
2. Run ``runner.install_command`` (toolchain only; no seed repo).
3. Stage public PRD / Contract / optional hardware + hidden ``milestones/final``.
4. Leave ``/app`` empty. Commit as ``codingbench-benchmark/<case>:deliverable``.

``build_command`` is recorded on the lock but is not replayed here: there is
no upstream tree to compile. The solving agent builds in ``/app``.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .denylist import (
    install_ban_hashes_from_file,
    log_probe_result,
    probe_banned_imports,
    render_strip_script,
)
from .docker_env import docker_available, image_exists
from .images import deliverable_tag
from .state import FINGERPRINT_LABEL, digest, file_manifest, image_matches
from .recipe import (
    RecipeLockError,
    env_recipe_tag,
    load_lock,
    public_base_pull_ref,
    recipe_lock_path,
    resolve_lock_base_image,
    resolve_lock_runner,
    stage_benchmark_bundle,
    staging_shell_command,
    validate_lock_env_install,
)

__all__ = ["ensure_deliverable_image", "resource_fetch_command"]

GENERIC_FETCH_SCRIPT = Path(__file__).resolve().parent / "fetch_resources.py"

BASE_IMAGE_DOCKERFILE_DIR = Path(__file__).resolve().parent / "base_image"

DEFAULT_ENV_BUILD_RETRIES = 3
DEFAULT_ENV_BUILD_RETRY_DELAY_SEC = 15.0

_REGISTRY_ENV_KEYS = (
    "PIP_INDEX_URL",
    "PIP_EXTRA_INDEX_URL",
    "PIP_TRUSTED_HOST",
    "NPM_CONFIG_REGISTRY",
    "npm_config_registry",
    "MAVEN_OPTS",
    "PNPM_HOME",
)


def _remove_container(name: str) -> None:
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True)


def _env_build_retries() -> int:
    raw = os.environ.get("CODINGBENCH_RECIPE_ENV_RETRIES", "").strip()
    if not raw:
        return DEFAULT_ENV_BUILD_RETRIES
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_ENV_BUILD_RETRIES


def _env_build_retry_delay_sec() -> float:
    raw = os.environ.get("CODINGBENCH_RECIPE_ENV_RETRY_DELAY_SEC", "").strip()
    if not raw:
        return DEFAULT_ENV_BUILD_RETRY_DELAY_SEC
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_ENV_BUILD_RETRY_DELAY_SEC


def _docker_network() -> str:
    return os.environ.get("CODINGBENCH_DOCKER_NETWORK", "host")


def _registry_docker_env() -> list[str]:
    args: list[str] = []
    for var in _REGISTRY_ENV_KEYS:
        val = os.environ.get(var)
        if val and val.strip():
            args += ["-e", f"{var}={val.strip()}"]
    return args


def _runner_docker_gpus(runner: dict[str, Any]) -> str | None:
    override = os.environ.get("CODINGBENCH_DOCKER_GPUS")
    if override is not None:
        value = override.strip()
        return value or None
    raw = runner.get("docker_gpus")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def resource_fetch_command(case_dir: Path | str) -> str:
    """Return a shell preamble that verifies ``source/env/resources.json``.

    Empty when the case does not declare public resources. Destination,
    HTTPS URL, size, SHA-256, and license are required on every item.
    """
    case_dir = Path(case_dir)
    path = case_dir / "source" / "env" / "resources.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RecipeLockError(f"invalid {path}: {exc}") from exc
    dest = str(data.get("destination") or "").strip()
    if not dest.startswith("/"):
        raise RecipeLockError(f"{path}: destination must be an absolute container path")
    items = data.get("resources")
    if not isinstance(items, list) or not items:
        raise RecipeLockError(f"{path}: resources must be a non-empty list")
    for item in items:
        if not isinstance(item, dict):
            raise RecipeLockError(f"{path}: each resource must be an object")
        for key in ("id", "url", "sha256", "size", "license"):
            if not item.get(key) and item.get(key) != 0:
                raise RecipeLockError(f"{path}: resource missing {key}")
        if not str(item["url"]).startswith("https://"):
            raise RecipeLockError(f"{path}: resource URLs must use HTTPS")
    return (
        "python3 /opt/cbrun/fetch_resources.py "
        f"/env-assets/resources.json {shlex.quote(dest)}"
    )


def _volume_mounts(case_dir: Path) -> list[str]:
    """Optional operator-supplied caches. Never invented per case."""
    mounts: list[str] = []
    env_dir = case_dir / "source" / "env"
    if env_dir.is_dir() and any(env_dir.iterdir()):
        mounts.extend(["-v", f"{env_dir.resolve()}:/env-assets:ro"])
    if (env_dir / "resources.json").is_file() and GENERIC_FETCH_SCRIPT.is_file():
        mounts.extend(
            ["-v", f"{GENERIC_FETCH_SCRIPT}:/opt/cbrun/fetch_resources.py:ro"]
        )
    cache_raw = os.environ.get("CODINGBENCH_BUILD_CACHE_DIR", "").strip()
    if cache_raw and cache_raw.lower() not in {"off", "0", "false", "no"}:
        cache_dir = Path(cache_raw).expanduser()
        if cache_dir.is_dir():
            mounts.extend(["-v", f"{cache_dir.resolve()}:/opt/cb-cache"])
    return mounts


def _load_manifest_runner(case_dir: Path) -> dict[str, Any]:
    manifest_path = case_dir / "source" / "manifest.json"
    if not manifest_path.is_file():
        raise RecipeLockError(f"missing {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RecipeLockError(f"invalid JSON in {manifest_path}: {exc}") from exc
    runner = manifest.get("runner")
    if not isinstance(runner, dict):
        raise RecipeLockError("manifest.runner missing")
    return runner


def _ensure_base_image(base_image: str) -> None:
    """Make *base_image* available locally.

    Public tags are pulled. ``codingbench-base/<public>`` is built FROM the
    public image using ``base_image/Dockerfile`` (toolchain, not a retag).
    """
    if image_exists(base_image):
        return
    from_image = public_base_pull_ref(base_image)
    print(f"[cbrun] pulling {from_image}", flush=True)
    proc = subprocess.run(["docker", "pull", from_image])
    if proc.returncode != 0:
        raise RecipeLockError(
            f"docker pull failed for {from_image} "
            f"(exit {proc.returncode}; see streamed docker output above)"
        )
    if from_image == base_image:
        if not image_exists(base_image):
            raise RecipeLockError(f"base image still missing after pull: {base_image}")
        return

    dockerfile = BASE_IMAGE_DOCKERFILE_DIR / "Dockerfile"
    if not dockerfile.is_file():
        raise RecipeLockError(f"missing base-image Dockerfile: {dockerfile}")
    print(
        f"[cbrun] building {base_image} FROM {from_image} "
        f"({dockerfile})",
        flush=True,
    )
    proc = subprocess.run(
        [
            "docker",
            "build",
            "--build-arg",
            f"FROM_IMAGE={from_image}",
            "-t",
            base_image,
            str(BASE_IMAGE_DOCKERFILE_DIR),
        ]
    )
    if proc.returncode != 0:
        raise RecipeLockError(
            f"docker build failed for {base_image} "
            f"(exit {proc.returncode}; see streamed docker output above)"
        )
    if not image_exists(base_image):
        raise RecipeLockError(f"base image still missing after build: {base_image}")


def _denylist_file(case_dir: Path) -> Path:
    return case_dir / "source" / "denylist.json"


def _image_probe_clean(tag: str, case_dir: Path) -> bool:
    path = _denylist_file(case_dir)
    if not path.is_file():
        return True
    probe = probe_banned_imports(tag, path)
    log_probe_result(probe)
    return not probe.errors


def _strip_env_image(
    *,
    source_tag: str,
    dest_tag: str,
    case_dir: Path,
    case_id: str,
    gpus: str | None,
) -> None:
    denylist = _denylist_file(case_dir)
    hashes = install_ban_hashes_from_file(denylist) if denylist.is_file() else []
    strip_name = f"z2r-recipe-env-strip-{case_id}"
    _remove_container(strip_name)
    with tempfile.TemporaryDirectory(prefix="cbrun-strip-") as raw:
        host = Path(raw)
        (host / "strip_banned.py").write_text(render_strip_script(), encoding="utf-8")
        (host / "denylist.hashes").write_text(
            ("\n".join(hashes) + "\n") if hashes else "",
            encoding="utf-8",
        )
        argv = [
            "docker",
            "run",
            "--name",
            strip_name,
            "--network",
            "none",
            "-v",
            f"{host.resolve()}:/opt/cbrun-strip:ro",
        ]
        if gpus:
            argv.extend(["--gpus", gpus])
        argv.extend(
            [
                source_tag,
                "bash",
                "-lc",
                "CBRUN_DENYLIST_HASHES=/opt/cbrun-strip/denylist.hashes "
                "python3 /opt/cbrun-strip/strip_banned.py",
            ]
        )
        print(f"[cbrun] stripping banned artefacts from {source_tag}", flush=True)
        proc = subprocess.run(argv)
        if proc.returncode != 0:
            _remove_container(strip_name)
            raise RecipeLockError(
                f"denylist strip failed for {source_tag} (exit {proc.returncode})"
            )
        commit = subprocess.run(
            ["docker", "commit", "-c", "CMD [\"/bin/bash\"]", strip_name, dest_tag],
            capture_output=True,
            text=True,
        )
        _remove_container(strip_name)
        if commit.returncode != 0:
            raise RecipeLockError(f"docker commit failed: {commit.stderr.strip()}")
    if denylist.is_file():
        probe = probe_banned_imports(dest_tag, denylist)
        log_probe_result(probe)
        if probe.errors:
            subprocess.run(["docker", "rmi", "-f", dest_tag], capture_output=True, text=True)
            raise RecipeLockError("; ".join(probe.errors))


def _build_env_image(
    case_dir: Path,
    lock: dict[str, Any],
    runner: dict[str, Any],
    *,
    force: bool,
) -> str:
    if not docker_available():
        raise RecipeLockError("docker is unavailable")

    case_id = case_dir.name
    tag = env_recipe_tag(case_id)
    if not force and image_exists(tag):
        if _image_probe_clean(tag, case_dir):
            print(f"[cbrun] reusing env image {tag}", flush=True)
            return tag
        print(f"[cbrun] env image {tag} failed denylist probe; rebuilding", flush=True)
        force = True

    base_image = resolve_lock_base_image(lock)
    _ensure_base_image(base_image)

    install = str(runner.get("install_command") or "").strip()
    if not install or install.lower() == "true":
        raise RecipeLockError("runner.install_command is empty")

    container_name = f"z2r-recipe-env-{case_id}"
    gpus = _runner_docker_gpus(runner)
    argv = [
        "docker",
        "run",
        "--name",
        container_name,
        "--network",
        _docker_network(),
        *_registry_docker_env(),
    ]
    if gpus:
        argv.extend(["--gpus", gpus])
    argv.extend(_volume_mounts(case_dir))
    fetch = resource_fetch_command(case_dir)
    command = f"{fetch} && {install}" if fetch else install
    argv.extend([base_image, "bash", "-lc", command])

    retries = _env_build_retries()
    delay = _env_build_retry_delay_sec()
    last_output = ""
    for attempt in range(1, retries + 1):
        _remove_container(container_name)
        print(
            f"[cbrun] building env {tag} from {base_image} "
            f"(attempt {attempt}/{retries})",
            flush=True,
        )
        proc = subprocess.run(argv)
        if proc.returncode == 0:
            break
        last_output = f"exit {proc.returncode} (see streamed docker output above)"
        if attempt < retries:
            print(
                f"[cbrun] env install failed (attempt {attempt}); "
                f"retrying in {delay}s",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(delay)
    else:
        _remove_container(container_name)
        raise RecipeLockError(
            f"env-only install failed after {retries} attempts:\n{last_output}"
        )

    pre_tag = f"{tag}-prestrip"
    commit = subprocess.run(
        ["docker", "commit", container_name, pre_tag],
        capture_output=True,
        text=True,
    )
    _remove_container(container_name)
    if commit.returncode != 0:
        raise RecipeLockError(f"docker commit failed: {commit.stderr.strip()}")
    try:
        if _denylist_file(case_dir).is_file():
            _strip_env_image(
                source_tag=pre_tag,
                dest_tag=tag,
                case_dir=case_dir,
                case_id=case_id,
                gpus=gpus,
            )
        else:
            tag_proc = subprocess.run(
                ["docker", "tag", pre_tag, tag],
                capture_output=True,
                text=True,
            )
            if tag_proc.returncode != 0:
                raise RecipeLockError(f"docker tag failed: {tag_proc.stderr.strip()}")
    finally:
        subprocess.run(["docker", "rmi", "-f", pre_tag], capture_output=True, text=True)
    print(f"[cbrun] committed env image {tag}", flush=True)
    return tag


def _stage_deliverable(
    case_dir: Path,
    env_tag: str,
    *,
    force: bool,
) -> str:
    case_id = case_dir.name
    tag = deliverable_tag(case_id)
    if not force and image_exists(tag):
        print(f"[cbrun] reusing deliverable image {tag}", flush=True)
        return tag

    final_dir = case_dir / "milestones" / "final"
    container_name = f"z2r-recipe-deliverable-{case_id}"
    with stage_benchmark_bundle(case_dir, final_dir) as bundle:
        _remove_container(container_name)
        argv = [
            "docker",
            "run",
            "--name",
            container_name,
            "--network",
            _docker_network(),
            "-v",
            f"{bundle}:/src:ro",
            env_tag,
            "bash",
            "-lc",
            staging_shell_command(),
        ]
        print(f"[cbrun] staging deliverable {tag} from {env_tag}", flush=True)
        proc = subprocess.run(argv)
        if proc.returncode != 0:
            _remove_container(container_name)
            raise RecipeLockError(
                f"deliverable staging failed (exit {proc.returncode}; "
                "see streamed docker output above)"
            )
        commit = subprocess.run(
            [
                "docker", "commit",
                "-c", "WORKDIR /app",
                "-c", f"LABEL {FINGERPRINT_LABEL}={deliverable_fingerprint(case_dir)}",
                container_name, tag,
            ],
            capture_output=True,
            text=True,
        )
        _remove_container(container_name)
        if commit.returncode != 0:
            raise RecipeLockError(f"docker commit failed: {commit.stderr.strip()}")
    print(f"[cbrun] committed deliverable image {tag}", flush=True)
    return tag


def ensure_deliverable_image(
    case_dir: Path | str,
    *,
    force: bool = False,
) -> str:
    """Build or reuse ``codingbench-benchmark/<case>:deliverable``.

    Idempotent when ``force`` is false and the tag already exists.
    """
    case_dir = Path(case_dir).resolve()
    tag = deliverable_tag(case_dir.name)
    rebuild_env = force
    if not force and image_exists(tag):
        if not image_matches(tag, deliverable_fingerprint(case_dir)):
            # Public docs or hidden tests changed since staging; the env
            # image (recipe toolchain) is still reused when its own lock matches.
            print(f"[cbrun] deliverable image {tag} is stale; restaging", flush=True)
        elif _image_probe_clean(tag, case_dir):
            print(f"[cbrun] reusing deliverable image {tag}", flush=True)
            return tag
        else:
            print(
                f"[cbrun] deliverable image {tag} failed denylist probe; rebuilding",
                flush=True,
            )
            rebuild_env = True

    lock = load_lock(case_dir)
    validate_lock_env_install(lock)
    runner = resolve_lock_runner(lock, _load_manifest_runner(case_dir))
    env_tag = _build_env_image(case_dir, lock, runner, force=rebuild_env)
    return _stage_deliverable(case_dir, env_tag, force=True)


def deliverable_fingerprint(case_dir: Path) -> str:
    """Hash of everything staged into ``:deliverable`` on top of the env image."""
    case_dir = Path(case_dir).resolve()
    with stage_benchmark_bundle(case_dir, case_dir / "milestones" / "final") as bundle:
        staged = file_manifest(bundle)
    lock = recipe_lock_path(case_dir)
    return digest(
        {
            "staged": staged,
            "staging": staging_shell_command(),
            "lock": lock.read_text(encoding="utf-8") if lock.is_file() else None,
        }
    )
