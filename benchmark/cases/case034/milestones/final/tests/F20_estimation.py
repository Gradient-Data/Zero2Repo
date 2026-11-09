# feature: F20
"""Acceptance tests for finite-history and moving-horizon estimation."""
import numpy as np
import pytest
import velunex as ct
from velunex.optimal import (OptimalEstimationProblem, disturbance_range_constraint, gaussian_likelihood_cost)
from scipy.optimize import LinearConstraint, NonlinearConstraint
from numpy.testing import assert_allclose
from _helpers import invoke, user_warnings
from F18_helpers import linear_sample_cost, sampled_cost, assert_convex_minimum
from F20_helpers import (estimate_history, estimation_quadratic,
                         equality_quadratic_solution)


def test_finite_histories_and_selected_channels():
    t = np.array([0., .2, .7, 1.3])
    u = np.array([[.2, .4, .9, 1.5]])
    y = np.array([[1.1, -.4, 2.2, 3.7]])
    # A disturbance equality makes the continuous dynamics exactly integrable;
    # no assertion pins a general-purpose collocation method.
    model = ct.ss(0, [[.8, 1.2]], 2, [[0, .3]])
    cost = lambda x, u, v, w: v@v + w@w
    result = estimate_history(model, t, y, u, cost,
        control_indices=[1], disturbance_indices=[0],
        trajectory_constraints=[NonlinearConstraint(lambda x,u,v,w: v, [0.], [0.])])
    assert result.success, result.message
    x, v, w = result.states, result.inputs, result.outputs
    assert x.shape == v.shape == w.shape == (1, len(t))
    assert_allclose(result.time, t)
    assert_allclose(v, 0, atol=2e-6)
    offset = 1.2*np.r_[0., np.cumsum((u[0, :-1]+u[0, 1:])/2*np.diff(t))]
    residual = y[0] - .3*u[0] - 2*offset
    initial = linear_sample_cost(residual, t)/(2*(t[-1]-t[0]))
    assert_allclose(x[0], initial+offset, atol=3e-4)
    assert_allclose(w, y-2*x-.3*u, atol=2e-6)
    assert_allclose(result.cost, linear_sample_cost((v*v+w*w)[0], t), atol=2e-6)

    # Reversed channels have distinct gains, so exchanging their roles fails.
    model = ct.ss(.7, [[.8, 1.2]], 2, [[0, 0]], 1)
    t = np.arange(4.)
    cost = lambda x,u,v,w: 2*(v@v) + .5*(w@w)
    result = estimate_history(model, t, y, u, cost,
                              control_indices=[1], disturbance_indices=[0])
    assert result.success, result.message
    x, v, w = result.states, result.inputs, result.outputs
    assert x.shape == v.shape == w.shape == (1, len(t))
    assert_allclose(result.time, t)
    assert_allclose(x[:, 1:], .7*x[:, :-1]+1.2*u[:, :-1]+.8*v[:, :-1], atol=2e-6)
    assert_allclose(w, y-2*x, atol=2e-6)
    h, f, e, rhs = estimation_quadratic(y, u)
    assert_allclose(np.r_[x[0], v[0]], equality_quadratic_solution(h,f,e,rhs), atol=3e-4)
    assert_allclose(result.cost, sampled_cost((2*v*v+.5*w*w)[0], np.ones(4)), atol=2e-6)


def test_likelihood_prior_and_constrained_optimum():
    multi = ct.ss(np.eye(2), np.eye(2), np.eye(2), np.zeros((2,2)), 1)
    rv, rw = np.array([[2., .4], [.4, 1.]]), np.array([[3., -.6], [-.6, 2.]])
    v, w = np.array([.7, -1.3]), np.array([1.1, .2])
    for q, r in ((rv, rw), (None, rw), (rv, None)):
        expected = (0 if q is None else v@np.linalg.solve(q,v)) + (0 if r is None else w@np.linalg.solve(r,w))
        assert_allclose(gaussian_likelihood_cost(multi,q,r)(np.zeros(2),np.zeros(2),v,w), expected)
    model = ct.ss(.7, [[1.2, .8]], 2, [[0, 0]], 1)
    t, y, u = np.arange(4.), np.array([[3., -2., 4., -1.]]), np.array([[.2,-.3,.1,.4]])
    cost = gaussian_likelihood_cost(model, .5, 2.)
    constraints = [disturbance_range_constraint(model, [-.15], [.2]),
                   LinearConstraint([[1.,0.,0.,0.]], [-.4], [.6])]
    for prior in (-.8, .9):
        result = estimate_history(model,t,y,u,cost, initial_state=[prior],
            terminal_cost=lambda x,x0: 3*((x-x0)@(x-x0)), trajectory_constraints=constraints)
        assert result.success, result.message
        x,v,w = result.states[0],result.inputs[0],result.outputs[0]
        z = np.r_[x,v]
        h,f,e,rhs = estimation_quadratic(y,u,prior,3.)
        assert_allclose(e@z,rhs,atol=2e-6)
        assert_allclose(w,y[0]-2*x,atol=2e-6)
        g = np.r_[np.eye(8), -np.eye(8)]
        bounds = np.r_[np.full(4,.6),np.full(4,.2),np.full(4,.4),np.full(4,.15)]
        assert_convex_minimum(z,h,f,e,g,bounds)
        assert_allclose(result.cost, np.sum(2*v*v+.5*w*w)+3*(x[0]-prior)**2,atol=2e-6)


