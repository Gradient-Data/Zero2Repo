# feature: F11
"""Acceptance checks for source-preserving column and schema transformations."""
from velnora import Dataset, DatasetDict, IterableDatasetDict
from velnora.features import ClassLabel, Features, List, Value

from F01_helpers import assert_invalid
from F11_helpers import (assert_column_source, column_models, column_snapshot,
                         column_source_test)


@column_source_test
def test_column_selection_removal_and_renaming():
    rows = [{'id': 7, 'label': 1, 'text': 'oak'}, {'id': -2, 'label': 0, 'text': 'elm'}]
    features = Features({'id': Value('int16'), 'label': ClassLabel(names=['low', 'high']),
                         'text': Value('string')})
    for dataset in column_models(rows, features):
        before = column_snapshot(dataset)
        for result, expected, schema in [
            (dataset.rename_column('label', 'category'),
             [{'id': 7, 'category': 1, 'text': 'oak'}, {'id': -2, 'category': 0, 'text': 'elm'}],
             Features({'id': features['id'], 'category': features['label'], 'text': features['text']})),
            (dataset.rename_columns({'id': 'key', 'text': 'word'}),
             [{'key': 7, 'label': 1, 'word': 'oak'}, {'key': -2, 'label': 0, 'word': 'elm'}],
             Features({'key': features['id'], 'label': features['label'], 'word': features['text']})),
            (dataset.remove_columns('text'), [{'id': 7, 'label': 1}, {'id': -2, 'label': 0}],
             Features({'id': features['id'], 'label': features['label']})),
            (dataset.remove_columns(['text', 'id']), [{'label': 1}, {'label': 0}],
             Features({'label': features['label']})),
            (dataset.select_columns(['label', 'text']),
             [{'label': 1, 'text': 'oak'}, {'label': 0, 'text': 'elm'}],
             Features({'label': features['label'], 'text': features['text']})),
        ]:
            assert list(result) == expected
            assert result.features == schema
            assert_column_source(dataset, before)
        for operation in (lambda: list(dataset.rename_column('missing', 'new')),
                          lambda: list(dataset.rename_columns({'missing': 'new'}))):
            assert_invalid(operation, (ValueError,))
        if isinstance(dataset, Dataset):
            for operation in (lambda: list(dataset.rename_column('id', '')),
                              lambda: list(dataset.rename_columns({'id': ''})),
                              lambda: list(dataset.rename_columns({'id': 'same', 'text': 'same'})),
                              lambda: list(dataset.remove_columns('missing')),
                              lambda: list(dataset.select_columns(['missing']))):
                assert_invalid(operation, (ValueError,))
        else:
            assert_invalid(lambda: list(dataset.rename_column('id', 'text')), (ValueError,))
            assert_invalid(lambda: list(dataset.rename_columns({'id': 'text'})), (ValueError,))
        assert_column_source(dataset, before)


@column_source_test
def test_add_column_and_append_union():
    dataset = Dataset.from_dict({'id': [8, -3], 'text': ['a', 'b'], 'empty': [None, None]})
    before = column_snapshot(dataset)
    added = dataset.add_column('score', [1.5, None])
    assert list(added) == [{'id': 8, 'text': 'a', 'empty': None, 'score': 1.5},
                           {'id': -3, 'text': 'b', 'empty': None, 'score': None}]
    assert added.features['score'].dtype in {'float16', 'float32', 'float64'}
    assert_column_source(dataset, before)
    appended = dataset.add_item({'id': 21, 'empty': 4, 'fresh': 'new'})
    assert list(appended) == [
        {'id': 8, 'text': 'a', 'empty': None, 'fresh': None},
        {'id': -3, 'text': 'b', 'empty': None, 'fresh': None},
        {'id': 21, 'text': None, 'empty': 4, 'fresh': 'new'}]
    assert appended.features['empty'].dtype in {'int8', 'int16', 'int32', 'int64', 'uint8', 'uint16', 'uint32', 'uint64'}
    assert appended.features['fresh'] == Value('string')
    assert_column_source(dataset, before)
    for name, values in [('id', [1, 2]), ('new', [1]), ('new', [1, 2, 3])]:
        assert_invalid(lambda: list(dataset.add_column(name, values)), (ValueError,))
    assert_column_source(dataset, before)


