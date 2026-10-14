# feature: F05
"""Acceptance tests for creating a concept with index and log bookkeeping (FP-05).

Public entries: the ``membundle create`` command and the ``membundle_create`` Model
Context Protocol tool. Observations go through the sealed harness
``workspace`` / ``invoke`` / ``mcp_batch`` path and the on-disk files
the create wrote or refused to write. These tests do not import Go
packages, do not call internal SaveConcept helpers, and do not use
``membundle show`` / ``membundle validate`` / ``membundle init`` to judge results.
"""

from __future__ import annotations

import os
from pathlib import Path

from _harness import (
    path_is_dir,
    path_is_file,
    read_bytes,
    read_file,
    utc_today_iso,
    workspace,
)
from F01_helpers import (
    combined_report,
    first_heading_text,
    membundle_version_declared,
    split_yaml_frontmatter,
    tz_offset_where_local_date_differs,
    utc_dates_spanning_invoke,
)
from F03_helpers import (
    assert_snapshot_helper_sees_write,
    concept_spec,
    path_tokens_for,
    unique_tokens,
)
from F05_helpers import (
    SAMPLE_IDENTITY,
    SAMPLE_PARENT,
    SAMPLE_TITLE,
    SAMPLE_TYPE,
    SEED_LOG_DATE,
    assert_concept_written,
    assert_creation_absent,
    assert_creation_bullet,
    assert_filename_not_listed,
    assert_instant_in_invoke_window,
    assert_named_path_create_landing,
    assert_nested_index_has_no_membundle_version,
    assert_parent_index_absent,
    assert_parent_listing,
    assert_today_heading_not_duplicated,
    concept_file,
    concept_filename,
    frontmatter_scalar,
    generated_by_and_at,
    heading_texts,
    mcp_create,
    mcp_create_with_instants,
    observe_cli_refusal,
    observe_mcp_refusal,
    mcp_bundle_dir,
    require_create_report_line,
    require_mcp_create_report,
    parent_index_path,
    parse_iso8601_combined_instant,
    require_create_structured_success,
    require_create_success,
    require_create_usage_failure,
    require_mcp_create_success,
    run_create,
    run_create_with_instants,
    seed_bundle,
    tags_mapping_region,
)



# Generated per test process: the leaf a ``..`` identity aims at, outside
# the bundle (the documents carry no such value).
_OUTSIDE_LEAF = f"o{__import__('uuid').uuid4().hex[:8]}"

def _bundle() -> str:
    return unique_tokens("kb")[0]


def _public_desc_body():
    desc, body = unique_tokens("pdesc", "pbody")
    return desc, body


def _assert_written(
    root: Path,
    identity: str,
    *,
    concept_type: str,
    generated_by: str,
    title: str | None = None,
    description: str | None = None,
    body_token: str | None = None,
    unused_body_token: str | None = None,
    unused_description_token: str | None = None,
):
    path = concept_file(root, identity)
    return assert_concept_written(
        path,
        concept_type=concept_type,
        generated_by=generated_by,
        title=title,
        description=description,
        body_token=body_token,
        unused_body_token=unused_body_token,
        unused_description_token=unused_description_token,
    )


def _dates(before: str, after: str) -> frozenset[str]:
    return utc_dates_spanning_invoke(before, after)


# ---------------------------------------------------------------------------
# A. Create writes identity.md with YAML type, generated.by, and body
# ---------------------------------------------------------------------------


def test_cli_generated_sample_writes_file_with_type_and_agent_cli():
    """Named-bundle CLI create of the generated nested sample writes its type and agent/cli."""
    with workspace() as ws:
        desc, body = _public_desc_body()
        rel = _bundle()
        root = seed_bundle(ws, rel)
        result = run_create(
            ws,
            SAMPLE_IDENTITY,
            rel,
            concept_type=SAMPLE_TYPE,
            title=SAMPLE_TITLE,
            description=desc,
            body=body,
        )
        require_create_success(result)
        _assert_written(
            root,
            SAMPLE_IDENTITY,
            concept_type=SAMPLE_TYPE,
            generated_by="agent/cli",
            title=SAMPLE_TITLE,
            description=desc,
            body_token=body,
        )
        assert path_is_dir(root / SAMPLE_PARENT), (
            f"parent directory {SAMPLE_PARENT}/ was not created"
        )
        print("cli public sample wrote Decision with agent/cli", flush=True)


def test_mcp_generated_sample_writes_file_with_type_title_description_and_agent_mcp():
    """MCP create of the generated nested sample stores type, title, description, at, and agent/mcp."""
    with workspace() as ws:
        desc, body = _public_desc_body()
        rel = _bundle()
        root = seed_bundle(ws, rel)
        outcome, before, after = mcp_create_with_instants(
            ws,
            SAMPLE_IDENTITY,
            concept_type=SAMPLE_TYPE,
            title=SAMPLE_TITLE,
            description=desc,
            body=body,
            bundle=rel,
        )
        require_mcp_create_success(outcome)
        mapping, _body = _assert_written(
            root,
            SAMPLE_IDENTITY,
            concept_type=SAMPLE_TYPE,
            generated_by="agent/mcp",
            title=SAMPLE_TITLE,
            description=desc,
            body_token=body,
        )
        _by, at = generated_by_and_at(mapping)
        instant = parse_iso8601_combined_instant(at)
        assert_instant_in_invoke_window(instant, before, after)
        print("mcp public sample wrote Decision with agent/mcp", flush=True)


def test_cli_generated_sample_shape_has_runtime_twin():
    """A runtime-unique CLI create is not the only identity that writes type and body."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "cid", "ctyp", "cttl", "cdsc", "cbod"
        )
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_bundle(ws, rel)
        result = run_create(
            ws,
            ident,
            rel,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
        )
        require_create_success(result)
        _assert_written(
            root,
            ident,
            concept_type=typ,
            generated_by="agent/cli",
            title=title,
            description=desc,
            body_token=body,
        )
        print(f"cli runtime twin ident={ident!r}", flush=True)


def test_mcp_generated_sample_shape_has_runtime_twin():
    """A runtime-unique MCP create is not the only identity that writes type and body."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "mid", "mtyp", "mttl", "mdsc", "mbod"
        )
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_bundle(ws, rel)
        outcome = mcp_create(
            ws,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            bundle=rel,
        )
        require_mcp_create_success(outcome)
        _assert_written(
            root,
            ident,
            concept_type=typ,
            generated_by="agent/mcp",
            title=title,
            description=desc,
            body_token=body,
        )
        print(f"mcp runtime twin ident={ident!r}", flush=True)


# ---------------------------------------------------------------------------
# B. Frontmatter carries type, optional title/description/tags, generated.at
# ---------------------------------------------------------------------------


