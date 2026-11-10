# feature: F01
"""Independent cryptographic identities and standard representation readers."""
import base64
import struct

from cryptography.hazmat.primitives import hashes, serialization as ser
from cryptography.hazmat.primitives.asymmetric import dsa, rsa, ec, ed25519, ed448, padding, utils

ALGORITHMS = (
    'ssh-dss', 'ssh-rsa', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384',
    'ecdsa-sha2-nistp521', 'ecdsa-sha2-1.3.132.0.10', 'ssh-ed25519', 'ssh-ed448',
)
CURVES = {'nistp256': ec.SECP256R1, 'nistp384': ec.SECP384R1,
          'nistp521': ec.SECP521R1, '1.3.132.0.10': ec.SECP256K1}


def external_key(algorithm):
    if algorithm == 'ssh-rsa':
        return rsa.generate_private_key(65537, 2048)
    if algorithm == 'ssh-dss':
        return dsa.generate_private_key(1024)
    if algorithm.startswith('ecdsa-sha2-'):
        return ec.generate_private_key(CURVES[algorithm[11:]]())
    return {'ssh-ed25519': ed25519.Ed25519PrivateKey,
            'ssh-ed448': ed448.Ed448PrivateKey}[algorithm].generate()


def identity(key):
    if hasattr(key, 'public_key'):
        key = key.public_key()
    return key.public_bytes(ser.Encoding.DER, ser.PublicFormat.SubjectPublicKeyInfo)


def ssh_string(value):
    if isinstance(value, str):
        value = value.encode()
    return struct.pack('>I', len(value)) + value


