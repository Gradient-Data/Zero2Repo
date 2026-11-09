# feature: F09
"""Public variational learning and posterior approximation acceptance tests."""
import math
import numpy as np
import pytest
import torch
from scipy import stats
import velnora
from velnora.infer import SVI, Trace_ELBO, TraceMeanField_ELBO, TraceEnum_ELBO, EnergyDistance
from velnora.infer.autoguide import (
    AutoDelta, AutoNormal, AutoDiagonalNormal, AutoMultivariateNormal,
    AutoLowRankMultivariateNormal, AutoNormalizingFlow, AutoIAFNormal,
    AutoGuideList, AutoStructured, AutoGaussian, AutoDiscreteParallel,
    AutoLaplaceApproximation, init_to_value)
from _helpers import isolated_state, invoke
from F01_helpers import assert_close, finite_difference, assert_frequency, SAMPLE_COUNT
from F09_helpers import normal_problem, normal_objective, fit_svi, energy_oracle, CubicNormal


@pytest.fixture(autouse=True)
def variational_state():
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        with isolated_state(seed=914, dtype=torch.float64, device='cpu'):
            yield
    finally:
        torch.set_num_threads(threads)


def test_f09_t01():
    n = 200000
    parameters = {}
    model, guide = normal_problem(n, parameters)
    loss = Trace_ELBO().differentiable_loss(model, guide) / n
    gradients = torch.autograd.grad(loss, [parameters[k] for k in ('a', 'm', 's')])
    a, m, ls = [torch.tensor(x, requires_grad=True) for x in (-.3, .4, math.log(.8))]
    expected = normal_objective(a, m, ls)
    reference = list(torch.autograd.grad(expected, (a, m, ls)))
    reference[2] = reference[2]/.8
    # Quadratic Gaussian sample averages: these margins exceed ten standard
    # errors for the specified sample count (including the scale derivative).
    assert abs(loss.item()-expected.item()) < .06
    for actual, wanted in zip(gradients, reference):
        assert abs(actual.item()-wanted.item()) < .08


def test_f09_t02():
    n = 200000
    def model():
        logit = velnora.param('prior', torch.tensor(.6))
        with velnora.plate('data', n):
            z = velnora.sample('z', velnora.distributions.Bernoulli(logits=logit))
            velnora.sample('obs', velnora.distributions.Bernoulli(probs=.2+.6*z), obs=torch.tensor(1.))
    def guide():
        logit = velnora.param('guide', torch.tensor(-.4))
        with velnora.plate('data', n):
            velnora.sample('z', velnora.distributions.Bernoulli(logits=logit))
    value = Trace_ELBO().differentiable_loss(model, guide)/n
    leaves = dict(velnora.get_param_store().named_parameters())
    actual = torch.autograd.grad(value, (leaves['prior'], leaves['guide']))
    p, q = [torch.tensor(x, requires_grad=True) for x in (.6, -.4)]
    pp, qq = p.sigmoid(), q.sigmoid()
    expected = (qq*(qq.log()-pp.log()-math.log(.8))
                +(1-qq)*((1-qq).log()-(1-pp).log()-math.log(.2)))
    wanted = torch.autograd.grad(expected, (p, q))
    # Bounded Bernoulli summands, margins > 10 standard errors.
    assert abs(value.item()-expected.item()) < .025
    for x, y in zip(actual, wanted):
        assert abs(x.item()-y.item()) < .025


