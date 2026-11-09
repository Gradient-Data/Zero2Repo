# feature: F04
"""Acceptance observations for OpenSSH connection configuration."""
import asyncio
import getpass
import os
import socket
import sys

import velnora
import pytest

from _helpers import bounded, run_async, tcp_server
from F02_helpers import certificate_identity
from F03_helpers import authorized_line, host_line
from F04_helpers import (ConfigPeer, config_file, config_listener,
                         configured_report, report_session, session_report, configuration_agent)


def test_precedence_and_accumulation(tmp_path, monkeypatch):
    """F04.T01: defaults, explicit choices, first lists, accumulated identities."""
    async def scenario():
        keys = [certificate_identity()[0] for _ in range(2)]
        paths = [tmp_path / ('identity-' + str(i)) for i in range(2)]
        for key, path in zip(keys, paths):
            key.write_private_key(path)
        monkeypatch.setenv('F04_ENV_ONE', 'first-value')
        monkeypatch.setenv('F04_ENV_TWO', 'second-value')
        async with config_listener(key=keys[0]) as (listener, _):
            path = config_file(tmp_path, f'''
# Unknown directives must not prevent application of later settings.
FutureExtension arbitrary words
Hostname 127.0.0.1
Port {listener.get_port()}
Port 1
User initial
User ignored
IdentityFile {paths[0]}
IdentityFile {paths[1]}
SendEnv F04_ENV_ONE
SendEnv F04_ENV_TWO
SetEnv SETTING=first
SetEnv SETTING=ignored OTHER=ignored
RemoteCommand first-command
RemoteCommand ignored-command
''')
            for key in keys:
                async with config_listener(key=key) as (target, _):
                    result = await configured_report(path, port=target.get_port())
                    assert result == {'username': 'initial', 'command': 'first-command',
                                      'terminal': None, 'environment': {
                                          'F04_ENV_ONE': 'first-value',
                                          'F04_ENV_TWO': 'second-value', 'SETTING': 'first'}}
            result = await configured_report(path, username='explicit',
                                             command='explicit-command',
                                             env={'SETTING': 'explicit'})
            assert result['username'] == 'explicit'
            assert result['command'] == 'explicit-command'
            assert result['environment']['SETTING'] == 'explicit'
        issuers = [certificate_identity()[0] for _ in keys]
        cert_paths = [tmp_path / ('certificate-' + str(i)) for i in range(2)]
        for issuer, key, cert_path in zip(issuers, keys, cert_paths):
            issuer.generate_user_certificate(key, 'configuration', principals=['initial']).write_certificate(cert_path)
        # Each CA-only server requires a different member of both accumulated lists.
        for issuer in issuers:
            authorization = velnora.import_authorized_keys(authorized_line(issuer, 'cert-authority'))
            async with velnora.listen('127.0.0.1', 0, config=None,
                    server_host_keys=[certificate_identity()[0]],
                    authorized_client_keys=authorization, process_factory=report_session) as server:
                path = config_file(tmp_path, f'Hostname 127.0.0.1\nPort {server.get_port()}\nUser initial\nIdentityFile {paths[0]}\nIdentityFile {paths[1]}\nCertificateFile {cert_paths[0]}\nCertificateFile {cert_paths[1]}\n')
                assert (await configured_report(path))['username'] == 'initial'
        return 'test_precedence_and_accumulation'
    assert run_async(scenario(), timeout=30) == 'test_precedence_and_accumulation'


