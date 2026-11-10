# feature: F16
"""Caller-owned networks used through the public registration integrations."""
from F01_helpers import jax, jnp, np
import velnora
from velnora.contrib.module import (flax_module, nnx_module, eqx_module,
    random_flax_module, random_nnx_module, random_eqx_module)

import equinox as eqx


class EquinoxAffine(eqx.Module):
    weight: jax.Array
    bias: jax.Array

    def __call__(self, x):
        return x @ self.weight + self.bias


class EquinoxCounter(eqx.Module):
    offset: jax.Array

    def __call__(self, x, count):
        return x + count + 1, count + 1


def affine_component(kind, name='net', prior=None):
    """Return a registered affine network with caller-defined initial values."""
    w = jnp.array([[.3], [-.6]])
    b = jnp.array([.7])
    if kind == 'functional':
        def init(key, shape):
            return shape[:-1] + (1,), (w, b)
        def apply(params, x):
            return x @ params[0] + params[1]
        return velnora.module(name, (init, apply), input_shape=(2,))
    if kind == 'flax':
        from flax import linen as nn
        class Affine(nn.Module):
            @nn.compact
            def __call__(self, x):
                weight = self.param('weight', lambda key: w)
                bias = self.param('bias', lambda key: b)
                return x @ weight + bias
        net = Affine()
        return (flax_module(name, net, input_shape=(2,)) if prior is None else
                random_flax_module(name, net, prior, input_shape=(2,)))
    if kind == 'nnx':
        from flax import nnx
        class Affine(nnx.Module):
            def __init__(self):
                self.weight, self.bias = nnx.Param(w), nnx.Param(b)
            def __call__(self, x):
                return x @ self.weight[...] + self.bias[...]
        net = Affine()
        return nnx_module(name, net) if prior is None else random_nnx_module(name, net, prior)
    if kind == 'eqx':
        net = EquinoxAffine(w, b)
        return eqx_module(name, net) if prior is None else random_eqx_module(name, net, prior)
    raise ValueError('Unknown integration')


def counting_component(kind):
    """State affects the returned value, rather than merely appearing in a trace."""
    if kind == 'flax':
        from flax import linen as nn
        class Counter(nn.Module):
            @nn.compact
            def __call__(self, x):
                self.param('offset', lambda key: jnp.array(0.))
                count = self.variable('counter', 'count', lambda: jnp.array(0.))
                count.value = count.value + 1
                return x + count.value
        return flax_module('counter', Counter(), input_shape=(), mutable=['counter'])
    if kind == 'nnx':
        from flax import nnx
        class Counter(nnx.Module):
            def __init__(self):
                self.offset = nnx.Param(jnp.array(0.))
                self.count = nnx.Variable(jnp.array(0.))
            def __call__(self, x):
                self.count[...] += 1
                return x + self.count[...]
        return nnx_module('counter', Counter())
    if kind == 'eqx':
        from velnora.primitives import mutable
        net = eqx_module('counter', EquinoxCounter(jnp.array(0.)))
        holder = mutable('counter$state', {'count': jnp.array(0.)})
        def apply(x):
            y, holder['count'] = net(x, holder['count'])
            return y
        return apply
    raise ValueError('Unknown integration')
