# feature: F11
"""Acceptance tests for table structure, geometry and continuation."""
import sys
import pytest
from talvo.dimension import PT
from talvo.table import (Table, TableStyle, TableBody, TableHead, TableRow,
    TableCell, TableCellStyle, TableWithCaption, TableWithCaptionStyle)
from talvo.paragraph import Paragraph, ParagraphStyle
from talvo.image import Caption
from talvo.reference import Reference
from talvo.warnings import TalvoWarning
from F01_helpers import pdf_observer_environment
from F07_helpers import token_box, visible_lines
from F09_helpers import compact_line, resolved_internal_links
from F11_helpers import (table_cell, table_row, table_snapshot, table_call,
    one_cell_area, cell_areas, CELL_COLORS, render_sourced_table, table_text_direction)
from _helpers import call_public, observe_pdf


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


def test_cell_grid_spans_blocks_and_header_only(tmp_path, observer):
    for headed in (False, True):
        table = Table(TableBody([
            TableRow([table_cell('Spanwide', colspan=2, color=0), table_cell('Righttop')]),
            TableRow([table_cell([Paragraph('Blockfirst'), Paragraph('Blocksecond')],
                                rowspan=2, color=1), table_cell('Middle'), table_cell('', color=2)]),
            TableRow([table_cell('Lower'), table_cell('Last')])]),
            head=TableHead([table_row('Headone','Headtwo','Headthree')]) if headed else None,
            column_widths=[90*PT,90*PT,90*PT])
        snap,_=table_snapshot(tmp_path/f'grid{headed}', [table], observer)
        for token in ('Spanwide','Righttop','Blockfirst','Blocksecond','Middle','Lower','Last'):
            token_box(snap,token)
        wide, tall, empty = [one_cell_area(snap,i) for i in range(3)]
        assert wide[2]-wide[0] == pytest.approx(2*(empty[2]-empty[0]),abs=.1)
        assert tall[2]-tall[0] == pytest.approx(empty[2]-empty[0],abs=.1)
        assert tall[1] <= token_box(snap,'Middle')['y'] < token_box(snap,'Lower')['y'] <= tall[3]
        assert token_box(snap,'Blockfirst')['y'] < token_box(snap,'Blocksecond')['y']
        assert empty[0] > token_box(snap,'Middle')['x1']
        assert empty[1] < token_box(snap,'Middle')['y'] < empty[3]
        if headed:
            for token in ('Headone','Headtwo','Headthree'):
                assert token_box(snap,token)['y'] < token_box(snap,'Spanwide')['y']
    snap,_=table_snapshot(tmp_path/'headonly', [Table(None,
        head=TableHead([table_row('Onlyhead','Secondhead')]))], observer)
    assert token_box(snap,'Onlyhead')['x1'] < token_box(snap,'Secondhead')['x0']


def test_fixed_proportional_auto_and_mixed_column_widths(tmp_path, observer):
    cases = [([60*PT,110*PT,90*PT],None), ([1,2,3],270*PT),
             ([50*PT,1,2],270*PT), ([None,None,None],270*PT),
             ([None,50*PT,30,60],280*PT)]
    for index,(widths,width) in enumerate(cases):
        texts=['Alpha','Longer','Gamma','Delta'][:len(widths)]
        snap,_=table_snapshot(tmp_path/f'width{index}',[Table(TableBody([
            TableRow([table_cell(t,color=i) for i,t in enumerate(texts)])]),
            column_widths=widths,width=width)],observer)
        areas=[one_cell_area(snap,i) for i in range(len(widths))]
        sizes=[a[2]-a[0] for a in areas]
        for i,(requested,area,text) in enumerate(zip(widths,areas,texts)):
            if not isinstance(requested,(int,type(None))):
                assert sizes[i] == pytest.approx(float(requested),abs=.1)
            box=token_box(snap,text)
            assert area[0] <= box['x0'] < box['x1'] <= area[2]+.1, (index, sizes, areas, text, box)
        proportional=[i for i,w in enumerate(widths) if isinstance(w,int)]
        if proportional:
            a=proportional[0]
            for b in proportional[1:]:
                assert sizes[a]/sizes[b] == pytest.approx(widths[a]/widths[b],abs=.002)
        if width:
            assert sum(sizes) <= float(width)+.1


