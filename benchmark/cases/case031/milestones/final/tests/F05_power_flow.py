# feature: F05
"""Acceptance tests for static linear and nonlinear electrical analysis."""

import numpy as np
import pandas as pd
import pytest
from velmora import Network

from F03_helpers import electrical_pair
from F05_helpers import flow_network, capture_circuit, circuit_observation, check_ac_balance


def test_linear_ac_dc_taps_phase_and_island_balance():
    n = electrical_pair()
    n.set_snapshots(['low', 'high', 'excluded'])
    n.add('Bus', 'tail', v_nom=110)
    n.add('Line', 'bypass', bus0='west', bus1='tail', r=8, x=20)
    n.add('Transformer', 'step', bus0='east', bus1='tail', x=.1,
          s_nom=100, tap_ratio=1.06, phase_shift=3)
    n.add('Carrier', 'DC')
    n.add('Bus', ['dc-source', 'dc-sink'], v_nom=40, carrier='DC')
    n.add('Line', 'dc-wire', bus0='dc-source', bus1='dc-sink', r=2, x=9)
    n.add('Generator', ['ac-slack', 'dc-slack'], bus=['west', 'dc-source'],
          control='Slack', p_set=2)
    n.add('Generator', 'local', bus='east', p_set=7)
    n.add('Load', 'ac-demand', bus='tail', p_set=pd.Series([20, 35, 99], index=n.snapshots))
    n.add('Load', 'dc-demand', bus='dc-sink', p_set=pd.Series([6, 11, 99], index=n.snapshots))
    circuit = capture_circuit(n)
    n.lpf(snapshots=['low', 'high'])
    for sn, ac, dc in [('low', 20, 6), ('high', 35, 11)]:
        angle = n.c.buses.dynamic.v_ang.loc[sn]
        magnitude = n.c.buses.dynamic.v_mag_pu.loc[sn]
        np.testing.assert_allclose(magnitude[['west', 'east', 'tail']], 1, atol=1e-12)
        assert angle['west'] == 0
        assert magnitude['dc-source'] == 1
        expected_injection = pd.Series({'west': ac-7, 'east': 7, 'tail': -ac,
                                        'dc-source': dc, 'dc-sink': -dc})
        withdrawals = expected_injection.astype(float) * 0
        for category in ['Line', 'Transformer']:
            c = n.components[category]
            for name, row in circuit[category].iterrows():
                if name == 'dc-wire':
                    expected = 40**2 * (magnitude[row.bus0]-magnitude[row.bus1])/row.r
                elif category == 'Line':
                    expected = 110**2 * (angle[row.bus0]-angle[row.bus1])/row.x
                else:
                    expected = row.s_nom*(angle[row.bus0]-angle[row.bus1]-np.deg2rad(row.phase_shift))/(row.x*row.tap_ratio)
                actual = c.dynamic.p0.at[sn, name]
                np.testing.assert_allclose(actual, expected, atol=1e-6, rtol=0)
                np.testing.assert_allclose(c.dynamic.p1.at[sn, name], -actual, atol=1e-6)
                withdrawals[row.bus0] += actual
                withdrawals[row.bus1] -= actual
        np.testing.assert_allclose(withdrawals, expected_injection, atol=1e-6)
        np.testing.assert_allclose(n.c.buses.dynamic.p.loc[sn, expected_injection.index], expected_injection, atol=1e-6)
        np.testing.assert_allclose(n.c.generators.dynamic.p.loc[sn, ['ac-slack', 'dc-slack', 'local']], [ac-7, dc, 7], atol=1e-6)


