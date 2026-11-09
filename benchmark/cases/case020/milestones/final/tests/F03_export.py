# feature: F03
"""Acceptance of recipe publication, revision identity and revision selection."""
import contextlib

from _helpers import read_bytes, write_file
from F01_helpers import cli_rejection, cli_success
from F02_helpers import recipe_client, recipe_file
from F03_helpers import (attach_repositories, exported_reference, git_command,
                         listed_revisions, publish_revision, recipe_repository,
                         revision_publisher, selected_recipe)


def test_export_identity_and_qualifiers(tmp_path):
    # F03.T01
    client = recipe_client(tmp_path)
    for user, channel in ((None, None), ('alice', 'stable'),
                          ('bob', 'stable'), ('alice', 'testing')):
        marker = repr((user, channel))
        source = recipe_file(tmp_path / 'input', f'    description = {marker!r}\n')
        flags = ('--user', user, '--channel', channel) if user else ()
        reference = exported_reference(client, source.parent, *flags)
        identity = 'specimen/2.7' + (f'@{user}/{channel}' if user else '')
        assert reference.split('#')[0] == identity
        assert reference.split('#')[1] in listed_revisions(client, identity)
    # Read after all exports so accidental identity collisions are observable.
    for user, channel in ((None, None), ('alice', 'stable'),
                          ('bob', 'stable'), ('alice', 'testing')):
        identity = 'specimen/2.7' + (f'@{user}/{channel}' if user else '')
        node = selected_recipe(client, identity, local=True)
        assert node['description'] == repr((user, channel))
        assert node['user'] == user and node['channel'] == channel
    for identity in ('    version = "2.7"\n', '    name = "incomplete"\n'):
        write_file(tmp_path / 'invalid/velmorafile.py',
                   'from velmora import VelmoraFile\nclass Recipe(VelmoraFile):\n' + identity)
        cli_rejection(client, 'export', tmp_path / 'invalid', '-nr')
    cli_rejection(client, 'cache', 'path', 'specimen/2.7@alice/stable/extra', '--format=json')
    # Export itself refuses an identity that would not form a valid reference.
    cli_rejection(client, 'export', source.parent, '-nr', '--user', 'alice', '--channel', 'stable/extra')
    recipe_file(tmp_path / 'malformed', '', name='bad/name')
    cli_rejection(client, 'export', tmp_path / 'malformed', '-nr')


def test_export_file_and_source_selection(tmp_path):
    # F03.T02
    client = recipe_client(tmp_path)
    source = recipe_file(tmp_path / 'input',
                         '    exports = "meta/*", "!meta/*.secret"\n'
                         '    exports_sources = "src/*", "!src/*.tmp"\n')
    files = {'meta/license.txt': b'license material\n', 'meta/private.secret': b'private\n',
             'src/implementation.c': b'int exported(void) { return 29; }\n',
             'src/discard.tmp': b'temporary\n', 'outside.txt': b'not selected\n'}
    for name, data in files.items():
        write_file(source.parent / name, data)
    reference = exported_reference(client, source.parent)
    exported = client.cache_path(reference)
    sources = client.cache_path(reference, folder='export_source')
    assert read_bytes(exported / 'velmorafile.py') == read_bytes(source)
    assert read_bytes(exported / 'meta/license.txt') == files['meta/license.txt']
    assert read_bytes(sources / 'src/implementation.c') == files['src/implementation.c']
    for root, absent in ((exported, ('meta/private.secret', 'src/implementation.c', 'outside.txt')),
                         (sources, ('src/discard.tmp', 'meta/license.txt', 'outside.txt'))):
        for name in absent:
            assert not (root / name).exists()


def test_content_revisions_and_retained_selection(tmp_path):
    # F03.T03
    client = recipe_client(tmp_path)
    source = recipe_file(tmp_path / 'input', '    exports_sources = "payload.txt"\n')
    write_file(source.parent / 'payload.txt', 'first source\n')
    first = exported_reference(client, source.parent)
    assert exported_reference(client, source.parent) == first
    write_file(source.parent / 'unselected.txt', 'outside the exported selection\n')
    assert exported_reference(client, source.parent) == first
    original_recipe = read_bytes(source)
    write_file(source, original_recipe + b'    description = "changed recipe"\n')
    second = exported_reference(client, source.parent)
    write_file(source.parent / 'payload.txt', 'second source\n')
    third = exported_reference(client, source.parent)
    assert len({first, second, third}) == 3
    assert set(listed_revisions(client, 'specimen/2.7')) == {r.split('#')[1] for r in (first, second, third)}
    for reference, recipe, payload in ((first, original_recipe, b'first source\n'),
                                       (second, read_bytes(source), b'first source\n'),
                                       (third, read_bytes(source), b'second source\n')):
        assert selected_recipe(client, reference, local=True)['rrev'] == reference.split('#')[1]
        assert read_bytes(client.cache_path(reference) / 'velmorafile.py') == recipe
        assert read_bytes(client.cache_path(reference, folder='export_source') / 'payload.txt') == payload
    # Declared exported files count towards the revision just as exported sources do.
    noted = recipe_file(tmp_path / 'noted', '    exports = "notes.txt"\n', name='noted')
    write_file(noted.parent / 'notes.txt', 'first note\n')
    first_note = exported_reference(client, noted.parent)
    assert exported_reference(client, noted.parent) == first_note
    write_file(noted.parent / 'notes.txt', 'second note\n')
    assert exported_reference(client, noted.parent) != first_note


