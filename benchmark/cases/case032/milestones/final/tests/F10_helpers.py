# feature: F10
"""Public guide workloads and independent Gaussian oracles."""
from F01_helpers import (jax, jnp, np, dist, close, read_array, call_public,
                         gaussian_samples, check_cdf_samples)
from scipy import stats
import velnora
from velnora import handlers as h, optim
from velnora.infer import SVI, Trace_ELBO
from velnora.infer import autoguide as ag

NORMALS = (ag.AutoNormal, ag.AutoDiagonalNormal, ag.AutoMultivariateNormal,
           ag.AutoLowRankMultivariateNormal, ag.AutoBatchedMultivariateNormal,
           ag.AutoBatchedLowRankMultivariateNormal)


def bind_guide(guide, *args, **kwargs):
    record = call_public(h.trace(h.seed(guide, 19)).get_trace, *args, **kwargs)
    params = {name: site['value'] for name, site in record.items() if site['type'] == 'param'}
    return params


def fit_guide(model, guide, steps=1800, *args):
    svi = SVI(model, guide, optim.Adam(.015), Trace_ELBO(num_particles=16))
    result = call_public(svi.run, jax.random.key(39), steps, *args,
                         progress_bar=False, timeout=600)
    assert np.isfinite(read_array(result.losses)).all()
    return result.params


def normal_model(positive=False, batched=False):
    def model():
        law = dist.LogNormal(0., 2.) if positive else dist.Normal(0., 2.)
        if batched:
            with velnora.plate('groups', 2):
                velnora.sample('x', law.expand((2,)).to_event(1))
        else:
            velnora.sample('x', law.expand((2,)).to_event(1))
    return model


def configured_normal(cls, positive=False, defaults=False):
    batched = cls in NORMALS[-2:]
    model = normal_model(positive, batched)
    guide = cls(model)
    params = bind_guide(guide)
    shape = (2, 2) if batched else (2,)
    loc = np.broadcast_to([.4, -.7], shape).copy()
    scale = np.broadcast_to([.65, 1.1], shape).copy()
    if cls is ag.AutoNormal:
        params['x_auto_loc'] = jnp.asarray(loc)
        if not defaults:
            params['x_auto_scale'] = jnp.asarray(scale)
        cov = np.diag(read_array(params['x_auto_scale'])**2)
    else:
        params['auto_loc'] = jnp.asarray(loc)
        if cls in (ag.AutoMultivariateNormal, ag.AutoBatchedMultivariateNormal):
            factor = np.array([[.65, 0.], [.55, 1.1]])
            if not defaults:
                params['auto_scale_tril'] = jnp.asarray(np.broadcast_to(factor, shape+(2,)))
            factor = read_array(params['auto_scale_tril'])
            cov = factor @ np.swapaxes(factor, -1, -2)
        elif cls in (ag.AutoLowRankMultivariateNormal, ag.AutoBatchedLowRankMultivariateNormal):
            if not defaults:
                params['auto_scale'] = jnp.asarray(scale)
                params['auto_cov_factor'] = jnp.asarray(np.broadcast_to([[.9], [-.7]], shape+(1,)))
            scale = read_array(params['auto_scale'])
            factor = read_array(params['auto_cov_factor'])*scale[..., None]
            cov = factor @ np.swapaxes(factor, -1, -2) + np.eye(2)*scale[..., None]**2
        else:
            if not defaults:
                params['auto_scale'] = jnp.asarray(scale)
            cov = np.diag(read_array(params['auto_scale'])**2)
    return guide, params, loc, cov


def posterior_array(guide, params, n=8192):
    return read_array(call_public(guide.sample_posterior, jax.random.key(73), params,
                                 sample_shape=(n,), timeout=600)['x'])


def check_normal_draws(values, loc, cov):
    if loc.ndim == 1:
        gaussian_samples(values, loc, cov)
    else:
        assert values.shape == (8192,) + loc.shape
        for i in range(len(loc)):
            gaussian_samples(values[:, i], loc[i], cov[i])


def fitted_normal_cdf(values, mean, sd):
    """Check a fitted Gaussian CDF with explicit approximation and sampling budgets.

    DKW sampling risk is at most 1e-12. The additional 0.10 is the requested
    approximation-CDF error bound, independent of the reference's fit.
    """
    x = np.sort(np.asarray(values))
    p = stats.norm(mean, sd).cdf(x)
    n = len(x)
    error = max(np.max(np.arange(1, n+1)/n-p), np.max(p-np.arange(n)/n))
    assert error < .10 + np.sqrt(np.log(2e12)/(2*n)), error
