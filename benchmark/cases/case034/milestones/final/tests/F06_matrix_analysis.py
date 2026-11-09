# feature: F06
"""Acceptance checks for state-space matrix analysis and equations."""

import velunex as ct
import numpy as np
import pytest
from numpy.testing import assert_allclose
from scipy.integrate import quad_vec
from scipy.linalg import expm
from F06_helpers import assert_matrix_balance, assert_riccati_result


def test_horizon_state_maps():
    a = np.array([[0., 1., 0.], [0., 0., 1.], [-2., -3., -4.]])
    b = np.array([[1., 0.], [0., 2.], [1., -1.]])
    c = np.array([[1., 2., 0.], [0., -1., 3.]])
    for horizon in (None, 1, 2, 7):
        count = 3 if horizon is None else min(horizon, 3)
        reach = np.hstack([np.linalg.matrix_power(a, k) @ b for k in range(count)])
        observe = np.vstack([c @ np.linalg.matrix_power(a, k) for k in range(count)])
        options = {} if horizon is None else {'t': horizon}
        assert_allclose(ct.ctrb(a, b, **options), reach)
        assert_allclose(ct.obsv(a, c, **options), observe)
    assert np.linalg.matrix_rank(ct.ctrb(a, b)) == 3
    assert np.linalg.matrix_rank(ct.obsv(a, c)) == 3
    for entry, matrix in ((ct.ctrb, np.ones((2, 1))),
                           (ct.obsv, np.ones((1, 2)))):
        with pytest.raises(ct.VelunexDimension):
            entry(a, matrix)


def test_energy_gramians_and_factors():
    b = np.array([[1., 0.], [.5, 2.]])
    c = np.array([[2., -.5], [0., 1.]])
    for discrete, a in ((False, np.array([[-1., .6], [0., -2.]])),
                        (True, np.array([[.3, .2], [0., .5]]))):
        sys = ct.ss(a, b, c, np.zeros((2, 2)), .2 if discrete else 0)
        if discrete:
            # The remaining geometric tail after 100 steps is below roundoff.
            powers = [np.linalg.matrix_power(a, k) for k in range(100)]
            wc = sum(p @ b @ b.T @ p.T for p in powers)
            wo = sum(p.T @ c.T @ c @ p for p in powers)
        else:
            wc, _ = quad_vec(lambda t: expm(a*t) @ b @ b.T @ expm(a.T*t), 0, np.inf)
            wo, _ = quad_vec(lambda t: expm(a.T*t) @ c.T @ c @ expm(a*t), 0, np.inf)
        for mode, expected in (('c', wc), ('o', wo), ('cf', wc), ('of', wo)):
            result = ct.gram(sys, mode)
            actual = result.T @ result if mode.endswith('f') else result
            assert_allclose(actual, expected, rtol=1e-8, atol=1e-9)
            unstable = ct.ss(np.diag([1.2, -.2]), b, c, np.zeros((2, 2)), sys.dt)
            with pytest.raises(ValueError):
                ct.gram(unstable, mode)


def test_lyapunov_and_sylvester_equations():
    q = np.array([[2., .4], [.4, 3.]])
    e = np.array([[1.3, .2], [0., .9]])
    forcing = np.array([[1., 2., -1.], [3., -.5, 2.]])
    for discrete, entry, a, right in (
        (False, ct.lyap, np.array([[-1., .7], [-.2, -2.]]),
         np.array([[-3., .2, 0.], [0., -1., .5], [.1, 0., -2.]])),
        (True, ct.dlyap, np.array([[.2, .3], [-.1, .4]]),
         np.array([[.3, .2, 0.], [0., .1, .4], [.1, 0., .2]]))):
        for descriptor in (None, e):
            x = entry(a, q, E=descriptor)
            assert x.shape == q.shape
            d = np.eye(2) if descriptor is None else descriptor
            if discrete:
                assert_matrix_balance(a @ x @ a.T, -d @ x @ d.T, q)
            else:
                assert_matrix_balance(a @ x @ d.T, d @ x @ a.T, q)
        x = entry(a, right, forcing)
        assert x.shape == forcing.shape
        if discrete:
            assert_matrix_balance(a @ x @ right.T, -x, forcing)
        else:
            assert_matrix_balance(a @ x, x @ right, forcing)
        for args, kwargs, error in (
            ((a, np.eye(3)), {}, ct.VelunexDimension),
            ((a, np.array([[1., 1.], [0., 1.]])), {}, ct.VelunexArgument),
            ((a, right, np.ones((3, 2))), {}, ct.VelunexDimension),
            ((a, q), {'E': np.eye(3)}, ct.VelunexDimension),
            ((a, q, q), {'E': e}, ct.VelunexArgument)):
            with pytest.raises(error):
                entry(*args, **kwargs)


def test_stabilizing_riccati_equations():
    b = np.array([[1., .2], [.3, 1.]])
    q = np.array([[2., .3], [.3, 1.]])
    r = np.array([[1.5, .2], [.2, 2.]])
    s = np.array([[.1, -.05], [.03, .2]])
    e = np.array([[1.2, .1], [0., .9]])
    for discrete, entry, a in (
        (False, ct.care, np.array([[.4, 1.], [-.3, -.2]])),
        (True, ct.dare, np.array([[1.1, .3], [-.2, .8]]))):
        cases = [({}, r, np.zeros((2, 2)), np.eye(2)),
                 ({'S': s}, r, s, np.eye(2)),
                 ({'E': e}, r, np.zeros((2, 2)), e),
                 ({'S': s, 'E': e}, r, s, e)]
        if not discrete:
            cases.append(({}, None, np.zeros((2, 2)), np.eye(2)))
        for options, weight, cross, descriptor in cases:
            result = entry(a, b, q, **options) if weight is None else entry(a, b, q, weight, **options)
            assert_riccati_result(result, a, b, q,
                                  np.eye(2) if weight is None else weight,
                                  cross, descriptor, discrete=discrete)


def test_nonstabilizing_riccati_and_failures():
    for discrete, entry in ((False, ct.care), (True, ct.dare)):
        a, b, q, r = (np.array([[v]]) for v in (.7, 1.2, 2., 1.5))
        result = entry(a, b, q, r, stabilizing=False)
        assert_riccati_result(result, a, b, q, r, np.zeros((1, 1)),
                              np.eye(1), discrete=discrete, stabilizing=False)
        base = [np.diag([.4, .8]), np.eye(2), np.eye(2), np.eye(2)]
        for index, value, error in (
            (0, np.ones((2, 3)), ct.VelunexDimension),
            (1, np.ones((3, 2)), ct.VelunexDimension),
            (2, np.eye(3), ct.VelunexDimension),
            (3, np.eye(3), ct.VelunexDimension),
            (2, np.array([[1., .3], [0., 1.]]), ct.VelunexArgument),
            (3, np.array([[1., .3], [0., 1.]]), ct.VelunexArgument)):
            args = base.copy()
            args[index] = value
            with pytest.raises(error):
                entry(*args)
        for options in ({'S': np.ones((3, 2))}, {'E': np.eye(3)}):
            with pytest.raises(ct.VelunexDimension):
                entry(*base, **options)
        # An uncontrollable unstable scalar cannot have a stabilizing solution.
        with pytest.raises(np.linalg.LinAlgError):
            entry([[1.2]], [[0.]], [[1.]], [[1.]], method='scipy')
