# feature: F05
"""Acceptance coverage for dependency resolution and recipe reuse."""
from pathlib import Path

from _helpers import write_file, read_bytes
from F01_helpers import cli_success, cli_rejection, named_node
from F02_helpers import recipe_client, recipe_file
from F03_helpers import recipe_repository, attach_repositories, revision_publisher
from F05_helpers import (dependency_recipe, dependency_graph, constraint_selection,
                         selected_version, dependency_edge, graph_failure,
                         usage_package, usage_consumer, usage_rows, native_usage_fields)


def test_recipe_and_direct_transitive_graph(tmp_path):
    client = recipe_client(tmp_path)
    leaf = dependency_recipe(client, tmp_path / 'leaf', 'leaf', '2.0')
    middle = dependency_recipe(client, tmp_path / 'middle', 'middle', body='    requires = "leaf/2.0"\n')
    consumer = recipe_file(tmp_path / 'consumer', '    requires = "middle/1.0"\n')
    for path, flags in ((consumer.parent, ()), (None, ('--requires=middle/1.0',))):
        report = dependency_graph(client, path, *flags)
        for name, reference in (('leaf', leaf), ('middle', middle)):
            node = named_node(report, name)
            assert node['ref'] == reference
            assert node['rrev'] == reference.split('#')[1]
            assert node['context'] == 'host'
        assert dependency_edge(report, 'middle', 'leaf')['ref'].partition('#')[0] == 'leaf/2.0'
    graph_failure(dependency_graph(client, None, '--requires=absent/7.0', rejected=True),
                  'missing', 'absent/7.0')
    # A transitive requirement whose recipe is absent is identified, not silently dropped.
    dependency_recipe(client, tmp_path / 'gap', 'gap', body='    requires = "absent/7.0"\n')
    graph_failure(dependency_graph(client, None, '--requires=gap/1.0', rejected=True),
                  'missing', 'absent/7.0')


def test_exact_bounds_conjunction_alternatives_prefix(tmp_path):
    client = recipe_client(tmp_path)
    # Exported once, in an order unrelated to version order, so recency cannot stand in for selection.
    versions = ('2.5', '1.0', '3.0', '1.4.1', '2.0', '1.5', '1.4')
    for version in versions:
        dependency_recipe(client, tmp_path / 'versions' / version, 'choice', version)
    cases = [('1.4', '1.4'), ('[>=1.4 <=2.0]', '2.0'), ('[>1.4 <2.5]', '2.0'),
             ('[<1.4 || >2.5]', '3.0'), ('[1.*]', '1.5'), ('[1.4.*]', '1.4.1'),
             ('[>=1.0 <1.4]', '1.0'), ('[<1.4 || >9]', '1.0'), ('[>=3.0]', '3.0')]
    for constraint, expected in cases:
        report = dependency_graph(client, None, '--requires=choice/' + constraint)
        assert selected_version(report) == expected
    # A prefix is textual: it stops at the characters supplied, not at a component or a leading digit.
    for version in ('1.4', '1.40', '1.9', '10.0'):
        dependency_recipe(client, tmp_path / 'prefix' / version, 'prefix', version)
    for constraint in ('[1.*]', '[1.4*]'):
        report = dependency_graph(client, None, '--requires=prefix/' + constraint)
        assert selected_version(report, 'prefix') == '1.40'
    graph_failure(dependency_graph(client, None, '--requires=choice/[>3.0 <4.0]', rejected=True),
                  'missing', 'choice/[>3.0 <4.0]')


