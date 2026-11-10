# feature: F04
"""Acceptance checks for execution inspection and program controls."""
import numpy as np
import pytest
import torch
from scipy import stats
import velnora

from _helpers import isolated_state
from F01_helpers import SAMPLE_COUNT, assert_close, assert_frequency


@pytest.fixture(autouse=True)
def control_state():
    with isolated_state(validation=True, dtype=torch.float64, device='cpu'):
        yield


def test_f04_t01():
    def model(repeat=False):
        bias = velnora.param('bias', torch.tensor(.4))
        latent = velnora.sample('latent', velnora.distributions.Normal(bias, 1.2))
        observed = velnora.sample('data', velnora.distributions.Normal(latent, .7), obs=torch.tensor([-.2, 1.1]))
        derived = velnora.deterministic('derived', latent.square() + observed)
        if repeat:
            velnora.sample('latent', velnora.distributions.Normal(0., 1.))
        return derived.sum()

    execution = velnora.poutine.trace(model).get_trace()
    nodes = execution.nodes
    assert {'bias', 'latent', 'data', 'derived', '_RETURN'} <= set(nodes)
    assert nodes['bias']['type'] == 'param'
    assert nodes['latent']['type'] == nodes['data']['type'] == 'sample'
    assert not nodes['latent']['is_observed']
    assert nodes['data']['is_observed']
    assert_close(nodes['bias']['value'], .4)
    latent = nodes['latent']['value'].item()
    assert_close(nodes['data']['value'], [-.2, 1.1])
    assert_close(nodes['derived']['value'], latent ** 2 + np.array([-.2, 1.1]))
    assert_close(nodes['_RETURN']['value'], 2 * latent ** 2 + .9)
    execution.compute_log_prob()
    prior = stats.norm.logpdf(latent, .4, 1.2)
    likelihood = stats.norm.logpdf([-.2, 1.1], latent, .7)
    assert_close(nodes['latent']['log_prob'], prior)
    assert_close(nodes['data']['log_prob'], likelihood)
    assert_close(nodes['derived']['log_prob'].sum(), 0.)
    assert_close(execution.log_prob_sum(), prior + likelihood.sum())
    with pytest.raises(RuntimeError):
        velnora.poutine.trace(model).get_trace(True)


def test_f04_t02():
    selected = torch.full((SAMPLE_COUNT,), 2.4)

    def model(obs=None):
        first = velnora.sample('first', velnora.distributions.Normal(-.3, .8).expand((SAMPLE_COUNT,)), obs=obs)
        other = velnora.sample('other', velnora.distributions.Normal(1.2, .6).expand((SAMPLE_COUNT,)))
        return first + 2 * other

    conditioned = velnora.poutine.condition(model, data={'first': selected})
    evidence = velnora.poutine.trace(conditioned).get_trace(torch.tensor(-4.))
    assert evidence.nodes['first']['is_observed']
    assert_close(evidence.nodes['first']['value'], selected.numpy())
    assert_frequency(evidence.nodes['other']['value'] <= 1.2, .5)
    assert_close(evidence.nodes['_RETURN']['value'], selected.numpy() + 2 * evidence.nodes['other']['value'].numpy())
    evidence.compute_log_prob()
    assert_close(evidence.nodes['first']['log_prob'], stats.norm.logpdf(selected.numpy(), -.3, .8))
    released = velnora.poutine.trace(velnora.poutine.uncondition(conditioned)).get_trace()
    assert not released.nodes['first']['is_observed']
    assert_frequency(released.nodes['first']['value'] <= -.3, .5)
    released.compute_log_prob()
    assert_close(released.nodes['first']['log_prob'], stats.norm.logpdf(released.nodes['first']['value'].numpy(), -.3, .8))

    def source():
        return velnora.sample('first', velnora.distributions.Normal(3., 1.).expand((SAMPLE_COUNT,)))

    previous = velnora.poutine.trace(source).get_trace()
    replayed = velnora.poutine.replay(model, trace=previous)
    for observation in (None, torch.tensor(-1.7)):
        execution = velnora.poutine.trace(replayed).get_trace(observation)
        first = execution.nodes['first']
        expected = previous.nodes['first']['value'].numpy() if observation is None else -1.7
        assert_close(first['value'], expected)
        assert first['is_observed'] == (observation is not None)
        assert_frequency(execution.nodes['other']['value'] <= 1.2, .5)
        assert_close(execution.nodes['_RETURN']['value'], expected + 2 * execution.nodes['other']['value'].numpy())
        execution.compute_log_prob()
        first_score = np.broadcast_to(stats.norm.logpdf(first['value'].numpy(), -.3, .8), (SAMPLE_COUNT,))
        other_score = stats.norm.logpdf(execution.nodes['other']['value'].numpy(), 1.2, .6)
        assert_close(first['log_prob'], first_score)
        assert_close(execution.log_prob_sum(), first_score.sum() + other_score.sum())


