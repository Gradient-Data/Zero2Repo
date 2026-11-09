# feature: F14
"""Acceptance coverage for posterior diagnostics and variational calibration."""
import pytest
from F01_helpers import gaussian_samples
from F09_helpers import empty_guide
from F14_helpers import (
    jax, jnp, np, dist, stats, close, call_public, read_array,
    velnora, optim, Trace_ELBO, calibration, routed_model, routed_guide,
    check_routed_result, lag_covariances, rhat_definition,
    stan_ess_definition, check_shortest_interval,
)
from _helpers import capture_output
from velnora.diagnostics import (
    summary, print_summary, hpdi, autocovariance, autocorrelation,
    effective_sample_size, gelman_rubin, split_gelman_rubin,
)
from velnora.infer.calibration import vsbc_diagnostic
from velnora.infer.importance import psis_diagnostic
from velnora.infer.hmc_util import consensus, parametric, parametric_draws


def test_summary_data_and_printed_components():
    x = np.random.default_rng(821).normal(size=(3, 31, 2, 2))
    x[1] += .8
    flat = x.reshape(-1, 2, 2)
    expected = dict(mean=flat.mean(0), std=flat.std(0, ddof=1),
                    median=np.median(flat, axis=0), n_eff=stan_ess_definition(x),
                    r_hat=rhat_definition(np.concatenate([x[:, :15], x[:, -15:]])))
    result = call_public(summary, {'theta': x})['theta']
    for name, value in expected.items():
        assert result[name].shape == (2, 2)
        close(result[name], value)
    check_shortest_interval(flat, np.stack([result['5.0%'], result['95.0%']]), .9)
    with capture_output() as captured:
        call_public(print_summary, {'theta': x})
    lines = [line.split() for line in captured.stdout.getvalue().splitlines() if line.strip()]
    columns = ['mean', 'std', 'median', '5.0%', '95.0%', 'n_eff', 'r_hat']
    assert lines[0] == columns
    rows = {row[0]: row[1:] for row in lines[1:]}
    assert set(rows) == {f'theta[{i},{j}]' for i in range(2) for j in range(2)}
    for i in range(2):
        for j in range(2):
            values = np.array([float(v) for v in rows[f'theta[{i},{j}]']])
            assert values.shape == (7,)
            # The printed shell exposes two fractional digits; layout is free.
            np.testing.assert_allclose(values, [result[c][i,j] for c in columns], atol=.0051, rtol=0)
    x[0, 1, 0, 1] = np.nan
    result = call_public(summary, {'theta': x})['theta']
    assert np.isnan(result['median'][0, 1])
    close(result['median'][1], np.median(x.reshape(-1, 2, 2), axis=0)[1])
    ungrouped = call_public(summary, {'theta': flat}, group_by_chain=False)['theta']
    close(ungrouped['mean'], flat.mean(0))
    close(ungrouped['r_hat'], rhat_definition(np.stack([flat[:46], flat[-46:]])))


def test_shortest_empirical_intervals():
    x = np.array([[0., 1., 2., 3., 9., 20., 40., 70.],
                  [4., 5., 6., 7., 8., 9., 10., 11.]])
    for prob in [.375, .625]:
        interval = call_public(hpdi, x, prob=prob, axis=1)
        check_shortest_interval(x, interval, prob, axis=1)
        result = call_public(summary, {'x': x.T}, prob=prob, group_by_chain=False)['x']
        close(result['median'], np.median(x, axis=1))
        lower, upper = f'{50*(1-prob):.1f}%', f'{50*(1+prob):.1f}%'
        check_shortest_interval(x.T, np.stack([result[lower], result[upper]]), prob)


def test_lag_covariance_and_correlation():
    x = np.random.default_rng(72).normal(size=(2, 9, 3)) + np.arange(9)[None,:,None]
    for bias in [True, False]:
        expected = lag_covariances(x, axis=1, bias=bias)
        actual = call_public(autocovariance, x, axis=1, bias=bias)
        assert actual.shape == x.shape
        close(actual, expected)
        close(call_public(autocorrelation, x, axis=1, bias=bias), expected/expected[:, :1])
    close(call_public(autocovariance, x, axis=1), lag_covariances(x, 1))
    close(call_public(autocorrelation, x, axis=1), lag_covariances(x, 1)/lag_covariances(x, 1)[:, :1])
    close(call_public(autocovariance, x[:, :, 0].T, axis=0), lag_covariances(x[:, :, 0].T))


