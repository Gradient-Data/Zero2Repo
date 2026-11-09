# feature: F01
"""Acceptance checks for the public probability distribution capability."""
import gc
import warnings

import pytest
from F01_helpers import (
    jax, jnp, np, stats, special, integrate, linalg, dist,
    close, draws, check_cdf_samples, frequency, gaussian_samples,
    scalar_laws, count_laws, vector_laws, matrix_laws, check_moments,
    lkj_density, cholesky_jacobian, read_array, call_public,
    N, ALPHA, MEAN, COV, FACTOR, ADJ, CAR_COV,
)


@pytest.fixture(autouse=True)
def release_compilation_cache():
    yield
    jax.clear_caches()
    gc.collect()


def test_f01_t01():
    # Across-key replications are tested as draws, never against a reference bitstream.
    laws=[r.law for r in scalar_laws()]+[r.law for r in count_laws()]
    laws += [r[0] for r in vector_laws()]+[r[0] for r in matrix_laws()]
    laws += [dist.Dirichlet(jnp.array([2.,3.,4.])),dist.LKJ(3),dist.LKJCholesky(3),
             dist.VonMises(.3,1.4),dist.SineBivariateVonMises(.3,-.2,1.4,1.7,correlation=.3),
             dist.ProjectedNormal(jnp.array([.3,-.2,.7])),
             dist.SineSkewed(dist.VonMises(jnp.array([.3,-.2]),jnp.array([1.4,1.7])).to_event(1),jnp.array([.2,-.3])),
             dist.MatrixNormal(jnp.zeros((2,2)),jnp.array(FACTOR),jnp.array([[.8,0.],[.2,1.1]])),
             dist.RelaxedBernoulli(.7,probs=.3),dist.GaussianRandomWalk(1.3,4),
             dist.GaussianStateSpace(3,jnp.array([[.7,.2],[-.1,.6]]),covariance_matrix=jnp.array(COV)),
             dist.ZeroSumNormal(1.3,(3,4)),
             dist.CirculantNormal(jnp.zeros(4),covariance_row=jnp.array([1.8,.3,.1,.3])),
             dist.EulerMaruyama(jnp.array([0.,.2,.7]),lambda y,t:(-.3*y,.7),dist.Normal(.3,1.2))]
    for i,law in enumerate(laws):
        a=draws(law,31,64); b=draws(law,31,64)
        np.testing.assert_array_equal(a,b)
        # A key-ignoring sampler repeats a whole block across all replications.
        blocks=np.stack([draws(law,k,32) for k in range(4)])
        assert any(not np.array_equal(blocks[0],x) for x in blocks[1:]), type(law)
    replicated=np.concatenate([draws(dist.Normal(.4,1.3),k,128) for k in range(64)])
    check_cdf_samples(replicated,stats.norm(.4,1.3).cdf)
    # Replication means have the normal law only when keys provide independent draws.
    means=np.array([draws(dist.Normal(.4,1.3),k,32).mean() for k in range(1024)])
    check_cdf_samples(means,stats.norm(.4,1.3/np.sqrt(32)).cdf)


def test_f01_t02():
    for defaults in [False,True]:
        for row in scalar_laws(defaults):
            x=row.oracle.ppf(np.array([.07,.31,.63,.92]))
            close(row.law.log_prob(jnp.array(x)),row.oracle.logpdf(x))


def test_f01_t03():
    # 2**20 draws give a DKW margin of 0.0037 (risk 1e-12). Look-alike laws
    # sampled in place of a listed family differ by more even at their best
    # matching scale: Student t(7) vs normal 0.0092, soft Laplace vs logistic
    # 0.0063, logistic vs normal 0.0095 (sup-CDF distances by quadrature).
    for row in scalar_laws():
        x=draws(row.law,n=2**20)
        lo,hi=row.oracle.support()
        assert np.all((x>=lo)&(x<=hi)),row.label
        check_cdf_samples(x,row.oracle.cdf)


def test_f01_t04():
    for row in count_laws():
        close(row.law.log_prob(jnp.array(row.outcomes)),np.log(row.probabilities))


def test_f01_t05():
    for row in count_laws():
        x=draws(row.law)
        assert np.equal(x,np.floor(x)).all()
        for outcome,p in zip(row.outcomes,row.probabilities):
            same=x==outcome
            if row.outcomes.ndim==2: same=same.all(-1)
            frequency(same,p)
        if row.outcomes.ndim==2:
            assert (x>=0).all()
            np.testing.assert_array_equal(x.sum(-1),np.full(N,5))
        elif row.oracle is not None:
            lo,hi=row.oracle.support()
            assert ((x>=lo)&(x<=hi)).all()
        else:
            assert (x>=0).all()


