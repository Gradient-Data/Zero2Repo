# feature: F02
"""Independent readers for signed certificate output."""
import base64
import struct
import time

import velnora
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa, dsa, ec, padding
from velnora.public_key import import_certificate_chain
from F01_helpers import (WireReader, ssh_string, read_public_blob, external_key,
                         external_private, identity, read_rfc4716)


def certificate_identity(algorithm='ssh-ed25519'):
    external = external_key(algorithm)
    return velnora.import_private_key(external_private(external, algorithm, 'pkcs8-pem')), external


def certificate_blob(data, fmt='openssh'):
    if fmt == 'openssh':
        return base64.b64decode(data.split()[1], validate=True)
    return read_rfc4716(data)[0]


def signed_openssh(data, issuer, fmt='openssh'):
    """Read the documented OpenSSH certificate packet and verify externally."""
    blob = certificate_blob(data, fmt)
    r = WireReader(blob)
    cert_algorithm = r.string()
    algorithm = cert_algorithm.replace(b'-cert-v01@openssh.com', b'')
    r.string()  # Random nonce has no prescribed value.
    start = r.offset
    count = 4 if algorithm == b'ssh-dss' else (2 if algorithm == b'ssh-rsa' or algorithm.startswith(b'ecdsa-') else 1)
    for _ in range(count):
        r.string()
    subject = read_public_blob(ssh_string(algorithm) + blob[start:r.offset])
    serial = struct.unpack('>Q', r.take(8))[0]
    role, key_id = r.uint32(), r.string().decode()
    principals = WireReader(r.string())
    names = []
    while principals.offset < len(principals.data):
        names.append(principals.string().decode())
    after, before = struct.unpack('>QQ', r.take(16))
    maps = []
    for _ in range(2):
        fields, values = WireReader(r.string()), {}
        while fields.offset < len(fields.data):
            name, value = fields.string().decode(), fields.string()
            values[name] = value
        maps.append(values)
    r.string()  # Reserved field.
    assert identity(read_public_blob(r.string())) == identity(issuer)
    signed = blob[:r.offset]
    signature = WireReader(r.string())
    assert signature.string() == b'ssh-ed25519'
    issuer.public_key().verify(signature.string(), signed)
    signature.finish()
    r.finish()
    return dict(subject=identity(subject), serial=serial, role=role, key_id=key_id,
                principals=names, after=after, before=before,
                options=maps[0], extensions=maps[1])


def x509_der(cert):
    return x509.load_der_x509_certificate(cert.export_certificate('der'))


def authority_chain(*, expired_intermediate=False, depth=1):
    root_key, root_external = certificate_identity()
    intermediate_key, _ = certificate_identity()
    leaf_key, _ = certificate_identity()
    now = int(time.time())
    root = root_key.generate_x509_ca_certificate(root_key, 'CN=Root', ca_path_len=depth)
    intermediate = root_key.generate_x509_ca_certificate(
        intermediate_key, 'CN=Intermediate', 'CN=Root', ca_path_len=0,
        valid_before=now-3600 if expired_intermediate else now+86400)
    leaf = intermediate_key.generate_x509_user_certificate(
        leaf_key, 'CN=Leaf', 'CN=Intermediate', principals=['member'], purposes=None)
    chain = import_certificate_chain(leaf.export_certificate('pem') + intermediate.export_certificate('pem'))
    return root, intermediate, leaf, chain


def verify_x509_signature(cert, public):
    """Verify using the signature algorithm carried by the X.509 certificate."""
    args = (cert.signature, cert.tbs_certificate_bytes)
    if isinstance(public, rsa.RSAPublicKey):
        public.verify(*args, padding.PKCS1v15(), cert.signature_hash_algorithm)
    elif isinstance(public, dsa.DSAPublicKey):
        public.verify(*args, cert.signature_hash_algorithm)
    elif isinstance(public, ec.EllipticCurvePublicKey):
        public.verify(*args, ec.ECDSA(cert.signature_hash_algorithm))
    else:
        public.verify(*args)
