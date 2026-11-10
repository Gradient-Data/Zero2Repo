# feature: F12
"""Acceptance tests for discovery, reusable selections and dependency editing."""
import time

from _helpers import read_bytes, read_json
from F01_helpers import cli_success, cli_rejection, graph_document, named_node
from F02_helpers import recipe_client, recipe_file
from F03_helpers import recipe_repository, attach_repositories, exported_reference
from F06_helpers import binary_payload, binary_reference
from F05_helpers import dependency_edge
from F12_helpers import (selection, selected_artifacts, node_artifact, saved_selection,
                         discovery_binary, export_versions,
                         dependency_report)


def test_search_sources_empty_and_errors(tmp_path):
    client = recipe_client(tmp_path / 'client')
    with recipe_repository(tmp_path / 'one', client.env) as one, \
            recipe_repository(tmp_path / 'two', client.env) as two:
        attach_repositories(client, [('one', one), ('two', two)], publish=True)
        for name, version, remote in [('parcel', '1.0', 'one'), ('parcel', '2.0', 'two'),
                                      ('other', '1.0', 'one')]:
            path = recipe_file(tmp_path / (name + version), '', name=name, version=version)
            ref = exported_reference(client, path.parent)
            cli_success(client, 'upload', ref, '-r', remote, '-c')
        assert set(selection(client, 'parcel/*')['Local Cache']) == {'parcel/1.0', 'parcel/2.0'}
        for command in ('list', 'search'):
            found = selection(client, 'parcel/*', '-r', '*', operation=command)
            assert set(found) == {'one', 'two'}
            assert set(found['one']) == {'parcel/1.0'}
            assert set(found['two']) == {'parcel/2.0'}
            assert selection(client, 'absent*', '-r', 'one', operation=command) == {'one': {}}
        cli_success(client, 'remote', 'add', 'broken', one + '/unavailable')
        for command in ('list', 'search'):
            failed = selection(client, 'parcel/*', '-r', 'broken', operation=command)
            assert set(failed) == {'broken'}
            assert isinstance(failed['broken']['error'], str)
            assert failed['broken']['error']
        assert selection(client, 'absent*') == {'Local Cache': {}}


def test_listing_identity_patterns_and_latest(tmp_path):
    client = recipe_client(tmp_path / 'client')
    first = discovery_binary(client, tmp_path / 'recipe')
    revised_package = discovery_binary(client, tmp_path / 'recipe', material='changed')
    second = discovery_binary(client, tmp_path / 'recipe', marker='second')
    debug = discovery_binary(client, tmp_path / 'recipe', marker='second', build_type='Debug', flavor='rich')
    other = discovery_binary(client, tmp_path / 'v2', version='2.0')
    nodes = [first, revised_package, second, debug, other]
    expected = {node_artifact(n) for n in nodes}
    assert first['prev'] != revised_package['prev']
    assert first['ref'] != second['ref']
    report = selection(client, 'parcel/*#*:*#*')
    assert selected_artifacts(report) == expected
    for node in nodes:
        ref, rrev, pid, prev = node_artifact(node)
        exact = selection(client, f'{ref}#{rrev}:{pid}#{prev}')
        assert selected_artifacts(exact) == {node_artifact(node)}
        info = report['Local Cache'][ref]['revisions'][rrev]['packages'][pid]['info']
        assert info['settings'] == node['settings']
        assert info['options'] == node['options']
    assert selected_artifacts(selection(client, 'parcel/1.0#latest:*#latest')) == {
        node_artifact(second), node_artifact(debug)}
    assert selected_artifacts(selection(client, first['ref'] + ':*#latest')) == {node_artifact(revised_package)}
    assert set(selection(client, 'parcel/*')['Local Cache']) == {'parcel/1.0', 'parcel/2.0'}
    missing = selection(client, 'parcel/8.0#latest')['Local Cache']
    assert isinstance(missing['error'], str)
    assert 'parcel/8.0' in missing['error']
    # Each exact layer: the absent identity is reported, not dropped or replaced by another.
    ref, rrev, pid, prev = node_artifact(first)
    absent = 'f' * 32
    for exact in (f'{ref}#{absent}', f'{ref}#{rrev}:{absent}', f'{ref}#{rrev}:{pid}#{absent}'):
        missing = selection(client, exact)['Local Cache']
        assert isinstance(missing['error'], str), exact
        assert absent in missing['error']


