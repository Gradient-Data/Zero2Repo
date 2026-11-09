# feature: F05
"""Acceptance of encoding through array binding, stored chunks and reopening."""
import gzip
import json
import struct
import bz2
import lzma
import zlib
import numpy as np
import numcodecs as nc
import pytest
import velnora
from velnora.codecs import (
    BloscCodec, BytesCodec, CastValue, Crc32cCodec, GzipCodec, ScaleOffset,
    TransposeCodec, VLenBytesCodec, VLenUTF8Codec, ZstdCodec,
)
from velnora.codecs import numcodecs as ext
from velnora.errors import UnknownCodecError
from velnora.registry import register_codec
from _helpers import invoke
from F02_helpers import create_typed_array
from F05_helpers import (encoding_array, chunk_payload, replace_payload,
                         reopened_values, check_encoded)


def test_f05_t01():
    data = np.array([17, -313, 4097, 52, -6, 81], dtype='i4')
    serialized = (data.astype('<i4').tobytes(), data.astype('>i4').tobytes())
    for version, choices in ((2, [None, nc.Blosc(clevel=3), nc.Zstd(level=2), nc.GZip(level=2)]),
                             (3, [None, BloscCodec(clevel=3, typesize=4, shuffle='shuffle'), ZstdCodec(level=2), GzipCodec(level=2)])):
        for codec in choices:
            a = encoding_array(data, zarr_format=version, compressors=codec)
            a[:] = data
            b = velnora.open_array(a.store, mode='r')
            np.testing.assert_array_equal(b[:], data)
            if codec is None:
                assert b.compressors == ()
            elif version == 2:
                assert b.compressors[0].get_config() == codec.get_config()
                assert b.metadata.compressor.get_config() == codec.get_config()
            else:
                assert b.compressors[0].to_dict() == codec.to_dict()
                assert b.metadata.codecs[-1].to_dict() == codec.to_dict()
            if isinstance(codec, (nc.GZip, GzipCodec)):
                # The stored payload is a real gzip stream of the element bytes.
                assert gzip.decompress(chunk_payload(a)) in serialized
            elif isinstance(codec, (nc.Zstd, ZstdCodec)):
                assert bytes(nc.Zstd().decode(chunk_payload(a))) in serialized
            elif isinstance(codec, (nc.Blosc, BloscCodec)):
                assert bytes(nc.Blosc().decode(chunk_payload(a))) in serialized
        # Compression is defaulted both when omitted and when requested as 'auto'.
        for request in ({}, {'compressors': 'auto'}):
            args = dict(store={}, shape=data.shape, chunks=data.shape, dtype=data.dtype,
                        zarr_format=version, fill_value=0, **request)
            a = invoke(velnora.create_array, call_kwargs=args).value
            a[:] = data
            b = velnora.open_array(a.store, mode='r')
            np.testing.assert_array_equal(b[:], data)
            assert len(b.compressors) == 1
            if version == 2:
                assert b.compressors[0].get_config()['id'] == 'zstd'
            else:
                assert b.compressors[0].to_dict()['name'] == 'zstd'
            # An independent decoder recovers the elements from the stored chunk.
            assert bytes(nc.Zstd().decode(chunk_payload(a))) in serialized


def test_f05_t02():
    data = np.full(16384, 37, dtype='i4')
    baseline = encoding_array(data)
    baseline[:] = data
    plain = chunk_payload(baseline)
    assert len(plain) == data.nbytes
    np.testing.assert_array_equal(reopened_values(baseline), data)
    for codec in (BloscCodec(), ZstdCodec(), GzipCodec()):
        a = encoding_array(data, compressors=codec)
        a[:] = data
        assert len(chunk_payload(a)) < len(plain)
        np.testing.assert_array_equal(reopened_values(a), data)


