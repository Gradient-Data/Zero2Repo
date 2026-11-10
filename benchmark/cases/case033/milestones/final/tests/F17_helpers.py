# feature: F17
"""Real OED workloads and independent probability objectives."""
import math
import numpy as np
from scipy import stats
import torch
import velnora
from _helpers import invoke


def gaussian_design(nuisance=False):
    records = CallbackLog()

    def model(design):
        z = velnora.sample('z', velnora.distributions.Normal(torch.zeros_like(design), 1.))
        u = velnora.sample('u', velnora.distributions.Normal(torch.zeros_like(design), 1.)) if nuisance else torch.zeros_like(z)
        a = velnora.sample('a', velnora.distributions.Normal(design*z + .8*u, 1.))
        b = velnora.sample('b', velnora.distributions.Normal(.6*z - .4*u + torch.zeros_like(design), .7))
        records.append({k: v.detach().numpy().copy() for k, v in
                        dict(z=z, u=u, a=a, b=b, design=design).items()})
    return model, records


def posterior_family(target='z', offset=0., train=False, nuisance=False):
    snapshots = CallbackLog()

    def guide(observations, design, observation_labels, target_labels):
        assert target_labels == [target]
        # Exact conditional Gaussian from independent normal prior/noise.
        # With nuisance, integrate its covariance rather than counting it as a target.
        names = list(observations)
        h = torch.stack([design if k == 'a' else torch.full_like(design, .6) for k in names], -1)
        g = torch.tensor([.8 if k == 'a' else -.4 for k in names])
        noise = torch.diag(torch.tensor([1. if k == 'a' else .49 for k in names]))
        if nuisance and target == 'z':
            noise = noise + g[:, None]*g[None, :]
        if target == 'u':
            noise = noise + h.unsqueeze(-1)*h.unsqueeze(-2)
            h = g.expand_as(h)
        precision = torch.linalg.inv(noise)
        variance = 1/(1+(h.unsqueeze(-2) @ precision @ h.unsqueeze(-1)).squeeze(-1).squeeze(-1))
        y = torch.stack([observations[k] for k in names], -1)
        mean = variance*(h.unsqueeze(-2) @ precision @ y.unsqueeze(-1)).squeeze(-1).squeeze(-1)
        shift = velnora.param('posterior_shift', torch.tensor(offset)) if train else torch.tensor(offset)
        mean = mean + shift
        value = velnora.sample(target, velnora.distributions.Normal(mean, variance.sqrt()))
        record = dict(observations, design=design, **{target: value})
        snapshots.append((float(shift.detach()), names,
                          {k: v.detach().numpy().copy() for k, v in record.items()}))
    return guide, snapshots


def posterior_cross_entropy(record, labels, target='z', shift=0., nuisance=False):
    d = record['design']
    h = np.stack([d if k == 'a' else np.full_like(d, .6) for k in labels], -1)
    g = np.array([.8 if k == 'a' else -.4 for k in labels])
    noise = np.diag([1. if k == 'a' else .49 for k in labels])
    if nuisance and target == 'z':
        noise = noise + np.outer(g, g)
    if target == 'u':
        noise = noise + h[..., :, None]*h[..., None, :]
        h = np.broadcast_to(g, h.shape)
    inverse = np.linalg.inv(noise)
    v = 1/(1+np.einsum('...i,...ij,...j->...', h, inverse, h))
    y = np.stack([record[k] for k in labels], -1)
    mean = v*np.einsum('...i,...ij,...j->...', h, inverse, y)+shift
    return -stats.norm.logpdf(record[target], mean, np.sqrt(v)).mean(0)


