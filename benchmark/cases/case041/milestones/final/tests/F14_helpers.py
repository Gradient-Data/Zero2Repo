# feature: F14
"""CMS documents paired with independent, frozen X.690 DER encodings."""
import json
from cobaltform.cms import (
    AttCertIssuer, AttCertSubject, AttributeCertificateV1, CertificateChoices, ContentInfo,
    IetfAttrValue, KeyAgreementRecipientIdentifier, OriginatorIdentifierOrKey,
    RecipientIdentifier, RecipientInfo, RevocationInfoChoice, SMIMEEncryptionKeyPreference,
    SignerIdentifier, Time,
)
from cobaltform.core import Integer, OctetString, UTF8String
from cobaltform.x509 import GeneralName
from _helpers import support_path
from F08_helpers import grouped_name
from F09_helpers import (
    CERT_START, CERT_END, cert_seq, cert_set, cert_explicit, cert_implicit,
    cert_algorithm, cert_name, cert_uri, certificate_document,
)
from F11_helpers import crl_document
from F13_helpers import ocsp_response_document


def cms_reference(tree):
    """Read independently encoded offline DER; missing vectors are errors."""
    data = json.loads(support_path('F14_vectors.json').read_text())
    return bytes.fromhex(data['vectors'][json.dumps(tree, separators=(',', ':'))])


def cms_compressed_input(payload):
    """Read a fixed legal stream, independently of the host compressor."""
    data = json.loads(support_path('F14_vectors.json').read_text())
    return bytes.fromhex(data['compression_inputs'][payload.hex()])


def cms_corrupt_inputs():
    """Read fixed malformed streams with independently encoded CMS framing."""
    data = json.loads(support_path('F14_vectors.json').read_text())
    return tuple(bytes.fromhex(value) for value in data['corrupt_compressed_inputs'])


CMS_IDENTITIES = (
    ('data', '1.2.840.113549.1.7.1'),
    ('signed_data', '1.2.840.113549.1.7.2'),
    ('enveloped_data', '1.2.840.113549.1.7.3'),
    ('signed_and_enveloped_data', '1.2.840.113549.1.7.4'),
    ('digested_data', '1.2.840.113549.1.7.5'),
    ('encrypted_data', '1.2.840.113549.1.7.6'),
    ('authenticated_data', '1.2.840.113549.1.9.16.1.2'),
    ('compressed_data', '1.2.840.113549.1.9.16.1.9'),
    ('authenticated_enveloped_data', '1.2.840.113549.1.9.16.1.23'),
)
CMS_PAYLOAD = b'CMS content\x00\xff\x80\n'
CMS_CIPHER = b'\x81\x00\xffEncrypted material\x17'
CMS_IV = bytes(range(16))


def cms_wrap(kind, fields, tree):
    identity = dict(CMS_IDENTITIES)[kind]
    return ({'content_type': kind, 'content': fields},
            cert_seq(['oid', identity], cert_explicit(0, tree)))


def cms_documents(case, parts, construct=True):
    fields, tree = parts
    wire = cms_reference(tree)
    documents = ((ContentInfo(fields), ContentInfo.load(wire)) if construct else
                 (ContentInfo.load(wire),))
    for document in documents:
        case.assertEqual(document.dump(), wire)
        document.native
    return documents


def cms_encapsulation(payload=CMS_PAYLOAD):
    fields = {'content_type': 'data'}
    parts = [['oid', '1.2.840.113549.1.7.1']]
    if payload is not None:
        fields['content'] = payload
        parts.append(cert_explicit(0, ['octets', payload.hex()]))
    return fields, cert_seq(*parts)


