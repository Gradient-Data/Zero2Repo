# feature: F16
"""Acceptance coverage for built-in and caller-defined document templates."""
import sys

import pytest
from talvo.attribute import Var
from talvo.dimension import PT
from talvo.flowable import PageBreak
from talvo.paragraph import Paragraph
from talvo.paper import Paper
from talvo.templates import Article, Book
from talvo.template import TemplateConfigurationFile
from talvo.structure import Section, Heading
from talvo.text import SingleStyledText
from talvo.strings import Strings, StringField
from talvo.language import Language
from F01_helpers import pdf_observer_environment
from F05_helpers import caller_sheet, assert_token_style
from F07_helpers import visible_lines, line_containing, token_box
from F08_helpers import FlowDocument
from F11_helpers import table_row
from F16_helpers import (template_snapshot, footer_labels, assert_tex_gyre,
                         render_template, page_label_field)
from _helpers import call_public, write_text


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


def test_article_title_abstract_columns_and_numbering(tmp_path, observer):
    snapshots = []
    abstract = ' '.join(['Abstractmarker'] + ['orchards and rivers'] * 16)
    for location in (None, 'body'):
        options = {} if location is None else dict(abstract_location=location)
        cfg = Article.Configuration('article layout', **options)
        cfg('contents_page', columns=2, footer_text=page_label_field(), title_page_footer_text=page_label_field())
        snap = template_snapshot(tmp_path / ('article' + str(location)), Article, cfg,
            [Paragraph('Bodymarker'), PageBreak(), Paragraph('Secondmarker'),
             PageBreak(), Paragraph('Thirdmarker')], observer,
            dict(title=SingleStyledText('Titlemarker'), subtitle=SingleStyledText('Subtitlemarker'),
                 author=SingleStyledText('Authormarker'), abstract=Paragraph(abstract)))
        for token in ('Titlemarker', 'Subtitlemarker', 'Authormarker', 'Bodymarker'):
            assert line_containing(snap, token)['page'] == 0
        assert token_box(snap, 'Titlemarker')['y'] < token_box(snap, 'Subtitlemarker')['y'] < token_box(snap, 'Authormarker')['y'] < token_box(snap, 'Bodymarker')['y']
        assert footer_labels(snap) == [str(i + 1) for i in range(len(snap['pages']))]
        assert_tex_gyre(snap, 'Bodymarker')
        abstract_lines = [line for line in visible_lines(snap) if 'orchards' in line['text']]
        assert abstract_lines
        line_containing(snap, 'Abstractmarker')
        snapshots.append(max(line['bbox'][2] - line['bbox'][0] for line in abstract_lines))
    page_width = snap['pages'][0]['rect'][2]
    assert snapshots[0] > page_width / 2
    assert snapshots[1] < page_width / 2


