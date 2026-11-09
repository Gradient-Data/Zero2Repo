# feature: F15
"""Acceptance tests for selective local artifact maintenance and recovery."""
from pathlib import Path
import hashlib

from _helpers import Client, environment, read_bytes, unavailable_paths, write_file
from F01_helpers import cli_success, cli_rejection, configuration_http, install_bundle
from F02_helpers import recipe_client
from F03_helpers import recipe_repository, attach_repositories
from F06_helpers import binary_reference
from F12_helpers import selection, selected_artifacts, node_artifact
from F13_helpers import upload_report
from F15_helpers import (maintenance_package, maintenance_inventory, maintenance_content,
                         recipe_revisions, backup_source_files, prepared_download_files)


def test_locate_exact_artifacts(tmp_path):
    client = recipe_client(tmp_path / 'client')
    old = maintenance_package(client, tmp_path / 'project')
    revised = maintenance_package(client, tmp_path / 'project', payload='package middle')
    new = maintenance_package(client, tmp_path / 'project', revision='two', payload='package two')
    for node in (old, revised, new):
        for reference in (node['ref'], binary_reference(node)):
            write_file(client.cache_path(reference, folder='metadata') / 'note.bin',
                       reference.encode() + b' metadata\x00')
    for node, revision, payload in [(old, 'one', 'package one'),
                                    (revised, 'one', 'package middle'), (new, 'two', 'package two')]:
        maintenance_content(client, node, payload, revision)
        for folder in ('export_source', 'source'):
            assert read_bytes(client.cache_path(node['ref'], folder=folder) / 'source.txt') == (
                'maintained source ' + revision).encode()
        assert read_bytes(client.cache_path(binary_reference(node), folder='build') / 'built.txt') == b'built material'
        for reference in (node['ref'], binary_reference(node)):
            assert read_bytes(client.cache_path(reference, folder='metadata') / 'note.bin') == reference.encode() + b' metadata\x00'
    # Exact missing revisions must not resolve to either existing revision.
    for ref in ('maintained/1.0#' + '0' * 32,
                old['ref'] + ':' + old['package_id'] + '#' + '0' * 32):
        cli_rejection(client, 'cache', 'path', ref, '--format=json')


def test_integrity_mixed_artifacts(tmp_path):
    client = recipe_client(tmp_path / 'client')
    nodes = [maintenance_package(client, tmp_path / name, name=name) for name in ('alpha', 'middle', 'omega')]
    # The last member's damaged artifact is neither its latest package revision
    # nor its latest recipe revision, and the first member has a second binary.
    maintenance_package(client, tmp_path / 'omega', name='omega', payload='later package revision')
    maintenance_package(client, tmp_path / 'omega', name='omega', revision='two')
    second_binary = maintenance_package(client, tmp_path / 'alpha', name='alpha', build_type='Debug')
    baseline = cli_success(client, 'cache', 'check-integrity', '*', '--format=json')
    assert baseline.json('stdout') == {'Local Cache': {}}
    # Move each kind of damage from the first member to the last member. Every
    # invocation includes intact members; the JSON identifies only the damage.
    for node in (nodes[0], nodes[-1]):
        package = client.cache_path(binary_reference(node))
        recipe = client.cache_path(node['ref'])
        for target, replacement, recipe_damage in (
                (package / 'payload.txt', None, False),
                (package / 'source.txt', b'changed recorded bytes', False),
                (package / 'velmoramanifest.txt', None, False),
                (recipe / 'recipe-data.txt', b'changed recipe bytes', True),
                (recipe / 'velmoramanifest.txt', None, True),
                *(() if node is nodes[0] else (
                    (recipe / 'recipe-data.txt', None, True),
                    (client.cache_path(node['ref'], folder='export_source') / 'source.txt',
                     b'changed exported source', True)))):
            original = read_bytes(target)
            try:
                if replacement is None:
                    target.unlink()
                else:
                    target.write_bytes(replacement)
                result = cli_rejection(client, 'cache', 'check-integrity', '*', '--format=json')
                damaged = result.json('stdout')['Local Cache']
                ref, rev, pid, prev = node_artifact(node)
                assert set(damaged) == {ref}
                revisions = damaged[ref]['revisions']
                assert set(revisions) == {rev}
                if recipe_damage:
                    assert 'packages' not in revisions[rev]
                else:
                    assert set(revisions[rev]['packages']) == {pid}
                    assert set(revisions[rev]['packages'][pid]['revisions']) == {prev}
            finally:
                target.write_bytes(original)
    # Damage to the other binary of a recipe is identified as that binary.
    target = client.cache_path(binary_reference(second_binary)) / 'payload.txt'
    original = read_bytes(target)
    target.write_bytes(b'changed recorded bytes')
    damaged = cli_rejection(client, 'cache', 'check-integrity', '*', '--format=json').json('stdout')['Local Cache']
    ref, rev, pid, prev = node_artifact(second_binary)
    assert set(damaged) == {ref}
    assert set(damaged[ref]['revisions'][rev]['packages']) == {pid}
    # A selection that leaves the damaged artifact out is intact.
    assert cli_success(client, 'cache', 'check-integrity', 'middle/*',
                       '--format=json').json('stdout') == {'Local Cache': {}}
    target.write_bytes(original)
    assert cli_success(client, 'cache', 'check-integrity', '*', '--format=json').json('stdout') == {'Local Cache': {}}


