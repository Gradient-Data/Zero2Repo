# feature: F05
"""Acceptance checks for independent populations and dependency inspection."""
import numpy as np
import pytest
import torch
from scipy import stats
import velnora
from velnora.infer import TraceEnum_ELBO, config_enumerate
from velnora.infer.inspect import get_dependencies
from velnora.ops.indexing import Vindex

from _helpers import isolated_state
from F01_helpers import SAMPLE_COUNT, assert_close, assert_frequency
from F05_helpers import finite_state_evidence


@pytest.fixture(autouse=True)
def independence_state():
    with isolated_state(validation=True, dtype=torch.float64, device='cpu'):
        yield


def test_f05_t01():
    locations = torch.tensor([[-.8], [1.4]])

    def model():
        with velnora.plate('repetitions', SAMPLE_COUNT, dim=-3) as repetitions:
            with velnora.plate('rows', 2, dim=-2) as rows:
                with velnora.plate('columns', 3, dim=-1) as columns:
                    value = velnora.sample('value', velnora.distributions.Normal(locations, .7))
        return repetitions, rows, columns, value

    execution = velnora.poutine.trace(model).get_trace()
    repetitions, rows, columns, value = execution.nodes['_RETURN']['value']
    for indices, size in ((repetitions, SAMPLE_COUNT), (rows, 2), (columns, 3)):
        assert_close(indices.sort().values, np.arange(size))
    assert value.shape == (SAMPLE_COUNT, 2, 3)
    signs = value <= locations
    assert_frequency(signs, .5)
    # Joint indicators detect copying a draw along either population axis.
    assert_frequency(signs.all(-1), .125)
    assert_frequency(signs.all(-2), .25)
    execution.compute_log_prob()
    assert_close(execution.nodes['value']['log_prob'], stats.norm.logpdf(value.numpy(), locations.numpy(), .7))

    def sequential():
        result = {}
        for member in velnora.plate('members', 4):
            draws = []
            for step in range(1 + member % 3):
                draws.append(velnora.sample('member_{}_{}'.format(member, step),
                                         velnora.distributions.Normal(member + step, .6).expand((SAMPLE_COUNT,))))
            result[member] = draws
        return result

    execution = velnora.poutine.trace(sequential).get_trace()
    result = execution.nodes['_RETURN']['value']
    assert set(result) == set(range(4))
    assert all(len(result[member]) == 1 + member % 3 for member in result)
    execution.compute_log_prob()
    for member, draws in result.items():
        for step, value in enumerate(draws):
            assert_frequency(value <= member + step, .5)
            assert_close(execution.nodes['member_{}_{}'.format(member, step)]['log_prob'],
                         stats.norm.logpdf(value.numpy(), member + step, .6))
    assert_frequency((result[0][0] <= 0) & (result[1][0] <= 1), .25)


def test_f05_t02():
    data = torch.tensor([-.7, .3, 1.8, -2.1, .9, 2.4, -.2])
    for selection, batch_size in ((None, 3), (torch.tensor([5, 0, 3]), 3), (None, None)):
        def model():
            with velnora.plate('population', len(data), subsample_size=batch_size,
                            subsample=selection) as indices:
                selected = data[indices]
                velnora.sample('data', velnora.distributions.Normal(.4, 1.1), obs=selected)
            velnora.sample('outside', velnora.distributions.Normal(-.3, .8), obs=torch.tensor(.6))
            return indices, selected

        execution = velnora.poutine.trace(model).get_trace()
        indices, selected = execution.nodes['_RETURN']['value']
        count = len(data) if batch_size is None else batch_size
        assert indices.shape == (count,)
        assert indices.dtype == torch.long
        assert len(set(indices.tolist())) == count
        assert ((indices >= 0) & (indices < len(data))).all()
        if selection is not None:
            assert_close(indices, selection.numpy())
        if batch_size is None:
            assert_close(indices.sort().values, np.arange(len(data)))
        assert_close(selected, data.numpy()[indices.numpy()])
        execution.compute_log_prob()
        score = stats.norm.logpdf(data.numpy()[indices.numpy()], .4, 1.1) * len(data) / count
        assert_close(execution.nodes['data']['log_prob'], score)
        assert_close(execution.nodes['outside']['log_prob'], stats.norm.logpdf(.6, -.3, .8))
        assert_close(execution.log_prob_sum(), score.sum() + stats.norm.logpdf(.6, -.3, .8))


