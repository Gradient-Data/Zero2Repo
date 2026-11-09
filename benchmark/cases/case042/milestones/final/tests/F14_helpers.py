# feature: F14
"""Public observations of copied arrays and saved group members."""
import numpy as np

from F02_helpers import assert_dtype_meaning
from F07_helpers import array_properties


def assert_saved_values(array, expected):
    assert array.shape == expected.shape
    assert_dtype_meaning(array.dtype, expected.dtype)
    np.testing.assert_array_equal(array[...], expected)


def assert_copy_choices(array, source):
    actual, expected = array_properties(array), array_properties(source)
    assert_dtype_meaning(actual.pop('dtype'), expected.pop('dtype'))
    # Codec identity/equality is not a public requirement. Compare the selected
    # configurations through their documented descriptions instead.
    for properties in (actual, expected):
        version = properties['zarr_format']
        for key in ('filters', 'compressors'):
            properties[key] = tuple(codec.to_dict() if version == 3 else codec.get_config()
                                    for codec in properties[key])
        serializer = properties['serializer']
        properties['serializer'] = None if serializer is None else serializer.to_dict()
    assert actual == expected
    assert dict(array.attrs) == dict(source.attrs)


def assert_saved_members(group, positional, named):
    members = dict(group.arrays())
    assert len(members) == len(positional) + len(named)
    for name, expected in named.items():
        assert_saved_values(group[name], expected)
    # Unnamed member spelling and iteration order are not core promises.
    remaining = [array for name, array in members.items() if name not in named]
    assert len(remaining) == len(positional)
    for expected in positional:
        matches = [index for index, array in enumerate(remaining)
                   if array.shape == expected.shape
                   and np.dtype(array.dtype).newbyteorder('=') == expected.dtype.newbyteorder('=')
                   and np.array_equal(array[...], expected)]
        assert len(matches) == 1
        remaining.pop(matches[0])
