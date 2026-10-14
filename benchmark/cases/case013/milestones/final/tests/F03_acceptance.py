# feature: F03
"""Acceptance tests for inspecting a concept (FP-03).

Public entries: the ``membundle show`` command and the ``membundle_show`` Model
Context Protocol tool. Observations go through the sealed harness
``workspace`` / ``invoke`` / ``mcp_batch`` path and the on-disk files
the tests wrote. These tests do not import Go packages, do not call
internal Show / LoadBundle helpers, and do not use ``membundle validate`` /
``membundle create`` / ``membundle search`` to judge results.
"""

from __future__ import annotations

import os
from _harness import workspace
from F03_helpers import (
    assert_human_presents,
    assert_snapshot_helper_sees_write,
    concept_body_from_file,
    concept_file_bytes,
    concept_spec,
    ignore_list_fixture,
    markdown_link,
    mcp_first_text,
    mcp_is_invalid_params,
    mcp_is_protocol_error,
    mcp_is_success_record,
    mcp_is_tool_error,
    mcp_membundle_show,
    structured_stdout_is_success_record,
    mcp_show,
    path_tokens_for,
    show_record_field,
    reject_identity_on_all_show_modes,
    render_concept_markdown,
    require_load_error,
    require_mcp_not_found,
    require_mcp_required_identity_non_success,
    require_mcp_success_record,
    require_mcp_tool_level_failure,
    require_not_found,
    require_not_successful_inspection,
    require_record_has_identity_type_body,
    require_show_raw_success,
    require_show_structured_success,
    require_human_show,
    require_usage_failure,
    resolve_show_binary,
    run_show,
    snapshot_tree,
    unselected_token_absent,
    unique_tokens,
    write_bundle,
)


# ---------------------------------------------------------------------------
# A. Human show presents identity, type, title, description, and body
# ---------------------------------------------------------------------------


def test_human_show_reports_identity_type_title_description_and_body():
    """Named-bundle human show presents field values, not a filename list."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "id", "typ", "ttl", "dsc", "bod"
        )
        nested = f"architecture/{ident}"
        body = f"{token}\n\nNested body token only after frontmatter.\n"
        rel = unique_tokens("kb")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    nested,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                )
            ],
        )
        result = run_show(ws, nested, rel)
        report = require_human_show(result)
        assert_human_presents(
            report,
            identity=nested,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )
        print(f"human nested identity={nested!r} presented", flush=True)


def test_human_show_generated_nested_identity_and_runtime_twin():
    """A generated nested identity is not the only one that shows."""
    with workspace() as ws:
        typ, title, desc, token, sdir, sleaf = unique_tokens(
            "ptyp", "pttl", "pdsc", "pbod", "psdir", "psleaf"
        )
        sample_id = f"{sdir}/{sleaf}"
        body = f"{token}\n"
        rel = unique_tokens("kbs")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    sample_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                )
            ],
        )
        sample = require_human_show(run_show(ws, sample_id, rel))
        assert_human_presents(
            sample,
            identity=sample_id,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )

        twin_id, ttyp, ttitle, tdesc, ttoken = unique_tokens(
            "twin", "ttyp", "tttl", "tdsc", "tbod"
        )
        rel2 = unique_tokens("kbt")[0]
        write_bundle(
            ws,
            rel2,
            [
                concept_spec(
                    twin_id,
                    concept_type=ttyp,
                    title=ttitle,
                    description=tdesc,
                    body=f"{ttoken}\n",
                )
            ],
        )
        twin = require_human_show(run_show(ws, twin_id, rel2))
        assert_human_presents(
            twin,
            identity=twin_id,
            concept_type=ttyp,
            title=ttitle,
            description=tdesc,
            body_token=ttoken,
        )
        unselected_token_absent(twin, token)
        unselected_token_absent(sample, ttoken)
        print(f"public-sample twin identity={twin_id!r}", flush=True)


# ---------------------------------------------------------------------------
# B. Tags if any; generated provenance if present
# ---------------------------------------------------------------------------


def test_human_show_presents_tags_only_when_present():
    """Tagged vs untagged concepts differ only by that tag token."""
    with workspace() as ws:
        tagged_id, plain_id, typ, title, desc, token, tag = unique_tokens(
            "tid", "pid", "typ", "ttl", "dsc", "bod", "tag"
        )
        body = f"{token}\n"
        rel = unique_tokens("kbtag")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    tagged_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                    tags=(tag,),
                ),
                concept_spec(
                    plain_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                ),
            ],
        )
        tagged = require_human_show(run_show(ws, tagged_id, rel))
        plain = require_human_show(run_show(ws, plain_id, rel))
        print(f"tag token={tag!r} tagged={tagged.fields!r} plain={plain.fields!r}", flush=True)
        assert tagged.value("Tags").split(", ") == [tag], (
            f"tagged show Tags: line is not {tag!r}: {tagged.fields!r}"
        )
        assert "Tags" not in plain.fields, (
            f"untagged show has a Tags: line: {plain.fields!r}"
        )
        unselected_token_absent(plain, tag)


def test_human_show_presents_generated_provenance_only_when_present():
    """Generated vs omitted provenance differ only by actor/timestamp."""
    with workspace() as ws:
        gen_id, plain_id, typ, title, desc, token, actor_leaf = unique_tokens(
            "gid", "nid", "typ", "ttl", "dsc", "bod", "act"
        )
        actor = f"agent/{actor_leaf}"
        stamped = "2026-04-01T08:09:10Z"
        body = f"{token}\n"
        rel = unique_tokens("kbgen")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    gen_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                    generated={"by": actor, "at": stamped},
                ),
                concept_spec(
                    plain_id,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                ),
            ],
        )
        generated = require_human_show(run_show(ws, gen_id, rel))
        plain = require_human_show(run_show(ws, plain_id, rel))
        print(
            f"actor={actor!r} generated={generated.fields!r} plain={plain.fields!r}",
            flush=True,
        )
        assert generated.value("Generated") == f"{stamped} by {actor}", (
            "generated show Generated: line is not '<at> by <by>' for "
            f"{stamped!r}/{actor!r}: {generated.fields!r}"
        )
        assert "Generated" not in plain.fields, (
            f"ungenerated show has a Generated: line: {plain.fields!r}"
        )
        unselected_token_absent(plain, actor)
        unselected_token_absent(plain, stamped)


# ---------------------------------------------------------------------------
# C. Trailing .md is stripped for resolution
# ---------------------------------------------------------------------------


def test_trailing_md_resolves_to_the_same_human_identity():
    """Shown identity is the stripped spelling, not an argv .md prefix."""
    with workspace() as ws:
        leaf, typ, title, desc, token = unique_tokens(
            "leaf", "typ", "ttl", "dsc", "bod"
        )
        ident = f"architecture/{leaf}"
        body = f"{token}\nno suffix in this fixture body\n"
        assert ".md" not in typ and ".md" not in title
        assert ".md" not in desc and ".md" not in body
        rel = unique_tokens("kbmd")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                )
            ],
        )
        stripped = require_human_show(run_show(ws, ident, rel))
        trailing = require_human_show(run_show(ws, f"{ident}.md", rel))
        assert_human_presents(
            stripped,
            identity=ident,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )
        assert_human_presents(
            trailing,
            identity=ident,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )
        print(f"trailing-.md ID={trailing.value('ID')!r}", flush=True)
        assert trailing.value("ID") == ident, (
            "trailing-.md show ID: is not the stripped identity "
            f"{ident!r}: {trailing.value('ID')!r}"
        )


def test_trailing_md_resolves_to_the_same_structured_identity():
    """Structured identity value is the stripped spelling."""
    with workspace() as ws:
        leaf, typ, title, desc, token = unique_tokens(
            "sleaf", "styp", "sttl", "sdsc", "sbod"
        )
        ident = f"architecture/{leaf}"
        body = f"{token}\nstructured body without suffix\n"
        assert ".md" not in body and ".md" not in typ
        rel = unique_tokens("kbsmd")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                )
            ],
        )
        file_body = concept_body_from_file(ws.resolve(rel) / f"{ident}.md")
        for shown in (ident, f"{ident}.md"):
            record = require_show_structured_success(
                run_show(ws, shown, rel, structured=True)
            )
            require_record_has_identity_type_body(record, ident, typ, file_body)
            print(f"structured shown={shown!r} identity value ok", flush=True)


# ---------------------------------------------------------------------------
# D. Inbound and outbound from Markdown links
# ---------------------------------------------------------------------------


def test_source_reports_outbound_target_identity():
    """Show of a source that links to Q reports Q's resolved identity."""
    with workspace() as ws:
        p_leaf, q_leaf, ptyp, qtyp, pttl, qttl, pdsc, qdsc, ptok, qtok = unique_tokens(
            "psrc", "qtgt", "ptyp", "qtyp", "pttl", "qttl", "pdsc", "qdsc", "pbod", "qbod"
        )
        p_id = f"architecture/{p_leaf}"
        q_id = f"architecture/{q_leaf}"
        p_body = f"{ptok}\n\nSee {markdown_link(q_leaf, f'{q_leaf}.md')}.\n"
        q_body = f"{qtok}\n\nNo backlink.\n"
        rel = unique_tokens("kbo")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(p_id, concept_type=ptyp, title=pttl, description=pdsc, body=p_body),
                concept_spec(q_id, concept_type=qtyp, title=qttl, description=qdsc, body=q_body),
            ],
        )
        source = require_human_show(run_show(ws, p_id, rel))
        print(f"source outbound={source.id_list('Outbound')!r}", flush=True)
        assert q_id in source.id_list("Outbound"), (
            f"show of source {p_id!r} does not report outbound identity "
            f"{q_id!r}: {source!r}"
        )


