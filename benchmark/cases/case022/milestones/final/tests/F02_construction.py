# feature: F02
"""Acceptance checks for finite construction and public inspection."""
from collections import Counter

import pyarrow as pa
from velnora import Dataset, DatasetDict, DatasetInfo
from velnora.features import ClassLabel, Features, List, Value

from F01_helpers import assert_invalid, typed_dataset


def test_construction_sources(tmp_path):
    columns = {'number': [9, -4, 21], 'label': [1, 0, 1], 'text': ['雪', '', 'last']}
    rows = [dict(zip(columns, values)) for values in zip(*columns.values())]
    features = Features({'number': Value('int32'), 'label': ClassLabel(names=['cold', 'warm']),
                         'text': Value('string')})

    def produce():
        yield from rows

    datasets = [Dataset.from_dict(columns, features=features),
                Dataset.from_list(rows, features=features),
                Dataset(pa.table(columns, schema=pa.schema([('number', pa.int32()), ('label', pa.int64()),
                                                           ('text', pa.string())])), info=DatasetInfo(features=features)),
                Dataset.from_generator(produce, features=features, cache_dir=str(tmp_path))]
    for dataset in datasets:
        assert list(dataset) == rows
        assert dataset.features == features


def test_unequal_columns_refused():
    assert Dataset.from_dict({'left': [8, 3], 'right': ['a', 'b']})[:] == {
        'left': [8, 3], 'right': ['a', 'b']}
    for columns in ({'left': [8, 3], 'right': ['a']}, {'left': [], 'right': ['a']}):
        assert_invalid(lambda: list(Dataset.from_dict(columns)), (ValueError,))


def test_inferred_and_explicit_schemas():
    columns = {'integer': [-129, 70000, None], 'fraction': [1.125, -3.5, None],
               'boolean': [True, False, None], 'text': ['雪', '', None],
               'binary': [b'\x00\xff', b'', None], 'empty': [None, None, None],
               'nested': [{'tags': ['a', 'b']}, {'tags': []}, {'tags': ['c']}]}
    dataset = Dataset.from_dict(columns)
    assert dataset[:] == columns
    assert dataset.features['integer'].dtype in {'int8', 'int16', 'int32', 'int64', 'uint8', 'uint16', 'uint32', 'uint64'}
    assert dataset.features['fraction'].dtype in {'float16', 'float32', 'float64'}
    for name, dtype in [('boolean', 'bool'), ('text', 'string'), ('binary', 'binary'), ('empty', 'null')]:
        assert dataset.features[name] == Value(dtype)
    assert dataset.features['nested'] == {'tags': List(Value('string'))}
    for values in ([], [None, None]):
        for dtype in ('int16', 'string'):
            explicit = typed_dataset(values, Value(dtype))
            assert explicit.features['value'] == Value(dtype)
            assert list(explicit['value']) == values


def test_mixed_types_require_opt_in():
    values = [7, 'seven', {'key': [False, None]}, ['x', 2], None]
    for construct, data in ((Dataset.from_dict, {'value': values}),
                            (Dataset.from_list, [{'value': value} for value in values])):
        assert_invalid(lambda: list(construct(data)), (ValueError, TypeError))
        assert list(construct(data, on_mixed_types='use_json')['value']) == values


def test_inspection_and_indexing():
    columns = {'id': [17, 4, 29, 6, 11], 'word': ['elm', 'oak', 'ash', 'fir', 'yew']}
    dataset = Dataset.from_dict(columns)
    rows = [dict(zip(columns, values)) for values in zip(*columns.values())]
    assert dataset.num_rows == len(rows)
    assert dataset.num_columns == len(columns)
    assert set(dataset.column_names) == set(columns)
    assert set(dataset.features) == set(columns)
    assert dataset.features['word'] == Value('string')
    for index in (0, 2, -1, -len(rows)):
        assert dataset[index] == rows[index]
    for name, values in columns.items():
        assert list(dataset[name]) == values
    for selection in (slice(1, 4), slice(None, None, 2), [3, 0, 3, -2], []):
        indices = list(range(len(rows)))[selection] if isinstance(selection, slice) else selection
        assert dataset[selection] == {name: [values[i] for i in indices] for name, values in columns.items()}
    for index in (len(rows), -len(rows) - 1):
        assert_invalid(lambda: dataset[index], (IndexError,))
    assert_invalid(lambda: list(dataset['missing']), (ValueError,))


