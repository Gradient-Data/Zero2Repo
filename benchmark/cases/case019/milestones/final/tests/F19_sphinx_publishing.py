# feature: F19
"""Acceptance checks through the Sphinx PDF builder."""
import re
import sys
from datetime import datetime
import pytest
from _helpers import write_text
from F01_helpers import pdf_observer_environment
from F02_helpers import pdf_plain_text
from F07_helpers import token_box, visible_lines, line_containing
from F09_helpers import resolved_internal_links
from F17_helpers import assert_source_words, assert_source_artwork
from F19_helpers import sphinx_project, build_sphinx, sphinx_pdfs, assembled_files, graphviz_environment, diagram_words


@pytest.fixture
def observer(tmp_path):
    return pdf_observer_environment(tmp_path / 'observer')


def test_multiple_assembled_targets(tmp_path, observer):
    path = sphinx_project(tmp_path / 'project', [dict(doc='index', target='first'),
        dict(doc='other', target='second')], files=assembled_files())
    pdfs = sphinx_pdfs(path, build_sphinx(path), observer)
    assert set(pdfs) == {'first', 'second'}
    assert_source_words(pdfs['first'], 'Rootbodymarker', 'Childbodymarker')
    assert_source_words(pdfs['second'], 'Otherbodymarker')
    assert 'Otherbodymarker' not in pdf_plain_text(pdfs['first'])
    assert 'Childbodymarker' not in pdf_plain_text(pdfs['second'])
    body = token_box(pdfs['first'], 'Childbodymarker')['page']
    assert body > 0
    assert any('Childheading' in line['text'] and line['page'] < body
               for line in visible_lines(pdfs['first']))


def test_selection_and_toctree_only(tmp_path, observer):
    for only in (False, True):
        path = sphinx_project(tmp_path / str(only), [dict(doc='index', target='chosen', toctree_only=only),
            dict(doc='other', target='excluded')], "talvo_targets = ['chosen']\n", assembled_files())
        pdfs = sphinx_pdfs(path, build_sphinx(path), observer)
        assert set(pdfs) == {'chosen'}
        assert_source_words(pdfs['chosen'], 'Childbodymarker')
        assert ('Rootbodymarker' in pdf_plain_text(pdfs['chosen'])) == (not only)


def test_target_metadata_and_templates(tmp_path, observer):
    custom = '''
from talvo.templates import Book
from talvo.paragraph import Paragraph
class Publication(Book):
    def render(self, *args, **kwargs):
        self.insert("contents", Paragraph(self.get_metadata("edition")), 0)
        return super().render(*args, **kwargs)
custom = Publication.Configuration("custom metadata")
'''
    files = {'index': ':title: Sourcetitle\n:author: Sourcewriter\n:date: Sourcedate\n\nRoot\n====\n\nBodymarker\n'}
    path = sphinx_project(tmp_path / 'project', None, extra="import sys, os\nsys.path.insert(0, os.path.dirname(__file__))\nfrom publication import custom\n", files=files,
        settings="talvo_documents = [dict(doc='index', target='book', title='Booktitle', subtitle='Booksubtitle', author='Bookwriter', date='Bookdate', logo='logo.png', template=custom, edition='Editionmarker'), dict(doc='index', target='article', title='Articletitle', subtitle='Articlesubtitle', author='Articlewriter', date='Articledate', template='article')]\n")
    write_text(path / 'publication.py', custom)
    from F10_helpers import image_asset
    image_asset(path / 'logo.png')
    pdfs = sphinx_pdfs(path, build_sphinx(path), observer)
    for target, title, author, subtitle in [('book', 'Booktitle', 'Bookwriter', 'Booksubtitle'), ('article', 'Articletitle', 'Articlewriter', 'Articlesubtitle')]:
        snap = pdfs[target]
        assert snap['metadata']['title'] == title
        assert snap['metadata']['author'] == author
        assert_source_words(snap, title, author, subtitle, 'Bodymarker')
        assert 'Sourcetitle' not in pdf_plain_text(snap)
    assert_source_words(pdfs['book'], 'Bookdate', 'Editionmarker')
    assert_source_artwork(path / 'out' / 'book.pdf', pdfs['book'], observer, 1)
    assert token_box(pdfs['book'], 'Booktitle')['page'] < token_box(pdfs['book'], 'Bodymarker')['page']
    assert token_box(pdfs['article'], 'Articletitle')['page'] == token_box(pdfs['article'], 'Bodymarker')['page']


