# feature: F18
"""Installed policies and executable extensions through public commands."""
import hashlib
import hmac
from pathlib import Path
from urllib.parse import urlsplit

from _helpers import read_json, write_file
from F01_helpers import cli_success, cli_rejection, named_node
from F02_helpers import recipe_client, recipe_file
from F06_helpers import binary_reference
from F13_helpers import transfer_world, transfer_reader, transfer_package
from F18_helpers import (install_extensions, extension_failure, POLICY_PACKAGE, PROFILE_POLICY,
                         COMMAND_EXTENSION, SUBCOMMAND_EXTENSION, DEPENDENCY_GENERATOR,
                         SIGNING_EXTENSION, SIGNING_KEY, signing_consumer, signing_receipts)


def test_hooks_inspect_and_reject_each_package_stage(tmp_path):
    # F18.T01: every enumerated stage has a live success and a policy refusal.
    # Observe recipe work completed before each policy decision.
    stages = {'post_export': [], 'pre_validate': [], 'pre_source': [], 'pre_build': ['source'],
              'post_package': ['source', 'build', 'package']}
    # Both installed modules hold every callback; the stages alternate which of them rejects.
    modules = ('audit', 'inspection')
    owner = {stage: modules[index % 2] for index, stage in enumerate(stages)}
    hook = 'import os\nfrom velmora.errors import VelmoraException\nMODULE = __MODULE__\n'
    for stage in stages:
        inspection = ('    assert velmorafile.description == "inspected material"\n'
                      if stage != 'post_package' else
                      '    import json\n    with open(os.path.join(velmorafile.package_folder, "payload.json")) as stream:\n'
                      '        assert json.load(stream)["material"] == "inspected material"\n')
        hook += f'\ndef {stage}(velmorafile):\n' + inspection
        hook += (f'    if os.environ.get("F18_BLOCK_STAGE") == MODULE + ":{stage}":\n'
                 f'        raise VelmoraException("policy-denied-{stage}")\n')
    for stage in stages:
        for rejected in (False, True):
            root = tmp_path / stage / str(rejected)
            client = recipe_client(root)
            install_extensions(client, {f'extensions/hooks/hook_{module}.py':
                                        hook.replace('__MODULE__', repr(module)) for module in modules})
            source = recipe_file(root / 'recipe', POLICY_PACKAGE, name='policy', version='1.0').parent
            steps = root / 'steps.txt'
            client.env['F18_STEPS'] = str(steps)
            client.env['F18_BLOCK_STAGE'] = f'{owner[stage]}:{stage}' if rejected else ''
            if rejected:
                extension_failure(client, 'create', source, '-nr', identity=f'hook_{owner[stage]}.py',
                                  reason='policy-denied-' + stage)
                assert (steps.read_text().split() if steps.exists() else []) == stages[stage]
            else:
                report = cli_success(client, 'create', source, '-nr', '--format=json').json('stdout')
                node = named_node(report, 'policy')
                assert read_json(Path(node['package_folder']) / 'payload.json') == {
                    'material': 'inspected material', 'build_type': 'Release'}


def test_profile_policy_changes_real_host_and_build_packages_and_rejects(tmp_path):
    # F18.T02
    client = recipe_client(tmp_path)
    install_extensions(client, {'extensions/plugins/profile.py': PROFILE_POLICY})
    tool = recipe_file(tmp_path / 'tool', POLICY_PACKAGE, name='policytool', version='1.0').parent
    cli_success(client, 'export', tool)
    source = recipe_file(tmp_path / 'host', POLICY_PACKAGE + '    tool_requires = "policytool/1.0"\n',
                         name='policyhost', version='1.0').parent
    report = cli_success(client, 'create', source, '-nr', '--build=missing', '-s:b',
                         'build_type=Debug', '--format=json').json('stdout')
    for name, context, expected in (('policyhost', 'host', 'Debug'),
                                    ('policytool', 'build', 'RelWithDebInfo')):
        node = named_node(report, name, context)
        assert node['settings']['build_type'] == expected
        assert read_json(Path(node['package_folder']) / 'payload.json') == {
            'material': 'inspected material', 'build_type': expected}
    for flag in ('-s:h', '-s:b'):
        extension_failure(client, 'create', source, '-nr', flag, 'build_type=MinSizeRel',
                          reason='profile-policy-denied-size')


