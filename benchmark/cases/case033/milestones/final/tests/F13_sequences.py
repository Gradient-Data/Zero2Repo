# feature: F13
"""Acceptance observations for sequence laws and temporal predictions."""
import numpy as np
import pytest
import torch
from scipy import stats
import velnora
from velnora.contrib.timeseries import (IndependentMaternGP, LinearlyCoupledMaternGP,
    DependentMaternGP, GenericLGSSM, GenericLGSSMWithGPNoiseModel)
from _helpers import isolated_state
from F01_helpers import assert_close, assert_frequency, SAMPLE_COUNT
from F05_helpers import finite_state_evidence
from F13_helpers import (make_gaussian, scalar_system, linear_joint,
    conditional_normal, matern_cov, check_temporal, learn_temporal)

STANDARD_SMOOTHNESS = (.5, 1.5, 2.5)


def check_temporal_any_smoothness(model, targets, mean, covariance_for_nu, future, **kwargs):
    """check_temporal against every standard Matern order, accepting the first match.

    The public documents fix no smoothness for the internal Matern noise of
    GenericLGSSMWithGPNoiseModel, so any of the standard orders is a faithful
    reading. A covariance that is wrong for a different reason still fails all
    three.
    """
    failures = []
    for nu in STANDARD_SMOOTHNESS:
        try:
            check_temporal(model, targets, mean, covariance_for_nu(nu), future, **kwargs)
            return
        except AssertionError as exc:
            failures.append('nu={}: {}'.format(nu, exc))
    raise AssertionError('no standard Matern order matches; ' + ' | '.join(failures))


def test_f13_t01():
    with isolated_state(dtype=torch.float64):
        initial = np.array([.8,.2])
        transition = np.array([[.2,.8],[.65,.35]])
        emission = np.array([[.85,.15],[.25,.75]])
        model = velnora.distributions.DiscreteHMM(torch.tensor(np.log(initial)),
            torch.tensor(np.log(transition)), velnora.distributions.Categorical(probs=torch.tensor(emission)))
        for obs in ([0,1,1], [1,0,0,1]):
            mass = 0.
            end = np.zeros(2)
            for start in range(2):
                evidence = finite_state_evidence((start,),2,obs,
                    lambda h,s: transition[h[-1],s], lambda s,y: emission[s,y])
                mass += initial[start]*evidence
                for final in range(2):
                    # Endpoint evidence by a terminal observation marker.
                    marked = list(enumerate(obs))
                    end[final] += initial[start]*finite_state_evidence((start,),2,marked,
                        lambda h,s: transition[h[-1],s],
                        lambda s,item: emission[s,item[1]]*(s == final if item[0] == len(obs)-1 else 1))
            value = torch.tensor(obs)
            assert_close(model.log_prob(value), np.log(mass))
            assert_close(model.filter(value).probs, end/mass)


def test_f13_t02():
    with isolated_state(seed=1302,dtype=torch.float64):
        model,(mean,cov) = make_gaussian()
        value = torch.tensor([[.3],[-.8],[1.2],[.1]])
        assert_close(model.log_prob(value),stats.multivariate_normal.logpdf(value.numpy().ravel(),mean=mean[:-1],cov=cov[:-1,:-1]))
        cm,cc = conditional_normal(mean,cov,value.numpy(),4)
        posterior = model.filter(value)
        assert_close(posterior.mean,cm)
        assert_close(posterior.covariance_matrix,cc)
        prefix = model.prefix_condition(value[:2])
        pm,pc = conditional_normal(mean[:-1],cov[:-1,:-1],value[:2].numpy(),2)
        assert_close(prefix.log_prob(value[2:]),stats.multivariate_normal.logpdf(value[2:].numpy().ravel(),mean=pm,cov=pc))
        # Check distribution probabilities (including cross-time dependence),
        # with bounded indicators and the existing Hoeffding error budget.
        samples = model.rsample((SAMPLE_COUNT,)).squeeze(-1)
        for time in (0,3):
            threshold = mean[time]+.4
            assert_frequency(samples[:,time] < threshold,stats.norm.cdf(.4/np.sqrt(cov[time,time])))
        assert_frequency((samples[:,0]<mean[0]) & (samples[:,3]<mean[3]),
            stats.multivariate_normal.cdf([0.,0.],mean=[0.,0.],cov=cov[np.ix_([0,3],[0,3])]))
        draws = prefix.rsample((SAMPLE_COUNT,)).squeeze(-1)
        assert_frequency(draws[:,0]<pm[0]+.3,stats.norm.cdf(.3/np.sqrt(pc[0,0])))