def test_compatible_major_minor_boundaries(tmp_path):
    client = recipe_client(tmp_path)
    cases = [('[^1.2]', ('1.1', '1.2', '1.9', '2.0'), '1.9'),
             ('[^0.2.3]', ('0.2.2', '0.2.3', '0.2.9', '0.3.0'), '0.2.9'),
             ('[^0.0.3]', ('0.0.2', '0.0.3', '0.0.4'), '0.0.3'),
             ('[~1.2]', ('1.1', '1.2', '1.2.9', '1.3'), '1.2.9'),
             ('[~1]', ('0.9', '1.0', '1.9', '2.0'), '1.9'),
             ('[^2.3]', ('2.2', '2.3', '3.0'), '2.3')]
    for i, (constraint, versions, expected) in enumerate(cases):
        report = constraint_selection(client, tmp_path / str(i), versions, constraint, name='compat' + str(i))
        assert selected_version(report, 'compat' + str(i)) == expected
    for i, constraint in enumerate(('[^1.2]', '[~1.2]')):
        name = 'lower' + str(i)
        report = constraint_selection(client, tmp_path / name, ('1.1', '2.0'), constraint,
                                      name=name, rejected=True)
        graph_failure(report, 'missing', name + '/' + constraint)


def test_local_remote_and_update_version_selection(tmp_path):
    client = recipe_client(tmp_path / 'reader')
    with recipe_repository(tmp_path / 'first', client.env) as first, \
            recipe_repository(tmp_path / 'second', client.env) as second:
        repositories = [('first', first), ('second', second)]
        publisher = revision_publisher(tmp_path / 'publisher', repositories)
        for version, remote in [('2.0', 'first'), ('2.7', 'first'), ('3.0', 'second'), ('4.0', 'second')]:
            dependency_recipe(publisher, tmp_path / ('publish' + version), 'choice', version)
            cli_success(publisher, 'upload', 'choice/' + version, '-r', remote, '-c')
        attach_repositories(client, repositories)
        def resolve(*args, constraint='[>=1 <4]'):
            return named_node(dependency_graph(client, None, '--requires=choice/' + constraint,
                                                *args, local=False), 'choice')
        node = resolve()
        assert node['version'] == '2.7'
        assert node['remote'] == 'first'
        dependency_recipe(client, tmp_path / 'local', 'choice', '2.8')
        assert resolve()['version'] == '2.8'
        node = resolve('--update')
        assert node['version'] == '3.0'
        assert node['remote'] == 'second'
        # A remote without a satisfying version is passed over for the next one offering a match.
        node = resolve(constraint='[>=4]')
        assert node['version'] == '4.0'
        assert node['remote'] == 'second'
        # An update keeps a local version higher than every remote match.
        dependency_recipe(client, tmp_path / 'newer', 'choice', '3.5')
        assert resolve('--update')['version'] == '3.5'


def test_prerelease_eligibility_and_caller_override(tmp_path):
    client = recipe_client(tmp_path)
    for version in ('1.0-pre.1', '1.0', '1.5-pre.2', '2.0-pre.1'):
        dependency_recipe(client, tmp_path / version, 'choice', version)
    cases = [('[>=1 <2]', (), '1.0'), ('[>=1 <2, include_prerelease]', (), '1.5-pre.2'),
             ('[>=1 <2, include_prerelease]', ('-cc', 'core.version_ranges:resolve_prereleases=False'), '1.0'),
             ('[>=1 <2]', ('-cc', 'core.version_ranges:resolve_prereleases=True'), '1.5-pre.2'),
             ('[>=1.0 <1.0.1, include_prerelease]', (), '1.0'),
             ('[^1.0, include_prerelease]', (), '1.5-pre.2'),
             ('[~1, include_prerelease]', (), '1.5-pre.2')]
    for constraint, args, expected in cases:
        report = dependency_graph(client, None, '--requires=choice/' + constraint, *args)
        assert selected_version(report) == expected
    # An inclusive release lower bound admits that release's prereleases.
    dependency_recipe(client, tmp_path / 'preonly', 'preonly', '1.0-pre.1')
    for constraint in ('[>=1.0 <2, include_prerelease]', '[^1.0, include_prerelease]',
                       '[~1.0, include_prerelease]'):
        assert selected_version(dependency_graph(client, None,
            '--requires=preonly/' + constraint), 'preonly') == '1.0-pre.1'
    graph_failure(dependency_graph(client, None, '--requires=preonly/[>=1 <2]', rejected=True),
                  'missing', 'preonly/[>=1 <2]')


