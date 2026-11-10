# feature: F17
"""Acceptance evidence for particle inference and the mathematical Stein kernels."""
import pytest
from F01_helpers import (jax, jnp, np, dist, stats, close, read_array,
                         call_public, check_cdf_samples, frequency, N)
from F10_helpers import ag
from F17_helpers import (stein_normal_model, stein_method, kernel_value,
                         stein_bandwidth)
import velnora
from velnora import optim
from velnora.contrib.einstein import (SVGD, ASVGD, SteinVI, RBFKernel, IMQKernel,
    LinearKernel, MixtureKernel, GraphicalKernel, ProbabilityProductKernel,
    RandomFeatureKernel, MixtureGuidePredictive)
from velnora.contrib.einstein.stein_kernels import RadialGaussNewtonKernel
from velnora.distributions import constraints
from velnora.infer import init_to_value, init_to_feasible, init_to_uniform


def test_f17_t01():
    # A one-particle point approximation has no repulsion: the RBF force is
    # exactly the normal score's magnitude, independently of the optimizer.
    point = stein_method('point', 1)
    state = call_public(point.init, jax.random.key(170))
    for offset, sd in [(1., .8), (-1., 1.4)]:
        x = float(point.get_params(state)['x_auto_loc'][0])
        mean = x + offset
        close(call_public(point.evaluate, state, mean, sd), abs(x-mean)/sd**2)
        following, force = call_public(point.update, state, mean, sd)
        close(force, abs(x-mean)/sd**2)
        if offset == 1.:
            assert abs(float(point.get_params(following)['x_auto_loc'][0])-mean) < abs(x-mean)
        state = following
    # Compare history to the force at each actual pre-update particle. The
    # initialization and optimization trajectory are chosen by the product.
    def observed(observation):
        x = velnora.sample('x', dist.Normal(0., 1.))
        velnora.sample('obs', dist.Normal(x, 1.), obs=observation)
    method = SVGD(observed, optim.Adam(.025), RBFKernel(), num_stein_particles=1)
    initial_key = jax.random.key(175)
    manual = call_public(method.init, initial_key, 30.)
    expected = []
    for _ in range(24):
        location = float(method.get_params(manual)['x_auto_loc'][0])
        expected.append(abs(30-2*location))
        manual, diagnostic = call_public(method.update, manual, 30.)
        close(diagnostic, expected[-1])
    history = call_public(method.run, initial_key, 24, 30., progress_bar=False)
    assert history.losses.shape == (24,)
    close(history.losses, expected)
    close(history.params['x_auto_loc'], method.get_params(manual)['x_auto_loc'])
    for kind, count in [('point', 64), ('annealed', 1), ('mixture', 4)]:
        method = stein_method(kind, count)
        result = call_public(method.run, jax.random.key(173), 1400,
                             progress_bar=False, timeout=600)
        assert result.losses.shape == (1400,)
        assert np.isfinite(read_array(result.losses)).all()
        close(result.params['x_auto_loc'], method.get_params(result.state)['x_auto_loc'])
        # Continue the returned state through the supported public update entry.
        next_state, force = call_public(method.update, result.state)
        assert np.isfinite(read_array(force)).all()
        again_state, again_force = call_public(method.update, result.state)
        close(method.get_params(next_state)['x_auto_loc'],
              method.get_params(again_state)['x_auto_loc'])
        close(force, again_force)
        params = method.get_params(next_state)
        loc = read_array(params['x_auto_loc'])
        grid = np.linspace(-.7, 4.1, 31)
        target = stats.norm(1.7, .8).cdf(grid)
        if kind == 'mixture':
            scale = read_array(params['x_auto_scale'])
            assert np.all(scale > 0)
            # Full mixture calibration is not promised quantitatively; the
            # original's narrow fitted scales are recorded in the ledger.
            assert abs(loc.mean()-1.7) < .3
            cdf = None
        elif kind == 'annealed':
            assert abs(loc[0]-1.7) < .1
            cdf = None
        else:
            cdf = (loc[None, :] <= grid[:, None]).mean(axis=1)
        # Numerical posterior approximation, not an exact optimization path.
        if cdf is not None:
            assert np.max(abs(cdf-target)) < .18, (kind, loc, cdf)
        def continue_fit(state):
            return jax.lax.fori_loop(0, 350,
                lambda i, current: method.update(current, -1.1, .6)[0], state)
        shifted_state = call_public(jax.jit(continue_fit), next_state, timeout=600)
        loc = read_array(method.get_params(shifted_state)['x_auto_loc'])
        assert abs(loc.mean()+1.1) < .3
    # The annealed run entry also accepts its own returned state.
    annealed = stein_method('annealed', 4)
    start = call_public(annealed.run, jax.random.key(176), 8, progress_bar=False)
    resumed = call_public(annealed.run, jax.random.key(177), 2,
                          init_state=start.state, progress_bar=False)
    assert resumed.losses.shape == (2,)


