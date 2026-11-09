# feature: F02
"""Acceptance checks for learnable named parameter state."""
import pytest
import torch
import velnora
from torch.distributions import constraints
from _helpers import isolated_state, invoke, save_and_load
from F01_helpers import assert_close
from F02_helpers import parameter_domain_cases, assert_parameter_domain, learn_parameter


@pytest.fixture(autouse=True)
def parameter_state():
    with isolated_state(validation=True, dtype=torch.float64, device='cpu'):
        yield


def test_f02_t01():
    store = velnora.get_param_store()
    calls = []

    def initialize():
        calls.append(True)
        return torch.tensor([1.2, -.6])

    first = velnora.param('learned', initialize)
    assert calls == [True]
    assert_close(first, [1.2, -.6])
    learned = learn_parameter('learned', torch.tensor([-2., 3.]), constraints.real)
    assert_close(velnora.param('learned'), learned.numpy())
    assert_close(velnora.param('learned', torch.tensor([9., 8.])), learned.numpy())
    assert_close(velnora.param('learned', initialize), learned.numpy())
    assert calls == [True]
    assert_close(store['learned'], learned.numpy())
    assert_close(velnora.param('another', initialize), [1.2, -.6])
    assert calls == [True, True]
    assert_close(velnora.param('learned'), learned.numpy())


def test_f02_t02():
    for name, domain, initial, target in parameter_domain_cases():
        value = velnora.param(name, initial.clone(), constraint=domain)
        assert_close(value, initial.numpy())
        assert_parameter_domain(value, domain)
        learn_parameter(name, target, domain)


def test_f02_t03():
    store = velnora.get_param_store()
    velnora.param('offset', torch.tensor([-1., 2.]))
    velnora.param('scale', torch.tensor([.4, 1.8]), constraint=constraints.positive)
    assert set(store.keys()) == {'offset', 'scale'}
    entries = dict(store.items())
    assert set(entries) == {'offset', 'scale'}
    assert_close(entries['offset'], [-1., 2.])
    assert_close(entries['scale'], [.4, 1.8])
    store['offset'] = torch.tensor([5., -3.])
    store['scale'] = torch.tensor([2.1, .7])
    assert_close(velnora.param('offset'), [5., -3.])
    assert_close(velnora.param('scale'), [2.1, .7])
    learn_parameter('scale', torch.tensor([-1., -2.]), constraints.positive)
    del store['offset']
    assert set(store.keys()) == {'scale'}
    for read in (lambda: velnora.param('offset'), lambda: store['offset']):
        result = invoke(read, allowed_exceptions=(KeyError,))
        assert isinstance(result.exception, KeyError)
    assert_close(velnora.param('offset', torch.tensor([7.])), [7.])
    store.clear()
    assert set(store.keys()) == set()
    assert dict(store.items()) == {}
    for name in ('offset', 'scale', 'never_registered'):
        result = invoke(velnora.param, name, allowed_exceptions=(KeyError,))
        assert isinstance(result.exception, KeyError)
    assert_close(velnora.param('scale', torch.tensor([-3.])), [-3.])


def test_f02_t04():
    store = velnora.get_param_store()
    cases = parameter_domain_cases()
    snapshots = {}
    for name, domain, initial, target in cases:
        velnora.param(name, initial.clone(), constraint=domain)
        snapshots[name] = learn_parameter(name, target, domain)

    def restore(path):
        store.clear()
        store.load(path)

    save_and_load(store.save, restore)
    assert set(store.keys()) == set(snapshots)
    for name, domain, _, target in cases:
        assert_close(velnora.param(name), snapshots[name].numpy())
        assert_parameter_domain(velnora.param(name), domain)
        learn_parameter(name, target, domain)


def test_f02_t05():
    store = velnora.get_param_store()
    velnora.param('shared', torch.tensor([1.4, .8]), constraint=constraints.positive)
    velnora.param('outer_only', torch.tensor([-5.]))
    outer = learn_parameter('shared', torch.tensor([-2., -1.]), constraints.positive)
    interval = constraints.interval(-4., -1.)
    with store.scope() as retained:
        assert set(store.keys()) == set()
        assert_close(velnora.param('shared', torch.tensor([-2.2, -3.1]), constraint=interval), [-2.2, -3.1])
        velnora.param('inner_only', torch.tensor([6.]))
        inner = learn_parameter('shared', torch.tensor([2., -8.]), interval)
    assert set(store.keys()) == {'shared', 'outer_only'}
    assert_close(velnora.param('shared'), outer.numpy())
    assert_close(velnora.param('outer_only'), [-5.])
    outer = learn_parameter('shared', torch.tensor([-2., -1.]), constraints.positive)
    with store.scope(retained):
        assert set(store.keys()) == {'shared', 'inner_only'}
        assert_close(velnora.param('shared'), inner.numpy())
        assert_close(velnora.param('inner_only'), [6.])
        inner = learn_parameter('shared', torch.tensor([-8., 2.]), interval)
    assert_close(velnora.param('shared'), outer.numpy())
    with store.scope(retained):
        assert_close(velnora.param('shared'), inner.numpy())
        assert_parameter_domain(velnora.param('shared'), interval)
    assert_close(velnora.param('shared'), outer.numpy())
