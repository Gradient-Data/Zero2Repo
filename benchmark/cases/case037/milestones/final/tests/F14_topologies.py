# feature: F14
"""Acceptance observations for composed SSH connection topologies."""
import asyncio
import socket
import sys
from contextlib import AsyncExitStack

import velnora
import pytest

from _helpers import bounded, run_async, opened_connection
from F02_helpers import certificate_identity
from F04_helpers import config_file, session_report, report_session
from F07_helpers import AccessPolicy
from F14_helpers import routed_listener, topology_options, socket_proxy


def test_tunnels_and_required_jump_sequence(tmp_path):
    """F14.T01: each required route and target security policy is effective."""
    async def exercise():
        hosts = [certificate_identity()[0] for _ in range(3)]
        users = [certificate_identity()[0] for _ in range(3)]
        routes = [{}, {}, {}]
        async with AsyncExitStack() as stack:
            peers = [await stack.enter_async_context(routed_listener(h, u, r))
                     for h, u, r in zip(hosts, users, routes)]
            ports = [peer[0].get_port() for peer in peers]
            routes[0][('middle.invalid', ports[1])] = ('127.0.0.1', ports[1])
            routes[1][('target.invalid', ports[2])] = ('127.0.0.1', ports[2])
            first = await stack.enter_async_context(velnora.connect(
                '127.0.0.1', ports[0], **topology_options(hosts[0], users[0])))
            # The first hop has no route to the target; bypassing the middle fails.
            with pytest.raises(velnora.ChannelOpenError):
                async with velnora.connect('target.invalid', ports[2],
                        **topology_options(hosts[2], users[2], tunnel=first)):
                    pass
            middle = await stack.enter_async_context(first.connect_ssh(
                'middle.invalid', ports[1], **topology_options(hosts[1], users[1])))
            async with velnora.connect('target.invalid', ports[2],
                    **topology_options(hosts[2], users[2], tunnel=middle)) as target:
                assert target.get_server_host_key() == hosts[2].convert_to_public()
                report = await session_report(target, command='target-session')
                assert report['command'] == 'target-session'
                assert report['username'] == 'member'
            for host, user, error in [
                    (hosts[0], users[2], velnora.HostKeyNotVerifiable),
                    (hosts[2], users[0], velnora.PermissionDenied)]:
                with pytest.raises(error):
                    async with velnora.connect('target.invalid', ports[2],
                            **topology_options(host, user, tunnel=middle)):
                        pass
            # Every automatic hop has a distinct host identity and private key.
            trust = tmp_path / 'known_hosts'
            names = ['127.0.0.1', 'middle.invalid', 'target.invalid']
            trust.write_bytes(b''.join(
                ('[' + name + ']:' + str(port) + ' ').encode() +
                host.export_public_key() for name, port, host in zip(names, ports, hosts)))
            blocks = []
            for index, (name, user) in enumerate(zip(names, users)):
                keypath = tmp_path / ('identity-' + str(index))
                user.write_private_key(keypath)
                keypath.chmod(0o600)
                blocks.append('Host ' + name + '\n User member\n IdentityFile ' +
                              str(keypath) + '\n IdentitiesOnly yes\n')
            config = config_file(tmp_path, ''.join(blocks) +
                                 'Host *\n UserKnownHostsFile ' + str(trust) + '\n')
            jumps = '127.0.0.1:' + str(ports[0]) + ',middle.invalid:' + str(ports[1])
            async def automatic():
                return await velnora.connect('target.invalid', ports[2], config=config,
                                              tunnel=jumps, agent_path=None)
            async with opened_connection(automatic()) as target:
                assert target.get_server_host_key() == hosts[2].convert_to_public()
                assert (await session_report(target, command='jump-session'))['command'] == 'jump-session'
            endpoint = routes[0].pop(('middle.invalid', ports[1]))
            with pytest.raises(velnora.ChannelOpenError):
                async with opened_connection(automatic()):
                    pass
            routes[0][('middle.invalid', ports[1])] = endpoint
            peers[1][1].key = users[2]
            with pytest.raises(velnora.PermissionDenied):
                async with opened_connection(automatic()):
                    pass
        return 'test_tunnels_and_required_jump_sequence'
    assert run_async(exercise(), timeout=60) == 'test_tunnels_and_required_jump_sequence'


