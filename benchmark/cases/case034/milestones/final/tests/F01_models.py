# feature: F01
"""Acceptance checks for the public linear-model interface."""

import numpy as np
import pytest
import velunex as ct
from numpy.testing import assert_allclose, assert_array_equal

from _helpers import isolated_mapping
from F01_helpers import (state_space_reference, polynomial_reference,
                         zpk_reference)


def test_model_construction_and_evaluation():
    # FP-01.01, FP-01.04. Tolerances allow floating point roundoff in these
    # small, well-conditioned equations, not a particular realization method.
    a = np.array([[-2., 1.], [0., -3.]])
    b = np.array([[1., 2.], [3., -1.]])
    c = np.array([[2., 1.], [-1., 4.], [3., -2.]])
    d = np.array([[0., 1.], [2., 0.], [-1., 3.]])
    points = np.array([0., .4+1.3j, 2.-.7j])
    for dt in (0, .2):
        model = ct.ss(a, b, c, d, dt=dt)
        assert (model.nstates, model.ninputs, model.noutputs) == (2, 2, 3)
        for field, supplied in zip((model.A, model.B, model.C, model.D), (a,b,c,d)):
            assert_array_equal(field, supplied)
        for x, u in [([2., -1.], [3., 4.]), ([-.5, 2.], [1., -2.])]:
            assert_allclose(model.dynamics(.7, x, u), a @ x + b @ u, atol=1e-10)
            assert_allclose(model.output(.7, x, u), c @ x + d @ u, atol=1e-10)
        assert_allclose(model(points, squeeze=False),
                        state_space_reference(a,b,c,d,points), rtol=1e-9, atol=1e-10)
    single = ct.ss(-2, 3, 4, 1)
    assert (single.nstates, single.ninputs, single.noutputs) == (1, 1, 1)
    assert_allclose(single(points, squeeze=False), (1+12/(points+2))[None,None,:])
    static = ct.ss([], [], [], d)
    assert (static.nstates, static.ninputs, static.noutputs) == (0, 2, 3)
    assert_allclose(static.output(0, [], [2, -1]), d @ [2,-1])
    assert_allclose(static(points, squeeze=False), np.repeat(d[:,:,None], 3, axis=2))

    # Includes non-monic denominators, unequal degrees, zero and static channels.
    num = [[[2, 3], [1, -2, 4]], [[0], [6]]]
    den = [[[2, 5, 3], [2, 1]], [[1, 3], [2]]]
    tf = ct.tf(num, den)
    assert (tf.ninputs, tf.noutputs) == (2, 2)
    expected = np.empty((2,2,len(points)), complex)
    for out in range(2):
        for inp in range(2):
            expected[out,inp] = polynomial_reference(num[out][inp], den[out][inp], points)
            # Exposed coefficients may be scaled or normalized equivalently.
            assert_allclose(polynomial_reference(tf.num[out][inp], tf.den[out][inp], points),
                            expected[out,inp], rtol=1e-9, atol=1e-10)
    assert_allclose(tf(points, squeeze=False), expected, rtol=1e-9, atol=1e-10)
    for zeros, poles, gain in [([-1+2j,-1-2j], [-2,-3], 2), ([], [-4], -3)]:
        model = ct.zpk(zeros, poles, gain)
        assert (model.ninputs, model.noutputs) == (1,1)
        assert_allclose(model(points, squeeze=False),
                        zpk_reference(zeros,poles,gain,points)[None,None,:],
                        rtol=1e-9, atol=1e-10)


def test_timebase_defaults_and_compatibility():
    # FP-01.02; keep global configuration as found by subsequent tests.
    with isolated_mapping(ct.config.defaults):
        assert ct.ss(-1,1,1,0).dt == 0
        assert ct.tf([1],[1,2]).dt == 0
        assert ct.ss([],[],[],[[2]]).dt is None
        assert ct.tf([2],[1]).dt is None
        for factory in (lambda dt: ct.ss(-1,1,1,0,dt=dt),
                        lambda dt: ct.tf([1],[1,2],dt=dt)):
            for dt in (None, 0, True, .125):
                model = factory(dt)
                if dt is None or dt is True:
                    assert model.dt is dt
                else:
                    assert model.dt == dt
            pairs = [(None,None,None), (None,0,0), (None,True,True),
                     (None,.125,.125), (True,True,True), (True,.125,.125),
                     (0,0,0), (.125,.125,.125)]
            for left,right,expected in pairs:
                for first,second in ((left,right),(right,left)):
                    combined = factory(first) + factory(second)
                    if expected is None or expected is True:
                        assert combined.dt is expected
                    else:
                        assert combined.dt == expected
            for left,right in [(0,True), (0,.125), (.125,.25)]:
                for first,second in ((left,right),(right,left)):
                    with pytest.raises(ValueError):
                        factory(first) + factory(second)


