# feature: F05
"""Acceptance checks for conversion, coordinates, sampling, and delays."""

import math
import numpy as np
import pytest
import velunex as ct
from numpy.testing import assert_allclose
from scipy.integrate import quad, quad_vec
from scipy.linalg import expm
from _helpers import invoke, user_warnings
from F01_helpers import state_space_reference, polynomial_reference, assert_unordered_roots


def test_representation_conversion():
    a = np.array([[-2., 1.], [0., -4.]])
    b, c, d = np.array([[1.], [3.]]), np.array([[2., -1.]]), np.array([[.4]])
    points = np.array([.2+.8j, 1.4-2j, 3.1+.2j])
    for dt in (0, .17, True, None):
        converted = ct.ss2tf(ct.ss(a,b,c,d,dt=dt))
        assert converted.dt == dt
        assert_allclose(converted(points, squeeze=False),
                        state_space_reference(a,b,c,d,points), rtol=1e-8, atol=1e-10)
        num, den = [2., 3., 7.], [2., 8., 6.]
        converted = ct.tf2ss(ct.tf(num,den,dt=dt))
        assert converted.dt == dt
        assert_allclose(converted(points, squeeze=False),
                        polynomial_reference(num,den,points)[None,None,:], rtol=1e-8, atol=1e-10)
    # Multichannel conversions in both directions; channels differ in degree.
    a3 = np.array([[-2.,1.,0.],[0.,-4.,1.],[1.,0.,-3.]])
    b3, c3 = np.array([[1.,0.],[3.,1.],[0.,2.]]), np.array([[2.,-1.,0.],[0.,1.,1.]])
    d3 = np.array([[.4,0.],[.1,-.2]])
    num = [[[2,3],[1]],[[0],[6,1]],[[1,0,2],[-1,4]]]
    den = [[[2,5,3],[1,4]],[[1,3],[2,1]],[[1,2,7],[1,1]]]
    matrix = np.array([[polynomial_reference(n,d,points) for n,d in zip(nr,dr)]
                       for nr,dr in zip(num,den)])
    for dt in (0, .17):
        converted = ct.ss2tf(ct.ss(a3,b3,c3,d3,dt=dt))
        assert converted.dt == dt
        assert (converted.noutputs, converted.ninputs) == (2, 2)
        assert_allclose(converted(points, squeeze=False),
                        state_space_reference(a3,b3,c3,d3,points), rtol=1e-8, atol=1e-10)
        converted = ct.tf2ss(ct.tf(num,den,dt=dt))
        assert converted.dt == dt
        assert (converted.noutputs, converted.ninputs) == (3, 2)
        assert_allclose(converted(points, squeeze=False), matrix, rtol=1e-8, atol=1e-10)
    with pytest.raises(ValueError):
        ct.tf2ss(ct.tf([1,2,3],[1,4]))


def test_similarity_direction_and_time_scale():
    model = ct.ss([[-2,1],[3,-4]], [[1,2],[3,-1]], [[2,3]], [[.2,-.3]])
    transform = np.array([[2.,1.],[-1.,3.]])
    for inverse in (False, True):
        mapping = np.linalg.inv(transform) if inverse else transform
        for options, scale in [({},1), ({'timescale':2.5},2.5)]:
            changed = ct.similarity_transform(model,transform,inverse=inverse,**options)
            assert_allclose(changed.A @ mapping, mapping @ model.A / scale, atol=1e-10)
            assert_allclose(changed.B, mapping @ model.B / scale, atol=1e-10)
            assert_allclose(changed.C @ mapping, model.C, atol=1e-10)
            assert_allclose(changed.D, model.D, atol=1e-10)
            for x,u in [([1.,-2.],[.7,2.]), ([-.3,1.],[2.,-1.])]:
                assert_allclose(changed.dynamics(0,mapping@x,u),
                                mapping@(model.A@x+model.B@u)/scale, atol=1e-10)
                assert_allclose(changed.output(0,mapping@x,u), model.C@x+model.D@u, atol=1e-10)


