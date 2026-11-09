# feature: F12
"""Public note fixtures and independent PDF link observations."""
from talvo.reference import Note, NoteMarkerBase
from talvo.flowable import StaticGroupedFlowables
from talvo.paragraph import Paragraph, FixedSpacing
from talvo.dimension import PT
from talvo.document import DocumentTree
from talvo.paper import Paper
from F04_helpers import supplied_typeface
from F05_helpers import caller_sheet
from F08_helpers import FlowDocument
from F07_helpers import token_box, line_containing
from _helpers import call_public, observe_pdf


def make_note(text, **options):
    return Note(StaticGroupedFlowables([Paragraph(text)]), **options)


def render_note_document(destination, elements):
    sheet = caller_sheet([
        ('body', Paragraph, dict(typeface=supplied_typeface('ttf'),
            font_weight=400, font_size=10*PT, line_spacing=FixedSpacing(14*PT),
            space_above=0*PT, space_below=0*PT, hyphenate=False)),
        ('notes', Note, dict(location='footer')),
        ('markers', NoteMarkerBase, dict(number_format='number', link=True)),
        ('explicit markers', NoteMarkerBase.like(style='explicit'), dict(custom_label=True)),
        ('body notes', Note.like(style='body'), dict(location='in-place'))])
    cfg = FlowDocument.Configuration('notes', stylesheet=sheet)
    for name in ('page', 'contents_page', 'contents_left_page', 'contents_right_page'):
        cfg(name, page_size=Paper('note paper', 360*PT, 300*PT),
            left_margin=30*PT, right_margin=30*PT, top_margin=30*PT,
            bottom_margin=30*PT, header_text=None, footer_text=None,
            chapter_title_flowables=None)
    return FlowDocument(DocumentTree(elements), configuration=cfg).render(str(destination))


def note_snapshot(destination, elements, environment):
    result = call_public(render_note_document, destination, elements, cwd=destination.parent)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr, result.warnings)
    return observe_pdf(destination.with_suffix('.pdf'), env=environment)


def assert_note_destination(snapshot, links, marker_anchor, note_token, label):
    """Require an action on the marker and a destination at its note region."""
    source = line_containing(snapshot, marker_anchor)
    target = token_box(snapshot, note_token)
    import unicodedata
    chars = [(letter, char) for span in source['spans'] for char in span['chars']
             for letter in unicodedata.normalize('NFKC', char['c'])
             if not letter.isspace()]
    text = ''.join(letter for letter, _ in chars)
    start = text.index(marker_anchor) + len(marker_anchor)
    selected = chars[start:start + len(label)]
    assert ''.join(letter for letter, _ in selected) == label
    marked = [char for _, char in selected]
    x0 = min(char['bbox'][0] for char in marked)
    x1 = max(char['bbox'][2] for char in marked)
    y0 = min(char['bbox'][1] for char in marked)
    y1 = max(char['bbox'][3] for char in marked)
    actions = [link for link in links[source['page']]
               if link['from'][0] <= x0 + .5 and link['from'][2] >= x1 - .5
               and link['from'][1] <= (y0+y1)/2 <= link['from'][3]]
    assert any(link.get('page') == target['page'] and 'to' in link
               and line_containing(snapshot, note_token)['bbox'][1] - 1
               <= link['to'][1] <= target['y'] + .5
               and link['to'][0] <= target['x0'] + 1 for link in actions), (actions, target)


def note_line_draw_bounds(snapshot, token):
    """Read glyph drawing boxes, excluding font-wide text extraction padding."""
    position = token_box(snapshot, token)
    line = line_containing(snapshot, token)
    boxes = [char[3] for span in snapshot['pages'][position['page']]['glyphs']
             for char in span['chars']
             if abs(char[2][1] - position['y']) < .05
             and line['bbox'][0] - .5 <= char[2][0] <= line['bbox'][2] + .5]
    assert boxes, (token, position)
    return min(b[1] for b in boxes), max(b[3] for b in boxes)