def test_configuration_queries(tmp_path):
    client = recipe_client(tmp_path / 'client')
    nodes = [discovery_binary(client, tmp_path / 'recipe', build_type=build, flavor=flavor)
             for build, flavor in [('Release', 'plain'), ('Release', 'rich'), ('Debug', 'plain')]]
    queries = [
        ('build_type=Release AND options.flavor=plain', {node_artifact(nodes[0])}),
        ('build_type=Debug OR options.flavor=rich', {node_artifact(nodes[1]), node_artifact(nodes[2])}),
        ('(build_type=Debug OR options.flavor=rich) AND options.flavor=plain', {node_artifact(nodes[2])}),
        # Grouping must decide these two: with the parentheses ignored, left-to-right or
        # AND-first reading changes the first, right-to-left or OR-first reading the second.
        ('options.flavor=plain AND (build_type=Debug OR options.flavor=rich)', {node_artifact(nodes[2])}),
        ('(build_type=Release AND options.flavor=rich) OR build_type=Debug',
         {node_artifact(nodes[1]), node_artifact(nodes[2])}),
        ('build_type=Debug AND options.flavor=rich', set())]
    for query, expected in queries:
        assert selected_artifacts(selection(client, 'parcel/1.0:*#*', '-p', query)) == expected
    invalid = selection(client, 'parcel/1.0:*', '-p', 'build_type=Release AND (')['Local Cache']
    assert isinstance(invalid['error'], str)
    assert 'build_type=Release AND (' in invalid['error']


def test_unused_selection_and_dependency_refresh(tmp_path):
    client = recipe_client(tmp_path / 'client')
    used = discovery_binary(client, tmp_path / 'used', name='used')
    idle = discovery_binary(client, tmp_path / 'idle', name='idle')
    created = time.monotonic()
    pattern = '*#*:*#*'
    assert selected_artifacts(selection(client, pattern, '--lru=1h')) == set()
    assert selection(client, '*#*', '--lru=1h') == {'Local Cache': {}}
    # Real elapsed time only, no cache timestamp edits. Both artifacts are at least
    # this old from here on, however slowly the judge runs the commands below.
    time.sleep(13)
    assert selected_artifacts(selection(client, pattern, '--lru=10s')) == {node_artifact(used), node_artifact(idle)}
    assert set(selection(client, '*#*', '--lru=10s')['Local Cache']) == {'used/1.0', 'idle/1.0'}
    assert selected_artifacts(selection(client, pattern, '--lru=1h')) == set()
    assert selection(client, '*#*', '--lru=1h') == {'Local Cache': {}}
    # The duration must lie between the age of the refreshed artifact and the idle one.
    # A round whose commands took longer than that duration cannot tell them apart and
    # is repeated; the idle artifact has aged meanwhile, so the next round has more room.
    for _ in range(6):
        started = time.monotonic()
        duration = int(started - created) - 1
        cli_success(client, 'install', '--requires=used/1.0', '-nr')
        artifacts = selected_artifacts(selection(client, pattern, f'--lru={duration}s'))
        recipes = set(selection(client, '*#*', f'--lru={duration}s')['Local Cache'])
        if time.monotonic() - started < duration:
            break
    else:
        raise AssertionError('the judge host never ran an install and two listings within the measured age')
    assert artifacts == {node_artifact(idle)}
    assert recipes == {'idle/1.0'}
    with recipe_repository(tmp_path / 'remote', client.env) as url:
        attach_repositories(client, [('remote', url)])
        cli_rejection(client, 'list', pattern, '--lru=10s', '-r', 'remote')


