# feature: F13
"""Acceptance of artifact transfer, preparation, metadata and configuration packages."""
from pathlib import Path

from _helpers import read_bytes, read_json, write_file
from F01_helpers import cli_rejection, cli_success, profile_document, named_node
from F02_helpers import recipe_file
from F03_helpers import exported_reference
from F06_helpers import binary_reference
from F12_helpers import selection, selected_artifacts, node_artifact, saved_selection
from F13_helpers import (transfer_world, transfer_reader, transfer_package, transfer_path,
                         assert_transferred, upload_report, prepare_transfer, artifact_writes,
                         remote_snapshot, recipe_bundle)


def test_upload_pattern_query_list_and_recipe_only(tmp_path):
    # F13.T01
    with transfer_world(tmp_path) as (publisher, repos, traffic):
        release = transfer_package(publisher, tmp_path / 'source')
        debug = transfer_package(publisher, tmp_path / 'source', build_type='Debug')
        other = transfer_package(publisher, tmp_path / 'other', name='other')
        recipe_only = transfer_package(publisher, tmp_path / 'only', name='only')
        upload_report(publisher, 'freight/*', '-p', 'build_type=Release')
        assert selected_artifacts({'store0': remote_snapshot(publisher)}, 'store0') == {node_artifact(release)}
        local = selection(publisher, binary_reference(debug))
        saved_selection(tmp_path / 'local.json', local)
        upload_report(publisher, '-l', tmp_path / 'local.json')
        upload_report(publisher, 'oth*/*')
        upload_report(publisher, 'only/*', '--only-recipe')
        # Recipe-only applies to a saved selection that does list binaries.
        listed_recipe = transfer_package(publisher, tmp_path / 'listed', name='listed')
        saved_selection(tmp_path / 'listed.json', selection(publisher, 'listed/*#*:*#*'))
        upload_report(publisher, '-l', tmp_path / 'listed.json', '--only-recipe')
        assert recipe_bundle({'store0': remote_snapshot(publisher)}, listed_recipe)['packages'] == {}
        assert selected_artifacts({'store0': remote_snapshot(publisher)}, 'store0') == {
            node_artifact(release), node_artifact(debug), node_artifact(other)}
        reader = transfer_reader(tmp_path / 'reader', repos)
        for node in (release, debug, other):
            assert_transferred(reader, node)
        cli_success(reader, 'download', recipe_only['ref'], '-r', 'store0', '--only-recipe')
        assert read_bytes(transfer_path(reader, recipe_only['ref']) / 'recipe-data.txt') == b'only recipe material\n'
        assert recipe_bundle({'store0': remote_snapshot(publisher)}, recipe_only)['packages'] == {}


def test_upload_skip_force_and_binary_policy(tmp_path):
    # F13.T02
    with transfer_world(tmp_path) as (publisher, repos, traffic):
        node = transfer_package(publisher, tmp_path / 'source')
        upload_report(publisher, 'freight/*')
        assert any(r['path'].endswith('/velmora_package.tgz') for r in artifact_writes(traffic[0]))
        assert any(r['path'].endswith('/velmorafile.py') for r in artifact_writes(traffic[0]))
        traffic[0].clear()
        report = upload_report(publisher, 'freight/*')
        assert recipe_bundle(report, node)['upload'] is False
        assert not artifact_writes(traffic[0])
        # A new binary of a recipe revision the destination already has: each revision is
        # decided on its own, so the recipe and old binary are skipped and the new one goes.
        added = transfer_package(publisher, tmp_path / 'source', build_type='Debug')
        assert added['ref'] == node['ref']
        traffic[0].clear()
        report = upload_report(publisher, 'freight/*')
        bundle = recipe_bundle(report, node)
        assert bundle['upload'] is False
        for binary, decision in [(node, False), (added, True)]:
            assert bundle['packages'][binary['package_id']]['revisions'][binary['prev']]['upload'] is decision
        writes = artifact_writes(traffic[0])
        assert any(r['path'].endswith('/velmora_package.tgz') and added['package_id'] in r['path'] for r in writes)
        assert not any(r['path'].endswith('/velmorafile.py') or node['package_id'] in r['path'] for r in writes)
        assert_transferred(transfer_reader(tmp_path / 'added-reader', repos), added)
        traffic[0].clear()
        report = upload_report(publisher, 'freight/*', '--force')
        assert recipe_bundle(report, node)['upload'] is True
        assert any(r['path'].endswith('/velmora_package.tgz') for r in artifact_writes(traffic[0]))
        assert any(r['path'].endswith('/velmorafile.py') for r in artifact_writes(traffic[0]))
        assert_transferred(transfer_reader(tmp_path / 'reader', repos), node)
        policy = transfer_package(publisher, tmp_path / 'policy', name='policy',
                                  extra='    upload_policy = "skip"\n')
        upload_report(publisher, 'policy/*')
        assert recipe_bundle({'store0': remote_snapshot(publisher)}, policy)['packages'] == {}
        reader = transfer_reader(tmp_path / 'policy-reader', repos)
        cli_success(reader, 'download', policy['ref'], '--only-recipe', '-r', 'store0')
        assert read_bytes(transfer_path(reader, policy['ref']) / 'recipe-data.txt') == b'policy recipe material\n'


