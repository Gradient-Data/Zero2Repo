# feature: F15
"""Acceptance tests for conditional forecasts and rolling evaluation."""
import math
import numpy as np
import pytest
import torch
import velnora
from velnora.contrib.forecast import Forecaster, HMCForecaster, backtest
from velnora.contrib.forecast.evaluate import eval_mae, eval_rmse, eval_crps
from _helpers import isolated_state, invoke
from F01_helpers import assert_close
from F13_helpers import conditional_normal
from F15_helpers import (CovariateForecast, CorrelatedForecast, LevelForecast,
    GroupForecast, SelectedGuide, forecast_fit, normal_nll, check_draw_moments, correlated_noise)


def test_f15_t01():
    with isolated_state(seed=120, dtype=torch.float64):
        cov = torch.tensor([[-.3, .2], [.8, -.5], [1.5, 2.], [-1.2, .7], [.4, -2.]])
        _, (mean, covariance) = correlated_noise(5)
        histories = (torch.tensor([[1.7, -.3], [-.9, 1.2]]),
                     torch.tensor([[-1., .6], [.2, -.5]]))
        for history in histories:
            fit = forecast_fit(CorrelatedForecast(), history, cov[:2])
            draws = invoke(fit, history, cov, 16000).value
            assert draws.shape == (16000, 3, 2)
            mu, cc = conditional_normal(mean, covariance, (history-cov[:2]).numpy(), 4)
            check_draw_moments(draws, mu+cov[2:].numpy().reshape(-1), cc)


def test_f15_t02():
    with isolated_state(seed=204, dtype=torch.float64):
        data = torch.tensor([[2., 2.4], [1.8, 2.2], [2.5, 2.1]])
        cov = torch.zeros_like(data)
        variance = 1/(1+4*data.numel())
        mean = 4*data.sum().item()*variance
        def guide(data, covariates):
            velnora.sample('level', velnora.distributions.Normal(mean, math.sqrt(variance)))
        fit = forecast_fit(LevelForecast(), data, cov, guide=guide, num_steps=3)
        # Exact posterior guide makes every Monte Carlo ELBO equal log evidence.
        c = .25*np.eye(data.numel())+np.ones((data.numel(), data.numel()))
        from scipy.stats import multivariate_normal
        expected = -multivariate_normal.logpdf(data.numpy().reshape(-1), cov=c)/data.numel()
        np.testing.assert_allclose(fit.losses, [expected]*3, rtol=1e-6)
        future = torch.zeros(5, 2)
        check_draw_moments(invoke(fit, data, future, 12000).value,
            np.full(4, mean), variance*np.ones((4, 4))+.25*np.eye(4))
        velnora.clear_param_store()
        sampled = invoke(HMCForecaster, LevelForecast(), data, cov,
            kwargs={'num_warmup': 100, 'num_samples': 250, 'max_tree_depth': 5}, timeout=120).value
        draws = invoke(sampled, data, future, 12000).value.reshape(12000, -1)
        # MCMC effective sample count is smaller than the predictive draw count.
        assert abs(draws.mean().item()-mean) < .22
        assert abs(draws[:, 0].var().item()-(variance+.25)) < .12
        velnora.clear_param_store()
        learned = forecast_fit(LevelForecast(), data, cov, num_steps=180,
                               learning_rate=.07, learning_rate_decay=1.)
        draws = invoke(learned, data, future, 4000).value
        assert abs(draws.mean().item()-mean) < .3


def test_f15_t03():
    with isolated_state(seed=309, dtype=torch.float64):
        cov = torch.tensor([[[0.], [1.], [2.]], [[3.], [-1.], [4.]],
                            [[-2.], [.5], [1.]], [[2.], [3.], [-3.]]])
        residual = torch.tensor([.2, 1., -.4, 1.7])[:, None, None]
        data = cov[:, :2]+residual
        # Deterministic selected minibatches isolate scaling and group alignment.
        for indices in (torch.tensor([0, 2]), torch.tensor([1, 3]), None):
            velnora.clear_param_store()
            guide = SelectedGuide(4, indices)
            fit = forecast_fit(GroupForecast(), data, cov[:, :2], guide=guide, num_steps=1)
            selected = np.arange(4) if indices is None else indices.numpy()
            expected = (normal_nll(residual.numpy()[selected]).sum()*2*4/len(selected)
                        +.5*math.log(2*math.pi))/data.numel()
            np.testing.assert_allclose(fit.losses, [expected], rtol=1e-6)
            draws = invoke(fit, data, cov, 10000).value
            check_draw_moments(draws, cov[:, 2].numpy(), .25*np.eye(4))
        # A shared uncertain level must induce cross-series forecast covariance.
        velnora.clear_param_store()
        variance = 1/(1+4*data.numel())
        mean = 4*(data-cov[:, :2]).sum().item()*variance
        def global_guide(data, covariates):
            velnora.sample('level', velnora.distributions.Normal(mean, math.sqrt(variance)))
        fit = forecast_fit(GroupForecast(), data, cov[:, :2], guide=global_guide)
        check_draw_moments(invoke(fit, data, cov, 16000).value,
            cov[:, 2].numpy().reshape(-1)+mean,
            variance*np.ones((4, 4))+.25*np.eye(4))


def test_f15_t04():
    with isolated_state(seed=405, dtype=torch.float64):
        data = torch.ones(3, 1)
        cov = torch.zeros(5, 1)
        for engine, options in ((Forecaster, {'num_steps': 0}),
                                (HMCForecaster, {'num_warmup': 2, 'num_samples': 2})):
            with pytest.raises(AssertionError):
                engine(LevelForecast(), data, cov, **options)
            fit = invoke(engine, LevelForecast(), data, cov[:3], kwargs=options).value
            assert invoke(fit, data, cov, 7).value.shape == (7, 2, 1)
            with pytest.raises(AssertionError):
                fit(data, cov[:2], 7)
            for count in (0, -2, 1.5):
                with pytest.raises(AssertionError):
                    fit(data, cov, count)


