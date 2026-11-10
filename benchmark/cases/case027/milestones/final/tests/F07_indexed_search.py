# feature: F07
"""Indexed search: order of preference, same results as a scan, narrowing,
statistics and every way an index or server is passed over."""

from __future__ import annotations

from _helpers import lf_lines
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from _helpers import make_tree, make_unreadable, run_trisift, unique_token, wait_until
from F01_helpers import REGEX_ERROR_LABEL, assert_exit, out_lines, tg
from F05_helpers import notes_in
from F06_helpers import assert_reported_directory, INDEX_DIR_NAME, build_index, expected_indexed_count
from F07_helpers import (
    BUILD_HINT,
    COVERAGE_WARNING,
    FALLBACK_NOTICE,
    NO_INDEX_WARNING,
    STATS_LOCAL,
    STATS_SCAN,
    STATS_SERVER,
    NoWatchServer,
    TracedIndex,
    assert_indexed_equals_scan,
    free_port,
    read_stats,
    rpc_status,
    wide_tree,
)

MODES = ["local", "server"]


def _paths(result):
    return sorted({l.split(":", 1)[0] for l in out_lines(result)})


def _warnings(result, rx):
    return [l for l in lf_lines(result.err) if rx.search(l)]


# F07.T01
def test_order_of_preference(tmp_path):
    tok = unique_token()
    root = make_tree(tmp_path / "w", {"a.txt": f"{tok} a\n", "d/b.txt": f"{tok} b\n"})
    want = ["./a.txt", "./d/b.txt"]

    # Neither: scan, and a file added now is found.
    make_tree(root, {"t0.txt": f"{tok} t0\n"})
    r = tg(["--stats", tok, "."], cwd=root)
    assert read_stats(r)["path"] == "scan"
    assert _paths(r) == ["./a.txt", "./d/b.txt", "./t0.txt"]
    os.remove(root / "t0.txt")

    # Only an index: the local index answers and misses a post-build tracer.
    build_index(root)
    make_tree(root, {"t1.txt": f"{tok} t1\n"})
    r = tg(["--stats", tok, "."], cwd=root)
    assert read_stats(r)["path"] == "local", r.describe()
    assert _paths(r) == want
    os.remove(root / "t1.txt")

    # A ready server is preferred over the index.
    with NoWatchServer(root) as server:
        server.wait_reconciled()
        make_tree(root, {"t2.txt": f"{tok} t2\n"})
        r = tg(["--stats", tok, "."], cwd=root)
        assert read_stats(r)["path"] == "server", r.describe()
        assert _paths(r) == want
    os.remove(root / "t2.txt")

    # --index-path selects a non-default index directory.
    other = make_tree(tmp_path / "o", {"a.txt": f"{tok} a\n", "d/b.txt": f"{tok} b\n"})
    idx = tmp_path / "custom-idx"
    build_index(other, index_path=idx)
    assert not (other / INDEX_DIR_NAME).exists()
    make_tree(other, {"t3.txt": f"{tok} t3\n"})
    r = tg(["--stats", "--index-path", str(idx), tok, "."], cwd=other)
    assert read_stats(r)["path"] == "local", r.describe()
    assert _paths(r) == want
    r = tg(["--stats", tok, "."], cwd=other)
    assert read_stats(r)["path"] == "scan", r.describe()
    assert "./t3.txt" in _paths(r)
    with NoWatchServer(other, index_path=tmp_path / "custom-srv"):
        make_tree(other, {"t4.txt": f"{tok} t4\n"})
        r = tg(["--stats", "--index-path", str(tmp_path / "custom-srv"), tok, "."], cwd=other)
        assert read_stats(r)["path"] == "server", r.describe()
        assert _paths(r) == ["./a.txt", "./d/b.txt", "./t3.txt"]


def _matrix_fixture(tok):
    up = tok.upper()
    return {
        "a.txt": f"{tok} one\nplain\n{tok} {tok} two\nctx line\nmore\nlast {tok}\n",
        "sub/b.rs": f"fn {tok}() {{}}\n// {up}\n",
        "c.md": f"x.{tok}*y\nWord{tok}\n{tok}\nafter\n",
        "none.txt": "nothing here\nat all\n",
        "long.txt": "a" * 300 + tok + "\n",
        "deep/er/d.txt": f"{tok}-dash\nno\n{tok}\n",
    }


def _matrix_cases(tok):
    return [
        [tok], ["-c", tok], ["--count-matches", tok], ["-C", "1", tok], ["-A", "1", tok],
        ["-B", "1", tok], ["--json", "--sort", "path", tok], ["--vimgrep", tok],
        ["--sort", "path", tok], ["-o", tok], ["-r", "REPL", "-o", tok], ["-w", tok],
        ["-x", tok], ["-i", tok.upper()], ["-S", tok], ["-F", f"x.{tok}*y"], ["-m", "1", tok],
        ["-U", f"{tok} one\\nplain"], ["-b", tok], ["--column", tok], ["-M", "50", tok],
        ["--stop-on-nonmatch", tok], ["-l", tok], ["-g", "*.txt", tok], ["-t", "rust", tok],
        ["--type-add", "mine:*.md", "-t", "mine", tok],
        # A file without any trigram of the literal must appear in these.
        ["-v", tok], ["--files-without-match", tok], ["-c", "--include-zero", tok],
        ["--passthru", tok],
    ]


