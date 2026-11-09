# feature: F01
"""Acceptance checks for software keys and portable authenticator references."""
import base64
import os

import velnora
import pytest
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric import dsa, rsa, ec, ed25519, ed448

from _helpers import digest
from F01_helpers import (
    ALGORITHMS, CURVES, external_key, identity, ssh_string, WireReader,
    public_blob, read_public, external_public, public_formats, private_formats,
    external_private, read_private, authenticate, decrypt_openssh,
    openssh_container, read_openssh_container, pem_payload,
    rfc4716_comment, fingerprint_bytes,
)

# DER encoding of the AES-256-CBC object identifier 2.16.840.1.101.3.4.1.42.
AES256_CBC_OID = bytes.fromhex('060960864801650304012a')


def test_generation():
    """F01.T01: generated keys meet the selected family and parameters."""
    for algorithm in ALGORITHMS:
        key = velnora.generate_private_key(algorithm)
        public = read_public(key.export_public_key('pkcs8-der'), 'pkcs8-der', algorithm)
        private = read_private(key.export_private_key(), 'openssh')
        assert identity(private) == identity(public)
        assert identity(read_public(key.export_public_key(), 'openssh', algorithm)) == identity(public)
        if algorithm == 'ssh-rsa':
            assert isinstance(public, rsa.RSAPublicKey)
            assert public.key_size == 2048
            assert public.public_numbers().e == 65537
        elif algorithm == 'ssh-dss':
            assert isinstance(public, dsa.DSAPublicKey)
            assert public.key_size == 1024
        elif algorithm.startswith('ecdsa-'):
            assert isinstance(public, ec.EllipticCurvePublicKey)
            assert public.curve.name == CURVES[algorithm[11:]]().name
        else:
            assert isinstance(public, {'ssh-ed25519': ed25519.Ed25519PublicKey,
                                       'ssh-ed448': ed448.Ed448PublicKey}[algorithm])
    # Size and exponent vary independently; no Cartesian matrix is needed.
    for options in ({'key_size': 1024}, {'key_size': 3072}, {'exponent': 3}):
        key = velnora.generate_private_key('ssh-rsa', **options)
        public = read_public(key.export_public_key('pkcs8-der'), 'pkcs8-der', 'ssh-rsa')
        assert public.key_size == options.get('key_size', 2048)
        assert public.public_numbers().e == options.get('exponent', 65537)
    for algorithm, options in (
        ('not-a-key', {}), ('ssh-rsa', {'key_size': 512}),
        ('ssh-rsa', {'exponent': 5}),
        ('ssh-dss', {'key_size': 2048}), ('ecdsa-sha2-unknown', {}),
        ('ssh-ed25519', {'key_size': 256}),
    ):
        with pytest.raises(velnora.KeyGenerationError):
            velnora.generate_private_key(algorithm, **options)


def test_public_formats(tmp_path):
    """F01.T02: external public keys and all export forms interoperate."""
    for algorithm in ALGORITHMS:
        external = external_key(algorithm)
        expected = identity(external)
        for fmt in public_formats(algorithm):
            material = external_public(external, algorithm, fmt)
            path = tmp_path / 'public'
            path.write_bytes(material)
            for loaded in (velnora.import_public_key(material), velnora.read_public_key(path)):
                exported = loaded.export_public_key(fmt)
                assert identity(read_public(exported, fmt, algorithm)) == expected
                reloaded = velnora.import_public_key(exported)
                assert identity(read_public(reloaded.export_public_key('pkcs8-der'), 'pkcs8-der', algorithm)) == expected
        loaded = velnora.import_public_key(external_public(external, algorithm, 'openssh'))
        with pytest.raises(velnora.KeyExportError):
            loaded.export_public_key('unknown-format')
        if algorithm not in ('ssh-dss', 'ssh-rsa'):
            for fmt in ('pkcs1-der', 'pkcs1-pem'):
                with pytest.raises(velnora.KeyExportError):
                    loaded.export_public_key(fmt)


def test_private_formats_and_authentication(tmp_path):
    """F01.T03: externally generated private keys retain signing capability."""
    for algorithm in ALGORITHMS:
        external = external_key(algorithm)
        for fmt in private_formats(algorithm):
            material = external_private(external, algorithm, fmt)
            path = tmp_path / 'private'
            path.write_bytes(material)
            for loaded in (velnora.import_private_key(material), velnora.read_private_key(path)):
                assert identity(read_private(loaded.export_private_key(fmt), fmt)) == identity(external)
                authenticate(loaded, external.public_key(), algorithm, os.urandom(49))
                reloaded = velnora.import_private_key(loaded.export_private_key(fmt))
                authenticate(reloaded, external.public_key(), algorithm, os.urandom(61))
        loaded = velnora.import_private_key(external_private(external, algorithm, 'pkcs8-pem'))
        with pytest.raises(velnora.KeyExportError):
            loaded.export_private_key('unknown-format')
        if algorithm in ('ssh-ed25519', 'ssh-ed448'):
            for fmt in ('pkcs1-der', 'pkcs1-pem'):
                with pytest.raises(velnora.KeyExportError):
                    loaded.export_private_key(fmt)


