# feature: F06
"""Acceptance checks for probabilistic neural modeling."""
import numpy as np
import pytest
import torch
from scipy import stats
import velnora
from velnora.nn import DenseNN, ConditionalDenseNN, AutoRegressiveNN, ConditionalAutoRegressiveNN
from velnora.contrib.bnn import HiddenLayer
from _helpers import isolated_state, save_and_load
from F01_helpers import SAMPLE_COUNT, assert_close, assert_frequency
from F02_helpers import assert_parameter_domain, learn_parameter
from F06_helpers import LearnedNetwork, DependentNetwork, fit_mapping
from torch.distributions import constraints


@pytest.fixture(autouse=True)
def neural_state():
    with isolated_state(seed=203, dtype=torch.float64, device='cpu'):
        yield


def test_f06_t01():
    model = LearnedNetwork()
    x = torch.tensor([[1., -2.], [-.3, .8], [2., 1.]])
    initial = model(x).detach().clone()
    execution = velnora.poutine.trace(model).get_trace(x)
    names = {'left.weight', 'left.bias', 'right.weight', 'right.bias', 'scale'}
    assert names <= set(execution.nodes)
    assert names <= set(velnora.get_param_store().keys())
    for component in ('left', 'right'):
        for name, parameter in getattr(model, component).named_parameters():
            assert velnora.param(component + '.' + name) is parameter
    expected = model.scale * torch.nn.functional.linear(x, model.left.weight, model.left.bias)
    expected = expected + torch.nn.functional.linear(x, model.right.weight, model.right.bias)
    assert_close(model(x), expected.detach().numpy())
    left_before = model.left.weight.detach().clone()
    right_before = model.right.weight.detach().clone()
    learned = learn_parameter('left.weight', torch.full_like(left_before, 3.), constraints.real)
    assert_close(model.left.weight, learned.numpy())
    assert_close(model.right.weight, right_before.numpy())
    learn_parameter('scale', torch.tensor(-2.), constraints.positive)
    assert_parameter_domain(model.scale, constraints.positive)
    updated = model(x)
    expected = model.scale * model.left(x) + model.right(x)
    assert_close(updated, expected.detach().numpy())
    assert not torch.allclose(updated, initial)
    assert_close(model(x), updated.detach().numpy())


def test_f06_t02():
    model = DependentNetwork(SAMPLE_COUNT)
    first = velnora.poutine.trace(model).get_trace()
    a, again, b, twice = first.nodes['_RETURN']['value']
    assert_close(a, again.numpy())
    assert_close(b, twice.numpy())
    for z in (-1., 0., 1.):
        assert_frequency((a - .4) / 1.3 <= z, stats.norm.cdf(z))
        assert_frequency((b - 2 * a) / .7 <= z, stats.norm.cdf(z))
    second = model()
    assert_frequency((second[0] - a) / (1.3 * np.sqrt(2)) <= 0., .5)
    assert not torch.equal(second[0], a)
    replayed = velnora.poutine.replay(model, trace=first)()
    for actual, expected in zip(replayed, (a, again, b, twice)):
        assert_close(actual, expected.numpy())
    selected = torch.full((SAMPLE_COUNT,), -1.6)
    observed = velnora.poutine.trace(velnora.poutine.condition(model, data={'parent': selected})).get_trace()
    assert observed.nodes['parent']['is_observed']
    for controlled in (observed.nodes['_RETURN']['value'], velnora.poutine.do(model, data={'parent': selected})()):
        assert_close(controlled[0], selected.numpy())
        assert_close(controlled[1], selected.numpy())
        assert_close(controlled[2], controlled[3].numpy())
        assert_frequency((controlled[2] - 2 * selected) / .7 <= 0., .5)


def test_f06_t03():
    model = LearnedNetwork()
    x = torch.tensor([[1., -1.], [2., .5], [-.4, .2]])
    model(x)
    fit_mapping(model, lambda: model(x), torch.tensor([[2.], [-1.], [.5]]))
    learn_parameter('scale', torch.tensor(.3), constraints.positive)
    prediction = model(x).detach().clone()
    fixed = torch.tensor(-.9)
    before = velnora.poutine.trace(velnora.poutine.condition(model, data={'noise': fixed})).get_trace(x, True)
    before.compute_log_prob()

    def restore(path):
        velnora.clear_param_store()
        restored = LearnedNetwork()
        restored.load_state_dict(torch.load(path, weights_only=True))
        return restored

    _, loaded = save_and_load(lambda path: torch.save(model.state_dict(), path), restore)
    restored = loaded.value
    assert_close(restored(x), prediction.numpy())
    assert_parameter_domain(restored.scale, constraints.positive)
    after = velnora.poutine.trace(velnora.poutine.condition(restored, data={'noise': fixed})).get_trace(x, True)
    after.compute_log_prob()
    expected = stats.norm.logpdf(fixed.item(), restored.left.bias.item(), restored.scale.item())
    assert_close(after.nodes['noise']['log_prob'], expected)
    assert_close(after.nodes['noise']['log_prob'], before.nodes['noise']['log_prob'].detach().numpy())
    samples = torch.stack([restored(x, True)[1].detach() for _ in range(3000)])
    standardized = (samples - restored.left.bias.detach()) / restored.scale.detach()
    # At n=3000 a CDF tolerance of .07 has Hoeffding error below 4e-13.
    for z in (-1., 0., 1.):
        assert abs((standardized <= z).double().mean().item() - stats.norm.cdf(z)) < .07