def test_f05_t03():
    data = np.array([11, 17, 26, 41], dtype='i4')
    # Two affine transforms do not commute. Expected values are independently
    # evaluated from the scale_offset standard's ordered arithmetic.
    check_encoded(data, [ScaleOffset(offset=3, scale=2), ScaleOffset(offset=5, scale=3)],
                  [33, 69, 123, 213], 'i4')
    filters = [nc.FixedScaleOffset(offset=3, scale=2, dtype='i4'),
               nc.FixedScaleOffset(offset=5, scale=3, dtype='i4')]
    a = encoding_array(data, zarr_format=2, filters=filters)
    a[:] = data
    np.testing.assert_array_equal(np.frombuffer(chunk_payload(a), dtype='<i4'), [33, 69, 123, 213])
    np.testing.assert_array_equal(reopened_values(a), data)
    for options in (dict(filters=[GzipCodec()]), dict(serializer=GzipCodec()),
                    dict(compressors=[BytesCodec()]), dict(serializer=None),
                    dict(filters=[BytesCodec(), BytesCodec()]),
                    dict(filters=[TransposeCodec(order=(0, 1))])):
        with pytest.raises((TypeError, ValueError)):
            a = encoding_array(data, **options)
            a[:] = data
            reopened_values(a)
    with pytest.raises((TypeError, ValueError)):
        a = encoding_array(data, zarr_format=2, compressors=[nc.GZip(), nc.Zstd()])
        a[:] = data
    with pytest.raises((TypeError, ValueError)):
        create_typed_array(velnora.dtype.VariableLengthUTF8(), version=3, shape=(3,),
                           serializer=BytesCodec())


def test_f05_t04():
    data = np.array([[0x1234, 0x2345, 0x3456], [0x4567, 0x5678, 0x6789]], dtype='u2')
    for endian, order in (('little', '<'), ('big', '>')):
        a = encoding_array(data, serializer=BytesCodec(endian=endian),
                           filters=[TransposeCodec(order=(1, 0))])
        a[:] = data
        expected = [data[i, j] for j in range(3) for i in range(2)]
        assert chunk_payload(a) == np.asarray(expected, dtype=order+'u2').tobytes()
        np.testing.assert_array_equal(reopened_values(a), data)
    for dtype, serializer, values in (
        (velnora.dtype.VariableLengthUTF8(), VLenUTF8Codec(), ['a', '', '猫é', 'a longer word']),
        (velnora.dtype.VariableLengthBytes(), VLenBytesCodec(), [b'a\x00z', b'', b'\xff', b'long bytes'])):
        a = velnora.create_array({}, shape=(4,), chunks=(4,), dtype=dtype,
                              serializer=serializer, compressors=None)
        a[:] = values
        raw = chunk_payload(a)
        assert struct.unpack_from('<I', raw)[0] == len(values)
        position = 4
        decoded = []
        for _ in values:
            length = struct.unpack_from('<I', raw, position)[0]
            position += 4
            decoded.append(raw[position:position+length])
            position += length
        assert position == len(raw)
        expected = [v.encode('utf-8') for v in values] if isinstance(values[0], str) else values
        assert decoded == expected
        np.testing.assert_array_equal(reopened_values(a), values)
    for order in ((0, 0), (1,), (0, 2)):
        with pytest.raises(ValueError):
            a = encoding_array(data, filters=[TransposeCodec(order=order)])
            a[:] = data
            reopened_values(a)


def test_f05_t05():
    import google_crc32c
    data = np.array([17, 2024, -31, 93], dtype='i4')
    a = encoding_array(data, serializer=BytesCodec(endian='little'), compressors=[Crc32cCodec()])
    a[:] = data
    raw = chunk_payload(a)
    assert raw[:-4] == data.astype('<i4').tobytes()
    assert int.from_bytes(raw[-4:], 'little') == google_crc32c.value(raw[:-4])
    np.testing.assert_array_equal(reopened_values(a), data)
    for index in (0, len(raw)-1):
        damaged = bytearray(raw)
        damaged[index] ^= 1
        replace_payload(a, bytes(damaged))
        with pytest.raises(ValueError):
            reopened_values(a)
    replace_payload(a, raw)
    np.testing.assert_array_equal(reopened_values(a), data)


