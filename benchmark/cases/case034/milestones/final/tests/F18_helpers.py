# feature: F18
"""Flat models and independent certificates for sampled quadratic problems."""

import numpy as np
from numpy.polynomial import Polynomial
from numpy.testing import assert_allclose
from scipy.linalg import null_space
from scipy.optimize import nnls
from velunex.flatsys import (FlatSystem)


def scaled_integrators(count=1, gain=1., constructor=FlatSystem):
    """Caller-defined flat model: each state derivative is gain times input."""
    def forward(x, u, params):
        return [np.array([x[i], params['gain'] * u[i]]) for i in range(count)]

    def reverse(flags, params):
        return (np.array([z[0] for z in flags]),
                np.array([z[1] / params['gain'] for z in flags]))

    def output(t, x, u, params):
        return np.asarray(x) ** 2 + 2 * np.asarray(u) + t

    return constructor(forward, reverse, outfcn=output, states=count,
                       inputs=count, outputs=count, params={'gain': gain})


def sampled_cost(values, weights, terminal=0.):
    """Sum explicitly selected sample values with caller-supplied weights."""
    return np.dot(np.asarray(values), np.asarray(weights)) + terminal


def held_sample_cost(values, times, terminal=0.):
    """Integrate left-held samples, excluding the final sample."""
    return sampled_cost(np.asarray(values)[:-1], np.diff(times), terminal)


def linear_sample_cost(values, times, terminal=0.):
    """Integrate piecewise linear sample values."""
    values = np.asarray(values)
    return sampled_cost((values[:-1] + values[1:]) / 2, np.diff(times), terminal)


def polynomial_rows(times, count, derivative=0):
    return np.array([Polynomial.basis(i).deriv(derivative)(times)
                     for i in range(count)]).T


def assert_convex_minimum(candidate, hessian, linear, equalities,
                          inequality_rows, upper, tolerance=2e-3):
    """Check a sufficient global certificate for a convex quadratic program.

    Objective is c.T H c / 2 + linear.T c; inequalities are G c <= upper.
    Equality feasibility is checked by callers against actual boundary data.
    Positive curvature on the equality null space also certifies a strict
    local minimum. No optimizer output or product-reported derivatives enter.
    """
    c, h = np.asarray(candidate), np.asarray(hessian)
    n = null_space(equalities)
    assert np.linalg.eigvalsh(n.T @ h @ n).min() > 1e-8
    g, bounds = np.asarray(inequality_rows), np.asarray(upper)
    slack = bounds - g @ c
    assert np.all(slack >= -tolerance)
    active = g[slack < tolerance]
    gradient = n.T @ (h @ c + linear)
    if len(active):
        multipliers, residual = nnls((active @ n).T, -gradient)
        assert residual <= tolerance * (1 + np.linalg.norm(gradient))
    else:
        assert np.linalg.norm(gradient) <= tolerance


def assert_integrator_trajectory(traj, times, gain=1.):
    """Check dynamics at new times by a symmetric numerical derivative."""
    times = np.asarray(times)
    x, u = traj.eval(times)
    plus, _ = traj.eval(times + 1e-5)
    minus, _ = traj.eval(times - 1e-5)
    assert_allclose((plus - minus) / 2e-5, gain * u, atol=2e-5, rtol=2e-5)
    return x, u


def assert_default_polynomials(traj, states, inputs):
    count = 2 * (states + inputs)
    assert len(traj.coeffs) == inputs
    for variable, coefficients in enumerate(traj.coeffs):
        assert len(coefficients) == count
        assert traj.basis.var_ncoefs(variable) == count
        for i in range(count):
            times = np.array([.17, .53, .91])
            assert_allclose(traj.basis.eval_deriv(i, 0, times, var=variable),
                            times ** i, atol=1e-12)
