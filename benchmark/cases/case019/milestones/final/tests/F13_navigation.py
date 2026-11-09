# feature: F13
"""Acceptance tests for generated contents, caption lists and PDF outlines."""
import sys

import pytest
from talvo.structure import TableOfContents, TableOfContentsStyle, Section, Heading
from talvo.paragraph import Paragraph
from talvo.flowable import PageBreak
from talvo.image import Figure, Caption, ListOfFigures
from talvo.table import Table, TableBody, TableWithCaption, ListOfTables
from F01_helpers import pdf_observer_environment
from F07_helpers import visible_lines
from F11_helpers import table_row
from F13_helpers import (navigation_section, navigation_snapshot, navigation_rows,
                         assert_navigation, content_line, resolved_navigation_outline)


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


def test_global_contents_depth_visibility_and_final_pages(tmp_path, observer):
    for depth in (None, 2, 4):
        toc = TableOfContents(style=None if depth is None else TableOfContentsStyle(depth=depth))
        branch = navigation_section('Cedar', 'I', [
            navigation_section('Birch', 'Ia', [
                navigation_section('Maple', 'IaA', [navigation_section('Willow', 'IaAi')])]),
            navigation_section('Omitted', 'X', [navigation_section('Removedchild', 'Xa')], style='excluded'),
            navigation_section('Invisible', 'Y', [navigation_section('Invisiblechild', 'Ya')], style='hidden')])
        snap = navigation_snapshot(tmp_path / f'global{depth}', [toc, branch,
            navigation_section('Juniper', 'II')], observer)
        selected = [('I', 'Cedar'), ('Ia', 'Birch')]
        if depth != 2:
            selected.append(('IaA', 'Maple'))
        if depth == 4:
            selected.append(('IaAi', 'Willow'))
        selected.append(('II', 'Juniper'))
        assert_navigation(snap, 'TOC', selected)
        content_line(snap, 'Omitted')
        assert not any('Invisible' in line['text'] for line in visible_lines(snap))


def test_local_contents_descendants_and_selected_depth(tmp_path, observer):
    for depth in (1, 2, 3):
        snap = navigation_snapshot(tmp_path / f'local{depth}', [
            navigation_section('Elsewhere', 'I', [navigation_section('Outsidechild', 'Ia')]),
            navigation_section('Container', 'II', [
                navigation_section('Localroot', 'IIa', [
                    TableOfContents(local=True, style=TableOfContentsStyle(depth=depth)),
                    navigation_section('Localchild', 'IIaA', [navigation_section('Localdeep', 'IIaAi')]),
                    navigation_section('Localpeer', 'IIaB')])]),
            navigation_section('Following', 'III')], observer)
        # Local depth includes the containing level; entries start at its children.
        selected = [] if depth == 1 else [('IIaA', 'Localchild')]
        if depth == 3:
            selected.append(('IIaAi', 'Localdeep'))
        if depth > 1:
            selected.append(('IIaB', 'Localpeer'))
        assert_navigation(snap, 'TOC', selected)


def test_caption_lists_order_numbered_only_and_final_pages(tmp_path, observer):
    for populated in (False, True):
        elements = [ListOfFigures(), ListOfTables(), Paragraph('Listboundary')]
        if populated:
            elements += [PageBreak(), Figure([Paragraph('Artworkone'), Caption('Seabird')]),
                TableWithCaption([Table(TableBody([table_row('Cellone')])), Caption('Rainfall')]),
                PageBreak(), TableWithCaption([Table(TableBody([table_row('Celltwo')])), Caption('Altitude')]),
                Figure([Paragraph('Artworktwo'), Caption('Mountain')]),
                Figure([Paragraph('Artworkthree'), Caption('Unlistedfigure', style='unnumbered')]),
                TableWithCaption([Table(TableBody([table_row('Cellthree')])),
                                  Caption('Unlistedtable', style='unnumbered')])]
        snap = navigation_snapshot(tmp_path / f'lists{populated}', elements, observer)
        assert_navigation(snap, 'FIG', [('1', 'Seabird'), ('2', 'Mountain')] if populated else [])
        assert_navigation(snap, 'TAB', [('1', 'Rainfall'), ('2', 'Altitude')] if populated else [])
        content_line(snap, 'Listboundary')
        if populated:
            content_line(snap, 'Unlistedfigure')
            content_line(snap, 'Unlistedtable')


def test_pdf_outline_hierarchy_titles_numbers_and_destinations(tmp_path, observer):
    snap = navigation_snapshot(tmp_path / 'outline', [TableOfContents(),
        # 'Inlet' starts mid-page, after North's body, so its destination is
        # distinguishable from the top of the page.
        navigation_section('North', 'I', [
            Section([Heading('Inlet', custom_label='Ib'), Paragraph('BodyInlet')]),
            navigation_section('Coast', 'Ia', [
            navigation_section('Cove', 'IaA')]),
            navigation_section('Excluded', 'X', [navigation_section('Bannedchild', 'Xa')], style='excluded'),
            navigation_section('Hidden', 'Y', [navigation_section('Hiddenchild', 'Ya')], style='hidden')]),
        navigation_section('South', 'II')], observer)
    expected = [(1, 'I', 'North'), (2, 'Ib', 'Inlet'), (2, 'Ia', 'Coast'),
                (3, 'IaA', 'Cove'), (1, 'II', 'South')]
    outline = resolved_navigation_outline((tmp_path / 'outline').with_suffix('.pdf'), observer)
    assert len(outline) == len(expected)
    for row, (level, label, title) in zip(outline, expected):
        target = content_line(snap, title)
        assert row[0] == level
        assert row[1].split() == [label, title]
        assert row[2] == target['page'] + 1
        assert row[3]['page'] == target['page']
        assert row[3]['to'][1] <= target['bbox'][3], row
        assert row[3]['to'][1] >= snap['pages'][target['page']]['rect'][1]
    inlet = [row for row in outline if row[1].split()[-1] == 'Inlet'][0]
    preceding = [line for line in visible_lines(snap) if line['text'] == 'BodyNorth'][0]
    assert inlet[3]['page'] == preceding['page']
    assert inlet[3]['to'][1] > preceding['bbox'][1], (inlet, preceding)
