# feature: F16
"""TSP inputs paired with independently encoded RFC structure descriptions."""
import json
from cobaltform.core import OctetString, UTF8String
from cobaltform.tsp import Evidence, TSTInfo
from cobaltform.x509 import GeneralName
from _helpers import support_path
from F09_helpers import (
    CERT_START, cert_seq, cert_set, cert_explicit, cert_implicit, cert_algorithm, cert_uri,
)
from F11_helpers import crl_document
from F14_helpers import cms_message, cms_signer, cms_attribute_row


def tsp_reference(tree):
    """Read frozen pyasn1 DER; missing reference material fails explicitly."""
    vectors = json.loads(support_path('F16_vectors.json').read_text())
    return bytes.fromhex(vectors[json.dumps(tree, separators=(',', ':'))])


def tsp_documents(case, cls, parts):
    fields, tree = parts
    wire = tsp_reference(tree)
    documents = cls(fields), cls.load(wire)
    for document in documents:
        case.assertEqual(document.dump(), wire)
        document.native
    return documents


TSP_STATUSES = ((0, 'granted'), (1, 'granted_with_mods'), (2, 'rejection'),
                (3, 'waiting'), (4, 'revocation_warning'), (5, 'revocation_notification'))
TSP_FAILURES = ((0, 'bad_alg'), (2, 'bad_request'), (5, 'bad_data_format'),
                (14, 'time_not_available'), (15, 'unaccepted_policy'),
                (16, 'unaccepted_extensions'), (17, 'add_info_not_available'), (25, 'system_failure'))


def tsp_imprint(alternate=False):
    name, oid, payload = (('sha384', '2.16.840.1.101.3.4.2.2', bytes(range(48))) if alternate else
                          ('sha256', '2.16.840.1.101.3.4.2.1', bytes(range(32))))
    return ({'hash_algorithm': {'algorithm': name}, 'hashed_message': payload},
            cert_seq(cert_algorithm(oid), ['octets', payload.hex()]))


def tsp_extensions():
    fields = [{'extn_id': '1.2.3.16.7', 'extn_value': b'\x00\xff'},
              {'extn_id': '1.2.3.16.8', 'critical': True, 'extn_value': b'\x05\x00'}]
    tree = cert_seq(cert_seq(['oid', '1.2.3.16.7'], ['octets', '00ff']),
                    cert_seq(['oid', '1.2.3.16.8'], ['bool', True], ['octets', '0500']))
    return fields, tree


def tsp_request(full=False, alternate=False):
    imprint, imprint_tree = tsp_imprint(alternate)
    fields = {'version': 'v1', 'message_imprint': imprint}
    pieces = [['int', 1], imprint_tree]
    if full:
        extensions, extension_tree = tsp_extensions()
        fields.update(req_policy='1.2.3.16.1', nonce=2 ** 79 + 57, cert_req=True, extensions=extensions)
        pieces += [['oid', '1.2.3.16.1'], ['int', 2 ** 79 + 57], ['bool', True],
                   cert_implicit(0, extension_tree)]
    return fields, cert_seq(*pieces)


def tsp_status(number, name, flags=None, texts=None):
    fields, pieces = {'status': name}, [['int', number]]
    if texts is not None:
        fields['status_string'] = texts
        pieces.append(cert_seq(*(['utf8', text] for text in texts)))
    if flags is not None:
        fields['fail_info'] = {name for bit, name in flags}
        positions = {bit for bit, name in flags}
        bits = ''.join('1' if bit in positions else '0' for bit in range(max(positions) + 1)) if positions else ''
        pieces.append(['bits', bits])
    return fields, cert_seq(*pieces)


