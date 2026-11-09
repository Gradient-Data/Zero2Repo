# feature: F16
"""Acceptance checks for timestamp requests, CMS interpretation and evidence."""
import unittest
from cobaltform.cms import ContentInfo, EncapsulatedContentInfo
from cobaltform.tsp import PKIStatusInfo, TimeStampReq, TimeStampResp, TimeStampedData
from F09_helpers import CERT_START, cert_seq, cert_explicit
from F11_helpers import crl_document
from F14_helpers import cms_bound_attributes
from F16_helpers import (
    TSP_STATUSES, TSP_FAILURES, tsp_reference, tsp_documents, tsp_imprint,
    tsp_extensions, tsp_request, tsp_status, tsp_information, tsp_token,
    tsp_signing_row, tsp_timestamped,
)


class TestTimestamp(unittest.TestCase):
    def test_f16_t01(self):
        for full in (False, True):
            parts = tsp_request(full, full)
            for request in tsp_documents(self, TimeStampReq, parts):
                self.assertEqual(request['version'].native, 'v1')
                self.assertEqual(request['message_imprint'].native, dict(
                    tsp_imprint(full)[0], hash_algorithm={'algorithm': 'sha384' if full else 'sha256', 'parameters': None}))
                self.assertEqual(request['req_policy'].native, '1.2.3.16.1' if full else None)
                self.assertEqual(request['nonce'].native, 2 ** 79 + 57 if full else None)
                self.assertEqual(request['cert_req'].native, full)
                self.assertEqual(request['extensions'].native,
                    [dict(tsp_extensions()[0][0], critical=False), tsp_extensions()[0][1]] if full else None)
        # Modify through the request entry after reading and serializing it.
        request = TimeStampReq.load(tsp_reference(tsp_request()[1]))
        request.native
        request.dump()
        for key, value in tsp_request(True, True)[0].items():
            request[key] = value
        self.assertEqual(request.dump(), tsp_reference(tsp_request(True, True)[1]))
        self.assertEqual(request['message_imprint']['hashed_message'].native, bytes(range(48)))
        self.assertTrue(request['cert_req'].native)

    def test_f16_t02(self):
        # Independent status documents do not rely on tokenless full responses.
        for number, name in TSP_STATUSES:
            for status in tsp_documents(self, PKIStatusInfo, tsp_status(number, name)):
                self.assertEqual(status['status'].native, name)
                self.assertIsNone(status['status_string'].native)
                self.assertIsNone(status['fail_info'].native)
        # Individual sparse bits must retain their identities, not merely a nonempty set.
        for flags in [(), *[(row,) for row in TSP_FAILURES], TSP_FAILURES]:
            texts = ['Service detail', '\u65f6\u95f4\u6233 \u03b2']
            expected = {'status': 'rejection', 'status_string': texts,
                        'fail_info': {name for bit, name in flags}}
            for status in tsp_documents(self, PKIStatusInfo, tsp_status(2, 'rejection', flags, texts)):
                self.assertEqual(status.native, expected)

    def test_f16_t03(self):
        for full in (False, True):
            token_fields, token_tree = tsp_token(full, full)
            status_fields, status_tree = tsp_status(int(full), 'granted_with_mods' if full else 'granted')
            parts = ({'status': status_fields, 'time_stamp_token': token_fields}, cert_seq(status_tree, token_tree))
            for response in tsp_documents(self, TimeStampResp, parts):
                self.assertEqual(response['status']['status'].native, status_fields['status'])
                token = response['time_stamp_token']
                self.assertEqual(token['content_type'].native, 'signed_data')
                self.assertEqual(token.dump(), tsp_reference(token_tree))
                encap = token['content']['encap_content_info']
                self.assertEqual(encap['content_type'].native, 'tst_info')
                info = encap['content'].parsed
                self.assertEqual(info['version'].native, 'v1')
                self.assertEqual(info['policy'].native, '1.2.3.16.2')
                self.assertEqual(info['message_imprint']['hash_algorithm']['algorithm'].native,
                                 'sha384' if full else 'sha256')
                self.assertEqual(info['message_imprint']['hashed_message'].native, bytes(range(48 if full else 32)))
                self.assertEqual(info['serial_number'].native, 2 ** 72 + 29)
                self.assertEqual(info['gen_time'].native, CERT_START)
                self.assertEqual(info['accuracy'].native, {'seconds': 3, 'millis': 421, 'micros': 87} if full else None)
                self.assertEqual(info['ordering'].native, full)
                self.assertEqual(info['nonce'].native, 2 ** 79 + 57 if full else None)
                self.assertEqual(info['tsa'].native, 'https://tsa.example.org/' if full else None)
                self.assertEqual(info['extensions'].native,
                    [dict(tsp_extensions()[0][0], critical=False), tsp_extensions()[0][1]] if full else None)
                self.assertEqual(info.dump(), tsp_reference(tsp_information(full, full)[1]))
                response['status'] = tsp_status(3, 'waiting', texts=['Pending'])[0]
                response['time_stamp_token'] = tsp_token(not full, not full)[0]
                expected = cert_seq(tsp_status(3, 'waiting', texts=['Pending'])[1], tsp_token(not full, not full)[1])
                self.assertEqual(response.dump(), tsp_reference(expected))

    def test_f16_t04(self):
        for full in (False, True):
            rows = [tsp_signing_row(version, full) for version in (1, 2)]
            # Reuse the earlier CMS signer path, but encode this feature's new bindings independently.
            for document in tsp_documents(self, ContentInfo, cms_bound_attributes(rows)):
                attrs = {attr['type'].native: attr for attr in document['content']['signer_infos'][0]['signed_attrs']}
                self.assertEqual(set(attrs), {'signing_certificate', 'signing_certificate_v2'})
                for version, name in ((1, 'signing_certificate'), (2, 'signing_certificate_v2')):
                    attribute = attrs[name]
                    self.assertEqual(len(attribute['values']), 1)
                    value = attribute['values'][0]
                    self.assertEqual(len(value['certs']), 2 if full else 1)
                    for index, reference in enumerate(value['certs']):
                        size = 20 if version == 1 else (48 if full and index == 1 else 32)
                        self.assertEqual(reference['cert_hash'].native, bytes(range(size - 1)) + bytes([index]))
                        if version == 2:
                            self.assertEqual(reference['hash_algorithm']['algorithm'].native,
                                             'sha384' if full and index == 1 else 'sha256')
                        if full:
                            self.assertEqual(reference['issuer_serial']['issuer'].native,
                                ['issuer.example.org', 'https://issuer.example.org/'])
                            self.assertEqual(reference['issuer_serial']['serial_number'].native, 830 + index)
                        else:
                            self.assertIsNone(reference['issuer_serial'].native)
                    self.assertEqual(value['policies'].native,
                        [{'policy_identifier': '1.2.3.16.10', 'policy_qualifiers': None},
                         {'policy_identifier': '1.2.3.16.11', 'policy_qualifiers': None}] if full else None)

    def test_f16_t05(self):
        for kind in ('tst_evidence', 'ers_evidence', 'other_evidence'):
            for full in (False, True):
                fields, tree = tsp_timestamped(kind, full)
                documents = list(tsp_documents(self, TimeStampedData, (fields, tree)))
                # Both CMS carriers bind the embedded timestamped-data type.
                wrapped = ({'content_type': 'timestamped_data', 'content': TimeStampedData(fields)},
                    cert_seq(['oid', '1.2.840.113549.1.9.16.1.31'], cert_explicit(0, tree)))
                for document in tsp_documents(self, ContentInfo, wrapped):
                    self.assertEqual(document['content_type'].native, 'timestamped_data')
                    documents.append(document['content'])
                encapsulated = ({'content_type': 'timestamped_data', 'content': TimeStampedData(fields)},
                    cert_seq(['oid', '1.2.840.113549.1.9.16.1.31'],
                             cert_explicit(0, ['octets', tsp_reference(tree).hex()])))
                for document in tsp_documents(self, EncapsulatedContentInfo, encapsulated):
                    self.assertEqual(document['content_type'].native, 'timestamped_data')
                    documents.append(document['content'].parsed)
                for document in documents:
                    self.assertEqual(document['version'].native, 'v1')
                    self.assertEqual(document['data_uri'].native, 'https://archive.example.org/data' if full else None)
                    self.assertEqual(document['content'].native, b'archive content\x00\xff' if full else None)
                    if full:
                        metadata = document['meta_data']
                        self.assertTrue(metadata['hash_protected'].native)
                        self.assertEqual(metadata['file_name'].native, 'report-\u03b2.txt')
                        self.assertEqual(metadata['media_type'].native, 'text/plain')
                        self.assertEqual(metadata['other_meta_data'].native,
                            [{'type': '1.2.3.16.20', 'values': ['metadata value']}])
                    else:
                        self.assertIsNone(document['meta_data'].native)
                    evidence = document['temporal_evidence']
                    self.assertEqual(evidence.name, kind)
                    value = evidence.chosen
                    if kind == 'other_evidence':
                        self.assertEqual(value['oe_type'].native, '1.2.3.16.21')
                        self.assertEqual(value['oe_value'].native, 'external evidence')
                    elif kind == 'tst_evidence':
                        self.assertEqual(len(value), 2 if full else 1)
                        for index, entry in enumerate(value):
                            self.assertEqual(entry['time_stamp']['content_type'].native, 'tst_info')
                            info = entry['time_stamp']['content'].parsed
                            self.assertEqual(info['message_imprint']['hashed_message'].native,
                                             bytes(range(48 if index else 32)))
                            self.assertEqual(info.dump(), tsp_reference(tsp_information(bool(index), bool(index))[1]))
                            if full and index == 0:
                                self.assertEqual(entry['crl'].dump(), crl_document()[1])
                            else:
                                self.assertIsNone(entry['crl'].native)
                    else:
                        self.assertEqual(value['version'].native, 'v1')
                        self.assertEqual([a['algorithm'].native for a in value['digest_algorithms']], ['sha256', 'sha384'])
                        if full:
                            self.assertEqual(value['crypto_infos'].native,
                                [{'type': '1.2.3.16.20', 'values': ['metadata value']}])
                            self.assertEqual(value['encryption_info']['encryption_info_type'].native, '1.2.3.16.22')
                            self.assertEqual(value['encryption_info']['encryption_info_value'].native, b'\x80\x00encryption')
                        else:
                            self.assertIsNone(value['crypto_infos'].native)
                            self.assertIsNone(value['encryption_info'].native)
                        stamps = value['archive_time_stamp_sequence']
                        self.assertEqual(len(stamps), 2 if full else 1)
                        for index, stamp in enumerate(stamps):
                            self.assertEqual(stamp['time_stamp'].dump(), tsp_reference(tsp_token(bool(index), bool(index))[1]))
                            if full:
                                self.assertEqual(stamp['digest_algorithm']['algorithm'].native, 'sha384' if index == 0 else 'sha256')
                                self.assertEqual(stamp['attributes'].native,
                                    [{'type': '1.2.3.16.20', 'values': ['metadata value']}])
                                self.assertEqual(stamp['reduced_hashtree'].native,
                                    [[b'left' + bytes([index]), b'right\x00'], [b'root\xff']])
                            else:
                                for key in ('digest_algorithm', 'attributes', 'reduced_hashtree'):
                                    self.assertIsNone(stamp[key].native)
