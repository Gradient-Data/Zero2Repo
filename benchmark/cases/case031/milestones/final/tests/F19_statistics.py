# feature: F19
"""Acceptance tests for physical/economic statistics and network comparison."""
import numpy as np
import pandas as pd
from velmora import Network, NetworkCollection
from _helpers import invoke
from F06_helpers import solve_dispatch, assert_close, dispatch_bus
from F07_helpers import storage_dispatch
from F08_helpers import expansion_problem, INVESTMENT_COMPONENTS
from F09_helpers import scheduled_asset
from F19_helpers import (statistics_value, statistics_solution, statistics_network, signed_ports,
                         check_energy_statistics, price_oracle, port_labels, statistics_regions)


def test_capacity_and_signed_port_expansion(statistics_network):
    for component in INVESTMENT_COMPONENTS:
        attrs = {'max_hours': 3} if component == 'StorageUnit' else {}
        n, nominal = expansion_problem(component, **attrs)
        solve_dispatch(n)
        c = n.components[component]
        optimal = c.static.at['asset', nominal+'_opt']
        assert optimal > 0
        for metric, expected in [('installed_capacity', 30),
                                 ('optimal_capacity', optimal),
                                 ('expanded_capacity', max(optimal-30, 0))]:
            assert_close(statistics_value(n, metric, components=[component]).loc[
                (component, 'asset')], expected)
        if component == 'StorageUnit':
            assert_close(statistics_value(n, 'optimal_capacity', storage=True).loc[
                (component, 'asset')], 3*optimal)
            assert_close(statistics_value(n, 'installed_capacity', storage=True).loc[
                (component, 'asset')], 90)
    n = statistics_network
    for metric, nominal in [('installed_capacity', 'p_nom'),
                            ('optimal_capacity', 'p_nom_opt')]:
        out = statistics_value(n, metric, components=['Link'],
                               groupby=['name', port_labels], at_port='all')
        for asset, efficiency in [('wire', 1), ('convert', .5)]:
            capacity = n.c.links.static.at[asset, nominal]
            assert_close(out.loc[('Link', asset, '0')], -capacity)
            assert_close(out.loc[('Link', asset, '1')], efficiency*capacity)
    # Expansion in signed consumption capacity must retain the negative sign.
    n = dispatch_bus([6, 10], [0, 1])
    n.add('Bus', 'source')
    n.add('Generator', 'fuel', bus='source', p_nom=100, marginal_cost=1)
    n.add('Link', 'asset', bus0='source', bus1='sink', p_nom=2,
          p_nom_extendable=True, efficiency=.5, capital_cost=1)
    solve_dispatch(n)
    out = statistics_value(n, 'expanded_capacity', components=['Link'],
                           groupby=['name', port_labels], at_port='all')
    assert_close(out.loc[('Link', 'asset', '0')], -18)
    assert_close(out.loc[('Link', 'asset', '1')], 9)


def test_supply_withdrawal_balance_and_curtailment(statistics_network):
    n = statistics_network
    assert (n.c.links.dynamic.p0['wire'] > 0).any()
    assert (n.c.links.dynamic.p0['wire'] < 0).any()
    for component, asset in [('Generator', 'ga'), ('Load', 'lb'),
                              ('Link', 'wire'), ('Link', 'convert')]:
        check_energy_statistics(n, component, asset)
    # Opposite injections must be split before adding the ports, not netted.
    assert statistics_value(n, 'supply', at_port='all').loc[('Link', 'wire')] > 0
    available = 60 - n.c.generators.dynamic.p['ga']
    assert_close(statistics_value(n, 'curtailment', components=['Generator']).loc[
        ('Generator', 'ga')], (available.clip(lower=0)*n.snapshot_weightings.generators).sum())
    # A negative minimum permits consumption; availability still bounds curtailment.
    m = dispatch_bus([3, 5], [0, 1])
    m.add('Generator', 'asset', bus='sink', p_nom=10, p_max_pu=[.5, .8],
          marginal_cost=1)
    solve_dispatch(m)
    assert_close(statistics_value(m, 'curtailment').loc[('Generator', 'asset')], 5)
    # Changing availability does not fabricate or overwrite the stored dispatch.
    m.c.generators.dynamic.p_max_pu.loc[:, 'asset'] = 0
    assert_close(statistics_value(m, 'curtailment').loc[('Generator', 'asset')], 0)