def test_canonical_forms_and_refusals():
    model = ct.ss([[-2,1],[0,-3]], [[1],[2]], [[3,-1]], [[.2]])
    companion = np.array([[-5.,-6.],[1.,0.]])
    for entry, expected, reachable in [
            (ct.canonical_form,companion,True), (ct.reachable_form,companion,True),
            (ct.observable_form,companion.T,False),
            (lambda s: ct.canonical_form(s,'observable'),companion.T,False)]:
        changed, mapping = entry(model)
        assert_allclose(changed.A,expected,atol=1e-9)
        assert_allclose(changed.B if reachable else changed.C,
                        [[1],[0]] if reachable else [[1,0]],atol=1e-9)
        assert_allclose(changed.A@mapping,mapping@model.A,atol=1e-9)
        assert_allclose(changed.B,mapping@model.B,atol=1e-9)
        assert_allclose(changed.C@mapping,model.C,atol=1e-9)
        assert_allclose(changed.D,model.D,atol=1e-9)
    # Dense coordinates conceal a real pole and a complex pair. Block ordering
    # and basis within the pair are not fixed.
    base = np.array([[-1.,0,0],[0,-2,3],[0,-3,-2]])
    mix = np.array([[1.,2,0],[0,1,1],[1,0,2]])
    modal_input = ct.ss(mix@base@np.linalg.inv(mix),[[1],[2],[3]],[[2,1,4]],0)
    for entry in (ct.modal_form, lambda s: ct.canonical_form(s,'modal')):
        changed, mapping = entry(modal_input)
        assert np.isrealobj(changed.A)
        assert_allclose(modal_input.A@mapping,mapping@changed.A,atol=1e-8)
        assert_allclose(modal_input.B,mapping@changed.B,atol=1e-8)
        assert_allclose(changed.C,modal_input.C@mapping,atol=1e-8)
        assert_allclose(changed.D,modal_input.D,atol=1e-8)
        assert_unordered_roots(np.linalg.eigvals(changed.A),[-1,-2+3j,-2-3j])
        isolated = [i for i in range(3) if np.all(np.abs(np.delete(changed.A[i],i))<1e-8)
                    and np.all(np.abs(np.delete(changed.A[:,i],i))<1e-8)]
        assert len(isolated) == 1
        assert_allclose(changed.A[isolated[0],isolated[0]],-1,atol=1e-8)
    for entry in (ct.reachable_form,ct.observable_form):
        with pytest.raises(ct.VelunexNotImplemented):
            entry(ct.ss([[-1,0],[0,-2]],np.eye(2),np.eye(2),np.zeros((2,2))))
    with pytest.raises(ValueError):
        ct.reachable_form(ct.ss([[-1,0],[0,-2]],[[1],[0]],[[1,1]],0))
    with pytest.raises(ValueError):
        ct.observable_form(ct.ss([[-1,0],[0,-2]],[[1],[1]],[[1,0]],0))


def test_hold_sampling_and_refusals():
    period = .23
    time = np.arange(9)*period
    inputs = np.array([0.,1.,-.4,2.,.5,-1.,1.3,0.,.7])
    for model in (ct.ss(-1.7,1,2.3,0),ct.tf([2.3],[1,1.7])):
        for options, linear in [({},False),({'method':'zoh'},False),({'method':'foh'},True)]:
            sampled = ct.sample_system(model,period,**options)
            assert sampled.dt == period
            expected = [0.]
            for k in range(len(time)-1):
                integral = quad(lambda t: np.exp(-1.7*(period-t))*2.3*(
                    inputs[k]+(inputs[k+1]-inputs[k])*t/period if linear else inputs[k]),0,period)[0]
                expected.append(np.exp(-1.7*period)*expected[-1]+integral)
            response = ct.forced_response(sampled,time,inputs)
            assert_allclose(response.outputs,expected,rtol=1e-8,atol=1e-10)
        with pytest.raises(ValueError):
            ct.sample_system(ct.sample_system(model,period),period)
    # Coupled states: the hold integrals involve the full matrix exponential.
    a2 = np.array([[-1.,2.],[-3.,-.5]])
    b2, c2 = np.array([[1.],[.4]]), np.array([[2.,-1.]])
    coupled = ct.ss(a2,b2,c2,0)
    for options, linear in [({},False),({'method':'foh'},True)]:
        sampled = ct.sample_system(coupled,period,**options)
        state, expected = np.zeros(2), [0.]
        for k in range(len(time)-1):
            integral = quad_vec(lambda t: expm(a2*(period-t))@b2[:,0]*(
                inputs[k]+(inputs[k+1]-inputs[k])*t/period if linear else inputs[k]),
                0,period,epsabs=1e-13)[0]
            state = expm(a2*period)@state+integral
            expected.append(c2[0]@state)
        assert_allclose(ct.forced_response(sampled,time,inputs).outputs,expected,
                        rtol=1e-8,atol=1e-10)
    with pytest.raises(ct.VelunexMIMONotImplemented):
        ct.sample_system(ct.tf([[[1],[2]]],[[[1,2],[1,3]]]),period)


def test_bilinear_weights_and_differences():
    period = .19
    points = np.array([1.2+.4j,.7+.8j,-.3+1.1j])
    choices = [('gbt',{'alpha':a},a) for a in (0,.31,.5,1)]
    choices += [('bilinear',{},.5),('euler',{},0),('backward_diff',{},1)]
    for model in (ct.tf([2,3],[1,4,5]),ct.ss([[-1,2],[-1,-3]],[[1],[2]],[[2,1]],.2)):
        for method,options,alpha in choices:
            sampled = ct.sample_system(model,period,method=method,**options)
            continuous_points = (points-1)/(period*(alpha*points+1-alpha))
            if isinstance(model,ct.TransferFunction):
                expected = polynomial_reference([2,3],[1,4,5],continuous_points)[None,None,:]
            else:
                expected = state_space_reference(model.A,model.B,model.C,model.D,continuous_points)
            assert sampled.dt == period
            assert_allclose(sampled(points,squeeze=False),expected,rtol=1e-8,atol=1e-10)
        for options in ({},{'alpha':-.1},{'alpha':1.1}):
            with pytest.raises(ValueError):
                ct.sample_system(model,period,method='gbt',**options)


