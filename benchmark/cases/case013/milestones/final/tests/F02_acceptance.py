# feature: F02
"""Acceptance tests for bootstrapping the Dual-Memory Agent Memory stack.

Public entry: the ``membundle bootstrap`` command (FP-02). Observations go through
the sealed harness ``workspace`` / ``invoke`` path and the on-disk files
bootstrap wrote. These tests do not import Go packages, do not call
internal Bootstrap helpers, and do not use ``membundle validate`` / ``membundle show``
/ ``membundle init`` to judge results.
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
    assert_index_structure,
    first_heading_text,
    membundle_version_declared,
    split_yaml_frontmatter,
    tz_offset_where_local_date_differs,
    unique_leaf,
)
from F02_helpers import (
    ALL_COMPONENTS,
    BEGIN_MEMBUNDLE_COMMENT,
    COMPONENT_AGENTS,
    COMPONENT_KNOWLEDGE,
    COMPONENT_MAKEFILE,
    COMPONENT_SKILL,
    END_MEMBUNDLE_COMMENT,
    SKILL_FILENAMES,
    assert_agents_file_missing_write,
    assert_bootstrap_log,
    assert_delimited_block_contents,
    assert_delimited_block_nonempty,
    assert_full_bootstrap_quality,
    assert_knowledge_scaffold,
    assert_makefile_convenience_tasks,
    assert_skip_makefile_report_not_installed,
    assert_skill_tree,
    dated_section_has_list_item,
    extract_membundle_agents_block,
    require_bootstrap_failure,
    require_bootstrap_success,
    run_agents_md_detection_contrast,
    run_bootstrap,
    run_bootstrap_with_dates,
    section_under_utc_date_heading,
    utc_date_heading_text,
)


# ---------------------------------------------------------------------------
# A. Full bootstrap creates the project and installs four components
# ---------------------------------------------------------------------------


def test_named_missing_directory_gets_all_four_components():
    """A missing named directory is not a no-op.

    One arm uses a README-like nested ``my-project`` leaf whose parent
    already exists; a second arm uses a different runtime-unique leaf.
    """
    with workspace() as ws:
        parent = unique_leaf("proj")
        ws.resolve(parent).mkdir()
        nested = f"{parent}/my-project"
        nested_result, nested_dates = run_bootstrap_with_dates(
            ws, extra_args=(nested,)
        )
        nested_target = ws.resolve(nested)
        print(
            f"nested target exists={path_is_dir(nested_target)} rel={nested}",
            flush=True,
        )
        assert path_is_dir(nested_target), (
            f"missing nested named path was not created: {nested}"
        )
        assert_full_bootstrap_quality(
            nested_target, nested_dates, "my-project", nested_result
        )

        rel = unique_leaf("grove")
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        target = ws.resolve(rel)
        print(f"unique target exists={path_is_dir(target)} rel={rel}", flush=True)
        assert path_is_dir(target), f"missing named path was not created: {rel}"
        assert_full_bootstrap_quality(target, dates, rel, result)


def test_named_existing_empty_directory_gets_all_four_components():
    """Create-if-needed still writes into a pre-existing empty directory."""
    with workspace() as ws:
        rel = unique_leaf("harbor")
        ws.resolve(rel).mkdir()
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        target = ws.resolve(rel)
        assert path_is_dir(target)
        assert_full_bootstrap_quality(target, dates, rel, result)


def test_omit_path_bootstraps_cwd_as_project_root():
    """No target argument: four components land in cwd."""
    with workspace() as ws:
        result, dates = run_bootstrap_with_dates(ws)
        project_name = ws.path.name
        print(f"omit-path cwd basename={project_name!r}", flush=True)
        assert_full_bootstrap_quality(ws.path, dates, project_name, result)
        assert path_is_file(ws.path / "knowledge" / "index.md")
        assert path_is_file(ws.path / "knowledge" / "log.md")


# ---------------------------------------------------------------------------
# B. knowledge/ index declares version 0.2 and is titled with the project name
# ---------------------------------------------------------------------------


def test_knowledge_index_frontmatter_declares_membundle_version_0_2():
    """Mapping key ``membundle_version`` has stripped scalar ``0.2``."""
    with workspace() as ws:
        rel = unique_leaf("idxver")
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        require_bootstrap_success(result, ALL_COMPONENTS)
        index_text = read_file(ws.resolve(rel) / "knowledge" / "index.md")
        mapping, _body = split_yaml_frontmatter(index_text)
        version = membundle_version_declared(mapping)
        print(f"declared membundle_version={version!r}", flush=True)
        assert version == "0.2"
        assert_full_bootstrap_quality(ws.resolve(rel), dates, rel, result)


def test_knowledge_index_heading_contains_project_name():
    """Two ``--name`` arms: each index heading (and AGENTS.md) contains that name."""
    with workspace() as ws:
        name_a = unique_leaf("alpha")
        name_b = unique_leaf("bravo")
        rel_a = unique_leaf("sitea")
        rel_b = unique_leaf("siteb")
        ra, dates_a = run_bootstrap_with_dates(
            ws, extra_args=(rel_a, "--name", name_a)
        )
        rb, dates_b = run_bootstrap_with_dates(
            ws, extra_args=(rel_b, "--name", name_b)
        )
        assert_full_bootstrap_quality(ws.resolve(rel_a), dates_a, name_a, ra)
        assert_full_bootstrap_quality(ws.resolve(rel_b), dates_b, name_b, rb)
        heading_a = first_heading_text(
            split_yaml_frontmatter(
                read_file(ws.resolve(rel_a) / "knowledge" / "index.md")
            )[1]
        )
        heading_b = first_heading_text(
            split_yaml_frontmatter(
                read_file(ws.resolve(rel_b) / "knowledge" / "index.md")
            )[1]
        )
        agents_a = read_file(ws.resolve(rel_a) / "AGENTS.md")
        agents_b = read_file(ws.resolve(rel_b) / "AGENTS.md")
        print(
            f"heading_a={heading_a!r} heading_b={heading_b!r}",
            flush=True,
        )
        assert name_a in heading_a
        assert name_b in heading_b
        assert name_b not in heading_a
        assert name_a not in heading_b
        assert name_a in agents_a
        assert name_b in agents_b
        assert name_b not in agents_a
        assert name_a not in agents_b


# ---------------------------------------------------------------------------
# C. knowledge/ log dated heading is today’s UTC ISO date, with a creation bullet
# ---------------------------------------------------------------------------


def test_knowledge_log_first_heading_is_utc_iso_date():
    """A log heading is today's UTC calendar date, wherever it sits."""
    with workspace() as ws:
        rel = unique_leaf("logdate")
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        require_bootstrap_success(result, ALL_COMPONENTS)
        log_text = read_file(ws.resolve(rel) / "knowledge" / "log.md")
        heading = utc_date_heading_text(log_text, dates)
        print(f"log heading={heading!r} allowed={sorted(dates)}", flush=True)
        assert heading in dates
        assert_bootstrap_log(
            ws.resolve(rel) / "knowledge" / "log.md", allowed_dates=dates
        )


