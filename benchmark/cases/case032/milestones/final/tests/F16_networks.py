# feature: F16
"""Acceptance tests for neural components in probabilistic models."""
import pytest
from scipy import stats
from F01_helpers import (jax, jnp, np, dist, close, call_public, read_array,
                         check_cdf_samples, frequency)
from F09_helpers import empty_guide
from F16_helpers import affine_component, counting_component
import velnora
from velnora import handlers as h, optim
from velnora.infer import SVI, Trace_ELBO, MCMC, NUTS, Predictive


def test_f16_t01():
    x = jnp.array([[1., 0.], [0., 1.], [-1., 2.], [2., 1.]])
    target = x @ jnp.array([[1.2], [-.8]]) - .4
    for kind in ('functional', 'flax', 'nnx', 'eqx'):
        def model(x, y=None):
            net = affine_component(kind)
            out = net(x)
            velnora.deterministic('output', out)
            velnora.sample('obs', dist.Normal(out, .2).to_event(2), obs=y)
            return out
        initial = call_public(h.seed(model, 1), x, target)
        close(initial, x @ jnp.array([[.3], [-.6]]) + .7)
        svi = SVI(model, empty_guide, optim.Adam(.05), Trace_ELBO())
        result = call_public(svi.run, jax.random.key(2), 350, x, target,
                             progress_bar=False, timeout=240)
        fitted = call_public(h.seed(h.substitute(model, data=result.params), 3), x, target)
        np.testing.assert_allclose(fitted, target, atol=.02, rtol=0)
        # A second input ensures training changed the network itself.
        probe = jnp.array([[.4, -1.7], [2.1, .2]])
        fitted = call_public(h.seed(h.substitute(model, data=result.params), 3), probe)
        np.testing.assert_allclose(fitted, probe @ jnp.array([[1.2], [-.8]]) - .4,
                                   atol=.03, rtol=0)


def test_f16_t02():
    x = jnp.array([[1., 0.], [0., 1.], [2., -1.]])
    for kind in ('flax', 'nnx', 'eqx'):
        for mode in ('selected', 'callback', 'shared'):
            def prior(name, shape):
                # These names and shapes belong to the caller's own network.
                assert (name, shape) in (('weight', (2, 1)), ('bias', (1,)))
                return dist.Normal(1.3, .8) if name == 'weight' else dist.Normal(-.9, .4)
            law = ({'weight': dist.Normal(1.3, .8)} if mode == 'selected' else
                   dist.Normal(1.3, .8) if mode == 'shared' else prior)
            def model():
                net = affine_component(kind, prior=law)
                first, second = net(x), net(x * 2)
                velnora.deterministic('first', first)
                velnora.deterministic('second', second)
            def draw(key):
                tr = h.trace(h.seed(model, key)).get_trace()
                weight = tr['net/weight']['value']
                bias = tr['net/bias']['value'] if mode != 'selected' else jnp.array([.7])
                return weight, bias, tr['first']['value'], tr['second']['value']
            w, b, first, second = call_public(jax.jit(jax.vmap(draw)),
                jax.random.split(jax.random.key(19), 8192), timeout=240)
            assert w.shape == (8192, 2, 1) and b.shape == (8192, 1)
            close(first, x @ w + b[:, None, :])
            close(second, (2 * x) @ w + b[:, None, :])
            for column in range(2):
                check_cdf_samples(read_array(w[:, column, 0]), stats.norm(1.3, .8).cdf)
            # The joint prior must not collapse distinct weights to one draw.
            check_cdf_samples(read_array((w[:, 0, 0] - w[:, 1, 0]) / (.8 * np.sqrt(2))),
                              stats.norm.cdf)
            if mode != 'selected':
                loc, scale = (-.9, .4) if mode == 'callback' else (1.3, .8)
                check_cdf_samples(read_array(b[:, 0]), stats.norm(loc, scale).cdf)


