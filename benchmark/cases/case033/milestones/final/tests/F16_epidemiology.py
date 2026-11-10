# feature: F16
"""Acceptance observations for compartmental epidemic simulation and inference."""
import numpy as np
import pytest
import torch
from scipy import integrate, stats
from velnora.contrib.epidemiology import models as em
from velnora.contrib.epidemiology import CompartmentalModel
from _helpers import invoke, isolated_state
from F01_helpers import assert_close, assert_frequency
from F16_helpers import (MeasuredEpidemic, epidemic_record, epidemic_score,
    epidemic_count_law, epidemic_families, epidemic_accounting, epidemic_fit,
    epidemic_batched, epidemic_cpu_threads,
    epidemic_repetitions, epidemic_repeated_frequency)


def test_custom_compartment_simulation():
    with isolated_state(seed=1601, dtype=torch.float64):
        for population, rate in [(20, .25), (37, .65)]:
            model = MeasuredEpidemic(population, duration=4)
            out, trace = epidemic_record(model, {'infectivity': rate})
            assert_close(out['infectivity'], rate)
            epidemic_accounting(model, out)
            susceptible, infected = population-1, 1
            for t in range(4):
                new, rec = out['S2I'][t].item(), out['I2R'][t].item()
                epidemic_count_law(trace, 'S2I_{}'.format(t), susceptible, rate)
                epidemic_count_law(trace, 'I2R_{}'.format(t), infected, .2)
                epidemic_count_law(trace, 'obs_{}'.format(t), new, .9)
                susceptible, infected = susceptible-new, infected+new-rec
        draws = epidemic_batched(MeasuredEpidemic(), {'infectivity': .4})
        assert_frequency(draws['S2I'][:, 0] <= 7, stats.binom.cdf(7, 19, .4))


def test_builtin_families_conserve_population():
    with isolated_state(seed=1602, dtype=torch.float64):
        for model in epidemic_families():
            out, _ = epidemic_record(model, {'R0': 2.4})
            epidemic_accounting(model, out)
            shape = (model.duration, 2) if model.is_regional else (model.duration,)
            for compartment in model.compartments:
                assert out[compartment].shape == shape


def test_fitting_uses_evidence_and_predicts_histories():
    with isolated_state(dtype=torch.float64):
        absent = MeasuredEpidemic()
        with pytest.raises((RuntimeError, AttributeError)):
            invoke(absent.predict).value
    # The custom infection/reporting law has an independently integrable
    # posterior. Opposite observations detect returning the prior or a fit flag.
    for method in ('svi', 'mcmc'):
        for observation in (2., 15.):
            with isolated_state(seed=1603, dtype=torch.float64):
                model = MeasuredEpidemic(data=torch.tensor([observation]))
                result = epidemic_fit(model, method, draws=160, steps=300 if method == 'svi' else 120)
                for key in ('S', 'I', 'S2I', 'I2R', 'obs'):
                    assert result[key].shape == (160, 3)
                assert all(value.size(0) == 160 for value in model.samples.values())
                likelihood = lambda p: stats.beta.pdf(p, 2, 2)*stats.binom.pmf(observation, 19, .9*p)
                mass = integrate.quad(likelihood, 0, 1)[0]
                mean = integrate.quad(lambda p: p*likelihood(p), 0, 1)[0]/mass
                assert abs(result['infectivity'].mean().item()-mean) < .12
                variance = integrate.quad(lambda p: (p-mean)**2*likelihood(p), 0, 1)[0]/mass
                assert .1*variance < result['infectivity'].var().item() < 5*variance
                assert_close(result['obs'][:, 0], np.full(160, observation))
                assert ((result['S'] >= 0) & (result['S'] <= 20)).all()
                assert ((result['I'] >= 0) & (result['I'] <= 20)).all()
                if method == 'mcmc':
                    assert (result['S2I'][:, 0] >= observation).all()
                    assert_close(result['S']+result['S2I'].cumsum(-1), np.full((160, 3), 19.))
                    assert_close(result['I'], 1+result['S2I'].cumsum(-1)-result['I2R'].cumsum(-1))