def test_target_reports_inbound_source_identity():
    """Show of the target reports the source identity as inbound."""
    with workspace() as ws:
        p_leaf, q_leaf, ptyp, qtyp, pttl, qttl, pdsc, qdsc, ptok, qtok = unique_tokens(
            "pin", "qin", "ptyp", "qtyp", "pttl", "qttl", "pdsc", "qdsc", "pbod", "qbod"
        )
        p_id = f"architecture/{p_leaf}"
        q_id = f"architecture/{q_leaf}"
        p_body = f"{ptok}\n\nSee {markdown_link(q_leaf, f'{q_leaf}.md')}.\n"
        q_body = f"{qtok}\n\nNo backlink.\n"
        rel = unique_tokens("kbi")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(p_id, concept_type=ptyp, title=pttl, description=pdsc, body=p_body),
                concept_spec(q_id, concept_type=qtyp, title=qttl, description=qdsc, body=q_body),
            ],
        )
        target = require_human_show(run_show(ws, q_id, rel))
        print(f"target inbound={target.id_list('Inbound')!r}", flush=True)
        assert p_id in target.id_list("Inbound"), (
            f"show of target {q_id!r} does not report inbound identity "
            f"{p_id!r}: {target!r}"
        )


def test_inbound_and_outbound_remainders_differ_when_only_link_direction_changes():
    """Hold shown P fixed; only P→Q vs Q→P changes; remainders still differ."""
    with workspace() as ws:
        (
            p_leaf,
            q_leaf,
            z_leaf,
            ptyp,
            qtyp,
            ztyp,
            pttl,
            qttl,
            zttl,
            pdsc,
            qdsc,
            zdsc,
            ptok,
            qtok,
            ztok,
        ) = unique_tokens(
            "pdir",
            "qdir",
            "zdir",
            "ptyp",
            "qtyp",
            "ztyp",
            "pttl",
            "qttl",
            "zttl",
            "pdsc",
            "qdsc",
            "zdsc",
            "pbod",
            "qbod",
            "zbod",
        )
        p_id = f"architecture/{p_leaf}"
        q_id = f"architecture/{q_leaf}"
        z_id = f"architecture/{z_leaf}"
        z_body = f"{ztok}\n"
        p_out = (
            f"{ptok}\n\n"
            f"{markdown_link(q_leaf, f'{q_leaf}.md')} {markdown_link(z_leaf, f'{z_leaf}.md')}\n"
        )
        p_in = f"{ptok}\n\n{markdown_link(z_leaf, f'{z_leaf}.md')}\n"
        q_plain = f"{qtok}\n\nNo backlink.\n"
        q_to_p = f"{qtok}\n\n{markdown_link(p_leaf, f'{p_leaf}.md')}\n"
        rel_out = unique_tokens("kbout")[0]
        rel_in = unique_tokens("kbin")[0]
        common_q = dict(concept_type=qtyp, title=qttl, description=qdsc)
        common_p = dict(concept_type=ptyp, title=pttl, description=pdsc)
        common_z = dict(concept_type=ztyp, title=zttl, description=zdsc)
        write_bundle(
            ws,
            rel_out,
            [
                concept_spec(p_id, body=p_out, **common_p),
                concept_spec(q_id, body=q_plain, **common_q),
                concept_spec(z_id, body=z_body, **common_z),
            ],
        )
        write_bundle(
            ws,
            rel_in,
            [
                concept_spec(p_id, body=p_in, **common_p),
                concept_spec(q_id, body=q_to_p, **common_q),
                concept_spec(z_id, body=z_body, **common_z),
            ],
        )
        report_out = require_human_show(run_show(ws, p_id, rel_out))
        report_in = require_human_show(run_show(ws, p_id, rel_in))
        out_in, out_out = report_out.id_list("Inbound"), report_out.id_list("Outbound")
        in_in, in_out = report_in.id_list("Inbound"), report_in.id_list("Outbound")
        print(
            f"direction P->Q bundle inbound={out_in!r} outbound={out_out!r}; "
            f"Q->P bundle inbound={in_in!r} outbound={in_out!r}",
            flush=True,
        )
        assert q_id in out_out and q_id not in out_in, (
            f"with P linking to Q, Q is not reported as outbound only: "
            f"inbound={out_in!r} outbound={out_out!r}"
        )
        assert q_id in in_in and q_id not in in_out, (
            f"with Q linking to P, Q is not reported as inbound only: "
            f"inbound={in_in!r} outbound={in_out!r}"
        )
        assert z_id in out_out and z_id in in_out, (
            f"P's unchanged link to Z is not outbound in both bundles: "
            f"{out_out!r} {in_out!r}"
        )


