# feature: F07
"""Application authentication policies over real SSH transports."""
from contextlib import asynccontextmanager
import velnora
from F02_helpers import certificate_identity
from F04_helpers import report_session, session_report


class AccessPolicy(velnora.SSHServer):
    def __init__(self, *, key=None, password=None, anonymous=False, delay=0):
        self.key, self.password = key, password
        self.anonymous, self.delay = anonymous, delay
        self.attempts = []
        self.credentials = []
        self.sessions = 0

    def connection_made(self, conn):
        self.conn = conn

    async def begin_auth(self, username):
        import asyncio
        if self.delay:
            await asyncio.sleep(self.delay)
        return not self.anonymous

    def public_key_auth_supported(self):
        return self.key is not None

    def validate_public_key(self, username, key):
        self.attempts.append('publickey')
        self.credentials.append((username, key))
        return self.key is not None and username == 'member' and key == self.key.convert_to_public()

    def password_auth_supported(self):
        return self.password is not None

    def validate_password(self, username, password):
        self.attempts.append('password')
        self.credentials.append((username, password))
        return username == 'member' and password == self.password


@asynccontextmanager
async def access_listener(policy, **options):
    host, _ = certificate_identity()
    async def application(process):
        policy.sessions += 1
        await report_session(process)
    async with velnora.listen('127.0.0.1', 0, config=None,
                               server_host_keys=[host], server_factory=lambda: policy,
                               process_factory=application, **options) as listener:
        yield listener.get_port()


def access_connect(port, **options):
    defaults = dict(config=None, known_hosts=None, agent_path=None,
                    client_keys=[], username='member')
    defaults.update(options)
    return velnora.connect('127.0.0.1', port, **defaults)


async def access_granted(port, **options):
    async with access_connect(port, **options) as conn:
        report = await session_report(conn, command='identity')
        assert report['username'] == options.get('username', 'member')
        return report


class ChangeClient(velnora.SSHClient):
    def __init__(self, replacement):
        self.replacement = replacement
        self.events = []

    def password_change_requested(self, prompt, lang):
        self.events.append(('request', prompt, lang))
        return 'old-secret', self.replacement

    def password_changed(self):
        self.events.append(('accepted',))

    def password_change_failed(self):
        self.events.append(('rejected',))


class InteractiveClient(velnora.SSHClient):
    def __init__(self, answers):
        self.answers = iter(answers)
        self.requested = False
        self.challenges = []

    def kbdint_auth_requested(self):
        if self.requested:
            return None
        self.requested = True
        return ''

    def kbdint_challenge_received(self, name, instructions, lang, prompts):
        self.challenges.append((name, instructions, lang, prompts))
        return next(self.answers)


def independent_invalid_signature(port, accepted, unrelated):
    """Offer an authorized public identity but sign with another real key."""
    import io
    import socket
    import sys
    import tempfile
    import zipfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as directory:
        for name in ('F06_paramiko.whl', 'F06_pynacl.whl'):
            with zipfile.ZipFile(Path(__file__).with_name(name)) as archive:
                archive.extractall(directory)
        sys.path.insert(0, directory)
        try:
            import paramiko
            wrong = paramiko.Ed25519Key.from_private_key(io.StringIO(
                unrelated.export_private_key().decode()))
            class IncorrectProof(paramiko.Ed25519Key):
                def sign_ssh_data(self, data, algorithm=None):
                    return wrong.sign_ssh_data(data, algorithm)
            key = IncorrectProof.from_private_key(io.StringIO(
                accepted.export_private_key().decode()))
            with socket.create_connection(('127.0.0.1', port), timeout=10) as sock:
                with paramiko.Transport(sock) as transport:
                    transport.start_client(timeout=10)
                    try:
                        transport.auth_publickey('member', key)
                    except paramiko.AuthenticationException:
                        return
                    raise AssertionError('Authentication accepted an invalid private-key proof')
        finally:
            sys.path.remove(directory)


