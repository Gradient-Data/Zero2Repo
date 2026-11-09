# feature: F19
"""Acceptance tests for latent-confounder causal effect estimation."""
import numpy as np
import torch
from velnora import poutine
from velnora.contrib.cevae import CEVAE, TraceCausalEffect_ELBO
from _helpers import invoke, isolated_state, save_and_load
from F01_helpers import assert_close
from F16_helpers import epidemic_cpu_threads
from F19_helpers import (causal_cohort, causal_fit, causal_inputs, causal_law_score,
                         integrated_effect, conditional_snapshot)


def test_f19_t01(epidemic_cpu_threads):
    with isolated_state(seed=1901, dtype=torch.float64, device='cpu'):
        x = torch.tensor([[-1., .5], [.3, -1.2], [1.1, 2.]])
        z = torch.tensor([[-.7, .2], [.4, -.9], [1.3, .8]])
        t = torch.tensor([0., 1., 0.])
        for family in ('bernoulli', 'exponential', 'laplace', 'normal', 'studentt'):
            causal = CEVAE(2, family, latent_dim=2, hidden_dim=8, num_layers=2)
            y = torch.tensor([0., 1., 1.]) if family == 'bernoulli' else torch.tensor([.2, .8, 2.])
            prior = causal.model.z_dist()
            assert prior.event_shape == (2,)
            assert_close(prior.base_dist.loc, 0.)
            assert_close(prior.base_dist.scale, 1.)
            px = causal.model.x_dist(z)
            assert px.event_shape == (2,)
            qz = causal.guide.z_dist(y, t, x)
            assert qz.event_shape == (2,)
            laws = [(prior, z, 'normal', True), (px, x, 'normal', True),
                    (causal.model.t_dist(z), t, 'bernoulli', False),
                    (causal.model.y_dist(t, z), y, family, False),
                    (causal.guide.t_dist(x), t, 'bernoulli', False),
                    (causal.guide.y_dist(t, x), y, family, False),
                    (qz, z, 'normal', True)]
            for law, value, name, vector in laws:
                causal_law_score(law, value, name, vector)
            # Scores on public traces must be the conditional joint, not just
            # standalone distributions with a disconnected execution path.
            guide = poutine.trace(causal.guide).get_trace(x, t, y)
            drawn_z = guide.nodes['z']['value']
            trace_laws = [(prior, drawn_z), (causal.model.x_dist(drawn_z), x),
                          (causal.model.t_dist(drawn_z), t),
                          (causal.model.y_dist(t, drawn_z), y)]
            model = poutine.trace(poutine.replay(causal.model, trace=guide)).get_trace(x, t, y)
            guide.compute_log_prob()
            model.compute_log_prob()
            for trace, names, expected in (
                (model, ('z', 'x', 't', 'y'), trace_laws),
                (guide, ('t', 'y', 'z'), [(laws[4][0], t), (laws[5][0], y), (qz, drawn_z)])):
                for name, (law, value) in zip(names, expected):
                    assert_close(trace.nodes[name]['log_prob'], law.log_prob(value).detach().numpy())
            # Two response means must be independently adjustable. A rank-two
            # Jacobian admits any network layout, including shared features.
            parameters = tuple(causal.model.parameters())
            responses = [causal.model.y_dist(torch.tensor(a), z).mean.sum() for a in (0., 1.)]
            rows = []
            for response in responses:
                gradients = torch.autograd.grad(response, parameters, allow_unused=True)
                rows.append(torch.cat([(torch.zeros_like(p) if g is None else g).flatten()
                                       for p, g in zip(parameters, gradients)]))
            assert torch.linalg.matrix_rank(torch.stack(rows)) == 2
            losses = invoke(causal.fit, x, t, y, kwargs=dict(num_epochs=2,
                batch_size=len(x), log_every=0)).value
            assert len(losses) == 2 and np.isfinite(losses).all()
            effects = invoke(causal.ite, x, kwargs={'num_samples': 8}).value
            assert effects.shape == (len(x),) and torch.isfinite(effects).all()
        default = CEVAE(2, latent_dim=2, hidden_dim=8, num_layers=2)
        causal_law_score(default.model.y_dist(t, z), torch.tensor([0., 1., 0.]), 'bernoulli')
        causal_law_score(default.guide.y_dist(t, x), torch.tensor([0., 1., 0.]), 'bernoulli')


