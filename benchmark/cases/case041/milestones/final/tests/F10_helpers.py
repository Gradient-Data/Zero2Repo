# feature: F10
"""Identity inputs attached through the public certificate fields."""
from cobaltform.x509 import Certificate, Extensions, GeneralName, GeneralNames
from F08_helpers import grouped_name
from F09_helpers import certificate_document


def identity_certificates(common_names=(), alternatives=None):
    """Yield a bound certificate and its loaded form, before identity access.

    None omits SAN; an empty sequence attaches an explicitly empty SAN.
    The earlier feature supplies the certificate envelope. Matching oracles
    are supplied by callers, independently of serialization round trips.
    """
    document, _, _ = certificate_document()
    document['tbs_certificate']['subject'] = grouped_name(
        [[('common_name', name)] for name in common_names])
    if alternatives is not None:
        document['tbs_certificate']['extensions'] = Extensions([
            {'extn_id': 'subject_alt_name',
             'extn_value': GeneralNames([
                 GeneralName(name, value) for name, value in alternatives])}])
    wire = document.dump()
    yield document
    yield Certificate.load(wire)