def cms_signer(key_id=False, attributes=False):
    if key_id:
        sid = SignerIdentifier(('subject_key_identifier', b'\xaa\x00\x99'))
        sid_tree = cert_implicit(0, ['octets', 'aa0099'])
    else:
        sid = SignerIdentifier(('issuer_and_serial_number', {
            'issuer': grouped_name([[('common_name', 'Signer Authority')]]), 'serial_number': 981}))
        sid_tree = cert_seq(cert_name('Signer Authority'), ['int', 981])
    fields = {'version': 'v3' if key_id else 'v1', 'sid': sid,
              'digest_algorithm': {'algorithm': 'sha256'},
              'signature_algorithm': {'algorithm': 'sha256_rsa'}, 'signature': b'\xab\x00\xf1'}
    tree = [['int', 3 if key_id else 1], sid_tree, cert_algorithm('2.16.840.1.101.3.4.2.1')]
    if attributes:
        row = cms_attribute_row('message_digest', '1.2.840.113549.1.9.4',
                                [b'\xa1\x00\xb2'], [['octets', 'a100b2']], [b'\xa1\x00\xb2'])
        fields['signed_attrs'] = [row[0]]
        tree.append(cert_implicit(0, cert_set(row[1])))
    tree += [cert_algorithm(), ['octets', 'ab00f1']]
    if attributes:
        row = cms_attribute_row('content_type', '1.2.840.113549.1.9.3', ['data'],
                                [['oid', '1.2.840.113549.1.7.1']], ['data'])
        fields['unsigned_attrs'] = [row[0]]
        tree.append(cert_implicit(1, cert_set(row[1])))
    return fields, cert_seq(*tree)


def cms_encryption(ciphertext=CMS_CIPHER):
    fields = {'content_type': 'data', 'content_encryption_algorithm': {
        'algorithm': 'aes128_cbc', 'parameters': CMS_IV}, 'encrypted_content': ciphertext}
    tree = cert_seq(['oid', '1.2.840.113549.1.7.1'],
        cert_seq(['oid', '2.16.840.1.101.3.4.1.2'], ['octets', CMS_IV.hex()]),
        cert_implicit(0, ['octets', ciphertext.hex()]))
    return fields, tree


def cms_recipients():
    """Each row supplies one distinct RFC 5652 recipient grammar."""
    rsa = {'algorithm': 'rsaes_pkcs1v15'}
    wrap = {'algorithm': 'aes128_wrap'}
    rsa_tree = cert_algorithm('1.2.840.113549.1.1.1')
    wrap_tree = cert_seq(['oid', '2.16.840.1.101.3.4.1.5'])
    rows = []
    for key_id in (False, True):
        rid = (RecipientIdentifier(('subject_key_identifier', b'\x12\x00\x34')) if key_id else
               RecipientIdentifier(('issuer_and_serial_number', {
                   'issuer': grouped_name([[('common_name', 'Recipient CA')]]), 'serial_number': 459})))
        rid_tree = (cert_implicit(0, ['octets', '120034']) if key_id else
                    cert_seq(cert_name('Recipient CA'), ['int', 459]))
        fields = {'version': 'v2' if key_id else 'v0', 'rid': rid,
                  'key_encryption_algorithm': rsa, 'encrypted_key': b'\x91\x00\xf2'}
        tree = cert_seq(['int', 2 if key_id else 0], rid_tree, rsa_tree, ['octets', '9100f2'])
        rows.append(('ktri', fields, tree))
    fields = {'version': 'v3', 'originator': OriginatorIdentifierOrKey(
        ('subject_key_identifier', b'\x03\x00\x04')), 'ukm': b'\x77\x88',
        'key_encryption_algorithm': wrap,
        'recipient_encrypted_keys': [{'rid': KeyAgreementRecipientIdentifier(('r_key_id', {
            'subject_key_identifier': b'\x55\x66', 'date': CERT_START})), 'encrypted_key': b'\xa0\xb1'}]}
    tree = cert_implicit(1, cert_seq(['int', 3], cert_explicit(0, cert_implicit(0, ['octets', '030004'])),
        cert_explicit(1, ['octets', '7788']), wrap_tree,
        cert_seq(cert_seq(cert_implicit(0, cert_seq(['octets', '5566'], ['time', '20240229123456Z'])),
                          ['octets', 'a0b1']))))
    rows.append(('kari', fields, tree))
    fields = {'version': 'v4', 'kekid': {'key_identifier': b'\x11\x22', 'date': CERT_START,
        'other': {'key_attr_id': '1.2.3.14', 'key_attr': UTF8String('key owner')}},
        'key_encryption_algorithm': wrap, 'encrypted_key': b'\xc2\xd3'}
    tree = cert_implicit(2, cert_seq(['int', 4], cert_seq(['octets', '1122'],
        ['time', '20240229123456Z'], cert_seq(['oid', '1.2.3.14'], ['utf8', 'key owner'])),
        wrap_tree, ['octets', 'c2d3']))
    rows.append(('kekri', fields, tree))
    fields = {'version': 'v0', 'key_derivation_algorithm': {'algorithm': 'pbkdf2',
        'parameters': {'salt': {'specified': b'\x13\x24\x35'}, 'iteration_count': 3072}},
        'key_encryption_algorithm': wrap, 'encrypted_key': b'\xe4\xf5'}
    tree = cert_implicit(3, cert_seq(['int', 0], cert_implicit(0, cert_seq(
        ['oid', '1.2.840.113549.1.5.12'], cert_seq(['octets', '132435'], ['int', 3072]))),
        wrap_tree, ['octets', 'e4f5']))
    rows.append(('pwri', fields, tree))
    fields = {'ori_type': '1.2.3.14.9', 'ori_value': UTF8String('external recipient')}
    tree = cert_implicit(4, cert_seq(['oid', '1.2.3.14.9'], ['utf8', 'external recipient']))
    rows.append(('ori', fields, tree))
    return rows