def test_saved_selection_consumed_without_losing_identity(tmp_path):
    client = recipe_client(tmp_path / 'client')
    old = discovery_binary(client, tmp_path / 'recipe')
    new_package = discovery_binary(client, tmp_path / 'recipe', material='second')
    new_recipe = discovery_binary(client, tmp_path / 'recipe', marker='second')
    excluded = discovery_binary(client, tmp_path / 'excluded', name='excluded')
    local = selection(client, 'parcel/*#*:*#*')
    expected = {node_artifact(old), node_artifact(new_package), node_artifact(new_recipe)}
    assert selected_artifacts(local) == expected
    local_file = saved_selection(tmp_path / 'local.json', local)
    with recipe_repository(tmp_path / 'remote', client.env) as url:
        attach_repositories(client, [('remote', url)], publish=True)
        cli_success(client, 'upload', '--list', local_file, '-r', 'remote', '-c')
        remote = selection(client, '*#*:*#*', '-r', 'remote')
        assert selected_artifacts(remote, 'remote') == expected
        remote_file = saved_selection(tmp_path / 'remote.json', remote)
        # The remote now also holds an artifact the saved selection does not name.
        cli_success(client, 'upload', 'excluded/*', '-r', 'remote', '-c')
        assert node_artifact(excluded) in selected_artifacts(selection(client, '*#*:*#*', '-r', 'remote'), 'remote')
        cli_success(client, 'remove', '*', '-c')
        cli_success(client, 'download', '--list', remote_file, '-r', 'remote')
        assert selected_artifacts(selection(client, '*#*:*#*')) == expected
        for node, material in [(old, 'first'), (new_package, 'second'), (new_recipe, 'first')]:
            package = client.cache_path(binary_reference(node))
            assert read_json(package / 'payload.json')['material'] == material
        # Consume a historical recipe revision and its latest retained binary.
        report = cli_success(client, 'install', '--requires=' + old['ref'], '-nr',
                             '--format=json').json('stdout')
        assert binary_payload(named_node(report, 'parcel'))['material'] == 'second'


def test_graph_status_selection_and_merge(tmp_path):
    client = recipe_client(tmp_path / 'client')
    base = discovery_binary(client, tmp_path / 'base', name='base')
    recipe = recipe_file(tmp_path / 'top', '    requires = "base/1.0"\n', name='top', version='1.0')
    graph = cli_success(client, 'create', recipe.parent, '-nr', '--format=json').json('stdout')
    top = named_node(graph, 'top')
    graph_file = saved_selection(tmp_path / 'graph.json', graph)
    built = selection(client, None, '-g', graph_file, '-gb', 'build')
    cached = selection(client, None, '-g', graph_file, '-gb', 'cache')
    assert selected_artifacts(built) == {node_artifact(top)}
    assert selected_artifacts(cached) == {node_artifact(base)}
    recipes = selection(client, None, '-g', graph_file, '-gr', 'cache')['Local Cache']
    assert set(recipes) == {'base/1.0', 'top/1.0'}
    assert all('packages' not in rev for recipe in recipes.values() for rev in recipe['revisions'].values())
    assert selection(client, None, '-g', graph_file, '-gr', 'downloaded') == {'Local Cache': {}}
    a = saved_selection(tmp_path / 'built.json', built)
    b = saved_selection(tmp_path / 'cached.json', cached)
    # The recipe-only selection overlaps both binary selections on the same recipe revisions;
    # the union keeps their binaries whether it comes first or last.
    r = saved_selection(tmp_path / 'recipes.json', {'Local Cache': recipes})
    merged = cli_success(client, 'pkglist', 'merge', '-l', r, '-l', a, '-l', b, '-l', a, '-l', r,
                         '--format=json').json('stdout')
    assert set(merged['Local Cache']) == {'base/1.0', 'top/1.0'}
    assert selected_artifacts(merged) == {node_artifact(top), node_artifact(base)}
    # Lists under different repositories keep their association through a merge.
    elsewhere = saved_selection(tmp_path / 'elsewhere.json', {'elsewhere': built['Local Cache']})
    merged = cli_success(client, 'pkglist', 'merge', '-l', elsewhere, '-l', b,
                         '--format=json').json('stdout')
    assert set(merged) == {'elsewhere', 'Local Cache'}
    assert selected_artifacts(merged, 'elsewhere') == {node_artifact(top)}
    assert selected_artifacts(merged) == {node_artifact(base)}


