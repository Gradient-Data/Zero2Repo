# feature: F01
"""Acceptance checks for probability laws, tensor events and differentiation."""
import velnora
import numpy as np
import pytest
import torch
from scipy import special, stats
from _helpers import isolated_state, invoke
from F01_helpers import SAMPLE_COUNT, assert_close, assert_frequency, projected_density


@pytest.fixture(autouse=True)
def distribution_state():
    with isolated_state(seed=20261029, validation=True, dtype=torch.float64, device='cpu'):
        yield


def test_f01_t05():
    events = torch.tensor([[-3., 2.], [1., 7.], [5., -1.]])
    weights = torch.tensor([0.15, 0.25, 0.60])
    empirical = velnora.distributions.Empirical(events, weights.log())
    mean = np.array([2.8, 1.45])
    assert_close(empirical.mean, mean)
    expected_variance = (weights.numpy()[:, None] * (events.numpy() - mean) ** 2).sum(0)
    assert_close(empirical.variance, expected_variance)
    draws = empirical.sample((SAMPLE_COUNT,))
    assert draws.shape == (SAMPLE_COUNT, 2)
    membership = (draws[:, None, :] == events).all(-1)
    assert membership.any(-1).all()
    assert_frequency(membership, weights.numpy())
    for dtype in (torch.int32, torch.int64):
        integer = velnora.distributions.Empirical(events.to(dtype), weights.log())
        for attribute in ('mean', 'variance'):
            result = invoke(getattr, integer, attribute, allowed_exceptions=(ValueError,))
            assert isinstance(result.exception, ValueError)


def test_f01_t07():
    location = torch.tensor([[-1.], [2.]])
    scale = torch.tensor([0.5, 1.5, 2.5])
    law = velnora.distributions.Normal(location, scale)
    assert law.batch_shape == (2, 3)
    assert law.event_shape == ()
    expanded = law.expand((4, 2, 3))
    samples = expanded.sample((5, 7))
    assert samples.shape == (5, 7, 4, 2, 3)
    value = torch.tensor([[0., 1., -2.], [3., 0., 4.]])
    expected = stats.norm.logpdf(value.numpy(), location.numpy(), scale.numpy())
    assert_close(law.log_prob(value), expected)
    assert_close(expanded.log_prob(value), np.broadcast_to(expected, (4, 2, 3)))
    joint = expanded.to_event(2)
    assert joint.batch_shape == (4,)
    assert joint.event_shape == (2, 3)
    assert joint.sample((5, 7)).shape == (5, 7, 4, 2, 3)
    assert_close(joint.log_prob(value), np.full(4, expected.sum()))
    # Score checks cannot establish that expansion also preserves sampling laws.
    draws = expanded.sample((SAMPLE_COUNT,))
    assert_frequency(draws <= location, np.full((4, 2, 3), 0.5))
    assert_frequency(draws <= location + scale, np.full((4, 2, 3), stats.norm.cdf(1)))


def test_f01_t08():
    law = velnora.distributions.Normal(torch.tensor([-1., 2., 4.]), torch.tensor([0.7, 1.2, 2.]))
    value = torch.tensor([0., 1., 6.])
    expected = stats.norm.logpdf(value.numpy(), [-1., 2., 4.], [0.7, 1.2, 2.])
    assert_close(law.log_prob(value), expected)
    for mask in (True, False, torch.tensor([True, False, True])):
        assert_close(law.mask(mask).log_prob(value), np.where(mask, expected, 0.))
    # Complete exclusion also tolerates observations outside the base support.
    positive = velnora.distributions.Exponential(torch.tensor([1., 2.]))
    assert_close(positive.log_prob(torch.tensor([0.5, 1.])), [-0.5, np.log(2)-2])
    assert_close(positive.mask(False).log_prob(torch.tensor([-1., -2.])), [0., 0.])


