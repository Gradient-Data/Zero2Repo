# feature: F17
"""Acceptance tests for structured source readers, observed through PDF output."""
import sys

import pytest
from talvo.frontend.rst import ReStructuredTextReader
from talvo.frontend.commonmark import CommonMarkReader
from F01_helpers import pdf_observer_environment
from F02_helpers import pdf_plain_text
from F05_helpers import caller_sheet, assert_token_style, token_spans
from F07_helpers import token_box, line_containing, visible_lines
from F09_helpers import covering_links, resolved_internal_links
from F10_helpers import image_asset
from F17_helpers import (source_snapshot, parse_source, assert_source_words,
                         assert_inline_semantics, assert_block_semantics,
                         assert_reader_note_target, reader_styles, assert_source_artwork)
from _helpers import call_public, write_text


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


RST_BODY = '''Headingmarker
=============

Bodymarker Plainmarker *Emphasismarker* **Strongmarker** ``Codemarker``.

* Bulletmarker

1. Orderedmarker

Quoteintro

    Quotemarker

::

    Literalmarker

Nestedmarker
------------

:Fieldmarker: Fieldvaluemarker

--switch  Optionvaluemarker

.. warning:: Admonitionmarker
'''


def test_rst_structure_and_metadata(tmp_path, observer):
    source = '''Titlemarker
###########
Subtitlemarker
**************

:Author: Authormarker

''' + RST_BODY + '''

.. topic:: Abstract
   :class: abstract

   Abstractmarker
'''
    path = write_text(tmp_path / 'source.rst', source)
    for stream in (False, True):
        snap = source_snapshot(tmp_path / ('rst' + str(stream)), ReStructuredTextReader,
                               source if stream else path, observer, stream)
        assert_source_words(snap, 'Titlemarker', 'Subtitlemarker', 'Authormarker',
            'Abstractmarker', 'Fieldmarker', 'Fieldvaluemarker', '--switch',
            'Optionvaluemarker', 'Admonitionmarker')
        assert snap['metadata']['title'] == 'Titlemarker'
        assert snap['metadata']['author'] == 'Authormarker'
        assert token_box(snap, 'Titlemarker')['y'] < token_box(snap, 'Subtitlemarker')['y']
        assert_inline_semantics(snap)
        assert_block_semantics(snap)
        assert '**' not in pdf_plain_text(snap)
        assert token_box(snap, 'Abstractmarker')['page'] == 0
        assert token_box(snap, 'Abstractmarker')['y'] < token_box(snap, 'Bodymarker')['y']
        assert_token_style(snap, 'Admonitionmarker', color=0x00ff00)
        assert token_box(snap, 'Fieldvaluemarker')['x0'] > token_box(snap, 'Fieldmarker')['x0']
        assert token_box(snap, 'Optionvaluemarker')['x0'] > token_box(snap, '--switch')['x0']


