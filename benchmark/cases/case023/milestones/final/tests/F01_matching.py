# feature: F01
"""Acceptance tests for public pattern matching and match selection.

Each function implements one planned entry. Expected successful results were
observed through the original product and checked against FP-01's rules; they
are fixed here, never obtained from a second product query during judging.
"""

from F01_helpers import (
    matching, matching_library, bounded_matching, byte_compilation,
    operation, pattern_request, assert_success_cases, assert_rejections,
)


def test_pattern_composition(matching):
    # F01.T01: operands, literal escapes, inclusive ranges, and precedence.
    scenarios = [
        ("owl", [(b"owl", [[0, 3]], True),
                 (b"xowl owlz", [[1, 4], [5, 8]], False),
                 (b"ow l", [], False), (b"ow", [], False)]),
        (r"\(\[a\]\)\+\?\.", [(b"([a])+?.", [[0, 8]], True),
                                  (b"x([a])+?.z", [[1, 9]], False),
                                  (b"([b])+?.", [], False),
                                  (b"([a])xxx", [], False)]),
        ("[bd-f]+", [(b"abcdefgbdf", [[1, 2], [3, 6], [7, 10]], False),
                     (b"bdef", [[0, 4]], True), (b"acg", [], False)]),
        ("ab|cd", [(b"ab", [[0, 2]], True), (b"cd", [[0, 2]], True),
                   (b"abcd", [[0, 2], [2, 4]], False), (b"acbd", [], False)]),
        ("(ab|cd)e", [(b"abe", [[0, 3]], True), (b"cde", [[0, 3]], True),
                      (b"ab", [], False), (b"cd", [], False),
                      (b"abxe", [], False),
                      (b"abe cde", [[0, 3], [4, 7]], False)]),
    ]
    cases = []
    for pattern, rows in scenarios:
        actions, expected = [], []
        for data, spans, full in rows:
            actions.extend([operation("find_all", data), operation("is_full_match", data)])
            expected.extend([spans, full])
        cases.append((pattern_request(pattern, actions), expected))
    assert_success_cases(matching, cases)


def test_repetition_forms_and_scope(matching):
    # F01.T02: each count form needs its own boundary observations.
    scenarios = [
        ("za*b", [(b"zb", True), (b"zaaaab", True)]),
        ("za+b", [(b"zb", False), (b"zab", True), (b"zaaaab", True)]),
        ("za?b", [(b"zb", True), (b"zab", True), (b"zaab", False)]),
        ("za{2}b", [(b"zab", False), (b"zaab", True), (b"zaaab", False)]),
        ("za{2,}b", [(b"zab", False), (b"zaab", True), (b"zaaaab", True)]),
        ("za{1,3}b", [(b"zb", False), (b"zab", True), (b"zaab", True),
                       (b"zaaab", True), (b"zaaaab", False)]),
        ("za{0,3}b", [(b"zb", True), (b"zab", True), (b"zaaab", True),
                       (b"zaaaab", False)]),
        ("za{2,2}b", [(b"zab", False), (b"zaab", True), (b"zaaab", False)]),
        ("za{0}b", [(b"zb", True), (b"zab", False)]),
        ("za{0,0}b", [(b"zb", True), (b"zab", False)]),
        ("z(ab){2,3}c", [(b"zabc", False), (b"zababc", True),
                          (b"zabababc", True), (b"zababababc", False),
                          (b"zabbc", False)]),
        ("zab+c", [(b"zabc", True), (b"zabbbc", True), (b"zababc", False)]),
    ]
    cases = []
    for pattern, rows in scenarios:
        actions, expected = [], []
        for data, accepted in rows:
            actions.extend([operation("find_all", data), operation("is_full_match", data)])
            expected.extend([[[0, len(data)]] if accepted else [], accepted])
        cases.append((pattern_request(pattern, actions), expected))
    assert_success_cases(matching, cases)


