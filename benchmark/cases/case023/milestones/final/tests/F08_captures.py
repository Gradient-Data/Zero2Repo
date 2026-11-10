# feature: F08
"""Acceptance tests for captured submatches through public Rust and C entries."""

from F01_helpers import assert_success_cases, operation, pattern_request
from F08_helpers import (
    assert_capture_refusals, bounded_captures, capture_api, capture_case,
)


def test_capture_extents_and_occurrences(capture_api):
    """F08.T01: unique decompositions retain whole, nested and unnamed byte spans."""
    assert_success_cases(capture_api, [
        capture_case(r"(?P<record>(??[A-Z]+)-(?P<number>[0-9]+))", [
            ("é:AB-7 猫:Q-42!".encode(), [
                [[3, 7], [3, 7], [3, 5], [6, 7]],
                [[12, 16], [12, 16], [12, 13], [14, 16]],
            ]),
            (b"no record", []),
        ]),
        capture_case(r"(?P<word>é|猫):(??[0-9]+)", [
            ("!é:12/猫:3".encode(), [
                [[1, 6], [1, 3], [4, 6]], [[7, 12], [7, 10], [11, 12]],
            ]),
        ]),
    ])


def test_capture_declarations_and_lookup(capture_api):
    """F08.T02: declaration order and lookup follow the selected capture mode."""
    cases = []
    for implicit in (None, False, True):
        names = [None, "z", None, "a"]
        spans = [[0, 5], [2, 4], [3, 4], [4, 5]]
        absent = [[0, 4], [2, 4], [3, 4], None]
        indices = [1, 3, None, None]
        if implicit:
            names.insert(1, None)
            spans.insert(1, [0, 1])
            absent.insert(1, [0, 1])
            indices = [2, 4, None, None]
        query_names = ["z", "a", "missing", ""]
        actions = [{"op": "metadata", "names": query_names}]
        expected = [{"names": names, "indices": indices}]
        for data, row in ((b"abcde", spans), (b"abcd", absent)):
            actions.append(operation("captures_all", data))
            expected.append([row])
            lookup = operation("lookup", data)
            lookup.update(indices=list(range(len(names) + 1)) + [999], names=query_names)
            actions.append(lookup)
            expected.append([{"by_index": row + [None, None],
                              "by_name": [[2, 4], [4, 5] if data == b"abcde" else None,
                                          None, None]}])
        request = pattern_request(r"(a)(?:b)(?P<z>c(??d))(?P<a>e)?", actions)
        if implicit is not None:
            request["implicit"] = implicit
        cases.append((request, expected))
    assert_success_cases(capture_api, cases)


def test_optional_absence_and_empty_participation(capture_api):
    """F08.T03: skipped, empty and nonempty captures are distinct, without stale spans."""
    assert_success_cases(capture_api, [
        capture_case(r"L(?P<part>[ab]+)?R", [
            (b"LaR LR LbbR", [[[0, 3], [1, 2]], [[4, 6], None], [[7, 11], [8, 10]]]),
            (b"LR", [[[0, 2], None]]),
            (b"LaaR", [[[0, 4], [1, 3]]]),
            (b"LR", [[[0, 2], None]]),
        ]),
        capture_case(r"L(?P<part>a*)R", [
            (b"LR LaaR", [[[0, 2], [1, 1]], [[3, 7], [4, 6]]]),
        ]),
        capture_case(r"(?P<part>a*)", [(b"", [[[0, 0], [0, 0]]])]),
    ])


def test_adjacent_mandatory_capture_allocation(capture_api):
    """F08.T04: earlier repeated classes take the longest feasible extent."""
    assert_success_cases(capture_api, [
        capture_case(r"(?P<first>[ab]+)(??[ab]+)", [
            (b"ababba", [[[0, 6], [0, 5], [5, 6]]]),
            (b"ab", [[[0, 2], [0, 1], [1, 2]]]),
        ]),
        capture_case(r"(?P<first>[ab]+)(?P<middle>[ab]{2,3})(?P<last>[ab]+)", [
            (b"abbaabab", [[[0, 8], [0, 5], [5, 7], [7, 8]]]),
            (b"abba", [[[0, 4], [0, 1], [1, 3], [3, 4]]]),
        ]),
    ])


def test_equal_span_alternation_retains_capture(capture_api):
    """F08.T05: a capture-free tied alternative cannot suppress participation."""
    rows = [(b"!ab:12 ab:7?", [
        [[1, 6], [4, 6]], [[7, 11], [10, 11]],
    ])]
    plain = r"ab:[0-9]+"
    captured = r"ab:(?P<number>[0-9]+)"
    assert_success_cases(capture_api, [
        capture_case(f"(?:{plain}|{captured})", rows),
        capture_case(f"(?:{captured}|{plain})", rows),
    ])


