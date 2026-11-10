# feature: F20
"""Public nested inference drivers and independent posterior references."""
from F01_helpers import (
    jax, jnp, np, dist, read_array, call_public, close, scalar_laws,
)
from F08_helpers import finite_assignment_table
from F12_helpers import observed_normal_model
from _helpers import capture_output, read_label
from scipy import stats, integrate, special
import velnora
from velnora.contrib.nested_sampling import NestedSampler


def run_nested(model, seed, *args, live=1200, **kwargs):
    sampler = NestedSampler(model,
        constructor_kwargs={'num_live_points': live, 'max_samples': 60000},
        termination_kwargs={'dlogZ': .001})
    call_public(sampler.run, jax.random.key(seed), *args, timeout=900, **kwargs)
    return sampler


def posterior_outputs(sampler, seed=83, count=16000, grouped=False):
    samples, log_weights = call_public(sampler.get_weighted_samples)
    samples = {k: read_array(v) for k, v in samples.items()}
    log_weights = read_array(log_weights)
    assert log_weights.ndim == 1
    assert not np.isnan(log_weights).any() and not np.isposinf(log_weights).any()
    weights = np.exp(log_weights-special.logsumexp(log_weights))
    assert np.isfinite(weights).all() and weights.sum() > 0
    assert all(len(v) == len(weights) for v in samples.values())
    draws = call_public(sampler.get_samples, jax.random.key(seed), count,
                        group_by_chain=grouped)
    draws = {k: read_array(v) for k, v in draws.items()}
    for key, value in draws.items():
        assert value.shape == ((1, count) if grouped else (count,)) + samples[key].shape[1:]
        assert np.isfinite(value).all()
    return samples, weights, draws


def assert_posterior_cdf(values, weights, cutoffs, probabilities, tolerance=.10):
    """Coarse distribution accuracy on independent reference quantiles.

    Weighted nested points are not IID: no IID sample-size claim is made for
    them. Large live populations and broad probability bands protect against
    integration randomness; resampling adds at most .03 with probability
    below 1e-12 (Hoeffding at 16000 draws). The ledger requests explicit
    probabilistic accuracy bands rather than fixing a random trajectory.
    """
    values = np.asarray(values)
    assert values.ndim == 1
    assert np.isfinite(values[weights > 0]).all()
    for cutoff, probability in zip(cutoffs, probabilities):
        actual = np.dot(weights, values <= cutoff)
        assert abs(actual-probability) < tolerance, (actual, probability, cutoff)


def assert_weighted_and_resampled(sampler, law, name='x', seed=83, grouped=False):
    samples, weights, draws = posterior_outputs(sampler, seed, grouped=grouped)
    cutoffs = law.ppf([.1, .25, .5, .75, .9])
    assert_posterior_cdf(samples[name], weights, cutoffs, [.1, .25, .5, .75, .9])
    flat = draws[name].reshape(-1)
    assert_posterior_cdf(flat, np.full(len(flat), 1/len(flat)), cutoffs,
                         [.1, .25, .5, .75, .9], .13)
    return samples, weights, draws


def summary_evidence(sampler):
    with capture_output() as output:
        call_public(sampler.print_summary)
    # Read the fixed public carrier; prose and the error estimate are not judged.
    value = read_label(output.stdout.getvalue(), 'logZ', separator='=')
    estimate, separator, uncertainty = value.partition(' +- ')
    assert separator
    return float(estimate), output.stdout.getvalue()


def tilted_scalar_case(row):
    law, oracle = row.law, row.oracle
    center = oracle.ppf(.8)
    noise = (oracle.ppf(.75)-oracle.ppf(.25))*.35
    def model():
        x = velnora.sample('x', law)
        velnora.sample('obs', dist.Normal(x, noise), obs=center)
    def integrand(q):
        return stats.norm.pdf(center, oracle.ppf(q), noise)
    evidence = integrate.quad(integrand, 0, 1, epsabs=1e-10, limit=250)[0]
    qs = [.25, .5, .75, .9]
    probabilities = [integrate.quad(integrand, 0, q, epsabs=1e-10,
                                   limit=250)[0]/evidence for q in qs]
    return model, oracle.ppf(qs), probabilities


def enumerated_vector_model(observed=1.8):
    z = velnora.sample('z', dist.Categorical(jnp.array([.15, .35, .5])),
                       infer={'enumerate': 'parallel'})
    x = velnora.sample('x', dist.LogNormal(jnp.array([-.3, .4]), .6).to_event(1))
    velnora.sample('obs', dist.Normal(jnp.log(x[0])+1.5*z, .4), obs=observed)
    velnora.deterministic('derived', x[0]*x[1])