def test_relationship_generated_pair_and_runtime_twin():
    """Same-directory link: source outbound, target inbound, plus a runtime twin."""
    with workspace() as ws:
        ptyp, qtyp, pttl, qttl, pdsc, qdsc, ptok, qtok, sdir, pleaf, qleaf = unique_tokens(
            "ptyp", "qtyp", "pttl", "qttl", "pdsc", "qdsc", "pbod", "qbod",
            "sdir", "sleafp", "sleafq",
        )
        p_id = f"{sdir}/{pleaf}"
        q_id = f"{sdir}/{qleaf}"
        rel = unique_tokens("kbsamp")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    p_id,
                    concept_type=ptyp,
                    title=pttl,
                    description=pdsc,
                    body=f"{ptok}\n\n{markdown_link('gov', qleaf + '.md')}\n",
                ),
                concept_spec(
                    q_id,
                    concept_type=qtyp,
                    title=qttl,
                    description=qdsc,
                    body=f"{qtok}\n",
                ),
            ],
        )
        source = require_human_show(run_show(ws, p_id, rel))
        target = require_human_show(run_show(ws, q_id, rel))
        assert q_id in source.id_list("Outbound"), (
            f"sample source missing outbound {q_id!r}: {source.fields!r}"
        )
        assert p_id in target.id_list("Inbound"), (
            f"sample target missing inbound {p_id!r}: {target.fields!r}"
        )

        t_leaf, u_leaf, ttyp, utyp, tttl, uttl, tdsc, udsc, ttok, utok = unique_tokens(
            "trel", "urel", "ttyp", "utyp", "tttl", "uttl", "tdsc", "udsc", "tbod", "ubod"
        )
        t_id = f"architecture/{t_leaf}"
        u_id = f"architecture/{u_leaf}"
        rel2 = unique_tokens("kbtwinr")[0]
        write_bundle(
            ws,
            rel2,
            [
                concept_spec(
                    t_id,
                    concept_type=ttyp,
                    title=tttl,
                    description=tdsc,
                    body=f"{ttok}\n\n{markdown_link(u_leaf, f'{u_leaf}.md')}\n",
                ),
                concept_spec(
                    u_id,
                    concept_type=utyp,
                    title=uttl,
                    description=udsc,
                    body=f"{utok}\n",
                ),
            ],
        )
        twin_src = require_human_show(run_show(ws, t_id, rel2))
        twin_tgt = require_human_show(run_show(ws, u_id, rel2))
        assert u_id in twin_src.id_list("Outbound"), (
            f"twin source missing outbound {u_id!r}: {twin_src.fields!r}"
        )
        assert t_id in twin_tgt.id_list("Inbound"), (
            f"twin target missing inbound {t_id!r}: {twin_tgt.fields!r}"
        )
        unselected_token_absent(twin_src, ptok)
        print(f"relationship twin {t_id} -> {u_id}", flush=True)


# ---------------------------------------------------------------------------
# E. Fenced blocks and non-concept link targets are ignored
# ---------------------------------------------------------------------------


def test_fenced_markdown_link_is_not_outbound():
    """A fenced link to an existing concept is not outbound."""
    with workspace() as ws:
        fx = ignore_list_fixture(ws, fence_ignored=True)
        report = require_human_show(run_show(ws, fx["p_id"], fx["rel"]))
        outbound = report.id_list("Outbound")
        print(f"fenced outbound={outbound!r}", flush=True)
        assert fx["q_id"] in outbound, (
            f"live unfenced target {fx['q_id']!r} is not outbound: {outbound!r}"
        )
        assert fx["ign_id"] not in outbound, (
            f"fenced identity {fx['ign_id']!r} is reported outbound: {outbound!r}"
        )
        ign_show = require_human_show(run_show(ws, fx["ign_id"], fx["rel"]))
        ign_inbound = ign_show.id_list("Inbound")
        assert fx["p_id"] not in ign_inbound, (
            f"fenced target reports source {fx['p_id']!r} as inbound: "
            f"{ign_inbound!r}"
        )


def test_unfenced_twin_does_count_the_same_link():
    """The same link unfenced is outbound; live baseline for the ignore arm."""
    with workspace() as ws:
        fx = ignore_list_fixture(ws, fence_ignored=False)
        report = require_human_show(run_show(ws, fx["p_id"], fx["rel"]))
        outbound = report.id_list("Outbound")
        print(f"unfenced outbound={outbound!r}", flush=True)
        assert fx["ign_id"] in outbound, (
            f"unfenced ignored identity {fx['ign_id']!r} is not outbound: "
            f"{outbound!r}"
        )
        ign_show = require_human_show(run_show(ws, fx["ign_id"], fx["rel"]))
        ign_inbound = ign_show.id_list("Inbound")
        assert fx["p_id"] in ign_inbound, (
            f"unfenced target does not report inbound {fx['p_id']!r}: "
            f"{ign_inbound!r}"
        )


def test_links_to_index_log_agents_and_external_urls_are_not_concept_relationships():
    """Reserved documents and URL-tail plants are not related identities."""
    with workspace() as ws:
        fx = ignore_list_fixture(ws, fence_ignored=True)
        report = require_human_show(run_show(ws, fx["p_id"], fx["rel"]))
        outbound = report.id_list("Outbound")
        inbound = report.id_list("Inbound")
        print(f"ignore-list inbound={inbound!r} outbound={outbound!r}", flush=True)
        assert fx["q_id"] in outbound, (
            f"live Q {fx['q_id']!r} is not outbound: {outbound!r}"
        )
        related = outbound + inbound
        for banned in (fx["ign_id"], fx["decoy_id"]):
            assert banned not in related, (
                f"non-concept link target {banned!r} is reported as a related "
                f"identity: inbound={inbound!r} outbound={outbound!r}"
            )
        for entry in related:
            leaf = entry.rsplit("/", 1)[-1]
            assert leaf not in ("index", "log", "AGENTS"), (
                f"reserved document {entry!r} is reported as a related "
                f"identity: inbound={inbound!r} outbound={outbound!r}"
            )
            assert "example.com" not in entry, (
                f"external URL {entry!r} is reported as a related identity"
            )
        decoy_show = require_human_show(run_show(ws, fx["decoy_id"], fx["rel"]))
        decoy_inbound = decoy_show.id_list("Inbound")
        assert fx["p_id"] not in decoy_inbound, (
            f"href-tail plant reports source {fx['p_id']!r} as inbound: "
            f"{decoy_inbound!r}"
        )


# ---------------------------------------------------------------------------
# F. Raw equals disk; structured is a parseable record
# ---------------------------------------------------------------------------


