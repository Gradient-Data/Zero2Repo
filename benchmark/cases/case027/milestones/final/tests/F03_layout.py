# feature: F03
"""Result output and formatting: layout, filenames, paths, listings, counts."""

from __future__ import annotations

from _helpers import lf_lines
import re

import pytest

from _helpers import make_tree, run_in_pty, unique_token
from F01_helpers import assert_exit, out_lines, tg
from F03_helpers import has_sgr, count_highlighted, strip_sgr


def _layout_tree(tmp_path):
    """Two files under ``w``; byte offsets of matching lines differ from line numbers."""
    tok = unique_token()
    make_tree(tmp_path / "w", {
        "a.txt": f"filler line zero\nfirst {tok} and {tok}\nmiddle\nlast {tok}\n",
        "sub/b.txt": f"padding padding padding\n{tok} here\n",
    })
    return tok


# F03.T01
def test_piped_defaults_and_explicit_layout_options(tmp_path):
    tok = _layout_tree(tmp_path)
    base = ["--sort", "path"]
    a1, a2, b1 = f"first {tok} and {tok}", f"last {tok}", f"{tok} here"
    off_a1 = len("filler line zero\n")
    off_a2 = off_a1 + len(a1) + 1 + len("middle\n")
    off_b1 = len("padding padding padding\n")
    col_a1, col_a2 = len("first ") + 1, len("last ") + 1

    flat = [f"w/a.txt:{a1}", f"w/a.txt:{a2}", f"w/sub/b.txt:{b1}"]
    numbered = [f"w/a.txt:2:{a1}", f"w/a.txt:4:{a2}", f"w/sub/b.txt:2:{b1}"]

    # On a pipe: no line numbers, no heading.
    assert out_lines(tg([*base, tok, "w"], cwd=tmp_path)) == flat
    for flag in ("-n", "--line-number"):
        assert out_lines(tg([*base, flag, tok, "w"], cwd=tmp_path)) == numbered
    assert out_lines(tg([*base, "--column", tok, "w"], cwd=tmp_path)) == [
        f"w/a.txt:2:{col_a1}:{a1}", f"w/a.txt:4:{col_a2}:{a2}", f"w/sub/b.txt:2:1:{b1}"]
    assert out_lines(tg([*base, "--vimgrep", tok, "w/sub"], cwd=tmp_path)) == [f"w/sub/b.txt:2:1:{b1}"]

    # Byte offset and context do not turn line numbers on.
    assert out_lines(tg([*base, "-b", tok, "w"], cwd=tmp_path)) == [
        f"w/a.txt:{off_a1}:{a1}", f"w/a.txt:{off_a2}:{a2}", f"w/sub/b.txt:{off_b1}:{b1}"]
    assert out_lines(tg([*base, "-C", "1", tok, "w/sub"], cwd=tmp_path)) == [
        "w/sub/b.txt-padding padding padding", f"w/sub/b.txt:{b1}"]

    # The no-line-number option turns them off again.
    for flag in ("-N", "--no-line-number"):
        assert out_lines(tg([*base, "-n", flag, tok, "w"], cwd=tmp_path)) == flat

    # Heading layout forced on a pipe, with and without line numbers.
    r = tg([*base, "--heading", tok, "w"], cwd=tmp_path)
    assert r.out == f"w/a.txt\n{a1}\n{a2}\n\nw/sub/b.txt\n{b1}\n"
    r = tg([*base, "--heading", "-n", tok, "w"], cwd=tmp_path)
    assert r.out == f"w/a.txt\n2:{a1}\n4:{a2}\n\nw/sub/b.txt\n2:{b1}\n"
    assert out_lines(tg([*base, "--no-heading", tok, "w"], cwd=tmp_path)) == flat

    # Pretty: heading plus line numbers (colour is checked separately).
    r = tg([*base, "-p", tok, "w"], cwd=tmp_path)
    assert strip_sgr(r.out) == f"w/a.txt\n2:{a1}\n4:{a2}\n\nw/sub/b.txt\n2:{b1}\n"


