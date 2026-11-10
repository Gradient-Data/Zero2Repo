# feature: F15
"""Local provisioning and public configuration/authority boundaries."""
import pytest

from _helpers import bounded
from F15_helpers import (local_workspace, workspace_bytes, workspace_command,
                         ApplicationWorkspaceClient)
from F01_helpers import RecordingModel
from F16_helpers import sandbox_run, shell_call, shell_output, tool_outputs
from velmora.sandbox import Manifest, SandboxAgent
from velmora.sandbox.entries import (
    AzureBlobMount, File, FuseMountPattern,
    InContainerMountStrategy, MountpointMountPattern,
    S3Mount,
)
from velmora.sandbox.errors import MountConfigError
from velmora.sandbox.sandboxes.docker import DockerSandboxClient, DockerSandboxClientOptions
from velmora.sandbox.sandboxes.unix_local import UnixLocalSandboxClient


@pytest.mark.asyncio
async def test_f15_t04(tmp_path):
    # A real successful workspace makes the refusal arms distinct from absence
    # of provisioning altogether. No provider API or result is replaced.
    manifest = Manifest(entries={'declared': File(content=b'backend workspace')})
    async with local_workspace(manifest) as session:
        assert await workspace_bytes(session, 'declared') == b'backend workspace'
        result = await workspace_command(session, 'cat declared')
        assert result.exit_code == 0 and result.stdout == b'backend workspace'
    # Provider-owned content proves the supplied application client was selected.
    client = ApplicationWorkspaceClient('provider-data', b'application-owned content')
    model = RecordingModel([shell_call('cat declared provider-data')], 'complete')
    result = await sandbox_run(SandboxAgent(name='application provider', model=model),
                               client=client, manifest=manifest)
    assert result.final_output == 'complete'
    assert shell_output(tool_outputs(model)['shell']) == (
        0, 'backend workspaceapplication-owned content')
    # With neither a client nor a live session nothing may run in a substitute environment.
    unprovisioned = RecordingModel([shell_call('printf substituted > substituted')], 'complete')
    with pytest.raises(Exception):
        await sandbox_run(SandboxAgent(name='no provider', model=unprovisioned), manifest=manifest)
    assert unprovisioned.requests == []
    import docker
    from requests.exceptions import ConnectionError
    connection = docker.DockerClient(
        base_url='unix://' + str(tmp_path / 'unavailable-docker.sock'), version='1.45')
    try:
        with pytest.raises(ConnectionError):
            await bounded(DockerSandboxClient(connection).create(
                manifest=manifest, options=DockerSandboxClientOptions(image='python:3')))
    finally:
        connection.close()


def test_f15_t05():
    # Validate the conflict at the public configuration boundary, before any
    # container could be started. These are not measurements of network effects.
    DockerSandboxClientOptions(image='python:3', network_mode='none')
    DockerSandboxClientOptions(image='python:3', exposed_ports=(8081,))
    with pytest.raises(ValueError):
        DockerSandboxClientOptions(image='python:3', network_mode='none', exposed_ports=(8081,))


def test_f15_t06():
    # This checks declaration compatibility only, not mounted file access.
    for factory, accepted, rejected in (
        (lambda pattern: S3Mount(bucket='application-data',
            mount_strategy=InContainerMountStrategy(pattern=pattern)),
         MountpointMountPattern, FuseMountPattern),
        (lambda pattern: AzureBlobMount(account='application', container='data',
            mount_strategy=InContainerMountStrategy(pattern=pattern)),
         FuseMountPattern, MountpointMountPattern),
    ):
        factory(accepted())
        with pytest.raises(MountConfigError):
            factory(rejected())


@pytest.mark.asyncio
async def test_f15_t07(tmp_path):
    client = UnixLocalSandboxClient()
    # Creating an unstarted session performs the real credential-boundary
    # check without executing a mount helper or contacting cloud storage.
    scoped = Manifest(root=str(tmp_path / 'scoped'), entries={
        'protected': S3Mount(bucket='bucket', access_key_id='application-key',
            secret_access_key='application-secret',
            mount_strategy=InContainerMountStrategy(pattern=MountpointMountPattern())),
        'other': S3Mount(bucket='public-bucket',
            mount_strategy=InContainerMountStrategy(pattern=MountpointMountPattern())),
    })
    with pytest.raises(MountConfigError):
        await bounded(client.create(manifest=scoped))
    wrong_mount = scoped.with_in_container_mount_credential_exposure_acknowledged('other')
    with pytest.raises(MountConfigError):
        await bounded(client.create(manifest=wrong_mount))
    acknowledged = scoped.with_in_container_mount_credential_exposure_acknowledged('protected')
    session = await bounded(client.create(manifest=acknowledged))
    payload = client.serialize_session_state(session.state)
    stored = payload['manifest']['entries']['protected']
    assert stored['access_key_id'] is None
    assert stored['secret_access_key'] is None
    restored = client.deserialize_session_state(payload)
    with pytest.raises((ValueError, MountConfigError)):
        await bounded(client.resume(restored))
    # Serializing a manifest also cannot preserve an application's approval.
    reloaded = Manifest.model_validate_json(acknowledged.model_dump_json())
    with pytest.raises(MountConfigError):
        await bounded(client.create(manifest=reloaded))

    both = Manifest(root=str(tmp_path / 'both'), entries={
        'protected': AzureBlobMount(account='account', container='container',
            account_key='application-account-key',
            mount_strategy=InContainerMountStrategy(pattern=FuseMountPattern())),
    })
    for incomplete in (both,
            both.with_in_container_mount_credential_exposure_acknowledged('protected'),
            both.with_in_container_mount_broad_credential_exposure_acknowledged('protected')):
        with pytest.raises(MountConfigError):
            await bounded(client.create(manifest=incomplete))
    complete = both.with_in_container_mount_credential_exposure_acknowledged('protected')
    complete = complete.with_in_container_mount_broad_credential_exposure_acknowledged('protected')
    session = await bounded(client.create(manifest=complete))
    payload = client.serialize_session_state(session.state)
    assert payload['manifest']['entries']['protected']['account_key'] is None
    restored = client.deserialize_session_state(payload)
    with pytest.raises((ValueError, MountConfigError)):
        await bounded(client.resume(restored))

    ambient = Manifest(root=str(tmp_path / 'ambient'), entries={
        'protected': AzureBlobMount(account='account', container='container',
            mount_strategy=InContainerMountStrategy(pattern=FuseMountPattern())),
    })
    with pytest.raises(MountConfigError):
        await bounded(client.create(manifest=ambient))
    scoped_only = ambient.with_in_container_mount_credential_exposure_acknowledged('protected')
    with pytest.raises(MountConfigError):
        await bounded(client.create(manifest=scoped_only))
    acknowledged = ambient.with_in_container_mount_broad_credential_exposure_acknowledged('protected')
    session = await bounded(client.create(manifest=acknowledged))
    restored = client.deserialize_session_state(client.serialize_session_state(session.state))
    with pytest.raises((ValueError, MountConfigError)):
        await bounded(client.resume(restored))
