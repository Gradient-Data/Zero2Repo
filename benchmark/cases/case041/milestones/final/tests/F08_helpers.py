# feature: F08
"""Caller-supplied names and independent, frozen RFC 5280 DER vectors."""
import json
import re
from cobaltform.core import OctetBitString
from cobaltform.x509 import (
    DirectoryString, Name, NameTypeAndValue, RDNSequence, RelativeDistinguishedName,
)
from _helpers import support_path

# Explicit attribute identities and RFC 5280 value encodings; order is the
# public name-building promise, not a runtime read of a product registry.
NAME_ATTRIBUTES = (
    ('incorporation_country', '1.3.6.1.4.1.311.60.2.1.3', 'directory', 'US'),
    ('incorporation_state_or_province', '1.3.6.1.4.1.311.60.2.1.2', 'directory', 'Delaware'),
    ('incorporation_locality', '1.3.6.1.4.1.311.60.2.1.1', 'directory', 'Dover'),
    ('business_category', '2.5.4.15', 'directory', 'Private Organization'),
    ('serial_number', '2.5.4.5', 'printable', 'R-572'),
    ('country_name', '2.5.4.6', 'printable', 'US'),
    ('postal_code', '2.5.4.17', 'directory', '90210'),
    ('state_or_province_name', '2.5.4.8', 'directory', 'California'),
    ('locality_name', '2.5.4.7', 'directory', 'Pasadena'),
    ('street_address', '2.5.4.9', 'directory', '17 Oak Road'),
    ('organization_name', '2.5.4.10', 'directory', 'Research Lab'),
    ('organizational_unit_name', '2.5.4.11', 'directory', 'Physics'),
    ('title', '2.5.4.12', 'directory', 'Scientist'),
    ('common_name', '2.5.4.3', 'directory', 'Nora Lee'),
    ('user_id', '0.9.2342.19200300.100.1.1', 'directory', 'nlee'),
    ('initials', '2.5.4.43', 'directory', 'NL'),
    ('generation_qualifier', '2.5.4.44', 'directory', 'III'),
    ('surname', '2.5.4.4', 'directory', 'Lee'),
    ('given_name', '2.5.4.42', 'directory', 'Nora'),
    ('name', '2.5.4.41', 'directory', 'Nora Lee Scientist'),
    ('pseudonym', '2.5.4.65', 'directory', 'Nova'),
    ('dn_qualifier', '2.5.4.46', 'printable', 'Q-3'),
    ('telephone_number', '2.5.4.20', 'telephone', '+1 555 1234'),
    ('email_address', '1.2.840.113549.1.9.1', 'ia5', 'nora@example.org'),
    ('domain_component', '0.9.2342.19200300.100.1.25', 'ia5', 'example'),
    ('name_distinguisher', '0.2.262.1.10.7.20', 'directory', 'Distinguished'),
    ('organization_identifier', '2.5.4.97', 'directory', 'ORG-128'),
    ('tpm_manufacturer', '2.23.133.2.1', 'utf8', 'Manufacturer A'),
    ('tpm_model', '2.23.133.2.2', 'utf8', 'Model B'),
    ('tpm_version', '2.23.133.2.3', 'utf8', 'Version C'),
    ('platform_manufacturer', '2.23.133.2.4', 'utf8', 'Platform D'),
    ('platform_model', '2.23.133.2.5', 'utf8', 'Model E'),
    ('platform_version', '2.23.133.2.6', 'utf8', 'Version F'),
    ('unique_identifier', '2.5.4.45', 'binary', b'\x00\x80\xff\x12'),
)


def name_vector(label):
    """Read an independent encoding, never a product-derived expected value."""
    data = json.loads(support_path('F08_vectors.json').read_text())
    return bytes.fromhex(data['vectors'][label])


def grouped_name(groups):
    """Construct caller-defined RDN groups through the public name classes."""
    rdns = []
    for group in groups:
        members = []
        for identity, text in group:
            value = (OctetBitString(text) if isinstance(text, bytes)
                     else DirectoryString(('utf8_string', text)))
            members.append(NameTypeAndValue({'type': identity, 'value': value}))
        rdns.append(RelativeDistinguishedName(members))
    return Name(name='', value=RDNSequence(rdns))


def name_groups(value):
    """Read grouped identities and native values without imposing SET order."""
    return [sorted((member['type'].dotted, member['value'].native)
                   for member in rdn) for rdn in value.chosen]


def readable_name_fields(text):
    """Read labelled fields and comma-separated value lists in the public view.

    Multi-value fields use comma-separated values and semicolon-separated
    fields; otherwise fields can be comma-separated. Scenarios exclude
    punctuation inside individual values, so no escaping rule is inferred.
    """
    fields = {}
    for field in text.split('; ' if '; ' in text else ', '):
        label, values = field.split(': ', 1)
        if label in fields:
            raise AssertionError('Duplicate readable name field: %s' % label)
        fields[label] = values.split(', ')
    return fields


def uri_escape_case(value):
    """Canonicalize only RFC 3986 percent-triplet hex case for comparison.

    Reserved characters remain escaped; no path or component is decoded.
    This accepts either spelling of each URI percent triplet.
    """
    pattern = rb'%[0-9A-Fa-f]{2}' if isinstance(value, bytes) else r'%[0-9A-Fa-f]{2}'
    return re.sub(pattern, lambda match: match.group(0).upper(), value)


NAME_DISPLAY_LABELS = (
    'Incorporation Country', 'Incorporation State/Province', 'Incorporation Locality',
    'Business Category', 'Serial Number', 'Country', 'Postal Code', 'State/Province',
    'Locality', 'Street Address', 'Organization', 'Organizational Unit', 'Title',
    'Common Name', 'User ID', 'Initials', 'Generation Qualifier', 'Surname',
    'Given Name', 'Name', 'Pseudonym', 'DN Qualifier', 'Telephone Number',
    'Email Address', 'Domain Component', 'Name Distinguisher', 'Organization Identifier',
    'TPM Manufacturer', 'TPM Model', 'TPM Version', 'Platform Manufacturer',
    'Platform Model', 'Platform Version',
)
