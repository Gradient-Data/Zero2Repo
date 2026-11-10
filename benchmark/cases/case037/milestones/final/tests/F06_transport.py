# feature: F06
"""Acceptance checks for real SSH transport and connection policy."""
import asyncio
import socket
import os
import json
import sys
from pathlib import Path
import struct
import time

import velnora
import pytest

from _helpers import bounded, run_async, socket_pair, tcp_server, temporary_environment, opened_connection
from F01_helpers import identity, read_public
from F02_helpers import certificate_identity
from F03_helpers import host_line
from F04_helpers import ConfigPeer
from F06_helpers import (transport_listener, client_options, checked_exchange,
                         openssh_exchange, openssh_daemon, daemon_connect,
                         echo_session, wire_proxy, ClientClosure, ServerClosure, volume_session,
                         independent_exchange, independent_hostkeys, assert_rekey_boundary,
                         expect_connection_timeout, independent_selection)


def test_tcp_and_connected_socket_roles(tmp_path):
    async def scenario():
        async with transport_listener() as (listener, key):
            await openssh_exchange(listener.get_port())
            async with velnora.connect('127.0.0.1', listener.get_port(),
                                       **client_options()) as conn:
                await checked_exchange(conn)
            sock = socket.socket()
            sock.setblocking(False)
            await asyncio.get_running_loop().sock_connect(
                sock, ('127.0.0.1', listener.get_port()))
            async with velnora.connect(sock=sock, **client_options()) as conn:
                await checked_exchange(conn, os.urandom(7919))
        key, _ = certificate_identity()
        async with velnora.listen('127.0.0.1', config=None, server_factory=ConfigPeer,
                server_host_keys=[key], process_factory=echo_session, encoding=None) as listener:
            assert listener.get_port() == 22
            async with velnora.connect('127.0.0.1', **client_options()) as conn:
                await checked_exchange(conn, b'default port')
        with socket_pair() as (left, right):
            server_task = asyncio.ensure_future(velnora.run_server(
                left, config=None, server_factory=ConfigPeer,
                server_host_keys=[key], process_factory=echo_session, encoding=None))
            try:
                async with velnora.run_client(right, host="127.0.0.1", **client_options()) as conn:
                    server = await bounded(server_task)
                    await checked_exchange(conn, b'connected socket roles\xff')
                    assert server.get_extra_info('username') == 'member'
                await bounded(server.wait_closed())
            finally:
                if not server_task.done():
                    server_task.cancel()
                    await asyncio.gather(server_task, return_exceptions=True)
        async with openssh_daemon(tmp_path / 'peer') as (port, user_key, keys, service):
            async with opened_connection(daemon_connect(port, user_key)) as conn:
                data = b'Independent OpenSSH server\x00\xff\n' * 31
                result = await bounded(conn.run('cat', input=data, encoding=None))
                assert result.exit_status == 0, result.stderr
                assert result.stdout == data
                assert conn.get_server_host_key() == keys[0].convert_to_public()
        return 'test_tcp_and_connected_socket_roles'
    assert run_async(scenario(), timeout=40) == 'test_tcp_and_connected_socket_roles'


def test_invalid_transport_and_ciphertext_integrity():
    async def scenario():
        for banner, packet, failure in (
                (b'SSH-1.0-independent\r\n', b'', velnora.ProtocolNotSupported),
                (b'SSH-2.0-independent\r\n', struct.pack('>IB', 12, 10) +
                 b'\x15' + bytes(10), velnora.ProtocolError)):
            finished = asyncio.get_running_loop().create_future()

            async def invalid_peer(reader, writer):
                try:
                    writer.write(banner)
                    await reader.readline()
                    writer.write(packet)
                    await writer.drain()
                    await reader.read()
                finally:
                    writer.close()
                    await writer.wait_closed()
                    finished.set_result(True)

            async with tcp_server(invalid_peer, host='127.0.0.1') as listener:
                with pytest.raises(failure):
                    await bounded(velnora.connect('127.0.0.1',
                        listener.sockets[0].getsockname()[1], **client_options()))
                await bounded(finished)
        # Encrypt-then-MAC and an AEAD cipher, with corruption in either direction.
        for cipher, macs in (('aes128-ctr', ['hmac-sha2-256-etm@openssh.com']),
                             ('chacha20-poly1305@openssh.com', ())):
            algorithms = dict(encryption_algs=[cipher], **({'mac_algs': macs} if macs else {}))
            for direction in ('to client', 'to server'):
                delivered = []

                async def recording_session(process):
                    data = bytearray()
                    while chunk := await process.stdin.read(65536):
                        data.extend(chunk)
                        delivered.append(bytes(chunk))
                    process.stdout.write(b'received:' + data)
                    process.exit(0)

                authenticated = asyncio.get_running_loop().create_future()
                server_closed = asyncio.get_running_loop().create_future()
                async with transport_listener(process_factory=recording_session,
                        server_factory=lambda: ServerClosure(authenticated, server_closed),
                        **algorithms) as (listener, _):
                    async with wire_proxy(listener.get_port()) as (port, state):
                        closed = asyncio.get_running_loop().create_future()
                        async with velnora.connect('127.0.0.1', port,
                                **client_options(client_factory=lambda: ClientClosure(closed),
                                                 **algorithms)) as conn:
                            await checked_exchange(conn, b'baseline before corruption')
                            assert conn.get_extra_info('send_cipher') == cipher
                            delivered.clear()
                            process = await conn.create_process('receive', encoding=None)
                            if direction == 'to client':
                                state['corrupt'] = True
                                result = await bounded(process.communicate(
                                    b'corrupted response must not arrive'))
                                await bounded(conn.wait_closed())
                                assert isinstance(await bounded(closed), velnora.MACError)
                                assert result[0] != b'received:corrupted response must not arrive'
                            else:
                                state['corrupt_client'] = True
                                process.stdin.write(b'corrupted request must not arrive')
                                assert isinstance(await bounded(server_closed), velnora.MACError)
                                await bounded(conn.wait_closed())
                                assert delivered == []
                            assert state['flipped']
                            assert conn.is_closed()
        return 'test_invalid_transport_and_ciphertext_integrity'
    assert run_async(scenario(), timeout=30) == 'test_invalid_transport_and_ciphertext_integrity'