def test_f05_t03():
    data = torch.arange(5 * 7 * 3.).reshape(5, 7, 3) / 11
    rows, columns = torch.tensor([4, 1]), torch.tensor([6, 0, 3])
    with velnora.plate('rows', 5, subsample=rows, dim=-2):
        with velnora.plate('columns', 7, subsample=columns, dim=-1):
            selected = velnora.subsample(data, event_dim=1)
            parameter = velnora.param('selected_parameter', data.clone(), event_dim=1)
            full = velnora.param('full_parameter', data.clone())
    expected = data.numpy()[rows.numpy()][:, columns.numpy(), :]
    assert selected.shape == parameter.shape == (2, 3, 3)
    assert_close(selected, expected)
    assert_close(parameter, expected)
    assert_close(full, data.numpy())
    assert_close(velnora.param('selected_parameter'), data.numpy())
    # Event axes stay whole even when their size equals a population size.
    square = torch.arange(25.).reshape(5, 5)
    with velnora.plate('square_rows', 5, subsample=rows):
        assert_close(velnora.subsample(square, event_dim=1), square.numpy()[rows.numpy()])
        assert_close(velnora.param('square', square.clone(), event_dim=1), square.numpy()[rows.numpy()])


def test_f05_t04():
    def broadcast(size):
        with velnora.plate('population', 4):
            return velnora.sample('value', velnora.distributions.Normal(torch.zeros(size), 1.))

    assert broadcast(4).shape == (4,)
    with pytest.raises(ValueError):
        broadcast(3)

    def nested(dimension):
        with velnora.plate('outer', 2, dim=-2):
            with velnora.plate('inner', 3, dim=dimension):
                return velnora.sample('value', velnora.distributions.Normal(0., 1.))

    assert nested(-1).shape == (2, 3)
    with pytest.raises(ValueError):
        nested(-2)
    with velnora.plate('valid', 7, subsample_size=2, subsample=torch.tensor([5, 1])) as indices:
        assert_close(indices, [5, 1])
    with pytest.raises(ValueError):
        with velnora.plate('invalid', 7, subsample_size=3, subsample=torch.tensor([5, 1])):
            pass


def test_f05_t05():
    transition = torch.tensor([[[.82, .18], [.37, .63]], [[.56, .44], [.13, .87]]])
    emission = torch.tensor([[.9, .1], [.22, .78]])
    observations = torch.tensor([[0, 1], [1, 1], [0, 0], [1, 0], [1, 1]])
    for history in (1, 2):
        @config_enumerate
        def model():
            previous, current = torch.tensor(0), torch.tensor(0)
            with velnora.plate('sequences', 2, dim=-1):
                for time in velnora.markov(range(len(observations)), history=history):
                    probs = (Vindex(transition)[previous, current, :] if history == 2
                             else Vindex(transition[0])[current, :])
                    state = velnora.sample('state_{}'.format(time), velnora.distributions.Categorical(probs))
                    velnora.sample('observation_{}'.format(time),
                                velnora.distributions.Categorical(Vindex(emission)[state, :]), obs=observations[time])
                    previous, current = current, state

        expected = 0.
        for sequence in observations.numpy().T:
            def probability(past, state):
                return transition.numpy()[past[-2] if history == 2 else 0, past[-1], state]
            evidence = finite_state_evidence((0,) * history, 2, sequence, probability,
                                            lambda state, obs: emission.numpy()[state, obs])
            expected -= np.log(evidence)
        actual = TraceEnum_ELBO(max_plate_nesting=1).loss(model, lambda: None)
        np.testing.assert_allclose(actual, expected, rtol=2e-6, atol=2e-7)


