# feature: F09
"""Certificate inputs and frozen, independent DER reference encodings.

Trees describe X.690 values independently of product schemas. Frozen vectors
are generated offline; missing entries fail, without runtime substitution.
"""
import json
from datetime import datetime, timezone
from cobaltform.core import ParsableOctetString
from cobaltform.x509 import Certificate, Time
from _helpers import support_path
from F08_helpers import grouped_name


def cert_reference(tree):
    vectors = json.loads(support_path('F09_vectors.json').read_text())
    return bytes.fromhex(vectors[json.dumps(tree, separators=(',', ':'))])


def cert_seq(*children):
    return ['seq', list(children)]


def cert_set(*children):
    return ['set', list(children)]


def cert_implicit(number, tree):
    return ['implicit', number, tree]


def cert_explicit(number, tree):
    return ['explicit', number, tree]


def cert_algorithm(oid='1.2.840.113549.1.1.11'):
    return cert_seq(['oid', oid], ['null', None])


def cert_name(text):
    return cert_seq(cert_set(cert_seq(['oid', '2.5.4.3'], ['utf8', text])))


CERT_START = datetime(2024, 2, 29, 12, 34, 56, tzinfo=timezone.utc)
CERT_END = datetime(2052, 3, 1, 1, 2, 3, tzinfo=timezone.utc)


def cert_extension(identity, name, tree, expected, critical=False):
    """Describe supplied extension identity, independent DER and semantic value."""
    return (identity, name, tree, expected, critical)


def cert_ext_tree(row):
    identity, name, tree, expected, critical = row
    return cert_seq(['oid', identity], *([['bool', True]] if critical else []),
                    ['octets', cert_reference(tree).hex()])


def certificate_document(rows=(), version='v3', issuer='Authority', subject='Receiver',
                         signature=b'\x01\x80\xff', unique=False, serial=793, ec=False):
    """Return constructed certificate, independently encoded input, and fields."""
    signature_algorithm = {'algorithm': 'sha256_rsa'}
    public_key = {'algorithm': {'algorithm': 'rsa'},
                  'public_key': {'modulus': 3233, 'public_exponent': 17}}
    algorithm_tree = cert_algorithm()
    public_tree = cert_seq(cert_algorithm('1.2.840.113549.1.1.1'),
                           ['bitbytes', cert_reference(cert_seq(['int', 3233], ['int', 17])).hex()])
    if ec:
        signature_algorithm = {'algorithm': 'sha384_ecdsa'}
        algorithm_tree = cert_seq(['oid', '1.2.840.10045.4.3.3'])
        point = b'\x04' + bytes(range(1, 65))
        public_key = {'algorithm': {'algorithm': 'ec', 'parameters': {'named': 'secp256r1'}},
                      'public_key': point}
        public_tree = cert_seq(cert_seq(['oid', '1.2.840.10045.2.1'],
                                       ['oid', '1.2.840.10045.3.1.7']), ['bitbytes', point.hex()])
    fields = {'serial_number': serial, 'signature': signature_algorithm,
              'issuer': grouped_name([[('common_name', issuer)]]),
              'subject': grouped_name([[('common_name', subject)]]),
              'validity': {'not_before': Time({'utc_time': CERT_START}),
                           'not_after': Time({'general_time': CERT_END})},
              'subject_public_key_info': public_key}
    pieces = []
    if version is not None:
        fields['version'] = version
        if version != 'v1':
            pieces.append(cert_explicit(0, ['int', {'v2': 1, 'v3': 2}[version]]))
    pieces += [['int', serial], algorithm_tree, cert_name(issuer),
               cert_seq(['utc', '240229123456Z'], ['time', '20520301010203Z']),
               cert_name(subject),
               public_tree]
    if unique:
        fields['issuer_unique_id'] = b'\xa1\x00'
        fields['subject_unique_id'] = b'\x80\x02'
        pieces += [cert_implicit(1, ['bitbytes', 'a100']), cert_implicit(2, ['bitbytes', '8002'])]
    if rows:
        fields['extensions'] = [dict(extn_id=r[0], critical=r[4], extn_value=ParsableOctetString(cert_reference(r[2]))) for r in rows]
        pieces.append(cert_explicit(3, cert_seq(*(cert_ext_tree(r) for r in rows))))
    tree = cert_seq(cert_seq(*pieces), algorithm_tree, ['bitbytes', signature.hex()])
    document = Certificate({'tbs_certificate': fields,
                               'signature_algorithm': signature_algorithm,
                               'signature_value': signature})
    return document, cert_reference(tree), fields


def cert_uri(uri):
    return cert_implicit(6, ['ia5', uri])


def cert_point(uri):
    return cert_seq(cert_explicit(0, cert_implicit(0, cert_seq(cert_uri(uri)))))


