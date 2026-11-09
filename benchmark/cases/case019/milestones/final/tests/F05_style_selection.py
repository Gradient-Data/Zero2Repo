# feature: F05
"""Acceptance coverage of style binding through rendered documents."""
import sys

# Bind public imports to the product mounted by the acceptance runner.

import pytest

from talvo.attribute import Var
from talvo.color import HexColor
from talvo.dimension import PT
from talvo.flowable import GroupedFlowables, StaticGroupedFlowables
from talvo.paragraph import Paragraph, ParagraphBase, ParagraphStyle
from talvo.style import NEXT_STYLE, PARENT_STYLE, StyleSheet, StyleSheetFile
from talvo.text import SingleStyledText, StyledText

from F01_helpers import pdf_observer_environment
from F02_helpers import pdf_plain_text
from F05_helpers import (caller_sheet, style_snapshot, token_spans,
                         assert_token_style, style_report_records)


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


def test_select_by_type_label_attribute_and_context(tmp_path, observer):
    outer = GroupedFlowables.like('outer')
    sheet = caller_sheet([
        ('all paragraphs', Paragraph, dict(font_size=11*PT)),
        ('label match', Paragraph.like('marked'), dict(font_size=13*PT)),
        ('attribute match', Paragraph.like(id='target'), dict(font_size=15*PT)),
        ('direct child', outer / Paragraph, dict(font_size=17*PT)),
        ('descendant', outer / ... / Paragraph.like('deep'), dict(font_size=19*PT)),
        ('inline only', StyledText.like('accent'), dict(font_size=21*PT)),
    ])
    elements = [Paragraph('Plain'), Paragraph('Marked', style='marked'),
                Paragraph('Target', id='target'), Paragraph('Other', id='other'),
                StaticGroupedFlowables([Paragraph('Direct'),
                    StaticGroupedFlowables([Paragraph('Deep', style='deep'),
                                            Paragraph('Nested')])], style='outer'),
                # Same label, no outer ancestor: the descendant rule must not apply.
                StaticGroupedFlowables([StaticGroupedFlowables(
                    [Paragraph('Stray', style='deep')])]),
                Paragraph([SingleStyledText('Surround '),
                           SingleStyledText('Accent', style='accent')])]
    snap = style_snapshot(tmp_path / 'selectors', elements, sheet, observer)
    for token, size in [('Plain',11), ('Marked',13), ('Target',15), ('Other',11),
                        ('Direct',17), ('Deep',19), ('Nested',11), ('Stray',11),
                        ('Surround',11), ('Accent',21)]:
        assert_token_style(snap, token, size=size)


def test_priority_precedes_specificity(tmp_path, observer):
    for index, reverse in enumerate((False, True)):
        rules = [
            ('ordinary', Paragraph.like('marked', id='target'), dict(font_size=19*PT)),
            ('positive', +Paragraph, dict(font_size=14*PT)),
            ('negative', -Paragraph.like('marked', id='target'), dict(font_size=23*PT)),
        ]
        sheet = caller_sheet(list(reversed(rules)) if reverse else rules)
        snap = style_snapshot(tmp_path / f'priority{index}',
                              [Paragraph('Priority', style='marked', id='target')], sheet, observer)
        assert_token_style(snap, 'Priority', size=14)
        # An ordinary selector must also beat a negative-priority, more specific one.
        sheet = caller_sheet([rules[0], rules[2]])
        snap = style_snapshot(tmp_path / f'zero{index}',
                              [Paragraph('Ordinary', style='marked', id='target')], sheet, observer)
        assert_token_style(snap, 'Ordinary', size=19)


def test_equal_priority_specificity(tmp_path, observer):
    # Each pair isolates one documented comparison; reverse declaration order
    # keeps a last-definition-wins implementation from passing.
    pairs = [
        (GroupedFlowables.like('outer') / Paragraph.like('marked'),
         Paragraph.like('marked', id='target')),
        (Paragraph.like('marked'), Paragraph.like(id='target')),
        (Paragraph.like(id='target'), GroupedFlowables / Paragraph),
        (Paragraph.like(id='target', has_class='flag'), Paragraph.like(id='target')),
        (Paragraph, ParagraphBase),
        (GroupedFlowables / Paragraph, Paragraph),
    ]
    for index, (winner, loser) in enumerate(pairs):
        for reverse in (False, True):
            rules = [('winner', winner, dict(font_size=16*PT)),
                     ('loser', loser, dict(font_size=22*PT))]
            sheet = caller_sheet(rules[::-1] if reverse else rules)
            paragraph = Paragraph('Specific', style='marked', id='target')
            paragraph.classes.append('flag')
            snap = style_snapshot(tmp_path / f'specific{index}{reverse}',
                [StaticGroupedFlowables([paragraph], style='outer')], sheet, observer)
            assert_token_style(snap, 'Specific', size=16)


