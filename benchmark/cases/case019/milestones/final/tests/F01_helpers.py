# feature: F01
"""Feature-specific document construction through public entries."""


def render_fraction_widths(destination, containing_width, fractions):
    from PIL import Image as RasterImage
    from talvo.dimension import PT
    from talvo.document import DocumentTree
    from talvo.flowable import FlowableStyle
    from talvo.image import Image
    from talvo.paper import Paper
    from talvo.templates import Article

    asset = destination.with_suffix('.source.png')
    RasterImage.new('RGB', (20, 2), (255, 0, 0)).save(asset)
    content = [Image(str(asset), width=fraction,
                     style=FlowableStyle(space_below=8*PT))
               for fraction in fractions]
    configuration = Article.Configuration('relative widths')
    configuration('contents_page',
                  page_size=Paper('custom', (containing_width+80)*PT, 600*PT),
                  left_margin=40*PT, right_margin=40*PT)
    return Article(DocumentTree(content), configuration=configuration).render(
        str(destination))


def red_band_widths(image_path, *, pixels_per_point):
    """Measure separate red bands from an independent raster, in points.

    Antialiasing is tolerated at edges; image-reading failures propagate.
    """
    from PIL import Image

    with Image.open(image_path) as image:
        rgb = image.convert('RGB')
        pixels = rgb.load()
        widths = []
        band_width = None
        for y in range(rgb.height):
            red_x = [x for x in range(rgb.width)
                     if pixels[x, y][0] > 200
                     and pixels[x, y][1] < 40 and pixels[x, y][2] < 40]
            if red_x:
                width = (red_x[-1] - red_x[0] + 1) / pixels_per_point
                band_width = width if band_width is None else max(band_width, width)
            elif band_width is not None:
                widths.append(band_width)
                band_width = None
        if band_width is not None:
            widths.append(band_width)
        return widths


def pdf_observer_environment(directory):
    """Unpack the bundled independent observer for an offline child process.

    The wheel includes its upstream license. Extraction or import failures are
    errors; this never substitutes product output or changes the parent process.
    """
    import os
    from pathlib import Path
    from zipfile import ZipFile

    directory.mkdir()
    with ZipFile(Path(__file__).with_name('assets') / 'F01_pymupdf.whl') as wheel:
        wheel.extractall(directory)
    environment = os.environ.copy()
    existing = environment.get('PYTHONPATH')
    environment['PYTHONPATH'] = str(directory)
    if existing:
        environment['PYTHONPATH'] += os.pathsep + existing
    return environment
