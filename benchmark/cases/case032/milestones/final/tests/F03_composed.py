# feature: F03
"""Acceptance tests for composed and partially observed probability laws."""
import gc
import warnings

import pytest
from scipy import stats, integrate, special
from F01_helpers import (
    jax, jnp, np, dist, close, read_array, call_public, draws,
    check_cdf_samples, frequency, gaussian_samples, scalar_laws, N,
)
from F02_helpers import c, t


@pytest.fixture(autouse=True)
def release_f03_cache():
    yield
    jax.clear_caches()
    gc.collect()


def test_f03_t01():
    weights = np.array([[.2, .8], [.65, .35]])
    loc = np.array([-1.2, 1.7])
    scale = np.array([.7, 1.3])
    mix = dist.Categorical(probs=jnp.array(weights))
    x = np.array([[-.8], [.4], [2.1]])
    same = dist.MixtureSameFamily(mix, dist.Normal(jnp.array(loc), jnp.array(scale)))
    general = dist.MixtureGeneral(mix, [dist.Normal(loc[0], scale[0]), dist.Laplace(loc[1], scale[1])])
    for law, second in [(same, stats.norm(loc[1], scale[1])), (general, stats.laplace(loc[1], scale[1]))]:
        expected = weights[:, 0] * stats.norm(loc[0], scale[0]).pdf(x) + weights[:, 1] * second.pdf(x)
        assert law.batch_shape == (2,) and law.event_shape == ()
        close(law.log_prob(jnp.array(x)), np.log(expected))
    means = np.array([[-.8, .4], [1.2, -.6]])
    components = dist.Normal(jnp.array(means), .9).to_event(1)
    vector = dist.MixtureSameFamily(dist.Categorical(probs=jnp.array([.3, .7])), components)
    point = np.array([.2, -.4])
    close(vector.log_prob(jnp.array(point)), np.log(np.dot([.3, .7], np.exp(stats.norm.logpdf(point, means, .9).sum(-1)))))
    equivalent = dist.MixtureGeneral(dist.Categorical(probs=jnp.array([.3, .7])), [dist.Normal(jnp.array(m), .9).to_event(1) for m in means])
    close(equivalent.log_prob(jnp.array(point)), np.log(np.dot([.3, .7], np.exp(stats.norm.logpdf(point, means, .9).sum(-1)))))
    invalid = [
        (AssertionError, lambda: dist.MixtureSameFamily(mix, dist.Normal(jnp.zeros(3), 1.))),
        (ValueError, lambda: dist.MixtureGeneral(mix, [dist.Normal()])),
        (ValueError, lambda: dist.MixtureGeneral(dist.Categorical(probs=jnp.array([.4, .6])), [dist.Normal(jnp.zeros(2), 1.).to_event(1), dist.Normal(jnp.zeros(3), 1.).to_event(1)])),
    ]
    for error, make in invalid:
        with pytest.raises(error):
            read_array(make().log_prob(jnp.array(0.)))


def test_f03_t02():
    p = np.array([.23, .77])
    loc = np.array([-2., 1.4])
    scales = np.array([.6, 1.1])
    mixing = dist.Categorical(probs=jnp.array(p))
    laws = [
        (dist.MixtureSameFamily(mixing, dist.Normal(jnp.array(loc), jnp.array(scales))), [stats.norm(loc[i], scales[i]) for i in range(2)]),
        (dist.MixtureGeneral(mixing, [dist.Normal(loc[0], scales[0]), dist.Laplace(loc[1], scales[1])]), [stats.norm(loc[0], scales[0]), stats.laplace(loc[1], scales[1])]),
    ]
    for law, oracles in laws:
        cdf = lambda x: sum(p[i] * oracles[i].cdf(x) for i in range(2))
        check_cdf_samples(draws(law), cdf)
        samples, intermediates = call_public(law.sample_with_intermediates, jax.random.key(78), (N,))
        samples = read_array(samples)
        indices = read_array(intermediates[0])
        assert samples.shape == indices.shape == (N,)
        assert np.isin(indices, [0, 1]).all()
        for i in range(2):
            frequency(indices == i, p[i])
            # Joint events test that labels describe the actual draw, rather than
            # an unrelated categorical draw with the correct marginal frequency.
            for threshold in [-1.3, .2, 2.]:
                frequency((indices == i) & (samples <= threshold), p[i] * oracles[i].cdf(threshold))
            check_cdf_samples(samples[indices == i], oracles[i].cdf)

    # Event-valued components and broadcast mixture batches must also select
    # complete events, rather than independently selecting each coordinate.
    weights = np.array([[.23, .77], [.65, .35]])
    means = np.array([[-1.4, .8], [1.3, -.7]])
    mixing = dist.Categorical(probs=jnp.array(weights))
    vector_laws = [
        dist.MixtureSameFamily(mixing, dist.Normal(jnp.array(means), .8).to_event(1)),
        dist.MixtureGeneral(mixing, [dist.Normal(jnp.array(m), .8).to_event(1) for m in means]),
    ]
    for law in vector_laws:
        samples, intermediates = call_public(law.sample_with_intermediates, jax.random.key(56), (N,))
        samples, indices = read_array(samples), read_array(intermediates[0])
        assert samples.shape == (N, 2, 2) and indices.shape == (N, 2)
        assert np.isin(indices, [0, 1]).all()
        for batch in range(2):
            for component in range(2):
                frequency(indices[:, batch] == component, weights[batch, component])
                gaussian_samples(samples[indices[:, batch] == component, batch], means[component], .8**2*np.eye(2))


