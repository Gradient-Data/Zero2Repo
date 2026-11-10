# feature: F05
"""Acceptance tests for controlled execution and causal intervention."""
import pytest
from scipy import stats
from F01_helpers import (
    jax, jnp, np, dist, close, read_array, call_public,
    check_cdf_samples, frequency, N,
)
import velnora
from velnora import handlers as h
from velnora.infer.util import log_density


def test_f05_t01():
    def model():
        p = velnora.param('offset', .4)
        with velnora.plate('rows', 3):
            x = velnora.sample('latent', dist.Normal(p, .8))
            y = velnora.sample('data', dist.Normal(x, 1.2), obs=jnp.array([.2, -.1, 1.4]))
            velnora.deterministic('total', x+y)
    record = call_public(h.trace(h.seed(model, 29)).get_trace)
    assert set(record) == {'offset', 'rows', 'latent', 'data', 'total'}
    close(record['offset']['value'], .4)
    x = read_array(record['latent']['value'])
    close(record['data']['value'], [.2, -.1, 1.4])
    close(record['total']['value'], x+[.2, -.1, 1.4])
    for name, loc, scale, observed in [('latent', .4, .8, False), ('data', x, 1.2, True)]:
        site = record[name]
        assert site['is_observed'] is observed
        close(call_public(site['fn'].log_prob, site['value']), stats.norm.logpdf(site['value'], loc, scale))
        assert {(f.name, f.dim, f.size) for f in site['cond_indep_stack']} == {('rows', -1, 3)}
    for first, second in [('sample', 'sample'), ('sample', 'deterministic'), ('deterministic', 'sample'), ('deterministic', 'deterministic')]:
        def duplicate():
            for kind in (first, second):
                if kind == 'sample':
                    velnora.sample('repeated', dist.Normal(), obs=.2)
                else:
                    velnora.deterministic('repeated', .3)
        with pytest.raises(AssertionError):
            call_public(h.trace(duplicate).get_trace)


def test_f05_t02():
    def model():
        p = velnora.param('offset', .4)
        with velnora.plate('rows', 7, subsample_size=3) as indices:
            x = velnora.sample('x', dist.Normal(p, .9))
        return indices, x, x.sum()+p
    for seed in [15, 83]:
        first = call_public(h.seed(model, seed))
        second = call_public(h.seed(model, seed))
        for a, b in zip(first, second):
            np.testing.assert_array_equal(a, b)
    for binding in [dict(data={'offset': -.6, 'x': jnp.array([.2, .8, -.4])}),
                    dict(substitute_fn=lambda site: {'offset': -.6, 'x': jnp.array([.2, .8, -.4])}.get(site['name']))]:
        result = call_public(h.seed(h.substitute(model, **binding), 17))
        close(result[1], [.2, .8, -.4])
        close(result[2], 0.)
    source = call_public(h.trace(h.seed(model, 17)).get_trace)
    replayed = h.replay(model, trace=source)
    indices, x, total = call_public(h.seed(replayed, 91))
    np.testing.assert_array_equal(indices, source['rows']['value'])
    close(x, source['x']['value'])
    close(total, read_array(x).sum()+.4)
    def draw(key):
        return h.seed(lambda: velnora.sample('x', dist.Normal(.7, 1.3)), key)()
    samples = call_public(jax.jit(jax.vmap(draw)), jax.random.split(jax.random.key(51), N))
    check_cdf_samples(read_array(samples), stats.norm(.7, 1.3).cdf)


