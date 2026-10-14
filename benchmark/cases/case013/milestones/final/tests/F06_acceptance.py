# feature: F06
"""Acceptance tests for updating an existing concept (FP-06).

Public entries: the ``membundle update`` command and the ``membundle_update`` Model
Context Protocol tool. Observations go through the sealed harness
``workspace`` / ``invoke`` / ``mcp_batch`` path and the on-disk files
the update rewrote or refused to rewrite. These tests do not import Go
packages, do not call internal SaveConcept helpers, and do not use
``membundle show`` / ``membundle validate`` / ``membundle create`` / ``membundle init`` to
judge results.
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
    split_yaml_frontmatter,
    tz_offset_where_local_date_differs,
    utc_dates_spanning_invoke,
)
from F03_helpers import (
    assert_snapshot_helper_sees_write,
    path_tokens_for,
    snapshot_tree,
    unique_tokens,
)
from F05_helpers import (
    SAMPLE_IDENTITY,
    SAMPLE_TYPE,
    SEED_LOG_DATE,
    assert_no_new_concept_file,
    assert_no_verified_key,
    concept_file,
    concept_filename,
    frontmatter_scalar,
    generated_by_and_at,
    heading_texts,
    parent_index_path,
    mcp_bundle_dir,
    tag_scalars,
)
from F06_helpers import (
    SAMPLE_DESC,
    SEED_GENERATED_AT,
    SEED_GENERATED_BY,
    assert_concept_updated,
    assert_description_cleared,
    assert_extra_keys_survive,
    assert_listing_cleared_description,
    assert_listing_follows_description,
    assert_listing_keeps_old_description,
    assert_named_path_update_landing,
    assert_no_successful_rewrite,
    assert_sources_survive,
    assert_update_absent,
    assert_update_bullet,
    assert_verified_survives,
    require_mcp_update_load_failure,
    require_mcp_update_not_found,
    require_mcp_update_report,
    require_update_load_failure,
    require_update_not_found,
    require_update_report_line,
    mcp_membundle_update,
    mcp_update,
    mcp_update_with_instants,
    require_mcp_update_non_success,
    require_mcp_update_success,
    require_mcp_update_tool_error,
    require_update_failure,
    require_update_success,
    require_update_usage_failure,
    run_update,
    run_update_with_instants,
    seed_updatable_concept,
)



# Generated per test process: the leaf a ``..`` identity aims at, outside
# the bundle (the documents carry no such value).
_OUTSIDE_LEAF = f"o{__import__('uuid').uuid4().hex[:8]}"

def _bundle() -> str:
    return unique_tokens("kb")[0]


def _dates(before: str, after: str) -> frozenset[str]:
    return utc_dates_spanning_invoke(before, after)


def _extras(*prefixes: str) -> dict[str, str]:
    keys_vals = unique_tokens(*prefixes)
    if len(keys_vals) != 4:
        k1, v1, k2, v2 = unique_tokens("xk1", "xv1", "xk2", "xv2")
        return {k1.replace("-", "_"): v1, k2.replace("-", "_"): v2}
    k1, v1, k2, v2 = keys_vals
    return {k1.replace("-", "_"): v1, k2.replace("-", "_"): v2}


def _runtime_fields(*more: str):
    tokens = unique_tokens("id", "ty", "tl", "ds", "bd", "xk1", "xv1", "xk2", "xv2", *more)
    ident = tokens[0]
    typ = tokens[1]
    title = tokens[2]
    desc = tokens[3]
    body = tokens[4]
    extra = {
        tokens[5].replace("-", "_"): tokens[6],
        tokens[7].replace("-", "_"): tokens[8],
    }
    rest = tokens[9:]
    return ident, typ, title, desc, body, extra, rest


def _assert_bookkeep(
    root: Path,
    identity: str,
    *,
    new_description: str,
    old_description: str,
    title: str,
    today: str,
    allowed_dates: frozenset[str],
    path_tokens,
) -> None:
    filename = concept_filename(identity)
    assert_listing_follows_description(
        parent_index_path(root, identity),
        identity=identity,
        filename=filename,
        new_description=new_description,
        old_description=old_description,
        title=title,
    )
    assert_update_bullet(
        root / "log.md",
        identity=identity,
        filename=filename,
        today=today,
        title=title,
        path_tokens=path_tokens,
        allowed_dates=allowed_dates,
    )


def _live_cli_rewrite(ws, rel: str) -> None:
    ident, typ, title, desc, body, extra, _rest = _runtime_fields("lvn")
    ident = f"live/{ident}"
    new_desc = unique_tokens("lvdn")[0]
    root = seed_updatable_concept(
        ws,
        rel,
        ident,
        concept_type=typ,
        title=title,
        description=desc,
        body=body,
        extra=extra,
    )
    result, before, after = run_update_with_instants(
        ws, ident, rel, description=new_desc
    )
    require_update_success(result)
    assert_concept_updated(
        concept_file(root, ident),
        concept_type=typ,
        generated_by="agent/cli",
        seed_generated_at=SEED_GENERATED_AT,
        before=before,
        after=after,
        title=title,
        description=new_desc,
        body_token=body,
    )
    print(f"[F06] live cli rewrite {ident!r}", flush=True)


def _live_mcp_rewrite(ws, rel: str) -> None:
    ident, typ, title, desc, body, extra, _rest = _runtime_fields("mvn")
    ident = f"mlive/{ident}"
    new_desc = unique_tokens("mvdn")[0]
    root = seed_updatable_concept(
        ws,
        rel,
        ident,
        concept_type=typ,
        title=title,
        description=desc,
        body=body,
        extra=extra,
    )
    outcome, before, after = mcp_update_with_instants(
        ws, ident, description=new_desc, bundle=rel
    )
    require_mcp_update_success(outcome)
    assert_concept_updated(
        concept_file(root, ident),
        concept_type=typ,
        generated_by="agent/mcp",
        seed_generated_at=SEED_GENERATED_AT,
        before=before,
        after=after,
        title=title,
        description=new_desc,
        body_token=body,
    )
    print(f"[F06] live mcp rewrite {ident!r}", flush=True)


# ---------------------------------------------------------------------------
# A. Description-only update rewrites in place
# ---------------------------------------------------------------------------


def test_cli_generated_sample_description_only_keeps_type_extras_and_refreshes_generated_at():
    """CLI description-only update of a generated nested sample keeps type/extra key, new generated.at, listing, Update."""
    with workspace() as ws:
        identity = SAMPLE_IDENTITY
        old_description = SAMPLE_DESC
        concept_type = SAMPLE_TYPE
        title, body, sentence_token = unique_tokens("ptl", "pbd", "pnd")
        new_desc = f"Prefer {sentence_token}."
        extra = _extras("pxk1", "pxv1", "pxk2", "pxv2")
        custom_key, custom_value = next(iter(extra.items()))
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            identity,
            concept_type=concept_type,
            title=title,
            description=old_description,
            body=body,
            extra=extra,
        )
        before_snap = snapshot_tree(ws.path)
        result, before, after = run_update_with_instants(
            ws, identity, rel, description=new_desc
        )
        today = utc_today_iso()
        require_update_success(result)
        mapping, body_after = assert_concept_updated(
            concept_file(root, identity),
            concept_type=concept_type,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=title,
            description=new_desc,
            body_token=body,
        )
        assert frontmatter_scalar(mapping, "description") == new_desc, (
            "after an update that changes only the description to a new sentence, "
            "the concept does not show the new description"
        )
        assert frontmatter_scalar(mapping, "title") == title, (
            "an update that changes only the description also changed the title"
        )
        assert body in body_after, (
            "an update that changes only the description also changed the body"
        )
        assert frontmatter_scalar(mapping, custom_key) == custom_value, (
            "custom extra frontmatter key did not remain after the rewrite"
        )
        assert custom_key in mapping, (
            "a custom extra frontmatter key is missing from the rewritten mapping"
        )
        assert frontmatter_scalar(mapping, "type") == concept_type, (
            "concept does not still have its original type"
        )
        _by, generated_at = generated_by_and_at(mapping)
        assert generated_at != SEED_GENERATED_AT, (
            "update did not write a new generated.at"
        )
        assert_extra_keys_survive(mapping, extra)
        assert path_is_file(concept_file(root, identity))
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        filename = concept_filename(identity)
        listing_item = assert_listing_follows_description(
            parent_index_path(root, identity),
            identity=identity,
            filename=filename,
            new_description=new_desc,
            old_description=old_description,
            title=title,
        )
        assert new_desc in listing_item, (
            "the parent index listing text does not follow the new description"
        )
        assert old_description not in listing_item, (
            "the parent index listing text still has the old description"
        )
        update_item = assert_update_bullet(
            root / "log.md",
            identity=identity,
            filename=filename,
            today=today,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
        )
        assert update_item, (
            "log.md does not contain an Update bullet for that file under "
            "today's UTC ISO 8601 date"
        )
        log_headings = heading_texts(read_file(root / "log.md"))
        dated = [h for h in log_headings if len(h) == 10 and h[4] == "-" and h[7] == "-"]
        today_hits = [h for h in dated if h in _dates(today, utc_today_iso())]
        assert today_hits, (
            "log.md has no heading whose text is today's UTC ISO 8601 date"
        )
        print(
            "cli sample description-only kept type/extra key and wrote Update",
            flush=True,
        )


def test_mcp_generated_sample_description_only_keeps_type_extras_and_writes_agent_mcp():
    """MCP description-only update of the generated sample writes agent/mcp and bookkeeps."""
    with workspace() as ws:
        title, body, new_desc = unique_tokens("mptl", "mpbd", "mpnd")
        extra = _extras("mpxk1", "mpxv1", "mpxk2", "mpxv2")
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            SAMPLE_IDENTITY,
            concept_type=SAMPLE_TYPE,
            title=title,
            description=SAMPLE_DESC,
            body=body,
            extra=extra,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, SAMPLE_IDENTITY, description=new_desc, bundle=rel
        )
        today = utc_today_iso()
        require_mcp_update_success(outcome)
        mapping, body_after = assert_concept_updated(
            concept_file(root, SAMPLE_IDENTITY),
            concept_type=SAMPLE_TYPE,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=title,
            description=new_desc,
            body_token=body,
        )
        extra_key, extra_value = next(iter(extra.items()))
        assert frontmatter_scalar(mapping, "description") == new_desc, (
            "after an update that changes only the description to a new sentence, "
            "the concept does not show the new description"
        )
        assert frontmatter_scalar(mapping, extra_key) == extra_value, (
            "custom extra frontmatter key did not remain after the rewrite"
        )
        assert frontmatter_scalar(mapping, "type") == SAMPLE_TYPE, (
            "concept does not still have its original type"
        )
        _by, generated_at = generated_by_and_at(mapping)
        assert generated_at != SEED_GENERATED_AT, (
            "update did not write a new generated.at"
        )
        assert_extra_keys_survive(mapping, extra)
        filename = concept_filename(SAMPLE_IDENTITY)
        listing_item = assert_listing_follows_description(
            parent_index_path(root, SAMPLE_IDENTITY),
            identity=SAMPLE_IDENTITY,
            filename=filename,
            new_description=new_desc,
            old_description=SAMPLE_DESC,
            title=title,
        )
        assert new_desc in listing_item, (
            "the parent index listing text does not follow the new description"
        )
        update_item = assert_update_bullet(
            root / "log.md",
            identity=SAMPLE_IDENTITY,
            filename=filename,
            today=today,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
        )
        assert update_item, (
            "log.md does not contain an Update bullet for that file under "
            "today's UTC ISO 8601 date"
        )
        print("mcp public sample description-only wrote agent/mcp", flush=True)


def test_cli_generated_sample_shape_has_runtime_twin():
    """A runtime-unique CLI description-only update is not only the public sample."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        today = utc_today_iso()
        require_update_success(result)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=title,
            description=new_desc,
            body_token=body,
        )
        assert_extra_keys_survive(mapping, extra)
        _assert_bookkeep(
            root,
            ident,
            new_description=new_desc,
            old_description=desc,
            title=title,
            today=today,
            allowed_dates=_dates(today, utc_today_iso()),
            path_tokens=path_tokens_for(rel, ws.path),
        )
        print("cli public-sample shape has runtime twin", flush=True)