def test_metadata_source_and_project_defaults(tmp_path, observer):
    for source in (True, False):
        body = (':title: Sourcetitle\n:author: Sourcewriter\n:date: Sourcedate\n\n' if source else '') + 'Root\n====\n\nBodymarker\n'
        path = sphinx_project(tmp_path / str(source), [dict(doc='index', target='result')], files={'index': body})
        snap = sphinx_pdfs(path, build_sphinx(path), observer)['result']
        assert snap['metadata']['author'] == 'Projectwriter'
        assert 'Orchardproject' in snap['metadata']['title']
        assert_source_words(snap, '7.4', 'Projectdate')
        # Source author and date fields are not imported anywhere in the PDF.
        assert 'Sourcewriter' not in pdf_plain_text(snap)
        assert 'Sourcedate' not in pdf_plain_text(snap)
    path = sphinx_project(tmp_path / 'current', [dict(doc='index', target='result')], "today = ''\ntoday_fmt = '%Y-%m-%d'\n")
    before = datetime.now().date()
    snap = sphinx_pdfs(path, build_sphinx(path), observer)['result']
    after = datetime.now().date()
    assert any(day.isoformat() in pdf_plain_text(snap) for day in {before, after})


def test_sphinx_navigation_domains_and_indexes(tmp_path, observer):
    files = assembled_files()
    files['index'] += '\nLinkanchor :ref:`Jumplink <destination>` and :py:func:`harvest.pick`.\n'
    files['child'] = '''.. _destination:

Childheading
============

Childbodymarker

.. py:module:: harvest

.. py:function:: pick(basket)

   Pickdescription.

   :param basket: Basketdescription.

.. code-block:: python

   print("Codemarker")

.. warning:: Warningmarker

.. glossary::

   Orchardterm
      Definitionmarker

.. index:: Zebraterm

Indexbodymarker
'''
    path = sphinx_project(tmp_path / 'project', [dict(doc='index', target='enabled'),
        dict(doc='index', target='disabled', domain_indices=False)], files=files)
    pdfs = sphinx_pdfs(path, build_sphinx(path), observer)
    for target, snap in pdfs.items():
        assert_source_words(snap, 'pick', 'basket', 'Pickdescription', 'Basketdescription', 'Codemarker', 'Warningmarker', 'Orchardterm', 'Definitionmarker', 'Zebraterm')
        links = resolved_internal_links(path / 'out' / (target + '.pdf'), observer)
        destination = token_box(snap, 'Childbodymarker')['page']
        source = line_containing(snap, 'Linkanchor')
        actions = [link for link in links[source['page']]
                   if link['from'][1] <= source['bbox'][3]
                   and link['from'][3] >= source['bbox'][1]]
        assert len(actions) >= 2, actions
        assert all(link.get('page') == destination and 'to' in link for link in actions), actions
        assert token_box(snap, 'Zebraterm')['page'] > token_box(snap, 'Indexbodymarker')['page']
    assert 'Python Module Index' in pdf_plain_text(pdfs['enabled'])
    assert 'Python Module Index' not in pdf_plain_text(pdfs['disabled'])
    # Enabling the domain index must add a module entry that reaches its body,
    # regardless of index placement, page numbering or destination encoding.
    module_entries = {}
    for target, snap in pdfs.items():
        body_page = token_box(snap, 'Childbodymarker')['page']
        links = resolved_internal_links(path / 'out' / (target + '.pdf'), observer)
        module_entries[target] = [line for line in visible_lines(snap)
            if re.search(r'\bharvest\b', line['text'])
            and any(link.get('page') == body_page and 'to' in link
                    and link['from'][1] <= line['bbox'][3]
                    and link['from'][3] >= line['bbox'][1]
                    for link in links[line['page']])]
    assert len(module_entries['enabled']) > len(module_entries['disabled']), module_entries


def test_latex_target_compatibility_and_precedence(tmp_path, observer):
    for name, documents in [('absent', None), ('empty', []), ('dedicated', [dict(doc='other', target='own')])]:
        path = sphinx_project(tmp_path / name, documents,
            "latex_documents = [('index', 'legacy.tex', 'Legacytitle', 'Legacywriter', 'manual')]\n", assembled_files())
        pdfs = sphinx_pdfs(path, build_sphinx(path), observer)
        expected = 'own' if name == 'dedicated' else 'legacy'
        assert set(pdfs) == {expected}
        assert_source_words(pdfs[expected], 'Otherbodymarker' if name == 'dedicated' else 'Childbodymarker')
        if expected == 'legacy':
            # The LaTeX definition's title and author define the target too.
            assert pdfs['legacy']['metadata']['title'] == 'Legacytitle'
            assert pdfs['legacy']['metadata']['author'] == 'Legacywriter'


