# feature: F19
"""Real Sphinx projects and independent PDF observations."""
import os
import sys
from _helpers import run_sphinx, write_text, observe_pdf


def sphinx_project(path, documents, settings='', files=None, extra=''):
    path.mkdir(parents=True)
    configuration = """extensions = ['talvo.frontend.sphinx', 'sphinx.ext.graphviz']
master_doc = 'index'
project = 'Orchardproject'
author = 'Projectwriter'
release = '7.4'
exclude_patterns = ['out']
latex_documents = []
today = 'Projectdate'
"""
    write_text(path / 'conf.py', configuration + extra + '\n' + settings)
    for name, body in (files or {'index': 'Root\n====\n\nRootbodymarker\n'}).items():
        write_text(path / (name + '.rst'), body)
    if documents is not None:
        with (path / 'conf.py').open('a') as stream:
            stream.write('\ntalvo_documents = ' + repr(documents) + '\n')
    return path


def build_sphinx(path):
    environment = dict(os.environ)
    return run_sphinx((sys.executable, '-m', 'sphinx'), path, path / 'out',
                      builder='talvo', args=('-E', '-a', '--no-color'),
                      cwd=path, env=environment, timeout=180)


def sphinx_pdfs(path, result, observer):
    assert result.returncode == 0, (result.stdout, result.stderr)
    return {p.stem: observe_pdf(p, env=observer) for p in (path / 'out').glob('*.pdf')}


def assembled_files():
    return {'index': 'Firstroot\n=========\n\nRootbodymarker\n\n.. toctree::\n\n   child\n',
            'child': 'Childheading\n============\n\nChildbodymarker\n',
            'other': 'Otherroot\n=========\n\nOtherbodymarker\n'}


def ubuntu_packages(root):
    """Unpack the official Ubuntu packages in assets/F19_debs under *root*.

    The packages are the ones Graphviz and Tesseract need beyond the case
    image. Absolute symbolic links are pointed into *root* so the unpacked
    tree never resolves into the host system.
    """
    import subprocess
    from pathlib import Path
    root.mkdir(parents=True)
    for package in sorted((Path(__file__).with_name('assets') / 'F19_debs').glob('*.deb')):
        subprocess.run(('dpkg-deb', '-x', str(package), str(root)), check=True)
    for link in [item for item in root.rglob('*') if item.is_symlink()]:
        target = os.readlink(link)
        if target.startswith('/'):
            link.unlink()
            link.symlink_to(os.path.relpath(root / target.lstrip('/'), link.parent))
    return root


def graphviz_environment(path):
    """Unpack the real Ubuntu Graphviz distribution for offline graph rendering."""
    import subprocess
    root = ubuntu_packages(path / 'graphviz')
    libraries = root / 'usr' / 'lib' / 'x86_64-linux-gnu'
    dot = root / 'usr' / 'bin' / 'dot'
    environment = dict(os.environ, LD_LIBRARY_PATH=str(libraries),
                       GVBINDIR=str(libraries / 'graphviz'))
    # Register the plugins, as the package's post-installation step does.
    subprocess.run((str(dot), '-c'), env=environment, check=True)
    wrapper = root / 'render-dot'
    write_text(wrapper, '#!/bin/sh\nexport LD_LIBRARY_PATH="' + str(libraries) + '"\nexport GVBINDIR="' + str(libraries / 'graphviz') + '"\nexec "' + str(dot) + '" "$@"\n')
    wrapper.chmod(0o755)
    return wrapper


def diagram_words(destination, snapshot, environment, tools, tokens):
    """Read visible diagram labels using independent offline Tesseract OCR."""
    import csv
    import io
    from _helpers import run_command
    from F10_helpers import page_pixels
    root = ubuntu_packages(tools / 'ocr')
    binary = root / 'usr' / 'bin' / 'tesseract'
    child = dict(environment)
    child['LD_LIBRARY_PATH'] = str(root / 'usr' / 'lib' / 'x86_64-linux-gnu')
    child['TESSDATA_PREFIX'] = str(root / 'usr' / 'share' / 'tesseract-ocr' / '5' / 'tessdata')
    found = {}
    observed = []
    for page in range(len(snapshot['pages'])):
        pixels = page_pixels(destination, environment, page=page)
        image = destination.with_name('ocr-page.png')
        from PIL import ImageChops, ImageOps, Image
        from itertools import groupby
        pixels = pixels.resize((pixels.width*2, pixels.height*2))
        red, green, blue = pixels.split()
        ink = ImageChops.lighter(ImageChops.lighter(red, green), blue).point(
            lambda value: 255 if value < 160 else 0)
        # Remove long straight ruling strokes before OCR; their geometry is
        # still measured on the unmodified rendered page below.
        def erase_rules(mask):
            data = bytearray(mask.tobytes())
            for y in range(mask.height):
                start = y*mask.width
                offset = 0
                for value, group in groupby(data[start:start+mask.width]):
                    count = sum(1 for _ in group)
                    if value and count > 80:
                        data[start+offset:start+offset+count] = bytes(count)
                    offset += count
            return Image.frombytes('L', mask.size, bytes(data))
        ink = erase_rules(ink)
        ink = erase_rules(ink.transpose(Image.Transpose.TRANSPOSE)).transpose(Image.Transpose.TRANSPOSE)
        ImageOps.invert(ink).save(image)
        result = run_command((str(binary), str(image), 'stdout', '-l', 'eng',
                              '--psm', '11', '-c', 'tessedit_create_tsv=1'),
                             env=child, timeout=60)
        assert result.returncode == 0, result
        rows = csv.DictReader(io.StringIO(result.stdout.decode()), delimiter='\t')
        for row in rows:
            word = row['text']
            if word.strip():
                observed.append((page, word))
            if word in tokens:
                assert word not in found, (word, found)
                x, y, width, height = [int(row[key])/4 for key in ('left', 'top', 'width', 'height')]
                found[word] = dict(page=page, x0=x, x1=x+width, y0=y, y1=y+height, y=y+height/2)
    assert set(found) == set(tokens), (found, observed)
    return found
