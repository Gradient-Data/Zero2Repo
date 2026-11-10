# feature: F07
"""Public transform measurements, without assumptions about parameter encoding."""
import math
import numpy as np
import torch
from scipy import stats
from F01_helpers import assert_close

FLOW_NAMES = (
    'affine_autoregressive', 'affine_coupling', 'batchnorm',
    'block_autoregressive', 'neural_autoregressive', 'planar', 'polynomial',
    'radial', 'spline', 'spline_autoregressive', 'spline_coupling', 'sylvester',
)
INVERTIBLE_NAMES = ('affine_autoregressive', 'affine_coupling', 'spline',
                    'spline_autoregressive', 'spline_coupling')
GENERATED_NAMES = ('planar', 'radial', 'polynomial', 'sylvester',
                   'block_autoregressive', 'neural_autoregressive')
CONDITIONAL_NAMES = ('affine_autoregressive', 'affine_coupling',
                     'neural_autoregressive', 'planar', 'radial', 'spline',
                     'spline_autoregressive')


def numerical_volume(transform, point):
    """Central differences on fresh tensor objects avoid cached pair identities."""
    columns = []
    for coordinate in range(point.numel()):
        step = torch.zeros_like(point)
        step[coordinate] = 1e-5
        columns.append(((transform(point + step) - transform(point - step)) / 2e-5).detach())
    matrix = torch.stack(columns, -1)
    sign, volume = torch.linalg.slogdet(matrix)
    assert sign.abs() == 1
    assert torch.isfinite(volume)
    return volume


def normal_vector_score(value, loc=0., scale=1.):
    return stats.norm.logpdf(value.detach().numpy(), loc=loc, scale=scale).sum(-1)


def assert_flow_scoring(transform, distribution):
    """Check actual generated values against an independent base density and volume."""
    values = distribution.rsample((5,))
    scores = distribution.log_prob(values)
    assert values.shape == (5, 3)
    assert scores.shape == (5,)
    # Recovering the generated sample is supported even by restricted flows.
    latent = transform.inv(values)
    expected = []
    for point in latent:
        expected.append(normal_vector_score(point) - numerical_volume(transform, point).item())
    np.testing.assert_allclose(scores.detach().numpy(), expected, rtol=2e-4, atol=2e-4)
    return values, scores


def assert_parameter_derivatives(transform, distribution):
    """Generated samples and their scores have correct directional derivatives."""
    params = tuple(transform.parameters())
    assert params
    rng = torch.random.get_rng_state()
    weights = torch.linspace(.3, 1.2, 15).reshape(5, 3)

    def objectives():
        torch.random.set_rng_state(rng)
        value = distribution.rsample((5,))
        return (value * weights).sum(), distribution.log_prob(value).sum()

    outputs = objectives()
    directions = [torch.cos(torch.arange(p.numel(), dtype=p.dtype)).reshape(p.shape)
                  / math.sqrt(p.numel()) for p in params]
    derivatives = []
    for output in outputs:
        assert output.requires_grad
        grads = torch.autograd.grad(output, params, retain_graph=True, allow_unused=True)
        active = [g for g in grads if g is not None]
        assert active and all(torch.isfinite(g).all() for g in active)
        derivatives.append(sum((g * direction).sum().item()
                               for g, direction in zip(grads, directions) if g is not None))
    saved = [p.detach().clone() for p in params]
    observed = []
    try:
        for sign in (1, -1):
            with torch.no_grad():
                for p, original, direction in zip(params, saved, directions):
                    p.copy_(original + sign * 1e-5 * direction)
            observed.append([v.detach().item() for v in objectives()])
    finally:
        with torch.no_grad():
            for p, original in zip(params, saved):
                p.copy_(original)
    numerical = (np.array(observed[0]) - np.array(observed[1])) / 2e-5
    np.testing.assert_allclose(derivatives, numerical, rtol=3e-3, atol=3e-3)


def assert_inverse_domain(factory, external):
    transform = factory()
    latent = transform.inv(external.clone())
    assert torch.isfinite(latent).all()
    assert_close(transform(latent.clone()), external.numpy())


def reparameterized_trace(law, reparam, coordinates):
    """Bind caller-supplied coordinates through public handlers and retain the trace."""
    import velnora
    from velnora import poutine

    def model():
        return velnora.sample('value', law)

    changed = poutine.reparam(model, config={'value': reparam})
    return poutine.trace(poutine.condition(changed, data=coordinates)).get_trace()


def reparameterized_draws(law, reparam, count):
    """Draw independent original-domain values through the reparameterized model."""
    import velnora
    from velnora import poutine

    def model():
        with velnora.plate('coordinate_draws', count):
            return velnora.sample('value', law)

    return poutine.reparam(model, config={'value': reparam})().detach()


