# feature: F02
"""Recipe inputs and public observations for recipe acceptance."""
from pathlib import Path

from _helpers import PRODUCT_PYTHON, read_bytes, run, write_file
from F01_helpers import configuration_client, install_bundle, cli_success, named_node, settings_profile


def recipe_client(root):
    client = configuration_client(root)
    install_bundle(client, Path(root) / 'configuration', {'profiles/default': settings_profile()})
    return client


def recipe_file(root, body, *, name='specimen', version='2.7'):
    return write_file(Path(root) / 'velmorafile.py',
                      'from velmora import VelmoraFile\nclass Recipe(VelmoraFile):\n'
                      + f'    name = {name!r}\n    version = {version!r}\n' + body)


def installed_graph(client, path, *args):
    return cli_success(client, 'install', path, '-nr', '--format=json', *args).json('stdout')


def inspected_recipe(client, path):
    return cli_success(client, 'inspect', path, '--format=json').json('stdout')


def yaml_document(client, path):
    """Read YAML using the provisioned parser, independently of pytest's Python.

    File, launch and parsing errors remain failures with their original cause
    or captured process diagnostics. Consume the complete JSON output.
    """
    source = read_bytes(path)
    parser = '''import json, sys, yaml
document = yaml.safe_load(sys.stdin.buffer)
encoded = json.dumps(document, allow_nan=False)
if json.loads(encoded) != document:
    raise ValueError("YAML document cannot be transferred losslessly as JSON")
sys.stdout.write(encoded)
'''
    result = run((PRODUCT_PYTHON, '-I', '-c', parser),
                 cwd=client.cwd, env=client.env, stdin=source)
    assert result.returncode == 0, result
    return result.json('stdout')


def consumer_dependency(report, name='choice'):
    return named_node(report, name)
