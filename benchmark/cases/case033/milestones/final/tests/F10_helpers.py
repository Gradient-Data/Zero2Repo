# feature: F10
"""Finite probability workloads for public enumeration entries."""
from itertools import product
import numpy as np
import torch
import velnora
from velnora.ops.indexing import Vindex


def empty_guide(*args, **kwargs):
    pass


def pair_problem(observation=1, size=None):
    prior = np.array([.5, .5])
    transition = np.array([[.5, .5], [.5, .5]])
    likelihood = np.array([[.60, .64], [.74, .02]])
    masses = prior[:, None]*transition*(likelihood if observation else 1-likelihood)

    def choices():
        x = velnora.sample('x', velnora.distributions.Categorical(torch.tensor(prior)), infer={'enumerate': 'parallel'})
        y = velnora.sample('y', velnora.distributions.Categorical(Vindex(torch.tensor(transition))[x, :]), infer={'enumerate': 'parallel'})
        velnora.sample('obs', velnora.distributions.Bernoulli(Vindex(torch.tensor(likelihood))[x, y]), obs=torch.tensor(float(observation)))
        return x, y

    def model():
        if size is None:
            return choices()
        with velnora.plate('population', size, dim=-1):
            return choices()
    return model, masses/masses.sum(), masses.sum()


def chain_problem(observations, size=None):
    transition = np.array([[.92, .08], [.17, .83]])
    emission = np.array([.12, .88])
    paths = list(product(range(2), repeat=len(observations)))
    masses = []
    for path in paths:
        previous, mass = 0, 1.
        for state, obs in zip(path, observations):
            mass *= transition[previous, state]*(emission[state] if obs else 1-emission[state])
            previous = state
        masses.append(mass)

    def sequence():
        previous = torch.tensor(0)
        result = []
        for t in velnora.markov(range(len(observations)), history=1):
            state = velnora.sample('state_{}'.format(t), velnora.distributions.Categorical(Vindex(torch.tensor(transition))[previous, :]), infer={'enumerate': 'parallel'})
            velnora.sample('obs_{}'.format(t), velnora.distributions.Bernoulli(torch.tensor(emission)[state]), obs=torch.tensor(float(observations[t])))
            result.append(state)
            previous = state
        return tuple(result)

    def model():
        if size is None:
            return sequence()
        with velnora.plate('population', size, dim=-1):
            return sequence()
    return model, paths, np.array(masses), transition, emission