def test_cli_frontmatter_type_title_description_match_supplied_values():
    """Explicit CLI type/title/description scalars match the supplied values."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "fid", "ftyp", "fttl", "fdsc", "fbod"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        _assert_written(
            root,
            ident,
            concept_type=typ,
            generated_by="agent/cli",
            title=title,
            description=desc,
            body_token=body,
        )
        print("frontmatter scalars match supplied values", flush=True)


def test_cli_omitted_type_writes_fact():
    """CLI omit of type writes frontmatter type Fact."""
    with workspace() as ws:
        ident, title, desc, body = unique_tokens("otid", "ottl", "odsc", "obod")
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(ws, ident, rel, title=title, description=desc, body=body)
        )
        _assert_written(
            root,
            ident,
            concept_type="Fact",
            generated_by="agent/cli",
            title=title,
            body_token=body,
        )
        print("omitted type wrote Fact", flush=True)


def test_cli_omitted_empty_and_whitespace_title_each_use_final_path_segment():
    """CLI omit, empty, and whitespace title each write the identity's final segment."""
    with workspace() as ws:
        leaf_omit, leaf_empty, leaf_ws, typ, desc, body = unique_tokens(
            "ltom", "ltem", "ltws", "ttyp", "tdsc", "tbod"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        cases = (
            ("omit", leaf_omit, None),
            ("empty", leaf_empty, ""),
            ("whitespace", leaf_ws, "   "),
        )
        for label, leaf, title_val in cases:
            ident = f"decisions/{leaf}"
            require_create_success(
                run_create(
                    ws,
                    ident,
                    rel,
                    concept_type=typ,
                    title=title_val,
                    description=desc,
                    body=body,
                )
            )
            mapping, _body = _assert_written(
                root,
                ident,
                concept_type=typ,
                generated_by="agent/cli",
                title=leaf,
                body_token=body,
            )
            found = frontmatter_scalar(mapping, "title")
            print(f"title {label} wrote segment {found!r}", flush=True)
            assert found == leaf, (
                f"CLI {label} title wrote {found!r}, expected final segment {leaf!r}"
            )


def test_cli_omitted_description_succeeds_without_description_value():
    """CLI omit of description succeeds and does not store an unused description token."""
    with workspace() as ws:
        ident, typ, title, unused, body = unique_tokens(
            "odid", "odty", "odtl", "odus", "odbod"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(ws, ident, rel, concept_type=typ, title=title, body=body)
        )
        _assert_written(
            root,
            ident,
            concept_type=typ,
            generated_by="agent/cli",
            title=title,
            unused_description_token=unused,
            body_token=body,
        )
        item = assert_parent_listing(
            parent_index_path(root, ident),
            filename=concept_filename(ident),
            title=title,
            unused_description_token=unused,
        )
        print(f"omitted description listing={item!r}", flush=True)


def test_cli_omitted_body_succeeds_without_unused_body_token():
    """CLI omit of body succeeds and a unique unused body token is absent after the fence."""
    with workspace() as ws:
        ident, typ, title, desc, unused = unique_tokens(
            "obid", "obty", "obtl", "obds", "obus"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws, ident, rel, concept_type=typ, title=title, description=desc
            )
        )
        _assert_written(
            root,
            ident,
            concept_type=typ,
            generated_by="agent/cli",
            title=title,
            unused_body_token=unused,
        )
        print("omitted body has no unused token", flush=True)


def test_cli_body_is_the_post_frontmatter_markdown():
    """A supplied unique body token is present after the closing YAML fence."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "bbid", "bbty", "bbtl", "bbds", "bbod"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        _assert_written(
            root,
            ident,
            concept_type=typ,
            generated_by="agent/cli",
            body_token=body,
        )
        print("supplied body token is post-fence", flush=True)


def test_cli_comma_separated_tags_are_each_a_mapping_scalar():
    """CLI comma-separated tags succeed and the written file includes tags."""
    with workspace() as ws:
        ident, typ, title, desc, body, tag_a, tag_b = unique_tokens(
            "tgid", "tgty", "tgtl", "tgds", "tgbod", "tga", "tgb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                tags=f"{tag_a}, {tag_b}",
            )
        )
        mapping, _body = _assert_written(
            root, ident, concept_type=typ, generated_by="agent/cli"
        )
        region = tags_mapping_region(mapping)
        print(f"tags mapping region={region!r}", flush=True)
        assert tag_a in region, (
            f"written file does not include supplied tag {tag_a!r} in tags: "
            f"{region!r}"
        )
        assert tag_b in region, (
            f"written file does not include supplied tag {tag_b!r} in tags: "
            f"{region!r}"
        )


def test_cli_generated_at_is_current_utc_iso8601_combined_datetime():
    """CLI generated.at is combined date-and-time inside the invoke window."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "atid", "atty", "attl", "atds", "atbod"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        result, before, after = run_create_with_instants(
            ws,
            ident,
            rel,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
        )
        require_create_success(result)
        mapping, _body = _assert_written(
            root, ident, concept_type=typ, generated_by="agent/cli"
        )
        _by, at = generated_by_and_at(mapping)
        instant = parse_iso8601_combined_instant(at)
        assert_instant_in_invoke_window(instant, before, after)
        print(f"cli generated.at={at!r}", flush=True)


def test_mcp_generated_at_is_current_utc_iso8601_combined_datetime():
    """MCP generated.at is combined date-and-time inside the invoke window."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "maid", "maty", "matl", "mads", "mabod"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        outcome, before, after = mcp_create_with_instants(
            ws,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            bundle=rel,
        )
        require_mcp_create_success(outcome)
        mapping, _body = _assert_written(
            root, ident, concept_type=typ, generated_by="agent/mcp"
        )
        _by, at = generated_by_and_at(mapping)
        instant = parse_iso8601_combined_instant(at)
        assert_instant_in_invoke_window(instant, before, after)
        print(f"mcp generated.at={at!r}", flush=True)


def test_fresh_create_does_not_invent_verified():
    """Fresh CLI create mapping has no verified key."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "vid", "vty", "vtl", "vds", "vbod"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        _assert_written(
            root, ident, concept_type=typ, generated_by="agent/cli"
        )
        print("fresh create has no verified key", flush=True)


# ---------------------------------------------------------------------------
# C. Parent index lists the new concept; missing nested vs root index
# ---------------------------------------------------------------------------


def test_parent_index_lists_filename_with_title_and_description():
    """Nested parent index lists the filename with title and description."""
    with workspace() as ws:
        desc, body = _public_desc_body()
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws,
                SAMPLE_IDENTITY,
                rel,
                concept_type=SAMPLE_TYPE,
                title=SAMPLE_TITLE,
                description=desc,
                body=body,
            )
        )
        item = assert_parent_listing(
            parent_index_path(root, SAMPLE_IDENTITY),
            filename=concept_filename(SAMPLE_IDENTITY),
            title=SAMPLE_TITLE,
            description=desc,
        )
        print(f"parent listing={item!r}", flush=True)


def test_empty_description_is_omitted_from_parent_listing():
    """Description present vs omitted: only the present arm keeps the token after strip."""
    with workspace() as ws:
        leaf, typ, title, desc, unused, body = unique_tokens(
            "elid", "elty", "eltl", "elds", "elun", "elb"
        )
        nested_ident = f"decisions/{leaf}"
        root_ident = unique_tokens("rlid")[0]
        nested_present, nested_omit, root_present, root_omit = unique_tokens(
            "np", "no", "rp", "ro"
        )
        for rel, ident, description, unused_tok in (
            (nested_present, nested_ident, desc, None),
            (nested_omit, nested_ident, None, unused),
            (root_present, root_ident, desc, None),
            (root_omit, root_ident, None, unused),
        ):
            root = seed_bundle(ws, rel)
            require_create_success(
                run_create(
                    ws,
                    ident,
                    rel,
                    concept_type=typ,
                    title=title,
                    description=description,
                    body=body,
                )
            )
            item = assert_parent_listing(
                parent_index_path(root, ident),
                filename=concept_filename(ident),
                title=title,
                description=description,
                unused_description_token=unused_tok,
            )
            print(f"listing contrast ident={ident!r} item={item!r}", flush=True)


def test_root_level_listing_includes_title_and_description():
    """A root-level create lists filename, title, and supplied description."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "rtid", "rtty", "rttl", "rtds", "rtbod"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        item = assert_parent_listing(
            root / "index.md",
            filename=concept_filename(ident),
            title=title,
            description=desc,
        )
        print(f"root listing={item!r}", flush=True)


def test_missing_nested_parent_index_is_created_without_membundle_version():
    """A missing nested parent index is created without membundle_version."""
    with workspace() as ws:
        leaf, typ, title, desc, body = unique_tokens(
            "mnid", "mnty", "mntl", "mnds", "mnb"
        )
        ident = f"decisions/{leaf}"
        rel = _bundle()
        root = seed_bundle(ws, rel)
        parent = parent_index_path(root, ident)
        assert not path_is_file(parent)
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        assert_nested_index_has_no_membundle_version(parent)
        assert_parent_listing(
            parent,
            filename=concept_filename(ident),
            title=title,
            description=desc,
        )
        print("nested parent index has no membundle_version", flush=True)


def test_missing_root_parent_index_is_created_with_membundle_version_0_2():
    """A missing root parent index is created declaring membundle_version 0.2."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "mrid", "mrty", "mrtl", "mrds", "mrb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        (root / "index.md").unlink()
        assert not path_is_file(root / "index.md")
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        assert path_is_file(root / "index.md")
        mapping, _body = split_yaml_frontmatter(read_file(root / "index.md"))
        version = membundle_version_declared(mapping)
        assert version == "0.2", f"root index membundle_version is {version!r}, expected 0.2"
        assert_parent_listing(
            root / "index.md",
            filename=concept_filename(ident),
            title=title,
            description=desc,
        )
        print("missing root index declared 0.2", flush=True)


