# feature: F16
"""Caller-defined epidemic workloads and independent probability observations."""
import pytest
import numpy as np
import torch
import velnora
from velnora import poutine
from scipy import stats
from velnora.contrib.epidemiology import CompartmentalModel
from velnora.contrib.epidemiology.distributions import binomial_dist
from velnora.contrib.epidemiology import models as em
from _helpers import invoke
from F01_helpers import assert_close, assert_frequency, SAMPLE_COUNT


class MeasuredEpidemic(CompartmentalModel):
    """Known reporting probability leaves one identifiable infection parameter."""
    def __init__(self, population=20, data=None, duration=1, compartments=('S', 'I')):
        self.data = [None] * duration if data is None else data
        super().__init__(compartments, len(self.data), population)

    def global_model(self):
        return velnora.sample('infectivity', velnora.distributions.Beta(2., 2.))

    def initialize(self, params):
        return {'S': self.population-1, 'I': 1}

    def transition(self, params, state, t):
        infections = velnora.sample('S2I_{}'.format(t), binomial_dist(state['S'], params))
        recoveries = velnora.sample('I2R_{}'.format(t), binomial_dist(state['I'], .2))
        state['S'] = state['S'] - infections
        state['I'] = state['I'] + infections - recoveries
        observed = isinstance(t, slice) or t < self.duration
        velnora.sample('obs_{}'.format(t), binomial_dist(infections, .9),
                    obs=self.data[t] if observed else None)


def epidemic_record(model, fixed=None, events=None):
    """Trace a public generate call, preserving real event distributions."""
    events = {} if events is None else {k: torch.as_tensor(v, dtype=torch.float64)
                                       for k, v in events.items()}
    call = poutine.trace(poutine.condition(model.generate, data=events)).get_trace
    trace = invoke(call, {} if fixed is None else fixed).value
    return trace.nodes['_RETURN']['value'], trace


def epidemic_score(trace, name, values, expected):
    """Score caller-selected outcomes, without inspecting distribution internals."""
    law = trace.nodes[name]['fn']
    actual = invoke(law.log_prob, torch.as_tensor(values, dtype=torch.float64)).value
    np.testing.assert_allclose(actual.detach().cpu().numpy(), expected,
                               rtol=3e-5, atol=3e-5)


def epidemic_count_law(trace, name, n, p, dispersion=0., concentration=None):
    """The PRD's count laws, independently evaluated by SciPy."""
    n, p = np.asarray(n), np.asarray(p)
    values = np.arange(int(n.max())+1, dtype=float)
    if n.ndim:
        values = values[:, None]
    if concentration is not None:
        a = np.asarray(concentration)
        reference = stats.betabinom(n, a, a*(1-p)/p)
    elif dispersion:
        # Mixing variance p^2(1-p)^2 d^2 fixes the beta concentrations.
        c = 1/(p*(1-p)*dispersion**2)-1
        reference = stats.betabinom(n, p*c, (1-p)*c)
    else:
        reference = stats.binom(n, p)
    epidemic_score(trace, name, values, reference.logpmf(values))
    return reference


def epidemic_families(duration=4):
    data = [None]*duration
    population = torch.tensor([41., 67.])
    coupling = torch.tensor([[1., .35], [.15, 1.]])
    return [em.SimpleSIRModel(41, 3., data), em.SimpleSEIRModel(41, 2.5, 3., data),
            em.SimpleSEIRDModel(41, 2.5, 3., .3, data),
            em.OverdispersedSIRModel(41, 3., data),
            em.OverdispersedSEIRModel(41, 2.5, 3., data),
            em.SuperspreadingSIRModel(41, 3., data),
            em.SuperspreadingSEIRModel(41, 2.5, 3., data),
            em.HeterogeneousSIRModel(41, 3., data),
            em.SparseSIRModel(41, 3., data, torch.ones(duration, dtype=torch.bool)),
            em.UnknownStartSIRModel(41, 3., 3, data),
            em.RegionalSIRModel(population, coupling, 3., data),
            em.HeterogeneousRegionalSIRModel(population, coupling, 3., data)]


