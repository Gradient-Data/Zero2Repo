# feature: F02
"""Caller-side NumPy and standard-library oracles for data type acceptance."""
import base64

import numpy as np
import velnora
from velnora.dtype import (
    Bool, Int8, Int16, Int32, Int64, UInt8, UInt16, UInt32, UInt64,
    Float16, Float32, Float64, Complex64, Complex128, FixedLengthUTF32,
    NullTerminatedBytes, RawBytes, Struct, VariableLengthBytes, VariableLengthUTF8,
)

from _helpers import invoke


def dtype_examples():
    """Cover each promised family without collecting a parameter cross product."""
    cases = [(Bool(), np.dtype('bool'), [True, False, True])]
    for kind, constructors in (
        ('i', (Int8, Int16, Int32, Int64)),
        ('u', (UInt8, UInt16, UInt32, UInt64)),
    ):
        for bits, constructor in zip((8, 16, 32, 64), constructors, strict=True):
            values = [-7, 12, -3] if kind == 'i' else [7, 132, 3]
            if bits > 8:
                values[1] = 2 ** (bits - 2) + 3
            cases.append((constructor(), np.dtype(f'{kind}{bits // 8}'), values))
    for bits, constructor in zip((16, 32, 64), (Float16, Float32, Float64), strict=True):
        cases.append((constructor(), np.dtype(f'f{bits // 8}'), [1.5, -2.25, 7.0]))
    for bits, constructor in zip((64, 128), (Complex64, Complex128), strict=True):
        cases.append((constructor(), np.dtype(f'c{bits // 8}'), [1.5-2.25j, -3+4j, 7j]))
    cases.extend([
        (FixedLengthUTF32(length=5), np.dtype('U5'), ['猫é', 'north', 'λ']),
        (VariableLengthUTF8(), np.dtypes.StringDType(), ['猫é', 'longer text', 'λ']),
        (NullTerminatedBytes(length=5), np.dtype('S5'), [b'ab', b'xyz', b'q']),
        (RawBytes(length=3), np.dtype('V3'), [b'\x01\x00\xff', b'abc', b'\x07\x08\x09']),
        (VariableLengthBytes(), np.dtype('O'), [b'a\x00z', b'longer bytes', b'\xff']),
    ])
    native = np.dtype([('number', '<i4'), ('inner', [('real', '<f8'), ('flag', '?')])])
    cases.append((Struct.from_native_dtype(native), native,
                  [(17, (2.5, True)), (-4, (-3.25, False)), (29, (7.5, True))]))
    return cases


def assert_dtype_meaning(actual, expected, *, preserve_endian=False):
    """Compare semantic field order and leaf types, never padding or scalar classes."""
    actual, expected = np.dtype(actual), np.dtype(expected)
    if expected.names is not None:
        assert actual.names == expected.names
        for name in expected.names:
            assert_dtype_meaning(actual.fields[name][0], expected.fields[name][0],
                                 preserve_endian=preserve_endian)
    elif preserve_endian or expected.kind == 'T':
        assert actual == expected
    else:
        assert actual.newbyteorder('=') == expected.newbyteorder('=')


def assert_scalar_meaning(actual, expected, native):
    native = np.dtype(native)
    if native.names is not None:
        for name in native.names:
            assert_scalar_meaning(actual[name], expected[name], native.fields[name][0])
    elif native.kind in 'Mm':
        if np.isnat(expected):
            assert np.isnat(actual)
        else:
            assert actual == expected
        assert np.datetime_data(actual.dtype) == np.datetime_data(native)
    elif native.kind == 'V':
        assert bytes(actual) == bytes(expected)
    else:
        assert actual == expected


def scalar_document(value, native, version):
    """Independent shell-format fixtures, using NumPy storage and RFC 4648 base64.

    This is not a copy of Velnora's conversion: NumPy supplies the byte layout and
    the standard library supplies base64; field values come from caller data.
    """
    native = np.dtype(native)
    if native.names is not None:
        if version == 3:
            return {name: scalar_document(value[name], native.fields[name][0], version)
                    for name in native.names}
        return base64.b64encode(value.tobytes()).decode('ascii')
    if native.kind in 'SVO':
        return base64.b64encode(bytes(value)).decode('ascii')
    if native.kind == 'c':
        return [float(value.real), float(value.imag)]
    if native.kind == 'b':
        return bool(value)
    if native.kind in 'iu':
        return int(value)
    if native.kind == 'f':
        return float(value)
    if native.kind in 'Mm':
        return int(value.view('i8'))
    return str(value)


def assert_scalar_document(document, expected, native, version):
    """Permit equivalent structured scalar carriers, and check their contents."""
    native = np.dtype(native)
    if native.names is not None and isinstance(document, str):
        stored = native if version == 2 else native.newbyteorder('<')
        decoded = np.frombuffer(base64.b64decode(document, validate=True), dtype=stored)
        assert len(decoded) == 1
        assert_scalar_meaning(decoded[0], expected, native)
    elif native.names is not None:
        assert isinstance(document, dict)
        assert set(document) == set(native.names)
        for name in native.names:
            assert_scalar_document(document[name], expected[name], native.fields[name][0], version)
    elif native.kind == 'c':
        assert isinstance(document, (tuple, list))
        assert tuple(document) == (float(expected.real), float(expected.imag))
    else:
        assert document == scalar_document(expected, native, version)


def create_typed_array(dtype, *, version, shape, store=None, **kwargs):
    return invoke(velnora.create_array, call_kwargs=dict(
        store={} if store is None else store, shape=shape, dtype=dtype,
        chunks=(2,), zarr_format=version, compressors=None, **kwargs)).value


def write_reopen(dtype, values, native, version):
    expected = np.array(values, dtype=native)
    array = create_typed_array(dtype, version=version, shape=expected.shape)
    array[:] = expected
    reopened = velnora.open_array(array.store, mode='r')
    assert_dtype_meaning(reopened.dtype, native, preserve_endian=version == 2)
    actual = reopened[:]
    assert actual.shape == expected.shape
    for got, want in zip(actual, expected, strict=True):
        assert_scalar_meaning(got, want, native)
    return reopened
