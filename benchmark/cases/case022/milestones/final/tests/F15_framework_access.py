# feature: F15
"""Acceptance checks for framework formatting and training adapters."""
from velnora import Dataset
from velnora.features import Array2D, Features, Value

from _helpers import consume_prefix, deadline
from F01_helpers import assert_invalid
from F04_helpers import iterable_records
from F15_helpers import assert_framework_batch, framework_source_test, framework_records, check_without_polars


@framework_source_test
def test_framework_values_and_shapes():
    values = {'id': [7, -2, 19],
              'matrix': [[[1., 2.], [3., 4.]], [[-1., 0.], [5., 6.]], [[9., 8.], [7., -3.]]]}
    dataset = Dataset.from_dict(values, features=Features(
        {'id': Value('int64'), 'matrix': Array2D((2, 2), 'float32')}))
    for representation in (None, 'numpy', 'torch', 'tensorflow', 'jax', 'pandas', 'polars', 'arrow'):
        formatted = dataset.with_format(representation)
        assert_framework_batch(formatted[:], representation, values)
        assert_framework_batch(formatted[1:3], representation,
                               {name: column[1:3] for name, column in values.items()})
        row = formatted[1]
        if representation in ('pandas', 'polars', 'arrow'):
            assert_framework_batch(row, representation, {name: [column[1]] for name, column in values.items()})
        else:
            import numpy as np
            assert int(row['id']) == -2
            np.testing.assert_array_equal(np.asarray(row['matrix']), values['matrix'][1])
    assert dataset[:] == values


@framework_source_test
def test_column_formatting_copy_reset_and_rejection():
    import numpy as np
    values = {'number': [4, -7, 12], 'text': ['alpha', 'beta', 'gamma']}
    dataset = Dataset.from_dict(values)
    separate = dataset.with_format('numpy', columns=['number'])
    assert_framework_batch(separate[:], 'numpy', {'number': values['number']})
    assert dataset[:] == values
    dataset.set_format('numpy', columns=['number'], output_all_columns=True)
    batch = dataset[:]
    assert isinstance(batch['number'], np.ndarray)
    assert batch['number'].tolist() == values['number']
    assert isinstance(batch['text'], list)
    assert batch['text'] == values['text']
    dataset.set_format('numpy', columns=['number'])
    assert_framework_batch(dataset[:], 'numpy', {'number': values['number']})
    dataset.reset_format()
    assert dataset[:] == values
    separate.reset_format()
    assert separate[:] == values
    for operation in (dataset.set_format, dataset.with_format):
        assert_invalid(lambda: operation('numpy', columns=['absent']), (ValueError,))
    assert dataset[:] == values


@framework_source_test
def test_access_transform_reexecutes_without_storage_change():
    values = {'number': [3, -5, 11], 'text': ['a', 'b', 'c']}
    for copy in (False, True):
        dataset = Dataset.from_dict(values).with_format('numpy')
        adjustment = [2]
        def transform(batch):
            return {'derived': [value * 3 + adjustment[0] for value in batch['number']]}
        if copy:
            transformed = dataset.with_transform(transform)
        else:
            dataset.set_transform(transform)
            transformed = dataset
        assert transformed[1] == {'derived': -13}
        assert transformed[0:2] == {'derived': [11, -13]}
        adjustment[0] = 20
        assert transformed[1] == {'derived': 5}
        assert transformed[0:2] == {'derived': [29, 5]}
        if copy:
            assert_framework_batch(dataset[:], 'numpy', {'number': values['number'], 'text': values['text']})
        transformed.reset_format()
        assert transformed[:] == values
        dataset.reset_format()
        assert dataset[:] == values


