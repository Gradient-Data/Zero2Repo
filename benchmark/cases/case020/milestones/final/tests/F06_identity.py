# feature: F06
"""Acceptance of binary identity and declared compatibility."""
from _helpers import read_json
from F01_helpers import cli_success, cli_rejection, install_bundle
from F02_helpers import recipe_client, recipe_file
from F03_helpers import exported_reference, recipe_repository, attach_repositories
from F05_helpers import dependency_recipe, dependency_graph
from F06_helpers import (binary_recipe, create_binary, binary_node, binary_payload,
                         consumer_identity, binary_reference, explained_packages)


def test_declared_configuration_identity_and_reuse(tmp_path):
    client = recipe_client(tmp_path)
    path = binary_recipe(tmp_path / 'recipe')
    original = create_binary(client, path)
    for args, system, flavor in [((), 'Linux', 'plain'),
                                 (('-s', 'os=FreeBSD'), 'FreeBSD', 'plain'),
                                 (('-s', 'arch=armv8'), 'Linux', 'plain'),
                                 (('-o', 'binary/*:flavor=rich'), 'Linux', 'rich')]:
        built = create_binary(client, path, *args)
        selected = binary_node(client, None, '--requires=binary/1.0', *args, install=True)
        assert selected['package_id'] == built['package_id']
        assert binary_payload(selected) == dict(os=system, flavor=flavor, material='original')
        assert (built['package_id'] == original['package_id']) == (not args)
    dependency_recipe(client, tmp_path / 'dep', 'dep', '1.0')
    dependency_recipe(client, tmp_path / 'dep2', 'dep', '2.0')
    first = consumer_identity(client, tmp_path / 'consumer', 'dep/1.0')
    assert consumer_identity(client, tmp_path / 'consumer', 'dep/2.0') != first
    # A setting the recipe does not declare is no part of its identity.
    assert consumer_identity(client, tmp_path / 'consumer', 'dep/1.0', args=('-s', 'os=FreeBSD')) == first


def test_recipe_removed_and_normalized_dimensions(tmp_path):
    client = recipe_client(tmp_path)
    for label, customization in [('removed', 'del self.info.settings.os'),
                                  ('normalized', 'self.info.settings.os = "Linux"')]:
        path = binary_recipe(tmp_path / label, f'    def package_id(self):\n        {customization}\n', name=label)
        built = create_binary(client, path, name=label)
        chosen = binary_node(client, None, '--requires=' + label + '/1.0', '-s', 'os=FreeBSD', name=label, install=True)
        assert chosen['package_id'] == built['package_id']
        assert binary_payload(chosen)['os'] == 'Linux'
        for retained in (('-o', label + '/*:flavor=rich'), ('-s', 'build_type=Debug')):
            other = binary_node(client, None, '--requires=' + label + '/1.0', *retained, name=label)
            assert other['package_id'] != built['package_id']
            assert other['binary'] == 'Missing'


