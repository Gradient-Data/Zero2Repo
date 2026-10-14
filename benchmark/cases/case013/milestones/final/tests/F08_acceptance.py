# feature: F08
"""Acceptance tests for MEMBUNDLE v0.2 validate and the producer gate (FP-08).

Public entries: the ``membundle validate`` command and the ``membundle_validate``
Model Context Protocol tool. Observations go through the sealed harness
``workspace`` / ``invoke`` / ``mcp_batch`` path. These tests do not
import Go packages, do not call internal Validate helpers, and do not
use ``membundle show`` / ``membundle search`` / ``membundle create`` / ``membundle init`` /
``membundle agents`` to judge results.
"""

from __future__ import annotations

import os

from _harness import utc_today_iso, workspace
from F01_helpers import tz_offset_where_local_date_differs
from F03_helpers import (
    assert_snapshot_helper_sees_write,
    markdown_link,
    unique_tokens,
)
from F08_helpers import (
    PASSING_AGENTS_TEXT,
    assert_both_pass,
    assert_conformant_gate_fail,
    assert_href_listed,
    assert_absent_from_loaded_concept_set,
    assert_href_not_listed,
    assert_identity_absent_from_string_values,
    assert_identity_listed,
    assert_identity_not_listed,
    assert_nonconformant,
    assert_numbers_later_greater,
    assert_numbers_not_greater,
    assert_finding_concerns,
    assert_more_findings,
    assert_report_includes_path_token,
    assert_requested_structured_validate_is_machine_readable,
    assert_warning_absent,
    fact_concept,
    mcp_validate,
    plant_ssot_links,
    require_cli_status_0,
    require_cli_status_1,
    require_cli_status_2,
    require_gate_finding_class,
    require_gate_finding_pair,
    require_hard_error_class,
    require_mcp_validate_both_pass,
    require_mcp_validate_report,
    require_mcp_validate_tool_error,
    require_warning_class,
    run_validate,
    run_validate_structured,
    seed_drift_bundle,
    seed_fact_identities,
    seed_validatable_bundle,
    utc_tomorrow,
    utc_yesterday,
)

def _gen_hex(n: int = 6) -> str:
    """Runtime-unique lowercase hex (the suite's own generated sample material)."""
    import uuid as _uuid

    return _uuid.uuid4().hex[:n]


# Generated per test process: a missing link target, and a concept
# description with an index listing text that contains it.
SAMPLE_MISSING_HREF = f"m{_gen_hex(7)}.md"
SAMPLE_DRIFT_DESC = f"Use K{_gen_hex(6)}"
SAMPLE_DRIFT_LISTING = f"{SAMPLE_DRIFT_DESC} for O{_gen_hex(5)}2."




def _rel() -> str:
    return unique_tokens("kb")[0]


def _seed_facts(ws, rel: str, identities: list[str], **kwargs):
    return seed_fact_identities(ws, rel, identities, **kwargs)


# ---------------------------------------------------------------------------
# A. Empty well-formed 0.2 bundle
# ---------------------------------------------------------------------------


def test_empty_well_formed_0_2_bundle_is_conformant_gate_pass():
    with workspace() as ws:
        rel = _rel()
        seed_validatable_bundle(ws, rel, [])
        human = run_validate(ws, rel)
        require_cli_status_0(human)
        result, payload = run_validate_structured(ws, rel)
        require_cli_status_0(result)
        assert_both_pass(payload)
        print("[F08] empty 0.2 both-pass", flush=True)


def test_mcp_empty_well_formed_0_2_bundle_is_conformant_gate_pass():
    with workspace() as ws:
        rel = _rel()
        seed_validatable_bundle(ws, rel, [])
        outcome = mcp_validate(ws, rel)
        payload = require_mcp_validate_report(outcome)
        assert_both_pass(payload)


# ---------------------------------------------------------------------------
# B. Hard-error conformance
# ---------------------------------------------------------------------------


def test_missing_or_empty_type_is_nonconformant_without_strict():
    with workspace() as ws:
        ident, twin, body = unique_tokens("id", "tw", "bd")
        rel_omit = unique_tokens("om")[0]
        seed_validatable_bundle(
            ws,
            rel_omit,
            [{"identity": ident, "frontmatter": {"title": twin}, "body": body}],
        )
        omit, omit_payload = run_validate_structured(ws, rel_omit)
        rel_empty = unique_tokens("em")[0]
        seed_validatable_bundle(
            ws,
            rel_empty,
            [{"identity": ident, "frontmatter": {"type": ""}, "body": body}],
        )
        empty, empty_payload = run_validate_structured(ws, rel_empty)
        rel_ok = unique_tokens("ok")[0]
        seed_validatable_bundle(ws, rel_ok, [fact_concept(ident, body=body)])
        repaired, repaired_payload = run_validate_structured(ws, rel_ok)
        require_hard_error_class(omit, repaired, structured_defective=omit_payload, concerns=f"{ident}.md")
        require_hard_error_class(empty, repaired, structured_defective=empty_payload, concerns=f"{ident}.md")
        assert_both_pass(repaired_payload)
        print("[F08] missing and empty type are nonconformant", flush=True)


def test_type_fact_with_no_other_fields_is_conformant():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel = _rel()
        seed_validatable_bundle(ws, rel, [fact_concept(ident)])
        loose, payload = run_validate_structured(ws, rel)
        require_cli_status_0(loose)
        assert_both_pass(payload)
        rel_empty = unique_tokens("z0")[0]
        seed_validatable_bundle(ws, rel_empty, [])
        empty, empty_payload = run_validate_structured(ws, rel_empty)
        require_cli_status_0(empty)
        assert_numbers_later_greater(empty_payload, payload)
        strict, strict_payload = run_validate_structured(ws, rel, strict=True)
        require_cli_status_0(strict)
        assert_both_pass(strict_payload)
        assert_numbers_later_greater(empty_payload, strict_payload)


def test_type_fact_generated_sample_has_runtime_twin():
    with workspace() as ws:
        sample, twin = unique_tokens("sm", "tw")
        rel_a = unique_tokens("a")[0]
        rel_b = unique_tokens("b")[0]
        seed_validatable_bundle(ws, rel_a, [fact_concept(sample)])
        seed_validatable_bundle(ws, rel_b, [fact_concept(twin)])
        a, pa = run_validate_structured(ws, rel_a)
        b, pb = run_validate_structured(ws, rel_b)
        require_cli_status_0(a)
        require_cli_status_0(b)
        assert_both_pass(pa)
        assert_both_pass(pb)
        rel_empty = unique_tokens("z0")[0]
        seed_validatable_bundle(ws, rel_empty, [])
        empty, empty_payload = run_validate_structured(ws, rel_empty)
        require_cli_status_0(empty)
        assert_numbers_later_greater(empty_payload, pa)
        assert_numbers_later_greater(empty_payload, pb)


def test_missing_yaml_frontmatter_is_hard_error():
    with workspace() as ws:
        ident, token = unique_tokens("id", "tk")
        rel_bad = unique_tokens("bd")[0]
        seed_validatable_bundle(
            ws,
            rel_bad,
            [{"identity": ident, "frontmatter": None, "body": token}],
        )
        bad, bad_payload = run_validate_structured(ws, rel_bad)
        rel_ok = unique_tokens("ok")[0]
        seed_validatable_bundle(ws, rel_ok, [fact_concept(ident, body=token)])
        repaired, repaired_payload = run_validate_structured(ws, rel_ok)
        require_hard_error_class(
            bad, repaired, structured_defective=bad_payload, concerns=f"{ident}.md"
        )
        assert_both_pass(repaired_payload)


def test_readme_without_frontmatter_is_hard_error():
    with workspace() as ws:
        token = unique_tokens("tk")[0]
        rel_bad = unique_tokens("bd")[0]
        seed_validatable_bundle(
            ws,
            rel_bad,
            [{"identity": "README", "frontmatter": None, "body": token}],
        )
        bad, bad_payload = run_validate_structured(ws, rel_bad)
        rel_ok = unique_tokens("ok")[0]
        seed_validatable_bundle(ws, rel_ok, [fact_concept("README", body=token)])
        repaired, _ = run_validate_structured(ws, rel_ok)
        require_hard_error_class(
            bad, repaired, structured_defective=bad_payload, concerns="README.md"
        )


def test_readme_with_type_is_conformant():
    with workspace() as ws:
        rel = _rel()
        seed_validatable_bundle(ws, rel, [fact_concept("README")])
        result, payload = run_validate_structured(ws, rel, strict=True)
        require_cli_status_0(result)
        assert_both_pass(payload)
        rel_empty = unique_tokens("z0")[0]
        seed_validatable_bundle(ws, rel_empty, [])
        empty, empty_payload = run_validate_structured(ws, rel_empty)
        require_cli_status_0(empty)
        assert_numbers_later_greater(empty_payload, payload)


def test_whitespace_only_title_is_hard_error():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_bad = unique_tokens("bd")[0]
        seed_validatable_bundle(
            ws,
            rel_bad,
            [
                {
                    "identity": ident,
                    "frontmatter": {"type": "Fact", "title": "   "},
                    "body": "body\n",
                }
            ],
        )
        bad, bad_payload = run_validate_structured(ws, rel_bad)
        rel_ok = unique_tokens("ok")[0]
        seed_validatable_bundle(ws, rel_ok, [fact_concept(ident)])
        repaired, _ = run_validate_structured(ws, rel_ok)
        require_hard_error_class(
            bad, repaired, structured_defective=bad_payload, concerns=f"{ident}.md"
        )


def test_mcp_missing_type_is_nonconformant_not_mixed_gate_fail():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_bad = unique_tokens("bd")[0]
        seed_validatable_bundle(
            ws,
            rel_bad,
            [{"identity": ident, "frontmatter": {"title": ident}, "body": "body\n"}],
        )
        rel_ok = unique_tokens("ok")[0]
        seed_validatable_bundle(ws, rel_ok, [fact_concept(ident)])
        bad = mcp_validate(ws, rel_bad)
        ok = mcp_validate(ws, rel_ok)
        bad_payload = require_mcp_validate_report(bad)
        ok_payload = require_mcp_validate_report(ok)
        assert_nonconformant(bad_payload, concerns=f"{ident}.md")
        assert_both_pass(ok_payload)


# ---------------------------------------------------------------------------
# C. What is loaded
# ---------------------------------------------------------------------------


def test_concept_count_tracks_loaded_non_reserved_markdown():
    with workspace() as ws:
        a, b = unique_tokens("a", "b")
        rel0, rel1, rel2 = unique_tokens("z0", "z1", "z2")
        seed_validatable_bundle(ws, rel0, [])
        seed_validatable_bundle(ws, rel1, [fact_concept(a)])
        seed_validatable_bundle(ws, rel2, [fact_concept(a), fact_concept(b)])
        r0, p0 = run_validate_structured(ws, rel0)
        r1, p1 = run_validate_structured(ws, rel1)
        r2, p2 = run_validate_structured(ws, rel2)
        require_cli_status_0(r0)
        require_cli_status_0(r1)
        require_cli_status_0(r2)
        assert_numbers_later_greater(p0, p1)
        assert_numbers_later_greater(p1, p2)
        assert_identity_listed(p2, a)
        assert_identity_listed(p2, b)
        assert_identity_not_listed(p0, a)
        assert_identity_not_listed(p0, b)


