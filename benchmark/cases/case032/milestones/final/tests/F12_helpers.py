# feature: F12
"""Public MCMC drivers and independent conjugate posterior checks."""
from F01_helpers import jax, jnp, np, dist, close, read_array, call_public
from F08_helpers import finite_assignment_table
from scipy import stats
import velnora
from velnora.infer import MCMC


def collect(kernel, *args, seed=41, warmup=300, samples=6000, extra_fields=(), **options):
    options.setdefault('num_chains', 3)
    options.setdefault('chain_method', 'sequential')
    runner = MCMC(kernel, num_warmup=warmup, num_samples=samples,
                  progress_bar=False, **options)
    call_public(runner.run, jax.random.key(seed), *args, extra_fields=extra_fields, timeout=600)
    return runner


def observed_normal_model(data=3.):
    x = velnora.sample('x', dist.Normal(0., 2.))
    velnora.sample('obs', dist.Normal(x, 1.), obs=data)
    velnora.deterministic('derived', 2*x + data)


def beta_model():
    p = velnora.sample('p', dist.Beta(2., 3.))
    velnora.sample('obs', dist.Binomial(20, p), obs=18.)
    velnora.deterministic('derived', p*p)


def check_law(values, law, cdf_tolerance=.04):
    """Check location, spread and CDF, without treating correlated draws as IID.

    These deliberately coarse accuracy bands use thousands of transitions on
    well-conditioned low-dimensional targets. No effective-size estimate from
    the product is used. The driver pools three independently keyed chains.
    This is empirical MCMC evidence, not an IID concentration theorem.
    """
    x = read_array(values).reshape(-1)
    assert len(x) >= 1000 and np.isfinite(x).all()
    scale = law.std()
    assert abs(x.mean() - law.mean()) < .20*scale
    assert abs(x.std() - scale) < .20*scale
    for q in (.1, .25, .5, .75, .9):
        assert abs(np.mean(x <= law.ppf(q)) - q) < cdf_tolerance


def pair_model():
    x = velnora.sample('x', dist.Normal(0., 1.))
    y = velnora.sample('y', dist.Normal(x, 1.))
    velnora.sample('obs', dist.Normal(y, 1.), obs=3.)
    velnora.deterministic('sum', x+y)


def update_x(rng_key, gibbs_sites, hmc_sites):
    return {'x': dist.Normal(hmc_sites['y']/2, jnp.sqrt(.5)).sample(rng_key)}


def check_pair(samples):
    # Conditioning a Gaussian chain on its terminal noisy observation gives
    # means (1, 2), covariance [[2/3, 1/3], [1/3, 2/3]].
    check_law(samples['x'], stats.norm(1., np.sqrt(2/3)))
    check_law(samples['y'], stats.norm(2., np.sqrt(2/3)))
    check_law(samples['sum'], stats.norm(3., np.sqrt(2.)))
    close(samples['sum'], samples['x'] + samples['y'])
    assert abs(np.cov(read_array(samples['x']), read_array(samples['y']))[0, 1] - 1/3) < .16


def mixed_model(enumerated=False):
    z = velnora.sample('z', dist.Bernoulli(.3),
                       infer={'enumerate': 'parallel'} if enumerated else {})
    x = velnora.sample('x', dist.Normal(2*z, 1.))
    velnora.sample('obs', dist.Normal(x, 1.), obs=2.)
    velnora.deterministic('derived', x*x)


def mixed_reference():
    _, masses = finite_assignment_table([2], lambda z:
        (.3 if z[0] else .7)*stats.norm.pdf(2., 2*z[0], np.sqrt(2.)))
    return masses[1]/masses.sum()


def check_mixed(samples, marginalized=False):
    p = mixed_reference()
    x = read_array(samples['x'])
    assert abs(x.mean() - (1+p)) < .18
    assert abs(x.var() - (.5+p*(1-p))) < .20
    for value in (0., 1., 2., 3.):
        cdf = (1-p)*stats.norm.cdf(value, 1., np.sqrt(.5)) + p*stats.norm.cdf(value, 2., np.sqrt(.5))
        assert abs(np.mean(x <= value)-cdf) < .10
    close(samples['derived'], x*x)
    if marginalized:
        assert 'z' not in samples
    else:
        z = read_array(samples['z'])
        assert np.isin(z, [0, 1]).all()
        assert abs(z.mean()-p) < .10
        for level in (0, 1):
            assert (z == level).sum() > 100
            check_law(x[z == level], stats.norm(1+level, np.sqrt(.5)))


def data_model(data):
    x = velnora.sample('x', dist.Normal(0., 2.))
    with velnora.plate('batch', len(data), subsample_size=8):
        velnora.sample('obs', dist.Normal(x, 1.), obs=velnora.subsample(data, 0))
