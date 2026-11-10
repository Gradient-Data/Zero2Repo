# feature: F10
"""Source preparation, production and consumer acceptance through real CLI entries."""
import json
from pathlib import Path
import shlex
import sys

from _helpers import read_bytes, read_json, write_file
from F01_helpers import cli_success, configuration_http, named_node
from F02_helpers import recipe_client, recipe_file
from F03_helpers import git_command
from F05_helpers import dependency_recipe, dependency_edge
from F06_helpers import binary_reference
from F10_helpers import (archive_input, consume_artifact, create_production, digest_source,
                         git_source_repository, production_failure, production_recipe,
                         source_recipe, standard_digests, consumer_test_recipe)


def test_source_materialization_and_rejection(tmp_path):
    client = recipe_client(tmp_path)
    root = source_recipe(tmp_path / 'recipe', '''        import os
        from velmora.tools.files import save
        save(self, os.path.join(self.source_folder, "nested", "input.txt"), "prepared material\\n")
''')
    cli_success(client, 'source', root)
    assert read_bytes(root / 'selected-source/nested/input.txt') == b'prepared material\n'
    source_recipe(root, '        raise RuntimeError("source-cause-token")\n')
    production_failure(client, 'source', root, cause='source-cause-token', affected='specimen/2.7')
    text = write_file(tmp_path / 'text/velmorafile.txt', '[requires]\n')
    production_failure(client, 'source', text, affected='velmorafile.txt')


def test_archive_extraction_patch_and_failures(tmp_path):
    client = recipe_client(tmp_path)
    archive = archive_input(tmp_path / 'http')
    patch = '--- a/value.txt\n+++ b/value.txt\n@@ -1 +1 @@\n-copper\n+silver\n'
    with configuration_http(archive.parent) as url:
        def prepare(folder, address, diff):
            root = source_recipe(folder, '''        from velmora.tools.files import get, patch
        get(self, %r, retry=0)
        patch(self, patch_file=%r)
''' % (address, str(Path(folder) / 'change.patch')))
            write_file(root / 'change.patch', diff)
            return root
        for name in ('sources.zip', 'sources.tar.gz'):
            root = prepare(tmp_path / ('valid-' + name), url + '/' + name, patch)
            cli_success(client, 'source', root)
            assert read_bytes(root / 'selected-source/value.txt') == b'silver\n'
            assert read_bytes(root / 'selected-source/nested/keep.txt') == b'unchanged\n'
        missing = prepare(tmp_path / 'unavailable', url + '/unavailable.zip', patch)
        production_failure(client, 'source', missing, affected='specimen/2.7')
        broken = prepare(tmp_path / 'bad-patch', url + '/sources.zip', patch.replace('copper', 'absent'))
        production_failure(client, 'source', broken, cause='change.patch', affected='specimen/2.7')


def test_download_standard_integrity_algorithms(tmp_path):
    client = recipe_client(tmp_path)
    # Binary data spans many digest blocks and common read buffers, including NULs and
    # non-UTF8 bytes, so only a digest of the complete ordered bytes matches.
    payload = bytes(range(256)) * 800 + b'ordered final bytes\x00\xff'
    write_file(tmp_path / 'http/payload.bin', payload)
    digests = standard_digests(payload)
    with configuration_http(tmp_path / 'http') as url:
        for algorithm, digest in digests.items():
            root = digest_source(tmp_path / algorithm, url + '/payload.bin', {algorithm: digest})
            cli_success(client, 'source', root)
            assert read_bytes(root / 'selected-source/download.bin') == payload
            # Differs from the payload only in its final byte.
            wrong = standard_digests(payload[:-1] + b'\xfe')[algorithm]
            bad = digest_source(tmp_path / (algorithm + '-bad'), url + '/payload.bin', {algorithm: wrong})
            production_failure(client, 'source', bad, affected='specimen/2.7')


def test_all_supplied_integrity_checks_are_required(tmp_path):
    client = recipe_client(tmp_path)
    payload = b'combined integrity declarations\x00\xff\n' * 29
    write_file(tmp_path / 'http/payload.bin', payload)
    good = standard_digests(payload)
    with configuration_http(tmp_path / 'http') as url:
        root = digest_source(tmp_path / 'valid', url + '/payload.bin', good)
        cli_success(client, 'source', root)
        assert read_bytes(root / 'selected-source/download.bin') == payload
        # Each single damaged declaration must reject, including the last supplied one.
        for algorithm in good:
            bad = dict(good)
            bad[algorithm] = standard_digests(payload + b'changed')[algorithm]
            root = digest_source(tmp_path / algorithm, url + '/payload.bin', bad)
            production_failure(client, 'source', root, affected='specimen/2.7')