def test_knowledge_log_dated_section_has_a_list_item():
    """A list item sits under the UTC date heading, wherever that heading sits."""
    with workspace() as ws:
        rel = unique_leaf("logbullet")
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        require_bootstrap_success(result, ALL_COMPONENTS)
        log_text = read_file(ws.resolve(rel) / "knowledge" / "log.md")
        section = section_under_utc_date_heading(log_text, dates)
        print(f"dated section={section!r}", flush=True)
        assert dated_section_has_list_item(section)
        assert_bootstrap_log(
            ws.resolve(rel) / "knowledge" / "log.md", allowed_dates=dates
        )


def test_knowledge_log_date_uses_utc_not_process_local_timezone():
    """A TZ whose local date differs from UTC still writes the UTC date."""
    tz_value, local_date = tz_offset_where_local_date_differs()
    print(f"TZ contrast tz={tz_value!r} local_date={local_date}", flush=True)
    with workspace() as ws:
        utc_rel = unique_leaf("tzutc")
        off_rel = unique_leaf("tzoff")
        utc_result, utc_dates = run_bootstrap_with_dates(
            ws, extra_args=(utc_rel,)
        )
        require_bootstrap_success(utc_result, ALL_COMPONENTS)
        off_result, off_dates = run_bootstrap_with_dates(
            ws, extra_args=(off_rel,), env_updates={"TZ": tz_value}
        )
        require_bootstrap_success(off_result, ALL_COMPONENTS)
        allowed = utc_dates | off_dates
        assert local_date not in allowed, (
            f"local date {local_date} collided with UTC spanning dates "
            f"{sorted(allowed)}"
        )
        utc_heading = utc_date_heading_text(
            read_file(ws.resolve(utc_rel) / "knowledge" / "log.md"), allowed
        )
        off_heading = utc_date_heading_text(
            read_file(ws.resolve(off_rel) / "knowledge" / "log.md"), allowed
        )
        print(
            f"utc_heading={utc_heading!r} offset_heading={off_heading!r}",
            flush=True,
        )
        assert utc_heading in allowed
        assert off_heading in allowed
        assert off_heading != local_date
        assert_bootstrap_log(
            ws.resolve(utc_rel) / "knowledge" / "log.md", allowed_dates=allowed
        )
        assert_bootstrap_log(
            ws.resolve(off_rel) / "knowledge" / "log.md", allowed_dates=allowed
        )


# ---------------------------------------------------------------------------
# D. Existing index / log / Makefile preserved; skill files replaced
# ---------------------------------------------------------------------------


def test_second_bootstrap_succeeds_preserves_index_log_makefile_and_still_reports_four():
    """Second bootstrap keeps custom index/log/Makefile and still names all four."""
    with workspace() as ws:
        rel = unique_leaf("reboot")
        first, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        assert_full_bootstrap_quality(ws.resolve(rel), dates, rel, first)
        target = ws.resolve(rel)
        token = unique_leaf("custom")
        index_path = target / "knowledge" / "index.md"
        log_path = target / "knowledge" / "log.md"
        makefile_path = target / "Makefile"
        index_path.write_text(f"# CUSTOM-INDEX-{token}\n", encoding="utf-8")
        log_path.write_text(
            f"## 1999-01-01\n* unique-bullet-{token}\n", encoding="utf-8"
        )
        makefile_path.write_text(f"# KEEP-MAKEFILE-{token}\n", encoding="utf-8")
        before_index = read_bytes(index_path)
        before_log = read_bytes(log_path)
        before_make = read_bytes(makefile_path)
        second, _dates2 = run_bootstrap_with_dates(ws, extra_args=(rel,))
        require_bootstrap_success(second, ALL_COMPONENTS)
        print(
            f"preserved index={read_bytes(index_path) == before_index} "
            f"log={read_bytes(log_path) == before_log} "
            f"makefile={read_bytes(makefile_path) == before_make}",
            flush=True,
        )
        assert read_bytes(index_path) == before_index
        assert read_bytes(log_path) == before_log
        assert read_bytes(makefile_path) == before_make