def test_host_key_trust_and_disabled_verification(tmp_path):
    async def scenario():
        other, _ = certificate_identity()
        async with transport_listener() as (listener, key):
            for trust, accepted in (([key.convert_to_public()], True), ([], False), ([other.convert_to_public()], False)):
                options = client_options()
                options['known_hosts'] = (trust, [], [])
                if accepted:
                    async with velnora.connect('127.0.0.1', listener.get_port(), **options) as conn:
                        await checked_exchange(conn)
                else:
                    with pytest.raises(velnora.HostKeyNotVerifiable):
                        async with velnora.connect('127.0.0.1', listener.get_port(), **options):
                            pass
            options = client_options()
            options['known_hosts'] = ([key.convert_to_public()], [], [key.convert_to_public()])
            with pytest.raises(velnora.HostKeyNotVerifiable):
                async with velnora.connect('127.0.0.1', listener.get_port(), **options):
                    pass
            async with velnora.connect('127.0.0.1', listener.get_port(), **client_options()) as conn:
                await checked_exchange(conn)
        # An independent server presents the trusted host key; only the private
        # key which signs its exchange hash differs between the two arms.
        trusted, _ = certificate_identity('ssh-rsa')
        forger, _ = certificate_identity('ssh-rsa')
        for forged in (False, True):
            async with independent_selection({}, host_key=trusted, expect_failure=forged,
                    forged_by=forger.export_private_key('pkcs1-pem').decode() if forged else None) as (port, observed):
                options = client_options()
                options['known_hosts'] = ([trusted.convert_to_public()], [], [])
                if forged:
                    with pytest.raises((velnora.KeyExchangeFailed, velnora.HostKeyNotVerifiable,
                                        velnora.ProtocolError)):
                        async with velnora.connect('127.0.0.1', port, **options):
                            pytest.fail('A host signature from another private key was accepted')
                else:
                    async with velnora.connect('127.0.0.1', port, **options) as conn:
                        await checked_exchange(conn, b'genuine host signature')
            if forged:
                assert observed['authenticated'] is False
        home = tmp_path / 'trust-home'
        (home / '.ssh').mkdir(parents=True)
        async with transport_listener() as (listener, key):
            options = client_options()
            del options['known_hosts']
            with temporary_environment({'HOME': str(home)}):
                with pytest.raises(velnora.HostKeyNotVerifiable):
                    async with velnora.connect('127.0.0.1', listener.get_port(), **options):
                        pytest.fail('No default trust material was installed')
                path = home / '.ssh' / 'known_hosts'
                path.write_text(host_line(f'[127.0.0.1]:{listener.get_port()}', key))
                async with velnora.connect('127.0.0.1', listener.get_port(), **options) as conn:
                    await checked_exchange(conn, b'local default host trust')
                path.write_text(host_line(f'[127.0.0.1]:{listener.get_port()}', other))
                with pytest.raises(velnora.HostKeyNotVerifiable):
                    async with velnora.connect('127.0.0.1', listener.get_port(), **options):
                        pytest.fail('Changed default host trust was ignored')
        async with transport_listener() as (listener, key):
            for approved in (True, False):
                decisions = []
                class HostValidation(velnora.SSHClient):
                    def validate_host_public_key(self, host, addr, port, presented):
                        decisions.append((host, addr, port, presented))
                        return approved and presented == key.convert_to_public()
                settings = client_options(client_factory=HostValidation)
                settings['known_hosts'] = ([], [], [])
                if approved:
                    async with velnora.connect('127.0.0.1', listener.get_port(), **settings) as conn:
                        await checked_exchange(conn, b'caller-approved host identity')
                else:
                    with pytest.raises(velnora.HostKeyNotVerifiable):
                        async with velnora.connect('127.0.0.1', listener.get_port(), **settings):
                            pytest.fail('A rejected custom host policy granted access')
                assert decisions
                assert all(row == ('127.0.0.1', '127.0.0.1', listener.get_port(),
                                    key.convert_to_public()) for row in decisions)
        return 'test_host_key_trust_and_disabled_verification'
    assert run_async(scenario(), timeout=30) == 'test_host_key_trust_and_disabled_verification'


def test_host_certificates_and_aliases():
    async def scenario():
        host, _ = certificate_identity()
        ca, _ = certificate_identity()
        other_ca, _ = certificate_identity()
        now = int(time.time())
        valid = ca.generate_host_certificate(host, 'host', principals=['service.example'])
        invalid = [
            ca.generate_user_certificate(host, 'user', principals=['service.example']),
            other_ca.generate_host_certificate(host, 'untrusted', principals=['service.example']),
            ca.generate_host_certificate(host, 'expired', principals=['service.example'],
                                         valid_before=now - 60),
            ca.generate_host_certificate(host, 'future', principals=['service.example'],
                                         valid_after=now + 3600),
            ca.generate_host_certificate(host, 'wrong name', principals=['other.example'])]
        for cert in [valid, *invalid]:
            async with transport_listener(server_host_keys=[(host, cert)]) as (listener, _):
                options = client_options(host_key_alias='service.example')
                options['known_hosts'] = velnora.import_known_hosts(
                    host_line('service.example', ca, '@cert-authority'))
                if cert is valid:
                    async with velnora.connect('127.0.0.1', listener.get_port(), **options) as conn:
                        await checked_exchange(conn)
                else:
                    with pytest.raises(velnora.HostKeyNotVerifiable):
                        async with velnora.connect('127.0.0.1', listener.get_port(), **options):
                            pass
        async with transport_listener(server_host_keys=[host]) as (listener, _):
            options = client_options(host_key_alias='service.example')
            options['known_hosts'] = velnora.import_known_hosts(host_line('service.example', host))
            async with velnora.connect('127.0.0.1', listener.get_port(), **options) as conn:
                await checked_exchange(conn)
        # An independent server presents the valid certificate, then the same
        # certificate with one bit of the authority's signature changed.
        import base64
        blob = base64.b64decode(valid.export_certificate('openssh').split()[1])
        tampered = blob[:-1] + bytes([blob[-1] ^ 1])
        for certificate, accepted in ((blob, True), (tampered, False)):
            async with independent_selection({}, expect_failure=not accepted,
                    host_private=host.export_private_key('pkcs8-pem').decode(),
                    host_algorithm='ssh-ed25519',
                    host_certificate=base64.b64encode(certificate).decode()) as (port, observed):
                options = client_options(host_key_alias='service.example')
                options['known_hosts'] = velnora.import_known_hosts(
                    host_line('service.example', ca, '@cert-authority'))
                if accepted:
                    async with velnora.connect('127.0.0.1', port, **options) as conn:
                        await checked_exchange(conn, b'independently presented host certificate')
                else:
                    with pytest.raises(velnora.HostKeyNotVerifiable):
                        async with velnora.connect('127.0.0.1', port, **options):
                            pytest.fail('A certificate with an invalid signature was trusted')
            if not accepted:
                assert observed['authenticated'] is False
        return 'test_host_certificates_and_aliases'
    assert run_async(scenario(), timeout=40) == 'test_host_certificates_and_aliases'


