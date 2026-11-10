# feature: F19
"""Acceptance tests for finite Hilbert space Gaussian-process models."""
import gc
import pytest
from F19_helpers import (
    jax, jnp, np, close, read_array, call_public, approximation, laplacian,
    spectra, rectangular_basis, independent_spectrum, finite_covariance,
    periodic_ingredients, assert_function_law,
)


@pytest.fixture(autouse=True)
def release_f19_cache():
    yield
    jax.clear_caches()
    gc.collect()


def test_f19_t01():
    for i, family in enumerate(('squared_exponential', 'matern', 'rational_quadratic')):
        entry = getattr(approximation, 'hsgp_'+family)
        for variant in range(2):
            kwargs = dict(x=jnp.array([-.7, .1, .8]), alpha=1.4 if variant == 0 else .8,
                          length=.7 if variant == 0 else 1.1,
                          ell=2.4 if variant == 0 else 3.1, m=4 if variant == 0 else 6)
            if family == 'matern':
                kwargs['nu'] = 1.7 if variant == 0 else 2.6
            if family == 'rational_quadratic':
                kwargs['scale_mixture'] = 2.3 if variant == 0 else 1.4
            assert_function_law(entry, kwargs, finite_covariance(family, **kwargs), 1910+i*2+variant)
    for variant in range(2):
        kwargs = dict(x=jnp.array([-.7, .1, .8]), alpha=1.3 if variant == 0 else .9,
                      length=.8 if variant == 0 else 1.2, w0=1.2 if variant == 0 else 2.1,
                      m=4 if variant == 0 else 6)
        cosines, sines, weights = periodic_ingredients(**kwargs)
        # The original uses Appendix B weights as coefficient scales, rather
        # than variances. This minor baseline bug is documented in the ledger.
        covariance = (cosines*weights**2)@cosines.T+(sines*weights**2)@sines.T
        assert_function_law(approximation.hsgp_periodic_non_centered, kwargs, covariance, 1920+variant)


def test_f19_t02():
    for x, ell, m in [(np.array([-.8, .2, 1.1]), 2.5, 4),
                      (np.array([[-.7, .4], [.2, -.6], [.9, 1.1]]), [2.2, 3.1], [2, 3])]:
        indices, omega, phi = rectangular_basis(x, ell, m)
        d = indices.shape[0]
        actual_indices = read_array(call_public(laplacian.eigenindices, m, d))
        assert actual_indices.shape == indices.shape
        assert sorted(map(tuple, actual_indices.T)) == sorted(map(tuple, indices.T))
        # Do not require an incidental enumeration order: every public result
        # must align to the indices the public enumeration actually returned.
        order = [list(map(tuple, indices.T)).index(tuple(row)) for row in actual_indices.T]
        close(call_public(laplacian.sqrt_eigenvalues, ell, m, d), omega[order].T)
        close(call_public(laplacian.eigenfunctions, jnp.array(x), ell, m), phi[..., order])
        for family in ('squared_exponential', 'matern', 'rational_quadratic'):
            # Multidimensional RQ normalization is a baseline bug; the
            # independently validated one-dimensional RQ capability remains.
            if family == 'rational_quadratic' and d > 1:
                continue
            length = .7 if d == 1 else jnp.array([.6, 1.1])
            params = dict(alpha=1.6, length=length)
            if family == 'matern':
                params['nu'] = 1.7
            if family == 'rational_quadratic':
                params['scale_mixture'] = 2.3
            diag = getattr(spectra, 'diag_spectral_density_'+family)
            density = getattr(spectra, 'spectral_density_'+family)
            expected = independent_spectrum(family, omega, **params)
            close(call_public(diag, **params, ell=ell, m=m, dim=d), expected[order])
            for frequency in (np.zeros(d), np.arange(1, d+1)*.45, -np.arange(1, d+1)*1.1):
                close(call_public(density, **params, dim=d, w=jnp.array(frequency)),
                      independent_spectrum(family, frequency, **params)[0])


def test_f19_t03():
    for alpha, length, w0, m in [(1.3, .8, 1.2, 4), (.7, 1.1, 2.3, 6)]:
        x = jnp.array([-.9, -.1, .6, 1.2])
        cosines, sines, weights = periodic_ingredients(x, alpha, length, w0, m)
        actual_cos, actual_sin = call_public(laplacian.eigenfunctions_periodic, x, w0, m)
        close(actual_cos, cosines)
        close(actual_sin, sines)
        close(call_public(spectra.diag_spectral_density_periodic, alpha, length, m), weights)
        covariance = (cosines*weights**2)@cosines.T+(sines*weights**2)@sines.T
        assert_function_law(approximation.hsgp_periodic_non_centered,
                            dict(x=x, alpha=alpha, length=length, w0=w0, m=m),
                            covariance, 1930+m)


def test_f19_t04():
    x = jnp.array([[-.7, .4], [.2, -.6], [.9, 1.1]])
    for i, family in enumerate(('squared_exponential', 'matern')):
        for per_axis in (False, True):
            kwargs = dict(x=x, alpha=1.3, length=jnp.array([.6, 1.1]) if per_axis else .8,
                          ell=[2.2, 3.1] if per_axis else 2.7, m=[2, 3] if per_axis else 3)
            if family == 'matern':
                kwargs['nu'] = 2.2
            covariance = finite_covariance(family, **kwargs)
            for non_centered in (False, True):
                assert_function_law(getattr(approximation, 'hsgp_'+family),
                                    dict(kwargs, non_centered=non_centered), covariance,
                                    1940+4*i+2*per_axis+non_centered)
    kwargs = dict(x=jnp.array([-.8, .2, .9]), alpha=.9, length=.65,
                  scale_mixture=1.8, ell=3.2, m=5)
    covariance = finite_covariance('rational_quadratic', **kwargs)
    for non_centered in (False, True):
        assert_function_law(approximation.hsgp_rational_quadratic,
                            dict(kwargs, non_centered=non_centered), covariance, 1950+non_centered)


def test_f19_t05():
    x = jnp.array([[-.7, .4], [.2, -.6], [.9, 1.1]])
    # Establish the live valid path before changing only an incompatible
    # per-axis specification. Materialization is inside the refusal capture.
    for family in ('squared_exponential', 'matern'):
        entry = getattr(approximation, 'hsgp_'+family)
        kwargs = dict(x=x, alpha=1.3, length=jnp.array([.6, 1.1]), ell=[2.2, 3.1], m=[2, 3])
        if family == 'matern':
            kwargs['nu'] = 1.7
        from velnora import handlers
        seeded = handlers.seed(entry, rng_seed=19)
        assert np.isfinite(read_array(call_public(seeded, **kwargs))).all()
        for field, bad in [('ell', [2.2, 3.1, 2.8]), ('m', [2, 3, 4]),
                           ('length', jnp.array([.6, 1.1, .9]))]:
            with pytest.raises(ValueError):
                read_array(call_public(seeded, **dict(kwargs, **{field: bad})))
    assert np.isfinite(read_array(call_public(laplacian.eigenfunctions, x, [2.2, 3.1], [2, 3]))).all()
    for ell, m in [([2.2], [2, 3]), ([2.2, 3.1], [2])]:
        with pytest.raises(ValueError):
            read_array(call_public(laplacian.eigenfunctions, x, ell, m))
    cosines, sines = call_public(laplacian.eigenfunctions_periodic, x[:, 0], 1.3, 4)
    assert np.isfinite(read_array(cosines)).all() and np.isfinite(read_array(sines)).all()
    with pytest.raises(ValueError):
        call_public(laplacian.eigenfunctions_periodic, x, 1.3, 4)
