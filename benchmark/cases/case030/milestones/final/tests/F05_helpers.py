# feature: F05
"""Source-backed interactive sessions using the shared isolated runner."""
import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from F00_candidate import materialize_candidate, activate_candidate, without_interpretation
from _helpers import observe_call


@contextmanager
def require_exception(exception_type):
    """Require the named carrier with a pickleable assertion on non-refusal."""
    try:
        yield
    except exception_type:
        return
    raise AssertionError(f"Expected {exception_type.__name__} was not raised")


def load_session_module(path):
    """Load a real source file with an ordinary module specification."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _interactive_worker(candidate, action):
    activate_candidate(candidate)
    from zelvori import ezelvori
    return without_interpretation(action)(ezelvori)


def interactive_session(directory, action):
    """Run translation and all result consumption within one capture."""
    directory.mkdir(parents=True)
    result = observe_call(_interactive_worker, materialize_candidate(directory),
                          action, cwd=directory, timeout=360)
    assert result.exception is None
    return result
