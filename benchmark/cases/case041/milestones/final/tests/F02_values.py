# feature: F02
"""Acceptance tests for universal values through the public Python API."""

import unittest

from cobaltform.core import (
    BMPString, BitString, Boolean, CharacterString, GeneralString, GraphicString, IA5String,
    Integer, IntegerBitString, IntegerOctetString, Null, NumericString, ObjectIdentifier,
    OctetBitString, OctetString, PrintableString, UTF8String, UniversalString,
    VideotexString, VisibleString,
)

from _helpers import observe
from F02_helpers import (
    NamedNumber, NamedAlternative, NamedIdentifier, SparseFlags,
    scalar_vectors, text_vectors, short_primitive, nested_chunks,
)


class TestValue(unittest.TestCase):
    def test_f02_t01(self):
        for cls, native, encoded in scalar_vectors():
            made = cls(native)
            self.assertEqual(made.native, native, msg=('type=%r' % (cls.__name__,), 'value=%r' % (native,),))
            self.assertEqual(made.dump(), encoded, msg=('type=%r' % (cls.__name__,), 'value=%r' % (native,),))
            loaded = cls.load(encoded)
            self.assertEqual(loaded.native, native, msg=('type=%r' % (cls.__name__,), 'value=%r' % (native,),))
            self.assertEqual(loaded.dump(force=True), encoded, msg=('type=%r' % (cls.__name__,), 'value=%r' % (native,),))
        # X.690 BER boolean truth is any nonzero content octet.
        self.assertIs(Boolean.load(b'\x01\x01\x01').native, True)
        # ENUMERATED has caller-defined alternatives, not unrestricted integers.
        self.assertEqual(NamedAlternative('active').dump(), b'\x0a\x02\x00\x80')
        self.assertEqual(NamedAlternative.load(b'\x0a\x01\x00').native, 'idle')
        for cls, encoded in (
            (Integer, b'\x04\x01\x01'),
            (Boolean, b'\x21\x03\x01\x01\xff'),
            (Integer, b'\x22\x03\x02\x01\x01'),
            (Null, b'\x25\x00'),
            (ObjectIdentifier, b'\x26\x02\x06\x00'),
            (NamedAlternative, b'\x02\x01\x00'),
        ):
            refusal = observe(cls.load, args=(encoded,),
                              consumers=(lambda v: v.native, lambda v: v.dump()),
                              expected_exceptions=(ValueError,))
            self.assertIsInstance(refusal.error, ValueError)

    def test_f02_t02(self):
        for cls, supplied, expected, encoded in (
            (NamedNumber, 'below', 'below', b'\x02\x01\xf9'),
            (NamedNumber, 128, 'above', b'\x02\x02\x00\x80'),
            (NamedNumber, 19, 19, b'\x02\x01\x13'),
            (NamedAlternative, 'idle', 'idle', b'\x0a\x01\x00'),
            (NamedAlternative, 128, 'active', b'\x0a\x02\x00\x80'),
            (NamedIdentifier, 'organization', 'organization', b'\x06\x06\x2a\x86\x48\x86\xf7\x0d'),
            (NamedIdentifier, '1.2.3.9', '1.2.3.9', b'\x06\x03\x2a\x03\x09'),
        ):
            self.assertEqual(cls(supplied).native, expected, msg=('type=%r' % (cls.__name__,), 'value=%r' % (supplied,),))
            self.assertEqual(cls(supplied).dump(), encoded, msg=('type=%r' % (cls.__name__,), 'value=%r' % (supplied,),))
            self.assertEqual(cls.load(encoded).native, expected, msg=('type=%r' % (cls.__name__,), 'value=%r' % (supplied,),))
        for cls, value in ((NamedNumber, 'unknown'), (NamedIdentifier, 'unknown'),
                           (NamedAlternative, 'unknown'), (NamedAlternative, 19)):
            refusal = observe(cls, args=(value,),
                              consumers=(lambda v: v.native, lambda v: v.dump()),
                              expected_exceptions=(ValueError,))
            self.assertIsInstance(refusal.error, ValueError)
        refusal = observe(NamedAlternative.load, args=(b'\x0a\x01\x13',),
                          consumers=(lambda v: v.native,),
                          expected_exceptions=(ValueError, KeyError))
        self.assertIsInstance(refusal.error, (ValueError, KeyError))

    def test_f02_t03(self):
        flags = SparseFlags({'read', 'audit'})
        for expected, encoded, edit in (
            ({'read', 'audit'}, b'\x03\x03\x06\x80\x40', None),
            ({'read', 'write', 'audit'}, b'\x03\x03\x06\x90\x40', ('write', True)),
            ({'write', 'audit'}, b'\x03\x03\x06\x10\x40', ('read', False)),
            ({'write'}, b'\x03\x02\x04\x10', ('audit', False)),
            (set(), b'\x03\x01\x00', ('write', False)),
        ):
            if edit is not None:
                flags[edit[0]] = edit[1]
            self.assertEqual(flags.native, expected)
            self.assertEqual(flags.dump(), encoded)
            loaded = SparseFlags.load(encoded)
            self.assertEqual(loaded.native, expected)
            for name in ('read', 'write', 'audit'):
                self.assertEqual(flags[name], name in expected)
                self.assertEqual(loaded[name], name in expected)
        positional = SparseFlags((1, 0, 0, 1, 0, 0, 0, 0, 0, 1))
        # Named bits are also changed on a loaded value, before any native read.
        for encoded, name, state, expected, changed in (
            (b'\x03\x02\x04\x10', 'audit', True, {'write', 'audit'}, b'\x03\x03\x06\x10\x40'),
            (b'\x03\x03\x06\x90\x40', 'write', False, {'read', 'audit'}, b'\x03\x03\x06\x80\x40'),
        ):
            loaded = SparseFlags.load(encoded)
            loaded[name] = state
            self.assertIs(loaded[name], state)
            self.assertEqual(loaded.native, expected)
            self.assertEqual(loaded.dump(), changed)
        self.assertEqual(positional.native, {'read', 'write', 'audit'})
        self.assertEqual(positional.dump(), b'\x03\x03\x06\x90\x40')
        self.assertEqual(SparseFlags((1,)).native, {'read'})
        self.assertEqual(SparseFlags(()).native, set())
        with self.assertRaises(ValueError):
            positional['unknown']
        with self.assertRaises(ValueError):
            positional['unknown'] = True
        refusal = observe(SparseFlags, args=((0,) * 11,),
                          consumers=(lambda v: v.native, lambda v: v.dump()),
                          expected_exceptions=(ValueError,))
        self.assertIsInstance(refusal.error, ValueError)

    def test_f02_t04(self):
        for dotted, name, encoded in (
            ('1.2.840.113549', 'organization', b'\x06\x06\x2a\x86\x48\x86\xf7\x0d'),
            ('2.999.16384.0.128', 'large', b'\x06\x08\x88\x37\x81\x80\x00\x00\x81\x00'),
        ):
            self.assertEqual(NamedIdentifier.map(dotted), name)
            self.assertEqual(NamedIdentifier.unmap(name), dotted)
            for supplied in (name, dotted):
                value = NamedIdentifier(supplied)
                self.assertEqual(value.dotted, dotted)
                self.assertEqual(value.native, name)
                self.assertEqual(value.dump(), encoded)
            self.assertEqual(NamedIdentifier.load(encoded).dotted, dotted)
        for dotted, encoded in (
            ('0.39.0', b'\x06\x02\x27\x00'),
            ('1.0.5', b'\x06\x02\x28\x05'),
            ('1.39.127', b'\x06\x02\x4f\x7f'),
            ('2.0.5', b'\x06\x02\x50\x05'),
            ('2.40.128', b'\x06\x03\x78\x81\x00'),
        ):
            self.assertEqual(ObjectIdentifier(dotted).dump(), encoded)
            self.assertEqual(ObjectIdentifier.load(encoded).native, dotted)
        for dotted in ('3.1.2', '0.40.2', '1.40.2'):
            refusal = observe(ObjectIdentifier, args=(dotted,),
                              consumers=(lambda v: v.native, lambda v: v.dump()),
                              expected_exceptions=(ValueError,))
            self.assertIsInstance(refusal.error, ValueError)

    def test_f02_t05(self):
        for cls, tag, text, payload in text_vectors():
            for value, contents in ((text, payload), ('', b'')):
                encoded = short_primitive(tag, contents)
                self.assertEqual(cls(value).native, value, msg=('type=%r' % (cls.__name__,), 'value=%r' % (value,),))
                self.assertEqual(cls(value).dump(), encoded, msg=('type=%r' % (cls.__name__,), 'value=%r' % (value,),))
                self.assertEqual(cls.load(encoded).native, value, msg=('type=%r' % (cls.__name__,), 'value=%r' % (value,),))
        binary = b'\x00\xff\x80A'
        self.assertEqual(VideotexString(binary).native, binary)
        self.assertEqual(VideotexString(binary).dump(), b'\x15\x04' + binary)
        self.assertEqual(VideotexString.load(b'\x15\x04' + binary).native, binary)
        for cls, value in (
            (IA5String, 'é'), (NumericString, '水'),
            (PrintableString, '水'), (GraphicString, '水'),
            (VisibleString, '水'), (GeneralString, '水'),
            (CharacterString, '水'), (UTF8String, '\ud800'),
            (UniversalString, '\ud800'), (BMPString, '\ud800'),
        ):
            refusal = observe(cls, args=(value,), consumers=(lambda v: v.dump(),),
                              expected_exceptions=(UnicodeEncodeError,))
            self.assertIsInstance(refusal.error, UnicodeEncodeError)

    def test_f02_t06(self):
        # Same-tag casts preserve contents, including unused-bit information.
        for encoded, interpretations in (
            (b'\x03\x03\x04\x01\xa0', (
                (BitString, (0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 0)),
                (OctetBitString, b'\x01\xa0'), (IntegerBitString, 26))),
            (b'\x04\x03\x00\x81\xff', (
                (OctetString, b'\x00\x81\xff'), (IntegerOctetString, 33279))),
        ):
            for source, native in interpretations:
                original = source.load(encoded)
                self.assertEqual(original.native, native)
                for target, expected in interpretations:
                    converted = original.cast(target)
                    self.assertIsInstance(converted, target)
                    self.assertEqual(converted.native, expected)
                    self.assertEqual(converted.contents, encoded[2:])
                    self.assertEqual(converted.dump(), encoded)
        for cls, supplied, encoded in (
            (OctetBitString, b'\x00\x81', b'\x03\x03\x00\x00\x81'),
        ):
            self.assertEqual(cls(supplied).native, supplied)
            self.assertEqual(cls(supplied).dump(), encoded)
        # Integer interpretations do not promise a default byte/bit width.
        # Interpret emitted contents with Python's independent integer primitive
        # instead of requiring this checkout's choice of leading zero octets.
        for cls, tag in ((IntegerBitString, 3), (IntegerOctetString, 4)):
            for supplied in (0, 129, 65539):
                value = cls(supplied)
                self.assertEqual(value.native, supplied)
                encoded = value.dump()
                contents = value.contents
                if tag == 3:
                    self.assertGreaterEqual(len(contents), 1)
                    self.assertIn(contents[0], range(8))
                    decoded = int.from_bytes(contents[1:], 'big') >> contents[0]
                else:
                    decoded = int.from_bytes(contents, 'big')
                self.assertEqual(decoded, supplied)
                self.assertEqual(cls.load(encoded).native, supplied)
        integer = IntegerOctetString(129)
        integer.set_encoded_width(4)
        self.assertEqual(integer.native, 129)
        self.assertEqual(integer.dump(), b'\x04\x04\x00\x00\x00\x81')
        integer.set_encoded_width(2)
        self.assertEqual(integer.dump(), b'\x04\x02\x00\x81')
        for value, target in ((BitString((1,)), OctetString),
                              (OctetString(b'x'), BitString)):
            with self.assertRaises(TypeError):
                value.cast(target)

    def test_f02_t07(self):
        chunks = (b'\x04\x02\x00\x80', b'\x04\x00', b'\x04\x02\xffA')
        value = OctetString.load(nested_chunks(4, chunks))
        self.assertEqual(value.native, b'\x00\x80\xffA')
        self.assertEqual(value.dump(force=True), b'\x04\x04\x00\x80\xffA')
        chunks = (b'\x03\x02\x00\x81', b'\x03\x01\x00', b'\x03\x02\x05\xa0')
        value = BitString.load(nested_chunks(3, chunks))
        self.assertEqual(value.native, (1, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1))
        self.assertEqual(value.dump(force=True), b'\x03\x03\x05\x81\xa0')
        for cls, tag, text, payload in text_vectors():
            # Split at a complete character boundary, including multibyte text.
            first = text[0]
            first_payload = payload[:len(first.encode(
                'utf-8' if tag == 12 else 'utf-32-be' if tag == 28
                else 'utf-16-be' if tag == 30 else 'latin-1'))]
            chunks = (short_primitive(tag, first_payload), short_primitive(tag, b''),
                      short_primitive(tag, payload[len(first_payload):]))
            value = cls.load(nested_chunks(tag, chunks))
            self.assertEqual(value.native, text, msg=('type=%r' % (cls.__name__,),))
            self.assertEqual(value.dump(force=True), short_primitive(tag, payload), msg=('type=%r' % (cls.__name__,),))
        value = VideotexString.load(nested_chunks(21, (b'\x15\x01\xff', b'\x15\x01\x00')))
        self.assertEqual(value.native, b'\xff\x00')
        self.assertEqual(value.dump(force=True), b'\x15\x02\xff\x00')
