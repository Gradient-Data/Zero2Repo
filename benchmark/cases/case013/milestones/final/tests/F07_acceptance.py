# feature: F07
"""Acceptance tests for relating two concepts with a relative Markdown link (FP-07).

Public entries: the ``membundle relate`` command and the ``membundle_relate`` Model
Context Protocol tool. Observations go through the sealed harness
``workspace`` / ``invoke`` / ``mcp_batch`` path and the on-disk files
the relate rewrote or refused to rewrite. These tests do not import Go
packages, do not call internal RelateConcepts helpers, and do not use
``membundle show`` / ``membundle validate`` / ``membundle create`` / ``membundle update`` /
``membundle init`` to judge results.
"""

from __future__ import annotations

import os
from pathlib import Path

from _harness import (
    path_is_dir,
    path_is_file,
    read_bytes,
    read_file,
    workspace,
)
from F01_helpers import combined_report, split_yaml_frontmatter
from F03_helpers import (
    assert_snapshot_helper_sees_write,
    markdown_link,
    path_tokens_for,
    snapshot_tree,
    unique_tokens,
)
from F05_helpers import (
    assert_no_new_concept_file,
    concept_file,
    concept_filename,
    generated_by_and_at,
)
from F06_helpers import SEED_GENERATED_AT, SEED_GENERATED_BY
from F07_helpers import (
    SAMPLE_PROSE,
    SAMPLE_SOURCE,
    SAMPLE_TARGET,
    _inline_links,
    assert_deeper_heading_not_reused,
    assert_distinct_related_list_items,
    assert_existing_related_heading_reused,
    assert_fenced_heading_not_reused,
    assert_named_path_relate_landing,
    assert_new_related_concepts_heading,
    assert_no_reciprocal_on_target,
    assert_no_successful_relate,
    assert_prose_follows_link,
    assert_relate_log_bullet,
    assert_related_to_item,
    assert_relative_link_to_target,
    assert_setext_related_heading_not_reused,
    assert_writing_relate_bookkeeping,
    count_related_links_to_target,
    first_named_related_item_for_target,
    mcp_membundle_relate,
    mcp_relate,
    related_section_items,
    require_mcp_relate_non_success,
    require_mcp_relate_success,
    require_mcp_relate_success_text,
    require_mcp_relate_tool_error,
    require_relate_endpoint_not_found,
    require_relate_error_line,
    require_relate_failure,
    require_relate_human_success,
    require_relate_success,
    require_relate_usage_failure,
    run_relate,
    seed_relatable_pair,
    write_relatable_concept,
)



# Generated per test process: the leaf a ``..`` identity aims at, outside
# the bundle (the documents carry no such value).
_OUTSIDE_LEAF = f"o{__import__('uuid').uuid4().hex[:8]}"

def _bundle() -> str:
    return unique_tokens("kb")[0]


def _root(ws, rel: str) -> Path:
    return ws.path if rel in (".", "") else ws.path / rel


def _bundle_arg(rel: str) -> str | None:
    return None if rel in (".", "") else rel


def _extras(*prefixes: str) -> dict[str, str]:
    keys_vals = unique_tokens(*prefixes)
    if len(keys_vals) != 4:
        k1, v1, k2, v2 = unique_tokens("xk1", "xv1", "xk2", "xv2")
        return {k1.replace("-", "_"): v1, k2.replace("-", "_"): v2}
    k1, v1, k2, v2 = keys_vals
    return {k1.replace("-", "_"): v1, k2.replace("-", "_"): v2}


def _final_segment(identity: str) -> str:
    name = Path(identity).name
    assert name, f"identity has no final segment: {identity!r}"
    return name


def _same_fields(*more: str):
    tokens = unique_tokens(
        "dir",
        "src",
        "tgt",
        "sty",
        "tty",
        "stl",
        "ttl",
        "sbd",
        "tbd",
        "prs",
        "unp",
        "xk1",
        "xv1",
        "xk2",
        "xv2",
        *more,
    )
    directory, src, tgt = tokens[0], tokens[1], tokens[2]
    extra = {
        tokens[11].replace("-", "_"): tokens[12],
        tokens[13].replace("-", "_"): tokens[14],
    }
    return {
        "source_id": f"{directory}/{src}",
        "target_id": f"{directory}/{tgt}",
        "source_type": tokens[3],
        "target_type": tokens[4],
        "source_title": tokens[5],
        "target_title": tokens[6],
        "source_body": tokens[7],
        "target_body": tokens[8],
        "prose": tokens[9],
        "unused_prose": tokens[10],
        "extra": extra,
        "rest": tokens[15:],
    }


def _cross_pair(*more: str):
    """Same-shape fields as ``_same_fields`` with source and target in different directories."""
    tokens = unique_tokens(
        "sd",
        "td",
        "src",
        "tgt",
        "sty",
        "tty",
        "stl",
        "ttl",
        "sbd",
        "tbd",
        "prs",
        "unp",
        "xk1",
        "xv1",
        "xk2",
        "xv2",
        *more,
    )
    extra = {
        tokens[12].replace("-", "_"): tokens[13],
        tokens[14].replace("-", "_"): tokens[15],
    }
    return {
        "source_id": f"{tokens[0]}/{tokens[2]}",
        "target_id": f"{tokens[1]}/{tokens[3]}",
        "source_type": tokens[4],
        "target_type": tokens[5],
        "source_title": tokens[6],
        "target_title": tokens[7],
        "source_body": tokens[8],
        "target_body": tokens[9],
        "prose": tokens[10],
        "unused_prose": tokens[11],
        "extra": extra,
        "rest": tokens[16:],
    }


def _parent_nested_pair(*more: str):
    """Source in a parent directory, target nested under that parent (descendant href)."""
    tokens = unique_tokens(
        "pd",
        "cd",
        "src",
        "tgt",
        "sty",
        "tty",
        "stl",
        "ttl",
        "sbd",
        "tbd",
        "prs",
        "unp",
        "xk1",
        "xv1",
        "xk2",
        "xv2",
        *more,
    )
    extra = {
        tokens[12].replace("-", "_"): tokens[13],
        tokens[14].replace("-", "_"): tokens[15],
    }
    return {
        "source_id": f"{tokens[0]}/{tokens[2]}",
        "target_id": f"{tokens[0]}/{tokens[1]}/{tokens[3]}",
        "source_type": tokens[4],
        "target_type": tokens[5],
        "source_title": tokens[6],
        "target_title": tokens[7],
        "source_body": tokens[8],
        "target_body": tokens[9],
        "prose": tokens[10],
        "unused_prose": tokens[11],
        "extra": extra,
        "rest": tokens[16:],
    }


def _seed(ws, rel: str, fields, *, source_body: str | None = None, extra_concepts=(), agents=None):
    return seed_relatable_pair(
        ws,
        rel,
        fields["source_id"],
        fields["target_id"],
        source_type=fields["source_type"],
        source_title=fields["source_title"],
        source_body=source_body if source_body is not None else fields["source_body"],
        target_type=fields["target_type"],
        target_title=fields["target_title"],
        target_body=fields["target_body"],
        extra=fields["extra"],
        extra_concepts=extra_concepts,
        agents=agents,
    )


def _titles(fields) -> tuple[str, str]:
    return (fields["source_title"], fields["target_title"])


def _assert_related_to(item: str, fields, path_tokens) -> None:
    links = _inline_links(item)
    assert links, f"related-to item has no inline link: {item!r}"
    assert_related_to_item(
        item,
        unused_prose=fields["unused_prose"],
        identities=(fields["source_id"], fields["target_id"]),
        filenames=(
            concept_filename(fields["source_id"]),
            concept_filename(fields["target_id"]),
        ),
        titles=_titles(fields),
        path_tokens=path_tokens,
        href=links[0][1],
    )


def _assert_writing(
    root: Path,
    fields,
    *,
    generated_by: str,
    path_tokens,
    href_mode: str,
    prose: str | None,
    new_heading: bool = False,
    link_text: str | None = None,
    exclude_setext_title: str | None = None,
) -> str:
    source_id = fields["source_id"]
    target_id = fields["target_id"]
    text = link_text if link_text is not None else fields["target_title"]
    item = assert_relative_link_to_target(
        concept_file(root, source_id),
        source_id,
        target_id,
        link_text=text,
        href_mode=href_mode,
        exclude_setext_title=exclude_setext_title,
    )
    mapping, body = split_yaml_frontmatter(read_file(concept_file(root, source_id)))
    if new_heading:
        assert_new_related_concepts_heading(body)
    if prose:
        assert_prose_follows_link(item, prose)
    else:
        _assert_related_to(item, fields, path_tokens)
    assert_writing_relate_bookkeeping(
        root,
        source_id,
        target_id,
        generated_by=generated_by,
        seed_generated_at=SEED_GENERATED_AT,
        extra=fields["extra"],
        seed_body_token=fields["source_body"],
        titles=_titles(fields),
        path_tokens=path_tokens,
    )
    print(
        f"[F07] writing relate source={source_id!r} target={target_id!r} "
        f"by={generated_by!r} href_mode={href_mode}",
        flush=True,
    )
    return item


def _live_cli_relate(ws, rel: str) -> None:
    fields = _same_fields("lv")
    root = _root(ws, rel)
    write_relatable_concept(
        root,
        fields["source_id"],
        concept_type=fields["source_type"],
        title=fields["source_title"],
        body=fields["source_body"],
        extra=fields["extra"],
    )
    write_relatable_concept(
        root,
        fields["target_id"],
        concept_type=fields["target_type"],
        title=fields["target_title"],
        body=fields["target_body"],
    )
    result = run_relate(
        ws,
        fields["source_id"],
        fields["target_id"],
        _bundle_arg(rel),
        description=fields["prose"],
    )
    require_relate_success(result)
    _assert_writing(
        root,
        fields,
        generated_by="agent/cli",
        path_tokens=path_tokens_for(rel, ws.path),
        href_mode="named",
        prose=fields["prose"],
        new_heading=True,
    )
    print(f"[F07] live cli relate {fields['source_id']!r}", flush=True)


def _live_mcp_relate(ws, rel: str) -> None:
    fields = _same_fields("mv")
    root = _root(ws, rel)
    write_relatable_concept(
        root,
        fields["source_id"],
        concept_type=fields["source_type"],
        title=fields["source_title"],
        body=fields["source_body"],
        extra=fields["extra"],
    )
    write_relatable_concept(
        root,
        fields["target_id"],
        concept_type=fields["target_type"],
        title=fields["target_title"],
        body=fields["target_body"],
    )
    outcome = mcp_relate(
        ws,
        fields["source_id"],
        fields["target_id"],
        description=fields["prose"],
        bundle=_bundle_arg(rel),
    )
    require_mcp_relate_success(outcome)
    _assert_writing(
        root,
        fields,
        generated_by="agent/mcp",
        path_tokens=path_tokens_for(rel, ws.path),
        href_mode="named",
        prose=fields["prose"],
        new_heading=True,
    )
    print(f"[F07] live mcp relate {fields['source_id']!r}", flush=True)


# ---------------------------------------------------------------------------
# A. Public-sample same-directory relate
# ---------------------------------------------------------------------------


