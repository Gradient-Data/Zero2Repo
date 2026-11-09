# feature: F15
"""Acceptance checks for rendered mathematical notation and equation references."""
import sys

import pytest
from talvo.math import Equation, DisplayEquation
from talvo.paragraph import Paragraph
from talvo.color import Color
from talvo.reference import Reference
from F01_helpers import pdf_observer_environment
from F07_helpers import token_box
from F09_helpers import compact_line, resolved_internal_links
from F10_helpers import page_pixels, color_extent
from F15_helpers import math_snapshot, math_ink, ink_union, equation_label_box


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path/'observer')


def test_mathematical_arrangement_and_inline_baseline(tmp_path, observer):
    root = tmp_path/'fraction'
    math_snapshot(root,[Paragraph([Equation(r'\frac{x}{y}')])],observer)
    boxes = math_ink(root,observer)
    # The fraction bar separates vertically stacked, horizontally overlapping ink.
    bar = max(boxes,key=lambda b:(b[2]-b[0])/max(.5,b[3]-b[1]))
    above = [b for b in boxes if b[3] < bar[1]]
    below = [b for b in boxes if b[1] > bar[3]]
    assert above and below
    for b in above+below:
        assert b[0] < bar[2] and b[2] > bar[0]

    root = tmp_path/'root'
    math_snapshot(root,[Paragraph([Equation(r'\sqrt{x}')])],observer)
    boxes = math_ink(root,observer)
    radical = max(boxes,key=lambda b:b[2]-b[0])
    enclosed = [b for b in boxes if b != radical and radical[0] < b[0]
                and radical[1] < b[1] and radical[2] >= b[2]
                and radical[3] > b[3]]
    assert enclosed, boxes

    root = tmp_path/'scripts'
    math_snapshot(root,[Paragraph([Equation(r'x_a^b')])],observer)
    boxes = math_ink(root,observer)
    base = min(boxes,key=lambda b:b[0])
    upper = [b for b in boxes if b[0] >= base[2] and b[1] < base[1]]
    lower = [b for b in boxes if b[0] >= base[2] and b[3] > base[3]]
    assert upper and lower, boxes

    root = tmp_path/'sum'
    snap = math_snapshot(root,[DisplayEquation(r'\sum_a^b x')],observer)
    label = equation_label_box(snap,1)
    boxes = math_ink(root,observer,exclude=[label['bbox']])
    operator = max(boxes,key=lambda b:b[3]-b[1])
    assert any(b[3] < operator[1] and b[0] < operator[2] and b[2] > operator[0]
               for b in boxes), boxes
    assert any(b[1] > operator[3] and b[0] < operator[2] and b[2] > operator[0]
               for b in boxes), boxes
    assert any(b[0] > operator[2] for b in boxes), boxes

    # Greek letters must produce artwork, not their multi-letter source commands.
    # This checks distinct visible glyphs, not a particular math font's outlines.
    glyph_masks = []
    for name in ('alpha','beta'):
        root = tmp_path/name
        snap = math_snapshot(root,[Paragraph([Equation('\\'+name)])],observer)
        boxes = math_ink(root,observer)
        bounds = ink_union(boxes)
        assert name not in ''.join(page['text'] for page in snap['pages']), snap
        image = page_pixels(root, observer).convert('L')
        crop = image.crop(tuple(round(2*v) for v in bounds))
        glyph_masks.append(crop.resize((64, 64)).point(lambda v: 255 if v < 180 else 0).tobytes())
    assert glyph_masks[0] != glyph_masks[1], 'Distinct Greek letters must retain distinct visible glyphs'

    root = tmp_path/'inline'
    snap = math_snapshot(root,[Paragraph(['Before ',Equation('x'),' After'])],
                         observer,size=10)
    before,after = token_box(snap,'Before'),token_box(snap,'After')
    assert before['y'] == pytest.approx(after['y'],abs=.1)
    bounds = ink_union(math_ink(root,observer,
        (before['x1']+1,0,after['x0']-1,400)))
    assert before['x1'] < bounds[0] < bounds[2] < after['x0']
    assert bounds[3] == pytest.approx(before['y'],abs=1)


