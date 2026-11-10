# feature: F09
"""Analytically soluble variational workloads and independent energy oracle."""
import math
import numpy as np
import torch
import velnora
from scipy import stats


def normal_problem(size=1, parameters=None):
    def model():
        a = velnora.param('a', torch.tensor(-.3))
        if parameters is not None:
            parameters['a'] = a
        with velnora.plate('data', size):
            z = velnora.sample('z', velnora.distributions.Normal(a, 1.3))
            velnora.sample('obs', velnora.distributions.Normal(z, .7), obs=torch.tensor(1.2))
    def guide():
        m = velnora.param('m', torch.tensor(.4))
        s = velnora.param('s', torch.tensor(.8), constraint=velnora.distributions.constraints.positive)
        if parameters is not None:
            parameters.update(m=m, s=s)
        with velnora.plate('data', size):
            velnora.sample('z', velnora.distributions.Normal(m, s))
    return model, guide


def normal_objective(a, m, log_s):
    s2 = (2 * log_s).exp()
    return (math.log(1.3) - log_s - .5 + (s2 + (m-a)**2)/(2*1.3**2)
            + math.log(.7) + .5*math.log(2*math.pi)
            + (s2+(m-1.2)**2)/(2*.7**2))


def fit_svi(model, guide, objective, steps=400, lr=.035):
    from velnora.infer import SVI
    svi = SVI(model, guide, velnora.optim.Adam({'lr': lr}), objective)
    values = [svi.step() for _ in range(steps)]
    assert np.isfinite(values).all()
    return svi


def energy_oracle(samples, data, weights, beta, latent=None, prior_scale=0.):
    """Direct finite empirical functional, independent of product scoring."""
    samples = np.asarray(samples)
    data, weights = np.asarray(data), np.asarray(weights)
    first = np.mean(np.sum(weights*(samples-data)**2, axis=-1)**(beta/2))
    pairs = [np.sum(weights*(x-y)**2)**(beta/2)
             for i, x in enumerate(samples) for y in samples[:i]]
    answer = first - .5*np.mean(pairs)
    if prior_scale:
        answer -= prior_scale*stats.norm.logpdf(latent, -.2, 1.4).sum()
    return answer


class CubicNormal(velnora.distributions.TorchDistribution):
    """A genuine implicit law: cube of a shifted standard normal draw.

    Only its differentiable sampler is supplied, as permitted for implicit
    generative models; density requests deliberately retain NotImplementedError.
    """
    arg_constraints = {}
    support = velnora.distributions.constraints.real
    has_rsample = True

    def __init__(self, loc, validate_args=None):
        self.loc = torch.as_tensor(loc)
        super().__init__(self.loc.shape, torch.Size(), validate_args=validate_args)

    def expand(self, batch_shape, _instance=None):
        return CubicNormal(self.loc.expand(batch_shape), self._validate_args)

    def rsample(self, sample_shape=torch.Size()):
        noise = torch.randn(sample_shape + self.batch_shape, dtype=self.loc.dtype,
                            device=self.loc.device)
        return (self.loc + noise).pow(3)
