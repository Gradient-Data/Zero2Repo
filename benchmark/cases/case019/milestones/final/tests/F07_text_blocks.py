# feature: F07
"""Acceptance tests for text layout, structured content and inline glossary."""
import sys

import pytest
from talvo.color import HexColor
from talvo.dimension import PT
from talvo.font import Typeface
from talvo.paragraph import (Paragraph, ParagraphStyle, TabStop, TabStopList,
    ProportionalSpacing, FixedSpacing, DefaultSpacing, Leading, SINGLE, STANDARD, DOUBLE)
from talvo.text import (SingleStyledText, MixedStyledText, TextStyle, StyledText,
                        Superscript, Subscript, NoBreakAfter)
from talvo.style import StyleSheet
from talvo.structure import Admonition
from talvo.glossary import GlossaryTerm, GlossaryTermStyle
from talvo.warnings import TalvoWarning
from _helpers import call_public, observe_pdf
from F01_helpers import pdf_observer_environment
from F02_helpers import pdf_plain_text
from F05_helpers import (caller_sheet, assert_token_style,
                         token_spans)
from F07_helpers import (rst_snapshot, visible_lines, line_containing, token_box,
                          independent_hyphenator, text_snapshot, render_content_document, insertion_text, supply_hyphenation_dictionary, list_label_text)


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


@pytest.fixture
def layout_sheet():
    return caller_sheet([('layout', Paragraph, dict(typeface=Typeface.from_string('courier'),
        font_size=12*PT, text_align='left', hyphenate=False,
        no_break_after=NoBreakAfter([])))], base='sphinx_article')


def test_inline_styles_nesting_and_width(tmp_path, observer, layout_sheet):
    source = ('Normal *Emphasis* **Strong** ``Literal`` '
              ':sup:`Raised` :sub:`Lowered`.\n\n' + 'alpha beta gamma delta ' * 20)
    snap = rst_snapshot(tmp_path / 'inline', source, layout_sheet, observer)
    for token in ('Normal', 'Emphasis', 'Strong', 'Literal', 'Raised', 'Lowered'):
        token_box(snap, token)
    assert token_spans(snap, 'Emphasis')['flags'] & 2
    assert token_spans(snap, 'Strong')['flags'] & 16
    assert token_spans(snap, 'Literal')['flags'] & 8
    normal = token_spans(snap, 'Normal')
    assert token_spans(snap, 'Raised')['size'] < normal['size']
    assert token_box(snap, 'Raised')['y'] < token_box(snap, 'Normal')['y']
    assert token_spans(snap, 'Lowered')['size'] < normal['size']
    assert token_box(snap, 'Lowered')['y'] > token_box(snap, 'Normal')['y']
    body = [l for l in visible_lines(snap) if 'alpha' in l['text'] or 'beta' in l['text']]
    assert len(body) > 1
    for line in body:
        assert line['bbox'][0] >= 39.9
        assert line['bbox'][2] <= snap['pages'][line['page']]['rect'][2]-39.9
    for word in ('alpha', 'beta', 'gamma', 'delta'):
        assert pdf_plain_text(snap).split().count(word) == 20
    inner = SingleStyledText('Nested', style=TextStyle(font_color=HexColor('204080')))
    outer = MixedStyledText([SingleStyledText('Outer '), inner],
                            style=TextStyle(font_size=19*PT))
    nested = text_snapshot(tmp_path / 'nested', [Paragraph(outer)], layout_sheet, observer)
    assert_token_style(nested, 'Nested', size=19, color=0x204080)
    assert_token_style(nested, 'Outer', size=19)