def test_invalid_and_absent_targets(tmp_path, observer):
    for missing in ('doc', 'target'):
        entry = dict(doc='index', target='valid')
        del entry[missing]
        path = sphinx_project(tmp_path / missing, [entry])
        result = build_sphinx(path)
        assert result.returncode == 2, result
        # The key must be named as a word, not found inside 'talvo_documents'.
        assert b'talvo_documents' in result.stderr, result
        assert re.search(rb'(?<![A-Za-z_])' + missing.encode() + rb'(?![A-Za-z_])',
                         result.stderr.replace(b'talvo_documents', b'')), result
        assert not list((path / 'out').glob('*.pdf'))
    for name, documents, settings, report in [
        ('root', [dict(doc='absentroot', target='bad'), dict(doc='index', target='valid')], '', 'absentroot'),
        ('selection', [dict(doc='index', target='valid')], "talvo_targets = ['valid', 'absenttarget']\n", 'absenttarget'),
        ('none', [], '', 'talvo_documents')]:
        path = sphinx_project(tmp_path / name, documents, settings)
        result = build_sphinx(path)
        pdfs = sphinx_pdfs(path, result, observer)
        assert report.encode() in result.stderr, result
        assert set(pdfs) == (set() if name == 'none' else {'valid'})
        if pdfs:
            assert_source_words(pdfs['valid'], 'Rootbodymarker')


def test_graphviz_diagram(tmp_path, observer):
    files = {'index': '''Graph
=====

.. graphviz::

   digraph orchard {
      rankdir=LR;
      node [shape=plaintext];
      Seednode -> Treenode [label="Growlabel", color=red];
      Treenode -> Fruitnode [label="Yieldlabel", color=blue];
   }
'''}
    dot = graphviz_environment(tmp_path / 'tools')
    path = sphinx_project(tmp_path / 'graph', [dict(doc='index', target='graph')],
                          settings='graphviz_dot = ' + repr(str(dot)) + '\n', files=files)
    snap = sphinx_pdfs(path, build_sphinx(path), observer)['graph']
    assert 'digraph' not in pdf_plain_text(snap)
    # Raster observations accept both embedded raster and vector diagrams.
    from F10_helpers import page_pixels
    labels = diagram_words(path / 'out' / 'graph.pdf', snap, observer, tmp_path / 'ocr',
                           ('Seednode', 'Treenode', 'Fruitnode', 'Growlabel', 'Yieldlabel'))
    boxes = [labels[name] for name in ('Seednode', 'Treenode', 'Fruitnode')]
    assert len({b['page'] for b in boxes}) == 1
    image = page_pixels(path / 'out' / 'graph.pdf', observer, page=boxes[0]['page'])
    for source, dest, edge_name in [(boxes[0], boxes[1], 'Growlabel'), (boxes[1], boxes[2], 'Yieldlabel')]:
        import math
        origin = ((source['x0'] + source['x1']) / 2, source['y'])
        dx = (dest['x0'] + dest['x1']) / 2 - origin[0]
        dy = dest['y'] - origin[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        edge = labels[edge_name]
        assert edge['page'] == source['page']
        label_u = (((edge['x0']+edge['x1'])/2-origin[0])*ux
                   + (edge['y']-origin[1])*uy)
        assert 0 < label_u < length, (edge_name, source, dest, edge)
        source_half = (abs(ux)*(source['x1']-source['x0']) + abs(uy)*(source['y1']-source['y0']))/2
        dest_half = (abs(ux)*(dest['x1']-dest['x0']) + abs(uy)*(dest['y1']-dest['y0']))/2
        points = []
        left = max(0, int(2*(min(source['x0'],dest['x0'])-25)))
        right = min(image.width, int(2*(max(source['x1'],dest['x1'])+25)))
        top = max(0, int(2*(min(source['y0'],dest['y0'])-25)))
        bottom = min(image.height, int(2*(max(source['y1'],dest['y1'])+25)))
        for x in range(left, right):
            for y in range(top, bottom):
                if min(image.getpixel((x,y))) >= 180:
                    continue
                px, py = x/2, y/2
                if any(label['x0']-1 <= px <= label['x1']+1 and
                       label['y0']-1 <= py <= label['y1']+1 for label in labels.values()):
                    continue
                u = (px-origin[0])*ux + (py-origin[1])*uy
                v = -(px-origin[0])*uy + (py-origin[1])*ux
                if source_half+1 < u < length-dest_half-1 and abs(v) < 20:
                    points.append((u,v))
        assert points, (source, dest)
        start, stop = min(p[0] for p in points), max(p[0] for p in points)
        columns = []
        for step in range(math.ceil(start), math.floor(stop)):
            ys = [v for u,v in points if step <= u < step+1]
            assert ys, (step, start, stop)
            columns.append(len(ys))
        # The stroke traverses the gap; the destination end has a widening and
        # tapering arrowhead. Neither color nor PDF drawing encoding is pinned.
        assert stop-start > (length-source_half-dest_half)/2
        middle = columns[len(columns)//4:len(columns)//2]
        end = columns[len(columns)//2:-2]
        assert middle and end and max(end) > 2*max(middle), columns
        assert end[-1] < max(end), columns