def test_sparse_cumulative_reports_and_discrete_imputation():
    with isolated_state(seed=1604, dtype=torch.float64):
        model = em.SparseSIRModel(41, 3., [None]*4, torch.tensor([False, True, False, True]))
        events = {'S2I_0': 4., 'S2I_1': 3., 'S2I_2': 2., 'S2I_3': 1.,
                  'S2O_0': 1., 'S2O_1': 2., 'S2O_2': 0., 'S2O_3': 1.,
                  'I2R_0': 0., 'I2R_1': 1., 'I2R_2': 1., 'I2R_3': 1.}
        out, trace = epidemic_record(model, {'R0': 2., 'rho': .4}, events)
        assert_close(out['O'], [1., 3., 3., 4.])
        for t, n in enumerate([4, 3, 2, 1]):
            epidemic_count_law(trace, 'S2O_{}'.format(t), n, .4)
        # Same latent path, only the mask differs: zero is a real observation.
        for observed in (False, True):
            candidate = em.SparseSIRModel(41, 3., torch.tensor([0.]), torch.tensor([observed]))
            _, tr = epidemic_record(candidate, {'R0': 2., 'rho': .4},
                                     {'S2I_0': 4., 'S2O_0': 1., 'I2R_0': 0.})
            epidemic_score(tr, 'obs_0', 0., -np.inf if observed else 0.)
        data = torch.tensor([0., float('nan'), 2., float('nan')])
        mask = torch.tensor([True, False, True, False])
        fitted = em.SparseSIRModel(30, 3., data, mask)
        result = epidemic_fit(fitted, 'mcmc', draws=24, steps=8)
        assert result['O'].shape == (24, 6)
        assert_close(result['O'][:, :4][:, mask], np.broadcast_to(data[mask].numpy(), (24, 2)))
        increments = torch.diff(result['O'], prepend=torch.zeros(24, 1), dim=-1)
        assert (increments >= 0).all() and (increments <= result['S2I']).all()
        assert torch.equal(increments, result['S2O'])
        assert (result['O'][:, 1] > 0).any(), 'Missing times must allow latent reports'


def test_regional_source_destination_infection_law():
    population = torch.tensor([31., 83.], dtype=torch.float64)
    for coupling in (torch.eye(2, dtype=torch.float64), torch.tensor([[1., .7], [.2, .9]], dtype=torch.float64)):
        with isolated_state(seed=1605, dtype=torch.float64):
            for cls in (em.RegionalSIRModel, em.HeterogeneousRegionalSIRModel):
                model = cls(population, coupling, 3., [None]*2)
                fixed = {'R0': 4., 'rho': .45, 'rho0': torch.tensor([.3, .6]),
                         'R_drift': .1, 'rho_drift': .2}
                events = {'S2I_0': torch.tensor([3., 0.]), 'I2R_0': torch.tensor([0., 0.]),
                          'R_factor_0': 1., 'R_factor_1': 1.}
                out, trace = epidemic_record(model, fixed, events)
                for t, (s, i) in enumerate([(np.array([30, 83]), np.array([1, 0])),
                                           (np.array([27, 83]), np.array([4, 0]))]):
                    weights = coupling.numpy()
                    count = i@weights
                    p = 1-(1-4/(3*(population.numpy()@weights)))**count
                    # Numerical extinction boundaries are deliberately excluded.
                    active = np.flatnonzero(count > 0)
                    for j in active:
                        grid = np.arange(s[j]+1, dtype=float)
                        values = np.zeros((len(grid), 2))
                        values[:, j] = grid
                        actual = trace.nodes['S2I_{}'.format(t)]['fn'].log_prob(torch.tensor(values))[:, j]
                        np.testing.assert_allclose(actual.numpy(), stats.binom.logpmf(grid, s[j], p[j]), rtol=3e-5, atol=3e-5)
                    epidemic_count_law(trace, 'I2R_{}'.format(t), i, 1/3)
                epidemic_accounting(model, out)
            model = em.RegionalSIRModel(population, coupling, 3., [None])
            draws = epidemic_batched(model, {'R0': 4., 'rho': .45})
            p = 1-(1-4/(3*(population.numpy()@coupling.numpy())))**(np.array([1., 0.])@coupling.numpy())
            # At zero infectious pressure the numerical probability floor is
            # negligible compared with the bounded frequency margin.
            assert_frequency(draws['S2I'][:, 0, :] > 0, 1-(1-p)**np.array([30, 83]))