def test_derived_definition_and_default_reset(tmp_path, observer):
    default_snap = style_snapshot(tmp_path / 'default', [Paragraph('Default', style='marked')],
                                  StyleSheet('Defaults'), observer)
    default = token_spans(default_snap, 'Default')
    inherited_size = default['size'] + 7
    inherited_color = default['color'] ^ 0xffffff
    base = caller_sheet([('marked', Paragraph.like('marked'),
                          dict(font_size=inherited_size*PT,
                               font_color=HexColor(f'{inherited_color:06x}')))])
    derived = StyleSheet('Derived', base=base)
    derived('marked', font_color=HexColor('2040c0'))
    snap = style_snapshot(tmp_path / 'derived', [Paragraph('Derived', style='marked')], derived, observer)
    assert_token_style(snap, 'Derived', size=inherited_size, color=0x2040c0)
    reset = StyleSheet('Reset', base=base)
    reset('marked', base='default')
    reset_snap = style_snapshot(tmp_path / 'reset', [Paragraph('Reset', style='marked')], reset, observer)
    a, b = token_spans(reset_snap, 'Reset'), token_spans(default_snap, 'Default')
    assert (a['size'], a['color'], a['font']) == (b['size'], b['color'], b['font'])
    assert a['size'] != inherited_size and a['color'] != inherited_color


def test_named_inline_and_explicit_parent_inheritance(tmp_path, observer):
    sheet = caller_sheet([
        ('outer', GroupedFlowables.like('outer'), dict(padding_left=27*PT)),
        ('paragraph', Paragraph.like('styled'), dict(font_size=17*PT, font_color=HexColor('2050a0'))),
        ('inline', StyledText.like('accent'), dict(font_color=HexColor('a03020'))),
        ('named', Paragraph.like('named'), dict(base='paragraph', font_color=HexColor('208040'))),
        ('parent group', GroupedFlowables.like('inherit'), dict(base=PARENT_STYLE)),
    ])
    snap = style_snapshot(tmp_path / 'inherit', [
        Paragraph([SingleStyledText('Parent '), SingleStyledText('Inline', style='accent')], style='styled'),
        Paragraph('Named', style='named'),
        StaticGroupedFlowables([Paragraph('Isolated'),
            StaticGroupedFlowables([Paragraph('Inherited')], style='inherit')], style='outer'),
        Paragraph('Default')], sheet, observer)
    assert_token_style(snap, 'Parent', size=17, color=0x2050a0)
    assert_token_style(snap, 'Inline', size=17, color=0xa03020)
    assert_token_style(snap, 'Named', size=17, color=0x208040)
    isolated = token_spans(snap, 'Isolated')
    default = token_spans(snap, 'Default')
    assert isolated['size'] == default['size']
    # Compatible nested groups explicitly inherit padding; paragraphs stay isolated.
    assert isolated['origin'][0] - default['origin'][0] == pytest.approx(27, abs=.02)
    assert token_spans(snap, 'Inherited')['origin'][0] - isolated['origin'][0] == pytest.approx(27, abs=.02)


def test_explicit_next_style_fills_only_unspecified_properties(tmp_path, observer):
    sheet = caller_sheet([
        ('general', Paragraph, dict(font_size=19*PT, font_color=HexColor('2050a0'))),
        ('specific', Paragraph.like('special'), dict(base=NEXT_STYLE, font_color=HexColor('a03020'))),
    ])
    snap = style_snapshot(tmp_path / 'next', [Paragraph('General'), Paragraph('Specific', style='special')], sheet, observer)
    assert_token_style(snap, 'General', size=19, color=0x2050a0)
    assert_token_style(snap, 'Specific', size=19, color=0xa03020)


def test_derived_variables_change_all_references_not_literals(tmp_path, observer):
    base = caller_sheet([
        ('first', Paragraph.like('first'), dict(font_size=Var('size'))),
        ('second', Paragraph.like('second'), dict(font_size=Var('size'))),
        ('literal', Paragraph.like('literal'), dict(font_size=13*PT)),
    ])
    base.variables['size'] = 13*PT
    derived = StyleSheet('Variable override', base=base)
    derived.variables['size'] = 21*PT
    for index, (sheet, expected) in enumerate(((base,13),(derived,21))):
        snap = style_snapshot(tmp_path / f'variables{index}',
            [Paragraph('First', style='first'), Paragraph('Second', style='second'),
             Paragraph('Literal', style='literal')], sheet, observer)
        assert_token_style(snap, 'First', size=expected)
        assert_token_style(snap, 'Second', size=expected)
        assert_token_style(snap, 'Literal', size=13)