def test_private_key_protection(tmp_path):
    """F01.T04: encryption requires the password and preserves real secrets."""
    password = b'a separate passphrase with spaces'
    for algorithm in ALGORITHMS:
        external = external_key(algorithm)
        loaded = velnora.import_private_key(external_private(external, algorithm, 'pkcs8-pem'))
        public_only = velnora.import_public_key(external_public(external, algorithm, 'pkcs8-pem'))
        for fmt in private_formats(algorithm):
            with pytest.raises(velnora.KeyExportError):
                public_only.export_private_key(fmt)
        formats = ['openssh', 'pkcs8-der', 'pkcs8-pem']
        if 'pkcs1-pem' in private_formats(algorithm):
            formats.append('pkcs1-pem')
        for fmt in formats:
            options = {'cipher_name': 'aes256-cbc'}
            if fmt == 'openssh':
                options.update(rounds=16, ignore_few_rounds=True)
            protected = loaded.export_private_key(fmt, passphrase=password, **options)
            independent = decrypt_openssh(protected, password) if fmt == 'openssh' else read_private(protected, fmt, password)
            assert identity(independent) == identity(external)
            # The selected cipher is named by each container's standard carrier.
            if fmt == 'pkcs1-pem':
                assert b'\nDEK-Info: AES-256-CBC,' in protected
            elif fmt.startswith('pkcs8'):
                der = pem_payload(protected) if fmt.endswith('pem') else protected
                assert AES256_CBC_OID in der
            if fmt != 'openssh':
                with pytest.raises(TypeError):
                    read_private(protected, fmt)
                with pytest.raises(ValueError):
                    read_private(protected, fmt, b'incorrect')
            for supplied in (password, password.decode()):
                recovered = velnora.import_private_key(protected, supplied)
                authenticate(recovered, external.public_key(), algorithm, os.urandom(53))
            path = tmp_path / 'encrypted'
            path.write_bytes(protected)
            recovered = velnora.read_private_key(path, password)
            authenticate(recovered, external.public_key(), algorithm, os.urandom(47))
            for supplied in (None, b'incorrect'):
                with pytest.raises((velnora.KeyImportError, velnora.KeyEncryptionError)):
                    velnora.import_private_key(protected, supplied)
            clear = loaded.export_private_key(fmt)
            assert identity(read_private(clear, fmt)) == identity(external)
        if 'pkcs1-der' in private_formats(algorithm):
            with pytest.raises(velnora.KeyExportError):
                loaded.export_private_key('pkcs1-der', passphrase=password)
    for material in (b'not a key', b'-----BEGIN PRIVATE KEY-----\n%%%%\n-----END PRIVATE KEY-----\n'):
        with pytest.raises(velnora.KeyImportError):
            velnora.import_private_key(material)
        with pytest.raises(velnora.KeyImportError):
            velnora.import_public_key(material)