# Vectors follow the two extension specifications at the PRD's pinned revision.
def test_f05_t06():
    for dtype in ('i1', '>i4', 'u2', '>u8', 'f4', '>f8'):
        data = np.array([5, 7, 11, 17], dtype=dtype)
        check_encoded(data, [ScaleOffset(offset=3, scale=2)], [4, 8, 16, 28], dtype, fill_value=3)
        check_encoded(data, [ScaleOffset()], data, dtype)
    check_encoded(np.array([1.25, -2.5, 4], dtype='f4'),
                  [ScaleOffset(offset=0.5, scale=2)], [1.5, -6, 7], 'f4')
    a = encoding_array(np.zeros(4, dtype='i4'), filters=[ScaleOffset(offset=5, scale=3)], fill_value=7)
    np.testing.assert_array_equal(reopened_values(a), [7]*4)
    a[1:3] = [11, 13]
    np.testing.assert_array_equal(np.frombuffer(chunk_payload(a), dtype='<i4'), [6, 18, 24, 6])
    np.testing.assert_array_equal(reopened_values(a), [7, 11, 13, 7])


def test_f05_t07():
    check_encoded(np.array([3, 5], dtype='i2'), [ScaleOffset(scale=2)], [6, 10], 'i2')
    for dtype, options in (('c16', {}), ('bool', {}), ('i4', {'scale': 0}),
                           ('f8', {'scale': '0.0'}), ('i4', {'offset': 1.5}),
                           ('i4', {'scale': 0.5}), ('u1', {'offset': -1}), ('i1', {'scale': 128})):
        with pytest.raises(ValueError):
            a = encoding_array(np.zeros(2, dtype=dtype), filters=[ScaleOffset(**options)])
            a[:] = 1
            reopened_values(a)
    for dtype, values, options, fill in (
        ('i1', [64, 1], {'scale': 2}, 0), ('u4', [2**32-1, 1], {'scale': 2}, 0),
        ('u8', [2**64-1, 1], {'scale': 2}, 0), ('u8', [50, 100], {'offset': 100}, 100)):
        with pytest.raises(ValueError):
            data = np.array(values, dtype=dtype)
            a = encoding_array(data, filters=[ScaleOffset(**options)], fill_value=fill)
            a[:] = data
            reopened_values(a)
    # Results exactly at a type's limit are valid; one further is refused.
    for dtype, values, options, fill, encoded in (
        ('i1', [126, 0], {'offset': -1}, -1, [127, 1]), ('i1', [-127, 0], {'offset': 1}, 1, [-128, -1]),
        ('i4', [2147483646, 0], {'offset': -1}, -1, [2147483647, 1]),
        ('u4', [1431655765, 1], {'scale': 3}, 0, [4294967295, 3]),
        ('u8', [6148914691236517205, 1], {'scale': 3}, 0, [2**64 - 1, 3])):
        check_encoded(np.array(values, dtype=dtype), [ScaleOffset(**options)],
                      np.array(encoded, dtype=dtype), dtype, fill_value=fill)
    for dtype, values, options, fill in (('i4', [2147483647, 0], {'offset': -1}, -1),
                                         ('u8', [6148914691236517206, 1], {'scale': 3}, 0)):
        with pytest.raises(ValueError):
            data = np.array(values, dtype=dtype)
            a = encoding_array(data, filters=[ScaleOffset(**options)], fill_value=fill)
            a[:] = data
            reopened_values(a)
    # Stored values that cannot decode are refused, in the widest type too.
    for dtype, options, fill, original, stored in (('u8', {'offset': 1}, 1, [1, 2], [2**64 - 1, 1]),
                                                   ('u8', {'scale': 2}, 0, [1, 2], [3, 4]),
                                                   ('i4', {'scale': 2}, 0, [1, 2], [3, 4]),
                                                   ('i4', {'offset': 1}, 1, [1, 2], [2147483647, 4])):
        data = np.array(original, dtype=dtype)
        a = encoding_array(data, filters=[ScaleOffset(**options)], fill_value=fill,
                           serializer=BytesCodec(endian='little'))
        a[:] = data
        np.testing.assert_array_equal(reopened_values(a), data)
        replace_payload(a, np.array(stored, dtype=np.dtype(dtype).newbyteorder('<')).tobytes())
        with pytest.raises(ValueError):
            reopened_values(a)
    a = check_encoded(np.array([2, 4], dtype='i2'), [ScaleOffset(scale=2)], [4, 8], 'i2')
    replace_payload(a, np.array([3, 8], dtype='<i2').tobytes())
    with pytest.raises(ValueError):
        reopened_values(a)
    a = check_encoded(np.array([1, 2], dtype='i1'), [ScaleOffset(offset=100)], [-99, -98], 'i1', fill_value=100)
    replace_payload(a, np.array([100, 101], dtype='i1').tobytes())
    with pytest.raises(ValueError):
        reopened_values(a)


