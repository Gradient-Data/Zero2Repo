# feature: F05
"""Independent finite-space probability oracle for repeated latent models."""
from itertools import product
import math


def finite_state_evidence(initial_history, state_count, observations, transition, emission):
    """Sum joint probabilities over all finite latent paths, without Velnora."""
    terms = []
    for path in product(range(state_count), repeat=len(observations)):
        history = tuple(initial_history)
        mass = 1.0
        for state, observation in zip(path, observations):
            mass *= transition(history, state) * emission(state, observation)
            history = history[1:] + (state,)
        terms.append(mass)
    return math.fsum(terms)