def test_root_agents_log_index_and_nested_index_are_not_concepts():
    with workspace() as ws:
        ident, other = unique_tokens("id", "ot")
        rel = _rel()
        seed_validatable_bundle(
            ws, rel, [fact_concept(ident), fact_concept(other)]
        )
        baseline_run, baseline = run_validate_structured(ws, rel)
        require_cli_status_0(baseline_run)
        assert_both_pass(baseline)
        assert_identity_listed(baseline, ident)
        assert_identity_listed(baseline, other)
        (ws.path / rel / "AGENTS.md").write_text(PASSING_AGENTS_TEXT, encoding="utf-8")
        agents_run, with_agents = run_validate_structured(ws, rel)
        require_cli_status_0(agents_run)
        assert_both_pass(with_agents)
        assert_identity_listed(with_agents, ident)
        assert_identity_listed(with_agents, other)
        assert_identity_absent_from_string_values(with_agents, "AGENTS")
        assert_numbers_not_greater(baseline, with_agents)
        nested = ws.path / rel / "dir"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "index.md").write_text("# nested\n", encoding="utf-8")
        index_run, with_index = run_validate_structured(ws, rel)
        require_cli_status_0(index_run)
        assert_both_pass(with_index)
        assert_identity_listed(with_index, ident)
        assert_identity_listed(with_index, other)
        assert_identity_absent_from_string_values(with_index, "AGENTS")
        assert_identity_absent_from_string_values(with_index, "dir/index")
        assert_numbers_not_greater(baseline, with_index)
        print("[F08] reserved files did not increase walked integers", flush=True)


def test_every_log_md_is_excluded_nested_agents_md_is_a_concept():
    with workspace() as ws:
        ident, nested_agents = unique_tokens("id", "na")
        rel = _rel()
        seed_validatable_bundle(ws, rel, [fact_concept(ident)])
        nested = ws.path / rel / "dir"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "log.md").write_text(
            "---\ntype: Fact\n---\n\nnested-log\n", encoding="utf-8"
        )
        _, with_log = run_validate_structured(ws, rel)
        assert_identity_not_listed(with_log, "dir/log")
        (nested / "AGENTS.md").write_text(
            "---\ntype: Fact\n---\n\n" + nested_agents + "\n", encoding="utf-8"
        )
        _, with_nested = run_validate_structured(ws, rel)
        assert_identity_listed(with_nested, "dir/AGENTS")
        assert_identity_listed(with_nested, ident)
        assert_numbers_later_greater(with_log, with_nested)


def test_hidden_node_modules_and_non_markdown_are_not_loaded():
    with workspace() as ws:
        visible, other, hid_file, hid_dir, nm_root, nm_nest, txt = unique_tokens(
            "vis", "oth", "hf", "hd", "nr", "nn", "tx"
        )
        rel = _rel()
        rel_md = unique_tokens("md")[0]
        concepts = [
            fact_concept(visible, body=visible),
            fact_concept(other, body=other),
        ]
        seed_validatable_bundle(ws, rel, concepts)
        seed_validatable_bundle(ws, rel_md, concepts)
        root = ws.path / rel
        (root / f".{hid_file}.md").write_text(
            f"---\ntype: Fact\n---\n\n{hid_file}\n", encoding="utf-8"
        )
        hidden = root / ".hidden"
        hidden.mkdir()
        (hidden / f"{hid_dir}.md").write_text(
            f"---\ntype: Fact\n---\n\n{hid_dir}\n", encoding="utf-8"
        )
        (root / "node_modules").mkdir()
        (root / "node_modules" / f"{nm_root}.md").write_text(
            f"---\ntype: Fact\n---\n\n{nm_root}\n", encoding="utf-8"
        )
        vendor = root / "vendor" / "node_modules"
        vendor.mkdir(parents=True)
        (vendor / f"{nm_nest}.md").write_text(
            f"---\ntype: Fact\n---\n\n{nm_nest}\n", encoding="utf-8"
        )
        txt_name = f"{txt}.txt"
        (root / txt_name).write_text(
            "---\ntype: Fact\n---\n\nnot-markdown\n", encoding="utf-8"
        )
        md_run, md_payload = run_validate_structured(ws, rel_md)
        result, payload = run_validate_structured(ws, rel)
        require_cli_status_0(md_run)
        require_cli_status_0(result)
        assert_identity_listed(payload, visible)
        assert_identity_listed(payload, other)
        for skipped in (
            f".{hid_file}",
            f".hidden/{hid_dir}",
            f"node_modules/{nm_root}",
            f"vendor/node_modules/{nm_nest}",
        ):
            assert_identity_not_listed(payload, skipped)
        assert_absent_from_loaded_concept_set(
            payload, txt_name, markdown_only=md_payload
        )


def test_declared_version_0_2_is_reported_versus_undeclared():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_d, rel_u = unique_tokens("dv", "uv")
        seed_validatable_bundle(
            ws, rel_d, [fact_concept(ident)], membundle_version="0.2"
        )
        seed_validatable_bundle(
            ws, rel_u, [fact_concept(ident)], membundle_version=None
        )
        declared, d_payload = run_validate_structured(ws, rel_d)
        undeclared, u_payload = run_validate_structured(ws, rel_u)
        require_cli_status_0(declared)
        require_cli_status_0(undeclared)
        print(f"[F08] declared={d_payload!r} undeclared={u_payload!r}", flush=True)
        assert d_payload.get("declared_version") == "0.2", (
            f"declared_version is not '0.2' for a 0.2 bundle: {d_payload!r}"
        )
        assert "declared_version" not in u_payload, (
            f"undeclared bundle reports a declared_version: {u_payload!r}"
        )


# ---------------------------------------------------------------------------
# D. Advisory warnings
# ---------------------------------------------------------------------------


def test_nested_index_with_frontmatter_is_warning_under_strict():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        seed_validatable_bundle(ws, rel_bad, [fact_concept(ident)])
        seed_validatable_bundle(ws, rel_ok, [fact_concept(ident)])
        (ws.path / rel_bad / "dir").mkdir()
        (ws.path / rel_bad / "dir" / "index.md").write_text(
            "---\nmembundle_version: 0.2\n---\n\n# nested\n", encoding="utf-8"
        )
        (ws.path / rel_ok / "dir").mkdir()
        (ws.path / rel_ok / "dir" / "index.md").write_text("# nested\n", encoding="utf-8")
        defective = run_validate(ws, rel_bad, strict=True)
        repaired = run_validate(ws, rel_ok, strict=True)
        require_warning_class(
            defective,
            repaired,
            concerns="dir/index.md",
        )
        assert_warning_absent(repaired, repaired, concerns="dir/index.md")


def test_two_hash_non_iso_log_heading_is_warning_single_hash_is_not():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_bad, rel_iso, rel_hash = unique_tokens("bd", "iso", "hs")
        for rel, log in (
            (rel_bad, "## Monday\n\n- seed\n"),
            (rel_iso, "## 2020-01-01\n\n- seed\n"),
            (rel_hash, "# Monday\n\n- seed\n"),
        ):
            seed_validatable_bundle(
                ws, rel, [fact_concept(ident)], log_markdown=log
            )
        defective = run_validate(ws, rel_bad, strict=True)
        iso = run_validate(ws, rel_iso, strict=True)
        single = run_validate(ws, rel_hash, strict=True)
        require_warning_class(
            defective,
            iso,
            concerns="log.md",
        )
        assert_warning_absent(single, iso, concerns="log.md")


def test_unmatched_footnote_warns_only_when_a_sources_id_is_listed():
    with workspace() as ws:
        ident, src_id, fn_key, resource = unique_tokens("id", "src", "fn", "rs")
        sources = [{"id": src_id, "resource": f"https://example.invalid/{resource}"}]
        rel_warn, rel_none, rel_match = unique_tokens("w", "n", "m")
        seed_validatable_bundle(
            ws,
            rel_warn,
            [
                fact_concept(
                    ident,
                    body=f"See [^{fn_key}].\n",
                    extra={"sources": sources},
                )
            ],
        )
        seed_validatable_bundle(
            ws,
            rel_none,
            [fact_concept(ident, body=f"See [^{fn_key}].\n")],
        )
        seed_validatable_bundle(
            ws,
            rel_match,
            [
                fact_concept(
                    ident,
                    body=f"See [^{src_id}].\n",
                    extra={"sources": sources},
                )
            ],
        )
        warn = run_validate(ws, rel_warn, strict=True)
        none = run_validate(ws, rel_none, strict=True)
        match = run_validate(ws, rel_match, strict=True)
        require_warning_class(
            warn,
            match,
            concerns=f"{ident}.md",
        )
        assert_warning_absent(none, match, concerns=f"{ident}.md")


def test_fenced_footnote_is_not_an_unmatched_warning():
    with workspace() as ws:
        ident, src_id, fn_key, resource = unique_tokens("id", "src", "fn", "rs")
        sources = [{"id": src_id, "resource": f"https://example.invalid/{resource}"}]
        rel_fence, rel_live, rel_ok = unique_tokens("fc", "lv", "ok")
        seed_validatable_bundle(
            ws,
            rel_fence,
            [
                fact_concept(
                    ident,
                    body=f"```\n[^{fn_key}]\n```\n",
                    extra={"sources": sources},
                )
            ],
        )
        seed_validatable_bundle(
            ws,
            rel_live,
            [
                fact_concept(
                    ident,
                    body=f"See [^{fn_key}].\n",
                    extra={"sources": sources},
                )
            ],
        )
        seed_validatable_bundle(
            ws,
            rel_ok,
            [
                fact_concept(
                    ident,
                    body=f"See [^{src_id}].\n",
                    extra={"sources": sources},
                )
            ],
        )
        fenced = run_validate(ws, rel_fence, strict=True)
        live = run_validate(ws, rel_live, strict=True)
        ok = run_validate(ws, rel_ok, strict=True)
        require_cli_status_0(fenced)
        require_warning_class(
            live,
            ok,
            concerns=f"{ident}.md",
        )
        assert_warning_absent(fenced, ok, concerns=f"{ident}.md")