def _assert_matrix_answer(result, tok, case):
    """Independent vectors for the original F07.T02 option matrix.

    Matching rows and spans are enumerated from the authored fixture; only
    their shell formatting and byte positions are calculated here.
    """
    from F03_helpers import OMITTED_MATCH, parse_json_stream
    files = _matrix_fixture(tok)
    lines = {p: lf_lines(text) for p, text in files.items()}
    selected = {
        "a.txt": [(1, [0]), (3, [0, len(tok) + 1]), (6, [5])],
        "c.md": [(1, [2]), (2, [4]), (3, [0])],
        "deep/er/d.txt": [(1, [0]), (3, [0])],
        "long.txt": [(1, [300])],
        "sub/b.rs": [(1, [3])],
    }
    assert result.code == 0, result.describe()
    rows = [(p, n, cols) for p in sorted(selected) for n, cols in selected[p]]
    def text(p, n):
        return lines[p][n - 1]
    def offset(p, n):
        return sum(len((s + "\n").encode()) for s in lines[p][:n - 1])
    plain = lambda p, n: f"{p}:{text(p, n)}"
    if case == 6:  # JSON: independently assert every selected row and span.
        messages = parse_json_stream(result)
        matched = [m["data"] for m in messages if m["type"] == "match"]
        server = read_stats(result)["path"] == "server"
        assert [(d["path"]["text"], d["line_number"], d["lines"]["text"]) for d in matched] == [
            (p, n, text(p, n) + "\n") for p, n, _ in rows]
        for data, (p, n, cols) in zip(matched, rows):
            assert data["absolute_offset"] == (0 if server else offset(p, n))
            assert [(s["start"], s["end"], s["match"]["text"]) for s in data["submatches"]] == [
                (c, c + len(tok), tok) for c in cols]
        assert messages[-1]["type"] == "summary"
        st = messages[-1]["data"]["stats"]
        assert (st["matches"], st["matched_lines"], st["searches_with_match"]) == (11, 10, 5)
        return
    if case in (1, 2, 28):
        counts = {p: (sum(len(c) for _, c in selected[p]) if case == 2 else len(selected[p]))
                  for p in selected}
        if case == 28:
            counts["none.txt"] = 0
        want = [f"{p}:{n}" for p, n in counts.items()]
    elif case in (3, 4, 5):
        # Exact context rows for C1, A1, B1 (no regex reimplementation).
        contexts = {
            3: {"a.txt": [2, 4, 5], "c.md": [4], "deep/er/d.txt": [2], "sub/b.rs": [2]},
            4: {"a.txt": [2, 4], "c.md": [4], "deep/er/d.txt": [2], "sub/b.rs": [2]},
            5: {"a.txt": [2, 5], "deep/er/d.txt": [2]},
        }
        want = [plain(p, n) for p, n, _ in rows]
        want += [f"{p}-{text(p, n)}" for p, nums in contexts[case].items() for n in nums]
        want += ["--"] * (4 if case == 3 else 5)
    elif case == 7:
        want = [f"{p}:{n}:{c + 1}:{text(p, n)}" for p, n, cols in rows for c in cols]
    elif case in (9, 10):
        want = [f"{p}:{tok if case == 9 else 'REPL'}" for p, _, cols in rows for _ in cols]
    elif case == 11:
        want = [plain(p, n) for p, n, _ in rows if (p, n) not in (("c.md", 2), ("long.txt", 1))]
    elif case == 12:
        want = [f"c.md:{tok}", f"deep/er/d.txt:{tok}"]
    elif case in (13, 14):
        want = [plain(p, n) for p, n, _ in rows] + [f"sub/b.rs:// {tok.upper()}"]
    elif case == 15:
        want = [f"c.md:x.{tok}*y"]
    elif case == 16:
        want = [plain(p, selected[p][0][0]) for p in selected]
    elif case == 17:
        want = [f"a.txt:{tok} one", "a.txt:plain"]
    elif case == 18:
        want = [f"{p}:{offset(p, n)}:{text(p, n)}" for p, n, _ in rows]
    elif case == 19:
        want = [f"{p}:{n}:{cols[0] + 1}:{text(p, n)}" for p, n, cols in rows]
    elif case == 20:
        want = [f"{p}:{OMITTED_MATCH}" if p == "long.txt" else plain(p, n) for p, n, _ in rows]
    elif case == 21:
        want = [plain(p, n) for p, n, _ in rows if (p, n) not in
                (("a.txt", 3), ("a.txt", 6), ("deep/er/d.txt", 3))]
    elif case == 22:
        want = list(selected)
    elif case in (23, 24, 25):
        paths = {23: {"a.txt", "deep/er/d.txt", "long.txt"}, 24: {"sub/b.rs"}, 25: {"c.md"}}[case]
        want = [plain(p, n) for p, n, _ in rows if p in paths]
    elif case == 27:
        want = ["none.txt"]
    elif case in (26, 29):
        unselected = {"a.txt": [2, 4, 5], "c.md": [4], "deep/er/d.txt": [2],
                      "sub/b.rs": [2], "none.txt": [1, 2]}
        separator = ":" if case == 26 else "-"
        want = [f"{p}{separator}{text(p, n)}" for p, nums in unselected.items() for n in nums]
        if case == 29:
            want += [plain(p, n) for p, n, _ in rows]
    else:
        assert case in (0, 8), case
        want = [plain(p, n) for p, n, _ in rows]
    assert sorted(out_lines(result)) == sorted(want), result.describe()


# F07.T02
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("case", range(len(_matrix_cases("token"))))
def test_indexed_results_equal_scan_over_option_matrix(tmp_path, mode, case):
    tok = unique_token()
    with TracedIndex(tmp_path, _matrix_fixture(tok), mode) as t:
        args = _matrix_cases(tok)[case]
        r = assert_indexed_equals_scan(t, args)
        _assert_matrix_answer(r, tok, case)
        scan = run_trisift(["--stats", "--no-index", *args], cwd=t.pristine)
        _assert_matrix_answer(scan, tok, case)
        if args[:-1] in (["-v"], ["--files-without-match"], ["-c", "--include-zero"], ["--passthru"]):
            assert b"none.txt" in r.stdout, f"{args}: {r.describe()}"
        assert_indexed_equals_scan(t, ["--sort", "path", tok, "."])


def _case_fixture():
    t = {k: unique_token() for k in ("whole", "ga", "gb", "smart", "kel", "lng", "look", "lk2", "br")}
    # Kelvin sign U+212A stands for 'k', long s U+017F for 's'.
    kel_word = f"{t['kel']}k{t['kel']}"
    lng_word = f"{t['lng']}s{t['lng']}"
    files = {
        "whole.txt": f"{t['whole'].upper()}\n",
        "group.txt": f"{t['ga']}{t['gb'].upper()}\n",
        "groupneg.txt": f"{t['ga'].upper()}{t['gb'].upper()}\n",
        "smart.txt": f"{t['smart'].upper()}\n",
        "kelvin.txt": f"{t['kel']}\u212a{t['kel']}\n",
        "longs.txt": f"{t['lng']}\u017f{t['lng']}\n",
        "look.txt": f"{t['look']} {t['lk2']}\n",
        "looknot.txt": f"{t['look']} other\n",
        "br.txt": f"{t['br']} {t['br']}\n",
        "brnot.txt": f"{t['br']} x\n",
    }
    cases = [
        ([f"(?i){t['whole']}"], "whole.txt"),
        ([f"{t['ga']}(?i:{t['gb']})"], "group.txt"),
        (["-S", t["smart"]], "smart.txt"),
        (["-i", kel_word], "kelvin.txt"),
        (["-i", lng_word], "longs.txt"),
        ([f"{t['look']}(?= {t['lk2']})"], "look.txt"),
        ([f"({t['br']}) \\1"], "br.txt"),
    ]
    return files, cases


