# feature: F01
"""Acceptance checks for public BER/DER element framing operations."""

import unittest

from cobaltform.core import Asn1Value, Integer, OctetString
from cobaltform.parser import emit, parse, peek

from _helpers import observe
from F01_helpers import framing_vectors


def test_f01_t01():
    checks = unittest.TestCase()
    for class_, method, tag, header, contents in framing_vectors():
        with checks.subTest(class_=class_, method=method, tag=tag):
            encoded = header + contents
            result = observe(parse, args=(encoded,)).value
            checks.assertIsInstance(result, tuple)
            checks.assertEqual(result, (class_, method, tag, header, contents, b''))
            checks.assertEqual(observe(peek, args=(encoded,)).value, len(encoded))

    # X.690 8.1.3.6 and 8.1.5: only the enclosing EOC is its trailer.
    # Zero octets inside a definite child and a child's long-form zero
    # length are contents, not an early end of the enclosing element.
    contents = (b'\x04\x04\x00\x00\xfe\xff'
                b'\xa1\x80\x02\x01\x09\x00\x00'
                b'\x30\x82\x00\x00')
    encoded = b'\x30\x80' + contents + b'\x00\x00'
    checks.assertEqual(observe(parse, args=(encoded,)).value,
                     (0, 1, 16, b'\x30\x80', contents, b'\x00\x00'))
    checks.assertEqual(observe(peek, args=(encoded,)).value, len(encoded))

def test_f01_t02():
    checks = unittest.TestCase()
    for encoded, expected in (
        (b'\x04\x03abc', (0, 0, 4, b'\x04\x03', b'abc', b'')),
        (b'\x30\x80\x05\x00\x00\x00',
         (0, 1, 16, b'\x30\x80', b'\x05\x00', b'\x00\x00')),
    ):
        checks.assertEqual(observe(parse, args=(encoded,),
                                 kwargs={'strict': True}).value, expected)
        for tail in (b'\x02\x01\x07', b'\xff'):
            with checks.subTest(encoded=encoded, tail=tail):
                combined = encoded + tail
                checks.assertEqual(observe(parse, args=(combined,)).value, expected)
                checks.assertEqual(observe(parse, args=(combined,),
                                         kwargs={'strict': False}).value, expected)
                checks.assertEqual(observe(peek, args=(combined,)).value, len(encoded))
                refusal = observe(parse, args=(combined,),
                                  kwargs={'strict': True}, expected_exceptions=(ValueError,))
                checks.assertIsInstance(refusal.error, ValueError)
    # The same complete-consumption request applies when a typed value is
    # loaded, not only to the low-level framing reader.
    for cls, encoded, read in ((Integer, b'\x02\x01\x07', lambda v: v.native),
                               (OctetString, b'\x04\x01x', lambda v: v.native),
                               (Asn1Value, b'\x30\x03\x02\x01\x09', lambda v: v[0].native)):
        native = read(observe(cls.load, args=(encoded,)).value)
        for tail in (b'\x05\x00', b'\xff'):
            with checks.subTest(typed=cls.__name__, tail=tail):
                checks.assertEqual(read(observe(cls.load, args=(encoded + tail,)).value), native)
                checks.assertEqual(read(observe(cls.load, args=(encoded,),
                                                kwargs={'strict': True}).value), native)
                refusal = observe(cls.load, args=(encoded + tail,), kwargs={'strict': True},
                                  consumers=(read,), expected_exceptions=(ValueError,))
                checks.assertIsInstance(refusal.error, ValueError)
    checks.assertEqual(Integer.load(b'\x02\x01\x07\x05\x00').native, 7)

