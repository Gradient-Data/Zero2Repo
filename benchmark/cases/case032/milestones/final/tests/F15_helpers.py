# feature: F15
"""Fixtures and strict readers for public model inspection outputs."""
import json
import xml.etree.ElementTree as ET

from _helpers import run_process
from F01_helpers import dist
import velnora


def inspection_model(data, mask):
    bias = velnora.param('bias', .4)
    scale = velnora.param('scale', 1.2, constraint=dist.constraints.positive)
    root = velnora.sample('root', dist.Normal(bias, scale))
    other = velnora.sample('other', dist.LogNormal(0., 1.))
    with velnora.plate('rows', len(mask)):
        local = velnora.sample('local', dist.Normal(root, 1.))
        velnora.sample('reading', dist.Normal(local + other, scale).mask(mask), obs=data)


def dependency_edges(mapping):
    """Remove only the arbitrary orientation of undirected posterior edges."""
    return {frozenset((source, target)): set(plates)
            for source, targets in mapping.items() for target, plates in targets.items()}


def read_dot_graph(source):
    """Parse DOT with the installed Graphviz parser, retaining named structure."""
    result = run_process(['dot', '-Tjson'], input_data=source, timeout=30)
    assert result.returncode == 0, result.stderr_text
    graph = json.loads(result.stdout_text)
    assert graph['directed'] is True
    objects = {item['_gvid']: item for item in graph['objects']}
    nodes = {item['name']: item for item in graph['objects'] if 'nodes' not in item}
    groups = {item['label']: {objects[i]['name'] for i in item['nodes']}
              for item in graph['objects'] if 'nodes' in item}
    edges = {(objects[e['tail']]['name'], objects[e['head']]['name'])
             for e in graph['edges']}
    return nodes, groups, edges


def read_svg_graph(path):
    """Read Graphviz SVG node and edge title carriers and visible text."""
    root = ET.parse(path).getroot()
    ns = {'s': 'http://www.w3.org/2000/svg'}
    assert root.tag == '{http://www.w3.org/2000/svg}svg'
    groups = {}
    for group in root.findall('.//s:g', ns):
        kind = group.attrib.get('class')
        if kind in ('node', 'edge', 'cluster'):
            title = group.find('s:title', ns)
            assert title is not None and title.text
            key = (kind, title.text)
            assert key not in groups
            groups[key] = group
    text = {''.join(t.itertext()) for t in root.findall('.//s:text', ns)}
    return groups, text


def read_shape_rows(report):
    """Read the sectioned shape table and its batch/event separator grammar."""
    lines = report.splitlines()
    assert lines[0].strip() == 'Trace Shapes:'
    section = None
    current = None
    sites = {}
    for line in lines[1:]:
        tokens = line.split()
        if tokens in (['Param', 'Sites:'], ['Sample', 'Sites:']):
            section = tokens[0]
            continue
        assert section == 'Sample', line
        left, separator, right = line.partition('|')
        assert separator, line
        fields = left.split()
        if len(fields) >= 2 and fields[1] == 'plate':
            continue
        if len(fields) >= 2 and fields[1] == 'dist':
            current = fields[0]
            assert current not in sites
            sites[current] = {}
            kind, dimensions = 'dist', fields[2:]
        else:
            assert current is not None and fields[0] in ('value', 'log_prob'), line
            kind, dimensions = fields[0], fields[1:]
        assert kind not in sites[current], line
        sites[current][kind] = (tuple(map(int, dimensions)), tuple(map(int, right.split())))
    return sites
