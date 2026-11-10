# feature: F08
"""Acceptance tests for capacity investment and investment pathways."""
import numpy as np
import pytest
from velmora import Network
from velmora.costs import annuity
from _helpers import invoke
from F06_helpers import solve_dispatch, assert_close, dispatch_bus
from F08_helpers import (INVESTMENT_COMPONENTS, expansion_problem, investment_flow,
                         financed_supply, transmission_triangle, solve_transmission)


def test_continuous_capacity_bounds_targets_and_existing_capacity():
    for component in INVESTMENT_COMPONENTS:
        for bound, capacity in [(None, 7), ('min', 9), ('max', 5), ('set', 8)]:
            nominal = 'e_nom' if component == 'Store' else (
                's_nom' if component in ('Line', 'Transformer') else 'p_nom')
            attrs = {} if bound is None else {nominal+'_'+bound: capacity}
            n, nominal = expansion_problem(component, **attrs)
            solve_dispatch(n, include_objective_constant=False)
            assert_close(n.components[component].static.at['asset', nominal+'_opt'], capacity)
            delivered = min(capacity, 7)
            if component in ('StorageUnit', 'Store'):
                assert_close(investment_flow(n, component), [-delivered, delivered])
                assert_close(n.c.generators.dynamic.p['supply'], [delivered, 7-delivered])
                assert_close(n.objective, 2*capacity+delivered+20*(7-delivered))
            else:
                assert_close(investment_flow(n, component), delivered)
                assert_close(n.c.generators.dynamic.p['backup'], 7-delivered)
                assert_close(n.objective, 2*capacity+delivered+20*(7-delivered))


def test_modular_capacity_continuous_nonpositive_and_incompatible_targets():
    for component in INVESTMENT_COMPONENTS:
        nominal = 'e_nom' if component == 'Store' else (
            's_nom' if component in ('Line', 'Transformer') else 'p_nom')
        n, _ = expansion_problem(component, **{nominal+'_mod': 4})
        solve_dispatch(n, include_objective_constant=False)
        assert_close(n.components[component].static.at['asset', nominal+'_opt'], 8)
        assert_close(investment_flow(n, component), [-7, 7] if component in ('Store', 'StorageUnit') else 7)
    for module, capacity in [(0, 7), (-4, 7)]:
        n, _ = expansion_problem('Generator', p_nom_mod=module)
        solve_dispatch(n)
        assert_close(n.c.generators.static.at['asset', 'p_nom_opt'], capacity)
    for attrs in [dict(p_nom_set=6, p_nom_mod=4),
                  dict(p_nom_set=11, p_nom_max=10),
                  dict(p_nom_set=3, p_nom_min=4)]:
        n, _ = expansion_problem('Generator', **attrs)
        result = invoke(n.optimize, kwargs={'solver_name': 'highs',
                                           'solver_options': {'threads': 1}})
        assert result.value == ('warning', 'infeasible'), result


def test_periodized_overnight_financing_maintenance_and_cost_tradeoff():
    # Equal repayments: five payments, discounted at 25%, fund the principal.
    # Present-value sum = 2.68928; no product cost helper supplies the oracle.
    annual = 100 / 2.68928
    for attrs, unit_cost in [
        (dict(capital_cost=17, fom_cost=3), 20),
        (dict(overnight_cost=100, discount_rate=.25, lifetime=5,
              capital_cost=999, fom_cost=3), annual*.5+3),
        (dict(overnight_cost=100, discount_rate=.25, lifetime=5), annual*.5)]:
        n = financed_supply(**attrs)
        solve_dispatch(n)
        assert_close(n.c.generators.static.at['asset', 'p_nom_opt'], 6)
        assert_close(n.c.generators.dynamic.p['asset'], [4, 6])
        assert_close(n.objective, 6*unit_cost+2190*2*10)
    for capital, expected in [(2, 7), (30, 0)]:
        n, _ = expansion_problem('Generator', capital_cost=capital, p_nom=0)
        solve_dispatch(n)
        assert_close(n.c.generators.static.at['asset', 'p_nom_opt'], expected)
        assert_close(n.c.generators.dynamic.p['asset'], expected)
        assert_close(n.objective, expected*(capital+1)+(7-expected)*20)