def test_named_channel_selection():
    # FP-01.03, FP-01.04: distinct dynamics make wrong channel routing visible.
    points = np.array([.2+.7j, 1.1-2j])
    a,b,c,d = ([[-2,1],[0,-3]], [[1,2],[3,-1]],
               [[2,1],[-1,4],[3,-2]], [[0,1],[2,0],[-1,3]])
    inputs, outputs = ['force','drive'], ['position','speed','load']
    ss = ct.ss(a,b,c,d, name='plant', inputs=inputs, outputs=outputs, states=['q','v'])
    assert ss.state_labels == ['q','v']
    assert ss.nstates == 2
    num = [[[1],[2,1]], [[3,-1],[4]], [[-2],[1,0,2]]]
    den = [[[1,2],[1,3]], [[1,4],[1,5]], [[1,6],[1,7]]]
    tf = ct.tf(num,den,name='plant',inputs=inputs,outputs=outputs)
    tf_expected = np.array([[polynomial_reference(n,d,points) for n,d in zip(nrow,drow)]
                            for nrow,drow in zip(num,den)])
    for model, expected in [(ss,state_space_reference(a,b,c,d,points)), (tf,tf_expected)]:
        assert model.name == 'plant'
        assert model.input_labels == inputs and model.output_labels == outputs
        assert (model.ninputs,model.noutputs) == (2,3)
        assert_allclose(model(points,squeeze=False),expected,rtol=1e-9,atol=1e-10)
        for key, rows, cols in [((2,0),[2],[0]),
                                (('speed','drive'),[1],[1]),
                                ((['load','position'],['drive','force']),[2,0],[1,0]),
                                ((slice(0,2),slice(None)),[0,1],[0,1])]:
            selected = model[key]
            assert (selected.noutputs,selected.ninputs) == (len(rows),len(cols))
            assert selected.output_labels == [outputs[i] for i in rows]
            assert selected.input_labels == [inputs[i] for i in cols]
            assert_allclose(selected(points,squeeze=False),expected[rows][:,cols],
                            rtol=1e-9,atol=1e-10)


def test_frequency_samples_and_refusal():
    # FP-01.05: every channel and sample is observed directly.
    omega = np.array([.2,.7,1.4,2.5])
    data = np.array([[[1+2j,3-1j,-2+.5j,4], [2j,4+1j,3-2j,1]],
                     [[-1j,2,5+2j,-3j], [4,2-3j,1j,-2+1j]]])
    for supplied, expected in [(data,data), (data[0,1],data[0:1,1:2])]:
        model = ct.frd(supplied,omega)
        assert (model.noutputs,model.ninputs) == expected.shape[:2]
        assert_array_equal(model.omega,omega)
        assert_array_equal(model.frdata,expected)
        assert_allclose(model.eval(omega,squeeze=False),expected,rtol=1e-9,atol=1e-10)
        assert_allclose(model.eval(omega[[1,3]],squeeze=False),expected[:,:,[1,3]])
        with pytest.raises(ValueError):
            model.eval([.5],squeeze=False)
    with pytest.raises(TypeError):
        ct.frd(data,omega[:-1])


