# feature: F20
"""Acceptance checks for nested posterior inference through public entries."""
import pytest
from F20_helpers import (
    jax, jnp, np, dist, stats, special, velnora, NestedSampler,
    call_public, close, read_array, scalar_laws, observed_normal_model,
    run_nested, posterior_outputs, assert_posterior_cdf,
    assert_weighted_and_resampled, summary_evidence, tilted_scalar_case,
    enumerated_vector_model, enumerated_reference, check_additional_priors,
)
from _helpers import read_label


@pytest.fixture(scope='module')
def normal_run():
    return run_nested(observed_normal_model, 230, data=3.)


def test_f20_t01(normal_run):
    # Independent Gaussian conditioning: prior variance 4, noise variance 1.
    law = stats.norm(2.4, np.sqrt(.8))
    assert_weighted_and_resampled(normal_run, law)
    assert_weighted_and_resampled(normal_run, law, grouped=True, seed=84)


def test_f20_t02():
    # Each named scalar family must work on the actual inference path.
    # These two named laws have no icdf in the baseline and cannot enter
    # nested inference. The PRD/plan corrections are recorded in the ledger.
    supported = [row for row in scalar_laws()
                 if row.label not in ('Kumaraswamy', 'Weibull')]
    for index, row in enumerate(supported):
        model, cutoffs, probabilities = tilted_scalar_case(row)
        sampler = run_nested(model, 300+index)
        samples, weights, draws = posterior_outputs(sampler)
        lower, upper = row.oracle.support()
        assert ((samples['x'][weights > 0] >= lower) &
                (samples['x'][weights > 0] <= upper)).all()
        assert ((draws['x'] >= lower) & (draws['x'] <= upper)).all()
        assert_posterior_cdf(samples['x'], weights, cutoffs, probabilities)
        assert_posterior_cdf(draws['x'], np.full(16000, 1/16000),
                             cutoffs, probabilities, .13)
        jax.clear_caches()
    check_additional_priors()


def test_f20_t03(normal_run):
    estimate, _ = summary_evidence(normal_run)
    expected = stats.norm.logpdf(3., 0., np.sqrt(5.))
    assert abs(estimate-expected) < .30
    other = run_nested(observed_normal_model, 231, data=-5.)
    estimate, _ = summary_evidence(other)
    assert abs(estimate-stats.norm.logpdf(-5., 0., np.sqrt(5.))) < .30


def test_f20_t04():
    sampler = run_nested(enumerated_vector_model, 440)
    samples, weights, draws = posterior_outputs(sampler)
    mixture, means, scale = enumerated_reference()
    cutoffs = np.array([-1., -.3, .4, 1., 1.7])
    probabilities = stats.norm.cdf(cutoffs[:, None], means, scale)@mixture
    for result, w in [(samples, weights), (draws, np.full(16000, 1/16000))]:
        x = result['x']
        assert x.shape[1:] == (2,)
        assert (x[w > 0] > 0).all()
        assert_posterior_cdf(np.log(x[:, 0]), w, cutoffs, probabilities, .13)
        assert_posterior_cdf(np.log(x[:, 1]), w,
                             stats.norm.ppf([.1, .5, .9], .4, .6), [.1, .5, .9], .13)
        close(result['derived'], x[:, 0]*x[:, 1])


def test_f20_t05(normal_run):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    _, text = summary_evidence(normal_run)
    assert int(read_label(text, 'samples')) > 0
    assert int(read_label(text, 'likelihood evals')) > 0
    assert float(read_label(text, 'ESS', separator='=')) > 0
    plt.close('all')
    call_public(normal_run.diagnostics, timeout=180)
    figures = [plt.figure(n) for n in plt.get_fignums()]
    assert figures
    # Inspect rendered public plot contents, not a call counter or blank canvas.
    nonconstant = []
    for fig in figures:
        fig.canvas.draw()
        pixels = np.asarray(fig.canvas.buffer_rgba())[..., :3]
        assert pixels.max() > pixels.min()
        nonconstant.extend(line for ax in fig.axes for line in ax.lines
                           if len(line.get_ydata()) > 1
                           and np.ptp(line.get_ydata()) > 0)
    assert nonconstant
    # Identify the named marginal through axis labels, without fixing layout,
    # bin count, styling, or title prose. Read its probability histogram.
    marginal_axes = [ax for fig in figures for ax in fig.axes
                     if ax.get_xlabel() == 'x']
    assert marginal_axes
    for axis in marginal_axes:
        bars = axis.patches
        assert bars
        left = np.array([bar.get_x() for bar in bars])
        widths = np.array([bar.get_width() for bar in bars])
        heights = np.array([bar.get_height() for bar in bars])
        assert (widths > 0).all() and (heights >= 0).all()
        masses = widths*heights
        assert np.isfinite(masses).all() and masses.sum() > 0
        for cutoff, probability in zip(stats.norm.ppf([.25, .5, .75], 2.4, np.sqrt(.8)),
                                       [.25, .5, .75]):
            fraction = np.clip((cutoff-left)/widths, 0, 1)
            assert abs(masses@fraction/masses.sum()-probability) < .15
    plt.close('all')


def test_f20_t06(normal_run):
    # A valid inference in the CPU/x64 environment precedes missing-result checks.
    assert_weighted_and_resampled(normal_run, stats.norm(2.4, np.sqrt(.8)), seed=85)
    sampler = NestedSampler(observed_normal_model)
    for operation in [lambda: sampler.get_samples(jax.random.key(9), 20),
                      sampler.get_weighted_samples, sampler.print_summary,
                      sampler.diagnostics]:
        with pytest.raises(RuntimeError):
            call_public(operation)
