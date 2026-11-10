# feature: F10
"""Acceptance tests for saving and restoring reusable patterns."""

from F01_helpers import operation, pattern_request, successful_values
from F03_helpers import (
    MODES, CHARACTERS, option_request, scalar_spans, shorthand_predicate,
    unicode16, unicode_ranges, in_ranges,
)
from F09_helpers import collection_request
from F10_helpers import persistence_api, restore_observed, save_observed, saved_bytes


def test_restore_matching_on_new_inputs(persistence_api, unicode16):
    """F10.T01: restored supported families retain selection, emptiness and options."""
    # Each row specifies an independent answer; no restored expectation comes
    # from a previous search. Baseline observations are recorded in the evidence.
    cases = [
        ("amber", {}, (b"amber", [[0, 5]]), [
            (b"xamber amberX", [[1, 6], [7, 12]]), (b"AMBER", []), (b"", []),
        ]),
        ("ab|abcd|xy", {}, (b"ab", [[0, 2]]), [
            (b"!abcd:xyab?", [[1, 5], [6, 8], [8, 10]]), (b"ax", []),
        ]),
        ("[ab]+", {}, (b"abb", [[0, 3]]), [
            (b"ba!abb?c", [[0, 2], [3, 6]]), (b"xyz", []), (b"", []),
        ]),
        ("[ab]*", {}, (b"a", [[0, 1], [1, 1]]), [
            (b"!ab?", [[0, 0], [1, 3], [3, 3], [4, 4]]), (b"", [[0, 0]]),
        ]),
        ("ID[0-9]{2}-[A-Z]{3}", {}, (b"ID12-ABC", [[0, 8]]), [
            (b"ID07-ZYX!ID99-ABC", [[0, 8], [9, 17]]),
            (b"ID8-QQQ ID01-abC", []),
        ]),
    ]
    for insensitive in (False, True):
        cases.append(("aBc", {"case_insensitive": insensitive}, (b"aBc", [[0, 3]]), [
            (b"ABC:aBc:abc", [[0, 3], [4, 7], [8, 11]] if insensitive else [[4, 7]]),
            (b"abx", []),
        ]))
    # Unicode expectations come from F03's isolated Unicode 16 provider.
    word, folded = unicode_ranges(unicode16, [r"\w", "(?i:[é])"])
    # Separate members so these rows measure mode membership independently of
    # run length. Fixed-count sequences and repeated runs are covered above.
    for mode in MODES:
        # New inputs exercise the same versioned memberships after restoration.
        text = "é 猫 Z _ 9 " + " ".join(CHARACTERS)
        expected = scalar_spans(text, shorthand_predicate("w", mode, word))
        cases.append((r"\w+", {"mode": mode}, (b"Q", [[0, 1]]), [
            (text.encode(), expected), (b"!", []),
        ]))
    text = "É é E e 猫"
    cases.append(("[é]+", {"mode": "Full", "case_insensitive": True},
                  ("é".encode(), [[0, 2]]), [
                      (text.encode(), scalar_spans(text, lambda c: in_ranges(c, folded))),
                  ]))
    for pattern, options, warm, rows in cases:
        print("Persistence case:", pattern, options, flush=True)
        request = option_request(pattern, [operation("find_all", warm[0])], **options)
        data = saved_bytes(save_observed(persistence_api, request, [warm[1]]))
        restore_observed(persistence_api, data,
                         [operation("find_all", text) for text, _ in rows],
                         [spans for _, spans in rows])


