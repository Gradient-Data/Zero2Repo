# feature: F07
"""Acceptance tests for storage energy, carrier conversion and port delivery."""
import logging
import numpy as np
import pandas as pd
from velmora.consistency import ConsistencyError
from _helpers import invoke
from F06_helpers import solve_dispatch, assert_close
from F07_helpers import storage_dispatch, storage_fields, port_network


def test_joint_and_independent_storage_ratings_and_defaults():
    for component, attrs, available in [
        ('StorageUnit', {}, 10), ('StorageUnit', {'max_hours': 2}, 16),
        ('Store', {}, 10), ('Store', {'e_nom': 16}, 16)]:
        n = storage_dispatch(component, demand=(0, 0, 8, 8), **attrs)
        n.c.generators.dynamic.marginal_cost.loc[:, 'supply'] = [1, 1, 20, 20]
        solve_dispatch(n)
        p, e = storage_fields(n, component)
        assert_close(p.iloc[:2].sum(), -available)
        assert_close(e.iloc[1], available)
        assert_close(p.iloc[2:].sum(), available)
        assert_close(e, -p.cumsum())
        assert_close(e.iloc[-1], 0)
        assert_close(n.objective, available + 20*(16-available))
        if component == 'StorageUnit':
            c = n.c.storage_units.dynamic
            assert_close(c.p_dispatch['buffer']-c.p_store['buffer'], p)
            assert (c.p_dispatch['buffer'] <= 10+1e-5).all()
            assert (c.p_store['buffer'] <= 10+1e-5).all()


    # A single cheap charging interval exposes the power rating separately
    # from energy duration; the independent Store can exceed that power.
    for component, attrs, available in [
        ('StorageUnit', {'max_hours': 2}, 10),
        ('Store', {'e_nom': 20}, 16)]:
        n = storage_dispatch(component, demand=(0, 16), **attrs)
        solve_dispatch(n)
        assert_close(storage_fields(n, component)[0], [-available, available])
    n = storage_dispatch('StorageUnit', demand=(15,), max_hours=2,
                         state_of_charge_initial=20)
    solve_dispatch(n)
    assert_close(storage_fields(n, 'StorageUnit')[0], 10)
    assert_close(storage_fields(n, 'StorageUnit')[1], 10)


def test_losses_efficiencies_inflow_spill_and_weighted_costs():
    for component in ['StorageUnit', 'Store']:
        attrs = dict(standing_loss=.1, marginal_cost=3, marginal_cost_storage=2)
        if component == 'StorageUnit':
            attrs.update(max_hours=2, state_of_charge_initial=10,
                         efficiency_store=.8, efficiency_dispatch=.5,
                         p_store_set=[2, 0], p_dispatch_set=[0, 1],
                         inflow=[1, 20], spill_cost=7,
                         state_of_charge_set=[15.2, 20])
        else:
            attrs.update(e_nom=30, e_initial=10, p_set=[-2, 1])
        n = storage_dispatch(component, demand=(4, 4), **attrs)
        n.snapshot_weightings.loc[:, 'stores'] = [2, 3]
        n.snapshot_weightings.loc[:, 'objective'] = [5, 7]
        n.snapshot_weightings.loc[:, 'generators'] = [11, 13]
        solve_dispatch(n)
        p, e = storage_fields(n, component)
        # The reference inserts initial energy directly; losses apply to
        # energy carried from an earlier modelled snapshot.
        if component == 'StorageUnit':
            assert_close(p, [-2, 1])
            assert_close(e, [15.2, 20])
            spill = n.c.storage_units.dynamic.spill['buffer']
            expected_spill = [0, (15.2*.9**3 + 60 - 6 - 20)/3]
            assert_close(spill, expected_spill)
            assert (spill >= -1e-5).all() and (spill <= [1, 20]).all()
            storage_cost = 7*3 + np.dot([5, 7], 2*e+7*spill)
        else:
            assert_close(p, [-2, 1])
            assert_close(e, [14, 14*.9**3-3])
            storage_cost = np.dot([5, 7], 3*p+2*e)
        assert_close(n.c.generators.dynamic.p['supply'], [6, 3])
        assert_close(n.objective, 5*6 + 7*20*3 + storage_cost)


