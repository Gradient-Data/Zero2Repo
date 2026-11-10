# feature: F12
"""Acceptance tests for posterior chains and conditional composition."""
import pytest
from F12_helpers import (jax, jnp, np, dist, close, read_array, call_public,
    velnora, stats, collect, observed_normal_model, beta_model, check_law, pair_model,
    update_x, check_pair, mixed_model, check_mixed, data_model)
from velnora.infer.gibbs import discrete_latent_sites
from velnora.infer import (MCMC, HMC, NUTS, BarkerMH, SA, AIES, ESS,
    Gibbs, CustomGibbs, DiscreteGibbs, DiscreteHMCGibbs, HMCGibbs, MixedHMC, HMCECS, init_to_value)


def test_continuous_posterior():
    for cls in (HMC, NUTS, BarkerMH):
        s = collect(cls(beta_model)).get_samples()
        assert ((read_array(s['p']) > 0) & (read_array(s['p']) < 1)).all()
        check_law(s['p'], stats.beta(20., 5.))
        close(s['derived'], s['p']**2)


def test_potential_and_derivative_free():
    # Absolute-value target has a cusp and needs no continuous derivative.
    potential = lambda x: jnp.abs(x-2.)/.7
    for cls in (SA, AIES, ESS):
        options = {} if cls is SA else dict(num_chains=12, chain_method='vectorized')
        initial = jnp.array(-1.) if cls is SA else jnp.linspace(-2., 5., 12)
        m = MCMC(cls(potential_fn=potential), num_warmup=700,
                 num_samples=80000 if cls is SA else 8000, progress_bar=False, **options)
        replicates = []
        for seed in (52, 103, 217):
            call_public(m.run, jax.random.key(seed), init_params=initial, timeout=600)
            replicates.append(read_array(m.get_samples()))
        check_law(np.concatenate(replicates), stats.laplace(2., .7))
    for cls in (HMC, NUTS, SA):
        with pytest.raises(ValueError):
            m = MCMC(cls(potential_fn=lambda x: x*x/2), num_warmup=2,
                     num_samples=2, progress_bar=False)
            call_public(m.run, jax.random.key(0))


def test_collection_and_diagnostics():
    potential = lambda x: (x-1.7)**2/(2*.6**2)
    m = MCMC(NUTS(potential_fn=potential), num_warmup=120,
             num_samples=2402, thinning=3, progress_bar=False)
    call_public(m.warmup, jax.random.key(1), init_params=jnp.array(-4.),
                collect_warmup=True, extra_fields=('potential_energy',), timeout=600)
    assert m.get_samples(group_by_chain=True).shape == (1, 40)
    call_public(m.run, jax.random.key(2), extra_fields=('potential_energy', 'accept_prob', 'diverging'), timeout=600)
    x = m.get_samples()
    assert x.shape == (800,)
    assert m.get_samples(group_by_chain=True).shape == (1, 800)
    fields = m.get_extra_fields()
    close(fields['potential_energy'], potential(x))
    a = read_array(fields['accept_prob'])
    assert a.shape == (800,) and ((0 <= a) & (a <= 1)).all()
    d = read_array(fields['diverging'])
    assert d.shape == (800,) and np.isin(d, [False, True]).all()
    assert abs(read_array(x).mean()-1.7) < .15
    default = MCMC(NUTS(observed_normal_model), num_warmup=20, num_samples=31, progress_bar=False)
    call_public(default.run, jax.random.key(17))
    assert default.get_samples(group_by_chain=True)['x'].shape == (1, 31)


def test_multiple_chain_modes():
    for method in ('sequential', 'vectorized'):
        m = collect(NUTS(observed_normal_model), samples=2400, num_chains=3,
                    chain_method=method, extra_fields=('diverging',))
        grouped, flat = m.get_samples(True), m.get_samples()
        assert grouped['x'].shape == (3, 2400)
        close(flat['x'], grouped['x'].reshape(-1))
        for chain in grouped['x']:
            check_law(chain, stats.norm(2.4, np.sqrt(.8)), cdf_tolerance=.10)
        assert not np.array_equal(read_array(grouped['x'][0]), read_array(grouped['x'][1]))
        assert m.get_extra_fields(True)['diverging'].shape == (3, 2400)