def test_cli_generated_sample_relate_writes_relative_link_prose_heading_and_log():
    """CLI relate of a generated same-directory pair writes named href, prose, heading, log."""
    with workspace() as ws:
        source_title, target_title, source_body, target_body = unique_tokens(
            "pstl", "pttl", "psbd", "ptbd"
        )
        extra = _extras("pxk1", "pxv1", "pxk2", "pxv2")
        rel = _bundle()
        fields = {
            "source_id": SAMPLE_SOURCE,
            "target_id": SAMPLE_TARGET,
            "source_type": unique_tokens("psty")[0],
            "target_type": unique_tokens("ptty")[0],
            "source_title": source_title,
            "target_title": target_title,
            "source_body": source_body,
            "target_body": target_body,
            "prose": SAMPLE_PROSE,
            "unused_prose": unique_tokens("punp")[0],
            "extra": extra,
        }
        root = seed_relatable_pair(
            ws,
            rel,
            SAMPLE_SOURCE,
            SAMPLE_TARGET,
            source_type=fields["source_type"],
            source_title=source_title,
            source_body=source_body,
            target_type=fields["target_type"],
            target_title=target_title,
            target_body=target_body,
            extra=extra,
        )
        before_snap = snapshot_tree(ws.path)
        result = run_relate(
            ws,
            SAMPLE_SOURCE,
            SAMPLE_TARGET,
            rel,
            description=SAMPLE_PROSE,
        )
        report = require_relate_success(result)
        assert path_is_file(concept_file(root, SAMPLE_SOURCE))
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=SAMPLE_PROSE,
            new_heading=True,
        )
        assert_no_reciprocal_on_target(
            concept_file(root, SAMPLE_TARGET),
            SAMPLE_TARGET,
            SAMPLE_SOURCE,
        )
        require_relate_human_success(result, SAMPLE_SOURCE, SAMPLE_TARGET, rel)
        print("cli public-sample relate wrote named relative link, heading, and Update", flush=True)


def test_mcp_generated_sample_relate_writes_relative_link_and_agent_mcp():
    """MCP relate of the public-sample pair writes named href and generated.by agent/mcp."""
    with workspace() as ws:
        source_title, target_title, source_body, target_body = unique_tokens(
            "mstl", "mttl", "msbd", "mtbd"
        )
        extra = _extras("mxk1", "mxv1", "mxk2", "mxv2")
        rel = _bundle()
        fields = {
            "source_id": SAMPLE_SOURCE,
            "target_id": SAMPLE_TARGET,
            "source_type": unique_tokens("msty")[0],
            "target_type": unique_tokens("mtty")[0],
            "source_title": source_title,
            "target_title": target_title,
            "source_body": source_body,
            "target_body": target_body,
            "prose": SAMPLE_PROSE,
            "unused_prose": unique_tokens("munp")[0],
            "extra": extra,
        }
        root = seed_relatable_pair(
            ws,
            rel,
            SAMPLE_SOURCE,
            SAMPLE_TARGET,
            source_type=fields["source_type"],
            source_title=source_title,
            source_body=source_body,
            target_type=fields["target_type"],
            target_title=target_title,
            target_body=target_body,
            extra=extra,
        )
        outcome = mcp_relate(
            ws,
            SAMPLE_SOURCE,
            SAMPLE_TARGET,
            description=SAMPLE_PROSE,
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=SAMPLE_PROSE,
            new_heading=True,
        )
        assert_no_reciprocal_on_target(
            concept_file(root, SAMPLE_TARGET),
            SAMPLE_TARGET,
            SAMPLE_SOURCE,
        )
        require_mcp_relate_success_text(outcome, SAMPLE_SOURCE, SAMPLE_TARGET, root)
        print("mcp public-sample relate wrote named relative link and agent/mcp", flush=True)


def test_cli_generated_sample_shape_has_runtime_twin():
    """CLI same-directory runtime twin uses filename.md / ./filename.md href."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        report = require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        assert_no_reciprocal_on_target(
            concept_file(root, fields["target_id"]),
            fields["target_id"],
            fields["source_id"],
        )
        require_relate_human_success(result, fields["source_id"], fields["target_id"], rel)
        print("cli public-sample shape has a runtime twin", flush=True)


def test_mcp_generated_sample_shape_has_runtime_twin():
    """MCP same-directory runtime twin uses filename.md / ./filename.md href."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        assert_no_reciprocal_on_target(
            concept_file(root, fields["target_id"]),
            fields["target_id"],
            fields["source_id"],
        )
        require_mcp_relate_success_text(outcome, fields["source_id"], fields["target_id"], root)
        print("mcp public-sample shape has a runtime twin", flush=True)


# ---------------------------------------------------------------------------
# B. Cross-directory relative path
# ---------------------------------------------------------------------------


def test_cli_cross_directory_href_resolves_relative_to_source_directory():
    """CLI nested-versus-sibling href POSIX-resolves to the target file."""
    with workspace() as ws:
        fields = _cross_pair()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="resolve",
            prose=fields["prose"],
            new_heading=True,
        )
        print("cli cross-directory href resolved relative to the source directory", flush=True)


def test_mcp_cross_directory_href_resolves_relative_to_source_directory():
    """MCP nested-versus-sibling href POSIX-resolves to the target file."""
    with workspace() as ws:
        fields = _cross_pair()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="resolve",
            prose=fields["prose"],
            new_heading=True,
        )
        print("mcp cross-directory href resolved relative to the source directory", flush=True)


def test_cli_parent_directory_source_href_resolves_to_nested_target():
    """CLI parent-directory source href POSIX-resolves to a nested target."""
    with workspace() as ws:
        fields = _parent_nested_pair()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="resolve",
            prose=fields["prose"],
            new_heading=True,
        )
        print("cli parent-directory source href resolved to the nested target", flush=True)


def test_mcp_parent_directory_source_href_resolves_to_nested_target():
    """MCP parent-directory source href POSIX-resolves to a nested target."""
    with workspace() as ws:
        fields = _parent_nested_pair()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="resolve",
            prose=fields["prose"],
            new_heading=True,
        )
        print("mcp parent-directory source href resolved to the nested target", flush=True)


# ---------------------------------------------------------------------------
# C. Link text is title, or final identity segment when title is empty
# ---------------------------------------------------------------------------


def test_cli_empty_target_title_uses_final_identity_segment_as_link_text():
    """CLI empty target title (omitted key and empty scalar) uses the final identity segment."""
    with workspace() as ws:
        for encoding, title in (("omitted", None), ("empty_scalar", "")):
            fields = _same_fields(encoding)
            unused_title = fields["rest"][0]
            fields["target_title"] = title
            rel = _bundle()
            root = seed_relatable_pair(
                ws,
                rel,
                fields["source_id"],
                fields["target_id"],
                source_type=fields["source_type"],
                source_title=fields["source_title"],
                source_body=fields["source_body"],
                target_type=fields["target_type"],
                target_title=title,
                target_body=fields["target_body"],
                extra=fields["extra"],
            )
            mapping, _body = split_yaml_frontmatter(
                read_file(concept_file(root, fields["target_id"]))
            )
            if encoding == "omitted":
                assert "title:" not in mapping, (
                    "omitted-title seed still has a title key in the YAML"
                )
            else:
                assert 'title: ""' in mapping, (
                    "empty-scalar seed did not plant title: \"\" in the YAML; "
                    f"mapping={mapping!r}"
                )
            result = run_relate(
                ws,
                fields["source_id"],
                fields["target_id"],
                rel,
                description=fields["prose"],
            )
            require_relate_success(result)
            item = _assert_writing(
                root,
                fields,
                generated_by="agent/cli",
                path_tokens=path_tokens_for(rel, ws.path),
                href_mode="named",
                prose=fields["prose"],
                new_heading=True,
                link_text=_final_segment(fields["target_id"]),
            )
            assert unused_title not in item, (
                f"unused title token {unused_title!r} appeared on an empty-title link item"
            )
            print(f"cli empty target title ({encoding}) used the final identity segment", flush=True)


def test_mcp_empty_target_title_uses_final_identity_segment_as_link_text():
    """MCP empty target title (omitted key and empty scalar) uses the final identity segment."""
    with workspace() as ws:
        for encoding, title in (("omitted", None), ("empty_scalar", "")):
            fields = _same_fields(f"m{encoding}")
            unused_title = fields["rest"][0]
            fields["target_title"] = title
            rel = _bundle()
            root = seed_relatable_pair(
                ws,
                rel,
                fields["source_id"],
                fields["target_id"],
                source_type=fields["source_type"],
                source_title=fields["source_title"],
                source_body=fields["source_body"],
                target_type=fields["target_type"],
                target_title=title,
                target_body=fields["target_body"],
                extra=fields["extra"],
            )
            mapping, _body = split_yaml_frontmatter(
                read_file(concept_file(root, fields["target_id"]))
            )
            if encoding == "omitted":
                assert "title:" not in mapping, (
                    "omitted-title seed still has a title key in the YAML"
                )
            else:
                assert 'title: ""' in mapping, (
                    "empty-scalar seed did not plant title: \"\" in the YAML; "
                    f"mapping={mapping!r}"
                )
            outcome = mcp_relate(
                ws,
                fields["source_id"],
                fields["target_id"],
                description=fields["prose"],
                bundle=rel,
            )
            require_mcp_relate_success(outcome)
            item = _assert_writing(
                root,
                fields,
                generated_by="agent/mcp",
                path_tokens=path_tokens_for(rel, ws.path),
                href_mode="named",
                prose=fields["prose"],
                new_heading=True,
                link_text=_final_segment(fields["target_id"]),
            )
            assert unused_title not in item
            print(f"mcp empty target title ({encoding}) used the final identity segment", flush=True)


# ---------------------------------------------------------------------------
# D. Relationship prose vs Related to
# ---------------------------------------------------------------------------


def test_cli_omitted_empty_and_whitespace_prose_each_write_a_related_to_link():
    """CLI omit, empty, and whitespace prose each write a Related to link."""
    with workspace() as ws:
        for kind in ("omit", "empty", "whitespace"):
            fields = _same_fields(kind)
            rel = _bundle()
            root = _seed(ws, rel, fields)
            kwargs = {}
            if kind == "empty":
                kwargs["description"] = ""
            elif kind == "whitespace":
                kwargs["description"] = "   "
            result = run_relate(
                ws,
                fields["source_id"],
                fields["target_id"],
                rel,
                **kwargs,
            )
            require_relate_success(result)
            _assert_writing(
                root,
                fields,
                generated_by="agent/cli",
                path_tokens=path_tokens_for(rel, ws.path),
                href_mode="named",
                prose=None,
                new_heading=True,
            )
            print(f"cli {kind} prose wrote a Related to link", flush=True)


def test_mcp_omitted_empty_and_whitespace_prose_each_write_a_related_to_link():
    """MCP omit, empty, and whitespace description each write a Related to link."""
    with workspace() as ws:
        for kind in ("omit", "empty", "whitespace"):
            fields = _same_fields(f"m{kind}")
            rel = _bundle()
            root = _seed(ws, rel, fields)
            kwargs = {"bundle": rel}
            if kind == "empty":
                kwargs["description"] = ""
            elif kind == "whitespace":
                kwargs["description"] = "   "
            outcome = mcp_relate(
                ws, fields["source_id"], fields["target_id"], **kwargs
            )
            require_mcp_relate_success(outcome)
            _assert_writing(
                root,
                fields,
                generated_by="agent/mcp",
                path_tokens=path_tokens_for(rel, ws.path),
                href_mode="named",
                prose=None,
                new_heading=True,
            )
            print(f"mcp {kind} prose wrote a Related to link", flush=True)


# ---------------------------------------------------------------------------
# E. Heading reuse, deeper, fenced, Setext otherwise-create, hyphen deeper
# ---------------------------------------------------------------------------


def _heading_pair(ws, rel: str, source_body: str, prefix: str):
    fields = _same_fields(prefix)
    fields["source_body"] = unique_tokens(f"{prefix}sb")[0]
    body = f"{source_body}\n{fields['source_body']}\n"
    root = _seed(ws, rel, fields, source_body=body)
    return fields, root, body


def _plant_pair(ws, rel: str, fields, source_body: str, root):
    """Seed the bundle on the first pair; write later pairs into the same bundle."""
    if root is None:
        return _seed(ws, rel, fields, source_body=source_body)
    write_relatable_concept(
        root,
        fields["source_id"],
        concept_type=fields["source_type"],
        title=fields["source_title"],
        body=source_body,
        extra=fields["extra"],
    )
    write_relatable_concept(
        root,
        fields["target_id"],
        concept_type=fields["target_type"],
        title=fields["target_title"],
        body=fields["target_body"],
    )
    return root


def _relate_via(ws, fields, rel: str, via: str):
    if via == "cli":
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(result)
        return "agent/cli"
    outcome = mcp_relate(
        ws,
        fields["source_id"],
        fields["target_id"],
        description=fields["prose"],
        bundle=rel,
    )
    require_mcp_relate_success(outcome)
    return "agent/mcp"


