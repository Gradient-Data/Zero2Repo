# feature: F04
"""Acceptance tests for real font selection and visible typography."""

import warnings
import pytest

from _helpers import call_public, isolated_workspace, run_python
from F04_helpers import (ASSETS, assert_glyph_outlines, body_glyphs,
                         font_expectation, font_observer_environment,
                         render_font_text, supplied_typeface, google_font_services)


def test_supplied_font_formats_and_unicode(tmp_path):
    environment = font_observer_environment(tmp_path / 'observer')
    for kind, text in [('otf', 'RαΩm'), ('ttf', 'RЖαm'),
                       ('type1', 'Ramb'), ('embedded-type1', '€')]:
        family = supplied_typeface(kind)
        destination = tmp_path / kind
        assert render_font_text(destination, text, family,
                                kerning=False, ligatures=False)
        glyphs = body_glyphs(destination, environment)
        assert len(glyphs) == len(text)
        if kind == 'embedded-type1':
            assert_glyph_outlines(destination, glyphs, environment,
                type1=str(ASSETS / 'F04_FreeEuro.pfa'), text=text)
        elif kind == 'type1':
            assert_glyph_outlines(destination, glyphs, environment,
                                  core='tiro', text=text)
        else:
            expected = font_expectation(text, environment, kind=kind)
            assert_glyph_outlines(destination, glyphs, environment,
                                  names=expected['names'], kind=kind)


    # Vary one face dimension at a time; this is not a Cartesian product.
    # Matching is proved by the selected outlines after style binding.
    from talvo.font import Typeface
    family = Typeface('Caller multi-face', *[supplied_typeface(kind).get_font(
        **choices) for kind, choices in [
            ('ttf', {}), ('bold', {'weight': 700}),
            ('italic', {'slant': 'italic'}), ('condensed', {'width': 4})]])
    for kind, choices in [('ttf', {}), ('bold', {'font_weight': 700}),
                          ('italic', {'font_slant': 'italic'}),
                          ('condensed', {'font_width': 4})]:
        destination = tmp_path / ('face-' + kind)
        text = 'Ramb'
        assert render_font_text(destination, text, family,
                                kerning=False, ligatures=False, **choices)
        glyphs = body_glyphs(destination, environment)
        expected = font_expectation(text, environment, kind=kind)
        assert len(glyphs) == len(expected['names'])
        assert_glyph_outlines(destination, glyphs, environment,
                              names=expected['names'], kind=kind)


def test_builtin_installed_and_assembled_typefaces(tmp_path):
    import importlib.metadata as metadata
    from talvo.font import Typeface
    environment = font_observer_environment(tmp_path / 'observer')
    # ITC ZapfDingbats is selected by the name its distribution registered
    # (installers may or may not keep the space), read from package metadata.
    zapf = [ep.name for ep in metadata.entry_points(group='talvo.typefaces')
            if ''.join(ep.name.split()).casefold() == 'itczapfdingbats']
    assert zapf, 'ITC ZapfDingbats must be a registered typeface'
    # Independent PDF core-font faces. Special families get characters from
    # their actual repertoire rather than an ordinary Latin fallback.
    for family_name, core, text in [
            ('Courier', 'cour', 'Ramb'), ('Helvetica', 'helv', 'Ramb'),
            ('Times', 'tiro', 'Ramb'), ('Symbol', 'symb', 'αβγ'),
            (zapf[0], 'zapfdingbats', '✁✂✃')]:
        destination = tmp_path / core
        assert render_font_text(destination, text, Typeface(family_name),
                                kerning=False, ligatures=False)
        glyphs = body_glyphs(destination, environment)
        assert len(glyphs) == len(text)
        assert_glyph_outlines(destination, glyphs, environment,
                              core=core, text=text)
    # Installed-name selection and direct caller assembly have the same
    # independently supplied font as an oracle, not each other as an oracle.
    for index, family in enumerate((Typeface('DejaVu Serif'),
                                    supplied_typeface('ttf'))):
        destination = tmp_path / ('named-{}'.format(index))
        text = 'RЖαm'
        assert render_font_text(destination, text, family,
                                kerning=False, ligatures=False)
        glyphs = body_glyphs(destination, environment)
        expected = font_expectation(text, environment, kind='ttf')
        assert len(glyphs) == len(expected['names'])
        assert_glyph_outlines(destination, glyphs, environment,
                              names=expected['names'], kind='ttf')