def test_algorithm_selection_and_rejection():
    async def scenario():
        # The independent client's first mutually supported cipher must win.
        async with transport_listener(encryption_algs=['aes128-ctr', 'aes256-ctr']) as (listener, _):
            _, diagnostic = await openssh_exchange(listener.get_port(),
                options=['Ciphers=aes256-ctr,aes128-ctr'])
            assert b'cipher: aes256-ctr ' in diagnostic
        async with transport_listener() as (listener, _):
            for selection, expected in (
                    ('aes128-*', 'aes128-ctr'),
                    ('^aes128-ctr', 'aes128-ctr'),
                    ('+aes256-cbc', 'aes256-cbc'),
                    ('-aes128-ctr', 'aes256-ctr')):
                # Restrict the peer so the requested addition/removal is observable.
                peer = ['aes256-cbc'] if selection.startswith('+') else ['aes128-ctr', 'aes256-ctr']
                async with transport_listener(encryption_algs=peer) as (restricted, _):
                    async with velnora.connect('127.0.0.1', restricted.get_port(),
                        **client_options(encryption_algs=selection)) as conn:
                        assert conn.get_extra_info('send_cipher') == expected
                        await checked_exchange(conn)
            for option in ('kex_algs', 'encryption_algs', 'mac_algs',
                           'compression_algs', 'signature_algs'):
                with pytest.raises(ValueError):
                    await velnora.connect('127.0.0.1', listener.get_port(),
                                           **client_options(**{option: ['unknown-algorithm']}))
        async with transport_listener(encryption_algs=['aes128-ctr']) as (listener, _):
            with pytest.raises(velnora.KeyExchangeFailed):
                await velnora.connect('127.0.0.1', listener.get_port(),
                    **client_options(encryption_algs=['aes256-ctr']))
        # Every family has ordered selection and set operations. The independent
        # server verifies decrypted data, then reports what it actually negotiated.
        families = (
            ('kex_algs', 'kex', ['ecdh-sha2-nistp256', 'ecdh-sha2-nistp384'],
             'diffie-hellman-group1-sha1', 'ecdh-sha2-nistp25?'),
            ('encryption_algs', 'ciphers', ['aes128-ctr', 'aes256-ctr'],
             'aes256-cbc', 'aes128-ct?'),
            ('mac_algs', 'digests', ['hmac-sha2-256', 'hmac-sha2-512'],
             'hmac-md5', 'hmac-sha2-25?'),
            ('compression_algs', 'compression', ['none', 'zlib@openssh.com'],
             'zlib', 'non?'),
            ('signature_algs', 'pubkeys', ['rsa-sha2-256', 'rsa-sha2-512'],
             'ssh-dss', 'rsa-sha2-25?'))
        signing_key, _ = certificate_identity('ssh-rsa')
        dsa_signing_key, _ = certificate_identity('ssh-dss')
        for option, field, pair, addition, pattern in families:
            selections = [(list(reversed(pair)), pair[1], pair),
                          (pattern, pair[0], pair),
                          ('^' + pair[1], pair[1], pair),
                          ('-' + pair[0], pair[1], pair)]
            # Signature choices filter permitted signing algorithms; their order
            # does not override the identity's own preferences.
            if option == 'signature_algs':
                selections[0] = (list(reversed(pair)), pair, pair)
                selections[2] = ('^' + pair[1], pair, pair)
                selections.append(('+ssh-dss', 'ssh-dss', ['ssh-dss']))
            else:
                selections.append(('+' + addition, addition, [addition]))
            for selection, expected, peer in selections:
                settings = {'ciphers': ['aes128-ctr'], 'digests': ['hmac-sha2-256']}
                settings[field] = peer
                async with independent_selection(settings) as (port, observed):
                    async with velnora.connect('127.0.0.1', port,
                            **dict(client_options(**{option: selection}),
                                   client_keys=[dsa_signing_key if selection == '+ssh-dss' else signing_key] if option == 'signature_algs' else [])) as conn:
                        await checked_exchange(conn, repr(selection).encode())
                assert observed[field] in (expected if isinstance(expected, list) else [expected]), (option, selection, observed)
        # A default client refuses a peer offering only choices outside the
        # default selection; the same offers succeed above once explicitly added.
        for field, offered in (('kex', 'diffie-hellman-group1-sha1'),
                               ('ciphers', 'aes256-cbc'), ('digests', 'hmac-md5')):
            settings = {'ciphers': ['aes128-ctr'], 'digests': ['hmac-sha2-256'], field: [offered]}
            async with independent_selection(settings, expect_failure=True) as (port, observed):
                # Either side may notice the empty intersection first.
                with pytest.raises((velnora.KeyExchangeFailed, velnora.ConnectionLost)):
                    async with velnora.connect('127.0.0.1', port, **client_options()):
                        pytest.fail('A non-default choice was accepted by default: ' + offered)
            # The independent peer never received the client's NEWKEYS.
            assert observed['authenticated'] is False
            assert not any(row[1] == 21 for row in observed['records']), offered
        return 'test_algorithm_selection_and_rejection'
    assert run_async(scenario(), timeout=120) == 'test_algorithm_selection_and_rejection'


def test_software_key_exchange_with_independent_peer(tmp_path):
    async def scenario():
        algorithms = (
            'curve25519-sha256', 'curve25519-sha256@libssh.org',
            'ecdh-sha2-nistp256', 'ecdh-sha2-nistp384', 'ecdh-sha2-nistp521',
            'diffie-hellman-group1-sha1', 'diffie-hellman-group14-sha1',
            'diffie-hellman-group14-sha256', 'diffie-hellman-group16-sha512',
            'diffie-hellman-group18-sha512', 'diffie-hellman-group-exchange-sha1',
            'diffie-hellman-group-exchange-sha256')
        for algorithm in algorithms:
            async with transport_listener(kex_algs=[algorithm]) as (listener, _):
                await openssh_exchange(listener.get_port(), options=['KexAlgorithms=' + algorithm])
        # These distinct software choices are not offered by the installed ssh.
        modern = ('curve448-sha512', 'ecdh-sha2-1.3.132.0.10',
                  'diffie-hellman-group15-sha512', 'diffie-hellman-group17-sha512',
                  'rsa2048-sha256', 'mlkem768x25519-sha256',
                  'mlkem768nistp256-sha256', 'mlkem1024nistp384-sha384')
        legacy = ('diffie-hellman-group14-sha224@ssh.com',
                  'diffie-hellman-group15-sha256@ssh.com', 'diffie-hellman-group15-sha384@ssh.com',
                  'diffie-hellman-group16-sha384@ssh.com',
                  'diffie-hellman-group-exchange-sha224@ssh.com',
                  'diffie-hellman-group-exchange-sha384@ssh.com',
                  'diffie-hellman-group-exchange-sha512@ssh.com', 'rsa1024-sha1')
        for algorithm in (*modern, *legacy):
            async with transport_listener(kex_algs=[algorithm]) as (listener, _):
                await independent_exchange(listener.get_port(), kex=algorithm)
        async with transport_listener() as (listener, _):
            for algorithm in modern:
                await independent_exchange(listener.get_port(), kex=algorithm)
            for algorithm in legacy:
                await independent_exchange(listener.get_port(), kex=algorithm, refused=True)
            for algorithm in algorithms:
                # Group 1 and group-exchange SHA-1 require explicit enablement.
                await openssh_exchange(listener.get_port(), options=['KexAlgorithms=' + algorithm],
                    expect_success=algorithm not in ('diffie-hellman-group1-sha1',
                        'diffie-hellman-group-exchange-sha1'))
        from F07_helpers import kerberos_realm
        async with kerberos_realm(tmp_path) as realm:
            choices = ('gss-curve25519-sha256', 'gss-curve448-sha512',
                'gss-nistp256-sha256', 'gss-nistp384-sha384', 'gss-nistp521-sha512',
                'gss-1.3.132.0.10-sha256', 'gss-gex-sha1', 'gss-gex-sha256',
                'gss-group1-sha1', 'gss-group14-sha1', 'gss-group14-sha256',
                'gss-group15-sha512', 'gss-group16-sha512', 'gss-group17-sha512',
                'gss-group18-sha512')
            settings = dict(gss_host=realm['service'], gss_store={'keytab': realm['env']['KRB5_KTNAME']},
                            gss_kex=True, gss_auth=False)
            for algorithm in choices:
                async with transport_listener(kex_algs=[algorithm], **settings) as (listener, _):
                    await independent_exchange(listener.get_port(), kex=algorithm + '-toWM5Slw5Ew8Mqkay+al2g==',
                        gss_cache=realm['cache'], gss_service=realm['service'])
            async with transport_listener(**settings) as (listener, _):
                for algorithm in choices:
                    await independent_exchange(listener.get_port(), kex=algorithm + '-toWM5Slw5Ew8Mqkay+al2g==',
                        gss_cache=realm['cache'], gss_service=realm['service'],
                        refused=algorithm in ('gss-group1-sha1', 'gss-gex-sha1'))
        return 'test_software_key_exchange_with_independent_peer'
    assert run_async(scenario(), timeout=300) == 'test_software_key_exchange_with_independent_peer'