def test_financing_lifetime_boundaries_and_unequal_period_duration():
    # Direct financing has its own scalar validation, independently of planning.
    assert_close(annuity(.25, 5), 1 / 2.68928)
    assert_close(annuity(0, 10), .1)
    for lifetime in [0, -1, -5.5]:
        with pytest.raises(ValueError):
            annuity(.05, lifetime)
    for lifetime, rate, annual in [(10, 0, 10), (np.inf, .08, 8),
                                   (np.inf, 0, 0), (np.inf, -.03, 0)]:
        n = financed_supply(overnight_cost=100, discount_rate=rate,
                            lifetime=lifetime, fom_cost=3)
        solve_dispatch(n)
        assert_close(n.c.generators.static.at['asset', 'p_nom_opt'], 6)
        assert_close(n.c.generators.dynamic.p['asset'], [4, 6])
        assert_close(n.objective, 6*(annual*.5+3)+2190*2*10)
    n = financed_supply(overnight_cost=100, discount_rate=.05, lifetime=20)
    n.set_investment_periods([2030, 2040])
    n.snapshot_weightings.loc[2040, 'objective'] = 4380
    with pytest.raises(ValueError):
        n.optimize(multi_investment_periods=True, solver_name='highs',
                   solver_options={'threads': 1})


def test_shared_period_investment_activity_weights_and_resource_years():
    n = dispatch_bus(6)
    n.set_investment_periods([2030, 2040, 2050])
    n.investment_period_weightings.loc[:, 'objective'] = [2, 3, 5]
    n.investment_period_weightings.loc[:, 'years'] = [7, 11, 13]
    n.add('Generator', 'old-fixed', bus='sink', p_nom=2, build_year=2020,
          lifetime=20, marginal_cost=1)
    n.add('Generator', 'old-expandable', bus='sink', p_nom=20,
          p_nom_extendable=True, build_year=2020, lifetime=20,
          capital_cost=2, marginal_cost=2)
    n.add('Generator', 'new', bus='sink', p_nom_extendable=True,
          build_year=2040, lifetime=10, capital_cost=3, marginal_cost=3)
    n.add('Generator', 'last', bus='sink', p_nom_extendable=True,
          build_year=2050, lifetime=10, capital_cost=4, marginal_cost=4)
    solve_dispatch(n, multi_investment_periods=True, include_objective_constant=False)
    assert_close(n.c.generators.static.loc[['old-fixed', 'old-expandable', 'new', 'last'], 'p_nom_opt'], [2, 4, 6, 6])
    assert_close(n.c.generators.dynamic.p.loc[:, ['old-fixed', 'old-expandable', 'new', 'last']],
                 [[2, 4, 0, 0], [0, 0, 6, 0], [0, 0, 0, 6]])
    assert_close(n.objective, 2*(2+8+8)+3*(18+18)+5*(24+24))
    # One investment spans both periods; peak demand determines its one capacity.
    shared = dispatch_bus(4)
    shared.set_investment_periods([2030, 2040])
    shared.c.loads.static.loc['demand', 'p_set'] = 0
    shared.add('Load', 'varying', bus='sink', p_set=[4, 7])
    shared.investment_period_weightings.loc[:, 'objective'] = [2, 5]
    shared.add('Generator', 'shared', bus='sink', p_nom_extendable=True,
               capital_cost=3, marginal_cost=1, build_year=2020, lifetime=30)
    solve_dispatch(shared, multi_investment_periods=True)
    assert_close(shared.c.generators.static.at['shared', 'p_nom_opt'], 7)
    assert_close(shared.c.generators.dynamic.p['shared'], [4, 7])
    assert_close(shared.objective, 7*3*(2+5)+2*4+5*7)
    # A second independent problem separates economic weights from resource years.
    n = dispatch_bus(4)
    n.set_investment_periods([2030, 2040])
    n.investment_period_weightings.loc[:, 'objective'] = [2, 5]
    n.investment_period_weightings.loc[:, 'years'] = [2, 3]
    n.add('Carrier', 'fuel', co2_emissions=1)
    n.add('Generator', 'fuel', bus='sink', carrier='fuel', p_nom=4, marginal_cost=1)
    n.add('Generator', 'clean', bus='sink', p_nom=4, marginal_cost=10)
    n.add('GlobalConstraint', 'budget', type='primary_energy',
          carrier_attribute='co2_emissions', sense='<=', constant=10)
    solve_dispatch(n, multi_investment_periods=True)
    assert_close(n.c.generators.dynamic.p['fuel'], [0, 10/3])
    assert_close(n.c.generators.dynamic.p['clean'], [4, 2/3])
    assert_close(n.objective, 130)


