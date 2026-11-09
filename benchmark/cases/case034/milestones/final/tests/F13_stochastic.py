# feature: F13
"""Acceptance of stochastic signals and Kalman estimation through public APIs."""

import velunex as ct
import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.integrate import solve_ivp
from scipy.linalg import solve_continuous_are, solve_discrete_are
from F06_helpers import assert_riccati_result
from F13_helpers import assert_gaussian_white, estimation_law


def test_gaussian_noise_intensity_and_independence():
    q = np.array([[1.7, .65], [.65, .9]])
    for spacing, discrete in ((.2, False), (.05, False), (.2, True)):
        time = np.arange(100000) * spacing
        samples = ct.white_noise(time, q, **({'dt': spacing} if discrete else {}))
        assert samples.shape == (2, len(time))
        assert_gaussian_white(samples, q if discrete else q / spacing)
    with pytest.raises(ValueError):
        ct.white_noise([0., .1, .25], q)
    with pytest.raises(ValueError):
        ct.white_noise([0., .1, .2], np.ones((2, 3)))


def test_lagged_channel_correlation_and_validation():
    time = np.arange(5) * .3 + 2
    x = np.array([[2., -1., 3., 0., 4.], [-2., 5., 1., 2., -3.]])
    y = np.array([[1., 3., -2., 4., 2.]])
    for other in (y, None):
        second = x if other is None else other
        lag, values = ct.correlation(time, x, other, squeeze=False)
        offsets = np.arange(-4, 5)
        assert_allclose(lag, offsets * .3, atol=1e-12)
        # Definition over actual overlapping sample pairs, independent of FFT
        # or convolution implementations. Axes are (second, first, lag).
        expected = np.zeros((len(second), len(x), len(offsets)))
        for k, offset in enumerate(offsets):
            for i in range(5):
                j = i - offset
                if 0 <= j < 5:
                    expected[:, :, k] += np.outer(second[:, j], x[:, i]) / 4
        assert_allclose(values, expected, rtol=1e-12, atol=1e-12)
    for bad_time, first, second in ((time, x[:, :-1], y),
                                    (time, x, y[:, :-1]),
                                    ([0, 1, 2, 3, 5], x, y)):
        with pytest.raises(ValueError):
            ct.correlation(bad_time, first, second)


def test_stationary_kalman_optimum_and_timebase():
    g = np.array([[1., .25], [.5, .75]])
    c = np.array([[1., -.4], [.2, 1.]])
    q = np.array([[.75, .125], [.125, .5]])
    r = np.array([[1.2, .2], [.2, .8]])
    for discrete, a in ((False, np.array([[.2, 1.], [-.4, -.3]])),
                        (True, np.array([[1.05, .2], [-.1, .85]]))):
        model = ct.ss(a, g, c, np.zeros((2, 2)), .25 if discrete else 0)
        for entry, args in (((ct.dlqe if discrete else ct.lqe), (a, g, c, q, r)),
                            (ct.lqe, (model, q, r))):
            gain, p, poles = entry(*args)
            # Estimation is the dual Riccati problem; symmetry, optimality,
            # stabilizing branch and the entire pole multiset are checked.
            assert_riccati_result((p, poles, gain.T), a.T, c.T,
                                  g @ q @ g.T, r, np.zeros((2, 2)),
                                  np.eye(2), discrete=discrete)
            assert np.linalg.eigvalsh(p).min() > 0


