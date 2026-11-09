# feature: F03
"""Character interpretation and options: exactly F03.T01 through F03.T12."""

from F01_helpers import matching, operation, pattern_request, assert_success_cases
from F03_helpers import (
    option_matching, unicode16, MODES, ASCII_SETS, CHARACTERS,
    unicode_ranges, in_ranges, boundary_text, scalar_spans, byte_spans,
    option_request, class_case, shorthand_predicate,
)


def test_wildcard_units_and_default(option_matching, matching):
    # F03.T01: byte offsets distinguish every UTF-8 width and include NUL.
    text = "Aé猫🦉\x00\nZ"
    actions = [operation("find_all", text.encode())]
    cases = []
    for mode in MODES:
        spans = (byte_spans(text, lambda b: b != 10) if mode in ("Ascii", "Default")
                 else scalar_spans(text, lambda c: c != "\n"))
        cases.append((option_request(".", actions, mode), [spans]))
        cases.append((option_request("_", actions, mode), [byte_spans(text)]))
    cases.append((option_request(".", actions), [byte_spans(text, lambda b: b != 10)]))
    assert_success_cases(option_matching, cases)
    assert_success_cases(matching, [
        (pattern_request(".", actions), [byte_spans(text, lambda b: b != 10)]),
        (pattern_request("_", actions), [byte_spans(text)]),
    ])


def test_standalone_membership_and_default(option_matching, matching, unicode16):
    # F03.T02: default construction must accept non-ASCII limited word members
    # while excluding wider word members; equal dot widths cannot prove this.
    tables = unicode_ranges(unicode16, [r"\w", r"\d", r"\s"])
    cases, default_cases = [], []
    for kind, table in zip("wds", tables):
        for mode in MODES:
            accepts = shorthand_predicate(kind, mode, table)
            cases.append(class_case("\\" + kind, CHARACTERS, accepts, mode))
        accepts = shorthand_predicate(kind, "Default", table)
        case = class_case("\\" + kind, CHARACTERS, accepts)
        cases.append(case)  # with_options without selecting a character mode
        default_cases.append(case)  # Regex::new, independently judged
    assert_success_cases(option_matching, cases)
    assert_success_cases(matching, default_cases)


def test_full_unicode_shorthand_properties(option_matching, unicode16):
    # F03.T03: each standard interval's boundaries, not Python's Unicode version.
    tables = unicode_ranges(unicode16, [r"[\p{Alphabetic}\p{Join_Control}\p{M}\p{Nd}\p{Pc}]",
                                        r"\p{Nd}", r"\p{White_Space}"])
    cases = []
    for kind, table in zip("wds", tables):
        text = boundary_text(table)
        cases.append(class_case("\\" + kind, text,
                                lambda c, t=table: in_ranges(c, t), "Full", full=True))
    assert_success_cases(option_matching, cases)


def test_negated_shorthands_and_classes(option_matching, unicode16):
    # F03.T04: excluded members and successful complementary spans both matter.
    tables = unicode_ranges(unicode16, [r"\w", r"\d", r"\s"])
    actions = [operation("find_all", CHARACTERS.encode())]
    cases = []
    for mode in MODES:
        for kind, table in zip("wds", tables):
            positive = shorthand_predicate(kind, mode, table)
            # FP-03.04 distinguishes scalar-wide standalone shorthands from
            # explicit negative classes, whose width depends on the mode.
            spans = scalar_spans(CHARACTERS, lambda c: not positive(c))
            cases.append((option_request("\\" + kind.upper(), actions, mode), [spans]))
        excluded = set("AQ09\n")
        spans = (byte_spans(CHARACTERS, lambda b: chr(b) not in excluded) if mode == "Ascii"
                 else scalar_spans(CHARACTERS, lambda c: c not in excluded))
        cases.append((option_request(r"[^AQ09\n]", actions, mode), [spans]))
        # Both polarities in one pattern keep their own memberships.
        for kind, table in zip("wds", tables):
            positive = shorthand_predicate(kind, mode, table)
            pair = "\\" + kind + "\\" + kind.upper()
            reverse = "\\" + kind.upper() + "\\" + kind
            units = list(CHARACTERS)
            ends = [len("".join(units[:i + 1]).encode()) for i in range(len(units))]
            for pattern, first, second in ((pair, True, False), (reverse, False, True)):
                spans, i = [], 0
                while i + 1 < len(units):
                    if positive(units[i]) == first and positive(units[i + 1]) == second:
                        spans.append([ends[i] - len(units[i].encode()), ends[i + 1]])
                        i += 2
                    else:
                        i += 1
                cases.append((option_request(pattern, actions, mode), [spans]))
        if mode != "Ascii":
            excluded_unicode = set("éΩ猫🦉")
            cases.append(class_case("[^éΩ猫🦉]", CHARACTERS,
                                    lambda c: c not in excluded_unicode, mode))
    assert_success_cases(option_matching, cases)


