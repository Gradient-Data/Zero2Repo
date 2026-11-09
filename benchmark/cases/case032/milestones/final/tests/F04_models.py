# feature: F04
"""Acceptance tests for model declarations and independent data groups."""
import itertools
import gc

import pytest
from scipy import stats
from F01_helpers import (
    jax, jnp, np, dist, close, read_array, call_public,
    check_cdf_samples, frequency, N,
)
import velnora
from velnora import handlers
from velnora.primitives import mutable
from velnora.infer import SVI, Trace_ELBO
from velnora.infer.autoguide import AutoNormal
from velnora.infer.util import log_density
from velnora.optim import SGD


@pytest.fixture(autouse=True)
def release_f04_cache():
    yield
    jax.clear_caches()
    gc.collect()


def test_f04_t01():
    def model(initial, observation, weight):
        p = velnora.param('offset', initial)
        z = velnora.sample('latent', dist.Normal(p, .8))
        y = velnora.sample('data', dist.Normal(z, 1.3), obs=observation)
        d = velnora.deterministic('derived', z * p + y)
        state = mutable('state', {'total': p})
        state['total'] = state['total'] + d
        velnora.factor('weight', weight)
        return p, z, y, d, state['total']

    for initial, supplied, observation, weight in [(1.2, -.4, .7, -1.6), (-.8, 2.1, -1.3, .9)]:
        args = (initial, observation, weight)
        values = {'offset': supplied, 'latent': .3}
        bound = handlers.substitute(model, data=values)
        result = call_public(bound, *args)
        close(result, [supplied, .3, observation, .3*supplied+observation, supplied+.3*supplied+observation])
        score, record = call_public(log_density, model, args, {}, values)
        close(score, stats.norm.logpdf(.3, supplied, .8)+stats.norm.logpdf(observation, .3, 1.3)+weight)
        for name, value in [('offset', supplied), ('latent', .3), ('data', observation), ('derived', .3*supplied+observation)]:
            close(record[name]['value'], value)
        assert record['data']['is_observed'] is True
        close(record['state']['value']['total'], supplied+.3*supplied+observation)
        independent = call_public(handlers.substitute(model, data={'latent': .3}), *args)
        close(independent[0], initial)


def test_f04_t02():
    def model(key=None):
        x = velnora.sample('x', dist.Normal(.4, 1.2), rng_key=key)
        y = velnora.sample('y', dist.Normal(2*x-.7, .9), obs=1.1)
        return x, x*x+y

    explicit = lambda key: model(key)
    seeded = lambda key: handlers.seed(model, rng_seed=key)()
    for run in [explicit, seeded]:
        keys = jax.random.split(jax.random.key(519), N)
        samples, results = call_public(jax.jit(jax.vmap(run)), keys)
        check_cdf_samples(read_array(samples), stats.norm(.4, 1.2).cdf)
        close(results, read_array(samples)**2+1.1)
        close(call_public(run, keys[0]), call_public(run, keys[0]))
        record = handlers.trace(handlers.seed(model, rng_seed=keys[0])).get_trace()
        x = read_array(record['x']['value'])
        close(record['y']['fn'].log_prob(record['y']['value']), stats.norm.logpdf(1.1, 2*x-.7, .9))

    def from_key():
        return jax.random.normal(velnora.prng_key(), (N,))
    check_cdf_samples(read_array(call_public(handlers.seed(from_key, rng_seed=21))), stats.norm.cdf)


def test_f04_t03():
    def model(stacked):
        if stacked:
            with velnora.plate_stack('groups', (3, 4)):
                return velnora.sample('x', dist.Normal(jnp.array([-.3, .8]), .7).to_event(1))
        with velnora.plate('outer', 3, dim=-2), velnora.plate('inner', 4, dim=-1):
            return velnora.sample('x', dist.Normal(jnp.array([-.3, .8]), .7).to_event(1))
    point = np.arange(24).reshape(3, 4, 2)/13
    for stacked in [False, True]:
        run = handlers.seed(model, rng_seed=2)
        assert call_public(run, stacked).shape == (3, 4, 2)
        score, record = call_public(log_density, model, (stacked,), {}, {'x': jnp.array(point)})
        assert record['x']['fn'].batch_shape == (3, 4)
        assert record['x']['fn'].event_shape == (2,)
        close(score, stats.norm.logpdf(point, [-.3, .8], .7).sum())
    def automatic():
        with velnora.plate('a', 3), velnora.plate('b', 4):
            return velnora.sample('x', dist.Normal(jnp.zeros(2), 1.).to_event(1))
    result = call_public(handlers.seed(automatic, rng_seed=3))
    assert sorted(result.shape[:-1]) == [3, 4] and result.shape[-1] == 2
    for dim in [0, 1]:
        with pytest.raises(ValueError):
            call_public(lambda: velnora.plate('bad', 3, dim=dim))
    def collision():
        with velnora.plate('a', 3, dim=-1), velnora.plate('b', 4, dim=-1):
            return velnora.sample('x', dist.Normal())
    with pytest.raises(AssertionError):
        call_public(handlers.seed(collision, rng_seed=3))