def test_missing_knowledge_log_is_written_without_replacing_existing_index():
    """Only the missing knowledge/log.md is created."""
    with workspace() as ws:
        rel = unique_leaf("onlyidx")
        target = ws.resolve(rel)
        (target / "knowledge").mkdir(parents=True)
        token = unique_leaf("keepidx")
        index_path = target / "knowledge" / "index.md"
        index_path.write_text(f"# CUSTOM-INDEX-{token}\n", encoding="utf-8")
        before_index = read_bytes(index_path)
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        require_bootstrap_success(result, ALL_COMPONENTS)
        assert read_bytes(index_path) == before_index
        log_path = target / "knowledge" / "log.md"
        assert path_is_file(log_path), "missing knowledge/log.md was not written"
        assert_bootstrap_log(log_path, allowed_dates=dates)


def test_missing_knowledge_index_is_written_without_replacing_existing_log():
    """Only the missing knowledge/index.md is created."""
    with workspace() as ws:
        rel = unique_leaf("onlylog")
        name = unique_leaf("idxname")
        target = ws.resolve(rel)
        (target / "knowledge").mkdir(parents=True)
        token = unique_leaf("keeplog")
        log_path = target / "knowledge" / "log.md"
        log_path.write_text(
            f"## 1999-01-01\n* unique-bullet-{token}\n", encoding="utf-8"
        )
        before_log = read_bytes(log_path)
        result, _dates = run_bootstrap_with_dates(
            ws, extra_args=(rel, "--name", name)
        )
        require_bootstrap_success(result, ALL_COMPONENTS)
        assert read_bytes(log_path) == before_log
        index_path = target / "knowledge" / "index.md"
        assert path_is_file(index_path), (
            "missing knowledge/index.md was not written"
        )
        assert_index_structure(index_path)
        heading = first_heading_text(
            split_yaml_frontmatter(read_file(index_path))[1]
        )
        print(f"written index heading={heading!r} name={name!r}", flush=True)
        assert name in heading


def test_existing_skill_files_are_replaced_when_skill_not_skipped():
    """Each of the six pre-seeded skill stubs is gone after a skill write."""
    with workspace() as ws:
        rel = unique_leaf("reskill")
        target = ws.resolve(rel)
        skill = target / ".agents" / "skills" / "membundle-memory"
        skill.mkdir(parents=True)
        token = unique_leaf("stub")
        stubs: dict[str, str] = {}
        for name in SKILL_FILENAMES:
            text = f"STUB-{name}-{token}\n"
            (skill / name).write_text(text, encoding="utf-8")
            stubs[name] = text
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        assert_full_bootstrap_quality(target, dates, rel, result)
        for name, stub in stubs.items():
            body = read_file(skill / name)
            print(f"skill {name} stub_gone={stub not in body}", flush=True)
            assert stub not in body, f"pre-seeded stub remained in {name}"
            assert len(body) > 0, f"replaced skill file is empty: {name}"


# ---------------------------------------------------------------------------
# E. Default project directory is cwd, not the knowledge/ load rule
# ---------------------------------------------------------------------------


def test_omit_path_with_existing_knowledge_still_uses_cwd_as_project():
    """Existing knowledge/ does not redirect project-level writes into it."""
    with workspace() as ws:
        knowledge = ws.path / "knowledge"
        knowledge.mkdir()
        token = unique_leaf("keepkn")
        index_path = knowledge / "index.md"
        log_path = knowledge / "log.md"
        index_path.write_text(f"# CUSTOM-INDEX-{token}\n", encoding="utf-8")
        log_path.write_text(
            f"## 1999-01-01\n* unique-bullet-{token}\n", encoding="utf-8"
        )
        before_index = read_bytes(index_path)
        before_log = read_bytes(log_path)
        result, _dates = run_bootstrap_with_dates(ws)
        require_bootstrap_success(result, ALL_COMPONENTS)
        assert read_bytes(index_path) == before_index
        assert read_bytes(log_path) == before_log
        project_name = ws.path.name
        print(f"omit-path existing-knowledge cwd name={project_name!r}", flush=True)
        assert_agents_file_missing_write(ws.path / "AGENTS.md", project_name)
        assert_skill_tree(ws.path)
        assert_makefile_convenience_tasks(ws.path / "Makefile")


def test_named_path_is_project_root_even_when_cwd_has_knowledge():
    """A named path is the project even when cwd also has knowledge/."""
    with workspace() as ws:
        (ws.path / "knowledge").mkdir()
        rel = unique_leaf("explicit")
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        named = ws.resolve(rel)
        assert_full_bootstrap_quality(named, dates, rel, result)


