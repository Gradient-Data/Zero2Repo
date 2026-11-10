# feature: F05
"""Acceptance tests using a private, real OpenSSH agent per test."""
import asyncio
import base64

import velnora
import pytest

from _helpers import run_async, run_command, temporary_environment
from F05_helpers import (local_agent, agent_material, agent_inventory, agent_proof)


def test_agent_locations_identities_and_signatures(tmp_path):
    """F05.T01: explicit/environment access and independent signing proof."""
    async def exercise():
        async with local_agent(tmp_path) as (socket, env, decision):
            expected = {}
            for algorithm, name in (('ssh-rsa', 'rsa identity'),
                                    ('ecdsa-sha2-nistp256', 'ec identity'),
                                    ('ssh-ed25519', 'ed identity')):
                path, external, blob = agent_material(tmp_path, algorithm, name)
                run_command(['ssh-add', path], env=env, check=True)
                expected[blob] = (external, algorithm, str(path))
            for explicit in (True, False):
                # An explicit selection must not depend on the advertised agent.
                advertised = str(tmp_path / 'not-advertised.sock') if explicit else str(socket)
                with temporary_environment({'SSH_AUTH_SOCK': advertised}):
                    async with velnora.connect_agent(str(socket)) if explicit else velnora.connect_agent() as agent:
                        keys = await agent.get_keys()
                        assert {key.public_data for key in keys} == set(expected)
                        for key in keys:
                            external, algorithm, comment = expected[key.public_data]
                            assert key.get_comment() == comment
                            await agent_proof(key, external, algorithm)
            with pytest.raises(OSError):
                await velnora.connect_agent(str(tmp_path / 'absent.sock'))
            with temporary_environment(remove=('SSH_AUTH_SOCK',)):
                with pytest.raises(OSError):
                    await velnora.connect_agent()
        return 'test_agent_locations_identities_and_signatures'
    assert run_async(exercise()) == 'test_agent_locations_identities_and_signatures'


def test_agent_identity_and_certificate_modifications(tmp_path):
    """F05.T02: changes reach the external agent, including certificates."""
    async def exercise():
        async with local_agent(tmp_path) as (socket, env, decision):
            ca, _, _ = agent_material(tmp_path, 'ssh-ed25519', 'issuer')
            path, external, blob = agent_material(tmp_path, 'ssh-rsa', 'subject')
            other, other_external, other_blob = agent_material(tmp_path, 'ssh-ed25519', 'other')
            run_command(['ssh-keygen', '-q', '-s', ca, '-I', 'agent-user',
                         '-n', 'member', path.with_suffix('.pub')], check=True)
            cert_path = tmp_path / 'subject-cert.pub'
            cert_blob = base64.b64decode(cert_path.read_bytes().split()[1], validate=True)
            key = velnora.read_private_key(path)
            cert = velnora.read_certificate(cert_path)
            async with velnora.connect_agent(str(socket)) as agent:
                await agent.add_keys([(key, cert), velnora.read_private_key(other)])
                expected = {blob, cert_blob, other_blob}
                assert agent_inventory(env) == expected
                keys = {key.public_data: key for key in await agent.get_keys()}
                assert set(keys) == expected
                for identity_blob in (blob, cert_blob):
                    await agent_proof(keys[identity_blob], external, 'ssh-rsa')
                await agent_proof(keys[other_blob], other_external, 'ssh-ed25519')
                await agent.remove_keys([keys[cert_blob]])
                assert agent_inventory(env) == {blob, other_blob}
                with pytest.raises(ValueError):
                    await keys[cert_blob].sign_async(b'removed certificate')
                await agent_proof(keys[blob], external, 'ssh-rsa')
                await keys[blob].remove()
                assert agent_inventory(env) == {other_blob}
                await agent_proof(keys[other_blob], other_external, 'ssh-ed25519')
                await agent.remove_all()
                assert agent_inventory(env) == set()
                assert list(await agent.get_keys()) == []
                with pytest.raises(ValueError):
                    await keys[other_blob].sign_async(b'removed identity')
        return 'test_agent_identity_and_certificate_modifications'
    assert run_async(exercise()) == 'test_agent_identity_and_certificate_modifications'