def test_f13_t03():
    with isolated_state(seed=1303,dtype=torch.float64):
        initial = velnora.distributions.MultivariateNormal(torch.tensor([[.2],[1.1]]),torch.tensor([[[.7]],[[1.3]]]))
        a = torch.tensor([[[.4]],[[.9]],[[.6]]])
        b = torch.tensor([[[1.2]],[[.7]],[[1.4]]])
        process = velnora.distributions.MultivariateNormal(torch.tensor([0.]),torch.tensor([[.3]]))
        noise = velnora.distributions.MultivariateNormal(torch.tensor([.1]),torch.tensor([[.4]]))
        model = velnora.distributions.GaussianHMM(initial,a,process,b,noise)
        samples = model.rsample((SAMPLE_COUNT,))
        assert samples.shape == (SAMPLE_COUNT,2,3,1)
        value = torch.tensor([[.2],[-.5],[1.]])
        for batch in range(2):
            mean,cov = linear_joint(initial.mean[batch].numpy(),initial.covariance_matrix[batch].numpy(),
                a.numpy(),np.zeros((3,1)),np.repeat([[[.3]]],3,0),b.numpy(),np.full((3,1),.1),np.repeat([[[.4]]],3,0))
            assert_close(model.log_prob(value)[batch],stats.multivariate_normal.logpdf(value.numpy().ravel(),mean=mean[:-1],cov=cov[:-1,:-1]))
            assert_frequency(samples[:,batch,-1,0]<mean[2]+.5,stats.norm.cdf(.5/np.sqrt(cov[2,2])))
        homogeneous = velnora.distributions.GaussianHMM(initial,torch.tensor([[.6]]),process,torch.tensor([[1.2]]),noise)
        with pytest.raises(AssertionError):
            homogeneous.rsample()
        explicit = velnora.distributions.GaussianHMM(initial,torch.tensor([[.6]]),process,torch.tensor([[1.2]]),noise,duration=5)
        assert explicit.rsample().shape == (2,5,1)
        # Homogeneous scoring accepts an observed length even without duration.
        mean,cov = linear_joint([.2],[[.7]],np.full((5,1,1),.6),np.zeros((5,1)),np.full((5,1,1),.3),np.full((5,1,1),1.2),np.full((5,1),.1),np.full((5,1,1),.4))
        assert_close(homogeneous.log_prob(torch.zeros(5,1))[0],stats.multivariate_normal.logpdf(np.zeros(5),mean=mean[:-1],cov=cov[:-1,:-1]))


