# feature: F19
"""Solved statistics workloads and independent labeled observations."""
import numpy as np
import pandas as pd
import pytest
from velmora import Network
from F06_helpers import solve_dispatch, assert_close, detached_solution


def statistics_value(n, metric, **kwargs):
    options = dict(groupby=False, nice_names=False, drop_zero=False, round=8)
    options.update(kwargs)
    return getattr(n.statistics, metric)(**options)


def statistics_grid(solve=True):
    n = Network()
    n.set_snapshots(['first', 'second', 'third'])
    n.snapshot_weightings = pd.DataFrame(
        {'objective': [2., 5., 3.], 'generators': [3., 1., 4.],
         'stores': [1., 1., 1.]}, index=n.snapshots)
    n.add('Carrier', ['AC', 'heat', 'fuel', 'wire', 'convert', 'load'])
    n.add('Bus', ['a', 'b', 'h'], carrier=['AC', 'AC', 'heat'],
          unit='MW', country=['north', 'south', 'south'], location=['west', 'east', 'east'])
    n.add('Generator', 'ga', bus='a', carrier='fuel', p_nom=60,
          marginal_cost=[2, 12, 3], p_max_pu=[1, 1, 1])
    n.add('Generator', 'gb', bus='b', carrier='fuel', p_nom=50,
          marginal_cost=[11, 1, 14])
    n.add('Generator', 'zero', bus='a', carrier='fuel', p_nom=0,
          marginal_cost=100)
    n.add('Load', 'la', bus='a', carrier='load', p_set=[2, 8, 3])
    n.add('Load', 'lb', bus='b', carrier='load', p_set=[9, 2, 7])
    n.add('Load', 'lh', bus='h', carrier='load', p_set=[2, 4, 3])
    n.add('Link', 'wire', bus0='a', bus1='b', carrier='wire',
          p_nom=4, p_min_pu=-1, efficiency=1)
    n.add('Link', 'convert', bus0='a', bus1='h', carrier='convert',
          p_nom=30, efficiency=.5)
    if solve:
        solve_dispatch(n)
    return n


def signed_ports(n, component, asset):
    """Explicit public power fields, with the network injection convention."""
    c = n.components[component]
    if component in ('Link', 'Process', 'Line', 'Transformer'):
        return {'0': -c.dynamic.p0[asset], '1': -c.dynamic.p1[asset]}
    return {'': c.dynamic.p[asset] * c.static.at[asset, 'sign']}


def check_energy_statistics(n, component, asset):
    ports = signed_ports(n, component, asset)
    weights = n.snapshot_weightings.generators
    for metric, transform in (
        ('supply', lambda p: p.clip(lower=0)),
        ('withdrawal', lambda p: -p.clip(upper=0)),
        ('energy_balance', lambda p: p),
    ):
        expected = sum((transform(p) for p in ports.values()))
        options = dict(components=[component], at_port='all')
        raw = statistics_value(n, metric, groupby_time=False, **options)
        assert_close(raw.loc[(component, asset), n.snapshots], expected)
        total = statistics_value(n, metric, **options)
        assert_close(total.loc[(component, asset)], (expected * weights).sum())


def price_oracle(n, buses, load_weighted):
    prices = n.c.buses.dynamic.marginal_price.loc[:, buses]
    weights = n.snapshot_weightings.objective
    demand = pd.DataFrame(0., index=n.snapshots, columns=buses)
    for component in ('Generator', 'Load', 'Link'):
        c = n.components[component]
        for asset in c.static.index:
            for port, p in signed_ports(n, component, asset).items():
                bus = c.static.at[asset, 'bus'+port]
                if bus in buses:
                    demand[bus] += -p.clip(upper=0)
    if not load_weighted:
        demand.loc[:, :] = 1.
    weighted = demand.mul(weights, axis=0)
    return (prices * weighted).sum().sum() / weighted.sum().sum()


def port_labels(network, component, port='', nice_names=False):
    return pd.Series(port, index=network.components[component].static.index,
                     name='port')


def statistics_regions(network, component, port='', nice_names=False):
    return network.components[component].static['bus'+port].map(
        {'a': 'shared', 'b': 'shared'}).rename('region')



@pytest.fixture(scope='module')
def statistics_solution(tmp_path_factory):
    network = statistics_grid()
    return detached_solution(network, tmp_path_factory.mktemp('statistics') / 'solved.nc')


@pytest.fixture
def statistics_network(statistics_solution):
    """Every consumer owns its tables, including scenario-changing consumers."""
    return statistics_solution.copy()