def test_file_relative_base_and_four_included_font_roles(tmp_path, observer):
    folder = tmp_path / 'sheets'
    folder.mkdir()
    (folder / 'base.rts').write_text('[STYLESHEET]\nname=File base\n\n[body]\nfont_size=18pt\nfont_color=#204080\n', encoding='utf-8')
    (folder / 'child.rts').write_text('[STYLESHEET]\nname=File child\nbase=base.rts\n\n[body]\nfont_color=#802040\n', encoding='utf-8')
    sheet = StyleSheetFile(str(folder / 'child.rts'))
    snap = style_snapshot(tmp_path / 'file', [Paragraph('Filebased')], sheet, observer)
    assert_token_style(snap, 'Filebased', size=18, color=0x802040)
    for name, families in [('sphinx', ('Pagella','Heros','Cursor')),
                            ('sphinx_article', ('Pagella','Heros','Cursor')),
                            ('sphinx_base14', ('Times','Helvetica','Courier')),
                            ('sphinx_article_base14', ('Times','Helvetica','Courier'))]:
        sheet = StyleSheet('Roles', base=name)
        snap = style_snapshot(tmp_path / name, [
            Paragraph(token, style=ParagraphStyle(typeface=Var(role)))
            for token, role in [('Serif','serif_typeface'), ('Sans','sans_typeface'), ('Mono','mono_typeface')]], sheet, observer)
        for token, family in zip(('Serif','Sans','Mono'), families):
            assert family.lower() in token_spans(snap, token)['font'].lower()


