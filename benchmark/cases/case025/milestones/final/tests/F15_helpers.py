# feature: F15
"""Usage search observations through the real CLI."""
import ast
import re
from collections import Counter
from textwrap import dedent
from _helpers import workspace, read_json
from F01_helpers import check_source
from F02_helpers import config_file


def usage_run(files, *, flags=(), config='', targets=None):
    with workspace({name: dedent(body).lstrip('\n') for name, body in files.items()}) as root:
        settings = config_file(root, config)
        report = root / 'usage.json'
        result = check_source(root, ['--config-file', str(settings), '--json-output',
                                    str(report), *flags,
                                    *[str(root / name) for name in
                                      (files if targets is None else targets)]])
        if result.returncode == 1:
            findings = read_json(report, result=result)
            assert isinstance(findings, list), findings
        else:
            assert result.returncode == 0, result
            assert result.stderr == '', result
            # File checking with no findings does not create a JSON report.
            assert not report.exists(), result
            findings = []
        return result, findings


def usage_diagnostics(source, *, flags=(), files=None, config=''):
    source = dedent(source).lstrip('\n')
    expected = Counter((line, code) for line, text in enumerate(source.splitlines(), 1)
                       if '# E: ' in text
                       for code in text.split('# E: ', 1)[1].split(', '))
    clean = '\n'.join(line.split('# E: ', 1)[0].rstrip()
                      for line in source.splitlines()) + '\n'
    project = dict(files or {})
    project['subject.py'] = clean
    result, findings = usage_run(project, flags=flags, config=config, targets=['subject.py'])
    assert result.returncode == (1 if expected else 0), result
    assert Counter((f['lineno'], f['code']) for f in findings) == expected, findings
    assert bool(result.stderr.strip()) == bool(expected), result
    return findings


def unused_members(stdout):
    records = []
    for line in stdout.splitlines():
        if line.startswith(('Unused attribute:', 'Unused method:')):
            match = re.fullmatch(r"Unused (attribute|method): <class '([^']+)'>\.([\w]+)", line)
            assert match, line
            records.append((match[1], match[2], match[3]))
    return set(records)


def unused_objects(stdout):
    records = {}
    for line in stdout.splitlines():
        if ': ' in line and not line.startswith('Unused '):
            name, status = line.split(': ', 1)
            if status in ('unused', 'used only in tests'):
                assert name not in records, stdout
                records[name] = status
    return records


def call_pattern_results(findings):
    """Read the call-pattern labels and payloads, leaving explanation prose free."""
    records = {}
    for finding in findings:
        match = re.fullmatch(
            r"Unused call pattern: ([\w.]+) parameter '([^']+)' (.+)",
            finding['description'], re.DOTALL,
        )
        assert match, finding
        subject = (match[1], match[2])
        assert subject not in records, findings
        detail = match[3]
        if detail.endswith(' omitted'):
            payload = ('omitted',)
        elif match := re.fullmatch(r'.+ literal (True|False)', detail, re.DOTALL):
            literal = ast.literal_eval(match[1])
            assert type(literal) is bool, finding
            payload = ('literal', literal)
        else:
            explanation, marker, values = detail.rpartition(' receives ')
            assert explanation and marker, finding
            missing, marker, observed = values.partition(' (observed ')
            assert marker and observed.endswith(')'), finding
            payload = ('union', _type_members(missing), _type_members(observed[:-1]))
        records[subject] = payload
    return records


def _type_members(expression):
    """Parse a union of built-in type names as a Python expression."""
    def members(node):
        if isinstance(node, ast.Name):
            return [node.id]
        assert isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr), expression
        return members(node.left) + members(node.right)

    names = members(ast.parse(expression.strip(), mode='eval').body)
    assert len(names) == len(set(names)), expression
    return frozenset(names)


def call_pattern_subjects(findings):
    subjects = []
    for finding in findings:
        match = re.match(r"Unused call pattern: ([\w.]+) parameter '([^']+)' ", finding['description'])
        assert match, finding
        subjects.append((match[1], match[2]))
    return Counter(subjects)