def test_literals_ranges_and_named_properties(option_matching, unicode16):
    # F03.T05: independent category, script and binary-property data, including
    # complements. All probes stay on well-formed Unicode scalar sequences.
    patterns = [r"\p{Letter}", r"\p{Number}", r"\p{Mark}", r"\p{Greek}",
                r"\p{Devanagari}", r"\p{Han}", r"\p{Uppercase}",
                r"\p{Alphabetic}", r"\p{Join_Control}", r"\p{White_Space}",
                r"\P{Greek}", r"\P{Number}", r"\P{White_Space}"]
    tables = unicode_ranges(unicode16, patterns)
    cases = []
    for mode in MODES[1:]:
        for pattern, table in zip(patterns, tables):
            cases.append(class_case(pattern, boundary_text(table),
                                    lambda c, t=table: in_ranges(c, t), mode, full=True))
        text = "\u08ff\u0900क\u097f\u0980𐐀𐐁𐐂𐐃é猫🦉!"
        cases.append(class_case(r"[\u{0900}-\u{097F}\u{10400}-\u{10402}]", text,
                                lambda c: 0x900 <= ord(c) <= 0x97F or 0x10400 <= ord(c) <= 0x10402,
                                mode, full=True))
        for literal in ("é", "猫", "🦉"):
            cases.append(class_case(literal, text, lambda c, x=literal: c == x, mode, full=True))
    assert_success_cases(option_matching, cases)


def test_special_ascii_hex_and_utf8_properties(option_matching):
    # F03.T06: special properties retain their own width, independently of dot.
    cases = []
    for mode in MODES:
        cases.append(class_case(r"\p{ascii}", CHARACTERS, lambda c: ord(c) < 128, mode))
        cases.append(class_case(r"\p{hex}", CHARACTERS,
                                lambda c: c in "0123456789abcdefABCDEF", mode))
        cases.append(class_case(r"\p{utf8}", CHARACTERS, lambda c: True, mode))
    assert_success_cases(option_matching, cases)


