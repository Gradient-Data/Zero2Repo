# feature: F11
"""Acceptance tests for CRL documents and entry-local revocation data."""
import unittest
from cobaltform.crl import CertificateList
from _helpers import standard_tools
from F08_helpers import grouped_name, name_groups
from F09_helpers import (
    CERT_START, CERT_END, cert_seq, cert_set, cert_implicit, cert_explicit,
    cert_name, cert_uri, cert_point, cert_extension,
)
from F11_helpers import (
    CRL_ENTRIES, CRL_REASONS, crl_document, crl_documents, crl_reference,
    crl_wide_rows, crl_entry_rows, crl_access, crl_issuer_row, crl_interpreted_value,
)


class TestCRL(unittest.TestCase):
    def test_f11_t01(self):
        # Explicit v1 is not the same as an absent version in a CRL.
        scenarios = [dict(version='v1'), dict(version='v2', ec=True),
                     dict(version=None, entries=None, next_update=False),
                     dict(entries=(), rows=[])]
        for options in scenarios:
            version = options.get('version', 'v2')
            entries = options.get('entries', CRL_ENTRIES)
            for document in crl_documents(self, **options):
                tbs = document['tbs_cert_list']
                self.assertEqual(tbs['version'].native, version)
                if version is None:
                    self.assertEqual(tbs['version'].dump(), b'')
                self.assertEqual(name_groups(document.issuer), [[('2.5.4.3', 'Revocation Authority')]])
                self.assertEqual(name_groups(tbs['issuer']), name_groups(document.issuer))
                self.assertEqual(tbs['this_update'].native, CERT_START)
                self.assertEqual(tbs['next_update'].native, CERT_END if options.get('next_update', True) else None)
                self.assertEqual(document.signature, b'\x00\x81\xfe')
                self.assertEqual(document['signature'].native, b'\x00\x81\xfe')
                for algorithm in (tbs['signature'], document['signature_algorithm']):
                    self.assertEqual(algorithm['algorithm'].native,
                                     'sha384_ecdsa' if options.get('ec') else 'sha256_rsa')
                actual = tbs['revoked_certificates']
                self.assertEqual(actual.native is None, entries is None)
                if entries is not None:
                    self.assertEqual([(entry['user_certificate'].native, entry['revocation_date'].native)
                                      for entry in actual],
                                     [(serial, CERT_END if general else CERT_START) for serial, general, rows in entries])
                    for entry in actual:
                        self.assertIsNone(entry['crl_entry_extensions'].native)
                self.assertEqual(tbs['crl_extensions'].native, [] if 'rows' in options else None)
                # Changes are checked against independent DER, after an earlier dump.
                tbs['issuer'] = grouped_name([[('common_name', 'Replacement Authority')]])
                document['signature'] = b'\xff\x00\x19\x80'
                if entries:
                    actual[0]['user_certificate'] = 811
                    actual[0]['revocation_date'] = {'general_time': CERT_END}
                changed = dict(options, issuer='Replacement Authority', signature=b'\xff\x00\x19\x80')
                if entries:
                    changed['entries'] = ((811, True, None),) + tuple(entries[1:])
                _, wire = crl_document(**changed)
                self.assertEqual(document.dump(), wire)
                reread = CertificateList.load(document.dump())
                self.assertEqual(name_groups(reread.issuer), [[('2.5.4.3', 'Replacement Authority')]])
                if entries:
                    self.assertEqual(reread['tbs_cert_list']['revoked_certificates'][0]['user_certificate'].native, 811)
                    self.assertEqual(reread['tbs_cert_list']['revoked_certificates'][0]['revocation_date'].native, CERT_END)

    def test_f11_t02(self):
        wide = crl_wide_rows()
        unknown = cert_extension('1.2.3.200.81', '1.2.3.200.81',
                                 cert_seq(['utf8', 'unregistered'], ['int', 281]), None, True)
        entry_specs = tuple((100 + number, False, crl_entry_rows(number, name) + [unknown])
                            for number, name in CRL_REASONS)
        for document in crl_documents(self, rows=wide + [unknown], entries=entry_specs):
            extensions = document['tbs_cert_list']['crl_extensions']
            self.assertEqual(len(extensions), len(wide) + 1)
            actual = {ext['extn_id'].dotted: ext for ext in extensions}
            self.assertEqual(set(actual), {row[0] for row in wide + [unknown]})
            for identity, name, tree, expected, critical in wide:
                extension = actual[identity]
                self.assertEqual(extension['extn_id'].native, name)
                self.assertEqual(extension['critical'].native, critical)
                self.assertEqual(extension['extn_value'].contents, crl_reference(tree))
                self.assertEqual(crl_interpreted_value(extension['extn_value'].parsed, tree), expected)
                self.assertEqual(crl_interpreted_value(getattr(document, name + '_value'), tree), expected)
            self.assertEqual(document.authority_key_identifier, b'\x00\x12\xff')
            self.assertEqual(document.critical_extensions, {row[1] for row in wide + [unknown] if row[4]})
            self.assertEqual(actual[unknown[0]]['extn_id'].native, unknown[0])
            self.assertTrue(actual[unknown[0]]['critical'].native)
            self.assertEqual(actual[unknown[0]]['extn_value'].native, crl_reference(unknown[2]))
            entries = document['tbs_cert_list']['revoked_certificates']
            self.assertEqual(len(entries), len(CRL_REASONS))
            for entry, (number, reason) in zip(entries, CRL_REASONS):
                rows = crl_entry_rows(number, reason)
                extensions = entry['crl_entry_extensions']
                self.assertEqual(len(extensions), len(rows) + 1)
                actual = {ext['extn_id'].dotted: ext for ext in extensions}
                self.assertEqual(set(actual), {row[0] for row in rows + [unknown]})
                for identity, name, tree, expected, critical in rows:
                    extension = actual[identity]
                    self.assertEqual(extension['extn_id'].native, name)
                    self.assertEqual(extension['critical'].native, critical)
                    self.assertEqual(extension['extn_value'].contents, crl_reference(tree))
                    self.assertEqual(crl_interpreted_value(extension['extn_value'].parsed, tree), expected)
                    if name != 'hold_instruction_code':
                        self.assertEqual(crl_interpreted_value(getattr(entry, name + '_value'), tree), expected)
                self.assertEqual(entry.critical_extensions, {'certificate_issuer', unknown[0]})
                self.assertEqual(actual[unknown[0]]['extn_id'].native, unknown[0])
                self.assertTrue(actual[unknown[0]]['critical'].native)
                self.assertEqual(actual[unknown[0]]['extn_value'].native, crl_reference(unknown[2]))
        # Absent and explicitly empty extension collections are both supported.
        for rows in (None, []):
            for document in crl_documents(self, rows=rows, entries=((91, False, rows),)):
                self.assertEqual(document['tbs_cert_list']['crl_extensions'].native, rows)
                self.assertEqual(document.critical_extensions, set())
                for row in wide:
                    self.assertIsNone(getattr(document, row[1] + '_value'))
                self.assertIsNone(document.authority_key_identifier)
                entry = document['tbs_cert_list']['revoked_certificates'][0]
                self.assertEqual(entry['crl_entry_extensions'].native, rows)
                self.assertEqual(entry.critical_extensions, set())
                for name in ('crl_reason_value', 'invalidity_date_value', 'certificate_issuer_value'):
                    self.assertIsNone(getattr(entry, name))

    def test_f11_t03(self):
        aia = cert_extension('1.3.6.1.5.5.7.1.1', 'authority_information_access', cert_seq(
            crl_access('1.3.6.1.5.5.7.48.2', cert_uri('http://issuer.example.org/one')),
            crl_access('1.3.6.1.5.5.7.48.2', cert_uri('http://issuer.example.org/two')),
            crl_access('1.3.6.1.5.5.7.48.1', cert_uri('http://ocsp.example.org/')),
            crl_access('1.3.6.1.5.5.7.48.2', cert_uri('https://issuer.example.org/secure')),
            crl_access('1.3.6.1.5.5.7.48.2', cert_uri('ldap://issuer.example.org/entry')),
            crl_access('1.3.6.1.5.5.7.48.2', cert_implicit(2, ['ia5', 'issuer.example.org']))), None)
        full_http = cert_point('http://delta.example.org/one')
        full_ldap = cert_seq(cert_explicit(0, cert_implicit(0, cert_seq(
            cert_implicit(2, ['ia5', 'delta.example.org']), cert_uri('ldap://delta.example.org/two')))))
        relative = cert_seq(cert_explicit(0, cert_implicit(1, cert_set(
            cert_seq(['oid', '2.5.4.3'], ['utf8', 'Relative Delta'])))))
        dns_only = cert_seq(cert_explicit(0, cert_implicit(0, cert_seq(
            cert_implicit(2, ['ia5', 'delta.example.org'])))))
        freshest = cert_extension('2.5.29.46', 'freshest_crl',
                                 cert_seq(relative, full_http, dns_only, full_ldap), None)
        for document in crl_documents(self, rows=[aia, freshest]):
            self.assertCountEqual(document.issuer_cert_urls,
                                  ['http://issuer.example.org/one', 'http://issuer.example.org/two'])
            points = document.delta_crl_distribution_points
            self.assertEqual(len(points), 2)
            self.assertCountEqual([point['distribution_point'].name for point in points], ['full_name', 'full_name'])
            self.assertCountEqual([point.native for point in points], [
                {'distribution_point': ['http://delta.example.org/one'], 'reasons': None, 'crl_issuer': None},
                {'distribution_point': ['delta.example.org', 'ldap://delta.example.org/two'], 'reasons': None, 'crl_issuer': None}])
        excluded_aia = cert_extension('1.3.6.1.5.5.7.1.1', 'authority_information_access', cert_seq(
            crl_access('1.3.6.1.5.5.7.48.1', cert_uri('http://ocsp.example.org/')),
            crl_access('1.3.6.1.5.5.7.48.2', cert_uri('https://issuer.example.org/secure'))), None)
        excluded_points = cert_extension('2.5.29.46', 'freshest_crl', cert_seq(relative, dns_only), None)
        for rows in (None, [excluded_aia, excluded_points]):
            for document in crl_documents(self, rows=rows):
                self.assertEqual(document.issuer_cert_urls, [])
                self.assertEqual(document.delta_crl_distribution_points, [])

    def test_f11_t04(self):
        hashes = standard_tools().hashlib
        # Separate fresh documents differ only in the supplied signature.
        for signature in (b'\x00\x81\xfe', b'\x00\x81\xff\x22'):
            _, wire = crl_document(signature=signature)
            for document in crl_documents(self, signature=signature):
                self.assertEqual(document.sha1, hashes.sha1(wire).digest())
                self.assertEqual(document.sha256, hashes.sha256(wire).digest())

    def test_f11_t05(self):
        names = cert_seq(cert_implicit(2, ['ia5', 'entry.example.org']),
                         cert_explicit(4, cert_name('First Entry Issuer')),
                         cert_explicit(4, cert_name('Second Entry Issuer')))
        no_directory = cert_seq(cert_uri('http://entry.example.org/issuer'),
                                cert_implicit(2, ['ia5', 'entry.example.org']))
        specs = ((13, False, [crl_issuer_row(names)]), (14, False, None),
                 (15, False, [crl_issuer_row(no_directory)]), (16, False, []))
        for document in crl_documents(self, entries=specs):
            first, absent, nondirectory, empty = document['tbs_cert_list']['revoked_certificates']
            self.assertEqual([name.name for name in first.certificate_issuer_value],
                             ['dns_name', 'directory_name', 'directory_name'])
            self.assertEqual(name_groups(first.issuer_name), [[('2.5.4.3', 'First Entry Issuer')]])
            self.assertIsNone(absent.certificate_issuer_value)
            self.assertIsNone(absent.issuer_name)
            self.assertEqual([name.native for name in nondirectory.certificate_issuer_value],
                             ['http://entry.example.org/issuer', 'entry.example.org'])
            self.assertIsNone(nondirectory.issuer_name)
            self.assertIsNone(empty.certificate_issuer_value)
            self.assertIsNone(empty.issuer_name)
