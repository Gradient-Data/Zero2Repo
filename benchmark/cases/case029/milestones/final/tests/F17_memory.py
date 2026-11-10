# feature: F17
"""Acceptance of skills, memory generation, reuse and conversation isolation."""
import io
import json
from pathlib import Path

import pytest

from _helpers import bounded, environment, run_process, run_python
from F01_helpers import RecordingModel, function_call
from F07_helpers import ApplicationSession
from F15_helpers import local_workspace, workspace_bytes
from F16_helpers import sandbox_run, shell_call, patch_call, tool_outputs, shell_output
from F17_helpers import (memory_model_pair, request_material, memory_segments,
                         assert_memory_artifacts)
from velmora import Runner, RunConfig, UserError
from velmora.sandbox import (Manifest, SandboxAgent, SandboxRunConfig, SandboxPathGrant,
                             MemoryReadConfig, MemoryLayoutConfig)
from velmora.sandbox.capabilities import (Skills, LocalDirLazySkillSource, Memory, Shell, Filesystem)
from velmora.sandbox.entries import LocalDir, GitRepo, File
from velmora.sandbox.errors import LocalDirReadError, WorkspaceReadNotFoundError
from velmora.sandbox.sandboxes.unix_local import UnixLocalSandboxClient


@pytest.mark.asyncio
async def test_f17_t01(tmp_path):
    source = tmp_path / 'skill-source'
    skill_dir = source / 'review'
    (skill_dir / 'references').mkdir(parents=True)
    body = '---\nname: review\ndescription: Check evidence before changing code\n---\nRead references/checklist.txt before review.\n'
    resource = b'Confirm the observed failure and verify the correction.\n'
    (skill_dir / 'SKILL.md').write_text(body)
    (skill_dir / 'references/checklist.txt').write_bytes(resource)
    # Git's native URL rewriting points a real clone at a real offline repository.
    for args in [('init',), ('config', 'user.email', 'skills@example.invalid'),
                 ('config', 'user.name', 'Skill author'), ('add', '.'),
                 ('commit', '-m', 'Add review skill'), ('tag', 'selected')]:
        result = run_process(['git', '-C', str(source), *args])
        assert result.returncode == 0, result.stderr
    with environment({'GIT_CONFIG_COUNT': '2',
        'GIT_CONFIG_KEY_0': f'url.{source.as_uri()}.insteadOf',
        'GIT_CONFIG_VALUE_0': 'https://skills.invalid/library.git',
        'GIT_CONFIG_KEY_1': f'url.{source.as_uri()}.insteadOf',
        'GIT_CONFIG_VALUE_1': 'https://skills.invalid/library'}):
        for mode in ('local', 'git', 'on-demand'):
            capability = (Skills(lazy_from=LocalDirLazySkillSource(source=LocalDir(src=source)))
                if mode == 'on-demand' else Skills(from_=(LocalDir(src=source) if mode == 'local'
                    else GitRepo(host='skills.invalid', repo='library', ref='selected'))))
            outputs = []
            if mode == 'on-demand':
                # Before selection only the index is exposed; the skill is not yet in the workspace.
                outputs.append([shell_call('cat .agents/review/SKILL.md', 'before-load')])
                outputs.append([function_call('load_skill', {'skill_name': 'review'}, 'load')])
            outputs.extend([[shell_call('cat .agents/review/SKILL.md', 'body'),
                             shell_call('cat .agents/review/references/checklist.txt', 'resource')], 'Ready.'])
            model = RecordingModel(*outputs)
            await sandbox_run(SandboxAgent(name='skills', model=model,
                capabilities=[capability, Shell()]), client=UnixLocalSandboxClient(),
                manifest=Manifest(extra_path_grants=(SandboxPathGrant(path=str(source)),)))
            material = request_material(model.requests[0])
            assert 'review' in material and 'Check evidence before changing code' in material
            if mode == 'on-demand':
                status, _ = shell_output(tool_outputs(model, 1)['before-load'])
                assert status != 0
            assert shell_output(tool_outputs(model)['body']) == (0, body)
            assert shell_output(tool_outputs(model)['resource']) == (0, resource.decode())
    for path, name in ((source, 'unknown'), (tmp_path / 'missing', 'review')):
        model = RecordingModel([function_call('load_skill', {'skill_name': name}, 'bad-load')])
        with pytest.raises(UserError):
            await sandbox_run(SandboxAgent(name='invalid-skill', model=model,
                capabilities=[Skills(lazy_from=LocalDirLazySkillSource(source=LocalDir(src=path)))]),
                client=UnixLocalSandboxClient(),
                manifest=Manifest(extra_path_grants=(SandboxPathGrant(path=str(path)),)))
    with pytest.raises(LocalDirReadError):
        await sandbox_run(SandboxAgent(name='missing-source', model=RecordingModel('Unreachable.'),
            capabilities=[Skills(from_=LocalDir(src=tmp_path / 'missing'))]),
            client=UnixLocalSandboxClient(), manifest=Manifest(extra_path_grants=(
                SandboxPathGrant(path=str(tmp_path / 'missing')),)))