def test_f01_t06():
    for law,logpdf,mean,cov,kind in vector_laws():
        x=np.stack([mean+.2,mean-np.arange(1,len(mean)+1)*.3])
        close(law.log_prob(jnp.array(x)),logpdf(x))
    a=np.array([1.4,2.7,3.2]); x=np.array([[.2,.3,.5],[.4,.35,.25]])
    close(dist.Dirichlet(jnp.array(a)).log_prob(jnp.array(x)),stats.dirichlet(a).logpdf(x.T))
    loc=np.array([[.3,-.4],[.7,.2]]); col=np.array([[.8,0],[.2,1.1]])
    law=dist.MatrixNormal(jnp.array(loc),jnp.array(FACTOR),jnp.array(col))
    x=loc+np.array([[.2,.4],[-.1,.6]])
    close(law.log_prob(jnp.array(x)),stats.matrix_normal(loc,COV,col@col.T).logpdf(x))
    x=np.array([[1.8,.3],[.3,1.1]]); chol=np.linalg.cholesky(x)
    for law,oracle,is_factor,is_inverse in matrix_laws():
        close(law.log_prob(jnp.array(chol if is_factor else x)),oracle.logpdf(x)+(cholesky_jacobian(chol) if is_factor else 0))
    for eta in [None,2.3]:
        kwargs={} if eta is None else dict(concentration=eta)
        e=1. if eta is None else eta
        r=np.array([[1.,.2,-.15],[.2,1.,.3],[-.15,.3,1.]])
        l=np.linalg.cholesky(r)
        close(dist.LKJ(3,**kwargs).log_prob(jnp.array(r)),lkj_density(r,e))
        # On a 3x3 factor, d(r12,r13,r23)/d(l21,l31,l32) = l22.
        close(dist.LKJCholesky(3,**kwargs).log_prob(jnp.array(l)),lkj_density(r,e)+np.log(l[1,1]))


def test_f01_t07():
    for law,logpdf,mean,cov,kind in vector_laws():
        x=draws(law)
        if kind == "student":
            for v in [np.array([1.,0.]),np.array([1.,-1.])]:
                check_cdf_samples(x@v,stats.t(7,MEAN@v,np.sqrt(v@COV@v)).cdf)
            z=linalg.solve_triangular(FACTOR,(x-MEAN).T,lower=True).T
            check_cdf_samples((z*z).sum(-1)/2,stats.f(2,7).cdf)
        else: gaussian_samples(x,mean,cov)
    a=np.array([1.4,2.7,3.2]); x=draws(dist.Dirichlet(jnp.array(a)))
    close(x.sum(-1),np.ones(N)); assert (x>0).all()
    for i in range(3):check_cdf_samples(x[:,i],stats.beta(a[i],a.sum()-a[i]).cdf)
    col=np.array([[.8,0],[.2,1.1]]); loc=np.array([[.3,-.4],[.7,.2]])
    x=draws(dist.MatrixNormal(jnp.array(loc),jnp.array(FACTOR),jnp.array(col)))
    gaussian_samples(x.reshape(N,4),loc.reshape(4),np.kron(COV,col@col.T))
    for law,oracle,is_factor,is_inverse in matrix_laws():
        x=draws(law)
        if is_factor:
            close(np.triu(x,1),0); assert (np.diagonal(x,axis1=-2,axis2=-1)>0).all()
            x=x@x.swapaxes(-1,-2)
        close(x,x.swapaxes(-1,-2)); assert (np.linalg.eigvalsh(x)>0).all()
        # Every quadratic projection has a known one-dimensional law; cross
        # projections also exercise the off-diagonal scale, not only diagonals.
        for v in [np.array([1.,0.]),np.array([0.,1.]),np.array([1.,-1.])]:
            q=np.einsum('i,nij,j->n',v,x,v); s=v@COV@v
            ref=stats.invgamma((8-2+1)/2,scale=s/2) if is_inverse else stats.chi2(8,scale=s)
            check_cdf_samples(q,ref.cdf)
    for cls in [dist.LKJ,dist.LKJCholesky]:
        for eta in [None,2.3]:
            kwargs={} if eta is None else dict(concentration=eta)
            e=1. if eta is None else eta
            x=draws(cls(3,**kwargs))
            if cls is dist.LKJCholesky:
                close(np.triu(x,1),0); assert (np.diagonal(x,axis1=-2,axis2=-1)>0).all()
                x=x@x.swapaxes(-1,-2)
            close(np.diagonal(x,axis1=-2,axis2=-1),1)
            close(x,x.swapaxes(-1,-2)); assert (np.linalg.eigvalsh(x)>0).all()
            for i,j in [(0,1),(0,2),(1,2)]:
                check_cdf_samples((x[:,i,j]+1)/2,stats.beta(e+.5,e+.5).cdf)
            # Joint dependence: a partial correlation has Beta(eta,eta).
            partial=(x[:,1,2]-x[:,0,1]*x[:,0,2])/np.sqrt((1-x[:,0,1]**2)*(1-x[:,0,2]**2))
            check_cdf_samples((partial+1)/2,stats.beta(e,e).cdf)