def test_invalid_histories_and_unsuccessful_estimation():
    model = ct.ss(.7, [[1.2,.8]], 2, [[0,0]], 1)
    t,y,u = np.arange(4.), np.array([[1.,-2.,3.,.4]]), np.array([[.2,.4,-.1,.3]])
    cost = gaussian_likelihood_cost(model,.5,2.)
    call = invoke(estimate_history, (model,t,y,u,cost))
    assert call.returned and not user_warnings(call, UserWarning)
    assert call.value.success
    for measured,known,guess in (
        (np.zeros((2,4)),u,None), (y,np.zeros((2,4)),None),
        (np.zeros((1,3)),u,None), (y,np.zeros((1,3)),None),
        (y,u,(np.zeros((2,4)),np.zeros((1,4)))),
        (y,u,(np.zeros((1,4)),np.zeros((1,3))))):
        with pytest.raises(ValueError):
            estimate_history(model,t,measured,known,cost,initial_guess=guess)
    failed = invoke(estimate_history, (model,t,y,u,cost),
                    {'trajectory_constraints': [LinearConstraint(
                        [[1.,0.,0.,0.], [1.,0.,0.,0.]], [1.,2.], [1.,2.])]})
    assert failed.returned
    assert not failed.value.success
    assert isinstance(failed.value.message,str) and failed.value.message.strip()
    assert user_warnings(failed, UserWarning)
    # A candidate is optional on failure; its presence never implies success.


def test_moving_window_prior_and_prediction():
    model = ct.ss(.7, [[1.2,.8]], 2, [[0,0]], 1)
    cost = gaussian_likelihood_cost(model,.5,2.)
    prior_cost = lambda x,x0: 3*((x-x0)@(x-x0))
    problem = OptimalEstimationProblem(model,np.arange(3.),cost,
        terminal_cost=prior_cost,control_indices=[0],disturbance_indices=[1],
        minimize_method='SLSQP',minimize_options={'ftol':1e-10,'maxiter':300})
    estimator = problem.create_mhe_iosystem()
    y = np.array([1.2,-.5,2.3,.1,-1.7,.8,3.,-.9])
    u = np.array([.2,.6,-.1,.4,-.2,.5,.1,-.3])
    response = ct.input_output_response(estimator,np.arange(len(y)),np.vstack([y,u]),squeeze=False)
    # Start with an empty zero history, then independently minimize each window.
    yw,uw,xw = np.zeros(3),np.zeros(3),np.zeros(3)
    expected = [0.]
    for measurement,known in zip(y[:-1],u[:-1]):
        yw = np.r_[yw[1:],measurement]
        uw = np.r_[uw[1:],known]
        h,f,e,rhs = estimation_quadratic(yw,uw,xw[1],3.)
        z = equality_quadratic_solution(h,f,e,rhs)
        xw,vw = z[:3],z[3:]
        expected.append(.7*xw[-1]+1.2*uw[-1]+.8*vw[-1])
    assert_allclose(response.outputs,[expected],atol=5e-4)
    continuous = ct.ss(0,[[1.2,.8]],2,[[0,0]])
    problem = OptimalEstimationProblem(continuous,np.linspace(0,1,3),cost,
                                          control_indices=[0],disturbance_indices=[1])
    with pytest.raises(ct.VelunexNotImplemented):
        problem.create_mhe_iosystem()


def test_nonlinear_finite_history_estimation():
    model = ct.nlsys(lambda t, x, u, p: [x[0]**2+u[0]+u[1]],
                     lambda t, x, u, p: x, states=1, inputs=2, outputs=1, dt=1)
    times = np.arange(5.)
    known = np.array([[.1, -.08, .15, .04, -.03]])
    truth = np.empty((1, len(times)))
    truth[0, 0] = .3
    for k in range(len(times)-1):
        truth[0, k+1] = truth[0, k]**2+known[0, k]
    cost = lambda x, u, v, w: v@v+w@w
    call = invoke(estimate_history, (model, times, truth, known, cost),
                  {'initial_guess': (truth+.02, np.full_like(known, .01))})
    assert call.returned and not user_warnings(call, UserWarning)
    result = call.value
    assert result.success, result.message
    x, v, w = result.states, result.inputs, result.outputs
    assert x.shape == v.shape == w.shape == truth.shape
    assert_allclose(result.time, times)
    assert_allclose(x[:, 1:], x[:, :-1]**2+known[:, :-1]+v[:, :-1], atol=2e-6)
    assert_allclose(w, truth-x, atol=2e-6)
    assert_allclose(result.cost, np.sum(v*v+w*w), atol=2e-6)
    # The observed zero-disturbance trajectory is a zero-cost feasible minimum.
    # The nearby initial guess selects this local solution, without imposing a
    # global convergence guarantee for general nonlinear estimation problems.
    assert_allclose(x, truth, atol=3e-4)
    assert_allclose(v, 0, atol=3e-4)
    assert_allclose(result.cost, 0, atol=1e-7)