def test_encryption_with_independent_peer_and_defaults():
    async def scenario():
        modern = ('chacha20-poly1305@openssh.com', 'aes128-gcm@openssh.com',
                  'aes256-gcm@openssh.com', 'aes128-ctr', 'aes192-ctr', 'aes256-ctr')
        legacy = ('aes128-cbc', 'aes192-cbc', 'aes256-cbc', '3des-cbc')
        for algorithm in (*modern, *legacy):
            async with transport_listener(encryption_algs=[algorithm]) as (listener, _):
                await openssh_exchange(listener.get_port(), options=['Ciphers=' + algorithm])
        async with transport_listener() as (listener, _):
            for algorithm in modern:
                await openssh_exchange(listener.get_port(), options=['Ciphers=' + algorithm])
            for algorithm in legacy:
                await openssh_exchange(listener.get_port(), options=['Ciphers=' + algorithm],
                                       expect_success=False)
        for algorithm in ('blowfish-cbc', 'cast128-cbc', 'seed-cbc@ssh.com',
                          'arcfour', 'arcfour128', 'arcfour256'):
            async with transport_listener(encryption_algs=[algorithm]) as (listener, _):
                await independent_exchange(listener.get_port(), cipher=algorithm)
            async with transport_listener() as (listener, _):
                await independent_exchange(listener.get_port(), cipher=algorithm, refused=True)
        return 'test_encryption_with_independent_peer_and_defaults'
    assert run_async(scenario(), timeout=150) == 'test_encryption_with_independent_peer_and_defaults'


def test_sntrup_exchange_and_default_offers():
    async def scenario():
        negotiated = []
        for algorithm in ('sntrup761x25519-sha512', 'sntrup761x25519-sha512@openssh.com'):
            for explicit in (True, False):
                settings = {'kex_algs': [algorithm]} if explicit else {}
                async with transport_listener(**settings) as (listener, _):
                    await independent_exchange(listener.get_port(), kex=algorithm)
                async with independent_selection({'kex': [algorithm]}) as (port, observed):
                    async with velnora.connect('127.0.0.1', port,
                                                **client_options(**settings)) as conn:
                        await checked_exchange(conn, b'independent hybrid transport')
                negotiated.append(observed['kex'])
                assert observed['kex'] == algorithm
        return negotiated
    assert run_async(scenario(), timeout=90) == [
        'sntrup761x25519-sha512', 'sntrup761x25519-sha512',
        'sntrup761x25519-sha512@openssh.com', 'sntrup761x25519-sha512@openssh.com']


def test_integrity_with_independent_peer_and_defaults():
    async def scenario():
        modern = ('hmac-sha1', 'hmac-sha2-256', 'hmac-sha2-512',
                  'hmac-sha1-etm@openssh.com', 'hmac-sha2-256-etm@openssh.com',
                  'hmac-sha2-512-etm@openssh.com', 'umac-64@openssh.com',
                  'umac-128@openssh.com', 'umac-64-etm@openssh.com',
                  'umac-128-etm@openssh.com')
        legacy = ('hmac-sha1-96', 'hmac-md5', 'hmac-md5-96',
                  'hmac-sha1-96-etm@openssh.com', 'hmac-md5-etm@openssh.com',
                  'hmac-md5-96-etm@openssh.com')
        for algorithm in (*modern, *legacy):
            async with transport_listener(encryption_algs=['aes128-ctr'],
                                          mac_algs=[algorithm]) as (listener, _):
                await openssh_exchange(listener.get_port(),
                    options=['Ciphers=aes128-ctr', 'MACs=' + algorithm])
        async with transport_listener(encryption_algs=['aes128-ctr']) as (listener, _):
            for algorithm in modern:
                await openssh_exchange(listener.get_port(),
                    options=['Ciphers=aes128-ctr', 'MACs=' + algorithm])
            for algorithm in legacy:
                await openssh_exchange(listener.get_port(),
                    options=['Ciphers=aes128-ctr', 'MACs=' + algorithm], expect_success=False)
        extra_modern = ('hmac-sha224@ssh.com', 'hmac-sha384@ssh.com')
        extra_legacy = ('hmac-sha2-256-96', 'hmac-sha2-512-96',
                        'hmac-sha2-256-96-etm@openssh.com', 'hmac-sha2-512-96-etm@openssh.com')
        for algorithm in (*extra_modern, *extra_legacy):
            async with transport_listener(encryption_algs=['aes128-ctr'], mac_algs=[algorithm]) as (listener, _):
                await independent_exchange(listener.get_port(), mac=algorithm)
            async with transport_listener(encryption_algs=['aes128-ctr']) as (listener, _):
                await independent_exchange(listener.get_port(), mac=algorithm, refused=algorithm in extra_legacy)
        return 'test_integrity_with_independent_peer_and_defaults'
    assert run_async(scenario(), timeout=150) == 'test_integrity_with_independent_peer_and_defaults'


