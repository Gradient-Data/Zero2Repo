# feature: F11
"""Posterior laws, proposal correction, filtering, and streaming summaries."""
import math
import numpy as np
import pytest
import torch
import velnora
from scipy import stats
from velnora.infer import Importance, SMCFilter
from velnora.infer.smcfilter import SMCFailed
from velnora.infer.mcmc import HMC, NUTS, MCMC, StreamingMCMC, RandomWalkKernel
from _helpers import isolated_state, invoke
from velnora.ops.streaming import StatsOfDict, StackStats
from F01_helpers import assert_close
from F11_helpers import (posterior_chain, ChainRecorder, BinaryStateModel,
                         BinaryStateGuide, OverwritingGuide, ImpossibleEvidenceModel, DenseMoments, two_site_energy, SwitchableScore)


@pytest.fixture(autouse=True)
def posterior_state():
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        with isolated_state(seed=1111, dtype=torch.float64, device='cpu'):
            yield
    finally:
        torch.set_num_threads(threads)


def test_f11_t01(tmp_path):
    def model():
        p = velnora.sample('p', velnora.distributions.Beta(2., 3.))
        velnora.sample('obs', velnora.distributions.Binomial(10, p), obs=torch.tensor(9.))
    recorder = ChainRecorder(tmp_path)
    chain = posterior_chain(NUTS(model), draws=900, warmup=180, num_chains=2,
                            hook_fn=recorder)
    separate = chain.get_samples(group_by_chain=True)['p']
    combined = chain.get_samples()['p']
    assert separate.shape == (2, 900)
    assert combined.shape == (1800,)
    assert_close(combined.sort().values, separate.reshape(-1).sort().values.numpy())
    assert ((separate > 0) & (separate < 1)).all()
    warm_chains = recorder.read_chains('Warmup')
    sample_chains = recorder.read_chains('Sample')
    assert len(warm_chains) == len(sample_chains) == 2
    for warm, retained in zip(warm_chains, sample_chains):
        assert [r['index'] for r in warm] == list(range(180))
        assert [r['index'] for r in retained] == list(range(900))
        actual = torch.tensor([r['samples']['p'] for r in retained]).sigmoid()
        matches = [torch.allclose(row, actual, rtol=2e-6, atol=2e-7) for row in separate]
        assert sum(matches) == 1
        row = separate[matches.index(True)]
        # Broad CDF margins allow Monte Carlo error and serial correlation;
        # they reject the prior and wrong posterior concentration, not trajectories.
        for q in (.2, .5, .8):
            cutoff = stats.beta.ppf(q, 11, 4)
            assert abs((row < cutoff).double().mean().item()-q) < .10


def test_f11_t02():
    def mixture_model():
        x = velnora.sample('x', velnora.distributions.Normal(0., 1.))
        z = velnora.sample('z', velnora.distributions.Bernoulli(.85), infer={'enumerate': 'parallel'})
        velnora.sample('obs', velnora.distributions.Normal(x+3*z, .4), obs=torch.tensor(3.2))
    samples = posterior_chain(NUTS(mixture_model, max_plate_nesting=0), draws=2000).get_samples()
    assert set(samples) == {'x'}
    # Enumerate the two analytic normal-normal conditional laws independently.
    masses = np.array([.15, .85])*stats.norm.pdf(3.2, [0., 3.], math.sqrt(1.16))
    masses /= masses.sum()
    means = np.array([3.2, .2])/1.16
    sd = math.sqrt(.16/1.16)
    for cutoff in (-.1, .3, .7):
        target = np.dot(masses, stats.norm.cdf(cutoff, means, sd))
        assert abs((samples['x'] < cutoff).double().mean().item()-target) < .075

    def potential(values):
        return .5*((values['x']+1.7)/.6).square()
    draws = posterior_chain(HMC(potential_fn=potential, step_size=.3, num_steps=5),
                            initial_params={'x': torch.tensor(0.)}, draws=2000).get_samples()['x']
    for q in (.2, .5, .8):
        assert abs((draws < stats.norm.ppf(q, -1.7, .6)).double().mean().item()-q) < .075

    def normal_model():
        x = velnora.sample('x', velnora.distributions.Normal(0., 1.))
        velnora.sample('obs', velnora.distributions.Normal(x, .5), obs=torch.tensor(3.))
    draws = posterior_chain(RandomWalkKernel(normal_model, init_step_size=.8),
                            draws=6000, warmup=500).get_samples()['x']
    for q in (.2, .5, .8):
        assert abs((draws < stats.norm.ppf(q, 2.4, math.sqrt(.2))).double().mean().item()-q) < .085


