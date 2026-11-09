# feature: F12
"""Public record transformation and filtering acceptance checks."""
import asyncio
from copy import deepcopy

from velnora import Dataset, DatasetDict, IterableDataset, IterableDatasetDict
from velnora.features import Features, Value
from pyarrow import ArrowInvalid, ArrowTypeError

from _helpers import consume_prefix, deadline, observe
from F04_helpers import endless_records, finite_and_iterable, iterable_records
from F11_helpers import assert_column_source, column_models, column_snapshot
from F12_helpers import transformation_source_test


@transformation_source_test
def test_record_and_batch_mapping():
    rows = [{'x': x, 'tag': tag} for x, tag in [(8, 'oak'), (-3, 'elm'), (5, 'ash')]]
    for dataset in finite_and_iterable(rows):
        before = column_snapshot(dataset)
        result = dataset.map(lambda row: {'x': row['x'] * 2, 'length': len(row['tag'])})
        assert list(result) == [{'x': r['x'] * 2, 'tag': r['tag'], 'length': len(r['tag'])} for r in rows]
        result = dataset.map(lambda batch: {'x': [x + 7 for x in batch['x']]}, batched=True, batch_size=2)
        assert list(result) == [{'x': r['x'] + 7, 'tag': r['tag']} for r in rows]
        assert_column_source(dataset, before)
    from F12_helpers import cpu_mapping_effect
    cpu_mapping_effect()


@transformation_source_test
def test_selected_columns_indices_and_removal():
    rows = [{'x': x, 'tag': tag} for x, tag in [(9, 'a'), (-4, 'bee'), (2, 'cedar')]]
    for dataset in finite_and_iterable(rows):
        result = dataset.map(lambda tag, x, index: {'x': x + index, 'size': len(tag)},
                             input_columns=['tag', 'x'], with_indices=True, remove_columns=['x', 'tag'])
        assert list(result) == [{'x': r['x'] + i, 'size': len(r['tag'])} for i, r in enumerate(rows)]
        result = dataset.map(lambda xs, indices: {'x': [x - i for x, i in zip(xs, indices)]},
                             input_columns=['x'], with_indices=True, remove_columns=['x'],
                             batched=True, batch_size=2)
        assert list(result) == [{'x': r['x'] - i, 'tag': r['tag']} for i, r in enumerate(rows)]


@transformation_source_test
def test_variable_batches_and_validation():
    rows = [{'x': i} for i in range(1003)]
    for dataset in finite_and_iterable(rows):
        sizes = []
        def batch_sizes(batch):
            sizes.append(len(batch['x']))
            return {'size': [len(batch['x'])] * len(batch['x'])}
        result = list(dataset.map(batch_sizes, batched=True))
        assert len(result) == len(rows)
        assert sum(sizes) == len(rows) and all(0 < size <= 1000 for size in sizes)
        assert [r['x'] for r in result] == list(range(1003))
        for omit in (False, True):
            short = finite_and_iterable(rows[:7])[0 if isinstance(dataset, Dataset) else 1]
            result = short.map(batch_sizes, batched=True, batch_size=3, drop_last_batch=omit)
            assert list(result) == [{'x': i, 'size': 3 if i < 6 else 1} for i in range(6 if omit else 7)]
        for copies in (0, 2):
            result = dataset.map(lambda b: {'y': [x * 3 for x in b['x'] for _ in range(copies)]},
                                 batched=True, batch_size=4, remove_columns=['x'])
            assert list(result) == [{'y': i * 3} for i in range(1003) for _ in range(copies)]
        for operation in (lambda: dataset.map(lambda b: {'y': [1]}, batched=True, batch_size=3),
                          lambda: dataset.map(lambda b: {'a': [1], 'b': [1, 2]},
                                              batched=True, remove_columns=['x'])):
            outcome = observe(operation, timeout=30, consume=list)
            assert isinstance(outcome.error, (ArrowInvalid, ValueError)), outcome


@transformation_source_test
def test_filter_modes_and_empty_schema():
    rows = [{'x': x, 'tag': str(x)} for x in [12, -3, 8, 1, 7, 0, 22]]
    features = Features({'x': Value('int64'), 'tag': Value('string')})
    expected = [r for i, r in enumerate(rows) if r['x'] > i]
    for dataset in column_models(rows, features):
        assert list(dataset.filter(lambda r: r['x'] % 2 == 0)) == [r for r in rows if r['x'] % 2 == 0]
        assert list(dataset.filter(lambda x, i: x > i, input_columns=['x'], with_indices=True)) == expected
        assert list(dataset.filter(lambda xs, indices: [x > i for x, i in zip(xs, indices)],
                                   input_columns=['x'], with_indices=True, batched=True, batch_size=3)) == expected
        empty = dataset.filter(lambda r: False)
        assert list(empty) == []
        assert empty.features == features


