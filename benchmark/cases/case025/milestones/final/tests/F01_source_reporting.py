# feature: F01
"""Acceptance of source targets, runtime inspection, and diagnostic carriers."""

import re
from _helpers import workspace, write_files, read_text
from F01_helpers import (check_source, reported_findings, assert_findings,
                         plain_stderr, detailed_headers, concise_headers, assert_source_column)


def test_source_target_forms():
    files = {
        'single.py': 'def single():\n    return missing_single\n',
        'tree/top.py': 'def top():\n    return missing_top\n',
        'tree/nested/leaf.py': '\ndef leaf():\n    return missing_leaf\n',
        'other/end.py': '\n\ndef end():\n    return missing_end\n',
        'tree/notes.txt': 'This is not Python source.\n',
    }
    with workspace(files) as root:
        for targets, locations in [
            (['single.py'], [('single.py', 2)]),
            (['tree'], [('tree/top.py', 2), ('tree/nested/leaf.py', 3)]),
            (['single.py', 'tree', 'other'], [('single.py', 2),
             ('tree/top.py', 2), ('tree/nested/leaf.py', 3), ('other/end.py', 4)]),
        ]:
            _, findings = reported_findings(root, [str(root / t) for t in targets])
            assert_findings(findings, [(str(root / p), line, 'undefined_name')
                                       for p, line in locations],
                            sources={str(root / p): body for p, body in files.items()})
        _, findings = reported_findings(root, ['--code', files['single.py']])
        assert_findings(findings, [('<code>', 2, 'undefined_name')],
                        sources={'<code>': files['single.py']})


def test_runtime_objects_and_uncalled_bodies():
    provider = ('class Generated: pass\n'
                'def factory() -> int: return 7\n'
                'member = 19\n')
    source = (
        'import runtime_provider\n'
        'from typing import assert_type\n'
        'def never_called():\n'
        '    assert_type(runtime_provider.factory(), int)\n'
        '    assert_type(runtime_provider.Generated(), runtime_provider.Generated)\n'
        '    good: int = runtime_provider.member\n'
        '    bad: str = runtime_provider.factory()\n'
        '    bad_member: str = runtime_provider.member\n'
        '    bad_class: int = runtime_provider.Generated()\n'
        '    return good, bad, bad_member, bad_class, absent_runtime_name\n'
    )
    with workspace({'runtime_provider.py': f'exec({provider!r})\n',
                    'client.py': source}) as root:
        _, findings = reported_findings(root, [str(root / 'client.py')])
        assert_findings(findings, [
            (str(root / 'client.py'), 7, 'incompatible_assignment'),
            (str(root / 'client.py'), 8, 'incompatible_assignment'),
            (str(root / 'client.py'), 9, 'incompatible_assignment'),
            (str(root / 'client.py'), 10, 'undefined_name'),
        ], sources={str(root / 'client.py'): source})
        # A valid counterpart proves runtime members and type assertions resolve.
        valid = (source.replace('bad: str', 'bad: int')
                 .replace('bad_member: str', 'bad_member: int')
                 .replace('bad_class: int', 'bad_class: runtime_provider.Generated')
                 .replace('absent_runtime_name', 'good'))
        write_files(root, {'client.py': valid})
        result = check_source(root, [str(root / 'client.py')])
        assert result.returncode == 0, result
        assert not result.stderr, result


def test_status_and_first_error():
    source = ('def first():\n    return absent_first\n\n'
              'def second():\n    value: int = "wrong"\n    return value\n')
    with workspace() as root:
        clean = check_source(root, ['--code', 'def good(value: int) -> int:\n    return value\n'])
        assert clean.returncode == 0, clean
        assert not clean.stderr, clean
        result, findings = reported_findings(root, ['--code', source])
        assert_findings(findings, [('<code>', 2, 'undefined_name'),
                                   ('<code>', 5, 'incompatible_assignment')], sources={'<code>': source})
        assert len(detailed_headers(result.stderr)) == 2, result
        first = check_source(root, ['--fail-after-first', '--code', source])
        assert first.returncode == 1, first
        # The reference repeats the same finding in an uncaught exception.
        headers = set(detailed_headers(first.stderr))
        assert len(headers) == 1, first
        assert next(iter(headers)) in [('<code>', '2'), ('<code>', '5')], first
        categories = set(re.findall(r'\(code: ([a-z_]+)\)', first.stderr))
        expected_category = {'2': 'undefined_name', '5': 'incompatible_assignment'}
        assert categories == {expected_category[next(iter(headers))[1]]}, first


