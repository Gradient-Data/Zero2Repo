# feature: F15
"""Acceptance tests for model dependency inspection and visualization."""
from F01_helpers import jnp, dist, call_public
from F15_helpers import (
    inspection_model, dependency_edges, read_dot_graph, read_svg_graph, read_shape_rows,
)
import velnora
from velnora import handlers
from velnora.infer.inspect import get_dependencies, get_model_relations, render_model
from velnora.util import format_shapes


def drop_empty_self(mapping):
    """Ignore a site listed as its own dependency with no coupling group.

    The documents describe a dependency mapping as the sites a site is coupled
    with; an empty self entry carries no such coupling and is never required.
    A non-empty self entry (plate coupling) survives and is still compared.
    """
    return {name: {other: groups for other, groups in targets.items()
                   if other != name or groups}
            for name, targets in mapping.items()}


def test_f15_t01():
    def collider(observation):
        a = velnora.sample('parent_a', dist.Normal())
        b = velnora.sample('parent_b', dist.LogNormal())
        velnora.sample('unrelated', dist.Normal())
        velnora.sample('child', dist.Normal(a, b), obs=observation)

    prior = {'parent_a': {'parent_a': set()}, 'parent_b': {'parent_b': set()},
             'unrelated': {'unrelated': set()},
             'child': {'child': set(), 'parent_a': set(), 'parent_b': set()}}
    for observation in (None, .7):
        result = call_public(get_dependencies, collider, model_kwargs={'observation': observation})
        assert drop_empty_self(result['prior_dependencies']) == drop_empty_self(prior)
        posterior = drop_empty_self(result['posterior_dependencies'])
        assert set(posterior) == ({'parent_a', 'parent_b', 'unrelated', 'child'}
                                  if observation is None else {'parent_a', 'parent_b', 'unrelated'})
        expected = {frozenset(('parent_a', 'parent_b')): set()}
        child_edges = {frozenset(('parent_a', 'child')): set(),
                       frozenset(('parent_b', 'child')): set()}
        if observation is None:
            assert dependency_edges(posterior) == {**expected, **child_edges}
        else:
            # Entries toward the observed child are optional; present, they are exactly its couplings.
            assert dependency_edges(posterior) in (expected, {**expected, **child_edges})

    def grouped(data, aggregate):
        with velnora.plate('subjects', len(data)):
            x = velnora.sample('effects', dist.Normal())
            if not aggregate:
                velnora.sample('measurements', dist.Normal(x, 1.), obs=data)
        if aggregate:
            velnora.sample('measurements', dist.Normal(x.sum(), 1.), obs=data.sum())

    for aggregate in (False, True):
        result = call_public(get_dependencies, grouped, (jnp.array([.2, -.4, 1.1]),),
                             {'aggregate': aggregate})
        assert drop_empty_self(result['prior_dependencies']) == drop_empty_self({
            'effects': {'effects': set()},
            'measurements': {'effects': set(), 'measurements': set()}})
        latent = {'effects': {'subjects'} if aggregate else set()}
        # The entry toward the observed site is optional; present, it carries no group.
        assert drop_empty_self(result['posterior_dependencies']) in (
            drop_empty_self({'effects': latent}),
            drop_empty_self({'effects': {**latent, 'measurements': set()}}))


def test_f15_t02():
    data = jnp.array([.3, 1.1, -.8])
    for mask in (jnp.ones(3, dtype=bool), jnp.array([True, False, True])):
        result = call_public(get_model_relations, inspection_model, model_args=(data, mask))
        assert {n: set(v) for n, v in result['sample_sample'].items()} == {
            'root': set(), 'other': set(), 'local': {'root'}, 'reading': {'local', 'other'}}
        assert {n: set(v) for n, v in result['sample_param'].items()} == {
            'root': {'bias', 'scale'}, 'other': set(), 'local': set(), 'reading': {'scale'}}
        assert result['sample_dist'] == {
            'root': 'Normal', 'other': 'LogNormal', 'local': 'Normal', 'reading': 'Normal'}
        assert set(result['param_constraint']) == {'bias', 'scale'}
        assert result['param_constraint']['bias'] in ('', str(dist.constraints.real))
        assert result['param_constraint']['scale'] == str(dist.constraints.positive)
        assert {n: set(v) for n, v in result['plate_sample'].items()} == {'rows': {'local', 'reading'}}
        assert set(result['observed']) == {'reading'}
    latent = call_public(get_model_relations, inspection_model,
                         model_args=(None, jnp.ones(3, dtype=bool)))
    assert set(latent['observed']) == set()
    assert latent['sample_dist']['reading'] == 'Normal'


