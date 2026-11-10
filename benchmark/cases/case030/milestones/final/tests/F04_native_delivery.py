# feature: F04
"""Acceptance tests for native source, artifact delivery and build selection."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import make_environment, run_command, run_python, write_json, write_text
from F01_helpers import require_no_runnable_artifact, require_source_error
from F00_candidate import require_native_program
from F03_helpers import ConfigurationSession, require_success, native_probe_config
from F04_helpers import (delivery_source, call_delivered, run_delivered_program,
                         target_source, consume_translation, require_invocation_error,
                         require_native_failure)


def test_native_artifact_delivery(tmp_path):
    session = ConfigurationSession(tmp_path / 'native')
    for name, options, target in [('default', [], 'fortran'),
                                  ('c', ['--language', 'c'], 'c'),
                                  ('fortran', ['--language', 'fortran'], 'fortran')]:
        root = session.root / name
        root.mkdir()
        source = delivery_source(root)
        require_success(session.command('compile', source, *options))
        assert target_source(root, target).is_file()
        call_delivered(root, session)
        run_delivered_program(root, session)


def test_translation_only_delivery(tmp_path):
    session = ConfigurationSession(tmp_path / 'translation')
    # The identical source has a live native-build baseline.
    baseline = session.root / 'baseline'
    baseline.mkdir()
    require_success(session.command('compile', delivery_source(baseline), '--language', 'c'))
    call_delivered(baseline, session)
    run_delivered_program(baseline, session)
    for target in ('c', 'fortran', 'python'):
        root = session.root / target
        root.mkdir()
        source = delivery_source(root)
        output = root / 'output'
        require_success(session.command('compile', source, '--language', target,
                                        '--convert-only', '--output', output))
        # Neither the destination nor the source location receives a runnable artifact.
        require_no_runnable_artifact(root)
        if target == 'python':
            result = run_command([sys.executable, output / 'submitted.py'], cwd=output, env=session.env)
            require_success(result)
            assert [int(line) for line in result.stdout.splitlines()] == [76, 8]
        else:
            consume_translation(output, target, session)
    root = session.root / 'cpp'
    root.mkdir()
    source = write_text(root, 'submitted.py', 'counter: int = 29\nratio: float = 1.5\nenabled: bool = True\n')
    require_success(session.command('compile', source, '--language', 'c++', '--convert-only'))
    require_no_runnable_artifact(root)
    translated = target_source(root, 'c++')
    assert translated.is_file()
    # Use the published native declarations, rather than matching source text.
    driver = write_text(root, 'read.cpp', '#include "' + str(translated) + '"\n#include <iostream>\n#include <type_traits>\nstatic_assert(std::is_integral_v<decltype(submitted::counter)>);\nstatic_assert(std::is_floating_point_v<decltype(submitted::ratio)>);\nstatic_assert(std::is_same_v<decltype(submitted::enabled), bool>);\nint main() { submitted::init(); std::cout << submitted::counter << " " << submitted::ratio << " " << submitted::enabled; }\n')
    require_success(run_command(['g++', driver, '-o', root / 'reader'], cwd=root))
    result = run_command([root / 'reader'], cwd=root)
    require_success(result)
    assert result.stdout.split() == ['29', '1.5', '1']


def test_build_options_and_destination(tmp_path):
    session = ConfigurationSession(tmp_path / 'options')
    config = session.export_gnu()
    # Reuse the earlier feature's real native library and required-header probe.
    probe = native_probe_config(session, config, 419)
    import json
    settings = json.loads(probe.read_text())['c']
    root = session.root / 'input'
    root.mkdir()
    source = write_text(root, 'submitted.py', 'def calculate(x: int, y: int) -> int:\n    return x * x - 3 * y + 7\n')
    output = session.root / 'chosen'
    # Both compilation paths require their own supplied macro; neither may be ignored.
    native = Path(settings['include'][0])
    write_text(native, 'options.h', """
#ifndef F04_NATIVE
#error Native options were ignored
#endif
void f03_emit(int);
static void __attribute__((constructor)) f04_initialize(void) { f03_emit(419); }
""")
    wrapper_header = write_text(native, 'wrapper_options.h', """