def test_f17_t02():
    def model(data=None):
        offset = velnora.param('offset', .7)
        x = velnora.sample('x', dist.Normal(0., 3.).expand((2,)).to_event(1))
        velnora.sample('y', dist.Normal(2*x+offset, .4).to_event(1), obs=data)
    def guide(data=None):
        loc = velnora.param('loc', lambda key: jax.random.normal(key, (2,)))
        velnora.sample('x', dist.Normal(loc, .3).to_event(1))
    method = SteinVI(model, guide, optim.Adam(.025), RBFKernel(),
                     num_stein_particles=3, num_elbo_particles=16)
    fitted = call_public(method.run, jax.random.key(178), 30,
                         jnp.array([1.5, -1.]), progress_bar=False, timeout=600)
    params = fitted.params
    assert params['loc'].shape == (3, 2)
    assert params['offset'].shape == ()
    result = call_public(MixtureGuidePredictive(model, guide, params,
                        guide_sites=['loc'], num_samples=N,
                        return_sites=['x', 'y']), jax.random.key(179), timeout=600)
    x, y = read_array(result['x']), read_array(result['y'])
    assert x.shape == y.shape == (N, 2)
    for d in range(2):
        loc = read_array(params['loc'])[:, d]
        check_cdf_samples(x[:, d], lambda v: stats.norm(loc, .3).cdf(v[:, None]).mean(axis=1))
        check_cdf_samples(y[:, d]-2*x[:, d]-float(params['offset']), stats.norm(0., .4).cdf)
    # Deliberately separated caller-supplied components expose single-component
    # prediction even when a trained unimodal target has nearly equal locations.
    supplied = dict(params, loc=jnp.array([[-4., 2.], [0., -3.], [5., 4.]]))
    draws = call_public(MixtureGuidePredictive(model, guide, supplied,
                         guide_sites=['loc'], num_samples=N,
                         return_sites=['x', 'y']), jax.random.key(180), timeout=600)
    assignments = read_array(draws['mixture_assignments'])
    assert assignments.shape == (N,)
    assert np.isin(assignments, [0, 1, 2]).all()
    for i in range(3):
        frequency(assignments == i, 1/3)
    residual = read_array(draws['x']) - read_array(supplied['loc'])[assignments]
    for d in range(2):
        check_cdf_samples(residual[:, d], stats.norm(0., .3).cdf)
        check_cdf_samples(read_array(draws['y'])[:, d]-2*read_array(draws['x'])[:, d]
                          -float(params['offset']), stats.norm(0., .4).cdf)


def test_f17_t03():
    particles = np.array([[-1., .3], [.4, 1.7], [2., -.6], [3.2, 2.1]])
    pairs = [(np.array([.2, -.5]), np.array([1.4, .8])),
             (np.array([-1.3, 2.]), np.array([.6, -.1]))]
    for p, factor in [(particles, None), (particles, lambda n: 2/n), (particles[:1], None)]:
        bandwidth = stein_bandwidth(p, factor)
        # None leaves the selector omitted: scalar output, and the scalar
        # diagonal for an omitted matrix selection (FP-17.03).
        for mode, matrix_mode in [(None, None), ('norm', 'norm_diag'), ('vector', 'norm_diag'),
                                  ('matrix', None), ('matrix', 'norm_diag'), ('matrix', 'vector_diag')]:
            kw = {} if factor is None else {'bandwidth_factor': factor}
            if mode is not None:
                kw['mode'] = mode
            if matrix_mode is not None:
                kw['matrix_mode'] = matrix_mode
            kernel = RBFKernel(**kw)
            for x, y in pairs:
                values = np.exp(-(x-y)**2/bandwidth)
                scalar = np.exp(-np.sum((x-y)**2)/bandwidth)
                expected = scalar if mode in (None, 'norm') else values
                if mode == 'matrix':
                    expected = np.diag(values if matrix_mode == 'vector_diag' else np.full(2, scalar))
                close(kernel_value(kernel, p, x, y), expected)
    for mode in [None, 'norm', 'vector']:
        for kwargs, c, beta in [({}, 1., -.5), ({'const': 1.8, 'expon': -.3}, 1.8, -.3)]:
            for x, y in pairs:
                delta = (x-y)**2
                expected = (c*c+(delta if mode == 'vector' else delta.sum()))**beta
                options = dict(kwargs) if mode is None else dict(kwargs, mode=mode)
                close(kernel_value(IMQKernel(**options), particles, x, y), expected)
    for x, y in pairs:
        close(kernel_value(LinearKernel(), particles, x, y), x@y+1)