def test_raw_mode_emits_on_disk_file_bytes():
    """Raw stdout bytes equal the concept file, including frontmatter."""
    with workspace() as ws:
        ident, typ, title, desc, token, extra_val = unique_tokens(
            "rid", "rtyp", "rttl", "rdsc", "rbod", "rxtra"
        )
        body = f"{token}\nraw body line\n"
        rel = unique_tokens("kbraw")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                    extra={"extra_field": extra_val},
                )
            ],
        )
        path = ws.resolve(rel) / f"{ident}.md"
        file_bytes = concept_file_bytes(path)
        result = run_show(ws, ident, rel, raw=True)
        require_show_raw_success(result, file_bytes)
        assert extra_val.encode("utf-8") in result.stdout
        assert token.encode("utf-8") in result.stdout
        print(f"raw len={len(result.stdout)} file_len={len(file_bytes)}", flush=True)


def test_structured_mode_record_includes_identity_type_and_body():
    """Structured stdout is a walkable record with identity, type, and body."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "jid", "jtyp", "jttl", "jdsc", "jbod"
        )
        body = f"{token}\nstructured paragraph\n"
        rel = unique_tokens("kbjson")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                )
            ],
        )
        file_body = concept_body_from_file(ws.resolve(rel) / f"{ident}.md")
        record = require_show_structured_success(
            run_show(ws, ident, rel, structured=True)
        )
        require_record_has_identity_type_body(record, ident, typ, file_body)
        print(f"structured identity={ident!r} type={typ!r}", flush=True)
        assert show_record_field(record, "id") == ident
        assert show_record_field(record, "type") == typ
        assert show_record_field(record, "body").strip() == file_body.strip()


def test_human_mode_is_not_replaced_by_structured_or_raw_only():
    """Default human show still presents fields on the same fixture."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "hid", "htyp", "httl", "hdsc", "hbod"
        )
        body = f"{token}\n"
        rel = unique_tokens("kbhum")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=body,
                )
            ],
        )
        path = ws.resolve(rel) / f"{ident}.md"
        require_show_raw_success(
            run_show(ws, ident, rel, raw=True), concept_file_bytes(path)
        )
        file_body = concept_body_from_file(path)
        require_record_has_identity_type_body(
            require_show_structured_success(
                run_show(ws, ident, rel, structured=True)
            ),
            ident,
            typ,
            file_body,
        )
        report = require_human_show(run_show(ws, ident, rel))
        assert_human_presents(
            report,
            identity=ident,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )


# ---------------------------------------------------------------------------
# G. Default bundle path and nested-knowledge load redirect
# ---------------------------------------------------------------------------


def test_omit_path_without_knowledge_dir_loads_cwd():
    """No knowledge/ directory: omit-path loads the cwd bundle."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "cid", "ctyp", "cttl", "cdsc", "cbod"
        )
        write_bundle(
            ws,
            ".",
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        assert not (ws.path / "knowledge").exists()
        report = require_human_show(run_show(ws, ident))
        assert_human_presents(
            report,
            identity=ident,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )
        print("omit-path cwd load ok", flush=True)


def test_omit_path_with_knowledge_dir_loads_knowledge_not_cwd_decoy():
    """knowledge/ as a directory wins omit-path; cwd decoy token is absent."""
    with workspace() as ws:
        leaf, typ, title, desc, token, dtitle, dtoken = unique_tokens(
            "klay", "ktyp", "kttl", "kdsc", "kbod", "dttl", "dbod"
        )
        ident = f"architecture/{leaf}"
        write_bundle(
            ws,
            "knowledge",
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        decoy = render_concept_markdown(
            concept_type=typ,
            title=dtitle,
            description=desc,
            body=f"{dtoken}\n",
        )
        ws.write(f"{ident}.md", decoy)
        report = require_human_show(run_show(ws, ident))
        assert_human_presents(
            report,
            identity=ident,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )
        unselected_token_absent(report, dtoken)
        unselected_token_absent(report, dtitle)
        print("omit-path knowledge decoy absent", flush=True)


def test_omit_path_knowledge_file_is_not_treated_as_bundle_dir():
    """A file named knowledge is not the omit-path bundle directory."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "fid", "ftyp", "fttl", "fdsc", "fbod"
        )
        write_bundle(
            ws,
            ".",
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        (ws.path / "knowledge").write_text("not-a-directory\n", encoding="utf-8")
        report = require_human_show(run_show(ws, ident))
        assert_human_presents(
            report,
            identity=ident,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )


def test_named_path_without_root_index_loads_nested_knowledge():
    """Named path with no root index.md loads nested knowledge/."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "nid", "ntyp", "nttl", "ndsc", "nbod"
        )
        proj = unique_tokens("proj")[0]
        write_bundle(
            ws,
            f"{proj}/knowledge",
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        assert not (ws.resolve(proj) / "index.md").exists()
        report = require_human_show(run_show(ws, ident, proj))
        assert_human_presents(
            report,
            identity=ident,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )
        print(f"nested knowledge load via named {proj}", flush=True)


def test_explicit_bundle_path_is_not_overridden_by_cwd_knowledge():
    """A named bundle is the load root even when cwd has knowledge/."""
    with workspace() as ws:
        ident, typ, title, desc, token, dtitle, dtoken = unique_tokens(
            "eid", "etyp", "ettl", "edsc", "ebod", "dttl", "dbod"
        )
        named = unique_tokens("namedb")[0]
        write_bundle(
            ws,
            named,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        write_bundle(
            ws,
            "knowledge",
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=dtitle,
                    description=desc,
                    body=f"{dtoken}\n",
                )
            ],
        )
        report = require_human_show(run_show(ws, ident, named))
        assert_human_presents(
            report,
            identity=ident,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )
        unselected_token_absent(report, dtoken)
        unselected_token_absent(report, dtitle)


# ---------------------------------------------------------------------------
# H. Missing identity argument
# ---------------------------------------------------------------------------


def test_missing_identity_argument_is_non_success_and_not_a_silent_or_success_shaped_failure():
    """Missing argv identity prints a usage-class report, not not-found."""
    with workspace() as ws:
        ident, typ, title, desc, token, g1, g2 = unique_tokens(
            "uid", "utyp", "uttl", "udsc", "ubod", "g1", "g2"
        )
        rel = unique_tokens("kbusage")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        success = require_human_show(run_show(ws, ident, rel))
        nf1 = require_not_found(run_show(ws, g1, rel), g1)
        nf2 = require_not_found(run_show(ws, g2, rel), g2)
        paths = path_tokens_for(rel, ws.path)
        print(f"not-found reports {nf1!r} vs {nf2!r}", flush=True)
        # TEST-FIX(F03): with no bin/membundle there is no product to run before show; per the Contract "Build" form, make build at the repository root writes that binary.
        missing = ws.invoke(["show"], binary=resolve_show_binary())
        require_usage_failure(
            missing,
            success.report,
            "",
            path_tokens=paths,
            ghost_identities=(g1, g2),
        )


# ---------------------------------------------------------------------------
# I. Invalid identities are rejected
# ---------------------------------------------------------------------------


def test_empty_identity_is_rejected():
    """Empty identity is rejected on human, structured, and raw."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "eid", "etyp", "ettl", "edsc", "ebod"
        )
        rel = unique_tokens("kbempty")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        results = reject_identity_on_all_show_modes(
            ws, "", rel, forbidden_body=token
        )
        print(f"empty identity exits={[r.returncode for r in results]}", flush=True)
        assert all(r.returncode != 0 for r in results), (
            "empty identity was not rejected on every show mode; "
            f"exits={[r.returncode for r in results]}"
        )


