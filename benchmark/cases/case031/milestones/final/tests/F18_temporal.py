# feature: F18
"""Acceptance checks for temporal aggregation through public accessors."""

import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from velmora import Network

from _helpers import invoke, run_command, isolated_site
from F18_helpers import (temporal_network, temporal_call, temporal_groups,
                         temporal_static_unchanged, long_network, interval_labels,
                         temporal_partition, check_group_values, BOUNDS, SERIES, check_segment_result)

CUSTOM_RULES = {'p_set': 'sum', 'e_max_pu': 'max', 'p_min_pu': 'sum',
                'p_max_pu': 'min'}
INTERVAL_HOURS = {'3h': 3, '5h': 5, '1D': 24, '2D': 48}


def period_groups(snapshots):
    """Source snapshots split by investment period (one group without)."""
    if isinstance(snapshots, pd.MultiIndex):
        periods = snapshots.get_level_values('period')
        return [snapshots[periods == p] for p in periods.unique()]
    return [snapshots]


def test_resample_and_mapped_aggregation():
    # Starts off the interval boundary and ends in a partial group.
    for periods in [False, True]:
        n = temporal_network(periods=periods)
        labels = pd.to_datetime(['2025-01-03 00:00', '2025-01-03 03:00',
                                 '2025-01-03 06:00'])
        base = [labels[0]] * 2 + [labels[1]] * 3 + [labels[2]] * 2
        assignment = ([(p, t) for p in [2030, 2040] for t in base]
                      if periods else base)
        mapping = pd.Series(base, index=n.snapshots) if not periods else None
        for custom in [False, True]:
            rules = {'p_set': 'sum', 'e_max_pu': 'max', 'p_min_pu': 'sum',
                     'p_max_pu': 'min'} if custom else None
            outcomes = [temporal_call(n.cluster.temporal.get_resample_result, '3h',
                                      aggregation_rules=rules)]
            if mapping is not None:
                outcomes.append(temporal_call(
                    n.cluster.temporal.get_from_snapshot_map_result, mapping,
                    aggregation_rules=rules))
            for result in outcomes:
                temporal_groups(n, result, assignment)
                # Membership is supplied independently of the product map.
                for label in dict.fromkeys(assignment):
                    sources = n.snapshots[np.array([x == label for x in assignment])]
                    np.testing.assert_allclose(result.n.snapshot_weightings.loc[label],
                                               n.snapshot_weightings.loc[sources].sum())
                    load = n.c.loads.dynamic.p_set.loc[sources, 'demand']
                    assert result.n.c.loads.dynamic.p_set.loc[label, 'demand'] == (
                        load.sum() if custom else load.mean())
                    upper = n.c.stores.dynamic.e_max_pu.loc[sources, 'reservoir']
                    upper = upper.max() if custom else upper.min()
                    lower = n.c.stores.dynamic.e_min_pu.loc[sources, 'reservoir'].max()
                    assert result.n.c.stores.dynamic.e_max_pu.loc[label, 'reservoir'] == upper
                    assert result.n.c.stores.dynamic.e_min_pu.loc[label, 'reservoir'] == min(lower, upper)
                    low = n.c.generators.dynamic.p_min_pu.loc[sources, 'plant']
                    high = n.c.generators.dynamic.p_max_pu.loc[sources, 'plant']
                    hi = high.min() if custom else high.mean()
                    lo = low.sum() if custom else low.mean()
                    assert np.isclose(result.n.c.generators.dynamic.p_min_pu.loc[label, 'plant'], min(lo, hi))
                    assert np.isclose(result.n.c.generators.dynamic.p_max_pu.loc[label, 'plant'], hi)

        daily = temporal_call(n.cluster.temporal.get_resample_result, '1D')
        day = pd.Timestamp('2025-01-03')
        daily_assignment = ([(p, day) for p in [2030, 2040] for _ in range(7)]
                            if periods else [day] * 7)
        temporal_groups(n, daily, daily_assignment)
        for label in dict.fromkeys(daily_assignment):
            sources = n.snapshots[np.array([x == label for x in daily_assignment])]
            np.testing.assert_allclose(daily.n.snapshot_weightings.loc[label],
                                       n.snapshot_weightings.loc[sources].sum())
            assert np.isclose(daily.n.c.loads.dynamic.p_set.loc[label, 'demand'],
                              n.c.loads.dynamic.p_set.loc[sources, 'demand'].mean())

    # 5h and 2D boundaries depend on the midnight anchor; the periods start on
    # different days and times, so each period must use its own first day.
    cases = [(temporal_network(periods=True, shifted=True), '5h'),
             (temporal_network(periods=True, shifted=True), '3h')]
    cases += [(long_network(periods=periods), interval)
              for periods in [False, True] for interval in ['5h', '1D', '2D']]
    for n, interval in cases:
        keys = interval_labels(n.snapshots, INTERVAL_HOURS[interval])
        for rules in [None, CUSTOM_RULES]:
            result = temporal_call(n.cluster.temporal.get_resample_result,
                                   interval, aggregation_rules=rules)
            for label, sources in temporal_partition(n, result, keys):
                check_group_values(n, result, label, sources, rules)
            np.testing.assert_allclose(result.n.snapshot_weightings.sum(),
                                       n.snapshot_weightings.sum())