def test_alignment_indent_spacing_and_tabs(tmp_path, observer, layout_sheet):
    width = 180
    for align in ('left', 'right', 'center', 'justify'):
        text = 'Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu'
        style = ParagraphStyle(margin_right=(520-width)*PT, text_align=align, hyphenate=False)
        snap = text_snapshot(tmp_path / align, [Paragraph(text, style=style)], layout_sheet, observer)
        lines = visible_lines(snap)
        assert len(lines) > 1
        assert ' '.join(word for l in lines for word in l['text'].split()) == text
        for line in lines[:-1]:
            x0, _, x1, _ = line['bbox']
            if align in ('left', 'justify'):
                assert x0 == pytest.approx(40, abs=.05)
            if align in ('right', 'justify'):
                assert x1 == pytest.approx(40+width, abs=.05)
            if align == 'center':
                assert (x0+x1)/2 == pytest.approx(40+width/2, abs=.05)
    snap = text_snapshot(tmp_path / 'indent', [Paragraph(
        'One two three four five six seven eight nine ten eleven twelve',
        style=ParagraphStyle(margin_right=360*PT, indent_first=23*PT,
                             line_spacing=FixedSpacing(29*PT)))], layout_sheet, observer)
    lines = visible_lines(snap)
    assert len(lines) > 2
    assert lines[0]['bbox'][0] == pytest.approx(63, abs=.05)
    assert lines[1]['bbox'][0] == pytest.approx(40, abs=.05)
    ys = [l['spans'][0]['origin'][1] for l in lines]
    assert all(b-a == pytest.approx(29, abs=.05) for a,b in zip(ys,ys[1:]))
    for align in ('left', 'right', 'center'):
        snap = text_snapshot(tmp_path / ('tab'+align), [Paragraph('Start\tTabtext',
            style=ParagraphStyle(tab_stops=TabStopList([TabStop(150*PT, align)])))], layout_sheet, observer)
        a = token_box(snap, 'Tabtext')
        actual = a['x0'] if align == 'left' else a['x1'] if align == 'right' else (a['x0']+a['x1'])/2
        assert actual == pytest.approx(190, abs=.05)


def test_source_whitespace_literal_lines_and_nonbreaking_space(tmp_path, observer, layout_sheet):
    source = ('Sourcefirst\nSourcesecond\n\nLiteral::\n\n'
              '    Literalfirst\n        Literalindented\n    Literallast\n\n'
              '| Linefirst\n|    Lineindented\n| Linelast\n')
    snap = rst_snapshot(tmp_path / 'whitespace', source, layout_sheet, observer)
    assert 'Sourcefirst Sourcesecond' in line_containing(snap, 'Sourcefirst')['text']
    for first, second, last in [('Literalfirst','Literalindented','Literallast'),
                                ('Linefirst','Lineindented','Linelast')]:
        a,b,c = [token_box(snap, t) for t in (first,second,last)]
        assert a['y'] < b['y'] < c['y']
        assert b['x0'] > a['x0']
        assert c['x0'] == pytest.approx(a['x0'], abs=.05)
    for index, separator in enumerate((' ', '\N{NO-BREAK SPACE}')):
        snap = text_snapshot(tmp_path / f'nbsp{index}', [Paragraph(
            'aaaa bbbb red'+separator+'blue tail', style=ParagraphStyle(margin_right=415*PT))], layout_sheet, observer)
        assert pdf_plain_text(snap) == 'aaaa bbbb red blue tail'
        red, blue = token_box(snap, 'red'), token_box(snap, 'blue')
        if index:
            assert red['y'] == pytest.approx(blue['y'], abs=.05)
        else:
            assert red['y'] < blue['y']


def test_dictionary_hyphenation_language_minimum_and_disable(tmp_path, observer):
    # The independent dictionaries supply permitted positions, not a particular
    # greedy line-breaking algorithm; any permitted break is accepted.
    scenarios = [('conversations', None, None, True, 65),
                 ('conversations', 'en_US', 2, True, 65),
                 ('Gesellschaft', 'de_DE', 2, True, 65),
                 ('international', 'en_US', 4, True, 90),
                 ('conversations', 'en_US', 2, False, 65)]
    for index, (word, language, minimum, enabled, width) in enumerate(scenarios):
        options = dict(typeface=Typeface.from_string('courier'), font_size=12*PT,
                       margin_right=(520-width)*PT, text_align='left', no_break_after=NoBreakAfter([]))
        if language is not None:
            options.update(hyphen_lang=language, hyphen_chars=minimum, hyphenate=enabled)
        supply_hyphenation_dictionary(tmp_path, language or 'en_US')
        sheet = caller_sheet([('hyphenation', Paragraph, options)])
        snap = text_snapshot(tmp_path / f'hyphen{index}', [Paragraph(word)], sheet, observer)
        parts = [l['text'].strip() for l in visible_lines(snap)]
        assert ''.join(p.rstrip('-') for p in parts) == word
        if enabled:
            assert len(parts) > 1, parts
            allowed = set(independent_hyphenator(tmp_path / 'dictionary', language or 'en_US', minimum or 2).positions(word))
            offset = 0
            for part in parts[:-1]:
                assert part.endswith('-'), parts
                offset += len(part)-1
                assert offset in allowed, (word, parts, allowed)
                assert offset >= (minimum or 2) and len(word)-offset >= (minimum or 2)
        else:
            assert parts == [word]