def test_absolute_identity_is_rejected():
    """Absolute identity does not inspect the aimed file."""
    with workspace() as ws:
        ident, typ, title, desc, token, atyp, atitle, adesc, atoken = unique_tokens(
            "aid", "atyp", "attl", "adsc", "abod", "xtyp", "xttl", "xdsc", "xbod"
        )
        rel = unique_tokens("kbabs")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        aimed = ws.write(
            f"{unique_tokens('aimed')[0]}.md",
            render_concept_markdown(
                concept_type=atyp,
                title=atitle,
                description=adesc,
                body=f"{atoken}\n",
            ),
        )
        abs_id = str(aimed.resolve())
        aimed_bytes = aimed.read_bytes()
        results = reject_identity_on_all_show_modes(
            ws,
            abs_id,
            rel,
            forbidden_body=atoken,
            forbidden_file_bytes=aimed_bytes,
        )
        print(f"absolute identity exits={[r.returncode for r in results]}", flush=True)
        assert all(r.returncode != 0 for r in results), (
            "absolute identity was not rejected on every show mode; "
            f"exits={[r.returncode for r in results]}"
        )
        assert all(r.stdout != aimed_bytes for r in results), (
            "absolute identity emitted the aimed file bytes as a successful "
            "inspection"
        )


def test_dotdot_identity_is_rejected():
    """Identities containing .. do not inspect the aimed file."""
    with workspace() as ws:
        ident, typ, title, desc, token, otyp, otitle, odesc, otoken = unique_tokens(
            "did", "dtyp", "dttl", "ddsc", "dbod", "otyp", "ottl", "odsc", "obod"
        )
        rel = unique_tokens("kbdot")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        outside = ws.write(
            f"{unique_tokens('outside')[0]}.md",
            render_concept_markdown(
                concept_type=otyp,
                title=otitle,
                description=odesc,
                body=f"{otoken}\n",
            ),
        )
        escape = f"../{outside.stem}"
        outside_bytes = outside.read_bytes()
        escape_results = reject_identity_on_all_show_modes(
            ws,
            escape,
            rel,
            forbidden_body=otoken,
            forbidden_file_bytes=outside_bytes,
        )
        nested = f"nest/../{ident}"
        nested_bytes = concept_file_bytes(ws.resolve(rel) / f"{ident}.md")
        nested_results = reject_identity_on_all_show_modes(
            ws,
            nested,
            rel,
            forbidden_body=token,
            forbidden_file_bytes=nested_bytes,
        )
        print(
            f"dotdot exits escape={[r.returncode for r in escape_results]} "
            f"nested={[r.returncode for r in nested_results]}",
            flush=True,
        )
        assert all(r.returncode != 0 for r in escape_results), (
            "identity containing .. was not rejected on every show mode; "
            f"exits={[r.returncode for r in escape_results]}"
        )
        assert all(r.stdout != outside_bytes for r in escape_results), (
            "identity containing .. emitted the aimed outside file bytes"
        )
        assert all(r.returncode != 0 for r in nested_results), (
            "nested .. identity was not rejected on every show mode; "
            f"exits={[r.returncode for r in nested_results]}"
        )
        assert all(r.stdout != nested_bytes for r in nested_results), (
            "nested .. identity emitted the in-bundle file bytes as a "
            "successful inspection"
        )


def test_leading_hyphen_identity_is_rejected():
    """An identity that starts with a hyphen is rejected."""
    with workspace() as ws:
        ident, typ, title, desc, token, hy = unique_tokens(
            "hid", "htyp", "httl", "hdsc", "hbod", "hyph"
        )
        rel = unique_tokens("kbhy")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        results = reject_identity_on_all_show_modes(
            ws, f"-{hy}", rel, forbidden_body=token
        )
        print(f"leading-hyphen exits={[r.returncode for r in results]}", flush=True)
        assert all(r.returncode != 0 for r in results), (
            "leading-hyphen identity was not rejected on every show mode; "
            f"exits={[r.returncode for r in results]}"
        )


def test_newline_cr_tab_identities_are_rejected():
    """Newline, CR, and tab in the identity do not inspect the concatenated id."""
    with workspace() as ws:
        left, right, typ, title, desc, token = unique_tokens(
            "cl", "cr", "ctyp", "cttl", "cdsc", "cbod"
        )
        concat = left + right
        rel = unique_tokens("kbctl")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    concat,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        file_bytes = concept_file_bytes(ws.resolve(rel) / f"{concat}.md")
        for ident in (left + "\n" + right, left + "\r" + right, left + "\t" + right):
            print(f"control-char identity={ident!r}", flush=True)
            results = reject_identity_on_all_show_modes(
                ws,
                ident,
                rel,
                forbidden_body=token,
                forbidden_file_bytes=file_bytes,
            )
            assert all(r.returncode != 0 for r in results), (
                "control-character identity was not rejected on every show "
                f"mode; identity={ident!r} exits={[r.returncode for r in results]}"
            )
            assert all(r.stdout != file_bytes for r in results), (
                "control-character identity emitted the concatenated concept "
                f"file bytes; identity={ident!r}"
            )


def test_null_byte_identity_is_rejected_via_mcp():
    """NUL in concept_id via MCP does not inspect the concatenated identity."""
    with workspace() as ws:
        left, right, typ, title, desc, token = unique_tokens(
            "nl", "nr", "ntyp", "nttl", "ndsc", "nbod"
        )
        concat = left + right
        rel = unique_tokens("kbnul")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    concat,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        file_body = concept_body_from_file(ws.resolve(rel) / f"{concat}.md")
        baseline = mcp_show(ws, concat, rel)
        require_mcp_success_record(baseline, concat, typ, file_body)
        outcome = mcp_show(ws, left + "\x00" + right, rel)
        print(f"nul mcp report={outcome.report_text!r}", flush=True)
        assert not mcp_is_protocol_error(outcome.reply), (
            "NUL identity was rejected as a JSON-RPC protocol error; "
            "the PRD requires a tool-level failure: "
            f"{outcome.reply!r}"
        )
        assert mcp_is_tool_error(outcome.reply), (
            "NUL identity is not a tool-level failure; a successful "
            "tools/call (including an empty or differently shaped result) "
            f"is not a non-success inspection; reply={outcome.reply!r}"
        )
        require_mcp_tool_level_failure(outcome)
        assert not mcp_is_success_record(outcome, concat, typ, file_body), (
            "NUL identity produced a successful concept record for the "
            f"concatenated identity {concat!r}: {outcome.report_text!r}"
        )