def test_f09_t03():
    # Deterministic guide makes optimizer participation and returned loss exact.
    def model():
        a = velnora.param('a', torch.tensor(-1.))
        z = velnora.sample('z', velnora.distributions.Normal(a, 1.))
        velnora.sample('obs', velnora.distributions.Normal(z, .5), obs=torch.tensor(2.))
    def guide():
        velnora.sample('z', velnora.distributions.Delta(velnora.param('m', torch.tensor(.2))))
    svi = SVI(model, guide, velnora.optim.SGD({'lr': .02}), Trace_ELBO())
    expected = -stats.norm.logpdf(.2, -1., 1.)-stats.norm.logpdf(2., .2, .5)
    assert abs(svi.evaluate_loss()-expected) < 1e-9
    before = {k: v.detach().clone() for k, v in velnora.get_param_store().items()}
    assert abs(svi.evaluate_loss()-expected) < 1e-9
    for k, v in before.items():
        assert torch.equal(velnora.param(k), v)
    assert abs(svi.step()-expected) < 1e-9
    assert velnora.param('a') > before['a']
    assert velnora.param('m') > before['m']
    assert svi.evaluate_loss() < expected
    # Count is judged by estimation error, not by instrumenting sampler calls.
    # Independent replicated objectives avoid assuming any particular RNG stream.
    errors = []
    for particles in (1, 64):
        with isolated_state(seed=72, dtype=torch.float64):
            model, guide = normal_problem()
            objective = Trace_ELBO(num_particles=particles, vectorize_particles=True,
                                   max_plate_nesting=1)
            draws = np.array([objective.loss(model, guide) for _ in range(800)])
            truth = normal_objective(torch.tensor(-.3), torch.tensor(.4), torch.tensor(math.log(.8))).item()
            errors.append(np.mean((draws-truth)**2))
    # Averaging 64 iid draws reduces MSE by 64; a factor 8 leaves ample reserve.
    assert errors[1] < errors[0]/8