@pytest.mark.asyncio
async def test_f17_t02():
    entries = {'memories/memory_summary.md': File(content=b'Prefer evidence from measured runs.'),
               'memories/MEMORY.md': File(content=b'Old review handbook.\n')}
    for editing in (False, True):
        outputs = [[shell_call('cat memories/MEMORY.md', 'read')]]
        if editing:
            outputs.append([patch_call('*** Begin Patch\n*** Update File: memories/MEMORY.md\n@@\n-Old review handbook.\n+Revised review handbook.\n*** End Patch', 'edit')])
        outputs.append('Memory used.')
        model = RecordingModel(*outputs)
        capabilities = [Memory(generate=None, read=MemoryReadConfig(live_update=editing),
            layout=MemoryLayoutConfig(memories_dir='memories', sessions_dir='sessions')), Shell()]
        if editing:
            capabilities.append(Filesystem())
        async with local_workspace(Manifest(entries=entries)) as session:
            result = await sandbox_run(SandboxAgent(name='reader', model=model,
                capabilities=capabilities), session=session)
            assert result.final_output == 'Memory used.'
            assert 'Prefer evidence from measured runs.' in request_material(model.requests[0])
            assert shell_output(tool_outputs(model)['read']) == (0, 'Old review handbook.\n')
            expected = b'Revised review handbook.\n' if editing else b'Old review handbook.\n'
            assert await workspace_bytes(session, 'memories/MEMORY.md') == expected
    layout = MemoryLayoutConfig(memories_dir='memories', sessions_dir='sessions')
    for capabilities in ([Memory(generate=None, read={'live_update': False}, layout=layout)],
                         [Memory(generate=None, read={'live_update': True}, layout=layout), Shell()],
                         [Memory(generate=None, read={'live_update': True}, layout=layout), Filesystem()]):
        with pytest.raises(UserError):
            await sandbox_run(SandboxAgent(name='invalid-memory', model=RecordingModel('Unreachable.'),
                capabilities=capabilities), client=UnixLocalSandboxClient())


@pytest.mark.asyncio
async def test_f17_t03():
    memory, extraction, consolidation = memory_model_pair('prefer concise reviews')
    async with local_workspace(Manifest()) as session:
        model = RecordingModel([shell_call('printf %s $((37 * 19))', 'measure')], 'Measured correction verified.')
        result = await sandbox_run(SandboxAgent(name='worker', model=model, capabilities=[memory, Shell()]),
            'For future reviews, report the measured correction.', session=session)
        assert result.final_output == 'Measured correction verified.'
        await bounded(session.aclose())
        assert extraction.requests and consolidation.requests
        material = request_material(extraction.requests[0])
        assert 'For future reviews, report the measured correction.' in material
        assert 'Measured correction verified.' in material and '703' in material
        status, extracts = shell_output(tool_outputs(consolidation)['read-extracts'])
        assert status == 0 and 'Durable preference: prefer concise reviews' in extracts
        await assert_memory_artifacts(session, memory, 'prefer concise reviews')


@pytest.mark.asyncio
async def test_f17_t04(tmp_path):
    for read_enabled in (True, False):
        memory, extraction, consolidation = memory_model_pair('persistent live preference', previous_summary='Previous live preference.')
        memory.read = MemoryReadConfig(live_update=False) if read_enabled else None
        async with local_workspace(Manifest()) as session:
            await bounded(session.mkdir(Path('memories'), parents=True))
            await bounded(session.write(Path('memories/memory_summary.md'), io.BytesIO(b'Previous live preference.\n')))
            generator = RecordingModel('New preference recorded.')
            await sandbox_run(SandboxAgent(name='generate-only', model=generator,
                capabilities=[memory, Shell()]), 'Record the new preference.', session=session)
            assert ('Previous live preference.' in request_material(generator.requests[0])) == read_enabled
            await bounded(session.aclose())
            await bounded(session.start())
            await assert_memory_artifacts(session, memory, 'persistent live preference')
            before = memory_segments(session.state.manifest.root, 'sessions')
            reader = RecordingModel([shell_call('cat memories/MEMORY.md')], 'Read live memory.')
            result = await sandbox_run(SandboxAgent(name='read-only', model=reader,
                capabilities=[Memory(generate=None, read={'live_update': False},
                    layout=MemoryLayoutConfig(memories_dir='memories', sessions_dir='sessions')), Shell()]), session=session)
            assert result.final_output == 'Read live memory.'
            assert 'Summary: persistent live preference' in request_material(reader.requests[0])
            assert shell_output(tool_outputs(reader)['shell']) == (0, 'Handbook: persistent live preference\n')
            assert memory_segments(session.state.manifest.root, 'sessions') == before
            await bounded(session.aclose())
            assert len(extraction.requests) == 1
    async with local_workspace(Manifest()) as fresh:
        model = RecordingModel('Fresh run completed.')
        result = await sandbox_run(SandboxAgent(name='fresh', model=model,
            capabilities=[Memory(generate=None, read={'live_update': False},
                layout=MemoryLayoutConfig(memories_dir='memories', sessions_dir='sessions')), Shell()]), session=fresh)
        assert result.final_output == 'Fresh run completed.'
        assert 'persistent live preference' not in request_material(model.requests[0])
        with pytest.raises(WorkspaceReadNotFoundError):
            await workspace_bytes(fresh, 'memories/memory_summary.md')
    code = '''
import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
from F17_helpers import memory_snapshot_process
print(json.dumps(asyncio.run(memory_snapshot_process(*sys.argv[2:]))))
'''
    for operation in ('write', 'read'):
        process = run_python(code, args=(str(Path(__file__).parent), operation,
            str(tmp_path / 'state.json'), str(tmp_path / 'snapshots')), timeout=90)
        assert process.returncode == 0, process.stderr.decode()
        observed = json.loads(process.stdout)
        if operation == 'read':
            assert 'Summary: snapshot preference' in observed['material']
            assert observed['file'] == [0, 'Handbook: snapshot preference\n']


