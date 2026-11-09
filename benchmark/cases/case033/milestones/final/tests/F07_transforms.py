# feature: F07
"""Acceptance observations of transformed probability laws."""
import math
import numpy as np
import pytest
import torch
from scipy import stats
import velnora
from velnora import poutine
from velnora.distributions import constraints
from velnora.infer.reparam import SplitReparam
from _helpers import isolated_state
from F01_helpers import SAMPLE_COUNT, assert_close, assert_frequency
from F07_helpers import (
    FLOW_NAMES, INVERTIBLE_NAMES, GENERATED_NAMES, CONDITIONAL_NAMES,
    numerical_volume, normal_vector_score, assert_flow_scoring,
    assert_parameter_derivatives, assert_inverse_domain,
    assert_autoregressive_structure, assert_spline_family,
    assert_planar_family, assert_radial_family, assert_polynomial_family,
    assert_neural_scalar_family, assert_affine_coupling_family,
)


@pytest.fixture(autouse=True)
def transform_state():
    with isolated_state(seed=709, dtype=torch.float64):
        yield


def test_ordered_transformed_density():
    # FP-07.01: noncommuting transforms have different independently known laws.
    for reverse in (False, True):
        transforms = [velnora.distributions.transforms.AffineTransform(.7, 1.4), velnora.distributions.transforms.ExpTransform()]
        if reverse:
            transforms.reverse()
        law = velnora.distributions.TransformedDistribution(velnora.distributions.Normal(-.3, .8), transforms)
        sample = law.sample((SAMPLE_COUNT,))
        values = torch.tensor([1.1, 2.2, 4.3])
        if reverse:
            latent = np.log((values.numpy() - .7) / 1.4)
            expected = stats.norm.logpdf(latent, -.3, .8) - np.log(values.numpy() - .7)
            threshold = .7 + 1.4 * np.exp(.2)
        else:
            latent = (np.log(values.numpy()) - .7) / 1.4
            expected = stats.norm.logpdf(latent, -.3, .8) - np.log(1.4 * values.numpy())
            threshold = np.exp(.7 + 1.4 * .2)
        assert_close(law.log_prob(values), expected)
        assert_frequency(sample < threshold, stats.norm.cdf(.2, -.3, .8))


def test_learnable_flow_derivatives():
    for name in FLOW_NAMES:
        options = ({'count_bins': 5, 'bound': 2.4, **({} if name == 'spline_coupling' else {'order': 'linear'})}
                   if 'spline' in name else {})
        transform = getattr(velnora.distributions.transforms, name)(3, **options).double()
        if name == 'batchnorm':
            transform.eval()
        law = velnora.distributions.TransformedDistribution(velnora.distributions.Normal(torch.zeros(3), 1).to_event(1), [transform])
        assert_flow_scoring(transform, law)
        assert_parameter_derivatives(transform, law)
        if name == 'affine_autoregressive':
            assert_autoregressive_structure(transform, 3, affine=True)
        elif name == 'affine_coupling':
            assert_affine_coupling_family(transform, 3, 1)
        elif name == 'batchnorm':
            point = torch.tensor([-.4, .7, 1.1])
            jacobian = torch.autograd.functional.jacobian(transform, point)
            assert_close(jacobian, np.diag(np.diag(jacobian.detach().numpy())))
            assert (jacobian.diag() > 0).all()
            assert_close(transform(2*point)-transform(torch.zeros(3)),
                         2*(transform(point.clone())-transform(torch.zeros(3))).detach().numpy())
        elif name in ('block_autoregressive', 'neural_autoregressive'):
            assert_autoregressive_structure(transform, 3)
        elif name == 'planar':
            assert_planar_family(transform, 3)
        elif name == 'radial':
            assert_radial_family(transform, 3)
        elif name == 'polynomial':
            assert_autoregressive_structure(transform, 3)
        elif name in ('spline', 'spline_autoregressive', 'spline_coupling'):
            assert_spline_family(transform, 3, 2.4, 5, 'either' if name == 'spline_coupling' else 'linear')


