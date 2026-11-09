# feature: F07
"""Acceptance tests for model probabilities and valid inference coordinates."""
import pytest
from scipy import stats
from F01_helpers import (
    jax, jnp, np, dist, close, call_public, read_array,
    check_cdf_samples, N,
)
from F07_helpers import (
    coordinate_model, pack_latents,
    independent_potential, prepare, prior_vector_model, median_coordinate_cdf,
)
import velnora
from velnora import handlers as h
from velnora.infer.util import (
    compute_log_probs, log_density, constrain_fn, unconstrain_fn, initialize_model,
    potential_energy, find_valid_initial_params,
)
from velnora.infer.initialization import (
    init_to_value, init_to_feasible, init_to_sample, init_to_mean,
    init_to_uniform, init_to_median,
)


def test_f07_t01():
    data = jnp.array([[.2, -.7], [1.4, .8], [-.3, 1.1]])
    selected = jnp.array([True, False, True])
    def model(observed, weight=1.):
        x = velnora.sample('latent', dist.Normal(-.3, 1.2))
        with h.scale(scale=weight), h.mask(mask=selected):
            velnora.sample('observed', dist.Normal(x, .9).expand((3, 2)).to_event(1), obs=observed)
            velnora.factor('adjustment', jnp.array([.3, -.8, -.2]))
        velnora.deterministic('derived', x+observed.sum())
    for latent, weight in [(.4, .7), (-.8, 1.9)]:
        expected = {
            'latent': stats.norm.logpdf(latent, -.3, 1.2),
            'observed': np.where(selected, stats.norm.logpdf(data, latent, .9).sum(-1)*weight, 0.),
            'adjustment': np.where(selected, np.array([.3, -.8, -.2])*weight, 0.),
        }
        terms, _ = call_public(compute_log_probs, model, (data,), {'weight': weight}, {'latent': latent}, sum_log_prob=False)
        assert set(terms) == set(expected)
        for name in expected:
            assert np.shape(terms[name]) == np.shape(expected[name])
            close(terms[name], expected[name])
        reduced, _ = call_public(compute_log_probs, model, (data,), {'weight': weight}, {'latent': latent})
        assert set(reduced) == set(expected)
        for name in expected:
            assert np.shape(reduced[name]) == ()
            close(reduced[name], np.sum(expected[name]))
        joint, _ = call_public(log_density, model, (data,), {'weight': weight}, {'latent': latent})
        close(joint, sum(np.sum(v) for v in expected.values()))


def test_f07_t02():
    for values in [dict(positive=1.8, fraction=.27, real=-.6),
                   dict(positive=.7, fraction=.73, real=.9)]:
        z = call_public(unconstrain_fn, coordinate_model, (), {}, values)
        assert set(z) == set(values)
        recovered = call_public(constrain_fn, coordinate_model, (), {}, z, return_deterministic=True)
        for name in values:
            close(recovered[name], values[name])
        close(recovered['derived'], values['positive']*values['fraction']+values['real'])
        expected = independent_potential(pack_latents(z))
        close(call_public(potential_energy, coordinate_model, (), {}, z), expected)
        info = prepare(coordinate_model, init_to_value(values=values))
        restored = call_public(info.postprocess_fn, z)
        for name in (*values, 'derived'):
            close(restored[name], recovered[name])
        close(call_public(info.potential_fn, z), expected)


def test_f07_t03():
    model = prior_vector_model(N)
    supplied = jnp.linspace(.3, 2.4, N)
    info = prepare(model, init_to_value(values={'x': supplied}))
    close(call_public(info.postprocess_fn, info.param_info.z)['x'], supplied)
    for strategy in [init_to_feasible, init_to_mean]:
        info = prepare(model, strategy)
        x = read_array(call_public(info.postprocess_fn, info.param_info.z)['x'])
        assert np.isfinite(x).all() and (x > 0).all()
        assert np.isfinite(read_array(info.param_info.potential_energy)).all()
        if strategy is init_to_mean:
            close(x, np.exp(.7 + 1.8**2/2))
    info = prepare(model, init_to_sample)
    x = read_array(call_public(info.postprocess_fn, info.param_info.z)['x'])
    check_cdf_samples(x, stats.lognorm(1.8, scale=np.exp(.7)).cdf)

    def partial_model():
        velnora.sample('fixed', dist.Gamma(2.7, 1.4))
        velnora.sample('omitted', dist.Normal(8., .3).expand((N,)).to_event(1))
    info = prepare(partial_model, init_to_value(values={'fixed': 1.7}))
    close(call_public(info.postprocess_fn, info.param_info.z)['fixed'], 1.7)
    omitted = read_array(info.param_info.z['omitted'])
    assert ((omitted >= -2) & (omitted <= 2)).all()
    check_cdf_samples(omitted, stats.uniform(-2, 4).cdf)


