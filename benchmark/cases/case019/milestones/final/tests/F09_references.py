# feature: F09
"""Acceptance tests for labels, references, links and dynamic fields."""
import sys

import pytest
from talvo.dimension import PT
from talvo.paragraph import Paragraph, ParagraphStyle
from talvo.structure import Section, Heading
from talvo.flowable import PageBreak
from talvo.text import MixedStyledText, SingleStyledText
from talvo.reference import (Reference, ReferenceStyle, Field, PAGE_NUMBER,
    NUMBER_OF_PAGES, SECTION_NUMBER, SECTION_TITLE, DOCUMENT_TITLE,
    DOCUMENT_SUBTITLE, DOCUMENT_AUTHOR)
from talvo.annotation import HyperLink
from talvo.image import Image
from talvo.warnings import TalvoWarning
from F01_helpers import pdf_observer_environment
from F07_helpers import token_box
from F09_helpers import reference_snapshot, compact_line, covering_links, resolved_internal_links


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


def test_numbering_scope_suppression_and_custom_labels(tmp_path, observer):
    for level, separator, expected in ((0,None,['1','2','3','4']),
            (1,None,['1','2','1','2']), (1,'.',['1.1','1.2','2.1','2.2'])):
        sections = []
        for chapter in range(2):
            rows = [Paragraph(f'Item{chapter}{i}', style=ParagraphStyle(
                number_format='number', numbering_level=level,
                number_separator=SingleStyledText(separator) if separator else None, label_prefix=SingleStyledText('['),label_suffix=SingleStyledText('] ')))
                for i in range(2)]
            sections.append(Section([Heading(f'Heading{chapter}')] + rows))
        snap,_ = reference_snapshot(tmp_path / f'scope{level}{separator}',sections,observer)
        for chapter in range(2):
            assert compact_line(snap,f'Heading{chapter}') == f'[{chapter+1}]Heading{chapter}'
            for i in range(2):
                token=f'Item{chapter}{i}'
                assert compact_line(snap,token) == f'[{expected[chapter*2+i]}]{token}'
    for enabled in (False,True):
        snap,_ = reference_snapshot(tmp_path / f'custom{enabled}',[
            Paragraph('Custombody',custom_label='Special',style=ParagraphStyle(
                number_format='number',custom_label=enabled,label_suffix=SingleStyledText(' '))),
            Paragraph('Hiddenbody',style=ParagraphStyle(number_format=None)),
            Section([Heading('Customheading',custom_label='Named',
                style=Heading.style_class(custom_label=enabled))]),
            Section([Heading('Hiddenheading',style=Heading.style_class(number_format=None))])],observer)
        assert compact_line(snap,'Custombody') == ('Special' if enabled else '1')+'Custombody'
        assert compact_line(snap,'Hiddenbody') == 'Hiddenbody'
        assert compact_line(snap,'Hiddenheading') == 'Hiddenheading'
        assert compact_line(snap,'Customheading') == ('[Named]' if enabled else '[1]')+'Customheading'


def test_bound_number_formats_and_cycles(tmp_path, observer):
    vectors = {
        'number': ['1','2','3','4','5','6','7','8','9','10','11','12','13','14'],
        'lowercase character': list('abcdefghijklmnopqrstuvwxyz')+['aa','ab','ac'],
        'uppercase character': list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')+['AA','AB','AC'],
        'lowercase roman': ['i','ii','iii','iv','v','vi','vii','viii','ix','x','xi','xii','xiii','xiv'],
        'uppercase roman': ['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII','XIII','XIV'],
        'symbol': ['*','†','‡','§','‖','¶','#','**','††','‡‡','§§','‖‖','¶¶','##','***'],
        None: ['','','']}
    for index,(fmt,labels) in enumerate(vectors.items()):
        rows=[Paragraph(f'Formatrow{i:02d}',style=ParagraphStyle(number_format=fmt,
            label_prefix=SingleStyledText('Pre'),label_suffix=SingleStyledText('Post '))) for i in range(len(labels))]
        snap,_=reference_snapshot(tmp_path / f'format{index}',rows,observer)
        for i,label in enumerate(labels):
            token=f'Formatrow{i:02d}'
            assert compact_line(snap,token) == (f'Pre{label}Post' if fmt else '')+token