def test_default_and_explicit_kerning_and_ligatures(tmp_path):
    environment = font_observer_environment(tmp_path / 'observer')
    # Read the independent AFM input, not the product's font metrics parser.
    afm = (ASSETS / 'F04_Times-Roman.afm').read_text()
    a_record = next(line for line in afm.splitlines() if '; N A ;' in line)
    a_width = float(next(field.split()[1] for field in a_record.split(';')
                         if field.strip().startswith('WX ')))
    pair = next(line for line in afm.splitlines() if line.startswith('KPX A V '))
    adjustment = float(pair.split()[3])
    assert adjustment != 0, 'The real input must exercise a kerning pair'
    for index, switch in enumerate((None, False, True)):
        destination = tmp_path / ('kern-{}'.format(index))
        choices = {} if switch is None else {'kerning': switch}
        assert render_font_text(destination, 'AV', supplied_typeface('type1'),
                                ligatures=False, **choices)
        glyphs = body_glyphs(destination, environment)
        assert len(glyphs) == 2
        expected_advance = (a_width + (0 if switch is False else adjustment))*24/1000
        assert glyphs[1][2][0] - glyphs[0][2][0] == pytest.approx(
            expected_advance, abs=0.02)
        assert_glyph_outlines(destination, glyphs, environment,
                              core='tiro', text='AV')
    ordinary = font_expectation('fi', environment)
    combined = font_expectation('fi', environment, feature='liga')
    assert len(combined['names']) < len(ordinary['names'])
    for index, switch in enumerate((None, False, True)):
        destination = tmp_path / ('liga-{}'.format(index))
        choices = {} if switch is None else {'ligatures': switch}
        assert render_font_text(destination, 'fi', supplied_typeface('otf'),
                                kerning=False, **choices)
        glyphs = body_glyphs(destination, environment)
        expected = ordinary if switch is False else combined
        assert len(glyphs) == len(expected['names'])
        assert_glyph_outlines(destination, glyphs, environment,
                              names=expected['names'])


def test_small_capitals_and_old_style_figures(tmp_path):
    environment = font_observer_environment(tmp_path / 'observer')
    for variant, feature, text in [('small capital', 'smcp', 'abcd'),
                                   ('oldstyle figures', 'onum', '0123456789')]:
        ordinary = font_expectation(text, environment)
        alternate = font_expectation(text, environment, feature=feature)
        assert alternate['names'] != ordinary['names']
        for index, selected in enumerate(('normal', variant)):
            destination = tmp_path / (feature + str(index))
            assert render_font_text(destination, text, supplied_typeface('otf'),
                                    font_variant=selected,
                                    kerning=False, ligatures=False)
            glyphs = body_glyphs(destination, environment)
            expected = ordinary if selected == 'normal' else alternate
            assert len(glyphs) == len(expected['names'])
            assert_glyph_outlines(destination, glyphs, environment,
                                  names=expected['names'])


def test_direct_missing_glyph_requests():
    from talvo.font import MissingGlyphException, Typeface
    # This Type1 face has a known, independently readable ordinary repertoire.
    font = Typeface('Times').get_font(weight=400)
    afm = (ASSETS / 'F04_Times-Roman.afm').read_text()
    for char, name in [('A', 'A'), ('m', 'm')]:
        record = next(line for line in afm.splitlines()
                      if '; N ' + name + ' ;' in line)
        width = float(next(field.split()[1] for field in record.split(';')
                           if field.strip().startswith('WX ')))
        result = call_public(font.get_glyph_metrics, char, 'normal')
        assert result.exception is None, result.traceback
        assert result.value.width == width
        assert result.value.name == name
    for char in ('\u2024', 'Ж'):
        result = call_public(font.get_glyph_metrics, char, 'normal')
        assert isinstance(result.exception, MissingGlyphException), result


def test_google_font_family_in_fresh_offline_processes(tmp_path):
    import os

    environment = font_observer_environment(tmp_path / 'observer')
    # The first process starts with no acquired family. The mirror serves the
    # real upstream manifest and font; no product call or result is replaced.
    with isolated_workspace(parent=tmp_path) as workspace:
        family_directory = (workspace.root / 'data' / 'talvotype'
                            / 'google_fonts' / 'Abel')
        assert not family_directory.exists()
        child_env = dict(workspace.env)
        child_env['PYTHONPATH'] = os.pathsep.join(
            [str(ASSETS.parent), child_env.get('PYTHONPATH', '')])
        source = """import sys
from pathlib import Path
from talvo.font import Typeface
from F04_helpers import render_font_text
family = Typeface('Abel')
assert render_font_text(Path(sys.argv[1]), sys.argv[2], family,
                        kerning=False, ligatures=False)
"""
        # Fresh interpreters exclude in-memory reuse. The second interpreter
        # has no reachable font service, and must use the first one's acquisition.
        for index, text in enumerate(('Ramb', 'Copper')):
            destination = workspace.output / ('google-' + str(index))
            if index == 0:
                with google_font_services(child_env) as service:
                    result = run_python(source, args=(str(destination), text),
                        env=service.env, cwd=workspace.work, timeout=90)
            else:
                offline = dict(child_env, HTTPS_PROXY='http://127.0.0.1:1',
                               HTTP_PROXY='http://127.0.0.1:1', NO_PROXY='',
                               https_proxy='http://127.0.0.1:1',
                               http_proxy='http://127.0.0.1:1', no_proxy='')
                result = run_python(source, args=(str(destination), text),
                                    env=offline, cwd=workspace.work, timeout=90)
            assert result.returncode == 0, result
            glyphs = body_glyphs(destination, environment)
            expected = font_expectation(text, environment, kind='google')
            assert len(glyphs) == len(expected['names'])
            assert_glyph_outlines(destination, glyphs, environment,
                                  names=expected['names'], kind='google')