def test_book_parts_navigation_and_numbering(tmp_path, observer):
    from talvo.image import Figure, Caption
    from talvo.table import Table, TableBody, TableWithCaption
    from talvo.index import IndexTarget, IndexTerm
    elements = [Section([Heading('Chaptermarker'), Paragraph('Bodymarker'),
        IndexTarget([IndexTerm('Zebraterm')]),
        Figure([Paragraph('Artworkmarker'), Caption('Figuremarker')]),
        TableWithCaption([Table(TableBody([table_row('Cellmarker')])), Caption('Tablemarker')]),
        PageBreak(), Paragraph('Lastbodymarker')])]
    cfg = Book.Configuration('book page labels')
    for name in ('front_matter_page', 'front_matter_left_page', 'front_matter_right_page',
                 'contents_page', 'contents_left_page', 'contents_right_page',
                 'back_matter_page', 'back_matter_left_page', 'back_matter_right_page'):
        cfg(name, footer_text=page_label_field(), chapter_footer_text=page_label_field())
    snap = template_snapshot(tmp_path / 'book', Book, cfg, elements, observer,
        dict(date='2020-01-01', title='Booktitlemarker', subtitle='Booksubtitlemarker',
             author='Bookauthormarker'))
    labels = footer_labels(snap)
    body = line_containing(snap, 'Bodymarker')['page']
    last = line_containing(snap, 'Lastbodymarker')['page']
    assert line_containing(snap, 'Bookauthormarker')['page'] < body
    for token in ('Chaptermarker', 'Figuremarker', 'Tablemarker'):
        occurrences = [line for line in visible_lines(snap) if token in line['text']]
        front_occurrences = [line for line in occurrences if line['page'] < body]
        assert front_occurrences, (token, occurrences)
        assert all(labels[line['page']] and set(labels[line['page']]) <= set('ivxlcdm') for line in front_occurrences)
        assert any(line['page'] >= body for line in occurrences)
    front = [i for i in range(body) if labels[i] is not None]
    assert front and labels[front[0]] == 'i'
    assert len(set(labels[i] for i in front)) == len(front)
    assert all(set(labels[i]) <= set('ivxlcdm') for i in front)
    assert labels[body] == '1'
    assert labels[last] == str(last - body + 1)
    index = line_containing(snap, 'Zebraterm')['page']
    assert index > last
    assert labels[index] == str(index - body + 1)
    assert_tex_gyre(snap, 'Bodymarker')
    # Control without figures, tables or index terms: the front matter keeps
    # only the contents (no empty lists) and the back matter adds no index.
    plain = template_snapshot(tmp_path / 'plainbook', Book, cfg,
        [Section([Heading('Chaptermarker'), Paragraph('Bodymarker'), PageBreak(),
                  Paragraph('Lastbodymarker')])], observer,
        dict(date='2020-01-01', title='Booktitlemarker', subtitle='Booksubtitlemarker',
             author='Bookauthormarker'))
    plain_labels = footer_labels(plain)
    plain_body = line_containing(plain, 'Bodymarker')['page']
    plain_last = line_containing(plain, 'Lastbodymarker')['page']
    def content(line):
        return line['text'].strip() and not line['text'].startswith('PageLabel')
    roman = [line for line in visible_lines(plain) if content(line) and line['page'] < plain_body
             and plain_labels[line['page']] and set(plain_labels[line['page']]) <= set('ivxlcdm')]
    assert roman, visible_lines(plain)
    # Contents title, the entry's number, title and page; nothing listing figures/tables.
    others = [line['text'] for line in roman if 'Chaptermarker' not in line['text']
              and not line['text'].strip().isdigit()]
    assert len(others) <= 1, others
    assert not [line['text'] for line in visible_lines(plain)
                if line['page'] > plain_last and content(line)]


def test_programmatic_inheritance_variables_and_overrides(tmp_path, observer):
    from talvo.stylesheets import sphinx_article
    sheet = caller_sheet([('body override', Paragraph, dict(font_size=17*PT))], base=sphinx_article)
    strings = Strings()
    strings['@chapter'] = 'Chapterreplacement'
    base = Book.Configuration('base', parts=['contents'], language=Language.from_string('fr'), strings=strings, stylesheet=sheet)
    base('contents_page', page_size=Paper('inherited', 480*PT, 620*PT), left_margin=60*PT,
         header_text=Var('decoration'), footer_text=Var('decoration'))
    for name in ('contents_right_page', 'contents_left_page'):
        base(name, base='contents_page', header_text=Var('decoration'), footer_text=Var('decoration'), chapter_header_text=Var('decoration'), chapter_footer_text=Var('decoration'))
    cfg = Book.Configuration('derived', base=base)
    cfg.variables['decoration'] = SingleStyledText('Shareddecoration')
    cfg('contents_page', right_margin=90*PT)
    snap = template_snapshot(tmp_path / 'inherit', Book, cfg,
        [Section([Heading('Chapterheading'), Paragraph('Styledmarker'), Paragraph(StringField('chapter')), Paragraph(' '.join(['boundaryword'] * 20)), PageBreak(), Paragraph('Nextmarker')])], observer)
    assert all(page['rect'][2:] == pytest.approx([480, 620], abs=.01) for page in snap['pages'])
    assert_token_style(snap, 'Styledmarker', size=17)
    assert 'Chapterreplacement' in snap['pages'][0]['text']
    for page in snap['pages'][:2]:
        assert page['text'].count('Shareddecoration') == 2
    assert token_box(snap, 'Styledmarker')['x0'] == pytest.approx(60, abs=.1)
    boundary = [line for line in visible_lines(snap) if 'boundaryword' in line['text']]
    assert max(line['bbox'][2] for line in boundary) == pytest.approx(390, abs=.1)
    # Language is inherited independently of a caller's standard-string override.
    from talvo.structure import Admonition, AdmonitionFlowables
    from talvo.flowable import DummyFlowable
    snap2 = template_snapshot(tmp_path / 'language', Book, cfg,
        [Section([Heading('Languageheading'), Admonition(DummyFlowable(),
            AdmonitionFlowables([Paragraph('Advicebody')]), type='warning')])], observer)
    assert 'Avertissement' in snap2['pages'][0]['text']


