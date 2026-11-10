# feature: F16
"""Acceptance tests for reduction and identification through public entries."""
import numpy as np
import pytest
import velunex as ct
from numpy.testing import assert_allclose
from scipy.linalg import solve_continuous_lyapunov
from _helpers import invoke, user_warnings
from F01_helpers import state_space_reference, polynomial_reference, assert_unordered_roots
from F16_helpers import impulse_samples, causal_design


def test_minimal_realization():
    points = np.array([0, .3j, 2j, 1+3j])
    a = np.diag([-1., -3., -5.])
    b = np.array([[2.], [0.], [4.]])
    c = np.array([[3., 7., 0.]])
    d = np.array([[.4]])
    reduced = ct.minimal_realization(ct.ss(a, b, c, d), verbose=False)
    assert reduced.nstates == 1
    assert_allclose(reduced(points, squeeze=False), state_space_reference(a,b,c,d,points), atol=1e-8)
    # The caller's tolerance decides cancellation in both directions.
    for separation, tol, order in [(0., 1e-3, 1), (1e-5, 1e-3, 1), (.02, 1e-3, 2),
                                   (.02, .05, 1), (1e-4, 1e-6, 2)]:
        numerator = np.poly([-2-separation]) * 3
        denominator = np.poly([-2., -4.])
        reduced = ct.minimal_realization(ct.tf(numerator, denominator), tol=tol, verbose=False)
        assert len(reduced.den[0][0])-1 == order
        expected = polynomial_reference([3], [1,4], points) if order == 1 else polynomial_reference(numerator,denominator,points)
        assert_allclose(reduced(points), expected, atol=1e-8)


def test_selected_reduction():
    a = np.array([[-2., 1.], [2., -5.]])
    b = np.array([[1., 3.], [2., -1.]])
    c = np.array([[2., 4.], [-1., 3.]])
    d = np.array([[.2, .3], [.4, .5]])
    model = ct.ss(a,b,c,d)
    points = np.array([0, .7j, 3j])
    for selection in [dict(elim_states=[1], elim_inputs=[0], elim_outputs=[1]),
                      dict(keep_states=[0], keep_inputs=[1], keep_outputs=[0])]:
        reduced = ct.model_reduction(model, method='truncate', **selection)
        assert (reduced.nstates, reduced.ninputs, reduced.noutputs) == (1,1,1)
        expected = state_space_reference(a[:1,:1], b[:1,1:], c[:1,:1], d[:1,1:], points)
        assert_allclose(reduced(points,squeeze=False), expected, atol=1e-9)
        matched = ct.model_reduction(model, **selection)
        # Eliminated equilibrium yields x1'=-1.6*x1+2.8*u, y=3.6*x1-.5*u.
        expected = state_space_reference([[-1.6]], [[2.8]], [[3.6]], [[-.5]], points)
        assert_allclose(matched(points,squeeze=False),expected,atol=1e-9)
        assert_allclose(matched(0), state_space_reference(a,b,c,d,[0])[0,1,0])
    for category in ['states','inputs','outputs']:
        with pytest.raises(ValueError):
            ct.model_reduction(model, **{'keep_'+category:[0], 'elim_'+category:[1]})
    with pytest.raises(ValueError):
        ct.model_reduction(ct.ss([[-1,1],[-1,0]],b,c,d), [1])
    with pytest.raises(NotImplementedError):
        ct.model_reduction(ct.ss(a/10,b,c,d,dt=.2), [1])