def test_case_sensitivity_and_simple_folding(option_matching, matching, unicode16):
    # F03.T07: Kelvin sign, long s, final sigma, sharp s and dotted I distinguish
    # Unicode simple-fold equivalence from ASCII lowercasing or full folding.
    patterns = ["k", "s", "Σ", "ß", "İ", "[A-C]", "[ΣΤ]"]
    tables = unicode_ranges(unicode16, ["(?i:" + p + ")" for p in patterns if p != "İ"])
    folded = dict(zip([p for p in patterns if p != "İ"], tables))
    text = "aAbBcCdDkKKsSſΣσςΤτßẞİiIı!"
    cases, defaults = [], []
    for mode in MODES:
        for pattern in patterns:
            if mode == "Ascii" and pattern not in ("k", "s", "[A-C]"):
                continue  # Non-ASCII literals in ASCII-only mode are not promised.
            sensitive_members = {"[A-C]": "ABC", "[ΣΤ]": "ΣΤ"}.get(pattern, pattern)
            sensitive = lambda c, members=sensitive_members: c in members
            table = folded.get(pattern)
            insensitive = (lambda c: c == "İ") if table is None else (
                lambda c, t=table, m=mode: in_ranges(c, t) and (m != "Ascii" or ord(c) < 128))
            cases.append(class_case(pattern, text, sensitive, mode))
            cases.append(class_case(pattern, text, insensitive, mode, case_insensitive=True))
            if mode == "Default":
                defaults.append(class_case(pattern, text, sensitive))
    # Explicit negated classes exclude the case-fold equivalents of their
    # members, and only those.
    for mode in MODES:
        for members in ("a", "a-c", "k"):
            pattern = "[^" + members + "]"
            table = unicode_ranges(unicode16, ["(?i:[" + members + "])"])[0]
            excluded = (lambda c, t=table, m=mode: in_ranges(c, t)
                        and (m != "Ascii" or ord(c) < 128))
            sample = "aAbBcCdDkKKsS!"
            if mode == "Ascii":
                sample = "aAbBcCdDkKsS!"
                accepts = lambda c, e=excluded: not e(c)
                cases.append((option_request(pattern, [operation("find_all", sample.encode())],
                                             mode, case_insensitive=True),
                              [byte_spans(sample, lambda b, a=accepts: a(chr(b)))]))
            else:
                cases.append(class_case(pattern, sample, lambda c, e=excluded: not e(c),
                                        mode, case_insensitive=True))
    # Simple folding never expands one scalar into multiple input characters.
    cases.append((option_request("ß", [operation("is_full_match", b"ss"),
                                       operation("is_full_match", b"SS")],
                                 "Full", case_insensitive=True), [False, False]))
    assert_success_cases(option_matching, cases)
    assert_success_cases(matching, defaults)


def test_dot_all_preserves_mode_width(option_matching, matching):
    # F03.T08: both arms contain positive matches; only line-feed inclusion varies.
    text = "\nA\ré\n猫🦉\n"
    actions = [operation("find_all", text.encode())]
    cases = []
    for mode in MODES:
        for enabled in (False, True):
            spans = (byte_spans(text, lambda b: enabled or b != 10) if mode in ("Ascii", "Default")
                     else scalar_spans(text, lambda c: enabled or c != "\n"))
            options = {"dot_matches_new_line": True} if enabled else {}
            cases.append((option_request(".", actions, mode, **options), [spans]))
            # Inline enabling has the same width as the global option.
            if enabled:
                for inline in ("(?s).", "(?s:.)"):
                    cases.append((option_request(inline, actions, mode), [spans]))
    assert_success_cases(option_matching, cases)
    assert_success_cases(matching, [(pattern_request(".", actions),
                                     [byte_spans(text, lambda b: b != 10)])])


def test_extended_whitespace_comments_and_escapes(option_matching, matching):
    # F03.T09: only conventional ASCII spacing is used; no incidental lexer set.
    rows = [
        ("a b", "ab|a b", [[3, 6]], [[0, 2]]),
        ("a\t b", "ab|a\t b", [[3, 7]], [[0, 2]]),
        ("a # first line\n b # second line\n c", "abc|ab|ac", [], [[0, 3]]),
        (r"a\ b", "ab|a b", [[3, 6]], [[3, 6]]),
        (r"a\#b", "ab|a#b", [[3, 6]], [[3, 6]]),
        ("a\\# # comment\n \\ b", "a# b|a#b|ab", [], [[0, 4]]),
        # Line feed outside a comment is spacing too.
        ("a\nb", "ab|a\nb", [[3, 6]], [[0, 2]]),
    ]
    cases, defaults = [], []
    for pattern, text, ordinary, extended in rows:
        actions = [operation("find_all", text.encode())]
        cases.append((option_request(pattern, actions), [ordinary]))
        cases.append((option_request(pattern, actions, ignore_whitespace=True), [extended]))
        defaults.append((pattern_request(pattern, actions), [ordinary]))
    assert_success_cases(option_matching, cases)
    assert_success_cases(matching, defaults)