def test_dependency_version_sensitivity_modes(tmp_path):
    client = recipe_client(tmp_path)
    versions = ['1.0', '1.0.0.0', '1.0.0.1', '1.0.1', '1.2', '2.0', '0.2.1', '0.2.2']
    for version in versions:
        dependency_recipe(client, tmp_path / version, 'dep', version, create=True)
    cases = [('unrelated_mode', '1.0', '2.0', None),
             ('semver_mode', '1.0', '1.2', '2.0'),
             ('semver_mode', '0.2.1', '0.2.1', '0.2.2'),
             ('major_mode', '1.0', '1.2', '2.0'),
             ('minor_mode', '1.0', '1.0.1', '1.2'),
             ('patch_mode', '1.0', '1.0.0.1', '1.0.1'),
             ('micro_mode', '1.0', '1.0.0.0', '1.0.0.1')]
    for index, (mode, base, equal, different) in enumerate(cases):
        root = tmp_path / ('consumer' + str(index))
        identity = consumer_identity(client, root, 'dep/' + base, mode=mode)
        assert consumer_identity(client, root, 'dep/' + equal, mode=mode) == identity
        if different:
            assert consumer_identity(client, root, 'dep/' + different, mode=mode) != identity
        # Keep the recipe revision identical while changing only the resolved dependency.
        name = 'reuse' + str(index)
        recipe = binary_recipe(root, f'''    def requirements(self):
        import os
        self.requires("dep/" + os.environ["F06_DEP_VERSION"], package_id_mode={mode!r})
''', name=name)
        client.env['F06_DEP_VERSION'] = base
        built = create_binary(client, recipe, name=name, material=mode)
        client.env['F06_DEP_VERSION'] = equal
        selected = binary_node(client, None, '--requires=' + name + '/1.0', name=name, install=True)
        assert selected['binary'] == 'Cache'
        assert selected['package_id'] == built['package_id']
        assert binary_payload(selected)['material'] == mode
        if different:
            client.env['F06_DEP_VERSION'] = different
            cli_rejection(client, 'install', '-nr', '--requires=' + name + '/1.0')
            missing = binary_node(client, None, '--requires=' + name + '/1.0', name=name)
            assert missing['binary'] == 'Missing'
            assert missing['package_id'] != built['package_id']
    # Unlike the major-for-nonzero mode, plain major sensitivity ignores minor and patch of a zero major.
    root = tmp_path / 'zero-major'
    assert consumer_identity(client, root, 'dep/0.2.1', mode='major_mode') == \
        consumer_identity(client, root, 'dep/0.2.2', mode='major_mode')


def test_complete_dependency_identity_modes(tmp_path):
    client = recipe_client(tmp_path)
    path = binary_recipe(tmp_path / 'dep', name='dep')
    original = create_binary(client, path, name='dep')
    modes = ['full_recipe_mode', 'revision_mode', 'full_package_mode', 'full_mode']
    before = {mode: consumer_identity(client, tmp_path / mode, 'dep/1.0', mode=mode) for mode in modes}
    for mode in modes:
        after = consumer_identity(client, tmp_path / mode, 'dep/1.0', mode=mode,
                                  args=('-o', 'dep/*:flavor=rich'))
        assert (after != before[mode]) == (mode in ('full_package_mode', 'full_mode'))
    path = binary_recipe(tmp_path / 'dep', '    description = "new recipe revision"\n', name='dep')
    changed = create_binary(client, path, name='dep')
    assert changed['ref'] != original['ref']
    for mode in modes:
        after = consumer_identity(client, tmp_path / mode, 'dep/1.0', mode=mode)
        assert (after != before[mode]) == (mode in ('revision_mode', 'full_mode'))
    for mode in modes + ['semver_mode', 'major_mode', 'minor_mode', 'patch_mode', 'micro_mode']:
        refs = []
        for name, user, channel in [('dep', 'vendor', 'stable'), ('other', 'vendor', 'stable'),
                                    ('dep', 'alternate', 'stable'), ('dep', 'vendor', 'testing')]:
            dependency_recipe(client, tmp_path / 'qualified', name, qualifier=(user, channel))
            refs.append(f'{name}/1.0@{user}/{channel}')
        ids = [consumer_identity(client, tmp_path / mode, ref, mode=mode) for ref in refs]
        assert len(set(ids)) == len(ids), (mode, ids)
    dependency_recipe(client, tmp_path / 'version', 'dep', '1.0.0.1')
    for mode in modes:
        assert consumer_identity(client, tmp_path / mode, 'dep/1.0.0.1', mode=mode) != consumer_identity(client, tmp_path / mode, 'dep/1.0', mode=mode)


