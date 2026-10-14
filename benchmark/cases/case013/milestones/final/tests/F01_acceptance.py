# feature: F01
"""Acceptance tests for initializing a bare MEMBUNDLE v0.2 knowledge bundle.

Public entry: the ``membundle init`` command (FP-01). Observations go through
the sealed harness ``workspace`` / ``invoke`` path and the on-disk files
init wrote. These tests do not import Go packages, do not call internal
init helpers, and do not use ``membundle validate`` / ``membundle show`` to judge results.
"""

from __future__ import annotations

from _harness import (
    list_dir,
    path_is_dir,
    path_is_file,
    read_bytes,
    read_file,
    workspace,
)
from F01_helpers import (
    assert_bare_bundle_layout,
    assert_index_structure,
    assert_init_scaffold,
    assert_log_structure,
    dated_section_after_first_heading,
    dated_section_has_membundle_list_item,
    first_heading_text,
    init_success_names_path,
    membundle_version_declared,
    require_init_failure,
    require_init_success,
    run_init,
    run_init_with_dates,
    split_yaml_frontmatter,
    tz_offset_where_local_date_differs,
    unique_leaf,
)


# ---------------------------------------------------------------------------
# A. Named-path init creates the target and writes root index + log
# ---------------------------------------------------------------------------


def test_named_missing_directory_is_created_with_index_and_log():
    """A missing named directory is not a no-op."""
    with workspace() as ws:
        rel = unique_leaf("grove")
        result, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        target = ws.resolve(rel)
        print(f"created target exists={path_is_dir(target)} path={target}", flush=True)
        assert path_is_dir(target), f"missing named path was not created: {target}"
        assert_init_scaffold(target, allowed_dates=dates)


def test_named_existing_empty_directory_receives_index_and_log():
    """Create-if-needed still writes into a pre-existing empty directory."""
    with workspace() as ws:
        rel = unique_leaf("harbor")
        ws.resolve(rel).mkdir()
        result, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        target = ws.resolve(rel)
        assert path_is_dir(target)
        assert_init_scaffold(target, allowed_dates=dates)


def test_nested_missing_path_creates_parents_and_bundle_files():
    """A nested missing leaf is created when its parent already exists.

    One arm uses a ``knowledge`` leaf (public-sample shape) so a stub that
    only handles a hardcoded ``my-project/knowledge`` still has to write
    into a runtime-unique parent. the PRD does not require creating missing
    ancestors (mkdir -p); a missing parent is a case where creation can fail.
    """
    with workspace() as ws:
        parent = unique_leaf("proj")
        ws.resolve(parent).mkdir()
        rel = f"{parent}/knowledge"
        result, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        target = ws.resolve(rel)
        print(f"nested leaf exists={path_is_dir(target)} rel={rel}", flush=True)
        assert path_is_dir(target), f"nested missing leaf was not created: {rel}"
        assert_init_scaffold(target, allowed_dates=dates)


# ---------------------------------------------------------------------------
# B. Root index declares MEMBUNDLE version 0.2 and has a heading body
# ---------------------------------------------------------------------------


def test_root_index_frontmatter_declares_membundle_version_0_2():
    """Mapping key ``membundle_version`` has stripped scalar ``0.2``."""
    with workspace() as ws:
        rel = unique_leaf("idxver")
        result, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        index_text = read_file(ws.resolve(rel) / "index.md")
        mapping, _body = split_yaml_frontmatter(index_text)
        version = membundle_version_declared(mapping)
        print(f"declared membundle_version={version!r}", flush=True)
        assert version == "0.2"
        # Keep scaffold so an empty-file stub cannot pass on a lone key.
        assert_init_scaffold(ws.resolve(rel), allowed_dates=dates)


def test_root_index_body_has_a_markdown_heading():
    """Heading is taken from the split body, not the raw file."""
    with workspace() as ws:
        rel = unique_leaf("idxhead")
        result, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        index_text = read_file(ws.resolve(rel) / "index.md")
        _mapping, body = split_yaml_frontmatter(index_text)
        heading = first_heading_text(body)
        print(f"body heading={heading!r}", flush=True)
        assert heading.strip() != ""
        assert_init_scaffold(ws.resolve(rel), allowed_dates=dates)


# ---------------------------------------------------------------------------
# C. Root log dated heading is today’s UTC ISO date, with an init bullet
# ---------------------------------------------------------------------------


def test_log_first_heading_is_utc_iso_date():
    """First log heading is the host UTC calendar date."""
    with workspace() as ws:
        rel = unique_leaf("logdate")
        result, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        log_text = read_file(ws.resolve(rel) / "log.md")
        heading = first_heading_text(log_text)
        print(f"log heading={heading!r} allowed={sorted(dates)}", flush=True)
        assert heading in dates
        assert_log_structure(ws.resolve(rel) / "log.md", allowed_dates=dates)


