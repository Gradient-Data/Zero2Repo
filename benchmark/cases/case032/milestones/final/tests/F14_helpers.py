# feature: F14
"""Independent statistical definitions and small calibration models."""
from F01_helpers import jax, jnp, np, dist, stats, close, call_public, read_array, RTOL, ATOL
from F09_helpers import velnora, optim, Trace_ELBO
from velnora.infer.calibration import vsbc_diagnostic


def lag_covariances(x, axis=0, bias=True):
    y = np.moveaxis(np.asarray(x), axis, 0)
    y = y - y.mean(axis=0)
    n = len(y)
    return np.moveaxis(np.stack([
        (y[:n-k] * y[k:]).sum(axis=0) / (n if bias else n-k)
        for k in range(n)]), 0, axis)


def rhat_definition(x):
    n = x.shape[1]
    within = x.var(axis=1, ddof=1).mean(axis=0)
    return np.sqrt(((1-1/n)*within + x.mean(axis=1).var(axis=0, ddof=1))/within)


def stan_ess_definition(x, bias=True):
    """Stan 2.18 sec. 15.4: paired initial positive monotone correlations.

    Direct lag products deliberately avoid the product's FFT implementation.
    """
    x = np.asarray(x)
    m, n = x.shape[:2]
    within = x.var(axis=1, ddof=1).mean(axis=0)
    pooled = within*(1-1/n)
    if m > 1:
        pooled += x.mean(axis=1).var(axis=0, ddof=1)
    else:
        within = pooled
    rho = 1 - (within - lag_covariances(x, 1, bias).mean(axis=0))/pooled
    rho[0] = 1
    pairs = [rho[k]+rho[k+1] for k in range(0, n-1, 2)]
    total = pairs[0].copy()
    previous = np.full_like(total, np.inf)
    for pair in pairs[1:]:
        previous = np.minimum(previous, np.maximum(pair, 0))
        total += previous
    return m*n/(2*total-1)


def check_shortest_interval(values, interval, prob, axis=0):
    """Accept every tied minimizing empirical rank interval."""
    x = np.sort(np.moveaxis(values, axis, 0), axis=0)
    endpoints = np.moveaxis(np.asarray(interval), axis, 0)
    assert endpoints.shape == (2,) + x.shape[1:]
    rank_gap = int(prob*len(x))
    widths = x[rank_gap:] - x[:len(x)-rank_gap]
    close(endpoints[1]-endpoints[0], widths.min(axis=0))
    candidates = (np.isclose(x[:len(x)-rank_gap], endpoints[0], rtol=RTOL, atol=ATOL) &
                  np.isclose(x[rank_gap:], endpoints[1], rtol=RTOL, atol=ATOL))
    assert candidates.any(axis=0).all()


def calibration(model, guide, *args, **kwargs):
    options = dict(observed_sites=['obs'], num_simulations=8,
                   num_svi_steps=2, num_samples=2048)
    options.update(kwargs)
    return call_public(vsbc_diagnostic, jax.random.PRNGKey(72), model, guide,
                       optim.Adam(.08), Trace_ELBO(), *args, timeout=240, **options)


def routed_model(obs=None):
    z = velnora.sample('z', dist.Normal(jnp.array([-2., 3.]), 1.).to_event(1))
    velnora.sample('obs', dist.Normal(z, .00001).to_event(1), obs=obs)


def routed_guide(obs=None):
    velnora.sample('z', dist.Normal(obs+jnp.array([-.7, .7]), .3).to_event(1))


def check_routed_result(result):
    assert set(result.param_names) == {'z'}
    p = result.probabilities['z']
    assert p.shape == (8, 2)
    # The likelihood noise is negligible relative to the guide scale. Hoeffding
    # with 2048 draws and error .10 gives a family failure bound below 6e-17.
    close(result.ranks['z']/2048, p)
    assert np.max(np.abs(p-stats.norm.cdf(np.array([.7, -.7])/.3))) < .10