def test_root_level_create_lists_in_existing_root_index():
    """An existing root index lists the new root-level filename with title and description."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "exid", "exty", "extl", "exds", "exb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        assert path_is_file(root / "index.md")
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        assert_parent_listing(
            root / "index.md",
            filename=concept_filename(ident),
            title=title,
            description=desc,
        )
        print("existing root index listed the new filename", flush=True)


def test_nested_create_does_not_write_a_missing_root_index():
    """Nested create into a dir with log.md but no root index leaves root index absent."""
    with workspace() as ws:
        leaf, typ, title, desc, body = unique_tokens(
            "nrid", "nrty", "nrtl", "nrds", "nrb"
        )
        ident = f"decisions/{leaf}"
        rel = _bundle()
        root = seed_bundle(ws, rel)
        (root / "index.md").unlink()
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        assert not path_is_file(root / "index.md"), (
            "nested create wrote a missing root index.md"
        )
        assert_nested_index_has_no_membundle_version(parent_index_path(root, ident))
        print("nested create left missing root index absent", flush=True)


# ---------------------------------------------------------------------------
# D. Log gains a Creation bullet under today's UTC date heading
# ---------------------------------------------------------------------------


def test_log_inserts_today_utc_heading_at_top_with_creation_bullet_naming_the_file():
    """Today's UTC heading is first; older heading remains; Creation names the file."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "lgid", "lgty", "lgtl", "lgds", "lgb"
        )
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_bundle(ws, rel)
        before = utc_today_iso()
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        after = utc_today_iso()
        dates = _dates(before, after)
        log_path = root / "log.md"
        headings = heading_texts(read_file(log_path))
        print(f"log headings={headings!r} dates={sorted(dates)}", flush=True)
        assert headings[0] in dates, (
            f"today's UTC heading was not inserted at the top; headings={headings!r}"
        )
        assert SEED_LOG_DATE in headings, (
            f"older seed heading {SEED_LOG_DATE!r} is missing; headings={headings!r}"
        )
        assert headings.index(SEED_LOG_DATE) > 0
        assert_creation_bullet(
            log_path,
            identity=ident,
            filename=concept_filename(ident),
            today=before,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            expect_first_heading=True,
            allowed_dates=dates,
        )


def test_log_reuses_existing_today_heading_without_duplicating_it():
    """An existing today heading is reused exactly once; Creation sits in that section."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "reid", "rety", "retl", "reds", "reb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        today = utc_today_iso()
        (root / "log.md").write_text(
            f"## {today}\n\n- already\n\n## {SEED_LOG_DATE}\n\n- seed\n",
            encoding="utf-8",
        )
        before = utc_today_iso()
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        after = utc_today_iso()
        dates = _dates(before, after)
        log_path = root / "log.md"
        assert_today_heading_not_duplicated(log_path, today, dates)
        assert_creation_bullet(
            log_path,
            identity=ident,
            filename=concept_filename(ident),
            today=today,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=dates,
        )
        print("today heading was not duplicated", flush=True)


def test_cli_log_heading_uses_utc_date_not_process_local_timezone():
    """CLI log heading date digits are UTC today, not the process-local date."""
    tz_value, local_date = tz_offset_where_local_date_differs()
    print(f"cli TZ contrast tz={tz_value!r} local={local_date}", flush=True)
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "tzid", "tzty", "tztl", "tzds", "tzb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        before = utc_today_iso()
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                env_updates={"TZ": tz_value},
            )
        )
        after = utc_today_iso()
        dates = _dates(before, after)
        assert local_date not in dates, (
            f"local date {local_date} collided with UTC dates {sorted(dates)}"
        )
        heading = first_heading_text(read_file(root / "log.md"))
        print(f"cli offset heading={heading!r}", flush=True)
        assert heading in dates
        assert heading != local_date
        assert_creation_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=before,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=dates,
        )


def test_mcp_log_heading_uses_utc_date_not_process_local_timezone():
    """MCP log heading date digits are UTC today, not the process-local date."""
    tz_value, local_date = tz_offset_where_local_date_differs()
    print(f"mcp TZ contrast tz={tz_value!r} local={local_date}", flush=True)
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "mzid", "mzty", "mztl", "mzds", "mzb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        before = utc_today_iso()
        outcome = mcp_create(
            ws,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            bundle=rel,
            env_updates={"TZ": tz_value},
        )
        after = utc_today_iso()
        require_mcp_create_success(outcome)
        dates = _dates(before, after)
        assert local_date not in dates
        heading = first_heading_text(read_file(root / "log.md"))
        print(f"mcp offset heading={heading!r}", flush=True)
        assert heading in dates
        assert heading != local_date
        assert_creation_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=before,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=dates,
        )


# ---------------------------------------------------------------------------
# E. CLI may skip log or index; MCP cannot
# ---------------------------------------------------------------------------


def test_cli_skip_log_does_not_gain_creation_bullet_and_still_lists_in_index():
    """CLI skip-log: no Creation item; parent listing and concept file are written."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "slid", "slty", "sltl", "slds", "slb"
        )
        ident = f"decisions/{ident}"
        skip_rel, live_rel = unique_tokens("slsk", "sllv")
        skip_root = seed_bundle(ws, skip_rel)
        live_root = seed_bundle(ws, live_rel)
        require_create_success(
            run_create(
                ws,
                ident,
                skip_rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                skip_log=True,
            )
        )
        _assert_written(
            skip_root, ident, concept_type=typ, generated_by="agent/cli"
        )
        assert_creation_absent(
            skip_root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            title=title,
            path_tokens=path_tokens_for(skip_rel, ws.path),
        )
        assert_parent_listing(
            parent_index_path(skip_root, ident),
            filename=concept_filename(ident),
            title=title,
            description=desc,
        )
        before = utc_today_iso()
        require_create_success(
            run_create(
                ws,
                ident,
                live_rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        after = utc_today_iso()
        assert_creation_bullet(
            live_root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=before,
            title=title,
            path_tokens=path_tokens_for(live_rel, ws.path),
            allowed_dates=_dates(before, after),
        )
        print("skip-log omitted Creation; live twin wrote it", flush=True)


def test_cli_skip_index_does_not_create_a_missing_parent_index_and_still_writes_creation_bullet():
    """CLI skip-index with missing parent: parent stays absent; Creation is written."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "siid", "sity", "sitl", "sids", "sib"
        )
        ident = f"decisions/{ident}"
        skip_rel, live_rel = unique_tokens("sisk", "silv")
        skip_root = seed_bundle(ws, skip_rel)
        live_root = seed_bundle(ws, live_rel)
        before = utc_today_iso()
        require_create_success(
            run_create(
                ws,
                ident,
                skip_rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                skip_index=True,
            )
        )
        _assert_written(
            skip_root, ident, concept_type=typ, generated_by="agent/cli"
        )
        assert_parent_index_absent(parent_index_path(skip_root, ident))
        assert_creation_bullet(
            skip_root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=before,
            title=title,
            path_tokens=path_tokens_for(skip_rel, ws.path),
            allowed_dates=_dates(before, utc_today_iso()),
        )
        require_create_success(
            run_create(
                ws,
                ident,
                live_rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        assert_parent_listing(
            parent_index_path(live_root, ident),
            filename=concept_filename(ident),
            title=title,
            description=desc,
        )
        print("skip-index left missing parent absent; live twin listed", flush=True)


def test_cli_skip_index_does_not_list_in_an_existing_parent_index_and_still_writes_creation_bullet():
    """CLI skip-index with existing parent: filename is not listed; Creation is written."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "seid", "sety", "setl", "seds", "seb"
        )
        ident = f"decisions/{ident}"
        filename = concept_filename(ident)
        skip_rel, live_rel = unique_tokens("sesk", "selv")
        skip_root = seed_bundle(ws, skip_rel)
        live_root = seed_bundle(ws, live_rel)
        parent = parent_index_path(skip_root, ident)
        parent.parent.mkdir(parents=True, exist_ok=True)
        parent.write_text("# Decisions\n\n- seed listing\n", encoding="utf-8")
        live_parent = parent_index_path(live_root, ident)
        live_parent.parent.mkdir(parents=True, exist_ok=True)
        live_parent.write_text("# Decisions\n\n- seed listing\n", encoding="utf-8")
        before = utc_today_iso()
        require_create_success(
            run_create(
                ws,
                ident,
                skip_rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                skip_index=True,
            )
        )
        _assert_written(
            skip_root, ident, concept_type=typ, generated_by="agent/cli"
        )
        assert_filename_not_listed(parent, filename)
        assert_creation_bullet(
            skip_root / "log.md",
            identity=ident,
            filename=filename,
            today=before,
            title=title,
            path_tokens=path_tokens_for(skip_rel, ws.path),
            allowed_dates=_dates(before, utc_today_iso()),
        )
        require_create_success(
            run_create(
                ws,
                ident,
                live_rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        assert_parent_listing(
            live_parent, filename=filename, title=title, description=desc
        )
        print("skip-index did not list existing parent; live twin listed", flush=True)


def test_mcp_create_always_writes_parent_listing_and_creation_bullet():
    """MCP create always writes the parent listing and Creation bullet."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "mcid", "mcty", "mctl", "mcds", "mcb"
        )
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_bundle(ws, rel)
        before = utc_today_iso()
        outcome = mcp_create(
            ws,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            bundle=rel,
        )
        after = utc_today_iso()
        require_mcp_create_success(outcome)
        _assert_written(
            root, ident, concept_type=typ, generated_by="agent/mcp"
        )
        assert_parent_listing(
            parent_index_path(root, ident),
            filename=concept_filename(ident),
            title=title,
            description=desc,
        )
        assert_creation_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=before,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(before, after),
        )
        print("mcp always bookkept listing and Creation", flush=True)


# ---------------------------------------------------------------------------
# F. Actor strings
# ---------------------------------------------------------------------------


def test_cli_omitted_actor_writes_agent_cli():
    """CLI omit of actor writes generated.by agent/cli."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "acid", "acty", "actl", "acds", "acb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        _assert_written(
            root, ident, concept_type=typ, generated_by="agent/cli"
        )
        print("omitted actor wrote agent/cli", flush=True)


def test_cli_empty_and_whitespace_actor_each_write_agent_membundle_tool():
    """CLI empty and whitespace actor each write generated.by agent/membundle-tool."""
    with workspace() as ws:
        empty_id, ws_id, typ, title, desc, body = unique_tokens(
            "aeid", "awid", "aety", "aetl", "aeds", "aeb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        for ident, actor in ((empty_id, ""), (ws_id, "   ")):
            require_create_success(
                run_create(
                    ws,
                    ident,
                    rel,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                    actor=actor,
                )
            )
            _assert_written(
                root, ident, concept_type=typ, generated_by="agent/membundle-tool"
            )
        print("empty/whitespace actor wrote agent/membundle-tool", flush=True)


def test_cli_supplied_producer_slash_actor_is_written_as_generated_by():
    """A producer-slash-version actor is written through as generated.by."""
    with workspace() as ws:
        ident, typ, title, desc, body, left, right = unique_tokens(
            "psid", "psty", "pstl", "psds", "psb", "psl", "psr"
        )
        actor = f"{left}/{right}"
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                actor=actor,
            )
        )
        _assert_written(root, ident, concept_type=typ, generated_by=actor)
        print(f"producer-slash actor={actor!r}", flush=True)


def test_cli_supplied_prefix_colon_actor_is_written_as_generated_by():
    """A prefix-colon-id actor is written through as generated.by."""
    with workspace() as ws:
        ident, typ, title, desc, body, prefix, rest = unique_tokens(
            "pcid", "pcty", "pctl", "pcds", "pcb", "pcp", "pcr"
        )
        actor = f"{prefix}:{rest}"
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                actor=actor,
            )
        )
        _assert_written(root, ident, concept_type=typ, generated_by=actor)
        print(f"prefix-colon actor={actor!r}", flush=True)