@column_source_test
def test_cast_values_and_schema():
    rows = [{'small': -17, 'text': '23'}, {'small': 96, 'text': '-8'}, {'small': None, 'text': None}]
    features = Features({'small': Value('int8'), 'text': Value('string')})
    for dataset in column_models(rows, features):
        before = column_snapshot(dataset)
        wide = dataset.cast_column('small', Value('int64'))
        assert list(wide) == rows
        assert wide.features == Features({'small': Value('int64'), 'text': Value('string')})
        assert_column_source(dataset, before)
        numeric = dataset.cast_column('text', Value('int32'))
        expected = [{'small': -17, 'text': 23}, {'small': 96, 'text': -8}, {'small': None, 'text': None}]
        assert list(numeric) == expected
        assert numeric.features == Features({'small': Value('int8'), 'text': Value('int32')})
        assert_column_source(dataset, before)
        schema = Features({'small': Value('int64'), 'text': Value('int64')})
        complete = dataset.cast(schema)
        assert list(complete) == expected
        assert complete.features == schema
        assert_column_source(dataset, before)
        if isinstance(dataset, Dataset):
            assert_invalid(lambda: list(dataset.cast(Features({'other': Value('int64')}))), (ValueError,))
    for dataset in column_models([{'text': 'not numeric'}], Features({'text': Value('string')})):
        for operation in (lambda: list(dataset.cast_column('text', Value('int64'))),
                          lambda: list(dataset.cast(Features({'text': Value('int64')})))):
            assert_invalid(operation, (ValueError,))


@column_source_test
def test_flatten_leaves_lists_and_default_depth():
    rows = [{'id': 5, 'record': {'inner': {'value': 9}, 'tags': ['x', 'y']}},
            {'id': 2, 'record': {'inner': {'value': -4}, 'tags': []}}]
    dataset = Dataset.from_list(rows)
    before = column_snapshot(dataset)
    result = dataset.flatten()
    assert list(result) == [{'id': 5, 'record.inner.value': 9, 'record.tags': ['x', 'y']},
                            {'id': 2, 'record.inner.value': -4, 'record.tags': []}]
    assert set(result.column_names) == {'id', 'record.inner.value', 'record.tags'}
    assert result.features['record.tags'] == List(Value('string'))
    assert_column_source(dataset, before)
    # Seventeen record levels expose the default boundary without depending on
    # the implementation's recursion, table layout or configurable depth.
    nested = 37
    for _ in range(17):
        nested = {'node': nested}
    deep = Dataset.from_list([nested])
    before = column_snapshot(deep)
    flattened = deep.flatten()
    name = '.'.join(['node'] * 16)
    assert flattened.column_names == [name]
    assert list(flattened) == [{name: {'node': 37}}]
    assert flattened.features[name]['node'].dtype in {'int8', 'int16', 'int32', 'int64', 'uint8', 'uint16', 'uint32', 'uint64'}
    assert_column_source(deep, before)


@column_source_test
def test_categorical_encoding_vocabulary_and_nulls():
    for values, names, codes in [(['zebra', None, 'apple', 'zebra', 'pear'],
                                 ['apple', 'pear', 'zebra'], [2, None, 0, 2, 1]),
                                ([2, 10, None, -1, 2], ['-1', '10', '2'], [2, 1, None, 0, 2])]:
        dataset = Dataset.from_dict({'category': values, 'id': list(range(len(values)))})
        before = column_snapshot(dataset)
        encoded = dataset.class_encode_column('category')
        assert list(encoded['category']) == codes
        assert encoded.features['category'].names == names
        assert list(encoded['id']) == list(range(len(values)))
        assert_column_source(dataset, before)
        included = dataset.class_encode_column('category', include_nulls=True)
        # The null category's textual name is not a core promise: use its ID
        # observed at the null row, and independently check all non-null meanings.
        null_id = list(included['category'])[values.index(None)]
        vocabulary = included.features['category'].names
        assert isinstance(null_id, int)
        assert 0 <= null_id < len(vocabulary)
        assert len(vocabulary) == len(names) + 1
        assert sorted(name for index, name in enumerate(vocabulary) if index != null_id) == names
        assert vocabulary == sorted(vocabulary)
        assert list(included['category']) == [null_id if value is None else vocabulary.index(str(value)) for value in values]
        assert list(included['id']) == list(range(len(values)))
        assert_column_source(dataset, before)
    assert_invalid(lambda: Dataset.from_dict({'x': [1]}).class_encode_column('missing'), (ValueError,))
    for values in ([[1], [2]], [{'x': 1}, {'x': 2}]):
        assert_invalid(lambda: Dataset.from_dict({'x': values}).class_encode_column('x'), (ValueError,))