def test_f05_t08():
    data = np.array([-2.5, -1.5, -0.2, 0.2, 1.5, 2.5], dtype='f8')
    vectors = {'nearest-even': [-2, -2, 0, 0, 2, 2], 'nearest-away': [-3, -2, 0, 0, 2, 3],
               'towards-zero': [-2, -1, 0, 0, 1, 2], 'towards-positive': [-2, -1, 0, 1, 2, 3],
               'towards-negative': [-3, -2, -1, 0, 1, 2]}
    for mode, expected in vectors.items():
        check_encoded(data, [CastValue(data_type='int16', rounding=mode)], expected, 'i2', decoded=expected)
    check_encoded(data, [CastValue(data_type='int16')], vectors['nearest-even'], 'i2', decoded=vectors['nearest-even'])
    for source, target, values in (('i8', 'float32', [17, -313, 4097]),
                                   ('f8', 'float32', [1.5, -2.25, 7.125]), ('u2', 'int32', [0, 255, 65535])):
        check_encoded(np.array(values, dtype=source), [CastValue(data_type=target)], values, target)
    data = np.array([[16777217, -16777217], [16777219, -16777219]], dtype='i8')
    for mode, expected in (
        ('nearest-even', [16777216, 16777220, -16777216, -16777220]),
        ('nearest-away', [16777218, 16777220, -16777218, -16777220]),
        ('towards-zero', [16777216, 16777218, -16777216, -16777218]),
        ('towards-positive', [16777218, 16777220, -16777216, -16777218]),
        ('towards-negative', [16777216, 16777218, -16777218, -16777220])):
        check_encoded(data, [TransposeCodec(order=(1, 0)), CastValue(data_type='float32', rounding=mode)],
                      expected, 'f4', decoded=np.array(expected).reshape(2, 2).T)


def test_f05_t09():
    for source, target, values, clamp, wrap in (
        ('i2', 'int8', [-129, -128, 127, 128], [-128, -128, 127, 127], [127, -128, 127, -128]),
        ('i4', 'uint8', [-1, 0, 255, 256], [0, 0, 255, 255], [255, 0, 255, 0]),
        ('i8', 'int32', [-2147483649, 2147483648], [-2147483648, 2147483647], [2147483647, -2147483648])):
        data = np.array(values, dtype=source)
        with pytest.raises(ValueError):
            a = encoding_array(data, filters=[CastValue(data_type=target)])
            a[:] = data
            reopened_values(a)
        for policy, expected in (('clamp', clamp), ('wrap', wrap)):
            check_encoded(data, [CastValue(data_type=target, out_of_range=policy)], expected, target, decoded=expected)
    data = np.array([0, 2**63], dtype='u8')
    with pytest.raises(ValueError):
        a = encoding_array(data, filters=[CastValue(data_type='int64')])
        a[:] = data
        reopened_values(a)
    for policy, encoded, decoded in (
        ('clamp', [0, 2**63-1], [0, 2**63-1]),
        ('wrap', [0, -2**63], [0, 2**63])):
        check_encoded(data, [CastValue(data_type='int64', out_of_range=policy)],
                      np.array(encoded, dtype='i8'), 'i8', decoded=np.array(decoded, dtype='u8'))
    with pytest.raises(ValueError):
        a = encoding_array(np.array([1, 2], dtype='i4'), filters=[CastValue(data_type='float32', out_of_range='wrap')])
        a[:] = [1, 2]
        reopened_values(a)
    a = check_encoded(np.array([1, 2], dtype='i1'), [CastValue(data_type='int16')], [1, 2], 'i2')
    replace_payload(a, np.array([128, 2], dtype='<i2').tobytes())
    with pytest.raises(ValueError):
        reopened_values(a)