# F07.T03
@pytest.mark.parametrize("mode", MODES)
def test_case_rules_and_engines_agree_on_every_path(tmp_path, mode):
    files, cases = _case_fixture()
    with TracedIndex(tmp_path, files, mode) as t:
        for args, sole in cases:
            scan = tg(["--no-index", "-l"] + args + ["."], cwd=t.pristine)
            assert out_lines(scan) == [f"./{sole}"], f"{args}: {scan.describe()}"
            r = assert_indexed_equals_scan(t, args + ["."], expect_path=mode)
            assert _paths(r) == [f"./{sole}"], f"{args}: {r.describe()}"
            assert b"groupneg.txt" not in r.stdout


# F07.T04
@pytest.mark.parametrize("mode", MODES)
def test_multiple_patterns_on_every_path(tmp_path, mode):
    toks = [unique_token() for _ in range(4)]
    files = {f"p{i}.txt": f"line {toks[i]}\n" for i in range(4)}
    files["none.txt"] = "unrelated\n"
    with TracedIndex(tmp_path, files, mode) as t:
        r = assert_indexed_equals_scan(t, ["-e", toks[0], "-e", toks[1], "--sort", "path", "."], expect_path=mode)
        assert _paths(r) == ["./p0.txt", "./p1.txt"]
        for base in (t.live, t.pristine):
            (base.parent / f"{base.name}.pats").write_text(f"  {toks[2]}  \n\n{toks[3]}\n")
        pat_file = f"../{t.live.name}.pats"
        r = assert_indexed_equals_scan(t, ["-f", pat_file, "--sort", "path", "."], expect_path=mode)
        assert _paths(r) == ["./p2.txt", "./p3.txt"]
        r = assert_indexed_equals_scan(t, ["-f", pat_file, "-e", toks[0], "--sort", "path", "."], expect_path=mode)
        assert _paths(r) == ["./p0.txt", "./p2.txt", "./p3.txt"]


# F07.T05
@pytest.mark.parametrize("mode", MODES)
def test_regex_size_limit_fails_on_indexed_paths(tmp_path, mode):
    tok = unique_token()
    files = {"a.txt": f"{tok}xx\n", "b.txt": f"{tok}\n"}
    with TracedIndex(tmp_path, files, mode) as t:
        for pat in (f"{tok}.*x", f"{tok}x+", f"{tok}x{{2,}}"):
            r = tg(["--regex-size-limit", "1", pat, "."], cwd=t.live)
            assert_exit(r, "error")
            assert r.stdout == b"", r.describe()
            assert REGEX_ERROR_LABEL in r.err, r.describe()
            # Live baseline: without the limit the pattern finds results.
            ok = tg([pat, "."], cwd=t.live)
            assert ok.stdout, ok.describe()
        assert_indexed_equals_scan(t, ["--regex-size-limit", "1", "-P", f"{tok}.*x"], expect_path=mode)


def _set_times(base, order):
    now = time.time()
    for i, rel in enumerate(order):
        # atime in the future so reading the file does not move it.
        os.utime(base / rel, (now + 100000 + 1000 * i, now - 100000 + 1000 * i))


# F07.T06
@pytest.mark.parametrize("mode", MODES)
def test_sort_order_same_on_every_path(tmp_path, mode):
    tok = unique_token()
    names = ["a.txt", "b/c.txt", "d.txt", "e/f/g.txt", "h.txt"]
    files = {n: f"{tok} {n}\n" for n in names}
    time_order = ["d.txt", "h.txt", "a.txt", "e/f/g.txt", "b/c.txt"]
    with TracedIndex(tmp_path, files, mode, setup=lambda b: _set_times(b, time_order)) as t:
        expect = {
            ("--sort", "path"): sorted(names),
            ("--sortr", "path"): sorted(names, reverse=True),
            ("--sort", "modified"): time_order,
            ("--sortr", "modified"): time_order[::-1],
            ("--sort", "accessed"): time_order,
        }
        for (opt, key), order in expect.items():
            r = assert_indexed_equals_scan(t, [opt, key, tok, "."], expect_path="indexed")
            assert [l.split(":", 1)[0] for l in out_lines(r)] == [f"./{n}" for n in order], (
                f"{opt} {key}: {r.describe()}")


# F07.T07
@pytest.mark.parametrize("mode", MODES)
def test_subtree_and_unrelated_root(tmp_path, mode):
    tok = unique_token()
    files = {"top.txt": f"{tok} top\n", "sub/s.txt": f"{tok} s\n", "sub/in/x.txt": f"{tok} x\n"}
    with TracedIndex(tmp_path, files, mode) as t:
        idx_live = str(t.live / INDEX_DIR_NAME)
        # Typed subdirectory from the root.
        r = tg(["--stats", "--index-path", idx_live, "--sort", "path", tok, "sub"], cwd=t.live)
        st = read_stats(r)
        assert st["path"] in ("local", "server"), r.describe()
        assert _paths(r) == ["sub/in/x.txt", "sub/s.txt"], r.describe()
        ref = tg(["--no-index", "--sort", "path", tok, "sub"], cwd=t.pristine)
        assert r.stdout == ref.stdout
        shallow = tg(["--stats", "--index-path", idx_live, "--max-depth", "1", tok, "sub"], cwd=t.live)
        assert read_stats(shallow)["path"] == mode
        assert _paths(shallow) == ["sub/s.txt"]
        # From inside the subtree, with no path and with '.'.
        for extra, want in (([], ["in/x.txt", "s.txt"]), (["."], ["./in/x.txt", "./s.txt"])):
            r = tg(["--stats", "--index-path", "../" + INDEX_DIR_NAME, "--sort", "path", tok] + extra,
                   cwd=t.live / "sub")
            assert read_stats(r)["path"] in ("local", "server"), r.describe()
            assert _paths(r) == want, r.describe()

        # A root outside the indexed tree: scanned, never the index's results.
        outside = make_tree(tmp_path / "elsewhere", {"o.txt": f"{tok} other\n"})
        r = tg(["--stats", "--index-path", idx_live, tok, str(outside)], cwd=tmp_path)
        assert read_stats(r)["path"] == "scan", r.describe()
        assert out_lines(r) == [f"{outside}/o.txt:{tok} other"], r.describe()


