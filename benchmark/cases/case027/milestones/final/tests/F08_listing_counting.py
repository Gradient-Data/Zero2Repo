# feature: F08
"""File listing (``--files``) and file counting (``count-files``)."""

from __future__ import annotations

from _helpers import lf_lines
import os
from contextlib import nullcontext

import pytest

from _helpers import git_init, make_sparse_file, make_tree, make_unreadable, run_trisift, unique_token
from F01_helpers import assert_exit, out_lines, tg
from F05_helpers import BINARY_EXTENSIONS
from F06_helpers import DEFAULT_SIZE_LIMIT, build_index
from F07_helpers import NoWatchServer, listing_path
from F08_helpers import MISSING_PATH, parse_count_files


def _listing_tree(root):
    return make_tree(root, {
        ".ignore": "ign.txt\nigdir/\n",
        "a.txt": "a\n",
        "nul.txt": b"x\0y\n",
        "pic.PNG": "not really\n",
        "arc.zip": "zip\n",
        "ign.txt": "ignored\n",
        "igdir/x.txt": "x\n",
        ".hid.txt": "h\n",
        "sub/b.rs": "fn b() {}\n",
        "sub/deep/c.md": "c\n",
    })


ADMITTED = ["./a.txt", "./arc.zip", "./nul.txt", "./pic.PNG", "./sub/b.rs", "./sub/deep/c.md"]


def _files(args, cwd, **kw):
    r = tg(["--files"] + list(args), cwd=cwd, **kw)
    assert r.code == 0, r.describe()
    return r


# F08.T01
def test_listing_admitted_paths_and_filters(tmp_path):
    root = _listing_tree(tmp_path / "w")
    r = _files(["--no-index", "--sort", "path", "."], root)
    assert out_lines(r) == ADMITTED, r.describe()
    r = _files(["--no-index", "."], root)
    assert sorted(out_lines(r)) == ADMITTED

    r = _files(["--no-index", "--sort", "path", "-g", "*.md", "."], root)
    assert out_lines(r) == ["./sub/deep/c.md"]
    r = _files(["--no-index", "--sort", "path", "-g", "!*.txt", "."], root)
    assert out_lines(r) == ["./arc.zip", "./pic.PNG", "./sub/b.rs", "./sub/deep/c.md"]
    r = _files(["--no-index", "--sort", "path", "-t", "rust", "."], root)
    assert out_lines(r) == ["./sub/b.rs"]
    r = _files(["--no-index", "--sort", "path", "--hidden", "."], root)
    assert out_lines(r) == sorted(ADMITTED + ["./.hid.txt", "./.ignore"])
    r = _files(["--no-index", "--sort", "path", "--max-depth", "1", "."], root)
    assert out_lines(r) == ["./a.txt", "./arc.zip", "./nul.txt", "./pic.PNG"]
    r = _files(["--no-index", "--sortr", "path", "."], root)
    assert out_lines(r) == ADMITTED[::-1]
    r = _files(["--no-index", "--sort", "path", "--null", "."], root)
    assert r.stdout == b"".join(p.encode() + b"\0" for p in ADMITTED), r.describe()
    r = _files(["--no-index", "--sort", "path", "--path-separator", "\\", "."], root)
    assert out_lines(r) == [p.replace("/", "\\") for p in ADMITTED]

    # Every positional argument is a path (no pattern), printed as typed.
    r = _files(["--no-index", "--sort", "path", "sub", "a.txt"], root)
    assert out_lines(r) == ["sub/b.rs", "sub/deep/c.md", "a.txt"], r.describe()
    r = _files(["--no-index", "--sort", "path"], root / "sub")
    assert out_lines(r) == ["b.rs", "deep/c.md"], r.describe()


