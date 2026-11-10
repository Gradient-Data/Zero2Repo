# feature: F01
"""Acceptance checks for declared data and semantic feature meanings."""
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import numpy as np
from velnora.features import (
    Array2D, Array3D, Array4D, Array5D, ClassLabel, Json, List, Translation,
    TranslationVariableLanguages, Value
)

from F01_helpers import assert_invalid, typed_dataset, typed_values


def test_scalar_numeric_types():
    cases = {'null': [None, None, None], 'bool': [True, False, None]}
    for width in (8, 16, 32, 64):
        cases[f'int{width}'] = [-(2 ** (width - 1)), 2 ** (width - 1) - 1, None]
        cases[f'uint{width}'] = [0, 2 ** width - 1, None]
    # Plain Python integer columns are inferred as signed int64 before casting.
    # The baseline cannot construct uint64 values above that range (ledger request).
    cases['uint64'] = [0, 2 ** 63 - 1, None]
    cases.update({
        'float16': [-2.25, 1.5, None],
        'float32': [-123.125, 65536.5, None],
        'float64': [-1.0000000000000002, 2 ** 40 + 0.25, None],
    })
    for dtype, values in cases.items():
        dataset = typed_dataset(values, Value(dtype))
        assert dataset.features['value'].dtype == dtype
        assert [row['value'] for row in dataset] == values


def test_scalar_text_decimal_temporal_types():
    local = timezone(timedelta(hours=5, minutes=30))
    cases = {
        'decimal128(20, 3)': [Decimal('-123456789012345.125'), Decimal('0.001')],
        'decimal256(50, 4)': [Decimal('1234567890123456789012345678901234567890.1234'), Decimal('-0.0001')],
        'string': ['雪 and café', ''],
        'binary': [b'\x00\xffbinary', b''],
        'date32': [date(2024, 2, 29), date(1960, 1, 2)],
        'date64': [date(2024, 2, 29), date(1960, 1, 2)],
        'time32[s]': [time(12, 34, 56), time(0, 0, 1)],
        'time64[us]': [time(23, 59, 59, 123456), time(0, 0, 0, 1)],
        'timestamp[us]': [datetime(1960, 1, 2, 3, 4, 5, 123456), datetime(2024, 2, 29)],
        'timestamp[us, tz=Asia/Kolkata]': [datetime(2024, 2, 29, 12, 30, tzinfo=local), datetime(1960, 1, 2, tzinfo=local)],
        'duration[us]': [timedelta(days=-2, microseconds=123), timedelta(seconds=5, microseconds=7)],
    }
    for dtype, values in cases.items():
        values = values + [None]
        dataset = typed_dataset(values, Value(dtype))
        assert dataset.features['value'].dtype == dtype
        assert [row['value'] for row in dataset] == values


def test_incompatible_scalar_values_are_refused():
    # Bounded types are probed just outside both ends of their ranges.
    for dtype, valid, invalids in (
        ('int8', [-128, 127], [[128], [-129]]),
        ('uint8', [0, 255], [[-1], [256]]),
        ('int64', [12, -9], [['not a number']]),
        ('float32', [1.5, -2.25], [['not a number']]),
        ('decimal128(5, 2)', [Decimal('123.45')], [[Decimal('1234.56')], [Decimal('-1234.56')]]),
    ):
        assert typed_values(valid, Value(dtype)) == valid
        for invalid in invalids:
            assert_invalid(lambda: typed_values(invalid, Value(dtype)))