@framework_source_test
def test_tensorflow_training_selection_batches_and_collation():
    import numpy as np
    import tensorflow as tf
    dataset = Dataset.from_dict({'number': [2, 7, -4, 13, 9], 'target': [20, 70, -40, 130, 90],
                                 'unused': [99] * 5})
    plain = dataset.to_tf_dataset(columns='number', label_cols='target', batch_size=2, shuffle=False,
                                  prefetch=False)
    with deadline(60):
        batches = list(plain.as_numpy_iterator())
    assert [len(inputs) for inputs, labels in batches] == [2, 2, 1]
    assert np.concatenate([x for x, y in batches]).tolist() == [2, 7, -4, 13, 9]
    assert np.concatenate([y for x, y in batches]).tolist() == [20, 70, -40, 130, 90]
    def collate(rows):
        return {'number': np.asarray([row['number'] + 6 for row in rows]),
                'target': np.asarray([row['target'] - 3 for row in rows])}
    for shuffle in (False, True):
        training = dataset.to_tf_dataset(columns='number', label_cols='target', batch_size=2,
                                        shuffle=shuffle, collate_fn=collate, prefetch=False)
        assert isinstance(training, tf.data.Dataset)
        observed_orders = []
        with deadline(60):
            for _ in range(8 if shuffle else 1):
                batches = list(training.as_numpy_iterator())
                observed_orders.append([int(x) for inputs, labels in batches for x in inputs])
        if shuffle:
            # Five distinct records: eight independent uniform shuffles all
            # matching the original order has probability (1/120)**8.
            assert any(order != [8, 13, 2, 19, 15] for order in observed_orders)
        assert [len(x) for x, y in batches] == [2, 2, 1]
        delivered = [(int(x), int(y)) for inputs, labels in batches for x, y in zip(inputs, labels)]
        expected = [(8, 17), (13, 67), (2, -43), (19, 127), (15, 87)]
        assert sorted(delivered) == sorted(expected)
        if not shuffle:
            assert delivered == expected
    # Shuffling's permutation is deliberately not fixed; content and pairing are.
    for options in ({'columns': 'absent'}, {'columns': 'number', 'label_cols': 'absent'},
                    {'columns': ['number', 'number']},
                    {'columns': 'number', 'label_cols': ['target', 'target']}):
        assert_invalid(lambda: list(dataset.to_tf_dataset(batch_size=2, prefetch=False,
                                                          **options).as_numpy_iterator()), (ValueError,))


@framework_source_test
def test_pytorch_loaders_finite_and_iterable_order():
    import torch
    from torch.utils.data import DataLoader
    rows = [{'number': 8, 'pair': [8, 80]}, {'number': -3, 'pair': [-3, -30]},
            {'number': 17, 'pair': [17, 170]}, {'number': 2, 'pair': [2, 20]},
            {'number': 11, 'pair': [11, 110]}]
    finite = Dataset.from_list(rows).select([3, 0, 4, 1, 2]).with_format('torch')
    incremental = iterable_records([rows[i] for i in [3, 0, 4, 1, 2]]).with_format('torch')
    for source, options, indices in ((finite, {}, [3, 0, 4, 1, 2]),
                                      (finite, {'sampler': [4, 1, 1, 0]}, [2, 0, 0, 3]),
                                      (incremental, {}, [3, 0, 4, 1, 2])):
        with deadline(60):
            batches = list(DataLoader(source, batch_size=2, num_workers=0, **options))
        assert [len(batch['number']) for batch in batches] == [2] * (len(indices) // 2) + ([1] if len(indices) % 2 else [])
        for batch in batches:
            assert isinstance(batch['number'], torch.Tensor)
            assert isinstance(batch['pair'], torch.Tensor)
        assert torch.cat([b['number'] for b in batches]).tolist() == [rows[i]['number'] for i in indices]
        assert torch.cat([b['pair'] for b in batches]).tolist() == [rows[i]['pair'] for i in indices]


@framework_source_test
def test_iterable_representations_bounded_access():
    from velnora import IterableDataset
    for representation in (None, 'numpy', 'torch', 'tensorflow', 'jax', 'pandas', 'polars', 'arrow'):
        # An infinite source cannot be fully materialized before yielding.
        source = IterableDataset.from_generator(framework_records).with_format(representation)
        with deadline(45):
            batches = consume_prefix(source.iter(batch_size=3), limit=2)
        assert len(batches) == 2
        for offset, batch in zip((0, 3), batches):
            assert_framework_batch(batch, representation,
                                   {'number': list(range(offset, offset + 3))})
    check_without_polars()
