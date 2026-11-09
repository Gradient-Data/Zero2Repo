# feature: F13
"""Acceptance checks for finite row selection, ordering and partitioning."""
from collections import Counter

from velnora import Dataset, ReadInstruction
from velnora.features import ClassLabel, Features, Value

from _helpers import deadline
from F01_helpers import assert_invalid
from F13_helpers import (assert_uniform_row_positions, independent_seeded_partitions,
                         row_operation_source_test, split_file_loader)


@row_operation_source_test
def test_ordered_selection_and_prefixes():
    rows = [{'id': i, 'label': i % 2, 'text': str(i)} for i in range(7)]
    features = Features({'id': Value('int32'), 'label': ClassLabel(names=['a', 'b']),
                         'text': Value('string')})
    dataset = Dataset.from_list(rows, features=features)
    for source_rows, source in ((rows, dataset),
                                ([rows[i] for i in [5, 1, 4, 0]], dataset.select([5, 1, 4, 0]))):
        for positions in ([2, 0, 2, 1], [], list(range(len(source_rows)))):
            result = source.select(positions)
            assert list(result) == [source_rows[i] for i in positions]
            assert result.features == features
        for size in (0, 2, len(source_rows)):
            result = source.take(size)
            assert list(result) == source_rows[:size]
            assert result.features == features
        for size in (0, 2, len(source_rows) - 1):
            result = source.skip(size)
            assert list(result) == source_rows[size:]
            assert result.features == features
        for positions in ([len(source_rows)], [0, len(source_rows) + 2]):
            assert_invalid(lambda: list(source.select(positions)), (IndexError,))
        assert_invalid(lambda: list(source.take(len(source_rows) + 1)), (IndexError,))


@row_operation_source_test
def test_sort_priorities_directions_and_nulls():
    rows = [{'id': i, 'a': a, 'b': b} for i, (a, b) in enumerate(
        [(2, 1), (1, 4), (None, 3), (1, 2), (2, None), (1, 2), (None, 1)])]
    dataset = Dataset.from_list(rows)
    # Compare key values, leaving fully tied records free to appear in either order.
    result = list(dataset.sort('a'))
    assert [r['a'] for r in result] == [1, 1, 1, 2, 2, None, None]
    assert sorted(result, key=lambda r: r['id']) == rows
    scenarios = [
        ({}, [(1, 2), (1, 2), (1, 4), (2, 1), (2, None), (None, 1), (None, 3)]),
        ({'reverse': [False, True]}, [(1, 4), (1, 2), (1, 2), (2, 1), (2, None), (None, 3), (None, 1)]),
        ({'reverse': True}, [(2, 1), (2, None), (1, 4), (1, 2), (1, 2), (None, 3), (None, 1)]),
        ({'null_placement': 'at_start'}, [(None, 1), (None, 3), (1, 2), (1, 2), (1, 4), (2, None), (2, 1)]),
    ]
    for options, expected in scenarios:
        result = list(dataset.sort(['a', 'b'], **options))
        assert [(r['a'], r['b']) for r in result] == expected
        assert sorted(result, key=lambda r: r['id']) == rows
    result = list(dataset.sort(['b', 'a']))
    assert [(r['b'], r['a']) for r in result] == [
        (1, 2), (1, None), (2, 1), (2, 1), (3, None), (4, 1), (None, 2)]
    # A third key orders the records tied on the first two.
    result = list(dataset.sort(['a', 'b', 'id'], reverse=[False, False, True]))
    assert [r['id'] for r in result] == [5, 3, 1, 0, 4, 6, 2]
    assert_invalid(lambda: list(dataset.sort('missing')), (ValueError,))
    assert_invalid(lambda: list(dataset.sort(['a', 'b'], reverse=[False])), (ValueError,))


