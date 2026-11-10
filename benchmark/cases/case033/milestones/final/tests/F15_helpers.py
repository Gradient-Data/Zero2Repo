# feature: F15
"""Caller-defined forecasting workloads and independent numerical observations."""
import math
import numpy as np
import torch
import velnora
from velnora.contrib.forecast import ForecastingModel, Forecaster
from F13_helpers import scalar_system, linear_joint


class CovariateForecast(ForecastingModel):
    def model(self, zero_data, covariates):
        self.predict(velnora.distributions.Normal(0., .5), covariates + zero_data)


def correlated_noise(duration):
    a, _, u, v, q, _ = scalar_system(duration)
    b = np.tile(np.array([[[1., -.7]]]), (duration, 1, 1))
    v = np.concatenate((v, -.5*v), -1)
    r = np.tile(np.array([[[.3, .18], [.18, .6]]]), (duration, 1, 1))
    tensor = torch.tensor
    noise = velnora.distributions.GaussianHMM(velnora.distributions.MultivariateNormal(tensor([.4]), tensor([[.8]])),
        tensor(a), velnora.distributions.MultivariateNormal(tensor(u), tensor(q)), tensor(b),
        velnora.distributions.MultivariateNormal(tensor(v), tensor(r)))
    mean, covariance = linear_joint([.4], [[.8]], a, u, q, b, v, r)
    return noise, (mean[:2*duration], covariance[:2*duration, :2*duration])


class CorrelatedForecast(ForecastingModel):
    def model(self, zero_data, covariates):
        noise, _ = correlated_noise(covariates.size(-2))
        self.predict(noise, covariates + zero_data)


class LevelForecast(ForecastingModel):
    def model(self, zero_data, covariates):
        level = velnora.sample('level', velnora.distributions.Normal(0., 1.))
        self.predict(velnora.distributions.Normal(0., .5), level.unsqueeze(-1) + covariates + zero_data)


class GroupForecast(ForecastingModel):
    def model(self, zero_data, covariates):
        level = velnora.sample('level', velnora.distributions.Normal(0., 1.))
        with velnora.plate('groups', zero_data.size(0), dim=-2):
            selected = velnora.subsample(covariates, event_dim=1)
            self.predict(velnora.distributions.Normal(0., .5), selected + level.unsqueeze(-1))


class SelectedGuide:
    def __init__(self, size, indices):
        self.size = size
        self.indices = indices
        self.create_plates = True

    def __call__(self, data, covariates):
        velnora.sample('level', velnora.distributions.Delta(torch.tensor(0.)))
        with velnora.plate('groups', self.size, dim=-2,
                        subsample=self.indices if self.create_plates else None):
            pass


def forecast_fit(model, data, covariates, **options):
    return Forecaster(model, data, covariates, num_steps=options.pop('num_steps', 0),
                      log_every=0, **options)


def normal_nll(residual, scale=.5):
    return .5*np.log(2*math.pi*scale**2) + np.asarray(residual)**2/(2*scale**2)


def check_draw_moments(draws, mean, covariance):
    values = draws.detach().numpy().reshape(draws.size(0), -1)
    mean, covariance = np.asarray(mean).reshape(-1), np.asarray(covariance)
    n = len(values)
    # Eight standard errors per coordinate/moment: negligible Gaussian tail
    # risk, while accepting independent samplers and different RNG sequences.
    np.testing.assert_array_less(abs(values.mean(0)-mean),
                                 8*np.sqrt(np.diag(covariance)/n)+.003)
    error = 8*np.sqrt((np.outer(np.diag(covariance), np.diag(covariance))+
                      covariance**2)/(n-1))+.003
    np.testing.assert_array_less(abs(np.cov(values, rowvar=False)-covariance), error)