def test_utilisation_revenue_and_primary_operation(statistics_network):
    for component in INVESTMENT_COMPONENTS:
        # A lossy link separates its input (operation) from its output port.
        attrs = ({'rate0': -2, 'rate1': .5} if component == 'Process' else
                 {'efficiency': .5} if component == 'Link' else {})
        n, nominal = expansion_problem(component, **attrs)
        n.snapshot_weightings.loc[:, 'generators'] = np.arange(1, len(n.snapshots)+1)*2
        solve_dispatch(n)
        c = n.components[component]
        field = 'e' if component == 'Store' else (
            'p0' if component in ('Line', 'Transformer', 'Link') else 'p')
        operation = c.dynamic[field]['asset'].abs()
        weights = n.snapshot_weightings.generators
        energy = (operation*weights).sum()
        assert energy > 0
        assert_close(statistics_value(n, 'capacity_factor', components=[component]).loc[
            (component, 'asset')], energy/weights.sum()/(c.static.at['asset', nominal+'_opt'] *
                (abs(attrs['rate0']) if component == 'Process' else 1)))
        if component == 'Link':
            # Total market value is per unit of primary-port (input) operation.
            revenue = sum((p*n.c.buses.dynamic.marginal_price[c.static.at['asset', 'bus'+port]] *
                           n.snapshot_weightings.objective).sum()
                          for port, p in signed_ports(n, component, 'asset').items())
            assert abs(revenue) > 1
            assert_close(statistics_value(n, 'market_value', components=[component],
                                          groupby_time='sum', at_port='all').loc[(component, 'asset')],
                         revenue/energy)
    n = statistics_network
    for component, asset in [('Generator', 'ga'), ('Load', 'lb'), ('Link', 'convert'),
                             ('Link', 'wire')]:
        c = n.components[component]
        revenue = 0.
        for port, p in signed_ports(n, component, asset).items():
            bus = c.static.at[asset, 'bus'+port]
            revenue += (p*n.c.buses.dynamic.marginal_price[bus]*
                        n.snapshot_weightings.objective).sum()
        assert_close(statistics_value(n, 'revenue', at_port='all').loc[(component, asset)], revenue)
        operation = c.dynamic['p0' if component == 'Link' else 'p'][asset].abs()
        denominator = (operation*n.snapshot_weightings.generators).sum()
        assert_close(statistics_value(n, 'market_value', groupby_time='sum', at_port='all').loc[(component, asset)],
                     revenue/denominator)
        # Default: ratio of the objective-weighted mean revenue to the
        # generator-weighted mean absolute primary operation.
        assert_close(statistics_value(n, 'market_value', at_port='all').loc[(component, asset)],
                     (revenue/n.snapshot_weightings.objective.sum()) /
                     (denominator/n.snapshot_weightings.generators.sum()))
    for component in ('StorageUnit', 'Store'):
        m = storage_dispatch(component, marginal_cost_storage=.2)
        solve_dispatch(m)
        c = m.components[component]
        operation = c.dynamic['e' if component == 'Store' else 'p']['buffer']
        assert_close(statistics_value(m, 'capacity_factor').loc[(component, 'buffer')],
                     operation.abs().mean()/c.static.at['buffer',
                         'e_nom_opt' if component == 'Store' else 'p_nom_opt'])


