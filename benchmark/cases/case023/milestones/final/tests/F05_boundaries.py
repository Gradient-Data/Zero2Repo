# feature: F05
"""Acceptance coverage for the four planned input/line/word boundary entries."""

from F01_helpers import (
    matching, operation, pattern_request, assert_success_cases, assert_rejections,
    successful_values,
)
from F03_helpers import (
    option_matching, unicode16, MODES, ASCII_SETS, CHARACTERS, unicode_ranges,
    shorthand_predicate, option_request,
)
from F05_helpers import boundary_atom_cases, boundary_compilation


def test_complete_input_anchors(matching, boundary_compilation):
    # F05.T01: later search candidates must not become new input boundaries.
    rows = [
        (r"\A", b"", [[0, 0]]),
        (r"\z", b"", [[0, 0]]),
        (r"\A\z", b"", [[0, 0]]),
        (r"\A\z", b"x", []),
        (r"\A", b"x\nx", [[0, 0]]),
        (r"\z", b"x\nx\n", [[4, 4]]),
        (r"\Ax", b"x x\nx", [[0, 1]]),
        (r"\Ax", b"!x\nx", []),
        (r"x\z", b"x x\nx", [[4, 5]]),
        (r"x\z", b"x\n", []),
        (r"\Ax\z", b"x", [[0, 1]]),
        (r"\Ax\z", b"xx", []),
        (r"x|\Ay", b"xy", [[0, 1]]),
        (r"\Ax|y", b"yxy", [[0, 1], [2, 3]]),
        (r"x\z|y", b"xyx", [[1, 2], [2, 3]]),
        (r"x?\A", b"xx", [[0, 0]]),
        (r"\Aé\z", "é".encode(), [[0, 2]]),
        (r"x\z", b"!x", [[1, 2]]),
        (r"x\z", b"x!", []),
        # A line-end assertion between consuming elements is still enforced
        # at its own position.
        (r"x$y", b"xy", []),
        (r"x$\ny", b"x\ny", [[0, 3]]),
    ]
    assert_success_cases(matching, [
        (pattern_request(p, [operation("find_all", data), operation("is_match", data)]),
         [spans, bool(spans)])
        for p, data, spans in rows
    ])
    actions = [operation("find_all", data) for data in (b"", b"x", b"xx", b"xyx\nx")]
    assert_success_cases(boundary_compilation, [
        (pattern_request(r"\Ax\z", actions), [[], [[0, 1]], [], []]),
    ])
    # Impossible expressions may be refused or compile to an empty language.
    # Neither syntax spelling nor the reference's construction choice decides
    # which of these two documented outcomes another implementation must use.
    # An input-end assertion that consuming text must follow is likewise
    # unsatisfiable wherever it occurs; it must never be silently dropped.
    actions = actions + [operation("find_all", data) for data in (b"xy", b"x\n", b"xy\n")]
    requests = [pattern_request(pattern, actions)
                for pattern in (r"x\A", r"x+\A", r"[xy]{1,2}\A", r"x\zy", r"x\z\n")]
    observations = boundary_compilation.json(requests).value
    assert len(observations) == len(requests), observations
    for request, observation in zip(requests, observations):
        if observation["ok"] is False:
            assert observation["error"]["category"] == "unsupported", (request, observation)
        else:
            assert successful_values(observation) == [[] for _ in actions], (request, observation)


def test_line_anchors_and_multiline_default(matching, option_matching):
    # F05.T02: LF is the only line separator; CR and other spacing stay content.
    text = b"x\nx\rx\tx\x0bx\x0cx\x00x\n\nx\n"
    rows = [
        ("^", [[0, 0], [2, 2], [14, 14], [15, 15], [17, 17]], [[0, 0]]),
        ("$", [[1, 1], [13, 13], [14, 14], [16, 16], [17, 17]], [[17, 17]]),
        ("^x", [[0, 1], [2, 3], [15, 16]], [[0, 1]]),
        ("x$", [[0, 1], [12, 13], [15, 16]], []),
        ("^x$", [[0, 1], [15, 16]], []),
        ("^$", [[14, 14], [17, 17]], []),
    ]
    cases, defaults = [], []
    for pattern, multiline, singleline in rows:
        actions = [operation("find_all", text)]
        defaults.append((pattern_request(pattern, actions), [multiline]))
        cases.append((option_request(pattern, actions), [multiline]))
        cases.append((option_request(pattern, actions, multiline=True), [multiline]))
        cases.append((option_request(pattern, actions, multiline=False), [singleline]))
    for pattern, data, spans in (("^$", b"", [[0, 0]]),
                                 ("^x$", b"x", [[0, 1]]),
                                 ("x$", b"!x", [[1, 2]]),
                                 ("^x$", b"!x!", [])):
        for enabled in (False, True):
            cases.append((option_request(pattern, [operation("find_all", data)],
                                         multiline=enabled), [spans]))
    # A scoped multiline change ends with its group; later anchors follow the
    # enclosing (default) setting again.
    for pattern, data, spans in (("(?-m:^x)|^y", b"x\ny", [[0, 1], [2, 3]]),
                                 ("(?-m:^x)y|^y", b"x\ny", [[2, 3]]),
                                 ("(?-m:x$)|y$", b"x\ny\n", [[2, 3]])):
        defaults.append((pattern_request(pattern, [operation("find_all", data)]), [spans]))
    assert_success_cases(matching, defaults)
    assert_success_cases(option_matching, cases)


