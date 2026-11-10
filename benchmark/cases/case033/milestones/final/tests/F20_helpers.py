# feature: F20
"""Independent finite sequence laws and public probabilistic observations."""
import itertools
from functools import lru_cache
import numpy as np
import torch
from scipy import stats
from velnora import poutine
from F01_helpers import assert_close
from _helpers import invoke


def fasta_sequences(path):
    records = []
    for line in path.read_text().splitlines():
        if line.startswith('>'):
            records.append('')
        else:
            assert records, 'FASTA sequence must follow a header'
            records[-1] += line
    return records


def hmm_enumeration(initial, transition, emission, observations):
    """Sum complete hidden paths; zero rows have emission weight one."""
    initial, transition, emission = map(np.asarray, (initial, transition, emission))
    observations = np.asarray(observations)
    steps, states = len(observations), len(initial)
    mass = np.zeros((steps, states))
    total = 0.
    for path in itertools.product(range(states), repeat=steps):
        weight = initial[path[0]]
        for t, state in enumerate(path):
            if t:
                weight *= transition[path[t-1], state]
            if observations[t].sum():
                weight *= emission[state, observations[t].argmax()]
        total += weight
        for t, state in enumerate(path):
            mass[t, state] += weight
    return total, mass / total


def alignment_probability(residue, insertion, ins, delete, observations):
    """Enumerate emit/skip decisions, summing all finite observed alignments."""
    residue, insertion, ins, delete = map(np.asarray, (residue, insertion, ins, delete))
    observations = np.asarray(observations)
    length = len(residue)

    def evidence(probabilities, t):
        return probabilities[observations[t].argmax()] if observations[t].sum() else 1.

    @lru_cache(None)
    def visit(t, position, previous):
        if t == len(observations):
            return 1.
        if position == length:
            return evidence(insertion[-1], t) * visit(t+1, position, 1)
        r, u = ins[position, previous, 1], delete[position, previous, 1]
        return (r * evidence(insertion[position], t) * visit(t+1, position, 1)
                + (1-r)*(1-u) * evidence(residue[position], t) * visit(t+1, position+1, 0)
                + (1-r)*u * visit(t, position+1, 2))
    return visit(0, 0, 0)


def sequence_args(model, data):
    from velnora.contrib.mue.models import FactorMuE
    return (data, torch.tensor(1.), torch.tensor(1.)) if isinstance(model, FactorMuE) else (data, torch.tensor(1.))


def sequence_trace(model, data, fixed=None, guide=False):
    call = model.guide if guide else model.model
    if fixed is not None:
        call = poutine.condition(call, data=fixed)
    return invoke(poutine.trace(call).get_trace, *sequence_args(model, data)).value


def sequence_draws(trace):
    return {name: site['value'].detach().clone() for name, site in trace.nodes.items()
            if site['type'] == 'sample' and name != 'batch' and not site['is_observed']}


def normal_site(site, location, scale):
    value = site['value'].detach().numpy()
    expected = stats.norm.logpdf(value, location, scale).sum()
    assert_close(site['fn'].log_prob(site['value']).sum(), expected)
    # A second point distinguishes a density from a stored score for its draw.
    probe = site['value'] + .37
    assert_close(site['fn'].log_prob(probe).sum(), stats.norm.logpdf(probe.detach().numpy(), location, scale).sum())


def profile_components(model, fixed):
    from velnora.contrib.mue.models import FactorMuE
    if isinstance(model, FactorMuE):
        decoded = model.decoder(fixed['latent'], fixed['W'], fixed['B'], fixed['inverse_temp'])
        residue = decoded['precursor_seq_logits'].exp()[0].detach().numpy()
        insertion = decoded['insert_seq_logits'].exp()[0].detach().numpy()
        if model.indel_factor_dependence:
            ins = decoded['insert_logits'].exp()[0].detach().numpy()
            delete = decoded['delete_logits'].exp()[0].detach().numpy()
        else:
            ins, delete = (fixed[n].softmax(-1).numpy() for n in ('insert', 'delete'))
        if model.substitution_matrix:
            weights = fixed['substitute'].exp().numpy()
            residue, insertion = residue @ weights, insertion @ weights
            residue /= residue.sum(-1, keepdims=True)
            insertion /= insertion.sum(-1, keepdims=True)
    else:
        residue, insertion, ins, delete = (fixed[n].softmax(-1).numpy()
            for n in ('precursor_seq', 'insert_seq', 'insert', 'delete'))
    return residue, insertion, ins, delete


def local_evidence(model, dataset, fixed):
    from velnora.contrib.mue.models import FactorMuE
    components = profile_components(model, fixed)
    result = []
    for data, length in dataset:
        score = np.log(alignment_probability(*components, data.numpy()))
        if isinstance(model, FactorMuE):
            guide = sequence_trace(model, data.unsqueeze(0), fixed, guide=True)
            law = guide.nodes['latent']['fn'].base_dist
            # Read the public conditional law; compare its score independently.
            z = fixed['latent'].numpy()
            family = stats.norm if model.z_prior_distribution == 'Normal' else stats.laplace
            score += family.logpdf(z).sum() - family.logpdf(z, law.loc.detach().numpy(), law.scale.detach().numpy()).sum()
        result.append(score)
    return np.asarray(result)


def fixed_evaluation(model, train, test):
    guide = sequence_trace(model, train.seq_data[:1], guide=True)
    fixed = sequence_draws(guide)
    with poutine.replay(trace=guide):
        result = invoke(model.evaluate, train, test).value
    expected = [local_evidence(model, ds, fixed) for ds in (train, test)]
    return result, expected


def predictive_sequence_score(model, dataset):
    """Observe fitted emission evidence through public guide/model calls."""
    guide = sequence_trace(model, dataset.seq_data, guide=True)
    observed = sequence_trace(model, dataset.seq_data, sequence_draws(guide))
    return observed.nodes['obs_seq']['fn'].log_prob(dataset.seq_data).sum().item()