def test_f07_t04():
    # 2**17 coordinates give a DKW margin of 0.0104 (risk 1e-12): a radius
    # off by 5% (CDF distance 0.025) or a median of 13 or 17 draws instead of
    # the default fifteen (order-statistic CDF distance >= 0.0147) is visible.
    large = 2**17
    model = prior_vector_model(large)
    for strategy, radius in [(None, 2.), (init_to_uniform(), 2.),
                             (init_to_uniform(radius=.65), .65),
                             (init_to_uniform(radius=0.), 0.)]:
        info = prepare(model, strategy)
        z = read_array(info.param_info.z['x'])
        assert z.shape == (large,)
        assert ((z >= -radius) & (z <= radius)).all()
        if radius:
            check_cdf_samples(z, stats.uniform(-radius, 2*radius).cdf)
        else:
            close(z, np.zeros(large))
        restored = read_array(call_public(info.postprocess_fn, info.param_info.z)['x'])
        assert np.isfinite(restored).all() and (restored > 0).all()
    for strategy, count, size in [(init_to_median(), 15, large), (init_to_median(num_samples=2), 2, N)]:
        # Repeat a one-coordinate model independently: a permissible chart may
        # mix coordinates in a larger event, so those coordinates are not IID.
        model = prior_vector_model(1)
        info = prepare(model, strategy)
        def initialize_one(key):
            return initialize_model(key, model, init_strategy=strategy).param_info.z['x'][0]
        z = read_array(call_public(jax.jit(jax.vmap(initialize_one)),
                                   jax.random.split(jax.random.key(71), size), timeout=240))
        assert z.shape == (size,)
        cdf = median_coordinate_cdf(info, model, count)
        # The DKW margin is 0.0104 or 0.042 (nominal tail risk 1e-12).
        # Independent authoring validation bounds baseline quadrature error
        # below 2e-7, negligible compared with the statistical margin.
        check_cdf_samples(z, cdf)


def test_f07_t05():
    for values in [dict(positive=1.8, fraction=.27, real=-.6),
                   dict(positive=.7, fraction=.73, real=.9)]:
        info = prepare(coordinate_model, init_to_value(values=values))
        z = pack_latents(info.param_info.z)
        expected = independent_potential(z)
        close(info.param_info.potential_energy, expected)
        close(call_public(info.potential_fn, info.param_info.z), expected)
        gradient = pack_latents(info.param_info.z_grad)
        assert np.isfinite(z).all() and np.isfinite(gradient).all()
        expected_gradient = []
        for axis in np.eye(len(z)):
            step = 1e-3*axis
            expected_gradient.append((independent_potential(z+step)-independent_potential(z-step))/2e-3)
        # Nested finite differences measure the actual public coordinate chart.
        np.testing.assert_allclose(gradient, expected_gradient, rtol=2e-4, atol=2e-4)
        restored = call_public(info.postprocess_fn, info.param_info.z)
        for name, value in values.items():
            close(restored[name], value)
        close(restored['derived'], values['positive']*values['fraction']+values['real'])
        result, valid = call_public(find_valid_initial_params, jax.random.key(81), coordinate_model,
                                    init_strategy=init_to_value(values=values), timeout=240)
        assert bool(valid)
        start, energy, derivative = result
        close(energy, independent_potential(pack_latents(start)))
        close(pack_latents(derivative), gradient)
    def impossible():
        velnora.sample('x', dist.Normal())
        velnora.factor('impossible', -jnp.inf)
    result, valid = call_public(find_valid_initial_params, jax.random.key(81), impossible, timeout=240)
    assert not bool(valid)
    with pytest.raises(RuntimeError):
        prepare(impossible)
