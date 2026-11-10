# feature: F07
"""Exactly the three planned hardened-matching acceptance checks.

Growth uses dense and no-match workloads with fixed product
settings, alternating nine-sample medians, and a test-owned monotonic clock.
Reference ratios (2026-10-26, isolated offline non-root acceptance run):
collection dense 10.343, collection empty 11.284, existence disabled 10.928,
existence enabled 11.052. All clear the strict <30 bound with ample reserve.
Full calibration records are kept in F07 author evidence.
The order-sensitive dense workload also measured 10.001 in the 2026-10-27
offline non-root review run (20,000 to 200,000 bytes, nine-sample medians).
"""

from F01_helpers import operation, successful_values
from F03_helpers import option_request
from F07_helpers import hardened_matching, growth_driver, assert_input_growth


def test_hardened_default_and_matching_semantics(hardened_matching):
    """F07.T01: hardening preserves complete ordinary matching outcomes."""
    scenarios = [
        ("owl", [(b"xowl owlz", [[1, 4], [5, 8]]), (b"ow l", [])]),
        ("é", [(b"!\xc3\xa9\xc3\xa9!", [[1, 3], [3, 5]]), (b"ee", [])]),
        ("[bd-f]+", [(b"abcdefgbdf", [[1, 2], [3, 6], [7, 10]]), (b"acg", [])]),
        ("(ab|cd){2,3}", [(b"!abcdab!cdcd!ab!", [[1, 7], [8, 12]]),
                           (b"ab!cd", [])]),
        ("a|ab|bcdef", [(b"abcdef ab a", [[0, 2], [7, 9], [10, 11]])]),
        ("aba", [(b"ababa aba", [[0, 3], [6, 9]])]),
        ("a+&aa", [(b"aaaaa", [[0, 2], [2, 4]]), (b"a!a", [])]),
        ("(~(a)&_){2,3}", [(b"a12a\xff\x00\n4a", [[1, 3], [4, 7]])]),
        ("~(ab)", [(b"ab", [[0, 1], [1, 2], [2, 2]]),
                   (b"xaby", [[0, 4], [4, 4]]), (b"", [[0, 0]])]),
        ("a(?=b)", [(b"ab!a!ba!ab", [[0, 1], [8, 9]]), (b"a!b", [])]),
        ("a(?!b)", [(b"ab!a!ba!ab", [[3, 4], [6, 7]]), (b"ab", [])]),
        ("(?<=b)a", [(b"ab!a!ba!ab", [[6, 7]]), (b"b!a", [])]),
        ("(?<!b)a", [(b"ab!a!ba!ab", [[0, 1], [3, 4], [8, 9]]), (b"ba", [])]),
        ("(?<=L[0-9]+)x(?=[ab]*R)", [(b"L1xR L123xabbaR Q12xR", [[2, 3], [9, 10]])]),
        (r"\b[a-z]+\b", [(b"!ab 12c de!", [[1, 3], [8, 10]])]),
        (r"\Aab\z", [(b"ab", [[0, 2]]), (b"xab", []), (b"abx", [])]),
        ("a*", [(b"ba", [[0, 0], [1, 2], [2, 2]]), (b"", [[0, 0]]),
                 (b"aa", [[0, 2], [2, 2]])]),
        ("", [(b"\xc3\xa9", [[0, 0], [1, 1], [2, 2]]), (b"", [[0, 0]])]),
    ]
    requests = [option_request(pattern,
                [operation("find_all", data) for data, _ in rows], hardened=True)
                for pattern, rows in scenarios]
    observations = hardened_matching.json(requests).value
    assert len(observations) == len(scenarios), observations
    for (pattern, rows), observation in zip(scenarios, observations):
        assert observation["default_hardened"] is False, observation
        assert successful_values(observation) == [spans for _, spans in rows], (
            pattern, rows, observation)


def test_hardened_collection_input_growth(growth_driver, capsys):
    """F07.T02: complete dense and empty results within the promised growth."""
    with capsys.disabled():
        assert_input_growth(growth_driver, pattern=".*[^q]|[q]", block=b"q",
                            operation="find_all", hardened=True, dense=True)
        assert_input_growth(growth_driver, pattern="q+r", block=b"q",
                            operation="find_all", hardened=True,
                            controls=[(b"qqr", [[0, 3]]), (b"rqq", [])])
        # Both required bytes occur, but their order prevents the long branch.
        # Alphabet-only pruning cannot establish the promised growth here.
        # Fixed-width short matches keep all nine complete measurements bounded.
        assert_input_growth(growth_driver, pattern=".*qq|[qr]{100}", block=b"qr",
                            operation="find_all", hardened=True, dense=True,
                            match_width=100,
                            controls=[(b"qrqq", [[0, 4]]), (b"qr", [])])


def test_existence_input_growth_with_each_hardening_setting(growth_driver, capsys):
    """F07.T03: each fixed setting meets the bound and still detects real hits."""
    with capsys.disabled():
        for hardened in (False, True):
            assert_input_growth(growth_driver, pattern="q+r", block=b"q",
                                operation="is_match", hardened=hardened,
                                controls=[(b"qqr", True), (b"rqq", False)])
