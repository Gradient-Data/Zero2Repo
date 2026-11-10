# feature: F20
"""Acceptance tests for SSHSIG interoperability and signing authorization."""
import base64
import hashlib
import time

import velnora
import pytest

from F20_helpers import (sshsig_identity, signer_document, openssh_command,
                         openssh_signature, openssh_certificate, sshsig_fields,
                         sshsig_packet)


def test_data_files_defaults_and_interoperability(tmp_path):
    """F20.T01: independently created and checked signatures bind data and namespace."""
    key, key_path, public = sshsig_identity(tmp_path, 'signer')
    data = b'Independent SSHSIG message\x00\xff\n' * 451
    path = tmp_path / 'message'
    path.write_bytes(data)
    allowed = signer_document(public)
    allowed_path = tmp_path / 'allowed'
    allowed_path.write_bytes(allowed)
    default = velnora.create_sshsig(key, data)
    magic, version, fields = sshsig_fields(default)
    assert (magic, version) == (b'SSHSIG', 1)
    assert fields[1] == b'file'
    assert fields[3] == b'sha512'
    signature_path = tmp_path / 'product.sig'
    signature_path.write_bytes(default)
    openssh_command('-Y', 'verify', '-f', str(allowed_path), '-I', 'reader',
                    '-n', 'file', '-s', str(signature_path), input=data)
    assert velnora.validate_sshsig(data, default, 'reader', allowed) is True
    for namespace, hash_name in [('file', 'sha256'), ('release', 'sha512')]:
        external = openssh_signature(key_path, path, namespace, hash_name)
        restricted = signer_document(public, options='namespaces="' + namespace + '"')
        assert velnora.validate_sshsig(data, external, 'reader', restricted) is True
        product = velnora.create_sshsig(key, path, namespace=namespace,
                                         hash_name=hash_name, raw=True)
        # OpenSSH accepts the armored public carrier; armor has no crypto semantics.
        signature_path.write_bytes(b'-----BEGIN SSH SIGNATURE-----\n' +
                                  base64.b64encode(product) +
                                  b'\n-----END SSH SIGNATURE-----\n')
        openssh_command('-Y', 'verify', '-f', str(allowed_path), '-I', 'reader',
                        '-n', namespace, '-s', str(signature_path), input=data)
        for signers in (allowed, velnora.import_allowed_signers(allowed.decode()),
                        allowed_path, [str(allowed_path)],
                        velnora.read_allowed_signers(allowed_path)):
            assert velnora.validate_sshsig(path, signature_path, 'reader', signers) is True
        fields = sshsig_fields(product)[2]
        fields[1] = b'another-namespace'
        assert velnora.validate_sshsig(data, sshsig_packet(fields), 'reader', allowed) is False


def test_precomputed_standard_digests(tmp_path):
    """F20.T02: SHA digests correspond to the original message, without rehashing."""
    key, key_path, public = sshsig_identity(tmp_path, 'digest-key')
    data = bytes(range(256)) * 37 + b'ordered suffix'
    path = tmp_path / 'digest-message'
    path.write_bytes(data)
    allowed = signer_document(public)
    for algorithm in ('sha256', 'sha512'):
        digest = hashlib.new(algorithm, data).digest()
        external = openssh_signature(key_path, path, hash_name=algorithm)
        assert velnora.validate_sshsig(digest, external, 'reader', allowed, is_hashed=True) is True
        product = velnora.create_sshsig(key, digest, hash_name=algorithm, is_hashed=True)
        assert velnora.validate_sshsig(data, product, 'reader', allowed) is True
        # Verify the prehashed result against original data with an external tool.
        sig_path = tmp_path / 'digest.sig'
        sig_path.write_bytes(product)
        allowed_path = tmp_path / 'digest-allowed'
        allowed_path.write_bytes(allowed)
        openssh_command('-Y', 'verify', '-f', str(allowed_path), '-I', 'reader',
                        '-n', 'file', '-s', str(sig_path), input=data)
        wrong = hashlib.new(algorithm, data[::-1]).digest()
        assert velnora.validate_sshsig(wrong, external, 'reader', allowed, is_hashed=True) is False
        for invalid in (digest[:-1], digest + b'\x00'):
            with pytest.raises(ValueError):
                velnora.create_sshsig(key, invalid, hash_name=algorithm, is_hashed=True)
            with pytest.raises(ValueError):
                velnora.validate_sshsig(invalid, external, 'reader', allowed, is_hashed=True)