# F07.T08
def test_filters_stay_on_the_index(tmp_path):
    tok = unique_token()
    files = {
        ".ignore": "ign.txt\n",
        "a.txt": f"{tok} a\n", "ign.txt": f"{tok} ign\n", ".h.txt": f"{tok} hidden\n",
        "sub/b.rs": f"{tok} b\n", "sub/c.TXT": f"{tok} c\n", "sub/deep/d.txt": f"{tok} d\n",
    }
    # Expected file sets come from the fixture: the index holds every
    # non-ignored file (hidden ones too); each filter narrows that set.
    cases = [
        (["-g", "*.txt"], ["./a.txt", "./sub/deep/d.txt"]),
        (["-g", "!sub/**"], ["./a.txt"]),
        (["--iglob", "*.txt"], ["./a.txt", "./sub/c.TXT", "./sub/deep/d.txt"]),
        (["-g", "*.txt", "--glob-case-insensitive"], ["./a.txt", "./sub/c.TXT", "./sub/deep/d.txt"]),
        (["-t", "rust"], ["./sub/b.rs"]),
        (["-g", "*", "-t", "rust"], ["./sub/b.rs"]),
        (["--hidden"], ["./.h.txt", "./a.txt", "./sub/b.rs", "./sub/c.TXT", "./sub/deep/d.txt"]),
        ([], ["./a.txt", "./sub/b.rs", "./sub/c.TXT", "./sub/deep/d.txt"]),
        (["--max-depth", "1"], ["./a.txt"]),
        (["--hidden", "-g", "*.txt"], ["./.h.txt", "./a.txt", "./sub/deep/d.txt"]),
    ]
    with TracedIndex(tmp_path, files, "local") as t:
        for args, want in cases:
            r = tg(["--stats"] + args + [tok, "."], cwd=t.live)
            assert read_stats(r)["path"] == "local", f"{args}: {r.describe()}"
            assert _paths(r) == want, f"{args}: {r.describe()}"
            assert b"_trc" not in r.stdout, f"{args}: {r.describe()}"
        r = tg(["--stats", "--sort", "path", tok, "."], cwd=t.live)
        assert read_stats(r)["path"] == "local"
        assert [l.split(":", 1)[0] for l in out_lines(r)] == ["./a.txt", "./sub/b.rs", "./sub/c.TXT",
                                                              "./sub/deep/d.txt"], r.describe()
        # Where no ignored or hidden file is involved the scan agrees.
        for args in (["-t", "rust"], ["--max-depth", "1"], ["-g", "!sub/**"], ["--sort", "path"]):
            assert_indexed_equals_scan(t, args + [tok], expect_path="local")

        # A positive glob never brings back an ignored file on the index...
        r = tg(["--stats", "-g", "ign.txt", tok, "."], cwd=t.live)
        assert read_stats(r)["path"] == "local", r.describe()
        assert r.stdout == b"", r.describe()
        assert_exit(r, "no_match")
        # ...but does under --no-index.
        r = tg(["--no-index", "-g", "ign.txt", tok, "."], cwd=t.pristine)
        assert out_lines(r) == [f"./ign.txt:{tok} ign"], r.describe()


SCAN_FORCERS = [
    ["--no-index"], ["--no-ignore"], ["--no-ignore-dot"], ["--no-ignore-vcs"],
    ["--no-ignore-exclude"], ["--no-ignore-global"], ["--no-ignore-parent"], ["-u"],
    ["--text"], ["--binary"], ["-E", "latin1"], ["-E", "utf-8"],
]


# F07.T09
def test_options_that_force_a_scan(tmp_path):
    tok, old, new = unique_token(), unique_token(), unique_token()
    root = make_tree(tmp_path / "w", {"a.txt": f"{tok} {old}\n", "b.txt": f"{tok} b\n",
                                      "bin.txt": f"{tok}\0\n".encode()})
    with NoWatchServer(root):
        make_tree(root, {"a.txt": f"{tok} {new}\n", "created.txt": f"{tok} created\n"})
        # Live baseline: the server answers from its snapshot.
        r = tg(["--stats", tok, "."], cwd=root)
        assert read_stats(r)["path"] == "server", r.describe()
        assert b"created.txt" not in r.stdout, r.describe()
        for opt in SCAN_FORCERS:
            r = tg(["--stats"] + opt + [tok, "."], cwd=root)
            assert read_stats(r)["path"] == "scan", f"{opt}: {r.describe()}"
            assert f"./created.txt:{tok} created" in out_lines(r), f"{opt}: {r.describe()}"
            assert f"./a.txt:{tok} {new}" in out_lines(r), f"{opt}: {r.describe()}"
        r = tg(["--stats", tok, "a.txt"], cwd=root)
        assert read_stats(r)["path"] == "scan", r.describe()
        assert out_lines(r) == [f"{tok} {new}"]
        r = tg(["--stats", tok, "bin.txt"], cwd=root)
        assert read_stats(r)["path"] == "scan", r.describe()
        assert len(notes_in(r)) == 1, r.describe()


# F07.T10
def test_encoding_and_binary_options_equal_scan_with_index_and_server(tmp_path):
    tok = unique_token()
    root = make_tree(tmp_path / "w", {
        "plain.txt": f"{tok} plain\n",
        "u16.txt": f"{tok} sixteen\n".encode("utf-16-le"),
        "lat.txt": f"{tok} café\n".encode("latin-1"),
        "bin.txt": f"{tok}\0 bin\n".encode(),
    })
    build_index(root)
    with NoWatchServer(root):
        for opt in (["-E", "latin1"], ["-E", "utf-16le"], ["--text"], ["--binary"]):
            args = opt + ["--sort", "path", tok, "."]
            a = tg(args, cwd=root)
            b = tg(["--no-index"] + args, cwd=root)
            assert (a.code, a.stdout) == (b.code, b.stdout), f"{opt}\n{a.describe()}\n{b.describe()}"
        r = tg(["-E", "utf-16le", "--sort", "path", tok, "."], cwd=root)
        assert f"./u16.txt:{tok} sixteen" in out_lines(r), r.describe()
        r = tg(["--sort", "path", tok, "."], cwd=root)
        assert b"u16.txt" not in r.stdout and b"bin.txt" not in r.stdout
        r = tg(["--binary", "--sort", "path", tok, "."], cwd=root)
        assert [p for p, _ in notes_in(r)] == ["./bin.txt"], r.describe()


# F07.T11
def test_options_ignored_by_indexed_search(tmp_path):
    tok = unique_token()
    outside = make_tree(tmp_path / "outside", {"o.txt": f"{tok} outside\n"})
    root = make_tree(tmp_path / "w", {".ignore": "UPPER.txt\n", "a.txt": f"{tok} a\n",
                                      "ign.txt": f"{tok} ign\n", "upper.txt": f"{tok} upper\n"})
    os.symlink(outside, root / "lnk")
    (tmp_path / "ignfile").write_text("ign.txt\n")
    build_index(root)
    full = ["./a.txt", "./ign.txt", "./upper.txt"]

    for opt in (["--ignore-file", str(tmp_path / "ignfile")], ["--ignore-file-case-insensitive"], ["-L"],
                ["--follow"], ["--one-file-system"]):
        r = tg(["--stats"] + opt + [tok, "."], cwd=root)
        assert read_stats(r)["path"] == "local", f"{opt}: {r.describe()}"
        assert _paths(r) == full, f"{opt}: {r.describe()}"

    base = tg(["--no-index", tok, "."], cwd=root)
    assert _paths(base) == full
    r = tg(["--no-index", "--ignore-file", str(tmp_path / "ignfile"), tok, "."], cwd=root)
    assert _paths(r) == ["./a.txt", "./upper.txt"], r.describe()
    r = tg(["--no-index", "--ignore-file-case-insensitive", tok, "."], cwd=root)
    assert _paths(r) == ["./a.txt", "./ign.txt"], r.describe()
    r = tg(["--no-index", "-L", tok, "."], cwd=root)
    assert _paths(r) == sorted(full + ["./lnk/o.txt"]), r.describe()