def test_git_commit_branch_tag_and_recorded_acquisition(tmp_path):
    client = recipe_client(tmp_path)
    repository = tmp_path / 'repository'
    first, last = git_source_repository(repository, client.env)
    for index, (revision, commit, content) in enumerate([
            (first, first, b'first revision\n'), ('release-point', first, b'first revision\n'),
            ('source-line', last, b'second revision\n')]):
        receipt = tmp_path / ('coordinates-%s.json' % index)
        root = source_recipe(tmp_path / str(index), '''        import json, os
        from velmora.tools.scm import Git
        from velmora.tools.files import save
        git = Git(self)
        git.clone(%r, target=".")
        git.checkout(%r)
        url, commit = git.get_url_and_commit()
        save(self, %r, json.dumps(dict(url=url, commit=commit)))
''' % (str(repository), revision, str(receipt)))
        cli_success(client, 'source', root)
        selected = root / 'selected-source'
        assert read_bytes(selected / 'value.txt') == content
        assert git_command(selected, client.env, 'rev-parse', 'HEAD') == commit
        coordinates = read_json(receipt)
        assert coordinates['commit'] == commit
        assert Path(coordinates['url']).resolve() == repository.resolve()
        replay = source_recipe(tmp_path / ('replay-%s' % index), '''        from velmora.tools.scm import Git
        git = Git(self)
        git.clone(%r, target=".")
        git.checkout(%r)
''' % (coordinates['url'], coordinates['commit']))
        cli_success(client, 'source', replay)
        assert read_bytes(replay / 'selected-source/value.txt') == content
        assert git_command(replay / 'selected-source', client.env, 'rev-parse', 'HEAD') == commit


def test_git_capture_respects_selected_scope(tmp_path):
    client = recipe_client(tmp_path)
    repository = tmp_path / 'repository'
    git_source_repository(repository, client.env)
    write_file(repository / 'scope/input.txt', 'committed\n')
    git_command(repository, client.env, 'add', '.')
    git_command(repository, client.env, '-c', 'user.name=Acceptance', '-c', 'user.email=acceptance@example.invalid',
                'commit', '-m', 'Add selected scope')
    expected = git_command(repository, client.env, 'rev-parse', 'HEAD')
    receipt = tmp_path / 'capture.json'
    root = source_recipe(tmp_path / 'capture', '''        import json
        from velmora.tools.scm import Git
        from velmora.tools.files import save
        url, commit = Git(self, folder=%r).get_url_and_commit()
        save(self, %r, json.dumps(dict(url=url, commit=commit)))
''' % (str(repository / 'scope'), str(receipt)))
    cli_success(client, 'source', root)
    assert read_json(receipt) == {'url': str(repository), 'commit': expected}
    write_file(repository / 'value.txt', 'outside selected scope\n')
    cli_success(client, 'source', root)
    assert read_json(receipt) == {'url': str(repository), 'commit': expected}
    # A new, never committed file inside the scope is an uncommitted change too.
    added = write_file(repository / 'scope/added.txt', 'never committed\n')
    production_failure(client, 'source', root, affected='specimen/2.7', cause=str(repository / 'scope'))
    added.unlink()
    write_file(repository / 'scope/input.txt', 'uncommitted\n')
    production_failure(client, 'source', root, affected='specimen/2.7', cause=str(repository / 'scope'))


def test_local_build_uses_configuration_locations_dependencies_and_propagates_failures(tmp_path):
    client = recipe_client(tmp_path)
    dependency_recipe(client, tmp_path / 'dependency', 'ingredient', body='''    def package(self):
        import os
        from velmora.tools.files import save
        save(self, os.path.join(self.package_folder, "ingredient.txt"), "dependency material\\n")
''', create=True)
    root = tmp_path / 'local'
    output = tmp_path / 'output'
    script = write_file(root / 'compile.py', '''import json, os, pathlib, sys
source, dependency, flavor, target = sys.argv[1:]
payload = dict(source=pathlib.Path(source).read_text(), dependency=pathlib.Path(dependency).read_text(),
               flavor=flavor, cwd=os.getcwd())
pathlib.Path(target).write_text(json.dumps(payload))
''')
    body = '''    settings = "build_type"
    requires = "ingredient/1.0"
    def layout(self):
        self.folders.source = "source-zone"
        self.folders.build = "build-zone"
    def build(self):
        import os, shlex
        dep = self.dependencies["ingredient"]
        self.run(shlex.join(%r + [os.path.join(self.source_folder, "input.txt"),
                 os.path.join(dep.package_folder, "ingredient.txt"), str(self.settings.build_type),
                 os.path.join(self.build_folder, "result.json")]))
''' % [sys.executable, str(script)]
    recipe_file(root, body)
    write_file(root / 'source-zone/input.txt', 'local source material\n')
    cli_success(client, 'build', root, '-nr', '-of', output, '-s', 'build_type=Debug')
    result = read_json(output / 'build-zone/result.json')
    assert result == dict(source='local source material\n', dependency='dependency material\n',
                          flavor='Debug', cwd=str(output / 'build-zone'))
    failure_script = write_file(root / 'fail.py', 'import sys\nprint("external-build-cause", file=sys.stderr)\nsys.exit(17)\n')
    recipe_file(root, '    def build(self):\n        self.run(%r)\n' % shlex.join([sys.executable, str(failure_script)]))
    production_failure(client, 'build', root, '-nr', cause='external-build-cause', affected='specimen/2.7')
    recipe_file(root, '    def build(self):\n        raise RuntimeError("recipe-build-cause")\n')
    production_failure(client, 'build', root, '-nr', cause='recipe-build-cause', affected='specimen/2.7')


