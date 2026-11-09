# feature: F01
"""Independent probability observations and bounded statistical checks."""
import velnora
import numpy as np
import torch
from scipy import integrate, stats

SAMPLE_COUNT = 40000


def assert_close(actual, expected):
    np.testing.assert_allclose(actual.detach().cpu().numpy(), expected,
                               rtol=2e-6, atol=2e-7)


def assert_frequency(indicator, probability):
    # Hoeffding: each bounded indicator has two-sided error <= 2 exp(-50).
    # Fewer than 1000 bounded frequency checks give total error < 4e-19.
    assert indicator.shape[0] == SAMPLE_COUNT
    assert_close_frequencies = np.asarray(indicator.double().mean(0).cpu())
    assert np.all(np.abs(assert_close_frequencies - probability) < 0.025)


def projected_density(location, direction):
    """Integrate a normal density along a ray with the polar volume element."""
    location, direction = np.asarray(location), np.asarray(direction)
    dimension = len(location)
    result, error = integrate.quad(
        lambda radius: radius ** (dimension - 1) * np.exp(
            stats.multivariate_normal.logpdf(radius * direction, mean=location)),
        0, np.inf, epsabs=1e-11, epsrel=1e-11)
    assert error < 1e-8
    return result


def scalar_cases(include_variations=False):
    """Public constructors paired with independently parameterized scalar laws.

    Geometric counts failures before success. Negative binomial counts successes
    before the supplied failure count, hence the complementary SciPy probability.
    Scale denotes standard deviation for normals; gamma parameters are shape/rate.
    """
    from scipy import special
    cases = []

    def add(name, parameters, observations, reference, discrete=False, fixed=()):
        cases.append((name, getattr(velnora.distributions, name), parameters, np.asarray(observations),
                      reference, discrete, fixed))

    add('Bernoulli', {'probs': .3}, [0., 1.], lambda p, x: stats.bernoulli.logpmf(x, p['probs']), True)
    add('Binomial', {'total_count': 7., 'probs': .35}, [0., 2., 6.], lambda p, x: stats.binom.logpmf(x, p['total_count'], p['probs']), True, ('total_count',))
    add('Categorical', {'probs': np.array([.15, .55, .30])}, [0, 1, 2], lambda p, x: np.log((p['probs']/p['probs'].sum())[np.asarray(x, dtype=int)]), True)
    add('Multinomial', {'probs': np.array([.2, .3, .5])}, [[1., 2., 2.], [0., 1., 4.]], lambda p, x: stats.multinomial.logpmf(x, 5, p['probs']/p['probs'].sum()), True)
    add('Geometric', {'probs': .4}, [0., 1., 4.], lambda p, x: stats.geom.logpmf(x+1, p['probs']), True)
    add('Poisson', {'rate': 2.3}, [0., 2., 5.], lambda p, x: stats.poisson.logpmf(x, p['rate']), True)
    add('NegativeBinomial', {'total_count': 3.2, 'probs': .35}, [0., 2., 5.], lambda p, x: stats.nbinom.logpmf(x, p['total_count'], 1-p['probs']), True)
    add('Beta', {'concentration1': 2.3, 'concentration0': 3.1}, [.2, .45, .8], lambda p, x: stats.beta.logpdf(x, p['concentration1'], p['concentration0']))
    add('ContinuousBernoulli', {'probs': .3}, [.1, .4, .9], lambda p, x: x*np.log(p['probs'])+(1-x)*np.log1p(-p['probs']) + np.log(np.log(p['probs']/(1-p['probs']))/(2*p['probs']-1)))
    add('Cauchy', {'loc': -.4, 'scale': 1.3}, [-2., .1, 3.], lambda p, x: stats.cauchy.logpdf(x, p['loc'], p['scale']))
    add('Chi2', {'df': 4.5}, [.5, 2., 7.], lambda p, x: stats.chi2.logpdf(x, p['df']))
    add('Exponential', {'rate': 1.7}, [.1, .8, 2.], lambda p, x: stats.expon.logpdf(x, scale=1/p['rate']))
    add('FisherSnedecor', {'df1': 4.2, 'df2': 8.3}, [.3, 1., 3.], lambda p, x: stats.f.logpdf(x, p['df1'], p['df2']))
    add('Gamma', {'concentration': 2.4, 'rate': 1.3}, [.2, 1., 4.], lambda p, x: stats.gamma.logpdf(x, p['concentration'], scale=1/p['rate']))
    add('InverseGamma', {'concentration': 3.4, 'rate': 2.1}, [.3, 1., 3.], lambda p, x: stats.invgamma.logpdf(x, p['concentration'], scale=p['rate']))
    add('Gumbel', {'loc': -.3, 'scale': 1.2}, [-1., .4, 2.], lambda p, x: stats.gumbel_r.logpdf(x, p['loc'], p['scale']))
    add('HalfCauchy', {'scale': 1.4}, [.2, 1., 4.], lambda p, x: stats.halfcauchy.logpdf(x, scale=p['scale']))
    add('HalfNormal', {'scale': 1.4}, [.2, 1., 3.], lambda p, x: stats.halfnorm.logpdf(x, scale=p['scale']))
    add('Kumaraswamy', {'concentration1': 2.2, 'concentration0': 3.4}, [.2, .5, .8], lambda p, x: np.log(p['concentration1']*p['concentration0'])+(p['concentration1']-1)*np.log(x)+(p['concentration0']-1)*np.log1p(-x**p['concentration1']))
    for name, scipy_name in [('Laplace', 'laplace'), ('Logistic', 'logistic'), ('Normal', 'norm')]:
        reference = getattr(stats, scipy_name)
        add(name, {'loc': .4, 'scale': 1.3}, [-1., .2, 2.], lambda p, x, ref=reference: ref.logpdf(x, p['loc'], p['scale']))
    add('LogNormal', {'loc': .2, 'scale': .7}, [.3, 1., 4.], lambda p, x: stats.lognorm.logpdf(x, p['scale'], scale=np.exp(p['loc'])))
    add('Pareto', {'scale': 1.2, 'alpha': 2.7}, [1.4, 2., 5.], lambda p, x: stats.pareto.logpdf(x, p['alpha'], scale=p['scale']))
    add('StudentT', {'df': 8.5, 'loc': -.3, 'scale': 1.2}, [-2., .2, 3.], lambda p, x: stats.t.logpdf(x, p['df'], p['loc'], p['scale']))
    add('Uniform', {'low': -1.2, 'high': 2.3}, [-1., .3, 2.], lambda p, x: stats.uniform.logpdf(x, p['low'], p['high']-p['low']))
    add('VonMises', {'loc': .3, 'concentration': 1.8}, [-2., .2, 2.], lambda p, x: stats.vonmises.logpdf(x, p['concentration'], loc=p['loc']))
    add('Weibull', {'scale': 1.4, 'concentration': 2.2}, [.2, 1., 3.], lambda p, x: stats.weibull_min.logpdf(x, p['concentration'], scale=p['scale']))
    if include_variations:
        variations = []
        for name, constructor, parameters, values, oracle, discrete, fixed in cases:
            changed = {}
            for key, value in parameters.items():
                if key in fixed:
                    changed[key] = value
                elif key == 'probs':
                    changed[key] = np.roll(value, 1) if np.ndim(value) else value + .25
                elif key == 'loc':
                    changed[key] = value + 1.
                elif key == 'low':
                    changed[key] = value - .8
                elif key == 'high':
                    changed[key] = value + 1.5
                elif key in ('rate', 'concentration0'):
                    changed[key] = value * .7
                elif key == 'scale':
                    changed[key] = value * (.8 if name == 'Pareto' else 1.6)
                else:
                    changed[key] = value * 1.8
            variations.append((name, constructor, changed, values, oracle, discrete, fixed))
        cases += variations
    return cases


