# feature: F02
"""Helpers for the pattern-matching suites: one-file fixtures and line sets."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Sequence

from _helpers import RunResult
from F01_helpers import out_lines, tg

__all__ = ["write_lines", "selected", "sha256_of"]


def write_lines(path, lines: Sequence[str]) -> Path:
    """Write ``lines`` to ``path`` as UTF-8, each terminated by ``\\n``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes("".join(line + "\n" for line in lines).encode("utf-8"))
    return p


def selected(args: Sequence, cwd, expect: str = "match") -> List[str]:
    """Run a search over one named file and return the printed lines.

    ``args`` must name exactly one file, so lines carry no path prefix.
    The exit status must be the one named by ``expect`` (``match`` or
    ``no_match``); any other status fails with the run's streams.
    """
    result: RunResult = tg(args, cwd=cwd)
    want = {"match": 0, "no_match": 1}[expect]
    assert result.code == want, f"expected exit {want} ({expect})\n{result.describe()}"
    return out_lines(result)


def sha256_of(path) -> str:
    """Return the hex SHA-256 of the file's bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