def test_nested_lists_and_multidimensional_arrays():
    feature = {'name': Value('string'), 'groups': List({'score': Value('int16'), 'tags': List(Value('string'))})}
    values = [{'name': 'first', 'groups': [{'score': -7, 'tags': ['a', 'b']}, {'score': 12, 'tags': []}]},
              {'name': 'second', 'groups': []}]
    assert typed_values(values, feature) == values
    fixed = List(Value('int32'), length=3)
    values = [[4, -2, 9], [10, 11, 12], None]
    assert typed_values(values, fixed) == values
    for invalid in ([[1, 2]], [[1, 2, 3, 4]]):
        assert_invalid(lambda: typed_values(invalid, fixed))
    for dimensions, cls in enumerate((Array2D, Array3D, Array4D, Array5D), start=2):
        shape = (2,) * dimensions
        first = np.arange(2 ** dimensions).reshape(shape).tolist()
        second = (-np.arange(2 ** dimensions) - 1).reshape(shape).tolist()
        assert typed_values([first, second], cls(shape=shape, dtype='int32')) == [first, second]
        shorter = np.arange(2 ** (dimensions - 1)).reshape((1,) + shape[1:]).tolist()
        assert typed_values([first, shorter], cls(shape=(None,) + shape[1:], dtype='int32')) == [first, shorter]


def test_categorical_vocabulary_sources(tmp_path):
    names = ['zebra', 'amber', '松']
    vocabulary = tmp_path / 'vocabulary.txt'
    vocabulary.write_text('\n'.join(names) + '\n', encoding='utf-8')
    for label, expected in ((ClassLabel(names=names), names),
                            (ClassLabel(names_file=str(vocabulary)), names),
                            (ClassLabel(num_classes=4), ['0', '1', '2', '3'])):
        assert label.names == expected
        assert list(label.str2int(expected)) == list(range(len(expected)))
        assert list(label.int2str(list(range(len(expected))))) == expected
        for index, name in enumerate(expected):
            assert label.str2int(name) == index
            assert label.int2str(index) == name
        order = [len(expected) - 1, 0, 1, 0]
        dataset = typed_dataset([expected[index] for index in order], label)
        assert [row['value'] for row in dataset] == order
        assert dataset.features['value'].names == expected
        assert typed_values(order, label) == order


def test_categorical_invalid_values_and_unknown_label():
    assert_invalid(lambda: ClassLabel(names=['same', 'same']), (ValueError,))
    assert_invalid(lambda: ClassLabel(names=['left', 'right'], num_classes=3), (ValueError,))
    label = ClassLabel(names=['right', 'left'])
    assert typed_values(['left', 'right', -1], label) == [1, 0, -1]
    assert_invalid(lambda: label.str2int('missing'), (ValueError,))
    assert_invalid(lambda: typed_values(['missing'], label), (ValueError,))
    for index in (-1, -2, 2):
        assert_invalid(lambda: label.int2str(index), (ValueError,))


def test_translation_associations_and_allowed_languages():
    fixed = Translation(languages=['fr', 'en'])
    values = [{'en': 'cat', 'fr': 'chat'}, {'en': 'dog', 'fr': 'chien'}]
    assert typed_values(values, fixed) == values
    variable = TranslationVariableLanguages(languages=['fr', 'en', 'de'])
    values = [{'fr': ['chat', 'félin', 'chat'], 'en': 'cat'}, {'de': 'Hund'}, {'en': ['dog', 'hound'], 'fr': 'chien'}]
    expected = [Counter([('fr', 'chat'), ('fr', 'félin'), ('fr', 'chat'), ('en', 'cat')]),
                Counter([('de', 'Hund')]), Counter([('en', 'dog'), ('en', 'hound'), ('fr', 'chien')])]
    actual = typed_values(values, variable)
    assert len(actual) == len(expected)
    for row, pairs in zip(actual, expected):
        assert len(row['language']) == len(row['translation'])
        assert Counter(zip(row['language'], row['translation'])) == pairs
    assert_invalid(lambda: typed_values([{'en': 'cat', 'es': 'gato'}], variable), (ValueError,))


def test_json_heterogeneity_and_typed_missing_fields():
    values = [{'left': 1}, {'right': ['x', None, False, {'deep': 2.5}]},
              [1, 'two', {'three': True}], 'text', 27, 1.25, False, None, {}, []]
    assert typed_values(values, Json()) == values
    records = [{'left': 1}, {'right': 'text'}, {}]
    declared = {'left': Value('int32'), 'right': Value('string')}
    assert typed_values(records, declared) == [
        {'left': 1, 'right': None}, {'left': None, 'right': 'text'}, {'left': None, 'right': None}]
