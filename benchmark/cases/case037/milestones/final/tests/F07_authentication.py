# feature: F07
"""Acceptance checks for authentication and application access policy."""
import asyncio
import getpass
import time

import velnora
import pytest

from _helpers import bounded, run_async, temporary_environment, opened_connection
from F02_helpers import certificate_identity
from F04_helpers import configuration_agent
from F06_helpers import openssh_daemon, daemon_connect
from F07_helpers import (AccessPolicy, access_listener, access_connect,
                         access_granted, ChangeClient, InteractiveClient,
                         independent_invalid_signature, closed_attempt)


def test_method_selection_and_access(tmp_path):
    async def scenario():
        key, _ = certificate_identity()
        wrong, _ = certificate_identity()
        class Methods(AccessPolicy):
            def host_based_auth_supported(self):
                return True
            def validate_host_public_key(self, host, addr, port, key):
                self.attempts.append('hostbased')
                return False
            def kbdint_auth_supported(self):
                return True
            def get_kbdint_challenge(self, username, lang, submethods):
                self.attempts.append('keyboard-interactive')
                return False
        policy = Methods(key=key, password='accepted')
        async with access_listener(policy, host_based_auth=True,
                                   trust_client_host=True) as port:
            await access_granted(port, client_host_keys=[wrong],
                                 client_host='client.example', client_username='origin',
                                 client_keys=[wrong], password='accepted')
            order = list(dict.fromkeys(policy.attempts))
            assert order == ['hostbased', 'publickey', 'keyboard-interactive', 'password']
            policy.attempts.clear()
            await access_granted(port, client_keys=[key], password='accepted',
                                 preferred_auth=['password', 'publickey'])
            assert policy.attempts == ['password']
            with pytest.raises(velnora.PermissionDenied):
                await bounded(closed_attempt(port, client_keys=[key], public_key_auth=False,
                                             password='wrong', kbdint_auth=False))
            with pytest.raises(velnora.PermissionDenied):
                await bounded(closed_attempt(port, preferred_auth=['publickey']))
            assert policy.sessions == 2
        anonymous = AccessPolicy(anonymous=True)
        async with access_listener(anonymous) as port:
            await access_granted(port)
        from F07_helpers import kerberos_realm
        from F06_helpers import independent_selection, checked_exchange
        async with kerberos_realm(tmp_path) as realm:
            # An initial 'none' probe is optional; only the order of real methods matters.
            for reject_keyex, expected in ((False, ['gssapi-keyex']),
                    (True, ['gssapi-keyex', 'gssapi-with-mic'])):
                async with independent_selection({'kex': ['gss-curve25519-sha256-toWM5Slw5Ew8Mqkay+al2g==']},
                        gss_service=realm['service'], gss_keytab=realm['env']['KRB5_KTNAME'],
                        reject_keyex=reject_keyex) as (port, observed):
                    async with velnora.connect('127.0.0.1', port, config=None,
                            known_hosts=None, agent_path=None, client_keys=[], username='member',
                            gss_host=realm['service'], gss_store={'ccache': realm['cache']},
                            gss_kex=True, gss_auth=True,
                            kex_algs=['gss-curve25519-sha256']) as conn:
                        await checked_exchange(conn, b'default GSS authentication order')
                assert [m for m in observed['methods'] if m != 'none'] == expected
        return 'test_method_selection_and_access'
    assert run_async(scenario(), timeout=70) == 'test_method_selection_and_access'