def test_warmup_continuation_and_changed_inputs():
    m = MCMC(NUTS(observed_normal_model), num_warmup=300, num_samples=2400, progress_bar=False)
    call_public(m.warmup, jax.random.key(11), 3., timeout=600)
    state = m.post_warmup_state
    assert state is not None
    call_public(m.run, jax.random.key(12), 3., timeout=600)
    check_law(m.get_samples()['x'], stats.norm(2.4, np.sqrt(.8)), cdf_tolerance=.10)
    last = m.last_state
    m.post_warmup_state = last
    call_public(m.run, jax.random.key(13), 3., timeout=600)
    s = m.get_samples()
    check_law(s['x'], stats.norm(2.4, np.sqrt(.8)), cdf_tolerance=.10)
    close(s['derived'], 2*s['x']+3.)
    # Same public state and key must yield the same continuation even in a new runner.
    other = MCMC(NUTS(observed_normal_model, init_strategy=init_to_value(values={'x': -100.})),
                 num_warmup=0, num_samples=2400, progress_bar=False)
    other.post_warmup_state = last
    call_public(other.run, jax.random.key(13), 3., timeout=600)
    close(other.get_samples()['x'], s['x'])
    m.post_warmup_state = None
    call_public(m.run, jax.random.key(14), -3., timeout=600)
    changed = m.get_samples()
    check_law(changed['x'], stats.norm(-2.4, np.sqrt(.8)), cdf_tolerance=.10)
    close(changed['derived'], 2*changed['x']-3.)


def test_discrete_and_marginalized_posterior():
    check_mixed(collect(NUTS(lambda: mixed_model(True))).get_samples(), True)
    for kernel in (MixedHMC(HMC(mixed_model)), DiscreteHMCGibbs(NUTS(mixed_model))):
        check_mixed(collect(kernel, samples=4000).get_samples())
    check_pair(collect(HMCGibbs(NUTS(pair_model), update_x, ['x'])).get_samples())


def test_composed_conditional_blocks():
    configurations = [
        Gibbs([(NUTS(pair_model), ['x']), (NUTS(pair_model), ['y'])]),
        Gibbs([(CustomGibbs(update_x), ['x']), (NUTS(pair_model), None)]),
        Gibbs([(Gibbs([(CustomGibbs(update_x), ['x']), (NUTS(pair_model), ['y'])]), None)])]
    for kernel in configurations:
        check_pair(collect(kernel, samples=4000).get_samples())
    auto = Gibbs([(DiscreteGibbs(mixed_model), discrete_latent_sites), (NUTS(mixed_model), None)])
    check_mixed(collect(auto, samples=4000).get_samples())


def test_partition_rejections():
    invalid = [
        [(NUTS(pair_model), ['x']), (NUTS(pair_model), ['x', 'y'])],
        [(NUTS(pair_model), ['x'])],
        [(NUTS(pair_model), ['obs']), (NUTS(pair_model), None)],
        [(NUTS(pair_model), []), (NUTS(pair_model), None)],
        [(NUTS(pair_model), None), (NUTS(pair_model), None)],
        [(NUTS(lambda: mixed_model(True)), ['z']), (NUTS(lambda: mixed_model(True)), None)]]
    # Use a single model identity so the final arm tests enumeration ownership.
    enum = lambda: mixed_model(True)
    invalid[-1] = [(NUTS(enum), ['z']), (NUTS(enum), None)]
    for blocks in invalid:
        with pytest.raises(ValueError):
            collect(Gibbs(blocks), warmup=2, samples=2)
    legal = collect(Gibbs([(NUTS(enum), None)]), samples=2400)
    check_mixed(legal.get_samples(), True)