def make_scalar(case, parameters=None):
    name, constructor, defaults, _, _, _, _ = case
    parameters = defaults if parameters is None else parameters
    tensors = {key: torch.as_tensor(value, dtype=torch.float64) for key, value in parameters.items()}
    if name == 'Multinomial':
        return constructor(total_count=5, **tensors)
    return constructor(**tensors)


def finite_difference(function, value):
    """Central differences of an independent numerical oracle, not the product."""
    value = np.array(value, dtype=float)
    result = np.empty_like(value)
    for index in np.ndindex(value.shape):
        step = 1e-5 * max(1., abs(value[index]))
        plus, minus = value.copy(), value.copy()
        plus[index] += step
        minus[index] -= step
        result[index] = (function(plus.item() if plus.ndim == 0 else plus)-function(minus.item() if minus.ndim == 0 else minus))/(2*step)
    return result


def assert_density_gradients(builder, parameters, value, oracle, *, observation=True, fixed=()):
    """Differentiate public scores and compare with independent score derivatives."""
    tensors = {key: torch.tensor(v, dtype=torch.float64, requires_grad=key not in fixed)
               for key, v in parameters.items()}
    x = torch.tensor(value, dtype=torch.float64, requires_grad=bool(observation))
    inputs = [v for v in tensors.values() if v.requires_grad] + ([x] if observation else [])
    result = builder(tensors).log_prob(x).sum()
    assert result.requires_grad
    gradients = torch.autograd.grad(result, inputs, allow_unused=True)
    expected = []
    for key in parameters:
        if key not in fixed:
            expected.append(finite_difference(lambda v: np.asarray(oracle(dict(parameters, **{key:v}), value)).sum(), parameters[key]))
    if observation:
        actual = gradients[-1]
        if isinstance(observation, str):
            assert actual is not None
        if observation == 'simplex':
            base = np.asarray(value)
            def shifted(v):
                out = base.copy()
                out[..., :-1] = v
                out[..., -1] += (base[..., :-1]-v).sum(-1)
                return np.asarray(oracle(parameters, out)).sum()
            reference = finite_difference(shifted, base[..., :-1])
            np.testing.assert_allclose((actual[..., :-1]-actual[..., -1:]).detach().numpy(), reference, rtol=3e-4, atol=3e-5)
        elif observation == 'sphere':
            base = np.asarray(value)
            tangent = np.eye(base.shape[-1])-np.outer(base,base)
            for direction in tangent:
                plus,minus=base+1e-5*direction,base-1e-5*direction
                plus,minus=plus/np.linalg.norm(plus),minus/np.linalg.norm(minus)
                reference=(oracle(parameters,plus)-oracle(parameters,minus))/2e-5
                measured=(actual*torch.tensor(direction)).sum().item()
                np.testing.assert_allclose(measured,reference,rtol=3e-4,atol=3e-5)
        elif observation in ('symmetric', 'correlation'):
            base = np.asarray(value)
            for row in range(base.shape[-1]):
                for col in range(row, base.shape[-1]):
                    if row == col and observation == 'correlation':
                        continue
                    direction = np.zeros_like(base)
                    direction[..., row, col] = 1
                    direction[..., col, row] = 1
                    reference = (np.asarray(oracle(parameters, base+1e-5*direction)).sum()-np.asarray(oracle(parameters, base-1e-5*direction)).sum())/2e-5
                    measured = (actual*torch.tensor(direction)).sum().item()
                    np.testing.assert_allclose(measured, reference, rtol=3e-4, atol=3e-5)
        else:
            expected.append(finite_difference(lambda v: np.asarray(oracle(parameters, v)).sum(), value))
        if isinstance(observation, str):
            gradients = gradients[:-1]
    for actual, reference in zip(gradients, expected):
        # Autograd represents an unused input by None. This is a legitimate zero
        # derivative only when the independent law has zero derivative too.
        if actual is None:
            np.testing.assert_allclose(reference, 0., rtol=0., atol=1e-8)
            continue
        np.testing.assert_allclose(actual.detach().numpy(), reference, rtol=3e-4, atol=3e-5)


