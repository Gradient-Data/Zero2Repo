# feature: F09
"""Acceptance tests for independent collection membership and classification."""

from F01_helpers import assert_success_cases, operation
from F03_helpers import CHARACTERS, shorthand_predicate, unicode16, unicode_ranges
from F09_helpers import collection_api, collection_case, collection_request


def test_independent_membership(collection_api):
    """F09.T01: every matching declaration counts, even behind a union winner."""
    scenarios = [
        (["qr"], [(b"qr qr", [0]), (b"qq", [])]),
        (["qr", "r", "rst", "qrst", "qr", "absent"],
         [(b"qrst qr qrst", [0, 1, 2, 3, 4]), (b"rst", [1, 2]),
          (b"!", []), (b"qr", [0, 1, 4])]),
        # More than one machine word of declarations; order is declaration
        # order, not occurrence order, and repeated occurrences are deduplicated.
        ([f"v{i};" for i in range(80)],
         [(b"v71;v2;v79;v2;", [2, 71, 79]), (b"v0;", [0])]),
    ]
    cases = []
    for patterns, rows in scenarios:
        actions, expected = [], []
        for data, members in rows:
            actions.extend([operation("is_match", data), operation("matched", data)])
            expected.extend([bool(members), members])
        cases.append((collection_request(patterns, actions), expected))
    assert_success_cases(collection_api, cases)


def test_shared_options_and_defaults(collection_api, unicode16):
    """F09.T02: each member receives the same requested matching options."""
    cases = []
    word_table, = unicode_ranges(unicode16, [r"\w"])
    # Shared options include the specified Unicode version, on every member.
    text = "é!猫!" + "!".join(CHARACTERS)
    for mode in (None, "Ascii", "Default", "Full", "Javascript"):
        accepts = shorthand_predicate("w", mode or "Default", word_table)
        spans = []
        offset = 0
        for char in text:
            end = offset + len(char.encode())
            accepted = accepts(char)
            if accepted:
                spans.append([offset, end])
            offset = end
        options = {} if mode is None else {"mode": mode}
        cases.append(collection_case([r"\w", r"\w{1}"],
                     [(text.encode(), [0, 1] if spans else [], spans)], options=options))
        if mode is None:
            cases.append(collection_case([r"\w", r"\w{1}"],
                         [(text.encode(), [0, 1], spans)]))
        widths = ([[0, 3], [4, 8]] if mode in ("Full", "Javascript")
                  else [[0, 2], [6, 8]])
        cases.append(collection_case(["L.", ".R"],
                     [("Lé!猫R".encode(), [0, 1], widths)], options=options))

    settings = [
        ("case_insensitive", False, ["owl", "fox"], b"OWL FOX owl fox",
         ([0, 1], [[8, 11], [12, 15]]),
         ([0, 1], [[0, 3], [4, 7], [8, 11], [12, 15]])),
        ("dot_matches_new_line", False, ["a.b", "c.d"], b"a\nb c\nd",
         ([], []), ([0, 1], [[0, 3], [4, 7]])),
        ("multiline", True, ["q$", "r$"], b"q\nr\nq!r",
         ([1], [[6, 7]]), ([0, 1], [[0, 1], [2, 3], [6, 7]])),
        ("ignore_whitespace", False, ["a b", "c d"], b"ab cd a b c d",
         ([0, 1], [[6, 9], [10, 13]]), ([0, 1], [[0, 2], [3, 5]])),
    ]
    for name, default, patterns, data, disabled, enabled in settings:
        for options, (members, spans) in (
            (None, enabled if default else disabled),
            ({}, enabled if default else disabled),
            ({name: False}, disabled), ({name: True}, enabled),
        ):
            cases.append(collection_case(patterns, [(data, members, spans)], options=options))
    assert_success_cases(collection_api, cases)


