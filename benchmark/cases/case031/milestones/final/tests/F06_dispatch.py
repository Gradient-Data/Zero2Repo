# feature: F06
"""Acceptance checks for deterministic economic dispatch and linear power flow."""
import numpy as np
import pandas as pd
import pytest
from velmora import Network
from _helpers import invoke
from F06_helpers import (dispatch_bus, solve_dispatch, assert_close,
                         conversion_dispatch, asset_dispatch,
                         loss_dispatch, loss_observation)


def test_weighted_selected_horizon_and_quadratic_cost():
    n = dispatch_bus([6, 9, 1000], ('a', 'b', 'outside'))
    n.snapshot_weightings.loc[:, 'objective'] = [2, 5, 99]
    n.add('Generator', 'linear', bus='sink', p_nom=20, marginal_cost=4)
    n.add('Generator', 'quadratic', bus='sink', p_nom=20,
          marginal_cost_quadratic=1)
    solve_dispatch(n, n.snapshots[:2])
    # The independently minimised convex cost is q^2 + 4*(d-q), q=2.
    assert_close(n.c.generators.dynamic.p.loc[['a', 'b'], 'quadratic'], [2, 2], atol=1e-4)
    assert_close(n.c.generators.dynamic.p.loc[['a', 'b'], 'linear'], [4, 7], atol=1e-4)
    assert_close(n.c.buses.dynamic.p.loc[['a', 'b'], 'sink'], 0)
    assert_close(n.objective, 2*20 + 5*32)


def test_dispatch_bounds_targets_signs_and_inactive_assets():
    for component in ('Generator', 'Link', 'Process'):
        for attrs, expected in [({}, 10), ({'p_max_pu': .6}, 6),
                                ({'p_set': 4}, 4), ({'active': False}, 0)]:
            n = conversion_dispatch(component, **attrs)
            solve_dispatch(n)
            assert_close(asset_dispatch(n, component), expected)
            assert_close(n.c.generators.dynamic.p.loc['now', 'backup'], 12-expected)
            assert_close(n.c.buses.dynamic.p.loc['now'], 0)
            assert_close(n.objective, (1 if component == 'Generator' else 2)*expected + 20*(12-expected))
        n = conversion_dispatch(component, p_min_pu=.3)
        n.components[component].static.loc['asset', 'marginal_cost'] = 30
        solve_dispatch(n)
        assert_close(asset_dispatch(n, component), 3)
        for target in [-1, 11]:
            n = conversion_dispatch(component, p_set=target)
            result = invoke(n.optimize, kwargs={'solver_name': 'highs'})
            assert result.value == ('warning', 'infeasible')
    for attributes, expected in [({'sign': -2}, 3), ({'p_min_pu': -1}, -3)]:
        n = dispatch_bus(2)
        n.add('Generator', 'supply', bus='sink', p_nom=100, marginal_cost=1)
        n.add('Generator', 'flex', bus='sink', p_nom=3,
              marginal_cost=-5 if 'sign' in attributes else 5, **attributes)
        solve_dispatch(n)
        assert_close(n.c.generators.dynamic.p.at['now', 'flex'], expected)
        assert_close(n.c.generators.dynamic.p.at['now', 'supply'], 8 if expected > 0 else 5)
        assert_close(n.c.buses.dynamic.p.at['now', 'sink'], 0)


def test_passive_ac_dc_ratings_and_controllable_transfers():
    for carrier, direction, extend in [('AC', 1, False), ('DC', -1, False), ('AC', -1, True)]:
        n = Network()
        n.set_snapshots(['now'])
        n.add('Carrier', carrier)
        n.add('Bus', ['a', 'b'], carrier=carrier, v_nom=1)
        for name, impedance, rating in [('first', .1, 40), ('second', .2, 100)]:
            n.add('Line', name, bus0='a', bus1='b', carrier=carrier,
                  x=impedance, r=impedance, s_nom=rating/2 if extend else rating,
                  s_nom_extendable=extend, s_nom_min=rating, s_nom_max=rating,
                  capital_cost=1 if extend else 0)
        source, sink = ('a', 'b') if direction == 1 else ('b', 'a')
        n.add('Link', 'controlled', bus0=source, bus1=sink, p_nom=7, marginal_cost=5)
        n.add('Generator', 'cheap', bus=source, p_nom=200, marginal_cost=1)
        n.add('Generator', 'dear', bus=sink, p_nom=200, marginal_cost=20)
        n.add('Load', 'demand', bus=sink, p_set=100)
        solve_dispatch(n)
        assert_close(n.c.lines.dynamic.p0.loc['now', ['first', 'second']], direction*np.array([40, 20]))
        assert_close(n.c.lines.dynamic.p1.loc['now'], -n.c.lines.dynamic.p0.loc['now'])
        assert_close(n.c.links.dynamic.p0.at['now', 'controlled'], 7)
        assert_close(n.c.generators.dynamic.p.at['now', 'cheap'], 67)
        assert_close(n.c.generators.dynamic.p.at['now', 'dear'], 33)
        assert_close(n.c.buses.dynamic.p.loc['now', ['a', 'b']], [direction*60, -direction*60])
        if carrier == 'AC':
            assert_close(n.c.buses.dynamic.v_ang.at['now', 'a'] - n.c.buses.dynamic.v_ang.at['now', 'b'], direction*4)