def test_f13_t04():
    with isolated_state(dtype=torch.float64):
        a,b,u,v,q,r = scalar_system(3)
        alpha,beta = 3.4,2.1
        model = velnora.distributions.GammaGaussianHMM(velnora.distributions.Gamma(alpha,beta),
            velnora.distributions.MultivariateNormal(torch.tensor([.4]),torch.tensor([[.8]])),
            torch.tensor(a),velnora.distributions.MultivariateNormal(torch.tensor(u),torch.tensor(q)),
            torch.tensor(b),velnora.distributions.MultivariateNormal(torch.tensor(v),torch.tensor(r)))
        mean,cov = linear_joint([.4],[[.8]],a,u,q,b,v,r)
        for data in ([[.2],[-.4],[1.1]], [[2.],[-1.],[.6]]):
            value = torch.tensor(data)
            delta = value.numpy().ravel()-mean[:-1]
            mahal = delta @ np.linalg.solve(cov[:-1,:-1],delta)
            assert_close(model.log_prob(value),stats.multivariate_t.logpdf(value.numpy().ravel(),loc=mean[:-1],shape=beta/alpha*cov[:-1,:-1],df=2*alpha))
            precision,state = model.filter(value)
            assert_close(precision.concentration,alpha+1.5)
            assert_close(precision.rate,beta+.5*mahal)
            cm,cc = conditional_normal(mean,cov,value.numpy(),3)
            assert_close(state.mean,cm)
            # Original returns a precision Cholesky as a covariance Cholesky;
            # the unsupported covariance promise is reported in the ledger.


def test_f13_t05():
    with isolated_state(dtype=torch.float64):
        steps = 3
        factors = [(np.array([.4]),np.array([[.8]]),[0])]
        tc = np.array([[1.2,.4],[.4,.9]])
        oc = np.array([[.7,-.3],[-.3,1.4]])
        for t in range(steps):
            factors.append((np.array([.1,-.2]),tc,[t,t+1]))
            factors.append((np.array([.3,.5]),oc,[t+1,steps+1+t]))
        precision = np.zeros((7,7))
        info = np.zeros(7)
        for loc,cov,indices in factors:
            inv = np.linalg.inv(cov)
            precision[np.ix_(indices,indices)] += inv
            info[indices] += inv @ loc
        cov = np.linalg.inv(precision)
        mean = cov @ info
        model = velnora.distributions.GaussianMRF(velnora.distributions.MultivariateNormal(torch.tensor([.4]),torch.tensor([[.8]])),
            velnora.distributions.MultivariateNormal(torch.tensor([.1,-.2]),torch.tensor(tc)),
            velnora.distributions.MultivariateNormal(torch.tensor([.3,.5]),torch.tensor(oc)))
        for value in (torch.tensor([[.2],[-.7],[1.3]]),torch.tensor([[1.],[-2.],[.6]])):
            assert_close(model.log_prob(value),stats.multivariate_normal.logpdf(value.numpy().ravel(),mean=mean[4:],cov=cov[4:,4:]))


