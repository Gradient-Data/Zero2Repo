# feature: F07
"""Independent key-document vectors and caller-supplied key components.

DER vectors are independently encoded from X.690 and the named document schemas.
The acceptance image reads the frozen encodings, without a runtime encoder.
"""
import json
from _helpers import support_path


def key_reference(description):
    vectors = json.loads(support_path('F07_vectors.json').read_text())
    return bytes.fromhex(vectors[json.dumps(description, separators=(',', ':'))])


def key_sequence(*parts):
    return key_reference(['sequence', [p.hex() for p in parts]])


def key_integer(number):
    return key_reference(['integer', number])


def key_octets(payload):
    return key_reference(['octets', payload.hex()])


def key_bits(payload):
    return key_reference(['bits', payload.hex()])


def key_oid(identity):
    return key_reference(['oid', identity])


def key_tagged(number, payload):
    return key_reference(['explicit', number, payload.hex()])


def key_identifier(identity, parameters=None):
    return key_sequence(key_oid(identity), *(() if parameters is None else (parameters,)))


KEY_IDENTITIES = {
    'rsa': '1.2.840.113549.1.1.1', 'rsassa_pss': '1.2.840.113549.1.1.10',
    'rsaes_oaep': '1.2.840.113549.1.1.7', 'dsa': '1.2.840.10040.4.1',
    'ec': '1.2.840.10045.2.1', 'dh': '1.2.840.10046.2.1',
    'x25519': '1.3.101.110', 'x448': '1.3.101.111',
    'ed25519': '1.3.101.112', 'ed448': '1.3.101.113',
}


def rsa_components(modulus=3233):
    return dict(version='two-prime', modulus=modulus, public_exponent=17,
                private_exponent=2753, prime1=61, prime2=53,
                exponent1=53, exponent2=49, coefficient=38)


def rsa_private_der(fields):
    return key_sequence(key_integer(0 if fields['version'] == 'two-prime' else 1),
                        *(key_integer(fields[name]) for name in (
                            'modulus', 'public_exponent', 'private_exponent',
                            'prime1', 'prime2', 'exponent1', 'exponent2', 'coefficient')),
                        *(() if 'other_prime_infos' not in fields else (
                            key_sequence(*(key_sequence(*(key_integer(p[n]) for n in (
                                'prime', 'exponent', 'coefficient')))
                                for p in fields['other_prime_infos'])),)))


def dsa_components(p=809, q=101):
    return dict(version=0, p=p, q=q, g=256, public_key=615, private_key=7)


def dsa_parameters_der(fields):
    return key_sequence(*(key_integer(fields[n]) for n in ('p', 'q', 'g')))


def private_container_der(algorithm, parameters, payload, attributes=None):
    return key_sequence(key_integer(0), key_identifier(KEY_IDENTITIES[algorithm], parameters),
                        key_octets(payload), *(() if attributes is None else (attributes,)))


def public_container_der(algorithm, parameters, payload):
    return key_sequence(key_identifier(KEY_IDENTITIES[algorithm], parameters), key_bits(payload))


def explicit_domain(order):
    return {'version': 'ecdpVer1',
            'field_id': {'field_type': 'prime_field', 'parameters': 23},
            'curve': {'a': b'\x01', 'b': b'\x02', 'seed': None},
            'base': b'\x04\x03\x0a', 'order': order, 'cofactor': 1, 'hash': None}