def test_positive_negative_and_default_character_spacing(tmp_path):
    from talvo.dimension import PT
    environment = font_observer_environment(tmp_path / 'observer')
    text = 'mmmm'
    expected = font_expectation(text, environment, kind='ttf')
    for index, additional in enumerate((None, 0, 2.5, -1.25)):
        destination = tmp_path / ('spacing-{}'.format(index))
        choices = {} if additional is None else {'character_spacing': additional*PT}
        assert render_font_text(destination, text, supplied_typeface('ttf'),
                                kerning=False, ligatures=False, **choices)
        glyphs = body_glyphs(destination, environment)
        assert len(glyphs) == len(text)
        assert_glyph_outlines(destination, glyphs, environment,
                              names=expected['names'], kind='ttf')
        for left, right, advance in zip(glyphs, glyphs[1:], expected['advances']):
            assert right[2][0] - left[2][0] == pytest.approx(
                advance + (0 if additional is None else additional), abs=0.02)


def test_font_face_choice_parsing_and_rejection():
    from talvo.attribute import ParseError
    from talvo.font.style import FontSlant, FontWeight, FontWidth
    for spelling in ('upright', 'oblique', 'italic'):
        assert FontSlant.from_string(spelling) == spelling
    widths = ('ultra-condensed', 'extra-condensed', 'condensed',
              'semi-condensed', 'normal', 'semi-expanded', 'expanded',
              'extra-expanded', 'ultra-expanded')
    for number, spelling in enumerate(widths, 1):
        assert FontWidth.from_string(spelling) == number
    # The entire integer interval is small enough to check without sampling.
    for weight in range(1001):
        assert FontWeight.from_string(str(weight)) == weight
    for klass, spellings in [(FontSlant, ('sideways',)),
                              (FontWidth, ('narrowish',)),
                              (FontWeight, ('1001', 'heavyish'))]:
        for spelling in spellings:
            with pytest.raises((ValueError, ParseError)):
                klass.from_string(spelling)
    with pytest.raises((ValueError, ParseError)):
        FontWeight.from_string('-1')


def test_unavailable_face_substitution_and_warning(tmp_path):
    from talvo.warnings import TalvoWarning
    environment = font_observer_environment(tmp_path / 'observer')
    family = supplied_typeface('otf')
    # Control: the family's own face is available, so requesting it is not a
    # substitution and must not warn.
    with warnings.catch_warnings(record=True) as exact:
        warnings.simplefilter('always')
        assert family.get_font(weight=400, slant='upright', width=5) in list(family.fonts())
    assert not [item for item in exact if issubclass(item.category, TalvoWarning)
                and 'Falling back to' in str(item.message)], exact
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        selected = family.get_font(weight=700, slant='italic', width=5)
    assert selected in list(family.fonts())
    records = [str(item.message) for item in caught
               if issubclass(item.category, TalvoWarning)]
    assert records, caught
    # The short substitution marker separates requested and selected face
    # descriptions. The surrounding explanatory sentences are not asserted.
    assert any(family.name in message.partition('Falling back to')[0]
               and 'normal bold italic' in message.partition('Falling back to')[0]
               and 'normal regular upright' in message.partition('Falling back to')[2]
               for message in records), records
    destination = tmp_path / 'substituted'
    with warnings.catch_warnings(record=True) as rendering_warnings:
        warnings.simplefilter('always')
        assert render_font_text(destination, 'Ramb', family,
                                font_slant='italic', font_width=5,
                                font_weight=700, kerning=False, ligatures=False)
    assert any(issubclass(item.category, TalvoWarning)
               for item in rendering_warnings), rendering_warnings
    glyphs = body_glyphs(destination, environment)
    expected = font_expectation('Ramb', environment)
    assert len(glyphs) == len(expected['names'])
    assert_glyph_outlines(destination, glyphs, environment,
                          names=expected['names'])
