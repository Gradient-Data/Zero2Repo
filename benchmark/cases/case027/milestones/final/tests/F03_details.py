# feature: F03
"""Result output and formatting: context, positions, long lines, JSON, sorting, buffering."""

from __future__ import annotations

from _helpers import lf_lines
import os
import time
from contextlib import nullcontext

import pytest

from _helpers import make_text_file, make_tree, unique_token
from F01_helpers import assert_exit, out_lines, tg
from F06_helpers import build_index
from F07_helpers import NoWatchServer, read_stats
from F03_helpers import (
    CONTEXT_SEP,
    GROUP_SEP,
    MATCH_SEP,
    OMITTED_CONTEXT,
    OMITTED_MATCH,
    PREVIEW_MARKER,
    parse_json_stream,
    read_first_line_live,
    without_timing,
)

# Matching line numbers (1-based) of the context fixture, 16 lines in all.
CTX_MATCHES = (2, 5, 9, 10, 15)
CTX_TOTAL = 16


def _context_file(tmp_path, name="ctx.txt"):
    tok = unique_token()
    lines = [f"{tok} m{n}" if n in CTX_MATCHES else f"plain {n}" for n in range(1, CTX_TOTAL + 1)]
    make_tree(tmp_path, {name: "".join(line + "\n" for line in lines)})
    return tok, lines


def _numbered(lines, groups, sep=MATCH_SEP, ctx=CONTEXT_SEP, group_sep=GROUP_SEP, prefix=""):
    """Render ``groups`` (lists of 1-based line numbers) as numbered output lines."""
    out = []
    for i, group in enumerate(groups):
        if i and group_sep is not None:
            out.append(group_sep)
        for n in group:
            mark = sep if n in CTX_MATCHES else ctx
            out.append(f"{prefix}{n}{mark}{lines[n - 1]}")
    return out


def _span(a, b):
    return list(range(a, b + 1))


# F03.T10
def test_context_lines_and_group_separators(tmp_path):
    tok, lines = _context_file(tmp_path)

    def run(*flags):
        r = tg(["-n", *flags, tok, "ctx.txt"], cwd=tmp_path)
        assert_exit(r, "match")
        return out_lines(r)

    # No context requested: no separator between non-adjacent matches.
    assert run() == [f"{n}:{lines[n - 1]}" for n in CTX_MATCHES]

    # Windows of lines 2 and 5 touch (3 then 4): one block, no separator.
    c1 = [_span(1, 6), _span(8, 11), _span(14, 16)]
    for flags in (["-C", "1"], ["--context", "1"], ["-C1"], ["-A", "1", "-B", "1"]):
        assert run(*flags) == _numbered(lines, c1), flags
    for flags in (["-A", "1"], ["--after-context", "1"]):
        assert run(*flags) == _numbered(lines, [[2, 3], [5, 6], [9, 10, 11], [15, 16]])
    for flags in (["-B", "1"], ["--before-context", "1"]):
        assert run(*flags) == _numbered(lines, [[1, 2], [4, 5], [8, 9, 10], [14, 15]])
    # Overlapping windows: every line once, in order, one block.
    assert run("-C", "2") == _numbered(lines, [_span(1, CTX_TOTAL)])
    assert run("-B", "2", "-A", "1") == _numbered(lines, [_span(1, 11), _span(13, 16)])

    # Between files in flat output.
    other = unique_token()
    make_tree(tmp_path, {"d/a.txt": f"x\n{other} one\ny\n", "d/b.txt": f"{other} two\nz\n"})
    r = tg(["--sort", "path", "-C", "1", other, "d"], cwd=tmp_path)
    assert out_lines(r) == [
        "d/a.txt-x", f"d/a.txt:{other} one", "d/a.txt-y",
        GROUP_SEP,
        f"d/b.txt:{other} two", "d/b.txt-z",
    ]
    # ... and none without context.
    r = tg(["--sort", "path", other, "d"], cwd=tmp_path)
    assert out_lines(r) == [f"d/a.txt:{other} one", f"d/b.txt:{other} two"]


