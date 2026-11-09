# feature: F10
"""Acceptance tests for images, figure placement and public drawing entries."""
import sys
import pytest
from talvo.dimension import PT
from talvo.image import Image, InlineImage, BackgroundImage, Figure, FigureStyle, Caption
from talvo.paragraph import Paragraph
from talvo.reference import Reference
from talvo.draw import Line, Polygon, Rectangle, LineStyle, ShapeStyle, Stroke
from talvo.color import Color
from talvo.warnings import TalvoWarning
from F01_helpers import pdf_observer_environment
from F07_helpers import token_box
from F09_helpers import compact_line
from F11_helpers import table_text_direction
from F10_helpers import (image_asset, pdf_artwork, image_snapshot, image_document,
    page_pixels, color_extent, artwork_extent, embedded_profiles, DrawingContent)


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


def test_image_formats_positions_appearance_and_profiles(tmp_path, observer):
    # Each format has a different necessary decoding path; each position has a
    # different public binding. Cover them independently rather than a product.
    for fmt, position in [('png','block'), ('jpg','inline'), ('pdf','background')]:
        asset = tmp_path / ('art.'+fmt)
        profile = None
        if fmt == 'pdf':
            pdf_artwork(asset, observer)
        else:
            profile = image_asset(asset, profile=True, alpha=fmt=='png')
        root = tmp_path / fmt
        elements = [Paragraph('Beforeimage')]
        page = None
        if position == 'block':
            elements += [Image(str(asset),width=80*PT)]
        elif position == 'inline':
            elements = [Paragraph(['Beforeimage ',InlineImage(str(asset),width=80*PT),' Afterimage'])]
        else:
            page = dict(background=BackgroundImage(str(asset),width=80*PT))
        snap = image_snapshot(root,elements,observer,page=page)
        pixels = page_pixels(root,observer)
        red = color_extent(pixels, (255,127,127) if fmt=='png' else (255,0,0))
        blue = color_extent(pixels,(0,0,255))
        assert red[2]-red[0] == pytest.approx(40,abs=2)
        assert blue[2]-blue[0] == pytest.approx(40,abs=2)
        assert blue[0] == pytest.approx(red[2],abs=2)
        assert blue[3]-blue[1] == pytest.approx(40,abs=2)
        before = token_box(snap,'Beforeimage')
        if position=='block':
            assert red[1] > before['y']
        elif position=='inline':
            after = token_box(snap,'Afterimage')
            assert before['x1'] < red[0] < blue[2] < after['x0']
        else:
            assert red[0] == pytest.approx(0,abs=1)
            assert red[1] == pytest.approx(0,abs=1)
        if profile:
            assert profile in embedded_profiles(root.with_suffix('.pdf'),observer)


def test_image_dimensions_scaling_and_resolution(tmp_path, observer):
    plain = tmp_path/'plain.png'
    tagged = tmp_path/'tagged.png'
    image_asset(plain)
    image_asset(tagged,dpi=144)
    cases = [(plain,{},(80,40)),(plain,dict(width=120*PT,height=30*PT),(120,30)),
        (plain,dict(width=100*PT),(100,50)),(plain,dict(height=30*PT),(60,30)),
        (plain,dict(scale=.75),(60,30)),(tagged,{},(40,20)),
        (tagged,dict(dpi=72),(80,40))]
    for i,(asset,options,expected) in enumerate(cases):
        root=tmp_path/f'size{i}'
        image_snapshot(root,[Image(str(asset),**options)],observer)
        x0,y0,x1,y1=artwork_extent(page_pixels(root,observer))
        assert (x1-x0,y1-y0)==pytest.approx(expected,abs=1)


def test_image_rotation_fit_and_fill(tmp_path, observer):
    asset=tmp_path/'art.png'
    image_asset(asset)
    for angle in (90,180):
        root=tmp_path/f'rotate{angle}'
        image_snapshot(root,[Image(str(asset),rotate=angle)],observer)
        pixels=page_pixels(root,observer)
        red=color_extent(pixels,(255,0,0)); blue=color_extent(pixels,(0,0,255))
        bounds=artwork_extent(pixels)
        assert (bounds[2]-bounds[0],bounds[3]-bounds[1])==pytest.approx(
            (40,80) if angle==90 else (80,40),abs=1)
        if angle==90:
            assert blue[3] <= red[1]+1
        else:
            assert blue[2] <= red[0]+1
    # A 240x180 area limits fitting by width and filling by height; a 360x60
    # area reverses both, so neither mode can follow one fixed dimension.
    wide=dict(left_margin=0*PT,right_margin=0*PT,top_margin=30*PT,bottom_margin=150*PT)
    for index,(scale,expected,page) in enumerate([('fit',(240,120),dict(left_margin=0*PT,right_margin=120*PT)),
                                ('fill',(360,180),dict(left_margin=0*PT,right_margin=120*PT)),
                                ('fit',(120,60),wide),('fill',(360,180),wide)]):
        root=tmp_path/f'{scale}{index}'
        image_snapshot(root,[Image(str(asset),scale=scale)],observer,page=page)
        bounds=artwork_extent(page_pixels(root,observer))
        assert (bounds[2]-bounds[0],bounds[3]-bounds[1])==pytest.approx(expected,abs=1)


