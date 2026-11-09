# feature: F11
"""Public table fixtures and PDF cell-area observations."""
from talvo.table import (TableCell, TableCellStyle, TableRow, TableCellBackground,
                         TableCellBorder)
from talvo.paragraph import Paragraph, FixedSpacing
from talvo.dimension import PT
from talvo.color import Color
from talvo.draw import Stroke
from talvo.document import DocumentTree
from talvo.paper import Paper
from F04_helpers import supplied_typeface
from F05_helpers import caller_sheet
from F08_helpers import FlowDocument
from _helpers import call_public, observe_pdf


CELL_COLORS = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1)]


def table_cell(text='', *, color=None, **options):
    content = [Paragraph(text)] if isinstance(text, str) and text else text or []
    return TableCell(content, style=('cell'+str(color)) if color is not None else None,
                     **options)


def table_row(*texts):
    return TableRow([table_cell(text) for text in texts])


def render_table_document(destination, elements, rules=()):
    styling = [
        ('body', Paragraph, dict(typeface=supplied_typeface('ttf'), font_weight=400, font_size=10*PT, line_spacing=FixedSpacing(14*PT),
            space_above=0*PT, space_below=0*PT, hyphenate=False)),
        ('cells', TableCell, dict(padding=3*PT)),
        ('grid', TableCellBorder, dict(stroke=Stroke(.5*PT, Color(0, 0, 0))))]
    for i, color in enumerate(CELL_COLORS):
        styling.append(('area'+str(i), TableCell.like(style='cell'+str(i)) /
                        TableCellBackground, dict(fill_color=Color(*color))))
    sheet = caller_sheet(styling + list(rules))
    cfg = FlowDocument.Configuration('tables', stylesheet=sheet)
    for name in ('page', 'contents_page', 'contents_left_page', 'contents_right_page'):
        cfg(name, page_size=Paper('table paper', 360*PT, 300*PT),
            left_margin=30*PT, right_margin=30*PT, top_margin=30*PT, bottom_margin=30*PT,
            header_text=None, footer_text=None, chapter_title_flowables=None)
    tree = elements if isinstance(elements, DocumentTree) else DocumentTree(elements)
    return FlowDocument(tree, configuration=cfg).render(str(destination))


def table_call(destination, elements, rules=()):
    return call_public(render_table_document, destination, elements, rules,
                       cwd=destination.parent)


def table_snapshot(destination, elements, environment, rules=()):
    result = table_call(destination, elements, rules)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr, result.warnings)
    return observe_pdf(destination.with_suffix('.pdf'), env=environment), result


def cell_areas(snapshot, color):
    """Read filled cell regions from the independent PDF drawing consumer."""
    areas = []
    for page, record in enumerate(snapshot['pages']):
        regions = []
        for drawing in record['drawings']:
            fill = drawing['fill']
            if fill is not None and max(abs(a-b) for a,b in zip(fill, color)) < .001:
                regions.append(drawing['rect'])
        if regions:
            areas.append((page, [min(r[0] for r in regions), min(r[1] for r in regions),
                                 max(r[2] for r in regions), max(r[3] for r in regions)]))
    assert areas, (color, snapshot)
    return areas


def one_cell_area(snapshot, index):
    areas = cell_areas(snapshot, CELL_COLORS[index])
    assert len(areas) == 1, areas
    return areas[0][1]


def render_sourced_table(destination, source, widths):
    from talvo.frontend.rst import ReStructuredTextReader
    from talvo.table import Table
    tree = ReStructuredTextReader().parse(str(source))
    return render_table_document(destination, tree,
        [('supplied widths', Table, dict(column_widths=widths))])


def table_text_direction(snapshot, token):
    matches = []
    for page in snapshot['pages']:
        for block in page['raw_text']['blocks']:
            for line in block.get('lines', []):
                text = ''.join(c['c'] for span in line['spans'] for c in span['chars'])
                if token in text:
                    matches.append(line['dir'])
    assert len(matches) == 1, (token, matches)
    return matches[0]