def test_f15_t05():
    with isolated_state(dtype=torch.float64):
        data = torch.tensor([[.2], [1.], [-.5], [2.], [.7], [-1.]])
        cov = torch.tensor([[.5], [-.7], [1.5], [.2], [-.9], [2.]])
        cases = [({}, [(0, i, 6) for i in range(1, 6)]),
            ({'min_train_window': 2, 'min_test_window': 2, 'stride': 2}, [(0, 2, 6), (0, 4, 6)]),
            ({'train_window': 2, 'min_train_window': 5, 'test_window': 2,
              'min_test_window': 5}, [(0, 2, 4), (1, 3, 5), (2, 4, 6)]),
            ({'min_train_window': 6}, [])]
        def guide(data, covariates):
            variance = 1/(1+4*data.numel())
            mean = 4*(data-covariates[..., :data.size(-2), :]).sum()*variance
            velnora.sample('level', velnora.distributions.Normal(mean, math.sqrt(variance)))
        for options, expected in cases:
            observed = []
            def metric(pred, truth):
                t0, t1, t2 = expected[len(observed)]
                observed.append((t0, t1, t2))
                assert pred.shape == (8000, t2-t1, 1)
                assert_close(truth, data[t1:t2].numpy())
                variance = 1/(1+4*(t1-t0))
                mean = 4*(data[t0:t1]-cov[t0:t1]).sum().item()*variance
                check_draw_moments(pred, cov[t1:t2].numpy().reshape(-1)+mean,
                    variance*np.ones((t2-t1, t2-t1))+.25*np.eye(t2-t1))
                return truth.square().mean().item()
            rows = invoke(backtest, data, cov, LevelForecast,
                kwargs=dict(options, metrics={'energy': metric}, num_samples=8000,
                            forecaster_options={'num_steps': 0, 'guide': guide})).value
            assert [(r['t0'], r['t1'], r['t2']) for r in rows] == expected
            assert observed == expected
            for row in rows:
                assert row['energy'] == data[row['t1']:row['t2']].square().mean().item()


def test_f15_t06():
    with isolated_state(seed=606, dtype=torch.float64):
        data = torch.tensor([[1.], [2.], [1.5], [2.5]])
        cov = torch.zeros_like(data)
        options = {'num_steps': 3, 'warm_start': True}
        rows = invoke(backtest, data, cov, LevelForecast,
            kwargs={'forecaster_options': options, 'num_samples': 1000}).value
        assert [(r['t0'], r['t1'], r['t2']) for r in rows] == [(0, 1, 4), (0, 2, 4), (0, 3, 4)]
        assert all(math.isfinite(r['rmse']) and r['rmse'] > 0 for r in rows)
        with pytest.raises(ValueError):
            backtest(data, cov, LevelForecast, train_window=2, forecaster_options=options)


def test_f15_t07():
    with isolated_state(dtype=torch.float64):
        pred = torch.tensor([[[0., 3.], [1., -1.]], [[2., 5.], [3., 2.]],
                             [[8., 6.], [4., 9.]]])
        truth = torch.tensor([[1., 2.], [0., 4.]])
        p, y = pred.numpy(), truth.numpy()
        expected = {'mae': np.abs(np.median(p, axis=0)-y).mean(),
            'rmse': np.sqrt(((p.mean(0)-y)**2).mean()),
            'crps': np.abs(p-y).mean()-.5*np.abs(p[:, None]-p[None, :]).mean()}
        for name, fn in [('mae', eval_mae), ('rmse', eval_rmse), ('crps', eval_crps)]:
            assert invoke(fn, pred, truth).value == pytest.approx(expected[name])
        data = torch.tensor([[.3], [1.2], [-.6], [2.]])
        cov = torch.tensor([[0.], [.5], [-1.], [1.]])
        for count in (None, 37):
            captured = []
            def record(pred, truth):
                captured.append((pred.clone(), truth.clone()))
                return (pred.mean(0)-truth).square().mean().item()
            kwargs = {'metrics': {'custom': record}, 'forecaster_options': {'num_steps': 0}}
            if count is not None:
                kwargs['num_samples'] = count
            rows = invoke(backtest, data, cov, CovariateForecast, kwargs=kwargs).value
            assert len(rows) == len(captured) == 3
            for row, (draws, heldout) in zip(rows, captured):
                n = 100 if count is None else count
                assert row['num_samples'] == n and draws.shape == (n, 4-row['t1'], 1)
                assert_close(heldout, data[row['t1']:].numpy())
                assert torch.all(abs(draws.mean(0)-cov[row['t1']:]) < 4/math.sqrt(n)+.015)
                assert row['custom'] == (draws.mean(0)-heldout).square().mean().item()
            default_draws = []
            def capture(pred, truth):
                default_draws.append((pred.clone(), truth.clone()))
                return pred, truth
            defaults = invoke(backtest, data, cov, CovariateForecast,
                kwargs={'transform': capture, 'forecaster_options': {'num_steps': 0}, **({} if count is None else {'num_samples': count})}).value
            assert len(defaults) == len(default_draws) == 3
            for row, (draws, heldout) in zip(defaults, default_draws):
                assert_close(heldout, data[row['t1']:row['t2']].numpy())
                assert row['num_samples'] == (100 if count is None else count)
                for name, fn in [('mae', eval_mae), ('rmse', eval_rmse), ('crps', eval_crps)]:
                    assert row[name] == pytest.approx(fn(draws, heldout))
