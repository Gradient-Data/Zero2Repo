# feature: F10
"""Exact finite marginalization and conditional joint-state acceptance tests."""
import math
from itertools import product
import numpy as np
import pytest
import torch
import velnora
from velnora.infer import TraceEnum_ELBO, infer_discrete
from velnora.ops.indexing import Vindex
from _helpers import isolated_state
from F01_helpers import assert_close, assert_frequency, SAMPLE_COUNT
from F05_helpers import finite_state_evidence
from F10_helpers import empty_guide, pair_problem, chain_problem


@pytest.fixture(autouse=True)
def enumeration_state():
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        with isolated_state(seed=1010, dtype=torch.float64, device='cpu'):
            yield
    finally:
        torch.set_num_threads(threads)


def test_f10_t01():
    probabilities = torch.tensor([[.15, .7, .4], [.8, .25, .6]])
    for logit in (-.8, .5):
        theta = torch.tensor(logit, requires_grad=True)
        def model():
            with velnora.plate('outer', 2, dim=-2):
                with velnora.plate('inner', 3, dim=-1):
                    z = velnora.sample('z', velnora.distributions.Bernoulli(logits=theta), infer={'enumerate': 'parallel'})
                    velnora.sample('obs', velnora.distributions.Bernoulli(.1+probabilities*z), obs=torch.ones(2, 3))
        objective = TraceEnum_ELBO(max_plate_nesting=2)
        actual = objective.differentiable_loss(model, empty_guide)
        p = theta.sigmoid()
        expected = -(.1+p*probabilities).log().sum()
        assert_close(actual, expected.detach().numpy())
        assert_close(torch.autograd.grad(actual, theta)[0], torch.autograd.grad(expected, theta)[0].numpy())

        qlogit = torch.tensor(.3, requires_grad=True)
        def guide():
            with velnora.plate('outer', 2, dim=-2):
                with velnora.plate('inner', 3, dim=-1):
                    velnora.sample('z', velnora.distributions.Bernoulli(logits=qlogit), infer={'enumerate': 'parallel'})
        actual = objective.differentiable_loss(model, guide)
        p = theta.sigmoid()
        q = qlogit.sigmoid()
        expected = (q*(q.log()-p.log()-(.1+probabilities).log())
                    +(1-q)*((1-q).log()-(1-p).log()-math.log(.1))).sum()
        assert_close(actual, expected.detach().numpy())
        measured = torch.autograd.grad(actual, (theta, qlogit))
        wanted = torch.autograd.grad(expected, (theta, qlogit))
        for a, b in zip(measured, wanted):
            assert_close(a, b.numpy())


def test_f10_t02():
    prior, proposal = .35, .6
    conditional = torch.tensor([.2, .8])
    qconditional = torch.tensor([.7, .3])
    likelihood = torch.tensor([[.1, .6], [.8, .3]])
    expected = 0.
    for x, y in product(range(2), repeat=2):
        p = (prior if x else 1-prior)*(conditional[x].item() if y else 1-conditional[x].item())*likelihood[x, y].item()
        q = (proposal if x else 1-proposal)*(qconditional[x].item() if y else 1-qconditional[x].item())
        expected += q*math.log(q/p)
    for mode in ('sequential', 'parallel'):
        def model():
            x = velnora.sample('x', velnora.distributions.Bernoulli(prior)).long()
            y = velnora.sample('y', velnora.distributions.Bernoulli(conditional[x])).long()
            velnora.sample('obs', velnora.distributions.Bernoulli(Vindex(likelihood)[x, y]), obs=torch.tensor(1.))
            return x, y
        def guide():
            x = velnora.sample('x', velnora.distributions.Bernoulli(proposal), infer={'enumerate': mode}).long()
            if mode == 'sequential':
                probability = qconditional[1] if x.item() else qconditional[0]
            else:
                probability = qconditional[x]
            y = velnora.sample('y', velnora.distributions.Bernoulli(probability), infer={'enumerate': mode})
            return x, y
        assert TraceEnum_ELBO(max_plate_nesting=0).loss(model, guide) == pytest.approx(expected)
    valid, _, evidence = pair_problem()
    assert TraceEnum_ELBO(max_plate_nesting=0).loss(valid, empty_guide) == pytest.approx(-math.log(evidence))
    def unsupported():
        velnora.sample('z', velnora.distributions.Bernoulli(.4), infer={'enumerate': 'sequential'})
    with pytest.raises(NotImplementedError):
        TraceEnum_ELBO(max_plate_nesting=0).loss(unsupported, empty_guide)