def test_f11_t03(tmp_path):
    potential = two_site_energy
    initial = {'x': torch.tensor([-2., 3.]), 'y': torch.tensor([1., -1.])}
    recorder = ChainRecorder(tmp_path)
    # StreamingMCMC supports multiple chains sequentially, avoiding the
    # original parallel worker shared-kernel initialization bug.
    chain = StreamingMCMC(HMC(potential_fn=potential, step_size=.2, num_steps=3),
                          num_samples=30, warmup_steps=5, initial_params=initial,
                          save_params=['y'], num_chains=2, hook_fn=recorder,
                          statistics=StatsOfDict(default=StackStats), disable_progbar=True)
    invoke(chain.run, timeout=180)
    summaries = chain.get_statistics()
    assert set(summaries) == {(0, 'y'), (1, 'y')}
    retained = {'y': torch.stack([summaries[c, 'y']['samples'] for c in range(2)])}
    assert retained['y'].shape == (2, 30)
    warm_chains = recorder.read_chains('Warmup')
    sample_chains = recorder.read_chains('Sample')
    assert len(warm_chains) == len(sample_chains) == 2
    for warm, samples in zip(warm_chains, sample_chains):
        first = warm[0]
        c = initial['x'].tolist().index(first['initial']['x'])
        for name in initial:
            assert first['initial'][name] == initial[name][c].item()
        assert_close(retained['y'][c], np.array([r['samples']['y'] for r in samples]))
    single = posterior_chain(HMC(potential_fn=potential, step_size=.2, num_steps=3),
                             draws=25, warmup=4, save_params=['y'],
                             initial_params={k: v[0] for k, v in initial.items()})
    assert set(single.get_samples()) == {'y'}
    assert single.get_samples()['y'].shape == (25,)
    with pytest.raises(ValueError):
        MCMC(HMC(potential_fn=potential), num_samples=3, num_chains=2,
             initial_params={'x': torch.zeros(3), 'y': torch.zeros(3)})
    with pytest.raises(ValueError):
        MCMC(HMC(potential_fn=potential), num_samples=3)

    def impossible_model():
        x = velnora.sample('x', velnora.distributions.Normal(0., 1.))
        velnora.factor('impossible', x*0-torch.inf)
    with pytest.raises(ValueError):
        posterior_chain(NUTS(impossible_model), draws=3, warmup=1)

    def invalid_gradient_model():
        x = velnora.sample('x', velnora.distributions.Normal(0., 1.))
        # Finite score, undefined derivative at every point.
        velnora.factor('bad_derivative', torch.sqrt((x-x).abs()))
    with pytest.raises(ValueError):
        posterior_chain(NUTS(invalid_gradient_model), draws=3, warmup=1)


def test_f11_t04():
    def model():
        x = velnora.sample('x', velnora.distributions.Bernoulli(.3))
        velnora.sample('obs', velnora.distributions.Bernoulli(.1+.8*x), obs=torch.tensor(1.))
    def guide():
        velnora.sample('x', velnora.distributions.Bernoulli(.65))
    for proposal, probability in ((guide, .65), (None, .3)):
        posterior = Importance(model, guide=proposal, num_samples=4000)
        invoke(posterior.run, timeout=120)
        x = torch.stack([t.nodes['x']['value'] for t in posterior.exec_traces])
        weights = torch.stack(posterior.log_weights)
        assert x.shape == weights.shape == (4000,)
        assert abs(x.mean().item()-probability) < .04
        ratio = torch.where(x.bool(), torch.tensor(.3*.9/probability),
                            torch.tensor(.7*.1/(1-probability)))
        assert_close(weights, ratio.log().numpy())
        normalized = posterior.get_normalized_weights()
        assert_close(normalized, (ratio/ratio.sum()).numpy())
        assert_close(posterior.get_log_normalizer(), ratio.mean().log().numpy())
        assert abs((normalized*x).sum().item()-(.27/.34)) < .04
        assert abs(posterior.get_log_normalizer().exp().item()-.34) < .03


def test_f11_t05():
    filtering = SMCFilter(BinaryStateModel(), BinaryStateGuide(), 12000, 0)
    invoke(filtering.init)
    prior = filtering.get_empirical()
    assert abs(prior['x'].mean.item()-.3) < .035
    odds = .3/.7
    for observation in (1, 1, 0):
        invoke(filtering.step, observation)
        odds *= (.85/.15) if observation else (.15/.85)
        empirical = filtering.get_empirical()
        target = odds/(1+odds)
        assert abs(empirical['x'].mean.item()-target) < .035
        assert_close(empirical['pair'].mean, [empirical['x'].mean.item(), 1-empirical['x'].mean.item()])
        # The joint-valued state must retain its component relation even after
        # resampling, not merely have the correct two marginal means.
        joint = empirical['pair'].sample((3000,))
        assert ((joint[:, 0] == 0) | (joint[:, 0] == 1)).all()
        assert_close(joint.sum(-1), np.ones(3000))
    blocked = SMCFilter(BinaryStateModel(), OverwritingGuide(), 100, 0)
    invoke(blocked.init)
    with pytest.raises(RuntimeError):
        invoke(blocked.step, 1)


