# feature: F04
"""Real font inputs, styled rendering, and independent glyph observations."""

import json
from pathlib import Path
from zipfile import ZipFile

from _helpers import observe_pdf, run_python
from F01_helpers import pdf_observer_environment

ASSETS = Path(__file__).with_name('assets')
FONT_FILES = {'otf': 'F04_termes.otf', 'ttf': 'F04_serif.ttf',
              'bold': 'F04_serif_bold.ttf', 'italic': 'F04_serif_italic.ttf',
              'condensed': 'F04_serif_condensed.ttf', 'google': 'F04_Abel-Regular.ttf'}


def font_observer_environment(directory):
    environment = pdf_observer_environment(directory)
    with ZipFile(ASSETS / 'F04_fonttools.whl') as archive:
        archive.extractall(directory)
    return environment


def supplied_typeface(kind):
    from talvo.font import Typeface
    from talvo.font.opentype import OpenTypeFont
    from talvo.font.type1 import Type1Font
    if kind == 'embedded-type1':
        font = Type1Font(str(ASSETS / 'F04_FreeEuro'), weight=400,
                         unicode_mapping={0x20ac: ['Euro.serif'], 0x20: ['Euro.serif']})
    elif kind == 'type1':
        font = Type1Font(str(ASSETS / 'F04_Times-Roman'), core=True, weight=400)
    else:
        font = OpenTypeFont(str(ASSETS / FONT_FILES[kind]))
    return Typeface('Caller supplied ' + kind, font)


def render_font_text(destination, text, typeface, **choices):
    from talvo.dimension import PT
    from talvo.document import DocumentTree
    from talvo.paragraph import Paragraph, ParagraphStyle
    from talvo.templates import Article
    from talvo.template import ContentsPartTemplate
    from talvo.paper import Paper

    class FontArticle(Article):
        contents = ContentsPartTemplate(page_number_format='number')

    configuration = FontArticle.Configuration('font observation')
    configuration('contents_page', page_size=Paper('font page', 500*PT, 560*PT),
                  left_margin=40*PT, right_margin=40*PT,
                  top_margin=40*PT, bottom_margin=40*PT)
    # A single uniform paragraph exercises binding, not isolated glyph helpers.
    choices = {'font_weight': 400} | choices
    style = ParagraphStyle(typeface=typeface, font_size=24*PT,
                           hyphenate=False, **choices)
    return FontArticle(DocumentTree([Paragraph(text, style=style)]),
                   configuration=configuration).render(str(destination))


def body_glyphs(destination, environment):
    snapshot = observe_pdf(destination.with_suffix('.pdf'), env=environment)
    assert len(snapshot['pages']) == 1
    spans = [span for span in snapshot['pages'][0]['glyphs']
             if span['bbox'][1] < 250]
    assert spans, snapshot
    assert all(abs(span['size'] - 24) < 0.001 for span in spans), spans
    return [char for span in spans for char in span['chars']]


# FontTools interprets the supplied font tables; MuPDF draws the expected
# outlines independently of the product. No product font queries supply oracles.
_FONT_ORACLE = r'''
import io, json, sys
from fontTools.ttLib import TTFont
p = json.loads(sys.argv[1])
f = TTFont(p['font'])
cmap = f.getBestCmap()
names = [cmap[ord(c)] for c in p['text']]
if p.get('feature'):
    records = f['GSUB'].table.FeatureList.FeatureRecord
    indices = set(i for r in records if r.FeatureTag == p['feature']
                  for i in r.Feature.LookupListIndex)
    for index in sorted(indices):
        lookup = f['GSUB'].table.LookupList.Lookup[index]
        for table in lookup.SubTable:
            if hasattr(table, 'mapping'):
                names = [table.mapping.get(n, n) for n in names]
            elif hasattr(table, 'ligatures'):
                result = []
                i = 0
                while i < len(names):
                    matches = [lig for lig in table.ligatures.get(names[i], [])
                               if names[i+1:i+lig.CompCount] == lig.Component]
                    if matches:
                        lig = max(matches, key=lambda item: item.CompCount)
                        result.append(lig.LigGlyph)
                        i += lig.CompCount
                    else:
                        result.append(names[i]); i += 1
                names = result
units = f['head'].unitsPerEm
advances = [f['hmtx'][n][0] * 24 / units for n in names]
print(json.dumps({'names': names, 'advances': advances}))
'''


def font_expectation(text, environment, kind='otf', feature=None):
    font = ASSETS / FONT_FILES[kind]
    result = run_python(_FONT_ORACLE, args=(json.dumps(
        dict(font=str(font), text=text, feature=feature)),), env=environment)
    assert result.returncode == 0, result
    return json.loads(result.stdout)