def test_find_remote_revision_locations(tmp_path):
    client = recipe_client(tmp_path / 'client')
    with recipe_repository(tmp_path / 'one', client.env) as one, \
            recipe_repository(tmp_path / 'two', client.env) as two:
        attach_repositories(client, [('one', one), ('two', two)], publish=True)
        first = discovery_binary(client, tmp_path / 'recipe')
        cli_success(client, 'upload', first['ref'], '-r', 'one', '-c')
        second = discovery_binary(client, tmp_path / 'recipe', material='second')
        cli_success(client, 'upload', second['ref'], '-r', 'two', '-c')
        absent = discovery_binary(client, tmp_path / 'recipe', marker='absent')
        local = saved_selection(tmp_path / 'local.json', selection(client, '*#*:*#*'))
        found = cli_success(client, 'pkglist', 'find-remote', local, '-r', '*',
                            '--format=json').json('stdout')
        assert set(found) == {'one', 'two'}
        assert selected_artifacts(found, 'one') == {node_artifact(first)}
        assert selected_artifacts(found, 'two') == {node_artifact(second)}
        # Only the selected remote is consulted and reported.
        narrowed = cli_success(client, 'pkglist', 'find-remote', local, '-r', 'one',
                               '--format=json').json('stdout')
        assert set(narrowed) == {'one'}
        assert selected_artifacts(narrowed, 'one') == {node_artifact(first)}
        missing = saved_selection(tmp_path / 'missing.json', selection(client, absent['ref'] + ':*#*'))
        assert cli_success(client, 'pkglist', 'find-remote', missing, '-r', '*',
                           '--format=json').json('stdout') == {}
        remote_list = saved_selection(tmp_path / 'found.json', found)
        cli_success(client, 'remove', '*', '-c')
        for remote in ('one', 'two'):
            cli_success(client, 'download', '--list', remote_list, '-r', remote)
        assert selected_artifacts(selection(client, '*#*:*#*')) == {node_artifact(first), node_artifact(second)}
        for node, material in [(first, 'first'), (second, 'second')]:
            package = client.cache_path(binary_reference(node))
            assert read_json(package / 'payload.json')['material'] == material
    # The actual repository process has stopped: transport failure is not a 404 absence.
    cli_rejection(client, 'pkglist', 'find-remote', local, '-r', 'one')


