# feature: F17
"""Public spatial-aggregation fixtures and geometric outcome checks."""

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from F03_helpers import electrical_pair


def spatial_pair():
    n = electrical_pair()
    n.set_snapshots(pd.Index([0, 1], name='snapshot'))
    n.c.buses.static.loc['west', ['x', 'y']] = [0., 0.]
    n.c.buses.static.loc['east', ['x', 'y']] = [2., 0.]
    n.c.lines.static.loc['circuit', 'length'] = 100.
    return n


def aggregate_row(table, **selectors):
    """Select a unique public row by semantic fields, never generated names."""
    mask = pd.Series(True, index=table.index)
    for key, value in selectors.items():
        mask &= table[key].eq(value)
    rows = table.loc[mask]
    assert len(rows) == 1, rows
    return rows.iloc[0]


def check_two_regions(coords, mapping):
    """Two Voronoi cells admit a nonconstant weak affine separator.

    Squared-distance comparison for two distinct representatives is affine.
    Fixing each normal component in turn to +/-1 covers every nonzero normal
    after rescaling; weak inequalities retain legitimate distance ties.
    """
    labels = mapping.unique()
    assert len(labels) == 2
    points = coords.loc[mapping.index].to_numpy(dtype=float)
    signs = np.where(mapping.to_numpy() == labels[0], 1., -1.)
    constraints = -signs[:, None] * np.column_stack([points, np.ones(len(points))])
    for axis in range(points.shape[1]):
        for direction in (-1., 1.):
            bounds = [(None, None)] * (points.shape[1] + 1)
            bounds[axis] = (direction, direction)
            result = linprog(np.zeros(points.shape[1] + 1), A_ub=constraints,
                             b_ub=np.zeros(len(points)), bounds=bounds, method='highs')
            if result.success:
                return
            assert result.status == 2, result.message
    raise AssertionError('Groups cannot be nearest-centre regions')


def check_nearest_centre_regions(coords, mapping):
    """Necessary condition for nearest-centre regions with any group count.

    For distinct representatives, the cells of any two groups are weakly
    separated by their bisector, a nonconstant affine function; each pair of
    groups is checked with the two-region separator above.
    """
    labels = list(mapping.unique())
    for i, first in enumerate(labels):
        for second in labels[i + 1:]:
            check_two_regions(coords, mapping[mapping.isin([first, second])])


def check_connected_groups(mapping, edges):
    for label in mapping.unique():
        members = set(mapping.index[mapping.eq(label)])
        reached = {next(iter(members))}
        for _ in range(len(members)):
            reached |= {v for u, v in edges if u in reached and v in members}
            reached |= {u for u, v in edges if v in reached and u in members}
        assert reached == members
