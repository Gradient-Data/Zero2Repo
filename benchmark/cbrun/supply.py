"""Supply manifest, locks, and the preparation phase of a full-suite run.

Only a full-suite run (``cbrun --all``) uses this module. A run on selected
cases leaves it inactive and every build downloads directly, as before.

One manifest (``benchmark/supply/manifest.json``) has three sections:

``base``
    The shared toolchain image: its public system image and the fixed-URL
    files its Dockerfile downloads.
``cases``
    One entry per case. ``files`` lists the fixed-URL downloads its install
    command makes (Go, Zig, another Node) with their checksums. A case that
    ships ``source/env/resources.json`` adds those files automatically.
``harnesses``
    One entry per built-in harness: its package, the versions allowed, and the
    fixed-URL files its install downloads (the private Node). A run takes the
    entry of the harness it selected at its pinned version.

Packages installed by name (apt, pip, npm, conda) are resolved by recording
the real install once, through the proxy in ``record`` mode: every reply,
index files included, is stored and listed in a lock under
``benchmark/supply/locks/``. Later builds replay that lock read-only. A lock
also carries a digest of the inputs it was recorded from, so editing an
install command without regenerating its lock is an error.

Generate locks with ``python -m cbrun.supply lock base|case <id>...|harness
<name>...``.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from .supply_proxy import Entry, ProxyHub, ProxySession, SupplyViolation, is_fixed_content, iter_body
from .supply_store import Store, StoreError, default_store, format_size

__all__ = [
    "CA_FETCH_SNIPPET",
    "Lock",
    "SupplyError",
    "SupplyRun",
    "activate",
    "active",
    "deactivate",
    "load_manifest",
]

SUPPLY_DIR = Path(__file__).resolve().parents[1] / "supply"
MANIFEST_PATH = SUPPLY_DIR / "manifest.json"
LOCKS_DIR = SUPPLY_DIR / "locks"
DOWNLOAD_WORKERS = 8

# Image builds fetch the proxy's CA from the proxy itself, so the certificate
# reaches the build without being part of the Dockerfile or the image. With no
# proxy configured (a run on selected cases) the step does nothing. The text is
# the same in both cases, so an image's fingerprint does not depend on the mode.
_BUILD_CA = "/tmp/cbrun-ca-bundle.pem"
CA_FETCH_SNIPPET = (
    'if [ -n "${https_proxy:-}" ]; then '
    f"trap 'rm -f {_BUILD_CA}' EXIT; "
    f"curl -fsS --max-time 30 http://cbrun-proxy.invalid/ca-bundle.pem -o {_BUILD_CA}; "
    f"export SSL_CERT_FILE={_BUILD_CA} REQUESTS_CA_BUNDLE={_BUILD_CA} "
    f"CURL_CA_BUNDLE={_BUILD_CA} PIP_CERT={_BUILD_CA} NODE_EXTRA_CA_CERTS={_BUILD_CA} "
    f"CONDA_SSL_VERIFY={_BUILD_CA}; "
    "fi"
)


class SupplyError(RuntimeError):
    """The manifest or a lock is missing, stale, or cannot be satisfied."""


# Manifest -----------------------------------------------------------------


@dataclass(frozen=True)
class DeclaredFile:
    url: str
    sha256: str
    size: int | None = None


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise SupplyError(f"supply manifest missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SupplyError(f"invalid supply manifest {path}: {exc}") from exc
    for key in ("base", "cases", "harnesses"):
        if not isinstance(data.get(key), dict):
            raise SupplyError(f"supply manifest {path}: section {key!r} must be an object")
    return data


def _declared(items: Any, where: str) -> list[DeclaredFile]:
    out = []
    for item in items or []:
        if not isinstance(item, dict) or not item.get("url") or not item.get("sha256"):
            raise SupplyError(f"{where}: each file needs url and sha256")
        size = item.get("size")
        out.append(DeclaredFile(str(item["url"]), str(item["sha256"]), int(size) if size else None))
    return out


def base_files(manifest: dict[str, Any]) -> list[DeclaredFile]:
    return _declared(manifest["base"].get("files"), "manifest base")


def case_files(manifest: dict[str, Any], case_dir: Path) -> list[DeclaredFile]:
    """Fixed-URL files of a case: its manifest entry plus its resource file."""
    entry = manifest["cases"].get(case_dir.name)
    if not isinstance(entry, dict):
        raise SupplyError(f"{case_dir.name}: no entry in the supply manifest ({MANIFEST_PATH})")
    files = _declared(entry.get("files"), f"manifest case {case_dir.name}")
    resources = case_dir / "source" / "env" / "resources.json"
    if resources.is_file():
        data = json.loads(resources.read_text(encoding="utf-8"))
        files += _declared(data.get("resources"), str(resources))
    return files


def harness_entry(manifest: dict[str, Any], backend: str, version: str) -> dict[str, Any]:
    entry = manifest["harnesses"].get(backend)
    if not isinstance(entry, dict):
        raise SupplyError(f"harness {backend}: no entry in the supply manifest ({MANIFEST_PATH})")
    versions = [str(v) for v in entry.get("versions") or []]
    if version not in versions:
        raise SupplyError(
            f"harness {backend}: version {version} is not listed in the supply manifest "
            f"(listed: {', '.join(versions) or 'none'}); add it and generate its lock"
        )
    return entry


# Locks --------------------------------------------------------------------


@dataclass(frozen=True)
class Lock:
    segment: str
    name: str
    inputs_digest: str
    entries: tuple[Entry, ...]
    from_image: str | None = None

    @property
    def label(self) -> str:
        return f"{self.segment} {self.name}"


def lock_path(segment: str, name: str) -> Path:
    if segment == "base":
        return LOCKS_DIR / "base.json"
    if segment == "case":
        return LOCKS_DIR / "cases" / f"{name}.json"
    if segment == "harness":
        return LOCKS_DIR / "harnesses" / f"{name}.json"
    raise ValueError(segment)


def read_lock(segment: str, name: str) -> Lock | None:
    path = lock_path(segment, name)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Lock(
        segment=segment,
        name=name,
        inputs_digest=str(data["inputs_digest"]),
        entries=tuple(Entry.from_dict(item) for item in data["entries"]),
        from_image=data.get("from_image"),
    )


def require_lock(segment: str, name: str, inputs_digest: str) -> Lock:
    lock = read_lock(segment, name)
    command = {"base": "lock base", "case": f"lock case {name}", "harness": f"lock harness {name}"}
    hint = f"run: python -m cbrun.supply {command[segment]}"
    if lock is None:
        raise SupplyError(f"{segment} {name}: no supply lock at {lock_path(segment, name)}; {hint}")
    if lock.inputs_digest != inputs_digest:
        raise SupplyError(
            f"{segment} {name}: supply lock {lock_path(segment, name)} was recorded from "
            f"different install inputs; {hint}"
        )
    return lock


def write_lock(lock: Lock, *, recorded_from: str, recorded_on: str | None = None) -> Path:
    path = lock_path(lock.segment, lock.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = sorted(lock.entries, key=lambda e: (e.url, e.accept))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "segment": lock.segment,
        "name": lock.name,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "recorded_from": recorded_from,
        "inputs_digest": lock.inputs_digest,
    }
    if lock.from_image:
        payload["from_image"] = lock.from_image
    if recorded_on:
        # The image the install ran on. A replay on a base whose sources
        # differ asks for URLs outside the lock and fails naming them.
        payload["recorded_on"] = recorded_on
    # Readable summary of what was installed; the entries are authoritative.
    payload["files"] = sorted(
        {
            PurePosixPath(urlsplit(e.url).path).name
            for e in entries
            if e.status == 200 and is_fixed_content(urlsplit(e.url).hostname or "", urlsplit(e.url).path)
        }
    )
    payload["entries"] = [e.to_dict() for e in entries]
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def _digest(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def base_inputs_digest() -> str:
    from .recipe_image import BASE_IMAGE_DOCKERFILE_DIR

    return _digest((BASE_IMAGE_DOCKERFILE_DIR / "Dockerfile").read_text(encoding="utf-8"))


def case_inputs_digest(case_dir: Path) -> str:
    from .recipe import RecipeLockError, load_lock, resolve_lock_runner
    from .recipe_image import _load_manifest_runner, resource_fetch_command

    try:
        runner = resolve_lock_runner(load_lock(case_dir), _load_manifest_runner(case_dir))
    except RecipeLockError as exc:
        raise SupplyError(f"{case_dir.name}: {exc}") from exc
    resources = case_dir / "source" / "env" / "resources.json"
    return _digest(
        str(runner.get("install_command") or ""),
        resource_fetch_command(case_dir),
        resources.read_text(encoding="utf-8") if resources.is_file() else "",
    )


def harness_version(backend: str, environ: dict[str, str]) -> str:
    from .agents import cli_version_spec

    return cli_version_spec(backend, environ).lstrip("@")


def harness_inputs_digest(backend: str, environ: dict[str, str]) -> str:
    from .images import harness_install_steps

    return _digest(harness_install_steps(backend, environ))


def harness_lock_name(backend: str, environ: dict[str, str]) -> str:
    return f"{backend}-{harness_version(backend, environ)}"


# Host-side download --------------------------------------------------------


def fetch_entry(store: Store, entry: Entry, hub: ProxyHub) -> bool:
    """Make *entry*'s body present and verified in *store*; True if it was downloaded."""
    with store.lock(entry.sha256):
        if store.has(entry.sha256, entry.size):
            return False
        parts = urlsplit(entry.url)
        tls = parts.scheme == "https"
        host = parts.hostname or ""
        port = parts.port or (443 if tls else 80)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        connect = hub.connect

        class Upstream(http.client.HTTPConnection):
            def connect(self) -> None:  # noqa: D401 - http.client hook
                self.sock = connect(host, port, tls)
                self.sock.settimeout(self.timeout)

        last: Exception | None = None
        for attempt in range(3):
            conn = Upstream(host, port, timeout=300)
            try:
                conn.putrequest("GET", path, skip_accept_encoding=True)
                if entry.accept:
                    conn.putheader("Accept", entry.accept)
                conn.putheader("Accept-Encoding", "identity")
                conn.endheaders()
                resp = conn.getresponse()
                if resp.status != entry.status:
                    raise StoreError(
                        f"{entry.url}: upstream answered {resp.status}, the lock recorded "
                        f"{entry.status}"
                    )
                with store.writer(
                    expect_sha256=entry.sha256, expect_size=entry.size, label=entry.url
                ) as writer:
                    for data in iter_body(resp, 1024 * 1024):
                        writer.write(data)
                return True
            except StoreError as exc:
                raise StoreError(
                    f"{exc}. The upstream content differs from the lock: copy the store "
                    "from the host that recorded it, or regenerate the lock"
                ) from exc
            except OSError as exc:  # a dropped or cut-off download is retried
                last = exc
                time.sleep(2 * (attempt + 1))
            finally:
                conn.close()
        raise StoreError(f"{entry.url}: download failed: {last}")


