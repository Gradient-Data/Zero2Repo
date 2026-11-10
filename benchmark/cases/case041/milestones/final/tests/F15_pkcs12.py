# feature: F15
"""Acceptance tests for PKCS#12 containers, typed bags and attributes."""
import unittest
from cobaltform.pkcs12 import AuthenticatedSafe, Pfx, SafeContents
from F07_helpers import rsa_components
from F09_helpers import cert_seq, certificate_document
from F11_helpers import crl_document
from F14_helpers import cms_message, CMS_CIPHER, CMS_IV
from F15_helpers import (
    p12_reference, p12_container, p12_documents, p12_bag, p12_secret,
    p12_safe_container, p12_bound_bags, p12_bag_rows, p12_attributes,
)


class TestPKCS12(unittest.TestCase):
    def test_f15_t01(self):
        plain = cms_message('data', p12_reference(cert_seq(p12_secret()[1])))
        encrypted = cms_message('encrypted_data')
        # Omitted, defaulted and explicit MAC iterations are separate states.
        for mac in (None, (None, b'\x00salt\xff', b'\xa1digest\x00'),
                    (2048, b'\xffother salt', b'\x00other digest')):
            entries = [encrypted, plain, cms_message('data', b'\x30\x00')]
            self.assertEqual(AuthenticatedSafe([fields for fields, tree in entries]).dump(),
                p12_reference(cert_seq(*(tree for fields, tree in entries))))
            parts = p12_container(entries, mac)
            for document in p12_documents(self, parts):
                self.assertEqual(document['version'].native, 'v3')
                self.assertEqual(document['auth_safe']['content_type'].native, 'data')
                self.assertEqual(document['auth_safe']['content'].native,
                    p12_reference(cert_seq(*(tree for fields, tree in entries))))
                safe = document.authenticated_safe
                self.assertEqual([e['content_type'].native for e in safe], ['encrypted_data', 'data', 'data'])
                body = safe[0]['content']
                self.assertEqual(body['version'].native, 'v0')
                info = body['encrypted_content_info']
                self.assertEqual(info['content_type'].native, 'data')
                self.assertEqual(info['content_encryption_algorithm']['algorithm'].native, 'aes128_cbc')
                self.assertEqual(info['content_encryption_algorithm']['parameters'].native, CMS_IV)
                self.assertEqual(info['encrypted_content'].native, CMS_CIPHER)
                self.assertEqual(safe[1]['content'].native, plain[0]['content'])
                self.assertEqual(safe[2]['content'].native, b'\x30\x00')
                if mac is None:
                    self.assertIsNone(document['mac_data'].native)
                else:
                    count, salt, digest = mac
                    self.assertEqual(document['mac_data']['iterations'].native, 1 if count is None else count)
                    self.assertEqual(document['mac_data']['mac_salt'].native, salt)
                    self.assertEqual(document['mac_data']['mac']['digest_algorithm']['algorithm'].native, 'sha256')
                    self.assertEqual(document['mac_data']['mac']['digest'].native, digest)
                    document['mac_data']['iterations'] = 4096
                    document['mac_data']['mac_salt'] = b'changed salt\x00'
                    self.assertEqual(document.dump(), p12_reference(p12_container(entries,
                        (4096, b'changed salt\x00', digest))[1]))
                # Edit the bound outer content; check bytes independently, then
                # read a newly loaded document without prescribing cache policy.
                changed = [plain]
                document['auth_safe'] = p12_container(changed)[0]['auth_safe']
                changed_mac = None if mac is None else (4096, b'changed salt\x00', mac[2])
                self.assertEqual(document.dump(), p12_reference(p12_container(changed, changed_mac)[1]))
                self.assertEqual(len(Pfx.load(document.dump()).authenticated_safe), 1)
        for document in p12_documents(self, p12_container([])):
            self.assertEqual(len(document.authenticated_safe), 0)

    def test_f15_t02(self):
        rows = p12_bag_rows()
        self.assertEqual(SafeContents([fields for fields, tree in rows]).dump(),
            p12_reference(cert_seq(*(tree for fields, tree in rows))))
        _, cert_wire, _ = certificate_document()
        _, crl_wire = crl_document()
        for document in p12_documents(self, p12_safe_container(rows)):
            bags = p12_bound_bags(document)
            self.assertEqual([bag['bag_id'].native for bag in bags],
                ['key_bag', 'pkcs8_shrouded_key_bag', 'cert_bag', 'cert_bag', 'crl_bag', 'secret_bag', 'safe_contents'])
            self.assertEqual(bags.dump(), p12_reference(cert_seq(*(tree for fields, tree in rows))))
            key = bags[0]['bag_value']
            self.assertEqual(key['version'].native, 0)
            self.assertEqual(key['private_key_algorithm']['algorithm'].native, 'rsa')
            for field, expected in rsa_components().items():
                self.assertEqual(key['private_key'].parsed[field].native, expected)
            encrypted = bags[1]['bag_value']
            self.assertEqual(encrypted['encryption_algorithm']['algorithm'].native, 'aes256_cbc')
            self.assertEqual(encrypted['encryption_algorithm']['parameters'].native, b'0123456789abcdef')
            self.assertEqual(encrypted['encrypted_data'].native, b'\x83\x00encrypted key\xff')
            cert = bags[2]['bag_value']
            self.assertEqual(cert['cert_id'].native, 'x509')
            self.assertEqual(cert['cert_value'].parsed.dump(), cert_wire)
            self.assertEqual(cert['cert_value'].parsed['tbs_certificate']['serial_number'].native, 793)
            sdsi = bags[3]['bag_value']
            self.assertEqual(sdsi['cert_id'].native, 'sdsi')
            self.assertEqual(sdsi['cert_value'].native, b'opaque SDSI\x00\xffpayload')
            crl = bags[4]['bag_value']
            self.assertEqual(crl['crl_id'].native, '1.2.840.113549.1.9.23.1')
            self.assertEqual(crl['crl_value'].native, crl_wire)
            secret = bags[5]['bag_value']
            self.assertEqual(secret['secret_type_id'].native, '1.2.3.15.5')
            self.assertEqual(secret['secret_value'].native, b'private secret\x00\xff')
            nested = bags[6]['bag_value']
            self.assertEqual([b['bag_id'].native for b in nested], ['safe_contents', 'secret_bag'])
            leaf = nested[0]['bag_value']
            self.assertEqual(len(leaf), 1)
            self.assertEqual(leaf[0]['bag_id'].native, 'secret_bag')
            self.assertEqual(leaf[0]['bag_value']['secret_type_id'].native, '1.2.3.15.5')
            self.assertEqual(leaf[0]['bag_value']['secret_value'].native, b'nested secret\x80\x00')
            self.assertEqual(nested[1]['bag_value']['secret_value'].native, b'sibling')
        for document in p12_documents(self, p12_safe_container([])):
            self.assertEqual(len(p12_bound_bags(document)), 0)

    def test_f15_t03(self):
        attributes = p12_attributes()
        base_fields, base_tree = p12_secret()
        # Same bag value with omitted, explicitly empty and populated attributes.
        rows = [p12_bag('secret_bag', base_fields['bag_value'], base_tree[1][1][2], state)
                for state in (None, [], attributes)]
        self.assertEqual(SafeContents([fields for fields, tree in rows]).dump(),
            p12_reference(cert_seq(*(tree for fields, tree in rows))))
        for document in p12_documents(self, p12_safe_container(rows)):
            bags = p12_bound_bags(document)
            self.assertIsNone(bags[0]['bag_attributes'].native)
            self.assertEqual(bags[1]['bag_attributes'].native, [])
            actual = {a['type'].native: a for a in bags[2]['bag_attributes']}
            self.assertEqual(set(actual), {row[0]['type'] for row in attributes})
            self.assertEqual(actual['friendly_name']['values'].native, ['Key \u4e3b\u4eba'])
            self.assertEqual(actual['local_key_id']['values'].native, [b'\x00\x80\xff'])
            self.assertEqual(set(actual['trusted_key_usage']['values'].native), {'any_extended_key_usage', 'server_auth'})
            for fields, tree in attributes:
                attribute = actual[fields['type']]
                self.assertEqual(attribute['type'].dotted, tree[1][0][1])
                self.assertEqual(attribute.dump(), p12_reference(tree))
            microsoft = actual['microsoft_local_machine_keyset']['values']
            self.assertEqual([v.native for v in microsoft], [None])
            unknown = actual['1.2.3.15.99']['values']
            self.assertEqual({v.dump() for v in unknown},
                {p12_reference(t) for t in (['utf8', 'open text'], ['int', 423], ['octets', 'ff00'])})
            self.assertEqual(bags.dump(), p12_reference(cert_seq(*(tree for fields, tree in rows))))


if __name__ == '__main__':
    unittest.main()