def test_f09_t04():
    def model():
        velnora.sample('z', velnora.distributions.Normal(torch.zeros(3), 1.).to_event(1))
    constructors = [AutoDelta, AutoNormal, AutoDiagonalNormal,
                    AutoMultivariateNormal, AutoLowRankMultivariateNormal,
                    lambda m, **kw: AutoNormalizingFlow(m, lambda dim: velnora.distributions.transforms.TanhTransform()),
                    AutoIAFNormal]
    for constructor in constructors:
        with isolated_state(seed=81, dtype=torch.float64):
            guide = constructor(model)
            guide()
            with velnora.plate('draws', 30000):
                values = guide()['z']
            assert values.shape[-1:] == (3,)
            assert torch.isfinite(values).all()
            if isinstance(guide, AutoDelta):
                assert_close(values, guide.median()['z'].expand_as(values).detach().numpy())
            elif isinstance(guide, AutoNormal):
                z = (values-guide.locs.z)/guide.scales.z
                assert abs(z.mean().item()) < .035
                assert abs(z.square().mean().item()-1) < .05
                assert_close(guide.median()['z'],guide.locs.z.detach().numpy())
                expected=stats.norm.ppf([.1,.5,.9])[:,None]*guide.scales.z.detach().numpy()+guide.locs.z.detach().numpy()
                assert_close(guide.quantiles([.1,.5,.9])['z'],expected)
            else:
                posterior = guide.get_posterior()
                points = posterior.rsample((30000,))
                assert torch.isfinite(posterior.log_prob(points)).all()
                if isinstance(guide, (AutoDiagonalNormal, AutoMultivariateNormal, AutoLowRankMultivariateNormal)):
                    covariance = (torch.diag(posterior.variance) if isinstance(guide, AutoDiagonalNormal)
                                  else posterior.covariance_matrix)
                    white = torch.linalg.solve_triangular(torch.linalg.cholesky(covariance),
                                                          (values-posterior.mean).T, upper=False).T
                    assert abs(white.mean().item()) < .035
                    assert_close(guide.median()['z'], posterior.mean.detach().numpy())
                    expected = stats.norm.ppf([.1,.5,.9])[:,None]*posterior.variance.detach().sqrt().numpy()+posterior.mean.detach().numpy()
                    assert_close(guide.quantiles([.1,.5,.9])['z'], expected)
                    np.testing.assert_allclose((white.T@white/len(white)).detach().numpy(), np.eye(3), atol=.045, rtol=0)
                    test_points = np.array([[.2,-.1,.4],[-.3,.5,-.2]])
                    assert_close(posterior.log_prob(torch.tensor(test_points)), stats.multivariate_normal.logpdf(test_points, posterior.mean.detach().numpy(), covariance.detach().numpy()))
                elif isinstance(guide, AutoNormalizingFlow) and not isinstance(guide, AutoIAFNormal):
                    # Caller-selected tanh transform must change the entire law.
                    assert (values.abs() < 1).all()
                    u = np.arctanh(values.detach().numpy())
                    score = stats.norm.logpdf(u).sum(-1)-np.log1p(-values.detach().numpy()**2).sum(-1)
                    assert_close(posterior.log_prob(values), score)
    covariance = torch.eye(3)*.5 + torch.ones(3,3)*.7
    def correlated_model():
        velnora.sample('z',velnora.distributions.MultivariateNormal(torch.tensor([.4,-.6,.8]),covariance_matrix=covariance))
    for constructor in (AutoMultivariateNormal,AutoLowRankMultivariateNormal,AutoIAFNormal):
        with isolated_state(seed=51,dtype=torch.float64):
            guide=constructor(correlated_model)
            fit_svi(correlated_model,guide,Trace_ELBO(num_particles=128,vectorize_particles=True),steps=800,lr=.02)
            with velnora.plate('draws',30000):
                samples=guide()['z'].detach().numpy()
            np.testing.assert_allclose(samples.mean(0),[.4,-.6,.8],atol=.2,rtol=0)
            np.testing.assert_allclose(np.cov(samples.T),covariance.numpy(),atol=.25,rtol=0)
    def constrained_model():
        velnora.sample('r', velnora.distributions.Normal(0.,1.))
        velnora.sample('p', velnora.distributions.LogNormal(0.,1.))
        velnora.sample('s', velnora.distributions.Dirichlet(torch.ones(3)))
        velnora.sample('u', velnora.distributions.Uniform(-2.,3.))
    for constructor in constructors:
        with isolated_state(seed=38, dtype=torch.float64):
            guide = constructor(constrained_model)
            for _ in range(8):
                values = guide()
                assert values['p'] > 0
                assert (values['s'] > 0).all()
                assert_close(values['s'].sum(), 1.)
                assert -2 < values['u'] < 3
            if isinstance(guide, (AutoNormal, AutoDiagonalNormal, AutoMultivariateNormal, AutoLowRankMultivariateNormal)):
                quantiles = guide.quantiles([.1,.5,.9])
                median = guide.median()
                with velnora.plate('summary_draws',SAMPLE_COUNT):
                    draws=guide()
                for name in ('r','p'):
                    assert_close(quantiles[name][1], median[name].detach().numpy())
                    assert_frequency(draws[name][...,None] < quantiles[name],np.array([.1,.5,.9]))
                    assert (quantiles[name][1:] > quantiles[name][:-1]).all()
                    # Positive-site summaries are lognormal marginals.
                    q = quantiles[name].detach().numpy()
                    if name == 'p':
                        q = np.log(q)
                    assert abs(q[0]+q[2]-2*q[1]) < 1e-8


