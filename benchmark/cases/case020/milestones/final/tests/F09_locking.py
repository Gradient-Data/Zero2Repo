# feature: F09
"""Acceptance coverage for dependency locking through the public CLI."""
from _helpers import read_json, write_file
from F01_helpers import cli_success, cli_rejection, named_node
from F02_helpers import recipe_client, recipe_file
from F05_helpers import dependency_recipe, dependency_graph
from F09_helpers import LOCK_CATEGORIES, lock_records, capture_lock, edit_lock


def test_capture_transitive_categories_and_preserve_selections(tmp_path):
    client = recipe_client(tmp_path)
    leaf = dependency_recipe(client, tmp_path / 'leaf', 'leaf')
    middle = dependency_recipe(client, tmp_path / 'mid', 'middle', body='    requires = "leaf/[>=1 <3]"\n')
    tool = dependency_recipe(client, tmp_path / 'tool', 'tool', body='    requires = "leaf/[>=1 <3]"\n')
    base = dependency_recipe(client, tmp_path / 'base', 'base', body='    package_type = "python-require"\n')
    reuse = dependency_recipe(client, tmp_path / 'reuse', 'reuse', body='    package_type = "python-require"\n    python_requires = "base/[>=1 <3]"\n')
    consumer = recipe_file(tmp_path / 'consumer', '''    requires = "middle/[>=1 <3]"
    tool_requires = "tool/[>=1 <3]"
    python_requires = "reuse/[>=1 <3]"
''')
    lock = capture_lock(client, consumer.parent, tmp_path / 'saved.lock')
    for category, references in [('requires', {middle, leaf}), ('build_requires', {tool, leaf}),
                                 ('python_requires', {reuse, base})]:
        assert set(lock_records(lock, category)) == references
    # Change the same-version revision and also introduce newer eligible versions.
    newer = {}
    for name in ('leaf', 'middle', 'tool', 'base', 'reuse'):
        body = '    description = "changed recipe"\n'
        if name in ('base', 'reuse'):
            body += '    package_type = "python-require"\n'
        dependency_recipe(client, tmp_path / name, name, body=body)
        newer[name] = dependency_recipe(client, tmp_path / (name + '2'), name, '2.0', body=body)
    report = dependency_graph(client, consumer.parent, '--lockfile', lock)
    for name, context, reference in [('middle', 'host', middle), ('leaf', 'host', leaf),
                                      ('tool', 'build', tool), ('leaf', 'build', leaf)]:
        assert named_node(report, name, context)['ref'] == reference
    assert set(named_node(report, 'specimen')['python_requires']) == {reuse, base}
    unlocked = dependency_graph(client, consumer.parent, '--lockfile=')
    assert named_node(unlocked, 'middle')['ref'] == newer['middle']
    assert named_node(unlocked, 'tool', 'build')['ref'] == newer['tool']
    assert set(named_node(unlocked, 'specimen')['python_requires']) == {newer['reuse']}


def test_automatic_disabled_and_explicit_lock_selection(tmp_path):
    client = recipe_client(tmp_path)
    first = dependency_recipe(client, tmp_path / 'one', 'choice', '1.0')
    consumer = recipe_file(tmp_path / 'consumer', '    requires = "choice/[>=1 <4]"\n')
    capture_lock(client, consumer.parent, consumer.parent / 'velmora.lock')
    second = dependency_recipe(client, tmp_path / 'two', 'choice', '2.0')
    other = capture_lock(client, consumer.parent, tmp_path / 'other.lock', '--lockfile=')
    third = dependency_recipe(client, tmp_path / 'three', 'choice', '3.0')
    for flags, expected in [((), first), (('--lockfile=',), third), (('--lockfile', other), second)]:
        assert named_node(dependency_graph(client, consumer.parent, *flags), 'choice')['ref'] == expected
    # Installation resolves through the same discovered and explicit locks.
    for flags, expected in [((), first), (('--lockfile', other), second)]:
        report = dependency_graph(client, consumer.parent, '--build=missing', *flags, install=True)
        assert named_node(report, 'choice')['ref'] == expected