def test_client_address_identity_authentication(tmp_path):
    """F04.T02: real endpoint, trust alias, key and password choices."""
    async def scenario():
        key, _ = certificate_identity()
        private = tmp_path / 'client-key'
        key.write_private_key(private)
        async with config_listener(key=key, password='credential') as (listener, host):
            trust = tmp_path / 'known_hosts'
            trust.write_text(host_line('trusted-alias', host))
            base = f'''AddressFamily inet
BindAddress 127.0.0.2
Hostname 127.0.0.1
Port {listener.get_port()}
User configured-user
HostKeyAlias trusted-alias
UserKnownHostsFile {trust}
GlobalKnownHostsFile none
IdentityFile {private}
IdentityAgent none
GSSAPIAuthentication no
HostbasedAuthentication no
TCPKeepAlive no
KbdInteractiveAuthentication no
'''
            path = config_file(tmp_path, base + 'PreferredAuthentications publickey\nPasswordAuthentication no\n')
            async with velnora.connect('unresolvable.invalid', config=path) as conn:
                assert conn.get_extra_info('sockname')[0] == '127.0.0.2'
                assert conn.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) == 0
                assert conn.get_server_host_key() == host.convert_to_public()
                assert (await session_report(conn))['username'] == 'configured-user'
            path = config_file(tmp_path, base.replace('TCPKeepAlive no', 'TCPKeepAlive yes') +
                               'PreferredAuthentications publickey\n')
            async with velnora.connect('unresolvable.invalid', config=path) as conn:
                assert conn.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) != 0
            # The listener is IPv4-only, so an IPv6-only family cannot reach it by name.
            path = config_file(tmp_path, base.replace('AddressFamily inet', 'AddressFamily inet6')
                               .replace('BindAddress 127.0.0.2\n', '')
                               .replace('Hostname 127.0.0.1', 'Hostname localhost'))
            with pytest.raises(OSError):
                async with velnora.connect('unresolvable.invalid', config=path):
                    pytest.fail('The configured address family was ignored')
            # A disabled public-key method cannot use the otherwise valid identity.
            path = config_file(tmp_path, base + 'PubkeyAuthentication no\nPasswordAuthentication no\n')
            with pytest.raises(velnora.PermissionDenied):
                async with velnora.connect('unresolvable.invalid', config=path, password='credential'):
                    pytest.fail('Disabled authentication unexpectedly succeeded')
            path = config_file(tmp_path, base + 'PubkeyAuthentication no\nPreferredAuthentications password\nPasswordAuthentication yes\n')
            async with velnora.connect('unresolvable.invalid', config=path,
                                         password='credential') as conn:
                assert (await session_report(conn))['username'] == 'configured-user'
            trust.write_text(host_line('trusted-alias', certificate_identity()[0]))
            with pytest.raises(velnora.HostKeyNotVerifiable):
                async with velnora.connect('unresolvable.invalid', config=path,
                                             password='credential'):
                    pytest.fail('An untrusted host was accepted')
        selected = []
        class AuthObserver(ConfigPeer):
            def validate_public_key(self, username, public_key):
                selected.append('publickey')
                return super().validate_public_key(username, public_key)
            def validate_password(self, username, password):
                selected.append('password')
                return super().validate_password(username, password)
        async with velnora.listen('127.0.0.1', 0, config=None,
                server_factory=lambda: AuthObserver(key, 'credential'),
                server_host_keys=[host], process_factory=report_session) as server:
            for preference in ('publickey,password', 'password,publickey'):
                selected.clear()
                path = config_file(tmp_path, f'Hostname 127.0.0.1\nPort {server.get_port()}\nIdentityFile {private}\nPreferredAuthentications {preference}\n')
                async with velnora.connect('target', config=path, known_hosts=None,
                        agent_path=None, password='credential') as conn:
                    assert (await session_report(conn, command='preference'))['command'] == 'preference'
                    assert selected and set(selected) == {preference.split(',')[0]}
        # Authenticate using only keys held by an independently running agent.
        agent_keys = [certificate_identity()[0] for _ in range(2)]
        public_paths = [tmp_path / ('agent-public-' + str(i)) for i in range(2)]
        for key, public_path in zip(agent_keys, public_paths):
            key.write_public_key(public_path)
        async with configuration_agent(tmp_path, agent_keys) as agent:
            async with config_listener(key=agent_keys[1]) as (server, _):
                for identity, allowed in [(public_paths[1], True), (public_paths[0], False)]:
                    path = config_file(tmp_path, f'Hostname 127.0.0.1\nPort {server.get_port()}\nIdentityAgent {agent}\nIdentityFile {identity}\nIdentitiesOnly yes\n')
                    if allowed:
                        async with velnora.connect('target', config=path, known_hosts=None) as conn:
                            assert (await session_report(conn, command='agent-auth'))['command'] == 'agent-auth'
                    else:
                        with pytest.raises(velnora.PermissionDenied):
                            async with velnora.connect('target', config=path, known_hosts=None):
                                pytest.fail('Agent identity filter was ignored')
        host_identity, _ = certificate_identity()
        class HostPolicy(ConfigPeer):
            def begin_auth(self, username):
                return True
            def host_based_auth_supported(self):
                return True
            def validate_host_public_key(self, name, address, port, key):
                return key == host_identity.convert_to_public()
            def validate_host_based_user(self, username, name, local_user):
                return username == 'member' and local_user == 'origin-user'
        async with velnora.listen('127.0.0.1', 0, config=None,
                server_host_keys=[certificate_identity()[0]], process_factory=report_session,
                host_based_auth=True, trust_client_host=True, server_factory=HostPolicy) as listener:
            for enabled in ('yes', 'no'):
                path = config_file(tmp_path, 'HostbasedAuthentication ' + enabled +
                    '\nEnableSSHKeysign no\nPreferredAuthentications hostbased\n')
                options = dict(config=path, known_hosts=None, agent_path=None,
                    username='member', client_host_keys=[host_identity], client_username='origin-user')
                if enabled == 'yes':
                    async with velnora.connect('127.0.0.1', listener.get_port(), **options) as conn:
                        assert (await session_report(conn))['username'] == 'member'
                else:
                    with pytest.raises(velnora.PermissionDenied):
                        async with velnora.connect('127.0.0.1', listener.get_port(), **options):
                            pytest.fail('Disabled host-based authentication was used')
        from F06_helpers import independent_selection, checked_exchange
        signing_key, _ = certificate_identity('ssh-rsa')
        for algorithm in ('rsa-sha2-256', 'rsa-sha2-512'):
            path = config_file(tmp_path, 'CASignatureAlgorithms ' + algorithm + '\n')
            async with independent_selection({'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512']}) as (port, result):
                async with velnora.connect('127.0.0.1', port, config=path, known_hosts=None,
                        agent_path=None, client_keys=[signing_key]) as conn:
                    await checked_exchange(conn, algorithm.encode())
            assert result['pubkeys'] == algorithm
        from F07_helpers import kerberos_realm
        from F06_helpers import openssh_daemon
        import shlex
        realm_dir = tmp_path / 'realm'
        realm_dir.mkdir()
        async with kerberos_realm(realm_dir) as realm:
            command = ('if test -n "$KRB5CCNAME"; then KRB5_CONFIG=' +
                shlex.quote(realm['env']['KRB5_CONFIG']) + ' ' +
                shlex.quote(str(realm['tools'] / 'usr/bin/kvno')) + ' ' +
                shlex.quote(realm['service']) +
                ' >/dev/null && printf delegated; else printf none; fi')
            async with openssh_daemon(tmp_path / 'gss-config',
                    extra='GSSAPIAuthentication yes\nGSSAPIStrictAcceptorCheck no\n') as (port, _, _, _):
                for delegate, expected in [('yes', 'delegated'), ('no', 'none')]:
                    path = config_file(tmp_path, 'GSSAPIAuthentication yes\nGSSAPIKeyExchange no\n'
                        'GSSAPIDelegateCredentials ' + delegate + '\nPreferredAuthentications gssapi-with-mic\n')
                    async with velnora.connect('127.0.0.1', port, config=path, known_hosts=None,
                            agent_path=None, username=getpass.getuser(), gss_host=realm['service'],
                            gss_store={'ccache': realm['cache']}) as conn:
                        result = await bounded(conn.run(command))
                        assert result.exit_status == 0, result.stderr
                        assert result.stdout == expected
                path = config_file(tmp_path, 'GSSAPIAuthentication no\nPreferredAuthentications gssapi-with-mic\n')
                with pytest.raises(velnora.PermissionDenied):
                    async with velnora.connect('127.0.0.1', port, config=path, known_hosts=None,
                            agent_path=None, username=getpass.getuser(), gss_host=realm['service'],
                            gss_store={'ccache': realm['cache']}):
                        pytest.fail('Disabled GSSAPI authentication granted access')
        return 'test_client_address_identity_authentication'
    assert run_async(scenario(), timeout=90) == 'test_client_address_identity_authentication'


