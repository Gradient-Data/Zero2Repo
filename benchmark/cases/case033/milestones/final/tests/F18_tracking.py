# feature: F18
"""Tracking and association acceptance checks through public library entries."""
import numpy as np
import pytest
from scipy.stats import multivariate_normal
import torch
from velnora.contrib.tracking.dynamic_models import NcpContinuous, NcpDiscrete, NcvContinuous, NcvDiscrete
from velnora.contrib.tracking.extended_kalman_filter import EKFState
from velnora.contrib.tracking.measurements import PositionMeasurement
from velnora.contrib.tracking.assignment import MarginalAssignment, MarginalAssignmentPersistent, MarginalAssignmentSparse
from _helpers import isolated_state, invoke
from F01_helpers import assert_close
from F18_helpers import association_law, check_association, check_probabilities


def test_f18_t01():
    with isolated_state(dtype=torch.float64, device='cpu'):
        for model_type in (NcpContinuous, NcpDiscrete, NcvContinuous, NcvDiscrete):
            position_only = model_type in (NcpContinuous, NcpDiscrete)
            size = 2 if position_only else 4
            mean = np.array([.7, -1.2, 1.1, -.6])[:size]
            lower = np.array([[1., 0., 0., 0.], [.2, .8, 0., 0.],
                              [.4, -.1, 1.2, 0.], [-.3, .2, .1, .9]])[:size, :size]
            covariance = lower @ lower.T
            for noise, dt in ((.3, .4), (1.1, 1.7)):
                state = EKFState(model_type(size, noise), torch.tensor(mean), torch.tensor(covariance), time=2.)
                transition = np.eye(size)
                if position_only:
                    added = noise * dt**2 * np.eye(size)
                else:
                    transition[:2, 2:] = dt * np.eye(2)
                    divisor = 3 if model_type is NcvContinuous else 4
                    added = noise * np.kron([[dt**4/divisor, dt**3/2],
                                             [dt**3/2, dt**2]], np.eye(2))
                prediction = invoke(state.predict, kwargs={'dt': dt}).value
                assert_close(prediction.mean, transition @ mean)
                assert_close(prediction.cov, transition @ covariance @ transition.T + added)
                assert prediction.time == 2. + dt


def test_f18_t02():
    with isolated_state(dtype=torch.float64, device='cpu'):
        for model_type in (NcpContinuous, NcvDiscrete):
            size = 2 if model_type is NcpContinuous else 4
            lower = np.array([[1., 0., 0., 0.], [.3, .8, 0., 0.],
                              [.6, -.2, 1., 0.], [.1, .5, .2, .7]])[:size, :size]
            state = EKFState(model_type(size, .4), torch.tensor([.4, -.7, 1.2, -.3][:size]),
                             torch.tensor(lower @ lower.T), time=1.).predict(dt=.6)
            m, p = state.mean.detach().numpy(), state.cov.detach().numpy()
            for r in (np.array([[.6, .15], [.15, .9]]), np.array([[1.8, -.2], [-.2, .5]])):
                z = np.array([2., -.1])
                measurement = PositionMeasurement(torch.tensor(z), torch.tensor(r), time=1.6)
                residual, innovation_cov = invoke(state.innovation, measurement).value
                s = p[:2, :2] + r
                assert_close(residual, z-m[:2])
                assert_close(innovation_cov, s)
                assert_close(invoke(state.log_likelihood_of_update, measurement).value,
                             multivariate_normal.logpdf(z, m[:2], s))
                updated, (dz, actual_s) = invoke(state.update, measurement).value
                gain = np.linalg.solve(s, p[:2, :]).T
                assert_close(updated.mean, m + gain @ (z-m[:2]))
                assert_close(updated.cov, p - gain @ p[:2, :])
                assert updated.time == state.time
                assert_close(dz, z-m[:2])
                assert_close(actual_s, s)
            wrong_time = PositionMeasurement(torch.tensor(z), torch.tensor(r), time=2.)
            for entry in (state.innovation, state.log_likelihood_of_update, state.update):
                with pytest.raises(AssertionError):
                    invoke(entry, wrong_time)


def test_f18_t03():
    with isolated_state(dtype=torch.float64, device='cpu'):
        model = NcpContinuous(2, .3)
        mean, cov = torch.tensor([.4, -.3]), torch.eye(2)
        frame_state = invoke(EKFState, model, mean, cov, kwargs={'frame_num': 4}).value
        assert frame_state.frame_num == 4
        assert_close(frame_state.mean, mean.numpy())
        with pytest.raises(ValueError):
            invoke(EKFState, model, mean, cov)
        state = EKFState(model, mean, cov, time=1.)
        for kwargs in ({'dt': .5}, {'destination_time': 1.5}):
            predicted = invoke(state.predict, kwargs=kwargs).value
            assert predicted.time == 1.5
            assert_close(predicted.mean, mean.numpy())
            assert_close(predicted.cov, cov.numpy() + .3*.5**2*np.eye(2))
        for kwargs in ({}, {'dt': .5, 'destination_time': 1.5}):
            with pytest.raises(AssertionError):
                invoke(state.predict, kwargs=kwargs)


