# feature: F03
"""Acceptance checks for consistency, topology, types and seasonal ratings."""

import logging

import numpy as np
import pandas as pd
import pytest
from velmora import Network
from velmora.consistency import ConsistencyError

from _helpers import invoke, read_table
from F03_helpers import electrical_pair, seasonal_pair


def test_consistency_warning_and_selected_refusal():
    # Each input starts from the same valid network. Do not parse diagnostic prose.
    cases = [
        ('unknown_buses', 'Load', 'bus', 'missing', {'bus': 'west'}),
        ('unknown_carriers', 'Generator', 'carrier', 'missing', {'bus': 'west'}),
        ('disconnected_buses', 'Bus', None, None, {}),
        ('zero_impedances', 'Line', 'x', 0.0,
         {'bus0': 'west', 'bus1': 'east', 'r': 0.2, 'x': 0.5}),
        ('zero_impedances', 'Line', 'r', 0.0,
         {'bus0': 'west', 'bus1': 'east', 'r': 0.2, 'x': 0.5}),
        ('static_power_attrs', 'Generator', 'p_nom_min', 20.0,
         {'bus': 'west', 'p_nom_min': 0, 'p_nom_max': 10}),
        ('static_power_attrs', 'Store', 'e_nom_min', 20.0,
         {'bus': 'west', 'e_nom_min': 0, 'e_nom_max': 10}),
        ('time_series_power_attrs', 'Store', 'e_min_pu', 0.9,
         {'bus': 'west', 'e_min_pu': 0.1, 'e_max_pu': 0.8}),
        ('phase_shift_bounds', 'Transformer', 'phase_shift_min', 20.0,
         {'bus0': 'west', 'bus1': 'east', 'r': 0.01, 'x': 0.1,
          's_nom': 10, 'phase_shift_min': -10, 'phase_shift_max': 10}),
    ]
    for check, component, attribute, bad, attributes in cases:
        for mode in ('warn', 'selected', 'unselected'):
            n = electrical_pair()
            if component != 'Bus':
                n.add(component, 'subject', **attributes)
                baseline = invoke(n.consistency_check, kwargs={'strict': [check]})
                n.components[component].static.at['subject', attribute] = bad
            else:
                baseline = invoke(n.consistency_check, kwargs={'strict': [check]})
                n.add('Bus', 'subject')
            assert not any(record.levelno >= logging.WARNING for record in baseline.logs)
            if mode == 'selected':
                with pytest.raises(ConsistencyError):
                    n.consistency_check(strict=[check])
            else:
                # Phase-shift bounds are strict by default in the original.
                kwargs = {} if mode == 'warn' and check != 'phase_shift_bounds' else {
                    'strict': ['unknown_carriers' if check == 'unknown_buses' else 'unknown_buses']
                }
                result = invoke(n.consistency_check, kwargs=kwargs)
                assert any(record.levelno == logging.WARNING for record in result.logs), check
    with pytest.raises(ValueError):
        electrical_pair().consistency_check(strict=['undefined-check'])
    n = electrical_pair()
    n.add('Transformer', 'shift', bus0='west', bus1='east', r=.01, x=.1,
          s_nom=10, phase_shift_min=20, phase_shift_max=10)
    with pytest.raises(ConsistencyError):
        n.consistency_check()


def test_passive_topology_and_oriented_parallel_connections():
    n = electrical_pair()
    n.add('Bus', ['remote', 'island', 'alone'], v_nom=110)
    n.add('Line', 'parallel', bus0='west', bus1='east', r=.3, x=.6)
    n.add('Transformer', 'step', bus0='east', bus1='remote', r=.01, x=.1, s_nom=10)
    n.add('Link', 'controlled', bus0='remote', bus1='island', p_nom=10)
    n.determine_network_topology()
    groups = n.c.buses.static.sub_network
    assert groups['west'] == groups['east'] == groups['remote']
    assert len({groups['west'], groups['island'], groups['alone']}) == 3
    order = pd.Index(['alone', 'remote', 'east', 'west', 'island'])
    adjacency = n.adjacency_matrix(branch_components=['Line', 'Transformer'],
                                   busorder=order, return_dataframe=True)
    expected = pd.DataFrame(0, index=order, columns=order)
    expected.at['west', 'east'] = 1
    expected.at['east', 'remote'] = 1
    np.testing.assert_array_equal(adjacency.loc[order, order], expected)
    # Select a single category so columns correspond to its public static row order.
    for category in ['Line', 'Transformer', 'Link']:
        branches = n.components[category].static
        matrix = n.incidence_matrix(branch_components=[category], busorder=order).toarray()
        expected = np.zeros((len(order), len(branches)))
        for column, (_, row) in enumerate(branches.iterrows()):
            expected[order.get_loc(row.bus0), column] = 1
            expected[order.get_loc(row.bus1), column] = -1
        np.testing.assert_array_equal(matrix, expected)