def test_client_session_negotiation_and_jump(tmp_path):
    """F04.T03: negotiated transport, terminal policy and an actual jump route."""
    async def scenario():
        async with config_listener() as (target, _):
            path = config_file(tmp_path, f'''Hostname 127.0.0.1
Port {target.get_port()}
Ciphers aes128-ctr
MACs hmac-sha2-256
KexAlgorithms curve25519-sha256
HostKeyAlgorithms ssh-ed25519
Compression yes
RemoteCommand configured-command
RequestTTY force
SetEnv MODE=configured
''')
            async with velnora.connect('target', config=path, known_hosts=None,
                                         agent_path=None, term_type='xterm') as conn:
                assert conn.get_extra_info('send_cipher') == 'aes128-ctr'
                assert conn.get_extra_info('recv_cipher') == 'aes128-ctr'
                assert conn.get_extra_info('send_mac') == 'hmac-sha2-256'
                assert conn.get_extra_info('send_compression') == 'zlib@openssh.com'
                result = await session_report(conn)
                assert result == {'username': getpass.getuser(), 'command': 'configured-command',
                                  'terminal': 'xterm', 'environment': {'MODE': 'configured'}}
            for mode, command, expected in [('no', 'exec', None), ('auto', 'exec', None),
                                             ('auto', None, 'xterm'), ('yes', 'exec', 'xterm')]:
                path = config_file(tmp_path, f'Hostname 127.0.0.1\nPort {target.get_port()}\nRequestTTY {mode}\n')
                async with velnora.connect('target', config=path, known_hosts=None,
                                             agent_path=None, term_type='xterm') as conn:
                    assert (await session_report(conn, command=command))['terminal'] == expected
            path = config_file(tmp_path, f'Hostname 127.0.0.1\nPort {target.get_port()}\nHostKeyAlgorithms ecdsa-sha2-nistp256\n')
            with pytest.raises(velnora.KeyExchangeFailed):
                await velnora.connect('target', config=path, known_hosts=None, agent_path=None)
            forwarded = []
            class Jump(ConfigPeer):
                def connection_requested(self, host, port, orig_host, orig_port):
                    forwarded.append((host, port))
                    return True
            async with velnora.listen('127.0.0.1', 0, config=None,
                    server_factory=Jump, server_host_keys=[certificate_identity()[0]]) as jump:
                # Match all also applies trust policy to the public jump connection.
                path = config_file(tmp_path, f'''Host target
Hostname 127.0.0.1
Port {target.get_port()}
ProxyJump jumper@127.0.0.1:{jump.get_port()}
RemoteCommand through-jump
Host *
UserKnownHostsFile none
GlobalKnownHostsFile none
''')
                async with velnora.connect('target', config=path, known_hosts=None,
                                             agent_path=None) as conn:
                    assert (await session_report(conn))['command'] == 'through-jump'
                assert forwarded == [('127.0.0.1', target.get_port())]
        # A reachable TCP endpoint which never starts SSH exercises the configured
        # negotiation deadline, not a failed connect to a guessed closed port.
        accepted = []
        def stall(reader, writer):
            accepted.append(writer)
        async with tcp_server(stall, host='127.0.0.1') as stalled:
            try:
                port = stalled.sockets[0].getsockname()[1]
                path = config_file(tmp_path, f'Hostname 127.0.0.1\nPort {port}\nConnectTimeout 1\n')
                with pytest.raises(asyncio.TimeoutError):
                    await velnora.connect('target', config=path, known_hosts=None, agent_path=None)
                assert accepted, 'The deadline must be exercised on a real TCP connection'
            finally:
                for writer in accepted:
                    writer.close()
                    await writer.wait_closed()
        from F06_helpers import (independent_selection, checked_exchange,
                                 wire_proxy, ClientClosure, assert_rekey_boundary)
        algorithms = {'kex': ['ecdh-sha2-nistp384'], 'ciphers': ['aes128-ctr'],
                      'digests': ['hmac-sha2-256-etm@openssh.com']}
        async with independent_selection(algorithms) as (port, observed):
            path = config_file(tmp_path, 'KexAlgorithms ecdh-sha2-nistp384\n'
                'Ciphers aes128-ctr\nMACs hmac-sha2-256-etm@openssh.com\n'
                'RekeyLimit 64K\n')
            async with velnora.connect('127.0.0.1', port, config=path,
                    known_hosts=None, agent_path=None) as conn:
                await checked_exchange(conn, b'configured client rekey' * 50000)
        assert observed['kex'] == 'ecdh-sha2-nistp384'
        assert_rekey_boundary(observed, 65536)
        async with independent_selection({}, ignore_keepalives=True) as (port, observed):
            closed = asyncio.get_running_loop().create_future()
            path = config_file(tmp_path, 'ServerAliveInterval 1\nServerAliveCountMax 1\n')
            async with velnora.connect('127.0.0.1', port, config=path,
                    known_hosts=None, agent_path=None,
                    client_factory=lambda: ClientClosure(closed)) as conn:
                await bounded(conn.wait_closed(), timeout=10)
                assert isinstance(await bounded(closed), velnora.ConnectionLost)
        assert observed['global_requests'].count('keepalive@openssh.com') == 1
        from F16_helpers import local_display, display_exchange, forwarded_authorization
        async with local_display(tmp_path / 'x11-local.auth', b'configured-display') as display:
            for directive in ('ForwardX11Trusted yes', 'ForwardX11Trusted no'):
                app_ready = asyncio.get_running_loop().create_future()
                async def held_session(process):
                    app_ready.set_result(process)
                    await process.stdin.read()
                    process.exit(0)
                server_auth = tmp_path / 'x11-server.auth'
                server_auth.write_bytes(b'')
                async with velnora.listen('127.0.0.1', 0, config=None, server_factory=ConfigPeer,
                        server_host_keys=[certificate_identity()[0]], process_factory=held_session,
                        x11_forwarding=True, x11_auth_path=str(server_auth)) as listener:
                    path = config_file(tmp_path, directive + '\n')
                    async with velnora.connect('127.0.0.1', listener.get_port(), config=path,
                            known_hosts=None, agent_path=None) as conn:
                        process = await conn.create_process(x11_display=display.address,
                                                           x11_auth_path=str(display.auth_path))
                        app = await bounded(app_ready)
                        remote = app.channel.get_x11_display()
                        if directive.endswith('yes'):
                            authorization = forwarded_authorization(server_auth, remote)
                            await display_exchange(display, remote, authorization, directive.encode())
                        else:
                            assert remote is None
                        process.stdin.write_eof()
                        assert (await bounded(process.wait())).exit_status == 0
            async with config_listener(x11_forwarding=True,
                    x11_auth_path=str(tmp_path / 'x11-optional.auth')) as (listener, _):
                path = config_file(tmp_path, 'ForwardX11Trusted yes\n')
                async with velnora.connect('127.0.0.1', listener.get_port(), config=path,
                        known_hosts=None, agent_path=None) as conn:
                    assert (await session_report(conn, command='optional-x11',
                        x11_display='invalid-display'))['command'] == 'optional-x11'
        return 'test_client_session_negotiation_and_jump'
    assert run_async(scenario(), timeout=70) == 'test_client_session_negotiation_and_jump'