def test_create_registers_consumable_selected_artifacts(tmp_path):
    client = recipe_client(tmp_path)
    root = production_recipe(tmp_path / 'producer')
    created = {}
    for flavor in ('small', 'large'):
        node = create_production(client, root, '-o', 'produced/*:flavor=' + flavor)
        assert node['package_id'] and node['prev'] and '#' in node['ref']
        package = client.cache_path(binary_reference(node))
        assert not (package / 'unselected.txt').exists()
        consumer, payload = consume_artifact(client, tmp_path / flavor, node['ref'], '-o', 'produced/*:flavor=' + flavor)
        assert (consumer['ref'], consumer['package_id'], consumer['prev']) == (node['ref'], node['package_id'], node['prev'])
        assert payload == dict(material='recipe source\n', flavor=flavor, build_type='Release')
        created[flavor] = node
    # The first selection's artifacts stay available after another selection was created.
    consumer, payload = consume_artifact(client, tmp_path / 'small-again', created['small']['ref'],
                                         '-o', 'produced/*:flavor=small')
    assert (consumer['package_id'], consumer['prev']) == (created['small']['package_id'], created['small']['prev'])
    assert payload == dict(material='recipe source\n', flavor='small', build_type='Release')


def test_export_prebuilt_uses_packaging_and_preserves_identity(tmp_path):
    client = recipe_client(tmp_path)
    dependency_recipe(client, tmp_path / 'dep', 'ingredient', create=True)
    root = tmp_path / 'prebuilt'
    recipe_file(root, '''    package_type = "static-library"
    settings = "os", "arch", "build_type"
    options = {"flavor": ["small", "large"]}
    default_options = {"flavor": "small"}
    requires = "ingredient/1.0"
    def layout(self):
        self.folders.build = "precompiled"
    def source(self):
        raise RuntimeError("prebuilt must not acquire sources")
    def build(self):
        raise RuntimeError("prebuilt must not rebuild")
    def package(self):
        from velmora.tools.files import copy
        copy(self, "artifact.json", self.build_folder, self.package_folder)
''', name='produced', version='1.0')
    expected = dict(material='independently prebuilt', flavor='large', build_type='Debug')
    write_file(root / 'precompiled/artifact.json', json.dumps(expected))
    write_file(root / 'precompiled/unselected.txt', 'not selected')
    report = cli_success(client, 'export-pkg', root, '-nr', '-s', 'build_type=Debug',
                         '-o', 'produced/*:flavor=large', '--format=json').json('stdout')
    node = named_node(report, 'produced')
    assert node['settings']['build_type'] == 'Debug'
    assert node['options']['flavor'] == 'large'
    dependency = named_node(report, 'ingredient')
    assert dependency['ref'].startswith('ingredient/1.0#')
    assert dependency_edge(report, 'produced', 'ingredient')['ref'] in (
        'ingredient/1.0', dependency['ref'])
    assert not (client.cache_path(binary_reference(node)) / 'unselected.txt').exists()
    # The same chosen settings/options must resolve the exported binary for a fresh consumer.
    consumer = recipe_file(tmp_path / 'consumer', '    requires = "produced/1.0"\n')
    installed = cli_success(client, 'install', consumer.parent, '-nr', '-s', 'build_type=Debug',
                            '-o', 'produced/*:flavor=large', '--format=json').json('stdout')
    selected = named_node(installed, 'produced')
    assert binary_reference(selected) == binary_reference(node)
    assert read_json(client.cache_path(binary_reference(selected)) / 'artifact.json') == expected


