# feature: F09
"""Independent geometric checks and paired margin observations."""
import numpy as np
from numpy.testing import assert_allclose
from scipy.optimize import brentq, minimize_scalar


def assert_margin_pairs(actual, expected, atol=2e-5):
    """Compare paired margin/frequency sets without requiring enumeration order."""
    assert len(actual) == 6
    for i in range(3):
        values, frequencies = np.asarray(actual[i]), np.asarray(actual[i+3])
        want_values, want_frequencies = np.asarray(expected[i]), np.asarray(expected[i+3])
        assert values.shape == frequencies.shape == want_values.shape == want_frequencies.shape
        order, wanted = np.argsort(frequencies), np.argsort(want_frequencies)
        assert_allclose(frequencies[order], want_frequencies[wanted], atol=atol, rtol=2e-5)
        assert_allclose(values[order], want_values[wanted], atol=atol, rtol=2e-5)


def disk_geometry(alpha, skew):
    """Intersect the PRD's multiplicative disk with rays and the unit circle."""
    def radius(gain):
        return abs(2*(gain-1)/(alpha*((1-skew)+(1+skew)*gain)))
    low = brentq(lambda g: radius(g)-1, 0, 1)
    high = brentq(lambda g: radius(g)-1, 1, 100)
    phase = brentq(lambda angle: radius(np.exp(1j*angle))-1, 0, np.pi)
    return 20*np.log10(min(1/low, high)), np.degrees(phase)


def two_channel_scaled_gain(matrix):
    """Solve the independent one-dimensional diagonal-scaling problem."""
    def gain(log_ratio):
        scaling = np.diag([np.exp(log_ratio), 1.])
        return np.linalg.svd(scaling @ matrix @ np.linalg.inv(scaling), compute_uv=False)[0]
    optimum = minimize_scalar(gain, bounds=(-15, 15), method='bounded')
    assert optimum.success
    return optimum.fun