def test_finite_repetition_reports_final_capture(capture_api):
    """F08.T06: fixed-width captures retain only the last finite repetition."""
    assert_success_cases(capture_api, [
        capture_case(r"(?P<pair>[ab][0-9]){1,3}!", [
            (b"a1! b2a3! a4b5a6!", [
                [[0, 3], [0, 2]], [[4, 9], [6, 8]], [[10, 17], [14, 16]],
            ]),
        ]),
        capture_case(r"(??[ab][0-9]){2}!", [
            (b"a1b2!", [[[0, 5], [2, 4]]]),
        ]),
        capture_case(r"(?P<pair>[ab][0-9]){0,2}!", [
            (b"! a1! a2b3!", [[[0, 1], None], [[2, 5], [2, 4]], [[6, 11], [8, 10]]]),
        ]),
    ])


def test_unsupported_capture_placement_and_repetition(capture_api):
    """F08.T07: forbidden capture compositions return a public unsupported error."""
    assert_success_cases(capture_api, [
        capture_case(r"(?P<part>a+)", [(b"!aaa", [[[1, 4], [1, 4]]])]),
        capture_case(r"(?P<part>a){1,2}", [(b"aa", [[[0, 2], [1, 2]]])]),
    ])
    assert_capture_refusals(capture_api, [
        r"(?P<part>a)*", r"(??a)+", r"(?P<part>a){2,}",
        r"(?:(?P<part>a)b)*", r"(?:(??a)b)+",
        r"~((?P<part>a))",
        r"(?=(?P<part>a))a", r"(?!(?P<part>b))a",
        r"(?<=(?P<part>a))b", r"(?<!(?P<part>a))b",
    ], "unsupported")


def test_capture_declaration_capacity(capture_api):
    """F08.T08: the whole-match slot is outside the joint named/unnamed limit."""
    cases, rejected = [], []
    for count in (62, 63, 64):
        pattern = "".join(f"(?P<g{i}>a)" if i % 2 == 0 else "(??b)" for i in range(count))
        if count > 63:
            rejected.append(pattern)
            continue
        data = bytes(ord("a") if i % 2 == 0 else ord("b") for i in range(count))
        names = [None] + [f"g{i}" if i % 2 == 0 else None for i in range(count)]
        request = pattern_request(pattern, [
            {"op": "metadata", "names": []}, operation("captures_all", data),
        ])
        cases.append((request, [{"names": names, "indices": []},
                               [[[0, count]] + [[i, i + 1] for i in range(count)]]]))
    assert_success_cases(capture_api, cases)
    assert_capture_refusals(capture_api, rejected, "unsupported")


def test_bounded_capture_storage(bounded_captures):
    """F08.T09: the C interface delivers complete rows and reports the total."""
    # Distinct row shapes prevent a constant result or duplicated row passing.
    rows = [[[0, 3], [1, 2], [2, 2]], [[4, 6], None, [5, 5]],
            [[7, 12], [8, 10], [10, 11]]]
    initial = 123456789
    # Include a mandatory empty-capable group as well as an absent optional one.
    # Whole, optional letters, optional-width digits: three slots per row.
    slots = 3
    stride = slots * 2
    capacities = [0, stride - 1, stride, 2 * stride + 1, 3 * stride, 3 * stride + 2]
    request = {"pattern": r"L(?P<letters>[ab]+)?(?P<digits>[0-9]*)R",
               "input": list(b"LaR LR Lbb7R"), "capacities": capacities, "initial": initial}
    results = bounded_captures.json([request]).value
    assert len(results) == 1, results
    observation = results[0]
    assert observation["ok"] is True, observation
    assert observation["slots"] == slots, observation
    absent = observation["absent"]  # C SIZE_MAX, measured from the host ABI, not the product.
    flat_rows = [[v for span in row for v in ([absent, absent] if span is None else span)]
                 for row in rows]
    assert len(observation["results"]) == len(capacities), observation
    for capacity, result in zip(capacities, observation["results"]):
        complete = min(capacity // stride, len(rows))
        expected = sum(flat_rows[:complete], [])
        assert result["count"] == len(rows), (capacity, result)
        assert result["storage"][:len(expected)] == expected, (capacity, result, expected)
        if complete < len(rows):
            # Pending results must not be partially written into the remainder.
            # Space left after every result was delivered is not constrained.
            assert result["storage"][len(expected):] == [initial] * (capacity - len(expected)), (
                capacity, result)


def test_invalid_capture_names(capture_api):
    """F08.T10: empty and duplicate names are invalid, not silently renamed."""
    request = pattern_request(r"(?P<z>a)(?P<a>b)", [
        {"op": "metadata", "names": ["a", "z"]}, operation("captures_all", b"!ab"),
    ])
    assert_success_cases(capture_api, [(request, [
        {"names": [None, "z", "a"], "indices": [2, 1]},
        [[[1, 3], [1, 2], [2, 3]]],
    ])])
    assert_capture_refusals(capture_api, [
        r"(?P<>a)", r"(?P<same>a)(?P<same>b)",
        r"(?P<same>a)|(?P<same>b)", r"(?P<same>a(?P<same>b))",
    ], "invalid_pattern")