# ---------------------------------------------------------------------------
# F. Project name: directory basename, explicit name, two-name contrast
# ---------------------------------------------------------------------------


def test_omitted_name_uses_target_directory_basename():
    """Omit ``--name``: index heading and AGENTS.md contain the directory basename."""
    with workspace() as ws:
        rel = unique_leaf("basin")
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        assert_full_bootstrap_quality(ws.resolve(rel), dates, rel, result)
        heading = first_heading_text(
            split_yaml_frontmatter(
                read_file(ws.resolve(rel) / "knowledge" / "index.md")
            )[1]
        )
        agents = read_file(ws.resolve(rel) / "AGENTS.md")
        print(f"omitted-name heading={heading!r} basename={rel!r}", flush=True)
        assert rel in heading
        assert rel in agents


def test_explicit_name_overrides_directory_basename():
    """Explicit ``--name`` is the title, not the directory basename."""
    with workspace() as ws:
        rel = unique_leaf("dirbase")
        name = unique_leaf("showname")
        result, dates = run_bootstrap_with_dates(
            ws, extra_args=(rel, "--name", name)
        )
        assert_full_bootstrap_quality(ws.resolve(rel), dates, name, result)
        heading = first_heading_text(
            split_yaml_frontmatter(
                read_file(ws.resolve(rel) / "knowledge" / "index.md")
            )[1]
        )
        agents = read_file(ws.resolve(rel) / "AGENTS.md")
        print(
            f"explicit heading={heading!r} name={name!r} basename={rel!r}",
            flush=True,
        )
        assert name in heading
        assert name in agents


# ---------------------------------------------------------------------------
# G. AGENTS.md write / append / leave-unchanged / overwrite
# ---------------------------------------------------------------------------


def test_missing_agents_md_is_written_with_delimiters_name_and_nonempty_block():
    """Missing AGENTS.md: both comments, name present, extracted block non-empty."""
    with workspace() as ws:
        rel = unique_leaf("agentsnew")
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        assert_full_bootstrap_quality(ws.resolve(rel), dates, rel, result)
        text = read_file(ws.resolve(rel) / "AGENTS.md")
        begin_at = text.find(BEGIN_MEMBUNDLE_COMMENT)
        end_at = text.find(END_MEMBUNDLE_COMMENT)
        print(f"BEGIN at {begin_at} END at {end_at}", flush=True)
        assert begin_at >= 0
        assert end_at > begin_at
        block = extract_membundle_agents_block(text)
        assert_delimited_block_contents(block)
        assert rel in text


def test_existing_human_rules_agents_md_is_appended_not_replaced():
    """HUMAN-RULES file gains the delimited block after the original prefix."""
    with workspace() as ws:
        rel = unique_leaf("append")
        target = ws.resolve(rel)
        target.mkdir()
        token = unique_leaf("rules")
        original = (
            f"# HUMAN-RULES-{token}\n"
            "Prefer local fixtures over remote lookups.\n"
        )
        agents_path = target / "AGENTS.md"
        agents_path.write_text(original, encoding="utf-8")
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        require_bootstrap_success(result, ALL_COMPONENTS)
        text = read_file(agents_path)
        print(f"appended AGENTS.md={text!r}", flush=True)
        assert token in text, "original human-rules marker was deleted"
        begin_at = text.find(BEGIN_MEMBUNDLE_COMMENT)
        marker_at = text.find(token)
        assert begin_at >= 0
        assert marker_at >= 0
        assert marker_at < begin_at, (
            "original rules were not retained before BEGIN (append, not replace)"
        )
        block = extract_membundle_agents_block(text)
        assert_delimited_block_contents(block)
        assert_knowledge_scaffold(target, dates, project_name=rel)


def test_agents_md_with_begin_phrase_is_left_unchanged_when_overwrite_off():
    """Detection string (1): phrase BEGIN MEMBUNDLE AGENT MEMORY, overwrite off."""
    with workspace() as ws:
        token = unique_leaf("keepbeg")
        detection = "BEGIN MEMBUNDLE AGENT MEMORY"
        prefix = f"# KEEP-{token}\n"
        suffix = "\n"
        detect_rel = unique_leaf("beginph")
        baseline_rel = unique_leaf("beginbase")
        detect_body = f"{prefix}{detection}{suffix}"
        baseline_body = f"{prefix}{suffix}"
        before, after, baseline_text = run_agents_md_detection_contrast(
            ws,
            detect_rel=detect_rel,
            baseline_rel=baseline_rel,
            detect_body=detect_body,
            baseline_body=baseline_body,
        )
        print(f"begin-phrase unchanged={after == before}", flush=True)
        assert after == before, (
            "BEGIN MEMBUNDLE AGENT MEMORY detection arm rewrote AGENTS.md"
        )
        block = extract_membundle_agents_block(baseline_text)
        assert_delimited_block_nonempty(block)
        assert token in baseline_text
        assert baseline_text != baseline_body, (
            "baseline that omitted BEGIN MEMBUNDLE AGENT MEMORY also left AGENTS.md "
            "unchanged; detection was not what kept the file"
        )


