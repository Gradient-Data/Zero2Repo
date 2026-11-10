# feature: F11
"""Acceptance checks for probability-preserving model coordinates."""
import pytest
from scipy import stats, fft
from F01_helpers import check_cdf_samples, gaussian_samples
from F10_helpers import fit_guide, bind_guide
from F11_helpers import (jax, jnp, np, dist, close, read_array, call_public,
                         volume, numerical_jacobian, h, velnora,
                         latent_model, coordinate_run, recovered)
from velnora.infer.reparam import (LocScaleReparam, TransformReparam,
    ProjectedNormalReparam, CircularReparam, ExplicitReparam,
    UnitJacobianReparam, HaarReparam, DiscreteCosineReparam, NeuTraReparam)
from velnora.distributions import transforms as t
from velnora.infer import MCMC, NUTS, autoguide as ag


def test_f11_t01():
    loc = np.array([.7, -1.2]); scale = np.array([1.8, .6])
    u = jnp.array([-.4, .9])
    for student in [False, True]:
        law = (dist.StudentT(7., jnp.asarray(loc), jnp.asarray(scale)) if student
               else dist.Normal(jnp.asarray(loc), jnp.asarray(scale))).to_event(1)
        oracle = lambda x: (stats.t.logpdf(x, 7, loc, scale) if student
                            else stats.norm.logpdf(x, loc, scale)).sum()
        model = latent_model(law)
        effects = []
        for fraction in [0., 1., .35, None]:
            config = {'x': LocScaleReparam(fraction, shape_params=['df'] if student else [])}
            for learned in ([.2, .8] if fraction is None else [None]):
                params = {} if learned is None else {'x_centered': jnp.full((2,), learned)}
                key = 'x' if fraction == 1. else 'x_decentered'
                def run(z):
                    return recovered(model, config, dict(params, **{key: z}))
                x, density, record = coordinate_run(model, config, dict(params, **{key: u}))
                effects.append(x)
                close(density, oracle(x)+volume(run, u))
                close(run(u+.3)-run(u), numerical_jacobian(run, u)@np.full(2,.3))
                if fraction == 0.:
                    close(x, loc+scale*np.asarray(u))
                    expected = stats.t.logpdf(u, 7) if student else stats.norm.logpdf(u)
                    close(density, expected.sum())
                elif fraction == 1.:
                    close(x, u)
                else:
                    # Judge the actual coordinate law, not a prescribed partial-centering formula.
                    aux = record[key]
                    close(aux['fn'].log_prob(aux['value']), density)
        for i,j in [(0,2),(1,2),(3,4)]:
            assert np.linalg.norm(effects[i]-effects[j]) > 0
        for fraction in [-.1, 1.1, jnp.array([.3, -1.])]:
            with pytest.raises(ValueError):
                coordinate_run(model, {'x': LocScaleReparam(fraction)}, {})
    with pytest.raises(ValueError):
        coordinate_run(latent_model(dist.LogNormal()), {'x': LocScaleReparam(0.)}, {})


