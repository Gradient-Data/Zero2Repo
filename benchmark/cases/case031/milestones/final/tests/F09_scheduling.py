# feature: F09
"""Acceptance outcomes for commitment, operating history and maintenance."""
import numpy as np
import pytest
from velmora.consistency import ConsistencyError
from F06_helpers import solve_dispatch, assert_close
from F08_helpers import investment_flow
from F09_helpers import (scheduled_asset, commitment_result,
                         check_binary_schedule, check_maintenance)


def test_commitment_operation():
    for component in ('Generator', 'Link', 'Process'):
        n = scheduled_asset(component, (0, 8, 8, 0, 0, 8), committable=True,
                            p_min_pu=.4, p_max_pu=.8, min_up_time=2,
                            min_down_time=2, up_time_before=0,
                            down_time_before=2, start_up_cost=1,
                            shut_down_cost=1)
        solve_dispatch(n)
        p, status = check_binary_schedule(n, component, initial=0,
                                         maximum=.8, up=2, down=2)
        assert_close(status, [0, 1, 1, 0, 0, 1])
        assert_close(p, [0, 8, 8, 0, 0, 8])
        # Ordinary ramping must move real dispatch onto the expensive backup.
        r = scheduled_asset(component, (4, 8, 4), committable=True,
                            p_min_pu=.1, ramp_limit_up=.2, ramp_limit_down=.2)
        solve_dispatch(r)
        assert_close(investment_flow(r, component), [4, 6, 4])
        # Mid-horizon minimum durations bind: standby cost alone would stop
        # after one snapshot; an early stop forbids the cheap restart.
        u = scheduled_asset(component, (0, 6, 0, 0), committable=True,
                            min_up_time=2, min_down_time=2, up_time_before=0,
                            down_time_before=1, stand_by_cost=1)
        solve_dispatch(u)
        assert_close(commitment_result(u, component)[0], [0, 1, 1, 0])
        d = scheduled_asset(component, (8, 0, 6, 0), committable=True,
                            p_min_pu=.4, min_down_time=2)
        solve_dispatch(d)
        assert_close(commitment_result(d, component)[0], [1, 0, 0, 0])
        assert_close(investment_flow(d, component), [8, 0, 0, 0])


def test_event_and_standby_costs():
    for costs in ({}, dict(start_up_cost=7, shut_down_cost=11, stand_by_cost=3)):
        n = scheduled_asset(demand=(0, 6, 0, 6, 0), committable=True,
                            p_min_pu=.4, up_time_before=0,
                            down_time_before=1, **costs)
        weights = np.array([2, 3, 5, 7, 11])
        n.snapshot_weightings.loc[:, 'objective'] = weights
        solve_dispatch(n)
        p, status = check_binary_schedule(n, initial=0, tight_events=bool(costs))
        _, starts, stops = commitment_result(n)
        assert_close(p, [0, 6, 0, 6, 0])
        expected = (p*weights).sum()
        if costs:
            expected += 7*starts.sum()+11*stops.sum()+3*(weights*status).sum()
        assert_close(n.objective, expected)


def test_expansion_modularity_and_relaxation():
    for component in ('Generator', 'Link', 'Process'):
        # No finite maximum is supplied: commitment must still expand.
        n = scheduled_asset(component, (0, 7, 0), committable=True,
                            p_nom=0, p_nom_extendable=True,
                            capital_cost=2, p_min_pu=.4, start_up_cost=1)
        solve_dispatch(n)
        assert_close(n.components[component].static.at['asset', 'p_nom_opt'], 7)
        assert_close(investment_flow(n, component), [0, 7, 0])
        m = scheduled_asset(component, (3, 7), committable=True, p_nom=0,
                            p_nom_extendable=True, p_nom_max=12, p_nom_mod=4,
                            capital_cost=2, stand_by_cost=1)
        solve_dispatch(m)
        assert_close(m.components[component].static.at['asset', 'p_nom_opt'], 8)
        assert_close(commitment_result(m, component)[0], [1, 2])
        assert_close(investment_flow(m, component), [3, 7])
        with pytest.raises(ValueError):
            m.optimize(solver_name='highs', linearized_unit_commitment=True)
    for relaxed in (False, True):
        n = scheduled_asset(demand=(3, 7), committable=True, stand_by_cost=10)
        solve_dispatch(n, linearized_unit_commitment=relaxed)
        assert_close(investment_flow(n, 'Generator'), [3, 7])
        assert_close(commitment_result(n)[0], [.3, .7] if relaxed else [1, 1])


def test_maintenance_events_and_elapsed_hours():
    for component, events in (('Generator', 2), ('Link', 1), ('Process', 1)):
        attrs = dict(maintainable=True, maintenance_duration=3.5)
        if events == 2:
            attrs['maintenance_events'] = events
        n = scheduled_asset(component, (8,)*8, **attrs)
        n.snapshot_weightings.loc[:, 'generators'] = [2, 1, 2, 1, 2, 1, 2, 1]
        solve_dispatch(n)
        maintenance = check_maintenance(n, component, duration=3.5, events=events)
        assert_close(investment_flow(n, component), 8*(1-maintenance))
    n = scheduled_asset(demand=(8,)*4, maintainable=True,
                        maintenance_duration=2, build_year=2030, lifetime=10)
    n.set_investment_periods([2020, 2030])
    solve_dispatch(n, multi_investment_periods=True)
    d = n.c.generators.dynamic
    assert_close(d.maintenance.loc[2020, 'asset'], 0)
    assert_close(d.maintenance_start.loc[2020, 'asset'], 0)
    assert_close(d.maintenance.loc[2030, 'asset'].sum(), 2)
    assert_close(d.maintenance_start.loc[2030, 'asset'].sum(), 1)
    check_maintenance(n, duration=2)