def test_reserved_index_log_agents_and_nested_index_are_rejected():
    """Reserved documents are not successful inspections, with or without .md."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "rid", "rtyp", "rttl", "rdsc", "rbod"
        )
        rel = unique_tokens("kbres")[0]
        root = write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
            agents="# agents\n",
        )
        (root / "architecture").mkdir(exist_ok=True)
        (root / "architecture" / "index.md").write_text("# nested nav\n", encoding="utf-8")
        index_bytes = (root / "index.md").read_bytes()
        reserved = (
            "index",
            "index.md",
            "architecture/index",
            "architecture/index.md",
            "log",
            "log.md",
            "AGENTS",
            "AGENTS.md",
        )
        for name in reserved:
            extra = index_bytes if name in {"index", "index.md"} else None
            results = reject_identity_on_all_show_modes(
                ws,
                name,
                rel,
                forbidden_body=token,
                forbidden_file_bytes=extra,
            )
            print(
                f"reserved {name!r} exits={[r.returncode for r in results]}",
                flush=True,
            )
            assert all(r.returncode != 0 for r in results), (
                f"reserved identity {name!r} was not rejected on every show "
                f"mode; exits={[r.returncode for r in results]}"
            )
            if extra is not None:
                assert all(r.stdout != extra for r in results), (
                    f"reserved identity {name!r} emitted on-disk index.md bytes"
                )


def test_raw_and_structured_modes_reject_reserved_and_invalid_identities():
    """Raw of reserved index is not the file; structured ghost is not a success record."""
    with workspace() as ws:
        ident, typ, title, desc, token, ghost = unique_tokens(
            "mid", "mtyp", "mttl", "mdsc", "mbod", "ghost"
        )
        rel = unique_tokens("kbmode")[0]
        root = write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        index_bytes = (root / "index.md").read_bytes()
        raw_index = run_show(ws, "index", rel, raw=True)
        require_not_successful_inspection(
            raw_index, forbidden_file_bytes=index_bytes
        )
        json_reserved = run_show(ws, "index", rel, structured=True)
        require_not_successful_inspection(
            json_reserved, forbidden_file_bytes=index_bytes
        )
        json_ghost = run_show(ws, ghost, rel, structured=True)
        require_not_found(json_ghost, ghost)
        file_body = concept_body_from_file(root / f"{ident}.md")
        assert not structured_stdout_is_success_record(
            json_ghost, ident, typ, file_body
        ), (
            "structured ghost produced a parseable success record of a live "
            f"concept: stdout={json_ghost.stdout!r}"
        )
        raw_empty = run_show(ws, "", rel, raw=True)
        require_not_successful_inspection(raw_empty, forbidden_body=token)


# ---------------------------------------------------------------------------
# J. Not-found vs load error
# ---------------------------------------------------------------------------


def test_missing_concept_does_not_succeed_and_identifies_the_identity():
    """A well-formed missing identity is not-found and names that identity."""
    with workspace() as ws:
        ident, typ, title, desc, token, ghost = unique_tokens(
            "jid", "jtyp", "jttl", "jdsc", "jbod", "miss"
        )
        rel = unique_tokens("kbnf")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        live = require_human_show(run_show(ws, ident, rel))
        assert_human_presents(
            live,
            identity=ident,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )
        require_not_found(run_show(ws, ghost, rel), ghost)


def test_two_missing_identities_are_identified_distinctly():
    """Two ghosts each name their own identity and share a class remainder."""
    with workspace() as ws:
        ident, typ, title, desc, token, g1, g2 = unique_tokens(
            "tid", "ttyp", "tttl", "tdsc", "tbod", "ga", "gb"
        )
        rel = unique_tokens("kbtwo")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        r1 = require_not_found(run_show(ws, g1, rel), g1)
        r2 = require_not_found(run_show(ws, g2, rel), g2)
        assert r1 != r2
        print(f"two-ghost reports {r1!r} vs {r2!r}", flush=True)
        assert g2 not in r1 and g1 not in r2, (
            "a ghost not-found report names the other ghost: "
            f"{r1!r} vs {r2!r}"
        )


def test_unloadable_bundle_differs_from_not_found_on_a_loadable_bundle():
    """Missing bundle directory is a load error, not not-found."""
    with workspace() as ws:
        ident, typ, title, desc, token, ghost = unique_tokens(
            "lid", "ltyp", "lttl", "ldsc", "lbod", "lgh"
        )
        rel = unique_tokens("kbload")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        nf = require_not_found(run_show(ws, ghost, rel), ghost)
        missing = unique_tokens("absent")[0]
        load = run_show(ws, ghost, missing)
        paths = path_tokens_for(rel, missing, ws.path)
        load_report = require_load_error(load, nf, paths, ghost)
        print(f"unloadable exit={load.returncode}", flush=True)
        assert load.returncode != 0, (
            f"missing bundle path succeeded; report={load_report!r}"
        )


def test_bundle_path_that_is_a_file_is_a_load_error():
    """A regular file as the bundle path is the same load-error class."""
    with workspace() as ws:
        ident, typ, title, desc, token, ghost = unique_tokens(
            "fid", "ftyp", "fttl", "fdsc", "fbod", "fgh"
        )
        rel = unique_tokens("kbfile")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        nf = require_not_found(run_show(ws, ghost, rel), ghost)
        file_bundle = unique_tokens("asfile")[0]
        ws.write(file_bundle, "not-a-bundle\n")
        load = run_show(ws, ghost, file_bundle)
        paths = path_tokens_for(rel, file_bundle, ws.path)
        load_report = require_load_error(load, nf, paths, ghost)
        print(f"file-as-bundle exit={load.returncode}", flush=True)
        assert load.returncode != 0, (
            f"file-as-bundle path succeeded; report={load_report!r}"
        )


def test_structured_and_raw_of_a_ghost_are_not_success_inspections():
    """--json and --raw of a missing identity are not-found, not success records."""
    with workspace() as ws:
        ident, typ, title, desc, token, ghost = unique_tokens(
            "gid", "gtyp", "gttl", "gdsc", "gbod", "ggh"
        )
        rel = unique_tokens("kbghost")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        require_not_found(run_show(ws, ghost, rel, structured=True), ghost)
        raw = run_show(ws, ghost, rel, raw=True)
        require_not_found(raw, ghost)
        live_bytes = concept_file_bytes(ws.resolve(rel) / f"{ident}.md")
        assert raw.stdout != live_bytes, (
            "raw ghost emitted a live concept file's bytes"
        )


# ---------------------------------------------------------------------------
# K. Load skips: symlink, hidden, node_modules, non-Markdown
# ---------------------------------------------------------------------------


def test_escaping_symlink_makes_show_a_load_error():
    """A .md symlink whose target leaves the bundle makes show a load error."""
    with workspace() as ws:
        ident, typ, title, desc, token, otyp, otitle, odesc, otoken = unique_tokens(
            "sid", "styp", "sttl", "sdsc", "sbod", "otyp", "ottl", "odsc", "obod"
        )
        rel_good = unique_tokens("kbgood")[0]
        rel_bad = unique_tokens("kbbad")[0]
        specs = [
            concept_spec(
                ident,
                concept_type=typ,
                title=title,
                description=desc,
                body=f"{token}\n",
            )
        ]
        write_bundle(ws, rel_good, specs)
        bad_root = write_bundle(ws, rel_bad, specs)
        secret = ws.write(
            f"{unique_tokens('secret')[0]}.md",
            render_concept_markdown(
                concept_type=otyp,
                title=otitle,
                description=odesc,
                body=f"{otoken}\n",
            ),
        )
        os.symlink(secret, bad_root / f"{unique_tokens('leak')[0]}.md")
        good = require_human_show(run_show(ws, ident, rel_good))
        assert_human_presents(
            good,
            identity=ident,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )
        ghost = unique_tokens("sgh")[0]
        nf = require_not_found(run_show(ws, ghost, rel_good), ghost)
        leaked = run_show(ws, ident, rel_bad)
        require_not_successful_inspection(
            leaked,
            forbidden_body=otoken,
            forbidden_file_bytes=secret.read_bytes(),
        )
        load_ghost = run_show(ws, ghost, rel_bad)
        require_load_error(
            load_ghost, nf, path_tokens_for(rel_good, rel_bad, ws.path), ghost
        )
        print(f"symlink load report={leaked.returncode}", flush=True)


def test_hidden_markdown_is_not_loaded_as_a_concept():
    """Hidden .md is not a concept; a visible sibling still shows."""
    with workspace() as ws:
        ident, typ, title, desc, token, htok = unique_tokens(
            "hid", "htyp", "httl", "hdsc", "hbod", "hsec"
        )
        rel = unique_tokens("kbhid")[0]
        root = write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        (root / ".secret.md").write_text(
            render_concept_markdown(
                concept_type=typ,
                title=title,
                description=desc,
                body=f"{htok}\n",
            ),
            encoding="utf-8",
        )
        visible = require_human_show(run_show(ws, ident, rel))
        assert_human_presents(
            visible,
            identity=ident,
            concept_type=typ,
            title=title,
            description=desc,
            body_token=token,
        )
        unselected_token_absent(visible, htok)
        hidden = run_show(ws, ".secret", rel)
        require_not_successful_inspection(hidden, forbidden_body=htok)


def test_node_modules_markdown_is_not_loaded_as_a_concept():
    """Show of node_modules/decoy and of decoy must not deliver that file."""
    with workspace() as ws:
        ident, typ, title, desc, token, dtok = unique_tokens(
            "nid", "ntyp", "nttl", "ndsc", "nbod", "nmod"
        )
        rel = unique_tokens("kbnm")[0]
        root = write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        nm = root / "node_modules"
        nm.mkdir()
        decoy_body = f"{dtok}\n"
        (nm / "decoy.md").write_text(
            render_concept_markdown(
                concept_type=typ,
                title=title,
                description=desc,
                body=decoy_body,
            ),
            encoding="utf-8",
        )
        visible = require_human_show(run_show(ws, ident, rel))
        assert token in visible.body, (
            f"visible sibling concept {ident!r} did not show: {visible!r}"
        )
        assert dtok not in visible.report, (
            f"show of the visible concept presented node_modules decoy "
            f"{dtok!r}: {visible!r}"
        )
        nm = run_show(ws, "node_modules/decoy", rel)
        require_not_successful_inspection(nm, forbidden_body=dtok)
        assert nm.returncode != 0, (
            "show of node_modules/decoy succeeded as a concept inspection"
        )
        decoy = run_show(ws, "decoy", rel)
        require_not_successful_inspection(decoy, forbidden_body=dtok)
        assert decoy.returncode != 0, (
            "show of decoy succeeded as the node_modules markdown file"
        )


def test_non_markdown_file_is_not_loaded_as_a_concept():
    """Show of notes.txt and of notes must not deliver the .txt token."""
    with workspace() as ws:
        ident, typ, title, desc, token, ntok = unique_tokens(
            "xid", "xtyp", "xttl", "xdsc", "xbod", "ntxt"
        )
        rel = unique_tokens("kbtxt")[0]
        root = write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        (root / "notes.txt").write_text(f"{ntok}\nplain text\n", encoding="utf-8")
        visible = require_human_show(run_show(ws, ident, rel))
        assert token in visible.body, (
            f"visible sibling concept {ident!r} did not show: {visible!r}"
        )
        assert ntok not in visible.report, (
            f"show of the visible concept presented notes.txt token "
            f"{ntok!r}: {visible!r}"
        )
        as_txt = run_show(ws, "notes.txt", rel)
        require_not_successful_inspection(as_txt, forbidden_body=ntok)
        assert as_txt.returncode != 0, (
            "show of notes.txt succeeded as a concept inspection"
        )
        as_notes = run_show(ws, "notes", rel)
        require_not_successful_inspection(as_notes, forbidden_body=ntok)
        assert as_notes.returncode != 0, (
            "show of notes succeeded as the non-markdown notes.txt file"
        )


# ---------------------------------------------------------------------------
# L. Show never creates or mutates files
# ---------------------------------------------------------------------------


def test_show_modes_do_not_mutate_bundle_files():
    """Human, structured, and raw success leave the bundle bytes unchanged."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "mid", "mtyp", "mttl", "mdsc", "mbod"
        )
        rel = unique_tokens("kbmut")[0]
        root = write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        assert_snapshot_helper_sees_write(ws, unique_tokens("probe")[0])
        before = snapshot_tree(root)
        require_human_show(run_show(ws, ident, rel))
        require_show_structured_success(run_show(ws, ident, rel, structured=True))
        require_show_raw_success(
            run_show(ws, ident, rel, raw=True),
            concept_file_bytes(root / f"{ident}.md"),
        )
        after = snapshot_tree(root)
        print(f"success snapshot equal={before == after}", flush=True)
        assert before == after, (
            "successful show mutated bundle files; "
            f"before={sorted(before)} after={sorted(after)}"
        )