def test_f19_t02(epidemic_cpu_threads):
    with isolated_state(seed=1902, dtype=torch.float64, device='cpu'):
        x, t, y = causal_cohort(12)
        causal = CEVAE(2, 'normal', latent_dim=1, hidden_dim=8, num_layers=2)
        guide = poutine.trace(causal.guide).get_trace(x, t, y)
        model = poutine.trace(poutine.replay(causal.model, trace=guide)).get_trace(x, t, y)
        guide.compute_log_prob()
        model.compute_log_prob()
        expected = (-sum(model.nodes[k]['log_prob'].sum() for k in ('z', 'x', 't', 'y'))
                    + guide.nodes['z']['log_prob'].sum()
                    - sum(guide.nodes[k]['log_prob'].sum() for k in ('t', 'y')))
        actual = invoke(TraceCausalEffect_ELBO().differentiable_loss,
                        poutine.replay(causal.model, trace=guide),
                        poutine.replay(causal.guide, trace=guide), x, t, y).value
        assert_close(actual, expected.detach().numpy())
        parameters = tuple(causal.parameters())
        gradients = torch.autograd.grad(actual, parameters, retain_graph=True, allow_unused=True)
        reference = torch.autograd.grad(expected, parameters, allow_unused=True)
        for p, got, want in zip(parameters, gradients, reference):
            assert_close(torch.zeros_like(p) if got is None else got,
                         (torch.zeros_like(p) if want is None else want).detach().numpy())
        assert any(g is not None and g.abs().max() > 0 for g in gradients)

        # Zero-rate fitting has the same expected per-individual objective;
        # independent Monte Carlo replicates avoid pinning shuffles or RNG use.
        losses = invoke(causal.fit, x, t, y, kwargs=dict(num_epochs=80,
            batch_size=len(x), learning_rate=0., weight_decay=0., log_every=0)).value
        standardized_x = causal_inputs(causal, x)
        direct = [invoke(TraceCausalEffect_ELBO().loss, causal.model, causal.guide,
                         standardized_x, t, y).value/len(x) for _ in range(80)]
        error = 8*np.sqrt(np.var(losses, ddof=1)/80 + np.var(direct, ddof=1)/80)
        assert np.isfinite(losses).all()
        assert len(losses) == 80
        assert abs(np.mean(losses)-np.mean(direct)) < error

    with isolated_state(seed=1922, dtype=torch.float64, device='cpu'):
        x, t, y = causal_cohort()
        causal = CEVAE(2, 'normal', latent_dim=1, hidden_dim=12, num_layers=2)
        invoke(causal.fit, x, t, y, kwargs=dict(num_epochs=1,
            batch_size=len(x), learning_rate=0., weight_decay=0., log_every=0)).value
        xx = causal_inputs(causal, x)
        def predictive_score():
            return -(causal.guide.t_dist(xx).log_prob(t) +
                     causal.guide.y_dist(t, xx).log_prob(y)).mean().item()
        before = predictive_score()
        probe_z = torch.linspace(-2., 2., 11)[:, None]
        initial_responses = [causal.model.y_dist(torch.tensor(a), probe_z).mean.detach().clone()
                             for a in (0., 1.)]
        losses = invoke(causal.fit, x, t, y, kwargs=dict(num_epochs=70,
            batch_size=32, learning_rate=.015, learning_rate_decay=1.,
            weight_decay=0., log_every=0), timeout=120).value
        assert len(losses) == 70*3
        assert np.isfinite(losses).all()
        xx = causal_inputs(causal, x)
        assert predictive_score() < before
        for treatment, initial in zip((0., 1.), initial_responses):
            learned = causal.model.y_dist(torch.tensor(treatment), probe_z).mean
            assert not torch.allclose(learned, initial)


def test_f19_t03(epidemic_cpu_threads):
    with isolated_state(seed=1903, dtype=torch.float64, device='cpu'):
        causal, (x, t, y), _ = causal_fit(epochs=2)
        valid = invoke(causal.ite, x[:4], kwargs={'num_samples': 8}).value
        assert valid.shape == (4,) and torch.isfinite(valid).all()
        invalid = [dict(outcome_dist='unknown')]
        for dimension in ('feature_dim', 'latent_dim', 'hidden_dim'):
            for size in (0, -2):
                invalid.append({dimension: size})
        for options in invalid:
            args = dict(feature_dim=2, latent_dim=1, hidden_dim=8, num_layers=2)
            args.update(options)
            result = invoke(CEVAE, kwargs=args, allowed_exceptions=(ValueError,))
            assert isinstance(result.exception, ValueError)
        result = invoke(causal.ite, torch.randn(4, 3), allowed_exceptions=(AssertionError,))
        assert isinstance(result.exception, AssertionError)