def test_cli_and_mcp_existing_level1_related_concepts_heading_is_reused():
    """Existing level-1 Related Concepts is reused on CLI and MCP; following token remains."""
    with workspace() as ws:
        rel = _bundle()
        following_cli, following_mcp = unique_tokens("fcli", "fmcp")
        cli, root, _body = _heading_pair(
            ws, rel, f"# Related Concepts\n\n- {following_cli}\n", "hcli"
        )
        mcp_fields = _same_fields("hmcp")
        mcp_body_token = mcp_fields["source_body"]
        mcp_fields["source_body"] = mcp_body_token
        write_relatable_concept(
            root,
            mcp_fields["source_id"],
            concept_type=mcp_fields["source_type"],
            title=mcp_fields["source_title"],
            body=f"# Related Concepts\n\n- {following_mcp}\n\n{mcp_body_token}\n",
            extra=mcp_fields["extra"],
        )
        write_relatable_concept(
            root,
            mcp_fields["target_id"],
            concept_type=mcp_fields["target_type"],
            title=mcp_fields["target_title"],
            body=mcp_fields["target_body"],
        )
        result = run_relate(
            ws, cli["source_id"], cli["target_id"], rel, description=cli["prose"]
        )
        require_relate_success(result)
        _assert_writing(
            root,
            cli,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=cli["prose"],
        )
        _mapping, body = split_yaml_frontmatter(
            read_file(concept_file(root, cli["source_id"]))
        )
        assert_existing_related_heading_reused(body, "Related Concepts", following_cli)
        outcome = mcp_relate(
            ws,
            mcp_fields["source_id"],
            mcp_fields["target_id"],
            description=mcp_fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            mcp_fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=mcp_fields["prose"],
        )
        _mapping, mcp_body = split_yaml_frontmatter(
            read_file(concept_file(root, mcp_fields["source_id"]))
        )
        assert_existing_related_heading_reused(
            mcp_body, "Related Concepts", following_mcp
        )
        print("cli and mcp reused existing level-1 Related Concepts", flush=True)


def test_cli_and_mcp_existing_level1_related_heading_is_reused_and_does_not_create_related_concepts():
    """Existing level-1 Related is reused before a following Notes heading; Related Concepts is not created."""
    with workspace() as ws:
        rel = _bundle()
        following_cli, following_mcp, notes_cli, notes_mcp = unique_tokens(
            "rcli", "rmcp", "nrcli", "nrmcp"
        )
        cli, root, _body = _heading_pair(
            ws,
            rel,
            f"# Related\n\n- {following_cli}\n\n# Notes\n\n{notes_cli}\n",
            "rcli",
        )
        mcp_fields = _same_fields("rmcp")
        mcp_body_token = mcp_fields["source_body"]
        write_relatable_concept(
            root,
            mcp_fields["source_id"],
            concept_type=mcp_fields["source_type"],
            title=mcp_fields["source_title"],
            body=(
                f"# Related\n\n- {following_mcp}\n\n# Notes\n\n{notes_mcp}\n\n"
                f"{mcp_body_token}\n"
            ),
            extra=mcp_fields["extra"],
        )
        write_relatable_concept(
            root,
            mcp_fields["target_id"],
            concept_type=mcp_fields["target_type"],
            title=mcp_fields["target_title"],
            body=mcp_fields["target_body"],
        )
        result = run_relate(
            ws, cli["source_id"], cli["target_id"], rel, description=cli["prose"]
        )
        require_relate_success(result)
        _assert_writing(
            root,
            cli,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=cli["prose"],
        )
        _mapping, body = split_yaml_frontmatter(
            read_file(concept_file(root, cli["source_id"]))
        )
        assert_existing_related_heading_reused(
            body, "Related", following_cli, forbid_related_concepts=True
        )
        _heading, items = related_section_items(body, required=True)
        section = "\n".join(items)
        assert notes_cli not in section, (
            "Notes token leaked into the Related section; the new item was "
            f"not placed before the following heading; section={section!r}"
        )
        assert notes_cli in body
        outcome = mcp_relate(
            ws,
            mcp_fields["source_id"],
            mcp_fields["target_id"],
            description=mcp_fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            mcp_fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=mcp_fields["prose"],
        )
        _mapping, mcp_body = split_yaml_frontmatter(
            read_file(concept_file(root, mcp_fields["source_id"]))
        )
        assert_existing_related_heading_reused(
            mcp_body, "Related", following_mcp, forbid_related_concepts=True
        )
        _heading, mcp_items = related_section_items(mcp_body, required=True)
        mcp_section = "\n".join(mcp_items)
        assert notes_mcp not in mcp_section
        assert notes_mcp in mcp_body
        print("cli and mcp reused Related before Notes and did not create Related Concepts", flush=True)


def test_cli_and_mcp_deeper_related_concepts_or_related_heading_is_not_reused():
    """A deeper Related Concepts or Related heading is not reused on CLI and MCP."""
    with workspace() as ws:
        rel = _bundle()
        root = None
        for heading_text, via, prefix in (
            ("Related Concepts", "cli", "dc1"),
            ("Related Concepts", "mcp", "dc2"),
            ("Related", "cli", "dc3"),
            ("Related", "mcp", "dc4"),
        ):
            token = unique_tokens(prefix)[0]
            fields = _same_fields(prefix)
            body_token = fields["source_body"]
            source_body = f"## {heading_text}\n\n{token}\n\n{body_token}\n"
            root = _plant_pair(ws, rel, fields, source_body, root)
            generated_by = _relate_via(ws, fields, rel, via)
            _assert_writing(
                root,
                fields,
                generated_by=generated_by,
                path_tokens=path_tokens_for(rel, ws.path),
                href_mode="named",
                prose=fields["prose"],
            )
            _mapping, body = split_yaml_frontmatter(
                read_file(concept_file(root, fields["source_id"]))
            )
            assert_deeper_heading_not_reused(
                body,
                heading_text,
                token,
                source_id=fields["source_id"],
                target_id=fields["target_id"],
            )
        print(
            "cli and mcp did not reuse a deeper Related Concepts or Related heading",
            flush=True,
        )


def test_cli_and_mcp_fenced_related_concepts_heading_is_not_reused():
    """A fenced Related Concepts or Related heading is not reused on CLI and MCP."""
    with workspace() as ws:
        rel = _bundle()
        root = None
        for heading_text, via, prefix in (
            ("Related Concepts", "cli", "fc1"),
            ("Related Concepts", "mcp", "fc2"),
            ("Related", "cli", "fc3"),
            ("Related", "mcp", "fc4"),
        ):
            fenced_token = unique_tokens(prefix)[0]
            fields = _same_fields(prefix)
            body_token = fields["source_body"]
            source_body = (
                f"```\n# {heading_text}\n{fenced_token}\n```\n\n{body_token}\n"
            )
            root = _plant_pair(ws, rel, fields, source_body, root)
            generated_by = _relate_via(ws, fields, rel, via)
            _assert_writing(
                root,
                fields,
                generated_by=generated_by,
                path_tokens=path_tokens_for(rel, ws.path),
                href_mode="named",
                prose=fields["prose"],
            )
            _mapping, body = split_yaml_frontmatter(
                read_file(concept_file(root, fields["source_id"]))
            )
            assert_fenced_heading_not_reused(body, fenced_token)
        print(
            "cli and mcp did not reuse a fenced Related Concepts or Related heading",
            flush=True,
        )


def test_cli_and_mcp_list_item_is_placed_under_existing_heading_before_a_following_level1():
    """The new list item sits under Related Concepts and before a following Notes heading."""
    with workspace() as ws:
        rel = _bundle()
        follow_cli, notes_cli, follow_mcp, notes_mcp = unique_tokens(
            "plcli", "ntcli", "plmcp", "ntmcp"
        )
        cli = _same_fields("plcli")
        cli_body = (
            f"# Related Concepts\n\n- {follow_cli}\n\n# Notes\n\n{notes_cli}\n\n"
            f"{cli['source_body']}\n"
        )
        root = _seed(ws, rel, cli, source_body=cli_body)
        mcp_fields = _same_fields("plmcp")
        mcp_body = (
            f"# Related Concepts\n\n- {follow_mcp}\n\n# Notes\n\n{notes_mcp}\n\n"
            f"{mcp_fields['source_body']}\n"
        )
        write_relatable_concept(
            root,
            mcp_fields["source_id"],
            concept_type=mcp_fields["source_type"],
            title=mcp_fields["source_title"],
            body=mcp_body,
            extra=mcp_fields["extra"],
        )
        write_relatable_concept(
            root,
            mcp_fields["target_id"],
            concept_type=mcp_fields["target_type"],
            title=mcp_fields["target_title"],
            body=mcp_fields["target_body"],
        )
        result = run_relate(
            ws, cli["source_id"], cli["target_id"], rel, description=cli["prose"]
        )
        require_relate_success(result)
        _assert_writing(
            root,
            cli,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=cli["prose"],
        )
        _mapping, body = split_yaml_frontmatter(
            read_file(concept_file(root, cli["source_id"]))
        )
        assert_existing_related_heading_reused(body, "Related Concepts", follow_cli)
        _heading, items = related_section_items(body, required=True)
        section = "\n".join(items)
        assert notes_cli not in section, (
            "Notes token leaked into the related section; item was not placed "
            f"before the following level-1; section={section!r}"
        )
        assert notes_cli in body
        outcome = mcp_relate(
            ws,
            mcp_fields["source_id"],
            mcp_fields["target_id"],
            description=mcp_fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            mcp_fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=mcp_fields["prose"],
        )
        _mapping, mcp_after = split_yaml_frontmatter(
            read_file(concept_file(root, mcp_fields["source_id"]))
        )
        assert_existing_related_heading_reused(
            mcp_after, "Related Concepts", follow_mcp
        )
        _heading, mcp_items = related_section_items(mcp_after, required=True)
        mcp_section = "\n".join(mcp_items)
        assert notes_mcp not in mcp_section
        assert notes_mcp in mcp_after
        print("cli and mcp placed the list item under Related Concepts before Notes", flush=True)


def test_cli_and_mcp_setext_related_heading_is_not_reused_and_new_related_concepts_is_created():
    """Setext equals Related Concepts or Related is otherwise-create on CLI and MCP."""
    with workspace() as ws:
        rel = _bundle()
        root = None
        for heading_text, via, prefix in (
            ("Related Concepts", "cli", "sx1"),
            ("Related Concepts", "mcp", "sx2"),
            ("Related", "cli", "sx3"),
            ("Related", "mcp", "sx4"),
        ):
            following = unique_tokens(prefix)[0]
            fields = _same_fields(prefix)
            body_token = fields["source_body"]
            underline = "=" * max(3, len(heading_text))
            source_body = (
                f"{heading_text}\n{underline}\n\n{following}\n\n{body_token}\n"
            )
            root = _plant_pair(ws, rel, fields, source_body, root)
            generated_by = _relate_via(ws, fields, rel, via)
            _assert_writing(
                root,
                fields,
                generated_by=generated_by,
                path_tokens=path_tokens_for(rel, ws.path),
                href_mode="named",
                prose=fields["prose"],
                exclude_setext_title=heading_text,
            )
            _mapping, body = split_yaml_frontmatter(
                read_file(concept_file(root, fields["source_id"]))
            )
            assert_setext_related_heading_not_reused(
                body,
                heading_text,
                following,
                fields["source_id"],
                fields["target_id"],
            )
        print(
            "cli and mcp created a new Related Concepts heading instead of reusing Setext",
            flush=True,
        )


