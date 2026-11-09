# feature: F05
"""Real OpenSSH agent lifecycle and independent signature observations."""
import base64
from contextlib import asynccontextmanager, contextmanager

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, utils

from _helpers import environment, managed_service, run_command
from F01_helpers import WireReader, external_key, external_private, public_blob


@asynccontextmanager
async def local_agent(directory):
    socket = directory / 'agent.sock'
    decision = directory / 'confirmation'
    decision.write_text('1')
    askpass = directory / 'askpass'
    askpass.write_text('#!/bin/sh\nexit "$(cat "$F05_CONFIRMATION")"\n')
    askpass.chmod(0o700)
    env = environment({'SSH_AUTH_SOCK': str(socket), 'SSH_ASKPASS': str(askpass),
                       'SSH_ASKPASS_REQUIRE': 'force', 'DISPLAY': ':0',
                       'F05_CONFIRMATION': str(decision), 'LC_ALL': 'C'})
    async with managed_service(['ssh-agent', '-D', '-a', str(socket)], env=env,
                               ready=lambda service: socket.exists()):
        yield socket, env, decision


def agent_material(directory, algorithm, name):
    external = external_key(algorithm)
    path = directory / name
    path.write_bytes(external_private(external, algorithm, 'openssh'))
    path.chmod(0o600)
    blob = public_blob(external, algorithm)
    path.with_suffix('.pub').write_bytes(
        algorithm.encode() + b' ' + base64.b64encode(blob) + b' ' + name.encode() + b'\n')
    return path, external, blob


def agent_inventory(env):
    """Read ssh-add's public identity listing; query failures remain failures."""
    result = run_command(['ssh-add', '-L'], env=env)
    if result.returncode == 1:
        # OpenSSH also uses status 1 for query failures. Only its explicit
        # empty-inventory response is absence; every other response fails.
        assert result.stdout == b'The agent has no identities.\n', (result.stdout, result.stderr)
        return set()
    assert result.returncode == 0, (result.returncode, result.stderr)
    return {base64.b64decode(line.split()[1], validate=True)
            for line in result.stdout.splitlines()}


def verify_agent_signature(signature, public, algorithm, message):
    """Verify the SSH signature using an independent cryptographic backend."""
    packet = WireReader(signature)
    signature_algorithm, raw = packet.string(), packet.string()
    packet.finish()
    expected = b'rsa-sha2-256' if algorithm == 'ssh-rsa' else algorithm.encode()
    assert signature_algorithm == expected
    if algorithm == 'ssh-rsa':
        public.verify(raw, message, padding.PKCS1v15(), hashes.SHA256())
    elif algorithm.startswith('ecdsa-'):
        parts = WireReader(raw)
        r, s = parts.integer(), parts.integer()
        parts.finish()
        public.verify(utils.encode_dss_signature(r, s), message, ec.ECDSA(hashes.SHA256()))
    else:
        public.verify(raw, message)


async def agent_proof(key, external, algorithm):
    for message in (b'agent proof\x00first', b'a different signing challenge\xff'):
        key.set_sig_algorithm(b'rsa-sha2-256' if algorithm == 'ssh-rsa' else algorithm.encode())
        signature = await key.sign_async(message)
        verify_agent_signature(signature, external.public_key(), algorithm, message)