def test_f01_t08():
    law=dist.VonMises(.4,1.7,validate_args=False)
    angles=jnp.array([-2.1,-.2,.7,2.4])
    close(law.log_prob(angles),stats.vonmises.logpdf(angles,1.7,loc=.4))
    close(law.log_prob(angles+2*np.pi),stats.vonmises.logpdf(angles,1.7,loc=.4))
    x=draws(law); assert ((x>=-np.pi)&(x<=np.pi)).all()
    check_cdf_samples(x,lambda v:stats.vonmises.cdf(v,1.7,loc=.4)-stats.vonmises.cdf(-np.pi,1.7,loc=.4))
    phi,psi=.3,-.5; k1,k2=1.4,1.8; corr=.6
    grid=np.linspace(-np.pi,np.pi,256,endpoint=False)
    u,v=np.meshgrid(grid,grid,indexing='ij')
    unnormalized=np.exp(k1*np.cos(u-phi)+k2*np.cos(v-psi)+corr*np.sin(u-phi)*np.sin(v-psi))
    norm=unnormalized.mean()*(2*np.pi)**2
    points=np.array([[.1,.2],[-1.2,1.7],[2.4,-.8]])
    ref=lambda x: np.exp(k1*np.cos(x[...,0]-phi)+k2*np.cos(x[...,1]-psi)+corr*np.sin(x[...,0]-phi)*np.sin(x[...,1]-psi))/norm
    for kwargs in [dict(correlation=corr),dict(weighted_correlation=corr/np.sqrt(k1*k2))]:
        base=dist.SineBivariateVonMises(phi,psi,k1,k2,**kwargs)
        close(base.log_prob(jnp.array(points)),np.log(ref(points)))
        weights=np.array([.35,-.2])
        for law,skew in [(base,np.zeros(2)),(dist.SineSkewed(base,jnp.array(weights)),weights)]:
            expected=ref(points)*(1+np.sin(points-np.array([phi,psi]))@skew)
            close(law.log_prob(jnp.array(points)),np.log(expected))
            x=draws(law,n=65536); assert ((x>=-np.pi)&(x<=np.pi)).all()
            # Quadrature for half-circle regions; shifted midpoint grid avoids
            # a boundary-cell bias and converges spectrally for these smooth laws.
            mid=grid+np.pi/256
            a,b=np.meshgrid(mid,mid,indexing='ij'); pts=np.stack([a,b],-1)
            mass=ref(pts)*(1+np.sin(pts-np.array([phi,psi]))@skew)*(2*np.pi/256)**2
            for i in range(2):
                mask=pts[...,i]>0
                frequency(x[:,i]>0,mass[mask].sum())
            frequency((x[:,0]>0)&(x[:,1]>0),mass[(a>0)&(b>0)].sum())
            # The sine-interaction sign event carries the dependence: its mass is
            # 0.587 here against 0.500 for independent angles (and 0.543 at half
            # the correlation), far beyond the 65536-draw margin of 0.015.
            same=np.sin(pts[...,0]-phi)*np.sin(pts[...,1]-psi)>0
            frequency(np.sin(x[:,0]-phi)*np.sin(x[:,1]-psi)>0,mass[same].sum())
    for dimension in [2,3]:
        mu=np.array([.6,-.3,.4][:dimension]); law=dist.ProjectedNormal(jnp.array(mu))
        points=np.array([mu/np.linalg.norm(mu),np.eye(dimension)[0]])
        def density(direction):
            return integrate.quad(lambda r:r**(dimension-1)*stats.multivariate_normal.pdf(r*direction,mu,np.eye(dimension)),0,np.inf,epsabs=1e-12)[0]
        close(law.log_prob(jnp.array(points)),np.log([density(p) for p in points]))
        x=draws(law); close(np.linalg.norm(x,axis=-1),1)
        rng=np.random.default_rng(410)
        z=rng.normal(size=(262144,dimension))+mu; z/=np.linalg.norm(z,axis=-1,keepdims=True)
        for i in range(dimension):
            error=stats.ks_2samp(x[:,i],z[:,i]).statistic
            bound=np.sqrt(np.log(4/ALPHA)/(2*N))+np.sqrt(np.log(4/ALPHA)/(2*len(z)))
            assert error<bound


def test_f01_t09():
    mu=np.array([.4,-.2,.7,.3,-.5]); law=dist.ProjectedNormal(jnp.array(mu))
    x=draws(law); close(np.linalg.norm(x,axis=-1),1)
    for i in range(len(mu)):frequency(x[:,i]>0,stats.norm.cdf(mu[i]))
    with pytest.raises(NotImplementedError):read_array(law.log_prob(jnp.array(x[:2])))
    law=dist.VonMises(.4,1.7,validate_args=True)
    good=.2; bad=good+2*np.pi
    with pytest.warns(UserWarning):result=read_array(law.log_prob(jnp.array([good,bad])))
    close(result[0],stats.vonmises.logpdf(good,1.7,loc=.4)); assert np.isneginf(result[1])


def test_f01_t10():
    for temp in [.4,1.8]:
        for kwargs in [dict(probs=.3),dict(logits=np.log(.3/.7))]:
            law=dist.RelaxedBernoulli(temp,**kwargs)
            x=np.array([.08,.3,.74,.94]); logit=special.logit(x)
            ref=stats.logistic.logpdf(temp*logit,loc=special.logit(.3))+np.log(temp)-np.log(x)-np.log1p(-x)
            close(law.log_prob(jnp.array(x)),ref)
            s=draws(law); assert ((s>0)&(s<1)).all()
            check_cdf_samples(s,lambda v:special.expit(temp*special.logit(v)-special.logit(.3)))
    for event_dim in [0,1]:
        point=jnp.array([.3,-.7]); weight=jnp.array([-.4,.2]) if event_dim==0 else -.4
        law=dist.Delta(point,log_density=weight,event_dim=event_dim)
        close(draws(law),np.broadcast_to(point,(N,2)))
        close(law.log_prob(point),weight)
        assert np.isneginf(read_array(law.log_prob(point+1))).all()