def test_cli_and_mcp_setext_hyphen_related_heading_is_not_reused():
    """Setext hyphen-underline Related Concepts or Related is a deeper heading, not reused."""
    with workspace() as ws:
        rel = _bundle()
        root = None
        for heading_text, via, prefix in (
            ("Related Concepts", "cli", "hy1"),
            ("Related Concepts", "mcp", "hy2"),
            ("Related", "cli", "hy3"),
            ("Related", "mcp", "hy4"),
        ):
            token = unique_tokens(prefix)[0]
            fields = _same_fields(prefix)
            body_token = fields["source_body"]
            underline = "-" * max(3, len(heading_text))
            source_body = (
                f"{heading_text}\n{underline}\n\n{token}\n\n{body_token}\n"
            )
            root = _plant_pair(ws, rel, fields, source_body, root)
            generated_by = _relate_via(ws, fields, rel, via)
            _assert_writing(
                root,
                fields,
                generated_by=generated_by,
                path_tokens=path_tokens_for(rel, ws.path),
                href_mode="named",
                prose=fields["prose"],
            )
            _mapping, body = split_yaml_frontmatter(
                read_file(concept_file(root, fields["source_id"]))
            )
            assert_deeper_heading_not_reused(
                body,
                heading_text,
                token,
                source_id=fields["source_id"],
                target_id=fields["target_id"],
            )
        print(
            "cli and mcp did not reuse a hyphen-underline Related Concepts or Related heading",
            flush=True,
        )


# ---------------------------------------------------------------------------
# F. Actor strings and generated.at refresh
# ---------------------------------------------------------------------------


def test_cli_omitted_actor_writes_agent_cli_not_seed_actor():
    """CLI omit actor writes generated.by agent/cli, not the seed actor."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        assert SEED_GENERATED_BY != "agent/cli"
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("cli omitted actor wrote agent/cli not the seed actor", flush=True)


def test_cli_empty_and_whitespace_actor_each_write_agent_membundle_tool():
    """CLI empty and whitespace actor each write generated.by agent/membundle-tool."""
    with workspace() as ws:
        for actor in ("", "   "):
            fields = _same_fields("act")
            rel = _bundle()
            root = _seed(ws, rel, fields)
            result = run_relate(
                ws,
                fields["source_id"],
                fields["target_id"],
                rel,
                description=fields["prose"],
                actor=actor,
            )
            require_relate_success(result)
            _assert_writing(
                root,
                fields,
                generated_by="agent/membundle-tool",
                path_tokens=path_tokens_for(rel, ws.path),
                href_mode="named",
                prose=fields["prose"],
                new_heading=True,
            )
        print("cli empty and whitespace actor each wrote agent/membundle-tool", flush=True)


def test_cli_supplied_producer_slash_actor_is_written_as_generated_by():
    """A supplied producer-slash-version actor is written through as generated.by."""
    with workspace() as ws:
        fields = _same_fields("psa", "psb")
        left, right = fields["rest"]
        actor = f"{left}/{right}"
        rel = _bundle()
        root = _seed(ws, rel, fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
            actor=actor,
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by=actor,
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("cli producer-slash actor was written as generated.by", flush=True)


def test_cli_supplied_prefix_colon_actor_is_written_as_generated_by():
    """A supplied prefix-colon-id actor is written through as generated.by."""
    with workspace() as ws:
        fields = _same_fields("pca", "pcb")
        left, right = fields["rest"]
        actor = f"{left}:{right}"
        rel = _bundle()
        root = _seed(ws, rel, fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
            actor=actor,
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by=actor,
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("cli prefix-colon actor was written as generated.by", flush=True)


def test_mcp_generated_by_is_agent_mcp():
    """MCP relate writes generated.by agent/mcp."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("mcp generated.by is agent/mcp", flush=True)


def test_cli_generated_at_differs_from_seed_on_writing_relate():
    """CLI writing relate refreshes source generated.at."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("cli generated.at differed from seed on a writing relate", flush=True)


def test_mcp_generated_at_differs_from_seed_on_writing_relate():
    """MCP writing relate refreshes source generated.at."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("mcp generated.at differed from seed on a writing relate", flush=True)


# ---------------------------------------------------------------------------
# G. Log Update naming both files
# ---------------------------------------------------------------------------


def test_log_gains_an_update_bullet_naming_both_files():
    """After a writing relate, log.md has an Update item naming both files."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        item = assert_relate_log_bullet(
            root / "log.md",
            source_id=fields["source_id"],
            target_id=fields["target_id"],
            titles=_titles(fields),
            path_tokens=path_tokens_for(rel, ws.path),
        )
        assert item, "log.md has no Update item naming both files"
        print("log.md gained an Update bullet naming both files", flush=True)


# ---------------------------------------------------------------------------
# H. No reciprocal link
# ---------------------------------------------------------------------------


def test_relate_does_not_add_a_reciprocal_link_on_the_target():
    """Source-to-target adds no source-pointing link on the target; reverse on a fresh copy does."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        assert_no_reciprocal_on_target(
            concept_file(root, fields["target_id"]),
            fields["target_id"],
            fields["source_id"],
        )
        reverse = _same_fields("rev")
        reverse["source_id"] = fields["target_id"]
        reverse["target_id"] = fields["source_id"]
        reverse["source_title"] = fields["target_title"]
        reverse["target_title"] = fields["source_title"]
        reverse["source_body"] = unique_tokens("rvsb")[0]
        reverse["target_body"] = unique_tokens("rvtb")[0]
        reverse_rel = _bundle()
        reverse_root = seed_relatable_pair(
            ws,
            reverse_rel,
            reverse["source_id"],
            reverse["target_id"],
            source_type=fields["target_type"],
            source_title=fields["target_title"],
            source_body=reverse["source_body"],
            target_type=fields["source_type"],
            target_title=fields["source_title"],
            target_body=reverse["target_body"],
            extra=reverse["extra"],
        )
        reverse_result = run_relate(
            ws,
            reverse["source_id"],
            reverse["target_id"],
            reverse_rel,
            description=reverse["prose"],
        )
        require_relate_success(reverse_result)
        _assert_writing(
            reverse_root,
            reverse,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(reverse_rel, ws.path),
            href_mode="named",
            prose=reverse["prose"],
            new_heading=True,
        )
        print("no reciprocal on target; reverse relate on a fresh copy wrote a link", flush=True)


# ---------------------------------------------------------------------------
# I. Same-triple idempotency and distinct complements
# ---------------------------------------------------------------------------


def test_cli_second_same_triple_succeeds_without_rewriting_source_or_log():
    """A second CLI relate of the same source, target, and prose does not rewrite."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        first = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(first)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        source_after = read_bytes(concept_file(root, fields["source_id"]))
        log_after = read_bytes(root / "log.md")
        mapping, _body = split_yaml_frontmatter(
            read_file(concept_file(root, fields["source_id"]))
        )
        _by, first_at = generated_by_and_at(mapping)
        second = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(second)
        assert read_bytes(concept_file(root, fields["source_id"])) == source_after
        assert read_bytes(root / "log.md") == log_after
        assert (
            count_related_links_to_target(
                concept_file(root, fields["source_id"]),
                fields["source_id"],
                fields["target_id"],
            )
            == 1
        )
        mapping2, _body2 = split_yaml_frontmatter(
            read_file(concept_file(root, fields["source_id"]))
        )
        _by2, second_at = generated_by_and_at(mapping2)
        assert second_at == first_at
        print("cli second same-triple did not rewrite source or log", flush=True)


def test_mcp_second_same_triple_succeeds_without_rewriting_source_or_log():
    """A second MCP relate of the same unique-prose triple does not rewrite."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        first = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(first)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        source_after = read_bytes(concept_file(root, fields["source_id"]))
        log_after = read_bytes(root / "log.md")
        second = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
            request_id=11,
        )
        require_mcp_relate_success(second)
        assert read_bytes(concept_file(root, fields["source_id"])) == source_after
        assert read_bytes(root / "log.md") == log_after
        assert (
            count_related_links_to_target(
                concept_file(root, fields["source_id"]),
                fields["source_id"],
                fields["target_id"],
            )
            == 1
        )
        print("mcp second same-triple did not rewrite source or log", flush=True)


def test_cli_second_trim_empty_prose_does_not_duplicate_related_to_line():
    """CLI omit then omit (and a packed empty follow-up) keeps one Related to line."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        first = run_relate(ws, fields["source_id"], fields["target_id"], rel)
        require_relate_success(first)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=None,
            new_heading=True,
        )
        source_after = read_bytes(concept_file(root, fields["source_id"]))
        log_after = read_bytes(root / "log.md")
        second = run_relate(ws, fields["source_id"], fields["target_id"], rel)
        require_relate_success(second)
        assert read_bytes(concept_file(root, fields["source_id"])) == source_after
        assert read_bytes(root / "log.md") == log_after
        packed = run_relate(
            ws, fields["source_id"], fields["target_id"], rel, description=""
        )
        require_relate_success(packed)
        assert read_bytes(concept_file(root, fields["source_id"])) == source_after
        assert read_bytes(root / "log.md") == log_after
        whitespace = run_relate(
            ws, fields["source_id"], fields["target_id"], rel, description="   "
        )
        require_relate_success(whitespace)
        assert read_bytes(concept_file(root, fields["source_id"])) == source_after
        assert read_bytes(root / "log.md") == log_after
        assert (
            count_related_links_to_target(
                concept_file(root, fields["source_id"]),
                fields["source_id"],
                fields["target_id"],
            )
            == 1
        )
        print("cli second trim-empty prose did not duplicate Related to", flush=True)


def test_mcp_second_trim_empty_prose_does_not_duplicate_related_to_line():
    """MCP omit then omit keeps one Related to item; source and log bytes unchanged."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        first = mcp_relate(
            ws, fields["source_id"], fields["target_id"], bundle=rel
        )
        require_mcp_relate_success(first)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=None,
            new_heading=True,
        )
        source_after = read_bytes(concept_file(root, fields["source_id"]))
        log_after = read_bytes(root / "log.md")
        second = mcp_relate(
            ws, fields["source_id"], fields["target_id"], bundle=rel, request_id=11
        )
        require_mcp_relate_success(second)
        assert read_bytes(concept_file(root, fields["source_id"])) == source_after
        assert read_bytes(root / "log.md") == log_after
        packed = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description="",
            bundle=rel,
            request_id=12,
        )
        require_mcp_relate_success(packed)
        assert read_bytes(concept_file(root, fields["source_id"])) == source_after
        assert read_bytes(root / "log.md") == log_after
        whitespace = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description="   ",
            bundle=rel,
            request_id=13,
        )
        require_mcp_relate_success(whitespace)
        assert read_bytes(concept_file(root, fields["source_id"])) == source_after
        assert read_bytes(root / "log.md") == log_after
        assert (
            count_related_links_to_target(
                concept_file(root, fields["source_id"]),
                fields["source_id"],
                fields["target_id"],
            )
            == 1
        )
        print("mcp second trim-empty prose did not duplicate Related to", flush=True)


def test_cli_distinct_prose_on_same_pair_adds_a_second_line():
    """A second CLI relate of the same pair with different prose adds a second line."""
    with workspace() as ws:
        fields = _same_fields("p2")
        prose2 = fields["rest"][0]
        rel = _bundle()
        root = _seed(ws, rel, fields)
        first = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(first)
        source_p1 = read_bytes(concept_file(root, fields["source_id"]))
        log_p1 = read_bytes(root / "log.md")
        second = run_relate(
            ws, fields["source_id"], fields["target_id"], rel, description=prose2
        )
        require_relate_success(second)
        assert_relative_link_to_target(
            concept_file(root, fields["source_id"]),
            fields["source_id"],
            fields["target_id"],
            link_text=fields["target_title"],
            href_mode="named",
        )
        assert_writing_relate_bookkeeping(
            root,
            fields["source_id"],
            fields["target_id"],
            generated_by="agent/cli",
            seed_generated_at=SEED_GENERATED_AT,
            extra=fields["extra"],
            seed_body_token=fields["source_body"],
            titles=_titles(fields),
            path_tokens=path_tokens_for(rel, ws.path),
        )
        _mapping, body = split_yaml_frontmatter(
            read_file(concept_file(root, fields["source_id"]))
        )
        _heading, items = related_section_items(body, required=True)
        idx1, item1, href1 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            fields["target_id"],
            link_text=fields["target_title"],
            prose=fields["prose"],
        )
        idx2, item2, href2 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            fields["target_id"],
            link_text=fields["target_title"],
            prose=prose2,
        )
        assert_distinct_related_list_items(
            idx1,
            item1,
            idx2,
            item2,
            what="the two unique proses",
        )
        assert_prose_follows_link(item1, fields["prose"], after_href=href1)
        assert_prose_follows_link(item2, prose2, after_href=href2)
        assert read_bytes(concept_file(root, fields["source_id"])) != source_p1
        assert read_bytes(root / "log.md") != log_p1
        print("cli distinct prose on the same pair added a second line", flush=True)