def test_f01_t09():
    scalar = velnora.distributions.NanMaskedNormal(torch.tensor([1., -2., 3.]), torch.tensor([0.7, 2., 1.]))
    assert_close(scalar.log_prob(torch.tensor([2., float('nan'), 4.])),
                 [stats.norm.logpdf(2, 1, .7), 0., stats.norm.logpdf(4, 3, 1)])
    location = np.array([1., -2., .5])
    covariance = np.array([[2., .6, -.4], [.6, 1.5, .3], [-.4, .3, 1.]])
    law = velnora.distributions.NanMaskedMultivariateNormal(torch.tensor(location), torch.tensor(covariance))
    values = np.array([[.2, -1., 2.], [.2, np.nan, 2.], [np.nan, -1., np.nan],
                       [np.nan, np.nan, np.nan]])
    expected = []
    for value in values:
        observed = ~np.isnan(value)
        expected.append(stats.multivariate_normal.logpdf(
            value[observed], location[observed], covariance[np.ix_(observed, observed)])
            if observed.any() else 0.)
    assert_close(law.log_prob(torch.tensor(values)), expected)
    assert_close(scalar.log_prob(torch.full((3,), float('nan'))), np.zeros(3))


def test_f01_t10():
    valid = velnora.distributions.Normal(torch.tensor([0., 1.]), torch.tensor([1., 2.]), validate_args=True)
    assert torch.isfinite(valid.log_prob(valid.sample((3,)))).all()
    for make in (lambda: velnora.distributions.Normal(0., -1., validate_args=True),
                 lambda: velnora.distributions.Beta(0., 2., validate_args=True),
                 lambda: velnora.distributions.Poisson(-1., validate_args=True)):
        result = invoke(make, allowed_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
    for law, valid_value, invalid_value in (
        (velnora.distributions.Beta(2., 3., validate_args=True), .4, -0.1),
        (velnora.distributions.Poisson(2., validate_args=True), 2., 1.5),
        (velnora.distributions.Categorical(probs=torch.tensor([.2, .8]), validate_args=True), 1., 2.)):
        assert torch.isfinite(law.log_prob(torch.tensor(valid_value)))
        result = invoke(law.log_prob, torch.tensor(invalid_value), allowed_exceptions=(ValueError,))
        assert isinstance(result.exception, ValueError)
    result = invoke(valid.log_prob, torch.ones(3), allowed_exceptions=(ValueError,))
    assert isinstance(result.exception, ValueError)
    multivariate = velnora.distributions.MultivariateNormal(torch.zeros(2), torch.eye(2), validate_args=True)
    assert torch.isfinite(multivariate.log_prob(torch.zeros(2)))
    result = invoke(multivariate.log_prob, torch.ones(3), allowed_exceptions=(ValueError,))
    assert isinstance(result.exception, ValueError)


def test_f01_t12():
    cutpoints = torch.tensor([-1.2, .3, 1.7])
    predictors = torch.tensor([-1., .4, 2.])
    law = velnora.distributions.OrderedLogistic(predictors, cutpoints)
    cumulative = special.expit(cutpoints.numpy() - predictors.numpy()[:, None])
    probabilities = np.diff(np.concatenate([np.zeros((3, 1)), cumulative, np.ones((3, 1))], -1), axis=-1)
    for category in range(4):
        assert_close(law.log_prob(torch.full((3,), category)), np.log(probabilities[:, category]))
    draws = law.sample((SAMPLE_COUNT,))
    assert draws.shape == (SAMPLE_COUNT, 3)
    assert ((0 <= draws) & (draws < 4)).all()
    for category in range(4):
        assert_frequency(draws == category, probabilities[:, category])


def test_f01_t13():
    for dimension in (2, 3, 4, 5):
        location = torch.linspace(-.6, 1.1, dimension)
        law = velnora.distributions.ProjectedNormal(location)
        draws = law.sample((SAMPLE_COUNT,))
        assert draws.shape == (SAMPLE_COUNT, dimension)
        assert_close(draws.norm(dim=-1), np.ones(SAMPLE_COUNT))
        assert_frequency(draws > 0, stats.norm.cdf(location.numpy()))
        assert_frequency((draws[:, 0] > 0) & (draws[:, -1] > 0),
                         stats.norm.cdf(location[0]) * stats.norm.cdf(location[-1]))
        directions = torch.stack([torch.ones(dimension), torch.arange(1., dimension+1)])
        directions = directions / directions.norm(dim=-1, keepdim=True)
        if dimension <= 4:
            expected = [np.log(projected_density(location.numpy(), direction.numpy()))
                        for direction in directions]
            assert_close(law.log_prob(directions), expected)
        else:
            result = invoke(law.log_prob, directions, allowed_exceptions=(NotImplementedError,))
            assert isinstance(result.exception, NotImplementedError)


def test_f01_t01():
    from F01_helpers import scalar_cases, make_scalar
    for case in scalar_cases(include_variations=True):
        name, _, parameters, values, oracle, _, _ = case
        law = make_scalar(case)
        assert_close(law.log_prob(torch.tensor(values)), oracle(parameters, values))


def test_f01_t02():
    from scipy.integrate import quad
    from F01_helpers import scalar_cases, make_scalar
    for case in scalar_cases(include_variations=True):
        name, _, parameters, values, oracle, discrete, _ = case
        law = make_scalar(case)
        draws = law.sample((SAMPLE_COUNT,))
        assert torch.isfinite(draws).all(), name
        second = law.sample((128,))
        # Even Bernoulli has collision probability below 1e-29 for this check.
        assert not torch.equal(draws[:128], second), name
        if name == 'Multinomial':
            assert draws.shape == (SAMPLE_COUNT, 3)
            assert (draws >= 0).all() and (draws == draws.floor()).all()
            assert (draws.sum(-1) == 5).all()
            for coordinate in range(3):
                probability = stats.binom.cdf(1, 5, parameters['probs'][coordinate])
                assert_frequency(draws[:, coordinate] <= 1, probability)
            for value in values:
                assert_frequency((draws == torch.tensor(value)).all(-1), np.exp(oracle(parameters, value)))
        elif discrete:
            assert draws.shape == (SAMPLE_COUNT,)
            assert (draws >= 0).all() and (draws == draws.floor()).all()
            for threshold in values:
                possible = np.arange(int(threshold)+1)
                probability = np.exp(oracle(parameters, possible)).sum()
                assert_frequency(draws <= threshold, probability)
        else:
            assert draws.shape == (SAMPLE_COUNT,)
            lower = -np.inf
            if name in ('Beta','ContinuousBernoulli','Chi2','Exponential','FisherSnedecor','Gamma','InverseGamma','HalfCauchy','HalfNormal','Kumaraswamy','LogNormal','Weibull'):
                lower = 0.
                assert (draws >= 0).all(), name
            if name in ('Beta','ContinuousBernoulli','Kumaraswamy'):
                assert (draws <= 1).all(), name
            if name == 'Pareto':
                lower = parameters['scale']
                assert (draws >= lower).all()
            if name == 'Uniform':
                lower = parameters['low']
                assert ((draws >= lower) & (draws <= parameters['high'])).all()
            if name == 'VonMises':
                lower = -np.pi
                # Circular angles are equivalent modulo a full turn.
                draws = torch.remainder(draws+np.pi, 2*np.pi)-np.pi
            for threshold in values:
                probability, error = quad(lambda x: float(np.exp(oracle(parameters,x))),lower,threshold,epsabs=1e-10)
                assert error < 1e-7
                indicator = draws <= threshold
                assert_frequency(indicator, probability)
                # The joint event in disjoint pairs also checks independent draws.
                # Its effective n is 20000: margin .04 gives <= 2 exp(-64).
                paired = (indicator[::2] & indicator[1::2]).double().mean().item()
                assert abs(paired-probability**2) < .04, name


def test_f01_t03():
    from F01_helpers import vector_cases, tensor_parameters
    for name, builder, parameters, values, oracle, _ in vector_cases():
        law = builder(tensor_parameters(parameters))
        assert law.event_shape == values.shape[1:], name
        assert_close(law.log_prob(torch.tensor(values)),oracle(parameters,values))
        draws = law.sample((SAMPLE_COUNT,))
        assert draws.shape == (SAMPLE_COUNT,)+values.shape[1:]
        assert torch.isfinite(draws).all()
        if name in ('MultivariateNormal','LowRankMultivariateNormal','MultivariateStudentT'):
            loc = parameters['loc']
            if name == 'LowRankMultivariateNormal':
                covariance = parameters['factor']@parameters['factor'].T+np.diag(parameters['diag'])
            else:
                lower = np.array([[parameters['diagonal'][0],0.],[parameters['off'],parameters['diagonal'][1]]])
                covariance = lower@lower.T
            # Linear projections measure dependence, rather than just marginals.
            for direction in (np.array([1.,0.]),np.array([0.,1.]),np.array([1.,-1.])):
                center = direction@loc
                scale = np.sqrt(direction@covariance@direction)
                threshold = center+.6*scale
                probability = stats.t.cdf(.6,parameters['df']) if name=='MultivariateStudentT' else stats.norm.cdf(.6)
                assert_frequency(draws@torch.tensor(direction) <= threshold, probability)
        elif name == 'Dirichlet':
            assert (draws > 0).all()
            assert_close(draws.sum(-1),np.ones(SAMPLE_COUNT))
            alpha = parameters['concentration']
            for coordinate in range(3):
                assert_frequency(draws[:,coordinate] <= .3,stats.beta.cdf(.3,alpha[coordinate],alpha.sum()-alpha[coordinate]))
        elif name == 'LogisticNormal':
            assert (draws > 0).all()
            assert_close(draws.sum(-1),np.ones(SAMPLE_COUNT))
            latent0 = torch.log(draws[:,0]/(1-draws[:,0]))+np.log(2.)
            latent1 = torch.log(draws[:,1]/draws[:,2])
            for coordinate, latent in enumerate((latent0,latent1)):
                assert_frequency(latent <= .5,stats.norm.cdf(.5,parameters['loc'][coordinate],parameters['scale'][coordinate]))
            assert_frequency((latent0 <= .5)&(latent1 <= .5),np.prod(stats.norm.cdf(.5,parameters['loc'],parameters['scale'])))
        elif name == 'Wishart':
            assert_close(draws,draws.transpose(-1,-2).numpy())
            assert (torch.linalg.eigvalsh(draws)>0).all()
            scale = parameters['scale']*np.array([[1.,.3],[.3,1.4]])
            for direction in (np.array([1.,0.]),np.array([1.,-1.])):
                projected = torch.einsum('i,nij,j->n',torch.tensor(direction),draws,torch.tensor(direction))
                assert_frequency(projected <= parameters['df']*(direction@scale@direction),stats.chi2.cdf(parameters['df'],parameters['df']))
        else:
            assert_close(draws,draws.transpose(-1,-2).numpy())
            assert_close(draws.diagonal(dim1=-2,dim2=-1),np.ones((SAMPLE_COUNT,2)))
            assert (torch.linalg.eigvalsh(draws)>0).all()
            eta = parameters['concentration']
            for threshold in (-.4,.2,.6):
                assert_frequency(draws[:,0,1] <= threshold,stats.beta.cdf((threshold+1)/2,eta,eta))
    event = torch.tensor([-.3,1.4,2.])
    point = velnora.distributions.Delta(event,event_dim=1)
    assert point.event_shape == (3,)
    assert_close(point.sample((11,)),np.broadcast_to(event.numpy(),(11,3)))
    assert_close(point.log_prob(event),0.)
    assert torch.isneginf(point.log_prob(event+torch.tensor([0.,.1,0.])))


def test_f01_t04():
    from F01_helpers import compound_cases, tensor_parameters
    for name, builder, parameters, values, oracle in compound_cases():
        law = builder(tensor_parameters(parameters))
        assert_close(law.log_prob(torch.tensor(values)),oracle(parameters,values))
        draws = law.sample((SAMPLE_COUNT,))
        assert (draws >= 0).all() and (draws == draws.floor()).all()
        assert torch.isfinite(draws).all()
        if name == 'DirichletMultinomial':
            assert draws.shape == (SAMPLE_COUNT,3)
            assert (draws.sum(-1)==5).all()
            for value in values:
                assert_frequency((draws==torch.tensor(value)).all(-1),np.exp(oracle(parameters,value)))
            for coordinate in range(3):
                alpha = parameters['concentration']
                assert_frequency(draws[:,coordinate]<=1,stats.betabinom.cdf(1,5,alpha[coordinate],alpha.sum()-alpha[coordinate]))
        else:
            assert draws.shape == (SAMPLE_COUNT,)
            for threshold in (0,1,3):
                assert_frequency(draws<=threshold,np.exp(oracle(parameters,np.arange(threshold+1))).sum())


def test_f01_t06():
    from F01_helpers import mixture_cases, tensor_parameters
    for name, builder, parameters, values, oracle in mixture_cases():
        law = builder(tensor_parameters(parameters))
        assert law.event_shape == (2,)
        assert_close(law.log_prob(torch.tensor(values)),oracle(parameters,values))
        draws = law.sample((SAMPLE_COUNT,))
        assert draws.shape == (SAMPLE_COUNT,2)
        assert torch.isfinite(draws).all()
        weights = special.softmax(parameters['component_logits'])
        for threshold in (-1.,1.):
            cdf = stats.norm.cdf(threshold,parameters['locs'],parameters['coord_scale'])
            assert_frequency(draws <= threshold,(weights[:,None]*cdf).sum(0))
            assert_frequency((draws<=threshold).all(-1),(weights*cdf.prod(-1)).sum())
    mask = torch.tensor([False,True,False,True])
    loc0,loc1 = np.array([-2.,-1.,0.,1.]),np.array([3.,4.,5.,6.])
    scale0,scale1 = np.array([.6,.8,1.,1.2]),np.array([1.3,1.1,.9,.7])
    selected = velnora.distributions.MaskedMixture(mask,velnora.distributions.Normal(torch.tensor(loc0),torch.tensor(scale0)),velnora.distributions.Normal(torch.tensor(loc1),torch.tensor(scale1)))
    location,scale = np.where(mask,loc1,loc0),np.where(mask,scale1,scale0)
    value = torch.tensor([0.,2.,-1.,3.])
    assert_close(selected.log_prob(value),stats.norm.logpdf(value.numpy(),location,scale))
    draws = selected.sample((SAMPLE_COUNT,))
    assert draws.shape == (SAMPLE_COUNT,4)
    assert_frequency(draws <= 2.,stats.norm.cdf(2.,location,scale))


def test_f01_t11():
    from F01_helpers import (scalar_cases,make_scalar,vector_cases,compound_cases,
                            mixture_cases,additional_score_cases,assert_density_gradients)
    for case in scalar_cases():
        name,_,parameters,values,oracle,discrete,fixed = case
        assert_density_gradients(lambda p:make_scalar(case,p),parameters,values,oracle,observation=not discrete,fixed=fixed)
    for _,builder,parameters,values,oracle,observation in vector_cases():
        assert_density_gradients(builder,parameters,values,oracle,observation=observation)
    for _,builder,parameters,values,oracle in compound_cases()+mixture_cases():
        assert_density_gradients(builder,parameters,values,oracle,observation=values.ndim==2 and values.shape[-1]==2)
    for _,builder,parameters,values,oracle,observation in additional_score_cases():
        assert_density_gradients(builder,parameters,values,oracle,observation=observation)
    # The promise is the availability of finite path derivatives, not a specific
    # noise transform. Density derivatives above are checked against independent
    # oracles; sampling does not pin any implementation's chosen coupling.
    constructors = [
        (lambda p:velnora.distributions.Normal(p[0],p[1]),[.3,1.2]),
        (lambda p:velnora.distributions.MultivariateNormal(p[0].expand(2),scale_tril=p[1]*torch.tensor([[1.,0.],[.4,.8]])),[.3,1.2]),
        (lambda p:velnora.distributions.Beta(p[0],p[1]),[2.3,3.4]),
        (lambda p:velnora.distributions.Gamma(p[0],p[1]),[2.3,1.4]),
        (lambda p:velnora.distributions.StudentT(p[0],p[1],p[2]),[8.4,.3,1.2]),
    ]
    for builder, values in constructors:
        parameters = [torch.tensor(v,requires_grad=True) for v in values]
        draws = builder(parameters).rsample((64,))
        assert draws.requires_grad and torch.isfinite(draws).all()
        # Nonlinear per-draw loss exercises location, scale and shape paths.
        gradients = torch.autograd.grad(draws.sin().sum(),parameters,allow_unused=True)
        for gradient in gradients:
            assert gradient is not None and torch.isfinite(gradient).all()
            assert gradient.abs().sum()>0