def test_key_identity_agent_filter_and_methods(tmp_path):
    async def scenario():
        key, _ = certificate_identity()
        other, _ = certificate_identity()
        policy = AccessPolicy(key=key)
        async with access_listener(policy) as port:
            methods = await velnora.get_server_auth_methods('127.0.0.1', port,
                config=None, username='member')
            assert set(methods) == {'publickey'}
            assert policy.sessions == 0
            await access_granted(port, client_keys=[key])
            await bounded(asyncio.to_thread(independent_invalid_signature, port, key, other))
            for options in [dict(client_keys=[other]),
                            dict(client_keys=[key], username='outsider')]:
                with pytest.raises(velnora.PermissionDenied):
                    await bounded(closed_attempt(port, **options))
            async with configuration_agent(tmp_path, [other, key]) as agent:
                await access_granted(port, agent_path=agent, agent_identities=[key])
                with pytest.raises(velnora.PermissionDenied):
                    await bounded(closed_attempt(port, agent_path=agent,
                                                 agent_identities=[other]))
            assert policy.sessions == 2
        # Advertised methods follow the server's actual enabled methods.
        for settings, advertised in ((dict(password='accepted'), {'password'}),
                                     (dict(key=key, password='accepted'), {'publickey', 'password'})):
            policy = AccessPolicy(**settings)
            async with access_listener(policy, kbdint_auth=False) as port:
                methods = await velnora.get_server_auth_methods('127.0.0.1', port,
                    config=None, username='member')
                assert set(methods) == advertised
                assert policy.sessions == 0
                await access_granted(port, password='accepted', preferred_auth=['password'])
                assert policy.sessions == 1
        # The independent daemon verifies a real signature, not a matching blob.
        async with openssh_daemon(tmp_path / 'daemon') as (port, private, hosts, service):
            async with opened_connection(daemon_connect(port, private)) as conn:
                result = await bounded(conn.run('printf independent-proof'))
                assert result.stdout == 'independent-proof'
                assert result.exit_status == 0
            with pytest.raises(velnora.PermissionDenied):
                await bounded(daemon_connect(port, other))
        anonymous = AccessPolicy(anonymous=True)
        async with access_listener(anonymous) as port:
            async with access_connect(port, username=getpass.getuser()) as conn:
                from F04_helpers import session_report
                report = await session_report(conn, command='identity')
                assert report['username'] == getpass.getuser()
            # Omit username at the public entry to exercise the actual default.
            async with velnora.connect('127.0.0.1', port, config=None,
                    known_hosts=None, agent_path=None, client_keys=[]) as conn:
                report = await session_report(conn, command='identity')
                assert report['username'] == getpass.getuser()
        xkey, _ = certificate_identity()
        xcert = xkey.generate_x509_user_certificate(
            xkey, 'CN=Member', principals=['member'])
        xauth = velnora.import_authorized_keys(xcert.export_certificate('openssh').decode())
        async with access_listener(AccessPolicy(), authorized_client_keys=xauth) as port:
            await access_granted(port, client_keys=[(xkey, xcert)])
            alien = other.generate_x509_user_certificate(
                other, 'CN=Member', principals=['member'])
            with pytest.raises(velnora.PermissionDenied):
                await bounded(closed_attempt(port, client_keys=[(other, alien)]))
        home = tmp_path / 'home'
        (home / '.ssh').mkdir(parents=True)
        key.write_private_key(home / '.ssh' / 'id_ed25519')
        async with access_listener(AccessPolicy(key=key)) as port:
            with temporary_environment({'HOME': str(home)}):
                await access_granted(port, client_keys=())
        return 'test_key_identity_agent_filter_and_methods'
    assert run_async(scenario(), timeout=30) == 'test_key_identity_agent_filter_and_methods'