def test_mcp_distinct_prose_on_same_pair_adds_a_second_line():
    """A second MCP relate of the same pair with different prose adds a second line."""
    with workspace() as ws:
        fields = _same_fields("mp2")
        prose2 = fields["rest"][0]
        rel = _bundle()
        root = _seed(ws, rel, fields)
        first = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(first)
        log_p1 = read_bytes(root / "log.md")
        second = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=prose2,
            bundle=rel,
            request_id=11,
        )
        require_mcp_relate_success(second)
        assert_relative_link_to_target(
            concept_file(root, fields["source_id"]),
            fields["source_id"],
            fields["target_id"],
            link_text=fields["target_title"],
            href_mode="named",
        )
        assert_writing_relate_bookkeeping(
            root,
            fields["source_id"],
            fields["target_id"],
            generated_by="agent/mcp",
            seed_generated_at=SEED_GENERATED_AT,
            extra=fields["extra"],
            seed_body_token=fields["source_body"],
            titles=_titles(fields),
            path_tokens=path_tokens_for(rel, ws.path),
        )
        _mapping, body = split_yaml_frontmatter(
            read_file(concept_file(root, fields["source_id"]))
        )
        _heading, items = related_section_items(body, required=True)
        idx1, item1, href1 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            fields["target_id"],
            link_text=fields["target_title"],
            prose=fields["prose"],
        )
        idx2, item2, href2 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            fields["target_id"],
            link_text=fields["target_title"],
            prose=prose2,
        )
        assert_distinct_related_list_items(
            idx1,
            item1,
            idx2,
            item2,
            what="the two unique proses",
        )
        assert_prose_follows_link(item1, fields["prose"], after_href=href1)
        assert_prose_follows_link(item2, prose2, after_href=href2)
        assert read_bytes(root / "log.md") != log_p1
        print("mcp distinct prose on the same pair added a second line", flush=True)


def test_cli_second_target_same_prose_adds_a_line():
    """A second CLI relate from the same source to a different target with the same prose adds."""
    with workspace() as ws:
        fields = _same_fields("t2d", "t2s", "t2t", "t2ty", "t2tl", "t2bd")
        t2_dir, t2_src, t2_leaf, t2_type, t2_title, t2_body = fields["rest"]
        target2 = f"{Path(fields['source_id']).parent.as_posix()}/{t2_leaf}"
        rel = _bundle()
        root = _seed(
            ws,
            rel,
            fields,
            extra_concepts=(
                {
                    "identity": target2,
                    "type": t2_type,
                    "title": t2_title,
                    "body": t2_body,
                },
            ),
        )
        first = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(first)
        second = run_relate(
            ws, fields["source_id"], target2, rel, description=fields["prose"]
        )
        require_relate_success(second)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
        )
        assert_relative_link_to_target(
            concept_file(root, fields["source_id"]),
            fields["source_id"],
            target2,
            link_text=t2_title,
            href_mode="named",
        )
        _mapping, body = split_yaml_frontmatter(
            read_file(concept_file(root, fields["source_id"]))
        )
        _heading, items = related_section_items(body, required=True)
        idx1, item1, href1 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            fields["target_id"],
            link_text=fields["target_title"],
        )
        idx2, item2, href2 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            target2,
            link_text=t2_title,
        )
        assert_distinct_related_list_items(
            idx1,
            item1,
            idx2,
            item2,
            what="the two targets",
        )
        assert_prose_follows_link(item1, fields["prose"], after_href=href1)
        assert_prose_follows_link(item2, fields["prose"], after_href=href2)
        print("cli second target with the same prose added a line", flush=True)


def test_mcp_second_target_same_prose_adds_a_line():
    """A second MCP relate from the same source to a different target with the same prose adds."""
    with workspace() as ws:
        fields = _same_fields("mt2", "mt2t", "mt2ty", "mt2tl", "mt2bd")
        t2_leaf, t2_type, t2_title, t2_body = fields["rest"][:4]
        target2 = f"{Path(fields['source_id']).parent.as_posix()}/{t2_leaf}"
        rel = _bundle()
        root = _seed(
            ws,
            rel,
            fields,
            extra_concepts=(
                {
                    "identity": target2,
                    "type": t2_type,
                    "title": t2_title,
                    "body": t2_body,
                },
            ),
        )
        first = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(first)
        second = mcp_relate(
            ws,
            fields["source_id"],
            target2,
            description=fields["prose"],
            bundle=rel,
            request_id=11,
        )
        require_mcp_relate_success(second)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
        )
        assert_relative_link_to_target(
            concept_file(root, fields["source_id"]),
            fields["source_id"],
            target2,
            link_text=t2_title,
            href_mode="named",
        )
        _mapping, body = split_yaml_frontmatter(
            read_file(concept_file(root, fields["source_id"]))
        )
        _heading, items = related_section_items(body, required=True)
        idx1, item1, href1 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            fields["target_id"],
            link_text=fields["target_title"],
        )
        idx2, item2, href2 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            target2,
            link_text=t2_title,
        )
        assert_distinct_related_list_items(
            idx1,
            item1,
            idx2,
            item2,
            what="the two targets",
        )
        assert_prose_follows_link(item1, fields["prose"], after_href=href1)
        assert_prose_follows_link(item2, fields["prose"], after_href=href2)
        print("mcp second target with the same prose added a line", flush=True)


def test_cli_second_target_omit_prose_adds_a_related_to_line():
    """A second CLI omit-prose relate to a third present target adds another Related to."""
    with workspace() as ws:
        fields = _same_fields("t3", "t3ty", "t3tl", "t3bd")
        t3_leaf, t3_type, t3_title, t3_body = fields["rest"][:4]
        target3 = f"{Path(fields['source_id']).parent.as_posix()}/{t3_leaf}"
        rel = _bundle()
        root = _seed(
            ws,
            rel,
            fields,
            extra_concepts=(
                {
                    "identity": target3,
                    "type": t3_type,
                    "title": t3_title,
                    "body": t3_body,
                },
            ),
        )
        first = run_relate(ws, fields["source_id"], fields["target_id"], rel)
        require_relate_success(first)
        second = run_relate(ws, fields["source_id"], target3, rel)
        require_relate_success(second)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=None,
        )
        assert_relative_link_to_target(
            concept_file(root, fields["source_id"]),
            fields["source_id"],
            target3,
            link_text=t3_title,
            href_mode="named",
        )
        t3_fields = dict(fields)
        t3_fields["target_id"] = target3
        t3_fields["target_title"] = t3_title
        _mapping, body = split_yaml_frontmatter(
            read_file(concept_file(root, fields["source_id"]))
        )
        _heading, items = related_section_items(body, required=True)
        idx1, item1, _href1 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            fields["target_id"],
            link_text=fields["target_title"],
        )
        idx3, item3, _href3 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            target3,
            link_text=t3_title,
        )
        assert_distinct_related_list_items(
            idx1,
            item1,
            idx3,
            item3,
            what="the two targets",
        )
        _assert_related_to(item1, fields, path_tokens_for(rel, ws.path))
        _assert_related_to(item3, t3_fields, path_tokens_for(rel, ws.path))
        print("cli second-target omit-prose added a Related to line", flush=True)


def test_mcp_second_target_omit_prose_adds_a_related_to_line():
    """A second MCP omit-prose relate to a third present target adds another Related to."""
    with workspace() as ws:
        fields = _same_fields("mt3", "mt3ty", "mt3tl", "mt3bd")
        t3_leaf, t3_type, t3_title, t3_body = fields["rest"][:4]
        target3 = f"{Path(fields['source_id']).parent.as_posix()}/{t3_leaf}"
        rel = _bundle()
        root = _seed(
            ws,
            rel,
            fields,
            extra_concepts=(
                {
                    "identity": target3,
                    "type": t3_type,
                    "title": t3_title,
                    "body": t3_body,
                },
            ),
        )
        first = mcp_relate(
            ws, fields["source_id"], fields["target_id"], bundle=rel
        )
        require_mcp_relate_success(first)
        second = mcp_relate(
            ws, fields["source_id"], target3, bundle=rel, request_id=11
        )
        require_mcp_relate_success(second)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=None,
        )
        assert_relative_link_to_target(
            concept_file(root, fields["source_id"]),
            fields["source_id"],
            target3,
            link_text=t3_title,
            href_mode="named",
        )
        t3_fields = dict(fields)
        t3_fields["target_id"] = target3
        t3_fields["target_title"] = t3_title
        _mapping, body = split_yaml_frontmatter(
            read_file(concept_file(root, fields["source_id"]))
        )
        _heading, items = related_section_items(body, required=True)
        idx1, item1, _href1 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            fields["target_id"],
            link_text=fields["target_title"],
        )
        idx3, item3, _href3 = first_named_related_item_for_target(
            items,
            fields["source_id"],
            target3,
            link_text=t3_title,
        )
        assert_distinct_related_list_items(
            idx1,
            item1,
            idx3,
            item3,
            what="the two targets",
        )
        _assert_related_to(item1, fields, path_tokens_for(rel, ws.path))
        _assert_related_to(item3, t3_fields, path_tokens_for(rel, ws.path))
        print("mcp second-target omit-prose added a Related to line", flush=True)


def test_cli_existing_body_link_outside_related_section_still_appends_related_item():
    """An unfenced outside-section link to the target is not already-present; CLI still writes."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        outside = markdown_link(
            fields["target_title"], concept_filename(fields["target_id"])
        )
        source_body = f"# Notes\n\nSee {outside}.\n\n{fields['source_body']}\n"
        root = _seed(ws, rel, fields, source_body=source_body)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        after = read_file(concept_file(root, fields["source_id"]))
        assert outside in after, (
            "outside-section Notes link disappeared after a writing relate"
        )
        assert (
            count_related_links_to_target(
                concept_file(root, fields["source_id"]),
                fields["source_id"],
                fields["target_id"],
            )
            == 1
        )
        print("cli outside-section body link still appended a related-section item", flush=True)


def test_mcp_existing_body_link_outside_related_section_still_appends_related_item():
    """An unfenced outside-section link to the target is not already-present; MCP still writes."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        outside = markdown_link(
            fields["target_title"], concept_filename(fields["target_id"])
        )
        source_body = f"# Notes\n\nSee {outside}.\n\n{fields['source_body']}\n"
        root = _seed(ws, rel, fields, source_body=source_body)
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        after = read_file(concept_file(root, fields["source_id"]))
        assert outside in after, (
            "outside-section Notes link disappeared after a writing relate"
        )
        assert (
            count_related_links_to_target(
                concept_file(root, fields["source_id"]),
                fields["source_id"],
                fields["target_id"],
            )
            == 1
        )
        print("mcp outside-section body link still appended a related-section item", flush=True)


# ---------------------------------------------------------------------------
# J. Omit-path default and named-path write root
# ---------------------------------------------------------------------------


