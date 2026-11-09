# feature: F15
"""Host OpenMP outcomes, independent of scheduling and execution order."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from F00_oracle import host_numpy as np
from F15_helpers import openmp_observation, WORKSHARING, SYNCHRONIZATION, CONTEXT, LOOPS


def test_parallel_worksharing_reduction_single_sections(tmp_path):
    def check(module):
        for n, seed in ((19, 3), (38, -2)):
            a = np.full(n, 5, dtype=np.int64)
            marks = np.full(6, -999, dtype=np.int64)
            result = module.work(a, marks, n, seed)
            terms = np.arange(n, dtype=np.int64)**2 + seed
            assert result == int(terms.sum())
            np.testing.assert_array_equal(a, 5 + terms)
            # marks[2] would be written by a third participant.
            np.testing.assert_array_equal(marks, [seed, seed * 2, -999, seed + 7, seed + 11, seed + 13])
    openmp_observation(tmp_path / 'worksharing', WORKSHARING, check)


def test_critical_atomic_barrier_task_completion(tmp_path):
    def check(module):
        for n, seed in ((257, 4), (1031, -3)):
            a = np.full(2, -999, dtype=np.int64)
            seen = np.full(4, -999, dtype=np.int64)
            result = module.sync(a, seen, n, seed)
            updates = sum(t + j + 1 for t in range(2) for j in range(n))
            tasks = sum(k + seed + k*k + seed for k in range(n))
            assert result == tasks
            np.testing.assert_array_equal(a, [seed, seed + 1])
            np.testing.assert_array_equal(seen, [2*seed + 1, 2*seed + 1, seed + updates, seed + updates])
    openmp_observation(tmp_path / 'synchronization', SYNCHRONIZATION, check)


def test_runtime_context_private_default_shared_and_loop_data(tmp_path):
    def check(module):
        for n, seed in ((23, 6), (41, -4)):
            out = np.full((2, 8), -999, dtype=np.int64)
            a = np.full(n, 9, dtype=np.int64)
            assert module.context(out, a, n, seed) == 2
            np.testing.assert_array_equal(out, [[seed, 2, 1, 1, 0, 2, 2, 0],
                                               [seed+17, 2, 1, 1, 1, 2, 2, 0]])
            np.testing.assert_array_equal(a, 9 + seed + np.arange(n))
    openmp_observation(tmp_path / 'context', CONTEXT, check)


def test_combined_parallel_and_vectorized_loop_results(tmp_path):
    def check(module):
        for n, seed in ((17, 2), (46, -5)):
            a = np.full(n, 3, dtype=np.int64)
            b = np.full(n, 8, dtype=np.int64)
            i = np.arange(n, dtype=np.int64)
            expected_a = 3 + seed + i*i + 8 + seed - i
            expected_b = 8 + seed - i
            report = np.full(2, -999, dtype=np.int64)
            result = module.loops(a, b, report, n, seed)
            assert result == int((seed+i*i).sum())
            np.testing.assert_array_equal(report, [int((seed-i).sum()), int(expected_a.sum())])
            np.testing.assert_array_equal(a, expected_a)
            np.testing.assert_array_equal(b, expected_b)
    openmp_observation(tmp_path / 'loops', LOOPS, check)
