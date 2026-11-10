# feature: F03
"""Type feature observations through the CLI and annotated source AST."""
import ast
import re
from collections import Counter
from textwrap import dedent
from _helpers import workspace, read_json
from F01_helpers import check_source, match_located


def check_types(source):
    """Check all diagnostics against explicit source-line expectations."""
    source = dedent(source).lstrip('\n')
    expected = []
    for line, text in enumerate(source.splitlines(), 1):
        marker = re.search(r'# E(?:\+(\d+))?: ', text)
        if marker:
            places = tuple(range(line, line + int(marker[1] or 0) + 1))
            for code in text[marker.end():].split(', '):
                expected.append((places, tuple(code.split('|'))))
    # Keep the oracle out of submitted source while preserving source positions.
    source = '\n'.join(re.split(r'# E(?:\+\d+)?: ', line, maxsplit=1)[0].rstrip()
                       for line in source.splitlines()) + '\n'
    with workspace() as root:
        report = root / 'types.json'
        result = check_source(root, ['--disable', 'unused_variable', '--json-output', str(report), '--code', source])
        assert result.returncode == (1 if expected else 0), result
        findings = read_json(report, result=result)
        match_located([(f['lineno'], f['code']) for f in findings], expected,
                      [(f['lineno'], f['code'], f['description']) for f in findings])
        if expected:
            assert result.stderr.strip(), result
        else:
            assert not result.stderr, result
        return findings


def expression_type(tree, kind, line, column):
    """Read the public type display for exactly one located expression."""
    nodes = [node for node in ast.walk(tree) if isinstance(node, kind)
             and node.lineno == line and node.col_offset == column]
    assert len(nodes) == 1, (kind, line, column, ast.dump(tree))
    return str(nodes[0].inferred_value)


def literal_display_value(display):
    """Decode the published Literal[<Python literal>] form without fixing quotes."""
    expression = ast.parse(display, mode='eval').body
    assert isinstance(expression, ast.Subscript), display
    assert isinstance(expression.value, ast.Name) and expression.value.id == 'Literal', display
    return ast.literal_eval(expression.slice)
