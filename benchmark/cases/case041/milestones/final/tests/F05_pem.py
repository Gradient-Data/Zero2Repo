# feature: F05
"""Acceptance tests for PEM detection and binary transport."""

import unittest

from cobaltform.pem import armor, detect, unarmor

from _helpers import exhaust, observe, standard_tools
from F05_helpers import read_armored_block


class TestPEMTransport(unittest.TestCase):
    def test_f05_t01(self):
        cases = (
            (b'', False),
            (b'\x30\x03\x02\x01\xff\nplain text\n', False),
            (b'-----END DATA 1-----\n', False),
            (b'-----BEGIN DATA 1-----\nAA==\n-----END DATA 1-----\n', True),
            (b'notes\n---- BEGIN DATA 2 ----\n', True),
            (b'-----BEGIN DATA 1-----\n', True),
        )
        for source, expected in cases:
            self.assertIs(detect(source), expected, msg=('source=%r' % (source,),))
        for source in ('-----BEGIN DATA 1-----', None, 17):
            with self.assertRaises(TypeError, msg=('nonbinary=%r' % (source,),)):
                detect(source)

    def test_f05_t02(self):
        # Build input with an independent Base64 encoder, never pem.armor.
        # Distinct contents under a repeated identity expose sorting/deduplication;
        # the headerless middle block exposes header leakage across blocks.
        payloads = (b'\x00\xff\x80first', bytes(range(256)), b'last\x00\x01')
        encoded = [standard_tools().base64.b64encode(p) for p in payloads]
        blocks = (
            b'-----BEGIN DATA 7-----\nOrigin:   first source  \n'
            b'Comment: a:b\n\n' + encoded[0] + b'\n-----END DATA 7-----\n',
            b'---- BEGIN PUBLIC KEY ----\n' + encoded[1][:80] + b'\n'
            + encoded[1][80:] + b'\n---- END PUBLIC KEY ----\n',
            b'-----BEGIN DATA 7-----\nOrigin: final source\n\n'
            + encoded[2] + b'\n-----END DATA 7-----\n',
        )
        expected = (
            ('DATA 7', {'Origin': 'first source', 'Comment': 'a:b'}, payloads[0]),
            ('PUBLIC KEY', {}, payloads[1]),
            ('DATA 7', {'Origin': 'final source'}, payloads[2]),
        )
        for block, result in zip(blocks, expected):
            self.assertEqual(unarmor(block), result, msg=('identity=%r' % (result[0],), 'payload=%r' % (result[2],),))
        source = b'Human-readable preamble\n' + b'Between blocks\n'.join(blocks) + b'Trailer\n'
        self.assertEqual(unarmor(source), expected[0])
        all_blocks = observe(
            unarmor, args=(source,), kwargs={'multiple': True},
            consumers=(lambda value: exhaust(value, max_items=3),),
        )
        self.assertEqual(all_blocks.consumed[0], expected)

        malformed = (
            b'', b'ordinary text\n', b'-----END DATA 7-----\n',
            b'-----BEGIN DATA 7-----\n',
            b'---- BEGIN DATA 7 ----\nAA==\n',
        )
        for source in malformed + ('not binary', None, 17):
            error_type = ValueError if isinstance(source, bytes) else TypeError
            for multiple in (False, True):
                # Call and consumption share the capture, so either eager or
                # lazy implementations can signal the public failure.
                result = observe(
                    unarmor, args=(source,), kwargs={'multiple': multiple},
                    consumers=((lambda value: exhaust(value, max_items=3)),)
                    if multiple else (),
                    expected_exceptions=(error_type,),
                )
                self.assertIsInstance(result.error, error_type, msg=('source=%r' % (source,), 'multiple=%r' % (multiple,),))

    def test_f05_t03(self):
        # Empty input, both padding cases and a multi-line all-byte payload
        # exercise binary transport without fixing an encoder's line width.
        cases = (
            ('EMPTY DATA 0', b'', None),
            ('CERTIFICATE', b'\x00', {}),
            ('PUBLIC KEY', b'\xff\x00', None),
            ('ARCHIVE 27 DATA', bytes(range(256)) * 2 + b'\xff',
             {'Origin': '  archive writer  ', 'Comment': 'alpha:beta, gamma'}),
        )
        for identity, payload, headers in cases:
            if headers is None:
                encoded = armor(identity, payload)
            else:
                encoded = armor(identity, payload, headers=headers)
            expected = (identity, {k: v.strip() for k, v in (headers or {}).items()}, payload)
            self.assertEqual(read_armored_block(encoded), expected, msg=('identity=%r' % (identity,),))
            self.assertEqual(unarmor(encoded), expected, msg=('identity=%r' % (identity,),))

        for identity, payload in ((b'DATA', b'abc'), (None, b'abc'),
                                  ('DATA', 'abc'), ('DATA', None)):
            with self.assertRaises(TypeError, msg=('identity=%r' % (identity,), 'payload=%r' % (payload,),)):
                armor(identity, payload)
        for identity, headers in (
            ('DÁTÁ', None), ('DATA', {'Origín': 'source'}),
            ('DATA', {'Origin': 'sourcé'}),
        ):
            with self.assertRaises(UnicodeEncodeError, msg=('identity=%r' % (identity,), 'headers=%r' % (headers,),)):
                armor(identity, b'abc', headers=headers)