def test_f03_t03():
    families = {'Normal', 'Cauchy', 'Laplace', 'Logistic', 'SoftLaplace', 'StudentT', 'Gamma'}
    for row in scalar_laws():
        if row.label not in families:
            continue
        a, b = row.oracle.ppf([.19, .79])
        # Omitted and explicit infinite bounds exercise the same conditional law.
        bounds = [(a, None), (None, b), (a, b)]
        # Gamma explicit infinite endpoints are excluded: the original feeds
        # them directly to incomplete-gamma evaluation / bisection (see ledger).
        if row.label != "Gamma":
            bounds += [(-np.inf, b), (a, np.inf)]
        for low, high in bounds:
            kwargs = dict(low=low, high=high)
            law = (dist.TruncatedGamma(3.4, 1.7, **kwargs) if row.label == 'Gamma'
                   else dist.TruncatedDistribution(row.law, **kwargs))
            lo = -np.inf if low is None else low
            hi = np.inf if high is None else high
            fl, fh = row.oracle.cdf([lo, hi])
            point = row.oracle.ppf(fl + (fh-fl)*np.array([.17, .51, .88]))
            close(law.log_prob(jnp.array(point)), row.oracle.logpdf(point)-np.log(fh-fl))
            samples = draws(law)
            assert ((samples >= lo) & (samples <= hi)).all()
            check_cdf_samples(samples, lambda x: (row.oracle.cdf(x)-fl)/(fh-fl))


def test_f03_t04():
    low, high = .7, 3.8
    for alpha in [-3.2, -1., -.4, 2.1]:
        law = dist.DoublyTruncatedPowerLaw(alpha, low, high, validate_args=True)
        # Independent quadrature of the defining proportional density, not the
        # product's antiderivative or its own CDF.
        mass = integrate.quad(lambda x: x**alpha, low, high, epsabs=1e-11)[0]
        points = np.array([.9, 1.6, 3.1])
        close(law.log_prob(jnp.array(points)), alpha*np.log(points)-np.log(mass))
        samples = draws(law)
        assert ((samples >= low) & (samples <= high)).all()
        for point in points:
            frequency(samples <= point, integrate.quad(lambda x: x**alpha, low, point)[0]/mass)
    for alpha in [-2.3, -4.1]:
        law = dist.LowerTruncatedPowerLaw(alpha, low, validate_args=True)
        oracle = stats.pareto(-alpha-1, scale=low)
        close(law.log_prob(jnp.array([.9, 1.6, 3.1])), oracle.logpdf([.9, 1.6, 3.1]))
        samples = draws(law)
        assert (samples >= low).all()
        check_cdf_samples(samples, oracle.cdf)
    for alpha in [-1., -.5]:
        with pytest.raises(ValueError):
            draws(dist.LowerTruncatedPowerLaw(alpha, low, validate_args=True), n=2)
    for make in [lambda: dist.LowerTruncatedPowerLaw(-2., 0., validate_args=True),
                 lambda: dist.DoublyTruncatedPowerLaw(np.inf, low, high, validate_args=True),
                 lambda: dist.DoublyTruncatedPowerLaw(-2., -.2, high, validate_args=True)]:
        with pytest.raises(ValueError):
            draws(make(), n=2)


