# feature: F18
"""Acceptance of flat mappings, endpoint planning, and optimal trajectories."""

import numpy as np
import pytest
import velunex as ct
from velunex.flatsys import (BSplineFamily, FlatSystem, LinearFlatSystem, PolyFamily, flatsys, point_to_point, solve_flat_optimal)
from numpy.testing import assert_allclose
from scipy.optimize import LinearConstraint, NonlinearConstraint
from _helpers import invoke, user_warnings
from F18_helpers import (scaled_integrators, held_sample_cost,
                         polynomial_rows, assert_convex_minimum,
                         assert_integrator_trajectory, assert_default_polynomials)


def test_flat_mappings_and_linear_conversion():
    for constructor in (FlatSystem, flatsys):
        model = scaled_integrators(2, gain=2., constructor=constructor)
        assert_allclose(model.forward([1., -3.], [.4, -.7], {'gain': 3.}),
                        [[1., 1.2], [-3., -2.1]])
        x, u = model.reverse([[2., 1.5], [-1., 3.]], {'gain': 3.})
        assert_allclose(x, [2., -1.])
        assert_allclose(u, [.5, 1.])
        for params, gain in [(None, 2.), ({'gain': 3.}, 3.)]:
            traj = point_to_point(model, [0., 1.], [0., 1.], [.1, -.2],
                                     [1., -1.], [.3, .4], params=params)
            x, u = assert_integrator_trajectory(traj, [.13, .47, .83], gain)
            xe, ue = traj.eval([0., 1.])
            assert_allclose(xe, [[0., 1.], [1., -1.]], atol=1e-7)
            assert_allclose(ue, [[.1, .3], [-.2, .4]], atol=1e-7)

    a = np.array([[0., 1.], [-2., -3.]])
    b = np.array([[0.], [2.]])
    for constructor in (LinearFlatSystem, flatsys):
        flat = constructor(ct.ss(a, b, [[1., .4]], 0))
        state, control = np.array([.7, -.3]), np.array([.6])
        flag = flat.forward(state, control, None)
        xr, ur = flat.reverse(flag, None)
        assert_allclose(xr, state, atol=1e-9)
        assert_allclose(ur, control, atol=1e-9)
        # Verify derivatives without choosing a normalization of flat coordinates.
        dx = a @ state + b @ control
        zp = flat.forward(state + 1e-5 * dx, control, None)[0]
        zm = flat.forward(state - 1e-5 * dx, control, None)[0]
        assert_allclose((zp[:-1] - zm[:-1]) / 2e-5, flag[0][1:], atol=1e-8)
        times = np.array([.11, .42, .79])
        for t in times:
            xx, uu = flat.reverse([[t**3 + t, 3*t*t + 1, 6*t]], None)
            xp, _ = flat.reverse([[(t+1e-5)**3+t+1e-5,
                                  3*(t+1e-5)**2+1, 6*(t+1e-5)]], None)
            xm, _ = flat.reverse([[(t-1e-5)**3+t-1e-5,
                                  3*(t-1e-5)**2+1, 6*(t-1e-5)]], None)
            assert_allclose((xp-xm)/2e-5, a @ xx + b @ uu, atol=1e-7)
        with pytest.raises(ct.VelunexNotImplemented):
            constructor(ct.ss(a, np.eye(2), np.eye(2), np.zeros((2, 2))))
        with pytest.raises(ValueError):
            constructor(ct.ss(np.diag([-1., -2.]), [[1.], [0.]], [[1., 1.]], 0))


def test_endpoint_planning_and_basis_requirements():
    model = scaled_integrators(2, gain=1.7)
    for basis in (None, BSplineFamily([.2, 1.4], 3, vars=2)):
        options = {} if basis is None else {'basis': basis}
        traj = point_to_point(model, [.2, 1.4], [1., -2.], [.4, -.2],
                                 [-.5, 1.], [-.3, .5], **options)
        x, u = traj.eval([.2, 1.4])
        assert_allclose(x, [[1., -.5], [-2., 1.]], atol=1e-7)
        assert_allclose(u, [[.4, -.3], [-.2, .5]], atol=1e-7)
        assert_integrator_trajectory(traj, [.31, .69, 1.19], gain=1.7)
        if basis is None:
            assert_default_polynomials(traj, 2, 2)
    for basis in (PolyFamily(3), BSplineFamily([0., 1.], 7, vars=1)):
        with pytest.raises(ValueError):
            point_to_point(model, [0., 1.], [0., 0.], [0., 0.],
                              [1., 2.], [0., 0.], basis=basis)