def test_leftmost_longest_nonoverlapping_selection(matching):
    # F01.T03: earliest start wins over a longer later occurrence; longest wins
    # at the same start regardless of branch order. Overlaps are not emitted.
    cases = []
    for pattern in ["a|ab|bcdef", "bcdef|ab|a"]:
        rows = [(b"ab", [[0, 2]]), (b"abcdef", [[0, 2]]),
                (b"xxab--a--bcdef", [[2, 4], [6, 7], [9, 14]]), (b"xyz", [])]
        actions, expected = [], []
        for data, spans in rows:
            actions.extend([operation("is_match", data), operation("find_all", data)])
            expected.extend([bool(spans), spans])
        cases.append((pattern_request(pattern, actions), expected))
    cases.append((pattern_request("aba", [operation("is_match", b"ababa aba"),
                                          operation("find_all", b"ababa aba")]),
                  [True, [[0, 3], [6, 9]]]))
    assert_success_cases(matching, cases)


def test_empty_matches_progress_by_byte(matching):
    # F01.T04: a two-byte scalar exposes bytewise rather than character progress.
    # "aab" places the end of a nonempty match before the input end, where the
    # adjacent empty match must still be retained; existence on input without
    # any consuming occurrence must still report the empty occurrences.
    inputs = [b"", b"aa", b"ba", b"\xc3\xa9", b"aab", b"bbb"]
    rows = [
        ("", [[[0, 0]], [[0, 0], [1, 1], [2, 2]],
              [[0, 0], [1, 1], [2, 2]], [[0, 0], [1, 1], [2, 2]],
              [[0, 0], [1, 1], [2, 2], [3, 3]], [[0, 0], [1, 1], [2, 2], [3, 3]]]),
        ("a*", [[[0, 0]], [[0, 2], [2, 2]],
                [[0, 0], [1, 2], [2, 2]], [[0, 0], [1, 1], [2, 2]],
                [[0, 2], [2, 2], [3, 3]], [[0, 0], [1, 1], [2, 2], [3, 3]]]),
        ("a+", [[], [[0, 2]], [[1, 2]], [], [[0, 2]], []]),
        ("a?", [[[0, 0]], [[0, 1], [1, 2], [2, 2]],
                [[0, 0], [1, 2], [2, 2]], [[0, 0], [1, 1], [2, 2]],
                [[0, 1], [1, 2], [2, 2], [3, 3]], [[0, 0], [1, 1], [2, 2], [3, 3]]]),
    ]
    cases = []
    for pattern, spans in rows:
        actions, expected = [], []
        for data, found in zip(inputs, spans):
            actions.extend([operation("find_all", data), operation("is_match", data)])
            expected.extend([found, bool(found)])
        cases.append((pattern_request(pattern, actions), expected))
    assert_success_cases(matching, cases)


def test_prefix_and_full_input_queries(matching):
    # F01.T05: all patterns stay within the explicitly supported assertion scope.
    rows = [
        ("a|ab+", [(b"abbb", [0, 4], True), (b"abbbx", [0, 4], False),
                    (b"xabbb", None, False), (b"xyz", None, False),
                    (b"", None, False)]),
        ("a*", [(b"", [0, 0], True), (b"bbb", [0, 0], False),
                 (b"aaa", [0, 3], True), (b"aaab", [0, 3], False)]),
    ]
    cases = []
    for pattern, inputs in rows:
        actions, expected = [], []
        for data, prefix, full in inputs:
            actions.extend([operation("find_anchored", data), operation("is_full_match", data)])
            expected.extend([prefix, full])
        cases.append((pattern_request(pattern, actions), expected))
    assert_success_cases(matching, cases)


def test_original_byte_input_and_offsets(matching):
    # F01.T06: bytes before/after NUL, malformed UTF-8, and multibyte literals.
    inputs = [b"\xff\x00A\xc3\xa9A\xfeA\x00A", b"e\xcc\x81A", b"\xff\x00\xfe"]
    rows = [
        ("A", [[[2, 3], [5, 6], [7, 8], [9, 10]], [[3, 4]], []]),
        (r"\x00", [[[1, 2], [8, 9]], [], [[1, 2]]]),
        ("é", [[[3, 5]], [], []]),
        ("éA", [[[3, 6]], [], []]),
    ]
    cases = []
    for pattern, matches in rows:
        actions, expected = [], []
        for data, spans in zip(inputs, matches):
            actions.extend([operation("is_match", data), operation("find_all", data)])
            expected.extend([bool(spans), spans])
        cases.append((pattern_request(pattern, actions), expected))
    assert_success_cases(matching, cases)