def test_mcp_generated_sample_shape_has_runtime_twin():
    """A runtime-unique MCP description-only update is not only the public sample."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, description=new_desc, bundle=rel
        )
        today = utc_today_iso()
        require_mcp_update_success(outcome)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=title,
            description=new_desc,
            body_token=body,
        )
        assert_extra_keys_survive(mapping, extra)
        _assert_bookkeep(
            root,
            ident,
            new_description=new_desc,
            old_description=desc,
            title=title,
            today=today,
            allowed_dates=_dates(today, utc_today_iso()),
            path_tokens=path_tokens_for(rel, ws.path),
        )
        print("mcp public-sample shape has runtime twin", flush=True)


# ---------------------------------------------------------------------------
# B. Apply only supplied title, description, and/or body
# ---------------------------------------------------------------------------


def test_cli_title_only_leaves_description_and_body():
    """CLI title-only stores the new title; description, body, type remain; at + Update."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nt")
        new_title = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, title=new_title
        )
        today = utc_today_iso()
        require_update_success(result)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=new_title,
            description=desc,
            body_token=body,
        )
        assert_update_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=today,
            title=new_title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
        )
        print("cli title-only left description and body", flush=True)


def test_mcp_title_only_leaves_description_and_body():
    """MCP title-only stores the new title; description and body remain; at + Update."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnt")
        new_title = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, title=new_title, bundle=rel
        )
        today = utc_today_iso()
        require_mcp_update_success(outcome)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=new_title,
            description=desc,
            body_token=body,
        )
        assert_update_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=today,
            title=new_title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
        )
        print("mcp title-only left description and body", flush=True)


def test_cli_body_only_replaces_body_and_leaves_title_and_description():
    """CLI body-only replaces the post-fence body; title and description remain."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nb")
        new_body = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, body=new_body
        )
        today = utc_today_iso()
        require_update_success(result)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=title,
            description=desc,
            body_token=new_body,
            absent_body_token=body,
        )
        assert_update_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=today,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
        )
        print("cli body-only replaced body and left title/description", flush=True)


def test_mcp_body_only_replaces_body_and_leaves_title_and_description():
    """MCP body-only replaces the post-fence body; title and description remain."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnb")
        new_body = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, body=new_body, bundle=rel
        )
        today = utc_today_iso()
        require_mcp_update_success(outcome)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=title,
            description=desc,
            body_token=new_body,
            absent_body_token=body,
        )
        assert_update_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=today,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
        )
        print("mcp body-only replaced body and left title/description", flush=True)


def test_cli_identity_only_refreshes_generated_and_leaves_content_fields():
    """CLI identity-only refreshes generated.at, keeps content and two extras, writes Update."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, _rest = _runtime_fields()
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(ws, ident, rel)
        today = utc_today_iso()
        require_update_success(result)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=title,
            description=desc,
            body_token=body,
        )
        assert_extra_keys_survive(mapping, extra)
        assert_update_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=today,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
        )
        print("cli identity-only refreshed generated and left content", flush=True)


def test_mcp_identity_only_refreshes_generated_and_leaves_content_fields():
    """MCP identity-only refreshes generated.at, keeps content and two extras, writes Update."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, _rest = _runtime_fields()
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        outcome, before, after = mcp_update_with_instants(ws, ident, bundle=rel)
        today = utc_today_iso()
        require_mcp_update_success(outcome)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=title,
            description=desc,
            body_token=body,
        )
        assert_extra_keys_survive(mapping, extra)
        assert_update_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=today,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
        )
        print("mcp identity-only refreshed generated and left content", flush=True)


def test_cli_title_and_description_together_leave_body():
    """CLI title+description in one invoke stores both and leaves the body."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nt2", "nd2")
        new_title, new_desc = rest
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, title=new_title, description=new_desc
        )
        today = utc_today_iso()
        require_update_success(result)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=new_title,
            description=new_desc,
            body_token=body,
        )
        _assert_bookkeep(
            root,
            ident,
            new_description=new_desc,
            old_description=desc,
            title=new_title,
            today=today,
            allowed_dates=_dates(today, utc_today_iso()),
            path_tokens=path_tokens_for(rel, ws.path),
        )
        print("cli title and description together left body", flush=True)


def test_mcp_title_and_description_together_leave_body():
    """MCP title+description in one invoke stores both and leaves the body."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnt2", "mnd2")
        new_title, new_desc = rest
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, title=new_title, description=new_desc, bundle=rel
        )
        today = utc_today_iso()
        require_mcp_update_success(outcome)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=new_title,
            description=new_desc,
            body_token=body,
        )
        _assert_bookkeep(
            root,
            ident,
            new_description=new_desc,
            old_description=desc,
            title=new_title,
            today=today,
            allowed_dates=_dates(today, utc_today_iso()),
            path_tokens=path_tokens_for(rel, ws.path),
        )
        print("mcp title and description together left body", flush=True)


# ---------------------------------------------------------------------------
# C. Preserve verified, sources, tags, and recognized unspecified fields
# ---------------------------------------------------------------------------


def test_cli_update_preserves_verified_sources_tags_and_recognized_unspecified_fields():
    """CLI description-only keeps verified, sources, tags, status, governance, code_refs."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields(
            "nd", "vby", "src", "tg1", "tg2", "st", "gv", "cr"
        )
        new_desc, vby, src, tg1, tg2, status, gov, cref = rest
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
            verified_by=vby,
            verified_at=SEED_GENERATED_AT,
            sources_token=src,
            tags=(tg1, tg2),
            status=status,
            governance=gov,
            code_refs=cref,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        require_update_success(result)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert_verified_survives(mapping, vby, SEED_GENERATED_AT)
        assert_sources_survive(mapping, src)
        tags = tag_scalars(mapping)
        assert tg1 in tags and tg2 in tags, f"tags {tags!r} missing {tg1!r}/{tg2!r}"
        assert frontmatter_scalar(mapping, "status") == status
        assert frontmatter_scalar(mapping, "governance") == gov
        region = read_file(concept_file(root, ident))
        assert cref in region, f"code_refs token {cref!r} absent after rewrite"
        print("cli preserved verified/sources/tags/recognized fields", flush=True)


