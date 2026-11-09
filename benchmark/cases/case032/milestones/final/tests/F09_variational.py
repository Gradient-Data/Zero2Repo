# feature: F09
"""Acceptance evidence for variational objectives and optimization."""
import pytest
from scipy import stats, special
from F01_helpers import (jax, jnp, np, dist, close, read_array, call_public,
                         check_cdf_samples, frequency)
from F08_helpers import finite_assignment_table
from F09_helpers import empty_guide, location_model, location_svi, objective_samples
import velnora
from velnora import handlers as h, optim
from velnora.primitives import mutable
from velnora.distributions import constraints
from velnora.infer import (SVI, Trace_ELBO, TraceMeanField_ELBO, TraceGraph_ELBO,
                           TraceEnum_ELBO, RenyiELBO)


def test_f09_t01():
    svi = location_svi()
    state = call_public(svi.init, jax.random.key(10), init_params={'location': jnp.array(-1.1)})
    close(svi.get_params(state)['location'], -1.1)
    before = svi.get_params(state)['location']
    close(call_public(svi.evaluate, state), -stats.norm.logpdf(2.3, float(before), 1.))
    close(svi.get_params(state)['location'], before)
    next_state, loss = call_public(svi.update, state)
    close(loss, -stats.norm.logpdf(2.3, float(before), 1.))
    assert float(svi.get_params(next_state)['location']) > float(before)
    first = call_public(svi.run, jax.random.key(1), 70, init_state=next_state, progress_bar=False, timeout=240)
    second = call_public(svi.run, jax.random.key(2), 70, init_state=first.state, progress_bar=False, timeout=240)
    whole = call_public(svi.run, jax.random.key(3), 140, init_state=next_state, progress_bar=False, timeout=240)
    assert first.losses.shape == second.losses.shape == (70,)
    close(second.losses, whole.losses[70:])
    close(second.params['location'], whole.params['location'])
    close(second.params['location'], svi.get_params(second.state)['location'])
    assert abs(float(second.params['location']) - 2.3) < .03
    close(second.losses[-1], -stats.norm.logpdf(2.3, float(second.params['location']), 1.))
    # Every returned history element represents a real objective before an update.
    manual = next_state
    values = []
    for _ in range(6):
        values.append(call_public(svi.evaluate, manual))
        manual, _ = call_public(svi.update, manual)
    close(first.losses[:6], values)
    shifted = call_public(svi.run, jax.random.key(4), 200, -1.4,
                          init_state=second.state, progress_bar=False, timeout=240)
    assert abs(float(shifted.params['location'])+1.4) < .03
    close(call_public(svi.evaluate, shifted.state, -1.4),
          -stats.norm.logpdf(-1.4, float(shifted.params['location'])))


def test_f09_t02():
    data = jnp.array([.2, -.8, 1.4, .6])
    selected = jnp.array([0, 2])
    active = jnp.array([True, False])
    def model():
        with h.scale(scale=1.7):
            with velnora.plate('rows', 4, subsample_size=2):
                velnora.factor('penalty', -.09)
                with h.mask(mask=active):
                    velnora.sample('data', dist.Normal(.4, 1.2), obs=data[selected])
    expected = -1.7 * (-.36 + 2 * stats.norm.logpdf(.2, .4, 1.2))
    # No latent uncertainty: all families must give the same exact weighted log joint.
    for cls in (Trace_ELBO, TraceMeanField_ELBO, TraceGraph_ELBO, TraceEnum_ELBO, RenyiELBO):
        close(call_public(cls().loss, jax.random.key(9), {}, model, empty_guide), expected)
    # Renyi subsampling: a data group enclosing every model and guide site is
    # supported (fixed subset, point guide: exact weighted value), while a
    # global latent outside the subsampled group is refused.
    def enclosed_model(outside):
        g = velnora.sample('g', dist.Normal(0., 1.)) if outside else 0.
        with velnora.plate('rows', 4, subsample_size=2) as rows:
            x = velnora.sample('x', dist.Normal(.3+g, 1.1))
            velnora.sample('obs', dist.Normal(x, .7), obs=data[rows])
    def enclosed_guide(outside):
        if outside:
            velnora.sample('g', dist.Normal(0., 1.))
        with velnora.plate('rows', 4, subsample_size=2):
            velnora.sample('x', dist.Delta(jnp.array([.5, -.4])))
    fixed = {'rows': jnp.array([0, 2])}
    point = (stats.norm.logpdf([.5, -.4], .3, 1.1) + stats.norm.logpdf([.2, 1.4], [.5, -.4], .7)).sum()
    for alpha in (0., .5):
        close(call_public(RenyiELBO(alpha=alpha).loss, jax.random.key(9), {},
                          h.substitute(enclosed_model, data=fixed),
                          h.substitute(enclosed_guide, data=fixed), False), -2*point)
        with pytest.raises(ValueError):
            call_public(RenyiELBO(alpha=alpha).loss, jax.random.key(9), {},
                        enclosed_model, enclosed_guide, True)
    def latent_model():
        velnora.sample('x', dist.Normal(1.2, .8))
    def guide():
        velnora.sample('x', dist.Normal(-.3, 1.1))
    expected = np.log(.8/1.1) + (1.1**2+1.5**2)/(2*.8**2)-.5
    values = objective_samples(Trace_ELBO(num_particles=32), latent_model, guide)
    # Gaussian quadratic log ratio: the broad absolute margin exceeds 9 standard errors.
    assert abs(values.mean()-expected) < .08