# F07.T12
def test_snapshot_freshness_without_server(tmp_path):
    tok = unique_token()
    root = make_tree(tmp_path / "w", {"a.txt": f"{tok} a\n"})
    build_index(root)
    fresh = unique_token()
    make_tree(root, {"later.txt": f"{tok} later\n{fresh}\n"})
    r = tg(["--stats", fresh, "."], cwd=root)
    assert_exit(r, "no_match")
    assert r.stdout == b"" and read_stats(r)["path"] == "local"
    r = tg(["--stats", tok, "."], cwd=root)
    assert read_stats(r)["path"] == "local"
    assert out_lines(r) == [f"./a.txt:{tok} a"]
    r = tg(["--no-index", "--sort", "path", tok, "."], cwd=root)
    assert out_lines(r) == [f"./a.txt:{tok} a", f"./later.txt:{tok} later"]


def _trigrams(s):
    b = s.encode()
    return {b[i:i + 3] for i in range(len(b) - 2)}


def _has_all(data, lit, fold=False):
    if fold:
        data, lit = data.lower(), lit.lower()
    return all(t in data for t in _trigrams(lit))


# F07.T13
def test_narrowing_bounds_raw_candidates(tmp_path):
    # Keep the narrowing bound separate from Unicode case-equivalence fallback.
    def literal():
        return unique_token(prefix="v").replace("k", "p").replace("s", "q")

    t1, t2 = literal(), literal()

    def scattered(t):
        return f"{t[:5]} -- {t[3:9]} -- {t[7:]}\n"

    files = {}
    files.update({f"m{i}.txt": f"x {t1} y\n" for i in range(3)})
    files.update({f"s{i}.txt": scattered(t1) for i in range(2)})
    files["up.txt"] = f"{t1.upper()}\n"
    files.update({f"n{i}.txt": f"{t2} filler {i}\n" for i in range(3)})
    files.update({f"z{i}.txt": f"nothing {i} here\n" for i in range(30)})
    root = make_tree(tmp_path / "w", files)
    for rel, body in files.items():
        if "-- " in body:
            assert t1 not in body and _has_all(body.encode(), t1)
    build_index(root)
    data = {rel: (root / rel).read_bytes() for rel in files}

    def stats(args):
        r = tg(["--stats"] + args + ["."], cwd=root)
        st = read_stats(r)
        assert st["path"] == "local", r.describe()
        return r, st

    # ASCII case variants may remain raw candidates even without -i.
    k = sum(_has_all(d, t1, fold=True) for d in data.values())
    r, st = stats([t1])
    matching = len(_paths(r))
    assert_exit(r, "match")
    assert set(_paths(r)) == {f"./m{i}.txt" for i in range(3)}
    assert matching <= st["raw"] <= k == 6, st

    k_ci = sum(_has_all(d, t1, fold=True) for d in data.values())
    r, st = stats(["-i", t1])
    assert_exit(r, "match")
    assert set(_paths(r)) == {f"./m{i}.txt" for i in range(3)} | {"./up.txt"}
    assert len(_paths(r)) <= st["raw"] <= k_ci, st

    k2 = sum(_has_all(d, t2, fold=True) for d in data.values())
    r, st = stats([f"{t1}|{t2}"])
    assert_exit(r, "match")
    assert set(_paths(r)) == {f"./{prefix}{i}.txt" for prefix in ("m", "n") for i in range(3)}
    union = sum(_has_all(d, t1, fold=True) or _has_all(d, t2, fold=True) for d in data.values())
    assert len(_paths(r)) <= st["raw"] <= union <= k + k2, st
    assert st["raw"] < st["indexed"]


# F07.T14
def test_stats_report_on_indexed_answer(tmp_path):
    tok = unique_token()
    files = {
        "a.txt": f"{tok} {tok}\nno\n{tok}\n",
        "b.rs": f"{tok}\n",
        "c.txt": "nothing\n",
        "d/e.txt": f"x{tok}y {tok}\n",
        "pic.png": f"{tok}\n",
    }
    root = make_tree(tmp_path / "w", files)
    build_index(root)
    texts = [v for k, v in files.items() if not k.endswith(".png")]
    want_matches = sum(t.count(tok) for t in texts)
    want_lines = sum(sum(1 for l in lf_lines(t) if tok in l) for t in texts)

    r = tg(["--stats", tok, "."], cwd=root)
    st = read_stats(r)
    assert st["path"] == "local"
    assert (st["matches"], st["matched_lines"]) == (want_matches, want_lines), r.describe()
    assert st["raw_indexed"] == st["indexed"] == expected_indexed_count(root) == 4
    assert st["raw"] < st["indexed"] and not st["no_narrowing"], r.describe()
    assert st["candidates"] <= st["raw"]

    r = tg(["--stats", "-g", "*.txt", tok, "."], cwd=root)
    st = read_stats(r)
    assert st["candidates"] < st["raw"], r.describe()
    r = tg(["--stats", "-t", "rust", tok, "."], cwd=root)
    st = read_stats(r)
    assert st["candidates"] < st["raw"], r.describe()

    r = tg(["--stats", "\\w+", "."], cwd=root)
    st = read_stats(r)
    assert st["raw"] == st["indexed"] and st["no_narrowing"], r.describe()

    r = tg([tok, "."], cwd=root)
    assert_exit(r, "match")
    assert r.stderr == b"", r.describe()

    merged = run_trisift(["--stats", "--sort", "path", tok, "."], cwd=root, merge_stderr=True)
    lines = lf_lines(merged.stdout.decode())
    stat_idx = [i for i, l in enumerate(lines) if STATS_LOCAL.search(l)]
    match_idx = [i for i, l in enumerate(lines) if l.startswith("./")]
    assert stat_idx and match_idx and min(stat_idx) > max(match_idx), merged.describe()

    with NoWatchServer(root):
        r = tg(["--stats", tok, "."], cwd=root)
        st = read_stats(r)
        assert st["path"] == "server"
        assert (st["matches"], st["matched_lines"]) == (want_matches, want_lines), r.describe()
        assert st["raw_indexed"] == st["indexed"] == 4 and st["raw"] < 4
        r = tg([tok, "."], cwd=root)
        assert r.stderr == b"", r.describe()