def ssh_integer(value):
    return ssh_string(value.to_bytes((value.bit_length() + 8) // 8, 'big'))


class WireReader:
    """Length-delimited SSH binary reader; truncation is always an error."""
    def __init__(self, data):
        self.data = data
        self.offset = 0

    def take(self, size):
        value = self.data[self.offset:self.offset + size]
        assert len(value) == size, 'Truncated SSH field'
        self.offset += size
        return value

    def uint32(self):
        return struct.unpack('>I', self.take(4))[0]

    def string(self):
        return self.take(self.uint32())

    def integer(self):
        return int.from_bytes(self.string(), 'big')

    def finish(self):
        assert self.offset == len(self.data), 'Trailing SSH fields'


def public_blob(key, algorithm):
    """Encode RFC 4253/5656/8709 public representations independently."""
    key = key.public_key() if hasattr(key, 'public_key') else key
    result = ssh_string(algorithm)
    if isinstance(key, rsa.RSAPublicKey):
        numbers = key.public_numbers()
        result += ssh_integer(numbers.e) + ssh_integer(numbers.n)
    elif isinstance(key, dsa.DSAPublicKey):
        numbers = key.public_numbers()
        params = numbers.parameter_numbers
        result += b''.join(ssh_integer(x) for x in (params.p, params.q, params.g, numbers.y))
    elif isinstance(key, ec.EllipticCurvePublicKey):
        result += ssh_string(algorithm[11:]) + ssh_string(key.public_bytes(
            ser.Encoding.X962, ser.PublicFormat.UncompressedPoint))
    else:
        result += ssh_string(key.public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw))
    return result


def read_public_blob(blob):
    reader = WireReader(blob)
    algorithm = reader.string().decode()
    if algorithm == 'ssh-rsa':
        e, n = reader.integer(), reader.integer()
        key = rsa.RSAPublicNumbers(e, n).public_key()
    elif algorithm == 'ssh-dss':
        p, q, g, y = [reader.integer() for _ in range(4)]
        key = dsa.DSAPublicNumbers(y, dsa.DSAParameterNumbers(p, q, g)).public_key()
    elif algorithm.startswith('ecdsa-sha2-'):
        curve = reader.string().decode()
        key = ec.EllipticCurvePublicKey.from_encoded_point(CURVES[curve](), reader.string())
    else:
        key = {'ssh-ed25519': ed25519.Ed25519PublicKey,
               'ssh-ed448': ed448.Ed448PublicKey}[algorithm].from_public_bytes(reader.string())
    reader.finish()
    return key


def pem_payload(data):
    return base64.b64decode(b''.join(data.splitlines()[1:-1]), validate=True)


def der_children(der):
    """Return (tag, contents) of each element directly inside a DER SEQUENCE."""
    def element(offset):
        tag, size = der[offset], der[offset+1]
        offset += 2
        if size & 128:
            width = size & 127
            size = int.from_bytes(der[offset:offset+width], 'big')
            offset += width
        assert offset + size <= len(der), 'Truncated DER element'
        return tag, der[offset:offset+size], offset + size
    tag, content, end = element(0)
    assert tag == 0x30 and end == len(der), 'Not a single DER SEQUENCE'
    der, offset, result = content, 0, []
    while offset < len(der):
        tag, value, offset = element(offset)
        result.append((tag, value))
    return result


def assert_layout(data, fmt, private):
    """PKCS#8 and traditional encodings have distinct standard ASN.1 shapes."""
    der = pem_payload(data) if fmt.endswith('pem') else data
    tags = [tag for tag, _ in der_children(der)]
    if fmt.startswith('pkcs8'):
        # PrivateKeyInfo: version, AlgorithmIdentifier, ...; SPKI: AlgorithmIdentifier, BIT STRING.
        assert tags[:2] == ([0x02, 0x30] if private else [0x30, 0x03]), tags
    else:
        # RSA/DSA/EC private structures and RSA/DSA public sequences start with integers.
        assert tags[0] == 0x02 and 0x30 not in tags[:2], tags


def armor(label, payload):
    encoded = base64.b64encode(payload)
    return (b'-----BEGIN ' + label + b'-----\n' +
            b'\n'.join(encoded[i:i+64] for i in range(0, len(encoded), 64)) +
            b'\n-----END ' + label + b'-----\n')


def rfc4716(blob):
    encoded = base64.b64encode(blob)
    return b'---- BEGIN SSH2 PUBLIC KEY ----\n' + encoded + b'\n---- END SSH2 PUBLIC KEY ----\n'


def der_numbers(values):
    def tlv(tag, data):
        size = len(data)
        length = bytes([size]) if size < 128 else bytes([128 + (size.bit_length()+7)//8]) + size.to_bytes((size.bit_length()+7)//8, 'big')
        return bytes([tag]) + length + data
    return tlv(48, b''.join(tlv(2, x.to_bytes((x.bit_length()+8)//8, 'big')) for x in values))


def read_der_numbers(data):
    def field(offset, tag):
        assert data[offset] == tag
        size = data[offset+1]
        offset += 2
        if size & 128:
            width = size & 127
            size = int.from_bytes(data[offset:offset+width], 'big')
            offset += width
        end = offset + size
        assert end <= len(data)
        return data[offset:end], end
    content, end = field(0, 48)
    assert end == len(data)
    data = content
    result, offset = [], 0
    while offset < len(data):
        value, offset = field(offset, 2)
        result.append(int.from_bytes(value, 'big'))
    return result


def external_public(key, algorithm, fmt):
    if fmt == 'openssh':
        return algorithm.encode() + b' ' + base64.b64encode(public_blob(key, algorithm)) + b'\n'
    if fmt == 'rfc4716':
        return rfc4716(public_blob(key, algorithm))
    if fmt.startswith('pkcs1') and algorithm == 'ssh-dss':
        n = key.public_key().public_numbers()
        p = n.parameter_numbers
        data = der_numbers((n.y, p.p, p.q, p.g))
        return armor(b'DSA PUBLIC KEY', data) if fmt.endswith('pem') else data
    return key.public_key().public_bytes(
        ser.Encoding.PEM if fmt.endswith('pem') else ser.Encoding.DER,
        ser.PublicFormat.PKCS1 if fmt.startswith('pkcs1') else ser.PublicFormat.SubjectPublicKeyInfo)


def read_rfc4716(data):
    """Decode RFC 4716 armor, including extensible and continued headers."""
    lines = data.splitlines()
    assert lines[0] == b'---- BEGIN SSH2 PUBLIC KEY ----'
    assert lines[-1] == b'---- END SSH2 PUBLIC KEY ----'
    headers, body, index = {}, [], 1
    while index < len(lines) - 1:
        line = lines[index]
        index += 1
        if not body and b':' in line:
            while line.endswith(b'\\'):
                assert index < len(lines) - 1, 'Truncated RFC 4716 header'
                line = line[:-1] + lines[index]
                index += 1
            name, value = line.split(b':', 1)
            name = name.lower()
            assert name not in headers, 'Duplicate RFC 4716 header'
            headers[name] = value.strip()
        elif line.strip():
            body.append(line.strip())
    return base64.b64decode(b''.join(body), validate=True), headers


def rfc4716_comment(data):
    _, headers = read_rfc4716(data)
    value = headers[b'comment']
    if value.startswith(b'"'):
        assert value.endswith(b'"')
        value = value[1:-1]
        result, escaped = bytearray(), False
        for byte in value:
            if escaped:
                result.append(byte)
                escaped = False
            elif byte == 92:
                escaped = True
            else:
                result.append(byte)
        assert not escaped, 'Truncated RFC 4716 quoted comment'
        value = bytes(result)
    return value


def fingerprint_bytes(text, name):
    label, encoded = text.split(':', 1)
    assert label.lower() == name
    if name == 'md5':
        octets = encoded.split(':')
        assert all(len(value) == 2 for value in octets)
        return bytes.fromhex(''.join(octets))
    return base64.b64decode(encoded + '=' * (-len(encoded) % 4), validate=True)


def read_public(data, fmt, algorithm):
    if fmt == 'openssh':
        parts = data.split()
        assert parts[0] == algorithm.encode()
        return read_public_blob(base64.b64decode(parts[1], validate=True))
    if fmt == 'rfc4716':
        payload, _ = read_rfc4716(data)
        return read_public_blob(payload)
    assert_layout(data, fmt, private=False)
    if fmt.startswith('pkcs1') and algorithm == 'ssh-dss':
        y, p, q, g = read_der_numbers(pem_payload(data) if fmt.endswith('pem') else data)
        return dsa.DSAPublicNumbers(y, dsa.DSAParameterNumbers(p, q, g)).public_key()
    return (ser.load_pem_public_key if fmt.endswith('pem') else ser.load_der_public_key)(data)


def openssh_private(key, algorithm):
    """Build an unencrypted OpenSSH container from an external private key."""
    pub = public_blob(key, algorithm)
    private = ssh_string(algorithm)
    if isinstance(key, rsa.RSAPrivateKey):
        n = key.private_numbers()
        private += b''.join(ssh_integer(x) for x in (n.public_numbers.n, n.public_numbers.e, n.d, n.iqmp, n.p, n.q))
    elif isinstance(key, dsa.DSAPrivateKey):
        n = key.private_numbers()
        p = n.public_numbers.parameter_numbers
        private += b''.join(ssh_integer(x) for x in (p.p, p.q, p.g, n.public_numbers.y, n.x))
    elif isinstance(key, ec.EllipticCurvePrivateKey):
        private += public_blob(key, algorithm)[len(ssh_string(algorithm)):] + ssh_integer(key.private_numbers().private_value)
    else:
        raw_pub = key.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
        raw_priv = key.private_bytes(ser.Encoding.Raw, ser.PrivateFormat.Raw, ser.NoEncryption())
        private += ssh_string(raw_pub) + ssh_string(raw_priv + raw_pub)
    return openssh_container(pub, private)


def openssh_container(pub, private):
    block = struct.pack('>II', 0x637291ab, 0x637291ab) + private + ssh_string(b'')
    padding_size = (-len(block)) % 8
    block += bytes(range(1, padding_size+1))
    return armor(b'OPENSSH PRIVATE KEY', b'openssh-key-v1\0' + ssh_string(b'none') +
                 ssh_string(b'none') + ssh_string(b'') + struct.pack('>I', 1) +
                 ssh_string(pub) + ssh_string(block))


def read_openssh_container(data):
    reader = WireReader(pem_payload(data))
    assert reader.take(15) == b'openssh-key-v1\0'
    assert reader.string() == b'none'
    assert reader.string() == b'none'
    assert reader.string() == b''
    assert reader.uint32() == 1
    public = reader.string()
    private = WireReader(reader.string())
    reader.finish()
    assert private.uint32() == private.uint32()
    return public, private


def read_private(data, fmt, password=None):
    if fmt != 'openssh' or password is not None:
        loader = ser.load_ssh_private_key if fmt == 'openssh' else (
            ser.load_pem_private_key if fmt.endswith('pem') else ser.load_der_private_key)
        key = loader(data, password)
        if password is None:
            assert_layout(data, fmt, private=True)
        return key
    public, reader = read_openssh_container(data)
    algorithm = reader.string().decode()
    if algorithm == 'ssh-rsa':
        n, e, d, iqmp, p, q = [reader.integer() for _ in range(6)]
        key = rsa.RSAPrivateNumbers(p, q, d, d % (p-1), d % (q-1), iqmp,
                                   rsa.RSAPublicNumbers(e, n)).private_key()
    elif algorithm == 'ssh-dss':
        p, q, g, y, x = [reader.integer() for _ in range(5)]
        key = dsa.DSAPrivateNumbers(x, dsa.DSAPublicNumbers(y, dsa.DSAParameterNumbers(p, q, g))).private_key()
    elif algorithm.startswith('ecdsa-sha2-'):
        curve = reader.string().decode()
        reader.string()
        key = ec.derive_private_key(reader.integer(), CURVES[curve]())
    else:
        raw_pub, raw_priv = reader.string(), reader.string()
        key = {'ssh-ed25519': ed25519.Ed25519PrivateKey,
               'ssh-ed448': ed448.Ed448PrivateKey}[algorithm].from_private_bytes(raw_priv[:-len(raw_pub)])
    reader.string()  # Comment is independent of the cryptographic identity.
    rest = reader.take(len(reader.data) - reader.offset)
    assert rest == bytes(range(1, len(rest)+1))
    assert identity(read_public_blob(public)) == identity(key)
    return key


def public_formats(algorithm):
    return ('openssh', 'rfc4716', 'pkcs8-der', 'pkcs8-pem') + (
        ('pkcs1-der', 'pkcs1-pem') if algorithm in ('ssh-dss', 'ssh-rsa') else ())


def private_formats(algorithm):
    return ('openssh', 'pkcs8-der', 'pkcs8-pem') + (
        ('pkcs1-der', 'pkcs1-pem') if algorithm in ('ssh-dss', 'ssh-rsa') or algorithm.startswith('ecdsa-') else ())


def external_private(key, algorithm, fmt):
    if fmt == 'openssh':
        return openssh_private(key, algorithm)
    return key.private_bytes(ser.Encoding.PEM if fmt.endswith('pem') else ser.Encoding.DER,
                             ser.PrivateFormat.TraditionalOpenSSL if fmt.startswith('pkcs1') else ser.PrivateFormat.PKCS8,
                             ser.NoEncryption())


def authenticate(key, peer_public, algorithm, challenge):
    """An independent verifier authenticates a fresh challenge signature."""
    sig_algorithm = b'rsa-sha2-256' if algorithm == 'ssh-rsa' else algorithm.encode()
    packet = WireReader(key.sign(challenge, sig_algorithm))
    assert packet.string() == sig_algorithm
    signature = packet.string()
    packet.finish()
    if algorithm == 'ssh-rsa':
        peer_public.verify(signature, challenge, padding.PKCS1v15(), hashes.SHA256())
    elif algorithm == 'ssh-dss':
        assert len(signature) == 40
        r, s = int.from_bytes(signature[:20], 'big'), int.from_bytes(signature[20:], 'big')
        peer_public.verify(utils.encode_dss_signature(r, s), challenge, hashes.SHA1())
    elif algorithm.startswith('ecdsa-'):
        parts = WireReader(signature)
        r, s = parts.integer(), parts.integer()
        parts.finish()
        digest = {256: hashes.SHA256, 384: hashes.SHA384, 521: hashes.SHA512}[peer_public.curve.key_size]
        peer_public.verify(utils.encode_dss_signature(r, s), challenge, ec.ECDSA(digest()))
    else:
        peer_public.verify(signature, challenge)


def decrypt_openssh(data, password):
    """Decrypt a requested AES-256-CBC OpenSSH export using external primitives."""
    import bcrypt
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    reader = WireReader(pem_payload(data))
    assert reader.take(15) == b'openssh-key-v1\0'
    assert reader.string() == b'aes256-cbc'
    assert reader.string() == b'bcrypt'
    params = WireReader(reader.string())
    salt, rounds = params.string(), params.uint32()
    params.finish()
    count = reader.uint32()
    public, encrypted = reader.string(), reader.string()
    reader.finish()
    material = bcrypt.kdf(password, salt, 48, rounds, ignore_few_rounds=True)
    decryptor = Cipher(algorithms.AES(material[:32]), modes.CBC(material[32:])).decryptor()
    plain = decryptor.update(encrypted) + decryptor.finalize()
    container = (b'openssh-key-v1\0' + ssh_string(b'none') + ssh_string(b'none') +
                 ssh_string(b'') + struct.pack('>I', count) + ssh_string(public) + ssh_string(plain))
    return read_private(armor(b'OPENSSH PRIVATE KEY', container), 'openssh')
