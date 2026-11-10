# feature: F16
"""Acceptance of sandbox execution, persistence and authority boundaries."""
import gzip
import io
import json
import sys
from pathlib import Path

import pytest

from _helpers import bounded
from F01_helpers import RecordingModel, function_call
from F04_helpers import execution_tool
from F08_helpers import pending_calls
from F15_helpers import local_workspace, workspace_bytes, workspace_command
from F16_helpers import (sandbox_run, shell_call, patch_call, tool_outputs,
                         shell_output, raster_bytes, image_payload, snapshot_storage,
                         IMAGE_MIME)
from velmora import RunState, UserError
from velmora.sandbox import Manifest, SandboxAgent, SandboxRunConfig, SandboxPathGrant
from velmora.sandbox.capabilities import Shell, Filesystem, Compaction
from velmora.sandbox.entries import File, S3Mount, InContainerMountStrategy, MountpointMountPattern
from velmora.sandbox.errors import MountConfigError, WorkspaceReadNotFoundError
from velmora.sandbox.sandboxes.unix_local import UnixLocalSandboxClient
from velmora.sandbox.snapshot import LocalSnapshotSpec, RemoteSnapshotSpec
from velmora.sandbox.session.dependencies import Dependencies


@pytest.mark.asyncio
async def test_f16_t01(tmp_path):
    client = UnixLocalSandboxClient()
    default = Manifest(entries={'origin': File(content=b'agent default')})
    override = Manifest(entries={'origin': File(content=b'run override')})
    for selected, expected in ((None, 'agent default'), (override, 'run override')):
        model = RecordingModel([shell_call('cat origin')], 'done')
        await sandbox_run(SandboxAgent(name='workspace', model=model, default_manifest=default),
                          client=client, manifest=selected)
        assert shell_output(tool_outputs(model)['shell']) == (0, expected)
    async with local_workspace(Manifest(entries={'origin': File(content=b'explicit state')})) as saved:
        async with local_workspace(Manifest(entries={'origin': File(content=b'caller live')})) as live:
            model = RecordingModel([shell_call('cat origin')], 'done')
            await sandbox_run(SandboxAgent(name='workspace', model=model, default_manifest=default),
                              client=client, session=live, session_state=saved.state, manifest=override)
            assert shell_output(tool_outputs(model)['shell']) == (0, 'caller live')
        model = RecordingModel([shell_call('cat origin')], 'done')
        await sandbox_run(SandboxAgent(name='workspace', model=model, default_manifest=default),
                          client=client, session_state=saved.state, manifest=override)
        assert shell_output(tool_outputs(model)['shell']) == (0, 'explicit state')
    # Pause through a real application approval so the checkpoint carries workspace state.
    effects = []
    approval = execution_tool(effects, needs_approval=True)
    model = RecordingModel([shell_call('printf checkpoint > origin')],
                           [function_call('record', {'value': 'continued'}, 'approval')],
                           [shell_call('cat origin', 'read-restored')], 'done')
    agent = SandboxAgent(name='checkpoint', model=model, tools=[approval], default_manifest=default)
    paused = await sandbox_run(agent, client=client,
                               snapshot=LocalSnapshotSpec(base_path=tmp_path / 'snapshots'))
    state = await RunState.from_json(agent, paused.to_state().to_json())
    assert set(pending_calls(state)) == {'approval'}
    state.approve(pending_calls(state)['approval'])
    async with local_workspace(Manifest(entries={'origin': File(content=b'lower priority')})) as explicit:
        resumed = await sandbox_run(agent, state, client=client, session_state=explicit.state, manifest=override)
        assert resumed.final_output == 'done' and effects == ['continued']
        assert shell_output(tool_outputs(model)['read-restored']) == (0, 'checkpoint')


