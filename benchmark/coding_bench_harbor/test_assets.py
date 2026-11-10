"""Hidden-test assets fetched from their official upstream URLs.

Hidden tests of some cases read large third-party files: release binaries,
Ubuntu packages, PyPI wheels, datasets, model weights. They are not committed.
``milestones/final/test_assets.json`` lists each one with its official URL,
SHA-256 and size, and whoever stages the hidden tests downloads it into the
staged copy at the listed path::

    {
      "assets": [
        {
          "path": "tests/assets/F01_pymupdf.whl",
          "url": "https://files.pythonhosted.org/packages/.../pymupdf-...whl",
          "sha256": "7777d0b7...",
          "size": 24115381
        }
      ]
    }

``path`` is relative to ``milestones/final``. The files land next to the hidden
tests, so a solving agent never sees them: the solve container does not
contain the hidden tests at all.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

__all__ = [
    "MANIFEST_NAME",
    "TestAsset",
    "TestAssetError",
    "download",
    "load",
    "materialize",
]

MANIFEST_NAME = "test_assets.json"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Release hosts (GitHub in particular) answer transient 5xx often enough that a
# few quick retries are not enough; back off up to about ten minutes in total.
_ATTEMPTS = 8
_BACKOFF_SECONDS = (5, 10, 20, 40, 80, 120, 180)


class TestAssetError(RuntimeError):
    """A test asset manifest is invalid or an asset cannot be fetched."""

    __test__ = False  # not a pytest test class


@dataclass(frozen=True)
class TestAsset:
    __test__ = False  # not a pytest test class

    path: str
    url: str
    sha256: str
    size: int


Fetcher = Callable[[TestAsset, Path], None]


def load(final_dir: Path | str) -> list[TestAsset]:
    """Assets declared by ``final_dir/test_assets.json``; empty when absent."""
    manifest = Path(final_dir) / MANIFEST_NAME
    if not manifest.is_file():
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TestAssetError(f"invalid JSON in {manifest}: {exc}") from exc
    items = data.get("assets") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise TestAssetError(f"{manifest}: 'assets' must be a non-empty list")
    assets: list[TestAsset] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise TestAssetError(f"{manifest}: each asset must be an object")
        path = str(item.get("path") or "")
        url = str(item.get("url") or "")
        sha256 = str(item.get("sha256") or "")
        size = item.get("size")
        pure = PurePosixPath(path)
        if not path or pure.is_absolute() or ".." in pure.parts or "\\" in path:
            raise TestAssetError(f"{manifest}: path must be relative inside the tests: {path!r}")
        if not url.startswith("https://"):
            raise TestAssetError(f"{manifest}: {path}: URL must use HTTPS: {url!r}")
        if not _SHA256.match(sha256):
            raise TestAssetError(f"{manifest}: {path}: sha256 must be 64 lowercase hex digits")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise TestAssetError(f"{manifest}: {path}: size must be a positive integer")
        if path in seen:
            raise TestAssetError(f"{manifest}: {path} is listed twice")
        seen.add(path)
        assets.append(TestAsset(path, url, sha256, size))
    return assets


def download(asset: TestAsset, target: Path) -> None:
    """Download *asset* from its URL into *target*, verifying size and SHA-256."""
    target.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for attempt in range(_ATTEMPTS):
        fd, tmp = tempfile.mkstemp(prefix=".asset-", dir=target.parent)
        try:
            digest = hashlib.sha256()
            count = 0
            request = urllib.request.Request(asset.url, headers={"User-Agent": "zero2repo-test-assets"})
            with os.fdopen(fd, "wb") as out, urllib.request.urlopen(request, timeout=120) as resp:
                while chunk := resp.read(1024 * 1024):
                    count += len(chunk)
                    if count > asset.size:
                        raise TestAssetError(
                            f"{asset.url}: more than the declared {asset.size} bytes"
                        )
                    digest.update(chunk)
                    out.write(chunk)
            if count != asset.size or digest.hexdigest() != asset.sha256:
                raise TestAssetError(
                    f"{asset.url}: got {count} bytes sha256 {digest.hexdigest()}, "
                    f"declared {asset.size} bytes sha256 {asset.sha256}"
                )
            os.replace(tmp, target)
            return
        except TestAssetError:
            raise
        except OSError as exc:  # network errors (URLError is an OSError) are retried
            last = exc
            if attempt < _ATTEMPTS - 1:
                time.sleep(_BACKOFF_SECONDS[attempt])
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    raise TestAssetError(f"{asset.url}: download failed after {_ATTEMPTS} attempts: {last}")


def materialize(final_dir: Path | str, dest_final_dir: Path | str, fetch: Fetcher = download) -> int:
    """Place every asset of ``final_dir`` under ``dest_final_dir``; return the count.

    A file already present at an asset's path is an error: the manifest, not a
    committed copy, is the single source of the asset.
    """
    dest = Path(dest_final_dir)
    assets = load(final_dir)
    for asset in assets:
        target = dest / asset.path
        if target.exists() or target.is_symlink():
            raise TestAssetError(
                f"{target}: a file already exists where test asset {asset.path} goes; "
                "remove the committed copy, the manifest is its source"
            )
        fetch(asset, target)
        print(f"[test-assets] {asset.path} ({asset.size} bytes) verified", flush=True)
    return len(assets)


def copy_from(path: Path, target: Path) -> None:
    """Copy an already verified local file to *target* (used by caches)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
