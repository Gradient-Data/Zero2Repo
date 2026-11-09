# feature: F02
"""Acceptance tests for certificate issuance, transport and identity validation."""
import os
import base64
import time
from datetime import timezone

import velnora
import pytest
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID

from F01_helpers import ALGORITHMS, identity, WireReader
from velnora.public_key import import_certificate_chain
from F02_helpers import (certificate_identity, signed_openssh, x509_der,
                         authority_chain, verify_x509_signature)


def test_openssh_issuance():
    """F02.T01: signed roles, identities, defaults and validity boundaries."""
    ca, issuer = certificate_identity()
    for algorithm in ALGORITHMS:
        subject, external = certificate_identity(algorithm)
        for role, issue in ((1, ca.generate_user_certificate), (2, ca.generate_host_certificate)):
            default = issue(subject.convert_to_public(), 'default identity')
            fields = signed_openssh(default.export_certificate(), issuer)
            assert fields['subject'] == identity(external)
            assert fields['role'] == role
            assert fields['key_id'] == 'default identity'
            assert fields['serial'] == 0
            assert fields['principals'] == []
            assert fields['after'] == 0
            assert fields['before'] == 2**64-1
            selected = issue(subject, 'selected identity', serial=731,
                             principals=['first', 'second'], valid_after=1234, valid_before=987654)
            fields = signed_openssh(selected.export_certificate(), issuer)
            assert fields['subject'] == identity(external)
            assert (fields['role'], fields['key_id'], fields['serial']) == (role, 'selected identity', 731)
            assert set(fields['principals']) == {'first', 'second'}
            assert (fields['after'], fields['before']) == (1234, 987654)
    now = int(time.time())
    ca.generate_user_certificate(subject, 'start', valid_after=now).validate(1, None)
    for options in ({'valid_before': now}, {'valid_after': now+3600}):
        with pytest.raises(ValueError):
            ca.generate_user_certificate(subject, 'outside', **options).validate(1, None)
    # Validate against the real clock: the current second has begun, and its
    # exclusive end is already expired when validation observes it.
    starting = ca.generate_user_certificate(subject, 'start', valid_after=now, valid_before=now+3600)
    ending = ca.generate_user_certificate(subject, 'end', valid_after=now-3600, valid_before=now)
    starting.validate(1, None)
    with pytest.raises(ValueError):
        ending.validate(1, None)
    for options in ({'version': 0}, {'version': 2}):
        with pytest.raises(velnora.KeyGenerationError):
            ca.generate_user_certificate(subject, 'invalid', **options)
    for after, before in ((8, 8), (9, 8)):
        with pytest.raises(ValueError):
            ca.generate_user_certificate(subject, 'invalid', valid_after=after, valid_before=before)


def test_openssh_restrictions_and_files(tmp_path):
    """F02.T02: each permission is independent and signed restrictions survive transport."""
    ca, issuer = certificate_identity()
    subject, _ = certificate_identity()
    permissions = {'permit_x11_forwarding': 'permit-X11-forwarding',
                   'permit_agent_forwarding': 'permit-agent-forwarding',
                   'permit_port_forwarding': 'permit-port-forwarding',
                   'permit_pty': 'permit-pty', 'permit_user_rc': 'permit-user-rc'}
    selections = [{}] + [{option: False} for option in permissions]
    selections += [{option: option == enabled for option in permissions}
                   for enabled in permissions]
    for selected in selections:
        cert = ca.generate_user_certificate(
            subject, 'restricted', force_command='run --safe',
            source_address=['192.0.2.0/24', '2001:db8::/32'],
            **selected)
        for fmt in ('openssh', 'rfc4716'):
            data = cert.export_certificate(fmt)
            path = tmp_path / 'certificates'
            cert.write_certificate(path, fmt)
            cert.append_certificate(path, fmt)
            loaded = [velnora.import_certificate(data), velnora.read_certificate(path),
                      *velnora.read_certificate_list(path)]
            assert len(velnora.read_certificate_list(path)) == 2
            for item in loaded:
                fields = signed_openssh(item.export_certificate(fmt), issuer, fmt)
                for name, expected in (('force-command', b'run --safe'),
                                       ('source-address', b'192.0.2.0/24,2001:db8::/32')):
                    value = WireReader(fields['options'][name])
                    decoded = value.string()
                    if name == 'source-address':
                        assert set(decoded.split(b',')) == set(expected.split(b','))
                    else:
                        assert decoded == expected
                    value.finish()
                for option, extension in permissions.items():
                    assert (extension in fields['extensions']) == selected.get(option, True)


