# feature: F17
"""Application memory models and observations of real workspace artifacts."""
import json
from pathlib import Path

from _helpers import bounded, parse_jsonl
from F01_helpers import RecordingModel
from F15_helpers import workspace_bytes
from F16_helpers import sandbox_run, shell_call, patch_call, tool_outputs, shell_output
from velmora.sandbox import (Manifest, MemoryGenerateConfig, MemoryLayoutConfig,
                            SandboxAgent, LocalSnapshotSpec)
from velmora.sandbox.capabilities import Memory, Shell
from velmora.sandbox.sandboxes.unix_local import UnixLocalSandboxClient


def memory_model_pair(label, *, memories_dir='memories', conversations=1, previous_summary=None):
    """Caller-supplied extraction results and real consolidation tool operations."""
    extraction = RecordingModel(*[json.dumps({
        'rollout_slug': 'lesson', 'rollout_summary': f'Conversation lesson: {label}',
        'raw_memory': f'Durable preference: {label}',
    }) for _ in range(conversations)])
    consolidation = RecordingModel([
        shell_call(f'cat {memories_dir}/raw_memories.md', 'read-extracts')], [
        patch_call(json.dumps({'type': 'update_file',
            'path': f'{memories_dir}/MEMORY.md', 'diff': f'@@\n+Handbook: {label}\n'}), 'handbook'),
        patch_call(json.dumps({'type': 'update_file',
            'path': f'{memories_dir}/memory_summary.md', 'diff': '@@\n' + ('' if previous_summary is None else f'-{previous_summary}\n') + f'+Summary: {label}\n'}), 'summary'),
    ], 'Consolidation complete.')
    memory = Memory(read=None, layout=MemoryLayoutConfig(memories_dir=memories_dir,
        sessions_dir='sessions' if memories_dir == 'memories' else memories_dir + '_sessions'),
        generate=MemoryGenerateConfig(phase_one_model=extraction, phase_two_model=consolidation))
    return memory, extraction, consolidation


def request_material(request):
    """Read text from the public instructions and input message carriers."""
    texts = [request['instructions'] or '']
    items = request['input']
    if isinstance(items, str):
        texts.append(items)
    else:
        for item in items:
            if item.get('role') in ('user', 'assistant', 'developer', 'system'):
                content = item['content']
                if isinstance(content, str):
                    texts.append(content)
                else:
                    texts.extend(part['text'] for part in content
                                 if part['type'] in ('input_text', 'output_text'))
    return '\n'.join(texts)


def memory_segments(root, sessions_dir):
    directory = Path(root) / sessions_dir
    assert directory.is_dir(), f'Missing conversation directory: {directory}'
    return {file.stem: parse_jsonl(file.read_bytes()) for file in directory.glob('*.jsonl')}


async def assert_memory_artifacts(session, memory, label):
    directory = memory.layout.memories_dir
    assert (await workspace_bytes(session, directory + '/MEMORY.md')).decode().strip() == f'Handbook: {label}'
    summary = (await workspace_bytes(session, directory + '/memory_summary.md')).decode().strip()
    assert summary == f'Summary: {label}', repr(summary)
    root = Path(session.state.manifest.root) / directory
    raw = list((root / 'raw_memories').glob('*.md'))
    summaries = list((root / 'rollout_summaries').glob('*.md'))
    assert raw and summaries
    assert all(f'Durable preference: {label}' in path.read_text() for path in raw)
    assert all(f'Conversation lesson: {label}' in path.read_text() for path in summaries)


async def memory_snapshot_process(operation, state_path, snapshot_dir):
    """Generate and restore in distinct interpreters, sharing only persisted state."""
    client = UnixLocalSandboxClient()
    if operation == 'write':
        session = await bounded(client.create(manifest=Manifest(),
            snapshot=LocalSnapshotSpec(base_path=Path(snapshot_dir))))
        try:
            await bounded(session.start())
            memory, extraction, consolidation = memory_model_pair('snapshot preference')
            result = await sandbox_run(SandboxAgent(name='writer', capabilities=[memory],
                model=RecordingModel('Preference stored.')), 'Use diagrams for reviews.', session=session)
            assert result.final_output == 'Preference stored.'
            await bounded(session.aclose())
            await assert_memory_artifacts(session, memory, 'snapshot preference')
            Path(state_path).write_text(json.dumps(client.serialize_session_state(session.state)))
        finally:
            await bounded(session.aclose())
            await bounded(client.delete(session))
        return {'generated': True}
    assert operation == 'read'
    state = client.deserialize_session_state(json.loads(Path(state_path).read_text()))
    session = await bounded(client.create(manifest=Manifest(), snapshot=state.snapshot))
    try:
        await bounded(session.start())
        model = RecordingModel([shell_call('cat memories/MEMORY.md')], 'Read restored memory.')
        result = await sandbox_run(SandboxAgent(name='reader', model=model,
            capabilities=[Memory(generate=None, read={'live_update': False},
                layout=MemoryLayoutConfig(memories_dir='memories', sessions_dir='sessions')), Shell()]),
            'Review the next change.', session=session)
        assert result.final_output == 'Read restored memory.'
        return {'material': request_material(model.requests[0]),
                'file': shell_output(tool_outputs(model)['shell'])}
    finally:
        await bounded(session.aclose())
        await bounded(client.delete(session))