def test_checked_upload_refuses_corrupt_artifacts(tmp_path):
    # F13.T03
    with transfer_world(tmp_path) as (publisher, repos, traffic):
        good = transfer_package(publisher, tmp_path / 'good', name='good')
        upload_report(publisher, 'good/*', '--check')
        assert_transferred(transfer_reader(tmp_path / 'reader', repos), good)
        # One arm alters packaged contents, the other alters exported recipe material.
        for name, reference, damaged in [('corrupt', binary_reference, 'source.txt'),
                                         ('altered', lambda node: node['ref'], 'recipe-data.txt')]:
            corrupt = transfer_package(publisher, tmp_path / name, name=name)
            write_file(transfer_path(publisher, reference(corrupt)) / damaged, 'damaged material')
            before = remote_snapshot(publisher)
            traffic[0].clear()
            cli_rejection(publisher, 'upload', name + '/*', '-r', 'store0', '-c', '--check')
            assert remote_snapshot(publisher) == before
            assert not artifact_writes(traffic[0])


def test_download_exact_artifacts_without_build_or_dependencies_and_failures(tmp_path):
    # F13.T04
    with transfer_world(tmp_path, protected=True) as (publisher, repos, traffic):
        transfer_package(publisher, tmp_path / 'dependency', name='unavailable')
        node = transfer_package(publisher, tmp_path / 'source',
                                extra='    requires = "unavailable/1.0"\n')
        # The recipe can be transferred even when its dependency is not available.
        source = tmp_path / 'source' / 'velmorafile.py'
        write_file(source, source.read_text() + '    requires = "unavailable/9.0"\n')
        ref = exported_reference(publisher, source.parent)
        upload_report(publisher, 'freight/*#*')
        reader = transfer_reader(tmp_path / 'reader', repos)
        cli_success(reader, 'remote', 'login', 'store0', 'publisher', '-p', 'acceptance-password')
        reader.env['F13_FORBID_BUILD'] = '1'
        assert_transferred(reader, node)
        cli_success(reader, 'download', ref, '--only-recipe', '-r', 'store0')
        assert read_bytes(transfer_path(reader, ref) / 'recipe-data.txt') == b'freight recipe material\n'
        assert set(selection(reader, '*')['Local Cache']) == {'freight/1.0'}
        missing = cli_rejection(reader, 'download', 'missing/1.0', '-r', 'store0')
        assert 'missing/1.0' in missing.text('stderr')
        for index, user in enumerate((None, 'outsider')):
            denied = transfer_reader(tmp_path / f'denied-{index}', repos)
            if user:
                cli_success(denied, 'remote', 'login', 'store0', user, '-p', 'outsider-password')
            traffic[0].clear()
            cli_rejection(denied, 'download', binary_reference(node), '-r', 'store0',
                          '-cc', 'core:non_interactive=True')
            assert any(r['status'] == (403 if user else 401) for r in traffic[0])
    # The owned real service has stopped; transport errors must stay failures.
    transport = transfer_reader(tmp_path / 'transport', repos)
    cli_rejection(transport, 'download', binary_reference(node), '-r', 'store0')