def test_f11_t02():
    base = dist.Normal(jnp.array([.3,-.5]), jnp.array([.8,1.4])).to_event(1)
    law = dist.TransformedDistribution(base, [t.AffineTransform(.2,1.7), t.ExpTransform()])
    model = latent_model(law); config = {'x': TransformReparam()}
    u = jnp.array([-.4,.8])
    x, density, _ = coordinate_run(model, config, {'x_base':u})
    close(x, np.exp(.2+1.7*np.asarray(u)))
    close(density, stats.norm.logpdf(u,[.3,-.5],[.8,1.4]).sum())
    def many_transformed():
        with velnora.plate('draws',8192):
            return velnora.sample('x',law)
    sample = read_array(call_public(h.seed(h.reparam(many_transformed,config=config),44)))
    gaussian_samples(np.log(sample),.2+1.7*np.array([.3,-.5]),np.diag((1.7*np.array([.8,1.4]))**2))
    for dim in [2,3]:
        concentration = np.linspace(-.7,1.1,dim)
        model = latent_model(dist.ProjectedNormal(jnp.asarray(concentration)))
        config = {'x': ProjectedNormalReparam()}
        noise = jnp.linspace(.2,.8,dim)
        x, density, record = coordinate_run(model, config, {'x_normal':noise})
        auxiliary = record['x_normal']
        close(density, auxiliary['fn'].log_prob(auxiliary['value']))
        close(np.linalg.norm(x), 1.)
        repeated = coordinate_run(model, config, {'x_normal':noise}, seed=72)[0]
        close(repeated, x)
        # Independent Gaussian projection law; two-sample DKW union risk < 1e-10.
        def many():
            with velnora.plate('draws',16384):
                return velnora.sample('x',dist.ProjectedNormal(jnp.asarray(concentration)))
        samples = read_array(call_public(h.seed(h.reparam(many,config=config),18)))
        independent = np.random.default_rng(98).normal(size=(65536,dim))+concentration
        independent /= np.linalg.norm(independent,axis=-1,keepdims=True)
        close(np.linalg.norm(samples,axis=-1),np.ones(len(samples)))
        for direction in np.eye(dim):
            assert stats.ks_2samp(samples@direction, independent@direction).statistic < .055
    model = latent_model(dist.VonMises(.6,2.3)); config = {'x':CircularReparam()}
    for angle in [-7.4,-1.2,.8,8.1]:
        x, density, _ = coordinate_run(model,config,{'x_unwrapped':jnp.asarray(angle)})
        close(np.exp(1j*x),np.exp(1j*angle))
        close(density, stats.vonmises.logpdf(x,2.3,loc=.6))
    # Infer in circular coordinates; independent chains bound correlation uncertainty.
    means = []
    for seed in range(8):
        chain = MCMC(NUTS(h.reparam(model,config=config)),num_warmup=300,num_samples=1200,progress_bar=False)
        call_public(chain.run,jax.random.key(seed+80),timeout=240)
        a = read_array(chain.get_samples()['x'])
        means.append([np.cos(a).mean(),np.sin(a).mean()])
    expected = np.array([np.cos(.6),np.sin(.6)])*stats.vonmises(2.3).expect(np.cos)
    np.testing.assert_allclose(np.mean(means,axis=0),expected,atol=.09,rtol=0)


def test_f11_t03():
    cases = [(TransformReparam(),dist.LogNormal(.2,.8),.9,'x_base',.1),
             (ProjectedNormalReparam(),dist.ProjectedNormal(jnp.array([.4,.8])),jnp.array([1.,0.]),'x_normal',jnp.array([.2,-.4])),
             (CircularReparam(),dist.VonMises(.4,1.2),.3,'x_unwrapped',.2),
             (UnitJacobianReparam(t.AffineTransform(.7,1.)),dist.Normal().expand((4,)).to_event(1),jnp.ones(4),'x_transformed',jnp.zeros(4)),
             (HaarReparam(),dist.Normal().expand((4,)).to_event(1),jnp.ones(4),'x_haar',jnp.zeros(4)),
             (DiscreteCosineReparam(),dist.Normal().expand((4,)).to_event(1),jnp.ones(4),'x_dct',jnp.zeros(4))]
    for reparam,law,observation,key,coordinate in cases:
        x,density,_ = coordinate_run(latent_model(law),{'x':reparam},{key:coordinate})
        assert np.isfinite(x).all() and np.isfinite(density).all()
        with pytest.raises(AssertionError):
            coordinate_run(latent_model(law,observation),{'x':reparam},{key:coordinate})


