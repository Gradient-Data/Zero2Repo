# feature: F03
"""Acceptance checks for installed resources and registered-name selection."""

import importlib.metadata as metadata
import re
import struct
import sys
import unicodedata

from _helpers import installed_distributions, observe_pdf
from F01_helpers import pdf_observer_environment
from F02_helpers import pdf_plain_text
from F03_helpers import (install_resource_bundle, listed_faces, listed_names,
                         listed_options, resource_cli)


def test_installed_resource_listings():
    inventory = installed_distributions(sys.executable)
    for kind, group in [('formats', 'talvo.frontends'),
                        ('templates', 'talvo.templates'),
                        ('stylesheets', 'talvo.stylesheets'),
                        ('fonts', 'talvo.typefaces')]:
        expected = {ep['name'].casefold() for dist in inventory
                    for ep in dist['entry_points'] if ep['group'] == group}
        assert expected, 'The acceptance image must contain installed resources'
        observed = listed_names(resource_cli('--list-' + kind), kind)
        if kind == 'fonts':
            expected = {''.join(name.split()) for name in expected}
            observed = {''.join(name.split()) for name in observed}
        assert expected <= observed


def test_extension_resources_are_discoverable_and_selectable(tmp_path):
    names, env = install_resource_bundle(tmp_path)
    for kind, name in [('formats', names['reader']),
                       ('templates', names['template']),
                       ('stylesheets', names['sheet']),
                       ('fonts', names['face'])]:
        assert name in listed_names(resource_cli('--list-' + kind, env=env), kind)
        # A fresh process without the installation must still describe its own
        # installation, rather than reusing a cached catalogue.
        assert name not in listed_names(resource_cli('--list-' + kind), kind)
    observer_env = pdf_observer_environment(tmp_path / 'observer')
    # No reader is registered for this extension: only the --format choice can
    # select the extension reader (the fallback reader would show it once).
    source = tmp_path / 'content.txt'
    for index, content in enumerate(('Copper birds fly.', 'Blue boats sail.')):
        source.write_text(content, encoding='utf-8')
        destination = tmp_path / ('selected-{}'.format(index))
        resource_cli(str(source), '--format', names['reader'],
                     '--template', names['template'], '--stylesheet', names['sheet'],
                     '--output', str(destination), env=env, cwd=tmp_path)
        pdf = observe_pdf(destination.with_suffix('.pdf'), env=observer_env)
        assert pdf_plain_text(pdf).count(content) == 2
        assert pdf['pages']
        for page in pdf['pages']:
            assert page['rect'] == [0, 0, 360, 500]
        spans = [span for page in pdf['pages']
                 for block in page['raw_text']['blocks'] if block['type'] == 0
                 for line in block['lines'] for span in line['spans']
                 if ''.join(char['c'] for char in span['chars']).strip()
                 and unicodedata.normalize('NFKC', ''.join(
                     char['c'] for char in span['chars'])).strip() in content
                 and any(char['c'].isalpha() for char in span['chars'])]
        assert spans, [(span['size'], ''.join(c['c'] for c in span['chars']))
                       for page in pdf['pages'] for block in page['raw_text']['blocks']
                       if block['type'] == 0 for line in block['lines']
                       for span in line['spans']]
        for span in spans:
            assert span['size'] == 19, span
            assert span['color'] == 0x0000ff
            # PDF subset tags are packaging, not a different selected font.
            assert re.fullmatch(r'(?:[A-Z]{6}\+)?Courier', span['font'], re.I)


def test_font_listing_includes_available_face_styles():
    observed = listed_faces(resource_cli('--list-fonts'))
    # Independent Adobe core font face catalogue (the AFM font names), not
    # values obtained from the product's typeface objects.
    # Which weight class a core face's AFM 'Medium'/'Roman' maps to is not
    # fixed; the catalogue fixes widths, slants and that Bold is the heavier.
    widths = ('ultra-condensed', 'extra-condensed', 'condensed',
              'semi-condensed', 'normal', 'semi-expanded', 'expanded',
              'extra-expanded', 'ultra-expanded')
    weights = {100: 'thin', 200: 'extra-light', 300: 'light', 400: 'regular',
               500: 'medium', 600: 'semi-bold', 700: 'bold', 800: 'extra-bold',
               900: 'heavy'}
    rank = {name: value for value, name in weights.items()}
    adobe_faces = {'courier': 'oblique', 'helvetica': 'oblique', 'times': 'italic'}
    for family, slant in adobe_faces.items():
        faces = observed[family]
        assert {width for width, _ in faces} == {'normal'}, faces
        upright = {style for _, style in faces if not style.startswith(slant + '-')}
        sloped = {style[len(slant) + 1:] for _, style in faces if style.startswith(slant + '-')}
        assert len(faces) == 4 and len(upright) == 2 and len(sloped) == 2, faces
        for group in (upright, sloped):
            assert 'bold' in group, faces
            other, = group - {'bold'}
            assert rank[other] < rank['bold'], faces
    for family in ('symbol', 'itc zapfdingbats'):
        faces = observed[family]
        assert len(faces) == 1 and next(iter(faces))[1] in rank, faces
        assert next(iter(faces))[0] == 'normal'
    # Read the actual installed OpenType/TrueType OS/2 table as independent
    # font metadata. No talvo font parser or face-selection method is called.
    for dist in metadata.distributions():
        entries = [ep for ep in dist.entry_points if ep.group == 'rinoh.typefaces']
        if not entries or dist.metadata['Name'] == 'talvotype':
            continue
        font_files = [path for path in dist.files
                      if path.suffix.lower() in ('.otf', '.ttf')]
        assert font_files, dist.metadata['Name']
        assert len(entries) == 1, 'Font package must identify its family unambiguously'
        expected = set()
        for path in font_files:
            data = dist.locate_file(path).read_bytes()
            count, = struct.unpack_from('>H', data, 4)
            tables = {data[offset:offset+4]: struct.unpack_from('>II', data, offset+8)
                      for offset in range(12, 12 + 16*count, 16)}
            offset, length = tables[b'OS/2']
            assert length >= 64
            weight, width = struct.unpack_from('>HH', data, offset+4)
            selection, = struct.unpack_from('>H', data, offset+62)
            slant = 'italic-' if selection & 1 else ''
            expected.add((widths[width-1], slant + weights[weight]))
        assert observed[entries[0].name.casefold()] == expected


def test_reader_option_types_defaults_and_no_options(tmp_path):
    names, env = install_resource_bundle(tmp_path)
    text = resource_cli('--list-options', names['reader'], env=env)
    assert listed_options(text) == {'copies': ('Integer', '2'),
                                    'uppercase': ('Bool', 'False')}
    # A positive status report names the selected reader; its explanatory
    # wording and the ordering of option records are not graded.
    for reader in (names['empty'], 'reStructuredText', 'CommonMark'):
        text = resource_cli('--list-options', reader, env=env)
        assert reader in text
        assert not any(line.startswith('- ') for line in text.splitlines())
        assert listed_options(text) == {}