def test_objective_zero_coefficients_absent_cost_and_infeasible():
    n = dispatch_bus(4)
    n.add('Generator', 'free', bus='sink', p_nom=3)
    n.add('Generator', 'paid', bus='sink', p_nom=3, marginal_cost=8)
    solve_dispatch(n)
    assert_close(n.c.generators.dynamic.p.loc['now', ['free', 'paid']], [3, 1])
    assert_close(n.objective, 8)
    n.c.generators.static.loc[:, 'marginal_cost'] = 0
    result = invoke(n.optimize, kwargs={'solver_name': 'highs'}, expected_exceptions=(ValueError,))
    assert isinstance(result.exception, ValueError)
    n.c.generators.static.loc['paid', 'marginal_cost'] = 8
    n.c.loads.static.loc['demand', 'p_set'] = 7
    result = invoke(n.optimize, kwargs={'solver_name': 'highs'})
    assert result.value == ('warning', 'infeasible')


def test_prices_and_capacity_shadow_values():
    # Distinct per-snapshot objective weights: each nodal price has its own
    # snapshot's weight removed (a is set by backup, b by the asset).
    objectives = []
    for demand, capacity in [((12, 6), 10), ((12.01, 6), 10), ((12, 6), 10.01),
                             ((12, 6.01), 10)]:
        n = conversion_dispatch('Generator', demand=list(demand), snapshots=('a', 'b'))
        n.c.generators.static.loc['asset', 'p_nom'] = capacity
        n.snapshot_weightings.loc[:, 'objective'] = [3, 5]
        solve_dispatch(n, assign_all_duals=True)
        objectives.append(n.objective)
        assert_close(n.c.buses.dynamic.marginal_price.loc[['a', 'b'], 'sink'], [20, 1])
        if len(objectives) == 1:
            shadow = n.c.generators.dynamic.mu_upper.at['a', 'asset']
    assert_close((objectives[1]-objectives[0])/.01, 3*20)
    assert_close((objectives[3]-objectives[0])/.01, 5*1)
    assert_close((objectives[2]-objectives[0])/.01, shadow)
    assert_close(shadow, 3*(1-20))


def test_transformer_variable_and_fixed_phase_shift():
    for bounds in [(-6, -2), (-2, -1), (0, 0)]:
        n = Network()
        n.set_snapshots(['now'])
        n.add('Bus', ['a', 'b'], v_nom=1)
        n.add('Line', 'parallel', bus0='a', bus1='b', x=.1, r=.001, s_nom=.2)
        n.add('Transformer', 'shift', bus0='a', bus1='b', x=10, r=.01,
              s_nom=100, phase_shift=1,
              phase_shift_min=bounds[0], phase_shift_max=bounds[1])
        n.add('Generator', 'cheap', bus='a', p_nom=2, marginal_cost=1)
        n.add('Generator', 'dear', bus='b', p_nom=2, marginal_cost=20)
        n.add('Load', 'demand', bus='b', p_set=1)
        solve_dispatch(n)
        phi = n.c.transformers.dynamic.phase_shift_opt.at['now', 'shift']
        line = n.c.lines.dynamic.p0.at['now', 'parallel']
        transformer = n.c.transformers.dynamic.p0.at['now', 'shift']
        assert n.c.transformers.static.at['shift', 'phase_shift'] == 1
        assert_close(.1*(line-transformer), np.deg2rad(phi))
        if bounds[0] < bounds[1]:
            assert bounds[0]-1e-5 <= phi <= bounds[1]+1e-5
            achievable = min(1, .4-np.deg2rad(bounds[0])/.1)
            assert_close(n.c.generators.dynamic.p.at['now', 'cheap'], achievable)
        else:
            assert_close(phi, 1)
            assert_close(line, .2)
            assert_close(n.c.generators.dynamic.p.at['now', 'cheap'], .4-np.deg2rad(1)/.1)