def test_source_control_revision_identity_and_unavailable_commit(tmp_path):
    # F03.T04
    client = recipe_client(tmp_path)
    root = tmp_path / 'git-input'
    recipe_file(root, '    revision_mode = "scm"\n')
    git_command(root, client.env, 'init')
    git_command(root, client.env, 'add', '.')
    git_command(root, client.env, '-c', 'user.name=Acceptance', '-c',
                'user.email=acceptance@example.invalid', 'commit', '-m', 'Recipe input')
    for iteration in range(2):
        if iteration:
            # A commit outside the exported content must still change SCM identity.
            write_file(root / 'notes.txt', 'commit changes without export changes\n')
            git_command(root, client.env, 'add', '.')
            git_command(root, client.env, '-c', 'user.name=Acceptance', '-c',
                        'user.email=acceptance@example.invalid', 'commit', '-m', 'Repository input')
        commit = git_command(root, client.env, 'rev-parse', 'HEAD')
        reference = exported_reference(client, root)
        assert reference == 'specimen/2.7#' + commit
        assert selected_recipe(client, reference, local=True)['rrev'] == commit
    recipe_file(tmp_path / 'no-commit', '    revision_mode = "scm"\n')
    git_command(tmp_path / 'no-commit', client.env, 'init')
    cli_rejection(client, 'export', tmp_path / 'no-commit', '-nr')


def test_unpinned_local_and_first_remote_selection(tmp_path):
    # F03.T05
    client = recipe_client(tmp_path / 'consumer')
    with contextlib.ExitStack() as stack:
        urls = [stack.enter_context(recipe_repository(tmp_path / name, client.env))
                for name in ('first', 'second')]
        repositories = list(zip(('first', 'second'), urls))
        publisher = revision_publisher(tmp_path / 'publisher', repositories)
        old = publish_revision(publisher, tmp_path / 'input', 'old first remote', 'first')
        newer = publish_revision(publisher, tmp_path / 'input', 'new first remote', 'first')
        latest = publish_revision(publisher, tmp_path / 'input', 'second remote newest', 'second')
        # A recipe held only by the second remote: the first remote lacking it is not the end.
        solo = recipe_file(tmp_path / 'solo-input', '', name='solo')
        solo_ref = exported_reference(publisher, solo.parent)
        cli_success(publisher, 'upload', solo_ref, '-r', 'second', '-c')
        attach_repositories(client, repositories)
        solo_node = selected_recipe(client, 'solo/2.7')
        assert solo_node['rrev'] == solo_ref.split('#')[1] and solo_node['remote'] == 'second'
        assert selected_recipe(client, 'tracked/2.7')['rrev'] == newer.split('#')[1]
        assert selected_recipe(client, old)['rrev'] == old.split('#')[1]
        local = recipe_file(tmp_path / 'local', '    description = "local only"\n', name='tracked')
        local_ref = exported_reference(client, local.parent)
        assert selected_recipe(client, 'tracked/2.7')['rrev'] == local_ref.split('#')[1]
        assert selected_recipe(client, latest)['rrev'] == latest.split('#')[1]


def test_update_compares_remote_timestamps_and_preserves_newer_local(tmp_path):
    # F03.T06
    client = recipe_client(tmp_path / 'consumer')
    initial_marker = 'exported second uploaded earlier'
    initial = recipe_file(tmp_path / 'initial-local',
                          f'    description = {initial_marker!r}\n', name='tracked')
    initial_ref = exported_reference(client, initial.parent)
    with contextlib.ExitStack() as stack:
        urls = [stack.enter_context(recipe_repository(tmp_path / name, client.env))
                for name in ('first', 'second')]
        repositories = list(zip(('first', 'second'), urls))
        publisher = revision_publisher(tmp_path / 'publisher', repositories)
        old = publish_revision(publisher, tmp_path / 'input', 'exported first uploaded last', 'first')
        new = publish_revision(publisher, tmp_path / 'input', initial_marker, 'first')
        # Upload an older content revision later, making its remote timestamp newer.
        cli_success(publisher, 'upload', old, '-r', 'second', '-c')
        old_rev, new_rev = old.split('#')[1], new.split('#')[1]
        first_times = listed_revisions(publisher, 'tracked/2.7', remote='first')
        second_times = listed_revisions(publisher, 'tracked/2.7', remote='second')
        assert second_times[old_rev]['timestamp'] > first_times[new_rev]['timestamp']
        attach_repositories(client, repositories)
        assert initial_ref == new
        assert second_times[old_rev]['timestamp'] > listed_revisions(client, 'tracked/2.7')[new_rev]['timestamp']
        assert selected_recipe(client, new)['rrev'] == new_rev
        assert selected_recipe(client, 'tracked/2.7', '--update')['rrev'] == old_rev
        # The newest can equally sit on the first remote: the timestamp decides, not the position.
        third = publish_revision(publisher, tmp_path / 'input', 'published last to first', 'first')
        assert selected_recipe(client, 'tracked/2.7', '--update')['rrev'] == third.split('#')[1]
        source = recipe_file(tmp_path / 'local', '    description = "newer local content"\n', name='tracked')
        local = exported_reference(client, source.parent).split('#')[1]
        before = listed_revisions(client, 'tracked/2.7')[local]['timestamp']
        assert before > second_times[old_rev]['timestamp']
        assert selected_recipe(client, 'tracked/2.7', '--update')['rrev'] == local
        assert listed_revisions(client, 'tracked/2.7')[local]['timestamp'] == before
