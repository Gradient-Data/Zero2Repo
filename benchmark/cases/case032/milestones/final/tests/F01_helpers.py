# feature: F01
"""Independent probability-law oracles and public distribution fixtures."""
import os
from dataclasses import dataclass

from _helpers import configure_cpu_environment, read_array, call_public

os.environ.update(configure_cpu_environment())
import jax
import jax.numpy as jnp
import numpy as np
from scipy import stats, special, integrate, linalg
import velnora.distributions as dist

# FP-01.18 specifies the observable error range for interior, well-conditioned
# numerical evaluations in double precision.
RTOL = 2e-5
ATOL = 2e-6
N = 8192
# DKW: P(sup |F_n-F| > eps) <= 2 exp(-2 n eps^2) = 1e-12.
# The suite uses fewer than 2000 such comparisons, giving union risk < 2e-9.
ALPHA = 1e-12


def close(actual, expected):
    np.testing.assert_allclose(read_array(actual), expected, rtol=RTOL, atol=ATOL)


def check_moments(law, mean, variance):
    """Compare moments after their documented broadcasting to batch and event axes."""
    shape = law.batch_shape + law.event_shape
    for actual, expected in [(law.mean, mean), (law.variance, variance)]:
        close(np.broadcast_to(read_array(actual), shape),
              np.broadcast_to(expected, shape))


def draws(law, seed=2027, n=N):
    return read_array(call_public(law.sample, jax.random.key(seed), (n,), timeout=240))


def check_cdf_samples(samples, cdf):
    x = np.sort(np.asarray(samples), axis=0)
    assert x.ndim == 1 and np.isfinite(x).all()
    p = cdf(x)
    n = len(x)
    error = max(np.max(np.arange(1, n + 1) / n - p),
                np.max(p - np.arange(n) / n))
    assert error < np.sqrt(np.log(2 / ALPHA) / (2 * n)), error


def frequency(indicator, probability):
    indicator = np.asarray(indicator)
    error = abs(indicator.mean(axis=0) - probability)
    assert np.all(error < np.sqrt(np.log(2 / ALPHA) / (2 * len(indicator)))), error


def gaussian_samples(samples, mean, cov):
    x = np.asarray(samples)
    z = linalg.solve_triangular(np.linalg.cholesky(cov), (x - mean).T, lower=True).T
    for direction in [*np.eye(z.shape[-1]), np.ones(z.shape[-1]) / np.sqrt(z.shape[-1])]:
        check_cdf_samples(z @ direction, stats.norm.cdf)
    check_cdf_samples(np.sum(z*z, axis=-1), stats.chi2(z.shape[-1]).cdf)


@dataclass
class ScalarLaw:
    law: object
    oracle: object
    label: str


def scalar_laws(defaults=False):
    """All enumerated scalar families, including both beta/AL parameterizations."""
    loc, scale = (0., 1.) if defaults else (.4, 1.3)
    ls = {} if defaults else dict(loc=loc, scale=scale)
    ss = {} if defaults else dict(scale=scale)
    rows = [
        (dist.Normal(**ls), stats.norm(loc, scale), 'Normal'),
        (dist.Cauchy(**ls), stats.cauchy(loc, scale), 'Cauchy'),
        (dist.HalfNormal(**ss), stats.halfnorm(scale=scale), 'HalfNormal'),
        (dist.HalfCauchy(**ss), stats.halfcauchy(scale=scale), 'HalfCauchy'),
        (dist.StudentT(7., **ls), stats.t(7, loc, scale), 'StudentT'),
        (dist.Laplace(**ls), stats.laplace(loc, scale), 'Laplace'),
        (dist.AsymmetricLaplace(asymmetry=1.7, **ls), stats.laplace_asymmetric(1.7, loc, scale), 'AsymmetricLaplace'),
        (dist.AsymmetricLaplaceQuantile(quantile=.3, **ls), stats.laplace_asymmetric(np.sqrt(.3/.7), loc, scale/np.sqrt(.3*.7)), 'AsymmetricLaplaceQuantile'),
        (dist.SoftLaplace(loc, scale), stats.hypsecant(loc, scale), 'SoftLaplace'),
        (dist.Logistic(**ls), stats.logistic(loc, scale), 'Logistic'),
        (dist.Uniform() if defaults else dist.Uniform(-.8, 2.3), stats.uniform(0,1) if defaults else stats.uniform(-.8,3.1), 'Uniform'),
        (dist.LogUniform(.3, 4.2), stats.loguniform(.3,4.2), 'LogUniform'),
        (dist.LogNormal(**ls), stats.lognorm(scale, scale=np.exp(loc)), 'LogNormal'),
        (dist.Exponential(1.7), stats.expon(scale=1/1.7), 'Exponential'),
        (dist.Gamma(3.4,1.7), stats.gamma(3.4,scale=1/1.7), 'Gamma'),
        (dist.InverseGamma(5.4,1.7), stats.invgamma(5.4,scale=1.7), 'InverseGamma'),
        (dist.Chi2(6.2), stats.chi2(6.2), 'Chi2'),
        (dist.Beta(2.3,4.1), stats.beta(2.3,4.1), 'Beta'),
        (dist.BetaProportion(.3,7.), stats.beta(2.1,4.9), 'BetaProportion'),
        (dist.Kumaraswamy(2.3,3.1), stats.rv_continuous, 'Kumaraswamy'),
        (dist.Pareto(1.3,5.2), stats.pareto(5.2,scale=1.3), 'Pareto'),
        (dist.Weibull(1.3,2.4), stats.weibull_min(2.4,scale=1.3), 'Weibull'),
        (dist.Gumbel(**ls), stats.gumbel_r(loc,scale), 'Gumbel'),
        (dist.Gompertz(1.3,1.7), stats.gompertz(1.3,scale=1/1.7), 'Gompertz'),
        (dist.Levy(loc,scale), stats.levy(loc,scale), 'Levy'),
        (dist.Dagum(2.3,5.4,1.7), stats.burr(5.4,2.3,scale=1.7), 'Dagum'),
    ]
    class Kumar(stats.rv_continuous):
        def _cdf(self,x): return 1-(1-x**2.3)**3.1
        def _pdf(self,x): return 2.3*3.1*x**1.3*(1-x**2.3)**2.1
        def _ppf(self,q): return (1-(1-q)**(1/3.1))**(1/2.3)
    rows[19] = (rows[19][0], Kumar(a=0,b=1), rows[19][2])
    return [ScalarLaw(*r) for r in rows]


