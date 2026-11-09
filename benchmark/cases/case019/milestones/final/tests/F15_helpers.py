# feature: F15
"""Representation-independent raster observations of isolated mathematics."""
from collections import deque
from F10_helpers import page_pixels


def math_ink(destination, environment, bounds=None, exclude=()):
    """Return connected ink bounds in page points, independent of PDF operators."""
    image = page_pixels(destination, environment)
    if bounds is None:
        bounds = (0, 0, image.width/2, image.height/2)
    x0, y0, x1, y1 = [int(2*v) for v in bounds]
    pixels = image.load()
    ink = {(x, y) for y in range(max(0,y0),min(image.height,y1))
           for x in range(max(0,x0),min(image.width,x1))
           if max(pixels[x,y])-min(pixels[x,y]) < 50 and min(pixels[x,y]) < 180
           and not any(a <= x/2 <= c and b <= y/2 <= d for a,b,c,d in exclude)}
    components = []
    while ink:
        start = ink.pop()
        queue = deque([start])
        points = [start]
        while queue:
            x,y = queue.popleft()
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    neighbor = (x+dx,y+dy)
                    if neighbor in ink:
                        ink.remove(neighbor)
                        queue.append(neighbor)
                        points.append(neighbor)
        if len(points) >= 3:
            xs,ys = zip(*points)
            components.append((min(xs)/2,min(ys)/2,(max(xs)+1)/2,(max(ys)+1)/2))
    return sorted(components, key=lambda b: (b[0],b[1]))


def ink_union(boxes):
    assert boxes, 'No equation artwork was visible'
    return (min(b[0] for b in boxes),min(b[1] for b in boxes),
            max(b[2] for b in boxes),max(b[3] for b in boxes))


def render_math_document(destination, elements, size=30, color=None):
    from talvo.color import BLACK
    from talvo.dimension import PT
    from talvo.document import DocumentTree
    from talvo.math import Equation, EquationLabel
    from talvo.paragraph import Paragraph
    from talvo.paper import Paper
    from talvo.text import SingleStyledText
    from F05_helpers import caller_sheet
    from F08_helpers import FlowDocument
    sheet = caller_sheet([
        ('body', Paragraph, dict(font_size=10*PT, space_above=0*PT,
                                space_below=10*PT)),
        ('equation', Equation, dict(font_size=size*PT, font_color=color or BLACK)),
        ('label', EquationLabel, dict(number_format='number',
            label_prefix=SingleStyledText('Label|'), label_suffix=SingleStyledText('|End')))])
    cfg = FlowDocument.Configuration('mathematics', stylesheet=sheet)
    cfg('page', page_size=Paper('math paper',600*PT,400*PT))
    return FlowDocument(DocumentTree(elements), configuration=cfg).render(str(destination))


def math_snapshot(destination, elements, environment, **settings):
    from _helpers import call_public, observe_pdf
    result = call_public(render_math_document, destination, elements, kwargs=settings)
    assert result.exception is None, result.traceback
    assert result.value is True, (result.stdout,result.stderr,result.warnings)
    return observe_pdf(destination.with_suffix('.pdf'),env=environment)


def equation_label_box(snapshot, number):
    """Read a standalone equation-number line, excluding reference text lines."""
    from F07_helpers import visible_lines
    matches = []
    for line in visible_lines(snapshot):
        chars = [c for span in line['spans'] for c in span['chars']]
        if ''.join(c['c'] for c in chars).strip() == 'Label|' + str(number) + '|End':
            selected = [c for c in chars if not c['c'].isspace()]
            matches.append(dict(page=line['page'],
                x0=min(c['bbox'][0] for c in selected),
                x1=max(c['bbox'][2] for c in selected),
                y=selected[0]['origin'][1], bbox=line['bbox']))
    assert len(matches) == 1, (number,matches)
    return matches[0]


def base_installation_math_render(directory, destination):
    """Install the public base package without extras in a clean offline venv."""
    import json
    from pathlib import Path
    from _helpers import (create_python_environment, install_distributions,
                          run_python)
    environment = create_python_environment(directory)
    install_distributions(environment, ['/app', 'pillow'],
        args=('--no-index', '--find-links=/opt/wheels'), timeout=180)
    # The helper path supplies caller document construction only; product imports
    # resolve solely through the freshly installed distribution, never /app/src.
    source = r'''
import json, sys, warnings
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from talvo.math import Equation
from talvo.paragraph import Paragraph
from F15_helpers import render_math_document
from talvo.warnings import TalvoWarning
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter('always')
    result = render_math_document(Path(sys.argv[2]), [
        Paragraph('Surroundingbefore'),
        Paragraph([Equation(r'\frac{x}{y}')]),
        Paragraph('Surroundingafter')])
Path(sys.argv[3]).write_text(json.dumps({
    'result': result,
    'warnings': [{'talvo': issubclass(w.category, TalvoWarning),
                  'message': str(w.message)} for w in caught]}))
'''
    report = destination.with_suffix('.json')
    result = run_python(source, python=environment.python,
        args=(str(Path(__file__).parent),str(destination),str(report)),
        env=environment.env, timeout=60)
    assert result.returncode == 0, (result.stdout,result.stderr)
    return json.loads(report.read_text())