def test_equation_style_labels_and_reference_destinations(tmp_path, observer):
    dimensions = []
    for size,color,rgb,name in ((20,Color(1,0,0),(255,0,0),'red'),
                                (40,Color(1,0,0),(255,0,0),'large'),
                                (20,Color(0,0,1),(0,0,255),'blue')):
        root = tmp_path/name
        snap = math_snapshot(root,[
            Paragraph(['Firstreference ',Reference('first',type='number')]),
            DisplayEquation('x',id='first'),
            DisplayEquation('y',id='second'),
            Paragraph(['Secondreference ',Reference('second',type='number')])],
            observer,size=size,color=color)
        assert compact_line(snap,'Firstreference') == 'Firstreference1'
        assert compact_line(snap,'Secondreference') == 'Secondreference2'
        labels = [equation_label_box(snap,n) for n in (1,2)]
        assert labels[0]['y'] < labels[1]['y']
        extent = color_extent(page_pixels(root,observer),rgb)
        dimensions.append((extent[2]-extent[0],extent[3]-extent[1]))
        links = resolved_internal_links(root.with_suffix('.pdf'),observer)
        targets = []
        for token,label in zip(('Firstreference','Secondreference'),labels):
            ref = token_box(snap,token)
            matching = [link for link in links[ref['page']]
                        if link['from'][0] >= ref['x1']-.5
                        and link['from'][1] <= ref['y'] <= link['from'][3]]
            assert len(matching) == 1, matching
            link = matching[0]
            assert link['page'] == label['page']
            assert label['y']-20 <= link['to'][1] <= label['y']
            targets.append(link['to'][1])
        assert targets[0] < targets[1]
    # The same glyph's ink scales with the selected size, independently of font.
    assert dimensions[1][0] == pytest.approx(2*dimensions[0][0],abs=1.5)
    assert dimensions[2][0] == pytest.approx(dimensions[0][0],abs=1)
    # Vertical extent spans two equations; avoid confusing line spacing with size.


def test_base_installation_math_warning_and_omission(tmp_path, observer, record_property):
    from F15_helpers import base_installation_math_render
    from _helpers import observe_pdf
    # A live full-support baseline prevents a renderer that always omits math
    # from satisfying the no-extra installation arm.
    baseline = tmp_path/'supported'
    math_snapshot(baseline,[Paragraph('Surroundingbefore'),
        Paragraph([Equation(r'\frac{x}{y}')]),
        Paragraph('Surroundingafter')],observer)
    baseline_snap = observe_pdf(baseline.with_suffix('.pdf'),env=observer)
    first = token_box(baseline_snap,'Surroundingbefore')
    last = token_box(baseline_snap,'Surroundingafter')
    baseline_boxes = math_ink(baseline,observer,(0,first['y']+6,600,last['y']-10))
    assert len(baseline_boxes) >= 3, baseline_boxes
    root = tmp_path/'base'
    report = base_installation_math_render(tmp_path/'base-venv',root)
    assert report['result'] is True, report
    snap = observe_pdf(root.with_suffix('.pdf'),env=observer)
    before = token_box(snap,'Surroundingbefore')
    after = token_box(snap,'Surroundingafter')
    assert before['page'] == after['page'] == 0
    assert before['y'] < after['y']
    boxes = math_ink(root,observer,(0,before['y']+6,600,after['y']-10))
    if boxes:
        # Self-contained renderers need not lose support without the math extra.
        bar = max(boxes,key=lambda b:(b[2]-b[0])/max(.5,b[3]-b[1]))
        assert any(b[3] < bar[1] for b in boxes), boxes
        assert any(b[1] > bar[3] for b in boxes), boxes
        record_property('missing_math_branch','unobserved: base installation renders mathematics')
    else:
        # Read the short public warning label, not its explanatory wording.
        assert any(w['talvo'] and w['message'].startswith('Math rendering')
                   for w in report['warnings']), report
        record_property('missing_math_branch','observed: warning and omitted artwork')
