# feature: F04
"""File selection: types, depth, size limits, bad values, malformed ignore rules."""

from __future__ import annotations

import pytest

from _helpers import make_text_file, make_tree, unique_token
from F01_helpers import assert_exit, out_lines
from F04_helpers import (
    DEFAULT_MAX_FILESIZE,
    Selection,
    ignore_reports,
    parse_type_list,
)


def _sel(tmp_path, cwd=None):
    tok = unique_token()
    return Selection(cwd or tmp_path, tok, tmp_path / "home"), f"{tok}\n"


def _typed_tree(tmp_path, body):
    names = ["a.rs", "b.py", "c.js", "d.c", "e.cpp", "f.h", "g.txt", "deep/h.rs", "k.foo", "k.bar",
             "rs/plain.txt", "sx.txt"]
    make_tree(tmp_path / "w", {name: body for name in names})
    return sorted(f"w/{n}" for n in names)


# F04.T09
def test_type_filters(tmp_path):
    sel, body = _sel(tmp_path)
    every = _typed_tree(tmp_path, body)

    assert sel.files("-t", "rust", "w") == ["w/a.rs", "w/deep/h.rs"]
    assert sel.files("--type", "py", "w") == ["w/b.py"]
    assert sel.files("-t", "python", "w") == ["w/b.py"]
    assert sel.files("-t", "js", "w") == ["w/c.js"]
    assert sel.files("-t", "c", "w") == ["w/d.c", "w/f.h"]
    assert sel.files("-t", "cpp", "w") == ["w/e.cpp", "w/f.h"]
    assert sel.files("-g", "*", "-t", "rust", "w") == ["w/a.rs", "w/deep/h.rs"]
    # Repeated uses combine.
    assert sel.files("-t", "rust", "-t", "py", "w") == ["w/a.rs", "w/b.py", "w/deep/h.rs"]
    # Type-not excludes, and takes precedence over type in either order.
    for flag in ("-T", "--type-not"):
        assert sel.files(flag, "rust", "w") == [p for p in every if not p.endswith(".rs")]
    assert sel.files("-t", "rust", "-t", "py", "-T", "py", "w") == ["w/a.rs", "w/deep/h.rs"]
    assert sel.files("-T", "py", "-t", "py", "-t", "rust", "w") == ["w/a.rs", "w/deep/h.rs"]
    assert sel.files("-t", "rust", "-T", "rust", "w", expect="no_match") == []

    # A type's globs match the file name only, wherever the file is.
    assert sel.files("--type-add", "q:h*", "-t", "q", "w") == ["w/deep/h.rs"]
    assert sel.files("--type-add", "q:s*", "-t", "q", "w") == ["w/sx.txt"]
    assert sel.files("--type-add", "q:rs", "-t", "q", "w", expect="no_match") == []


# F04.T10
def test_type_add_and_type_clear(tmp_path):
    sel, body = _sel(tmp_path)
    _typed_tree(tmp_path, body)

    assert sel.files("--type-add", "mine:*.foo", "-t", "mine", "w") == ["w/k.foo"]
    assert sel.files("--type-add", "mine:*.foo", "--type-add", "mine:*.bar", "-t", "mine", "w") == [
        "w/k.bar", "w/k.foo"]
    # Adding to a built-in type extends it.
    assert sel.files("--type-add", "rust:*.foo", "-t", "rust", "w") == ["w/a.rs", "w/deep/h.rs", "w/k.foo"]

    # include: copies the globs the named types have at that point.
    assert sel.files("--type-add", "mine:*.foo", "--type-add", "both:include:mine,rust",
                     "-t", "both", "w") == ["w/a.rs", "w/deep/h.rs", "w/k.foo"]
    late = ["--type-add", "mine:*.foo", "--type-add", "both:include:mine", "--type-add", "mine:*.bar"]
    assert sel.files(*late, "-t", "both", "w") == ["w/k.foo"]
    assert sel.files(*late, "-t", "mine", "w") == ["w/k.bar", "w/k.foo"]

    for opts in (["--type-add", "both:include:rust", "--type-clear", "rust"],
                 ["--type-clear", "rust", "--type-add", "both:include:rust"]):
        assert_exit(sel.run([*opts, sel.token, "w"]), "error")
    # type-clear removes a type's definitions.
    r = sel.run(["-l", "--type-clear", "rust", "-t", "rust", sel.token, "w"])
    assert_exit(r, "error")
    assert r.stdout == b""
    assert sel.files("--type-clear", "rust", "--type-add", "rust:*.foo", "-t", "rust", "w") == ["w/k.foo"]
    assert sel.files("--type-clear", "rust", "-t", "py", "w") == ["w/b.py"]