def test_f05_t06():
    table = torch.arange(3 * 4 * 5.).reshape(3, 4, 5) / 7
    assert_close(Vindex(table)[2, :, 1], table.numpy()[2, :, 1])
    rows = torch.tensor([[2], [0]])
    columns = torch.tensor([[4, 1, 3]])
    expected = np.empty((2, 3, 4))
    for i in range(2):
        for j in range(3):
            expected[i, j] = table.numpy()[rows[i, 0], :, columns[0, j]]
    assert_close(Vindex(table)[rows, :, columns], expected)

    # Leading table batches and index enumeration dimensions broadcast together.
    batched = torch.stack((table, table + 10))
    enum_rows = torch.tensor([0, 2, 1]).reshape(3, 1, 1)
    plate_columns = torch.tensor([[4, 0], [1, 3]])
    expected = np.empty((3, 2, 2, 4))
    for e in range(3):
        for p in range(2):
            for b in range(2):
                expected[e, p, b] = batched.numpy()[b, enum_rows[e, 0, 0], :, plate_columns[p, b]]
    result = Vindex(batched)[..., enum_rows, :, plate_columns]
    assert result.shape == (3, 2, 2, 4)
    assert_close(result, expected)


def test_f05_t07():
    def model(branch):
        a = velnora.sample('a', velnora.distributions.Normal(0., 1.))
        b = velnora.sample('b', velnora.distributions.Normal(0., 1.))
        intermediate = velnora.deterministic('intermediate', a * 2)
        point = velnora.sample('point', velnora.distributions.Delta(intermediate))
        c = velnora.sample('c', velnora.distributions.Normal(point + (b if branch else 0.), 1.))
        velnora.sample('observed', velnora.distributions.Normal(c, 1.), obs=torch.tensor(.2))
        with velnora.poutine.mask(mask=False):
            velnora.sample('excluded', velnora.distributions.Normal(a, 1.), obs=torch.tensor(.3))
        velnora.sample('other_observed', velnora.distributions.Normal(b, 1.), obs=torch.tensor(-.4))

    for branch in (False, True):
        result = get_dependencies(model, model_args=(branch,))
        prior = {'a': {'a': set()}, 'b': {'b': set()},
                 'c': {'c': set(), 'a': set()},
                 'observed': {'observed': set(), 'c': set()},
                 'other_observed': {'other_observed': set(), 'b': set()}}
        posterior = {'a': {'a': set(), 'c': set()},
                     'b': {'b': set(), 'other_observed': set()},
                     'c': {'c': set(), 'observed': set()}}
        if branch:
            prior['c']['b'] = set()
            posterior['a']['b'] = set()
            posterior['b']['c'] = set()
        assert result['prior_dependencies'] == prior
        assert result['posterior_dependencies'] == posterior


def test_f05_t08():
    def model(aggregate):
        with velnora.plate('population', 4):
            a = velnora.sample('a', velnora.distributions.Normal(0., 1.))
            b = velnora.sample('b', velnora.distributions.Normal(a, 1.))
            if not aggregate:
                velnora.sample('observed', velnora.distributions.Normal(b, 1.), obs=torch.zeros(4))
        if aggregate:
            velnora.sample('observed', velnora.distributions.Normal(b.sum(), 1.), obs=torch.tensor(0.))
        with velnora.plate('separate', 3):
            velnora.sample('independent', velnora.distributions.Normal(0., 1.))

    for aggregate in (False, True):
        result = get_dependencies(model, model_kwargs={'aggregate': aggregate})
        assert result['prior_dependencies'] == {
            'a': {'a': set()}, 'b': {'a': set(), 'b': set()},
            'observed': {'b': set(), 'observed': set()},
            'independent': {'independent': set()}}
        assert result['posterior_dependencies'] == {
            'a': {'a': set(), 'b': set()},
            'b': {'b': {'population'} if aggregate else set(), 'observed': set()},
            'independent': {'independent': set()}}