# SEC2, ANSI X9.62 and RFC 5639 identities, independently transcribed.
# Every row is a required identity/width, not an option cross product.
BUILTIN_CURVES = (
    ('secp112r1', '1.3.132.0.6', 14), ('secp112r2', '1.3.132.0.7', 14),
    ('sect113r1', '1.3.132.0.4', 15), ('sect113r2', '1.3.132.0.5', 15),
    ('secp128r1', '1.3.132.0.28', 16), ('secp128r2', '1.3.132.0.29', 16),
    ('sect131r1', '1.3.132.0.22', 17), ('sect131r2', '1.3.132.0.23', 17),
    ('brainpoolp160r1', '1.3.36.3.3.2.8.1.1.1', 20), ('brainpoolp160t1', '1.3.36.3.3.2.8.1.1.2', 20),
    ('c2pnb163v1', '1.2.840.10045.3.0.1', 21), ('c2pnb163v2', '1.2.840.10045.3.0.2', 21),
    ('c2pnb163v3', '1.2.840.10045.3.0.3', 21), ('c2pnb176w1', '1.2.840.10045.3.0.4', 21),
    ('sect163k1', '1.3.132.0.1', 21), ('sect163r1', '1.3.132.0.2', 21),
    ('secp160r1', '1.3.132.0.8', 21), ('secp160k1', '1.3.132.0.9', 21),
    ('sect163r2', '1.3.132.0.15', 21), ('secp160r2', '1.3.132.0.30', 21),
    ('c2tnb191v1', '1.2.840.10045.3.0.5', 24), ('c2tnb191v2', '1.2.840.10045.3.0.6', 24),
    ('c2tnb191v3', '1.2.840.10045.3.0.7', 24), ('c2onb191v4', '1.2.840.10045.3.0.8', 24),
    ('c2onb191v5', '1.2.840.10045.3.0.9', 24), ('prime192v2', '1.2.840.10045.3.1.2', 24),
    ('prime192v3', '1.2.840.10045.3.1.3', 24), ('secp192r1', '1.2.840.10045.3.1.1', 24),
    ('secp192k1', '1.3.132.0.31', 24), ('brainpoolp192r1', '1.3.36.3.3.2.8.1.1.3', 24),
    ('brainpoolp192t1', '1.3.36.3.3.2.8.1.1.4', 24),
    ('c2pnb208w1', '1.2.840.10045.3.0.10', 25), ('sect193r1', '1.3.132.0.24', 25),
    ('sect193r2', '1.3.132.0.25', 25), ('secp224r1', '1.3.132.0.33', 28),
    ('brainpoolp224r1', '1.3.36.3.3.2.8.1.1.5', 28), ('brainpoolp224t1', '1.3.36.3.3.2.8.1.1.6', 28),
    ('sect233k1', '1.3.132.0.26', 29), ('secp224k1', '1.3.132.0.32', 29),
    ('c2tnb239v1', '1.2.840.10045.3.0.11', 30), ('c2tnb239v2', '1.2.840.10045.3.0.12', 30),
    ('c2tnb239v3', '1.2.840.10045.3.0.13', 30), ('c2onb239v4', '1.2.840.10045.3.0.14', 30),
    ('c2onb239v5', '1.2.840.10045.3.0.15', 30), ('prime239v1', '1.2.840.10045.3.1.4', 30),
    ('prime239v2', '1.2.840.10045.3.1.5', 30), ('prime239v3', '1.2.840.10045.3.1.6', 30),
    ('sect239k1', '1.3.132.0.3', 30), ('sect233r1', '1.3.132.0.27', 30),
    ('secp256r1', '1.2.840.10045.3.1.7', 32), ('secp256k1', '1.3.132.0.10', 32),
    ('brainpoolp256r1', '1.3.36.3.3.2.8.1.1.7', 32), ('brainpoolp256t1', '1.3.36.3.3.2.8.1.1.8', 32),
    ('c2pnb272w1', '1.2.840.10045.3.0.16', 33), ('sect283k1', '1.3.132.0.16', 36),
    ('sect283r1', '1.3.132.0.17', 36), ('c2pnb304w1', '1.2.840.10045.3.0.17', 37),
    ('brainpoolp320r1', '1.3.36.3.3.2.8.1.1.9', 40), ('brainpoolp320t1', '1.3.36.3.3.2.8.1.1.10', 40),
    ('c2tnb359v1', '1.2.840.10045.3.0.18', 45), ('c2pnb368w1', '1.2.840.10045.3.0.19', 45),
    ('secp384r1', '1.3.132.0.34', 48), ('brainpoolp384r1', '1.3.36.3.3.2.8.1.1.11', 48),
    ('brainpoolp384t1', '1.3.36.3.3.2.8.1.1.12', 48), ('sect409k1', '1.3.132.0.36', 51),
    ('sect409r1', '1.3.132.0.37', 52), ('c2tnb431r1', '1.2.840.10045.3.0.20', 53),
    ('brainpoolp512r1', '1.3.36.3.3.2.8.1.1.13', 64), ('brainpoolp512t1', '1.3.36.3.3.2.8.1.1.14', 64),
    ('secp521r1', '1.3.132.0.35', 66), ('sect571k1', '1.3.132.0.38', 72),
    ('sect571r1', '1.3.132.0.39', 72),
)


def key_checked_documents(case, cls, fields, wire):
    """Check constructed and independently encoded input through public APIs."""
    documents = (cls(fields), cls.load(wire))
    for document in documents:
        case.assertEqual(document.dump(), wire)
        # Force complete interpretation; nested failures must remain failures.
        document.native
    return documents


def key_attribute_wire(label):
    """RFC 5208 implicit [0] attributes containing a friendly-name attribute."""
    return key_reference(['attributes', label])