def _fetch_all(store: Store, hub: ProxyHub, entries: Iterable[Entry]) -> tuple[int, list[str]]:
    unique: dict[str, Entry] = {}
    for entry in entries:
        unique.setdefault(entry.sha256, entry)
    errors: list[str] = []
    fetched = 0
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        futures = {pool.submit(fetch_entry, store, e, hub): e for e in unique.values()}
        for future, entry in futures.items():
            try:
                fetched += int(future.result())
            except (StoreError, OSError) as exc:
                errors.append(str(exc))
    return fetched, errors


# The active run -------------------------------------------------------------


class SupplyRun:
    """Supply state of one full-suite run: manifest, store, proxy."""

    def __init__(
        self,
        *,
        environ: dict[str, str] | None = None,
        store: Store | None = None,
        hub: ProxyHub | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        self.environ = dict(os.environ if environ is None else environ)
        self.store = store or default_store(self.environ)
        self.hub = hub or ProxyHub(self.store)
        self.manifest = manifest if manifest is not None else load_manifest()

    # Locks for each build ----------------------------------------------------

    def base_lock(self) -> Lock:
        return require_lock("base", "base", base_inputs_digest())

    def case_lock(self, case_dir: Path) -> Lock:
        case_files(self.manifest, case_dir)  # the case must have a manifest entry
        return require_lock("case", case_dir.name, case_inputs_digest(case_dir))

    def harness_lock(self, backend: str) -> Lock:
        version = harness_version(backend, self.environ)
        harness_entry(self.manifest, backend, version)
        return require_lock(
            "harness", f"{backend}-{version}", harness_inputs_digest(backend, self.environ)
        )

    def base_from_image(self) -> str:
        lock = self.base_lock()
        if not lock.from_image:
            raise SupplyError(f"base lock {lock_path('base', 'base')} has no from_image")
        return lock.from_image

    @contextmanager
    def locked(self, owner: str, entries: Iterable[Entry] = ()) -> Iterator[ProxySession]:
        """Read-only proxy session; raises after the block if anything was refused."""
        session = self.hub.session("locked", owner, entries=entries)
        try:
            yield session
        finally:
            session.close()
        session.raise_for_violations()

    # Preparation -------------------------------------------------------------

    def prepare(self, case_dirs: list[Path], backends: list[str], *, force: bool = False) -> None:
        """Download what this run will install, building the base image alongside.

        Only what will actually be built is prepared: the base image when it is
        missing, cases whose environment image is missing (all with *force*),
        and the selected harnesses whose shared image is missing. Every problem
        with the manifest or a lock is reported together before any download.
        """
        from .docker_env import image_exists
        from .images import agent_tag, cli_image_tag
        from .agents import NPM_BACKENDS
        from .recipe import env_recipe_tag

        started = time.monotonic()
        problems: list[str] = []
        case_locks: list[Lock] = []
        for case_dir in case_dirs:
            if not force and image_exists(env_recipe_tag(case_dir.name)):
                continue
            try:
                case_locks.append(self.case_lock(case_dir))
            except (SupplyError, OSError, ValueError) as exc:
                problems.append(str(exc))
        harness_locks: list[Lock] = []
        npm_images = False
        for backend in dict.fromkeys(backends):
            try:
                if backend in NPM_BACKENDS:
                    if not force and image_exists(cli_image_tag(backend, self.environ)):
                        continue
                    harness_locks.append(self.harness_lock(backend))
                    npm_images = True
                elif backend == "cursor":
                    # Cursor installs into each case's agent image.
                    if force or any(
                        not image_exists(agent_tag(case_dir.name, backend)) for case_dir in case_dirs
                    ):
                        harness_locks.append(self.harness_lock(backend))
            except (SupplyError, RuntimeError) as exc:
                problems.append(str(exc))
        base_tag = str(self.manifest["base"].get("image") or "")
        if not base_tag:
            problems.append("supply manifest base.image is empty")
        need_base = bool(base_tag) and not image_exists(base_tag) and bool(case_locks)
        base_lock = None
        if need_base or npm_images:
            # A shared CLI image is built FROM the system image the base lock pins.
            try:
                lock = self.base_lock()
                if need_base:
                    base_lock = lock
            except SupplyError as exc:
                problems.append(str(exc))
        if problems:
            raise SupplyError("supply preparation cannot start:\n  " + "\n  ".join(problems))

        errors: list[str] = []
        fetched = 0
        base_thread = None
        base_error: list[BaseException] = []
        if base_lock is not None:
            print(f"[cbrun] supply: fetching {len(base_lock.entries)} base image files", file=sys.stderr)
            count, errs = _fetch_all(self.store, self.hub, base_lock.entries)
            fetched += count
            if errs:
                raise SupplyError("base image files:\n  " + "\n  ".join(errs))

            def build_base() -> None:
                from .recipe_image import _ensure_base_image

                try:
                    _ensure_base_image(base_tag)
                except BaseException as exc:  # noqa: BLE001 - reported after the join
                    base_error.append(exc)

            print(f"[cbrun] supply: building {base_tag} while the other files download",
                  file=sys.stderr)
            base_thread = threading.Thread(target=build_base, name="supply-base-build")
            base_thread.start()
        others = [e for lock in case_locks + harness_locks for e in lock.entries]
        if others:
            print(
                f"[cbrun] supply: fetching files for {len(case_locks)} case(s) and "
                f"{len(harness_locks)} harness(es)",
                file=sys.stderr,
            )
            count, errs = _fetch_all(self.store, self.hub, others)
            fetched += count
            errors += errs
        if base_thread is not None:
            base_thread.join()
            if base_error:
                errors.append(f"base image {base_tag}: {base_error[0]}")
        print(
            f"[cbrun] supply: ready in {time.monotonic() - started:.0f}s; downloaded "
            f"{fetched} file(s); local store {self.store.root} holds "
            f"{format_size(self.store.disk_usage())}",
            file=sys.stderr,
        )
        if errors:
            raise SupplyError("supply preparation failed:\n  " + "\n  ".join(errors))


_ACTIVE: SupplyRun | None = None


def activate(run: SupplyRun) -> SupplyRun:
    global _ACTIVE
    _ACTIVE = run
    return run


def deactivate() -> None:
    global _ACTIVE
    _ACTIVE = None


def active() -> SupplyRun | None:
    """The supply of this process's full-suite run, or None outside one."""
    return _ACTIVE


# Lock generation ----------------------------------------------------------


def _check_declared(session: ProxySession, declared: list[DeclaredFile]) -> list[str]:
    """Compare each declared file with what the install actually received.

    A declared URL may answer with a redirect (go.dev/dl hands out the file
    from another host); the file is the end of the recorded redirect chain.
    """
    from urllib.parse import urljoin

    problems = []
    recorded = {e.url: e for e in session.recorded.values()}
    for item in declared:
        entry = recorded.get(item.url)
        for _hop in range(10):
            if entry is None or not (300 <= entry.status < 400 and entry.headers.get("location")):
                break
            entry = recorded.get(urljoin(entry.url, entry.headers["location"]))
        if entry is None:
            continue
        if entry.sha256 != item.sha256 or (item.size is not None and entry.size != item.size):
            problems.append(
                f"{item.url}: recorded sha256 {entry.sha256} size {entry.size} does not "
                f"match the declared sha256 {item.sha256}"
                + (f" size {item.size}" if item.size is not None else "")
            )
    return problems


def _finish_record(
    session: ProxySession,
    declared: list[DeclaredFile],
    lock: Lock,
    recorded_from: str,
    recorded_on: str | None = None,
) -> Path:
    problems = list(dict.fromkeys(session.violations)) + _check_declared(session, declared)
    if problems:
        raise SupplyError(f"{lock.label}: recording failed:\n  " + "\n  ".join(problems))
    if not session.recorded:
        raise SupplyError(f"{lock.label}: the install made no requests through the proxy")
    path = write_lock(
        Lock(lock.segment, lock.name, lock.inputs_digest, tuple(session.recorded.values()),
             lock.from_image),
        recorded_from=recorded_from,
        recorded_on=recorded_on,
    )
    print(f"[cbrun] wrote {path} ({len(session.recorded)} entries)", file=sys.stderr)
    return path


def _docker(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *argv], capture_output=True, text=True)