# F08.T02
def test_single_file_argument(tmp_path):
    root = _listing_tree(tmp_path / "w")
    for path in ("a.txt", "./a.txt", "sub/../a.txt"):
        r = _files(["--no-index", path], root)
        assert out_lines(r) == [path], r.describe()
    r = _files(["--no-index", "-g", "*.txt", "a.txt"], root)
    assert out_lines(r) == ["a.txt"]
    r = _files(["--no-index", "-g", "*.rs", "a.txt", "sub/b.rs"], root)
    assert out_lines(r) == ["sub/b.rs"], r.describe()
    r = _files(["--no-index", "-t", "rust", "a.txt"], root)
    assert r.stdout == b"", r.describe()
    r = _files(["--no-index", "-t", "rust", "sub/b.rs"], root)
    assert out_lines(r) == ["sub/b.rs"]
    assert _files(["-T", "rust", "sub/b.rs"], root).stdout == b""
    r = _files(["--no-index", "pic.PNG"], root)
    assert out_lines(r) == ["pic.PNG"]

    # Empty inventories are successful, whether empty before or after filters,
    # and whether obtained by walking, from a snapshot, or from a server.
    empty = make_tree(tmp_path / "empty", {})
    for corpus, filters in ((empty, []), (root, ["-g", "*.never_admitted"])):
        build_index(corpus)
        for mode in ("walk", "local", "server"):
            with NoWatchServer(corpus) if mode == "server" else nullcontext():
                args = ["--stats", *filters, "."]
                if mode == "walk":
                    args.insert(0, "--no-index")
                result = _files(args, corpus)
                assert result.stdout == b"", result.describe()
                assert listing_path(result) == mode, result.describe()


# F08.T03
def test_indexed_listing(tmp_path):
    root = _listing_tree(tmp_path / "w")
    build_index(root)
    make_tree(root, {"post.txt": "post\n"})

    r = _files(["--stats", "--sort", "path", "."], root)
    assert listing_path(r) == "local", r.describe()
    assert out_lines(r) == ADMITTED, r.describe()  # binaries included, post-build file absent

    r = _files(["--stats", "--no-index", "--sort", "path", "."], root)
    assert listing_path(r) == "walk", r.describe()
    assert out_lines(r) == sorted(ADMITTED + ["./post.txt"])

    r = _files(["--stats", "--sort", "path", "--hidden", "-g", "*.txt", "."], root)
    assert listing_path(r) == "local"
    assert out_lines(r) == ["./.hid.txt", "./a.txt", "./nul.txt"]

    r = _files(["--stats", "--sort", "path", "--null", "."], root)
    assert r.stdout == b"".join(p.encode() + b"\0" for p in ADMITTED)
    r = _files(["--stats", "--max-depth", "1", "."], root)
    assert sorted(out_lines(r)) == [p for p in ADMITTED if p.count("/") == 1]
    assert listing_path(_files(["--stats", "--no-ignore-files", "."], root)) == "local"

    with NoWatchServer(root) as server:
        server.wait_reconciled()
        make_tree(root, {"post2.txt": "post2\n"})
        r = _files(["--stats", "--sort", "path", "."], root)
        assert listing_path(r) == "server", r.describe()
        lines = out_lines(r)
        assert lines == sorted(ADMITTED + ["./post.txt"]), r.describe()


WALK_FORCERS = [
    ["--no-index"], ["--no-ignore"], ["--no-ignore-dot"], ["--no-ignore-vcs"], ["--no-ignore-exclude"],
    ["--no-ignore-global"], ["--no-ignore-parent"], ["--no-require-git"], ["-L"],
    ["--follow"], ["--one-file-system"], ["--ignore-file", "IGNF"], ["--ignore-file-case-insensitive"],
    ["--max-filesize", str(DEFAULT_SIZE_LIMIT)], ["--no-max-filesize"],
]


# F08.T04
@pytest.mark.parametrize("opt", WALK_FORCERS, ids=lambda o: o[0])
def test_options_that_make_listing_walk(tmp_path, opt):
    root = make_tree(tmp_path / "w", {"a.txt": "a\n", "b/c.txt": "c\n"})
    (tmp_path / "IGNF").write_text("nomatch-at-all\n")
    build_index(root)
    make_tree(root, {"post.txt": "post\n"})
    # Live baseline: the default listing is answered by the index.
    r = _files(["--stats", "."], root)
    assert listing_path(r) == "local" and "./post.txt" not in out_lines(r)
    o = [str(tmp_path / "IGNF") if x == "IGNF" else x for x in opt]
    r = _files(["--stats"] + o + ["."], root)
    assert listing_path(r) == "walk", r.describe()
    assert "./post.txt" in out_lines(r), r.describe()


# F08.T05
def test_json_has_no_effect_on_listing(tmp_path):
    root = _listing_tree(tmp_path / "w")
    for extra in (["--no-index"], []):
        if not extra:
            build_index(root)
        a = _files(extra + ["--sort", "path", "."], root)
        b = _files(extra + ["--json", "--sort", "path", "."], root)
        assert a.stdout == b.stdout and a.stdout, b.describe()


