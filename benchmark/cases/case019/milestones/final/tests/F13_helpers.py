# feature: F13
"""Navigation fixtures using public content and caller-selected reference fields."""
from talvo.document import DocumentTree
from talvo.dimension import PT
from talvo.paper import Paper
from talvo.paragraph import Paragraph, FixedSpacing
from talvo.structure import Section, Heading, TableOfContentsEntry, ListOfEntry
from talvo.image import Caption, Figure, ListOfFigures
from talvo.table import ListOfTables
from talvo.text import SingleStyledText, MixedStyledText
from talvo.reference import ReferenceField
from talvo.flowable import PageBreak
from F04_helpers import supplied_typeface
from F05_helpers import caller_sheet
from F08_helpers import FlowDocument
from F07_helpers import visible_lines
from _helpers import call_public, observe_pdf


def navigation_section(title, label, children=(), *, style=None):
    return Section([PageBreak(), Heading(title, custom_label=label),
                    Paragraph('Body' + title)] + list(children), style=style)


def render_navigation(destination, elements):
    sheet = caller_sheet([
        ('body', Paragraph, dict(typeface=supplied_typeface('ttf'),
            font_weight=400, font_size=10*PT, line_spacing=FixedSpacing(14*PT),
            space_above=0*PT, space_below=0*PT, hyphenate=False)),
        ('heading', Heading, dict(custom_label=True, label_prefix=None,
            label_suffix=SingleStyledText(' '), keep_with_next=False)),
        ('excluded', Section.like(style='excluded'), dict(show_in_toc=False)),
        ('hidden', Section.like(style='hidden'), dict(hide=True)),
        ('toc fields', TableOfContentsEntry,
            dict(text=MixedStyledText(['TOC|', ReferenceField('number'), '|', ReferenceField('title'), '|', ReferenceField('page'), '|END']))),
        ('figure fields', ListOfFigures / ListOfEntry,
            dict(text=MixedStyledText(['FIG|', ReferenceField('number'), '|', ReferenceField('title'), '|', ReferenceField('page'), '|END']))),
        ('table fields', ListOfTables / ListOfEntry,
            dict(text=MixedStyledText(['TAB|', ReferenceField('number'), '|', ReferenceField('title'), '|', ReferenceField('page'), '|END']))),
        ('captions', Caption, dict(numbering_level=0)),
        ('unnumbered caption', Caption.like(style='unnumbered'), dict(number_format=None))])
    cfg = FlowDocument.Configuration('navigation', stylesheet=sheet)
    for name in ('page', 'contents_page', 'contents_left_page', 'contents_right_page'):
        cfg(name, page_size=Paper('navigation paper', 600*PT, 500*PT),
            left_margin=30*PT, right_margin=30*PT, top_margin=30*PT,
            bottom_margin=30*PT, header_text=None, footer_text=None,
            chapter_title_flowables=None)
    return FlowDocument(DocumentTree(elements), configuration=cfg).render(str(destination))


def navigation_snapshot(destination, elements, environment):
    result = call_public(render_navigation, destination, elements, cwd=destination.parent)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr, result.warnings)
    return observe_pdf(destination.with_suffix('.pdf'), env=environment)


def navigation_rows(snapshot, prefix):
    rows = []
    for line in visible_lines(snapshot):
        if line['text'].startswith(prefix + '|'):
            fields = line['text'].split('|')
            assert len(fields) == 5 and fields[4] == 'END', line
            rows.append((fields[1], fields[2], int(fields[3])))
    return rows


def content_line(snapshot, title):
    lines = [line for line in visible_lines(snapshot)
             if title in line['text'] and not line['text'].startswith(('TOC|', 'FIG|', 'TAB|', 'Body'))]
    assert len(lines) == 1, (title, lines)
    return lines[0]


def assert_navigation(snapshot, prefix, entries):
    expected = [(label, title, content_line(snapshot, title)['page'] + 1)
                for label, title in entries]
    assert navigation_rows(snapshot, prefix) == expected


def resolved_navigation_outline(path, environment):
    """Resolve named outline destinations in the same page coordinates as text."""
    import json
    from _helpers import run_python
    source = '''import fitz, json, sys
with fitz.open(sys.argv[1]) as document:
    names = document.resolve_names()
    rows = document.get_toc(simple=False)
    for row in rows:
        action = row[3]
        if action['kind'] == fitz.LINK_NAMED:
            target = names[action['nameddest']]
            action['page'] = target['page']
            action['to'] = fitz.Point(target['to']) * document[target['page']].transformation_matrix
        if 'to' in action:
            action['to'] = list(action['to'])
    print(json.dumps(rows))
'''
    result = run_python(source, args=(str(path),), env=environment)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
