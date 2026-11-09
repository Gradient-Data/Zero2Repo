# feature: F06
"""Acceptance tests for structured probabilistic control flow."""
import pytest
from scipy import stats
from F01_helpers import (
    jax, jnp, np, dist, close, read_array, call_public,
    check_cdf_samples, N,
)
import velnora
from velnora import handlers as h
from velnora.contrib.control_flow import scan, cond
from velnora.contrib.funsor import enum, config_enumerate
from velnora.infer.util import log_density


def test_f06_t01():
    for inputs, initial in [([.2, -.7, 1.1, .4], .6), ([-.3, .8, .1], -1.2)]:
        inputs = np.array(inputs)
        trajectory = np.linspace(-.6, 1.3, len(inputs))
        observations = np.linspace(1.1, -.4, len(inputs))
        for reverse in [False, True]:
            means = np.empty(len(inputs))
            outputs = np.empty(len(inputs))
            carry = initial
            order = range(len(inputs)-1, -1, -1) if reverse else range(len(inputs))
            for t in order:
                means[t] = .7*carry + inputs[t]
                carry = trajectory[t] + .2*carry
                outputs[t] = carry + observations[t]
            def model():
                def step(previous, item):
                    x, y, observed_state = item
                    latent = velnora.sample('state', dist.Normal(.7*previous+x, .8), obs=observed_state if reverse else None)
                    observed = velnora.sample('data', dist.Normal(latent-x, 1.1), obs=y)
                    current = latent + .2*previous
                    return current, current+observed
                return scan(step, jnp.asarray(initial), (jnp.asarray(inputs), jnp.asarray(observations), jnp.asarray(trajectory)), reverse=reverse)
            for binder in ([h.condition] if reverse else [h.substitute, h.condition]):
                bound = model if reverse else binder(model, data={'state': jnp.asarray(trajectory)})
                with h.trace() as record:
                    final, sequence = call_public(h.seed(bound, 21))
                close(final, carry)
                close(sequence, outputs)
                assert record['state']['value'].shape == (len(inputs),)
                close(record['state']['value'], trajectory)
                close(record['data']['value'], observations)
                assert record['state']['is_observed'] is (binder is h.condition)
                assert record['data']['is_observed'] is True
                close(call_public(record['state']['fn'].log_prob, record['state']['value']), stats.norm.logpdf(trajectory, means, .8))
                close(call_public(record['data']['fn'].log_prob, record['data']['value']), stats.norm.logpdf(observations, trajectory-inputs, 1.1))


def test_f06_t02():
    inputs = jnp.array([.2, -.4, .9, .1])
    supplied = jnp.asarray(np.linspace(-.7, 1.2, 24).reshape(4, 3, 2))
    observations = supplied*.3+.5
    active = jnp.array([[True, False, True], [False, True, True], [True, True, False], [False, False, True]])
    def model():
        def step(previous, item):
            x, y, included = item
            with velnora.plate('rows', 3, dim=-1), h.mask(mask=included):
                z = velnora.sample('latent', dist.Normal(previous+x, .7).to_event(1))
                velnora.sample('data', dist.Normal(z*2, 1.2).to_event(1), obs=y)
                result = velnora.deterministic('derived', z+previous)
            return z, result
        return scan(step, jnp.zeros((3, 2)), (inputs, observations, active))
    # Replay uses a real seeded execution, not a fabricated trace.
    source = call_public(h.trace(h.seed(model, 32)).get_trace)
    for bound, expected, observed in [
        (h.substitute(model, data={'latent': supplied}), supplied, False),
        (h.condition(model, data={'latent': supplied}), supplied, True),
        (h.replay(model, trace=source), source['latent']['value'], False),
    ]:
        previous = np.concatenate([np.zeros((1, 3, 2)), read_array(expected)[:-1]], axis=0)
        with h.trace() as record:
            final, sequence = call_public(h.seed(bound, 93))
        close(final, expected[-1])
        close(sequence, read_array(expected)+previous)
        close(record['derived']['value'], read_array(expected)+previous)
        close(record['latent']['value'], expected)
        assert record['latent']['is_observed'] is observed
        assert record['data']['is_observed'] is True
        close(record['data']['value'], observations)
        for name in ['latent', 'data']:
            assert record[name]['value'].shape == (4, 3, 2)
            assert {(f.name, f.dim, f.size) for f in record[name]['cond_indep_stack']} == {('rows', -1, 3)}
        latent_terms = stats.norm.logpdf(expected, previous+read_array(inputs)[:, None, None], .7).sum(-1)
        data_terms = stats.norm.logpdf(observations, read_array(expected)*2, 1.2).sum(-1)
        close(call_public(record['latent']['fn'].log_prob, expected), np.where(active, latent_terms, 0.))
        close(call_public(record['data']['fn'].log_prob, observations), np.where(active, data_terms, 0.))
        score, _ = call_public(log_density, h.seed(bound, 93), (), {}, {})
        close(score, np.where(active, latent_terms+data_terms, 0.).sum())