def test_shared_visible_constraints_and_identity_conflicts(tmp_path):
    client = recipe_client(tmp_path)
    for version in ('1.0', '2.0'):
        dependency_recipe(client, tmp_path / version, 'leaf', version)
    dependency_recipe(client, tmp_path / 'left', 'left', body='    requires = "leaf/1.0"\n')
    dependency_recipe(client, tmp_path / 'right', 'right', body='    requires = "leaf/[>=1 <2]"\n')
    consumer = recipe_file(tmp_path / 'consumer', '    requires = "left/1.0", "right/1.0"\n')
    report = dependency_graph(client, consumer.parent)
    assert selected_version(report, 'leaf') == '1.0'
    assert dependency_edge(report, 'right', 'leaf')['ref'].partition('#')[0] == 'leaf/1.0'
    for requirement in ('leaf/2.0', 'leaf/1.0@vendor/stable', 'leaf/[>=2 <3]',
                        'leaf/[>=1 <2]@vendor/stable'):
        dependency_recipe(client, tmp_path / 'right', 'right', body=f'    requires = {requirement!r}\n')
        graph_failure(dependency_graph(client, consumer.parent, rejected=True), 'conflict', 'leaf')


def test_consumer_override_changes_edges_without_adding_dependency(tmp_path):
    client = recipe_client(tmp_path)
    for version in ('1.0', '2.0'):
        dependency_recipe(client, tmp_path / version, 'leaf', version)
    dependency_recipe(client, tmp_path / 'middle', 'middle', body='    requires = "leaf/1.0"\n')
    for has_middle in (True, False):
        body = ('    requires = "middle/1.0"\n' if has_middle else '') + '''    def requirements(self):
        self.requires("leaf/2.0", override=True)
'''
        path = recipe_file(tmp_path / 'consumer', body)
        report = dependency_graph(client, path.parent)
        if has_middle:
            assert selected_version(report, 'leaf') == '2.0'
            assert dependency_edge(report, 'middle', 'leaf')['ref'].partition('#')[0] == 'leaf/2.0'
        else:
            assert {n['name'] for n in report['graph']['nodes'].values()} == {'specimen'}


def test_host_build_and_local_test_dependency_roles(tmp_path):
    client = recipe_client(tmp_path)
    for name, version in [('dual', '1.0'), ('dual', '2.0'), ('testing', '1.0')]:
        usage_package(client, tmp_path / (name + version), name, version=version)
    declarations = '''    requires = "dual/1.0"
    tool_requires = "dual/2.0"
    test_requires = "testing/1.0"
'''
    report, observed = usage_consumer(client, tmp_path / 'consumer', declarations,
                                     '-s:h', 'os=Linux', '-s:b', 'os=FreeBSD')
    assert named_node(report, 'dual')['version'] == '1.0'
    assert named_node(report, 'dual', 'build')['version'] == '2.0'
    assert named_node(report, 'dual')['settings']['os'] == 'Linux'
    assert named_node(report, 'dual', 'build')['settings']['os'] == 'FreeBSD'
    rows = usage_rows(observed)
    assert rows['testing', False]['test'] is True
    assert rows['dual', True]['build'] is True
    cli_success(client, 'create', tmp_path / 'consumer', '-nr', '--build=missing')
    downstream, observed = usage_consumer(client, tmp_path / 'downstream', '    requires = "observer/1.0"\n', name='downstream')
    assert named_node(downstream, 'observer')['version'] == '1.0'
    assert ('testing', False) not in usage_rows(observed)