def test_omit_path_without_knowledge_dir_relates_cwd():
    """Omit bundle path with no knowledge/ directory relates the cwd pair."""
    with workspace() as ws:
        fields = _same_fields()
        root = _seed(ws, ".", fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        assert not path_is_file(
            ws.path / "knowledge" / f"{fields['source_id']}.md"
        )
        print("omit-path without knowledge/ related cwd", flush=True)


def test_omit_path_with_knowledge_dir_relates_knowledge_not_cwd():
    """Omit bundle path with knowledge/ as a directory relates knowledge/, not a cwd decoy."""
    with workspace() as ws:
        fields = _same_fields("dk")
        decoy = fields["rest"][0]
        root = _seed(ws, "knowledge", fields)
        decoy_path = ws.path / f"{fields['source_id']}.md"
        decoy_path.parent.mkdir(parents=True, exist_ok=True)
        decoy_path.write_text(decoy, encoding="utf-8")
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for("knowledge", ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        assert decoy_path.read_text(encoding="utf-8") == decoy
        print("omit-path with knowledge/ related knowledge not cwd", flush=True)


def test_omit_path_knowledge_file_is_not_treated_as_bundle_dir():
    """A file named knowledge is not a directory, so omit-path uses cwd."""
    with workspace() as ws:
        fields = _same_fields()
        root = _seed(ws, ".", fields)
        knowledge_file = ws.path / "knowledge"
        knowledge_file.write_text("not-a-directory\n", encoding="utf-8")
        before_bytes = read_bytes(knowledge_file)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
        )
        require_relate_success(result)
        assert knowledge_file.is_file()
        assert read_bytes(knowledge_file) == before_bytes
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("knowledge file was not treated as a bundle dir", flush=True)


def test_mcp_omit_bundle_knowledge_file_is_not_treated_as_bundle_dir():
    """MCP omit-bundle: a file named knowledge is not a directory, so omit-path uses cwd."""
    with workspace() as ws:
        fields = _same_fields()
        root = _seed(ws, ".", fields)
        knowledge_file = ws.path / "knowledge"
        knowledge_file.write_text("not-a-directory\n", encoding="utf-8")
        before_bytes = read_bytes(knowledge_file)
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
        )
        require_mcp_relate_success(outcome)
        assert knowledge_file.is_file()
        assert read_bytes(knowledge_file) == before_bytes
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("mcp knowledge file was not treated as a bundle dir", flush=True)


def test_explicit_bundle_path_is_not_overridden_by_cwd_knowledge():
    """A named bundle path is the write target even when cwd has knowledge/."""
    with workspace() as ws:
        fields = _same_fields("dk")
        decoy = fields["rest"][0]
        rel = _bundle()
        root = _seed(ws, rel, fields)
        decoy_dir = ws.path / "knowledge"
        decoy_dir.mkdir()
        decoy_path = decoy_dir / f"{fields['source_id']}.md"
        decoy_path.parent.mkdir(parents=True, exist_ok=True)
        decoy_path.write_text(decoy, encoding="utf-8")
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        assert decoy_path.read_text(encoding="utf-8") == decoy
        require_relate_human_success(result, fields["source_id"], fields["target_id"], rel)
        print("named bundle was not overridden by cwd knowledge/", flush=True)


def test_named_path_without_root_index_relates_named_path_nested_files_unchanged():
    """Named path with no root index.md relates the named path; nested knowledge/ stays."""
    with workspace() as ws:
        fields = _same_fields()
        rel = unique_tokens("nkrel")[0]
        nested = _seed(ws, f"{rel}/knowledge", fields)
        named = ws.path / rel
        if path_is_file(named / "index.md"):
            (named / "index.md").unlink()
        assert not path_is_file(named / "index.md")
        assert path_is_dir(named / "knowledge")
        nested_source_before = read_bytes(concept_file(nested, fields["source_id"]))
        nested_target_before = read_bytes(concept_file(nested, fields["target_id"]))
        nested_log_before = read_bytes(nested / "log.md")
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        report = require_relate_success(result)
        assert_named_path_relate_landing(
            named,
            nested,
            fields["source_id"],
            fields["target_id"],
            generated_by="agent/cli",
            extra=fields["extra"],
            seed_generated_at=SEED_GENERATED_AT,
            seed_body_token=fields["source_body"],
            link_text=fields["target_title"],
            prose=fields["prose"],
            unused_prose=fields["unused_prose"],
            nested_source_before=nested_source_before,
            nested_target_before=nested_target_before,
            nested_log_before=nested_log_before,
            titles=_titles(fields),
            path_tokens=path_tokens_for(rel, named, ws.path),
        )
        require_relate_human_success(result, fields["source_id"], fields["target_id"], rel)
        print("cli named path related named root; nested unchanged", flush=True)


def test_mcp_omit_bundle_without_knowledge_dir_relates_cwd():
    """MCP omit bundle, no knowledge/ directory: rewrite lands at cwd."""
    with workspace() as ws:
        fields = _same_fields()
        root = _seed(ws, ".", fields)
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        assert not path_is_file(
            ws.path / "knowledge" / f"{fields['source_id']}.md"
        )
        print("mcp omit-bundle without knowledge/ related cwd", flush=True)