def test_invalid_actor_on_generated_verified_and_sources_author_is_warning():
    with workspace() as ws:
        ident, resource = unique_tokens("id", "rs")
        invalid = "not an actor"
        valid_gen = {"by": "agent/cli", "at": "2020-06-15T12:00:00Z"}
        valid_ver = [{"by": "human:alice", "at": "2020-06-16T12:00:00Z"}]
        cases = [
            ("generated", {"generated": {"by": invalid, "at": "2020-06-15T12:00:00Z"}}, {"generated": valid_gen}),
            (
                "verified",
                {
                    "generated": valid_gen,
                    "verified": [{"by": invalid, "at": "2020-06-16T12:00:00Z"}],
                },
                {"generated": valid_gen, "verified": valid_ver},
            ),
            (
                "sources.author",
                {
                    "sources": [
                        {
                            "id": "s1",
                            "resource": f"https://example.invalid/{resource}",
                            "author": invalid,
                        }
                    ]
                },
                {
                    "sources": [
                        {
                            "id": "s1",
                            "resource": f"https://example.invalid/{resource}",
                            "author": "human:alice",
                        }
                    ]
                },
            ),
        ]
        for label, bad_extra, good_extra in cases:
            rel_bad, rel_ok = unique_tokens("bd", "ok")
            seed_validatable_bundle(
                ws, rel_bad, [fact_concept(ident, extra=bad_extra)]
            )
            seed_validatable_bundle(
                ws, rel_ok, [fact_concept(ident, extra=good_extra)]
            )
            defective = run_validate(ws, rel_bad, strict=True)
            repaired = run_validate(ws, rel_ok, strict=True)
            print(f"[F08] invalid actor field={label}", flush=True)
            require_warning_class(
            defective,
            repaired,
            concerns=f"{ident}.md",
        )


def test_verified_without_by_is_warning():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_bad, rel_ok, rel_gate = unique_tokens("bd", "ok", "gt")
        stamp = "2020-06-16T12:00:00Z"
        gen_stamp = "2020-06-15T12:00:00Z"
        seed_validatable_bundle(
            ws,
            rel_bad,
            [fact_concept(ident, extra={"verified": [{"at": stamp}]})],
        )
        seed_validatable_bundle(
            ws,
            rel_ok,
            [
                fact_concept(
                    ident,
                    extra={"verified": [{"by": "human:alice", "at": stamp}]},
                )
            ],
        )
        seed_validatable_bundle(
            ws,
            rel_gate,
            [fact_concept(ident, extra={"generated": {"at": gen_stamp}})],
        )
        defective = run_validate(ws, rel_bad, strict=True)
        repaired = run_validate(ws, rel_ok, strict=True)
        print("[F08] verified entry with no by is a warning", flush=True)
        require_warning_class(
            defective,
            repaired,
            concerns=f"{ident}.md",
        )
        bad_st, bad_payload = run_validate_structured(ws, rel_bad, strict=True)
        ok_st, ok_payload = run_validate_structured(ws, rel_ok, strict=True)
        require_cli_status_0(bad_st)
        assert_both_pass(bad_payload)
        require_cli_status_0(ok_st)
        assert_both_pass(ok_payload)
        assert_more_findings(bad_payload, ok_payload, "warnings", f"{ident}.md")
        gate, gate_payload = run_validate_structured(ws, rel_gate, strict=True)
        require_cli_status_1(gate)
        assert_conformant_gate_fail(gate_payload)
        assert_finding_concerns(gate_payload, "gate_findings", f"{ident}.md")
        mcp_bad = mcp_validate(ws, rel_bad)
        mcp_ok = mcp_validate(ws, rel_ok)
        mcp_bad_payload = require_mcp_validate_report(mcp_bad)
        mcp_ok_payload = require_mcp_validate_report(mcp_ok)
        assert_both_pass(mcp_bad_payload)
        assert_both_pass(mcp_ok_payload)
        assert_more_findings(
            mcp_bad_payload, mcp_ok_payload, "warnings", f"{ident}.md"
        )


def test_missing_generated_at_is_warning():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        stamp = "2020-06-15T12:00:00Z"
        seed_validatable_bundle(
            ws,
            rel_bad,
            [fact_concept(ident, extra={"generated": {"by": "agent/cli"}})],
        )
        seed_validatable_bundle(
            ws,
            rel_ok,
            [
                fact_concept(
                    ident,
                    extra={"generated": {"by": "agent/cli", "at": stamp}},
                )
            ],
        )
        defective = run_validate(ws, rel_bad, strict=True)
        repaired = run_validate(ws, rel_ok, strict=True)
        print("[F08] missing generated.at", flush=True)
        require_warning_class(
            defective,
            repaired,
            concerns=f"{ident}.md",
        )


def test_unparseable_generated_at_is_warning():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        stamp = "2020-06-15T12:00:00Z"
        seed_validatable_bundle(
            ws,
            rel_bad,
            [
                fact_concept(
                    ident,
                    extra={
                        "generated": {"by": "agent/cli", "at": "not-a-timestamp"}
                    },
                )
            ],
        )
        seed_validatable_bundle(
            ws,
            rel_ok,
            [
                fact_concept(
                    ident,
                    extra={"generated": {"by": "agent/cli", "at": stamp}},
                )
            ],
        )
        defective = run_validate(ws, rel_bad, strict=True)
        repaired = run_validate(ws, rel_ok, strict=True)
        print("[F08] unparseable generated.at", flush=True)
        require_warning_class(
            defective,
            repaired,
            concerns=f"{ident}.md",
        )


def test_missing_verified_at_is_warning():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        stamp = "2020-06-16T12:00:00Z"
        seed_validatable_bundle(
            ws,
            rel_bad,
            [fact_concept(ident, extra={"verified": [{"by": "human:alice"}]})],
        )
        seed_validatable_bundle(
            ws,
            rel_ok,
            [
                fact_concept(
                    ident,
                    extra={
                        "verified": [{"by": "human:alice", "at": stamp}]
                    },
                )
            ],
        )
        defective = run_validate(ws, rel_bad, strict=True)
        repaired = run_validate(ws, rel_ok, strict=True)
        print("[F08] missing verified.at", flush=True)
        require_warning_class(
            defective,
            repaired,
            concerns=f"{ident}.md",
        )


def test_unparseable_verified_at_is_warning():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_bad, rel_ok, rel_gate = unique_tokens("bd", "ok", "gt")
        stamp = "2020-06-16T12:00:00Z"
        earlier = "2020-01-01T00:00:00Z"
        later = "2020-06-15T12:00:00Z"
        bad_at = unique_tokens("ts")[0]
        seed_validatable_bundle(
            ws,
            rel_bad,
            [
                fact_concept(
                    ident,
                    extra={"verified": [{"by": "human:alice", "at": bad_at}]},
                )
            ],
        )
        seed_validatable_bundle(
            ws,
            rel_ok,
            [
                fact_concept(
                    ident,
                    extra={"verified": [{"by": "human:alice", "at": stamp}]},
                )
            ],
        )
        seed_validatable_bundle(
            ws,
            rel_gate,
            [
                fact_concept(
                    ident,
                    extra={
                        "generated": {"by": "agent/cli", "at": later},
                        "verified": [{"by": "human:alice", "at": earlier}],
                    },
                )
            ],
        )
        defective = run_validate(ws, rel_bad, strict=True)
        repaired = run_validate(ws, rel_ok, strict=True)
        print("[F08] unparseable verified.at is a warning", flush=True)
        require_warning_class(
            defective,
            repaired,
            concerns=f"{ident}.md",
        )
        bad_st, bad_payload = run_validate_structured(ws, rel_bad, strict=True)
        ok_st, ok_payload = run_validate_structured(ws, rel_ok, strict=True)
        require_cli_status_0(bad_st)
        assert_both_pass(bad_payload)
        require_cli_status_0(ok_st)
        assert_both_pass(ok_payload)
        assert_more_findings(bad_payload, ok_payload, "warnings", f"{ident}.md")
        gate, gate_payload = run_validate_structured(ws, rel_gate, strict=True)
        require_cli_status_1(gate)
        assert_conformant_gate_fail(gate_payload)
        assert_finding_concerns(gate_payload, "gate_findings", f"{ident}.md")
        mcp_bad = mcp_validate(ws, rel_bad)
        mcp_ok = mcp_validate(ws, rel_ok)
        mcp_bad_payload = require_mcp_validate_report(mcp_bad)
        mcp_ok_payload = require_mcp_validate_report(mcp_ok)
        assert_both_pass(mcp_bad_payload)
        assert_both_pass(mcp_ok_payload)
        assert_more_findings(
            mcp_bad_payload, mcp_ok_payload, "warnings", f"{ident}.md"
        )


def test_sources_last_modified_not_yyyy_mm_dd_is_warning():
    with workspace() as ws:
        ident, resource = unique_tokens("id", "rs")
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        bad = {
            "sources": [
                {
                    "id": "s1",
                    "resource": f"https://example.invalid/{resource}",
                    "last_modified": "not-a-date",
                }
            ]
        }
        good = {
            "sources": [
                {
                    "id": "s1",
                    "resource": f"https://example.invalid/{resource}",
                    "last_modified": "2020-01-01",
                }
            ]
        }
        seed_validatable_bundle(ws, rel_bad, [fact_concept(ident, extra=bad)])
        seed_validatable_bundle(ws, rel_ok, [fact_concept(ident, extra=good)])
        defective = run_validate(ws, rel_bad, strict=True)
        repaired = run_validate(ws, rel_ok, strict=True)
        require_warning_class(
            defective,
            repaired,
            concerns=f"{ident}.md",
        )


def test_malformed_stale_after_is_warning_not_stale_count():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        yesterday = utc_yesterday()
        tomorrow = utc_tomorrow()
        rel_bad, rel_y, rel_t = unique_tokens("bd", "yd", "tm")
        seed_validatable_bundle(
            ws, rel_bad, [fact_concept(ident, extra={"stale_after": "not-a-date"})]
        )
        seed_validatable_bundle(
            ws, rel_y, [fact_concept(ident, extra={"stale_after": yesterday})]
        )
        seed_validatable_bundle(
            ws, rel_t, [fact_concept(ident, extra={"stale_after": tomorrow})]
        )
        malformed = run_validate(ws, rel_bad, strict=True)
        tomorrow_run = run_validate(ws, rel_t, strict=True)
        require_warning_class(
            malformed,
            tomorrow_run,
            concerns=f"{ident}.md",
        )
        m_stale, m_payload = run_validate_structured(ws, rel_bad, stale=True)
        y_stale, y_payload = run_validate_structured(ws, rel_y, stale=True)
        require_cli_status_0(m_stale)
        require_cli_status_1(y_stale)
        assert_both_pass(m_payload)
        assert_conformant_gate_fail(y_payload)
        assert_numbers_later_greater(m_payload, y_payload, field="stale_count")


# ---------------------------------------------------------------------------
# E. Producer-gate findings
# ---------------------------------------------------------------------------


def test_timestamp_field_is_gate_finding_strict_fails_gate():
    with workspace() as ws:
        ident, leftover = unique_tokens("id", "ts")
        payload = require_gate_finding_pair(
            ws, ident, {"timestamp": leftover}, {}
        )
        assert_conformant_gate_fail(payload)