def test_sections_nested_lists_and_definition_labels(tmp_path, observer, layout_sheet):
    source = '''Introbody

Parent heading
==============

Parentbody

Child heading
-------------

Childbody

* Bulletfirst

  * Bulletnested

* Bulletlast

1. Numberfirst

   1. Numbernested

2. Numberlast

Termfirst
    Definitionfirst

    Termnested
        Definitionnested

Termlast
    Definitionlast
'''
    snap = rst_snapshot(tmp_path / 'structure', source, layout_sheet, observer)
    text = pdf_plain_text(snap)
    ordered = ['Parent heading','Parentbody','Child heading','Childbody',
               'Bulletfirst','Bulletnested','Bulletlast','Numberfirst','Numbernested',
               'Numberlast','Termfirst','Definitionfirst','Termnested','Definitionnested',
               'Termlast','Definitionlast']
    assert [text.index(t) for t in ordered] == sorted(text.index(t) for t in ordered)
    for outer, nested, last in [('Bulletfirst','Bulletnested','Bulletlast'),
                                ('Numberfirst','Numbernested','Numberlast'),
                                ('Definitionfirst','Definitionnested','Definitionlast')]:
        a,b,c = [token_box(snap,t) for t in (outer,nested,last)]
        assert b['x0'] > a['x0']
        assert c['x0'] == pytest.approx(a['x0'], abs=.05)
    assert token_spans(snap, 'Parent heading')['size'] > token_spans(snap, 'Parentbody')['size']
    assert token_spans(snap, 'Child heading')['size'] > token_spans(snap, 'Childbody')['size']
    for term, body in [('Termfirst','Definitionfirst'),('Termnested','Definitionnested'),('Termlast','Definitionlast')]:
        assert token_box(snap,body)['x0'] > token_box(snap,term)['x0']
    # Enumeration must advance; a bullet label copied to every item is not
    # enumeration. Neither numbering alphabet nor decoration is prescribed.
    assert list_label_text(snap, 'Numberfirst') != list_label_text(snap, 'Numberlast')
    # Labels must actually be rendered, without prescribing their decoration.
    for token in ('Bulletfirst','Bulletnested','Bulletlast','Numberfirst','Numbernested','Numberlast'):
        body = token_box(snap,token)
        assert any(l['text'].strip() and l['bbox'][0] < body['x0']-.1
                   and l['page'] == body['page']
                   and abs(l['spans'][0]['origin'][1]-body['y']) < .1 for l in visible_lines(snap))


def test_quotations_fields_options_rules_and_admonition_titles(tmp_path, observer, layout_sheet):
    source = '''Ordinarybody

    Quotedbody

:Fieldname: Fieldbody

--orchard  Optionbody

AboveRule

----------

BelowRule

.. admonition:: Customtitle

   Advicebody
'''
    for index, inline in enumerate((True, False)):
        sheet = caller_sheet([('admonition layout', Admonition, dict(inline_title=inline))], base=layout_sheet)
        snap = rst_snapshot(tmp_path / f'blocks{index}', source, sheet, observer)
        for token in ('Ordinarybody','Quotedbody','Fieldname','Fieldbody','--orchard',
                      'Optionbody','AboveRule','BelowRule','Customtitle','Advicebody'):
            token_box(snap,token)
        assert token_box(snap,'Quotedbody')['x0'] > token_box(snap,'Ordinarybody')['x0']
        for label, body in [('Fieldname','Fieldbody'),('--orchard','Optionbody')]:
            assert token_box(snap,body)['x0'] > token_box(snap,label)['x1']
        a,b = token_box(snap,'AboveRule'), token_box(snap,'BelowRule')
        assert any(a['y'] < d['rect'][1] < b['y'] and d['rect'][2] > d['rect'][0]
                   for page in snap['pages'] for d in page['drawings'])
        title,body = token_box(snap,'Customtitle'), token_box(snap,'Advicebody')
        if inline:
            assert title['y'] == pytest.approx(body['y'], abs=.05)
            assert title['x1'] < body['x0']
        else:
            assert title['y'] < body['y']


def test_code_language_highlighting_and_whitespace(tmp_path, observer, layout_sheet):
    from pygments.style import Style
    from pygments.token import Keyword, Name, String, Number, Comment
    from talvo.highlight import CodeBlock, pygments_style_to_stylesheet
    class CallerHighlight(Style):
        styles = {Keyword: '#b02030', Name: '#207040', String: '#2040b0',
                  Number: '#8030a0', Comment: '#707070'}
    sheet = pygments_style_to_stylesheet(CallerHighlight, base=layout_sheet)
    code = 'while orchard:\n    fruit = "pear"\n    if fruit:\n        amount = 37 # harvest\n'
    snap = text_snapshot(tmp_path / 'code', [CodeBlock(code, language='python')], sheet, observer)
    assert [l['text'].strip() for l in visible_lines(snap)] == [line.strip() for line in code.splitlines()]
    for token, color in [('while',0xb02030),('orchard',0x207040),('"pear"',0x2040b0),
                         ('37',0x8030a0),('# harvest',0x707070)]:
        assert_token_style(snap,token,color=color)
    # Indentation is read as geometry, accepting equivalent PDFs that position
    # the first visible glyph without emitting leading space characters.
    edge = token_box(snap,'while')['x0']
    indent = token_box(snap,'fruit =')['x0']-edge
    assert indent > 0
    assert token_box(snap,'amount')['x0']-edge == pytest.approx(2*indent, abs=.05)