def _pinned_public_image(ref: str) -> str:
    pull = subprocess.run(["docker", "pull", ref])
    if pull.returncode != 0:
        raise SupplyError(f"docker pull {ref} failed (exit {pull.returncode})")
    inspect = _docker("image", "inspect", "--format", "{{json .RepoDigests}}", ref)
    if inspect.returncode != 0:
        raise SupplyError(f"docker image inspect {ref} failed: {inspect.stderr.strip()}")
    repo = ref.split(":", 1)[0]
    for digest_ref in json.loads(inspect.stdout or "[]"):
        name, _, digest = digest_ref.partition("@")
        if name.split("/")[-1] == repo.split("/")[-1] and digest:
            return f"{ref}@{digest}"
    raise SupplyError(f"{ref} has no registry digest after pull")


def record_base(run: SupplyRun) -> Path:
    from .recipe_image import BASE_IMAGE_DOCKERFILE_DIR

    base = run.manifest["base"]
    public = str(base.get("from") or "")
    tag = str(base.get("image") or "")
    if not public or not tag:
        raise SupplyError("supply manifest base needs 'from' and 'image'")
    from_image = _pinned_public_image(public)
    scratch = f"{tag}-supply-record"
    declared = base_files(run.manifest)
    session = run.hub.session(
        "record", "base", declared_urls=[f.url for f in declared]
    )
    try:
        proc = subprocess.run(
            [
                "docker", "build", *session.build_args(),
                "--build-arg", f"FROM_IMAGE={from_image}",
                "-t", scratch, str(BASE_IMAGE_DOCKERFILE_DIR),
            ]
        )
    finally:
        session.close()
    if proc.returncode != 0:
        raise SupplyError(f"base image build while recording failed (exit {proc.returncode})")
    lock = Lock("base", "base", base_inputs_digest(), (), from_image)
    path = _finish_record(session, declared, lock, f"docker build of {BASE_IMAGE_DOCKERFILE_DIR}")
    _adopt_or_drop(scratch, tag)
    return path


