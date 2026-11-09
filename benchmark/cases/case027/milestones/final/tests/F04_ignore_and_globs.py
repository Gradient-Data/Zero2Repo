# feature: F04
"""File selection: ignore sources, hidden files, unrestricted levels, globs."""

from __future__ import annotations

import pytest

from _helpers import git_add, git_init, make_tree, unique_token
from F01_helpers import assert_exit, out_lines
from F04_helpers import Selection


def _sel(tmp_path, cwd=None):
    tok = unique_token()
    return Selection(cwd or tmp_path, tok, tmp_path / "home"), f"{tok}\n"


# F04.T01
def test_gitignore_needs_a_repository_and_dot_ignore_overrides_it(tmp_path):
    sel, body = _sel(tmp_path)
    files = {
        "keep.txt": body,
        "by_git.log": body,       # excluded by .gitignore
        "back.log": body,         # excluded by .gitignore, re-admitted by .ignore
        "by_dot.tmp": body,       # excluded by .ignore
        "sub/deep.log": body,
        "sub/deep.tmp": body,
        ".gitignore": "*.log\n",
        ".ignore": "*.tmp\n!back.log\n",
    }
    make_tree(tmp_path / "plain", files)
    make_tree(tmp_path / "repo", files)
    git_init(tmp_path / "repo")

    # Outside a repository .gitignore is not applied; .ignore is.
    assert sel.files("plain") == [
        "plain/back.log", "plain/by_git.log", "plain/keep.txt", "plain/sub/deep.log"]
    assert sel.files("--no-require-git", "plain") == ["plain/back.log", "plain/keep.txt"]
    # Inside a repository both apply, and the `!` rule of .ignore wins.
    assert sel.files("repo") == ["repo/back.log", "repo/keep.txt"]
    # A repository found in an ancestor of the search root counts too.
    assert sel.files("repo/sub", expect="no_match") == []
    assert sel.files("plain/sub") == ["plain/sub/deep.log"]


# F04.T02
def test_exclude_global_parent_and_p4ignore_sources(tmp_path):
    sel, body = _sel(tmp_path)
    home = tmp_path / "home"
    make_tree(home, {
        ".gitconfig": f"[core]\n\texcludesFile = {home}/global-ignore\n",
        "global-ignore": "*.glb\n",
    })
    repo = make_tree(tmp_path / "outer" / "repo", {
        "keep.txt": body, "a.exc": body, "a.glb": body, "a.par": body, "sub/b.exc": body,
    })
    git_init(repo)
    make_tree(repo, {".git/info/exclude": "*.exc\n"})
    make_tree(tmp_path / "outer", {".ignore": "*.par\n"})

    assert sel.files("repo", cwd=tmp_path / "outer") == ["repo/keep.txt"]
    # Live baseline per source: lifting that source alone brings its file back.
    assert sel.files("--no-ignore-exclude", "repo", cwd=tmp_path / "outer") == [
        "repo/a.exc", "repo/keep.txt", "repo/sub/b.exc"]
    assert sel.files("--no-ignore-global", "repo", cwd=tmp_path / "outer") == [
        "repo/a.glb", "repo/keep.txt"]
    assert sel.files("--no-ignore-parent", "repo", cwd=tmp_path / "outer") == [
        "repo/a.par", "repo/keep.txt"]

    # p4ignore.ini in the root, with either separator.
    make_tree(tmp_path / "p4", {
        "p4ignore.ini": "one\\two\\back.txt\nthree/four/fwd.txt\n",
        "one/two/back.txt": body, "one/two/stay.txt": body,
        "three/four/fwd.txt": body, "three/four/stay.txt": body,
    })
    assert sel.files("p4") == ["p4/one/two/stay.txt", "p4/three/four/stay.txt"]
    assert sel.files("--no-ignore", "p4") == [
        "p4/one/two/back.txt", "p4/one/two/stay.txt",
        "p4/three/four/fwd.txt", "p4/three/four/stay.txt"]


