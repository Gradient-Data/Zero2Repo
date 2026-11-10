# feature: F14
"""Acceptance tests for CMS/PKCS#7 content, metadata and compression."""
import unittest
import zlib
from cobaltform.cms import ContentInfo, DigestedData
from cobaltform.core import ParsableOctetString
from _helpers import observe
from F08_helpers import name_groups
from F09_helpers import CERT_START, CERT_END, cert_seq, cert_set, cert_explicit, certificate_document
from F11_helpers import crl_document
from F13_helpers import ocsp_response_document
from F14_helpers import (
    CMS_IDENTITIES, CMS_PAYLOAD, CMS_CIPHER, CMS_IV, cms_reference, cms_wrap,
    cms_documents, cms_message, cms_signer, cms_recipients, cms_attribute_row,
    cms_attribute_rows, cms_bound_attributes, cms_certificate_choices,
    cms_revocation_choices, cms_attribute_certificate,
    cms_compressed_input, cms_corrupt_inputs,
)


class TestCMS(unittest.TestCase):
    def test_f14_t01(self):
        for kind, oid in CMS_IDENTITIES:
            parts = cms_message(kind, recipients=cms_recipients()[:1])
            for document in cms_documents(self, parts):
                self.assertEqual(document['content_type'].native, kind)
                self.assertEqual(document['content_type'].dotted, oid)
                body = document['content']
                if kind == 'data':
                    self.assertEqual(body.native, CMS_PAYLOAD)
                    document['content'] = b'changed data\x00'
                    expected = cms_message(kind, b'changed data\x00')
                    self.assertEqual(document.dump(), cms_reference(expected[1]))
                elif kind in ('signed_data', 'digested_data', 'authenticated_data'):
                    self.assertEqual(body['encap_content_info']['content_type'].native, 'data')
                    self.assertEqual(body['encap_content_info']['content'].native, CMS_PAYLOAD)
                    body['encap_content_info']['content'] = b'changed encapsulation\xff'
                    expected = cms_message(kind, b'changed encapsulation\xff', recipients=cms_recipients()[:1])
                    self.assertEqual(document.dump(), cms_reference(expected[1]))
                elif kind == 'compressed_data':
                    self.assertEqual(body['compression_algorithm']['algorithm'].native, 'zlib')
                    self.assertEqual(body['encap_content_info']['content'].native, cms_compressed_input(CMS_PAYLOAD))
                else:
                    field = 'auth_encrypted_content_info' if kind == 'authenticated_enveloped_data' else 'encrypted_content_info'
                    self.assertEqual(body[field]['encrypted_content'].native, CMS_CIPHER)
                    body[field]['encrypted_content'] = b'changed ciphertext\x00'
                    expected = cms_message(kind, recipients=cms_recipients()[:1], ciphertext=b'changed ciphertext\x00')
                    self.assertEqual(document.dump(), cms_reference(expected[1]))
        for kind in ('signed_data', 'digested_data', 'authenticated_data'):
            for payload in (None, b''):
                for document in cms_documents(self, cms_message(kind, payload)):
                    self.assertEqual(document['content']['encap_content_info']['content'].native, payload)
        # The same non-data identity has direct PKCS#7 and octet-wrapped CMS forms.
        inner_fields, inner_tree = cms_message('digested_data', b'nested content\x00')
        inner_fields, inner_tree = inner_fields['content'], inner_tree[1][1][2]
        for pkcs7 in (True, False):
            fields, tree = cms_message('signed_data')
            fields['content']['version'] = 'v1' if pkcs7 else 'v3'
            fields['content']['encap_content_info'] = {'content_type': 'digested_data',
                'content': DigestedData(inner_fields) if pkcs7 else ParsableOctetString(cms_reference(inner_tree))}
            body_tree = tree[1][1][2]
            body_tree[1][0] = ['int', 1 if pkcs7 else 3]
            body_tree[1][2] = cert_seq(['oid', '1.2.840.113549.1.7.5'], cert_explicit(0,
                inner_tree if pkcs7 else ['octets', cms_reference(inner_tree).hex()]))
            for document in cms_documents(self, (fields, tree)):
                encapsulated = document['content']['encap_content_info']
                self.assertEqual(encapsulated['content_type'].native, 'digested_data')
                nested = encapsulated['content'] if pkcs7 else encapsulated['content'].parsed
                self.assertEqual(nested['digest'].native, b'\xdd\x00\x99')
                self.assertEqual(nested['encap_content_info']['content'].native, b'nested content\x00')

    def test_f14_t02(self):
        cert_rows = cms_certificate_choices()[:1]
        rev_rows = cms_revocation_choices()[:1]
        for present in (True, False):
            signers = [cms_signer(False, present), cms_signer(True, present)]
            parts = cms_message('signed_data', signers=signers,
                certificates=cert_rows if present else None, revocations=rev_rows if present else None)
            for document in cms_documents(self, parts):
                body = document['content']
                self.assertEqual([a['algorithm'].native for a in body['digest_algorithms']], ['sha256'])
                self.assertEqual(len(body['signer_infos']), 2)
                signers_by_id = {s['sid'].name: s for s in body['signer_infos']}
                self.assertEqual(set(signers_by_id), {'issuer_and_serial_number', 'subject_key_identifier'})
                for identity, signer in signers_by_id.items():
                    if identity == 'subject_key_identifier':
                        self.assertEqual(signer['sid'].chosen.native, b'\xaa\x00\x99')
                    else:
                        self.assertEqual(signer['sid'].chosen['serial_number'].native, 981)
                        self.assertEqual(name_groups(signer['sid'].chosen['issuer']), [[('2.5.4.3', 'Signer Authority')]])
                    self.assertEqual(signer['digest_algorithm']['algorithm'].native, 'sha256')
                    self.assertEqual(signer['signature_algorithm']['algorithm'].native, 'sha256_rsa')
                    self.assertEqual(signer['signature'].native, b'\xab\x00\xf1')
                    if present:
                        self.assertEqual(signer['signed_attrs'][0]['type'].native, 'message_digest')
                        self.assertEqual(signer['signed_attrs'][0]['values'].native, [b'\xa1\x00\xb2'])
                        self.assertEqual(signer['unsigned_attrs'][0]['type'].native, 'content_type')
                        self.assertEqual(signer['unsigned_attrs'][0]['values'].native, ['data'])
                    else:
                        self.assertIsNone(signer['signed_attrs'].native)
                        self.assertIsNone(signer['unsigned_attrs'].native)
                if present:
                    self.assertEqual(body['certificates'][0].name, 'certificate')
                    self.assertEqual(body['certificates'][0].chosen.dump(), certificate_document()[1])
                    self.assertEqual(body['crls'][0].name, 'crl')
                    self.assertEqual(body['crls'][0].chosen.dump(), crl_document()[1])
                else:
                    self.assertIsNone(body['certificates'].native)
                    self.assertIsNone(body['crls'].native)
        row = cms_attribute_row('message_digest', '1.2.840.113549.1.9.4', [b'\x09\x00'], [['octets', '0900']], [b'\x09\x00'])
        for present in (True, False):
            for document in cms_documents(self, cms_message('authenticated_data', recipients=cms_recipients()[:1],
                    signed_attrs=[row] if present else None, unsigned_attrs=[row] if present else None)):
                body = document['content']
                self.assertEqual(body['mac_algorithm']['algorithm'].native, 'sha256')
                self.assertEqual(body['digest_algorithm']['algorithm'].native, 'sha256')
                self.assertEqual(body['mac'].native, b'\x88\x00\xbb')
                for field in ('auth_attrs', 'unauth_attrs'):
                    if present:
                        self.assertEqual(body[field][0]['type'].native, 'message_digest')
                        self.assertEqual(body[field][0]['values'].native, [b'\x09\x00'])
                    else:
                        self.assertIsNone(body[field].native)
        for document in cms_documents(self, cms_message('digested_data')):
            self.assertEqual(document['content']['digest_algorithm']['algorithm'].native, 'sha256')
            self.assertEqual(document['content']['digest'].native, b'\xdd\x00\x99')

    def test_f14_t03(self):
        for kind in ('encrypted_data', 'enveloped_data', 'signed_and_enveloped_data', 'authenticated_enveloped_data'):
            for document in cms_documents(self, cms_message(kind, recipients=cms_recipients())):
                body = document['content']
                field = 'auth_encrypted_content_info' if kind == 'authenticated_enveloped_data' else 'encrypted_content_info'
                encrypted = body[field]
                self.assertEqual(encrypted['content_type'].native, 'data')
                self.assertEqual(encrypted['content_encryption_algorithm']['algorithm'].native, 'aes128_cbc')
                self.assertEqual(encrypted['content_encryption_algorithm']['parameters'].native, CMS_IV)
                self.assertEqual(encrypted['encrypted_content'].native, CMS_CIPHER)
                if kind == 'authenticated_enveloped_data':
                    self.assertEqual(body['mac'].native, b'\x10\x00\x20')
                if kind == 'encrypted_data':
                    continue
                recipients = body['recipient_infos']
                self.assertEqual(len(recipients), 6)
                self.assertEqual({r.name for r in recipients}, {'ktri', 'kari', 'kekri', 'pwri', 'ori'})
                self.assertEqual({r.chosen['rid'].name for r in recipients if r.name == 'ktri'},
                    {'issuer_and_serial_number', 'subject_key_identifier'})
                for recipient in recipients:
                    value = recipient.chosen
                    if recipient.name == 'ori':
                        self.assertEqual(value['ori_type'].dotted, '1.2.3.14.9')
                        self.assertEqual(value['ori_value'].native, 'external recipient')
                        continue
                    algorithm = value['key_encryption_algorithm']
                    self.assertEqual(algorithm['algorithm'].native, 'rsaes_pkcs1v15' if recipient.name == 'ktri' else 'aes128_wrap')
                    if recipient.name == 'ktri':
                        self.assertEqual(value['encrypted_key'].native, b'\x91\x00\xf2')
                        rid = value['rid']
                        if rid.name == 'subject_key_identifier':
                            self.assertEqual(rid.chosen.native, b'\x12\x00\x34')
                        else:
                            self.assertEqual(rid.name, 'issuer_and_serial_number')
                            self.assertEqual(rid.chosen['serial_number'].native, 459)
                            self.assertEqual(name_groups(rid.chosen['issuer']), [[('2.5.4.3', 'Recipient CA')]])
                    elif recipient.name == 'kari':
                        self.assertEqual(value['originator'].name, 'subject_key_identifier')
                        self.assertEqual(value['originator'].chosen.native, b'\x03\x00\x04')
                        self.assertEqual(value['ukm'].native, b'\x77\x88')
                        self.assertEqual(len(value['recipient_encrypted_keys']), 1)
                        key = value['recipient_encrypted_keys'][0]
                        self.assertEqual(key['rid'].name, 'r_key_id')
                        self.assertEqual(key['rid'].chosen.native, {'subject_key_identifier': b'\x55\x66', 'date': CERT_START, 'other': None})
                        self.assertEqual(key['encrypted_key'].native, b'\xa0\xb1')
                    elif recipient.name == 'kekri':
                        self.assertEqual(value['kekid'].native, {'key_identifier': b'\x11\x22', 'date': CERT_START,
                            'other': {'key_attr_id': '1.2.3.14', 'key_attr': 'key owner'}})
                        self.assertEqual(value['encrypted_key'].native, b'\xc2\xd3')
                    else:
                        self.assertEqual(value['key_derivation_algorithm']['algorithm'].native, 'pbkdf2')
                        params = value['key_derivation_algorithm']['parameters']
                        self.assertEqual(params['salt'].chosen.native, b'\x13\x24\x35')
                        self.assertEqual(params['iteration_count'].native, 3072)
                        self.assertEqual(value['encrypted_key'].native, b'\xe4\xf5')

    def test_f14_t04(self):
        for generalized_time in (False, True):
            rows = cms_attribute_rows(generalized_time)
            for document in cms_documents(self, cms_bound_attributes(rows)):
                attributes = document['content']['signer_infos'][0]['signed_attrs']
                by_name = {a['type'].native: a for a in attributes}
                self.assertEqual(set(by_name), {r[0]['type'] for r in rows})
                for fields, tree, expected in rows:
                    name = fields['type']
                    attribute = by_name[name]
                    self.assertEqual(attribute.dump(), cms_reference(tree))
                    if expected is not None:
                        self.assertEqual(attribute['values'].native, expected)
                    elif name == '1.2.3.14.100':
                        self.assertEqual(attribute['type'].dotted, name)
                        self.assertEqual({v.dump() for v in attribute['values']},
                            {cms_reference(['int', 751]), cms_reference(['utf8', 'open value'])})
                    else:
                        self.assertEqual(len(attribute['values']), 1)
                        token = attribute['values'][0]
                        self.assertEqual(token['content_type'].native, 'signed_data')
                        self.assertEqual(token['content']['encap_content_info']['content'].native, name.encode('ascii'))
                        self.assertEqual(token['content']['signer_infos'][0]['sid'].chosen.native, b'\xaa\x00\x99')

    def test_f14_t05(self):
        for request in (False, True):
            certificates = cms_certificate_choices()
            revocations = cms_revocation_choices(request)
            # New documents are checked against canonical independent encodings.
            # The v1 certificate uses a preserved BER default to avoid the known
            # original reader bug; do not require new encoders to retain that default.
            cms_documents(self, cms_message('signed_data',
                certificates=[row for row in certificates if row[0] != 'v1_attr_cert'], revocations=revocations))
            for document in cms_documents(self, cms_message('signed_data',
                    certificates=certificates, revocations=revocations), construct=False):
                choices = {c.name: c.chosen for c in document['content']['certificates']}
                self.assertEqual(set(choices), {'certificate', 'extended_certificate', 'v1_attr_cert', 'v2_attr_cert', 'other'})
                self.assertEqual(choices['certificate'].dump(), certificate_document()[1])
                extended = choices['extended_certificate']
                self.assertEqual(extended['extended_certificate_info']['version'].native, 0)
                self.assertEqual(extended['extended_certificate_info']['certificate'].dump(), certificate_document()[1])
                self.assertEqual(extended['extended_certificate_info']['attributes'][0]['type'].dotted, '1.2.3.98')
                self.assertEqual(extended['extended_certificate_info']['attributes'][0]['values'][0].native, 17)
                self.assertEqual(extended['signature'].native, b'\x27\x00\x81')
                for name, version in (('v1_attr_cert', 'v1'), ('v2_attr_cert', 'v2')):
                    cert = choices[name]
                    self.assertEqual(cert['ac_info']['version'].native, version)
                    self.assertEqual(cert['ac_info']['serial_number'].native, 832)
                    self.assertEqual(cert['signature'].native, b'\x97\x00\xff')
                self.assertEqual(choices['v1_attr_cert']['ac_info']['subject'].name, 'subject_name')
                self.assertEqual(choices['v1_attr_cert']['ac_info']['subject'].chosen.native, ['holder@example.org'])
                self.assertEqual(choices['v1_attr_cert']['ac_info']['issuer'].native, ['issuer.example.org'])
                self.assertEqual(choices['v1_attr_cert']['ac_info']['attributes'][0]['values'][0].native, 'v1 attribute')
                self.assertEqual(choices['other']['other_cert_format'].dotted, '1.2.3.14.7')
                self.assertEqual(choices['other']['other_cert'].native, b'other certificate\x00')
                revs = document['content']['crls']
                self.assertEqual(len(revs), 4)
                self.assertEqual(sum(r.name == 'crl' for r in revs), 1)
                others = {}
                for rev in revs:
                    if rev.name == 'crl':
                        self.assertEqual(rev.chosen.dump(), crl_document()[1])
                    else:
                        self.assertEqual(rev.name, 'other')
                        others[rev.chosen['other_rev_info_format'].native] = rev.chosen['other_rev_info']
                self.assertEqual(set(others), {'ocsp_response', 'scvp', '1.2.3.14.8'})
                self.assertEqual(others['ocsp_response'].dump(), ocsp_response_document()[1])
                self.assertEqual(others['ocsp_response']['response_status'].native, 'successful')
                scvp = others['scvp']
                self.assertEqual(scvp['response']['content_type'].native, 'data')
                self.assertEqual(scvp['response']['content'].native, b'SCVP response\xff')
                if request:
                    self.assertEqual(scvp['request']['content_type'].native, 'data')
                    self.assertEqual(scvp['request']['content'].native, b'SCVP request\x00')
                else:
                    self.assertIsNone(scvp['request'].native)
                self.assertEqual(others['1.2.3.14.8'].native, 'other revocation')

    def test_f14_t06(self):
        for full in (False, True):
            choice, rows = cms_attribute_certificate(full)
            for document in cms_documents(self, cms_message('signed_data', certificates=[choice])):
                selected = document['content']['certificates'][0]
                self.assertEqual(selected.name, 'v2_attr_cert')
                cert = selected.chosen
                info = cert['ac_info']
                self.assertEqual(info['holder']['entity_name'].native, ['holder@example.org'])
                self.assertEqual(info['issuer'].name, 'v2_form')
                self.assertEqual(info['issuer'].chosen['issuer_name'].native, ['issuer.example.org'])
                self.assertEqual(info['att_cert_validity_period'].native,
                    {'not_before_time': CERT_START, 'not_after_time': CERT_END})
                self.assertEqual(info['signature']['algorithm'].native, 'sha256_rsa')
                self.assertEqual(cert['signature_algorithm']['algorithm'].native, 'sha256_rsa')
                self.assertEqual(cert['signature'].native, b'\x97\x00\xff')
                attrs = {a['type'].native: a for a in info['attributes']}
                self.assertEqual(set(attrs), {r[0]['type'] for r in rows})
                for fields, tree, expected in rows:
                    attribute = attrs[fields['type']]
                    self.assertEqual(attribute['values'].native, expected)
                    self.assertEqual(attribute.dump(), cms_reference(tree))

    def test_f14_t07(self):
        for payload in (b'', b'a different CMS message\x00\xff', bytes(range(256)) * 31):
            for document in cms_documents(self, cms_message('compressed_data', payload)):
                body = document['content']
                self.assertEqual(body['compression_algorithm']['algorithm'].native, 'zlib')
                self.assertEqual(body.decompressed, payload)
        # Corrupt bytes still have valid ASN.1 framing; refusal belongs to decompression.
        for compressed in cms_corrupt_inputs():
            fields = {'version': 'v0', 'compression_algorithm': {'algorithm': 'zlib'},
                'encap_content_info': {'content_type': 'data', 'content': compressed}}
            tree = cert_seq(['int', 0], cert_seq(['oid', '1.2.840.113549.1.9.16.3.8']),
                cert_seq(['oid', '1.2.840.113549.1.7.1'], cert_explicit(0, ['octets', compressed.hex()])))
            fields, tree = cms_wrap('compressed_data', fields, tree)
            # Include lazy property access in the captured operation.
            result = observe(ContentInfo.load, args=(cms_reference(tree),),
                consumers=(lambda value: value['content'].decompressed,), expected_exceptions=(zlib.error,))
            self.assertIsInstance(result.error, zlib.error)
