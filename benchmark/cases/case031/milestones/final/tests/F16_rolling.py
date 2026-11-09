# feature: F16
"""Acceptance of limited foresight, retained state and window-local maintenance."""
import numpy as np
import pytest
from _helpers import invoke
from F06_helpers import assert_close, solve_dispatch
from F07_helpers import storage_dispatch, storage_fields
from F09_helpers import scheduled_asset, commitment_result, check_binary_schedule
from F16_helpers import rolling_operation, foresight_storage


def test_limited_foresight():
    # No consumption or terminal-energy reward in the first two snapshots:
    # their minimum attainable operating cost is zero. Later expensive demand
    # must not make this window buy energy. The second window can shift eight
    # units from its cheaper snapshot, with operating cost 16 * 20.
    for later_cost in (30, 90):
        n = foresight_storage(later_cost)
        rolling_operation(n, horizon=2, snapshots=n.snapshots)
        p = n.c.generators.dynamic.p.loc[n.snapshots, 'supply']
        assert_close(p.loc[[0, 1]], 0)
        assert_close(20*p.loc[2] + later_cost*p.loc[3], 320)
        flow, energy = storage_fields(n, 'StorageUnit')
        assert_close(p + flow, [0, 0, 8, 8])
        assert_close(energy, [0, 0, 8, 0])
    full = foresight_storage()
    solve_dispatch(full)
    # Full foresight can buy eight units at cost one for the last snapshot.
    assert_close(full.c.generators.dynamic.p['supply'], [8, 0, 8, 0])
    # A requested horizon excluding snapshot zero windows from snapshot one:
    # the first window stores cost-two energy for snapshot two.
    n = foresight_storage()
    rolling_operation(n, horizon=2, snapshots=n.snapshots[1:])
    p = n.c.generators.dynamic.p.loc[[1, 2, 3], 'supply']
    flow, energy = storage_fields(n, 'StorageUnit')
    assert_close(p, [8, 0, 8])
    assert_close(flow.loc[[1, 2, 3]], [-8, 8, 0])
    assert_close(energy.loc[[1, 2, 3]], [8, 0, 0])


def test_retained_physical_and_commitment_history():
    for component, initial in (('Store', {'e_initial': 8, 'e_nom': 8}),
                               ('StorageUnit', {'state_of_charge_initial': 8,
                                                'p_nom': 8, 'max_hours': 1})):
        n = storage_dispatch(component, demand=(2, 2, 2, 2), **initial)
        n.c.generators.dynamic.marginal_cost.loc[:, 'supply'] = 20
        rolling_operation(n, horizon=2)
        flow, energy = storage_fields(n, component)
        assert_close(flow, 2)
        assert_close(energy, [6, 4, 2, 0])
        assert_close(n.c.generators.dynamic.p['supply'], 0)

    ramp = scheduled_asset(demand=(2, 4, 8, 8, 8, 8),
                           ramp_limit_up=.2, ramp_limit_down=.2,
                           marginal_cost=[1, 1, 1, 1, 200, 200])
    rolling_operation(ramp, horizon=2)
    assert_close(ramp.c.generators.dynamic.p['asset'], [2, 4, 6, 8, 6, 4])
    assert_close(ramp.c.generators.dynamic.p['backup'], [0, 0, 2, 0, 2, 4])

    # A start in the first window leaves two mandatory online snapshots.
    # Zero minimum output there permits that obligation to be observed even
    # with zero demand; later positive minimum output forces a real shutdown.
    uc = scheduled_asset(demand=(0, 6, 0, 0, 0, 0, 6, 6),
                         committable=True, min_up_time=3, min_down_time=3,
                         p_min_pu=[.4, .4, 0, 0, .4, .4, .4, .4],
                         up_time_before=0, down_time_before=3,
                         stand_by_cost=1, start_up_cost=1, shut_down_cost=1)
    rolling_operation(uc, horizon=2)
    check_binary_schedule(uc, initial=0,
                          minimum=np.array([.4, .4, 0, 0, .4, .4, .4, .4]),
                          up=3, down=3)
    status, starts, stops = commitment_result(uc)
    assert_close(status, [0, 1, 1, 1, 0, 0, 0, 1])
    assert_close(starts, [0, 1, 0, 0, 0, 0, 0, 1])
    assert_close(stops, [0, 0, 0, 0, 1, 0, 0, 0])
    assert_close(uc.c.generators.dynamic.p['asset'], [0, 6, 0, 0, 0, 0, 0, 6])
    assert_close(uc.c.generators.dynamic.p['backup'], [0, 0, 0, 0, 0, 0, 6, 0])


def test_overlap_reconsiders_only_unretained_decisions():
    plain = foresight_storage()
    rolling_operation(plain, horizon=3)
    assert_close(plain.c.generators.dynamic.p['supply'], [8, 0, 0, 8])
    n = foresight_storage()
    rolling_operation(n, horizon=3, overlap=1)
    # First lookahead buys energy at snapshot zero for snapshot two. The next
    # lookahead retains that purchase but reallocates the energy to the newly
    # visible, more expensive demand, recomputing snapshot two's dispatch.
    assert_close(n.c.generators.dynamic.p['supply'], [8, 0, 8, 0])
    flow, energy = storage_fields(n, 'StorageUnit')
    assert_close(flow, [-8, 0, 0, 8])
    assert_close(energy, [8, 8, 8, 0])
    for overlap in (3, 4):
        invalid = foresight_storage()
        result = invoke(invalid.optimize.optimize_with_rolling_horizon,
                        kwargs=dict(horizon=3, overlap=overlap,
                                    solver_name='highs'),
                        expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)


def test_window_local_maintenance():
    n = scheduled_asset(demand=(8,)*12, maintainable=True,
                        maintenance_duration=2, maintenance_events=2)
    rolling_operation(n, horizon=6)
    d = n.c.generators.dynamic
    for window in (slice(0, 6), slice(6, 12)):
        starts = d.maintenance_start['asset'].to_numpy()[window]
        maintenance = d.maintenance['asset'].to_numpy()[window]
        assert_close(starts, np.round(starts))
        assert_close(starts.sum(), 2)
        assert_close(starts[-1], 0)
        assert_close(maintenance, starts + np.r_[0, starts[:-1]])
        assert_close(d.p['asset'].to_numpy()[window], 8*(1-maintenance))
        assert_close(d.p['backup'].to_numpy()[window], 8*maintenance)

    # Overlapping windows can start a new event instead of continuing one in
    # progress at their boundary. Unique minimum lost-dispatch costs select
    # starts at 1, then 3, then 4 in the three successive windows.
    n = scheduled_asset(demand=(8, 0, 1, 2, 0, 8), maintainable=True,
                        maintenance_duration=2, maintenance_events=1)
    rolling_operation(n, horizon=4, overlap=2)
    d = n.c.generators.dynamic
    assert_close(d.maintenance_start['asset'], [0, 1, 0, 1, 1, 0])
    assert_close(d.maintenance['asset'], [0, 1, 0, 1, 1, 1])
    assert_close(d.p['asset'], [8, 0, 1, 0, 0, 0])
    assert_close(d.p['backup'], [0, 0, 0, 2, 0, 8])
