# feature: F15
"""PKCS#12 inputs paired with frozen, independent DER encodings."""
import json
from cobaltform.core import Integer, Null, OctetString, UTF8String
from cobaltform.pkcs12 import Pfx, SafeContents
from _helpers import support_path
from F07_helpers import rsa_components, rsa_private_der, private_container_der
from F09_helpers import cert_seq, cert_set, cert_explicit, cert_algorithm, certificate_document
from F11_helpers import crl_document
from F14_helpers import cms_message


def p12_reference(tree):
    """Load an independently generated encoding; missing vectors are errors."""
    vectors = json.loads(support_path('F15_vectors.json').read_text())
    return bytes.fromhex(vectors[json.dumps(tree, separators=(',', ':'))])


def p12_container(entries, mac=None):
    """Wrap caller-supplied CMS entries in a data-carried authenticated safe."""
    safe_tree = cert_seq(*(tree for fields, tree in entries))
    safe_wire = p12_reference(safe_tree)
    auth_fields, auth_tree = cms_message('data', safe_wire)
    fields = {'version': 'v3', 'auth_safe': auth_fields}
    parts = [['int', 3], auth_tree]
    if mac is not None:
        count, salt, digest = mac
        fields['mac_data'] = {'mac': {'digest_algorithm': {'algorithm': 'sha256'}, 'digest': digest},
                              'mac_salt': salt}
        mac_parts = [cert_seq(cert_algorithm('2.16.840.1.101.3.4.2.1'), ['octets', digest.hex()]),
                     ['octets', salt.hex()]]
        if count is not None:
            fields['mac_data']['iterations'] = count
            if count != 1:
                mac_parts.append(['int', count])
        parts.append(cert_seq(*mac_parts))
    return fields, cert_seq(*parts)


def p12_documents(case, parts):
    fields, tree = parts
    wire = p12_reference(tree)
    documents = (Pfx(fields), Pfx.load(wire))
    for document in documents:
        case.assertEqual(document.dump(), wire)
        document.native
    return documents


def p12_bag(kind, value, tree, attributes=None):
    identities = {'key_bag': '1.2.840.113549.1.12.10.1.1',
                  'pkcs8_shrouded_key_bag': '1.2.840.113549.1.12.10.1.2',
                  'cert_bag': '1.2.840.113549.1.12.10.1.3',
                  'crl_bag': '1.2.840.113549.1.12.10.1.4',
                  'secret_bag': '1.2.840.113549.1.12.10.1.5',
                  'safe_contents': '1.2.840.113549.1.12.10.1.6'}
    fields = {'bag_id': kind, 'bag_value': value}
    parts = [['oid', identities[kind]], cert_explicit(0, tree)]
    if attributes is not None:
        fields['bag_attributes'] = [row[0] for row in attributes]
        parts.append(cert_set(*(row[1] for row in attributes)))
    return fields, cert_seq(*parts)


def p12_secret(payload=b'private secret\x00\xff'):
    fields = {'secret_type_id': '1.2.3.15.5', 'secret_value': payload}
    return p12_bag('secret_bag', fields,
        cert_seq(['oid', '1.2.3.15.5'], cert_explicit(0, ['octets', payload.hex()])))


def p12_safe_container(bags):
    safe_tree = cert_seq(*(tree for fields, tree in bags))
    return p12_container([cms_message('data', p12_reference(safe_tree))])


def p12_bound_bags(document):
    """Follow the PFX data binding before decoding its safe-content bytes."""
    return SafeContents.load(document.authenticated_safe[0]['content'].native)


def p12_bag_rows():
    rsa = rsa_components()
    private_wire = private_container_der('rsa', b'\x05\x00', rsa_private_der(rsa))
    private = {'version': 0, 'private_key_algorithm': {'algorithm': 'rsa'}, 'private_key': rsa}
    rows = [p12_bag('key_bag', private, ['raw', private_wire.hex()])]
    iv, cipher = b'0123456789abcdef', b'\x83\x00encrypted key\xff'
    encrypted = {'encryption_algorithm': {'algorithm': 'aes256_cbc', 'parameters': iv}, 'encrypted_data': cipher}
    rows.append(p12_bag('pkcs8_shrouded_key_bag', encrypted,
        cert_seq(cert_seq(['oid', '2.16.840.1.101.3.4.1.42'], ['octets', iv.hex()]), ['octets', cipher.hex()])))
    certificate, cert_wire, _ = certificate_document()
    rows.append(p12_bag('cert_bag', {'cert_id': 'x509', 'cert_value': certificate},
        cert_seq(['oid', '1.2.840.113549.1.9.22.1'], cert_explicit(0, ['octets', cert_wire.hex()]))))
    sdsi = b'opaque SDSI\x00\xffpayload'
    rows.append(p12_bag('cert_bag', {'cert_id': 'sdsi', 'cert_value': sdsi},
        cert_seq(['oid', '1.2.840.113549.1.9.22.2'], cert_explicit(0, ['octets', sdsi.hex()]))))
    _, crl_wire = crl_document()
    rows.append(p12_bag('crl_bag', {'crl_id': '1.2.840.113549.1.9.23.1', 'crl_value': crl_wire},
        cert_seq(['oid', '1.2.840.113549.1.9.23.1'], cert_explicit(0, ['octets', crl_wire.hex()]))))
    rows.append(p12_secret())
    leaf = p12_secret(b'nested secret\x80\x00')
    inner = p12_bag('safe_contents', [leaf[0]], cert_seq(leaf[1]))
    rows.append(p12_bag('safe_contents', [inner[0], p12_secret(b'sibling')[0]],
        cert_seq(inner[1], p12_secret(b'sibling')[1])))
    return rows


def p12_attributes():
    """All promised attribute identities, including heterogeneous open values."""
    rows = []
    for name, oid, values, trees in (
        ('friendly_name', '1.2.840.113549.1.9.20', ['Key \u4e3b\u4eba'],
            [['bmp', 'Key \u4e3b\u4eba']]),
        ('local_key_id', '1.2.840.113549.1.9.21', [b'\x00\x80\xff'],
            [['octets', '0080ff']]),
        ('microsoft_local_machine_keyset', '1.3.6.1.4.1.311.17.1', [Null()], [['null', None]]),
        ('trusted_key_usage', '2.16.840.1.113894.746875.1.1', ['any_extended_key_usage', 'server_auth'],
            [['oid', '2.5.29.37.0'], ['oid', '1.3.6.1.5.5.7.3.1']]),
        ('1.2.3.15.99', '1.2.3.15.99', [UTF8String('open text'), Integer(423), OctetString(b'\xff\x00')],
            [['utf8', 'open text'], ['int', 423], ['octets', 'ff00']]),
    ):
        rows.append(({'type': name, 'values': values}, cert_seq(['oid', oid], cert_set(*trees))))
    return rows
