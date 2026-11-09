# feature: F08
"""Public page-template construction and independent PDF observations."""
from talvo.template import (DocumentTemplate, ContentsPartTemplate,
                            FixedDocumentPartTemplate, BodyPageTemplate)
from talvo.attribute import OverrideDefault
from talvo.dimension import PT
from talvo.document import DocumentTree
from talvo.paper import Paper
from talvo.paragraph import Paragraph
from talvo.font import Typeface
from talvo.paragraph import FixedSpacing
from F05_helpers import caller_sheet
from _helpers import call_public, observe_pdf


class FlowDocument(DocumentTemplate):
    """Caller-defined parts with a plain, measurable body area."""
    parts = OverrideDefault(['contents'])
    contents = ContentsPartTemplate()
    front = FixedDocumentPartTemplate()
    tail = FixedDocumentPartTemplate()
    empty = FixedDocumentPartTemplate()
    page = BodyPageTemplate(left_margin=30*PT, right_margin=30*PT,
                            top_margin=30*PT, bottom_margin=30*PT,
                            header_text=None, footer_text=None)
    contents_page = BodyPageTemplate(base='page')
    contents_left_page = BodyPageTemplate(base='contents_page')
    contents_right_page = BodyPageTemplate(base='contents_page')
    front_page = BodyPageTemplate(base='page')
    tail_page = BodyPageTemplate(base='page')
    empty_page = BodyPageTemplate(base='page')


def render_flow(destination, elements, page_options, part_options, parts, inserts):
    sheet = caller_sheet([('plain body', Paragraph, dict(
        typeface=Typeface.from_string('courier'), font_size=10*PT,
        line_spacing=FixedSpacing(16*PT), space_above=0*PT,
        space_below=0*PT, hyphenate=False))])
    cfg = FlowDocument.Configuration('caller flow', stylesheet=sheet, parts=parts)
    for name in ('page', 'contents_page', 'contents_left_page',
                 'contents_right_page', 'front_page', 'tail_page', 'empty_page'):
        options = dict(page_options['page'])
        options.update(page_options.get(name, {}))
        cfg(name, **options)
    for name, options in part_options.items():
        cfg(name, **options)
    doc = FlowDocument(DocumentTree(elements), configuration=cfg)
    for part, text, position in inserts:
        doc.insert(part, Paragraph(text), position)
    return doc.render(str(destination))


def flow_snapshot(destination, elements, environment, *, page=None,
                  pages=None, part_options=None, parts=None, inserts=()):
    options = dict(page_size=Paper('caller size', 360*PT, 240*PT))
    if page:
        options.update(page)
    if options['page_size'] is None:
        del options['page_size']  # Explicitly exercise the product default.
    settings = {'page': options}
    if pages:
        settings.update(pages)
    result = call_public(render_flow, destination, elements, settings,
                         part_options or {}, parts or ['contents'], inserts)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr)
    return observe_pdf(destination.with_suffix('.pdf'), env=environment)