def test_flow_external_inverse_and_volume():
    for name in INVERTIBLE_NAMES:
        options = ({'count_bins': 5, 'bound': 2.4, **({} if name == 'spline_coupling' else {'order': 'linear'})}
                   if 'spline' in name else {})
        transform = getattr(velnora.distributions.transforms, name)(3, **options).double()
        for point in (torch.tensor([-.8, .4, 1.1]), torch.tensor([.3, -.7, .2])):
            value = transform(point)
            assert_close(transform.inv(value.clone()), point.numpy())
            volume = numerical_volume(transform, point)
            value = transform(point.clone())
            assert_close(transform.log_abs_det_jacobian(point, value).sum(), volume.numpy())
        if name == 'affine_autoregressive':
            assert_autoregressive_structure(transform, 3, affine=True)
        elif name == 'affine_coupling':
            assert_affine_coupling_family(transform, 3, 1)
        else:
            assert_spline_family(transform, 3, 2.4, 5, 'either' if name == 'spline_coupling' else 'linear')
        # This instance has never seen a forward evaluation of either value.
        external = torch.tensor([.45, -.35, .9])
        inverse = transform.inv(external.clone())
        assert_close(transform(inverse.clone()), external.numpy())


def test_generated_sample_flow_scores():
    for name in GENERATED_NAMES:
        options = ({'count_bins': 5, 'bound': 2.4, **({} if name == 'spline_coupling' else {'order': 'linear'})}
                   if 'spline' in name else {})
        transform = getattr(velnora.distributions.transforms, name)(3, **options).double()
        law = velnora.distributions.TransformedDistribution(velnora.distributions.Normal(torch.zeros(3), 1).to_event(1), [transform])
        assert_flow_scoring(transform, law)
        if name == 'planar':
            assert_planar_family(transform, 3)
        elif name == 'radial':
            assert_radial_family(transform, 3)
        elif name in ('polynomial', 'block_autoregressive', 'neural_autoregressive'):
            assert_autoregressive_structure(transform, 3)
    assert_polynomial_family()
    # One-coordinate restrictions have independent defining function relations.
    # They distinguish generic bijections without fixing coefficient storage.
    block = velnora.distributions.transforms.block_autoregressive(1, hidden_factors=[1], activation='tanh').double()
    assert_planar_family(block, 1, residual_input=False)
    sylvester = velnora.distributions.transforms.sylvester(1).double()
    assert_planar_family(sylvester, 1)
    for activation in ('sigmoid', 'tanh'):
        neural = velnora.distributions.transforms.neural_autoregressive(1, width=2, activation=activation).double()
        assert_neural_scalar_family(neural, activation)


def test_conditional_flow_batch_laws():
    context = torch.tensor([[-1.2, .7], [2., -.9]])
    for name in CONDITIONAL_NAMES:
        options = ({'count_bins': 5, 'bound': 2.4, **({} if name == 'spline_coupling' else {'order': 'linear'})}
                   if 'spline' in name else {})
        module = getattr(velnora.distributions.transforms, 'conditional_' + name)(3, 2, **options).double()
        base = velnora.distributions.Normal(torch.zeros(2, 3), 1).to_event(1)
        conditional = velnora.distributions.ConditionalTransformedDistribution(base, [module])
        law = conditional.condition(context)
        values = law.rsample((4,))
        scores = law.log_prob(values)
        latent = law.transforms[0].inv(values)
        assert values.shape == (4, 2, 3)
        assert scores.shape == (4, 2)
        point = torch.tensor([-.4, .2, .8])
        batch_transform = module.condition(context)
        batch_result = batch_transform(point.expand(2, 3).clone())
        for index in range(2):
            single = module.condition(context[index])
            assert_close(single(point.clone()), batch_result[index].detach().numpy())
            if name == 'affine_autoregressive':
                assert_autoregressive_structure(single, 3, affine=True)
            elif name == 'affine_coupling':
                assert_affine_coupling_family(single, 3, 1)
            elif name == 'planar':
                assert_planar_family(single, 3)
            elif name == 'radial':
                assert_radial_family(single, 3)
            elif name in ('spline', 'spline_autoregressive'):
                assert_spline_family(single, 3, 2.4, 5, 'linear')
            else:
                assert_autoregressive_structure(single, 3)
            # Use one batched generated value, preserving the restricted inverse domain.
        expected = torch.empty_like(scores)
        for row in range(4):
            for index in range(2):
                single = module.condition(context[index])
                x = latent[row, index]
                expected[row, index] = normal_vector_score(x) - numerical_volume(single, x)
        np.testing.assert_allclose(scores.detach().numpy(), expected.detach().numpy(), rtol=3e-4, atol=3e-4)
        # A member must not acquire dependence on another context batch member.
        differentiable_context = context.clone().requires_grad_()
        output = module.condition(differentiable_context)(point.expand(2, 3).clone())
        jacobian = torch.autograd.grad(output[0].sum(), differentiable_context)[0]
        assert torch.isfinite(jacobian).all()
        assert_close(jacobian[1], np.zeros(2))
    for activation in ('sigmoid', 'tanh'):
        module = velnora.distributions.transforms.conditional_neural_autoregressive(
            1, 2, width=2, activation=activation).double()
        for selected_context in context:
            assert_neural_scalar_family(module.condition(selected_context), activation)


