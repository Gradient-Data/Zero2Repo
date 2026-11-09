# feature: F08
"""Observable optimization, continuation and differentiable update checks."""
import copy

import pytest
import torch
import velnora
from velnora.optim import VelnoraOptim, VelnoraLRScheduler
from velnora.optim.multi import MixedMultiOptimizer, Newton
from velnora.ops.newton import newton_step
from _helpers import isolated_state, invoke, temporary_directory
from F01_helpers import assert_close
from F08_helpers import apply_gradients, named_leaf, quadratic


@pytest.fixture(autouse=True)
def optimization_state():
    with isolated_state(dtype=torch.float64, device='cpu'):
        yield


def test_f08_t01():
    optim = VelnoraOptim(torch.optim.SGD, {'lr': .2, 'momentum': .5})
    first = named_leaf('first', [2., -1.])
    untouched = named_leaf('untouched', [7., 3.])
    apply_gradients(optim, [(first, [1., -2.])])
    assert_close(first, [1.8, -.6])
    late = named_leaf('late', [-3., 4.])
    apply_gradients(optim, [(late, [-2., 3.])])
    assert_close(late, [-2.6, 3.4])
    assert_close(first, [1.8, -.6])
    apply_gradients(optim, [(first, [2., 1.]), (late, [1., -1.])])
    assert_close(first, [1.3, -.6])
    assert_close(late, [-2.6, 3.3])
    assert_close(untouched, [7., 3.])


def test_f08_t02():
    settings = {'frozen': {'lr': 0.}, 'fast': {'lr': .4},
                'value': {'lr': .2}, 'norm': {'lr': .3}}
    clipping = {'frozen': {}, 'fast': {}, 'value': {'clip_value': 2.},
                'norm': {'clip_norm': 2.}}
    optim = VelnoraOptim(torch.optim.SGD, lambda name: settings[name],
                      lambda module, name: clipping[name])
    values = {name: named_leaf(name, [1., -1.]) for name in settings}
    apply_gradients(optim, [(p, [6., -8.]) for p in values.values()])
    assert_close(values['frozen'], [1., -1.])
    assert_close(values['fast'], [-1.4, 2.2])
    assert_close(values['value'], [.6, -.6])
    # Norm clipping has a numerical stabilization epsilon: judge its effect
    # at the shared floating-point tolerance, rather than pinning that epsilon.
    assert_close(values['norm'], [.64, -.52])


def test_f08_t03():
    for constructor, options, metrics, rates in (
        (torch.optim.lr_scheduler.StepLR, {'step_size': 1, 'gamma': .5}, [None, None], [.2, .1]),
        (torch.optim.lr_scheduler.ReduceLROnPlateau,
         {'factor': .5, 'patience': 0, 'mode': 'min'}, [1., 2.], [.4, .2]),
    ):
        with isolated_state(dtype=torch.float64):
            scheduler = VelnoraLRScheduler(constructor, {
                'optimizer': torch.optim.SGD, 'optim_args': {'lr': .4}, **options})
            first = named_leaf('first', [3.])
            apply_gradients(scheduler, [(first, [1.])])
            assert_close(first, [2.6])
            for metric, expected_rate in zip(metrics, rates):
                if metric is None:
                    scheduler.step()
                else:
                    scheduler.step(metric)
                before = first.detach().clone()
                apply_gradients(scheduler, [(first, [1.])])
                assert_close(before - first, [expected_rate])
            late = named_leaf('late', [-2.])
            apply_gradients(scheduler, [(late, [1.])])
            assert_close(late, [-2.4])
            if constructor is torch.optim.lr_scheduler.StepLR:
                scheduler.step()
            else:
                scheduler.step(1.)
                scheduler.step(2.)
            before = late.detach().clone()
            apply_gradients(scheduler, [(late, [1.])])
            assert_close(before - late, [.2])