def test_model_declaration_validation():
    with isolated_state(seed=1606, dtype=torch.float64):
        assert epidemic_record(MeasuredEpidemic(population=2))[0]['S'].shape == (1,)
        regional = em.RegionalSIRModel(torch.tensor([1., 2.]), torch.eye(2), 3., [None])
        epidemic_accounting(regional, epidemic_record(regional)[0])
        for duration in (0, -2, 1.5):
            with pytest.raises(AssertionError):
                # Invoke the public base initializer on a caller-defined subclass.
                CompartmentalModel.__init__(MeasuredEpidemic.__new__(MeasuredEpidemic), ('S', 'I'), duration, 20)
        for population in (0, 1, -1, 2.5, torch.tensor([1., 0.]), torch.tensor([2., -.1])):
            with pytest.raises(AssertionError):
                MeasuredEpidemic(population=population)
        with pytest.raises(AssertionError):
            MeasuredEpidemic(compartments=('S', 'I', 'S'))
        with pytest.raises(AssertionError):
            em.SimpleSIRModel(1, 3., [None])


def test_basic_transition_reporting_and_death_laws():
    with isolated_state(seed=1607, dtype=torch.float64):
        for model in epidemic_families(3)[:3]:
            exposed = 'E' in model.compartments
            edge = 'S2E' if exposed else 'S2I'
            events = {edge+'_0': 4., edge+'_1': 3., edge+'_2': 2.,
                      'I2R_0': 0., 'I2R_1': 1., 'I2R_2': 1.}
            if exposed:
                events.update({'E2I_0': 0., 'E2I_1': 2., 'E2I_2': 1.})
            if 'D' in model.compartments:
                events.update({'I2D_0': 0., 'I2D_1': 0., 'I2D_2': 1.})
            out, trace = epidemic_record(model, {'R0': 2.7, 'rho': .35}, events)
            epidemic_accounting(model, out)
            s, e, i = 40, 0, 1
            for t in range(3):
                new = out[edge][t].item()
                epidemic_count_law(trace, edge+'_{}'.format(t), s, 1-(1-2.7/(3*41))**i)
                if exposed:
                    epidemic_count_law(trace, 'E2I_{}'.format(t), e, 1/2.5)
                dead = out['I2D'][t].item() if 'D' in model.compartments else 0
                if 'D' in model.compartments:
                    epidemic_count_law(trace, 'I2D_{}'.format(t), i, .3/3)
                epidemic_count_law(trace, 'I2R_{}'.format(t), i-dead, 1/3)
                epidemic_count_law(trace, 'obs_{}'.format(t), new, .35)
                progress = out['E2I'][t].item() if exposed else new
                s, e, i = s-new, e+new-progress, i+progress-out['I2R'][t].item()-dead