def test_add_dependencies_version_selection(tmp_path):
    client = recipe_client(tmp_path / 'client')
    kinds = [('ordinary', 'requires', ()), ('tooling', 'tool_requires', ('--tool',)),
             ('checking', 'test_requires', ('--test',))]
    with recipe_repository(tmp_path / 'one', client.env) as one, \
            recipe_repository(tmp_path / 'two', client.env) as two:
        attach_repositories(client, [('one', one), ('two', two)], publish=True)
        for name, _, _ in kinds:
            export_versions(client, tmp_path, name, ['1.0', '2.4'])
            cli_success(client, 'upload', name + '/*', '-r', 'one', '-c')
            export_versions(client, tmp_path, name, ['9.0'])
            cli_success(client, 'upload', name + '/9.0', '-r', 'two', '-c')
        # Only the second selected remote provides this name. Version order, not text order,
        # decides the highest: a range from 9.0 would stop short of 10.0.
        export_versions(client, tmp_path, 'secondonly', ['9.0', '10.0'])
        cli_success(client, 'upload', 'secondonly/*', '-r', 'two', '-c')
        recipe = recipe_file(tmp_path / 'consumer', '', name='consumer', version='1.0')
        for name, category, flag in kinds:
            cli_success(client, 'require', 'add', '--folder', recipe.parent, *flag, name)
        cli_success(client, 'require', 'add', '--folder', recipe.parent, 'secondonly')
        graph = graph_document(client, recipe.parent)
        assert named_node(graph, 'secondonly')['version'] == '10.0'
        assert named_node(graph, 'ordinary')['version'] == '2.4'
        assert named_node(graph, 'tooling', 'build')['version'] == '2.4'
        assert named_node(graph, 'checking')['version'] == '2.4'
        for name, category, _ in kinds:
            edge = dependency_edge(graph, 'consumer', name,
                                   target_context='build' if category == 'tool_requires' else 'host')
            assert edge['build'] is (category == 'tool_requires')
            assert edge['test'] is (category == 'test_requires')
            export_versions(client, tmp_path, name, ['2.5', '3.0'])
        # Newly available compatible versions must be admitted; the next major must not.
        graph = graph_document(client, recipe.parent)
        for name, context in [('ordinary', 'host'), ('tooling', 'build'), ('checking', 'host')]:
            assert named_node(graph, name, context)['version'] == '2.5'
        # A named remote is the only one consulted, even when an earlier one provides the name.
        chosen = recipe_file(tmp_path / 'chosen', '', name='chosen', version='1.0')
        cli_success(client, 'require', 'add', '--folder', chosen.parent, 'ordinary', '-r', 'two')
        assert named_node(graph_document(client, chosen.parent), 'ordinary')['version'] == '9.0'
        local_recipe = recipe_file(tmp_path / 'local', '', name='local', version='1.0')
        for name, category, flag in kinds:
            cli_success(client, 'require', 'add', '--folder', local_recipe.parent, *flag, name, '-nr')
        graph = graph_document(client, local_recipe.parent)
        for name, context in [('ordinary', 'host'), ('tooling', 'build'), ('checking', 'host')]:
            assert named_node(graph, name, context)['version'] == '9.0'
            edge = dependency_edge(graph, 'local', name, target_context=context)
            assert edge['build'] is (context == 'build')
            assert edge['test'] is (name == 'checking')
            export_versions(client, tmp_path, name, ['9.2', '10.0'])
        graph = graph_document(client, local_recipe.parent)
        for name, context in [('ordinary', 'host'), ('tooling', 'build'), ('checking', 'host')]:
            assert named_node(graph, name, context)['version'] == '9.2'
        # With only older and out-of-range versions available, the remote-selected range fails.
        for version in ('2.4', '2.5'):
            cli_success(client, 'remove', 'ordinary/' + version, '-c')
        result = cli_rejection(client, 'graph', 'info', recipe.parent, '-nr', '--format=json')
        error = result.json('stdout')['graph']['error']
        assert error['type'] == 'missing'
        assert error['require']['ref'].partition('/')[0] == 'ordinary'
    # Explicit versions need no discovery, even with an unreachable selected remote.
    cli_success(client, 'remote', 'add', 'broken', one + '/unavailable')
    explicit = recipe_file(tmp_path / 'explicit', '', name='explicit', version='1.0')
    cli_success(client, 'require', 'add', '--folder', explicit.parent, 'fixed/4.2', 'label/release', '-r', 'broken')
    export_versions(client, tmp_path, 'fixed', ['4.2'])
    export_versions(client, tmp_path, 'label', ['release'])
    graph = graph_document(client, explicit.parent)
    assert named_node(graph, 'fixed')['version'] == '4.2'
    assert named_node(graph, 'label')['version'] == 'release'
    export_versions(client, tmp_path, 'fixed', ['4.8', '5.0'])
    export_versions(client, tmp_path, 'label', ['release2'])
    graph = graph_document(client, explicit.parent)
    assert named_node(graph, 'fixed')['version'] == '4.8'
    assert named_node(graph, 'label')['version'] == 'release'