@pytest.mark.asyncio
async def test_f16_t02():
    history = [{'type': 'message', 'role': 'user', 'content': 'earlier conversation'},
               {'type': 'compaction', 'encrypted_content': 'received summary'},
               {'type': 'message', 'role': 'user', 'content': 'continue'}]
    for capabilities in (None, [Shell()], [Filesystem()], []):
        model = RecordingModel([shell_call('printf actual; exit 7')], 'done') if capabilities is None or capabilities and isinstance(capabilities[0], Shell) else RecordingModel('done')
        options = {} if capabilities is None else {'capabilities': capabilities}
        await sandbox_run(SandboxAgent(name='capabilities', model=model, **options), history,
                          client=UnixLocalSandboxClient())
        assert model.requests[0]['input'] == (history[1:] if capabilities is None else history)
        names = {tool.name for tool in model.requests[0]['tools']}
        if capabilities is None:
            assert {'exec_command', 'apply_patch', 'view_image'} <= names
        elif capabilities and isinstance(capabilities[0], Shell):
            assert 'exec_command' in names
            assert not {'apply_patch', 'view_image'} & names
        elif capabilities:
            assert {'apply_patch', 'view_image'} <= names
            assert not {'exec_command', 'write_stdin'} & names
        else:
            assert not {'exec_command', 'write_stdin', 'apply_patch', 'view_image'} & names
        if 'exec_command' in names:
            assert shell_output(tool_outputs(model)['shell']) == (7, 'actual')


@pytest.mark.asyncio
async def test_f16_t03():
    async with local_workspace(Manifest()) as session:
        assert session.supports_pty()
        script = 'import os,sys,termios; t=termios.tcgetattr(0); t[3] &= ~termios.ECHO; termios.tcsetattr(0,termios.TCSANOW,t); print("ready",flush=True); a=input(); print(a.upper(),flush=True); b=input(); print(a+":"+b,flush=True)'
        update = await bounded(session.pty_exec_start(sys.executable, '-u', '-c', script,
                                                      shell=False, tty=True, yield_time_s=0.25))
        process = update.process_id
        assert isinstance(process, int) and update.exit_code is None
        async def collect(update, expected, *, complete=False):
            output = update.output
            while (update.exit_code is None and
                   (complete or not output.replace(b'\r\n', b'\n').endswith(expected))):
                update = await session.pty_write_stdin(session_id=process, chars='', yield_time_s=0.25)
                assert update.process_id == process
                output += update.output
            assert output.replace(b'\r\n', b'\n') == expected
            assert update.exit_code == (0 if complete else None)

        await bounded(collect(update, b'ready\n'))
        update = await bounded(session.pty_write_stdin(session_id=process, chars='first\n', yield_time_s=0.25))
        assert update.process_id == process
        await bounded(collect(update, b'FIRST\n'))
        update = await bounded(session.pty_write_stdin(session_id=process, chars='second\n', yield_time_s=0.25))
        assert update.process_id in (None, process)
        await bounded(collect(update, b'first:second\n', complete=True))


@pytest.mark.asyncio
async def test_f16_t04():
    async with local_workspace(Manifest(entries={'change': File(content=b'first kept\nold\nlast kept\n'),
                                               'remove': File(content=b'obsolete\n')})) as session:
        patch = '*** Begin Patch\n*** Add File: added\n+new contents\n*** Update File: change\n@@\n first kept\n-old\n+replacement\n last kept\n*** Delete File: remove\n*** End Patch\n'
        model = RecordingModel([patch_call(patch)], 'done')
        result = await sandbox_run(SandboxAgent(name='editor', model=model), session=session)
        assert result.final_output == 'done'
        assert 'patch' in tool_outputs(model)
        assert (await workspace_bytes(session, 'added')).splitlines() == [b'new contents']
        assert (await workspace_bytes(session, 'change')).splitlines() == [
            b'first kept', b'replacement', b'last kept']
        with pytest.raises(WorkspaceReadNotFoundError):
            await workspace_bytes(session, 'remove')


@pytest.mark.asyncio
async def test_f16_t05():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="3" height="2"><rect width="3" height="2" fill="blue"/></svg>'
    contents = {format.lower() + '.data': raster_bytes(format)
                for format in ('PNG', 'JPEG', 'GIF', 'WEBP', 'BMP', 'TIFF')}
    # Misleading extensions: recognition must come from content, not the file name.
    contents.update({'gif-named.png': raster_bytes('GIF'), 'jpeg-named.bmp': raster_bytes('JPEG')})
    contents.update({'vector.data': svg, 'vector.svgz': gzip.compress(svg)})
    formats = {path: format for format in IMAGE_MIME for path in contents
               if path == format.lower() + '.data'}
    formats.update({'gif-named.png': 'GIF', 'jpeg-named.bmp': 'JPEG', 'vector.data': 'SVG',
                    'vector.svgz': 'SVG', 'limit.png': 'PNG'})
    png = contents['png.data']
    contents['limit.png'] = png + b'\0' * (10 * 1024 * 1024 - len(png))
    contents['large.png'] = contents['limit.png'] + b'\0'
    contents['invalid.png'] = b'This is ordinary text.'
    manifest = Manifest(entries={path: File(content=data) for path, data in contents.items()})
    async with local_workspace(manifest) as session:
        for path, expected in contents.items():
            model = RecordingModel([function_call('view_image', {'path': path}, 'image')], 'done')
            await sandbox_run(SandboxAgent(name='images', model=model), session=session)
            output = tool_outputs(model)['image']
            if path in ('large.png', 'invalid.png'):
                assert isinstance(output, str) and output
            else:
                assert image_payload(output, IMAGE_MIME[formats[path]]) == expected
        model = RecordingModel([function_call('view_image', {'path': 'missing.png'}, 'image')], 'done')
        await sandbox_run(SandboxAgent(name='images', model=model), session=session)
        output = tool_outputs(model)['image']
        assert isinstance(output, str) and output


