# feature: F13
"""Acceptance checks for piecewise costs and conversion characteristics."""
from velmora import Network
from _helpers import invoke
from F06_helpers import assert_close, dispatch_bus, solve_dispatch
from F11_helpers import solve_edited_model
from F08_helpers import INVESTMENT_COMPONENTS, expansion_problem, investment_flow
from F13_helpers import (OPERATING_COMPONENTS, operating_curve_problem,
                         curve_options, bind_and_solve)


def test_operating_cost_interpretations_and_dispatch():
    # The expensive first interval cannot be skipped to reach the cheap second.
    curve = {0: 97, .2: 8, .6: 2, 1: 20}
    for component in OPERATING_COMPONENTS:
        for equality in [False, True]:
            n = operating_curve_problem(component, curve)
            n.snapshot_weightings.loc[:, 'objective'] = 3
            solve_dispatch(n, **curve_options(component, 'marginal_cost', equality=equality))
            c = n.components[component]
            flow = c.dynamic['p0' if component == 'Link' else 'p']['asset']
            assert_close(flow, 6)
            assert_close(n.c.generators.dynamic.p['backup'], 2)
            total = 24
            assert_close(c.dynamic.marginal_cost_piecewise_opt['asset'], total / 6)
            assert_close(n.objective, 3 * (total + 10))
        # An interior operating point distinguishes total-cost interpolation
        # from interpolating the unit price. The same curve is supplied as a
        # mapping in non-ascending key order; breakpoints are quantities.
        shuffled = {1: 20, .2: 8, 0: 97, .6: 2}
        n = operating_curve_problem(component, shuffled, demand=4)
        n.c.generators.static.loc['backup', 'marginal_cost'] = 100
        solve_dispatch(n)
        c = n.components[component]
        assert_close(c.dynamic['p0' if component == 'Link' else 'p']['asset'], 4)
        total = 20
        assert_close(c.dynamic.marginal_cost_piecewise_opt['asset'], total / 4)
        assert_close(n.objective, total)


def test_capital_cost_interpretations_and_investment():
    for component in INVESTMENT_COMPONENTS:
        n, nominal = expansion_problem(component, capital_cost={0: 97, 2: 8, 6: 2, 10: 20})
        if component not in ('Line', 'Transformer'):
            n.components[component].static.loc['asset', 'marginal_cost'] = 0
        n.c.loads.dynamic.p_set.loc[:, 'demand'] = [0, 8] if component in ('Store', 'StorageUnit') else 8
        if component in ('Store', 'StorageUnit'):
            n.c.generators.dynamic.marginal_cost.loc[:, 'supply'] = [0, 5]
        else:
            n.c.generators.static.loc['backup', 'marginal_cost'] = 5
            if component != 'Generator':
                n.c.generators.static.loc['supply', 'marginal_cost'] = 0
        solve_dispatch(n)
        c = n.components[component]
        assert_close(c.static.at['asset', nominal+'_opt'], 6)
        total = 24
        if component not in ('Line', 'Transformer'):
            assert_close(c.static.at['asset', 'capital_cost_piecewise_opt'], total / 6)
        assert_close(investment_flow(n, component), [-6, 6] if component in ('Store', 'StorageUnit') else 6)
        assert_close(n.objective, total + 10)
        # Interior capacity exposes an incorrect convex-hull relaxation.
        c.static.loc['asset', nominal+'_set'] = 4
        solve_dispatch(n)
        assert_close(c.static.at['asset', nominal+'_opt'], 4)
        if component not in ('Line', 'Transformer'):
            assert_close(c.static.at['asset', 'capital_cost_piecewise_opt'], 5)
        assert_close(n.objective, 40)


def test_fuel_and_multiport_quantity_interpolation():
    # Fuel breakpoints are (0,0), (5,20), (10,25). A budget of 22
    # permits 7 output, whereas interpolating efficiency would give another limit.
    n = dispatch_bus([0, 8], (0, 1))
    n.add('Carrier', 'fuel', co2_emissions=1)
    n.add('Generator', 'asset', bus='sink', carrier='fuel', p_nom=10,
          efficiency={0: 0, .5: .25, 1: .4}, marginal_cost=1)
    n.add('Generator', 'backup', bus='sink', p_nom=20, marginal_cost=10)
    n.add('GlobalConstraint', 'budget', carrier_attribute='co2_emissions', constant=22)
    solve_dispatch(n)
    assert_close(n.c.generators.dynamic.p['asset'], [0, 7])
    assert_close(n.c.generators.dynamic.p['backup'], [0, 1])
    assert_close(n.objective, 17)
    for component in ['Link', 'Process']:
        n = Network()
        n.set_snapshots([0, 1, 2])
        n.add('Bus', ['source', 'out', 'extra'])
        n.add('Generator', 'fuel', bus='source', p_nom=100, marginal_cost=1)
        n.add('Load', 'out', bus='out', p_set=[20, 30, 40])
        n.add('Load', 'extra', bus='extra', p_set=[25, 31.25, 37.5])
        attrs = {'efficiency': {0: 0, .1: .3, .5: .4, 1: .6}, 'efficiency2': .5} if component == 'Link' else {
            'rate1': {0: 0, .1: .3, .5: .4, 1: .6}, 'rate2': .5}
        n.add(component, 'asset', bus0='source', bus1='out', bus2='extra', p_nom=100, **attrs)
        solve_dispatch(n)
        c = n.components[component]
        assert_close(c.dynamic.p0['asset'], [50, 62.5, 75])
        assert_close(c.dynamic.p1['asset'], [-20, -30, -40])
        assert_close(c.dynamic.p2['asset'], [-25, -31.25, -37.5])
        assert_close(n.objective, 187.5)
    # A negative process rate describes a withdrawal, with quantity interpolated.
    n = dispatch_bus(30)
    n.add('Bus', 'source')
    n.add('Generator', 'fuel', bus='source', p_nom=200, marginal_cost=1)
    n.add('Process', 'asset', bus0='source', bus1='sink', p_nom=100,
          rate0={0: 0, .1: -1/.3, .5: -1/.4, 1: -1/.6}, rate1=1)
    solve_dispatch(n)
    assert_close(n.c.processes.dynamic.p['asset'], 30)
    assert_close(n.c.processes.dynamic.p0['asset'], 475/6)
    assert_close(n.c.processes.dynamic.p1['asset'], -30)