def test_f16_t03():
    for kind in ('flax', 'nnx', 'eqx'):
        def model():
            out = counting_component(kind)(jnp.array(0.))
            velnora.factor('score', -out ** 2)
        svi = SVI(model, empty_guide, optim.Adam(.01), Trace_ELBO(num_particles=1))
        state = call_public(svi.init, jax.random.key(4))
        losses = []
        for _ in range(4):
            state, loss = call_public(jax.jit(svi.update), state)
            losses.append(float(loss))
        # Initialization may call a stateful network to discover its variables;
        # compare increments, not that framework-specific starting count.
        roots = np.sqrt(losses)
        assert roots[0] >= 1
        close(np.diff(roots), np.ones(3))

    from flax import linen as nn
    from flax import nnx
    import equinox as eqx
    x = jnp.ones((8192,))
    for kind in ('flax', 'nnx', 'eqx'):
        def model(key):
            if kind == 'flax':
                from velnora.contrib.module import flax_module
                class Drop(nn.Module):
                    @nn.compact
                    def __call__(self, x):
                        self.param('offset', lambda key: jnp.array(0.))
                        return nn.Dropout(.25)(x, deterministic=False)
                net = flax_module('drop', Drop(), input_shape=x.shape, apply_rng=['dropout'])
                return net(x, rngs={'dropout': key})
            if kind == 'nnx':
                from velnora.contrib.module import nnx_module
                net = nnx_module('drop', nnx.Dropout(.25, rngs=nnx.Rngs(0)))
                return net(x, rngs=nnx.Rngs(dropout=key))
            from velnora.contrib.module import eqx_module
            return eqx_module('drop', eqx.nn.Dropout(.25))(x, key=key)
        for seed in (17, 33):
            out = read_array(call_public(h.seed(model, 0), jax.random.key(seed)))
            assert out.shape == x.shape
            assert np.all(np.isclose(out, 0) | np.isclose(out, 1 / .75))
            frequency(out == 0, .25)
        # Caller-selected randomness must be honoured even within one execution.
        def paired():
            return model(jax.random.key(17)), model(jax.random.key(33))
        a, b = call_public(h.seed(paired, 0))
        frequency(read_array(a == b), .25 ** 2 + .75 ** 2)


def test_f16_t04():
    x = jnp.array([[1., 0.], [0., 1.], [1., 1.], [-1., 2.], [2., -.5]])
    y = x @ jnp.array([[1.1], [-.8]]) + .7
    # Independent conjugate Gaussian posterior for caller-defined linear nets.
    covariance = np.linalg.inv(np.eye(2) + np.asarray(x).T @ np.asarray(x) / .2 ** 2)
    mean = covariance @ (np.asarray(x).T @ (np.asarray(y[:, 0]) - .7) / .2 ** 2)
    for kind in ('flax', 'nnx', 'eqx'):
        def model(x, y=None):
            net = affine_component(kind, prior={'weight': dist.Normal()})
            out = velnora.deterministic('output', net(x))
            velnora.sample('obs', dist.Normal(out, .2).to_event(2), obs=y)
        sampler = MCMC(NUTS(model), num_warmup=300, num_samples=1600, progress_bar=False)
        call_public(sampler.run, jax.random.key(29), x, y, timeout=240)
        samples = sampler.get_samples()
        w = read_array(samples['net/weight'])
        assert w.shape == (1600, 2, 1)
        np.testing.assert_allclose(w[:, :, 0].mean(0), mean, atol=.04, rtol=0)
        np.testing.assert_allclose(np.cov(w[:, :, 0].T), covariance, atol=.004, rtol=.25)
        probe = jnp.array([[.2, 1.], [-.7, .3], [1.4, -.2]])
        pred = call_public(Predictive(model, samples, return_sites=['output', 'obs']),
                           jax.random.key(30), probe, timeout=240)
        assert pred['output'].shape == pred['obs'].shape == (1600, 3, 1)
        close(pred['output'], probe @ samples['net/weight'] + .7)
        check_cdf_samples(read_array((pred['obs'] - pred['output'])[:, 0, 0]),
                          stats.norm(0, .2).cdf)


def test_f16_t05():
    def init(key, shape):
        return shape[:-1] + (1,), (jnp.full((shape[-1], 1), .4), jnp.array([-.2]))
    def apply(params, x):
        return x @ params[0] + params[1]
    x = jnp.array([[1., 2., 3.], [-1., 0., 2.]])
    def model(shape=None):
        return velnora.module('net', (init, apply), input_shape=shape)(x)
    supplied = (jnp.array([[1.], [-2.], [.5]]), jnp.array([.8]))
    out = call_public(h.seed(h.substitute(model, data={'net$params': supplied}), 0))
    close(out, apply(supplied, x))
    close(call_public(h.seed(model, 0), (3,)), x @ jnp.full((3, 1), .4) - .2)
    with pytest.raises(ValueError):
        call_public(h.seed(model, 0))
