# feature: F19
"""Finite-horizon optimal control through public entries."""
import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.optimize import NonlinearConstraint
import velunex as ct
from velunex.optimal import (OptimalControlProblem, input_range_constraint, quadratic_cost, state_range_constraint)
from velunex.flatsys import PolyFamily
from _helpers import invoke, isolated_mapping, user_warnings
from F18_helpers import linear_sample_cost, assert_convex_minimum
from F19_helpers import (solve_horizon, scalar_horizon_quadratic,
                         check_scalar_discrete)


def test_continuous_and_discrete_objectives_and_dynamics():
    times = np.array([0., .2, .55, 1.])
    # For both models z'=u. Cauchy-Schwarz gives a unique constant optimal
    # input for integral(u^2) + (z(T)-target)^2, including sampled trapezoids.
    for nonlinear in (False, True):
        model = (ct.nlsys(lambda t, x, u, p: [u[0]/(2*x[0])],
                          lambda t, x, u, p: x, states=1, inputs=1, outputs=1)
                 if nonlinear else ct.ss(0, 1, 1, 0))
        initial, target = 1., 2.4
        z = (lambda x: x[0]**2) if nonlinear else (lambda x: x[0])
        running = lambda x, u: u @ u
        terminal = lambda x, u: (z(x)-target)**2
        result = solve_horizon(model, times, [initial], running,
                               terminal_cost=terminal, trajectory_method='shooting', basis=PolyFamily(1),
                               solve_ivp_kwargs={'rtol': 1e-9, 'atol': 1e-11})
        assert result.success, result.message
        assert_allclose(result.time, times)
        x, u = result.states[0], result.inputs[0]
        optimal = (target-initial)/(1+times[-1])
        assert_allclose(u, optimal, atol=2e-3)
        expected_x = np.sqrt(initial+optimal*times) if nonlinear else initial+optimal*times
        assert_allclose(x, expected_x, atol=2e-3)
        assert_allclose(x[0], initial, atol=1e-8)
        assert_allclose(result.cost, linear_sample_cost(u*u, times,
                         terminal(result.states[:, -1], result.inputs[:, -1])), atol=2e-6)
        assert_allclose(result.cost, (target-initial)**2/(1+times[-1]), atol=2e-5)

    # Nonconstant running costs on an irregular grid distinguish trapezoidal
    # integration from left sampling, while a convex certificate checks quality.
    model = ct.ss(0, 1, 1, 0)
    running = quadratic_cost(model, 1., .3)
    terminal = quadratic_cost(model, 2., .3)
    result = solve_horizon(model, times, [1.], running, terminal_cost=terminal)
    assert result.success, result.message
    x, u = result.states[0], result.inputs[0]
    integral = np.zeros((len(times), len(times)))
    for k, dt in enumerate(np.diff(times)):
        integral[k+1] = integral[k]
        integral[k+1, k:k+2] += dt/2
    assert_allclose(x, 1+integral@u, atol=2e-6)
    weights = np.zeros(len(times))
    weights[:-1] += np.diff(times)/2
    weights[1:] += np.diff(times)/2
    state_weights = weights.copy()
    state_weights[-1] += 2
    input_weights = .3*weights
    input_weights[-1] += .3
    h = 2*(integral.T@(state_weights[:, None]*integral)+np.diag(input_weights))
    linear = 2*integral.T@state_weights
    assert_convex_minimum(u, h, linear, np.empty((0, 4)), np.empty((0, 4)), np.empty(0))
    assert_allclose(result.cost, linear_sample_cost(x*x+.3*u*u, times,
                    2*x[-1]**2+.3*u[-1]**2), atol=2e-6)

    model = ct.nlsys(lambda t, x, u, p: [x[0]**2+u[0]],
                     lambda t, x, u, p: x, states=1, inputs=1, outputs=1, dt=.4)
    running = lambda x, u: u @ u
    terminal = lambda x, u: (x[0]-1.3)**2 + u @ u
    result = solve_horizon(model, np.array([0., .4]), [.6], running, terminal_cost=terminal)
    assert result.success
    x, u = result.states[0], result.inputs[0]
    assert_allclose(result.time, [0., .4])
    assert_allclose(x[0], .6, atol=1e-8)
    assert_allclose(x[1], x[0]**2+u[0], atol=1e-7)
    assert_allclose(u, [(1.3-.6**2)/2, 0.], atol=2e-4)
    assert_allclose(result.cost, u[0]**2+(x[1]-1.3)**2+u[1]**2, atol=1e-7)