def test_agents_md_with_membundle_agent_memory_substring_is_left_unchanged_when_overwrite_off():
    """Detection string (2): substring membundle-agent-memory, overwrite off."""
    with workspace() as ws:
        token = unique_leaf("keepsub")
        detection = "membundle-agent-memory"
        prefix = f"# KEEP-{token}\nSee "
        suffix = " notes.\n"
        detect_rel = unique_leaf("substr")
        baseline_rel = unique_leaf("subbase")
        detect_body = f"{prefix}{detection}{suffix}"
        baseline_body = f"{prefix}{suffix}"
        before, after, baseline_text = run_agents_md_detection_contrast(
            ws,
            detect_rel=detect_rel,
            baseline_rel=baseline_rel,
            detect_body=detect_body,
            baseline_body=baseline_body,
        )
        print(f"substring unchanged={after == before}", flush=True)
        assert after == before, (
            "membundle-agent-memory detection arm rewrote AGENTS.md"
        )
        block = extract_membundle_agents_block(baseline_text)
        assert_delimited_block_nonempty(block)
        assert token in baseline_text
        assert baseline_text != baseline_body, (
            "baseline that omitted membundle-agent-memory also left AGENTS.md "
            "unchanged; detection was not what kept the file"
        )


def test_agents_md_with_open_knowledge_format_membundle_phrase_is_left_unchanged_when_overwrite_off():
    """Detection string (3): phrase Open Bundle Format (MEMBUNDLE), overwrite off."""
    with workspace() as ws:
        token = unique_leaf("keepfmt")
        detection = "Open Bundle Format (MEMBUNDLE)"
        prefix = f"# KEEP-{token}\n"
        suffix = "\n"
        detect_rel = unique_leaf("fmtph")
        baseline_rel = unique_leaf("fmtbase")
        detect_body = f"{prefix}{detection}{suffix}"
        baseline_body = f"{prefix}{suffix}"
        before, after, baseline_text = run_agents_md_detection_contrast(
            ws,
            detect_rel=detect_rel,
            baseline_rel=baseline_rel,
            detect_body=detect_body,
            baseline_body=baseline_body,
        )
        print(f"MEMBUNDLE-phrase unchanged={after == before}", flush=True)
        assert after == before, (
            "Open Bundle Format (MEMBUNDLE) detection arm rewrote AGENTS.md"
        )
        block = extract_membundle_agents_block(baseline_text)
        assert_delimited_block_nonempty(block)
        assert token in baseline_text
        assert baseline_text != baseline_body, (
            "baseline that omitted Open Bundle Format (MEMBUNDLE) also left "
            "AGENTS.md unchanged; detection was not what kept the file"
        )


def test_overwrite_replaces_human_rules_agents_md_with_template():
    """Overwrite on vs off differ only in the overwrite option."""
    with workspace() as ws:
        token = unique_leaf("owhuman")
        original = (
            f"# HUMAN-RULES-{token}\n"
            "Prefer local fixtures over remote lookups.\n"
        )
        rel_on = unique_leaf("owon")
        rel_off = unique_leaf("owoff")
        ws.resolve(rel_on).mkdir()
        ws.resolve(rel_off).mkdir()
        (ws.resolve(rel_on) / "AGENTS.md").write_text(original, encoding="utf-8")
        (ws.resolve(rel_off) / "AGENTS.md").write_text(original, encoding="utf-8")
        on_result, on_dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_on, "--overwrite-agents-md")
        )
        off_result, off_dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_off,)
        )
        require_bootstrap_success(on_result, ALL_COMPONENTS)
        require_bootstrap_success(off_result, ALL_COMPONENTS)
        on_text = read_file(ws.resolve(rel_on) / "AGENTS.md")
        off_text = read_file(ws.resolve(rel_off) / "AGENTS.md")
        print(
            f"overwrite token_gone={token not in on_text} "
            f"append token_kept={token in off_text}",
            flush=True,
        )
        assert token not in on_text, (
            "overwrite left the original human-rules marker in place"
        )
        assert_agents_file_missing_write(
            ws.resolve(rel_on) / "AGENTS.md", rel_on
        )
        assert token in off_text
        assert_delimited_block_contents(extract_membundle_agents_block(off_text))
        assert_knowledge_scaffold(ws.resolve(rel_on), on_dates, project_name=rel_on)
        assert_knowledge_scaffold(ws.resolve(rel_off), off_dates, project_name=rel_off)