def test_existing_package_consumer_build_and_test_outcomes(tmp_path):
    client = recipe_client(tmp_path)
    node = create_production(client, production_recipe(tmp_path / 'producer'))
    reference = node['ref']
    other = production_recipe(tmp_path / 'newer-producer')
    write_file(other / 'velmorafile.py', read_bytes(other / 'velmorafile.py').replace(
        b'recipe source', b'newer source'))
    create_production(client, other)
    for phase in (None, 'build', 'test'):
        receipt = tmp_path / ('test-%s.json' % phase)
        root = consumer_test_recipe(tmp_path / ('consumer-%s' % phase), receipt, failure=phase)
        if phase is None:
            cli_success(client, 'test', root, reference, '-nr')
        else:
            production_failure(client, 'test', root, reference, '-nr', cause='consumer-%s-cause' % phase)
        if phase != 'build':
            assert read_json(receipt) == dict(material='recipe source\n', flavor='small', build_type='Release')


def test_create_associated_consumer_default_disable_and_failures(tmp_path):
    # Fresh isolated arms share all inputs except whether tests are disabled or a phase fails.
    for phase in ('success', 'disabled', 'build', 'test'):
        arm = tmp_path / phase
        client = recipe_client(arm)
        root = production_recipe(arm / 'producer')
        receipt = arm / 'tested.json'
        consumer_test_recipe(root / 'test_package', receipt, failure=phase if phase in ('build', 'test') else None)
        if phase in ('build', 'test'):
            production_failure(client, 'create', root, '-nr', cause='consumer-%s-cause' % phase)
        else:
            node = create_production(client, root, *(('-tf', '') if phase == 'disabled' else ()))
            assert read_json(client.cache_path(binary_reference(node)) / 'artifact.json') == dict(
                material='recipe source\n', flavor='small', build_type='Release')
        if phase == 'disabled':
            assert not receipt.exists()
        elif phase != 'build':
            assert read_json(receipt) == dict(material='recipe source\n', flavor='small', build_type='Release')


def test_system_prerequisites_context_timing_and_failure(tmp_path):
    client = recipe_client(tmp_path)
    receipt = tmp_path / 'prerequisites.jsonl'
    # A real external observation of prerequisite calls; no system package installation.
    script = write_file(tmp_path / 'prerequisite.py', '''import json, pathlib, sys
log, phase, arch = sys.argv[1:]
with pathlib.Path(log).open('a') as stream:
    stream.write(json.dumps(dict(phase=phase, arch=arch)) + '\\n')
''')
    command = shlex.join([sys.executable, str(script), str(receipt)])
    body = '''    settings = "os", "arch"
    def system_requirements(self):
        self.run(%r + " host " + str(self.settings.arch))
    def build_system_requirements(self):
        self.run(%r + " build " + str(self.settings_build.arch))
        from velmora.tools.system.package_manager import Apt
        Apt(self).install(["bash"])
''' % (command, command)
    root = recipe_file(tmp_path / 'producer', body, name='prerequisite', version='1.0').parent
    flags = ('-nr', '-s:h', 'arch=armv8', '-s:b', 'arch=x86_64',
             '-c', 'tools.system.package_manager:tool=apt-get',
             '-c', 'tools.system.package_manager:mode=check')
    cli_success(client, 'create', root, *flags)
    events = [json.loads(line) for line in receipt.read_text().splitlines()]
    assert sorted(events, key=lambda row: row['phase']) == [dict(phase='build', arch='x86_64'), dict(phase='host', arch='armv8')]
    receipt.unlink()
    cli_success(client, 'install', '--requires=prerequisite/1.0', *flags)
    assert [json.loads(line) for line in receipt.read_text().splitlines()] == [dict(phase='host', arch='armv8')]
    receipt.unlink()
    local = recipe_file(tmp_path / 'local', body).parent
    cli_success(client, 'install', local, *flags)
    assert dict(phase='build', arch='x86_64') in [json.loads(line) for line in receipt.read_text().splitlines()]
    # Check the real installed native prerequisite without installing anything. The same
    # prerequisite is unavailable for the foreign host architecture in this image.
    host = recipe_file(tmp_path / 'host-check', '    settings = "os", "arch"\n    def system_requirements(self):\n        from velmora.tools.system.package_manager import Apt\n        Apt(self).install(["bash"])\n').parent
    native = ('-nr', '-s:h', 'arch=x86_64', '-s:b', 'arch=x86_64',
              '-c', 'tools.system.package_manager:tool=apt-get',
              '-c', 'tools.system.package_manager:mode=check')
    cli_success(client, 'install', host, *native)
    production_failure(client, 'install', host, *flags, cause='bash')
    for method, operation in [('system_requirements', 'install'), ('build_system_requirements', 'create')]:
        root = recipe_file(tmp_path / method, '    def %s(self):\n        raise RuntimeError("prerequisite-cause-%s")\n' % (method, method)).parent
        production_failure(client, operation, root, '-nr', cause='prerequisite-cause-' + method)