# F04.T11
def test_type_list(tmp_path):
    sel, body = _sel(tmp_path)
    _typed_tree(tmp_path, body)

    r = sel.run(["--type-list"])
    assert r.code == 0, r.describe()
    rows = parse_type_list(r)
    names = [name for name, _ in rows]
    assert names == sorted(names) and len(names) == len(set(names))
    listed = {name: sorted(globs) for name, globs in rows}
    # The built-in types the PRD names are listed, each alias on its own line.
    missing = sorted({"rust", "py", "python", "js", "c", "cpp"} - set(listed))
    assert not missing, f"built-in types missing from the listing: {missing}"
    assert all(listed[name] and all(listed[name]) for name in listed)

    # It does not search, even when given a pattern and a path that would match.
    again = sel.run(["--type-list", sel.token, "w"])
    assert again.code == 0, again.describe()
    assert {n: sorted(g) for n, g in parse_type_list(again)} == listed

    # The listing reflects type-add and type-clear.
    custom = unique_token("zz")
    r2 = sel.run(["--type-list", "--type-add", f"{custom}:*.foo", "--type-add", f"{custom}:*.q",
                  "--type-add", "rust:*.extra", "--type-clear", "py"])
    assert r2.code == 0, r2.describe()
    rows2 = parse_type_list(r2)
    names2 = [name for name, _ in rows2]
    assert names2 == sorted(names2)
    listed2 = {name: sorted(globs) for name, globs in rows2}
    # Measured against the product's own built-in listing above.
    expected = {n: g for n, g in listed.items() if n != "py"}
    expected[custom] = ["*.foo", "*.q"]
    expected["rust"] = sorted([*listed["rust"], "*.extra"])
    assert listed2 == expected
    assert "python" in listed2          # clearing one name leaves its alias


# F04.T12
def test_max_depth(tmp_path):
    sel, body = _sel(tmp_path)
    make_tree(tmp_path / "w", {
        "r.txt": body, "l1/a.txt": body, "l1/l2/b.txt": body, "l1/l2/l3/c.txt": body, "m1/d.txt": body})
    assert sel.files("--max-depth", "1", "w") == ["w/r.txt"]
    assert sel.files("--max-depth", "2", "w") == ["w/l1/a.txt", "w/m1/d.txt", "w/r.txt"]
    assert sel.files("--max-depth", "3", "w") == ["w/l1/a.txt", "w/l1/l2/b.txt", "w/m1/d.txt", "w/r.txt"]
    assert sel.files("--max-depth=4", "w") == [
        "w/l1/a.txt", "w/l1/l2/b.txt", "w/l1/l2/l3/c.txt", "w/m1/d.txt", "w/r.txt"]
    # The depth is counted from each search root.
    assert sel.files("--max-depth", "1", "w/l1") == ["w/l1/a.txt"]


@pytest.fixture(scope="module")
def big_files(tmp_path_factory):
    """Real (non-sparse, NUL-free) text files around the default size cap."""
    base = tmp_path_factory.mktemp("bigfiles")
    tok = unique_token()
    make_text_file(base / "w" / "at_cap.txt", DEFAULT_MAX_FILESIZE, tok)
    make_text_file(base / "w" / "over_cap.txt", DEFAULT_MAX_FILESIZE + 1, tok)
    make_text_file(base / "w" / "small.txt", 4096, tok)
    return base, Selection(base, tok, base / "home")


# F04.T13
def test_default_size_cap(big_files):
    base, sel = big_files
    # Walked: exactly 64 MiB is searched, one byte more is skipped.
    assert sel.files("w") == ["w/at_cap.txt", "w/small.txt"]
    # Named explicitly: searched whatever its size.
    assert sel.files("w/over_cap.txt") == ["w/over_cap.txt"]
    assert sel.files("w/over_cap.txt", "w") == ["w/at_cap.txt", "w/over_cap.txt", "w/small.txt"]


