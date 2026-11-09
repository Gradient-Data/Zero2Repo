# feature: F07
"""Public content construction and PDF geometry observations for text layout."""
import io
import unicodedata
from pathlib import Path
from zipfile import ZipFile

from _helpers import call_public, observe_pdf


def render_content_document(destination, elements, stylesheet):
    """Render content alone, with automatic contents and page decorations off."""
    from talvo.document import DocumentTree
    from talvo.templates import Article
    from talvo.paper import Paper
    from talvo.dimension import PT
    from talvo.structure import TableOfContentsSection
    from F05_helpers import caller_sheet
    stylesheet = caller_sheet([('suppress automatic contents', +TableOfContentsSection,
                                dict(hide=True))], base=stylesheet)
    configuration = Article.Configuration('content observation', parts=['contents'],
                                          stylesheet=stylesheet)
    configuration('contents_page', page_size=Paper('caller paper', 600*PT, 800*PT), left_margin=40*PT, right_margin=40*PT,
                  top_margin=40*PT, bottom_margin=40*PT,
                  header_text=None, footer_text=None,
                  title_page_header_text=None, title_page_footer_text=None)
    return Article(DocumentTree(elements), configuration=configuration).render(str(destination))


def text_snapshot(destination, elements, stylesheet, environment):
    result = call_public(render_content_document, destination, elements, stylesheet,
                         cwd=destination.parent)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr)
    return observe_pdf(destination.with_suffix('.pdf'), env=environment)


def insertion_text(text, color, size):
    from talvo.text import SingleStyledText, TextStyle
    from talvo.color import HexColor
    from talvo.dimension import PT
    return SingleStyledText(text, style=TextStyle(font_color=HexColor(color), font_size=size*PT))


def render_rst_content(destination, source, stylesheet):
    from talvo.frontend.rst import ReStructuredTextReader
    tree = ReStructuredTextReader().parse(io.StringIO(source))
    return render_content_document(destination, tree.children, stylesheet)


def rst_snapshot(destination, source, stylesheet, environment):
    result = call_public(render_rst_content, destination, source, stylesheet,
                         cwd=destination.parent)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr)
    return observe_pdf(destination.with_suffix('.pdf'), env=environment)


def visible_lines(snapshot):
    """Read PDF text lines with their characters, coordinates and span styles."""
    lines = []
    for page_index, page in enumerate(snapshot['pages']):
        for block in page['raw_text']['blocks']:
            for line in block.get('lines', []):
                text = unicodedata.normalize('NFKC', ''.join(
                    char['c'] for span in line['spans'] for char in span['chars']))
                lines.append(dict(text=text, spans=line['spans'], bbox=line['bbox'],
                                  page=page_index))
    return lines


def line_containing(snapshot, token):
    matches = [line for line in visible_lines(snapshot) if token in line['text']]
    assert len(matches) == 1, (token, matches)
    return matches[0]


def token_box(snapshot, token):
    """Locate a unique token even when it crosses PDF style spans."""
    matches = []
    for line in visible_lines(snapshot):
        chars = [(letter, c) for span in line['spans'] for c in span['chars']
                 for letter in unicodedata.normalize('NFKC', c['c'])]
        text = ''.join(letter for letter, c in chars)
        start = text.find(token)
        if start >= 0:
            assert text.find(token, start+1) < 0, text
            selected = [c for letter,c in chars[start:start+len(token)]]
            matches.append(dict(page=line['page'],
                x0=min(c['bbox'][0] for c in selected),
                x1=max(c['bbox'][2] for c in selected),
                y=selected[0]['origin'][1]))
    assert len(matches) == 1, (token, matches)
    return matches[0]


def independent_hyphenator(directory, language, minimum):
    """Use upstream Pyphen dictionaries, not the product's hyphenation output.

    Wheel: Pyphen 0.17.2 from PyPI, with its included dictionary licenses.
    Extraction and dictionary failures propagate. No network is used at runtime.
    """
    import sys
    directory.mkdir(exist_ok=True)
    with ZipFile(Path(__file__).with_name('assets') / 'F07_pyphen.whl') as wheel:
        wheel.extractall(directory)
    sys.path.insert(0, str(directory))
    import pyphen
    return pyphen.Pyphen(lang=language, left=minimum, right=minimum)


def supply_hyphenation_dictionary(directory, language):
    """Supply a real upstream language dictionary through the public cwd path."""
    name = 'hyph_' + language + '.dic'
    with ZipFile(Path(__file__).with_name('assets') / 'F07_pyphen.whl') as wheel:
        data = wheel.read('pyphen/dictionaries/' + name)
    (directory / name).write_bytes(data)


def list_label_text(snapshot, body_token):
    """Read the label region on a known list body's baseline, not its prose."""
    body = token_box(snapshot, body_token)
    chars = []
    for line in visible_lines(snapshot):
        if line['page'] != body['page']:
            continue
        for span in line['spans']:
            for char in span['chars']:
                if (abs(char['origin'][1] - body['y']) < .05
                        and char['bbox'][2] < body['x0']):
                    chars.append(char)
    chars.sort(key=lambda char: char['origin'][0])
    label = ''.join(char['c'] for char in chars).strip()
    assert label, (body_token, body, snapshot)
    return label


def typographic_metrics(font_path, size, environment):
    """Read standardized input font metrics using an independent parser."""
    import json
    from _helpers import run_python
    source = """import json, sys
from fontTools.ttLib import TTFont
with TTFont(sys.argv[1]) as font:
    scale = float(sys.argv[2]) / font['head'].unitsPerEm
    table = font['OS/2']
    print(json.dumps([getattr(table, key)*scale for key in
        ('sTypoAscender', 'sTypoDescender', 'sTypoLineGap')]))
"""
    result = run_python(source, args=(str(font_path), str(size)), env=environment)
    assert result.returncode == 0, result
    return json.loads(result.stdout)
