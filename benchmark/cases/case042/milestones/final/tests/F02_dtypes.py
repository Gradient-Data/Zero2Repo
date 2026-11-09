# feature: F02
"""Acceptance tests for public native types, scalar values and registration."""
import numpy as np
import pytest
import velnora
from velnora.dtype import (
    DateTime64, Float16, Float32, Float64, Int16, Int8, Struct, TimeDelta64, VariableLengthBytes, VariableLengthUTF8, data_type_registry, parse_dtype
)

from _helpers import invoke

from F02_helpers import (
    dtype_examples, assert_dtype_meaning, assert_scalar_meaning,
    scalar_document, assert_scalar_document, create_typed_array, write_reopen,
)


def test_f02_t01():
    # FP-02.01/02: every family, with independently supplied scalar metadata.
    for dtype, native, values in dtype_examples():
        scalar = np.array(values, dtype=native)[0]
        for version in (2, 3):
            description = dtype.to_json(zarr_format=version)
            recovered = data_type_registry.match_json(description, zarr_format=version)
            assert_dtype_meaning(recovered.to_native_dtype(), native,
                                 preserve_endian=version == 2)
            document = dtype.to_json_scalar(scalar, zarr_format=version)
            assert_scalar_document(document, scalar, native, version)
            supplied = scalar_document(scalar, native, version)
            decoded = dtype.from_json_scalar(supplied, zarr_format=version)
            assert_scalar_meaning(decoded, scalar, native)
            write_reopen(dtype, values, native, version)


def test_f02_t02():
    # A record's stored byte order follows the encoding, field by field.
    packed = np.dtype([('a', 'i2'), ('b', 'f4')])
    records = np.array([(1, 1.5), (-2, 2.5)], dtype=packed)
    for order, endian in (('<', 'little'), ('>', 'big')):
        array = velnora.create_array({}, shape=(2,), chunks=(2,), dtype=Struct.from_native_dtype(packed),
                                  serializer=velnora.codecs.BytesCodec(endian=endian), compressors=None)
        array[:] = records
        stored = invoke(array.store.get, 'c/0').value.to_bytes()
        assert stored == records.astype([('a', order + 'i2'), ('b', order + 'f4')]).tobytes()
        result = velnora.open_array(array.store, mode='r')[:]
        assert result['a'].tolist() == [1, -2] and result['b'].tolist() == [1.5, 2.5]
    # FP-02.07 enumerates units; scale edges are tested separately from byte order.
    units = ('Y', 'M', 'W', 'D', 'h', 'm', 's', 'ms', 'us', 'ns', 'ps', 'fs', 'as', 'generic')
    for cls, kind, name in ((DateTime64, 'M8', 'numpy.datetime64'),
                            (TimeDelta64, 'm8', 'numpy.timedelta64')):
        for unit in units:
            dtype = cls(unit=unit, scale_factor=3)
            native = np.dtype(f'{kind}[3{unit}]')
            scalar = np.array([19], dtype='i8').view(native)[0]
            for version in (2, 3):
                description = dtype.to_json(zarr_format=version)
                parsed = data_type_registry.match_json(description, zarr_format=version)
                assert np.datetime_data(parsed.to_native_dtype()) == (unit, 3)
                assert dtype.to_json_scalar(scalar, zarr_format=version) == 19
                assert_scalar_meaning(dtype.from_json_scalar(19, zarr_format=version), scalar, native)
                assert np.isnat(dtype.from_json_scalar('NaT', zarr_format=version))
                assert np.isnat(dtype.from_json_scalar(-(2**63), zarr_format=version))
                missing = np.array(['NaT'], dtype=native)[0]
                encoded = dtype.to_json_scalar(missing, zarr_format=version)
                assert encoded in ('NaT', -(2**63))
            write_reopen(dtype, np.array([19, -7, 43], dtype='i8').view(native), native, 3)
        for scale in (1, 2147483647):
            dtype = cls(unit='ns', scale_factor=scale)
            assert np.datetime_data(dtype.to_native_dtype()) == ('ns', scale)
            for version in (2, 3):
                parsed = data_type_registry.match_json(dtype.to_json(zarr_format=version),
                                                         zarr_format=version)
                assert np.datetime_data(parsed.to_native_dtype()) == ('ns', scale)
        for scale in (0, -1, 2147483648):
            with pytest.raises(ValueError):
                cls(unit='ns', scale_factor=scale)
        for order, endian in (('<', 'little'), ('>', 'big')):
            native = np.dtype(f'{order}{kind}[2us]')
            dtype = cls.from_native_dtype(native)
            description = dtype.to_json(zarr_format=2)
            assert np.dtype(description['name']) == native
            parsed = data_type_registry.match_json(description, zarr_format=2)
            assert parsed.to_native_dtype() == native
            # V3 metadata does not encode byte order; the public bytes codec does.
            assert dtype.to_json(zarr_format=3) == {
                'name': name, 'configuration': {'unit': 'us', 'scale_factor': 2}}
            data = np.array([19, -7, 43], dtype=f'{order}i8').view(native)
            array = create_typed_array(dtype, version=3, shape=(3,),
                                      serializer=velnora.codecs.BytesCodec(endian=endian))
            array[:] = data
            reopened = velnora.open_array(array.store, mode='r')
            np.testing.assert_array_equal(reopened[:], data)
            assert reopened.metadata.codecs[0].to_dict()['configuration']['endian'] == endian
            chunk = invoke(array.store.get, 'c/0').value
            assert chunk is not None
            assert chunk.to_bytes() == np.array([19, -7], dtype=f'{order}i8').tobytes()