def test_agent_restrictions_and_refused_operations(tmp_path):
    """F05.T03: requested lifetime/confirmation and explicit operation failures."""
    async def exercise():
        async with local_agent(tmp_path) as (socket, env, decision):
            path, external, blob = agent_material(tmp_path, 'ssh-ed25519', 'restricted')
            other, other_external, other_blob = agent_material(tmp_path, 'ssh-ed25519', 'survivor')
            local = velnora.read_private_key(path)
            async with velnora.connect_agent(str(socket)) as agent:
                # Same agent, identity and denied confirmation decision; only the
                # requested confirmation constraint changes between these arms.
                for confirm in (False, True):
                    await agent.remove_all()
                    await agent.add_keys([local], confirm=confirm)
                    key = (await agent.get_keys())[0]
                    assert key.public_data == blob
                    if confirm:
                        with pytest.raises(ValueError):
                            await agent_proof(key, external, 'ssh-ed25519')
                        decision.write_text('0')
                    await agent_proof(key, external, 'ssh-ed25519')
                await agent.remove_all()
                await agent.add_keys([local], lifetime=2)
                await agent.add_keys([velnora.read_private_key(other)])
                keys = {key.public_data: key for key in await agent.get_keys()}
                assert set(keys) == {blob, other_blob}
                await agent_proof(keys[blob], external, 'ssh-ed25519')
                await asyncio.sleep(3)
                assert agent_inventory(env) == {other_blob}
                assert {key.public_data for key in await agent.get_keys()} == {other_blob}
                with pytest.raises(ValueError):
                    await keys[blob].sign_async(b'expired identity')
                await agent_proof(keys[other_blob], other_external, 'ssh-ed25519')
                with pytest.raises(ValueError):
                    await agent.remove_keys([keys[blob]])
                await agent.lock('modification guard')
                with pytest.raises(ValueError):
                    await agent.add_keys([local])
                with pytest.raises(ValueError):
                    await agent.remove_keys([keys[other_blob]])
                with pytest.raises(ValueError):
                    await agent.remove_all()
                await agent.unlock('modification guard')
                assert agent_inventory(env) == {other_blob}
                await agent_proof(keys[other_blob], other_external, 'ssh-ed25519')
        return 'test_agent_restrictions_and_refused_operations'
    assert run_async(exercise(), timeout=20) == 'test_agent_restrictions_and_refused_operations'


def test_agent_lock_wrong_passphrase_and_recovery(tmp_path):
    """F05.T04: live signing is protected and the correct passphrase restores it."""
    async def exercise():
        async with local_agent(tmp_path) as (socket, env, decision):
            path, external, blob = agent_material(tmp_path, 'ssh-ed25519', 'protected')
            run_command(['ssh-add', path], env=env, check=True)
            async with velnora.connect_agent(str(socket)) as agent:
                key = (await agent.get_keys())[0]
                assert key.public_data == blob
                await agent_proof(key, external, 'ssh-ed25519')
                run_command(['ssh-add', '-T', path.with_suffix('.pub')], env=env, check=True)
                await agent.lock('a caller-selected passphrase')
                probe = run_command(['ssh-add', '-T', path.with_suffix('.pub')], env=env)
                assert probe.returncode == 1, (probe.stdout, probe.stderr)
                with pytest.raises(ValueError):
                    await key.sign_async(b'locked identity')
                with pytest.raises(ValueError):
                    await agent.unlock('incorrect passphrase')
                with pytest.raises(ValueError):
                    await key.sign_async(b'still locked')
                probe = run_command(['ssh-add', '-T', path.with_suffix('.pub')], env=env)
                assert probe.returncode == 1, (probe.stdout, probe.stderr)
                await agent.unlock('a caller-selected passphrase')
                run_command(['ssh-add', '-T', path.with_suffix('.pub')], env=env, check=True)
                assert agent_inventory(env) == {blob}
                assert {item.public_data for item in await agent.get_keys()} == {blob}
                await agent_proof(key, external, 'ssh-ed25519')
        return 'test_agent_lock_wrong_passphrase_and_recovery'
    assert run_async(exercise(), timeout=20) == 'test_agent_lock_wrong_passphrase_and_recovery'