def test_objective_offset_and_fixing_capacity_for_operation():
    for component in INVESTMENT_COMPONENTS:
        n, nominal = expansion_problem(component, fom_cost=3)
        without = n.copy()
        solve_dispatch(n)
        solve_dispatch(without, include_objective_constant=False)
        assert_close(n.components[component].static.at['asset', nominal+'_opt'], 7)
        assert_close(without.components[component].static.at['asset', nominal+'_opt'], 7)
        assert_close(investment_flow(n, component), investment_flow(without, component))
        assert_close(without.objective-n.objective, 30*5)
        n.optimize.fix_optimal_capacities()
        c = n.components[component]
        assert_close(c.static.at['asset', nominal], 7)
        assert not c.static.at['asset', nominal+'_extendable']
        # Change demand to prove the fixed capacity cannot expand on re-solve.
        n.c.loads.static.loc['demand', 'p_set'] = 9
        if component in ('Store', 'StorageUnit'):
            n.c.loads.dynamic.p_set.loc[:, 'demand'] = [0, 9]
        solve_dispatch(n)
        assert_close(c.static.at['asset', nominal+'_opt'], 7)
        assert_close(investment_flow(n, component), [-7, 7] if component in ('Store', 'StorageUnit') else 7)
    # Only active periods enter the accounting deduction.
    n = dispatch_bus(6)
    n.set_investment_periods([2030, 2040])
    n.investment_period_weightings.loc[:, 'objective'] = [2, 5]
    n.add('Generator', 'first', bus='sink', p_nom=10, p_nom_extendable=True,
          build_year=2030, lifetime=10, capital_cost=3, fom_cost=2, marginal_cost=1)
    n.add('Generator', 'second', bus='sink', p_nom=20, p_nom_extendable=True,
          build_year=2040, lifetime=10, capital_cost=4, fom_cost=3, marginal_cost=2)
    other = n.copy()
    solve_dispatch(n, multi_investment_periods=True)
    solve_dispatch(other, multi_investment_periods=True, include_objective_constant=False)
    assert_close(other.objective-n.objective, 2*10*5+5*20*7)
    assert_close(n.c.generators.static.p_nom_opt, [6, 6])
    assert_close(n.c.generators.dynamic.p.loc[:, ['first', 'second']], [[6, 0], [0, 6]])
    assert_close(other.c.generators.dynamic.p, n.c.generators.dynamic.p)


def test_transmission_expansion_adjusts_impedance_and_final_operation():
    for carrier, field in [('AC', 'x'), ('DC', 'r')]:
        n = transmission_triangle(carrier)
        ordinary = n.copy()
        solve_dispatch(ordinary)
        assert_close(ordinary.c.lines.static.at['asset', 's_nom_opt'], 20)
        assert_close(ordinary.c.lines.static.at['asset', field], .2)
        assert_close(ordinary.c.lines.dynamic.p0.loc[:, ['asset', 'bc', 'ac']], [[12, 12, 18]])
        solve_transmission(n)
        assert_close(n.c.lines.static.at['asset', 's_nom_opt'], 20)
        assert_close(n.c.lines.static.at['asset', field], .1)
        # Independent series/parallel circuit: both paths now have impedance .2.
        assert_close(n.c.lines.dynamic.p0.loc[:, ['asset', 'bc', 'ac']], [[15, 15, 15]])
        assert_close(n.c.lines.dynamic.p1.loc[:, ['asset', 'bc', 'ac']], [[-15, -15, -15]])
        assert_close(n.c.generators.dynamic.p['supply'], 30)