def test_lossless_default_and_loss_balance_and_rating():
    for enabled in [False, True]:
        n = loss_dispatch(99)
        solve_dispatch(n, **({'transmission_losses': True} if enabled else {}))
        flow, loss = loss_observation(n)
        p0 = n.c.lines.dynamic.p0.at['now', 'circuit']
        p1 = n.c.lines.dynamic.p1.at['now', 'circuit']
        assert_close(p0, flow+loss/2)
        assert_close(p1, -flow+loss/2)
        assert_close(n.c.generators.dynamic.p.at['now', 'supply'], p0)
        assert_close(n.c.generators.dynamic.p.at['now', 'local'], 99+p1)
        assert_close(n.c.buses.dynamic.p.loc['now', ['west', 'east']], [p0, p1])
        assert_close(n.objective, 7*p0 + 70*(99+p1))
        if enabled:
            assert loss > 0
            assert_close(abs(flow)+loss, 100)
            assert n.c.generators.dynamic.p.at['now', 'local'] > 0
        else:
            assert_close([flow, loss], [99, 0])


def test_upper_loss_accuracy_defaults_and_tolerances():
    for options, atol, rtol in [(True, 1, .1), ({'mode': 'secants', 'atol': .02, 'rtol': .01}, .02, .01)]:
        for demand in [13, 43, 77]:
            n = loss_dispatch(demand)
            solve_dispatch(n, transmission_losses=options)
            flow, loss = loss_observation(n)
            true_loss = .001*flow**2
            assert -1e-5 <= loss-true_loss <= max(atol, rtol*true_loss)+1e-5
            assert_close(n.c.generators.dynamic.p.at['now', 'supply'], demand+loss)
            assert_close(n.objective, 7*(demand+loss))


def test_lower_loss_accuracy_for_requested_resolution():
    for segments in [1, 4, 9]:
        for demand in [13, 43, 77]:
            n = loss_dispatch(demand)
            solve_dispatch(n, transmission_losses={'mode': 'tangents', 'segments': segments})
            flow, loss = loss_observation(n)
            true_loss = .001*flow**2
            assert -1e-5 <= loss <= true_loss+1e-5
            assert true_loss-loss <= .25*.001*100**2/segments**2+1e-5
            assert_close(n.c.generators.dynamic.p.at['now', 'supply'], demand+loss)
            assert_close(n.objective, 7*(demand+loss))