def test_f05_t10():
    data = np.array([1, 2, 3], dtype='i4')
    check_encoded(data, [CastValue(data_type='int16')], [1, 2, 3], 'i2')
    check_encoded(data, [CastValue(data_type='int16', scalar_map={'encode': [(1, 9)]})], [9, 2, 3], 'i2', decoded=[9, 2, 3])
    check_encoded(data, [CastValue(data_type='int16', scalar_map={'decode': [(2, 17)]})], [1, 2, 3], 'i2', decoded=[1, 17, 3])
    a = check_encoded(np.array([1000, 2, 3], dtype='i4'),
                      [CastValue(data_type='int8', scalar_map={'encode': [(1000, 7)], 'decode': [(7, -500)]})],
                      [7, 2, 3], 'i1', decoded=[-500, 2, 3])
    replace_payload(a, np.array([7, 4, 5], dtype='i1').tobytes())
    np.testing.assert_array_equal(reopened_values(a), [-500, 4, 5])


def test_f05_t11():
    check_encoded(np.array([1.5, -2.5], dtype='f8'), [CastValue(data_type='int16')], [2, -2], 'i2', decoded=[2, -2])
    from F05_helpers import check_missing_conversion_support
    check_missing_conversion_support()
    for source, target in (('c16', 'float32'), ('bool', 'int16'), ('i4', 'complex64')):
        with pytest.raises(ValueError):
            a = encoding_array(np.zeros(2, dtype=source), filters=[CastValue(data_type=target)])
            a[:] = 1
            reopened_values(a)