@transformation_source_test
def test_async_mapping_and_filtering():
    rows = [{'x': x} for x in [7, 2, 9, 0, 5]]
    async def transform(row):
        await asyncio.sleep((10 - row['x']) * .001)
        return {'square': row['x'] ** 2}
    async def predicate(row):
        await asyncio.sleep((10 - row['x']) * .001)
        return row['x'] % 2 == 1
    for dataset in finite_and_iterable(rows):
        assert list(dataset.map(transform)) == [dict(r, square=r['x'] ** 2) for r in rows]
        assert list(dataset.filter(predicate)) == [r for r in rows if r['x'] % 2 == 1]


@transformation_source_test
def test_caller_errors_fail_the_request():
    def broken(row):
        if row['x'] == 2:
            raise RuntimeError('Caller operation failed')
        return {'ok': True}
    async def async_broken(row):
        await asyncio.sleep(.001)
        return broken(row)
    def predicate(row):
        broken(row)
        return True
    async def async_predicate(row):
        await async_broken(row)
        return True
    for dataset in finite_and_iterable([{'x': i} for i in range(5)]):
        for method, operation in [('map', broken), ('map', async_broken),
                                  ('filter', predicate), ('filter', async_predicate)]:
            outcome = observe(lambda: getattr(dataset, method)(operation), timeout=30, consume=list)
            # The requirement allows a public exception translation; neither its
            # wording nor the identity of the caller's original exception is fixed.
            assert isinstance(outcome.error, Exception), outcome


@transformation_source_test
def test_split_transformations_are_independent():
    sources = {'train': [{'x': 9}, {'x': 2}, {'x': 7}], 'validation': [{'x': -3}, {'x': 4}]}
    for collection in (DatasetDict({k: Dataset.from_list(v) for k, v in sources.items()}),
                       IterableDatasetDict({k: iterable_records(v) for k, v in sources.items()})):
        mapped = collection.map(lambda r, i: {'y': r['x'] + i}, with_indices=True)
        filtered = collection.filter(lambda r: r['x'] % 2 == 0)
        assert set(mapped) == set(filtered) == set(sources)
        for split, rows in sources.items():
            assert list(mapped[split]) == [dict(r, y=r['x'] + i) for i, r in enumerate(rows)]
            assert list(filtered[split]) == [r for r in rows if r['x'] % 2 == 0]
            assert list(collection[split]) == rows


@transformation_source_test
def test_unbounded_incremental_transformations():
    with deadline(30):
        source = IterableDataset.from_generator(endless_records)
        result = source.map(lambda r: {'double': r['number'] * 2}).filter(lambda r: r['number'] % 3 == 1)
        assert consume_prefix(result, limit=8) == [
            {'number': i, 'text': str(i), 'double': i * 2} for i in range(1, 23, 3)]


@transformation_source_test
def test_transformed_checkpoint_continuation():
    rows = [{'x': i} for i in range(13)]
    for copies in (1, 2):
        def make():
            return iterable_records(rows).map(
                lambda b: {'y': [x * 10 + j for x in b['x'] if x % 3 != 0 for j in range(copies)]},
                batched=True, batch_size=4, remove_columns=['x']).filter(
                    lambda b: [y % 4 != 2 for y in b['y']], batched=True, batch_size=3)
        expected = [{'y': x * 10 + j} for x in range(13) if x % 3 != 0
                    for j in range(copies) if (x * 10 + j) % 4 != 2]
        assert list(make()) == expected
        for delivered in (1, 3, 4, len(expected)):
            dataset = make()
            iterator = iter(dataset)
            assert consume_prefix(iterator, limit=delivered) == expected[:delivered]
            checkpoint = deepcopy(dataset.state_dict())
            restored = make()
            restored.load_state_dict(checkpoint)
            assert list(restored) == expected[delivered:]


@transformation_source_test
def test_finite_mixed_output_json_policy():
    values = [3, 'oak', {'nested': [True, None]}, [2, 4]]
    dataset = Dataset.from_list([{'i': i} for i in range(len(values))])
    operation = lambda b: {'mixed': [values[i] for i in b['i']]}
    assert list(dataset.map(operation, batched=True)) == [dict(i=i, mixed=v) for i, v in enumerate(values)]
    outcome = observe(lambda: dataset.map(operation, batched=True, on_mixed_types=None), timeout=30, consume=list)
    assert isinstance(outcome.error, (ArrowInvalid, ArrowTypeError, TypeError, ValueError)), outcome
