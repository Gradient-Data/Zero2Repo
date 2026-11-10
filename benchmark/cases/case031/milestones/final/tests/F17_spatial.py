# feature: F17
"""Acceptance checks for spatial network aggregation through public accessors."""

import math
import numpy as np
import pandas as pd
import pytest
from velmora import Network
from _helpers import read_table
from F17_helpers import (spatial_pair, aggregate_row, check_two_regions,
                         check_connected_groups, check_nearest_centre_regions)


def test_busmap_remaps_assets_and_removes_internal_branches():
    n = spatial_pair()
    n.add('Bus', ['west2', 'east2'], v_nom=110, x=[0., 2.], y=0.)
    n.add('Line', 'parallel', bus0='east2', bus1='west2', s_nom=50,
          r=.3, x=.6, length=120)
    n.add('Line', 'internal', bus0='west', bus1='west2', r=.1, x=.2, length=10)
    for category in ['Generator', 'Load', 'Store', 'StorageUnit', 'ShuntImpedance']:
        n.add(category, category, bus='west2')
    n.add('Link', 'retained', bus0='west2', bus1='east', bus2='east2', bus3='west',
          length=100, capital_cost=30)
    n.add('Link', 'internal', bus0='west', bus1='west2', bus2='east', length=10)
    mapping = pd.Series({'west': 'W', 'west2': 'W', 'east': 'E', 'east2': 'E'})
    result = n.cluster.spatial.get_clustering_from_busmap(mapping)
    reduced = result.n
    pd.testing.assert_series_equal(result.busmap.sort_index(), mapping.sort_index(), check_names=False, check_dtype=False, check_index_type=False, check_series_type=False)
    assert set(reduced.c.buses.static.index) == {'W', 'E'}
    assert set(result.linemap.index) == {'circuit', 'parallel'}
    assert result.linemap['circuit'] == result.linemap['parallel']
    assert set(reduced.c.lines.static.index) == set(result.linemap)
    assert len(reduced.c.lines.static) == 1
    line = reduced.c.lines.static.loc[result.linemap['circuit']]
    assert {line.bus0, line.bus1} == {'W', 'E'}
    assert line.s_nom == 150
    for category in ['Generator', 'Load', 'Store', 'StorageUnit', 'ShuntImpedance']:
        assert reduced.components[category].static.loc[category, 'bus'] == 'W'
    assert set(reduced.c.links.static.index) == {'retained'}
    assert reduced.c.links.static.loc['retained', ['bus0', 'bus1', 'bus2', 'bus3']].tolist() == ['W', 'E', 'E', 'W']