@dataclass
class CountLaw:
    law: object
    outcomes: np.ndarray
    probabilities: np.ndarray
    oracle: object = None
    kind: str = ""


def count_laws():
    """Masses from independent finite laws and integrated mixing distributions."""
    p, n = .27, 5
    logits = np.log(p/(1-p))
    probs = np.array([.17,.32,.51])
    weights = np.log(probs)+1.4
    rows = []
    for kwargs in [dict(probs=p),dict(logits=logits)]:
        rows.append((dist.Bernoulli(**kwargs),np.arange(2),stats.bernoulli(p),"Bernoulli"))
        rows.append((dist.Binomial(n,**kwargs),np.arange(n+1),stats.binom(n,p),"Binomial"))
        rows.append((dist.Geometric(**kwargs),np.arange(12),stats.geom(p,loc=-1),"Geometric"))
        rows.append((dist.NegativeBinomial(2.4,**kwargs),np.arange(18),stats.nbinom(2.4,1-p),"NegativeBinomial"))
    for kwargs in [dict(probs=jnp.array(probs)),dict(logits=jnp.array(weights))]:
        rows.append((dist.Categorical(**kwargs),np.arange(3),stats.rv_discrete(values=(np.arange(3),probs)),"Categorical"))
        outcomes=np.array([[i,j,n-i-j] for i in range(n+1) for j in range(n+1-i)])
        rows.append((dist.Multinomial(n,**kwargs),outcomes,stats.multinomial(n,probs),"Multinomial"))
    rows += [
        (dist.Poisson(2.7),np.arange(15),stats.poisson(2.7),"Poisson"),
        (dist.DiscreteUniform(-2,3),np.arange(-2,4),stats.randint(-2,4),"DiscreteUniform"),
        (dist.BetaBinomial(2.3,4.7,n),np.arange(n+1),stats.betabinom(n,2.3,4.7),"BetaBinomial"),
        (dist.NegativeBinomial2(3.2,2.4),np.arange(20),stats.nbinom(2.4,2.4/(2.4+3.2)),"NegativeBinomial2"),
        (dist.GammaPoisson(2.4,1.6),np.arange(18),stats.nbinom(2.4,1.6/2.6),"GammaPoisson"),
    ]
    result = [CountLaw(law,x,np.exp(o.logpmf(x)),o,kind) for law,x,o,kind in rows]
    x=np.arange(35)
    # NB counts use a success-count probability p, hence scipy's 1-p.
    masses=np.array([integrate.quad(lambda p: stats.nbinom.pmf(k,2.4,1-p)*stats.beta.pdf(p,2.3,5.7),0,1,epsabs=1e-12)[0] for k in x])
    result.append(CountLaw(dist.BetaNegativeBinomial(2.3,5.7,2.4),x,masses,kind="BetaNegativeBinomial"))
    a=np.array([1.3,2.4,3.7])
    x=np.array([[i,j,n-i-j] for i in range(n+1) for j in range(n+1-i)])
    result.append(CountLaw(dist.DirichletMultinomial(jnp.array(a),n),x,np.exp(stats.dirichlet_multinomial.logpmf(x,a,n)),kind="DirichletMultinomial"))
    cuts=np.array([-.9,.4,1.7]); predictor=.3
    masses=np.diff(np.r_[0,special.expit(cuts-predictor),1])
    result.append(CountLaw(dist.OrderedLogistic(predictor,jnp.array(cuts)),np.arange(4),masses,kind="OrderedLogistic"))
    return result