def test_mcp_generated_by_is_agent_mcp():
    """MCP create writes generated.by agent/mcp with no actor argument."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "mgid", "mgty", "mgtl", "mgds", "mgb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_mcp_create_success(
            mcp_create(
                ws,
                ident,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                bundle=rel,
            )
        )
        _assert_written(
            root, ident, concept_type=typ, generated_by="agent/mcp"
        )
        print("mcp generated.by is agent/mcp", flush=True)


# ---------------------------------------------------------------------------
# G. Structured CLI output names identity and path
# ---------------------------------------------------------------------------


def test_structured_cli_names_this_run_identity_and_path():
    """Structured CLI success names this run's identity and a distinct path string."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "stid", "stty", "sttl", "stds", "stb"
        )
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_bundle(ws, rel)
        result = run_create(
            ws,
            ident,
            rel,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            structured=True,
        )
        require_create_structured_success(result, ident, concept_filename(ident))
        _assert_written(
            root,
            ident,
            concept_type=typ,
            generated_by="agent/cli",
            title=title,
            description=desc,
            body_token=body,
        )
        print("structured named this-run identity and path", flush=True)


def test_human_mode_still_writes_concept_files():
    """Default (no structured flag) still writes the concept file."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "hmid", "hmty", "hmtl", "hmds", "hmb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        _assert_written(
            root, ident, concept_type=typ, generated_by="agent/cli", body_token=body
        )
        print("human mode wrote concept files", flush=True)


# ---------------------------------------------------------------------------
# H. Overwrite still bookkeeps as a creation
# ---------------------------------------------------------------------------


def test_overwrite_replaces_concept_file_and_bookkeeps_as_creation():
    """CLI overwrite replaces file fields and bookkeeps as a Creation."""
    with workspace() as ws:
        (
            leaf,
            typ,
            old_title,
            old_desc,
            old_body,
            new_title,
            new_desc,
            new_body,
        ) = unique_tokens(
            "owid", "owty", "owot", "owod", "owob", "ownt", "ownd", "ownb"
        )
        ident = f"decisions/{leaf}"
        rel = _bundle()
        root = seed_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=old_title,
                    description=old_desc,
                    body=f"{old_body}\n",
                )
            ],
        )
        filename = concept_filename(ident)
        parent = parent_index_path(root, ident)
        parent.parent.mkdir(parents=True, exist_ok=True)
        parent.write_text(
            f"# Decisions\n\n* [{old_title}]({filename}) - {old_desc}\n",
            encoding="utf-8",
        )
        before_text = read_file(concept_file(root, ident))
        assert old_body in before_text
        before = utc_today_iso()
        result, inst_before, inst_after = run_create_with_instants(
            ws,
            ident,
            rel,
            concept_type=typ,
            title=new_title,
            description=new_desc,
            body=new_body,
        )
        require_create_success(result)
        mapping, body = _assert_written(
            root,
            ident,
            concept_type=typ,
            generated_by="agent/cli",
            title=new_title,
            description=new_desc,
            body_token=new_body,
        )
        assert old_body not in body
        _by, at = generated_by_and_at(mapping)
        assert_instant_in_invoke_window(
            parse_iso8601_combined_instant(at), inst_before, inst_after
        )
        assert_parent_listing(
            parent, filename=filename, title=new_title, description=new_desc
        )
        assert_creation_bullet(
            root / "log.md",
            identity=ident,
            filename=filename,
            today=before,
            title=new_title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(before, utc_today_iso()),
        )
        print("cli overwrite bookkept as Creation", flush=True)


def test_mcp_overwrite_replaces_concept_file_and_bookkeeps_as_creation():
    """MCP overwrite replaces file fields, actor agent/mcp, Creation bullet."""
    with workspace() as ws:
        (
            leaf,
            typ,
            old_title,
            old_desc,
            old_body,
            new_title,
            new_desc,
            new_body,
        ) = unique_tokens(
            "mwid", "mwty", "mwot", "mwod", "mwob", "mwnt", "mwnd", "mwnb"
        )
        ident = f"decisions/{leaf}"
        rel = _bundle()
        root = seed_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=old_title,
                    description=old_desc,
                    body=f"{old_body}\n",
                )
            ],
        )
        filename = concept_filename(ident)
        parent = parent_index_path(root, ident)
        parent.parent.mkdir(parents=True, exist_ok=True)
        parent.write_text(
            f"# Decisions\n\n* [{old_title}]({filename}) - {old_desc}\n",
            encoding="utf-8",
        )
        assert old_body in read_file(concept_file(root, ident))
        before = utc_today_iso()
        outcome, inst_before, inst_after = mcp_create_with_instants(
            ws,
            ident,
            concept_type=typ,
            title=new_title,
            description=new_desc,
            body=new_body,
            bundle=rel,
        )
        require_mcp_create_success(outcome)
        mapping, body = _assert_written(
            root,
            ident,
            concept_type=typ,
            generated_by="agent/mcp",
            title=new_title,
            description=new_desc,
            body_token=new_body,
        )
        assert old_body not in body
        _by, at = generated_by_and_at(mapping)
        assert_instant_in_invoke_window(
            parse_iso8601_combined_instant(at), inst_before, inst_after
        )
        assert_parent_listing(
            parent, filename=filename, title=new_title, description=new_desc
        )
        assert_creation_bullet(
            root / "log.md",
            identity=ident,
            filename=filename,
            today=before,
            title=new_title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(before, utc_today_iso()),
        )
        print("mcp overwrite bookkept as Creation", flush=True)


# ---------------------------------------------------------------------------
# I. Omit-path default bundle landing
# ---------------------------------------------------------------------------


def test_omit_path_without_knowledge_dir_writes_cwd():
    """Omit bundle path with no knowledge/ directory lands the file at cwd."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "opid", "opty", "optl", "opds", "opb"
        )
        seed_bundle(ws, ".")
        require_create_success(
            run_create(
                ws, ident, concept_type=typ, title=title, description=desc, body=body
            )
        )
        assert path_is_file(ws.path / f"{ident}.md")
        assert not path_is_file(ws.path / "knowledge" / f"{ident}.md")
        print("omit-path without knowledge/ wrote cwd", flush=True)