def test_f01_t11():
    loc=np.array([[-.4],[.6]]); scale=np.array([[.7,1.2,1.8]])
    law=dist.Normal(jnp.array(loc),jnp.array(scale))
    assert law.batch_shape==(2,3) and law.event_shape==()
    x=draws(law,n=1024); assert x.shape==(1024,2,3)
    close(law.log_prob(jnp.array(x[:4])),stats.norm.logpdf(x[:4],loc,scale))
    for i in range(2):
        for j in range(3):check_cdf_samples(x[:,i,j],stats.norm(loc[i,0],scale[0,j]).cdf)
    expanded=law.expand((4,2,3)); x=draws(expanded,n=2048)
    assert expanded.batch_shape==(4,2,3) and x.shape==(2048,4,2,3)
    close(expanded.log_prob(jnp.array(x[:2])),stats.norm.logpdf(x[:2],loc,scale))
    gaussian_samples(x.reshape(2048,-1),np.broadcast_to(loc,(4,2,3)).reshape(-1),np.diag(np.broadcast_to(scale,(4,2,3)).reshape(-1)**2))
    for rank in [1,2]:
        joint=law.to_event(rank); x=draws(joint,n=2048)
        assert joint.batch_shape==law.batch_shape[:-rank] and joint.event_shape==law.batch_shape[-rank:]
        close(joint.log_prob(jnp.array(x[:3])),stats.norm.logpdf(x[:3],loc,scale).sum(axis=tuple(range(-rank,0))))
        gaussian_samples(x.reshape(2048,-1),np.broadcast_to(loc,(2,3)).reshape(-1),np.diag(np.broadcast_to(scale,(2,3)).reshape(-1)**2))
    vector=dist.MultivariateNormal(jnp.array(MEAN),jnp.array(COV)).expand((3,))
    x=draws(vector,n=1024); assert x.shape==(1024,3,2)
    close(vector.log_prob(jnp.array(x[:3])),stats.multivariate_normal(MEAN,COV).logpdf(x[:3]))


def test_f01_t12():
    law=dist.Normal(jnp.zeros((2,3)),1.)
    assert draws(law.expand((4,2,3)),n=2).shape==(2,4,2,3)
    assert draws(law.to_event(2),n=2).shape==(2,2,3)
    with pytest.raises(ValueError):read_array(law.expand((2,4)).sample(jax.random.key(0)))
    with pytest.raises(ValueError):read_array(law.to_event(3).log_prob(jnp.zeros((2,3))))


def test_f01_t13():
    names={'Normal','Uniform','Exponential','Cauchy','HalfCauchy','Logistic','Laplace','Beta','Weibull'}
    for row in scalar_laws():
        if row.label not in names:continue
        q=np.array([.03,.17,.42,.73,.96]); x=row.oracle.ppf(q)
        close(row.law.cdf(jnp.array(x)),q)
        if row.label!="Weibull":close(row.law.icdf(jnp.array(q)),x)


def test_f01_t14():
    from velnora.distributions import kl_divergence
    pairs=[
        (dist.Normal(.2,.7),dist.Normal(-.6,1.4),stats.norm(.2,.7),stats.norm(-.6,1.4)),
        (dist.Beta(2.3,4.1),dist.Beta(3.7,1.6),stats.beta(2.3,4.1),stats.beta(3.7,1.6)),
        (dist.Gamma(2.3,1.4),dist.Gamma(3.7,.8),stats.gamma(2.3,scale=1/1.4),stats.gamma(3.7,scale=1/.8)),
    ]
    for a,b,oa,ob in pairs:
        for p,q,op,oq in [(a,b,oa,ob),(b,a,ob,oa)]:
            lo,hi=op.support()
            expected=integrate.quad(lambda x:np.exp(op.logpdf(x))*(op.logpdf(x)-oq.logpdf(x)),lo,hi,epsabs=1e-10)[0]
            close(kl_divergence(p,q),expected)
    a=np.array([1.3,2.7,4.1]);b=np.array([2.5,3.2,.9])
    for x,y in [(a,b),(b,a)]:
        expected=special.gammaln(x.sum())-special.gammaln(y.sum())+np.sum(special.gammaln(y)-special.gammaln(x)+(x-y)*(special.digamma(x)-special.digamma(x.sum())))
        close(kl_divergence(dist.Dirichlet(jnp.array(x)),dist.Dirichlet(jnp.array(y))),expected)
    p=np.array([.2,.3,.5]);q=np.array([.6,.15,.25])
    for x,y in [(p,q),(q,p)]:close(kl_divergence(dist.Categorical(probs=jnp.array(x)),dist.Categorical(probs=jnp.array(y))),special.rel_entr(x,y).sum())
    for ma,ca,mb,cb in [(MEAN,COV,-MEAN,np.array([[.9,-.2],[-.2,1.7]])),(-MEAN,np.array([[.9,-.2],[-.2,1.7]]),MEAN,COV)]:
        delta=mb-ma
        expected=.5*(np.trace(np.linalg.solve(cb,ca))+delta@np.linalg.solve(cb,delta)-2+np.linalg.slogdet(cb)[1]-np.linalg.slogdet(ca)[1])
        close(kl_divergence(dist.MultivariateNormal(jnp.array(ma),jnp.array(ca)),dist.MultivariateNormal(jnp.array(mb),jnp.array(cb))),expected)
    a=stats.weibull_min(2.4,scale=1.3);b=stats.gamma(3.2,scale=1/1.7)
    expected=integrate.quad(lambda x:a.pdf(x)*(a.logpdf(x)-b.logpdf(x)),0,np.inf,epsabs=1e-10)[0]
    close(kl_divergence(dist.Weibull(1.3,2.4),dist.Gamma(3.2,1.7)),expected)
    close(kl_divergence(dist.Normal(jnp.array([.2,-.6]),jnp.array([.7,1.4])),dist.Normal(0.,1.)),.5*(np.array([.7,1.4])**2+np.array([.2,-.6])**2-1-2*np.log([.7,1.4])))
    with pytest.raises(NotImplementedError):kl_divergence(dist.Normal(),dist.Poisson(2.))