def test_mcp_update_preserves_verified_sources_tags_and_recognized_unspecified_fields():
    """MCP description-only keeps verified, sources, tags, status, governance, code_refs."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields(
            "mnd", "mvby", "msrc", "mtg1", "mtg2", "mst", "mgv", "mcr"
        )
        new_desc, vby, src, tg1, tg2, status, gov, cref = rest
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
            verified_by=vby,
            verified_at=SEED_GENERATED_AT,
            sources_token=src,
            tags=(tg1, tg2),
            status=status,
            governance=gov,
            code_refs=cref,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, description=new_desc, bundle=rel
        )
        require_mcp_update_success(outcome)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert_extra_keys_survive(mapping, extra)
        assert_verified_survives(mapping, vby, SEED_GENERATED_AT)
        assert_sources_survive(mapping, src)
        tags = tag_scalars(mapping)
        assert tg1 in tags and tg2 in tags, f"tags {tags!r} missing {tg1!r}/{tg2!r}"
        assert frontmatter_scalar(mapping, "status") == status
        assert frontmatter_scalar(mapping, "governance") == gov
        region = read_file(concept_file(root, ident))
        assert cref in region, f"code_refs token {cref!r} absent after rewrite"
        print("mcp preserved verified/sources/tags/recognized fields", flush=True)


def test_cli_update_does_not_invent_verified():
    """CLI description-only of a seed without verified writes generated and no verified key."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        require_update_success(result)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert_no_verified_key(mapping)
        print("cli did not invent verified", flush=True)


def test_mcp_update_does_not_invent_verified():
    """MCP description-only of a seed without verified writes generated and no verified key."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, description=new_desc, bundle=rel
        )
        require_mcp_update_success(outcome)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert_no_verified_key(mapping)
        print("mcp did not invent verified", flush=True)


# ---------------------------------------------------------------------------
# D. Actor strings and generated.at refresh
# ---------------------------------------------------------------------------


def test_cli_omitted_actor_writes_agent_cli_not_seed_actor():
    """CLI omit actor writes generated.by agent/cli even when the seed by differed."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
            generated_by=SEED_GENERATED_BY,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        require_update_success(result)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        by, _at = generated_by_and_at(mapping)
        assert by != SEED_GENERATED_BY
        print("cli omitted actor wrote agent/cli not seed actor", flush=True)


def test_cli_empty_and_whitespace_actor_each_write_agent_membundle_tool():
    """CLI empty and whitespace actor each write generated.by agent/membundle-tool."""
    with workspace() as ws:
        rel = _bundle()
        for actor, prefix in (("", "ae"), ("   ", "aw")):
            ident, typ, title, desc, body, extra, rest = _runtime_fields(f"{prefix}nd")
            new_desc = rest[0]
            ident = f"decisions/{ident}"
            root = seed_updatable_concept(
                ws,
                rel,
                ident,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                extra=extra,
            )
            result, before, after = run_update_with_instants(
                ws, ident, rel, description=new_desc, actor=actor
            )
            require_update_success(result)
            assert_concept_updated(
                concept_file(root, ident),
                concept_type=typ,
                generated_by="agent/membundle-tool",
                seed_generated_at=SEED_GENERATED_AT,
                before=before,
                after=after,
                description=new_desc,
            )
        print("cli empty/whitespace actor each wrote agent/membundle-tool", flush=True)


def test_cli_supplied_producer_slash_actor_is_written_as_generated_by():
    """A producer-slash-version actor is written through as generated.by."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "al", "ar")
        new_desc, left, right = rest
        actor = f"{left}/{right}"
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc, actor=actor
        )
        require_update_success(result)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by=actor,
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        print(f"producer-slash actor={actor!r}", flush=True)


def test_cli_supplied_prefix_colon_actor_is_written_as_generated_by():
    """A prefix-colon-id actor is written through as generated.by."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "ap", "ar")
        new_desc, prefix, rest_id = rest
        actor = f"{prefix}:{rest_id}"
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc, actor=actor
        )
        require_update_success(result)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by=actor,
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        print(f"prefix-colon actor={actor!r}", flush=True)


def test_mcp_generated_by_is_agent_mcp():
    """MCP update writes generated.by agent/mcp with no actor argument."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, description=new_desc, bundle=rel
        )
        require_mcp_update_success(outcome)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        print("mcp generated.by is agent/mcp", flush=True)


def test_cli_generated_at_is_new_current_utc_iso8601_combined_datetime():
    """CLI generated.at is combined date-and-time in the invoke window and differs from seed."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        require_update_success(result)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        print("cli generated.at is new current utc combined datetime", flush=True)


def test_mcp_generated_at_is_new_current_utc_iso8601_combined_datetime():
    """MCP generated.at is combined date-and-time in the invoke window and differs from seed."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, description=new_desc, bundle=rel
        )
        require_mcp_update_success(outcome)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        print("mcp generated.at is new current utc combined datetime", flush=True)


# ---------------------------------------------------------------------------
# E. Parent index listing follows the new description
# ---------------------------------------------------------------------------


def test_parent_index_listing_follows_the_new_description():
    """Nested parent listing item follows the new description; old token gone from that item."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        require_update_success(result)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert_extra_keys_survive(mapping, extra)
        assert_listing_follows_description(
            parent_index_path(root, ident),
            identity=ident,
            filename=concept_filename(ident),
            new_description=new_desc,
            old_description=desc,
            title=title,
        )
        print("parent index listing follows the new description", flush=True)