def test_show_failures_do_not_create_or_mutate_files():
    """Not-found, reserved, missing-arg, and load-error do not write files."""
    with workspace() as ws:
        ident, typ, title, desc, token, ghost = unique_tokens(
            "fid", "ftyp", "fttl", "fdsc", "fbod", "fgh"
        )
        rel = unique_tokens("kbfail")[0]
        root = write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        assert_snapshot_helper_sees_write(ws, unique_tokens("probe2")[0])
        before_ws = snapshot_tree(ws.path)
        require_not_found(run_show(ws, ghost, rel), ghost)
        require_not_successful_inspection(run_show(ws, "index", rel))
        # TEST-FIX(F03): with no bin/membundle there is no product to run before show; per the Contract "Build" form, make build at the repository root writes that binary.
        require_not_successful_inspection(
            ws.invoke(["show"], binary=resolve_show_binary())
        )
        require_not_successful_inspection(
            run_show(ws, ghost, unique_tokens("nope")[0])
        )
        after_ws = snapshot_tree(ws.path)
        print(
            f"failure snapshot equal={before_ws == after_ws} "
            f"n={len(before_ws)}",
            flush=True,
        )
        assert before_ws == after_ws, (
            "failure-path show created or mutated files; "
            f"before={sorted(before_ws)} after={sorted(after_ws)}"
        )
        bundle_before = {
            key[len(rel) + 1 :]: value
            for key, value in before_ws.items()
            if key.startswith(f"{rel}/")
        }
        assert snapshot_tree(root) == bundle_before, (
            "failure-path show mutated the bundle tree; "
            f"before={sorted(bundle_before)} after={sorted(snapshot_tree(root))}"
        )


