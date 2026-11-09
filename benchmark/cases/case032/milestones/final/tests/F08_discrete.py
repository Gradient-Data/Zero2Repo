# feature: F08
"""Acceptance tests for finite discrete inference and analytic marginalization."""
import pytest
from scipy import stats
from F01_helpers import jax, jnp, np, dist, close, read_array, call_public, frequency, N
from F08_helpers import finite_assignment_table, finite_state_table
import velnora
from velnora import handlers as h
from velnora.contrib.funsor import config_enumerate, enum, infer_discrete
from velnora.contrib.funsor.infer_util import log_density as enum_log_density
from velnora.contrib.control_flow import scan
from velnora.infer.util import log_density
from velnora.ops.indexing import Vindex


def test_f08_t01():
    observations = np.array([[.1, 1.6, -.4], [2.1, .7, 1.3]])
    root_probs = np.array([.2, .35, .45])
    parent_probs = np.array([.15, .55, .8])
    def model(weight, active):
        offset = velnora.sample('offset', dist.Normal(.3, 1.1))
        root = velnora.sample('root', dist.Categorical(jnp.asarray(root_probs)))
        with velnora.plate('groups', 2, dim=-2):
            parent = velnora.sample('parent', dist.Bernoulli(jnp.asarray(parent_probs)[root]))
            with velnora.plate('items', 3, dim=-1):
                child = velnora.sample('child', dist.Bernoulli(.2+.6*parent))
                with h.scale(scale=weight), h.mask(mask=active):
                    velnora.sample('data', dist.Normal(offset+root+.7*parent+1.3*child, .9), obs=jnp.asarray(observations))
    for offset, fixed_root, weight, active in [
        (-.2, None, 1., np.ones((2, 3), bool)),
        (.9, 1, .65, np.array([[True, False, True], [False, True, True]])),
    ]:
        total = 0.
        for root in (range(3) if fixed_root is None else [fixed_root]):
            group_mass = 1.
            for group in range(2):
                subtotal = 0.
                for parent in range(2):
                    term = stats.bernoulli.pmf(parent, parent_probs[root])
                    for item in range(3):
                        term *= sum(stats.bernoulli.pmf(child, .2+.6*parent) *
                                    (stats.norm.pdf(observations[group, item], offset+root+.7*parent+1.3*child, .9)**weight if active[group, item] else 1.)
                                    for child in range(2))
                    subtotal += term
                group_mass *= subtotal
            total += root_probs[root]*group_mass
        params = {'offset': jnp.asarray(offset)}
        if fixed_root is not None:
            params['root'] = jnp.asarray(fixed_root)
        score, _ = call_public(enum_log_density, enum(config_enumerate(model), first_available_dim=-3), (weight, jnp.asarray(active)), {}, params)
        close(score, np.log(total)+stats.norm.logpdf(offset, .3, 1.1))


# Each frequency check uses the imported Hoeffding bound (risk <= 1e-12).
# The joint-assignment and complete-path checks total 16 comparisons, so their
# combined false-rejection probability is at most 1.6e-11.
def test_f08_t02():
    likelihood = np.array([[.9, .85], [.75, .025]])
    def model(observed):
        a = velnora.sample('a', dist.Bernoulli(.6)).astype(int)
        b = velnora.sample('b', dist.Bernoulli(.5)).astype(int)
        velnora.sample('data', dist.Bernoulli(Vindex(jnp.asarray(likelihood))[a, b]), obs=observed)
        return a, b
    for observed in [1., 0.]:
        assignments, masses = finite_assignment_table([2, 2], lambda x: stats.bernoulli.pmf(x[0], .6)*.5*stats.bernoulli.pmf(observed, likelihood[x]))
        actual = read_array(call_public(infer_discrete(config_enumerate(model), temperature=0, rng_key=jax.random.key(81)), observed))
        assert actual.shape == (2,)
        matches = np.all(assignments == actual, axis=1)
        assert matches.any()
        assert masses[matches][0] == masses.max()
        def draw(key):
            return infer_discrete(config_enumerate(model), temperature=1, rng_key=key)(observed)
        a, b = call_public(jax.jit(jax.vmap(draw)), jax.random.split(jax.random.key(82), N), timeout=240)
        a, b = read_array(a), read_array(b)
        assert np.isin(a, [0, 1]).all() and np.isin(b, [0, 1]).all()
        for assignment, mass in zip(assignments, masses):
            frequency((a == assignment[0]) & (b == assignment[1]), mass/masses.sum())
    for temperature in [-1., .5, 2.]:
        with pytest.raises(ValueError):
            call_public(lambda: infer_discrete(config_enumerate(model), temperature=temperature, rng_key=jax.random.key(83))(1.))