def test_f09_t03():
    def model():
        velnora.sample('x', dist.Normal(1.1, .7))
    def guide():
        velnora.sample('x', dist.Normal(-.4, 1.3))
    expected = np.log(.7/1.3)+(1.3**2+1.5**2)/(2*.7**2)-.5
    values = objective_samples(TraceMeanField_ELBO(), model, guide, count=16)
    close(values, np.full(16, expected))
    def enum_model():
        x = velnora.sample('x', dist.Bernoulli(.3), infer={'enumerate': 'parallel'})
        velnora.sample('obs', dist.Bernoulli(.15+.65*x), obs=1)
    _, masses = finite_assignment_table([2], lambda row:
        stats.bernoulli.pmf(row[0], .3)*(.15+.65*row[0]))
    values = objective_samples(TraceEnum_ELBO(), enum_model, empty_guide, count=16)
    close(values, np.full(16, -np.log(masses.sum())))
    def enum_guide():
        velnora.sample('x', dist.Bernoulli(.6), infer={'enumerate': 'parallel'})
    expected = sum(stats.bernoulli.pmf(x, .6) *
        (stats.bernoulli.logpmf(x, .6)-stats.bernoulli.logpmf(x, .3)-np.log(.15+.65*x))
        for x in (0, 1))
    close(objective_samples(TraceEnum_ELBO(), enum_model, enum_guide, count=16), np.full(16, expected))


def test_f09_t04():
    def model():
        x = velnora.sample('x', dist.Normal(0., 1.))
        velnora.sample('obs', dist.Normal(x, 1.), obs=0.)
    def guide():
        velnora.sample('x', dist.Normal(0., 1.))
    for cls in (Trace_ELBO, TraceMeanField_ELBO, TraceGraph_ELBO, TraceEnum_ELBO):
        for particles in (None, 16):
            objective = cls() if particles is None else cls(num_particles=particles)
            n = 1 if particles is None else particles
            values = objective_samples(objective, model, guide)
            # The loss is a shifted scaled chi-square with n independent components.
            check_cdf_samples(2*n*(values-.5*np.log(2*np.pi)), stats.chi2(n).cdf)
    def discrete_model():
        x = velnora.sample('x', dist.Bernoulli(.25))
        velnora.sample('obs', dist.Bernoulli(.1+.8*x), obs=1)
    def discrete_guide():
        p = velnora.param('p', .5, constraint=constraints.unit_interval)
        velnora.sample('x', dist.Bernoulli(p))
    svi = SVI(discrete_model, discrete_guide, optim.Adam(.025), TraceGraph_ELBO(num_particles=512))
    result = call_public(svi.run, jax.random.key(83), 700, progress_bar=False, timeout=240)
    posterior = .25*.9/(.25*.9+.75*.1)
    assert abs(float(result.params['p'])-posterior) < .055