def _count_tree(root, n_bin):
    files = {"t1.txt": "x\n", "t2.rs": "y\n", "sub/t3.md": "z\n", "nul.txt": b"a\0b\n",
             ".hid.txt": "h\n", ".ignore": "ign.txt\nigdir/\n", "ign.txt": "i\n", "igdir/q.txt": "q\n"}
    exts = BINARY_EXTENSIONS[:n_bin - 1]
    for i, ext in enumerate(exts):
        files[f"bins/f{i}.{ext}"] = "text inside\n"
    files["bins/mixed.JpEg"] = "mixed case\n"
    make_tree(root, files)
    make_sparse_file(root / "big.dat2", DEFAULT_SIZE_LIMIT + 1)
    make_sparse_file(root / "edge.dat2", DEFAULT_SIZE_LIMIT)
    return root


def _regular_files(root, hidden=False, ignored=()):
    n = 0
    for d, dirs, files in os.walk(root):
        rel = os.path.relpath(d, root)
        if not hidden:
            dirs[:] = [x for x in dirs if not x.startswith(".")]
        dirs[:] = [x for x in dirs if os.path.normpath(os.path.join(rel, x)) not in ignored]
        for f in files:
            p = os.path.normpath(os.path.join(rel, f))
            if (not hidden and f.startswith(".")) or p in ignored:
                continue
            if os.path.isfile(os.path.join(d, f)) and not os.path.islink(os.path.join(d, f)):
                n += 1
    return n


# F08.T06
def test_count_files_counts_and_skips(tmp_path):
    n_bin = len(BINARY_EXTENSIONS) + 1
    root = _count_tree(tmp_path / "w", n_bin)
    r = run_trisift(["count-files", "."], cwd=root)
    assert_exit(r, "match")
    c = parse_count_files(r)
    total = _regular_files(root, ignored={"ign.txt", "igdir"})
    assert c["binary_ext"] == n_bin, r.describe()
    assert c["too_large"] == 1, r.describe()
    assert c["admitted"] == c["stdout_count"] == total - n_bin - 1, r.describe()
    assert c["errors"] == 0

    r = run_trisift(["count-files", "--hidden", "."], cwd=root)
    c2 = parse_count_files(r)
    assert c2["stdout_count"] == c2["admitted"] == c["admitted"] + 2, r.describe()  # .hid.txt and .ignore

    for opt in (["--no-ignore"], ["-u"]):
        r = run_trisift(["count-files"] + opt + ["."], cwd=root)
        c3 = parse_count_files(r)
        assert c3["stdout_count"] == c3["admitted"] == c["admitted"] + 2, f"{opt}: {r.describe()}"
        both = parse_count_files(run_trisift(["count-files", "--hidden", *opt, "."], cwd=root))
        assert both["stdout_count"] == both["admitted"] == c["admitted"] + 4

    # With no argument the current directory is counted.
    r = run_trisift(["count-files"], cwd=root)
    assert parse_count_files(r)["admitted"] == c["admitted"]


# F08.T07
def test_count_files_symlinks_and_errors(tmp_path):
    root = make_tree(tmp_path / "w", {
        "a.txt": "a\n", "locked/in1.txt": "1\n", "locked2/in2.txt": "2\n", "unread.txt": "u\n",
        ".ignore": "igdir/\n", "igdir/z.txt": "z\n", ".hdir/h.txt": "h\n",
    })
    os.symlink("does-not-exist", root / "dangling")
    os.symlink("a.txt", root / "live")
    os.symlink("locked", root / "dirlink")

    r = run_trisift(["count-files", "."], cwd=root)
    base = parse_count_files(r)
    assert base["admitted"] == 4 and base["errors"] == 0, r.describe()  # a, unread, in1, in2

    with make_unreadable(root / "locked"), make_unreadable(root / "locked2"), make_unreadable(root / "unread.txt"), \
            make_unreadable(root / "igdir"), make_unreadable(root / ".hdir"):
        r = run_trisift(["count-files", "."], cwd=root)
        assert_exit(r, "match")
        c = parse_count_files(r)
        assert c["errors"] == 2, r.describe()
        assert c["admitted"] == c["stdout_count"] == 2, r.describe()  # a.txt and unread.txt

    lone = make_tree(tmp_path / "lone", {"x.txt": "x\n"})
    with make_unreadable(lone):
        r = run_trisift(["count-files", str(lone)], cwd=tmp_path)
        assert_exit(r, "match")
        c = parse_count_files(r)
        assert (c["errors"], c["admitted"], c["stdout_count"]) == (1, 0, 0), r.describe()