def test_tracking_costs_and_sampled_constraints():
    multi = ct.ss(np.eye(2), np.eye(2), np.eye(2), np.zeros((2, 2)), 1)
    x, u = np.array([1.2, -.7]), np.array([-.4, 1.1])
    q, r = np.array([[2., .3], [.3, 1.]]), np.array([[1., -.2], [-.2, 3.]])
    xr, ur = np.array([.2, .5]), np.array([.1, -.3])
    assert_allclose(quadratic_cost(multi, q, r, xr, ur)(x, u),
                    (x-xr) @ q @ (x-xr)+(u-ur) @ r @ (u-ur))
    assert_allclose(quadratic_cost(multi, 2., 3.)(x, u), 2*(x@x)+3*(u@u))
    assert_allclose(quadratic_cost(multi, None, r)(x, u), u@r@u)
    assert_allclose(quadratic_cost(multi, q, None)(x, u), x@q@x)
    for weights in ((np.eye(3), r), (q, np.eye(3))):
        with pytest.raises(ValueError):
            quadratic_cost(multi, *weights)

    model = ct.ss(0, 1, 2, 0, 1)
    times = np.arange(4.)
    # Each convenience separately restricts an otherwise infeasible optimum.
    for signal in ('state', 'input', 'output'):
        for kind in ('range', 'poly'):
            factory = getattr(ct.optimal, signal+'_'+kind+'_constraint')
            constraint = (factory(model, [-.25], [.4]) if kind == 'range'
                          else factory(model, [[1.], [-1.]], [.4, .25]))
            for target in (-1., 1.):
                running = quadratic_cost(model, None, 1., u0=np.array([target]))
                terminal = running
                free = solve_horizon(model, times, [0.], running, terminal_cost=terminal)
                result = solve_horizon(model, times, [0.], running, terminal_cost=terminal,
                                       trajectory_constraints=[constraint])
                xx, uu = check_scalar_discrete(result, times, 0., 0., running, terminal)
                observed = uu if signal == 'input' else xx*(2 if signal == 'output' else 1)
                baseline = free.inputs[0] if signal == 'input' else free.states[0]*(2 if signal == 'output' else 1)
                assert free.success
                assert np.any((baseline < -.25-1e-3) | (baseline > .4+1e-3))
                assert np.all(observed >= -.25-2e-5)
                assert np.all(observed <= .4+2e-5)
            bad_args = ([0., 0.], [1.]) if kind == 'range' else ([[1., 1.]], [1.])
            with pytest.raises(ValueError):
                factory(model, *bad_args)
            if kind == 'poly':
                with pytest.raises(ValueError):
                    factory(model, [[1.]], [1., 2.])

    nonlinear = (NonlinearConstraint, lambda x, u: [x[0]**2+u[0]**2], [.04], [.25])
    for target in (.8, 0.):
        running = quadratic_cost(model, None, 1., u0=np.array([target]))
        result = solve_horizon(model, times, [.2], running, terminal_cost=running,
                               trajectory_constraints=[nonlinear], initial_guess=np.full((1, 4), .3))
        xx, uu = check_scalar_discrete(result, times, .2, 0., running, running)
        values = xx*xx+uu*uu
        assert np.all(values >= .04-2e-5)
        assert np.all(values <= .25+2e-5)
        free = solve_horizon(model, times, [.2], running, terminal_cost=running)
        assert free.success
        baseline = free.states[0]**2+free.inputs[0]**2
        assert np.any((baseline < .04-1e-3) | (baseline > .25+1e-3))
    running = quadratic_cost(model, None, 1., u0=np.array([.8]))
    endpoint = solve_horizon(model, times, [0.], running, terminal_cost=running,
                             terminal_constraints=[state_range_constraint(model, [.1], [.15])])
    xx, uu = check_scalar_discrete(endpoint, times, 0., 0., running, running)
    assert .1-2e-5 <= xx[-1] <= .15+2e-5
    assert xx[1] > .15+1e-3  # Terminal bound must not become a path bound.


def test_input_basis_and_initial_guesses():
    model = ct.ss(.8, 1, 1, 0, 1)
    times = np.arange(5.)
    running = quadratic_cost(model, 1., .3)
    terminal = quadratic_cost(model, 2., .3)
    offset, response, h, linear = scalar_horizon_quadratic(.8, 1.2, len(times))
    constant = -linear.sum()/h.sum()
    free_optimum = np.linalg.solve(h, -linear)
    for guess in (np.full((1, 5), .7), np.full((1, 5), -.9)):
        limited = solve_horizon(model, times, [1.2], running, terminal_cost=terminal,
                                basis=PolyFamily(1), initial_guess=guess)
        xx, uu = check_scalar_discrete(limited, times, 1.2, .8, running, terminal)
        assert_allclose(uu, constant, atol=3e-4)
        free = solve_horizon(model, times, [1.2], running, terminal_cost=terminal,
                             initial_guess=guess)
        xx, uu = check_scalar_discrete(free, times, 1.2, .8, running, terminal)
        assert_allclose(uu, free_optimum, atol=3e-4)
        assert free.cost < limited.cost-1e-3
    with pytest.raises(ValueError):
        solve_horizon(model, times, [1.2], running, initial_guess=np.zeros((2, 5)))
    with pytest.raises(ValueError):
        solve_horizon(model, times, [1.2], running, initial_guess=np.zeros((1, 4)))