def observation_families(train=False, nuisance=False):
    snapshots = CallbackLog()

    def marginal(design, observation_labels, target_labels):
        shift = velnora.param('marginal_shift', torch.tensor(1.4)) if train else torch.tensor(.3)
        record = {'design': design}
        # An intentionally restricted, independent approximation, not the true
        # joint observation law; objectives must use this supplied family.
        for k in observation_labels:
            record[k] = velnora.sample(k, velnora.distributions.Normal(shift.expand_as(design), 1.6 if k == 'a' else 1.2))
        snapshots.append(('marginal', float(shift.detach()),
                          {k: v.detach().numpy().copy() for k, v in record.items()}))

    def conditional(targets, design, observation_labels, target_labels):
        shift = velnora.param('conditional_shift', torch.tensor(-1.1)) if train else torch.tensor(-.2)
        record = dict(targets, design=design)
        for k in observation_labels:
            mean = (design if k == 'a' else .6)*targets['z'] + shift
            scale = math.sqrt((1. if k == 'a' else .49)+((.64 if k == 'a' else .16) if nuisance else 0.))
            record[k] = velnora.sample(k, velnora.distributions.Normal(mean, scale))
        snapshots.append(('conditional', float(shift.detach()),
                          {k: v.detach().numpy().copy() for k, v in record.items()}))
    return marginal, conditional, snapshots


def observation_objective(record, labels, marginal_shift, conditional_shift=None, nuisance=False):
    value = 0.
    for k in labels:
        value = value - stats.norm.logpdf(record[k], marginal_shift, 1.6 if k == 'a' else 1.2)
        mean = (record['design'] if k == 'a' else .6)*record['z']
        if conditional_shift is None:
            mean = mean + ((.8 if k == 'a' else -.4)*record['u'] if nuisance else 0.)
            scale = 1. if k == 'a' else .7
        else:
            mean = mean + conditional_shift
            scale = math.sqrt((1. if k == 'a' else .49)+((.64 if k == 'a' else .16) if nuisance else 0.))
        value = value + stats.norm.logpdf(record[k], mean, scale)
    return value.mean(0)


_optimization_epoch = None


class CallbackLog(list):
    """Caller callback observations associated with public optimizer updates."""
    def __init__(self):
        super().__init__()
        self.epochs = []

    def append(self, value):
        super().append(value)
        self.epochs.append(_optimization_epoch)

    def at(self, step):
        return [value for value, epoch in zip(self, self.epochs) if epoch == step]


class ObservedOptimizer:
    def __init__(self, optimizer):
        self.optimizer = optimizer

    def __call__(self, parameters):
        global _optimization_epoch
        self.optimizer(parameters)
        _optimization_epoch += 1

    def __getattr__(self, name):
        return getattr(self.optimizer, name)


def ode_call(entry, *args, **kwargs):
    global _optimization_epoch
    previous = _optimization_epoch
    _optimization_epoch = 0
    args = tuple(ObservedOptimizer(arg) if isinstance(arg, velnora.optim.VelnoraOptim)
                 else arg for arg in args)
    try:
        return invoke(entry, *args, kwargs=kwargs, timeout=180.).value
    finally:
        _optimization_epoch = previous


class PairScore(torch.nn.Module):
    """A real trainable quadratic score with an independently readable weight."""
    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.tensor(.4))
        self.calls = CallbackLog()

    def forward(self, design, trace, observation_labels, target_labels):
        z = trace.nodes[target_labels[0]]['value']
        feature = sum((trace.nodes[k]['value']-(design if k == 'a' else .6)*z).square()
                      for k in observation_labels)
        score = -self.weight*feature
        self.calls.append((float(self.weight.detach()), feature.detach().numpy().copy()))
        return score


def binary_design(nuisance=False):
    def model(design):
        z = velnora.sample('z', velnora.distributions.Bernoulli(torch.full_like(design, .5)))
        u = velnora.sample('u', velnora.distributions.Bernoulli(torch.full_like(design, .5))) if nuisance else torch.zeros_like(z)
        velnora.sample('a', velnora.distributions.Bernoulli(.5 + design*(2*z-1) + (.12*(2*u-1) if nuisance else 0.)))
        velnora.sample('b', velnora.distributions.Bernoulli(.5 + .3*(2*z-1) - (.1*(2*u-1) if nuisance else 0.)))
    return model