def test_mcp_timestamp_finding_fails_default_producer_gate():
    with workspace() as ws:
        ident, leftover = unique_tokens("id", "ts")
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        seed_validatable_bundle(
            ws, rel_bad, [fact_concept(ident, extra={"timestamp": leftover})]
        )
        seed_validatable_bundle(ws, rel_ok, [fact_concept(ident)])
        fail = mcp_validate(ws, rel_bad)
        off = mcp_validate(ws, rel_bad, strict=False)
        ok = mcp_validate(ws, rel_ok)
        fail_payload = require_mcp_validate_report(fail)
        off_payload = require_mcp_validate_report(off)
        ok_payload = require_mcp_validate_report(ok)
        assert_conformant_gate_fail(fail_payload)
        assert_both_pass(off_payload)
        assert_both_pass(ok_payload)
        assert_finding_concerns(fail_payload, "gate_findings", f"{ident}.md")
        assert_more_findings(off_payload, ok_payload, "gate_findings", f"{ident}.md")


def test_single_hash_citations_outside_fences_is_gate_finding():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        seed_validatable_bundle(
            ws, rel_bad, [fact_concept(ident, body="# Citations\n\ntext\n")]
        )
        seed_validatable_bundle(ws, rel_ok, [fact_concept(ident, body="text\n")])
        without = run_validate(ws, rel_bad)
        with_strict, payload = run_validate_structured(ws, rel_bad, strict=True)
        repaired, _ = run_validate_structured(ws, rel_ok, strict=True)
        require_gate_finding_class(
            without,
            with_strict,
            repaired,
            structured_strict=payload,
            concerns=f"{ident}.md",
        )


def test_deeper_setext_and_fenced_citations_are_not_gate_findings():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        bodies = {
            "deeper": "## Citations\n\ntext\n",
            "setext": "Citations\n=========\n\ntext\n",
            "fenced": "```\n# Citations\n```\n",
        }
        rel_bad = unique_tokens("bd")[0]
        seed_validatable_bundle(
            ws, rel_bad, [fact_concept(ident, body="# Citations\n\ntext\n")]
        )
        bad, bad_payload = run_validate_structured(ws, rel_bad, strict=True)
        require_cli_status_1(bad)
        assert_conformant_gate_fail(bad_payload)
        rel_ok = unique_tokens("ok")[0]
        seed_validatable_bundle(ws, rel_ok, [fact_concept(ident, body="text\n")])
        repaired, repaired_payload = run_validate_structured(ws, rel_ok, strict=True)
        require_cli_status_0(repaired)
        assert_both_pass(repaired_payload)
        for label, body in bodies.items():
            rel = unique_tokens("c")[0]
            seed_validatable_bundle(ws, rel, [fact_concept(ident, body=body)])
            cli, payload = run_validate_structured(ws, rel, strict=True)
            require_cli_status_0(cli)
            assert_both_pass(payload)
            mcp_payload = require_mcp_validate_report(mcp_validate(ws, rel))
            assert_both_pass(mcp_payload)
            print(f"[F08] citations non-finding {label}", flush=True)


def test_sources_without_resource_is_gate_finding():
    with workspace() as ws:
        ident, sid = unique_tokens("id", "sid")
        payload = require_gate_finding_pair(
            ws,
            ident,
            {"sources": [{"id": sid}]},
            {"sources": [{"id": sid, "resource": "https://example.invalid/x"}]},
        )
        assert_conformant_gate_fail(payload)


def test_generated_without_by_is_gate_finding_invalid_by_is_not():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        payload = require_gate_finding_pair(
            ws,
            ident,
            {"generated": {"at": "2020-06-15T12:00:00Z"}},
            {"generated": {"by": "agent/cli", "at": "2020-06-15T12:00:00Z"}},
        )
        assert_conformant_gate_fail(payload)
        rel_invalid = unique_tokens("iv")[0]
        seed_validatable_bundle(
            ws,
            rel_invalid,
            [
                fact_concept(
                    ident,
                    extra={
                        "generated": {
                            "by": "not an actor",
                            "at": "2020-06-15T12:00:00Z",
                        }
                    },
                )
            ],
        )
        invalid_strict = run_validate(ws, rel_invalid, strict=True)
        require_cli_status_0(invalid_strict)


def test_verified_at_before_generated_at_is_gate_finding():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        earlier = "2020-01-01T00:00:00Z"
        later = "2020-06-15T12:00:00Z"
        payload = require_gate_finding_pair(
            ws,
            ident,
            {
                "generated": {"by": "agent/cli", "at": later},
                "verified": [{"by": "human:alice", "at": earlier}],
            },
            {
                "generated": {"by": "agent/cli", "at": earlier},
                "verified": [{"by": "human:alice", "at": later}],
            },
        )
        assert_conformant_gate_fail(payload)


def test_present_governance_outside_closed_set_is_gate_finding_omit_is_not():
    with workspace() as ws:
        ident, bogus = unique_tokens("id", "gv")
        payload = require_gate_finding_pair(ws, ident, {"governance": bogus}, {})
        assert_conformant_gate_fail(payload)
        rel_omit = unique_tokens("om")[0]
        seed_validatable_bundle(ws, rel_omit, [fact_concept(ident)])
        omit, payload = run_validate_structured(ws, rel_omit, strict=True)
        require_cli_status_0(omit)
        assert_both_pass(payload)


def test_constraint_hold_context_including_constraint_casefold_are_not_gate_findings():
    with workspace() as ws:
        ident, bogus = unique_tokens("id", "gv")
        rel_bad = unique_tokens("bd")[0]
        seed_validatable_bundle(
            ws, rel_bad, [fact_concept(ident, extra={"governance": bogus})]
        )
        bad, bad_payload = run_validate_structured(ws, rel_bad, strict=True)
        require_cli_status_1(bad)
        assert_conformant_gate_fail(bad_payload)
        for value in ("constraint", "hold", "context", "Constraint"):
            rel = unique_tokens("g")[0]
            seed_validatable_bundle(
                ws, rel, [fact_concept(ident, extra={"governance": value})]
            )
            result, payload = run_validate_structured(ws, rel, strict=True)
            require_cli_status_0(result)
            assert_both_pass(payload)
            print(f"[F08] governance {value!r} is not a finding", flush=True)


def test_present_status_outside_closed_set_is_gate_finding_omit_and_draft_stable_deprecated_are_not():
    with workspace() as ws:
        ident, bogus = unique_tokens("id", "st")
        payload = require_gate_finding_pair(ws, ident, {"status": bogus}, {})
        assert_conformant_gate_fail(payload)
        for value in (None, "draft", "stable", "deprecated"):
            rel = unique_tokens("s")[0]
            extra = {} if value is None else {"status": value}
            seed_validatable_bundle(ws, rel, [fact_concept(ident, extra=extra)])
            result, payload = run_validate_structured(ws, rel, strict=True)
            require_cli_status_0(result)
            assert_both_pass(payload)


def test_status_values_are_compared_ignoring_letter_case():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        for value in ("Draft", "STABLE", "Deprecated"):
            rel = unique_tokens("s")[0]
            seed_validatable_bundle(ws, rel, [fact_concept(ident, extra={"status": value})])
            result, payload = run_validate_structured(ws, rel, strict=True)
            require_cli_status_0(result)
            assert_both_pass(payload)


def test_absolute_and_dotdot_code_refs_are_gate_findings():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        abs_payload = require_gate_finding_pair(
            ws, ident, {"code_refs": ["/tmp/absolute.go"]}, {"code_refs": ["inside.go"]}
        )
        assert_conformant_gate_fail(abs_payload)
        rel_dot = unique_tokens("dd")[0]
        seed_validatable_bundle(
            ws, rel_dot, [fact_concept(ident, extra={"code_refs": ["../secret.go"]})]
        )
        rel_ok = unique_tokens("ok")[0]
        seed_validatable_bundle(
            ws, rel_ok, [fact_concept(ident, extra={"code_refs": ["inside.go"]})]
        )
        (ws.path / rel_ok / "inside.go").write_text("package x\n", encoding="utf-8")
        without = run_validate(ws, rel_dot)
        with_strict, payload = run_validate_structured(ws, rel_dot, strict=True)
        repaired, _ = run_validate_structured(ws, rel_ok, strict=True)
        require_gate_finding_class(
            without,
            with_strict,
            repaired,
            structured_strict=payload,
            concerns=f"{ident}.md",
        )


def test_relative_in_bundle_code_refs_is_not_gate_finding():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_ok, rel_abs = unique_tokens("ok", "ab")
        seed_validatable_bundle(
            ws, rel_ok, [fact_concept(ident, extra={"code_refs": ["inside.go"]})]
        )
        (ws.path / rel_ok / "inside.go").write_text("package x\n", encoding="utf-8")
        seed_validatable_bundle(
            ws,
            rel_abs,
            [fact_concept(ident, extra={"code_refs": ["/tmp/absolute.go"]})],
        )
        ok, ok_payload = run_validate_structured(ws, rel_ok, strict=True)
        bad, bad_payload = run_validate_structured(ws, rel_abs, strict=True)
        require_cli_status_0(ok)
        assert_both_pass(ok_payload)
        require_cli_status_1(bad)
        assert_conformant_gate_fail(bad_payload)


def test_gate_findings_are_not_fatal_when_version_is_not_0_2():
    with workspace() as ws:
        ident, leftover = unique_tokens("id", "ts")
        rel_decl, rel_omit, rel_02 = unique_tokens("dv", "om", "v2")
        seed_validatable_bundle(
            ws,
            rel_decl,
            [fact_concept(ident, extra={"timestamp": leftover})],
            membundle_version="0.1",
        )
        seed_validatable_bundle(
            ws,
            rel_omit,
            [fact_concept(ident, extra={"timestamp": leftover})],
            membundle_version=None,
        )
        seed_validatable_bundle(
            ws,
            rel_02,
            [fact_concept(ident, extra={"timestamp": leftover})],
            membundle_version="0.2",
        )
        declared, d_payload = run_validate_structured(ws, rel_decl, strict=True)
        omitted, o_payload = run_validate_structured(ws, rel_omit, strict=True)
        fail_02, fail_payload = run_validate_structured(ws, rel_02, strict=True)
        require_cli_status_0(declared)
        assert_both_pass(d_payload)
        require_cli_status_0(omitted)
        assert_both_pass(o_payload)
        require_cli_status_1(fail_02)
        assert_conformant_gate_fail(fail_payload)
        assert_finding_concerns(fail_payload, "gate_findings", f"{ident}.md")


# ---------------------------------------------------------------------------
# F. Connectivity
# ---------------------------------------------------------------------------


def test_two_unlinked_concepts_are_orphans_strict_fails_gate_without_strict_passes():
    with workspace() as ws:
        a, b = unique_tokens("a", "b")
        rel = _rel()
        _seed_facts(ws, rel, [a, b])
        loose, loose_payload = run_validate_structured(ws, rel)
        require_cli_status_0(loose)
        assert_both_pass(loose_payload)
        assert_identity_listed(loose_payload, a)
        assert_identity_listed(loose_payload, b)
        human = run_validate(ws, rel)
        require_cli_status_0(human)
        assert_identity_listed(human, a)
        assert_identity_listed(human, b)
        strict, strict_payload = run_validate_structured(ws, rel, strict=True)
        require_cli_status_1(strict)
        assert_conformant_gate_fail(strict_payload)
        assert_identity_listed(strict_payload, a)
        assert_identity_listed(strict_payload, b)
        human_strict = run_validate(ws, rel, strict=True)
        require_cli_status_1(human_strict)
        assert_identity_listed(human_strict, a)