def test_preparation_is_read_only_and_acquires_exported_sources(tmp_path):
    # F13.T05
    with transfer_world(tmp_path, count=2) as (publisher, repos, traffic):
        node = transfer_package(publisher, tmp_path / 'source')
        upload_report(publisher, '*')
        relay = transfer_reader(tmp_path / 'relay', repos)
        cli_success(relay, 'remote', 'login', 'store1', 'publisher', '-p', 'acceptance-password')
        cli_success(relay, 'install', '--requires=freight/1.0', '-r', 'store0')
        metadata = transfer_path(relay, node['ref'], 'metadata')
        write_file(metadata / 'notes' / 'transfer.txt', 'prepared metadata')
        traffic[1].clear()
        report = prepare_transfer(relay, tmp_path / 'prepared.json', remote='store1')
        assert recipe_bundle(report, node, 'store1')['upload'] is True
        assert not artifact_writes(traffic[1])
        assert remote_snapshot(publisher, 'store1') == {}
        assert any(r['method'] == 'GET' and 'velmora_sources.tgz' in r['path'] and r['status'] == 200
                   for r in traffic[0])
        upload_report(relay, '-l', tmp_path / 'prepared.json', remote='store1')
        reader = transfer_reader(tmp_path / 'reader', repos)
        assert_transferred(reader, node, 'store1')
        cli_success(reader, 'download', node['ref'], '--only-recipe', '--metadata=*', '-r', 'store1')
        assert read_bytes(transfer_path(reader, node['ref'], 'metadata') / 'notes' / 'transfer.txt') == b'prepared metadata'


def test_prepared_execution_has_no_recipe_or_python_recipe_side_effects(tmp_path):
    # F13.T06
    with transfer_world(tmp_path) as (publisher, repos, traffic):
        receipt = tmp_path / 'recipe-effects.txt'
        prefix = ('from pathlib import Path\n'
                  f'with Path({str(receipt)!r}).open("a") as stream:\n'
                  '    stream.write("recipe loaded\\n")\n')
        pyrecipe = recipe_file(tmp_path / 'reusable', '', name='reusable', version='1.0')
        write_file(pyrecipe, prefix + pyrecipe.read_text())
        exported_reference(publisher, pyrecipe.parent)
        node = transfer_package(publisher, tmp_path / 'source', prefix=prefix,
                                extra='    python_requires = "reusable/1.0"\n')
        prepared = tmp_path / 'prepared.json'
        prepare_transfer(publisher, prepared)
        before = read_bytes(receipt)
        assert before  # Creation/preparation really execute the instrumented recipes.
        # Establish a live baseline at the same state as each transfer arm.
        cli_success(publisher, 'graph', 'info', '--requires=freight/1.0', '-nr')
        assert len(read_bytes(receipt)) > len(before)
        write_file(receipt, before)
        traffic[0].clear()
        upload_report(publisher, '-l', prepared)
        assert read_bytes(receipt) == before
        assert any(r['path'].endswith('/velmora_package.tgz') for r in artifact_writes(traffic[0]))
        assert any(r['path'].endswith('/velmorafile.py') for r in artifact_writes(traffic[0]))
        reader = transfer_reader(tmp_path / 'reader', repos)
        assert_transferred(reader, node)
        reader.env['F13_FORBID_BUILD'] = '1'
        cli_success(reader, 'install', '--requires=freight/1.0', '-r', 'store0')