def test_f05_t03():
    def latent(obs=None):
        return velnora.sample('x', dist.Normal(.3, .8), obs=obs)
    for binding in [dict(data={'x': 1.7}), dict(condition_fn=lambda site: 1.7 if site['name'] == 'x' else None)]:
        record = call_public(h.trace(h.condition(latent, **binding)).get_trace)
        close(record['x']['value'], 1.7)
        assert record['x']['is_observed'] is True
    def draw(key):
        return h.seed(h.uncondition(h.condition(latent, data={'x': 1.7})), key)()
    values = call_public(jax.jit(jax.vmap(draw)), jax.random.split(jax.random.key(52), N))
    check_cdf_samples(read_array(values), stats.norm(.3, .8).cdf)
    record = call_public(h.trace(h.seed(h.uncondition(latent), 11)).get_trace, obs=1.7)
    assert record['x']['is_observed'] is False
    deterministic = call_public(h.trace(lambda: velnora.deterministic('x', .2)).get_trace)
    observed = call_public(h.trace(latent).get_trace, obs=1.7)
    for incompatible in [deterministic, observed]:
        with pytest.raises(RuntimeError):
            call_public(h.seed(h.replay(latent, trace=incompatible), 11))
    def group():
        with velnora.plate('x', 3):
            pass
    with pytest.raises(RuntimeError):
        call_public(h.seed(h.replay(group, trace=observed), 11))
    # An observation in the destination remains evidence, rather than being replayed.
    valid = call_public(h.trace(h.seed(latent, 5)).get_trace)
    result = call_public(h.trace(h.replay(latent, trace=valid)).get_trace, obs=-.4)
    close(result['x']['value'], -.4)
    assert result['x']['is_observed'] is True


def test_f05_t04():
    def model():
        p = velnora.param('p', .7)
        x = velnora.sample('x', dist.Normal(), obs=1.2)
        return velnora.deterministic('answer', p+2*x)
    baseline = call_public(h.trace(model).get_trace)
    assert set(baseline) == {'p', 'x', 'answer'}
    options = [({}, set()), (dict(hide_fn=lambda s: s['name'] == 'x'), {'p', 'answer'}),
               (dict(hide=['p']), {'x', 'answer'}), (dict(expose_types=['sample']), {'x'}),
               (dict(expose=['answer']), {'answer'}),
               (dict(hide_fn=lambda s: s['name'] == 'x', hide=['p'], expose_types=['param'], expose=['x']), {'p', 'answer'}),
               (dict(hide=['p'], expose_types=['param'], expose=['p']), {'x', 'answer'}),
               (dict(expose_types=['sample'], expose=['p']), {'x'})]
    for kwargs, names in options:
        with h.trace() as record:
            result = call_public(h.block(model, **kwargs))
        assert set(record) == names
        close(result, 3.1)
        for name in names:
            close(record[name]['value'], baseline[name]['value'])


def test_f05_t05():
    def part():
        p = velnora.param('offset', 0.)
        return velnora.sample('x', dist.Normal(p, .7)) + p
    def model():
        return h.scope(part, prefix='left', divider=':')(), h.scope(part, prefix='right', divider=':')()
    values = {'left:offset': -.4, 'right:offset': 1.2, 'left:x': .8, 'right:x': -1.7}
    bound = h.substitute(model, data=values)
    close(call_public(bound), [.4, -.5])
    record = call_public(h.trace(bound).get_trace)
    assert set(record) == set(values)
    for name, value in values.items():
        close(record[name]['value'], value)
    close(record['left:x']['fn'].log_prob(.8), stats.norm.logpdf(.8, -.4, .7))
    close(record['right:x']['fn'].log_prob(-1.7), stats.norm.logpdf(-1.7, 1.2, .7))


def test_f05_t06():
    data = jnp.array([-.8, .3, 1.4, 2.1])
    terms = stats.norm.logpdf(data, .2, .9)
    def model(weight=1., first=True, second=True):
        velnora.sample('outside', dist.Normal(-.3, 1.1), obs=.6)
        with h.scale(scale=weight), h.scale(scale=2.3), h.mask(mask=first), h.mask(mask=second):
            velnora.sample('inside', dist.Normal(.2, .9), obs=data)
    for weight, first, second in [(1., True, True), (.4, jnp.array([True, False, True, True]), jnp.array([False, True, True, True])), (1.7, False, True)]:
        score, _ = call_public(log_density, model, (weight, first, second), {}, {})
        close(score, stats.norm.logpdf(.6, -.3, 1.1)+weight*2.3*np.sum(np.where(np.asarray(first)&np.asarray(second), terms, 0)))
    for weight in [0., -.2]:
        with pytest.raises(ValueError):
            call_public(log_density, model, (weight,), {}, {})