@row_operation_source_test
def test_seeded_shuffle_permutation_and_positions():
    rows = [{'id': i, 'text': f'row-{i}'} for i in range(4)]
    dataset = Dataset.from_list(rows)
    for seed in (17, 891):
        first = list(dataset.shuffle(seed=seed, load_from_cache_file=False))
        second = list(Dataset.from_list(rows).shuffle(seed=seed, load_from_cache_file=False))
        assert first == second
        assert sorted(first, key=lambda row: row['id']) == rows
    with deadline(120):
        permutations = [list(dataset.shuffle(seed=seed, load_from_cache_file=False))
                        for seed in range(4096)]
    assert_uniform_row_positions(permutations, rows)


@row_operation_source_test
def test_partition_sizes_order_and_seed():
    rows = [{'id': i, 'text': f'row-{i}'} for i in range(11)]
    # Each entry isolates an omitted size, rounding rule, or unused remainder.
    scenarios = [({}, 8, 3), ({'test_size': 3}, 8, 3), ({'train_size': 4}, 4, 7),
                 ({'test_size': .3}, 7, 4), ({'train_size': .3}, 3, 8),
                 ({'train_size': 4, 'test_size': 2}, 4, 2),
                 ({'train_size': .3, 'test_size': .3}, 3, 4)]
    for options, n_train, n_test in scenarios:
        split = Dataset.from_list(rows).train_test_split(shuffle=False, **options)
        assert list(split['train']) == rows[:n_train]
        assert list(split['test']) == rows[n_train:n_train + n_test]
        first, second = independent_seeded_partitions(rows, seed=137, **options)
        assert first == second
        assert len(first['train']) == n_train and len(first['test']) == n_test
        combined = first['train'] + first['test']
        ids = [row['id'] for row in combined]
        assert len(set(ids)) == n_train + n_test
        assert all(row == rows[row['id']] for row in combined)
    # Default shuffling must actually permute, but no single seed must differ.
    ordered = {'train': rows[:8], 'test': rows[8:]}
    outcomes = [independent_seeded_partitions(rows, seed=seed)[0] for seed in range(16)]
    assert any(outcome != ordered for outcome in outcomes)
    assert any(outcome != outcomes[0] for outcome in outcomes[1:])


@row_operation_source_test
def test_partition_invalid_sizes_and_empty():
    dataset = Dataset.from_dict({'id': list(range(9))})
    valid = dataset.train_test_split(test_size=2, shuffle=False)
    assert list(valid['train']['id']) == list(range(7))
    assert list(valid['test']['id']) == [7, 8]
    for field in ('train_size', 'test_size'):
        for value in (0, -1, 9, 10, 0.0, -.1, 1.0, 1.1):
            assert_invalid(lambda: dataset.train_test_split(**{field: value}), (ValueError,))
    for options in ({'train_size': 5, 'test_size': 5},
                    {'train_size': .7, 'test_size': .4},
                    {'train_size': .01}, {'test_size': .99}):
        assert_invalid(lambda: dataset.train_test_split(**options), (ValueError,))
    empty = Dataset.from_dict({'id': []}).train_test_split()
    assert list(empty['train']) == []
    assert list(empty['test']) == []