def test_f09_t05():
    def model():
        positive = velnora.param('positive', .4, constraint=constraints.positive)
        fraction = velnora.param('fraction', .2, constraint=constraints.unit_interval)
        simplex = velnora.param('simplex', jnp.array([.6,.25,.15]), constraint=constraints.simplex)
        counter = mutable('counter', {'value': jnp.array(0.)})
        counter['value'] = counter['value'] + 1
        velnora.sample('a', dist.Normal(positive, 1.), obs=2.)
        velnora.sample('b', dist.Normal(fraction, 1.), obs=.75)
        velnora.factor('c', jnp.sum(jnp.array([2.,3.,5.])*jnp.log(simplex)))
        velnora.factor('state', -.01*counter['value'])
    for cls in (Trace_ELBO, TraceMeanField_ELBO):
        svi = SVI(model, empty_guide, optim.Adam(.05), cls())
        initial = call_public(svi.init, jax.random.key(4))
        base = float(initial.mutable_state['counter']['value'])
        state = initial
        for step in range(4):
            state, _ = call_public(svi.update, state)
            close(state.mutable_state['counter']['value'], base+step+1)
        # The carried state affects the next public objective, not just a returned counter.
        p = svi.get_params(state)
        expected = (-stats.norm.logpdf(2., float(p['positive']))
                    -stats.norm.logpdf(.75, float(p['fraction']))
                    -np.dot([2.,3.,5.], np.log(p['simplex']))+.01*(base+5))
        state, observed_loss = call_public(svi.update, state)
        close(observed_loss, expected)
        result = call_public(svi.run, jax.random.key(2), 240, init_state=state, progress_bar=False, timeout=240)
        p = result.params
        assert p['positive'] > 0 and 0 < p['fraction'] < 1
        assert np.all(read_array(p['simplex']) > 0)
        close(jnp.sum(p['simplex']), 1.)
        assert abs(float(p['positive'])-2.) < .03
        assert abs(float(p['fraction'])-.75) < .03
        np.testing.assert_allclose(p['simplex'], [.2,.3,.5], atol=.01)
        for length in (0, -3):
            with pytest.raises(ValueError):
                call_public(svi.run, jax.random.key(1), length, progress_bar=False)
    def multi_model():
        mutable('state', {'value': jnp.array(0.)})
        velnora.sample('x', dist.Normal(0., 1.))
    def multi_guide():
        velnora.sample('x', dist.Normal(0., 1.).expand((3,)))
    # An equivalent guide without model state is a supported live baseline.
    def plain_model():
        velnora.sample('x', dist.Normal(0., 1.))
    good = SVI(plain_model, multi_guide, optim.Adam(.01), Trace_ELBO(multi_sample_guide=True))
    state = call_public(good.init, jax.random.key(2))
    close(call_public(good.evaluate, state), 0.)
    with pytest.raises(ValueError):
        bad = SVI(multi_model, multi_guide, optim.Adam(.01), Trace_ELBO(multi_sample_guide=True))
        state = call_public(bad.init, jax.random.key(2))
        call_public(bad.update, state)


def test_f09_t06():
    # Independent numerical optimizer API: compare outputs only, never state layout.
    from jax.example_libraries import optimizers as reference
    schedule = lambda step: .07/(1+.2*step)
    choices = [(optim.Adam, reference.adam, {'b1': .7, 'b2': .85}),
               (optim.Adagrad, reference.adagrad, {'momentum': .4}),
               (optim.Momentum, reference.momentum, {'mass': .6}),
               (optim.RMSProp, reference.rmsprop, {'gamma': .8}),
               (optim.RMSPropMomentum, reference.rmsprop_momentum, {'gamma': .8, 'momentum': .6}),
               (optim.SGD, reference.sgd, {}),
               (optim.SM3, reference.sm3, {'momentum': .4})]
    start = {'w': jnp.array([[.7, -.2], [1.1, -.9]]), 'b': jnp.array([.3, -.8])}
    for cls, rule, kwargs in choices:
        product = cls(schedule, **kwargs)
        init, update, get = rule(schedule, **kwargs)
        actual, expected = call_public(product.init, start), init(start)
        for name in start:
            close(product.get_params(actual)[name], start[name])
        for step in range(5):
            gradient = {'w': jnp.array([[.2+step, -.5], [(-1.)**step*.8, .3-step*.1]]),
                        'b': jnp.array([.7-step*.3, -.2-step])}
            actual = call_public(product.update, gradient, actual)
            expected = update(step, gradient, expected)
            for name in start:
                close(product.get_params(actual)[name], get(expected)[name])