def test_embedded_and_header_dependency_identity(tmp_path):
    client = recipe_client(tmp_path)
    for dep_kind, consumer_kinds in [('static-library', ('application', 'shared-library')),
                                      ('header-library', ('application', 'shared-library', 'static-library'))]:
        name = 'dep'
        path = binary_recipe(tmp_path / 'dep', name=name, kind=dep_kind)
        create_binary(client, path, name=name)
        before = {kind: consumer_identity(client, tmp_path / kind, 'dep/1.0', kind=kind) for kind in consumer_kinds}
        for kind in consumer_kinds:
            assert consumer_identity(client, tmp_path / kind, 'dep/1.0', kind=kind,
                                     args=('-o', 'dep/*:flavor=rich')) != before[kind]
        path = binary_recipe(tmp_path / 'dep', '    description = "revision change"\n', name=name, kind=dep_kind)
        create_binary(client, path, name=name)
        for kind in consumer_kinds:
            assert consumer_identity(client, tmp_path / kind, 'dep/1.0', kind=kind) != before[kind]
        # Build a consumer which embeds the actual selected dependency material.
        consumer = binary_recipe(tmp_path / 'embedded', '''    requires = "dep/1.0"
    def generate(self):
        import os
        from velmora.tools.files import load, save
        save(self, os.path.join(self.generators_folder, "consumed.json"),
             load(self, os.path.join(self.dependencies["dep"].package_folder, "payload.json")))
''', name='embedded', kind=consumer_kinds[0])
        create_binary(client, consumer, name='embedded')
        dependency_graph(client, consumer, install=True)
        assert read_json(consumer / 'consumed.json')['material'] == 'original'


def test_nonembedded_dependency_minor_compatibility(tmp_path):
    client = recipe_client(tmp_path)
    for dep_kind, consumers in [('shared-library', ('application', 'shared-library', 'static-library')),
                                ('static-library', ('static-library',))]:
        for version in ('1.2.0', '1.2.9', '1.3.0'):
            dependency_recipe(client, tmp_path / version, 'dep', version, body=f'    package_type = {dep_kind!r}\n')
        for kind in consumers:
            base = consumer_identity(client, tmp_path / kind, 'dep/1.2.0', kind=kind)
            assert consumer_identity(client, tmp_path / kind, 'dep/1.2.9', kind=kind) == base
            assert consumer_identity(client, tmp_path / kind, 'dep/1.3.0', kind=kind) != base


def test_header_identity_clearing_and_header_consumers(tmp_path):
    client = recipe_client(tmp_path)
    for version in ('1.0', '2.0'):
        dependency_recipe(client, tmp_path / version, 'dep', version, create=True)
    # The explicit mode makes the dependency contribute unless the automatic configuration omits it.
    path = binary_recipe(tmp_path / 'header', '''    implements = ["auto_header_only"]
    def requirements(self):
        self.requires("dep/[>=1]", package_id_mode="major_mode")
''', kind='header-library')
    first = create_binary(client, path)
    for args in [('-s', 'os=FreeBSD'), ('-o', 'binary/*:flavor=rich')]:
        selected = binary_node(client, None, '--requires=binary/1.0', *args, install=True)
        assert selected['package_id'] == first['package_id']
        assert binary_payload(selected)['flavor'] == 'plain'
    for version in ('1.0', '2.0'):
        identity = consumer_identity(client, tmp_path / 'consumer', 'dep/' + version, kind='header-library')
        if version == '1.0':
            base = identity
        else:
            assert identity == base
    dependency_recipe(client, tmp_path / 'new', 'dep', '3.0', create=True)
    assert binary_node(client, None, '--requires=binary/1.0', install=True)['package_id'] == first['package_id']


