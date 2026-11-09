# feature: F12
"""Prediction, weighted prediction, empirical summaries and chain diagnostics."""
import numpy as np
import torch
import velnora
from velnora.infer import Predictive, WeighedPredictive
from velnora.infer.mcmc.util import summary
from velnora.ops import stats
from _helpers import invoke, isolated_state
from F01_helpers import assert_close, assert_frequency, SAMPLE_COUNT
from F12_helpers import (binary_prediction, binary_guide, weighted_prediction,
                         weighted_evidence)


def test_f12_t01():
    with isolated_state(seed=1201, dtype=torch.float64):
        # Test actual conditional laws, not a particular random sequence.
        for parallel in (False, True):
            latent = torch.arange(4000).remainder(2).double()
            out = invoke(Predictive(binary_prediction, {'z': latent},
                         return_sites=('z', 'y', 'score', '_RETURN'),
                         parallel=parallel)).value
            z, y = out['z'].reshape(-1), out['y'].reshape(-1)
            assert_close(z, latent)
            assert_close(out['score'].reshape(-1), 3*z+y)
            assert_close(out['_RETURN'].reshape(-1, 3), torch.stack((z, y, 3*z+y), -1))
            # Each group has 2000 independent bounded draws: Hoeffding gives
            # <= 2 exp(-32.4) per arm at margin .09, < 1e-12 combined.
            for value in (0., 1.):
                assert abs(y[z == value].mean().item()-(.15+.7*value)) < .09
        for guide, probability in ((None, .3), (binary_guide, .65)):
            out = invoke(Predictive(binary_prediction, guide=guide,
                         num_samples=SAMPLE_COUNT, parallel=True,
                         return_sites=('z', 'y', 'score', '_RETURN'))).value
            z, y = out['z'].reshape(-1), out['y'].reshape(-1)
            assert_frequency(z == 1, probability)
            assert_frequency((z == 1) & (y == 1), probability*.85)
            assert_frequency((z == 0) & (y == 1), (1-probability)*.15)
            assert_close(out['score'].reshape(-1), 3*z+y)
            assert_close(out['_RETURN'].reshape(-1, 3), torch.stack((z, y, 3*z+y), -1))


def test_f12_t02():
    with isolated_state(seed=1202, dtype=torch.float64):
        latent = torch.tensor([0., 1., 1., 0., 1.])
        ordinary = invoke(Predictive(binary_prediction, {'z': latent}, parallel=True)).value
        assert set(ordinary) == {'y', 'score'}
        guided = invoke(Predictive(binary_prediction, guide=binary_guide,
                        num_samples=5, parallel=True)).value
        assert set(guided) == {'z', 'y', 'score'}
        selected = invoke(Predictive(binary_prediction, {'z': latent},
                          return_sites=('z', '_RETURN'), parallel=True)).value
        assert set(selected) == {'z', '_RETURN'}
        assert_close(selected['z'].reshape(-1), latent)
        assert_close(selected['_RETURN'][..., 0].reshape(-1), latent)
        construction = invoke(Predictive, binary_prediction,
                              kwargs={'posterior_samples': {'z': latent},
                                      'num_samples': 2, 'return_sites': ('z',),
                                      'parallel': True})
        assert any(issubclass(w.category, UserWarning) for w in construction.warnings)
        conflicted = invoke(construction.value).value
        assert conflicted['z'].shape[0] == len(latent)
        assert_close(conflicted['z'].reshape(-1), latent)


def test_f12_t03():
    with isolated_state(seed=1203, dtype=torch.float64):
        # Empty posterior is not a second source; both valid source forms work.
        for kwargs in ({'posterior_samples': {}, 'guide': binary_guide, 'num_samples': 7},
                       {'posterior_samples': {'z': torch.ones(7)}}):
            out = invoke(Predictive(binary_prediction, parallel=True, **kwargs)).value
            assert out['y'].shape[0] == 7
            assert_close(out['score'].reshape(-1).remainder(3), out['y'].reshape(-1))
        for kwargs in ({}, {'posterior_samples': {}},
                       {'guide': binary_guide},
                       {'posterior_samples': {'z': torch.ones(7)}, 'guide': binary_guide}):
            rejected = invoke(Predictive, binary_prediction, kwargs=kwargs,
                              allowed_exceptions=(ValueError,))
            assert isinstance(rejected.exception, ValueError)


