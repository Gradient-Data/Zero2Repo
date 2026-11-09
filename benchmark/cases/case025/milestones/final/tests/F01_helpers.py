# feature: F01
"""CLI observations for source checking; no inferred or missing-report defaults."""

import re
import os
from pathlib import Path
from collections import Counter
from _helpers import run_cli, read_json


def match_located(actual, expected, detail=None):
    """Match findings to expectations; each expectation lists accepted places and codes.

    A place or code with several accepted values is used only where the documents
    leave that choice open; every expectation still consumes exactly one finding.
    """
    remaining = Counter(actual)
    flexible = []
    missing = []
    for places, codes in expected:
        if len(places) == 1 and len(codes) == 1:
            key = (places[0], codes[0])
            if remaining[key] > 0:
                remaining[key] -= 1
            else:
                missing.append(key)
        else:
            flexible.append((places, codes))
    for places, codes in flexible:
        key = next((k for k in remaining if remaining[k] > 0 and k[0] in places and k[1] in codes), None)
        if key is None:
            missing.append((places, codes))
        else:
            remaining[key] -= 1
    unexpected = +remaining
    assert not missing and not unexpected, (unexpected, missing, detail)


def check_source(root, args):
    # The judge starts pytest in the selected product root. Preserve that
    # import root when moving the subprocess into its isolated source project.
    search_path = str(Path.cwd().resolve())
    if os.environ.get('PYTHONPATH'):
        search_path += os.pathsep + os.environ['PYTHONPATH']
    return run_cli('velnora', args, cwd=root, allowed_returncodes={0, 1},
                   env={'PYTHONPATH': search_path})


def reported_findings(root, args, *, report='findings.json'):
    path = root / report
    result = check_source(root, ['--json-output', str(path), *args])
    assert result.returncode == 1, result
    findings = read_json(path, result=result)
    assert isinstance(findings, list), findings
    return result, findings


def assert_source_column(column, source_line, *, start=None, end=None):
    """Require a UTF-8 character boundary within the affected source span."""
    if start is None:
        start = len(source_line) - len(source_line.lstrip())
    if end is None:
        end = len(source_line.rstrip())
    offsets = {len(source_line[:index].encode('utf-8'))
               for index in range(start, end)}
    assert type(column) is int and column in offsets, (column, source_line, start, end)


def assert_findings(findings, expected, *, sources):
    """Compare located categories and require columns within affected statements.

    A diagnostic may point at the statement or at an expression within it; the
    public reporting interface does not choose a particular highlight anchor.
    Each supplied line contains a single affected statement.
    """
    actual = Counter((f['filename'], f['lineno'], f['code']) for f in findings)
    assert actual == Counter(expected), findings
    for finding in findings:
        assert finding['description'].strip(), finding
        source_line = sources[finding['filename']].splitlines()[finding['lineno'] - 1]
        assert_source_column(finding['col_offset'], source_line)


def plain_stderr(result):
    """Remove ANSI SGR presentation sequences, retaining all diagnostic text."""
    return re.sub(r'\x1b\[[0-9;]*m', '', result.stderr)


def detailed_headers(text):
    return re.findall(r'^In (.+) at line (\d+)$', text, re.MULTILINE)


def concise_headers(text):
    return re.findall(r'^(.+):(\d+):(\d+): (.+) \[([a-z_]+)\]$',
                      text, re.MULTILINE)
