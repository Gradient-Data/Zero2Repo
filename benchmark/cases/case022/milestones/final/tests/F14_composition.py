# feature: F14
"""Acceptance checks for dataset concatenation and interleaving."""
from velnora import Dataset, concatenate_datasets, interleave_datasets
from velnora.features import ClassLabel, Features, List, Value

from _helpers import consume_prefix, deadline
from F01_helpers import assert_invalid
from F04_helpers import iterable_records
from F14_helpers import (assert_source_progression, composition_source_test,
                         composition_sources)


@composition_source_test
def test_vertical_union_and_semantic_alignment():
    left_features = Features({'record': {'name': Value('string'), 'label': ClassLabel(names=['red', 'blue'])},
                              'items': List(Value('null')), 'left': Value('int32')})
    right_features = Features({'items': List(Value('int64')),
                               'record': {'label': ClassLabel(names=['red', 'blue']), 'name': Value('string')},
                               'right': Value('string')})
    left = [{'record': {'name': 'alpha', 'label': 1}, 'items': [None, None], 'left': 17},
            {'record': {'name': 'beta', 'label': 0}, 'items': [], 'left': -8}]
    right = [{'record': {'label': 0, 'name': 'gamma'}, 'items': [4, 9], 'right': 'tail'}]
    expected = [dict(row, right=None) for row in left] + [dict(row, left=None) for row in right]
    for streaming in (False, True):
        def make(rows, features):
            finite = Dataset.from_list(rows, features=features)
            return finite.to_iterable_dataset() if streaming else finite
        inputs = [make(left, left_features), make(right, right_features)]
        result = concatenate_datasets(inputs)
        assert list(result) == expected
        assert result.features == Features({'record': right_features['record'], 'items': List(Value('int64')),
                                             'left': Value('int32'), 'right': Value('string')})
        # Reverse the inputs: null adoption must not depend on which comes first.
        assert list(concatenate_datasets(inputs[::-1])) == expected[2:] + expected[:2]
        # Beyond two inputs, every input still contributes in the supplied order.
        assert list(concatenate_datasets([inputs[1], inputs[0], inputs[1]])) == (
            expected[2:] + expected[:2] + expected[2:])
        null_schema = Features({'record': {'name': Value('null'), 'label': ClassLabel(names=['red', 'blue'])}})
        null_row = [{'record': {'name': None, 'label': 1}}]
        aligned = concatenate_datasets([make(null_row, null_schema), inputs[1]])
        assert list(aligned) == [dict(null_row[0], items=None, right=None)] + right
        assert aligned.features['record'] == right_features['record']
        for incompatible in (
            Features({'record': {'name': Value('string'), 'label': ClassLabel(names=['blue', 'red'])}}),
            Features({'record': {'name': Value('int64'), 'label': ClassLabel(names=['red', 'blue'])}}),
            Features({'items': List(Value('string'))}),
        ):
            bad_row = ({'items': ['bad']} if 'items' in incompatible else
                       {'record': {'name': 3 if incompatible['record']['name'] == Value('int64') else 'bad', 'label': 0}})
            bad = make([bad_row], incompatible)
            assert_invalid(lambda: list(concatenate_datasets([inputs[1], bad])), (ValueError,))
    assert_invalid(lambda: concatenate_datasets([]), (ValueError,))
    assert_invalid(lambda: list(concatenate_datasets([Dataset.from_list(left), iterable_records(left)])), (ValueError,))