def test_mcp_default_producer_gate_fails_on_orphans_until_strict_false():
    with workspace() as ws:
        a, b = unique_tokens("a", "b")
        rel = _rel()
        _seed_facts(ws, rel, [a, b])
        default = mcp_validate(ws, rel)
        off = mcp_validate(ws, rel, strict=False)
        d_payload = require_mcp_validate_report(default)
        o_payload = require_mcp_validate_report(off)
        assert_conformant_gate_fail(d_payload)
        assert_both_pass(o_payload)
        assert_identity_listed(d_payload, a)
        assert_identity_listed(o_payload, b)


def test_linked_pair_is_not_orphaned_under_strict():
    with workspace() as ws:
        a, b = unique_tokens("a", "b")
        rel = _rel()
        seed_validatable_bundle(
            ws,
            rel,
            [
                fact_concept(a, body=markdown_link("to", f"{b}.md") + "\n"),
                fact_concept(b),
            ],
        )
        result, payload = run_validate_structured(ws, rel, strict=True)
        require_cli_status_0(result)
        assert_both_pass(payload)
        human = run_validate(ws, rel, strict=True)
        require_cli_status_0(human)
        rel_empty = unique_tokens("z0")[0]
        seed_validatable_bundle(ws, rel_empty, [])
        empty, empty_payload = run_validate_structured(ws, rel_empty)
        require_cli_status_0(empty)
        assert_numbers_later_greater(empty_payload, payload)
        rel_unlinked = unique_tokens("ul")[0]
        _seed_facts(ws, rel_unlinked, [a, b])
        unlinked, unlinked_payload = run_validate_structured(
            ws, rel_unlinked, strict=True
        )
        require_cli_status_1(unlinked)
        assert_conformant_gate_fail(unlinked_payload)
        assert_identity_listed(unlinked_payload, a)
        assert_identity_listed(unlinked_payload, b)


def test_third_unlinked_concept_is_orphan_when_another_pair_is_linked():
    with workspace() as ws:
        a, b, c = unique_tokens("a", "b", "c")
        rel = _rel()
        seed_validatable_bundle(
            ws,
            rel,
            [
                fact_concept(a, body=markdown_link("to", f"{b}.md") + "\n"),
                fact_concept(b),
                fact_concept(c),
            ],
        )
        loose, loose_payload = run_validate_structured(ws, rel)
        require_cli_status_0(loose)
        assert_both_pass(loose_payload)
        assert_identity_listed(loose_payload, c)
        strict, strict_payload = run_validate_structured(ws, rel, strict=True)
        require_cli_status_1(strict)
        assert_conformant_gate_fail(strict_payload)
        assert_identity_listed(strict_payload, c)
        mcp_payload = require_mcp_validate_report(mcp_validate(ws, rel))
        assert_conformant_gate_fail(mcp_payload)
        assert_identity_listed(mcp_payload, c)


def test_fenced_peer_reserved_external_and_index_listings_do_not_rescue_orphans():
    with workspace() as ws:
        a, b, title_a, title_b, desc_a, desc_b = unique_tokens(
            "a", "b", "ta", "tb", "da", "db"
        )
        rel_fence, rel_extra, rel_live = unique_tokens("fc", "ex", "lv")
        seed_validatable_bundle(
            ws,
            rel_fence,
            [
                fact_concept(a, body=f"```\n{markdown_link('to', f'{b}.md')}\n```\n"),
                fact_concept(b),
            ],
        )
        seed_validatable_bundle(
            ws,
            rel_extra,
            [
                fact_concept(
                    a,
                    body=markdown_link("ext", "https://example.invalid/x") + "\n",
                ),
                fact_concept(b),
            ],
            listings=[
                (title_a, f"{a}.md", desc_a),
                (title_b, f"{b}.md", desc_b),
            ],
        )
        seed_validatable_bundle(
            ws,
            rel_live,
            [
                fact_concept(a, body=markdown_link("to", f"{b}.md") + "\n"),
                fact_concept(b),
            ],
        )
        for rel in (rel_fence, rel_extra):
            loose, payload = run_validate_structured(ws, rel)
            require_cli_status_0(loose)
            assert_both_pass(payload)
            assert_identity_listed(payload, a)
            assert_identity_listed(payload, b)
            strict, s_payload = run_validate_structured(ws, rel, strict=True)
            require_cli_status_1(strict)
            assert_conformant_gate_fail(s_payload)
            assert_identity_listed(s_payload, a)
            assert_identity_listed(s_payload, b)
        live, live_payload = run_validate_structured(ws, rel_live, strict=True)
        require_cli_status_0(live)
        assert_both_pass(live_payload)


def test_single_concept_is_not_orphaned_under_strict():
    with workspace() as ws:
        ident, other = unique_tokens("id", "ot")
        rel_one, rel_two = unique_tokens("one", "two")
        seed_validatable_bundle(ws, rel_one, [fact_concept(ident)])
        seed_validatable_bundle(
            ws, rel_two, [fact_concept(ident), fact_concept(other)]
        )
        one, one_payload = run_validate_structured(ws, rel_one, strict=True)
        require_cli_status_0(one)
        assert_both_pass(one_payload)
        rel_empty = unique_tokens("z0")[0]
        seed_validatable_bundle(ws, rel_empty, [])
        empty, empty_payload = run_validate_structured(ws, rel_empty)
        require_cli_status_0(empty)
        assert_numbers_later_greater(empty_payload, one_payload)
        two, two_payload = run_validate_structured(ws, rel_two, strict=True)
        require_cli_status_1(two)
        assert_conformant_gate_fail(two_payload)
        assert_identity_listed(two_payload, ident)
        assert_identity_listed(two_payload, other)


def test_broken_relative_missing_md_listed_fails_gate_only_when_strict():
    with workspace() as ws:
        ident, unique_href = unique_tokens("id", "uh")
        rel_pub, rel_twin, rel_ok = unique_tokens("pb", "tw", "ok")
        seed_validatable_bundle(
            ws,
            rel_pub,
            [fact_concept(ident, body=markdown_link("x", SAMPLE_MISSING_HREF) + "\n")],
        )
        seed_validatable_bundle(
            ws,
            rel_twin,
            [fact_concept(ident, body=markdown_link("x", f"{unique_href}.md") + "\n")],
        )
        seed_validatable_bundle(
            ws,
            rel_ok,
            [
                fact_concept(ident, body=markdown_link("x", "present.md") + "\n"),
                fact_concept("present"),
            ],
        )
        loose, payload = run_validate_structured(ws, rel_pub)
        require_cli_status_0(loose)
        assert_both_pass(payload)
        assert_href_listed(payload, SAMPLE_MISSING_HREF, source=f"{ident}.md")
        strict, s_payload = run_validate_structured(ws, rel_pub, strict=True)
        require_cli_status_1(strict)
        assert_conformant_gate_fail(s_payload)
        twin, t_payload = run_validate_structured(ws, rel_twin)
        require_cli_status_0(twin)
        assert_href_listed(t_payload, f"{unique_href}.md", source=f"{ident}.md")
        ok, ok_payload = run_validate_structured(ws, rel_ok, strict=True)
        require_cli_status_0(ok)
        assert_both_pass(ok_payload)
        assert_href_not_listed(ok_payload, SAMPLE_MISSING_HREF)
        assert_href_not_listed(ok_payload, "present.md")


def test_mcp_broken_missing_md_fails_default_producer_gate():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel = _rel()
        seed_validatable_bundle(
            ws,
            rel,
            [fact_concept(ident, body=markdown_link("x", SAMPLE_MISSING_HREF) + "\n")],
        )
        outcome = mcp_validate(ws, rel)
        payload = require_mcp_validate_report(outcome)
        assert_conformant_gate_fail(payload)
        assert_href_listed(payload, SAMPLE_MISSING_HREF, source=f"{ident}.md")


def test_fenced_and_external_hrefs_are_not_broken_links():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_fence, rel_ext, rel_live = unique_tokens("fc", "ex", "lv")
        seed_validatable_bundle(
            ws,
            rel_fence,
            [fact_concept(ident, body=f"```\n[x]({SAMPLE_MISSING_HREF})\n```\n")],
        )
        seed_validatable_bundle(
            ws,
            rel_ext,
            [
                fact_concept(
                    ident,
                    body=markdown_link("x", f"https://example.invalid/{SAMPLE_MISSING_HREF}") + "\n",
                )
            ],
        )
        seed_validatable_bundle(
            ws,
            rel_live,
            [fact_concept(ident, body=markdown_link("x", SAMPLE_MISSING_HREF) + "\n")],
        )
        fenced, f_payload = run_validate_structured(ws, rel_fence, strict=True)
        external, e_payload = run_validate_structured(ws, rel_ext, strict=True)
        live, l_payload = run_validate_structured(ws, rel_live, strict=True)
        require_cli_status_0(fenced)
        assert_both_pass(f_payload)
        require_cli_status_0(external)
        assert_both_pass(e_payload)
        require_cli_status_1(live)
        assert_conformant_gate_fail(l_payload)
        assert_href_listed(l_payload, SAMPLE_MISSING_HREF, source=f"{ident}.md")
        assert_href_not_listed(f_payload, SAMPLE_MISSING_HREF)
        assert_href_not_listed(e_payload, SAMPLE_MISSING_HREF)


def test_links_to_reserved_index_log_agents_are_broken():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel = _rel()
        body = (
            markdown_link("i", "index.md")
            + " "
            + markdown_link("l", "log.md")
            + " "
            + markdown_link("a", "AGENTS.md")
            + "\n"
        )
        seed_validatable_bundle(ws, rel, [fact_concept(ident, body=body)])
        loose, payload = run_validate_structured(ws, rel)
        require_cli_status_0(loose)
        assert_href_listed(payload, "index.md", source=f"{ident}.md")
        assert_href_listed(payload, "log.md", source=f"{ident}.md")
        assert_href_listed(payload, "AGENTS.md", source=f"{ident}.md")
        strict, s_payload = run_validate_structured(ws, rel, strict=True)
        require_cli_status_1(strict)
        assert_conformant_gate_fail(s_payload)
        rel_real = unique_tokens("rl")[0]
        seed_validatable_bundle(
            ws,
            rel_real,
            [
                fact_concept("dir/src", body=markdown_link("a", "agents.md") + "\n"),
                fact_concept("dir/agents"),
            ],
        )
        real, real_payload = run_validate_structured(ws, rel_real, strict=True)
        require_cli_status_0(real)
        assert_both_pass(real_payload)
        assert_href_not_listed(real_payload, "AGENTS.md")


# ---------------------------------------------------------------------------
# G. Stale-date gate
# ---------------------------------------------------------------------------