def test_conflicting_image_sizing_is_refused(tmp_path, observer):
    asset=tmp_path/'art.png'
    image_asset(asset)
    for dimension in ('width','height'):
        for extra in (dict(scale=2),dict(dpi=96)):
            # Capture construction and complete rendering in the same boundary.
            def render_conflict():
                from F08_helpers import render_flow
                image=Image(str(asset),**{dimension:60*PT},**extra)
                return render_flow(tmp_path/'conflict',[image],{'page':{}},{},['contents'],())
            from _helpers import call_public
            result=call_public(render_conflict)
            assert isinstance(result.exception,TypeError),result
    root=tmp_path/'valid'
    image_snapshot(root,[Image(str(asset),width=60*PT,scale=1)],observer)
    box=artwork_extent(page_pixels(root,observer))
    assert (box[2]-box[0],box[3]-box[1])==pytest.approx((60,30),abs=1)


def test_figure_caption_legend_references_and_placement(tmp_path, observer):
    asset=tmp_path/'art.png'
    image_asset(asset)
    for placement in (None,'here','sideways'):
        root=tmp_path/f'figure{placement}'
        figure=Figure([Image(str(asset),width=80*PT),Caption('Harborcaption'),
                       Paragraph('Harborlegend')],id='harbor',style=FigureStyle(float=placement))
        snap=image_snapshot(root,[Paragraph('Precedingbody'),figure,Paragraph('Followingbody'),
            Paragraph(['Crossreference ',Reference('harbor',type='number')])],observer)
        assert compact_line(snap,'Crossreference')=='Crossreference1'
        assert compact_line(snap,'Harborcaption')=='Figure1Harborcaption'
        before=token_box(snap,'Precedingbody'); cap=token_box(snap,'Harborcaption')
        legend=token_box(snap,'Harborlegend'); after=token_box(snap,'Followingbody')
        assert cap['page']==legend['page']
        assert cap['y'] < legend['y']
        pixels=page_pixels(root,observer,cap['page'])
        box=artwork_extent(pixels)
        if placement=='sideways':
            assert cap['page'] != before['page']
            # A sideways page: portrait page box, page rotation or rotated content.
            page=snap['pages'][cap['page']]
            assert (page['rect'][2:] == pytest.approx([240,360]) or page['rotation']%180==90
                    or abs(table_text_direction(snap,'Harborcaption')[1])>.9), page['rect']
        else:
            assert box[3] < cap['y']
            assert legend['y'] < after['y']
            assert (before['y'] < box[1]) if placement is None else (legend['y'] < before['y'])


def test_unavailable_images_report_failure_and_visible_replacement(tmp_path, observer):
    for alt in (None,'Caller supplied alternative'):
        asset=tmp_path/('missing-alt.png' if alt else 'missing.png')
        root=tmp_path/('withalt' if alt else 'withoutalt')
        result=image_document(root,[Paragraph('Livecontent'),Image(str(asset),alt=alt)])
        assert result.exception is None,result.traceback
        assert result.value is False
        assert any(issubclass(category,TalvoWarning) and asset.name in str(message)
                   for category,message,*_ in result.warnings),result.warnings
        from _helpers import observe_pdf
        snap=observe_pdf(root.with_suffix('.pdf'),env=observer)
        text=''.join(p['text'] for p in snap['pages'])
        assert 'Livecontent' in text
        if alt:
            assert alt in text
        else:
            # Identity is carried by the warning; the PDF needs a visible
            # replacement, whose explanatory wording is not prescribed.
            from F07_helpers import line_containing
            live = line_containing(snap, 'Livecontent')
            x0, y0, x1, y1 = live['bbox']
            visible = False
            for page in range(len(snap['pages'])):
                pixels = page_pixels(root, observer, page)
                visible |= any(min(pixels.getpixel((x, y))) < 240
                    for y in range(pixels.height) for x in range(pixels.width)
                    if page != live['page'] or not
                       (x0-1 <= x/2 <= x1+1 and y0-1 <= y/2 <= y1+1))
            assert visible, 'The failed image needs a visible replacement'


def test_lines_polygons_rectangles_geometry_and_styles(tmp_path, observer):
    root=tmp_path/'drawing'
    red=Color(1,0,0); blue=Color(0,0,1)
    shapes=[Line((10,-10),(100,-30),style=LineStyle(stroke=Stroke(3*PT,red))),
        Polygon([(10,-50),(50,-50),(30,-90)],
                style=ShapeStyle(stroke=Stroke(2*PT,blue),fill_color=red)),
        Rectangle((70,-80),40,30,style=ShapeStyle(stroke=None,fill_color=blue)),
        Rectangle((130,-80),40,30,
                  style=ShapeStyle(stroke=Stroke(4*PT,red),fill_color=None))]
    image_snapshot(root,[DrawingContent(shapes)],observer)
    pixels=page_pixels(root,observer)
    # Samples are well inside requested fills and strokes; independent raster
    # observation accepts equivalent vector paths or rasterized geometry.
    def pixel(x,y):
        return pixels.getpixel((int(2*(30+x)),int(2*(30+y))))
    assert pixel(55,20)==pytest.approx((255,0,0),abs=2)
    assert pixel(55,21)==pytest.approx((255,0,0),abs=2)
    assert pixel(55,23)==(255,255,255)
    assert pixel(30,65)==pytest.approx((255,0,0),abs=2)
    assert pixel(20,70)==pytest.approx((0,0,255),abs=2)
    assert pixel(90,65)==pytest.approx((0,0,255),abs=2)
    assert pixel(150,65)==(255,255,255)
    assert pixel(130,65)==pytest.approx((255,0,0),abs=2)
    assert pixel(128.5,65)==pytest.approx((255,0,0),abs=2)
    assert pixel(127,65)==(255,255,255)
    assert pixel(69,65)==(255,255,255)