def test_f18_t04():
    with isolated_state(dtype=torch.float64, device='cpu'):
        for existence, factors in (([-.8, .5], [[1.4, -.6], [.9, .3], [-.5, 1.1]]),
                                    ([.7], [[1.2], [.8]])):
            result = invoke(MarginalAssignment, torch.tensor(existence), torch.tensor(factors)).value
            check_association(result, association_law(existence, factors))


def test_f18_t05():
    with isolated_state(dtype=torch.float64, device='cpu'):
        existence = [-.7, .4]
        factors = np.array([[[1.4, -.4], [.8, .6]], [[-.8, 1.3], [.2, -.5]]])
        for values in (factors, factors + np.array([[[.3, -.2]], [[-.5, .4]]])):
            result = invoke(MarginalAssignmentPersistent, torch.tensor(existence), torch.tensor(values)).value
            check_association(result, association_law(existence, values, persistent=True))


def test_f18_t06():
    with isolated_state(dtype=torch.float64, device='cpu'):
        existence = torch.tensor([-.6, .5, -.2])
        edges = torch.tensor([[0, 1, 1, 2], [0, 0, 1, 1]])
        result = invoke(MarginalAssignmentSparse, 3, 4, edges, existence,
                        torch.tensor([1.2, -.4, .8, .5]), 12).value
        check_probabilities(result, 3, (4,))
        probabilities = result.assign_dist.probs
        allowed = torch.zeros(4, 3, dtype=torch.bool)
        allowed[edges[0], edges[1]] = True
        assert_close(probabilities[:, :3][~allowed], np.zeros(int((~allowed).sum())))
        assert bool((probabilities[:, :3][allowed] > 0).all())
        assert bool((probabilities[:, -1] > 0).all())
        assert_close(probabilities[3], [0., 0., 0., 1.])
        # An isolated object's posterior retains its supplied existence law.
        assert_close(result.exists_dist.probs[2], 1/(1+np.exp(.2)))


def test_f18_t07():
    # Acyclic bipartite graphs reach the public finite coverage guarantee.
    with isolated_state(dtype=torch.float64, device='cpu'):
        existence = torch.tensor([-.6, .4])
        factors = torch.tensor([[1.2, -.5], [.3, .8], [-.9, .2]])
        edges = torch.tensor([[0, 0, 1, 1, 2, 2], [0, 1, 0, 1, 0, 1]])
        for effort in (1, 7):
            dense = invoke(MarginalAssignment, existence, factors, kwargs={'bp_iters': effort}).value
            sparse = invoke(MarginalAssignmentSparse, 2, 3, edges, existence,
                            factors[edges[0], edges[1]], effort).value
            persistent = invoke(MarginalAssignmentPersistent, existence,
                                torch.stack((factors, factors.flip(0))),
                                kwargs={'bp_iters': effort, 'bp_momentum': .3}).value
            check_probabilities(dense, 2, (3,))
            check_probabilities(sparse, 2, (3,))
            check_probabilities(persistent, 2, (2, 3))

        # Different path lengths, branches and a disconnected object exercise
        # whole-graph dependence rather than one local update. No new cases
        # are collected; extend this existing approximation observation.
        for mask in (np.array([[1, 1, 0], [0, 1, 1], [0, 0, 1]], dtype=bool),
                     np.array([[1, 0, 0], [1, 1, 0], [1, 0, 0]], dtype=bool)):
            existence = torch.tensor([-.7, .5, -1.1])
            factors = torch.tensor([[1.2, -.6, .3], [-.4, .9, -.8], [.7, -.3, 1.4]])
            edges = torch.tensor(np.array(np.nonzero(mask)))
            effort = sum(mask.shape)
            expected = association_law(existence, factors, feasible=mask)
            # Dense missing edges are represented by negative infinity; the
            # finite feasible factors, not impossible edges, define the law.
            dense_factors = factors.masked_fill(~torch.tensor(mask), -float('inf'))
            for count in (effort, effort+2):
                dense = invoke(MarginalAssignment, existence, dense_factors,
                               kwargs={'bp_iters': count}).value
                sparse = invoke(MarginalAssignmentSparse, 3, 3, edges, existence,
                                factors[edges[0], edges[1]], count).value
                for result in (dense, sparse):
                    np.testing.assert_allclose(result.exists_dist.probs.numpy(), expected[0],
                                               rtol=0., atol=1e-6)
                    np.testing.assert_allclose(result.assign_dist.probs.numpy(), expected[1],
                                               rtol=0., atol=1e-6)