def test_yesterday_stale_after_increments_count_strict_alone_still_passes():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        yesterday = utc_yesterday()
        tomorrow = utc_tomorrow()
        rel_y, rel_t, rel_o = unique_tokens("yd", "tm", "om")
        seed_validatable_bundle(
            ws, rel_y, [fact_concept(ident, extra={"stale_after": yesterday})]
        )
        seed_validatable_bundle(
            ws, rel_t, [fact_concept(ident, extra={"stale_after": tomorrow})]
        )
        seed_validatable_bundle(ws, rel_o, [fact_concept(ident)])
        y, y_payload = run_validate_structured(ws, rel_y, strict=True)
        t, t_payload = run_validate_structured(ws, rel_t, strict=True)
        o, o_payload = run_validate_structured(ws, rel_o, strict=True)
        require_cli_status_0(y)
        require_cli_status_0(t)
        require_cli_status_0(o)
        assert_both_pass(y_payload)
        assert_both_pass(t_payload)
        assert_numbers_later_greater(t_payload, y_payload, field="stale_count")
        assert_numbers_later_greater(o_payload, y_payload, field="stale_count")
        require_warning_class(
            run_validate(ws, rel_y, strict=True),
            run_validate(ws, rel_t, strict=True),
            concerns=f"{ident}.md",
        )


def test_stale_date_gate_fails_producer_gate_on_nonzero_stale_count():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        yesterday = utc_yesterday()
        rel = _rel()
        seed_validatable_bundle(
            ws, rel, [fact_concept(ident, extra={"stale_after": yesterday})]
        )
        without, without_payload = run_validate_structured(ws, rel, strict=True)
        require_cli_status_0(without)
        assert_both_pass(without_payload)
        with_stale, payload = run_validate_structured(
            ws, rel, stale=True, strict=True
        )
        require_cli_status_1(with_stale)
        assert_conformant_gate_fail(payload)


def test_today_utc_is_stale_tomorrow_is_not():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        today = utc_today_iso()
        tomorrow = utc_tomorrow()
        rel_today, rel_tm = unique_tokens("td", "tm")
        seed_validatable_bundle(
            ws, rel_today, [fact_concept(ident, extra={"stale_after": today})]
        )
        seed_validatable_bundle(
            ws, rel_tm, [fact_concept(ident, extra={"stale_after": tomorrow})]
        )
        today_run, today_payload = run_validate_structured(ws, rel_today, stale=True)
        tm_run, tm_payload = run_validate_structured(ws, rel_tm, stale=True)
        require_cli_status_1(today_run)
        assert_conformant_gate_fail(today_payload)
        require_cli_status_0(tm_run)
        assert_both_pass(tm_payload)
        assert_numbers_later_greater(tm_payload, today_payload, field="stale_count")


def test_stale_after_uses_utc_today_under_tz_offset():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        today = utc_today_iso()
        tomorrow = utc_tomorrow()
        tz_value, local_date = tz_offset_where_local_date_differs()
        rel, rel_pass = unique_tokens("td", "ps")
        seed_validatable_bundle(
            ws, rel, [fact_concept(ident, extra={"stale_after": today})]
        )
        seed_validatable_bundle(
            ws, rel_pass, [fact_concept(ident, extra={"stale_after": tomorrow})]
        )
        result, payload = run_validate_structured(
            ws, rel, stale=True, env_updates={"TZ": tz_value}
        )
        pass_run, pass_payload = run_validate_structured(
            ws, rel_pass, stale=True, env_updates={"TZ": tz_value}
        )
        print(f"[F08] TZ={tz_value} local={local_date} utc_today={today}", flush=True)
        require_cli_status_1(result)
        assert_conformant_gate_fail(payload)
        require_cli_status_0(pass_run)
        assert_both_pass(pass_payload)
        assert local_date != today


def test_mcp_stale_gate_only_when_requested():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        yesterday = utc_yesterday()
        rel = _rel()
        seed_validatable_bundle(
            ws, rel, [fact_concept(ident, extra={"stale_after": yesterday})]
        )
        omitted = mcp_validate(ws, rel)
        requested = mcp_validate(ws, rel, stale=True)
        o_payload = require_mcp_validate_report(omitted)
        r_payload = require_mcp_validate_report(requested)
        assert_both_pass(o_payload)
        assert_conformant_gate_fail(r_payload)


# ---------------------------------------------------------------------------
# H. Drift audit
# ---------------------------------------------------------------------------


def test_drift_warns_when_listing_does_not_contain_description_after_named_comparison():
    with workspace() as ws:
        ident, title, mismatch = unique_tokens("id", "tl", "ms")
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        seed_drift_bundle(ws, rel_bad, ident, title, SAMPLE_DRIFT_DESC, mismatch)
        seed_drift_bundle(ws, rel_ok, ident, title, SAMPLE_DRIFT_DESC, SAMPLE_DRIFT_LISTING)
        warn = run_validate(ws, rel_bad, drift=True, strict=True)
        ok = run_validate(ws, rel_ok, drift=True, strict=True)
        require_warning_class(
            warn,
            ok,
            concerns="index.md",
        )


def test_drift_containment_and_punctuation_strip_do_not_warn():
    with workspace() as ws:
        ident, title, mismatch = unique_tokens("id", "tl", "ms")
        hello = "Hello world"
        rel_quiet, rel_case, rel_punct, rel_bad = unique_tokens("qt", "cs", "pc", "bd")
        rel_bs, rel_sq, rel_bt, rel_as, rel_hello = unique_tokens(
            "bs", "sq", "bt", "as", "ok"
        )
        seed_drift_bundle(ws, rel_quiet, ident, title, hello, hello)
        seed_drift_bundle(ws, rel_case, ident, title, hello, "HELLO WORLD")
        seed_drift_bundle(ws, rel_punct, ident, title, hello, 'He"llo  wo_rld.')
        seed_drift_bundle(ws, rel_bad, ident, title, SAMPLE_DRIFT_DESC, mismatch)
        seed_drift_bundle(ws, rel_bs, ident, title, hello, r"Hel\lo world")
        seed_drift_bundle(ws, rel_sq, ident, title, hello, "Hel'lo world")
        seed_drift_bundle(ws, rel_bt, ident, title, hello, "Hel`lo world")
        seed_drift_bundle(ws, rel_as, ident, title, hello, "Hel*lo world")
        seed_drift_bundle(ws, rel_hello, ident, title, hello, "Hello world and more")
        quiet = run_validate(ws, rel_quiet, drift=True, strict=True)
        case = run_validate(ws, rel_case, drift=True, strict=True)
        punct = run_validate(ws, rel_punct, drift=True, strict=True)
        bad = run_validate(ws, rel_bad, drift=True, strict=True)
        backslash = run_validate(ws, rel_bs, drift=True, strict=True)
        single_quote = run_validate(ws, rel_sq, drift=True, strict=True)
        backtick = run_validate(ws, rel_bt, drift=True, strict=True)
        asterisk = run_validate(ws, rel_as, drift=True, strict=True)
        hello_ok = run_validate(ws, rel_hello, drift=True, strict=True)
        require_cli_status_0(quiet)
        require_cli_status_0(case)
        require_cli_status_0(punct)
        require_cli_status_0(backslash)
        require_cli_status_0(single_quote)
        require_cli_status_0(backtick)
        require_cli_status_0(asterisk)
        require_cli_status_0(hello_ok)
        require_warning_class(
            bad,
            quiet,
            concerns="index.md",
        )
        for arm, label in (
            (case, "casefold"),
            (punct, "quote-underscore-whitespace-period"),
            (backslash, "backslash"),
            (single_quote, "single-quote"),
            (backtick, "backtick"),
            (asterisk, "asterisk"),
            (hello_ok, "containment"),
        ):
            print(f"[F08] drift named comparison {label}", flush=True)
            assert_warning_absent(arm, quiet, concerns="index.md")


def test_drift_warning_alone_does_not_fail_producer_gate():
    with workspace() as ws:
        ident, title, mismatch = unique_tokens("id", "tl", "ms")
        rel, rel_ok = unique_tokens("bd", "ok")
        seed_drift_bundle(ws, rel, ident, title, SAMPLE_DRIFT_DESC, mismatch)
        seed_drift_bundle(ws, rel_ok, ident, title, SAMPLE_DRIFT_DESC, SAMPLE_DRIFT_LISTING)
        result, payload = run_validate_structured(ws, rel, drift=True, strict=True)
        require_cli_status_0(result)
        assert_both_pass(payload)
        ok = run_validate(ws, rel_ok, drift=True, strict=True)
        require_warning_class(
            run_validate(ws, rel, drift=True, strict=True),
            ok,
            concerns="index.md",
        )


def test_mcp_drift_mismatch_does_not_fail_producer_gate():
    with workspace() as ws:
        ident, title, mismatch = unique_tokens("id", "tl", "ms")
        rel = _rel()
        desc = SAMPLE_DRIFT_DESC
        listing = SAMPLE_DRIFT_LISTING
        seed_drift_bundle(ws, rel, ident, title, desc, mismatch)
        outcome = mcp_validate(ws, rel)
        payload = require_mcp_validate_report(outcome)
        assert_both_pass(payload)
        rel_ok = unique_tokens("ok")[0]
        seed_drift_bundle(ws, rel_ok, ident, title, desc, listing)
        ok = mcp_validate(ws, rel_ok)
        ok_payload = require_mcp_validate_report(ok)
        assert_both_pass(ok_payload)
        assert_more_findings(payload, ok_payload, "warnings", "index.md")


def test_cli_drift_is_opt_in_mcp_drift_is_always_on():
    with workspace() as ws:
        ident, title, mismatch = unique_tokens("id", "tl", "ms")
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        seed_drift_bundle(ws, rel_bad, ident, title, SAMPLE_DRIFT_DESC, mismatch)
        seed_drift_bundle(ws, rel_ok, ident, title, SAMPLE_DRIFT_DESC, SAMPLE_DRIFT_LISTING)
        cli_off = run_validate(ws, rel_bad, strict=True)
        cli_on = run_validate(ws, rel_bad, drift=True, strict=True)
        baseline = run_validate(ws, rel_ok, drift=True, strict=True)
        require_cli_status_0(cli_off)
        require_warning_class(
            cli_on,
            baseline,
            concerns="index.md",
        )
        assert_warning_absent(cli_off, baseline, concerns="index.md")
        mcp_default = mcp_validate(ws, rel_bad, strict=False)
        payload = require_mcp_validate_report(mcp_default)
        assert_both_pass(payload)
        mcp_ok = mcp_validate(ws, rel_ok, strict=False)
        ok_payload = require_mcp_validate_report(mcp_ok)
        assert_both_pass(ok_payload)
        assert_more_findings(payload, ok_payload, "warnings", "index.md")