def test_energy_bounds_targets_and_separate_power_targets():
    for component in ['StorageUnit', 'Store']:
        attrs = ({'state_of_charge_set': [4, 2], 'p_store_set': [5, 0],
                  'p_dispatch_set': [1, 2], 'p_set': [-4, 2]}
                 if component == 'StorageUnit' else
                 {'e_set': [4, 2], 'e_min_pu': .2, 'e_max_pu': .4})
        n = storage_dispatch(component, demand=(4, 4), **attrs)
        solve_dispatch(n)
        p, e = storage_fields(n, component)
        assert_close(p, [-4, 2])
        assert_close(e, [4, 2])
        if component == 'StorageUnit':
            assert_close(n.c.storage_units.dynamic.p_store['buffer'], [5, 0])
            assert_close(n.c.storage_units.dynamic.p_dispatch['buffer'], [1, 2])
        # Each target must remain subject to the physical energy boundaries.
        for bad in [11, -1]:
            key = 'state_of_charge_set' if component == 'StorageUnit' else 'e_set'
            n = storage_dispatch(component, demand=(4,), **{key: bad})
            result = invoke(n.optimize, kwargs={'solver_name': 'highs'})
            assert result.value == ('warning', 'infeasible')
        n = storage_dispatch(component, demand=(4, 4), p_set=[-3, 2])
        solve_dispatch(n)
        assert_close(storage_fields(n, component)[0], [-3, 2])
        assert_close(storage_fields(n, component)[1], [3, 1])
        # No energy may be supplied from an omitted initial level.
        n = storage_dispatch(component, demand=(4,))
        solve_dispatch(n)
        assert_close(storage_fields(n, component)[0], 0)


    n = storage_dispatch('Store', e_min_pu=.2, e_max_pu=.4)
    solve_dispatch(n)
    p, e = storage_fields(n, 'Store')
    assert_close(e.iloc[0], 4)
    assert_close(e.iloc[-1], 2)
    assert_close(p.iloc[1:].sum(), 2)


def test_initial_cyclic_and_independent_period_boundaries():
    for component in ['StorageUnit', 'Store']:
        initial = 'state_of_charge_initial' if component == 'StorageUnit' else 'e_initial'
        cyclic = 'cyclic_state_of_charge' if component == 'StorageUnit' else 'e_cyclic'
        initial_period = initial+'_per_period'
        cyclic_period = cyclic+'_per_period'
        for mode in ['initial', 'cyclic', 'period_initial', 'period_cyclic']:
            attrs = {initial: 6}
            if 'cyclic' in mode:
                # Deliberately outside the capacity: cyclic must ignore this.
                attrs.update({initial: 99, cyclic: True})
            if mode.startswith('period'):
                attrs[cyclic_period if 'cyclic' in mode else initial_period] = True
            n = storage_dispatch(component, demand=(4, 4), **attrs)
            if mode.startswith('period'):
                n.set_investment_periods([2030, 2040])
                n.c.loads.dynamic.p_set.loc[2040, 'demand'] = [3, 5]
                # Energy carried from cheap 2030 into dear 2040 would pay off,
                # so per-period boundaries must really isolate the periods,
                # even when the horizon-wide cyclic flag is also set.
                n.c.generators.dynamic.marginal_cost.loc[2040, 'supply'] = 20
            solve_dispatch(n, **({'multi_investment_periods': True}
                                 if mode.startswith('period') else {}))
            p, e = storage_fields(n, component)
            groups = [p.index] if not mode.startswith('period') else [
                p.index[p.index.get_level_values(0) == year] for year in [2030, 2040]]
            for rows in groups:
                pp, ee = p.loc[rows], e.loc[rows]
                boundary = ee.iloc[-1] if 'cyclic' in mode else 6
                assert_close(ee, boundary-pp.cumsum())
                assert_close(pp.sum(), 0 if 'cyclic' in mode else 6)
                if 'cyclic' not in mode:
                    assert_close(ee.iloc[-1], 0)


