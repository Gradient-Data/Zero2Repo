# feature: F17
"""Acceptance checks for Bayesian experiment-design training failures."""

import pytest
import torch
import velnora
from velnora.contrib.oed.eig import posterior_eig

from _helpers import invoke, isolated_state


def test_f17_t08():
    # This is a real approximation family, scored on samples from a real model.
    # A nonfinite location makes its entire cross-entropy objective undefined;
    # validation is disabled on this distribution so the objective guard, rather
    # than constructor validation, is the public failure under examination.
    def model(design):
        theta = velnora.sample('theta', velnora.distributions.Normal(torch.zeros_like(design), 1.))
        velnora.sample('observation', velnora.distributions.Normal(theta * design, 1.))

    def run(initial):
        def guide(observations, design, observation_labels, target_labels):
            location = velnora.param('approximation_location', torch.tensor(initial))
            velnora.sample('theta', velnora.distributions.Normal(location.expand_as(design), 1.,
                                             validate_args=False))

        return invoke(
            posterior_eig, model, torch.tensor([0., 1.]),
            ['observation'], ['theta'], 128, 5, guide,
            velnora.optim.Adam({'lr': .1}),
            kwargs={'eig': False, 'return_history': True},
            allowed_exceptions=(ArithmeticError,),
        )

    with isolated_state(seed=1708, dtype=torch.float64, device='cpu'):
        good = run(2.)
        assert good.exception is None
        history, estimate = good.value
        assert history.shape == (5, 2)
        assert estimate.shape == (2,)
        assert torch.isfinite(history).all()
        assert torch.isfinite(estimate).all()
        # Establish that the baseline really trains rather than merely returning
        # a finite placeholder. The optimum of this restricted family is zero.
        assert 0. < velnora.param('approximation_location').item() < 2.

    with isolated_state(seed=1708, dtype=torch.float64, device='cpu'):
        bad = run(float('nan'))
        assert isinstance(bad.exception, ArithmeticError)


import math
import numpy as np
from scipy import special
from velnora.contrib.oed.eig import (
    nmc_eig, marginal_eig, marginal_likelihood_eig, vnmc_eig,
    donsker_varadhan_eig, lfire_eig,
)
from F01_helpers import assert_close
from F17_helpers import (
    gaussian_design, posterior_family, posterior_cross_entropy,
    observation_families, observation_objective, ode_call, PairScore,
    binary_design, binary_information, gaussian_nested_objective,
    assert_objective_candidates, posterior_objectives, observation_objectives,
    nested_objectives, score_objectives, assert_score_population_functional,
)


def test_f17_t01():
    # For this symmetric binary channel, inner integration depends only on
    # the empirical fair-coin proportion. With M=4096, its deviation > .06
    # has probability <= 2 exp(-2 M .06^2). This bounds log-marginal error
    # by -log(1-1.6*.06) < .102. The outer true log-ratio range is log(9);
    # N=4096 gives error > .13 probability <= 2 exp(-2 N (.13/log(9))^2).
    # Eight complete independent calls, each with 512 outer samples, give
    # the same 4096 total outer draws; union-bound all inner events, including implementations using independent
    # integration populations for each observation.
    # Total failure probability is below 2e-9; .233 includes both errors, not
    # a claim that nested Monte Carlo is unbiased.
    with isolated_state(seed=1701, dtype=torch.float64, device='cpu'):
        designs = torch.tensor([[0., .4], [.4, 0.]])
        answer = torch.stack([ode_call(nmc_eig, binary_design(), designs, ['a'], ['z'],
                                      N=512, M=4096) for _ in range(8)]).mean(0)
        assert answer.shape == designs.shape
        expected = binary_information(designs.numpy(), ['a'], ['z'])
        np.testing.assert_allclose(answer.numpy(), expected, rtol=0., atol=.233)
        # Independence is exact here: every conditional observation law is
        # identical, so no stochastic accuracy choice is needed for this arm.
        assert_close(answer[designs == 0], 0.)


def test_f17_t02():
    for labels, target in [(['a'], 'z'), (['b'], 'u'), (['a', 'b'], 'z')]:
        with isolated_state(seed=1702, dtype=torch.float64, device='cpu'):
            model, records = gaussian_design(nuisance=True)
            guide, snapshots = posterior_family(target=target, nuisance=True)
            designs = torch.tensor([[0., 1.5], [.7, 2.2]])
            value = ode_call(posterior_eig, model, designs, labels, [target],
                             4096, 0, guide, velnora.optim.Adam({'lr': .1}))
            assert value.shape == designs.shape
            assert_objective_candidates(value,
                (.5*math.log(2*math.pi*math.e)-ce for ce in posterior_objectives(
                    snapshots, labels, 4096, designs.shape, target, True)))