def test_f03_t05():
    for base, oracle in [(dist.Normal(.3, 1.2), stats.norm(.3, 1.2)), (dist.Exponential(1.4), stats.expon(scale=1/1.4))]:
        x = np.array([.2, .8, 1.6])
        for cls, cumulative in [(dist.LeftCensoredDistribution, oracle.cdf), (dist.RightCensoredDistribution, oracle.sf)]:
            law = cls(base, censored=jnp.array([False, True, True]))
            close(law.log_prob(jnp.array(x)), [oracle.logpdf(x[0]), *np.log(cumulative(x[1:]))])
        # Neither indicator: both sides of the specified close-endpoint rule.
        lo = np.array([.8, .8, .8, .8, .8, .8])
        hi = np.array([1.6, 1.6, 1.6, .8, .8+4e-6, .8+3e-5])
        left = jnp.array([True, False, True, False, False, False])
        right = jnp.array([False, True, True, False, False, False])
        mass = oracle.cdf(hi)-oracle.cdf(lo)
        expected = [oracle.cdf(hi[0]), oracle.sf(lo[1]), 1-mass[2], oracle.pdf(lo[3]), oracle.pdf(lo[4]), mass[5]]
        law = dist.IntervalCensoredDistribution(base, left, right)
        close(law.log_prob(jnp.array(np.stack([lo, hi], -1))), np.log(expected))

    # Discrete censoring must use cumulative masses, including only the upper
    # endpoint of an interval, rather than treating point observations as density.
    oracle = stats.poisson(2.1)
    base = dist.Poisson(2.1)
    for cls, probability in [(dist.LeftCensoredDistribution, oracle.cdf), (dist.RightCensoredDistribution, oracle.sf)]:
        law = cls(base, censored=jnp.array([False, True, True]))
        close(law.log_prob(jnp.array([1, 2, 4])), np.log([oracle.pmf(1), *probability([2, 4])]))
    points = jnp.array([[2, 2], [1, 3], [1, 3], [1, 3], [1, 3]])
    law = dist.IntervalCensoredDistribution(base, jnp.array([0, 0, 1, 0, 1], dtype=bool), jnp.array([0, 0, 0, 1, 1], dtype=bool))
    interval = oracle.cdf(3)-oracle.cdf(1)
    close(law.log_prob(points), np.log([oracle.pmf(2), interval, oracle.cdf(3), oracle.sf(1), 1-interval]))


def test_f03_t06():
    base = dist.Exponential(1.4)
    oracle = stats.expon(scale=1/1.4)
    # Singly censored ignored endpoints may be outside support or unordered.
    points = jnp.array([[-3., .8], [4., .8], [.8, -3.], [.8, .2], [.8, .8+4e-6]])
    left = jnp.array([1, 1, 0, 0, 1], dtype=bool)
    right = jnp.array([0, 0, 1, 1, 1], dtype=bool)
    law = dist.IntervalCensoredDistribution(base, left, right, validate_args=True)
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter('always')
        result = read_array(law.log_prob(points))
    assert not records
    close(result, np.log([oracle.cdf(.8), oracle.cdf(.8), oracle.sf(.8), oracle.sf(.8), 1-(oracle.cdf(.8+4e-6)-oracle.cdf(.8))]))
    # Every row is a refusal the PRD states: an endpoint outside the base support,
    # or unordered interval endpoints. Equal endpoints are ordered and are not one.
    bad_points = jnp.array([[.8, -.2], [-.2, .8], [.8, .2], [.8, .2], [-.2, -.2], [.8, -.2]])
    bad = dist.IntervalCensoredDistribution(base, jnp.array([1, 0, 0, 1, 0, 1], dtype=bool), jnp.array([0, 1, 0, 1, 0, 1], dtype=bool), validate_args=True)
    with pytest.warns(UserWarning):
        result = read_array(bad.log_prob(bad_points))
    assert np.isneginf(result).all()