def test_independent_usage_traits_and_consumer_runtime(tmp_path):
    client = recipe_client(tmp_path)
    usage_package(client, tmp_path / 'dep', 'payload', 'shared-library')
    for i, (headers, libs, runtime) in enumerate(((True, True, True), (False, True, True),
                                               (True, False, True), (True, True, False))):
        declarations = f'''    def requirements(self):
        self.requires("payload/1.0", headers={headers}, libs={libs}, run={runtime})
'''
        report, observed = usage_consumer(client, tmp_path / str(i), declarations, native=True)
        row = usage_rows(observed)['payload', False]
        assert (row['headers'], row['libs'], row['run']) == (headers, libs, runtime)
        assert observed['payloads'] == ({'payload-payload': 'payload'} if runtime else {})
        fields = native_usage_fields(tmp_path / str(i), 'payload')
        assert fields['IncludeDirectories'] == (['$(VelmorapayloadRootFolder)/include'] if headers else [])
        assert fields['Libraries'] == (['payload_link.lib'] if libs else [])
        assert fields['BinaryDirectories'] == (['$(VelmorapayloadRootFolder)/bin'] if runtime else [])
        edge = dependency_edge(report, 'observer', 'payload')
        assert (edge['headers'], edge['libs'], edge['run']) == (headers, libs, runtime)


def test_invisible_branch_does_not_constrain_visible_branch(tmp_path):
    client = recipe_client(tmp_path)
    for version in ('1.0', '2.0'):
        usage_package(client, tmp_path / version, 'leaf', version=version)
    usage_package(client, tmp_path / 'private', 'private', body='''    def requirements(self):
        self.requires("leaf/1.0", visible=False)
''')
    report, observed = usage_consumer(client, tmp_path / 'consumer',
                                    '    requires = "private/1.0", "leaf/2.0"\n')
    assert usage_rows(observed)['leaf', False]['version'] == '2.0'
    assert dependency_edge(report, 'private', 'leaf')['ref'].partition('#')[0] == 'leaf/1.0'
    assert dependency_edge(report, 'observer', 'leaf')['ref'].partition('#')[0] == 'leaf/2.0'
    assert dependency_edge(report, 'private', 'leaf')['visible'] is False


def test_local_recipes_index_sources_and_binary_absence(tmp_path):
    client = recipe_client(tmp_path / 'client')
    index = tmp_path / 'index'
    write_file(index / 'recipes/indexed/config.yml', 'versions:\n  "1.0":\n    folder: old\n  "2.0":\n    folder: current\n')
    for folder, marker in [('old', 'older source'), ('current', 'selected source')]:
        recipe_file(index / 'recipes/indexed' / folder, '''    exports_sources = "material.txt"
    def package(self):
        from velmora.tools.files import copy
        copy(self, "material.txt", self.source_folder, self.package_folder)
''', name='indexed', version='2.0' if folder == 'current' else '1.0')
        write_file(index / 'recipes/indexed' / folder / 'material.txt', marker)
    attach_repositories(client, [])
    cli_success(client, 'remote', 'add', 'index', index, '--type=local-recipes-index')
    # Recipe resolution succeeds but the index cannot satisfy binary acquisition.
    unresolved_binary = dependency_graph(client, None, '--requires=indexed/2.0', local=False)
    assert named_node(unresolved_binary, 'indexed')['binary'] == 'Missing'
    rejected = cli_rejection(client, 'install', '--requires=indexed/2.0', '--format=json')
    assert 'indexed/2.0' in rejected.text('stderr')
    for version, constraint, marker in [('1.0', '[>=1 <2]', 'older source'),
                                        ('2.0', '2.0', 'selected source')]:
        report = dependency_graph(client, None, '--requires=indexed/' + constraint,
                                  '--build=missing', local=False, install=True)
        node = named_node(report, 'indexed')
        assert node['version'] == version
        assert read_bytes(Path(node['package_folder']) / 'material.txt') == marker.encode()