def test_f02_t03():
    # Refusals use the public ValueError carrier, without parsing prose.
    for version in (2, 3):
        assert_dtype_meaning(parse_dtype(np.dtype('i4'), zarr_format=version).to_native_dtype(), 'i4')
        for dtype, values, native in (
            (VariableLengthUTF8(), ['real text', '猫', 'x'], np.dtypes.StringDType()),
            (VariableLengthBytes(), [b'ab', b'\x00\xff', b'z'], np.dtype('O')),
        ):
            write_reopen(dtype, values, native, version)
        # Explicit text interpretation applies to supplied non-text objects too.
        objects = np.array([17, -203, 0], dtype=object)
        text = create_typed_array(VariableLengthUTF8(), version=version, shape=objects.shape)
        text[:] = objects
        np.testing.assert_array_equal(velnora.open_array(text.store, mode='r')[:],
                                      [str(value) for value in objects])
        with pytest.raises(ValueError):
            parse_dtype(np.dtype('O'), zarr_format=version)
        with pytest.raises(ValueError):
            create_typed_array(np.dtype('O'), version=version, shape=(3,))
        with pytest.raises(ValueError):
            data_type_registry.match_dtype(np.dtype('f16'))
    class AnotherInt16(Int16):
        _velnora_v3_name = 'acceptance.another_int16'
    data_type_registry.register(AnotherInt16._velnora_v3_name, AnotherInt16)
    try:
        with pytest.raises(ValueError):
            data_type_registry.match_dtype(np.dtype('i2'))
        with pytest.raises(ValueError):
            create_typed_array(np.dtype('i2'), version=3, shape=(3,))
    finally:
        data_type_registry.unregister(AnotherInt16._velnora_v3_name)
    assert_dtype_meaning(data_type_registry.match_dtype(np.dtype('i2')).to_native_dtype(), 'i2')


def test_f02_t04():
    padded = [
        np.dtype([('a', 'i1'), ('b', 'i8')], align=True),
        np.dtype({'names': ['a', 'b'], 'formats': ['i1', 'i4'],
                  'offsets': [0, 8], 'itemsize': 16}),
        np.dtype([('a', 'i4'), ('inner', np.dtype([('x', 'i1'), ('y', 'f8')], align=True))]),
    ]
    for native in padded:
        values = np.zeros(3, dtype=native)
        values['a'] = [17, -4, 9]
        if 'b' in native.names:
            values['b'] = [-11, 23, 6]
        else:
            values['inner']['x'] = [3, -2, 1]
            values['inner']['y'] = [1.5, -2.25, 7]
        dtype = Struct.from_native_dtype(native)
        for version in (2, 3):
            parsed = data_type_registry.match_json(dtype.to_json(zarr_format=version), zarr_format=version)
            assert_dtype_meaning(parsed.to_native_dtype(), native, preserve_endian=version == 2)
            # Pass the padded native array itself through array creation, not its packed replacement.
            array = velnora.create_array(store={}, data=values, chunks=(2,), zarr_format=version,
                                      compressors=None)
            result = velnora.open_array(array.store, mode='r')[:]
            for actual, expected in zip(result, values, strict=True):
                assert_scalar_meaning(actual, expected, native)
    unsupported = [np.dtype([(('title', 'a'), 'i4')]),
                   np.dtype([('a', 'i4', (2,))]),
                   np.dtype([('outer', [('a', 'i4', (2,))])])]
    for native in unsupported:
        with pytest.raises(ValueError):
            Struct.from_native_dtype(native)
        for version in (2, 3):
            with pytest.raises(ValueError):
                create_typed_array(native, version=version, shape=(3,))


