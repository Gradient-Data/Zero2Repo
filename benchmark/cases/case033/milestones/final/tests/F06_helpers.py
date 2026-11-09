# feature: F06
"""Neural workloads using public module attributes and forward calls."""
import velnora
import torch
from torch.distributions import constraints
from velnora.nn import VelnoraModule, VelnoraParam, VelnoraSample


class LearnedNetwork(VelnoraModule):
    def __init__(self):
        super().__init__()
        self.left = VelnoraModule[torch.nn.Linear](2, 1)
        self.right = VelnoraModule[torch.nn.Linear](2, 1)
        self.scale = VelnoraParam(torch.tensor(.8), constraints.positive)
        self.noise = VelnoraSample(lambda m: velnora.distributions.Normal(m.left.bias.squeeze(), m.scale))

    def forward(self, x, stochastic=False):
        prediction = self.scale * self.left(x) + self.right(x)
        return (prediction, self.noise) if stochastic else prediction


class DependentNetwork(VelnoraModule):
    def __init__(self, count):
        super().__init__()
        self.parent = VelnoraSample(velnora.distributions.Normal(.4, 1.3).expand((count,)).to_event(1))
        self.child = VelnoraSample(lambda m: velnora.distributions.Normal(2 * m.parent, .7).to_event(1))

    def forward(self):
        return self.parent, self.parent, self.child, self.child


def fit_mapping(network, call, target):
    """Observe reduction of a caller-defined regression objective."""
    optimizer = torch.optim.Adam(network.parameters(), lr=.03)
    before = ((call() - target) ** 2).mean().item()
    for _ in range(180):
        optimizer.zero_grad()
        loss = ((call() - target) ** 2).mean()
        loss.backward()
        optimizer.step()
    after = ((call() - target) ** 2).mean().item()
    assert after < before
    return call().detach()