def test_nonlinear_terminal_circuits_losses_and_shunts():
    # Each circuit model and tap location needs an electrical observation;
    # keeping them in this planned test avoids collected parameter expansion.
    # None means "not supplied": the oracle then uses the PRD default (central
    # shunt T circuit, tap at the first terminal, ratio one, zero phase shift),
    # never the value the product writes into its own tables.
    for model, side, ratio, shift in [(None, None, None, None), (None, None, 1.04, 4),
                                      ('t', 1, 1.04, 4), ('pi', 0, 1.04, 4), ('pi', 1, 1.04, 4)]:
        n = flow_network()
        supplied = {'model': model, 'tap_side': side, 'tap_ratio': ratio, 'phase_shift': shift}
        for field, value in supplied.items():
            if value is not None:
                n.c.transformers.static.at['step', field] = value
        n.add('ShuntImpedance', 'capacitor', bus='tail', g=.004, b=.012)
        circuit = capture_circuit(n)
        defaults = {'model': 't', 'tap_side': 0, 'tap_ratio': 1., 'phase_shift': 0.}
        for field, value in supplied.items():
            circuit['Transformer'].at['step', field] = defaults[field] if value is None else value
        result = n.pf(snapshots=['light', 'heavy'], x_tol=1e-9)
        assert result['converged'].loc[['light', 'heavy']].to_numpy().all()
        for sn in ['light', 'heavy']:
            _, terminals = check_ac_balance(n, sn, circuit)
            for s0, s1 in terminals.values():
                assert (s0+s1).real > 0
            v = n.c.buses.dynamic.v_mag_pu.at[sn, 'tail']
            np.testing.assert_allclose(n.c.shunt_impedances.dynamic.p.at[sn, 'capacitor'], .004*v*v, atol=1e-6)
            # The public shunt q carrier uses positive injection for b > 0.
            np.testing.assert_allclose(n.c.shunt_impedances.dynamic.q.at[sn, 'capacitor'], .012*v*v, atol=1e-6)
            assert n.c.loads.dynamic.p.at[sn, 'demand'] == {'light': .18, 'heavy': .27}[sn]
            assert n.c.loads.dynamic.q.at[sn, 'demand'] == .055


def test_bus_controls_precedence_prescriptions_and_voltage_targets():
    n = flow_network()
    n.add('Generator', 'fixed-east', bus='east', p_set=.015, q_set=.009)
    n.add('Generator', 'fixed-west', bus='west', control='PV', p_set=.012)
    n.add('Generator', 'fixed-tail', bus='tail', p_set=.008, q_set=.004)
    n.c.buses.static.loc[['west', 'east'], 'v_mag_pu_set'] = [1.03, 1.01]
    circuit = capture_circuit(n)
    r = n.pf(snapshots=['light', 'heavy'])
    assert r['converged'].to_numpy().all()
    assert n.c.buses.static.loc[['west', 'east', 'tail'], 'control'].tolist() == ['Slack', 'PV', 'PQ']
    for sn in ['light', 'heavy']:
        check_ac_balance(n, sn, circuit)
        np.testing.assert_allclose(n.c.buses.dynamic.v_mag_pu.loc[sn, ['west', 'east']], [1.03, 1.01], atol=1e-6)
        assert n.c.buses.dynamic.v_ang.at[sn, 'west'] == 0
        for name, p in [('regulated', .06), ('fixed-east', .015), ('fixed-west', .012), ('fixed-tail', .008)]:
            np.testing.assert_allclose(n.c.generators.dynamic.p.at[sn, name], p, atol=1e-6)
        np.testing.assert_allclose(n.c.generators.dynamic.q.loc[sn, ['fixed-east', 'fixed-tail']], [.009, .004], atol=1e-6)
        np.testing.assert_allclose(n.c.buses.dynamic.p.at[sn, 'tail'], .008-n.c.loads.dynamic.p.at[sn, 'demand'], atol=1e-6)
        np.testing.assert_allclose(n.c.buses.dynamic.q.at[sn, 'tail'], .004-.055, atol=1e-6)