def test_remove_dependencies_and_absent_reporting(tmp_path):
    client = recipe_client(tmp_path / 'client')
    for name in ('ordinary', 'tooling', 'checking', 'retained'):
        export_versions(client, tmp_path, name, ['1.0'])
    recipe = recipe_file(tmp_path / 'consumer', '''    def requirements(self):
        self.requires("ordinary/1.0")
        self.requires("retained/1.0")
        pass
    def build_requirements(self):
        self.tool_requires("tooling/1.0")
        self.tool_requires("retained/1.0")
        self.test_requires("checking/1.0")
        pass
''', name='consumer', version='1.0')
    graph = graph_document(client, recipe.parent)
    for name, context in [('ordinary', 'host'), ('tooling', 'build'), ('checking', 'host')]:
        named_node(graph, name, context)
    args = ('ordinary', '--tool', 'tooling', '--test', 'checking')
    cli_success(client, 'require', 'remove', '--folder', recipe.parent, *args)
    graph = graph_document(client, recipe.parent)
    assert {n['name'] for n in graph['graph']['nodes'].values()} == {'consumer', 'retained'}
    before = read_bytes(recipe)
    result = cli_success(client, 'require', 'remove', '--folder', recipe.parent, *args)
    for name, category in [('ordinary', 'requires'), ('tooling', 'tool_requires'), ('checking', 'test_requires')]:
        dependency_report(result, name, category)
    assert read_bytes(recipe) == before
    assert named_node(graph_document(client, recipe.parent), 'retained')['version'] == '1.0'
    # Removal acts on the named kind: the same package stays declared as the other kind.
    cli_success(client, 'require', 'remove', '--folder', recipe.parent, '--tool', 'retained')
    graph = graph_document(client, recipe.parent)
    assert named_node(graph, 'retained')['version'] == '1.0'
    assert not [n for n in graph['graph']['nodes'].values()
                if n['name'] == 'retained' and n['context'] == 'build']


def test_add_preserves_existing_and_reports_unavailable(tmp_path):
    client = recipe_client(tmp_path / 'client')
    for name in ('present', 'presenttool', 'presenttest', 'solo'):
        export_versions(client, tmp_path, name, ['1.0', '2.0'])
    recipe = recipe_file(tmp_path / 'consumer', '''    def requirements(self):
        self.requires("present/1.0")
    def build_requirements(self):
        self.tool_requires("presenttool/1.0")
        self.test_requires("presenttest/1.0")
''', name='consumer', version='1.0')
    before = read_bytes(recipe)
    result = cli_success(client, 'require', 'add', '--folder', recipe.parent,
                         'present', '--tool', 'presenttool', '--test', 'presenttest', '-nr')
    for name, category in [('present', 'requires'), ('presenttool', 'tool_requires'),
                           ('presenttest', 'test_requires')]:
        dependency_report(result, name, category)
    assert read_bytes(recipe) == before
    graph = graph_document(client, recipe.parent)
    assert named_node(graph, 'present')['version'] == '1.0'
    assert named_node(graph, 'presenttool', 'build')['version'] == '1.0'
    assert named_node(graph, 'presenttest')['version'] == '1.0'
    result = cli_success(client, 'require', 'add', '--folder', recipe.parent, 'unavailable',
                         '--tool', 'unavailabletool', '--test', 'unavailabletest', '-nr')
    for name in ('unavailable', 'unavailabletool', 'unavailabletest'):
        dependency_report(result, name, label='ERROR:')
    assert read_bytes(recipe) == before
    cli_rejection(client, 'require', 'add', '--folder', tmp_path / 'missing', 'present', '-nr')
    # Already declared means declared as that kind: the same package can be added as another.
    solo = recipe_file(tmp_path / 'solo-consumer', '''    def requirements(self):
        self.requires("solo/1.0")
''', name='soloconsumer', version='1.0')
    cli_success(client, 'require', 'add', '--folder', solo.parent, '--tool', 'solo', '-nr')
    graph = graph_document(client, solo.parent)
    assert named_node(graph, 'solo')['version'] == '1.0'
    assert named_node(graph, 'solo', 'build')['version'] == '2.0'
