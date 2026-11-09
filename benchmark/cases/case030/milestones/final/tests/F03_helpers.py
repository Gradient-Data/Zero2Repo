# feature: F03
"""Compiler configuration observations through the public command line."""
import copy
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from F00_candidate import materialize_candidate, require_native_program
from _helpers import make_environment, read_json, run_command, write_json, write_text


class ConfigurationSession:
    """Keep subprocesses independent while sharing one private registration home."""

    def __init__(self, root):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        candidate = materialize_candidate(root)
        self.home = root / 'registrations'
        self.env = make_environment({
            'PYTHONPATH': str(candidate), 'ZELVORI_CONFIG_HOME': str(self.home),
            'ZELVORI_DEFAULT_COMPILER': None, 'NO_COLOR': '1', 'TERM': 'dumb',
        })

    def command(self, *args, env=None, cwd=None):
        return run_command(
            [str(Path(sys.executable).with_name('zelvori')), *map(str, args)],
            cwd=self.root if cwd is None else cwd,
            env=self.env if env is None else env, timeout=360,
        )

    def export_gnu(self):
        path = self.root / 'export.json'
        require_success(self.command('config', 'export', path, '--compiler-family', 'GNU'))
        return read_json(path)

    def build_and_run(self, name, selection=(), env=None):
        directory = self.root / name
        directory.mkdir()
        source = write_text(directory, 'submitted.py',
                            "if __name__ == '__main__':\n    print(137)\n")
        built = self.command('compile', '--language', 'c', *selection, source,
                             env=env, cwd=directory)
        require_success(built)
        require_native_program(directory / 'submitted')
        executed = run_command([str(directory / 'submitted')], cwd=directory, env=self.env)
        require_success(executed)
        return [int(line) for line in executed.stdout.splitlines()]


def require_success(result):
    assert result.returncode == 0, (result.argv, result.stdout, result.stderr)


def require_config_error(result, *, channel='stderr'):
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert any(line.startswith('|Error|:') for line in getattr(result, channel).splitlines()), result


def native_probe_config(session, exported, value):
    """Build a real external library and header whose initialization is visible.

    The header requires both the configured include search path and macro
    option; its initializer calls the configured library. The library emits
    once even when more than one translation unit includes the header.
    """
    native = session.root / f'native_{value}'
    native.mkdir()
    header = write_text(native, 'probe.h', '''
#ifndef F03_EXEC_ENABLED
#error The configured executable is required
#endif
#ifndef F03_VALUE
#error The configured macro is required
#endif
void f03_emit(int);
static void __attribute__((constructor)) f03_initialize(void) { f03_emit(F03_VALUE); }
''')
    library_source = write_text(native, 'probe.c', '''
#include <stdio.h>
void f03_emit(int value) {
    static int emitted = 0;
    if (!emitted) { emitted = 1; printf("%d\\n", value); }
}
''')
    compiler = shutil.which('gcc')
    assert compiler is not None, 'The acceptance environment requires GNU C'
    obj = native / 'probe.o'
    require_success(run_command([compiler, '-c', '-fPIC', library_source, '-o', obj], cwd=native))
    archive = native / 'libprobe.a'
    require_success(run_command(['ar', 'rcs', archive, obj], cwd=native))
    # A caller-provided compiler driver delegates every build to the real GNU
    # toolchain; the required macro makes its selection observable in the build.
    driver = write_text(native, 'compiler-driver',
                        '#!/bin/sh\nexec ' + compiler + ' -DF03_EXEC_ENABLED=1 "$@"\n')
    driver.chmod(0o700)
    config = copy.deepcopy(exported)
    config['c']['exec'] = str(driver)
    config['c']['general_flags'] += ['-include', header.name, f'-DF03_VALUE={value}']
    config['c']['include'] = [str(native)]
    config['c']['dependencies'] = [str(archive)]
    path = write_json(session.root, f'custom_{value}.json', config)
    return path


def configuration_advisories(result):
    """Read the stated warning carrier, leaving explanatory wording opaque."""
    require_success(result)
    return [line.removeprefix('|Warning|:').strip()
            for line in result.stderr.splitlines() if line.startswith('|Warning|:')]


def require_advisory_subjects(result, subjects):
    """Check caller-supplied identifiers in the warning information payload."""
    records = configuration_advisories(result)
    assert records, result
    for setting, language in subjects:
        patterns = [re.compile(r'(?<![\w+])' + re.escape(value) + r'(?![\w+])')
                    for value in (setting, language)]
        assert any(all(pattern.search(record) for pattern in patterns)
                   for record in records), (subjects, result)