def test_rst_embedded_features_and_relative_resources(tmp_path, observer):
    source_dir = tmp_path / 'sources'
    source_dir.mkdir()
    image_asset(source_dir / 'art.png')
    write_text(source_dir / 'part.rst', 'Includedmarker\n')
    source = '''.. contents:: Contentsmarker
   :local:

Sectionmarker
=============

.. include:: part.rst

+------------+------------+
| Cellalpha  | Cellbeta   |
+============+============+
| Cellgamma  | Celldelta  |
+------------+------------+

.. image:: art.png
   :width: 80pt

.. figure:: art.png
   :width: 80pt

   Captionmarker

See Externalmarker_ and Internalmarker_ and Footanchor [1]_ and Citeanchor [REF]_.

.. _Externalmarker: https://example.org/reader

.. _Internalmarker:

Targetmarker

.. [1] Footnotemarker
.. [REF] Citationmarker

Inlinebefore :math:`x^2` Inlineafter

Displaybefore

.. math::

   \\frac{x}{y}

Displayafter
'''
    path = write_text(source_dir / 'source.rst', source)
    destination = tmp_path / 'embedded'
    snap = source_snapshot(destination, ReStructuredTextReader, path, observer)
    assert_source_words(snap, 'Includedmarker', 'Cellalpha', 'Cellbeta', 'Cellgamma',
                        'Celldelta', 'Captionmarker', 'Footnotemarker', 'Citationmarker')
    assert token_box(snap, 'Cellalpha')['y'] == pytest.approx(token_box(snap, 'Cellbeta')['y'], abs=1)
    assert token_box(snap, 'Cellgamma')['y'] > token_box(snap, 'Cellalpha')['y']
    assert token_box(snap, 'Cellbeta')['x0'] > token_box(snap, 'Cellalpha')['x0']
    assert any(link.get('uri') == 'https://example.org/reader'
               for link in covering_links(snap, 'Externalmarker'))
    links = resolved_internal_links(destination.with_suffix('.pdf'), observer)
    assert_reader_note_target(snap, links, 'Footanchor', 'Footnotemarker', '1')
    assert_reader_note_target(snap, links, 'Citeanchor', 'Citationmarker', 'REF')
    internal = covering_links(snap, 'Internalmarker')
    assert internal
    target = token_box(snap, 'Targetmarker')
    size = token_spans(snap, 'Targetmarker')['size']
    assert any(link.get('page') == target['page'] and 'to' in link
               and target['y'] - 2*size <= link['to'][1] <= target['y'] + size
               for page in links for link in page if link['from'] == internal[0]['from'])
    headings = [line for line in visible_lines(snap) if 'Sectionmarker' in line['text']]
    assert len(headings) == 2
    assert any(link['from'][1] <= headings[0]['bbox'][3] and link['from'][3] >= headings[0]['bbox'][1]
               for link in snap['pages'][headings[0]['page']]['links'])
    assert_source_artwork(destination, snap, observer, 2)
    # Mathematics must produce actual ink in its reserved regions, not source text.
    from F15_helpers import math_ink
    before, after = token_box(snap, 'Displaybefore'), token_box(snap, 'Displayafter')
    boxes = math_ink(destination, observer, (0, before['y']+3, 600, after['y']-12))
    bar = max(boxes, key=lambda b: (b[2]-b[0])/max(.5, b[3]-b[1]))
    assert any(b[3] < bar[1] and b[0] < bar[2] and b[2] > bar[0] for b in boxes)
    assert any(b[1] > bar[3] and b[0] < bar[2] and b[2] > bar[0] for b in boxes)
    left, right = token_box(snap, 'Inlinebefore'), token_box(snap, 'Inlineafter')
    boxes = math_ink(destination, observer, (left['x1']+2, line_containing(snap, 'Inlinebefore')['bbox'][1]-2, right['x0']-2, left['y']+3))
    base = min(boxes, key=lambda b: b[0])
    assert any(b[0] >= base[2] and b[1] < base[1] for b in boxes), boxes
    assert '\\frac' not in pdf_plain_text(snap)


def test_commonmark_blocks_inline_images_and_links(tmp_path, observer):
    image_asset(tmp_path / 'art.png')
    source = '''Introparagraph

# Headingmarker

Bodymarker Plainmarker *Emphasismarker* **Strongmarker** `Codemarker`.

- Bulletmarker

1. Orderedmarker

> Quotemarker

```text
Literalmarker
```

## Nestedmarker

[Externalmarker](https://example.org/commonmark)

![Artwork](art.png)

Beforebreak

---

Afterbreak
'''
    source = source.replace('art.png', str(tmp_path / 'art.png'))
    path = write_text(tmp_path / 'source.md', source)
    for stream in (False, True):
        destination = tmp_path / ('markdown' + str(stream))
        snap = source_snapshot(destination, CommonMarkReader,
                               source if stream else path, observer, stream)
        assert_inline_semantics(snap)
        assert_block_semantics(snap)
        assert any(link.get('uri') == 'https://example.org/commonmark'
                   for link in covering_links(snap, 'Externalmarker'))
        assert_source_artwork(destination, snap, observer, 1)
        before, after = token_box(snap, 'Beforebreak'), token_box(snap, 'Afterbreak')
        assert any(before['y'] < drawing['rect'][1] < after['y']
                   and drawing['rect'][2] - drawing['rect'][0] > drawing['rect'][3] - drawing['rect'][1]
                   for drawing in snap['pages'][before['page']]['drawings'])
        assert '```' not in pdf_plain_text(snap)