def test_f19_t04(epidemic_cpu_threads):
    with isolated_state(seed=1904, dtype=torch.float64, device='cpu'):
        causal, (x, _, _), _ = causal_fit()
        query = torch.tensor([[-1.2, .7], [.6, -1.4], [2., .3]])
        expected, variance = integrated_effect(causal, x, query, 40)
        refined, _ = integrated_effect(causal, x, query, 64)
        integration_error = (expected-refined).abs()*4 + 1e-6
        # Independent repeated estimates and eight standard errors per
        # coordinate allow unrelated random streams; exact integration also
        # passes. The uncertainty includes treatment/outcome variation that
        # does not vanish as the requested confounder draw count increases.
        for count in (1, 256):
            effects = torch.stack([invoke(causal.ite, query, kwargs={'num_samples': count}).value
                                   for _ in range(508)])
            assert effects.shape == (508, len(query))
            bound = 8*((variance[0]+variance[1]/count)/len(effects)).sqrt() + integration_error
            assert ((effects.mean(0)-refined).abs() < bound).all()
            assert abs(effects.mean()-refined.mean()) < bound.mean()
            # The sample-count promise is an upper variance bound, not a
            # claim that all uncertainty vanishes. Integrate fourth moments
            # independently. Each block mean of four squared errors exceeds
            # its expectation by two standard deviations with probability at
            # most 1/4 (Chebyshev). The median of 127 independent blocks then
            # exceeds that bound with probability below 7e-10 per coordinate:
            # sum_{k=64}^{127} binom(127,k) (1/4)^k (3/4)^(127-k).
            _, variance64, fourth = integrated_effect(causal, x, query, 64, sample_count=count)
            total_variance = variance64[0]+variance64[1]/count
            coarse_variance = variance[0]+variance[1]/count
            margin = (fourth-total_variance.square()).clamp(min=0).sqrt()
            margin += 4*(total_variance-coarse_variance).abs()
            margin += integration_error.square()+2*integration_error*total_variance.sqrt()
            block_mse = (effects-refined).square().reshape(127, 4, len(query)).mean(1)
            assert (block_mse.median(0).values <= total_variance+margin).all()


def test_f19_t05(epidemic_cpu_threads):
    with isolated_state(seed=1905, dtype=torch.float64, device='cpu'):
        causal, (x, _, _), _ = causal_fit()
        query = torch.tensor([[1.7, -.1], [-.8, 1.3], [.2, -1.1],
                              [2.4, .8], [-1.5, -.6], [.9, 1.8], [-.4, .2]])
        expected, variance = integrated_effect(causal, x, query, 64)
        coarse, _ = integrated_effect(causal, x, query, 40)
        for batch_size in (None, 2, 4):
            effects = torch.stack([invoke(causal.ite, query,
                kwargs={'num_samples': 256, 'batch_size': batch_size}).value for _ in range(128)])
            assert effects.shape == (128, len(query))
            bound = 8*((variance[0]+variance[1]/256)/128).sqrt() + 4*(expected-coarse).abs() + 1e-6
            assert ((effects.mean(0)-expected).abs() < bound).all()


def test_f19_t06(epidemic_cpu_threads):
    with isolated_state(seed=1906, dtype=torch.float64, device='cpu'):
        causal, (x, _, _), _ = causal_fit()
        query = torch.tensor([[-.9, 1.], [.8, -.4], [2.1, 1.3]])
        before = conditional_snapshot(causal, x, query)
        _, result = save_and_load(lambda path: torch.save(causal, path),
                                 lambda path: torch.load(path, weights_only=False))
        restored = result.value
        after = conditional_snapshot(restored, x, query)
        for got, want in zip(after, before):
            assert_close(got, want.numpy())
        expected, variance = integrated_effect(causal, x, query, 64)
        coarse, _ = integrated_effect(causal, x, query, 40)
        # Observe both models against the same conditional integral, allowing
        # independent stochastic predictions rather than identical RNG draws.
        for fitted in (causal, restored):
            effects = torch.stack([invoke(fitted.ite, query, kwargs={'num_samples': 256}).value
                                   for _ in range(128)])
            bound = 8*((variance[0]+variance[1]/256)/128).sqrt() + 4*(expected-coarse).abs() + 1e-6
            assert ((effects.mean(0)-expected).abs() < bound).all()