def test_f04_t04():
    data = jnp.arange(30.).reshape(10, 3)/7
    local = jnp.arange(30.).reshape(10, 3)/11-.4
    def model(size):
        with velnora.plate('rows', 10, subsample_size=size) as indices:
            selected = velnora.subsample(data, event_dim=1)
            p = velnora.param('local', local, event_dim=1)
            velnora.sample('data', dist.Normal(p, .8).to_event(1), obs=selected)
            velnora.factor('extra', -.1*jnp.sum(selected**2, axis=-1))
            velnora.deterministic('selection', selected)
            velnora.deterministic('parameters', p)
        return indices, selected, p
    for size in [4, 10]:
        seeded = handlers.seed(model, rng_seed=37)
        indices, selected, p = call_public(seeded, size)
        indices = read_array(indices)
        assert indices.shape == (size,) and len(np.unique(indices)) == size
        assert ((0 <= indices) & (indices < 10)).all()
        close(selected, read_array(data)[indices])
        close(p, read_array(local)[indices])
        if size == 10:
            assert set(indices) == set(range(10))
        score, record = call_public(log_density, handlers.seed(model, rng_seed=37), (size,), {}, {})
        close(record['selection']['value'], selected)
        close(record['parameters']['value'], p)
        expected = (stats.norm.logpdf(selected, p, .8).sum()-.1*np.square(selected).sum())*10/size
        close(score, expected)


def test_f04_t05():
    def subset(key):
        with handlers.seed(rng_seed=key):
            with velnora.plate('rows', 5, subsample_size=2) as indices:
                return indices
    indices = read_array(call_public(jax.jit(jax.vmap(subset)), jax.random.split(jax.random.key(47), N)))
    assert indices.shape == (N, 2)
    assert ((indices >= 0) & (indices < 5)).all()
    assert (indices[:, 0] != indices[:, 1]).all()
    # There are ten unordered subsets. Each Bernoulli indicator uses the
    # shared Hoeffding bound (1e-12 per check); union risk is at most 1e-11.
    ordered = np.sort(indices, axis=-1)
    for pair in itertools.combinations(range(5), 2):
        frequency(np.all(ordered == pair, axis=-1), .1)


def test_f04_t06():
    mask = jnp.array([True, False, True, False])
    for event_size in [None, 2]:
        shape = (4,) if event_size is None else (4, event_size)
        data = jnp.arange(np.prod(shape), dtype=float).reshape(shape)/4+.5
        def model(observations):
            loc = velnora.param('location', jnp.array(0.))
            law = dist.Normal(loc, 1.) if event_size is None else dist.Normal(jnp.full((event_size,), loc), 1.).to_event(1)
            with velnora.plate('rows', 4):
                return velnora.sample('data', law, obs=observations, obs_mask=mask)
        def generate(key):
            return handlers.seed(model, rng_seed=key)(data)
        samples = read_array(call_public(jax.jit(jax.vmap(generate)), jax.random.split(jax.random.key(94), N)))
        assert samples.shape == (N,)+shape
        close(samples[:, np.asarray(mask)], np.broadcast_to(np.asarray(data)[np.asarray(mask)], samples[:, np.asarray(mask)].shape))
        for column in samples[:, ~np.asarray(mask)].reshape(N, -1).T:
            check_cdf_samples(column, stats.norm.cdf)
        # At initialization the automatic normal guide equals the missing-data
        # prior. Its probability cancels the latent prior, leaving known data.
        # Use explicit zero-radius uniform initialization to set real latent means
        # to zero, without depending on auxiliary site names or parameter layout.
        from velnora.infer import init_to_uniform
        guide = handlers.mask(AutoNormal(model, init_loc_fn=init_to_uniform(radius=0.), init_scale=1.), mask=~mask)
        svi = SVI(model, guide, SGD(.01), Trace_ELBO(num_particles=N, vectorize_particles=True))
        state = call_public(svi.init, jax.random.key(48), data)
        loss = call_public(svi.evaluate, state, data)
        close(loss, -stats.norm.logpdf(np.asarray(data)[np.asarray(mask)]).sum())
        changed = jnp.where(mask.reshape((4,)+(1,)*(len(shape)-1)), data, data+100.)
        other_loss = call_public(svi.evaluate, state, changed)
        close(other_loss, loss)
        updated, training_loss = call_public(svi.update, state, data)
        updated_other, other_training_loss = call_public(svi.update, state, changed)
        close(training_loss, other_training_loss)
        fitted = svi.get_params(updated)
        fitted_other = svi.get_params(updated_other)
        for name in fitted:
            close(fitted[name], fitted_other[name])
        # Missing-prior score noise has standard error sqrt(missing_count/N).
        # Ten standard errors give negligible false rejection risk.
        expected = .01*np.asarray(data)[np.asarray(mask)].sum()
        error = .01*10*np.sqrt(np.asarray(data)[~np.asarray(mask)].size/N)
        assert abs(float(fitted['location'])-expected) < error


def test_f04_t07():
    data = jnp.array([-.8, .4, 1.7])
    def model(theta):
        offset = velnora.param('offset', theta)
        with velnora.plate('rows', 3):
            velnora.sample('data', dist.Normal(2*offset+.3, .8), obs=data)
        velnora.factor('penalty', -.4*offset**2)
        return velnora.deterministic('result', offset**2+data.sum())
    def score(theta):
        return log_density(model, (theta,), {}, {})[0]
    points = jnp.array([-.7, .2, 1.1])
    expected = stats.norm.logpdf(np.asarray(data)[None, :], 2*np.asarray(points)[:, None]+.3, .8).sum(-1)-.4*np.asarray(points)**2
    close(call_public(jax.jit(jax.vmap(score)), points), expected)
    close(call_public(jax.vmap(jax.grad(score)), points), (2*(np.asarray(data)[None, :]-2*np.asarray(points)[:, None]-.3)/.8**2).sum(-1)-.8*np.asarray(points))
    def seeded(theta, key):
        return handlers.seed(model, rng_seed=key)(theta)
    keys = jax.random.split(jax.random.key(55), len(points))
    close(call_public(jax.jit(jax.vmap(seeded)), points, keys), np.asarray(points)**2+float(data.sum()))
