# feature: F02
"""Public parameter-domain workloads and learning observations."""
import torch
import velnora
from torch.distributions import constraints
from F01_helpers import assert_close


def parameter_domain_cases():
    """Each required domain has a nonstationary differentiable objective."""
    return [
        ('real', constraints.real, torch.tensor([-1., 2.]), torch.tensor([3., -4.])),
        ('positive', constraints.positive, torch.tensor([.8, 1.7]), torch.tensor([-2., -1.])),
        ('interval', constraints.interval(-2., 3.), torch.tensor([-.7, 1.2]), torch.tensor([8., -6.])),
        ('simplex', constraints.simplex, torch.tensor([.2, .5, .3]), torch.tensor([2., -1., 0.])),
        ('definite', constraints.positive_definite, torch.tensor([[1.4, .2], [.2, .9]]), -torch.eye(2)),
        ('triangular', constraints.lower_cholesky, torch.tensor([[1.1, 0.], [.3, .8]]), torch.tensor([[-2., 0.], [-1., -3.]])),
    ]


def assert_parameter_domain(value, domain):
    assert torch.isfinite(value).all()
    assert domain.check(value).all()


def learn_parameter(name, target, domain):
    """Check useful learning through public optimizer-facing parameter tensors.

    No expected coordinate values, derivatives, update trajectory or convergence
    rate is imposed. Targets outside constrained domains expose unconstrained
    updates that cease to respect the registered domain.
    """
    store = velnora.get_param_store()
    before = velnora.param(name).detach().clone()
    assert_parameter_domain(before, domain)
    leaves = dict(store.named_parameters())
    optimizer = torch.optim.Adam([leaves[name]], lr=.15)
    initial_loss = ((before - target) ** 2).sum().item()
    for _ in range(16):
        optimizer.zero_grad()
        value = velnora.param(name)
        assert_parameter_domain(value, domain)
        loss = ((value - target) ** 2).sum()
        loss.backward()
        assert leaves[name].grad is not None
        assert torch.isfinite(leaves[name].grad).all()
        optimizer.step()
        assert_parameter_domain(velnora.param(name), domain)
    after = velnora.param(name)
    assert ((after.detach() - target) ** 2).sum().item() < initial_loss
    assert_close(store[name], after.detach().numpy())
    return after.detach().clone()