# F04.T14
def test_max_filesize_options(tmp_path, big_files):
    sel, body = _sel(tmp_path)
    tok = sel.token
    make_text_file(tmp_path / "w" / "k_at.txt", 3 * 1024, tok)
    make_text_file(tmp_path / "w" / "k_over.txt", 3 * 1024 + 1, tok)
    make_text_file(tmp_path / "w" / "m_at.txt", 1024 * 1024, tok)
    make_text_file(tmp_path / "w" / "m_over.txt", 1024 * 1024 + 1, tok)
    make_text_file(tmp_path / "w" / "tiny.txt", 100, tok)
    every = ["w/k_at.txt", "w/k_over.txt", "w/m_at.txt", "w/m_over.txt", "w/tiny.txt"]

    assert sel.files("w") == every
    assert sel.files("--max-filesize", "3K", "w") == ["w/k_at.txt", "w/tiny.txt"]
    assert sel.files("--max-filesize", "3072", "w") == ["w/k_at.txt", "w/tiny.txt"]
    assert sel.files("--max-filesize", "3073", "w") == ["w/k_at.txt", "w/k_over.txt", "w/tiny.txt"]
    assert sel.files("--max-filesize", "1M", "w") == ["w/k_at.txt", "w/k_over.txt", "w/m_at.txt", "w/tiny.txt"]
    assert sel.files("--max-filesize", "1024K", "w") == [
        "w/k_at.txt", "w/k_over.txt", "w/m_at.txt", "w/tiny.txt"]
    assert sel.files("--max-filesize", "100", "w") == ["w/tiny.txt"]
    assert sel.files("--max-filesize", "99", "w", expect="no_match") == []

    # An explicitly given limit applies to a file named explicitly too.
    assert sel.files("--max-filesize", "3K", "w/k_over.txt", expect="no_match") == []
    assert sel.files("--max-filesize", "3K", "w/k_at.txt") == ["w/k_at.txt"]
    assert sel.files("w/k_over.txt") == ["w/k_over.txt"]

    # The later of max-filesize / no-max-filesize wins.
    assert sel.files("--max-filesize", "3K", "--no-max-filesize", "w") == every
    assert sel.files("--no-max-filesize", "--max-filesize", "3K", "w") == ["w/k_at.txt", "w/tiny.txt"]

    # Limits above and without the default: the file over 64 MiB is searched.
    base, big = big_files
    over = ["w/at_cap.txt", "w/over_cap.txt", "w/small.txt"]
    assert big.files("--no-max-filesize", "w") == over
    assert big.files("--max-filesize", "1G", "w") == over
    assert big.files("--max-filesize", "65M", "w") == over
    assert big.files("--max-filesize", "64M", "w") == ["w/at_cap.txt", "w/small.txt"]
    assert big.files("--max-filesize", "64M", "w/over_cap.txt", expect="no_match") == []


# F04.T16
@pytest.mark.parametrize("args", [
    ["-t", "notatype"],
    ["--type", "notatype"],
    ["-T", "notatype"],
    ["--type-not", "notatype"],
    ["-t", "rust", "-T", "notatype"],
    ["--type-add", "nocolon"],
    ["--type-add", ":*.x"],
    ["--type-add", "name:"],
    ["--type-add", "name:include:notatype"],
    ["--type-add", "name:include:rust,notatype"],
    ["--type-add", "name:include:"],
])
def test_bad_type_arguments_are_errors(tmp_path, args):
    sel, body = _sel(tmp_path)
    make_tree(tmp_path / "w", {"a.rs": body, "b.txt": body})
    # Live baseline: the search itself matches.
    assert sel.files("w") == ["w/a.rs", "w/b.txt"]
    r = sel.run([*args, sel.token, "w"])
    assert_exit(r, "error")
    assert r.stdout == b""
    assert r.stderr.strip() != b"", r.describe()


# F04.T17
@pytest.mark.parametrize("value", ["abc", "1X", "1.5K", "K", "", "10KB", "-5", "3 Q"])
def test_malformed_max_filesize_is_rejected(tmp_path, value):
    sel, body = _sel(tmp_path)
    make_tree(tmp_path / "w", {"a.txt": body})
    assert sel.files("w") == ["w/a.txt"]
    for paths in (["w"], ["w/a.txt"]):
        r = sel.run(["--max-filesize", value, sel.token, *paths])
        assert_exit(r, "error")
        assert r.stdout == b""
        assert r.stderr.strip() != b"", r.describe()


BAD_RULES = (
    "# comment\n"            # 1
    "\n"                     # 2
    "[z-a].txt\n"            # 3  reversed bracket range
    "*.skipme\n"             # 4  good
    "{{left,open\n"          # 5  `{` never closed   (doubled for str.format)
    "right}}close\n"         # 6  `}` never opened
    "trailing\\\n"           # 7  lone backslash at the very end
    "[abc\n"                 # 8  unclosed bracket alone: not malformed
    "!{{neg\n"               # 9  malformed after the leading `!`
    "[{{]ok.x\n"             # 10 brace inside a bracket expression: fine
    "*.also\n"               # 11 good
).format()
BAD_LINES = [3, 5, 6, 7, 9]


