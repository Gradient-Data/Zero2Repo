# feature: F12
"""Public state-feedback design acceptance tests."""

import velunex as ct
import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.integrate import quad_vec
from scipy.linalg import expm
from F01_helpers import assert_unordered_roots
from F06_helpers import assert_riccati_result


def test_full_and_selective_pole_assignment():
    a = np.array([[0., 1.], [2., -.5]])
    b = np.array([[0.], [1.]])
    for entry, poles in ((ct.place, [-1.2, -3.1]),
                         (ct.place, [-1.+2.j, -1.-2.j]),
                         (ct.place_acker, [-2., -2.]),
                         (ct.place_acker, [-.7+1.3j, -.7-1.3j]),
                         (ct.place_varga, [-1.5, -2.5])):
        gain = entry(a, b, poles)
        assert gain.shape == (1, 2)
        assert_allclose(np.imag(gain), 0, atol=1e-10)
        # Double roots lose roughly half the floating-point digits.
        assert_unordered_roots(np.linalg.eigvals(a - b @ gain),
                               np.asarray(poles), rtol=1e-6, atol=1e-7)
    with pytest.raises(ValueError):
        ct.place(a, b, [-2., -2.])
    with pytest.raises(ValueError):
        ct.place_acker(np.diag([1., 2.]), b, [-1., -3.])
    # Repetition up to the input rank is feasible; gains need not be unique.
    multi_a = np.array([[.2, 1., 0.], [0., -.5, 1.], [1., 0., .3]])
    multi_b = np.array([[1., 0.], [0., 1.], [0., 1.]])
    requested = np.array([-1., -1., -2.])
    gain = ct.place(multi_a, multi_b, requested)
    assert gain.shape == (2, 3)
    assert_unordered_roots(np.linalg.eigvals(multi_a - multi_b @ gain), requested)
    for discrete, original, alpha, targets, expected in (
        (False, [-3., -.2, 1.], -1., [-2., -4.], [-3., -2., -4.]),
        (True, [-.2, .8, 1.2], .5, [.3, .4], [-.2, .3, .4])):
        dynamics = np.diag(original)
        inputs = np.ones((3, 1))
        gain = ct.place_varga(dynamics, inputs, targets, dtime=discrete, alpha=alpha)
        assert_unordered_roots(np.linalg.eigvals(dynamics - inputs @ gain),
                               np.asarray(expected))


def test_quadratic_optimum_and_model_timebase():
    b = np.array([[1., .2], [.3, 1.]])
    q = np.array([[2., .3], [.3, 1.4]])
    r = np.array([[1.5, .2], [.2, 2.]])
    cross = np.array([[.2, -.1], [.05, .3]])
    for discrete, a in ((False, np.array([[.4, 1.], [-.3, -.2]])),
                        (True, np.array([[1.1, .3], [-.2, .8]]))):
        model = ct.ss(a, b, np.eye(2), np.zeros((2, 2)), .2 if discrete else 0)
        direct = ct.dlqr if discrete else ct.lqr
        # Both raw matrices and timebase dispatch must solve the stated cost.
        for entry, prefix in ((direct, (a, b)), (ct.lqr, (model,))):
            for weights in ((q, r), (q, r, cross)):
                gain, cost, poles = entry(*prefix, *weights)
                n = np.zeros_like(cross) if len(weights) == 2 else cross
                assert_riccati_result((cost, poles, gain), a, b, q, r, n,
                                      np.eye(2), discrete=discrete)
        if discrete:
            gain, cost, poles = ct.dlqr(model, q, r, cross)
            assert_riccati_result((cost, poles, gain), a, b, q, r, cross,
                                  np.eye(2), discrete=True)


def test_integral_feedback_and_invalid_designs():
    b = np.array([[0.], [1.]])
    selection = np.array([[1., .4]])
    q = np.diag([2., 1., 3.])
    r = np.array([[1.7]])
    for discrete, entry, a in (
        (False, ct.lqr, np.array([[0., 1.], [-.4, -.6]])),
        (True, ct.dlqr, np.array([[1., .2], [-.1, .8]]))):
        gain, cost, poles = entry(a, b, q, r, integral_action=selection)
        augmented = np.block([[a, np.zeros((2, 1))],
                              [selection, np.eye(1) if discrete else np.zeros((1, 1))]])
        inputs = np.vstack([b, [[0.]]])
        assert_riccati_result((cost, poles, gain), augmented, inputs, q, r,
                              np.zeros((3, 1)), np.eye(3), discrete=discrete)
        # Observe accumulated state/input cost of the actual returned feedback,
        # including an initially nonzero integral state.
        closed = augmented - inputs @ gain
        running_cost = q + gain.T @ r @ gain
        initial = np.array([.7, -.3, 1.2])
        if discrete:
            state = initial.copy()
            observed = 0.
            for _ in range(2000):
                observed += state @ running_cost @ state
                state = closed @ state
            assert_allclose(state, 0, atol=1e-8)
        else:
            def instantaneous(t):
                state = expm(closed * t) @ initial
                return state @ running_cost @ state
            observed, _ = quad_vec(instantaneous, 0., np.inf, epsabs=1e-9)
        assert_allclose(observed, initial @ cost @ initial, rtol=1e-7, atol=1e-8)
        with pytest.raises(ct.VelunexDimension):
            entry(a, b, np.eye(2), r, integral_action=selection)
        with pytest.raises((ct.VelunexDimension, ct.VelunexArgument)):
            entry(a, b, q, r, integral_action=np.ones((1, 3)))
        # Weight shape and symmetry validation belong to the design entries.
        base = [a, np.eye(2), np.eye(2), np.eye(2)]
        for index, invalid, error in (
            (2, np.eye(3), ct.VelunexDimension),
            (3, np.eye(3), ct.VelunexDimension),
            (2, np.array([[1., .2], [0., 1.]]), ct.VelunexArgument),
            (3, np.array([[1., .2], [0., 1.]]), ct.VelunexArgument)):
            args = base.copy()
            args[index] = invalid
            with pytest.raises(error):
                entry(*args)
        with pytest.raises(ct.VelunexDimension):
            entry(*base, np.ones((3, 2)))
    continuous = ct.ss([[0., 1.], [-1., -.5]], b, np.eye(2), np.zeros((2, 1)), 0)
    with pytest.raises(ct.VelunexArgument):
        ct.dlqr(continuous, np.eye(2), r)
