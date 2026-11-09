# feature: F14
"""Acceptance tests for Gaussian process inference and prediction."""
import numpy as np
import pytest
import torch
from scipy import integrate, special, stats
import velnora
from velnora import poutine
from velnora.contrib.gp import kernels as k, models as m, likelihoods as lik
from velnora.infer import TraceMeanField_ELBO
from _helpers import isolated_state
from F01_helpers import assert_close, assert_frequency, SAMPLE_COUNT
from F09_helpers import fit_svi
from F14_helpers import (gp_problem, gp_kernel, bilinear_cov, regression_oracle,
                         check_gp_prediction, variational_oracle, gp_fit_score)


def test_f14_t01():
    with isolated_state(dtype=torch.float64):
        x, y, new = gp_problem()
        for noise, mean in [(1., None), (.35, lambda a: .4+a[:, 0]*.6)]:
            velnora.clear_param_store()
            kernel = gp_kernel()
            options = {} if mean is None else {'noise': torch.tensor(noise), 'mean_function': mean}
            model = m.GPRegression(x, y, kernel, jitter=0., **options)
            expected = regression_oracle(x, y, new, kernel, noise, mean)
            check_gp_prediction(model, new, expected, noise)
            score = poutine.trace(model.model).get_trace().log_prob_sum()
            mu = np.zeros(len(x)) if mean is None else mean(x).numpy()
            assert_close(score, stats.multivariate_normal.logpdf(y.numpy(), mu,
                bilinear_cov(x, x, kernel)+noise*np.eye(len(x))))


def test_f14_t02():
    # Independent covariance laws use caller-selected nondefault parameters.
    with isolated_state(dtype=torch.float64):
        x = torch.tensor([[-1.2, .3, 2.], [.7, -.4, 3.], [1.8, 1.1, -2.]])
        z = torch.tensor([[.6, -.8, 4.], [-.3, .5, -3.]])
        families = [k.RBF, k.Exponential, k.RationalQuadratic, k.Matern32,
                    k.Matern52, k.Cosine, k.Periodic, k.Linear, k.Polynomial,
                    k.Constant, k.WhiteNoise]
        for family in families:
            velnora.clear_param_store()
            explicit = {'variance': torch.tensor(1.)}
            if family in families[:7]:
                explicit['lengthscale'] = torch.tensor(1.)
            if family is k.Periodic:
                explicit['period'] = torch.tensor(1.)
            if family is k.RationalQuadratic:
                explicit['scale_mixture'] = torch.tensor(1.)
            if family is k.Polynomial:
                explicit.update(degree=1, bias=torch.tensor(1.))
            default, configured = family(2), family(2, **explicit)
            default_covariance = default(x[:, :2], z[:, :2]).detach().clone()
            velnora.clear_param_store()
            assert_close(configured(x[:, :2], z[:, :2]), default_covariance.numpy())
            chosen = family(2, active_dims=[2, 0], **explicit)
            assert_close(chosen(x, z), configured(x[:, [2, 0]], z[:, [2, 0]]).detach().numpy())
            if family is not k.WhiteNoise:
                assert_close(default(x[:, :2]), default(x[:, :2], x[:, :2]).detach().numpy())
        for family in families:
            velnora.clear_param_store()
            options = {'variance': torch.tensor(1.7)}
            lengths = np.array([.7, 1.6])
            if family in families[:7]:
                options['lengthscale'] = torch.tensor(lengths)
            if family is k.Periodic:
                options['period'] = torch.tensor([1.3, 2.1])
            if family is k.RationalQuadratic:
                options['scale_mixture'] = torch.tensor(.6)
            if family is k.Polynomial:
                options.update(degree=3, bias=torch.tensor(.4))
            kernel = family(2, **options)
            for right in (z[:, :2], x[:, :2]):
                left = x[:, :2].numpy()
                other = right.numpy()
                delta = left[:, None] - other[None, :]
                square = ((delta/lengths)**2).sum(-1)
                radius = np.sqrt(square)
                dot = left @ other.T
                expected = {
                    k.RBF: lambda: 1.7*np.exp(-square/2),
                    k.Exponential: lambda: 1.7*np.exp(-radius),
                    k.RationalQuadratic: lambda: 1.7*(1+square/(2*.6))**(-.6),
                    k.Matern32: lambda: 1.7*(1+np.sqrt(3)*radius)*np.exp(-np.sqrt(3)*radius),
                    k.Matern52: lambda: 1.7*(1+np.sqrt(5)*radius+5*square/3)*np.exp(-np.sqrt(5)*radius),
                    k.Cosine: lambda: 1.7*np.cos(radius),
                    k.Periodic: lambda: 1.7*np.exp(-2*((np.sin(np.pi*delta/np.array([1.3, 2.1]))/lengths)**2).sum(-1)),
                    k.Linear: lambda: 1.7*dot,
                    k.Polynomial: lambda: 1.7*(.4+dot)**3,
                    k.Constant: lambda: np.full(dot.shape, 1.7),
                    k.WhiteNoise: lambda: np.zeros(dot.shape),
                }[family]()
                assert_close(kernel(x[:, :2], right), expected)
                if family is not k.WhiteNoise and len(right) == len(x):
                    assert_close(kernel(x[:, :2]), expected)
                    assert_close(kernel(x[:, :2], diag=True), np.diag(expected))
        b = torch.tensor([-2., -.4, .6, 1.8])
        expected = 1.7*np.where(np.outer(b.numpy(), b.numpy()) >= 0,
                               np.minimum.outer(abs(b.numpy()), abs(b.numpy())), 0.)
        velnora.clear_param_store()
        brown = k.Brownian(1, variance=torch.tensor(1.7))
        assert_close(brown(b), expected)
        assert_close(brown(b, diag=True), np.diag(expected))
        velnora.clear_param_store()
        assert_close(k.Brownian(1)(b), expected/1.7)
        velnora.clear_param_store()
        white = k.WhiteNoise(1, variance=torch.tensor(.8))
        assert_close(white(b), .8*np.eye(len(b)))
        assert_close(white(b, b.clone()), np.zeros((len(b), len(b))))
        assert_close(white(b, diag=True), np.full(len(b), .8))
        kernel = gp_kernel()
        x, _, z = gp_problem()
        assert_close(kernel(x, z), bilinear_cov(x, z, kernel))
        assert_close(kernel(x, diag=True), np.diag(bilinear_cov(x, x, kernel)))
        selected = k.Coregionalize(3, components=kernel.components.detach().clone(),
            diagonal=kernel.diagonal.detach().clone(), active_dims=[2, 0, 1])
        assert_close(selected(x, z), bilinear_cov(x[:, [2, 0, 1]], z[:, [2, 0, 1]], kernel))


