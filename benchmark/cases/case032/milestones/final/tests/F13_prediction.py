# feature: F13
"""Acceptance tests for predictive laws and pointwise observation likelihoods."""
import pytest
from F01_helpers import (jax, jnp, np, dist, stats, close, read_array,
                         call_public, check_cdf_samples, gaussian_samples,
                         frequency, N)
from F08_helpers import finite_assignment_table
from F10_helpers import fit_guide, ag
import velnora
from velnora.infer import Predictive, log_likelihood


def test_f13_t01():
    def model(offset, data=None):
        x = velnora.sample('x', dist.Normal(-.8, 1.2))
        velnora.sample('y', dist.Normal(2*x+offset, .6), obs=data)
    offset = 1.7
    prior = call_public(Predictive(model, num_samples=N), jax.random.key(131), offset)
    gaussian_samples(np.column_stack([read_array(prior['x']), read_array(prior['y'])]),
                     np.array([-.8, .1]), np.array([[1.44, 2.88], [2.88, 6.12]]))
    supplied = np.linspace(-2., 2.5, N)
    posterior = call_public(Predictive(model, {'x': jnp.asarray(supplied)}),
                            jax.random.key(132), offset)
    residual = read_array(posterior['y']) - (2*supplied+offset)
    # Check each half separately so reordering conditioning samples cannot hide
    # behind a correct unconditional mixture.
    for part in np.array_split(residual, 2):
        check_cdf_samples(part, stats.norm(0., .6).cdf)
    guide = ag.AutoNormal(model)
    params = fit_guide(model, guide, 1200, offset, jnp.asarray(3.1))
    guided = call_public(Predictive(model, guide=guide, params=params,
                                   num_samples=N, return_sites=['x', 'y']),
                         jax.random.key(133), offset)
    x, y = read_array(guided['x']), read_array(guided['y'])
    # Compare to the fitted guide actually supplied, not the reference fit.
    loc, scale = float(params['x_auto_loc']), float(params['x_auto_scale'])
    gaussian_samples(np.column_stack([x, y]), np.array([loc, 2*loc+offset]),
                     np.array([[scale**2, 2*scale**2],
                               [2*scale**2, 4*scale**2+.36]]))


def test_f13_t02():
    def model(inputs):
        x = velnora.sample('x', dist.Normal(0., 1.))
        mean = velnora.deterministic('mean', x*inputs)
        velnora.sample('future', dist.Normal(mean, .4).to_event(1))
    x = jnp.linspace(-1., 2., N)
    stale = jnp.broadcast_to(jnp.array([7., -8.]), (N, 2))
    samples = {'x': x, 'mean': stale}
    inputs = jnp.array([1.5, -.7])
    default = call_public(Predictive(model, samples), jax.random.key(134), inputs)
    assert set(default) == {'mean', 'future'}
    expected = read_array(x)[:, None]*read_array(inputs)
    close(default['mean'], expected)
    gaussian_samples(read_array(default['future'])-expected, np.zeros(2), np.eye(2)*.16)
    selected = call_public(Predictive(model, samples, return_sites=['x', 'mean']),
                           jax.random.key(134), inputs)
    assert set(selected) == {'x', 'mean'}
    close(selected['x'], read_array(x))
    close(selected['mean'], expected)
    conditioned = call_public(Predictive(model, samples, condition_deterministic=True),
                              jax.random.key(134), inputs)
    assert set(conditioned) == {'mean', 'future'}
    close(conditioned['mean'], read_array(stale))
    gaussian_samples(read_array(conditioned['future'])-read_array(stale),
                     np.zeros(2), np.eye(2)*.16)