def test_f09_t05():
    def model():
        x = velnora.sample('x', velnora.distributions.Normal(0.,1.))
        velnora.sample('y', velnora.distributions.Normal(.8*x,.7))
    composite = AutoGuideList(model)
    composite.append(AutoDelta(velnora.poutine.block(model, expose=['x']), init_loc_fn=init_to_value(values={'x':torch.tensor(.7)})))
    def custom():
        return {'y': velnora.sample('y', velnora.distributions.Normal(velnora.param('custom',torch.tensor(-.4)), .8))}
    composite.append(custom)
    values = composite()
    assert set(values) == {'x','y'}
    assert_close(values['x'], .7)
    tr = velnora.poutine.trace(composite).get_trace()
    assert_close(tr.log_prob_sum(), stats.norm.logpdf(tr.nodes['y']['value'].item(),-.4,.8))
    def blocks():
        velnora.sample('x', velnora.distributions.Normal(0.,1.))
        velnora.sample('y', velnora.distributions.Normal(torch.zeros(2),1.).to_event(1))
        velnora.sample('d', velnora.distributions.Normal(0.,1.))
        velnora.sample('c', velnora.distributions.Normal(0.,1.))
    def noise():
        return velnora.sample('custom_noise', velnora.distributions.Normal(torch.zeros(1),.7).to_event(1), infer={'is_auxiliary':True})
    structured = AutoStructured(blocks,
        conditionals={'x':'normal','y':'mvn','d':'delta','c':noise},
        dependencies={'y':{'x':lambda x: 2*x.expand(x.shape[:-1]+(2,))}},
        init_loc_fn=init_to_value(values={'x':torch.tensor(0.),'y':torch.zeros(2),'d':torch.tensor(.3),'c':torch.tensor(0.)}), init_scale=.6)
    structured()
    with velnora.plate('draws',30000):
        tr = velnora.poutine.trace(structured).get_trace()
    v = tr.nodes['_RETURN']['value']
    residual = v['y']-2*v['x'][...,None]
    assert abs(v['x'].square().mean().item()-.36) < .02
    np.testing.assert_allclose((residual.T@residual/30000).detach().numpy(), np.eye(2)*.36, atol=.025,rtol=0)
    assert abs(v['c'].square().mean().item()-.49) < .025
    assert_close(v['d'], np.full(v['d'].shape,.3))
    expected = (stats.norm.logpdf(v['x'].detach().numpy(),0,.6).sum()
                +stats.norm.logpdf(residual.detach().numpy(),0,.6).sum()
                +stats.norm.logpdf(v['c'].detach().numpy(),0,.7).sum())
    assert_close(tr.log_prob_sum(), expected)
    # Learn an analytically correlated joint law; independent normals cannot fit it.
    with isolated_state(seed=18,dtype=torch.float64):
        gaussian = AutoGaussian(model, backend='dense')
        fit_svi(model,gaussian,Trace_ELBO(num_particles=128,vectorize_particles=True),steps=2400,lr=.01)
        with velnora.plate('draws',30000):
            values = gaussian()
        pair = torch.stack([values['x'],values['y']],-1).detach().numpy()
        np.testing.assert_allclose(pair.mean(0),[0.,0.],atol=.18,rtol=0)
        np.testing.assert_allclose(np.cov(pair.T),[[1.,.8],[.8,1.13]],atol=.25,rtol=0)


def test_f09_t06():
    def model():
        velnora.sample('a',velnora.distributions.LogNormal(0.,1.))
        velnora.sample('b',velnora.distributions.Normal(0.,1.))
    for constructor in (AutoDelta,AutoNormal,AutoDiagonalNormal,AutoMultivariateNormal,AutoLowRankMultivariateNormal):
        for index, rule in enumerate((init_to_value(values={'a':torch.tensor(2.4),'b':torch.tensor(-.8)}),
                     lambda site: torch.tensor(1.7 if site['name']=='a' else .6))):
            with isolated_state(dtype=torch.float64):
                guide=constructor(model,init_loc_fn=rule)
                values=guide.median() if isinstance(guide,AutoDelta) else None
                if values is None:
                    guide()
                    values=guide.median()
                expected_a,expected_b=(2.4,-.8) if index == 0 else (1.7,.6)
                assert_close(values['a'],expected_a)
                assert_close(values['b'],expected_b)
        def discrete():
            velnora.sample('z',velnora.distributions.Bernoulli(.4))
        with isolated_state(dtype=torch.float64):
            rejected=invoke(constructor(discrete),allowed_exceptions=(ValueError,))
            assert isinstance(rejected.exception,ValueError)