def test_visual_properties_padding_borders_and_visibility(tmp_path, observer):
    from talvo.draw import Stroke
    from talvo.structure import List, ListItem, ListItemLabel
    sheet = caller_sheet([
        ('frame', Paragraph.like('frame'), dict(font_size=16*PT, font_color=HexColor('204080'),
            margin_left=12*PT, margin_right=18*PT, padding=8*PT,
            padding_left=15*PT, padding_right=0, padding_top=11*PT, padding_bottom=13*PT,
            border=Stroke(2*PT, HexColor('c02040')),
            border_left=Stroke(5*PT, HexColor('208040')), background_color=HexColor('e0d080'))),
        ('hidden', Paragraph.like('hidden'), dict(hide=True)),
        ('label', (List.like('hiddenlabel') / ListItem / ListItemLabel), dict(hide=True)),
        ('caller bullet', List.like('hiddenlabel'), dict(bullet=SingleStyledText('Marker'))),
    ], base='sphinx_article')
    elements = [Paragraph('Framed', style='frame'), Paragraph('Visible'),
                Paragraph('Concealed', style='hidden'),
                List([ListItem(StaticGroupedFlowables([Paragraph('Listbody')]))], style='hiddenlabel')]
    snap = style_snapshot(tmp_path / 'visual', elements, sheet, observer)
    frame = assert_token_style(snap, 'Framed', size=16, color=0x204080)
    normal = token_spans(snap, 'Visible')
    assert frame['origin'][0] - normal['origin'][0] == pytest.approx(32, abs=.02)
    text = pdf_plain_text(snap)
    assert 'Visible' in text and 'Listbody' in text
    assert 'Concealed' not in text
    drawings = [d for page in snap['pages'] for d in page['drawings']]
    fill = [d for d in drawings if d['fill'] is not None and tuple(d['fill']) == pytest.approx((224/255,208/255,128/255), abs=.001)]
    assert len(fill) == 1, drawings
    rect = fill[0]['rect']
    assert rect[0] == pytest.approx(normal['origin'][0]+12, abs=.02)
    assert frame['origin'][0]-rect[0] == pytest.approx(20, abs=.02)
    assert rect[2]-rect[0] == pytest.approx(snap['pages'][0]['rect'][2]-80-12-18, abs=.02)
    for width, color in [(2,(192/255,32/255,64/255)), (5,(32/255,128/255,64/255))]:
        assert any(d['width'] == pytest.approx(width, abs=.01) and d['color'] is not None
                   and tuple(d['color']) == pytest.approx(color, abs=.001) for d in drawings), drawings
    # Compare identical text and frames so font-dependent ascent cancels.
    padding_observations = []
    for index, sides in enumerate(({}, dict(padding_top=11*PT, padding_bottom=13*PT))):
        padding_sheet = caller_sheet([('padding', Paragraph, dict(
            font_size=16*PT, padding=8*PT, background_color=HexColor('e0d080'), **sides))])
        padding_snap = style_snapshot(tmp_path / f'padding{index}', [Paragraph('Padding')], padding_sheet, observer)
        padding_span = token_spans(padding_snap, 'Padding')
        boxes = [d['rect'] for page in padding_snap['pages'] for d in page['drawings'] if d['fill'] is not None]
        assert len(boxes) == 1, boxes
        padding_observations.append((padding_span['origin'][1]-boxes[0][1], boxes[0][3]-boxes[0][1]))
    assert padding_observations[1][0]-padding_observations[0][0] == pytest.approx(3, abs=.02)
    assert padding_observations[1][1]-padding_observations[0][1] == pytest.approx(8, abs=.02)
    right_origins = []
    for index, right in enumerate((0, 8, 14)):
        right_sheet = caller_sheet([('right padding', Paragraph, dict(
            padding=8*PT, padding_right=right if right == 0 else right*PT, text_align='right'))])
        right_snap = style_snapshot(tmp_path / f'right{index}', [Paragraph('Rightpad')], right_sheet, observer)
        right_origins.append(token_spans(right_snap, 'Rightpad')['origin'][0])
    assert right_origins[0] == pytest.approx(right_origins[1], abs=.02)
    assert right_origins[2] == pytest.approx(right_origins[1]-6, abs=.02)
    for side in ('left', 'right', 'top', 'bottom'):
        side_sheet = caller_sheet([('side border', Paragraph, dict(
            border=Stroke(2*PT, HexColor('c02040')), background_color=HexColor('e0d080'),
            **{'border_'+side: Stroke(5*PT, HexColor('208040'))}))])
        side_snap = style_snapshot(tmp_path / side, [Paragraph('Sideborder')], side_sheet, observer)
        token_spans(side_snap, 'Sideborder')
        marks = [d for page in side_snap['pages'] for d in page['drawings']]
        boxes = [d['rect'] for d in marks if d['fill'] is not None]
        assert len(boxes) == 1, marks
        edges = [d for d in marks if d['color'] is not None and tuple(d['color']) == pytest.approx((32/255,128/255,64/255), abs=.001)]
        assert len(edges) == 1, marks
        edge = edges[0]
        assert edge['width'] == pytest.approx(5, abs=.01)
        x0,y0,x1,y1 = boxes[0]
        a,b,c,d = edge['rect']
        # Side identity matters; the stroke's inward/centered placement does not.
        if side in ('left', 'right'):
            assert abs(c-a) < .02 and d-b > 0
            near, far = (x0,x1) if side == 'left' else (x1,x0)
            assert abs(a-near) < abs(a-far)
        else:
            assert abs(d-b) < .02 and c-a > 0
            near, far = (y0,y1) if side == 'top' else (y1,y0)
            assert abs(b-near) < abs(b-far)
    # A live baseline proves that hiding a label removes an otherwise rendered label.
    baseline = style_snapshot(tmp_path / 'labels',
        [List([ListItem(StaticGroupedFlowables([Paragraph('Listbody')]))], style='hiddenlabel')],
        caller_sheet([('caller bullet', List.like('hiddenlabel'),
                       dict(bullet=SingleStyledText('Marker')))], base='sphinx_article'), observer)
    assert 'Listbody' in pdf_plain_text(baseline)
    assert 'Marker' in pdf_plain_text(baseline)
    assert 'Marker' not in text


def test_style_report_element_matches_selected_and_inherited_source(tmp_path, observer):
    base = caller_sheet([('general', Paragraph, dict(font_size=12*PT)),
                         ('selected', Paragraph.like('marked'), dict(font_size=20*PT))], name='Report base')
    derived = StyleSheet('Report derived', base=base)
    derived('selected', base='general', font_color=HexColor('204080'))
    destination = tmp_path / 'report'
    snap = style_snapshot(destination, [Paragraph('Reportmarked', style='marked'), Paragraph('Reportunmarked')], derived, observer)
    assert_token_style(snap, 'Reportmarked', size=12, color=0x204080)
    assert_token_style(snap, 'Reportunmarked', size=12)
    records = style_report_records(destination.with_suffix('.stylelog'))
    for token, expected, unmatched in [
            ('Reportmarked', {'selected':('>','Report derived','general'), 'general':(' ','Report base',None)}, ()),
            ('Reportunmarked', {'general':('>','Report base',None)}, ('selected',))]:
        matches = [r['matches'] for r in records if r['element'].startswith("Paragraph('") and token in r['element']]
        assert matches, (token, records)
        for rows in matches:
            by_name = {r['name']:r for r in rows}
            # Only styles that match the element are reported for it.
            assert not set(unmatched) & set(by_name), rows
            for name, (marker, source, parent) in expected.items():
                assert name in by_name, rows
                assert by_name[name]['mark'] == marker
                assert by_name[name]['sheet'] == source
                if parent is not None:
                    assert by_name[name]['base'] == parent