def test_f04_t03():
    def model(observation=None):
        parent = velnora.sample('parent', velnora.distributions.Normal(.2, 1.1).expand((SAMPLE_COUNT,)))
        child = velnora.sample('child', velnora.distributions.Normal(parent, .8), obs=observation)
        result = velnora.sample('result', velnora.distributions.Normal(child, .6), obs=torch.tensor(-.4))
        return parent, child, child.square() + result

    intervention = torch.tensor(2.3)
    for observation in (None, torch.tensor(-1.2)):
        execution = velnora.poutine.trace(velnora.poutine.do(model, data={'child': intervention})).get_trace(observation)
        parent, child, result = execution.nodes['_RETURN']['value']
        assert_close(child, 2.3)
        assert_close(result, 2.3 ** 2 - .4)
        # Intervention must not update the parent law, including under conflicting evidence.
        assert_frequency(parent <= .2, .5)
        factual = execution.nodes['child']
        assert factual['is_observed'] == (observation is not None)
        if observation is not None:
            assert_close(factual['value'], -1.2)
        else:
            assert_frequency(factual['value'] - parent <= 0., .5)
        execution.compute_log_prob()
        parent_score = stats.norm.logpdf(parent.numpy(), .2, 1.1)
        factual_score = stats.norm.logpdf(factual['value'].numpy(), parent.numpy(), .8)
        result_score = stats.norm.logpdf(-.4, 2.3, .6)
        assert_close(execution.nodes['parent']['log_prob'], parent_score)
        assert_close(factual['log_prob'], factual_score)
        assert_close(execution.nodes['result']['log_prob'], result_score)
        assert_close(execution.log_prob_sum(), parent_score.sum() + factual_score.sum() + result_score)


def test_f04_t04():
    def model():
        hidden = velnora.sample('hidden', velnora.distributions.Normal(.4, .7), obs=torch.tensor(1.3))
        visible = velnora.sample('visible', velnora.distributions.Normal(hidden, .5), obs=torch.tensor(-.6))
        return hidden.square() + visible

    for hide in ([], ['hidden']):
        inner = velnora.poutine.trace(model)
        outer = velnora.poutine.trace(velnora.poutine.block(inner, hide=hide)).get_trace()
        assert_close(outer.nodes['_RETURN']['value'], 1.3 ** 2 - .6)
        assert {'hidden', 'visible'} <= set(inner.trace.nodes)
        assert ('hidden' in outer.nodes) == (not hide)
        assert 'visible' in outer.nodes
        assert_close(inner.trace.nodes['hidden']['value'], 1.3)
        assert_close(outer.nodes['visible']['value'], -.6)
        expected = stats.norm.logpdf(-.6, 1.3, .5)
        if not hide:
            expected += stats.norm.logpdf(1.3, .4, .7)
        assert_close(outer.log_prob_sum(), expected)


def test_f04_t05():
    def model():
        first = velnora.param('first', torch.tensor(.7))
        other = velnora.param('other', torch.tensor(-.4))
        again = velnora.param('first')
        return first * other + again.square()

    assert_close(model(), .7 * -.4 + .7 ** 2)
    before = {name: value.detach().clone() for name, value in velnora.get_param_store().items()}
    for replacement in (-1.2, 2.6):
        wrapped = velnora.poutine.substitute(model, data={'first': torch.tensor(replacement)})
        execution = velnora.poutine.trace(wrapped).get_trace()
        assert_close(execution.nodes['_RETURN']['value'], replacement * -.4 + replacement ** 2)
        assert_close(execution.nodes['first']['value'], replacement)
        assert_close(execution.nodes['other']['value'], -.4)
        assert set(velnora.get_param_store().keys()) == set(before)
        for name, value in before.items():
            assert_close(velnora.get_param_store()[name], value.numpy())
        assert_close(model(), .7 * -.4 + .7 ** 2)


