# feature: F18
"""Temporal fixtures and public-result observations."""

import numpy as np
import pandas as pd
from velmora import Network

from _helpers import invoke


def temporal_network(*, periods=False, unit=False, shifted=False):
    """Seven hourly snapshots per period starting 2025-01-03 01:00.

    shifted (with periods) gives the second period its own calendar day,
    starting 2040-03-06 05:00, instead of repeating the first period's times.
    """
    n = Network()
    first = pd.date_range('2025-01-03 01:00', periods=7, freq='h')
    if periods and shifted:
        second = pd.date_range('2040-03-06 05:00', periods=7, freq='h')
        n.set_snapshots(pd.MultiIndex.from_tuples(
            [(2030, t) for t in first] + [(2040, t) for t in second],
            names=['period', 'timestep']))
    else:
        n.set_snapshots(first)
    if periods:
        n.set_investment_periods([2030, 2040])
    populate(n)
    if not unit:
        count = len(n.snapshots)
        n.snapshot_weightings.loc[:, :] = np.column_stack(
            [np.arange(count) + 1, np.arange(count) + 2, np.arange(count) + 3])
    return n


def populate(n):
    """Assets with time series; every paired bound of BOUNDS has two series."""
    n.add('Bus', ['hub', 'far'], v_nom=220)
    count = len(n.snapshots)
    values = np.arange(count, dtype=float) ** 2 + 2

    def cycle(pattern):
        return np.resize(pattern, count)

    n.add('Load', 'demand', bus='hub', p_set=values)
    n.add('Load', 'other', bus='far', p_set=3. * values[::-1] + 1.)
    n.add('Generator', 'plant', bus='hub', p_nom=73,
          p_min_pu=cycle([.1, .2, .3, .4, .2, .1, .2]),
          p_max_pu=cycle([.8, .7, .6, .9, .8, .7, .6]))
    n.add('Generator', 'plant2', bus='far', p_nom=31,
          p_min_pu=cycle([.5, .1, .6, .2, .3, .4, .1]),
          p_max_pu=cycle([.6, .9, .7, .5, .4, .9, .8]))
    n.add('Link', 'tie', bus0='hub', bus1='far', p_nom=40,
          p_min_pu=cycle([.2, .6, .1, .5, .3, .2, .4]),
          p_max_pu=cycle([.7, .8, .3, .9, .6, .5, .9]))
    n.add('StorageUnit', 'pond', bus='far', p_nom=17,
          p_min_pu=cycle([.3, .1, .5, .2, .6, .1, .3]),
          p_max_pu=cycle([.4, .9, .8, .3, .7, .6, .5]))
    n.add('Store', 'reservoir', bus='hub', e_nom=123,
          e_min_pu=cycle([.1, .6, .2, .3, .8, .1, .2]),
          e_max_pu=cycle([.9, .7, .4, .8, .9, .5, .7]))
    n.add('Store', 'reservoir2', bus='far', e_nom=56,
          e_min_pu=cycle([.4, .2, .7, .1, .3, .6, .2]),
          e_max_pu=cycle([.5, .8, .9, .6, .3, .7, .4]))


# (component table, lower attribute, upper attribute, asset)
BOUNDS = [('generators', 'p_min_pu', 'p_max_pu', 'plant'),
          ('generators', 'p_min_pu', 'p_max_pu', 'plant2'),
          ('links', 'p_min_pu', 'p_max_pu', 'tie'),
          ('storage_units', 'p_min_pu', 'p_max_pu', 'pond'),
          ('stores', 'e_min_pu', 'e_max_pu', 'reservoir'),
          ('stores', 'e_min_pu', 'e_max_pu', 'reservoir2')]
SERIES = [('loads', 'p_set', 'demand'), ('loads', 'p_set', 'other')]


def long_network(*, periods=False):
    """Several calendar days; the periods differ in day, start and length."""
    n = Network()
    first = pd.date_range('2025-01-03 22:00', periods=40, freq='h')
    if periods:
        second = pd.date_range('2040-03-06 05:00', periods=32, freq='h')
        n.set_snapshots(pd.MultiIndex.from_tuples(
            [(2030, t) for t in first] + [(2040, t) for t in second],
            names=['period', 'timestep']))
        n.set_investment_periods([2030, 2040])
    else:
        n.set_snapshots(first)
    populate(n)
    count = len(n.snapshots)
    n.snapshot_weightings.loc[:, :] = np.column_stack(
        [np.arange(count) + 1, np.arange(count) + 2, np.arange(count) + 3])
    return n


