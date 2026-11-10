# feature: F15
"""Acceptance observations of remote access to a real client SSH agent."""
import velnora
import pytest

from _helpers import bounded, run_async, run_command, temporary_environment
from F02_helpers import certificate_identity
from F03_helpers import authorized_line
from F05_helpers import local_agent, agent_material, agent_proof
from F09_helpers import observed_session, finish_session
from F15_helpers import forwarding_session


def test_forwarded_enumeration_signing_and_default(tmp_path):
    """F15.T01: both remote entries reach the selected, independently held keys."""
    async def exercise():
        selected = tmp_path / 'selected'
        other = tmp_path / 'other'
        selected.mkdir()
        other.mkdir()
        async with local_agent(selected) as (socket, env, _):
            async with local_agent(other) as (other_socket, other_env, _):
                expected = {}
                for name in ('first', 'second'):
                    path, external, blob = agent_material(selected, 'ssh-ed25519', name)
                    run_command(['ssh-add', path], env=env, check=True)
                    expected[blob] = external
                path, _, _ = agent_material(other, 'ssh-ed25519', 'decoy')
                run_command(['ssh-add', path], env=other_env, check=True)
                with temporary_environment({'SSH_AUTH_SOCK': str(other_socket)}):
                    # True follows agent_path; an explicit forwarding path overrides it.
                    for options in (
                            dict(agent_path=str(socket), agent_forwarding=True),
                            dict(agent_path=str(other_socket), agent_forwarding=str(socket))):
                        async with forwarding_session(client_options=options) as (conn, ready):
                            writer, _, _, app = await observed_session(conn, ready)
                            remote = app.channel.get_connection()
                            forwarded_path = app.channel.get_agent_path()
                            assert forwarded_path is not None
                            for entry in (remote, forwarded_path):
                                async with velnora.connect_agent(entry) as agent:
                                    keys = await bounded(agent.get_keys())
                                    assert {key.public_data for key in keys} == set(expected)
                                    for key in keys:
                                        await bounded(agent_proof(
                                            key, expected[key.public_data], 'ssh-ed25519'))
                            await finish_session(writer, app)
                    # An available agent alone must not opt a client into forwarding.
                    async with forwarding_session(client_options={
                            'agent_path': str(socket)}) as (conn, ready):
                        writer, _, _, app = await observed_session(conn, ready)
                        assert app.channel.get_agent_path() is None
                        # Refusal is the promised form; no specific code is promised.
                        with pytest.raises(velnora.ChannelOpenError):
                            async with velnora.connect_agent(app.channel.get_connection()):
                                pytest.fail('Unrequested forwarding provided agent access')
                        await finish_session(writer, app)
        return 'test_forwarded_enumeration_signing_and_default'
    assert run_async(exercise(), timeout=30) == 'test_forwarded_enumeration_signing_and_default'


def test_forwarding_permissions_unsolicited_and_unreachable(tmp_path):
    """F15.T02: policy refusals and unreachable agents have public failures."""
    async def exercise():
        async with local_agent(tmp_path) as (socket, env, _):
            path, external, blob = agent_material(tmp_path, 'ssh-ed25519', 'identity')
            run_command(['ssh-add', path], env=env, check=True)
            key, _ = certificate_identity()
            ca, _ = certificate_identity()
            # Each prohibition has the same authenticated, enabled live baseline.
            for identity_kind in ('server', 'key', 'certificate'):
                for allowed in (True, False):
                    if identity_kind == 'certificate':
                        identity = (key, ca.generate_user_certificate(
                            key, 'forwarding', principals=['member'],
                            permit_agent_forwarding=allowed))
                        text = authorized_line(ca, 'cert-authority')
                    else:
                        identity = key
                        text = authorized_line(key, 'no-agent-forwarding'
                                               if identity_kind == 'key' and not allowed else '')
                    async with forwarding_session(
                            client_options=dict(agent_path=str(socket), agent_forwarding=True),
                            authorization=velnora.import_authorized_keys(text),
                            client_keys=[identity],
                            server_forwarding=allowed if identity_kind == 'server' else True
                    ) as (conn, ready):
                        writer, _, _, app = await observed_session(conn, ready)
                        remote = app.channel.get_connection()
                        if allowed:
                            assert app.channel.get_agent_path() is not None
                            async with velnora.connect_agent(remote) as agent:
                                keys = await bounded(agent.get_keys())
                                assert [item.public_data for item in keys] == [blob]
                                await bounded(agent_proof(keys[0], external, 'ssh-ed25519'))
                        else:
                            assert app.channel.get_agent_path() is None
                            with pytest.raises(velnora.ChannelOpenError):
                                async with velnora.connect_agent(remote):
                                    pytest.fail('Prohibited forwarding provided agent access')
                        await finish_session(writer, app)
            async with forwarding_session(client_options={
                    'agent_path': str(socket)}) as (conn, ready):
                writer, _, _, app = await observed_session(conn, ready)
                # Send an unsolicited agent channel via the public channel API,
                # bypassing only the server convenience entry's local policy check.
                channel = app.channel.get_connection().create_agent_channel()
                # An unsolicited agent channel is refused; no code is promised.
                with pytest.raises(velnora.ChannelOpenError):
                    await bounded(channel.open(velnora.SSHUNIXSession))
                await finish_session(writer, app)
            async with forwarding_session(client_options=dict(
                    agent_path=None, agent_forwarding=str(tmp_path / 'unreachable.sock'))
            ) as (conn, ready):
                writer, _, _, app = await observed_session(conn, ready)
                assert app.channel.get_agent_path() is not None
                # Failed forwarded access is the promised form; no code is promised.
                with pytest.raises(velnora.ChannelOpenError):
                    async with velnora.connect_agent(app.channel.get_connection()) as agent:
                        await bounded(agent.get_keys())
                await finish_session(writer, app)
        return 'test_forwarding_permissions_unsolicited_and_unreachable'
    assert run_async(exercise(), timeout=30) == 'test_forwarding_permissions_unsolicited_and_unreachable'