def test_f17_t04():
    p = np.array([[-1., .2], [.7, 1.1], [2., -1.]])
    x, y = np.array([.5, -.2]), np.array([1.3, 2.])
    for mode in ['norm', 'vector', 'matrix']:
        first = RBFKernel(mode)
        second = RBFKernel(mode, bandwidth_factor=lambda n: 2.)
        kernel = MixtureKernel([2., 3.], [first, second], mode=mode)
        delta = (x-y)**2
        if mode != 'vector':
            delta = delta.sum()
        expected = 2*np.exp(-delta/stein_bandwidth(p))+3*np.exp(-delta/stein_bandwidth(p, lambda n: 2.))
        if mode == 'matrix':
            expected = np.eye(2)*expected
        close(kernel_value(kernel, p, x, y), expected)
    for weights, kernels in [([1.], [RBFKernel()]),
                              ([1., 2.], [RBFKernel(), RBFKernel('vector')])]:
        with pytest.raises(AssertionError):
            kernel_value(MixtureKernel(weights, kernels), p, x, y)


def test_f17_t05():
    p = np.array([[-1., .2, 1.], [.7, 1.1, -2.], [2., -1., .5]])
    x, y = np.array([.5, -.2, 1.3]), np.array([1.3, 2., -.7])
    info = {'first': (0, 2), 'second': (2, 3)}
    for default in [None, IMQKernel('vector', const=1.4, expon=-.4)]:
        kwargs = {} if default is None else {'default_kernel_fn': default}
        kernel = GraphicalKernel(local_kernel_fns={'second': LinearKernel()}, **kwargs)
        expected = np.zeros((3, 3))
        if default is None:
            value = np.exp(-np.sum((x[:2]-y[:2])**2)/stein_bandwidth(p[:, :2]))
            expected[:2, :2] = np.eye(2)*value
        else:
            expected[:2, :2] = np.diag((1.4**2+(x[:2]-y[:2])**2)**(-.4))
        expected[2, 2] = x[2]*y[2]+1
        close(kernel_value(kernel, p, x, y, info), expected)


def test_f17_t06():
    guide = ag.AutoNormal(stein_normal_model)
    info = {'x_auto_loc': (0, 2), 'x_auto_scale': (2, 4)}
    locs = np.array([[.4, -1.2], [1.9, .7]])
    scales = np.array([[.5, 1.4], [1.8, .8]])
    p = np.concatenate([locs, read_array(dist.biject_to(guide.scale_constraint).inv(jnp.asarray(scales)))], axis=1)
    for kwargs, scale in [({}, 1.), ({'scale': 2.3}, 2.3)]:
        expected = np.exp(-scale/2*np.sum((locs[0]-locs[1])**2/(scales[0]**2+scales[1]**2)))
        kernel = ProbabilityProductKernel(guide, **kwargs)
        close(kernel_value(kernel, p, p[0], p[1], info), expected)
        close(kernel_value(kernel, p, p[0], p[0], info), 1.)
    with pytest.raises(AssertionError):
        kernel_value(ProbabilityProductKernel(ag.AutoDiagonalNormal(stein_normal_model)),
                     p, p[0], p[1], info)


