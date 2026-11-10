# feature: F07
"""Public inference fixtures and independent probability/coordinate oracles."""
from F01_helpers import jax, jnp, np, dist, close, read_array, call_public
from F02_helpers import volume
from scipy import stats, special
import velnora
from velnora.infer.util import initialize_model, constrain_fn, unconstrain_fn


def coordinate_model(data=.6):
    x = velnora.sample('positive', dist.Gamma(2.7, 1.4))
    p = velnora.sample('fraction', dist.Beta(2.2, 3.1))
    r = velnora.sample('real', dist.Normal(-.4, 1.3))
    velnora.sample('observation', dist.Normal(x*p+r, .8), obs=data)
    velnora.deterministic('derived', x*p+r)


def model_log_probability(values, data=.6):
    x, p, r = [float(values[k]) for k in ('positive', 'fraction', 'real')]
    return (stats.gamma.logpdf(x, 2.7, scale=1/1.4)
            + stats.beta.logpdf(p, 2.2, 3.1)
            + stats.norm.logpdf(r, -.4, 1.3)
            + stats.norm.logpdf(data, x*p+r, .8))


def pack_latents(values):
    return np.array([values[k] for k in ('positive', 'fraction', 'real')], dtype=float)


def unpack_latents(vector):
    return dict(zip(('positive', 'fraction', 'real'), vector))


def recovered_vector(vector):
    return pack_latents(call_public(constrain_fn, coordinate_model, (), {}, unpack_latents(vector)))


def independent_potential(vector):
    values = call_public(constrain_fn, coordinate_model, (), {}, unpack_latents(vector))
    return -model_log_probability(values) - volume(recovered_vector, vector)


def prepare(model, strategy=None, seed=71):
    options = {} if strategy is None else {'init_strategy': strategy}
    return call_public(initialize_model, jax.random.key(seed), model, timeout=240, **options)


def prior_vector_model(size):
    def model():
        velnora.sample('x', dist.LogNormal(.7, 1.8).expand((size,)).to_event(1))
    return model


def median_coordinate_cdf(info, model, count):
    """Order-statistic law in an arbitrary reversible one-coordinate chart.

    Odd medians have a binomial order-statistic CDF. For two draws, integrate
    F(2t-Q(q)) over q in (0,1), independently of product sampling and RNG order.
    Legendre quadrature integrates the conditional probability, not samples.
    """
    law = stats.lognorm(1.8, scale=np.exp(.7))
    recover = jax.jit(lambda z: info.postprocess_fn({'x': jnp.reshape(z, (1,))})['x'][0])
    endpoints = read_array(call_public(jax.vmap(recover), jnp.array([-.2, .2])))
    increasing = endpoints[-1] > endpoints[0]

    def coordinate_cdf(z):
        shape = np.shape(z)
        values = read_array(call_public(jax.jit(jax.vmap(recover)),
                                       jnp.asarray(z).reshape(-1), timeout=240)).reshape(shape)
        return law.cdf(values) if increasing else law.sf(values)

    if count % 2:
        return lambda z: stats.binom.sf(count//2, count, coordinate_cdf(z))
    assert count == 2
    nodes, weights = special.roots_legendre(512)
    quantiles = law.ppf((nodes+1)/2)
    def chart(value):
        return unconstrain_fn(model, (), {}, {'x': jnp.reshape(value, (1,))})['x'][0]
    q = read_array(call_public(jax.jit(jax.vmap(chart)), jnp.asarray(quantiles), timeout=240))
    return lambda z: weights @ coordinate_cdf(2*np.asarray(z)[None, :] - q[:, None]) / 2
