# feature: F02
"""Acceptance checks for time axes, scenarios, and characteristic data."""

import numpy as np
import pandas as pd
from velmora import Network

from _helpers import invoke, read_table


def test_series_alignment_precedence_and_results():
    n = Network()
    n.set_snapshots(['early', 'middle', 'late'])
    n.add('Bus', 'hub')
    n.add('Generator', 'supply', bus='hub', control='Slack')
    n.add('Load', ['fixed', 'varying'], bus='hub', p_set=[7, 99])
    # Attach labeled input through the public add entry.
    values = pd.DataFrame({'varying': [3, 5, 8]}, index=n.snapshots)
    n.add('Load', ['varying'], bus='hub', p_set=values, overwrite=True)
    n.c.loads.static.at['varying', 'p_set'] = 99
    n.lpf()
    assert n.c.loads.dynamic.p_set.loc[n.snapshots, 'varying'].tolist() == [3, 5, 8]
    assert n.c.loads.dynamic.p.loc[n.snapshots, 'varying'].tolist() == [3, 5, 8]
    assert n.c.loads.dynamic.p.loc[n.snapshots, 'fixed'].tolist() == [7, 7, 7]
    assert n.c.generators.dynamic.p.loc[n.snapshots, 'supply'].tolist() == [10, 12, 15]
    assert n.c.loads.static.at['varying', 'p_set'] == 99
    n.c.loads.dynamic.p.loc[:, 'varying'] = 42
    assert n.c.loads.dynamic.p_set['varying'].tolist() == [3, 5, 8]
    for bad in (
        pd.DataFrame({'bad': [1, 2, 3]}, index=n.snapshots),
        pd.DataFrame({'new': [1, 2, 3]}, index=['early', 'middle', 'absent']),
        np.ones((2, 2)),
    ):
        result = invoke(n.add, 'Load', ['new'], kwargs={'bus': 'hub', 'p_set': bad},
                        expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
        assert 'new' not in n.c.loads.static.index
    for bad in ([1, 2], pd.Series([1, 2, 3], index=['early', 'middle', 'absent'])):
        result = invoke(n.add, 'Load', 'single', kwargs={'bus': 'hub', 'p_set': bad},
                        expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
        assert 'single' not in n.c.loads.static.index
    assert n.c.loads.dynamic.p_set['varying'].tolist() == [3, 5, 8]


def test_snapshot_weight_columns_and_elapsed_hours():
    times = pd.to_datetime(['2024-01-01 00:00', '2024-01-01 01:30',
                            '2024-01-01 05:00'])
    n = Network()
    n.set_snapshots(times)
    columns = ['objective', 'generators', 'stores']
    assert (read_table(n.snapshot_weightings, columns=columns) == 1).all().all()
    n.snapshot_weightings = pd.DataFrame({'objective': [2, 3, 4],
                                          'generators': [5, 6, 7],
                                          'stores': [8, 9, 10]}, index=n.snapshots)
    for column, expected in zip(columns, ([2, 3, 4], [5, 6, 7], [8, 9, 10])):
        assert n.snapshot_weightings[column].tolist() == expected
    n.set_snapshots(times, weightings_from_timedelta=True)
    for column in columns:
        assert n.snapshot_weightings[column].tolist() == [1.5, 3.5, 3.5]
    common = Network()
    common.set_snapshots(times, default_snapshot_weightings=2.5)
    assert (common.snapshot_weightings[columns] == 2.5).all().all()


def test_snapshot_axis_validation():
    n = Network()
    n.set_snapshots(['night', 'day'])
    assert n.snapshots.tolist() == ['night', 'day']
    n.name = 'unchanged study'
    n.meta = {'study': {'revision': 3}}
    n.add('Bus', 'hub', v_nom=66)
    n.add('Load', 'demand', bus='hub', p_set=[4, 9], q_set=[2, 3])
    n.add('Generator', 'plant', bus='hub', p_nom=17, p_max_pu=[.2, .8])
    n.snapshot_weightings.loc[:, ['objective', 'generators', 'stores']] = [[2, 3, 5], [7, 11, 13]]
    previous_axis = n.snapshots.copy()
    previous_weights = n.snapshot_weightings.copy(deep=True)
    previous_static = {c: n.c[c].static.copy(deep=True) for c in ['Bus', 'Load', 'Generator']}
    previous_series = {(c, attr): n.c[c].dynamic[attr].copy(deep=True)
                       for c, attr in [('Load', 'p_set'), ('Load', 'q_set'), ('Generator', 'p_max_pu')]}
    for invalid in ([], pd.date_range('2024-01-01', periods=2, tz='UTC'),
                    pd.MultiIndex.from_product([[2030], ['a'], ['x']]),
                    pd.MultiIndex.from_arrays([['a', 'b']])):
        result = invoke(n.set_snapshots, invalid, expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
        assert n.snapshots.equals(previous_axis)
        pd.testing.assert_frame_equal(n.snapshot_weightings, previous_weights,
                                      check_dtype=False, check_names=False, check_freq=False, check_index_type=False,
                                      check_column_type=False, check_frame_type=False)
        for c, table in previous_static.items():
            pd.testing.assert_frame_equal(n.c[c].static, table, check_dtype=False,
                                          check_names=False, check_like=True, check_index_type=False,
                                          check_column_type=False, check_frame_type=False)
        for (c, attr), table in previous_series.items():
            pd.testing.assert_frame_equal(n.c[c].dynamic[attr], table, check_dtype=False,
                                          check_names=False, check_like=True, check_freq=False,
                                          check_index_type=False, check_column_type=False, check_frame_type=False)
        assert n.name == 'unchanged study'
        assert n.meta == {'study': {'revision': 3}}
    n.set_snapshots(pd.MultiIndex.from_product([[2030, 2040], ['a', 'b']]))
    assert n.snapshots.tolist() == [(2030, 'a'), (2030, 'b'), (2040, 'a'), (2040, 'b')]


def test_investment_period_replication_and_validation():
    n = Network()
    n.set_snapshots(['a', 'b'])
    n.add('Bus', 'hub')
    n.add('Load', 'demand', bus='hub', p_set=[4, 9])
    n.snapshot_weightings.loc[:, 'objective'] = [3, 7]
    n.snapshot_weightings.loc[:, 'generators'] = [2, 5]
    n.snapshot_weightings.loc[:, 'stores'] = [6, 8]
    before = n.snapshot_weightings.copy()
    n.set_investment_periods([2030, 2040])
    assert n.snapshots.tolist() == [(2030, 'a'), (2030, 'b'), (2040, 'a'), (2040, 'b')]
    for period in [2030, 2040]:
        assert n.c.loads.dynamic.p_set.loc[period, 'demand'].tolist() == [4, 9]
        assert n.snapshot_weightings.loc[period].to_numpy().tolist() == before.to_numpy().tolist()
    assert (n.investment_period_weightings.loc[[2030, 2040], ['objective', 'years']] == 1).all().all()
    n.investment_period_weightings.loc[:, 'years'] = [10, 15]
    n.set_investment_periods([2030, 2040])
    n.set_investment_periods([])
    assert n.c.loads.dynamic.p_set['demand'].tolist() == [4, 9, 4, 9]
    assert n.investment_period_weightings['years'].tolist() == [10, 15]
    assert n.snapshot_weightings.to_numpy().tolist() == before.to_numpy().tolist() * 2
    for invalid in ([2030, 2030], [2040, 2030], [2030.5, 2040.5], ['2030', '2040'], [2030, 2050]):
        result = invoke(n.set_investment_periods, invalid, expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
        assert n.snapshots.tolist() == [(2030, 'a'), (2030, 'b'), (2040, 'a'), (2040, 'b')]
    flat = Network()
    flat.set_snapshots(['a', 'b'])
    flat.add('Bus', 'hub')
    flat.add('Load', 'demand', bus='hub', p_set=[4, 9])
    for invalid in ([2030, 2030], [2040, 2030], [2030.5, 2040.5]):
        result = invoke(flat.set_investment_periods, invalid, expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
        assert flat.snapshots.tolist() == ['a', 'b']
        assert flat.c.loads.dynamic.p_set['demand'].tolist() == [4, 9]
    result = invoke(n.set_investment_periods, [2030], expected_exceptions=(NotImplementedError,))
    assert isinstance(result.exception, NotImplementedError)


def test_scenario_probabilities_replication_and_replacement():
    n = Network()
    n.set_snapshots(['a', 'b'])
    n.add('Bus', 'hub')
    n.add('Generator', 'g', bus='hub', p_nom=17, p_max_pu=[0.2, 0.8])
    n.set_scenarios(['dry', 'wet', 'normal'])
    assert set(n.scenarios) == {'dry', 'wet', 'normal'}
    for scenario in ['dry', 'wet', 'normal']:
        assert n.scenario_weightings.at[scenario, 'weight'] == 1 / 3
        assert n.c.generators.static.at[(scenario, 'g'), 'p_nom'] == 17
        assert n.c.generators.dynamic.p_max_pu[(scenario, 'g')].tolist() == [0.2, 0.8]
    n.c.generators.static.at[('wet', 'g'), 'p_nom'] = 23
    n.c.generators.dynamic.p_max_pu.loc['a', ('wet', 'g')] = 0.4
    assert n.c.generators.static.at[('dry', 'g'), 'p_nom'] == 17
    assert n.c.generators.dynamic.p_max_pu.at['a', ('dry', 'g')] == 0.2
    result = invoke(n.set_scenarios, ['new'], expected_exceptions=(NotImplementedError,))
    assert isinstance(result.exception, NotImplementedError)
    assert set(n.scenarios) == {'dry', 'wet', 'normal'}
    assert n.c.generators.static.at[('wet', 'g'), 'p_nom'] == 23
    assert n.c.generators.dynamic.p_max_pu.at['a', ('wet', 'g')] == 0.4
    for probabilities in ({'a': 0.2, 'b': 0.8}, {'a': 0.2, 'b': 0.800009},
                          {'a': 0.2, 'b': 0.799991}):
        other = Network()
        other.set_scenarios(probabilities)
        for name, weight in probabilities.items():
            assert other.scenario_weightings.at[name, 'weight'] == weight
    for probabilities in ({'a': 0.2, 'b': 0.800011}, {'a': 0.2, 'b': 0.799989}):
        refused = Network()
        result = invoke(refused.set_scenarios, probabilities, expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
        assert not refused.has_scenarios
        refused.set_scenarios({'a': 0.3, 'b': 0.7})
        assert refused.scenario_weightings.loc[['a', 'b'], 'weight'].tolist() == [0.3, 0.7]


def test_scenario_extraction_and_time_selection_are_independent():
    n = Network()
    n.set_snapshots(['a', 'b', 'c'])
    n.add('Bus', 'hub')
    n.add('Load', 'd', bus='hub', p_set=[2, 5, 9])
    n.set_investment_periods([2030, 2040])
    n.snapshot_weightings.loc[:, 'stores'] = [1, 2, 3, 4, 5, 6]
    n.investment_period_weightings.loc[:, 'objective'] = [7, 11]
    n.investment_period_weightings.loc[:, 'years'] = [10, 20]
    n.set_scenarios({'low': 0.4, 'high': 0.6})
    n.c.loads.static.at[('high', 'd'), 'p_set'] = 19
    n.c.loads.dynamic.p_set.loc[:, ('high', 'd')] = [3, 6, 10, 4, 8, 12]
    selected = n.get_scenario('high')
    assert not selected.has_scenarios
    assert selected.c.loads.static.at['d', 'p_set'] == 19
    assert selected.c.loads.dynamic.p_set['d'].tolist() == [3, 6, 10, 4, 8, 12]
    assert selected.investment_period_weightings['objective'].tolist() == [7, 11]
    assert selected.investment_period_weightings['years'].tolist() == [10, 20]
    assert selected.snapshot_weightings['stores'].tolist() == [1, 2, 3, 4, 5, 6]
    for positions, rows, values, weights, periods in (
        ([1, 4], [(2030, 'b'), (2040, 'b')], [6, 8], [2, 5], [2030, 2040]),
        ([3, 4, 5], [(2040, 'a'), (2040, 'b'), (2040, 'c')], [4, 8, 12], [4, 5, 6], [2040]),
    ):
        sliced = selected.slice_network(snapshots=positions)
        assert sliced.snapshots.tolist() == rows
        assert sliced.c.loads.dynamic.p_set['d'].tolist() == values
        assert sliced.snapshot_weightings['stores'].tolist() == weights
        assert sliced.periods.tolist() == periods
        assert sliced.c.loads.static.at['d', 'p_set'] == 19
        sliced.c.loads.dynamic.p_set.loc[:, 'd'] = 77
        assert selected.c.loads.dynamic.p_set['d'].tolist() == [3, 6, 10, 4, 8, 12]
    selected.c.loads.static.at['d', 'p_set'] = 41
    selected.c.loads.dynamic.p_set.loc[:, 'd'] = 88
    selected.snapshot_weightings.loc[:, 'stores'] = 90
    selected.investment_period_weightings.loc[:, 'years'] = 99
    assert n.c.loads.static.at[('high', 'd'), 'p_set'] == 19
    assert n.c.loads.dynamic.p_set[('high', 'd')].tolist() == [3, 6, 10, 4, 8, 12]
    assert n.c.loads.dynamic.p_set[('low', 'd')].tolist() == [2, 5, 9, 2, 5, 9]
    assert n.snapshot_weightings['stores'].tolist() == [1, 2, 3, 4, 5, 6]
    assert n.investment_period_weightings['years'].tolist() == [10, 20]


def test_piecewise_characteristics_preserve_breakpoint_pairs():
    n = Network()
    n.add('Bus', ['a', 'b'])
    for component, kwargs, attribute in (
        ('Generator', {'bus': 'a', 'p_nom': 20}, 'marginal_cost'),
        ('Link', {'bus0': 'a', 'bus1': 'b', 'p_nom': 20}, 'efficiency'),
        ('Process', {'bus0': 'a', 'bus1': 'b', 'p_nom': 20}, 'rate1'),
    ):
        curves = {'long': [(1.0, 0.9), (0.0, 0.0), (0.4, 0.6)],
                  'short': [(1.0, 0.7), (0.0, 0.0)]}
        for name, pairs in curves.items():
            n.add(component, name, **kwargs, **{attribute: dict(pairs)})
        table = n.c[component].piecewise[attribute]
        for name, pairs in curves.items():
            stored = table[name][['p_pu', attribute]].dropna(how='all')
            assert not stored.isna().any().any()
            assert sorted(map(tuple, stored.to_numpy())) == sorted(pairs)
    # The represented curve, not the input order, determines optimisation results.
    outcomes = []
    for curve in ({0: 0, 0.2: 8, 0.6: 2, 1: 20}, {0.6: 2, 1: 20, 0: 0, 0.2: 8}):
        m = Network()
        m.set_snapshots(['now'])
        m.add('Bus', 'sink')
        m.add('Load', 'demand', bus='sink', p_set=8)
        m.add('Generator', 'backup', bus='sink', p_nom=100, marginal_cost=5)
        m.add('Generator', 'asset', bus='sink', p_nom=10, marginal_cost=curve)
        result = invoke(m.optimize, kwargs={'solver_name': 'highs',
                                            'solver_options': {'threads': 1}})
        assert result.value == ('ok', 'optimal')
        outcomes.append((m.c.generators.dynamic.p.loc['now', 'asset'],
                         m.c.generators.dynamic.p.loc['now', 'backup'], m.objective))
    for asset, backup, objective in outcomes:
        assert np.isclose(asset, 6, atol=1e-5)
        assert np.isclose(backup, 2, atol=1e-5)
        assert np.isclose(objective, 34, atol=1e-4)


def test_piecewise_scenario_incompatibility_in_both_orders():
    curve = {1.0: 30, 0.0: 0, 0.5: 12}
    n = Network()
    n.add('Bus', 'hub')
    n.add('Generator', 'g', bus='hub', p_nom=10, marginal_cost=curve)
    assert sorted(n.c.generators.piecewise['marginal_cost']['g']['p_pu'].tolist()) == [0, 0.5, 1]
    result = invoke(n.set_scenarios, ['low', 'high'], expected_exceptions=(NotImplementedError,))
    assert isinstance(result.exception, NotImplementedError)
    other = Network()
    other.add('Bus', 'hub')
    other.set_scenarios(['low', 'high'])
    assert other.scenario_weightings.loc[['low', 'high'], 'weight'].tolist() == [0.5, 0.5]
    result = invoke(other.add, 'Generator', 'g',
                    kwargs={'bus': 'hub', 'p_nom': 10, 'marginal_cost': curve},
                    expected_exceptions=(NotImplementedError,))
    assert isinstance(result.exception, NotImplementedError)


def test_snapshot_resize_preserves_inputs_and_initializes_new_rows():
    for common in (None, 2.5):
        n = Network()
        n.set_snapshots(['a', 'b', 'c'])
        n.add('Bus', 'hub')
        n.add('Load', 'd', bus='hub', p_set=[4, 7, 9])
        n.add('Generator', 'g', bus='hub', p_max_pu=[0.2, 0.6, 0.8])
        n.add('Generator', 'h', bus='hub', efficiency=[0.5, 0.6, 0.7],
              marginal_cost=[11, 12, 13])
        n.snapshot_weightings = pd.DataFrame({'objective': [2, 3, 4], 'generators': [5, 6, 7],
                                              'stores': [8, 9, 10]}, index=n.snapshots)
        kwargs = {} if common is None else {'default_snapshot_weightings': common}
        n.set_snapshots(['c', 'a', 'new'], **kwargs)
        assert n.snapshots.tolist() == ['c', 'a', 'new']
        assert n.c.loads.dynamic.p_set['d'].tolist() == [9, 4, 0]
        assert n.c.generators.dynamic.p_max_pu['g'].tolist() == [0.8, 0.2, 1]
        assert n.c.generators.dynamic.efficiency['h'].tolist() == [0.7, 0.5, 1]
        assert n.c.generators.dynamic.marginal_cost['h'].tolist() == [13, 11, 0]
        for column, expected in [('objective', [4, 2]), ('generators', [7, 5]), ('stores', [10, 8])]:
            assert n.snapshot_weightings[column].tolist() == expected + [1 if common is None else common]
    n = Network()
    old = pd.to_datetime(['2024-02-01 00:00', '2024-02-01 02:00', '2024-02-01 06:00'])
    n.set_snapshots(old, weightings_from_timedelta=True)
    new = pd.to_datetime(['2024-02-01 00:00', '2024-02-01 03:00', '2024-02-01 06:00'])
    n.set_snapshots(new, default_snapshot_weightings=99, weightings_from_timedelta=True)
    for column in ['objective', 'generators', 'stores']:
        assert n.snapshot_weightings[column].tolist() == [3, 3, 3]