def test_f03_t07():
    for cls in [dist.LeftCensoredDistribution, dist.RightCensoredDistribution, dist.IntervalCensoredDistribution]:
        for enabled in [False, True]:
            kwargs = (dict(left_censored=enabled, right_censored=enabled) if cls is dist.IntervalCensoredDistribution else dict(censored=enabled))
            law = cls(dist.Normal(.3, 1.2), validate_args=True, **kwargs)
            samples = draws(law)
            assert samples.shape == (N,)
            check_cdf_samples(samples, stats.norm(.3, 1.2).cdf)
            with pytest.raises(TypeError):
                draws(cls(dist.ZeroInflatedPoisson(gate=.3, rate=1.2), validate_args=True, **kwargs), n=2)


def test_f03_t08():
    gate = .31
    nb = stats.nbinom(2.4, 2.4/(2.4+1.7))
    rows = [
        (dist.ZeroInflatedDistribution(dist.Binomial(5, probs=.4), gate=gate), stats.binom(5, .4)),
        (dist.ZeroInflatedDistribution(dist.Binomial(5, probs=.4), gate_logits=special.logit(gate)), stats.binom(5, .4)),
        (dist.ZeroInflatedPoisson(gate=gate, rate=1.7), stats.poisson(1.7)),
        (dist.ZeroInflatedNegativeBinomial2(1.7, 2.4, gate=gate), nb),
    ]
    for law, oracle in rows:
        points = np.arange(5)
        expected = (1-gate)*oracle.pmf(points)
        expected[0] += gate
        close(law.log_prob(jnp.array(points)), np.log(expected))
        samples = draws(law)
        assert ((samples >= 0) & (samples == np.floor(samples))).all()
        for point in points:
            frequency(samples <= point, gate+(1-gate)*oracle.cdf(point))


def test_f03_t09():
    gate = .27
    rows = [
        (dist.HurdlePoisson(gate=gate, rate=1.1), stats.poisson(1.1), True),
        (dist.HurdleNegativeBinomial2(gate=gate, mean=1.7, concentration=2.4), stats.nbinom(2.4, 2.4/(2.4+1.7)), True),
        (dist.HurdleGamma(gate, 2.3, 1.4), stats.gamma(2.3, scale=1/1.4), False),
        (dist.HurdleLogNormal(gate, .2, .8), stats.lognorm(.8, scale=np.exp(.2)), False),
    ]
    for law, oracle, discrete in rows:
        points = np.array([0., 1., 2., 4.])
        p0 = oracle.pmf(0) if discrete else 0.
        logp = oracle.logpmf(points[1:]) if discrete else oracle.logpdf(points[1:])
        close(law.log_prob(jnp.array(points)), np.r_[np.log(gate), np.log1p(-gate)+logp-np.log1p(-p0)])
        samples = draws(law)
        assert (samples >= 0).all()
        if discrete:
            assert (samples == np.floor(samples)).all()
        frequency(samples == 0, gate)
        for point in [1., 2., 4.]:
            frequency(samples <= point, gate+(1-gate)*(oracle.cdf(point)-p0)/(1-p0))
    oracle = stats.norm(.8, 1.3)
    folded = dist.FoldedDistribution(dist.Normal(.8, 1.3))
    points = np.array([.2, .9, 2.1])
    close(folded.log_prob(jnp.array(points)), np.log(oracle.pdf(points)+oracle.pdf(-points)))
    samples = draws(folded)
    assert (samples >= 0).all()
    check_cdf_samples(samples, lambda x: oracle.cdf(x)-oracle.cdf(-x))


def test_f03_t10():
    a, b = np.array([2.3, 3.4]), np.array([4.2, 1.8])
    oracle = stats.beta(a, b)
    points = np.array([[.2, .6], [.7, .3], [.4, .8]])
    for rho in [0., .65]:
        corr = np.array([[1., rho], [rho, 1.]])
        z = stats.norm.ppf(oracle.cdf(points))
        expected = stats.multivariate_normal(cov=corr).logpdf(z)-stats.norm.logpdf(z).sum(-1)+oracle.logpdf(points).sum(-1)
        for kwargs in [dict(correlation_matrix=jnp.array(corr)), dict(correlation_cholesky=jnp.array(np.linalg.cholesky(corr)))]:
            for law in [dist.GaussianCopula(dist.Beta(jnp.array(a), jnp.array(b)), **kwargs), dist.GaussianCopulaBeta(jnp.array(a), jnp.array(b), **kwargs)]:
                assert law.event_shape == (2,)
                close(law.log_prob(jnp.array(points)), expected)
                # Compile the complete public sampling request so numerical
                # iteration does not incur eager dispatch for every operation.
                sample = jax.jit(law.sample, static_argnames=("sample_shape",))
                samples = read_array(call_public(sample, jax.random.key(2027),
                                                 sample_shape=(N,), timeout=240))
                assert samples.shape == (N, 2)
                assert ((samples > 0) & (samples < 1)).all()
                for i in range(2):
                    check_cdf_samples(samples[:, i], stats.beta(a[i], b[i]).cdf)
                gaussian_samples(stats.norm.ppf(oracle.cdf(samples)), np.zeros(2), corr)