def test_investment_costs_activity_and_period_weighting():
    n = Network()
    n.set_snapshots(['first', 'second'])
    n.set_investment_periods([2030, 2040])
    n.investment_period_weightings.loc[:, 'objective'] = [2, 5]
    n.add('Bus', 'sink')
    n.add('Load', 'demand', bus='sink', p_set=7)
    n.add('Generator', 'asset', bus='sink', p_nom=20, p_nom_extendable=True,
          capital_cost=4, fom_cost=3, marginal_cost=2)
    n.add('Generator', 'future', bus='sink', p_nom=3, capital_cost=6,
          fom_cost=1, marginal_cost=100, build_year=2040, lifetime=5)
    solve_dispatch(n, multi_investment_periods=True)
    for period, weight in [(2030, 2), (2040, 5)]:
        for metric, expected in [('capex', 7*4*weight),
                                 ('installed_capex', 20*4*weight),
                                 ('expanded_capex', -13*4*weight),
                                 ('fom', 7*3*weight),
                                 ('system_cost', (7*4+7*3+2*7*2)*weight)]:
            out = statistics_value(n, metric)
            assert_close(out.loc[('Generator', 'asset'), period], expected)
        future = statistics_value(n, 'capex').loc[('Generator', 'future'), period]
        if period == 2040:
            assert_close(future, 3*6*weight)
        else:
            assert_close(0 if pd.isna(future) else future, 0)
    m = dispatch_bus([4, 7], [0, 1])
    m.snapshot_weightings.loc[:, 'objective'] = [4380, 4380]
    m.add('Generator', 'asset', bus='sink', p_nom_extendable=True,
          overnight_cost=90, discount_rate=0, lifetime=10, fom_cost=2,
          marginal_cost=1)
    solve_dispatch(m)
    assert_close(statistics_value(m, 'overnight_cost').loc[('Generator', 'asset')], 630)
    assert_close(statistics_value(m, 'capex').loc[('Generator', 'asset')], 63)
    assert_close(statistics_value(m, 'fom').loc[('Generator', 'asset')], 14)


def test_operating_cost_terms_and_system_cost():
    n = scheduled_asset(demand=(6, 0, 6), committable=True, p_min_pu=.4,
                        start_up_cost=7, shut_down_cost=5, stand_by_cost=2,
                        up_time_before=0)
    n.snapshot_weightings.loc[:, 'objective'] = [2, 3, 5]
    solve_dispatch(n)
    d = n.c.generators.dynamic
    expected = (d.p['asset']*n.snapshot_weightings.objective).sum()
    for metric, field, coefficient, weighted in [
        ('start_up_cost', 'start_up', 7, False),
        ('shut_down_cost', 'shut_down', 5, False),
        ('stand_by_cost', 'status', 2, True)]:
        term = d[field]['asset']*coefficient
        if weighted:
            term = term*n.snapshot_weightings.objective
        assert term.sum() > 0
        assert_close(statistics_value(n, 'opex', cost_types=[metric]).loc[
            ('Generator', 'asset')], term.sum())
        expected += term.sum()
    assert_close(statistics_value(n, 'opex').loc[('Generator', 'asset')], expected)
    assert_close(statistics_value(n, 'system_cost').loc[('Generator', 'asset')], expected)
    q = dispatch_bus([2, 5], [0, 1])
    q.snapshot_weightings.loc[:, 'objective'] = [3, 7]
    q.add('Generator', 'asset', bus='sink', p_nom=20, marginal_cost=2,
          marginal_cost_quadratic=.5)
    solve_dispatch(q)
    assert_close(statistics_value(q, 'opex').loc[('Generator', 'asset')],
                 (2*2+.5*4)*3+(2*5+.5*25)*7)
    for component in ('StorageUnit', 'Store'):
        s = storage_dispatch(component, marginal_cost_storage=.7)
        s.snapshot_weightings.loc[:, 'objective'] = [2, 5, 3]
        if component == 'StorageUnit':
            s.c.storage_units.static.loc['buffer', 'spill_cost'] = .4
            s.add('StorageUnit', 'water', bus='sink', p_nom=0, max_hours=1,
                  inflow=[2, 3, 4], spill_cost=.4)
        solve_dispatch(s)
        c = s.components[component]
        field = 'e' if component == 'Store' else 'state_of_charge'
        energy = c.dynamic[field]['buffer']
        assert energy.sum() > 0
        assert_close(statistics_value(s, 'opex', cost_types=['marginal_cost_storage']).loc[
            (component, 'buffer')], (energy*.7*s.snapshot_weightings.objective).sum())
        if component == 'StorageUnit':
            assert_close(statistics_value(s, 'opex', cost_types=['spill_cost']).loc[
                (component, 'water')], .4*(2*2+3*5+4*3))