def test_ordered_row_and_batch_iteration():
    columns = {'id': [19, 2, 31, 7, 13, 5, 23], 'text': list('abcdefg')}
    dataset = Dataset.from_dict(columns)
    assert list(dataset) == [dict(zip(columns, values)) for values in zip(*columns.values())]
    for size in (1, 3, 10):
        expected = [{name: values[start:start + size] for name, values in columns.items()}
                    for start in range(0, len(columns['id']), size)]
        assert list(dataset.iter(batch_size=size)) == expected
        assert list(dataset.iter(batch_size=size, drop_last_batch=True)) == [
            batch for batch in expected if len(batch['id']) == size]


def test_named_split_inspection():
    training = Dataset.from_dict({'id': [3, 8, 1]}, features=Features({'id': Value('int16')}))
    evaluation = Dataset.from_dict({'text': ['held out'], 'ok': [True]})
    splits = DatasetDict({'training': training, 'evaluation': evaluation})
    assert set(splits) == {'training', 'evaluation'}
    assert list(splits['training']) == [{'id': 3}, {'id': 8}, {'id': 1}]
    assert list(splits['evaluation']) == [{'text': 'held out', 'ok': True}]
    assert splits.num_rows == {'training': 3, 'evaluation': 1}
    assert splits.num_columns == {'training': 1, 'evaluation': 2}
    assert {name: set(columns) for name, columns in splits.column_names.items()} == {
        'training': {'id'}, 'evaluation': {'text', 'ok'}}
    assert splits['training'].features == Features({'id': Value('int16')})
    assert splits['evaluation'].features == Features({'text': Value('string'), 'ok': Value('bool')})
    assert_invalid(lambda: splits['missing'], (KeyError,))


def test_metadata_and_split_retained():
    for suffix, version in [('alpha', '1.2.3'), ('beta', '4.0.1')]:
        metadata = {'description': 'Description ' + suffix, 'citation': 'Citation ' + suffix,
                    'license': 'License ' + suffix, 'homepage': 'https://example.org/' + suffix}
        dataset = Dataset.from_dict({'id': [8]}, info=DatasetInfo(**metadata, version=version), split=suffix)
        assert list(dataset) == [{'id': 8}]
        for field, value in metadata.items():
            assert getattr(dataset.info, field) == value
        assert str(dataset.info.version) == version
        assert str(dataset.split) == suffix


def test_distinct_scalar_values_per_split():
    first = Dataset.from_dict({'number': [4, None, 4, -2, None], 'text': ['b', 'a', 'b', None, None]})
    second = Dataset.from_dict({'number': [9, 9, None], 'text': ['z', 'z', None]})
    for name, expected in [('number', [4, None, -2]), ('text', ['b', 'a', None])]:
        assert Counter(first.unique(name)) == Counter(expected)
    splits = DatasetDict({'first': first, 'second': second})
    for name, expected in [('number', {'first': [4, None, -2], 'second': [9, None]}),
                           ('text', {'first': ['b', 'a', None], 'second': ['z', None]})]:
        actual = splits.unique(name)
        assert set(actual) == set(expected)
        for split, values in expected.items():
            assert Counter(actual[split]) == Counter(values)
    assert_invalid(lambda: first.unique('missing'), (ValueError,))
    assert_invalid(lambda: splits.unique('missing'), (ValueError,))