def test_x509_issuance_and_formats(tmp_path):
    """F02.T03: independently inspect and verify X.509 user, host and CA output."""
    ca, issuer = certificate_identity()
    for algorithm in ALGORITHMS:
        key, external = certificate_identity(algorithm)
        ca, issuer = certificate_identity(algorithm)
        for role in ('user', 'host', 'ca'):
            options = dict(issuer='CN=Issuer', serial=1947, valid_after=1600000000,
                           valid_before=2000000000)
            if role == 'ca':
                options['ca_path_len'] = 2
            else:
                options.update(principals=['alpha', 'beta'], purposes=['1.3.6.1.5.5.7.3.21'])
            cert = getattr(ca, 'generate_x509_' + role + '_certificate')(key, 'CN=Subject', **options)
            for fmt in ('der', 'pem', 'openssh'):
                data = cert.export_certificate(fmt)
                path = tmp_path / 'x509'
                path.write_bytes(data)
                for loaded in (velnora.import_certificate(data), velnora.read_certificate(path)):
                    parsed = x509_der(loaded)
                    assert identity(parsed.public_key()) == identity(external)
                    assert parsed.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'Subject'
                    assert parsed.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'Issuer'
                    assert parsed.serial_number == 1947
                    assert parsed.not_valid_before.replace(tzinfo=timezone.utc).timestamp() == 1600000000
                    assert parsed.not_valid_after.replace(tzinfo=timezone.utc).timestamp() == 2000000000
                    verify_x509_signature(parsed, issuer.public_key())
                    constraints = parsed.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS).value
                    assert constraints.ca == (role == 'ca')
                    if role == 'ca':
                        assert constraints.path_length == 2
                    else:
                        # Principals are carried as subject alternative names; the
                        # general-name type is not a promised value.
                        names = parsed.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
                        carried = {str(getattr(name, 'value', name)) for name in names}
                        assert {'alpha', 'beta'} <= carried
                        assert {oid.dotted_string for oid in parsed.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE).value} == {'1.3.6.1.5.5.7.3.21'}
    for signer_type, subject_type, digest in (('ssh-ed25519', 'ssh-dss', ''),
                                              ('ssh-rsa', 'ssh-ed448', 'sha256')):
        signer, issuer = certificate_identity(signer_type)
        subject, external = certificate_identity(subject_type)
        cert = signer.generate_x509_user_certificate(subject, 'CN=Cross family', hash_alg=digest)
        parsed = x509_der(cert)
        assert identity(parsed.public_key()) == identity(external)
        verify_x509_signature(parsed, issuer.public_key())
    root, intermediate, leaf, chain = authority_chain()
    # Signature checks are independent of the product's own chain validator.
    verify_x509_signature(x509_der(intermediate), x509_der(root).public_key())
    verify_x509_signature(x509_der(leaf), x509_der(intermediate).public_key())
    assert chain.validate_chain([root], [], set(), None, 'member') is None
    loaded = velnora.load_certificates([leaf.export_certificate('pem'), intermediate.export_certificate('pem')])
    assert [x509_der(c).serial_number for c in loaded] == [x509_der(c).serial_number for c in (leaf, intermediate)]
    for data in (b'not certificate material', b'-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n', leaf.export_certificate('der')[:30]):
        with pytest.raises(velnora.KeyImportError):
            velnora.import_certificate(data)


