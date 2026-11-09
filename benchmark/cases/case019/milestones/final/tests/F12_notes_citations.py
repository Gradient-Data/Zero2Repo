# feature: F12
"""Acceptance tests for note labels, links and placement."""
import sys

import pytest
from talvo.reference import NoteMarkerByID, NoteMarkerWithNote
from talvo.paragraph import Paragraph
from talvo.flowable import PageBreak
from talvo.text import SingleStyledText
from F01_helpers import pdf_observer_environment
from F07_helpers import token_box, line_containing, list_label_text, visible_lines
from F09_helpers import compact_line, resolved_internal_links
from F12_helpers import make_note, note_snapshot, assert_note_destination, note_line_draw_bounds


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


def test_note_reference_order_labels_and_links(tmp_path, observer):
    first_declared = make_note('Declaredfirstbody', id='earlier', style='body')
    second_declared = make_note('Declaredsecondbody', id='later', style='body')
    explicit = make_note('Explicitnotebody', style='body')
    destination = tmp_path / 'labels'
    snap = note_snapshot(destination, [
        first_declared, second_declared,
        Paragraph(['Firstcall', NoteMarkerByID('later'), ' End']),
        Paragraph(['Secondcall ', NoteMarkerByID('earlier'), ' End']),
        Paragraph(['Namedcall ', NoteMarkerWithNote(explicit,
            custom_label=SingleStyledText('Harbor'), style='explicit'), ' End']),
        explicit,
        Paragraph(['Againcall ', NoteMarkerByID('later'), ' End'])], observer)
    links = resolved_internal_links(destination.with_suffix('.pdf'), observer)
    for anchor, label, body in (
            ('Firstcall', '1', 'Declaredsecondbody'),
            ('Secondcall', '2', 'Declaredfirstbody'),
            ('Namedcall', 'Harbor', 'Explicitnotebody'),
            ('Againcall', '1', 'Declaredsecondbody')):
        assert compact_line(snap, anchor) == anchor + label + 'End'
        assert list_label_text(snap, body) == label
        assert_note_destination(snap, links, anchor, body, label)


def test_footer_notes_first_reference_reserve_space_and_deduplicate(tmp_path, observer):
    alpha = make_note('Alphanotebody\nAlphanotecontinuation', id='alpha')
    beta = make_note('Betanotebody', id='beta')
    elements = [alpha, beta,
        Paragraph(['Earlycall ', NoteMarkerByID('alpha'), ' End']),
        Paragraph(['Repeatcall ', NoteMarkerByID('alpha'), ' End'])]
    elements += [Paragraph(f'Bodyrow{i:02d}') for i in range(32)]
    elements += [PageBreak(), Paragraph(['Latecall ', NoteMarkerByID('beta'), ' End']),
                 Paragraph('Lastbodyrow')]
    snap = note_snapshot(tmp_path / 'footers', elements, observer)
    for body, anchor in (('Alphanotebody', 'Earlycall'), ('Betanotebody', 'Latecall')):
        note = line_containing(snap, body)
        call = token_box(snap, anchor)
        assert note['page'] == call['page']
        # The configured content bottom is 270 points; no fixed whitespace is required.
        assert note['bbox'][1] > 150
        assert token_box(snap, body)['y'] <= 270
        for line in visible_lines(snap):
            if line['page'] == note['page'] and (
                    line['text'].startswith(('Bodyrow', 'Earlycall', 'Repeatcall',
                                             'Latecall', 'Lastbodyrow'))):
                assert note_line_draw_bounds(snap, line['text'])[1] <= note_line_draw_bounds(snap, body)[0]
    assert token_box(snap, 'Repeatcall')['page'] == token_box(snap, 'Earlycall')['page']
    assert token_box(snap, 'Latecall')['page'] > token_box(snap, 'Earlycall')['page']
    assert token_box(snap, 'Bodyrow31')['page'] > token_box(snap, 'Earlycall')['page']
    assert compact_line(snap, 'Earlycall') == 'Earlycall1End'
    assert compact_line(snap, 'Repeatcall') == 'Repeatcall1End'
    assert compact_line(snap, 'Latecall') == 'Latecall2End'
    for i in range(32):
        token_box(snap, f'Bodyrow{i:02d}')
    token_box(snap, 'Alphanotecontinuation')


def test_in_place_notes_and_citation_body_or_footer(tmp_path, observer):
    for location in ('body', 'footer'):
        note = make_note('Inplacenotebody', id='ordinary', style='body')
        citation = make_note('Citationentrybody', id='citation', style=location)
        destination = tmp_path / location
        snap = note_snapshot(destination, [
            Paragraph(['Notecall ', NoteMarkerByID('ordinary'), ' End']),
            Paragraph(['Citecall ', NoteMarkerByID('citation',
                custom_label=SingleStyledText('RiverAtlas'), style='explicit'), ' End']),
            Paragraph('Beforeentries'), note, citation, Paragraph('Afterentries')], observer)
        assert compact_line(snap, 'Notecall') == 'Notecall1End'
        assert compact_line(snap, 'Citecall') == 'CitecallRiverAtlasEnd'
        assert list_label_text(snap, 'Inplacenotebody') == '1'
        assert list_label_text(snap, 'Citationentrybody') == 'RiverAtlas'
        before = token_box(snap, 'Beforeentries')
        after = token_box(snap, 'Afterentries')
        placed = token_box(snap, 'Inplacenotebody')
        cited = token_box(snap, 'Citationentrybody')
        assert before['page'] == placed['page'] == after['page'] == cited['page']
        assert before['y'] < placed['y'] < after['y']
        if location == 'body':
            assert placed['y'] < cited['y'] < after['y']
        else:
            assert cited['y'] > after['y']
            assert line_containing(snap, 'Citationentrybody')['bbox'][1] > 150
        links = resolved_internal_links(destination.with_suffix('.pdf'), observer)
        assert_note_destination(snap, links, 'Notecall', 'Inplacenotebody', '1')
        assert_note_destination(snap, links, 'Citecall', 'Citationentrybody', 'RiverAtlas')