def test_self_and_transitive_dependency_cycles(tmp_path):
    client = recipe_client(tmp_path)
    dependency_recipe(client, tmp_path / 'self', 'selfdep', body='    requires = "selfdep/1.0"\n')
    graph_failure(dependency_graph(client, None, '--requires=selfdep/1.0', rejected=True),
                  'loop', 'selfdep/1.0')
    dependency_recipe(client, tmp_path / 'a', 'alpha', body='    requires = "beta/1.0"\n')
    dependency_recipe(client, tmp_path / 'b', 'beta', body='    requires = "gamma/1.0"\n')
    dependency_recipe(client, tmp_path / 'g', 'gamma')
    assert named_node(dependency_graph(client, None, '--requires=alpha/1.0'), 'gamma')['version'] == '1.0'
    dependency_recipe(client, tmp_path / 'g', 'gamma', body='    requires = "alpha/1.0"\n')
    graph_failure(dependency_graph(client, None, '--requires=alpha/1.0', rejected=True),
                  'loop', 'alpha/1.0')


def test_profile_replacement_contexts_and_direct_exemption(tmp_path):
    client = recipe_client(tmp_path)
    for version in ('1.0', '2.0', '3.0', '4.0'):
        dependency_recipe(client, tmp_path / version, 'leaf', version)
    for version in ('1.0', '4.0'):
        dependency_recipe(client, tmp_path / ('builder' + version), 'builder', version)
    dependency_recipe(client, tmp_path / 'tool', 'tool',
                      body='    requires = "leaf/1.0"\n    tool_requires = "builder/1.0"\n')
    consumer = recipe_file(tmp_path / 'consumer', '    requires = "leaf/1.0"\n    tool_requires = "tool/1.0", "leaf/1.0"\n')
    host = write_file(tmp_path / 'host', '[replace_requires]\nleaf/*: leaf/2.0\n[replace_tool_requires]\nleaf/*: leaf/3.0\n')
    build = write_file(tmp_path / 'build', '[replace_requires]\nleaf/*: leaf/3.0\n[replace_tool_requires]\nbuilder/*: builder/4.0\n')
    report = dependency_graph(client, consumer.parent, '-pr:h', host, '-pr:b', build)
    assert selected_version(report, 'leaf') == '2.0'
    assert {n['version'] for n in report['graph']['nodes'].values()
            if n['name'] == 'leaf' and n['context'] == 'build'} == {'3.0'}
    assert selected_version(report, 'builder', 'build') == '4.0'
    assert dependency_edge(report, 'tool', 'builder', context='build')['ref'].partition('#')[0] == 'builder/4.0'
    direct = dependency_graph(client, None, '--requires=leaf/1.0', '-pr:h', host)
    assert selected_version(direct, 'leaf') == '1.0'
    direct = dependency_graph(client, None, '--tool-requires=leaf/1.0', '-pr:h', host)
    assert selected_version(direct, 'leaf', 'build') == '1.0'


def test_profile_replacement_order_composition_and_override_priority(tmp_path):
    client = recipe_client(tmp_path)
    for version in ('1.0', '2.0', '3.0', '4.0'):
        dependency_recipe(client, tmp_path / version, 'leaf', version)
    dependency_recipe(client, tmp_path / 'mid', 'middle', body='    requires = "leaf/1.0"\n')
    consumer = recipe_file(tmp_path / 'consumer', '''    requires = "middle/1.0"
    def requirements(self):
        self.requires("leaf/4.0", override=True)
''')
    first = write_file(tmp_path / 'first', '[replace_requires]\nleaf/*: leaf/2.0\nleaf/2.0: leaf/4.0\nleaf/1.0: leaf/3.0\n')
    assert selected_version(dependency_graph(client, consumer.parent, '-pr', first), 'leaf') == '2.0'
    second = write_file(tmp_path / 'second', '[replace_requires]\nleaf/*: leaf/3.0\n')
    assert selected_version(dependency_graph(client, consumer.parent, '-pr', first, '-pr', second), 'leaf') == '3.0'
    # Removing one inherited pattern leaves the others in effect; a version pattern matches only its version.
    unpattern = write_file(tmp_path / 'unpattern', '[replace_requires]\nleaf/*: !\n')
    plain = recipe_file(tmp_path / 'plain', '    requires = "leaf/1.0"\n')
    assert selected_version(dependency_graph(client, plain.parent, '-pr', first, '-pr', unpattern), 'leaf') == '3.0'
    remove = write_file(tmp_path / 'remove', '[replace_requires]\n*: !\n')
    assert selected_version(dependency_graph(client, consumer.parent, '-pr', first, '-pr', remove), 'leaf') == '4.0'