def logistic_normal_score(parameters, value):
    value = np.asarray(value)
    remaining = 1 - np.concatenate([np.zeros(value.shape[:-1]+(1,)), np.cumsum(value[..., :-2], axis=-1)], axis=-1)
    tail = remaining - value[..., :-1]
    latent = np.log(value[..., :-1]/tail) + np.log(np.arange(value.shape[-1]-1, 0, -1))
    log_jacobian = (np.log(value[..., :-1]) + np.log(tail) - np.log(remaining)).sum(-1)
    return stats.norm.logpdf(latent, parameters['loc'], parameters['scale']).sum(-1)-log_jacobian


def vector_cases():
    """Vector/matrix laws with independent standard probability references."""
    from scipy import special

    def covariance(p):
        lower = np.array([[p['diagonal'][0], 0.], [p['off'], p['diagonal'][1]]])
        return lower @ lower.T

    def lower(p):
        return torch.stack([torch.stack([p['diagonal'][0], p['off']*0]),
                            torch.stack([p['off'], p['diagonal'][1]])])

    loc = np.array([-.4, .8])
    shape = {'loc':loc, 'diagonal':np.array([1.2, .7]), 'off':.65}
    values = np.array([[-1., .3], [.5, 1.4], [2., -.5]])
    normal_ref = lambda p, x: stats.multivariate_normal.logpdf(x, p['loc'], covariance(p))
    cases = [
        ('MultivariateNormal', lambda p: velnora.distributions.MultivariateNormal(p['loc'], scale_tril=lower(p)), shape, values, normal_ref, True),
        ('LowRankMultivariateNormal', lambda p: velnora.distributions.LowRankMultivariateNormal(p['loc'], p['factor'], p['diag']),
         {'loc':loc, 'factor':np.array([[.9],[.6]]), 'diag':np.array([.5,.8])}, values,
         lambda p, x: stats.multivariate_normal.logpdf(x, p['loc'], p['factor']@p['factor'].T+np.diag(p['diag'])), True),
        ('MultivariateStudentT', lambda p: velnora.distributions.MultivariateStudentT(p['df'], p['loc'], lower(p)),
         dict(shape, df=8.2), values, lambda p, x: stats.multivariate_t.logpdf(x, p['loc'], covariance(p), p['df']), True),
        ('Dirichlet', lambda p: velnora.distributions.Dirichlet(p['concentration']), {'concentration':np.array([1.4,2.3,3.2])},
         np.array([[.2,.3,.5],[.5,.4,.1]]),
         lambda p, x: special.gammaln(np.sum(p['concentration']))-special.gammaln(p['concentration']).sum()+((p['concentration']-1)*np.log(x)).sum(-1), 'simplex'),
        ('LogisticNormal', lambda p: velnora.distributions.LogisticNormal(p['loc'], p['scale']),
         {'loc':np.array([.4,-.7]), 'scale':np.array([.8,1.2])}, np.array([[.2,.3,.5],[.5,.4,.1]]), logistic_normal_score, 'simplex'),
        ('Wishart', lambda p: velnora.distributions.Wishart(p['df'], covariance_matrix=p['scale']*torch.tensor([[1.,.3],[.3,1.4]])),
         {'df':6.3, 'scale':1.2}, np.array([[[2.,.3],[.3,1.5]], [[4.,-.4],[-.4,2.]]]),
         lambda p, x: np.array([stats.wishart.logpdf(matrix, p['df'], p['scale']*np.array([[1.,.3],[.3,1.4]])) for matrix in x]), 'symmetric'),
        ('LKJ', lambda p: velnora.distributions.LKJ(2, p['concentration']), {'concentration':2.4},
         np.array([[[1.,.2],[.2,1.]], [[1.,-.6],[-.6,1.]]]),
         lambda p, x: stats.beta.logpdf((np.asarray(x)[...,0,1]+1)/2, p['concentration'], p['concentration'])-np.log(2.), 'correlation'),
    ]
    return cases


