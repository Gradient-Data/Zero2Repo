# feature: F09
"""Public commitment and maintenance fixtures and outcome checks."""
import numpy as np
from F06_helpers import dispatch_bus, assert_close
from F08_helpers import investment_flow


def scheduled_asset(component='Generator', demand=(6, 0, 6), **attributes):
    n = dispatch_bus(list(demand), range(len(demand)))
    n.add('Generator', 'backup', bus='sink', p_nom=100, marginal_cost=100)
    attrs = dict(p_nom=10, marginal_cost=1)
    attrs.update(attributes)
    if component == 'Generator':
        n.add(component, 'asset', bus='sink', **attrs)
    else:
        n.add('Bus', 'source')
        n.add('Generator', 'fuel', bus='source', p_nom=100, marginal_cost=1)
        n.add(component, 'asset', bus0='source', bus1='sink', **attrs)
    return n


def commitment_result(n, component='Generator', rows=None):
    rows = n.snapshots if rows is None else rows
    d = n.components[component].dynamic
    return tuple(d[field].loc[rows, 'asset'].to_numpy() for field in
                 ('status', 'start_up', 'shut_down'))


def check_binary_schedule(n, component='Generator', initial=1, minimum=.4,
                          maximum=1, up=0, down=0, tight_events=True):
    status, starts, stops = commitment_result(n, component)
    for values in (status, starts, stops):
        assert_close(values, np.round(values))
        assert ((values >= -1e-5) & (values <= 1+1e-5)).all()
    delta = status - np.r_[initial, status[:-1]]
    assert (starts >= np.maximum(delta, 0)-1e-5).all()
    assert (stops >= np.maximum(-delta, 0)-1e-5).all()
    if tight_events:
        assert_close(starts, np.maximum(delta, 0))
        assert_close(stops, np.maximum(-delta, 0))
    p = investment_flow(n, component).to_numpy()
    assert (p >= 10*minimum*status-1e-5).all()
    assert (p <= 10*maximum*status+1e-5).all()
    for t in np.flatnonzero(starts > .5):
        assert_close(status[t:min(len(status), t+up)], 1)
    for t in np.flatnonzero(stops > .5):
        assert_close(status[t:min(len(status), t+down)], 0)
    return p, status


def check_maintenance(n, component='Generator', duration=3, events=1):
    d = n.components[component].dynamic
    starts = d.maintenance_start['asset'].to_numpy()
    maintenance = d.maintenance['asset'].to_numpy()
    assert_close(starts, np.round(starts))
    assert_close(maintenance, np.round(maintenance))
    assert ((starts >= -1e-5) & (starts <= 1+1e-5)).all()
    assert ((maintenance >= -1e-5) & (maintenance <= 1+1e-5)).all()
    assert_close(starts.sum(), events)
    weights = n.snapshot_weightings.generators.to_numpy()
    coverage = np.zeros(len(starts))
    for t in np.flatnonzero(starts > .5):
        end = t
        elapsed = 0
        while end < len(weights) and elapsed < duration-1e-8:
            elapsed += weights[end]
            end += 1
        assert elapsed >= duration-1e-8
        assert elapsed-duration < weights[end-1]+1e-8
        coverage[t:end] += 1
    assert (coverage <= 1).all()
    assert_close(maintenance, coverage)
    return maintenance