def test_f02_t05():
    record = np.dtype([('text', 'U3'), ('time', 'M8[us]'),
                       ('inner', [('bytes', 'S4'), ('raw', 'V3'), ('duration', 'm8[3us]')])])
    defaults = dtype_examples() + [(Struct.from_native_dtype(record), record, None)]
    for dtype, native, _ in defaults:
        # Independent NumPy zero storage, including recursive fixed-size records.
        expected = np.zeros(1, dtype=native)[0]
        if native.kind == 'O':
            expected = b''
        for version in (2, 3):
            default = dtype.default_scalar()
            assert_scalar_meaning(default, expected, native)
            assert_scalar_document(dtype.to_json_scalar(default, zarr_format=version), expected, native, version)
            array = create_typed_array(dtype, version=version, shape=(3,))
            for value in velnora.open_array(array.store, mode='r')[:]:
                assert_scalar_meaning(value, expected, native)
    for cls, kind in ((DateTime64, 'M8'), (TimeDelta64, 'm8')):
        dtype = cls(unit='us', scale_factor=3)
        native = np.dtype(f'{kind}[3us]')
        expected = np.array(['NaT'], dtype=native)[0]
        assert_scalar_meaning(dtype.default_scalar(), expected, native)
        for version in (2, 3):
            array = create_typed_array(dtype, version=version, shape=(3,))
            for value in velnora.open_array(array.store, mode='r')[:]:
                assert_scalar_meaning(value, expected, native)
    # Non-finite floating-point fills and their defined metadata spellings.
    for cls in (Float16, Float32, Float64):
        for version in (2, 3):
            for spelling, value in (('NaN', np.nan), ('Infinity', np.inf), ('-Infinity', -np.inf)):
                dtype = cls()
                np.testing.assert_array_equal(dtype.from_json_scalar(spelling, zarr_format=version), value)
                assert dtype.to_json_scalar(value, zarr_format=version) == spelling
                array = create_typed_array(dtype, version=version, shape=(2,), fill_value=value)
                np.testing.assert_array_equal(velnora.open_array(array.store, mode='r')[:], [value, value])
    # Valid fills on the same paths ensure this does not reward a uniform rejector.
    for dtype, good, bad in ((Int8(), 17, 'not an integer'),
                             (Float32(), 1.5, {'invalid': 1}),
                             (DateTime64(unit='ns'), np.datetime64('NaT', 'ns'), [1.5])):
        for version in (2, 3):
            array = create_typed_array(dtype, version=version, shape=(3,), fill_value=good)
            expected = dtype.cast_scalar(good)
            for actual in array[:]:
                assert_scalar_meaning(actual, expected, dtype.to_native_dtype())
            with pytest.raises((TypeError, ValueError)):
                create_typed_array(dtype, version=version, shape=(3,), fill_value=bad)


def test_f02_t06():
    # An extension uses the public base protocol and the existing integer encoding.
    class RegisteredInt16(Int16):
        _velnora_v3_name = 'acceptance.registered_int16'
    name = RegisteredInt16._velnora_v3_name
    with pytest.raises(ValueError):
        data_type_registry.match_json(name, zarr_format=3)
    data_type_registry.unregister('int16')
    data_type_registry.register(name, RegisteredInt16)
    try:
        dtype = data_type_registry.match_dtype(np.dtype('i2'))
        assert isinstance(dtype, RegisteredInt16)
        parsed = data_type_registry.match_json(name, zarr_format=3)
        assert isinstance(parsed, RegisteredInt16)
        for version in (2, 3):
            assert dtype.to_json_scalar(-113, zarr_format=version) == -113
            assert dtype.from_json_scalar(107, zarr_format=version) == 107
            write_reopen(dtype, [-113, 107, 29], np.dtype('i2'), version)
        array = create_typed_array(name, version=3, shape=(3,), fill_value=107)
        array[:] = [-113, 107, 29]
        reopened = velnora.open_array(array.store, mode='r')
        description = reopened.metadata.data_type.to_json(zarr_format=3)
        assert (description if isinstance(description, str) else description['name']) == name
        np.testing.assert_array_equal(reopened[:], [-113, 107, 29])
    finally:
        data_type_registry.unregister(name)
        data_type_registry.register('int16', Int16)
    with pytest.raises(ValueError):
        data_type_registry.match_json(name, zarr_format=3)
