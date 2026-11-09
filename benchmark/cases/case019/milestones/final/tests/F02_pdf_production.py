# feature: F02
"""Acceptance checks for programmatic PDF delivery and document properties."""

from _helpers import call_public, observe_pdf
from F01_helpers import pdf_observer_environment
from F02_helpers import pdf_plain_text, render_plain_article
from talvo.text import MixedStyledText, SingleStyledText


def test_programmatic_paragraphs_and_reading_order(tmp_path):
    observer_env = pdf_observer_environment(tmp_path / 'pdf-observer')
    paragraphs = ['Zebras rest beside the quiet lake.',
                  'Amber boats cross the blue sea.',
                  'Moss grows near the stone gate.']
    # Reverse the order and change content as well: neither alphabetical order
    # nor a fixed document can stand in for the caller's document tree.
    scenarios = [(paragraphs, (420, 560)),
                 ([paragraphs[2], 'Silver bells ring at noon.', paragraphs[0]],
                  (500, 640))]
    for index, (content, page_size) in enumerate(scenarios):
        destination = tmp_path / ('programmatic-{}'.format(index))
        result = call_public(render_plain_article, destination, content,
                             page_size)
        assert result.exception is None, result.traceback
        assert result.value is True
        pdf = observe_pdf(destination.with_suffix('.pdf'), env=observer_env)
        assert pdf['pages']
        for page in pdf['pages']:
            assert page['rect'][2] - page['rect'][0] == page_size[0]
            assert page['rect'][3] - page['rect'][1] == page_size[1]
        # Ignore line/page breaks introduced by legal layout choices.
        text = pdf_plain_text(pdf)
        positions = [text.index(paragraph) for paragraph in content]
        assert positions == sorted(positions)


def test_file_destination_and_missing_destination(tmp_path):
    observer_env = pdf_observer_environment(tmp_path / 'pdf-observer')
    # Different existing directories and stems must both be honoured.
    for index, directory in enumerate(('chosen folder', 'other folder')):
        parent = tmp_path / directory
        parent.mkdir()
        destination = parent / ('caller report {}'.format(index))
        paragraph = 'The chosen file contains this caller supplied text.'
        result = call_public(render_plain_article, destination, [paragraph])
        assert result.exception is None, result.traceback
        assert result.value is True
        pdf = observe_pdf(parent / (destination.name + '.pdf'), env=observer_env)
        text = pdf_plain_text(pdf)
        assert paragraph in text
    refused = call_public(render_plain_article, None, [paragraph])
    assert isinstance(refused.exception, ValueError), refused


def test_plain_and_styled_title_author_properties(tmp_path):
    observer_env = pdf_observer_environment(tmp_path / 'pdf-observer')
    scenarios = [({'title': 'Harbor survey', 'author': 'Renée Santos'},
                  ('Harbor survey', 'Renée Santos')),
                 ({'title': MixedStyledText([
                       SingleStyledText('Forest', style='emphasis'),
                       ' field ', SingleStyledText('notes', style='strong')]),
                   'author': MixedStyledText([
                       'Zoë ', SingleStyledText('Martin', style='emphasis')])},
                  ('Forest field notes', 'Zoë Martin'))]
    for index, (metadata, expected) in enumerate(scenarios):
        destination = tmp_path / ('properties-{}'.format(index))
        result = call_public(render_plain_article, destination,
                             ['A short report about the natural world.'],
                             kwargs={'metadata': metadata})
        assert result.exception is None, result.traceback
        assert result.value is True
        pdf = observe_pdf(destination.with_suffix('.pdf'), env=observer_env)
        assert pdf['metadata']['title'] == expected[0]
        assert pdf['metadata']['author'] == expected[1]
