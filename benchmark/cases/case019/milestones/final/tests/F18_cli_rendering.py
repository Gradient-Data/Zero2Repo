# feature: F18
"""Command-line publication, failures and actual font specimens."""
import uuid
import sys
import os
import pytest

from _helpers import write_text, observe_pdf, isolated_workspace, installed_distributions
from F01_helpers import pdf_observer_environment
from F02_helpers import pdf_plain_text
from F03_helpers import install_resource_bundle, resource_cli, listed_faces
from F04_helpers import font_observer_environment, ASSETS, FONT_FILES
from F05_helpers import assert_token_style
from F07_helpers import line_containing, token_box, visible_lines
from F18_helpers import (conversion_cli, converted_pdf, assert_cli_refusal,
                         assert_specimen_outlines, installed_specimen_faces,
                         resource_services, TERMES_WHEEL, typeface_distribution)


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


def test_input_format_selection(tmp_path, observer):
    # Syntax whose visible result differs between the two real readers.
    cases = [('rst', 'Codemarker ``Literalmarker``', (), 'Literalmarker'),
             ('md', '# Headingmarker\n\nBodymarker', (), 'Headingmarker'),
             ('rst', '# Headingmarker\n\nBodymarker', ('--format', 'CommonMark'), 'Headingmarker'),
             ('md', 'Codemarker :literal:`Literalmarker`', ('--format', 'reStructuredText'), 'Literalmarker'),
             ('unknownextension', 'Codemarker ``Literalmarker``', (), 'Literalmarker')]
    for index, (ext, text, options, marker) in enumerate(cases):
        source = write_text(tmp_path / ('input' + str(index) + '.' + ext), text + '\n')
        destination = tmp_path / ('result' + str(index))
        result = conversion_cli(str(source), '--output', str(destination), *options, cwd=tmp_path)
        assert result.returncode == 0, result
        snap = observe_pdf(destination.with_suffix('.pdf'), env=observer)
        if marker == 'Literalmarker':
            line_containing(snap, marker)
            assert assert_token_style(snap, 'Literalmarker')['flags'] & 8
            assert '`' not in pdf_plain_text(snap)
        else:
            # A heading may also occur in navigation or page decorations.
            # Measure its actual characters rather than a numbering prefix.
            import unicodedata
            body_size = max(span['size'] for span in
                            line_containing(snap, 'Bodymarker')['spans'])
            heading_sizes = []
            for line in visible_lines(snap):
                chars = [(letter, span['size']) for span in line['spans']
                         for char in span['chars']
                         for letter in unicodedata.normalize('NFKC', char['c'])]
                text = ''.join(letter for letter, size in chars)
                start = text.find(marker)
                if start >= 0:
                    heading_sizes.append(min(size for letter, size in
                                             chars[start:start + len(marker)]))
            assert heading_sizes and max(heading_sizes) > body_size, heading_sizes
            assert '#' not in pdf_plain_text(snap)
        if ext == 'unknownextension':
            assert 'restructuredtext' in result.stdout.decode('utf-8').casefold(), result
    assert_cli_refusal(conversion_cli(str(source), '--format', 'unsupported-format', cwd=tmp_path), 'unsupported-format')


def test_template_configuration_and_cli_overrides(tmp_path, observer):
    source = write_text(tmp_path / 'document.rst', 'Titlemarker\n===========\n\n:author: Authormarker\n\nBodymarker\n')
    result = conversion_cli(str(source), cwd=tmp_path)
    assert result.returncode == 0, result
    default = observe_pdf(tmp_path / 'document.pdf', env=observer)
    article = converted_pdf(source, tmp_path / 'article', observer, '--template', 'article')
    for snap in (default, article):
        assert token_box(snap, 'Titlemarker')['page'] == token_box(snap, 'Bodymarker')['page']
        line_containing(snap, 'Authormarker')
    book = converted_pdf(source, tmp_path / 'book', observer, '--template', 'book')
    assert token_box(book, 'Titlemarker')['page'] < token_box(book, 'Bodymarker')['page']
    inherited = write_text(tmp_path / 'inherited.rts', '[STYLESHEET]\nname = inherited\nbase = sphinx_article\n\n[body]\nfont_size = 17pt\nfont_color = #ff0000\n')
    override = write_text(tmp_path / 'override.rts', '[STYLESHEET]\nname = override\nbase = sphinx_article\n\n[body]\nfont_size = 23pt\nfont_color = #0000ff\n')
    cfg = write_text(tmp_path / 'choices.rtt', '[TEMPLATE_CONFIGURATION]\nname = choices\ntemplate = article\nstylesheet = inherited.rts\n\n[VARIABLES]\npaper_size = A5\n')
    baseline = converted_pdf(source, tmp_path / 'configured', observer, '--template', str(cfg))
    assert_token_style(baseline, 'Bodymarker', size=17, color=0xff0000)
    assert baseline['pages'][0]['rect'][2:] == pytest.approx([148*72/25.4, 210*72/25.4], abs=.02)
    # Independent options as well as precedence over configuration.
    for label, options, size, color, paper in [
        ('style', ('--stylesheet', str(override)), 23, 0x0000ff, None),
        ('paper', ('--paper', 'letter'), None, None, [612,792]),
        ('both', ('--template', str(cfg), '--stylesheet', str(override), '--paper', 'letter'), 23, 0x0000ff, [612,792]),
        ('style-precedence', ('--template', str(cfg), '--stylesheet', str(override)), 23, 0x0000ff, None),
        ('paper-precedence', ('--template', str(cfg), '--paper', 'letter'), 17, 0xff0000, [612,792])]:
        directory = tmp_path / label
        directory.mkdir()
        result = conversion_cli(str(source), '--output', str(directory), *options, cwd=tmp_path)
        assert result.returncode == 0, result
        snap = observe_pdf(directory / 'document.pdf', env=observer)
        line_containing(snap, 'Bodymarker')
        if size is not None:
            assert_token_style(snap, 'Bodymarker', size=size, color=color)
        if paper is not None:
            assert all(page['rect'][2:] == pytest.approx(paper, abs=.02) for page in snap['pages'])


