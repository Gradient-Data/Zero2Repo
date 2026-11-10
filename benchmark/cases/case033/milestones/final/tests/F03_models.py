# feature: F03
"""Acceptance checks for executable probabilistic programs."""
import random

import numpy as np
import pytest
import torch
from scipy import stats
import velnora

from _helpers import isolated_state
from F01_helpers import SAMPLE_COUNT, assert_close, assert_frequency


@pytest.fixture(autouse=True)
def model_state():
    with isolated_state(validation=True, dtype=torch.float64, device='cpu'):
        yield


def test_f03_t01():
    def model(evidence):
        gate = velnora.sample('gate', velnora.distributions.Bernoulli(.35), obs=evidence)
        values = []
        for index in range(3 if gate.item() else 2):
            location = index + 2 * gate
            values.append(velnora.sample('choice_{}'.format(index),
                                      velnora.distributions.Normal(location, .8).expand((SAMPLE_COUNT,))))
        observed = velnora.sample('evidence', velnora.distributions.Normal(values[-1], 1.3),
                               obs=torch.tensor(-.6))
        return gate, values, observed, values[-1].square() + observed

    for evidence in (torch.tensor(0.), torch.tensor(1.)):
        execution = velnora.poutine.trace(model).get_trace(evidence)
        gate, values, observed, calculation = execution.nodes['_RETURN']['value']
        assert_close(gate, evidence.numpy())
        assert_close(observed, -.6)
        assert len(values) == (3 if evidence.item() else 2)
        assert_close(calculation, values[-1].square().numpy() - .6)
        execution.compute_log_prob()
        expected = stats.bernoulli.logpmf(evidence.item(), .35)
        for index, value in enumerate(values):
            location = index + 2 * evidence.item()
            assert value.shape == (SAMPLE_COUNT,)
            assert_frequency(value <= location + .4, stats.norm.cdf(.5))
            score = stats.norm.logpdf(value.numpy(), location, .8)
            assert_close(execution.nodes['choice_{}'.format(index)]['log_prob'], score)
            expected += score.sum()
        likelihood = stats.norm.logpdf(-.6, values[-1].numpy(), 1.3)
        assert_close(execution.nodes['evidence']['log_prob'], likelihood)
        expected += likelihood.sum()
        assert_close(execution.log_prob_sum(), expected)


def test_f03_t02():
    observation = torch.tensor([[7., 8., 9.], [-7., -8., -9.]])
    locations = torch.tensor([[.2, -.4, .7], [1.2, -.8, 2.]])
    law = velnora.distributions.Normal(locations, .9).expand((SAMPLE_COUNT, 2, 3)).to_event(1)
    # Mixed and scalar masks exercise broadcasting over batch axes while an
    # event's coordinates remain together. Frequencies reuse the F01 bound.
    for mask in (torch.tensor([True, False]), torch.tensor(False), torch.tensor(True)):
        def model():
            return velnora.sample('partial', law, obs=observation, obs_mask=mask)

        execution = velnora.poutine.trace(model).get_trace()
        value = execution.nodes['_RETURN']['value']
        assert value.shape == (SAMPLE_COUNT, 2, 3)
        assert_close(execution.nodes['partial']['value'], value.numpy())
        selected = mask.expand(2)
        for member in range(2):
            if selected[member]:
                assert_close(value[:, member], np.broadcast_to(observation[member].numpy(), (SAMPLE_COUNT, 3)))
            else:
                assert_frequency(value[:, member] <= locations[member], .5)
                assert_frequency((value[:, member] <= locations[member]).all(-1), .125)
    with pytest.raises(ValueError):
        velnora.sample('invalid_partial', velnora.distributions.Normal(locations, .9).to_event(1),
                    obs=observation, obs_mask=torch.tensor([True, False, True]))