def test_f04_t06():
    values = torch.tensor([-.8, .2, 1.4, 2.1])
    outer_mask = torch.tensor([True, True, False, False])
    inner_mask = torch.tensor([True, False, True, False])
    raw = stats.norm.logpdf(values.numpy(), .3, 1.2)

    def model(controlled):
        velnora.sample('outside', velnora.distributions.Normal(.3, 1.2), obs=values)
        if controlled:
            with velnora.poutine.scale(scale=2.5), velnora.poutine.mask(mask=outer_mask):
                velnora.sample('outer', velnora.distributions.Normal(.3, 1.2), obs=values)
                with velnora.poutine.scale(scale=torch.tensor([.4, .8, 1.2, 1.6])), velnora.poutine.mask(mask=inner_mask):
                    velnora.sample('inner', velnora.distributions.Normal(.3, 1.2), obs=values)
        else:
            velnora.sample('outer', velnora.distributions.Normal(.3, 1.2), obs=values)
            velnora.sample('inner', velnora.distributions.Normal(.3, 1.2), obs=values)
        velnora.sample('after', velnora.distributions.Normal(.3, 1.2), obs=values)

    for controlled in (False, True):
        execution = velnora.poutine.trace(model).get_trace(controlled)
        execution.compute_log_prob()
        expected = {'outside': raw, 'after': raw, 'outer': raw, 'inner': raw}
        if controlled:
            expected['outer'] = np.where(outer_mask.numpy(), raw * 2.5, 0.)
            expected['inner'] = np.where((outer_mask & inner_mask).numpy(), raw * 2.5 * np.array([.4, .8, 1.2, 1.6]), 0.)
        for name, score in expected.items():
            assert_close(execution.nodes[name]['log_prob'], score)
        assert_close(execution.log_prob_sum(), sum(score.sum() for score in expected.values()))
    for invalid in (0., -1., torch.tensor([1., 0.]), torch.tensor([1., -1.])):
        with pytest.raises(ValueError):
            velnora.poutine.scale(model, scale=invalid)(False)


def test_f04_t07():
    def model():
        weight = velnora.param('weight', torch.tensor(-5.))
        offset = velnora.param('offset', torch.tensor(.6))
        data = velnora.sample('data', velnora.distributions.Normal(weight + offset, .9), obs=torch.tensor(.2))
        return weight, weight + offset, data

    lifted = velnora.poutine.lift(model, prior={'weight': velnora.distributions.Normal(1.4, .7).expand((SAMPLE_COUNT,))})
    execution = velnora.poutine.trace(lifted).get_trace()
    site = execution.nodes['weight']
    assert site['type'] == 'sample'
    assert not site['is_observed']
    weight, mean, data = execution.nodes['_RETURN']['value']
    assert_frequency(weight <= 1.4, .5)
    assert_frequency(weight <= 2.1, stats.norm.cdf(1.))
    assert_close(mean, weight.numpy() + .6)
    assert_close(data, .2)
    assert execution.nodes['offset']['type'] == 'param'
    for run, observed in ((execution, False),
                          (velnora.poutine.trace(velnora.poutine.replay(lifted, trace=execution)).get_trace(), False),
                          (velnora.poutine.trace(velnora.poutine.condition(lifted, data={'weight': torch.tensor(-.8)})).get_trace(), True)):
        current = run.nodes['weight']
        assert current['is_observed'] == observed
        expected = -.8 if observed else weight.numpy()
        assert_close(current['value'], expected)
        assert_close(run.nodes['_RETURN']['value'][1], expected + .6)
        run.compute_log_prob()
        prior = np.broadcast_to(stats.norm.logpdf(expected, 1.4, .7), (SAMPLE_COUNT,))
        likelihood = stats.norm.logpdf(.2, expected + .6, .9)
        assert_close(current['log_prob'], prior)
        assert_close(run.nodes['data']['log_prob'], likelihood)
        assert_close(run.log_prob_sum(), np.sum(prior) + np.sum(likelihood))
