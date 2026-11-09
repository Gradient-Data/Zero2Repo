# feature: F13
"""OCSP inputs and frozen independent RFC 6960/5280 DER expectations."""
import json
from cobaltform.core import ParsableOctetString
from cobaltform.ocsp import (
    BasicOCSPResponse, CertStatus, OCSPRequest, OCSPResponse, RequestExtensions,
    ResponderId, ResponseDataExtensions, SingleResponseExtensions, TBSRequestExtensions,
)
from cobaltform.x509 import GeneralName
from _helpers import support_path
from F08_helpers import grouped_name
from F09_helpers import (
    CERT_START, CERT_END, cert_seq, cert_explicit, cert_implicit,
    cert_algorithm, cert_name, cert_uri, cert_extension, certificate_document,
)


def ocsp_reference(tree):
    """Read an offline pyasn1 encoding; missing vectors fail directly."""
    data = json.loads(support_path('F13_vectors.json').read_text())
    return bytes.fromhex(data[json.dumps(tree, separators=(',', ':'))])


OCSP_IDS = (
    ('sha1', '1.3.14.3.2.26', bytes(range(20)), bytes(range(20, 40)), 513),
    ('sha256', '2.16.840.1.101.3.4.2.1', bytes(range(32)), bytes(range(32, 64)), 2 ** 80 + 29),
    ('sha1', '1.3.14.3.2.26', b'\xa7' * 20, b'\x19' * 20, 81),
)
OCSP_STATUSES = ((0, 'successful'), (1, 'malformed_request'), (2, 'internal_error'),
                 (3, 'try_later'), (5, 'sign_required'), (6, 'unauthorized'))


def ocsp_identifier(index, serial=None):
    name, oid, name_hash, key_hash, original_serial = OCSP_IDS[index]
    serial = original_serial if serial is None else serial
    return ({'hash_algorithm': {'algorithm': name}, 'issuer_name_hash': name_hash,
             'issuer_key_hash': key_hash, 'serial_number': serial},
            cert_seq(cert_algorithm(oid), ['octets', name_hash.hex()],
                     ['octets', key_hash.hex()], ['int', serial]))


def ocsp_extension_parts(rows, encode):
    fields = [dict(extn_id=row[0], extn_value=ParsableOctetString(encode(row[2])),
                   **({'critical': True} if row[4] else {})) for row in rows]
    tree = cert_seq(*(cert_seq(['oid', row[0]], *([['bool', True]] if row[4] else []),
                               ['octets', encode(row[2]).hex()]) for row in rows))
    return fields, tree


def ocsp_request_document(signed=False, certificates=False, requestor=None, count=2,
                          wide=None, single=None, serial=None, signature=b'\x00\x81\xfd',
                          encode=ocsp_reference):
    requests, request_trees = [], []
    for index in range(count):
        identifier, identifier_tree = ocsp_identifier(index, serial if index == 0 else None)
        fields, pieces = {'req_cert': identifier}, [identifier_tree]
        if single is not None and index == 0:
            ext_fields, ext_tree = ocsp_extension_parts(single, encode)
            fields['single_request_extensions'] = RequestExtensions(ext_fields)
            pieces.append(cert_explicit(0, ext_tree))
        requests.append(fields)
        request_trees.append(cert_seq(*pieces))
    tbs, pieces = {'request_list': requests}, []
    if requestor is not None:
        tbs['requestor_name'] = GeneralName(('uniform_resource_identifier', requestor))
        pieces.append(cert_explicit(1, cert_uri(requestor)))
    pieces.append(cert_seq(*request_trees))
    if wide is not None:
        ext_fields, ext_tree = ocsp_extension_parts(wide, encode)
        tbs['request_extensions'] = TBSRequestExtensions(ext_fields)
        pieces.append(cert_explicit(2, ext_tree))
    fields, tree = {'tbs_request': tbs}, [cert_seq(*pieces)]
    if signed:
        sig = {'signature_algorithm': {'algorithm': 'sha256_rsa'}, 'signature': signature}
        sig_parts = [cert_algorithm(), ['bitbytes', signature.hex()]]
        if certificates:
            cert, wire, _ = certificate_document()
            sig['certs'] = [cert]
            sig_parts.append(cert_explicit(0, cert_seq(['raw', wire.hex()])))
        fields['optional_signature'] = sig
        tree.append(cert_explicit(0, cert_seq(*sig_parts)))
    return OCSPRequest(fields), encode(cert_seq(*tree))


