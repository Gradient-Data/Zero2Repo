# feature: F11
"""CRL inputs with frozen, independently encoded RFC 5280 DER vectors."""
import json
from cobaltform.core import ParsableOctetString
from cobaltform.crl import (
    CRLEntryExtensions, CertificateList, RevokedCertificates, TBSCertListExtensions,
)
from cobaltform.x509 import Time
from _helpers import support_path
from F08_helpers import grouped_name
from F09_helpers import (
    CERT_START, CERT_END, cert_seq, cert_set, cert_explicit, cert_implicit,
    cert_algorithm, cert_name, cert_uri, cert_point, cert_extension,
)


def crl_reference(tree):
    """Read an offline pyasn1 encoding; absent vectors are errors."""
    vectors = json.loads(support_path('F11_vectors.json').read_text())
    return bytes.fromhex(vectors[json.dumps(tree, separators=(',', ':'))])


def crl_extension_tree(row):
    identity, name, tree, expected, critical = row
    return cert_seq(['oid', identity], *([['bool', True]] if critical else []),
                    ['octets', crl_reference(tree).hex()])


def crl_extension_fields(rows):
    return [dict(extn_id=row[0], extn_value=ParsableOctetString(crl_reference(row[2])),
                 **({'critical': True} if row[4] else {})) for row in rows]


def crl_interpreted_value(value, tree):
    """Observe scalar OID identity independently of its display-name mapping."""
    if tree[0] == 'oid':
        return value.dotted
    return value.native


def crl_entry_parts(serial, general=False, rows=None):
    fields = {'user_certificate': serial,
              'revocation_date': Time({'general_time': CERT_END} if general else {'utc_time': CERT_START})}
    parts = [['int', serial], ['time', '20520301010203Z'] if general else ['utc', '240229123456Z']]
    if rows is not None:
        fields['crl_entry_extensions'] = CRLEntryExtensions(crl_extension_fields(rows))
        parts.append(cert_seq(*(crl_extension_tree(row) for row in rows)))
    return fields, cert_seq(*parts)


CRL_ENTRIES = ((301, False, None), (7, True, None), (2 ** 70 + 19, False, None))


def crl_document(version='v2', entries=CRL_ENTRIES, rows=None, next_update=True,
                 issuer='Revocation Authority', signature=b'\x00\x81\xfe', ec=False):
    algorithm = {'algorithm': 'sha384_ecdsa' if ec else 'sha256_rsa'}
    algorithm_tree = cert_seq(['oid', '1.2.840.10045.4.3.3']) if ec else cert_algorithm()
    fields = {'signature': algorithm, 'issuer': grouped_name([[('common_name', issuer)]]),
              'this_update': Time({'utc_time': CERT_START})}
    pieces = []
    if version is not None:
        fields['version'] = version
        pieces.append(['int', {'v1': 0, 'v2': 1}[version]])
    pieces += [algorithm_tree, cert_name(issuer), ['utc', '240229123456Z']]
    if next_update:
        fields['next_update'] = Time({'general_time': CERT_END})
        pieces.append(['time', '20520301010203Z'])
    if entries is not None:
        entry_parts = [crl_entry_parts(*entry) for entry in entries]
        fields['revoked_certificates'] = RevokedCertificates([entry[0] for entry in entry_parts])
        pieces.append(cert_seq(*(entry[1] for entry in entry_parts)))
    if rows is not None:
        fields['crl_extensions'] = TBSCertListExtensions(crl_extension_fields(rows))
        pieces.append(cert_explicit(0, cert_seq(*(crl_extension_tree(row) for row in rows))))
    tree = cert_seq(cert_seq(*pieces), algorithm_tree, ['bitbytes', signature.hex()])
    document = CertificateList({'tbs_cert_list': fields,
                                    'signature_algorithm': algorithm, 'signature': signature})
    return document, crl_reference(tree)


def crl_documents(case, **kwargs):
    created, wire = crl_document(**kwargs)
    loaded = CertificateList.load(wire)
    for document in (created, loaded):
        case.assertEqual(document.dump(), wire)
        document.native
    return created, loaded


def crl_wide_rows():
    """Explicit extension identities and supplied semantic expectations."""
    return [
        cert_extension('2.5.29.18', 'issuer_alt_name', cert_seq(cert_implicit(2, ['ia5', 'revoker.example.org']),
            cert_uri('https://revoker.example.org/')), ['revoker.example.org', 'https://revoker.example.org/']),
        cert_extension('2.5.29.20', 'crl_number', ['int', 4097], 4097),
        cert_extension('2.5.29.27', 'delta_crl_indicator', ['int', 4090], 4090, True),
        cert_extension('2.5.29.28', 'issuing_distribution_point', cert_seq(
            cert_explicit(0, cert_implicit(0, cert_seq(cert_uri('http://revoker.example.org/scope')))),
            cert_implicit(1, ['bool', True]), cert_implicit(3, ['bits', '0100001']),
            cert_implicit(4, ['bool', True])),
            {'distribution_point': ['http://revoker.example.org/scope'], 'only_contains_user_certs': True,
             'only_contains_ca_certs': False, 'only_some_reasons': {'key_compromise', 'certificate_hold'},
             'indirect_crl': True, 'only_contains_attribute_certs': False}, True),
        cert_extension('2.5.29.35', 'authority_key_identifier', cert_seq(cert_implicit(0, ['octets', '0012ff'])),
            {'key_identifier': b'\x00\x12\xff', 'authority_cert_issuer': None, 'authority_cert_serial_number': None}),
        cert_extension('2.5.29.46', 'freshest_crl', cert_seq(cert_point('https://revoker.example.org/delta')),
            [{'distribution_point': ['https://revoker.example.org/delta'], 'reasons': None, 'crl_issuer': None}]),
        cert_extension('1.3.6.1.5.5.7.1.1', 'authority_information_access', cert_seq(cert_seq(
            ['oid', '1.3.6.1.5.5.7.48.2'], cert_uri('http://revoker.example.org/issuer'))),
            [{'access_method': 'ca_issuers', 'access_location': 'http://revoker.example.org/issuer'}]),
    ]


CRL_REASONS = ((0, 'unspecified'), (1, 'key_compromise'), (2, 'ca_compromise'),
               (3, 'affiliation_changed'), (4, 'superseded'), (5, 'cessation_of_operation'),
               (6, 'certificate_hold'), (8, 'remove_from_crl'), (9, 'privilege_withdrawn'),
               (10, 'aa_compromise'))


def crl_entry_rows(reason_number=1, reason_name='key_compromise'):
    return [
        cert_extension('2.5.29.21', 'crl_reason', ['enum', reason_number], reason_name),
        cert_extension('2.5.29.23', 'hold_instruction_code', ['oid', '1.2.840.10040.2.2'], '1.2.840.10040.2.2'),
        cert_extension('2.5.29.24', 'invalidity_date', ['time', '20240229123456Z'], CERT_START),
        cert_extension('2.5.29.29', 'certificate_issuer', cert_seq(cert_explicit(4, cert_name('Entry Authority'))),
            [{'common_name': 'Entry Authority'}], True),
    ]


def crl_access(method, location):
    return cert_seq(['oid', method], location)


def crl_issuer_row(tree):
    return cert_extension('2.5.29.29', 'certificate_issuer', tree, None, True)