def test_selective_local_and_remote_removal(tmp_path):
    client = recipe_client(tmp_path / 'client')
    with recipe_repository(tmp_path / 'server', client.env) as url:
        attach_repositories(client, [('store', url)], publish=True)
        a = maintenance_package(client, tmp_path / 'project')
        b = maintenance_package(client, tmp_path / 'project', payload='package two')
        c = maintenance_package(client, tmp_path / 'project', build_type='Debug')
        d = maintenance_package(client, tmp_path / 'project', revision='two')
        other = maintenance_package(client, tmp_path / 'other', name='unrelated')
        nodes = [a, b, c, d, other]
        expected = {node_artifact(n) for n in nodes}
        assert len(expected) == len(nodes)
        cli_success(client, 'upload', '*#*:*#*', '-r', 'store', '-c')
        for remote in (None, 'store'):
            flags = () if remote is None else ('-r', remote)
            assert maintenance_inventory(client, remote) == expected
            recipes = {(n['ref'].split('#')[0], n['ref'].split('#')[1]) for n in nodes}
            assert recipe_revisions(client, remote) == recipes
            dry = cli_success(client, 'remove', 'maintained/1.0', '--dry-run', '-c', '--format=json', *flags)
            assert set(dry.json('stdout')[remote or 'Local Cache']) == {'maintained/1.0'}
            assert maintenance_inventory(client, remote) == expected
            assert recipe_revisions(client, remote) == recipes
            remaining = set(expected)
            steps = [(binary_reference(a), [a]),
                     (b['ref'] + ':' + b['package_id'], [b]),
                     (c['ref'], [c]), ('maintained/1.0', [d])]
            for pattern, removed in steps:
                cli_success(client, 'remove', pattern, '-c', *flags)
                remaining.difference_update(node_artifact(n) for n in removed)
                assert maintenance_inventory(client, remote) == remaining
                # Binary selections retain their recipe; recipe selections remove it.
                if pattern == c['ref']:
                    recipes.discard(tuple(c['ref'].split('#')))
                elif pattern == 'maintained/1.0':
                    recipes.discard(tuple(d['ref'].split('#')))
                assert recipe_revisions(client, remote) == recipes
            if remote is not None:
                reader = recipe_client(tmp_path / 'reader')
                attach_repositories(reader, [('store', url)])
                cli_success(reader, 'download', binary_reference(other), '-r', 'store')
                maintenance_content(reader, other, 'package one')
                cli_rejection(reader, 'download', binary_reference(a), '-r', 'store')
        maintenance_content(client, other, 'package one')