def test_invalid_syntax_has_invalid_pattern_carrier(matching):
    # F01.T07: enumerate every invalid-syntax family named by FP-01.06.
    assert_success_cases(matching, [
        (pattern_request("(ab|cd)e", [operation("find_all", b"abe cde")]),
         [[[0, 3], [4, 7]]]),
    ])
    assert_rejections(matching, [
        "(ab", "[ab", "[z-a]", "*ab", "a{3,2}", "a{2", "a{-1}",
        "\\", r"\xGG", r"\p{NoSuchProperty}", "(?q)a",
    ], "invalid_pattern")


def test_unsupported_syntax_has_unsupported_carrier(matching):
    # F01.T08: supported controls exercise the operands used by rejected forms.
    # Global and scoped greediness reversal must each be refused independently
    # of lazy quantifiers, which have their own unsupported syntax check.
    assert_success_cases(matching, [
        (pattern_request("a+", [operation("find_all", b"baaa")]), [[[1, 4]]]),
        (pattern_request("(a)a", [operation("find_all", b"baa")]), [[[1, 3]]]),
        (pattern_request("a{2,3}", [operation("find_all", b"baaa")]), [[[1, 4]]]),
    ])
    assert_rejections(matching, [
        "a*?", "a+?", "a??", "a{2,3}?", r"(a)\1", "(?U)a+", "(?U:a+)",
    ], "unsupported")


def test_invalid_utf8_pattern_text_is_refused(byte_compilation):
    # F01.T09: observe refusal through a null handle and diagnostic bytes.
    # The byte interface does not require a distinct UTF-8 error category.
    live = byte_compilation.json([
        {"pattern_bytes": list("é".encode("utf-8")), "input": list(b"x\xc3\xa9")},
    ]).value
    assert live == [{"ok": True, "count": 1, "storage": [1, 3]}], live
    patterns = [b"\xff", b"\xc3", b"a\x80b", b"\xed\xa0\x80", b"(ab", b"a*?"]
    observations = byte_compilation.json([
        {"pattern_bytes": list(pattern), "input": []} for pattern in patterns
    ]).value
    assert len(observations) == len(patterns), observations
    for pattern, observation in zip(patterns, observations):
        assert observation["ok"] is False, (pattern, observation)
        assert observation["diagnostic"], (pattern, observation)


def test_explicit_repetition_limits_and_override(matching):
    # F01.T10: check acceptance at the limit, rejection above it, and actual
    # execution under the override for exact, lower-bounded, and bounded forms.
    inputs = [b"a" * n for n in [499, 500, 501, 502]]
    rows = [
        ("a{500}", [[], [[0, 500]], [[0, 500]], [[0, 500]]]),
        ("a{500,}", [[], [[0, 500]], [[0, 501]], [[0, 502]]]),
        ("a{499,500}", [[[0, 499]], [[0, 500]], [[0, 500]], [[0, 500]]]),
    ]
    assert_success_cases(matching, [
        (pattern_request(pattern, [operation("find_all", data) for data in inputs],
                         unbounded=False), expected)
        for pattern, expected in rows
    ])
    # The bound is checked for every operand kind, not only single literals.
    assert_success_cases(matching, [
        (pattern_request("(ab){500}", [operation("find_all", b"ab" * 501)],
                         unbounded=False), [[[0, 1000]]]),
        (pattern_request("[ab]{500}", [operation("find_all", b"ab" * 250 + b"!")],
                         unbounded=False), [[[0, 500]]]),
    ])
    excessive = ["a{501}", "a{501,}", "a{500,501}", "(ab){501}", "[ab]{501}",
                 "[ab]{2,501}", "(?:ab){501,}"]
    assert_rejections(matching, excessive, "unsupported", unbounded=False)
    # The same limit applies when no options are supplied at all.
    assert_rejections(matching, excessive, "unsupported")
    rows = [
        ("a{501}", [[], [[0, 501]], [[0, 501]]]),
        ("a{501,}", [[], [[0, 501]], [[0, 502]]]),
        ("a{500,501}", [[[0, 500]], [[0, 501]], [[0, 501]]]),
    ]
    assert_success_cases(matching, [
        (pattern_request(pattern, [operation("find_all", data) for data in inputs[1:]],
                         unbounded=True), expected)
        for pattern, expected in rows
    ])


