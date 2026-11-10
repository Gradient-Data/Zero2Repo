# feature: F15
"""Independent feedback equations and observable performance measurements."""
import numpy as np
from scipy.linalg import solve_continuous_lyapunov
from F01_helpers import state_space_reference


def close_generalized(plant, controller, nmeas=1, ncon=1):
    """Eliminate u = K y, including both direct terms, by linear algebra."""
    a, b, c, d = (np.asarray(getattr(plant, key)) for key in ('A', 'B', 'C', 'D'))
    ak, bk, ck, dk = (np.asarray(getattr(controller, key)) for key in ('A', 'B', 'C', 'D'))
    b1, b2 = b[:, :-ncon], b[:, -ncon:]
    c1, c2 = c[:-nmeas], c[-nmeas:]
    d11, d12 = d[:-nmeas, :-ncon], d[:-nmeas, -ncon:]
    d21, d22 = d[-nmeas:, :-ncon], d[-nmeas:, -ncon:]
    ux = np.linalg.solve(np.eye(ncon) - dk @ d22, dk @ c2)
    uk = np.linalg.solve(np.eye(ncon) - dk @ d22, ck)
    uw = np.linalg.solve(np.eye(ncon) - dk @ d22, dk @ d21)
    return (np.block([[a + b2 @ ux, b2 @ uk],
                      [bk @ (c2 + d22 @ ux), ak + bk @ d22 @ uk]]),
            np.vstack([b1 + b2 @ uw, bk @ (d21 + d22 @ uw)]),
            np.hstack([c1 + d12 @ ux, d12 @ uk]), d11 + d12 @ uw)


def assert_stable_dynamics(matrices):
    assert np.all(np.linalg.eigvals(matrices[0]).real < 0)


def impulse_energy(matrices):
    a, b, c, d = matrices
    assert_stable_dynamics(matrices)
    assert np.linalg.norm(d) < 1e-8
    gramian = solve_continuous_lyapunov(a, -b @ b.T)
    return float(np.trace(c @ gramian @ c.T))


def sampled_peak(matrices):
    """Include DC and the infinite-frequency limit, plus a broad log grid."""
    responses = state_space_reference(*matrices, 1j*np.r_[0, np.logspace(-7, 9, 2400)])
    finite = np.linalg.svd(responses.transpose(2, 0, 1), compute_uv=False)[:, 0]
    return max(finite.max(), np.linalg.norm(matrices[3], 2))


def model_matrices(model):
    return tuple(np.asarray(getattr(model, name)) for name in ('A', 'B', 'C', 'D'))
