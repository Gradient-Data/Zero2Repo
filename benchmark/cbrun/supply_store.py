"""Host-wide content-addressed store for files a full-suite run downloads.

Every file lives under ``blobs/sha256/<2>/<hex>`` and is named by its SHA-256.
A write goes to a temporary file first and is renamed into place only after
its size and digest match, so a reader never sees a partial file. Blobs are
never rewritten, so a read checks only that the file is there at its size.

Several cbrun processes share one store. Work on one key (a digest or a URL)
is serialized by an ``flock`` under ``locks/``: the first process downloads,
the others wait and then find the file present. The kernel drops the lock
when its holder dies.

Files a solve fetches without a known digest are remembered by request key
under ``urls/`` so the next request for the same URL is served locally.

Nothing is ever deleted automatically. :func:`disk_usage` reports the size.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

STORE_ENV = "CBRUN_STORE_DIR"
DEFAULT_STORE_DIR = Path("/data/cbrun-store")

__all__ = [
    "STORE_ENV",
    "DEFAULT_STORE_DIR",
    "Blob",
    "Store",
    "StoreError",
    "default_store",
]


class StoreError(RuntimeError):
    """A stored file is missing, corrupt, or cannot be written."""


@dataclass(frozen=True)
class Blob:
    sha256: str
    size: int


_HEX = re.compile(r"[0-9a-f]{64}")


class Store:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        try:
            for sub in ("blobs/sha256", "tmp", "locks", "urls", "ca"):
                _mkdir_shared(self.root / sub)
        except OSError as exc:
            raise StoreError(
                f"cannot create the local store at {self.root}: {exc}. "
                f"Set {STORE_ENV} to a writable directory."
            ) from exc

    # Paths -----------------------------------------------------------------

    def blob_path(self, sha256: str) -> Path:
        if not _HEX.fullmatch(sha256):
            raise StoreError(f"invalid sha256 {sha256!r}")
        return self.root / "blobs" / "sha256" / sha256[:2] / sha256

    def has(self, sha256: str, size: int | None = None) -> bool:
        path = self.blob_path(sha256)
        if not path.is_file():
            return False
        return size is None or path.stat().st_size == size

    # Locks -----------------------------------------------------------------

    @contextmanager
    def lock(self, key: str) -> Iterator[None]:
        """Hold the host-wide lock for *key* (a digest or a URL)."""
        name = hashlib.sha256(key.encode()).hexdigest()
        path = self.root / "locks" / f"{name}.lock"
        with open(path, "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    # Writes ----------------------------------------------------------------

    @contextmanager
    def writer(
        self,
        *,
        expect_sha256: str | None = None,
        expect_size: int | None = None,
        label: str = "",
    ) -> Iterator["BlobWriter"]:
        """Write a new blob. It is renamed into place only if the digest checks out."""
        fd, tmp_name = tempfile.mkstemp(dir=self.root / "tmp", prefix="part-")
        tmp = Path(tmp_name)
        writer = BlobWriter(os.fdopen(fd, "wb"))
        try:
            yield writer
            writer.handle.close()
            blob = Blob(writer.digest.hexdigest(), writer.size)
            if expect_size is not None and blob.size != expect_size:
                raise StoreError(
                    f"{label or 'download'}: size {blob.size} does not match the "
                    f"expected {expect_size}"
                )
            if expect_sha256 is not None and blob.sha256 != expect_sha256:
                raise StoreError(
                    f"{label or 'download'}: sha256 {blob.sha256} does not match the "
                    f"expected {expect_sha256}"
                )
            dest = self.blob_path(blob.sha256)
            _mkdir_shared(dest.parent)
            os.chmod(tmp, 0o664)
            os.replace(tmp, dest)
            writer.blob = blob
        finally:
            if not writer.handle.closed:
                writer.handle.close()
            tmp.unlink(missing_ok=True)

    # Reads -----------------------------------------------------------------

    def stored_path(self, sha256: str, size: int | None, *, label: str = "") -> Path:
        """Return the blob path; raise naming what is wrong if it is missing or resized."""
        path = self.blob_path(sha256)
        what = label or sha256
        if not path.is_file():
            raise StoreError(f"{what}: not in the local store ({path})")
        actual_size = path.stat().st_size
        if size is not None and actual_size != size:
            raise StoreError(
                f"{what}: stored file {path} has size {actual_size}, expected {size}"
            )
        return path

    # URL index (solve-time cache) ------------------------------------------

    def _url_record(self, key: str) -> Path:
        return self.root / "urls" / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def lookup_url(self, key: str) -> dict | None:
        path = self._url_record(key)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def remember_url(self, key: str, record: dict) -> None:
        path = self._url_record(key)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
        os.chmod(tmp, 0o664)
        os.replace(tmp, path)

    def disk_usage(self) -> int:
        total = 0
        for dirpath, _dirs, names in os.walk(self.root / "blobs"):
            for name in names:
                try:
                    total += (Path(dirpath) / name).stat().st_size
                except OSError:
                    pass
        return total


class BlobWriter:
    def __init__(self, handle: BinaryIO) -> None:
        self.handle = handle
        self.digest = hashlib.sha256()
        self.size = 0
        self.blob: Blob | None = None

    def write(self, data: bytes) -> None:
        self.handle.write(data)
        self.digest.update(data)
        self.size += len(data)


def _mkdir_shared(path: Path) -> None:
    """Create *path* group-writable so every user on the host can share it."""
    if path.is_dir():
        return
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o2775)
    except PermissionError:
        pass


def default_store(environ: dict[str, str] | None = None) -> Store:
    environ = os.environ if environ is None else environ
    raw = (environ.get(STORE_ENV) or "").strip()
    return Store(Path(raw).expanduser() if raw else DEFAULT_STORE_DIR)


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TiB"