def test_missing_non_glob_code_refs_path_is_drift_warning():
    with workspace() as ws:
        ident, missing = unique_tokens("id", "mf")
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        path = f"{missing}.go"
        seed_validatable_bundle(
            ws, rel_bad, [fact_concept(ident, extra={"code_refs": [path]})]
        )
        seed_validatable_bundle(
            ws, rel_ok, [fact_concept(ident, extra={"code_refs": [path]})]
        )
        (ws.path / rel_ok / path).write_text("package x\n", encoding="utf-8")
        warn = run_validate(ws, rel_bad, drift=True, strict=True)
        ok = run_validate(ws, rel_ok, drift=True, strict=True)
        require_warning_class(
            warn,
            ok,
            concerns=f"{ident}.md",
        )


def test_glob_code_refs_and_existing_project_or_bundle_path_do_not_drift_warn():
    with workspace() as ws:
        ident, leaf = unique_tokens("id", "lf")
        rel_glob, rel_proj, rel_bundle, rel_miss = unique_tokens("g", "p", "b", "m")
        seed_validatable_bundle(
            ws, rel_glob, [fact_concept(ident, extra={"code_refs": ["*.go"]})]
        )
        seed_validatable_bundle(
            ws,
            rel_proj,
            [fact_concept(ident, extra={"code_refs": [f"{leaf}.go"]})],
        )
        (ws.path / f"{leaf}.go").write_text("package x\n", encoding="utf-8")
        seed_validatable_bundle(
            ws,
            rel_bundle,
            [fact_concept(ident, extra={"code_refs": [f"{leaf}.go"]})],
        )
        (ws.path / rel_bundle / f"{leaf}.go").write_text("package x\n", encoding="utf-8")
        seed_validatable_bundle(
            ws,
            rel_miss,
            [fact_concept(ident, extra={"code_refs": [f"{leaf}-gone.go"]})],
        )
        glob = run_validate(ws, rel_glob, drift=True, strict=True)
        proj = run_validate(ws, rel_proj, drift=True, strict=True)
        bundle = run_validate(ws, rel_bundle, drift=True, strict=True)
        miss = run_validate(ws, rel_miss, drift=True, strict=True)
        require_cli_status_0(glob)
        require_cli_status_0(proj)
        require_cli_status_0(bundle)
        require_warning_class(
            miss,
            glob,
            concerns=f"{ident}.md",
        )
        assert_warning_absent(proj, glob, concerns=f"{ident}.md")
        assert_warning_absent(bundle, glob, concerns=f"{ident}.md")


def test_cli_missing_code_refs_path_without_drift_is_not_that_warning():
    with workspace() as ws:
        ident, missing = unique_tokens("id", "mf")
        rel = _rel()
        path = f"{missing}.go"
        seed_validatable_bundle(
            ws, rel, [fact_concept(ident, extra={"code_refs": [path]})]
        )
        off = run_validate(ws, rel, strict=True)
        on = run_validate(ws, rel, drift=True, strict=True)
        rel_ok = unique_tokens("ok")[0]
        seed_validatable_bundle(
            ws, rel_ok, [fact_concept(ident, extra={"code_refs": [path]})]
        )
        (ws.path / rel_ok / path).write_text("package x\n", encoding="utf-8")
        baseline = run_validate(ws, rel_ok, drift=True, strict=True)
        require_cli_status_0(off)
        require_warning_class(
            on,
            baseline,
            concerns=f"{ident}.md",
        )
        assert_warning_absent(off, baseline, concerns=f"{ident}.md")


def test_mcp_missing_code_refs_path_warns_without_failing_gate():
    with workspace() as ws:
        ident, missing, title = unique_tokens("id", "mf", "tl")
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        path = f"{missing}.go"
        desc = SAMPLE_DRIFT_DESC
        listing = SAMPLE_DRIFT_LISTING
        seed_validatable_bundle(
            ws,
            rel_bad,
            [
                fact_concept(
                    ident,
                    extra={"description": desc, "title": title, "code_refs": [path]},
                )
            ],
            listings=[(title, f"{ident}.md", listing)],
        )
        seed_validatable_bundle(
            ws,
            rel_ok,
            [
                fact_concept(
                    ident,
                    extra={"description": desc, "title": title, "code_refs": [path]},
                )
            ],
            listings=[(title, f"{ident}.md", listing)],
        )
        (ws.path / rel_ok / path).write_text("package x\n", encoding="utf-8")
        bad = mcp_validate(ws, rel_bad)
        ok = mcp_validate(ws, rel_ok)
        b_payload = require_mcp_validate_report(bad)
        o_payload = require_mcp_validate_report(ok)
        assert_both_pass(b_payload)
        assert_both_pass(o_payload)
        assert_more_findings(b_payload, o_payload, "warnings", f"{ident}.md")


# ---------------------------------------------------------------------------
# I. CLI exit statuses
# ---------------------------------------------------------------------------


def test_cli_status_0_on_conformant_gate_pass():
    with workspace() as ws:
        ident_a, ident_b = unique_tokens("a", "b")
        rel_empty, rel_fact, rel_orph = unique_tokens("e", "f", "o")
        seed_validatable_bundle(ws, rel_empty, [])
        seed_validatable_bundle(ws, rel_fact, [fact_concept(ident_a)])
        _seed_facts(ws, rel_orph, [ident_a, ident_b])
        require_cli_status_0(run_validate(ws, rel_empty))
        require_cli_status_0(run_validate(ws, rel_fact))
        require_cli_status_0(run_validate(ws, rel_orph))


def test_cli_status_1_on_nonconformance_and_on_failed_gate():
    with workspace() as ws:
        ident, a, b = unique_tokens("id", "a", "b")
        yesterday = utc_yesterday()
        rel_type, rel_orph, rel_stale = unique_tokens("t", "o", "s")
        seed_validatable_bundle(
            ws,
            rel_type,
            [{"identity": ident, "frontmatter": {"title": ident}, "body": "body\n"}],
        )
        _seed_facts(ws, rel_orph, [a, b])
        seed_validatable_bundle(
            ws, rel_stale, [fact_concept(ident, extra={"stale_after": yesterday})]
        )
        require_cli_status_1(run_validate(ws, rel_type))
        require_cli_status_1(run_validate(ws, rel_orph, strict=True))
        require_cli_status_1(run_validate(ws, rel_stale, stale=True))
        rel_agents = unique_tokens("ag")[0]
        seed_validatable_bundle(ws, rel_agents, [])
        require_cli_status_1(run_validate(ws, rel_agents, agents=True))


def test_cli_status_2_on_missing_bundle():
    with workspace() as ws:
        missing = unique_tokens("gone")[0]
        result = run_validate(ws, missing)
        require_cli_status_2(result)
        rel_ok, rel_bad = unique_tokens("ok", "bd")
        seed_validatable_bundle(ws, rel_ok, [])
        ident = unique_tokens("id")[0]
        seed_validatable_bundle(
            ws,
            rel_bad,
            [{"identity": ident, "frontmatter": {"title": ident}, "body": "body\n"}],
        )
        require_cli_status_0(run_validate(ws, rel_ok))
        require_cli_status_1(run_validate(ws, rel_bad))


# ---------------------------------------------------------------------------
# J. MCP validate modes and load
# ---------------------------------------------------------------------------


def test_mcp_missing_bundle_is_tool_error():
    with workspace() as ws:
        missing = unique_tokens("gone")[0]
        fail = mcp_validate(ws, missing)
        require_mcp_validate_tool_error(fail)
        rel = _rel()
        seed_validatable_bundle(ws, rel, [])
        ok = mcp_validate(ws, rel)
        require_mcp_validate_both_pass(ok)


def test_mcp_omit_strict_is_producer_gate_on():
    with workspace() as ws:
        a, b = unique_tokens("a", "b")
        rel = _rel()
        _seed_facts(ws, rel, [a, b])
        omitted = mcp_validate(ws, rel)
        off = mcp_validate(ws, rel, strict=False)
        o_payload = require_mcp_validate_report(omitted)
        f_payload = require_mcp_validate_report(off)
        assert_conformant_gate_fail(o_payload)
        assert_both_pass(f_payload)


# ---------------------------------------------------------------------------
# K. Omit-path and named nested knowledge/ load
# ---------------------------------------------------------------------------


def test_omit_path_cwd_versus_nested_knowledge_directory():
    with workspace() as ws:
        sel_a, sel_b, dcy_a, dcy_b = unique_tokens("sa", "sb", "da", "db")
        _seed_facts(ws, ".", [sel_a, sel_b])
        result, payload = run_validate_structured(ws, None)
        require_cli_status_0(result)
        assert_identity_listed(payload, sel_a)
        assert_identity_listed(payload, sel_b)
        ws2_rel = unique_tokens("p2")[0]
        (ws.path / ws2_rel).mkdir()
        _seed_facts(ws, f"{ws2_rel}/knowledge", [sel_a, sel_b])
        _seed_facts(ws, ws2_rel, [dcy_a, dcy_b])
        got, g_payload = run_validate_structured(
            ws, None, cwd=ws.path / ws2_rel
        )
        require_cli_status_0(got)
        assert_identity_listed(g_payload, sel_a)
        assert_identity_listed(g_payload, sel_b)
        assert_identity_not_listed(g_payload, dcy_a)
        assert_identity_not_listed(g_payload, dcy_b)


def test_omit_path_knowledge_file_is_not_a_bundle_dir():
    with workspace() as ws:
        sel_a, sel_b = unique_tokens("sa", "sb")
        _seed_facts(ws, ".", [sel_a, sel_b])
        (ws.path / "knowledge").write_text("not-a-directory\n", encoding="utf-8")
        cli, payload = run_validate_structured(ws, None)
        require_cli_status_0(cli)
        assert_identity_listed(payload, sel_a)
        assert_identity_listed(payload, sel_b)
        mcp = mcp_validate(ws, None)
        m_payload = require_mcp_validate_report(mcp)
        assert_identity_listed(m_payload, sel_a)
        assert_identity_listed(m_payload, sel_b)


def test_named_path_without_root_index_loads_nested_knowledge():
    with workspace() as ws:
        sel_a, sel_b, decoy = unique_tokens("sa", "sb", "dcy")
        named = unique_tokens("nm")[0]
        named_root = ws.path / named
        named_root.mkdir()
        (named_root / f"{decoy}.md").write_text(
            f"---\ntype: Fact\n---\n\n{decoy}\n", encoding="utf-8"
        )
        _seed_facts(ws, f"{named}/knowledge", [sel_a, sel_b])
        result, payload = run_validate_structured(ws, named)
        require_cli_status_0(result)
        assert_identity_listed(payload, sel_a)
        assert_identity_listed(payload, sel_b)
        assert_identity_not_listed(payload, decoy)
        mcp = mcp_validate(ws, named)
        m_payload = require_mcp_validate_report(mcp)
        assert_identity_listed(m_payload, sel_a)
        assert_identity_listed(m_payload, sel_b)
        assert_identity_not_listed(m_payload, decoy)