def test_reference_kinds_forward_backward_and_final_pages(tmp_path, observer):
    placements=[]
    for padding in (0,100):
        refs=[]
        for kind in ('reference','number','title','page','custom'):
            refs.append(Paragraph([f'Forward{kind} ', Reference('target',type=kind,
                custom_title=SingleStyledText('Callerword') if kind=='custom' else None)]))
        # The target is a nested section: whether a top-level section is referenced with the chapter
        # or the section label is not stated, a nested one carries the section label.
        target=Section([Heading('Outerheading'),
                        Section([Heading('Harborheading'),Paragraph('Targetbody')],id='target')])
        back=[Paragraph([f'Backward{kind} ',Reference('target',type=kind,
            custom_title=SingleStyledText('Callerword') if kind=='custom' else None)])
            for kind in ('reference','number','title','page','custom')]
        snap,_=reference_snapshot(tmp_path / f'resolve{padding}',refs+
            ([Paragraph('\n'.join(f'Filler{i}' for i in range(padding)))] if padding else [])+
            [PageBreak(),target,PageBreak()]+back,observer)
        page=token_box(snap,'Targetbody')['page']+1
        placements.append(page)
        expected={'reference':'Section1.1','number':'1.1','title':'Harborheading',
                  'page':str(page),'custom':'Callerword'}
        for direction in ('Forward','Backward'):
            for kind,value in expected.items():
                token=direction+kind
                assert compact_line(snap,token)==token+value
    assert placements[1]>placements[0]


def test_internal_reference_links_default_enabled_and_disabled(tmp_path, observer):
    for mode in (None,True,False):
        ref=Reference('island',type='custom',custom_title=SingleStyledText('Goisland'),style=None if mode is None else ReferenceStyle(link=mode))
        snap,_=reference_snapshot(tmp_path / f'link{mode}',[Paragraph(['Navigate ',ref]),
            PageBreak(),Section([Heading('Islandtitle'),Paragraph('Islandbody')],id='island')],observer)
        assert compact_line(snap,'Navigate')=='NavigateGoisland'
        # Resolve destinations independently of the PDF encoding choice.
        source_page=token_box(snap,'Navigate')['page']
        links=resolved_internal_links((tmp_path / f'link{mode}').with_suffix('.pdf'), observer)[source_page]
        if mode is False:
            assert links==[]
        else:
            assert links
            assert all(l['page']==token_box(snap,'Islandbody')['page'] for l in links), links
            assert covering_links(snap,'Goisland')
            heading=token_box(snap,'Islandtitle')
            assert all(abs(l['to'][1]-heading['y'])<20 for l in links), (links, heading)
            assert all(l['from'][0]>=token_box(snap,'Navigate')['x1']-.5 for l in links)


def test_missing_reference_warning_quiet_and_replacement(tmp_path, observer):
    for target,kind in (('absent','title'),('plain','number')):
        for mode in ('default','quiet','replacement','both'):
            quiet=mode in ('quiet','both')
            replacement=SingleStyledText('Alternative') if mode in ('replacement','both') else None
            ref=Reference(target,type=kind,custom_title=replacement,
                style=ReferenceStyle(quiet=True,link=False) if quiet else ReferenceStyle(link=False))
            snap,result=reference_snapshot(tmp_path / f'missing{target}{mode}',[
                Paragraph('Livebody',id='plain'),Paragraph(['Before ',ref,' After'])],observer)
            assert compact_line(snap,'Livebody')=='Livebody'
            assert compact_line(snap,'Before')=='Before'+('??' if mode=='default' else
                'Alternative' if replacement is not None else '')+'After'
            warnings=[str(w[1]) for w in result.warnings]
            if mode=='default':
                assert any(issubclass(w[0], TalvoWarning) and "'"+target+"'" in str(w[1])
                           and "'"+kind+"'" in str(w[1]) for w in result.warnings), warnings
            else:
                assert not warnings, warnings