@column_source_test
def test_align_scalar_labels():
    mapping = {'WARM': 2, 'CoLd': 1, 'mild': 0}
    for feature, values, expected in [
        (ClassLabel(names=['cold', 'Mild', 'Warm']), [2, None, 0, 1, 2], [2, None, 1, 0, 2])]:
        dataset = Dataset.from_dict({'label': values, 'id': list(range(len(values)))},
                                    features=Features({'label': feature, 'id': Value('int32')}))
        before = column_snapshot(dataset)
        aligned = dataset.align_labels_with_mapping(mapping, 'label')
        assert list(aligned['label']) == expected
        assert list(aligned['id']) == list(range(len(values)))
        vocabulary = aligned.features['label']
        assert [name.lower() for name in vocabulary.names] == ['mild', 'cold', 'warm']
        assert_column_source(dataset, before)
    ordinary = Dataset.from_dict({'label': [0, 1]})
    assert_invalid(lambda: ordinary.align_labels_with_mapping(mapping, 'missing'), (ValueError,))


@column_source_test
def test_split_transformations_are_independent():
    features = Features({'id': Value('int16'), 'text': Value('string')})
    parts = {'train': [{'id': 8, 'text': '12'}, {'id': 3, 'text': '-5'}],
             'validation': [{'id': -6, 'text': '31'}]}
    for model, collection in [(0, DatasetDict), (1, IterableDatasetDict)]:
        splits = collection({name: column_models(rows, features)[model] for name, rows in parts.items()})
        before = {name: column_snapshot(dataset) for name, dataset in splits.items()}
        for transformed, row_rule, schema in [
            (splits.rename_column('text', 'word'), lambda row: {'id': row['id'], 'word': row['text']},
             Features({'id': features['id'], 'word': features['text']})),
            (splits.rename_columns({'id': 'key', 'text': 'word'}), lambda row: {'key': row['id'], 'word': row['text']},
             Features({'key': features['id'], 'word': features['text']})),
            (splits.remove_columns('text'), lambda row: {'id': row['id']}, Features({'id': features['id']})),
            (splits.select_columns(['text']), lambda row: {'text': row['text']}, Features({'text': features['text']})),
            (splits.cast_column('text', Value('int32')), lambda row: {'id': row['id'], 'text': int(row['text'])},
             Features({'id': features['id'], 'text': Value('int32')})),
            (splits.cast(Features({'id': Value('int64'), 'text': Value('int64')})),
             lambda row: {'id': row['id'], 'text': int(row['text'])},
             Features({'id': Value('int64'), 'text': Value('int64')})),
        ]:
            assert set(transformed) == set(parts)
            for name, rows in parts.items():
                assert list(transformed[name]) == [row_rule(row) for row in rows]
                assert transformed[name].features == schema
                assert_column_source(splits[name], before[name])
    nested = DatasetDict({name: Dataset.from_list([{'record': {'id': row['id']}} for row in rows])
                          for name, rows in parts.items()})
    before = {name: column_snapshot(dataset) for name, dataset in nested.items()}
    flattened = nested.flatten()
    assert set(flattened) == set(parts)
    for name, rows in parts.items():
        assert list(flattened[name]) == [{'record.id': row['id']} for row in rows]
        assert_column_source(nested[name], before[name])
    categories = DatasetDict({'train': Dataset.from_dict({'label': ['b', 'a', None]}),
                              'validation': Dataset.from_dict({'label': ['c', 'b']})})
    before = {name: column_snapshot(dataset) for name, dataset in categories.items()}
    encoded = categories.class_encode_column('label')
    assert set(encoded) == set(categories)
    for name, codes, names in [('train', [1, 0, None], ['a', 'b']), ('validation', [1, 0], ['b', 'c'])]:
        assert list(encoded[name]['label']) == codes
        assert encoded[name].features['label'].names == names
        assert_column_source(categories[name], before[name])
    # Use a complete common vocabulary to test split-wide alignment.
    labeled = DatasetDict({name: Dataset.from_dict({'label': [0, 1, None] if name == 'train' else [1]},
                           features=Features({'label': ClassLabel(names=['cold', 'warm'])})) for name in parts})
    snapshots = {name: column_snapshot(dataset) for name, dataset in labeled.items()}
    aligned = labeled.align_labels_with_mapping({'WARM': 0, 'COLD': 1}, 'label')
    assert set(aligned) == set(parts)
    for name, codes in [('train', [1, 0, None]), ('validation', [0])]:
        assert list(aligned[name]['label']) == codes
        assert [word.lower() for word in aligned[name].features['label'].names] == ['warm', 'cold']
        assert_column_source(labeled[name], snapshots[name])
