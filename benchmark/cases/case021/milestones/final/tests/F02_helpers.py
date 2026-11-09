# feature: F02
"""Build real extensions and compare application observations with Python 3.12."""
import pickle
import textwrap
from _helpers import temporary_project, build_extensions, run_python
from F01_helpers import translate_source


def check_python_execution(source, driver, *, options=(), reference=True):
    """Run identical driving operations in fresh native and Python processes."""
    source, driver = textwrap.dedent(source), textwrap.dedent(driver)
    with temporary_project() as project:
        path = project.write('execution_subject.pyx', source)
        translated = translate_source(project, path, options=options)
        assert translated.returncode == 0, translated.text('stderr')
        built = build_extensions(project, [{'name': path.stem,
                                  'sources': [str(path.with_suffix('.c'))]}],
                                 env=project.environment())
        assert built.returncode == 0, built.text('stderr') + built.text()
        trailer = '\nimport pickle\nprint(pickle.dumps(exercise(subject)).hex())\n'
        def run(prefix, python=None):
            result = run_python(prefix + driver + trailer, python=python,
                                env=project.environment())
            assert result.returncode == 0, result.text('stderr') + result.text()
            return pickle.loads(bytes.fromhex(result.text().strip()))
        if reference:
            expected = run('import types\nsubject = types.ModuleType("oracle")\n'
                           f'exec(compile({source!r}, {str(path)!r}, "exec"), subject.__dict__)\n',
                           '/usr/bin/python3.12')
            actual = run('import execution_subject as subject\n')
            assert actual == expected, (actual, expected)
        else:
            return run('import execution_subject as subject\n')