def test_signer_authorization_and_tampering(tmp_path):
    """F20.T03: each authorization restriction is enforced on the verification path."""
    key, _, public = sshsig_identity(tmp_path, 'authorized')
    other, _, _ = sshsig_identity(tmp_path, 'outsider')
    data = b'Authorization requires both identity and signed content.'
    signatures = {ns: velnora.create_sshsig(key, data, namespace=ns)
                  for ns in ('release', 'release-secret', 'other')}
    allowed = signer_document(public, 'team-*,!team-blocked',
                              'namespaces="release*,!release-secret"')
    assert velnora.validate_sshsig(data, signatures['release'], 'team-reader', allowed) is True
    for principal, namespace in [('team-blocked', 'release'), ('outsider', 'release'),
                                 ('team-reader', 'release-secret'), ('team-reader', 'other')]:
        assert velnora.validate_sshsig(data, signatures[namespace], principal, allowed) is False
    assert velnora.validate_sshsig(data + b'changed', signatures['release'], 'team-reader', allowed) is False
    assert velnora.validate_sshsig(data, velnora.create_sshsig(other, data, namespace='release'),
                                    'team-reader', allowed) is False
    fields = sshsig_fields(signatures['release'])[2]
    fields[4] = fields[4][:-1] + bytes([fields[4][-1] ^ 1])
    assert velnora.validate_sshsig(data, sshsig_packet(fields), 'team-reader', allowed) is False
    # Use real UTC wall time; intervals are wide enough to avoid scheduling races.
    for options, expected in [('valid-after=19700101Z,valid-before=29990101Z', True),
                              ('valid-after=29990101Z', False),
                              ('valid-before=19700101Z', False)]:
        assert velnora.validate_sshsig(data, signatures['release'], 'reader',
                                        signer_document(public, options=options)) is expected
    now = time.strftime('%Y%m%d%H%M%SZ', time.gmtime())
    assert velnora.validate_sshsig(data, signatures['release'], 'reader',
                                    signer_document(public, options='valid-after=' + now)) is True
    assert velnora.validate_sshsig(data, signatures['release'], 'reader',
                                    signer_document(public, options='valid-before=' + now)) is False


def test_authority_certificates_and_direct_keys(tmp_path):
    """F20.T04: authority trust checks independent certificates; direct key trust is distinct."""
    ca, ca_path, ca_public = sshsig_identity(tmp_path, 'authority')
    key, key_path, public = sshsig_identity(tmp_path, 'subject')
    _, _, untrusted = sshsig_identity(tmp_path, 'untrusted')
    data = b'Certificate authorized content'
    allowed = signer_document(ca_public, '*', 'cert-authority')
    for validity, principal, expected in [('-1h:+1h', 'reader', True),
                                          ('-1h:+1h', 'other', False),
                                          ('-2h:-1h', 'reader', False),
                                          ('+1h:+2h', 'reader', False)]:
        cert_data = openssh_certificate(ca_path, key_path, validity=validity)
        cert = velnora.import_certificate(cert_data)
        sig = velnora.create_sshsig((key, cert), data)
        assert velnora.validate_sshsig(data, sig, principal, allowed) is expected
        assert velnora.validate_sshsig(data, sig, principal, signer_document(public, '*')) is True
        assert velnora.validate_sshsig(data, sig, principal,
                                        signer_document(untrusted, '*', 'cert-authority')) is False
    cert = velnora.import_certificate(openssh_certificate(ca_path, key_path))
    good = velnora.create_sshsig((key, cert), data, raw=True)
    assert velnora.validate_sshsig(data, good, 'reader', allowed) is True
    fields = sshsig_fields(good)[2]
    fields[0] = fields[0][:-1] + bytes([fields[0][-1] ^ 1])
    assert velnora.validate_sshsig(data, sshsig_packet(fields), 'reader', allowed) is False
    assert velnora.validate_sshsig(data, velnora.create_sshsig(key, data), 'reader', allowed) is False


def test_invalid_signing_signature_and_signer_inputs(tmp_path):
    """F20.T05: malformed signatures fail, while invalid requests/configuration raise."""
    key, _, public = sshsig_identity(tmp_path, 'errors')
    data = b'Valid baseline before malformed input'
    allowed = signer_document(public)
    valid = velnora.create_sshsig(key, data, raw=True)
    assert velnora.validate_sshsig(data, valid, 'reader', allowed) is True
    for settings in ({'hash_name': 'sha1'}, {'namespace': ''}, {'key': []}):
        selected = dict(settings)
        selected_key = selected.pop('key', key)
        with pytest.raises(ValueError):
            velnora.create_sshsig(selected_key, data, **selected)
    x509 = key.generate_x509_user_certificate(key, 'CN=Signer')
    with pytest.raises(ValueError):
        velnora.create_sshsig((key, x509), data)
    fields = sshsig_fields(valid)[2]
    malformed = [b'xxx', b'-', b'-----BEGIN WRONG-----\n',
                 b'-----BEGIN SSH SIGNATURE-----\n',
                 b'-----BEGIN SSH SIGNATURE-----\nXXX\n-----END SSH SIGNATURE-----\n',
                 valid[:6], valid[:-1], sshsig_packet(fields, version=2),
                 sshsig_packet(fields, magic=b'WRONG!')]
    for index, replacement in [(0, b'not a key'), (1, b'\xff'), (4, b'')]:
        changed = list(fields)
        changed[index] = replacement
        malformed.append(sshsig_packet(changed))
    for signature in malformed:
        assert velnora.validate_sshsig(data, signature, 'reader', allowed) is False
    for index, replacement in [(1, b''), (3, b'sha1')]:
        changed = list(fields)
        changed[index] = replacement
        with pytest.raises(ValueError):
            velnora.validate_sshsig(data, sshsig_packet(changed), 'reader', allowed)
    for document in ('\n', '*\n', '* xxx\n', '* xxx"\n', '* xxx\\\n', '* =xxx\n'):
        with pytest.raises(ValueError):
            velnora.import_allowed_signers(document)
        with pytest.raises(ValueError):
            velnora.validate_sshsig(data, valid, 'reader', document.encode())
