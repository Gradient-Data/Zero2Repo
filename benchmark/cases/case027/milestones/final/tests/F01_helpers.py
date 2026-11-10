# feature: F01
"""Helpers for the plain-search suites (scan path).

Everything here reads the product only through its command line: the exit
status, standard output and standard error of one finished run.  The values
below are the product's shell (exit statuses, fixed labels); no expected
result of any search lives here.
"""

from __future__ import annotations

from _helpers import lf_lines
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from _helpers import RunResult, run_trisift, trisift_binary

__all__ = [
    "MATCH",
    "NO_MATCH",
    "ERROR",
    "REGEX_ERROR_LABEL",
    "STATS_SCAN_LABEL",
    "USAGE_LABEL",
    "tg",
    "resolve_binary",
    "assert_exit",
    "out_lines",
    "err_lines",
    "parse_match_lines",
    "file_blocks",
    "content_of",
]

#: Exit statuses of a search (ripgrep convention).
MATCH = 0
NO_MATCH = 1
ERROR = 2

_EXIT_NAMES = {"match": MATCH, "no_match": NO_MATCH, "error": ERROR}

#: Label that starts the diagnostic for a pattern that cannot be compiled.
REGEX_ERROR_LABEL = "regex error:"

#: Label of the statistics report line when a filesystem scan answered.
STATS_SCAN_LABEL = "Brute-force search completed"

#: Label that starts the usage text.
USAGE_LABEL = "Usage:"


def resolve_binary(binary=None) -> str:
    """Compatibility entry for the shared executable selection policy."""
    return trisift_binary(binary)


def tg(args: Sequence, cwd, env: Optional[Mapping[str, str]] = None, **kw) -> RunResult:
    """Run the product once with ``args`` in ``cwd`` and return its result.

    Thin alias of :func:`_helpers.run_trisift`; spawn failures and timeouts
    raise, the exit status is never interpreted here.
    """
    return run_trisift(list(args), cwd=cwd, env=env, **kw)


def assert_exit(result: RunResult, kind: str) -> None:
    """Assert ``result`` ended with the exit status named ``kind``.

    ``kind`` is one of ``match``, ``no_match``, ``error``.
    """
    want = _EXIT_NAMES[kind]
    assert result.code == want, f"expected exit {want} ({kind})\n{result.describe()}"


def out_lines(result: RunResult) -> List[str]:
    """Return standard output split into lines (strict UTF-8, ``\\n`` only).

    A non-empty output that does not end with a newline is a failure: every
    result line is newline-terminated.
    """
    text = result.out
    if text == "":
        return []
    assert text.endswith("\n"), f"stdout does not end with a newline\n{result.describe()}"
    return text[:-1].split("\n")


def err_lines(result: RunResult) -> List[str]:
    """Return standard error split into lines (strict UTF-8)."""
    return lf_lines(result.err)


def parse_match_lines(
    result: RunResult,
    paths: Iterable[str],
    sep: str = ":",
    ctx_sep: str = "-",
    group_sep: Optional[str] = None,
) -> List[dict]:
    """Split path-prefixed result lines into ``{path, kind, rest}`` records.

    ``paths`` are the printed paths the caller expects.  A line must start
    with one of them followed by ``sep`` (``kind`` = ``match``) or
    ``ctx_sep`` (``kind`` = ``context``); the longest path wins.  A line
    equal to ``group_sep`` yields ``{path: None, kind: 'separator'}``.  Any
    other line fails the test: nothing is guessed.
    """
    known = sorted(set(paths), key=len, reverse=True)
    records = []
    for line in out_lines(result):
        if group_sep is not None and line == group_sep:
            records.append({"path": None, "kind": "separator", "rest": ""})
            continue
        for p in known:
            if line.startswith(p + sep):
                records.append({"path": p, "kind": "match", "rest": line[len(p) + len(sep):]})
                break
            if line.startswith(p + ctx_sep):
                records.append({"path": p, "kind": "context", "rest": line[len(p) + len(ctx_sep):]})
                break
        else:
            raise AssertionError(
                f"result line {line!r} does not start with any expected path {known!r}\n"
                f"{result.describe()}"
            )
    return records


def file_blocks(records: Sequence[dict]) -> Dict[str, List[str]]:
    """Group parsed records by path, keeping each file's line order.

    Separator records are dropped.  Use it to compare multi-file output when
    the order of files is not fixed by a sort option.
    """
    blocks: Dict[str, List[str]] = {}
    for rec in records:
        if rec["path"] is None:
            continue
        blocks.setdefault(rec["path"], []).append(rec["rest"])
    return blocks


def content_of(result: RunResult, paths: Iterable[str]) -> Dict[str, List[str]]:
    """Shorthand: ``file_blocks(parse_match_lines(result, paths))``."""
    return file_blocks(parse_match_lines(result, paths))
