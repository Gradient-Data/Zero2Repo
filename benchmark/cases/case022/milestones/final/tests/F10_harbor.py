# feature: F10
"""Acceptance tests for discovery and non-executing ingestion of Harbor tasks."""
from F10_helpers import harbor_source_test, harbor_task, harbor_rows
from F05_helpers import write_records
from F01_helpers import assert_invalid


@harbor_source_test
def test_nested_task_discovery_content_and_nonexecution(tmp_path):
    root = tmp_path / 'benchmark'
    marker = tmp_path / 'executed'
    expected = {}
    for relative, name, instruction in [
            ('tasks/cedar', 'botany/inspect-cedar', '# Inspect cedar\n\nKeep the notes.\n'),
            ('archive/release/tasks/elm', 'botany/inspect-elm', 'Compare the elm specimens.\n')]:
        config, _ = harbor_task(root, relative, name=name, instruction=instruction, marker=marker)
        expected[relative] = (name, instruction, config)
    write_records(root, 'ordinary.jsonl', [83, 19])
    result = harbor_rows(root)
    assert set(result) == {'test'}
    assert len(result['test']) == len(expected)
    rows = {row['location']: row for row in result['test']}
    assert set(rows) == set(expected)
    for location, (name, instruction, config) in expected.items():
        row = rows[location]
        assert row['name'] == name
        assert row['instruction'] == instruction
        assert row['config'] == config
        assert row['metadata'] == config['metadata']
    assert not marker.exists(), 'Loading task documents executed task code'


@harbor_source_test
def test_task_file_policy_and_distinct_invalid_sources(tmp_path):
    from velnora import load_dataset
    from velnora.exceptions import DataFilesNotFoundError, DatasetGenerationError

    root = tmp_path / 'valid'
    config, files = harbor_task(root, 'tasks/maple', name='botany/maple',
                               instruction='Inventory the maple leaves.\n', marker=tmp_path / 'executed')
    default = harbor_rows(root)['test']
    assert len(default) == 1
    assert set(default[0]['files']) == files
    assert len(default[0]['files']) == len(files)
    omitted = harbor_rows(root, include_files=False)['test']
    assert len(omitted) == 1
    assert omitted[0]['files'] is None
    for row in (default[0], omitted[0]):
        assert row['instruction'] == 'Inventory the maple leaves.\n'
        assert row['config'] == config
        assert row['metadata'] == config['metadata']
        assert row['location'] == 'tasks/maple'
    broken = tmp_path / 'malformed'
    harbor_task(broken, 'tasks/maple', name='botany/maple', instruction='Inspect.\n',
                marker=tmp_path / 'executed')
    (broken / 'tasks/maple/task.toml').write_text('[task\nname = "broken"\n', encoding='utf-8')
    assert_invalid(lambda: list(load_dataset(str(broken))['test']),
                   errors=(DatasetGenerationError,))
    unavailable = tmp_path / 'unavailable'
    unavailable.mkdir()
    (unavailable / 'other.toml').write_text('name = "not a task"\n', encoding='utf-8')
    assert_invalid(lambda: list(load_dataset(str(unavailable), data_files='*.toml').values()),
                   errors=(DataFilesNotFoundError,))


@harbor_source_test
def test_canary_prefix_removal_and_original_instructions(tmp_path):
    root = tmp_path / 'instructions'
    body = '# Task title\n\nUse the canary observations.\n<!-- canary inside body -->\n# canary inside body\n'
    cases = {
        'html': ('<!-- benchmark canary marker -->\n\n' + body, body),
        'hash': ('# benchmark canary marker\n\n' + body, body),
        'consecutive': ('<!-- benchmark canary marker -->\n# another canary marker\n\n\n' + body, body),
        'plain': (body, body),
        # Ordinary text naming the marker word is not a comment line.
        'text-mention': ('Feed the canary first.\n\n' + body, 'Feed the canary first.\n\n' + body),
        'ordinary-comment': ('<!-- ordinary provenance comment -->\n\n' + body,
                             '<!-- ordinary provenance comment -->\n\n' + body),
    }
    for name, (original, _) in cases.items():
        harbor_task(root, 'tasks/' + name, name=name, instruction=original,
                    marker=tmp_path / 'executed')
    stripped = harbor_rows(root)['test']
    assert len(stripped) == len(cases)
    assert {row['location']: row['instruction'] for row in stripped} == {
        'tasks/' + name: expected for name, (_, expected) in cases.items()}
    preserved = harbor_rows(root, strip_canary=False)['test']
    assert len(preserved) == len(cases)
    assert {row['location']: row['instruction'] for row in preserved} == {
        'tasks/' + name: original for name, (original, _) in cases.items()}

    # The baseline strips leading blank lines even without a comment; only the
    # original-content option has a dependable preservation promise here.
    blank_root = tmp_path / 'blank_instruction'
    harbor_task(blank_root, 'tasks/blank', name='blank', instruction='\n\n' + body,
                marker=tmp_path / 'executed')
    assert harbor_rows(blank_root, strip_canary=False)['test'][0]['instruction'] == '\n\n' + body