def test_overwrite_replaces_begin_marker_agents_md_with_template():
    """Overwrite on a begin-marker file replaces unique original rules."""
    with workspace() as ws:
        token = unique_leaf("owbegin")
        original = (
            f"# ORIGINAL-RULES-{token}\n"
            f"{BEGIN_MEMBUNDLE_COMMENT}\n"
        )
        rel_on = unique_leaf("begon")
        rel_off = unique_leaf("begoff")
        ws.resolve(rel_on).mkdir()
        ws.resolve(rel_off).mkdir()
        (ws.resolve(rel_on) / "AGENTS.md").write_text(original, encoding="utf-8")
        (ws.resolve(rel_off) / "AGENTS.md").write_text(original, encoding="utf-8")
        on_result, on_dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_on, "--overwrite-agents-md")
        )
        off_result, _off_dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_off,)
        )
        require_bootstrap_success(on_result, ALL_COMPONENTS)
        require_bootstrap_success(off_result, ALL_COMPONENTS)
        on_text = read_file(ws.resolve(rel_on) / "AGENTS.md")
        off_bytes = read_bytes(ws.resolve(rel_off) / "AGENTS.md")
        print(
            f"begin-overwrite token_gone={token not in on_text} "
            f"leave-unchanged={off_bytes == original.encode('utf-8')}",
            flush=True,
        )
        assert token not in on_text, (
            "overwrite-on left unique original rules in a begin-marker file"
        )
        assert_agents_file_missing_write(
            ws.resolve(rel_on) / "AGENTS.md", rel_on
        )
        assert off_bytes == original.encode("utf-8")
        assert_knowledge_scaffold(ws.resolve(rel_on), on_dates, project_name=rel_on)


def test_begin_marker_is_not_duplicated_when_overwrite_off():
    """A file that already contains the BEGIN comment is not duplicated."""
    with workspace() as ws:
        token = unique_leaf("keepdup")
        prefix = f"# KEEP-{token}\n"
        suffix = "\n"
        detect_rel = unique_leaf("nodup")
        baseline_rel = unique_leaf("dupbase")
        detect_body = f"{prefix}{BEGIN_MEMBUNDLE_COMMENT}{suffix}"
        baseline_body = f"{prefix}{suffix}"
        before, after, baseline_text = run_agents_md_detection_contrast(
            ws,
            detect_rel=detect_rel,
            baseline_rel=baseline_rel,
            detect_body=detect_body,
            baseline_body=baseline_body,
        )
        after_text = after.decode("utf-8")
        before_count = detect_body.count(BEGIN_MEMBUNDLE_COMMENT)
        after_count = after_text.count(BEGIN_MEMBUNDLE_COMMENT)
        print(
            f"BEGIN count before={before_count} after={after_count}",
            flush=True,
        )
        assert after == before, (
            "begin-marker arm rewrote AGENTS.md when overwrite was off"
        )
        assert after_count == 1
        assert after_count == before_count
        assert token in after_text
        begin_at = baseline_text.find(BEGIN_MEMBUNDLE_COMMENT)
        end_at = baseline_text.find(END_MEMBUNDLE_COMMENT)
        print(
            f"append BEGIN at {begin_at} END at {end_at}",
            flush=True,
        )
        assert begin_at >= 0
        assert end_at > begin_at
        block = extract_membundle_agents_block(baseline_text)
        assert_delimited_block_nonempty(block)
        assert token in baseline_text
        assert baseline_text != baseline_body, (
            "baseline that omitted the begin comment also left AGENTS.md "
            "unchanged; the begin marker was not what kept the file"
        )


# ---------------------------------------------------------------------------
# H. Independent skips omit only that component
# ---------------------------------------------------------------------------


def test_skip_skill_omits_skill_tree_only():
    """Skip skill: no .agents/skills/membundle-memory/; other three A-quality.

    Arms differ only in the skill skip. The full run is the live baseline
    on which the skill tree with the six documents exists.
    """
    with workspace() as ws:
        rel_skip = unique_leaf("noskill")
        rel_full = unique_leaf("yesskill")
        skip_result, dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_skip, "--no-skill")
        )
        full_result, _full_dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_full,)
        )
        require_bootstrap_success(
            skip_result, (COMPONENT_KNOWLEDGE, COMPONENT_AGENTS, COMPONENT_MAKEFILE)
        )
        require_bootstrap_success(full_result, ALL_COMPONENTS)
        skip_target = ws.resolve(rel_skip)
        full_target = ws.resolve(rel_full)
        skip_skill = skip_target / ".agents" / "skills" / "membundle-memory"
        full_skill = full_target / ".agents" / "skills" / "membundle-memory"
        print(
            f"skip skill dir present={path_is_dir(skip_skill)} "
            f"full skill dir present={path_is_dir(full_skill)}",
            flush=True,
        )
        assert path_is_dir(full_skill), (
            "full-run live baseline did not create .agents/skills/membundle-memory/"
        )
        assert_skill_tree(full_target)
        assert not path_is_dir(skip_skill), (
            "skip-skill left .agents/skills/membundle-memory/ in place"
        )
        assert_knowledge_scaffold(skip_target, dates, project_name=rel_skip)
        assert_agents_file_missing_write(skip_target / "AGENTS.md", rel_skip)
        assert_makefile_convenience_tasks(skip_target / "Makefile")