def test_impulse_invariant_normalization():
    for period in (.13,.37):
        for model in (ct.ss(-2,1,3,0),ct.tf([3],[1,2])):
            sampled = ct.sample_system(model,period,method='impulse')
            time = np.arange(7)*period
            inputs = np.zeros(7)
            inputs[0] = 1
            assert sampled.dt == period
            assert_allclose(ct.forced_response(sampled,time,inputs).outputs,
                            period*3*np.exp(-2*time),rtol=1e-8,atol=1e-10)
        for model in (ct.ss(-2,1,3,.4),ct.tf([.4,3.8],[1,2])):
            with pytest.raises(ValueError):
                ct.sample_system(model,period,method='impulse')


def test_matched_roots_and_low_frequency_gain():
    for zeros,poles,gain in [([-3],[-1,-2],2),([], [0],1.7),
                             ([],[0,0],2.1),([0],[-2,-4],3),([-2],[0,-3],2)]:
        num,den = gain*np.poly(zeros),np.poly(poles)
        for period in (.16,.41):
            sampled = ct.sample_system(ct.tf(np.atleast_1d(num),np.atleast_1d(den)),period,method='matched')
            assert sampled.dt == period
            assert_unordered_roots(sampled.zeros(),np.exp(np.array(zeros)*period))
            assert_unordered_roots(sampled.poles(),np.exp(np.array(poles)*period),rtol=1e-6)
            # Approach the origin without evaluating a pole there. The error
            # budget allows the O(s) difference between the two low-frequency limits.
            s = 1e-5j
            expected = polynomial_reference(np.atleast_1d(num),np.atleast_1d(den),s)
            assert_allclose(sampled(np.exp(s*period))/expected,1,rtol=2e-4,atol=2e-4)


def test_prewarping_and_ignored_warning():
    period,omega = .28,2.4
    for model in (ct.tf([2,3],[1,4,5]),ct.ss(-2,1,3,.4)):
        expected = (2j*omega+3)/((1j*omega)**2+4j*omega+5) if isinstance(model,ct.TransferFunction) else .4+3/(2+1j*omega)
        for method,options in [('bilinear',{}),('gbt',{'alpha':.5})]:
            # Prewarping is applied here, so no ignored-prewarp notification.
            result = invoke(ct.sample_system,(model,period),
                            dict(method=method,prewarp_frequency=omega,**options))
            assert result.returned and not user_warnings(result, UserWarning)
            sampled = result.value
            assert sampled.dt == period
            assert_allclose(sampled(np.exp(1j*omega*period)),expected,rtol=1e-8,atol=1e-10)
        for method,options,alpha in [('euler',{},0),('gbt',{'alpha':.3},.3)]:
            with pytest.warns(UserWarning):
                sampled = ct.sample_system(model,period,method=method,prewarp_frequency=omega,**options)
            z = 1.2+.7j
            s = (z-1)/(period*(alpha*z+1-alpha))
            expected = (2*s+3)/(s*s+4*s+5) if isinstance(model,ct.TransferFunction) else .4+3/(2+s)
            assert_allclose(sampled(z),expected,rtol=1e-8,atol=1e-10)


def test_delay_approximation_orders_and_refusals():
    for delay,options,n,m in [(1.3,{},1,1),(.7,{'n':0},0,0),
                             (1.7,{'n':3},3,3),(.8,{'n':4,'numdeg':2},4,2),
                             (2.1,{'n':3,'numdeg':0},3,0)]:
        num,den = map(np.asarray,ct.pade(delay,**options))
        assert len(num) == m+1 and len(den) == n+1
        assert num[0] != 0 and den[0] != 0 and den[-1] != 0
        # The defining Taylor identity Q(s) exp(-T s) - P(s) has
        # zero coefficients through degree m+n; no product recurrence is copied.
        p,q = num[::-1]/den[-1],den[::-1]/den[-1]
        expansion = np.array([(-delay)**k/math.factorial(k) for k in range(m+n+1)])
        lhs = np.convolve(q,expansion)[:m+n+1]
        rhs = np.pad(p,(0,n))
        assert_allclose(lhs,rhs,rtol=1e-8,atol=1e-10)
    num,den = ct.pade(0,n=4,numdeg=2)
    assert_allclose(polynomial_reference(num,den,np.array([0,1j,2+3j])),1,atol=1e-10)
    for args in [(-1,2,None),(1,-1,None),(1,2,3),(1,2,-3)]:
        with pytest.raises(ValueError):
            ct.pade(*args)