def test_f01_t15():
    from F01_helpers import validation_specs
    for cls,kwargs,invalid in validation_specs():
        # The successful operation rules out a universal rejector. Capture covers
        # construction and completed sampling so delayed validation is accepted.
        good=cls(**kwargs,validate_args=True)
        assert np.isfinite(draws(good,n=2)).all()
        for field,values in invalid.items():
            for value in values:
                bad=dict(kwargs);bad[field]=jnp.asarray(value)
                with pytest.raises(ValueError):
                    draws(cls(**bad,validate_args=True),n=2)
    for cls in [dist.LKJ,dist.LKJCholesky]:
        assert draws(cls(2,validate_args=True),n=2).shape==(2,2,2)
        with pytest.raises(ValueError):draws(cls(1,validate_args=True),n=2)
    # Probability endpoints which the PRD includes must remain usable.
    for cls in [dist.Bernoulli,dist.Binomial]:
        for p in [0.,1.]:
            law=cls(probs=p,**({} if cls is dist.Bernoulli else dict(total_count=3)),validate_args=True)
            close(draws(law,n=8),p*(1 if cls is dist.Bernoulli else 3))
    close(draws(dist.Geometric(probs=1.,validate_args=True),n=8),0)
    close(draws(dist.Poisson(0.,validate_args=True),n=8),0)
    close(dist.NegativeBinomial(2.4,probs=0.,validate_args=True).log_prob(0),0)
    close(dist.Categorical(logits=jnp.array([-np.inf,0.]),validate_args=True).log_prob(1),0)


def test_f01_t16():
    from velnora import validation_enabled
    with validation_enabled():
        # Real-valued, unconstrained laws have no finite out-of-support value.
        rows=[]
        for row in scalar_laws():
            lo,hi=row.oracle.support()
            if np.isfinite(lo):rows.append((row.law,row.oracle.ppf(.4),lo-1))
            elif np.isfinite(hi):rows.append((row.law,row.oracle.ppf(.4),hi+1))
        for row in count_laws():
            if row.outcomes.ndim==1:rows.append((row.law,row.outcomes[1],row.outcomes.min()-1))
            else:rows.append((row.law,row.outcomes[1],np.array([-1,3,3])))
        rows += [
            (dist.Dirichlet(jnp.array([2.,3.,4.])),np.array([.2,.3,.5]),np.array([.2,.3,.3])),
            (dist.Wishart(8.,scale_matrix=jnp.array(COV)),np.eye(2),np.diag([-1.,1.])),
            (dist.InverseWishart(8.,scale_matrix=jnp.array(COV)),np.eye(2),np.diag([-1.,1.])),
            (dist.WishartCholesky(8.,scale_matrix=jnp.array(COV)),np.eye(2),np.diag([-1.,1.])),
            (dist.InverseWishartCholesky(8.,scale_matrix=jnp.array(COV)),np.eye(2),np.diag([-1.,1.])),
            (dist.LKJ(3),np.eye(3),np.diag([1.,1.,2.])),
            (dist.LKJCholesky(3),np.eye(3),np.diag([1.,1.,2.])),
            (dist.ZeroSumNormal(1.3,(3,)),np.array([.2,-.3,.1]),np.array([.2,-.3,.7])),
            (dist.VonMises(.2,1.3),.4,4.),
            (dist.SineBivariateVonMises(.2,-.3,1.3,1.7,correlation=.3),np.array([.3,.4]),np.array([4.,.4])),
            (dist.RelaxedBernoulli(.7,probs=.3),.4,-.2),
        ]
        for law,good,bad in rows:
            points=jnp.array(np.stack([good,bad]))
            with pytest.warns(UserWarning):result=read_array(law.log_prob(points))
            assert np.isfinite(result[0]).all(),type(law)
            assert np.isneginf(result[1]).all(),type(law)


