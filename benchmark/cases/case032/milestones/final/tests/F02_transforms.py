# feature: F02
"""Acceptance tests for support geometry and probability transformations."""
import gc
import pytest
from scipy import fft, special
from jax.example_libraries import stax
from F02_helpers import (
    jax, jnp, np, dist, close, read_array, call_public, c, t, mask,
    coordinates, numerical_jacobian, volume, verify_transform,
    lower_coordinates, correlation_coordinates, unpack_record, pack_record,
)
from velnora.distributions.flows import (
    InverseAutoregressiveTransform, BlockNeuralAutoregressiveTransform,
)
from velnora.nn import AutoregressiveNN, BlockNeuralAutoregressiveNN


@pytest.fixture(autouse=True)
def release_f02_cache():
    yield
    jax.clear_caches()
    gc.collect()


def test_f02_t01():
    x = [-np.inf, -2., -1., 0., .5, 1., 2., np.inf, np.nan]
    rows = [
        (c.boolean, [0,0,0,1,0,1,0,0,0]),
        (c.real, [0,1,1,1,1,1,1,0,0]),
        (c.extended_real, [1,1,1,1,1,1,1,1,0]),
        (c.integer_interval(-1,1), [0,0,1,1,0,1,0,0,0]),
        (c.integer_greater_than(-1), [0,0,1,1,0,1,1,0,0]),
        (c.positive_integer, [0,0,0,0,0,1,1,0,0]),
        (c.nonnegative_integer, [0,0,0,1,0,1,1,0,0]),
        (c.interval(-1,1), [0,0,1,1,1,1,0,0,0]),
        (c.open_interval(-1,1), [0,0,0,1,1,0,0,0,0]),
    ]
    for domain, expected in rows:
        mask(domain, x, expected)
    # The original one-sided domains compare bounds without requiring finiteness.
    finite = [-2., -1., 0., .5, 1., 2., np.nan]
    for domain, expected in [
        (c.positive,[0,0,0,1,1,1,0]), (c.nonnegative,[0,0,1,1,1,1,0]),
        (c.greater_than(-1),[0,0,1,1,1,1,0]),
        (c.greater_than_eq(-1),[0,1,1,1,1,1,0]),
        (c.less_than(1),[1,1,1,1,0,0,0]),
    ]:
        mask(domain, finite, expected)
    mask(c.circular, [-np.pi, 0, np.pi, -3.3, 3.3, np.nan], [1,1,1,0,0,0])


def test_f02_t02():
    mask(c.real_vector, [[0,1],[np.inf,0],[1,np.nan]], [1,0,0])
    mask(c.real_matrix, [[[1,0],[0,1]],[[1,np.nan],[0,1]]], [1,0])
    mask(c.complex, [1+2j, -3j, complex(np.nan,0), complex(np.inf,0)], [1,1,0,0])
    mask(c.simplex, [[.2,.3,.5],[0,0,1],[-.1,.6,.5],[.2,.3,.4]], [1,1,0,0])
    mask(c.softmax_logits, [[0,-np.inf,2],[-np.inf]*3,[0,np.inf,2],[0,np.nan,2]], [1,0,0,0])
    # Fractional count rejection is not implemented by the original; see ledger.
    mask(c.multinomial(4), [[0,1,3],[1,1,1],[-1,2,3]], [1,0,0])
    mask(c.ordered_vector, [[-2,0,1],[1,1,2],[1,3,2]], [1,0,0])
    mask(c.positive_ordered_vector, [[.2,.5,1],[-1,.5,1],[.2,.2,1]], [1,0,0])
    mask(c.sphere, [[.6,.8],[0,0],[1,1]], [1,0,0])
    mask(c.l1_ball, [[.2,-.3],[.6,-.4],[.7,.7]], [1,1,0])
    matrices = [ [[1,0],[.3,2]], [[1,.2],[.3,2]], [[0,0],[.3,2]], [[-1,0],[.3,2]] ]
    for domain in [c.lower_cholesky,c.scaled_unit_lower_cholesky]:
        mask(domain, matrices, [1,0,0,0])
    mask(c.corr_cholesky, [[[1,0],[.6,.8]],[[1,0],[.6,1]],[[1,.1],[.6,.8]],[[1,0],[.6,-.8]]], [1,0,0,0])
    mask(c.corr_matrix, [[[1,.3],[.3,1]],[[1,2],[2,1]],[[1,.2],[.3,1]],[[2,.3],[.3,1]]], [1,0,0,0])
    matrices = [[[2,.3],[.3,1]],[[1,1],[1,1]],[[1,2],[2,1]],[[2,.1],[.3,1]]]
    mask(c.positive_definite, matrices, [1,0,0,0])
    mask(c.positive_semidefinite, matrices, [1,1,0,0])
    mask(c.zero_sum(), [[1,-2,1],[1,-1,1]], [1,0])
    mask(c.zero_sum(2), [[[1,-1],[-1,1]],[[1,-1],[2,-2]],[[1,2],[-1,-2]]], [1,0,0])