def test_f13_t03():
    def model():
        x = velnora.sample('x', dist.Normal(0., 1.).expand((2,)).to_event(1))
        velnora.deterministic('shift', 3*x-1)
        with velnora.plate('rows', 3):
            velnora.sample('future', dist.Normal(x, .7).to_event(1))
    for shape in [(), (N,), (2, N//2)]:
        x = np.arange(max(1, int(np.prod(shape)))*2).reshape(shape+(2,))/1000
        result = call_public(Predictive(model, {'x': jnp.asarray(x)},
                                        batch_ndims=len(shape)), jax.random.key(135))
        assert read_array(result['future']).shape == shape+(3, 2)
        assert read_array(result['shift']).shape == shape+(2,)
        close(result['shift'], 3*x-1)
        if shape:
            residual = read_array(result['future']) - x[..., None, :]
            gaussian_samples(residual.reshape((-1, 6)), np.zeros(6), np.eye(6)*.49)
    with pytest.warns(UserWarning):
        result = call_public(lambda: Predictive(model, {'x': jnp.ones((7, 2))},
                                                num_samples=11)(jax.random.key(136)))
    assert read_array(result['future']).shape == (7, 3, 2)
    close(result['shift'], np.full((7, 2), 2.))
    prior = call_public(Predictive(model, num_samples=13), jax.random.key(137))
    assert read_array(prior['future']).shape == (13, 3, 2)


def test_f13_t04():
    def model():
        x = velnora.sample('x', dist.Normal(0., 1.))
        y = velnora.sample('y', dist.Normal(x, 1.))
        velnora.deterministic('sum', x+y)
    def guide():
        velnora.sample('x', dist.Normal(1., .5))
        velnora.sample('y', dist.Normal(-1., .7))
    for options in [{}, {'guide': guide}, {'posterior_samples': {}},
                    {'posterior_samples': {'x': jnp.ones(3), 'y': jnp.ones(4)}},
                    {'posterior_samples': {'x': jnp.ones((2, 3)), 'y': jnp.ones((2, 4))},
                     'batch_ndims': 2}]:
        with pytest.raises(ValueError):
            call_public(lambda: Predictive(model, **options)(jax.random.key(138)))
    valid = call_public(Predictive(model, {'x': jnp.arange(3.), 'y': jnp.ones(3)}),
                        jax.random.key(138))
    close(valid['sum'], np.arange(3.)+1)
    for options in [{}, {'guide': guide}, {'posterior_samples': {}}]:
        valid = call_public(Predictive(model, num_samples=5, **options), jax.random.key(138))
        assert read_array(valid['sum']).shape == (5,)
        assert np.isfinite(read_array(valid['sum'])).all()


def test_f13_t05():
    def model():
        z = velnora.sample('z', dist.Bernoulli(.25), infer={'enumerate': 'parallel'})
        velnora.sample('x', dist.Normal(2*z, 1.))
        velnora.sample('future', dist.Bernoulli(.15+.7*z))
    # Both sites must be inferred jointly: future is unobserved and must retain
    # dependence on z, while supplied x changes the conditional category law.
    for value in [-.5, 1.7]:
        assignments, masses = finite_assignment_table([2, 2], lambda row:
            stats.bernoulli.pmf(row[0], .25)*stats.norm.pdf(value, 2*row[0], 1.)*
            stats.bernoulli.pmf(row[1], .15+.7*row[0]))
        result = call_public(Predictive(model, {'x': jnp.full((N,), value)},
                                        infer_discrete=True), jax.random.key(139), timeout=240)
        assert set(result) == {'z', 'future'}
        z, future = read_array(result['z']), read_array(result['future'])
        assert z.shape == future.shape == (N,)
        assert np.isin(z, [0, 1]).all() and np.isin(future, [0, 1]).all()
        for row, mass in zip(assignments, masses):
            frequency((z == row[0]) & (future == row[1]), mass/masses.sum())


def test_f13_t06():
    def model(inputs, observed, count):
        x = velnora.sample('x', dist.Normal(-2., .3))
        with velnora.plate('rows', len(inputs)):
            velnora.sample('data', dist.Normal(x*inputs, .8), obs=observed)
        velnora.sample('count', dist.Poisson(jnp.exp(x)), obs=count)
        velnora.deterministic('extra', x+1)
    inputs, observed = np.array([-.7, .2, 1.4]), np.array([.4, -.3, 1.8])
    for shape in [(), (4,), (2, 3)]:
        x = np.linspace(-.8, .9, max(1, int(np.prod(shape)))).reshape(shape)
        for parallel in [False, True]:
            result = call_public(log_likelihood, model, {'x': jnp.asarray(x)},
                                 jnp.asarray(inputs), jnp.asarray(observed), 2,
                                 batch_ndims=len(shape), parallel=parallel)
            assert set(result) == {'data', 'count'}
            assert read_array(result['data']).shape == shape+(3,)
            assert read_array(result['count']).shape == shape
            close(result['data'], stats.norm.logpdf(observed, x[..., None]*inputs, .8))
            close(result['count'], stats.poisson.logpmf(2, np.exp(x)))