def test_user_certificate_authorization():
    async def scenario():
        ca, _ = certificate_identity()
        untrusted, _ = certificate_identity()
        key, _ = certificate_identity()
        now = int(time.time())
        trusted = 'cert-authority ' + ca.export_public_key().decode()
        policy = AccessPolicy()
        async with access_listener(policy, authorized_client_keys=velnora.import_authorized_keys(trusted)) as port:
            cert = ca.generate_user_certificate(key, 'login', principals=['member'])
            await access_granted(port, client_keys=[(key, cert)])
            cases = [
                untrusted.generate_user_certificate(key, 'login', principals=['member']),
                ca.generate_host_certificate(key, 'login', principals=['member']),
                ca.generate_user_certificate(key, 'login', principals=['outsider']),
                ca.generate_user_certificate(key, 'login', principals=['member'], valid_before=now-60),
                ca.generate_user_certificate(key, 'login', principals=['member'], valid_after=now+3600),
                ca.generate_user_certificate(key, 'login', principals=['member'], source_address=['192.0.2.0/24']),
            ]
            # An independently issued unknown critical option must be rejected.
            import tempfile
            from pathlib import Path
            from _helpers import run_command
            with tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                ca.write_private_key(directory / 'ca')
                (directory / 'ca').chmod(0o600)
                key.write_public_key(directory / 'identity.pub')
                result = run_command(['ssh-keygen', '-q', '-s', str(directory / 'ca'),
                    '-I', 'critical', '-n', 'member', '-O', 'critical:unknown-policy=required',
                    str(directory / 'identity.pub')])
                assert result.returncode == 0, result.stderr
                key.write_private_key(directory / 'identity')
                (directory / 'identity').chmod(0o600)
                argv = ['ssh', '-F', '/dev/null', '-p', str(port),
                    '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null',
                    '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
                    '-o', 'IdentityAgent=none', '-o', 'PreferredAuthentications=publickey',
                    '-o', 'CertificateFile=' + str(directory / 'identity-cert.pub'),
                    '-i', str(directory / 'identity'), 'member@127.0.0.1', 'identity']
                certpath = directory / 'identity-cert.pub'
                critical = certpath.read_bytes()
                certpath.write_bytes(cert.export_certificate('openssh'))
                success = await asyncio.to_thread(run_command, argv)
                assert success.returncode == 0, success.stderr
                import json
                assert json.loads(success.stdout)['username'] == 'member'
                certpath.write_bytes(critical)
                denied = await asyncio.to_thread(run_command, argv)
                assert denied.returncode == 255, denied.stderr
            for rejected in cases:
                with pytest.raises(velnora.PermissionDenied):
                    await bounded(closed_attempt(port, client_keys=[(key, rejected)]))
            assert policy.sessions == 2
        # Explicit authorization principals replace the implicit username match.
        auth = 'cert-authority,principals="role" ' + ca.export_public_key().decode()
        async with access_listener(AccessPolicy(), authorized_client_keys=velnora.import_authorized_keys(auth)) as port:
            await access_granted(port, client_keys=[(key, ca.generate_user_certificate(
                key, 'role', principals=['role']))])
            with pytest.raises(velnora.PermissionDenied):
                await bounded(closed_attempt(port, client_keys=[(key, cert)]))
        allowed = ca.generate_user_certificate(key, 'source', principals=['member'],
                                               source_address=['127.0.0.0/8'])
        async with access_listener(AccessPolicy(), authorized_client_keys=velnora.import_authorized_keys(trusted)) as port:
            await access_granted(port, client_keys=[(key, allowed)])
        # An independent client presents the authorized certificate, then the
        # same certificate with one bit of the authority's signature changed.
        import base64
        from F06_helpers import transport_listener, independent_exchange
        blob = base64.b64decode(cert.export_certificate('openssh').split()[1])
        tampered = blob[:-1] + bytes([blob[-1] ^ 1])
        async with transport_listener(server_factory=velnora.SSHServer,
                authorized_client_keys=velnora.import_authorized_keys(trusted)) as (listener, _):
            for certificate, accepted in ((blob, True), (tampered, False)):
                result = await independent_exchange(listener.get_port(), algorithm='ssh-ed25519',
                    private=key.export_private_key('pkcs8-pem').decode(),
                    certificate=base64.b64encode(certificate).decode(), denied=not accepted)
                assert result.get('denied', False) is not accepted
        return 'test_user_certificate_authorization'
    assert run_async(scenario(), timeout=40) == 'test_user_certificate_authorization'