def test_link_multiport_efficiency_signs_defaults_and_costs():
    for mode in ['default', 'single', 'multi']:
        n = port_network()
        attrs = {} if mode == 'default' else {'efficiency': [.5, .8]}
        if mode == 'multi':
            attrs.update(bus2='heat', efficiency2=[.3, .4],
                         bus3='aux', efficiency3=-.2)
            n.add('Load', 'heat', bus='heat', p_set=[3, 4])
        n.add('Link', 'convert', bus0='fuel', bus1='product', p_nom=10,
              marginal_cost=5, **attrs)
        n.add('Load', 'product', bus='product', p_set=[5, 8] if mode != 'default' else [6, 9])
        solve_dispatch(n)
        d = n.c.links.dynamic
        q = np.array([6, 9] if mode == 'default' else [10, 10])
        assert_close(d.p0['convert'], q)
        assert_close(d.p1['convert'], -np.array([6, 9] if mode == 'default' else [5, 8]))
        if mode == 'multi':
            assert_close(d.p2['convert'], [-3, -4])
            assert_close(d.p3['convert'], [2, 2])
            assert_close(n.c.generators.dynamic.p['aux'], [2, 2])
        assert_close(n.c.generators.dynamic.p['fuel'], q)
        assert_close(n.objective, 7*q.sum() + (12 if mode == 'multi' else 0))


def test_process_signed_rates_throughput_defaults_and_costs():
    for explicit in [False, True]:
        n = port_network()
        attrs = {}
        if explicit:
            attrs.update(rate0=-2, rate1=[.5, 1], bus2='heat', rate2=.3,
                         bus3='aux', rate3=-.4)
            n.add('Load', 'heat', bus='heat', p_set=[3, 3])
        n.add('Process', 'convert', bus0='fuel', bus1='product', p_nom=10,
              marginal_cost=5, **attrs)
        n.add('Load', 'product', bus='product', p_set=[5, 10] if explicit else [6, 9])
        solve_dispatch(n)
        d = n.c.processes.dynamic
        q = np.array([10, 10] if explicit else [6, 9])
        assert_close(d.p['convert'], q)
        assert_close(d.p0['convert'], (2 if explicit else 1)*q)
        assert_close(d.p1['convert'], -np.array([5, 10] if explicit else [6, 9]))
        if explicit:
            assert_close(d.p2['convert'], [-3, -3])
            assert_close(d.p3['convert'], [4, 4])
            assert_close(n.c.generators.dynamic.p['aux'], [4, 4])
        assert_close(n.c.generators.dynamic.p['fuel'], (2 if explicit else 1)*q)
        assert_close(n.objective, (9 if explicit else 7)*q.sum() + (24 if explicit else 0))