# F08.T08
def test_listing_reports_missing_path_and_lists_others(tmp_path):
    root = _listing_tree(tmp_path / "w")
    missing = unique_token("nope")
    for extra in (["--no-index"], []):
        r = tg(["--files"] + extra + ["a.txt", missing, "sub"], cwd=root)
        assert r.code == 0, r.describe()
        reported = [m.group("path") for m in (MISSING_PATH.match(l) for l in lf_lines(r.err)) if m]
        assert reported == [missing], r.describe()
        assert sorted(out_lines(r)) == ["a.txt", "sub/b.rs", "sub/deep/c.md"], r.describe()


# F08.T09
def test_count_files_missing_root_is_error(tmp_path):
    r = run_trisift(["count-files", str(tmp_path / unique_token("gone"))], cwd=tmp_path)
    assert_exit(r, "error")
    assert r.err.strip(), r.describe()


# F08.T04 regression — FP-08.01, FP-08.03

def test_listing_traversal_flags_change_admission(tmp_path):
    root = make_tree(tmp_path / "w", {".ignore": "omit.txt\nCASE.txt\n", "omit.txt": "o\n", "keep.txt": "k\n",
                                   "case.txt": "c\n", "large.txt": "z" * 200})
    other = make_tree(tmp_path / "outside", {"linked.txt": "l\n"})
    (root / "link").symlink_to(other, target_is_directory=True)
    rules = tmp_path / "rules"
    rules.write_text("keep.txt\n")
    index = root / "storage"
    build_index(root, index_path=index)
    base = ["--index-path", str(index), "--stats", "--sort", "path"]
    regular = ["./case.txt", "./keep.txt", "./large.txt"]
    cases = [(["--no-ignore"], regular + ["./omit.txt"]),
             (["--no-ignore-dot"], regular + ["./omit.txt"]),
             (["--ignore-file", str(rules)], ["./case.txt", "./large.txt"]),
             (["--ignore-file-case-insensitive"], ["./keep.txt", "./large.txt"]),
             (["--follow"], regular + ["./link/linked.txt"]),
             (["--max-filesize", "20"], ["./case.txt", "./keep.txt"])]
    for opts, want in cases:
        r = _files([*base, *opts, "."], root)
        assert listing_path(r) == "walk"
        assert out_lines(r) == sorted(want)
    r = _files([*base, "--no-index", "--hidden", "."], root)
    assert not any("storage/" in p for p in out_lines(r))


# F08.T03 regression — FP-08.03

def test_server_listing_uses_refreshed_live_corpus(tmp_path):
    from F09_helpers import ServerProcess, wait_ready, wait_reflected, rpc_files
    root = make_tree(tmp_path / "w", {"before.txt": "before\n"})
    build_index(root)
    with ServerProcess(root, []) as srv:
        wait_ready(srv)
        make_tree(root, {"new.txt": "new\n"})
        wait_reflected(lambda: "new.txt" in rpc_files(srv.port), timeout=60,
                       what="server listing addition", server=srv)
        r = _files(["--stats", "--sort", "path", "."], root)
        assert listing_path(r) == "server"
        assert out_lines(r) == ["./before.txt", "./new.txt"]


# F08.T06 regression — FP-08.05

def test_count_uses_git_nested_wildcard_and_negation_rules(tmp_path):
    from _helpers import hermetic_env
    root = make_tree(tmp_path / "w", {".gitignore": "*.log\n!keep.log\n", "bad.log": "x\n",
        "keep.log": "x\n", "good.txt": "x\n", "sub/.ignore": "*.tmp\n",
        "sub/bad.tmp": "x\n", "sub/good.txt": "x\n"})
    env = hermetic_env(tmp_path / "home")
    git_init(root, env=env)
    r = run_trisift(["count-files", "."], cwd=root, env=env)
    assert r.code == 0
    c = parse_count_files(r)
    assert c["stdout_count"] == c["admitted"] == 3 and c["errors"] == 0