def test_server_configuration_effects(tmp_path):
    """F04.T04: configured listener identity, authorization and terminal policy."""
    async def scenario():
        client, _ = certificate_identity()
        host_keys = [certificate_identity('ssh-ed25519')[0],
                     certificate_identity('ecdsa-sha2-nistp256')[0]]
        host_paths = [tmp_path / ('host-' + str(i)) for i in range(2)]
        for key, path in zip(host_keys, host_paths):
            key.write_private_key(path)
        auth = tmp_path / 'authorized_keys'
        auth.write_text(authorized_line(client))
        for permit in ('yes', 'no'):
            path = config_file(tmp_path, f'''AddressFamily inet
Port 0
HostKey {host_paths[0]}
HostKey {host_paths[1]}
AuthorizedKeysFile {auth}
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
Ciphers aes256-ctr
MACs hmac-sha2-512
KexAlgorithms curve25519-sha256
Compression no
PermitTTY {permit}
TCPKeepAlive {permit}
UseDNS no
''', 'sshd_config')
            accepted = []
            class ServerObserver(velnora.SSHServer):
                def connection_made(self, conn):
                    accepted.append(conn)
            async with velnora.listen(config=path, process_factory=report_session,
                                       server_factory=ServerObserver) as server:
                for key in host_keys:
                    async with velnora.connect('127.0.0.1', server.get_port(),
                            config=None, known_hosts=None, agent_path=None,
                            username='member', client_keys=[client],
                            server_host_key_algs=[key.get_algorithm()]) as conn:
                        assert conn.get_server_host_key() == key.convert_to_public()
                        assert (accepted[-1].get_extra_info('socket').getsockopt(
                            socket.SOL_SOCKET, socket.SO_KEEPALIVE) != 0) == (permit == 'yes')
                        assert conn.get_extra_info('send_cipher') == 'aes256-ctr'
                        assert conn.get_extra_info('send_mac') == 'hmac-sha2-512'
                        assert conn.get_extra_info('send_compression') == 'none'
                        assert (await session_report(conn, command='alive'))['command'] == 'alive'
                        if permit == 'yes':
                            assert (await session_report(conn, term_type='xterm', request_pty=True))['terminal'] == 'xterm'
                        else:
                            with pytest.raises(velnora.ChannelOpenError):
                                await conn.run(term_type='xterm', request_pty=True)
                with pytest.raises(velnora.PermissionDenied):
                    async with velnora.connect('127.0.0.1', server.get_port(),
                            config=None, known_hosts=None, agent_path=None,
                            username='member', client_keys=[], password='wrong'):
                        pytest.fail('Unauthenticated connection accepted')
                # AddressFamily inet leaves the IPv6 loopback without a listener.
                with pytest.raises(OSError):
                    async with velnora.connect('::1', server.get_port(),
                            config=None, known_hosts=None, agent_path=None,
                            username='member', client_keys=[client]):
                        pytest.fail('The configured address family was ignored')
        # Both configured host certificates must remain selectable, just like keys.
        cas = [certificate_identity()[0] for _ in host_keys]
        certificates = [tmp_path / ('host-cert-' + str(i)) for i in range(2)]
        for ca, key, cert in zip(cas, host_keys, certificates):
            ca.generate_host_certificate(key, 'configured-host', principals=['127.0.0.1']).write_certificate(cert)
        path = config_file(tmp_path, f'HostKey {host_paths[0]}\nHostKey {host_paths[1]}\nHostCertificate {certificates[0]}\nHostCertificate {certificates[1]}\n', 'sshd_config')
        async with velnora.listen('127.0.0.1', 0, config=path,
                server_factory=ConfigPeer, process_factory=report_session) as server:
            for ca, key in zip(cas, host_keys):
                trust = velnora.import_known_hosts(host_line('127.0.0.1', ca, '@cert-authority'))
                async with velnora.connect('127.0.0.1', server.get_port(), config=None,
                        known_hosts=trust, agent_path=None,
                        server_host_key_algs=[key.get_algorithm() + '-cert-v01@openssh.com']) as conn:
                    assert (await session_report(conn, command='certificate-host'))['command'] == 'certificate-host'
        # LoginGraceTime bounds an unauthenticated connection which really exists.
        path = config_file(tmp_path, 'LoginGraceTime 1\n', 'sshd_config')
        async with config_listener(config=path) as (server, _):
            reader, writer = await asyncio.open_connection('127.0.0.1', server.get_port())
            try:
                assert (await reader.readline()).startswith(b'SSH-2.0-')
                await bounded(reader.read(), timeout=5)
                assert reader.at_eof(), 'The unauthenticated connection must close'
            finally:
                writer.close()
                await writer.wait_closed()
        agent_key, _ = certificate_identity()
        async with configuration_agent(tmp_path, [agent_key]) as agent:
            async with config_listener(key=agent_key) as (destination, _):
                for client_forward, server_forward in [('yes', 'yes'), ('no', 'yes'), ('yes', 'no')]:
                    observed = asyncio.get_running_loop().create_future()
                    async def observe_agent(process):
                        observed.set_result(process.channel.get_connection().get_agent_path())
                        await report_session(process)
                    server_config = config_file(tmp_path, f'AllowAgentForwarding {server_forward}\n', 'sshd_config')
                    async with velnora.listen('127.0.0.1', 0, config=server_config,
                            server_factory=ConfigPeer, server_host_keys=[host_keys[0]],
                            process_factory=observe_agent) as gateway:
                        client_config = config_file(tmp_path, f'IdentityAgent {agent}\nForwardAgent {client_forward}\n')
                        async with velnora.connect('127.0.0.1', gateway.get_port(),
                                config=client_config, known_hosts=None) as conn:
                            assert (await session_report(conn, command='forwarding'))['command'] == 'forwarding'
                            forwarded_path = await bounded(observed)
                            if client_forward == server_forward == 'yes':
                                # Reach the real agent through the SSH forwarding path
                                # and prove possession of its key by a second login.
                                assert forwarded_path is not None
                                async with velnora.connect('127.0.0.1', destination.get_port(),
                                        config=None, known_hosts=None, client_keys=[],
                                        agent_path=forwarded_path, username='forwarded-user') as through:
                                    assert (await session_report(through))['username'] == 'forwarded-user'
                            else:
                                assert forwarded_path is None
        from F06_helpers import (volume_session, independent_exchange, assert_rekey_boundary,
                                 ServerClosure, wire_proxy, openssh_exchange, echo_session)
        path = config_file(tmp_path, 'RekeyLimit 64K\n', 'sshd_config')
        async with velnora.listen('127.0.0.1', 0, config=path, server_factory=ConfigPeer,
                server_host_keys=[host_keys[0]], process_factory=volume_session,
                encoding=None, encryption_algs=['aes128-ctr'],
                mac_algs=['hmac-sha2-256-etm@openssh.com']) as listener:
            result = await independent_exchange(listener.get_port(), measure='bytes',
                mac='hmac-sha2-256-etm@openssh.com')
            assert_rekey_boundary(result, 65536)
        authenticated = asyncio.get_running_loop().create_future()
        closed = asyncio.get_running_loop().create_future()
        path = config_file(tmp_path, 'ClientAliveInterval 1\nClientAliveCountMax 1\n', 'sshd_config')
        async with velnora.listen('127.0.0.1', 0, config=path,
                server_factory=lambda: ServerClosure(authenticated, closed),
                server_host_keys=[host_keys[0]], process_factory=echo_session, encoding=None) as listener:
            task = asyncio.create_task(independent_exchange(listener.get_port(), ignore_keepalives=True))
            try:
                await bounded(authenticated)
                assert isinstance(await bounded(closed, timeout=10), velnora.ConnectionLost)
                result = await bounded(task, timeout=20)
                assert result['global_requests'].count('keepalive@openssh.com') == 1
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        signing_key, _ = certificate_identity('ssh-rsa')
        for algorithm in ('rsa-sha2-256', 'rsa-sha2-512'):
            path = config_file(tmp_path, 'CASignatureAlgorithms ' + algorithm + '\n', 'sshd_config')
            async with velnora.listen('127.0.0.1', 0, config=path, server_host_keys=[host_keys[0]],
                    server_factory=lambda: ConfigPeer(key=signing_key),
                    process_factory=echo_session, encoding=None) as listener:
                result = await independent_exchange(listener.get_port(), algorithm='ssh-rsa',
                    private=signing_key.export_private_key('pkcs8-pem').decode())
                assert result['signed'] == [algorithm]
        return 'test_server_configuration_effects'
    assert run_async(scenario(), timeout=60) == 'test_server_configuration_effects'


