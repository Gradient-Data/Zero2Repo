# feature: F01
"""Regex search over files and directories, answered by a filesystem scan."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from _helpers import PRODUCT_COMMAND, make_tree, unique_token, make_unreadable
from F07_helpers import read_stats
from F01_helpers import (
    ERROR,
    MATCH,
    NO_MATCH,
    REGEX_ERROR_LABEL,
    STATS_SCAN_LABEL,
    USAGE_LABEL,
    assert_exit,
    content_of,
    err_lines,
    out_lines,
    tg,
)

SUBCOMMAND_NAMES = ["index", "serve", "search", "status", "count-files", "help"]


@pytest.mark.parametrize("entry", [[], ["search"]])
def test_directory_search_prints_matches_and_sets_status(tmp_path, entry):
    tok, other, absent = unique_token(), unique_token(), unique_token()
    root = make_tree(tmp_path / "w", {
        "top.txt": f"first {tok} line\nplain line\n",
        "sub/deep/inner.txt": f"{other}\nsecond {tok}\n",
        "sub/none.txt": "nothing to see\n",
    })

    make_tree(tmp_path, {"outside.txt": f"{tok} outside\n"})
    r = tg([*entry, tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert content_of(r, ["w/top.txt", "w/sub/deep/inner.txt"]) == {
        "w/top.txt": [f"first {tok} line"],
        "w/sub/deep/inner.txt": [f"second {tok}"],
    }

    # TEST-FIX(F01): upstream tgrep-cli/src/main.rs:1179 shows both entries
    # use run_search, including no-match searches and omitted paths.
    r = tg([*entry, absent, "w"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b""

    # No path argument: the current directory is searched.
    r = tg([*entry, tok], cwd=root)
    assert_exit(r, "match")
    assert content_of(r, ["top.txt", "sub/deep/inner.txt"]) == {
        "top.txt": [f"first {tok} line"],
        "sub/deep/inner.txt": [f"second {tok}"],
    }
    r = tg([*entry, tok], cwd=root / "sub" / "deep")
    assert_exit(r, "match")
    assert content_of(r, ["inner.txt"]) == {"inner.txt": [f"second {tok}"]}
    r = tg([*entry, absent], cwd=root)
    assert_exit(r, "no_match")
    assert r.stdout == b""


# F01.T02
@pytest.mark.parametrize("file_first", [True, False])
@pytest.mark.parametrize("entry", [[], ["search"]])
def test_named_file_and_directory_arguments_are_all_searched(tmp_path, file_first, entry):
    tok = unique_token()
    make_tree(tmp_path, {
        "tree/a.txt": f"{tok} a\n",
        "tree/n1/b.txt": f"{tok} b\n",
        "tree/n1/n2/c.txt": f"{tok} c\n",
        "lone/file.txt": f"{tok} lone\n",
        "lone/unnamed.txt": f"{tok} must not appear\n",
    })
    args = ["lone/file.txt", "tree"] if file_first else ["tree", "lone/file.txt"]
    # TEST-FIX(F01): upstream tgrep-cli/src/main.rs:1183 shows explicit search
    # forwards all paths to the same run_search as the default entry.
    r = tg([*entry, tok, *args], cwd=tmp_path)
    assert_exit(r, "match")
    paths = ["tree/a.txt", "tree/n1/b.txt", "tree/n1/n2/c.txt", "lone/file.txt", "lone/unnamed.txt"]
    assert content_of(r, paths) == {
        "tree/a.txt": [f"{tok} a"],
        "tree/n1/b.txt": [f"{tok} b"],
        "tree/n1/n2/c.txt": [f"{tok} c"],
        "lone/file.txt": [f"{tok} lone"],
    }
    r = tg([*entry, tok, "lone/file.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == [f"{tok} lone"]
    for targets in (args, ["lone/file.txt"]):
        r = tg([*entry, unique_token(), *targets], cwd=tmp_path)
        assert_exit(r, "no_match")
        assert r.stdout == b""


# F01.T03
@pytest.mark.parametrize("entry", [[], ["search"]])
def test_several_directory_arguments_are_all_covered(tmp_path, entry):
    toks = [unique_token() for _ in range(4)]
    files = {f"d{i}/f{i}.txt": f"{t} in {i}\nfiller\n" for i, t in enumerate(toks)}
    make_tree(tmp_path, files)
    pattern = "|".join(toks)
    dirs = [f"d{i}" for i in range(4)]
    # TEST-FIX(F01): upstream tgrep-cli/src/main.rs:1183 shows both entries
    # retain multiple directory arguments for matching and nonmatching input.
    r = tg([*entry, pattern, *dirs], cwd=tmp_path)
    assert_exit(r, "match")
    assert content_of(r, list(files)) == {
        f"d{i}/f{i}.txt": [f"{t} in {i}"] for i, t in enumerate(toks)
    }
    # A pattern present under one argument only still gives the match status
    # whichever position that argument has.
    for order in (dirs, dirs[::-1]):
        r = tg([*entry, toks[3], *order], cwd=tmp_path)
        assert_exit(r, "match")
        assert content_of(r, list(files)) == {"d3/f3.txt": [f"{toks[3]} in 3"]}
    r = tg([*entry, unique_token(), *dirs], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b""


# F01.T04
def test_explicit_pattern_makes_every_positional_a_path(tmp_path):
    name, tok = unique_token("dir"), unique_token()
    make_tree(tmp_path, {
        f"{name}/in.txt": f"{tok} inside\nother\n",
        "decoy.txt": f"{name} decoy mentions the directory name\n{tok} outside\n",
        "pats.txt": f"{tok}\n",
    })
    inside = {f"{name}/in.txt": [f"{tok} inside"]}
    make_tree(tmp_path, {"second/another.txt": f"{tok} second\n"})
    inside["second/another.txt"] = [f"{tok} second"]
    paths = [f"{name}/in.txt", "second/another.txt", "decoy.txt", "pats.txt"]

    # With an explicit pattern the first positional is a directory to search.
    r = tg(["-e", tok, name, "second"], cwd=tmp_path)
    assert_exit(r, "match")
    assert content_of(r, paths) == inside

    # Same with a pattern file.
    r = tg(["-f", "pats.txt", name, "second"], cwd=tmp_path)
    assert_exit(r, "match")
    assert content_of(r, paths) == inside

    # Without either, the same first positional is the pattern.
    r = tg([name, "decoy.txt", name], cwd=tmp_path)
    assert_exit(r, "match")
    assert content_of(r, paths) == {
        "decoy.txt": [f"{name} decoy mentions the directory name"],
    }


# F01.T04b — FP-01.01/01.03, FP-02.06, FP-07.02
@pytest.mark.parametrize("entry", [[], ["search"]], ids=["top", "search"])
@pytest.mark.parametrize("mode", ["scan", "local", "server"])
@pytest.mark.parametrize("source", ["-e", "--regexp", "-f", "--file", "attached-regexp", "equals-regexp", "attached-file", "equals-file", "repeated", "mixed", "empty-file", "empty-regexp"])
def test_search_subcommand_accepts_explicit_pattern_without_positional_pattern(tmp_path, entry, mode, source):
    from contextlib import nullcontext
    from F06_helpers import build_index
    from F07_helpers import NoWatchServer

    tok, other = unique_token(), unique_token()
    root = make_tree(tmp_path / "w", {
        "top.txt": f"{tok} top\nnot selected\n",
        "sub/nested.txt": f"{tok} nested\n{other} extra\n",
    })
    pattern_file = tmp_path / "patterns.txt"
    pattern_file.write_text("" if source == "empty-file" else tok + "\n", encoding="utf-8")
    patterns = {
        "-e": ["-e", tok], "--regexp": ["--regexp", tok],
        "-f": ["-f", str(pattern_file)], "--file": ["--file", str(pattern_file)],
        "attached-regexp": ["-e" + tok], "equals-regexp": ["--regexp=" + tok],
        "attached-file": ["-f" + str(pattern_file)], "equals-file": ["--file=" + str(pattern_file)],
        "repeated": ["-e", tok, "--regexp", other],
        "mixed": ["--file", str(pattern_file), "-e", other],
        "empty-file": ["-f", str(pattern_file)], "empty-regexp": ["--regexp", ""],
    }[source]
    selected = {"top.txt": [f"{tok} top"], "sub/nested.txt": [f"{tok} nested"]}
    if source in ("repeated", "mixed", "empty-file", "empty-regexp"):
        selected["sub/nested.txt"].append(f"{other} extra")
    if source in ("empty-file", "empty-regexp"):
        selected["top.txt"].append("not selected")
    if mode != "scan":
        build_index(root)
    with NoWatchServer(root) if mode == "server" else nullcontext():
        for targets, prefix in (([], ""), (["."], "./"), (["--", "top.txt", "sub"], "")):
            r = tg([*entry, *(["--no-index"] if mode == "scan" else []),
                    "--stats", *patterns, *targets], cwd=root)
            assert_exit(r, "match")
            assert content_of(r, [prefix + p for p in selected]) == {
                prefix + p: rows for p, rows in selected.items()
            }, r.describe()
            if not targets or targets == ["."]:
                assert read_stats(r)["path"] == mode, r.describe()
        r = tg([*entry, *patterns, "top.txt"], cwd=root)
        assert_exit(r, "match")
        assert out_lines(r) == selected["top.txt"], r.describe()


# F01.T05
def test_double_dash_makes_dash_and_subcommand_patterns_text(tmp_path):
    tok = unique_token()
    lines = [f"{name} {tok} {i}" for i, name in enumerate(SUBCOMMAND_NAMES)]
    dash = f"-{tok}x"
    make_tree(tmp_path, {"d/words.txt": "\n".join(lines) + f"\nlead {dash} tail\nunrelated\n"})

    r = tg(["--", dash, "d"], cwd=tmp_path)
    assert_exit(r, "match")
    assert content_of(r, ["d/words.txt"]) == {"d/words.txt": [f"lead {dash} tail"]}

    for name, line in zip(SUBCOMMAND_NAMES, lines):
        r = tg(["--", name, "d"], cwd=tmp_path)
        assert_exit(r, "match")
        assert content_of(r, ["d/words.txt"]) == {"d/words.txt": [line]}, name


# F01.T06
@pytest.mark.parametrize("wrap", [
    "\"{}\"",
    "'{}'",
    "  {}  ",
    "  \"  ' {} '  \"  ",
    "'\"'{}'\"'",
    "\t\" {} \"\t",
])
def test_quoted_path_arguments_are_unwrapped(tmp_path, wrap):
    tok = unique_token()
    make_tree(tmp_path, {
        "sp ace/named.txt": f"{tok} named\n",
        "plain/in.txt": f"{tok} walked\n",
    })
    # The wrapped spelling itself names nothing on disk.
    for target in ("sp ace/named.txt", "plain"):
        typed = wrap.format(target)
        assert typed != target and not os.path.exists(tmp_path / typed)

    r = tg([tok, wrap.format("sp ace/named.txt")], cwd=tmp_path)
    assert_exit(r, "match")
    lines = out_lines(r)
    assert len(lines) == 1 and lines[0].endswith(f"{tok} named"), r.describe()

    both = tg(["-I", tok, wrap.format("plain"), wrap.format("sp ace/named.txt")], cwd=tmp_path)
    assert_exit(both, "match")
    assert sorted(out_lines(both)) == sorted([f"{tok} named", f"{tok} walked"])

    r = tg([tok, wrap.format("plain")], cwd=tmp_path)
    assert_exit(r, "match")
    lines = out_lines(r)
    assert len(lines) == 1 and lines[0].endswith(f"{tok} walked"), r.describe()


# F01.T07
def test_quiet_mode_statuses(tmp_path):
    tok, absent, missing = unique_token(), unique_token(), unique_token("gone")
    make_tree(tmp_path, {"d/a.txt": f"{tok}\n", "d/b.txt": "plain\n"})

    # Live baseline: the same search without quiet mode prints the line.
    r = tg([tok, "d"], cwd=tmp_path)
    assert out_lines(r) == [f"d/a.txt:{tok}"]

    for flag in ("-q", "--quiet"):
        r = tg([flag, tok, "d"], cwd=tmp_path)
        assert r.stdout == b""
        assert_exit(r, "match")

        # A match wins over an error reported for another path argument.
        for order in (["d", missing], [missing, "d"]):
            r = tg([flag, tok, *order], cwd=tmp_path)
            assert r.stdout == b""
            assert_exit(r, "match")

        r = tg([flag, absent, "d"], cwd=tmp_path)
        assert r.stdout == b""
        assert_exit(r, "no_match")

        r = tg([flag, absent, "d", missing], cwd=tmp_path)
        assert r.stdout == b""
        assert_exit(r, "error")


# F01.T08
def test_pcre2_version_names_engine_and_does_not_search(tmp_path):
    tok = unique_token()
    make_tree(tmp_path, {"d/a.txt": f"{tok}\n"})
    for args in (["--pcre2-version"], ["--pcre2-version", tok, "d"]):
        r = tg(args, cwd=tmp_path)
        assert r.code == 0, r.describe()
        lines = out_lines(r)
        assert len(lines) == 1, r.describe()
        assert "fancy-regex" in lines[0]
        assert "PCRE2" in lines[0]
        assert re.search(r"\bnot linked\b", lines[0]), r.describe()
        assert tok not in r.out


def _crlf_tree(tmp_path, tok):
    return make_tree(tmp_path / "w", {
        "one.txt": f"aa {tok}\r\nbb {tok} tail\r\ncc {tok}\n",
        "two/nested.txt": f"zz {tok}\r\n{tok} mid line\r\n",
    })


CRLF_EXPECTED = lambda tok: (
    f"w/one.txt:aa {tok}\nw/one.txt:cc {tok}\nw/two/nested.txt:zz {tok}\n"
).encode()


# F01.T09
@pytest.mark.parametrize("extra", [
    ["--mmap"],
    ["--no-mmap"],
    ["--crlf"],
    ["--no-crlf"],
    ["--no-config"],
    ["--colors", "match:fg:blue"],
    ["--colors", "path:style:bold", "--colors", "line:fg:green"],
    ["--threads", "1"],
    ["--threads", "3"],
    ["-j", "2"],
])
def test_compatibility_options_leave_results_unchanged(tmp_path, extra):
    tok = unique_token()
    _crlf_tree(tmp_path, tok)
    plain = tg(["--sort", "path", f"{tok}$", "w"], cwd=tmp_path)
    assert_exit(plain, "match")
    # The carriage return is stripped before matching and before printing.
    assert plain.stdout == CRLF_EXPECTED(tok)

    r = tg(["--sort", "path", *extra, f"{tok}$", "w"], cwd=tmp_path)
    assert r.code == plain.code, r.describe()
    assert r.stdout == plain.stdout, r.describe()

    # ... and a no-match search stays a no-match search.
    absent = unique_token()
    r = tg(["--sort", "path", *extra, f"{absent}$", "w"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b""


# F01.T10
def test_carriage_return_stripped_and_debug_trace_enable_stats(tmp_path):
    tok = unique_token()
    _crlf_tree(tmp_path, tok)
    args = ["--sort", "path", f"{tok}$", "w"]

    plain = tg(args, cwd=tmp_path)
    assert_exit(plain, "match")
    assert plain.stdout == CRLF_EXPECTED(tok)
    assert b"\r" not in plain.stdout
    assert not any(STATS_SCAN_LABEL in line for line in err_lines(plain)), plain.describe()

    for flag in ("--debug", "--trace"):
        r = tg([flag, *args], cwd=tmp_path)
        assert_exit(r, "match")
        assert r.stdout == plain.stdout
        stats = read_stats(r)
        assert stats["path"] == "scan"
        assert stats["matches"] == stats["matched_lines"] == 3


# F01.T11
def test_missing_path_is_reported_and_others_still_searched(tmp_path):
    tok, missing = unique_token(), unique_token("gone")
    missing2 = unique_token("gone")
    make_tree(tmp_path, {"d1/a.txt": f"{tok} one\n", "d2/b.txt": f"{tok} two\n"})
    expected = {"d1/a.txt": [f"{tok} one"], "d2/b.txt": [f"{tok} two"]}

    for order in (["d1", missing, "d2"], [missing, "d1", "d2"], ["d1", "d2", missing]):
        r = tg([tok, *order, missing2], cwd=tmp_path)
        assert any(line.startswith(f"trisift: {missing2}: ") for line in err_lines(r)), r.describe()
        assert content_of(r, list(expected)) == expected
        assert_exit(r, "error")
        assert any(missing in line for line in err_lines(r)), r.describe()

        r = tg(["--no-messages", tok, *order], cwd=tmp_path)
        assert content_of(r, list(expected)) == expected
        assert_exit(r, "error")
        assert missing not in r.err, r.describe()

    # Nothing matches and a path is missing: still the error status.
    r = tg([unique_token(), "d1", missing], cwd=tmp_path)
    assert r.stdout == b""
    assert_exit(r, "error")
    assert any(missing in line for line in err_lines(r)), r.describe()


# F01.T12
@pytest.mark.parametrize("entry", [[], ["search"]])
def test_bare_invocation_prints_usage_on_stderr(tmp_path, entry):
    tok = unique_token()
    make_tree(tmp_path, {"a.txt": f"{tok}\n"})
    r = tg(entry, cwd=tmp_path)
    assert_exit(r, "error")
    assert r.stdout == b""
    assert USAGE_LABEL in r.err, r.describe()


# F01.T13
@pytest.mark.parametrize("flag", ["--search-zip", "-z"])
def test_search_zip_is_refused(tmp_path, flag):
    tok = unique_token()
    make_tree(tmp_path, {"d/a.txt": f"{tok}\n"})
    # Live baseline: without the option the file matches.
    r = tg([tok, "d"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == [f"d/a.txt:{tok}"]

    r = tg([flag, tok, "d"], cwd=tmp_path)
    assert_exit(r, "error")
    assert r.stdout == b""
    assert "--search-zip" in r.err, r.describe()


# F01.T14
@pytest.mark.parametrize("pattern", ["(", "a[", "x{2,1}"])
@pytest.mark.parametrize("engine", [[], ["-P"], ["--engine", "pcre2"]])
def test_uncompilable_pattern_is_an_error(tmp_path, pattern, engine):
    tok = unique_token()
    make_tree(tmp_path, {"d/a.txt": f"{tok}\n"})
    # A pattern that compiles and finds nothing is the no-match status ...
    r = tg([unique_token(), "d"], cwd=tmp_path)
    assert r.code == NO_MATCH, r.describe()
    # ... while one that cannot be compiled is the error status.
    r = tg([*engine, pattern, "d"], cwd=tmp_path)
    assert r.code == ERROR and r.code not in (MATCH, NO_MATCH), r.describe()
    assert REGEX_ERROR_LABEL in r.err, r.describe()


# F01.T01 regression — FP-01.01, FP-01.08, FP-02.08

def test_full_content_regex_and_terminal_carriage_return(tmp_path):
    tok = unique_token()
    make_tree(tmp_path, {"data.txt": "padding\n" * 900 + f"{tok}42\n{tok}777\r"})
    r = tg([f"^{tok}([0-9]{{2}}|7+)$", "data.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    assert r.stdout == f"{tok}42\n{tok}777\n".encode()


# F01.T07 regression — FP-01.06

def test_quiet_match_does_not_read_later_unreadable_file(tmp_path):
    tok = unique_token()
    make_tree(tmp_path, {"first.txt": tok + "\n", "later.txt": tok + "\n"})
    with make_unreadable(tmp_path / "later.txt"):
        baseline = tg([tok, "first.txt", "later.txt"], cwd=tmp_path)
        assert_exit(baseline, "error")
        assert f"first.txt:{tok}" in baseline.out
        quiet = tg(["-q", tok, "first.txt", "later.txt"], cwd=tmp_path)
        assert_exit(quiet, "match")
        assert quiet.stdout == b""

    # Final status alone cannot establish early termination. Hold the later
    # regular file unreadable by an open lease, with a non-quiet live control.
    from F00_observations import ReadGate
    from _helpers import BackgroundProcess
    with ReadGate(tmp_path / "later.txt") as gate:
        with BackgroundProcess([tok, "first.txt", "later.txt"], cwd=tmp_path) as proc:
            try:
                gate.wait_blocked(proc)
            finally:
                gate.release()
            baseline = proc.wait(timeout=30)
        assert_exit(baseline, "match")
        assert out_lines(baseline) == [f"first.txt:{tok}", f"later.txt:{tok}"]
    with ReadGate(tmp_path / "later.txt") as gate:
        with BackgroundProcess(["-q", tok, "first.txt", "later.txt"], cwd=tmp_path) as proc:
            try:
                quiet = proc.wait(timeout=10)
                assert_exit(quiet, "match")
                assert quiet.stdout == b""
            finally:
                gate.release()