def test_password_and_change():
    async def scenario():
        class PasswordPolicy(AccessPolicy):
            def validate_password(self, username, password):
                self.credentials.append((username, password))
                if password == 'old-secret':
                    raise velnora.PasswordChangeRequired('Choose replacement', 'en-US')
                return username == 'member' and password == 'current-secret'
            def change_password(self, username, old, new):
                self.credentials.append((username, old, new))
                return username == 'member' and old == 'old-secret' and new == 'new-secret'
        policy = PasswordPolicy(password='enabled')
        async with access_listener(policy, kbdint_auth=False) as port:
            await access_granted(port, password='current-secret', preferred_auth=['password'])
            assert policy.credentials[-1] == ('member', 'current-secret')
            with pytest.raises(velnora.PermissionDenied):
                await bounded(closed_attempt(port, password='invalid', preferred_auth=['password']))
            for replacement, accepted in [('new-secret', True), ('bad-replacement', False)]:
                client = ChangeClient(replacement)
                options = dict(password='old-secret', client_factory=lambda: client,
                               preferred_auth=['password'])
                if accepted:
                    await access_granted(port, **options)
                else:
                    with pytest.raises(velnora.PermissionDenied):
                        await bounded(closed_attempt(port, **options))
                assert client.events == [('request', 'Choose replacement', 'en-US'),
                                         ('accepted' if accepted else 'rejected',)]
                assert ('member', 'old-secret', replacement) in policy.credentials
            assert policy.sessions == 2
        return 'test_password_and_change'
    assert run_async(scenario()) == 'test_password_and_change'


def test_interactive_rounds_and_rejection():
    async def scenario():
        challenges = [('First', 'Identify', 'en-US', [('User', True), ('Secret', False)]),
                      ('Second', 'Confirm', 'en-US', [('Code', False)])]
        class InteractivePolicy(AccessPolicy):
            def __init__(self):
                super().__init__()
                self.responses = []
            def kbdint_auth_supported(self):
                return True
            def get_kbdint_challenge(self, username, lang, submethods):
                return challenges[0]
            def validate_kbdint_response(self, username, responses):
                self.responses.append(responses)
                if len(self.responses) == 1:
                    return challenges[1] if responses == ['member', 'secret'] else False
                return responses == ['654321']
        for answers, accepted in [([['member', 'secret'], ['654321']], True),
                                  ([['member', 'wrong']], False),
                                  ([['member', 'secret'], ['wrong']], False)]:
            policy = InteractivePolicy()
            client = InteractiveClient(answers)
            async with access_listener(policy) as port:
                options = dict(client_factory=lambda: client,
                               preferred_auth=['keyboard-interactive'])
                if accepted:
                    await access_granted(port, **options)
                else:
                    with pytest.raises(velnora.PermissionDenied):
                        await bounded(closed_attempt(port, **options))
                assert client.challenges == challenges[:len(answers)]
                assert policy.responses == answers
                assert policy.sessions == int(accepted)
        return 'test_interactive_rounds_and_rejection'
    assert run_async(scenario()) == 'test_interactive_rounds_and_rejection'


def test_host_based_identity_and_user_relationship():
    async def scenario():
        host, _ = certificate_identity()
        other, _ = certificate_identity()
        class HostPolicy(AccessPolicy):
            def __init__(self):
                super().__init__()
                self.hosts, self.users = [], []
            def host_based_auth_supported(self):
                return True
            def validate_host_public_key(self, name, addr, port, key):
                self.hosts.append((name, key))
                return name == 'origin.example' and key == host.convert_to_public()
            def validate_host_based_user(self, username, name, local_user):
                self.users.append((username, name, local_user))
                return username == 'member' and local_user == 'local-member'
        for key, hostname, user, remote, accepted in [
                (host, 'origin.example', 'local-member', 'member', True),
                (other, 'origin.example', 'local-member', 'member', False),
                (host, 'untrusted.example', 'local-member', 'member', False),
                (host, 'origin.example', 'outsider', 'member', False),
                (host, 'origin.example', 'local-member', 'outsider', False)]:
            policy = HostPolicy()
            async with access_listener(policy, host_based_auth=True,
                                       trust_client_host=True) as port:
                options = dict(client_host_keys=[key], client_host=hostname,
                               client_username=user, username=remote, preferred_auth=['hostbased'])
                if accepted:
                    await access_granted(port, **options)
                    assert policy.hosts == [(hostname, host.convert_to_public())]
                    assert policy.users == [(remote, hostname, user)]
                else:
                    with pytest.raises(velnora.PermissionDenied):
                        await bounded(closed_attempt(port, **options))
                assert policy.sessions == int(accepted)
        return 'test_host_based_identity_and_user_relationship'
    assert run_async(scenario()) == 'test_host_based_identity_and_user_relationship'