def test_detailed_and_concise_presentations():
    source = 'def describe():\n    return missing_presentation\n'
    with workspace({'presentation.py': source}) as root:
        target = str(root / 'presentation.py')
        for options in [[], ['--output-format', 'detailed'], ['--output-format', 'concise']]:
            result = check_source(root, [*options, target])
            assert result.returncode == 1, result
            text = plain_stderr(result)
            if options == ['--output-format', 'concise']:
                headers = concise_headers(text)
                assert len(headers) == 1, result
                path, line, column, explanation, code = headers[0]
                assert (path, line, code) == (target, '2', 'undefined_name')
                assert_source_column(int(column), source.splitlines()[1])
                assert 'missing_presentation' in explanation
                # The chosen presentation replaces the detailed one.
                assert detailed_headers(text) == [], result
            else:
                assert concise_headers(text) == [], result
                assert detailed_headers(text) == [(target, '2')], result
                assert '(code: undefined_name)' in text
                explanations = re.findall(r'^(.+) \(code: undefined_name\)$', text, re.MULTILINE)
                assert len(explanations) == 1 and 'missing_presentation' in explanations[0], result
                assert source.splitlines()[1].strip() in text


def test_source_input_and_execution_failures():
    with workspace({'broken.py': 'def broken(:\n',
                    'unreadable.py': 'x = 1\n',
                    'explodes.py': 'raise RuntimeError("source execution marker")\n'}) as root:
        live = check_source(root, ['--code', 'answer = 42\n'])
        assert live.returncode == 0, live
        (root / 'unreadable.py').chmod(0)
        for name, failure_class in [('unreadable.py', 'FileNotFoundError'),
                                    ('broken.py', 'SyntaxError')]:
            result = check_source(root, [str(root / name)])
            assert result.returncode == 1, result
            text = plain_stderr(result)
            assert re.search(r'^(?:[\w.]+\.)?' + failure_class + r': .+', text, re.MULTILINE), result
            assert str(root / name) in text, result
        for args, filename in [([str(root / 'explodes.py')], str(root / 'explodes.py')),
                               (['--code', 'raise RuntimeError("source execution marker")\n'], '<code>')]:
            result, findings = reported_findings(root, args)
            assert_findings(findings, [(filename, 1, 'import_failed')],
                            sources={filename: 'raise RuntimeError("source execution marker")\n'})
            description = findings[0]['description']
            assert 'RuntimeError' in description and 'source execution marker' in description
            assert '(code: import_failed)' in result.stderr
            assert 'RuntimeError' in result.stderr and 'source execution marker' in result.stderr


def test_json_and_markdown_exports():
    files = {'alpha.py': 'def alpha():\n    return absent_alpha\n\n'
                         'def alpha_again():\n    return absent_again\n',
             'beta.py': '\ndef beta():\n    value: int = "wrong"\n    return value\n'}
    with workspace(files) as root:
        result, findings = reported_findings(root, [
            '--markdown-output', str(root / 'report.md'),
            str(root / 'alpha.py'), str(root / 'beta.py')])
        assert_findings(findings, [(str(root / 'alpha.py'), 2, 'undefined_name'),
                                   (str(root / 'alpha.py'), 5, 'undefined_name'),
                                   (str(root / 'beta.py'), 3, 'incompatible_assignment')],
                        sources={str(root / name): body for name, body in files.items()})
        document = read_text(root / 'report.md', result=result)
        sections = re.split(r'^### (.+) \((\d+) failures\)\s*$', document, flags=re.MULTILINE)
        assert len(sections) == 7, document
        groups = {name: (int(count), body) for name, count, body
                  in zip(sections[1::3], sections[2::3], sections[3::3])}
        assert set(groups) == {'/alpha.py', '/beta.py'}, document
        # Sections with different finding counts tell a real count from a constant.
        for filename, expected in [
            ('/alpha.py', [(2, 'undefined_name', ('absent_alpha',)),
                           (5, 'undefined_name', ('absent_again',))]),
            ('/beta.py', [(3, 'incompatible_assignment', ('value', 'int', 'str'))]),
        ]:
            count, body = groups[filename]
            entries = re.findall(r'^\* line (\d+): `(.+)`$', body, re.MULTILINE)
            assert count == len(expected) == len(entries), document
            by_line = {int(position): explanation for position, explanation in entries}
            assert set(by_line) == {line for line, _, _ in expected}, document
            for line, category, subjects in expected:
                assert f'(code: {category})' in by_line[line]
                assert any(subject in by_line[line] for subject in subjects), by_line[line]
