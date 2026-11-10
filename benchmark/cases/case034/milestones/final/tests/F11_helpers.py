# feature: F11
"""Geometric observations and caller-supplied dynamics for phase analysis."""
import numpy as np
from numpy.testing import assert_allclose
from scipy.optimize import linear_sum_assignment


def assert_point_set(actual, expected, atol=1e-7):
    actual, expected = np.asarray(actual), np.asarray(expected)
    assert actual.shape == expected.shape
    rows, cols = linear_sum_assignment(
        np.linalg.norm(actual[:, None, :] - expected[None, :, :], axis=2))
    assert_allclose(actual[rows], expected[cols], atol=atol, rtol=0)


def phase_coordinates(line):
    return np.column_stack((line.get_xdata(), line.get_ydata()))


def covers_flow(paths, seed, velocity, duration, direction, atol=1e-7):
    """Whether drawn segments cover the requested interval on one flow line."""
    velocity = np.asarray(velocity)
    lower = -duration if direction != 'forward' else 0.
    upper = duration if direction != 'reverse' else 0.
    pieces = []
    for path in paths:
        offsets = np.asarray(path)-seed
        times = offsets @ velocity / (velocity @ velocity)
        on_line = np.linalg.norm(offsets-times[:, None]*velocity, axis=1) <= atol
        for i in range(len(path)-1):
            if on_line[i] and on_line[i+1]:
                left, right = sorted(times[i:i+2])
                if right >= lower and left <= upper:
                    pieces.append((max(left, lower), min(right, upper)))
    covered = lower
    for left, right in sorted(pieces):
        if left > covered+atol:
            return False
        covered = max(covered, right)
    return covered >= upper-atol


def assert_flow_paths(paths, seeds, velocity, duration, direction, atol=1e-7):
    """Measure complete flow segments independently of artist partitioning.

    Every finite segment must belong to a requested trajectory. Their union
    must cover each requested time interval without gaps. Vertex order, artist
    order, splitting, joining at a seed, and nonfinite separators are free.
    """
    seeds, velocity = np.asarray(seeds), np.asarray(velocity)
    speed_squared = velocity @ velocity
    lower = -duration if direction != 'forward' else 0.
    upper = duration if direction != 'reverse' else 0.
    intervals = [[] for _ in seeds]
    for path in paths:
        path = np.asarray(path)
        assert path.ndim == 2 and path.shape[1] == 2
        finite = np.all(np.isfinite(path), axis=1)
        offsets = path[:, None, :] - seeds[None, :, :]
        times = offsets @ velocity / speed_squared
        residuals = offsets - times[:, :, None]*velocity
        on_path = ((np.linalg.norm(residuals, axis=2) <= atol)
                   & (times >= lower-atol) & (times <= upper+atol))
        assert np.all(np.any(on_path[finite], axis=1))
        for i in range(len(path)-1):
            if not (finite[i] and finite[i+1]):
                continue
            matches = np.flatnonzero(on_path[i] & on_path[i+1])
            assert len(matches), 'A drawn segment leaves the requested flows'
            for index in matches:
                intervals[index].append(tuple(sorted(times[i:i+2, index])))
    for pieces in intervals:
        assert pieces, 'A requested trajectory is missing'
        covered = lower
        for left, right in sorted(pieces):
            assert left <= covered+atol, 'A requested trajectory has a gap'
            covered = max(covered, right)
        assert covered >= upper-atol, 'A requested trajectory is incomplete'


def shifted_saddle(t, x, u, p):
    # Eigenvectors (1, 1) and (1, -1), with opposite stability.
    z = np.asarray(x) - p['center']
    return [z[1], z[0]]
