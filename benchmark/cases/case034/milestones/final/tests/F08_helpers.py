# feature: F08
"""Frequency-domain observations with phase-branch freedom."""

import numpy as np
from numpy.testing import assert_allclose


def assert_frequency_data(response, omega, expected):
    assert_allclose(response.omega, omega)
    assert_allclose(response.frdata, expected, rtol=1e-7, atol=1e-9)
    assert_allclose(response.magnitude, abs(expected), rtol=1e-7, atol=1e-9)
    assert_allclose(np.exp(1j*response.phase), expected/abs(expected), atol=1e-8)


def assert_phase_coordinates(actual, expected, degrees=False):
    angle = np.asarray(actual) * (np.pi/180 if degrees else 1)
    assert_allclose(np.exp(1j*angle), expected/abs(expected), atol=1e-8)