def test_conditional_configuration(tmp_path):
    """F04.T05: host patterns, combined/negated conditions and final pass."""
    from F00_environment import in_hosts_view
    hosts = '127.0.0.1 loopback.example localhost\n::1 localhost\n'
    child = in_hosts_view(test_conditional_configuration, tmp_path, hosts)
    if child is not None:
        assert child.returncode == 0, (child.stdout, child.stderr)
        return
    async def scenario():
        async with config_listener() as (listener, _):
            base = f'Hostname 127.0.0.1\nPort {listener.get_port()}\nUser remote-user\nTag release\n'
            conditions = [
                ('Host node* !node-blocked', 'node-one', True),
                ('Host node* !node-blocked', 'node-blocked', False),
                ('Host node-?', 'node-a', True),
                ('Host node-?', 'node-ab', False),
                ('Match all', 'node-one', True),
                ('Match host 127.0.0.1 originalhost node* user remote-*', 'node-one', True),
                ('Match host 127.0.0.1 originalhost other* user remote-*', 'node-one', False),
                # Each condition must also be able to fail on its own.
                ('Match host other.example', 'node-one', False),
                ('Match user other-*', 'node-one', False),
                (f'Match localuser {getpass.getuser()} !user other tagged release', 'node-one', True),
                (f'Match localuser not-{getpass.getuser()}', 'node-one', False),
                ('Match tagged other', 'node-one', False),
                ('Match !tagged release', 'node-one', False),
                ('Match exec "true"', 'node-one', True),
                ('Match exec "false"', 'node-one', False),
                ('Match localnetwork 127.0.0.0/8', 'node-one', True),
                ('Match localnetwork 192.0.2.0/24', 'node-one', False),
                ('Match !localnetwork 127.0.0.0/8', 'node-one', False),
                ('Match canonical', 'node-one', False),
                ('Match final', 'node-one', True),
            ]
            for condition, host, matches in conditions:
                path = config_file(tmp_path, base + condition + '\nRemoteCommand selected\nMatch all\nRemoteCommand unselected\n')
                result = await configured_report(path, host=host)
                assert result['command'] == ('selected' if matches else 'unselected'), condition
            path = config_file(tmp_path, base + 'RemoteCommand earlier\nMatch final\nRemoteCommand later\nSetEnv FINAL=applied\n')
            result = await configured_report(path)
            assert result['command'] == 'earlier'
            assert result['environment'] == {'FINAL': 'applied'}
            # Server conditions are re-evaluated with actual accepted connection data.
            key, _ = certificate_identity()
            for condition, matches in [
                    ('address 127.0.0.0/8 localaddress 127.0.0.1 user member', True),
                    ('address 192.0.2.0/24', False), ('!user member', False),
                    ('localaddress 192.0.2.1', False), ('user other', False),
                    ('host other.example', False),
                    ('host 127.0.0.1 exec "true"', True)]:
                path = config_file(tmp_path, 'UseDNS no\nMatch ' + condition + '\nPermitTTY no\n', 'sshd_config')
                async with config_listener(config=path) as (server, _):
                    async with velnora.connect('127.0.0.1', server.get_port(), config=None,
                            known_hosts=None, agent_path=None, username='member') as conn:
                        if matches:
                            with pytest.raises(velnora.ChannelOpenError):
                                await conn.run(term_type='xterm', request_pty=True)
                        else:
                            assert (await session_report(conn, term_type='xterm', request_pty=True))['terminal'] == 'xterm'
            # libc reads a real isolated hosts file. Changing UseDNS must change
            # the host condition's input independently of the judge's records.
            reverse_name = socket.gethostbyaddr('127.0.0.1')[0]
            assert reverse_name != '127.0.0.1', 'A named loopback reverse record is required'
            for lookup, matches in [('yes', True), ('no', False)]:
                path = config_file(tmp_path, 'UseDNS ' + lookup +
                    '\nMatch host ' + reverse_name + '\nPermitTTY no\n', 'sshd_config')
                async with config_listener(config=path) as (server, _):
                    async with velnora.connect('127.0.0.1', server.get_port(), config=None,
                            known_hosts=None, agent_path=None) as conn:
                        if matches:
                            with pytest.raises(velnora.ChannelOpenError):
                                await conn.run(term_type='xterm', request_pty=True)
                        else:
                            assert (await session_report(conn, term_type='xterm', request_pty=True))['terminal'] == 'xterm'
            path = config_file(tmp_path, base + 'Match unsupported foo\nRemoteCommand invalid\n')
            with pytest.raises(velnora.ConfigParseError):
                await configured_report(path)
            with socket.socket() as reserved:
                reserved.bind(('127.0.0.1', 0))
                port = reserved.getsockname()[1]
            for candidate, matches in [(port, True), (port + 1, False)]:
                path = config_file(tmp_path, 'Match localport ' + str(candidate) +
                                   '\nPermitTTY no\n', 'sshd_config')
                async with velnora.listen('127.0.0.1', port, config=path,
                        server_host_keys=[key], server_factory=ConfigPeer,
                        process_factory=report_session) as server:
                    async with velnora.connect('127.0.0.1', server.get_port(), config=None,
                            known_hosts=None, agent_path=None) as conn:
                        if matches:
                            with pytest.raises(velnora.ChannelOpenError):
                                await conn.run(term_type='xterm', request_pty=True)
                        else:
                            assert (await session_report(conn, term_type='xterm', request_pty=True))['terminal'] == 'xterm'
        return 'test_conditional_configuration'
    assert run_async(scenario(), timeout=60) == 'test_conditional_configuration'