@composition_source_test
def test_horizontal_alignment_and_exhaustion():
    left = [{'a': 11}, {'a': -3}, {'a': 8}]
    right = [{'b': 'x'}, {'b': 'y'}, {'b': 'z'}]
    for streaming in (False, True):
        make = iterable_records if streaming else Dataset.from_list
        assert list(concatenate_datasets([make(left), make(right)], axis=1)) == [
            {**a, **b} for a, b in zip(left, right)]
        third = [{'c': True}, {'c': None}, {'c': False}]
        assert list(concatenate_datasets([make(right), make(third), make(left)], axis=1)) == [
            {**b, **c, **a} for a, b, c in zip(left, right, third)]
        assert_invalid(lambda: list(concatenate_datasets([make(left), make(left)], axis=1)), (ValueError,))
        if streaming:
            for a_rows, b_rows, expected in [
                (left, right[:1], [{'a': 11, 'b': 'x'}, {'a': -3, 'b': None}, {'a': 8, 'b': None}]),
                (left[:1], right, [{'a': 11, 'b': 'x'}, {'a': None, 'b': 'y'}, {'a': None, 'b': 'z'}]),
            ]:
                result = list(concatenate_datasets([make(a_rows), make(b_rows)], axis=1))
                assert result == expected
        else:
            assert_invalid(lambda: list(concatenate_datasets([make(left), make(right[:1])], axis=1)), (ValueError,))


@composition_source_test
def test_round_robin_stopping_policies():
    for streaming in (False, True):
        sources = composition_sources([2, 3, 4], streaming)
        first = [(0, 0), (1, 0), (2, 0), (0, 1)]
        repeated = [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1),
                    (0, 0), (1, 2), (2, 2), (0, 1), (1, 0), (2, 3)]
        no_repeat = [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, 2), (2, 2), (2, 3)]
        if not streaming:
            first += [(1, 1), (2, 1)]
        for options, expected in [({}, first), ({'stopping_strategy': 'first_exhausted'}, first),
                                  ({'stopping_strategy': 'all_exhausted'}, repeated),
                                  ({'stopping_strategy': 'all_exhausted_without_replacement'}, no_repeat)]:
            assert list(interleave_datasets(sources, **options)) == [
                {'source': source, 'index': index} for source, index in expected]
        # The longest source is first here, so iterable repeating stops mid-round.
        sources = composition_sources([4, 2, 3], streaming)
        result = list(interleave_datasets(sources, stopping_strategy='all_exhausted'))
        assert [(r['source'], r['index']) for r in result] == (
            [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (0, 2), (1, 0), (2, 2), (0, 3)]
            + ([] if streaming else [(1, 1), (2, 0)]))


@composition_source_test
def test_weighted_choices_seed_distribution_and_validation():
    for streaming in (False, True):
        sources = composition_sources([128, 128, 128], streaming)
        def prefix(seed):
            return consume_prefix(interleave_datasets(sources, probabilities=[.15, .3, .55], seed=seed), limit=64)
        assert prefix(917) == prefix(917)
        counts = [0, 0, 0]
        positions = [[0, 0, 0] for _ in range(64)]
        with deadline(150):
            for seed in range(64):
                rows = prefix(seed)
                assert len(rows) == 64
                assert_source_progression(rows, [128, 128, 128])
                for position, row in enumerate(rows):
                    counts[row['source']] += 1
                    positions[position][row['source']] += 1
        # Also observe each choice position across runs: a fixed schedule with
        # the right pooled counts is not categorical sampling. Union bound over
        # 192 cells: 384*exp(-2*64*.42**2) < 6.1e-8 per access model.
        for counts_at_position in positions:
            for count, probability in zip(counts_at_position, [.15, .3, .55]):
                assert abs(count / 64 - probability) <= .42
        # 4096 categorical choices; Hoeffding and union bound over three sources
        # give a false rejection bound of 6*exp(-2*4096*.055**2) < 1.1e-10.
        for count, probability in zip(counts, [.15, .3, .55]):
            assert abs(count / 4096 - probability) <= .055
        make = iterable_records if streaming else Dataset.from_list
        a, b = make([{'x': 1}]), make([{'x': 'incompatible'}])
        assert_invalid(lambda: list(interleave_datasets([a, b], probabilities=[.4, .6], seed=19)), (ValueError,))
    assert_invalid(lambda: interleave_datasets([]), (ValueError,))
    assert_invalid(lambda: list(interleave_datasets([Dataset.from_dict({'x': [1]}), iterable_records([{'x': 2}])])), (ValueError,))