def test_f05_t12():
    import gzip
    from F05_helpers import RegisteredGzip
    data = np.array([17, -313, 4097, 52, -6, 81], dtype='i4')
    raw = data.astype('<i4').tobytes()
    for codec, decode in ((ext.LZ4(), nc.LZ4().decode), (ext.Zlib(level=3), zlib.decompress),
                           (ext.BZ2(level=3), bz2.decompress), (ext.LZMA(), lzma.decompress)):
        register_codec(codec.codec_name, type(codec))
        a = encoding_array(data, compressors=[codec], serializer=BytesCodec(endian='little'))
        a[:] = data
        assert decode(chunk_payload(a)) == raw
        b = velnora.open_array(a.store, mode='r')
        np.testing.assert_array_equal(b[:], data)
        assert b.compressors[0].to_dict() == codec.to_dict()
    a = encoding_array(data, compressors=[ext.CRC32()], serializer=BytesCodec(endian='little'))
    a[:] = data
    protected = chunk_payload(a)
    assert int.from_bytes(protected[:4], 'little') == zlib.crc32(raw)
    assert protected[4:] == raw
    np.testing.assert_array_equal(reopened_values(a), data)
    damaged = bytearray(protected)
    damaged[-1] ^= 1
    replace_payload(a, bytes(damaged))
    with pytest.raises(RuntimeError):
        reopened_values(a)
    check_encoded(data, [ext.Delta(dtype='i4')], [17, -330, 4410, -4045, -58, 87], 'i4')
    # Different encoded widths and real-valued differences use independent
    # subtraction, not the encoder's own inverse, as the stored-byte oracle.
    for native, encoded_type, values in (
        ('i4', 'i2', [[41, 35, -17], [90, 22, 87]]),
        ('f4', 'f8', [[1.5, -2.25, 7.125], [4.5, -0.25, 8.0]]),
    ):
        values = np.array(values, dtype=native)
        flat = values.astype('f8').ravel()
        differences = np.concatenate((flat[:1], flat[1:] - flat[:-1]))
        check_encoded(values, [ext.Delta(dtype=native, astype=encoded_type)],
                      differences, encoded_type, config={'order': 'F'})
    # Each chunk starts a new difference sequence, in row-major coordinates
    # even when the array's in-memory order is column-major.
    values = np.array([[11, 18, -4], [29, 7, 31],
                       [83, 16, 45], [2, 61, -9]], dtype='i4')
    delta = velnora.create_array({}, data=values, chunks=(2, 3), compressors=None,
                               filters=[ext.Delta(dtype='i4')],
                               serializer=BytesCodec(endian='little'), config={'order': 'F'})
    for index in (0, 1):
        flat = values[index * 2:index * 2 + 2].ravel()
        expected = np.concatenate((flat[:1], flat[1:] - flat[:-1]))
        delta_payload = invoke(delta.store.get, f'c/{index}/0').value.to_bytes()
        np.testing.assert_array_equal(np.frombuffer(delta_payload, dtype='<i4'), expected)
    np.testing.assert_array_equal(reopened_values(delta), values)
    # Independent arithmetic oracle: normal binary values round to the nearest
    # point of the requested significand grid. No product encoder supplies the
    # expected values. Two reduced precisions detect an ignored precision choice;
    # full precision detects an unconditional lossy transform.
    for native, full_precision in (('f2', 10), ('f4', 23), ('f8', 52)):
        values = np.array([0, 1.03125, 1.09375, -1.03125, -1.09375,
                           13.123456, -0.003217, 1043.875], dtype=native)
        fractions, exponents = np.frexp(values.astype('f8'))
        for precision in (0, 3, 7, full_precision):
            rounded = np.ldexp(np.rint(np.ldexp(fractions, precision + 1)),
                               exponents - precision - 1).astype(native)
            a = encoding_array(values, filters=[ext.BitRound(keepbits=precision)],
                               serializer=BytesCodec(endian='little'))
            a[:] = values
            np.testing.assert_array_equal(np.frombuffer(chunk_payload(a), dtype='<'+native), rounded)
            b = velnora.open_array(a.store, mode='r')
            np.testing.assert_array_equal(b[:], rounded)
            assert b.metadata.codecs[0].to_dict()['configuration']['keepbits'] == precision
        for precision in (-1, full_precision + 1):
            with pytest.raises(ValueError):
                a = encoding_array(values, filters=[ext.BitRound(keepbits=precision)])
                a[:] = values
                reopened_values(a)
    for native in ('i4', 'bool', 'c8'):
        with pytest.raises((TypeError, ValueError)):
            values = np.ones((2, 3), dtype=native)
            a = encoding_array(values, filters=[ext.BitRound(keepbits=3)])
            a[:] = values
            reopened_values(a)

    # Packing must preserve actual bits, including a partial final byte, and
    # reduce payload size before compression. No particular bit layout is used.
    for shape in ((2, 4), (3, 5)):
        values = (np.arange(np.prod(shape)).reshape(shape) % 3) == 1
        plain = encoding_array(values, serializer=BytesCodec())
        plain[:] = values
        packed = encoding_array(values, filters=[ext.PackBits()], serializer=BytesCodec())
        packed[:] = values
        assert len(chunk_payload(packed)) < len(chunk_payload(plain))
        np.testing.assert_array_equal(reopened_values(packed), values)
    for native in ('i1', 'f4'):
        with pytest.raises(ValueError):
            values = np.array([[0, 1], [1, 0]], dtype=native)
            a = encoding_array(values, filters=[ext.PackBits()])
            a[:] = values
            reopened_values(a)

    # The PRD's increment rule supplies an arithmetic oracle for both fine and
    # coarse decimal requests, with binary ties of either parity and sign.
    for native in ('f2', 'f4', 'f8'):
        values = np.array([[1.00390625, 1.01171875, -1.00390625, -1.01171875],
                           [13.123456, -123.8125, 234.5, -235.5]], dtype=native)
        for digits in (-2, -1, 0, 2):
            increment = 2.0 ** np.floor(np.log2(10.0 ** -digits))
            expected = (np.rint(values.astype('f8') / increment) * increment).astype(native)
            a = encoding_array(values, filters=[ext.Quantize(digits=digits)],
                               serializer=BytesCodec(endian='little'))
            a[:] = values
            quantized = np.frombuffer(chunk_payload(a), dtype='<'+native).reshape(values.shape)
            np.testing.assert_array_equal(quantized, expected)
            np.testing.assert_array_equal(reopened_values(a), expected)
    a = encoding_array(data, compressors=[GzipCodec(level=2)])
    a[:] = data
    document = json.loads(invoke(a.store.get, 'zarr.json').value.to_bytes())
    name = RegisteredGzip.encoding_name
    document['codecs'][-1]['name'] = name
    from velnora.core.buffer import default_buffer_prototype
    invoke(a.store.set, 'zarr.json', default_buffer_prototype().buffer.from_bytes(json.dumps(document).encode()))
    with pytest.raises(UnknownCodecError) as caught:
        reopened_values(a)
    assert name in str(caught.value)
    register_codec(name, RegisteredGzip)
    np.testing.assert_array_equal(reopened_values(a), data)
    b = velnora.open_array(a.store, mode='r')
    assert b.compressors[0].to_dict()['configuration'] == {'level': 2}
    assert gzip.decompress(chunk_payload(a)) == raw