def test_strict_explicit_revision_requires_matching_entry(tmp_path):
    client = recipe_client(tmp_path)
    old = dependency_recipe(client, tmp_path / 'dep', 'choice')
    consumer = recipe_file(tmp_path / 'consumer', f'    requires = {old!r}\n')
    lock = capture_lock(client, consumer.parent, tmp_path / 'saved.lock')
    new = dependency_recipe(client, tmp_path / 'dep', 'choice', body='    description = "new revision"\n')
    assert old != new
    assert named_node(dependency_graph(client, consumer.parent, '--lockfile', lock), 'choice')['ref'] == old
    recipe_file(consumer.parent, f'    requires = {new!r}\n')
    cli_rejection(client, 'graph', 'info', consumer.parent, '-nr', '--lockfile', lock)


def test_partial_missing_entries_explicit_revision_and_updated_lock(tmp_path):
    client = recipe_client(tmp_path)
    old = dependency_recipe(client, tmp_path / 'dep', 'choice')
    consumer = recipe_file(tmp_path / 'consumer', '    requires = "choice/[>=1 <3]"\n')
    lock = capture_lock(client, consumer.parent, tmp_path / 'saved.lock')
    dependency_recipe(client, tmp_path / 'new-version', 'choice', '2.0')
    absent = dependency_recipe(client, tmp_path / 'absent', 'added')
    reusable = dependency_recipe(client, tmp_path / 'reusable', 'reusable',
                                 body='    package_type = "python-require"\n')
    # Each kind of requirement absent from the lock is refused when strict and
    # resolved normally when partial, so the refusal is about the lock alone.
    base = '    requires = "choice/[>=1 <3]"\n'
    for declaration, read in [
            ('    requires = "choice/[>=1 <3]", "added/[>=1 <2]"\n',
             lambda graph: named_node(graph, 'added')['ref']),
            (base + '    tool_requires = "added/[>=1 <2]"\n',
             lambda graph: named_node(graph, 'added', 'build')['ref']),
            (base + '    python_requires = "reusable/[>=1 <2]"\n',
             lambda graph: next(iter(named_node(graph, 'specimen')['python_requires'])))]:
        recipe_file(consumer.parent, declaration)
        cli_rejection(client, 'graph', 'info', consumer.parent, '-nr', '--lockfile', lock)
        partial = dependency_graph(client, consumer.parent, '--lockfile', lock, '--lockfile-partial')
        assert read(partial) == (reusable if 'python_requires' in declaration else absent)
        assert named_node(partial, 'choice')['ref'] == old
    recipe_file(consumer.parent, '    requires = "choice/[>=1 <3]", "added/1.0"\n')
    cli_rejection(client, 'graph', 'info', consumer.parent, '-nr', '--lockfile', lock)
    updated = tmp_path / 'updated.lock'
    report = dependency_graph(client, consumer.parent, '--lockfile', lock, '--lockfile-partial', '--lockfile-out', updated)
    assert named_node(report, 'choice')['ref'] == old
    assert named_node(report, 'added')['ref'] == absent
    assert set(lock_records(updated, 'requires')) == {old, absent}
    new = dependency_recipe(client, tmp_path / 'dep', 'choice', body='    description = "explicit revision"\n')
    recipe_file(consumer.parent, f'    requires = {new!r}, "added/1.0"\n')
    report = dependency_graph(client, consumer.parent, '--lockfile', lock, '--lockfile-partial', '--lockfile-out', updated)
    assert named_node(report, 'choice')['ref'] == new
    assert set(lock_records(updated, 'requires')) == {old, new, absent}


