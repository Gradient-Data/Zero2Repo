# feature: F17
"""PDF inputs and frozen independent PDF 1.7 / X.690 encodings."""
import json
from cobaltform.pdf import RevocationInfoArchival
from cobaltform.x509 import GeneralName
from _helpers import support_path
from F09_helpers import certificate_document, cert_seq, cert_explicit, cert_uri
from F11_helpers import crl_document
from F13_helpers import ocsp_response_document
from F14_helpers import cms_attribute_row, cms_bound_attributes


def pdf_reference(tree):
    """Read offline pyasn1 DER; missing vectors are errors."""
    vectors = json.loads(support_path('F17_vectors.json').read_text())
    return bytes.fromhex(vectors[json.dumps(tree, separators=(',', ':'))])


def pdf_certificate(auth=None):
    version = {None: 1, False: 128, True: 3}[auth]
    location = 'https://tsa.example.org/service/' + str(version)
    timestamp = {'version': version, 'location': GeneralName(('uniform_resource_identifier', location))}
    timestamp_tree = cert_seq(['int', version], cert_uri(location))
    if auth is not None:
        timestamp['requires_auth'] = auth
        if auth:
            timestamp_tree[1].append(['bool', True])
    rows = [
        ('adobe_archive_rev_info', '1.2.840.113583.1.1.9.2', {'version': version + 1}, cert_seq(['int', version + 1])),
        ('adobe_timestamp', '1.2.840.113583.1.1.9.1', timestamp, timestamp_tree),
        ('adobe_ppklite_credential', '1.2.840.113583.1.1.10', None, ['null', None]),
        ('extended_key_usage', '2.5.29.37', ['pdf_signing'], cert_seq(['oid', '1.2.840.113583.1.1.5'])),
    ]
    document, _, _ = certificate_document()
    document['tbs_certificate']['extensions'] = [
        {'extn_id': name, 'extn_value': value} for name, oid, value, tree in rows]
    extensions = cert_seq(*(cert_seq(['oid', oid], ['octets', pdf_reference(tree).hex()])
                            for name, oid, value, tree in rows))
    return document, ['certificate', extensions], rows, version, location


def pdf_archival_parts(present, empty=False):
    """Bind each supplied collection through a CMS signer's signed attributes."""
    crls = [crl_document(), crl_document(version='v1')]
    responses = [ocsp_response_document(), ocsp_response_document(by_name=False, encode=pdf_reference)]
    others = [{'type': '1.2.3.17.1', 'value': b'\x00\xffopaque revocation'},
              {'type': '1.2.3.17.2', 'value': b'\x80\x01different material'}]
    supplied = {'crl': [row[0] for row in crls], 'ocsp': [row[0] for row in responses],
                'other_rev_info': others}
    trees = {'crl': [['raw', row[1].hex()] for row in crls],
             'ocsp': [['raw', row[1].hex()] for row in responses],
             'other_rev_info': [cert_seq(['oid', row['type']], ['octets', row['value'].hex()]) for row in others]}
    fields, pieces = {}, []
    for number, name in enumerate(('crl', 'ocsp', 'other_rev_info')):
        if name in present:
            fields[name] = [] if empty else supplied[name]
            pieces.append(cert_explicit(number, cert_seq(*([] if empty else trees[name]))))
    if not present:
        # The original empty-dict Sequence constructor leaves content unset.
        # Supply an independently encoded empty record through the public loader.
        fields = RevocationInfoArchival.load(pdf_reference(cert_seq()))
    row = cms_attribute_row('adobe_revocation_info_archival', '1.2.840.113583.1.1.8',
                            [fields], [cert_seq(*pieces)], None)
    return cms_bound_attributes([row]), crls, responses, others