def test_versioned_python_recipe_behavior_material_and_failures(tmp_path):
    client = recipe_client(tmp_path)
    for version, marker in [('1.0', 'old material'), ('1.5', 'selected material')]:
        base = recipe_file(tmp_path / ('base' + version), '''    package_type = "python-require"
    exports = "material.txt"
''', name='base', version=version)
        write_file(base.parent / 'material.txt', marker)
        cli_success(client, 'export', base.parent, '-nr')
    reusable = write_file(tmp_path / 'reuse/velmorafile.py', '''from velmora import VelmoraFile
import os
class SharedBehavior:
    def package(self):
        from velmora.tools.files import load, save
        base = self.python_requires["base"]
        save(self, os.path.join(self.package_folder, "result.txt"),
             load(self, os.path.join(base.path, "material.txt")) + ":extended")
class Reuse(VelmoraFile):
    name = "reuse"
    version = "1.0"
    package_type = "python-require"
    python_requires = "base/[>=1 <2]"
''')
    cli_success(client, 'export', reusable.parent, '-nr')
    package = recipe_file(tmp_path / 'package', '''    python_requires = "reuse/1.0"
    python_requires_extend = "reuse.SharedBehavior"
''', name='reuser', version='1.0')
    report = cli_success(client, 'create', package.parent, '-nr', '--format=json').json('stdout')
    node = named_node(report, 'reuser')
    assert read_bytes(Path(node['package_folder']) / 'result.txt') == b'selected material:extended'
    # Python-require failures have no structured category in graph JSON.
    # Assert their public failure carrier and affected requirement, never prose wording.
    for requirement in ('unavailable/1.0', 'base/[>8]'):
        bad = recipe_file(tmp_path / 'bad', f'    python_requires = {requirement!r}\n')
        result = cli_rejection(client, 'export', bad.parent, '-nr')
        assert requirement in result.text('stderr')
    conflicting = recipe_file(tmp_path / 'conflicting',
        '    python_requires = "base/1.0", "reuse/1.0"\n')
    result = cli_rejection(client, 'export', conflicting.parent, '-nr')
    assert 'base' in result.text('stderr')