# F04.T03
def test_ignore_file_options(tmp_path):
    sel, body = _sel(tmp_path)
    make_tree(tmp_path, {
        "w/a.aa": body, "w/b.bb": body, "w/k.txt": body, "w/sub/c.aa": body,
        "rules1": "*.aa\n*.bb\n", "rules2": "!*.bb\n", "rules3": "*.bb\n",
    })
    everything = ["w/a.aa", "w/b.bb", "w/k.txt", "w/sub/c.aa"]
    assert sel.files("w") == everything
    assert sel.files("--ignore-file", "rules1", "w") == ["w/k.txt"]
    # Later files take precedence.
    assert sel.files("--ignore-file", "rules1", "--ignore-file", "rules2", "w") == ["w/b.bb", "w/k.txt"]
    assert sel.files("--ignore-file", "rules2", "--ignore-file", "rules3", "w") == [
        "w/a.aa", "w/k.txt", "w/sub/c.aa"]

    # Case-insensitive matching of ignore-file rules.
    make_tree(tmp_path / "ci", {
        ".ignore": "*.zz\nUPPER/\n", "low.zz": body, "HIGH.ZZ": body, "Mixed.Zz": body,
        "upper/in.txt": body, "k.txt": body,
    })
    assert sel.files("ci") == ["ci/HIGH.ZZ", "ci/Mixed.Zz", "ci/k.txt", "ci/upper/in.txt"]
    assert sel.files("--ignore-file-case-insensitive", "ci") == ["ci/k.txt"]
    make_tree(tmp_path, {"explicit": "*.AA\n"})
    assert sel.files("--ignore-file-case-insensitive", "--ignore-file", "explicit", "w") == everything


SOURCES = {
    "--no-ignore-dot": "f.dot",
    "--no-ignore-vcs": "f.vcs",
    "--no-ignore-exclude": "f.exc",
    "--no-ignore-global": "f.glb",
    "--no-ignore-parent": "f.par",
    "--no-ignore-files": "f.fil",
}


def _all_sources(tmp_path):
    sel, body = _sel(tmp_path, tmp_path / "outer")
    home = tmp_path / "home"
    make_tree(home, {
        ".gitconfig": f"[core]\n\texcludesFile = {home}/global-ignore\n",
        "global-ignore": "*.glb\n",
    })
    repo = make_tree(tmp_path / "outer" / "repo", {
        **{name: body for name in SOURCES.values()},
        "f.keep": body,
        ".ignore": "*.dot\n",
        ".gitignore": "*.vcs\n",
    })
    git_init(repo)
    make_tree(repo, {".git/info/exclude": "*.exc\n"})
    make_tree(tmp_path / "outer", {".ignore": "*.par\n"})
    make_tree(tmp_path, {"extra-rules": "*.fil\n"})
    return sel, str(tmp_path / "extra-rules")


# F04.T04
def test_disabling_ignore_sources(tmp_path):
    sel, rules = _all_sources(tmp_path)

    # Every source active: only the unignored file.
    assert sel.files("--ignore-file", rules, "repo") == ["repo/f.keep"]

    # Each single-source option brings back its own source's file and no other.
    for flag, name in SOURCES.items():
        got = sel.files("--ignore-file", rules, flag, "repo")
        expected = ["repo/f.keep", f"repo/{name}"]
        if flag == "--no-ignore-dot":
            expected.append("repo/f.par")
        assert got == sorted(expected), flag

    # No-ignore disables the sources found on disk and in git configuration.
    found = sorted(f"repo/{n}" for n in [*SOURCES.values(), "f.keep"])
    assert sel.files("--no-ignore", "repo") == found
    assert sel.files("--no-ignore", "--ignore-file", rules, "repo") == [p for p in found if p != "repo/f.fil"]
    assert sel.files("--no-ignore", "--ignore-file", rules, "--no-ignore-files", "repo") == found


# F04.T05
def test_core_ignorecase_adds_a_case_insensitive_pass(tmp_path):
    sel, body = _sel(tmp_path)
    repo = make_tree(tmp_path / "repo", {
        ".gitignore": "build/\n*.gen\n",
        "Build/loose.txt": body,
        "Build/tracked.txt": body,
        "OUT/o.txt": body,
        "data.GEN": body,
        "kept.GEN": body,
        "nested/.gitignore": "low.txt\n",
        "nested/LOW.txt": body,
        "nested/low.txt": body,
        "plain.txt": body,
    })
    git_init(repo)
    make_tree(repo, {".git/info/exclude": "out/\n"})
    git_add(repo, ["Build/tracked.txt", "kept.GEN"], force=True)

    # Live baseline: without core.ignorecase the differently-cased paths are admitted.
    baseline = [
        "repo/Build/loose.txt", "repo/Build/tracked.txt", "repo/OUT/o.txt", "repo/data.GEN",
        "repo/kept.GEN", "repo/nested/LOW.txt", "repo/plain.txt"]
    assert sel.files("repo") == baseline

    git_init(repo, {"core.ignorecase": "true"})
    # Root .gitignore and info/exclude now also exclude case-insensitive matches,
    # except paths git tracks; the nested .gitignore gets no such pass.
    assert sel.files("repo") == [
        "repo/Build/tracked.txt", "repo/kept.GEN", "repo/nested/LOW.txt", "repo/plain.txt"]
    assert sel.files("repo/Build") == ["repo/Build/tracked.txt"]
    # No-ignore disables the pass (and the rules themselves).
    assert sel.files("--no-ignore", "repo") == sorted([*baseline, "repo/nested/low.txt"])

    git_init(repo, {"core.ignorecase": "false"})
    assert sel.files("repo") == baseline


