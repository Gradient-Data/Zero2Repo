# feature: F08
"""Acceptance of dependency environments, operations, activation and commands."""
import shlex
import sys
from pathlib import Path

from _helpers import read_json, run, write_file
from F01_helpers import cli_success, cli_rejection
from F02_helpers import recipe_client, recipe_file
from F08_helpers import (environment_probe, activated_observation, environment_dependency,
                         environment_consumer, install_environment)


def test_dependency_context_environments(tmp_path):
    client = recipe_client(tmp_path)
    environment_dependency(client, tmp_path / 'runtime', 'toolruntime', 29)
    environment_dependency(client, tmp_path / 'tool', 'tool', 43, requires='toolruntime/1.0')
    environment_dependency(client, tmp_path / 'host', 'hostruntime', 71)
    # The same kind of package as the runtime dependency, but with runtime use
    # explicitly turned off on the requirement.
    recipe_file(tmp_path / 'disabled', '''    package_type = "shared-library"
    def package(self):
        from velmora.tools.files import save
        import os
        save(self, os.path.join(self.package_folder, "bin", "f08-not-runtime"), "")
''', name='runtimedisabled', version='1.0')
    cli_success(client, 'create', tmp_path / 'disabled', '-nr')
    source = environment_consumer(tmp_path / 'consumer', declarations=
        '    requires = "hostruntime/1.0"\n    tool_requires = "tool/1.0"\n'
        '    def requirements(self):\n        self.requires("runtimedisabled/1.0", run=False)\n')
    folder = install_environment(client, source, tmp_path / 'generated')
    build = activated_observation(client, folder, commands=('f08-tool', 'f08-toolruntime'))
    runtime = activated_observation(client, folder, 'velmorarun.sh', name='runtime',
                                    commands=('f08-hostruntime',))
    assert build['commands'] == {'f08-tool': '43', 'f08-toolruntime': '29'}
    assert runtime['commands'] == {'f08-hostruntime': '71'}
    assert build['env']['F08_BUILD_TOOL'] == 'build-tool'
    assert build['env']['F08_RUN_TOOLRUNTIME'] == 'run-toolruntime'
    assert runtime['env']['F08_RUN_HOSTRUNTIME'] == 'run-hostruntime'
    # Successful external observations also prove these absences are not probe failures.
    assert 'F08_RUN_HOSTRUNTIME' not in build['env']
    assert 'F08_BUILD_TOOL' not in runtime['env']
    assert 'F08_RUN_TOOLRUNTIME' not in runtime['env']
    assert not any((Path(entry) / 'f08-not-runtime').exists()
                   for entry in runtime['env']['PATH'].split(':'))


def test_environment_value_operations(tmp_path):
    client = recipe_client(tmp_path)
    for prefix in ('F08_CALLER', 'F08_RECIPE'):
        client.env.update({prefix+'_DEFINE': 'old', prefix+'_UNSET': 'old',
                           prefix+'_WORDS': 'middle', prefix+'_PATHS': '/middle'})
    body = '''    def generate(self):
        from velmora.tools.env import Environment
        env = Environment()
        env.define("F08_RECIPE_DEFINE", "replacement")
        env.unset("F08_RECIPE_UNSET")
        env.prepend("F08_RECIPE_WORDS", "first")
        env.append("F08_RECIPE_WORDS", "last")
        env.prepend_path("F08_RECIPE_PATHS", ["/first", "/second"])
        env.append_path("F08_RECIPE_PATHS", ["/third", "/fourth"])
        env.vars(self).save_script("recipe-operations")
'''
    source = environment_consumer(tmp_path / 'consumer', body)
    profile = write_file(tmp_path / 'operations.profile', '''include(default)
[buildenv]
F08_CALLER_DEFINE=replacement
F08_CALLER_UNSET=!
F08_CALLER_WORDS=+first
F08_CALLER_WORDS+=last
F08_CALLER_PATHS=+(path)/first:/second
F08_CALLER_PATHS+=(path)/third:/fourth
''')
    folder = install_environment(client, source, tmp_path / 'generated', '-pr:h', profile)
    for script, prefix in (('velmorabuild.sh', 'F08_CALLER'),
                           ('recipe-operations.sh', 'F08_RECIPE')):
        observed = activated_observation(client, folder, script, name=prefix)['env']
        assert observed[prefix+'_DEFINE'] == 'replacement'
        assert prefix+'_UNSET' not in observed
        assert observed[prefix+'_WORDS'].split() == ['first', 'middle', 'last']
        assert observed[prefix+'_PATHS'].split(':') == ['/first', '/second', '/middle', '/third', '/fourth']