def test_f14_t03():
    with isolated_state(dtype=torch.float64):
        x, _, z = gp_problem()
        a = gp_kernel()
        b = k.Constant(3, variance=torch.tensor(.7))
        base = bilinear_cov(x, z, a)
        scale = lambda t: 1.+t[:, 0].square()
        warp = lambda t: t.square()+.2*t
        composed = k.Warping(k.VerticalScaling(k.Sum(a, b), scale), iwarping_fn=warp)
        wx, wz = warp(x), warp(z)
        expected = (bilinear_cov(wx, wz, a)+.7)*np.outer(scale(wx), scale(wz))
        checks = [(k.Sum(a, b), base+.7), (k.Product(a, b), base*.7),
                  (k.Exponent(a), np.exp(base)),
                  (k.VerticalScaling(a, scale), base*np.outer(scale(x), scale(z))),
                  (k.Warping(a, iwarping_fn=warp), bilinear_cov(wx, wz, a)),
                  (composed, expected)]
        for kernel, expected in checks:
            assert_close(kernel(x, z), expected)
            assert_close(kernel(x, diag=True), np.diag(kernel(x).detach().numpy()))


def test_f14_t04():
    with isolated_state(dtype=torch.float64):
        x, y, _ = gp_problem()
        u = x[:2].clone()
        for approx in ['DTC', 'FITC', 'VFE', None]:
            velnora.clear_param_store()
            kernel = gp_kernel()
            model = m.SparseGPRegression(x, y, kernel, u, noise=torch.tensor(.4), approx=approx, jitter=0.)
            kuu = bilinear_cov(u, u, kernel)
            kuf = bilinear_cov(u, x, kernel)
            q = kuf.T @ np.linalg.solve(kuu, kuf)
            residual = bilinear_cov(x, x, kernel)-q
            cov = q+.4*np.eye(len(x))
            if approx == 'FITC':
                cov += np.diag(np.diag(residual))
            expected = stats.multivariate_normal.logpdf(y.numpy(), np.zeros(len(x)), cov)
            if approx in ['VFE', None]:
                expected -= np.trace(residual)/(2*.4)
            trace = poutine.trace(model.model).get_trace()
            assert_close(trace.log_prob_sum(), expected)
            assert_close(torch.as_tensor(poutine.trace(model.guide).get_trace().log_prob_sum()), 0.)
        with pytest.raises(ValueError):
            m.SparseGPRegression(x, y, gp_kernel(), u, approx='unsupported')