# F07.T15
def test_no_index_warning(tmp_path):
    tok = unique_token()
    root = make_tree(tmp_path / "w", {"a.txt": f"{tok}\n", "b/c.txt": f"{tok} c\n"})
    r = tg(["--stats", "--sort", "path", tok, "."], cwd=root)
    assert read_stats(r)["path"] == "scan"
    warn = [m for m in (NO_INDEX_WARNING.match(l) for l in lf_lines(r.err)) if m]
    assert len(warn) == 1, r.describe()
    assert_reported_directory(r, root / INDEX_DIR_NAME, warning=True)
    assert BUILD_HINT in r.err
    assert out_lines(r) == [f"./a.txt:{tok}", f"./b/c.txt:{tok} c"]

    custom = tmp_path / "nowhere-idx"
    r = tg(["--index-path", str(custom), tok, "."], cwd=root)
    warn = [m for m in (NO_INDEX_WARNING.match(l) for l in lf_lines(r.err)) if m]
    assert len(warn) == 1
    assert_reported_directory(r, custom, warning=True)
    assert BUILD_HINT in r.err
    assert_exit(r, "match")

    r = tg(["-q", tok, "."], cwd=root)
    assert_exit(r, "match")
    assert not NO_INDEX_WARNING.search(r.err) and BUILD_HINT not in r.err, r.describe()


def _break_meta_missing(idx, other):
    os.remove(idx / "meta.json")


def _break_meta_garbled(idx, other):
    (idx / "meta.json").write_text("{not json")


def _break_extra_missing(idx, other):
    os.remove(idx / "files-extra.bin")


def _break_extra_empty(idx, other):
    (idx / "files-extra.bin").write_bytes(b"")