MEAN = np.array([.4,-.7])
COV = np.array([[1.4,.35],[.35,.8]])
FACTOR = np.linalg.cholesky(COV)
ADJ = np.array([[0.,1.,.5],[1.,0.,.7],[.5,.7,0.]])
CAR_COV = np.linalg.inv(1.6*(np.diag(ADJ.sum(-1))-.4*ADJ))


def vector_laws():
    """Return public laws and caller-owned oracle metadata, including family labels."""
    rows=[]
    for kwargs in [dict(covariance_matrix=jnp.array(COV)),dict(precision_matrix=jnp.array(np.linalg.inv(COV))),dict(scale_tril=jnp.array(FACTOR))]:
        rows.append((dist.MultivariateNormal(jnp.array(MEAN),**kwargs),stats.multivariate_normal(MEAN,COV).logpdf,MEAN,COV,"normal"))
    f=np.array([[.4],[.7]]); diagonal=np.array([.8,1.2]); cov=f@f.T+np.diag(diagonal)
    rows.append((dist.LowRankMultivariateNormal(jnp.array(MEAN),jnp.array(f),jnp.array(diagonal)),stats.multivariate_normal(MEAN,cov).logpdf,MEAN,cov,"normal"))
    rows.append((dist.MultivariateStudentT(7.,jnp.array(MEAN),jnp.array(FACTOR)),stats.multivariate_t(MEAN,COV,7).logpdf,MEAN,7/5*COV,"student"))
    rows.append((dist.CAR(jnp.array([.3,-.5,.7]),.4,1.6,jnp.array(ADJ)),stats.multivariate_normal([.3,-.5,.7],CAR_COV).logpdf,np.array([.3,-.5,.7]),CAR_COV,"car"))
    return rows


def lkj_density(matrix, eta):
    """LKJ density for a 3x3 correlation matrix, normalized by beta integrals."""
    # Integral over the three independent off-diagonal coordinates is
    # B(1/2,eta+1/2)^2 B(1/2,eta).
    return ((eta-1)*np.linalg.slogdet(matrix)[1]
            -2*special.betaln(.5,eta+.5)-special.betaln(.5,eta))


def cholesky_jacobian(factor):
    d=factor.shape[-1]
    return d*np.log(2)+np.sum(np.arange(d,0,-1)*np.log(np.diagonal(factor,axis1=-2,axis2=-1)),axis=-1)


def matrix_laws():
    rows=[]
    for cls,oracle,is_factor,is_inverse in [
        (dist.Wishart,stats.wishart,False,False),
        (dist.InverseWishart,stats.invwishart,False,True),
        (dist.WishartCholesky,stats.wishart,True,False),
        (dist.InverseWishartCholesky,stats.invwishart,True,True)]:
        for kwargs in [dict(scale_matrix=jnp.array(COV)),dict(rate_matrix=jnp.array(np.linalg.inv(COV))),dict(scale_tril=jnp.array(FACTOR))]:
            rows.append((cls(8.,**kwargs),oracle(8,COV),is_factor,is_inverse))
    return rows


