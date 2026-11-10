# feature: F02
"""Caller-defined basis used to exercise the public extension protocol."""

import numpy as np
from velunex.flatsys import BasisFamily


class HarmonicFamily(BasisFamily):
    """A constant and two independently scaled harmonic functions."""

    def __init__(self):
        super().__init__(3)

    def eval_deriv(self, i, k, t, var=None):
        t = np.asarray(t)
        if i == 0:
            return np.ones_like(t) if k == 0 else np.zeros_like(t)
        if i == 1:
            return 2 ** k * np.sin(2 * t + k * np.pi / 2)
        if i == 2:
            return 3 ** k * np.cos(3 * t + k * np.pi / 2)
        raise IndexError('Basis index out of range')