def test_proxy_transport_security_and_failures(tmp_path):
    """F14.T02: a real subprocess transports authenticated SSH sessions."""
    async def exercise():
        host, _ = certificate_identity()
        user, _ = certificate_identity()
        other, _ = certificate_identity()
        async with routed_listener(host, user, {}) as (listener, _):
            command = socket_proxy(listener.get_port(), tmp_path / 'stop')
            options = topology_options(host, user, proxy_command=command)
            # This name cannot be reached directly; only the selected proxy knows the socket.
            async with velnora.connect('proxy-target.invalid', **options) as conn:
                assert conn.get_server_host_key() == host.convert_to_public()
                report = await session_report(conn, command='through-proxy')
                assert report['command'] == 'through-proxy'
                assert report['username'] == 'member'
                (tmp_path / 'stop').touch()
                await bounded(conn.wait_closed())
                assert conn.is_closed()
            (tmp_path / 'stop').unlink()
            for trusted, credential, error in [
                    (other, user, velnora.HostKeyNotVerifiable),
                    (host, other, velnora.PermissionDenied)]:
                with pytest.raises(error):
                    async with velnora.connect('proxy-target.invalid',
                            **topology_options(trusted, credential, proxy_command=command)):
                        pass
            with pytest.raises(FileNotFoundError):
                async with velnora.connect('proxy-target.invalid',
                        **topology_options(host, user, proxy_command=[str(tmp_path / 'missing')])):
                    pass
            with pytest.raises(velnora.ConnectionLost):
                async with velnora.connect('proxy-target.invalid',
                        **topology_options(host, user, proxy_command=[sys.executable, '-c', 'pass'])):
                    pass
        return 'test_proxy_transport_security_and_failures'
    assert run_async(exercise(), timeout=40) == 'test_proxy_transport_security_and_failures'


def test_reverse_roles_direct_and_tunneled():
    """F14.T03: TCP acceptors act as authenticated SSH session clients."""
    async def exercise():
        host, _ = certificate_identity()
        user, _ = certificate_identity()
        other, _ = certificate_identity()
        async with routed_listener(other, other, {}) as (jump, policy):
            async with velnora.connect('127.0.0.1', jump.get_port(),
                    **topology_options(other, other)) as tunnel:
                for tunneled in (False, True):
                    for failure in (None, 'identity', 'credential'):
                        accepted = asyncio.get_running_loop().create_future()
                        failed = asyncio.get_running_loop().create_future()
                        options = topology_options(other if failure == 'identity' else host,
                                                   other if failure == 'credential' else user)
                        async with velnora.listen_reverse(
                                '127.0.0.1', 0, **options,
                                acceptor=accepted.set_result,
                                error_handler=lambda conn, exc: failed.set_result(exc)) as listener:
                            port = listener.get_port()
                            policy.routes[('reverse.invalid', port)] = ('127.0.0.1', port)
                            kwargs = dict(config=None, server_host_keys=[host],
                                          server_factory=lambda: AccessPolicy(key=user),
                                          process_factory=report_session)
                            if tunneled:
                                kwargs['tunnel'] = tunnel
                            address = 'reverse.invalid' if tunneled else '127.0.0.1'
                            if failure:
                                expected = (velnora.HostKeyNotVerifiable if failure ==
                                            'identity' else velnora.PermissionDenied)
                                with pytest.raises((velnora.ConnectionLost, expected)):
                                    async with velnora.connect_reverse(address, port, **kwargs):
                                        pass
                                error = await bounded(failed)
                                assert isinstance(error, expected)
                            else:
                                async with velnora.connect_reverse(address, port, **kwargs) as server:
                                    client = await bounded(accepted)
                                    try:
                                        assert client.get_server_host_key() == host.convert_to_public()
                                        report = await session_report(client, command='reverse-session')
                                        assert report['username'] == 'member'
                                        assert report['command'] == 'reverse-session'
                                        assert server.get_extra_info('username') == 'member'
                                    finally:
                                        client.close()
                                        await bounded(client.wait_closed())
        return 'test_reverse_roles_direct_and_tunneled'
    assert run_async(exercise(), timeout=60) == 'test_reverse_roles_direct_and_tunneled'


