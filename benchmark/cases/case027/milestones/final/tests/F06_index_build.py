# feature: F06
"""Building the on-disk index with ``trisift index``."""

from __future__ import annotations

from _helpers import lf_lines
import os
import sys

import pytest

from _helpers import git_init, make_text_file, make_tree, run_trisift, unique_token
from F01_helpers import assert_exit, out_lines, tg
from F06_helpers import (
    BUFFER_CONFIRMATION,
    INDEX_DIR_NAME,
    INDEX_FILES,
    build_index,
    build_report,
    assert_reported_directory,
    expected_indexed_count,
    index_cmd,
)
from F07_helpers import NO_INDEX_WARNING, listing_path, read_stats

NOT_APPLIED_WARNING = "warning:"


def _files_listing(root, extra=()):
    r = tg(["--files", "--stats", "--sort", "path"] + list(extra) + ["."], cwd=root)
    assert r.code == 0, r.describe()
    return listing_path(r), out_lines(r)


def _indexed_answer(root, pattern, extra=()):
    r = tg(["--stats", "--sort", "path"] + list(extra) + [pattern, "."], cwd=root)
    st = read_stats(r)
    assert st["path"] == "local", f"not answered by the local index\n{r.describe()}"
    return r, st


# F06.T01
def test_build_reports_success_and_index_answers(tmp_path):
    toks = [unique_token() for _ in range(4)]
    root = make_tree(tmp_path / "w", {
        "a.txt": f"plain first line\n{toks[0]}\n",
        "d/b.rs": f"fn {toks[1]}() {{}}\n",
        "d/e/c.md": f"# {toks[2]}\n",
        ".hidden/h.txt": f"{toks[3]}\n",
    })
    r = run_trisift(index_cmd(root), cwd=tmp_path)
    assert_exit(r, "match")  # success status
    assert r.stdout == b"", r.describe()
    rep = build_report(r)
    assert_reported_directory(r, root / INDEX_DIR_NAME)
    assert rep["strategy"] == "external"
    assert rep["secs"] >= 0
    if sys.platform.startswith(("linux", "darwin", "win")):
        assert rep["peak"], f"no peak memory on this platform\n{r.describe()}"

    # The index answers: a file added after the build is not seen, every
    # admitted file's token is found.
    late = unique_token()
    make_tree(root, {"late.txt": f"{late} {toks[0]}\n"})
    for tok, path in zip(toks, ["./a.txt", "./d/b.rs", "./d/e/c.md", "./.hidden/h.txt"]):
        res, st = _indexed_answer(root, tok, ["--hidden"])
        assert [l.split(":", 1)[0] for l in out_lines(res)] == [path], res.describe()
    res, st = _indexed_answer(root, late)
    assert res.stdout == b"", res.describe()
    assert_exit(res, "no_match")


def _content_rules_tree(root, ign):
    git_init(root)
    make_tree(root, {
        ".gitignore": "ignored.txt\nigdir/\n",
        "a.txt": f"{ign} a\n",
        ".hid.txt": f"{ign} hid\n",
        ".hdir/x.txt": f"{ign} hx\n",
        "ignored.txt": f"{ign} ign\n",
        "igdir/y.txt": f"{ign} igy\n",
        "skipme/z.txt": f"{ign} z\n",
        "deep/er/skipme/q.txt": f"{ign} q\n",
        "deep/er/keep.txt": f"{ign} keep\n",
        "nested/inner.txt": f"{ign} inner\n",
    })
    git_init(root / "nested")


# F06.T02
def test_what_is_indexed_hidden_ignored_git_and_exclude(tmp_path):
    ign = unique_token()
    root = tmp_path / "w"
    _content_rules_tree(root, ign)
    ignored = ["ignored.txt", "igdir/"]

    build_index(root, ["--exclude", "skipme"])
    via, listing = _files_listing(root, ["--hidden"])
    assert via == "local"
    assert listing == sorted([
        "./.gitignore", "./.hdir/x.txt", "./.hid.txt", "./a.txt",
        "./deep/er/keep.txt", "./nested/inner.txt",
    ]), listing
    _, st = _indexed_answer(root, ign)
    want = expected_indexed_count(root, ignored=ignored, exclude=["skipme"])
    assert st["indexed"] == want

    build_index(root, ["--no-ignore"])
    _, st2 = _indexed_answer(root, ign)
    want2 = expected_indexed_count(root, no_ignore=True)
    git_files = sum(len(f) for d, _, f in os.walk(root) if "/.git" in d + "/" or d.endswith(".git"))
    assert git_files > 0
    # Rises by exactly the ignored files, the .git content and the files
    # under the excluded directories (no exclude this time).
    assert st2["indexed"] == want2
    assert want2 == want + 2 + 2 + git_files