def test_f15_t03(tmp_path):
    args = (jnp.array([.3, 1.1, -.8]), jnp.ones(3, dtype=bool))
    samples = {'root', 'other', 'local', 'reading'}
    sample_edges = {('root', 'local'), ('other', 'reading'), ('local', 'reading')}
    param_edges = {('bias', 'root'), ('scale', 'root'), ('scale', 'reading')}
    annotations = {'root ~ Normal', 'other ~ LogNormal', 'local ~ Normal',
                   'reading ~ Normal', f'scale ∈ {dist.constraints.positive}'}
    # Two independent switches: exercise each alone as well as their combination.
    for params, distributions in ((False, False), (True, False), (False, True), (True, True)):
        path = tmp_path / f'model_{params}_{distributions}.svg'
        graph = call_public(render_model, inspection_model, model_args=args,
                            filename=str(path), render_params=params,
                            render_distributions=distributions)
        nodes, groups, edges = read_dot_graph(graph.source)
        expected_nodes = samples | ({'bias', 'scale'} if params else set())
        if distributions:
            expected_nodes |= {'distribution_description_node'}
            expected_annotations = annotations if params else {a for a in annotations if ' ~ ' in a}
            # The unconstrained parameter may carry the real constraint's string or no description.
            optional = {f'bias ∈ {dist.constraints.real}'} if params else set()
            rendered = set(filter(None, nodes['distribution_description_node']['label'].split('\\l')))
            assert rendered in (expected_annotations, expected_annotations | optional)
        assert set(nodes) == expected_nodes
        assert groups == {'rows': {'local', 'reading'}}
        assert edges == sample_edges | (param_edges if params else set())
        assert nodes['reading']['fillcolor'] != nodes['local']['fillcolor']
        svg, text = read_svg_graph(path)
        assert {name for kind, name in svg if kind == 'node'} == expected_nodes
        assert {name for kind, name in svg if kind == 'edge'} == {f'{a}->{b}' for a, b in edges}
        assert ('cluster', 'cluster_rows') in svg
        assert 'rows' in text
        assert samples <= text
        if distributions:
            assert expected_annotations <= text
        observed_fill = {element.attrib['fill'] for element in svg['node', 'reading'].iter()
                         if 'fill' in element.attrib}
        latent_fill = {element.attrib['fill'] for element in svg['node', 'local'].iter()
                       if 'fill' in element.attrib}
        assert observed_fill and latent_fill
        assert observed_fill != latent_fill
    # The same site changes observed status without changing model structure.
    graph = call_public(render_model, inspection_model, model_args=(None, args[1]))
    nodes, groups, edges = read_dot_graph(graph.source)
    assert set(nodes) == samples and edges == sample_edges
    assert nodes['reading']['fillcolor'] == nodes['local']['fillcolor']


def test_f15_t04():
    for batch, event, draws in ((2, 3, 5), (3, 2, 7)):
        def model():
            velnora.sample('scalar', dist.Normal())
            velnora.sample('vector', dist.Normal(jnp.zeros((batch, event)), 1.).to_event(1),
                           sample_shape=(draws,))
            with velnora.plate('rows', 4):
                velnora.sample('matrix', dist.Normal(jnp.zeros((2, event)), 1.).to_event(2))
        trace = call_public(handlers.trace(handlers.seed(model, 82)).get_trace)
        expected = {
            'scalar': {'dist': ((), ()), 'value': ((), ())},
            'vector': {'dist': ((batch,), (event,)), 'value': ((draws, batch), (event,))},
            'matrix': {'dist': ((4,), (2, event)), 'value': ((4,), (2, event))}}
        report = call_public(format_shapes, trace)
        assert read_shape_rows(report) == expected
        for option in (True, lambda site: site['name'] == 'vector'):
            rows = read_shape_rows(call_public(format_shapes, trace, compute_log_prob=option))
            want = {name: dict(fields) for name, fields in expected.items()}
            for name, shape in [('scalar', ()), ('vector', (draws, batch)), ('matrix', (4,))]:
                if option is True or name == 'vector':
                    want[name]['log_prob'] = (shape, ())
            assert rows == want