def assert_autoregressive_structure(transform, width, affine=False):
    """Infer dependency edges from derivatives, allowing any coordinate order."""
    edges = np.zeros((width, width), dtype=bool)
    for point in (torch.linspace(-.7, .9, width), torch.linspace(.8, -.3, width)):
        jacobian = torch.autograd.functional.jacobian(transform, point).detach().numpy()
        assert (np.diag(jacobian) > 0).all()
        edges |= np.abs(jacobian) > 1e-8
        if affine:
            for coordinate in range(width):
                offset = torch.zeros(width)
                offset[coordinate] = .6
                endpoints = transform(point-offset)[coordinate]+transform(point+offset)[coordinate]
                assert_close(endpoints, 2*transform(point.clone())[coordinate].detach().numpy())
    np.fill_diagonal(edges, False)
    # A topological elimination accepts every permutation, not a particular NN mask.
    remaining = set(range(width))
    while remaining:
        independent = {i for i in remaining if not any(edges[i, j] for j in remaining)}
        assert independent, 'Autoregressive coordinate dependencies contain a cycle'
        remaining -= independent


def _rational_segment(values, degree):
    """Does one sampled segment belong to a ratio of degree-d polynomials?"""
    x = np.linspace(-1., 1., len(values))
    y = np.asarray(values)
    # Affine output rescaling preserves rational degree and improves conditioning.
    y = (y-y.mean())/max(np.ptp(y), 1e-12)
    powers = np.stack([x**i for i in range(degree+1)], axis=-1)
    matrix = np.concatenate([powers, -y[:, None]*powers], axis=-1)
    # A rational function supplies a nonzero homogeneous coefficient solution.
    singular = np.linalg.svd(matrix, compute_uv=False)
    return singular[-1] <= 2e-8*singular[0]


def assert_spline_family(transform, width, bound, bins, order):
    """Measure rational degree and piece count, without reading learned knots."""
    degree = 1 if order == 'linear' else 2
    max_pieces = bins*(2 if order in ('linear', 'either') else 1)
    grid = torch.linspace(-bound+.0001, bound-.0001, 241)
    for coordinate in range(width):
        points = torch.linspace(-.3, .4, width).expand(len(grid), width).clone()
        points[:, coordinate] = grid
        values = transform(points).detach().numpy()[:, coordinate]
        assert (np.diff(values) > 0).all()
        assert values.min() >= -bound-1e-6 and values.max() <= bound+1e-6
        # Greedily take maximal rational pieces. Each actual knot can end one
        # piece; the next starts on the next sampled point. The fit is checked
        # on all intervening points, not a fitted value from the product.
        start, pieces = 0, 0
        minimum = 2*(degree+1)
        while start < len(values):
            end = min(start+minimum-1, len(values))
            while end < len(values) and _rational_segment(values[start:end+1], degree):
                end += 1
            pieces += 1
            start = end
        assert pieces <= max_pieces, (order, coordinate, pieces, max_pieces)


def _fit_relation(residual, starts, tolerance=3e-6):
    """Fit an observable mathematical family with bounded deterministic effort."""
    from scipy.optimize import least_squares
    results = [least_squares(residual, initial, max_nfev=1200,
                             ftol=1e-12, xtol=1e-12, gtol=1e-12)
               for initial in starts]
    best = min(results, key=lambda result: np.max(np.abs(result.fun)))
    error = np.max(np.abs(best.fun))
    assert error < tolerance, 'Output does not obey the named mathematical family: {}'.format(error)
    return best.x


def assert_planar_family(transform, width, residual_input=True):
    """Fit the tanh projection to independent vector observations."""
    rng = np.random.default_rng(7103)
    points = rng.normal(size=(55, width))*2
    values = transform(torch.tensor(points)).detach().numpy()
    displacement = values-points if residual_input else values
    # For a planar residual, every displacement lies on the same line.
    _, singular, vectors = np.linalg.svd(displacement, full_matrices=False)
    if singular[0] < 1e-10:
        return
    if residual_input:
        assert np.linalg.norm(singular[1:]) < 1e-7*(1+singular[0])
        direction = vectors[0]
        scalar = displacement @ direction
        design = np.column_stack((points, np.ones(len(points))))
        amplitude = max(np.max(abs(scalar))*1.3, .1)
        slope = np.linalg.lstsq(design, np.arctanh(np.clip(scalar/amplitude, -.95, .95)), rcond=None)[0]
        def residual(parameters):
            return parameters[0]*np.tanh(design@parameters[1:])-scalar
        starts = [np.r_[amplitude*factor, slope/factor] for factor in (1., 2., 5.)]
        parameters = _fit_relation(residual, starts)
        assert parameters[0]*np.dot(direction, parameters[1:-1]) > -1-1e-6
    else:
        # One-dimensional block autoregression with one hidden unit is an
        # increasing scaled and shifted tanh, not a generic monotone bijection.
        assert width == 1
        x, y = points[:, 0], values[:, 0]
        center, amplitude = (y.max()+y.min())/2, max(np.ptp(y)/2, .1)
        def residual(parameters):
            a, b, c, d = parameters
            return a*np.tanh(b*x+c)+d-y
        starts = [np.array([amplitude, slope, 0., center]) for slope in (.3, 1., 2.)]
        parameters = _fit_relation(residual, starts)
        assert parameters[0]*parameters[1] > 0


