# feature: F03
"""Structured documents observed through the public Python API.

Literal encodings are X.690 (2015) vectors (sections 8 and 11); they are
independent of the product's encoder. Unordered native views are compared by
membership, while DER wire order is checked only where promised.
"""

import unittest

from cobaltform.core import Asn1Value, Integer, OctetString, Sequence, Set, UTF8String

from _helpers import observe
from F02_helpers import scalar_vectors, text_vectors
from F03_helpers import (
    PairRecord, UnorderedRecord, IntegerList, IntegerBag, TextOrNumber,
    RecursiveRecord, PresenceRecord, ChoiceRecord, EditableRecord, TaggedRecord,
    OpenRecord, AssociatedOpenRecord, EmbeddedOctets, EmbeddedBits, MixedConcat,
    DiagnosticRecord, diagnostic_fields, check_diagnostic_headers,
)


class TestStructure(unittest.TestCase):
    def test_f03_t01(self):
        pair = {'number': 128, 'label': 'é'}
        encoded = b'\x30\x08\x02\x02\x00\x80\x0c\x02\xc3\xa9'
        for value in (PairRecord(pair), PairRecord.load(encoded)):
            self.assertEqual(value.native, pair)
            self.assertEqual(value['number'].native, 128)
            self.assertEqual(value['label'].native, 'é')
            self.assertEqual(value.dump(), encoded)
        # SET fields identify themselves by tags, independently of wire order.
        for encoded_set in (b'\x31\x06\x82\x01\x09\x80\x01Z',
                            b'\x31\x06\x80\x01Z\x82\x01\x09'):
            value = UnorderedRecord.load(encoded_set)
            self.assertEqual(value.native, {'number': 9, 'label': 'Z'})
            self.assertEqual(value['number'].native, 9)
            self.assertEqual(value['label'].native, 'Z')
        self.assertEqual(UnorderedRecord({'number': 9, 'label': 'Z'}).dump(),
                         b'\x31\x06\x80\x01Z\x82\x01\x09')
        for values, sequence, bag in (
            ([], b'\x30\x00', b'\x31\x00'),
            ([9], b'\x30\x03\x02\x01\x09', b'\x31\x03\x02\x01\x09'),
            ([9, -1, 9], b'\x30\x09\x02\x01\x09\x02\x01\xff\x02\x01\x09',
             b'\x31\x09\x02\x01\x09\x02\x01\x09\x02\x01\xff'),
        ):
            self.assertEqual(IntegerList(values).dump(), sequence)
            self.assertEqual(IntegerList.load(sequence).native, values)
            loaded = IntegerList.load(sequence)
            self.assertEqual([loaded[i].native for i in range(len(values))], values)
            self.assertEqual(IntegerBag(values).dump(), bag)
            self.assertCountEqual(IntegerBag.load(bag).native, values)
        for name, native, encoded_choice in (
            ('number', -5, b'\x02\x01\xfb'), ('text', 'hi', b'\x0c\x02hi'),
        ):
            for value in (TextOrNumber(name=name, value=native),
                          TextOrNumber.load(encoded_choice)):
                self.assertEqual(value.name, name)
                self.assertEqual(value.chosen.native, native)
                self.assertEqual(value.native, native)
                self.assertEqual(value.dump(), encoded_choice)
        recursive = {'child': {'child': {'number': 3}, 'number': 2}, 'number': 1}
        wire = b'\x30\x0d\x30\x08\x30\x03\x02\x01\x03\x02\x01\x02\x02\x01\x01'
        self.assertEqual(RecursiveRecord(recursive).dump(), wire)
        value = RecursiveRecord.load(wire)
        self.assertEqual(value['child']['child']['number'].native, 3)
        self.assertEqual(value['child']['number'].native, 2)
        self.assertEqual(value['number'].native, 1)

    def test_f03_t02(self):
        wire = b'\x30\x03\x02\x01\x07'
        for value in (PresenceRecord({'number': 7}), PresenceRecord.load(wire)):
            self.assertEqual(value.native, {'number': 7, 'extra': None,
                                            'enabled': True, 'nothing': None})
            self.assertEqual(value['extra'].native, None)
            self.assertEqual(value['extra'].dump(), b'')
            self.assertIs(value['enabled'].native, True)
            self.assertEqual(value['nothing'].dump(), b'')
            self.assertEqual(value.dump(), wire)
        # A present empty string and present NULL differ from omitted fields.
        present_wire = b'\x30\x07\x02\x01\x07\x80\x00\x81\x00'
        present = PresenceRecord.load(present_wire)
        self.assertEqual(present['extra'].native, b'')
        self.assertIsNone(present['nothing'].native)
        self.assertEqual(present['nothing'].dump(), b'\x81\x00')
        self.assertEqual(present.dump(), present_wire)
        disabled = PresenceRecord({'number': 7, 'enabled': False})
        self.assertIs(disabled['enabled'].native, False)
        self.assertEqual(disabled.dump(), b'\x30\x06\x02\x01\x07\x01\x01\x00')
        # Removing a defaulted field restores its declared default.
        del disabled['enabled']
        self.assertIs(disabled['enabled'].native, True)
        self.assertEqual(disabled.dump(), wire)
        for entry, args, consumers in (
            (PresenceRecord, ({'extra': b'x'},), (lambda v: v.dump(),)),
            (PresenceRecord.load, (b'\x30\x00',), (lambda v: v.native,)),
        ):
            result = observe(entry, args=args, consumers=consumers,
                             expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)

    def test_f03_t03(self):
        self.assertEqual(PairRecord.load(b'\x30\x06\x02\x01\x08\x0c\x01Q').native,
                         {'number': 8, 'label': 'Q'})
        self.assertEqual(ChoiceRecord.load(b'\x30\x03\x02\x01\x08')['value'].chosen.native, 8)
        for cls, wire in (
            (PairRecord, b'\x30\x06\x04\x01\x08\x0c\x01Q'),
            (PairRecord, b'\x30\x06\x02\x01\x08\x04\x01Q'),
            (ChoiceRecord, b'\x30\x03\x04\x01Q'),
        ):
            result = observe(cls.load, args=(wire,), consumers=(lambda v: v.native,),
                             expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)

    def test_f03_t04(self):
        wire = b'\x30\x16\x30\x06\x02\x01\x01\x0c\x01A\x30\x06\x02\x01\x02\x02\x01\x03\xa0\x04\x0c\x02ok'
        value = EditableRecord.load(wire)
        self.assertEqual(value.dump(), wire)
        value['pair']['number'] = 128
        value['numbers'].append(4)
        first = b'\x30\x1a\x30\x07\x02\x02\x00\x80\x0c\x01A\x30\x09\x02\x01\x02\x02\x01\x03\x02\x01\x04\xa0\x04\x0c\x02ok'
        self.assertEqual(value.dump(), first)
        value['pair']['label'] = 'B'
        value['numbers'][0] = -2
        del value['numbers'][1]
        self.assertEqual(value['numbers'].native, [-2, 4])
        del value['note']
        self.assertIsNone(value['note'].native)
        self.assertEqual(value['note'].dump(), b'')
        self.assertEqual(value['pair'].native, {'number': 128, 'label': 'B'})
        self.assertEqual(value.dump(), b'\x30\x11\x30\x07\x02\x02\x00\x80\x0c\x01B\x30\x06\x02\x01\xfe\x02\x01\x04')
        value['pair'] = {'number': 5, 'label': 'C'}
        self.assertEqual(value.dump(), b'\x30\x10\x30\x06\x02\x01\x05\x0c\x01C\x30\x06\x02\x01\xfe\x02\x01\x04')

    def test_f03_t05(self):
        wire = b'\x30\x10\x30\x06\x02\x01\x01\x0c\x01A\x30\x06\x02\x01\x02\x02\x01\x03'
        expected = {'pair': {'number': 1, 'label': 'A'}, 'numbers': [2, 3], 'note': None}
        # Copy both an unconsumed load and an already-interpreted document.
        for interpreted in (False, True):
            original = EditableRecord.load(wire)
            if interpreted:
                self.assertEqual(original.native, expected)
            copied = original.copy()
            self.assertEqual(copied.native, expected)
            self.assertEqual(copied.dump(), wire)
            copied['pair']['number'] = 9
            copied['numbers'].append(4)
            self.assertEqual(copied['pair']['number'].native, 9)
            self.assertEqual(copied['pair']['label'].native, 'A')
            self.assertEqual(copied['numbers'].native, [2, 3, 4])
            self.assertEqual(copied.dump(), b'\x30\x13\x30\x06\x02\x01\x09\x0c\x01A\x30\x09\x02\x01\x02\x02\x01\x03\x02\x01\x04')
            self.assertEqual(original.native, expected)
            self.assertEqual(original.dump(), wire)
            original['pair']['label'] = 'Z'
            self.assertEqual(copied['pair']['label'].native, 'A')
            self.assertEqual(original.dump(), b'\x30\x10\x30\x06\x02\x01\x01\x0c\x01Z\x30\x06\x02\x01\x02\x02\x01\x03')

    def test_f03_t06(self):
        # X.690 class bits, explicit wrappers, and implicit replacement tags.
        for tagging, wire in (
            ({'implicit': (0, 7)}, b'\x07\x01\x09'),
            ({'implicit': (1, 7)}, b'\x47\x01\x09'),
            ({'implicit': 7}, b'\x87\x01\x09'),
            ({'implicit': (3, 7)}, b'\xc7\x01\x09'),
            ({'explicit': (0, 7)}, b'\x27\x03\x02\x01\x09'),
            ({'explicit': (1, 7)}, b'\x67\x03\x02\x01\x09'),
            ({'explicit': 7}, b'\xa7\x03\x02\x01\x09'),
            ({'explicit': (3, 7)}, b'\xe7\x03\x02\x01\x09'),
            ({'explicit': ((1, 3), (2, 4))}, b'\xa4\x05\x63\x03\x02\x01\x09'),
        ):
            made = Integer(9, **tagging)
            self.assertEqual(made.dump(), wire)
            loaded = Integer.load(wire, **tagging)
            self.assertEqual(loaded.native, 9)
            self.assertEqual(loaded.untag().dump(), b'\x02\x01\x09')
            changed = loaded.retag({'implicit': (3, 8)})
            self.assertEqual(changed.native, 9)
            self.assertEqual(changed.dump(), b'\xc8\x01\x09')
            self.assertEqual(loaded.dump(), wire)
            explicit_copy = loaded.retag({'explicit': (1, 8)})
            self.assertEqual(explicit_copy.native, 9)
            self.assertEqual(explicit_copy.dump(), b'\x68\x03\x02\x01\x09')
        # The declared class, number and form are checked on reading: a value
        # that differs from the declaration in any of them is a type mismatch.
        for wire, tagging in (
            (b'\x07\x01\x09', {'implicit': (0, 8)}), (b'\x47\x01\x09', {'implicit': (2, 7)}),
            (b'\xc7\x01\x09', {'implicit': (1, 7)}), (b'\x87\x01\x09', {'explicit': 7}),
            (b'\x27\x03\x02\x01\x09', {'explicit': (2, 7)}),
            (b'\x67\x03\x02\x01\x09', {'explicit': (1, 6)}),
            (b'\xe7\x03\x02\x01\x09', {'explicit': 7}),
            (b'\xa4\x05\x63\x03\x02\x01\x09', {'explicit': ((1, 3), (2, 5))}),
            (b'\xa4\x05\x63\x03\x02\x01\x09', {'explicit': ((2, 3), (2, 4))}),
        ):
            result = observe(Integer.load, args=(wire,), kwargs=tagging,
                             consumers=(lambda v: v.native,), expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)
        wire = b'\x30\x08\x63\x03\x02\x01\x09\xc4\x01Z'
        for mismatch in (b'\x30\x08\xa3\x03\x02\x01\x09\xc4\x01Z', b'\x30\x08\x64\x03\x02\x01\x09\xc4\x01Z',
                         b'\x30\x08\x43\x03\x02\x01\x09\xc4\x01Z', b'\x30\x08\x63\x03\x02\x01\x09\x84\x01Z',
                         b'\x30\x08\x63\x03\x02\x01\x09\xc5\x01Z'):
            result = observe(TaggedRecord.load, args=(mismatch,), consumers=(lambda v: v.native,),
                             expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)
        # The field definition, not the supplied object, decides the tagging.
        for number, label in ((Integer(9), UTF8String('Z')),
                              (Integer(9, explicit=5), UTF8String('Z', implicit=6))):
            self.assertEqual(TaggedRecord({'number': number, 'label': label}).dump(), wire)
        assigned = TaggedRecord.load(wire)
        assigned.dump()
        assigned['number'] = Integer(10)
        assigned['label'] = UTF8String('Q')
        self.assertEqual(assigned.dump(), b'\x30\x08\x63\x03\x02\x01\x0a\xc4\x01Q')
        for value in (TaggedRecord({'number': 9, 'label': 'Z'}), TaggedRecord.load(wire)):
            self.assertEqual(value.native, {'number': 9, 'label': 'Z'})
            self.assertEqual(value.dump(), wire)
        self.assertEqual(TextOrNumber('number', 9, explicit=1).dump(), b'\xa1\x03\x02\x01\x09')
        result = observe(TextOrNumber, args=('number', 9), kwargs={'implicit': 1},
                         consumers=(lambda v: v.native, lambda v: v.dump()),
                         expected_exceptions=(ValueError,))
        self.assertIsInstance(result.error, ValueError)
        self.assertEqual(TextOrNumber.load(b'\xa1\x03\x02\x01\x09', explicit=1).native, 9)
        for wire, tagging in ((b'\x81\x01\x09', {'implicit': 1}),
                              (b'\xa2\x03\x02\x01\x09', {'explicit': 1}),
                              (b'\x61\x03\x02\x01\x09', {'explicit': 1})):
            result = observe(TextOrNumber.load, args=(wire,), kwargs=tagging,
                             consumers=(lambda v: v.native,), expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)

    def test_f03_t07(self):
        pair_wire = b'\x30\x06\x02\x01\x0b\x0c\x01K'
        expected = {'number': 11, 'label': 'K'}
        open_wire = b'\x30\x0c\x06\x02\x2a\x03' + pair_wire
        made = AssociatedOpenRecord({'kind': '1.2.3', 'payload': PairRecord(expected)})
        self.assertEqual(made.dump(), open_wire)
        associated = AssociatedOpenRecord.load(open_wire)
        self.assertEqual(associated['payload'].native, expected)
        self.assertEqual(associated['payload']['number'].native, 11)
        self.assertEqual(associated.dump(), open_wire)
        # Each embedded carrier is reached through its enclosing record.
        for cls, wire in (
            (EmbeddedOctets, b'\x30\x0e\x06\x02\x2a\x03\x04\x08' + pair_wire),
            (EmbeddedBits, b'\x30\x0f\x06\x02\x2a\x03\x03\x09\x00' + pair_wire),
        ):
            bound = cls.load(wire)
            self.assertEqual(bound['payload'].parsed.native, expected)
            self.assertEqual(bound['payload'].parsed['label'].native, 'K')
            self.assertEqual(bound.dump(), wire)
            made = cls({'kind': '1.2.3', 'payload': PairRecord(expected)})
            self.assertEqual(made['payload'].parsed.native, expected)
            self.assertEqual(made.dump(), wire)
        for cls, wire in (
            (OpenRecord, open_wire),
            (EmbeddedOctets, b'\x30\x0e\x06\x02\x2a\x09\x04\x08' + pair_wire),
            (EmbeddedBits, b'\x30\x0f\x06\x02\x2a\x09\x03\x09\x00' + pair_wire),
        ):
            value = cls.load(wire)
            payload = value['payload']
            self.assertEqual(value.dump(), wire)
            if cls is not OpenRecord:
                self.assertEqual(payload.native, pair_wire)
            self.assertEqual(payload.parse(PairRecord).native, expected)
            self.assertEqual(payload.parsed.native, expected)
            self.assertEqual(value.dump(), wire)
            # Fresh binding prevents an earlier parse from hiding bad specs.
            result = observe(cls.load, args=(wire,),
                             consumers=(lambda v: v['payload'].parse(Integer).native,),
                             expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)
            # A later incompatible definition is refused even after a
            # successful interpretation of the same carrier.
            result = observe(lambda: payload.parse(Integer).native,
                             expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)
            self.assertEqual(payload.parse(PairRecord)['number'].native, 11)
        for cls, wire in (
            (AssociatedOpenRecord, b'\x30\x07\x06\x02\x2a\x03\x02\x01\x0b'),
            (EmbeddedOctets, b'\x30\x09\x06\x02\x2a\x03\x04\x03\x02\x01\x0b'),
            (EmbeddedBits, b'\x30\x0a\x06\x02\x2a\x03\x03\x04\x00\x02\x01\x0b'),
        ):
            result = observe(cls.load, args=(wire,), consumers=(lambda v: v.native,),
                             expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)
        unknown = b'\x30\x07\x06\x02\x2a\x09\x02\x01\x7b'
        unbound = AssociatedOpenRecord.load(unknown)
        self.assertEqual(unbound['payload'].dump(), b'\x02\x01\x7b')
        self.assertEqual(unbound.dump(), unknown)

    def test_f03_t08(self):
        # DEFAULT TRUE is absent in DER even if explicitly supplied or encoded.
        self.assertEqual(PresenceRecord({'number': 7, 'enabled': True}).dump(),
                         b'\x30\x03\x02\x01\x07')
        # BER allows a long-form length and a non-FF true octet. INTEGER
        # contents remain minimal and BOOLEAN contents remain one octet.
        ber = b'\x30\x81\x06\x02\x01\x07\x01\x01\x01'
        value = PresenceRecord.load(ber)
        self.assertEqual(value.native['number'], 7)
        self.assertIs(value['enabled'].native, True)
        self.assertEqual(value.dump(), ber)
        self.assertEqual(value.dump(force=True), b'\x30\x03\x02\x01\x07')
        for cls, ber, der in (
            (UnorderedRecord, b'\x31\x06\x82\x01\x09\x80\x01Z',
             b'\x31\x06\x80\x01Z\x82\x01\x09'),
            (IntegerBag, b'\x31\x09\x02\x01\xff\x02\x01\x09\x02\x01\x09',
             b'\x31\x09\x02\x01\x09\x02\x01\x09\x02\x01\xff'),
        ):
            value = cls.load(ber)
            self.assertEqual(value.dump(), ber)
            # Materialize through the public view before SET canonicalization.
            value.native
            self.assertEqual(value.dump(force=True), der)

    def test_f03_t09(self):
        wire = b'\x30\x06\x02\x01\x09\x0c\x01R\x04\x03\x00\xffA\x02\x02\x00\x80'
        for value in (MixedConcat([PairRecord({'number': 9, 'label': 'R'}),
                                  OctetString(b'\x00\xffA'), Integer(128)]),
                      MixedConcat.load(wire, strict=True)):
            self.assertEqual(value[0].native, {'number': 9, 'label': 'R'})
            self.assertEqual(value[1].native, b'\x00\xffA')
            self.assertEqual(value[2].native, 128)
            self.assertEqual(value.dump(), wire)
        self.assertEqual(MixedConcat.load(wire + b'\x05\x00').dump(), wire)
        result = observe(MixedConcat.load, args=(wire + b'\x05\x00',),
                         kwargs={'strict': True}, consumers=(lambda v: v.dump(),),
                         expected_exceptions=(ValueError,))
        self.assertIsInstance(result.error, ValueError)

    def test_f03_t10(self):
        for number, octet in ((9, b'\x09'), (12, b'\x0c')):
            wire = b'\x30\x0a\xa2\x03\x02\x01' + octet + b'\x04\x03\x02\x01' + octet
            value = DiagnosticRecord.load(wire)
            self.assertEqual(value['payload'].parse(Integer).native, number)
            result = observe(value.debug)
            fields = diagnostic_fields(result.stdout)
            self.assertEqual(set(fields), {'count', 'payload'})
            count = [text for _, text in fields['count']]
            check_diagnostic_headers(count, (b'\xa2\x03', b'\x02\x01'))
            self.assertIn('context tag 2 (explicitly tagged)', count)
            self.assertIn('primitive universal 2', count)
            self.assertIn('Data: 0x' + octet.hex(), count)
            self.assertIn('Native: %d' % number, count)
            payload = fields['payload']
            self.assertIn('Header: 0x0403', [text for _, text in payload])
            self.assertIn('primitive universal tag 4', [text for _, text in payload])
            outer = [indent for indent, text in payload if text == 'Data: 0x0201' + octet.hex()]
            inner = [indent for indent, text in payload if text == 'Data: 0x' + octet.hex()]
            native = [indent for indent, text in payload if text == 'Native: %d' % number]
            self.assertTrue(outer)
            self.assertTrue(any(child > parent for child in inner for parent in outer))
            self.assertTrue(any(child > parent for child in native for parent in outer))
            self.assertIn('primitive universal tag 2', [text for _, text in payload])

    def test_f03_t11(self):
        # The unsupported semantic universal types and unmapped ENUMERATED are
        # outside this requirement; use the concrete supported scalar types.
        for cls, expected, wire in scalar_vectors():
            value = Asn1Value.load(wire)
            self.assertIsInstance(value, cls)
            self.assertEqual(value.native, expected)
            self.assertEqual(value.dump(), wire)
        for cls, tag, text, payload in text_vectors():
            wire = bytes((tag, len(payload))) + payload
            value = Asn1Value.load(wire)
            self.assertIsInstance(value, cls)
            self.assertEqual(value.native, text)
        wire = b'\x30\x10\x02\x01\x09\x30\x08\x0c\x01Z\x30\x03\x01\x01\xff\x04\x01Q'
        value = Asn1Value.load(wire)
        self.assertIsInstance(value, Sequence)
        self.assertEqual(value[0].native, 9)
        self.assertIsInstance(value[1], Sequence)
        self.assertEqual(value[1][0].native, 'Z')
        self.assertIsInstance(value[1][1], Sequence)
        self.assertIs(value[1][1][0].native, True)
        self.assertEqual(value[2].native, b'Q')
        for encoded_set in (b'\x31\x00', b'\x31\x03\x02\x01\x09'):
            generic_set = Asn1Value.load(encoded_set)
            self.assertIsInstance(generic_set, Set)
            self.assertEqual(generic_set.dump(), encoded_set)
        self.assertEqual(value.dump(), wire)