def cms_message(kind, payload=CMS_PAYLOAD, signers=(), recipients=(), certificates=None, revocations=None,
                signed_attrs=None, unsigned_attrs=None, ciphertext=CMS_CIPHER):
    if kind == 'data':
        return cms_wrap(kind, payload, ['octets', payload.hex()])
    encap, encap_tree = cms_encapsulation(payload)
    encrypted, encrypted_tree = cms_encryption(ciphertext)
    rec_fields = [RecipientInfo((name, fields)) for name, fields, tree in recipients]
    rec_tree = cert_set(*(tree for name, fields, tree in recipients))
    sig_fields = [fields for fields, tree in signers]
    sig_tree = cert_set(*(tree for fields, tree in signers))
    if kind == 'signed_data':
        fields = {'version': 'v3', 'digest_algorithms': [{'algorithm': 'sha256'}],
                  'encap_content_info': encap, 'signer_infos': sig_fields}
        pieces = [['int', 3], cert_set(cert_algorithm('2.16.840.1.101.3.4.2.1')), encap_tree]
        if certificates is not None:
            fields['certificates'] = [CertificateChoices((n, f)) for n, f, t in certificates]
            pieces.append(cert_implicit(0, cert_set(*(t for n, f, t in certificates))))
        if revocations is not None:
            fields['crls'] = [RevocationInfoChoice((n, f)) for n, f, t in revocations]
            pieces.append(cert_implicit(1, cert_set(*(t for n, f, t in revocations))))
        pieces.append(sig_tree)
    elif kind == 'digested_data':
        fields = {'version': 'v2', 'digest_algorithm': {'algorithm': 'sha256'},
                  'encap_content_info': encap, 'digest': b'\xdd\x00\x99'}
        pieces = [['int', 2], cert_algorithm('2.16.840.1.101.3.4.2.1'), encap_tree, ['octets', 'dd0099']]
    elif kind == 'compressed_data':
        compressed = cms_compressed_input(payload)
        encap, encap_tree = cms_encapsulation(compressed)
        fields = {'version': 'v0', 'compression_algorithm': {'algorithm': 'zlib'}, 'encap_content_info': encap}
        pieces = [['int', 0], cert_seq(['oid', '1.2.840.113549.1.9.16.3.8']), encap_tree]
    elif kind == 'encrypted_data':
        fields = {'version': 'v0', 'encrypted_content_info': encrypted}
        pieces = [['int', 0], encrypted_tree]
    elif kind in ('enveloped_data', 'signed_and_enveloped_data'):
        fields = {'version': 'v0', 'recipient_infos': rec_fields, 'encrypted_content_info': encrypted}
        pieces = [['int', 0], rec_tree]
        if kind == 'signed_and_enveloped_data':
            fields.update(digest_algorithms=[{'algorithm': 'sha256'}], signer_infos=sig_fields)
            pieces.append(cert_set(cert_algorithm('2.16.840.1.101.3.4.2.1')))
        pieces.append(encrypted_tree)
        if kind == 'signed_and_enveloped_data':
            pieces.append(sig_tree)
    elif kind == 'authenticated_data':
        fields = {'version': 'v0', 'recipient_infos': rec_fields, 'mac_algorithm': {'algorithm': 'sha256'},
                  'digest_algorithm': {'algorithm': 'sha256'}, 'encap_content_info': encap, 'mac': b'\x88\x00\xbb'}
        pieces = [['int', 0], rec_tree, cert_seq(['oid', '1.2.840.113549.2.9']),
                  cert_implicit(1, cert_algorithm('2.16.840.1.101.3.4.2.1')), encap_tree]
        if signed_attrs is not None:
            fields['auth_attrs'] = [r[0] for r in signed_attrs]
            pieces.append(cert_implicit(2, cert_set(*(r[1] for r in signed_attrs))))
        pieces.append(['octets', '8800bb'])
        if unsigned_attrs is not None:
            fields['unauth_attrs'] = [r[0] for r in unsigned_attrs]
            pieces.append(cert_implicit(3, cert_set(*(r[1] for r in unsigned_attrs))))
    elif kind == 'authenticated_enveloped_data':
        fields = {'version': 'v0', 'recipient_infos': rec_fields,
                  'auth_encrypted_content_info': encrypted, 'mac': b'\x10\x00\x20'}
        pieces = [['int', 0], rec_tree, encrypted_tree, ['octets', '100020']]
    else:
        raise ValueError('Unsupported test content identity')
    return cms_wrap(kind, fields, cert_seq(*pieces))