def record_case(run: SupplyRun, case_dir: Path) -> Path:
    from .docker_env import image_exists
    from .recipe import load_lock, resolve_lock_base_image, resolve_lock_runner
    from .recipe_image import _env_install_argv, _load_manifest_runner, _remove_container

    lock_data = load_lock(case_dir)
    base_image = resolve_lock_base_image(lock_data)
    if not image_exists(base_image):
        raise SupplyError(f"{case_dir.name}: base image {base_image} is missing; build it first")
    runner = resolve_lock_runner(lock_data, _load_manifest_runner(case_dir))
    declared = case_files(run.manifest, case_dir)
    name = f"z2r-supply-record-{case_dir.name}"
    session = run.hub.session(
        "record", case_dir.name, declared_urls=[f.url for f in declared]
    )
    try:
        _remove_container(name)
        argv = _env_install_argv(case_dir, base_image, runner, name, session)
        proc = subprocess.run(argv)
    finally:
        _remove_container(name)
        session.close()
    if proc.returncode != 0:
        raise SupplyError(f"{case_dir.name}: install while recording failed (exit {proc.returncode})")
    from .state import image_identity

    lock = Lock("case", case_dir.name, case_inputs_digest(case_dir), ())
    base_id = image_identity(base_image)["id"]
    return _finish_record(
        session, declared, lock, f"install_command of {case_dir.name}", f"{base_image} {base_id}"
    )