def test_chain_convergence_and_ess():
    x = np.random.default_rng(29).normal(size=(4, 19, 2))
    x[:, :, 0] += np.arange(19)*.3
    x[:, :, 1] += np.arange(4)[:, None]
    close(call_public(gelman_rubin, x), rhat_definition(x))
    halves = np.concatenate([x[:, :9], x[:, -9:]])
    close(call_public(split_gelman_rubin, x), rhat_definition(halves))
    for bias in [True, False]:
        close(call_public(effective_sample_size, x, bias=bias), stan_ess_definition(x, bias))
        close(call_public(effective_sample_size, x[:1], bias=bias), stan_ess_definition(x[:1], bias))
    close(call_public(effective_sample_size, x), stan_ess_definition(x))
    for fn, shape in [(gelman_rubin, (1, 5)), (gelman_rubin, (2, 1)),
                      (split_gelman_rubin, (2, 3)), (effective_sample_size, (2, 1))]:
        with pytest.raises(AssertionError):
            call_public(fn, np.ones(shape))


def test_gaussian_subposterior_combination():
    rng = np.random.default_rng(11)
    arrays = [rng.multivariate_normal(m, c, size=8192) for m, c in [
        ([1., -2.], [[1., .7], [.7, 2.]]),
        ([-1., 3.], [[3., -.4], [-.4, .5]]),
        ([.4, .2], [[.4, .1], [.1, 1.3]])]]
    sub = [{'z': jnp.array(x)} for x in arrays]
    for diagonal in [False, True]:
        covs = [np.diag(np.var(x, axis=0, ddof=1)) if diagonal else np.cov(x.T) for x in arrays]
        precisions = [np.linalg.inv(c) for c in covs]
        cov = np.linalg.inv(sum(precisions))
        mean = cov @ sum(p @ x.mean(0) for p, x in zip(precisions, arrays))
        actual_mean, actual_cov = call_public(parametric, sub, diagonal=diagonal)
        close(actual_mean, mean)
        close(actual_cov, np.diag(cov) if diagonal else cov)
        expected = sum((cov @ p @ x.T).T for p, x in zip(precisions, arrays))
        close(call_public(consensus, sub, diagonal=diagonal)['z'], expected)
        draws = call_public(parametric_draws, sub, 8192, diagonal=diagonal, rng_key=jax.random.key(18))['z']
        assert draws.shape == (8192, 2)
        gaussian_samples(draws, mean, cov)


def test_pareto_importance_tail_and_degenerate_weights():
    def guide(observation, alpha):
        shape = velnora.param('shape', 2.)
        velnora.sample('z', dist.Pareto(1., shape))
    def model(observation, alpha):
        velnora.sample('z', dist.Pareto(1., alpha))
        velnora.sample('data', dist.Normal(0., 1.), obs=observation)
    # Under q=Pareto(1,b), p/q is proportional to z**(b-a),
    # an exact Pareto tail with shape 1-a/b. This oracle is independent of
    # the estimator. Large tails and a .25 margin allow estimation variation.
    for alpha in [2.4, .9]:
        actual = call_public(psis_diagnostic, jax.random.key(81), {'shape': jnp.array(3.)},
                             model, guide, .3, alpha, num_particles=200000, timeout=240)
        assert abs(actual-(1-alpha/3)) < .25
    def exact():
        velnora.sample('z', dist.Normal(0., 1.))
    with pytest.warns(UserWarning):
        actual = call_public(psis_diagnostic, jax.random.key(2), {},
                             exact, exact, num_particles=1024)
    assert actual == np.inf
    with pytest.raises(ValueError):
        call_public(psis_diagnostic, jax.random.key(2), {}, model, guide, .3, 2., num_particles=1)


