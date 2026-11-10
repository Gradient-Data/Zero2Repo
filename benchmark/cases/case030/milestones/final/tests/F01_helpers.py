# feature: F01
"""Public source compilation and source-diagnostic observations."""

import re
import sys
from pathlib import Path

# Support independent importlib collection before the feature test module.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _helpers import make_environment, observe_call, run_command, write_text

from F00_candidate import materialize_candidate, activate_candidate, without_interpretation, require_native_program, require_compiled


def _translate_in_worker(source, language, folder, candidate):
    activate_candidate(candidate)
    from zelvori import ezelvori
    return require_compiled(ezelvori(source, language=language, folder=folder), language)


def _consume_natively(consume):
    def run(value):
        return without_interpretation(consume)(value)
    return run


def translate_and_observe(source, language, directory, consume):

    directory.mkdir(parents=True)
    result = observe_call(
        _translate_in_worker, source, language, str(directory),
        materialize_candidate(directory), cwd=directory,
        consume=_consume_natively(consume), timeout=360,
    )
    assert result.exception is None
    return result


def compile_source(directory, source, *, mode="--semantic-only", language="fortran"):
    directory.mkdir(parents=True)
    path = write_text(directory, "submitted.py", source)
    result = run_command(
        [str(Path(sys.executable).with_name("zelvori")), "compile", *([mode] if mode else []),
         "--language", language, str(path)], cwd=directory, env=make_environment({"PYTHONPATH": str(materialize_candidate(directory))}),
        timeout=240,
    )
    return result, path


def require_source_error(result, path, stage, lines):
    """Read the CLI's severity, stage, source and location fields, not prose."""
    assert result.returncode == 1, (result.stdout, result.stderr)
    records = []
    # This is the product's diagnostic record grammar; message text is opaque.
    grammar = re.compile(
        r"^ \|(?:error|fatal) \[(None|syntactic|semantic)\]: (.*?)"
        r"(?: \[(\d+)(?:,\d+)?\])?\| .+$", re.MULTILINE,
    )
    for category, filename, line in grammar.findall(result.stdout):
        records.append((category, Path(filename), int(line) if line else None))
    assert any(category == stage and filename == path and (lines is None or line in lines)
               for category, filename, line in records), (result.stdout, result.stderr)


def require_no_runnable_artifact(directory):
    # Validation has no native module or script executable, including in its
    # documented build directory. Source and parser cache files are permitted.
    import importlib.machinery
    import os

    for path in directory.rglob("*"):
        if path.is_file():
            assert not any(path.name.endswith(suffix)
                           for suffix in importlib.machinery.EXTENSION_SUFFIXES), path
            assert not os.access(path, os.X_OK), path