def test_custom_commands_and_subcommands_deliver_inputs_and_files(tmp_path):
    # F18.T03
    client = recipe_client(tmp_path)
    install_extensions(client, {'extensions/commands/cmd_render.py': COMMAND_EXTENSION,
                               'extensions/commands/cmd_toolkit.py': SUBCOMMAND_EXTENSION})
    for text in ('copper alloy', 'silver/ore'):
        destination = tmp_path / (text.split('/')[0] + '.txt')
        report = cli_success(client, 'render', text, destination, '--format=json').json('stdout')
        assert report == {'result': text.upper() + '\n'}
        assert destination.read_text() == text.upper() + '\n'
    destination = tmp_path / 'repeated.txt'
    report = cli_success(client, 'toolkit', 'repeat', 'ore!', '3', destination,
                         '--format=json').json('stdout')
    assert report == {'result': 'ore!ore!ore!'}
    assert destination.read_text() == 'ore!ore!ore!'


def test_unloadable_command_is_identified_without_disabling_builtins(tmp_path):
    # F18.T04
    client = recipe_client(tmp_path)
    install_extensions(client, {'extensions/commands/cmd_broken.py':
                               'raise RuntimeError("command-load-denied")\n'})
    result = cli_success(client, 'config', 'home')
    assert result.text('stdout').strip() == client.env['VELMORA_HOME']
    extension_failure(client, 'broken', identity='cmd_broken.py')
    source = recipe_file(tmp_path / 'usable', '', name='usable', version='1.0').parent
    report = cli_success(client, 'create', source, '-nr', '--format=json').json('stdout')
    assert named_node(report, 'usable')['binary'] == 'Build'


def test_custom_generator_uses_resolved_dependency_files_and_reports_failures(tmp_path):
    # F18.T05
    client = recipe_client(tmp_path)
    install_extensions(client, {'extensions/generators/receipt.py': DEPENDENCY_GENERATOR,
                               'extensions/generators/failing.py': '''class FailingReceipt:
    def __init__(self, velmorafile):
        pass
    def generate(self):
        raise RuntimeError("generator-policy-denied")
'''})
    for name, version, material in (('ore', '1.2', 'copper'), ('alloy', '3.4', 'bronze')):
        source = recipe_file(tmp_path / name, '''    def package(self):
        import os
        from velmora.tools.files import save
        save(self, os.path.join(self.package_folder, "source.txt"), %r)
''' % material, name=name, version=version).parent
        cli_success(client, 'create', source, '-nr')
    source = recipe_file(tmp_path / 'consumer', '    requires = "ore/1.2", "alloy/3.4"\n').parent
    out = tmp_path / 'generated'
    cli_success(client, 'install', source, '-nr', '-g', 'DependencyReceipt', '-of', out)
    assert read_json(out / 'dependencies.json') == {
        'ore': {'version': '1.2', 'content': 'copper'},
        'alloy': {'version': '3.4', 'content': 'bronze'}}
    cli_rejection(client, 'install', source, '-nr', '-g', 'UnavailableReceipt')
    extension_failure(client, 'install', source, '-nr', '-g', 'FailingReceipt',
                      reason='generator-policy-denied')


def test_command_wrapper_changes_executed_command_and_reports_errors(tmp_path):
    # F18.T06: original command is a real Python process; wrapper adds an environment value.
    client = recipe_client(tmp_path)
    install_extensions(client, {'extensions/plugins/cmd_wrapper.py': '''import os
from velmora.errors import VelmoraException

def cmd_wrapper(cmd, velmorafile, **kwargs):
    if os.environ.get("F18_WRAPPER_REJECT"):
        raise VelmoraException("wrapper-policy-denied")
    return "F18_WRAPPED=" + velmorafile.name + " " + cmd
'''})
    for name, value in (('wrappedone', 'copper'), ('wrappedtwo', 'tin')):
        source = recipe_file(tmp_path / name, '''    exports_sources = "command.py"
    def build(self):
        import os, sys, shlex
        for step in ("first", "second"):
            self.run(shlex.quote(sys.executable) + " " + shlex.quote(os.path.join(self.source_folder, "command.py")) + " " + step)
    def package(self):
        from velmora.tools.files import copy
        copy(self, "*.json", self.build_folder, self.package_folder)
''', name=name, version='1.0').parent
        write_file(source / 'command.py', 'import os, json, sys\n'
                   'with open(sys.argv[1] + ".json", "w") as stream:\n'
                   f'    json.dump({{"wrapper": os.environ.get("F18_WRAPPED"), "content": {value!r}}}, stream)\n')
        report = cli_success(client, 'create', source, '-nr', '--format=json').json('stdout')
        for step in ('first', 'second'):
            assert read_json(Path(named_node(report, name)['package_folder']) / (step + '.json')) == {
                'wrapper': name, 'content': value}
    client.env['F18_WRAPPER_REJECT'] = '1'
    extension_failure(client, 'create', source, '-nr', reason='wrapper-policy-denied')