def test_line_types_scaling_override_and_reapplication():
    n = electrical_pair()
    n.add('LineType', 'custom', r_per_length=.2, x_per_length=.5,
          c_per_length=100, f_nom=50)
    n.add('Line', ['single', 'double', 'long'], bus0='west', bus1='east',
          type='custom', length=[10, 10, 30], num_parallel=[1, 2, 1],
          r=99, x=98, b=97)
    n.calculate_dependent_values()
    values = read_table(n.c.lines.static, rows=['single', 'double', 'long'], columns=['r', 'x', 'b'])
    np.testing.assert_allclose(values, [[2, 5, np.pi/10000],
                                      [1, 2.5, np.pi/5000],
                                      [6, 15, 3*np.pi/10000]])
    n.c.line_types.static.loc['custom', ['r_per_length', 'x_per_length', 'f_nom']] = [.3, .8, 60]
    n.calculate_dependent_values()
    np.testing.assert_allclose(n.c.lines.static.loc['double', ['r', 'x', 'b']].astype(float),
                               [1.5, 4, .00024*np.pi])
    n.c.lines.static.at['single', 'type'] = 'absent-type'
    with pytest.raises(ValueError):
        n.calculate_dependent_values()


def test_transformer_types_quantities_taps_and_reapplication():
    n = electrical_pair()
    n.add('TransformerType', 'custom', s_nom=10, v_nom_0=110, v_nom_1=20,
          vsc=5, vscr=3, pfe=60, i0=1, phase_shift=15,
          tap_side=1, tap_neutral=1, tap_step=2.5)
    n.add('Transformer', ['one', 'two'], bus0='west', bus1='east', type='custom',
          num_parallel=[1, 2], tap_position=[3, -1], r=9, x=8, g=7, b=6,
          s_nom=99, phase_shift=33, tap_ratio=1.8, tap_side=0)
    columns = ['r', 'x', 'g', 'b', 's_nom', 'tap_ratio', 'tap_side', 'phase_shift']
    n.calculate_dependent_values()
    np.testing.assert_allclose(read_table(n.c.transformers.static, rows=['one', 'two'], columns=columns),
                               [[.03, .04, .006, -.008, 10, 1.05, 1, 15],
                                [.015, .02, .012, -.016, 10, .95, 1, 15]])
    n.c.transformer_types.static.loc['custom', ['s_nom', 'vsc', 'vscr', 'pfe', 'i0',
                                               'tap_step', 'tap_side', 'phase_shift']] = [20, 13, 5, 200, .5, 4, 0, -10]
    n.calculate_dependent_values()
    np.testing.assert_allclose(read_table(n.c.transformers.static, rows=['one', 'two'], columns=columns),
                               [[.05, .12, .01, 0, 20, 1.08, 0, -10],
                                [.025, .06, .02, 0, 20, .92, 0, -10]])
    n.c.transformers.static.at['two', 'type'] = 'absent-type'
    with pytest.raises(ValueError):
        n.calculate_dependent_values()


def test_scenario_structural_invariants_and_type_consistency():
    base = electrical_pair()
    base.set_snapshots(['first', 'second', 'third'])
    base.add('Carrier', 'other')
    base.add('Generator', 'plant', bus='west', p_nom=10, marginal_cost=2)
    base.add('Store', 'reservoir', bus='west', e_nom=10)
    base.add('Link', 'transfer', bus0='west', bus1='east', p_nom=10)
    base.add('Transformer', 'transform', bus0='west', bus1='east', r=.01, x=.1, s_nom=10)
    base.add('LineType', 'wire', r_per_length=.2, x_per_length=.4)
    base.add('TransformerType', 'core', s_nom=10, vsc=5, vscr=3)
    base.set_scenarios(['low', 'high'])
    # Operational differences are legal and must not trigger structural rejection.
    base.c.generators.static.at[('high', 'plant'), 'marginal_cost'] = 7
    base.consistency_check(strict=['scenario_invariant_attrs', 'line_types', 'transformer_types'])
    changes = [
        ('Generator', 'plant', 'bus', 'east'),
        ('Line', 'circuit', 'bus0', 'east'),
        ('Link', 'transfer', 'bus1', 'west'),
        ('Line', 'circuit', 'type', 'wire'),
        ('Generator', 'plant', 'carrier', 'other'),
        ('Generator', 'plant', 'sign', -1.),
        ('Generator', 'plant', 'weight', 2.),
        ('Generator', 'plant', 'p_nom_extendable', True),
        ('Line', 'circuit', 's_nom_extendable', True),
        ('Store', 'reservoir', 'e_nom_extendable', True),
        ('Generator', 'plant', 'p_nom_mod', 3.),
        ('Line', 'circuit', 's_nom_mod', 3.),
        ('Store', 'reservoir', 'e_nom_mod', 3.),
        ('Generator', 'plant', 'p_nom_set', 12.),
        ('Line', 'circuit', 's_nom_set', 12.),
        ('Store', 'reservoir', 'e_nom_set', 12.),
        ('Generator', 'plant', 'committable', True),
        ('Generator', 'plant', 'build_year', 2030),
        ('Generator', 'plant', 'lifetime', 25.),
        ('Generator', 'plant', 'active', False),
        ('Link', 'transfer', 'delay', 1.),
        ('Link', 'transfer', 'cyclic_delay', False),
    ]
    for category, name, attribute, value in changes:
        n = base.copy()
        n.components[category].static.at[('high', name), attribute] = value
        with pytest.raises(ConsistencyError):
            n.consistency_check()
    for category, name, attribute, value, check in [
        ('LineType', 'wire', 'r_per_length', .7, 'line_types'),
        ('TransformerType', 'core', 'vsc', 8., 'transformer_types'),
    ]:
        n = base.copy()
        n.components[category].static.at[('high', name), attribute] = value
        # FP-03.04: type differences warn by default, refuse only when selected strict.
        result = invoke(n.consistency_check)
        assert result.exception is None
        assert any(record.levelno == logging.WARNING for record in result.logs), check
        with pytest.raises(ConsistencyError):
            n.consistency_check(strict=[check])