def test_union_selection_and_contextual_attribution(collection_api):
    """F09.T03: select the union span first, then its earliest eligible member."""
    cases = [
        collection_case(["qr", "qrst", "rst", "stuv", "[0-9]+", "[0-9]{2}"],
                        [(b"!qrstuv 42 567", [0, 1, 2, 3, 4, 5],
                          [[1, 5, 1], [8, 10, 4], [11, 14, 4]])], classify=True),
        collection_case(["absent", "qr", "[a-z]+", "qr"],
                        [(b"qr qrs", [1, 2, 3], [[0, 2, 1], [3, 6, 2]])], classify=True),
        collection_case(["absent", "[a-z]+", "qr", "qr"],
                        [(b"qr qrs", [1, 2, 3], [[0, 2, 1], [3, 6, 1]])], classify=True),
        collection_case([r"\Aq", "q$", "q"],
                        [(b"q q\nq", [0, 1, 2], [[0, 1, 0], [2, 3, 1], [4, 5, 1]]),
                         (b"xq q!", [2], [[1, 2, 2], [3, 4, 2]]),
                         (b"q", [0, 1, 2], [[0, 1, 0]])], classify=True),
        collection_case([r"q\b", "q"],
                        [(b"qq q1 q!", [0, 1],
                          [[0, 1, 1], [1, 2, 0], [3, 4, 1], [6, 7, 0]])], classify=True),
        collection_case(["q(?=rs)", "q(?=r)", "q(?!r)", "q"],
                        [(b"qrs qr qx q", [0, 1, 2, 3],
                          [[0, 1, 0], [4, 5, 1], [7, 8, 2], [10, 11, 2]])], classify=True),
        # Context controls union acceptance as well as which tag wins.
        collection_case([r"\Aq", "r$", r"s\b", "t(?=u)"],
                        [(b"q r! s1 tx r\ns! tu", [0, 1, 2, 3],
                          [[0, 1, 0], [11, 12, 1], [13, 14, 2], [16, 17, 3]]),
                         (b"xq r! s1 tx", [], [])], classify=True),
    ]
    assert_success_cases(collection_api, cases)


def test_empty_collections_and_nullable_members(collection_api):
    """F09.T04: empty collections succeed, while nullable members stay eligible."""
    cases = [
        collection_case([], [(b"", [], []), (b"qr\n", [], [])], classify=True),
        collection_case(["q"], [(b"", [], []), (b"!q!", [0], [[1, 2, 0]])], classify=True),
        collection_case(["q", ""], [(b"", [1], [[0, 0, 1]])], classify=True),
        collection_case(["q", "r*", ""], [(b"", [1, 2], [[0, 0, 1]])], classify=True),
        collection_case(["", "q", "r*"], [(b"", [0, 2], [[0, 0, 0]])], classify=True),
    ]
    assert_success_cases(collection_api, cases)


def test_member_rejections_identify_position(collection_api):
    """F09.T05: unusable members carry indices; malformed syntax is distinct."""
    assert_success_cases(collection_api, [collection_case(
        ["q", "(?:r)", r"\As", r"t\b", "u(?=v)", "w$"],
        [(b"q r t uv w", [0, 1, 3, 4, 5], [[0, 1], [2, 3], [4, 5], [6, 7], [9, 10]])],
    )])
    requests, expected = [], []
    violations = ["(?<item>q)", "(?<=x)q", "(?<!x)q", r"\bq", r"\Bq", "^q"]
    for i, pattern in enumerate(violations):
        position = i % 3
        patterns = ["r", "s"]
        patterns.insert(position, pattern)
        requests.append(collection_request(patterns))
        expected.append(("set_member", position))
    for pattern, position in (("[", 0), ("(", 2)):
        patterns = ["r", "s"]
        patterns.insert(position, pattern)
        requests.append(collection_request(patterns))
        expected.append(("invalid_pattern", None))
    observed = collection_api.json(requests).value
    assert len(observed) == len(requests), observed
    for request, item, (category, index) in zip(requests, observed, expected):
        assert item["ok"] is False, (request, item)
        assert item["error"]["category"] == category, (request, item)
        if index is not None:
            assert item["error"]["index"] == index, (request, item)