def test_invalid_requests_and_image_error_status(tmp_path, observer):
    source = write_text(tmp_path / 'good.rst', 'Workingmarker\n')
    line_containing(converted_pdf(source, tmp_path / 'good', observer), 'Workingmarker')
    for args, offending in [
        ((str(tmp_path / 'absent.rst'),), 'absent.rst'),
        ((str(source), '--stylesheet', 'absent.rts'), 'absent.rts'),
        ((str(source), '--template', 'absent-template'), 'absent-template'),
        ((str(source), '--paper', 'absent-paper'), 'absent-paper'),
        ((str(source), '--option', 'unsupported-option=true'), 'unsupported-option')]:
        assert_cli_refusal(conversion_cli(*args, cwd=tmp_path), offending)
    (tmp_path / 'reader').mkdir()
    names, env = install_resource_bundle(tmp_path / 'reader')
    extension_source = write_text(tmp_path / 'input.probe', 'Readerbody')
    valid = converted_pdf(extension_source, tmp_path / 'reader-valid', observer,
                          '--format', names['reader'], '--option', 'copies=3', env=env)
    assert pdf_plain_text(valid).count('Readerbody') == 3
    assert_cli_refusal(conversion_cli(str(extension_source), '--format', names['reader'],
                                     '--option', 'uppercase=not-a-boolean', cwd=tmp_path, env=env), 'uppercase')
    numeric = conversion_cli(str(extension_source), '--format', names['reader'],
                             '--option', 'copies=not-an-integer', cwd=tmp_path, env=env)
    assert numeric.returncode == 1, numeric
    assert numeric.stderr.strip(), numeric
    image_source = write_text(tmp_path / 'image.rst', 'Survivingmarker\n\n.. image:: absent-image.png\n')
    result = conversion_cli(str(image_source), '--output', str(tmp_path / 'image'), cwd=tmp_path)
    assert result.returncode == 1, result
    assert 'absent-image.png' in result.stderr.decode('utf-8'), result
    assert result.stderr.strip(), result
    line_containing(observe_pdf(tmp_path / 'image.pdf', env=observer), 'Survivingmarker')


def test_installed_font_specimen_uses_face_glyphs(tmp_path, observer):
    path = tmp_path / 'specimen'
    result = conversion_cli('--list-fonts', str(path), cwd=tmp_path)
    assert result.returncode == 0, result
    snapshot = observe_pdf(path.with_suffix('.pdf'), env=observer)
    catalogue = listed_faces(resource_cli('--list-fonts'))
    # Independent Adobe core-font catalogue. Check each Latin face's specimen
    # against MuPDF's independent outlines, not a name in a PDF font dictionary.
    # Rows are '<typeface> <width> <slant> <weight>'; the word naming a core
    # face's non-bold weight is not fixed, the bold face is named Bold.
    weight_words = ('thin', 'hairline', 'extra-light', 'ultra-light', 'light',
                    'regular', 'normal', 'book', 'roman', 'medium')
    core = {'Courier': [('Upright', False, 'Courier'), ('Upright', True, 'Courier-Bold'), ('Oblique', False, 'Courier-Oblique'), ('Oblique', True, 'Courier-BoldOblique')],
            'Helvetica': [('Upright', False, 'Helvetica'), ('Upright', True, 'Helvetica-Bold'), ('Oblique', False, 'Helvetica-Oblique'), ('Oblique', True, 'Helvetica-BoldOblique')],
            'Times': [('Upright', False, 'Times-Roman'), ('Upright', True, 'Times-Bold'), ('Italic', False, 'Times-Italic'), ('Italic', True, 'Times-BoldItalic')]}
    faces = []
    for family, variants in core.items():
        assert family.casefold() in catalogue
        for slant, bold, font in variants:
            prefix = (family + ' Normal ' + slant + ' ').casefold()
            row = [line for line in visible_lines(snapshot)
                   if line['text'].strip().casefold().startswith(prefix)
                   and ((line['text'].strip().casefold()[len(prefix):] == 'bold') if bold
                        else line['text'].strip().casefold()[len(prefix):] in weight_words)]
            assert len(row) == 1, (family, slant, bold, [line['text'] for line in visible_lines(snapshot)])
            faces.append(dict(page=row[0]['page'], bbox=row[0]['bbox'], spans=row[0]['spans'], font=font))
    font_environment = font_observer_environment(tmp_path / 'fontobserver')
    for item in installed_specimen_faces(font_environment):
        label = ''.join(item['label'].split()).casefold()
        rows = [line for line in visible_lines(snapshot)
                if ''.join(line['text'].split()).casefold() == label]
        assert len(rows) == 1, item
        faces.append(dict(page=rows[0]['page'], bbox=rows[0]['bbox'],
                          spans=rows[0]['spans'], font_file=item['font_file']))
    assert_specimen_outlines(path.with_suffix('.pdf'), faces, font_environment)


