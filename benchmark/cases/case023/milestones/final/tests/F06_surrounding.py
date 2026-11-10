# feature: F06
"""Acceptance checks for surrounding text through the public matching API."""

from F01_helpers import (
    assert_rejections, assert_success_cases, matching, operation, pattern_request,
)
from F04_helpers import assert_boolean_languages
from F05_helpers import boundary_compilation


def test_context_polarity_position_and_extent(matching):
    """F06.T01: context gates a candidate at its position without consuming it."""
    text = b"ab!a!b!ba!ab"
    scenarios = [
        ("a(?=b)", [(text, [[0, 1], [10, 11]]), (b"a", []),
                     (b"a!b", []), (b"ba", []), (b"", [])]),
        ("a(?!b)", [(text, [[3, 4], [8, 9]]), (b"ab", []),
                     (b"a!b", [[0, 1]]), (b"a", [[0, 1]]), (b"", [])]),
        ("(?<=b)a", [(text, [[8, 9]]), (b"a", []), (b"b!a", []),
                      (b"ba", [[1, 2]]), (b"", [])]),
        ("(?<!b)a", [(text, [[0, 1], [3, 4], [10, 11]]), (b"ba", []),
                      (b"b!a", [[2, 3]]), (b"a", [[0, 1]]), (b"", [])]),
        # Assertions alone accept empty spans wherever their condition holds.
        ("(?=b)", [(b"abab", [[1, 1], [3, 3]]), (b"", [])]),
        ("(?<=a)", [(b"abab", [[1, 1], [3, 3]])]),
        ("(?!b)", [(b"ab", [[0, 0], [2, 2]])]),
        ("(?<!a)", [(b"ab", [[0, 0], [2, 2]])]),
        # Lookahead text is not consumed: the next candidate may start in it.
        ("a(?=a)", [(b"aaa", [[0, 1], [1, 2]])]),
        ("[ab](?=ab)", [(b"ababab", [[1, 2], [3, 4]])]),
        # Lookbehind sees text consumed by the preceding match.
        ("(?<=a)a", [(b"aaa", [[1, 2], [2, 3]])]),
        ("(?<!b)b", [(b"bb", [[0, 1]]), (b"abb", [[1, 2]])]),
        # A context that accepts the empty string always occurs.
        ("(?<!a*)b", [(b"b", []), (b"ab", [])]),
        ("(?<!x?)b", [(b"b", []), (b"xb", [])]),
        # A leading negative lookahead excludes candidates starting there.
        ("(?!a)[ab]", [(b"ab", [[1, 2]])]),
        ("(?!ab)[a-z]{2}", [(b"abacab", [[1, 3], [3, 5]])]),
    ]
    cases = []
    for pattern, rows in scenarios:
        actions, expected = [], []
        for data, spans in rows:
            actions.extend([operation("is_match", data), operation("find_all", data)])
            expected.extend([bool(spans), spans])
        cases.append((pattern_request(pattern, actions), expected))
    assert_success_cases(matching, cases)


