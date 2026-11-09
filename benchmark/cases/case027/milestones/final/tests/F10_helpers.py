# feature: F10
"""Helpers for the ``trisift status`` suites.

The status report on standard output is a header line followed by labelled
field lines ``  <Label>: <value>``.  This module reads exactly those stated
labels and the stated value forms; it never scrapes free text.
"""

from __future__ import annotations

from _helpers import lf_lines
import re
from typing import Dict, Optional

from _helpers import RunResult, run_trisift

__all__ = [
    "SERVER_HEADER",
    "INDEX_HEADER",
    "NO_INDEX_HEADER",
    "BUILD_HINT_PREFIX",
    "StatusReport",
    "run_status",
    "parse_status_report",
    "split_watch_mode",
    "indexing_progress",
    "coverage_word",
    "COVERAGE_WARNING_LABEL",
    "seconds_value",
    "age_value",
]

#: Header of the report when a server answered: ``Server status for <root>``.
SERVER_HEADER = "Server status for "
#: Header of the report from on-disk metadata: ``Index status for <root>``.
INDEX_HEADER = "Index status for "
#: Header of the no-index report: ``No index found at <index dir>``.
NO_INDEX_HEADER = "No index found at "
#: Second line of the no-index report: ``Run `trisift index <root>` to build one.``
BUILD_HINT_PREFIX = "Run `trisift index "

#: Label that starts the standard-error warning for unreadable coverage metadata.
COVERAGE_WARNING_LABEL = "warning:"

_FIELD = re.compile(r"^  (?P<label>[^:\r\n]+?):\s+(?P<value>.*)$")


class StatusReport:
    """A parsed status report: ``kind`` (server/index/none), ``subject`` and ``fields``.

    ``subject`` is the path the header names (the root, or for the no-index
    report the index directory).  ``fields`` maps each label to its value
    text.  ``hint`` is the build command named on the no-index report.
    """

    def __init__(self, kind: str, subject: str, fields: Dict[str, str], hint: Optional[str], raw: str):
        self.kind = kind
        self.subject = subject
        self.fields = fields
        self.hint = hint
        self.raw = raw

    def __getitem__(self, label: str) -> str:
        assert label in self.fields, f"status report lacks the {label!r} field:\n{self.raw}"
        return self.fields[label]

    def get(self, label: str) -> Optional[str]:
        return self.fields.get(label)

    def __repr__(self) -> str:
        return f"StatusReport({self.kind!r}, {self.subject!r}, {self.fields!r})"


def parse_status_report(stdout: str) -> StatusReport:
    """Parse the whole status output; fail on any line that is not a stated form."""
    lines = lf_lines(stdout)
    assert lines, "status printed nothing on stdout"
    head = lines[0]
    if head.startswith(SERVER_HEADER):
        kind, subject = "server", head[len(SERVER_HEADER):]
    elif head.startswith(INDEX_HEADER):
        kind, subject = "index", head[len(INDEX_HEADER):]
    elif head.startswith(NO_INDEX_HEADER):
        # Guidance is free prose; retain it for a direct check of the stated command.
        hint = "\n".join(lines[1:])
        assert "trisift index " in hint, f"no-index report lacks build command: {stdout}"
        return StatusReport("none", head[len(NO_INDEX_HEADER):], {}, hint, stdout)
    else:
        raise AssertionError(f"status output starts with no known header:\n{stdout}")
    fields: Dict[str, str] = {}
    for line in lines[1:]:
        m = _FIELD.match(line)
        assert m, f"status line {line!r} is not a labelled field:\n{stdout}"
        label = m.group("label")
        # "Last successful reconcile" may legitimately appear once; any
        # duplicated label is a malformed report.
        assert label not in fields, f"label {label!r} repeated:\n{stdout}"
        fields[label] = m.group("value")
    return StatusReport(kind, subject, fields, None, stdout)


def run_status(path, *, cwd, index_path=None, env=None) -> RunResult:
    """Run ``trisift status [--index-path DIR] PATH`` and return the RunResult."""
    args = ["status"]
    if index_path is not None:
        args += ["--index-path", str(index_path)]
    args.append(str(path))
    return run_trisift(args, cwd=cwd, env=env, timeout=60)


def split_watch_mode(value: str) -> tuple:
    """Split ``<active> (requested: <requested>)`` into ``(active, requested)``."""
    m = re.fullmatch(r"(\S+) \(requested: (\S+)\)", value)
    assert m, f"Watch mode value {value!r} is not '<active> (requested: <requested>)'"
    return m.group(1), m.group(2)


def indexing_progress(value: str):
    """Return ``'complete'`` or ``(done, total)`` from the Indexing value."""
    if value == "complete":
        return "complete"
    m = re.fullmatch(r"([0-9]+)/([0-9]+) files", value)
    assert m, f"Indexing value {value!r} is neither 'complete' nor '<done>/<total> files'"
    return int(m.group(1)), int(m.group(2))


def coverage_word(value: str) -> str:
    """Return the coverage state word (``complete`` / ``unavailable``) of a Hidden coverage value.

    The value is the state word, optionally followed by a parenthesised note
    whose text is free.
    """
    m = re.fullmatch(r"(complete|unavailable)(?: \(.*\))?", value)
    assert m, f"Hidden coverage value {value!r} is not 'complete' or 'unavailable[ (<note>)]'"
    return m.group(1)


def seconds_value(value: str) -> int:
    """Return ``<n>`` from a Poll interval value ``<n>s`` (an optional note may follow)."""
    m = re.fullmatch(r"([0-9]+)s(?: .*)?", value)
    assert m, f"value {value!r} is not '<seconds>s'"
    return int(m.group(1))


def age_value(value: str) -> int:
    """Return an age in seconds from ``<n><unit> ago`` (unit s, m, h or d)."""
    m = re.fullmatch(r"([0-9]+)([smhd]) ago", value)
    assert m, f"value {value!r} is not '<n><s|m|h|d> ago'"
    return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