# F04.T06
def test_hidden_files(tmp_path):
    sel, body = _sel(tmp_path)
    make_tree(tmp_path / "w", {
        ".dotfile.txt": body,
        ".hd/in.txt": body,
        ".hd/.deeper/x.txt": body,
        "vis/v.txt": body,
        "vis/.inner.txt": body,
        "vis/skipped.zz": body,
        ".hd/skipped.zz": body,
        ".ignore": "*.zz\n",
    })
    assert sel.files("w") == ["w/vis/v.txt"]
    for flag in ("--hidden", "-."):
        # Hidden shows dot-names but never lifts ignore rules.
        assert sel.files(flag, "w") == [
            "w/.dotfile.txt", "w/.hd/.deeper/x.txt", "w/.hd/in.txt", "w/vis/.inner.txt", "w/vis/v.txt"]
    # Hiddenness is relative to the search root.
    assert sel.files("w/.hd") == ["w/.hd/in.txt"]
    assert sel.files(".", cwd=tmp_path / "w" / ".hd") == ["./in.txt"]
    # A file named explicitly is searched even when hidden.
    assert sel.files("w/.dotfile.txt") == ["w/.dotfile.txt"]
    assert sel.files("w/.hd/.deeper/x.txt", "w/vis") == ["w/.hd/.deeper/x.txt", "w/vis/v.txt"]


# F04.T07
def test_unrestricted_levels(tmp_path):
    sel, body = _sel(tmp_path)
    tok = sel.token
    make_tree(tmp_path / "w", {
        "plain.txt": body,
        "ignored.zz": body,
        ".hidden.txt": body,
        ".hd/ignored.zz": body,
        "blob.txt": f"{tok}\0tail\n".encode(),
        ".ignore": "*.zz\n",
    })
    paths = ["w/plain.txt", "w/ignored.zz", "w/.hidden.txt", "w/.hd/ignored.zz", "w/blob.txt"]

    def shown(*flags):
        r = sel.run(["--sort", "path", *flags, tok, "w"])
        assert_exit(r, "match")
        lines = out_lines(r)
        got = set()
        for line in lines:
            owners = [p for p in paths if line.startswith(p + ":")]
            assert len(owners) == 1, r.describe()
            got.add(owners[0])
        assert len(lines) == len(got), r.describe()
        return sorted(got)

    assert shown() == ["w/plain.txt"]
    for flags in (["-u"], ["--unrestricted"]):
        assert shown(*flags) == ["w/ignored.zz", "w/plain.txt"]
    for flags in (["-uu"], ["-u", "-u"], ["--unrestricted", "--unrestricted"]):
        assert shown(*flags) == ["w/.hd/ignored.zz", "w/.hidden.txt", "w/ignored.zz", "w/plain.txt"]
    for flags in (["-uuu"], ["-u", "-u", "-u"]):
        # The walked binary file is now reported, by one line carrying its path.
        assert shown(*flags) == sorted(paths)
        from F05_helpers import notes_in
        report = sel.run([*flags, tok, "w"])
        assert notes_in(report) == [("w/blob.txt", len(tok))]
        assert b"\0" not in report.stdout