def test_f11_t06():
    for count in (0, -3):
        with pytest.raises(AssertionError):
            SMCFilter(BinaryStateModel(), BinaryStateGuide(), count, 0)
    filtering = SMCFilter(ImpossibleEvidenceModel(), BinaryStateGuide(), 1000, 0)
    invoke(filtering.init)
    invoke(filtering.step, 0)
    assert abs(filtering.get_empirical()['x'].mean.item()-.3) < .07
    with pytest.raises(SMCFailed):
        invoke(filtering.step, 1)


def test_f11_t07():
    recorded = {0: [], 1: []}
    warmup = {0: [], 1: []}
    def hook(kernel, samples, stage, index):
        for c in range(2):
            if stage == 'Sample [{}]'.format(c):
                recorded[c].append(samples['x'].detach().clone())
            elif stage == 'Warmup [{}]'.format(c):
                warmup[c].append(samples['x'].detach().clone())
    def potential(values):
        x = values['x']
        return .5*((x[0]-1).square()+((x[1]+.7*x[0]+2)/.6).square())
    chain = StreamingMCMC(NUTS(potential_fn=potential), num_samples=300,
                          warmup_steps=70, num_chains=2,
                          initial_params={'x': torch.tensor([[-3., 4.], [5., -4.]])},
                          hook_fn=hook, disable_progbar=True)
    invoke(chain.run, timeout=180)
    separate = chain.get_statistics()
    for c in range(2):
        assert len(warmup[c]) == 70
        values = torch.stack(recorded[c])
        summary = separate[c, 'x']
        assert values.shape == (300, 2)
        assert summary['count'] == 300
        assert_close(summary['mean'], values.mean(0).numpy())
        assert_close(summary['variance'], values.var(0, unbiased=True).numpy())
    combined = chain.get_statistics(group_by_chain=False)['x']
    values = torch.stack(recorded[0]+recorded[1])
    assert combined['count'] == 600
    assert_close(combined['mean'], values.mean(0).numpy())
    assert_close(combined['variance'], values.var(0, unbiased=True).numpy())

    # User-supplied statistics exercise the public aggregation protocol.
    recorded = {0: [], 1: []}
    warmup = {0: [], 1: []}
    chain = StreamingMCMC(NUTS(potential_fn=potential), num_samples=160,
                          warmup_steps=40, num_chains=2,
                          statistics=StatsOfDict(default=DenseMoments),
                          initial_params={'x': torch.tensor([[-3., 4.], [5., -4.]])},
                          hook_fn=hook, disable_progbar=True)
    invoke(chain.run, timeout=180)
    separate = chain.get_statistics()
    for c in range(2):
        values = torch.stack(recorded[c])
        summary = separate[c, 'x']
        assert values.shape == (160, 2)
        assert summary['count'] == 160
        assert_close(summary['mean'], values.mean(0).numpy())
        assert_close(summary['covariance'], np.cov(values.numpy(), rowvar=False))
    combined = chain.get_statistics(group_by_chain=False)['x']
    values = torch.stack(recorded[0]+recorded[1])
    assert combined['count'] == 320
    assert_close(combined['mean'], values.mean(0).numpy())
    assert_close(combined['covariance'], np.cov(values.numpy(), rowvar=False))


def test_derivative_free_transitions_after_initialization():
    availability = {'enabled': True, 'evaluations': 0}
    callbacks = []

    def model():
        value = velnora.sample('x', velnora.distributions.Normal(0., 1.))
        velnora.factor('observation', SwitchableScore.apply(value, availability))

    def disable_derivatives(kernel, samples, stage, index):
        availability['enabled'] = False
        callbacks.append((stage, index))

    draws = posterior_chain(RandomWalkKernel(model, init_step_size=.8),
                            draws=6000, warmup=500,
                            hook_fn=disable_derivatives).get_samples()['x']
    assert len(callbacks) == 6500
    assert draws.shape == (6000,) and torch.isfinite(draws).all()
    for q in (.2, .5, .8):
        assert abs((draws < stats.norm.ppf(q, 2.4, math.sqrt(.2))).double().mean().item()-q) < .085
