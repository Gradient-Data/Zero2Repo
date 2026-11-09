# feature: F10
"""Acceptance tests for automatic posterior guide construction."""
import pytest
from F10_helpers import (jax, jnp, np, dist, close, read_array, call_public,
    gaussian_samples, check_cdf_samples, stats, velnora, h, ag,
    NORMALS, bind_guide, fit_guide, normal_model, configured_normal,
    posterior_array, check_normal_draws, fitted_normal_cdf)
from velnora.infer import Predictive
from velnora.distributions.transforms import biject_to
from velnora.distributions import constraints
from F02_helpers import volume


def test_f10_t01():
    # Every family binds a genuine constrained, vector-valued model.
    for cls in (*NORMALS, ag.AutoDelta, ag.AutoLaplaceApproximation,
                ag.AutoIAFNormal, ag.AutoBNAFNormal, ag.AutoDAIS,
                ag.AutoSurrogateLikelihoodDAIS, ag.AutoSemiDAIS):
        batched = cls in (*NORMALS[-2:], ag.AutoSemiDAIS)
        def model():
            if batched:
                with velnora.plate('groups', 2):
                    x = velnora.sample('x', dist.LogNormal(0., 1.).expand((2,)).to_event(1))
            else:
                x = velnora.sample('x', dist.LogNormal(0., 1.).expand((2,)).to_event(1))
            velnora.sample('obs', dist.Normal(jnp.log(x), .5).to_event(jnp.ndim(x)),
                           obs=jnp.broadcast_to(jnp.array([1.5, -.9]), x.shape))
        options = {'num_flows': 2} if cls is ag.AutoIAFNormal else {}
        if cls is ag.AutoSurrogateLikelihoodDAIS:
            options['surrogate_model'] = model
        elif cls is ag.AutoSemiDAIS:
            options.update(local_model=model, global_guide=None)
        guide = cls(model, **options)
        params = fit_guide(model, guide)
        samples = call_public(guide.sample_posterior, jax.random.key(72), params,
                              sample_shape=(16, 32), timeout=600)
        x = read_array(samples['x'])
        assert x.shape == (16, 32) + ((2, 2) if batched else (2,))
        assert np.isfinite(x).all() and (x > 0).all()
        # Analytic log-coordinate posterior mean = observation / 1.25.
        # The point guide optimizes density in the original domain instead.
        target = np.array([1.2, -.72]) - (.2 if cls is ag.AutoDelta else 0.)
        np.testing.assert_allclose(np.log(x).mean(axis=(0, 1)),
                                   np.broadcast_to(target, x.shape[2:]), atol=.22, rtol=0)
        if cls is not ag.AutoDelta:
            np.testing.assert_allclose(np.log(x).var(axis=(0, 1)), .2, atol=.09, rtol=0)
            for i in range(2):
                fitted_normal_cdf(np.log(x)[..., i].ravel(), target[i], np.sqrt(.2))
        jax.clear_caches()


def test_f10_t02():
    for cls in NORMALS:
        guide, params, loc, cov = configured_normal(cls)
        check_normal_draws(posterior_array(guide, params), loc, cov)
        record = call_public(h.trace(h.seed(h.substitute(guide, data=params), 5)).get_trace)
        # Read the complete guide score, including auxiliary and volume terms.
        site = record['x']
        expected = stats.multivariate_normal.logpdf(read_array(site['value']), loc, cov) if loc.ndim == 1 else np.array([
            stats.multivariate_normal.logpdf(read_array(site['value'])[i], loc[i], cov[i]) for i in range(2)])
        close(sum(jnp.sum(part['fn'].log_prob(part['value'])) for part in record.values() if part['type'] == 'sample'), np.sum(expected))


def test_f10_t03():
    q = np.array([.13, .5, .86])
    for cls in NORMALS:
        guide, params, loc, cov = configured_normal(cls, positive=True)
        chart = biject_to(constraints.positive)
        median = call_public(guide.median, params)['x']
        assert median.shape == loc.shape
        close(median, chart(jnp.asarray(loc)))
        if cls not in NORMALS[-2:]:
            expected = chart(jnp.asarray(loc + stats.norm.ppf(q)[:, None]*np.sqrt(np.diag(cov))))
            quantiles = call_public(guide.quantiles, params, q)['x']
            assert quantiles.shape == (len(q),) + loc.shape
            close(quantiles, expected)
    point = ag.AutoDelta(normal_model(positive=True))
    params = bind_guide(point)
    params['x_auto_loc'] = jnp.array([1.7, .35])
    close(call_public(point.median, params)['x'], [1.7, .35])
    close(posterior_array(point, params), np.broadcast_to([1.7, .35], (8192, 2)))