def enumerated_reference(observed=1.8):
    _, mass = finite_assignment_table([3], lambda z:
        [.15, .35, .5][z[0]]*stats.norm.pdf(observed, -.3+1.5*z[0], np.sqrt(.52)))
    mixture = mass/mass.sum()
    variance = 1/(1/.36+1/.16)
    means = variance*(-.3/.36+(observed-1.5*np.arange(3))/.16)
    return mixture, means, np.sqrt(variance)


def check_additional_priors():
    """Non-scalar laws, finite priors, and compositional prior wrappers."""
    for index, (law, support, prior_mass) in enumerate([
        (dist.DiscreteUniform(-1, 3), np.arange(-1, 4), np.full(5, .2)),
        (dist.Bernoulli(.3), np.arange(2), np.array([.7, .3])),
        (dist.Categorical(jnp.array([.2, .3, .5])), np.arange(3), np.array([.2, .3, .5])),
    ]):
        def model():
            x = velnora.sample('x', law)
            velnora.sample('obs', dist.Normal(x, .7), obs=1.7)
        masses = prior_mass*stats.norm.pdf(1.7, support, .7)
        probabilities = np.cumsum(masses/masses.sum())
        sampler = run_nested(model, 520+index)
        samples, weights, draws = posterior_outputs(sampler)
        for result, w in [(samples, weights), (draws, np.full(16000, 1/16000))]:
            assert np.isin(result['x'][w > 0], support).all()
            assert_posterior_cdf(result['x'], w, support, probabilities, .13)
        jax.clear_caches()

    def simplex_model():
        p = velnora.sample('p', dist.Dirichlet(jnp.array([2., 3., 4.])))
        velnora.sample('obs', dist.Categorical(p).expand((15,)).to_event(1),
                       obs=jnp.full((15,), 2))
    sampler = run_nested(simplex_model, 530)
    samples, weights, draws = posterior_outputs(sampler)
    for result, w in [(samples, weights), (draws, np.full(16000, 1/16000))]:
        p = result['p']
        assert p.shape[1:] == (3,)
        assert (p[w > 0] > 0).all()
        close(p.sum(-1), np.ones(len(p)))
        for dim, alpha in enumerate([2., 3., 19.]):
            law = stats.beta(alpha, 24-alpha)
            assert_posterior_cdf(p[:, dim], w, law.ppf([.1, .5, .9]), [.1, .5, .9], .13)
    jax.clear_caches()

    covariance = np.array([[1., .65], [.65, 1.4]])
    def vector_model():
        x = velnora.sample('x', dist.MultivariateNormal(jnp.array([-.4, .7]),
                            covariance_matrix=jnp.asarray(covariance)))
        velnora.sample('obs', dist.Normal(x[0], .5), obs=1.5)
    mean = np.array([-.4, .7])+covariance[:, 0]/1.25*(1.5+.4)
    posterior_cov = covariance-np.outer(covariance[:, 0], covariance[0])/1.25
    sampler = run_nested(vector_model, 540)
    samples, weights, draws = posterior_outputs(sampler)
    for result, w in [(samples, weights), (draws, np.full(16000, 1/16000))]:
        assert result['x'].shape[1:] == (2,)
        for direction in [np.array([1., 0.]), np.array([0., 1.]), np.array([1., -1.])]:
            law = stats.norm(direction@mean, np.sqrt(direction@posterior_cov@direction))
            assert_posterior_cdf(result['x']@direction, w, law.ppf([.1, .5, .9]), [.1, .5, .9], .13)
    jax.clear_caches()

    def wrapped_model():
        law = dist.TransformedDistribution(dist.Normal(-.2, .8), dist.transforms.ExpTransform())
        x = velnora.sample('x', law.expand((2,)).to_event(1))
        velnora.sample('obs', dist.Normal(jnp.log(x), .4).to_event(1), obs=jnp.array([1., -.8]))
    sampler = run_nested(wrapped_model, 550)
    samples, weights, draws = posterior_outputs(sampler)
    for result, w in [(samples, weights), (draws, np.full(16000, 1/16000))]:
        assert result['x'].shape[1:] == (2,)
        assert (result['x'][w > 0] > 0).all()
        for dim, observed in enumerate([1., -.8]):
            variance = 1/(1/.64+1/.16)
            law = stats.norm(variance*(-.2/.64+observed/.16), np.sqrt(variance))
            assert_posterior_cdf(np.log(result['x'][:, dim]), w,
                                 law.ppf([.1, .5, .9]), [.1, .5, .9], .13)
    jax.clear_caches()