def test_componentwise_calibration_ranks_and_symmetry():
    offsets = jnp.array([[0., -1.], [1., 0.]])
    def model(obs=None):
        z = velnora.sample('z', dist.Normal(jnp.zeros((2, 2)), 1.).to_event(2))
        velnora.sample('obs', dist.Delta(z, event_dim=2), obs=obs)
    def guide(obs=None):
        velnora.sample('z', dist.Delta(obs+offsets, event_dim=2))
    result = calibration(model, guide, num_simulations=6, num_samples=32)
    assert set(result.param_names) == {'z'}
    expected = np.broadcast_to(np.array([[0, 32], [0, 0]]), (6, 2, 2))
    np.testing.assert_array_equal(result.ranks['z'], expected)
    close(result.probabilities['z'], expected/32)
    for index in np.ndindex(2, 2):
        p = result.probabilities['z'][(slice(None),)+index]
        ks = stats.ks_2samp(p, 1-p, method='asymp')
        close(result.ks_stats['z'][index], ks.statistic)
        close(result.ks_pvalues['z'][index], ks.pvalue)
    def centered_guide(obs=None):
        velnora.sample('z', dist.Normal(obs, .3).to_event(1))
    result = calibration(routed_model, centered_guide)
    assert np.max(np.abs(result.probabilities['z']-.5)) < .10
    for i in range(2):
        p = result.probabilities['z'][:, i]
        ks = stats.ks_2samp(p, 1-p, method='asymp')
        close(result.ks_stats['z'][i], ks.statistic)
        close(result.ks_pvalues['z'][i], ks.pvalue)


def test_calibration_refits_and_training_budget():
    def model(obs=None):
        z = velnora.sample('z', dist.Normal(0., .1))
        velnora.sample('obs', dist.Normal(z, .00001), obs=obs)
    def guide(obs=None):
        center = velnora.param('center', 6.)
        velnora.sample('z', dist.Normal(center, .1))
    def run(steps):
        return call_public(vsbc_diagnostic, jax.random.PRNGKey(95), model, guide,
                           optim.SGD(.5/(100+1e10)), Trace_ELBO(num_particles=64),
                           observed_sites=['obs'], num_simulations=8,
                           num_svi_steps=steps, num_samples=2048, timeout=240)
    short, fitted = run(1), run(24)
    assert np.max(short.probabilities['z']) < .05
    # Each generating value is within negligible noise of its observation.
    # Re-fitting centers the narrow guide there, rather than at a previous
    # simulation's observation. Broad bounds cover optimization/MC variation.
    assert np.all((fitted.probabilities['z'] > .2) & (fitted.probabilities['z'] < .8))
    close(fitted.ranks['z']/2048, fitted.probabilities['z'])


def test_calibration_simulated_data_routing():
    check_routed_result(calibration(routed_model, routed_guide))
    def alias_model(data=None, scale=1.):
        z = velnora.sample('z', dist.Normal(jnp.array([-2., 3.])*scale, 1.).to_event(1))
        velnora.sample('obs', dist.Normal(z, .00001).to_event(1), obs=data)
    def alias_guide(data=None, scale=1.):
        return routed_guide(data)
    check_routed_result(calibration(alias_model, alias_guide, scale=2.))
    def container_model(data=None):
        z = velnora.sample('z', dist.Normal(jnp.array([-2., 3.]), 1.).to_event(1))
        for i, name in enumerate(['left', 'right']):
            velnora.sample(name, dist.Normal(z[i], .00001), obs=None if data is None else data[name])
    def container_guide(data=None):
        obs = jnp.stack([data['left'], data['right']])
        routed_guide(obs)
    def convert(sim_data, *args, **kwargs):
        return (), {'data': sim_data}
    check_routed_result(calibration(container_model, container_guide,
                        data={'left': 500., 'right': -500.},
                        observed_sites=['left', 'right'], simulated_data_to_args=convert))


def test_calibration_rejects_invalid_requests():
    check_routed_result(calibration(routed_model, routed_guide))
    for options in [dict(observed_sites=['missing']), dict(observed_sites=['z', 'obs']),
                    dict(observed_sites=None), dict(num_simulations=1),
                    dict(num_svi_steps=0), dict(num_samples=1),
                    dict(simulated_data_to_args=3),
                    dict(simulated_data_to_args=lambda data, *a, **k: data),
                    dict(simulated_data_to_args=lambda data, *a, **k: (3, {})),
                    dict(simulated_data_to_args=lambda data, *a, **k: ((), 3))]:
        with pytest.raises(ValueError):
            calibration(routed_model, routed_guide, **options)
    def discrete_model(obs=None):
        z = velnora.sample('z', dist.Bernoulli(.4))
        velnora.sample('obs', dist.Normal(z, 1.), obs=obs)
    with pytest.raises(ValueError):
        calibration(discrete_model, empty_guide)
    def ambiguous(first=None, second=None):
        routed_model(first)
    with pytest.raises(ValueError):
        calibration(ambiguous, routed_guide)
    def alias(data=None):
        routed_model(data)
    with pytest.raises(ValueError):
        calibration(alias, routed_guide, jnp.ones(2))