def test_includes_substitutions_and_proxy(tmp_path, monkeypatch):
    """F04.T06: included values, real proxy and user authorization file expansion."""
    async def scenario():
        monkeypatch.setenv('F04_EXPANSION', 'expanded')
        async with config_listener() as (target, _):
            child = tmp_path / 'included.conf'
            child.write_text(f'Port {target.get_port()}\nUser remote-user\n')
            nested = tmp_path / 'nested.conf'
            nested.write_text(f'Include {tmp_path}/included*.conf\n')
            path = config_file(tmp_path, f'''Include {tmp_path}/absent-*.conf
Hostname 127.0.0.1
Include {nested}
Port 1
RemoteCommand %h|%n|%p|%r|%u|%d|%i|%l|%L|${{F04_EXPANSION}}|%%
''')
            result = await configured_report(path)
            hostname = socket.gethostname()
            assert result['command'].split('|') == [
                '127.0.0.1', 'target', str(target.get_port()), 'remote-user',
                getpass.getuser(), os.path.expanduser('~'), str(os.getuid()),
                hostname, hostname.split('.')[0], 'expanded', '%']
            path = config_file(tmp_path, f'Hostname %h\nPort {target.get_port()}\nRemoteCommand destination-substitution\n')
            assert (await configured_report(path, host='127.0.0.1'))['command'] == 'destination-substitution'
            # This is a real byte relay, not an SSH implementation or canned peer.
            relay = tmp_path / 'relay.py'
            relay.write_text('''import os, socket, sys, threading
s = socket.create_connection((sys.argv[1], int(sys.argv[2])))
def send():
    while True:
        data = os.read(0, 65536)
        if not data:
            s.shutdown(socket.SHUT_WR)
            return
        s.sendall(data)
threading.Thread(target=send, daemon=True).start()
while True:
    data = s.recv(65536)
    if not data:
        break
    os.write(1, data)
''')
            path = config_file(tmp_path, f'''Hostname 127.0.0.1
Port {target.get_port()}
ProxyCommand {sys.executable} {relay} %h %p
RemoteCommand proxied-${{F04_EXPANSION}}
''')
            assert (await configured_report(path))['command'] == 'proxied-expanded'
            for directive, value in [('RemoteCommand', '%Z'),
                                     ('RemoteCommand', '${F04_MISSING_VARIABLE}'),
                                     ('IdentityFile', '%Z'),
                                     ('CertificateFile', '%Z'),
                                     ('IdentityAgent', '%Z'),
                                     ('ProxyCommand', '%Z')]:
                monkeypatch.delenv('F04_MISSING_VARIABLE', raising=False)
                path = config_file(tmp_path, f'{directive} {value}\n')
                with pytest.raises(velnora.ConfigParseError):
                    await configured_report(path)
        client, _ = certificate_identity()
        authorization = tmp_path / 'member.authorized'
        issuer, _ = certificate_identity()
        client.write_private_key(tmp_path / 'member.private')
        issuer.generate_user_certificate(client, 'expanded-location', principals=['member']).write_certificate(tmp_path / 'member.certificate')
        authorization.write_text(authorized_line(issuer, 'cert-authority'))
        monkeypatch.setenv('F04_AUTH_DIRECTORY', str(tmp_path))
        path = config_file(tmp_path, 'Match user ?*\nAuthorizedKeysFile ${F04_AUTH_DIRECTORY}/%u.authorized\n', 'sshd_config')
        host, _ = certificate_identity()
        async with velnora.listen('127.0.0.1', 0, config=path,
                server_host_keys=[host], process_factory=report_session) as server:
            client_config = config_file(tmp_path, f'Hostname 127.0.0.1\nPort {server.get_port()}\nUser member\nIdentityFile ${{F04_AUTH_DIRECTORY}}/%r.private\nCertificateFile ${{F04_AUTH_DIRECTORY}}/%r.certificate\n')
            assert (await configured_report(client_config))['username'] == 'member'
        return 'test_includes_substitutions_and_proxy'
    assert run_async(scenario(), timeout=40) == 'test_includes_substitutions_and_proxy'