def test_f17_t03():
    for labels in (['b'], ['a', 'b']):
        for entropy in (True, False):
            with isolated_state(seed=1703, dtype=torch.float64, device='cpu'):
                model, records = gaussian_design()
                guide, snapshots = posterior_family(offset=1.5, train=True)
                result = ode_call(
                    posterior_eig, model, torch.tensor([.1, 1.3]), labels, ['z'],
                    256, 24, guide, velnora.optim.Adam({'lr': .08}),
                    eig=not entropy, return_history=entropy, final_num_samples=1024)
                if entropy:
                    history, value = result
                else:
                    value = result
                # Read the actual fitted family, not an assumption that it
                # reached the exact posterior. Scores use SciPy's normal law.
                if entropy:
                    for step, row in enumerate(history):
                        assert_objective_candidates(row, posterior_objectives(snapshots, labels, 256, (2,), step=step))
                candidates = posterior_objectives(snapshots, labels, 1024, (2,), step=24)
                assert_objective_candidates(value, candidates if entropy else
                    (.5*math.log(2*math.pi*math.e)-ce for ce in candidates))
                fitted = velnora.param('posterior_shift').item()
                assert fitted**2 < 1.5**2


def test_f17_t04():
    for paired, nuisance, labels in [(False, False, ['b']), (False, False, ['a', 'b']),
                                     (True, True, ['a', 'b'])]:
        with isolated_state(seed=1704, dtype=torch.float64, device='cpu'):
            model, records = gaussian_design(nuisance)
            marginal, conditional, snapshots = observation_families(True, nuisance)
            args = [model, torch.tensor([.2, 1.1]), labels, ['z'], 256, 20, marginal]
            if paired:
                args.append(conditional)
            args.append(velnora.optim.Adam({'lr': .08}))
            history, value = ode_call(marginal_likelihood_eig if paired else marginal_eig,
                                      *args, return_history=True, final_num_samples=1024)
            assert history.shape == (20, 2)
            for step, row in enumerate(history):
                assert_objective_candidates(row, observation_objectives(
                    records, snapshots, labels, 256, (2,), paired, nuisance, step=step))
            assert_objective_candidates(value, observation_objectives(
                records, snapshots, labels, 1024, (2,), paired, nuisance, step=20))
            assert velnora.param('marginal_shift').item()**2 < 1.4**2
            if paired:
                assert velnora.param('conditional_shift').item() != -1.1

    # The original's history mode changes the paired conditional gradient;
    # measure learning on its supported no-history training path instead.
    with isolated_state(seed=1744, dtype=torch.float64, device='cpu'):
        model, records = gaussian_design(True)
        marginal, conditional, snapshots = observation_families(True, True)
        value = ode_call(marginal_likelihood_eig, model, torch.tensor([.2, 1.1]),
                          ['a', 'b'], ['z'], 512, 24, marginal, conditional,
                          velnora.optim.Adam({'lr': .06}), final_num_samples=1024)
        ms, cs = (velnora.param(name).item() for name in ('marginal_shift', 'conditional_shift'))
        assert ms**2 < 1.4**2
        assert cs**2 < 1.1**2
        assert_objective_candidates(value, observation_objectives(
            records, snapshots, ['a', 'b'], 1024, (2,), True, True, step=24))