def test_external_text_and_image_link_regions(tmp_path, observer):
    from PIL import Image as RasterImage
    asset=tmp_path / 'linked.png'
    RasterImage.new('RGB',(60,20),'blue').save(asset)
    text=SingleStyledText('Visitdestination')
    text.annotation=HyperLink('https://example.org/path?q=blue#section')
    image=Image(str(asset),width=90*PT)
    image.annotation=HyperLink('https://example.net/image')
    snap,_=reference_snapshot(tmp_path / 'external',[Paragraph(text),image],observer)
    links=covering_links(snap,'Visitdestination')
    assert any(l['kind']==2 and l['uri']=='https://example.org/path?q=blue#section' for l in links)
    images=[(p,img) for p in snap['pages'] for img in p['images']]
    assert len(images)==1
    page,img=images[0]
    x0,y0,x1,y1=img['bbox']
    text_box=token_box(snap,'Visitdestination')
    text_middle=(text_box['x0']+text_box['x1'])/2
    # A page-sized action is not the supplied text or image region.
    assert all(not (l['from'][0] <= (x0+x1)/2 <= l['from'][2]
                       and l['from'][1] <= (y0+y1)/2 <= l['from'][3]) for l in links)
    assert any(l['kind']==2 and l['uri']=='https://example.net/image'
        and l['from'][0]<=x0+.5 and l['from'][1]<=y0+.5
        and l['from'][2]>=x1-.5 and l['from'][3]>=y1-.5
        and not (l['from'][0] <= text_middle <= l['from'][2]
                 and l['from'][1] <= text_box['y'] <= l['from'][3]) for l in page['links'])


def test_page_sequence_totals_and_current_section_fields(tmp_path, observer):
    footer=MixedStyledText(['Page ',Field(PAGE_NUMBER),' Total ',Field(NUMBER_OF_PAGES),' End'])
    for tail_length in (1,3):
        snap,_=reference_snapshot(tmp_path / f'fields{tail_length}',[
            Section([Heading('Outer'),Section([Heading('Inner'),Paragraph('Firstbody'),
                PageBreak(),Paragraph('Secondbody')]),
                PageBreak(),Section([Heading('Otherinner'),Paragraph('Thirdbody')])]),
            PageBreak(),Section([Heading('Otherouter'),
                Section([Heading('Lastinner'),Paragraph('Fourthbody')])])],observer,
            parts=['front','contents','tail'],page=dict(footer_text=footer,
                header_text=MixedStyledText(['Section ',Field(SECTION_TITLE(1)),' Number ',
                    Field(SECTION_NUMBER(1)),' Subsection ',Field(SECTION_TITLE(2)),
                    ' Subnumber ',Field(SECTION_NUMBER(2)),' Stop'])),
            options={'front':dict(flowables=[Paragraph('Prelude'),PageBreak(),Paragraph('Presecond')],
                                 page_number_format='number'),
                     'contents':dict(page_number_format='continue'),
                     'tail':dict(flowables=sum(([PageBreak(),Paragraph(f'Tail{i}')] if i else
                         [Paragraph(f'Tail{i}')] for i in range(tail_length)),[]),page_number_format='number')})
        start=token_box(snap,'Firstbody')['page']
        tail=token_box(snap,'Tail0')['page']
        assert tail>start
        assert tail != len(snap['pages'])-tail
        for p,page in enumerate(snap['pages']):
            sub=dict(pages=[page])
            number=p+1 if p<tail else p-tail+1
            total=tail if p<tail else len(snap['pages'])-tail
            assert compact_line(sub,'Page')==f'Page{number}Total{total}End'
        for token,expected in (('Firstbody','SectionOuterNumber1SubsectionInnerSubnumber1.1Stop'),
                               ('Secondbody','SectionOuterNumber1SubsectionInnerSubnumber1.1Stop'),
                               ('Thirdbody','SectionOuterNumber1SubsectionOtherinnerSubnumber1.2Stop'),
                               ('Fourthbody','SectionOtherouterNumber2SubsectionLastinnerSubnumber2.1Stop')):
            page=snap['pages'][token_box(snap,token)['page']]
            assert compact_line(dict(pages=[page]),'Subsection')==expected


def test_metadata_fields_present_and_missing(tmp_path, observer):
    for metadata in ({'title':'Atlas','subtitle':'Riverguide','author':'Marina'},{}):
        rows=[Paragraph([f'Meta{i} ',Field(kind),' End']) for i,kind in enumerate(
            (DOCUMENT_TITLE,DOCUMENT_SUBTITLE,DOCUMENT_AUTHOR))]
        snap,_=reference_snapshot(tmp_path / ('present' if metadata else 'missing'),rows,
            observer,metadata=metadata)
        for i,key in enumerate(('title','subtitle','author')):
            assert compact_line(snap,f'Meta{i}')==f'Meta{i}'+metadata.get(key,'')+'End'