def test_f05_t07():
    def model():
        a = velnora.param('shared', 10.)
        b = velnora.param('shared', 10.)
        c = velnora.param('untouched', -.5)
        velnora.sample('data', dist.Normal(a+c, .8), obs=.2, infer={'existing': 'kept'})
        return a, b, a+b+c
    lifted = h.lift(model, prior={'shared': dist.Normal(.7, 1.2)})
    def run(key):
        return h.seed(lifted, key)()
    a, b, result = call_public(jax.jit(jax.vmap(run)), jax.random.split(jax.random.key(31), N))
    check_cdf_samples(read_array(a), stats.norm(.7, 1.2).cdf)
    close(a, b)
    close(result, 2*read_array(a)-.5)
    configured = h.infer_config(lifted, config_fn=lambda s: {'role': s['name'], 'selected': s['name'] == 'data'})
    record = call_public(h.trace(h.seed(configured, 31)).get_trace)
    assert record['shared']['type'] == 'sample'
    assert record['untouched']['type'] == 'param'
    close(record['untouched']['value'], -.5)
    for name in ['shared', 'data']:
        assert record[name]['infer']['role'] == name
        assert record[name]['infer']['selected'] is (name == 'data')
    assert record['data']['infer']['existing'] == 'kept'
    # A distribution prior also applies to parameters without a name mapping.
    all_lifted = call_public(h.trace(h.seed(h.lift(model, prior=dist.Normal()), 32)).get_trace)
    assert all_lifted['untouched']['type'] == 'sample'


def test_f05_t08():
    def model(observation=None):
        u = velnora.sample('upstream', dist.Bernoulli(.3))
        v = velnora.sample('child', dist.Bernoulli(.15+.7*u), obs=observation)
        return velnora.deterministic('result', 2*u+3*v)
    intervened = h.do(model, data={'child': 1.})
    conditioned = h.condition(model, data={'child': 1.})
    def draw(key):
        with h.trace() as record:
            result = h.seed(intervened, key)()
        return record['upstream']['value'], record['child']['value'], result
    upstream, original, result = call_public(jax.jit(jax.vmap(draw)), jax.random.split(jax.random.key(72), N))
    frequency(read_array(upstream), .3)
    frequency(read_array(original), .7*.15+.3*.85)
    frequency((read_array(upstream) == 1) & (read_array(original) == 1), .3*.85)
    close(result, 2*read_array(upstream)+3)
    for obs in [None, 0.]:
        record = call_public(h.trace(h.seed(intervened, 72)).get_trace, obs)
        assert record['child']['is_observed'] is (obs is not None)
        if obs is not None:
            close(record['child']['value'], obs)
        close(record['result']['value'], 2*record['upstream']['value']+3)
    masses = []
    evidence = []
    for u in [0., 1.]:
        total = 0.
        for v in [0., 1.]:
            score, _ = call_public(log_density, intervened, (), {}, {'upstream': u, 'child': v})
            total += np.exp(float(score))
        masses.append(total)
        score, record = call_public(log_density, conditioned, (), {}, {'upstream': u})
        evidence.append(np.exp(float(score)))
        close(record['child']['value'], 1.)
        assert record['child']['is_observed'] is True
    close(masses, [.7, .3])
    close(evidence, [.7*.15, .3*.85])
    close(np.asarray(evidence)/sum(evidence), np.array([.7*.15, .3*.85])/(.7*.15+.3*.85))
