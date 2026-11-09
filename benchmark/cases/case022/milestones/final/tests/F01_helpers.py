# feature: F01
"""Public construction and fully consumed failure observations for typed columns."""
from velnora import Dataset
from velnora.features import Features
from _helpers import observe


def typed_dataset(values, feature):
    return Dataset.from_dict({'value': values}, features=Features({'value': feature}))


def typed_values(values, feature):
    return [row['value'] for row in typed_dataset(values, feature)]


def assert_invalid(operation, errors=(ValueError, TypeError)):
    result = observe(operation, timeout=30)
    assert isinstance(result.error, errors), (
        f'Expected an invalid-data exception, got {result.error!r}; value={result.value!r}'
    )