def test_prepared_decisions_survive_destination_changes(tmp_path):
    # F13.T07
    with transfer_world(tmp_path) as (publisher, repos, traffic):
        node = transfer_package(publisher, tmp_path / 'source')
        prepared = tmp_path / 'upload.json'
        prepare_transfer(publisher, prepared)
        upload_report(publisher, '*')  # Destination acquired the revision after preparation.
        traffic[0].clear()
        upload_report(publisher, '-l', prepared)
        assert any(r['path'].endswith('/velmora_package.tgz') for r in artifact_writes(traffic[0]))
        assert any(r['path'].endswith('/velmorafile.py') for r in artifact_writes(traffic[0]))
        assert_transferred(transfer_reader(tmp_path / 'reader', repos), node)
        skipped = tmp_path / 'skip.json'
        report = prepare_transfer(publisher, skipped)
        assert recipe_bundle(report, node)['upload'] is False
        cli_success(publisher, 'remove', '*', '-r', 'store0', '-c')
        assert remote_snapshot(publisher) == {}
        traffic[0].clear()
        upload_report(publisher, '-l', skipped)
        assert not artifact_writes(traffic[0])
        assert remote_snapshot(publisher) == {}


def test_prepared_selection_refuses_different_destination(tmp_path):
    # F13.T08
    with transfer_world(tmp_path, count=2) as (publisher, repos, traffic):
        node = transfer_package(publisher, tmp_path / 'source')
        prepared = tmp_path / 'prepared.json'
        prepare_transfer(publisher, prepared)
        before = [remote_snapshot(publisher, remote) for remote, _ in repos]
        for records in traffic:
            records.clear()
        cli_rejection(publisher, 'upload', '-l', prepared, '-r', 'store1', '-c')
        assert [remote_snapshot(publisher, remote) for remote, _ in repos] == before
        assert all(not artifact_writes(records) for records in traffic)
        upload_report(publisher, '-l', prepared)
        assert_transferred(transfer_reader(tmp_path / 'reader', repos), node)


def test_mixed_preparation_refused_but_local_lists_upload(tmp_path):
    # F13.T09
    with transfer_world(tmp_path) as (publisher, repos, traffic):
        first = transfer_package(publisher, tmp_path / 'first', name='first')
        second = transfer_package(publisher, tmp_path / 'second', name='second')
        report = prepare_transfer(publisher, tmp_path / 'prepared.json', 'first/*')
        plain = selection(publisher, binary_reference(second))
        report['store0'].update(plain['Local Cache'])
        saved_selection(tmp_path / 'mixed.json', report)
        traffic[0].clear()
        cli_rejection(publisher, 'upload', '-l', tmp_path / 'mixed.json', '-r', 'store0', '-c')
        assert not artifact_writes(traffic[0])
        assert remote_snapshot(publisher) == {}
        # The same mixture one level down: a prepared recipe record holding unprepared binaries.
        del report['store0']['second/1.0']
        listed = selection(publisher, 'first/*#*:*#*')['Local Cache']
        recipe_bundle(report, first)['packages'] = recipe_bundle({'store0': listed}, first)['packages']
        saved_selection(tmp_path / 'mixed-binary.json', report)
        traffic[0].clear()
        cli_rejection(publisher, 'upload', '-l', tmp_path / 'mixed-binary.json', '-r', 'store0', '-c')
        assert not artifact_writes(traffic[0])
        assert remote_snapshot(publisher) == {}
        saved_selection(tmp_path / 'plain.json', selection(publisher, '*#*:*#*'))
        upload_report(publisher, '-l', tmp_path / 'plain.json')
        reader = transfer_reader(tmp_path / 'reader', repos)
        for node in (first, second):
            assert_transferred(reader, node)