# F03.T11
def test_custom_separators(tmp_path):
    tok, lines = _context_file(tmp_path)
    groups = [_span(1, 6), _span(8, 11), _span(14, 16)]

    r = tg(["-n", "-C", "1", "--context-separator", "@@@", tok, "ctx.txt"], cwd=tmp_path)
    assert out_lines(r) == _numbered(lines, groups, group_sep="@@@")
    r = tg(["-n", "-C", "1", "--no-context-separator", tok, "ctx.txt"], cwd=tmp_path)
    assert out_lines(r) == _numbered(lines, groups, group_sep=None)

    r = tg(["-n", "-C", "1", "--field-match-separator", "=>", tok, "ctx.txt"], cwd=tmp_path)
    assert out_lines(r) == _numbered(lines, groups, sep="=>")
    r = tg(["-n", "-C", "1", "--field-context-separator", "~", tok, "ctx.txt"], cwd=tmp_path)
    assert out_lines(r) == _numbered(lines, groups, ctx="~")
    # Both at once, with a path field and a column field in front.
    r = tg(["-H", "--column", "-b", "-C", "1", "--field-match-separator", "=", "--field-context-separator", "~",
            "--context-separator", "", tok, "ctx.txt"], cwd=tmp_path)
    expected = []
    for i, group in enumerate(groups):
        if i:
            expected.append("")
        for n in group:
            if n in CTX_MATCHES:
                offset = sum(len((line + "\n").encode()) for line in lines[:n-1])
                expected.append(f"ctx.txt={n}=1={offset}={lines[n - 1]}")
            else:
                offset = sum(len((line + "\n").encode()) for line in lines[:n-1])
                expected.append(f"ctx.txt~{n}~{offset}~{lines[n - 1]}")
    assert out_lines(r) == expected


# F03.T12
def test_column_and_byte_offset(tmp_path):
    tok = unique_token()
    first = f"éé日 {tok} then {tok}"
    lines = ["plain zero", first, "plain two", f"{tok} at start"]
    data = "".join(line + "\n" for line in lines).encode("utf-8")
    make_tree(tmp_path, {"p.txt": data})
    col = len("éé日 ".encode("utf-8")) + 1          # byte column, not character column
    assert col != len("éé日 ") + 1
    off = [0]
    for line in lines[:-1]:
        off.append(off[-1] + len(line.encode("utf-8")) + 1)

    r = tg(["--column", tok, "p.txt"], cwd=tmp_path)
    assert out_lines(r) == [f"2:{col}:{first}", f"4:1:{lines[3]}"]
    # Context lines get no column.
    r = tg(["--column", "-C", "1", tok, "p.txt"], cwd=tmp_path)
    assert out_lines(r) == [
        "1-plain zero", f"2:{col}:{first}", "3-plain two", f"4:1:{lines[3]}"]
    # Between column and no-column the later one wins.
    r = tg(["--column", "--no-column", tok, "p.txt"], cwd=tmp_path)
    assert out_lines(r) == [first, lines[3]]
    r = tg(["--no-column", "--column", tok, "p.txt"], cwd=tmp_path)
    assert out_lines(r) == [f"2:{col}:{first}", f"4:1:{lines[3]}"]
    r = tg(["-n", "--column", "--no-column", tok, "p.txt"], cwd=tmp_path)
    assert out_lines(r) == [f"2:{first}", f"4:{lines[3]}"]

    for flag in ("-b", "--byte-offset"):
        r = tg([flag, tok, "p.txt"], cwd=tmp_path)
        assert out_lines(r) == [f"{off[1]}:{first}", f"{off[3]}:{lines[3]}"]
    r = tg(["-b", "-C", "1", tok, "p.txt"], cwd=tmp_path)
    assert out_lines(r) == [
        f"{off[0]}-plain zero", f"{off[1]}:{first}", f"{off[2]}-plain two", f"{off[3]}:{lines[3]}"]
    # Under only-matching: the offset of each match itself.
    second = off[1] + len(f"éé日 {tok} then ".encode("utf-8"))
    r = tg(["-b", "-o", tok, "p.txt"], cwd=tmp_path)
    assert out_lines(r) == [f"{off[1] + col - 1}:{tok}", f"{second}:{tok}", f"{off[3]}:{tok}"]