def validation_specs():
    """Valid constructor arguments and independently specified forbidden domains."""
    specs=[]
    for cls in [dist.Normal,dist.Cauchy,dist.HalfNormal,dist.HalfCauchy,dist.Laplace,dist.Logistic,dist.LogNormal,dist.Gumbel]:
        specs.append((cls,dict(scale=1.3),{'scale':[0.,-.2]}))
    specs += [
        (dist.StudentT,dict(df=5.,loc=.2,scale=1.3),{'df':[0.,-.2],'scale':[0.,-.2]}),
        (dist.AsymmetricLaplace,dict(loc=.2,scale=1.3,asymmetry=1.4),{'scale':[0.,-.2],'asymmetry':[0.,-.2]}),
        (dist.AsymmetricLaplaceQuantile,dict(loc=.2,scale=1.3,quantile=.3),{'scale':[0.,-.2],'quantile':[0.,1.,-.2,1.2]}),
        (dist.SoftLaplace,dict(loc=.2,scale=1.3),{'scale':[0.,-.2]}),
        (dist.Exponential,dict(rate=1.3),{'rate':[0.,-.2]}),
        (dist.Chi2,dict(df=5.),{'df':[0.,-.2]}),
        (dist.Pareto,dict(scale=1.3,alpha=4.2),{'scale':[0.,-.2],'alpha':[0.,-.2]}),
        (dist.Weibull,dict(scale=1.3,concentration=2.4),{'scale':[0.,-.2],'concentration':[0.,-.2]}),
        (dist.Levy,dict(loc=.2,scale=1.3),{'scale':[0.,-.2]}),
        (dist.Dagum,dict(concentration=2.3,sharpness=5.4,scale=1.7),{'concentration':[0.,-.2],'sharpness':[0.,-.2],'scale':[0.,-.2]}),
        (dist.BetaProportion,dict(mean=.3,concentration=7.),{'mean':[-.2,1.2],'concentration':[0.,-.2]}),
        (dist.VonMises,dict(loc=.2,concentration=1.3),{'concentration':[0.,-.2]}),
        (dist.RelaxedBernoulli,dict(temperature=.7,probs=.3),{'temperature':[0.,-.2]}),
        (dist.SineBivariateVonMises,dict(phi_loc=.2,psi_loc=-.3,phi_concentration=1.3,psi_concentration=1.7,correlation=.3),{'phi_concentration':[0.,-.2],'psi_concentration':[0.,-.2]}),
    ]
    for cls in [dist.Gamma,dist.InverseGamma,dist.Gompertz,dist.GammaPoisson]:
        specs.append((cls,dict(concentration=3.4,rate=1.7),{'concentration':[0.,-.2],'rate':[0.,-.2]}))
    for cls in [dist.Beta,dist.Kumaraswamy,dist.BetaBinomial]:
        specs.append((cls,dict(concentration1=2.3,concentration0=4.7),{'concentration1':[0.,-.2],'concentration0':[0.,-.2]}))
    specs.append((dist.BetaBinomial,dict(concentration1=2.3,concentration0=4.7,total_count=5),{'total_count':[-1,1.5]}))
    specs.append((dist.BetaNegativeBinomial,dict(concentration1=2.3,concentration0=4.7,n=2.4),{'concentration1':[0.,-.2],'concentration0':[0.,-.2],'n':[0.,-.2]}))
    for cls in [dist.Bernoulli,dist.Binomial,dist.Geometric,dist.NegativeBinomial]:
        kw={} if cls in [dist.Bernoulli,dist.Geometric] else dict(total_count=3)
        kw['probs']=.3
        bad=[-.2,1.2]+([1.] if cls is dist.NegativeBinomial else [])
        invalid={'probs':bad}
        if cls is dist.Binomial:invalid['total_count']=[-1,1.5]
        if cls is dist.NegativeBinomial:invalid['total_count']=[0.,-.2]
        specs.append((cls,kw,invalid))
    specs += [
        (dist.Poisson,dict(rate=1.3),{'rate':[-.2]}),
        (dist.NegativeBinomial2,dict(mean=2.3,concentration=1.7),{'mean':[-.2],'concentration':[0.,-.2]}),
        (dist.Categorical,dict(probs=jnp.array([.2,.3,.5])),{'probs':[jnp.array([.2,.3,.2]),jnp.array([-.2,.7,.5])]}),
        (dist.Categorical,dict(logits=jnp.array([-.2,-np.inf,.5])),{'logits':[jnp.array([-np.inf,-np.inf]),jnp.array([0.,np.inf]),jnp.array([0.,np.nan])]}),
        (dist.Multinomial,dict(total_count=5,probs=jnp.array([.2,.3,.5])),{'total_count':[-1,1.5],'probs':[jnp.array([.2,.3,.2])]}),
        (dist.DirichletMultinomial,dict(total_count=5,concentration=jnp.array([1.3,2.4,3.7])),{'total_count':[-1,1.5],'concentration':[jnp.array([1.,0.,2.])]}),
        (dist.Dirichlet,dict(concentration=jnp.array([1.3,2.4,3.7])),{'concentration':[jnp.array([1.,0.,2.])]}),
        (dist.OrderedLogistic,dict(predictor=.3,cutpoints=jnp.array([-.4,.5,1.2])),{'cutpoints':[jnp.array([-.4,-.4,1.2]),jnp.array([.5,-.4,1.2])]}),
        (dist.ZeroSumNormal,dict(scale=1.3,event_shape=(3,)),{'scale':[0.,-.2]}),
        (dist.GaussianRandomWalk,dict(scale=1.3,num_steps=4),{'scale':[0.,-.2]}),
        (dist.CAR,dict(loc=jnp.zeros(3),correlation=.4,conditional_precision=1.6,adj_matrix=jnp.array(ADJ)),{'correlation':[-1.,1.],'conditional_precision':[0.,-.2]}),
    ]
    for cls in [dist.LKJ,dist.LKJCholesky]:
        specs.append((cls,dict(dimension=3,concentration=1.7),{'concentration':[0.,-.2]}))
    return specs