def test_downsample_periods_and_short_tail():
    networks = [temporal_network(), temporal_network(periods=True),
                long_network(), long_network(periods=True)]
    for n in networks:
        # Each column is uniform within each period, but periods differ.
        uniform = [[2, 3, 5], [7, 11, 13]]
        for group, weights in zip(period_groups(n.snapshots), uniform):
            n.snapshot_weightings.loc[group] = weights
        for stride in [1, 3, 5, 10]:
            result = temporal_call(n.cluster.temporal.get_downsample_result, stride)
            keys = [(k, i // stride) for k, group in enumerate(period_groups(n.snapshots))
                    for i in range(len(group))]
            pairs = temporal_partition(n, result, keys)
            for label, sources in pairs:
                # The representative is the first snapshot of its group.
                assert label == sources[0]
                np.testing.assert_allclose(result.n.snapshot_weightings.loc[label],
                                           n.snapshot_weightings.loc[sources].sum())
                for table, attr, asset in SERIES:
                    assert (result.n.c[table].dynamic[attr].loc[label, asset]
                            == n.c[table].dynamic[attr].loc[label, asset])
                for table, low, high, asset in BOUNDS:
                    for attr in [low, high]:
                        assert np.isclose(result.n.c[table].dynamic[attr].loc[label, asset],
                                          n.c[table].dynamic[attr].loc[label, asset])
            np.testing.assert_allclose(result.n.snapshot_weightings.sum(),
                                       n.snapshot_weightings.sum())
        for stride in [0, -2]:
            rejected = invoke(n.cluster.temporal.get_downsample_result, stride,
                              expected_exceptions=(ValueError,))
            assert isinstance(rejected.exception, ValueError)


def test_snapshot_mapping_validation():
    n = temporal_network()
    mapping = pd.Series(['a', 'b', 'a', 'b', 'c', 'c', 'b'], index=n.snapshots)
    result = temporal_call(n.cluster.temporal.get_from_snapshot_map_result, mapping)
    temporal_groups(n, result, mapping.tolist())
    for label in ['a', 'b', 'c']:
        sources = mapping.index[mapping == label]
        assert result.n.c.loads.dynamic.p_set.loc[label, 'demand'] == n.c.loads.dynamic.p_set.loc[sources, 'demand'].mean()
        np.testing.assert_allclose(result.n.snapshot_weightings.loc[label],
                                   n.snapshot_weightings.loc[sources].sum())
    extra = pd.concat([mapping, pd.Series(['c'], index=[pd.Timestamp('2025-01-04')])])
    for bad in [mapping.iloc[:-1], extra, mapping.iloc[::-1]]:
        rejected = invoke(n.cluster.temporal.get_from_snapshot_map_result, bad,
                          expected_exceptions=(ValueError,))
        assert isinstance(rejected.exception, ValueError)


def test_segment_coverage_duration_and_attributes():
    n = temporal_network(unit=True)
    for excluded in [None, ['p_set'], []]:
        kwargs = {} if excluded is None else {'exclude_attrs': excluded}
        result = temporal_call(n.cluster.temporal.get_segment_result, 3, **kwargs)
        check_segment_result(n, result, excluded)


def test_temporal_unsupported_inputs():
    n = temporal_network(unit=True)
    assert len(temporal_call(n.cluster.temporal.get_segment_result, 2).n.snapshots) == 2
    for count in [0, -1, len(n.snapshots) + 1]:
        result = invoke(n.cluster.temporal.get_segment_result, count,
                        expected_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
    empty = Network()
    empty.set_snapshots(n.snapshots)
    result = invoke(empty.cluster.temporal.get_segment_result, 2,
                    expected_exceptions=(ValueError,))
    assert isinstance(result.exception, ValueError)
    multi = temporal_network(periods=True, unit=True)
    result = invoke(multi.cluster.temporal.get_segment_result, 2,
                    expected_exceptions=(NotImplementedError,))
    assert isinstance(result.exception, NotImplementedError)
    n.set_scenarios(['dry', 'wet'])
    for method, argument in [
        (n.cluster.temporal.get_resample_result, '3h'),
        (n.cluster.temporal.get_downsample_result, 2),
        (n.cluster.temporal.get_from_snapshot_map_result, pd.Series('a', index=n.snapshots)),
        (n.cluster.temporal.get_segment_result, 2)]:
        result = invoke(method, argument, expected_exceptions=(NotImplementedError,))
        assert isinstance(result.exception, NotImplementedError)


def test_segmentation_without_optional_support(tmp_path):
    isolated = isolated_site(tmp_path / 'site', excluded={'tsam'},
                             product_spec=importlib.util.find_spec('velmora'))
    observation = tmp_path / 'observation.json'
    script = """
import sys, json, importlib.util
from pathlib import Path
sys.path = [sys.argv[1], sys.argv[2]] + [p for p in sys.path if 'site-packages' not in p and 'dist-packages' not in p]
assert importlib.util.find_spec('tsam') is None
from F18_helpers import temporal_network, check_segment_result
n = temporal_network(unit=True)
try:
    result = n.cluster.temporal.get_segment_result(3)
except ModuleNotFoundError as error:
    outcome = {'outcome': 'missing-support', 'message': str(error)}
else:
    # An implementation with its own segmentation support must still deliver
    # the actual capability, through the same checks used with support present.
    check_segment_result(n, result)
    outcome = {'outcome': 'segmented'}
Path(sys.argv[3]).write_text(json.dumps(outcome))
"""
    result = run_command([sys.executable, '-S', '-c', script, str(isolated),
                          str(Path(__file__).parent), str(observation)], cwd=tmp_path,
                         env={'PYTHONPATH': None})
    assert result.returncode == 0, result.stderr
    observed = json.loads(observation.read_text())
    assert observed['outcome'] in {'missing-support', 'segmented'}
    if observed['outcome'] == 'missing-support':
        assert observed['message']