def test_comments_and_key_files(tmp_path):
    """F01.T05: comments and written/appended identity collections survive."""
    algorithm = 'ssh-rsa'
    external = [external_key(algorithm), external_key(algorithm)]
    keys = [velnora.import_private_key(external_private(key, algorithm, 'pkcs8-pem')) for key in external]
    for key in keys:
        assert key.get_comment() is None
        for comment in ('first note', 'changed note π'):
            key.set_comment(comment)
            assert key.get_comment() == comment
            for fmt in ('openssh', 'rfc4716'):
                assert velnora.import_public_key(key.export_public_key(fmt)).get_comment() == comment
            assert velnora.import_private_key(key.export_private_key()).get_comment() == comment
            # The comment travels in each format's standard comment carrier.
            assert key.export_public_key('openssh').rstrip(b'\n').split(None, 2)[2] == comment.encode()
            assert rfc4716_comment(key.export_public_key('rfc4716')) == comment.encode()
            _, block = read_openssh_container(key.export_private_key())
            assert block.string() == b'ssh-rsa'
            for _ in range(6):
                block.string()
            assert block.string() == comment.encode()
            external_line = external_public(external[0], algorithm, 'openssh').rstrip(b'\n')
            assert velnora.import_public_key(external_line + b' ' + comment.encode() + b'\n').get_comment() == comment
        key.set_comment(None)
        assert key.get_comment() is None
    for private, formats in ((False, public_formats(algorithm)), (True, private_formats(algorithm))):
        for fmt in formats:
            path = tmp_path / 'collection'
            # A write must replace existing material; append must preserve it.
            path.write_bytes(b'obsolete content')
            writer = keys[0].write_private_key if private else keys[0].write_public_key
            appender = keys[1].append_private_key if private else keys[1].append_public_key
            writer(path, fmt)
            single = path.read_bytes()
            reader = read_private if private else lambda data, form: read_public(data, form, algorithm)
            assert identity(reader(single, fmt)) == identity(external[0])
            appender(path, fmt)
            combined = path.read_bytes()
            assert combined[:len(single)] == single
            assert identity(reader(combined[len(single):], fmt)) == identity(external[1])
            collection = velnora.read_private_key_list(path) if private else velnora.read_public_key_list(path)
            # Identity, not collection order, is the promised outcome.
            assert len(collection) == 2
            assert {identity(read_public(key.export_public_key('pkcs8-der'), 'pkcs8-der', algorithm)) for key in collection} == {identity(key) for key in external}


def test_fingerprints():
    """F01.T06: independent RFC wire encodings and standard digests agree."""
    for algorithm in ALGORITHMS:
        if algorithm == 'ecdsa-sha2-1.3.132.0.10':
            continue  # The fingerprint requirement specifies NIST ECDSA.
        external = external_key(algorithm)
        private = velnora.import_private_key(external_private(external, algorithm, 'pkcs8-pem'))
        public = velnora.import_public_key(external_public(external, algorithm, 'pkcs8-pem'))
        wire = public_blob(external, algorithm)
        for name in ('md5', 'sha1', 'sha256', 'sha384', 'sha512'):
            raw = digest(wire, name)
            assert fingerprint_bytes(private.get_fingerprint(name), name) == raw
            assert fingerprint_bytes(public.get_fingerprint(name), name) == raw
            if name == 'sha256':
                assert fingerprint_bytes(private.get_fingerprint(), name) == raw
                assert fingerprint_bytes(public.get_fingerprint(), name) == raw
        with pytest.raises(ValueError):
            private.get_fingerprint('not-a-digest')


def test_security_key_references():
    """F01.T07: portable OpenSSH references keep identity and application."""
    for algorithm in ('sk-ecdsa-sha2-nistp256@openssh.com', 'sk-ssh-ed25519@openssh.com'):
        external = external_key('ecdsa-sha2-nistp256' if algorithm.startswith('sk-ecdsa') else 'ssh-ed25519')
        if algorithm.startswith('sk-ecdsa'):
            public_fields = ssh_string(b'nistp256') + ssh_string(external.public_key().public_bytes(ser.Encoding.X962, ser.PublicFormat.UncompressedPoint))
        else:
            public_fields = ssh_string(external.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw))
        for application in (b'ssh:', b'ssh:portable-identity'):
            public = ssh_string(algorithm) + public_fields + ssh_string(application)
            # These are opaque portable reference bytes, not simulated hardware.
            handle = os.urandom(37)
            fields = public + b'\x01' + ssh_string(handle) + ssh_string(b'')
            material = openssh_container(public, fields)
            private = velnora.import_private_key(material)
            pub_line = algorithm.encode() + b' ' + base64.b64encode(public) + b'\n'
            public_only = velnora.import_public_key(pub_line)
            for key in (private, public_only):
                exported = key.export_public_key()
                assert exported.split()[0] == algorithm.encode()
                assert base64.b64decode(exported.split()[1], validate=True) == public
            exported = private.export_private_key()
            exported_public, reader = read_openssh_container(exported)
            assert exported_public == public
            assert reader.string() == algorithm.encode()
            if algorithm.startswith('sk-ecdsa'):
                assert reader.string() == b'nistp256'
                assert reader.string() == external.public_key().public_bytes(ser.Encoding.X962, ser.PublicFormat.UncompressedPoint)
            else:
                assert reader.string() == external.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
            assert reader.string() == application
            reader.take(1)  # Flags are not an asserted value in this feature.
            reader.string()  # Opaque authenticator handle.
            reader.string()  # Reserved field.
            # Reload the exported reference and observe its public identity again.
            assert base64.b64decode(velnora.import_private_key(exported).export_public_key().split()[1]) == public
            with pytest.raises(velnora.KeyExportError):
                private.export_private_key('pkcs8-pem')