def test_distributed_slack_all_participation_forms_and_zero_capacity():
    for mode in ['p_set', 'p_nom', 'p_nom_opt', 'bus', 'generator']:
        n = flow_network()
        # 'additional' shares the west bus with 'reference': bus-level shares
        # (supplied bus weights, optimised capacity) are divided between them
        # in proportion to nominal capacity 2:5, as FP-05.04 states.
        n.add('Generator', 'additional', bus='west', p_set=.02)
        names = ['reference', 'regulated', 'additional']
        n.c.generators.static.loc[names, 'p_nom'] = [2, 3, 5]
        n.c.generators.static.loc[names, 'p_nom_opt'] = [6, 1, 3]
        n.c.generators.dynamic.p_set['regulated'] = [.06, .08, .06]
        n.determine_network_topology()
        subnet = n.c.buses.static.at['west', 'sub_network']
        weights = mode
        if mode == 'bus':
            weights = {subnet: pd.Series({'west': .7, 'east': .3, 'tail': 0.})}
        elif mode == 'generator':
            weights = {subnet: pd.Series([.1, .7, .2], index=pd.Index(names, name='name'))}
        circuit = capture_circuit(n)
        r = n.pf(snapshots=['light', 'heavy'], distribute_slack=True, slack_weights=weights, x_tol=1e-9)
        assert r['converged'].to_numpy().all()
        for sn in ['light', 'heavy']:
            check_ac_balance(n, sn, circuit)
            prescribed = np.array([.04, .06 if sn == 'light' else .08, .02])
            increment = n.c.generators.dynamic.p.loc[sn, names].to_numpy() - prescribed
            assert increment.sum() > .01
            expected = {'p_set': prescribed/prescribed.sum(), 'p_nom': [.2, .3, .5],
                        'p_nom_opt': [.9*2/7, .1, .9*5/7], 'bus': [.2, .3, .5],
                        'generator': [.1, .7, .2]}[mode]
            np.testing.assert_allclose(increment/increment.sum(), expected, atol=1e-6, rtol=0)
    for mode in ['p_nom', 'p_nom_opt']:
        n = flow_network()
        n.c.generators.static[mode] = 0.
        with pytest.raises(ValueError):
            n.pf(distribute_slack=True, slack_weights=mode)


def test_convergence_and_independent_remaining_mismatch():
    n = electrical_pair()
    n.c.buses.static['v_nom'] = 1.
    n.c.lines.static.loc['circuit', ['r', 'x']] = [.1, .5]
    n.add('Bus', ['other-source', 'other-sink'])
    n.add('Line', 'other-line', bus0='other-source', bus1='other-sink', r=.1, x=.5)
    n.set_snapshots(['feasible', 'infeasible', 'excluded'])
    n.add('Generator', ['reference', 'other-reference'], bus=['west', 'other-source'], control='Slack')
    n.add('Load', 'demand', bus='east', p_set=pd.Series([.1, .85, .1], index=n.snapshots), q_set=.05)
    n.add('Load', 'other-demand', bus='other-sink', p_set=.08, q_set=.02)
    circuit = capture_circuit(n)
    for kwargs, tolerance in [({}, 1e-6), ({'x_tol': 1e-8}, 1e-8)]:
        r = n.pf(snapshots=['feasible', 'infeasible'], **kwargs)
        groups = n.c.buses.static.sub_network
        assert set(r['converged'].index) == {'feasible', 'infeasible'}
        assert set(r['converged'].columns) == set(groups)
        for sn in ['feasible', 'infeasible']:
            calculated, _ = circuit_observation(n, sn, circuit)
            for sink, demand, reactive in [('east', .1 if sn == 'feasible' else .85, .05), ('other-sink', .08, .02)]:
                mismatch = calculated[sink] + complex(demand, reactive)
                residual = max(abs(mismatch.real), abs(mismatch.imag))
                reported = r['error'].at[sn, groups[sink]]
                failed_case = sink == 'east' and sn == 'infeasible'
                if np.isfinite(residual):
                    np.testing.assert_allclose(reported, residual, rtol=1e-6, atol=1e-10)
                    assert bool(r['converged'].at[sn, groups[sink]]) == (residual < tolerance)
                    if failed_case:
                        assert residual > tolerance
                    else:
                        assert residual < tolerance
                else:
                    # Divergence may exhaust finite arithmetic. It must remain
                    # an explicit failed result, never a fabricated small error.
                    assert failed_case
                    assert not np.isfinite(reported)
                    assert not bool(r['converged'].at[sn, groups[sink]])
    # A meshed circuit checks both default and requested tolerances using
    # independent residuals. Impedances keep cancellation below the reporting
    # accuracy while requiring further refinement at the tighter tolerance.
    n = Network()
    n.add('Carrier', 'AC')
    n.add('Bus', ['station', 'coupler', 'feeder'], v_nom=380)
    n.add('Line', 'busbar-1', bus0='station', bus1='coupler', r=4., x=40.)
    n.add('Line', 'busbar-2', bus0='coupler', bus1='feeder', r=5., x=50.)
    n.add('Line', 'busbar-3', bus0='station', bus1='feeder', r=7., x=70.)
    n.set_snapshots(['day', 'night'])
    n.add('Generator', 'grid', bus='station', control='Slack', p_set=0.)
    n.add('Load', 'city', bus='feeder', p_set=pd.Series([310., 170.], index=n.snapshots), q_set=60)
    n.add('Load', 'works', bus='coupler', p_set=140., q_set=25)
    circuit = capture_circuit(n)
    for kwargs, tolerance in [({}, 1e-6), ({'x_tol': 1e-8}, 1e-8)]:
        r = n.pf(**kwargs)
        for sn in ['day', 'night']:
            balance, _ = circuit_observation(n, sn, circuit)
            residuals = []
            for bus, demand in [('feeder', complex({'day': 310., 'night': 170.}[sn], 60)),
                                ('coupler', complex(140., 25))]:
                mismatch = balance[bus] + demand
                residuals.extend([abs(mismatch.real), abs(mismatch.imag)])
            residual = np.max(residuals)
            reported = r['error'].loc[sn].max()
            if np.isfinite(residual):
                np.testing.assert_allclose(reported, residual, rtol=1e-6, atol=1e-10)
                assert bool(r['converged'].loc[sn].all()) == (residual < tolerance)
            else:
                assert not np.isfinite(reported)
                assert not r['converged'].loc[sn].to_numpy().any()
            if not kwargs:
                check_ac_balance(n, sn, circuit)
                assert residual < tolerance
                assert r['converged'].loc[sn].to_numpy().all()