def binary_information(designs, labels, targets, nuisance=False):
    from itertools import product
    result = []
    for d in np.asarray(designs).flat:
        joint = {}
        for z, u in product((0, 1), repeat=2):
            if not nuisance and u:
                continue
            pa = .5+d*(2*z-1)+(.12*(2*u-1) if nuisance else 0.)
            pb = .5+.3*(2*z-1)-(.1*(2*u-1) if nuisance else 0.)
            for a, b in product((0, 1), repeat=2):
                values = dict(z=z, u=u, a=a, b=b)
                key = (tuple(values[k] for k in targets), tuple(values[k] for k in labels))
                p = (.25 if nuisance else .5)*(pa if a else 1-pa)*(pb if b else 1-pb)
                joint[key] = joint.get(key, 0.)+p
        pt, py = {}, {}
        for (t, y), p in joint.items():
            pt[t] = pt.get(t, 0.)+p
            py[y] = py.get(y, 0.)+p
        result.append(sum(p*math.log(p/(pt[t]*py[y])) for (t, y), p in joint.items()))
    return np.array(result).reshape(np.shape(designs))


def gaussian_nested_objective(outer, inner, labels, shift):
    """Independent Gaussian importance integral on the actual draw population."""
    from scipy.special import logsumexp
    h = np.stack([inner['design'] if k == 'a' else np.full_like(inner['design'], .6)
                  for k in labels], -1)
    y = np.stack([inner[k] for k in labels], -1)
    inv_noise = np.diag([1. if k == 'a' else 1/.49 for k in labels])
    v = 1/(1+np.einsum('...i,ij,...j->...', h, inv_noise, h))
    mean = v*np.einsum('...i,ij,...j->...', h, inv_noise, y)+shift
    q = stats.norm.logpdf(inner['z'], mean, np.sqrt(v))
    joint = stats.norm.logpdf(inner['z'])
    conditional = 0.
    for k in labels:
        scale = 1. if k == 'a' else .7
        joint = joint + stats.norm.logpdf(inner[k], (inner['design'] if k == 'a' else .6)*inner['z'], scale)
        conditional = conditional + stats.norm.logpdf(outer[k], (outer['design'] if k == 'a' else .6)*outer['z'], scale)
    return (conditional-logsumexp(joint-q, axis=0)+math.log(inner['z'].shape[0])).mean(0)


def assert_objective_candidates(actual, candidates):
    """Match only independently computed objectives on actual callback data.

    Callback ordering and repeated evaluation are deliberately irrelevant.
    Whole populations and sample-axis chunks are both accepted.
    """
    actual = actual.detach().numpy()
    candidates = list(candidates)
    assert candidates, "No callback population supplies the requested objective"
    assert any(np.shape(expected) == actual.shape and
               np.allclose(actual, expected, rtol=2e-6, atol=2e-7)
               for expected in candidates), (actual, candidates)


def population_records(records, count, batch_shape):
    """Read caller data by batch shape and count, never by invocation position."""
    eligible = []
    for record in records:
        shape = np.shape(record['design'])
        if len(shape) < len(batch_shape) or tuple(shape[-len(batch_shape):]) != tuple(batch_shape):
            continue
        prefix = shape[:-len(batch_shape)]
        size = math.prod(prefix)
        row = {key: np.broadcast_to(value, shape).reshape((size,)+tuple(batch_shape))
               for key, value in record.items()}
        if size == count:
            yield row
        if size < count:
            eligible.append(row)
    # A streamed evaluation can supply its entire population in several chunks.
    if eligible and sum(len(row['design']) for row in eligible) == count:
        yield {key: np.concatenate([row[key] for row in eligible], 0) for key in eligible[0]}


def posterior_objectives(snapshots, labels, count, batch_shape, target='z', nuisance=False, step=0):
    snapshots = snapshots.at(step)
    for shift in set(s[0] for s in snapshots):
        records = [s[2] for s in snapshots if s[0] == shift]
        for record in population_records(records, count, batch_shape):
            yield posterior_cross_entropy(record, labels, target, shift, nuisance)