def test_one_port_aggregation_rules_selection_and_consent():
    n = spatial_pair()
    mapping = pd.Series({'west': 'A', 'east': 'A'})
    for category in ['Generator', 'StorageUnit', 'Store']:
        capacity = 'e_nom' if category == 'Store' else 'p_nom'
        kwargs = {capacity: [10., 30.], capacity + '_min': [2., 4.],
                  capacity + '_max': [20., 80.], 'marginal_cost': [4., 12.],
                  'capital_cost': [100., 300.], 'build_year': [2000, 2010],
                  'lifetime': [20., 40.], 'p_set': [0., 0.]}
        if category == 'Generator':
            kwargs.update(p_min_pu=[.1, .3], p_max_pu=[.5, .9],
                          ramp_limit_up=[.2, .6], ramp_limit_down=[.1, .5],
                          ramp_limit_start_up=[.3, .7], ramp_limit_shut_down=[.4, .8])
        if category == 'Generator':
            kwargs.update(efficiency=[.4, .8], control='PV', weight=[2., 5.])
        if category == 'StorageUnit':
            kwargs.update(max_hours=[2., 6.], inflow=pd.DataFrame([[1., 4.], [2., 6.]], index=n.snapshots, columns=['u', 'v']))
        n.add(category, ['u', 'v'], bus=['west', 'east'], carrier='group', **kwargs)
        for attr in ['p', 'q', 'p_set', 'q_set']:
            n.components[category].dynamic[attr] = pd.DataFrame([[2., 7.], [3., 11.]], index=n.snapshots, columns=['u', 'v'])
    n.add('Generator', ['z1', 'z2'], bus=['west', 'east'], carrier='zero',
          p_nom=0, p_set=0., marginal_cost=[6., 14.], efficiency=[.2, .8])
    n.add('Generator', ['keep1', 'keep2'], bus=['west', 'east'], carrier='keep', p_nom=[5., 7.], p_set=0., control=['Slack', 'PQ'])
    # Populate output series for every asset: sparse output densification in the
    # baseline otherwise creates object columns rejected by pandas during import.
    for attr in ['p', 'q']:
        for asset in ['z1', 'z2', 'keep1', 'keep2']:
            n.c.generators.dynamic[attr][asset] = [0., 0.]
    n.c.generators.dynamic.p_max_pu['z1'] = [.2, .6]
    n.c.generators.dynamic.p_max_pu['z2'] = [.4, .8]
    n.add('Load', ['d1', 'd2'], bus=['west', 'east'], carrier='group',
          p_set=pd.DataFrame({'d1': [2., 3.], 'd2': [7., 11.]}, index=n.snapshots),
          q_set=pd.DataFrame({'d1': [1., 4.], 'd2': [5., 8.]}, index=n.snapshots))
    kwargs = dict(aggregate_generators_weighted=True,
                  aggregate_generators_carriers=['group', 'zero'],
                  aggregate_one_ports=['Store', 'StorageUnit', 'Load'])
    reduced = n.cluster.spatial.get_clustering_from_busmap(mapping, **kwargs).n
    for category in ['Generator', 'StorageUnit', 'Store']:
        row = aggregate_row(reduced.components[category].static, bus='A', carrier='group')
        capacity = 'e_nom' if category == 'Store' else 'p_nom'
        for attr, expected in {capacity: 40., capacity + '_min': 6., capacity + '_max': 100.,
                               'marginal_cost': 10., 'capital_cost': 250., 'build_year': 0., 'lifetime': np.inf}.items():
            assert row[attr] == pytest.approx(expected)
        if category == 'Generator':
            for attr, expected in {'p_min_pu': .25, 'p_max_pu': .8, 'ramp_limit_up': .4,
                                   'ramp_limit_down': .3, 'ramp_limit_start_up': .5,
                                   'ramp_limit_shut_down': .6}.items():
                assert row[attr] == pytest.approx(expected)
        if category == 'Generator':
            assert row.efficiency == pytest.approx(.7)
            assert row.weight == 7
            assert row.control == ''
        if category == 'StorageUnit':
            assert row.max_hours == 5
            np.testing.assert_allclose(reduced.c.storage_units.dynamic.inflow[row.name], [5., 8.])
        for attr in ['p', 'q', 'p_set', 'q_set']:
            np.testing.assert_allclose(reduced.components[category].dynamic[attr][row.name], [9., 14.])
    demand = aggregate_row(reduced.c.loads.static, bus='A', carrier='group')
    np.testing.assert_allclose(reduced.c.loads.dynamic.p_set[demand.name], [9., 14.])
    np.testing.assert_allclose(reduced.c.loads.dynamic.q_set[demand.name], [6., 12.])
    zero = aggregate_row(reduced.c.generators.static, carrier='zero')
    assert zero.marginal_cost == 10
    assert zero.efficiency == pytest.approx(.5)
    np.testing.assert_allclose(reduced.c.generators.dynamic.p_max_pu[zero.name], [.3, .7])
    assert read_table(reduced.c.generators.static, rows=['keep1', 'keep2'], columns=['bus', 'p_nom']).values.tolist() == [['A', 5.], ['A', 7.]]
    # A dynamic bound mixes a time series with a static member value.
    n.c.generators.dynamic.p_max_pu['u'] = [.2, .6]
    reduced = n.cluster.spatial.get_clustering_from_busmap(mapping, **kwargs).n
    row = aggregate_row(reduced.c.generators.static, carrier='group')
    np.testing.assert_allclose(reduced.c.generators.dynamic.p_max_pu[row.name], [.725, .825])
    custom = dict(kwargs, generator_strategies={'marginal_cost': 'max', 'p_max_pu': 'max'})
    reduced = n.cluster.spatial.get_clustering_from_busmap(mapping, **custom).n
    row = aggregate_row(reduced.c.generators.static, carrier='group')
    assert row.marginal_cost == 12
    np.testing.assert_allclose(reduced.get_switchable_as_dense('Generator', 'p_max_pu')[row.name], [.9, .9])
    n.c.generators.static.at['v', 'p_nom_extendable'] = True
    with pytest.raises(ValueError):
        n.cluster.spatial.get_clustering_from_busmap(mapping, **kwargs)