def test_compression_bidirectional_data(tmp_path):
    async def scenario():
        payload = b'compressible data\x00\xff' * 10000
        for algorithm in ('none', 'zlib', 'zlib@openssh.com'):
            async with transport_listener(compression_algs=[algorithm]) as (listener, _):
                async with velnora.connect('127.0.0.1', listener.get_port(),
                    **client_options(compression_algs=[algorithm])) as conn:
                    assert conn.get_extra_info('send_compression') == algorithm
                    assert conn.get_extra_info('recv_compression') == algorithm
                    await checked_exchange(conn, payload)
                # OpenSSH supports no compression and delayed zlib, not immediate zlib.
                if algorithm != 'zlib':
                    await openssh_exchange(listener.get_port(), payload=payload,
                        options=['Compression=' + ('no' if algorithm == 'none' else 'yes')])
        async with transport_listener() as (listener, _):
            async with velnora.connect('127.0.0.1', listener.get_port(), **client_options()) as conn:
                assert conn.get_extra_info('send_compression') == 'none'
                assert conn.get_extra_info('recv_compression') == 'none'
                await checked_exchange(conn, payload)
        class CompressionPeer(ConfigPeer):
            def connection_made(self, connection):
                self.connection = connection
            def begin_auth(self, username):
                self.connection.send_auth_banner('before authentication ' * 1000)
                return False
        for algorithm in ('none', 'zlib', 'zlib@openssh.com'):
            async with transport_listener(server_factory=CompressionPeer,
                    compression_algs=[algorithm], encryption_algs=['aes128-ctr'],
                    mac_algs=['hmac-sha2-256-etm@openssh.com']) as (listener, _):
                result = await independent_exchange(listener.get_port(), compression=algorithm,
                    mac='hmac-sha2-256-etm@openssh.com')
                banners = [row for row in result['records'] if row[1] == 53]
                assert len(banners) == 1
                if algorithm == 'zlib':
                    assert banners[0][0] < banners[0][3]
                else:
                    assert banners[0][0] >= banners[0][3]
                # Verified external decompression is also exercised in both
                # directions by the independent peer's application exchange.
        # Server defaults permit delayed compression, not compression before authentication.
        async with transport_listener() as (listener, _):
            await independent_exchange(listener.get_port(), compression='zlib@openssh.com')
            await independent_exchange(listener.get_port(), compression='zlib', refused=True)
        for enabled, expected in (('yes', 'zlib@openssh.com'), ('no', 'none')):
            path = tmp_path / 'compression-config'
            path.write_text('Compression ' + enabled + '\n')
            async with independent_selection({'compression': ['none', 'zlib', 'zlib@openssh.com']}) as (port, result):
                options = client_options()
                options['config'] = str(path)
                async with velnora.connect('127.0.0.1', port, **options) as conn:
                    await checked_exchange(conn, b'configuration compression order' * 100)
            assert result['compression'] == expected
            remaining = ['none', 'zlib'] if enabled == 'yes' else ['zlib', 'zlib@openssh.com']
            async with independent_selection({'compression': remaining}) as (port, result):
                async with velnora.connect('127.0.0.1', port, **options) as conn:
                    await checked_exchange(conn, b'configuration second compression preference' * 100)
            assert result['compression'] == ('zlib' if enabled == 'yes' else 'zlib@openssh.com')
            async with independent_selection({'compression': ['zlib']}) as (port, result):
                async with velnora.connect('127.0.0.1', port, **options) as conn:
                    await checked_exchange(conn, b'configuration remaining alternative' * 100)
            assert result['compression'] == 'zlib'
        return 'test_compression_bidirectional_data'
    assert run_async(scenario(), timeout=60) == 'test_compression_bidirectional_data'


def test_host_and_user_signatures_with_independent_peer(tmp_path):
    async def scenario():
        for key_type, signatures in (
                ('ssh-rsa', ('rsa-sha2-256', 'rsa-sha2-512', 'ssh-rsa')),
                ('ecdsa-sha2-nistp256', ('ecdsa-sha2-nistp256',)),
                ('ecdsa-sha2-nistp384', ('ecdsa-sha2-nistp384',)),
                ('ecdsa-sha2-nistp521', ('ecdsa-sha2-nistp521',)),
                ('ssh-ed25519', ('ssh-ed25519',)),
                ('ssh-dss', ('ssh-dss',))):
            key, _ = certificate_identity(key_type)
            path = tmp_path / key_type
            key.write_private_key(path)
            path.chmod(0o600)
            for signature in signatures:
                async with transport_listener(server_host_keys=[key],
                    server_factory=lambda: ConfigPeer(key=key),
                    signature_algs=[signature]) as (listener, _):
                    await openssh_exchange(listener.get_port(), options=[
                        'HostKeyAlgorithms=' + signature,
                        'PubkeyAcceptedAlgorithms=' + signature,
                        'IdentitiesOnly=yes', 'IdentityFile=' + str(path)])
        ca, _ = certificate_identity()
        key, _ = certificate_identity()
        cert = ca.generate_host_certificate(key, 'transport', principals=['127.0.0.1'])
        async with transport_listener(server_host_keys=[(key, cert)]) as (listener, _):
            await openssh_exchange(listener.get_port(),
                options=['HostKeyAlgorithms=ssh-ed25519-cert-v01@openssh.com'])
        dsa_key, _ = certificate_identity('ssh-dss')
        async with transport_listener(server_host_keys=[dsa_key]) as (listener, _):
            with pytest.raises(velnora.KeyExchangeFailed):
                await velnora.connect('127.0.0.1', listener.get_port(), **client_options())
        for key_type, signatures in (
                ('ssh-ed448', ('ssh-ed448',)),
                ('ecdsa-sha2-1.3.132.0.10', ('ecdsa-sha2-1.3.132.0.10',)),
                ('ssh-rsa', ('ssh-rsa-sha224@ssh.com', 'ssh-rsa-sha384@ssh.com',
                             'ssh-rsa-sha256@ssh.com', 'ssh-rsa-sha512@ssh.com'))):
            key, _ = certificate_identity(key_type)
            for signature in signatures:
                async with transport_listener(server_host_keys=[key],
                        server_factory=lambda: ConfigPeer(key=key),
                        signature_algs=[signature]) as (listener, _):
                    result = await independent_exchange(listener.get_port(), signature=signature,
                        user_signature=signature, private=key.export_private_key('pkcs8-pem').decode(),
                        algorithm=key_type)
                    assert result['signatures'] == [signature]
        # The independent OpenSSH client signs using an actual user certificate.
        user, _ = certificate_identity()
        authority, _ = certificate_identity()
        user_cert = authority.generate_user_certificate(user, 'transport-user', principals=['member'])
        path = tmp_path / 'certified-user'
        user.write_private_key(path)
        path.chmod(0o600)
        cert_path = tmp_path / 'certified-user.pub'
        user_cert.write_certificate(cert_path)
        authorization = velnora.import_authorized_keys('cert-authority ' + authority.export_public_key().decode())
        async with transport_listener(server_factory=velnora.SSHServer,
                authorized_client_keys=authorization) as (listener, _):
            await openssh_exchange(listener.get_port(), options=[
                'IdentityFile=' + str(path), 'CertificateFile=' + str(cert_path),
                'IdentityAgent=none', 'IdentitiesOnly=yes', 'PreferredAuthentications=publickey'])
        host, _ = certificate_identity('ssh-rsa')
        user, _ = certificate_identity('ssh-rsa')
        host_cert = host.generate_x509_host_certificate(host, 'CN=Transport host', principals=['127.0.0.1'])
        user_cert = user.generate_x509_user_certificate(user, 'CN=Transport user', principals=['member'])
        authorization = velnora.import_authorized_keys(user_cert.export_certificate('openssh').decode())
        async with transport_listener(server_factory=velnora.SSHServer,
                server_host_keys=[(host, host_cert)], authorized_client_keys=authorization) as (listener, _):
            import base64
            # RFC 6187 chain framing comes from independently parsed DER bytes.
            from F01_helpers import ssh_string
            cert_blob = (ssh_string('x509v3-rsa2048-sha256') + struct.pack('>I', 1) +
                         ssh_string(user_cert.export_certificate('der')) + struct.pack('>I', 0))
            result = await independent_exchange(listener.get_port(), signature='x509v3-rsa2048-sha256',
                user_signature='x509v3-rsa2048-sha256', algorithm='ssh-rsa',
                private=user.export_private_key('pkcs8-pem').decode(),
                certificate=base64.b64encode(cert_blob).decode())
            assert result['signatures'] == ['rsa2048-sha256']
        return 'test_host_and_user_signatures_with_independent_peer'
    assert run_async(scenario(), timeout=100) == 'test_host_and_user_signatures_with_independent_peer'