def test_f14_t05():
    with isolated_state(dtype=torch.float64):
        x, y, new = gp_problem()
        for approx in ['DTC', 'FITC', 'VFE']:
            for u in [x[:2].clone(), x[1:].clone(), x.clone()]:
                velnora.clear_param_store()
                kernel = gp_kernel()
                model = m.SparseGPRegression(x, y, kernel, u, noise=torch.tensor(.35), approx=approx, jitter=0.)
                expected = regression_oracle(x, y, new, kernel, .35, inducing=u, approx=approx)
                check_gp_prediction(model, new, expected, .35)
                if len(u) == len(x):
                    full = regression_oracle(x, y, new, kernel, .35)
                    check_gp_prediction(model, new, full, .35)


def test_f14_t06():
    with isolated_state(seed=1406, dtype=torch.float64):
        # Integrate the observation probabilities over independent Gaussian latent
        # values. Frequency margins reuse the suite's bounded-indicator budget.
        loc, var = -.4, .6
        for likelihood, response, law in [
            (lik.Binary(), special.expit, 'binary'),
            (lik.Binary(lambda f: torch.sigmoid(2*f+.3)), lambda f: special.expit(2*f+.3), 'binary'),
            (lik.Poisson(), np.exp, 'count'),
            (lik.Poisson(lambda f: torch.exp(.5*f-.2)), lambda f: np.exp(.5*f-.2), 'count')]:
            draws = likelihood(torch.full((SAMPLE_COUNT,), loc), torch.full((SAMPLE_COUNT,), var))
            function = (lambda f: response(f)) if law == 'binary' else (lambda f: np.exp(-response(f)))
            probability = integrate.quad(lambda t: function(loc+np.sqrt(var)*t)*stats.norm.pdf(t), -10, 10)[0]
            assert_frequency(draws == (1 if law == 'binary' else 0), probability)
            y = torch.tensor([0., 1., 2.] if law == 'count' else [0., 1., 1.])
            f = torch.tensor([-.7, .2, .9])
            trace = poutine.trace(likelihood).get_trace(f, torch.full_like(f, 1e-24), y)
            p = response(f.numpy())
            expected = stats.bernoulli.logpmf(y.numpy(), p) if law == 'binary' else stats.poisson.logpmf(y.numpy(), p)
            assert_close(trace.log_prob_sum(), expected.sum())
        gaussian = lik.Gaussian(variance=torch.tensor(.7))
        f = torch.tensor([-.6, .8])
        v = torch.tensor([.4, .9])
        draws = gaussian(f.expand(SAMPLE_COUNT, 2), v.expand(SAMPLE_COUNT, 2))
        assert_frequency(draws < torch.tensor([0., 1.]), stats.norm.cdf([0., 1.], f.numpy(), np.sqrt(v.numpy()+.7)))
        y = torch.tensor([.2, -.3])
        assert_close(poutine.trace(gaussian).get_trace(f, v, y).log_prob_sum(),
                     stats.norm.logpdf(y.numpy(), f.numpy(), np.sqrt(v.numpy()+.7)).sum())
        for response in [None, lambda f: torch.softmax(2*f+.2*f.square(), -1)]:
            likelihood = lik.MultiClass(3, response_function=response)
            f = torch.tensor([-.6, .2, 1.])
            logits = f.numpy() if response is None else 2*f.numpy()+.2*f.numpy()**2
            probabilities = special.softmax(logits)
            draws = likelihood(f[:, None].expand(3, SAMPLE_COUNT), torch.full((3, SAMPLE_COUNT), 1e-24))
            for category in range(3):
                assert_frequency(draws == category, probabilities[category])
            targets = torch.tensor([0, 1, 2])
            score = poutine.trace(likelihood).get_trace(f[:, None].expand(3, 3), torch.full((3, 3), 1e-24), targets).log_prob_sum()
            assert_close(score, np.log(probabilities).sum())


