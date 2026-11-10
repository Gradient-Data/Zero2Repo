# feature: F14
"""Acceptance tests for alphabetical indexes in rendered PDF documents."""
import sys

import pytest
from talvo.index import (Index, IndexStyle, IndexTarget, InlineIndexTarget,
                         IndexTerm, IndexSee, IndexSeeAlso)
from talvo.paragraph import Paragraph
from talvo.text import MixedStyledText
from talvo.flowable import PageBreak
from F01_helpers import pdf_observer_environment
from F07_helpers import line_containing
from F14_helpers import index_snapshot, index_pdf_lines, index_line, index_words


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


def test_occurrences_merge_with_all_pages_and_nested_terms(tmp_path, observer):
    snap = index_snapshot(tmp_path / 'occurrences', [
        IndexTarget([IndexTerm('Orchard'), IndexTerm('Orchard', 'Citrus'),
                     IndexTerm('Orchard', 'Citrus', 'Lemon')]),
        Paragraph('Firstlocation'), PageBreak(), Paragraph('Unindexedfirst'), PageBreak(),
        Paragraph(MixedStyledText(['Secondlocation', InlineIndexTarget([
            IndexTerm('Orchard'), IndexTerm('Orchard', 'Citrus')])])),
        PageBreak(), Paragraph('Unindexedsecond'), PageBreak(),
        IndexTarget([IndexTerm('Orchard'), IndexTerm('Orchard', 'Pear')]),
        Paragraph('Thirdlocation'), PageBreak(), Index()], observer)
    pages = [line_containing(snap, marker)['page'] + 1
             for marker in ('Firstlocation', 'Secondlocation', 'Thirdlocation')]
    assert len(set(pages)) == 3
    for term, locations in [('Orchard', pages), ('Citrus', pages[:2]),
                            ('Lemon', pages[:1]), ('Pear', pages[2:])]:
        words = index_words(index_line(snap, term)['text'])
        assert words[0] == term
        assert sorted(words[1:]) == sorted(map(str, locations))
    entries = [line for line in index_pdf_lines(snap)
               if index_words(line['text'])[0] in ('Orchard', 'Citrus', 'Lemon', 'Pear')]
    assert [index_words(line['text'])[0] for line in entries] == ['Orchard', 'Citrus', 'Lemon', 'Pear']
    parent, child, grandchild, sibling = entries
    assert parent['bbox'][0] < child['bbox'][0] < grandchild['bbox'][0]
    assert sibling['bbox'][0] == pytest.approx(child['bbox'][0], abs=0.1)


def test_alphabetical_order_default_initials_and_disabled_grouping(tmp_path, observer):
    terms = ['Zebra', 'apricot', 'Banana', 'almond', '#hash', '3number']
    for grouping in (None, True, False):
        snap = index_snapshot(tmp_path / f'grouping{grouping}', [
            IndexTarget([IndexTerm(term) for term in terms]), Paragraph('Markedlocation'),
            PageBreak(), Index(style=None if grouping is None else IndexStyle(initials=grouping))], observer)
        expected_terms = ['#hash', '3number', 'almond', 'apricot', 'Banana', 'Zebra']
        page = line_containing(snap, 'Markedlocation')['page'] + 1
        for term in terms:
            line = index_line(snap, term)
            assert index_words(line['text'][len(term):]) == [str(page)]
        rows = index_pdf_lines(snap)
        entry_rows = [index_line(snap, term) for term in expected_terms]
        alphabetic = entry_rows[2:]
        assert [line for line in rows if line in alphabetic] == alphabetic
        labels = [line['text'].casefold() for line in rows if line not in entry_rows]
        if grouping is False:
            assert labels == []
        else:
            assert len(labels) == 4
            assert {'a', 'b', 'z'}.issubset(labels)
            symbol_label, = [label for label in labels if label not in ('a', 'b', 'z')]
            assert symbol_label.strip()
            # The output shell has standalone heading lines followed by their entries.
            groups = {}
            current = None
            for line in rows:
                if line not in entry_rows:
                    current = line['text'].casefold()
                    assert current not in groups
                    groups[current] = []
                else:
                    assert current is not None
                    groups[current].append(next(term for term in terms
                                                if line == index_line(snap, term)))
            assert groups['a'] == ['almond', 'apricot']
            assert groups['b'] == ['Banana']
            assert groups['z'] == ['Zebra']
            assert set(groups[symbol_label]) == {'#hash', '3number'}


def test_see_and_seealso_preserve_multiple_and_page_free_entries(tmp_path, observer):
    snap = index_snapshot(tmp_path / 'crossrefs', [IndexTarget([
        IndexTerm('Cedar'), IndexTerm('Birch'), IndexTerm('Maple'),
        IndexTerm('Oak'), IndexTerm('Ash'),
        IndexSee('Alias', 'Cedar'), IndexSee('Alias', 'Birch'),
        IndexSeeAlso('Alias', 'Maple'), IndexSeeAlso('Alias', 'Oak'),
        IndexSeeAlso('Cedar', 'Ash'), IndexSeeAlso('Cedar', 'Oak'),
        IndexSee('Redirect', 'Maple')]), Paragraph('Crosslocation'), PageBreak(), Index()], observer)
    page = str(line_containing(snap, 'Crosslocation')['page'] + 1)
    for term in ('Birch', 'Maple', 'Oak', 'Ash'):
        assert index_words(index_line(snap, term)['text']) == [term, page]
    alias = index_words(index_line(snap, 'Alias')['text'])
    assert alias[0] == 'Alias'
    assert len(alias[1:]) == 8
    assert sorted(zip(alias[1::2], alias[2::2])) == sorted([
        ('Refer', 'Cedar'), ('Refer', 'Birch'), ('Related', 'Maple'), ('Related', 'Oak')])
    cedar = index_words(index_line(snap, 'Cedar')['text'])
    assert cedar[:2] == ['Cedar', page]
    assert len(cedar[2:]) == 4
    assert sorted(zip(cedar[2::2], cedar[3::2])) == [('Related', 'Ash'), ('Related', 'Oak')]
    assert index_words(index_line(snap, 'Redirect')['text']) == ['Redirect', 'Refer', 'Maple']