def test_support_domains_and_composition():
    # Domain checks do not fix which interior coordinate chart is used.
    cases = [
        (constraints.positive, torch.tensor([.2, 1.3, 4.])),
        (constraints.ordered_vector, torch.tensor([-1.2, .4, 2.3])),
        (constraints.simplex, torch.tensor([.2, .3, .5])),
        (constraints.positive_definite, torch.tensor([[1.4, .2], [.2, .9]])),
        (constraints.corr_matrix, torch.tensor([[1., .35], [.35, 1.]])),
        (constraints.lower_cholesky, torch.tensor([[1.3, 0.], [-.4, .8]])),
    ]
    for constraint, external in cases:
        factory = lambda c=constraint: velnora.distributions.transforms.transform_to(c)
        assert_inverse_domain(factory, external)
        transform = factory()
        coordinate = transform.inv(external.clone())
        mapped = transform(coordinate + .1)
        assert constraint.check(mapped).all()
    point = torch.tensor([-.4, .2, .7])
    ordered, exponential = velnora.distributions.transforms.OrderedTransform(), velnora.distributions.transforms.ExpTransform()
    composition = velnora.distributions.transforms.ComposeTransform([ordered, exponential])
    assert_close(composition(point), exponential(ordered(point)).numpy())
    assert_close(composition.inv(composition(point).clone()), point.numpy())


def test_spline_orders_bounds_and_inverse():
    for order, bound in [('linear', 1.7), ('quadratic', 2.6)]:
        factory = lambda: velnora.distributions.transforms.spline(3, count_bins=5, bound=bound, order=order).double()
        transform = factory()
        outside = torch.tensor([-bound - .3, bound + .2, bound + 2.])
        assert_close(transform(outside), outside.numpy())
        assert_close(transform.log_abs_det_jacobian(outside, transform(outside)), np.zeros(3))
        point = torch.tensor([-.61, .24, .82])
        volume = numerical_volume(transform, point)
        value = transform(point.clone())
        assert_close(transform.log_abs_det_jacobian(point, value).sum(), volume.numpy())
        assert_close(transform.inv(value.clone()), point.numpy())
        assert_inverse_domain(factory, torch.tensor([-.53, .17, .73]))
        assert_spline_family(transform, 3, bound, 5, order)
        jacobian = torch.autograd.functional.jacobian(transform, point)
        assert_close(jacobian, np.diag(np.diag(jacobian.detach().numpy())))
    for bound in (0., -.4):
        with pytest.raises(AssertionError):
            velnora.distributions.transforms.spline(3, bound=bound)(torch.zeros(3))
    with pytest.raises(ValueError):
        velnora.distributions.transforms.spline(3, order='cubic')(torch.zeros(3))


