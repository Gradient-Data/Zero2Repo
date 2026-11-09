# feature: F20
"""Public estimation calls and independent scalar quadratic specifications."""
import numpy as np
from velunex.optimal import (solve_optimal_estimate)


def estimate_history(model, times, measured, known, cost, **kwargs):
    options = dict(control_indices=[0], disturbance_indices=[1],
                   squeeze=False, print_summary=False, minimize_method='SLSQP',
                   minimize_options={'ftol': 1e-10, 'maxiter': 300})
    options.update(kwargs)
    return solve_optimal_estimate(model, times, measured, known, cost, **options)


def estimation_quadratic(measured, known, prior=None, weight=0.,
                         a=.7, b=1.2, g=.8, c=2., rv=.5, rw=2.):
    """Specify the caller's quadratic objective and linear dynamics in [x,v]."""
    y, u = np.asarray(measured).ravel(), np.asarray(known).ravel()
    n = len(y)
    h = np.diag(np.r_[np.full(n, 2*c*c/rw), np.full(n, 2/rv)])
    f = np.r_[-2*c*y/rw, np.zeros(n)]
    if prior is not None:
        h[0, 0] += 2*weight
        f[0] -= 2*weight*prior
    e = np.zeros((n-1, 2*n))
    for k in range(n-1):
        e[k, k], e[k, k+1], e[k, n+k] = -a, 1., -g
    return h, f, e, b*u[:-1]


def equality_quadratic_solution(h, f, e, rhs):
    """Solve the independent strictly convex equality problem by linear algebra."""
    block = np.block([[h, e.T], [e, np.zeros((len(e), len(e)))]])
    return np.linalg.solve(block, np.r_[-f, rhs])[:len(f)]
