# feature: F15
"""Acceptance of robust controllers by their closed-loop objectives."""
import velunex as ct
import numpy as np
import pytest
from numpy.testing import assert_allclose
from F01_helpers import state_space_reference
from F15_helpers import (close_generalized, assert_stable_dynamics,
                         impulse_energy, sampled_peak, model_matrices)


def test_h2_minimum_energy():
    # Scalar LQG: the positive control and estimation Riccati roots give
    # J* = X + X**2 Y for unit process/measurement noise and actuation cost.
    # This is an objective certificate, not a prescribed controller realization.
    for drift, penalty in [(0., 1.), (.7, 2.3)]:
        plant = ct.ss([[drift]], [[1, 0, 1]],
                      [[np.sqrt(penalty)], [0], [1]],
                      [[0, 0, 0], [0, 0, 1], [0, 1, 0]])
        controller = ct.h2syn(plant, 1, 1)
        closed = close_generalized(plant, controller)
        x = drift + np.sqrt(drift**2 + penalty)
        y = drift + np.sqrt(drift**2 + 1)
        assert_allclose(impulse_energy(closed), x + x*x*y, rtol=2e-6, atol=2e-7)


def test_hinfinity_gain_and_feedthrough():
    # The symmetric integrator's scalar bounded-real feasibility condition is
    # X=Y=1/sqrt(1-gamma**-2), XY < gamma**2, hence infimum sqrt(2).
    # Changing the actuation coordinate v=u+h*(x+w2) and measurement
    # y=x+w2+d*u preserves that optimization and exercises nonzero D11/D22.
    for h, direct, scale in [(0., 0., 1.), (.35, .2, 1.7)]:
        plant = ct.ss([[h]], [[1, h, 1]], [[scale], [scale*h], [1]],
                      [[0, 0, 0], [0, scale*h, scale], [0, 1, direct]])
        controller, returned, gain, _ = ct.hinfsyn(plant, 1, 1)
        closed = close_generalized(plant, controller)
        assert_stable_dynamics(closed)
        assert_stable_dynamics(model_matrices(returned))
        points = 1j*np.r_[0, np.logspace(-4, 5, 90)]
        assert_allclose(state_space_reference(*model_matrices(returned), points),
                        state_space_reference(*closed, points), rtol=2e-5, atol=2e-6)
        optimum = scale*np.sqrt(2)
        assert_allclose(gain, optimum, rtol=3e-4)
        assert_allclose(sampled_peak(closed), gain, rtol=3e-4)


def test_weighted_generalized_channels_and_rejections():
    plant = ct.ss([[-1, .3], [0, -2]], [[1, .2], [-.4, 1]],
                  [[1, .5], [.2, 1], [1, -1]],
                  [[.1, 0], [0, .2], [.1, -.1]])
    weights = [ct.tf([2, 3], [1, 4]), ct.tf([.5, 2], [1, 3]),
               ct.ss([], [], [], [[1, .2, -.3], [.4, 2, .1], [-.2, .1, .8]])]
    points = 1j*np.array([0, .3, 2, 13])
    g = state_space_reference(*model_matrices(plant), points)
    # Each singleton, omission in combinations, and all weights distinguish
    # channel selection; the rectangular plant separates input/output sizes.
    for selection in [(0,), (1,), (2,), (0, 1), (0, 2), (1, 2), (0, 1, 2)]:
        supplied = [w if i in selection else None for i, w in enumerate(weights)]
        if selection == (2,):
            supplied[2] = ct.tf([1.3], [1])
        augmented = ct.augw(plant, *supplied)
        actual = state_space_reference(*model_matrices(augmented), points)
        expected = []
        for j, point in enumerate(points):
            blocks = []
            for i in selection:
                if i == 0:
                    w = (2*point+3)/(point+4)*np.eye(3)
                    blocks.append(np.hstack([w, -w @ g[:, :, j]]))
                elif i == 1:
                    w = (.5*point+2)/(point+3)*np.eye(2)
                    blocks.append(np.hstack([np.zeros((2, 3)), w]))
                else:
                    w = np.array([[1, .2, -.3], [.4, 2, .1], [-.2, .1, .8]])
                    if selection == (2,):
                        w = 1.3*np.eye(3)
                    blocks.append(np.hstack([np.zeros((3, 3)), w @ g[:, :, j]]))
            blocks.append(np.hstack([np.eye(3), -g[:, :, j]]))
            expected.append(np.vstack(blocks))
        assert_allclose(actual, np.stack(expected, axis=-1), rtol=1e-8, atol=1e-9)
    with pytest.raises(ValueError):
        ct.augw(plant)
    for index in range(3):
        bad = [None]*3
        bad[index] = ct.ss([], [], [], np.ones((2, 4)))
        with pytest.raises(ValueError):
            ct.augw(plant, *bad)


def test_mixed_sensitivity_weighted_optimum():
    plant = ct.ss(ct.tf([1, 2], [1, 1]))
    # W2=b*G makes weighted effort b*T. For every frequency S+T=1,
    # so Cauchy-Schwarz gives gamma >= a*sqrt(b²+c²)/sqrt(a²+b²+c²).
    # A stable proper inverse of G attains the bound with constant S and T.
    for a, b, c in [(2., 1., 0.), (1., 0., 3.), (1.5, .7, 2.)]:
        w1 = ct.tf([a], [1])
        w2 = b*plant if b else None
        w3 = ct.tf([c], [1]) if c else None
        controller, returned, info = ct.mixsyn(plant, w1, w2, w3)
        # Independent original-plant negative-feedback closure for stability.
        negative = ct.ss(controller.A, controller.B, -controller.C, -controller.D)
        physical = ct.ss(plant.A, np.hstack([plant.B, plant.B]),
                         np.vstack([plant.C, plant.C]),
                         np.block([[plant.D, plant.D], [plant.D, plant.D]]))
        assert_stable_dynamics(close_generalized(physical, negative))
        points = 1j*np.r_[0, np.logspace(-5, 5, 160)]
        g = state_space_reference(*model_matrices(plant), points)[0, 0]
        k = state_space_reference(*model_matrices(controller), points)[0, 0]
        sensitivity = 1/(1+g*k)
        tracking = g*k*sensitivity
        expected = [a*sensitivity]
        if b:
            expected.append(b*tracking)
        if c:
            expected.append(c*tracking)
        assert_allclose(state_space_reference(*model_matrices(returned), points),
                        np.array(expected)[:, None, :], rtol=1e-6, atol=1e-7)
        assert_stable_dynamics(model_matrices(returned))
        optimum = a*np.sqrt(b*b+c*c)/np.sqrt(a*a+b*b+c*c)
        assert_allclose(info[0], optimum, rtol=3e-4)
        assert_allclose(sampled_peak(model_matrices(returned)), optimum, rtol=3e-4)
    with pytest.raises(ValueError):
        ct.mixsyn(plant)