def test_f10_t04():
    prior_cov = np.array([[1.7, .5], [.5, 1.1]])
    design = np.array([[1., .3], [-.4, 1.2]])
    data = np.array([1.6, -.8])
    noise = .6
    cov = np.linalg.inv(np.linalg.inv(prior_cov) + design.T @ design/noise**2)
    mode = cov @ design.T @ data/noise**2
    def model():
        x = velnora.sample('x', dist.MultivariateNormal(jnp.zeros(2), jnp.asarray(prior_cov)))
        velnora.sample('obs', dist.Normal(jnp.asarray(design)@x, noise).to_event(1), obs=jnp.asarray(data))
    guide = ag.AutoLaplaceApproximation(model)
    params = fit_guide(model, guide, 800)
    np.testing.assert_allclose(call_public(guide.median, params)['x'], mode, atol=.003, rtol=0)
    gaussian_samples(posterior_array(guide, params), read_array(params['auto_loc']), cov)
    q = np.array([.17, .5, .91])
    close(call_public(guide.quantiles, params, q)['x'], read_array(params['auto_loc']) + stats.norm.ppf(q)[:, None]*np.sqrt(np.diag(cov)))


def test_f10_t05():
    def model():
        velnora.sample('left', dist.Normal(0., 2.))
        velnora.sample('right', dist.LogNormal(0., 1.).expand((2,)).to_event(1))
    combined = ag.AutoGuideList(model)
    combined.append(ag.AutoNormal(h.block(model, expose=['left']), prefix='a'))
    combined.append(ag.AutoDelta(h.block(model, expose=['right']), prefix='b'))
    params = bind_guide(combined)
    params.update(left_a_loc=jnp.array(1.3), left_a_scale=jnp.array(.7),
                  right_b_loc=jnp.array([.4, 2.1]))
    samples = call_public(combined.sample_posterior, jax.random.key(1), params, sample_shape=(8192,))
    assert {'left', 'right'} <= samples.keys()
    check_cdf_samples(read_array(samples['left']), stats.norm(1.3, .7).cdf)
    close(samples['right'], np.broadcast_to([.4, 2.1], (8192, 2)))
    for cls, options in ((ag.AutoDAIS, {}),
                         (ag.AutoSurrogateLikelihoodDAIS, {'surrogate_model': model}),
                         (ag.AutoSemiDAIS, {'local_model': model, 'global_guide': None})):
        with pytest.raises(ValueError):
            bad = ag.AutoGuideList(model)
            bad.append(cls(model, **options))
            bind_guide(bad)
    def deterministic_model():
        x = velnora.sample('x', dist.Normal(0., 1.))
        velnora.deterministic('square', x*x)
    with pytest.raises(ValueError):
        bad = ag.AutoGuideList(deterministic_model)
        bad.append(ag.AutoDiagonalNormal(deterministic_model))
        bind_guide(bad)


def test_f10_t06():
    def discrete():
        velnora.sample('x', dist.Bernoulli(.4))
    def empty():
        velnora.sample('obs', dist.Normal(0., 1.), obs=.3)
    for cls in NORMALS:
        guide, params, loc, cov = configured_normal(cls)
        check_normal_draws(posterior_array(guide, params), loc, cov)
        with pytest.raises(ValueError):
            bind_guide(cls(discrete))
        if cls is not ag.AutoNormal:
            with pytest.raises(RuntimeError):
                bind_guide(cls(empty))
        for scale in (0., -.3):
            with pytest.raises(ValueError):
                bind_guide(cls(normal_model(), init_scale=scale))

    for cls, options in ((ag.AutoDelta, {}), (ag.AutoLaplaceApproximation, {}),
                         (ag.AutoIAFNormal, {}), (ag.AutoBNAFNormal, {}),
                         (ag.AutoDAIS, {}),
                         (ag.AutoSurrogateLikelihoodDAIS, {'surrogate_model': normal_model()}),
                         (ag.AutoSemiDAIS, {'local_model': normal_model()})):
        with pytest.raises(ValueError):
            bind_guide(cls(discrete, **options))
        if cls not in (ag.AutoDelta, ag.AutoSemiDAIS):
            with pytest.raises(RuntimeError):
                bind_guide(cls(empty, **options))