def test_f03_t03():
    observation = torch.tensor([-.4, 1.7])

    def model(factors, record):
        value = velnora.sample('data', velnora.distributions.Normal(.3, 1.2).expand((2,)).to_event(1), obs=observation)
        for index, factor in enumerate(factors):
            velnora.factor('weight_{}'.format(index), factor)
        derived = torch.stack((value.square(), value + 2))
        if record:
            returned = velnora.deterministic('derived', derived)
            assert_close(returned, derived.numpy())
            velnora.deterministic('per_member', value * 3, event_dim=0)
        return derived

    baseline = stats.norm.logpdf(observation.numpy(), .3, 1.2).sum()
    for factors in ([], [torch.tensor(-2.3)], [torch.tensor([.7, -1.2]), torch.tensor(1.4)]):
        expected = baseline + sum(factor.sum().item() for factor in factors)
        for record in (False, True):
            execution = velnora.poutine.trace(model).get_trace(factors, record)
            derived = np.stack((observation.numpy() ** 2, observation.numpy() + 2))
            assert_close(execution.nodes['_RETURN']['value'], derived)
            if record:
                assert_close(execution.nodes['derived']['value'], derived)
                assert_close(execution.nodes['per_member']['value'], observation.numpy() * 3)
            assert_close(execution.log_prob_sum(), expected)


def test_f03_t04():
    def model():
        return (velnora.sample('noise', velnora.distributions.Normal(0., 1.).expand((64,))),
                np.random.random(64), np.array([random.random() for _ in range(64)]))

    def same(left, right):
        assert torch.equal(left[0], right[0])
        np.testing.assert_array_equal(left[1], right[1])
        np.testing.assert_array_equal(left[2], right[2])

    velnora.set_rng_seed(382)
    first, second = model(), model()
    velnora.set_rng_seed(382)
    same(first, model())
    same(second, model())
    # A constant generator cannot satisfy either the law or advancement check.
    assert not torch.equal(first[0], second[0])
    velnora.set_rng_seed(927)
    alternate = model()
    assert not torch.equal(first[0], alternate[0])
    # Check the distribution through the model, without pinning seeded values.
    samples = velnora.sample('many', velnora.distributions.Normal(0., 1.).expand((SAMPLE_COUNT,)))
    assert_frequency(samples <= 0., .5)
    assert_frequency(samples <= 1., stats.norm.cdf(1.))

    for abort in (False, True):
        velnora.set_rng_seed(115)
        before, after = model(), model()
        velnora.set_rng_seed(115)
        same(before, model())
        try:
            with velnora.poutine.seed(rng_seed=618):
                local = model()
                with velnora.poutine.seed(rng_seed=932):
                    model()
                if abort:
                    raise RuntimeError('Scope exit probe')
        except RuntimeError as error:
            if not abort:
                raise
            assert str(error) == 'Scope exit probe'
        same(after, model())
        same(local, velnora.poutine.seed(model, rng_seed=618)())


def test_f03_t05():
    def valid():
        assert_close(velnora.distributions.Normal(.2, .9).log_prob(torch.tensor(.6)), stats.norm.logpdf(.6, .2, .9))

    def invalid():
        return velnora.distributions.Normal(torch.tensor(0.), torch.tensor(-1.))

    for global_choice in (True, False):
        velnora.enable_validation(global_choice)
        valid()
        if global_choice:
            with pytest.raises(ValueError):
                invalid()
        else:
            invalid()  # Only acceptance is required; no invalid score is pinned.
        for abort in (False, True):
            try:
                with velnora.validation_enabled(not global_choice):
                    valid()
                    if global_choice:
                        invalid()
                    else:
                        with pytest.raises(ValueError):
                            invalid()
                    with velnora.validation_enabled(global_choice):
                        if global_choice:
                            with pytest.raises(ValueError):
                                invalid()
                        else:
                            invalid()
                    if global_choice:
                        invalid()
                    else:
                        with pytest.raises(ValueError):
                            invalid()
                    if abort:
                        raise RuntimeError('Scope exit probe')
            except RuntimeError as error:
                if not abort:
                    raise
                assert str(error) == 'Scope exit probe'
            valid()
            if global_choice:
                with pytest.raises(ValueError):
                    invalid()
            else:
                invalid()
