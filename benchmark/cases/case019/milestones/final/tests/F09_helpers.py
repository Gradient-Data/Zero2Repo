# feature: F09
"""Render references and fields through caller-defined public templates."""
from talvo.document import DocumentTree
from talvo.strings import Strings
from talvo.dimension import PT
from talvo.paper import Paper
from talvo.paragraph import Paragraph, FixedSpacing
from talvo.text import SingleStyledText
from talvo.structure import Heading
from F04_helpers import supplied_typeface
from F05_helpers import caller_sheet
from F08_helpers import FlowDocument
from F07_helpers import line_containing
from _helpers import call_public, observe_pdf


def render_reference_document(destination, elements, metadata, page, parts, options):
    sheet = caller_sheet([
        ('body', Paragraph, dict(typeface=supplied_typeface('ttf'),
            font_weight=400, font_size=10*PT, line_spacing=FixedSpacing(16*PT),
            space_above=0*PT, space_below=0*PT, hyphenate=False)),
        ('headings', Heading, dict(number_format='number', number_separator=SingleStyledText('.'),
            label_prefix=SingleStyledText('['),
            label_suffix=SingleStyledText('] '), font_weight=400, font_size=10*PT, space_above=0*PT,
            space_below=0*PT, keep_with_next=False))])
    strings = Strings()
    strings['@chapter'] = 'Division'
    cfg = FlowDocument.Configuration('references', stylesheet=sheet, parts=parts, strings=strings)
    cfg('page', page_size=Paper('reference paper', 600*PT, 400*PT),
        chapter_title_flowables=None, **page)
    for name in ('contents_page', 'contents_left_page', 'contents_right_page',
                 'front_page', 'tail_page'):
        cfg(name, **page)
    for name, settings in options.items():
        cfg(name, **settings)
    document = FlowDocument(DocumentTree(elements), configuration=cfg)
    document.metadata.update(metadata)
    return document.render(str(destination))


def reference_snapshot(destination, elements, environment, *, metadata=None,
                       page=None, parts=None, options=None):
    result = call_public(render_reference_document, destination, elements,
        metadata or {}, page or {}, parts or ['contents'], options or {})
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr)
    return observe_pdf(destination.with_suffix('.pdf'), env=environment), result


def compact_line(snapshot, token):
    return ''.join(line_containing(snapshot, token)['text'].split())


def covering_links(snapshot, token):
    from F07_helpers import token_box
    box = token_box(snapshot, token)
    return [link for link in snapshot['pages'][box['page']]['links']
            if link['from'][0] <= box['x0']+.5
            and link['from'][2] >= box['x1']-.5
            and link['from'][1] <= box['y'] <= link['from'][3]]


def resolved_internal_links(path, environment):
    """Resolve PDF destinations using an independent PDF consumer."""
    import json
    from _helpers import run_python
    source = '''import fitz, json, sys
with fitz.open(sys.argv[1]) as doc:
    names = doc.resolve_names()
    rows = []
    for page in doc:
        links = []
        for link in page.get_links():
            if link['kind'] == fitz.LINK_NAMED:
                target = names[link['nameddest']]
                link['page'] = target['page']
                link['to'] = fitz.Point(target['to']) * doc[link['page']].transformation_matrix
            link['from'] = list(link['from'])
            if 'to' in link:
                link['to'] = list(link['to'])
            links.append(link)
        rows.append(links)
    print(json.dumps(rows))
'''
    result = run_python(source, args=(str(path),), env=environment)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
