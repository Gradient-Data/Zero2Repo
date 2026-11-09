# feature: F02
"""Pattern matching controls on the scan path."""

from __future__ import annotations

import pytest

from _helpers import make_tree, unique_token
from F01_helpers import REGEX_ERROR_LABEL, assert_exit, err_lines, out_lines, tg
from F02_helpers import selected, sha256_of, write_lines


def _case_file(tmp_path):
    tok = unique_token()
    lines = [tok, tok.upper(), tok.capitalize(), f"pre {tok} post", "unrelated"]
    write_lines(tmp_path / "c.txt", lines)
    return tok, lines


# F02.T01
def test_case_controls_and_precedence(tmp_path):
    tok, lines = _case_file(tmp_path)
    lower_only = [tok, f"pre {tok} post"]
    every = lines[:4]
    cap = tok.capitalize()

    assert selected([tok, "c.txt"], tmp_path) == lower_only
    assert selected([cap, "c.txt"], tmp_path) == [cap]
    for flag in ("-i", "--ignore-case"):
        assert selected([flag, tok, "c.txt"], tmp_path) == every
        assert selected([flag, cap, "c.txt"], tmp_path) == every
    for flag in ("-S", "--smart-case"):
        # All-lowercase pattern: insensitive.  Pattern with an uppercase: sensitive.
        assert selected([flag, tok, "c.txt"], tmp_path) == every
        assert selected([flag, cap, "c.txt"], tmp_path) == [cap]
    # Case-sensitive overrides smart case, whichever comes first.
    assert selected(["-S", "-s", tok, "c.txt"], tmp_path) == lower_only
    assert selected(["-s", "-S", tok, "c.txt"], tmp_path) == lower_only
    assert selected(["--smart-case", "--case-sensitive", tok, "c.txt"], tmp_path) == lower_only
    assert selected(["-S", "-s", tok.upper(), "c.txt"], tmp_path) == [tok.upper()]
    # Ignore-case still wins over case-sensitive.
    assert selected(["-i", "-s", tok, "c.txt"], tmp_path) == every
    assert selected(["-s", "-i", tok, "c.txt"], tmp_path) == every


# F02.T02
def test_inline_case_flags(tmp_path):
    tok = unique_token(length=9)
    a, b, c = tok[:5], tok[5:8], tok[8:]
    lines = [
        a + b + c,                  # all lower
        a + b.upper() + c,          # only the group's text differs
        a.upper() + b.upper() + c,  # text outside the group differs
        a + b + c.upper(),          # text outside the group differs
        a.upper() + b + c,          # text outside the group differs
        (a + b + c).upper(),
        "unrelated",
    ]
    write_lines(tmp_path / "f.txt", lines)

    assert selected([f"(?i){a}{b}{c}", "f.txt"], tmp_path) == lines[:6]
    assert selected([f"{a}(?i:{b}){c}", "f.txt"], tmp_path) == lines[:2]
    assert selected([f"(?i:{a}){b}{c}", "f.txt"], tmp_path) == [lines[0], lines[4]]
    # The flag can be switched off again for the rest of the pattern.
    assert selected([f"(?i){a}(?-i){b}{c}", "f.txt"], tmp_path) == [lines[0], lines[4]]
    # Live baseline: no flag, only the exact line.
    assert selected([f"{a}{b}{c}", "f.txt"], tmp_path) == lines[:1]


# F02.T03
def test_fixed_strings_match_literally(tmp_path):
    tok = unique_token()
    literal = f"{tok}.a+"
    lines = [f"x {literal} y", f"{tok}Zaaa", f"{tok}.a", f"{tok}(1|2)[", f"{tok}1"]
    write_lines(tmp_path / "f.txt", lines)

    for flag in ("-F", "--fixed-strings"):
        assert selected([flag, literal, "f.txt"], tmp_path) == [lines[0]]
    # The same text as a regex matches the other lines too.
    assert selected([literal, "f.txt"], tmp_path) == lines[:3]

    for args in (["-e", literal, "-e", tok + "(x)"], ["-f", "literal-patterns"]):
        (tmp_path / "literal-patterns").write_text(literal + "\n" + tok + "(x)\n")
        assert selected(["-F", *args, "f.txt"], tmp_path) == [lines[0]]

    # Text that is not even a valid regex is found literally.
    broken = f"{tok}(1|2)["
    assert selected(["-F", broken, "f.txt"], tmp_path) == [lines[3]]
    r = tg([broken, "f.txt"], cwd=tmp_path)
    assert_exit(r, "error")