def assert_radial_family(transform, width):
    """Recover a common radial center and check its full distance relation."""
    rng = np.random.default_rng(7104)
    points = rng.normal(size=(40, width))*1.7
    displacements = transform(torch.tensor(points)).detach().numpy()-points
    lengths = np.linalg.norm(displacements, axis=-1)
    if lengths.max() < 1e-10:
        return
    assert width > 1
    directions = displacements/lengths[:, None]
    projections = np.eye(width)-directions[:, :, None]*directions[:, None, :]
    center = np.linalg.lstsq(projections.reshape(-1, width),
                            np.einsum('nij,nj->ni', projections, points).reshape(-1), rcond=None)[0]
    delta = points-center
    radius = np.linalg.norm(delta, axis=-1)
    multiplier = (displacements*delta).sum(-1)/(delta**2).sum(-1)
    np.testing.assert_allclose(displacements, multiplier[:, None]*delta, atol=2e-7, rtol=2e-7)
    coefficients = np.linalg.lstsq(np.column_stack((np.ones(len(radius)), radius)),
                                 1/multiplier, rcond=None)[0]
    beta = 1/coefficients[1]
    alpha = coefficients[0]*beta
    assert alpha > 0 and beta > -alpha
    np.testing.assert_allclose(displacements, beta*delta/(alpha+radius[:, None]), atol=2e-7, rtol=2e-7)


class PolynomialCoefficients(torch.nn.Module):
    """A real trainable coefficient function in a caller-chosen coordinate order."""
    def __init__(self, width, degree, count):
        super().__init__()
        self.width, self.degree, self.count = width, degree, count
        self.coefficients = torch.nn.Parameter(
            torch.linspace(-.4, .7, count*(degree+1)*width).reshape(count, degree+1, width))

    def forward(self, value):
        preceding = value.cumsum(-1)-value
        coefficients = self.coefficients + .1*preceding[..., None, None, :]
        return coefficients.reshape(*value.shape[:-1], self.count*(self.degree+1), self.width)


def assert_polynomial_family():
    """Score caller-chosen polynomial degrees using an independent integral."""
    from velnora.distributions.transforms import Polynomial
    for degree, count in ((1, 2), (3, 1)):
        coefficients = PolynomialCoefficients(3, degree, count)
        transform = Polynomial(coefficients, input_dim=3, count_degree=degree, count_sum=count)
        point = torch.tensor([-.7, .4, 1.1])
        raw = coefficients(point).detach().numpy().reshape(count, degree+1, 3)
        value = transform(point)
        derivative = np.zeros(3)
        for coordinate in range(3):
            baseline = point.clone()
            baseline[coordinate] = 0.
            expected = 0.
            for row in raw[:, :, coordinate]:
                squared = np.polynomial.polynomial.polymul(row, row)
                integral = np.polynomial.polynomial.polyint(squared)
                expected += np.polynomial.polynomial.polyval(float(point[coordinate]), integral)
                derivative[coordinate] += np.polynomial.polynomial.polyval(float(point[coordinate]), row)**2
            assert_close(value[coordinate]-transform(baseline)[coordinate], expected)
        value = transform(point.clone())
        # The baseline rounds a small stabilizer in this score; use the same
        # density roundoff allowance as the generated-volume measurement.
        np.testing.assert_allclose(transform.log_abs_det_jacobian(point, value).detach().numpy(),
                                   np.log(derivative).sum(), rtol=2e-4, atol=2e-4)


def assert_neural_scalar_family(transform, activation, units=2):
    """Independent sigmoid/tanh mixture relation on a one-coordinate flow."""
    from scipy.special import expit
    x = np.linspace(-3., 3., 61)
    y = transform(torch.tensor(x[:, None])).detach().numpy()[:, 0]
    activate = expit if activation == 'sigmoid' else np.tanh
    target = activate(y)
    def residual(parameters):
        slope = np.exp(parameters[:units])
        offset = parameters[units:2*units]
        logits = np.r_[parameters[2*units:], 0.]
        weight = np.exp(logits-np.max(logits))
        weight /= weight.sum()
        return (activate(x[:, None]*slope+offset)*weight).sum(-1)-target
    starts = [np.r_[np.log(np.array([.4, 1.2])*factor), [-.3, .3], 0.] for factor in (.5, 1., 2.)]
    _fit_relation(residual, starts, tolerance=3e-7)


def assert_affine_coupling_family(transform, width, split):
    points = torch.linspace(-.7, .8, width)
    baseline = transform(points.clone())
    assert_close(baseline[:split], points[:split].numpy())
    for coordinate in range(split, width):
        offset = torch.zeros(width)
        offset[coordinate] = .8
        left, right = transform(points-offset), transform(points+offset)
        assert_close(left+right, 2*baseline.detach().numpy())
        assert right[coordinate] > left[coordinate]
        others = [i for i in range(width) if i != coordinate]
        assert_close(left[others], baseline[others].detach().numpy())