def test_omit_path_with_knowledge_dir_writes_knowledge_not_cwd():
    """Omit bundle path with knowledge/ as a directory lands under knowledge/, not cwd."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "okid", "okty", "oktl", "okds", "okb"
        )
        seed_bundle(ws, "knowledge")
        require_create_success(
            run_create(
                ws, ident, concept_type=typ, title=title, description=desc, body=body
            )
        )
        assert path_is_file(ws.path / "knowledge" / f"{ident}.md")
        assert not path_is_file(ws.path / f"{ident}.md"), (
            "omit-path wrote cwd while knowledge/ existed"
        )
        print("omit-path with knowledge/ wrote knowledge not cwd", flush=True)


def test_omit_path_knowledge_file_is_not_treated_as_bundle_dir():
    """A file named knowledge is not a directory, so omit-path uses cwd."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "ofid", "ofty", "oftl", "ofds", "ofb"
        )
        seed_bundle(ws, ".")
        knowledge_file = ws.path / "knowledge"
        knowledge_file.write_text("not-a-directory\n", encoding="utf-8")
        before = read_bytes(knowledge_file)
        require_create_success(
            run_create(
                ws, ident, concept_type=typ, title=title, description=desc, body=body
            )
        )
        assert knowledge_file.is_file()
        assert read_bytes(knowledge_file) == before
        assert path_is_file(ws.path / f"{ident}.md")
        print("knowledge file was not treated as a bundle dir", flush=True)