def test_point_to_point_optimization_and_minimal_basis():
    model = scaled_integrators()
    times = np.linspace(0., 1., 5)
    cost = lambda x, u: x @ x + .2 * (u @ u)
    # Endpoints are prescribed separately from interior path constraints.
    for constraint in ((LinearConstraint, [[1., 0.]], [-2.], [.4]),
                       (NonlinearConstraint, lambda x, u: x, [-2.], [.4])):
        call = invoke(point_to_point, (model, times, [0.], [0.], [1.], [0.]),
                      dict(basis=PolyFamily(5), integral_cost=cost,
                           trajectory_constraints=[constraint],
                           minimize_options={'ftol': 1e-11, 'maxiter': 300}))
        assert call.returned and not user_warnings(call, UserWarning)
        traj = call.value
        assert traj.success
        x, u = assert_integrator_trajectory(traj, times)
        assert_allclose(x[:, [0, -1]], [[0., 1.]], atol=1e-7)
        assert_allclose(u[:, [0, -1]], [[0., 0.]], atol=1e-7)
        assert np.all(x[:, 1:-1] <= .4 + 1e-6)
        assert np.all(x[:, 1:-1] >= -2. - 1e-6)
        # Uniform sampling and zero initial cost give the left-held integral.
        weights = np.diff(times)[1:]
        measured = held_sample_cost((x*x + .2*u*u)[0], times)
        assert_allclose(traj.cost, measured, atol=1e-7, rtol=1e-7)
        rows = polynomial_rows(times[1:-1], 5)
        derivs = polynomial_rows(times[1:-1], 5, 1)
        h = 2 * (rows.T @ (weights[:, None]*rows)
                 + .2 * derivs.T @ (weights[:, None]*derivs))
        eq = np.vstack([polynomial_rows([0., 1.], 5),
                        polynomial_rows([0., 1.], 5, 1)])
        probe = np.linspace(0, 1, 5)
        candidate = np.linalg.solve(polynomial_rows(probe, 5), traj.eval(probe)[0][0])
        assert_convex_minimum(candidate, h, np.zeros(5), eq,
                              np.vstack([rows, -rows]), np.r_[np.full(3, .4), np.full(3, 2.)])

    result = invoke(point_to_point, (model, times, [0.], [0.], [1.], [0.]),
                    {'basis': PolyFamily(4), 'integral_cost': cost,
                     'trajectory_constraints': [(LinearConstraint, [[1., 0.]], [-2.], [.1])]})
    assert result.returned
    assert user_warnings(result, UserWarning)
    x, u = result.value.eval(times)
    assert_allclose(x[:, [0, -1]], [[0., 1.]], atol=1e-7)
    assert_allclose(u[:, [0, -1]], [[0., 0.]], atol=1e-7)
    # Unique cubic endpoint solution violates the requested path bound.
    assert_allclose(x[0], 3*times**2 - 2*times**3, atol=1e-7)
    assert_integrator_trajectory(result.value, [.13, .46, .72])


def test_initial_only_optimal_planning_and_response():
    model = scaled_integrators()
    times = np.array([0., .15, .4, .7, 1.])
    running = lambda x, u: x @ x + .2*(u @ u)
    terminal = lambda x, u: 3*(x[0]-2)**2
    traj = solve_flat_optimal(model, times, [.2], [.1],
                                 integral_cost=running, terminal_cost=terminal,
                                 basis=PolyFamily(4),
                                 trajectory_constraints=[(LinearConstraint, [[0., 1.]], [-2.], [.8])],
                                 minimize_options={'ftol': 1e-11, 'maxiter': 300})
    assert traj.success
    x, u = assert_integrator_trajectory(traj, times)
    assert_allclose(x[:, 0], [.2], atol=1e-7)
    assert_allclose(u[:, 0], [.1], atol=1e-7)
    assert np.all(u <= .8 + 1e-6)
    assert np.all(u >= -2. - 1e-6)
    assert_allclose(traj.cost, held_sample_cost((x*x+.2*u*u)[0], times,
                                               terminal(x[:, -1], u[:, -1])), atol=1e-7)
    rows, derivs = polynomial_rows(times, 4), polynomial_rows(times, 4, 1)
    weights = np.diff(times)
    h = 2*(rows[:-1].T @ (weights[:, None]*rows[:-1])
           + .2*derivs[:-1].T @ (weights[:, None]*derivs[:-1])
           + 3*np.outer(rows[-1], rows[-1]))
    probe = np.linspace(0, 1, 4)
    candidate = np.linalg.solve(polynomial_rows(probe, 4), traj.eval(probe)[0][0])
    assert_convex_minimum(candidate, h, -12*rows[-1],
                          np.vstack([rows[0], derivs[0]]),
                          np.vstack([derivs, -derivs]), np.r_[np.full(5, .8), np.full(5, 2.)])
    response = traj.response(times, squeeze=False)
    assert_allclose(response.time, times)
    assert_allclose(response.states, x, atol=1e-8)
    assert_allclose(response.inputs, u, atol=1e-8)
    assert_allclose(response.outputs, x*x+2*u+times, atol=1e-8)

    multi = scaled_integrators(2)
    target = np.array([1., -.7])
    terminal_multi = lambda x, u: np.sum((x-target)**2) + u @ u
    default = solve_flat_optimal(multi, times, [0., 0.], [0., 0.],
                                    terminal_cost=terminal_multi,
                                    minimize_method='SLSQP',
                                    minimize_options={'ftol': 1e-11, 'maxiter': 300})
    assert default.success
    assert_default_polynomials(default, 2, 2)
    xx, uu = assert_integrator_trajectory(default, times)
    assert_allclose(xx[:, 0], [0., 0.], atol=1e-7)
    assert_allclose(uu[:, 0], [0., 0.], atol=1e-7)
    assert_allclose(xx[:, -1], target, atol=1e-4)
    assert_allclose(uu[:, -1], [0., 0.], atol=1e-4)
    # Nonnegative objective attaining zero certifies a global minimum.
    assert_allclose(default.cost, terminal_multi(xx[:, -1], uu[:, -1]), atol=1e-9)
    assert_allclose(default.cost, 0., atol=1e-7)
    with pytest.raises(TypeError):
        solve_flat_optimal(model, times, [.2], [.1])
    with pytest.raises(ValueError):
        solve_flat_optimal(model, times, [.2], [.1], integral_cost=running,
                              basis=PolyFamily(2))
    with pytest.raises(ValueError):
        solve_flat_optimal(multi, times, [0., 0.], [0., 0.], integral_cost=running,
                              basis=BSplineFamily([0., 1.], 7, vars=1))


