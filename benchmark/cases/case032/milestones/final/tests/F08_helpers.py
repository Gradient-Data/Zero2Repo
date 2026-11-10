# feature: F08
"""Independent finite-assignment and finite-state probability references."""
from itertools import product
import numpy as np


def finite_assignment_table(support_sizes, probability):
    """Return all finite assignments and their unnormalized joint masses."""
    assignments = np.asarray(list(product(*(range(n) for n in support_sizes))), dtype=int)
    masses = np.asarray([probability(tuple(row)) for row in assignments], dtype=float)
    assert np.isfinite(masses).all() and (masses >= 0).all() and masses.sum() > 0
    return assignments, masses


def finite_state_table(transition, emission, observations, initial=0):
    """Enumerate paths using caller-supplied transition and observation laws."""
    transition, emission = np.asarray(transition), np.asarray(emission)
    def probability(path):
        mass, previous = 1., initial
        for state, observed in zip(path, observations):
            mass *= transition[previous, state] * emission[state, observed]
            previous = state
        return mass
    return finite_assignment_table([len(transition)] * len(observations), probability)