def tsp_information(full=False, alternate=False):
    imprint, imprint_tree = tsp_imprint(alternate)
    fields = {'version': 'v1', 'policy': '1.2.3.16.2', 'message_imprint': imprint,
              'serial_number': 2 ** 72 + 29, 'gen_time': CERT_START}
    pieces = [['int', 1], ['oid', '1.2.3.16.2'], imprint_tree, ['int', 2 ** 72 + 29],
              ['time', '20240229123456Z']]
    if full:
        extensions, extension_tree = tsp_extensions()
        fields.update(accuracy={'seconds': 3, 'millis': 421, 'micros': 87}, ordering=True,
                      nonce=2 ** 79 + 57, tsa=GeneralName(('uniform_resource_identifier', 'https://tsa.example.org/')),
                      extensions=extensions)
        pieces += [cert_seq(['int', 3], cert_implicit(0, ['int', 421]), cert_implicit(1, ['int', 87])),
                   ['bool', True], ['int', 2 ** 79 + 57],
                   cert_explicit(0, cert_uri('https://tsa.example.org/')), cert_implicit(1, extension_tree)]
    return fields, cert_seq(*pieces)


def tsp_token(full=False, alternate=False):
    info, tree = tsp_information(full, alternate)
    fields, cms_tree = cms_message('signed_data', signers=[cms_signer(True)])
    encap = {'content_type': 'tst_info', 'content': TSTInfo(info)}
    encap_tree = cert_seq(['oid', '1.2.840.113549.1.9.16.1.4'],
                          cert_explicit(0, ['octets', tsp_reference(tree).hex()]))
    fields['content']['encap_content_info'] = encap
    # Replace the encapsulated-content field in the independent signed-data tree.
    cms_tree[1][1][2][1][2] = encap_tree
    return fields, cms_tree


def tsp_signing_row(version=1, full=False):
    certs, trees = [], []
    for index in range(2 if full else 1):
        size = 20 if version == 1 else (48 if full and index == 1 else 32)
        digest = bytes(range(size - 1)) + bytes([index])
        reference, parts = {'cert_hash': digest}, []
        if version == 2 and full and index == 1:
            reference['hash_algorithm'] = {'algorithm': 'sha384'}
            parts.append(cert_algorithm('2.16.840.1.101.3.4.2.2'))
        parts.append(['octets', digest.hex()])
        if full:
            reference['issuer_serial'] = {'issuer': [GeneralName(('dns_name', 'issuer.example.org')),
                GeneralName(('uniform_resource_identifier', 'https://issuer.example.org/'))],
                'serial_number': 830 + index}
            parts.append(cert_seq(cert_seq(cert_implicit(2, ['ia5', 'issuer.example.org']),
                cert_uri('https://issuer.example.org/')), ['int', 830 + index]))
        certs.append(reference)
        trees.append(cert_seq(*parts))
    fields, pieces = {'certs': certs}, [cert_seq(*trees)]
    if full:
        fields['policies'] = [{'policy_identifier': '1.2.3.16.10'}, {'policy_identifier': '1.2.3.16.11'}]
        pieces.append(cert_seq(cert_seq(['oid', '1.2.3.16.10']), cert_seq(['oid', '1.2.3.16.11'])))
    name, oid = (('signing_certificate', '1.2.840.113549.1.9.16.2.12') if version == 1 else
                 ('signing_certificate_v2', '1.2.840.113549.1.9.16.2.47'))
    return cms_attribute_row(name, oid, [fields], [cert_seq(*pieces)], None)


def tsp_metadata():
    attrs = [{'type': '1.2.3.16.20', 'values': [UTF8String('metadata value')]}]
    attrs_tree = cert_seq(cert_seq(['oid', '1.2.3.16.20'], cert_set(['utf8', 'metadata value'])))
    return ({'hash_protected': True, 'file_name': 'report-\u03b2.txt', 'media_type': 'text/plain',
             'other_meta_data': attrs},
            cert_seq(['bool', True], ['utf8', 'report-\u03b2.txt'], ['ia5', 'text/plain'], attrs_tree))


