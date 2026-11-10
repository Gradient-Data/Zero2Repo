# feature: F11
"""Requirement-backed command execution through the public run entry."""
import shlex
import sys

from _helpers import read_json, write_file
from F01_helpers import cli_success, cli_rejection
from F02_helpers import recipe_client, recipe_file
from F08_helpers import environment_probe
from F11_helpers import runnable_package


def test_run_requirement_inputs_contexts_and_host_priority(tmp_path):
    client = recipe_client(tmp_path)
    runnable_package(client, tmp_path / 'host', 'hostapp', 'host-material', variable='F11_HOST')
    runnable_package(client, tmp_path / 'build', 'buildapp', 'build-material', variable='F11_BUILD', build_tool=True)
    recipe = recipe_file(tmp_path / 'consumer', '    requires = "hostapp/1.0"\n    tool_requires = "buildapp/1.0"\n')
    # Context measurements keep the recipe, command and state identical.
    for context, expected in [('host', 'host-material'), ('build', 'build-material'), (None, 'host-material')]:
        command, receipt = environment_probe(tmp_path / 'probe', commands=('f11-command',))
        cli_success(client, 'run', recipe.parent, command, '-nr',
                    *(('--context', context) if context else ()))
        result = read_json(receipt)
        assert result['commands'] == {'f11-command': expected}
        assert result['cwd'] == str(tmp_path)
        if context in ('host', None):
            assert result['env']['F11_HOST'] == 'host-material'
        if context in ('build', None):
            assert result['env']['F11_BUILD'] == 'build-material'
        if context == 'host':
            assert 'F11_BUILD' not in result['env']
        if context == 'build':
            assert 'F11_HOST' not in result['env']
        receipt.unlink()
    command, receipt = environment_probe(tmp_path / 'direct', commands=('f11-command',))
    cli_success(client, 'run', command, '--requires=hostapp/1.0', '--tool-requires=buildapp/1.0', '-nr')
    assert read_json(receipt)['commands'] == {'f11-command': 'host-material'}
    profile = write_file(tmp_path / 'tools.profile', 'include(default)\n[tool_requires]\nbuildapp/1.0\n')
    cli_success(client, 'run', command, '-pr:h', profile, '-nr')
    assert read_json(receipt)['commands'] == {'f11-command': 'build-material'}


def test_run_installation_and_execution_failures(tmp_path):
    client = recipe_client(tmp_path)
    runnable_package(client, tmp_path / 'app', 'hostapp', 'executed-material', variable='F11_HOST')
    command, receipt = environment_probe(tmp_path / 'probe', commands=('f11-command',))
    cli_success(client, 'run', command, '--requires=hostapp/1.0', '-nr')
    assert read_json(receipt)['commands'] == {'f11-command': 'executed-material'}
    receipt.unlink()
    cli_rejection(client, 'run', command, '--requires=absent/1.0', '-nr')
    assert not receipt.exists()
    cli_rejection(client, 'run', 'f11-executable-not-installed', '--requires=hostapp/1.0', '-nr')
    failure_script = write_file(tmp_path / 'failure.py', 'import pathlib, sys\npathlib.Path(sys.argv[1]).write_text("command executed")\nsys.exit(23)\n')
    executed = tmp_path / 'executed.txt'
    cli_rejection(client, 'run', shlex.join([sys.executable, str(failure_script), str(executed)]), '--requires=hostapp/1.0', '-nr')
    assert executed.read_text() == 'command executed'
