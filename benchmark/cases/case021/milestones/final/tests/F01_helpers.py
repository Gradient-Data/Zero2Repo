# feature: F01
"""Public translation and native execution support for source compilation tests."""
import re
from _helpers import build_extensions, parse_json, run_module, run_python


def translate_source(project, source, *, options=(), output=None):
    args = [*options]
    if output is not None:
        args += ['-o', str(output)]
    return run_module('velora', [*args, str(source)], env=project.environment())


def execute_native(project, name, generated, expression, *, language=None):
    spec = {'name': name, 'sources': [str(generated)]}
    if language is not None:
        spec['language'] = language
    result = build_extensions(project, [spec], env=project.environment())
    assert result.returncode == 0, result.text('stderr') + result.text()
    result = run_python(
        f'import json\nimport {name} as subject\nprint(json.dumps({expression}))',
        env=project.environment())
    assert result.returncode == 0, result.text('stderr')
    return parse_json(result.stdout)


def source_diagnostics(result, source):
    """Read complete CLI location records, without inspecting message wording."""
    # Public stderr record: <path>:<line>:<column>: <explanation>.
    pattern = re.compile(r'^(?P<warning>warning: )?' + re.escape(str(source)) +
                         r':(?P<line>\d+):(?P<column>\d+): (?P<explanation>.+)$')
    return [match.groupdict() for line in result.text('stderr').splitlines()
            if (match := pattern.fullmatch(line))]
