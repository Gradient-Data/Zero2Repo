# feature: F13
"""Independent dense probability oracles for small temporal models."""
import velnora
import numpy as np
import torch
from scipy import stats
from F01_helpers import assert_close


def linear_joint(initial_mean, initial_cov, transitions, process_mean, process_cov,
                 observations, noise_mean, noise_cov):
    """Build affine loadings of independent innovations, including the final state."""
    steps, hidden, _ = transitions.shape
    obs = observations.shape[-1]
    width = hidden*(steps+1)+obs*steps
    loading = np.zeros((hidden, width))
    loading[:, :hidden] = np.linalg.cholesky(initial_cov)
    mean = np.asarray(initial_mean)
    means, loadings = [], []
    for t in range(steps):
        mean = mean @ transitions[t]+process_mean[t]
        loading = transitions[t].T @ loading
        loading[:, hidden*(t+1):hidden*(t+2)] += np.linalg.cholesky(process_cov[t])
        out = observations[t].T @ loading
        start = hidden*(steps+1)+obs*t
        out[:, start:start+obs] += np.linalg.cholesky(noise_cov[t])
        means.append(mean @ observations[t]+noise_mean[t])
        loadings.append(out)
    means.append(mean)
    loadings.append(loading)
    matrix = np.concatenate(loadings)
    return np.concatenate(means), matrix @ matrix.T


def conditional_normal(mean, cov, observed, count):
    gain = np.linalg.solve(cov[:count, :count], cov[:count, count:]).T
    return (mean[count:]+gain @ (np.asarray(observed).reshape(-1)-mean[:count]),
            cov[count:, count:]-gain @ cov[:count, count:])


def scalar_system(steps=4):
    a = np.linspace(.45, .85, steps)[:, None, None]
    b = np.linspace(.7, 1.3, steps)[:, None, None]
    u = np.linspace(-.15, .2, steps)[:, None]
    v = np.linspace(.2, -.1, steps)[:, None]
    q = np.linspace(.25, .5, steps)[:, None, None]
    r = np.linspace(.3, .6, steps)[:, None, None]
    return a, b, u, v, q, r


def make_gaussian(steps=4, **kwargs):
    a,b,u,v,q,r = scalar_system(steps)
    tensor = torch.tensor
    model = velnora.distributions.GaussianHMM(velnora.distributions.MultivariateNormal(tensor([.4]), tensor([[.8]])),
        tensor(a), velnora.distributions.MultivariateNormal(tensor(u), tensor(q)), tensor(b),
        velnora.distributions.MultivariateNormal(tensor(v), tensor(r)), **kwargs)
    return model, linear_joint([.4], [[.8]], a,u,q,b,v,r)


def matern_cov(times, nu, length, scale):
    # Closed forms of the named Matern covariance, not state-space recursions.
    distance = np.abs(np.subtract.outer(times, times))
    x = np.sqrt(2*nu)*distance/length
    polynomial = 1 if nu == .5 else (1+x if nu == 1.5 else 1+x+x*x/3)
    return scale**2*polynomial*np.exp(-x)


def check_temporal(model, targets, mean, covariance, future, independent=False,
                   check_covariance=True):
    n, dims = targets.shape
    count = n*dims
    expected = []
    if independent:
        for j in range(dims):
            idx = np.arange(j,count,dims)
            expected.append(stats.multivariate_normal.logpdf(targets[:,j].detach().numpy(),
                mean=mean[idx], cov=covariance[np.ix_(idx,idx)]))
    else:
        expected = stats.multivariate_normal.logpdf(targets.detach().numpy().reshape(-1),
                    mean=mean[:count], cov=covariance[:count,:count])
    assert_close(model.log_prob(targets), expected)
    cm, cc = conditional_normal(mean, covariance, targets.detach().numpy(), count)
    forecast = model.forecast(targets, future)
    assert_close(forecast.mean, cm.reshape(-1,dims))
    if check_covariance:
        blocks = np.stack([cc[i:i+dims,i:i+dims] for i in range(0,len(cm),dims)])
        if independent or check_covariance == "diagonal":
            assert_close(forecast.variance, np.diagonal(blocks,axis1=-2,axis2=-1))
        else:
            assert_close(forecast.covariance_matrix, blocks)


def learn_temporal(model, targets):
    """One small gradient step must improve the actual likelihood."""
    params = list(model.parameters())
    before = model.log_prob(targets).sum()
    gradients = torch.autograd.grad(before, params)
    assert all(torch.isfinite(g).all() for g in gradients)
    assert sum(g.square().sum().item() for g in gradients) > 1e-8
    # Compare the objective derivative with a central finite difference through
    # the same public likelihood, without assuming an optimization algorithm.
    directions = [torch.linspace(-.7,.9,p.numel()).reshape(p.shape) for p in params]
    originals = [p.detach().clone() for p in params]
    displaced = []
    for sign in (1.,-1.):
        with torch.no_grad():
            for p,base,direction in zip(params,originals,directions):
                p.copy_(base+sign*1e-5*direction)
        displaced.append(model.log_prob(targets).sum().detach())
    with torch.no_grad():
        for p,base in zip(params,originals):
            p.copy_(base)
    expected_derivative = (displaced[0]-displaced[1])/2e-5
    assert_close(sum((g*v).sum() for g,v in zip(gradients,directions)),expected_derivative)
    # Normalized ascent makes this a small step without assuming an optimizer.
    norm = sum(g.square().sum() for g in gradients).sqrt()
    with torch.no_grad():
        for parameter, gradient in zip(params, gradients):
            parameter.add_(.0001*gradient/norm)
    after = model.log_prob(targets).sum()
    assert after > before