def test_f02_t03():
    scalar = [c.boolean,c.real,c.extended_real,c.complex,c.positive,c.nonnegative,
              c.interval(4,7),c.open_interval(-7,-4),c.greater_than(9),c.greater_than_eq(9),
              c.less_than(-9),c.integer_interval(4,7),c.integer_greater_than(9),
              c.positive_integer,c.nonnegative_integer,c.circular]
    vector = [c.real_vector,c.simplex,c.softmax_logits,c.multinomial(7),c.ordered_vector,
              c.positive_ordered_vector,c.sphere,c.l1_ball,c.zero_sum()]
    matrix = [c.real_matrix,c.lower_cholesky,c.scaled_unit_lower_cholesky,c.corr_cholesky,
              c.corr_matrix,c.positive_definite,c.positive_semidefinite,c.zero_sum(2)]
    for domains, shape in [(scalar,(2,3)),(vector,(2,4)),(matrix,(2,3,3))]:
        for domain in domains:
            result = call_public(domain.feasible_like, jnp.zeros(shape))
            assert result.shape == shape
            assert read_array(call_public(domain,result)).all()
    # Parameter-dependent feasibility is checked independently, not just by self-check.
    for domain, relation in [(c.interval(4,7),lambda z:(z>=4)&(z<=7)),
                             (c.greater_than(9),lambda z:z>9),
                             (c.less_than(-9),lambda z:z < -9)]:
        assert relation(read_array(call_public(domain.feasible_like,jnp.zeros((2,3))))).all()
    domain = c.cat([c.positive,c.interval(-3,-1)], dim=-1, lengths=[2,1])
    x = jnp.array([[1.,2.,-2.],[-1.,2.,0.]])
    mask(domain, x, [[1,1,1],[0,1,0]])
    z = call_public(domain.feasible_like,x)
    assert z.shape == x.shape
    assert (np.asarray(z)[:,:2] > 0).all()
    assert ((np.asarray(z)[:,2]>=-3)&(np.asarray(z)[:,2]<=-1)).all()
    mask(c.independent(domain,1),x,[1,0])
    x = jnp.ones((2,3,4)).at[1,1,2].set(-1)
    mask(c.independent(c.positive,2),x,[1,0])
    mask(c.independent(c.independent(c.positive,1),1),x,[1,0])


def test_f02_t04():
    mask(c.real, [0.,np.nan], [1,0])
    y = call_public(t.biject_to(c.positive),jnp.array([-.5,.7]))
    assert (read_array(y)>0).all()
    with pytest.raises(ValueError):
        call_public(c.dependent,jnp.array(0.))
    for domain in [c.boolean,c.integer_interval(0,3),c.softmax_logits,c.extended_real]:
        with pytest.raises(NotImplementedError):
            call_public(lambda: t.biject_to(domain)(jnp.array([.2,.3])))