def test_restore_fixed_capture_names_and_spans(persistence_api):
    """F10.T02: independent loaded inputs retain nested, unnamed and named captures."""
    cases = [
        (r"L(?P<outer>(?P<z>[A-Z]{2})-(??[0-9]{2}))R",
         [None, "outer", "z", None], ["z", "outer"],
         b"LAB-12R", [[[0, 7], [1, 6], [1, 3], [4, 6]]],
         [(b"!LCD-90R LXY-07R", [
             [[1, 8], [2, 7], [2, 4], [5, 7]],
             [[9, 16], [10, 15], [10, 12], [13, 15]],
         ]), (b"no record", [])], [2, 1]),
        (r"(?P<letter>é)(??[0-9]{2})-(?P<tail>[A-Z])",
         [None, "letter", None, "tail"], ["tail", "letter"],
         "é12-A".encode(), [[[0, 6], [0, 2], [2, 4], [5, 6]]],
         [("猫é90-Z/é07-Q".encode(), [
             [[3, 9], [3, 5], [5, 7], [8, 9]],
             [[10, 16], [10, 12], [12, 14], [15, 16]],
         ]), (b"", [])], [3, 1]),
    ]
    for pattern, names, queries, warm, warm_spans, rows, indices in cases:
        actions = [{"op": "metadata"}, dict(operation("captures_all", warm), names=queries)]
        expected = [names, [{"spans": spans, "by_name": [spans[i] for i in indices]}
                            for spans in warm_spans]]
        data = saved_bytes(save_observed(persistence_api, pattern_request(pattern, actions), expected))
        actions, expected = [{"op": "metadata"}], [names]
        for text, spans in rows:
            actions.extend([operation("find_all", text),
                            dict(operation("captures_all", text), names=queries)])
            expected.extend([[row[0] for row in spans],
                             [{"spans": row, "by_name": [row[i] for i in indices]} for row in spans]])
        restore_observed(persistence_api, data, actions, expected)


def test_saving_refuses_variable_captures_and_combined_set(persistence_api):
    """F10.T03: unsupported saving fails at dump after real successful matching."""
    control = pattern_request(r"(?P<a>[0-9]{2})\.(?P<b>[0-9]{2})",
                              [operation("find_all", b"12.34")])
    data = saved_bytes(save_observed(persistence_api, control, [[[0, 5]]]))
    restore_observed(persistence_api, data, [operation("find_all", b"!98.76")], [[[1, 6]]])
    for pattern in (r"(?P<a>[0-9]{1,3})\.(?P<b>[0-9]{1,3})",
                    r"(?P<a>[0-9]+)\.(?P<b>[0-9]+)"):
        action = dict(operation("captures_all", b"1.23 456.7"), names=["a", "b"])
        expected = [[
            {"spans": [[0, 4], [0, 1], [2, 4]], "by_name": [[0, 1], [2, 4]]},
            {"spans": [[5, 10], [5, 8], [9, 10]], "by_name": [[5, 8], [9, 10]]},
        ]]
        saved = save_observed(persistence_api, pattern_request(pattern, [action]), expected)
        assert saved["ok"] is False, saved
        assert saved["error"]["category"] == "serialize", saved
    request = collection_request(["ab", "xyz"], [operation("find_all", b"!xyzab")])
    observation = persistence_api.json([dict(request, op="save_set")]).value
    assert len(observation) == 1, observation
    assert successful_values(observation[0]) == [[[1, 4], [4, 6]]], observation
    saved = observation[0]["saved"]
    assert saved["ok"] is False, saved
    assert saved["error"]["category"] == "serialize", saved


def test_loading_incomplete_saved_data_is_refused(persistence_api):
    """F10.T04: required data cannot be silently replaced with a default pattern."""
    # Empty data must be refused. For nonempty prefixes, optional suffix data
    # may be absent, but loading must never silently change the saved pattern.
    # Cut positions follow the actual representation, without assuming a header
    # layout, mandatory tail bytes, or a minimum encoding size.
    for pattern, warm, new, spans in [
        ("violet", b"violet", b"!violet?", [[1, 7]]),
        ("[0-9]+", b"37", b"x123y8", [[1, 4], [5, 6]]),
    ]:
        request = pattern_request(pattern, [operation("find_all", warm)])
        data = saved_bytes(save_observed(persistence_api, request, [[[0, len(warm)]]]))
        restore_observed(persistence_api, data, [operation("find_all", new)], [spans])
        observation = persistence_api.json([
            {"op": "load", "saved": data[:0], "actions": []}
        ]).value
        assert len(observation) == 1, observation
        item = observation[0]
        assert item["ok"] is False, item
        assert item["error"]["category"] == "serialize", item
        cuts = sorted({cut for cut in (1, len(data) // 2, len(data) - 1)
                       if 0 < cut < len(data)})
        actions = [operation("find_all", new), operation("find_all", b"")]
        expected = [spans, []]
        observations = persistence_api.json([
            {"op": "load", "saved": data[:cut], "actions": actions}
            for cut in cuts
        ]).value
        assert len(observations) == len(cuts), observations
        for cut, item in zip(cuts, observations):
            print("Saved prefix:", pattern, cut, len(data), item, flush=True)
            if item["ok"] is False:
                assert item["error"]["category"] == "serialize", (cut, item)
            else:
                assert successful_values(item) == expected, (cut, item, expected)