def test_f14_t07():
    for sparse in [False, True]:
        for family in ['Gaussian', 'Binary', 'MultiClass', 'Poisson']:
            with isolated_state(seed=1407, dtype=torch.float64):
                x, _, new = gp_problem()
                likelihood = getattr(lik, family)(3) if family == 'MultiClass' else getattr(lik, family)()
                targets = {'Gaussian': [2., -1., .8], 'Binary': [1., 0., 1.],
                           'MultiClass': [0, 1, 2], 'Poisson': [4., 0., 2.]}[family]
                y = torch.tensor(targets)
                options = {'latent_shape': torch.Size([3])} if family == 'MultiClass' else {}
                kernel = gp_kernel()
                model = (m.VariationalSparseGP(x, y, kernel, x[:2].clone(), likelihood, jitter=0., **options)
                         if sparse else m.VariationalGP(x, y, kernel, likelihood, jitter=0., **options))
                location = model.u_loc if sparse else model.f_loc
                scale = model.u_scale_tril if sparse else model.f_scale_tril
                before_loc, before_scale = location.detach().clone(), scale.detach().clone()
                before = gp_fit_score(model, sparse, family)
                fit_svi(model.model, model.guide, TraceMeanField_ELBO(), steps=180, lr=.025)
                after = gp_fit_score(model, sparse, family)
                assert after > before
                scale = model.u_scale_tril if sparse else model.f_scale_tril
                assert not torch.equal(location.detach(), before_loc)
                assert not torch.equal(scale.detach(), before_scale)
                assert torch.linalg.eigvalsh(scale @ scale.transpose(-1, -2)).min() > 0
                expected = variational_oracle(model, new, sparse)
                predicted = model(new, full_cov=True)
                assert_close(predicted[0], expected[0])
                assert_close(predicted[1], expected[1])
                assert_close(model(new)[1], np.diagonal(expected[1], axis1=-2, axis2=-1))
                # Concentrate the fitted approximation to measure the observation
                # link through the model entry, rather than only in isolation.
                velnora.clear_param_store()
                if sparse:
                    model.u_scale_tril = scale.detach()*1e-8
                else:
                    model.f_scale_tril = scale.detach()*1e-8
                if sparse:
                    model.set_data(model.Xu.detach().clone(), y[:len(model.Xu)].clone())
                y = model.y
                latent_mean, latent_cov = variational_oracle(model, model.X, sparse)
                trace = poutine.trace(model.model).get_trace()
                scores = trace.nodes['likelihood.y']['fn'].base_dist.log_prob(y)
                if family == 'Gaussian':
                    variance = np.diagonal(latent_cov, axis1=-2, axis2=-1)+model.likelihood.variance.item()
                    expected_score = stats.norm.logpdf(y.numpy(), latent_mean, np.sqrt(variance))
                elif family == 'Binary':
                    expected_score = stats.bernoulli.logpmf(y.numpy(), special.expit(latent_mean))
                elif family == 'Poisson':
                    expected_score = stats.poisson.logpmf(y.numpy(), np.exp(latent_mean))
                else:
                    probabilities = special.softmax(latent_mean.T, axis=-1)
                    expected_score = np.log(probabilities[np.arange(len(y)), y.numpy()])
                count = len(y)
                assert_close(scores[:count], expected_score[:count])


