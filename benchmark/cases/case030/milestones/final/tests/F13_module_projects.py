# feature: F13
"""Acceptance of module semantics, project selection and dependency failures."""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _helpers import run_command, write_text
from F03_helpers import ConfigurationSession, require_success
from F13_helpers import (module_project, selected_project, integer_program,
                         extension_values, check_selected_delivery, directory_project)


def test_cooperating_modules_and_initialization(tmp_path):
    session = ConfigurationSession(tmp_path / 'modules')
    for target in ('c', 'fortran'):
        root = session.root / target
        source = module_project(root)
        python = run_command([sys.executable, source], cwd=root, env=session.env)
        require_success(python)
        expected = [int(line) for line in python.stdout.splitlines()]
        assert expected == [271, 48, -67]
        # Single-file compilation consumes already translated dependencies.
        for relative in ('parcel/base.py', 'parcel/left.py', 'parcel/right.py', 'submitted.py'):
            require_success(session.command('compile', root / relative, '--language', target, cwd=root))
        assert integer_program(root / 'submitted', session) == expected
        assert extension_values(root, 'submitted',
            ['module.calculate(7, 2)', 'module.calculate(-3, 5)',
             'module.calculate(0, -4)'], session) == ([271], [48, -67, 8])


def test_project_file_selection(tmp_path):
    session = ConfigurationSession(tmp_path / 'selection')
    for mode in ('files', 'pattern', 'manifest'):
        root = session.root / mode
        files = selected_project(root)
        selections = {'files': ['-f', *files], 'pattern': ['-g', 'chosen/*.py'],
                      'manifest': ['-d', 'selection.txt']}
        require_success(session.command('make', *selections[mode], '--language', 'c', cwd=root))
        check_selected_delivery(root, session)


def test_project_build_systems_and_destination(tmp_path):
    session = ConfigurationSession(tmp_path / 'builds')
    # Selection spellings are covered separately. These four builds cover both
    # promised targets with each build system, without multiplying other axes.
    for target, system in [('c', 'meson'), ('fortran', 'meson'),
                           ('c', 'cmake'), ('fortran', 'cmake')]:
        root = session.root / (target + '_' + system)
        files = selected_project(root)
        destination = root / 'delivered'
        require_success(session.command('make', '-f', *files, '--language', target,
            '--build-system', system, '--output', destination, cwd=root))
        check_selected_delivery(destination, session)


def test_project_dependency_errors(tmp_path):
    session = ConfigurationSession(tmp_path / 'dependencies')
    baseline = session.root / 'baseline'
    files = directory_project(baseline)
    require_success(session.command('make', '-f', *files, '--language', 'c', cwd=baseline))
    assert integer_program(baseline / 'main', session) == [63]

    root = session.root / 'cycle'
    files = directory_project(root, cycle=True)
    cycle = session.command('make', '-f', *files, '--language', 'c', cwd=root)
    assert cycle.returncode == 1, (cycle.stdout, cycle.stderr)
    # Dependency identifiers are caller data in the diagnostic explanation;
    # no fixed English sentence or list separator is part of the shell.
    records = dependency_records(cycle)
    assert records, (cycle.stdout, cycle.stderr)
    for participant in (root / 'pkg/one', root / 'pkg/two'):
        assert any(information_contains(message, str(participant))
                   for _, message in records), (participant, cycle.stdout)

    root = session.root / 'missing'
    root.mkdir()
    source = write_text(root, 'main.py',
        "from absent_dependency import compute\n\nif __name__ == '__main__':\n    print(compute())\n")
    missing = session.command('make', '-f', source, '--language', 'c', cwd=root)
    assert missing.returncode == 1, (missing.stdout, missing.stderr)
    records = dependency_records(missing)
    assert any(filename == source and information_contains(message, 'absent_dependency')
               for filename, message in records), (missing.stdout, missing.stderr)


def dependency_records(result):
    """Parse fatal source diagnostic records; explanation sentences are opaque."""
    grammar = re.compile(
        r'^ \|fatal \[(?:None|syntactic|semantic|cwrapper)\]: (.*?)'
        r'(?: \[\d+(?:,\d+)?\])?\| (.+)$', re.MULTILINE)
    return [(Path(filename), message) for filename, message in grammar.findall(result.stdout)]


def information_contains(message, identifier):
    """Match an intact caller identifier, independently of surrounding prose."""
    return re.search(r'(?<![\w/])' + re.escape(identifier) + r'(?![\w/])', message) is not None