def epidemic_accounting(model, output):
    """Check flows against populations and returned post-transition histories."""
    population = torch.as_tensor(model.population)
    initial_i = torch.zeros_like(population) if model.is_regional else torch.tensor(0.)
    if not isinstance(model, em.UnknownStartSIRModel):
        if model.is_regional:
            initial_i[0] = 1
        else:
            initial_i = initial_i + 1
    prev = {'S': population-initial_i, 'I': initial_i,
            'E': torch.zeros_like(population), 'D': torch.zeros_like(population),
            'O': torch.zeros_like(population)}
    recovered = torch.zeros_like(population)
    for t in range(model.duration):
        suffix = 'S2E' if 'E' in model.compartments else 'S2I'
        new = output[suffix][t]
        rec = output['I2R'][t]
        exposed = output['E2I'][t] if 'E' in model.compartments else new
        dead = output['I2D'][t] if 'D' in model.compartments else 0
        assert ((new >= 0) & (new <= prev['S'])).all()
        assert ((rec >= 0) & (rec+dead <= prev['I'])).all()
        if 'E' in model.compartments:
            assert ((exposed >= 0) & (exposed <= prev['E'])).all()
        expected = {'S': prev['S']-new, 'I': prev['I']+exposed-rec-dead,
                    'E': prev['E']+new-exposed, 'D': prev['D']+dead}
        if 'O' in model.compartments:
            report = output['S2O'][t]
            assert ((report >= 0) & (report <= new)).all()
            expected['O'] = prev['O']+report
        elif not isinstance(model, em.UnknownStartSIRModel):
            assert ((output['obs'][t] >= 0) & (output['obs'][t] <= new)).all()
        recovered = recovered+rec
        for key in model.compartments:
            value = output[key][t]
            assert torch.equal(value, expected[key])
            assert (value >= 0).all() and torch.equal(value, value.round())
        total = expected['S']+expected['I']+recovered
        if 'E' in model.compartments:
            total = total+expected['E']
        if 'D' in model.compartments:
            total = total+expected['D']
        assert torch.equal(total, population)
        prev.update(expected)


def epidemic_fit(model, method, draws=40, steps=2):
    if method == 'svi':
        invoke(model.fit_svi, kwargs=dict(num_samples=draws, num_steps=steps,
               num_particles=8, log_every=steps+1), timeout=240).value
    else:
        invoke(model.fit_mcmc, kwargs=dict(num_samples=draws, warmup_steps=steps,
               num_quant_bins=2, max_tree_depth=4, disable_progbar=True), timeout=240).value
    return invoke(model.predict, kwargs={'forecast': 2}, timeout=120).value


def epidemic_batched(model, fixed, events=None):
    events = {} if events is None else {k: torch.as_tensor(v) for k, v in events.items()}
    with velnora.plate('epidemic_draws', SAMPLE_COUNT, dim=-1-model.max_plate_nesting):
        return invoke(poutine.condition(model.generate, data=events), fixed).value


@pytest.fixture(autouse=True)
def epidemic_cpu_threads():
    """Small tensor workloads avoid machine-dependent thread oversubscription."""
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        yield
    finally:
        torch.set_num_threads(previous)


def epidemic_repetitions(model, fixed=None):
    """Independent public simulations; no batched deterministic-site assumptions."""
    return invoke(lambda: [model.generate({} if fixed is None else fixed)
                           for _ in range(2048)], timeout=120).value


def epidemic_repeated_frequency(indicator, probability):
    # Hoeffding: 2048 independent indicators and a .09 margin give
    # a two-sided error below 8e-15 per check, without an RNG-sequence oracle.
    values = np.asarray(indicator)
    assert values.shape[0] == 2048
    assert np.all(abs(values.mean(0)-probability) < .09)
