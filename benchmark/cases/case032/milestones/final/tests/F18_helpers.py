# feature: F18
"""Stochastic-support workloads and independent Gaussian evidence oracles."""
from F01_helpers import jax, jnp, np, dist, stats, close, read_array, call_public
from F10_helpers import ag, fitted_normal_cdf
from F12_helpers import check_law
import velnora
from velnora import optim
from velnora.contrib.stochastic_support.dcc import DCC
from velnora.contrib.stochastic_support.sdvi import SDVI
from velnora.infer import Trace_ELBO
from scipy.special import softmax


def branching_normal_model(y=1.4, varying=True):
    branch = velnora.sample('branch', dist.Bernoulli(.3), infer={'branching': True})
    if branch == 0:
        x = velnora.sample('left', dist.Normal(jnp.array([-1.]), 1.).to_event(1))
    else:
        x = velnora.sample('right', dist.Normal(jnp.array([2., -.8, .6] if varying else [2.]), 1.).to_event(1))
    velnora.sample('observation', dist.Normal(x[..., 0], 1.), obs=y)


def equal_dimension_model(y=1.4):
    return branching_normal_model(y, varying=False)


def path_oracle(path, y, varying=True):
    assert path in ('0', '1')
    if path == '0':
        name, prior, mass = 'left', np.array([-1.]), .7
    else:
        name, prior, mass = 'right', np.array([2., -.8, .6] if varying else [2.]), .3
    mean, variance = prior.copy(), np.ones(len(prior))
    mean[0], variance[0] = (prior[0]+y)/2, .5
    evidence = np.log(mass) + stats.norm.logpdf(y, prior[0], np.sqrt(2.))
    return name, mean, variance, evidence


def support_method(kind, *, model=branching_normal_model, cap=2, explore=128,
                   loss=None, steps=1800, samples=6000, guide_init=ag.AutoDiagonalNormal):
    common = dict(num_slp_samples=explore, max_slps=cap)
    if kind == 'dcc':
        return DCC(model, mcmc_kwargs=dict(num_warmup=400, num_samples=samples,
                   num_chains=1, progress_bar=False), **common)
    assert kind == 'sdvi'
    return SDVI(model, optim.Adam(.02), guide_init=guide_init,
                svi_num_steps=steps, combine_elbo_particles=16384,
                loss=Trace_ELBO(num_particles=16) if loss is None else loss, **common)


def run_support(method, seed, y=1.4):
    return call_public(method.run, jax.random.key(seed), y, timeout=600)


def normalized_weights(result, paths):
    assert set(result.slp_weights) == set(paths)
    weights = np.array([read_array(result.slp_weights[p]).item() for p in paths])
    assert np.isfinite(weights).all() and (weights >= 0).all()
    close(weights.sum(), 1.)
    return weights


def path_draws(result, kind, path, seed=712):
    if kind == 'dcc':
        return result.samples[path]
    guide, params = result.guides[path]
    assert params
    return call_public(guide.sample_posterior, jax.random.key(seed), params,
                       sample_shape=(8192,), timeout=240)


def check_path_posterior(result, kind, path, y, varying=True):
    name, mean, variance, _ = path_oracle(path, y, varying)
    draws = path_draws(result, kind, path)
    assert set(draws) == {name}
    x = read_array(draws[name])
    assert x.ndim == 2 and x.shape[1:] == mean.shape
    for i in range(len(mean)):
        if kind == 'dcc':
            check_law(x[:, i], stats.norm(mean[i], np.sqrt(variance[i])), cdf_tolerance=.07)
        else:
            fitted_normal_cdf(x[:, i], mean[i], np.sqrt(variance[i]))
    return x


def independent_guide_bound(guide, params, path, y):
    # This workload has one real-valued vector site, so the diagonal guide's
    # public latent Gaussian is already in model coordinates. Evaluate the
    # evidence bound as log evidence minus Gaussian KL, using NumPy/SciPy.
    posterior = call_public(guide.get_posterior, params)
    mean, variance = read_array(posterior.mean), read_array(posterior.variance)
    _, target_mean, target_var, log_evidence = path_oracle(path, y)
    assert mean.shape == target_mean.shape and variance.shape == target_var.shape
    assert np.isfinite(mean).all() and np.isfinite(variance).all() and (variance > 0).all()
    kl = .5*np.sum((variance + (mean-target_mean)**2)/target_var - 1
                    + np.log(target_var/variance))
    return log_evidence - kl