def test_accumulate_merge_and_clean_configuration_locks(tmp_path):
    client = recipe_client(tmp_path)
    refs = {name: dependency_recipe(client, tmp_path / name, name) for name in ('linuxdep', 'windep')}
    tools = {name: dependency_recipe(client, tmp_path / name, name) for name in ('linuxtool', 'wintool')}
    consumer = recipe_file(tmp_path / 'consumer', '''    settings = "os"
    def requirements(self):
        self.requires("windep/1.0" if self.settings.os == "Windows" else "linuxdep/1.0")
    def build_requirements(self):
        self.tool_requires("wintool/1.0" if self.settings.os == "Windows" else "linuxtool/1.0")
''')
    linux = capture_lock(client, consumer.parent, tmp_path / 'linux.lock', '-s', 'os=Linux')
    windows = capture_lock(client, consumer.parent, tmp_path / 'windows.lock', '-s', 'os=Windows')
    accumulated = capture_lock(client, consumer.parent, tmp_path / 'all.lock', '--lockfile', linux, '-s', 'os=Windows')
    merged = tmp_path / 'merged.lock'
    cli_success(client, 'lock', 'merge', '--lockfile', linux, '--lockfile', windows, '--lockfile-out', merged)
    for path in (accumulated, merged):
        assert set(lock_records(path, 'requires')) == set(refs.values())
        assert set(lock_records(path, 'build_requires')) == set(tools.values())
        for system, name in [('Linux', 'linuxdep'), ('Windows', 'windep')]:
            report = dependency_graph(client, consumer.parent, '--lockfile', path, '-s', 'os=' + system)
            assert named_node(report, name)['ref'] == refs[name]
    # Merging retains each category of each input, including one only it records.
    sides = []
    for side in ('left', 'right'):
        sides.append(tmp_path / (side + '.lock'))
        cli_success(client, 'lock', 'add', '--lockfile=', '--lockfile-out', sides[-1], *[
            '--' + category.replace('_', '-') + '=' + side + '/1.0' for category in LOCK_CATEGORIES])
    both = tmp_path / 'both.lock'
    cli_success(client, 'lock', 'merge', '--lockfile', sides[0], '--lockfile', sides[1], '--lockfile-out', both)
    for category in LOCK_CATEGORIES:
        assert set(lock_records(both, category)) == {'left/1.0', 'right/1.0'}
    stale = edit_lock(client, 'add', merged, tmp_path / 'stale.lock', '--python-requires=unused/1.0#rev')
    assert set(lock_records(stale, 'python_requires')) == {'unused/1.0#rev'}
    clean = tmp_path / 'clean.lock'
    dependency_graph(client, consumer.parent, '--lockfile', stale, '-s', 'os=Linux', '--lockfile-clean', '--lockfile-out', clean)
    assert set(lock_records(clean, 'requires')) == {refs['linuxdep']}
    assert set(lock_records(clean, 'build_requires')) == {tools['linuxtool']}
    # A category left with no entries may be an empty array or be left out.
    assert read_json(clean).get('python_requires', []) == []


def test_add_remove_categories_independently(tmp_path):
    client = recipe_client(tmp_path)
    lock = tmp_path / 'edited.lock'
    # The same references in each category make removal isolation observable.
    args = [flag for category in LOCK_CATEGORIES for flag in
            ('--' + category.replace('_', '-') + '=shared/1.0#rev',
             '--' + category.replace('_', '-') + '=retained/2.0')]
    cli_success(client, 'lock', 'add', '--lockfile=', '--lockfile-out', lock, *args)
    for category in LOCK_CATEGORIES:
        assert set(lock_records(lock, category)) == {'shared/1.0#rev', 'retained/2.0'}
    removed = set()
    for category in LOCK_CATEGORIES:
        edit_lock(client, 'remove', lock, lock, '--' + category.replace('_', '-') + '=shared/1.0#rev')
        removed.add(category)
        for observed in LOCK_CATEGORIES:
            expected = {'retained/2.0'} if observed in removed else {'shared/1.0#rev', 'retained/2.0'}
            assert set(lock_records(lock, observed)) == expected


def test_invalid_entries_and_lock_inputs_are_reported(tmp_path):
    client = recipe_client(tmp_path)
    ref = dependency_recipe(client, tmp_path / 'dep', 'choice')
    consumer = recipe_file(tmp_path / 'consumer', '    requires = "choice/1.0"\n')
    good = capture_lock(client, consumer.parent, tmp_path / 'good.lock')
    assert named_node(dependency_graph(client, consumer.parent, '--lockfile', good), 'choice')['ref'] == ref
    for category in LOCK_CATEGORIES:
        cli_rejection(client, 'lock', 'add', '--lockfile', good,
                      '--' + category.replace('_', '-') + '=choice/[>=1 <3]',
                      '--lockfile-out', tmp_path / 'invalid.lock')
    broken = write_file(tmp_path / 'broken.lock', '{ invalid JSON')
    misshapen = write_file(tmp_path / 'misshapen.lock', '{"requires": [42]}')
    # Partial locking would accept an input read as an empty lock, so a refusal
    # here is about the input rather than about the requirement it lacks.
    for path in (broken, misshapen, tmp_path / 'unavailable.lock'):
        for partial in ((), ('--lockfile-partial',)):
            cli_rejection(client, 'graph', 'info', consumer.parent, '-nr', '--lockfile', path, *partial)