def test_f14_t08():
    for dimension in [1, 2]:
        with isolated_state(seed=1408, dtype=torch.float64):
            initial = torch.tensor([[-.8, .3], [.2, -.6], [1., .7]])[:, :dimension].clone()
            y = torch.tensor([[1., -.5, 1.2], [-.7, .4, .9]])
            kernel = k.Coregionalize(dimension, components=torch.full((dimension, 1), .7), diagonal=torch.full((dimension,), .8))
            model = m.GPLVM(m.GPRegression(initial.clone(), y, kernel, noise=torch.tensor(.4), jitter=0.))
            assert_close(model.X_loc, initial.numpy())
            value = initial+.25
            prior = poutine.trace(poutine.condition(model.model, data={'X': value})).get_trace()
            prior.compute_log_prob()
            assert_close(prior.nodes['X']['log_prob'], stats.norm.logpdf(value.numpy()).sum())
            covariance = bilinear_cov(value, value, kernel)+.4*np.eye(len(value))
            observation_score = sum(stats.multivariate_normal.logpdf(row, np.zeros(len(value)), covariance) for row in y.numpy())
            assert_close(prior.log_prob_sum(), stats.norm.logpdf(value.numpy()).sum()+observation_score)
            guide = poutine.trace(poutine.condition(model.guide, data={'X': value})).get_trace()
            guide.compute_log_prob()
            assert_close(guide.nodes['X']['log_prob'], stats.norm.logpdf(value.numpy(), model.X_loc.detach().numpy(), model.X_scale.detach().numpy()).sum())
            old_scale = model.X_scale.detach().clone()
            fit_svi(model.model, model.guide, TraceMeanField_ELBO(), steps=200, lr=.02)
            assert model.X_loc.shape == initial.shape and model.X_scale.shape == initial.shape
            assert torch.isfinite(model.X_loc).all() and torch.isfinite(model.X_scale).all()
            assert (model.X_scale > 0).all()
            assert not torch.equal(model.X_loc.detach(), initial)
            assert not torch.equal(model.X_scale.detach(), old_scale)
            guide = poutine.trace(poutine.condition(model.guide, data={'X': value})).get_trace()
            guide.compute_log_prob()
            assert_close(guide.nodes['X']['log_prob'], stats.norm.logpdf(value.numpy(), model.X_loc.detach().numpy(), model.X_scale.detach().numpy()).sum())


def test_f14_t09():
    with isolated_state(seed=1409, dtype=torch.float64):
        x, y, new = gp_problem()
        model = m.GPRegression(x, y, gp_kernel(), noise=torch.tensor(.6), jitter=0.)
        fit_svi(model.model, model.guide, TraceMeanField_ELBO(), steps=30, lr=.01)
        components = model.kernel.components.detach().clone()
        diagonal = model.kernel.diagonal.detach().clone()
        noise = model.noise.detach().clone()
        replacement_x = x[:2]*1.3
        replacement_y = torch.tensor([-.9, 1.7])
        model.set_data(replacement_x, replacement_y)
        assert_close(model.kernel.components, components.numpy())
        assert_close(model.kernel.diagonal, diagonal.numpy())
        assert_close(model.noise, noise.numpy())
        check_gp_prediction(model, new, regression_oracle(replacement_x, replacement_y, new, model.kernel, noise.item()), noise.item())
        likelihood = lik.Gaussian(variance=torch.tensor(.8))
        sparse = m.VariationalSparseGP(x, y, gp_kernel(), x[:2].clone(), likelihood, jitter=0.)
        fit_svi(sparse.model, sparse.guide, TraceMeanField_ELBO(), steps=30, lr=.01)
        parameters = [p.detach().clone() for p in sparse.parameters()]
        sparse.set_data(replacement_x, replacement_y)
        for p, old in zip(sparse.parameters(), parameters):
            assert_close(p, old.numpy())
        assert np.isfinite(TraceMeanField_ELBO().loss(sparse.model, sparse.guide))
        for obj in [model, sparse, m.VariationalGP(x, y, gp_kernel(), lik.Gaussian()),
                    m.SparseGPRegression(x, y, gp_kernel(), x[:2].clone())]:
            assert torch.isfinite(obj(new)[0]).all()
            with pytest.raises(ValueError):
                obj.set_data(x, y[:2])
            for invalid in [torch.ones(2, 2), torch.ones(2, 3, 1)]:
                with pytest.raises(ValueError):
                    obj(invalid)
        with pytest.raises(ValueError):
            m.GPRegression(x, y[:2], gp_kernel())