def test_f11_t04():
    u = jnp.array([-.6,.2,1.1,-.3])
    loc = np.linspace(-.5,.8,4); scale = np.linspace(.7,1.4,4)
    model = latent_model(dist.Normal(jnp.asarray(loc),jnp.asarray(scale)).to_event(1))
    explicit = ExplicitReparam(t.AffineTransform(.4,1.7))
    x,p,_ = coordinate_run(model,{'x':explicit},{'x_base':u})
    close(x,(np.asarray(u)-.4)/1.7)
    close(p,stats.norm.logpdf(x,loc,scale).sum()-4*np.log(1.7))
    unit = UnitJacobianReparam(t.AffineTransform(.7,1.))
    x,p,_ = coordinate_run(model,{'x':unit},{'x_transformed':u})
    close(x,np.asarray(u)-.7); close(p,stats.norm.logpdf(x,loc,scale).sum())
    haar = np.array([[1,1,1,1],[1,1,-1,-1],[np.sqrt(2),-np.sqrt(2),0,0],[0,0,np.sqrt(2),-np.sqrt(2)]])/2
    for reparam,key,basis in [(HaarReparam(),'x_haar',haar),
                              (DiscreteCosineReparam(),'x_dct',fft.dct(np.eye(4),type=2,norm='ortho',axis=0))]:
        config = {'x':reparam}
        run = lambda z: recovered(model,config,{key:z})
        x,p,_ = coordinate_run(model,config,{key:u})
        matrix = numerical_jacobian(run,u)
        close(run(u+.2),matrix@(np.asarray(u)+.2))
        close(volume(run,u),0.)
        forward = np.linalg.inv(matrix)
        directions = forward/np.linalg.norm(forward,axis=1,keepdims=True)
        alignment = np.abs(directions@basis.T)
        close(alignment.max(axis=1),np.ones(4))
        assert len(set(alignment.argmax(axis=1))) == 4
        close(p,stats.norm.logpdf(x,loc,scale).sum())
        # Positive support and a non-final event axis exercise the same bound path.
        positive = latent_model(dist.LogNormal(jnp.zeros((4,2)),.8).to_event(2))
        rp = HaarReparam(dim=-2) if key=='x_haar' else DiscreteCosineReparam(dim=-2)
        z = jnp.arange(8.).reshape(4,2)/7-.4
        mapping = lambda v: np.log(recovered(positive,{'x':rp},{key:v}))
        x,p,_ = coordinate_run(positive,{'x':rp},{key:z})
        assert (x>0).all()
        close(volume(mapping,z),0.)
        close(p,stats.norm.logpdf(np.log(x),0,.8).sum())
        event_matrix = numerical_jacobian(mapping,z)
        close(mapping(z).ravel(),event_matrix@np.asarray(z).ravel())
        for column in range(2):
            indices = np.arange(column,8,2)
            other = np.arange(1-column,8,2)
            close(event_matrix[np.ix_(indices,other)],np.zeros((4,4)))
            actual = np.linalg.inv(event_matrix[np.ix_(indices,indices)])
            directions = actual/np.linalg.norm(actual,axis=1,keepdims=True)
            alignment = np.abs(directions@basis.T)
            close(alignment.max(axis=1),np.ones(4))
            assert len(set(alignment.argmax(axis=1))) == 4


def test_f11_t05():
    prior_mean = np.array([-.4,.3])
    prior_sd = np.array([1.7,.9])
    def model():
        pair = velnora.sample('pair',dist.Normal(jnp.asarray(prior_mean),jnp.asarray(prior_sd)).to_event(1))
        velnora.sample('obs',dist.Normal(pair.sum(),.6),obs=1.1)
    guide = ag.AutoMultivariateNormal(model)
    params = fit_guide(model,guide,steps=1000)
    fitted_transform = call_public(guide.get_transform,params)
    def make():
        return NeuTraReparam(guide,params)
    def run(z):
        transport = make()
        from velnora.infer.util import log_density
        p,tr = call_public(log_density,h.seed(transport.reparam(model),42),(),{}, {'auto_shared_latent':z})
        return read_array(tr['pair']['value']),read_array(p)
    for z in [jnp.array([-.7,.2]),jnp.array([.9,-.4])]:
        x,p = run(z)
        close(x,call_public(fitted_transform,z))
        restored = call_public(make().transform_sample,z)
        close(x,restored['pair'])
        correction = volume(lambda v:run(v)[0],z)
        close(p,stats.norm.logpdf(x,prior_mean,prior_sd).sum()+stats.norm.logpdf(1.1,x.sum(),.6)+correction)
    assert np.linalg.norm(run(jnp.array([.9,-.4]))[0]-run(jnp.array([-.7,.2]))[0])>0
    covariance = np.linalg.inv(np.diag(1/prior_sd**2)+np.ones((2,2))/.6**2)
    mean = covariance@(prior_mean/prior_sd**2+1.1/.6**2)
    estimates = []
    second_moments = []
    # Independent chains, rather than a self-reported effective sample count.
    # A generous absolute error budget is requested in the ledger; no guide-fit
    # accuracy is assumed, since MCMC must correct the fitted approximation.
    for seed in range(8):
        transport = make()
        chain = MCMC(NUTS(transport.reparam(model)),num_warmup=300,num_samples=2000,progress_bar=False)
        call_public(chain.run,jax.random.key(seed+100),timeout=240)
        original = call_public(transport.transform_sample,chain.get_samples()['auto_shared_latent'])
        samples = read_array(original['pair'])
        estimates.append(samples.mean(axis=0))
        centered = samples-mean
        second_moments.append(centered.T@centered/len(centered))
    np.testing.assert_allclose(np.mean(estimates,axis=0),mean,atol=.15,rtol=0)
    np.testing.assert_allclose(np.mean(second_moments,axis=0),covariance,atol=.15,rtol=0)
    for cls,error in [(ag.AutoNormal,TypeError),(ag.AutoDAIS,ValueError)]:
        incompatible = cls(model)
        values = bind_guide(incompatible)
        with pytest.raises(error):
            call_public(NeuTraReparam,incompatible,values)
