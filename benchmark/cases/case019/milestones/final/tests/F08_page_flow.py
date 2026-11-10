# feature: F08
"""Acceptance checks for physical pages, flow controls and document parts."""
import sys

from collections import Counter
import pytest

from talvo.dimension import PT
from talvo.paper import Paper
from talvo.paragraph import Paragraph, ParagraphStyle
from talvo.flowable import PageBreak
from talvo.structure import Section, Heading
from talvo.text import MixedStyledText
from talvo.reference import Field, PAGE_NUMBER
from F01_helpers import pdf_observer_environment
from F02_helpers import pdf_plain_text
from F07_helpers import visible_lines, token_box
from F08_helpers import flow_snapshot


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


def test_page_geometry_margins_orientation_and_columns(tmp_path, observer):
    for orientation in ('portrait', 'landscape'):
        snap = flow_snapshot(tmp_path / orientation, [Paragraph('Geometry')], observer,
            page=dict(page_size=Paper('custom', 370*PT, 260*PT),
                      page_orientation=orientation, left_margin=43*PT))
        expected = (370, 260) if orientation == 'portrait' else (260, 370)
        assert snap['pages'][0]['rect'][2:] == pytest.approx(expected, abs=.02)
        assert token_box(snap, 'Geometry')['x0'] == pytest.approx(43, abs=.05)
    baseline = flow_snapshot(tmp_path / 'topbase', [Paragraph('Topmark')], observer)
    shifted = flow_snapshot(tmp_path / 'topshift', [Paragraph('Topmark')], observer,
                            page=dict(top_margin=53*PT))
    assert token_box(shifted, 'Topmark')['y']-token_box(baseline, 'Topmark')['y'] == pytest.approx(23, abs=.05)
    for columns, gap, bottom in ((1, 0, 30), (2, 26, 30), (3, 14, 54)):
        labels = [f'Row{i:03d}' for i in range(70)]
        snap = flow_snapshot(tmp_path / f'cols{columns}',
            [Paragraph('\n'.join(labels))], observer,
            page=dict(columns=columns, column_spacing=gap*PT, left_margin=41*PT,
                      right_margin=47*PT, bottom_margin=bottom*PT))
        assert Counter(pdf_plain_text(snap).split()) == Counter(labels)
        width = (360-41-47-(columns-1)*gap)/columns
        edges = [41+i*(width+gap) for i in range(columns)]
        lines = visible_lines(snap)
        for edge in edges:
            assert any(l['bbox'][0] == pytest.approx(edge, abs=.05) for l in lines)
        for line in lines:
            assert line['bbox'][3] <= 240-bottom+.05
        right = flow_snapshot(tmp_path / f'right{columns}', [Paragraph('Edge',
            style=ParagraphStyle(text_align='right'))], observer,
            page=dict(columns=columns, column_spacing=gap*PT,
                      left_margin=41*PT, right_margin=47*PT))
        assert token_box(right, 'Edge')['x1'] == pytest.approx(41+width, abs=.05)


def test_paper_sizes_custom_and_default(tmp_path, observer):
    # ISO 216 trimmed A-series table, independently published by ISO at
    # https://www.iso.org/standard/36631.html (millimetres).
    sizes = [(841,1189),(594,841),(420,594),(297,420),(210,297),(148,210),
             (105,148),(74,105),(52,74),(37,52),(26,37)]
    cases = [(f'A{i}', w*72/25.4, h*72/25.4) for i,(w,h) in enumerate(sizes)]
    cases += [(name, w*72, h*72) for name,w,h in [
        ('letter',8.5,11),('legal',8.5,14),('junior legal',8,5),
        ('ledger',17,11),('tabloid',11,17)]]
    cases += [('123pt * 167pt',123,167)]
    for index,(name,w,h) in enumerate(cases):
        snap = flow_snapshot(tmp_path / f'paper{index}', [Paragraph('P')], observer,
            page=dict(page_size=Paper.from_string(name), left_margin=3*PT,
                      right_margin=3*PT, top_margin=3*PT, bottom_margin=3*PT))
        assert snap['pages'][0]['rect'][2:] == pytest.approx((w,h), abs=.02)
        assert pdf_plain_text(snap) == 'P'
    # None explicitly leaves the template's default paper and orientation.
    snap = flow_snapshot(tmp_path / 'default', [Paragraph('Defaultpaper')], observer,
                         page=dict(page_size=None))
    assert snap['pages'][0]['rect'][2:] == pytest.approx((210*72/25.4,297*72/25.4), abs=.02)
    assert pdf_plain_text(snap) == 'Defaultpaper'


