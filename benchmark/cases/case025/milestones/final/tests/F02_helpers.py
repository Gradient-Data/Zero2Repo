# feature: F02
"""Configuration projects and direct CLI observations."""

import ast
import re
from collections import Counter
from _helpers import read_json, write_files
from F01_helpers import check_source, match_located


def config_file(root, body='', name='pyproject.toml'):
    return write_files(root, {name: '[tool.velnora]\n' + body})[name]


def check_configured(root, config, targets=(), flags=(), expected=()):
    """Assert exact located categories and the ordinary-run outcome."""
    report = root / 'report.json'
    if report.exists():
        report.unlink()
    result = check_source(root, ['--config-file', str(config), '--json-output',
                                 str(report), *flags, *map(str, targets)])
    if expected:
        assert result.returncode == 1, result
        findings = read_json(report, result=result)
        match_located([((f['filename'], f['lineno']), f['code']) for f in findings],
                      [(((str(root / path), line),), tuple(code.split('|'))) for path, line, code in expected],
                      findings)
        assert result.stderr.strip(), result
    else:
        assert result.returncode == 0, result
        assert result.stderr == '', result
    return result


def displayed_options(root, config, flags=()):
    """Read named option blocks, not their enumeration order."""
    result = check_source(root, ['--config-file', str(config), '--display-options', *flags])
    assert result.returncode == 0, result
    assert result.stderr == '', result
    blocks = {}
    current = None
    for line in result.stdout.splitlines():
        match = re.fullmatch(r'    ([a-z_]+) \(value: (.*)\)', line)
        if match:
            current = match[1]
            assert current not in blocks, result.stdout
            blocks[current] = (match[2], [])
        elif line.startswith('        '):
            assert current is not None, result.stdout
            blocks[current][1].append(line[8:])
        else:
            assert line == 'Options:', result.stdout
    assert blocks, result.stdout
    return blocks


def displayed_paths(display, root):
    """Read path-list payloads and compare the locations they designate."""
    sequence = ast.parse(display, mode='eval').body
    assert isinstance(sequence, ast.List), display
    paths = []
    for item in sequence.elts:
        assert isinstance(item, ast.Call), display
        assert isinstance(item.func, ast.Name) and item.func.id == 'PosixPath', display
        assert len(item.args) == 1 and not item.keywords, display
        path = ast.literal_eval(item.args[0])
        assert isinstance(path, str), display
        paths.append((root / path).resolve())
    return paths