def test_host_key_discovery_without_application_session():
    async def scenario():
        authenticated, sessions = [], []

        class DiscoveryPeer(ConfigPeer):
            def begin_auth(self, username):
                authenticated.append(username)
                return False

        async def application(process):
            sessions.append(process.command)
            await echo_session(process)

        key, external = certificate_identity()
        async with transport_listener(server_host_keys=[key],
                server_factory=DiscoveryPeer, process_factory=application) as (listener, _):
            discovered = await bounded(velnora.get_server_host_key(
                '127.0.0.1', listener.get_port(), config=None))
            assert identity(read_public(discovered.export_public_key(), 'openssh',
                                        'ssh-ed25519')) == identity(external)
            assert authenticated == []
            assert sessions == []
            await openssh_exchange(listener.get_port())
            assert authenticated == ['member']
            assert sessions == ['receive']
        return 'test_host_key_discovery_without_application_session'
    assert run_async(scenario()) == 'test_host_key_discovery_without_application_session'


def test_host_key_update_categories():
    async def scenario():
        retained, _ = certificate_identity()
        added, _ = certificate_identity('ecdsa-sha2-nistp256')
        removed, _ = certificate_identity()
        revoked, _ = certificate_identity('ssh-rsa')
        observed = asyncio.get_running_loop().create_future()

        def observer(*groups):
            observed.set_result(groups)

        async with transport_listener(server_host_keys=[retained, added, revoked],
                                      send_server_host_keys=True) as (listener, _):
            options = client_options(server_host_keys_handler=observer)
            options['known_hosts'] = ([retained.convert_to_public(), removed.convert_to_public()],
                                     [], [revoked.convert_to_public()])
            async with velnora.connect('127.0.0.1', listener.get_port(), **options) as conn:
                groups = await bounded(observed)
                assert [set(group) for group in groups] == [
                    {added.convert_to_public()}, {removed.convert_to_public()},
                    {retained.convert_to_public()}, {revoked.convert_to_public()}]
                await checked_exchange(conn)
        # Both peers send the same key claim; only possession proof differs.
        retained, _ = certificate_identity('ssh-rsa')
        added, _ = certificate_identity('ssh-rsa')
        for invalid in (False, True):
            observed = []
            async with independent_hostkeys(retained, added, invalid) as port:
                settings = client_options(server_host_keys_handler=lambda *groups: observed.append(groups))
                settings['known_hosts'] = ([retained.convert_to_public()], [], [])
                async with velnora.connect('127.0.0.1', port, **settings) as conn:
                    await checked_exchange(conn, b'proof must bind the newly offered private key')
                    # A protocol round trip drains prior global request responses.
                    await checked_exchange(conn, b'second round trip')
                    if invalid:
                        assert not observed or all(not groups[0] for groups in observed)
                    else:
                        assert len(observed) == 1
                        assert set(observed[0][0]) == {added.convert_to_public()}
        return 'test_host_key_update_categories'
    assert run_async(scenario(), timeout=50) == 'test_host_key_update_categories'


def test_independent_connection_and_owned_resource_closure():
    async def scenario():
        async with transport_listener() as (listener, _):
            async with velnora.connect('127.0.0.1', listener.get_port(), **client_options()) as survivor:
                await checked_exchange(survivor)
                for action in ('close', 'abort', 'disconnect'):
                    conn = await velnora.connect('127.0.0.1', listener.get_port(), **client_options())
                    try:
                        await checked_exchange(conn)
                        channel = await conn.create_process('receive', encoding=None)
                        remote = await conn.forward_remote_port('127.0.0.1', 0,
                                                                 '127.0.0.1', listener.get_port())
                        port = remote.get_port()
                        # A real forwarding path exists before closure.
                        reader, writer = await asyncio.open_connection('127.0.0.1', port)
                        assert (await bounded(reader.readline())).startswith(b'SSH-2.0-')
                        writer.close()
                        await writer.wait_closed()
                        if action == 'disconnect':
                            conn.disconnect(velnora.DISC_BY_APPLICATION, 'Application complete')
                        else:
                            getattr(conn, action)()
                        await bounded(conn.wait_closed())
                        await bounded(channel.wait_closed())
                        await bounded(remote.wait_closed())
                        assert conn.is_closed()
                        try:
                            reader, writer = await asyncio.open_connection('127.0.0.1', port)
                        except (ConnectionRefusedError, ConnectionResetError):
                            pass
                        else:
                            try:
                                assert await bounded(reader.read(1)) == b''
                            finally:
                                writer.close()
                                await writer.wait_closed()
                        await checked_exchange(survivor, action.encode())
                    finally:
                        conn.close()
                        await bounded(conn.wait_closed())
        peers = []
        class AbruptPeer(ConfigPeer):
            def connection_made(self, connection):
                peers.append(connection)
        async def incomplete(process):
            process.stdout.write(b'ready')
            await process.stdout.drain()
            await process.stdin.read()
        async with transport_listener(server_factory=AbruptPeer,
                process_factory=incomplete) as (listener, _):
            async with velnora.connect('127.0.0.1', listener.get_port(), **client_options()) as conn:
                process = await conn.create_process('pending', encoding=None)
                assert await bounded(process.stdout.readexactly(5)) == b'ready'
                pending = asyncio.create_task(process.stdout.readexactly(17))
                await asyncio.sleep(0)
                assert not pending.done()
                peers[-1].abort()
                with pytest.raises(velnora.ConnectionLost):
                    await bounded(pending)
                await bounded(conn.wait_closed())
        return 'test_independent_connection_and_owned_resource_closure'
    assert run_async(scenario(), timeout=30) == 'test_independent_connection_and_owned_resource_closure'


def test_establishment_deadline_and_invalid_settings():
    async def scenario():
        # Fill a real Linux accept queue. Further TCP handshakes remain pending;
        # no routing assumptions, packet filters or privileged fixtures are used.
        with socket.socket() as queued, socket.socket() as occupied, socket.socket() as probe:
            queued.bind(('127.0.0.1', 0))
            queued.listen(0)
            address = queued.getsockname()
            occupied.setblocking(False)
            probe.setblocking(False)
            loop = asyncio.get_running_loop()
            await bounded(loop.sock_connect(occupied, address))
            pending = asyncio.create_task(loop.sock_connect(probe, address))
            try:
                done, _ = await asyncio.wait([pending], timeout=0.2)
                assert not done, 'TCP establishment did not stall on the full accept queue'
                await expect_connection_timeout(velnora.connect(*address,
                    **client_options(connect_timeout=0.15)))
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
        finished = []

        async def silent_peer(reader, writer):
            done = asyncio.get_running_loop().create_future()
            finished.append(done)
            try:
                await reader.read()
            finally:
                writer.close()
                await writer.wait_closed()
                done.set_result(True)

        async with tcp_server(silent_peer, host='127.0.0.1') as listener:
            port = listener.sockets[0].getsockname()[1]
            await expect_connection_timeout(velnora.connect('127.0.0.1', port,
                **client_options(connect_timeout=0.15)))
        for done in finished:
            await bounded(done)
        # Real authentication is delayed independently of the transport.
        gate = asyncio.Event()

        class DelayedPeer(ConfigPeer):
            async def begin_auth(self, username):
                await gate.wait()
                return False

        async with transport_listener(server_factory=DelayedPeer) as (listener, _):
            await expect_connection_timeout(velnora.connect('127.0.0.1', listener.get_port(),
                **client_options(connect_timeout=0.15)))
            for timeout in (0, None):
                gate.clear()
                pending = asyncio.ensure_future(velnora.connect(
                    '127.0.0.1', listener.get_port(), **client_options(connect_timeout=timeout)))
                try:
                    await asyncio.sleep(0.3)
                    assert not pending.done()
                    gate.set()
                    async with opened_connection(bounded(pending)) as conn:
                        await checked_exchange(conn)
                finally:
                    if not pending.done():
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
            with pytest.raises(ValueError):
                await velnora.connect('127.0.0.1', listener.get_port(),
                                       **client_options(connect_timeout=-1))
        return 'test_establishment_deadline_and_invalid_settings'
    assert run_async(scenario(), timeout=15) == 'test_establishment_deadline_and_invalid_settings'


