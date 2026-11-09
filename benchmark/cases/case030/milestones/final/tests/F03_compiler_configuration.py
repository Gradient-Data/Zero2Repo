# feature: F03
"""Acceptance tests for compiler configuration selection and lifecycle."""
import copy
from collections import Counter
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import make_environment, read_json, write_json, write_text
from F03_helpers import (ConfigurationSession, configuration_advisories, require_advisory_subjects, native_probe_config,
                         require_config_error, require_success)


def test_configuration_export(tmp_path):
    session = ConfigurationSession(tmp_path / 'export')
    exported = {}
    for family in ('GNU', 'intel', 'nvidia', 'LLVM'):
        path = session.root / f'{family}.json'
        require_success(session.command('config', 'export', path, '--compiler-family', family))
        configuration = read_json(path)
        assert set(configuration) == {'c', 'c++', 'fortran'}
        for language, settings in configuration.items():
            assert isinstance(settings['exec'], str) and settings['exec']
        require_success(session.command('config', 'check', path))
        exported[family] = configuration
    # Four distinct compiler families cannot share one configuration document.
    documents = [repr(sorted(value.items())) for value in exported.values()]
    assert len(set(documents)) == 4, exported
    assert session.build_and_run('reuse', ['--compiler-config', session.root / 'GNU.json']) == [137]


def test_configuration_selection(tmp_path):
    session = ConfigurationSession(tmp_path / 'selection')
    exported = session.export_gnu()
    # The default and explicit family choices both deliver a real program.
    assert session.build_and_run('default') == [137]
    first = native_probe_config(session, exported, 913)
    second = native_probe_config(session, exported, 527)
    require_success(session.command('config', 'register', 'environment_choice', second))
    environment = make_environment({'ZELVORI_DEFAULT_COMPILER': 'environment_choice'}, base=session.env)
    assert Counter(session.build_and_run('environment', env=environment)) == Counter([527, 137])
    assert session.build_and_run('explicit_family', ['--compiler-family', 'GNU'], env=environment) == [137]
    assert Counter(session.build_and_run('explicit_file', ['--compiler-config', first], env=environment)) == Counter([913, 137])


def test_configuration_validation(tmp_path):
    session = ConfigurationSession(tmp_path / 'validation')
    valid = session.export_gnu()
    require_success(session.command('config', 'check', session.root / 'export.json'))
    # Every supported language is checked through the same public entry.
    for language in ('c', 'c++', 'fortran'):
        require_success(session.command('config', 'check',
                        write_json(session.root, 'single.json', {language: valid[language]})))
    by_link_name = copy.deepcopy(valid)
    by_link_name['c']['libs'] = ['m']
    require_success(session.command('config', 'check', write_json(session.root, 'link.json', by_link_name)))
    invalid = [write_text(session.root, 'malformed.json', '{"c":')]
    invalid.append(write_json(session.root, 'language.json', {**valid, 'rust': {}}))
    # Rotate the damaged language so every supported language's settings are
    # validated, not only the first one; the other languages stay valid.
    languages = ('c', 'c++', 'fortran')
    for index, (setting, wrong_type) in enumerate([
            ('exec', []), ('general_flags', '-O0'), ('release_flags', {}),
            ('debug_flags', 3), ('mpi_exec', []), ('libs', 'm')]):
        config = copy.deepcopy(valid)
        config[languages[index % 3]][setting] = wrong_type
        invalid.append(write_json(session.root, f'type_{setting}.json', config))
    paths = [(setting, kind, path) for setting in ('include', 'libdir', 'dependencies', 'libs')
             for kind, path in [('relative', 'missing/location'),
                                ('absent', str(session.root / 'does-not-exist'))]]
    for index, (setting, kind, path) in enumerate(paths):
        config = copy.deepcopy(valid)
        config[languages[index % 3]][setting] = [path]
        invalid.append(write_json(session.root, f'{setting}_{kind}.json', config))
    for path in invalid:
        require_config_error(session.command('config', 'check', path))


def test_configuration_advisories(tmp_path):
    session = ConfigurationSession(tmp_path / 'advisories')
    valid = session.export_gnu()
    baseline = session.command('config', 'check', session.root / 'export.json')
    assert configuration_advisories(baseline) == []

    unknown = copy.deepcopy(valid)
    unknown['c']['caller_extension'] = ['-O1']
    omitted = copy.deepcopy(valid)
    del omitted['fortran']['debug_flags']
    combined = copy.deepcopy(unknown)
    del combined['fortran']['debug_flags']
    expected_unknown = ('caller_extension', 'c')
    expected_omitted = ('debug_flags', 'fortran')
    for filename, configuration, expected in [
        ('unknown.json', unknown, {expected_unknown}),
        ('omitted.json', omitted, {expected_omitted}),
        ('combined.json', combined, {expected_unknown, expected_omitted}),
    ]:
        path = write_json(session.root, filename, configuration)
        result = session.command('config', 'check', path)
        require_advisory_subjects(result, expected)


def test_registration_lifecycle(tmp_path):
    session = ConfigurationSession(tmp_path / 'lifecycle')
    exported = session.export_gnu()
    custom = native_probe_config(session, exported, 683)
    require_success(session.command('config', 'register', 'local_toolchain', custom))
    assert Counter(session.build_and_run('registered', ['--compiler-family', 'local_toolchain'])) == Counter([683, 137])
    # A refused duplicate leaves the existing registration selecting its own toolchain.
    replacement = native_probe_config(session, exported, 691)
    require_config_error(session.command('config', 'register', 'local_toolchain', replacement))
    assert Counter(session.build_and_run('still_registered', ['--compiler-family', 'local_toolchain'])) == Counter([683, 137])
    require_success(session.command('config', 'remove', 'local_toolchain'))
    assert not (session.home / 'local_toolchain').exists()
    # Selection is retried through a fresh public command after removal.
    source = write_text(session.root, 'after_removal.py', "if __name__ == '__main__':\n    print(137)\n")
    rejected = session.command('compile', '--language', 'c', '--compiler-family', 'local_toolchain', source)
    assert rejected.returncode == 2, rejected
    assert any(line.startswith('usage:') for line in rejected.stderr.splitlines()), rejected
    require_config_error(session.command('config', 'remove', 'local_toolchain'))
    require_config_error(session.command('config', 'remove', '../outside'))
    # Registration's containment failure is reported on stdout by this entry.
    require_config_error(session.command('config', 'register', '../outside', custom), channel='stdout')
    # The refused name resolves to <ZELVORI_CONFIG_HOME>/../outside; nothing is created there.
    assert not (session.home.parent / 'outside').exists()