def test_balanced_reduction():
    a = np.diag([-1., -3., -8.])
    b = np.array([[1.,.2],[.3,1.],[.1,.4]])
    c = np.array([[2.,.3,.1],[.2,1.,.5]])
    d = np.array([[.1,0],[0,.2]])
    model = ct.ss(a,b,c,d)
    wc = solve_continuous_lyapunov(a, -b@b.T)
    wo = solve_continuous_lyapunov(a.T, -c.T@c)
    expected = np.sort(np.sqrt(np.linalg.eigvals(wc@wo).real))[::-1]
    assert_allclose(ct.hankel_singular_values(model),expected,rtol=1e-7,atol=1e-10)
    points = 1j*np.r_[0,np.logspace(-3,3,181)]
    full = state_space_reference(a,b,c,d,points)
    for order, reduced in zip([1,2],ct.balanced_reduction(model,[1,2])):
        assert reduced.nstates == order
        # Truncation removes state contributions only: feedthrough is kept,
        # unlike a gain-preserving reduction, which also meets the bound.
        assert_allclose(reduced.D, d, atol=1e-10)
        error = full - reduced(points,squeeze=False)
        largest = max(np.linalg.svd(error[:,:,k],compute_uv=False)[0] for k in range(len(points)))
        assert largest <= 2*sum(expected[order:]) + 1e-8
    matched = ct.balanced_reduction(model,1,method='matchdc')
    assert matched.nstates == 1
    assert_allclose(matched(0,squeeze=False),full[:,:,0],atol=1e-8)
    unstable = ct.ss(np.diag([.5, 1.2, -3., -7.]), np.ones((4,1)), [[1,2,3,4]], [[0]])
    reduced = ct.balanced_reduction(unstable,3)
    assert reduced.nstates == 3
    poles = np.linalg.eigvals(reduced.A)
    assert_unordered_roots(poles[poles.real>0], np.array([.5,1.2]))
    # Too-small-order rejection is absent in the baseline; see the ledger.


def test_impulse_realization():
    a = np.array([[.4,.2],[0.,-.3]])
    b = np.array([[1.,2.],[3.,-.5]])
    c = np.array([[2.,1.],[-1.,3.]])
    for period, feedthrough, explicit in [(1.,np.array([[.2,.4],[-.3,.1]]),False),
                                          (.25,np.zeros((2,2)),True)]:
        data = impulse_samples(a,b,c,feedthrough,13,period)
        model, singular = ct.eigensys_realization(data[:,:,:9],2,**({'dt':period} if explicit else {}))
        assert model.nstates == 2
        assert model.dt == (period if explicit else True)
        actual = impulse_samples(model.A,model.B,model.C,model.D,13,period)
        assert_allclose(actual,data,rtol=1e-7,atol=1e-8)
        hankel = np.block([[data[:,:,i+j+1] for j in range(4)] for i in range(4)])
        assert_allclose(singular,np.linalg.svd(hankel,compute_uv=False),rtol=1e-7,atol=1e-9)
        with pytest.raises(ValueError):
            ct.eigensys_realization(data[:,:,:8],2)


def test_markov_identification():
    rng = np.random.default_rng(614)
    inputs = rng.normal(size=(2,30))
    coefficients = np.array([[[.4,1.,-.3],[-.2,.7,.5]],[[.1,-.8,.2],[.5,.3,-.4]]])
    design = causal_design(inputs,3)
    outputs = (design @ coefficients.transpose(0,2,1).reshape(2,6).T).T
    for period in [1.,.2]:
        estimated = ct.markov(outputs,inputs,3,dt=period)
        assert_allclose(estimated,coefficients/period,atol=1e-9)
    record = ct.TimeResponseData(np.arange(30)*.2,outputs,inputs=inputs)
    assert_allclose(ct.markov(record,3),coefficients/.2,atol=1e-9)
    # Noisy records demand least squares, including the requested initial omission.
    noisy = outputs + rng.normal(scale=.2,size=outputs.shape)
    noisy[:,:3] += 5
    for truncate in [False,True]:
        # Enough usable observations: no underdetermined-estimate notification.
        call = invoke(ct.markov,(noisy,inputs,3),{'truncate':truncate})
        assert call.returned and not user_warnings(call, UserWarning)
        estimated = call.value
        start = 3 if truncate else 0
        x = design[start:]
        residual = x@estimated.transpose(0,2,1).reshape(2,6).T-noisy[:,start:].T
        assert_allclose(x.T@residual,0,atol=1e-8)
    u = np.array([2.,-1.,3.,.5,1.])
    y = np.array([1.,4.,-2.,3.,.7])
    result = ct.markov(y,u)
    assert result.shape == (5,)
    assert_allclose(causal_design(u,5)@result,y,atol=1e-9)
    for truncate in [False,True]:
        short_u, short_y = inputs[:,:5],outputs[:,:5]
        with pytest.warns(UserWarning):
            estimate = ct.markov(short_y,short_u,3,truncate=truncate)
        x = causal_design(short_u,3)[3 if truncate else 0:]
        residual = x@estimate.transpose(0,2,1).reshape(2,6).T-short_y[:,3 if truncate else 0:].T
        assert_allclose(x.T@residual,0,atol=1e-8)
    with pytest.raises(ct.VelunexDimension):
        ct.markov(outputs[:,:-1],inputs,3)