@row_operation_source_test
def test_stratified_counts_members_and_rejections():
    features = Features({'id': Value('int64'), 'label': ClassLabel(names=['a', 'b', 'c'])})
    # Integral allocations and nonintegral allocations exercise different promises.
    for sizes, options in [([20, 12, 8], {'train_size': 20, 'test_size': 10}),
                           ([17, 9, 5], {'train_size': 13, 'test_size': 11})]:
        rows = [{'id': i, 'label': label} for i, label in enumerate(
            [label for label, count in enumerate(sizes) for _ in range(count)])]
        for seed in range(12):
            split = Dataset.from_list(rows, features=features).train_test_split(
                stratify_by_column='label', seed=seed, load_from_cache_file=False, **options)
            combined = list(split['train']) + list(split['test'])
            assert len({r['id'] for r in combined}) == sum(options.values())
            assert all(row == rows[row['id']] for row in combined)
            for name, bound in [('train', 1), ('test', 2)]:
                assert len(split[name]) == options[name + '_size']
                counts = Counter(split[name]['label'])
                for label, count in enumerate(sizes):
                    numerator = count * len(split[name])
                    target = numerator / len(rows)
                    if numerator % len(rows) == 0:
                        assert counts[label] == numerator // len(rows)
                    else:
                        assert abs(counts[label] - target) < bound
    base = Dataset.from_dict({'id': list(range(12)), 'label': [0] * 4 + [1] * 4 + [2] * 4},
                             features=features)
    for options in ({'shuffle': False}, {'train_size': 2}, {'test_size': 2}):
        assert_invalid(lambda: base.train_test_split(stratify_by_column='label', **options), (ValueError,))
    numeric = Dataset.from_dict({'id': list(range(12)), 'label': [0] * 6 + [1] * 6})
    assert_invalid(lambda: numeric.train_test_split(stratify_by_column='label'), (ValueError,))
    singleton = Dataset.from_dict({'id': list(range(9)), 'label': [0] * 4 + [1] * 4 + [2]},
                                  features=features)
    assert_invalid(lambda: singleton.train_test_split(stratify_by_column='label'), (ValueError,))


@row_operation_source_test
def test_contiguous_and_cyclic_shards():
    rows = [{'id': i, 'text': str(i)} for i in range(11)]
    dataset = Dataset.from_list(rows)
    for count in (1, 3, 11):
        start = 0
        for index in range(count):
            length = len(rows) // count + (index < len(rows) % count)
            assert list(dataset.shard(count, index)) == rows[start:start + length]
            assert list(dataset.shard(count, index, contiguous=True)) == rows[start:start + length]
            assert list(dataset.shard(count, index, contiguous=False)) == rows[index::count]
            start += length
    for index in (-1, 3):
        assert_invalid(lambda: list(dataset.shard(3, index)), (ValueError,))


@row_operation_source_test
def test_finite_repeat():
    rows = [{'id': i, 'text': str(i)} for i in (7, 2, 9)]
    dataset = Dataset.from_list(rows)
    for count in (0, 1, 3):
        assert list(dataset.repeat(count)) == rows * count
    assert_invalid(lambda: list(dataset.repeat(None)), (ValueError,))


@row_operation_source_test
def test_absolute_split_intervals_and_concatenation():
    training, testing = list(range(13)), list(range(100, 107))
    with split_file_loader(training, testing) as load:
        cases = [('train[2:6]', training[2:6]), ('train[-5:-1]', training[-5:-1]),
                 ('train[:3]', training[:3]), ('train[10:]', training[10:]),
                 ('train[-3:]', training[-3:]), ('train[:]', training),
                 ('test[1:4]+train[2:5]+test[:1]', testing[1:4] + training[2:5] + testing[:1])]
        for expression, expected in cases:
            assert list(load(expression)) == [{'value': value} for value in expected]
        for expression in ('missing[:2]',):
            assert_invalid(lambda: list(load(expression)), (ValueError,))


@row_operation_source_test
def test_percentage_split_rounding_and_bounds():
    training, testing = list(range(250)), list(range(31))
    with split_file_loader(training, testing) as load:
        # Explicit known boundaries: 2.5 -> 2, 7.5 -> 8; 50% of 31 -> 16.
        cases = [('train[1%:3%]', training[2:8]), ('test[:50%]', testing[:16]),
                 ('train[-3%:-1%]', training[242:248]),
                 (ReadInstruction('train', from_=1, to=3, unit='%',
                                  rounding='pct1_dropremainder'), training[2:6]),
                 (ReadInstruction('train', from_=0, to=100, unit='%',
                                  rounding='pct1_dropremainder'), training[:200])]
        for expression, expected in cases:
            assert list(load(expression)) == [{'value': value} for value in expected]
        for expression in ('train[:101%]', 'train[-101%:]',
                           ReadInstruction('test', from_=0, to=50, unit='%',
                                           rounding='pct1_dropremainder')):
            assert_invalid(lambda: list(load(expression)), (ValueError,))