def _break_extra_truncated(idx, other):
    p = idx / "files-extra.bin"
    b = p.read_bytes()
    p.write_bytes(b[: len(b) // 2])


def _break_meta_foreign(idx, other):
    shutil.copy(other / "meta.json", idx / "meta.json")


def _break_extra_foreign(idx, other):
    shutil.copy(other / "files-extra.bin", idx / "files-extra.bin")


BREAKS = [_break_meta_missing, _break_meta_garbled, _break_extra_missing, _break_extra_empty,
          _break_extra_truncated, _break_meta_foreign, _break_extra_foreign]


# F07.T16
@pytest.mark.parametrize("brk", BREAKS, ids=lambda f: f.__name__[7:])
def test_incomplete_coverage_makes_search_scan(tmp_path, brk):
    tok = unique_token()
    other_root = make_tree(tmp_path / "other", {"q.txt": "q\n", "s/t.txt": "t\n"})
    build_index(other_root)
    root = make_tree(tmp_path / "w", {"a.txt": f"{tok} a\n", "b.txt": f"{tok} b\n"})
    build_index(root)
    make_tree(root, {"post.txt": f"{tok} post\n"})
    # Live baseline: the unaltered index is used.
    r = tg(["--stats", tok, "."], cwd=root)
    assert read_stats(r)["path"] == "local"
    brk(root / INDEX_DIR_NAME, other_root / INDEX_DIR_NAME)

    r = tg(["--stats", "--sort", "path", tok, "."], cwd=root)
    assert read_stats(r)["path"] == "scan", r.describe()
    assert out_lines(r) == [f"./a.txt:{tok} a", f"./b.txt:{tok} b", f"./post.txt:{tok} post"]
    assert len(_warnings(r, COVERAGE_WARNING)) == 1, r.describe()
    assert_exit(r, "match")

    r = tg([unique_token(), "."], cwd=root)
    assert_exit(r, "no_match")
    assert len(_warnings(r, COVERAGE_WARNING)) == 1, r.describe()
    for quiet in (["-q"], ["--no-messages"]):
        r = tg(quiet + [tok, "."], cwd=root)
        assert_exit(r, "match")
        assert not _warnings(r, COVERAGE_WARNING), r.describe()


# F07.T17
def test_build_that_could_not_read_a_directory_lacks_coverage(tmp_path):
    tok, hid = unique_token(), unique_token()
    root = make_tree(tmp_path / "w", {"a.txt": f"{tok} a\n", "locked/l.txt": f"{hid} locked\n"})
    # Live baseline: a clean build answers from the index.
    build_index(root)
    make_tree(root, {"post.txt": f"{tok} post\n"})
    r = tg(["--stats", tok, "."], cwd=root)
    assert read_stats(r)["path"] == "local" and b"post.txt" not in r.stdout
    os.remove(root / "post.txt")

    with make_unreadable(root / "locked"):
        build_index(root)
    r = tg(["--stats", hid, "."], cwd=root)
    assert read_stats(r)["path"] == "scan", r.describe()
    assert out_lines(r) == [f"./locked/l.txt:{hid} locked"], r.describe()
    assert len(_warnings(r, COVERAGE_WARNING)) == 1, r.describe()


# F07.T18
def test_unusable_server_falls_back_with_complete_results(tmp_path):
    tok = unique_token()
    root = make_tree(tmp_path / "w", {"a.txt": f"{tok} a\n", "d/b.txt": f"{tok} b\n"})
    build_index(root)
    rec = root / INDEX_DIR_NAME / "serve.json"
    with free_port() as port:
        rec.write_text(json.dumps({"pid": os.getpid(), "port": port}))
        r = tg(["--sort", "path", tok, "."], cwd=root)
        assert len(_warnings(r, FALLBACK_NOTICE)) == 1, r.describe()
        ref = tg(["--no-index", "--sort", "path", tok, "."], cwd=root)
        assert (r.code, r.stdout) == (ref.code, ref.stdout)
        assert out_lines(r) == [f"./a.txt:{tok} a", f"./d/b.txt:{tok} b"]
    os.remove(rec)

    # Block one hidden source file, while the client scans visible content.
    # This observes an incomplete build without prescribing a minimum duration.
    from F00_observations import ReadGate
    big = make_tree(tmp_path / "big", {".gate": "unrelated\n", "needle.txt": f"{tok} needle\n"})
    srv = NoWatchServer(big)
    with ReadGate(big / ".gate") as gate:
        srv.start(ready=False)
        try:
            gate.wait_blocked(srv.proc)
            before = _first_status(srv)
            assert before["indexing"] is True and before["hidden_complete"] is False
            r = tg(["--sort", "path", tok, "."], cwd=big)
            assert srv.status()["indexing"] is True
            assert len(_warnings(r, FALLBACK_NOTICE)) == 1, r.describe()
            assert out_lines(r) == [f"./needle.txt:{tok} needle"], r.describe()
            assert_exit(r, "match")
        finally:
            gate.release()
            srv.proc.__exit__(None, None, None)


def _first_status(srv):
    return wait_until(lambda: srv.status(), timeout=30, retry_on=(OSError, ValueError),
                      message="server status never answered")


# F07.T14 regression — FP-07.08, FP-07.09

def test_candidate_counts_and_actual_reads(tmp_path):
    from F00_observations import ReadEvents
    root = make_tree(tmp_path / "w", {"a.txt": "redwood redwood\n", "b.txt": "redwood?\n",
        "c.txt": "unrelated\n", "z.rs": "redwood\n"})
    build_index(root)
    # Every literal-bearing file must be a candidate; the path filter then narrows it.
    r = tg(["--stats", "-g", "*.txt", "redwood", "."], cwd=root)
    st = read_stats(r)
    assert st["raw"] == 3 and st["candidates"] == 2 and st["indexed"] == 4
    assert sorted(out_lines(r)) == ["./a.txt:redwood redwood", "./b.txt:redwood?"]
    with ReadEvents([root / "c.txt"]) as events:
        r = tg(["--stats", "redwood", "."], cwd=root)
        assert_exit(r, "match")
        assert read_stats(r)["candidates"] == 3
        assert events.accessed() == set()
        assert_exit(tg(["--no-index", "unrelated", "."], cwd=root), "match")
        assert events.accessed() == {root / "c.txt"}
    empty = make_tree(tmp_path / "empty", {})
    build_index(empty)
    r = tg(["--stats", "redwood", "."], cwd=empty)
    assert_exit(r, "no_match")
    st = read_stats(r)
    assert st["indexed"] == st["raw"] == st["candidates"] == 0 and not st["no_narrowing"]


# F07.T02 regression — FP-02–FP-05, FP-07.02, FP-07.04, FP-07.08
def _independent_option_cases(tok):
    """Fixture-derived answers, never output captured from another product run."""
    from F03_helpers import OMITTED_MATCH
    line = f"xx {tok} {tok}"
    row = f"./a.txt:{line}"
    cases = {}

    def add(name, opts, want, pattern=None, selection=("-g", "!*.rs", "-g", "!*.md"), code=0):
        args = [*([] if "--sortr" in opts else ["--sort", "path"]), *selection, *opts]
        if pattern is not False:
            args.append(tok if pattern is None else pattern)
        args.append(".")
        output = want if isinstance(want, bytes) else "".join(s + "\n" for s in want).encode()
        cases[name] = (args, output, code)

    add("plain", [], [row])
    add("context", ["-C", "1"], ["./a.txt-before", row, "./a.txt-after"])
    add("before-context", ["-B", "1", "-n"], ["./a.txt-1-before", f"./a.txt:2:{line}"])
    add("after-context", ["-A", "1", "-n"], [f"./a.txt:2:{line}", "./a.txt-3-after"])
    add("only", ["-o"], [f"./a.txt:{tok}"] * 2)
    add("replacement", ["-o", "-r", "leaf" + tok], [f"./a.txt:leaf{tok}"] * 2)
    add("named-replacement", ["-r", "${word}!", "-o"], [f"./a.txt:{tok}!"] * 2,
        pattern=f"(?P<word>{tok})")
    add("offset", ["-b"], [f"./a.txt:7:{line}"])
    add("only-offset-column", ["-o", "-b", "--column"],
        [f"./a.txt:2:4:10:{tok}", f"./a.txt:2:{5 + len(tok)}:{11 + len(tok)}:{tok}"])
    add("column", ["--column"], [f"./a.txt:2:4:{line}"])
    add("vimgrep", ["--vimgrep"], [f"./a.txt:2:4:{line}", f"./a.txt:2:{5 + len(tok)}:{line}"])
    add("long-line", ["-M", "10"], [f"./a.txt:{OMITTED_MATCH}"])
    add("count-lines", ["-c"], ["./a.txt:1"])
    add("count-matches", ["--count-matches"], ["./a.txt:2"])
    add("count-zero", ["-c", "--include-zero"], ["./a.txt:1", "./b.txt:0"])
    add("filenames-null", ["-l", "-0"], b"./a.txt\0")
    add("files-without", ["--files-without-match"], ["./b.txt"])
    add("files-without-no-match", ["--files-without-match"], [], pattern=".", code=1)
    add("invert", ["-v"], ["./a.txt:before", "./a.txt:after", "./b.txt:7"])
    add("passthru", ["--passthru"], ["./a.txt-before", row, "./a.txt-after", "./b.txt-7"])
    add("passthru-no-match", ["--passthru"], ["./a.txt-before", f"./a.txt-{line}", "./a.txt-after", "./b.txt-7"],
        pattern=tok + "absent", code=1)
    add("max-count-zero", ["-m", "0"], [], code=1)
    add("max-count-one", ["-m", "1", "-o"], [f"./a.txt:{tok}"] * 2)
    add("stop-after-match", ["--stop-on-nonmatch"], [row])
    add("no-filename", ["-H", "-I", "-n"], [f"2:{line}"])
    add("heading", ["--heading", "-n"], ["./a.txt", f"2:{line}"])
    add("field-separators", ["-C", "1", "-n", "--field-match-separator", "|",
                             "--field-context-separator", "~"],
        ["./a.txt~1~before", f"./a.txt|2|{line}", "./a.txt~3~after"])
    add("line-buffered", ["--line-buffered"], [row])
    add("block-buffered", ["--line-buffered", "--block-buffered"], [row])
    add("trim", ["--trim"], [row])
    add("ignore-case", ["-i"], [row], pattern=tok.upper())
    add("smart-case", ["-S"], [row])
    add("case-sensitive-over-smart", ["-S", "-s"], [], pattern=tok.upper(), code=1)
    add("ignore-over-sensitive", ["-i", "-s", "-S"], [row], pattern=tok.upper())
    add("inline-case", [], [row], pattern=f"(?i:{tok.upper()})")
    add("fixed", ["-F"], [row], pattern=f"{tok} {tok}")
    add("fixed-no-match", ["-F"], [], pattern=f"{tok}.*", code=1)
    add("word", ["-w"], [row])
    add("line", ["-w", "-x"], [row], pattern=line)
    add("line-no-match", ["-x"], [], code=1)
    add("multiple-patterns", ["-e", tok, "-e", r"^\d$"], [row, "./b.txt:7"], pattern=False)
    add("pattern-file", ["-f", "../patterns"], [row, "./b.txt:7"], pattern=False)
    add("multiline", ["-U"], ["./a.txt:before", row], pattern=f"before\nxx {tok}")
    add("dotall", ["--multiline-dotall"], ["./a.txt:before", row], pattern=f"before.*{tok}")
    add("lookaround-auto", [], [row], pattern=f"{tok}(?= {tok})")
    add("lookaround-pcre", ["-P"], [row], pattern=f"{tok}(?= {tok})")
    add("backreference", ["--engine", "pcre2"], [row], pattern=rf"({tok}) \1")
    add("default-engine", ["--engine", "default", "--regex-size-limit", "1G"], [row], pattern=tok + "+")
    add("dfa-limit", ["--dfa-size-limit", "1"], [row])
    add("no-unicode", ["--no-unicode"], [row], pattern=rf"\b{tok}\b")
    add("absent", [], [], pattern=tok + "absent", code=1)
    add("hidden", ["--hidden"], [f"./.hidden.txt:{tok}", row])
    add("negative-glob", ["-g", "!a.txt"], [], code=1)
    add("rust-type", ["-t", "rust", "-x"], [f"./sub/c.rs:{tok}"], selection=())
    add("type-not", ["-T", "rust"], [row])
    add("custom-type", ["--type-add", "mine:*.rs", "-t", "mine", "-x"], [f"./sub/c.rs:{tok}"], selection=())
    add("iglob", ["--iglob", "*.RS", "-i", "-x"], [f"./sub/c.rs:{tok.upper()}", f"./sub/c.rs:{tok}"], selection=())
    add("glob-case", ["--glob-case-insensitive", "-x"], [f"./sub/c.rs:{tok}"], selection=("-g", "*.RS"))
    add("depth", ["--max-depth", "1", "-g", "*.rs"], [], selection=(), code=1)
    add("size", ["--max-filesize", "2"], [], code=1)
    add("no-size-limit", ["--no-max-filesize"], [row])
    add("reverse-sort", ["--sortr", "path", "-i", "-l"], ["./sub/c.rs", "./encoded.md", "./a.txt"], selection=())
    add("auto-bom", ["-E", "auto"], [f"./encoded.md:{tok} café"], selection=("-g", "*.md"))
    add("empty-encoding-auto", ["-E", " "], [f"./encoded.md:{tok} café"], selection=("-g", "*.md"))
    add("no-encoding-restores-auto", ["-E", "latin1", "--no-encoding"], [f"./encoded.md:{tok} café"],
        selection=("-g", "*.md"))
    add("json", ["--json"], [])
    add("json-only-ignored", ["--json", "-o"], [])
    add("json-count-plain", ["--json", "-c"], ["./a.txt:1"])
    add("json-files-plain", ["--json", "-l"], ["./a.txt"])
    return cases


@pytest.mark.parametrize("mode", ["scan", "local", "server"])
@pytest.mark.parametrize("case", list(_independent_option_cases("placeholder")))
def test_indexed_options_have_independent_expected_results(tmp_path, mode, case):
    from contextlib import nullcontext
    from F03_helpers import parse_json_stream

    tok = unique_token()
    text = f"before\nxx {tok} {tok}\nafter\n"
    if case == "trim":
        text = f"before\n  xx {tok} {tok} \t\nafter\n"
    files = {"a.txt": text, "b.txt": "7\n", ".hidden.txt": tok + "\n",
             "sub/c.rs": f"{tok.upper()}\n{tok}42\n{tok}\n",
             "encoded.md": ("\ufeff" + tok + " café\n").encode("utf-16-le")}
    args, expected, code = _independent_option_cases(tok)[case]
    if mode == "scan":
        root = make_tree(tmp_path / "scan" / "tree", files)
        context = nullcontext()
    else:
        context = TracedIndex(tmp_path, files, mode)
        root = context.live
        # Pattern files lie outside both trees so they are query inputs only.
        (context.pristine.parent / "patterns").write_text(f" {tok} \n\n^\\d$\n")
    (root.parent / "patterns").write_text(f" {tok} \n\n^\\d$\n")

    with context:
        r = run_trisift(["--stats", *(["--no-index"] if mode == "scan" else []), *args], cwd=root)
        assert r.code == code, r.describe()
        st = read_stats(r)
        # These modes currently use the local index even with a server ready.
        # They must still stay indexed, and all their output is checked below.
        local_modes = {"count-zero", "files-without", "files-without-no-match",
                       "passthru", "passthru-no-match"}
        allowed = ("server", "local") if mode == "server" and case in local_modes else (mode,)
        assert st["path"] in allowed, r.describe()
        answering = st["path"]

        def assert_expected(result, source):
            assert result.code == code, result.describe()
            if case not in ("json", "json-only-ignored"):
                assert result.stdout == expected, result.describe()
                return
            messages = parse_json_stream(result)
            assert [m["type"] for m in messages] == ["begin", "match", "end", "summary"]
            begin, match, end, summary = [m["data"] for m in messages]
            assert [d["path"]["text"] for d in (begin, match, end)] == ["./a.txt"] * 3
            assert match["lines"]["text"] == f"xx {tok} {tok}\n"
            assert match["line_number"] == 2
            assert match["absolute_offset"] == (0 if source == "server" else 7)
            assert [(s["start"], s["end"], s["match"]["text"]) for s in match["submatches"]] == [
                (3, 3 + len(tok), tok), (4 + len(tok), 4 + 2 * len(tok), tok)]
            assert end["binary_offset"] is None
            for stats in (end["stats"], summary["stats"]):
                assert stats["matches"] == 2 and stats["matched_lines"] == 1
                assert stats["searches_with_match"] == 1
            assert end["stats"]["searches"] == 1
            assert end["stats"]["bytes_searched"] == (0 if source == "server" else len(text.encode()))
            # FP-07.02: invocation work depends on narrowing; assert bounds,
            # and the server's specified zero, rather than equating all work.
            if source == "server":
                assert summary["stats"]["bytes_searched"] == 0
            else:
                assert len(text.encode()) <= summary["stats"]["bytes_searched"] <= len(text.encode()) + 2
            assert 1 <= summary["stats"]["searches"] <= 2, result.describe()
            raw = lf_lines(result.stdout, keepends=True)
            assert end["stats"]["bytes_printed"] == sum(map(len, raw[:2]))
            assert summary["stats"]["bytes_printed"] == sum(map(len, raw[:-1]))

        assert_expected(r, answering)
        if mode != "scan":
            scan = run_trisift(["--no-index", *args], cwd=context.pristine)
            assert_expected(scan, "scan")
            if case not in ("json", "json-only-ignored"):
                assert (r.stdout, r.code) == (scan.stdout, scan.code)
            # Existing TracedIndex puts matching twins in the live tree after
            # indexing. Exact output above rejects a disguised live scan.