def test_skip_skill_does_not_delete_preexisting_skill_files():
    """Skip-skill leaves seeded skill files; omitting the skip replaces them.

    The two arms differ only by the skill skip and start from the same
    stub bytes. Byte equality is the skip arm. The other arm must replace
    each stub, so a bootstrap that never writes skills cannot pass.
    """
    with workspace() as ws:
        rel_skip = unique_leaf("keepskill")
        rel_full = unique_leaf("replaceskill")
        token = unique_leaf("preexist")
        seeded: dict[str, bytes] = {}
        for rel in (rel_skip, rel_full):
            skill = ws.resolve(rel) / ".agents" / "skills" / "membundle-memory"
            skill.mkdir(parents=True)
            for name in SKILL_FILENAMES:
                text = f"KEEP-{name}-{token}\n"
                (skill / name).write_text(text, encoding="utf-8")
                seeded[name] = text.encode("utf-8")
        skip_result, dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_skip, "--no-skill")
        )
        full_result, _full_dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_full,)
        )
        require_bootstrap_success(
            skip_result, (COMPONENT_KNOWLEDGE, COMPONENT_AGENTS, COMPONENT_MAKEFILE)
        )
        require_bootstrap_success(full_result, ALL_COMPONENTS)
        skip_skill = ws.resolve(rel_skip) / ".agents" / "skills" / "membundle-memory"
        full_skill = ws.resolve(rel_full) / ".agents" / "skills" / "membundle-memory"
        for name, raw in seeded.items():
            skip_after = read_bytes(skip_skill / name)
            full_body = read_file(full_skill / name)
            print(
                f"preexisting {name} skip_unchanged={skip_after == raw} "
                f"full_stub_gone={raw.decode('utf-8') not in full_body}",
                flush=True,
            )
            assert skip_after == raw, f"skip-skill deleted or replaced {name}"
            assert raw.decode("utf-8") not in full_body, (
                f"skill install left the pre-existing stub in {name}"
            )
            assert len(full_body) > 0, f"replaced skill file is empty: {name}"
        assert_knowledge_scaffold(
            ws.resolve(rel_skip), dates, project_name=rel_skip
        )
        assert_agents_file_missing_write(
            ws.resolve(rel_skip) / "AGENTS.md", rel_skip
        )
        assert_makefile_convenience_tasks(ws.resolve(rel_skip) / "Makefile")


def test_skip_agents_md_leaves_file_uncreated():
    """Skip AGENTS.md: that file is uncreated; other three A-quality.

    Arms differ only in the AGENTS.md skip. The full run is the live
    baseline on which AGENTS.md is created with both named delimiters
    and the project name.
    """
    with workspace() as ws:
        rel_skip = unique_leaf("noagents")
        rel_full = unique_leaf("yesagents")
        skip_result, dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_skip, "--no-agents-md")
        )
        full_result, _full_dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_full,)
        )
        require_bootstrap_success(
            skip_result, (COMPONENT_KNOWLEDGE, COMPONENT_SKILL, COMPONENT_MAKEFILE)
        )
        require_bootstrap_success(full_result, ALL_COMPONENTS)
        skip_target = ws.resolve(rel_skip)
        full_target = ws.resolve(rel_full)
        skip_agents = skip_target / "AGENTS.md"
        full_agents = full_target / "AGENTS.md"
        print(
            f"skip AGENTS.md present={path_is_file(skip_agents)} "
            f"full AGENTS.md present={path_is_file(full_agents)}",
            flush=True,
        )
        assert path_is_file(full_agents), (
            "full-run live baseline did not write AGENTS.md"
        )
        assert_agents_file_missing_write(full_agents, rel_full)
        assert not path_is_file(skip_agents), "skip-AGENTS.md created AGENTS.md"
        assert_knowledge_scaffold(skip_target, dates, project_name=rel_skip)
        assert_skill_tree(skip_target)
        assert_makefile_convenience_tasks(skip_target / "Makefile")


def test_skip_makefile_omits_makefile_only():
    """Skip Makefile: file uncreated; report not installed vs full run.

    Arms differ only in the skip-Makefile option. The full run is the live
    baseline that presents Makefile as installed.
    """
    with workspace() as ws:
        rel_skip = unique_leaf("nomake")
        rel_full = unique_leaf("yesmake")
        skip_result, dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_skip, "--no-makefile")
        )
        full_result, _full_dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_full,)
        )
        skip_report = require_bootstrap_success(
            skip_result, (COMPONENT_KNOWLEDGE, COMPONENT_SKILL, COMPONENT_AGENTS)
        )
        full_report = require_bootstrap_success(full_result, ALL_COMPONENTS)
        target = ws.resolve(rel_skip)
        makefile = target / "Makefile"
        full_makefile = ws.resolve(rel_full) / "Makefile"
        print(
            f"skip Makefile present={path_is_file(makefile)} "
            f"full Makefile present={path_is_file(full_makefile)}",
            flush=True,
        )
        assert path_is_file(full_makefile), (
            "full-run live baseline did not write a Makefile"
        )
        assert not path_is_file(makefile), "skip-Makefile created Makefile"
        assert_knowledge_scaffold(target, dates, project_name=rel_skip)
        assert_skill_tree(target)
        assert_agents_file_missing_write(target / "AGENTS.md", rel_skip)
        print(
            f"skip-Makefile report={skip_report!r} "
            f"full-run report={full_report!r}",
            flush=True,
        )
        assert_skip_makefile_report_not_installed(
            full_report,
            skip_report,
            (
                rel_skip,
                rel_full,
                str(target),
                str(ws.resolve(rel_full)),
            ),
            full_path=rel_full,
            skip_path=rel_skip,
        )