def tsp_evidence(kind, full=False):
    if kind == 'tst_evidence':
        fields, trees = [], []
        # This public structure uses EncapsulatedContentInfo for timestamp entries.
        for index in range(2 if full else 1):
            info, info_tree = tsp_information(bool(index), bool(index))
            encap = {'content_type': 'tst_info', 'content': TSTInfo(info)}
            encap_tree = cert_seq(['oid', '1.2.840.113549.1.9.16.1.4'],
                cert_explicit(0, ['octets', tsp_reference(info_tree).hex()]))
            entry, pieces = {'time_stamp': encap}, [encap_tree]
            if full and index == 0:
                crl, wire = crl_document()
                entry['crl'] = crl
                pieces.append(['raw', wire.hex()])
            fields.append(entry)
            trees.append(cert_seq(*pieces))
        return Evidence((kind, fields)), cert_implicit(0, cert_seq(*trees))
    if kind == 'other_evidence':
        fields = {'oe_type': '1.2.3.16.21', 'oe_value': UTF8String('external evidence')}
        return Evidence((kind, fields)), cert_implicit(2, cert_seq(['oid', '1.2.3.16.21'], ['utf8', 'external evidence']))
    if kind != 'ers_evidence':
        raise ValueError('Unknown evidence input')
    fields = {'version': 'v1', 'digest_algorithms': [{'algorithm': 'sha256'}, {'algorithm': 'sha384'}]}
    pieces = [['int', 1], cert_seq(cert_algorithm('2.16.840.1.101.3.4.2.1'), cert_algorithm('2.16.840.1.101.3.4.2.2'))]
    attrs, attrs_tree = tsp_metadata()[0]['other_meta_data'], tsp_metadata()[1][1][-1]
    if full:
        fields.update(crypto_infos=attrs, encryption_info={'encryption_info_type': '1.2.3.16.22',
                      'encryption_info_value': OctetString(b'\x80\x00encryption')})
        pieces += [cert_implicit(0, attrs_tree), cert_implicit(1, cert_seq(['oid', '1.2.3.16.22'],
                    ['octets', b'\x80\x00encryption'.hex()]))]
    entries, trees = [], []
    for index in range(2 if full else 1):
        stamp, stamp_tree = tsp_token(bool(index), bool(index))
        entry, entry_parts = {'time_stamp': stamp}, []
        if full:
            digest_name, digest_oid = (('sha384', '2.16.840.1.101.3.4.2.2') if index == 0 else
                                      ('sha256', '2.16.840.1.101.3.4.2.1'))
            hashes = [[b'left' + bytes([index]), b'right\x00'], [b'root\xff']]
            entry.update(digest_algorithm={'algorithm': digest_name}, attributes=attrs, reduced_hashtree=hashes)
            entry_parts += [cert_implicit(0, cert_algorithm(digest_oid)), cert_implicit(1, attrs_tree),
                cert_implicit(2, cert_seq(*(cert_seq(*(['octets', h.hex()] for h in row)) for row in hashes)))]
        entry_parts.append(stamp_tree)
        entries.append(entry)
        trees.append(cert_seq(*entry_parts))
    fields['archive_time_stamp_sequence'] = entries
    pieces.append(cert_seq(*trees))
    return Evidence((kind, fields)), cert_implicit(1, cert_seq(*pieces))


def tsp_timestamped(kind, full=False):
    evidence, evidence_tree = tsp_evidence(kind, full)
    fields, pieces = {'version': 'v1', 'temporal_evidence': evidence}, [['int', 1]]
    if full:
        metadata, metadata_tree = tsp_metadata()
        fields.update(data_uri='https://archive.example.org/data', meta_data=metadata, content=b'archive content\x00\xff')
        pieces += [['ia5', 'https://archive.example.org/data'], metadata_tree,
                   ['octets', b'archive content\x00\xff'.hex()]]
    pieces.append(evidence_tree)
    return fields, cert_seq(*pieces)