def test_f01_t17():
    law=dist.Normal(jnp.array([.2,-.4]),jnp.array([.7,1.3])).to_event(1)
    @jax.jit
    def through(d,x):return d,d.log_prob(x),d.sample(jax.random.key(23),(N,))
    returned,lp,s=through(law,jnp.array([.6,-.2]))
    assert returned.batch_shape==() and returned.event_shape==(2,) and s.shape==(N,2)
    close(lp,stats.norm.logpdf([.6,-.2],[.2,-.4],[.7,1.3]).sum())
    gaussian_samples(read_array(s),np.array([.2,-.4]),np.diag(np.array([.7,1.3])**2))
    close(returned.log_prob(jnp.array([-.3,.7])),stats.norm.logpdf([-.3,.7],[.2,-.4],[.7,1.3]).sum())
    mapped=jax.vmap(lambda m:dist.Normal(m,1.3))(jnp.array([.2,-.7,.9]))
    def observe(d):
        assert d.batch_shape==() and d.event_shape==()
        return d.log_prob(.4),d.sample(jax.random.key(81),(N,))
    logp,samples=jax.vmap(observe)(mapped)
    close(logp,stats.norm.logpdf(.4,[.2,-.7,.9],1.3))
    s=read_array(samples).T
    for i,m in enumerate([.2,-.7,.9]):check_cdf_samples(s[:,i],stats.norm(m,1.3).cdf)
    # Independent finite differences exercise continuous parameter derivatives
    # without comparing the product's autodiff to its own finite differences.
    specs=[
        (lambda p:dist.Normal(p[0],p[1]),lambda p:stats.norm(p[0],p[1]),np.array([.2,1.3]),.7),
        (lambda p:dist.Gamma(p[0],p[1]),lambda p:stats.gamma(p[0],scale=1/p[1]),np.array([2.3,1.7]),.8),
        (lambda p:dist.Beta(p[0],p[1]),lambda p:stats.beta(*p),np.array([2.3,4.1]),.4),
        (lambda p:dist.StudentT(p[0],p[1],p[2]),lambda p:stats.t(*p),np.array([6.3,.2,1.3]),.7),
    ]
    for make,oracle,p,x in specs:
        expected=[]
        for i in range(len(p)):
            h=1e-4;delta=np.eye(len(p))[i]*h
            expected.append((oracle(p+delta).logpdf(x)-oracle(p-delta).logpdf(x))/(2*h))
        close(jax.jit(jax.grad(lambda p:make(p).log_prob(x)))(jnp.array(p)),expected)


def test_f01_t18():
    # First or second moments have nonzero derivatives for every supplied
    # parameter; independent SciPy moments determine the expectation derivatives.
    specs=[
        (lambda p:dist.Normal(p[0],p[1]),lambda p:stats.norm(*p),np.array([.2,1.3])),
        (lambda p:dist.Gamma(p[0],p[1]),lambda p:stats.gamma(p[0],scale=1/p[1]),np.array([3.3,1.7])),
        (lambda p:dist.Beta(p[0],p[1]),lambda p:stats.beta(*p),np.array([2.3,4.1])),
        (lambda p:dist.StudentT(p[0],p[1],p[2]),lambda p:stats.t(*p),np.array([7.3,.2,1.3])),
    ]
    for index,(make,oracle,p) in enumerate(specs):
        power=2 if index in [0,3] else 1
        def expectation(p):
            return oracle(p).moment(power)
        expected=[]
        for i in range(len(p)):
            delta=np.eye(len(p))[i]*1e-3
            expected.append((expectation(p+delta)-expectation(p-delta))/2e-3)
        # Independent replications estimate uncertainty, rather than requiring
        # reference noise or a particular pathwise estimator. 12 standard errors
        # plus a 0.005 integration/Monte Carlo allowance has a large reserve.
        grads=[]
        gradient=jax.jit(jax.grad(lambda p,key:(make(p).sample(key,(8192,))**power).mean(),argnums=0))
        for key in jax.random.split(jax.random.key(90),16):
            grads.append(read_array(gradient(jnp.array(p),key)))
        grads=np.array(grads); error=np.abs(grads.mean(0)-expected)
        assert np.all(error<12*grads.std(0,ddof=1)/4+.005),(error,expected)
        assert np.all(np.abs(expected)>.005)


def test_f01_t19():
    loc=.4;scale=1.3
    for cls,param,values in [(dist.AsymmetricLaplace,'asymmetry',[.6,1.7]),(dist.AsymmetricLaplaceQuantile,'quantile',[.2,.73])]:
        for v in values:
            left,right=(scale*v,scale/v) if param=='asymmetry' else (scale/(1-v),scale/v)
            law=cls(loc,scale,**{param:v})
            x=np.array([loc-2.1,loc-.2,loc,loc+.2,loc+1.7])
            expected=np.exp(-np.abs(x-loc)/np.where(x<loc,left,right))/(left+right)
            close(law.log_prob(jnp.array(x)),np.log(expected))
            s=draws(law)
            cdf=lambda x:np.where(x<loc,left/(left+right)*np.exp(np.minimum(x-loc,0)/left),1-right/(left+right)*np.exp(-np.maximum(x-loc,0)/right))
            check_cdf_samples(s,cdf)
            frequency(s<loc,left/(left+right))