def test_f03_t11():
    loc = np.array([.3, -.5, 1.2])
    base = dist.Normal(jnp.array(loc), .8)
    points = jnp.array([[.1, .2, .7], [.5, -.8, 1.4]])
    for mask in [False, True, jnp.array([True, False, True])]:
        law = base.mask(mask)
        close(law.log_prob(points), np.where(mask, stats.norm.logpdf(points, loc, .8), 0.))
        samples = draws(law)
        gaussian_samples(samples, loc, .8**2*np.eye(3))
    improper = dist.ImproperUniform(c.positive, (2,), (3,))
    assert improper.batch_shape == (2,) and improper.event_shape == (3,)
    close(improper.log_prob(jnp.ones((4, 2, 3))), np.zeros((4, 2)))
    with pytest.raises(NotImplementedError):
        draws(improper, n=2)
    weights = jnp.array([-.7, 1.2])
    unit = dist.Unit(weights)
    assert unit.event_shape == (0,) and unit.batch_shape == (2,)
    samples = draws(unit, n=4)
    assert samples.shape == (4, 2, 0)
    close(unit.log_prob(jnp.array(samples)), np.broadcast_to(weights, (4, 2)))


def test_f03_t12():
    loc, scale = .3, .8
    # Ordered nonlinear then affine transformations have an independent
    # log-normal oracle and distinguish reverse composition and missing volume.
    law = dist.TransformedDistribution(dist.Normal(loc, scale), [t.ExpTransform(), t.AffineTransform(-.4, 2.3)])
    points = np.array([.1, 1.2, 4.5])
    oracle = stats.lognorm(scale, loc=-.4, scale=2.3*np.exp(loc))
    close(law.log_prob(jnp.array(points)), oracle.logpdf(points))
    check_cdf_samples(draws(law), oracle.cdf)
    # A matrix transform broadcasts the base batch and declares a new event shape.
    means = np.array([[-.3], [.6]])
    scales = np.array([[.7, 1.1, 1.4, .9]])
    offset = np.array([.2, -.4, .6, .1])
    multiplier = np.array([1.3, -.8, 2., .6])
    base = dist.Normal(jnp.array(means), jnp.array(scales)).to_event(1)
    law = dist.TransformedDistribution(base, [t.AffineTransform(jnp.array(offset), jnp.array(multiplier)), t.ReshapeTransform((2, 2), (4,))])
    assert law.batch_shape == (2,) and law.event_shape == (2, 2)
    points = np.array([[[.2, -.1], [.8, .4]], [[-.4, .6], [.2, -.3]]])
    transformed_mean = means*multiplier+offset
    transformed_scale = scales*np.abs(multiplier)
    close(law.log_prob(jnp.array(points)), stats.norm.logpdf(points.reshape(2, 4), transformed_mean, transformed_scale).sum(-1))
    samples = draws(law)
    assert samples.shape == (N, 2, 2, 2)
    for i in range(2):
        gaussian_samples(samples[:, i].reshape(N, 4), transformed_mean[i], np.diag(transformed_scale[0]**2))

    broadcast = dist.TransformedDistribution(dist.Normal(.3, .7), t.AffineTransform(jnp.array([[-.2], [.6]]), jnp.array([[.8, 1.3, 1.9]])))
    assert broadcast.batch_shape == (2, 3) and broadcast.event_shape == ()
    means = np.array([[-.2], [.6]]) + .3*np.array([[.8, 1.3, 1.9]])
    scales = np.broadcast_to(.7*np.array([[.8, 1.3, 1.9]]), (2, 3))
    close(broadcast.log_prob(.4), stats.norm.logpdf(.4, means, scales))
    samples = draws(broadcast)
    assert samples.shape == (N, 2, 3)
    gaussian_samples(samples.reshape(N, 6), means.ravel(), np.diag(scales.ravel()**2))