def test_glossary_policies_conflicts_and_missing_definitions(tmp_path, observer, layout_sheet):
    for index, policy in enumerate((None,'always','never')):
        style = None if policy is None else GlossaryTermStyle(show_definition=policy)
        elements = [Paragraph([SingleStyledText(f'Use{n} '), GlossaryTerm(
            SingleStyledText('Arboretum'), SingleStyledText('Treecollection'), style=style)])
                    for n in range(3)]
        snap = text_snapshot(tmp_path / f'glossary{index}', elements, layout_sheet, observer)
        text = pdf_plain_text(snap)
        assert text.count('Arboretum') == 3
        assert text.count('Treecollection') == (1 if policy is None else 3 if policy == 'always' else 0)
        if policy is None:
            assert text.index('Use0') < text.index('Treecollection') < text.index('Use1')
    elements = [Paragraph(GlossaryTerm(SingleStyledText('Canopy'), SingleStyledText('Firstmeaning'),
                                      style=GlossaryTermStyle(show_definition='always'))),
                Paragraph(GlossaryTerm(SingleStyledText('Canopy'), SingleStyledText('Othermeaning'),
                                      style=GlossaryTermStyle(show_definition='always'))),
                Paragraph(GlossaryTerm(SingleStyledText('Rootstock')))]
    dest = tmp_path / 'warnings'
    result = call_public(render_content_document,dest,elements,layout_sheet)
    assert result.exception is None, result.traceback
    assert result.value is True
    snap = observe_pdf(dest.with_suffix('.pdf'),env=observer)
    text = pdf_plain_text(snap)
    assert text.count('Canopy') == 2 and text.count('Firstmeaning') == 2
    assert 'Othermeaning' not in text and 'Rootstock' in text
    messages = [str(message) for category,message,filename,line in result.warnings
                if issubclass(category,TalvoWarning)]
    # Warning identity is its category and refused term, not its free prose.
    assert any('Canopy' in message for message in messages), messages
    assert any('Rootstock' in message for message in messages), messages


def test_proportional_spacing_presets_and_largest_inline_size(tmp_path, observer, layout_sheet):
    for index, (spacing,factor) in enumerate([(SINGLE,1),(STANDARD,1.2),(DOUBLE,2),
                                              (ProportionalSpacing(1.65),1.65)]):
        content = [SingleStyledText('Firstline\n'),
                   SingleStyledText('Large',style=TextStyle(font_size=20*PT)),
                   SingleStyledText(' small\nLastline')]
        snap = text_snapshot(tmp_path / f'proportional{index}',
            [Paragraph(content,style=ParagraphStyle(line_spacing=spacing))],layout_sheet,observer)
        for token,size in [('Firstline',12),('Large',20),('Lastline',12)]:
            assert_token_style(snap,token,size=size)
        first,large,last = [token_box(snap,t)['y'] for t in ('Firstline','Large','Lastline')]
        assert large-first == pytest.approx(factor*20,abs=.05)
        assert last-large == pytest.approx(factor*12,abs=.05)

    from F04_helpers import ASSETS, FONT_FILES, font_observer_environment, supplied_typeface
    from F07_helpers import typographic_metrics
    environment = font_observer_environment(tmp_path / 'metric-observer')
    # Two actual fonts and different span sizes separate typographic bounds
    # from glyph ink and from a multiple of the largest font size.
    first_font, second_font = supplied_typeface('ttf'), supplied_typeface('otf')
    previous = typographic_metrics(ASSETS / FONT_FILES['ttf'], 12, environment)
    upper = typographic_metrics(ASSETS / FONT_FILES['otf'], 20, environment)
    lower = typographic_metrics(ASSETS / FONT_FILES['ttf'], 16, environment)
    snap = text_snapshot(tmp_path / 'recommended', [Paragraph([
        SingleStyledText('Firstmetric\n', style=TextStyle(typeface=first_font)),
        SingleStyledText('Uppermetric ', style=TextStyle(typeface=second_font, font_size=20*PT)),
        SingleStyledText('Lowermetric', style=TextStyle(typeface=first_font, font_size=16*PT))],
        style=ParagraphStyle(line_spacing=DefaultSpacing()))], layout_sheet, observer)
    assert_token_style(snap, 'Uppermetric', size=20)
    assert_token_style(snap, 'Lowermetric', size=16)
    assert token_box(snap, 'Uppermetric')['y'] == pytest.approx(token_box(snap, 'Lowermetric')['y'], abs=.05)
    expected = max(upper[0], lower[0]) - previous[1] + max(upper[2], lower[2])
    assert token_box(snap, 'Uppermetric')['y'] - token_box(snap, 'Firstmetric')['y'] == pytest.approx(expected, abs=.05)