def test_unsafe_authorization_user(tmp_path):
    """F04.T07: reject every unsafe category; authenticate safe near matches."""
    async def scenario():
        client, _ = certificate_identity()
        host, _ = certificate_identity()
        path = config_file(tmp_path, f'Match user ?*\nAuthorizedKeysFile {tmp_path}/%u.keys\n', 'sshd_config')
        safe = ('inside..name', 'inside~name', 'Cname:', 'name$plain')
        for user in safe:
            (tmp_path / (user + '.keys')).write_text(authorized_line(client))
        async with velnora.listen('127.0.0.1', 0, config=path,
                server_host_keys=[host], process_factory=report_session) as server:
            for user in safe:
                async with velnora.connect('127.0.0.1', server.get_port(), config=None,
                        known_hosts=None, agent_path=None, username=user, client_keys=[client]) as conn:
                    assert (await session_report(conn))['username'] == user
            for user in ('..', '~name', 'C:name', 'part/name', 'part\\name', '${HOME}'):
                with pytest.raises(velnora.IllegalUserName):
                    async with velnora.connect('127.0.0.1', server.get_port(), config=None,
                            known_hosts=None, agent_path=None, username=user, client_keys=[client]):
                        pytest.fail('Unsafe authorization identity accepted')
        return 'test_unsafe_authorization_user'
    assert run_async(scenario()) == 'test_unsafe_authorization_user'


def test_invalid_configuration_location(tmp_path):
    """F04.T08: typed values, required arguments and quotation error locations."""
    async def scenario():
        invalid = ('Port not-an-integer', 'Compression perhaps', 'AddressFamily ipx',
                   'RequestTTY sometimes', 'CanonicalizeHostname perhaps',
                   'User', 'User "unterminated')
        for line in invalid:
            path = config_file(tmp_path, '# Header\n\n' + line + '\n')
            with pytest.raises(velnora.ConfigParseError) as error:
                await velnora.connect('127.0.0.1', config=path, agent_path=None)
            # File and line are diagnostic shell, not the prose of the reason.
            assert str(error.value).startswith(f'{path} line 3:')
        for line in ('Port broken', 'PermitTTY perhaps', 'AddressFamily ipx',
                     'CanonicalizeHostname perhaps', 'HostKey', 'HostKey "unterminated', 'Match unknown value'):
            path = config_file(tmp_path, '# Header\n' + line + '\n', 'sshd_config')
            with pytest.raises(velnora.ConfigParseError) as error:
                await velnora.listen('127.0.0.1', 0, config=path)
            assert str(error.value).startswith(f'{path} line 2:')
        return 'test_invalid_configuration_location'
    assert run_async(scenario()) == 'test_invalid_configuration_location'


