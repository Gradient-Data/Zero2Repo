# feature: F10
"""Image fixtures and independent rendered-page measurements."""
import json
from PIL import Image as Raster, ImageCms
from talvo.dimension import PT
from talvo.flowable import Flowable
from F08_helpers import render_flow
from _helpers import call_public, observe_pdf, rasterize_pdf_page, run_python


def image_asset(path, *, dpi=None, alpha=False, profile=False):
    image = Raster.new('RGBA' if alpha else 'RGB', (80, 40),
                       (255, 0, 0, 128) if alpha else (255, 0, 0))
    # Asymmetric real artwork makes rotation, placeholders and mirroring visible.
    for x in range(40, 80):
        for y in range(40):
            image.putpixel((x, y), (0, 0, 255, 255) if alpha else (0, 0, 255))
    options = {}
    if dpi:
        options['dpi'] = (dpi, dpi)
    if profile:
        options['icc_profile'] = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    if path.suffix == '.jpg':
        options.update(quality=98, subsampling=0)
    image.save(path, **options)
    return options.get('icc_profile')


def image_document(destination, elements, *, page=None):
    options = dict(left_margin=30*PT, right_margin=30*PT,
                   top_margin=30*PT, bottom_margin=30*PT)
    options.update(page or {})
    from talvo.paper import Paper
    options['page_size'] = Paper('image paper', 360*PT, 240*PT)
    return call_public(render_flow, destination, elements, {'page': options}, {}, ['contents'], ())


def image_snapshot(destination, elements, environment, *, page=None):
    result = image_document(destination, elements, page=page)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout, result.stderr, result.warnings)
    return observe_pdf(destination.with_suffix('.pdf'), env=environment)


def page_pixels(destination, environment, page=0):
    path = destination.with_name(destination.name + f'-page{page}.png')
    rasterize_pdf_page(destination.with_suffix('.pdf'), path, page=page,
                       dpi=144, alpha=False, env=environment)
    with Raster.open(path) as image:
        return image.convert('RGB')


def color_extent(image, color):
    points = [(x/2, y/2) for y in range(image.height) for x in range(image.width)
              if max(abs(a-b) for a,b in zip(image.getpixel((x,y)), color)) < 18]
    assert points, f'No visible pixels for {color}'
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs)+.5, max(ys)+.5


def artwork_extent(image):
    red = color_extent(image, (255,0,0))
    blue = color_extent(image, (0,0,255))
    return (min(red[0],blue[0]), min(red[1],blue[1]),
            max(red[2],blue[2]), max(red[3],blue[3]))


def pdf_artwork(path, environment):
    source = '''import fitz, sys
with fitz.open() as doc:
    page=doc.new_page(width=80,height=40)
    page.draw_rect(fitz.Rect(0,0,40,40),color=None,fill=(1,0,0))
    page.draw_rect(fitz.Rect(40,0,80,40),color=None,fill=(0,0,1))
    page.clean_contents()
    doc.save(sys.argv[1])
'''
    result = run_python(source, args=(str(path),), env=environment)
    assert result.returncode == 0, result.stderr


def embedded_profiles(path, environment):
    source = '''import fitz, json, sys
with fitz.open(sys.argv[1]) as doc:
    print(json.dumps([doc.xref_stream(i).hex() for i in range(1,doc.xref_length())
                      if doc.xref_is_stream(i)]))
'''
    result = run_python(source, args=(str(path),), env=environment)
    assert result.returncode == 0, result.stderr
    return [bytes.fromhex(value) for value in json.loads(result.stdout)]


class DrawingContent(Flowable):
    """Caller extension that places public drawing objects in document space."""
    def __init__(self, shapes):
        super().__init__()
        self.shapes = shapes

    def render(self, container, last_descender, state, **kwargs):
        for shape in self.shapes:
            shape.render(container)
        container.advance(120*PT)
        return 180*PT, 120*PT, 0