def test_f17_t07():
    p = jnp.array([[-1., .2], [.7, 1.1], [2., -1.], [3., 2.]])
    for subset in [None, 3]:
        kernels = [RandomFeatureKernel(bandwidth_subset=subset) for _ in range(2)]
        grams = []
        for kernel in kernels:
            call_public(kernel.init, jax.random.key(181), p.shape)
            fn = call_public(kernel.compute, jax.random.key(182), p, {}, None)
            gram = read_array(call_public(jax.vmap(lambda x: jax.vmap(lambda y: fn(x, y))(p)), p))
            assert gram.shape == (4, 4) and np.isfinite(gram).all()
            close(gram, gram.T)
            assert np.linalg.eigvalsh(gram).min() > -1e-8
            close(call_public(fn, p[0], p[1]), call_public(fn, p[0], p[1]))
            grams.append(gram)
        close(grams[0], grams[1])
    # FP-17.07 gives independent initializations at least 1/2 probability of
    # different representable similarities. Disjoint pairs give independent
    # Bernoulli observations for either a discrete or continuous law. Hoeffding
    # bounds false rejection by 1e-12, without a reference variance or formula.
    independent = []
    for key in jax.random.split(jax.random.key(184), 512):
        kernel = RandomFeatureKernel()
        call_public(kernel.init, key, p.shape)
        fn = call_public(kernel.compute, jax.random.key(182), p, {}, None)
        gram = read_array(call_public(jax.vmap(lambda x: jax.vmap(lambda y: fn(x, y))(p)), p))
        assert np.isfinite(gram).all()
        independent.append(gram)
    independent = np.stack(independent)
    pair_values = independent[:, 0, 1]
    differences = pair_values[::2] != pair_values[1::2]
    margin = np.sqrt(np.log(1e12)/(2*len(differences)))
    assert differences.mean() >= .5-margin
    assert np.any(np.ptp(independent, axis=(1, 2)) > 0)
    with pytest.raises(RuntimeError):
        kernel_value(RandomFeatureKernel(), p, p[0], p[1], initialize=False)
    kernel = RandomFeatureKernel()
    call_public(kernel.init, jax.random.key(183), p.shape)
    with pytest.raises(ValueError):
        kernel_value(kernel, p[:2], p[0], p[1], initialize=False)


def test_f17_t08():
    p = np.array([[-1., .2], [.7, 1.1], [2., -1.]])
    matrix = np.array([[1.7, .3], [.3, .8]])
    offset = np.array([.4, -.6])
    def loss(key, x, index):
        return .5*x@jnp.asarray(matrix)@x+jnp.asarray(offset)@x
    gradients = p@matrix+offset
    kernel = RadialGaussNewtonKernel()
    for delta in [np.array([.2, -.4]), np.array([1.1, .8])]:
        expected = np.exp(-np.mean((gradients@delta)**2)/(2*p.shape[1]))
        close(kernel_value(kernel, p, p[0], p[0]+delta, loss=loss), expected)
    close(kernel_value(kernel, p, p[1], p[1], loss=loss), 1.)


def test_f17_t09():
    good = stein_method('mixture', 2)
    assert np.isfinite(read_array(call_public(good.evaluate,
                       call_public(good.init, jax.random.key(184))))).all()
    guides = [ag.AutoIAFNormal(stein_normal_model), ag.AutoBNAFNormal(stein_normal_model),
              ag.AutoDAIS(stein_normal_model),
              ag.AutoSemiDAIS(stein_normal_model, stein_normal_model, stein_normal_model),
              ag.AutoSurrogateLikelihoodDAIS(stein_normal_model, stein_normal_model)]
    for guide in guides:
        with pytest.raises(AssertionError):
            method = SteinVI(stein_normal_model, guide, optim.Adam(.02), RBFKernel())
            call_public(method.init, jax.random.key(185))
    for initializer in [init_to_value(values={'x': 0.}), init_to_feasible,
                        init_to_uniform(radius=0.)]:
        with pytest.raises(AssertionError):
            method = SteinVI(stein_normal_model,
                             ag.AutoNormal(stein_normal_model, init_loc_fn=initializer),
                             optim.Adam(.02), RBFKernel())
            call_public(method.init, jax.random.key(186))
    legal = ASVGD(stein_normal_model, optim.Adam(.02), RBFKernel(),
                  num_cycles=1, transition_speed=2.)
    call_public(legal.run, jax.random.key(187), 2, progress_bar=False)
    for kwargs in [{'num_cycles': 0}, {'num_cycles': -2},
                   {'transition_speed': 0}, {'transition_speed': -1}]:
        with pytest.raises(AssertionError):
            method = ASVGD(stein_normal_model, optim.Adam(.02), RBFKernel(), **kwargs)
            call_public(method.run, jax.random.key(188), 2, progress_bar=False)
    p = np.array([[-1., .2], [.7, 1.1]])
    assert np.isfinite(kernel_value(IMQKernel(), p, p[0], p[1]))
    for kwargs in [{'const': 0}, {'const': -1}, {'expon': -1}, {'expon': 0}, {'expon': .3}]:
        with pytest.raises(AssertionError):
            kernel_value(IMQKernel(**kwargs), p, p[0], p[1])