def test_unknown_tools_tests_and_python_recipe_defaults(tmp_path):
    client = recipe_client(tmp_path)
    for version in ('1.2.0', '1.9.0', '2.0', '0.2.1', '0.2.2'):
        dependency_recipe(client, tmp_path / version, 'dep', version, create=True)
    ids = [consumer_identity(client, tmp_path / 'consumer', 'dep/' + v) for v in ('1.2.0', '1.9.0', '2.0', '0.2.1', '0.2.2')]
    assert ids[0] == ids[1]
    assert len(set([ids[0], *ids[2:]])) == 4
    for declaration in ('tool_requires', 'test_requires'):
        observed = []
        for version in ('1.2.0', '2.0'):
            path = recipe_file(tmp_path / declaration, f'    {declaration} = "dep/{version}"\n', name='consumer')
            observed.append(binary_node(client, path.parent, name='consumer')['package_id'])
        assert observed[0] == observed[1]
    # What a test dependency itself requires does not contribute either.
    observed = []
    for version in ('1.2.0', '2.0'):
        dependency_recipe(client, tmp_path / 'wrapper', 'wrapper', body=f'    requires = "dep/{version}"\n')
        path = recipe_file(tmp_path / 'wrapped', '    test_requires = "wrapper/1.0"\n', name='consumer')
        observed.append(binary_node(client, path.parent, name='consumer')['package_id'])
    assert observed[0] == observed[1]
    assert consumer_identity(client, tmp_path / 'no-usage', 'dep/1.2.0', traits=', headers=False, libs=False') == consumer_identity(client, tmp_path / 'no-usage', 'dep/2.0', traits=', headers=False, libs=False')
    observed = []
    for version in ('1.2.0', '1.2.9', '1.3.0', '2.0'):
        dependency_recipe(client, tmp_path / 'python', 'base', version, body='    package_type = "python-require"\n')
        path = recipe_file(tmp_path / 'python-consumer', f'    python_requires = "base/{version}"\n', name='consumer')
        observed.append(binary_node(client, path.parent, name='consumer')['package_id'])
    assert observed[0] == observed[1]
    assert len(set([observed[0], *observed[2:]])) == 3


def test_package_content_revisions_and_explicit_download(tmp_path):
    client = recipe_client(tmp_path / 'publisher')
    path = binary_recipe(tmp_path / 'recipe')
    first = create_binary(client, path, material='first contents')
    repeated = create_binary(client, path, material='first contents')
    assert repeated['prev'] == first['prev']
    changed = create_binary(client, path, material='second contents')
    assert changed['ref'] == first['ref']
    assert changed['package_id'] == first['package_id']
    assert changed['prev'] != first['prev']
    report = cli_success(client, 'list', first['ref'] + ':*#*', '--format=json').json('stdout')
    reference, _, revision = first['ref'].partition('#')
    revisions = report['Local Cache'][reference]['revisions'][revision]['packages'][first['package_id']]['revisions']
    assert set(revisions) == {first['prev'], changed['prev']}
    with recipe_repository(tmp_path / 'server', client.env) as url:
        attach_repositories(client, [('origin', url)], publish=True)
        cli_success(client, 'upload', first['ref'] + ':*#*', '-r', 'origin', '-c')
        reader = recipe_client(tmp_path / 'reader')
        attach_repositories(reader, [('origin', url)])
        for node, material in [(first, 'first contents'), (changed, 'second contents')]:
            cli_success(reader, 'download', binary_reference(node), '-r', 'origin')
            assert read_json(reader.cache_path(binary_reference(node)) / 'payload.json')['material'] == material


def test_invalid_configuration_reason_and_missing_binary(tmp_path):
    client = recipe_client(tmp_path)
    reason = 'This flavor cannot represent the requested configuration'
    path = binary_recipe(tmp_path / 'recipe', f'''    def validate(self):
        from velmora.errors import VelmoraInvalidConfiguration
        if self.options.flavor == "extra":
            raise VelmoraInvalidConfiguration({reason!r})
''')
    create_binary(client, path)
    assert binary_node(client, None, '--requires=binary/1.0', install=True)['binary'] == 'Cache'
    for flavor, status in [('rich', 'Missing'), ('extra', 'Invalid')]:
        args = ('--requires=binary/1.0', '-o', 'binary/*:flavor=' + flavor)
        node = binary_node(client, None, *args)
        assert node['binary'] == status
        assert node['info_invalid'] == (reason if flavor == 'extra' else None)
        cli_rejection(client, 'install', '-nr', *args,
                      status=6 if flavor == 'extra' else 1)