def _bad_rule_tree(tmp_path, body, where):
    make_tree(tmp_path / "w", {
        "keep.txt": body, "a.skipme": body, "sub/b.also": body, "sub/keep2.txt": body})
    if where == "walk":
        make_tree(tmp_path / "w", {".ignore": BAD_RULES})
        return str(tmp_path / "w" / ".ignore"), []
    name = unique_token("rules")
    make_tree(tmp_path, {name: BAD_RULES})
    return name, ["--ignore-file", name]


# F04.T18
def test_malformed_rules_in_a_walked_ignore_file(tmp_path):
    sel, body = _sel(tmp_path)
    _bad_rule_tree(tmp_path, body, "walk")

    r = sel.run(["-l", sel.token, "w"])
    # The search's own status: a match.
    assert_exit(r, "match")
    # The good rules of the same file still exclude.
    assert sorted(out_lines(r)) == ["w/keep.txt", "w/sub/keep2.txt"]
    reports = ignore_reports(r)
    assert sorted(line for _, line in reports) == BAD_LINES, r.describe()
    assert all(path.endswith(".ignore") for path, _ in reports), r.describe()

    # The search's own status: no match, with the same reports.
    r = sel.run(["-l", unique_token(), "w"])
    assert_exit(r, "no_match")
    assert r.stdout == b""
    assert sorted(line for _, line in ignore_reports(r)) == BAD_LINES, r.describe()

    # A file with only well-formed rules (and an unclosed bracket) reports nothing.
    make_tree(tmp_path / "w", {".ignore": "*.skipme\n[abc\n*.also\n"})
    r = sel.run(["-l", sel.token, "w"])
    assert_exit(r, "match")
    assert sorted(out_lines(r)) == ["w/keep.txt", "w/sub/keep2.txt"]
    assert ignore_reports(r) == [], r.describe()


# F04.T19
def test_malformed_rules_in_an_ignore_file_option_and_suppression(tmp_path):
    sel, body = _sel(tmp_path)
    name, opts = _bad_rule_tree(tmp_path, body, "option")
    kept = ["w/keep.txt", "w/sub/keep2.txt"]

    r = sel.run(["-l", *opts, sel.token, "w"])
    assert_exit(r, "match")
    assert sorted(out_lines(r)) == kept
    reports = ignore_reports(r)
    assert sorted(line for _, line in reports) == BAD_LINES, r.describe()
    assert all(path.endswith(name) for path, _ in reports), r.describe()

    for quiet in ("--no-ignore-messages", "--no-messages"):
        r = sel.run(["-l", *opts, quiet, sel.token, "w"])
        assert_exit(r, "match")
        # The remaining rules still apply.
        assert sorted(out_lines(r)) == kept
        assert ignore_reports(r) == [], r.describe()
        assert name not in r.err, r.describe()

    # The same suppression for an ignore file found during the walk.
    make_tree(tmp_path / "w", {".ignore": BAD_RULES})
    r = sel.run(["-l", sel.token, "w"])
    assert sorted(line for _, line in ignore_reports(r)) == BAD_LINES, r.describe()
    for quiet in ("--no-ignore-messages", "--no-messages"):
        r = sel.run(["-l", quiet, sel.token, "w"])
        assert_exit(r, "match")
        assert sorted(out_lines(r)) == kept
        assert ignore_reports(r) == [], r.describe()


# F04.T09 regression — FP-04.06, FP-04.07, FP-04.09, FP-04.10, FP-04.14

def test_filters_plain_output_more_types_and_nested_diagnostics(tmp_path):
    from _helpers import make_sparse_file
    sel, body = _sel(tmp_path)
    files = {"a.go": body, "b.toml": body, "c.java": body, "d.sh": body, "deep/e.go": body,
             "large.go": body * 30, "plain.txt": body}
    make_tree(tmp_path / "w", files)
    for kind, name in (("go", "a.go"), ("toml", "b.toml"), ("java", "c.java"), ("sh", "d.sh")):
        r = sel.run(["--max-depth", "1", "--max-filesize", str(len(body)), "-t", kind,
                     "-g", "*", sel.token, "w"])
        assert_exit(r, "match")
        assert out_lines(r) == [f"w/{name}:{sel.token}"]
    make_tree(tmp_path / "w/deep", {".ignore": "[z-a]\n*.go\n"})
    r = sel.run([sel.token, "w"])
    assert any(path.endswith("deep/.ignore") and line == 1 for path, line in ignore_reports(r))
    assert "w/deep/e.go:" not in r.out
    make_sparse_file(tmp_path / "sparse/inside.txt", 1_020_000_000)
    make_sparse_file(tmp_path / "sparse/outside.txt", 1_073_741_825)
    r = sel.run(["--files", "--max-filesize", "1G", "sparse"])
    assert r.code == 0 and out_lines(r) == ["sparse/inside.txt"]
