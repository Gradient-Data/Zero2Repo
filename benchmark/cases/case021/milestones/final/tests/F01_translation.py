# feature: F01
"""Acceptance checks for translation, diagnostics and compilation policies."""
from _helpers import temporary_project, run_python, parse_json
from F01_helpers import translate_source, execute_native, source_diagnostics


def test_f01_t01():
    # Both input languages and both output modes are required; two paired
    # projects cover the members without an unnecessary Cartesian product.
    cases = [('.py', (), '.c', 'def evaluate(x):\n    return sum(v * v for v in x) + len(x)\n',
              '[subject.evaluate(x) for x in ([2, -5, 7], [], [11, 3])]', [81, 0, 132], None),
             ('.pyx', ('--cplus',), '.cpp',
              'def evaluate(int x, int y):\n    cdef long result = x * y + x - y\n    return result\n',
              '[subject.evaluate(x, y) for x, y in [(6, 9), (-4, 7), (12, -3)]]',
              [51, -39, -21], 'c++')]
    for suffix, options, native_suffix, text, expression, expected, language in cases:
        with temporary_project() as project:
            source = project.write('translation_probe' + suffix, text)
            result = translate_source(project, source, options=options)
            assert result.returncode == 0, result.text('stderr')
            generated = source.with_suffix(native_suffix)
            assert generated.is_file()
            source.unlink()
            assert execute_native(project, source.stem, generated, expression,
                                  language=language) == expected


def test_f01_t02():
    # Exercise each rejection independently; explanations are human-readable.
    cases = [('def broken(:\n    pass\n', 1),
             ('cdef MissingNativeType value\n', 1),
             ('cdef int *value\ncdef double scalar\nvalue = scalar\n', 3)]
    with temporary_project() as project:
        valid = project.write('valid.pyx', 'def value():\n    return 17\n')
        assert translate_source(project, valid).returncode == 0
        for index, (text, line) in enumerate(cases):
            source = project.write(f'invalid_{index}.pyx', text)
            result = translate_source(project, source)
            assert result.returncode == 1, result.text('stderr')
            records = source_diagnostics(result, source)
            assert any(int(record['line']) == line and int(record['column']) >= 0
                       and record['explanation'].strip() for record in records), result.text('stderr')


def test_f01_t03():
    with temporary_project() as project:
        valid = project.write('valid.pyx', 'def value():\n    return 19\n')
        assert translate_source(project, valid).returncode == 0
        cases = [(project.path('absent_source.pyx'), 'absent_source.pyx'),
                 (project.write('declarations.pyx', 'cimport absent_declarations\n'),
                  'absent_declarations.pxd'),
                 (project.write('inclusion.pyx', 'include "absent_fragment.pxi"\n'),
                  'absent_fragment.pxi')]
        for source, missing in cases:
            result = translate_source(project, source)
            assert result.returncode == 1, result.text('stderr')
            # Missing-input names are application data, not pinned prose.
            assert missing in result.text('stderr'), result.text('stderr')


def test_f01_t04():
    with temporary_project() as project:
        source = project.write('configuration.pyx', 'def value():\n    return 23\n')
        assert translate_source(project, source, options=('-X', 'cdivision=True')).returncode == 0
        for options, status in [(('--no-such-compilation-option',), 2), (('-X', 'cdivision=invalid'), 1)]:
            result = translate_source(project, source, options=options)
            assert result.returncode == status, result.text('stderr')
            assert result.stderr
        # Exercise build configuration through the documented build entry,
        # not the option parser in isolation. Only documented ValueError counts.
        result = run_python('''
import json, sys
from Velora.Build import veloraize
outcomes = []
for directives in ({'cdivision': True}, {'nonexistent_directive': True}, {'language_level': 'invalid'}):
    try:
        veloraize(sys.argv[1], compiler_directives=directives, quiet=True, force=True)
    except ValueError:
        outcomes.append('invalid-configuration')
    else:
        outcomes.append('translated')
print(json.dumps(outcomes))
''', args=[str(source)], env=project.environment())
        assert result.returncode == 0, result.text('stderr')
        assert parse_json(result.stdout) == ['translated', 'invalid-configuration', 'invalid-configuration']