# ---------------------------------------------------------------------------
# M. MCP membundle_show is the same inspection
# ---------------------------------------------------------------------------


def test_mcp_show_returns_identity_type_and_body():
    """membundle_show returns a concept record with identity, type, and body."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "mcp", "mtyp", "mttl", "mdsc", "mbod"
        )
        rel = unique_tokens("kbmcp")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        file_body = concept_body_from_file(ws.resolve(rel) / f"{ident}.md")
        outcome = mcp_show(ws, ident, rel)
        record = require_mcp_success_record(outcome, ident, typ, file_body)
        print(f"mcp identity={ident!r} type={typ!r}", flush=True)
        assert show_record_field(record, "id") == ident
        assert show_record_field(record, "type") == typ
        assert show_record_field(record, "body").strip() == file_body.strip()


def test_mcp_show_matches_structured_cli_record_on_a_linked_concept():
    """membundle_show of a linked concept is the structured inspect record, not human inbound/outbound."""
    with workspace() as ws:
        p_leaf, q_leaf, ptyp, qtyp, pttl, qttl, pdsc, qdsc, ptok, qtok = unique_tokens(
            "plnk", "qlnk", "ptyp", "qtyp", "pttl", "qttl", "pdsc", "qdsc", "pbod", "qbod"
        )
        p_id = f"architecture/{p_leaf}"
        q_id = f"architecture/{q_leaf}"
        p_body = f"{ptok}\n\nSee {markdown_link(q_leaf, f'{q_leaf}.md')}.\n"
        q_body = f"{qtok}\n\nNo backlink.\n"
        rel = unique_tokens("kbmcpio")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    p_id, concept_type=ptyp, title=pttl, description=pdsc, body=p_body
                ),
                concept_spec(
                    q_id, concept_type=qtyp, title=qttl, description=qdsc, body=q_body
                ),
            ],
        )
        source_human = require_human_show(run_show(ws, p_id, rel))
        target_human = require_human_show(run_show(ws, q_id, rel))
        print(
            f"human source outbound={source_human.id_list('Outbound')!r} "
            f"human target inbound={target_human.id_list('Inbound')!r}",
            flush=True,
        )
        assert q_id in source_human.id_list("Outbound"), (
            f"CLI show of source {p_id!r} does not report outbound {q_id!r}: "
            f"{source_human.fields!r}"
        )
        assert p_id in target_human.id_list("Inbound"), (
            f"CLI show of target {q_id!r} does not report inbound {p_id!r}: "
            f"{target_human.fields!r}"
        )
        file_body = concept_body_from_file(ws.resolve(rel) / f"{p_id}.md")
        cli_record = require_show_structured_success(
            run_show(ws, p_id, rel, structured=True)
        )
        require_record_has_identity_type_body(cli_record, p_id, ptyp, file_body)
        mcp_outcome = mcp_show(ws, p_id, rel)
        mcp_record = require_mcp_success_record(mcp_outcome, p_id, ptyp, file_body)
        for key in ("id", "type"):
            cli_value = show_record_field(cli_record, key)
            mcp_value = show_record_field(mcp_record, key)
            print(f"linked inspect {key}: cli={cli_value!r} mcp={mcp_value!r}", flush=True)
            assert cli_value == mcp_value, (
                f"membundle_show and structured CLI differ on {key!r}: "
                f"cli={cli_value!r} mcp={mcp_value!r}"
            )
        cli_body = show_record_field(cli_record, "body")
        mcp_body = show_record_field(mcp_record, "body")
        assert cli_body.strip() == mcp_body.strip(), (
            "membundle_show and structured CLI differ on the post-frontmatter body; "
            f"cli={cli_body!r} mcp={mcp_body!r}"
        )


def test_mcp_show_strips_trailing_md():
    """membundle_show concept_id with a trailing .md still resolves."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "ms", "mtyp", "mttl", "mdsc", "mbod"
        )
        rel = unique_tokens("kbmcmd")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        file_body = concept_body_from_file(ws.resolve(rel) / f"{ident}.md")
        outcome = mcp_show(ws, f"{ident}.md", rel)
        record = require_mcp_success_record(outcome, ident, typ, file_body)
        print(f"mcp trailing-.md id={show_record_field(record, 'id')!r}", flush=True)
        assert show_record_field(record, "id") == ident, (
            "membundle_show with trailing .md has no stripped identity "
            f"{ident!r}; record={record!r}"
        )


def test_mcp_show_missing_concept_is_tool_error_and_identifies_identity():
    """MCP not-found uses the tool-error channel and names the identity."""
    with workspace() as ws:
        ident, typ, title, desc, token, ghost = unique_tokens(
            "mn", "mtyp", "mttl", "mdsc", "mbod", "mgh"
        )
        rel = unique_tokens("kbmnf")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        file_body = concept_body_from_file(ws.resolve(rel) / f"{ident}.md")
        live = mcp_show(ws, ident, rel)
        require_mcp_success_record(live, ident, typ, file_body)
        missing = mcp_show(ws, ghost, rel)
        require_mcp_not_found(missing, ghost)
        print(f"mcp not-found ghost={ghost!r} reply={missing.reply!r}", flush=True)
        assert mcp_is_tool_error(missing.reply), (
            "membundle_show of a missing identity is not a tool-level failure "
            f"; reply={missing.reply!r}"
        )
        assert mcp_first_text(missing.reply).startswith(f"Concept '{ghost}' not found"), (
            f"membundle_show not-found does not identify {ghost!r}: "
            f"{mcp_first_text(missing.reply)!r}"
        )


def test_mcp_show_without_concept_id_does_not_succeed():
    """Missing concept_id is not a successful concept record."""
    with workspace() as ws:
        ident, typ, title, desc, token = unique_tokens(
            "mw", "mtyp", "mttl", "mdsc", "mbod"
        )
        rel = unique_tokens("kbmmiss")[0]
        write_bundle(
            ws,
            rel,
            [
                concept_spec(
                    ident,
                    concept_type=typ,
                    title=title,
                    description=desc,
                    body=f"{token}\n",
                )
            ],
        )
        file_body = concept_body_from_file(ws.resolve(rel) / f"{ident}.md")
        live = mcp_show(ws, ident, rel)
        require_mcp_success_record(live, ident, typ, file_body)
        missing = mcp_membundle_show(ws, {"bundle": rel}, request_id=11)
        print(
            f"missing concept_id reply={missing.reply!r}",
            flush=True,
        )
        assert missing.reply, "missing concept_id produced no JSON-RPC reply"
        assert mcp_is_tool_error(missing.reply) or mcp_is_invalid_params(
            missing.reply
        ), (
            "membundle_show without concept_id must be a tool error or JSON-RPC "
            "invalid-params; a successful tools/call (including an empty "
            f"result) is not a non-success inspection; reply={missing.reply!r}"
        )
        require_mcp_required_identity_non_success(missing)
        assert not mcp_is_success_record(missing, ident, typ, file_body), (
            "membundle_show without concept_id returned a successful concept record: "
            f"{missing.report_text!r}"
        )