def test_certificate_key_association():
    """F02.T04: associated identities expose the certificate and prove private possession."""
    ca, issuer = certificate_identity()
    keys = [certificate_identity() for _ in range(2)]
    certs = [ca.generate_user_certificate(key, str(i)) for i, (key, _) in enumerate(keys)]
    explicit = [velnora.load_keypairs([(key, cert)])[0] for (key, _), cert in zip(keys, certs)]
    separate = velnora.load_keypairs([key for key, _ in keys], certlist=list(reversed(certs)))
    certified = [pair for pair in separate if pair.has_cert]
    assert len(certified) == 2
    for pairs in (explicit, certified):
        expected = {identity(external): external for _, external in keys}
        observed = set()
        for pair in pairs:
            assert pair.has_cert
            encoded = pair.get_algorithm().encode() + b' ' + base64.b64encode(pair.public_data)
            subject = signed_openssh(encoded, issuer)['subject']
            assert subject in expected
            observed.add(subject)
            external = expected[subject]
            challenge = os.urandom(64)
            signature = WireReader(pair.sign(challenge))
            assert signature.string() == b'ssh-ed25519'
            external.public_key().verify(signature.string(), challenge)
            signature.finish()
        assert observed == set(expected)
    with pytest.raises(ValueError):
        velnora.load_keypairs([(keys[0][0], certs[1])])
    pair = velnora.load_keypairs([keys[0][0]])[0]
    with pytest.raises(ValueError):
        pair.set_certificate(certs[1])


def test_x509_chain_validation():
    """F02.T05: trust, completeness, time and subordinate depth are enforced."""
    root, intermediate, leaf, chain = authority_chain()
    assert chain.validate_chain([root], [], set(), None, 'member') is None
    unrelated, _, _, _ = authority_chain()
    for roots in ([], [unrelated]):
        with pytest.raises(ValueError):
            chain.validate_chain(roots, [], set(), None, 'member')
    incomplete = import_certificate_chain(leaf.export_certificate('pem'))
    with pytest.raises(ValueError):
        incomplete.validate_chain([root], [], set(), None, 'member')
    for options in ({'expired_intermediate': True}, {'depth': 0}):
        root, _, _, chain = authority_chain(**options)
        with pytest.raises(ValueError):
            chain.validate_chain([root], [], set(), None, 'member')
    key, _ = certificate_identity()
    now = int(time.time())
    for validity in ({'valid_before': now-3600}, {'valid_after': now+3600}):
        expired = key.generate_x509_user_certificate(key, 'CN=Time', purposes=None, **validity)
        with pytest.raises(ValueError):
            expired.validate_chain([], [expired], [], None)


def test_x509_principal_validation():
    """F02.T06: SAN principals and common-name fallback require exact matches."""
    key, _ = certificate_identity()
    for role in ('user', 'host'):
        issue = getattr(key, 'generate_x509_' + role + '_certificate')
        for principals in ([], ['exact.example', 'other.example']):
            cert = issue(key, 'CN=common.example', principals=principals, purposes=None)
            good = principals or ['common.example']
            for name in good:
                assert cert.validate_chain([], [cert], [], None, **{role+'_principal': name}) is None
            for name in ('prefix.exact.example', 'exact.example.extra', 'common.example' if principals else 'common.example.extra'):
                with pytest.raises(ValueError):
                    cert.validate_chain([], [cert], [], None, **{role+'_principal': name})


def test_x509_purpose_validation():
    """F02.T07: any matching OID suffices, absent restrictions and disabled checks work."""
    key, _ = certificate_identity()
    client, server = '1.3.6.1.5.5.7.3.21', '1.3.6.1.5.5.7.3.22'
    cert = key.generate_x509_user_certificate(key, 'CN=Purpose', purposes=[client])
    for purposes in ([client], [server, client], None, 'any'):
        assert cert.validate_chain([], [cert], [], purposes) is None
    with pytest.raises(ValueError):
        cert.validate_chain([], [cert], [], [server])
    unrestricted = key.generate_x509_user_certificate(key, 'CN=Unrestricted', purposes=None)
    assert unrestricted.validate_chain([], [unrestricted], [], [server]) is None
    # Disabling the check must accept a purpose other than any default selection.
    server_only = key.generate_x509_user_certificate(key, 'CN=Server only', purposes=[server])
    for purposes in (None, 'any'):
        assert server_only.validate_chain([], [server_only], [], purposes) is None
    with pytest.raises(ValueError):
        server_only.validate_chain([], [server_only], [], [client])