def test_incompatible_blocks_and_updates():
    def dynamic():
        x = velnora.sample('x', dist.Normal())
        velnora.sample('y', dist.Uniform(x, x+1))
    for blocks, args in [
        ([(NUTS(pair_model), ['x']), (NUTS(observed_normal_model), None)], ()),
        ([(NUTS(mixed_model), None)], ()),
        ([(NUTS(data_model), None)], (jnp.arange(16.),)),
        ([(NUTS(dynamic), ['y']), (NUTS(dynamic), None)], ())]:
        with pytest.raises(ValueError):
            collect(Gibbs(blocks), *args, warmup=2, samples=2)
    for result in ({}, {'x': jnp.array(0.), 'extra': jnp.array(1.)}):
        def bad(rng_key, gibbs_sites, hmc_sites):
            return result
        with pytest.raises(ValueError):
            collect(Gibbs([(CustomGibbs(bad), ['x']), (NUTS(pair_model), None)]), warmup=2, samples=2)
    check_pair(collect(Gibbs([(CustomGibbs(update_x), ['x']), (NUTS(pair_model), None)])).get_samples())


def test_energy_conserving_subsampling():
    data = jnp.linspace(-2., 6., 80)
    kernel = HMCECS(NUTS(data_model), proxy=HMCECS.taylor_proxy({'x': jnp.array(2.)}))
    m = collect(kernel, data, extra_fields=('z.batch',))
    s = m.get_samples()
    check_law(s['x'], stats.norm(float(data.sum()/(80+.25)), np.sqrt(1/(80+.25))))
    indices = read_array(m.get_extra_fields()['z.batch'])
    assert indices.shape == (3*6000, 8)
    assert np.issubdtype(indices.dtype, np.integer)
    assert ((indices >= 0) & (indices < 80)).all()
    assert np.unique(indices, axis=0).shape[0] > 1


def test_collection_and_ensemble_rejections():
    for options in (dict(num_warmup=-1), dict(num_warmup=1.5), dict(thinning=0),
                    dict(thinning=1.5), dict(num_samples=0), dict(num_samples=2.5),
                    dict(num_samples=2, thinning=3)):
        config = dict(num_warmup=2, num_samples=2)
        config.update(options)
        with pytest.raises(ValueError):
            m = MCMC(NUTS(observed_normal_model), progress_bar=False, **config)
            call_public(m.run, jax.random.key(0))
    for cls in (AIES, ESS):
        for count, method, initial_count in [(1, 'vectorized', 1), (3, 'vectorized', 3),
                (4, 'sequential', 4), (4, 'vectorized', 2)]:
            with pytest.raises((AssertionError, ValueError)):
                m = MCMC(cls(potential_fn=lambda x: x*x/2), num_warmup=2,
                         num_samples=2, num_chains=count, chain_method=method, progress_bar=False)
                call_public(m.run, jax.random.key(0), init_params=jnp.arange(float(initial_count)))
        move = cls.StretchMove() if cls is AIES else cls.RandomMove()
        legal = MCMC(cls(potential_fn=lambda x: x*x/2, moves={move: 1.}), num_warmup=0,
                     num_samples=1, thinning=1, num_chains=2,
                     chain_method='vectorized', progress_bar=False)
        call_public(legal.run, jax.random.key(0), init_params=jnp.array([-1., 1.]))
        assert legal.get_samples(True).shape == (2, 1)


def test_external_probability_integration():
    from tensorflow_probability.substrates.jax import distributions as tfd
    from velnora.contrib.tfp.distributions import TFPDistribution
    from velnora.contrib.tfp.mcmc import HamiltonianMonteCarlo
    external = tfd.Beta(2., 3.)
    wrapped = TFPDistribution[tfd.Beta](2., 3.)
    points = jnp.array([.2, .45, .8])
    close(wrapped.log_prob(points), stats.beta.logpdf(read_array(points), 2., 3.))
    def model():
        p = velnora.sample('p', external)
        velnora.sample('obs', dist.Binomial(20, p), obs=18.)
    for kernel in (NUTS(model), HamiltonianMonteCarlo(model, step_size=.25, num_leapfrog_steps=5)):
        s = collect(kernel).get_samples()['p']
        assert ((read_array(s) > 0) & (read_array(s) < 1)).all()
        check_law(s, stats.beta(20., 5.))