def test_log_has_init_bullet_naming_membundle_v0_2():
    """The MEMBUNDLE v0.2 list item sits in the first dated section."""
    with workspace() as ws:
        rel = unique_leaf("logbullet")
        result, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        log_text = read_file(ws.resolve(rel) / "log.md")
        section = dated_section_after_first_heading(log_text)
        print(f"dated section={section!r}", flush=True)
        assert dated_section_has_membundle_list_item(section)
        assert_log_structure(ws.resolve(rel) / "log.md", allowed_dates=dates)


def test_log_date_uses_utc_not_process_local_timezone():
    """A TZ whose local date differs from UTC still writes the UTC date."""
    tz_value, local_date = tz_offset_where_local_date_differs()
    print(f"TZ contrast tz={tz_value!r} local_date={local_date}", flush=True)
    with workspace() as ws:
        utc_rel = unique_leaf("tzutc")
        off_rel = unique_leaf("tzoff")
        utc_result, utc_dates = run_init_with_dates(ws, extra_args=(utc_rel,))
        require_init_success(utc_result)
        off_result, off_dates = run_init_with_dates(
            ws, extra_args=(off_rel,), env_updates={"TZ": tz_value}
        )
        require_init_success(off_result)
        allowed = utc_dates | off_dates
        assert local_date not in allowed, (
            f"local date {local_date} collided with UTC spanning dates {sorted(allowed)}"
        )
        utc_heading = first_heading_text(read_file(ws.resolve(utc_rel) / "log.md"))
        off_heading = first_heading_text(read_file(ws.resolve(off_rel) / "log.md"))
        print(
            f"utc_heading={utc_heading!r} offset_heading={off_heading!r}",
            flush=True,
        )
        assert utc_heading in allowed
        assert off_heading in allowed
        assert off_heading != local_date
        assert_log_structure(ws.resolve(utc_rel) / "log.md", allowed_dates=allowed)
        assert_log_structure(ws.resolve(off_rel) / "log.md", allowed_dates=allowed)


# ---------------------------------------------------------------------------
# D. Already-present index or log is left unchanged; second init succeeds
# ---------------------------------------------------------------------------


def test_second_init_succeeds_and_preserves_custom_index_and_log():
    """A second init on custom files still succeeds and does not replace them."""
    with workspace() as ws:
        rel = unique_leaf("reinit")
        first, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(first)
        target = ws.resolve(rel)
        assert_init_scaffold(target, allowed_dates=dates)
        token = unique_leaf("custom")
        index_path = target / "index.md"
        log_path = target / "log.md"
        custom_index = f"# CUSTOM-INDEX-{token}\n"
        custom_log = f"## 1999-01-01\n* unique-bullet-{token}\n"
        index_path.write_text(custom_index, encoding="utf-8")
        log_path.write_text(custom_log, encoding="utf-8")
        before_index = read_bytes(index_path)
        before_log = read_bytes(log_path)
        second, _dates2 = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(second)
        after_index = read_bytes(index_path)
        after_log = read_bytes(log_path)
        print(
            f"preserved index={after_index == before_index} "
            f"log={after_log == before_log}",
            flush=True,
        )
        assert after_index == before_index
        assert after_log == before_log


def test_missing_log_is_written_without_replacing_existing_index():
    """Independent missing-file write: only log.md is created."""
    with workspace() as ws:
        rel = unique_leaf("onlyidx")
        target = ws.resolve(rel)
        target.mkdir()
        token = unique_leaf("keepidx")
        custom_index = f"# CUSTOM-INDEX-{token}\n"
        index_path = target / "index.md"
        index_path.write_text(custom_index, encoding="utf-8")
        before_index = read_bytes(index_path)
        result, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        assert read_bytes(index_path) == before_index
        log_path = target / "log.md"
        assert path_is_file(log_path), "missing log.md was not written"
        assert_log_structure(log_path, allowed_dates=dates)


def test_missing_index_is_written_without_replacing_existing_log():
    """Independent missing-file write: only index.md is created."""
    with workspace() as ws:
        rel = unique_leaf("onlylog")
        target = ws.resolve(rel)
        target.mkdir()
        token = unique_leaf("keeplog")
        custom_log = f"## 1999-01-01\n* unique-bullet-{token}\n"
        log_path = target / "log.md"
        log_path.write_text(custom_log, encoding="utf-8")
        before_log = read_bytes(log_path)
        result, _dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        assert read_bytes(log_path) == before_log
        index_path = target / "index.md"
        assert path_is_file(index_path), "missing index.md was not written"
        assert_index_structure(index_path)


# ---------------------------------------------------------------------------
# E. Omit-path default bundle rule
# ---------------------------------------------------------------------------