def test_unsuccessful_optimization_is_reported():
    model = scaled_integrators()
    times = np.linspace(0., 1., 5)
    cost = lambda x, u: x @ x + u @ u
    # Incompatible bounds on the same scalar, represented as separate valid constraints.
    impossible = [(LinearConstraint, [[1., 0.]], [2.], [3.]),
                  (LinearConstraint, [[1., 0.]], [-3.], [-2.])]
    for entry, args in ((point_to_point, (model, times, [0.], [0.], [1.], [0.])),
                        (solve_flat_optimal, (model, times, [0.], [0.]))):
        options = {'basis': PolyFamily(5), 'integral_cost': cost,
                   'minimize_options': {'maxiter': 100}}
        call = invoke(entry, args, options)
        assert call.returned and not user_warnings(call, UserWarning)
        good = call.value
        assert good.success
        assert np.isfinite(good.cost)
        result = invoke(entry, args, dict(options, trajectory_constraints=impossible))
        assert result.returned
        assert user_warnings(result, UserWarning)
        assert not result.value.success
        x, u = result.value.eval(times)
        assert x.shape == (1, len(times))
        assert u.shape == (1, len(times))
        assert np.all(np.isfinite(x))
        assert np.all(np.isfinite(u))
        assert_allclose(x[:, 0], [0.], atol=1e-6)
        assert_allclose(u[:, 0], [0.], atol=1e-6)


def test_initial_only_nonlinear_path_constraint():
    model = scaled_integrators()
    times = np.linspace(0., 1., 5)
    target, input_square_bound = 1., .49
    terminal = lambda x, u: (x[0]-target)**2
    solutions = []
    for constrained in (False, True):
        constraints = [(NonlinearConstraint, lambda x, u: u*u,
                        [0.], [input_square_bound])] if constrained else []
        call = invoke(solve_flat_optimal, (model, times, [0.], [0.]),
                      dict(terminal_cost=terminal, basis=PolyFamily(3),
                           minimize_method='SLSQP',
                           trajectory_constraints=constraints,
                           minimize_options={'ftol': 1e-11, 'maxiter': 300}))
        assert call.returned, constrained
        traj = call.value
        # The documents fix no default starting point, and whether SLSQP reports
        # convergence at this optimum depends on it. They do fix the pairing: a
        # successful optimization completes without a warning, an unsuccessful one
        # warns. The trajectory itself must be the optimum either way (below).
        warned = bool(user_warnings(call, UserWarning))
        assert traj.success != warned, (
            constrained, traj.success, [str(w.message) for w in call.warnings])
        x, u = assert_integrator_trajectory(traj, times)
        assert_allclose(x[:, 0], 0, atol=1e-7)
        assert_allclose(u[:, 0], 0, atol=1e-7)
        assert_allclose(traj.cost, terminal(x[:, -1], u[:, -1]), atol=1e-7)
        # Initial conditions leave x(t)=a*t**2. The feasible interval in a
        # and its unique objective minimizer follow from the supplied bound.
        coefficient = target/times[-1]**2
        if constrained:
            assert np.all(u*u <= input_square_bound+1e-6)
            coefficient = min(coefficient, np.sqrt(input_square_bound)/(2*times[-1]))
        assert_allclose(x[0], coefficient*times**2, atol=2e-4)
        assert_allclose(u[0], 2*coefficient*times, atol=2e-4)
        solutions.append((x, u))
    assert np.max(solutions[0][1]**2) > input_square_bound