def test_skip_bundle_omits_knowledge_scaffold_only():
    """Skip bundle: no new knowledge/ scaffold; other three A-quality.

    Arms differ only in the bundle skip. The full run is the live baseline
    on which knowledge/index.md and knowledge/log.md exist.
    """
    with workspace() as ws:
        rel_skip = unique_leaf("nobundle")
        rel_full = unique_leaf("yesbundle")
        skip_result, dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_skip, "--no-bundle")
        )
        full_result, _full_dates = run_bootstrap_with_dates(
            ws, extra_args=(rel_full,)
        )
        require_bootstrap_success(
            skip_result, (COMPONENT_SKILL, COMPONENT_AGENTS, COMPONENT_MAKEFILE)
        )
        require_bootstrap_success(full_result, ALL_COMPONENTS)
        skip_target = ws.resolve(rel_skip)
        full_target = ws.resolve(rel_full)
        skip_knowledge = skip_target / "knowledge"
        full_index = full_target / "knowledge" / "index.md"
        full_log = full_target / "knowledge" / "log.md"
        print(
            f"skip knowledge dir present={path_is_dir(skip_knowledge)} "
            f"full index present={path_is_file(full_index)} "
            f"full log present={path_is_file(full_log)}",
            flush=True,
        )
        assert path_is_file(full_index), (
            "full-run live baseline did not write knowledge/index.md"
        )
        assert path_is_file(full_log), (
            "full-run live baseline did not write knowledge/log.md"
        )
        assert not path_is_dir(skip_knowledge), (
            "skip-bundle created a knowledge/ scaffold"
        )
        assert_skill_tree(skip_target)
        assert_agents_file_missing_write(skip_target / "AGENTS.md", rel_skip)
        assert_makefile_convenience_tasks(skip_target / "Makefile")
        print(f"skip-bundle spanning dates={sorted(dates)}", flush=True)


# ---------------------------------------------------------------------------
# I. Makefile written only when absent; file provides recipes
# ---------------------------------------------------------------------------


def test_makefile_is_written_with_recipes():
    """After a fresh full bootstrap the Makefile provides the two convenience tasks."""
    with workspace() as ws:
        rel = unique_leaf("makerec")
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        assert_full_bootstrap_quality(ws.resolve(rel), dates, rel, result)
        assert_makefile_convenience_tasks(ws.resolve(rel) / "Makefile")


# ---------------------------------------------------------------------------
# J. Unrelated project files are not deleted; uncreatable target does not succeed
# ---------------------------------------------------------------------------


def test_bootstrap_does_not_delete_unrelated_project_files():
    """Pre-written notes.txt and an extra file remain in the project."""
    with workspace() as ws:
        control = ws.resolve("control-lister")
        control.mkdir()
        (control / "seen.txt").write_text("positive-control\n", encoding="utf-8")
        listed_control = list_dir(control)
        print(f"positive-control list_dir={listed_control}", flush=True)
        assert "seen.txt" in listed_control, (
            "filesystem lister did not see a file the test itself wrote"
        )
        rel = unique_leaf("keepnotes")
        target = ws.resolve(rel)
        target.mkdir()
        token = unique_leaf("notes")
        notes_path = target / "notes.txt"
        extra_path = target / "keep-extra.txt"
        notes_path.write_text(f"NOTES-{token}\n", encoding="utf-8")
        extra_path.write_text(f"EXTRA-{token}\n", encoding="utf-8")
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        assert_full_bootstrap_quality(target, dates, rel, result)
        names = list_dir(target)
        print(f"project list_dir={names}", flush=True)
        assert "notes.txt" in names
        assert "keep-extra.txt" in names


def test_bootstrap_fails_when_parent_path_is_a_file():
    """A named path whose parent is a regular file does not succeed."""
    with workspace() as ws:
        blocker = unique_leaf("blocker")
        ws.write(blocker, "this is a file, not a directory\n")
        fail_rel = f"{blocker}/child"
        fail_result = run_bootstrap(ws, extra_args=(fail_rel,))
        require_bootstrap_failure(fail_result)
        print(
            f"parent-is-file exit={fail_result.returncode}",
            flush=True,
        )
        assert fail_result.returncode != 0, (
            "bootstrap succeeded when the named path's parent is a regular file"
        )


def test_bootstrap_fails_when_target_exists_as_a_file():
    """A named path that exists as a regular file does not succeed."""
    with workspace() as ws:
        fail_rel = unique_leaf("filetgt")
        ws.write(fail_rel, "not a directory\n")
        fail_result = run_bootstrap(ws, extra_args=(fail_rel,))
        require_bootstrap_failure(fail_result)
        print(
            f"target-is-file exit={fail_result.returncode}",
            flush=True,
        )
        assert fail_result.returncode != 0, (
            "bootstrap succeeded when the named path exists as a regular file"
        )


# ---------------------------------------------------------------------------
# K. Full success report names all four not-skipped components
# ---------------------------------------------------------------------------


def test_full_success_report_names_all_four_components():
    """A successful full run names knowledge, the skill tree, AGENTS.md, Makefile."""
    with workspace() as ws:
        rel = unique_leaf("rptfour")
        result, dates = run_bootstrap_with_dates(ws, extra_args=(rel,))
        report = require_bootstrap_success(result, ALL_COMPONENTS)
        print(f"full success report={report!r}", flush=True)
        assert_full_bootstrap_quality(ws.resolve(rel), dates, rel, result)