def compound_cases():
    from scipy import special
    def dm(p, x):
        x = np.asarray(x)
        alpha = p['concentration']
        n = x.sum(-1)
        return special.gammaln(n+1)-special.gammaln(x+1).sum(-1)+special.gammaln(alpha.sum())-special.gammaln(n+alpha.sum())+(special.gammaln(x+alpha)-special.gammaln(alpha)).sum(-1)
    def zi(reference, p, x):
        base = reference(p, x)
        return np.where(np.asarray(x)==0, np.logaddexp(np.log(p['gate']), np.log1p(-p['gate'])+base), np.log1p(-p['gate'])+base)
    poisson = lambda p, x: stats.poisson.logpmf(x, p['rate'])
    nb = lambda p, x: stats.nbinom.logpmf(x, p['total_count'], 1-p['probs'])
    return [
        ('BetaBinomial', lambda p: velnora.distributions.BetaBinomial(p['concentration1'], p['concentration0'], total_count=6),
         {'concentration1':1.4,'concentration0':2.7}, np.arange(7.),
         lambda p,x: stats.betabinom.logpmf(x, 6, p['concentration1'],p['concentration0'])),
        ('DirichletMultinomial', lambda p: velnora.distributions.DirichletMultinomial(p['concentration'], total_count=5),
         {'concentration':np.array([1.2,2.3,3.4])}, np.array([[0.,0.,5.],[1.,2.,2.],[4.,1.,0.]]),dm),
        ('GammaPoisson', lambda p: velnora.distributions.GammaPoisson(p['concentration'], p['rate']),
         {'concentration':2.3,'rate':1.7}, np.arange(6.),
         lambda p,x: stats.nbinom.logpmf(x,p['concentration'],p['rate']/(p['rate']+1))),
        ('ZeroInflatedPoisson', lambda p: velnora.distributions.ZeroInflatedPoisson(p['rate'],gate=p['gate']),
         {'rate':2.4,'gate':.3},np.arange(6.), lambda p,x: zi(poisson,p,x)),
        ('ZeroInflatedNegativeBinomial', lambda p: velnora.distributions.ZeroInflatedNegativeBinomial(p['total_count'],probs=p['probs'],gate=p['gate']),
         {'total_count':3.2,'probs':.4,'gate':.25},np.arange(6.),lambda p,x: zi(nb,p,x)),
    ]