def test_f08_t03():
    transition = np.array([[.72, .28], [.19, .81]])
    emission = np.array([[.85, .15], [.12, .88]])
    def model(observations):
        def step(previous, observed):
            state = velnora.sample('state', dist.Categorical(jnp.asarray(transition)[previous]))
            velnora.sample('data', dist.Categorical(jnp.asarray(emission)[state]), obs=observed)
            return state, state
        _, states = scan(step, 0, observations)
        return states
    # Longer scan marginalization works; trajectory recovery is limited by the
    # documented adjoint/Markov-sum-product bug (see the F08 ledger).
    for observations in [np.array([1, 0, 1]), np.array([0, 1, 1, 0])]:
        _, masses = finite_state_table(transition, emission, observations)
        score, _ = call_public(enum_log_density, enum(config_enumerate(model), first_available_dim=-1), (jnp.asarray(observations),), {}, {})
        close(score, np.log(masses.sum()))
    for observations in [np.array([0, 1]), np.array([1, 0])]:
        paths, masses = finite_state_table(transition, emission, observations)
        score, _ = call_public(enum_log_density, enum(config_enumerate(model), first_available_dim=-1), (jnp.asarray(observations),), {}, {})
        close(score, np.log(masses.sum()))
        best = read_array(call_public(infer_discrete(config_enumerate(model), temperature=0, rng_key=jax.random.key(91)), jnp.asarray(observations)))
        assert best.shape == observations.shape
        matches = np.all(paths == best, axis=1)
        assert matches.any()
        assert masses[matches][0] == masses.max()
        def draw(key):
            return infer_discrete(config_enumerate(model), temperature=1, rng_key=key)(jnp.asarray(observations))
        samples = read_array(call_public(jax.jit(jax.vmap(draw)), jax.random.split(jax.random.key(92), N), timeout=240))
        assert samples.shape == (N, len(observations))
        assert np.isin(samples, [0, 1]).all()
        for path, mass in zip(paths, masses):
            frequency(np.all(samples == path, axis=1), mass/masses.sum())


def test_f08_t04():
    tensor = np.linspace(-2., 3., 2*3*4*5).reshape(2, 3, 4, 5)
    first = jnp.array([[0], [2], [1]])
    last = jnp.array([[4, 0]])
    result = call_public(lambda: Vindex(jnp.asarray(tensor))[..., first, :, last])
    expected = np.empty((3, 2, 4))
    for i, selected in enumerate([0, 2, 1]):
        for batch, end in enumerate([4, 0]):
            expected[i, batch] = tensor[batch, selected, :, end]
    assert result.shape == expected.shape
    np.testing.assert_array_equal(read_array(result), expected)
    # Without leading batches, two index batches still broadcast and retain events.
    unbatched = tensor[1]
    result = call_public(lambda: Vindex(jnp.asarray(unbatched))[first, :, last])
    expected = np.stack([np.stack([unbatched[selected, :, end] for end in [4, 0]]) for selected in [0, 2, 1]])
    assert result.shape == expected.shape
    np.testing.assert_array_equal(read_array(result), expected)


def test_f08_t05():
    for alpha, beta in [(1.7, 3.2), (.6, 2.4)]:
        for family, count, value in [('binomial', 7, 2.), ('bernoulli', 1, 0.), ('bernoulli', 1, 1.)]:
            def model():
                with h.collapse():
                    probability = velnora.sample('probability', dist.Beta(alpha, beta))
                    law = dist.Binomial(count, probability) if family == 'binomial' else dist.Bernoulli(probability)
                    velnora.sample('data', law, obs=value)
            score, record = call_public(log_density, model, (), {}, {})
            close(score, stats.betabinom.logpmf(value, count, alpha, beta))
            # Collapse emits an observed probability factor, not a latent draw.
            samples = [site for site in record.values() if site['type'] == 'sample']
            assert samples
            assert all(site['is_observed'] for site in samples)
            traced = call_public(h.trace(model).get_trace)
            assert all(site['is_observed'] for site in traced.values() if site['type'] == 'sample')
