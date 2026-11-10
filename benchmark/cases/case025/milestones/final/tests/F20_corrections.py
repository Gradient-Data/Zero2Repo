# feature: F20
"""Acceptance coverage for annotation suggestions and explicit source edits."""
import ast
import builtins
import importlib
import typing

from _helpers import workspace, read_text
from F20_helpers import (edit_report, terminal_edit, source_namespace,
                         return_expression, annotation_accepts_scalar,
                         annotation_is_unrestricted)


PREFIX_SOURCE = '''# Keep this module comment.
SENTINEL = 41

def render(name: str) -> str:
    return "Hello {name}"
'''


def test_observed_annotation_suggestions():
    source = '''from typing import Any

def take(value) -> None:
    pass

def produce(value: str):
    return value

class Receiver:
    def method(self) -> None:
        pass

def opaque(value: Any):
    return value

def unknown(value) -> None:
    pass

def calls(unrestricted: Any) -> None:
    take(17)
    take(-4)
    unknown(unrestricted)
    Receiver().method()
'''
    with workspace({'sample.py': source}) as root:
        assert edit_report(root) == []
        findings = edit_report(root, ['--enable', 'suggested_parameter_type', '--enable', 'suggested_return_type'])
        assert {(f['lineno'], f['code']) for f in findings} == {
            (3, 'suggested_parameter_type'), (6, 'suggested_return_type')}, findings
        assert len(findings) == 2
        for finding in findings:
            metadata = finding['extra_metadata']
            namespace = {**vars(builtins), **vars(typing), 'typing': typing, 'builtins': builtins}
            for module in metadata['imports']:
                namespace[module.split('.')[0]] = importlib.import_module(module.split('.')[0])
            annotation = eval(metadata['suggested_type'], namespace)
            assert not annotation_is_unrestricted(annotation), finding
            # Python's runtime class relation independently checks these simple observations.
            observations = (17, -4) if finding['code'] == 'suggested_parameter_type' else ('alpha', 'beta')
            assert all(annotation_accepts_scalar(annotation, value) for value in observations)
        assert read_text(root / 'sample.py') == source


def test_prefix_and_unused_suppression_corrections():
    with workspace({'sample.py': PREFIX_SOURCE}) as root:
        assert [f['code'] for f in edit_report(root, ['--enable', 'missing_f'])] == ['missing_f']
        edit_report(root, ['--enable', 'missing_f', '--autofix'])
        edited = read_text(root / 'sample.py')
        assert isinstance(return_expression(edited, 'render'), ast.JoinedStr)
        assert '# Keep this module comment.' in edited
        namespace = source_namespace(edited)
        assert namespace['SENTINEL'] == 41
        assert [namespace['render'](v) for v in ('Ada', 'Lin')] == ['Hello Ada', 'Hello Lin']
        assert edit_report(root, ['--enable', 'missing_f']) == []
    for comment in ('    # static analysis: ignore[undefined_name]\n', ''):
        source = '# Retain me.\ndef stable() -> int:\n' + comment + '    return 23' + ('' if comment else '  # static analysis: ignore[undefined_name]') + '\n'
        with workspace({'sample.py': source}) as root:
            assert [f['code'] for f in edit_report(root, ['--enable', 'unused_ignore'])] == ['unused_ignore']
            edit_report(root, ['--enable', 'unused_ignore', '--autofix'])
            edited = read_text(root / 'sample.py')
            assert 'static analysis: ignore' not in edited
            assert '# Retain me.' in edited
            assert ast.dump(ast.parse(edited)) == ast.dump(ast.parse(source))
            assert edit_report(root, ['--enable', 'unused_ignore']) == []


def test_edit_acceptance_rejection_and_automatic_mode():
    for mode in ('ordinary', 'reject', 'accept', 'automatic'):
        with workspace({'sample.py': PREFIX_SOURCE}) as root:
            flags = ['--enable', 'missing_f']
            if mode in ('accept', 'reject'):
                terminal_edit(root, flags, 'y' if mode == 'accept' else 'n')
            else:
                findings = edit_report(root, flags + (['--autofix'] if mode == 'automatic' else []))
                assert [f['code'] for f in findings] == ['missing_f']
            edited = read_text(root / 'sample.py')
            if mode in ('ordinary', 'reject'):
                assert edited == PREFIX_SOURCE
                assert [f['code'] for f in edit_report(root, flags)] == ['missing_f']
            else:
                assert isinstance(return_expression(edited, 'render'), ast.JoinedStr)
                assert source_namespace(edited)['render']('Mira') == 'Hello Mira'
                assert edit_report(root, flags) == []


def test_category_suppression_and_unavailable_correction():
    source = 'def broken() -> int:\n    return missing_symbol\n'
    with workspace({'sample.py': source}) as root:
        assert [f['code'] for f in edit_report(root)] == ['undefined_name']
        assert [f['code'] for f in edit_report(root, ['--autofix'])] == ['undefined_name']
        assert read_text(root / 'sample.py') == source
        assert [f['code'] for f in edit_report(root)] == ['undefined_name']
    with workspace({'sample.py': source}) as root:
        terminal_edit(root, ['--add-ignores'], 'y')
        edited = read_text(root / 'sample.py')
        assert '# static analysis: ignore[undefined_name]' in edited
        assert ast.dump(ast.parse(edited)) == ast.dump(ast.parse(source))
        assert edit_report(root) == []
        # Keep the comment in place and introduce a different error on its statement.
        changed = edited.replace('missing_symbol', '"wrong return type"')
        (root / 'sample.py').write_text(changed, encoding='utf-8')
        assert [f['code'] for f in edit_report(root)] == ['incompatible_return_value']


def test_percent_conversion_preserves_dynamic_meaning():
    sources = [
        'def render(text: str, number: int) -> str:\n    return "item=%s count=%d" % (text, number)\n',
        'class Item:\n    text: str\n    number: int\ndef render(item: Item) -> str:\n    return "item=%s count=%d" % (item.text, item.number)\n',
    ]
    for source in sources:
        with workspace({'sample.py': source}) as root:
            assert edit_report(root) == []
            assert read_text(root / 'sample.py') == source
            assert [f['code'] for f in edit_report(root, ['--enable', 'use_fstrings'])] == ['use_fstrings']
            edit_report(root, ['--enable', 'use_fstrings', '--autofix'])
            edited = read_text(root / 'sample.py')
            assert isinstance(return_expression(edited, 'render'), ast.JoinedStr)
            before, after = source_namespace(source), source_namespace(edited)
            for text, number in [('alpha', 7), ('quote" and %', -52), ('', 0)]:
                if 'Item' in before:
                    original_item, edited_item = before['Item'](), after['Item']()
                    for item in (original_item, edited_item):
                        item.text, item.number = text, number
                    expected = before['render'](original_item)
                    actual = after['render'](edited_item)
                else:
                    expected = before['render'](text, number)
                    actual = after['render'](text, number)
                assert actual == expected
            assert edit_report(root, ['--enable', 'use_fstrings']) == []
