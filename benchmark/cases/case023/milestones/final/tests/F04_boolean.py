# feature: F04
"""Boolean language acceptance: exactly F04.T01, F04.T02 and F04.T03.

Whole-input answers and complete search spans are independently specified.
No contextual assertions occur under complement. No regex implementation or
second product query supplies an oracle at judging time.
"""

from F01_helpers import matching
from F03_helpers import option_matching
from F04_helpers import assert_boolean_languages, assert_boolean_languages_in_modes


def test_intersection_same_span_and_precedence(matching):
    # F04.T01: each of the three constraints independently excludes a candidate.
    scenarios = [
        ("[a-z]+&a_*&_*z",
         [(b"az", True), (b"abz", True), (b"a!z", False),
          (b"bz", False), (b"ab", False), (b"", False)],
         [(b"!abz!az!", [[1, 4], [5, 7]]), (b"a!bz", [])]),
        ("(ab|abc)&(abc|bc)",
         [(b"abc", True), (b"ab", False), (b"bc", False)],
         [(b"ab abc bc abc", [[3, 6], [10, 13]])]),
        # Different starts, different ends and disjoint spans are all insufficient.
        ("ab&b", [(b"ab", False)], [(b"ab", [])]),
        ("ab&abc", [(b"abc", False)], [(b"abc", [])]),
        ("a&b", [(b"", False), (b"ab", False)], [(b"ab ba", [])]),
        # Concatenation binds above intersection, which binds above alternation.
        ("ab&ab", [(b"ab", True), (b"a", False), (b"abb", False)],
         [(b"!ab!", [[1, 3]])]),
        ("a|b&c", [(b"a", True), (b"b", False), (b"c", False)],
         [(b"abc", [[0, 1]])]),
        ("(a|b)&c", [(b"a", False), (b"b", False), (b"c", False)],
         [(b"abc", [])]),
        ("a&a|b", [(b"a", True), (b"b", True)],
         [(b"abc", [[0, 1], [1, 2]])]),
        ("a&(a|b)", [(b"a", True), (b"b", False)],
         [(b"abc", [[0, 1]])]),
        ("a+&aa", [(b"a", False), (b"aa", True), (b"aaa", False)],
         [(b"aaaaa", [[0, 2], [2, 4]])]),
        ("(ab&ab){2,3}",
         [(b"ab", False), (b"abab", True), (b"ababab", True),
          (b"abababab", False)],
         [(b"!abababab!abab!", [[1, 7], [10, 14]])]),
        ("x(ab&ab)y", [(b"xaby", True), (b"ab", False), (b"xacy", False)],
         [(b"ab!xaby!xacy", [[3, 7]])]),
        # An operand accepting only the empty span still constrains the span.
        ("()&a*", [(b"", True), (b"a", False), (b"aa", False)],
         [(b"aa", [[0, 0], [1, 1], [2, 2]])]),
        ("(a*&())b", [(b"b", True), (b"ab", False)], [(b"ab", [[1, 2]])]),
    ]
    assert_boolean_languages(matching, scenarios)


def test_complement_byte_language_and_empty_membership(matching, option_matching):
    # F04.T02: a complement is of whole byte strings, not characters or a
    # substring-absence test. Cover every single byte plus multi-byte members.
    samples = [b"", b"ab", b"aab", b"aba", b"xaby", b"aa",
               b"\xffab\n\x00", b"\xff\x80", b"\xc3\xa9", bytes(range(256))]
    samples.extend(bytes([value]) for value in range(256))
    scenarios = [
        ("~(ab)", [(data, data != b"ab") for data in samples],
         [(b"", [[0, 0]]), (b"ab", [[0, 1], [1, 2], [2, 2]]),
          (b"xaby", [[0, 4], [4, 4]]),
          (b"\xff\x00\n", [[0, 3], [3, 3]])]),
        ("~(_*ab_*)", [(data, b"ab" not in data) for data in samples],
         [(b"zabqab", [[0, 2], [2, 5], [5, 6], [6, 6]]),
          (b"\xff\x00\n", [[0, 3], [3, 3]]), (b"", [[0, 0]])]),
        ("~(a*)", [(data, any(byte != ord("a") for byte in data))
                    for data in samples],
         [(b"", []), (b"aaa", []), (b"aa!aa", [[0, 5]])]),
        ("~()", [(data, len(data) != 0) for data in samples],
         [(b"", []), (b"\xff\x00\n", [[0, 3]])]),
        ("~(_*)", [(data, False) for data in samples],
         [(b"", []), (b"\xff\x00\n", [])]),
    ]
    assert_boolean_languages(matching, scenarios)
    # The byte-string universe does not depend on the character-coverage mode.
    assert_boolean_languages_in_modes(option_matching, [
        (pattern, [(data, accepted(data)) for data in samples])
        for pattern, accepted in (("~(ab)", lambda d: d != b"ab"),
                                  ("~(_*ab_*)", lambda d: b"ab" not in d))
    ])


def test_nested_complement_and_boolean_composition(matching):
    # F04.T03: judge each language against independent answers, not merely
    # agreement between equivalent product expressions.
    union_members = [(b"", False), (b"ab", True), (b"c", True),
                     (b"a", False), (b"b", False), (b"abc", False),
                     (b"\xff", False)]
    scenarios = [
        ("~(~(ab|c))", union_members,
         [(b"!ab!c!", [[1, 3], [4, 5]])]),
        ("~(~(ab)&~(c))", union_members,
         [(b"!ab!c!", [[1, 3], [4, 5]])]),
        ("~(~(ab)|~(a_))",
         [(b"ab", True), (b"ac", False), (b"a", False),
          (b"", False), (b"abc", False)],
         [(b"ac!ab!a", [[3, 5]])]),
        ("~(ab)&[a-c]{2}",
         [(bytes([left, right]), bytes([left, right]) != b"ab")
          for left in b"abc" for right in b"abc"] +
         [(b"", False), (b"a", False), (b"abcd", False), (b"a\xff", False)],
         [(b"abacbb!", [[1, 3], [3, 5]])]),
        ("x~(ab)y",
         [(b"xy", True), (b"xaby", False), (b"xay", True),
          (b"xabcy", True), (b"xxaby", True), (b"x\xff\x00y", True)],
         [(b"!xaby!", []), (b"!xacy!", [[1, 5]]),
          (b"!xaby!xacy!", [[1, 10]])]),
        ("(~(a)&_){2,3}",
         [(b"", False), (b"1", False), (b"12", True), (b"123", True),
          (b"1234", False), (b"1a", False), (b"a1", False),
          (b"\xff\x00\n", True)],
         [(b"a12a\xff\x00\n4a", [[1, 3], [4, 7]])]),
        ("(~(a)&_)*",
         [(b"", True), (b"1234", True), (b"a", False), (b"1a", False),
          (b"\xff\x00\n", True)],
         [(b"a12a3", [[0, 0], [1, 3], [3, 3], [4, 5], [5, 5]])]),
        ("(~(a)&_)|ab",
         [(b"ab", True), (b"b", True), (b"\xff", True),
          (b"a", False), (b"aa", False), (b"", False)],
         [(b"aab!", [[1, 3], [3, 4]])]),
    ]
    assert_boolean_languages(matching, scenarios)