def test_banner_deadline_and_nontrivial_policy():
    async def scenario():
        class BannerPolicy(AccessPolicy):
            def connection_made(self, conn):
                super().connection_made(conn)
                conn.send_auth_banner('Authorized access only\n', 'en-US')
        class BannerClient(velnora.SSHClient):
            def auth_banner_received(self, message, lang):
                banners.append((message, lang))
        banners = []
        async with access_listener(BannerPolicy(password='secret')) as port:
            await access_granted(port, password='secret', client_factory=BannerClient)
        assert banners == [('Authorized access only\n', 'en-US')]
        async with access_listener(AccessPolicy(anonymous=True)) as port:
            await access_granted(port)
            with pytest.raises(velnora.PermissionDenied):
                await bounded(closed_attempt(port, disable_trivial_auth=True))
        # A real credential exchange satisfies the same client restriction.
        async with access_listener(AccessPolicy(password='secret'), kbdint_auth=False) as port:
            await access_granted(port, password='secret', preferred_auth=['password'],
                                 disable_trivial_auth=True)
        for deadline in [-1]:
            with pytest.raises(ValueError):
                velnora.SSHClientConnectionOptions(config=None, login_timeout=deadline)
            with pytest.raises(ValueError):
                velnora.SSHServerConnectionOptions(config=None, login_timeout=deadline)
        # Same delayed authentication on both arms: only the deadline changes.
        for deadline, accepted in [(0.1, False), (0, True)]:
            async with access_listener(AccessPolicy(anonymous=True, delay=0.4), login_timeout=0) as port:
                if accepted:
                    await access_granted(port, login_timeout=deadline)
                else:
                    with pytest.raises(velnora.ConnectionLost):
                        await bounded(closed_attempt(port, login_timeout=deadline))
        for deadline, accepted in [(0.1, False), (0, True)]:
            async with access_listener(AccessPolicy(anonymous=True, delay=0.4), login_timeout=deadline) as port:
                if accepted:
                    await access_granted(port, login_timeout=0)
                else:
                    with pytest.raises(velnora.ConnectionLost):
                        await bounded(closed_attempt(port, login_timeout=0))
        # Observe each default through a pending login, with the peer's timer off.
        # The interval only accommodates scheduling around the specified 120 s.
        async def default_deadline(client_default):
            server_options = {'login_timeout': 0} if client_default else {}
            client_options = {} if client_default else {'login_timeout': 0}
            async with access_listener(AccessPolicy(anonymous=True, delay=150),
                                       **server_options) as port:
                start = time.monotonic()
                with pytest.raises(velnora.ConnectionLost):
                    await bounded(closed_attempt(port, **client_options), timeout=145)
                assert 115 <= time.monotonic() - start <= 145
        await asyncio.gather(default_deadline(True), default_deadline(False))
        return 'test_banner_deadline_and_nontrivial_policy'
    assert run_async(scenario(), timeout=155) == 'test_banner_deadline_and_nontrivial_policy'


def test_host_based_external_keysign(tmp_path):
    """OpenSSH signs a permitted public host identity without a supplied secret."""
    import shlex
    from F00_environment import filesystem_view
    from F04_helpers import session_report
    host, _ = certificate_identity()
    keys = tmp_path / 'system-ssh'
    keys.mkdir()
    private = keys / 'ssh_host_ed25519_key'
    host.write_private_key(private)
    private.chmod(0o600)
    host.write_public_key(keys / 'ssh_host_ed25519_key.pub')
    (keys / 'ssh_config').write_text('EnableSSHKeysign yes\n')
    public = tmp_path / 'host.pub'
    host.write_public_key(public)

    class HostPolicy(AccessPolicy):
        def host_based_auth_supported(self):
            return True
        def validate_host_public_key(self, name, addr, port, key):
            return key == host.convert_to_public()
        def validate_host_based_user(self, username, name, local_user):
            return username == 'member' and local_user == getpass.getuser()

    with filesystem_view(tmp_path, [(keys, '/etc/ssh')]) as (argv, env):
        wrapper = tmp_path / 'keysign'
        wrapper.write_text('#!/bin/sh\nexec env ' +
            ' '.join(shlex.quote(name + '=' + env[name]) for name in
                     ('LD_LIBRARY_PATH', 'PROOT_NO_SECCOMP')) + ' ' +
            shlex.join([*argv, '/usr/lib/openssh/ssh-keysign']) + '\n')
        wrapper.chmod(0o700)
        async def scenario():
            policy = HostPolicy()
            async with access_listener(policy, host_based_auth=True, trust_client_host=True) as port:
                options = dict(client_host_keys=[str(public)], client_host_keysign=str(wrapper),
                    client_username=getpass.getuser(), client_host='localhost', preferred_auth=['hostbased'])
                async with access_connect(port, **options) as conn:
                    assert (await session_report(conn, command='external-host-proof'))['command'] == 'external-host-proof'
                assert policy.sessions == 1
            return policy.sessions
        assert run_async(scenario(), timeout=30) == 1