def test_transmission_discrete_increments_threshold_and_fractional_last_unit():
    for threshold, fractional in [(None, False), (.5, False), (.5, True)]:
        # Each row distinguishes a promised rounding branch; paired line/link
        # circuits exercise their separate public workflow bindings in one solve.
        cases = [(12, 100, 10), (13, 100, 20), (14, 100, 20),
                 (7, 8, 8), (11, 15, 10), (13, 15, 10)]
        if threshold == .5:
            cases = [(14, 100, 10), (15, 100, 20), (16, 100, 20),
                     (7, 8, 8), (11, 14, 10), (12, 14, 14 if fractional else 10),
                     (13, 14, 14 if fractional else 10)]
        n = Network()
        n.set_snapshots(['now'])
        n.add('Carrier', 'DC')
        for component in ['Line', 'Link']:
            for i, (demand, maximum, expected) in enumerate(cases):
                name = f'{component}-{i}'
                n.add('Bus', [name+'-a', name+'-b'], v_nom=1)
                nominal = 's_nom' if component == 'Line' else 'p_nom'
                attrs = {nominal: 5, nominal+'_extendable': True,
                         nominal+'_max': maximum, 'capital_cost': 1}
                attrs.update({'x': .1, 'r': .01} if component == 'Line' else {'carrier': 'DC'})
                n.add(component, name, bus0=name+'-a', bus1=name+'-b', **attrs)
                n.add('Generator', name+'-source', bus=name+'-a', p_nom=100, marginal_cost=1)
                n.add('Generator', name+'-backup', bus=name+'-b', p_nom=100, marginal_cost=100)
                n.add('Load', name, bus=name+'-b', p_set=demand)
        options = {'line_unit_size': 10, 'link_unit_size': {'DC': 10},
                   'fractional_last_unit_size': fractional}
        if threshold is not None:
            options.update(line_threshold=threshold, link_threshold={'DC': threshold})
        solve_transmission(n, **options)
        for component in ['Line', 'Link']:
            nominal = 's_nom' if component == 'Line' else 'p_nom'
            for i, (demand, maximum, expected) in enumerate(cases):
                name = f'{component}-{i}'
                c = n.components[component]
                assert_close(c.static.at[name, nominal+'_opt'], expected)
                delivered = min(demand, expected)
                assert_close(c.dynamic.p0[name], delivered)
                assert_close(c.dynamic.p1[name], -delivered)
                assert_close(n.c.generators.dynamic.p[name+'-backup'], demand-delivered)


def test_investment_defaults_and_unbounded_continuous_operation():
    for component in INVESTMENT_COMPONENTS:
        n, nominal = expansion_problem(component)
        c = n.components[component]
        row = c.static.loc['asset']
        assert row[nominal+'_min'] == 0
        assert np.isposinf(row[nominal+'_max'])
        assert np.isposinf(row['lifetime'])
        assert row['build_year'] == 0
        assert row['fom_cost'] == 0
        # Re-add with omitted investment cost and omitted module size.
        attrs = {nominal: 0, nominal+'_extendable': True}
        if component in ('Generator', 'StorageUnit', 'Store'):
            attrs['bus'] = 'sink'
        else:
            attrs.update(bus0='source', bus1='sink')
        if component in ('Line', 'Transformer'):
            attrs.update(x=.1, r=.01)
        if component == 'Generator':
            attrs['marginal_cost'] = 1
        n.remove(component, 'asset')
        n.add(component, 'asset', **attrs)
        assert n.components[component].static.at['asset', 'capital_cost'] == 0
        # A nonintegral target above demand proves continuous investment without
        # relying on a solver's arbitrary choice among zero-cost capacities.
        n.components[component].static.loc['asset', nominal+'_set'] = 9.25
        solve_dispatch(n)
        assert_close(n.components[component].static.at['asset', nominal+'_opt'], 9.25)
        assert_close(n.objective, 7)
        assert_close(investment_flow(n, component), [-7, 7] if component in ('Store', 'StorageUnit') else 7)
