# feature: F01
"""Independent mathematical references for linear models."""

import numpy as np
from numpy.testing import assert_allclose
from scipy.optimize import linear_sum_assignment


def state_space_reference(a, b, c, d, points):
    """Evaluate the defining zero-initial-state linear equations."""
    a, b, c, d = (np.asarray(v) for v in (a, b, c, d))
    return np.stack([c @ np.linalg.solve(p * np.eye(len(a)) - a, b) + d
                     for p in points], axis=-1)


def polynomial_reference(numerator, denominator, points):
    """Evaluate a single channel's supplied descending-power polynomials."""
    return np.polyval(numerator, points) / np.polyval(denominator, points)


def zpk_reference(zeros, poles, gain, points):
    """Evaluate the defining root-product relation, without a product import."""
    points = np.asarray(points, dtype=complex)
    return gain * np.prod(points[:, None] - np.asarray(zeros), axis=1) / np.prod(
        points[:, None] - np.asarray(poles), axis=1)


def assert_unordered_roots(actual, expected, *, rtol=1e-7, atol=1e-9):
    """Match roots bijectively; repeated roots retain their multiplicity."""
    actual, expected = np.asarray(actual), np.asarray(expected)
    assert actual.shape == expected.shape
    rows, cols = linear_sum_assignment(abs(actual[:, None] - expected[None, :]))
    assert_allclose(actual[rows], expected[cols], rtol=rtol, atol=atol)
