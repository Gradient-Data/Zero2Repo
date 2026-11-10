# feature: F06
"""Small deterministic optimisation fixtures and public solver driver."""
import numpy as np
from velmora import Network
from _helpers import invoke
from F03_helpers import electrical_pair


def dispatch_bus(demand=12, snapshots=('now',)):
    n = Network()
    n.set_snapshots(snapshots)
    n.add('Bus', 'sink', v_nom=1)
    n.add('Load', 'demand', bus='sink', p_set=demand)
    return n


def solve_dispatch(n, snapshots=None, **kwargs):
    result = invoke(n.optimize, snapshots, kwargs={
        'solver_name': 'highs', 'solver_options': {'threads': 1}, **kwargs},)
    assert result.value == ('ok', 'optimal'), result
    return n


def assert_close(actual, expected, atol=1e-5):
    np.testing.assert_allclose(actual, expected, atol=atol, rtol=1e-6)


def conversion_dispatch(component, demand=12, snapshots=('now',), **attributes):
    n = dispatch_bus(demand, snapshots)
    n.add('Generator', 'backup', bus='sink', p_nom=100, marginal_cost=20)
    if component == 'Generator':
        n.add(component, 'asset', bus='sink', p_nom=10,
              marginal_cost=1, **attributes)
    else:
        n.add('Bus', 'source', v_nom=1)
        n.add('Generator', 'fuel', bus='source', p_nom=100, marginal_cost=1)
        n.add(component, 'asset', bus0='source', bus1='sink', p_nom=10,
              marginal_cost=1, **attributes)
    return n


def asset_dispatch(n, component, snapshots=None):
    field = 'p' if component == 'Generator' else 'p0'
    rows = n.snapshots if snapshots is None else snapshots
    return n.components[component].dynamic[field].loc[rows, 'asset']


def loss_dispatch(demand=40, **attributes):
    n = electrical_pair()
    n.set_snapshots(['now'])
    n.c.buses.static.loc[:, 'v_nom'] = 1.
    n.c.lines.static.loc['circuit', ['r', 'x', 's_nom']] = [.001, .01, 100]
    for key, value in attributes.items():
        n.c.lines.static.loc['circuit', key] = value
    n.add('Generator', 'supply', bus='west', p_nom=500, marginal_cost=7)
    n.add('Generator', 'local', bus='east', p_nom=500, marginal_cost=70)
    n.add('Load', 'demand', bus='east', p_set=demand)
    return n


def loss_observation(n):
    p0 = n.c.lines.dynamic.p0.at['now', 'circuit']
    p1 = n.c.lines.dynamic.p1.at['now', 'circuit']
    return (p0-p1)/2, p0+p1


def detached_solution(network, path):
    """Preserve real solved public tables without copying native solver handles.

    Use the public persistence interface, not solver implementation attributes.
    Export/import errors remain failed prerequisites; no cached file is reused
    across pytest invocations.
    """
    network.export_to_netcdf(path)
    restored = Network()
    restored.import_from_netcdf(path)
    return restored