def test_maintenance_capacity_coupling():
    # These branches separate full outage, partial operation, and expansion
    # combined with commitment; no particular optimal event time is required.
    for component in ('Generator', 'Link', 'Process'):
        for mode in ('default', 'partial', 'expanded', 'off'):
            attrs = dict(maintainable=True, maintenance_duration=2)
            if mode != 'default':
                attrs.update(maintenance_pu=.5, committable=True, p_min_pu=.2)
            if mode == 'expanded':
                attrs.update(p_nom=0, p_nom_extendable=True, p_nom_max=10,
                             capital_cost=1)
            if mode == 'off':
                attrs['marginal_cost'] = 200
            n = scheduled_asset(component, (8,)*5, **attrs)
            solve_dispatch(n)
            maintenance = check_maintenance(n, component, duration=2)
            p = investment_flow(n, component).to_numpy()
            if mode == 'off':
                assert_close(p, 0)
                assert_close(commitment_result(n, component)[0], 0)
                assert_close(n.c.generators.dynamic.p['backup'], 8)
            else:
                fraction = 1 if mode == 'default' else .5
                assert_close(p, np.minimum(8, 10*(1-fraction*maintenance)))
                assert_close(n.c.generators.dynamic.p['backup'], 8-p)
                if mode == 'expanded':
                    assert_close(n.components[component].static.at['asset', 'p_nom_opt'], 10)
                if mode != 'default':
                    assert_close(commitment_result(n, component)[0], 1)


def test_maintenance_validation():
    valid = scheduled_asset(demand=(6,)*4, maintainable=True, maintenance_duration=2)
    solve_dispatch(valid)
    check_maintenance(valid, duration=2)
    missing = scheduled_asset(demand=(6,)*4, maintainable=True)
    with pytest.raises(ConsistencyError):
        missing.consistency_check(strict=['maintenance'])
    invalid = [dict(maintenance_duration=0), dict(maintenance_duration=-1),
               dict(maintenance_events=0), dict(maintenance_events=-1),
               dict(maintenance_duration=5),
               dict(maintenance_duration=3, maintenance_events=2),
               dict(p_nom_extendable=True)]
    for change in invalid:
        attrs = dict(maintainable=True, maintenance_duration=2)
        attrs.update(change)
        n = scheduled_asset(demand=(6,)*4, **attrs)
        with pytest.raises(ConsistencyError):
            n.consistency_check(strict=['maintenance'])


def test_history_and_horizon_boundaries():
    n = scheduled_asset(demand=(6, 0, 6), committable=True, p_min_pu=.4)
    solve_dispatch(n)
    assert_close(commitment_result(n)[0], [1, 0, 1])
    assert_close(n.objective, 12)
    # Default online history leaves two of three required snapshots online.
    n = scheduled_asset(demand=(0, 0, 0), committable=True, min_up_time=3,
                        stand_by_cost=1)
    solve_dispatch(n)
    assert_close(commitment_result(n)[0], [1, 1, 0])
    explicit = scheduled_asset(demand=(0, 0, 0), committable=True,
                               min_up_time=4, up_time_before=2, stand_by_cost=1)
    solve_dispatch(explicit)
    assert_close(commitment_result(explicit)[0], [1, 1, 0])
    # Offline history overrides even a simultaneously supplied online history.
    n = scheduled_asset(demand=(6, 6, 6), committable=True, min_down_time=3,
                        up_time_before=8, down_time_before=1)
    solve_dispatch(n)
    assert_close(commitment_result(n)[0], [0, 0, 1])
    assert_close(investment_flow(n, 'Generator'), [0, 0, 6])
    # A start at the horizon end does not create obligations outside it.
    n = scheduled_asset(demand=(0, 0, 6), committable=True, min_up_time=4,
                        up_time_before=0, down_time_before=4, p_min_pu=.4)
    solve_dispatch(n)
    assert_close(commitment_result(n)[0], [0, 0, 1])
    terminal = scheduled_asset(demand=(6, 0), committable=True,
                               min_down_time=4, p_min_pu=.4)
    solve_dispatch(terminal)
    assert_close(commitment_result(terminal)[0], [1, 0])
    # Continued optimisation must use the just-solved off status, not inputs.
    n = scheduled_asset(demand=(0, 6, 6, 6), committable=True, p_min_pu=.4,
                        min_down_time=3, up_time_before=9)
    solve_dispatch(n, snapshots=n.snapshots[:1])
    assert_close(commitment_result(n, rows=n.snapshots[:1])[0], [0])
    solve_dispatch(n, snapshots=n.snapshots[1:])
    assert_close(commitment_result(n, rows=n.snapshots[1:])[0], [0, 0, 1])
    for component in ('Generator', 'Link', 'Process'):
        n = scheduled_asset(component, (0, 8, 8, 0), committable=True,
                            p_min_pu=.1, up_time_before=0, down_time_before=1,
                            ramp_limit_start_up=.3, ramp_limit_shut_down=.2)
        solve_dispatch(n)
        assert_close(investment_flow(n, component), [0, 3, 2, 0])