def test_filters_grouping_time_and_dimensions(statistics_network):
    n = statistics_network
    p = n.c.generators.dynamic.p
    weights = n.snapshot_weightings.generators
    expected = (p[['ga', 'gb']].sum(axis=1)*weights).sum()
    default = n.statistics.supply(nice_names=False, round=8)
    assert_close(default.loc[('Generator', 'fuel')], expected)
    for group, labels in [('bus', {'a': ['ga'], 'b': ['gb']}),
                          ('country', {'north': ['ga'], 'south': ['gb']}),
                          ('location', {'west': ['ga'], 'east': ['gb']}),
                          ('name', {'ga': ['ga'], 'gb': ['gb']}),
                          ('unit', {'MW': ['ga', 'gb']}),
                          ('p_nom', {60.: ['ga'], 50.: ['gb']})]:
        out = statistics_value(n, 'supply', components=['Generator'], groupby=group)
        for label, assets in labels.items():
            assert_close(out.loc[('Generator', label)],
                         (p[assets].sum(axis=1)*weights).sum())
    out = statistics_value(n, 'supply', components=['Generator'], groupby=statistics_regions)
    assert_close(out.loc[('Generator', 'shared')], expected)
    raw = statistics_value(n, 'supply', components=['Generator'],
                           groupby_time=False, carrier='fuel')
    assert_close(raw.loc[('Generator', 'ga'), n.snapshots], p['ga'])
    mean = statistics_value(n, 'supply', components=['Generator'], groupby_time='mean')
    assert_close(mean.loc[('Generator', 'ga')], (p['ga']*weights).sum()/weights.sum())
    kept = statistics_value(n, 'supply', components=['Generator'])
    assert_close(kept.loc[('Generator', 'zero')], 0)
    dropped = n.statistics.supply(components=['Generator'], groupby=False)
    assert set(dropped.index) == {('Generator', 'ga'), ('Generator', 'gb')}
    combined = statistics_value(n, 'supply', components=['Generator', 'Link'],
                                groupby='bus_carrier', at_port='all',
                                aggregate_across_components=True)
    assert_close(combined.loc['heat'], (n.c.loads.dynamic.p['lh']*weights).sum())
    filtered = statistics_value(n, 'supply', components=['Link'], bus_carrier='heat')
    assert_close(filtered.loc[('Link', 'convert')], (n.c.loads.dynamic.p['lh']*weights).sum())
    primary = statistics_value(n, 'supply', components=['Link'], at_port='bus0',
                               bus_carrier='AC')
    assert_close(primary.loc[('Link', 'convert')], 0)
    # Capacity defaults to the primary-port magnitude; a bus-carrier filter
    # considers the conversion output port with its coefficient.
    capacity = statistics_value(n, 'installed_capacity', components=['Link'])
    assert_close(capacity.loc[('Link', 'convert')], 30)
    heat = statistics_value(n, 'installed_capacity', components=['Link'], bus_carrier='heat')
    assert_close(heat.loc[('Link', 'convert')], 15)
    assert_close(heat.get(('Link', 'wire'), 0), 0)
    n.set_scenarios({'dry': .4, 'wet': .6})
    n.c.generators.static.loc[('wet', 'ga'), 'p_nom'] = 73
    capacity = statistics_value(n, 'installed_capacity', components=['Generator'])
    assert_close(capacity.loc[('Generator', 'dry', 'ga')], 60)
    assert_close(capacity.loc[('Generator', 'wet', 'ga')], 73)


