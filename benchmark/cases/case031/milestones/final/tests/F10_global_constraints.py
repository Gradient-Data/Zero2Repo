# feature: F10
"""Acceptance outcomes for resource, transmission and growth policies."""
import numpy as np
import pytest
from _helpers import invoke
from F06_helpers import solve_dispatch, assert_close, dispatch_bus
from F10_helpers import (resource_supply, transmission_policy, technology_policy,
                         growth_policy)


def test_primary_energy_efficiency_weights_and_storage_depletion():
    for sense in ('<=', '>=', '=='):
        n = resource_supply('primary_energy', sense, 6, expensive=sense == '>=')
        solve_dispatch(n)
        p = n.c.generators.dynamic.p
        assert_close((p['fuel'] * [2, 3]).sum(), 10)
        assert_close(p.sum(axis=1), 4)
        assert_close(n.objective, 210)
    # Both storage public entries contribute physical depletion, not dispatch
    # weighted a second time. The coefficient belongs to the storage carrier.
    for component in ('Store', 'StorageUnit'):
        for cyclic in (False, True):
            n = dispatch_bus(0, ('a', 'b'))
            n.c.loads.static.loc['demand', 'p_set'] = 0
            n.add('Load', 'varying', bus='sink', p_set=[0, 4])
            n.add('Carrier', 'stock', co2_emissions=.4)
            n.add('Generator', 'supply', bus='sink', p_nom=10, marginal_cost=10)
            # Lossy discharge separates stored-energy depletion from dispatch.
            attrs = dict(e_nom=6, e_initial=6, e_cyclic=cyclic) if component == 'Store' else dict(
                p_nom=6, max_hours=1, state_of_charge_initial=6,
                cyclic_state_of_charge=cyclic, efficiency_dispatch=.5)
            delivered = 2 if component == 'Store' else 1
            n.add(component, 'stock', bus='sink', carrier='stock', **attrs)
            n.add('GlobalConstraint', 'policy', type='primary_energy',
                  carrier_attribute='co2_emissions', sense='<=', constant=.8)
            solve_dispatch(n)
            energy = n.components[component].dynamic['e' if component == 'Store' else 'state_of_charge']
            if cyclic:
                assert_close(n.c.generators.dynamic.p['supply'].sum(), 4)
                assert_close(n.objective, 40)
            else:
                assert_close(6-energy.at['b', 'stock'], 2)
                assert_close(n.c.generators.dynamic.p['supply'].sum(), 4-delivered)
                assert_close(n.objective, 10*(4-delivered))


def test_operational_production_weights_comparisons_and_storage():
    for sense in ('<=', '>=', '=='):
        n = resource_supply('operational_limit', sense, 10, expensive=sense == '>=')
        solve_dispatch(n)
        assert_close((n.c.generators.dynamic.p['fuel'] * [2, 3]).sum(), 10)
        assert_close(n.c.generators.dynamic.p.sum(axis=1), 4)
        assert_close(n.objective, 210)
        for component in ('Store', 'StorageUnit'):
            n = dispatch_bus(4)
            n.add('Carrier', 'stock', co2_emissions=7)
            n.add('Generator', 'backup', bus='sink', p_nom=10, marginal_cost=10)
            attrs = dict(e_nom=6, e_initial=6) if component == 'Store' else dict(
                p_nom=6, max_hours=1, state_of_charge_initial=6, efficiency_dispatch=1)
            n.add(component, 'stock', bus='sink', carrier='stock',
                  marginal_cost=20 if sense == '>=' else 0, **attrs)
            n.add('GlobalConstraint', 'policy', type='operational_limit',
                  carrier_attribute='stock', sense=sense, constant=2)
            solve_dispatch(n)
            energy = n.components[component].dynamic['e' if component == 'Store' else 'state_of_charge']
            assert_close(6-energy.at['now', 'stock'], 2)
            assert_close(n.c.generators.dynamic.p['backup'], 2)


