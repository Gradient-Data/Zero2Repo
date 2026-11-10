# feature: F20
"""Acceptance checks for native application entry support and dependency limits."""
from _helpers import temporary_project, run_command, parse_json, unique_module_name
from F20_helpers import build_embedded_application


def test_f20_t01():
    with temporary_project() as project:
        executable = build_embedded_application(project, '''
            import json, os, sys
            cdef long scale = int(os.environ['EMBED_SCALE'])
            cdef long total = sum(int(value) for value in sys.argv[1:-1])
            print(json.dumps({'main': __name__, 'arguments': sys.argv[1:],
                              'answer': total * scale, 'tag': sys.argv[-1]}))
        ''')
        for args, scale, expected in [(['4', '-7', '12', 'first tag'], '3', 27),
                                       (['-9', '2', '第二次'], '-4', 28)]:
            result = run_command([executable, *args], env=project.environment(
                overrides={'EMBED_SCALE': scale}))
            assert result.returncode == 0, result.text('stderr')
            assert parse_json(result.stdout) == {
                'main': '__main__', 'arguments': args, 'answer': expected, 'tag': args[-1]}


def test_f20_t02():
    with temporary_project() as project:
        executable = build_embedded_application(project, '''
            import json, sys
            if sys.argv[1] == 'raise':
                raise ValueError('application rejected the request')
            print(json.dumps({'answer': int(sys.argv[1]) * 7 + 2}))
        ''')
        success = run_command([executable, '6'], env=project.environment())
        assert success.returncode == 0, success.text('stderr')
        assert parse_json(success.stdout) == {'answer': 44}
        failure = run_command([executable, 'raise'], env=project.environment())
        assert failure.returncode == 1, failure.text('stderr')
        assert failure.stderr.strip(), failure


def test_f20_t03():
    with temporary_project() as project:
        first = unique_module_name('linked_first')
        second = unique_module_name('linked_second')
        executable = build_embedded_application(project, f'''
            import json, sys
            import {first}, {second}
            print(json.dumps([{first}.calculate(int(value)) +
                              {second}.calculate(int(value)) for value in sys.argv[1:]]))
        ''', modules={first: '''
            def calculate(long value):
                cdef long squared = value * value
                return squared + 3
        ''', second: f'''
            from {first} import calculate as square_offset
            def calculate(long value):
                return square_offset(value + 1) - 2 * value
        '''})
        # No extension was built; the source files have also been removed.
        # Only the linked executable can provide these uniquely named modules.
        result = run_command([executable, '-3', '0', '8'], env=project.environment())
        assert result.returncode == 0, result.text('stderr')
        assert parse_json(result.stdout) == [25, 7, 135]


def test_f20_t04():
    with temporary_project() as project:
        dependency = unique_module_name('runtime_dependency')
        project.write(dependency + '.py', '''
def transform(values):
    return [value * 5 - 4 for value in values]
''')
        executable = build_embedded_application(project, f'''
            import json, sys
            try:
                import {dependency} as dependency
            except ImportError:
                print(json.dumps({{'failure': 'import'}}), flush=True)
                raise
            print(json.dumps({{'values': dependency.transform([int(v) for v in sys.argv[1:]])}}))
        ''')
        # The dependency exists while building, but remains a runtime input.
        available = project.path('available')
        unavailable = project.path('unavailable')
        available.mkdir()
        unavailable.mkdir()
        project.path(dependency + '.py').rename(available / (dependency + '.py'))
        for directory, succeeds in [(available, True), (unavailable, False)]:
            result = run_command([executable, '-2', '0', '9'],
                env=project.environment(import_paths=[directory]))
            if succeeds:
                assert result.returncode == 0, result.text('stderr')
                assert parse_json(result.stdout) == {'values': [-14, -4, 41]}
            else:
                assert result.returncode == 1, result.text('stderr')
                assert result.stderr.strip(), result
                assert parse_json(result.stdout) == {'failure': 'import'}
