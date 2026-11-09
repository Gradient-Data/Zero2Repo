# feature: F14
"""Acceptance of supplied feedback controllers and gain schedules."""
import velunex as ct
import numpy as np
import pytest
from numpy.testing import assert_allclose
from F14_helpers import check_feedback_history, check_cubic_pieces


def test_tracking_reference_and_selected_inputs():
    plant = ct.ss([[-1]], [[3, 2]], [[1]], [[0, 0]],
                  inputs=['disturbance', 'actuation'], outputs=['position'])
    ctrl, closed = ct.create_statefbk_iosystem(
        plant, np.array([[2.]]), control_indices=['actuation'])
    for desired, nominal, actual in [(1., .5, 3.), (-2., 1., -.5)]:
        assert_allclose(ctrl.output(0, [], [desired, nominal, actual]),
                        [nominal - 2*(actual-desired)])
    t = np.linspace(0, 2, 41)
    # Closed-loop inputs: desired state, desired actuation, unused plant input.
    check_feedback_history(closed, t, np.tile([[1], [.5], [.7]], (1, len(t))),
        lambda t, z: [-5*z[0]+7.1], lambda z: np.vstack([z[0], 2.5-2*z[0]]), [0])
    plant = ct.ss([[-1]], [[2]], [[1]], [[0]])
    ctrl, closed = ct.create_statefbk_iosystem(
        plant, np.array([[2.]]), feedfwd_gain=3., feedfwd_pattern='refgain')
    assert_allclose(ctrl.output(0, [], [1.2, -.4]), [4.4])
    check_feedback_history(closed, t, np.full((1, len(t)), 1.2),
        lambda t, z: [-5*z[0]+7.2], lambda z: np.vstack([z[0], 3.6-2*z[0]]), [0])


def test_integral_action_and_dimensions():
    for dt in (0, .2):
        plant = ct.ss([[-1 if dt == 0 else .7]], [[1]], [[1]], [[0]], dt=dt)
        for pattern in ('trajgen', 'refgain'):
            options = {} if pattern == 'trajgen' else dict(feedfwd_pattern=pattern, feedfwd_gain=3.)
            ctrl, closed = ct.create_statefbk_iosystem(
                plant, np.array([[2., .5]]), integral_action=np.array([[2.]]), **options)
            u = [1., .3, 4.] if pattern == 'trajgen' else [1., 4.]
            error = 6. if pattern == 'trajgen' else 7.
            assert_allclose(ctrl.dynamics(0, [1.5], u), [error + (1.5 if dt else 0)])
            assert_allclose(ctrl.output(0, [1.5], u), [-6.45 if pattern == 'trajgen' else -5.75])
            t = np.arange(21)*(.2 if dt else .05)
            ext = np.tile([[1.], [.3]] if pattern == 'trajgen' else [[1.]], (1, len(t)))
            def action(z):
                return (2.3 if pattern == 'trajgen' else 3.) - 2*z[0] - .5*z[1]
            def law(t, z):
                return [-z[0]+action(z), 2*z[0]-(2 if pattern == 'trajgen' else 1)]
            if dt == 0:
                check_feedback_history(closed, t, ext, law,
                    lambda z: np.vstack([z[0], action(z)]), [0, 0])
            else:
                z = np.zeros((2, len(t)))
                for j in range(len(t)-1):
                    z[:, j+1] = [.7*z[0, j]+action(z[:, j]),
                        z[1, j]+2*z[0, j]-(2 if pattern == 'trajgen' else 1)]
                response = ct.input_output_response(closed, t, ext, squeeze=False)
                assert_allclose(response.outputs, np.vstack([z[0], action(z)]), atol=1e-9)
    for gain, integral in [(np.ones((1, 1)), np.ones((1, 1))),
                           (np.ones((1, 2)), np.ones((1, 2)))]:
        with pytest.raises((ValueError, ct.VelunexArgument)):
            ct.create_statefbk_iosystem(plant, gain, integral_action=integral)


def test_supplied_estimator_and_state_dimensions():
    plant = ct.ss([[-1]], [[1]], [[1]], [[0]], inputs=['u'], outputs=['y'], name='plant')
    estimator = ct.ss([[-3]], [[1, 2]], [[1]], [[0, 0]],
                      inputs=['u', 'y'], outputs=['estimate'], name='observer')
    ctrl, closed = ct.create_statefbk_iosystem(plant, np.array([[2.]]), estimator=estimator)
    assert_allclose(ctrl.output(0, [], [1, .5, -.4]), [3.3])
    t = np.linspace(0, 2, 41)
    check_feedback_history(closed, t, np.tile([[1], [.5]], (1, len(t))),
        lambda t, z: [-z[0]+2.5-2*z[1], 2*z[0]-5*z[1]+2.5],
        lambda z: np.vstack([z[0], 2.5-2*z[1]]), [0, 0])
    full = ct.ss(-np.eye(2), np.ones((2, 1)), np.eye(2), np.zeros((2, 1)))
    partial = ct.ss(-np.eye(2), np.ones((2, 1)), [[1, 0]], [[0]])
    bad_estimator = ct.ss([[-1]], [[1, 1]], [[1]], [[0, 0]])
    for system, gain, options in [
            (partial, np.ones((1, 2)), {}),
            (full, np.ones((2, 2)), {}),
            (full, np.ones((1, 2)), {'state_indices': [0, 1, 2]}),
            (full, np.ones((1, 2)), {'estimator': bad_estimator})]:
        with pytest.raises((ValueError, ct.VelunexArgument)):
            ct.create_statefbk_iosystem(system, gain, **options)