def test_f06_t04():
    x = torch.randn(24, 3)
    context = torch.randn(24, 2)
    order = torch.tensor([2, 0, 1])
    networks = [
        (DenseNN(3, [16], param_dims=[2, 1], nonlinearity=torch.nn.Tanh()), False, False),
        (ConditionalDenseNN(3, 2, [16], param_dims=[2, 1], nonlinearity=torch.nn.Tanh()), True, False),
        (AutoRegressiveNN(3, [16], param_dims=[2, 1], permutation=order, nonlinearity=torch.nn.Tanh()), False, True),
        (ConditionalAutoRegressiveNN(3, 2, [16], param_dims=[2, 1], permutation=order, nonlinearity=torch.nn.Tanh()), True, True),
    ]
    for network, conditional, autoregressive in networks:
        def outputs(c=context):
            return network(x, context=c) if conditional else network(x)
        parts = outputs()
        shapes = [(24, 2, 3), (24, 1, 3)] if autoregressive else [(24, 2), (24, 1)]
        assert [tuple(part.shape) for part in parts] == shapes
        def flattened():
            return torch.cat([part.reshape(24, -1) for part in outputs()], -1)
        # Dense targets use the input; autoregressive dependence is measured
        # separately below on targets respecting the declared ordering.
        base = torch.ones(24, 1) if autoregressive else x[:, :1]
        if conditional:
            base = base + context[:, :1]
        target = base * torch.linspace(.3, 1.1, flattened().shape[-1])
        fit_mapping(network, flattened, target)
        if not autoregressive:
            shifted = network(x + 1., context=context) if conditional else network(x + 1.)
            assert not torch.allclose(outputs()[0], shifted[0])
        if conditional:
            assert not torch.allclose(outputs()[0], outputs(context + 1.)[0])


def test_f06_t05():
    order = [2, 0, 3, 1]
    for conditional in (False, True):
        constructor = ConditionalAutoRegressiveNN if conditional else AutoRegressiveNN
        args = (4, 2, [24, 24]) if conditional else (4, [24, 24])
        network = constructor(*args, param_dims=[1], permutation=torch.tensor(order), nonlinearity=torch.nn.Tanh())
        training_x = torch.randn(80, 4)
        training_context = torch.randn(80, 2)
        target = torch.zeros_like(training_x)
        for rank, coordinate in enumerate(order):
            if rank:
                target[:, coordinate] = training_x[:, order[rank-1]]
        if conditional:
            target = target + training_context[:, :1]
        training_call = (lambda: network(training_x, context=training_context)) if conditional else (lambda: network(training_x))
        fit_mapping(network, training_call, target)
        x = torch.randn(4, requires_grad=True)
        context = torch.tensor([.3, -.8], requires_grad=True)
        def call(value):
            return network(value, context=context) if conditional else network(value)
        output = call(x)
        assert output.shape == (4,)
        allowed = []
        for rank, coordinate in enumerate(order):
            gradient = torch.autograd.grad(output[coordinate], x, retain_graph=True)[0]
            assert_close(gradient[order[rank:]], np.zeros(4-rank))
            changed = x.detach().clone()
            changed[order[rank:]] += torch.arange(1., 5-rank)
            assert_close(call(changed)[coordinate], output[coordinate].detach().numpy())
            if rank:
                allowed.append(gradient[order[:rank]].abs().sum().item())
        assert sum(allowed) > 1e-8
        if conditional:
            derivative = torch.autograd.grad(output.sum(), context)[0]
            assert derivative.abs().sum() > 1e-8


def test_f06_t06():
    x = torch.tensor([[1., -2.], [-.5, .8], [2., .3]])
    mean = torch.tensor([[.7, -.4], [.2, .9]])
    scale = torch.tensor([[.6, 1.1], [.4, .7]])
    # Independent normal-weight marginals; no cross-row coupling is assumed.
    location = x.numpy() @ mean.numpy()
    deviation = np.sqrt(x.numpy() ** 2 @ (scale.numpy() ** 2))
    for options, transform, bias in [({}, lambda z: np.maximum(z, 0.), True),
                                      ({'non_linearity': torch.tanh, 'include_hidden_bias': False}, np.tanh, False)]:
        layer = HiddenLayer(x, mean, scale, **options)
        sample = layer.rsample(torch.Size([SAMPLE_COUNT]))
        assert sample.shape == (SAMPLE_COUNT, 3, 2 + int(bias))
        if bias:
            assert_close(sample[..., -1], np.ones((SAMPLE_COUNT, 3)))
            assert (sample[..., :-1] >= 0).all()
        values = sample[..., :2]
        for z in (-.5, .5, 1.5):
            thresholds = location + z * deviation
            if bias:
                # ReLU has an atom at zero; negative thresholds have zero CDF.
                probability = np.where(thresholds < 0., 0., stats.norm.cdf(z))
                threshold = thresholds
            else:
                probability = stats.norm.cdf(z)
                threshold = transform(thresholds)
            assert_frequency(values <= torch.tensor(threshold), probability)


def test_f06_t07():
    mean = torch.tensor([[.4, -1.2], [.7, .2]])
    scale = torch.tensor([[.8, 1.4], [.5, 1.1]])
    # Independent analytic KL for normal weights against the default unit normal.
    divergence = .5 * np.sum(mean.numpy() ** 2 + scale.numpy() ** 2 - 1 - np.log(scale.numpy() ** 2))
    x = torch.tensor([[1., -.3], [2., .8]])
    for factor in (0., .35, 1.7):
        layer = HiddenLayer(x, mean, scale, KL_factor=factor)
        for value in (torch.zeros(2, 3), torch.full((2, 3), 4.)):
            assert_close(layer.log_prob(value), -factor * divergence)