def test_continuation_preserves_reading_order_and_content(tmp_path, observer):
    labels = [f'Flow{i:03d}' for i in range(85)]
    snap = flow_snapshot(tmp_path / 'continuation', [Paragraph('\n'.join(labels))],
                         observer, page=dict(columns=2, column_spacing=24*PT))
    lines = visible_lines(snap)
    assert Counter(pdf_plain_text(snap).split()) == Counter(labels)
    assert len(snap['pages']) > 1
    # Geometry determines reading order independently of PDF drawing order.
    ordered = sorted(lines, key=lambda l:(l['page'], l['bbox'][0] > 180, l['bbox'][1]))
    assert [l['text'].strip() for l in ordered] == labels
    assert all(any(l['page']==p and l['bbox'][0]>180 for l in lines)
               for p in range(len(snap['pages'])-1))


def test_explicit_breaks_and_requested_page_sides(tmp_path, observer):
    for mode in ('any','left','right'):
        snap = flow_snapshot(tmp_path / mode, [Paragraph('First'), PageBreak(mode),
            Paragraph('Second'), PageBreak(mode), Paragraph('Third')], observer)
        places = [token_box(snap,t)['page'] for t in ('First','Second','Third')]
        expected = {'any':[0,1,2], 'left':[0,1,3], 'right':[0,2,4]}[mode]
        assert places == expected
        assert pdf_plain_text(snap).split() == ['First','Second','Third']
        for p in set(range(places[-1]+1))-set(places):
            # No body content on inserted blank pages; decorations are off.
            assert not snap['pages'][p]['text'].strip()


def test_keep_with_next_in_fitting_fresh_areas(tmp_path, observer):
    for columns in (1,2):
        for keep in (False,True):
            filler = [f'Fill{i:02d}' for i in range(10)]
            tail = [f'Next{i:02d}' for i in range(4)]
            snap = flow_snapshot(tmp_path / f'keep{columns}{keep}',
                [Paragraph('\n'.join(filler)),
                 Paragraph('Together', style=ParagraphStyle(keep_with_next=keep)),
                 Paragraph('\n'.join(tail))], observer, page=dict(columns=columns))
            assert Counter(pdf_plain_text(snap).split()) == Counter(filler+['Together']+tail)
            if not keep:
                # Without the setting the block stays where it fits (11 lines fit).
                fill, together = token_box(snap,filler[-1]), token_box(snap,'Together')
                assert (together['page'],round(together['x0'],1)) == (fill['page'],round(fill['x0'],1))
            if keep:
                boxes = [token_box(snap,t) for t in ['Together']+tail]
                assert len({(b['page'],round(b['x0'],1)) for b in boxes}) == 1
                assert [b['y'] for b in boxes] == sorted(b['y'] for b in boxes)


def test_paragraph_split_minimum_lines(tmp_path, observer):
    for columns in (1,2):
        for minimum in (None,3,5):
            filler = [f'Prior{i:02d}' for i in range(9)]
            labels = [f'Para{i:02d}' for i in range(8)]
            style = None if minimum is None else ParagraphStyle(split_minimum_lines=minimum)
            snap = flow_snapshot(tmp_path / f'split{columns}{minimum}',
                [Paragraph('\n'.join(filler)),Paragraph('\n'.join(labels),style=style)],
                observer, page=dict(columns=columns))
            assert Counter(pdf_plain_text(snap).split()) == Counter(filler+labels)
            boxes = [token_box(snap,t) for t in labels]
            groups = Counter((b['page'],round(b['x0'],1)) for b in boxes)
            first = (boxes[0]['page'],round(boxes[0]['x0'],1))
            if minimum is not None and len(groups)>1:
                assert groups[first] >= minimum
            prior = token_box(snap,filler[-1])
            if minimum is not None:
                # The current area has fewer than the chosen minimum lines left.
                assert first != (prior['page'],round(prior['x0'],1))
            else:
                # No default minimum: the two lines that fit stay in the current area.
                assert first == (prior['page'],round(prior['x0'],1))
                assert groups[first] < len(labels)