@pytest.mark.asyncio
async def test_f16_t06():
    image = raster_bytes('PNG')
    manifest = Manifest(entries={'root': File(content=b'root contents'),
        'nested/value': File(content=b'nested contents'), 'nested/image': File(content=image)})
    async with local_workspace(manifest) as session:
        model = RecordingModel([shell_call('cat value; cat ../root')],
            [patch_call('*** Begin Patch\n*** Add File: made\n+from patch\n*** End Patch\n')],
            [function_call('view_image', {'path': 'image'}, 'image')], 'done')
        await sandbox_run(SandboxAgent(name='cwd', model=model), session=session, cwd='nested')
        assert shell_output(tool_outputs(model, 1)['shell']) == (0, 'nested contentsroot contents')
        assert (await workspace_bytes(session, 'nested/made')).splitlines() == [b'from patch']
        assert await workspace_bytes(session, 'root') == b'root contents'
        assert image_payload(tool_outputs(model)['image']) == image
        with pytest.raises(WorkspaceReadNotFoundError):
            await workspace_bytes(session, 'made')
        for cwd in ('', '/absolute', '../outside', 'nested/../nested'):
            with pytest.raises(ValueError):
                SandboxRunConfig(session=session, cwd=cwd)
        for cwd in ('absent', 'root'):
            with pytest.raises(UserError):
                await sandbox_run(SandboxAgent(name='invalid cwd', model=RecordingModel('unused')),
                                  session=session, cwd=cwd)
        assert await workspace_bytes(session, 'root') == b'root contents'


@pytest.mark.asyncio
async def test_f16_t07(tmp_path):
    with snapshot_storage(tmp_path / 'remote-store') as storage:
        for route in ('local', 'remote'):
            route_path = tmp_path / route
            route_path.mkdir()
            spec = (LocalSnapshotSpec(base_path=route_path / 'snapshots') if route == 'local'
                    else RemoteSnapshotSpec(client_dependency_key='application-storage'))
            client = UnixLocalSandboxClient(dependencies=Dependencies.with_values(
                {'application-storage': storage}))
            external = route_path / 'external'
            external.mkdir()
            (external / 'host').write_bytes(b'host only')
            manifest = Manifest(entries={'durable': File(content=b'initial'),
                'temporary': File(content=b'ephemeral initial', ephemeral=True)},
                extra_path_grants=(SandboxPathGrant(path=str(external)),))
            session = await bounded(client.create(manifest=manifest,
                snapshot=spec))
            try:
                await bounded(session.start())
                await bounded(session.write(Path('durable'), io.BytesIO(b'persisted change')))
                await bounded(session.write(Path('temporary'), io.BytesIO(b'temporary change')))
                await bounded(session.stop())
                payload = json.loads(json.dumps(client.serialize_session_state(session.state)))
                reconnect = await bounded(client.resume(client.deserialize_session_state(payload)))
                await bounded(reconnect.start())
                assert await workspace_bytes(reconnect, 'durable') == b'persisted change'
                await bounded(reconnect.aclose())
                await bounded(session.stop())
                snapshot = session.state.snapshot
                assert await bounded(snapshot.restorable(dependencies=session.dependencies))
                # The selected storage, not some substitute location, received the snapshot bytes.
                store = tmp_path / 'remote-store' if route == 'remote' else route_path / 'snapshots'
                stored = [path for path in store.rglob('*') if path.is_file()]
                assert stored and all(path.stat().st_size for path in stored), route
                fresh = await bounded(client.create(manifest=Manifest(), snapshot=snapshot))
                try:
                    await bounded(fresh.start())
                    assert await workspace_bytes(fresh, 'durable') == b'persisted change'
                    for path in ('temporary', 'host'):
                        with pytest.raises(WorkspaceReadNotFoundError):
                            await workspace_bytes(fresh, path)
                    assert (external / 'host').read_bytes() == b'host only'
                finally:
                    await bounded(fresh.aclose())
                    await bounded(client.delete(fresh))
            finally:
                await bounded(session.aclose())
                await bounded(client.delete(session))