# F06.T03
def test_binary_files_are_not_indexed(tmp_path):
    tok = unique_token()
    root = make_tree(tmp_path / "w", {
        "a.txt": f"{tok} a\n",
        "b.txt": f"{tok} b\n",
        "nul.txt": f"{tok}\0x\n".encode(),
        "pic.PNG": f"{tok} png\n",
        "arc.zip": f"{tok} zip\n",
    })
    build_index(root)
    want = expected_indexed_count(root)
    assert want == 2
    r, st = _indexed_answer(root, tok)
    assert st["indexed"] == want, r.describe()
    assert out_lines(r) == [f"./a.txt:{tok} a", f"./b.txt:{tok} b"]
    s = run_trisift(["status", "."], cwd=root)
    assert s.code == 0, s.describe()
    files = [l.split(":", 1)[1].strip() for l in lf_lines(s.out) if l.strip().startswith("Files:")]
    assert [int(f) for f in files] == [want], s.describe()


# F06.T04
def test_build_size_limit(tmp_path):
    tok = unique_token()
    limit = 4096
    root = tmp_path / "w"
    make_text_file(root / "at.txt", limit, tok)
    make_text_file(root / "over.txt", limit + 1, tok)
    make_text_file(root / "under.txt", 100, tok)
    build_index(root, ["--max-filesize", str(limit)])
    r, st = _indexed_answer(root, tok)
    assert [l.split(":", 1)[0] for l in out_lines(r)] == ["./at.txt", "./under.txt"], r.describe()
    assert st["indexed"] == expected_indexed_count(root, max_filesize=limit) == 2
    via, listing = _files_listing(root)
    assert via == "local"
    assert listing == ["./at.txt", "./under.txt"]

    # Live baseline: without the build limit the larger file is indexed.
    build_index(root)
    r, st = _indexed_answer(root, tok)
    assert [l.split(":", 1)[0] for l in out_lines(r)] == ["./at.txt", "./over.txt", "./under.txt"]
    build_index(root, ["--max-filesize", str(limit), "--no-max-filesize"])
    _, listing = _files_listing(root)
    assert listing == ["./at.txt", "./over.txt", "./under.txt"]


# F06.T05
def test_gitignore_outside_git_warning(tmp_path):
    tok = unique_token()
    files = {".gitignore": "ign.txt\n", "ign.txt": f"{tok} ign\n", "keep.txt": f"{tok} keep\n"}

    plain = make_tree(tmp_path / "plain", files)
    r = build_index(plain)
    warn = [l for l in lf_lines(r.err) if NOT_APPLIED_WARNING in l]
    assert len(warn) == 1, r.describe()
    assert str(plain) in warn[0] or os.path.realpath(plain) in warn[0], r.describe()
    _, listing = _files_listing(plain)
    assert "./ign.txt" in listing, listing

    r = build_index(plain, ["--no-require-git"])
    assert NOT_APPLIED_WARNING not in r.err, r.describe()
    res = tg(["--stats", tok, "."], cwd=plain)
    assert read_stats(res)["path"] == "local"
    assert sorted(out_lines(res)) == [f"./keep.txt:{tok} keep"], res.describe()

    r = build_index(plain, ["--no-ignore"])
    assert NOT_APPLIED_WARNING not in r.err, r.describe()

    repo = make_tree(tmp_path / "repo", files)
    git_init(repo)
    r = build_index(repo)
    assert NOT_APPLIED_WARNING not in r.err, r.describe()
    _, listing = _files_listing(repo)
    assert "./ign.txt" not in listing and "./keep.txt" in listing, listing


def _query_set(root, toks):
    out = {}
    for q in [toks[0], f"{toks[1]}|{toks[2]}", "\\w+_x", f"(?i){toks[0].upper()}"]:
        r = tg(["--stats", "--sort", "path", q, "."], cwd=root)
        assert read_stats(r)["path"] == "local", r.describe()
        out[q] = (r.code, r.stdout)
    r = tg(["--stats", "-c", "--sort", "path", toks[1], "."], cwd=root)
    out["count"] = (r.code, r.stdout)
    return out