def cms_attribute_row(name, oid, values, trees, expected):
    return ({'type': name, 'values': values}, cert_seq(['oid', oid], cert_set(*trees)), expected)


def cms_attribute_rows(generalized_time=False):
    rows = [
        cms_attribute_row('content_type', '1.2.840.113549.1.9.3', ['data'], [['oid', '1.2.840.113549.1.7.1']], ['data']),
        cms_attribute_row('message_digest', '1.2.840.113549.1.9.4', [b'\x71\x00\xf2'], [['octets', '7100f2']], [b'\x71\x00\xf2']),
        cms_attribute_row('signing_time', '1.2.840.113549.1.9.5',
            [Time(('generalized_time', CERT_END))] if generalized_time else [Time(('utc_time', CERT_START))],
            [['time', '20520301010203Z']] if generalized_time else [['utc', '240229123456Z']],
            [CERT_END] if generalized_time else [CERT_START]),
    ]
    signer, signer_tree = cms_signer(True)
    rows.append(cms_attribute_row('counter_signature', '1.2.840.113549.1.9.6', [signer], [signer_tree],
        [{'version': 'v3', 'sid': b'\xaa\x00\x99', 'digest_algorithm': {'algorithm': 'sha256', 'parameters': None},
          'signed_attrs': None, 'signature_algorithm': {'algorithm': 'sha256_rsa', 'parameters': None},
          'signature': b'\xab\x00\xf1', 'unsigned_attrs': None}]))
    rows.append(cms_attribute_row('smime_capabilities', '1.2.840.113549.1.9.15', [[
        {'capability_id': 'aes128_cbc'}, {'capability_id': 'rc2', 'parameters': Integer(128)}]],
        [cert_seq(cert_seq(['oid', '2.16.840.1.101.3.4.1.2']),
                  cert_seq(['oid', '1.2.840.113549.3.2'], ['int', 128]))],
        [[{'capability_id': 'aes128_cbc', 'parameters': None}, {'capability_id': 'rc2', 'parameters': 128}]]))
    rows.append(cms_attribute_row('encrypt_key_pref', '1.2.840.113549.1.9.16.2.11', [
        SMIMEEncryptionKeyPreference(('recipient_key_id', {'subject_key_identifier': b'\x80\x91'}))],
        [cert_implicit(1, cert_seq(['octets', '8091']))],
        [{'subject_key_identifier': b'\x80\x91', 'date': None, 'other': None}]))
    for name, oid in (('signature_time_stamp_token', '1.2.840.113549.1.9.16.2.14'),
                      ('microsoft_nested_signature', '1.3.6.1.4.1.311.2.4.1'),
                      ('microsoft_time_stamp_token', '1.3.6.1.4.1.311.3.3.1')):
        fields, tree = cms_message('signed_data', payload=name.encode('ascii'), signers=[cms_signer(True)])
        # The nested token is a CMS document; its fields are checked on the bound path.
        rows.append(cms_attribute_row(name, oid, [fields], [tree], None))
    rows.append(cms_attribute_row('cms_algorithm_protection', '1.2.840.113549.1.9.52', [{
        'digest_algorithm': {'algorithm': 'sha256'}, 'signature_algorithm': {'algorithm': 'sha256_rsa'}}],
        [cert_seq(cert_algorithm('2.16.840.1.101.3.4.2.1'), cert_implicit(1, cert_algorithm()))],
        [{'digest_algorithm': {'algorithm': 'sha256', 'parameters': None},
          'signature_algorithm': {'algorithm': 'sha256_rsa', 'parameters': None}, 'mac_algorithm': None}]))
    rows.append(cms_attribute_row('1.2.3.14.100', '1.2.3.14.100', [UTF8String('open value'), Integer(751)],
        [['utf8', 'open value'], ['int', 751]], None))
    return rows