# F03.T02
def test_terminal_defaults_under_a_pty(tmp_path):
    tok = _layout_tree(tmp_path)
    a1, a2, b1 = f"first {tok} and {tok}", f"last {tok}", f"{tok} here"
    headed = f"w/a.txt\n2:{a1}\n4:{a2}\n\nw/sub/b.txt\n2:{b1}\n"

    for extra in ([], ["--color", "auto"]):
        r = run_in_pty(["--sort", "path", *extra, tok, "w"], cwd=tmp_path)
        assert_exit(r, "match")
        text = r.out
        # Line numbers and per-file heading by default on a terminal.
        assert strip_sgr(text) == headed, r.describe()
        # Colour: every matched span is highlighted.
        assert has_sgr(text)
        assert count_highlighted(text, tok) == 4, r.describe()

    # Explicit options still override on a terminal.
    r = run_in_pty(["--sort", "path", "--no-heading", tok, "w"], cwd=tmp_path)
    assert strip_sgr(r.out) == (
        f"w/a.txt:2:{a1}\nw/a.txt:4:{a2}\nw/sub/b.txt:2:{b1}\n")
    r = run_in_pty(["--sort", "path", "-N", "--no-heading", "--color", "never", tok, "w"], cwd=tmp_path)
    assert r.out == f"w/a.txt:{a1}\nw/a.txt:{a2}\nw/sub/b.txt:{b1}\n"

    # The same search on a pipe has neither (live contrast for the default).
    r = tg(["--sort", "path", tok, "w"], cwd=tmp_path)
    assert r.out == f"w/a.txt:{a1}\nw/a.txt:{a2}\nw/sub/b.txt:{b1}\n"


# F03.T03
def test_color_always_never_and_pretty(tmp_path):
    tok = _layout_tree(tmp_path)
    a1, a2, b1 = f"first {tok} and {tok}", f"last {tok}", f"{tok} here"
    flat = f"w/a.txt:{a1}\nw/a.txt:{a2}\nw/sub/b.txt:{b1}\n"

    never = tg(["--sort", "path", "--color", "never", tok, "w"], cwd=tmp_path)
    assert never.out == flat and not has_sgr(never.out)
    auto = tg(["--sort", "path", "--color", "auto", tok, "w"], cwd=tmp_path)
    assert auto.out == flat and not has_sgr(auto.out)

    always = tg(["--sort", "path", "--color", "always", tok, "w"], cwd=tmp_path)
    assert_exit(always, "match")
    assert strip_sgr(always.out) == flat
    lines = lf_lines(always.out)
    spans = [count_highlighted(line, tok) for line in lines]
    assert spans == [2, 1, 1], always.describe()
    # Surrounding text may be styled as well; each selected span has emphasis.
    part = tok[2:7]
    r = tg(["--color", "always", part, "w/sub/b.txt"], cwd=tmp_path)
    assert strip_sgr(r.out) == tok + " here\n"
    assert count_highlighted(r.out, part) == 1, r.describe()

    for flag in ("-p", "--pretty"):
        r = tg(["--sort", "path", flag, tok, "w"], cwd=tmp_path)
        assert strip_sgr(r.out) == f"w/a.txt\n2:{a1}\n4:{a2}\n\nw/sub/b.txt\n2:{b1}\n"
        assert count_highlighted(r.out, tok) == 4, r.describe()


# F03.T04
def test_filename_prefix_rules(tmp_path):
    tok = unique_token()
    make_tree(tmp_path, {
        "solo/one.txt": f"{tok} one\nplain\n{tok} again\n",
        "two.txt": f"{tok} two\n",
    })
    bare_one = [f"{tok} one", f"{tok} again"]
    pref_one = [f"solo/one.txt:{tok} one", f"solo/one.txt:{tok} again"]

    # Exactly one path argument and it is a file: no prefix.
    assert out_lines(tg([tok, "solo/one.txt"], cwd=tmp_path)) == bare_one
    # One directory argument: prefix on every line, even with a single file inside.
    assert out_lines(tg([tok, "solo"], cwd=tmp_path)) == pref_one
    # Two file arguments: prefix on every line.
    assert out_lines(tg(["--sort", "path", tok, "solo/one.txt", "two.txt"], cwd=tmp_path)) == [
        *pref_one, f"two.txt:{tok} two"]

    for flag in ("-H", "--with-filename"):
        assert out_lines(tg([flag, tok, "solo/one.txt"], cwd=tmp_path)) == pref_one
    for flag in ("-I", "--no-filename"):
        assert out_lines(tg([flag, tok, "solo"], cwd=tmp_path)) == bare_one
    # No-filename wins in both orders.
    assert out_lines(tg(["-H", "-I", tok, "solo"], cwd=tmp_path)) == bare_one
    assert out_lines(tg(["-I", "-H", tok, "solo"], cwd=tmp_path)) == bare_one
    assert out_lines(tg(["-I", "-H", tok, "solo/one.txt"], cwd=tmp_path)) == bare_one


