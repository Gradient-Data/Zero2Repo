# feature: F02
"""Literal semantics through both public escaping entries (F02.T01)."""

from F01_helpers import matching, operation, pattern_request, assert_success_cases
from F02_helpers import escaping


def test_literal_escaping_and_append(escaping, matching):
    # Each operator is isolated so another malformed operator cannot conceal
    # its accidental interpretation. Compound text also exercises escape syntax.
    literals = ["Invoice 27", "", "é猫🦉", "a\x00b\t c\nd",
                r"\d+\p{L}", "[ab]|(cd){2}", " \tEdge Space\n ", "aaBB"]
    literals.extend("p" + char + "q" for char in r"\.+*?()|[]{}^$#&-~_")
    # Ordinary punctuation, including characters that begin other escapes
    # when preceded by a backslash, must remain literal as well.
    literals.append("a<b>c\"%',/:;=@`")
    prefix = "(?:L|R):"
    specs = [{"text": text, "prefix": prefix} for text in literals]
    observations = escaping.json(specs).value
    assert len(observations) == len(specs), observations
    cases = []
    for text, observation in zip(literals, observations):
        escaped = observation["escaped"]
        appended = observation["appended"]
        assert isinstance(escaped, str), observation
        twice = observation["appended_twice"]
        assert isinstance(appended, str), observation
        assert isinstance(twice, str), observation
        assert appended[:len(prefix)] == prefix, (text, observation)
        assert twice[:len(appended)] == appended, (text, observation)
        # Interpret each output separately; equivalent escaped spellings need
        # neither equal each other nor equal the reference's spelling.
        variants = [(escaped, ""), (appended, "L:"), (appended, "R:")]
        for pattern, lead in variants:
            literal = (lead + text).encode("utf-8")
            actions = [operation("is_full_match", literal),
                       operation("find_all", literal)]
            expected = [True, [[0, len(literal)]]]
            if text:
                # Replace each scalar independently, preserving UTF-8 byte
                # length. These are literal contrasts, not a regex oracle.
                for index, char in enumerate(text):
                    replacement = {1: "!", 2: "ö", 3: "犬", 4: "🐈"}[len(char.encode("utf-8"))]
                    assert replacement != char
                    changed = (lead + text[:index] + replacement + text[index + 1:]).encode("utf-8")
                    assert len(changed) == len(literal)
                    actions.extend([operation("is_full_match", changed),
                                    operation("find_all", changed)])
                    expected.extend([False, []])
                    # Other spellings a literal must not accept: the character
                    # repeated, a case partner, or different spacing.
                    others = [char + char]
                    if char.swapcase() != char and len(char.swapcase()) == 1:
                        others.append(char.swapcase())
                    if char.isspace():
                        others.append("\t" if char != "\t" else " ")
                    for other in others:
                        changed = (lead + text[:index] + other + text[index + 1:]).encode("utf-8")
                        actions.append(operation("is_full_match", changed))
                        expected.append(False)
            else:
                actions.append(operation("is_full_match", (lead + "x").encode()))
                expected.append(False)
            if literal:
                surrounded = b"\x01" + literal + b"\x02" + literal + b"\x03"
                actions.extend([operation("is_full_match", surrounded),
                                operation("find_all", surrounded)])
                expected.extend([False, [[1, 1 + len(literal)],
                                         [2 + len(literal), 2 + 2 * len(literal)]]])
            cases.append((pattern_request(pattern, actions), expected))
        # The existing pattern prefix must remain active, rather than becoming
        # literal text, and cannot be silently discarded during appending.
        cases.append((pattern_request(appended, [
            operation("is_full_match", ("X:" + text).encode()),
            operation("is_full_match", text.encode()),
        ]), [False, False]))
        # Repeated appends each contribute the literal once more.
        doubled = ("R:" + text + text).encode("utf-8")
        cases.append((pattern_request(twice, [
            operation("is_full_match", doubled),
            operation("is_full_match", ("R:" + text).encode("utf-8")),
        ]), [True, not text]))
        # The returned fragment composes inside a larger pattern at any position,
        # including when the literal is empty.
        inner = ("L" + text + "R").encode("utf-8")
        cases.append((pattern_request("L" + escaped + "R", [
            operation("find_all", b"\x01" + inner + b"\x02"),
        ]), [[[1, 1 + len(inner)]]]))
    assert_success_cases(matching, cases)