def test_f13_t06():
    with isolated_state(seed=1306,dtype=torch.float64):
        loc = torch.tensor([-.7,1.2],requires_grad=True)
        # Positive exponential innovations cannot be replaced by Gaussian noise.
        initial = velnora.distributions.Laplace(loc,torch.tensor([.3,.5])).to_event(1)
        process = velnora.distributions.Exponential(torch.tensor([1.3,.8])).to_event(1)
        noise = velnora.distributions.Uniform(torch.tensor([-.2,-.4]),torch.tensor([.2,.4])).to_event(1)
        model = velnora.distributions.LinearHMM(initial,torch.eye(2),process,torch.eye(2),noise,duration=3)
        samples = model.rsample((SAMPLE_COUNT,))
        difference = samples[:,1]-samples[:,0]
        # Independent uniform observation differences have bounded support;
        # compare a CDF computed by independent quadrature of the noise law.
        from scipy.integrate import quad
        for j,(rate,width) in enumerate(((1.3,.4),(.8,.8))):
            threshold = .5
            probability,error = quad(lambda z:(width-abs(z))/width**2*stats.expon.cdf(threshold-z,scale=1/rate),-width,width,points=[threshold] if threshold<width else None)
            assert error < 1e-7
            assert_frequency(difference[:,j]<threshold,probability)
            scale = (.3,.5)[j]
            first_probability,outer_error = quad(
                lambda innovation: rate*np.exp(-rate*innovation)*quad(
                    lambda observed_noise: stats.laplace.cdf(.4-innovation-observed_noise,scale=scale)/width,
                    -width/2,width/2,epsabs=1e-9)[0],0,np.inf,epsabs=1e-9)
            assert outer_error < 1e-7
            assert_frequency(samples[:,0,j]<loc[j].item()+.4,first_probability)
        gradient, = torch.autograd.grad(samples.mean(),loc)
        assert_close(gradient,torch.full((2,),.5))
        # IndependentHMM converts an actual univariate batch into observations.
        base_location = torch.tensor([[-1.],[2.]],requires_grad=True)
        base = velnora.distributions.LinearHMM(velnora.distributions.Normal(base_location,.3).to_event(1),
            torch.tensor([[.7]]),velnora.distributions.Laplace(torch.zeros(2,1,1),.5).to_event(1),
            torch.tensor([[1.]]),velnora.distributions.Uniform(-torch.ones(2,1,1),torch.ones(2,1,1)).to_event(1),duration=3)
        combined = velnora.distributions.IndependentHMM(base).rsample((SAMPLE_COUNT,))
        assert combined.shape == (SAMPLE_COUNT,3,2)
        # Symmetric laws give each marginal median its propagated initial mean.
        left = combined[:,0,0]<-.7
        right = combined[:,0,1]<1.4
        assert_frequency(left,.5)
        assert_frequency(right,.5)
        assert_frequency(left & right,.25)
        group_gradient, = torch.autograd.grad(combined[:,0,0].mean(),base_location)
        assert_close(group_gradient,[[.7],[0.]])
        with pytest.raises(AssertionError):
            velnora.distributions.LinearHMM(velnora.distributions.Poisson(torch.ones(1)).to_event(1),torch.ones(1,1),
                velnora.distributions.Normal(torch.zeros(1),1).to_event(1),torch.ones(1,1),velnora.distributions.Normal(torch.zeros(1),1).to_event(1),duration=2)


def test_f13_t07():
    with isolated_state(seed=1307,dtype=torch.float64):
        targets = torch.tensor([[.3,-.4],[1.1,.2],[-.7,.8],[.4,-.1]])
        future = torch.tensor([.4,1.7])
        times = np.r_[np.arange(4)*.6,1.8+future.numpy()]
        for nu in (.5,1.5,2.5):
            velnora.clear_param_store()
            model = IndependentMaternGP(nu=nu,dt=.6,obs_dim=2,
                length_scale_init=torch.tensor([.8,1.4]),kernel_scale_init=torch.tensor([1.2,.7]),
                obs_noise_scale_init=torch.tensor([.3,.5]))
            for trained in (False,True):
                if trained:
                    learn_temporal(model,targets)
                cov = np.zeros((12,12))
                for j in range(2):
                    idx = np.arange(j,12,2)
                    c = matern_cov(times,nu,model.kernel.length_scale[j].item(),model.kernel.kernel_scale[j].item())
                    c += np.eye(6)*model.obs_noise_scale[j].item()**2
                    cov[np.ix_(idx,idx)] = c
                check_temporal(model,targets,np.zeros(12),cov,future,independent=True)