def test_event_split_reconstruction_and_probability():
    for shape, parts, axis in [((6,), [2, 1, 3], -1), ((4, 2), [1, 3], -2)]:
        size = int(np.prod(shape))
        loc = torch.linspace(-.6, .9, size).reshape(shape)
        scale = torch.linspace(.7, 1.6, size).reshape(shape)
        value = torch.linspace(-1.3, 1.7, size).reshape(shape)
        law = velnora.distributions.Normal(loc, scale).to_event(len(shape))

        def model(observed=None):
            return velnora.sample('event', law, obs=observed)

        model_split = poutine.reparam(model, config={'event': SplitReparam(parts, axis)})
        supplied = {'event_split_{}'.format(i): part for i, part in enumerate(value.split(parts, axis))}
        trace = poutine.trace(poutine.condition(model_split, data=supplied)).get_trace()
        assert_close(trace.nodes['event']['value'], value.numpy())
        assert_close(trace.log_prob_sum(), normal_vector_score((value - loc) / scale).sum() - torch.log(scale).sum().item())
        with pytest.raises(RuntimeError):
            poutine.trace(poutine.reparam(model, config={'event': SplitReparam([1], axis)})).get_trace(value)


def test_conditional_families_learn_context_influence():
    context = torch.tensor([[-1.2, .7], [2., -.9], [.4, 1.3]])
    points = torch.tensor([[-.4, .2, .8], [.5, -.7, .1]])[:, None, :].expand(2, 3, 3)
    target = points + .2*context[None, :, :1]
    for name in CONDITIONAL_NAMES:
        options = {'count_bins': 5, 'bound': 2.4, 'order': 'linear'} if 'spline' in name else {}
        module = getattr(velnora.distributions.transforms, 'conditional_'+name)(3, 2, **options).double()
        optimizer = torch.optim.Adam(module.parameters(), lr=.02)
        for _ in range(80):
            optimizer.zero_grad()
            output = module.condition(context)(points.clone())
            loss = (output-target).square().mean()
            loss.backward()
            optimizer.step()
        # No particular context coordinate, initial value, parameter encoding or
        # output amplitude is required. A context-blind family cannot pass.
        output = module.condition(context)(points.clone())
        assert torch.isfinite(output).all()
        assert (output[:, 1:]-output[:, :1]).abs().max() > 1e-8, name


def test_spline_junction_continuity_and_endpoints():
    from scipy.integrate import quad_vec

    # Integral identities test matching value and derivative limits without
    # assuming a knot layout or exposing the module's coefficient storage.
    with isolated_state(seed=771, dtype=torch.float64):
        for order in ('linear', 'quadratic'):
            bound = 2.3
            transform = velnora.distributions.transforms.spline(
                2, count_bins=4, bound=bound, order=order).double()
            optimizer = torch.optim.Adam(transform.parameters(), lr=.01)
            points = torch.linspace(-bound, bound, 41)[:, None].expand(41, 2)
            for _ in range(30):
                optimizer.zero_grad()
                output = transform(points.clone())
                (output-(points+.15*torch.sin(points*math.pi/bound))).square().mean().backward()
                optimizer.step()
            endpoints = torch.tensor([[-bound, -bound], [bound, bound]])
            assert_close(transform(endpoints.clone()), endpoints.numpy())
            for coordinate in range(2):
                def values(position):
                    point = torch.zeros(2, requires_grad=True)
                    displacement = torch.zeros(2)
                    displacement[coordinate] = position
                    output = transform(point+displacement)[coordinate]
                    first = torch.autograd.grad(output, point, create_graph=True)[0][coordinate]
                    second = torch.autograd.grad(first, point)[0][coordinate]
                    return np.array([output.item(), first.item(), second.item()])

                edges = np.linspace(-bound+1e-4, bound-1e-4, 9)
                for left, right in zip(edges[:-1], edges[1:]):
                    integral, error, info = quad_vec(
                        lambda x: values(x)[1:], left, right,
                        epsabs=1e-5, epsrel=1e-5, limit=600, full_output=True)
                    assert info.success, info.message
                    difference = values(right)[:2]-values(left)[:2]
                    np.testing.assert_allclose(integral, difference, rtol=2e-4, atol=2e-4)
