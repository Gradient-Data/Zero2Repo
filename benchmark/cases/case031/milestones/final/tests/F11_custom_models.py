# feature: F11
"""Acceptance of public model editing and decision-linked aggregates."""
import numpy as np
from _helpers import invoke
from F06_helpers import dispatch_bus, assert_close
from F08_helpers import expansion_problem
from F11_helpers import solve_edited_model, aggregate_cell


def test_custom_variables_constraints_objective_and_infeasibility():
    for objective in ('original', 'replace', 'extend'):
        n, _ = expansion_problem('Generator', p_nom=0)
        m = invoke(n.optimize.create_model).value
        p = m.variables['Generator-p'].sel(name='asset')
        q = m.add_variables(lower=0, upper=5, name='custom-delivery')
        m.add_constraints(p == q, name='custom-coupling')
        if objective == 'replace':
            m.add_objective(-q, overwrite=True)
        elif objective == 'extend':
            # Original marginal saving is 17 per delivered unit; reverse it.
            m.add_objective(m.objective.expression + 30*q, overwrite=True)
        solve_edited_model(n)
        expected = 0 if objective == 'extend' else 5
        assert_close(q.solution.item(), expected)
        assert_close(n.c.generators.dynamic.p['asset'], expected)
        assert_close(n.c.generators.dynamic.p['backup'], 7-expected)
        if objective == 'original':
            assert_close(n.c.generators.static.at['asset', 'p_nom_opt'], 5)
            assert_close(n.objective, 55)
        elif objective == 'replace':
            assert_close(n.objective, -5)
        else:
            assert_close(n.objective, 140)
    n, _ = expansion_problem('Generator', p_nom=0)
    m = invoke(n.optimize.create_model).value
    p = m.variables['Generator-p'].sel(name='asset')
    m.add_constraints(p >= 4, name='custom-lower')
    m.add_constraints(p <= 2, name='custom-upper')
    solve_edited_model(n, ('warning', 'infeasible'))


def test_capacity_cost_and_operation_aggregates_constrain_decisions():
    for quantity in ('capacity', 'capex', 'opex', 'operation'):
        n = dispatch_bus([4, 6], (0, 1))
        n.add('Carrier', ['renewable', 'backup'])
        n.add('Generator', 'asset', bus='sink', carrier='renewable',
              p_nom_extendable=True, capital_cost=2, marginal_cost=1)
        n.add('Generator', 'backup', bus='sink', carrier='backup',
              p_nom=100, marginal_cost=20)
        n.snapshot_weightings.loc[:, 'objective'] = [5, 1]
        n.snapshot_weightings.loc[:, 'generators'] = [2, 3]
        m = invoke(n.optimize.create_model).value
        kwargs = dict(components=['Generator'], groupby=['carrier', 'bus'],
                      carrier='renewable', nice_names=False)
        if quantity in ('operation', 'opex'):
            kwargs['groupby_time'] = 'sum'
        expression = getattr(n.optimize.expressions, quantity)(**kwargs)
        selected = aggregate_cell(expression, 'Generator', 'renewable', 'sink')
        # Each restriction cuts the unconstrained renewable optimum differently.
        limit = {'capacity': 3, 'capex': 8, 'operation': 14, 'opex': 12}[quantity]
        m.add_constraints(selected <= limit, name='aggregate-budget')
        solve_edited_model(n)
        capacity = {'capacity': 3, 'capex': 4, 'operation': 4, 'opex': 2}[quantity]
        assert_close(n.c.generators.static.at['asset', 'p_nom_opt'], capacity)
        power = n.c.generators.dynamic.p['asset'].to_numpy()
        assert_close(power, [4, 2] if quantity == 'operation' else [capacity, capacity])
        assert_close(n.c.generators.dynamic.p['backup'], np.array([4, 6])-power)
        energy = np.dot([2, 3], power)
        independent = {'capacity': capacity, 'capex': 2*capacity,
                       'operation': energy, 'opex': np.dot([5, 1], power)}[quantity]
        assert_close(selected.solution.item(), independent)
        operating_energy = np.dot([5, 1], power)
        assert_close(n.objective, 2*capacity+operating_energy+20*(26-operating_energy))