def test_single_family_inline_options_and_restoration(option_matching, unicode16):
    # F03.T10: no pattern mixes option families. Each pair varies only the
    # global setting; positional and scoped enable/disable must take precedence.
    rows = [
        ("case_insensitive", "a(?i)b", "aB|AB|ab", [[[0, 2], [6, 8]], [[0, 2], [3, 5], [6, 8]]]),
        ("case_insensitive", "a(?-i)b", "Ab|AB|ab", [[[6, 8]], [[0, 2], [6, 8]]]),
        ("case_insensitive", "a(?i:b)c", "aBc|aBC|ABC", [[[0, 3]], [[0, 3], [4, 7], [8, 11]]]),
        ("case_insensitive", "a(?-i:b)c", "AbC|ABC|abc", [[[8, 11]], [[0, 3], [8, 11]]]),
        ("case_insensitive", "a((?i)b)c", "aBc|aBC|ABC", [[[0, 3]], [[0, 3], [4, 7], [8, 11]]]),
        ("case_insensitive", "a((?-i)b)c", "AbC|ABC|abc", [[[8, 11]], [[0, 3], [8, 11]]]),
        ("dot_matches_new_line", "a(?s).b.c", "a\nb\nc|axbzc", [[[0, 5], [6, 11]], [[0, 5], [6, 11]]]),
        ("dot_matches_new_line", "a(?-s).b.c", "a\nb\nc|axbzc", [[[6, 11]], [[6, 11]]]),
        ("dot_matches_new_line", "a(?s:.b).c", "a\nbzc|a\nb\nc|axbzc", [[[0, 5], [12, 17]], [[0, 5], [6, 11], [12, 17]]]),
        ("dot_matches_new_line", "a(?-s:.b).c", "axb\nc|a\nbzc|axbzc", [[[12, 17]], [[0, 5], [12, 17]]]),
        ("dot_matches_new_line", "a((?s).b).c", "a\nbzc|a\nb\nc", [[[0, 5]], [[0, 5], [6, 11]]]),
        ("dot_matches_new_line", "a((?-s).b).c", "axb\nc|a\nbzc", [[], [[0, 5]]]),
        ("multiline", "^a$", "a\na", [[], [[0, 1], [2, 3]]]),
        ("multiline", "(?m)^a$", "a\na", [[[0, 1], [2, 3]], [[0, 1], [2, 3]]]),
        ("multiline", "(?-m)^a$", "a\na", [[], []]),
        ("multiline", "(?m:^a$)|^b$", "a\nb", [[[0, 1]], [[0, 1], [2, 3]]]),
        ("multiline", "(?-m:^a$)|^b$", "a\nb", [[], [[2, 3]]]),
        ("multiline", "((?m)^a$)|^b$", "a\nb", [[[0, 1]], [[0, 1], [2, 3]]]),
        ("multiline", "((?-m)^a$)|^b$", "a\nb", [[], [[2, 3]]]),
        ("ignore_whitespace", "a (?x)b c", "a bc|abc", [[[0, 4]], [[5, 8]]]),
        ("ignore_whitespace", "a (?-x)b c", "a b c|ab c", [[[0, 5]], [[6, 10]]]),
        ("ignore_whitespace", "a(?x: b ) c", "ab c|abc", [[[0, 4]], [[5, 8]]]),
        ("ignore_whitespace", "a(?-x: b ) c", "a b  c|a b c", [[[0, 6]], [[7, 12]]]),
        ("ignore_whitespace", "a((?x) b ) c", "ab c|abc", [[[0, 4]], [[5, 8]]]),
        ("ignore_whitespace", "a((?-x) b ) c", "a b  c|a b c", [[[0, 6]], [[7, 12]]]),
    ]
    rows += [
        # A positional setting reaches the end of the enclosing group, across
        # later alternatives, and an ordinary group inherits the active setting.
        ("case_insensitive", "x(?i)a|b", "B|xA|Xa", [[[0, 1], [2, 4]], [[0, 1], [2, 4], [5, 7]]]),
        ("case_insensitive", "(?-i)a|b", "A|B|a|b", [[[4, 5], [6, 7]], [[4, 5], [6, 7]]]),
        ("case_insensitive", "(?i:a(b)c)", "ABC|abc", [[[0, 3], [4, 7]], [[0, 3], [4, 7]]]),
        ("case_insensitive", "(?i)a(?:b(c))", "ABC|aBc", [[[0, 3], [4, 7]], [[0, 3], [4, 7]]]),
        ("dot_matches_new_line", "x(?s)a.|b.", "b\n|xa\n|bz", [[[0, 2], [3, 6], [7, 9]], [[0, 2], [3, 6], [7, 9]]]),
        ("multiline", "(?-m)a$|b$", "b\nb", [[[2, 3]], [[2, 3]]]),
    ]
    cases = []
    for option, pattern, text, expected in rows:
        for enabled in (False, True):
            cases.append((option_request(pattern, [operation("find_all", text.encode())],
                                         **{option: enabled}), [expected[int(enabled)]]))
    # Inline case-insensitivity uses the same simple-fold classes as the global
    # option in every Unicode-aware mode, positional and scoped alike.
    sigma, e_acute = unicode_ranges(unicode16, ["(?i:σ)", "(?i:é)"])
    for mode in MODES[1:]:
        text = "aΣaσaςas"
        cases.append((option_request("a(?i)σ", [operation("find_all", text.encode())], mode),
                      [[[0, 3], [3, 6], [6, 9]]]))
        sample = "éxÉxexěx"
        spans = [[o, o + len(c.encode()) + 1] for o, c in
                 zip([0, 3, 6, 8], "éÉeě") if in_ranges(c, e_acute)]
        cases.append((option_request("(?i:é)x", [operation("find_all", sample.encode())], mode),
                      [spans]))
        assert all(in_ranges(c, sigma) for c in "Σσς")
    # Global options combined with extended mode keep each of their effects.
    cases.append((option_request("a . b", [operation("find_all", b"A\nB|a\nb|AxB")],
                                 case_insensitive=True, dot_matches_new_line=True,
                                 ignore_whitespace=True), [[[0, 3], [4, 7], [8, 11]]]))
    assert_success_cases(option_matching, cases)


