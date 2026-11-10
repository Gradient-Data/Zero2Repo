# feature: F18
"""CLI outcomes and independent specimen observations."""
import os
import sys
import json
import hashlib
from pathlib import Path

from _helpers import run_cli, run_python, observe_pdf, loopback_https_mirror


def conversion_cli(*args, cwd, env=None):
    child = dict(os.environ if env is None else env)
    return run_cli((sys.executable, '-m', 'talvo'), args, cwd=cwd,
                   env=child, timeout=120)


def converted_pdf(source, destination, environment, *options, cwd=None, env=None):
    result = conversion_cli(str(source), '--output', str(destination), *options,
                            cwd=cwd or source.parent, env=env)
    assert result.returncode == 0, result
    return observe_pdf(destination.with_suffix('.pdf'), env=environment)


def assert_cli_refusal(result, offending):
    assert result.returncode == 1, result
    assert offending.casefold() in result.stderr.decode('utf-8').casefold(), result


_SPECIMEN_ORACLE = r'''
import json, sys
import fitz
from PIL import Image, ImageChops, ImageFilter
p = json.load(sys.stdin)
with fitz.open(p['pdf']) as doc:
    errors = []
    for item in p['faces']:
        page = doc[item['page']]
        # Render only the selected specimen row. The expected font is from the
        # independent Adobe base-14 catalogue, not the PDF's font declaration.
        expected_doc = fitz.open()
        expected = expected_doc.new_page(width=page.rect.width, height=page.rect.height)
        writer = fitz.TextWriter(expected.rect)
        font = (fitz.Font(fontfile=item['font_file']) if 'font_file' in item
                else fitz.Font(item['font']))
        for span in item['spans']:
            for char in span['chars']:
                writer.append(char['origin'], char['c'], font=font, fontsize=span['size'])
        writer.write_text(expected)
        # Restrict to the interior of the text row so adjacent rules and
        # neighbouring rows cannot contribute ink to this face's observation.
        clip = fitz.Rect(item['bbox']) + (0,1,0,-1)
        def mask(pg):
            pix = pg.get_pixmap(matrix=fitz.Matrix(6,6), clip=clip,
                               colorspace=fitz.csGRAY, alpha=False)
            return Image.frombytes('L', (pix.width,pix.height), pix.samples).point(
                lambda v: 255 if v < 160 else 0)
        a,b = mask(page),mask(expected)
        def ink(im): return sum(im.histogram()[1:])
        assert ink(a) > 0 and ink(b) > 0
        errors.append([ink(ImageChops.subtract(a,b.filter(ImageFilter.MaxFilter(3))))/ink(a),
                       ink(ImageChops.subtract(b,a.filter(ImageFilter.MaxFilter(3))))/ink(b)])
    print(json.dumps(errors))
'''


def assert_specimen_outlines(path, faces, environment):
    result = run_python(_SPECIMEN_ORACLE,
                        input=json.dumps(dict(pdf=str(path), faces=faces)).encode('utf-8'),
                        env=environment, timeout=120)
    assert result.returncode == 0, result
    errors = json.loads(result.stdout)
    # One raster pixel of outline tolerance at 432 dpi; no page design pinned.
    assert errors and max(max(pair) for pair in errors) < .02, errors


_INSTALLED_SPECIMEN_FACES = r'''
import importlib.metadata as metadata
import json
from fontTools.ttLib import TTFont
widths = ('Ultra-Condensed','Extra-Condensed','Condensed','Semi-Condensed',
          'Normal','Semi-Expanded','Expanded','Extra-Expanded','Ultra-Expanded')
weights = {100:'Thin',200:'Extra-Light',300:'Light',400:'Regular',500:'Medium',
           600:'Semi-Bold',700:'Bold',800:'Extra-Bold',900:'Heavy'}
faces = []
for dist in metadata.distributions():
    entries = [ep for ep in dist.entry_points if ep.group == 'rinoh.typefaces']
    if not entries or dist.metadata['Name'] == 'talvotype':
        continue
    assert len(entries) == 1, dist.metadata['Name']
    files = [p for p in dist.files if p.suffix.lower() in ('.ttf','.otf')]
    assert files, dist.metadata['Name']
    for path in files:
        filename = str(dist.locate_file(path))
        with TTFont(filename) as font:
            table = font['OS/2']
            label = ' '.join((entries[0].name, widths[table.usWidthClass-1],
                              'Italic' if table.fsSelection & 1 else 'Upright',
                              weights[table.usWeightClass]))
        faces.append(dict(label=label, font_file=filename))
print(json.dumps(faces))
'''


def installed_specimen_faces(environment):
    result = run_python(_INSTALLED_SPECIMEN_FACES, env=environment)
    assert result.returncode == 0, result
    faces = json.loads(result.stdout)
    assert faces, 'The image must provide installed font distributions'
    return faces


TERMES_WHEEL = (Path(__file__).with_name('assets')
                / 'F18_rinoh_typeface_texgyretermes-0.1.1-py3-none-any.whl')
_WHEEL_URL = ('https://files.pythonhosted.org/packages/b9/15/82225ab8b159aba51073'
              'b61ee35955aac8e3b340ff7c6612be8f356e3a27/' + TERMES_WHEEL.name[4:])


def typeface_distribution(family):
    """Index project name of a typeface family, in the naming form of the typeface
    distributions installed in the environment (rinoh-typeface-<id>): <id> is the
    family name lowercased with every character other than ASCII letters and
    digits removed."""
    identifier = ''.join(c for c in family.lower() if c.isascii() and c.isalnum())
    return 'rinoh-typeface-<id>'.replace('<id>', identifier)


def resource_services(env, index_url='https://pypi.org/simple'):
    """Loopback mirror of PyPI and Google Fonts for an offline judge.

    PyPI publishes exactly one typeface project, the unmodified upstream wheel
    (simple index and JSON API); every other project is absent (404). Google
    Fonts hosts answer 400, the real answer for a family they do not provide.
    """
    wheel = TERMES_WHEEL.read_bytes()
    digest = hashlib.sha256(wheel).hexdigest()
    project = typeface_distribution('TeX Gyre Termes')
    assert project == 'rinoh-typeface-texgyretermes', project
    index = ('<!DOCTYPE html><html><body><a href="{}#sha256={}">{}</a></body></html>'
             .format(_WHEEL_URL, digest, TERMES_WHEEL.name[4:])).encode('ascii')
    api = json.dumps({'info': {'name': project, 'version': '0.1.1'},
                      'urls': [{'filename': TERMES_WHEEL.name[4:], 'url': _WHEEL_URL,
                                'packagetype': 'bdist_wheel',
                                'digests': {'sha256': digest}}]}).encode('ascii')

    def answer(url):
        path = url.split('?', 1)[0].rstrip('/')
        if path in (index_url.rstrip('/') + '/' + project,
                    index_url.rstrip('/') + '/' + project.replace('-', '_')):
            return 200, index, 'text/html'
        if index_url == 'https://pypi.org/simple' and path == 'https://pypi.org/pypi/' + project + '/json':
            return 200, api, 'application/json'
        if path == _WHEEL_URL:
            return 200, wheel, 'application/octet-stream'
        host = url.split('/')[2]
        if host.endswith(('google.com', 'googleapis.com', 'gstatic.com')):
            return 400, b'', 'text/plain'
        return None
    return loopback_https_mirror(answer, env=env)
