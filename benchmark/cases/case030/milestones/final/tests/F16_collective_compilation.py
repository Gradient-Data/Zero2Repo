# feature: F16
"""Root-source semantics and usable delivery to real MPI participants."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from F16_helpers import collective_observation


ROOT_SOURCE = '''def evaluate(x: int, y: int):
    return x * x - 3 * y + 7

def combine(x: int, y: int):
    return 2 * x + y * y - 5
'''

OTHER_SOURCE = '''def evaluate(x: int, y: int):
    return 4 * x + y - 19

def combine(x: int, y: int):
    return x - 6 * y + 23
'''


def test_default_root_collective_module_delivery(tmp_path):
    def check(comm, ezelvori, root_input, other_input, language, root_only):
        source = root_input if comm.rank == 0 else other_input
        module = ezelvori(source, comm=comm, language=language, folder=language)
        # Every rank consumes the delivered module with its own data; a copied
        # root answer, local-source compilation or root-only result cannot pass.
        for x, y in ((comm.rank + 2, 3 * comm.rank - 4),
                     (-5 - comm.rank, comm.rank + 7)):
            assert module.evaluate(x, y) == x * x - 3 * y + 7
            assert module.combine(x, y) == 2 * x + y * y - 5

    collective_observation(tmp_path / 'default', ROOT_SOURCE, OTHER_SOURCE, check)


def test_nonzero_root_and_root_only_function_delivery(tmp_path):
    def check(comm, ezelvori, root_input, other_input, language, root_only):
        source = root_input.evaluate if comm.rank == 1 else other_input.evaluate
        function = ezelvori(source, comm=comm, root=1, bcast=not root_only,
                           language=language, folder=language)
        if root_only and comm.rank != 1:
            # None is the positive public return carrier for no delivery.
            assert function is None
        else:
            for x, y in ((comm.rank + 2, 3 * comm.rank - 4),
                         (-5 - comm.rank, comm.rank + 7)):
                assert function(x, y) == x * x - 3 * y + 7

    # Fresh jobs and folders keep both arms identical except for delivery mode.
    for root_only in (False, True):
        collective_observation(tmp_path / str(root_only), ROOT_SOURCE, OTHER_SOURCE,
                               check, root_only=root_only)