# F03.T13
def test_max_columns_placeholders_and_preview(tmp_path):
    tok = unique_token(length=6)          # 8 bytes
    assert len(tok) == 8
    n = 12
    fit, over = tok + "a" * (n - 9), tok + "b" * (n - 8)      # n-1 and n bytes of text
    ctx_fit, ctx_over = "c" * (n - 1), "d" * n

    # LF terminator counts one byte.
    make_tree(tmp_path, {"lf.txt": f"{fit}\n{ctx_over}\n{over}\n{ctx_fit}\n"})
    for flag in (["-M", str(n)], ["--max-columns", str(n)]):
        r = tg([*flag, "-C", "1", tok, "lf.txt"], cwd=tmp_path)
        assert_exit(r, "match")
        assert out_lines(r) == [fit, OMITTED_CONTEXT, OMITTED_MATCH, ctx_fit]
    assert OMITTED_MATCH != OMITTED_CONTEXT
    # One more byte admits them all.
    r = tg(["-M", str(n + 1), "-C", "1", tok, "lf.txt"], cwd=tmp_path)
    assert out_lines(r) == [fit, ctx_over, over, ctx_fit]

    make_tree(tmp_path, {"wide.txt": f"{tok}ééé\n"})
    assert out_lines(tg(["-M", str(n), tok, "wide.txt"], cwd=tmp_path)) == [OMITTED_MATCH]

    # CRLF counts two bytes; an unterminated final line counts none.
    crlf_fit, crlf_over = tok + "e" * (n - 10), tok + "f" * (n - 9)   # n-2, n-1 bytes of text
    last_fit = tok + "g" * (n - 8)                                    # n bytes, no terminator
    make_tree(tmp_path, {"crlf.txt": f"{crlf_fit}\r\n{crlf_over}\r\n{last_fit}".encode()})
    r = tg(["-M", str(n), tok, "crlf.txt"], cwd=tmp_path)
    assert out_lines(r) == [crlf_fit, OMITTED_MATCH, last_fit]
    make_tree(tmp_path, {"last.txt": f"{tok}\n{tok}{'h' * (n - 7)}".encode()})   # n+1 bytes, no terminator
    r = tg(["-M", str(n), tok, "last.txt"], cwd=tmp_path)
    assert out_lines(r) == [tok, OMITTED_MATCH]

    # Preview: the first part of the line, then the omission marker.
    long_match, long_ctx = tok + "".join(str(i % 10) for i in range(40)), "".join(
        chr(ord("a") + i % 26) for i in range(48))
    make_tree(tmp_path, {"pv.txt": f"{fit}\n{long_ctx}\n{long_match}\n{ctx_fit}\n"})
    r = tg(["-M", str(n), "--max-columns-preview", "-C", "1", tok, "pv.txt"], cwd=tmp_path)
    got = out_lines(r)
    assert len(got) == 4 and got[0] == fit and got[3] == ctx_fit, r.describe()
    for shown, full in ((got[1], long_ctx), (got[2], long_match)):
        assert shown.endswith(PREVIEW_MARKER), r.describe()
        kept = shown[: -len(PREVIEW_MARKER)]
        assert kept and full.startswith(kept) and len(kept) < len(full), r.describe()