def test_f01_t03():
    checks = unittest.TestCase()
    valid = (
        (b'\x04\x00', (0, 0, 4, b'\x04\x00', b'', b'')),
        (b'\xbf\x1f\x01x', (2, 1, 31, b'\xbf\x1f\x01', b'x', b'')),
        (b'\x04\x81\x80' + b'x' * 128,
         (0, 0, 4, b'\x04\x81\x80', b'x' * 128, b'')),
        (b'\x30\x80\x05\x00\x00\x00',
         (0, 1, 16, b'\x30\x80', b'\x05\x00', b'\x00\x00')),
    )
    for encoded, expected in valid:
        checks.assertEqual(observe(parse, args=(encoded,)).value, expected)
        checks.assertEqual(observe(peek, args=(encoded,)).value, len(encoded))

    malformed = (
        b'',                                  # Empty input
        b'\xbf', b'\xbf\x81',                 # Truncated high tag
        b'\x04', b'\xbf\x1f',                 # Missing length
        b'\x04\x81', b'\x04\x82\x01',        # Truncated long length
        b'\x04\x02x',                         # Truncated short contents
        b'\x04\x81\x80' + b'x' * 127,        # Truncated long contents
        b'\x30\x80',                          # Missing outer EOC
        b'\x30\x80\x30\x80\x00\x00',       # Only inner EOC
        b'\x30\x80\x05\x00\x00',            # Partial EOC
        b'\x04\x80\x00\x00',                 # Primitive indefinite length
        b'\x1f\x04\x00',                      # High-tag form for low tag
        b'\xbf\x80\x1f\x00',                 # Leading zero tag group
    )
    for entry in (parse, peek):
        for encoded in malformed:
            with checks.subTest(entry=entry.__name__, encoded=encoded):
                result = observe(entry, args=(encoded,), expected_exceptions=(ValueError,))
                checks.assertIsInstance(result.error, ValueError)
        for incompatible in ('\x04\x00', bytearray(b'\x04\x00'), [4, 0], None, 4):
            with checks.subTest(entry=entry.__name__, input_type=type(incompatible)):
                result = observe(entry, args=(incompatible,), expected_exceptions=(TypeError,))
                checks.assertIsInstance(result.error, TypeError)

def test_f01_t04():
    checks = unittest.TestCase()
    # A complete primitive descendant has exactly `ancestors` indefinite
    # containers above it. No malformed tail can cause the limit refusal.
    for ancestors in (1, 9, 10):
        encoded = b'\x30\x80' * ancestors + b'\x04\x01x' + b'\x00\x00' * ancestors
        contents = encoded[2:-2]
        with checks.subTest(ancestors=ancestors):
            checks.assertEqual(observe(parse, args=(encoded,),
                                     kwargs={'strict': True}).value,
                             (0, 1, 16, b'\x30\x80', contents, b'\x00\x00'))
            checks.assertEqual(observe(peek, args=(encoded,)).value, len(encoded))
    for ancestors in (11, 12):
        encoded = b'\x30\x80' * ancestors + b'\x04\x01x' + b'\x00\x00' * ancestors
        for entry in (parse, peek):
            with checks.subTest(ancestors=ancestors, entry=entry.__name__):
                result = observe(entry, args=(encoded,), expected_exceptions=(ValueError,))
                checks.assertIsInstance(result.error, ValueError)

def test_f01_t05():
    checks = unittest.TestCase()
    for class_, method, tag, header, contents in framing_vectors():
        with checks.subTest(class_=class_, method=method, tag=tag):
            result = observe(emit, args=(class_, method, tag, contents)).value
            checks.assertIsInstance(result, bytes)
            checks.assertEqual(result, header + contents)

    for args in ((-1, 0, 4, b'x'), (4, 0, 4, b'x'),
                 (0, -1, 4, b'x'), (0, 2, 4, b'x'), (0, 0, -1, b'x')):
        with checks.subTest(args=args):
            result = observe(emit, args=args, expected_exceptions=(ValueError,))
            checks.assertIsInstance(result.error, ValueError)
    for position, values in ((0, ('0', 0.5, None)), (1, ('0', 0.5, None)),
                             (2, ('4', 4.5, None)),
                             (3, ('x', bytearray(b'x'), [120], None))):
        for value in values:
            args = [0, 0, 4, b'x']
            args[position] = value
            with checks.subTest(position=position, input_type=type(value)):
                result = observe(emit, args=tuple(args), expected_exceptions=(TypeError,))
                checks.assertIsInstance(result.error, TypeError)