def _pip_environment(workspace, env, index_url='https://pypi.org/simple'):
    """Private pip target and index for one conversion; nothing else installed."""
    target = workspace.root / 'installed'
    target.mkdir()
    env = dict(env)
    env['PYTHONPATH'] = str(target) + os.pathsep + env.get('PYTHONPATH', '')
    env.pop('PIP_NO_INDEX', None)
    env.pop('PIP_FIND_LINKS', None)
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX='0',
               PIP_TARGET=str(target), PIP_INDEX_URL=index_url,
               PIP_NO_CACHE_DIR='1', PIP_NO_DEPS='1', PIP_RETRIES='0',
               PIP_DEFAULT_TIMEOUT='20', PIP_DISABLE_PIP_VERSION_CHECK='1')
    return target, env


def _typeface_sheet(workspace, family):
    # Resolve the requested family during rendering, where resource
    # acquisition is supported, rather than while parsing the stylesheet.
    return write_text(workspace.work / 'required.rts',
        '[STYLESHEET]\nname = required typeface\nbase = sphinx_article\n'
        '\n[VARIABLES]\nserif_typeface = ' + family +
        '\n\n[body]\nfont_size = 24pt\n')


def test_acquire_missing_pypi_typeface_and_render(tmp_path, observer):
    # The real upstream distribution is obtained from the package index during
    # the conversion; the judge has no network, so the index is the loopback
    # mirror, which publishes the unmodified wheel and nothing else.
    family = 'TeX Gyre Termes'
    index_url = 'https://pypi.org/caller-selected/simple'
    with isolated_workspace(parent=tmp_path) as workspace, \
            resource_services(workspace.env, index_url) as services:
        target, env = _pip_environment(workspace, services.env, index_url)
        inventory = installed_distributions(sys.executable, env=env)
        registered = {entry['name'].replace(' ', '').casefold()
                      for distribution in inventory
                      for entry in distribution['entry_points']
                      if entry['group'] == 'rinoh.typefaces'}
        assert family.replace(' ', '').casefold() not in registered, (
            'The acquisition requires a genuinely uninstalled typeface', inventory)
        marker = 'Acquisitionmarker' + uuid.uuid4().hex[:8]
        source = write_text(workspace.work / 'input.rst', marker + '\n')
        sheet = _typeface_sheet(workspace, family)
        destination = workspace.output / 'acquired'
        snapshot = converted_pdf(source, destination, observer,
            '--stylesheet', str(sheet), '--install-resources', env=env)
        line = line_containing(snapshot, marker)
        # The default index is absent from this service. Successful installation
        # and the real glyphs prove that the caller-selected index was effective.
        assert any(path.name.endswith('.dist-info') for path in target.iterdir())
        # Independent upstream font asset already supplied by F04; no product
        # font name or installation log serves as evidence of the glyphs.
        assert_specimen_outlines(destination.with_suffix('.pdf'), [dict(
            page=line['page'], bbox=line['bbox'], spans=line['spans'],
            font_file=str(ASSETS / FONT_FILES['otf']))], observer)


def test_missing_resource_rejected_with_and_without_permission(tmp_path, observer):
    source = write_text(tmp_path / 'input.rst', 'Resourcebody\n')
    line_containing(converted_pdf(source, tmp_path / 'available', observer), 'Resourcebody')
    missing = 'unavailable' + uuid.uuid4().hex
    # An absent family fails with and without permission; a family that the
    # index does publish is still refused, and not installed, without it.
    for family, permission in ((missing, ()), (missing, ('--install-resources',)),
                               ('TeX Gyre Termes', ())):
        with isolated_workspace(parent=tmp_path) as workspace, \
                resource_services(workspace.env) as services:
            target, env = _pip_environment(workspace, services.env)
            sheet = _typeface_sheet(workspace, family)
            result = conversion_cli(str(source), '--stylesheet', str(sheet),
                                     '--output', str(workspace.output / 'result'),
                                     *permission, cwd=workspace.work, env=env)
            assert_cli_refusal(result, family)
            if not permission:
                assert not any(url.startswith('https://files.pythonhosted.org/')
                               for url in services.requests), services.requests
                assert not list(target.iterdir())