def test_highest_version_latest_recorded_revision_and_category_isolation(tmp_path):
    client = recipe_client(tmp_path)
    refs = {}
    for version in ('1.0', '2.0', '3.0', '5.0'):
        refs[version] = dependency_recipe(client, tmp_path / version, 'choice', version,
                                         body='    package_type = "python-require"\n')
    changed = dependency_recipe(client, tmp_path / '2.0', 'choice', '2.0',
                                body='    package_type = "python-require"\n    description = "new cache revision"\n')
    later = {}
    for version in ('1.0', '3.0'):
        later[version] = dependency_recipe(client, tmp_path / version, 'choice', version,
                          body='    package_type = "python-require"\n    description = "new cache revision"\n')
    # Deliberately give the older cache revision the later *recorded* timestamp.
    lock = tmp_path / 'candidates.lock'
    cli_success(client, 'lock', 'add', '--lockfile=', '--lockfile-out', lock,
                '--requires=' + refs['1.0'] + '%10', '--requires=' + changed + '%20',
                '--requires=' + refs['2.0'] + '%30', '--requires=' + refs['5.0'] + '%40',
                '--build-requires=' + refs['1.0'] + '%10',
                '--build-requires=' + refs['3.0'] + '%30',
                '--build-requires=' + later['3.0'] + '%20',
                '--python-requires=' + refs['1.0'] + '%30',
                '--python-requires=' + later['1.0'] + '%20')
    assert lock_records(lock, 'requires')[refs['2.0']] > lock_records(lock, 'requires')[changed]
    consumer = recipe_file(tmp_path / 'consumer', '''    requires = "choice/[>=1 <4]"
    tool_requires = "choice/[>=1 <4]"
    python_requires = "choice/[>=1 <4]"
''')
    report = dependency_graph(client, consumer.parent, '--lockfile', lock)
    assert named_node(report, 'choice')['ref'] == refs['2.0']
    assert named_node(report, 'choice', 'build')['ref'] == refs['3.0']
    assert set(named_node(report, 'specimen')['python_requires']) == {refs['1.0']}
    # A build tool's own requirement also reads the build category, and the highest
    # version wins in a merged lock whatever order its inputs recorded them in.
    versions = {version: dependency_recipe(client, tmp_path / ('isolated' + version), 'isolated', version)
                for version in ('1.0', '2.0', '3.0')}
    carrier = dependency_recipe(client, tmp_path / 'carrier', 'carrier', body='    requires = "isolated/[>=1 <4]"\n')
    first = tmp_path / 'first.lock'
    second = tmp_path / 'second.lock'
    cli_success(client, 'lock', 'add', '--lockfile=', '--lockfile-out', first, '--requires=' + versions['1.0'],
                '--build-requires=' + versions['2.0'], '--build-requires=' + carrier)
    cli_success(client, 'lock', 'add', '--lockfile=', '--lockfile-out', second, '--requires=' + versions['2.0'],
                '--build-requires=' + versions['3.0'])
    together = tmp_path / 'together.lock'
    cli_success(client, 'lock', 'merge', '--lockfile', first, '--lockfile', second, '--lockfile-out', together)
    isolated = recipe_file(tmp_path / 'isolated-consumer', '''    requires = "isolated/[>=1 <4]"
    tool_requires = "carrier/1.0"
''')
    report = dependency_graph(client, isolated.parent, '--lockfile', together)
    assert named_node(report, 'isolated')['ref'] == versions['2.0']
    assert named_node(report, 'isolated', 'build')['ref'] == versions['3.0']