def cms_bound_attributes(rows):
    fields, tree = cms_signer(True)
    fields['signed_attrs'] = [r[0] for r in rows]
    tree[1].insert(3, cert_implicit(0, cert_set(*(r[1] for r in rows))))
    return cms_message('signed_data', signers=[(fields, tree)])


def cms_att_rows(full=True):
    """Attribute-certificate inputs with explicit structured expectations."""
    rows = []
    for name, oid in (('authentication_info', '1.3.6.1.5.5.7.10.1'), ('access_identity', '1.3.6.1.5.5.7.10.2')):
        fields = {'service': GeneralName(('uniform_resource_identifier', 'https://service.example.org/')),
                  'ident': GeneralName(('rfc822_name', name + '@example.org'))}
        parts = [cert_uri('https://service.example.org/'), cert_implicit(1, ['ia5', name + '@example.org'])]
        expected = {'service': 'https://service.example.org/', 'ident': name + '@example.org', 'auth_info': None}
        if full:
            fields['auth_info'] = b'\x10\x00\x90'
            parts.append(['octets', '100090'])
            expected['auth_info'] = b'\x10\x00\x90'
        rows.append(cms_attribute_row(name, oid, [fields], [cert_seq(*parts)], [expected]))
    for name, oid in (('charging_identity', '1.3.6.1.5.5.7.10.3'), ('group', '1.3.6.1.5.5.7.10.4')):
        fields = {'values': [IetfAttrValue(('octets', b'\xaa\x00')), IetfAttrValue(('oid', '1.2.3.77')),
                             IetfAttrValue(('string', name + ' member'))]}
        parts = []
        expected = {'policy_authority': None, 'values': [b'\xaa\x00', '1.2.3.77', name + ' member']}
        if full:
            fields['policy_authority'] = [GeneralName(('uniform_resource_identifier', 'https://policy.example.org/'))]
            parts.append(cert_implicit(0, cert_seq(cert_uri('https://policy.example.org/'))))
            expected['policy_authority'] = ['https://policy.example.org/']
        parts.append(cert_seq(['octets', 'aa00'], ['oid', '1.2.3.77'], ['utf8', name + ' member']))
        rows.append(cms_attribute_row(name, oid, [fields], [cert_seq(*parts)], [expected]))
    fields = {'role_name': GeneralName(('uniform_resource_identifier', 'urn:role:auditor'))}
    parts = []
    expected = {'role_authority': None, 'role_name': 'urn:role:auditor'}
    if full:
        fields['role_authority'] = [GeneralName(('dns_name', 'roles.example.org'))]
        parts.append(cert_implicit(0, cert_seq(cert_implicit(2, ['ia5', 'roles.example.org']))))
        expected['role_authority'] = ['roles.example.org']
    parts.append(cert_explicit(1, cert_uri('urn:role:auditor')))
    rows.append(cms_attribute_row('role', '2.5.4.72', [fields], [cert_seq(*parts)], [expected]))
    fields = {'policy_id': '1.2.3.88'}
    parts = [['oid', '1.2.3.88']]
    expected = {'policy_id': '1.2.3.88', 'class_list': {'unclassified'}, 'security_categories': None}
    if full:
        fields['class_list'] = {'secret', 'top_secret'}
        fields['security_categories'] = [{'type': '1.2.3.89', 'value': UTF8String('restricted', explicit=1)}]
        parts += [['bits', '000011'], cert_set(cert_seq(cert_implicit(0, ['oid', '1.2.3.89']),
                                                       cert_explicit(1, ['utf8', 'restricted']))) ]
        expected.update(class_list={'secret', 'top_secret'},
                        security_categories=[{'type': '1.2.3.89', 'value': 'restricted'}])
    rows.append(cms_attribute_row('clearance', '2.5.4.55', [fields], [cert_seq(*parts)], [expected]))
    def big(major, fraction, sign=None):
        value = {'major': major, 'fractional_seconds': fraction}
        pieces = [['int', major], ['int', fraction]]
        if sign is not None:
            value['sign'] = sign
            pieces.append(['int', sign])
        return value, cert_seq(*pieces), dict(value, sign=sign)
    supplied = [big(3950000000, 43), big(2, 77, -1 if full else None), big(3, 88), big(3950000300, 99)]
    names = ('ntp_time', 'offset', 'delay', 'expiration')
    fields = {name: row[0] for name, row in zip(names, supplied)}
    pieces = [r[1] for r in supplied]
    expected = {name: row[2] for name, row in zip(names, supplied)}
    expected['leap_event'] = None
    if full:
        leap = big(3950000100, 17, 1)
        fields['leap_event'] = [{'leap_time': leap[0], 'action': -1}]
        pieces.append(cert_set(cert_seq(leap[1], ['int', -1])))
        expected['leap_event'] = [{'leap_time': leap[2], 'action': -1}]
    rows.append(cms_attribute_row('timing_metrics', '1.3.6.1.4.1.601.10.4.1', [fields], [cert_seq(*pieces)], [expected]))
    fields = {'policy_id': ['1.2.3.90', '1.2.3.91']}
    pieces = [cert_seq(['oid', '1.2.3.90'], ['oid', '1.2.3.91'])]
    expected = {'policy_id': ['1.2.3.90', '1.2.3.91'], 'max_offset': None, 'max_delay': None}
    if full:
        for number, name in enumerate(('max_offset', 'max_delay')):
            value = big(number + 4, number + 55, 1)
            fields[name] = value[0]
            pieces.append(cert_explicit(number, value[1]))
            expected[name] = value[2]
    rows.append(cms_attribute_row('timing_policy', '1.3.6.1.4.1.601.10.4.2', [fields], [cert_seq(*pieces)], [expected]))
    return rows