def test_fixed_baseline_spacing_and_minimum(tmp_path, observer, layout_sheet):
    for index, (spacing,expected) in enumerate([
        (FixedSpacing(31*PT),31), (FixedSpacing(7*PT),20),
        (FixedSpacing(7*PT,minimum=ProportionalSpacing(1.5)),30),
        (FixedSpacing(7*PT,minimum=None),7)]):
        snap = text_snapshot(tmp_path / f'fixed{index}', [Paragraph([
            SingleStyledText('Firstline\n'),SingleStyledText('Large',style=TextStyle(font_size=20*PT))],
            style=ParagraphStyle(line_spacing=spacing))],layout_sheet,observer)
        assert_token_style(snap,'Large',size=20)
        assert token_box(snap,'Large')['y']-token_box(snap,'Firstline')['y'] == pytest.approx(expected,abs=.05)

    from F04_helpers import ASSETS, FONT_FILES, font_observer_environment, supplied_typeface
    from F07_helpers import typographic_metrics
    environment = font_observer_environment(tmp_path / 'metric-observer')
    family = supplied_typeface('ttf')
    previous = typographic_metrics(ASSETS / FONT_FILES['ttf'], 12, environment)
    current = typographic_metrics(ASSETS / FONT_FILES['ttf'], 20, environment)
    gap = 9
    snap = text_snapshot(tmp_path / 'text-bound-gap', [Paragraph([
        SingleStyledText('Firstbound\n', style=TextStyle(typeface=family)),
        SingleStyledText('Secondbound', style=TextStyle(typeface=family, font_size=20*PT))],
        style=ParagraphStyle(line_spacing=Leading(gap*PT)))], layout_sheet, observer)
    assert_token_style(snap, 'Secondbound', size=20)
    assert token_box(snap, 'Secondbound')['y'] - token_box(snap, 'Firstbound')['y'] == pytest.approx(current[0] - previous[1] + gap, abs=.05)


def test_styled_insertions_before_and_after_paragraph_and_inline(tmp_path, observer, layout_sheet):
    sheet = caller_sheet([
        ('paragraph wrapper',Paragraph.like('wrapped'),dict(font_size=22*PT,
            before=insertion_text('Parbefore ','c02040',15),after=insertion_text(' Parafter','2040c0',17))),
        ('inline wrapper',StyledText.like('wrapped'),dict(font_size=12*PT,
            before=insertion_text('Inbefore ','208040',14),after=insertion_text(' Inafter','8020a0',16)))],base=layout_sheet)
    snap = text_snapshot(tmp_path / 'insertions', [Paragraph([
        SingleStyledText('Begin '),SingleStyledText('Center',style='wrapped'),
        SingleStyledText(' End')],style='wrapped')],sheet,observer)
    assert pdf_plain_text(snap) == 'Parbefore Begin Inbefore Center Inafter End Parafter'
    for token,color,size in [('Parbefore',0xc02040,15),('Parafter',0x2040c0,17),
                             ('Inbefore',0x208040,14),('Inafter',0x8020a0,16)]:
        assert_token_style(snap,token,color=color,size=size)
    assert_token_style(snap,'Center',size=12)


def test_no_break_after_words_and_explicit_empty_list(tmp_path, observer, layout_sheet):
    for index, protected in enumerate((['red'],[])):
        snap = text_snapshot(tmp_path / f'protect{index}',[Paragraph('aaaa bbbb red blue tail',
            style=ParagraphStyle(margin_right=415*PT,no_break_after=NoBreakAfter(protected)))],layout_sheet,observer)
        assert pdf_plain_text(snap) == 'aaaa bbbb red blue tail'
        assert len(visible_lines(snap)) > 1
        red,blue = token_box(snap,'red'),token_box(snap,'blue')
        if protected:
            assert red['y'] == pytest.approx(blue['y'],abs=.05)
        else:
            assert red['y'] < blue['y']
