# feature: F13
"""Acceptance tests for OCSP documents and context-bound extensions."""
import unittest
from cobaltform.ocsp import CertStatus, OCSPRequest, OCSPResponse
from F08_helpers import name_groups
from F09_helpers import CERT_START, CERT_END, cert_seq, certificate_document
from F13_helpers import (
    OCSP_IDS, OCSP_STATUSES, ocsp_reference, ocsp_request_document,
    ocsp_response_document, ocsp_extension_rows,
)


class TestOCSP(unittest.TestCase):
    def test_f13_t01(self):
        # Each variant distinguishes an optional document component.
        for signed, certificates, requestor, count in (
            (False, False, None, 1),
            (True, False, 'https://requestor.example.org/', 2),
            (True, True, 'https://requestor.example.org/', 2),
        ):
            options = dict(signed=signed, certificates=certificates, requestor=requestor, count=count)
            created, wire = ocsp_request_document(**options)
            for document in (created, OCSPRequest.load(wire)):
                self.assertEqual(document.dump(), wire)
                tbs = document['tbs_request']
                self.assertEqual(tbs['version'].native, 'v1')
                self.assertEqual(tbs['requestor_name'].native, requestor)
                if requestor is not None:
                    self.assertEqual(tbs['requestor_name'].name, 'uniform_resource_identifier')
                self.assertEqual(len(tbs['request_list']), count)
                for index, request in enumerate(tbs['request_list']):
                    name, _, name_hash, key_hash, serial = OCSP_IDS[index]
                    identifier = request['req_cert']
                    self.assertEqual(identifier['hash_algorithm']['algorithm'].native, name)
                    self.assertEqual(identifier['issuer_name_hash'].native, name_hash)
                    self.assertEqual(identifier['issuer_key_hash'].native, key_hash)
                    self.assertEqual(identifier['serial_number'].native, serial)
                sig = document['optional_signature']
                if signed:
                    self.assertEqual(sig['signature_algorithm']['algorithm'].native, 'sha256_rsa')
                    self.assertEqual(sig['signature'].native, b'\x00\x81\xfd')
                    if certificates:
                        _, certificate_wire, _ = certificate_document()
                        self.assertEqual(len(sig['certs']), 1)
                        self.assertEqual(sig['certs'][0].dump(), certificate_wire)
                    else:
                        self.assertIsNone(sig['certs'].native)
                else:
                    self.assertIsNone(sig.native)
                tbs['request_list'][0]['req_cert']['serial_number'] = 9001
                if signed:
                    sig['signature'] = b'\x1a\x00\x92'
                _, expected = ocsp_request_document(**options, serial=9001,
                    signature=b'\x1a\x00\x92' if signed else b'\x00\x81\xfd')
                self.assertEqual(document.dump(), expected)

    def test_f13_t02(self):
        for number, status in OCSP_STATUSES:
            wire = ocsp_reference(cert_seq(['enum', number]))
            for document in (OCSPResponse({'response_status': status}),
                             OCSPResponse.load(wire)):
                self.assertEqual(document['response_status'].native, status)
                self.assertIsNone(document['response_bytes'].native)
                self.assertEqual(document.dump(), wire)
        # A status-only response and a response carrying a basic document differ.
        created, wire = ocsp_response_document()
        for document in (created, OCSPResponse.load(wire)):
            self.assertEqual(document['response_status'].native, 'successful')
            self.assertEqual(document['response_bytes']['response_type'].native, 'basic_ocsp_response')
            basic = document['response_bytes']['response'].parsed
            self.assertEqual(len(basic['tbs_response_data']['responses']), 3)
            self.assertEqual(document.dump(), wire)
            document['response_status'] = 'unauthorized'
            del document['response_bytes']
            self.assertEqual(document.dump(), ocsp_reference(cert_seq(['enum', 6])))

    def test_f13_t03(self):
        for by_name, certificates, reason in ((True, True, True), (False, False, False)):
            options = dict(by_name=by_name, certificates=certificates, reason=reason)
            created, wire = ocsp_response_document(**options)
            for document in (created, OCSPResponse.load(wire)):
                self.assertEqual(document.dump(), wire)
                basic = document['response_bytes']['response'].parsed
                data = basic['tbs_response_data']
                self.assertEqual(data['version'].native, 'v1')
                responder = data['responder_id']
                self.assertEqual(responder.name, 'by_name' if by_name else 'by_key')
                if by_name:
                    self.assertEqual(name_groups(responder.chosen), [[('2.5.4.3', 'OCSP Authority')]])
                else:
                    self.assertEqual(responder.chosen.native, b'\x92' * 20)
                self.assertEqual(data['produced_at'].native, CERT_START)
                self.assertEqual(len(data['responses']), 3)
                for index, expected_status in enumerate(('good', 'unknown', 'revoked')):
                    entry = data['responses'][index]
                    name, _, name_hash, key_hash, serial = OCSP_IDS[index]
                    identifier = entry['cert_id']
                    self.assertEqual(identifier['hash_algorithm']['algorithm'].native, name)
                    self.assertEqual(identifier['issuer_name_hash'].native, name_hash)
                    self.assertEqual(identifier['issuer_key_hash'].native, key_hash)
                    self.assertEqual(identifier['serial_number'].native, serial)
                    status = entry['cert_status']
                    self.assertEqual(status.name, expected_status)
                    if expected_status == 'revoked':
                        expected = {'revocation_time': CERT_START,
                                    'revocation_reason': 'key_compromise' if reason else None}
                        self.assertEqual(status.native, expected)
                        self.assertEqual(status.chosen.native, expected)
                    else:
                        self.assertEqual(status.native, expected_status)
                        self.assertEqual(status.chosen.native, expected_status)
                    self.assertEqual(entry['this_update'].native, CERT_START)
                    self.assertEqual(entry['next_update'].native, CERT_END if index == 0 else None)
                self.assertEqual(basic['signature_algorithm']['algorithm'].native, 'sha256_rsa')
                self.assertEqual(basic['signature'].native, b'\xff\x00\xa5')
                if certificates:
                    _, certificate_wire, _ = certificate_document()
                    self.assertEqual(len(basic['certs']), 1)
                    self.assertEqual(basic['certs'][0].dump(), certificate_wire)
                else:
                    self.assertIsNone(basic['certs'].native)
                # Change a parsed embedded document and explicitly bind it back.
                data['responses'][0]['cert_id']['serial_number'] = 9002
                data['responses'][0]['cert_status'] = CertStatus(('unknown', None))
                data['produced_at'] = CERT_END
                basic['signature'] = b'\x5a\x00\x93'
                document['response_bytes']['response'] = basic
                _, expected = ocsp_response_document(**options, serial=9002, first_status='unknown',
                    produced_end=True, signature=b'\x5a\x00\x93')
                self.assertEqual(document.dump(), expected)

    def test_f13_t04(self):
        request_rows, entry_rows, response_rows, single_rows = ocsp_extension_rows()
        for present in (True, False):
            created_request, request_wire = ocsp_request_document(
                wide=request_rows if present else None, single=entry_rows if present else None)
            created_response, response_wire = ocsp_response_document(
                wide=response_rows if present else None, single=single_rows if present else None)
            for request, response in ((created_request, created_response),
                                      (OCSPRequest.load(request_wire), OCSPResponse.load(response_wire))):
                self.assertEqual(request.dump(), request_wire)
                self.assertEqual(response.dump(), response_wire)
                request_entry = request['tbs_request']['request_list'][0]
                data = response['response_bytes']['response'].parsed['tbs_response_data']
                single_response = data['responses'][0]
                levels = (
                    (request, request['tbs_request']['request_extensions'], request_rows),
                    (request_entry, request_entry['single_request_extensions'], entry_rows),
                    (response, data['response_extensions'], response_rows),
                    (single_response, single_response['single_extensions'], single_rows),
                )
                for owner, extensions, rows in levels:
                    if not present:
                        self.assertIsNone(extensions.native)
                        self.assertEqual(owner.critical_extensions, set())
                        for row in rows:
                            if row[1] not in ('1.2.3.200.13', 'signed_certificate_timestamp_list'):
                                self.assertIsNone(getattr(owner, row[1] + '_value'))
                        continue
                    self.assertEqual(len(extensions), len(rows))
                    by_oid = {extension['extn_id'].dotted: extension for extension in extensions}
                    self.assertEqual(set(by_oid), {row[0] for row in rows})
                    self.assertEqual(owner.critical_extensions, {row[1] for row in rows if row[4]})
                    for identity, name, tree, expected, critical in rows:
                        extension = by_oid[identity]
                        self.assertEqual(extension['extn_id'].native, name)
                        self.assertEqual(extension['critical'].native, critical)
                        self.assertEqual(extension['extn_value'].contents, ocsp_reference(tree))
                        if name == '1.2.3.200.13':
                            continue
                        parsed = extension['extn_value'].parsed
                        self.assertEqual(parsed.native, expected)
                        if name != 'signed_certificate_timestamp_list':
                            value = getattr(owner, name + '_value')
                            self.assertIsNotNone(value)
                            self.assertEqual(value.native, expected)
                # Extensions on the first entry must not leak into its sibling.
                sibling_request = request['tbs_request']['request_list'][1]
                self.assertIsNone(sibling_request['single_request_extensions'].native)
                self.assertIsNone(sibling_request.service_locator_value)
                self.assertEqual(sibling_request.critical_extensions, set())
                sibling_response = data['responses'][1]
                self.assertIsNone(sibling_response['single_extensions'].native)
                self.assertIsNone(sibling_response.crl_value)
                self.assertEqual(sibling_response.critical_extensions, set())