def test_signatures_cover_uploaded_artifacts_and_independent_acquisition(tmp_path):
    # F18.T07: an independent HMAC oracle checks actual transmitted artifact bytes.
    with transfer_world(tmp_path / 'world') as (publisher, repositories, records):
        install_extensions(publisher, {'extensions/plugins/sign/sign.py': SIGNING_EXTENSION})
        node = transfer_package(publisher, Path(publisher.cwd) / 'package')
        unselected = transfer_package(publisher, Path(publisher.cwd) / 'unselected', name='bystander')
        cli_success(publisher, 'cache', 'sign', 'freight/1.0')
        signature = read_json(publisher.cache_path(binary_reference(node), folder='metadata') /
                              'sign/digests.json')
        for reference in (unselected['ref'], binary_reference(unselected)):
            assert not (publisher.cache_path(reference, folder='metadata') / 'sign/digests.json').exists()
        cli_success(publisher, 'upload', 'freight/1.0', '-r', 'store0', '-c')
        artifacts = [r for r in records[0] if r['method'] == 'PUT' and
                     Path(urlsplit(r['path']).path).name == 'velmora_package.tgz']
        assert artifacts
        for artifact in artifacts:
            assert signature['velmora_package.tgz'] == hmac.new(
                SIGNING_KEY, artifact['sent'], hashlib.sha256).hexdigest()
        reader = transfer_reader(tmp_path / 'reader', repositories)
        install_extensions(reader, {'extensions/plugins/sign/sign.py': SIGNING_EXTENSION})
        receipt = tmp_path / 'verified.jsonl'
        reader.env['F18_VERIFICATION_RECEIPT'] = str(receipt)
        consumer, output = signing_consumer(reader, Path(reader.cwd) / 'consumer', 'freight/1.0')
        cli_success(reader, 'install', consumer, '-r', 'store0')
        assert output.read_text() == 'freight source material\n'
        verified = signing_receipts(receipt)
        assert any(item['ref'].startswith('freight/1.0:') and
                   'velmora_package.tgz' in item['checked'] for item in verified)
        assert any(item['ref'] == 'freight/1.0' and 'velmorafile.py' in item['checked']
                   for item in verified)
        # Exported sources are acquired artifacts too; a full download fetches them.
        complete = transfer_reader(tmp_path / 'complete', repositories)
        install_extensions(complete, {'extensions/plugins/sign/sign.py': SIGNING_EXTENSION})
        receipt = tmp_path / 'complete.jsonl'
        complete.env['F18_VERIFICATION_RECEIPT'] = str(receipt)
        cli_success(complete, 'download', 'freight/1.0', '-r', 'store0')
        assert any(item['ref'] == 'freight/1.0' and 'velmora_sources.tgz' in item['checked']
                   for item in signing_receipts(receipt))


def test_verification_rejection_blocks_consumption_and_missing_signer_is_refused(tmp_path):
    # F18.T08: acceptance and rejection use fresh clients and the same signed package.
    with transfer_world(tmp_path / 'world') as (publisher, repositories, records):
        install_extensions(publisher, {'extensions/plugins/sign/sign.py': SIGNING_EXTENSION})
        transfer_package(publisher, Path(publisher.cwd) / 'package')
        cli_success(publisher, 'cache', 'sign', 'freight/1.0')
        cli_success(publisher, 'upload', 'freight/1.0', '-r', 'store0', '-c')
        for rejected in ('', 'recipe', 'binary'):
            reader = transfer_reader(tmp_path / (rejected or 'accepted'), repositories)
            install_extensions(reader, {'extensions/plugins/sign/sign.py': SIGNING_EXTENSION})
            reader.env['F18_VERIFICATION_RECEIPT'] = str(Path(reader.cwd) / 'verified.jsonl')
            reader.env['F18_REJECT_VERIFY'] = rejected
            consumer, output = signing_consumer(reader, Path(reader.cwd) / 'consumer', 'freight/1.0')
            if rejected:
                # A repeated acquisition is judged again: a rejected artifact was never kept.
                for _ in range(2):
                    extension_failure(reader, 'install', consumer, '-r', 'store0', identity='freight/1.0',
                                      reason='verification-policy-denied')
                    assert not output.exists()
            else:
                cli_success(reader, 'install', consumer, '-r', 'store0')
                assert output.read_text() == 'freight source material\n'
        unsigned = recipe_client(tmp_path / 'unsigned')
        transfer_package(unsigned, Path(unsigned.cwd) / 'package')
        cli_rejection(unsigned, 'cache', 'sign', 'freight/1.0')
