# feature: F08
"""Container sessions including the candidate's installed Fortran resources."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from F00_candidate import materialize_candidate, activate_candidate, without_interpretation, require_compiled
from _helpers import observe_call


def _container_worker(source, language, directory, candidate):
    activate_candidate(candidate)
    from zelvori import ezelvori
    return require_compiled(ezelvori(source, language=language, folder=str(directory)), language)


def _consume_natively(consume):
    def run(value):
        return without_interpretation(consume)(value)
    return run


def translate_containers(source, language, directory, consume):
    directory.mkdir(parents=True)
    candidate = materialize_candidate(directory, fortran_containers=language == 'fortran')
    result = observe_call(_container_worker, source, language, directory, candidate,
                          cwd=directory, consume=_consume_natively(consume), timeout=480)
    assert result.exception is None
    return result