def test_explicit_and_automatic_slack_identity_and_residual():
    for method in ['lpf', 'pf']:
        for explicit in [True, False]:
            n = electrical_pair()
            n.c.buses.static['v_nom'] = 1.
            n.c.lines.static.loc['circuit', ['r', 'x']] = [.02, .15]
            n.set_snapshots(['first', 'second'])
            n.add('Generator', 'one', bus='west', p_set=.03,
                  **({'control': 'Slack'} if explicit else {}))
            n.add('Generator', 'two', bus='east', p_set=.04)
            n.add('Load', 'demand', bus='east', p_set=pd.Series([.15, .24], index=n.snapshots), q_set=.03)
            circuit = capture_circuit(n)
            getattr(n, method)()
            subnet = n.c.buses.static.at['west', 'sub_network']
            selected = n.c.sub_networks.static.at[subnet, 'obj'].slack_generator
            assert selected in {'one', 'two'}
            if explicit:
                assert selected == 'one'
            bus = n.c.generators.static.at[selected, 'bus']
            other = ({'one', 'two'} - {selected}).pop()
            for sn, demand in [('first', .15), ('second', .24)]:
                assert n.c.buses.dynamic.v_ang.at[sn, bus] == 0
                np.testing.assert_allclose(n.c.buses.dynamic.v_mag_pu.at[sn, bus], 1., atol=1e-6)
                target_other = {'one': .03, 'two': .04}[other]
                np.testing.assert_allclose(n.c.generators.dynamic.p.at[sn, other], target_other, atol=1e-6)
                loss = 0.
                if method == 'pf':
                    _, terminals = check_ac_balance(n, sn, circuit)
                    loss = sum((s0+s1).real for s0, s1 in terminals.values())
                np.testing.assert_allclose(n.c.generators.dynamic.p.at[sn, selected], demand+loss-target_other, atol=1e-6)
