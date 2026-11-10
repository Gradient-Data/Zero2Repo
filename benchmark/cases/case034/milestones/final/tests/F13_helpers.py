# feature: F13
"""Independent distribution measurements and estimation equations."""

import numpy as np
from numpy.testing import assert_allclose
from scipy.stats import kstest


def assert_gaussian_white(samples, covariance):
    """Whiten by the requested covariance, not the empirical covariance.

    With 100000 samples, the moment margins exceed eight standard errors.
    Projection KS tests use a Bonferroni-sized 1e-10 per-test tail budget.
    Lag products include squared samples to detect nonlinear dependence.
    These finite measurements do not claim to prove all-order independence.
    """
    z = np.linalg.solve(np.linalg.cholesky(covariance), samples)
    assert np.isfinite(z).all()
    assert_allclose(z.mean(axis=1), 0, atol=.03)
    assert_allclose(z @ z.T / z.shape[1], np.eye(len(z)), atol=.04)
    directions = np.array([[1., 0.], [0., 1.], [1., 1.], [1., -2.]])
    for direction in directions:
        projection = direction @ z / np.linalg.norm(direction)
        assert kstest(projection, 'norm').pvalue > 1e-10
    for lag in (1, 2, 7, 31):
        left, right = z[:, lag:], z[:, :-lag]
        assert_allclose(left @ right.T / left.shape[1], 0, atol=.04)
        assert_allclose((left**2 - 1) @ (right**2 - 1).T / left.shape[1],
                        0, atol=.08)


def estimation_law(a, b, c, g, q, r, state, inputs, *, discrete, correct):
    """Evaluate the documented continuous or one-step prediction equations."""
    n, m = len(a), len(c)
    x, p = state[:n], state[n:].reshape(n, n)
    mean = a @ x + b @ inputs[m:]
    covariance = (a @ p @ a.T if discrete else a @ p + p @ a.T) + g @ q @ g.T
    if correct:
        cross = (a @ p if discrete else p) @ c.T
        innovation = r + c @ p @ c.T if discrete else r
        gain = np.linalg.solve(innovation, cross.T).T
        mean = mean + gain @ (inputs[:m] - c @ x)
        covariance = covariance - gain @ cross.T
    return np.r_[mean, covariance.ravel()]