def test_composed_regular_contexts_and_intersection(matching):
    """F06.T02: all context and consuming constraints retain their meaning."""
    scenarios = [
        ("(?<=L)(?=a[bc])[a-z]{2}(?=R)", [],
         [(b"LabR LacR", [[1, 3], [6, 8]]), (b"XabR", []), (b"LabX", []),
          (b"LadR", []), (b"LabR LabR", [[1, 3], [6, 8]])]),
        # Each rejection below violates a different surrounding condition.
        ("(?<=L)(?<!XL)ab(?=R)(?!RX)", [],
         [(b"LabR", [[1, 3]]), (b"XLabR", []), (b"LabRX", []),
          (b"XabR", []), (b"LabX", [])]),
        ("(?<=[PQ]P)(?<=Q[PQ])ab", [],
         [(b"QPab", [[2, 4]]), (b"PPab", []), (b"QQab", []), (b"Pab", [])]),
        ("(?<=L[0-9]{2})x(?=(red|blue)[0-9]{1,3}!)", [],
         [(b"L12xred1!", [[3, 4]]), (b"L98xblue123!", [[3, 4]]),
          (b"L1xred1!", []), (b"L123xred1!", []), (b"L12xgreen1!", []),
          (b"L12xred!", []), (b"L12xred1234!", [])]),
        ("(?<=AB|CD)x", [],
         [(b"ABx CDx ADx CBx A!Bx", [[2, 3], [6, 7]]), (b"x", [])]),
        ("(?<=L[0-9]{1,3})x", [],
         [(b"L1x L12x L123x L1234x", [[2, 3], [7, 8], [13, 14]]),
          (b"Lx", []), (b"Q12x", [])]),
        ("(?<=L[0-9]+)x(?=[ab]*R)", [],
         [(b"L1xR", [[2, 3]]), (b"L12345xabbaR", [[6, 7]]),
          (b"LxR", []), (b"Q123xR", []), (b"L12xabX", [])]),
        ("(?<!L[0-9]{1,3})x(?![ab]+R)", [],
         [(b"Q12xR", [[3, 4]]), (b"L12xR", []), (b"Q12xabR", []),
          (b"L1234xR", [[5, 6]])]),
        ("(?=(ab|cd)[0-9]{2})[a-z]+", [],
         [(b"ab12 cd34 ef56 ab1", [[0, 2], [5, 7]]), (b"abxx12", [])]),
        ("((?<=L)[a-z]+(?=R))&[a-m]{2}", [],
         [(b"LabR LnzR LabcR XabR LabX", [[1, 3]])]),
        # Context must not count toward the width required by intersection.
        ("(?=ab)a+&_", [],
         [(b"ab", [[0, 1]]), (b"baba", [[1, 2]]), (b"aa", [])]),
        ("(?=ab)a+&__", [], [(b"ab", []), (b"baba", [])]),
        # A failed context only removes that candidate; a shorter span from the
        # same start whose context holds is selected instead.
        ("[a-z]+(?=b)", [], [(b"aab", [[0, 2]])]),
        ("a+(?=a)", [], [(b"aaa", [[0, 2]])]),
        ("[a-z]+(?!b)", [], [(b"abb", [[0, 3]]), (b"ab!", [[0, 2]])]),
        # Alternatives of different widths and long unbounded runs in context.
        ("(?<=a|bc)x", [], [(b"ax bcx cx", [[1, 2], [5, 6]])]),
        ("(?<=ab|c)x", [], [(b"abx cx bx", [[2, 3], [5, 6]])]),
        ("(?<=L[0-9]+)x", [], [(b"L123456789012x", [[13, 14]]),
                                (b"Q123456789012x", [])]),
        ("x(?=[ab]*R)", [], [(b"xabababababababR", [[0, 1]]),
                              (b"xababababababX", [])]),
        ("(?<!L[0-9]+)x", [], [(b"L123456789012x", []),
                                (b"Q123456789012x", [[13, 14]])]),
        # Context text follows the active case setting.
        ("(?i)(?<=a)b(?=c)", [], [(b"ABC", [[1, 2]]), (b"aBc", [[1, 2]]),
                                   (b"xBC", [])]),
        ("(?i:(?<!a)b)", [], [(b"AB", []), (b"xB", [[1, 2]])]),
    ]
    assert_boolean_languages(matching, scenarios)


def test_bounded_lookbehind_alternation(matching, boundary_compilation):
    """F06.T03: supported branch shapes match; overlapping unequal ones refuse."""
    scenarios = [
        ("(?<=A)abc|(?<=C)abz", [],
         [(b"Aabc Cabz Aabz Cabc Zabc", [[1, 4], [6, 9]]), (b"abc abz", [])]),
        ("(?<=A)abc|(?<=C)abc", [],
         [(b"Aabc Cabc Zabc", [[1, 4], [6, 9]]), (b"abc", [])]),
        ("(?<=A)abc|(?<=C)xyzw", [],
         [(b"Aabc Cxyzw Axyzw Cabc", [[1, 4], [6, 10]]), (b"abc xyzw", [])]),
        ("(?<=A)(abc|abcd)", [],
         [(b"Aabcd Aabc Cabcd", [[1, 5], [7, 10]]), (b"abc abcd", [])]),
        ("(?<=A)abc|(?<=A)abcd", [],
         [(b"Aabcd Aabc Cabcd", [[1, 5], [7, 10]])]),
        ("(?<=[AB]{1,2})xy|(?<=CD)zt", [],
         [(b"Axy BBxy CDzt Qxy Azt CDxy", [[1, 3], [6, 8], [11, 13]])]),
        # Variable-length branches with disjoint first bytes.
        ("(?<=A)ab+|(?<=C)xy+", [],
         [(b"Aabbb Cxyyy Axy Cab", [[1, 5], [7, 11]])]),
        ("(?<=A)a[0-9]*|(?<=C)b[a-z]*", [],
         [(b"Aa123 Cbxyz Ab Ca", [[1, 5], [7, 11]])]),
    ]
    assert_boolean_languages(matching, scenarios)
    assert_rejections(boundary_compilation, [
        "(?<=A)abc|(?<=C)abcd",
        "(?<=A)ab|(?<=C)ab|(?<=E)abc",
    ], "unsupported")


def test_nonleading_lookbehind_is_unsupported(matching, boundary_compilation):
    """F06.T04: mandatory consuming prefixes cannot precede lookbehind."""
    assert_boolean_languages(matching, [
        ("(?<=ab)c", [], [(b"abc abxc c", [[2, 3]])]),
        ("(?<!ab)c", [], [(b"abc abxc c", [[7, 8], [9, 10]])]),
    ])
    assert_rejections(boundary_compilation, [
        "ab(?<=ab)c", "ab(?<!xy)c", "[ab]+(?<=a)c", "(ab){2}(?<!xy)c",
    ], "unsupported")