def test_global_priors_and_biological_domains():
    with isolated_state(seed=1608, dtype=torch.float64):
        for model in epidemic_families():
            _, trace = epidemic_record(model)
            epidemic_score(trace, 'R0', [.4, 1.3, 3.], stats.lognorm.logpdf([.4, 1.3, 3.], 1, scale=1))
            if not isinstance(model, (em.HeterogeneousSIRModel, em.UnknownStartSIRModel,
                                      em.RegionalSIRModel, em.HeterogeneousRegionalSIRModel)):
                epidemic_score(trace, 'rho', [.2, .45, .8], stats.beta.logpdf([.2, .45, .8], 10, 10))
        for model in epidemic_families(1):
            # The constructor signature carries known biological durations.
            cls = type(model)
            if isinstance(model, (em.SimpleSEIRModel, em.SimpleSEIRDModel, em.OverdispersedSEIRModel, em.SuperspreadingSEIRModel)):
                for incubation, recovery in [(1., 3.), (.5, 3.), (2., 1.), (2., 0.)]:
                    args = [41, incubation, recovery]
                    if cls is em.SimpleSEIRDModel:
                        args.append(.3)
                    with pytest.raises(AssertionError):
                        cls(*args, [None])
            else:
                for recovery in (1., 0.):
                    if model.is_regional:
                        args = (torch.tensor([41., 67.]), torch.eye(2), recovery, [None])
                    elif cls is em.UnknownStartSIRModel:
                        args = (41, recovery, 3, [None])
                    elif cls is em.SparseSIRModel:
                        args = (41, recovery, [None], [True])
                    else:
                        args = (41, recovery, [None])
                    with pytest.raises(AssertionError):
                        cls(*args)
        for mortality in (0., 1., -.1, 1.2):
            with pytest.raises(AssertionError):
                em.SimpleSEIRDModel(41, 2., 3., mortality, [None])
        draws = epidemic_batched(em.SimpleSIRModel(41, 3., [None]), {})
        assert_frequency(draws['R0'] <= 1., .5)
        assert_frequency(draws['rho'] <= .4, stats.beta.cdf(.4, 10, 10))


def test_overdispersed_transition_and_reporting_laws():
    with isolated_state(seed=1609, dtype=torch.float64):
        for cls in (em.OverdispersedSIRModel, em.OverdispersedSEIRModel):
            seir = cls is em.OverdispersedSEIRModel
            model = cls(41, 2.5, 3., [None]*3) if seir else cls(41, 3., [None]*3)
            edge = 'S2E' if seir else 'S2I'
            events = {edge+'_0': 5., 'I2R_0': 0., edge+'_1': 3., 'I2R_1': 0.}
            if seir:
                events.update({'E2I_0': 0., 'E2I_1': 3.})
            for dispersion in (0., .7):
                out, trace = epidemic_record(model, {'R0': 3., 'rho': .4, 'od': dispersion}, events)
                epidemic_score(trace, 'od', [.1, .3, .7], stats.beta.logpdf([.1, .3, .7], 2, 6))
                s, e, i = 40, 0, 1
                for t in range(3):
                    new = out[edge][t].item()
                    epidemic_count_law(trace, edge+'_{}'.format(t), s, 1-(1-3/(3*41))**i, dispersion)
                    epidemic_count_law(trace, 'I2R_{}'.format(t), i, 1/3, dispersion)
                    epidemic_count_law(trace, 'obs_{}'.format(t), new, .4, dispersion)
                    progress = new
                    if seir:
                        epidemic_count_law(trace, 'E2I_{}'.format(t), e, 1/2.5, dispersion)
                        progress = out['E2I'][t].item()
                    s, e, i = s-new, e+new-progress, i+progress-out['I2R'][t].item()
            prior_draws = epidemic_batched(model, {'R0': 3., 'rho': .4}, events)
            assert_frequency(prior_draws['od'] <= .3, stats.beta.cdf(.3, 2, 6))
            # Repeat actual generated counts, not merely distribution labels.
            draws = epidemic_batched(model, {'R0': 3., 'rho': .4, 'od': .7}, events)
            i = 4 if seir else 9
            p = 1-(1-3/(3*41))**i
            c = 1/(p*(1-p)*.7**2)-1
            reference = stats.betabinom(32, p*c, (1-p)*c)
            assert_frequency(draws[edge][:, 2] <= 2, reference.cdf(2))
            # Reporting has a fixed parent count in the conditioned middle step.
            c = 1/(.4*.6*.7**2)-1
            assert_frequency(draws['obs'][:, 1] == 0, stats.betabinom.pmf(0, 3, .4*c, .6*c))