def test_gssapi_realm_identity_and_delegation(tmp_path):
    async def scenario():
        from F07_helpers import kerberos_realm
        async with kerberos_realm(tmp_path) as realm:
            class GSSPolicy(AccessPolicy):
                def __init__(self):
                    super().__init__()
                    self.principals = []
                def validate_gss_principal(self, username, user_principal, host_principal):
                    self.principals.append((username, user_principal, host_principal))
                    return username == 'member' and user_principal == realm['principal']
            for method, kex in [('gssapi-keyex', 'gss-curve25519-sha256'),
                                ('gssapi-with-mic', 'curve25519-sha256')]:
                policy = GSSPolicy()
                async with access_listener(policy, gss_host=realm['service'],
                        gss_store={'keytab': realm['env']['KRB5_KTNAME']},
                        gss_kex=True, gss_auth=True) as port:
                    options = dict(gss_host=realm['service'], gss_kex=True, gss_auth=True,
                                   preferred_auth=[method], kex_algs=[kex])
                    await access_granted(port, gss_store={'ccache': realm['cache']}, **options)
                    assert policy.principals == [('member', realm['principal'], realm['service'])]
                    with pytest.raises(velnora.PermissionDenied):
                        await bounded(closed_attempt(port,
                            gss_store={'ccache': realm['other_cache']}, **options))
                    assert policy.principals[-1] == ('member', realm['alternate'], realm['service'])
                    with pytest.raises(velnora.PermissionDenied):
                        await bounded(closed_attempt(port, gss_auth=False,
                            **{name: value for name, value in options.items() if name != 'gss_auth'}))
                    assert policy.sessions == 1
            # An independent SSH service consumes the forwarded ticket cache.
            # A service-ticket request proves that delegation delivered usable
            # credentials, rather than merely toggling a reported flag.
            import shlex
            command = (
                'if test -n "$KRB5CCNAME"; then KRB5_CONFIG=' +
                shlex.quote(realm['env']['KRB5_CONFIG']) + ' ' +
                shlex.quote(str(realm['tools'] / 'usr/bin/kvno')) + ' ' +
                shlex.quote(realm['service']) +
                ' >/dev/null && printf delegated; else printf none; fi')
            async with openssh_daemon(tmp_path / 'gss-daemon',
                    extra='GSSAPIAuthentication yes\nGSSAPIStrictAcceptorCheck no\n') as (port, private, hosts, service):
                for delegation, expected in [({'gss_delegate_creds': True}, 'delegated'),
                                             ({}, 'none'),
                                             ({'gss_delegate_creds': False}, 'none')]:
                    async with opened_connection(daemon_connect(port, private,
                            preferred_auth=['gssapi-with-mic'], gss_kex=False,
                            gss_auth=True, gss_host=realm['service'],
                            gss_store={'ccache': realm['cache']}, **delegation)) as conn:
                        result = await bounded(conn.run(command))
                        assert result.exit_status == 0, result.stderr
                        assert result.stdout == expected
        return 'test_gssapi_realm_identity_and_delegation'
    assert run_async(scenario(), timeout=45) == 'test_gssapi_realm_identity_and_delegation'
