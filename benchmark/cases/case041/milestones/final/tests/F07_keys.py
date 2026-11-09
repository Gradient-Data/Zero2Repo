# feature: F07
"""Key-document acceptance tests; no key generation or cryptographic validation."""
import unittest

from cobaltform.core import Null, UTF8String
from cobaltform.keys import (
    DSAParams, DSAPrivateKey, ECDomainParameters, ECPoint, ECPointBitString, ECPrivateKey,
    EncryptedPrivateKeyInfo, PrivateKeyInfo, PublicKeyInfo, RSAPrivateKey, RSAPublicKey,
)
from _helpers import observe, run_python, standard_tools
from F02_helpers import short_primitive
from F07_helpers import (
    KEY_IDENTITIES, BUILTIN_CURVES, key_sequence as seq, key_integer as integer,
    key_octets as octets, key_bits as bits, key_oid as oid,
    key_tagged as explicit, key_identifier as identifier,
    rsa_components, rsa_private_der, dsa_components, dsa_parameters_der,
    private_container_der as pkcs8, public_container_der as spki,
    explicit_domain, key_checked_documents, key_attribute_wire,
)


class TestKey(unittest.TestCase):
    def test_f07_t01(self):
        rsa = rsa_components()
        dsa = dsa_components()
        ec = {'version': 'ecPrivkeyVer1', 'private_key': 7,
              'parameters': ('named', 'secp256r1'), 'public_key': b'\x04\x03\x0a'}
        ec_wire = seq(integer(1), octets(b'\x00' * 31 + b'\x07'),
                      explicit(0, oid('1.2.840.10045.3.1.7')),
                      explicit(1, bits(b'\x04\x03\x0a')))
        multi = dict(rsa, version='multi', other_prime_infos=[
            {'prime': 47, 'exponent': 19, 'coefficient': 11}])
        public = {'modulus': 3233, 'public_exponent': 17}
        standalone = (
            (RSAPrivateKey, rsa, rsa_private_der(rsa), dict(rsa, other_prime_infos=None)),
            (RSAPrivateKey, multi, rsa_private_der(multi), multi),
            (RSAPublicKey, public, seq(integer(3233), integer(17)), public),
            (DSAPrivateKey, dsa, seq(*(integer(dsa[n]) for n in (
                'version', 'p', 'q', 'g', 'public_key', 'private_key'))), dsa),
            (ECPrivateKey, ec, ec_wire, dict(ec, parameters='secp256r1')),
        )
        for cls, fields, wire, native in standalone:
            for doc in key_checked_documents(self, cls, fields, wire):
                self.assertEqual(doc.native, native)
                for name, expected in native.items():
                    self.assertEqual(doc[name].native, expected)
                if cls is RSAPublicKey:
                    doc['public_exponent'] = 65537
                    self.assertEqual(doc.dump(), seq(integer(3233), integer(65537)))
                elif cls is RSAPrivateKey:
                    doc['coefficient'] = 39
                    self.assertEqual(doc.dump(), rsa_private_der(dict(fields, coefficient=39)))
                elif cls is DSAPrivateKey:
                    doc['private_key'] = 9
                    self.assertEqual(doc.dump(), seq(*(integer(9 if n == 'private_key' else dsa[n])
                        for n in ('version', 'p', 'q', 'g', 'public_key', 'private_key'))))
                else:
                    doc['public_key'] = b'\x04\x05\x07'
                    self.assertEqual(doc.dump(), seq(integer(1), octets(b'\x00' * 31 + b'\x07'),
                        explicit(0, oid('1.2.840.10045.3.1.7')),
                        explicit(1, bits(b'\x04\x05\x07'))))

        # RFC 4055 restrictions are actual fields, including non-default values.
        sha256 = identifier('2.16.840.1.101.3.4.2.1', b'\x05\x00')
        restrictions = {'hash_algorithm': {'algorithm': 'sha256'},
                        'mask_gen_algorithm': {'algorithm': 'mgf1',
                            'parameters': {'algorithm': 'sha256'}}, 'salt_length': 37}
        restriction_wire = seq(explicit(0, sha256),
            explicit(1, identifier('1.2.840.113549.1.1.8', sha256)), explicit(2, integer(37)))
        attributes = [{'type': '1.2.840.113549.1.9.20',
                       'values': [UTF8String('key label')]}]
        # The PKCS#8 attributes field is a context-specific implicit SET OF.
        attribute_wire = key_attribute_wire('key label')
        for algorithm, params, encoded_params, payload, encoded_payload, expected_payload in (
            ('rsa', Null(), b'\x05\x00', rsa, rsa_private_der(rsa), dict(rsa, other_prime_infos=None)),
            ('rsassa_pss', restrictions, restriction_wire, rsa, rsa_private_der(rsa), dict(rsa, other_prime_infos=None)),
            ('dsa', {n: dsa[n] for n in ('p', 'q', 'g')}, dsa_parameters_der(dsa),
             7, integer(7), 7),
            ('ec', ('named', 'secp256r1'), oid('1.2.840.10045.3.1.7'),
             ec, ec_wire, dict(ec, parameters='secp256r1')),
        ):
            fields = {'version': 0, 'private_key_algorithm': {'algorithm': algorithm,
                'parameters': params}, 'private_key': payload, 'attributes': attributes}
            wire = pkcs8(algorithm, encoded_params, encoded_payload, attribute_wire)
            for doc in key_checked_documents(self, PrivateKeyInfo, fields, wire):
                self.assertEqual(doc.algorithm, algorithm)
                self.assertEqual(doc['private_key_algorithm']['parameters'].dump(), encoded_params)
                self.assertEqual(doc['private_key'].parsed.native, expected_payload)
                self.assertEqual(doc['attributes'][0]['type'].dotted, '1.2.840.113549.1.9.20')
                self.assertEqual(doc['attributes'][0]['values'][0].native, 'key label')
                doc['attributes'][0]['values'][0] = UTF8String('renamed')
                self.assertEqual(doc.dump(), pkcs8(algorithm, encoded_params, encoded_payload,
                                                   key_attribute_wire('renamed')))
        for algorithm, size in (('x25519', 32), ('x448', 56), ('ed25519', 32), ('ed448', 57)):
            payload = bytes(range(size))
            private_wire = pkcs8(algorithm, None, octets(payload))
            public_wire = spki(algorithm, None, payload)
            for doc in key_checked_documents(self, PrivateKeyInfo,
                    {'version': 0, 'private_key_algorithm': {'algorithm': algorithm},
                     'private_key': payload}, private_wire):
                self.assertEqual(doc.algorithm, algorithm)
                self.assertIsNone(doc['private_key_algorithm']['parameters'].native)
                self.assertEqual(doc['private_key'].parsed.native, payload)
                doc['private_key'] = payload[::-1]
                self.assertEqual(doc.dump(), pkcs8(algorithm, None, octets(payload[::-1])))
            for doc in key_checked_documents(self, PublicKeyInfo,
                    {'algorithm': {'algorithm': algorithm}, 'public_key': payload}, public_wire):
                self.assertEqual(doc.algorithm, algorithm)
                self.assertEqual(doc['public_key'].native, payload)
                self.assertIsNone(doc['algorithm']['parameters'].native)
                doc['public_key'] = payload[::-1]
                self.assertEqual(doc.dump(), spki(algorithm, None, payload[::-1]))
        public_variants = (
            ('rsa', Null(), b'\x05\x00', public, seq(integer(3233), integer(17)), public),
            ('rsassa_pss', restrictions, restriction_wire, public, seq(integer(3233), integer(17)), public),
            ('rsaes_oaep', {'hash_algorithm': {'algorithm': 'sha256'}}, seq(explicit(0, sha256)),
             public, seq(integer(3233), integer(17)), public),
            ('dsa', {n: dsa[n] for n in ('p', 'q', 'g')}, dsa_parameters_der(dsa), 615, integer(615), 615),
            ('ec', ('named', 'secp256r1'), oid('1.2.840.10045.3.1.7'),
             b'\x04\x03\x0a', b'\x04\x03\x0a', b'\x04\x03\x0a'),
            ('dh', {'p': 23, 'g': 5, 'q': 11}, seq(integer(23), integer(5), integer(11)),
             8, integer(8), 8),
        )
        for algorithm, params, encoded_params, payload, encoded_payload, expected in public_variants:
            wire = spki(algorithm, encoded_params, encoded_payload)
            for doc in key_checked_documents(self, PublicKeyInfo,
                    {'algorithm': {'algorithm': algorithm, 'parameters': params},
                     'public_key': payload}, wire):
                self.assertEqual(doc.algorithm, algorithm)
                self.assertEqual(doc['algorithm']['parameters'].dump(), encoded_params)
                actual = doc['public_key'].native if algorithm == 'ec' else doc['public_key'].parsed.native
                self.assertEqual(actual, expected)
        # Encrypted containers retain ciphertext; they do not decrypt it.
        encrypted = {'encryption_algorithm': {'algorithm': 'aes256_cbc',
                     'parameters': b'0123456789abcdef'}, 'encrypted_data': b'\x00\xffciphertext'}
        encryption = identifier('2.16.840.1.101.3.4.1.42', octets(b'0123456789abcdef'))
        for doc in key_checked_documents(self, EncryptedPrivateKeyInfo, encrypted,
                                        seq(encryption, octets(b'\x00\xffciphertext'))):
            self.assertEqual(doc.native, encrypted)
            doc['encrypted_data'] = b'new ciphertext'
            self.assertEqual(doc.dump(), seq(encryption, octets(b'new ciphertext')))

    def test_f07_t02(self):
        rsa, dsa = rsa_components(), dsa_components()
        rsa_wire = rsa_private_der(rsa)
        dsa_wire = seq(*(integer(dsa[n]) for n in (
            'version', 'p', 'q', 'g', 'public_key', 'private_key')))
        ec_wire = seq(integer(1), octets(b'\x00' * 31 + b'\x09'),
                      explicit(0, oid('1.3.132.0.10')), explicit(1, bits(b'\x04\x03\x0a')))
        stripped_ec = seq(integer(1), octets(b'\x00' * 31 + b'\x09'),
                          explicit(1, bits(b'\x04\x03\x0a')))
        for algorithm, cls, wire, params, wrapped_payload in (
            ('rsa', RSAPrivateKey, rsa_wire, b'\x05\x00', rsa_wire),
            ('dsa', DSAPrivateKey, dsa_wire, dsa_parameters_der(dsa), integer(7)),
            ('ec', ECPrivateKey, ec_wire, oid('1.3.132.0.10'), stripped_ec),
        ):
            for value in (wire, cls.load(wire)):
                wrapped = PrivateKeyInfo.wrap(value, algorithm)
                # Wrapping does not change the supplied standalone key.
                self.assertEqual(value if isinstance(value, bytes) else value.dump(), wire)
                self.assertEqual(wrapped.algorithm, algorithm)
                self.assertEqual(wrapped['private_key_algorithm']['parameters'].dump(), params)
                # SEC1 permits the matching domain to remain in the inner key.
                # Both encodings retain every supplied component and the
                # PKCS#8 algorithm parameters; neither changes the scalar width.
                payloads = (wrapped_payload, wire) if algorithm == 'ec' else (wrapped_payload,)
                self.assertIn(wrapped['private_key'].parsed.dump(), payloads)
                self.assertIn(wrapped.dump(), tuple(pkcs8(algorithm, params, p) for p in payloads))
        public_wire = seq(integer(3233), integer(17))
        for value in (public_wire, RSAPublicKey.load(public_wire)):
            wrapped = PublicKeyInfo.wrap(value, 'rsa')
            self.assertEqual(wrapped.algorithm, 'rsa')
            self.assertEqual(wrapped['public_key'].parsed.native,
                             {'modulus': 3233, 'public_exponent': 17})
            self.assertEqual(wrapped.dump(), spki('rsa', b'\x05\x00', public_wire))

    def test_f07_t03(self):
        domains = [('named', 'secp256r1'), ('specified', explicit_domain(257)), ('implicit_ca', None)]
        for declaration in domains:
            domain = ECDomainParameters(declaration)
            self.assertEqual(domain.name, declaration[0])
            self.assertEqual(domain.chosen.native, declaration[1])
            for cls, fields in (
                (PrivateKeyInfo, {'version': 0, 'private_key_algorithm': {
                    'algorithm': 'ec', 'parameters': declaration},
                    'private_key': {'version': 1, 'private_key': 7}}),
                (PublicKeyInfo, {'algorithm': {'algorithm': 'ec', 'parameters': declaration},
                                     'public_key': b'\x04\x03\x0a'}),
            ):
                doc = cls(fields)
                self.assertEqual(doc.curve, declaration)
                self.assertEqual(cls.load(doc.dump()).curve, declaration)
        # Exact small boundaries and large orders within the supported precision
        # envelope use an independent integer oracle, never a product-derived width.
        boundary = 1 << 256
        distance = boundary // 10**12 + 1
        orders = (2, 255, 256, 257, 65536, 65537,
                  (1 << 32) - 1, 1 << 32, (1 << 32) + 1,
                  boundary - distance, boundary + distance,
                  (1 << 383) + 12345, (1 << 1023) + 1)
        for order in orders:
            width = ((order - 1).bit_length() + 7) // 8
            domain = ECDomainParameters(('specified', explicit_domain(order)))
            self.assertEqual(domain.key_size, width)
        self.assertEqual(ECDomainParameters(('named', 'secp256r1')).key_size, 32)
        for declaration in (('named', '1.3.6.1.4.1.55555.700'), ('implicit_ca', None)):
            result = observe(lambda: ECDomainParameters(declaration).key_size,
                             expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)
        for doc in (PrivateKeyInfo.wrap(RSAPrivateKey(rsa_components()), 'rsa'),
                    PublicKeyInfo.wrap(RSAPublicKey({'modulus': 3233, 'public_exponent': 17}), 'rsa')):
            result = observe(lambda: doc.curve, expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)

    def test_f07_t04(self):
        # A fresh interpreter isolates registration without reading registries.
        result = run_python('''
from cobaltform.keys import ECDomainParameters, ECPrivateKey, NamedCurve, PrivateKeyInfo
for name, identity, width in (("acceptance_curve", "1.3.6.1.4.1.55555.707", 19),
                               ("secp256r1", "1.2.840.10045.3.1.7", 35)):
    NamedCurve.register(name, identity, width)
    for spelling in (name, identity):
        named = NamedCurve(spelling)
        assert named.native == name
        assert named.dotted == identity
        domain = ECDomainParameters(("named", spelling))
        assert domain.key_size == width
        standalone = ECPrivateKey({"version": 1, "private_key": 257, "parameters": domain})
        container = PrivateKeyInfo({"version": 0,
            "private_key_algorithm": {"algorithm": "ec", "parameters": ("named", spelling)},
            "private_key": {"version": 1, "private_key": 257}})
        for key in (standalone, container["private_key"].parsed):
            assert key["private_key"].native == 257
            assert key["private_key"].contents == b"\\x00" * (width - 2) + b"\\x01\\x01"
            assert key["private_key"].dump() == bytes((4, width)) + b"\\x00" * (width - 2) + b"\\x01\\x01"
        assert standalone["parameters"].chosen.dotted == identity
        assert container["private_key_algorithm"]["parameters"].chosen.dotted == identity
        assert ECPrivateKey.load(standalone.dump())["private_key"].contents == b"\\x00" * (width - 2) + b"\\x01\\x01"
        assert PrivateKeyInfo.load(container.dump(force=True))["private_key"].parsed["private_key"].contents == b"\\x00" * (width - 2) + b"\\x01\\x01"
''')
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_f07_t05(self):
        scenarios = [(name, identity, width, 257 + index)
                     for index, (name, identity, width) in enumerate(BUILTIN_CURVES)]
        # Zero and a high-bit full-width scalar add unsigned boundaries that
        # the leading-zero identity rows cannot establish; pair rather than
        # multiplying these scalar boundaries across every curve.
        scenarios += [('secp256r1', '1.2.840.10045.3.1.7', 32, 0),
                      ('secp112r1', '1.3.132.0.6', 14, (1 << 112) - 1)]
        for name, identity, width, scalar in scenarios:
            # Each curve must work by both public spellings. Scalar values vary
            # across rows, retaining leading zeros without testing key validity.
            expected = scalar.to_bytes(width, 'big')
            for spelling in (name, identity):
                domain = ECDomainParameters(('named', spelling))
                self.assertEqual(domain.chosen.native, name, msg=('curve=%r' % (name,), 'spelling=%r' % (spelling,),))
                self.assertEqual(domain.chosen.dotted, identity, msg=('curve=%r' % (name,), 'spelling=%r' % (spelling,),))
                self.assertEqual(domain.key_size, width, msg=('curve=%r' % (name,), 'spelling=%r' % (spelling,),))
                standalone = ECPrivateKey({'version': 1, 'private_key': scalar,
                                                'parameters': domain})
                container = PrivateKeyInfo({'version': 0,
                    'private_key_algorithm': {'algorithm': 'ec', 'parameters': ('named', spelling)},
                    'private_key': {'version': 1, 'private_key': scalar}})
                self.assertEqual(standalone['parameters'].chosen.dotted, identity, msg=('curve=%r' % (name,), 'spelling=%r' % (spelling,),))
                self.assertEqual(container['private_key_algorithm']['parameters'].chosen.dotted, identity, msg=('curve=%r' % (name,), 'spelling=%r' % (spelling,),))
                inner_wire = seq(integer(1), octets(expected))
                self.assertEqual(standalone.dump(), seq(integer(1), octets(expected),
                                                       explicit(0, oid(identity))), msg=('curve=%r' % (name,), 'spelling=%r' % (spelling,),))
                self.assertEqual(container.dump(force=True), pkcs8('ec', oid(identity), inner_wire), msg=('curve=%r' % (name,), 'spelling=%r' % (spelling,),))
                for key in (standalone, container['private_key'].parsed):
                    self.assertEqual(key['private_key'].native, scalar, msg=('curve=%r' % (name,), 'spelling=%r' % (spelling,),))
                    self.assertEqual(key['private_key'].contents, expected, msg=('curve=%r' % (name,), 'spelling=%r' % (spelling,),))
                    self.assertEqual(key['private_key'].dump(), short_primitive(4, expected), msg=('curve=%r' % (name,), 'spelling=%r' % (spelling,),))

    def test_f07_t06(self):
        for cls in (ECPoint, ECPointBitString):
            for payload, coords in ((b'\x04\x00\x01\x80\xff', (1, 33023)),
                                    (b'\x04\x12\x34\xab\xcd', (4660, 43981))):
                self.assertEqual(cls(payload).to_coords(), coords)
            for payload in (b'\x02\x12\x34', b'\x03\x12\x34', b'\x05\x12\x34'):
                result = observe(lambda: cls(payload).to_coords(), expected_exceptions=(ValueError,))
                self.assertIsInstance(result.error, ValueError)

    def test_f07_t07(self):
        params = {'p': (1 << 1030) + 12345, 'q': (1 << 159) + 19, 'g': 7}
        # Non-byte-aligned primes distinguish byte rounding from bit length;
        # different public integers distinguish the domain prime from the key.
        scenarios = [
            ('rsa', b'\x05\x00', seq(integer((1 << 1028) + 123), integer(65537)), 1032, 129),
            # One bit past a byte boundary still rounds up to the next byte.
            ('rsa', b'\x05\x00', seq(integer((1 << 1024) + (1 << 1000)), integer(65537)), 1032, 129),
            ('dsa', dsa_parameters_der(params), integer(615), 1032, 129),
            ('ec', oid('1.2.840.10045.3.1.7'), b'\x04' + bytes(range(64)), 256, 32),
            ('ec', oid('1.3.132.0.35'), b'\x04' + bytes(range(132)), 528, 66),
        ]
        for algorithm, parameters, payload, bit_size, byte_size in scenarios:
            wire = spki(algorithm, parameters, payload)
            doc = PublicKeyInfo.load(wire)
            self.assertEqual(doc.algorithm, algorithm)
            self.assertEqual(doc.bit_size, bit_size)
            self.assertEqual(doc.byte_size, byte_size)
            self.assertEqual(doc.sha1, standard_tools().hashlib.sha1(payload).digest())
            self.assertEqual(doc.sha256, standard_tools().hashlib.sha256(payload).digest())
        # The digest promise also covers opaque RFC 8410 public-key payloads.
        for algorithm in ('ed25519', 'ed448', 'x25519', 'x448'):
            payload = b'\xff\x00\x30\x80' + algorithm.encode('ascii')
            doc = PublicKeyInfo.load(spki(algorithm, None, payload))
            self.assertEqual(doc.sha1, standard_tools().hashlib.sha1(payload).digest())
            self.assertEqual(doc.sha256, standard_tools().hashlib.sha256(payload).digest())

    def test_f07_t08(self):
        for modulus, bit_size, byte_size in (((1 << 1028) + 123, 1032, 129),
                                            ((1 << 2047) + 65537, 2048, 256)):
            doc = PrivateKeyInfo.load(pkcs8('rsa', b'\x05\x00', rsa_private_der(rsa_components(modulus))))
            self.assertEqual(doc.bit_size, bit_size)
            self.assertEqual(doc.byte_size, byte_size)
        for subgroup_bits, family in ((160, 'sha1'), (224, 'sha2'), (256, 'sha2')):
            for q in ((1 << (subgroup_bits - 1)) + 19, (1 << subgroup_bits) - 1):
                fields = {'p': (1 << 1030) + 12345, 'q': q, 'g': 7}
                parameters = dsa_parameters_der(fields)
                self.assertEqual(DSAParams.load(parameters).q_byte_size, subgroup_bits // 8)
                for doc in (PrivateKeyInfo.load(pkcs8('dsa', parameters, integer(7))),
                            PublicKeyInfo.load(spki('dsa', parameters, integer(615)))):
                    self.assertEqual(doc.hash_algo, family)
                    self.assertEqual(doc.bit_size, 1032)
                    self.assertEqual(doc.byte_size, 129)
        for q, width in ((127, 1), (128, 1), (255, 1), (256, 2), (65537, 3)):
            self.assertEqual(DSAParams({'p': 809, 'q': q, 'g': 256}).q_byte_size, width)
        missing = PublicKeyInfo.load(spki('dsa', None, integer(615)))
        self.assertIsNone(missing.hash_algo)
        for doc in (PrivateKeyInfo.wrap(RSAPrivateKey(rsa_components()), 'rsa'),
                    PublicKeyInfo.wrap(RSAPublicKey({'modulus': 3233, 'public_exponent': 17}), 'rsa')):
            result = observe(lambda: doc.hash_algo, expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)