_RASTER_ORACLE = r'''
import io, json, sys
import fitz
from PIL import Image, ImageChops, ImageFilter
from fontTools.ttLib import TTFont
p = json.loads(sys.argv[1])
with fitz.open(p['pdf']) as actual:
    page = actual[0]
    oracle = fitz.open()
    expected = oracle.new_page(width=page.rect.width, height=page.rect.height)
    if p.get('type1'):
        from fontTools import t1Lib
        from fontTools.fontBuilder import FontBuilder
        from fontTools.pens.ttGlyphPen import TTGlyphPen
        from fontTools.pens.cu2quPen import Cu2QuPen
        source = t1Lib.T1Font(p['type1'])
        glyphs = source.getGlyphSet()
        names = ['.notdef', 'Euro.serif']
        converted, metrics = {}, {}
        for name in names:
            pen = TTGlyphPen(None)
            glyphs[name].draw(Cu2QuPen(pen, 0.1, reverse_direction=True))
            converted[name] = pen.glyph()
            converted[name].recalcBounds(None)
            metrics[name] = (round(glyphs[name].width), converted[name].xMin)
        builder = FontBuilder(1000, isTTF=True)
        builder.setupGlyphOrder(names)
        builder.setupCharacterMap({0x20ac: 'Euro.serif'})
        builder.setupGlyf(converted)
        builder.setupHorizontalMetrics(metrics)
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupNameTable({'familyName': 'Independent FreeEuro',
                                'styleName': 'Regular'})
        builder.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                         usWinAscent=800, usWinDescent=200)
        builder.setupPost()
        buffer = io.BytesIO(); builder.save(buffer)
        font = fitz.Font(fontbuffer=buffer.getvalue())
        text = p['text']
    elif p.get('core'):
        font = fitz.Font(p['core'])
        text = p['text']
    else:
        f = TTFont(p['font'])
        mapping = {0xe000+i: name for i, name in enumerate(p['names'])}
        for table in f['cmap'].tables:
            if table.isUnicode():
                table.cmap = mapping.copy()
        buffer = io.BytesIO(); f.save(buffer)
        font = fitz.Font(fontbuffer=buffer.getvalue())
        text = ''.join(chr(0xe000+i) for i in range(len(p['names'])))
    writer = fitz.TextWriter(expected.rect)
    assert len(text) == len(p['origins']), (text, p['origins'])
    for char, origin in zip(text, p['origins']):
        writer.append(origin, char, font=font, fontsize=24)
    writer.write_text(expected)
    # Exclude the running footer, retaining the entire content region so extra
    # unwanted marks are not hidden by a tight expected-glyph crop.
    clip = fitz.Rect(0, 0, page.rect.width, 250)
    def mask(page):
        pix = page.get_pixmap(matrix=fitz.Matrix(3,3), clip=clip,
                             colorspace=fitz.csGRAY, alpha=False)
        return Image.frombytes('L', (pix.width,pix.height), pix.samples).point(
            lambda v: 255 if v < 160 else 0)
    a, b = mask(page), mask(expected)
    def total(image):
        return sum(image.histogram()[1:])
    ink_a, ink_b = total(a), total(b)
    assert ink_a > 0 and ink_b > 0
    # One raster pixel of edge tolerance at 216 dpi admits antialiasing and
    # equivalent curve representations, but not a different glyph silhouette.
    missed_a = total(ImageChops.subtract(a, b.filter(ImageFilter.MaxFilter(3))))
    missed_b = total(ImageChops.subtract(b, a.filter(ImageFilter.MaxFilter(3))))
    print(json.dumps([missed_a/ink_a, missed_b/ink_b]))
'''


def assert_glyph_outlines(destination, glyphs, environment, *, names=None,
                          kind='otf', core=None, text=None, type1=None):
    payload = dict(pdf=str(destination.with_suffix('.pdf')),
                   origins=[g[2] for g in glyphs], names=names, core=core,
                   text=text, type1=type1, font=str(ASSETS / FONT_FILES[kind]))
    result = run_python(_RASTER_ORACLE, args=(json.dumps(payload),),
                        env=environment)
    assert result.returncode == 0, result
    errors = json.loads(result.stdout)
    assert max(errors) < 0.02, errors


def google_font_services(env):
    """Serve the captured upstream manifest and its unmodified static face."""
    from _helpers import loopback_https_mirror
    manifest = (ASSETS / 'F04_Abel_manifest.json').read_bytes()
    family = json.loads(manifest[5:])
    faces = {entry['url']: (ASSETS / ('F04_' + entry['filename'])).read_bytes()
             for entry in family['manifest']['fileRefs']}

    def answer(url):
        if url == 'https://fonts.google.com/download/list?family=Abel':
            return 200, manifest, 'application/json; charset=utf-8'
        if url in faces:
            return 200, faces[url], 'font/ttf'
        return None
    return loopback_https_mirror(answer, env=env)