def test_rekey_limits_and_data_survival():
    # Each call owns setup, observation and cleanup on a fresh event loop.
    # Reserve covers local key/listener setup, scheduling and resource closure.
    reserve = 10
    openssh_budget = 20 + reserve  # Includes the 1.2-second EOF delay.
    exchange_budget = 30 + reserve  # Includes the peer's 1.2-second observation.
    client_budget = 15 + 10 + 1.3 + 10 + 20 + reserve
    # Client: readiness + connect/session + observation + communicate + peer exit.
    policy_budget = 10 + reserve

    async def openssh_measurement(option):
        async with transport_listener(**option) as (listener, _):
            # OpenSSH validates renewed exchange and then decrypts channel data.
            _, log = await openssh_exchange(listener.get_port(),
                payload=b'rekey traffic\x00\xff' * 20000, delay_before_eof=1.2,
                options=['KexAlgorithms=curve25519-sha256'])
            if option != {'rekey_seconds': 0}:
                assert log.count(b'SSH2_MSG_NEWKEYS received') >= 2, log
            else:
                assert log.count(b'SSH2_MSG_NEWKEYS received') == 1, log

    async def traffic_measurement():
        async with transport_listener(process_factory=volume_session,
                rekey_bytes=65536, rekey_seconds=0,
                encryption_algs=['aes128-ctr'], mac_algs=['hmac-sha2-256-etm@openssh.com']) as (listener, _):
            result = await independent_exchange(listener.get_port(), measure='bytes',
                mac='hmac-sha2-256-etm@openssh.com')
            assert_rekey_boundary(result, 65536)

    async def server_time_measurement(seconds):
        async with transport_listener(process_factory=volume_session,
                rekey_seconds=seconds, encryption_algs=['aes128-ctr'],
                mac_algs=['hmac-sha2-256-etm@openssh.com']) as (listener, _):
            result = await independent_exchange(listener.get_port(), measure='time',
                mac='hmac-sha2-256-etm@openssh.com')
            times = [row[2] for row in result['records'] if row[1] == 20]
            if seconds:
                assert len(times) >= 2 and times[1] - times[0] >= 0.95, times
            else:
                assert len(times) == 1, times

    # The client role renews keys after its selected interval as well.
    async def client_time_measurement(seconds):
        async with independent_selection({'ciphers': ['aes128-ctr'], 'digests': ['hmac-sha2-256']}) as (port, observed):
            async with velnora.connect('127.0.0.1', port,
                    **client_options(rekey_seconds=seconds)) as conn:
                process = await conn.create_process('receive', encoding=None)
                process.stdin.write(b'before interval')
                await asyncio.sleep(1.3)
                process.stdin.write(b' after interval')
                process.stdin.write_eof()
                output, _ = await bounded(process.communicate())
                assert output == b'received:before interval after interval'
        starts = [row[2] for row in observed['records'] if row[1] == 20]
        # A loaded host may legitimately pass a further interval, so only a
        # lower bound on renewals is judged; the first gap shows the interval.
        if seconds:
            assert len(starts) >= 2 and starts[1] - starts[0] >= 0.95, starts
        else:
            assert len(starts) == 1, starts

    async def invalid_server_setting(invalid):
        with pytest.raises(ValueError):
            async with transport_listener(**invalid):
                pytest.fail('Invalid server setting was accepted')

    async def invalid_client_setting(option):
        async with transport_listener() as (listener, _):
            with pytest.raises(ValueError):
                await velnora.connect('127.0.0.1', listener.get_port(),
                                       **client_options(**option))

    async def established_keepalive_policy():
        async with transport_listener() as (listener, _):
            async with velnora.connect('127.0.0.1', listener.get_port(), **client_options()) as conn:
                for option in ({'interval': -1}, {'count_max': -1}):
                    with pytest.raises(ValueError):
                        conn.set_keepalive(**option)
                conn.set_keepalive(interval=0)
                await checked_exchange(conn)

    for option in ({'rekey_bytes': 65536}, {'rekey_seconds': 1},
                   {'rekey_seconds': 0}):
        run_async(openssh_measurement(option), timeout=openssh_budget)
    run_async(traffic_measurement(), timeout=exchange_budget)
    for seconds in (1, 0):
        run_async(server_time_measurement(seconds), timeout=exchange_budget)
    for seconds in (1, 0):
        run_async(client_time_measurement(seconds), timeout=client_budget)
    for option in ({'rekey_bytes': 0}, {'rekey_bytes': -1}, {'rekey_seconds': -1},
                   {'keepalive_interval': -1}, {'keepalive_count_max': -1},
                   {'keepalive_count_max': 0}):
        run_async(invalid_server_setting(option), timeout=policy_budget)
    for option in ({'rekey_bytes': 0}, {'rekey_bytes': -1}, {'rekey_seconds': -1},
                   {'keepalive_interval': -1}, {'keepalive_count_max': -1},
                   {'keepalive_count_max': 0}):
        run_async(invalid_client_setting(option), timeout=policy_budget)
    # These checks share connection state: rejected updates must still allow
    # disabling keepalive and exchanging data on that same connection.
    run_async(established_keepalive_policy(), timeout=10 + policy_budget)