def test_omit_path_without_knowledge_dir_uses_cwd_and_does_not_create_knowledge():
    """No ``knowledge/`` directory: omit-path writes in cwd.

    the PRD requires the bundle files in the current directory when
    ``knowledge/`` is not a directory. They do not forbid also creating
    ``knowledge/`` as a side effect.
    """
    with workspace() as ws:
        result, dates = run_init_with_dates(ws)
        require_init_success(result, expected_path=".")
        assert path_is_file(ws.path / "index.md")
        assert path_is_file(ws.path / "log.md")
        assert_init_scaffold(ws.path, allowed_dates=dates)


def test_omit_path_with_knowledge_dir_writes_inside_knowledge_not_cwd():
    """Existing ``knowledge/`` directory: omit-path writes inside it."""
    with workspace() as ws:
        (ws.path / "knowledge").mkdir()
        result, dates = run_init_with_dates(ws)
        require_init_success(result, expected_path="knowledge")
        knowledge = ws.path / "knowledge"
        assert path_is_file(knowledge / "index.md")
        assert path_is_file(knowledge / "log.md")
        assert not path_is_file(ws.path / "index.md"), (
            "omit-path wrote cwd index.md while knowledge/ existed"
        )
        assert not path_is_file(ws.path / "log.md"), (
            "omit-path wrote cwd log.md while knowledge/ existed"
        )
        assert_init_scaffold(knowledge, allowed_dates=dates)


def test_omit_path_knowledge_file_is_not_treated_as_bundle_dir():
    """A file named ``knowledge`` is not a directory, so omit-path uses cwd."""
    with workspace() as ws:
        knowledge_file = ws.path / "knowledge"
        knowledge_file.write_text("not-a-directory\n", encoding="utf-8")
        before = read_bytes(knowledge_file)
        result, dates = run_init_with_dates(ws)
        require_init_success(result, expected_path=".")
        assert knowledge_file.is_file(), "knowledge file was replaced by a directory"
        assert read_bytes(knowledge_file) == before
        assert path_is_file(ws.path / "index.md")
        assert path_is_file(ws.path / "log.md")
        assert_init_scaffold(ws.path, allowed_dates=dates)


# ---------------------------------------------------------------------------
# F. Named path is the write target; nested-knowledge load redirect is not init
# ---------------------------------------------------------------------------


def test_named_path_with_nested_knowledge_writes_at_named_root():
    """Named init writes at the named directory, not only under nested knowledge/."""
    with workspace() as ws:
        rel = unique_leaf("namedkn")
        target = ws.resolve(rel)
        target.mkdir()
        (target / "knowledge").mkdir()
        result, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        assert path_is_file(target / "index.md"), (
            "named init did not write index.md at the named root"
        )
        assert path_is_file(target / "log.md"), (
            "named init did not write log.md at the named root"
        )
        assert_init_scaffold(target, allowed_dates=dates)


def test_explicit_path_is_not_overridden_by_cwd_knowledge():
    """An explicit path still wins when cwd also has knowledge/."""
    with workspace() as ws:
        (ws.path / "knowledge").mkdir()
        rel = unique_leaf("explicit")
        result, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        named = ws.resolve(rel)
        assert path_is_file(named / "index.md")
        assert path_is_file(named / "log.md")
        assert not path_is_file(ws.path / "knowledge" / "index.md"), (
            "explicit path was redirected into cwd knowledge/"
        )
        assert not path_is_file(ws.path / "knowledge" / "log.md")
        assert_init_scaffold(named, allowed_dates=dates)


# ---------------------------------------------------------------------------
# G. Success report names the target
# ---------------------------------------------------------------------------


def test_success_report_identifies_target_path_and_membundle_v0_2():
    """Each success report is the stated line naming its own directory.

    Contract Output forms, ``init``: one line containing ``'<path>'`` with
    ``<path>`` the path the caller named.
    """
    with workspace() as ws:
        a = unique_leaf("grove")
        b = unique_leaf("harbor")
        ra, _da = run_init_with_dates(ws, extra_args=(a,))
        rb, _db = run_init_with_dates(ws, extra_args=(b,))
        report_a = require_init_success(ra)
        report_b = require_init_success(rb)
        print(f"report_a={report_a!r}\nreport_b={report_b!r}", flush=True)
        assert init_success_names_path(report_a, a)
        assert init_success_names_path(report_b, b)
        assert not init_success_names_path(report_a, b)
        assert not init_success_names_path(report_b, a)
        assert report_a != report_b