def test_removal_dry_run_preserves_content(tmp_path):
    client = recipe_client(tmp_path / 'client')
    chosen = maintenance_package(client, tmp_path / 'chosen')
    other = maintenance_package(client, tmp_path / 'other', name='unrelated')
    before = maintenance_inventory(client)
    report = cli_success(client, 'remove', binary_reference(chosen), '--dry-run', '-c',
                         '--format=json').json('stdout')
    assert selected_artifacts(report) == {node_artifact(chosen)}
    assert maintenance_inventory(client) == before
    # A recipe selection identifies that recipe revision and is not deleted either.
    report = cli_success(client, 'remove', chosen['ref'], '--dry-run', '-c',
                         '--format=json').json('stdout')['Local Cache']
    ref, rev = chosen['ref'].split('#')
    assert set(report) == {ref}
    assert set(report[ref]['revisions']) == {rev}
    assert maintenance_inventory(client) == before
    for node in (chosen, other):
        maintenance_content(client, node, 'package one')
    cli_success(client, 'remove', binary_reference(chosen), '-c')
    assert maintenance_inventory(client) == {node_artifact(other)}


def test_removal_confirmation(tmp_path):
    # Each arm starts with the same materials and differs only in confirmation.
    for answer, confirmed in [('no\n', False), ('yes\n', True), (None, True)]:
        root = tmp_path / ('explicit' if answer is None else answer.strip())
        client = recipe_client(root / 'client')
        node = maintenance_package(client, root / 'project')
        client = Client(client.command, client.cwd,
                        environment(client.env, remove=('VELMORA_NON_INTERACTIVE',)))
        args = ('-c',) if answer is None else ()
        ref, rev = node['ref'].split('#')
        # A binary selection first, and then the recipe revision that retained.
        for pattern in (binary_reference(node), node['ref']):
            result = client.run('remove', pattern, '--format=json', *args,
                                stdin='' if answer is None else answer)
            assert result.returncode == 0, result
            report = result.json('stdout')['Local Cache']
            if confirmed:
                assert set(report) == {ref}
                assert set(report[ref]['revisions']) == {rev}
                assert maintenance_inventory(client) == set()
            else:
                assert report == {}
                assert maintenance_inventory(client) == {node_artifact(node)}
        assert recipe_revisions(client) == (set() if confirmed else {(ref, rev)})
        if not confirmed:
            maintenance_content(client, node, 'package one')


def test_cleanup_selected_disposable_material(tmp_path):
    client = recipe_client(tmp_path / 'client')
    install_bundle(client, tmp_path / 'backup-config', {
        'global.conf': 'core.sources:download_cache=' + str(tmp_path / 'source-backups') + '\n'})
    web = tmp_path / 'web'
    payloads = {'maintained': b'download source A', 'unrelated': b'download source B'}
    for name, payload in payloads.items():
        write_file(web / (name + '.txt'), payload)
    with configuration_http(web) as url, recipe_repository(tmp_path / 'server', client.env) as remote:
        attach_repositories(client, [('store', remote)], publish=True)
        nodes = [maintenance_package(client, tmp_path / name, name=name,
                                     url=url + '/' + name + '.txt',
                                     digest=hashlib.sha256(payload).hexdigest())
                 for name, payload in payloads.items()]
        prepared = upload_report(client, '*#*:*#*', '--dry-run', remote='store')
        downloads = [prepared_download_files(prepared, node, 'store') for node in nodes]
        assert all(paths and all(path.is_file() for path in paths) for paths in downloads)
        work = [(client.cache_path(n['ref'], folder='source'),
                 client.cache_path(binary_reference(n), folder='build')) for n in nodes]
        for source, build in work:
            assert (source / 'downloaded.txt').is_file()
            assert read_bytes(build / 'built.txt') == b'built material'
        backups = backup_source_files(client)
        assert all(payload in backups.values() for payload in payloads.values())
        # Each selector removes its own material and nothing else.
        cli_success(client, 'cache', 'clean', nodes[0]['ref'], '--source')
        assert not any(p.is_file() or p.is_symlink()
                       for p in [work[0][0], *work[0][0].rglob("*")])
        assert read_bytes(work[0][1] / 'built.txt') == b'built material'
        cli_success(client, 'cache', 'clean', nodes[0]['ref'], '--build')
        assert not any(p.is_file() or p.is_symlink()
                       for p in [work[0][1], *work[0][1].rglob("*")])
        assert read_bytes(work[1][0] / 'downloaded.txt') == payloads['unrelated']
        assert read_bytes(work[1][1] / 'built.txt') == b'built material'
        assert all(p.is_file() for paths in downloads for p in paths)
        cli_success(client, 'cache', 'clean', nodes[0]['ref'], '--download')
        assert all(not p.exists() for p in downloads[0])
        assert all(p.is_file() for p in downloads[1])
        assert backup_source_files(client) == backups
        cli_success(client, 'cache', 'clean', nodes[0]['ref'], '--backup-sources')
        after = backup_source_files(client)
        assert payloads['maintained'] not in after.values()
        assert payloads['unrelated'] in after.values()
        assert read_bytes(work[1][0] / 'downloaded.txt') == payloads['unrelated']
        assert read_bytes(work[1][1] / 'built.txt') == b'built material'
        assert all(p.is_file() for p in downloads[1])
        assert maintenance_inventory(client) == {node_artifact(n) for n in nodes}
        for node in nodes:
            maintenance_content(client, node, 'package one')
            assert read_bytes(client.cache_path(node['ref'], folder='export_source') / 'source.txt') == (
                node['name'] + ' source one').encode()