def test_automatic_bus_groups_and_aggregate_network():
    n = Network()
    names = pd.Index(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'])
    n.add('Bus', names, x=[0, 0, 0, 1, 8, 9, 9, 9], y=[0, 0, 1, 0, 8, 8, 9, 9], v_nom=110)
    edges = list(zip(names[:-1], names[1:]))
    for i, (left, right) in enumerate(edges):
        n.add('Line', str(i), bus0=left, bus1=right, r=.1, x=.2, s_nom=100, length=100)
    geo = n.cluster.spatial.busmap_by_kmeans(pd.Series([1, 2, 1, 3, 1, 2, 1, 1], index=names), n_clusters=2, random_state=18)
    geo_three = n.cluster.spatial.busmap_by_kmeans(pd.Series(1, index=names), n_clusters=3, random_state=18)
    feature = pd.DataFrame({'signal': [0, 0, 0, 0, 10, 10, 10, 10]}, index=names)
    hac = n.cluster.spatial.busmap_by_hac(n_clusters=2, feature=feature)
    strength = n.cluster.spatial.busmap_by_greedy_modularity(n_clusters=2)
    strength_three = n.cluster.spatial.busmap_by_greedy_modularity(n_clusters=3)
    for mapping, count in [(geo, 2), (geo_three, 3), (hac, 2),
                           (strength, 2), (strength_three, 3)]:
        assert mapping.index.is_unique
        assert set(mapping.index) == set(names)
        assert mapping.notna().all()
        assert mapping.nunique() == count
        result = n.cluster.spatial.get_clustering_from_busmap(mapping)
        assert set(result.n.c.buses.static.index) == set(mapping)
        assert len(result.n.c.buses.static) == count
    for mapping in [geo, geo_three]:
        assert mapping['a'] == mapping['b']
        assert mapping['g'] == mapping['h']
    check_two_regions(n.c.buses.static[['x', 'y']], geo)
    # Larger counts: 6 distinct locations, so 3..6 nonempty nearest-centre groups.
    for count in [3, 5, 6]:
        many = n.cluster.spatial.busmap_by_kmeans(pd.Series(1, index=names),
                                                  n_clusters=count, random_state=18)
        assert set(many.index) == set(names) and many.notna().all()
        assert many.nunique() == count
        assert many['a'] == many['b'] and many['g'] == many['h']
        check_nearest_centre_regions(n.c.buses.static[['x', 'y']], many)
    assert {frozenset(hac.index[hac.eq(label)]) for label in hac.unique()} == {frozenset(names[:4]), frozenset(names[4:])}
    check_connected_groups(hac, edges)
    check_connected_groups(strength, edges)
    check_connected_groups(strength_three, edges)
    # A selected connected subnetwork must have complete, exclusive ownership.
    selected = names[1:7]
    subset = n.cluster.spatial.busmap_by_hac(n_clusters=3, buses_i=selected,
                                            feature=feature.loc[selected])
    assert set(subset.index) == set(selected)
    assert subset.index.is_unique and subset.notna().all()
    assert subset.nunique() == 3
    check_connected_groups(subset, edges)


def test_stochastic_spatial_aggregation_is_refused():
    mapping = pd.Series({'west': 'A', 'east': 'B'})
    deterministic = spatial_pair()
    result = deterministic.cluster.spatial.get_clustering_from_busmap(mapping)
    assert set(result.n.c.buses.static.index) == {'A', 'B'}
    assert len(result.n.c.lines.static) == 1
    stochastic = spatial_pair()
    stochastic.set_scenarios({'mild': .4, 'strong': .6})
    with pytest.raises(ValueError):
        stochastic.cluster.spatial.get_clustering_from_busmap(mapping)


def test_bus_and_line_aggregation_rules_and_groupers():
    for capacities, expected in [([10., 30.], [.8, .25, 2009., 35.]),
                                 ([0., 0.], [.7, .2, 2006., 30.])]:
        n = spatial_pair()
        n.add('Bus', 'west2', v_nom=220, x=2., y=2., v_mag_pu_min=.95, v_mag_pu_max=1.05)
        n.c.buses.static.loc['west', ['v_mag_pu_min', 'v_mag_pu_max']] = [.9, 1.1]
        n.add('Line', 'second', bus0='west2', bus1='east', r=.4, x=.8, length=100)
        fields = {'s_nom': capacities, 's_nom_min': [2., 5.], 's_nom_max': [20., 90.],
                  's_max_pu': [.5, .9], 's_min_pu': [.1, .3], 'num_parallel': [2., 3.],
                  'terrain_factor': [1., 3.], 'build_year': [2000, 2012], 'lifetime': [20., 40.],
                  'v_ang_min': [-.5, -.2], 'v_ang_max': [.4, .3], 's_nom_extendable': [False, True]}
        for attr, values in fields.items():
            n.c.lines.static.loc[['circuit', 'second'], attr] = np.asarray(values)
        n.c.lines.dynamic.s_max_pu = pd.DataFrame({'circuit': [.2, .4], 'second': [.6, .8]}, index=n.snapshots)
        mapping = pd.Series({'west': 'A', 'west2': 'A', 'east': 'B'})
        result = n.cluster.spatial.get_clustering_from_busmap(mapping)
        row = result.n.c.buses.static.loc['A']
        np.testing.assert_allclose(row[['x', 'y', 'v_nom', 'v_mag_pu_min', 'v_mag_pu_max']].astype(float), [1., 1., 220., .95, 1.05])
        assert len(result.n.c.lines.static) == 1
        line = result.n.c.lines.static.loc[result.linemap['circuit']]
        for attr, value in {'s_nom': sum(capacities), 's_nom_min': 7., 's_nom_max': 110.,
                             'num_parallel': 5., 'terrain_factor': 2., 's_max_pu': expected[0],
                             's_min_pu': expected[1], 'build_year': expected[2], 'lifetime': expected[3],
                             'v_ang_min': -.2, 'v_ang_max': .3}.items():
            assert line[attr] == pytest.approx(value)
        assert bool(line.s_nom_extendable)
        np.testing.assert_allclose(result.n.c.lines.dynamic.s_max_pu[line.name],
                                   [.5, .7] if capacities[0] else [.4, .6])
        split = n.cluster.spatial.get_clustering_from_busmap(mapping, custom_line_groupers=['build_year'])
        assert len(split.n.c.lines.static) == 2
        assert split.linemap['circuit'] != split.linemap['second']
        for source in ['circuit', 'second']:
            assert split.n.c.lines.static.loc[split.linemap[source], 'build_year'] == n.c.lines.static.loc[source, 'build_year']


def test_geographic_length_electrical_equivalence_and_link_costs():
    n = spatial_pair()
    # Equatorial two-degree arc is independently R * angle, without product geometry.
    n.c.buses.static.loc['east', 'v_nom'] = 220.
    n.c.lines.static.loc['circuit', ['r', 'x', 'g', 'b', 's_nom', 'capital_cost']] = [2., 4., .01, .02, 10., 100.]
    n.add('Line', 'second', bus0='east', bus1='west', r=6., x=12., g=.03, b=.06,
          length=200., s_nom=30., capital_cost=300.)
    n.add('Link', 'transfer', bus0='west', bus1='east', length=80., capital_cost=40.)
    # Only positive original lengths receive the geographic adjustment.
    n.add('Link', 'unmeasured', bus0='west', bus1='east', length=0., capital_cost=40.)
    mapping = pd.Series({'west': 'A', 'east': 'B'})
    geometries = [((0., 0.), (2., 0.), math.pi / 90.),
                  ((0., 30.), (90., 60.), math.acos(math.sin(math.pi / 6.) * math.sin(math.pi / 3.)))]
    for start, end, angle in geometries:
        n.c.buses.static.loc['west', ['x', 'y']] = start
        n.c.buses.static.loc['east', ['x', 'y']] = end
        for options, factor in [({}, 1.), ({'line_length_factor': 1.7}, 1.7)]:
            result = n.cluster.spatial.get_clustering_from_busmap(mapping, **options)
            length = 6371. * angle * factor
            row = result.n.c.lines.static.loc[result.linemap['circuit']]
            # Each independent contribution uses its original input-terminal voltage.
            ratios = np.array([length / 100., length / 200.])
            voltage_squared = np.array([4., 1.])
            expected = {
                'length': length,
                'r': 1. / np.sum(1. / (np.array([2., 6.]) * ratios * voltage_squared)),
                'x': 1. / np.sum(1. / (np.array([4., 12.]) * ratios * voltage_squared)),
                'g': np.sum(np.array([.01, .03]) * ratios / voltage_squared),
                'b': np.sum(np.array([.02, .06]) * ratios / voltage_squared),
                'capital_cost': np.dot([.25, .75], np.array([100., 300.]) * ratios),
            }
            for attr, value in expected.items():
                assert row[attr] == pytest.approx(value)
            link = result.n.c.links.static.loc['transfer']
            assert link.length == pytest.approx(length)
            assert link.capital_cost == pytest.approx(40. * length / 80.)
            other = result.n.c.links.static.loc['unmeasured']
            assert other.length == 0 and other.capital_cost == 40.
            unscaled = n.cluster.spatial.get_clustering_from_busmap(mapping, scale_link_capital_costs=False, **options).n
            assert unscaled.c.links.static.at['transfer', 'capital_cost'] == 40.
            assert unscaled.c.links.static.at['transfer', 'length'] == pytest.approx(length)
