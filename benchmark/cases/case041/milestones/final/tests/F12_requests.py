# feature: F12
"""Acceptance tests for complete certificate signing requests."""
import unittest
from cobaltform.csr import CertificationRequest
from cobaltform.x509 import DirectoryString
from F08_helpers import grouped_name, name_groups
from F12_helpers import (
    csr_document, csr_attributes, csr_reference, csr_standard_parts,
)


class TestRequest(unittest.TestCase):
    def test_f12_t01(self):
        for attributes in (None, 'empty'):
            created, wire = csr_document(attributes=attributes)
            for document in (created, CertificationRequest.load(wire)):
                self.assertEqual(document.dump(), wire)
                info = document['certification_request_info']
                self.assertEqual(info['version'].native, 'v1')
                self.assertEqual(name_groups(info['subject']), [[('2.5.4.3', 'Enrollment Subject')]])
                public = info['subject_pk_info']
                self.assertEqual(public['algorithm']['algorithm'].native, 'rsa')
                self.assertEqual(public['public_key'].parsed.native,
                                 {'modulus': 3233, 'public_exponent': 17})
                self.assertEqual(document['signature_algorithm']['algorithm'].native, 'sha256_rsa')
                self.assertEqual(document['signature'].native, b'\x00\x81\xff\x29')
                self.assertEqual(info['attributes'].native, None if attributes is None else [])
                self.assertEqual(info['attributes'].dump(), b'' if attributes is None else b'\xa0\x00')
                # Modify a previously serialized request, including nested public-key data.
                info['subject'] = grouped_name([[('common_name', 'Changed Subject')]])
                public['public_key'] = {'modulus': 65537, 'public_exponent': 17}
                document['signature_algorithm'] = {'algorithm': 'sha384_ecdsa'}
                document['signature'] = b'\xfe\x00\x10'
                _, expected = csr_document(attributes=attributes, subject='Changed Subject',
                                           modulus=65537, ec_signature=True, signature=b'\xfe\x00\x10')
                self.assertEqual(document.dump(), expected)
                reread = CertificationRequest.load(document.dump())
                self.assertEqual(name_groups(reread['certification_request_info']['subject']),
                                 [[('2.5.4.3', 'Changed Subject')]])
                self.assertEqual(reread['certification_request_info']['subject_pk_info']
                                 ['public_key'].parsed['modulus'].native, 65537)
                self.assertEqual(reread['signature_algorithm']['algorithm'].native, 'sha384_ecdsa')
                self.assertEqual(reread['signature'].native, b'\xfe\x00\x10')

    def test_f12_t02(self):
        created, wire = csr_document(attributes='standard')
        _, trees = csr_standard_parts()
        for document in (created, CertificationRequest.load(wire)):
            self.assertEqual(document.dump(), wire)
            attributes = csr_attributes(document)
            self.assertEqual(len(document['certification_request_info']['attributes']), 4)
            self.assertEqual(set(attributes), {'1.2.840.113549.1.9.7', '1.2.840.113549.1.9.9',
                                              '1.2.840.113549.1.9.14', '1.2.3.200.99'})
            password = attributes['1.2.840.113549.1.9.7']
            self.assertEqual(password['type'].native, 'challenge_password')
            self.assertEqual(password['values'].native, ['saffron secret'])
            extended = attributes['1.2.840.113549.1.9.9']
            self.assertEqual(extended['type'].native, 'extended_certificate_attributes')
            self.assertEqual(len(extended['values']), 1)
            nested = extended['values'][0]
            self.assertEqual(nested['type'].dotted, '1.2.3.200.12')
            self.assertCountEqual([value.native for value in nested['values']], ['nested text', 73])
            requested = attributes['1.2.840.113549.1.9.14']
            self.assertEqual(requested['type'].native, 'extension_request')
            self.assertEqual(len(requested['values']), 1)
            extensions = requested['values'][0]
            self.assertEqual(len(extensions), 2)
            by_oid = {extension['extn_id'].dotted: extension for extension in extensions}
            self.assertEqual(set(by_oid), {'2.5.29.17', '2.5.29.19'})
            san = by_oid['2.5.29.17']
            self.assertEqual(san['extn_id'].native, 'subject_alt_name')
            self.assertTrue(san['critical'].native)
            self.assertEqual([(value.name, value.native) for value in san['extn_value'].parsed],
                             [('dns_name', 'csr.example.org'), ('uniform_resource_identifier',
                               'https://csr.example.org/enroll'), ('ip_address', '192.0.2.44')])
            basic = by_oid['2.5.29.19']
            self.assertEqual(basic['extn_id'].native, 'basic_constraints')
            self.assertFalse(basic['critical'].native)
            self.assertEqual(basic['extn_value'].parsed.native, {'ca': True, 'path_len_constraint': 2})
            unknown = attributes['1.2.3.200.99']
            self.assertEqual(unknown['type'].native, '1.2.3.200.99')
            self.assertEqual(unknown['values'].dump(), csr_reference(trees[3][1][1]))
            # Keep every attribute's independently encoded content observable.
            for identity, tree in zip(('1.2.840.113549.1.9.7', '1.2.840.113549.1.9.9',
                                       '1.2.840.113549.1.9.14', '1.2.3.200.99'), trees):
                self.assertEqual(attributes[identity].dump(), csr_reference(tree))
            for index, value in enumerate(password['values']):
                if value.native == 'saffron secret':
                    password['values'][index] = DirectoryString(('utf8_string', 'changed secret'))
            _, expected = csr_document(attributes='standard', password='changed secret')
            self.assertEqual(document.dump(), expected)

    def test_f12_t03(self):
        created, wire = csr_document(attributes='microsoft')
        for document in (created, CertificationRequest.load(wire)):
            self.assertEqual(document.dump(), wire)
            attributes = csr_attributes(document)
            self.assertEqual(len(document['certification_request_info']['attributes']), 3)
            self.assertEqual(set(attributes), {'1.3.6.1.4.1.311.13.2.2', '1.3.6.1.4.1.311.13.2.3',
                                              '1.3.6.1.4.1.311.21.20'})
            provider = attributes['1.3.6.1.4.1.311.13.2.2']
            self.assertEqual(provider['type'].native, 'microsoft_enrollment_csp_provider')
            self.assertEqual(len(provider['values']), 1)
            self.assertEqual(provider['values'][0]['keyspec'].native, 2)
            self.assertEqual(provider['values'][0]['cspname'].native, 'Enrollment Provider Ω')
            self.assertEqual(provider['values'][0]['signature'].native, (1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0))
            os_version = attributes['1.3.6.1.4.1.311.13.2.3']
            self.assertEqual(os_version['type'].native, 'microsoft_os_version')
            self.assertCountEqual(os_version['values'].native, ['10.0.22631', '6.3.9600'])
            client = attributes['1.3.6.1.4.1.311.21.20']
            self.assertEqual(client['type'].native, 'microsoft_request_client_info')
            self.assertEqual(len(client['values']), 1)
            for field, expected in (('clientid', 9), ('machinename', 'node.enroll.example.org'),
                                    ('username', 'domain\\analyst'), ('processname', 'enroll-tool.exe')):
                self.assertEqual(client['values'][0][field].native, expected)