def test_mcp_omit_bundle_with_knowledge_dir_relates_knowledge_not_cwd():
    """MCP omit bundle with knowledge/ as a directory relates knowledge/, not a cwd decoy."""
    with workspace() as ws:
        fields = _same_fields("dk")
        decoy = fields["rest"][0]
        root = _seed(ws, "knowledge", fields)
        decoy_path = ws.path / f"{fields['source_id']}.md"
        decoy_path.parent.mkdir(parents=True, exist_ok=True)
        decoy_path.write_text(decoy, encoding="utf-8")
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for("knowledge", ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        assert decoy_path.read_text(encoding="utf-8") == decoy
        print("mcp omit-bundle with knowledge/ related knowledge not cwd", flush=True)


def test_mcp_named_bundle_is_not_overridden_by_cwd_knowledge():
    """MCP named bundle writes there even when cwd has a knowledge/ decoy."""
    with workspace() as ws:
        fields = _same_fields("dk")
        decoy = fields["rest"][0]
        rel = _bundle()
        root = _seed(ws, rel, fields)
        decoy_dir = ws.path / "knowledge"
        decoy_dir.mkdir()
        decoy_path = decoy_dir / f"{fields['source_id']}.md"
        decoy_path.parent.mkdir(parents=True, exist_ok=True)
        decoy_path.write_text(decoy, encoding="utf-8")
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        assert decoy_path.read_text(encoding="utf-8") == decoy
        require_mcp_relate_success_text(outcome, fields["source_id"], fields["target_id"], root)
        print("mcp named bundle ignored cwd knowledge decoy", flush=True)


def test_mcp_named_path_without_root_index_relates_named_path_nested_files_unchanged():
    """MCP named path with no root index.md relates the named path; nested knowledge/ stays."""
    with workspace() as ws:
        fields = _same_fields()
        rel = unique_tokens("mnkrel")[0]
        nested = _seed(ws, f"{rel}/knowledge", fields)
        named = ws.path / rel
        if path_is_file(named / "index.md"):
            (named / "index.md").unlink()
        assert not path_is_file(named / "index.md")
        nested_source_before = read_bytes(concept_file(nested, fields["source_id"]))
        nested_target_before = read_bytes(concept_file(nested, fields["target_id"]))
        nested_log_before = read_bytes(nested / "log.md")
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_success(outcome)
        assert_named_path_relate_landing(
            named,
            nested,
            fields["source_id"],
            fields["target_id"],
            generated_by="agent/mcp",
            extra=fields["extra"],
            seed_generated_at=SEED_GENERATED_AT,
            seed_body_token=fields["source_body"],
            link_text=fields["target_title"],
            prose=fields["prose"],
            unused_prose=fields["unused_prose"],
            nested_source_before=nested_source_before,
            nested_target_before=nested_target_before,
            nested_log_before=nested_log_before,
            titles=_titles(fields),
            path_tokens=path_tokens_for(rel, named, ws.path),
        )
        require_mcp_relate_success_text(outcome, fields["source_id"], fields["target_id"], named)
        print("mcp named path related named root; nested unchanged", flush=True)


# ---------------------------------------------------------------------------
# K. Invalid, reserved, and escaping identities
# ---------------------------------------------------------------------------


def test_empty_identity_as_source_or_target_fails_without_successful_relate():
    """Empty string as source or as target fails without a successful relate on CLI and MCP."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        for aimed_s, aimed_t in (("", fields["target_id"]), (fields["source_id"], "")):
            before_snap = snapshot_tree(ws.path)
            result = run_relate(
                ws, aimed_s, aimed_t, rel, description=fields["prose"]
            )
            require_relate_failure(result)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            assert read_bytes(concept_file(root, fields["source_id"])) == src_before
            assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
            outcome = mcp_membundle_relate(
                ws,
                {
                    "source_id": aimed_s,
                    "target_id": aimed_t,
                    "description": fields["prose"],
                    "bundle": rel,
                },
            )
            require_mcp_relate_non_success(outcome)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        _live_cli_relate(ws, rel)
        print("empty identity as source or target refused on CLI and MCP", flush=True)


def test_absolute_identity_as_source_or_target_fails_without_successful_relate():
    """An absolute-path identity as source or as target fails without a successful relate."""
    with workspace() as ws:
        fields = _same_fields("ab")
        leaf = fields["rest"][0]
        aimed = f"/{leaf}"
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        for aimed_s, aimed_t in (
            (aimed, fields["target_id"]),
            (fields["source_id"], aimed),
        ):
            before_snap = snapshot_tree(ws.path)
            result = run_relate(
                ws, aimed_s, aimed_t, rel, description=fields["prose"]
            )
            require_relate_failure(result)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            assert read_bytes(concept_file(root, fields["source_id"])) == src_before
            assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
            outcome = mcp_membundle_relate(
                ws,
                {
                    "source_id": aimed_s,
                    "target_id": aimed_t,
                    "description": fields["prose"],
                    "bundle": rel,
                },
            )
            require_mcp_relate_non_success(outcome)
        _live_cli_relate(ws, rel)
        print("absolute identity as source or target refused", flush=True)


def test_dotdot_identity_as_source_or_target_fails_and_does_not_write_outside_the_bundle():
    """../outside and foo/../outside as source or target fail; nothing is written outside."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        assert_snapshot_helper_sees_write(ws, unique_tokens("snap")[0])
        outside = ws.path / f"{_OUTSIDE_LEAF}.md"
        nested_outside = ws.path / _OUTSIDE_LEAF
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        for aimed in (f"../{_OUTSIDE_LEAF}", f"foo/../{_OUTSIDE_LEAF}"):
            for aimed_s, aimed_t in (
                (aimed, fields["target_id"]),
                (fields["source_id"], aimed),
            ):
                before_snap = snapshot_tree(ws.path)
                result = run_relate(
                    ws, aimed_s, aimed_t, rel, description=fields["prose"]
                )
                require_relate_failure(result)
                assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
                outcome = mcp_membundle_relate(
                    ws,
                    {
                        "source_id": aimed_s,
                        "target_id": aimed_t,
                        "description": fields["prose"],
                        "bundle": rel,
                    },
                )
                require_mcp_relate_non_success(outcome)
                assert read_bytes(concept_file(root, fields["source_id"])) == src_before
                assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
        assert not outside.exists(), "relate of ../outside wrote a file outside the bundle"
        assert not nested_outside.exists()
        _live_cli_relate(ws, rel)
        print("dotdot identities did not write outside the bundle", flush=True)


def test_leading_hyphen_identity_as_source_or_target_fails_without_successful_relate():
    """A leading-hyphen identity as source or as target fails without a successful relate."""
    with workspace() as ws:
        fields = _same_fields("hy")
        aimed = f"-{fields['rest'][0]}"
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        for aimed_s, aimed_t in (
            (aimed, fields["target_id"]),
            (fields["source_id"], aimed),
        ):
            before_snap = snapshot_tree(ws.path)
            result = run_relate(
                ws, aimed_s, aimed_t, rel, description=fields["prose"]
            )
            require_relate_failure(result)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            assert read_bytes(concept_file(root, fields["source_id"])) == src_before
            assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
            outcome = mcp_membundle_relate(
                ws,
                {
                    "source_id": aimed_s,
                    "target_id": aimed_t,
                    "description": fields["prose"],
                    "bundle": rel,
                },
            )
            require_mcp_relate_non_success(outcome)
        _live_cli_relate(ws, rel)
        print("leading-hyphen identity as source or target refused", flush=True)


def test_cli_newline_cr_and_tab_identities_each_fail_without_successful_relate():
    """CLI newline, CR, and tab identities each fail as source and as target."""
    with workspace() as ws:
        fields = _same_fields("cl", "cr")
        left, right = fields["rest"][:2]
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        for aimed in (f"{left}\n{right}", f"{left}\r{right}", f"{left}\t{right}"):
            for aimed_s, aimed_t in (
                (aimed, fields["target_id"]),
                (fields["source_id"], aimed),
            ):
                before_snap = snapshot_tree(ws.path)
                result = run_relate(
                    ws, aimed_s, aimed_t, rel, description=fields["prose"]
                )
                require_relate_failure(result)
                assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
                assert read_bytes(concept_file(root, fields["source_id"])) == src_before
                assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
        _live_cli_relate(ws, rel)
        print("cli control-character identities refused as source and as target", flush=True)


def test_mcp_newline_cr_and_tab_identities_each_are_non_success_and_write_nothing():
    """MCP newline, CR, and tab identities as source or target are non-success and write nothing."""
    with workspace() as ws:
        fields = _same_fields("ml", "mr")
        left, right = fields["rest"][:2]
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        request_id = 40
        for aimed in (f"{left}\n{right}", f"{left}\r{right}", f"{left}\t{right}"):
            for aimed_s, aimed_t in (
                (aimed, fields["target_id"]),
                (fields["source_id"], aimed),
            ):
                before_snap = snapshot_tree(ws.path)
                outcome = mcp_membundle_relate(
                    ws,
                    {
                        "source_id": aimed_s,
                        "target_id": aimed_t,
                        "description": fields["prose"],
                        "bundle": rel,
                    },
                    request_id=request_id,
                )
                request_id += 1
                require_mcp_relate_non_success(outcome)
                assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
                assert read_bytes(concept_file(root, fields["source_id"])) == src_before
                assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
        _live_mcp_relate(ws, rel)
        print("mcp newline/cr/tab identities refused; well-formed pair related", flush=True)


def test_mcp_nul_identity_as_source_or_target_is_tool_error_and_writes_nothing():
    """MCP null-byte identity as source_id or target_id is a tool error and writes nothing."""
    with workspace() as ws:
        fields = _same_fields("nl", "nr")
        left, right = fields["rest"][:2]
        aimed = f"{left}\x00{right}"
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        for request_id, aimed_s, aimed_t in (
            (60, aimed, fields["target_id"]),
            (61, fields["source_id"], aimed),
        ):
            before_snap = snapshot_tree(ws.path)
            outcome = mcp_membundle_relate(
                ws,
                {
                    "source_id": aimed_s,
                    "target_id": aimed_t,
                    "description": fields["prose"],
                    "bundle": rel,
                },
                request_id=request_id,
            )
            require_mcp_relate_tool_error(outcome)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            assert read_bytes(concept_file(root, fields["source_id"])) == src_before
            assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
        _live_mcp_relate(ws, rel)
        print("mcp nul identity as source or target is a tool error", flush=True)


def test_reserved_index_nested_index_root_log_and_root_agents_fail_without_successful_relate():
    """Reserved index, nested index, root log, and root AGENTS fail as source or target."""
    with workspace() as ws:
        fields = _same_fields("rs")
        nest = fields["rest"][0]
        rel = _bundle()
        root = _seed(ws, rel, fields, agents="# agents seed\n")
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
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        for aimed in ("index", f"{nest}/index", "log", "AGENTS"):
            for aimed_s, aimed_t in (
                (aimed, fields["target_id"]),
                (fields["source_id"], aimed),
            ):
                before_snap = snapshot_tree(ws.path)
                result = run_relate(
                    ws, aimed_s, aimed_t, rel, description=fields["prose"]
                )
                require_relate_failure(result)
                assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
                assert read_bytes(concept_file(root, fields["source_id"])) == src_before
                assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
        for key, path in reserved_paths.items():
            assert read_bytes(path) == before_bytes[key], (
                f"reserved file {key} changed after a refusing relate"
            )
        _live_cli_relate(ws, rel)
        print("reserved identities refused; reserved files unchanged", flush=True)


def test_mcp_reserved_index_nested_index_root_log_and_root_agents_are_non_success_and_write_nothing():
    """MCP reserved index / nested index / root log / root AGENTS are non-success."""
    with workspace() as ws:
        fields = _same_fields("mr")
        nest = fields["rest"][0]
        rel = _bundle()
        root = _seed(ws, rel, fields, agents="# agents seed\n")
        nested_index = root / nest / "index.md"
        nested_index.parent.mkdir(parents=True, exist_ok=True)
        nested_index.write_text("# nested\n", encoding="utf-8")
        reserved_paths = [root / "index.md", root / "log.md", root / "AGENTS.md", nested_index]
        before_bytes = [read_bytes(path) for path in reserved_paths]
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        request_id = 50
        for aimed in ("index", f"{nest}/index", "log", "AGENTS"):
            for aimed_s, aimed_t in (
                (aimed, fields["target_id"]),
                (fields["source_id"], aimed),
            ):
                before_snap = snapshot_tree(ws.path)
                outcome = mcp_membundle_relate(
                    ws,
                    {
                        "source_id": aimed_s,
                        "target_id": aimed_t,
                        "description": fields["prose"],
                        "bundle": rel,
                    },
                    request_id=request_id,
                )
                request_id += 1
                require_mcp_relate_non_success(outcome)
                assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
                assert read_bytes(concept_file(root, fields["source_id"])) == src_before
        for path, payload in zip(reserved_paths, before_bytes):
            assert read_bytes(path) == payload
        _live_mcp_relate(ws, rel)
        print("mcp reserved identities refused", flush=True)


def test_nested_log_is_missing_and_nested_agents_is_relatable():
    """Nested log.md is missing-class; nested AGENTS.md is relatable as source and as target."""
    with workspace() as ws:
        fields = _same_fields("nld", "nla", "nlt")
        nest, agents_leaf_unused, note_leaf = fields["rest"][:3]
        log_ident = f"{nest}/log"
        agents_ident = f"{nest}/AGENTS"
        rel = _bundle()
        root = _seed(ws, rel, fields, agents="# agents seed\n")
        write_relatable_concept(
            root,
            log_ident,
            concept_type=fields["source_type"],
            title=fields["source_title"],
            body=unique_tokens("nlb")[0],
        )
        write_relatable_concept(
            root,
            agents_ident,
            concept_type=fields["target_type"],
            title=unique_tokens("natl")[0],
            body=unique_tokens("nabd")[0],
            extra=fields["extra"],
        )
        log_path = concept_file(root, log_ident)
        agents_path = concept_file(root, agents_ident)
        assert concept_filename(log_ident) == "log.md"
        assert concept_filename(agents_ident) == "AGENTS.md"
        log_before = read_bytes(log_path)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        for aimed_s, aimed_t in (
            (log_ident, fields["target_id"]),
            (fields["source_id"], log_ident),
        ):
            result = run_relate(
                ws, aimed_s, aimed_t, rel, description=fields["prose"]
            )
            require_relate_failure(result)
            assert read_bytes(log_path) == log_before
            assert read_bytes(concept_file(root, fields["source_id"])) == src_before
            assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
        agents_as_source = _same_fields("nas")
        agents_as_source["source_id"] = agents_ident
        agents_as_source["source_title"] = unique_tokens("nast")[0]
        write_relatable_concept(
            root,
            agents_ident,
            concept_type=agents_as_source["source_type"],
            title=agents_as_source["source_title"],
            body=agents_as_source["source_body"],
            extra=agents_as_source["extra"],
        )
        result = run_relate(
            ws,
            agents_ident,
            fields["target_id"],
            rel,
            description=agents_as_source["prose"],
        )
        require_relate_success(result)
        agents_as_source["target_id"] = fields["target_id"]
        agents_as_source["target_title"] = fields["target_title"]
        assert_relative_link_to_target(
            agents_path,
            agents_ident,
            fields["target_id"],
            link_text=fields["target_title"],
            href_mode="resolve",
        )
        twin_source = _same_fields("nat")
        write_relatable_concept(
            root,
            twin_source["source_id"],
            concept_type=twin_source["source_type"],
            title=twin_source["source_title"],
            body=twin_source["source_body"],
            extra=twin_source["extra"],
        )
        result = run_relate(
            ws,
            twin_source["source_id"],
            agents_ident,
            rel,
            description=twin_source["prose"],
        )
        require_relate_success(result)
        twin_source["target_id"] = agents_ident
        twin_source["target_title"] = agents_as_source["source_title"]
        assert_relative_link_to_target(
            concept_file(root, twin_source["source_id"]),
            twin_source["source_id"],
            agents_ident,
            link_text=agents_as_source["source_title"],
            href_mode="resolve",
        )
        log_bytes = read_bytes(root / "log.md")
        agents_root = read_bytes(root / "AGENTS.md")
        require_relate_failure(
            run_relate(ws, "log", fields["target_id"], rel, description=fields["prose"])
        )
        require_relate_failure(
            run_relate(
                ws, fields["source_id"], "AGENTS", rel, description=fields["prose"]
            )
        )
        assert read_bytes(root / "log.md") == log_bytes
        assert read_bytes(root / "AGENTS.md") == agents_root
        print("nested log.md is missing; nested AGENTS.md is relatable", flush=True)


def test_mcp_nested_log_is_missing_and_nested_agents_is_relatable():
    """MCP nested log.md is missing-class; nested AGENTS.md is relatable as source and as target."""
    with workspace() as ws:
        fields = _same_fields("mld")
        nest = fields["rest"][0]
        log_ident = f"{nest}/log"
        agents_ident = f"{nest}/AGENTS"
        rel = _bundle()
        root = _seed(ws, rel, fields, agents="# agents seed\n")
        write_relatable_concept(
            root,
            log_ident,
            concept_type=fields["source_type"],
            title=fields["source_title"],
            body=unique_tokens("mlb")[0],
        )
        agents_title = unique_tokens("mnat")[0]
        write_relatable_concept(
            root,
            agents_ident,
            concept_type=fields["target_type"],
            title=agents_title,
            body=unique_tokens("mnab")[0],
            extra=fields["extra"],
        )
        log_before = read_bytes(concept_file(root, log_ident))
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        for aimed_s, aimed_t, request_id in (
            (log_ident, fields["target_id"], 70),
            (fields["source_id"], log_ident, 71),
        ):
            outcome = mcp_membundle_relate(
                ws,
                {
                    "source_id": aimed_s,
                    "target_id": aimed_t,
                    "description": fields["prose"],
                    "bundle": rel,
                },
                request_id=request_id,
            )
            require_mcp_relate_non_success(outcome)
            assert read_bytes(concept_file(root, log_ident)) == log_before
            assert read_bytes(concept_file(root, fields["source_id"])) == src_before
        as_source = mcp_relate(
            ws,
            agents_ident,
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
            request_id=72,
        )
        require_mcp_relate_success(as_source)
        assert_relative_link_to_target(
            concept_file(root, agents_ident),
            agents_ident,
            fields["target_id"],
            link_text=fields["target_title"],
            href_mode="resolve",
        )
        twin = _same_fields("mnt")
        write_relatable_concept(
            root,
            twin["source_id"],
            concept_type=twin["source_type"],
            title=twin["source_title"],
            body=twin["source_body"],
            extra=twin["extra"],
        )
        as_target = mcp_relate(
            ws,
            twin["source_id"],
            agents_ident,
            description=twin["prose"],
            bundle=rel,
            request_id=73,
        )
        require_mcp_relate_success(as_target)
        assert_relative_link_to_target(
            concept_file(root, twin["source_id"]),
            twin["source_id"],
            agents_ident,
            link_text=agents_title,
            href_mode="resolve",
        )
        print("mcp nested log.md is missing; nested AGENTS.md is relatable", flush=True)


def test_mcp_dotdot_absolute_empty_and_leading_hyphen_are_non_success_and_write_nothing():
    """MCP ../outside, absolute, empty, and leading-hyphen identities are non-success."""
    with workspace() as ws:
        fields = _same_fields("ab", "hy")
        leaf, hyphen_leaf = fields["rest"][:2]
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        request_id = 80
        for aimed in (f"../{_OUTSIDE_LEAF}", f"/{leaf}", "", f"-{hyphen_leaf}"):
            for aimed_s, aimed_t in (
                (aimed, fields["target_id"]),
                (fields["source_id"], aimed),
            ):
                before_snap = snapshot_tree(ws.path)
                outcome = mcp_membundle_relate(
                    ws,
                    {
                        "source_id": aimed_s,
                        "target_id": aimed_t,
                        "description": fields["prose"],
                        "bundle": rel,
                    },
                    request_id=request_id,
                )
                request_id += 1
                require_mcp_relate_non_success(outcome)
                assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
                assert read_bytes(concept_file(root, fields["source_id"])) == src_before
        _live_mcp_relate(ws, rel)
        print("mcp invalid-identity set refused", flush=True)


def test_cli_escaping_symlink_write_is_refused():
    """CLI write through a .md symlink whose target leaves the bundle is refused."""
    with workspace() as ws:
        fields = _same_fields("sc")
        secret_leaf = fields["rest"][0]
        rel = _bundle()
        root = _seed(ws, rel, fields)
        _live_cli_relate(ws, rel)
        secret = ws.write(f"{secret_leaf}.md", b"outside-secret\n")
        secret_bytes = secret.read_bytes()
        link_ident = unique_tokens("syid")[0]
        dest = concept_file(root, link_ident)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(secret, dest)
        assert_snapshot_helper_sees_write(ws, unique_tokens("syc")[0])
        before_snap = snapshot_tree(ws.path)
        result = run_relate(
            ws, link_ident, fields["target_id"], rel, description=fields["prose"]
        )
        require_relate_failure(result)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        assert secret.read_bytes() == secret_bytes
        assert dest.is_symlink() or not dest.exists(), (
            "refusing relate replaced the escaping symlink with a regular concept file"
        )
        print("cli escaping symlink write refused; outside target unchanged", flush=True)


def test_mcp_escaping_symlink_write_is_refused():
    """MCP write through a .md symlink whose target leaves the bundle is refused."""
    with workspace() as ws:
        fields = _same_fields("msc")
        secret_leaf = fields["rest"][0]
        rel = _bundle()
        root = _seed(ws, rel, fields)
        _live_mcp_relate(ws, rel)
        secret = ws.write(f"{secret_leaf}.md", b"outside-secret\n")
        secret_bytes = secret.read_bytes()
        link_ident = unique_tokens("msyid")[0]
        dest = concept_file(root, link_ident)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(secret, dest)
        before_snap = snapshot_tree(ws.path)
        outcome = mcp_relate(
            ws,
            link_ident,
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_non_success(outcome)
        assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
        assert secret.read_bytes() == secret_bytes
        print("mcp escaping symlink write refused; outside target unchanged", flush=True)


# ---------------------------------------------------------------------------
# L. Fewer than two identities; MCP missing source or target key
# ---------------------------------------------------------------------------


def test_fewer_than_two_identities_is_non_success_usage_and_does_not_write():
    """membundle relate with zero or one identity is usage-class, unlike empty/reserved/self/missing/success."""
    with workspace() as ws:
        fields = _same_fields("nf")
        missing_id = fields["rest"][0]
        rel = _bundle()
        cwd_fields = _same_fields("cwd")
        cwd_root = _seed(ws, ".", cwd_fields)
        root = _seed(ws, rel, fields)
        paths = path_tokens_for(rel, ws.path)
        success = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        success_report = require_relate_success(success)
        require_relate_human_success(
            success, fields["source_id"], fields["target_id"], rel
        )
        empty = run_relate(ws, "", fields["target_id"], rel, description=fields["prose"])
        require_relate_failure(empty)
        require_relate_error_line(empty)
        reserved = run_relate(
            ws, "index", fields["target_id"], rel, description=fields["prose"]
        )
        require_relate_failure(reserved)
        require_relate_error_line(reserved)
        self_rel = run_relate(
            ws,
            fields["source_id"],
            fields["source_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_failure(self_rel)
        require_relate_error_line(self_rel)
        missing = run_relate(
            ws, fields["source_id"], missing_id, rel, description=fields["prose"]
        )
        require_relate_failure(missing)
        require_relate_endpoint_not_found(
            missing, endpoint="target", identity=missing_id
        )
        empty_report = combined_report(empty)
        reserved_report = combined_report(reserved)
        self_report = combined_report(self_rel)
        missing_report = combined_report(missing)
        cwd_before = read_bytes(concept_file(cwd_root, cwd_fields["source_id"]))
        for extra_args in ((), (cwd_fields["source_id"],)):
            before_snap = snapshot_tree(ws.path)
            result = run_relate(
                ws,
                extra_args[0] if extra_args else None,
                None,
            )
            require_relate_failure(result)
            require_relate_usage_failure(
                result,
                empty_report,
                reserved_report,
                self_report,
                missing_report,
                success_report,
                paths,
            )
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=".")
            assert read_bytes(concept_file(cwd_root, cwd_fields["source_id"])) == cwd_before
        print("fewer than two identities is usage-class and did not write", flush=True)


def test_mcp_missing_source_or_target_key_is_tool_error_and_writes_no_link():
    """MCP relate missing source_id, target_id, or both is a tool error and writes no link."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        for request_id, arguments in (
            (90, {"target_id": fields["target_id"], "bundle": rel}),
            (91, {"source_id": fields["source_id"], "bundle": rel}),
            (92, {"bundle": rel}),
        ):
            before_snap = snapshot_tree(ws.path)
            outcome = mcp_membundle_relate(ws, arguments, request_id=request_id)
            require_mcp_relate_tool_error(outcome)
            assert_no_new_concept_file(ws.path, before_snap, bundle_rel=rel)
            assert read_bytes(concept_file(root, fields["source_id"])) == src_before
            assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
        _live_mcp_relate(ws, rel)
        print("mcp missing source or target key is a tool error", flush=True)


# ---------------------------------------------------------------------------
# M. Self-relate and missing source or target
# ---------------------------------------------------------------------------


def test_cli_self_relate_fails_without_writing():
    """CLI relate of a present concept to itself does not succeed and does not write."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        result = run_relate(
            ws,
            fields["source_id"],
            fields["source_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_failure(result)
        assert_no_successful_relate(
            root,
            fields["source_id"],
            fields["source_id"],
            seed_body_token=fields["source_body"],
            target_before=src_before,
            path_tokens=path_tokens_for(rel, ws.path),
            source_title=fields["source_title"],
        )
        assert read_bytes(concept_file(root, fields["source_id"])) == src_before
        live = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(live)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("cli self-relate failed without writing; live pair related", flush=True)


def test_mcp_self_relate_is_non_success_and_does_not_write():
    """MCP self-relate of a present concept is non-success and does not write."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        outcome = mcp_relate(
            ws,
            fields["source_id"],
            fields["source_id"],
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_non_success(outcome)
        assert_no_successful_relate(
            root,
            fields["source_id"],
            fields["source_id"],
            seed_body_token=fields["source_body"],
            target_before=src_before,
            path_tokens=path_tokens_for(rel, ws.path),
            source_title=fields["source_title"],
        )
        live = mcp_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
            request_id=11,
        )
        require_mcp_relate_success(live)
        _assert_writing(
            root,
            fields,
            generated_by="agent/mcp",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("mcp self-relate is non-success and did not write", flush=True)


def test_cli_missing_source_or_missing_target_fails_without_writing():
    """CLI missing source or missing target fails without writing or creating a file."""
    with workspace() as ws:
        fields = _same_fields("ms", "mt")
        missing_source, missing_target = fields["rest"][:2]
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        missing_tgt = run_relate(
            ws,
            fields["source_id"],
            missing_target,
            rel,
            description=fields["prose"],
        )
        require_relate_failure(missing_tgt)
        assert_no_successful_relate(
            root,
            fields["source_id"],
            missing_target,
            seed_body_token=fields["source_body"],
            target_before=tgt_before,
            path_tokens=path_tokens_for(rel, ws.path),
            source_title=fields["source_title"],
        )
        assert read_bytes(concept_file(root, fields["source_id"])) == src_before
        assert not path_is_file(concept_file(root, missing_target))
        missing_src = run_relate(
            ws,
            missing_source,
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_failure(missing_src)
        assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
        assert not path_is_file(concept_file(root, missing_source))
        print("cli missing source or missing target failed without writing", flush=True)


def test_mcp_missing_source_or_missing_target_is_non_success_and_does_not_write():
    """MCP missing source or missing target is non-success and writes nothing."""
    with workspace() as ws:
        fields = _same_fields("mms", "mmt")
        missing_source, missing_target = fields["rest"][:2]
        rel = _bundle()
        root = _seed(ws, rel, fields)
        src_before = read_bytes(concept_file(root, fields["source_id"]))
        tgt_before = read_bytes(concept_file(root, fields["target_id"]))
        missing_tgt = mcp_relate(
            ws,
            fields["source_id"],
            missing_target,
            description=fields["prose"],
            bundle=rel,
        )
        require_mcp_relate_non_success(missing_tgt)
        assert_no_successful_relate(
            root,
            fields["source_id"],
            missing_target,
            seed_body_token=fields["source_body"],
            path_tokens=path_tokens_for(rel, ws.path),
            source_title=fields["source_title"],
        )
        assert read_bytes(concept_file(root, fields["source_id"])) == src_before
        missing_src = mcp_relate(
            ws,
            missing_source,
            fields["target_id"],
            description=fields["prose"],
            bundle=rel,
            request_id=11,
        )
        require_mcp_relate_non_success(missing_src)
        assert read_bytes(concept_file(root, fields["target_id"])) == tgt_before
        assert not path_is_file(concept_file(root, missing_source))
        print("mcp missing source or missing target is non-success", flush=True)


# ---------------------------------------------------------------------------
# N. Structured CLI still writes; human mode still writes
# ---------------------------------------------------------------------------


def test_structured_cli_still_writes_source_link_and_log():
    """Structured CLI success still writes the source link, log Update, and generated.by agent/cli."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
            structured=True,
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("structured cli still wrote the source link and log", flush=True)


def test_structured_cli_supplied_actor_is_written_as_generated_by():
    """Structured CLI with a supplied actor writes that actor as generated.by."""
    with workspace() as ws:
        fields = _same_fields("jsa", "jsb")
        left, right = fields["rest"]
        actor = f"{left}/{right}"
        rel = _bundle()
        root = _seed(ws, rel, fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
            actor=actor,
            structured=True,
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by=actor,
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("structured cli supplied actor was written as generated.by", flush=True)


def test_structured_cli_empty_and_whitespace_actor_each_write_agent_membundle_tool():
    """Structured CLI empty and whitespace actor each write generated.by agent/membundle-tool."""
    with workspace() as ws:
        for actor in ("", "   "):
            fields = _same_fields("jact")
            rel = _bundle()
            root = _seed(ws, rel, fields)
            result = run_relate(
                ws,
                fields["source_id"],
                fields["target_id"],
                rel,
                description=fields["prose"],
                actor=actor,
                structured=True,
            )
            require_relate_success(result)
            _assert_writing(
                root,
                fields,
                generated_by="agent/membundle-tool",
                path_tokens=path_tokens_for(rel, ws.path),
                href_mode="named",
                prose=fields["prose"],
                new_heading=True,
            )
        print("structured cli empty and whitespace actor each wrote agent/membundle-tool", flush=True)


def test_human_mode_still_writes_source_link_and_log():
    """Default human mode on a twin still writes the source link, log Update, and agent/cli."""
    with workspace() as ws:
        fields = _same_fields()
        rel = _bundle()
        root = _seed(ws, rel, fields)
        result = run_relate(
            ws,
            fields["source_id"],
            fields["target_id"],
            rel,
            description=fields["prose"],
        )
        require_relate_success(result)
        _assert_writing(
            root,
            fields,
            generated_by="agent/cli",
            path_tokens=path_tokens_for(rel, ws.path),
            href_mode="named",
            prose=fields["prose"],
            new_heading=True,
        )
        print("human mode still wrote the source link and log", flush=True)