def test_platform_requirements_identity_revision_context_and_install(tmp_path):
    client = recipe_client(tmp_path)
    for declaration in ('platform/1.5', 'platform/1.5#declared'):
        profile = write_file(tmp_path / 'platform-profile', 'include(default)\n[platform_requires]\n' + declaration + '\n')
        for kind in ('requires', 'test_requires'):
            report, observed = usage_consumer(client, tmp_path / (kind + declaration.replace('/', '-').replace('#', '-')),
                f'    {kind} = "platform/[>=1 <2]"\n', '-pr', profile)
            assert usage_rows(observed)['platform', False]['version'] == '1.5'
    for i, (requirement, supplied) in enumerate([
            ('platform/1.5#same', 'platform/1.5#same'),
            ('platform/1.5#requested', 'platform/1.5'),
            ('platform/1.5@vendor/stable', 'platform/1.5@vendor/stable')]):
        profile = write_file(tmp_path / ('matching' + str(i)),
                             'include(default)\n[platform_requires]\n' + supplied + '\n')
        _, observed = usage_consumer(client, tmp_path / ('matched' + str(i)),
                                    f'    requires = {requirement!r}\n', '-pr', profile)
        assert usage_rows(observed)['platform', False]['version'] == '1.5'
    assert cli_success(client, 'list', 'platform/*', '--format=json').json('stdout')['Local Cache'] == {}
    ordinary = write_file(tmp_path / 'ordinary-only', 'include(default)\n[platform_requires]\nplatform/2.0\n')
    tool_consumer = recipe_file(tmp_path / 'tool-only', '    tool_requires = "platform/2.0"\n')
    graph_failure(dependency_graph(client, tool_consumer.parent, '-pr', ordinary, rejected=True),
                  'missing', 'platform/2.0')
    # Separate tool declarations satisfy build-context requirements without local recipes.
    profile = write_file(tmp_path / 'tools', 'include(default)\n[platform_requires]\nplatform/1.5\n[platform_tool_requires]\nplatform/2.0\n')
    report, observed = usage_consumer(client, tmp_path / 'both',
        '    requires = "platform/1.5"\n    tool_requires = "platform/2.0"\n', '-pr', profile)
    assert usage_rows(observed)['platform', True]['version'] == '2.0'
    # Every mismatching identity dimension leaves real acquisition in effect.
    for i, (requirement, supplied, section) in enumerate([
            ('platform/1.5', 'other/1.5', 'platform_requires'),
            ('platform/1.5', 'platform/2.0', 'platform_requires'),
            ('platform/[>=1 <2]', 'platform/3.0', 'platform_requires'),
            ('platform/1.5#requested', 'platform/1.5#different', 'platform_requires'),
            ('platform/1.5', 'platform/1.5', 'platform_tool_requires')]):
        profile = write_file(tmp_path / ('mismatch' + str(i)),
                             f'include(default)\n[{section}]\n' + supplied + '\n')
        recipe = recipe_file(tmp_path / 'check', f'    requires = {requirement!r}\n')
        graph_failure(dependency_graph(client, recipe.parent, '-pr', profile, rejected=True),
                      'missing', requirement)
    dependency_recipe(client, tmp_path / 'real', 'platform', '1.5', create=True)
    profile = write_file(tmp_path / 'nonmatching', 'include(default)\n[platform_requires]\nplatform/3.0\n')
    report = dependency_graph(client, None, '--requires=platform/1.5', '-pr', profile, install=True)
    assert named_node(report, 'platform')['binary'] == 'Cache'


def test_package_kind_default_usages_and_explicit_overrides(tmp_path):
    client = recipe_client(tmp_path)
    kinds = [('unknown', True, True, False, True), ('static-library', True, True, False, True),
             ('shared-library', True, True, True, True), ('header-library', True, False, False, True),
             ('application', False, False, True, True), ('build-scripts', False, False, True, False), ('library', True, True, False, True)]
    for i, (kind, headers, libs, runtime, visible) in enumerate(kinds):
        name = 'kind' + str(i)
        usage_package(client, tmp_path / name, name, kind,
                      body=('    options = {"shared": [True, False]}\n    default_options = {"shared": False}\n'
                            if kind == 'library' else ''))
        report, observed = usage_consumer(client, tmp_path / ('consumer' + str(i)), f'    requires = "{name}/1.0"\n', native=True)
        row = usage_rows(observed)[name, False]
        assert (row['headers'], row['libs'], row['run'], row['visible']) == (headers, libs, runtime, visible)
        assert observed['payloads'] == ({name + '-payload': name} if runtime else {})
        fields = native_usage_fields(tmp_path / ('consumer' + str(i)), name)
        assert fields['IncludeDirectories'] == ([f'$(Velmora{name}RootFolder)/include'] if headers else [])
        assert fields['Libraries'] == ([name + '_link.lib'] if libs else [])
    report, observed = usage_consumer(client, tmp_path / 'tool', '    tool_requires = "kind2/1.0"\n')
    row = usage_rows(observed)['kind2', True]
    assert (row['headers'], row['libs'], row['run'], row['visible']) == (False, False, True, False)
    report, observed = usage_consumer(client, tmp_path / 'explicit', '''    def requirements(self):
        self.requires("kind4/1.0", headers=True, libs=True, run=False, visible=False)
''')
    row = usage_rows(observed)['kind4', False]
    assert (row['headers'], row['libs'], row['run'], row['visible']) == (True, True, False, False)
    assert observed['payloads'] == {}