def test_profile_definitions_override_dependencies(tmp_path):
    client = recipe_client(tmp_path)
    environment_dependency(client, tmp_path / 'dep', 'envprovider', 17, definitions=
        '        self.buildenv_info.define("F08_PRIORITY_BUILD", "dependency-build")\n'
        '        self.runenv_info.define("F08_PRIORITY_RUN", "dependency-run")\n')
    source = environment_consumer(tmp_path / 'consumer', declarations=
        '    requires = "envprovider/1.0"\n    tool_requires = "envprovider/1.0"\n')
    profile = write_file(tmp_path / 'priority.profile', '''include(default)
[buildenv]
F08_PRIORITY_BUILD=profile-build
[runenv]
F08_PRIORITY_RUN=profile-run
''')
    for label, args, expected in (
            ('dependency', (), ('dependency-build', 'dependency-run')),
            ('profile', ('-pr:h', profile), ('profile-build', 'profile-run'))):
        folder = install_environment(client, source, tmp_path / label, *args)
        build = activated_observation(client, folder)['env']
        runtime = activated_observation(client, folder, 'velmorarun.sh', name='runtime')['env']
        assert build['F08_PRIORITY_BUILD'] == expected[0]
        assert runtime['F08_PRIORITY_RUN'] == expected[1]


def test_activation_restores_state_and_configurations(tmp_path):
    client = recipe_client(tmp_path)
    client.env['F08_EXISTING'] = 'caller value'
    client.env['F08_REMOVED'] = 'caller removal value'
    client.env['F08_EMPTY'] = ''
    client.env.pop('F08_ABSENT', None)
    source = environment_consumer(tmp_path / 'consumer')
    folder = tmp_path / 'generated'
    for configuration in ('Release', 'Debug'):
        profile = write_file(tmp_path / (configuration+'.profile'),
            'include(default)\n[buildenv]\nF08_EXISTING='+configuration+
            '\nF08_ABSENT=new value\nF08_REMOVED=!\nF08_EMPTY=filled\n')
        install_environment(client, source, folder, '-pr:h', profile,
                            '-s:h', 'build_type='+configuration)
    # Both installations have finished before either configuration is activated.
    for configuration in ('Release', 'Debug'):
        before, before_file = environment_probe(folder, 'before-'+configuration)
        active, active_file = environment_probe(folder, 'active-'+configuration)
        after, after_file = environment_probe(folder, 'after-'+configuration)
        script = folder / ('velmorabuildenv-'+configuration.lower()+'-x86_64.sh')
        deactivate = folder / ('deactivate_velmorabuildenv-'+configuration.lower()+'-x86_64.sh')
        result = run(('bash', '-c', '\n'.join(['set -e', before,
            'source '+shlex.quote(str(script)), active,
            'source '+shlex.quote(str(deactivate)), after])), cwd=folder, env=client.env)
        assert result.returncode == 0, result
        old, current, restored = [read_json(p)['env'] for p in (before_file, active_file, after_file)]
        assert old['F08_EXISTING'] == 'caller value'
        assert old['F08_REMOVED'] == 'caller removal value'
        assert 'F08_ABSENT' not in old
        assert old['F08_EMPTY'] == ''
        assert current['F08_EXISTING'] == configuration
        assert current['F08_ABSENT'] == 'new value'
        assert 'F08_REMOVED' not in current
        assert current['F08_EMPTY'] == 'filled'
        for variable in ('F08_EXISTING', 'F08_REMOVED', 'F08_ABSENT', 'F08_EMPTY'):
            assert (variable in restored) == (variable in old)
            if variable in old:
                assert restored[variable] == old[variable]


def test_recipe_command_context_and_failure(tmp_path):
    client = recipe_client(tmp_path)
    client.env['F08_SELECTED'] = 'caller-value'
    project = tmp_path / 'consumer'
    work = tmp_path / 'command directory'
    work.mkdir()
    command, output = environment_probe(tmp_path, 'recipe-command')
    exit_command = shlex.join([sys.executable, '-c', 'import sys; sys.exit(23)'])
    for mode in ('success', 'handled', 'failure'):
        body = f'''    def generate(self):
        from velmora.tools.env import Environment
        env = Environment()
        env.define("F08_SELECTED", "selected-value")
        env.vars(self, scope=None).save_script("selected")
        default = Environment()
        default.define("F08_SELECTED", "default-value")
        default.vars(self).save_script("default")
    def build(self):
        import json, os
        self.run({command!r}, env="selected", cwd={str(work)!r})
'''
        if mode != 'success':
            body += f'        result = self.run({exit_command!r}, env="selected", cwd={str(work)!r}, ignore_errors={mode == "handled"!r})\n'
            body += f'        with open({str(tmp_path / (mode+".json"))!r}, "w") as stream:\n            json.dump({{"result": result}}, stream)\n'
        source = environment_consumer(project, body)
        if output.exists():
            output.unlink()
        if mode == 'failure':
            cli_rejection(client, 'build', source.parent, '-nr')
        else:
            cli_success(client, 'build', source.parent, '-nr')
        observed = read_json(output)
        assert observed['env']['F08_SELECTED'] == 'selected-value'
        assert Path(observed['cwd']) == work
        if mode == 'handled':
            assert read_json(tmp_path / 'handled.json')['result'] == 23