def test_explicit_bundle_path_is_not_overridden_by_cwd_knowledge():
    with workspace() as ws:
        sel_a, sel_b, dcy_a, dcy_b = unique_tokens("sa", "sb", "da", "db")
        named = unique_tokens("nm")[0]
        _seed_facts(ws, named, [sel_a, sel_b])
        _seed_facts(ws, "knowledge", [dcy_a, dcy_b])
        result, payload = run_validate_structured(ws, named)
        require_cli_status_0(result)
        assert_identity_listed(payload, sel_a)
        assert_identity_listed(payload, sel_b)
        assert_identity_not_listed(payload, dcy_a)
        assert_identity_not_listed(payload, dcy_b)
        mcp = mcp_validate(ws, named)
        m_payload = require_mcp_validate_report(mcp)
        assert_identity_listed(m_payload, sel_a)
        assert_identity_listed(m_payload, sel_b)
        assert_identity_not_listed(m_payload, dcy_a)
        assert_identity_not_listed(m_payload, dcy_b)


def test_mcp_omit_and_named_bundle_follow_the_same_load_rule():
    with workspace() as ws:
        sel_a, sel_b, dcy_a, dcy_b = unique_tokens("sa", "sb", "da", "db")
        _seed_facts(ws, "knowledge", [sel_a, sel_b])
        _seed_facts(ws, ".", [dcy_a, dcy_b])
        omit = mcp_validate(ws, None)
        payload = require_mcp_validate_report(omit)
        assert_identity_listed(payload, sel_a)
        assert_identity_listed(payload, sel_b)
        assert_identity_not_listed(payload, dcy_a)
        assert_identity_not_listed(payload, dcy_b)
        named = unique_tokens("nm")[0]
        named_a, named_b = unique_tokens("na", "nb")
        _seed_facts(ws, named, [named_a, named_b])
        got = mcp_validate(ws, named)
        named_payload = require_mcp_validate_report(got)
        assert_identity_listed(named_payload, named_a)
        assert_identity_listed(named_payload, named_b)
        assert_identity_not_listed(named_payload, sel_a)
        assert_identity_not_listed(named_payload, sel_b)


# ---------------------------------------------------------------------------
# L. Escaping symlink
# ---------------------------------------------------------------------------


def test_escaping_symlink_is_cli_load_failure_status_2():
    with workspace() as ws:
        ident, token = unique_tokens("id", "tk")
        rel = _rel()
        seed_validatable_bundle(ws, rel, [])
        outside = ws.path / f"{token}.md"
        outside.write_text("---\ntype: Fact\n---\n\noutside\n", encoding="utf-8")
        dest = ws.path / rel / f"{ident}.md"
        os.symlink(os.path.relpath(outside, dest.parent), dest)
        result = run_validate(ws, rel)
        require_cli_status_2(result)
        dest.unlink()
        seed_validatable_bundle(ws, rel, [fact_concept(ident)])
        twin = run_validate(ws, rel)
        require_cli_status_0(twin)
        assert_snapshot_helper_sees_write(ws, unique_tokens("snap")[0])


def test_mcp_escaping_symlink_is_tool_error():
    with workspace() as ws:
        ident, token = unique_tokens("id", "tk")
        rel = _rel()
        seed_validatable_bundle(ws, rel, [])
        outside = ws.path / f"{token}.md"
        outside.write_text("---\ntype: Fact\n---\n\noutside\n", encoding="utf-8")
        dest = ws.path / rel / f"{ident}.md"
        os.symlink(os.path.relpath(outside, dest.parent), dest)
        fail = mcp_validate(ws, rel)
        require_mcp_validate_tool_error(fail)
        dest.unlink()
        seed_validatable_bundle(ws, rel, [fact_concept(ident)])
        ok = mcp_validate(ws, rel)
        require_mcp_validate_both_pass(ok)


# ---------------------------------------------------------------------------
# M. Optional agents governance check
# ---------------------------------------------------------------------------


def test_agents_check_not_requested_does_not_fail_on_missing_agents_md():
    with workspace() as ws:
        rel = _rel()
        seed_validatable_bundle(ws, rel, [])
        result = run_validate(ws, rel)
        require_cli_status_0(result)


def test_agents_check_requested_fails_status_1_when_the_check_fails():
    with workspace() as ws:
        rel = _rel()
        seed_validatable_bundle(ws, rel, [])
        result = run_validate(ws, rel, agents=True)
        require_cli_status_1(result)


def test_agents_check_requested_passes_when_agents_md_and_ssot_links_pass():
    with workspace() as ws:
        proj = unique_tokens("pj")[0]
        bundle = f"{proj}/knowledge"
        seed_validatable_bundle(ws, bundle, [])
        missing = run_validate(ws, bundle, agents=True)
        require_cli_status_1(missing)
        parent = ws.path / proj
        parent.joinpath("AGENTS.md").write_text(PASSING_AGENTS_TEXT, encoding="utf-8")
        plant_ssot_links(parent)
        result = run_validate(ws, bundle, agents=True)
        require_cli_status_0(result)


def test_agents_check_fails_when_one_ssot_mapping_is_omitted():
    with workspace() as ws:
        rel = _rel()
        root = seed_validatable_bundle(ws, rel, [], agents=PASSING_AGENTS_TEXT)
        plant_ssot_links(root, omit="CLAUDE.md")
        result = run_validate(ws, rel, agents=True)
        require_cli_status_1(result)


def test_agents_check_fails_when_one_ssot_path_is_a_regular_file():
    with workspace() as ws:
        rel = _rel()
        root = seed_validatable_bundle(ws, rel, [], agents=PASSING_AGENTS_TEXT)
        plant_ssot_links(root, regular="CLAUDE.md")
        result = run_validate(ws, rel, agents=True)
        require_cli_status_1(result)


def test_agents_check_uses_parent_agents_md_when_only_parent_has_it():
    with workspace() as ws:
        proj = unique_tokens("pj")[0]
        bundle = f"{proj}/knowledge"
        seed_validatable_bundle(ws, bundle, [])
        parent = ws.path / proj
        parent.joinpath("AGENTS.md").write_text("café →\n", encoding="utf-8")
        fail = run_validate(ws, bundle, agents=True)
        require_cli_status_1(fail)
        parent.joinpath("AGENTS.md").write_text(PASSING_AGENTS_TEXT, encoding="utf-8")
        plant_ssot_links(parent)
        ok = run_validate(ws, bundle, agents=True)
        require_cli_status_0(ok)


# ---------------------------------------------------------------------------
# N. Structured CLI vs human default
# ---------------------------------------------------------------------------


def test_structured_cli_walks_booleans_and_counts():
    with workspace() as ws:
        ident, a, b = unique_tokens("id", "a", "b")
        rel_fact, rel_orph, rel_type = unique_tokens("f", "o", "t")
        seed_validatable_bundle(ws, rel_fact, [fact_concept(ident)])
        _seed_facts(ws, rel_orph, [a, b])
        seed_validatable_bundle(
            ws,
            rel_type,
            [{"identity": ident, "frontmatter": {"title": ident}, "body": "body\n"}],
        )
        fact, fact_payload = run_validate_structured(ws, rel_fact)
        require_cli_status_0(fact)
        assert_requested_structured_validate_is_machine_readable(fact)
        assert_both_pass(fact_payload)
        orph, orph_payload = run_validate_structured(ws, rel_orph, strict=True)
        require_cli_status_1(orph)
        assert_conformant_gate_fail(orph_payload)
        assert_identity_listed(orph_payload, a)
        typ, type_payload = run_validate_structured(ws, rel_type)
        require_cli_status_1(typ)
        assert_nonconformant(type_payload)


def test_report_includes_bundle_path_hard_errors_and_warnings():
    with workspace() as ws:
        ident = unique_tokens("id")[0]
        rel_a, rel_b = unique_tokens("pa", "pb")
        seed_validatable_bundle(ws, rel_a, [fact_concept(ident)])
        seed_validatable_bundle(ws, rel_b, [fact_concept(ident)])
        a_run, a_payload = run_validate_structured(ws, rel_a)
        b_run, b_payload = run_validate_structured(ws, rel_b)
        require_cli_status_0(a_run)
        require_cli_status_0(b_run)
        assert_both_pass(a_payload)
        assert_both_pass(b_payload)
        assert_report_includes_path_token(a_payload, rel_a)
        assert_report_includes_path_token(b_payload, rel_b)

        ident_err = unique_tokens("er")[0]
        rel_bad, rel_ok = unique_tokens("bd", "ok")
        seed_validatable_bundle(
            ws,
            rel_bad,
            [
                {
                    "identity": ident_err,
                    "frontmatter": {"title": ident_err},
                    "body": "body\n",
                }
            ],
        )
        seed_validatable_bundle(ws, rel_ok, [fact_concept(ident_err)])
        bad, bad_payload = run_validate_structured(ws, rel_bad)
        repaired, repaired_payload = run_validate_structured(ws, rel_ok)
        require_hard_error_class(
            bad,
            repaired,
            structured_defective=bad_payload,
            concerns=f"{ident_err}.md",
        )
        assert_both_pass(repaired_payload)
        assert_more_findings(
            bad_payload, repaired_payload, "errors", f"{ident_err}.md"
        )

        ident_warn = unique_tokens("wn")[0]
        rel_warn, rel_quiet = unique_tokens("ww", "qq")
        seed_validatable_bundle(ws, rel_warn, [fact_concept(ident_warn)])
        seed_validatable_bundle(ws, rel_quiet, [fact_concept(ident_warn)])
        (ws.path / rel_warn / "dir").mkdir()
        (ws.path / rel_warn / "dir" / "index.md").write_text(
            "---\nmembundle_version: 0.2\n---\n\n# nested\n", encoding="utf-8"
        )
        (ws.path / rel_quiet / "dir").mkdir()
        (ws.path / rel_quiet / "dir" / "index.md").write_text(
            "# nested\n", encoding="utf-8"
        )
        warn, warn_payload = run_validate_structured(ws, rel_warn)
        quiet, quiet_payload = run_validate_structured(ws, rel_quiet)
        require_cli_status_0(warn)
        require_cli_status_0(quiet)
        assert_both_pass(warn_payload)
        assert_both_pass(quiet_payload)
        require_warning_class(
            run_validate(ws, rel_warn),
            run_validate(ws, rel_quiet),
            concerns="dir/index.md",
        )
        assert_more_findings(warn_payload, quiet_payload, "warnings", "dir/index.md")


def test_human_default_still_lists_orphans_and_uses_exit_status():
    with workspace() as ws:
        ident, a, b = unique_tokens("id", "a", "b")
        rel_fact, rel_orph, rel_type = unique_tokens("f", "o", "t")
        seed_validatable_bundle(ws, rel_fact, [fact_concept(ident)])
        _seed_facts(ws, rel_orph, [a, b])
        seed_validatable_bundle(
            ws,
            rel_type,
            [{"identity": ident, "frontmatter": {"title": ident}, "body": "body\n"}],
        )
        require_cli_status_0(run_validate(ws, rel_fact))
        orph = run_validate(ws, rel_orph, strict=True)
        require_cli_status_1(orph)
        assert_identity_listed(orph, a)
        assert_identity_listed(orph, b)
        require_cli_status_1(run_validate(ws, rel_type))