def test_prices_and_signed_transmission(statistics_network):
    n = statistics_network
    for weighting in ['load', 'time']:
        actual = n.statistics.prices(groupby=False, weighting=weighting)
        for bus in ['a', 'b', 'h']:
            assert_close(actual.loc[bus], price_oracle(n, [bus], weighting == 'load'))
        grouped = n.statistics.prices(groupby='bus_carrier', weighting=weighting)
        assert_close(grouped.loc['AC'], price_oracle(n, ['a', 'b'], weighting == 'load'))
    assert_close(n.statistics.prices(groupby=False).loc['a'], price_oracle(n, ['a'], True))
    raw = n.statistics.prices(groupby=False, groupby_time=False)
    assert_close(raw.loc['a', n.snapshots], n.c.buses.dynamic.marginal_price['a'])
    out = statistics_value(n, 'transmission', at_port='all', groupby=['name', port_labels])
    assert set(out.index) == {('Link', 'wire', '0'), ('Link', 'wire', '1')}
    flow = n.c.links.dynamic.p0['wire']
    total = (flow*n.snapshot_weightings.generators).sum()
    assert_close(out.loc[('Link', 'wire', '0')], total)
    assert_close(out.loc[('Link', 'wire', '1')], -total)


def test_labeled_collection_selection_grouping_and_live_members():
    members = []
    for capacity in [11, 19, 31]:
        n = dispatch_bus([3, 5], [0, 1])
        n.add('Generator', 'asset', bus='sink', carrier='fuel', p_nom=capacity,
              marginal_cost=2)
        n.set_scenarios({'dry': .3, 'wet': .7})
        n.c.generators.static.loc[('wet', 'asset'), 'p_nom'] = capacity+4
        members.append(n)
    labels = pd.MultiIndex.from_tuples([('north', 'one'), ('north', 'two'),
                                       ('south', 'three')], names=['region', 'member'])
    collection = NetworkCollection(members, index=labels)
    for label, capacity in zip(labels, [11, 19, 31]):
        assert_close(collection.c.generators.static.loc[(*label, 'dry', 'asset'), 'p_nom'], capacity)
        assert_close(statistics_value(collection, 'installed_capacity').loc[
            ('Generator', *label, 'wet', 'asset')], capacity+4)
        assert_close(collection[label].c.generators.static.loc[('dry', 'asset'), 'p_nom'], capacity)
        assert_close(collection.get_network(label).c.generators.static.loc[
            ('wet', 'asset'), 'p_nom'], capacity+4)
    selected = collection[pd.Series(collection.index.get_level_values('region') == 'north',
                                    index=collection.index)]
    assert set(selected.index) == {('north', 'one'), ('north', 'two')}
    # Member-label grouping is the public pandas Series grouping of the collection.
    grouped = collection.networks.groupby(level='region')
    for region, group in grouped:
        subset = NetworkCollection(group)
        out = statistics_value(subset, 'installed_capacity')
        expected = 30 if region == 'north' else 31
        assert_close(out.xs('dry', level='scenario').sum(), expected)
    # Changes to the caller's own member objects, and to members obtained from
    # the collection, are visible through later collection reads.
    members[0].c.generators.static.loc[('dry', 'asset'), 'p_nom'] = 23
    collection.get_network(('north', 'two')).c.generators.static.loc[
        ('wet', 'asset'), 'p_nom'] = 41
    assert_close(collection.c.generators.static.loc[
        ('north', 'one', 'dry', 'asset'), 'p_nom'], 23)
    capacity = statistics_value(collection, 'installed_capacity')
    assert_close(capacity.loc[('Generator', 'north', 'one', 'dry', 'asset')], 23)
    assert_close(capacity.loc[('Generator', 'north', 'two', 'wet', 'asset')], 41)
    for index in [['short'], ['n1', 'n2', 'n3', 'n4'], labels[:2]]:
        result = invoke(NetworkCollection, members, kwargs={'index': index},
                        expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
