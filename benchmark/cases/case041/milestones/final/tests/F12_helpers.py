# feature: F12
"""CSR inputs and independent RFC 2986/2985 DER expectations.

Frozen vectors are generated offline, independently of the product. No product output
is used as an expected encoding, and missing vectors are errors.
"""
import json
from cobaltform.core import Any, Integer, ParsableOctetString, UTF8String
from cobaltform.csr import CRIAttributes, CertificationRequest
from cobaltform.x509 import DirectoryString
from _helpers import support_path
from F07_helpers import rsa_components
from F08_helpers import grouped_name
from F09_helpers import cert_seq, cert_set, cert_implicit, cert_algorithm, cert_name, cert_uri


def csr_reference(tree):
    vectors = json.loads(support_path('F12_vectors.json').read_text())
    return bytes.fromhex(vectors[json.dumps(tree, separators=(',', ':'))])


def csr_attribute(identity, values):
    return cert_seq(['oid', identity], cert_set(*values))


def csr_standard_parts(encode=csr_reference, password='saffron secret'):
    san = cert_seq(cert_implicit(2, ['ia5', 'csr.example.org']),
                   cert_uri('https://csr.example.org/enroll'),
                   cert_implicit(7, ['octets', 'c000022c']))
    constraints = cert_seq(['bool', True], ['int', 2])
    extensions = cert_seq(
        cert_seq(['oid', '2.5.29.17'], ['bool', True], ['octets', encode(san).hex()]),
        cert_seq(['oid', '2.5.29.19'], ['octets', encode(constraints).hex()]))
    inner = cert_seq(['oid', '1.2.3.200.12'], cert_set(['utf8', 'nested text'], ['int', 73]))
    unknown = cert_set(['utf8', 'opaque payload'], ['octets', '0081ff'])
    trees = [csr_attribute('1.2.840.113549.1.9.7', [['utf8', password]]),
             csr_attribute('1.2.840.113549.1.9.9', [inner]),
             csr_attribute('1.2.840.113549.1.9.14', [extensions]),
             cert_seq(['oid', '1.2.3.200.99'], unknown)]
    fields = [
        {'type': 'challenge_password', 'values': [DirectoryString(('utf8_string', password))]},
        {'type': 'extended_certificate_attributes', 'values': [
            {'type': '1.2.3.200.12', 'values': [UTF8String('nested text'), Integer(73)]}]},
        {'type': 'extension_request', 'values': [[
            {'extn_id': 'subject_alt_name', 'critical': True,
             'extn_value': ParsableOctetString(encode(san))},
            {'extn_id': 'basic_constraints',
             'extn_value': ParsableOctetString(encode(constraints))}]]},
        {'type': '1.2.3.200.99', 'values': Any.load(encode(unknown))},
    ]
    return fields, trees


def csr_microsoft_parts(encode=csr_reference):
    provider = {'keyspec': 2, 'cspname': 'Enrollment Provider Ω',
                'signature': (1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0)}
    client = {'clientid': 9, 'machinename': 'node.enroll.example.org',
              'username': 'domain\\analyst', 'processname': 'enroll-tool.exe'}
    trees = [csr_attribute('1.3.6.1.4.1.311.13.2.2', [cert_seq(
                 ['int', provider['keyspec']], ['bmp', provider['cspname']], ['bits', '10110010110'])]),
             csr_attribute('1.3.6.1.4.1.311.13.2.3', [['utf8', '10.0.22631'], ['printable', '6.3.9600']]),
             csr_attribute('1.3.6.1.4.1.311.21.20', [cert_seq(
                 ['int', client['clientid']], *(['utf8', client[key]] for key in
                                              ('machinename', 'username', 'processname')))])]
    fields = [{'type': 'microsoft_enrollment_csp_provider', 'values': [provider]},
              {'type': 'microsoft_os_version', 'values': [
                  DirectoryString(('utf8_string', '10.0.22631')),
                  DirectoryString(('printable_string', '6.3.9600'))]},
              {'type': 'microsoft_request_client_info', 'values': [client]}]
    return fields, trees


def csr_document(attributes=None, subject='Enrollment Subject', modulus=3233,
                 signature=b'\x00\x81\xff\x29', ec_signature=False,
                 password='saffron secret', encode=csr_reference):
    components = rsa_components(modulus)
    public = {'algorithm': {'algorithm': 'rsa'},
              'public_key': {key: components[key] for key in ('modulus', 'public_exponent')}}
    public_tree = cert_seq(cert_algorithm('1.2.840.113549.1.1.1'),
        ['bitbytes', encode(cert_seq(['int', modulus], ['int', 17])).hex()])
    fields = {'version': 'v1', 'subject': grouped_name([[('common_name', subject)]]),
              'subject_pk_info': public}
    info = [['int', 0], cert_name(subject), public_tree]
    if attributes is not None:
        if attributes == 'standard':
            values, trees = csr_standard_parts(encode, password)
        elif attributes == 'microsoft':
            values, trees = csr_microsoft_parts(encode)
        elif attributes == 'empty':
            values, trees = [], []
        else:
            raise ValueError('Unknown CSR input description')
        fields['attributes'] = CRIAttributes(values)
        info.append(cert_implicit(0, cert_set(*trees)))
    algorithm = {'algorithm': 'sha384_ecdsa' if ec_signature else 'sha256_rsa'}
    algorithm_tree = cert_seq(['oid', '1.2.840.10045.4.3.3']) if ec_signature else cert_algorithm()
    document = CertificationRequest({'certification_request_info': fields,
                                       'signature_algorithm': algorithm, 'signature': signature})
    return document, encode(cert_seq(cert_seq(*info), algorithm_tree, ['bitbytes', signature.hex()]))


def csr_attributes(document):
    """Read attributes by numeric identity without imposing SET order."""
    return {attribute['type'].dotted: attribute
            for attribute in document['certification_request_info']['attributes']}