# F03.T05
def test_printed_paths_keep_the_typed_argument(tmp_path):
    tok = unique_token()
    root = make_tree(tmp_path / "w", {"a.txt": f"{tok} a\n", "n1/n2/b.txt": f"{tok} b\n"})
    absolute = str(root)

    def listed(args, cwd=tmp_path):
        return out_lines(tg(["--sort", "path", "-l", tok, *args], cwd=cwd))

    assert listed(["w"]) == ["w/a.txt", "w/n1/n2/b.txt"]
    assert listed(["./w"]) == ["./w/a.txt", "./w/n1/n2/b.txt"]
    assert listed(["w/"]) == ["w/a.txt", "w/n1/n2/b.txt"]
    assert listed(["./w//"]) == ["./w//a.txt", "./w//n1/n2/b.txt"]
    assert listed(["./w/n1/"]) == ["./w/n1/n2/b.txt"]
    assert listed([absolute]) == [f"{absolute}/a.txt", f"{absolute}/n1/n2/b.txt"]
    assert listed(["../w/n1"], cwd=root) == ["../w/n1/n2/b.txt"]
    # A file named explicitly prints exactly as typed.
    assert listed(["./w/n1/n2/b.txt"]) == ["./w/n1/n2/b.txt"]
    assert listed([f"{absolute}/a.txt", "w/n1/../a.txt"]) == [f"{absolute}/a.txt", "w/n1/../a.txt"]
    # No path argument: relative to the current directory, no prefix.
    assert listed([], cwd=root) == ["a.txt", "n1/n2/b.txt"]
    assert listed([], cwd=root / "n1") == ["n2/b.txt"]

    # Match lines use the same paths.
    assert out_lines(tg(["--sort", "path", tok, "./w"], cwd=tmp_path)) == [
        f"./w/a.txt:{tok} a", f"./w/n1/n2/b.txt:{tok} b"]

    # The path-separator option replaces every separator, typed ones included.
    r = tg(["--sort", "path", "--path-separator", "@", tok, "./w"], cwd=tmp_path)
    assert out_lines(r) == [f".@w@a.txt:{tok} a", f".@w@n1@n2@b.txt:{tok} b"]
    r = tg(["--sort", "path", "--path-separator", "@", "-l", tok], cwd=root)
    assert out_lines(r) == ["a.txt", "n1@n2@b.txt"]


def _listing_tree(tmp_path):
    tok = unique_token()
    make_tree(tmp_path / "w", {
        "hit1.txt": f"{tok}\nx\n{tok} {tok}\n{tok}\n",
        "miss.txt": "nothing\nat all\n",
        "sub/hit2.txt": f"a {tok}\n",
        "sub/miss2.txt": "\n",
    })
    return tok


