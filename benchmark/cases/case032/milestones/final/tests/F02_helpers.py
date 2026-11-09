# feature: F02
"""Independent coordinate and numerical observations of public transformations."""
from F01_helpers import jax, jnp, np, dist, close, read_array, call_public
from velnora.distributions import constraints as c, transforms as t

# Pytest plugins may import JAX before environment configuration takes effect.
jax.config.update("jax_enable_x64", True)


def mask(domain, values, expected):
    actual = read_array(call_public(domain, jnp.asarray(values, dtype=np.result_type(np.asarray(values).dtype, float))))
    assert actual.dtype == np.bool_
    np.testing.assert_array_equal(actual, expected)


def coordinates(value):
    value = np.asarray(value)
    if np.iscomplexobj(value):
        return np.r_[value.real.ravel(), value.imag.ravel()]
    return value.ravel()


def numerical_jacobian(function, x):
    """Central differences of observable results, not product derivatives."""
    x = np.asarray(x, dtype=float)
    columns = []
    for i in range(x.size):
        step = np.zeros(x.size)
        step[i] = 1e-5
        plus = coordinates(function(jnp.asarray(x + step.reshape(x.shape))))
        minus = coordinates(function(jnp.asarray(x - step.reshape(x.shape))))
        columns.append((plus - minus) / 2e-5)
    return np.stack(columns, axis=-1)


def volume(function, x):
    jacobian = numerical_jacobian(function, x)
    # Gram volume also works for isometric embeddings and complex spectra.
    sign, logdet = np.linalg.slogdet(jacobian.T @ jacobian)
    assert sign > 0
    return logdet / 2


def verify_transform(transform, x, chart=coordinates, expected=None, shape=True):
    x = jnp.asarray(x)
    y = call_public(transform, x)
    assert read_array(call_public(transform.domain, x)).all()
    assert read_array(call_public(transform.codomain, y)).all()
    if expected is not None:
        close(y, expected)
    close(call_public(transform.inv, y), x)
    if shape:
        assert transform.forward_shape(x.shape) == y.shape
        assert transform.inverse_shape(y.shape) == x.shape
    reported = call_public(transform.log_abs_det_jacobian, x, y)
    assert np.shape(reported) == ()
    close(reported, volume(lambda z: chart(transform(z)), x))
    return read_array(y)


def lower_coordinates(value):
    value = np.asarray(value)
    return value[np.tril_indices(value.shape[-1])]


def correlation_coordinates(value):
    value = np.asarray(value)
    return value[np.tril_indices(value.shape[-1], -1)]


def unpack_record(x):
    return {'head': x[0], 'tail': x[1:].reshape(2, 2)}


def pack_record(record):
    return jnp.concatenate([jnp.reshape(record['head'], (1,)), record['tail'].reshape(-1)])
