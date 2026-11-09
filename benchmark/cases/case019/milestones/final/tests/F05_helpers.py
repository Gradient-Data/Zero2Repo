# feature: F05
"""Render caller-defined style sheets and read independent PDF observations."""
import re
import unicodedata

from _helpers import call_public, observe_pdf


def render_style_document(destination, elements, stylesheet):
    from talvo.document import DocumentTree
    from talvo.templates import Article
    from talvo.dimension import PT
    configuration = Article.Configuration('style observation', stylesheet=stylesheet)
    configuration('contents_page', left_margin=40*PT, right_margin=40*PT,
                  top_margin=40*PT, bottom_margin=40*PT)
    return Article(DocumentTree(elements), configuration=configuration).render(str(destination))


def style_snapshot(destination, elements, stylesheet, environment):
    result = call_public(render_style_document, destination, elements, stylesheet)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr)
    return observe_pdf(destination.with_suffix('.pdf'), env=environment)


def token_spans(snapshot, token):
    """Read a unique token across equivalent PDF text-span partitions."""
    from functools import reduce
    from operator import and_
    found = []
    for page in snapshot['pages']:
        for block in page['raw_text']['blocks']:
            for line in block.get('lines', []):
                characters = [(letter, char, span) for span in line['spans']
                              for char in span['chars']
                              for letter in unicodedata.normalize('NFKC', char['c'])]
                text = ''.join(letter for letter, _, _ in characters)
                start = text.find(token)
                if start < 0:
                    continue
                assert text.find(token, start + 1) < 0, (token, text)
                selected = characters[start:start + len(token)]
                spans = [span for _, _, span in selected]
                chars = [char for _, char, _ in selected]
                # These callers observe uniformly styled tokens. Encoding one
                # token in several subset fonts must preserve its logical face.
                fonts = {re.sub(r'^[A-Z]{6}\+', '', span['font']) for span in spans}
                assert len(fonts) == 1, (token, fonts)
                assert max(s['size'] for s in spans) - min(s['size'] for s in spans) < .01
                assert len({s['color'] for s in spans}) == 1, (token, spans)
                found.append(dict(spans[0], font=next(iter(fonts)),
                    flags=reduce(and_, (s['flags'] for s in spans)), chars=chars,
                    origin=chars[0]['origin'], bbox=[
                        min(c['bbox'][0] for c in chars), min(c['bbox'][1] for c in chars),
                        max(c['bbox'][2] for c in chars), max(c['bbox'][3] for c in chars)]))
    assert len(found) == 1, (token, found)
    return found[0]


def assert_token_style(snapshot, token, *, size=None, color=None):
    import pytest
    span = token_spans(snapshot, token)
    if size is not None:
        assert span['size'] == pytest.approx(size, abs=0.01)
    if color is not None:
        assert span['color'] == color
    return span


def style_report_records(path):
    """Read element records and their adjacent match rows, ignoring score values.

    The public report is an indented element tree with match rows carrying a
    marker, parenthesized specificity, style label, sheet and base label.
    Unrecognized match rows fail rather than becoming a missing match.
    """
    records = []
    current = None
    row = re.compile(r'^\s+(?P<mark>[>x ]) \([^)]*\) (?P<name>.+?) \[(?P<sheet>[^]]+)\](?: > (?P<base>.+))?$')
    for line in path.read_text(encoding='utf-8').splitlines():
        if re.match(r'^\s+[>x ] \(', line):
            match = row.fullmatch(line)
            assert match is not None, line
            assert current is not None, line
            current['matches'].append(match.groupdict())
        elif line.strip() and not line.startswith(('---', '####')):
            current = {'element': line.strip(), 'matches': []}
            records.append(current)
    return records


def caller_sheet(rules, base=None, name='Caller rules'):
    from talvo.style import StyleSheet, StyledMatcher
    sheet = StyleSheet(name, matcher=StyledMatcher({n: s for n, s, p in rules}), base=base)
    for label, selector, properties in rules:
        sheet(label, **properties)
    return sheet