def record_harness(run: SupplyRun, backend: str) -> Path:
    from .images import harness_record_dockerfile

    version = harness_version(backend, run.environ)
    harness_entry(run.manifest, backend, version)
    from_image = run.base_from_image()
    name = f"{backend}-{version}"
    scratch = f"codingbench-cli/{backend}:{version}-supply-record"
    declared = _declared(harness_entry(run.manifest, backend, version).get("files"), f"manifest harness {backend}")
    session = run.hub.session("record", f"harness {name}", declared_urls=[f.url for f in declared])
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as ctx:
            (Path(ctx) / "Dockerfile").write_text(
                harness_record_dockerfile(backend, run.environ, from_image), encoding="utf-8"
            )
            proc = subprocess.run(
                ["docker", "build", *session.build_args(), "--no-cache", "-t", scratch, ctx]
            )
    finally:
        session.close()
    if proc.returncode != 0:
        raise SupplyError(f"harness {name}: install while recording failed (exit {proc.returncode})")
    lock = Lock("harness", name, harness_inputs_digest(backend, run.environ), ())
    path = _finish_record(session, declared, lock, f"shared CLI install of {backend} {version}")
    _docker("rmi", "-f", scratch)
    return path


def _adopt_or_drop(scratch: str, tag: str) -> None:
    from .docker_env import image_exists

    if not image_exists(tag):
        _docker("tag", scratch, tag)
        print(f"[cbrun] tagged the recorded build as {tag}", file=sys.stderr)
    _docker("rmi", scratch)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m cbrun.supply",
        description="Generate supply locks by recording a real install through the proxy.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    lock = sub.add_parser("lock", help="Record a lock.")
    lock.add_argument("segment", choices=("base", "case", "harness"))
    lock.add_argument("names", nargs="*", help="Case ids or harness names.")
    lock.add_argument("--cases-root", type=Path, default=SUPPLY_DIR.parent / "cases")
    args = parser.parse_args(argv)

    run = SupplyRun()
    try:
        if args.segment == "base":
            record_base(run)
        elif args.segment == "case":
            if not args.names:
                parser.error("lock case needs case ids")
            for name in args.names:
                record_case(run, args.cases_root / name)
        else:
            if not args.names:
                parser.error("lock harness needs harness names")
            for name in args.names:
                record_harness(run, name)
    except (SupplyError, SupplyViolation, StoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"[cbrun] local store {run.store.root} holds {format_size(run.store.disk_usage())}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