def cert_extension_rows():
    """Explicit RFC 5280/7633/6960 extension declarations and supplied values."""
    gn = cert_seq(cert_implicit(2, ['ia5', 'alt.example.org']), cert_uri('https://identity.example.org/'))
    gn_native = ['alt.example.org', 'https://identity.example.org/']
    return [
        cert_extension('2.5.29.9', 'subject_directory_attributes', cert_seq(
            cert_seq(['oid', '1.3.6.1.5.5.7.9.3'], cert_set(['printable', 'F']))),
            [{'type': 'pda_gender', 'values': ['F']}]),
        cert_extension('2.5.29.14', 'key_identifier', ['octets', '12ab00'], b'\x12\xab\x00'),
        cert_extension('2.5.29.15', 'key_usage', ['bits', '101000001'], {'digital_signature', 'key_encipherment', 'decipher_only'}, True),
        cert_extension('2.5.29.16', 'private_key_usage_period', cert_seq(
            cert_implicit(0, ['time', '20240229123456Z']), cert_implicit(1, ['time', '20520301010203Z'])),
            {'not_before': CERT_START, 'not_after': CERT_END}),
        cert_extension('2.5.29.17', 'subject_alt_name', gn, gn_native),
        cert_extension('2.5.29.18', 'issuer_alt_name', gn, gn_native),
        cert_extension('2.5.29.19', 'basic_constraints', cert_seq(['bool', True], ['int', 3]),
                       {'ca': True, 'path_len_constraint': 3}, True),
        cert_extension('2.5.29.30', 'name_constraints', cert_seq(
            cert_implicit(0, cert_seq(cert_seq(cert_implicit(2, ['ia5', '.example.org'])))),
            cert_implicit(1, cert_seq(cert_seq(cert_implicit(2, ['ia5', '.blocked.org']), cert_implicit(1, ['int', 4]))))),
            {'permitted_subtrees': [{'base': '.example.org', 'minimum': 0, 'maximum': None}],
             'excluded_subtrees': [{'base': '.blocked.org', 'minimum': 0, 'maximum': 4}]}),
        cert_extension('2.5.29.31', 'crl_distribution_points', cert_seq(cert_point('ldap://crl.example.org/all')),
            [{'distribution_point': ['ldap://crl.example.org/all'], 'reasons': None, 'crl_issuer': None}]),
        cert_extension('2.5.29.32', 'certificate_policies', cert_seq(cert_seq(['oid', '1.2.3.4'], cert_seq(
            cert_seq(['oid', '1.3.6.1.5.5.7.2.1'], ['ia5', 'https://policy.example.org/'])))),
            [{'policy_identifier': '1.2.3.4', 'policy_qualifiers': [
                {'policy_qualifier_id': 'certification_practice_statement', 'qualifier': 'https://policy.example.org/'}]}]),
        cert_extension('2.5.29.33', 'policy_mappings', cert_seq(cert_seq(['oid', '1.2.3.4'], ['oid', '1.2.3.5'])),
            [{'issuer_domain_policy': '1.2.3.4', 'subject_domain_policy': '1.2.3.5'}]),
        cert_extension('2.5.29.35', 'authority_key_identifier', cert_seq(cert_implicit(0, ['octets', 'ab12'])),
            {'key_identifier': b'\xab\x12', 'authority_cert_issuer': None, 'authority_cert_serial_number': None}),
        cert_extension('2.5.29.36', 'policy_constraints', cert_seq(cert_implicit(0, ['int', 2]), cert_implicit(1, ['int', 5])),
            {'require_explicit_policy': 2, 'inhibit_policy_mapping': 5}),
        cert_extension('2.5.29.46', 'freshest_crl', cert_seq(cert_point('https://crl.example.org/delta')),
            [{'distribution_point': ['https://crl.example.org/delta'], 'reasons': None, 'crl_issuer': None}]),
        cert_extension('2.5.29.54', 'inhibit_any_policy', ['int', 6], 6),
        cert_extension('2.5.29.37', 'extended_key_usage', cert_seq(['oid', '1.3.6.1.5.5.7.3.1'], ['oid', '1.3.6.1.5.5.7.3.2']),
            ['server_auth', 'client_auth']),
        cert_extension('1.3.6.1.5.5.7.1.1', 'authority_information_access', cert_seq(cert_seq(
            ['oid', '1.3.6.1.5.5.7.48.1'], cert_uri('https://ocsp.example.org/'))),
            [{'access_method': 'ocsp', 'access_location': 'https://ocsp.example.org/'}]),
        cert_extension('1.3.6.1.5.5.7.1.11', 'subject_information_access', cert_seq(cert_seq(
            ['oid', '1.3.6.1.5.5.7.48.5'], cert_uri('https://repository.example.org/'))),
            [{'access_method': 'ca_repository', 'access_location': 'https://repository.example.org/'}]),
        cert_extension('1.3.6.1.5.5.7.1.24', 'tls_feature', cert_seq(['int', 5], ['int', 17]), [5, 17]),
        cert_extension('1.3.6.1.5.5.7.48.1.5', 'ocsp_no_check', ['null', None], None),
        cert_extension('1.2.840.113533.7.65.0', 'entrust_version_extension', cert_seq(['general', 'V7.1'], ['bits', '101']),
            {'entrust_vers': 'V7.1', 'entrust_info_flags': (1, 0, 1)}),
        cert_extension('2.16.840.1.113730.1.1', 'netscape_certificate_type', ['bits', '11000101'],
            {'ssl_client', 'ssl_server', 'ssl_ca', 'object_signing_ca'}),
        cert_extension('1.3.6.1.4.1.11129.2.4.2', 'signed_certificate_timestamp_list', ['octets', '00050003aabbcc'], b'\x00\x05\x00\x03\xaa\xbb\xcc'),
        cert_extension('1.3.6.1.4.1.311.20.2', 'microsoft_enroll_certtype', ['bmp', 'User Certificate'], 'User Certificate'),
    ]


def cert_directory_row(attributes):
    """Bind explicit (OID, value-set tree) attributes as a certificate extension."""
    return cert_extension('2.5.29.9', 'subject_directory_attributes',
                          cert_seq(*(cert_seq(['oid', oid], values) for oid, values in attributes)), None)


def cert_documents(case, **kwargs):
    """Check public construction and independent loading against reference DER."""
    created, wire, fields = certificate_document(**kwargs)
    loaded = Certificate.load(wire)
    for document in (created, loaded):
        case.assertEqual(document.dump(), wire)
        document.native
    return created, loaded