def test_f12_t04():
    with isolated_state(seed=1204, dtype=torch.float64):
        for separate in (False, True):
            model = weighted_prediction if separate else weighted_evidence
            prediction = WeighedPredictive(model, guide=binary_guide,
                                           num_samples=SAMPLE_COUNT, parallel=True)
            out = invoke(prediction, kwargs={'model_guide': weighted_evidence}).value
            z = out.samples['z'].reshape(-1)
            assert_frequency(z == 1, .65)
            proposal = np.where(z.numpy() == 1, .65, .35)
            joint = np.where(z.numpy() == 1, .3*.8, .7*.2)
            assert out.log_weights.shape == (SAMPLE_COUNT,)
            assert_close(out.guide_log_prob, np.log(proposal))
            assert_close(out.model_log_prob, np.log(joint))
            assert_close(out.log_weights, np.log(joint/proposal))
            weights = out.log_weights.softmax(0)
            # For this binary proposal, the weighted estimate is a smooth
            # function of its frequency. The already checked .025 frequency
            # margin bounds the posterior mean error by .028; .04 is looser.
            posterior_probability = .3*.8/(.3*.8+.7*.2)
            assert abs((weights*z).sum().item()-posterior_probability) < .04
            if separate:
                y = out.samples['y'].reshape(-1)
                assert_frequency((z == 1) & (y == 1), .65*.9)
                assert_frequency((z == 0) & (y == 1), .35*.1)
                assert abs((weights*y).sum().item()-(.1+.8*posterior_probability)) < .06


def test_f12_t05():
    with isolated_state(dtype=torch.float64):
        values = torch.tensor([[9., -2.], [0., 5.], [1., 12.], [2., 7.],
                               [3., 1.], [15., 3.], [4., 8.], [5., 2.]])
        probs = [0., .17, .5, .83, 1.]
        for dim, samples in ((0, values), (1, values.T)):
            expected = np.quantile(samples.numpy(), probs, axis=dim)
            if dim == 1:
                expected = expected.T
            assert_close(invoke(stats.quantile, samples, probs, kwargs={'dim': dim}).value, expected)
            assert_close(invoke(stats.quantile, samples, .37, kwargs={'dim': dim}).value,
                         np.quantile(samples.numpy(), .37, axis=dim))
            mass = .5
            expected = np.quantile(samples.numpy(), [.25, .75], axis=dim)
            if dim == 1:
                expected = expected.T
            assert_close(invoke(stats.pi, samples, mass, kwargs={'dim': dim}).value, expected)
            interval = invoke(stats.hpdi, samples, mass, kwargs={'dim': dim}).value
            interval = interval if dim == 0 else interval.T
            ordered = np.sort(values.numpy(), axis=0)
            rank_span = int(len(values)*mass)
            # Accept every tied shortest interval, independently per event.
            for event in range(2):
                pairs = [(ordered[i, event], ordered[i+rank_span, event])
                         for i in range(len(values)-rank_span)]
                shortest = min(right-left for left, right in pairs)
                assert any(np.allclose(interval[:, event].numpy(), pair)
                           for pair in pairs if pair[1]-pair[0] == shortest)
        for grouped in (False, True):
            samples = values.reshape(2, 4, 2) if grouped else values
            report = invoke(summary, {'v': samples},
                            kwargs={'prob': .5, 'group_by_chain': grouped}).value
            assert_close(report['v']['mean'], values.mean(0))
            assert_close(report['v']['std'], np.std(values.numpy(), axis=0, ddof=1))
            scaled = invoke(summary, {'v': 3*samples+7},
                            kwargs={'prob': .5, 'group_by_chain': grouped}).value
            assert torch.all(report['v']['std'] > 0)
            assert_close(scaled['v']['std'], 3*report['v']['std'])