# F02.T04
def test_word_and_line_regexp(tmp_path):
    tok = unique_token()
    lines = [tok, f"x{tok}", f"{tok}y", f"a {tok} b", f"{tok}-z", f"_{tok}", f"({tok})", f"{tok}9"]
    write_lines(tmp_path / "f.txt", lines)

    # Live baseline: every line contains the token.
    assert selected([tok, "f.txt"], tmp_path) == lines
    bounded = [tok, f"a {tok} b", f"{tok}-z", f"({tok})"]
    for flag in ("-w", "--word-regexp"):
        assert selected([flag, tok, "f.txt"], tmp_path) == bounded
    for flag in ("-x", "--line-regexp"):
        assert selected([flag, tok, "f.txt"], tmp_path) == [tok]
    # Line-regexp wins in both orders.
    assert selected(["-w", "-x", tok, "f.txt"], tmp_path) == [tok]
    assert selected(["-x", "-w", tok, "f.txt"], tmp_path) == [tok]
    # A pattern that as a whole line needs a non-word edge still matches under
    # both, which word-regexp alone would not require to be the whole line.
    assert selected(["-x", "-w", f"a {tok} b", "f.txt"], tmp_path) == [f"a {tok} b"]
    assert selected(["-x", "-w", f"{tok} b", "f.txt"], tmp_path, expect="no_match") == []