# F03.T06
def test_listing_modes_and_null(tmp_path):
    tok = _listing_tree(tmp_path)
    base = ["--sort", "path"]

    for flag in ("-l", "--files-with-matches"):
        r = tg([*base, flag, tok, "w"], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == ["w/hit1.txt", "w/sub/hit2.txt"]
    r = tg([*base, "-l", unique_token(), "w"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b""

    r = tg([*base, "--files-without-match", tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == ["w/miss.txt", "w/sub/miss2.txt"]
    # Every searched file matches: nothing printed, no-match status.
    r = tg([*base, "--files-without-match", tok, "w/hit1.txt", "w/sub/hit2.txt"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b""
    # Nothing matches anywhere: every file is printed, match status.
    r = tg([*base, "--files-without-match", unique_token(), "w/sub"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == ["w/sub/hit2.txt", "w/sub/miss2.txt"]

    for flag in ("--null", "-0"):
        r = tg([*base, "-l", flag, tok, "w"], cwd=tmp_path)
        assert r.stdout == b"w/hit1.txt\0w/sub/hit2.txt\0"
        r = tg([*base, "--files-without-match", flag, tok, "w"], cwd=tmp_path)
        assert r.stdout == b"w/miss.txt\0w/sub/miss2.txt\0"


# F03.T07
def test_counts(tmp_path):
    tok = _listing_tree(tmp_path)
    base = ["--sort", "path"]

    for flag in ("-c", "--count"):
        r = tg([*base, flag, tok, "w"], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == ["w/hit1.txt:3", "w/sub/hit2.txt:1"]
    r = tg([*base, "--count-matches", tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == ["w/hit1.txt:4", "w/sub/hit2.txt:1"]

    r = tg([*base, "-c", "--include-zero", tok, "w"], cwd=tmp_path)
    assert out_lines(r) == ["w/hit1.txt:3", "w/miss.txt:0", "w/sub/hit2.txt:1", "w/sub/miss2.txt:0"]
    r = tg([*base, "--count-matches", "--include-zero", tok, "w"], cwd=tmp_path)
    assert out_lines(r) == ["w/hit1.txt:4", "w/miss.txt:0", "w/sub/hit2.txt:1", "w/sub/miss2.txt:0"]

    # Without a filename prefix only the number is printed.
    assert out_lines(tg(["-c", tok, "w/hit1.txt"], cwd=tmp_path)) == ["3"]
    assert out_lines(tg(["--count-matches", tok, "w/hit1.txt"], cwd=tmp_path)) == ["4"]
    assert out_lines(tg([*base, "-c", "-I", tok, "w"], cwd=tmp_path)) == ["3", "1"]
    assert out_lines(tg(["-c", "--include-zero", tok, "w/miss.txt"], cwd=tmp_path)) == ["0"]
    assert out_lines(tg(["-c", "-H", tok, "w/hit1.txt"], cwd=tmp_path)) == ["w/hit1.txt:3"]
    # A file with no match is not printed without include-zero.
    r = tg(["-c", tok, "w/miss.txt"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b""


# F03.T08
def test_max_count(tmp_path):
    tok = unique_token()
    make_tree(tmp_path / "w", {
        "a.txt": f"{tok} a1 {tok}\nskip\n{tok} a2\n{tok} a3\n{tok} a4\n",
        "b.txt": f"{tok} b1\n{tok} b2\n{tok} b3 {tok}\n",
        "c.txt": f"only\n{tok} c1\n",
    })
    base = ["--sort", "path"]

    for flag in (["-m", "2"], ["--max-count", "2"], ["--max-count=2"]):
        r = tg([*base, *flag, tok, "w"], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == [
            f"w/a.txt:{tok} a1 {tok}", f"w/a.txt:{tok} a2",
            f"w/b.txt:{tok} b1", f"w/b.txt:{tok} b2",
            f"w/c.txt:{tok} c1",
        ]
    # The limit counts lines, so every match on an admitted line is reported.
    r = tg([*base, "-m", "1", "-o", tok, "w"], cwd=tmp_path)
    assert out_lines(r) == [f"w/a.txt:{tok}", f"w/a.txt:{tok}", f"w/b.txt:{tok}", f"w/c.txt:{tok}"]

    r = tg([*base, "-U", "-m", "1", "-o", tok, "w"], cwd=tmp_path)
    assert out_lines(r) == [f"w/a.txt:{tok}", f"w/a.txt:{tok}", f"w/b.txt:{tok}", f"w/c.txt:{tok}"]

    # Zero: nothing, and the no-match status.
    r = tg([*base, "-m", "0", tok, "w"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b""

    # Multiline: the unit is a block of lines covered by matches.
    p, q = unique_token(), unique_token()
    make_tree(tmp_path, {"ml.txt": f"x\n{p} 1\n{q} 1\ny\n{p} 2\n{q} 2\nz\n"})
    pattern = f"{p} \\d\\n{q} \\d"
    assert out_lines(tg(["-U", pattern, "ml.txt"], cwd=tmp_path)) == [
        f"{p} 1", f"{q} 1", f"{p} 2", f"{q} 2"]
    assert out_lines(tg(["-U", "-m", "1", pattern, "ml.txt"], cwd=tmp_path)) == [f"{p} 1", f"{q} 1"]


# F03.T09
def test_only_matching(tmp_path):
    tok = unique_token()
    make_tree(tmp_path, {"f.txt": f"pre {tok}1 mid {tok}22 post\nnone\n{tok}333 end\n"})
    for flag in ("-o", "--only-matching"):
        r = tg([flag, f"{tok}\\d+", "f.txt"], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == [f"{tok}1", f"{tok}22", f"{tok}333"]
    r = tg(["-o", "-n", f"{tok}\\d+", "f.txt"], cwd=tmp_path)
    assert out_lines(r) == [f"1:{tok}1", f"1:{tok}22", f"3:{tok}333"]


# F03.T22
@pytest.mark.parametrize("flag", ["--sort", "--sortr"])
@pytest.mark.parametrize("key", ["bogus", "name", "size", "Path", "MODIFIED", ""])
def test_unknown_sort_key_is_rejected(tmp_path, flag, key):
    tok = _listing_tree(tmp_path)
    r = tg([flag, key, tok, "w"], cwd=tmp_path)
    assert_exit(r, "error")
    assert r.stdout == b""
    assert r.stderr.strip() != b"", r.describe()


# F03.T23
@pytest.mark.parametrize("value", ["bogus", "yes", "ALWAYS", "ansi"])
def test_unknown_color_value_behaves_as_auto(tmp_path, value):
    tok = _layout_tree(tmp_path)
    never = tg(["--sort", "path", "--color", "never", tok, "w"], cwd=tmp_path)
    r = tg(["--sort", "path", "--color", value, tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert not has_sgr(r.out)
    assert r.stdout == never.stdout and never.stdout != b""

    auto = run_in_pty(["--sort", "path", "--color", "auto", tok, "w"], cwd=tmp_path)
    assert count_highlighted(auto.out, tok) == 4, auto.describe()
    r = run_in_pty(["--sort", "path", "--color", value, tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert strip_sgr(r.out) == strip_sgr(auto.out), r.describe()
    assert count_highlighted(r.out, tok) == 4, r.describe()
    # Live contrast: on the same terminal `never` prints no escapes.
    plain = run_in_pty(["--sort", "path", "--color", "never", tok, "w"], cwd=tmp_path)
    assert not has_sgr(plain.out) and plain.stdout != auto.stdout