def check_group_values(source, result, label, sources, rules=None):
    """Compare one representative row with the rule applied to its members."""
    rules = rules or {}
    defaults = {'e_max_pu': 'min', 'e_min_pu': 'max'}

    def rule(attr):
        return rules.get(attr, defaults.get(attr, 'mean'))

    np.testing.assert_allclose(result.n.snapshot_weightings.loc[label],
                               source.snapshot_weightings.loc[sources].sum())
    for table, attr, asset in SERIES:
        series = source.c[table].dynamic[attr].loc[sources, asset]
        assert np.isclose(result.n.c[table].dynamic[attr].loc[label, asset],
                          series.agg(rule(attr)))
    for table, low, high, asset in BOUNDS:
        dynamic = source.c[table].dynamic
        upper = dynamic[high].loc[sources, asset].agg(rule(high))
        lower = dynamic[low].loc[sources, asset].agg(rule(low))
        reduced = result.n.c[table].dynamic
        assert np.isclose(reduced[high].loc[label, asset], upper)
        assert np.isclose(reduced[low].loc[label, asset], min(lower, upper))


def temporal_call(entry, *args, **kwargs):
    result = invoke(entry, *args, kwargs=kwargs)
    assert result.exception is None
    return result.value


def temporal_static_unchanged(source, reduced):
    for component in ['buses', 'loads', 'generators', 'links', 'storage_units', 'stores']:
        before = source.c[component].static
        after = reduced.c[component].static
        assert set(after.index) == set(before.index)
        assert set(before.columns) <= set(after.columns)
        pd.testing.assert_frame_equal(before, after.loc[before.index, before.columns],
                                      check_dtype=False, check_index_type=False,
                                      check_column_type=False, check_names=False,
                                      check_frame_type=False)


def interval_labels(snapshots, hours):
    """Expected group start for each snapshot under a fixed whole-hour interval.

    Groups begin at midnight of the first represented day (separately in each
    investment period) and then at successive interval boundaries; a snapshot
    belongs to the group whose start it reaches and whose next boundary it
    does not.  Computed from the PRD rule, not from product output.
    """
    step = pd.Timedelta(hours=hours)
    if isinstance(snapshots, pd.MultiIndex):
        labels = []
        for period in snapshots.unique('period'):
            times = snapshots[snapshots.get_level_values('period') == period]
            times = pd.DatetimeIndex(times.get_level_values('timestep'))
            labels += [(period, t) for t in interval_labels(times, hours)]
        return labels
    anchor = snapshots[0].normalize()
    return [anchor + ((t - anchor) // step) * step for t in snapshots]


def temporal_groups(source, result, assignment):
    assert result.snapshot_map.index.tolist() == source.snapshots.tolist()
    assert result.snapshot_map.tolist() == assignment
    assert set(result.n.snapshots) == set(assignment)
    temporal_static_unchanged(source, result.n)


def temporal_partition(source, result, keys):
    """Check the snapshot map against an expected grouping, label-agnostic.

    keys[i] identifies the expected group of source snapshot i.  Members of a
    group share one representative, different groups have different ones, and
    the representatives are exactly the result snapshots.  Returns
    (representative, source snapshots) pairs in expected-group order.
    """
    mapping = result.snapshot_map
    assert mapping.index.tolist() == source.snapshots.tolist()
    values = mapping.tolist()
    groups = {}
    for position, key in enumerate(keys):
        groups.setdefault(key, []).append(position)
    pairs = []
    for positions in groups.values():
        labels = {values[i] for i in positions}
        assert len(labels) == 1, labels
        pairs.append((values[positions[0]], source.snapshots[positions]))
    assert len({label for label, _ in pairs}) == len(pairs)
    assert set(result.n.snapshots) == {label for label, _ in pairs}
    assert len(result.n.snapshots) == len(pairs)
    temporal_static_unchanged(source, result.n)
    return pairs


def check_segment_result(n, result, excluded=None):
    """Check every promised segment quantity through the public result tables."""
    m, mapping = result.n, result.snapshot_map
    assert mapping.index.tolist() == n.snapshots.tolist()
    assert len(m.snapshots) == 3
    assert set(mapping) == set(m.snapshots)
    temporal_static_unchanged(n, m)
    actual_excluded = ['e_min_pu'] if excluded is None else excluded
    for label in m.snapshots:
        positions = np.flatnonzero(mapping.to_numpy() == label)
        assert len(positions) > 0
        assert positions.tolist() == list(range(positions[0], positions[-1] + 1))
        assert label == n.snapshots[positions[0]]
        np.testing.assert_allclose(m.snapshot_weightings.loc[label], len(positions))
        sources = n.snapshots[positions]
        def representative(component, attr, asset):
            series = n.c[component].dynamic[attr][asset]
            return (series.loc[label] if attr in actual_excluded
                    else series.loc[sources].mean())
        for component, attr, asset in SERIES:
            assert np.isclose(m.c[component].dynamic[attr].loc[label, asset],
                              representative(component, attr, asset))
        # Every paired bound with two series is corrected, in every category.
        for component, low, high, asset in BOUNDS:
            upper = representative(component, high, asset)
            lower = min(representative(component, low, asset), upper)
            assert np.isclose(m.c[component].dynamic[high].loc[label, asset], upper)
            assert np.isclose(m.c[component].dynamic[low].loc[label, asset], lower)
    np.testing.assert_allclose(m.snapshot_weightings.sum(), n.snapshot_weightings.sum())