# F02.T05
def test_invert_match(tmp_path):
    tok = unique_token()
    lines = [f"{tok} one", "plain a", f"two {tok}", "plain b", ""]
    write_lines(tmp_path / "f.txt", lines)
    for flag in ("-v", "--invert-match"):
        assert selected([flag, tok, "f.txt"], tmp_path) == ["plain a", "plain b", ""]

    write_lines(tmp_path / "all.txt", [f"{tok} one", f"two {tok}"])
    r = tg(["-v", tok, "all.txt"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b""
    # Live baseline for that file: without inversion both lines are selected.
    assert selected([tok, "all.txt"], tmp_path) == [f"{tok} one", f"two {tok}"]


# F02.T06
def test_multiple_patterns_are_ored(tmp_path):
    a, b, c, d = (unique_token() for _ in range(4))
    lines = [f"has {a}", f"has {b}", f"x {c} y", f"has {d}", "none of them", f"{a} and {c}"]
    write_lines(tmp_path / "f.txt", lines)

    assert selected(["-e", a, "-e", b, "f.txt"], tmp_path) == [lines[0], lines[1], lines[5]]
    assert selected(["--regexp", a, "--regexp", d, "f.txt"], tmp_path) == [lines[0], lines[3], lines[5]]

    # Pattern file: blank lines are skipped and patterns are trimmed.
    (tmp_path / "pats").write_text(f"\n   {c}   \n\n\t{d}\t\n\n")
    assert selected(["-f", "pats", "f.txt"], tmp_path) == [lines[2], lines[3], lines[5]]
    assert selected(["--file", "pats", "f.txt"], tmp_path) == [lines[2], lines[3], lines[5]]
    (tmp_path / "blank-patterns").write_text(" \n\t\n")
    assert selected(["-f", "blank-patterns", "f.txt"], tmp_path) == lines
    # Both sources together.
    assert selected(["-e", b, "-f", "pats", "f.txt"], tmp_path) == lines[1:4] + [lines[5]]


# F02.T07
def test_multiline_rules(tmp_path):
    a, b, c, d = (unique_token() for _ in range(4))
    lines = [a, b, f"{c} {b}", d, f"{b} tail"]
    write_lines(tmp_path / "f.txt", lines)

    # Without multiline a match never crosses a line boundary ...
    assert selected([f"{a}\\n{b}", "f.txt"], tmp_path, expect="no_match") == []
    # ... and anchors apply to each line.
    assert selected([f"^{b}$", "f.txt"], tmp_path) == [b]
    assert selected([f"^{b}", "f.txt"], tmp_path) == [b, f"{b} tail"]
    assert selected([f"{b}$", "f.txt"], tmp_path) == [b, f"{c} {b}"]

    for flag in ("-U", "--multiline"):
        assert selected([flag, f"{a}\\n{b}", "f.txt"], tmp_path) == [a, b]
        assert selected([flag, f"{b}\\n{c} {b}\\n{d}", "f.txt"], tmp_path) == [b, f"{c} {b}", d]
        # A dot still does not match a newline.
        assert selected([flag, f"{a}.{b}", "f.txt"], tmp_path, expect="no_match") == []

    # Multiline-dotall alone implies multiline.
    assert selected(["--multiline-dotall", f"{a}.{b}", "f.txt"], tmp_path) == [a, b]
    assert selected(["--multiline-dotall", f"{a}.*{d}", "f.txt"], tmp_path) == lines[:4]
    assert selected(["-U", "--multiline-dotall", f"{c} {b}.{d}", "f.txt"], tmp_path) == [f"{c} {b}", d]


def _engine_file(tmp_path):
    tok = unique_token()
    lines = [f"{tok}bar", f"{tok}baz", f"{tok}{tok}", f"{tok} {tok}x", "zz yy"]
    write_lines(tmp_path / "e.txt", lines)
    return tok, lines


ENGINE_ARGS = {
    "auto-default": [],
    "auto": ["--engine", "auto"],
    "default": ["--engine", "default"],
    "pcre2": ["--engine", "pcre2"],
    "-P": ["-P"],
    "--pcre2": ["--pcre2"],
}


# F02.T08
def test_engine_selection(tmp_path):
    tok, lines = _engine_file(tmp_path)
    lookahead = f"{tok}(?=bar)"
    lookbehind = f"(?<={tok})baz"
    backref = f"({tok})\\1"

    # A plain pattern gives the same output under every engine choice.
    for name, eng in ENGINE_ARGS.items():
        assert selected([*eng, f"{tok}ba\\w", "e.txt"], tmp_path) == lines[:2], name

    for name in ("auto-default", "auto", "pcre2", "-P", "--pcre2"):
        eng = ENGINE_ARGS[name]
        assert selected([*eng, lookahead, "e.txt"], tmp_path) == [lines[0]], name
        assert selected([*eng, lookbehind, "e.txt"], tmp_path) == [lines[1]], name
        assert selected([*eng, backref, "e.txt"], tmp_path) == [lines[2]], name

    for pattern in (lookahead, lookbehind, backref):
        r = tg(["--engine", "default", pattern, "e.txt"], cwd=tmp_path)
        assert_exit(r, "error")
        assert REGEX_ERROR_LABEL in r.err, r.describe()


# F02.T09
def test_standard_engine_syntax(tmp_path):
    tok = unique_token()
    lines = ["αβγ", tok, "12345", "٣٤٥", "naïve", f"{tok}=678", "Ünï", "tab\there"]
    write_lines(tmp_path / "u.txt", lines)
    for eng in ([], ["--engine", "default"]):
        # Unicode script and general-category classes.
        assert selected([*eng, "^\\p{Greek}+$", "u.txt"], tmp_path) == ["αβγ"]
        assert selected([*eng, "^\\p{Lu}", "u.txt"], tmp_path) == ["Ünï"]
        # POSIX bracket classes are ASCII-only.
        assert selected([*eng, "^[[:alpha:]]+$", "u.txt"], tmp_path) == [tok]
        assert selected([*eng, "^[[:digit:]]+$", "u.txt"], tmp_path) == ["12345"]
        # Perl classes are Unicode-aware by default.
        assert selected([*eng, "^\\d+$", "u.txt"], tmp_path) == ["12345", "٣٤٥"]
        # An ASCII-only class inside a pattern via the inline flag.
        assert selected([*eng, "^(?-u:\\w)+$", "u.txt"], tmp_path) == [tok, "12345"]
        # Named captures, both spellings, and non-capturing groups.
        assert selected([*eng, f"(?P<k>{tok})=(?<v>\\d+)", "u.txt"], tmp_path) == [f"{tok}=678"]
        assert selected([*eng, "-o", "-r", "${v}/${k}", f"(?P<k>{tok})=(?<v>\\d+)", "u.txt"],
                        tmp_path) == [f"678/{tok}"]
        # Escapes and counted repetition.
        assert selected([*eng, "^tab\\there$", "u.txt"], tmp_path) == ["tab\there"]
        assert selected([*eng, "^\\d{5}$", "u.txt"], tmp_path) == ["12345"]
        assert selected([*eng, "^\\x{3b1}", "u.txt"], tmp_path) == ["αβγ"]


# F02.T10
def test_no_unicode_turns_off_unicode_classes(tmp_path):
    tok = unique_token()
    lines = ["αβγ", tok, "12345", "٣٤٥", "naïve"]
    write_lines(tmp_path / "u.txt", lines)

    assert selected(["^\\w+$", "u.txt"], tmp_path) == lines
    assert selected(["--no-unicode", "^\\w+$", "u.txt"], tmp_path) == [tok, "12345"]
    assert selected(["^\\d+$", "u.txt"], tmp_path) == ["12345", "٣٤٥"]
    assert selected(["--no-unicode", "^\\d+$", "u.txt"], tmp_path) == ["12345"]


# F02.T11
def test_replace_expands_captures_and_never_modifies_files(tmp_path):
    k1, v1, k2, v2 = (unique_token() for _ in range(4))
    lines = [f"{k1}={v1}", f"lead {k2}={v2} tail", "no pair here"]
    path = write_lines(tmp_path / "r.txt", lines)
    before = sha256_of(path)
    numbered = "(\\w+)=(\\w+)"
    named = "(?P<key>\\w+)=(?P<val>\\w+)"

    for flag in ("-r", "--replace"):
        assert selected([flag, "$2<$1", numbered, "r.txt"], tmp_path) == [
            f"{v1}<{k1}", f"lead {v2}<{k2} tail"]
    assert selected(["-r", "${val}->${key}", named, "r.txt"], tmp_path) == [
        f"{v1}->{k1}", f"lead {v2}->{k2} tail"]
    assert selected(["-r", "${2}${1}", numbered, "r.txt"], tmp_path) == [
        f"{v1}{k1}", f"lead {v2}{k2} tail"]
    # With only-matching, only the replacement texts.
    assert selected(["-o", "-r", "$2", numbered, "r.txt"], tmp_path) == [v1, v2]
    assert selected(["-o", "-r", "[${key}]", named, "r.txt"], tmp_path) == [f"[{k1}]", f"[{k2}]"]
    # A replacement without group references replaces each match.
    assert selected(["-r", "#", "=", "r.txt"], tmp_path) == [f"{k1}#{v1}", f"lead {k2}#{v2} tail"]

    twice = f"{k1}={v1} {k2}={v2}"
    write_lines(tmp_path / "twice.txt", [twice])
    assert selected(["-r", "$2:$1", numbered, "twice.txt"], tmp_path) == [f"{v1}:{k1} {v2}:{k2}"]
    assert sha256_of(path) == before
    assert path.read_text() == "".join(line + "\n" for line in lines)


# F02.T12
@pytest.mark.parametrize("value", ["bogus", "PCRE2", "regex", "Default", ""])
def test_unknown_engine_value_is_rejected(tmp_path, value):
    tok, lines = _engine_file(tmp_path)
    r = tg(["--engine", value, tok, "e.txt"], cwd=tmp_path)
    assert_exit(r, "error")
    assert r.stdout == b""
    assert r.stderr.strip() != b"", r.describe()


def _repeat_tree(tmp_path):
    tok = unique_token()
    make_tree(tmp_path / "w", {
        "a.txt": f"{tok}ooo\n{tok}\nplain\n",
        "sub/b.txt": f"x {tok}o y\n",
        "sub/c.txt": "nothing\n",
    })
    expected = f"w/a.txt:{tok}ooo\nw/sub/b.txt:x {tok}o y\n".encode()
    return tok, expected


# F02.T13
def test_size_values_are_parsed(tmp_path):
    tok, expected = _repeat_tree(tmp_path)
    pattern = f"{tok}o+"
    base = ["--sort", "path", "--engine", "default"]

    for value in ("1G", "1g", "1024M", "1024m", "1048576K", "1048576k", "1073741824", "2G"):
        r = tg([*base, "--regex-size-limit", value, pattern, "w"], cwd=tmp_path)
        assert_exit(r, "match")
        assert r.stdout == expected, value
        r = tg([*base, "--dfa-size-limit", value, pattern, "w"], cwd=tmp_path)
        assert_exit(r, "match")
        assert r.stdout == expected, value

    flags = ("--regex-size-limit", "--dfa-size-limit")
    for flag, other in (flags, flags[::-1]):
        for value in ("abc", "1X", "1.5K", "K", "12MM", "17179869184G", "99999999999999999999"):
            r = tg([*base, flag, value, pattern, "w"], cwd=tmp_path)
            assert_exit(r, "error")
            assert r.stdout == b"", (flag, value)
            assert flag in r.err, r.describe()


# F02.T14
def test_regex_size_limit_of_one_byte(tmp_path):
    tok, expected = _repeat_tree(tmp_path)
    limit = ["--sort", "path", "--regex-size-limit", "1"]
    unbounded = [f"{tok}o+", f"{tok}o*", f"{tok}o{{1,}}"]

    # Live baseline: every pattern compiles and matches without the option.
    for pattern in unbounded:
        assert_exit(tg(["--sort", "path", pattern, "w"], cwd=tmp_path), "match")

    for engine in ([], ["--engine", "auto"], ["--engine", "default"]):
        for pattern in unbounded:
            for extra in ([], ["-i"], ["-w"], ["-x"], ["-v"], ["-o"], ["-c"]):
                r = tg([*limit, *engine, *extra, pattern, "w"], cwd=tmp_path)
                assert_exit(r, "error")
                assert r.stdout == b"", r.describe()
                assert REGEX_ERROR_LABEL in r.err, r.describe()
                assert "size limit" in r.err, r.describe()

    # Patterns compiled by the backtracking engine are not subject to it.
    for engine in (["-P"], ["--engine", "pcre2"]):
        r = tg([*limit, *engine, f"{tok}o+", "w"], cwd=tmp_path)
        assert_exit(r, "match")
        assert r.stdout == expected
    r = tg([*limit, f"{tok}o+(?=o| )", "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert r.stdout == expected
    r = tg([*limit, f"({tok})o+|(zz)\\2", "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert r.stdout == expected


# F02.T15
@pytest.mark.parametrize("value", ["1", "10", "1K", "64k", "3M", "1G", "1g"])
def test_dfa_size_limit_never_changes_results(tmp_path, value):
    tok, expected = _repeat_tree(tmp_path)
    for pattern, kind in ((f"{tok}o+", "match"), (f"{tok}\\w*o\\b", "match"), (f"{tok}q+", "no_match")):
        plain = tg(["--sort", "path", pattern, "w"], cwd=tmp_path)
        assert_exit(plain, kind)
        r = tg(["--sort", "path", "--dfa-size-limit", value, pattern, "w"], cwd=tmp_path)
        assert r.code == plain.code, r.describe()
        assert r.stdout == plain.stdout, r.describe()
    plain = tg(["--sort", "path", f"{tok}o+", "w"], cwd=tmp_path)
    assert plain.stdout == expected


# F02.T04 regression — FP-02.01, FP-02.04, FP-02.06, FP-02.08

def test_alternation_boundaries_unicode_and_negative_lookaround(tmp_path):
    lines = ["cedar", "maple", "cedarwood", "xmaple", "xcedar", "maplewood", "(cedar)"]
    write_lines(tmp_path / "f.txt", lines)
    for args in (["-x"], ["-w"]):
        want = lines[:2] if args == ["-x"] else [*lines[:2], lines[6]]
        assert selected([*args, "cedar|maple", "f.txt"], tmp_path) == want
    for flags in (["-x", "-w"], ["-w", "-x"]):
        assert selected([*flags, r"\(cedar\)", "f.txt"], tmp_path) == ["(cedar)"]
    write_lines(tmp_path / "unicode.txt", ["élan", "ÉLAN", "unrelated"])
    for flags in (["-i"], ["-S"]):
        assert selected([*flags, "élan", "unicode.txt"], tmp_path) == ["élan", "ÉLAN"]
    for eng in ([], ["-P"], ["--engine", "pcre2"]):
        assert selected([*eng, "-i", "CEDAR(?!wood)", "f.txt"], tmp_path) == ["cedar", "xcedar", "(cedar)"]
        assert selected([*eng, "(?<!x)maple", "f.txt"], tmp_path) == ["maple", "maplewood"]
    for patterns in (["-e", "cedar$", "-e", "^maple"], ["-f", "patterns"]):
        (tmp_path / "patterns").write_text("cedar$\n^maple\n")
        assert selected([*patterns, "f.txt"], tmp_path) == [lines[i] for i in (0, 1, 4, 5)]
    for args in (["-e", "ÉLAN"], ["-f", "upper-pattern"]):
        (tmp_path / "upper-pattern").write_text("ÉLAN\n")
        assert selected(["-S", *args, "unicode.txt"], tmp_path) == ["élan", "ÉLAN"]


# F02.T02 regression — FP-02.02, FP-02.05, FP-02.06, FP-02.12
@pytest.mark.parametrize("mode", ["local", "server"])
def test_matching_controls_on_indexed_paths(tmp_path, mode):
    from contextlib import nullcontext
    from F06_helpers import build_index
    from F07_helpers import NoWatchServer, read_stats
    from _helpers import run_trisift
    root = make_tree(tmp_path / "tree", {"a.txt": "EVERGREEN42\nplain\n", "b.txt": "unrelated\n", "c.txt": "evergreen42\n"})
    build_index(root)
    (tmp_path / "patterns").write_text("(?i)evergreen[0-9]+\n")
    with NoWatchServer(root) if mode == "server" else nullcontext():
        r = run_trisift(["--stats", "-f", str(tmp_path / "patterns"), "."], cwd=root)
        assert_exit(r, "match")
        assert read_stats(r)["path"] == mode
        assert sorted(out_lines(r)) == ["./a.txt:EVERGREEN42", "./c.txt:evergreen42"]
        direct = run_trisift(["--stats", "(?i)EVERGREEN[0-9]+", "."], cwd=root)
        assert read_stats(direct)["path"] == mode
        assert sorted(out_lines(direct)) == ["./a.txt:EVERGREEN42", "./c.txt:evergreen42"]
        inv = run_trisift(["--sort", "path", "-v", "EVERGREEN42", "."], cwd=root)
        assert out_lines(inv) == ["./a.txt:plain", "./b.txt:unrelated", "./c.txt:evergreen42"]
        bad = run_trisift(["--regex-size-limit", "1", "EVERGREEN[0-9]+", "."], cwd=root)
        assert_exit(bad, "error")
        assert REGEX_ERROR_LABEL in bad.err and bad.stdout == b""
