# feature: F19
"""Real causal workloads and deterministic integration of public fitted laws."""
import numpy as np
import torch
from scipy import stats
from numpy.polynomial.hermite import hermgauss
from velnora.contrib.cevae import CEVAE
from _helpers import invoke
from F01_helpers import assert_close


def causal_cohort(n=96):
    """Sample an observed cohort from a heterogeneous treatment-response law."""
    x = torch.randn(n, 2) * torch.tensor([1.3, .8]) + torch.tensor([.7, -.4])
    t = torch.distributions.Bernoulli(logits=.6*x[:, 0]).sample()
    y = -1 + 1.5*x[:, 0] + t*(2 + .7*x[:, 1]) + .3*torch.randn(n)
    return x, t, y


def causal_fit(epochs=70):
    x, t, y = causal_cohort()
    causal = CEVAE(2, 'normal', latent_dim=1, hidden_dim=12, num_layers=2,
                   num_samples=64)
    losses = invoke(causal.fit, x, t, y, kwargs=dict(num_epochs=epochs,
        batch_size=32, learning_rate=.015, learning_rate_decay=1.,
        weight_decay=0., log_every=0), timeout=120).value
    return causal, (x, t, y), losses


def causal_inputs(causal, query):
    """Use the fitted public covariate adapter; do not fix its transform."""
    return invoke(causal.whiten, query).value


def causal_law_score(law, value, family, vector=False):
    """Compare published probability parameters with independent SciPy laws."""
    base = law.base_dist if vector else law
    array = lambda v: torch.as_tensor(v).detach().cpu().numpy()
    v = array(value)
    if family == 'bernoulli':
        expected = stats.bernoulli.logpmf(v, array(base.probs))
        mean = array(base.probs)
    elif family == 'exponential':
        expected = stats.expon.logpdf(v, scale=1/array(base.rate))
        mean = 1/array(base.rate)
    elif family == 'studentt':
        expected = stats.t.logpdf(v, array(base.df), array(base.loc), array(base.scale))
        mean = stats.t.mean(array(base.df), array(base.loc), array(base.scale))
    else:
        reference = {'normal': stats.norm, 'laplace': stats.laplace}[family]
        expected = reference.logpdf(v, array(base.loc), array(base.scale))
        mean = array(base.loc)
    if vector:
        expected = expected.sum(-1)
    assert_close(law.log_prob(value), expected)
    assert_close(law.mean, mean)
    return law.log_prob(value)


@torch.no_grad()
def integrated_effect(causal, training, query, order=40, sample_count=None):
    """Integrate q(t,y,z|x) and intervention means, without calling ite.

    Binary treatment is summed exactly; independent Gaussian quadrature handles
    approximate outcomes and confounders. This workload uses one latent normal
    coordinate, so no assumption on the learned network architecture is needed.
    Return its mean and between/within conditional variances. The original
    samples approximate treatment and outcome once per call, then averages
    confounder draws conditional on them; allow that hierarchical estimator.
    """
    x = causal_inputs(causal, query)
    nodes, weights = hermgauss(order)
    nodes = torch.as_tensor(nodes)*2**.5
    weights = torch.as_tensor(weights/np.sqrt(np.pi))
    probability = causal.guide.t_dist(x).probs
    first, second = torch.zeros(len(x)), torch.zeros(len(x))
    outer_second = torch.zeros(len(x))
    conditional_moments = []
    for treatment in (0., 1.):
        t = torch.full((len(x),), treatment)
        outcome = causal.guide.y_dist(t, x)
        y = outcome.loc + outcome.scale*nodes[:, None]
        posterior = causal.guide.z_dist(y, t.expand_as(y),
                                         x.expand(order, *x.shape)).base_dist
        z = posterior.loc[:, None] + posterior.scale[:, None]*nodes[None, :, None, None]
        contrast = causal.model.y_dist(torch.ones(()), z).mean - causal.model.y_dist(torch.zeros(()), z).mean
        joint_weight = weights[:, None, None]*weights[None, :, None]
        treatment_weight = probability if treatment else 1-probability
        first += treatment_weight*(joint_weight*contrast).sum((0, 1))
        second += treatment_weight*(joint_weight*contrast.square()).sum((0, 1))
        conditional_mean = (weights[None, :, None]*contrast).sum(1)
        outer_second += treatment_weight*(weights[:, None]*conditional_mean.square()).sum(0)
        if sample_count is not None:
            moments = [(weights[None, :, None]*contrast.pow(power)).sum(1)
                       for power in range(1, 5)]
            conditional_moments.append((treatment_weight*weights[:, None], moments))
    between = (outer_second-first.square()).clamp(min=0)
    within = (second-outer_second).clamp(min=0)
    if sample_count is not None:
        fourth = torch.zeros(len(x))
        n = sample_count
        for weight, (mean, raw2, raw3, raw4) in conditional_moments:
            offset = mean-first
            var = (raw2-mean.square()).clamp(min=0)
            central3 = raw3-3*mean*raw2+2*mean.pow(3)
            central4 = raw4-4*mean*raw3+6*mean.square()*raw2-3*mean.pow(4)
            moment = (offset.pow(4)+6*offset.square()*var/n+4*offset*central3/n**2
                      +(central4+3*(n-1)*var.square())/n**3)
            fourth += (weight*moment).sum(0)
        return first, (between, within), fourth
    return first, (between, within)


def conditional_snapshot(causal, training, query):
    """Read learned conditional distributions, including posterior uncertainty."""
    x = causal_inputs(causal, query)
    z = torch.linspace(-1.4, 1.7, len(x))[:, None]
    result = [causal.guide.t_dist(x).probs, causal.model.t_dist(z).probs]
    for t in (torch.zeros(len(x)), torch.ones(len(x))):
        for law in (causal.model.y_dist(t, z), causal.guide.y_dist(t, x),
                    causal.guide.z_dist(torch.linspace(-2., 3., len(x)), t, x).base_dist):
            result.extend([law.loc, law.scale])
    law = causal.model.x_dist(z).base_dist
    result.extend([law.loc, law.scale])
    return [value.detach().clone() for value in result]