def test_save_restore_independent_home(tmp_path):
    origin = tmp_path / 'origin'
    client = recipe_client(origin / 'client')
    a = maintenance_package(client, origin / 'project')
    b = maintenance_package(client, origin / 'project', payload='second payload')
    c = maintenance_package(client, origin / 'project', revision='two', payload='third payload')
    maintenance_package(client, origin / 'excluded', name='excluded')
    nodes = [(a, 'package one', 'one'), (b, 'second payload', 'one'), (c, 'third payload', 'two')]
    expected = {node_artifact(n) for n, _, _ in nodes}
    assert len(expected) == 3
    for node, payload, revision in nodes:
        for reference, material in ((node['ref'], revision), (binary_reference(node), payload)):
            write_file(client.cache_path(reference, folder='metadata') / 'note.bin',
                       material.encode() + b' metadata\x00')
    archive = tmp_path / 'delivered.tgz'
    saved = cli_success(client, 'cache', 'save', 'maintained/*#*:*#*', '--file', archive,
                        '--format=json').json('stdout')
    assert selected_artifacts(saved) == expected
    receiver = recipe_client(tmp_path / 'receiver')
    unrelated = maintenance_package(receiver, tmp_path / 'receiver-project', name='unrelated')
    with unavailable_paths([origin]):
        for _ in range(2):
            restored = cli_success(receiver, 'cache', 'restore', archive, '--format=json').json('stdout')
            assert selected_artifacts(restored) == expected
            assert maintenance_inventory(receiver) == expected | {node_artifact(unrelated)}
            for node, payload, revision in nodes:
                maintenance_content(receiver, node, payload, revision)
                for reference, material in ((node['ref'], revision), (binary_reference(node), payload)):
                    assert read_bytes(receiver.cache_path(reference, folder='metadata') / 'note.bin') == material.encode() + b' metadata\x00'
            maintenance_content(receiver, unrelated, 'package one')
            # Consume restored recipes and binaries through the installation path.
            cli_success(receiver, 'install', '--requires=' + a['ref'], '-nr')
            cli_success(receiver, 'install', '--requires=' + c['ref'], '-nr')


def test_restore_missing_archive_and_exact_save(tmp_path):
    client = recipe_client(tmp_path / 'client')
    node = maintenance_package(client, tmp_path / 'project')
    # The selected binary is neither the latest package nor the latest recipe revision.
    maintenance_package(client, tmp_path / 'project', payload='later package revision')
    maintenance_package(client, tmp_path / 'project', revision='two', payload='later recipe revision')
    cli_rejection(client, 'cache', 'restore', tmp_path / 'missing.tgz')
    missing = '0' * 32
    for ref in ('maintained/1.0#' + missing,
                node['ref'] + ':' + node['package_id'] + '#' + missing):
        cli_rejection(client, 'cache', 'save', ref, '--file', tmp_path / 'bad.tgz', '--format=json')
    exact = tmp_path / 'exact.tgz'
    report = cli_success(client, 'cache', 'save', binary_reference(node), '--file', exact,
                         '--format=json').json('stdout')
    assert selected_artifacts(report) == {node_artifact(node)}
    receiver = recipe_client(tmp_path / 'receiver')
    cli_success(receiver, 'cache', 'restore', exact)
    assert maintenance_inventory(receiver) == {node_artifact(node)}
    maintenance_content(receiver, node, 'package one')