def test_seasonal_months_composition_and_replacement():
    ratings = pd.DataFrame({'summer': [80, 30], 'winter': [120, 60]}, index=['circuit', 'second'])
    for custom, compose in [(False, True), (True, True), (False, False)]:
        n = seasonal_pair()
        # Cover every month in the existing test, retaining season boundaries.
        n.set_snapshots(pd.to_datetime([
            '2025-01-01', '2025-02-01', '2025-03-31', '2025-04-01',
            '2025-05-01', '2025-06-01', '2025-07-01', '2025-08-01',
            '2025-09-30', '2025-10-01', '2025-11-01', '2025-12-01',
        ]))
        n.c.lines.static.at['circuit', 's_max_pu'] = .9
        n.add('Line', 'second', bus0='west', bus1='east', s_nom=50, r=.2, x=.4)
        existing = [.5, .6, .7, .8, .9, .4, .6, .8, .7, .5, .4, .9]
        n.c.lines.dynamic.s_max_pu['second'] = existing
        kwargs = {}
        if custom:
            kwargs['summer_months'] = [2, 7, 11]
        if not compose:
            kwargs['compose'] = False
        n.c.lines.apply_seasonal_rating(ratings, **kwargs)
        ratios = np.array([[1.2, 1.2]] * 3 + [[.8, .6]] * 6 + [[1.2, 1.2]] * 3)
        if custom:
            ratios = np.array([[1.2, 1.2], [.8, .6], [1.2, 1.2], [1.2, 1.2],
                               [1.2, 1.2], [1.2, 1.2], [.8, .6], [1.2, 1.2],
                               [1.2, 1.2], [1.2, 1.2], [.8, .6], [1.2, 1.2]])
        if compose:
            ratios *= np.column_stack(([.9] * len(existing), existing))
        np.testing.assert_allclose(read_table(n.c.lines.dynamic.s_max_pu,
                                             rows=n.snapshots, columns=['circuit', 'second']), ratios)
        assert n.c.lines.static.loc[['circuit', 'second'], 's_nom'].tolist() == [100, 50]


def test_seasonal_validation_refuses_invalid_inputs():
    good = pd.DataFrame({'summer': [80.], 'winter': [120.]}, index=['circuit'])
    n = seasonal_pair()
    n.c.lines.apply_seasonal_rating(good)
    np.testing.assert_allclose(n.c.lines.dynamic.s_max_pu['circuit'], [1.2, .8, .8, 1.2])
    cases = [('snapshots', TypeError), ('line', KeyError),
             ('summer', KeyError), ('winter', KeyError),
             ('zero-summer', ValueError), ('negative-winter', ValueError),
             ('zero-capacity', ValueError), ('negative-capacity', ValueError),
             ('months', ValueError)]
    for defect, exception in cases:
        n = seasonal_pair()
        ratings = good.copy()
        kwargs = {}
        if defect == 'snapshots':
            n.set_snapshots(['early', 'late'])
        elif defect == 'line':
            ratings.index = ['absent-line']
        elif defect in ('summer', 'winter'):
            ratings = ratings.drop(columns=defect)
        elif defect == 'zero-summer':
            ratings.at['circuit', 'summer'] = 0
        elif defect == 'negative-winter':
            ratings.at['circuit', 'winter'] = -1
        elif defect in ('zero-capacity', 'negative-capacity'):
            n.c.lines.static.at['circuit', 's_nom'] = 0 if defect == 'zero-capacity' else -1
        elif defect == 'months':
            kwargs['summer_months'] = []
        with pytest.raises(exception):
            n.c.lines.apply_seasonal_rating(ratings, **kwargs)