@contextmanager
def token_provider(directory):
    """Initialize real, isolated SoftHSM tokens with independent key material."""
    import tarfile
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    import pkcs11
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.x509.oid import NameOID
    from _helpers import temporary_environment

    bundle = directory / 'provider'
    bundle.mkdir()
    with tarfile.open(Path(__file__).with_name('F05_softhsm.tar.gz')) as archive:
        archive.extractall(bundle, filter='data')
    provider = bundle / 'usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so'
    util = bundle / 'usr/bin/softhsm2-util'
    tokens = directory / 'tokens'
    tokens.mkdir()
    config = directory / 'softhsm.conf'
    config.write_text(f'directories.tokendir = {tokens}\nobjectstore.backend = file\nlog.level = ERROR\n')
    pin = '482719'
    with temporary_environment({'SOFTHSM2_CONF': str(config)}):
        for label in ('alpha', 'beta'):
            run_command([util, '--module', provider, '--init-token', '--free',
                         '--label', label, '--so-pin', '82461973', '--pin', pin], check=True)
        library = pkcs11.lib(str(provider))
        serials = {label: library.get_token(token_label=label).serial
                   for label in ('alpha', 'beta')}
        materials = []
        for index, (token_label, algorithm, label, key_id) in enumerate((
                ('alpha', 'ssh-rsa', 'shared', b'\x11'),
                ('alpha', 'ecdsa-sha2-nistp256', 'curve', b'\x22'),
                ('beta', 'ecdsa-sha2-nistp256', 'shared', b'\x22'))):
            external = external_key(algorithm)
            path = directory / f'token-key-{index}.pem'
            path.write_bytes(external_private(external, algorithm, 'pkcs8-pem'))
            if algorithm == 'ssh-rsa':
                run_command([util, '--module', provider, '--import', path,
                             '--token', token_label, '--label', label,
                             '--id', key_id.hex(), '--pin', pin], check=True)
            else:
                from asn1crypto.core import OctetString, ObjectIdentifier
                point = external.public_key().public_bytes(
                    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
                with library.get_token(token_label=token_label).open(user_pin=pin, rw=True) as session:
                    session.create_object({
                        pkcs11.Attribute.CLASS: pkcs11.ObjectClass.PRIVATE_KEY,
                        pkcs11.Attribute.KEY_TYPE: pkcs11.KeyType.EC,
                        pkcs11.Attribute.TOKEN: True,
                        pkcs11.Attribute.PRIVATE: True,
                        pkcs11.Attribute.SIGN: True,
                        pkcs11.Attribute.SENSITIVE: True,
                        pkcs11.Attribute.EXTRACTABLE: False,
                        pkcs11.Attribute.LABEL: label,
                        pkcs11.Attribute.ID: key_id,
                        pkcs11.Attribute.EC_PARAMS: ObjectIdentifier('1.2.840.10045.3.1.7').dump(),
                        pkcs11.Attribute.EC_POINT: OctetString(point).dump(),
                        pkcs11.Attribute.VALUE: external.private_numbers().private_value.to_bytes(32, 'big')})
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'{token_label}-{label}')])
            now = datetime.now(timezone.utc)
            cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                    .public_key(external.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1))
                    .sign(external, hashes.SHA256()))
            der = cert.public_bytes(serialization.Encoding.DER)
            with library.get_token(token_label=token_label).open(user_pin=pin, rw=True) as session:
                session.create_object({
                    pkcs11.Attribute.CLASS: pkcs11.ObjectClass.CERTIFICATE,
                    pkcs11.Attribute.CERTIFICATE_TYPE: pkcs11.CertificateType.X_509,
                    pkcs11.Attribute.TOKEN: True,
                    pkcs11.Attribute.LABEL: label,
                    pkcs11.Attribute.ID: key_id,
                    pkcs11.Attribute.SUBJECT: name.public_bytes(),
                    pkcs11.Attribute.VALUE: der})
            materials.append(dict(token=token_label, serial=serials[token_label],
                                  algorithm=algorithm, label=label, key_id=key_id,
                                  external=external, certificate=der,
                                  blob=public_blob(external, algorithm)))
        yield str(provider), pin, materials


@asynccontextmanager
async def shared_token_provider(directory, provider):
    """Expose selected real tokens using the unmodified p11-kit RPC service."""
    import tarfile
    from pathlib import Path
    from _helpers import managed_service, temporary_environment, environment
    bundle = directory / 'token-sharing-tools'
    bundle.mkdir()
    with tarfile.open(Path(__file__).with_name('F05_p11kit.tar.gz')) as archive:
        archive.extractall(bundle, filter='data')
    socket = directory / 'pkcs11.sock'
    library_dir = bundle / 'usr/lib/x86_64-linux-gnu'
    server = bundle / 'usr/libexec/p11-kit/p11-kit-server'
    command = [str(server), '--foreground', '--name', str(socket),
               '--provider', provider, 'pkcs11:token=alpha', 'pkcs11:token=beta']
    async with managed_service(command, env=environment({'LD_LIBRARY_PATH': str(library_dir),
                'P11_KIT_PRIVATEDIR': str(bundle / 'usr/libexec/p11-kit')}),
                               ready=lambda service: socket.exists()) as service:
        with temporary_environment({'P11_KIT_SERVER_ADDRESS': 'unix:path=' + str(socket)}):
            try:
                yield str(library_dir / 'pkcs11/p11-kit-client.so')
            except BaseException as error:
                error.add_note(repr(service.output()))
                raise