def test_f09_t07():
    for family in ('Bernoulli','Categorical','OneHotCategorical'):
        with isolated_state(seed=29,dtype=torch.float64):
            def model():
                with velnora.plate('batch',2):
                    probs=torch.tensor([.3,.6]) if family=='Bernoulli' else torch.tensor([[.2,.3,.5],[.5,.3,.2]])
                    z=velnora.sample('z',getattr(velnora.distributions,family)(probs=probs),infer={'enumerate':'parallel'})
                    k=z if family=='Bernoulli' else (z.argmax(-1) if family=='OneHotCategorical' else z)
                    velnora.sample('obs',velnora.distributions.Bernoulli(probs=.15+.3*k),obs=torch.ones(2))
            guide=AutoDiscreteParallel(model)
            guide()
            before=guide.z_probs.detach().clone()
            fit_svi(model,guide,TraceEnum_ELBO(max_plate_nesting=1),steps=240,lr=.05)
            prior=before.numpy()
            likelihood=np.array([.15,.45]) if family=='Bernoulli' else np.array([.15,.45,.75])
            if family=='Bernoulli':
                target=prior*.45/((1-prior)*.15+prior*.45)
            else:
                target=prior*likelihood
                target/=target.sum(-1,keepdims=True)
            np.testing.assert_allclose(guide.z_probs.detach().numpy(),target,atol=.015,rtol=0)
            samples=torch.stack([guide()['z'] for _ in range(10000)])
            if family=='Categorical':
                frequency=torch.nn.functional.one_hot(samples.long(),3).double().mean(0)
            else:
                frequency=samples.mean(0)
            # Sampling law follows this fitted probability, rather than requiring
            # that a finite optimization run reach the exact posterior.
            fitted=guide.z_probs.detach().numpy()
            np.testing.assert_allclose(frequency.numpy(),fitted,atol=.04,rtol=0)
            if family=='Bernoulli':
                indicators=torch.stack([1-samples,samples],-1)
                probabilities=np.stack([1-fitted,fitted],-1)
            elif family=='Categorical':
                indicators=torch.nn.functional.one_hot(samples.long(),3).double()
                probabilities=fitted
            else:
                indicators=samples
                probabilities=fitted
            joint=(indicators[:,0,:,None]*indicators[:,1,None,:]).mean(0)
            np.testing.assert_allclose(joint.numpy(),probabilities[0,:,None]*probabilities[1,None,:],atol=.04,rtol=0)
            # Hoeffding at n=10000 and margin .04 gives < 3e-14 per
            # marginal/joint indicator, with fewer than forty indicators.

    def unsupported():
        velnora.sample('z',velnora.distributions.Binomial(3,.4),infer={'enumerate':'parallel'})
    def sequential():
        for i in velnora.plate('items',2):
            velnora.sample('z'+str(i),velnora.distributions.Bernoulli(.4),infer={'enumerate':'parallel'})
    for model in (unsupported,sequential):
        result=invoke(AutoDiscreteParallel(model),allowed_exceptions=(NotImplementedError,))
        assert isinstance(result.exception,NotImplementedError)


def test_f09_t08():
    def model():
        velnora.sample('z',velnora.distributions.Normal(torch.zeros(2),1.).to_event(1))
    def guide():
        velnora.sample('z',velnora.distributions.Normal(torch.ones(2),1.).to_event(1))
    assert math.isfinite(Trace_ELBO().loss(model,guide))
    def wrong_event():
        with velnora.plate('batch',2):
            velnora.sample('z',velnora.distributions.Normal(torch.zeros(2),1.))
    def wrong_shape():
        velnora.sample('z',velnora.distributions.Normal(torch.zeros(3),1.).to_event(1))
    for bad in (wrong_event,wrong_shape):
        result=invoke(Trace_ELBO().loss,model,bad,allowed_exceptions=(ValueError,))
        assert isinstance(result.exception,ValueError)
    def factor_guide(declared):
        guide()
        if declared:
            velnora.factor('factor',torch.tensor(.7),has_rsample=True)
        else:
            velnora.factor('factor',torch.tensor(.7))
    value=Trace_ELBO().loss(model,lambda:factor_guide(True))
    assert math.isfinite(value)
    refused=invoke(Trace_ELBO().loss,model,lambda:factor_guide(False),allowed_exceptions=(ValueError,))
    assert isinstance(refused.exception,ValueError)


