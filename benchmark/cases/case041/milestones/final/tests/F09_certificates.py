# feature: F09
"""Acceptance tests of certificate values, extensions and derived metadata."""
import unittest
from cobaltform.algos import AnyAlgorithmIdentifier
from cobaltform.core import Integer
from cobaltform.x509 import (
    Certificate, CertificateAux, SubjectDirectoryAttribute, SubjectDirectoryAttributes,
    TrustedCertificate,
)
from _helpers import standard_tools
from F08_helpers import name_groups
from F09_helpers import (
    CERT_START, CERT_END, cert_reference, cert_seq, cert_set, cert_implicit,
    cert_explicit, cert_algorithm, certificate_document, cert_documents,
    cert_extension, cert_extension_rows, cert_uri, cert_point, cert_directory_row,
)


class TestCertificate(unittest.TestCase):
    def test_f09_t01(self):
        for version, unique in ((None, False), ('v1', False), ('v2', True), ('v3', True)):
            rows = cert_extension_rows()[1:2] if version == 'v3' else ()
            ec = version == 'v3'
            for document in cert_documents(self, version=version, unique=unique, rows=rows, ec=ec):
                tbs = document['tbs_certificate']
                self.assertEqual(tbs['version'].native, version or 'v1')
                self.assertEqual(tbs['serial_number'].native, 793)
                self.assertEqual(document.serial_number, 793)
                self.assertEqual(name_groups(document.issuer), [[('2.5.4.3', 'Authority')]])
                self.assertEqual(name_groups(document.subject), [[('2.5.4.3', 'Receiver')]])
                self.assertEqual(document.not_valid_before, CERT_START)
                self.assertEqual(document.not_valid_after, CERT_END)
                self.assertEqual(tbs['validity']['not_before'].name, 'utc_time')
                self.assertEqual(tbs['validity']['not_after'].name, 'general_time')
                self.assertEqual(document.public_key['algorithm']['algorithm'].native, 'ec' if ec else 'rsa')
                if ec:
                    self.assertEqual(document.public_key['algorithm']['parameters'].native, 'secp256r1')
                    self.assertEqual(document.public_key['public_key'].native, b'\x04' + bytes(range(1, 65)))
                else:
                    self.assertEqual(document.public_key['public_key'].parsed.native,
                                     {'modulus': 3233, 'public_exponent': 17})
                for algorithm in (tbs['signature'], document['signature_algorithm']):
                    self.assertEqual(algorithm['algorithm'].native, 'sha384_ecdsa' if ec else 'sha256_rsa')
                self.assertEqual(document.signature_algo, 'ecdsa' if ec else 'rsassa_pkcs1v15')
                self.assertEqual(document.hash_algo, 'sha384' if ec else 'sha256')
                self.assertEqual(document.signature, b'\x01\x80\xff')
                self.assertEqual(document['signature_value'].native, b'\x01\x80\xff')
                self.assertEqual(tbs['issuer_unique_id'].native, b'\xa1\x00' if unique else None)
                self.assertEqual(tbs['subject_unique_id'].native, b'\x80\x02' if unique else None)
                self.assertEqual(tbs['extensions'].native is None, not bool(rows))
                # Modification is checked against a second independent encoding.
                tbs['serial_number'] = 794
                document['signature_value'] = b'\x00\x11\x22'
                _, expected, _ = certificate_document(version=version, unique=unique, rows=rows,
                    serial=794, signature=b'\x00\x11\x22', ec=ec)
                self.assertEqual(document.dump(), expected)

    def test_f09_t02(self):
        rows = cert_extension_rows()
        unknown = cert_extension('1.2.3.200.19', '1.2.3.200.19',
                                 cert_seq(['utf8', 'opaque'], ['int', 47]), None, True)
        for document in cert_documents(self, rows=rows + [unknown]):
            extensions = document['tbs_certificate']['extensions']
            self.assertEqual(len(extensions), len(rows) + 1)
            actual = {e['extn_id'].dotted: e for e in extensions}
            self.assertEqual(set(actual), {r[0] for r in rows + [unknown]})
            for identity, name, tree, expected, critical in rows:
                extension = actual[identity]
                self.assertEqual(extension['extn_id'].native, name)
                self.assertEqual(extension['critical'].native, critical)
                self.assertEqual(extension['extn_value'].contents, cert_reference(tree))
                self.assertEqual(extension['extn_value'].parsed.native, expected)
                # The convenience entry is reached through the certificate.
                if name not in ('entrust_version_extension', 'netscape_certificate_type',
                                'signed_certificate_timestamp_list', 'microsoft_enroll_certtype'):
                    value = getattr(document, name + '_value')
                    self.assertIsNotNone(value)
                    self.assertEqual(value.native, expected)
            self.assertEqual(actual[unknown[0]]['extn_id'].native, unknown[0])
            self.assertEqual(actual[unknown[0]]['extn_value'].native, cert_reference(unknown[2]))
            self.assertEqual(document.critical_extensions, {r[1] for r in rows + [unknown] if r[4]})
        for document in cert_documents(self):
            self.assertEqual(document.critical_extensions, set())
            for row in rows[:20]:
                self.assertIsNone(getattr(document, row[1] + '_value'))
        # Empty basic constraints expose the standard false default.
        default = cert_extension('2.5.29.19', 'basic_constraints', cert_seq(), {'ca': False, 'path_len_constraint': None})
        for document in cert_documents(self, rows=[default]):
            self.assertEqual(document.basic_constraints_value.native, default[3])
            self.assertFalse(document['tbs_certificate']['extensions'][0]['critical'].native)

    def test_f09_t03(self):
        # Each CA condition changes the reported path constraint.
        for tree, declared, limit in ((None, False, None), (cert_seq(), False, None),
                                     (cert_seq(['bool', True]), True, None),
                                     (cert_seq(['bool', True], ['int', 0]), True, 0),
                                     (cert_seq(['bool', True], ['int', 5]), True, 5)):
            rows = [] if tree is None else [cert_extension('2.5.29.19', 'basic_constraints', tree, None)]
            for document in cert_documents(self, rows=rows):
                self.assertEqual(bool(document.ca), declared)
                self.assertEqual(document.max_path_length, limit)
        # Independent documents differ only in the named identity condition.
        cases = [(None, None, True), (b'subject', None, True), (None, b'authority', True),
                 (b'subject', b'subject', True), (b'subject', b'authority', False)]
        for subject_key, authority_key, candidate in cases:
            rows = []
            if subject_key is not None:
                rows.append(cert_extension('2.5.29.14', 'key_identifier', ['octets', subject_key.hex()], None))
            if authority_key is not None:
                rows.append(cert_extension('2.5.29.35', 'authority_key_identifier',
                    cert_seq(cert_implicit(0, ['octets', authority_key.hex()])), None))
            for document in cert_documents(self, rows=rows, issuer='  EXAMPLE  Authority ', subject='example authority'):
                self.assertEqual(document.key_identifier, subject_key)
                self.assertEqual(document.authority_key_identifier, authority_key)
                self.assertTrue(document.self_issued)
                self.assertEqual(document.self_signed, 'maybe' if candidate else 'no')
            for document in cert_documents(self, rows=rows, issuer='Other Authority', subject='example authority'):
                self.assertFalse(document.self_issued)
                self.assertEqual(document.self_signed, 'no')

    def test_f09_t04(self):
        relative = cert_seq(cert_explicit(0, cert_implicit(1, cert_set(
            cert_seq(['oid', '2.5.4.3'], ['utf8', 'Relative CRL'])))))
        dns_only = cert_seq(cert_explicit(0, cert_implicit(0, cert_seq(cert_implicit(2, ['ia5', 'crl.example.org'])))))
        # RFC 5280 4.2.1.13 requires a distribution point or a CRL issuer.
        # An issuer-only point is valid but supplies no full-name location.
        no_name = cert_seq(cert_implicit(2, cert_seq(cert_uri('https://issuer.example.org/'))))
        all_uri = 'ftp://crl.example.org/complete'
        delta_uri = 'ldaps://crl.example.org/delta'
        points = cert_seq(relative, cert_point(all_uri), dns_only, no_name)
        delta = cert_seq(dns_only, cert_point(delta_uri), relative)
        access = []
        eligible = ['http://ocsp.example.org/', 'https://ocsp.example.org/',
                    'ldap://ocsp.example.org/', 'ldaps://ocsp.example.org/']
        for uri in eligible + ['ftp://ocsp.example.org/']:
            access.append(cert_seq(['oid', '1.3.6.1.5.5.7.48.1'], cert_uri(uri)))
        excluded = [cert_seq(['oid', '1.3.6.1.5.5.7.48.2'], cert_uri('https://issuer.example.org/')),
                    cert_seq(['oid', '1.3.6.1.5.5.7.48.1'], cert_implicit(2, ['ia5', 'ocsp.example.org']))]
        rows = [cert_extension('2.5.29.31', 'crl_distribution_points', points, None),
                cert_extension('2.5.29.46', 'freshest_crl', delta, None),
                cert_extension('1.3.6.1.5.5.7.1.1', 'authority_information_access', cert_seq(*(access + excluded)), None)]
        for document in cert_documents(self, rows=rows):
            self.assertEqual([p['distribution_point'].name for p in document.crl_distribution_points], ['full_name'])
            self.assertEqual([p.native for p in document.crl_distribution_points],
                             [{'distribution_point': [all_uri], 'reasons': None, 'crl_issuer': None}])
            self.assertEqual([p.native for p in document.delta_crl_distribution_points],
                             [{'distribution_point': [delta_uri], 'reasons': None, 'crl_issuer': None}])
            self.assertCountEqual(document.ocsp_urls, eligible)
        nonqualifying = [cert_extension('2.5.29.31', 'crl_distribution_points', cert_seq(relative, dns_only, no_name), None),
            cert_extension('2.5.29.46', 'freshest_crl', cert_seq(relative, dns_only), None),
            cert_extension('1.3.6.1.5.5.7.1.1', 'authority_information_access', cert_seq(*excluded, access[-1]), None)]
        for rows in ((), nonqualifying):
            for document in cert_documents(self, rows=rows):
                self.assertEqual(document.crl_distribution_points, [])
                self.assertEqual(document.delta_crl_distribution_points, [])
                self.assertEqual(document.ocsp_urls, [])

    def test_f09_t05(self):
        hashes = standard_tools().hashlib
        # Only the signature differs, so a digest of just the TBS cannot pass.
        for signature in (b'\x01\x80\xff', b'\x01\x80\xfe'):
            created, wire, _ = certificate_document(signature=signature)
            for document in (created, Certificate.load(wire)):
                self.assertEqual(document.dump(), wire)
                for algorithm in ('sha1', 'sha256'):
                    digest = getattr(hashes, algorithm)(wire).digest()
                    self.assertEqual(getattr(document, algorithm), digest)
                    fingerprint = getattr(document, algorithm + '_fingerprint')
                    self.assertEqual(bytes.fromhex(fingerprint), digest)

    def test_f09_t06(self):
        cert, cert_wire, _ = certificate_document()
        full_fields = {'trust': ['server_auth', 'email_protection'], 'reject': ['client_auth'],
                       'alias': 'Trusted Équipe', 'keyid': b'\x80\x00\xff',
                       'other': [{'algorithm': '1.2.3.88', 'parameters': Integer(31)}]}
        full_tree = cert_seq(cert_seq(['oid', '1.3.6.1.5.5.7.3.1'], ['oid', '1.3.6.1.5.5.7.3.4']),
            cert_implicit(0, cert_seq(['oid', '1.3.6.1.5.5.7.3.2'])), ['utf8', 'Trusted Équipe'],
            ['octets', '8000ff'], cert_implicit(1, cert_seq(cert_seq(['oid', '1.2.3.88'], ['int', 31]))))
        for fields, tree in (({}, cert_seq()), (full_fields, full_tree)):
            aux_wire = cert_reference(tree)
            wire = cert_wire + aux_wire
            created = TrustedCertificate([cert.copy(), CertificateAux.load(aux_wire) if not fields else CertificateAux(fields)])
            for trusted in (created, TrustedCertificate.load(wire)):
                self.assertEqual(trusted.dump(), wire)
                self.assertEqual(trusted[0].dump(), cert_wire)
                self.assertEqual(trusted[0].serial_number, 793)
                aux = trusted[1]
                for name in ('trust', 'reject', 'alias', 'keyid'):
                    self.assertEqual(aux[name].native, fields.get(name))
                if fields:
                    self.assertEqual(aux['other'][0]['algorithm'].dotted, '1.2.3.88')
                    self.assertEqual(aux['other'][0]['parameters'].native, 31)
                else:
                    self.assertIsNone(aux['other'].native)

    def test_f09_t07(self):
        supported = cert_seq(cert_algorithm(), cert_explicit(0, ['bits', '101']),
                             cert_explicit(1, cert_seq(cert_seq(['oid', '1.2.3.91']))))
        attributes = [
            ('2.5.4.52', cert_set(supported, cert_seq(cert_algorithm('1.2.840.113549.1.1.5')))),
            ('1.3.6.1.5.5.7.9.1', cert_set(['time', '19870714000000Z'])),
            ('1.3.6.1.5.5.7.9.2', cert_set(['utf8', 'Montréal'])),
            ('1.3.6.1.5.5.7.9.3', cert_set(['printable', 'F'])),
            ('1.3.6.1.5.5.7.9.4', cert_set(['printable', 'CA'], ['printable', 'FR'])),
            ('1.3.6.1.5.5.7.9.5', cert_set(['printable', 'DE'])),
            ('1.2.3.97', cert_set(['utf8', 'open value'], ['int', 29])),
        ]
        row = cert_directory_row(attributes)
        for document in cert_documents(self, rows=[row]):
            bound = document.subject_directory_attributes_value
            values = {a['type'].dotted: a['values'] for a in bound}
            self.assertEqual(set(values), {a[0] for a in attributes})
            for identity, tree in attributes:
                self.assertEqual(values[identity].dump(), cert_reference(tree))
            algorithms = {a['algorithm_identifier']['algorithm'].dotted: a for a in values['2.5.4.52']}
            self.assertEqual(set(algorithms), {'1.2.840.113549.1.1.11', '1.2.840.113549.1.1.5'})
            complete = algorithms['1.2.840.113549.1.1.11']
            self.assertEqual(complete['intended_usage'].native, {'digital_signature', 'key_encipherment'})
            self.assertEqual(complete['intended_certificate_policies'].native,
                             [{'policy_identifier': '1.2.3.91', 'policy_qualifiers': None}])
            minimal = algorithms['1.2.840.113549.1.1.5']
            self.assertIsNone(minimal['intended_usage'].native)
            self.assertIsNone(minimal['intended_certificate_policies'].native)
            self.assertEqual(values['1.3.6.1.5.5.7.9.1'][0].native.isoformat(), '1987-07-14T00:00:00+00:00')
            self.assertEqual(values['1.3.6.1.5.5.7.9.2'].native, ['Montréal'])
            self.assertEqual(values['1.3.6.1.5.5.7.9.3'].native, ['F'])
            self.assertEqual(set(values['1.3.6.1.5.5.7.9.4'].native), {'CA', 'FR'})
            self.assertEqual(values['1.3.6.1.5.5.7.9.5'].native, ['DE'])
            self.assertEqual({v.native for v in values['1.2.3.97']}, {'open value', 29})
            # Construct the typed values and attach them through the certificate.
            document['tbs_certificate']['extensions'][0]['extn_value'] = SubjectDirectoryAttributes([
                {'type': 'supported_algorithms', 'values': [
                    {'algorithm_identifier': AnyAlgorithmIdentifier.load(cert_reference(cert_algorithm())),
                     'intended_usage': {'digital_signature', 'key_encipherment'},
                     'intended_certificate_policies': [{'policy_identifier': '1.2.3.91'}]},
                    {'algorithm_identifier': AnyAlgorithmIdentifier.load(cert_reference(cert_algorithm('1.2.840.113549.1.1.5')))}]},
                *[SubjectDirectoryAttribute.load(cert_reference(cert_seq(['oid', oid], tree))) for oid, tree in attributes[1:]]])
            self.assertEqual(document.dump(), certificate_document(rows=[row])[1])

    def test_f09_t08(self):
        methods = ('internal', 'injected', 'internal_revocable', 'injected_revocable')
        locations = ('tpm_manufacturer', 'platform_manufacturer', 'ek_cert_signer')
        statuses = ('designed_to_meet', 'evaluation_in_progress', 'evaluation_completed')
        strengths = ('basic', 'medium', 'high')
        # Seven rows cover every enumerated member, without a Cartesian product.
        for index in range(7):
            ref = cert_seq(['ia5', 'https://security.example.org/profile'],
                           cert_seq(['oid', '2.16.840.1.101.3.4.2.1'], ['null', None]), ['bits', '101101'])
            ref_fields = {'uniform_resource_identifier': 'https://security.example.org/profile',
                          'hash_algorithm': {'algorithm': 'sha256'}, 'hash_value': (1, 0, 1, 1, 0, 1)}
            cc_fields = {'version': '3.1', 'assurance_level': 'level%d' % (index + 1),
                         'evaluation_status': statuses[index % 3], 'plus': True,
                         'strengh_of_function': strengths[index % 3],
                         'profile_oid': '1.2.3.71', 'profile_url': ref_fields,
                         'target_oid': '1.2.3.72', 'target_uri': ref_fields}
            cc_tree = cert_seq(['ia5', '3.1'], ['enum', index + 1], ['enum', index % 3], ['bool', True],
                cert_implicit(0, ['enum', index % 3]), cert_implicit(1, ['oid', '1.2.3.71']),
                cert_implicit(2, ref), cert_implicit(3, ['oid', '1.2.3.72']), cert_implicit(4, ref))
            assertion_fields = {'version': 'v3', 'field_upgradable': True,
                'ek_generation_type': methods[index % 4], 'ek_generation_location': locations[index % 3],
                'ek_certificate_generation_location': locations[(index + 1) % 3], 'cc_info': cc_fields,
                'fips_level': {'version': '140-2', 'level': 'level%d' % (index % 4 + 1), 'plus': True},
                'iso_9000_certified': True, 'iso_9000_uri': 'https://security.example.org/iso'}
            assertion_tree = cert_seq(['int', 2], ['bool', True],
                cert_implicit(0, ['enum', index % 4]), cert_implicit(1, ['enum', index % 3]),
                cert_implicit(2, ['enum', (index + 1) % 3]), cert_implicit(3, cc_tree),
                cert_implicit(4, cert_seq(['ia5', '140-2'], ['enum', index % 4 + 1], ['bool', True])),
                cert_implicit(5, ['bool', True]), ['ia5', 'https://security.example.org/iso'])
            tpm_fields = {'family': '2.0', 'level': 2 + index, 'revision': 138 + index}
            platform_fields = {'version': {'major_version': 2, 'minor_version': index, 'revision': 43},
                               'platform_class': b'\x00\x00\x00\x01'}
            attributes = [('2.23.133.2.16', cert_set(cert_seq(['utf8', '2.0'], ['int', 2 + index], ['int', 138 + index]))),
                ('2.23.133.2.17', cert_set(cert_seq(cert_seq(['int', 2], ['int', index], ['int', 43]), ['octets', '00000001']))),
                ('2.23.133.2.18', cert_set(assertion_tree))]
            row = cert_directory_row(attributes)
            for document in cert_documents(self, rows=[row]):
                bound = {a['type'].native: a['values'][0] for a in document.subject_directory_attributes_value}
                self.assertEqual(bound['tpm_specification'].native, tpm_fields)
                self.assertEqual(bound['tcg_platform_specification'].native, platform_fields)
                # Digest identifier includes optional parameters in its native shape.
                expected = dict(assertion_fields)
                expected['cc_info'] = dict(cc_fields)
                expected_reference = dict(ref_fields)
                expected_reference['hash_algorithm'] = {'algorithm': 'sha256', 'parameters': None}
                expected['cc_info']['profile_url'] = expected_reference
                expected['cc_info']['target_uri'] = expected_reference
                self.assertEqual(bound['tpm_security_assertions'].native, expected)
                typed = SubjectDirectoryAttributes([
                    {'type': 'tpm_specification', 'values': [tpm_fields]},
                    {'type': 'tcg_platform_specification', 'values': [platform_fields]},
                    {'type': 'tpm_security_assertions', 'values': [assertion_fields]}])
                document['tbs_certificate']['extensions'][0]['extn_value'] = typed
                self.assertEqual(document.dump(), certificate_document(rows=[row])[1])
        # Independent minimal encoding checks every specified omitted default.
        minimal_cc = cert_seq(['ia5', '3.1'], ['enum', 1], ['enum', 0],
            cert_implicit(4, cert_seq(['ia5', 'https://security.example.org/target'])))
        minimal_fips = cert_seq(['ia5', '140-3'], ['enum', 1])
        minimal = cert_seq(cert_implicit(3, minimal_cc), cert_implicit(4, minimal_fips))
        row = cert_directory_row([('2.23.133.2.18', cert_set(minimal))])
        for document in cert_documents(self, rows=[row]):
            assertion = document.subject_directory_attributes_value[0]['values'][0]
            self.assertEqual(assertion['version'].native, 'v1')
            for name in ('field_upgradable', 'iso_9000_certified'):
                self.assertIs(assertion[name].native, False)
            for name in ('cc_info', 'fips_level'):
                self.assertIs(assertion[name]['plus'].native, False)
            for name in ('ek_generation_type', 'ek_generation_location', 'ek_certificate_generation_location', 'iso_9000_uri'):
                self.assertIsNone(assertion[name].native)
            for name in ('strengh_of_function', 'profile_oid', 'profile_url', 'target_oid'):
                self.assertIsNone(assertion['cc_info'][name].native)
            reference = assertion['cc_info']['target_uri']
            self.assertEqual(reference['uniform_resource_identifier'].native, 'https://security.example.org/target')
            self.assertIsNone(reference['hash_algorithm'].native)
            self.assertIsNone(reference['hash_value'].native)
            self.assertEqual(assertion.dump(), cert_reference(minimal))
