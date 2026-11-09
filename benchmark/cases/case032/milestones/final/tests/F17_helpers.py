# feature: F17
"""Public Stein workloads and caller-specified kernel observations."""
from F01_helpers import jax, jnp, np, dist, read_array, call_public
import velnora
from velnora import optim
from velnora.contrib.einstein import SVGD, ASVGD, SteinVI, RBFKernel
from velnora.infer import autoguide as ag


def stein_normal_model(mean=1.7, sd=.8):
    velnora.sample('x', dist.Normal(mean, sd))


def stein_method(kind, count=32):
    args = (stein_normal_model, optim.Adam(.025), RBFKernel())
    if kind == 'mixture':
        return SteinVI(args[0], ag.AutoNormal(args[0]), args[1], args[2],
                       num_stein_particles=count, num_elbo_particles=32)
    if kind == 'annealed':
        return ASVGD(*args, num_stein_particles=count, num_cycles=2,
                     transition_speed=1.)
    return SVGD(*args, num_stein_particles=count)


def kernel_value(kernel, particles, x, y, info=None, loss=None, initialize=True):
    """Read a computed public kernel at two supplied coordinates."""
    particles = jnp.asarray(particles)
    if initialize:
        call_public(kernel.init, jax.random.key(171), particles.shape)
    fn = call_public(kernel.compute, jax.random.key(172), particles,
                     {} if info is None else info, loss)
    return read_array(call_public(fn, jnp.asarray(x), jnp.asarray(y)))


def stein_bandwidth(particles, factor=None):
    """Independent ordered-distance definition specified by the requirement."""
    p = np.asarray(particles)
    if len(p) == 1:
        return 1.
    distances = np.linalg.norm(p[:, None] - p[None, :], axis=-1)
    return np.median(distances)**2 * (1/np.log(len(p)) if factor is None else factor(len(p)))