# F04.T08
def test_globs(tmp_path):
    sel, body = _sel(tmp_path)
    make_tree(tmp_path / "a" / "b", {
        "sub/x.txt": body,
        "sub/x.md": body,
        "other/sub/y.txt": body,
        "other/o.txt": body,
        "z.txt": body,
        "UP.TXT": body,
    })
    def files(*flags):
        return sel.files(*flags, "a/b")

    every = ["a/b/UP.TXT", "a/b/other/o.txt", "a/b/other/sub/y.txt", "a/b/sub/x.md", "a/b/sub/x.txt", "a/b/z.txt"]
    assert files() == every
    lower_txt = ["a/b/other/o.txt", "a/b/other/sub/y.txt", "a/b/sub/x.txt", "a/b/z.txt"]

    # A glob with a directory part matches relative to the search root.
    for flag in ("-g", "--glob"):
        assert files(flag, "sub/*.txt") == ["a/b/sub/x.txt"]
    assert sel.files("-g", "b/sub/*.txt", "a") == ["a/b/sub/x.txt"]
    assert sel.files("-g", "sub/*.txt", "a", expect="no_match") == []
    # Positive globs: any of them admits.
    assert files("-g", "*.txt") == lower_txt
    assert files("-g", "*.md", "-g", "z.*") == ["a/b/sub/x.md", "a/b/z.txt"]
    # Negative globs exclude.
    assert files("-g", "!*.txt") == ["a/b/UP.TXT", "a/b/sub/x.md"]
    assert files("-g", "*.txt", "-g", "!z.txt") == ["a/b/other/o.txt", "a/b/other/sub/y.txt", "a/b/sub/x.txt"]
    # A negative glob matching a directory excludes its whole subtree.
    assert files("-g", "!other") == ["a/b/UP.TXT", "a/b/sub/x.md", "a/b/sub/x.txt", "a/b/z.txt"]
    assert files("-g", "!sub") == ["a/b/UP.TXT", "a/b/other/o.txt", "a/b/z.txt"]

    # Case: globs are case-sensitive; iglob and glob-case-insensitive are not.
    assert files("-g", "*.TXT") == ["a/b/UP.TXT"]
    assert files("--iglob", "*.TXT") == sorted([*lower_txt, "a/b/UP.TXT"])
    assert files("--glob-case-insensitive", "-g", "*.TXT") == sorted([*lower_txt, "a/b/UP.TXT"])
    assert files("-g", "*.TXT", "--glob-case-insensitive") == sorted([*lower_txt, "a/b/UP.TXT"])
    assert files("--iglob", "!*.TXT") == ["a/b/sub/x.md"]
    assert files("--iglob", "SUB/*.txt") == ["a/b/sub/x.txt"]
    assert files("-g", "*.TXT", "--iglob", "*.md") == ["a/b/UP.TXT", "a/b/sub/x.md"]
    assert files("-g", "[xz].t?t") == ["a/b/sub/x.txt", "a/b/z.txt"]
    assert files("-g", "*.{md,TXT}") == ["a/b/UP.TXT", "a/b/sub/x.md"]
    assert files("-g", "**/sub/*.txt") == ["a/b/other/sub/y.txt", "a/b/sub/x.txt"]


# F04.T15
def test_follow_symlinks_and_one_file_system(tmp_path):
    sel, body = _sel(tmp_path)
    make_tree(tmp_path, {"outside/dir/in.txt": body, "outside/file.txt": body, "w/real/r.txt": body})
    (tmp_path / "w" / "linkdir").symlink_to(tmp_path / "outside" / "dir", target_is_directory=True)
    (tmp_path / "w" / "linkfile.txt").symlink_to(tmp_path / "outside" / "file.txt")

    assert sel.files("w") == ["w/real/r.txt"]
    for flag in ("-L", "--follow"):
        assert sel.files(flag, "w") == ["w/linkdir/in.txt", "w/linkfile.txt", "w/real/r.txt"]

    # On a single filesystem the option is accepted and changes nothing.
    assert sel.files("--one-file-system", "w") == ["w/real/r.txt"]
    assert sel.files("--one-file-system", "-L", "w") == [
        "w/linkdir/in.txt", "w/linkfile.txt", "w/real/r.txt"]


# F04.T15 regression — FP-04.01, FP-04.11

def test_p4_negation_and_cross_filesystem_follow(tmp_path):
    import os
    import tempfile
    from pathlib import Path
    sel, body = _sel(tmp_path)
    make_tree(tmp_path / "p4", {"p4ignore.ini": "*.log\n!keep.log\n",
                               "keep.log": body, "hide.log": body, "plain.txt": body})
    assert sel.files("p4") == ["p4/keep.log", "p4/plain.txt"]
    make_tree(tmp_path / "walk", {"local.txt": body})
    with tempfile.TemporaryDirectory(dir="/dev/shm") as other:
        other = Path(other)
        assert other.stat().st_dev != tmp_path.stat().st_dev, "fixture needs two filesystems"
        make_tree(other, {"remote.txt": body})
        (tmp_path / "walk/link").symlink_to(other, target_is_directory=True)
        assert sel.files("--follow", "walk") == ["walk/link/remote.txt", "walk/local.txt"]
        assert sel.files("--follow", "--one-file-system", "walk") == ["walk/local.txt"]
