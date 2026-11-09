# feature: F14
"""Dense Gaussian laws and caller-defined covariance workloads."""
import numpy as np
import torch
from scipy import stats
from velnora.contrib.gp import kernels as k
from F01_helpers import assert_close
from F13_helpers import conditional_normal


def gp_problem():
    x = torch.tensor([[1., .2, -.3], [.1, 1.1, .4], [-.4, .3, 1.2]])
    y = torch.tensor([1.4, -.8, .6])
    new = torch.tensor([[.7, -.2, .5], [-.3, .9, .8]])
    return x, y, new


def gp_kernel():
    return k.Coregionalize(3, components=torch.tensor([[.7], [-.4], [.9]]),
                          diagonal=torch.tensor([.6, .9, .5]))


def bilinear_cov(x, z, kernel):
    factor = kernel.components.detach().numpy()
    diagonal = kernel.diagonal.detach().numpy()
    return np.asarray(x) @ (factor @ factor.T + np.diag(diagonal)) @ np.asarray(z).T


def regression_oracle(x, y, new, kernel, noise, mean=None, inducing=None, approx='DTC'):
    x, y, new = map(np.asarray, (x, y, new))
    kff = bilinear_cov(x, x, kernel)
    kss = bilinear_cov(new, new, kernel)
    cross = bilinear_cov(x, new, kernel)
    if inducing is not None:
        kuu = bilinear_cov(inducing, inducing, kernel)
        kuf = bilinear_cov(inducing, x, kernel)
        kus = bilinear_cov(inducing, new, kernel)
        qff = kuf.T @ np.linalg.solve(kuu, kuf)
        cross = kuf.T @ np.linalg.solve(kuu, kus)
        kff = qff + (np.diag(np.diag(kff-qff)) if approx == 'FITC' else 0)
    mx = np.zeros(len(x)) if mean is None else np.asarray(mean(torch.tensor(x)))
    ms = np.zeros(len(new)) if mean is None else np.asarray(mean(torch.tensor(new)))
    joint = np.block([[kff+noise*np.eye(len(x)), cross], [cross.T, kss]])
    return conditional_normal(np.r_[mx, ms], joint, y, len(x))


def check_gp_prediction(model, new, expected, noise=None):
    loc, cov = model(new, full_cov=True)
    assert_close(loc, expected[0])
    assert_close(cov, expected[1])
    loc, var = model(new)
    assert_close(loc, expected[0])
    assert_close(var, np.diag(expected[1]))
    if noise is not None:
        loc, cov = model(new, full_cov=True, noiseless=False)
        assert_close(loc, expected[0])
        assert_close(cov, expected[1]+noise*np.eye(len(new)))
        loc, var = model(new, noiseless=False)
        assert_close(loc, expected[0])
        assert_close(var, np.diag(expected[1])+noise)


def variational_oracle(model, new, sparse):
    basis = model.Xu if sparse else model.X
    loc = model.u_loc if sparse else model.f_loc
    scale = model.u_scale_tril if sparse else model.f_scale_tril
    kuu = bilinear_cov(basis.detach(), basis.detach(), model.kernel)
    cross = bilinear_cov(new, basis.detach(), model.kernel)
    gain = np.linalg.solve(kuu, cross.T).T
    s = scale.detach().numpy()
    covariance = bilinear_cov(new, new, model.kernel)-gain @ cross.T
    covariance = covariance + gain @ (s @ np.swapaxes(s, -1, -2)) @ gain.T
    return loc.detach().numpy() @ gain.T, covariance


def gp_fit_score(model, sparse, family):
    """Independent predictive log score using Gaussian quadrature, not ELBO noise."""
    from scipy import special
    mean, covariance = variational_oracle(model, model.X, sparse)
    variance = np.diagonal(covariance, axis1=-2, axis2=-1).clip(min=0)
    observed = model.y.detach().numpy()
    if family == 'Gaussian':
        return stats.norm.logpdf(observed, mean,
            np.sqrt(variance+model.likelihood.variance.item())).sum()
    nodes, weights = special.roots_hermitenorm(40)
    weights = weights/np.sqrt(2*np.pi)
    if family == 'MultiClass':
        grid = np.stack(np.meshgrid(nodes, nodes, nodes, indexing='ij'), -1).reshape(-1, 3)
        weight = np.einsum('i,j,k->ijk', weights, weights, weights).reshape(-1)
        logits = mean.T[None]+np.sqrt(variance.T)[None]*grid[:, None]
        probabilities = special.softmax(logits, axis=-1)
        return sum(np.log(weight @ probabilities[:, i, int(y)]) for i, y in enumerate(observed))
    latent = mean[None]+np.sqrt(variance)[None]*nodes[:, None]
    mass = (stats.bernoulli.pmf(observed, special.expit(latent)) if family == 'Binary'
            else stats.poisson.pmf(observed, np.exp(latent)))
    return np.log(weights @ mass).sum()
