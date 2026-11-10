# feature: F04
"""Helpers for the file-selection suites."""

from __future__ import annotations

from _helpers import lf_lines
import re
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

from _helpers import RunResult, hermetic_env
from F01_helpers import out_lines, tg

__all__ = [
    "parse_type_list",
    "IGNORE_ERROR_LINE",
    "DEFAULT_MAX_FILESIZE",
    "Selection",
    "ignore_reports",
]

#: Default cap on the size of a walked file, in bytes (64 MiB).
DEFAULT_MAX_FILESIZE = 64 * 1024 * 1024

#: Form of the report for one malformed ignore rule: a standard-error line
#: carrying the ignore file's path followed by ``: line <N>:`` where ``<N>``
#: is the 1-based line number of the rule in that file.
IGNORE_ERROR_LINE = re.compile(r"(?P<path>\S+): line (?P<line>[0-9]+):")

def parse_type_list(result: RunResult) -> List[tuple]:
    """Parse type-list output into ``[(name, [globs])]`` in printed order.

    Every line must have the form ``<name>: <glob>, <glob>, ...``; a line
    without the ``": "`` separator fails the test.
    """
    rows = []
    for line in out_lines(result):
        assert ": " in line, f"type-list line without 'name: globs' form: {line!r}"
        name, globs = line.split(": ", 1)
        rows.append((name, globs.split(", ")))
    return rows


class Selection:
    """Runs searches for one token in an isolated environment and reports which files matched.

    ``home`` becomes ``HOME`` (and the parent of ``XDG_CONFIG_HOME``), so no
    personal or system git configuration or global ignore file is visible
    unless the test writes one there.
    """

    def __init__(self, cwd, token: str, home, extra_env: Optional[Mapping[str, str]] = None):
        self.cwd = Path(cwd)
        self.token = token
        self.home = Path(home)
        self.env = hermetic_env(self.home, extra_env)

    def run(self, args: Sequence[str], cwd=None) -> RunResult:
        """Run the product with ``args`` verbatim in the isolated environment."""
        return tg(list(args), cwd=cwd or self.cwd, env=self.env)

    def files(self, *args: str, cwd=None, expect: str = "match") -> List[str]:
        """Return the sorted paths printed by a files-with-matches search for the token.

        ``args`` are extra options and path arguments.  The exit status must
        be the one named by ``expect`` (``match`` or ``no_match``); anything
        else fails with the run's streams, so a crashed run never reads as
        "no files".
        """
        result = self.run(["-l", self.token, *args], cwd=cwd)
        want = {"match": 0, "no_match": 1}[expect]
        assert result.code == want, f"expected exit {want} ({expect})\n{result.describe()}"
        return sorted(out_lines(result))


def ignore_reports(result: RunResult) -> List[tuple]:
    """Return ``[(path, line number)]`` for every malformed-rule report on standard error.

    Reads only lines of the form stated by :data:`IGNORE_ERROR_LINE`; other
    standard-error lines are not reports and are left alone.
    """
    found = []
    for line in lf_lines(result.err):
        m = IGNORE_ERROR_LINE.search(line)
        if m:
            found.append((m.group("path"), int(m.group("line"))))
    return found