def test_utf8_parsing_independent_of_template_and_styles(tmp_path, observer):
    from talvo.templates import Article, Book
    from talvo.paragraph import Paragraph
    from talvo.dimension import PT
    from talvo.color import Color
    for reader, suffix in ((ReStructuredTextReader, 'rst'), (CommonMarkReader, 'md')):
        path = write_text(tmp_path / ('unicode.' + suffix), 'Publicationtitle\n================\n\nCafé naïve résumé\n\nBodymarker\n')
        # UTF-8 regardless of the process locale: parse and publish in a child
        # whose locale encoding is ASCII (C locale, UTF-8 mode disabled).
        import os
        from _helpers import run_python, observe_pdf as observe
        child = dict(os.environ, LC_ALL='C', LANG='C', PYTHONUTF8='0',
                     PYTHONCOERCECLOCALE='0', PYTHONIOENCODING='utf-8')
        child.pop('LC_CTYPE', None)
        localized = tmp_path / ('locale-' + suffix)
        script = ('import sys, locale\n'
                  'assert locale.getpreferredencoding(False).lower() not in ("utf-8", "utf8")\n'
                  'from talvo.frontend.rst import ReStructuredTextReader\n'
                  'from talvo.frontend.commonmark import CommonMarkReader\n'
                  'from talvo.templates import Article\n'
                  'reader = {"rst": ReStructuredTextReader, "md": CommonMarkReader}[sys.argv[2]]\n'
                  'sys.exit(0 if Article(reader().parse(sys.argv[1])).render(sys.argv[3]) else 1)\n')
        run = run_python(script, args=(str(path), suffix, str(localized)),
                         env=child, cwd=tmp_path, timeout=120)
        assert run.returncode == 0, run
        assert_source_words(observe(localized.with_suffix('.pdf'), env=observer),
                            'Café naïve résumé', 'Bodymarker')
        # Parse first; the same public parsed result then receives publishing choices.
        tree = reader().parse(str(path))
        for index, (template, color) in enumerate(((Article, Color(1, 0, 0)), (Article, Color(0, 0, 1)), (Book, Color(0, 0, 1)))):
            sheet = caller_sheet([('body', Paragraph, dict(font_size=13*PT, font_color=color))], base=reader_styles())
            cfg = template.Configuration('after parsing', stylesheet=sheet)
            document = template(tree, configuration=cfg)
            destination = tmp_path / (suffix + str(index))
            result = call_public(document.render, str(destination), cwd=tmp_path, timeout=120)
            assert result.exception is None, result.traceback
            assert result.value is True, (result.stdout, result.stderr)
            from _helpers import observe_pdf
            snap = observe_pdf(destination.with_suffix('.pdf'), env=observer)
            assert_source_words(snap, 'Café naïve résumé', 'Bodymarker', 'Publicationtitle')
            title, body = token_box(snap, 'Publicationtitle'), token_box(snap, 'Bodymarker')
            if template is Article:
                assert title['page'] == body['page']
            else:
                assert title['page'] < body['page']
            assert_token_style(snap, 'Bodymarker', size=13, color=0xff0000 if index == 0 else 0x0000ff)


def test_unavailable_source_is_reported(tmp_path, observer):
    for reader, suffix in ((ReStructuredTextReader, 'rst'), (CommonMarkReader, 'md')):
        path = write_text(tmp_path / ('present.' + suffix), 'Availablemarker\n')
        snap = source_snapshot(tmp_path / ('available' + suffix), reader, path, observer)
        assert_source_words(snap, 'Availablemarker')
        result = call_public(parse_source, reader, tmp_path / ('missing.' + suffix))
        assert result.exception is not None
        from docutils.io import InputError
        assert isinstance(result.exception, InputError), result.traceback