def test_metadata_transfer_preserves_identity_and_empty_selection_reports(tmp_path):
    # F13.T10
    with transfer_world(tmp_path) as (publisher, repos, traffic):
        node = transfer_package(publisher, tmp_path / 'source')
        upload_report(publisher, '*')
        before = selected_artifacts({'store0': remote_snapshot(publisher)}, 'store0')
        reader = transfer_reader(tmp_path / 'reader', repos)
        assert_transferred(reader, node)
        for reference in (node['ref'], binary_reference(node)):
            write_file(transfer_path(publisher, reference, 'metadata') / 'notes' / 'keep.txt', reference)
            write_file(transfer_path(publisher, reference, 'metadata') / 'private' / 'omit.txt', 'unselected')
        for value in ('initial metadata', 'updated metadata'):
            for reference in (node['ref'], binary_reference(node)):
                write_file(transfer_path(publisher, reference, 'metadata') / 'notes' / 'keep.txt', value + reference)
            traffic[0].clear()
            upload_report(publisher, '*', '--metadata=notes/*')
            writes = artifact_writes(traffic[0])
            assert writes
            assert all('/metadata/notes/' in r['path'] for r in writes)
            traffic[0].clear()
            cli_success(reader, 'download', binary_reference(node), '-r', 'store0', '--metadata=notes/*')
            assert not any(r['method'] == 'GET' and r['path'].endswith('/velmora_package.tgz') for r in traffic[0])
            for reference in (node['ref'], binary_reference(node)):
                folder = transfer_path(reader, reference, 'metadata')
                assert read_bytes(folder / 'notes' / 'keep.txt') == (value + reference).encode()
                assert not (folder / 'private' / 'omit.txt').exists()
            assert selected_artifacts({'store0': remote_snapshot(publisher)}, 'store0') == before
        # The download pattern selects too: metadata the server holds outside it stays there.
        upload_report(publisher, '*', '--metadata=private/*')
        cli_success(reader, 'download', binary_reference(node), '-r', 'store0', '--metadata=notes/*')
        for reference in (node['ref'], binary_reference(node)):
            assert not (transfer_path(reader, reference, 'metadata') / 'private' / 'omit.txt').exists()
        empty = saved_selection(tmp_path / 'empty.json', {'Local Cache': {}})
        traffic[0].clear()
        result = cli_success(publisher, 'upload', '-l', empty, '-r', 'store0', '-c', '--format=json')
        assert result.json('stdout') == {'store0': {}}
        assert any(line.startswith('WARN:') for line in result.text('stderr').splitlines())
        assert not artifact_writes(traffic[0])
        assert selected_artifacts({'store0': remote_snapshot(publisher)}, 'store0') == before


def test_configuration_package_activates_and_records_revision(tmp_path):
    # F13.T11
    with transfer_world(tmp_path) as (publisher, repos, traffic):
        source = recipe_file(tmp_path / 'config', '''    package_type = "configuration"
    exports_sources = "profiles/*"
    def package(self):
        from velmora.tools.files import copy
        copy(self, "*", self.source_folder, self.package_folder)
''', name='configuration', version='3.2')
        write_file(source.parent / 'profiles' / 'company', '[settings]\nos=Linux\narch=x86_64\nbuild_type=Debug\n')
        report = cli_success(publisher, 'create', source.parent, '-nr', '--format=json').json('stdout')
        node = named_node(report, 'configuration')
        upload_report(publisher, 'configuration/*')
        reader = transfer_reader(tmp_path / 'reader', repos)
        lock = tmp_path / 'configuration.lock'
        cli_success(reader, 'config', 'install-pkg', node['ref'], '--lockfile-out', lock)
        profile = profile_document(reader, '-pr:h=company')
        assert profile['host']['settings']['build_type'] == 'Debug'
        config_version = read_json(Path(reader.env['VELMORA_HOME']) / 'config_version.json')
        assert config_version['config_version'] == [node['ref']]
        # Locks may carry timestamps after the revision; compare the reference component.
        assert {ref.split('%')[0] for ref in read_json(lock)['config_requires']} == {node['ref']}
        # A newer revision of the same version is published after the lock was recorded.
        write_file(source.parent / 'profiles' / 'company', '[settings]\nos=Linux\narch=x86_64\nbuild_type=Release\n')
        newer = named_node(cli_success(publisher, 'create', source.parent, '-nr', '--format=json').json('stdout'),
                           'configuration')
        assert newer['ref'] != node['ref']
        upload_report(publisher, 'configuration/*')
        second = transfer_reader(tmp_path / 'second', repos)
        cli_success(second, 'config', 'install-pkg', 'configuration/3.2', '--lockfile', lock)
        assert profile_document(second, '-pr:h=company')['host']['settings']['build_type'] == 'Debug'
        assert read_json(Path(second.env['VELMORA_HOME']) / 'config_version.json')['config_version'] == [node['ref']]