# F06.T06
def test_strategies_give_identical_indexes_and_buffer_confirmation(tmp_path):
    toks = [unique_token() for _ in range(3)]
    files = {f"d{i}/f{j}.txt": f"{toks[(i + j) % 3]} w{i}_x {j}\n" for i in range(4) for j in range(5)}
    files["late_holder.txt"] = "nothing\n"
    root = make_tree(tmp_path / "w", files)
    results = {}
    for strategy in ("memory", "external"):
        r = build_index(root, ["--index-strategy", strategy])
        assert build_report(r)["strategy"] == strategy
        # Tracer added after the build: an index answer cannot see it.
        make_tree(root, {"tracer.txt": f"{toks[0]} {toks[1]} {toks[2]} w9_x\n"})
        results[strategy] = _query_set(root, toks)
        for code, out in results[strategy].values():
            assert b"tracer.txt" not in out
        os.remove(root / "tracer.txt")
    assert results["memory"] == results["external"]
    assert all(code == 0 for code, _ in results["memory"].values())

    r = build_index(root)
    assert build_report(r)["strategy"] == "external"
    assert not BUFFER_CONFIRMATION.search(r.err), r.describe()

    for mib in (8, 33):
        r = build_index(root, ["--index-buffer", str(mib)])
        conf = BUFFER_CONFIRMATION.findall(r.err)
        assert [int(n) for n in conf] == [mib], r.describe()
        r = build_index(root, ["--index-strategy", "external", "--index-buffer", str(mib)])
        assert [int(n) for n in BUFFER_CONFIRMATION.findall(r.err)] == [mib], r.describe()
        r = build_index(root, ["--index-strategy", "memory", "--index-buffer", str(mib)])
        assert not BUFFER_CONFIRMATION.search(r.err), r.describe()
        assert build_report(r)["strategy"] == "memory"


# F06.T07
def test_rebuild_reflects_current_tree(tmp_path):
    keep, gone, edited_old, edited_new, new = (unique_token() for _ in range(5))
    root = make_tree(tmp_path / "w", {
        "keep.txt": f"{keep}\n", "gone.txt": f"{gone}\n", "edit.txt": f"{edited_old}\n",
    })
    build_index(root)
    os.remove(root / "gone.txt")
    make_tree(root, {"edit.txt": f"{edited_new}\n", "new.txt": f"{new}\n"})

    # Before the rebuild the index still answers from the old tree.
    r, _ = _indexed_answer(root, new)
    assert r.stdout == b""
    r, _ = _indexed_answer(root, edited_new)
    assert r.stdout == b""

    build_index(root)
    r, _ = _indexed_answer(root, new)
    assert out_lines(r) == [f"./new.txt:{new}"]
    r, _ = _indexed_answer(root, edited_new)
    assert out_lines(r) == [f"./edit.txt:{edited_new}"]
    r, _ = _indexed_answer(root, edited_old)
    assert r.stdout == b""
    assert_exit(r, "no_match")
    r, _ = _indexed_answer(root, gone)
    assert r.stdout == b""
    assert _files_listing(root)[1] == ["./edit.txt", "./keep.txt", "./new.txt"]
    r, _ = _indexed_answer(root, keep)
    assert out_lines(r) == [f"./keep.txt:{keep}"]


# F06.T08
def test_index_directory_layout_and_missing_lookup(tmp_path):
    tok = unique_token()
    root = make_tree(tmp_path / "w", {"a.txt": f"{tok}\n"})
    build_index(root)
    idx = root / INDEX_DIR_NAME
    present = set(os.listdir(idx))
    for name in INDEX_FILES:
        assert name in present, f"{name} missing from {sorted(present)}"

    make_tree(root, {"late.txt": f"{tok} late\n"})
    os.remove(idx / "lookup.bin")
    r = tg(["--stats", "--sort", "path", tok, "."], cwd=root)
    assert read_stats(r)["path"] == "scan", r.describe()
    warn = [m for m in (NO_INDEX_WARNING.match(l) for l in lf_lines(r.err)) if m]
    assert len(warn) == 1, r.describe()
    assert_reported_directory(r, idx, warning=True)
    assert out_lines(r) == [f"./a.txt:{tok}", f"./late.txt:{tok} late"]