def test_omit_path_success_reports_differ_for_cwd_vs_knowledge():
    """Omit-path reports name the default bundle path each run used.

    Contract Output forms, ``init``: ``<path>`` is the default bundle path
    when omitted: ``.`` without a ``knowledge`` directory, ``knowledge`` with one.
    """
    with workspace() as ws:
        leaf = unique_leaf("basin")
        parent_a = unique_leaf("ridge")
        parent_b = unique_leaf("shore")
        cwd_a = ws.resolve(f"{parent_a}/{leaf}")
        cwd_b = ws.resolve(f"{parent_b}/{leaf}")
        cwd_a.mkdir(parents=True)
        cwd_b.mkdir(parents=True)
        (cwd_b / "knowledge").mkdir()
        ra, dates_a = run_init_with_dates(ws, cwd=cwd_a)
        rb, dates_b = run_init_with_dates(ws, cwd=cwd_b)
        report_a = require_init_success(ra, expected_path=".")
        report_b = require_init_success(rb, expected_path="knowledge")
        print(
            f"omit report cwd={report_a!r}\nomit report knowledge={report_b!r}",
            flush=True,
        )
        assert report_a != report_b, (
            "omit-path success reports for cwd vs knowledge/ did not differ"
        )
        assert not init_success_names_path(report_a, "knowledge"), (
            f"omit-path cwd report names 'knowledge': {report_a!r}"
        )
        assert_init_scaffold(cwd_a, allowed_dates=dates_a)
        assert_init_scaffold(cwd_b / "knowledge", allowed_dates=dates_b)


# ---------------------------------------------------------------------------
# H. Uncreatable / unwritable target does not succeed and reports
# ---------------------------------------------------------------------------


def test_init_fails_when_parent_path_is_a_file():
    """A named path whose parent is a regular file does not succeed."""
    with workspace() as ws:
        success_rel = unique_leaf("okwrite")
        ok_result, _dates = run_init_with_dates(ws, extra_args=(success_rel,))
        success_report = require_init_success(ok_result)
        blocker = unique_leaf("blocker")
        ws.write(blocker, "this is a file, not a directory\n")
        fail_rel = f"{blocker}/child"
        fail_result = run_init(ws, extra_args=(fail_rel,))
        tokens = (
            success_rel,
            str(ws.resolve(success_rel)),
            fail_rel,
            blocker,
            str(ws.resolve(blocker)),
        )
        fail_report = require_init_failure(fail_result, success_report, tokens)
        print(
            f"parent-is-file exit={fail_result.returncode} report={fail_report!r}",
            flush=True,
        )
        assert fail_result.returncode != 0, (
            "init succeeded when the named path's parent is a regular file; "
            f"report={fail_report!r}"
        )
        assert fail_report, (
            "init failed on a file-parent path but reported nothing"
        )


def test_init_fails_when_target_exists_as_a_file():
    """A named path that exists as a regular file does not succeed."""
    with workspace() as ws:
        success_rel = unique_leaf("sibfile")
        ok_result, _dates = run_init_with_dates(ws, extra_args=(success_rel,))
        success_report = require_init_success(ok_result)
        fail_rel = unique_leaf("filetgt")
        ws.write(fail_rel, "not a directory\n")
        fail_result = run_init(ws, extra_args=(fail_rel,))
        tokens = (
            success_rel,
            str(ws.resolve(success_rel)),
            fail_rel,
            str(ws.resolve(fail_rel)),
        )
        fail_report = require_init_failure(fail_result, success_report, tokens)
        print(
            f"target-is-file exit={fail_result.returncode} report={fail_report!r}",
            flush=True,
        )
        assert fail_result.returncode != 0, (
            "init succeeded when the named path exists as a regular file; "
            f"report={fail_report!r}"
        )
        assert fail_report, (
            "init failed on a file target but reported nothing"
        )


# ---------------------------------------------------------------------------
# I. Init does not create concepts, AGENTS.md, skill files, or a Makefile
# ---------------------------------------------------------------------------


def test_init_does_not_write_concepts_agents_skills_or_makefile():
    """After init of a missing target, extras the PRD names are absent."""
    with workspace() as ws:
        control = ws.resolve("control-lister")
        control.mkdir()
        (control / "AGENTS.md").write_text("positive-control\n", encoding="utf-8")
        listed_control = list_dir(control)
        print(f"positive-control list_dir={listed_control}", flush=True)
        assert "AGENTS.md" in listed_control, (
            "filesystem lister did not see an AGENTS.md the test itself wrote"
        )
        rel = unique_leaf("bare")
        result, dates = run_init_with_dates(ws, extra_args=(rel,))
        require_init_success(result)
        target = ws.resolve(rel)
        assert_init_scaffold(target, allowed_dates=dates)
        names = list_dir(target)
        print(f"bundle list_dir={names}", flush=True)
        assert "AGENTS.md" not in names
        assert "Makefile" not in names
        assert_bare_bundle_layout(target)
        # UTF-8 text: decode failure in read_file is a harness error, not a pass.
        read_file(target / "index.md")
        read_file(target / "log.md")