def test_continuous_dynamic_covariance_and_prediction():
    a = np.array([[-.4, .7], [-.2, -.8]])
    b = np.array([[1.], [.3]])
    g = np.array([[.4], [1.2]])
    c = np.array([[1., -.6]])
    q, r = np.array([[.5]]), np.array([[.8]])
    p0 = np.array([[1.3, .2], [.2, .7]])
    initial = np.r_[.4, -.3, p0.ravel()]
    inputs = np.array([1.1, -.2])
    time = np.linspace(0, 1.5, 31)
    plants = (
        (ct.ss(a, np.column_stack((b, g)), c, np.zeros((1, 2)),
               inputs=['actuation', 'disturbance']),
         {'control_indices': ['actuation'], 'disturbance_indices': ['disturbance']}),
        (ct.ss(a, b, np.eye(2), np.zeros((2, 1))), {'G': g, 'C': c}))
    for plant, selection in plants:
        est = ct.create_estimator_iosystem(
            plant, q, r, P0=p0, estimate_labels=['first', 'second'],
            covariance_labels=['aa', 'ab', 'ba', 'bb'], **selection)
        assert est.output_labels == ['first', 'second']
        assert est.state_labels == ['first', 'second', 'aa', 'ab', 'ba', 'bb']
        assert_allclose(est.output(0, initial, inputs), initial[:2])
        steady = solve_continuous_are(a.T, c.T, g @ q @ g.T, r)
        equilibrium = np.r_[np.zeros(2), steady.ravel()]
        assert_allclose(est.dynamics(0, equilibrium, np.zeros(2)),
                        np.zeros(6), atol=1e-10)
        for correct in (True, False):
            params = {} if correct else {'correct': False}
            law = lambda t, z: estimation_law(
                a, b, c, g, q, r, z, inputs, discrete=False, correct=correct)
            assert_allclose(est.dynamics(0, initial, inputs, params=params),
                            law(0, initial), atol=1e-12)
            reference = solve_ivp(law, (time[0], time[-1]), initial,
                                  t_eval=time, rtol=1e-10, atol=1e-12)
            assert reference.success
            result = ct.input_output_response(
                est, time, np.repeat(inputs[:, None], len(time), axis=1),
                initial, params=params, squeeze=False,
                solve_ivp_kwargs={'rtol': 1e-9, 'atol': 1e-11})
            assert_allclose(result.states, reference.y, rtol=2e-7, atol=2e-9)
            assert_allclose(result.outputs, reference.y[:2], rtol=2e-7, atol=2e-9)


def test_discrete_one_step_covariance_and_fixed_point():
    a = np.array([[.8, .25], [-.15, .9]])
    b = np.array([[.7], [.2]])
    c = np.array([[1., -.3]])
    q, r = np.array([[.6]]), np.array([[.9]])
    plant = ct.ss(a, b, c, 0, .2)
    p0 = np.array([[1.2, .3], [.3, .8]])
    steady = solve_discrete_are(a.T, c.T, b @ q @ b.T, r)
    est = ct.create_estimator_iosystem(plant, q, r, P0=p0)
    time = np.arange(9) * .2
    inputs = np.vstack((np.sin(np.arange(9)), np.linspace(-.4, .6, 9)))
    for covariance, correct in ((p0, True), (p0, False), (steady, True)):
        initial = np.r_[.2, -.5, covariance.ravel()]
        history = [initial]
        for k in range(len(time) - 1):
            history.append(estimation_law(a, b, c, b, q, r, history[-1],
                           inputs[:, k], discrete=True, correct=correct))
        expected = np.array(history).T
        result = ct.input_output_response(
            est, time, inputs, initial, squeeze=False,
            params={} if correct else {'correct': False})
        assert_allclose(result.states, expected, rtol=1e-9, atol=1e-10)
        assert_allclose(result.outputs, expected[:2], rtol=1e-9, atol=1e-10)
        if covariance is steady:
            assert_allclose(result.states[2:],
                            np.repeat(steady.ravel()[:, None], len(time), axis=1),
                            rtol=1e-9, atol=1e-10)


def test_estimation_rejections():
    a, g, c = -.5 * np.eye(2), np.eye(2), np.eye(2)
    q, r = np.eye(2), np.eye(2)
    for entry in (ct.lqe, ct.dlqe):
        entry(a, g, c, q, r)
        for bad_q, bad_r in ((np.eye(3), r), (q, np.eye(3)),
                             (np.array([[1., .5], [0., 1.]]), r),
                             (q, np.array([[1., .5], [0., 1.]]))):
            with pytest.raises((ct.VelunexDimension, ct.VelunexArgument)):
                entry(a, g, c, bad_q, bad_r)
        for cross in (np.zeros((2, 2)), .1 * np.eye(2)):
            with pytest.raises(ct.VelunexNotImplemented):
                entry(a, g, c, q, r, cross)
    plant = ct.ss(a, g, c, np.zeros((2, 2)))
    ct.create_estimator_iosystem(plant, q, r, P0=np.eye(2))
    with pytest.raises(NotImplementedError):
        ct.create_estimator_iosystem(ct.ss(a, g, c, np.eye(2)), q, r)
    with pytest.raises(ValueError):
        ct.create_estimator_iosystem(plant, q, r, C=np.array([[1., 0.]]))
    with pytest.raises(ct.VelunexDimension):
        ct.create_estimator_iosystem(plant, q, np.eye(3), P0=np.eye(2))
    with pytest.raises(ValueError):
        ct.create_estimator_iosystem(ct.ss(a, g, [[1., 0.]], np.zeros((1, 2))),
                                    q, np.eye(1), C=np.array([[0., 1.]]))
