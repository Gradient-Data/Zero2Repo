# feature: F06
"""Acceptance tests for algorithm descriptions, not cryptographic execution."""
import unittest

from cobaltform.algos import (
    AlgorithmIdentifier, DSASignature, DigestAlgorithm, EncryptionAlgorithm, HmacAlgorithm,
    KdfAlgorithm, KeyExchangeAlgorithm, Pkcs5MacAlgorithm, SignedDigestAlgorithm,
)
from cobaltform.core import Integer, Null, OctetString
from _helpers import observe
from F06_helpers import (
    DIGEST_IDENTITIES, HMAC_IDENTITIES, LEGACY_PASSWORD_IDENTITIES,
    signature_identities, checked_algorithm_descriptions, pbkdf2_description,
    algo_der_sequence as seq, algo_der_integer as integer,
    algo_der_octets as octets, algo_der_identifier as identifier,
    algo_der_explicit as explicit,
)


class TestAlgorithm(unittest.TestCase):
    def test_f06_t01(self):
        for cls, identities in ((DigestAlgorithm, DIGEST_IDENTITIES),
                                (HmacAlgorithm, HMAC_IDENTITIES)):
            for name, oid in identities:
                if name.endswith('_len'):
                    parameter, encoded = Integer(512), integer(512)
                else:
                    parameter, encoded = Null(), b'\x05\x00'
                for value in checked_algorithm_descriptions(
                        self, cls, name, oid, parameter, encoded):
                    self.assertEqual(value['parameters'].native, parameter.native, msg=('type=%r' % (cls.__name__,), 'algorithm=%r' % (name,),))
        # Unknown identifiers remain usable, with open values intact.
        for cls in (AlgorithmIdentifier, DigestAlgorithm, HmacAlgorithm):
            for parameter, encoded in ((Integer(729), integer(729)),
                                       (OctetString(b'opaque\x00'), octets(b'opaque\x00'))):
                for value in checked_algorithm_descriptions(
                        self, cls, '1.3.6.1.4.1.55555.19', '1.3.6.1.4.1.55555.19',
                        parameter, encoded):
                    self.assertEqual(value['parameters'].native, parameter.native)
                    value['parameters'] = Integer(811)
                    self.assertEqual(value['parameters'].native, 811)
                    self.assertEqual(value.dump(), identifier('1.3.6.1.4.1.55555.19', integer(811)))
        value = DigestAlgorithm({'algorithm': 'shake128_len', 'parameters': Integer(256)})
        value['algorithm'] = 'shake256_len'
        value['parameters'] = Integer(1024)
        self.assertEqual(value.native, {'algorithm': 'shake256_len', 'parameters': 1024})
        self.assertEqual(value.dump(), identifier('2.16.840.1.101.3.4.2.18', integer(1024)))

    def test_f06_t02(self):
        for name, oid, family, digest in signature_identities():
            for value in checked_algorithm_descriptions(
                    self, SignedDigestAlgorithm, name, oid, Null(), b'\x05\x00'):
                self.assertEqual(value.signature_algo, family, msg=('algorithm=%r' % (name,),))
                self.assertEqual(value.hash_algo, digest, msg=('algorithm=%r' % (name,),))
                self.assertEqual(value.cms_hash_algo, digest, msg=('algorithm=%r' % (name,),))
        for name, oid, cms in (
                ('rsassa_pkcs1v15', '1.2.840.113549.1.1.1', None),
                ('dsa', '1.2.840.10040.4.1', None),
                ('ecdsa', '1.2.840.10045.4', None),
                ('ed25519', '1.3.101.112', 'sha512'),
                ('ed448', '1.3.101.113', 'shake256')):
            for value in checked_algorithm_descriptions(
                    self, SignedDigestAlgorithm, name, oid, Null(), b'\x05\x00'):
                self.assertEqual(value.signature_algo, name)
                result = observe(lambda: value.hash_algo, expected_exceptions=(ValueError,))
                self.assertIsInstance(result.error, ValueError)
                if cms is None:
                    result = observe(lambda: value.cms_hash_algo, expected_exceptions=(ValueError,))
                    self.assertIsInstance(result.error, ValueError)
                else:
                    self.assertEqual(value.cms_hash_algo, cms)
        for digest, oid in (('sha256', '2.16.840.1.101.3.4.2.1'),
                             ('sha384', '2.16.840.1.101.3.4.2.2')):
            params = {'hash_algorithm': {'algorithm': digest}}
            encoded = seq(explicit(0, identifier(oid, b'\x05\x00')))
            for value in checked_algorithm_descriptions(self, SignedDigestAlgorithm,
                    'rsassa_pss', '1.2.840.113549.1.1.10', params, encoded):
                self.assertEqual(value.signature_algo, 'rsassa_pss')
                self.assertEqual(value.hash_algo, digest)
                self.assertEqual(value.cms_hash_algo, digest)

    def test_f06_t03(self):
        sha256 = identifier('2.16.840.1.101.3.4.2.1', b'\x05\x00')
        sha384 = identifier('2.16.840.1.101.3.4.2.2', b'\x05\x00')
        mgf = identifier('1.2.840.113549.1.1.8', sha384)
        common = {'hash_algorithm': {'algorithm': 'sha256'},
                  'mask_gen_algorithm': {'algorithm': 'mgf1', 'parameters': {'algorithm': 'sha384'}}}
        for cls, name, oid, extra, encoded_extra in (
            (SignedDigestAlgorithm, 'rsassa_pss', '1.2.840.113549.1.1.10',
             {'salt_length': 37, 'trailer_field': 'trailer_field_bc'}, explicit(2, integer(37))),
            (EncryptionAlgorithm, 'rsaes_oaep', '1.2.840.113549.1.1.7',
             {'p_source_algorithm': {'algorithm': 'p_specified', 'parameters': b'label\x00'}},
             explicit(2, identifier('1.2.840.113549.1.1.9', octets(b'label\x00')))),
        ):
            encoded = seq(explicit(0, sha256), explicit(1, mgf), encoded_extra)
            for value in checked_algorithm_descriptions(self, cls, name, oid,
                                                        dict(common, **extra), encoded):
                params = value['parameters']
                self.assertEqual(params['hash_algorithm']['algorithm'].native, 'sha256')
                self.assertEqual(params['mask_gen_algorithm']['algorithm'].native, 'mgf1')
                self.assertEqual(params['mask_gen_algorithm']['parameters']['algorithm'].native, 'sha384')
                if name == 'rsassa_pss':
                    self.assertEqual(params['salt_length'].native, 37)
                    self.assertEqual(params['trailer_field'].native, 'trailer_field_bc')
                else:
                    self.assertEqual(params['p_source_algorithm']['algorithm'].native, 'p_specified')
                    self.assertEqual(params['p_source_algorithm']['parameters'].native, b'label\x00')
            defaults = dict(hash_algorithm={'algorithm': 'sha1'}, mask_gen_algorithm={
                'algorithm': 'mgf1', 'parameters': {'algorithm': 'sha1'}})
            if name == 'rsassa_pss':
                defaults.update(salt_length=20, trailer_field='trailer_field_bc')
            else:
                defaults['p_source_algorithm'] = {'algorithm': 'p_specified', 'parameters': b''}
            # A supplied empty SEQUENCE is distinct from missing parameters.
            for value in checked_algorithm_descriptions(self, cls, name, oid, defaults, seq()):
                params = value['parameters']
                self.assertEqual(params['hash_algorithm']['algorithm'].native, 'sha1')
                self.assertEqual(params['mask_gen_algorithm']['algorithm'].native, 'mgf1')
                self.assertEqual(params['mask_gen_algorithm']['parameters']['algorithm'].native, 'sha1')
                if name == 'rsassa_pss':
                    self.assertEqual(params['salt_length'].native, 20)
                    self.assertEqual(params['trailer_field'].native, 'trailer_field_bc')
                else:
                    self.assertEqual(params['p_source_algorithm']['algorithm'].native, 'p_specified')
                    self.assertEqual(params['p_source_algorithm']['parameters'].native, b'')

    def test_f06_t04(self):
        rows = [(DigestAlgorithm, name, oid) for name, oid in DIGEST_IDENTITIES
                if name in ('sha1', 'sha224', 'sha256', 'sha384', 'sha512')]
        rows += [(SignedDigestAlgorithm, name, oid)
                 for name, oid, _, _ in signature_identities()
                 if name in ('sha224_rsa', 'sha256_rsa', 'sha384_rsa', 'sha512_rsa')]
        rows += [(SignedDigestAlgorithm, 'rsassa_pkcs1v15', '1.2.840.113549.1.1.1'),
                 (EncryptionAlgorithm, 'rsaes_pkcs1v15', '1.2.840.113549.1.1.1')]
        for cls, name, oid in rows:
            # Both creation by mapping and by assigning the identifier field
            # of a description created without parameters.
            assigned = cls({'algorithm': '1.3.6.1.4.1.55555.19'})
            assigned['algorithm'] = name
            for value in (cls({'algorithm': name}), assigned):
                self.assertEqual(value['parameters'].dump(), b'\x05\x00')
                self.assertIsNone(value['parameters'].native)
                self.assertEqual(value.dump(), identifier(oid, b'\x05\x00'))

    def test_f06_t05(self):
        iv8, iv16 = b'\x00one-IV!', bytes(range(16))
        for name, oid, cipher, size, key in (
                ('des', '1.3.14.3.2.7', 'des', 8, 8),
                ('tripledes_3key', '1.2.840.113549.3.7', 'tripledes', 8, 24)):
            for value in checked_algorithm_descriptions(self, EncryptionAlgorithm,
                    name, oid, iv8, octets(iv8)):
                self.assertEqual(value['parameters'].native, iv8)
                self.assertEqual(value.encryption_cipher, cipher)
                self.assertEqual(value.encryption_mode, 'cbc')
                self.assertEqual(value.encryption_block_size, size)
                self.assertEqual(value.key_length, key)
                self.assertEqual(value.encryption_iv, iv8)
        for version, key in ((160, 5), (120, 8), (58, 16)):
            params = {'rc2_parameter_version': version, 'iv': iv8}
            for value in checked_algorithm_descriptions(self, EncryptionAlgorithm,
                    'rc2', '1.2.840.113549.3.2', params, seq(integer(version), octets(iv8))):
                self.assertEqual(value['parameters'].native, params)
                self.assertEqual(value.encryption_cipher, 'rc2')
                self.assertEqual(value.encryption_mode, 'cbc')
                self.assertEqual(value.encryption_block_size, 8)
                self.assertEqual(value.key_length, key)
                self.assertEqual(value.encryption_iv, iv8)
        for bits, rounds, iv in ((64, 16, iv8), (128, 42, iv16)):
            params = {'version': 'v1-0', 'rounds': rounds, 'block_size_in_bits': bits, 'iv': iv}
            for value in checked_algorithm_descriptions(self, EncryptionAlgorithm,
                    'rc5', '1.2.840.113549.3.9', params,
                    seq(integer(16), integer(rounds), integer(bits), octets(iv))):
                self.assertEqual(value['parameters'].native, params)
                self.assertEqual(value.encryption_cipher, 'rc5')
                self.assertEqual(value.encryption_mode, 'cbc')
                self.assertEqual(value.encryption_block_size, bits // 8)
                self.assertEqual(value.encryption_iv, iv)
        # AES size and mode jointly select the identity; cover each listed member.
        for bits, key, offset in ((128, 16, 0), (192, 24, 20), (256, 32, 40)):
            for number, mode in enumerate(('ecb', 'cbc', 'ofb', 'cfb', 'wrap', 'gcm', 'ccm', 'wrap_pad'), 1):
                name = 'aes%d_%s' % (bits, mode)
                oid = '2.16.840.1.101.3.4.1.%d' % (offset + number)
                if mode == 'ccm':
                    params = {'aes_nonce': b'nonce-123456', 'aes_icvlen': 12}
                    encoded = seq(octets(b'nonce-123456'), integer(12))
                else:
                    # Non-structured modes deliberately receive an open value.
                    params = iv16 if mode in ('cbc', 'ofb') else OctetString(iv16)
                    encoded = octets(iv16)
                for value in checked_algorithm_descriptions(self, EncryptionAlgorithm,
                                                            name, oid, params, encoded):
                    self.assertEqual(value.encryption_cipher, 'aes', msg=('algorithm=%r' % (name,),))
                    self.assertEqual(value.encryption_mode, mode, msg=('algorithm=%r' % (name,),))
                    self.assertEqual(value.encryption_block_size, 16, msg=('algorithm=%r' % (name,),))
                    self.assertEqual(value.key_length, key, msg=('algorithm=%r' % (name,),))
                    self.assertEqual(value['parameters'].native, params if mode == 'ccm' else iv16, msg=('algorithm=%r' % (name,),))
                    if mode in ('cbc', 'ofb'):
                        self.assertEqual(value.encryption_iv, iv16, msg=('algorithm=%r' % (name,),))
        for name, oid in (('rc4', '1.2.840.113549.3.4'),
                          ('rsaes_pkcs1v15', '1.2.840.113549.1.1.1')):
            for value in checked_algorithm_descriptions(self, EncryptionAlgorithm,
                    name, oid, Null(), b'\x05\x00'):
                self.assertIsNone(value['parameters'].native)
        # RSA-OAEP structured parameters are measured in T03.

    def test_f06_t06(self):
        for salt, iterations, key, prf in (
                (b'salt-one', 4097, None, None),
                (b'\x00salt-two', 1337, 28, ('sha256', '1.2.840.113549.2.9'))):
            params, encoded = pbkdf2_description(salt, iterations, key, prf)
            for value in checked_algorithm_descriptions(self, KdfAlgorithm,
                    'pbkdf2', '1.2.840.113549.1.5.12', params, encoded):
                bound = value['parameters']
                self.assertEqual(bound['salt'].name, 'specified')
                self.assertEqual(bound['salt'].native, salt)
                self.assertEqual(bound['iteration_count'].native, iterations)
                self.assertEqual(bound['key_length'].native, key)
                self.assertEqual(bound['prf']['algorithm'].native, 'sha1' if prf is None else prf[0])
            # PBMAC1 binds both derivation and authentication descriptions.
            mac_params = {'key_derivation_func': {'algorithm': 'pbkdf2', 'parameters': params},
                          'message_auth_scheme': {'algorithm': 'sha3_256'}}
            mac_wire = seq(identifier('1.2.840.113549.1.5.12', encoded),
                           identifier('2.16.840.1.101.3.4.2.14'))
            for value in checked_algorithm_descriptions(self, Pkcs5MacAlgorithm,
                    'pbmac1', '1.2.840.113549.1.5.14', mac_params, mac_wire):
                bound = value['parameters']
                self.assertEqual(bound['key_derivation_func']['algorithm'].native, 'pbkdf2')
                self.assertEqual(bound['key_derivation_func']['parameters']['salt'].native, salt)
                self.assertEqual(bound['key_derivation_func']['parameters']['iteration_count'].native, iterations)
                self.assertEqual(bound['key_derivation_func']['parameters']['key_length'].native, key)
                self.assertEqual(bound['key_derivation_func']['parameters']['prf']['algorithm'].native,
                                 'sha1' if prf is None else prf[0])
                self.assertEqual(bound['message_auth_scheme']['algorithm'].native, 'sha3_256')
        for key in (None, 24):
            params = {'salt': b'scrypt-salt', 'cost_parameter': 16384,
                      'block_size': 8, 'parallelization_parameter': 3}
            parts = [octets(b'scrypt-salt'), integer(16384), integer(8), integer(3)]
            if key is not None:
                params['key_length'] = key
                parts.append(integer(key))
            encoded = seq(*parts)
            for value in checked_algorithm_descriptions(self, KdfAlgorithm,
                    'scrypt', '1.3.6.1.4.1.11591.4.11', params, encoded):
                self.assertEqual(value['parameters'].native, dict(params, key_length=key))
            outer = {'key_derivation_func': {'algorithm': 'scrypt', 'parameters': params},
                     'encryption_scheme': {'algorithm': 'aes192_cbc', 'parameters': bytes(range(16))}}
            wire = seq(identifier('1.3.6.1.4.1.11591.4.11', encoded),
                       identifier('2.16.840.1.101.3.4.1.22', octets(bytes(range(16)))))
            for value in checked_algorithm_descriptions(self, EncryptionAlgorithm,
                    'pbes2', '1.2.840.113549.1.5.13', outer, wire):
                self.assertEqual(value.kdf, 'scrypt')
                self.assertEqual(value['parameters']['key_derivation_func']['parameters'].native,
                                 dict(params, key_length=key))
        for length in (None, 160):
            params = {'p': (1 << 521) - 1, 'g': 5}
            parts = [integer(params['p']), integer(5)]
            if length is not None:
                params['private_value_length'] = length
                parts.append(integer(length))
            for value in checked_algorithm_descriptions(self, KeyExchangeAlgorithm,
                    'dh', '1.2.840.113549.1.3.1', params, seq(*parts)):
                self.assertEqual(value['parameters'].native, dict(params, private_value_length=length))
        # PBES1 and PKCS#12 description members are each read and created in T07.

    def test_f06_t07(self):
        for index, (name, oid, kdf, digest, cipher, key) in enumerate(LEGACY_PASSWORD_IDENTITIES):
            salt, count = bytes(range(index, index + 8)), 1025 + index
            params = {'salt': salt, 'iterations': count}
            for value in checked_algorithm_descriptions(self, EncryptionAlgorithm,
                    name, oid, params, seq(octets(salt), integer(count))):
                self.assertEqual(value['parameters'].native, params)
                self.assertEqual(value.kdf, kdf)
                self.assertEqual(value.kdf_hmac, digest)
                self.assertEqual(value.kdf_salt, salt)
                self.assertEqual(value.kdf_iterations, count)
                self.assertEqual(value.encryption_cipher, cipher)
                self.assertEqual(value.key_length, key)
                self.assertIsNone(value.encryption_iv)
                if cipher != 'rc4':
                    self.assertEqual(value.encryption_mode, 'cbc')
                    self.assertEqual(value.encryption_block_size, 8)
        # Explicit derivation lengths override the embedded cipher, including a
        # value different from every AES key size. Default PRF has its own arm.
        for cipher, cipher_oid, size, iv, key, prf in (
            ('aes256_cbc', '2.16.840.1.101.3.4.1.42', 16, bytes(range(16)), None, None),
            ('aes256_cbc', '2.16.840.1.101.3.4.1.42', 16, bytes(range(16)), 19,
             ('sha512', '1.2.840.113549.2.11')),
            ('des', '1.3.14.3.2.7', 8, b'12345678', None, None),
        ):
            kd, kd_wire = pbkdf2_description(b'PBESsalt', 3001, key, prf)
            params = {'key_derivation_func': {'algorithm': 'pbkdf2', 'parameters': kd},
                      'encryption_scheme': {'algorithm': cipher, 'parameters': iv}}
            wire = seq(identifier('1.2.840.113549.1.5.12', kd_wire), identifier(cipher_oid, octets(iv)))
            for value in checked_algorithm_descriptions(self, EncryptionAlgorithm,
                    'pbes2', '1.2.840.113549.1.5.13', params, wire):
                self.assertEqual(value.kdf, 'pbkdf2')
                self.assertEqual(value.kdf_hmac, 'sha1' if prf is None else prf[0])
                self.assertEqual(value.kdf_salt, b'PBESsalt')
                self.assertEqual(value.kdf_iterations, 3001)
                self.assertEqual(value.encryption_cipher, 'aes' if cipher.startswith('aes') else 'des')
                self.assertEqual(value.encryption_mode, 'cbc')
                self.assertEqual(value.encryption_block_size, size)
                self.assertEqual(value.encryption_iv, iv)
                self.assertEqual(value.key_length, key if key is not None else (32 if size == 16 else 8))
        # The external salt choice keeps its description but cannot yield bytes.
        source = {'algorithm': '1.3.6.1.4.1.55555.23', 'parameters': Integer(7)}
        kd = {'salt': ('other_source', source), 'iteration_count': 3001}
        kd_wire = seq(identifier('1.3.6.1.4.1.55555.23', integer(7)), integer(3001))
        params = {'key_derivation_func': {'algorithm': 'pbkdf2', 'parameters': kd},
                  'encryption_scheme': {'algorithm': 'aes256_cbc', 'parameters': bytes(range(16))}}
        wire = seq(identifier('1.2.840.113549.1.5.12', kd_wire),
                   identifier('2.16.840.1.101.3.4.1.42', octets(bytes(range(16)))))
        for value in checked_algorithm_descriptions(self, EncryptionAlgorithm,
                'pbes2', '1.2.840.113549.1.5.13', params, wire):
            self.assertEqual(value.kdf, 'pbkdf2')
            self.assertEqual(value.kdf_iterations, 3001)
            self.assertEqual(value['parameters']['key_derivation_func']['parameters']['salt'].name, 'other_source')
            result = observe(lambda: value.kdf_salt, expected_exceptions=(ValueError,))
            self.assertIsInstance(result.error, ValueError)

    def test_f06_t08(self):
        # Independent integer encodings establish conformance, not just a
        # product-produced signature that the same product reads back.
        for r, s, minimum in ((0, 0, 1), (0, 128, 1), (128, 1, 1),
                              (0x1234, 0x80ff01, 3), ((1 << 256) - 1, 257, 32)):
            wire = seq(integer(r), integer(s))
            for value in (DSASignature({'r': r, 's': s}), DSASignature.load(wire)):
                self.assertEqual(value['r'].native, r)
                self.assertEqual(value['s'].native, s)
                self.assertEqual(value.dump(), wire)
                self.assertEqual(value.to_p1363(), r.to_bytes(minimum, 'big') + s.to_bytes(minimum, 'big'))
                for width in (minimum, minimum + 1, minimum + 7):
                    raw = r.to_bytes(width, 'big') + s.to_bytes(width, 'big')
                    self.assertEqual(value.to_p1363(width=width), raw)
                    parsed = DSASignature.from_p1363(raw)
                    self.assertEqual(parsed['r'].native, r)
                    self.assertEqual(parsed['s'].native, s)
                    self.assertEqual(parsed.dump(), wire)
                result = observe(value.to_p1363, kwargs={'width': minimum - 1},
                                 expected_exceptions=(ValueError,))
                self.assertIsInstance(result.error, ValueError)