def test_word_transitions_in_each_character_mode(option_matching, unicode16):
    # F05.T03: independent Unicode 16 membership; Unicode observations only
    # touch scalar boundaries. ASCII probes additionally observe byte adjacency.
    table, = unicode_ranges(unicode16, [r"\w"])
    cases = []
    for mode in MODES:
        is_word = shorthand_predicate("w", mode, table)
        for text in ("", "q", "!", "qq!!q_9\n!q\t"):
            members = [c in ASCII_SETS["w"] for c in text]
            transitions = [(members[i - 1] if i else False) !=
                           (members[i] if i < len(members) else False)
                           for i in range(len(members) + 1)]
            for pattern, wanted in ((r"\b", True), (r"\B", False)):
                expected = [[i, i] for i, boundary in enumerate(transitions) if boundary == wanted]
                cases.append((option_request(pattern, [operation("find_all", text.encode())], mode),
                              [expected]))
        # ASCII literal probes retain byte adjacency in ASCII mode and scalar
        # adjacency to Unicode neighbors in every other mode.
        for literal in ("q", "!"):
            cases.extend(boundary_atom_cases(literal, literal,
                                             lambda c, x=literal: c == x, mode, is_word))
        text = "q!qq!!_q9q\nq\tqéqΩq\u0300q\u07c0q\u0800q猫q\u200cq\u203fq𐐀q🦉q!éé猫猫!q"
        # Apply the same public Unicode version to adjacent word classification.
        text += "".join("q" + char for char in CHARACTERS) + "q"
        for literal in ("q", "!"):
            cases.extend(boundary_atom_cases(text, literal,
                                             lambda c, x=literal: c == x, mode, is_word))
        # Unicode literals exercise composition separately from shorthands:
        # these scalars straddle limited Unicode's word-membership range.
        if mode != "Ascii":
            for literal in ("é", "猫"):
                for literal_input in (literal, text):
                    cases.extend(boundary_atom_cases(
                        literal_input, literal, lambda c, x=literal: c == x, mode, is_word))
        # Standalone shorthands also consume Unicode scalars in these contexts.
        atom_inputs = ("q!qq!!_q9q\nq\t",) if mode == "Ascii" else (text, "é", "猫")
        for atom, accepts in ((r"\w", is_word), (r"\W", lambda c: not is_word(c))):
            for atom_input in atom_inputs:
                cases.extend(boundary_atom_cases(atom_input, atom, accepts, mode, is_word))
    # Assertions between two consuming atoms are enforced there as well.
    for pattern, data, spans in ((r"q\bq", "qq", []), (r"!\b!", "!!", []),
                                 (r"ab\bcd", "abcd", []), (r"q\B!", "q!", []),
                                 (r"q\b!", "q!", [[0, 2]]), (r"q\Bq", "qq", [[0, 2]])):
        for mode in MODES:
            cases.append((option_request(pattern, [operation("find_all", data.encode())], mode),
                          [spans]))
    assert_success_cases(option_matching, cases)
    # Bare assertions next to non-ASCII scalars classify them with the mode's
    # word set. Only scalar boundaries are judged; positions inside a scalar
    # are outside the promise and are filtered out before comparison.
    texts = ["é", "猫x", "éx!", "x\u0800", "!é猫q"]
    requests, expectations = [], []
    for mode in MODES:
        is_word = shorthand_predicate("w", mode, table)
        for text in texts:
            data = text.encode()
            if mode == "Ascii":
                units = [chr(b) for b in data]
                bounds = list(range(len(data) + 1))
            else:
                units = list(text)
                bounds = [len(text[:i].encode()) for i in range(len(text) + 1)]
            members = [is_word(u) for u in units]
            flags = [(members[i - 1] if i else False) !=
                     (members[i] if i < len(members) else False)
                     for i in range(len(members) + 1)]
            for pattern, wanted in ((r"\b", True), (r"\B", False)):
                requests.append(option_request(pattern, [operation("find_all", data)], mode))
                expectations.append((set(bounds),
                                     [[b, b] for b, f in zip(bounds, flags) if f == wanted]))
    observations = option_matching.json(requests).value
    assert len(observations) == len(requests), observations
    for request, observation, (bounds, spans) in zip(requests, observations, expectations):
        found, = successful_values(observation)
        assert all(start == end for start, end in found), (request, observation)
        assert [s for s in found if s[0] in bounds] == spans, (request, observation, spans)


def test_finite_word_assertion_repetition(matching, boundary_compilation):
    # F05.T04: zero/optional/one counts retain semantics; larger finite maxima
    # have the public unsupported carrier, for both assertion kinds.
    data = b"q!qq!!"
    positions = [[i, i] for i in range(len(data) + 1)]
    cases = []
    for assertion, required in ((r"\b", [[0, 0], [1, 1], [2, 2], [4, 4]]),
                                (r"\B", [[3, 3], [5, 5], [6, 6]])):
        for suffix, expected in (("{0}", positions), ("{0,0}", positions),
                                 ("{0,1}", positions), ("{1}", required),
                                 ("{1,1}", required)):
            cases.append((pattern_request(assertion + suffix,
                                          [operation("find_all", data)]), [expected]))
    assert_success_cases(matching, cases)
    assert_success_cases(boundary_compilation, [(pattern_request(r"\b{1}"), [])])
    assert_rejections(boundary_compilation,
                      [assertion + suffix for assertion in (r"\b", r"\B")
                       for suffix in ("{2}", "{0,2}", "{1,2}", "{2,2}", "{1,3}")],
                      "unsupported")