def test_capacity_scaling_and_invalid_per_unit_scope():
    for component in OPERATING_COMPONENTS:
        for capacity in [10, 20]:
            n = operating_curve_problem(component, {0: 0, .5: 2, 1: 10},
                                        demand=.75*capacity, capacity=capacity)
            n.c.generators.static.loc['backup', 'marginal_cost'] = 100
            solve_dispatch(n)
            assert_close(n.objective, 3.5*capacity)
        nominal = 'e_nom' if component == 'Store' else 'p_nom'
        for attrs in [{nominal: 0}, {}, {nominal: float('inf')},
                      {nominal: float('nan')}, {nominal: 10, nominal+'_extendable': True}]:
            n = dispatch_bus(1)
            n.add('Bus', 'source')
            n.add('Generator', 'backup', bus='sink', p_nom=100, marginal_cost=5)
            attrs = dict(attrs, marginal_cost={0: 0, .5: 2, 1: 10})
            attrs.update({'bus': 'sink'} if component in ('Generator', 'Store', 'StorageUnit') else {'bus0': 'source', 'bus1': 'sink'})
            result = invoke(bind_and_solve, n, component, attrs, expected_exceptions=(ValueError,))
            assert isinstance(result.exception, ValueError), result
    # Absolute capacity curves remain usable for extendable equipment.
    n, nominal = expansion_problem('Generator', capital_cost={0: 0, 5: 2, 10: 4})
    solve_dispatch(n)
    assert_close(n.c.generators.static.at['asset', nominal+'_opt'], 7)
    assert_close(n.objective, 25)


def test_curve_endpoint_sign_and_cost_conflicts():
    for curve in [{.1: 0, .5: 2, 1: 4}, {0: 0, .5: 2, .8: 4}]:
        n = dispatch_bus(1)
        result = invoke(bind_and_solve, n, 'Generator',
                        {'bus': 'sink', 'p_nom': 10, 'marginal_cost': curve},
                        expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError), result
    for component, attribute in [('Link', 'efficiency'), ('Link', 'efficiency2'),
                                 ('Process', 'rate0'), ('Process', 'rate1'), ('Process', 'rate2')]:
        n = dispatch_bus(1)
        n.add('Bus', ['source', 'extra'])
        result = invoke(bind_and_solve, n, component,
                        {'bus0': 'source', 'bus1': 'sink', 'bus2': 'extra', 'p_nom': 10,
                         attribute: {0: 0, .5: -.5, 1: .8}},
                        expected_exceptions=(NotImplementedError,))
        assert isinstance(result.exception, NotImplementedError), result
    n = dispatch_bus(1)
    result = invoke(bind_and_solve, n, 'Generator',
                    {'bus': 'sink', 'p_nom_extendable': True, 'p_nom_max': 10,
                     'capital_cost': {0: 0, 5: 2, 10: 4}, 'overnight_cost': 100},
                    expected_exceptions=(ValueError,))
    assert isinstance(result.exception, ValueError), result


def test_equality_cost_relation_rejects_cost_above_curve():
    # A positive cost floor distinguishes equality from a lower bound even
    # though both ordinarily minimise to the same curve value.
    selections = [(c, 'marginal_cost') for c in OPERATING_COMPONENTS]
    selections += [(c, 'capital_cost') for c in INVESTMENT_COMPONENTS]
    for component, attribute in selections:
        for equality in [False, True]:
            if attribute == 'marginal_cost':
                n = operating_curve_problem(component, {0: 0, .5: 2, 1: 8}, demand=7)
                n.components[component].static.at['asset', 'p_set'] = 7
                if component == 'StorageUnit':
                    n.c.storage_units.static.loc['asset', ['p_store_set', 'p_dispatch_set']] = [0, 7]
            else:
                nominal = 'e_nom' if component == 'Store' else (
                    's_nom' if component in ('Line', 'Transformer') else 'p_nom')
                n, _ = expansion_problem(component, **{
                    nominal: 0, nominal + '_set': 7,
                    'capital_cost': {0: 0, 5: 2, 10: 8}})
            model = n.optimize.create_model(**curve_options(component, attribute, equality=equality))
            total = model.variables[component + '-' + attribute + '_piecewise'].sel(name='asset')
            model.add_constraints(total >= 30, name='cost-floor')
            solve_edited_model(n, ('warning', 'infeasible') if equality else ('ok', 'optimal'))
            if not equality:
                solved_total = model.variables[component + '-' + attribute + '_piecewise'].sel(name='asset')
                assert_close(solved_total.solution.item(), 30)
                assert_close(investment_flow(n, component).iloc[-1], 7)
                if attribute == 'marginal_cost' or component not in ('Store', 'StorageUnit'):
                    assert_close(n.c.generators.dynamic.p.at['now', 'backup'], 0)
                else:
                    assert_close(n.c.generators.dynamic.p['supply'], [7, 0])
                assert_close(n.objective, 30 if attribute == 'marginal_cost' else 37)