def test_f09_t09():
    n=200000
    parameters = {}
    def model():
        with velnora.plate('data',n):
            velnora.sample('z',velnora.distributions.Normal(-.3,1.3))
    def guide():
        m=velnora.param('m',torch.tensor(.4))
        s=velnora.param('s',torch.tensor(.8),constraint=velnora.distributions.constraints.positive)
        parameters.update(m=m, s=s)
        with velnora.plate('data',n):
            velnora.sample('z',velnora.distributions.Normal(m,s))
    value=TraceMeanField_ELBO().differentiable_loss(model,guide)/n
    expected=math.log(1.3/.8)+(.8**2+.7**2)/(2*1.3**2)-.5
    # Accept analytic integration and unbiased Monte Carlo alike, with margins
    # exceeding ten standard errors of these Gaussian score averages.
    assert abs(value.item()-expected)<.03
    gradients=torch.autograd.grad(value,(parameters['m'],parameters['s']))
    assert abs(gradients[0].item()-.7/1.3**2)<.04
    assert abs(gradients[1].item()-(.8/1.3**2-1/.8))<.05
    with isolated_state(dtype=torch.float64):
        def positive():
            velnora.sample('z',velnora.distributions.Gamma(3.,2.))
        point=AutoDelta(positive,init_loc_fn=init_to_value(values={'z':torch.tensor(3.)}))
        fit_svi(positive,point,Trace_ELBO(),steps=350)
        # Gamma mode in original coordinates is (shape-1)/rate; optimizing
        # transformed density would incorrectly give shape/rate instead.
        assert abs(point.median()['z'].item()-1.)<.015


def test_f09_t10():
    captured={}
    theta=velnora.param('theta',torch.tensor(.3))
    def guide():
        z=velnora.sample('z',velnora.distributions.Normal(theta,.8))
        captured.setdefault('z',[]).append(z)
    def model():
        z=velnora.sample('z',velnora.distributions.Normal(-.2,1.4))
        with velnora.plate('batch',3,dim=-1):
            with velnora.poutine.mask(mask=torch.tensor([True,False,True])), velnora.poutine.scale(scale=torch.tensor([.5,2.,1.7])):
                a=velnora.sample('a',velnora.distributions.Normal(z+torch.tensor([-.2,.4,.8]),.6),obs=torch.tensor([.1,8.,-.7]))
            b=velnora.sample('b',velnora.distributions.Normal(2*z+torch.tensor([.3,-.5,.2]),.4),obs=torch.tensor([.8,-.3,.4]))
        captured.setdefault('samples',[]).append(torch.cat([a,b],-1))
    data=np.array([.1,8.,-.7,.8,-.3,.4])
    weights=np.array([.5,0.,1.7,1.,1.,1.])
    for beta,weight,n in ((1.,0.,2),(.7,.23,5),(1.6,.11,4)):
        captured.clear()
        value=EnergyDistance(beta=beta,prior_scale=weight,num_particles=n,max_plate_nesting=2)(model,guide)
        # Draws observed across every model and guide execution, batched or not.
        samples=torch.cat([s.detach().reshape(-1,6) for s in captured['samples']]).numpy()
        latent=torch.cat([z.detach().reshape(-1) for z in captured['z']]).numpy()
        assert samples.shape==(n,6) and latent.shape==(n,), (samples.shape,latent.shape)
        expected=energy_oracle(samples,data,weights,beta,latent,weight)
        assert_close(value,expected)
        actual=torch.autograd.grad(value,theta)[0]
        # Independent oracle differentiated under a location perturbation;
        # common random draws are observed from this actual model execution.
        direction=np.array([1.,1.,1.,2.,2.,2.])
        wanted=finite_difference(lambda shift:energy_oracle(samples+shift*direction,data,weights,beta,latent+shift,weight),0.)
        assert_close(actual,wanted)