def test_loss_parameter_validation_and_finite_capacity():
    for options in [{'mode': 'secants', 'atol': 0}, {'mode': 'secants', 'atol': -1},
                    {'mode': 'secants', 'rtol': -.1},
                    {'mode': 'tangents', 'segments': 0}, {'mode': 'tangents', 'segments': -1}]:
        n = loss_dispatch()
        result = invoke(n.optimize, kwargs={'solver_name': 'highs', 'transmission_losses': options}, expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
    for mode in [{'mode': 'secants'}, {'mode': 'tangents', 'segments': 1}]:
        n = loss_dispatch(s_nom_extendable=True, capital_cost=1)
        result = invoke(n.optimize, kwargs={'solver_name': 'highs', 'transmission_losses': mode}, expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
        n.c.lines.static.loc['circuit', 's_nom_max'] = 100
        solve_dispatch(n, transmission_losses=mode)
    n = loss_dispatch()
    solve_dispatch(n, transmission_losses={'mode': 'secants', 'atol': .01, 'rtol': 0})
    flow, loss = loss_observation(n)
    assert 0-1e-5 <= loss-.001*flow**2 <= .01+1e-5


def test_explicit_penalised_load_shedding():
    for enabled in [False, True]:
        n = dispatch_bus(12)
        n.add('Generator', 'supply', bus='sink', p_nom=7, marginal_cost=3)
        if not enabled:
            result = invoke(n.optimize, kwargs={'solver_name': 'highs'})
            assert result.value == ('warning', 'infeasible')
        else:
            names = pd.Index(['sink curtailed'])
            n.optimize.add_load_shedding(suffix=' curtailed', buses=pd.Index(['sink']),
                                        sign=.5, marginal_cost=50, p_nom=100)
            solve_dispatch(n)
            assert_close(n.c.generators.dynamic.p.at['now', 'supply'], 7)
            curtailed = n.c.generators.dynamic.p.loc['now', names]
            assert_close(curtailed*n.c.generators.static.loc[names, 'sign'], 5)
            assert_close(n.objective, 7*3+10*50)
            assert_close(n.c.buses.dynamic.p.at['now', 'sink'], 0)


def test_generator_cumulative_dispatch_selected_weighted_horizon():
    for bounds, expected in [({}, 30), ({'e_sum_max': 15}, 15),
                              ({'e_sum_min': 8}, 8)]:
        n = conversion_dispatch('Generator', snapshots=('a', 'b', 'outside'), **bounds)
        n.snapshot_weightings.loc[:, 'generators'] = [1, 2, 19]
        n.snapshot_weightings.loc[:, 'objective'] = [3, 1, 7]
        if 'e_sum_min' in bounds:
            n.c.generators.static.loc['asset', 'marginal_cost'] = 30
        solve_dispatch(n, n.snapshots[:2])
        p = asset_dispatch(n, 'Generator', ['a', 'b'])
        assert_close(p @ np.array([1, 2]), expected)
        assert np.all((p >= -1e-5) & (p <= 10+1e-5))
        assert_close(p+n.c.generators.dynamic.p.loc[['a', 'b'], 'backup'], 12)
    n = conversion_dispatch('Generator', e_sum_min=31, snapshots=('a', 'b'))
    n.snapshot_weightings.loc[:, 'generators'] = [1, 2]
    result = invoke(n.optimize, kwargs={'solver_name': 'highs'})
    assert result.value == ('warning', 'infeasible')


def test_symmetric_voltage_angle_limits_independent_of_capacity():
    for component in ['Line', 'Transformer']:
        for direction, rating, limit in [(1, 100, .5), (-1, 100, .5), (1, 200, .5), (1, 100, np.inf)]:
            n = Network()
            n.set_snapshots(['now'])
            n.add('Bus', ['a', 'b'], v_nom=1)
            attrs = {'x': .1} if component == 'Line' else {'x': rating*.1, 'phase_shift': .2}
            n.add(component, 'branch', bus0='a', bus1='b', r=.001,
                  s_nom=rating, v_ang_max=limit, **attrs)
            source, sink = ('a', 'b') if direction == 1 else ('b', 'a')
            n.add('Generator', 'cheap', bus=source, p_nom=10, marginal_cost=1)
            n.add('Generator', 'dear', bus=sink, p_nom=10, marginal_cost=20)
            n.add('Load', 'demand', bus=sink, p_set=1)
            solve_dispatch(n)
            branch = n.components[component]
            flow = branch.dynamic.p0.at['now', 'branch']
            phase = .2 if component == 'Transformer' else 0
            expected = min(1, np.deg2rad(limit-direction*phase)/.1)
            assert_close(flow, direction*expected)
            assert_close(n.c.generators.dynamic.p.at['now', 'cheap'], expected)
            if component == 'Line':
                angle = n.c.buses.dynamic.v_ang.at['now', 'a']-n.c.buses.dynamic.v_ang.at['now', 'b']
                assert_close(angle, .1*flow)
            else:
                assert_close(n.c.transformers.dynamic.phase_shift_opt.at['now', 'branch'], .2)


def test_ramps_initial_dispatch_capacity_and_period_boundaries():
    for component in ['Generator', 'Link', 'Process']:
        for limited, initial, extend in [(False, None, False), (True, None, False),
                                         (True, 0, False), (True, 0, True)]:
            attrs = {}
            if limited:
                attrs.update(ramp_limit_up=.2, ramp_limit_down=.3)
            if initial is not None:
                attrs['p_init'] = initial
            if extend:
                attrs.update(p_nom_extendable=True, p_nom_min=20, p_nom_max=20, capital_cost=1)
            n = conversion_dispatch(component, demand=[8, 2, 9], snapshots=('a', 'b', 'c'), **attrs)
            n.snapshot_weightings.loc[:, :] = [[4, 7, 3], [2, 5, 8], [9, 6, 2]]
            solve_dispatch(n)
            expected = [8, 2, 9] if not limited else ([5, 2, 4] if initial is None else [2, 2, 4])
            if extend:
                expected = [4, 2, 6]
            assert_close(asset_dispatch(n, component), expected)
            assert_close(n.components[component].static.at['asset', 'p_nom_opt'], 20 if extend else 10)
            assert_close(n.c.generators.dynamic.p['backup']+asset_dispatch(n, component), [8, 2, 9])
        n = conversion_dispatch(component, demand=[0, 8], snapshots=('a', 'b'), ramp_limit_up=.1, ramp_limit_down=.1)
        n.set_investment_periods([2030, 2040])
        n.c.loads.dynamic.p_set.loc[(2040, 'a'), 'demand'] = 8
        solve_dispatch(n, multi_investment_periods=True)
        assert_close(asset_dispatch(n, component).loc[(2040, 'a')], 8)
