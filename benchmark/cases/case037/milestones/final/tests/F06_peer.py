# feature: F06
"""Independent SSH protocol observations, with standard cryptographic primitives.

Paramiko owns framing, authentication and channels. Extensions below implement
RFC 4253/4432/5656 and SSH hybrid exchange using only external cryptography.
No product modules are imported or patched by this peer.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import sys
import tempfile
import threading
import time
import zipfile


def initialize():
    global paramiko, Message
    import paramiko
    from paramiko import Message
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, x448, x25519, mlkem, rsa, padding
    from cryptography.hazmat.decrepit.ciphers import algorithms as legacy
    from cryptography.hazmat.primitives.ciphers import modes
    from paramiko.kex_ecdh_nist import KexNistp256
    from paramiko.kex_group14 import KexGroup14
    from paramiko.kex_gex import KexGex

    class ObservedPackets(paramiko.Packetizer):
        REKEY_BYTES = 1 << 42
        REKEY_PACKETS = 1 << 42
        def __init__(self, sock):
            super().__init__(sock)
            self.records = []
            self.order = []
            self.methods = []
            self.global_requests = []
            self.capture = None
        def read_all(self, size, check_rekey=False):
            data = super().read_all(size, check_rekey)
            if self.capture is not None:
                self.capture.extend(data)
            return data
        def read_message(self):
            self.capture = bytearray()
            kind, message = super().read_message()
            length = struct.unpack('>I', self.capture[:4])[0]
            self.capture = None
            self.records.append((length, kind, time.monotonic(), len(message.asbytes()) + 1))
            self.order.append(('receive', kind))
            if kind == 80:
                self.global_requests.append(Message(message.asbytes()).get_text())
            if kind == 50:
                request = Message(message.asbytes())
                request.get_string()
                request.get_string()
                method = request.get_text()
                self.methods.append(method)
            return kind, message
        def send_message(self, message):
            self.order.append(('send', message.asbytes()[0]))
            return super().send_message(message)

    class ExtendedTransport(paramiko.Transport):
        def __init__(self, sock, **options):
            super().__init__(sock, packetizer_class=ObservedPackets, **options)
        def _parse_global_request(self, message):
            if (getattr(self, 'task_spec', {}).get('ignore_keepalives') and
                    Message(message.asbytes()).get_text() == 'keepalive@openssh.com'):
                return
            super()._parse_global_request(message)
        def _parse_kex_init(self, message):
            super()._parse_kex_init(message)
            self.selected_kex = self.kex_engine.name if hasattr(self.kex_engine, 'name') else next(
                name for name, cls in self._kex_info.items() if type(self.kex_engine) is cls)
        def _compute_key(self, ident, size):
            if not isinstance(self.K, bytes):
                return super()._compute_key(ident, size)
            # Hybrid SSH encodes the combined secret as a string, not an mpint.
            prefix = pack(self.K) + self.H
            h = self.kex_engine.hash_algo
            result = h(prefix + ident.encode() + self.session_id).digest()
            while len(result) < size:
                result += h(prefix + result).digest()
            return result[:size]

    for name, cls, size, block in (
            ('blowfish-cbc', legacy.Blowfish, 16, 8),
            ('cast128-cbc', legacy.CAST5, 16, 8),
            ('seed-cbc@ssh.com', legacy.SEED, 16, 16),
            ('arcfour', legacy.ARC4, 16, 8),
            ('arcfour128', legacy.ARC4, 16, 8),
            ('arcfour256', legacy.ARC4, 32, 8)):
        ExtendedTransport._cipher_info[name] = {'class': cls, 'mode': modes.CBC,
                                               'key-size': size, 'block-size': block}

    original_engine = ExtendedTransport._get_engine
    def engine(self, name, key, iv=None, operation=None, aead=False):
        if not name.startswith('arcfour'):
            return original_engine(self, name, key, iv, operation, aead)
        from cryptography.hazmat.primitives.ciphers import Cipher
        ctx = Cipher(legacy.ARC4(key), None).encryptor()
        if name != 'arcfour':
            ctx.update(bytes(1536))  # RFC 4345 stream-cipher initial discard.
        return ctx
    ExtendedTransport._get_engine = engine

    for digest, label in ((hashlib.sha1, 'sha1'), (hashlib.sha224, 'sha2-224'),
            (hashlib.sha256, 'sha2-256'), (hashlib.sha384, 'sha2-384'),
            (hashlib.sha512, 'sha2-512'), (hashlib.md5, 'md5')):
        for truncated in (False, True):
            if truncated and label in ('sha2-224', 'sha2-384'):
                continue
            name = ('hmac-' + label + ('-96' if truncated else ''))
            if label in ('sha2-224', 'sha2-384'):
                name = 'hmac-' + label.replace('sha2-', 'sha') + '@ssh.com'
            for suffix in ('', '-etm@openssh.com'):
                if suffix and label in ('sha2-224', 'sha2-384'):
                    continue
                ExtendedTransport._mac_info[name + suffix] = {
                    'class': digest, 'size': 12 if truncated else digest().digest_size}

    from F01_helpers import read_public_blob, public_blob, WireReader, ssh_string, ssh_integer
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed448, dsa, utils

    class ExternalKey(paramiko.PKey):
        verified = []
        signed = []
        def __init__(self, msg=None, data=None, private=None, certificate=None, algorithm=None):
            self.private = None
            self.public_blob = None
            if private is not None:
                self.private = serialization.load_pem_private_key(private.encode(), None)
                self.public = self.private.public_key()
                self.algorithm = algorithm
                self.blob = public_blob(self.private, algorithm)
                if certificate:
                    blob = base64.b64decode(certificate)
                    self.public_blob = paramiko.pkey.PublicBlob(Message(blob).get_text(), blob)
            else:
                self.blob = data if data is not None else msg.asbytes()
                packet = WireReader(self.blob)
                self.algorithm = packet.string().decode()
                if self.algorithm.startswith('x509v3-'):
                    count = packet.uint32()
                    certs = [x509.load_der_x509_certificate(packet.string()) for _ in range(count)]
                    assert count >= 1
                    self.public = certs[0].public_key()
                    for _ in range(packet.uint32()):
                        packet.string()
                    packet.finish()
                else:
                    self.public = read_public_blob(self.blob)
        def asbytes(self):
            return self.blob
        def get_name(self):
            return self.algorithm
        def get_bits(self):
            return 448 if isinstance(self.public, ed448.Ed448PublicKey) else self.public.key_size
        def can_sign(self):
            return self.private is not None
        def verify_ssh_sig(self, data, message):
            algorithm, signature = message.get_text(), message.get_string()
            digest = self.digest(algorithm)
            try:
                if isinstance(self.public, rsa.RSAPublicKey):
                    self.public.verify(signature, data, padding.PKCS1v15(), digest)
                elif isinstance(self.public, dsa.DSAPublicKey):
                    assert len(signature) == 40
                    self.public.verify(utils.encode_dss_signature(
                        int.from_bytes(signature[:20], 'big'), int.from_bytes(signature[20:], 'big')),
                        data, hashes.SHA1())
                elif isinstance(self.public, ec.EllipticCurvePublicKey):
                    parts = Message(signature)
                    r, value = parts.get_mpint(), parts.get_mpint()
                    self.public.verify(utils.encode_dss_signature(r, value), data, ec.ECDSA(digest))
                else:
                    self.public.verify(signature, data)
            except InvalidSignature:
                return False
            self.verified.append(algorithm)
            return True
        @staticmethod
        def digest(algorithm):
            if algorithm in ('ssh-ed448', 'ssh-ed25519'):
                return None
            if algorithm in ('ssh-rsa', 'ssh-dss'):
                return hashes.SHA1()
            for bits in (224, 256, 384, 512):
                if str(bits) in algorithm:
                    return getattr(hashes, 'SHA' + str(bits))()
            if algorithm == 'ecdsa-sha2-1.3.132.0.10':
                return hashes.SHA256()
            if algorithm == 'ecdsa-sha2-nistp521':
                return hashes.SHA512()
            raise ValueError('Unsupported signature algorithm: ' + algorithm)
        def sign_ssh_data(self, data, algorithm=None):
            algorithm = (algorithm or self.algorithm).removeprefix('x509v3-').replace(
                '-cert-v01@openssh.com', '')
            digest = self.digest(algorithm)
            self.signed.append(algorithm)
            if isinstance(self.private, rsa.RSAPrivateKey):
                signature = self.private.sign(data, padding.PKCS1v15(), digest)
            elif isinstance(self.private, ec.EllipticCurvePrivateKey):
                raw = self.private.sign(data, ec.ECDSA(digest))
                r, value = utils.decode_dss_signature(raw)
                signature = ssh_integer(r) + ssh_integer(value)
            else:
                signature = self.private.sign(data)
            return Message(ssh_string(algorithm) + ssh_string(signature))

    ExtendedTransport.external_key = ExternalKey
    for algorithm in ('ssh-dss', 'ssh-rsa', 'rsa-sha2-256', 'rsa-sha2-512',
            'ssh-rsa-sha224@ssh.com', 'ssh-rsa-sha384@ssh.com',
            'ssh-rsa-sha256@ssh.com', 'ssh-rsa-sha512@ssh.com',
            'ssh-ed448', 'ecdsa-sha2-1.3.132.0.10',
            'x509v3-rsa2048-sha256', 'x509v3-ssh-rsa'):
        ExtendedTransport._key_info[algorithm] = ExternalKey
    # RFC 3526 primes are derived from the published formula, independently
    # of the product's constants. Decimal Chudnovsky supplies sufficient pi bits.
    def prime(bits, adjustment):
        from decimal import Decimal, localcontext
        with localcontext() as context:
            context.prec = bits // 3 + 80
            m, l, x, k = 1, 13591409, 1, 6
            total = Decimal(l)
            for i in range(1, context.prec // 14 + 2):
                m = m * (k**3 - 16*k) // i**3
                l += 545140134
                x *= -262537412640768000
                total += Decimal(m*l) / x
                k += 12
            pi = 426880 * Decimal(10005).sqrt() / total
            return 2**bits - 2**(bits-64) - 1 + 2**64 * (
                int(Decimal(2)**(bits-130) * pi) + adjustment)

    for group, bits, adjustment, digests in (
            (14, 2048, 124476, ('sha224',)),
            (15, 3072, 1690314, ('sha256', 'sha384', 'sha512')),
            (16, 4096, 240904, ('sha384',)),
            (17, 6144, 929484, ('sha512',))):
        modulus = prime(bits, adjustment)
        for digest in digests:
            name = f'diffie-hellman-group{group}-{digest}'
            if digest != 'sha512':
                name += '@ssh.com'
            ExtendedTransport._kex_info[name] = type('FixedGroup', (KexGroup14,), {
                'name': name, 'P': modulus, 'hash_algo': staticmethod(getattr(hashlib, digest))})
    for digest in ('sha224', 'sha384', 'sha512'):
        name = 'diffie-hellman-group-exchange-' + digest + '@ssh.com'
        ExtendedTransport._kex_info[name] = type('GroupExchange', (KexGex,), {
            'name': name, 'hash_algo': staticmethod(getattr(hashlib, digest))})
    ExtendedTransport._kex_info['ecdh-sha2-1.3.132.0.10'] = type(
        'Secp256k1', (KexNistp256,), {'curve': ec.SECP256K1()})

    class ECDH:
        """Client exchange for raw Montgomery and hybrid public values."""
        hash_algo = staticmethod(hashlib.sha512)
        curve = None
        pq = None
        ciphertext_size = 0
        def __init__(self, transport):
            self.transport = transport
        def start_kex(self):
            if self.curve is None:
                self.key = x448.X448PrivateKey.generate()
                self.public = self.key.public_key().public_bytes_raw()
            elif self.curve == 'x25519':
                self.key = x25519.X25519PrivateKey.generate()
                self.public = self.key.public_key().public_bytes_raw()
            else:
                self.key = ec.generate_private_key(self.curve)
                self.public = self.key.public_key().public_bytes(
                    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
            if self.transport.server_mode:
                assert self.curve == 'x25519' and self.pq is SNTRUPKey
                self.transport._expect_packet(30)
                return
            if self.pq:
                self.kem = self.pq.generate()
                self.public = self.kem.public_key().public_bytes_raw() + self.public
            msg = Message()
            msg.add_byte(b'\x1e')
            msg.add_string(self.public)
            self.transport._send_message(msg)
            self.transport._expect_packet(31)
        def parse_next(self, kind, msg):
            if self.transport.server_mode:
                assert kind == 30
                peer = msg.get_string()
                pq_secret, ciphertext = SNTRUPKey.encapsulate(peer[:1158])
                shared = self.key.exchange(x25519.X25519PublicKey.from_public_bytes(peer[1158:]))
                self.public = ciphertext + self.public
                shared = self.hash_algo(pq_secret + shared).digest()
                host_key = self.transport.get_server_key()
                host = host_key.asbytes()
                hm = Message()
                hm.add(self.transport.remote_version, self.transport.local_version,
                       self.transport.remote_kex_init, self.transport.local_kex_init,
                       host, peer, self.public)
                hm.add_string(shared)
                exchange_hash = self.hash_algo(hm.asbytes()).digest()
                self.transport._set_K_H(shared, exchange_hash)
                response = Message()
                response.add_byte(b'\x1f')
                response.add_string(host)
                response.add_string(self.public)
                response.add_string(host_key.sign_ssh_data(exchange_hash, self.transport.host_key_type).asbytes())
                self.transport._send_message(response)
                self.transport._activate_outbound()
                return
            assert kind == 31
            host, peer, signature = msg.get_string(), msg.get_string(), msg.get_string()
            if self.pq:
                pq_secret = self.kem.decapsulate(peer[:self.ciphertext_size])
                ec_public = peer[self.ciphertext_size:]
            else:
                ec_public = peer
            if self.curve is None:
                shared = self.key.exchange(x448.X448PublicKey.from_public_bytes(ec_public))
            elif self.curve == 'x25519':
                shared = self.key.exchange(x25519.X25519PublicKey.from_public_bytes(ec_public))
            else:
                shared = self.key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(
                    self.curve, ec_public))
            hm = Message()
            hm.add(self.transport.local_version, self.transport.remote_version,
                   self.transport.local_kex_init, self.transport.remote_kex_init,
                   host, self.public, peer)
            if self.pq:
                shared = self.hash_algo(pq_secret + shared).digest()
                hm.add_string(shared)
            else:
                shared = int.from_bytes(shared, 'big')
                hm.add_mpint(shared)
            self.transport._set_K_H(shared, self.hash_algo(hm.asbytes()).digest())
            self.transport._verify_key(host, signature)
            self.transport._activate_outbound()
    ExtendedTransport._kex_info['curve448-sha512'] = ECDH
    for name, curve, pq, size, digest in (
            ('mlkem768x25519-sha256', 'x25519', mlkem.MLKEM768PrivateKey, 1088, hashlib.sha256),
            ('mlkem768nistp256-sha256', ec.SECP256R1(), mlkem.MLKEM768PrivateKey, 1088, hashlib.sha256),
            ('mlkem1024nistp384-sha384', ec.SECP384R1(), mlkem.MLKEM1024PrivateKey, 1568, hashlib.sha384)):
        ExtendedTransport._kex_info[name] = type('Hybrid', (ECDH,), {
            'curve': curve, 'pq': pq, 'ciphertext_size': size, 'hash_algo': staticmethod(digest)})

    class SNTRUPKey:
        """Independent NTRU Prime operations using the real liboqs C API."""
        @staticmethod
        def library():
            import ctypes
            import ctypes.util
            name = ctypes.util.find_library('oqs')
            if not name:
                raise RuntimeError('SNTRUP exchange requires liboqs')
            return ctypes.CDLL(name)
        @classmethod
        def generate(cls):
            import ctypes
            key = cls()
            public, private = ctypes.create_string_buffer(1158), ctypes.create_string_buffer(1763)
            assert key.library().OQS_KEM_ntruprime_sntrup761_keypair(public, private) == 0
            key.public, key.private = public.raw, private.raw
            return key
        def public_key(self):
            return self
        def public_bytes_raw(self):
            return self.public
        def decapsulate(self, ciphertext):
            import ctypes
            assert len(ciphertext) == 1039
            secret = ctypes.create_string_buffer(32)
            assert self.library().OQS_KEM_ntruprime_sntrup761_decaps(secret, ciphertext, self.private) == 0
            return secret.raw
        @classmethod
        def encapsulate(cls, public):
            import ctypes
            assert len(public) == 1158
            ciphertext, secret = ctypes.create_string_buffer(1039), ctypes.create_string_buffer(32)
            assert cls.library().OQS_KEM_ntruprime_sntrup761_encaps(ciphertext, secret, public) == 0
            return secret.raw, ciphertext.raw

    for name in ('sntrup761x25519-sha512', 'sntrup761x25519-sha512@openssh.com'):
        ExtendedTransport._kex_info[name] = type('SNTRUPHybrid', (ECDH,), {
            'name': name, 'curve': 'x25519', 'pq': SNTRUPKey,
            'ciphertext_size': 1039, 'hash_algo': staticmethod(hashlib.sha512)})

    class RSAExchange:
        """RFC 4432 client exchange with independently generated shared secret."""
        hash_algo = staticmethod(hashlib.sha256)
        hash_class = hashes.SHA256
        def __init__(self, transport):
            self.transport = transport
        def start_kex(self):
            self.transport._expect_packet(30)
        def parse_next(self, kind, msg):
            if kind == 30:
                self.host, self.transient = msg.get_string(), msg.get_string()
                keydata = Message(self.transient)
                assert keydata.get_text() == 'ssh-rsa'
                e, n = keydata.get_mpint(), keydata.get_mpint()
                key = rsa.RSAPublicNumbers(e, n).public_key()
                self.shared = secrets.randbits(key.key_size - 2*self.hash_algo().digest_size*8 - 49)
                value = Message()
                value.add_mpint(self.shared)
                h = self.hash_class()
                self.encrypted = key.encrypt(value.asbytes(), padding.OAEP(padding.MGF1(h), h, None))
                request = Message()
                request.add_byte(b'\x1f')
                request.add_string(self.encrypted)
                self.transport._send_message(request)
                self.transport._expect_packet(32)
            else:
                assert kind == 32
                signature = msg.get_string()
                hm = Message()
                hm.add(self.transport.local_version, self.transport.remote_version,
                       self.transport.local_kex_init, self.transport.remote_kex_init,
                       self.host, self.transient, self.encrypted)
                hm.add_mpint(self.shared)
                self.transport._set_K_H(self.shared, self.hash_algo(hm.asbytes()).digest())
                self.transport._verify_key(self.host, signature)
                self.transport._activate_outbound()
    ExtendedTransport._kex_info['rsa2048-sha256'] = RSAExchange
    ExtendedTransport._kex_info['rsa1024-sha1'] = type('RSA1024', (RSAExchange,), {
        'hash_algo': staticmethod(hashlib.sha1), 'hash_class': hashes.SHA1})
    class GSSExchange:
        """Independent RFC 4462 / RFC 8732 initiator, authenticated by MIT GSS."""
        hash_algo = staticmethod(hashlib.sha256)
        group = None
        curve = None
        exchange_group = False
        def __init__(self, transport):
            self.transport = transport
            self.host = b''
            self.group_fields = b''
        def start_kex(self):
            import gssapi
            spec = self.transport.task_spec
            if self.transport.server_mode:
                assert self.curve == 'x25519'
                service = gssapi.Name(spec['gss_service'], name_type=gssapi.NameType.kerberos_principal)
                creds = gssapi.Credentials(name=service, usage='accept', store={'keytab': spec['gss_keytab']})
                self.context = gssapi.SecurityContext(creds=creds, usage='accept')
                self.private = x25519.X25519PrivateKey.generate()
                self.public = self.private.public_key().public_bytes_raw()
                self.transport._expect_packet(30)
                return
            creds = gssapi.Credentials(usage='initiate', store={'ccache': spec['gss_cache']})
            self.context = gssapi.SecurityContext(creds=creds,
                name=gssapi.Name(spec['gss_service'], name_type=gssapi.NameType.kerberos_principal),
                usage='initiate', flags=[gssapi.RequirementFlag.mutual_authentication,
                                         gssapi.RequirementFlag.integrity])
            if self.exchange_group:
                request = Message()
                request.add_byte(b'\x28')
                request.add_int(1024)
                request.add_int(2048)
                request.add_int(8192)
                self.transport._send_message(request)
                self.transport._expect_packet(41)
            else:
                if self.group:
                    self.p, self.g = self.group, 2
                self.send_init()
        def send_init(self):
            if self.curve:
                if self.curve == 'x25519':
                    self.private = x25519.X25519PrivateKey.generate()
                    self.public = self.private.public_key().public_bytes_raw()
                elif self.curve == 'x448':
                    self.private = x448.X448PrivateKey.generate()
                    self.public = self.private.public_key().public_bytes_raw()
                else:
                    self.private = ec.generate_private_key(self.curve)
                    self.public = self.private.public_key().public_bytes(
                        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
                self.client_value = pack(self.public)
            else:
                self.exponent = secrets.randbits(256)
                self.public = pow(self.g, self.exponent, self.p)
                message = Message()
                message.add_mpint(self.public)
                self.client_value = message.asbytes()
            msg = Message()
            msg.add_byte(b'\x1e')
            msg.add_string(self.context.step())
            msg.add_bytes(self.client_value)
            self.transport._send_message(msg)
            self.transport._expect_packet(31, 32, 33, 34)
        def parse_next(self, kind, msg):
            if self.transport.server_mode:
                assert kind == 30
                token, peer = msg.get_string(), msg.get_string()
                response = self.context.step(token)
                assert self.context.complete
                shared = int.from_bytes(self.private.exchange(
                    x25519.X25519PublicKey.from_public_bytes(peer)), 'big')
                hm = Message()
                hm.add(self.transport.remote_version, self.transport.local_version,
                       self.transport.remote_kex_init, self.transport.local_kex_init,
                       b'', peer, self.public)
                hm.add_mpint(shared)
                exchange_hash = self.hash_algo(hm.asbytes()).digest()
                self.transport._set_K_H(shared, exchange_hash)
                context = self.context
                class AuthContext:
                    def ssh_check_mic(self, mic, session_id, username):
                        challenge = (pack(session_id) + b'\x32' + pack(username.encode()) +
                                     pack(b'ssh-connection') + pack(b'gssapi-keyex'))
                        context.verify_signature(challenge, mic)
                self.transport.kexgss_ctxt = AuthContext()
                self.transport.gss_kex_used = True
                msg = Message()
                msg.add_byte(b'\x20')
                msg.add_string(self.public)
                msg.add_string(self.context.get_signature(exchange_hash))
                msg.add_boolean(response is not None)
                if response is not None:
                    msg.add_string(response)
                self.transport._send_message(msg)
                self.transport._activate_outbound()
                return
            if kind == 41:
                self.p, self.g = msg.get_mpint(), msg.get_mpint()
                assert 1024 <= self.p.bit_length() <= 8192
                fields = Message()
                fields.add_int(1024)
                fields.add_int(2048)
                fields.add_int(8192)
                fields.add_mpint(self.p)
                fields.add_mpint(self.g)
                self.group_fields = fields.asbytes()
                self.send_init()
                return
            if kind == 33:
                self.host = msg.get_string()
                self.transport._expect_packet(31, 32, 34)
                return
            if kind == 31:
                token = self.context.step(msg.get_string())
                response = Message()
                response.add_byte(b'\x1f')
                response.add_string(token)
                self.transport._send_message(response)
                self.transport._expect_packet(31, 32, 34)
                return
            assert kind == 32, ('GSS exchange failed', kind, msg.asbytes())
            server = Message()
            if self.curve:
                public = msg.get_string()
                server.add_string(public)
                if self.curve == 'x25519':
                    shared = self.private.exchange(x25519.X25519PublicKey.from_public_bytes(public))
                elif self.curve == 'x448':
                    shared = self.private.exchange(x448.X448PublicKey.from_public_bytes(public))
                else:
                    shared = self.private.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(self.curve, public))
                shared = int.from_bytes(shared, 'big')
            else:
                public = msg.get_mpint()
                assert 1 < public < self.p - 1
                server.add_mpint(public)
                shared = pow(public, self.exponent, self.p)
            mic = msg.get_string()
            if msg.get_boolean():
                assert self.context.step(msg.get_string()) is None
            assert self.context.complete
            hm = Message()
            hm.add(self.transport.local_version, self.transport.remote_version,
                   self.transport.local_kex_init, self.transport.remote_kex_init, self.host)
            hm.add_bytes(self.group_fields + self.client_value + server.asbytes())
            hm.add_mpint(shared)
            exchange_hash = self.hash_algo(hm.asbytes()).digest()
            self.context.verify_signature(exchange_hash, mic)
            self.transport._set_K_H(shared, exchange_hash)
            self.transport._activate_outbound()

    from paramiko.kex_group1 import KexGroup1
    from paramiko.kex_group16 import KexGroup16SHA512
    group_values = {1: KexGroup1.P, 14: KexGroup14.P,
                    15: prime(3072, 1690314), 16: KexGroup16SHA512.P,
                    17: prime(6144, 929484), 18: prime(8192, 4743158)}
    for group, digests in ((1, ('sha1',)), (14, ('sha1', 'sha256')),
                           (15, ('sha512',)), (16, ('sha512',)),
                           (17, ('sha512',)), (18, ('sha512',))):
        for digest in digests:
            prefix = f'gss-group{group}-{digest}'
            ExtendedTransport._kex_info[prefix + '-toWM5Slw5Ew8Mqkay+al2g=='] = type('GSSFixed', (GSSExchange,), {
                'group': group_values[group], 'hash_algo': staticmethod(getattr(hashlib, digest))})
    for digest in ('sha1', 'sha256'):
        ExtendedTransport._kex_info['gss-gex-' + digest + '-toWM5Slw5Ew8Mqkay+al2g=='] = type('GSSGex', (GSSExchange,), {
            'exchange_group': True, 'hash_algo': staticmethod(getattr(hashlib, digest))})
    for curve, name, digest in (('x25519', 'curve25519', 'sha256'),
            ('x448', 'curve448', 'sha512'), (ec.SECP256R1(), 'nistp256', 'sha256'),
            (ec.SECP384R1(), 'nistp384', 'sha384'), (ec.SECP521R1(), 'nistp521', 'sha512'),
            (ec.SECP256K1(), '1.3.132.0.10', 'sha256')):
        prefix = 'gss-' + name + '-' + digest
        ExtendedTransport._kex_info[prefix + '-toWM5Slw5Ew8Mqkay+al2g=='] = type('GSSECDH', (GSSExchange,), {
            'curve': curve, 'hash_algo': staticmethod(getattr(hashlib, digest))})
    from paramiko.auth_handler import AuthHandler
    original_auth = AuthHandler._parse_userauth_request
    def userauth(self, message):
        spec = self.transport.task_spec
        request = Message(message.asbytes())
        username, service, method = request.get_text(), request.get_text(), request.get_text()
        if method == 'gssapi-with-mic' and spec.get('gss_service'):
            import gssapi
            mechanisms = [request.get_string() for _ in range(request.get_int())]
            kerberos_oid = bytes.fromhex('06092a864886f712010202')
            assert kerberos_oid in mechanisms and service == 'ssh-connection'
            credentials = gssapi.Credentials(usage='accept', store={'keytab': spec['gss_keytab']})
            self.independent_gss = gssapi.SecurityContext(creds=credentials, usage='accept')
            self.auth_username = username
            response = Message()
            response.add_byte(b'\x3c')
            response.add_string(kerberos_oid)
            self.transport._send_message(response)
            return
        if spec.get('reject_keyex'):
            if method == 'gssapi-keyex':
                self.transport.kexgss_ctxt.ssh_check_mic(request.get_string(), self.transport.session_id, username)
                self.auth_username = username
                self._send_auth_result(username, method, paramiko.AUTH_FAILED)
                return
        return original_auth(self, message)
    AuthHandler._parse_userauth_request = userauth
    original_table = AuthHandler._server_handler_table.fget
    def gss_token(self, message):
        token = self.independent_gss.step(message.get_string())
        if token is not None:
            response = Message()
            response.add_byte(b'\x3d')
            response.add_string(token)
            self.transport._send_message(response)
    def gss_mic(self, message):
        assert self.independent_gss.complete
        challenge = (pack(self.transport.session_id) + b'\x32' +
                     pack(self.auth_username.encode()) + pack(b'ssh-connection') +
                     pack(b'gssapi-with-mic'))
        self.independent_gss.verify_signature(challenge, message.get_string())
        self._send_auth_result(self.auth_username, 'gssapi-with-mic', paramiko.AUTH_SUCCESSFUL)
    def server_handlers(self):
        handlers = original_table(self)
        if hasattr(self, 'independent_gss'):
            handlers.update({61: lambda message: gss_token(self, message),
                             66: lambda message: gss_mic(self, message)})
        return handlers
    AuthHandler._server_handler_table = property(server_handlers)
    return ExtendedTransport


def pack(value):
    return struct.pack('>I', len(value)) + value


def client(spec, Transport):
    from paramiko.ssh_exception import IncompatiblePeer
    with socket.create_connection(('127.0.0.1', spec['port']), timeout=10) as sock:
        with Transport(sock) as transport:
            transport.task_spec = spec
            settings = transport.get_security_options()
            settings.kex = (spec.get('kex', 'curve25519-sha256@libssh.org'),)
            settings.ciphers = (spec.get('cipher', 'aes128-ctr'),)
            settings.digests = (spec.get('mac', 'hmac-sha2-256'),)
            settings.compression = (spec.get('compression', 'none'),)
            if 'signature' in spec:
                settings.key_types = (spec['signature'],)
            if 'user_signature' in spec:
                transport._preferred_pubkeys = (spec['user_signature'],)
            try:
                transport.start_client(timeout=15)
            except IncompatiblePeer:
                assert spec.get('refused'), 'No matching algorithm'
                return {'refused': True}
            assert not spec.get('refused'), 'Disabled algorithm was accepted'
            if 'private' in spec:
                key = Transport.external_key(private=spec['private'], algorithm=spec['algorithm'],
                    certificate=spec.get('certificate'))
                try:
                    transport.auth_publickey('member', key)
                except paramiko.AuthenticationException:
                    assert spec.get('denied'), 'Authentication was refused'
                    return {'denied': True}
                assert not spec.get('denied'), 'Authentication was accepted'
            else:
                transport.auth_none('member')
            if spec.get('ignore_keepalives'):
                deadline = time.monotonic() + 15
                while transport.is_active() and time.monotonic() < deadline:
                    time.sleep(0.02)
                assert not transport.is_active(), 'Peer did not enforce unanswered keepalive allowance'
                return {'records': transport.packetizer.records,
                        'global_requests': transport.packetizer.global_requests}
            channel = transport.open_session(timeout=10)
            channel.settimeout(15)
            if spec.get('measure'):
                channel.exec_command('volume')
                if spec['measure'] == 'bytes':
                    requests = [(0, 2**20)]
                else:
                    requests = [(0, 257), (0.3, 257), (1.2, 257)]
                origin = time.monotonic()
                for delay, size in requests:
                    pause = origin + delay - time.monotonic()
                    if pause > 0:
                        time.sleep(pause)
                    block = os.urandom(32)
                    channel.sendall(struct.pack('>I', size) + block)
                    received = bytearray()
                    while len(received) < size:
                        part = channel.recv(size - len(received))
                        assert part, 'Unexpected EOF before requested data'
                        received.extend(part)
                    assert received == (block * ((size+31)//32))[:size]
                channel.sendall(struct.pack('>I', 0))
                channel.shutdown_write()
                assert channel.recv(1) == b''
            else:
                channel.exec_command('receive')
                data = os.urandom(5003) + b'compressible\0' * 4000
                channel.sendall(data)
                channel.shutdown_write()
                received = bytearray()
                while part := channel.recv(65536):
                    received.extend(part)
                assert received == b'received:' + data
            assert channel.recv_exit_status() == 0
            channel.close()
            return {'received': len(received), 'refused': False,
                    'records': transport.packetizer.records,
                    'order': transport.packetizer.order,
                    'signatures': Transport.external_key.verified,
                    'signed': Transport.external_key.signed}


def server(spec, Transport):
    """A real server which can prove or falsely claim additional host keys."""
    retained = paramiko.RSAKey.from_private_key(io.StringIO(spec['retained']))
    added = paramiko.RSAKey.from_private_key(io.StringIO(spec['added']))
    signer = retained if spec['invalid'] else added
    # Counts exec requests: start_server() returns before auth and channel open, so a request can
    # arrive before the loop below starts waiting; a cleared Event would lose that wakeup.
    completed = threading.Semaphore(0)
    class Policy(paramiko.ServerInterface):
        def check_auth_none(self, username):
            return paramiko.AUTH_SUCCESSFUL
        def check_channel_request(self, kind, chanid):
            assert kind == 'session'
            return paramiko.OPEN_SUCCEEDED
        def check_channel_exec_request(self, channel, command):
            completed.release()
            return True
        def check_global_request(self, kind, message):
            if kind != 'hostkeys-prove-00@openssh.com':
                return False
            proofs = []
            while message.get_remainder():
                key = message.get_string()
                assert key in (retained.asbytes(), added.asbytes())
                challenge = pack(b'hostkeys-prove-00@openssh.com') + pack(transport.session_id) + pack(key)
                signing_key = signer if key == added.asbytes() else retained
                proofs.append(signing_key.sign_ssh_data(challenge).asbytes())
            return tuple(proofs)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(15)
        print(json.dumps({'port': listener.getsockname()[1]}), flush=True)
        sock, _ = listener.accept()
        with sock, Transport(sock) as transport:
            transport.task_spec = spec
            transport.add_server_key(retained)
            transport.start_server(server=Policy())
            for index in range(2):
                channel = transport.accept(15)
                assert channel is not None and completed.acquire(timeout=15)
                if index == 0:
                    transport.global_request('hostkeys-00@openssh.com', (retained.asbytes(), added.asbytes()), wait=False)
                channel.settimeout(15)
                data = bytearray()
                while part := channel.recv(65536):
                    data.extend(part)
                channel.sendall(b'received:' + data)
                channel.send_exit_status(0)
                channel.shutdown_write()
                channel.close()
            # Keep the encrypted transport until the caller closes it.
            deadline = time.monotonic() + 15
            while transport.is_active() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert not transport.is_active(), 'Client did not close transport'
    return {'completed': True}


def selection_server(spec, Transport):
    """Independent server records negotiated algorithms after carrying data."""
    completed = threading.Event()
    class Policy(paramiko.ServerInterface):
        def check_auth_none(self, username):
            return paramiko.AUTH_FAILED if 'pubkeys' in spec['algorithms'] or spec.get('gss_service') else paramiko.AUTH_SUCCESSFUL
        def get_allowed_auths(self, username):
            return 'gssapi-keyex,gssapi-with-mic' if spec.get('gss_service') else 'publickey'
        def enable_auth_gssapi(self):
            return bool(spec.get('gss_service'))
        def check_auth_gssapi_keyex(self, username, status):
            return status
        def check_auth_gssapi_with_mic(self, username, status, gss_authenticated=1):
            return status
        def check_auth_publickey(self, username, key):
            return paramiko.AUTH_SUCCESSFUL
        def check_channel_request(self, kind, chanid):
            return paramiko.OPEN_SUCCEEDED
        def check_channel_exec_request(self, channel, command):
            completed.set()
            return True
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(15)
        print(json.dumps({'port': listener.getsockname()[1]}), flush=True)
        sock, _ = listener.accept()
        with sock, Transport(sock) as transport:
            transport.task_spec = spec
            transport.set_gss_host('localhost', trust_dns=False)
            if 'host_private' in spec:
                # A certified host identity: the certificate blob is the host key.
                key = Transport.external_key(private=spec['host_private'],
                    algorithm=spec['host_algorithm'], certificate=spec['host_certificate'])
                key.asbytes = lambda: key.public_blob.key_blob
                key.get_name = lambda: key.public_blob.key_type
            else:
                key = paramiko.RSAKey.from_private_key(io.StringIO(spec['key']))
            if spec.get('forged_by'):
                # Present the trusted host key but sign the exchange hash with another key.
                forger = paramiko.RSAKey.from_private_key(io.StringIO(spec['forged_by']))
                key.sign_ssh_data = forger.sign_ssh_data
            transport.add_server_key(key)
            settings = transport.get_security_options()
            for name, value in spec['algorithms'].items():
                if name == 'pubkeys':
                    transport._preferred_pubkeys = tuple(value)
                else:
                    setattr(settings, name, tuple(value))
            if spec.get('expect_failure'):
                # The client is expected to abandon the connection.
                try:
                    transport.start_server(server=Policy())
                except (paramiko.SSHException, EOFError, OSError):
                    pass
                deadline = time.monotonic() + 15
                while transport.is_active() and time.monotonic() < deadline:
                    time.sleep(0.02)
                assert not transport.is_active(), 'Client did not abandon the connection'
                return {'authenticated': transport.is_authenticated(),
                        'records': transport.packetizer.records}
            transport.start_server(server=Policy())
            if spec.get('ignore_keepalives'):
                deadline = time.monotonic() + 15
                while transport.is_active() and time.monotonic() < deadline:
                    time.sleep(0.02)
                assert not transport.is_active(), 'Peer did not enforce unanswered keepalive allowance'
                return {'records': transport.packetizer.records,
                        'global_requests': transport.packetizer.global_requests}
            channel = transport.accept(15)
            assert channel is not None and completed.wait(15)
            channel.settimeout(15)
            data = bytearray()
            while part := channel.recv(65536):
                data.extend(part)
            channel.sendall(b'received:' + data)
            channel.send_exit_status(0)
            channel.shutdown_write()
            channel.close()
            result = {'kex': transport.selected_kex, 'ciphers': transport.remote_cipher,
                      'digests': transport.remote_mac, 'compression': transport.remote_compression,
                      'key_types': transport.host_key_type,
                      'pubkeys': Transport.external_key.verified[-1] if Transport.external_key.verified else None}
            deadline = time.monotonic() + 15
            while transport.is_active() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert not transport.is_active()
            result['records'] = transport.packetizer.records
            result['order'] = transport.packetizer.order
            result['methods'] = transport.packetizer.methods
            return result


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as directory:
        for name in ('F06_paramiko.whl', 'F06_pynacl.whl'):
            with zipfile.ZipFile(Path(__file__).with_name(name)) as archive:
                archive.extractall(directory)
        sys.path.insert(0, directory)
        transport_class = initialize()
        spec = json.loads(sys.stdin.readline())
        result = {'client': client, 'server': server, 'selection': selection_server}[sys.argv[1]](spec, transport_class)
        print(json.dumps(result), flush=True)