def test_f17_t05():
    # Exact differentiably sampled posterior makes every importance weight
    # equal to the marginal likelihood: nested bias and approximation error
    # vanish separately, even at finite inner count.
    for labels in (['a'], ['a', 'b']):
        with isolated_state(seed=1705, dtype=torch.float64, device='cpu'):
            model, records = gaussian_design()
            guide, snapshots = posterior_family(train=True)
            history, value = ode_call(vnmc_eig, model, torch.tensor([.2, 1.1]), labels,
                                      ['z'], (512, 8), 3, guide,
                                      velnora.optim.Adam({'lr': 0.}), return_history=True,
                                      final_num_samples=(2048, 16))
            for step, row in enumerate(history):
                assert_objective_candidates(row, nested_objectives(
                    records, snapshots, labels, (512, 8), (2,), step=step))
            assert_objective_candidates(value, nested_objectives(
                records, snapshots, labels, (2048, 16), (2,), step=3))


    with isolated_state(seed=1755, dtype=torch.float64, device='cpu'):
        model, records = gaussian_design()
        guide, snapshots = posterior_family(offset=.8, train=True)
        history, value = ode_call(vnmc_eig, model, torch.tensor([.2, 1.1]), ['a', 'b'],
                                  ['z'], (256, 16), 24, guide,
                                  velnora.optim.Adam({'lr': .04}), return_history=True,
                                  final_num_samples=(512, 32))
        for step, row in enumerate(history):
            assert_objective_candidates(row, nested_objectives(
                records, snapshots, ['a', 'b'], (256, 16), (2,), step=step))
        assert_objective_candidates(value, nested_objectives(
            records, snapshots, ['a', 'b'], (512, 32), (2,), step=24))
        assert velnora.param('posterior_shift').item()**2 < .8**2


def test_f17_t06():
    for labels in (['b'], ['a', 'b']):
        for entry in (lfire_eig, donsker_varadhan_eig):
            with isolated_state(seed=1706, dtype=torch.float64, device='cpu'):
                model, records = gaussian_design()
                score = PairScore()
                args = [model, torch.tensor([.2, 1.1]), labels, ['z'], 256]
                if entry is lfire_eig:
                    args.append(16)
                args += [4, score, velnora.optim.Adam({'lr': .03})]
                history, value = ode_call(entry, *args, return_history=True, final_num_samples=2048)
                for step, row in enumerate(history):
                    assert_objective_candidates(row, score_objectives(
                        score.calls, 256, entry is donsker_varadhan_eig, entry is lfire_eig, step=step))
                assert_objective_candidates(value, score_objectives(
                    score.calls, 2048 if entry is donsker_varadhan_eig else 16*2048,
                    entry is donsker_varadhan_eig, step=4))
                assert score.weight.item() != .4
                assert_score_population_functional(
                    entry, torch.tensor([.2, 1.1]), labels,
                    dv=entry is donsker_varadhan_eig)


    # Without a history request LFIRE uses its actual logistic training loss.
    # Check its learning effect on a fixed real joint/independent population,
    # rather than mistaking the history evaluation scores for logistic losses.
    with isolated_state(seed=1766, dtype=torch.float64, device='cpu'):
        model, records = gaussian_design()
        score = PairScore()
        value = ode_call(lfire_eig, model, torch.tensor([.2, 1.1]), ['a', 'b'],
                          ['z'], 1024, 16, 12, score, velnora.optim.Adam({'lr': .02}))
        # A separate, fixed real population measures the fitted logistic risk.
        rng = np.random.default_rng(1766)
        design = np.array([.2, 1.1])
        z = rng.normal(size=(100000, 2))
        other = rng.normal(size=(100000, 2))
        a = design*z+rng.normal(size=z.shape)
        b = .6*z+.7*rng.normal(size=z.shape)
        joint = (a-design*z)**2+(b-.6*z)**2
        independent = (a-design*other)**2+(b-.6*other)**2
        final_weight = score.weight.item()
        loss_before = (np.logaddexp(0., .4*joint)+np.logaddexp(0., -.4*independent)).mean()
        loss_after = (np.logaddexp(0., final_weight*joint)+np.logaddexp(0., -final_weight*independent)).mean()
        assert loss_after < loss_before
        assert_objective_candidates(value, score_objectives(score.calls, 16*1024, step=12))


def test_f17_t07():
    # The same trained family is evaluated on final designs. Expectations use
    # its fitted shift, so no exact-generalization assumption enters the test.
    with isolated_state(seed=1707, dtype=torch.float64, device='cpu'):
        model, records = gaussian_design()
        guide, snapshots = posterior_family(offset=1.2, train=True)
        final = torch.tensor([[0., .8, 1.5], [.3, 1.2, 2.]])
        history, value = ode_call(posterior_eig, model, torch.tensor([.2, .4]),
                                  ['a', 'b'], ['z'], 64, 8, guide,
                                  velnora.optim.Adam({'lr': .08}), eig=False,
                                  return_history=True, final_design=final,
                                  final_num_samples=3072)
        assert history.shape == (8, 2)
        assert value.shape == final.shape
        assert_objective_candidates(value, posterior_objectives(
            snapshots, ['a', 'b'], 3072, tuple(final.shape), step=8))