def test_superspreading_infection_and_other_count_laws():
    with isolated_state(seed=1610, dtype=torch.float64):
        for cls in (em.SuperspreadingSIRModel, em.SuperspreadingSEIRModel):
            seir = cls is em.SuperspreadingSEIRModel
            model = cls(41, 2.5, 3., [None]*3) if seir else cls(41, 3., [None]*3)
            edge = 'S2E' if seir else 'S2I'
            events = {edge+'_0': 5., 'I2R_0': 0., edge+'_1': 3., 'I2R_1': 0.}
            if seir:
                events.update({'E2I_0': 0., 'E2I_1': 3.})
            out, trace = epidemic_record(model, {'R0': 3., 'rho': .4, 'k': .6}, events)
            epidemic_score(trace, 'k', [.15, .7, 2.], stats.expon.logpdf([.15, .7, 2.]))
            s, e, i = 40, 0, 1
            for t in range(3):
                p = 1-(1-3/41)**i
                new = out[edge][t].item()
                epidemic_count_law(trace, edge+'_{}'.format(t), s, p, concentration=.6*i)
                epidemic_count_law(trace, 'I2R_{}'.format(t), i, 1/3)
                epidemic_count_law(trace, 'obs_{}'.format(t), new, .4)
                progress = new
                if seir:
                    epidemic_count_law(trace, 'E2I_{}'.format(t), e, 1/2.5)
                    progress = out['E2I'][t].item()
                s, e, i = s-new, e+new-progress, i+progress-out['I2R'][t].item()
            prior_draws = epidemic_batched(model, {'R0': 3., 'rho': .4}, events)
            assert_frequency(prior_draws['k'] <= .7, stats.expon.cdf(.7))
            draws = epidemic_batched(model, {'R0': 3., 'rho': .4, 'k': .6}, events)
            i = 4 if seir else 9
            p = 1-(1-3/41)**i
            assert_frequency(draws[edge][:, 2] <= 2, stats.betabinom.cdf(2, 32, .6*i, .6*i*(1-p)/p))