def cms_attribute_certificate(full=True, v1=False):
    rows = cms_att_rows(full)
    fields = {'version': 'v1' if v1 else 'v2', 'signature': {'algorithm': 'sha256_rsa'},
              'serial_number': 832, 'att_cert_validity_period': {'not_before_time': CERT_START, 'not_after_time': CERT_END}}
    issuer_names = [GeneralName(('dns_name', 'issuer.example.org'))]
    holder_names = [GeneralName(('rfc822_name', 'holder@example.org'))]
    issuer_tree = cert_seq(cert_implicit(2, ['ia5', 'issuer.example.org']))
    holder_tree = cert_seq(cert_implicit(1, ['ia5', 'holder@example.org']))
    if v1:
        fields['subject'] = AttCertSubject(('subject_name', holder_names))
        fields['issuer'] = issuer_names
        fields['attributes'] = [{'type': '1.2.3.99', 'values': [UTF8String('v1 attribute')]}]
        pieces = [['int', 0], cert_explicit(1, holder_tree), issuer_tree]
        attrs_tree = cert_seq(cert_seq(['oid', '1.2.3.99'], cert_set(['utf8', 'v1 attribute'])))
    else:
        fields['holder'] = {'entity_name': holder_names}
        fields['issuer'] = AttCertIssuer(('v2_form', {'issuer_name': issuer_names}))
        fields['attributes'] = [r[0] for r in rows]
        pieces = [['int', 1], cert_seq(cert_implicit(1, holder_tree)), cert_implicit(0, cert_seq(issuer_tree))]
        attrs_tree = cert_seq(*(r[1] for r in rows))
    pieces += [cert_algorithm(), ['int', 832], cert_seq(['time', '20240229123456Z'], ['time', '20520301010203Z']), attrs_tree]
    fields = {'ac_info': fields, 'signature_algorithm': {'algorithm': 'sha256_rsa'}, 'signature': b'\x97\x00\xff'}
    tree = cert_seq(cert_seq(*pieces), cert_algorithm(), ['bitbytes', '9700ff'])
    if v1:
        # Preserve an explicit BER default: the original choice reader cannot
        # disambiguate a v1 certificate with its default version omitted.
        fields = AttributeCertificateV1.load(cms_reference(tree))
    return ('v1_attr_cert' if v1 else 'v2_attr_cert', fields, cert_implicit(1 if v1 else 2, tree)), rows