def test_explicit_bundle_path_is_not_overridden_by_cwd_knowledge():
    """A named bundle path is the write target even when cwd has knowledge/."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "ebid", "ebty", "ebtl", "ebds", "ebb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        seed_bundle(ws, "knowledge")
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        assert path_is_file(root / f"{ident}.md")
        assert not path_is_file(ws.path / "knowledge" / f"{ident}.md")
        print("named bundle was not overridden by cwd knowledge/", flush=True)


def test_mcp_omit_bundle_without_knowledge_dir_writes_cwd():
    """MCP omit bundle, no knowledge/ directory: file lands at cwd."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "mpid", "mpty", "mptl", "mpds", "mpb"
        )
        seed_bundle(ws, ".")
        require_mcp_create_success(
            mcp_create(
                ws,
                ident,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        assert path_is_file(ws.path / f"{ident}.md")
        assert not path_is_file(ws.path / "knowledge" / f"{ident}.md")
        print("mcp omit-bundle without knowledge/ wrote cwd", flush=True)


def test_mcp_omit_bundle_with_knowledge_dir_writes_knowledge_not_cwd():
    """MCP omit bundle with knowledge/ as a directory lands under knowledge/, not cwd."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "mkid", "mkty", "mktl", "mkds", "mkb"
        )
        seed_bundle(ws, "knowledge")
        require_mcp_create_success(
            mcp_create(
                ws,
                ident,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        assert path_is_file(ws.path / "knowledge" / f"{ident}.md")
        assert not path_is_file(ws.path / f"{ident}.md"), (
            "mcp omit-bundle wrote cwd while knowledge/ existed"
        )
        print("mcp omit-bundle with knowledge/ wrote knowledge not cwd", flush=True)


def test_mcp_named_bundle_is_not_overridden_by_cwd_knowledge():
    """MCP named bundle writes there even when cwd has a knowledge/ decoy of the same identity."""
    with workspace() as ws:
        ident, typ, title, desc, body, decoy = unique_tokens(
            "mnbid", "mnbty", "mnbtl", "mnbds", "mnbb", "mnbdk"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        decoy_dir = ws.path / "knowledge"
        decoy_dir.mkdir()
        decoy_path = decoy_dir / f"{ident}.md"
        decoy_path.write_text(decoy, encoding="utf-8")
        require_mcp_create_success(
            mcp_create(
                ws,
                ident,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                bundle=rel,
            )
        )
        assert path_is_file(root / f"{ident}.md")
        assert decoy_path.read_text(encoding="utf-8") == decoy
        print("mcp named bundle ignored cwd knowledge decoy", flush=True)


def test_named_path_without_root_index_writes_named_path_not_nested_knowledge():
    """Named path with no root index.md and a nested knowledge/ writes at the named path."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "nkid", "nkty", "nktl", "nkds", "nkb"
        )
        rel = unique_tokens("nkrel")[0]
        nested = seed_bundle(ws, f"{rel}/knowledge")
        named = ws.path / rel
        assert not path_is_file(named / "index.md")
        assert path_is_dir(named / "knowledge")
        nested_index_before = read_bytes(nested / "index.md")
        nested_log_before = read_bytes(nested / "log.md")
        before = utc_today_iso()
        result = run_create(
            ws,
            ident,
            rel,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
        )
        after = utc_today_iso()
        report = require_create_success(result)
        assert_named_path_create_landing(
            named,
            nested,
            ident,
            concept_type=typ,
            generated_by="agent/cli",
            title=title,
            description=desc,
            body_token=body,
            nested_index_before=nested_index_before,
            nested_log_before=nested_log_before,
            today=before,
            allowed_dates=_dates(before, after),
            path_tokens=path_tokens_for(rel, named, ws.path),
        )
        require_create_report_line(result, ident, title, rel)
        print("cli named path wrote at named root, not nested knowledge/", flush=True)


def test_mcp_named_path_without_root_index_writes_named_path_not_nested_knowledge():
    """MCP named path with no root index.md and a nested knowledge/ writes at the named path."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "mnkid", "mnkty", "mnktl", "mnkds", "mnkb"
        )
        rel = unique_tokens("mnkrel")[0]
        nested = seed_bundle(ws, f"{rel}/knowledge")
        named = ws.path / rel
        assert not path_is_file(named / "index.md")
        assert path_is_dir(named / "knowledge")
        nested_index_before = read_bytes(nested / "index.md")
        nested_log_before = read_bytes(nested / "log.md")
        before = utc_today_iso()
        outcome = mcp_create(
            ws,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            bundle=rel,
        )
        after = utc_today_iso()
        require_mcp_create_success(outcome)
        assert_named_path_create_landing(
            named,
            nested,
            ident,
            concept_type=typ,
            generated_by="agent/mcp",
            title=title,
            description=desc,
            body_token=body,
            nested_index_before=nested_index_before,
            nested_log_before=nested_log_before,
            today=before,
            allowed_dates=_dates(before, after),
            path_tokens=path_tokens_for(rel, named, ws.path),
        )
        require_mcp_create_report(outcome, ident, mcp_bundle_dir(ws, rel))
        print("mcp named path wrote at named root, not nested knowledge/", flush=True)


# ---------------------------------------------------------------------------
# J. Invalid, reserved, and escaping identities
# ---------------------------------------------------------------------------


def _live_cli_write(ws, rel: str) -> None:
    ident, typ, title, desc, body = unique_tokens(
        "lvid", "lvty", "lvtl", "lvds", "lvb"
    )
    require_create_success(
        run_create(
            ws,
            ident,
            rel,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
        )
    )
    assert path_is_file(concept_file(ws.resolve(rel), ident))


def _live_mcp_write(ws, rel: str) -> None:
    ident, typ, title, desc, body = unique_tokens(
        "lmvid", "lmvty", "lmvtl", "lmvds", "lmvb"
    )
    require_mcp_create_success(
        mcp_create(
            ws,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            bundle=rel,
        )
    )
    assert path_is_file(concept_file(ws.resolve(rel), ident))


def test_empty_identity_fails_without_writing():
    """Empty identity fails without writing on CLI and MCP."""
    with workspace() as ws:
        typ, title, desc = unique_tokens("eeid", "eety", "eeds")
        rel = _bundle()
        seed_bundle(ws, rel)
        observe_cli_refusal(
            ws, "", rel, concept_type=typ, title=title, description=desc
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": "",
                "type": typ,
                "title": title,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
        )
        _live_cli_write(ws, rel)
        print("empty identity refused on CLI and MCP", flush=True)


def test_absolute_identity_fails_without_writing():
    """An absolute-path identity fails without writing on CLI and MCP."""
    with workspace() as ws:
        leaf, typ, title, desc = unique_tokens("abid", "abty", "abtl", "abds")
        ident = f"/{leaf}"
        rel = _bundle()
        seed_bundle(ws, rel)
        observe_cli_refusal(
            ws, ident, rel, concept_type=typ, title=title, description=desc
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": typ,
                "title": title,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
        )
        _live_cli_write(ws, rel)
        print("absolute identity refused", flush=True)


def test_dotdot_identity_fails_and_does_not_write_outside_the_bundle():
    """../outside and foo/../outside fail; nothing is written outside the bundle."""
    with workspace() as ws:
        typ, title, desc = unique_tokens("ddty", "ddtl", "ddds")
        rel = _bundle()
        seed_bundle(ws, rel)
        assert_snapshot_helper_sees_write(ws, unique_tokens("snap")[0])
        outside = ws.path / f"{_OUTSIDE_LEAF}.md"
        nested_outside = ws.path / _OUTSIDE_LEAF
        for ident in (f"../{_OUTSIDE_LEAF}", f"foo/../{_OUTSIDE_LEAF}"):
            observe_cli_refusal(
                ws, ident, rel, concept_type=typ, title=title, description=desc
            )
            observe_mcp_refusal(
                ws,
                {
                    "concept_id": ident,
                    "type": typ,
                    "title": title,
                    "description": desc,
                    "bundle": rel,
                },
                bundle_rel=rel,
                request_id=20 + len(ident),
            )
        assert not outside.exists(), "create of ../outside wrote a file outside the bundle"
        assert not nested_outside.exists()
        _live_cli_write(ws, rel)
        print("dotdot identities did not write outside the bundle", flush=True)


def test_leading_hyphen_identity_fails_without_writing():
    """A leading-hyphen identity fails without writing on CLI and MCP."""
    with workspace() as ws:
        leaf, typ, title, desc = unique_tokens("hyid", "hyty", "hytl", "hyds")
        ident = f"-{leaf}"
        rel = _bundle()
        seed_bundle(ws, rel)
        observe_cli_refusal(
            ws, ident, rel, concept_type=typ, title=title, description=desc
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": typ,
                "title": title,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
        )
        _live_cli_write(ws, rel)
        print("leading-hyphen identity refused", flush=True)


def test_cli_newline_cr_and_tab_identities_each_fail_without_writing():
    """CLI newline, CR, and tab identities each fail without writing."""
    with workspace() as ws:
        left, right, typ, title, desc = unique_tokens(
            "clid", "crid", "clty", "cltl", "clds"
        )
        rel = _bundle()
        seed_bundle(ws, rel)
        for ident in (f"{left}\n{right}", f"{left}\r{right}", f"{left}\t{right}"):
            observe_cli_refusal(
                ws, ident, rel, concept_type=typ, title=title, description=desc
            )
        _live_cli_write(ws, rel)
        print("cli control-character identities refused", flush=True)


def test_mcp_null_byte_identity_is_tool_error_and_writes_nothing():
    """MCP create of a null-byte identity is a tool error and writes no concept.

    Arms differ only in whether the identity string contains a null byte.
    The same type and title on an otherwise well-formed identity succeed
    and write the file. Command-line create is not required to demonstrate
    a null-byte identity.
    """
    with workspace() as ws:
        left, right, typ, title, desc = unique_tokens(
            "nbid", "nbrid", "nbty", "nbtl", "nbds"
        )
        rel = _bundle()
        seed_bundle(ws, rel)
        bad_ident = f"{left}\x00{right}"
        good_ident = f"{left}{right}"
        observe_mcp_refusal(
            ws,
            {
                "concept_id": bad_ident,
                "type": typ,
                "title": title,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=50,
        )
        outcome = mcp_create(
            ws,
            good_ident,
            concept_type=typ,
            title=title,
            description=desc,
            bundle=rel,
            request_id=51,
        )
        require_mcp_create_success(outcome)
        assert path_is_file(concept_file(ws.resolve(rel), good_ident)), (
            "well-formed identity on the same tool did not write a concept file"
        )
        print(
            "mcp null-byte identity is tool error; well-formed identity writes",
            flush=True,
        )


def test_mcp_newline_cr_tab_and_nul_identities_each_are_tool_errors_and_write_nothing():
    """MCP newline, CR, tab, and NUL identities are tool errors and write nothing."""
    with workspace() as ws:
        left, right, typ, title, desc = unique_tokens(
            "mlid", "mrid", "mlty", "mltl", "mlds"
        )
        rel = _bundle()
        seed_bundle(ws, rel)
        for request_id, ident in enumerate(
            (
                f"{left}\n{right}",
                f"{left}\r{right}",
                f"{left}\t{right}",
                f"{left}\x00{right}",
            ),
            start=30,
        ):
            observe_mcp_refusal(
                ws,
                {
                    "concept_id": ident,
                    "type": typ,
                    "title": title,
                    "description": desc,
                    "bundle": rel,
                },
                bundle_rel=rel,
                request_id=request_id,
            )
        _live_mcp_write(ws, rel)
        print("mcp control-character identities refused", flush=True)


def test_reserved_index_nested_index_root_log_and_root_agents_fail_without_writing():
    """Reserved index, nested index, root log, and root AGENTS fail; reserved files unchanged."""
    with workspace() as ws:
        nest, typ, title, desc = unique_tokens("rsdir", "rsty", "rstl", "rsds")
        rel = _bundle()
        root = seed_bundle(ws, rel, agents="# agents seed\n")
        nested_index = root / nest / "index.md"
        nested_index.parent.mkdir(parents=True, exist_ok=True)
        nested_index.write_text("# nested\n", encoding="utf-8")
        reserved_paths = {
            "index.md": root / "index.md",
            "log.md": root / "log.md",
            "AGENTS.md": root / "AGENTS.md",
            f"{nest}/index.md": nested_index,
        }
        before_bytes = {key: read_bytes(path) for key, path in reserved_paths.items()}
        for ident in ("index", f"{nest}/index", "log", "AGENTS"):
            observe_cli_refusal(
                ws, ident, rel, concept_type=typ, title=title, description=desc
            )
        for key, path in reserved_paths.items():
            assert read_bytes(path) == before_bytes[key], (
                f"reserved file {key} changed after a refusing create"
            )
        _live_cli_write(ws, rel)
        print("reserved identities refused; reserved files unchanged", flush=True)


def test_mcp_reserved_index_nested_index_root_log_and_root_agents_are_tool_errors_and_write_nothing():
    """MCP reserved index / nested index / root log / root AGENTS are tool errors."""
    with workspace() as ws:
        nest, typ, title, desc = unique_tokens("mrdir", "mrty", "mrtl", "mrds")
        rel = _bundle()
        root = seed_bundle(ws, rel, agents="# agents seed\n")
        nested_index = root / nest / "index.md"
        nested_index.parent.mkdir(parents=True, exist_ok=True)
        nested_index.write_text("# nested\n", encoding="utf-8")
        reserved_paths = [root / "index.md", root / "log.md", root / "AGENTS.md", nested_index]
        before_bytes = [read_bytes(path) for path in reserved_paths]
        for request_id, ident in enumerate(
            ("index", f"{nest}/index", "log", "AGENTS"), start=40
        ):
            observe_mcp_refusal(
                ws,
                {
                    "concept_id": ident,
                    "type": typ,
                    "title": title,
                    "description": desc,
                    "bundle": rel,
                },
                bundle_rel=rel,
                request_id=request_id,
            )
        for path, payload in zip(reserved_paths, before_bytes):
            assert read_bytes(path) == payload
        _live_mcp_write(ws, rel)
        print("mcp reserved identities refused", flush=True)


def test_nested_log_and_agents_are_creatable():
    """Nested dir/log and dir/AGENTS succeed on CLI while root log/AGENTS still fail."""
    with workspace() as ws:
        nest, typ, title, desc, body = unique_tokens(
            "nldir", "nlty", "nltl", "nlds", "nlb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel, agents="# agents seed\n")
        for ident in (f"{nest}/log", f"{nest}/AGENTS"):
            require_create_success(
                run_create(
                    ws,
                    ident,
                    rel,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                )
            )
            assert path_is_file(concept_file(root, ident))
        log_bytes = read_bytes(root / "log.md")
        agents_bytes = read_bytes(root / "AGENTS.md")
        observe_cli_refusal(
            ws, "log", rel, concept_type=typ, title=title, description=desc
        )
        observe_cli_refusal(
            ws, "AGENTS", rel, concept_type=typ, title=title, description=desc
        )
        assert read_bytes(root / "log.md") == log_bytes
        assert read_bytes(root / "AGENTS.md") == agents_bytes
        print("nested log/AGENTS creatable; root still reserved", flush=True)


def test_mcp_nested_log_and_agents_are_creatable():
    """Nested dir/log and dir/AGENTS succeed on MCP while root log/AGENTS still fail."""
    with workspace() as ws:
        nest, typ, title, desc, body = unique_tokens(
            "mldir", "mlty", "mltl", "mlds", "mlb"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel, agents="# agents seed\n")
        for ident in (f"{nest}/log", f"{nest}/AGENTS"):
            require_mcp_create_success(
                mcp_create(
                    ws,
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                    bundle=rel,
                )
            )
            assert path_is_file(concept_file(root, ident))
        observe_mcp_refusal(
            ws,
            {
                "concept_id": "log",
                "type": typ,
                "title": title,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=50,
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": "AGENTS",
                "type": typ,
                "title": title,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=51,
        )
        print("mcp nested log/AGENTS creatable; root still reserved", flush=True)


def test_mcp_dotdot_absolute_empty_and_leading_hyphen_are_tool_errors_and_write_nothing():
    """MCP ../outside, absolute, empty, and leading-hyphen identities are tool errors."""
    with workspace() as ws:
        leaf, typ, title, desc = unique_tokens("mxid", "mxty", "mxtl", "mxds")
        rel = _bundle()
        seed_bundle(ws, rel)
        for request_id, ident in enumerate(
            (f"../{_OUTSIDE_LEAF}", f"/{leaf}", "", f"-{leaf}"), start=60
        ):
            observe_mcp_refusal(
                ws,
                {
                    "concept_id": ident,
                    "type": typ,
                    "title": title,
                    "description": desc,
                    "bundle": rel,
                },
                bundle_rel=rel,
                request_id=request_id,
            )
        _live_mcp_write(ws, rel)
        print("mcp invalid-identity set refused", flush=True)


def test_escaping_symlink_write_is_refused():
    """Write through a .md symlink whose target leaves the bundle is refused."""
    with workspace() as ws:
        ident, typ, title, desc, body, secret_leaf = unique_tokens(
            "syid", "syty", "sytl", "syds", "syb", "sysc"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        secret = ws.write(f"{secret_leaf}.md", b"outside-secret\n")
        secret_bytes = secret.read_bytes()
        os.symlink(secret, root / f"{ident}.md")
        assert_snapshot_helper_sees_write(ws, unique_tokens("syc")[0])
        observe_cli_refusal(
            ws, ident, rel, concept_type=typ, title=title, description=desc, body=body
        )
        assert secret.read_bytes() == secret_bytes
        link = root / f"{ident}.md"
        assert link.is_symlink() or not link.exists(), (
            "refusing create replaced the escaping symlink with a regular concept file"
        )
        _live_cli_write(ws, rel)
        print("escaping symlink write refused; outside target unchanged", flush=True)


# ---------------------------------------------------------------------------
# K. Missing identity prints usage and fails
# ---------------------------------------------------------------------------


def test_missing_identity_argument_is_non_success_usage_and_writes_nothing():
    """membundle create with no identity argument is usage-class, unlike empty/reserved/success."""
    with workspace() as ws:
        ident, typ, title, desc, body = unique_tokens(
            "usid", "usty", "ustl", "usds", "usb"
        )
        rel = _bundle()
        seed_bundle(ws, ".")
        seed_bundle(ws, rel)
        paths = path_tokens_for(rel, ws.path)
        success = run_create(
            ws,
            ident,
            rel,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
        )
        require_create_success(success)
        empty = observe_cli_refusal(
            ws, "", rel, concept_type=typ, title=title, description=desc
        )
        reserved = observe_cli_refusal(
            ws, "index", rel, concept_type=typ, title=title, description=desc
        )
        missing = observe_cli_refusal(ws, None, None)
        usage_report = require_create_usage_failure(
            missing,
            empty,
            reserved,
            success,
            ident,
            title,
            rel,
        )
        print("missing identity is usage-class and wrote nothing", flush=True)
        assert missing.returncode != 0, (
            f"create with a missing identity argument succeeded; "
            f"report={usage_report!r}"
        )
        assert usage_report, (
            "create with a missing identity argument produced empty combined "
            "streams"
        )


# ---------------------------------------------------------------------------
# L. Type, title, description, and actor field refusals
# ---------------------------------------------------------------------------


def test_cli_empty_and_whitespace_type_each_fail_without_writing():
    """CLI empty and whitespace type each fail without writing."""
    with workspace() as ws:
        ident, title, desc = unique_tokens("etid", "ettl", "etds")
        rel = _bundle()
        seed_bundle(ws, rel)
        for type_val in ("", "   "):
            observe_cli_refusal(
                ws, ident, rel, concept_type=type_val, title=title, description=desc
            )
        _live_cli_write(ws, rel)
        print("cli empty/whitespace type refused", flush=True)


def test_cli_whitespace_only_description_fails_without_writing():
    """CLI description present but only whitespace fails without writing."""
    with workspace() as ws:
        ident, typ, title = unique_tokens("wdid", "wdty", "wdtl")
        rel = _bundle()
        seed_bundle(ws, rel)
        observe_cli_refusal(
            ws, ident, rel, concept_type=typ, title=title, description="   "
        )
        _live_cli_write(ws, rel)
        print("cli whitespace description refused", flush=True)


def test_cli_newline_in_each_of_type_title_description_and_actor_fails_without_writing():
    """CLI type, title, description, and actor containing a newline each fail without writing."""
    with workspace() as ws:
        ident, typ, title, desc, body, poison = unique_tokens(
            "nlid", "nlty", "nltl", "nlds", "nlb", "nlpo"
        )
        rel = _bundle()
        seed_bundle(ws, rel)
        injected = f"{poison}\nextra"
        observe_cli_refusal(
            ws, ident, rel, concept_type=injected, title=title, description=desc
        )
        observe_cli_refusal(
            ws, ident, rel, concept_type=typ, title=injected, description=desc
        )
        observe_cli_refusal(
            ws, ident, rel, concept_type=typ, title=title, description=injected
        )
        observe_cli_refusal(
            ws,
            ident,
            rel,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            actor=injected,
        )
        _live_cli_write(ws, rel)
        print("cli newline in each named field refused", flush=True)


def test_cli_frontmatter_delimiter_in_each_of_type_title_description_and_actor_fails_without_writing():
    """CLI type, title, description, and actor containing --- each fail without writing."""
    with workspace() as ws:
        ident, typ, title, desc, body, poison = unique_tokens(
            "fmid", "fmty", "fmtl", "fmds", "fmb", "fmpo"
        )
        rel = _bundle()
        seed_bundle(ws, rel)
        injected = f"{poison}---extra"
        observe_cli_refusal(
            ws, ident, rel, concept_type=injected, title=title, description=desc
        )
        observe_cli_refusal(
            ws, ident, rel, concept_type=typ, title=injected, description=desc
        )
        observe_cli_refusal(
            ws, ident, rel, concept_type=typ, title=title, description=injected
        )
        observe_cli_refusal(
            ws,
            ident,
            rel,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            actor=injected,
        )
        _live_cli_write(ws, rel)
        print("cli --- in each named field refused", flush=True)


def test_mcp_newline_in_each_of_type_title_and_description_is_tool_error_and_writes_nothing():
    """MCP type, title, and description containing a newline are tool errors."""
    with workspace() as ws:
        ident, typ, title, desc, poison = unique_tokens(
            "mnfid", "mnfty", "mnftl", "mnfds", "mnfpo"
        )
        rel = _bundle()
        seed_bundle(ws, rel)
        injected = f"{poison}\nextra"
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": injected,
                "title": title,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=70,
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": typ,
                "title": injected,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=71,
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": typ,
                "title": title,
                "description": injected,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=72,
        )
        _live_mcp_write(ws, rel)
        print("mcp newline in each named field refused", flush=True)


def test_mcp_frontmatter_delimiter_in_each_of_type_title_and_description_is_tool_error_and_writes_nothing():
    """MCP type, title, and description containing --- are tool errors."""
    with workspace() as ws:
        ident, typ, title, desc, poison = unique_tokens(
            "mfdid", "mfdty", "mfdtl", "mfdds", "mfdpo"
        )
        rel = _bundle()
        seed_bundle(ws, rel)
        injected = f"{poison}---extra"
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": injected,
                "title": title,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=80,
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": typ,
                "title": injected,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=81,
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": typ,
                "title": title,
                "description": injected,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=82,
        )
        _live_mcp_write(ws, rel)
        print("mcp --- in each named field refused", flush=True)


def test_mcp_omitted_empty_and_whitespace_title_each_is_tool_error_and_writes_nothing():
    """MCP omit, empty, and whitespace title are each a tool error and write no file."""
    with workspace() as ws:
        ident, typ, desc = unique_tokens("mtid", "mtty", "mtds")
        rel = _bundle()
        seed_bundle(ws, rel)
        observe_mcp_refusal(
            ws,
            {"concept_id": ident, "type": typ, "description": desc, "bundle": rel},
            bundle_rel=rel,
            request_id=90,
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": typ,
                "title": "",
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=91,
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": typ,
                "title": "   ",
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=92,
        )
        _live_mcp_write(ws, rel)
        print("mcp omit/empty/whitespace title refused", flush=True)


def test_mcp_omitted_empty_and_whitespace_type_each_is_tool_error_and_writes_nothing():
    """MCP omit, empty, and whitespace type are each a tool error and write no file."""
    with workspace() as ws:
        ident, title, desc = unique_tokens("myid", "mytl", "myds")
        rel = _bundle()
        seed_bundle(ws, rel)
        observe_mcp_refusal(
            ws,
            {"concept_id": ident, "title": title, "description": desc, "bundle": rel},
            bundle_rel=rel,
            request_id=93,
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": "",
                "title": title,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=94,
        )
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": "   ",
                "title": title,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
            request_id=95,
        )
        _live_mcp_write(ws, rel)
        print("mcp omit/empty/whitespace type refused", flush=True)


def test_mcp_omitted_description_succeeds():
    """MCP omit of description succeeds; unused description token is absent."""
    with workspace() as ws:
        ident, typ, title, unused, body = unique_tokens(
            "mdoid", "mdoty", "mdotl", "mdoun", "mdob"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_mcp_create_success(
            mcp_create(
                ws, ident, concept_type=typ, title=title, body=body, bundle=rel
            )
        )
        _assert_written(
            root,
            ident,
            concept_type=typ,
            generated_by="agent/mcp",
            title=title,
            unused_description_token=unused,
            body_token=body,
        )
        print("mcp omitted description succeeded", flush=True)


def test_mcp_omitted_body_succeeds_without_unused_body_token():
    """MCP omit of body succeeds; unique unused body token is absent after the fence."""
    with workspace() as ws:
        ident, typ, title, desc, unused = unique_tokens(
            "mboid", "mboty", "mbotl", "mbods", "mboun"
        )
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_mcp_create_success(
            mcp_create(
                ws,
                ident,
                concept_type=typ,
                title=title,
                description=desc,
                bundle=rel,
            )
        )
        _assert_written(
            root,
            ident,
            concept_type=typ,
            generated_by="agent/mcp",
            unused_body_token=unused,
        )
        print("mcp omitted body has no unused token", flush=True)


def test_mcp_whitespace_only_description_is_tool_error_and_writes_nothing():
    """MCP whitespace-only description is a tool error and writes no file."""
    with workspace() as ws:
        ident, typ, title = unique_tokens("mwdid", "mwdty", "mwdtl")
        rel = _bundle()
        seed_bundle(ws, rel)
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": typ,
                "title": title,
                "description": "   ",
                "bundle": rel,
            },
            bundle_rel=rel,
        )
        _live_mcp_write(ws, rel)
        print("mcp whitespace description refused", flush=True)


def test_mcp_omit_title_on_generated_sample_identity_writes_no_file():
    """MCP create of the generated nested sample that omits title writes no file."""
    with workspace() as ws:
        desc = unique_tokens("psods")[0]
        rel = _bundle()
        root = seed_bundle(ws, rel)
        observe_mcp_refusal(
            ws,
            {
                "concept_id": SAMPLE_IDENTITY,
                "type": SAMPLE_TYPE,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
        )
        assert not path_is_file(concept_file(root, SAMPLE_IDENTITY))
        print("mcp omit title on public-sample identity wrote no file", flush=True)


# ---------------------------------------------------------------------------
# M. MCP create without identity, type, or title is a tool error
# ---------------------------------------------------------------------------


def test_mcp_missing_identity_is_tool_error_and_writes_nothing():
    """MCP tools-call missing concept_id is a tool error, not a protocol error."""
    with workspace() as ws:
        typ, title, desc = unique_tokens("mmity", "mmitl", "mmids")
        rel = _bundle()
        seed_bundle(ws, rel)
        observe_mcp_refusal(
            ws,
            {"type": typ, "title": title, "description": desc, "bundle": rel},
            bundle_rel=rel,
        )
        _live_mcp_write(ws, rel)
        print("mcp missing identity is tool error", flush=True)


def test_mcp_missing_type_is_tool_error_and_writes_nothing():
    """MCP tools-call missing type is a tool error, not a protocol error."""
    with workspace() as ws:
        ident, title, desc = unique_tokens("mmnid", "mmntl", "mmnds")
        rel = _bundle()
        seed_bundle(ws, rel)
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "title": title,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
        )
        _live_mcp_write(ws, rel)
        print("mcp missing type is tool error", flush=True)


def test_mcp_missing_title_is_tool_error_and_writes_nothing():
    """MCP tools-call missing title is a tool error, not a protocol error."""
    with workspace() as ws:
        ident, typ, desc = unique_tokens("mmqid", "mmqty", "mmqds")
        rel = _bundle()
        seed_bundle(ws, rel)
        observe_mcp_refusal(
            ws,
            {
                "concept_id": ident,
                "type": typ,
                "description": desc,
                "bundle": rel,
            },
            bundle_rel=rel,
        )
        _live_mcp_write(ws, rel)
        print("mcp missing title is tool error", flush=True)


# ---------------------------------------------------------------------------
# N. Creating parent directories
# ---------------------------------------------------------------------------


def test_create_makes_missing_parent_directories():
    """A three-segment nested identity creates intermediate dirs; listing is the immediate parent."""
    with workspace() as ws:
        a, b, c, typ, title, desc, body = unique_tokens(
            "pda", "pdb", "pdc", "pdty", "pdtl", "pdds", "pdbod"
        )
        ident = f"{a}/{b}/{c}"
        rel = _bundle()
        root = seed_bundle(ws, rel)
        require_create_success(
            run_create(
                ws,
                ident,
                rel,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
            )
        )
        assert path_is_dir(root / a)
        assert path_is_dir(root / a / b)
        assert path_is_file(root / a / b / f"{c}.md")
        assert not path_is_file(root / f"{c}.md"), (
            "create wrote only the final segment at the bundle root"
        )
        assert_parent_listing(
            parent_index_path(root, ident),
            filename=concept_filename(ident),
            title=title,
            description=desc,
        )
        print("three-segment identity created parent directories", flush=True)