def test_transmission_volume_and_investment_comparisons():
    for kind, coefficient in [('transmission_volume_expansion_limit', 'length'),
                               ('transmission_expansion_cost_limit', 'capital_cost')]:
        for sense in ('<=', '>=', '=='):
            n = transmission_policy(kind, sense)
            # For a lower bound, make expansion costly so the bound is active.
            if sense == '>=':
                n.c.generators.static.loc[['AC-backup', 'DC-backup'], 'marginal_cost'] = 1
            solve_dispatch(n)
            line = n.c.lines.static.loc['AC']
            link = n.c.links.static.loc['DC']
            total = line.s_nom_opt*line[coefficient]+link.p_nom_opt*link[coefficient]
            assert_close(total, n.c.global_constraints.static.at['policy', 'constant'])
            assert_close(n.c.links.static.at['other', 'p_nom_opt'], 6)
            assert_close(n.c.links.static.at['fixed', 'p_nom_opt'], 50)
            for carrier, component in [('AC', 'Line'), ('DC', 'Link'), ('other', 'Link')]:
                flow = n.components[component].dynamic.p0.at['now', carrier]
                assert_close(flow+n.c.generators.dynamic.p.at['now', carrier+'-backup'], 6)
            # Independent accounting verifies investment is part of real cost.
            capital = line.s_nom_opt*5+link.p_nom_opt*7+6*13
            operating = sum(n.c.generators.dynamic.p.at['now', name]*row.marginal_cost
                            for name, row in n.c.generators.static.iterrows())
            assert_close(n.objective, capital+operating)


def test_technology_capacity_scope_duals_and_infeasibility():
    for sense in ('<=', '>=', '=='):
        n = technology_policy(sense, 4)
        solve_dispatch(n)
        assert_close(n.c.generators.static.at['a-new', 'p_nom_opt'], 4)
        assert_close(n.c.generators.static.at['b-new', 'p_nom_opt'], 0 if sense == '>=' else 9)
        # Perturbation stays within one nondegenerate linear segment.
        shifted = technology_policy(sense, 4.1)
        solve_dispatch(shifted)
        marginal = (shifted.objective-n.objective)/.1
        assert abs(marginal) > 1
        assert_close(n.c.global_constraints.static.at['policy', 'mu'], marginal)
    n = technology_policy('<=', 4, period=True)
    solve_dispatch(n, multi_investment_periods=True)
    assert_close(n.c.generators.static.loc[['a-2030', 'a-2040', 'b-2030', 'b-2040'], 'p_nom_opt'],
                 [9, 4, 9, 9])
    # No bus restriction means the whole carrier, not one arbitrary bus.
    n = technology_policy('==', 7)
    n.c.global_constraints.static.at['policy', 'bus'] = ''
    solve_dispatch(n)
    assert_close(n.c.generators.static.loc[['a-new', 'b-new'], 'p_nom_opt'].sum(), 7)
    n = technology_policy('<=', 4)
    n.add('GlobalConstraint', 'contradiction', type='tech_capacity_expansion_limit',
          carrier_attribute='target', bus='a', sense='>=', constant=5)
    result = invoke(n.optimize, kwargs={'solver_name': 'highs', 'solver_options': {'threads': 1}})
    assert result.value == ('warning', 'infeasible'), result


def test_carrier_growth_first_activity_and_period_scope_rejection():
    for absolute, relative, expected in [(3, 0, [3, 3, 3]), (3, .5, [3, 4.5, 5.25]),
                                         (np.inf, .5, [30, 0, 0])]:
        n = growth_policy(absolute, relative)
        solve_dispatch(n, multi_investment_periods=True)
        assert_close(n.c.generators.static.loc[['early', 'middle', 'last'], 'p_nom_opt'], expected)
        cumulative = np.cumsum(expected)
        assert_close(n.c.generators.dynamic.p.loc[:, ['early', 'middle', 'last']].sum(axis=1), cumulative)
        assert_close(n.c.generators.dynamic.p['backup'], 30-cumulative)
    # Exercise the scope on a real dispatch constraint before rejecting its
    # use without the multi-period optimisation mode.
    n = resource_supply('operational_limit', '<=', 5)
    n.set_investment_periods([2030, 2040])
    n.c.global_constraints.static.at['policy', 'investment_period'] = 2040
    solve_dispatch(n, multi_investment_periods=True)
    p = n.c.generators.dynamic.p['fuel']
    assert_close((p.loc[2030]*[2, 3]).sum(), 20)
    assert_close((p.loc[2040]*[2, 3]).sum(), 5)
    for kind, attr in [('primary_energy', 'co2_emissions'), ('operational_limit', 'fuel')]:
        n = resource_supply(kind, '<=', 5)
        n.c.global_constraints.static.at['policy', 'investment_period'] = 2040
        with pytest.raises(ValueError):
            n.optimize(solver_name='highs', solver_options={'threads': 1})