def test_root_level_listing_follows_the_new_description():
    """Root-level identity listing in bundle-root index.md follows the new description."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        require_update_success(result)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert_extra_keys_survive(mapping, extra)
        assert_listing_follows_description(
            root / "index.md",
            identity=ident,
            filename=concept_filename(ident),
            new_description=new_desc,
            old_description=desc,
            title=title,
        )
        print("root-level listing follows the new description", flush=True)


def test_cli_skip_index_does_not_update_an_existing_parent_listing_and_still_writes_update_bullet():
    """On the CLI with index skipped, the parent index listing is not updated."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        skip_rel = unique_tokens("skrel")[0]
        for target in (rel, skip_rel):
            seed_updatable_concept(
                ws,
                target,
                ident,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                extra=extra,
            )
        live_root = ws.resolve(rel)
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        today = utc_today_iso()
        require_update_success(result)
        assert_listing_follows_description(
            parent_index_path(live_root, ident),
            identity=ident,
            filename=concept_filename(ident),
            new_description=new_desc,
            old_description=desc,
            title=title,
        )
        skip_root = ws.resolve(skip_rel)
        skip_result, skip_before, skip_after = run_update_with_instants(
            ws, ident, skip_rel, description=new_desc, skip_index=True
        )
        require_update_success(skip_result)
        assert_concept_updated(
            concept_file(skip_root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=skip_before,
            after=skip_after,
            description=new_desc,
        )
        skip_listing = assert_listing_keeps_old_description(
            parent_index_path(skip_root, ident),
            identity=ident,
            filename=concept_filename(ident),
            old_description=desc,
            new_description=new_desc,
        )
        assert desc in skip_listing, (
            "on the CLI with index skipped, the parent index listing lost "
            "the old description"
        )
        assert new_desc not in skip_listing, (
            "on the CLI with index skipped, the parent index listing is not "
            "updated — it was rewritten with the new description"
        )
        assert_update_bullet(
            skip_root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=today,
            title=title,
            path_tokens=path_tokens_for(skip_rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
        )
        print(
            "CLI with index skipped: parent index listing was not updated",
            flush=True,
        )


def test_mcp_update_always_writes_parent_listing_and_update_bullet():
    """The Model Context Protocol update tool cannot skip bookkeeping: it still writes the parent listing and the Update bullet."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, description=new_desc, bundle=rel
        )
        today = utc_today_iso()
        require_mcp_update_success(outcome)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        filename = concept_filename(ident)
        listing_item = assert_listing_follows_description(
            parent_index_path(root, ident),
            identity=ident,
            filename=filename,
            new_description=new_desc,
            old_description=desc,
            title=title,
        )
        assert new_desc in listing_item, (
            "the Model Context Protocol update tool did not write the parent listing"
        )
        update_item = assert_update_bullet(
            root / "log.md",
            identity=ident,
            filename=filename,
            today=today,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
        )
        assert update_item, (
            "the Model Context Protocol update tool cannot skip those updates: "
            "it still writes the parent listing and the Update bullet"
        )
        print(
            "MCP update cannot skip: parent listing and Update bullet were written",
            flush=True,
        )


# ---------------------------------------------------------------------------
# F. Log gains an Update bullet under today’s UTC date heading
# ---------------------------------------------------------------------------


def test_log_inserts_today_utc_heading_with_update_bullet_naming_the_file():
    """Among dated headings, today precedes the older seed and that section names the file as Update."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        today = utc_today_iso()
        require_update_success(result)
        headings = heading_texts(read_file(root / "log.md"))
        print(f"log headings={headings!r}", flush=True)
        assert_update_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=today,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
            older_date=SEED_LOG_DATE,
        )
        print("log inserted today utc heading with Update bullet", flush=True)


def test_cli_skip_log_does_not_gain_update_bullet_and_still_updates_listing():
    """On the CLI with log skipped, log.md does not gain that Update bullet."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        live_rel = _bundle()
        skip_rel = unique_tokens("slrel")[0]
        for target in (live_rel, skip_rel):
            seed_updatable_concept(
                ws,
                target,
                ident,
                concept_type=typ,
                title=title,
                description=desc,
                body=body,
                extra=extra,
            )
        live_root = ws.resolve(live_rel)
        live_result, live_before, live_after = run_update_with_instants(
            ws, ident, live_rel, description=new_desc
        )
        today = utc_today_iso()
        require_update_success(live_result)
        live_update = assert_update_bullet(
            live_root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=today,
            title=title,
            path_tokens=path_tokens_for(live_rel, ws.path),
            allowed_dates=_dates(today, utc_today_iso()),
        )
        assert live_update, (
            "unskipped CLI update did not write an Update bullet; skip-log "
            "has no live baseline"
        )
        skip_root = ws.resolve(skip_rel)
        skip_result, skip_before, skip_after = run_update_with_instants(
            ws, ident, skip_rel, description=new_desc, skip_log=True
        )
        require_update_success(skip_result)
        assert_concept_updated(
            concept_file(skip_root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=skip_before,
            after=skip_after,
            description=new_desc,
        )
        assert_listing_follows_description(
            parent_index_path(skip_root, ident),
            identity=ident,
            filename=concept_filename(ident),
            new_description=new_desc,
            old_description=desc,
            title=title,
        )
        assert_update_absent(
            skip_root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            title=title,
            path_tokens=path_tokens_for(skip_rel, ws.path),
        )
        skip_log_after = read_file(skip_root / "log.md")
        filename = concept_filename(ident)
        assert (
            "Update" not in skip_log_after
            or filename not in skip_log_after
        ), (
            "on the CLI with log skipped, log.md gained that Update bullet"
        )
        print(
            "CLI with log skipped: log.md did not gain that Update bullet",
            flush=True,
        )


def test_cli_log_heading_uses_utc_date_not_process_local_timezone():
    """CLI log heading date digits are UTC today, not the process-local date."""
    tz_value, local_date = tz_offset_where_local_date_differs()
    print(f"cli TZ contrast tz={tz_value!r} local={local_date}", flush=True)
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        before = utc_today_iso()
        result = run_update(
            ws,
            ident,
            rel,
            description=new_desc,
            env_updates={"TZ": tz_value},
        )
        after = utc_today_iso()
        require_update_success(result)
        dates = _dates(before, after)
        assert local_date not in dates, (
            f"local date {local_date} collided with UTC dates {sorted(dates)}"
        )
        assert_update_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=before,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=dates,
        )
        headings = heading_texts(read_file(root / "log.md"))
        dated = [h for h in headings if len(h) == 10 and h[4] == "-" and h[7] == "-"]
        today_hits = [h for h in dated if h in dates]
        assert today_hits, f"no utc today heading; dated={dated!r}"
        assert today_hits[0] != local_date
        print("cli log heading used utc date not local timezone", flush=True)


def test_mcp_log_heading_uses_utc_date_not_process_local_timezone():
    """MCP log heading date digits are UTC today, not the process-local date."""
    tz_value, local_date = tz_offset_where_local_date_differs()
    print(f"mcp TZ contrast tz={tz_value!r} local={local_date}", flush=True)
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        before = utc_today_iso()
        outcome = mcp_update(
            ws,
            ident,
            description=new_desc,
            bundle=rel,
            env_updates={"TZ": tz_value},
        )
        after = utc_today_iso()
        require_mcp_update_success(outcome)
        dates = _dates(before, after)
        assert local_date not in dates
        assert_update_bullet(
            root / "log.md",
            identity=ident,
            filename=concept_filename(ident),
            today=before,
            title=title,
            path_tokens=path_tokens_for(rel, ws.path),
            allowed_dates=dates,
        )
        headings = heading_texts(read_file(root / "log.md"))
        dated = [h for h in headings if len(h) == 10 and h[4] == "-" and h[7] == "-"]
        today_hits = [h for h in dated if h in dates]
        assert today_hits, f"no utc today heading; dated={dated!r}"
        assert today_hits[0] != local_date
        print("mcp log heading used utc date not local timezone", flush=True)


# ---------------------------------------------------------------------------
# G. Empty description clears; omit leaves; whitespace-only fails
# ---------------------------------------------------------------------------


def test_cli_empty_description_clears_description():
    """CLI empty description clears the value; listing item remains without the old token."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        live_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        live_rel = unique_tokens("gcrel")[0]
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        seed_updatable_concept(
            ws,
            live_rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        live_result, live_before, live_after = run_update_with_instants(
            ws, ident, live_rel, description=live_desc
        )
        require_update_success(live_result)
        assert_concept_updated(
            concept_file(ws.resolve(live_rel), ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=live_before,
            after=live_after,
            description=live_desc,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=""
        )
        require_update_success(result)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=title,
            body_token=body,
        )
        assert_description_cleared(mapping, desc)
        assert_listing_cleared_description(
            parent_index_path(root, ident),
            identity=ident,
            filename=concept_filename(ident),
            old_description=desc,
            title=title,
        )
        print("cli empty description cleared description", flush=True)


def test_mcp_empty_description_clears_description():
    """MCP empty-string description clears the value; listing item remains."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnd")
        live_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        live_rel = unique_tokens("mgcrel")[0]
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        seed_updatable_concept(
            ws,
            live_rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        live, live_before, live_after = mcp_update_with_instants(
            ws, ident, description=live_desc, bundle=live_rel
        )
        require_mcp_update_success(live)
        assert_concept_updated(
            concept_file(ws.resolve(live_rel), ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=live_before,
            after=live_after,
            description=live_desc,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, description="", bundle=rel
        )
        require_mcp_update_success(outcome)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=title,
            body_token=body,
        )
        assert_description_cleared(mapping, desc)
        assert_listing_cleared_description(
            parent_index_path(root, ident),
            identity=ident,
            filename=concept_filename(ident),
            old_description=desc,
            title=title,
        )
        print("mcp empty description cleared description", flush=True)


def test_cli_omitted_description_leaves_existing_description():
    """CLI omit of description while supplying a new title leaves the old description."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nt")
        new_title = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, title=new_title
        )
        require_update_success(result)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=new_title,
            description=desc,
            body_token=body,
        )
        print("cli omitted description left existing description", flush=True)


def test_mcp_omitted_description_leaves_existing_description():
    """MCP omit of description while supplying a new title leaves the old description."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnt")
        new_title = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, title=new_title, bundle=rel
        )
        require_mcp_update_success(outcome)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            title=new_title,
            description=desc,
            body_token=body,
        )
        print("mcp omitted description left existing description", flush=True)


def test_cli_whitespace_only_description_fails_without_successful_update():
    """CLI whitespace-only description fails; planted generated.at and log stay."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, _rest = _runtime_fields()
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        before_snap = snapshot_tree(ws.path)
        result = run_update(ws, ident, rel, description="   ")
        require_update_failure(result)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        assert_no_successful_rewrite(
            root,
            ident,
            seed_title=title,
            seed_description=desc,
            seed_body=body,
            new_description="   ",
            path_tokens=path_tokens_for(rel, ws.path),
        )
        _live_cli_rewrite(ws, rel)
        print("cli whitespace-only description failed without rewrite", flush=True)


def test_mcp_whitespace_only_description_is_tool_error_and_does_not_rewrite():
    """MCP whitespace-only description fails and does not rewrite."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, _rest = _runtime_fields()
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        before_snap = snapshot_tree(ws.path)
        outcome = mcp_update(ws, ident, description="   ", bundle=rel)
        require_mcp_update_non_success(outcome)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        assert_no_successful_rewrite(
            root,
            ident,
            seed_title=title,
            seed_description=desc,
            seed_body=body,
            path_tokens=path_tokens_for(rel, ws.path),
        )
        _live_mcp_rewrite(ws, rel)
        print("mcp whitespace-only description is tool error", flush=True)


# ---------------------------------------------------------------------------
# H. Empty or whitespace title fails; omitting title leaves it
# ---------------------------------------------------------------------------


def test_cli_empty_and_whitespace_title_each_fail_without_successful_update():
    """CLI empty and whitespace title each fail without a successful rewrite."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, _rest = _runtime_fields()
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        for title_val in ("", "   "):
            before_snap = snapshot_tree(ws.path)
            result = run_update(ws, ident, rel, title=title_val)
            require_update_failure(result)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            assert_no_successful_rewrite(
                root,
                ident,
                seed_title=title,
                seed_description=desc,
                seed_body=body,
                new_title=title_val,
                path_tokens=path_tokens_for(rel, ws.path),
            )
        _live_cli_rewrite(ws, rel)
        print("cli empty/whitespace title each failed without rewrite", flush=True)