def test_f13_t08():
    with isolated_state(seed=1308,dtype=torch.float64):
        targets = torch.tensor([[.2,-.4],[.9,.3],[-.6,.7],[.5,-.2]])
        future = torch.tensor([.5,1.6])
        times = np.r_[np.arange(4)*.7,2.1+future.numpy()]
        for nu in (.5,1.5,2.5):
            velnora.clear_param_store()
            model = LinearlyCoupledMaternGP(nu=nu,dt=.7,obs_dim=2,num_gps=2,
                length_scale_init=torch.tensor([.8,1.3]),kernel_scale_init=torch.tensor([1.1,.6]),
                obs_noise_scale_init=torch.tensor([.25,.4]))
            with torch.no_grad():
                model.A.copy_(torch.tensor([[1.,.5],[-.3,.9]]))
            for trained in (False,True):
                if trained:
                    learn_temporal(model,targets)
                cov = np.zeros((12,12))
                a = model.A.detach().numpy()
                for j in range(2):
                    c = matern_cov(times,nu,model.kernel.length_scale[j].item(),model.kernel.kernel_scale[j].item())
                    cov += np.kron(c,np.outer(a[j],a[j]))
                cov += np.kron(np.eye(6),np.diag(model.obs_noise_scale.detach().numpy()**2))
                check_temporal(model,targets,np.zeros(12),cov,future)
        # Equal correlation lengths retain genuine cross-output dependence and
        # admit the closed-form covariance of a second-order driven process.
        velnora.clear_param_store()
        model = DependentMaternGP(nu=1.5,dt=.7,obs_dim=2,length_scale_init=torch.tensor([1.2,1.2]),
                                  obs_noise_scale_init=torch.tensor([.3,.3]))
        model.wiener_noise_tril = torch.tensor([[1.1,0.],[.6,.8]])
        rho = np.sqrt(3)/1.2
        w = model.wiener_noise_tril.detach().numpy()
        spatial = w @ w.T/(4*rho**3)
        cov = np.kron(matern_cov(times,1.5,1.2,1.),spatial)
        cov += np.kron(np.eye(6),np.diag([.3**2,.3**2]))
        check_temporal(model,targets,np.zeros(12),cov,future,check_covariance="diagonal")
        learn_temporal(model,targets)
        # After joint training, use a general independent SDE covariance integral
        # to accommodate the two lengths no longer being equal.
        from scipy.integrate import quad
        model.obs_noise_scale = torch.tensor([.3,.3])
        lengths = model.kernel.length_scale.detach().numpy()
        w = model.wiener_noise_tril.detach().numpy()
        drive = w @ w.T
        cov = np.empty((12,12))
        for t in range(6):
            for s in range(6):
                for i in range(2):
                    for j in range(2):
                        lag = times[t]-times[s]
                        ri,rj = np.sqrt(3)/lengths[i],np.sqrt(3)/lengths[j]
                        integral,error = quad(lambda z:(z+max(lag,0))*(z+max(-lag,0))*np.exp(-ri*(z+max(lag,0))-rj*(z+max(-lag,0))),0,np.inf,epsabs=1e-11)
                        assert error < 1e-8
                        cov[2*t+i,2*s+j] = drive[i,j]*integral
        cov += np.kron(np.eye(6),np.diag(model.obs_noise_scale.detach().numpy()**2))
        check_temporal(model,targets,np.zeros(12),cov,future,check_covariance="diagonal")
        # One-output forecasts do not encounter the baseline's erroneous
        # broadcasting of observation variances into off-diagonal entries.
        velnora.clear_param_store()
        scalar = DependentMaternGP(nu=1.5,dt=.7,obs_dim=1,
            length_scale_init=torch.tensor([1.2]),obs_noise_scale_init=torch.tensor([.3]))
        scalar.wiener_noise_tril = torch.tensor([[1.1]])
        cov = matern_cov(times,1.5,1.2,1.)*1.1**2/(4*rho**3)+np.eye(6)*.09
        check_temporal(scalar,targets[:,:1],np.zeros(6),cov,future)