def test_f10_t07():
    # Conjugate Gaussian observations give an independent posterior and predictive law.
    # Training accuracy is checked separately from Monte Carlo sampling accuracy.
    data = jnp.array([1.4, 1.8, 1.6, 1.2, 1.7, 1.3, 1.9, 1.5])
    def full():
        x = velnora.sample('x', dist.Normal(0., 1.))
        with velnora.plate('rows', 8):
            velnora.sample('obs', dist.Normal(x, 1.), obs=data)
    def subsampled():
        x = velnora.sample('x', dist.Normal(0., 1.))
        with velnora.plate('rows', 8, subsample_size=4):
            batch = velnora.subsample(data, event_dim=0)
            velnora.sample('obs', dist.Normal(x, 1.), obs=batch)
    for model, cls, options in ((full, ag.AutoDAIS, {}),
                               (subsampled, ag.AutoSurrogateLikelihoodDAIS, {'surrogate_model': full})):
        guide = cls(model, K=4, **options)
        params = fit_guide(model, guide, 2500)
        x = posterior_array(guide, params)
        assert abs(x.mean()-float(data.sum()/9)) < .16
        assert abs(x.var()-1/9) < .06
        fitted_normal_cdf(x, float(data.sum()/9), np.sqrt(1/9))
        def forecast():
            x = velnora.sample('x', dist.Normal(0., 1.))
            velnora.sample('future', dist.Normal(x, 1.))
        pred = call_public(Predictive(forecast, posterior_samples={'x': jnp.asarray(x)}), jax.random.key(91))
        assert abs(read_array(pred['future']).mean()-float(data.sum()/9)) < .18
        assert abs(read_array(pred['future']).var()-10/9) < .15
        jax.clear_caches()
    def global_model():
        value = velnora.sample('global', dist.Normal(0., 1.))
        velnora.sample('global_obs', dist.Normal(value, .6), obs=-.8)
        return value
    def local_model(global_value):
        with velnora.plate('rows', 8, subsample_size=4):
            batch = velnora.subsample(data, event_dim=0)
            local = velnora.sample('x', dist.Normal(0., 1.))
            velnora.sample('obs', dist.Normal(local, 1.), obs=batch)
    def semi_model():
        local_model(global_model())
    global_guide = ag.AutoNormal(global_model, prefix='global_q')
    guide = ag.AutoSemiDAIS(semi_model, local_model, global_guide, K=4)
    params = fit_guide(semi_model, guide, 3000)
    # Pin public subsample identities so local posterior comparisons are meaningful.
    with h.substitute(data={'rows': jnp.array([0, 2, 4, 6])}):
        samples = call_public(guide.sample_posterior, jax.random.key(9), params, sample_shape=(8192,), timeout=600)
    local = read_array(samples['x'])
    assert local.shape == (8192, 4)
    np.testing.assert_allclose(local.mean(0), read_array(data)[[0, 2, 4, 6]]/2, atol=.20, rtol=0)
    np.testing.assert_allclose(local.var(0), .5, atol=.16, rtol=0)
    global_draws = read_array(samples['global'])
    assert abs(global_draws.mean() - (-.8/1.36)) < .12
    assert abs(global_draws.var() - .36/1.36) < .10
    fitted_normal_cdf(global_draws, -.8/1.36, np.sqrt(.36/1.36))
    for i, row in enumerate([0, 2, 4, 6]):
        fitted_normal_cdf(local[:, i], float(data[row]/2), np.sqrt(.5))
    correlation = np.corrcoef(np.column_stack([global_draws, local]), rowvar=False)
    assert np.max(np.abs(correlation - np.eye(5))) < .15


def test_f10_t08():
    for cls in NORMALS:
        guide, params, loc, cov = configured_normal(cls, positive=True, defaults=True)
        close(cov, np.broadcast_to(np.eye(2)*.01, cov.shape))
        values = posterior_array(guide, params)
        chart = biject_to(constraints.positive)
        check_normal_draws(read_array(chart.inv(jnp.asarray(values))), loc, cov)
        record = call_public(h.trace(h.seed(h.substitute(guide, data=params), 8)).get_trace)
        site = record['x']
        value = read_array(site['value'])
        coordinate = read_array(chart.inv(jnp.asarray(value)))
        correction = volume(chart, coordinate)
        if loc.ndim == 1:
            expected = stats.multivariate_normal.logpdf(coordinate, loc, cov) - correction
        else:
            expected = sum(stats.multivariate_normal.logpdf(coordinate[i], loc[i], cov[i]) for i in range(2)) - correction
        close(sum(jnp.sum(part['fn'].log_prob(part['value'])) for part in record.values() if part['type'] == 'sample'), expected)