def test_configuration_relative_base_and_stylesheet(tmp_path, observer):
    root = tmp_path / 'configuration'
    write_text(root / 'styles' / 'body.rts', '[STYLESHEET]\nname = caller style\nbase = sphinx_article\n\n[body]\nfont_size = 19pt\n')
    write_text(root / 'base' / 'base.rtt', '[TEMPLATE_CONFIGURATION]\nname = base\ntemplate = article\nstylesheet = ../styles/body.rts\n\n[contents_page]\nleft_margin = 71pt\nheader_text = \'Inheritedheader\'\ntitle_page_header_text = \'Inheritedheader\'\n')
    derived = write_text(root / 'child.rtt', '[TEMPLATE_CONFIGURATION]\nname = child\nbase = base/base.rtt\n\n[contents_page]\nright_margin = 83pt\n')
    cfg = TemplateConfigurationFile(str(derived))
    snap = template_snapshot(tmp_path / 'relative', cfg.template, cfg,
        [Paragraph('Relativebody'), Paragraph(' '.join(['relativeboundary'] * 18))], observer)
    assert_token_style(snap, 'Relativebody', size=19)
    assert token_box(snap, 'Relativebody')['x0'] == pytest.approx(71, abs=.1)
    line_containing(snap, 'Inheritedheader')
    boundary = [line for line in visible_lines(snap) if 'relativeboundary' in line['text']]
    assert max(line['bbox'][2] for line in boundary) == pytest.approx(snap['pages'][0]['rect'][2] - 83, abs=.1)


def test_custom_parts_and_specific_page_precedence(tmp_path, observer):
    cfg = FlowDocument.Configuration('custom arrangement', parts=['front', 'contents', 'tail'])
    cfg('front', flowables=[Paragraph('Frontmarker')])
    cfg('tail', flowables=[Paragraph('Tailmarker')])
    for name in ('front_page', 'tail_page'):
        cfg(name, page_size=Paper('custom', 450*PT, 420*PT), left_margin=35*PT)
    cfg('contents_page', page_size=Paper('custom', 450*PT, 420*PT), left_margin=50*PT, top_margin=65*PT, header_footer_distance=5*PT, header_text=SingleStyledText('Generalheader'))
    cfg('contents_right_page', base='contents_page', left_margin=80*PT, header_text=SingleStyledText('Rightheader'), chapter_header_text=SingleStyledText('Rightheader'))
    cfg('contents_left_page', base='contents_page', left_margin=110*PT, header_text=SingleStyledText('Leftheader'), chapter_header_text=SingleStyledText('Leftheader'))
    snap = template_snapshot(tmp_path / 'custom', FlowDocument, cfg,
        [Paragraph('Firstbody'), PageBreak(), Paragraph('Secondbody'), PageBreak(), Paragraph('Thirdbody')], observer)
    front, tail = [token_box(snap, token)['page'] for token in ('Frontmarker', 'Tailmarker')]
    # Which page counts as left or right is not fixed; consecutive body pages
    # alternate sides, and each page's margin and header come from one side.
    sides = []
    for token in ('Firstbody', 'Secondbody', 'Thirdbody'):
        box = token_box(snap, token)
        assert front < box['page'] < tail
        right = box['x0'] == pytest.approx(80, abs=.1)
        assert right or box['x0'] == pytest.approx(110, abs=.1), box
        text = snap['pages'][box['page']]['text']
        assert ('Rightheader' if right else 'Leftheader') in text
        assert ('Leftheader' if right else 'Rightheader') not in text
        assert 'Generalheader' not in text
        sides.append((box['page'], right))
    assert [page for page, _ in sides] == list(range(sides[0][0], sides[0][0] + 3))
    assert sides[0][1] != sides[1][1] != sides[2][1]
    assert all(page['rect'][2:] == pytest.approx([450, 420], abs=.01) for page in snap['pages'])


def test_invalid_options_and_unknown_components(tmp_path, observer):
    valid = template_snapshot(tmp_path / 'valid', Article, Article.Configuration('valid'), [Paragraph('Validbody')], observer)
    line_containing(valid, 'Validbody')
    def unsupported():
        cfg = Article.Configuration('invalid', unsupported_option=True)
        return render_template(tmp_path / 'unsupported', Article, cfg, [Paragraph('Body')])
    result = call_public(unsupported)
    assert isinstance(result.exception, TypeError), result
    for name in ('missing_part', 'missing_page'):
        path = write_text(tmp_path / (name + '.rtt'), '[TEMPLATE_CONFIGURATION]\nname = invalid\ntemplate = article\n\n[' + name + ']\n')
        def unknown():
            cfg = TemplateConfigurationFile(str(path))
            return render_template(tmp_path / name, cfg.template, cfg, [Paragraph('Body')])
        result = call_public(unknown)
        assert isinstance(result.exception, ValueError), result
