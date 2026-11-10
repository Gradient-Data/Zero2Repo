# feature: F14
"""Index rendering through public document entries and PDF text observations."""
import re
from talvo.document import DocumentTree
from talvo.dimension import PT
from talvo.paper import Paper
from talvo.paragraph import Paragraph, FixedSpacing
from talvo.index import IndexLabel
from talvo.styleds import IndexEntry
from talvo.strings import Strings
from F04_helpers import supplied_typeface
from F05_helpers import caller_sheet
from F08_helpers import FlowDocument
from F07_helpers import visible_lines
from _helpers import call_public, observe_pdf


def render_index_document(destination, elements):
    sheet = caller_sheet([
        ('body', Paragraph, dict(typeface=supplied_typeface('ttf'),
            font_weight=400, font_size=10*PT, line_spacing=FixedSpacing(16*PT),
            space_above=0*PT, space_below=0*PT, hyphenate=False)),
        ('index labels', IndexLabel, dict(keep_with_next=False)),
        ('nested entries', IndexEntry.like(index_level=2), dict(margin_left=18*PT)),
        ('deep entries', IndexEntry.like(index_level=3), dict(margin_left=36*PT))])
    strings = Strings()
    strings['@index_see'] = 'Refer'
    strings['@index_seealso'] = 'Related'
    cfg = FlowDocument.Configuration('index observation', stylesheet=sheet, strings=strings)
    cfg('page', page_size=Paper('index paper', 700*PT, 700*PT))
    return FlowDocument(DocumentTree(elements), configuration=cfg).render(str(destination))


def index_snapshot(destination, elements, environment):
    result = call_public(render_index_document, destination, elements, cwd=destination.parent)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr, result.warnings)
    return observe_pdf(destination.with_suffix('.pdf'), env=environment)


def index_pdf_lines(snapshot):
    """Fixtures place the index on a fresh final page, after body occurrences."""
    return [line for line in visible_lines(snapshot)
            if line['page'] == len(snapshot['pages']) - 1]


def index_line(snapshot, term):
    matches = [line for line in index_pdf_lines(snapshot)
               if line['text'].startswith(term)
               and (len(line['text']) == len(term)
                    or not line['text'][len(term)].isalnum())]
    assert len(matches) == 1, (term, matches, index_pdf_lines(snapshot))
    return matches[0]


def index_words(text):
    """Read word/page-label tokens, leaving joining punctuation ungraded."""
    return re.findall(r'[A-Za-z]+|[0-9]+', text)