def test_positive_shorthand_class_unions(option_matching, unicode16):
    # F03.T11: singleton, literal, range and shorthand-union forms have distinct
    # required semantics; these loops stay within the one planned measurement.
    tables = unicode_ranges(unicode16, [r"\w", r"\d", r"\s"])
    cases = []
    for mode in MODES:
        predicates = {k: shorthand_predicate(k, mode, table, combined=True)
                      for k, table in zip("wds", tables)}
        for kind, table in zip("wds", tables):
            standalone = shorthand_predicate(kind, mode, table)
            cases.append(class_case("[\\" + kind + "]", CHARACTERS, standalone, mode))
            combined = predicates[kind]
            cases.append(class_case("[\\" + kind + "!]", CHARACTERS,
                                    lambda c, p=combined: p(c) or c == "!", mode))
            cases.append(class_case("[\\" + kind + ":-@]", CHARACTERS,
                                    lambda c, p=combined: p(c) or ":" <= c <= "@", mode))
        for first, second in (("w", "s"), ("d", "s"), ("w", "d")):
            cases.append(class_case("[\\" + first + "\\" + second + "]", CHARACTERS,
                                    lambda c, p=predicates[first], q=predicates[second]: p(c) or q(c), mode))
    assert_success_cases(option_matching, cases)


def test_complementary_shorthand_pairs(option_matching):
    # F03.T12: complementary pairs are universal, including newline, and their
    # width differs from standalone negated shorthands in limited Unicode mode.
    text = "a_7! \t\n\x00é猫🦉"
    cases = []
    for mode in MODES:
        spans = byte_spans(text) if mode in ("Ascii", "Default") else scalar_spans(text)
        for pair in (r"[\w\W]", r"[\d\D]", r"[\s\S]", r"[\W\w]", r"[\D\d]", r"[\S\s]"):
            cases.append((option_request(pair, [operation("find_all", text.encode())], mode), [spans]))
    assert_success_cases(option_matching, cases)