def test_f06_t03():
    def model(predicate, operand):
        def branch(multiplier, offset, scale):
            def run(value):
                z = velnora.sample('latent', dist.Normal(multiplier*value+offset, scale))
                y = velnora.sample('data', dist.Normal(z+offset, .9), obs=value-.2)
                d = velnora.deterministic('derived', multiplier*z+y)
                return z, d+value
            return run
        return cond(predicate, branch(2., .7, .6), branch(-1., -.4, 1.3), operand)
    for predicate in [False, True]:
        multiplier, offset, scale = (2., .7, .6) if predicate else (-1., -.4, 1.3)
        for operand in [-.3, 1.1]:
            for binder in [h.substitute, h.condition]:
                bound = binder(model, data={'latent': .8})
                with h.trace() as record:
                    result = call_public(h.seed(bound, 61), predicate, jnp.asarray(operand))
                close(result, [.8, multiplier*.8+operand-.2+operand])
                close(record['derived']['value'], multiplier*.8+operand-.2)
                close(record['data']['value'], operand-.2)
                assert record['data']['is_observed'] is True
                assert record['latent']['is_observed'] is (binder is h.condition)
                close(call_public(record['latent']['fn'].log_prob, .8), stats.norm.logpdf(.8, multiplier*operand+offset, scale))
                close(call_public(record['data']['fn'].log_prob, operand-.2), stats.norm.logpdf(operand-.2, .8+offset, .9))
            # Deterministic replacements must travel through the conditional too.
            replaced = h.substitute(model, data={'latent': .8, 'derived': -2.4})
            result = call_public(h.seed(replaced, 61), predicate, jnp.asarray(operand))
            close(result, [.8, -2.4+operand])
        def draw(key):
            return h.seed(model, key)(predicate, jnp.asarray(.4))[0]
        samples = call_public(jax.jit(jax.vmap(draw)), jax.random.split(jax.random.key(62), N))
        check_cdf_samples(read_array(samples), stats.norm(multiplier*.4+offset, scale).cdf)


def test_f06_t04():
    def model(predicate):
        def yes(value):
            return velnora.sample('choice', dist.Bernoulli(.8)) + value
        def no(value):
            return velnora.sample('choice', dist.Bernoulli(.2)) - value
        return cond(predicate, yes, no, jnp.asarray(.4))
    for predicate, probability, result in [(True, .8, 1.4), (False, .2, .6)]:
        bound = h.substitute(model, data={'choice': jnp.asarray(1.)})
        with h.trace() as record:
            actual = call_public(h.seed(bound, 12), predicate)
        close(actual, result)
        close(call_public(record['choice']['fn'].log_prob, 1.), np.log(probability))
        with pytest.raises(RuntimeError):
            call_public(h.seed(enum(config_enumerate(model), first_available_dim=-1), 12), predicate)