def test_repeated_side_and_chapter_decorations(tmp_path, observer):
    for side_specific in (False,True):
        pages = {}
        if side_specific:
            pages = {'contents_left_page':dict(header_text=MixedStyledText(['Lefthead']),
                                               footer_text=MixedStyledText(['Leftfoot'])),
                     'contents_right_page':dict(header_text=MixedStyledText(['Righthead']),
                                                footer_text=MixedStyledText(['Rightfoot']))}
        snap = flow_snapshot(tmp_path / f'decor{side_specific}',
            [Paragraph('Bodyone'),PageBreak(),Paragraph('Bodytwo'),PageBreak(),Paragraph('Bodythree')],
            observer, page=dict(top_margin=55*PT,bottom_margin=55*PT,
                header_text=MixedStyledText(['Generalhead']),footer_text=MixedStyledText(['Generalfoot'])),
            pages=pages)
        for p,body in enumerate(('Bodyone','Bodytwo','Bodythree')):
            head = ('Righthead' if p%2==0 else 'Lefthead') if side_specific else 'Generalhead'
            foot = ('Rightfoot' if p%2==0 else 'Leftfoot') if side_specific else 'Generalfoot'
            sub = dict(pages=[snap['pages'][p]])
            assert Counter(pdf_plain_text(sub).split()) == Counter([head,body,foot])
            assert token_box(sub,head)['y'] < 55
            assert 55 < token_box(sub,body)['y'] < 185
            assert token_box(sub,foot)['y'] > 185
    body_positions = []
    for height in (45,75):
        snap = flow_snapshot(tmp_path / f'chapter{height}', [Section([
            Heading('Originalheading'),Paragraph('Chapterbody')])], observer,
            page=dict(top_margin=45*PT,bottom_margin=45*PT,
                chapter_title_flowables=[Paragraph('Chaptertitle')],
                chapter_title_height=height*PT,
                chapter_header_text=MixedStyledText(['Chapterhead']),
                chapter_footer_text=MixedStyledText(['Chapterfoot'])))
        assert Counter(pdf_plain_text(snap).split()) == Counter(['Chaptertitle','Chapterbody','Chapterhead','Chapterfoot'])
        title,body = [token_box(snap,t) for t in ('Chaptertitle','Chapterbody')]
        assert 45 <= title['y'] < 45+height
        assert body['y'] >= 45+height
        body_positions.append(body['y'])
        assert token_box(snap,'Chapterhead')['y'] < 45
        assert token_box(snap,'Chapterfoot')['y'] > 195
    assert body_positions[1]-body_positions[0] == pytest.approx(30, abs=.05)


def test_parts_selection_order_empty_omission_and_insertion(tmp_path, observer):
    for parts in (['front','empty','contents','tail'], ['tail','contents','empty','front'],
                  ['contents','tail']):
        snap = flow_snapshot(tmp_path / ('parts'+''.join(parts)),[Paragraph('Main')],observer,
            parts=parts,part_options={
                'front':dict(flowables=[Paragraph('Front')]),
                'tail':dict(flowables=[Paragraph('Tailfirst'),Paragraph('Taillast')]),
                'empty':dict(drop_if_empty=True)}, inserts=[('tail','Inserted',1)])
        texts = {'front':['Front'],'contents':['Main'],
                 'tail':['Tailfirst','Inserted','Taillast'],'empty':[]}
        expected = [word for part in parts for word in texts[part]]
        assert pdf_plain_text(snap).split() == expected
        assert len(snap['pages']) == len(parts)-('empty' in parts)
        assert token_box(snap,'Inserted')['page'] == token_box(snap,'Tailfirst')['page']
    for drop in (False,True):
        snap = flow_snapshot(tmp_path / f'empty{drop}',[Paragraph('Main')],observer,
            parts=['empty','contents'],part_options={'empty':dict(drop_if_empty=drop)})
        assert pdf_plain_text(snap) == 'Main'
        assert token_box(snap,'Main')['page'] == (0 if drop else 1)


def test_part_numbering_restart_continue_and_ending_side(tmp_path, observer):
    footer = MixedStyledText(['PageLabel ',Field(PAGE_NUMBER),' EndLabel'])
    # A two-page front part ends on a left page and a one-page front part on a
    # right page; each ending side then needs a blank page in one of them.
    for ending, front_pages, main_index in (('any',2,2),('left',2,2),('right',2,3),
                                            ('any',1,1),('left',1,2)):
        flowables = [Paragraph('Prelude')]
        if front_pages == 2:
            flowables += [PageBreak(),Paragraph('Frontsecond')]
        snap = flow_snapshot(tmp_path / f'numbers{ending}{front_pages}',[Paragraph('Main')],observer,
            parts=['front','contents','tail'],page=dict(footer_text=footer),
            part_options={
                'front':dict(flowables=flowables,
                             page_number_format='lowercase roman',end_at_page=ending),
                'contents':dict(page_number_format='continue'),
                'tail':dict(flowables=[Paragraph('Tail')],page_number_format='number')})
        main = token_box(snap,'Main')['page']
        assert main == main_index
        roman = ['i','ii','iii','iv']
        expected = {'Prelude':'i','Main':roman[main_index],'Tail':'1'}
        if front_pages == 2:
            expected['Frontsecond'] = 'ii'
        for token,number in expected.items():
            page = snap['pages'][token_box(snap,token)['page']]
            assert pdf_plain_text(dict(pages=[page])).split() == [token,'PageLabel',number,'EndLabel']