async def closed_attempt(port, **options):
    """Propagate login failures and close any unexpectedly granted connection."""
    async with access_connect(port, **options):
        pass


@asynccontextmanager
async def kerberos_realm(directory):
    """Provision a real isolated MIT realm with fresh forwardable credentials."""
    import asyncio
    import getpass
    import socket
    import tarfile
    from pathlib import Path
    from _helpers import environment, managed_service, run_command, temporary_environment

    tools = directory / 'tools'
    tools.mkdir()
    with tarfile.open(Path(__file__).with_name('F07_kerberos.tar.gz')) as archive:
        archive.extractall(tools, filter='data')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    realm = 'ACCEPTANCE.TEST'
    principal = getpass.getuser() + '@' + realm
    alternate = 'alternate@' + realm
    service = 'host/localhost@' + realm
    config = directory / 'krb5.conf'
    profile = directory / 'kdc.conf'
    config.write_text(
        '[libdefaults]\n default_realm = ' + realm + '\n'
        ' dns_lookup_kdc = false\n dns_lookup_realm = false\n'
        ' rdns = false\n dns_canonicalize_hostname = false\n forwardable = true\n'
        '[realms]\n ' + realm + ' = {\n kdc = 127.0.0.1:' + str(port) + '\n }\n')
    profile.write_text(
        '[kdcdefaults]\n kdc_ports = ' + str(port) + '\n kdc_tcp_ports = ' + str(port) + '\n'
        '[realms]\n ' + realm + ' = {\n database_name = ' + str(directory / 'principal') +
        '\n key_stash_file = ' + str(directory / 'stash') + '\n acl_file = ' + str(directory / 'acl') + '\n }\n'
        '[dbmodules]\n db_module_dir = ' + str(tools / 'usr/lib/x86_64-linux-gnu/krb5/plugins/kdb') + '\n')
    cache = 'FILE:' + str(directory / 'user.ccache')
    other_cache = 'FILE:' + str(directory / 'alternate.ccache')
    keytab = directory / 'service.keytab'
    env = environment({'KRB5_CONFIG': str(config), 'KRB5_KDC_PROFILE': str(profile),
                       'KRB5_KTNAME': str(keytab), 'KRB5CCNAME': cache,
                       'LD_LIBRARY_PATH': str(tools / 'usr/lib/x86_64-linux-gnu')})
    def command(name, *args, **kwargs):
        subdir = 'sbin' if name in ('kdb5_util', 'kadmin.local', 'krb5kdc') else 'bin'
        return run_command([tools / 'usr' / subdir / name, *args], env=env,
                           check=True, **kwargs)
    command('kdb5_util', 'create', '-s', '-P', 'isolated-master-secret')
    for identity in (principal, alternate, service):
        command('kadmin.local', '-q', 'addprinc -randkey ' + identity)
    command('kadmin.local', '-q', 'ktadd -k ' + str(keytab) + ' ' + service)
    client_keytab = directory / 'client.keytab'
    for identity in (principal, alternate):
        command('kadmin.local', '-q', 'ktadd -k ' + str(client_keytab) + ' ' + identity)

    async def ready(child):
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', port)
        except ConnectionRefusedError:
            return False
        writer.close()
        await writer.wait_closed()
        return True

    async with managed_service([tools / 'usr/sbin/krb5kdc', '-n'], env=env, ready=ready):
        for identity, target in ((principal, cache), (alternate, other_cache)):
            command('kinit.mit', '-f', '-k', '-t', str(client_keytab), '-c', target, identity)
        with temporary_environment({'KRB5_CONFIG': str(config), 'KRB5_KTNAME': str(keytab),
                                    'KRB5CCNAME': other_cache}):
            yield dict(principal=principal, alternate=alternate, service=service,
                       cache=cache, other_cache=other_cache, tools=tools, env=env)