def test_schedule_interpolation_and_dimensions():
    plant = ct.ss([[-1]], [[1]], [[1]], [[0]])
    knots = np.array([0., 1., 2., 4., 5.])
    gains = [np.array([[v]]) for v in [1., 3., 2., 6., 4.]]
    # Schedule on desired input: state error remains one, so u_d-u reads gain.
    for method in (None, 'linear', 'nearest', 'cubic'):
        options = {} if method is None else {'gainsched_method': method}
        ctrl, _ = ct.create_statefbk_iosystem(plant, (gains, knots), gainsched_indices=[1], **options)
        for q, gain in zip(knots, gains):
            assert_allclose(ctrl.output(0, [], [0, q, 1]), [q-gain[0, 0]], atol=1e-9)
        if method in (None, 'linear', 'nearest'):
            for q in (.2, 1.7, 3.4):
                expected = (gains[np.argmin(abs(knots-q))][0, 0] if method == 'nearest'
                            else np.interp(q, knots, [g[0, 0] for g in gains]))
                assert_allclose(ctrl.output(0, [], [0, q, 1]), [q-expected], atol=1e-9)
        else:
            check_cubic_pieces(ctrl, knots, lambda q: [0, q, 1])
    plant2 = ct.ss(-np.eye(2), np.eye(2), np.eye(2), np.zeros((2, 2)))
    points = np.array([[0., 0.], [2., 0.], [0., 2.]])
    gains2 = [np.array([[1+x, 2+y], [-1+2*y, 3-x]]) for x, y in points]
    for method in ('linear', 'nearest', 'cubic'):
        ctrl, _ = ct.create_statefbk_iosystem(plant2, (gains2, points),
            gainsched_indices=[1, 0], gainsched_method=method)
        queries = [*points, np.array([.3, .6])]
        for q in queries:
            xd = q[::-1]
            gain = (gains2[np.argmin(np.linalg.norm(points-q, axis=1))] if method == 'nearest'
                    else np.array([[1+q[0], 2+q[1]], [-1+2*q[1], 3-q[0]]]))
            assert_allclose(ctrl.output(0, [], np.r_[xd, [.4, -.2], xd+[1, -2]]),
                            np.array([.4, -.2])-gain @ [1, -2], atol=2e-6)
    for schedule, indices in [((gains[:3], [[0, 0], [1, 0], [0, 1]]), [0]),
            (([np.ones((1, 1)), np.ones((1, 2))], [0, 1]), [0])]:
        with pytest.raises((ValueError, ct.VelunexArgument)):
            ct.create_statefbk_iosystem(plant, schedule, gainsched_indices=indices)


def test_schedule_outside_region_nearest_extension():
    plant = ct.ss(-np.eye(2), [[1], [1]], np.eye(2), np.zeros((2, 1)))
    points = np.array([[0., 0.], [3., 0.], [0., 2.]])
    gains = [np.array([[1., 2.]]), np.array([[3., -1.]]), np.array([[-2., 4.]])]
    for method in ('linear', 'cubic'):
        ctrl, _ = ct.create_statefbk_iosystem(plant, (gains, points), gainsched_method=method)
        for q in (np.array([4., .2]), np.array([-.3, 3.]), np.array([-2., -1.])):
            gain = gains[np.argmin(np.linalg.norm(points-q, axis=1))]
            assert_allclose(ctrl.output(0, [], np.r_[q, .7, q+[2, -1]]),
                            [.7-(gain @ [2, -1])[0]], atol=1e-9)


def test_dynamic_signed_correction():
    plant = ct.ss([[-1]], [[1]], [[1]], [[0]])
    correction = ct.ss([[-2]], [[3]], [[-4]], [[-.5]])
    ctrl, closed = ct.create_statefbk_iosystem(plant, correction)
    # Zero initial memory avoids imposing a realization on the assembled model.
    t = np.linspace(0, 2, 41)
    response = ct.input_output_response(ctrl, t, np.tile([[1], [.3], [2]], (1, len(t))),
        squeeze=False, solve_ivp_kwargs={'rtol': 1e-9, 'atol': 1e-11})
    assert_allclose(response.outputs, [-.2-6*(1-np.exp(-2*t))], atol=2e-8)
    check_feedback_history(closed, t, np.tile([[1], [.3]], (1, len(t))),
        lambda t, z: [-1.5*z[0]-4*z[1]+.8, 3*z[0]-2*z[1]-3],
        lambda z: np.vstack([z[0], .8-.5*z[0]-4*z[1]]), [0, 0])