@composition_source_test
def test_weighted_exhaustion_and_remaining_proportions():
    for streaming in (False, True):
        sources = composition_sources([2, 5, 7], streaming)
        for strategy in ('first_exhausted', 'all_exhausted', 'all_exhausted_without_replacement'):
            saw_repetition = False
            for seed in range(12):
                with deadline(30):
                    rows = list(interleave_datasets(sources, probabilities=[.6, .3, .1], seed=seed,
                                                    stopping_strategy=strategy))
                assert rows
                counts = assert_source_progression(rows, [2, 5, 7], repeating=strategy == 'all_exhausted')
                before = counts.copy()
                before[rows[-1]['source']] -= 1
                if strategy == 'first_exhausted':
                    assert all(a < b for a, b in zip(before, [2, 5, 7]))
                    assert any(a == b for a, b in zip(counts, [2, 5, 7]))
                elif strategy == 'all_exhausted':
                    assert all(a >= b for a, b in zip(counts, [2, 5, 7]))
                    assert any(a < b for a, b in zip(before, [2, 5, 7]))
                    saw_repetition |= any(a > b for a, b in zip(counts, [2, 5, 7]))
                else:
                    assert counts == [2, 5, 7]
            if strategy == 'all_exhausted':
                # Repetition need not occur in every random run; with this
                # imbalance, its absence across all twelve runs is negligible.
                assert saw_repetition
        assert_invalid(lambda: list(interleave_datasets(sources, stopping_strategy='unknown')), (ValueError,))
        sources = composition_sources([1, 256, 256], streaming)
        counts = [0, 0, 0]
        with deadline(150):
            for seed in range(64):
                rows = list(interleave_datasets(sources, probabilities=[.5, .125, .375], seed=seed,
                                               stopping_strategy='all_exhausted_without_replacement'))
                assert assert_source_progression(rows, [1, 256, 256]) == [1, 256, 256]
                exhausted_at = next(i for i, row in enumerate(rows) if row['source'] == 0)
                tail = rows[exhausted_at + 1:exhausted_at + 65]
                assert len(tail) == 64
                for row in tail:
                    counts[row['source']] += 1
        # After removal, the remaining categorical probabilities are .25/.75.
        # 4096 draws, two cells: Hoeffding union bound < 7e-11 at .055.
        assert counts[0] == 0
        for count, probability in zip(counts[1:], [.25, .75]):
            assert abs(count / 4096 - probability) <= .055


@composition_source_test
def test_weighted_finite_zero_and_empty_sources():
    features = Features({'source': Value('int64'), 'index': Value('int64')})
    empty = Dataset.from_dict({'source': [], 'index': []}, features=features)
    live = composition_sources([3, 5], False)
    for inactive in (empty, Dataset.from_list([{'source': 9, 'index': 0}], features=features)):
        with deadline(30):
            result = list(interleave_datasets([inactive] + live, probabilities=[0, .4, .6], seed=317))
        counts = assert_source_progression(result, [3, 5])
        assert result
        assert counts[result[-1]['source']] == [3, 5][result[-1]['source']]
        before = counts.copy()
        before[result[-1]['source']] -= 1
        assert all(a < b for a, b in zip(before, [3, 5]))
        assert_invalid(lambda: list(interleave_datasets([inactive] + live, probabilities=[0, .4, .6],
                                                       stopping_strategy='all_exhausted', seed=317)), (ValueError,))
    for strategy in ('first_exhausted', 'all_exhausted'):
        assert_invalid(lambda: list(interleave_datasets([empty] + live, probabilities=[.2, .3, .5],
                                                       stopping_strategy=strategy, seed=317)), (ValueError,))