def test_keepalive_responsive_peers(tmp_path):
    async def scenario():
        for side in ('client', 'server'):
            server_options = {'keepalive_interval': 1, 'keepalive_count_max': 3} if side == 'server' else {}
            client_settings = {'keepalive_interval': 1, 'keepalive_count_max': 3} if side == 'client' else {}
            async with transport_listener(**server_options) as (listener, _):
                async with velnora.connect('127.0.0.1', listener.get_port(),
                                           **client_options(**client_settings)) as conn:
                    await checked_exchange(conn)
                    await asyncio.sleep(3.2)
                    await checked_exchange(conn, b'alive after multiple keepalive periods')
        # Drop real replies while an independent server records received requests.
        async with openssh_daemon(tmp_path / 'keepalive') as (port, key, _, service):
            for settings, allowance in (({}, 0), ({'keepalive_interval': 0.05}, 3),
                    ({'keepalive_interval': 0.05, 'keepalive_count_max': 1}, 1)):
                before = service.output()[1].count(b'rtype keepalive@openssh.com want_reply 1')
                async with wire_proxy(port) as (proxy_port, state):
                    closed = asyncio.get_running_loop().create_future()
                    async with opened_connection(daemon_connect(proxy_port, key,
                            client_factory=lambda: ClientClosure(closed))) as conn:
                        baseline = await bounded(conn.run('printf ready'))
                        assert baseline.stdout == 'ready'
                        state['drop_server'] = True
                        if settings:
                            conn.set_keepalive(interval=1,
                                **({'count_max': settings['keepalive_count_max']}
                                   if 'keepalive_count_max' in settings else {}))
                            await bounded(conn.wait_closed(), timeout=10)
                            assert isinstance(await bounded(closed), velnora.ConnectionLost)
                        else:
                            await asyncio.sleep(0.3)
                            assert not conn.is_closed()
                            state['drop_server'] = False
                            resumed = await bounded(conn.run('printf resumed'))
                            assert resumed.stdout == 'resumed'
                after = service.output()[1].count(b'rtype keepalive@openssh.com want_reply 1')
                assert after - before == allowance
        # The server role applies the same policy to a silent independent client.
        authenticated = asyncio.get_running_loop().create_future()
        closed = asyncio.get_running_loop().create_future()
        class ObservedClosure(ServerClosure):
            def connection_made(self, connection):
                self.connection = connection
        policy = ObservedClosure(authenticated, closed)
        async with transport_listener(server_factory=lambda: policy) as (listener, _):
            async with wire_proxy(listener.get_port()) as (port, state):
                exchange = asyncio.create_task(openssh_exchange(port,
                    delay_before_eof=10, expect_success=False))
                try:
                    await bounded(authenticated)
                    state['drop_client'] = True
                    policy.connection.set_keepalive(interval=1)
                    assert isinstance(await bounded(closed, timeout=10), velnora.ConnectionLost)
                    _, log = await bounded(exchange)
                    assert log.count(b'rtype keepalive@openssh.com want_reply 1') == 3, log
                finally:
                    if not exchange.done():
                        exchange.cancel()
                        await asyncio.gather(exchange, return_exceptions=True)
        async with transport_listener() as (listener, _):
            closed = asyncio.get_running_loop().create_future()
            async with velnora.connect('127.0.0.1', listener.get_port(),
                    **client_options(client_factory=lambda: ClientClosure(closed))) as conn:
                await checked_exchange(conn, b'working before zero allowance')
                conn.set_keepalive(interval=0.05, count_max=0)
                await bounded(conn.wait_closed(), timeout=3)
                assert isinstance(await bounded(closed), velnora.ConnectionLost)
        return 'test_keepalive_responsive_peers'
    assert run_async(scenario(), timeout=60) == 'test_keepalive_responsive_peers'


def test_connection_quantity_settings():
    async def scenario():
        async with transport_listener() as (listener, _):
            # Each unit goes through connection setup, not a standalone converter.
            for quantity in ('1s', '1m', '1h', '1d', '1w', '1w2d3h4m5s', '1'):
                async with velnora.connect('127.0.0.1', listener.get_port(),
                    **client_options(connect_timeout=quantity, rekey_seconds=quantity,
                                     keepalive_interval=quantity)) as conn:
                    await checked_exchange(conn, quantity.encode())
            for quantity in ('4096', '4k', '1m', '1g'):
                async with velnora.connect('127.0.0.1', listener.get_port(),
                    **client_options(rekey_bytes=quantity)) as conn:
                    await checked_exchange(conn, quantity.encode())
            # Equal caller-selected intervals expressed in every unit must have
            # the same externally observed timeout effect, with scheduling reserve.
            finished = []
            async def silent(reader, writer):
                done = asyncio.get_running_loop().create_future()
                finished.append(done)
                try:
                    await reader.read()
                finally:
                    writer.close()
                    await writer.wait_closed()
                    done.set_result(True)
            async with tcp_server(silent, host='127.0.0.1') as stalled:
                port = stalled.sockets[0].getsockname()[1]
                for quantity in ('0.12', '0.12s', '0.002m',
                                 '0.00003333333333333333h',
                                 '0.000001388888888888889d',
                                 '0.0000001984126984126984w', '0.001m0.06s'):
                    start = time.monotonic()
                    await expect_connection_timeout(velnora.connect('127.0.0.1', port,
                        **client_options(connect_timeout=quantity)))
                    assert time.monotonic() - start >= 0.06
            for done in finished:
                await bounded(done)
            for name, quantities in (
                    ('connect_timeout', ('1fortnight', '1s trailing', '--1')),
                    ('rekey_seconds', ('1x', '1h?')),
                    ('keepalive_interval', ('1x', '1s!')),
                    ('rekey_bytes', ('1t', '1.2.3k', '4k garbage', ''))):
                for quantity in quantities:
                    with pytest.raises(ValueError):
                        await velnora.connect('127.0.0.1', listener.get_port(),
                            **client_options(**{name: quantity}))
        for quantity in ('65536', '64k', '0.0625m', '0.00006103515625g'):
            async with transport_listener(process_factory=volume_session,
                    rekey_bytes=quantity, rekey_seconds=0, encryption_algs=['aes128-ctr'],
                    mac_algs=['hmac-sha2-256-etm@openssh.com']) as (server, _):
                result = await independent_exchange(server.get_port(), measure='bytes',
                    mac='hmac-sha2-256-etm@openssh.com')
                assert_rekey_boundary(result, 65536)
        return 'test_connection_quantity_settings'
    assert run_async(scenario(), timeout=60) == 'test_connection_quantity_settings'


def test_default_rekey_traffic_boundary():
    async def measure(mode):
        # The product's traffic and time rekey settings are both omitted.
        async with transport_listener(process_factory=volume_session,
                encryption_algs=['aes128-ctr'],
                mac_algs=['hmac-sha2-256-etm@openssh.com']) as (listener, _):
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(Path(__file__).with_name('F06_helpers.py')),
                str(listener.get_port()), mode, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            try:
                out, err = await bounded(proc.communicate(), timeout=3690)
            finally:
                if proc.returncode is None:
                    proc.kill()
                    await bounded(proc.communicate())
            assert proc.returncode == 0, err.decode(errors='replace')
            result = json.loads(out)
        records, order = result['records'], result['order']
        exchanges = [i for i, (_, kind) in enumerate(records) if kind == 20]
        assert len(exchanges) == 2, exchanges
        assert sum(kind == 21 for _, kind in records) == 2
        if mode == 'time':
            times = [stamp for stamp, kind in result['times'] if kind == 20]
            assert times[1] - times[0] >= 3599, times
            return
        first_end = next(i for i, (_, kind) in enumerate(records) if kind == 21)
        start = first_end + 1
        if records[start][1] == 7:
            start += 1
        lengths = [length for length, _ in records[start:exchanges[1]]]
        threshold = 1024 ** 3
        assert sum(lengths[:-1]) < threshold <= sum(lengths), sum(lengths)
        # The independent peer must respond to, rather than initiate, rekey.
        exchange_order = [direction for direction, kind in order if kind == 20]
        assert exchange_order == ['send', 'receive', 'receive', 'send']
    async def scenario():
        await measure('bytes')
        await measure('time')
        return 'test_default_rekey_traffic_boundary'
    assert run_async(scenario(), timeout=3750) == 'test_default_rekey_traffic_boundary'