def test_f01_t20():
    scale=1.3;steps=4
    law=dist.GaussianRandomWalk(scale,steps)
    x=draws(law); assert x.shape==(N,steps)
    increments=np.diff(x,axis=-1,prepend=0)
    gaussian_samples(increments,np.zeros(steps),scale**2*np.eye(steps))
    path=np.array([.3,-.2,.7,.4])
    close(law.log_prob(jnp.array(path)),stats.norm.logpdf(np.diff(path,prepend=0),scale=scale).sum())
    transition=np.array([[.7,.2],[-.1,.6]])
    for kwargs in [dict(covariance_matrix=jnp.array(COV)),dict(precision_matrix=jnp.array(np.linalg.inv(COV))),dict(scale_tril=jnp.array(FACTOR))]:
        for initial in [None,np.array([.8,-.4])]:
            init=np.zeros(2) if initial is None else initial
            args={} if initial is None else dict(initial_value=jnp.array(initial))
            law=dist.GaussianStateSpace(steps,jnp.array(transition),**kwargs,**args)
            x=draws(law);assert x.shape==(N,steps,2)
            prev=np.concatenate([np.broadcast_to(init,(N,1,2)),x[:,:-1]],axis=1)
            innovations=x-prev@transition.T
            gaussian_samples(innovations.reshape(N,-1),np.zeros(steps*2),np.kron(np.eye(steps),COV))
            path=np.array([[.3,-.2],[.6,.4],[-.1,.7],[.5,-.3]])
            prev=np.concatenate([init[None],path[:-1]])
            close(law.log_prob(jnp.array(path)),stats.multivariate_normal(np.zeros(2),COV).logpdf(path-prev@transition.T).sum())
    for shape in [(4,),(3,4)]:
        law=dist.ZeroSumNormal(scale,shape);x=draws(law)
        for axis in range(-len(shape),0):close(x.sum(axis=axis),0)
        projection=np.array([[1.]])
        for size in shape:projection=np.kron(projection,np.eye(size)-np.ones((size,size))/size)
        eigenvalues,basis=np.linalg.eigh(projection);basis=basis[:,eigenvalues>.5]
        coords=x.reshape(N,-1)@basis
        gaussian_samples(coords,np.zeros(basis.shape[-1]),scale**2*np.eye(basis.shape[-1]))
        point=(np.arange(np.prod(shape)).reshape(shape)/7)
        point=(projection@point.reshape(-1)).reshape(shape)
        close(law.log_prob(jnp.array(point)),stats.multivariate_normal(np.zeros(basis.shape[-1]),scale**2*np.eye(basis.shape[-1])).logpdf(point.reshape(-1)@basis))


def test_f01_t21():
    time=np.array([0.,.13,.48,1.2]);dim=2
    drift=lambda y,t:.2-.35*y+.1*t
    diffusion=lambda y,t:jnp.array([.7,1.1])+t*.1
    initial=dist.Normal(jnp.array([.3,-.2]),jnp.array([.8,1.2])).to_event(1)
    law=dist.EulerMaruyama(jnp.array(time),lambda y,t:(drift(y,t),diffusion(y,t)),initial)
    x=draws(law);assert x.shape==(N,len(time),dim)
    gaussian_samples(x[:,0],np.array([.3,-.2]),np.diag([.8**2,1.2**2]))
    z=[]
    for i,dt in enumerate(np.diff(time)):
        z.append((x[:,i+1]-x[:,i]-dt*drift(x[:,i],time[i]))/(np.sqrt(dt)*np.array([.7+time[i]*.1,1.1+time[i]*.1])))
    gaussian_samples(np.stack(z,axis=1).reshape(N,-1),np.zeros(6),np.eye(6))
    point=np.array([[.3,-.2],[.4,.1],[-.1,.2],[.6,.5]])
    expected=stats.norm.logpdf(point[0],[.3,-.2],[.8,1.2]).sum()
    for i,dt in enumerate(np.diff(time)):
        expected+=stats.norm.logpdf(point[i+1],point[i]+dt*drift(point[i],time[i]),np.sqrt(dt)*np.array([.7+time[i]*.1,1.1+time[i]*.1])).sum()
    close(law.log_prob(jnp.array(point)),expected)
    row=np.array([1.8,.3,.1,.3]);cov=linalg.circulant(row);mean=np.array([.2,-.3,.7,.1])
    for kwargs in [dict(covariance_row=jnp.array(row)),dict(covariance_rfft=jnp.array(np.fft.rfft(row).real))]:
        law=dist.CirculantNormal(jnp.array(mean),**kwargs)
        point=np.array([.1,.4,-.2,.8])
        close(law.log_prob(jnp.array(point)),stats.multivariate_normal(mean,cov).logpdf(point))
        gaussian_samples(draws(law),mean,cov)


def test_f01_t22():
    laws=[
        (dist.Bernoulli(probs=jnp.array([.2,.7])),np.arange(2)),
        (dist.Categorical(probs=jnp.array([[.2,.3,.5],[.4,.5,.1]])),np.arange(3)),
        (dist.OrderedLogistic(jnp.array([.2,-.5]),jnp.array([-.4,.6,1.2])),np.arange(4)),
        (dist.Binomial(jnp.array([4,4]),probs=jnp.array([.2,.7])),np.arange(5)),
        (dist.BetaBinomial(2.3,4.7,jnp.array([4,4])),np.arange(5)),
        (dist.DiscreteUniform(jnp.array([-2,-2]),jnp.array([3,3])),np.arange(-2,4)),
    ]
    for law,expected in laws:
        for expand in [False,True]:
            values=read_array(law.enumerate_support(expand=expand))
            assert values.shape==(len(expected),2 if expand else 1)
            # Enumeration order is not a probability outcome.
            for column in values.T:np.testing.assert_array_equal(np.sort(column),expected)
    bad=[dist.Binomial(jnp.array([3,4]),probs=.3),dist.BetaBinomial(2.,3.,jnp.array([3,4])),dist.DiscreteUniform(jnp.array([0,1]),jnp.array([3,4])),dist.DiscreteUniform(jnp.array([0,0]),jnp.array([3,4]))]
    for law in bad:
        with pytest.raises(NotImplementedError):read_array(law.enumerate_support())