def observation_objectives(records, snapshots, labels, count, batch_shape, paired=False, nuisance=False, step=0):
    records, snapshots = records.at(step), snapshots.at(step)
    # Join callbacks by their actual observations, not their calling order.
    for record in population_records(records, count, batch_shape):
        marginal_shifts = set()
        conditional_shifts = set()
        for kind, shift, data in snapshots:
            for candidate in population_records([data], count, batch_shape):
                if all(np.array_equal(candidate[k], record[k]) for k in labels):
                    (marginal_shifts if kind == 'marginal' else conditional_shifts).add(shift)
        for ms in marginal_shifts:
            for cs in conditional_shifts if paired else [None]:
                yield observation_objective(record, labels, ms, cs, nuisance)


def nested_objectives(records, snapshots, labels, count, batch_shape, step=0):
    records, snapshots = records.at(step), snapshots.at(step)
    outer_count, inner_count = count
    for outer in population_records(records, outer_count, batch_shape):
        for shift, names, inner in snapshots:
            if np.shape(inner['design']) != (inner_count, outer_count)+tuple(batch_shape):
                continue
            if all(np.array_equal(inner[k], np.broadcast_to(outer[k], np.shape(inner[k])))
                   for k in labels):
                yield gaussian_nested_objective(outer, inner, labels, shift)


def score_objectives(calls, count, dv=False, targetwise=False, step=0):
    """Check sample arithmetic; population semantics are calibrated separately."""
    calls = calls.at(step)
    # Callback order does not identify joint and independent populations.
    # These candidates only establish consistency with observed sample values;
    # assert_score_population_functional independently checks their required laws.
    for weight, joint in calls:
        if (joint.shape[0] if targetwise else math.prod(joint.shape[:-1])) != count:
            continue
        joint_mean = (-weight*joint).mean(0 if targetwise else tuple(range(joint.ndim-1)))
        if not dv:
            yield joint_mean
            continue
        for other_weight, independent in calls:
            if other_weight == weight and independent.shape == joint.shape:
                from scipy.special import logsumexp
                yield joint_mean-logsumexp(-weight*independent, axis=0)+math.log(count)


def assert_score_population_functional(entry, design, labels, *, dv):
    """Calibrate population roles independently of callback pairing or order."""
    count = 131072
    noise = np.diag([1. if name == 'a' else .49 for name in labels])
    # LFIRE's training objective changes when histories are requested. Both
    # paths must still evaluate the same joint score population at the end.
    for return_history in (False, True):
        model, _ = gaussian_design()
        score = PairScore()
        args = [model, design, labels, ['z'], count]
        if not dv:
            args.append(1)
        args += [1, score, velnora.optim.Adam({'lr': 0.})]
        result = ode_call(entry, *args, return_history=return_history)
        history, actual = result if return_history else ((), result)
        weight = score.weight.detach().item()
        expected = np.full(tuple(design.shape), -weight*np.trace(noise))
        if dv:
            slopes = np.stack([design.numpy() if name == 'a'
                               else np.full(tuple(design.shape), .6) for name in labels], -1)
            independent_covariance = noise + 2*slopes[..., :, None]*slopes[..., None, :]
            sign, logdet = np.linalg.slogdet(np.eye(len(labels))+2*weight*independent_covariance)
            assert (sign > 0).all()
            expected += .5*logdet
        # The score is a Gaussian quadratic. Its joint expectation is -w tr(D);
        # the independent exponential expectation is det(I+2w(D+2hh'))**(-1/2).
        # At this population size, a Gaussian quadratic-form tail bound plus
        # Bernstein's bound for the bounded exponential gives simultaneous error
        # below .04 with failure probability below 1e-10 for these workloads.
        for value in (*history, actual):
            # LFIRE retains a target-population axis in each history row.
            observed = value.detach().numpy()
            np.testing.assert_allclose(observed, np.broadcast_to(expected, observed.shape),
                                       rtol=0., atol=.04)