def test_transitive_usage_defaults_visibility_and_propagation_overrides(tmp_path):
    client = recipe_client(tmp_path)
    usage_package(client, tmp_path / 'leaf', 'leaf', 'shared-library')
    usage_package(client, tmp_path / 'archive', 'archive', 'static-library')
    cases = [('leaf', 'static-library', '', False, True, True),
             ('leaf', 'shared-library', '', False, False, True),
             ('leaf', 'application', '', False, False, True),
             ('leaf', 'header-library', '', True, True, True),
             ('leaf', 'static-library', ', visible=False', None, None, None),
             ('leaf', 'static-library', ', transitive_headers=True, transitive_libs=False', True, False, True),
             ('leaf', 'header-library', ', transitive_headers=False', False, True, True),
             ('leaf', 'shared-library', ', transitive_libs=True', False, True, True),
             ('archive', 'static-library', '', False, True, False)]
    for i, (dep, kind, traits, headers, libs, runtime) in enumerate(cases):
        name = 'middle' + str(i)
        usage_package(client, tmp_path / name, name, kind, body=f'''    def requirements(self):
        self.requires("{dep}/1.0"{traits})
''')
        report, observed = usage_consumer(client, tmp_path / ('consumer' + str(i)), f'    requires = "{name}/1.0"\n', native=True)
        rows = usage_rows(observed)
        assert rows[name, False]['version'] == '1.0'
        if headers is None:
            assert (dep, False) not in rows
            assert dep + '-payload' not in observed['payloads']
        else:
            row = rows[dep, False]
            assert (row['headers'], row['libs'], row['run']) == (headers, libs, runtime)
            assert observed['payloads'].get(dep + '-payload') == (dep if runtime else None)
            fields = native_usage_fields(tmp_path / ('consumer' + str(i)), dep)
            assert fields['IncludeDirectories'] == ([f'$(Velmora{dep}RootFolder)/include'] if headers else [])
            assert fields['Libraries'] == ([dep + '_link.lib'] if libs else [])


def test_main_version_component_order_and_zero_equivalence(tmp_path):
    client = recipe_client(tmp_path)
    cases = [(('2.9', '2.10'), '[>=2]', '2.10'),
             (('1.alpha', '1.beta'), '[>=1]', '1.beta'),
             (('1.0', '1.0.0'), '[>=1 <=1]', None),
             (('1.0.0', '1.0.1'), '[>1]', '1.0.1'),
             (('1.a9', '1.a10'), '[>=1]', '1.a9'),
             (('1.10', '1.b'), '[>=1]', '1.b')]
    for i, (versions, constraint, expected) in enumerate(cases):
        name = 'order' + str(i)
        report = constraint_selection(client, tmp_path / name, versions, constraint, name=name)
        chosen = selected_version(report, name)
        if expected is None:
            assert chosen in versions
        else:
            assert chosen == expected


def test_prerelease_and_build_qualifier_order(tmp_path):
    client = recipe_client(tmp_path)
    cases = [(('1.0-pre.9', '1.0'), '1.0'),
             (('1.0-pre.9', '1.0-pre.10'), '1.0-pre.10'),
             (('1.0-alpha', '1.0-beta'), '1.0-beta'),
             (('1.0', '1.0+build.1'), '1.0+build.1'),
             (('1.0+build.9', '1.0+build.10'), '1.0+build.10'),
             (('1.0+alpha', '1.0+beta'), '1.0+beta')]
    for i, (versions, expected) in enumerate(cases):
        name = 'qualifier' + str(i)
        report = constraint_selection(client, tmp_path / name, versions,
                                      '[>=0, include_prerelease]', name=name)
        assert selected_version(report, name) == expected