def test_frequency_interpolation():
    # FP-01.05: affine channels include zero slope. No general spline choice
    # or extrapolation behavior is prescribed by this observation.
    omega = np.array([.2,.7,1.4,2.5])
    offsets = np.array([[2+3j,-1+.5j],[4-2j,1+1j]])
    slopes = np.array([[0,-.5+.2j],[1+2j,-2-.5j]])
    data = offsets[:,:,None] + slopes[:,:,None]*omega
    model = ct.frd(data,omega,smooth=True)
    assert_allclose(model.eval(omega,squeeze=False),data,rtol=1e-9,atol=1e-10)
    # Probe the open intervals and both sides of interior sample boundaries.
    query = np.array([.3,.5,.7-1e-6,.7+1e-6,1.1,1.4-1e-6,1.4+1e-6,2.1])
    assert_allclose(model.eval(query,squeeze=False),
                    offsets[:,:,None]+slopes[:,:,None]*query,rtol=1e-9,atol=1e-10)
    # Non-affine measurements: require sample reproduction and continuity,
    # without selecting the interpolating curve between measurements.
    data = 1/(1+1j*omega)
    model = ct.frd(data, omega, smooth=True)
    assert_allclose(model.eval(omega, squeeze=False)[0, 0], data, rtol=1e-9, atol=1e-10)
    probes = np.r_[omega[1:-1], (omega[:-1]+omega[1:])/2]
    for point in probes:
        value = model.eval([point], squeeze=False)[0, 0, 0]
        scale = max(1., float(abs(value)), float(np.max(abs(data))))
        # Shrink toward each point; no derivative or convergence rate is fixed.
        errors = []
        for exponent in range(3, 13):
            delta = min(point-omega[0], omega[-1]-point)*10.**(-exponent)
            nearby = model.eval([point-delta, point+delta], squeeze=False)[0, 0]
            assert np.all(np.isfinite(nearby))
            errors.append(np.max(abs(nearby-value)))
        assert min(errors) <= 1e-6*scale
    with pytest.raises(ValueError):
        ct.frd([2+1j],[.5],smooth=True)


def test_random_models_stability_and_dimensions():
    # FP-01.06 promises stability, not a pole distribution or reproducibility.
    for generator, discrete in [(ct.rss,False),(ct.drss,True)]:
        for states,outputs,inputs in [(1,1,1),(4,2,3)]:
            for strictly_proper in (False,True):
                model = generator(states,outputs,inputs,strictly_proper=strictly_proper)
                assert (model.nstates,model.noutputs,model.ninputs) == (states,outputs,inputs)
                assert model.A.shape == (states,states)
                assert model.B.shape == (states,inputs)
                assert model.C.shape == (outputs,states)
                assert model.D.shape == (outputs,inputs)
                for matrix in (model.A,model.B,model.C,model.D):
                    assert np.isfinite(matrix).all()
                poles = np.linalg.eigvals(model.A)
                assert np.all(abs(poles)<1) if discrete else np.all(poles.real<0)
                if strictly_proper:
                    assert_array_equal(model.D,np.zeros((outputs,inputs)))
        for axis in range(3):
            for invalid in (0,-1,1.5):
                dimensions = [2,2,2]
                dimensions[axis] = invalid
                with pytest.raises((ValueError, TypeError)):
                    generator(*dimensions)


def test_invalid_models_and_signal_descriptions():
    # FP-01.01, FP-01.03: successful neighbors accompany explicit refusals.
    ss = ct.ss([[-1,0],[0,-2]],[[1],[2]],[[2,1]],[[0]],
               inputs=['force'],outputs=['position'],states=['q','v'])
    tf = ct.tf([2,1],[1,3],inputs=['force'],outputs=['position'])
    assert_allclose(ss([0],squeeze=False),[[[3.]]])
    assert_allclose(tf([0],squeeze=False),[[[1/3]]])
    invalid_matrices = [([[1,2]],[[1]],[[1]],[[0]]),
                        ([[-1,0],[0,-2]],[[1]],[[1,1]],[[0]]),
                        ([[-1,0],[0,-2]],[[1],[1]],[[1]],[[0]]),
                        ([[-1]],[[1]],[[1]],[[0,0]])]
    for matrices in invalid_matrices:
        with pytest.raises(ValueError):
            ct.ss(*matrices)
    for num,den in [([[[1],[2],[3]]],[[[1,2],[1,3]]]),
                    ([[[1]],[[2]],[[3]]],[[[1,2]],[[1,3]]]), ([1],[0,0])]:
        with pytest.raises(ValueError):
            ct.tf(num,den)
    for keyword in ('inputs','outputs','states'):
        with pytest.raises(ValueError):
            ct.ss(-1,1,1,0,**{keyword:['one','two']})
    for keyword in ('inputs','outputs'):
        with pytest.raises(ValueError):
            ct.tf([1],[1,2],**{keyword:['one','two']})
    for model in (ss,tf):
        for key in [('absent','force'),('position','absent')]:
            with pytest.raises(ValueError):
                model[key]