def test_explicit_width_cardinality_is_refused(tmp_path, observer):
    snap,_=table_snapshot(tmp_path/'matched',[Table(TableBody([table_row('Validleft','Validright')]),
        column_widths=[80*PT,90*PT])],observer)
    token_box(snap,'Validright')
    for widths in ([80*PT], [80*PT,90*PT,70*PT]):
        result=table_call(tmp_path/f'mismatch{len(widths)}',[Table(
            TableBody([table_row('Validleft','Validright')]),column_widths=widths)])
        assert isinstance(result.exception,ValueError), (result.traceback,result)


def test_cell_decoration_alignment_padding_and_wrapping(tmp_path, observer):
    from talvo.color import Color
    from talvo.draw import Stroke
    for padding in (2,11):
        cells=[TableCell([Paragraph('Tallone\nTalltwo\nTallthree\nTallfour')])]
        cells += [TableCell([Paragraph(token)],style=TableCellStyle(
            vertical_align=align,padding=padding*PT,background_color=Color(*CELL_COLORS[i])))
            for i,(align,token) in enumerate(zip(('top','middle','bottom'),('Upper','Center','Bottom')))]
        root=tmp_path/f'decoration{padding}'
        snap,_=table_snapshot(root,[Table(TableBody([TableRow(cells)]),column_widths=[75*PT]*4,
            style=TableStyle(border=Stroke(2*PT,Color(1,0,1)),background_color=Color(0,1,1)))],observer)
        ys=[token_box(snap,t)['y'] for t in ('Upper','Center','Bottom')]
        assert ys[0] < ys[1] < ys[2]
        # Same single-line content and padding in all three cells: middle
        # alignment centres it, so its baseline lies halfway between the
        # top- and bottom-aligned baselines.
        assert ys[1] == pytest.approx((ys[0]+ys[2])/2, abs=.5)
        for i,token in enumerate(('Upper','Center','Bottom')):
            area=one_cell_area(snap,i)
            assert token_box(snap,token)['x0']-area[0] == pytest.approx(padding,abs=.8)
        drawings=snap['pages'][0]['drawings']
        assert any(d['color'] is not None and d['width']==pytest.approx(2,abs=.01)
                   and d['color']==pytest.approx([1,0,1],abs=.001) for d in drawings)
        assert any(d['color'] is not None and d['width']==pytest.approx(.5,abs=.01) for d in drawings)
        cell_areas(snap,(0,1,1))
    phrase=' '.join('Wrapword' for _ in range(14))
    heights=[]
    for width in (75,220):
        snap,_=table_snapshot(tmp_path/f'wrap{width}',[Table(TableBody([TableRow([
            table_cell(phrase,color=0)])]),column_widths=[width*PT])],observer)
        area=one_cell_area(snap,0)
        lines=[line for line in visible_lines(snap) if 'Wrapword' in line['text']]
        assert sum(line['text'].count('Wrapword') for line in lines)==14
        assert all(area[0] <= line['bbox'][0] and line['bbox'][2] <= area[2]+.1
                   and area[1] <= line['spans'][0]['origin'][1] <= area[3] for line in lines)
        heights.append(area[3]-area[1])
    assert heights[0] > heights[1]


def test_long_table_continuation_spans_and_repeated_headers(tmp_path, observer):
    for repeat in (None,True):
        rows=[]
        for i in range(32):
            cells=[] if i%2 else [table_cell(f'Span{i:02d}',rowspan=2)]
            rows.append(TableRow(cells+[table_cell(f'Row{i:02d}')]))
        options={} if repeat is None else dict(repeat_head=repeat)
        snap,_=table_snapshot(tmp_path/f'long{repeat}',[Table(TableBody(rows),
            head=TableHead([table_row('Spanhead','Rowhead')]),column_widths=[100*PT,100*PT],
            style=TableStyle(**options))],observer)
        positions=[token_box(snap,f'Row{i:02d}') for i in range(32)]
        pages=sorted({p['page'] for p in positions})
        assert len(pages)>1
        assert [(p['page'],p['y']) for p in positions] == sorted((p['page'],p['y']) for p in positions)
        for i in range(0,32,2):
            span=token_box(snap,f'Span{i:02d}')
            assert span['page']==positions[i]['page']==positions[i+1]['page']
        for page in pages:
            text=snap['pages'][page]['text']
            for header in ('Spanhead','Rowhead'):
                assert text.count(header)==(1 if repeat or page==pages[0] else 0)


