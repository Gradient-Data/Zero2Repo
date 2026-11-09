# feature: F08
"""Helpers for the file-listing and file-counting suite."""

from __future__ import annotations

import re

from _helpers import RunResult

__all__ = ["COUNT_REPORT", "MISSING_PATH", "parse_count_files"]

#: stderr report of ``count-files``:
#: ``<admitted> text files (<binary-ext> binary skipped, <too-large> too large, <errors> errors) in <ms>ms``.
COUNT_REPORT = {
    "admitted": re.compile(r"([0-9]+) text files\b"),
    "binary_ext": re.compile(r"([0-9]+) binary skipped\b"),
    "too_large": re.compile(r"([0-9]+) too large\b"),
    "errors": re.compile(r"([0-9]+) errors\b"),
    "elapsed_ms": re.compile(r"(?<![\w.])([0-9]+)ms\b"),
}

#: stderr line for a listing path argument that does not exist; carries the path.
MISSING_PATH = re.compile(r"^trisift: (?P<path>.+?): ")


def parse_count_files(result: RunResult) -> dict:
    """Read ``count-files`` output: stdout is one integer, stderr one report line.

    Returns ``{stdout_count, admitted, binary_ext, too_large, errors, elapsed_ms}``.
    Fails (never guesses) when either form is missing.
    """
    out = result.out
    assert re.fullmatch(r"[0-9]+\n", out), f"stdout is not one integer line\n{result.describe()}"
    parsed = {"stdout_count": int(out)}
    for key, rx in COUNT_REPORT.items():
        matches = rx.findall(result.err)
        assert len(matches) == 1, f"expected one {key} field: {result.describe()}"
        parsed[key] = float(matches[0]) if key == "elapsed_ms" else int(matches[0])
    return parsed