def test_canonicalization_defaults_and_required_failure(tmp_path):
    """F14.T04 (partial): real local resolution and strict failure policy."""
    from F00_environment import in_hosts_view
    hosts = ('127.0.0.1 localhost\n127.0.0.1 node\n'
             '127.0.0.1 part.node.example\n127.0.0.1 deep.part.node\n')
    child = in_hosts_view(test_canonicalization_defaults_and_required_failure, tmp_path, hosts)
    if child is not None:
        assert child.returncode == 0, (child.stdout, child.stderr)
        return
    async def exercise():
        host, _ = certificate_identity()
        user, _ = certificate_identity()
        async with routed_listener(host, user, {}) as (listener, _):
            base = topology_options(host, user, family=socket.AF_INET,
                                    canonical_domains=['unavailable.invalid'])
            # Disabled by default even when domains and strict failure are configured.
            async with velnora.connect('node', listener.get_port(),
                    **dict(base, canonicalize_fallback_local=False)) as conn:
                assert (await session_report(conn, command='default-name'))['command'] == 'default-name'
                assert conn.get_extra_info('host') == 'node'
            # Failure of domain search uses ordinary local resolution by default.
            async with velnora.connect('node', listener.get_port(),
                    **dict(base, canonicalize_hostname=True)) as conn:
                assert (await session_report(conn, command='local-name'))['command'] == 'local-name'
                assert conn.get_extra_info('host') == 'node'
            with pytest.raises(OSError):
                async with velnora.connect('node', listener.get_port(),
                        **dict(base, canonicalize_hostname=True,
                               canonicalize_fallback_local=False)):
                    pass
            # A real named destination is reachable only through the later suffix.
            # No numeric-address shorthand or local fallback supplies the result.
            async with velnora.connect('part.node', listener.get_port(),
                    **dict(base, canonicalize_hostname=True,
                           canonical_domains=['unavailable.invalid', 'example'],
                           canonicalize_fallback_local=False)) as conn:
                assert conn.get_extra_info('host') == 'part.node.example'
                assert (await session_report(conn, command='canonical'))['command'] == 'canonical'
            # A name with two dots is not eligible for canonicalization, so the
            # strict failure policy does not apply and it resolves locally.
            async with velnora.connect('deep.part.node', listener.get_port(),
                    **dict(base, canonicalize_hostname=True,
                           canonicalize_fallback_local=False)) as conn:
                assert (await session_report(conn, command='two-dots'))['command'] == 'two-dots'
            proxy = socket_proxy(listener.get_port(), tmp_path / 'stop-canonical-proxy')
            async with velnora.connect('node', listener.get_port(),
                    **dict(base, proxy_command=proxy, canonicalize_fallback_local=False)) as conn:
                assert (await session_report(conn, command='proxy-default'))['command'] == 'proxy-default'
            with pytest.raises(OSError):
                async with velnora.connect('node', listener.get_port(),
                        **dict(base, proxy_command=proxy, canonicalize_hostname=True,
                               canonicalize_fallback_local=False)):
                    pytest.fail('Proxy command unexpectedly bypassed required canonicalization')
        return 'test_canonicalization_defaults_and_required_failure'
    assert run_async(exercise(), timeout=40) == 'test_canonicalization_defaults_and_required_failure'


def test_canonicalization_threshold_and_alias_permissions(tmp_path):
    """Both name-pattern sides and the selected dot threshold affect host trust."""
    from F00_environment import in_hosts_view
    from F03_helpers import host_line
    hosts = ('127.0.0.1 localhost\n127.0.0.1 canonical.example part.node.example\n'
             '127.0.0.1 part.node\n')
    child = in_hosts_view(test_canonicalization_threshold_and_alias_permissions, tmp_path, hosts)
    if child is not None:
        assert child.returncode == 0, (child.stdout, child.stderr)
        return
    async def scenario():
        observations = []
        host, _ = certificate_identity()
        user, _ = certificate_identity()
        async with routed_listener(host, user, {}) as (listener, _):
            for threshold in (0, 1):
                for patterns, alias in [([('*', '*')], True),
                        ([('other.*', '*')], False), ([('*', 'other.*')], False)]:
                    expected = ('part.node' if threshold == 0 else
                                'canonical.example' if alias else 'part.node.example')
                    settings = topology_options(host, user, canonicalize_hostname=True,
                        canonical_domains=['example'], canonicalize_fallback_local=False,
                        canonicalize_max_dots=threshold, canonicalize_permitted_cnames=patterns)
                    settings['known_hosts'] = velnora.import_known_hosts(host_line(expected, host))
                    async with velnora.connect('part.node', listener.get_port(), **settings) as conn:
                        actual = conn.get_extra_info('host')
                        observations.append((actual, expected))
                        assert actual == expected
                        assert (await session_report(conn, command='resolved-host'))['command'] == 'resolved-host'
                    settings['known_hosts'] = velnora.import_known_hosts(host_line('unrelated.example', host))
                    with pytest.raises(velnora.HostKeyNotVerifiable):
                        async with velnora.connect('part.node', listener.get_port(), **settings):
                            pytest.fail('Canonical host trust ignored the selected public host identity')
        return observations
    observations = run_async(scenario(), timeout=60)

    assert len(observations) == 6
    assert all(actual == expected for actual, expected in observations)


if __name__ == '__main__':
    from pathlib import Path
    globals()[sys.argv[1]](Path(sys.argv[2]))