def test_initial_split_minimum_rows(tmp_path, observer):
    fresh,_=table_snapshot(tmp_path/'fresh', [Table(TableBody([table_row(f'Body{i}') for i in range(6)]),
        column_widths=[100*PT])], observer)
    assert {token_box(fresh,f'Body{i}')['page'] for i in range(6)} == {0}
    for filler in (8,11):
        # None leaves the style unset, exercising the default (no minimum).
        for minimum in (None,0,3):
            style=None if minimum is None else TableStyle(split_minimum_rows=minimum)
            snap,_=table_snapshot(tmp_path/f'min{filler}_{minimum}',[
                Paragraph('\n'.join(f'Prelude{i}' for i in range(filler))),
                Table(TableBody([table_row(f'Body{i}') for i in range(6)]),
                    column_widths=[100*PT],style=style)],observer)
            positions=[token_box(snap,f'Body{i}') for i in range(6)]
            counts={p:sum(box['page']==p for box in positions) for p in {box['page'] for box in positions}}
            assert len(counts)<=2
            if minimum and len(counts)>1:
                assert min(counts.values())>=minimum
            if not minimum and filler==11:
                # Without a minimum the table that overflows the page continues
                # across pages, starting in the space left on the current page.
                assert len(counts)==2
                assert positions[0]['page']==token_box(snap,f'Prelude{filler-1}')['page']
            assert [(p['page'],p['y']) for p in positions] == sorted((p['page'],p['y']) for p in positions)


def test_caption_references_and_sideways_table(tmp_path, observer):
    for sideways in (False,True):
        root=tmp_path/f'caption{sideways}'
        snap,_=table_snapshot(root,[Paragraph(['Lookupone ',Reference('cargo',type='number')]),
            Paragraph(['Lookuptwo ',Reference('parcel',type='number')]),
            TableWithCaption([Caption(' Parcel caption'), Table(TableBody([table_row('Parcelcell')]))],id='parcel'),
            TableWithCaption([Caption(' Cargo caption'),Table(TableBody([
                table_row('Cellnorth','Celleast'),table_row('Cellsouth','Cellwest')]),
                column_widths=[100*PT,100*PT])],id='cargo',
                style=TableWithCaptionStyle(float='sideways' if sideways else None))],observer)
        caption=token_box(snap,'Cargo caption')
        for token in ('Cellnorth','Celleast','Cellsouth','Cellwest'):
            assert token_box(snap,token)['page']==caption['page']
        cargo_number=compact_line(snap,'Lookupone').removeprefix('Lookupone')
        parcel_number=compact_line(snap,'Lookuptwo').removeprefix('Lookuptwo')
        assert cargo_number.isdecimal() and parcel_number.isdecimal()
        assert cargo_number != parcel_number
        assert compact_line(snap,'Cargo caption')=='Table'+cargo_number+'Cargocaption'
        assert compact_line(snap,'Parcel caption')=='Table'+parcel_number+'Parcelcaption'
        links=resolved_internal_links(root.with_suffix('.pdf'),observer)
        assert any(link.get('page')==caption['page'] for page in links for link in page)
        page=snap['pages'][caption['page']]
        if sideways:
            rotated_content=all(abs(table_text_direction(snap,token)[1])>.9
                for token in ('Cargo caption','Cellnorth','Celleast','Cellsouth','Cellwest'))
            assert page['rect'][2]<page['rect'][3] or page['rotation']%180==90 or rotated_content
        else:
            assert page['rect'][2]>page['rect'][3]


def test_excessive_fixed_and_content_widths_warn(tmp_path, observer):
    for kind,widths,text in [('fits',[100*PT,100*PT],'Fits'),
                             ('fixed',[190*PT,190*PT],'Fixed'),
                             ('content',[None,None],'W'*90)]:
        source=tmp_path/(kind+'.rst')
        border='+'+'-'*(len(text)+2)+'+------+\n'
        source.write_text(border+'| '+text+' | Peer |\n'+border, encoding='utf-8')
        result=call_public(render_sourced_table,tmp_path/kind,source,widths)
        assert result.exception is None, result.traceback
        assert result.value is True, result
        snap=observe_pdf((tmp_path/kind).with_suffix('.pdf'),env=observer)
        token_box(snap,'Peer')
        warnings=[str(message) for category,message,_,_ in result.warnings
                  if issubclass(category,TalvoWarning)]
        if kind=='fits':
            assert warnings==[]
        else:
            assert warnings, result
            # Read the fixed source-location envelope, never the free explanation.
            import re
            locations=[re.match(r'^\[(.+):([^ ]+) <([^>]+)>\] ', message) for message in warnings]
            assert any(match and match[1]==str(source) and match[3]=='table'
                       for match in locations), warnings
