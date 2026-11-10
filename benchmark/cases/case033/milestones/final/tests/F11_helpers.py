# feature: F11
"""Soluble posterior workloads and public sampling-hook observations."""
import json
import os
from pathlib import Path
import torch
import velnora
from velnora.infer.mcmc import MCMC
from _helpers import invoke


def posterior_chain(kernel, *, draws=1200, warmup=200, **kwargs):
    chain = MCMC(kernel, num_samples=draws, warmup_steps=warmup,
                 disable_progbar=True, **kwargs)
    invoke(chain.run, timeout=180)
    return chain


class ChainRecorder:
    """One file per public hook stage permits observations in worker processes."""
    def __init__(self, directory):
        self.directory = Path(directory)

    def __call__(self, kernel, samples, stage, index):
        record = {'index': index,
                  'samples': {k: v.detach().tolist() for k, v in samples.items()},
                  'initial': {k: v.detach().tolist() for k, v in kernel.initial_params.items()}}
        stage, separator, suffix = stage.partition(' [')
        if stage not in ('Warmup', 'Sample'):
            raise ValueError('Unknown sampling stage')
        if separator:
            if not suffix.endswith(']'):
                raise ValueError('Malformed chain stage')
            chain = int(suffix[:-1])
            if chain < 0:
                raise ValueError('Chain index must be nonnegative')
            key = 'chain-{}'.format(chain)
        else:
            # Worker callbacks have no chain suffix; each chain owns a process.
            key = 'worker-{}'.format(os.getpid())
        with (self.directory / (stage + '-' + key + '.jsonl')).open('a') as stream:
            stream.write(json.dumps(record) + '\n')

    def read_chains(self, stage):
        records = []
        for path in sorted(self.directory.glob(stage + '-*.jsonl')):
            with path.open() as stream:
                records.append([json.loads(line) for line in stream])
        return records


class BinaryStateModel:
    """Static binary state with correlated components and repeated evidence."""
    def init(self, state):
        x = velnora.sample('x', velnora.distributions.Bernoulli(.3))
        state['x'] = x
        state['pair'] = torch.stack((x, 1-x), -1)

    def step(self, state, observation):
        p = .15 + .7 * state['x']
        velnora.sample('obs', velnora.distributions.Bernoulli(p), obs=torch.tensor(float(observation)))


class BinaryStateGuide:
    def init(self, state):
        velnora.sample('x', velnora.distributions.Bernoulli(.6))

    def step(self, state, observation):
        # Reading retained state is permitted.
        state['x']


class OverwritingGuide(BinaryStateGuide):
    def step(self, state, observation):
        state['x'] = torch.zeros_like(state['x'])


class ImpossibleEvidenceModel(BinaryStateModel):
    def step(self, state, observation):
        velnora.sample('obs', velnora.distributions.Delta(torch.zeros_like(state['x'])),
                    obs=torch.tensor(float(observation)))


class DenseMoments:
    """Caller-supplied bounded-memory covariance summary for StreamingMCMC."""
    def __init__(self):
        self.count = 0
        self.total = None
        self.outer = None

    def update(self, sample):
        sample = sample.detach().reshape(-1)
        if self.count == 0:
            self.total = torch.zeros_like(sample)
            self.outer = torch.zeros(sample.numel(), sample.numel(), dtype=sample.dtype)
        self.count += 1
        self.total += sample
        self.outer += torch.outer(sample, sample)

    def merge(self, other):
        merged = DenseMoments()
        merged.count = self.count + other.count
        merged.total = self.total + other.total
        merged.outer = self.outer + other.outer
        return merged

    def get(self):
        mean = self.total/self.count
        covariance = (self.outer-self.count*torch.outer(mean, mean))/(self.count-1)
        return {'count': self.count, 'mean': mean, 'covariance': covariance}


def two_site_energy(values):
    return .5*(values['x'].square()+values['y'].square())


class SwitchableScore(torch.autograd.Function):
    """A genuine Gaussian log likelihood with caller-controlled derivatives."""
    @staticmethod
    def forward(ctx, value, availability):
        ctx.save_for_backward(value)
        ctx.availability = availability
        return -.5*((value-3.)/.5).square()

    @staticmethod
    def backward(ctx, gradient):
        if not ctx.availability['enabled']:
            raise RuntimeError("Density derivatives are unavailable after initialization")
        value, = ctx.saved_tensors
        ctx.availability['evaluations'] += 1
        return -gradient*(value-3.)/.25, None