def test_group_nesting_limit_and_override(matching):
    # F01.T11: simultaneous nesting differs from the total number of groups.
    at_limit = "(" * 1000 + "a" + ")" * 1000
    above_limit = "(" * 1001 + "a" + ")" * 1001
    assert_success_cases(matching, [
        (pattern_request(at_limit, [operation("find_all", b"baac")]),
         [[[1, 2], [2, 3]]]),
        (pattern_request("(a)" * 1001,
                         [operation("find_all", b"a" * 1000),
                          operation("find_all", b"a" * 1001)]),
         [[], [[0, 1001]]]),
    ])
    assert_rejections(matching, [above_limit], "unsupported")
    # Every group kind contributes a nesting level, alone or mixed.
    plain_at_limit = "(?:" * 1000 + "a" + ")" * 1000
    plain_above = "(?:" * 1001 + "a" + ")" * 1001
    mixed_above = "(?:" * 500 + "(" * 501 + "a" + ")" * 501 + ")" * 500
    assert_success_cases(matching, [
        (pattern_request(plain_at_limit, [operation("find_all", b"baac")]),
         [[[1, 2], [2, 3]]]),
    ])
    assert_rejections(matching, [plain_above, mixed_above], "unsupported")
    assert_success_cases(matching, [
        (pattern_request(pattern, [operation("find_all", b"baac")], unbounded=True),
         [[[1, 2], [2, 3]]]) for pattern in (above_limit, plain_above, mixed_above)
    ])


def test_bounded_output_delivers_complete_prefix_and_total(bounded_matching):
    # F01.T12: storage lengths are in usize slots, with two slots per result.
    # All caller memory is valid; the odd slot must remain unchanged.
    initial = 987654321
    capacities = [0, 1, 3, 4, 6, 8]
    scenarios = [
        ("a|ab|bcdef", b"xxab--a--bcdef", [[2, 4], [6, 7], [9, 14]]),
        ("a*", b"aa", [[0, 2], [2, 2]]),
        ("a+", b"xyz", []),
        # The explicit byte length governs; zero bytes do not end the input.
        ("A", b"\x00A\x00\xffA", [[1, 2], [4, 5]]),
    ]
    observations = bounded_matching.json([
        {"pattern": pattern, "input": list(data), "capacities": capacities,
         "initial": initial} for pattern, data, spans in scenarios
    ]).value
    assert len(observations) == len(scenarios), observations
    for (pattern, data, spans), observation in zip(scenarios, observations):
        assert observation["ok"] is True, observation
        assert len(observation["results"]) == len(capacities), observation
        for capacity, result in zip(capacities, observation["results"]):
            assert result["count"] == len(spans), (pattern, data, capacity, result)
            prefix = spans[:capacity // 2]
            written = [offset for pair in prefix for offset in pair]
            assert result["storage"][:len(written)] == written, (pattern, data, capacity, result)
            if capacity % 2 and len(spans) > capacity // 2:
                # The remaining slot cannot carry a complete next result.
                assert result["storage"][capacity - 1] == initial, (pattern, data, capacity, result)


def test_reused_pattern_searches_are_independent(matching):
    # F01.T13: one compiled instance per row, including repeated earlier inputs.
    assert_success_cases(matching, [
        (pattern_request("a|ab|bcdef", [
            operation("is_match", b"abcdef"),
            operation("find_all", b"xxab--a--bcdef"),
            operation("is_match", b"xyz"),
            operation("find_all", b""),
            operation("is_match", b""),
            operation("find_all", b"abcdef"),
            operation("is_match", b"xxab--a--bcdef"),
            operation("find_all", b"xyz"),
            operation("is_match", b"abcdef"),
            operation("find_all", b"xxab--a--bcdef"),
        ]), [True, [[2, 4], [6, 7], [9, 14]], False, [], False, [[0, 2]],
             True, [], True, [[2, 4], [6, 7], [9, 14]]]),
        (pattern_request("a*", [
            operation("find_all", b"aa"), operation("is_match", b""),
            operation("find_all", b"ba"), operation("is_match", b"aa"),
            operation("find_all", b""), operation("find_all", b"aa"),
        ]), [[[0, 2], [2, 2]], True, [[0, 0], [1, 2], [2, 2]], True,
             [[0, 0]], [[0, 2], [2, 2]]]),
    ])