def test_f12_t06():
    with isolated_state(seed=1206, dtype=torch.float64):
        independent = torch.randn(4, 2048, 2)
        correlated = torch.empty_like(independent)
        correlated[:, 0] = independent[:, 0]
        for index in range(1, independent.size(1)):
            correlated[:, index] = .95*correlated[:, index-1]+independent[:, index]
        separated = independent + torch.tensor([-6., -2., 2., 6.])[:, None, None]
        drifting = independent.clone()
        drifting[:, :1024] -= 4
        drifting[:, 1024:] += 4
        ess = invoke(stats.effective_sample_size, independent).value
        dependent_ess = invoke(stats.effective_sample_size, correlated).value
        assert ess.shape == dependent_ess.shape == (2,)
        assert torch.isfinite(ess).all() and torch.isfinite(dependent_ess).all()
        assert torch.all(ess > dependent_ess)
        # Calibrate the unit, not just the ordering. IID draws retain the full
        # information count; stationary AR(1) mean variance is inflated by
        # (1 + rho) / (1 - rho). Broad margins admit finite-chain estimation
        # and different consistent autocorrelation estimators.
        total = independent.shape[0] * independent.shape[1]
        assert torch.all((ess > total / 2) & (ess < 3 * total / 2))
        equivalent = total * (1 - .95) / (1 + .95)
        assert torch.all((dependent_ess > equivalent / 2) &
                         (dependent_ess < 2 * equivalent))
        for entry in (stats.gelman_rubin, stats.split_gelman_rubin):
            baseline = invoke(entry, independent).value
            shifted = invoke(entry, separated).value
            assert baseline.shape == shifted.shape == (2,)
            assert torch.all(shifted > baseline)
            permuted = invoke(entry, separated.permute(2, 1, 0),
                              kwargs={'chain_dim': 2, 'sample_dim': 1}).value
            assert_close(permuted, shifted)
        unsplit = invoke(stats.gelman_rubin, drifting).value
        split = invoke(stats.split_gelman_rubin, drifting).value
        assert torch.all(split > unsplit)
        assert_close(invoke(stats.effective_sample_size, correlated.permute(2, 1, 0),
                            kwargs={'chain_dim': 2, 'sample_dim': 1}).value, dependent_ess)


def test_f12_t07():
    with isolated_state(dtype=torch.float64):
        raw = np.array([[2., -3., 7.], [5., 1., -2.], [-1., 4., 3.],
                        [7., 2., 0.], [0., -5., 1.], [3., 8., -4.],
                        [-4., 0., 5.], [1., 6., -1.]])
        centered = raw - raw.mean(axis=0)
        samples = torch.tensor(centered)
        # Direct paired products are independent of the product's FFT path.
        products = np.stack([(centered[:len(raw)-lag] * centered[lag:]).sum(0)
                             for lag in range(len(raw))])
        for entry in (stats.autocorrelation, stats.autocovariance):
            expected = products / np.arange(len(raw), 0, -1)[:, None]
            if entry is stats.autocorrelation:
                expected = expected / expected[0]
            out = invoke(entry, samples).value
            assert out.shape == samples.shape
            assert torch.isfinite(out).all()
            assert_close(out, expected)
            assert_close(invoke(entry, samples.T, kwargs={'dim': 1}).value, out.T)
            # Changing a coordinate's origin cannot change its dependence.
            shifted = samples + torch.tensor([11., -7., 4.])
            assert_close(invoke(entry, shifted).value, out)
            factors = torch.tensor([2., -3., .5])
            scaled = invoke(entry, samples*factors).value
            assert_close(scaled, out if entry is stats.autocorrelation else out*factors.square())


def test_f12_t08():
    with isolated_state(dtype=torch.float64):
        pred = torch.tensor([[[1., -2.], [4., 0.]], [[7., 3.], [-1., 2.]],
                             [[2., 8.], [6., -3.]], [[2., 1.], [3., 9.]]])
        truth = torch.tensor([[.5, 2.], [3., -1.]])
        for draws in (pred, pred[:1]):
            # Direct empirical expectation includes all independent pairs,
            # including equal indices, as required by the scoring functional.
            x, y = draws.numpy(), truth.numpy()
            expected = np.abs(x-y).mean(0)-.5*np.abs(x[:, None]-x[None, :]).mean((0, 1))
            actual = invoke(stats.crps_empirical, draws, truth).value
            assert actual.shape == truth.shape
            assert_close(actual, expected)


def test_f12_t09():
    with isolated_state(dtype=torch.float64):
        samples = torch.tensor([[10., -4.], [0., 8.], [4., 1.], [20., 3.]])
        probs = [.12, .43, .78]
        for weights in (np.array([1., 3., 2., 4.]), np.array([5., 1., 7., 2.])):
            answers = []
            for event in range(2):
                order = np.argsort(samples[:, event].numpy())
                cumulative = np.cumsum(weights[order]/weights.sum())
                positions = (cumulative-cumulative[0])/(cumulative[-1]-cumulative[0])
                answers.append(np.interp(probs, positions, samples[:, event].numpy()[order]))
            expected = np.array(answers).T
            logs = torch.tensor(np.log(weights))
            assert_close(invoke(stats.weighed_quantile, samples, probs, logs).value, expected)
            assert_close(invoke(stats.weighed_quantile, samples.T, probs, logs,
                                kwargs={'dim': 1}).value, expected.T)
            assert_close(invoke(stats.weighed_quantile, samples, probs, logs+9).value, expected)
