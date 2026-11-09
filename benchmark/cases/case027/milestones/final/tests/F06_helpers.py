# feature: F06
"""Helpers for the index-build suite.

Shell forms of ``trisift index`` (its success report, the buffer
confirmation, the files of a published index directory) and an independent
count of the files a build must index, computed from the fixture on disk
under the PRD's content rules, never from the product.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from _helpers import RunResult, run_trisift
from F05_helpers import BINARY_EXTENSIONS

__all__ = [
    "INDEX_DIR_NAME",
    "INDEX_FILES",
    "DEFAULT_SIZE_LIMIT",
    "BUILD_SUCCESS",
    "BUILD_REPORT",
    "BUFFER_CONFIRMATION",
    "build_index",
    "index_cmd",
    "build_report",
    "expected_indexed_count",
]

#: Default index directory name, directly inside the indexed root.
INDEX_DIR_NAME = ".trisift"

#: Files a published index directory holds.
INDEX_FILES = ("lookup.bin", "index.bin", "files.bin", "files-extra.bin", "meta.json", "filestamps.json")

#: Default file-size limit of a build and a search (64 MiB).
DEFAULT_SIZE_LIMIT = 64 * 1024 * 1024

# Independently delimited quantities. Report wording is free.
BUILD_SUCCESS = None
BUILD_REPORT = re.compile(r"(?<![\w.])(?P<secs>[0-9]+(?:\.[0-9]+)?)s\b")
BUILD_STRATEGY = re.compile(r"\b(?:(memory|external) strategy|strategy: (memory|external))\b")
BUILD_PEAK = re.compile(r"\bpeak memory:? (?P<peak>[0-9]+(?:\.[0-9]+)? ?(?:[KMGT]i?B|bytes|B))\b")


def assert_reported_directory(result, directory, *, warning=False):
    if warning:
        pattern = r"^warning: .*?\bat (.+?) - .+$"
    else:
        pattern = r"^Index\b.*?\bat (.+)$"
    fields = re.findall(pattern, result.err, re.MULTILINE)
    assert len(fields) == 1, result.describe()
    reported = Path(fields[0])
    if not reported.is_absolute():
        reported = Path(result.cwd) / reported
    assert reported.resolve() == Path(directory).resolve(), result.describe()

#: stderr confirmation of an explicitly given external buffer: carries
#: ``arena <MiB> MB``.
BUFFER_CONFIRMATION = re.compile(r"\barena (?P<mib>[0-9]+) MB\b")


def index_cmd(root, extra: Sequence[str] = (), index_path=None) -> List[str]:
    """Argument list of ``trisift index [--index-path P] <extra> <root>``."""
    args = ["index"]
    if index_path is not None:
        args += ["--index-path", os.fspath(index_path)]
    return args + list(extra) + [os.fspath(root)]


def build_index(root, extra: Sequence[str] = (), index_path=None, cwd=None, env=None) -> RunResult:
    """Run a build, assert it exits 0 and published ``lookup.bin``; return the run."""
    root = Path(root)
    r = run_trisift(index_cmd(root, extra, index_path), cwd=cwd or root, env=env)
    assert r.code == 0, f"index build failed\n{r.describe()}"
    idx = Path(index_path) if index_path is not None else root / INDEX_DIR_NAME
    assert (idx / "lookup.bin").is_file(), f"no lookup.bin in {idx}\n{r.describe()}"
    return r


def build_report(result: RunResult) -> dict:
    """Read the success report of a build from its stderr.

    Returns ``{secs, strategy, peak}`` (``peak`` may be ``None``).
    Reads declared fragments from the labelled report line; announcement wording is free.
    """
    reports = re.findall(r"^Indexed\b[^\n]*$", result.err, re.MULTILINE)
    assert len(reports) == 1, result.describe()
    report = reports[0]
    times = BUILD_REPORT.findall(report)
    assert len(times) == 1, result.describe()
    strategies = [a or b for a, b in BUILD_STRATEGY.findall(report)]
    assert len(strategies) == 1, result.describe()
    peak = BUILD_PEAK.search(report)
    return dict(secs=float(times[0]), strategy=strategies[0], peak=peak['peak'] if peak else None)


def _is_binary_ext(name: str) -> bool:
    if "." not in name:
        return False
    return name.rsplit(".", 1)[1].lower() in BINARY_EXTENSIONS


def expected_indexed_count(
    root,
    ignored: Iterable[str] = (),
    exclude: Iterable[str] = (),
    no_ignore: bool = False,
    max_filesize: Optional[int] = DEFAULT_SIZE_LIMIT,
    index_dir_name: str = INDEX_DIR_NAME,
) -> int:
    """Count the files a build of ``root`` must index, from the files on disk.

    Rules (FP-06.02/06.03): hidden files count; symlinks are not followed;
    ``ignored`` lists root-relative files or directories (``dir/``) the
    fixture's ignore rules exclude, and ``.git`` subtrees are excluded, both
    unless ``no_ignore``; directories named in ``exclude`` are skipped at
    any depth; files with a known binary extension, files with a NUL byte,
    and files over ``max_filesize`` bytes are not indexed.  The index
    directory itself is never counted.  A file whose first NUL lies beyond
    8 KiB is left to the implementer, so it is refused here.
    """
    base = Path(root)
    ign_files = {p for p in ignored if not p.endswith("/")}
    ign_dirs = {p.rstrip("/") for p in ignored if p.endswith("/")}
    excl = set(exclude)
    count = 0
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        rel_dir = os.path.relpath(dirpath, base)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        keep = []
        for d in dirnames:
            rel = f"{rel_dir}/{d}" if rel_dir else d
            if rel_dir == "" and d == index_dir_name:
                continue
            if os.path.islink(os.path.join(dirpath, d)) or d in excl:
                continue
            if not no_ignore and (d == ".git" or rel in ign_dirs):
                continue
            keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            full = os.path.join(dirpath, f)
            rel = f"{rel_dir}/{f}" if rel_dir else f
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            if not no_ignore and rel in ign_files:
                continue
            if _is_binary_ext(f):
                continue
            size = os.path.getsize(full)
            if max_filesize is not None and size > max_filesize:
                continue
            data = Path(full).read_bytes()
            nul = data.find(b"\0")
            if nul >= 8192:
                raise ValueError(f"fixture file {rel} has its first NUL beyond 8 KiB; its count is open")
            if nul >= 0:
                continue
            count += 1
    return count