DIVISION = 'def divide(int a, int b):\n    return a // b\n'
CALL_DIVISION = '[subject.divide(a, b) for a, b in [(-7, 3), (7, -3), (8, 3)]]'


def test_f01_t05():
    for source_setting, expected in [(None, [-2, -2, 2]), (False, [-3, -3, 2])]:
        with temporary_project() as project:
            prefix = '' if source_setting is None else '# velora: cdivision=False\n'
            source = project.write('build_policy.pyx', prefix + DIVISION)
            result = run_python('''
import sys
from Velora.Build import veloraize
veloraize(sys.argv[1], compiler_directives={'cdivision': True}, quiet=True)
''', args=[str(source)], env=project.environment())
            assert result.returncode == 0, result.text('stderr')
            assert execute_native(project, source.stem, source.with_suffix('.c'), CALL_DIVISION) == expected


def test_f01_t06():
    # The original's file header overrides the CLI (documented baseline bug).
    # Retain effective CLI behavior without a conflicting header as well.
    for header, options, expected in [('', ('-X', 'cdivision=True'), [-2, -2, 2]),
                                      ('', ('-X', 'cdivision=False'), [-3, -3, 2]),
                                      ('# velora: cdivision=True\n', ('-X', 'cdivision=False'), [-2, -2, 2])]:
        with temporary_project() as project:
            source = project.write('command_policy.pyx', header + DIVISION)
            result = translate_source(project, source, options=options)
            assert result.returncode == 0, result.text('stderr')
            assert execute_native(project, source.stem, source.with_suffix('.c'), CALL_DIVISION) == expected


def test_f01_t07():
    with temporary_project() as project:
        source = project.write('local_policy.pyx', '''
import velora

def global_divide(int a, int b):
    return a // b

@velora.cdivision(True)
def local_divide(int a, int b):
    before = a // b
    with velora.cdivision(False):
        inner = a // b
    after = a // b
    return before, inner, after

def block_divide(int a, int b):
    before = a // b
    with velora.cdivision(True):
        middle = a // b
        with velora.cdivision(False):
            inner = a // b
        restored = a // b
    after = a // b
    return before, middle, inner, restored, after
''')
        result = translate_source(project, source, options=('-X', 'cdivision=False'))
        assert result.returncode == 0, result.text('stderr')
        values = execute_native(project, source.stem, source.with_suffix('.c'),
            '[[subject.global_divide(a,b), subject.local_divide(a,b), subject.block_divide(a,b)] '
            'for a,b in [(-7,3), (7,-3)]]')
        assert values == [[-3, [-2, -3, -2], [-3, -2, -3, -2, -3]]] * 2


def test_f01_t08():
    with temporary_project() as project:
        source = project.write('warning_policy.pyx', 'def value():\n    return 29\n    return 31\n')
        ordinary = translate_source(project, source)
        assert ordinary.returncode == 0, ordinary.text('stderr')
        assert source_diagnostics(ordinary, source), ordinary.text('stderr')
        assert any(record['warning'] for record in source_diagnostics(ordinary, source)), \
            ordinary.text('stderr')
        assert execute_native(project, source.stem, source.with_suffix('.c'), 'subject.value()') == 29
        disabled = translate_source(project, source, options=('-X', 'warn.unreachable=False'))
        assert disabled.returncode == 0, disabled.text('stderr')
        assert disabled.stderr == b''
        fatal = translate_source(project, source, options=('--warning-errors',))
        assert fatal.returncode == 1, fatal.text('stderr')
        assert source_diagnostics(fatal, source), fatal.text('stderr')
        # Control: statements after a conditional return are reachable. The
        # warning (and its fatal form) must follow reachability, not appear for
        # every source or for any statement that follows a return keyword.
        reachable = project.write('reachable_policy.pyx',
                                  'def value(x):\n    if x:\n        return 29\n    return 31\n')
        for options in ((), ('--warning-errors',)):
            result = translate_source(project, reachable, options=options)
            assert result.returncode == 0, result.text('stderr')
            assert result.stderr == b'', result.text('stderr')
        assert execute_native(project, reachable.stem, reachable.with_suffix('.c'),
                              '[subject.value(1), subject.value(0)]') == [29, 31]