@pytest.mark.asyncio
async def test_f17_t05(tmp_path):
    # Each condition has two distinct contributions; identities are never inferred from ordering.
    modes = ('server', 'session', 'group', 'per-run')
    for mode in modes:
        memory, extraction, consolidation = memory_model_pair(mode, conversations=2 if mode == 'per-run' else 1)
        chat = ApplicationSession('chat-identity', tmp_path / (mode + '.db'))
        try:
            async with local_workspace(Manifest()) as session:
                config = RunConfig(tracing_disabled=True, group_id=None if mode == 'per-run' else 'group-identity',
                    sandbox=SandboxRunConfig(session=session))
                if mode == 'server':
                    with pytest.raises(UserError):
                        await bounded(Runner.run(SandboxAgent(name='conflicting-owner',
                            model=RecordingModel('Must not complete.'), capabilities=[memory]),
                            'Conflicting conversation ownership.', session=chat,
                            conversation_id='server-identity', run_config=config))
                kwargs = {'conversation_id': 'server-identity'} if mode == 'server' else {}
                if mode in ('session',):
                    kwargs['session'] = chat
                for contribution in ('First contribution: use measured evidence.', 'Second contribution: preserve the correction.'):
                    model = RecordingModel('Contribution retained.')
                    result = await bounded(Runner.run(SandboxAgent(name='worker', model=model,
                        capabilities=[memory]), contribution, run_config=config, **kwargs))
                    assert result.final_output == 'Contribution retained.'
                records = memory_segments(session.state.manifest.root, memory.layout.sessions_dir)
                if mode == 'per-run':
                    assert len(records) == 2
                    assert all(len(segments) == 1 for segments in records.values())
                else:
                    expected = {'server': 'server-identity', 'session': 'chat-identity', 'group': 'group-identity'}[mode]
                    assert set(records) == {expected}
                    assert len(records[expected]) == 2
                segments = [segment for group in records.values() for segment in group]
                assert {item['content'] for segment in segments for item in segment['input']} == {
                    'First contribution: use measured evidence.', 'Second contribution: preserve the correction.'}
                await bounded(session.aclose())
                materials = [request_material(request) for request in extraction.requests]
                if mode == 'per-run':
                    assert len(materials) == 2
                    assert sum('First contribution: use measured evidence.' in text for text in materials) == 1
                    assert sum('Second contribution: preserve the correction.' in text for text in materials) == 1
                else:
                    assert len(materials) == 1
                    assert 'First contribution: use measured evidence.' in materials[0]
                    assert 'Second contribution: preserve the correction.' in materials[0]
                await assert_memory_artifacts(session, memory, mode)
        finally:
            chat.close()
    async with local_workspace(Manifest()) as session:
        pairs = [memory_model_pair(label, memories_dir=label + '_memory') for label in ('engineering', 'sales')]
        for label, (memory, extraction, consolidation) in zip(('engineering', 'sales'), pairs):
            for message in (label + ' first finding', label + ' second finding'):
                await bounded(Runner.run(SandboxAgent(name=label, model=RecordingModel('Finding retained.'),
                    capabilities=[memory]), message, conversation_id='shared-identity',
                    run_config=RunConfig(tracing_disabled=True, sandbox=SandboxRunConfig(session=session))))
            records = memory_segments(session.state.manifest.root, memory.layout.sessions_dir)
            assert set(records) == {'shared-identity'} and len(records['shared-identity']) == 2
        await bounded(session.aclose())
        for label, other, (memory, extraction, consolidation) in zip(
                ('engineering', 'sales'), ('sales', 'engineering'), pairs):
            material = request_material(extraction.requests[0])
            assert label + ' first finding' in material and label + ' second finding' in material
            assert other + ' first finding' not in material
            await assert_memory_artifacts(session, memory, label)
