# feature: F17
"""Reader-to-template rendering and semantic PDF assertions."""
from _helpers import call_public, observe_pdf, text_stream
from F02_helpers import pdf_plain_text
from F05_helpers import token_spans
from F07_helpers import token_box, line_containing, list_label_text


def parse_source(reader, source, stream=False):
    return reader().parse(text_stream(source) if stream else str(source))


def publish_source(destination, reader, source, stream=False, template=None, sheet=None):
    from talvo.templates import Article
    tree = parse_source(reader, source, stream)
    template = template or Article
    cfg = template.Configuration('reader publication', stylesheet=sheet or reader_styles())
    cfg('contents_page', header_text=None, footer_text=None)
    return template(tree, configuration=cfg).render(str(destination))


def source_snapshot(destination, reader, source, environment, stream=False, **options):
    result = call_public(publish_source, destination, reader, source, stream,
                         kwargs=options, cwd=destination.parent, timeout=120)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr, result.warnings)
    return observe_pdf(destination.with_suffix('.pdf'), env=environment)


def assert_source_words(snapshot, *words):
    text = pdf_plain_text(snapshot)
    for word in words:
        assert word in text, (word, text)


def assert_inline_semantics(snapshot):
    plain = token_spans(snapshot, 'Plainmarker')
    assert token_spans(snapshot, 'Emphasismarker')['flags'] & 2
    assert token_spans(snapshot, 'Strongmarker')['flags'] & 16
    assert token_spans(snapshot, 'Codemarker')['flags'] & 8
    assert not plain['flags'] & (2 | 16 | 8)


def assert_block_semantics(snapshot):
    assert_source_words(snapshot, 'Bodymarker', 'Headingmarker', 'Nestedmarker',
                        'Bulletmarker', 'Orderedmarker', 'Quotemarker', 'Literalmarker')
    assert token_spans(snapshot, 'Headingmarker')['size'] > token_spans(snapshot, 'Bodymarker')['size']
    assert token_spans(snapshot, 'Nestedmarker')['size'] < token_spans(snapshot, 'Headingmarker')['size']
    assert list_label_text(snapshot, 'Bulletmarker').strip()
    assert '1' in list_label_text(snapshot, 'Orderedmarker')
    assert token_box(snapshot, 'Quotemarker')['x0'] > token_box(snapshot, 'Bodymarker')['x0']
    assert token_spans(snapshot, 'Literalmarker')['flags'] & 8


def reader_styles():
    """Specify semantic presentation so reader checks do not pin default design."""
    from F05_helpers import caller_sheet
    from talvo.structure import Heading, Section, TableOfContentsSection, Admonition
    from talvo.paragraph import Paragraph
    from talvo.flowable import StaticGroupedFlowables
    from talvo.highlight import CodeBlock
    from talvo.text import StyledText
    from talvo.font import Typeface
    from talvo.reference import NoteMarkerBase
    from talvo.dimension import PT
    from talvo.color import Color
    return caller_sheet([
        ('automatic contents', +TableOfContentsSection, dict(hide=True)),
        ('continuous sections', +Section, dict(page_break=None)),
        ('note labels', +NoteMarkerBase, dict(custom_label=True, label_prefix=None, label_suffix=None, link=True)),
        ('quotation', +StaticGroupedFlowables.like('block quote'), dict(margin_left=20*PT)),
        ('emphasis', +StyledText.like('emphasis'), dict(font_slant='italic')),
        ('strong', +StyledText.like('strong'), dict(font_weight=700)),
        ('inline code', +StyledText.like('monospaced'), dict(typeface=Typeface('courier'))),
        ('code block', +CodeBlock, dict(typeface=Typeface('courier'))),
        ('section', Heading.like(level=1), dict(font_size=18*PT)),
        ('subsection', Heading.like(level=2), dict(font_size=14*PT)),
        ('warning content', +(Admonition / ... / Paragraph), dict(font_color=Color(0, 1, 0))),
    ], base='sphinx')


def assert_reader_note_target(snapshot, links, anchor, target, label):
    """Locate a marker's link and require its destination beside the note text."""
    source = line_containing(snapshot, anchor)
    text = source['text']
    start = text.index(anchor) + len(anchor)
    chars = [c for span in source['spans'] for c in span['chars']]
    remaining = chars[start:]
    while remaining and remaining[0]['c'].isspace():
        remaining = remaining[1:]
    selected = remaining[:len(label)]
    assert ''.join(c['c'] for c in selected) == label
    x = sum(c['origin'][0] for c in selected) / len(selected)
    y = sum((c['bbox'][1] + c['bbox'][3])/2 for c in selected) / len(selected)
    actions = [a for a in links[source['page']]
               if a['from'][0] <= x <= a['from'][2] and a['from'][1] <= y <= a['from'][3]]
    note = token_box(snapshot, target)
    size = token_spans(snapshot, target)['size']
    assert any(a.get('page') == note['page'] and 'to' in a
               and note['y'] - 2*size <= a['to'][1] <= note['y'] + size
               and a['to'][0] <= note['x0'] + size for a in actions), (actions, note)


def assert_source_artwork(destination, snapshot, environment, expected_count):
    """Observe each supplied two-color artwork in pixels, regardless of PDF encoding."""
    from PIL import ImageChops
    from F10_helpers import page_pixels, color_extent
    count = 0
    for index in range(len(snapshot['pages'])):
        image = page_pixels(destination, environment, page=index)
        red, green, blue = image.split()
        mask = ImageChops.multiply(red.point(lambda v: 255 if v > 230 else 0),
                                  green.point(lambda v: 255 if v < 25 else 0))
        mask = ImageChops.multiply(mask, blue.point(lambda v: 255 if v < 25 else 0))
        start = None
        for row in range(image.height + 1):
            present = row < image.height and mask.crop((0, row, image.width, row+1)).getbbox() is not None
            if present and start is None:
                start = row
            if not present and start is not None:
                crop = image.crop((0, start, image.width, row))
                r = color_extent(crop, (255, 0, 0))
                b = color_extent(crop, (0, 0, 255))
                assert r[2] <= b[0] + 1 and abs(r[1]-b[1]) <= 1
                count += 1
                start = None
    assert count == expected_count, count
