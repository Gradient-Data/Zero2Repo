# feature: F08
"""External environment observations and real local dependency fixtures."""
import shlex
import sys
from pathlib import Path

from _helpers import read_json, run, write_file
from F01_helpers import cli_success
from F02_helpers import recipe_file
from F05_helpers import dependency_recipe


ENVIRONMENT_PROBE = '''import json, os, subprocess, sys
with open(sys.argv[1], 'w') as stream:
    json.dump({'env': dict(os.environ), 'cwd': os.getcwd(),
               'commands': {name: subprocess.check_output([name], text=True).strip()
                            for name in sys.argv[2:]}}, stream)
'''


def environment_probe(root, name='observation', commands=()):
    root = Path(root)
    script = write_file(root / 'observe.py', ENVIRONMENT_PROBE)
    output = root / (name + '.json')
    return shlex.join([sys.executable, str(script), str(output), *commands]), output


def activated_observation(client, folder, script='velmorabuild.sh', *, name='observation', commands=()):
    command, output = environment_probe(folder, name, commands)
    result = run(('bash', '-c', 'set -e\nsource ' + shlex.quote(str(Path(folder) / script))
                  + '\n' + command), cwd=folder, env=client.env)
    assert result.returncode == 0, result
    return read_json(output)


def environment_dependency(client, root, name, number, *, requires=None, definitions=''):
    # These are actual ELF programs and shared libraries without a runtime search path.
    # Executing each program needs both the executable and loader environment.
    body = f'''    package_type = "shared-library"
    settings = "os", "arch", "build_type"
'''
    if requires:
        body += f'    requires = {requires!r}\n'
    body += f'''    def package(self):
        import os, subprocess
        from velmora.tools.files import save
        lib = os.path.join(self.package_folder, "lib")
        bin = os.path.join(self.package_folder, "bin")
        os.makedirs(lib, exist_ok=True)
        os.makedirs(bin, exist_ok=True)
        save(self, "value.c", "int {name}_value(void) {{ return {number}; }}")
        save(self, "main.c", '#include <stdio.h>\\nint {name}_value(void);\\nint main(void) {{ printf("%d\\\\n", {name}_value()); return 0; }}')
        subprocess.check_call(["gcc", "-shared", "-fPIC", "value.c", "-o", os.path.join(lib, "lib{name}.so")])
        subprocess.check_call(["gcc", "main.c", "-L"+lib, "-l{name}", "-o", os.path.join(bin, "f08-{name}")])
    def package_info(self):
        self.buildenv_info.define("F08_BUILD_{name.upper()}", "build-{name}")
        self.runenv_info.define("F08_RUN_{name.upper()}", "run-{name}")
'''
    body += definitions
    return dependency_recipe(client, root, name, body=body, create=True)


def environment_consumer(root, body='', declarations=''):
    return recipe_file(root, '    settings = "os", "arch", "build_type"\n'
                       '    generators = "VirtualBuildEnv", "VirtualRunEnv"\n'
                       + declarations + body, name='environment-consumer', version='1.0')


def install_environment(client, source, output, *args):
    cli_success(client, 'install', Path(source).parent, '-nr', '-of', output, *args)
    return Path(output)
