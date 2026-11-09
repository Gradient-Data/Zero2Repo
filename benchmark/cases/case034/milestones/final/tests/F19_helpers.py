# feature: F19
"""Independent finite-horizon checks and public optimization calls."""
import numpy as np
from numpy.testing import assert_allclose
from velunex.optimal import (solve_optimal_trajectory)


def solve_horizon(model, times, initial, running, **kwargs):
    options = dict(squeeze=False, print_summary=False, minimize_method='SLSQP',
                   minimize_options={'ftol': 1e-10, 'maxiter': 400})
    options.update(kwargs)
    return solve_optimal_trajectory(model, times, initial, running, **options)


def scalar_horizon_quadratic(a, initial, count, q=1., r=.3, terminal=2.):
    """Condense the specified scalar recurrence, not the product's solver."""
    offset = initial * a ** np.arange(count)
    response = np.zeros((count, count))
    for k in range(1, count):
        for j in range(k):
            response[k, j] = a ** (k-j-1)
    weights = np.r_[np.full(count-1, q), terminal]
    hessian = 2 * (response.T @ (weights[:, None]*response) + r*np.eye(count))
    linear = 2 * response.T @ (weights * offset)
    return offset, response, hessian, linear


def check_scalar_discrete(result, times, initial, a, running, terminal):
    assert result.success, result.message
    assert_allclose(result.time, times)
    x, u = np.asarray(result.states), np.asarray(result.inputs)
    assert x.shape == u.shape == (1, len(times))
    assert_allclose(x[:, 0], [initial], atol=1e-7)
    assert_allclose(x[:, 1:], a*x[:, :-1]+u[:, :-1], atol=2e-6)
    cost = sum(running(x[:, k], u[:, k]) for k in range(len(times)-1))
    cost += terminal(x[:, -1], u[:, -1])
    assert_allclose(result.cost, cost, atol=2e-6, rtol=2e-6)
    return x[0], u[0]