def test_exact_and_declared_compatibility_selection(tmp_path):
    # Both binaries are always built plain first; the two declared orders are opposite, so
    # neither build recency nor any ordering of the binaries themselves can stand in for declared order.
    for policy, order in (('recipe', ('rich', 'plain')), ('installed', ('plain', 'rich')), ('none', ())):
        client = recipe_client(tmp_path / policy)
        candidates = f'[{{"options": [("flavor", value)]}} for value in {order!r}] + [{{"settings": [("os", "FreeBSD")]}}]'
        declaration = f'''    def compatibility(self):
        return {candidates}
'''
        if policy == 'installed':
            install_bundle(client, tmp_path / 'plugin', {
                'extensions/plugins/compatibility/compatibility.py':
                f'def compatibility(velmorafile):\n    return {candidates}\n'})
        path = binary_recipe(tmp_path / policy / 'recipe', declaration if policy == 'recipe' else '')
        plain = create_binary(client, path)
        rich = create_binary(client, path, '-o', 'binary/*:flavor=rich')
        for flavor, expected in [('plain', plain), ('rich', rich)]:
            chosen = binary_node(client, None, '--requires=binary/1.0', '-o', 'binary/*:flavor=' + flavor, install=True)
            assert chosen['package_id'] == expected['package_id']
            assert binary_payload(chosen)['flavor'] == flavor
        args = ('--requires=binary/1.0', '-o', 'binary/*:flavor=extra')
        if policy == 'none':
            cli_rejection(client, 'install', '-nr', *args)
            failed = binary_node(client, None, *args)
            assert failed['binary'] == 'Missing'
        else:
            built = dict(plain=plain, rich=rich)
            for flavor in order:
                chosen = binary_node(client, None, *args, install=True)
                assert chosen['package_id'] == built[flavor]['package_id']
                assert binary_payload(chosen)['flavor'] == flavor
                cli_success(client, 'remove', built[flavor]['ref'] + ':' + built[flavor]['package_id'], '-c')
            # A policy does not make every existing binary eligible, only the ones it declares.
            create_binary(client, path, '-o', 'binary/*:flavor=extra', '-s', 'build_type=Debug')
            cli_rejection(client, 'install', '-nr', *args)
            assert binary_node(client, None, *args)['binary'] == 'Missing'
            # A declared setting alternative is eligible like an option alternative.
            other_os = create_binary(client, path, '-o', 'binary/*:flavor=extra', '-s', 'os=FreeBSD')
            chosen = binary_node(client, None, *args, install=True)
            assert chosen['package_id'] == other_os['package_id']
            assert binary_payload(chosen) == dict(os='FreeBSD', flavor='extra', material='original')


def test_binary_diagnostics_configuration_differences(tmp_path):
    client = recipe_client(tmp_path)
    dependency_recipe(client, tmp_path / 'dep', 'dep', '1.0', create=True)
    # A second non-platform setting and a second option stay equal, so only the differing entry may be listed.
    install_bundle(client, tmp_path / 'definitions', {'settings_user.yml': 'stage: [alpha, beta]\n'})
    base = ('-s', 'stage=alpha')
    path = binary_recipe(tmp_path / 'recipe', '''    settings = "os", "arch", "build_type", "stage"
    options = {"flavor": ["plain", "rich"], "level": ["low", "high"]}
    default_options = {"flavor": "plain", "level": "low"}
    requires = "dep/[>=1]"
    def package_id(self):
        self.info.requires.full_recipe_mode()
''', kind='unknown', config=False)
    exported_reference(client, path)
    empty = explained_packages(client, 'binary/1.0', *base)
    assert empty, empty
    assert all('packages' not in revision for revision in empty.values()), empty
    built = create_binary(client, path, *base)
    for args, category, existing, expected in [
            (('-s', 'build_type=Debug'), 'settings', 'build_type=Release', 'build_type=Debug'),
            (('-o', 'binary/*:flavor=rich'), 'options', 'flavor=plain', 'flavor=rich'),
            ((), 'dependencies', 'dep/1.0', 'dep/2.0')]:
        if category == 'dependencies':
            dependency_recipe(client, tmp_path / 'dep2', 'dep', '2.0', create=True)
        revisions = explained_packages(client, 'binary/1.0', *base, *args)
        package = revisions[built['ref'].partition('#')[2]]['packages'][built['package_id']]
        # Only the dimension that differs is reported, and only its differing entry.
        for name in ('settings', 'options', 'dependencies'):
            diff = package['diff'][name]
            wanted = ([existing], [expected]) if name == category else ([], [])
            assert (diff.get('existing', []), diff.get('expected', [])) == wanted, package