REFUSED = [
    ["--follow"], ["--max-depth", "1"], ["--one-file-system"], ["--ignore-file", "IGN"],
    ["--ignore-file-case-insensitive"], ["--no-ignore-dot"], ["--no-ignore-exclude"],
    ["--no-ignore-files"], ["--no-ignore-global"], ["--no-ignore-parent"], ["--no-ignore-vcs"],
]


# F06.T09
@pytest.mark.parametrize("opt", REFUSED, ids=lambda o: o[0])
def test_refused_traversal_options(tmp_path, opt):
    root = make_tree(tmp_path / "w", {"a.txt": "x\n", "IGN": "a.txt\n"})
    r = run_trisift(index_cmd(root, opt), cwd=root)
    assert_exit(r, "error")
    assert opt[0] in r.err, r.describe()
    assert not (root / INDEX_DIR_NAME / "lookup.bin").exists()


# F06.T10
def test_index_directory_containing_root_is_refused(tmp_path):
    outer = make_tree(tmp_path / "outer", {"inner/a.txt": "x\n"})
    for idx in (outer, tmp_path, outer / "inner"):
        r = run_trisift(index_cmd(outer / "inner", index_path=idx), cwd=tmp_path)
        assert_exit(r, "error")
        assert r.err.strip(), r.describe()
        assert not (idx / "lookup.bin").exists()
    # Control: a sibling index directory is accepted.
    r = run_trisift(index_cmd(outer / "inner", index_path=tmp_path / "sib"), cwd=tmp_path)
    assert_exit(r, "match")


# F06.T11
@pytest.mark.parametrize("opt", [
    ["--index-buffer", "0"], ["--index-buffer", "abc"], ["--index-buffer", "1.5"],
    ["--index-buffer", "18446744073709551615"], ["--index-strategy", "memory", "--index-buffer", "18446744073709551615"], ["--index-buffer", "99999999999999999999999"],
    ["--index-strategy", "fast"], ["--index-strategy", "Memory2"],
], ids=lambda o: "=".join(o))
def test_invalid_buffer_and_strategy(tmp_path, opt):
    root = make_tree(tmp_path / "w", {"a.txt": "x\n"})
    r = run_trisift(index_cmd(root, opt), cwd=root)
    assert_exit(r, "error")
    assert r.stdout == b"", r.describe()
    assert r.err.strip(), r.describe()
    assert not (root / INDEX_DIR_NAME / "lookup.bin").exists()


# F06.T08 regression — FP-06.01, FP-06.02, FP-06.03, FP-06.07

def test_default_root_resources_corpus_and_persisted_file_metadata(tmp_path):
    import json
    import re
    from _helpers import make_text_file
    from F06_helpers import DEFAULT_SIZE_LIMIT
    root = make_tree(tmp_path / "w", {".ignore": "ignored.txt\n", "ignored.txt": "first\nsecret\n",
        "keep.txt": "first\nvisible\n", "utf16.txt": b"\xff\xfe" + "decoded needle\n".encode("utf-16-le"),
        "one/out.txt": "excluded\n", "deep/two/out.txt": "excluded\n",
        "pic.png": "image\n", "blob.txt": b"x\0y\n"})
    make_text_file(root / "too-big.txt", DEFAULT_SIZE_LIMIT + 1, "oversize")
    r = run_trisift(["index", "--exclude", "one", "--exclude", "two"], cwd=root)
    assert_exit(r, "match")
    assert_reported_directory(r, root / INDEX_DIR_NAME)
    rep = build_report(r)
    # An independently generated nontrivial build cannot use zero resource placeholders.
    assert rep["secs"] >= 0
    assert float(re.match(r"[0-9.]+", rep["peak"])[0]) > 0
    _, paths = _files_listing(root)
    assert paths == ["./blob.txt", "./keep.txt", "./pic.png", "./utf16.txt"]
    assert out_lines(_indexed_answer(root, "needle")[0]) == ["./utf16.txt:decoded needle"]
    stamps = json.loads((root / INDEX_DIR_NAME / "filestamps.json").read_text())
    for name in ("keep.txt", "utf16.txt", ".ignore"):
        st = (root / name).stat()
        assert stamps[name]["size"] == st.st_size
        assert stamps[name]["mtime"] == int(st.st_mtime)
    for flag in ("-u", "--unrestricted", "--no-ignore"):
        build_index(root, [flag])
        assert out_lines(_indexed_answer(root, "secret")[0]) == ["./ignored.txt:secret"]