def test_f13_t09():
    with isolated_state(seed=1309,dtype=torch.float64):
        targets = torch.tensor([[.2,-.4],[.7,.3],[-.5,.9],[.4,-.2]])
        for cls in (GenericLGSSM,GenericLGSSMWithGPNoiseModel):
            velnora.clear_param_store()
            model = cls(obs_dim=2,state_dim=2,obs_noise_scale_init=torch.tensor([.3,.5]))
            gp = cls is GenericLGSSMWithGPNoiseModel
            transition = model.z_trans_matrix if gp else model.trans_matrix
            observation = model.z_obs_matrix if gp else model.obs_matrix
            with torch.no_grad():
                transition.copy_(torch.tensor([[.7,.2],[-.1,.6]]))
                observation.copy_(torch.tensor([[1.,.4],[-.2,.8]]))
            for trained in (False,True):
                if trained:
                    learn_temporal(model,targets)
                a = transition.detach().numpy()
                b = observation.detach().numpy()
                q = np.diag(model.trans_noise_scale_sq.detach().numpy())
                r = np.diag(model.obs_noise_scale.detach().numpy()**2)
                mean,cov = linear_joint(np.zeros(2),np.diag(model.init_noise_scale_sq.detach().numpy()),
                    np.repeat(a[None],6,0),np.zeros((6,2)),np.repeat(q[None],6,0),
                    np.repeat(b[None],6,0),np.zeros((6,2)),np.repeat(r[None],6,0))
                mean,cov = mean[:-2],cov[:-2,:-2]
                if gp:
                    def gp_covariance(nu, base=cov, m=model):
                        c = base.copy()
                        for j in range(2):
                            idx = np.arange(j,12,2)
                            c[np.ix_(idx,idx)] += matern_cov(np.arange(6),nu,m.kernel.length_scale[j].item(),m.kernel.kernel_scale[j].item())
                        return c
                    check_temporal_any_smoothness(model,targets,mean,gp_covariance,2,check_covariance=False)
                else:
                    check_temporal(model,targets,mean,cov,2)
            if gp:
                # The original omits posterior cross-component covariance.
                # Its covariance is dependable when the linear contribution is
                # absent; likelihood and mean above still exercise both parts.
                with torch.no_grad():
                    observation.zero_()
                cov = np.kron(np.eye(6),np.diag(model.obs_noise_scale.detach().numpy()**2))
                def gp_only_covariance(nu, base=cov, m=model):
                    c = base.copy()
                    for j in range(2):
                        idx = np.arange(j,12,2)
                        c[np.ix_(idx,idx)] += matern_cov(np.arange(6),nu,m.kernel.length_scale[j].item(),m.kernel.kernel_scale[j].item())
                    return c
                check_temporal_any_smoothness(model,targets,np.zeros(12),gp_only_covariance,2)


def test_f13_t10():
    with isolated_state(dtype=torch.float64):
        for cls in (IndependentMaternGP,LinearlyCoupledMaternGP,DependentMaternGP):
            supported = (1.5,) if cls is DependentMaternGP else (.5,1.5,2.5)
            for nu in supported:
                velnora.clear_param_store()
                model = cls(nu=nu,obs_dim=2)
                assert torch.isfinite(model.log_prob(torch.tensor([[.2,-.1],[.6,.4],[-.3,.8]]))).all()
            refused = (.5,2.5,1.) if cls is DependentMaternGP else (1.,3.5)
            for nu in refused:
                with pytest.raises(NotImplementedError):
                    cls(nu=nu,obs_dim=2)


@pytest.mark.parametrize("cls", (GenericLGSSM, GenericLGSSMWithGPNoiseModel))
def test_learnable_observation_location(cls):
    with isolated_state(seed=1311, dtype=torch.float64):
        targets = torch.tensor([[.2, -.4], [.7, .3], [-.5, .9], [.4, -.2]])
        offset = torch.tensor([1.3, -.8])
        velnora.clear_param_store()
        model = cls(obs_dim=2, state_dim=2,
                    obs_noise_scale_init=torch.tensor([.3, .5]),
                    learnable_observation_loc=True)
        baseline = model.log_prob(targets).detach()
        with torch.no_grad():
            model.obs_loc.copy_(offset)
        shifted = targets+offset
        assert_close(model.log_prob(shifted), baseline.numpy())
        derivative = torch.autograd.grad(model.log_prob(shifted), model.obs_loc)[0]
        expected = []
        for coordinate in range(2):
            delta = torch.zeros(2)
            delta[coordinate] = 1e-5
            expected.append((model.log_prob(shifted-delta)-model.log_prob(shifted+delta)).detach().item()/2e-5)
        assert_close(derivative, expected)
        assert derivative.abs().sum() > 1e-8
