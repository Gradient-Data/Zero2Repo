# feature: F07
"""Controlled inference coordinates and independently checked probability laws."""
import velnora
import math

import numpy as np
import pytest
import torch
from scipy import fft, linalg, stats

from velnora.infer.reparam import (
    DiscreteCosineReparam, HaarReparam, LatentStableReparam, LocScaleReparam,
    ProjectedNormalReparam, StudentTReparam, TransformReparam,
)

from _helpers import isolated_state
from F01_helpers import SAMPLE_COUNT, assert_close, assert_frequency
from F07_helpers import normal_vector_score, reparameterized_trace, reparameterized_draws


@pytest.fixture(autouse=True)
def coordinate_state():
    with isolated_state(seed=719, dtype=torch.float64):
        yield


def test_location_transform_student_coordinates():
    # FP-07.08: control the new coordinates, rather than merely count sites.
    loc = torch.tensor([-.8, 1.2, .4])
    scale = torch.tensor([.7, 1.6, 2.1])
    coordinate = torch.tensor([.3, -.6, 1.1])
    normal = velnora.distributions.Normal(loc, scale).to_event(1)
    for centered in (0., .4):
        trace = reparameterized_trace(normal, LocScaleReparam(centered=centered),
                                      {'value_decentered': coordinate})
        expected = loc + scale.pow(1 - centered) * (coordinate - centered * loc)
        assert_close(trace.nodes['value']['value'], expected.numpy())
        score = stats.norm.logpdf(coordinate.numpy(), centered * loc.numpy(),
                                 scale.numpy() ** centered).sum()
        assert_close(trace.log_prob_sum(), score)
    draws = reparameterized_draws(normal, LocScaleReparam(centered=0.), SAMPLE_COUNT)
    assert_frequency(draws <= loc + .3 * scale, np.full(3, stats.norm.cdf(.3)))

    transforms = [velnora.distributions.transforms.AffineTransform(.6, 1.3), velnora.distributions.transforms.ExpTransform()]
    transformed = velnora.distributions.TransformedDistribution(normal, transforms)
    trace = reparameterized_trace(transformed, TransformReparam(), {'value_base': coordinate})
    assert_close(trace.nodes['value']['value'], np.exp(.6 + 1.3 * coordinate.numpy()))
    assert_close(trace.log_prob_sum(), stats.norm.logpdf(coordinate.numpy(), loc, scale).sum())
    draws = reparameterized_draws(transformed, TransformReparam(), SAMPLE_COUNT)
    assert_frequency(draws <= torch.exp(.6 + 1.3 * (loc + .3 * scale)),
                     np.full(3, stats.norm.cdf(.3)))

    df = torch.tensor([3.5, 7., 12.])
    student = velnora.distributions.StudentT(df, loc, scale).to_event(1)
    for precision in (torch.tensor([.4, 1.3, 2.]), torch.tensor([1.8, .6, .9])):
        trace = reparameterized_trace(student, StudentTReparam(),
                                      {'value_gamma': precision, 'value': coordinate})
        assert_close(trace.nodes['value']['value'], coordinate.numpy())
        expected = stats.gamma.logpdf(precision.numpy(), df.numpy() / 2,
                                      scale=2 / df.numpy()).sum()
        expected += stats.norm.logpdf(coordinate.numpy(), loc.numpy(),
                                      scale.numpy() / np.sqrt(precision.numpy())).sum()
        assert_close(trace.log_prob_sum(), expected)
    draws = reparameterized_draws(student, StudentTReparam(), SAMPLE_COUNT)
    assert_frequency(draws <= loc + .6 * scale, stats.t.cdf(.6, df.numpy()))