def test_mcp_empty_and_whitespace_title_each_is_tool_error_and_does_not_rewrite():
    """MCP empty and whitespace title each fails and does not rewrite."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, _rest = _runtime_fields()
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        for request_id, title_val in enumerate(("", "   "), start=20):
            before_snap = snapshot_tree(ws.path)
            outcome = mcp_update(
                ws, ident, title=title_val, bundle=rel, request_id=request_id
            )
            require_mcp_update_non_success(outcome)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            assert_no_successful_rewrite(
                root,
                ident,
                seed_title=title,
                seed_description=desc,
                seed_body=body,
                new_title=title_val,
                path_tokens=path_tokens_for(rel, ws.path),
            )
        _live_mcp_rewrite(ws, rel)
        print("mcp empty/whitespace title each is tool error", flush=True)


# ---------------------------------------------------------------------------
# I. Omit-path default and named-path write root
# ---------------------------------------------------------------------------


def test_omit_path_without_knowledge_dir_updates_cwd():
    """Omit bundle path with no knowledge/ directory rewrites the cwd concept."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        seed_updatable_concept(
            ws, ".", ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        result, before, after = run_update_with_instants(
            ws, ident, description=new_desc
        )
        require_update_success(result)
        assert_concept_updated(
            ws.path / f"{ident}.md",
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert not path_is_file(ws.path / "knowledge" / f"{ident}.md")
        print("omit-path without knowledge/ updated cwd", flush=True)


def test_omit_path_with_knowledge_dir_updates_knowledge_not_cwd():
    """Omit bundle path with knowledge/ as a directory rewrites knowledge/, not a cwd decoy."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "dk")
        new_desc, decoy = rest
        seed_updatable_concept(
            ws,
            "knowledge",
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        decoy_path = ws.path / f"{ident}.md"
        decoy_path.write_text(decoy, encoding="utf-8")
        result, before, after = run_update_with_instants(
            ws, ident, description=new_desc
        )
        require_update_success(result)
        assert_concept_updated(
            ws.path / "knowledge" / f"{ident}.md",
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert decoy_path.read_text(encoding="utf-8") == decoy
        print("omit-path with knowledge/ updated knowledge not cwd", flush=True)


def test_omit_path_knowledge_file_is_not_treated_as_bundle_dir():
    """A file named knowledge is not a directory, so omit-path uses cwd."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        seed_updatable_concept(
            ws, ".", ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        knowledge_file = ws.path / "knowledge"
        knowledge_file.write_text("not-a-directory\n", encoding="utf-8")
        before_bytes = read_bytes(knowledge_file)
        result, before, after = run_update_with_instants(
            ws, ident, description=new_desc
        )
        require_update_success(result)
        assert knowledge_file.is_file()
        assert read_bytes(knowledge_file) == before_bytes
        assert_concept_updated(
            ws.path / f"{ident}.md",
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        print("knowledge file was not treated as a bundle dir", flush=True)


def test_explicit_bundle_path_is_not_overridden_by_cwd_knowledge():
    """A named bundle path is the write target even when cwd has knowledge/."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "dk")
        new_desc, decoy = rest
        rel = _bundle()
        root = seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        decoy_dir = ws.path / "knowledge"
        decoy_dir.mkdir()
        decoy_path = decoy_dir / f"{ident}.md"
        decoy_path.write_text(decoy, encoding="utf-8")
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        require_update_success(result)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert_extra_keys_survive(mapping, extra)
        assert decoy_path.read_text(encoding="utf-8") == decoy
        print("named bundle was not overridden by cwd knowledge/", flush=True)


def test_named_path_without_root_index_updates_named_path_nested_files_unchanged():
    """Named path with no root index.md updates the named path; nested knowledge/ stays."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        rel = unique_tokens("nkrel")[0]
        nested = seed_updatable_concept(
            ws,
            f"{rel}/knowledge",
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        named = ws.path / rel
        if path_is_file(named / "index.md"):
            (named / "index.md").unlink()
        assert not path_is_file(named / "index.md")
        assert path_is_dir(named / "knowledge")
        nested_concept_before = read_bytes(concept_file(nested, ident))
        nested_index_before = read_bytes(nested / "index.md")
        nested_log_before = read_bytes(nested / "log.md")
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        today = utc_today_iso()
        report = require_update_success(result)
        assert_named_path_update_landing(
            named,
            nested,
            ident,
            concept_type=typ,
            generated_by="agent/cli",
            title=title,
            old_description=desc,
            new_description=new_desc,
            extra=extra,
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            nested_concept_before=nested_concept_before,
            nested_index_before=nested_index_before,
            nested_log_before=nested_log_before,
            today=today,
            allowed_dates=_dates(today, utc_today_iso()),
            path_tokens=path_tokens_for(rel, named, ws.path),
        )
        require_update_report_line(result, ident, rel)
        print("cli named path updated named root; nested unchanged", flush=True)


def test_mcp_omit_bundle_without_knowledge_dir_updates_cwd():
    """MCP omit bundle, no knowledge/ directory: rewrite lands at cwd."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnd")
        new_desc = rest[0]
        seed_updatable_concept(
            ws, ".", ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        outcome, before, after = mcp_update_with_instants(
            ws, ident, description=new_desc
        )
        require_mcp_update_success(outcome)
        assert_concept_updated(
            ws.path / f"{ident}.md",
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert not path_is_file(ws.path / "knowledge" / f"{ident}.md")
        print("mcp omit-bundle without knowledge/ updated cwd", flush=True)


def test_mcp_omit_bundle_with_knowledge_dir_updates_knowledge_not_cwd():
    """MCP omit bundle with knowledge/ as a directory rewrites knowledge/, not a cwd decoy."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnd", "dk")
        new_desc, decoy = rest
        seed_updatable_concept(
            ws,
            "knowledge",
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        decoy_path = ws.path / f"{ident}.md"
        decoy_path.write_text(decoy, encoding="utf-8")
        outcome, before, after = mcp_update_with_instants(
            ws, ident, description=new_desc
        )
        require_mcp_update_success(outcome)
        assert_concept_updated(
            ws.path / "knowledge" / f"{ident}.md",
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert decoy_path.read_text(encoding="utf-8") == decoy
        print("mcp omit-bundle with knowledge/ updated knowledge not cwd", flush=True)


def test_mcp_named_bundle_is_not_overridden_by_cwd_knowledge():
    """MCP named bundle writes there even when cwd has a knowledge/ decoy."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnd", "dk")
        new_desc, decoy = rest
        rel = _bundle()
        root = seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        decoy_dir = ws.path / "knowledge"
        decoy_dir.mkdir()
        decoy_path = decoy_dir / f"{ident}.md"
        decoy_path.write_text(decoy, encoding="utf-8")
        outcome, before, after = mcp_update_with_instants(
            ws, ident, description=new_desc, bundle=rel
        )
        require_mcp_update_success(outcome)
        assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert decoy_path.read_text(encoding="utf-8") == decoy
        print("mcp named bundle ignored cwd knowledge decoy", flush=True)


def test_mcp_named_path_without_root_index_updates_named_path_nested_files_unchanged():
    """MCP named path with no root index.md updates the named path; nested knowledge/ stays."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("mnd")
        new_desc = rest[0]
        rel = unique_tokens("mnkrel")[0]
        nested = seed_updatable_concept(
            ws,
            f"{rel}/knowledge",
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        named = ws.path / rel
        if path_is_file(named / "index.md"):
            (named / "index.md").unlink()
        assert not path_is_file(named / "index.md")
        assert path_is_dir(named / "knowledge")
        nested_concept_before = read_bytes(concept_file(nested, ident))
        nested_index_before = read_bytes(nested / "index.md")
        nested_log_before = read_bytes(nested / "log.md")
        outcome, before, after = mcp_update_with_instants(
            ws, ident, description=new_desc, bundle=rel
        )
        today = utc_today_iso()
        require_mcp_update_success(outcome)
        assert_named_path_update_landing(
            named,
            nested,
            ident,
            concept_type=typ,
            generated_by="agent/mcp",
            title=title,
            old_description=desc,
            new_description=new_desc,
            extra=extra,
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            nested_concept_before=nested_concept_before,
            nested_index_before=nested_index_before,
            nested_log_before=nested_log_before,
            today=today,
            allowed_dates=_dates(today, utc_today_iso()),
            path_tokens=path_tokens_for(rel, named, ws.path),
        )
        require_mcp_update_report(outcome, ident, mcp_bundle_dir(ws, rel))
        print("mcp named path updated named root; nested unchanged", flush=True)


# ---------------------------------------------------------------------------
# J. Invalid, reserved, and escaping identities
# ---------------------------------------------------------------------------


def test_empty_identity_fails_without_successful_update():
    """Empty identity fails without a successful update on CLI and MCP."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        before_snap = snapshot_tree(ws.path)
        result = run_update(ws, "", rel, description=new_desc)
        require_update_failure(result)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        outcome = mcp_membundle_update(
            ws,
            {"concept_id": "", "description": new_desc, "bundle": rel},
            request_id=21,
        )
        require_mcp_update_non_success(outcome)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        _live_cli_rewrite(ws, rel)
        print("empty identity refused on CLI and MCP", flush=True)


def test_absolute_identity_fails_without_successful_update():
    """An absolute-path identity fails without a successful update on CLI and MCP."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "ab")
        new_desc, leaf = rest
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        aimed = f"/{leaf}"
        before_snap = snapshot_tree(ws.path)
        result = run_update(ws, aimed, rel, description=new_desc)
        require_update_failure(result)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        outcome = mcp_membundle_update(
            ws,
            {"concept_id": aimed, "description": new_desc, "bundle": rel},
            request_id=22,
        )
        require_mcp_update_non_success(outcome)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        _live_cli_rewrite(ws, rel)
        print("absolute identity refused", flush=True)


def test_dotdot_identity_fails_and_does_not_write_outside_the_bundle():
    """../outside and foo/../outside fail; nothing is written outside the bundle."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        assert_snapshot_helper_sees_write(ws, unique_tokens("snap")[0])
        outside = ws.path / f"{_OUTSIDE_LEAF}.md"
        nested_outside = ws.path / _OUTSIDE_LEAF
        for aimed in (f"../{_OUTSIDE_LEAF}", f"foo/../{_OUTSIDE_LEAF}"):
            before_snap = snapshot_tree(ws.path)
            result = run_update(ws, aimed, rel, description=new_desc)
            require_update_failure(result)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            outcome = mcp_membundle_update(
                ws,
                {"concept_id": aimed, "description": new_desc, "bundle": rel},
                request_id=30 + len(aimed),
            )
            require_mcp_update_non_success(outcome)
        assert not outside.exists(), "update of ../outside wrote a file outside the bundle"
        assert not nested_outside.exists()
        _live_cli_rewrite(ws, rel)
        print("dotdot identities did not write outside the bundle", flush=True)


def test_leading_hyphen_identity_fails_without_successful_update():
    """A leading-hyphen identity fails without a successful update on CLI and MCP."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "hy")
        new_desc, leaf = rest
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        aimed = f"-{leaf}"
        before_snap = snapshot_tree(ws.path)
        result = run_update(ws, aimed, rel, description=new_desc)
        require_update_failure(result)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        outcome = mcp_membundle_update(
            ws,
            {"concept_id": aimed, "description": new_desc, "bundle": rel},
            request_id=23,
        )
        require_mcp_update_non_success(outcome)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        _live_cli_rewrite(ws, rel)
        print("leading-hyphen identity refused", flush=True)


def test_cli_newline_cr_and_tab_identities_each_fail_without_successful_update():
    """CLI newline, CR, and tab identities each fail without a successful update."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "cl", "cr")
        new_desc, left, right = rest
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        for aimed in (f"{left}\n{right}", f"{left}\r{right}", f"{left}\t{right}"):
            before_snap = snapshot_tree(ws.path)
            result = run_update(ws, aimed, rel, description=new_desc)
            require_update_failure(result)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        _live_cli_rewrite(ws, rel)
        print("cli control-character identities refused", flush=True)


def test_mcp_newline_cr_tab_and_nul_identities_each_are_tool_errors_and_write_nothing():
    """MCP newline, CR, tab, and NUL identities fail and write nothing."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "ml", "mr")
        new_desc, left, right = rest
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        good_ident = f"{left}{right}"
        seed_updatable_concept(
            ws,
            rel,
            good_ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        for request_id, aimed in enumerate(
            (
                f"{left}\n{right}",
                f"{left}\r{right}",
                f"{left}\t{right}",
                f"{left}\x00{right}",
            ),
            start=40,
        ):
            before_snap = snapshot_tree(ws.path)
            outcome = mcp_membundle_update(
                ws,
                {"concept_id": aimed, "description": new_desc, "bundle": rel},
                request_id=request_id,
            )
            require_mcp_update_non_success(outcome)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        live, before, after = mcp_update_with_instants(
            ws, good_ident, description=new_desc, bundle=rel, request_id=49
        )
        require_mcp_update_success(live)
        assert_concept_updated(
            concept_file(ws.resolve(rel), good_ident),
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        print("mcp control-character identities refused; well-formed rewrites", flush=True)


def test_reserved_index_nested_index_root_log_and_root_agents_fail_without_successful_update():
    """Reserved index, nested index, root log, and root AGENTS fail; reserved files unchanged."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "rs")
        new_desc, nest = rest
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
            agents="# agents seed\n",
        )
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
        for aimed in ("index", f"{nest}/index", "log", "AGENTS"):
            before_snap = snapshot_tree(ws.path)
            result = run_update(ws, aimed, rel, description=new_desc)
            require_update_failure(result)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        for key, path in reserved_paths.items():
            assert read_bytes(path) == before_bytes[key], (
                f"reserved file {key} changed after a refusing update"
            )
        live, live_before, live_after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        require_update_success(live)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=live_before,
            after=live_after,
            description=new_desc,
        )
        assert_extra_keys_survive(mapping, extra)
        print("reserved identities refused; reserved files unchanged", flush=True)


def test_mcp_reserved_index_nested_index_root_log_and_root_agents_are_tool_errors_and_write_nothing():
    """MCP reserved index / nested index / root log / root AGENTS fail and write nothing."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "mr")
        new_desc, nest = rest
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
            agents="# agents seed\n",
        )
        nested_index = root / nest / "index.md"
        nested_index.parent.mkdir(parents=True, exist_ok=True)
        nested_index.write_text("# nested\n", encoding="utf-8")
        reserved_paths = [root / "index.md", root / "log.md", root / "AGENTS.md", nested_index]
        before_bytes = [read_bytes(path) for path in reserved_paths]
        for request_id, aimed in enumerate(
            ("index", f"{nest}/index", "log", "AGENTS"), start=50
        ):
            before_snap = snapshot_tree(ws.path)
            outcome = mcp_membundle_update(
                ws,
                {"concept_id": aimed, "description": new_desc, "bundle": rel},
                request_id=request_id,
            )
            require_mcp_update_non_success(outcome)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        for path, payload in zip(reserved_paths, before_bytes):
            assert read_bytes(path) == payload
        _live_mcp_rewrite(ws, rel)
        print("mcp reserved identities refused", flush=True)


def test_nested_log_and_agents_are_updatable():
    """Nested log.md is not-found and is not rewritten; nested non-log.md and AGENTS.md rewrite."""
    with workspace() as ws:
        nest, typ, title, desc, body = unique_tokens("nldir", "nlty", "nltl", "nlds", "nlb")
        extra = _extras("nlxk1", "nlxv1", "nlxk2", "nlxv2")
        new_desc, ghost, note_leaf = unique_tokens("nlnd", "nlghost", "nlnote")
        log_ident = f"{nest}/log"
        agents_ident = f"{nest}/AGENTS"
        note_ident = f"{nest}/{note_leaf}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            log_ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
            agents="# agents seed\n",
        )
        seed_updatable_concept(
            ws,
            rel,
            agents_ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
            agents="# agents seed\n",
        )
        seed_updatable_concept(
            ws,
            rel,
            note_ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        missing_dir = unique_tokens("nlmiss")[0]
        paths = path_tokens_for(rel, missing_dir, ws.path)
        log_path = concept_file(root, log_ident)
        note_path = concept_file(root, note_ident)
        agents_path = concept_file(root, agents_ident)
        assert concept_filename(log_ident) == "log.md"
        assert concept_filename(note_ident) != "log.md"
        assert concept_filename(agents_ident) == "AGENTS.md"
        assert path_is_file(log_path)
        log_before = read_bytes(log_path)
        note_before = read_bytes(note_path)
        agents_before = read_bytes(agents_path)
        nested_log = run_update(ws, log_ident, rel, description=new_desc)
        require_update_failure(nested_log)
        assert read_bytes(log_path) == log_before, (
            "command-line update of a nested identity whose file is named "
            "log.md, after that file is already present, rewrote the file"
        )
        assert_no_successful_rewrite(
            root,
            log_ident,
            seed_title=title,
            seed_description=desc,
            seed_body=body,
            new_description=new_desc,
            path_tokens=paths,
        )
        not_found = run_update(ws, ghost, rel, description=new_desc)
        require_update_failure(not_found)
        assert not path_is_file(concept_file(root, ghost)), (
            "command-line update of a missing identity does not succeed and "
            "does not create a file"
        )
        load_error = run_update(ws, ghost, missing_dir, description=new_desc)
        require_update_failure(load_error)
        require_update_not_found(
            nested_log, log_ident, "update of a nested identity whose file is named log.md"
        )
        require_update_not_found(
            not_found, ghost, "update of an identity not in the loaded concept set"
        )
        require_update_load_failure(load_error, "update in a missing bundle directory")
        note_result, note_before_t, note_after_t = run_update_with_instants(
            ws, note_ident, rel, description=new_desc
        )
        require_update_success(note_result)
        note_mapping, _note_body = assert_concept_updated(
            note_path,
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=note_before_t,
            after=note_after_t,
            description=new_desc,
        )
        assert read_bytes(note_path) != note_before, (
            "update of a nested identity whose file is not named log.md, "
            "present as a concept file, did not rewrite"
        )
        assert frontmatter_scalar(note_mapping, "description") == new_desc, (
            "update of a nested identity whose file is not named log.md, "
            "present as a concept file, succeeds and rewrites"
        )
        agents_result, agents_before_t, agents_after_t = run_update_with_instants(
            ws, agents_ident, rel, description=new_desc
        )
        require_update_success(agents_result)
        agents_mapping, _agents_body = assert_concept_updated(
            agents_path,
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=agents_before_t,
            after=agents_after_t,
            description=new_desc,
        )
        assert read_bytes(agents_path) != agents_before, (
            "update of a nested identity whose file is named AGENTS.md, "
            "present as a concept file, did not rewrite"
        )
        assert frontmatter_scalar(agents_mapping, "description") == new_desc, (
            "update of a nested identity whose file is named AGENTS.md, "
            "present as a concept file, succeeds and rewrites"
        )
        log_bytes = read_bytes(root / "log.md")
        agents_bytes = read_bytes(root / "AGENTS.md")
        require_update_failure(run_update(ws, "log", rel, description=new_desc))
        require_update_failure(run_update(ws, "AGENTS", rel, description=new_desc))
        assert read_bytes(root / "log.md") == log_bytes
        assert read_bytes(root / "AGENTS.md") == agents_bytes
        print("nested log.md is not-found; nested non-log.md and AGENTS.md rewrite", flush=True)


def test_mcp_nested_log_and_agents_are_updatable():
    """MCP nested log.md is not-found and is not rewritten; nested non-log.md and AGENTS.md rewrite."""
    with workspace() as ws:
        nest, typ, title, desc, body = unique_tokens("mldir", "mlty", "mltl", "mlds", "mlb")
        extra = _extras("mlxk1", "mlxv1", "mlxk2", "mlxv2")
        new_desc, ghost, note_leaf = unique_tokens("mlnd", "mlghost", "mlnote")
        log_ident = f"{nest}/log"
        agents_ident = f"{nest}/AGENTS"
        note_ident = f"{nest}/{note_leaf}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws,
            rel,
            log_ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
            agents="# agents seed\n",
        )
        seed_updatable_concept(
            ws,
            rel,
            agents_ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
            agents="# agents seed\n",
        )
        seed_updatable_concept(
            ws,
            rel,
            note_ident,
            concept_type=typ,
            title=title,
            description=desc,
            body=body,
            extra=extra,
        )
        missing_dir = unique_tokens("mlmiss")[0]
        paths = path_tokens_for(rel, missing_dir, ws.path)
        log_path = concept_file(root, log_ident)
        note_path = concept_file(root, note_ident)
        agents_path = concept_file(root, agents_ident)
        assert concept_filename(log_ident) == "log.md"
        assert concept_filename(note_ident) != "log.md"
        assert concept_filename(agents_ident) == "AGENTS.md"
        assert path_is_file(log_path)
        log_before = read_bytes(log_path)
        note_before = read_bytes(note_path)
        agents_before = read_bytes(agents_path)
        nested_log = mcp_update(
            ws, log_ident, description=new_desc, bundle=rel, request_id=54
        )
        require_mcp_update_non_success(nested_log)
        assert read_bytes(log_path) == log_before, (
            "Model Context Protocol update of a nested identity whose file is "
            "named log.md, after that file is already present, rewrote the file"
        )
        assert_no_successful_rewrite(
            root,
            log_ident,
            seed_title=title,
            seed_description=desc,
            seed_body=body,
            new_description=new_desc,
            path_tokens=paths,
        )
        not_found = mcp_update(
            ws, ghost, description=new_desc, bundle=rel, request_id=55
        )
        require_mcp_update_non_success(not_found)
        assert not path_is_file(concept_file(root, ghost)), (
            "update of a missing identity does not succeed and does not create "
            "a file"
        )
        load_error = mcp_update(
            ws, ghost, description=new_desc, bundle=missing_dir, request_id=56
        )
        require_mcp_update_non_success(load_error)
        require_mcp_update_not_found(
            nested_log, log_ident, "membundle_update of a nested identity whose file is named log.md"
        )
        require_mcp_update_not_found(
            not_found, ghost, "membundle_update of an identity not in the bundle"
        )
        require_mcp_update_load_failure(load_error, "membundle_update of a missing named bundle")
        note_outcome, note_before_t, note_after_t = mcp_update_with_instants(
            ws, note_ident, description=new_desc, bundle=rel, request_id=57
        )
        require_mcp_update_success(note_outcome)
        note_mapping, _note_body = assert_concept_updated(
            note_path,
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=note_before_t,
            after=note_after_t,
            description=new_desc,
        )
        assert read_bytes(note_path) != note_before, (
            "update of a nested identity whose file is not named log.md, "
            "present as a concept file, did not rewrite"
        )
        assert frontmatter_scalar(note_mapping, "description") == new_desc, (
            "update of a nested identity whose file is not named log.md, "
            "present as a concept file, succeeds and rewrites"
        )
        agents_outcome, agents_before_t, agents_after_t = mcp_update_with_instants(
            ws, agents_ident, description=new_desc, bundle=rel, request_id=58
        )
        require_mcp_update_success(agents_outcome)
        agents_mapping, _agents_body = assert_concept_updated(
            agents_path,
            concept_type=typ,
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            before=agents_before_t,
            after=agents_after_t,
            description=new_desc,
        )
        assert read_bytes(agents_path) != agents_before, (
            "update of a nested identity whose file is named AGENTS.md, "
            "present as a concept file, did not rewrite"
        )
        assert frontmatter_scalar(agents_mapping, "description") == new_desc, (
            "update of a nested identity whose file is named AGENTS.md, "
            "present as a concept file, succeeds and rewrites"
        )
        log_bytes = read_bytes(root / "log.md")
        agents_bytes = read_bytes(root / "AGENTS.md")
        require_mcp_update_non_success(
            mcp_membundle_update(
                ws,
                {"concept_id": "log", "description": new_desc, "bundle": rel},
                request_id=60,
            )
        )
        require_mcp_update_non_success(
            mcp_membundle_update(
                ws,
                {"concept_id": "AGENTS", "description": new_desc, "bundle": rel},
                request_id=61,
            )
        )
        assert read_bytes(root / "log.md") == log_bytes
        assert read_bytes(root / "AGENTS.md") == agents_bytes
        print("mcp nested log.md is not-found; nested non-log.md and AGENTS.md rewrite", flush=True)


def test_mcp_dotdot_absolute_empty_and_leading_hyphen_are_tool_errors_and_write_nothing():
    """MCP ../outside, absolute, empty, and leading-hyphen identities fail and write nothing."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "mx")
        new_desc, leaf = rest
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        for request_id, aimed in enumerate(
            (f"../{_OUTSIDE_LEAF}", f"/{leaf}", "", f"-{leaf}"), start=70
        ):
            before_snap = snapshot_tree(ws.path)
            outcome = mcp_membundle_update(
                ws,
                {"concept_id": aimed, "description": new_desc, "bundle": rel},
                request_id=request_id,
            )
            require_mcp_update_non_success(outcome)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        _live_mcp_rewrite(ws, rel)
        print("mcp invalid-identity set refused", flush=True)


def test_escaping_symlink_write_is_refused():
    """Write through a .md symlink whose target leaves the bundle is refused."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "sc")
        new_desc, secret_leaf = rest
        rel = _bundle()
        root = seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        live, live_before, live_after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        require_update_success(live)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=live_before,
            after=live_after,
            description=new_desc,
        )
        assert_extra_keys_survive(mapping, extra)
        secret = ws.write(f"{secret_leaf}.md", b"outside-secret\n")
        secret_bytes = secret.read_bytes()
        link_ident = unique_tokens("syid")[0]
        dest = concept_file(root, link_ident)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(secret, dest)
        assert_snapshot_helper_sees_write(ws, unique_tokens("syc")[0])
        before_snap = snapshot_tree(ws.path)
        result = run_update(ws, link_ident, rel, description=new_desc)
        require_update_failure(result)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        assert secret.read_bytes() == secret_bytes
        assert dest.is_symlink() or not dest.exists(), (
            "refusing update replaced the escaping symlink with a regular concept file"
        )
        print("escaping symlink write refused; outside target unchanged", flush=True)


# ---------------------------------------------------------------------------
# K. Missing identity prints usage and fails
# ---------------------------------------------------------------------------


def test_missing_identity_argument_is_non_success_usage_and_does_not_rewrite():
    """membundle update with no identity argument is usage-class, unlike empty/reserved/not-found/load/success."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "nf")
        new_desc, missing_id = rest
        rel = _bundle()
        cwd_root = seed_updatable_concept(
            ws, ".", ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        paths = path_tokens_for(rel, ws.path)
        success, _before, _after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        require_update_success(success)
        empty = run_update(ws, "", rel, description=new_desc)
        require_update_failure(empty)
        reserved = run_update(ws, "index", rel, description=new_desc)
        require_update_failure(reserved)
        not_found = run_update(ws, missing_id, rel, description=new_desc)
        require_update_failure(not_found)
        missing_dir = unique_tokens("noload")[0]
        load_error = run_update(ws, missing_id, missing_dir, description=new_desc)
        require_update_failure(load_error)
        before_snap = snapshot_tree(ws.path)
        missing = run_update(ws, None, None)
        require_update_failure(missing)
        usage_report = require_update_usage_failure(
            missing,
            empty,
            reserved,
            not_found,
            load_error,
            success,
            not_found_identity=missing_id,
            success_identity=ident,
            success_bundle=rel,
        )
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=".")
        assert_no_successful_rewrite(
            cwd_root,
            ident,
            seed_title=title,
            seed_description=desc,
            seed_body=body,
            path_tokens=paths,
        )
        print("missing identity is usage-class and did not rewrite", flush=True)
        assert missing.returncode != 0, (
            f"update with a missing identity argument succeeded; "
            f"report={usage_report!r}"
        )
        assert usage_report, (
            "update with a missing identity argument produced empty combined "
            "streams"
        )


def test_mcp_missing_identity_is_tool_error_and_does_not_rewrite():
    """MCP tools-call missing concept_id is a tool error, not a protocol error."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        before_snap = snapshot_tree(ws.path)
        outcome = mcp_membundle_update(
            ws, {"description": new_desc, "bundle": rel}, request_id=80
        )
        require_mcp_update_tool_error(outcome)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        _live_mcp_rewrite(ws, rel)
        print("mcp missing identity is tool error", flush=True)


# ---------------------------------------------------------------------------
# L. Not found does not create a file; load failure is a load error
# ---------------------------------------------------------------------------


def test_missing_identity_in_bundle_is_not_found_and_does_not_create_a_file():
    """Well-formed identity not in a loadable bundle is not-found and creates no file."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "ghost")
        new_desc, ghost = rest
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        missing_dir = unique_tokens("ldir")[0]
        paths = path_tokens_for(rel, missing_dir, ws.path)
        before_snap = snapshot_tree(ws.path)
        not_found = run_update(ws, ghost, rel, description=new_desc)
        require_update_failure(not_found)
        ghost_path = concept_file(ws.resolve(rel), ghost)
        assert not path_is_file(ghost_path), (
            "command-line update of a missing identity does not succeed and "
            "does not create a file"
        )
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        load_error = run_update(ws, ghost, missing_dir, description=new_desc)
        require_update_failure(load_error)
        require_update_not_found(not_found, ghost, "update of an absent identity")
        require_update_load_failure(load_error, "update in a missing bundle directory")
        _live_cli_rewrite(ws, rel)
        print("missing identity in bundle is not-found and created no file", flush=True)


def test_mcp_missing_identity_in_bundle_is_tool_error_and_does_not_create_a_file():
    """MCP missing identity does not succeed and does not create a file."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "ghost")
        new_desc, ghost = rest
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        missing_dir = unique_tokens("mldir")[0]
        paths = path_tokens_for(rel, missing_dir, ws.path)
        before_snap = snapshot_tree(ws.path)
        not_found = mcp_update(ws, ghost, description=new_desc, bundle=rel, request_id=81)
        require_mcp_update_non_success(not_found)
        ghost_path = concept_file(ws.resolve(rel), ghost)
        assert not path_is_file(ghost_path), (
            "update of a missing identity does not succeed and does not create "
            "a file"
        )
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        load_error = mcp_update(
            ws, ghost, description=new_desc, bundle=missing_dir, request_id=82
        )
        require_mcp_update_non_success(load_error)
        require_mcp_update_not_found(not_found, ghost, "membundle_update of an absent identity")
        require_mcp_update_load_failure(load_error, "membundle_update of a missing named bundle")
        print("mcp missing identity failed and created no file", flush=True)


def test_missing_bundle_directory_is_load_error_not_not_found():
    """Missing bundle directory is a load error, distinguishable from not-found."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        missing_dir = unique_tokens("ldir2")[0]
        ghost = unique_tokens("gone")[0]
        paths = path_tokens_for(rel, missing_dir, ws.path)
        not_found = run_update(ws, ghost, rel, description=new_desc)
        require_update_failure(not_found)
        load_error = run_update(ws, ident, missing_dir, description=new_desc)
        require_update_failure(load_error)
        require_update_not_found(not_found, ghost, "update of an absent identity")
        require_update_load_failure(load_error, "update in a missing bundle directory")
        _live_cli_rewrite(ws, rel)
        print("missing bundle directory is load error not not-found", flush=True)


def test_mcp_missing_bundle_is_tool_error_distinct_from_not_found():
    """MCP named missing bundle is a load failure distinct from MCP not-found."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd", "ghost")
        new_desc, ghost = rest
        rel = _bundle()
        seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        missing_dir = unique_tokens("mldir2")[0]
        paths = path_tokens_for(rel, missing_dir, ws.path)
        not_found = mcp_update(ws, ghost, description=new_desc, bundle=rel, request_id=83)
        require_mcp_update_non_success(not_found)
        load_error = mcp_update(
            ws, ghost, description=new_desc, bundle=missing_dir, request_id=84
        )
        require_mcp_update_non_success(load_error)
        require_mcp_update_not_found(not_found, ghost, "membundle_update of an absent identity")
        require_mcp_update_load_failure(load_error, "membundle_update of a missing named bundle")
        print("mcp missing bundle is load failure distinct from not-found", flush=True)


# ---------------------------------------------------------------------------
# M. Newline or three-dash delimiter in title, description, or actor
# ---------------------------------------------------------------------------


def test_cli_newline_in_each_of_title_description_and_actor_fails_without_successful_update():
    """CLI newline in title, description, and actor each fails without a rewrite."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("bad")
        poison = rest[0] + "\n" + unique_tokens("nlx")[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        for kwargs in (
            {"title": poison},
            {"description": poison},
            {"actor": poison},
        ):
            before_snap = snapshot_tree(ws.path)
            result = run_update(ws, ident, rel, **kwargs)
            require_update_failure(result)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            assert_no_successful_rewrite(
                root,
                ident,
                seed_title=title,
                seed_description=desc,
                seed_body=body,
                new_title=kwargs.get("title"),
                new_description=kwargs.get("description"),
                path_tokens=path_tokens_for(rel, ws.path),
            )
        _live_cli_rewrite(ws, rel)
        print("cli newline in title/description/actor each refused", flush=True)


def test_cli_frontmatter_delimiter_in_each_of_title_description_and_actor_fails_without_successful_update():
    """CLI three-dash delimiter in title, description, and actor each fails without a rewrite."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("bad")
        poison = rest[0] + "---" + unique_tokens("ddx")[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        for kwargs in (
            {"title": poison},
            {"description": poison},
            {"actor": poison},
        ):
            before_snap = snapshot_tree(ws.path)
            result = run_update(ws, ident, rel, **kwargs)
            require_update_failure(result)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            assert_no_successful_rewrite(
                root,
                ident,
                seed_title=title,
                seed_description=desc,
                seed_body=body,
                new_title=kwargs.get("title"),
                new_description=kwargs.get("description"),
                path_tokens=path_tokens_for(rel, ws.path),
            )
        _live_cli_rewrite(ws, rel)
        print("cli --- in title/description/actor each refused", flush=True)


def test_mcp_newline_in_each_of_title_and_description_is_tool_error_and_does_not_rewrite():
    """MCP newline in title and description each fails and does not rewrite."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("bad")
        poison = rest[0] + "\n" + unique_tokens("mnlx")[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        for request_id, kwargs in enumerate(
            ({"title": poison}, {"description": poison}), start=90
        ):
            before_snap = snapshot_tree(ws.path)
            outcome = mcp_update(ws, ident, bundle=rel, request_id=request_id, **kwargs)
            require_mcp_update_non_success(outcome)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            assert_no_successful_rewrite(
                root,
                ident,
                seed_title=title,
                seed_description=desc,
                seed_body=body,
                new_title=kwargs.get("title"),
                new_description=kwargs.get("description"),
                path_tokens=path_tokens_for(rel, ws.path),
            )
        _live_mcp_rewrite(ws, rel)
        print("mcp newline in title/description each refused", flush=True)


def test_mcp_frontmatter_delimiter_in_each_of_title_and_description_is_tool_error_and_does_not_rewrite():
    """MCP three-dash delimiter in title and description each fails without a rewrite."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("bad")
        poison = rest[0] + "---" + unique_tokens("mddx")[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        for request_id, kwargs in enumerate(
            ({"title": poison}, {"description": poison}), start=94
        ):
            before_snap = snapshot_tree(ws.path)
            outcome = mcp_update(ws, ident, bundle=rel, request_id=request_id, **kwargs)
            require_mcp_update_non_success(outcome)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            assert_no_successful_rewrite(
                root,
                ident,
                seed_title=title,
                seed_description=desc,
                seed_body=body,
                new_title=kwargs.get("title"),
                new_description=kwargs.get("description"),
                path_tokens=path_tokens_for(rel, ws.path),
            )
        _live_mcp_rewrite(ws, rel)
        print("mcp --- in title/description each refused", flush=True)


# ---------------------------------------------------------------------------
# N. Structured CLI still rewrites and bookkeeps
# ---------------------------------------------------------------------------


def test_structured_cli_still_rewrites_concept_files():
    """Structured CLI success still rewrites the concept, listing, and Update bullet."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc, structured=True
        )
        today = utc_today_iso()
        require_update_success(result)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert_extra_keys_survive(mapping, extra)
        _assert_bookkeep(
            root,
            ident,
            new_description=new_desc,
            old_description=desc,
            title=title,
            today=today,
            allowed_dates=_dates(today, utc_today_iso()),
            path_tokens=path_tokens_for(rel, ws.path),
        )
        print("structured cli still rewrote concept files and bookkeeping", flush=True)


def test_human_mode_still_rewrites_concept_files():
    """Default human mode on a twin still rewrites the concept, listing, and Update."""
    with workspace() as ws:
        ident, typ, title, desc, body, extra, rest = _runtime_fields("nd")
        new_desc = rest[0]
        ident = f"decisions/{ident}"
        rel = _bundle()
        root = seed_updatable_concept(
            ws, rel, ident, concept_type=typ, title=title, description=desc, body=body, extra=extra
        )
        result, before, after = run_update_with_instants(
            ws, ident, rel, description=new_desc
        )
        today = utc_today_iso()
        require_update_success(result)
        mapping, _body = assert_concept_updated(
            concept_file(root, ident),
            concept_type=typ,
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            before=before,
            after=after,
            description=new_desc,
        )
        assert_extra_keys_survive(mapping, extra)
        _assert_bookkeep(
            root,
            ident,
            new_description=new_desc,
            old_description=desc,
            title=title,
            today=today,
            allowed_dates=_dates(today, utc_today_iso()),
            path_tokens=path_tokens_for(rel, ws.path),
        )
        print("human mode still rewrote concept files", flush=True)