def test_f09_t11():
    captured={}
    def guide():
        z=velnora.sample('z',CubicNormal(velnora.param('center',torch.tensor(-.7))))
        captured.setdefault('z',[]).append(z)
    def model():
        z=velnora.sample('z',CubicNormal(torch.tensor(0.)))
        y=velnora.sample('obs',CubicNormal(z*.1),obs=torch.tensor(2.))
        captured.setdefault('y',[]).append(y)
    objective=EnergyDistance(max_plate_nesting=1)
    value=objective(model,guide)
    # Draws observed across every model execution, batched or not.
    drawn=torch.cat([y.detach().reshape(-1) for y in captured['y']])
    assert drawn.shape == (2,), drawn.shape
    expected=energy_oracle(drawn.numpy()[:,None],np.array([2.]),np.ones(1),1.)
    assert_close(value,expected)
    assert value.requires_grad
    assert torch.isfinite(torch.autograd.grad(value,velnora.param('center'))[0])
    # Actual density-free training: a deterministic differentiable guide and
    # implicit observation law learn its translation from observed data.
    with isolated_state(seed=37,dtype=torch.float64):
        def location_guide():
            velnora.sample('z',velnora.distributions.Delta(velnora.param('loc',torch.tensor(-3.))))
        def location_model():
            z=velnora.sample('z',CubicNormal(torch.tensor(0.)))
            velnora.sample('obs',velnora.distributions.TransformedDistribution(CubicNormal(torch.tensor(0.)),velnora.distributions.transforms.AffineTransform(z, .05)),obs=torch.tensor(1.5))
        fit_svi(location_model,location_guide,EnergyDistance(num_particles=64,max_plate_nesting=1),steps=250,lr=.04)
        assert abs(velnora.param('loc').item()-1.5)<.15
    for kwargs in ({'beta':0.},{'beta':2.},{'beta':-.1},{'prior_scale':-.01},{'num_particles':1}):
        result=invoke(EnergyDistance,kwargs=kwargs,allowed_exceptions=(ValueError,))
        assert isinstance(result.exception,ValueError)
    def empty():
        velnora.sample('z',velnora.distributions.Normal(0.,1.))
    result=invoke(objective,empty,lambda:velnora.sample('z',velnora.distributions.Normal(0.,1.)),allowed_exceptions=(ValueError,))
    assert isinstance(result.exception,ValueError)
    def discrete_guide():
        velnora.sample('z',velnora.distributions.Bernoulli(.4))
    def discrete_model():
        z=velnora.sample('z',velnora.distributions.Bernoulli(.4))
        velnora.sample('obs',velnora.distributions.Normal(z,1.),obs=torch.tensor(1.))
    result=invoke(objective,discrete_model,discrete_guide,allowed_exceptions=(ValueError,))
    assert isinstance(result.exception,ValueError)


def test_f09_t12():
    covariance=torch.tensor([[1.3,.65],[.65,.9]])
    center=torch.tensor([.7,-1.1])
    def model():
        velnora.sample('z',velnora.distributions.MultivariateNormal(center,covariance_matrix=covariance))
    guide=AutoLaplaceApproximation(model,init_loc_fn=init_to_value(values={'z':torch.tensor([-2.,2.])}))
    fit_svi(model,guide,Trace_ELBO(),steps=450,lr=.05)
    learned=guide()['z'].detach()
    np.testing.assert_allclose(learned.numpy(),center.numpy(),atol=.015,rtol=0)
    posterior=guide.laplace_approximation().get_posterior()
    assert_close(posterior.mean,learned.numpy())
    assert_close(posterior.covariance_matrix,covariance.numpy())
    points=torch.tensor([[.2,-.8],[1.4,.1]])
    assert_close(posterior.log_prob(points),stats.multivariate_normal.logpdf(points.numpy(),learned.numpy(),covariance.numpy()))
