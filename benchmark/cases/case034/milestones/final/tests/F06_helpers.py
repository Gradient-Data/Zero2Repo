# feature: F06
"""Equation checks independent of the product's solvers."""

import numpy as np
from numpy.testing import assert_allclose
from scipy.linalg import eigvals
from F01_helpers import assert_unordered_roots


def assert_matrix_balance(*terms):
    """Allow roundoff relative to the equation's scale, not a solver's output."""
    scale = max(1., sum(np.linalg.norm(t, ord='fro') for t in terms))
    assert np.linalg.norm(sum(terms), ord='fro') <= 1e-8 * scale


def assert_riccati_result(result, a, b, q, r, s, e, *, discrete,
                          stabilizing=True):
    """Check equations, feedback and spectrum without selecting a method."""
    x, poles, gain = result
    assert x.shape == a.shape
    assert gain.shape == (b.shape[1], a.shape[0])
    assert np.isfinite(x).all() and np.isfinite(gain).all()
    assert_allclose(x, x.T, rtol=1e-8, atol=1e-8)
    if discrete:
        weight = r + b.T @ x @ b
        assert_matrix_balance(weight @ gain, -b.T @ x @ a, -s.T)
        assert_matrix_balance(a.T @ x @ a, -e.T @ x @ e, q,
                              -gain.T @ weight @ gain)
    else:
        assert_matrix_balance(r @ gain, -b.T @ x @ e, -s.T)
        assert_matrix_balance(a.T @ x @ e, e.T @ x @ a, q,
                              -gain.T @ r @ gain)
    expected = eigvals(a - b @ gain, e)
    assert_unordered_roots(poles, expected)
    if discrete:
        assert np.all(abs(expected) < 1) if stabilizing else np.all(abs(expected) > 1)
    else:
        assert np.all(expected.real < 0) if stabilizing else np.all(expected.real > 0)