def test_time_varying_single_population_model():
    with isolated_state(seed=1611, dtype=torch.float64):
        model = em.HeterogeneousSIRModel(41, 3., [None]*23)
        out, trace = epidemic_record(model, {'R0': 2., 'rho0': .2, 'rho1': .5, 'rho2': .8})
        for name, a, b in [('rho0', 2, 4), ('rho1', 4, 4), ('rho2', 8, 4)]:
            epidemic_score(trace, name, [.2, .5, .8], stats.beta.logpdf([.2, .5, .8], a, b))
        previous, s, i = 1., 40., 1.
        for t in range(23):
            epidemic_score(trace, 'beta_{}'.format(t), [.7, 1., 1.4],
                           stats.lognorm.logpdf([.7, 1., 1.4], .1, scale=previous))
            assert_close(out['Rt'][t], 2*out['beta'][t].item())
            reporting = .2 if t < 14 else .5 if t < 21 else .8
            epidemic_count_law(trace, 'obs_{}'.format(t), out['S2I'][t].item(), reporting)
            if i > 0:
                epidemic_count_law(trace, 'S2I_{}'.format(t), s, 1-(1-out['Rt'][t].item()/(3*41))**i)
            previous = out['beta'][t].item()
            s, i = out['S'][t].item(), out['I'][t].item()
        repeated = epidemic_repetitions(em.HeterogeneousSIRModel(41, 3., [None]*2), {'R0': .5})
        multipliers = np.stack([row['beta'].numpy() for row in repeated])
        increments = np.diff(np.log(multipliers), prepend=np.zeros((2048, 1)), axis=-1)
        epidemic_repeated_frequency(increments < -.05, stats.norm.cdf(-.5))
        epidemic_repeated_frequency((increments[:, 0] < -.05) & (increments[:, 1] < -.05), stats.norm.cdf(-.5)**2)
        for name, a, b in [('rho0', 2, 4), ('rho1', 4, 4), ('rho2', 8, 4)]:
            values = np.array([row[name].item() for row in repeated])
            epidemic_repeated_frequency(values < .4, stats.beta.cdf(.4, a, b))
        fitted = em.HeterogeneousSIRModel(41, 3., torch.zeros(22))
        epidemic_fit(fitted, 'mcmc', draws=8, steps=2)
        from velnora import poutine
        tr = invoke(poutine.trace(poutine.block(fitted.predict,
                    expose=['obs_22', 'obs_23', 'beta_22', 'beta_23'])).get_trace,
                    kwargs={'forecast': 2}).value
        result = tr.nodes['_RETURN']['value']
        assert result['beta'].shape == (8, 24)
        assert result['S'].shape == (8, 24)
        for t in (22, 23):
            actual = tr.nodes['obs_{}'.format(t)]['fn'].log_prob(torch.zeros(8, 1))
            expected = stats.binom.logpmf(0, result['S2I'][:, t].numpy(), result['rho2'].reshape(-1).numpy())
            np.testing.assert_allclose(actual.reshape(-1).numpy(), expected, rtol=3e-5, atol=3e-5)
            actual = tr.nodes['beta_{}'.format(t)]['fn'].log_prob(torch.ones(8, 1))
            expected = stats.lognorm.logpdf(1., .1, scale=result['beta'][:, t-1].numpy())
            np.testing.assert_allclose(actual.reshape(-1).numpy(), expected, rtol=3e-5, atol=3e-5)


def test_unknown_start_exposure_reporting_and_time_origin():
    with isolated_state(seed=1612, dtype=torch.float64):
        model = em.UnknownStartSIRModel(41, 3., 3, [None]*2)
        events = {'S2I_0': 1., 'S2I_1': 1., 'S2I_2': 1., 'I2R_0': 0., 'I2R_1': 0., 'I2R_2': 0.}
        out, trace = epidemic_record(model, {'R0': 2.4, 'rho0': .2, 'rho1': .7}, events)
        assert out['S'].shape == (5,)
        assert_close(out['obs'][:3], np.zeros(3))
        for name in ('rho0', 'rho1'):
            epidemic_score(trace, name, [.2, .5, .8], stats.beta.logpdf([.2, .5, .8], 10, 10))
        s, i = 41., 0.
        for t in range(5):
            external = 3/(2.4*3)
            p = 1-(1-2.4/(3*41))**(i+external)
            epidemic_count_law(trace, 'S2I_{}'.format(t), s, p)
            epidemic_count_law(trace, 'obs_{}'.format(t), out['S2I'][t].item(), .2 if t < 3 else .7)
            s, i = out['S'][t].item(), out['I'][t].item()
        fitted = em.UnknownStartSIRModel(30, 3., 3, torch.tensor([1., 1.]))
        result = epidemic_fit(fitted, 'mcmc', draws=16, steps=4)
        assert result['I'].shape == (16, 7)
        first = result['first_infection']
        assert first.shape == (16,)
        for history, time in zip(result['I'], first):
            t = int(time)
            assert 0 <= t < 5
            assert (history[:t] == 0).all() and history[t] > 0
        # Read forecast observation distributions from the public prediction call.
        from velnora import poutine
        tr = invoke(poutine.trace(poutine.block(fitted.predict, expose=['obs_5', 'obs_6'])).get_trace, kwargs={'forecast': 2}).value
        result = tr.nodes['_RETURN']['value']
        for t in (5, 6):
            values = torch.zeros_like(result['rho1'])
            actual = tr.nodes['obs_{}'.format(t)]['fn'].log_prob(values)
            expected = stats.binom.logpmf(0, result['S2I'][:, t].numpy(), result['rho1'].reshape(-1).numpy())
            np.testing.assert_allclose(actual.reshape(-1).numpy(), expected, rtol=3e-5, atol=3e-5)
        with pytest.raises(AssertionError):
            em.UnknownStartSIRModel(41, 3., 0, [None])