@pytest.mark.asyncio
async def test_f16_t08(tmp_path):
    sessions = []
    def inspect_tools(tools):
        sessions.append(tools.exec_command.session)
    model = RecordingModel([shell_call('printf lasting > saved')], 'done')
    agent = SandboxAgent(name='owned', model=model, capabilities=[Shell(configure_tools=inspect_tools)])
    await sandbox_run(agent, client=UnixLocalSandboxClient(),
                      snapshot=LocalSnapshotSpec(base_path=tmp_path / 'snapshots'))
    owned = sessions.pop()
    assert not await bounded(owned.running())
    # The run-created Unix-local workspace directory was removed by the SDK's cleanup.
    assert not Path(owned.state.manifest.root).exists()
    client = UnixLocalSandboxClient()
    restored = await bounded(client.resume(owned.state))
    try:
        await bounded(restored.start())
        assert await workspace_bytes(restored, 'saved') == b'lasting'
    finally:
        await bounded(restored.aclose())
        await bounded(client.delete(restored))
    async with local_workspace(Manifest()) as live:
        model = RecordingModel([shell_call('printf still-live > saved')], 'done')
        await sandbox_run(SandboxAgent(name='caller', model=model), session=live)
        assert await bounded(live.running())
        assert await workspace_bytes(live, 'saved') == b'still-live'
        result = await workspace_command(live, 'cat saved')
        assert result.exit_code == 0 and result.stdout == b'still-live'


@pytest.mark.asyncio
async def test_f16_t09(tmp_path):
    client = UnixLocalSandboxClient()
    mount = S3Mount(bucket='application-data', access_key_id='current-key',
        secret_access_key='current-secret',
        mount_strategy=InContainerMountStrategy(pattern=MountpointMountPattern()))
    trusted = Manifest(root=str(tmp_path / 'authority'), entries={'data': mount}).with_in_container_mount_credential_exposure_acknowledged('data')
    session = await bounded(client.create(manifest=trusted))
    trusted = trusted.model_copy(update={"root": session.state.manifest.root})
    state = client.deserialize_session_state(json.loads(json.dumps(client.serialize_session_state(session.state))))
    with pytest.raises(ValueError):
        await bounded(client.resume(state))
    for manifest in (None, Manifest(), Manifest(entries={'data': mount.model_copy(update={'bucket': 'different'})})):
        with pytest.raises((ValueError, MountConfigError)):
            await sandbox_run(SandboxAgent(name='authority', model=RecordingModel('unused')),
                              client=client, session_state=state, manifest=manifest)
    rebound = state.rebind_persisted_mount_authority(trusted, provider_backend_id=client.backend_id)
    resumed = await bounded(client.resume(rebound))
    assert resumed.state.manifest.entries['data'].bucket == mount.bucket


@pytest.mark.asyncio
async def test_f16_t10():
    async with local_workspace(Manifest(entries={'kept': File(content=b'workspace remains')})) as session:
        items = [{'type': 'message', 'role': 'user', 'content': 'old context'},
                 {'type': 'compaction', 'encrypted_content': 'earlier summary'},
                 {'type': 'message', 'role': 'user', 'content': 'middle context'},
                 {'type': 'compaction', 'encrypted_content': 'latest summary'},
                 {'type': 'message', 'role': 'user', 'content': 'recent context'}]
        for explicit in (False, True):
            model = RecordingModel([shell_call('cat kept')], 'done')
            options = {'capabilities': [Shell(), Compaction()]} if explicit else {}
            await sandbox_run(SandboxAgent(name='compaction', model=model, **options),
                              items, session=session)
            assert model.requests[0]['input'] == items[3:]
            later = model.requests[1]['input']
            assert later[:2] == items[3:]
            assert shell_output(tool_outputs(model)['shell']) == (0, 'workspace remains')
            assert await workspace_bytes(session, 'kept') == b'workspace remains'
