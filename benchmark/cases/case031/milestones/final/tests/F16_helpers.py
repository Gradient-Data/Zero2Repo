# feature: F16
"""Public rolling-operation driver and small foresight fixture."""
from _helpers import invoke
from F07_helpers import storage_dispatch


def rolling_operation(n, horizon, overlap=0, snapshots=None):
    result = invoke(n.optimize.optimize_with_rolling_horizon,
                    kwargs=dict(snapshots=snapshots, horizon=horizon,
                                overlap=overlap, solver_name='highs',
                                solver_options={'threads': 1}))
    # The rolling entry returns the network, not an optimiser status tuple.
    assert result.value is n
    return n


def foresight_storage(last_cost=30):
    n = storage_dispatch('StorageUnit', demand=(0, 0, 8, 8),
                         p_nom=8, max_hours=1)
    n.c.generators.dynamic.marginal_cost.loc[:, 'supply'] = [1, 2, 20, last_cost]
    return n