def test_f02_t05():
    x = np.array([-.8,.2,1.1])
    for transform, expected in [
        (t.IdentityTransform(),x), (t.AffineTransform(.4,-1.7),.4-1.7*x),
        (t.ExpTransform(),np.exp(x)), (t.SigmoidTransform(),special.expit(x)),
        (t.SoftplusTransform(),np.logaddexp(0,x)),
    ]:
        # Scalar transforms return one volume per scalar event.
        for value, target in zip(x,expected):
            verify_transform(transform,np.array(value),expected=target)
    verify_transform(t.PowerTransform(2.3),np.array(.7),expected=.7**2.3)
    close(call_public(t.AbsTransform(),jnp.asarray(x)),np.abs(x))
    ordered = verify_transform(t.OrderedTransform(),x)
    assert (np.diff(ordered)>0).all()
    y = verify_transform(t.StickBreakingTransform(),x,chart=lambda z:np.asarray(z)[:-1])
    assert (y>0).all(); close(y.sum(),1)
    y = verify_transform(t.L1BallTransform(),x)
    assert np.abs(y).sum()<1
    for cls in [t.LowerCholeskyTransform,t.SoftplusLowerCholeskyTransform,t.ScaledUnitLowerCholeskyTransform]:
        y = verify_transform(cls(),x,chart=lower_coordinates)
        close(np.triu(y,1),np.zeros_like(y)); assert (np.diag(y)>0).all()
    y = verify_transform(t.CorrCholeskyTransform(),x,chart=correlation_coordinates)
    close((y*y).sum(-1),np.ones(3)); assert (np.diag(y)>0).all()
    verify_transform(t.PermuteTransform(jnp.array([2,0,1])),x,expected=x[[2,0,1]])
    verify_transform(t.ReshapeTransform((1,3),(3,)),x,expected=x.reshape(1,3))
    verify_transform(t.ComplexTransform(),np.array([.3,-.8]),expected=.3-.8j)
    for ndims, values in [(1,x),(2,np.array([[.2,-.3],[.5,.7]]))]:
        y = verify_transform(t.ZeroSumTransform(ndims),values)
        for axis in range(-ndims,0):
            close(y.sum(axis),np.zeros(y.sum(axis).shape))


