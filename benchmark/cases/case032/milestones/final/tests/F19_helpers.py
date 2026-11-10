# feature: F19
"""Independent finite HSGP law oracles from the cited mathematical definitions."""
from itertools import product
from scipy import integrate, special, stats
from F01_helpers import (
    jax, jnp, np, close, read_array, call_public, gaussian_samples,
)
from velnora import handlers
from velnora.contrib.hsgp import approximation as approximation
from velnora.contrib.hsgp import laplacian as laplacian
from velnora.contrib.hsgp import spectral_densities as spectra


def rectangular_basis(x, ell, m):
    x = np.asarray(x)
    if x.ndim == 1:
        x = x[:, None]
    d = x.shape[-1]
    widths = np.broadcast_to(ell, (d,))
    counts = np.broadcast_to(m, (d,))
    indices = np.array(list(product(*(range(1, int(n)+1) for n in counts)))).T
    omega = indices.T*np.pi/(2*widths)
    phi = np.prod(np.sin((x[..., None, :]+widths)*omega)/np.sqrt(widths), axis=-1)
    return indices, omega, phi


def independent_spectrum(family, omega, alpha, length, nu=1.7, scale_mixture=2.3):
    """Fourier densities; RQ is integrated as the defining gamma mixture of SEs."""
    omega = np.atleast_2d(omega)
    d = omega.shape[-1]
    length = np.broadcast_to(length, (d,))
    radius = np.sum((omega*length)**2, axis=-1)
    if family == 'squared_exponential':
        return alpha*(2*np.pi)**(d/2)*np.prod(length)*np.exp(-radius/2)
    if family == 'matern':
        return (alpha*2**d*np.pi**(d/2)*special.gamma(nu+d/2)/special.gamma(nu)
                *(2*nu)**nu*np.prod(length)/(2*nu+radius)**(nu+d/2))
    assert family == 'rational_quadratic'
    q = scale_mixture
    return np.array([integrate.quad(
        lambda t: stats.gamma.pdf(t, q, scale=1/q)*alpha*(2*np.pi)**(d/2)
        *np.prod(length)*t**(-d/2)*np.exp(-r/(2*t)),
        0, np.inf, epsabs=1e-11, epsrel=1e-10)[0] for r in radius])


def finite_covariance(family, **kwargs):
    _, omega, phi = rectangular_basis(kwargs['x'], kwargs['ell'], kwargs['m'])
    weights = independent_spectrum(family, omega, kwargs['alpha'], kwargs['length'],
                                   kwargs.get('nu', 1.7), kwargs.get('scale_mixture', 2.3))
    return (phi*weights)@phi.T


def periodic_ingredients(x, alpha, length, w0, m):
    angle = np.asarray(x)[:, None]*w0*np.arange(m)
    weights = alpha**2*np.where(np.arange(m) == 0, 1, 2)*special.ive(np.arange(m), length**-2)
    return np.cos(angle), np.sin(angle), weights


def assert_function_law(entry, kwargs, covariance, seed):
    """Read only function returns, with no assumptions about latent organization."""
    def draw(key):
        return handlers.seed(entry, rng_seed=key)(**kwargs)
    n = 32768
    draws = read_array(call_public(jax.jit(jax.vmap(draw)),
                      jax.random.split(jax.random.key(seed), n), timeout=240))
    assert draws.shape == (n, covariance.shape[0])
    gaussian_samples(draws, np.zeros(covariance.shape[0]), covariance)
    # Gaussian mean and covariance SEs; nine SEs have negligible union risk
    # across this feature. Distribution checks also reject non-Gaussian laws
    # that preserve the first two moments.
    assert np.all(np.abs(draws.mean(0)) < 9*np.sqrt(np.diag(covariance)/n))
    se = np.sqrt((covariance**2+np.outer(np.diag(covariance), np.diag(covariance)))/(n-1))
    assert np.all(np.abs(np.cov(draws.T)-covariance) < 9*se)