def test_constrained_discrete_quadratic_optimum():
    model = ct.ss(.8, 1, 1, 0, 1)
    times = np.arange(5.)
    running, terminal = quadratic_cost(model, 1., .3), quadratic_cost(model, 2., .3)
    for initial in (1.2, -.9):
        result = solve_horizon(model, times, [initial], running, terminal_cost=terminal,
                               trajectory_constraints=[input_range_constraint(model, [-.3], [.2]),
                                                       state_range_constraint(model, [-1.5], [1.5])])
        xx, uu = check_scalar_discrete(result, times, initial, .8, running, terminal)
        offset, response, h, linear = scalar_horizon_quadratic(.8, initial, len(times))
        assert_allclose(xx, offset+response@uu, atol=2e-6)
        rows = np.vstack([np.eye(5), -np.eye(5), response, -response])
        bounds = np.r_[np.full(5, .2), np.full(5, .3), 1.5-offset, 1.5+offset]
        assert_convex_minimum(uu, h, linear, np.empty((0, 5)), rows, bounds)


def test_failed_optimization_reports_reason_and_candidate():
    model = ct.ss(.8, 1, 1, 0, 1)
    times = np.arange(4.)
    running = quadratic_cost(model, 1., 1.)
    call = invoke(solve_horizon, (model, times, [1.], running))
    assert call.returned and not user_warnings(call, UserWarning)
    good = call.value
    assert good.success
    impossible = [input_range_constraint(model, [-1.], [0.]),
                  input_range_constraint(model, [1.], [2.])]
    capture = invoke(solve_horizon, (model, times, [1.], running),
                     {'trajectory_constraints': impossible})
    assert capture.returned
    assert user_warnings(capture, UserWarning)
    result = capture.value
    assert not result.success
    assert isinstance(result.message, str) and result.message.strip()
    assert_allclose(result.time, times)
    assert result.states.shape == result.inputs.shape == (1, len(times))
    assert np.all(np.isfinite(result.states)) and np.all(np.isfinite(result.inputs))
    assert_allclose(result.states[:, 0], [1.], atol=1e-7)
    assert_allclose(result.states[:, 1:], .8*result.states[:, :-1]+result.inputs[:, :-1], atol=2e-6)


def test_predictive_controller_updates_measurements_and_feedback():
    model = ct.ss(1, 1, 1, 0, 1, name='plant', inputs='u', outputs='x')
    cost = quadratic_cost(model, 1., 1.)
    problem = OptimalControlProblem(model, np.arange(3.), cost, terminal_cost=cost,
                                        minimize_method='SLSQP', minimize_options={'ftol': 1e-10, 'maxiter': 100})
    controller = problem.create_mpc_iosystem(name='controller', inputs='x', outputs='u')
    with isolated_mapping(ct.config.defaults, {'velunex.squeeze_time_response': False}):
        measurements = np.array([[1., -.7, .3, 1.4]])
        response = ct.input_output_response(controller, np.arange(4.), measurements, squeeze=False)
        # Completing squares for this two-step horizon gives u(0)=-3*x(0)/5.
        assert_allclose(response.outputs, -.6*measurements, atol=3e-4)
        closed = ct.interconnect([model, controller], connections=[['plant.u', 'controller.u'],
                                ['controller.x', 'plant.x']], inplist=[],
                                outlist=['plant.x', 'controller.u'])
        result = ct.input_output_response(closed, np.arange(5.),
                                          initial_state=np.r_[1., np.zeros(controller.nstates)], squeeze=False)
        assert_allclose(result.outputs[0], .4**np.arange(5.), atol=5e-4)
        assert_allclose(result.outputs[1], -.6*result.outputs[0], atol=3e-4)
    continuous = ct.ss(0, 1, 1, 0)
    problem = OptimalControlProblem(continuous, np.linspace(0, 1, 3),
                                        quadratic_cost(continuous, 1., 1.))
    with pytest.raises(ct.VelunexNotImplemented):
        problem.create_mpc_iosystem()
