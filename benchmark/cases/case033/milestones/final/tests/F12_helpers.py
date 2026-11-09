# feature: F12
"""Caller-owned predictive workloads; no substitute product behavior."""
import torch
import velnora


def binary_prediction():
    z = velnora.sample('z', velnora.distributions.Bernoulli(.3))
    y = velnora.sample('y', velnora.distributions.Bernoulli(.15 + .7*z))
    score = velnora.deterministic('score', 3*z+y)
    return torch.stack((z, y, score), -1)


def binary_guide():
    return velnora.sample('z', velnora.distributions.Bernoulli(.65))


def weighted_prediction():
    z = velnora.sample('z', velnora.distributions.Bernoulli(.3))
    velnora.sample('y', velnora.distributions.Bernoulli(.1 + .8*z))


def weighted_evidence():
    z = velnora.sample('z', velnora.distributions.Bernoulli(.3))
    velnora.sample('evidence', velnora.distributions.Bernoulli(.2 + .6*z), obs=torch.tensor(1.))