def ocsp_response_document(by_name=True, certificates=True, reason=True, wide=None, single=None,
                           serial=None, first_status='good', produced_end=False,
                           signature=b'\xff\x00\xa5', encode=ocsp_reference):
    responses, trees = [], []
    for index, status in enumerate((first_status, 'unknown', 'revoked')):
        identifier, identifier_tree = ocsp_identifier(index, serial if index == 0 else None)
        pieces = [identifier_tree]
        if status == 'revoked':
            value = {'revocation_time': CERT_START}
            revoked = [['time', '20240229123456Z']]
            if reason:
                value['revocation_reason'] = 'key_compromise'
                revoked.append(cert_explicit(0, ['enum', 1]))
            status_tree = cert_implicit(1, cert_seq(*revoked))
        else:
            value = None
            status_tree = cert_implicit(0 if status == 'good' else 2, ['null', None])
        fields = {'cert_id': identifier, 'cert_status': CertStatus((status, value)),
                  'this_update': CERT_START}
        pieces += [status_tree, ['time', '20240229123456Z']]
        if index == 0:
            fields['next_update'] = CERT_END
            pieces.append(cert_explicit(0, ['time', '20520301010203Z']))
        if single is not None and index == 0:
            ext_fields, ext_tree = ocsp_extension_parts(single, encode)
            fields['single_extensions'] = SingleResponseExtensions(ext_fields)
            pieces.append(cert_explicit(1, ext_tree))
        responses.append(fields)
        trees.append(cert_seq(*pieces))
    responder = (('by_name', grouped_name([[('common_name', 'OCSP Authority')]])) if by_name
                 else ('by_key', b'\x92' * 20))
    responder_tree = (cert_explicit(1, cert_name('OCSP Authority')) if by_name
                      else cert_explicit(2, ['octets', (b'\x92' * 20).hex()]))
    data = {'responder_id': ResponderId(responder),
            'produced_at': CERT_END if produced_end else CERT_START, 'responses': responses}
    pieces = [responder_tree, ['time', '20520301010203Z' if produced_end else '20240229123456Z'],
              cert_seq(*trees)]
    if wide is not None:
        ext_fields, ext_tree = ocsp_extension_parts(wide, encode)
        data['response_extensions'] = ResponseDataExtensions(ext_fields)
        pieces.append(cert_explicit(1, ext_tree))
    fields = {'tbs_response_data': data, 'signature_algorithm': {'algorithm': 'sha256_rsa'},
              'signature': signature}
    basic_parts = [cert_seq(*pieces), cert_algorithm(), ['bitbytes', signature.hex()]]
    if certificates:
        cert, wire, _ = certificate_document()
        fields['certs'] = [cert]
        basic_parts.append(cert_explicit(0, cert_seq(['raw', wire.hex()])))
    basic_wire = encode(cert_seq(*basic_parts))
    response_tree = cert_seq(['enum', 0], cert_explicit(0, cert_seq(
        ['oid', '1.3.6.1.5.5.7.48.1.1'], ['octets', basic_wire.hex()])))
    return OCSPResponse({'response_status': 'successful', 'response_bytes': {
        'response_type': 'basic_ocsp_response',
        'response': BasicOCSPResponse(fields)}}), encode(response_tree)


def ocsp_extension_rows():
    """Explicit standard OIDs, typed values and payloads at each binding level."""
    unknown = cert_extension('1.2.3.200.13', '1.2.3.200.13',
                             cert_seq(['int', 73], ['octets', '0081ff']), None, True)
    request = [
        cert_extension('1.3.6.1.5.5.7.48.1.2', 'nonce', ['octets', '0081a5ff'], b'\x00\x81\xa5\xff', True),
        cert_extension('1.3.6.1.5.5.7.48.1.4', 'acceptable_responses', cert_seq(
            ['oid', '1.3.6.1.5.5.7.48.1.1'], ['oid', '1.2.3.77']), ['basic_ocsp_response', '1.2.3.77']),
        cert_extension('1.3.6.1.5.5.7.48.1.8', 'preferred_signature_algorithms', cert_seq(
            cert_seq(cert_algorithm(), cert_algorithm('1.2.840.113549.1.1.1')),
            cert_seq(cert_seq(['oid', '1.2.840.10045.4.3.3']))),
            [{'sig_identifier': {'algorithm': 'sha256_rsa', 'parameters': None},
              'cert_identifier': {'algorithm': 'rsa', 'parameters': None}},
             {'sig_identifier': {'algorithm': 'sha384_ecdsa', 'parameters': None}, 'cert_identifier': None}]),
        unknown,
    ]
    entry = [cert_extension('1.3.6.1.5.5.7.48.1.7', 'service_locator', cert_seq(
        cert_name('Locator Authority'), cert_seq(cert_seq(
            ['oid', '1.3.6.1.5.5.7.48.1'], cert_uri('https://status.example.org/')))),
        {'issuer': {'common_name': 'Locator Authority'}, 'locator': [
            {'access_method': 'ocsp', 'access_location': 'https://status.example.org/'}]}, True), unknown]
    response = [cert_extension('1.3.6.1.5.5.7.48.1.2', 'nonce', ['octets', '19ab00'], b'\x19\xab\x00'),
                cert_extension('1.3.6.1.5.5.7.48.1.9', 'extended_revoke', ['null', None], None, True), unknown]
    single = [
        cert_extension('1.3.6.1.5.5.7.48.1.3', 'crl', cert_seq(
            cert_explicit(0, ['ia5', 'https://status.example.org/list']),
            cert_explicit(1, ['int', 513]), cert_explicit(2, ['time', '20240229123456Z'])),
            {'crl_url': 'https://status.example.org/list', 'crl_num': 513, 'crl_time': CERT_START}),
        cert_extension('1.3.6.1.5.5.7.48.1.6', 'archive_cutoff', ['time', '20520301010203Z'], CERT_END),
        cert_extension('2.5.29.21', 'crl_reason', ['enum', 6], 'certificate_hold'),
        cert_extension('2.5.29.24', 'invalidity_date', ['time', '20240229123456Z'], CERT_START),
        cert_extension('2.5.29.29', 'certificate_issuer', cert_seq(
            cert_explicit(4, cert_name('Certificate Authority'))), [{'common_name': 'Certificate Authority'}], True),
        cert_extension('1.3.6.1.4.1.11129.2.4.5', 'signed_certificate_timestamp_list',
                       ['octets', '00050003aabbcc'], b'\x00\x05\x00\x03\xaa\xbb\xcc'), unknown,
    ]
    return request, entry, response, single