def test_regional_hierarchy_drift_and_coupling_validation():
    with isolated_state(seed=1613, dtype=torch.float64):
        for model in epidemic_families(3)[-2:]:
            out, trace = epidemic_record(model)
            epidemic_accounting(model, out)
            if isinstance(model, em.RegionalSIRModel):
                for name in ('rho_c1', 'rho_c0'):
                    epidemic_score(trace, name, [.5, 7., 14.], stats.gamma.logpdf([.5, 7., 14.], 10))
                values = np.array([[.2], [.5], [.8]])
                epidemic_score(trace, 'rho', values, np.broadcast_to(stats.beta.logpdf(values, out['rho_c1'].item(), out['rho_c0'].item()), (3, 2)))
            else:
                epidemic_score(trace, 'rho0', [[.2], [.5], [.8]], np.broadcast_to(stats.beta.logpdf(np.array([[.2], [.5], [.8]]), 4, 4), (3, 2)))
                for name in ('R_drift', 'rho_drift'):
                    epidemic_score(trace, name, [.02, .1, .3], stats.lognorm.logpdf([.02, .1, .3], 1, scale=np.exp(-3)))
                previous_r, previous_shift = 1., np.zeros(2)
                for t in range(3):
                    epidemic_score(trace, 'R_factor_{}'.format(t), [.7, 1., 1.4], stats.lognorm.logpdf([.7, 1., 1.4], out['R_drift'].item(), scale=previous_r))
                    values = np.array([[-.3], [0.], [.4]])
                    epidemic_score(trace, 'rho_shift_{}'.format(t), values, stats.norm.logpdf(values, previous_shift, out['rho_drift'].item()))
                    assert_close(out['Rt'][t], out['R0']*out['R_factor'][t])
                    baseline = out['rho0']
                    expected_rho = (baseline.log()-torch.log1p(-baseline)+out['rho_shift'][t]).sigmoid()
                    assert_close(out['rho'][t], expected_rho)
                    epidemic_count_law(trace, 'obs_{}'.format(t), out['S2I'][t].numpy(), expected_rho.numpy())
                    previous_r, previous_shift = out['R_factor'][t].item(), out['rho_shift'][t].numpy()
        population = torch.tensor([41., 67.])
        coupling = torch.tensor([[1., .2], [.3, 1.]])
        repeated = epidemic_repetitions(em.HeterogeneousRegionalSIRModel(population, coupling, 3., [None]*2),
                                        {'R0': .5, 'R_drift': .2, 'rho_drift': .3})
        factors = np.stack([row['R_factor'].numpy().reshape(2) for row in repeated])
        shifts = np.stack([row['rho_shift'].numpy() for row in repeated])
        log_steps = np.diff(np.log(factors), prepend=np.zeros((2048, 1)), axis=1)
        shift_steps = np.diff(shifts, prepend=np.zeros((2048, 1, 2)), axis=1)
        epidemic_repeated_frequency(log_steps < -.1, stats.norm.cdf(-.5))
        epidemic_repeated_frequency(shift_steps < -.15, stats.norm.cdf(-.5))
        epidemic_repeated_frequency((shift_steps[:, 0, 0] < -.15) & (shift_steps[:, 0, 1] < -.15), stats.norm.cdf(-.5)**2)
        for cls in (em.RegionalSIRModel, em.HeterogeneousRegionalSIRModel):
            for coupling in (torch.tensor([[1., -.1], [.2, 1.]]), torch.tensor([[1., .2], [1.1, 1.]])):
                with pytest.raises(AssertionError):
                    cls(torch.tensor([41., 67.]), coupling, 3., [None])
