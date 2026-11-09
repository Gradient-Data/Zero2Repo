# feature: F17
"""Acceptance checks for PDF certificate metadata and CMS archival material."""
import unittest
from cobaltform.cms import ContentInfo
from cobaltform.x509 import Certificate
from F17_helpers import pdf_reference, pdf_certificate, pdf_archival_parts


class TestPDF(unittest.TestCase):
    def test_f17_t01(self):
        # Importing PDF enables interpretation; only bound results prove it works.
        for auth in (None, False, True):
            created, tree, rows, version, location = pdf_certificate(auth)
            wire = pdf_reference(tree)
            for certificate in (created, Certificate.load(wire)):
                self.assertEqual(certificate.dump(), wire)
                extensions = {e['extn_id'].native: e for e in certificate['tbs_certificate']['extensions']}
                self.assertEqual(set(extensions), {r[0] for r in rows})
                for name, oid, value, value_tree in rows:
                    extension = extensions[name]
                    self.assertEqual(extension['extn_id'].dotted, oid)
                    self.assertEqual(extension['extn_value'].parsed.dump(), pdf_reference(value_tree))
                self.assertEqual(extensions['adobe_archive_rev_info']['extn_value'].parsed.native,
                                 {'version': version + 1})
                timestamp = extensions['adobe_timestamp']['extn_value'].parsed
                self.assertEqual(timestamp['version'].native, version)
                self.assertEqual(timestamp['location'].name, 'uniform_resource_identifier')
                self.assertEqual(timestamp['location'].chosen.native, location)
                self.assertEqual(timestamp['requires_auth'].native, auth is True)
                self.assertIsNone(extensions['adobe_ppklite_credential']['extn_value'].parsed.native)
                self.assertEqual(extensions['extended_key_usage']['extn_value'].parsed.native, ['pdf_signing'])

    def test_f17_t02(self):
        # Singles establish independent presence/absence; together establishes
        # coexistence and multiple members. Empty collections differ from absent.
        names = ('crl', 'ocsp', 'other_rev_info')
        scenarios = [((), False)] + [((name,), False) for name in names] + [(names, False), (names, True)]
        for present, empty in scenarios:
            (fields, tree), crls, responses, others = pdf_archival_parts(present, empty)
            wire = pdf_reference(tree)
            for message in (ContentInfo(fields), ContentInfo.load(wire)):
                self.assertEqual(message.dump(), wire)
                attribute = message['content']['signer_infos'][0]['signed_attrs'][0]
                self.assertEqual(attribute['type'].native, 'adobe_revocation_info_archival')
                self.assertEqual(attribute['type'].dotted, '1.2.840.113583.1.1.8')
                self.assertEqual(len(attribute['values']), 1)
                archival = attribute['values'][0]
                for name in names:
                    collection = archival[name]
                    if name not in present:
                        self.assertIsNone(collection.native)
                    elif empty:
                        self.assertEqual(collection.native, [])
                    elif name in ('crl', 'ocsp'):
                        expected = crls if name == 'crl' else responses
                        self.assertEqual([document.dump() for document in collection], [row[1] for row in expected])
                        if name == 'crl':
                            self.assertEqual([document['tbs_cert_list']['version'].native for document in collection], ['v2', 'v1'])
                        else:
                            self.assertEqual([document['response_status'].native for document in collection], ['successful', 'successful'])
                    else:
                        self.assertEqual(collection.native, others)