def test_token_provider_configuration(tmp_path):
    """File-selected signing provider supplies otherwise unavailable credentials."""
    import base64
    from F05_helpers import token_provider, shared_token_provider
    async def scenario():
        with token_provider(tmp_path) as (provider, pin, materials):
            async with shared_token_provider(tmp_path, provider) as shared_provider:
                identity = materials[0]
                public = velnora.import_public_key(identity['algorithm'].encode() + b' ' +
                                                   base64.b64encode(identity['blob']))
                async with config_listener(key=public) as (listener, _):
                    path = config_file(tmp_path, 'PKCS11Provider ' + shared_provider +
                        '\nPreferredAuthentications publickey\n')
                    options = dict(config=path, known_hosts=None, agent_path=None,
                                   client_keys=[], username='member')
                    async with velnora.connect('127.0.0.1', listener.get_port(),
                                                 pkcs11_pin=pin, **options) as conn:
                        report = await session_report(conn, command='token-only')
                        assert report['command'] == 'token-only'
                    path = config_file(tmp_path, 'PKCS11Provider none\nPreferredAuthentications publickey\n')
                    with pytest.raises(velnora.PermissionDenied):
                        async with velnora.connect('127.0.0.1', listener.get_port(),
                                                     pkcs11_pin=pin, **options):
                            pytest.fail('A disabled token provider supplied signing credentials')
        return report['command']
    assert run_async(scenario(), timeout=60) == 'token-only'


def test_server_gss_key_exchange_configuration(tmp_path):
    """Server file configuration enables and disables real GSS transport."""
    from F07_helpers import kerberos_realm
    from F06_helpers import echo_session, independent_exchange
    async def scenario():
        outcomes = {}
        async with kerberos_realm(tmp_path) as realm:
            for enabled in ('yes', 'no'):
                path = config_file(tmp_path, 'GSSAPIKeyExchange ' + enabled + '\n', 'sshd_config')
                async with velnora.listen('127.0.0.1', 0, config=path,
                        server_factory=ConfigPeer, server_host_keys=[certificate_identity()[0]],
                        process_factory=echo_session, encoding=None,
                        gss_host=realm['service'],
                        gss_store={'keytab': realm['env']['KRB5_KTNAME']}) as listener:
                    result = await independent_exchange(listener.get_port(),
                        kex='gss-curve25519-sha256-toWM5Slw5Ew8Mqkay+al2g==',
                        gss_cache=realm['cache'], gss_service=realm['service'], refused=enabled == 'no')
                    outcomes[enabled] = result['refused']
                    await independent_exchange(listener.get_port(), kex='curve25519-sha256@libssh.org')
        return outcomes
    assert run_async(scenario(), timeout=60) == {'yes': False, 'no': True}


def test_canonical_conditions_and_reverse_server_configuration(tmp_path):
    """Real name resolution drives canonical blocks and outbound server options."""
    from F00_environment import in_hosts_view
    hosts = ('127.0.0.1 localhost\n'
             '127.0.0.1 canonical.example node.example part.node.example\n'
             '127.0.0.1 node part.node\n')
    child = in_hosts_view(test_canonical_conditions_and_reverse_server_configuration, tmp_path, hosts)
    if child is not None:
        assert child.returncode == 0, (child.stdout, child.stderr)
        return
    async def scenario():
        observations = []
        async with config_listener() as (listener, _):
            for enabled, expected in [('yes', 'canonical-block'), ('no', 'ordinary-block')]:
                path = config_file(tmp_path, f'Port {listener.get_port()}\n'
                    f'CanonicalizeHostname {enabled}\nCanonicalDomains example\n'
                    'CanonicalizeFallbackLocal no\nMatch canonical\nRemoteCommand canonical-block\n'
                    'Match all\nRemoteCommand ordinary-block\n')
                assert (await configured_report(path, host='node'))['command'] == expected
        key, _ = certificate_identity()
        for threshold in (0, 1):
            for host_pattern, alias_pattern, follows in [('*', '*', True),
                    ('other.*', '*', False), ('*', 'other.*', False)]:
                accepted = asyncio.get_running_loop().create_future()
                async with velnora.listen_reverse('127.0.0.1', 0, config=None,
                        known_hosts=([key.convert_to_public()], [], []), agent_path=None,
                        client_keys=[], username='member', acceptor=accepted.set_result) as listener:
                    path = config_file(tmp_path, 'CanonicalizeHostname yes\nCanonicalDomains example\n'
                        'CanonicalizeFallbackLocal no\nCanonicalizeMaxDots ' + str(threshold) +
                        '\nCanonicalizePermittedCNAMEs ' + host_pattern + ':' + alias_pattern + '\n', 'sshd_config')
                    expected = ('part.node' if threshold == 0 else
                                'canonical.example' if follows else 'part.node.example')
                    async with velnora.connect_reverse('part.node', listener.get_port(),
                            config=path, server_factory=ConfigPeer, server_host_keys=[key],
                            process_factory=report_session) as server:
                        client = await bounded(accepted)
                        try:
                            actual = server.get_extra_info('host')
                            observations.append((actual, expected))
                            assert actual == expected
                            assert (await session_report(client, command='reverse-config'))['command'] == 'reverse-config'
                        finally:
                            client.close()
                            await bounded(client.wait_closed())
        return observations
    observations = run_async(scenario(), timeout=90)

    assert len(observations) == 6
    assert all(actual == expected for actual, expected in observations)


if __name__ == '__main__':
    from pathlib import Path
    globals()[sys.argv[1]](Path(sys.argv[2]))