def test_elapsed_delay_zero_cyclic_noncyclic_and_period_isolation():
    # Cumulative starts are 0,1,3,4,6,7; three hours is two rows,
    # not three rows. All arrivals align exactly, including modulo nine.
    for component in ['Link', 'Process']:
        for mode in ['default', 'zero', 'cyclic', 'noncyclic', 'periods', 'periods_noncyclic']:
            periods = mode.startswith('periods')
            snapshots = pd.MultiIndex.from_product([[2030, 2040], range(6)]) if periods else range(6)
            n = port_network(snapshots)
            repeat = 2 if periods else 1
            n.snapshot_weightings.loc[:, 'generators'] = [1, 2, 1, 2, 1, 2]*repeat
            n.snapshot_weightings.loc[:, 'stores'] = 4
            n.snapshot_weightings.loc[:, 'objective'] = 2
            demand = np.array([6, 12, 18, 24, 30, 36] + ([7, 14, 21, 28, 35, 42] if periods else []))
            n.add('Load', 'product', bus='product', p_set=demand)
            n.add('Generator', 'backup', bus='product', p_nom=100, marginal_cost=50)
            delaykey = 'delay' if component == 'Link' else 'delay1'
            cyclickey = 'cyclic_delay' if component == 'Link' else 'cyclic_delay1'
            attrs = {} if mode == 'default' else {delaykey: 0 if mode == 'zero' else 3}
            if mode.endswith('noncyclic'):
                attrs[cyclickey] = False
            n.add(component, 'convert', bus0='fuel', bus1='product', p_nom=100,
                  marginal_cost=1, **attrs)
            solve_dispatch(n, **({'multi_investment_periods': True} if periods else {}))
            d = n.components[component].dynamic
            q = d['p0' if component == 'Link' else 'p']['convert'].to_numpy()
            arrival = -d.p1['convert'].to_numpy()
            for offset in range(0, len(demand), 6):
                target = demand[offset:offset+6]
                if mode in ['default', 'zero']:
                    source, delivered = target, target
                elif mode.endswith('noncyclic'):
                    source, delivered = np.r_[target[2:], 0, 0], np.r_[0, 0, target[2:]]
                else:
                    source, delivered = target[[2, 3, 4, 5, 0, 1]], target
                assert_close(q[offset:offset+6], source)
                assert_close(arrival[offset:offset+6], delivered)
            assert_close(n.c.generators.dynamic.p['fuel'], q)
            assert_close(n.c.generators.dynamic.p['backup'], demand-arrival)


    for component in ['Link', 'Process']:
        n = port_network(range(6))
        n.snapshot_weightings.loc[:, 'generators'] = [1, 2, 1, 2, 1, 2]
        q = np.array([3, 5, 7, 9, 11, 13])
        attrs = ({'delay': 3, 'efficiency2': .5} if component == 'Link' else
                 {'delay0': 3, 'delay1': 3, 'rate2': .5})
        n.add(component, 'convert', bus0='fuel', bus1='product', bus2='heat',
              p_nom=20, p_set=q, delay2=6, marginal_cost=1, **attrs)
        n.add('Load', 'product', bus='product', p_set=np.roll(q, 2))
        n.add('Load', 'heat', bus='heat', p_set=.5*np.roll(q, 4))
        solve_dispatch(n)
        d = n.components[component].dynamic
        assert_close(d['p0' if component == 'Link' else 'p']['convert'], q)
        assert_close(d.p1['convert'], -np.roll(q, 2))
        assert_close(d.p2['convert'], -.5*np.roll(q, 4))
        assert_close(n.c.generators.dynamic.p['fuel'],
                     q if component == 'Link' else np.roll(q, 2))


def test_invalid_delay_diagnostics_and_legal_boundaries():
    for component in ['Link', 'Process']:
        key = 'delay' if component == 'Link' else 'delay1'
        for delay in [0, 2, -1, 5]:
            n = port_network(range(3))
            n.snapshot_weightings.loc[:, 'generators'] = [1, 2, 1]
            n.add(component, 'convert', bus0='fuel', bus1='product',
                  p_nom=10, **{key: delay})
            if delay >= 0 and delay < 4:
                n.consistency_check(strict=['dispatch_delays'])
            else:
                warning = invoke(n.consistency_check, kwargs={'strict': []})
                assert any(r.levelno == logging.WARNING and r.name == 'velmora.consistency'
                           for r in warning.logs)
                failure = invoke(n.consistency_check,
                                 kwargs={'strict': ['dispatch_delays']},
                                 expected_exceptions=(ConsistencyError,))
                assert isinstance(failure.exception, ConsistencyError)
    # The limit is one investment period's duration (4 hours), not the
    # whole two-period horizon (8 hours).
    for component in ['Link', 'Process']:
        key = 'delay' if component == 'Link' else 'delay1'
        for delay in [3, 5]:
            n = port_network(pd.MultiIndex.from_product([[2030, 2040], range(3)]))
            n.snapshot_weightings.loc[:, 'generators'] = [1, 2, 1]*2
            n.add(component, 'convert', bus0='fuel', bus1='product',
                  p_nom=10, **{key: delay})
            if delay == 3:
                n.consistency_check(strict=['dispatch_delays'])
            else:
                failure = invoke(n.consistency_check,
                                 kwargs={'strict': ['dispatch_delays']},
                                 expected_exceptions=(ConsistencyError,))
                assert isinstance(failure.exception, ConsistencyError)
