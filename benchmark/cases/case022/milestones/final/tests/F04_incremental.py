# feature: F04
"""Acceptance checks for incremental iteration and grouped datasets."""
from collections import Counter

from velnora import Dataset, IterableDataset

from _helpers import consume_prefix, deadline
from F01_helpers import assert_invalid
from F04_helpers import (endless_records, finite_and_iterable, group_columns,
                         iterable_records)


def test_restartable_incremental_rows_and_columns():
    rows = [{'number': 19, 'text': 'oak'}, {'number': -3, 'text': ''},
            {'number': 8, 'text': '雪'}, {'number': 27, 'text': 'elm'}]
    for dataset in (iterable_records(rows), Dataset.from_list(rows).to_iterable_dataset(num_shards=2)):
        assert list(dataset) == rows
        assert list(dataset) == rows
        for column in rows[0]:
            assert list(dataset[column]) == [row[column] for row in rows]
        assert_invalid(lambda: list(dataset[0]), (TypeError, KeyError, ValueError))
    # A real unbounded producer rules out materializing the source before yielding.
    # The deadline is a hang guard, not a throughput or prefetch requirement.
    with deadline(30):
        dataset = IterableDataset.from_generator(endless_records)
        assert consume_prefix(dataset, limit=7) == [
            {'number': i, 'text': str(i)} for i in range(7)]
        assert consume_prefix(dataset['number'], limit=5) == list(range(5))


def test_take_and_skip_boundaries():
    rows = [{'number': i, 'text': str(i)} for i in [11, -4, 8, 2, 19]]
    for length in (0, 2, len(rows), len(rows) + 6):
        assert list(iterable_records(rows).take(length)) == rows[:length]
        assert list(iterable_records(rows).skip(length)) == rows[length:]
    assert list(iterable_records(rows).skip(1).take(3)) == rows[1:4]


def test_iteration_batches_and_repetition():
    rows = [{'number': i, 'text': str(i)} for i in [17, 2, -5, 31, 6, 9, 23]]
    for size in (1, 3, 10):
        expected = [group_columns(rows[start:start + size]) for start in range(0, len(rows), size)]
        assert list(iterable_records(rows).iter(batch_size=size)) == expected
        assert list(iterable_records(rows).iter(batch_size=size, drop_last_batch=True)) == [
            batch for batch in expected if len(batch['number']) == size]
    for repetitions in (0, 1, 3):
        assert list(iterable_records(rows).repeat(repetitions)) == rows * repetitions
    with deadline(30):
        assert consume_prefix(iterable_records(rows).repeat(None), limit=18) == (rows * 3)[:18]


def test_unshuffled_checkpoint_rows_and_batches():
    rows = [{'number': i, 'text': str(i)} for i in range(11)]
    # Exercise both producer-backed and converted/sharded public sources.
    for converted, make in ((False, lambda: iterable_records(rows)),
                            (True, lambda: Dataset.from_list(rows).to_iterable_dataset(num_shards=3))):
        for batched in (False, True):
            dataset = make()
            iterator = dataset.iter(batch_size=3) if batched else iter(dataset)
            prefix = consume_prefix(iterator, limit=2)
            expected_prefix = [group_columns(rows[:3]), group_columns(rows[3:6])] if batched else rows[:2]
            assert prefix == expected_prefix
            checkpoint = dataset.state_dict()
            # Advancing the original must not change the captured checkpoint.
            assert list(iterator) == ([group_columns(rows[i:i + 3]) for i in range(6, 11, 3)]
                                      if batched else rows[2:])
            # Converted sources require the same consumption mode and batch size
            # on restore; see the documented baseline limitation in the ledger.
            if not converted or not batched:
                restored = make()
                restored.load_state_dict(checkpoint)
                assert list(restored) == rows[6 if batched else 2:]
            if not converted or batched:
                restored_batches = make()
                restored_batches.load_state_dict(checkpoint)
                start = 6 if batched else 2
                assert list(restored_batches.iter(batch_size=3)) == [
                    group_columns(rows[i:i + 3]) for i in range(start, len(rows), 3)]


def test_seeded_shuffle_and_epoch():
    rows = [{'number': i, 'text': str(i)} for i in range(24)]
    for buffer_size in (5, len(rows)):
        orders = []
        for epoch in range(12):
            pair = []
            for _ in range(2):
                dataset = iterable_records(rows).shuffle(seed=871, buffer_size=buffer_size)
                dataset.set_epoch(epoch)
                shuffled = list(dataset)
                assert sorted(shuffled, key=lambda row: row['number']) == rows
                pair.append(shuffled)
            assert pair[0] == pair[1]
            orders.append(pair[0])
        # No demand that every pair of epochs differ, or follow a distribution.
        assert any(order != orders[0] for order in orders[1:])


def test_full_source_shuffle_position_distribution():
    rows = [{'number': i, 'text': str(i)} for i in range(4)]
    samples = 4096
    counts = [Counter() for _ in rows]
    with deadline(90):
        for seed in range(samples):
            shuffled = list(iterable_records(rows).shuffle(seed=seed, buffer_size=len(rows)))
            assert sorted(shuffled, key=lambda row: row['number']) == rows
            for position, row in enumerate(shuffled):
                counts[row['number']][position] += 1
    # For independent uniform permutations, Hoeffding + union bound over 16
    # cells gives P(any error > .055) <= 32 exp(-2*4096*.055**2) < 6e-10.
    # This leaves substantial room for sampling noise and fixes no seed mapping.
    for positions in counts:
        for position in range(len(rows)):
            assert abs(positions[position] / samples - 1 / len(rows)) <= .055


def test_fixed_size_grouped_dataset_rows():
    rows = [{'number': i, 'text': str(i)} for i in [9, -3, 18, 5, 2, 27, 4]]
    for dataset in finite_and_iterable(rows):
        for size in (1, 3, 10):
            expected = [group_columns(rows[i:i + size]) for i in range(0, len(rows), size)]
            assert list(dataset.batch(batch_size=size)) == expected
            # Finite grouping cannot reliably drop the entire source (baseline
            # map returns the original rows when no batch is processed).
            if size <= len(rows) or isinstance(dataset, IterableDataset):
                assert list(dataset.batch(batch_size=size, drop_last_batch=True)) == [
                    group for group in expected if len(group['number']) == size]
        assert_invalid(lambda: list(dataset.batch()), (ValueError,))


def test_consecutive_column_grouped_dataset_rows():
    rows = [{'key': key, 'subkey': subkey, 'number': i}
            for i, (key, subkey) in enumerate([
                ('a', 1), ('a', 1), ('a', 2), ('a', 2), ('a', 2),
                ('b', 2), ('b', 1), ('a', 1), ('a', 1)])]
    # Explicit source spans are an independent oracle, not a product round trip.
    for dataset in finite_and_iterable(rows):
        for columns, spans in [('key', [(0, 5), (5, 7), (7, 9)]),
                               (['key', 'subkey'], [(0, 2), (2, 5), (5, 6), (6, 7), (7, 9)])]:
            expected = [group_columns(rows[start:end]) for start, end in spans]
            assert list(dataset.batch(by_column=columns)) == expected
            # A reading batch boundary must neither split nor merge value runs.
            assert list(dataset.batch(batch_size=2, by_column=columns)) == expected