#ifndef F04_WRAPPER
#error Wrapper options were ignored
#endif
#include <stdio.h>
static void __attribute__((constructor)) f04_wrapper_initialize(void) { puts("421"); }
""")
    require_success(session.command('compile', source, '--language', 'c', '--output', output,
        '--flags=-include options.h -DF04_NATIVE=1',
        f'--wrapper-flags=-include {wrapper_header} -DF04_WRAPPER=1',
        '--include', native, '--libdir', native, '--libs', 'probe'))
    # Observe both the linked library effect and the submitted computation.
    result = run_python('import submitted; print(submitted.calculate(6, 2))', cwd=output, env=session.env)
    require_success(result)
    values = [int(line) for line in result.stdout.splitlines()]
    # The caller prints its result once. Header initialization can run in
    # multiple translation units, so its multiplicity is not a build promise.
    assert values.count(37) == 1, values
    assert set(values) == {37, 419, 421}, values
    assert not (root / 'submitted').exists()


def test_native_build_failures(tmp_path):
    session = ConfigurationSession(tmp_path / 'failures')
    baseline = session.root / 'baseline'
    baseline.mkdir()
    require_success(session.command('compile', delivery_source(baseline), '--language', 'c'))
    call_delivered(baseline, session)
    config = session.export_gnu()
    config['c']['exec'] = str(session.root / 'absent_compiler')
    path = write_json(session.root, 'unavailable.json', config)
    for name, options in [('compiler', ['--compiler-config', path]),
                           ('library', ['--libs', 'f04_library_that_does_not_exist'])]:
        root = session.root / name
        root.mkdir()
        source = delivery_source(root)
        result = session.command('compile', source, '--language', 'c', *options)
        require_native_failure(result)
        require_no_runnable_artifact(root)


def test_invalid_translation_invocations(tmp_path):
    session = ConfigurationSession(tmp_path / 'invalid')
    source = delivery_source(session.root)
    require_success(session.command('compile', source, '--semantic-only'))
    other = write_text(session.root, 'not_python.txt', source.read_text())
    for arguments in [(session.root / 'missing.py',), (other,), (source, '--language', 'unknown')]:
        require_invocation_error(session.command('compile', *arguments))


def test_debug_selection(tmp_path):
    session = ConfigurationSession(tmp_path / 'debug')
    config = session.export_gnu()
    native = session.root / 'debug_support'
    native.mkdir()
    header = write_text(native, 'mode.h', '''
#include <stdio.h>
static void __attribute__((constructor)) mode_report(void) { printf("%d\\n", F04_MODE); }
''')
    config['c']['release_flags'] = ['-DF04_MODE=0']
    config['c']['debug_flags'] = ['-DF04_MODE=1']
    config['c']['general_flags'] += ['-include', str(header)]
    path = write_json(session.root, 'modes.json', config)
    for name, environment, options, expected in [
        ('default', None, [], 0), ('environment', '1', [], 1),
        ('explicit_on', None, ['--debug'], 1),
        ('explicit_off', '1', ['--no-debug'], 0)]:
        root = session.root / name
        root.mkdir()
        source = delivery_source(root)
        env = make_environment({'ZELVORI_DEBUG_MODE': environment}, base=session.env)
        require_success(session.command('compile', source, '--language', 'c',
            '--compiler-config', path, *options, env=env))
        require_native_program(root / 'submitted')
        result = run_command([root / 'submitted'], cwd=root, env=env)
        require_success(result)
        lines = [int(line) for line in result.stdout.splitlines()]
        # C initialization and program output may use separate stdio buffers.
        # Preserve program order while checking every initialization effect.
        assert [value for value in lines if value not in (0, 1)] == [76, 8]
        modes = [value for value in lines if value in (0, 1)]
        assert modes and all(value == expected for value in modes)


def test_validation_mode_precedence(tmp_path):
    session = ConfigurationSession(tmp_path / 'precedence')
    # Semantic-only takes priority over conversion, with successful validation
    # and no delivered source or runnable artifact.
    for name, modes in [('semantic', ['--semantic-only']),
                         ('combined', ['--semantic-only', '--convert-only'])]:
        root = session.root / name
        root.mkdir()
        source = delivery_source(root)
        require_success(session.command('compile', source, *modes))
        require_no_runnable_artifact(root)
        assert not target_source(root, 'fortran').exists()
    root = session.root / 'type_error'
    root.mkdir()
    source = write_text(root, 'submitted.py', 'def compute(x: int):\n    return missing + x\n')
    result = session.command('compile', source, '--semantic-only', '--convert-only')
    require_source_error(result, source, 'semantic', {2})
    require_no_runnable_artifact(root)
    # Malformed syntax is still rejected in the presence of every mode.
    root = session.root / 'malformed'
    root.mkdir()
    source = write_text(root, 'submitted.py', 'def broken(:\n    pass\n')
    result = session.command('compile', source, '--syntax-only', '--semantic-only', '--convert-only')
    require_source_error(result, source, 'None', None)
    require_no_runnable_artifact(root)