def test_f01_t23():
    excluded={'Cauchy','HalfCauchy','Gompertz','Levy'}
    for row in scalar_laws():
        if row.label in excluded:continue
        check_moments(row.law,row.oracle.mean(),row.oracle.var())
    for row in count_laws():
        law=row.law
        if row.kind in {"Categorical","OrderedLogistic"}:continue
        if row.kind=="BetaNegativeBinomial":
            a,b,n=2.3,5.7,2.4
            mean=n*a/(b-1);var=n*a*(a+b-1)*(n+b-1)/((b-2)*(b-1)**2)
        elif row.kind=="DirichletMultinomial":
            a=np.array([1.3,2.4,3.7]);p=a/a.sum();mean=5*p;var=5*p*(1-p)*(5+a.sum())/(1+a.sum())
        elif row.outcomes.ndim==2:mean,var=row.oracle.mean(),np.diag(row.oracle.cov())
        else:mean,var=row.oracle.mean(),row.oracle.var()
        check_moments(law,mean,var)
    a=np.array([1.4,2.7,3.2]);p=a/a.sum();law=dist.Dirichlet(jnp.array(a))
    check_moments(law,p,p*(1-p)/(a.sum()+1))
    for law,logpdf,mean,cov,kind in vector_laws():
        if kind == "car":continue
        check_moments(law,mean,np.diag(cov))
    for cls in [dist.Wishart,dist.InverseWishart]:
        law=cls(8.,scale_matrix=jnp.array(COV))
        oracle=(stats.wishart if cls is dist.Wishart else stats.invwishart)(8,COV)
        check_moments(law,oracle.mean(),oracle.var())
    law=dist.WishartCholesky(8.,scale_matrix=jnp.array(COV))
    # Independent Bartlett-factor moments: standard lower entries are normal,
    # and diagonal entries follow chi laws with decreasing degrees of freedom.
    chi_mean=np.array([stats.chi(8-i).mean() for i in range(2)])
    chi_var=np.array([stats.chi(8-i).var() for i in range(2)])
    expected_mean=FACTOR@np.diag(chi_mean)
    expected_var=np.zeros((2,2))
    for i in range(2):
        for j in range(i+1):expected_var[i,j]=FACTOR[i,j]**2*chi_var[j]+np.sum(FACTOR[i,j+1:i+1]**2)
    check_moments(law,expected_mean,expected_var)
    law=dist.GaussianRandomWalk(1.3,4);check_moments(law,np.zeros(4),1.3**2*np.arange(1,5))
    transition=np.array([[.7,.2],[-.1,.6]]);init=np.array([.8,-.4])
    law=dist.GaussianStateSpace(4,jnp.array(transition),covariance_matrix=jnp.array(COV),initial_value=jnp.array(init))
    means=[];variances=[];mean=init;cov=np.zeros((2,2))
    for _ in range(4):
        mean=transition@mean;cov=transition@cov@transition.T+COV;means.append(mean);variances.append(np.diag(cov))
    check_moments(law,means,variances)
    row=np.array([1.8,.3,.1,.3]);mean=np.array([.2,-.3,.7,.1])
    law=dist.CirculantNormal(jnp.array(mean),covariance_row=jnp.array(row))
    check_moments(law,mean,np.full(4,1.8))
    for shape in [(4,),(3,4)]:
        law=dist.ZeroSumNormal(1.3,shape)
        check_moments(law,np.zeros(shape),np.full(shape,1.3**2*np.prod([1-1/s for s in shape])))
    # Broadcasting is part of moments, not just scalar correctness.
    law=dist.Normal(jnp.array([[.2],[-.4]]),jnp.array([[.7,1.3,2.1]]))
    check_moments(law,np.array([[.2],[-.4]]),np.array([[.7,1.3,2.1]])**2)


def test_f01_t24():
    names={'Normal','StudentT','Laplace','Logistic','Uniform','LogUniform','LogNormal','Exponential','Gamma','InverseGamma','Beta','Pareto','Weibull','Cauchy','Levy'}
    for row in scalar_laws():
        if row.label in names:close(row.law.entropy(),row.oracle.entropy())
    for row in count_laws():
        if row.kind in {"Bernoulli","Categorical","DiscreteUniform","Geometric"}:
            close(row.law.entropy(),row.oracle.entropy())
    a=np.array([1.4,2.7,3.2]);close(dist.Dirichlet(jnp.array(a)).entropy(),stats.dirichlet(a).entropy())
    for law,logpdf,mean,cov,kind in vector_laws():
        if kind == "normal":
            close(law.entropy(),stats.multivariate_normal(mean,cov).entropy())
    close(dist.Wishart(8.,scale_matrix=jnp.array(COV)).entropy(),stats.wishart(8,COV).entropy())
    row=np.array([1.8,.3,.1,.3]);mean=np.array([.2,-.3,.7,.1])
    close(dist.CirculantNormal(jnp.array(mean),covariance_row=jnp.array(row)).entropy(),stats.multivariate_normal(mean,linalg.circulant(row)).entropy())
    close(dist.Normal(jnp.array([.2,-.7]),jnp.array([.7,1.3])).entropy(),stats.norm.entropy(scale=[.7,1.3]))
    close(dist.Categorical(probs=jnp.array([[.2,.3,.5],[.6,.1,.3]])).entropy(),stats.entropy([[.2,.3,.5],[.6,.1,.3]],axis=-1))