def test_f10_t03():
    # Independent population members supply independent joint posterior draws.
    # Reuse the shared Hoeffding bound; no exact random sequence is required.
    for observation in (0, 1):
        model, posterior, _ = pair_problem(observation, SAMPLE_COUNT)
        for options in ({}, {'temperature': 1}):
            x, y = infer_discrete(model, first_available_dim=-2, **options)()
            assert x.shape == y.shape == (SAMPLE_COUNT,)
            assert bool(((x >= 0) & (x < 2) & (y >= 0) & (y < 2)).all())
            for a, b in product(range(2), repeat=2):
                assert_frequency((x == a) & (y == b), posterior[a, b])


def test_f10_t04():
    for observation in (0, 1):
        model, posterior, _ = pair_problem(observation)
        x, y = infer_discrete(model, first_available_dim=-1, temperature=0)()
        assert posterior[int(x), int(y)] == posterior.max()
    model, _, _ = pair_problem()
    for temperature in (-1, .5, 2):
        with pytest.raises(ValueError):
            infer_discrete(model, first_available_dim=-1, temperature=temperature)()


def test_f10_t05():
    likelihood = torch.tensor([[.2, .7, .9], [.8, .3, .1]])
    priors = torch.tensor([[.1, .3, .6], [.6, .25, .15]])
    observations = torch.tensor([1., 0.])
    def model():
        with velnora.plate('population', 2, dim=-1):
            x = velnora.sample('x', velnora.distributions.Categorical(priors), infer={'enumerate': 'parallel'})
            p = Vindex(likelihood)[torch.arange(2), x]
            velnora.sample('obs', velnora.distributions.Bernoulli(p), obs=observations)
    marginals = TraceEnum_ELBO(max_plate_nesting=1).compute_marginals(model, empty_guide)
    assert set(marginals) == {'x'}
    expected = priors.numpy()*np.stack([likelihood[0].numpy(), 1-likelihood[1].numpy()])
    expected /= expected.sum(-1, keepdims=True)
    assert marginals['x'].probs.shape == (2, 3)
    assert_close(marginals['x'].probs, expected)
    assert_close(marginals['x'].probs.sum(-1), np.ones(2))
    pair, posterior, _ = pair_problem()
    marginals = TraceEnum_ELBO(max_plate_nesting=0).compute_marginals(pair, empty_guide)
    assert set(marginals) == {'x', 'y'}
    assert_close(marginals['x'].probs, posterior.sum(1))
    assert_close(marginals['y'].probs, posterior.sum(0))


def test_f10_t06():
    for observations in ([0, 1, 1, 1], [0, 1, 1, 0]):
        model, paths, masses, transition, emission = chain_problem(observations)
        evidence = finite_state_evidence((0,), 2, observations,
            lambda history, state: transition[history[-1], state],
            lambda state, obs: emission[state] if obs else 1-emission[state])
        assert TraceEnum_ELBO(max_plate_nesting=0).loss(model, empty_guide) == pytest.approx(-math.log(evidence))
        assignment = infer_discrete(model, first_available_dim=-1, temperature=0)()
        path = tuple(int(x) for x in assignment)
        assert masses[paths.index(path)] == masses.max()
        batched, _, _, _, _ = chain_problem(observations, SAMPLE_COUNT)
        draws = infer_discrete(batched, first_available_dim=-2)()
        for path, probability in zip(paths, masses/masses.sum()):
            indicator = torch.ones(SAMPLE_COUNT, dtype=torch.bool)
            for state, wanted in zip(draws, path):
                assert state.shape == (SAMPLE_COUNT,)
                indicator &= state == wanted
            assert_frequency(indicator, probability)


def test_f10_t07():
    for scale in (1., 2.5, torch.tensor(1.7)):
        model, posterior, evidence = pair_problem(size=3)
        scaled = velnora.poutine.scale(model, scale=scale)
        assert TraceEnum_ELBO(max_plate_nesting=1).loss(scaled, empty_guide) == pytest.approx(-3*float(scale)*math.log(evidence))
        for dimension in (-2, -3):
            x, y = infer_discrete(model, first_available_dim=dimension, temperature=0)()
            assert x.shape == y.shape == (3,)
            assert np.all(posterior[x.numpy(), y.numpy()] == posterior.max())
    model, _, _ = pair_problem()
    for dimension in (0, 1):
        with pytest.raises(AssertionError):
            infer_discrete(model, first_available_dim=dimension)()
    def inconsistent(scale):
        x = velnora.sample('x', velnora.distributions.Bernoulli(.4), infer={'enumerate': 'parallel'})
        with velnora.poutine.scale(scale=scale):
            velnora.sample('obs', velnora.distributions.Bernoulli(.2+.6*x), obs=torch.tensor(1.))
    assert TraceEnum_ELBO(max_plate_nesting=0).loss(lambda: inconsistent(1.), empty_guide) == pytest.approx(-math.log(.44))
    for scale in (2., torch.tensor([1., 1.])):
        with pytest.raises(ValueError):
            TraceEnum_ELBO(max_plate_nesting=0).loss(lambda: inconsistent(scale), empty_guide)