def test_f02_t06():
    x = np.array([.3,-1.2,.8,2.1])
    # Spectral row directions come from independent transforms. Observe each
    # implementation's coefficient gains and order, allowing normalization and
    # ordering choices while rejecting identity or arbitrary orthogonal maps.
    haar_basis = np.array([[1,1,1,1],[1,1,-1,-1],
                           [1,-1,0,0],[0,0,1,-1]],dtype=float)
    for transform, basis in [(t.DiscreteCosineTransform(),fft.dct(np.eye(4),type=2,axis=0)),
                              (t.HaarTransform(),haar_basis)]:
        y = verify_transform(transform,x)
        actual_basis = np.stack([read_array(call_public(transform,jnp.asarray(e)))
                                 for e in np.eye(4)],axis=1)
        actual_norm = np.linalg.norm(actual_basis,axis=1)
        assert (actual_norm>0).all()
        directions = actual_basis/actual_norm[:,None]
        basis = basis/np.linalg.norm(basis,axis=1)[:,None]
        similarities = np.abs(directions@basis.T)
        matches = similarities.argmax(axis=1)
        assert len(set(matches))==4
        close(similarities[np.arange(4),matches],np.ones(4))
        close(y,actual_basis@x)
        close(transform(jnp.asarray(2*x)),2*y)
        close(transform.log_abs_det_jacobian(jnp.asarray(x),jnp.asarray(y)),0.)
    for shape in [(5,),(6,),(2,3)]:
        values = np.linspace(-1.1,2.3,np.prod(shape)).reshape(shape)
        transform = t.RealFastFourierTransform(transform_shape=shape,transform_ndims=len(shape))
        y = verify_transform(transform,values)
        oracle = np.fft.rfftn(values)
        factor = np.vdot(oracle,y)/np.vdot(oracle,oracle)
        assert abs(factor)>0
        close(np.imag(factor),0.)
        close(y,factor*oracle)
        close(transform(jnp.asarray(2*values)),2*y)
    for size in [5,6]:
        values = np.linspace(-.7,1.3,size)
        transform = t.PackRealFastFourierCoefficientsTransform((size,))
        y = verify_transform(transform,values)
        assert y.shape == (size//2+1,)
        close(y.imag[[0]],0.)
        if size%2==0: close(y.imag[[-1]],0.)
        close(transform(jnp.asarray(2*values)),2*y)
        close(transform.log_abs_det_jacobian(jnp.asarray(values),jnp.asarray(y)),0.)


def test_f02_t07():
    x = jnp.array([-.5,.2,.8])
    compose = t.ComposeTransform([t.AffineTransform(.4,1.7),t.ExpTransform()])
    y = call_public(compose,x)
    assert y.shape == x.shape
    close(y,np.exp(.4+1.7*np.asarray(x)))
    close(compose.inv(y),x)
    close(compose.log_abs_det_jacobian(x,y),np.log(1.7)+.4+1.7*np.asarray(x))
    cat = t.CatTransform([t.ExpTransform(),t.AffineTransform(.3,-2.)],dim=-1,lengths=[2,1])
    y = call_public(cat,x)
    close(y,np.r_[np.exp(np.asarray(x[:2])),.3-2*np.asarray(x[2:])])
    close(cat.inv(y),x)
    close(cat.log_abs_det_jacobian(x,y),np.r_[np.asarray(x[:2]),np.log(2.)])
    batched = jnp.stack([x,x+.2])
    independent = t.IndependentTransform(compose,1)
    y = call_public(independent,batched)
    close(y,np.exp(.4+1.7*np.asarray(batched)))
    close(independent.inv(y),batched)
    close(independent.log_abs_det_jacobian(batched,y),
          (np.log(1.7)+.4+1.7*np.asarray(batched)).sum(-1))
    unpack = t.UnpackTransform(unpack_record,pack_record)
    flat = jnp.arange(10.).reshape(2,5)
    records = call_public(unpack,flat)
    close(records['head'],np.asarray(flat[:,0]))
    close(records['tail'],np.asarray(flat[:,1:]).reshape(2,2,2))
    single = call_public(unpack,flat[0])
    close(call_public(unpack.inv,single),flat[0])
    close(unpack.log_abs_det_jacobian(flat,records),np.zeros(2))


def test_f02_t08():
    verify_transform(t.ReshapeTransform((2,2),(4,)),np.arange(4.),expected=np.arange(4.).reshape(2,2))
    with pytest.raises(ValueError):
        call_public(lambda:t.ReshapeTransform((2,3),(4,))(jnp.arange(4.)))
    values = jnp.arange(5.)
    transform = t.UnpackTransform(unpack_record,pack_record)
    close(call_public(transform.inv,call_public(transform,values)),values)
    with pytest.raises(NotImplementedError):
        call_public(lambda:t.UnpackTransform(unpack_record).inv(unpack_record(values)))


def test_f02_t09():
    x = np.array([-.6,.2,.9])
    rows = [(c.positive,np.array(.3),coordinates),
            (c.interval(-2,3),np.array(-.7),coordinates),
            (c.ordered_vector,x,coordinates),(c.simplex,x,lambda z:np.asarray(z)[:-1]),
            (c.corr_matrix,x,correlation_coordinates),(c.corr_cholesky,x,correlation_coordinates),
            (c.positive_definite,x,lower_coordinates),(c.lower_cholesky,x,lower_coordinates),
            (c.l1_ball,x,coordinates),(c.zero_sum(),x,coordinates),
            (c.zero_sum(2),np.array([[.2,-.4],[.5,.7]]),coordinates)]
    for index, (domain, values, chart) in enumerate(rows):
        transform = call_public(t.biject_to,domain)
        y = verify_transform(transform,values,chart)
        assert read_array(call_public(domain,jnp.asarray(y))).all()
        if index == 0: assert y>0
        elif index == 1: assert -2<y<3
        elif index == 2: assert (np.diff(y)>0).all()
        elif index == 3: assert (y>0).all(); close(y.sum(),1)
        elif index == 4:
            close(y,y.T); close(np.diag(y),np.ones(3)); assert np.linalg.eigvalsh(y).min()>0
        elif index == 6:
            close(y,y.T); assert np.linalg.eigvalsh(y).min()>0
        elif index in (5, 7):
            close(np.triu(y,1),np.zeros_like(y)); assert (np.diag(y)>0).all()
            if index == 5: close((y*y).sum(-1),np.ones(3))
        elif index == 8: assert np.abs(y).sum()<1
        else:
            for axis in range(-domain.event_dim,0): close(y.sum(axis),np.zeros(y.sum(axis).shape))


def test_f02_t10():
    x = jnp.array([.2,-.6,.8])
    def network(z, offset=0.):
        previous = jnp.concatenate([jnp.zeros(1),z[:-1]])
        return .3+.2*previous, offset+jnp.array([-.3,.1,.4])+.1*previous
    for bounds in [None,(-.7,.5)]:
        kwargs = {} if bounds is None else dict(log_scale_min_clip=bounds[0],log_scale_max_clip=bounds[1])
        low,high = (-5.,3.) if bounds is None else bounds
        for offset in [0.,-10.,10.]:
            transform = InverseAutoregressiveTransform(lambda z:network(z,offset),**kwargs)
            mean,logs = network(x,offset)
            clipped = np.clip(np.asarray(logs),low,high)
            y = verify_transform(transform,x,expected=np.asarray(mean)+np.exp(clipped)*np.asarray(x))
            close(transform.log_abs_det_jacobian(x,jnp.asarray(y)),clipped.sum())
            law = dist.TransformedDistribution(dist.Normal(jnp.zeros(3),1.).to_event(1),transform)
            expected = -.5*np.sum(np.asarray(x)**2)-1.5*np.log(2*np.pi)-clipped.sum()
            close(call_public(law.log_prob,jnp.asarray(y)),expected)
    def logvolume(parameter):
        transform = InverseAutoregressiveTransform(lambda z:network(z,parameter))
        return transform.log_abs_det_jacobian(x,transform(x))
    close(jax.grad(logvolume)(.1),3.)
    close(jax.grad(logvolume)(.1),(logvolume(.10001)-logvolume(.09999))/2e-5)


def test_f02_t11():
    init,apply = BlockNeuralAutoregressiveNN(3,[3])
    params = call_public(init,jax.random.key(41),(3,))[1]
    x = jnp.array([-.3,.4,.8])
    transform = BlockNeuralAutoregressiveTransform(lambda z:apply(params,z))
    y = call_public(transform,x)
    observed = call_public(transform.log_abs_det_jacobian,x,y)
    close(observed,volume(transform,x))
    # Inverting the flow direction makes density observable without asking the
    # unsupported neural inverse to run.
    law = dist.TransformedDistribution(dist.Normal(jnp.zeros(3),1.).to_event(1),transform.inv)
    expected = -.5*np.sum(np.asarray(y)**2)-1.5*np.log(2*np.pi)+volume(transform,x)
    close(call_public(law.log_prob,x),expected)
    def objective(delta):
        shifted = jax.tree.map(lambda p:p+delta,params)
        flow = BlockNeuralAutoregressiveTransform(lambda z:apply(shifted,z))
        return flow.log_abs_det_jacobian(x,flow(x))
    close(jax.grad(objective)(0.),(objective(1e-5)-objective(-1e-5))/2e-5)


def test_f02_t12():
    x = jnp.array([-.3,.4,.8])
    permutation = np.array([2,0,1])
    for multiplicities in [[1],[1,1],[2,3]]:
        init,apply = AutoregressiveNN(3,[7],param_dims=multiplicities,
                                      permutation=jnp.asarray(permutation),skip_connections=True,
                                      nonlinearity=stax.Elu)
        params = call_public(init,jax.random.key(31),(2,3))[1]
        output = call_public(apply,params,jnp.stack([x,x+.2]))
        groups = (output,) if len(multiplicities)==1 else output
        for group, count in zip(groups,multiplicities):
            expected_shape = (2,3) if all(p==1 for p in multiplicities) else (count,2,3)
            assert group.shape == expected_shape
        active_dependency = False
        # Check caller-supplied trainable values as well as initialization, so
        # a legitimate zero initialization need not already be nonconstant.
        for supplied in [params,jax.tree.map(lambda p:p+.2,params)]:
            def flattened(z):
                result = apply(supplied,z)
                result = (result,) if len(multiplicities)==1 else result
                return jnp.concatenate([a.reshape(-1,3) for a in result],axis=0)
            jac = numerical_jacobian(flattened,x).reshape(-1,3,3)
            ordered = jac[:,permutation][:,:,permutation]
            close(np.triu(ordered),np.zeros_like(ordered))
            active_dependency |= bool(np.any(np.tril(ordered,-1)!=0))
        assert active_dependency
    for residual in [None,'normal','gated']:
        init,apply = BlockNeuralAutoregressiveNN(3,[3],residual=residual)
        params = call_public(init,jax.random.key(32),(2,3))[1]
        y,logs = call_public(apply,params,jnp.stack([x,x+.2]))
        assert y.shape == logs.shape == (2,3)
        for row in range(2):
            z = x+.2*row
            jac = numerical_jacobian(lambda v:apply(params,v)[0],z)
            close(np.triu(jac,1),np.zeros_like(jac))
            assert (np.diag(jac)!=0).all()
            close(logs[row].sum(),np.linalg.slogdet(jac)[1])
        def objective(delta):
            shifted = jax.tree.map(lambda p:p+delta,params)
            return apply(shifted,x)[1].sum()
        close(jax.grad(objective)(0.),(objective(1e-5)-objective(-1e-5))/2e-5)


def test_f02_t13():
    for transform, matrix, offdiag in [
        (t.CholeskyTransform(),np.array([[1.7,.3],[.3,.9]]),False),
        (t.CorrMatrixCholeskyTransform(),np.array([[1.,.3],[.3,1.]]),True),
    ]:
        factor = call_public(transform,jnp.asarray(matrix))
        close(factor,np.linalg.cholesky(matrix))
        close(transform.inv(factor),matrix)
        chart = correlation_coordinates if offdiag else lower_coordinates
        indices = np.tril_indices(2,-1 if offdiag else 0)
        def expand(z):
            result = np.eye(2) if offdiag else np.zeros((2,2))
            result[indices] = z
            return result+np.tril(result,-1).T
        expected_volume = volume(lambda z:chart(transform(jnp.asarray(expand(z)))),matrix[indices])
        close(transform.log_abs_det_jacobian(jnp.asarray(matrix),factor),expected_volume)
    loc = np.array([.3,-.5]); factor = np.array([[1.3,0],[.4,.8]])
    verify_transform(t.LowerCholeskyAffine(jnp.asarray(loc),jnp.asarray(factor)),np.array([-.7,.2]),
                     expected=loc+factor@np.array([-.7,.2]))
    p = np.array([.2,.3,.1,.4]); cumulative = np.cumsum(p)[:-1]
    for anchor in [None,1.4]:
        transform = t.SimplexToOrderedTransform() if anchor is None else t.SimplexToOrderedTransform(anchor)
        y = call_public(transform,jnp.asarray(p))
        close(y,special.logit(cumulative)+(0 if anchor is None else anchor))
        close(transform.inv(y),p)
        expected_volume = volume(lambda z:transform(jnp.r_[z,1-jnp.sum(z)]),p[:-1])
        close(transform.log_abs_det_jacobian(jnp.asarray(p),y),expected_volume)
    transition = np.array([[.6,.2],[-.1,.5]])
    values = np.array([[.3,-.4],[.8,.2],[-.5,.7]])
    for initial in [None,np.array([.5,-.2])]:
        transform = t.RecursiveLinearTransform(jnp.asarray(transition)) if initial is None else t.RecursiveLinearTransform(jnp.asarray(transition),jnp.asarray(initial))
        previous = np.zeros(2) if initial is None else initial
        expected = []
        for value in values:
            previous = transition@previous+value
            expected.append(previous)
        verify_transform(transform,values,expected=np.array(expected))
