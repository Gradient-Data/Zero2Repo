# feature: F20
"""OpenSSH interoperability fixtures and SSHSIG wire readers."""
import base64
import struct

from cryptography.hazmat.primitives import serialization as ser

from _helpers import run_command
from F01_helpers import external_private, WireReader, ssh_string
from F02_helpers import certificate_identity


def sshsig_identity(directory, name):
    key, external = certificate_identity()
    path = directory / name
    path.write_bytes(external_private(external, 'ssh-ed25519', 'openssh'))
    path.chmod(0o600)
    public = external.public_key().public_bytes(
        ser.Encoding.OpenSSH,
        ser.PublicFormat.OpenSSH)
    path.with_suffix('.pub').write_bytes(public + b'\n')
    return key, path, public


def openssh_command(*arguments, input=None):
    result = run_command(['ssh-keygen', *arguments], input=input)
    assert result.returncode == 0, (result.args, result.stdout, result.stderr)
    return result


def signer_document(public, principals='reader', options=''):
    return (principals + ' ' + (options + ' ' if options else '')).encode() + public + b'\n'


def sshsig_fields(signature):
    if signature.startswith(b'-----BEGIN SSH SIGNATURE-----\n'):
        signature = base64.b64decode(b''.join(signature.splitlines()[1:-1]), validate=True)
    reader = WireReader(signature)
    magic, version = reader.take(6), reader.uint32()
    fields = [reader.string() for _ in range(5)]
    reader.finish()
    return magic, version, fields


def sshsig_packet(fields, version=1, magic=b'SSHSIG'):
    return magic + struct.pack('>I', version) + b''.join(ssh_string(field) for field in fields)


def openssh_signature(key_path, data_path, namespace='file', hash_name='sha512'):
    output = data_path.with_name(data_path.name + '.sig')
    if output.exists():
        output.unlink()
    openssh_command('-Y', 'sign', '-f', str(key_path), '-n', namespace,
                    '-O', 'hashalg=' + hash_name, str(data_path))
    return output.read_bytes()


def openssh_certificate(ca_path, subject_path, *, principals='reader', validity='-1h:+1h'):
    openssh_command('-s', str(ca_path), '-I', 'signing identity', '-n', principals,
                    '-V', validity, str(subject_path.with_suffix('.pub')))
    return subject_path.with_name(subject_path.name + '-cert.pub').read_bytes()