def test_f08_t04():
    for transport in ('memory', 'file'):
        with isolated_state(dtype=torch.float64), temporary_directory() as directory:
            optim = VelnoraOptim(torch.optim.SGD, {'lr': .15, 'momentum': .8})
            early = named_leaf('early', [1., -2.])
            late = named_leaf('late', [3., .5])
            for gradients in ([2., -1.], [-3., 4.], [1., 2.]):
                apply_gradients(optim, [(early, gradients), (late, gradients[::-1])])
            checkpoint = {name: velnora.param(name).detach().clone() for name in ('early', 'late')}
            state = copy.deepcopy(optim.get_state())
            path = directory / 'optimizer.pt'
            optim.save(path)
            future = [([4., -2.], [-1., 3.]), ([-2., 1.], [2., -4.])]
            expected = []
            for g1, g2 in future:
                apply_gradients(optim, [(early, g1), (late, g2)])
                expected.append((early.detach().clone(), late.detach().clone()))
            assert not torch.allclose(expected[0][0], checkpoint['early'])
            assert not torch.allclose(expected[0][1], checkpoint['late'])
            velnora.clear_param_store()
            resumed = VelnoraOptim(torch.optim.SGD, {'lr': .15, 'momentum': .8})
            if transport == 'memory':
                resumed.set_state(state)
            else:
                resumed.load(path)
            early = named_leaf('early', checkpoint['early'])
            # The second parameter has not even been registered at restoration.
            apply_gradients(resumed, [(early, future[0][0])])
            assert_close(early, expected[0][0].numpy())
            late = named_leaf('late', checkpoint['late'])
            apply_gradients(resumed, [(late, future[0][1])])
            assert_close(late, expected[0][1].numpy())
            apply_gradients(resumed, [(early, future[1][0]), (late, future[1][1])])
            assert_close(early, expected[1][0].numpy())
            assert_close(late, expected[1][1].numpy())
            # Establish that these histories matter, rather than comparing two
            # identical stateless trajectories.
            fresh = checkpoint['early'] - .15 * torch.tensor(future[0][0])
            assert not torch.allclose(expected[0][0], fresh)


def test_f08_t05():
    x = named_leaf('x', [3., -2.])
    y = named_leaf('y', [-1., 4.])
    parts = [(['x'], VelnoraOptim(torch.optim.SGD, {'lr': .1})), (['y'], Newton())]
    mixed = MixedMultiOptimizer(parts)
    target_x = torch.tensor([1., 2.])
    target_y = torch.tensor([2., -3.])
    loss = ((x - target_x) ** 2).sum() + 1.5 * ((y - target_y) ** 2).sum()
    mixed.step(loss, {'x': x, 'y': y})
    assert_close(x, [2.6, -1.2])
    assert_close(y, target_y.numpy())
    refused = invoke(MixedMultiOptimizer,
                     [(['x', 'y'], Newton()), (['y'], Newton())],
                     allowed_exceptions=(ValueError,))
    assert isinstance(refused.exception, ValueError)


def test_f08_t06():
    for dimension in (1, 2, 3):
        x = torch.tensor([[2., -1., 3.], [-2., 4., 1.]])[:, :dimension].clone().requires_grad_()
        center = torch.tensor([[.3, -.6, 1.], [1., .2, -.4]])[:, :dimension]
        matrix = torch.tensor([[3., .6, -.2], [.6, 2., .4], [-.2, .4, 1.5]])[:dimension, :dimension]
        updated, covariance = newton_step(quadratic(x, center, matrix), x)
        assert updated.shape == x.shape
        assert covariance.shape == (2, dimension, dimension)
        assert_close(updated, center.numpy())
        expected = torch.linalg.inv(matrix).expand(2, dimension, dimension)
        assert_close(covariance, expected.numpy())


def test_f08_t07():
    for dimension in (1, 2, 3):
        x = torch.full((dimension,), -2., requires_grad=True)
        center = torch.arange(1., dimension + 1.)
        matrix = torch.eye(dimension) * 2 + .2
        loss = quadratic(x, center, matrix)
        free, _ = newton_step(loss, x)
        assert torch.linalg.vector_norm(free - x) > .4
        limited, _ = newton_step(loss, x, trust_radius=.4)
        distance = torch.linalg.vector_norm(limited - x)
        assert 0 < distance <= .4 + 1e-8
        assert quadratic(limited, center, matrix) < loss
        # A smooth objective with nonlinear dependence on external inputs has
        # nonzero first and second derivatives, so detaching any order is visible.
        theta = torch.tensor(.7, requires_grad=True)
        center = theta.pow(3).expand(dimension)
        matrix = torch.eye(dimension) * theta.exp()
        updated, covariance = newton_step(quadratic(x, center, matrix), x)
        first = torch.autograd.grad(updated.sum(), theta, create_graph=True, retain_graph=True)[0]
        second = torch.autograd.grad(first, theta, retain_graph=True)[0]
        assert_close(first, (dimension * 3 * theta.square()).detach().numpy())
        assert_close(second, (dimension * 6 * theta).detach().numpy())
        cov_first = torch.autograd.grad(covariance.sum(), theta, create_graph=True)[0]
        cov_second = torch.autograd.grad(cov_first, theta)[0]
        assert_close(cov_first, (-dimension * (-theta).exp()).detach().numpy())
        assert_close(cov_second, (dimension * (-theta).exp()).detach().numpy())