def test_stable_projected_coordinates():
    # At stability two the stable law is Gaussian; the standard angle/radius
    # coordinates give a closed-form reconstruction independent of product code.
    angle = torch.tensor([-.6, .25, .8])
    exponential = torch.tensor([.4, 1.2, 2.3])
    loc = torch.tensor([-.7, .4, 1.1])
    scale = torch.tensor([.8, 1.4, .6])
    gaussian = velnora.distributions.Stable(torch.full((3,), 2.), torch.zeros(3), scale, loc).to_event(1)
    for noise in (exponential, exponential.flip(0)):
        trace = reparameterized_trace(gaussian, LatentStableReparam(),
                                      {'value_uniform': angle, 'value_exponential': noise})
        assert_close(trace.nodes['value']['value'], loc.numpy() + 2 * scale.numpy() * np.sin(angle.numpy()) * np.sqrt(noise.numpy()))
        expected = stats.uniform.logpdf(angle.numpy(), -math.pi / 2, math.pi).sum()
        expected += stats.expon.logpdf(noise.numpy()).sum()
        assert_close(trace.log_prob_sum(), expected)
    # A non-Gaussian stable law is checked against SciPy's independent law.
    stable = velnora.distributions.Stable(1.4, 0., 1.3, -.4)
    draws = reparameterized_draws(stable, LatentStableReparam(), SAMPLE_COUNT)
    for threshold in (-1.1, .6):
        assert_frequency(draws <= threshold, stats.levy_stable.cdf(threshold, 1.4, 0., loc=-.4, scale=1.3))

    concentration = torch.tensor([.9, -.5, .7])
    projected = velnora.distributions.ProjectedNormal(concentration)
    for noise in (torch.tensor([-.3, .8, .4]), torch.tensor([.7, -.2, -.9])):
        trace = reparameterized_trace(projected, ProjectedNormalReparam(), {'value_normal': noise})
        shifted = noise.numpy() + concentration.numpy()
        expected = shifted / np.linalg.norm(shifted)
        assert_close(trace.nodes['value']['value'], expected)
        assert_close(trace.log_prob_sum(), normal_vector_score(noise))
    draws = reparameterized_draws(projected, ProjectedNormalReparam(), SAMPLE_COUNT)
    assert_close(draws.norm(dim=-1), np.ones(SAMPLE_COUNT))
    for direction in (np.array([1., 0., 0.]), np.array([.3, -.4, .5])):
        probability = stats.norm.cdf(direction @ concentration.numpy() / np.linalg.norm(direction))
        assert_frequency(draws @ torch.tensor(direction) > 0, probability)


def test_time_coordinate_reconstruction_and_probability():
    # Independent orthonormal DCT-II reference; test both event axes.
    # Positive original variables also require the support-volume correction.
    scenarios = [
        ((4, 3), -2, DiscreteCosineReparam(dim=-2), 'value_dct',
         lambda z: fft.idct(z, type=2, norm='ortho', axis=-2)),
        ((4, 3), -1, DiscreteCosineReparam(dim=-1), 'value_dct',
         lambda z: fft.idct(z, type=2, norm='ortho', axis=-1)),
        # The two-point orthonormal Haar basis is the full Helmert basis.
        ((3, 2), -1, HaarReparam(dim=-1, flip=True), 'value_haar',
         lambda z: (z @ linalg.helmert(2, full=True))[..., ::-1].copy()),
    ]
    for shape, axis, reparam, site, inverse in scenarios:
        size = int(np.prod(shape))
        loc = torch.linspace(-.7, .8, size).reshape(shape)
        scale = torch.linspace(.6, 1.5, size).reshape(shape)
        law = velnora.distributions.LogNormal(loc, scale).to_event(2)
        coordinate = torch.linspace(-1.1, .9, size).reshape(shape)
        trace = reparameterized_trace(law, reparam, {site: coordinate})
        latent = inverse(coordinate.numpy())
        expected = np.exp(latent)
        assert_close(trace.nodes['value']['value'], expected)
        # The log chart cancels the lognormal volume term; time maps are orthogonal.
        expected_score = stats.norm.logpdf(latent, loc.numpy(), scale.numpy()).sum()
        assert_close(trace.log_prob_sum(), expected_score)
        draws = reparameterized_draws(law, reparam, SAMPLE_COUNT)
        assert_frequency(draws <= torch.exp(loc + .2 * scale),
                         np.full(shape, stats.norm.cdf(.2)))