def test_f09_t07():
    from jax.example_libraries import optimizers as reference
    import optax
    gradients = [np.array([50., 2., -30.]), np.array([-.5, -40., 3.]), np.array([4., .3, -2.])]
    for interval in (None, 1.7):
        product = optim.ClippedAdam(.1) if interval is None else optim.ClippedAdam(.1, clip_norm=interval)
        bound = 10. if interval is None else interval
        init, update, get = reference.adam(.1)
        state, expected = product.init(jnp.array([.1,.2,.3])), init(jnp.array([.1,.2,.3]))
        for step, gradient in enumerate(gradients):
            state = call_public(product.update, jnp.asarray(gradient), state)
            expected = update(step, jnp.asarray(np.clip(gradient, -bound, bound)), expected)
            close(product.get_params(state), get(expected))
    for optimizer, steps in ((optim.Minimize(), 2),
                             (optim.optax_to_velnora(optax.sgd(.1, momentum=.3)), 120),
                             (optax.adam(.07), 200)):
        svi = location_svi(optimizer)
        result = call_public(svi.run, jax.random.key(8), steps, progress_bar=False, timeout=240)
        assert abs(float(result.params['location'])-2.3) < .01
        close(call_public(svi.evaluate, result.state), -stats.norm.logpdf(2.3, float(result.params['location'])))


def test_f09_t08():
    def model(mode=0):
        x = velnora.param('x', 0.)
        if mode == 1:
            value = x+jnp.inf
        elif mode == 2:
            value = jnp.sqrt(x)
        else:
            value = -.5*(x-1.4)**2
        velnora.factor('objective', value)
    svi = SVI(model, empty_guide, optim.Adam(.1), Trace_ELBO())
    initial = call_public(svi.init, jax.random.key(1))
    close(call_public(svi.evaluate, initial, 2), 0.)
    for mode in (1, 2):
        rejected, loss = call_public(svi.stable_update, initial, mode)
        assert np.isnan(float(loss))
        close(svi.get_params(rejected)['x'], svi.get_params(initial)['x'])
        # Several later updates expose contamination of hidden optimizer moments/counter.
        left, right = rejected, initial
        for _ in range(4):
            left, l_loss = call_public(svi.stable_update, left, 0)
            right, r_loss = call_public(svi.update, right, 0)
            close(l_loss, r_loss)
            close(svi.get_params(left)['x'], svi.get_params(right)['x'])
        assert float(svi.get_params(left)['x']) > .2


def test_f09_t09():
    def model():
        velnora.sample('x', dist.Bernoulli(.75))
    def guide():
        velnora.sample('x', dist.Bernoulli(.4))
    for alpha, particles in ((None, None), (0., 5), (-.6, 5), (.5, 5), (1.7, 5)):
        kwargs = {} if alpha is None else {'alpha': alpha, 'num_particles': particles}
        a, n = (0., 2) if alpha is None else (alpha, particles)
        values = objective_samples(RenyiELBO(**kwargs), model, guide)
        ratios = np.array([.25/.6, .75/.4])
        expected = np.array([-np.log(((n-k)*ratios[0]**(1-a)+k*ratios[1]**(1-a))/n)/(1-a)
                             for k in range(n+1)])
        distances = abs(values[:, None]-expected[None, :])
        closest = distances.argmin(axis=1)
        assert np.max(distances.min(axis=1)) < 2e-6
        for k in range(n+1):
            frequency(closest == k, stats.binom.pmf(k, n, .4))
    with pytest.raises(ValueError):
        call_public(lambda: RenyiELBO(alpha=1.).loss(jax.random.key(1), {}, model, guide))