# F03.T14
def test_trim(tmp_path):
    tok = unique_token()
    make_tree(tmp_path, {"t.txt": f"\u2003 \t {tok} inner  gap \t\u00a0\n{tok}\n\u2003ctx line\u00a0\n"})
    r = tg([tok, "t.txt"], cwd=tmp_path)
    assert out_lines(r) == [f"\u2003 \t {tok} inner  gap \t\u00a0", tok]
    r = tg(["--trim", tok, "t.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == [f"{tok} inner  gap", tok]
    r = tg(["--trim", "-n", "-A", "1", tok, "t.txt"], cwd=tmp_path)
    assert out_lines(r) == [f"1:{tok} inner  gap", f"2:{tok}", "3-ctx line"]


# F03.T15
def test_passthru(tmp_path):
    tok = unique_token()
    text = ["alpha", f"has {tok}", "omega", ""]
    body = "".join(line + "\n" for line in text)
    make_tree(tmp_path, {
        "text.txt": body,
        "blob": b"binary\0payload without the word\nsecond\n",
        "walk/text.txt": body,
        "walk/blob": b"binary\0payload without the word\nsecond\n",
    })

    r = tg(["--passthru", tok, "text.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == text
    r = tg(["--passthru", unique_token(), "text.txt"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert out_lines(r) == text

    # A non-matching binary file that is opened prints nothing.
    r = tg(["--passthru", "-I", tok, "text.txt", "blob"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == text
    r = tg(["--passthru", "-I", tok, "blob"], cwd=tmp_path)
    assert_exit(r, "no_match")
    assert r.stdout == b""
    r = tg(["--passthru", "-I", "--binary", tok, "walk"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == text

    # A limit of zero prints nothing at all.
    for args in (["text.txt"], ["text.txt", "blob"], ["walk"]):
        r = tg(["--passthru", "-m", "0", tok, *args], cwd=tmp_path)
        assert_exit(r, "no_match")
        assert r.stdout == b""


# F03.T16
def test_stop_on_nonmatch(tmp_path):
    tok = unique_token()
    make_tree(tmp_path, {
        "a.txt": f"{tok} 1\n{tok} 2\nbreak\n{tok} 3\n",
        "b.txt": f"lead\nlead\n{tok} 1\nbreak\n{tok} 2\n{tok} 3\n",
    })
    assert out_lines(tg([tok, "a.txt"], cwd=tmp_path)) == [f"{tok} 1", f"{tok} 2", f"{tok} 3"]
    assert out_lines(tg(["--stop-on-nonmatch", tok, "a.txt"], cwd=tmp_path)) == [f"{tok} 1", f"{tok} 2"]
    assert out_lines(tg([tok, "b.txt"], cwd=tmp_path)) == [f"{tok} 1", f"{tok} 2", f"{tok} 3"]
    r = tg(["--stop-on-nonmatch", tok, "b.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == [f"{tok} 1"]


# F03.T17
def test_vimgrep_rows(tmp_path):
    tok = unique_token()
    first = f"é {tok} mid {tok}"
    make_tree(tmp_path, {"w/v.txt": f"none\n{first}\n{tok}\n", "w/z.txt": f"zz {tok}\n"})
    c1 = len("é ".encode()) + 1
    c2 = len(f"é {tok} mid ".encode()) + 1

    r = tg(["--sort", "path", "--vimgrep", tok, "w"], cwd=tmp_path)
    assert_exit(r, "match")
    assert out_lines(r) == [
        f"w/v.txt:2:{c1}:{first}", f"w/v.txt:2:{c2}:{first}", f"w/v.txt:3:1:{tok}", f"w/z.txt:1:4:zz {tok}"]
    # The path is shown even for one named file.
    r = tg(["--vimgrep", tok, "w/z.txt"], cwd=tmp_path)
    assert out_lines(r) == [f"w/z.txt:1:4:zz {tok}"]

    # Multiline: one row per match, on its starting line.
    p, q = unique_token(), unique_token()
    make_tree(tmp_path, {"ml.txt": f"x\nab {p}\n{q} 1\ny\n{p}\n{q} 2\n"})
    r = tg(["--vimgrep", "-U", f"{p}\\n{q}", "ml.txt"], cwd=tmp_path)
    assert out_lines(r) == [f"ml.txt:2:4:ab {p}", f"ml.txt:5:1:{p}"]


def _json_tree(tmp_path):
    tok = unique_token()
    files = {
        "one/a.txt": f"lead line\nxx {tok} yy {tok}\ntail\n",
        "one/b.txt": "no hit in here\n",
        "two/c.txt": f"{tok}\nmid\né {tok}\n{tok} {tok} {tok}\n",
        "two/deep/d.txt": "still nothing\nat all\n",
        "three/e.txt": f"p\nq\n{tok} end\n",
    }
    make_tree(tmp_path, files)
    return tok, files


def _by_kind(messages, kind):
    return [m["data"] for m in messages if m["type"] == kind]


# F03.T18
def test_json_stream(tmp_path):
    tok, files = _json_tree(tmp_path)
    r = tg(["--sort", "path", "--json", "-C", "1", tok, "one", "two", "three/e.txt"], cwd=tmp_path)
    assert_exit(r, "match")
    msgs = parse_json_stream(r)

    # Shape: begin, lines, end per file with output; one summary, last.
    assert [m["type"] for m in msgs].count("summary") == 1 and msgs[-1]["type"] == "summary"
    order = [(m["type"], m["data"].get("path", {}).get("text")) for m in msgs[:-1]]
    per_file = {}
    for kind, path in order:
        per_file.setdefault(path, []).append(kind)
    assert list(per_file) == ["one/a.txt", "two/c.txt", "three/e.txt"]
    assert per_file["one/a.txt"] == ["begin", "context", "match", "context", "end"]
    assert per_file["two/c.txt"] == ["begin", "match", "context", "match", "match", "end"]
    assert per_file["three/e.txt"] == ["begin", "context", "match", "end"]
    # Messages of one file are contiguous.
    assert [p for i, (_, p) in enumerate(order) if i == 0 or order[i - 1][1] != p] == list(per_file)

    # Match messages: text, line number, byte offset, one submatch per match.
    expected_counts = {}
    for data in _by_kind(msgs, "match"):
        path = data["path"]["text"]
        raw = files[path].encode("utf-8")
        text = data["lines"]["text"]
        file_lines = lf_lines(files[path], keepends=True)
        assert file_lines[data["line_number"] - 1] == text
        offset = sum(len(l.encode("utf-8")) for l in file_lines[: data["line_number"] - 1])
        assert data["absolute_offset"] == offset
        assert raw[offset: offset + len(text.encode("utf-8"))] == text.encode("utf-8")
        subs = data["submatches"]
        assert len(subs) == text.count(tok) >= 1
        encoded = text.encode("utf-8")
        starts = []
        for sub in subs:
            assert encoded[sub["start"]: sub["end"]].decode("utf-8") == tok == sub["match"]["text"]
            starts.append(sub["start"])
        assert starts == sorted(set(starts))
        lines_n, matches_n = expected_counts.get(path, (0, 0))
        expected_counts[path] = (lines_n + 1, matches_n + len(subs))
    assert expected_counts == {"one/a.txt": (1, 2), "two/c.txt": (3, 5), "three/e.txt": (1, 1)}
    offsets = {(d["path"]["text"], d["line_number"]): d["absolute_offset"] for d in _by_kind(msgs, "match")}
    assert offsets[("one/a.txt", 2)] == len("lead line\n") and offsets[("two/c.txt", 1)] == 0

    assert [(d["path"]["text"], d["line_number"]) for d in _by_kind(msgs, "context")] == [
        ("one/a.txt", 1), ("one/a.txt", 3), ("two/c.txt", 2), ("three/e.txt", 2)]
    for data in _by_kind(msgs, "context"):
        path = data["path"]["text"]
        file_lines = lf_lines(files[path], keepends=True)
        assert file_lines[data["line_number"] - 1] == data["lines"]["text"]
        assert data["submatches"] == []
        assert data["absolute_offset"] == sum(
            len(l.encode("utf-8")) for l in file_lines[: data["line_number"] - 1])

    raw_records = lf_lines(r.stdout, keepends=True)
    printed = {}
    for raw, message in zip(raw_records, msgs):
        if message["type"] in ("begin", "match", "context"):
            path = message["data"]["path"]["text"]
            printed[path] = printed.get(path, 0) + len(raw)

    # Per-file statistics on the end message.
    for data in _by_kind(msgs, "end"):
        path = data["path"]["text"]
        stats = data["stats"]
        assert (stats["matched_lines"], stats["matches"]) == expected_counts[path]
        assert stats["searches"] == 1 and stats["searches_with_match"] == 1
        assert stats["bytes_searched"] == len(files[path].encode("utf-8"))
        assert stats["bytes_printed"] == printed[path]

    # The single summary counts every path searched, over all arguments.
    stats = msgs[-1]["data"]["stats"]
    assert stats["bytes_printed"] == sum(len(raw) for raw, message in zip(raw_records, msgs) if message["type"] != "summary")
    assert stats["searches"] == len(files)
    assert stats["searches_with_match"] == 3
    assert stats["matched_lines"] == 5
    assert stats["matches"] == 8
    assert stats["bytes_searched"] == sum(len(v.encode("utf-8")) for v in files.values())

    # Nothing matches: still exactly one summary, and nothing else.
    r = tg(["--json", unique_token(), "one", "two"], cwd=tmp_path)
    assert_exit(r, "no_match")
    msgs = parse_json_stream(r)
    assert [m["type"] for m in msgs] == ["summary"]
    assert msgs[0]["data"]["stats"]["searches"] == 4
    assert msgs[0]["data"]["stats"]["matches"] == 0


# F03.T19
def test_json_with_only_matching_and_with_plain_modes(tmp_path):
    tok, files = _json_tree(tmp_path)
    args = [tok, "one", "two", "three/e.txt"]
    base = ["--sort", "path"]

    plain_json = parse_json_stream(tg([*base, "--json", *args], cwd=tmp_path))
    with_o = parse_json_stream(tg([*base, "--json", "-o", *args], cwd=tmp_path))
    assert without_timing(with_o) == without_timing(plain_json)
    assert len(_by_kind(plain_json, "match")) == 5

    for mode in (["-c"], ["--count-matches"], ["-l"], ["--files-without-match"],
                 ["-c", "--include-zero"]):
        want = tg([*base, *mode, *args], cwd=tmp_path)
        assert want.stdout != b""
        for order in ([*mode, "--json"], ["--json", *mode]):
            got = tg([*base, *order, *args], cwd=tmp_path)
            assert got.stdout == want.stdout, got.describe()
            assert got.code == want.code
            assert b'"type"' not in got.stdout and b"{" not in got.stdout

    want = tg([*base, "--files", "one", "two"], cwd=tmp_path)
    assert out_lines(want) == ["one/a.txt", "one/b.txt", "two/c.txt", "two/deep/d.txt"]
    got = tg([*base, "--files", "--json", "one", "two"], cwd=tmp_path)
    assert got.stdout == want.stdout and b"{" not in got.stdout


def _set_times(root, spec):
    for name, (atime, mtime) in spec.items():
        os.utime(root / name, (atime, mtime))


# F03.T20
@pytest.mark.parametrize("mode", ["scan", "local", "server"])
def test_sorting(tmp_path, mode):
    tok = unique_token()
    root = make_tree(tmp_path / "w", {
        "a.txt": f"{tok}\n", "b/m.txt": f"{tok}\n", "c.txt": f"{tok}\n", "d.txt": "no hit\n"})
    now = time.time()
    # name: (atime, mtime).  Path order a < b/m < c; mtime order b/m < c < a;
    # atime order c < a < b/m.  All three differ.
    spec = {
        "a.txt": (now - 2000, now - 100),
        "b/m.txt": (now - 1000, now - 300),
        "c.txt": (now - 3000, now - 200),
        "d.txt": (now - 50, now - 50),
    }
    by_path = ["w/a.txt", "w/b/m.txt", "w/c.txt"]
    by_mtime = ["w/b/m.txt", "w/c.txt", "w/a.txt"]
    by_atime = ["w/c.txt", "w/a.txt", "w/b/m.txt"]

    if mode != "scan":
        build_index(root)
    base = ["--stats"] + (["--no-index"] if mode == "scan" else [])
    with NoWatchServer(root) if mode == "server" else nullcontext():
        def listed(*flags):
            _set_times(root, spec)      # a run may read files and so touch access times
            r = tg([*base, *flags, "-l", tok, "w"], cwd=tmp_path)
            assert read_stats(r)["path"] == mode, r.describe()
            assert_exit(r, "match")
            return out_lines(r)

        assert listed("--sort", "path") == by_path
        assert listed("--sortr", "path") == by_path[::-1]
        assert listed("--sort-files") == by_path
        assert listed("--sort", "modified") == by_mtime
        assert listed("--sortr", "modified") == by_mtime[::-1]
        assert listed("--sort", "accessed") == by_atime
        assert listed("--sortr", "accessed") == by_atime[::-1]
        # Creation time cannot be set from here: accepted, every file exactly once.
        assert sorted(listed("--sort", "created")) == by_path
        assert sorted(listed("--sortr", "created")) == by_path
        assert sorted(listed("--sort", "none")) == by_path
        assert sorted(listed("--sortr", "none")) == by_path

        # Match lines follow the same file order.
        _set_times(root, spec)
        r = tg([*base, "--sort", "modified", tok, "w"], cwd=tmp_path)
        assert_exit(r, "match")
        assert read_stats(r)["path"] == mode, r.describe()
        assert out_lines(r) == [f"{p}:{tok}" for p in by_mtime]


@pytest.fixture(scope="module")
def slow_tail_tree(tmp_path_factory):
    """A root whose first file (by path) matches and whose other files are large and do not."""
    base = tmp_path_factory.mktemp("buffering")
    tok = unique_token()
    make_tree(base / "w", {"a_first.txt": f"{tok} first\n"})
    for i in range(20):
        make_text_file(base / "w" / f"b_tail{i}.txt", 4 * 1024 * 1024)
    make_tree(base / "w", {"z_last.txt": f"{tok} last\n"})
    return base, tok


# F03.T21
def test_line_buffered_delivers_lines_while_running(slow_tail_tree):
    base, tok = slow_tail_tree
    args = ["--sort", "path", tok, "w"]
    expected = f"w/a_first.txt:{tok} first\nw/z_last.txt:{tok} last\n".encode()

    from F03_helpers import read_stdout_packets, read_before_later_file
    for mode, want in (([], expected), (["-c"], b"w/a_first.txt:1\nw/z_last.txt:1\n")):
        for flags in (["--line-buffered"], ["--block-buffered", "--line-buffered"]):
            output, code, error = read_before_later_file(
                [*flags, *mode, *args], base, base / "w" / "z_last.txt",
                want.split(b"\n", 1)[0] + b"\n")
            assert code == 0, error
            assert output == want
            packets, code, error = read_stdout_packets([*flags, *mode, *args], cwd=base)
            assert code == 0, error
            assert b"".join(packets) == want
            # A flush after each line keeps the next line out of the same
            # write. Partial-line writes remain valid; process speed is free.
            assert all(b"\n" not in packet[:-1] for packet in packets), packets

    # Block-buffered, and both flags with block-buffered last: same bytes, no error.
    for flags in (["--block-buffered"], ["--line-buffered", "--block-buffered"], []):
        r = tg([*flags, *args], cwd=base)
        assert_exit(r, "match")
        assert r.stdout == expected, flags


@pytest.mark.parametrize("mode", ["scan", "local", "server"])
def test_json_records_preserve_unicode_separators(tmp_path, mode):
    from F07_helpers import normalise_json
    token = unique_token()
    content = f"{token}\u0085middle\u2028end\u2029\n"
    root = make_tree(tmp_path / "unicode", {"text.txt": content})
    if mode != "scan":
        build_index(root)
    with NoWatchServer(root) if mode == "server" else nullcontext():
        flags = ["--no-index"] if mode == "scan" else []
        result = tg([*flags, "--json", token, "."], cwd=root)
        assert_exit(result, "match")
        messages = parse_json_stream(result)
        rows = [m["data"] for m in messages if m["type"] == "match"]
        assert len(rows) == 1 and rows[0]["lines"]["text"] == content, result.describe()
        projected = normalise_json(result.stdout)
        assert [m["data"]["lines"]["text"] for m in projected if m["type"] == "match"] == [content]