def cms_certificate_choices():
    certificate, wire, _ = certificate_document()
    v1, _ = cms_attribute_certificate(v1=True)
    v2, _ = cms_attribute_certificate()
    extended = {'extended_certificate_info': {'version': 0, 'certificate': certificate,
        'attributes': [{'type': '1.2.3.98', 'values': [Integer(17)]}]},
        'signature_algorithm': {'algorithm': 'sha256_rsa'}, 'signature': b'\x27\x00\x81'}
    ext_tree = cert_implicit(0, cert_seq(cert_seq(['int', 0], ['raw', wire.hex()],
        cert_set(cert_seq(['oid', '1.2.3.98'], cert_set(['int', 17])))), cert_algorithm(), ['bitbytes', '270081']))
    other = {'other_cert_format': '1.2.3.14.7', 'other_cert': OctetString(b'other certificate\x00')}
    return [('certificate', certificate, ['raw', wire.hex()]), ('extended_certificate', extended, ext_tree), v1, v2,
            ('other', other, cert_implicit(3, cert_seq(['oid', '1.2.3.14.7'], ['octets', b'other certificate\x00'.hex()])))]


def cms_revocation_choices(request=True):
    crl, crl_wire = crl_document()
    response, response_wire = ocsp_response_document()
    request_fields, request_tree = cms_message('data', b'SCVP request\x00')
    response_fields, response_tree = cms_message('data', b'SCVP response\xff')
    scvp = {'response': response_fields}
    pieces = []
    if request:
        scvp['request'] = request_fields
        pieces.append(cert_explicit(0, request_tree))
    pieces.append(response_tree)
    rows = [('crl', crl, ['raw', crl_wire.hex()])]
    for oid, fields, tree in (
        ('1.3.6.1.5.5.7.16.2', response, ['raw', response_wire.hex()]),
        ('1.3.6.1.5.5.7.16.4', scvp, cert_seq(*pieces)),
        ('1.2.3.14.8', UTF8String('other revocation'), ['utf8', 'other revocation']),
    ):
        rows.append(('other', {'other_rev_info_format': oid, 'other_rev_info': fields},
                     cert_implicit(1, cert_seq(['oid', oid], tree))))
    return rows