def test_energy_port_and_transmission_aggregates_constrain_decisions():
    for quantity in ('energy_balance', 'supply', 'withdrawal', 'curtailment',
                     'transmission'):
        n = dispatch_bus([4, 6], (0, 1))
        n.add('Carrier', ['electricity', 'heat', 'wind', 'backup', 'transfer',
                          'other'])
        n.c.buses.static.loc['sink', 'carrier'] = 'electricity'
        n.add('Bus', 'source', carrier='electricity')
        # The second link joins buses of different carriers: it is withdrawal
        # at the shared source bus but not transmission between equal carriers.
        n.add('Bus', 'other', carrier='heat')
        n.add('Generator', 'wind', bus='source', carrier='wind', p_nom=10,
              p_max_pu=[1, .5], marginal_cost=1)
        n.add('Generator', 'backup', bus='sink', carrier='backup',
              p_nom=100, marginal_cost=20)
        n.add('Link', 'delivery', bus0='source', bus1='sink', carrier='transfer',
              efficiency=.8, p_nom=20)
        n.add('Link', 'other', bus0='source', bus1='other', carrier='transfer',
              efficiency=.5, p_nom=20)
        n.add('Load', 'other', bus='other', p_set=1)
        # A distinct carrier has unused potential, making filtering observable.
        n.add('Generator', 'other', bus='source', carrier='other', p_nom=1,
              p_max_pu=[1, 1], marginal_cost=100)
        n.snapshot_weightings.loc[:, 'objective'] = [5, 1]
        n.snapshot_weightings.loc[:, 'generators'] = [2, 3]
        m = invoke(n.optimize.create_model).value
        kwargs = dict(groupby=['carrier', 'bus'], nice_names=False,
                      groupby_time='sum')
        if quantity == 'curtailment':
            expression = n.optimize.expressions.curtailment(
                components=['Generator'], carrier='wind', **kwargs)
            selected = aggregate_cell(expression, 'Generator', 'wind', 'source')
            m.add_constraints(selected >= 10, name='aggregate-restriction')
            input_energy = 15
        else:
            port = 'bus1' if quantity in ('energy_balance', 'supply') else 'bus0'
            expression = getattr(n.optimize.expressions, quantity)(
                components=['Link'], carrier='transfer', bus_carrier='electricity',
                at_port=[port], **kwargs)
            bus = 'sink' if port == 'bus1' else 'source'
            selected = aggregate_cell(expression, 'Link', 'transfer', bus)
            # Both links share bus0, so its withdrawal group includes the fixed
            # other flow; transmission excludes the link to the heat bus.
            if quantity in ('energy_balance', 'supply'):
                m.add_constraints(selected <= 10, name='aggregate-restriction')
            elif quantity == 'withdrawal':
                m.add_constraints(selected <= 22.5, name='aggregate-restriction')
            else:
                m.add_constraints(selected >= -12.5, name='aggregate-restriction')
            input_energy = 12.5
        if quantity == 'energy_balance':
            input_balance = aggregate_cell(
                n.optimize.expressions.energy_balance(
                    components=['Link'], carrier='transfer', at_port=['bus0'],
                    bus_carrier='electricity', **kwargs),
                'Link', 'transfer', 'source')
            m.add_constraints(input_balance >= -22.5, name='input-balance-budget')
        solve_edited_model(n)
        p0 = n.c.links.dynamic.p0['delivery'].to_numpy()
        p1 = n.c.links.dynamic.p1['delivery'].to_numpy()
        assert_close(p1, -.8*p0)
        assert_close(n.c.links.dynamic.p0['other'], 2)
        assert_close(n.c.links.dynamic.p1['other'], -1)
        assert_close(np.dot([2, 3], p0), input_energy)
        assert_close(n.c.generators.dynamic.p['wind'], p0+2)
        assert_close(n.c.generators.dynamic.p['other'], 0)
        assert_close(n.c.generators.dynamic.p['backup'], np.array([4, 6])+p1)
        if quantity == 'curtailment':
            independent = np.dot([2, 3], np.array([10, 5])-(p0+2))
        elif quantity in ('energy_balance', 'supply'):
            independent = np.dot([2, 3], -p1)
        elif quantity == 'transmission':
            independent = -np.dot([2, 3], p0)
        else:
            independent = np.dot([2, 3], p0+2)
        assert_close(selected.solution.item(), independent)
        if quantity == 'energy_balance':
            assert_close(input_balance.solution.item(), -np.dot([2, 3], p0+2))

    # At a hub with both ports selected, supply counts only inbound delivery
    # and withdrawal only outbound flow, not their signed net contribution.
    for quantity, inflow, outflow in [('supply', 4, 6), ('withdrawal', 4, 4)]:
        n = dispatch_bus(6)
        n.add('Carrier', ['electricity', 'transfer'])
        n.c.buses.static.loc['sink', 'carrier'] = 'electricity'
        n.add('Bus', ['far', 'hub'], carrier='electricity')
        n.add('Generator', 'far', bus='far', p_nom=10, marginal_cost=1)
        n.add('Generator', 'local', bus='hub', p_nom=100, marginal_cost=10)
        n.add('Generator', 'backup', bus='sink', p_nom=100, marginal_cost=20)
        n.add('Link', 'in', bus0='far', bus1='hub', carrier='transfer', p_nom=10)
        n.add('Link', 'out', bus0='hub', bus1='sink', carrier='transfer', p_nom=10)
        n.snapshot_weightings.loc[:, 'generators'] = 2
        m = invoke(n.optimize.create_model).value
        selected = aggregate_cell(getattr(n.optimize.expressions, quantity)(
            components=['Link'], carrier='transfer', bus_carrier='electricity',
            at_port=['bus0', 'bus1'], groupby=['carrier', 'bus'],
            nice_names=False, groupby_time='sum'), 'Link', 'transfer', 'hub')
        m.add_constraints(selected <= 8, name='aggregate-restriction')
        solve_edited_model(n)
        assert_close(n.c.links.dynamic.p0.loc['now', ['in', 'out']], [inflow, outflow])
        assert_close(n.c.generators.dynamic.p.loc['now', ['far', 'local', 'backup']],
                     [inflow, outflow-inflow, 6-outflow])
        assert_close(selected.solution.item(), 2*(inflow if quantity == 'supply' else outflow))
        assert_close(n.objective, inflow+10*(outflow-inflow)+20*(6-outflow))