def mixture_cases():
    from scipy import special
    def score(p, x):
        logits = p['component_logits']
        scales = p['coord_scale']
        scores = stats.norm.logpdf(np.asarray(x)[...,None,:],p['locs'],scales).sum(-1)
        return special.logsumexp(scores+logits-special.logsumexp(logits),axis=-1)
    locs = np.array([[-2.,1.],[3.,-1.]])
    logits = np.log([.3,.7])
    values = np.array([[-1.,.5],[2.,-2.],[0.,0.]])
    return [
        ('MixtureOfDiagNormals',lambda p:velnora.distributions.MixtureOfDiagNormals(**p),
         {'locs':locs,'coord_scale':np.array([[.7,1.2],[1.3,.6]]),'component_logits':logits},values,score),
        ('MixtureOfDiagNormalsSharedCovariance',lambda p:velnora.distributions.MixtureOfDiagNormalsSharedCovariance(**p),
         {'locs':locs,'coord_scale':np.array([.8,1.1]),'component_logits':logits},values,score),
    ]


def tensor_parameters(parameters):
    return {key:torch.as_tensor(value,dtype=torch.float64) for key,value in parameters.items()}


def additional_score_cases():
    from scipy import special
    mask = np.array([False, True, False])
    def ordered(p,x):
        cumulative = special.expit(p['cutpoints']-np.asarray(p['predictor'])[...,None])
        probabilities = np.diff(np.concatenate([np.zeros(cumulative.shape[:-1]+(1,)),cumulative,np.ones(cumulative.shape[:-1]+(1,))],-1),axis=-1)
        return np.log(np.take_along_axis(probabilities,np.asarray(x,dtype=int)[...,None],-1)[...,0])
    events = np.array([[-3.,2.],[1.,7.],[5.,-1.]])
    def empirical(p,x):
        weights = special.softmax(p['log_weights'])
        return np.log(weights[np.all(events==x,axis=-1)].sum())
    def missing_mv(p,x):
        covariance = p['scale']*np.array([[1.3,.5],[.5,1.7]])
        result = []
        for row in x:
            observed = np.isfinite(row)
            result.append(stats.multivariate_normal.logpdf(row[observed],p['loc'][observed],covariance[np.ix_(observed,observed)]) if observed.any() else 0.)
        return np.array(result)
    cases = [
        ('Empirical',lambda p:velnora.distributions.Empirical(torch.tensor(events),p['log_weights']),{'log_weights':np.log([.2,.3,.5])},events[1],empirical,False),
        ('MaskedMixture',lambda p:velnora.distributions.MaskedMixture(torch.tensor(mask),velnora.distributions.Normal(p['loc0'],p['scale0']),velnora.distributions.Normal(p['loc1'],p['scale1'])),
         {'loc0':-.5,'scale0':.8,'loc1':1.2,'scale1':1.4},np.array([-.2,.5,1.]),
         lambda p,x:stats.norm.logpdf(x,np.where(mask,p['loc1'],p['loc0']),np.where(mask,p['scale1'],p['scale0'])),True),
        ('MaskedNormal',lambda p:velnora.distributions.Normal(p['loc'],p['scale']).mask(torch.tensor(mask)),
         {'loc':np.array([-.2,.3,1.]),'scale':np.array([.8,1.2,.7])},np.array([0.,1.,2.]),
         lambda p,x:np.where(mask,stats.norm.logpdf(x,p['loc'],p['scale']),0.),True),
        ('NanMaskedNormal',lambda p:velnora.distributions.NanMaskedNormal(p['loc'],p['scale']),{'loc':np.array([-.4,.8,1.2]),'scale':np.array([.7,1.2,.8])},
         np.array([.2,np.nan,2.]),lambda p,x:np.where(np.isnan(x),0.,stats.norm.logpdf(x,p['loc'],p['scale'])),True),
        ('NanMaskedMultivariateNormal',lambda p:velnora.distributions.NanMaskedMultivariateNormal(p['loc'],p['scale']*torch.tensor([[1.3,.5],[.5,1.7]])),
         {'loc':np.array([-.2,.8]),'scale':1.2},np.array([[.3,1.2],[np.nan,.5],[.7,np.nan],[np.nan,np.nan]]),missing_mv,True),
        ('OrderedLogistic',lambda p:velnora.distributions.OrderedLogistic(p['predictor'],p['cutpoints']),
         {'predictor':np.array([-.3,.8,1.2]),'cutpoints':np.array([-1.,.2,1.4])},np.array([0.,1.,3.]),ordered,False),
    ]
    for dimension in (2,3,4):
        direction = np.arange(1.,dimension+1)
        direction /= np.linalg.norm(direction)
        cases.append(('ProjectedNormal',lambda p:velnora.distributions.ProjectedNormal(p['concentration']),
                      {'concentration':np.linspace(-.4,.7,dimension)},direction,
                      lambda p,x:np.log(projected_density(p['concentration'],x)),'sphere'))
    return cases
