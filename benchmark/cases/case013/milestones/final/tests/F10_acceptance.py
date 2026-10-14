# feature: F10
"""Acceptance tests for AGENTS.md MBG lint, domain codex, and SSoT links (FP-10).

Public entry: the ``membundle agents`` command with subcommands lint, init, link,
and check. Validate's optional agents-governance check is observed through
sealed F08 ``run_validate``. Observations go through the sealed harness
``workspace`` / ``invoke`` path and on-disk files. These tests do not
import Go packages and do not call internal MBG or symlink helpers.
"""

from __future__ import annotations

import os
from pathlib import Path

from _harness import (
    path_is_dir,
    path_is_file,
    path_is_symlink,
    workspace,
)
from F01_helpers import (
    combined_report,
    first_heading_text,
)
from F02_helpers import BEGIN_MEMBUNDLE_COMMENT, END_MEMBUNDLE_COMMENT, extract_membundle_agents_block
from F03_helpers import path_tokens_for, snapshot_tree
from F08_helpers import (
    plant_ssot_links,
    require_cli_status_0,
    require_cli_status_1,
    run_validate,
    seed_validatable_bundle,
)
from F10_helpers import (
    SAMPLE_SMALL_CAP,
    MBG_RULE_IDS,
    ascii_agents_body,
    assert_exceeded_mark_matches_mbg005,
    assert_in_force_cap_differs,
    assert_named_ssot_symlinks,
    assert_rule_absent,
    assert_rule_only,
    assert_ssot_mapping_state,
    assert_structured_counts_greater,
    assert_structured_pass_fail_distinct,
    assert_warning_count_unchanged_when_errors_increase,
    assert_working_memory_estimate_sorts_below,
    budget_safe_token,
    budget_safe_tokens,
    budget_word_list,
    domain_codex_region,
    finding_rule_ids,
    human_lint_budget,
    link_check_marks,
    mentions_profile,
    parse_structured_lint,
    require_agents_failure,
    require_agents_success,
    run_agents_check,
    run_agents_init,
    run_agents_link,
    run_agents_lint,
    unique_passing_agents,
    write_agents,
)


def _gen_hex(n: int = 6) -> str:
    """Runtime-unique lowercase hex (the suite's own generated sample material)."""
    import uuid as _uuid

    return _uuid.uuid4().hex[:n]


# Generated per test process: an invariant list item whose first word is not
# a modal, and a profile name outside the five profiles.
NON_MODAL_ITEM = f"Q{_gen_hex(6)} s{_gen_hex(5)} before e{_gen_hex(5)}"
SAMPLE_UNKNOWN_PROFILE = f"x{_gen_hex(6)}-profile"


def _paths(ws, *extra: str | Path) -> list[str]:
    return path_tokens_for(ws.path, *extra)


def _lint_structured(ws, body: str, rel: str = "AGENTS.md", **kwargs):
    write_agents(ws, rel, body)
    result = run_agents_lint(ws, rel, structured=True, **kwargs)
    payload = parse_structured_lint(result)
    print(
        f"[F10] structured lint exit={result.returncode} rel={rel}",
        flush=True,
    )
    return result, payload


def _lint_human(ws, body: str, rel: str = "AGENTS.md", **kwargs):
    write_agents(ws, rel, body)
    result = run_agents_lint(ws, rel, structured=False, **kwargs)
    report = combined_report(result)
    print(
        f"[F10] human lint exit={result.returncode} rel={rel} "
        f"report_len={len(report)}",
        flush=True,
    )
    return result, report


def _positive_symlink_control(ws) -> None:
    leaf = budget_safe_token("ctl")
    target = ws.write(f"{leaf}-target.txt", "control\n")
    link = ws.path / f"{leaf}-link"
    os.symlink(target.name, link)
    print(f"[F10] symlink control link={link} is_link={path_is_symlink(link)}", flush=True)
    assert path_is_symlink(link), f"observer did not see a symlink the test created: {link}"


# ---------------------------------------------------------------------------
# A. MBG-001 ASCII-only lines
# ---------------------------------------------------------------------------


def test_non_ascii_arrow_is_mbg001_and_fails_lint():
    with workspace() as ws:
        token = budget_safe_token("arr")
        arrow_body = ascii_agents_body(extra=f"flow {token} ➔ next\n")
        ascii_body = ascii_agents_body(extra=f"flow {token} -> next\n")
        fail_result, fail_payload = _lint_structured(ws, arrow_body, "arrow.md")
        assert_rule_only(fail_payload, "MBG-001")
        human_fail, _ = _lint_human(ws, arrow_body, "arrow-human.md")
        require_agents_failure(human_fail)
        ok_result, ok_payload = _lint_structured(ws, ascii_body, "ascii.md")
        require_agents_success(ok_result)
        assert_rule_absent(ok_payload, "MBG-001")
        human_ok, _ = _lint_human(ws, ascii_body, "ascii-human.md")
        require_agents_success(human_ok)
        fail_ids = finding_rule_ids(fail_payload)
        please = budget_safe_token("pls")
        please_body = ascii_agents_body(
            invariants_item=f"{NON_MODAL_ITEM} {please}",
        )
        _, please_payload = _lint_structured(ws, please_body, "please.md")
        assert_rule_only(please_payload, "MBG-002")
        please_ids = finding_rule_ids(please_payload)
        assert fail_ids != please_ids, (
            "MBG-001 and MBG-002 structured reports carry the same finding "
            f"rule ids; {fail_ids!r}"
        )


def test_non_ascii_outside_domain_codex_is_still_mbg001():
    with workspace() as ws:
        token = budget_safe_token("ltr")
        bad = ascii_agents_body(extra=f"## 2. Notes\nlater {token} café\n")
        good = ascii_agents_body(extra=f"## 2. Notes\nlater {token} cafe\n")
        _, fail_payload = _lint_structured(ws, bad, "letter.md")
        assert_rule_only(fail_payload, "MBG-001")
        human_fail, _ = _lint_human(ws, bad, "letter-human.md")
        require_agents_failure(human_fail)
        ok_result, ok_payload = _lint_structured(ws, good, "letter-ok.md")
        require_agents_success(ok_result)
        assert_rule_absent(ok_payload, "MBG-001")


# ---------------------------------------------------------------------------
# B. MBG-002 RFC 2119 modals on hyphen items
# ---------------------------------------------------------------------------


def test_invariants_please_item_is_mbg002_must_item_is_not():
    with workspace() as ws:
        suffix = budget_safe_token("inv")
        please_body = ascii_agents_body(
            invariants_item=f"{NON_MODAL_ITEM} {suffix}",
        )
        must_body = ascii_agents_body(invariants_item=f"MUST {suffix}")
        _, please_payload = _lint_structured(ws, please_body, "please.md")
        assert_rule_only(please_payload, "MBG-002")
        human_fail, _ = _lint_human(ws, please_body, "please-human.md")
        require_agents_failure(human_fail)
        must_result, must_payload = _lint_structured(ws, must_body, "must.md")
        require_agents_success(must_result)
        assert_rule_absent(must_payload, "MBG-002")
        two_item = ascii_agents_body(
            invariants_item=f"MUST {suffix}",
            extra_invariants_items=(f"{NON_MODAL_ITEM} {suffix}b",),
        )
        _, two_payload = _lint_structured(ws, two_item, "two.md")
        assert_rule_only(two_payload, "MBG-002")
        two_human, _ = _lint_human(ws, two_item, "two-human.md")
        require_agents_failure(two_human)
        single_result, single_payload = _lint_structured(ws, must_body, "single.md")
        require_agents_success(single_result)
        assert_rule_absent(single_payload, "MBG-002")


def test_each_finite_modal_prefix_and_token_alone_and_backtick_pass_mbg002():
    with workspace() as ws:
        suffix = budget_safe_token("mdl")
        please_body = ascii_agents_body(
            invariants_item=f"{NON_MODAL_ITEM} {suffix}",
        )
        _, please_payload = _lint_structured(ws, please_body, "please.md")
        assert_rule_only(please_payload, "MBG-002")
        prefixes = (
            f"MUST NOT {suffix}",
            f"NEVER {suffix}",
            f"PREFER {suffix}",
            f"ALWAYS {suffix}",
            f"SHOULD {suffix}",
            f"MAY {suffix}",
            f"! {suffix}",
        )
        for index, item in enumerate(prefixes):
            body = ascii_agents_body(invariants_item=item)
            result, payload = _lint_structured(ws, body, f"modal-{index}.md")
            require_agents_success(result)
            assert_rule_absent(payload, "MBG-002")
        for index, item in enumerate(("MUST", "!")):
            body = ascii_agents_body(invariants_item=item)
            result, payload = _lint_structured(ws, body, f"alone-{index}.md")
            require_agents_success(result)
            assert_rule_absent(payload, "MBG-002")
        tick = ascii_agents_body(invariants_item=f"`MUST {suffix}")
        tick_result, tick_payload = _lint_structured(ws, tick, "tick.md")
        require_agents_success(tick_result)
        assert_rule_absent(tick_payload, "MBG-002")


def test_modal_without_following_space_is_mbg002():
    with workspace() as ws:
        suffix = budget_safe_token("glued")
        body = ascii_agents_body(invariants_item=f"MUSTsearch {suffix}")
        _, payload = _lint_structured(ws, body, "glued.md")
        assert_rule_only(payload, "MBG-002")
        human, _ = _lint_human(ws, body, "glued-human.md")
        require_agents_failure(human)
        twin = ascii_agents_body(invariants_item=f"MUST {suffix}")
        ok_result, ok_payload = _lint_structured(ws, twin, "glued-ok.md")
        require_agents_success(ok_result)
        assert_rule_absent(ok_payload, "MBG-002")


def test_mbg002_heading_classes_constraints_rfc2119_and_1_and_not_section_2():
    with workspace() as ws:
        suffix = budget_safe_token("hd")
        please = f"{NON_MODAL_ITEM} {suffix}"
        for label, heading in (
            ("constraints", "Constraints"),
            ("rfc", "rfc 2119 notes"),
            ("one", "1. Rules"),
        ):
            body = ascii_agents_body(
                invariants_item=please,
                invariants_heading=heading,
            )
            _, payload = _lint_structured(ws, body, f"{label}.md")
            assert_rule_only(payload, "MBG-002")
            human, _ = _lint_human(ws, body, f"{label}-human.md")
            require_agents_failure(human)
        outside = ascii_agents_body(
            invariants_item=please,
            invariants_heading="2. Guard clauses",
        )
        result, payload = _lint_structured(ws, outside, "section2.md")
        require_agents_success(result)
        assert_rule_absent(payload, "MBG-002")


# ---------------------------------------------------------------------------
# C. MBG-003 unclosed membundle_ / tool_ parentheses
# ---------------------------------------------------------------------------


def test_unclosed_membundle_and_tool_parens_are_mbg003_balanced_and_unrelated_are_not():
    with workspace() as ws:
        token = budget_safe_token("prn")
        unclosed_membundle = ascii_agents_body(extra=f"call membundle_search({token}\n")
        _, membundle_payload = _lint_structured(ws, unclosed_membundle, "membundle-open.md")
        assert_rule_only(membundle_payload, "MBG-003")
        human_membundle, _ = _lint_human(ws, unclosed_membundle, "membundle-open-human.md")
        require_agents_failure(human_membundle)
        balanced_membundle = ascii_agents_body(
            extra=f"call membundle_search(query=keywords) {token}\n"
        )
        ok_result, ok_payload = _lint_structured(ws, balanced_membundle, "membundle-ok.md")
        require_agents_success(ok_result)
        assert_rule_absent(ok_payload, "MBG-003")
        unclosed_tool = ascii_agents_body(extra=f"call tool_search({token}\n")
        _, tool_payload = _lint_structured(ws, unclosed_tool, "tool-open.md")
        assert_rule_only(tool_payload, "MBG-003")
        human_tool, _ = _lint_human(ws, unclosed_tool, "tool-open-human.md")
        require_agents_failure(human_tool)
        balanced_tool = ascii_agents_body(
            extra=f"call tool_search(query=keywords) {token}\n"
        )
        tool_ok, tool_ok_payload = _lint_structured(ws, balanced_tool, "tool-ok.md")
        require_agents_success(tool_ok)
        assert_rule_absent(tool_ok_payload, "MBG-003")
        unrelated = ascii_agents_body(extra=f"plain_open({token}\n")
        unrelated_result, unrelated_payload = _lint_structured(
            ws, unrelated, "plain-open.md"
        )
        require_agents_success(unrelated_result)
        assert_rule_absent(unrelated_payload, "MBG-003")
        extra_close = ascii_agents_body(extra=f"call membundle_search){token}\n")
        close_result, close_payload = _lint_structured(ws, extra_close, "membundle-close.md")
        require_agents_success(close_result)
        assert_rule_absent(close_payload, "MBG-003")


# ---------------------------------------------------------------------------
# D. MBG-004 Mermaid only when a Domain Codex / 0. section exists
# ---------------------------------------------------------------------------


def test_section_0_without_mermaid_is_mbg004_mention_removes_it():
    with workspace() as ws:
        token = budget_safe_token("mm")
        missing = ascii_agents_body(section0=f"plain notes {token}")
        _, payload = _lint_structured(ws, missing, "no-mm.md")
        assert_rule_only(payload, "MBG-004")
        human, _ = _lint_human(ws, missing, "no-mm-human.md")
        require_agents_failure(human)
        present = ascii_agents_body(section0=f"plain notes {token} mermaid")
        ok_result, ok_payload = _lint_structured(ws, present, "with-mm.md")
        require_agents_success(ok_result)
        assert_rule_absent(ok_payload, "MBG-004")
        lower = ascii_agents_body(section0=f"plain notes {token} mermaid")
        lower_result, lower_payload = _lint_structured(ws, lower, "lower-mm.md")
        require_agents_success(lower_result)
        assert_rule_absent(lower_payload, "MBG-004")


def test_no_domain_codex_or_0_heading_does_not_fail_mbg004():
    with workspace() as ws:
        token = budget_safe_token("none")
        missing = ascii_agents_body(section0=f"plain notes {token}")
        _, miss_payload = _lint_structured(ws, missing, "missing-mm.md")
        assert_rule_only(miss_payload, "MBG-004")
        miss_human, _ = _lint_human(ws, missing, "missing-mm-human.md")
        require_agents_failure(miss_human)
        body = ascii_agents_body(section0=None, extra=f"## 2. Notes\n{token}\n")
        result, payload = _lint_structured(ws, body, "no-section.md")
        require_agents_success(result)
        assert_rule_absent(payload, "MBG-004")


def test_mermaid_outside_the_section_does_not_satisfy_mbg004():
    with workspace() as ws:
        token = budget_safe_token("out")
        body = ascii_agents_body(
            section0=f"plain notes {token}",
            extra=f"## 2. Notes\nmermaid {token}\n",
        )
        _, payload = _lint_structured(ws, body, "mm-outside.md")
        assert_rule_only(payload, "MBG-004")
        human, _ = _lint_human(ws, body, "mm-outside-human.md")
        require_agents_failure(human)
        inside = ascii_agents_body(section0=f"plain notes {token} mermaid")
        ok_result, ok_payload = _lint_structured(ws, inside, "mm-inside.md")
        require_agents_success(ok_result)
        assert_rule_absent(ok_payload, "MBG-004")


def test_domain_codex_heading_without_0_still_requires_mermaid():
    with workspace() as ws:
        token = budget_safe_token("dc")
        zero_only = (
            f"# 0. Scope\nplain notes {token}\n\n"
            f"{BEGIN_MEMBUNDLE_COMMENT}\nkeep compact\n{END_MEMBUNDLE_COMMENT}\n"
        )
        _, zero_payload = _lint_structured(ws, zero_only, "zero-only.md")
        assert_rule_only(zero_payload, "MBG-004")
        human_zero, _ = _lint_human(ws, zero_only, "zero-only-human.md")
        require_agents_failure(human_zero)
        codex_only = (
            f"# Domain Codex notes\nplain notes {token}\n\n"
            f"{BEGIN_MEMBUNDLE_COMMENT}\nkeep compact\n{END_MEMBUNDLE_COMMENT}\n"
        )
        _, codex_payload = _lint_structured(ws, codex_only, "codex-only.md")
        assert_rule_only(codex_payload, "MBG-004")
        human_codex, _ = _lint_human(ws, codex_only, "codex-only-human.md")
        require_agents_failure(human_codex)
        repaired = (
            f"# 0. Scope\nplain notes {token} mermaid\n\n"
            f"{BEGIN_MEMBUNDLE_COMMENT}\nkeep compact\n{END_MEMBUNDLE_COMMENT}\n"
        )
        ok_result, ok_payload = _lint_structured(ws, repaired, "zero-repaired.md")
        require_agents_success(ok_result)
        assert_rule_absent(ok_payload, "MBG-004")


# ---------------------------------------------------------------------------
# E. MBG-005 working-memory token budget
# ---------------------------------------------------------------------------


def _under_400_delimited(token: str) -> str:
    words = budget_word_list(30, "u")
    inner = " ".join(words + [token])
    return ascii_agents_body(inner=inner)


def test_delimited_block_over_small_cap_is_mbg005_default_400_and_nonpositive_are_not():
    with workspace() as ws:
        under_token = budget_safe_token("under")
        under = _under_400_delimited(under_token)
        fail20, payload20 = _lint_structured(ws, under, "under.md", budget=SAMPLE_SMALL_CAP)
        assert_rule_only(payload20, "MBG-005")
        human20, _ = _lint_human(ws, under, "under-human.md", budget=SAMPLE_SMALL_CAP)
        require_agents_failure(human20)


def test_token_estimate_uses_delimited_block_when_end_follows_begin_else_whole_file():
    with workspace() as ws:
        token = budget_safe_token("del")
        huge = " ".join(budget_word_list(360, "h"))
        inner = f"keep compact {token}"
        section = f"# 0. Domain Codex\nmermaid\n\n"
        ordered = (
            f"{huge}\n\n{section}"
            f"{BEGIN_MEMBUNDLE_COMMENT}\n{inner}\n{END_MEMBUNDLE_COMMENT}\n"
        )
        omitted = f"{huge}\n\n{section}{inner}\n"
        reversed_delims = (
            f"{huge}\n\n{section}"
            f"{END_MEMBUNDLE_COMMENT}\n{inner}\n{BEGIN_MEMBUNDLE_COMMENT}\n"
        )
        only_begin = (
            f"{huge}\n\n{section}{BEGIN_MEMBUNDLE_COMMENT}\n{inner}\n"
        )
        only_end = f"{huge}\n\n{section}{inner}\n{END_MEMBUNDLE_COMMENT}\n"
        ordered_result, ordered_payload = _lint_structured(
            ws, ordered, "ordered.md", budget=SAMPLE_SMALL_CAP
        )
        _, omitted_payload = _lint_structured(ws, omitted, "omitted.md", budget=SAMPLE_SMALL_CAP)
        assert_rule_only(omitted_payload, "MBG-005")
        omitted_human, _ = _lint_human(ws, omitted, "omitted-human.md", budget=SAMPLE_SMALL_CAP)
        require_agents_failure(omitted_human)
        assert_working_memory_estimate_sorts_below(ordered_payload, omitted_payload)
        print(
            f"[F10] ordered delimiter lint exit={ordered_result.returncode} "
            f"(MBG-005 pass/fail on the few-word inner is not checked here)",
            flush=True,
        )
        for label, body in (
            ("reversed", reversed_delims),
            ("begin", only_begin),
            ("end", only_end),
        ):
            _, payload = _lint_structured(ws, body, f"{label}.md", budget=SAMPLE_SMALL_CAP)
            assert_rule_only(payload, "MBG-005")
            human, _ = _lint_human(ws, body, f"{label}-human.md", budget=SAMPLE_SMALL_CAP)
            require_agents_failure(human)
        inner_huge = ascii_agents_body(inner=huge)
        _, inner_payload = _lint_structured(ws, inner_huge, "inner-huge.md", budget=SAMPLE_SMALL_CAP)
        assert_rule_only(inner_payload, "MBG-005")


def test_human_lint_prints_budget_400_versus_small_cap():
    with workspace() as ws:
        token = budget_safe_token("hb")
        # Few-word inner: omit and the small cap share findings/status, so the
        # printed in-force cap is the only difference between the reports.
        under = ascii_agents_body(inner=f"keep compact {token}")
        write_agents(ws, "under.md", under)
        omit = run_agents_lint(ws, "under.md")
        cap20 = run_agents_lint(ws, "under.md", budget=SAMPLE_SMALL_CAP)
        cap400 = run_agents_lint(ws, "under.md", budget=400)
        cap0 = run_agents_lint(ws, "under.md", budget=0)
        cap_neg = run_agents_lint(ws, "under.md", budget=-1)
        caps = {
            "omit": human_lint_budget(omit),
            "cap20": human_lint_budget(cap20),
            "cap400": human_lint_budget(cap400),
            "cap0": human_lint_budget(cap0),
            "cap-1": human_lint_budget(cap_neg),
        }
        print(f"[F10] human in-force budgets={caps!r}", flush=True)
        assert caps["omit"] == 400, (
            f"omit-cap human report does not print Budget 400: {caps['omit']}"
        )
        assert caps["cap20"] == SAMPLE_SMALL_CAP, (
            f"small-cap human report does not print Budget {SAMPLE_SMALL_CAP}: "
            f"{caps['cap20']}"
        )
        assert caps["cap400"] == 400, (
            f"budget-400 human report does not print Budget 400: {caps['cap400']}"
        )
        assert caps["cap0"] == 400, (
            f"budget-0 human report does not print Budget 400: {caps['cap0']}"
        )
        assert caps["cap-1"] == 400, (
            f"budget--1 human report does not print Budget 400: {caps['cap-1']}"
        )
        arrow = ascii_agents_body(extra=f"flow {token} ➔ next\n")
        fail, _fail_report = _lint_human(ws, arrow, "arrow.md")
        require_agents_failure(fail)
        fail_cap = human_lint_budget(fail)
        assert fail_cap == 400, (
            f"human MBG-001 fail with omit cap does not print Budget 400: {fail_cap}"
        )


def test_structured_lint_reports_token_statistics_grouping():
    with workspace() as ws:
        token = budget_safe_token("ts")
        short = ascii_agents_body(inner=f"keep compact {token}")
        write_agents(ws, "short.md", short)
        omit_result = run_agents_lint(ws, "short.md", structured=True)
        require_agents_success(omit_result)
        omit = parse_structured_lint(omit_result)
        cap20 = parse_structured_lint(
            run_agents_lint(ws, "short.md", structured=True, budget=SAMPLE_SMALL_CAP)
        )
        cap400 = parse_structured_lint(
            run_agents_lint(ws, "short.md", structured=True, budget=400)
        )
        cap0 = parse_structured_lint(
            run_agents_lint(ws, "short.md", structured=True, budget=0)
        )
        cap_neg = parse_structured_lint(
            run_agents_lint(ws, "short.md", structured=True, budget=-1)
        )
        for rule_id in MBG_RULE_IDS:
            assert_rule_absent(omit, rule_id)
        assert_in_force_cap_differs(
            omit, cap20, also_400=(cap400, cap0, cap_neg)
        )
        arrow = ascii_agents_body(
            inner=f"keep compact {token}",
            extra=f"flow {token} ➔ next\n",
        )
        _, arrow_payload = _lint_structured(ws, arrow, "arrow.md")
        assert_rule_only(arrow_payload, "MBG-001")
        huge = _under_400_delimited(token)
        _, huge20 = _lint_structured(ws, huge, "huge.md", budget=SAMPLE_SMALL_CAP)
        assert_rule_only(huge20, "MBG-005")
        assert_structured_pass_fail_distinct(omit, arrow_payload)
        assert_exceeded_mark_matches_mbg005(omit, arrow_payload, huge20)


# ---------------------------------------------------------------------------
# F. Lint entry, structured report, missing file
# ---------------------------------------------------------------------------


def test_lint_defaults_to_cwd_agents_md_not_knowledge():
    with workspace() as ws:
        token = budget_safe_token("def")
        passing = ascii_agents_body(extra=f"note {token}\n")
        failing = ascii_agents_body(extra=f"flow {token} ➔ next\n")
        write_agents(ws, "AGENTS.md", passing)
        knowledge = ws.path / "knowledge"
        knowledge.mkdir()
        write_agents(ws, "knowledge/AGENTS.md", failing)
        named_human = run_agents_lint(ws, "knowledge/AGENTS.md")
        require_agents_failure(named_human)
        named_structured = run_agents_lint(ws, "knowledge/AGENTS.md", structured=True)
        named_payload = parse_structured_lint(named_structured)
        assert_rule_only(named_payload, "MBG-001")
        result = run_agents_lint(ws)
        require_agents_success(result)
        structured = run_agents_lint(ws, structured=True)
        require_agents_success(structured)
        payload = parse_structured_lint(structured)
        for rule_id in MBG_RULE_IDS:
            assert_rule_absent(payload, rule_id)
        write_agents(ws, "AGENTS.md", failing)
        omit_fail = run_agents_lint(ws)
        require_agents_failure(omit_fail)
        omit_fail_structured = run_agents_lint(ws, structured=True)
        omit_fail_payload = parse_structured_lint(omit_fail_structured)
        assert_rule_only(omit_fail_payload, "MBG-001")


def test_lint_named_path_not_cwd_decoy():
    with workspace() as ws:
        token = budget_safe_token("named")
        decoy = ascii_agents_body(extra=f"decoy {token}\n")
        named = ascii_agents_body(extra=f"flow {token} ➔ next\n")
        write_agents(ws, "AGENTS.md", decoy)
        (ws.path / "sub").mkdir()
        write_agents(ws, "sub/notes.md", named)
        result = run_agents_lint(ws, "sub/notes.md", structured=True)
        payload = parse_structured_lint(result)
        assert_rule_only(payload, "MBG-001")
        decoy_result = run_agents_lint(ws, structured=True)
        require_agents_success(decoy_result)
        decoy_payload = parse_structured_lint(decoy_result)
        assert_rule_absent(decoy_payload, "MBG-001")


def test_lint_missing_file_does_not_succeed():
    with workspace() as ws:
        missing = run_agents_lint(ws)
        require_agents_failure(missing)
        named_missing = run_agents_lint(ws, "missing-agents.md")
        require_agents_failure(named_missing)
        token = budget_safe_token("live")
        write_agents(ws, "AGENTS.md", ascii_agents_body(extra=f"note {token}\n"))
        live = run_agents_lint(ws)
        require_agents_success(live)


def test_structured_lint_reports_rule_identifiers_on_fail_not_on_pass():
    with workspace() as ws:
        token = budget_safe_token("st")
        fail_body = ascii_agents_body(extra=f"flow {token} ➔ next\n")
        pass_body = ascii_agents_body(extra=f"flow {token} -> next\n")
        _, fail_payload = _lint_structured(ws, fail_body, "fail.md")
        assert_rule_only(fail_payload, "MBG-001")
        ok_result, ok_payload = _lint_structured(ws, pass_body, "pass.md")
        require_agents_success(ok_result)
        for rule_id in MBG_RULE_IDS:
            assert_rule_absent(ok_payload, rule_id)
        inner_words = budget_word_list(30, "cnt")
        inner = " ".join(inner_words)
        one_mark = f"flow {token} ➔ one"
        two_mark = f"flow {token} ➔ two"
        one_body = ascii_agents_body(inner=inner, extra=f"{one_mark}\n")
        two_body = ascii_agents_body(
            inner=inner, extra=f"{one_mark}\n{two_mark}\n"
        )
        _, one_payload = _lint_structured(ws, one_body, "count-one.md")
        assert_rule_only(one_payload, "MBG-001")
        _, two_payload = _lint_structured(ws, two_body, "count-two.md")
        assert_rule_only(two_payload, "MBG-001")
        assert_structured_counts_greater(
            one_payload,
            two_payload,
            rule_id="MBG-001",
        )
        assert_warning_count_unchanged_when_errors_increase(
            one_payload, two_payload
        )


# ---------------------------------------------------------------------------
# G. Init domain profiles, overwrite, name
# ---------------------------------------------------------------------------


def _read_init_agents(ws, root: str | Path | None = None) -> str:
    path = (ws.path / root / "AGENTS.md") if root is not None else ws.path / "AGENTS.md"
    text = path.read_text(encoding="utf-8")
    print(f"[F10] init AGENTS.md at {path} bytes={len(text.encode('utf-8'))}", flush=True)
    return text


def test_init_legal_domain_codex_differs_from_software():
    with workspace() as ws:
        legal_root, soft_root = budget_safe_tokens("lg", "sw")
        legal_result = run_agents_init(ws, legal_root, domain="legal")
        require_agents_success(legal_result)
        soft_result = run_agents_init(ws, soft_root, domain="software")
        require_agents_success(soft_result)
        legal_region = domain_codex_region(_read_init_agents(ws, legal_root))
        soft_region = domain_codex_region(_read_init_agents(ws, soft_root))
        print(
            f"[F10] legal mentions={mentions_profile(legal_region, 'legal')} "
            f"software mentions={mentions_profile(soft_region, 'software')}",
            flush=True,
        )
        assert mentions_profile(legal_region, "legal"), (
            f"legal Domain Codex does not mention privacy/compliance: {legal_region!r}"
        )
        assert mentions_profile(soft_region, "software"), (
            f"software Domain Codex does not mention clean architecture/TDD: "
            f"{soft_region!r}"
        )
        assert legal_region != soft_region, (
            "legal and software Domain Codex regions are not observably different"
        )


def test_init_research_coaching_books_profiles_mention_named_tokens():
    with workspace() as ws:
        research, coaching, books, software = budget_safe_tokens("rs", "ch", "bk", "sf")
        for root, domain in (
            (research, "research"),
            (coaching, "coaching"),
            (books, "books"),
            (software, "software"),
        ):
            result = run_agents_init(ws, root, domain=domain)
            require_agents_success(result)
        research_region = domain_codex_region(_read_init_agents(ws, research))
        coaching_region = domain_codex_region(_read_init_agents(ws, coaching))
        books_region = domain_codex_region(_read_init_agents(ws, books))
        software_region = domain_codex_region(_read_init_agents(ws, software))
        assert mentions_profile(research_region, "research"), (
            f"research Domain Codex does not mention citation integrity: "
            f"{research_region!r}"
        )
        assert mentions_profile(coaching_region, "coaching"), (
            f"coaching Domain Codex does not mention ICF ethics: {coaching_region!r}"
        )
        assert mentions_profile(books_region, "books"), (
            f"books Domain Codex does not mention canon/spoilers: {books_region!r}"
        )
        assert research_region != software_region
        assert coaching_region != software_region
        assert books_region != software_region


def test_init_default_and_unknown_domain_use_software_profile():
    with workspace() as ws:
        name = budget_safe_token("nm")
        omit, explicit, unknown, unique = budget_safe_tokens("om", "ex", "uk", "uq")
        require_agents_success(run_agents_init(ws, omit, name=name))
        require_agents_success(
            run_agents_init(ws, explicit, domain="software", name=name)
        )
        require_agents_success(
            run_agents_init(ws, unknown, domain=SAMPLE_UNKNOWN_PROFILE, name=name)
        )
        runtime_unknown = budget_safe_token("dom")
        require_agents_success(
            run_agents_init(ws, unique, domain=runtime_unknown, name=name)
        )
        for root in (omit, explicit, unknown, unique):
            region = domain_codex_region(_read_init_agents(ws, root))
            assert mentions_profile(region, "software"), (
                f"root {root} is not the software class: {region!r}"
            )


def test_init_writes_delimiters_mermaid_and_project_name():
    with workspace() as ws:
        name_a, name_b, root_a, root_b = budget_safe_tokens("na", "nb", "ra", "rb")
        require_agents_success(run_agents_init(ws, root_a, name=name_a, domain="legal"))
        require_agents_success(run_agents_init(ws, root_b, name=name_b, domain="legal"))
        text_a = _read_init_agents(ws, root_a)
        text_b = _read_init_agents(ws, root_b)
        assert BEGIN_MEMBUNDLE_COMMENT in text_a, "BEGIN delimiter comment is missing"
        assert END_MEMBUNDLE_COMMENT in text_a, "END delimiter comment is missing"
        extract_membundle_agents_block(text_a)
        region = domain_codex_region(text_a)
        assert "mermaid" in region.lower(), (
            f"Domain Codex region does not mention Mermaid: {region!r}"
        )
        heading_a = first_heading_text(text_a)
        heading_b = first_heading_text(text_b)
        print(
            f"[F10] heading_a={heading_a!r} heading_b={heading_b!r}",
            flush=True,
        )
        assert name_a in heading_a, (
            f"project name is not in the first heading: {heading_a!r}"
        )
        assert name_b in heading_b, (
            f"other project name is not in the first heading: {heading_b!r}"
        )
        assert heading_a != heading_b, "different names produced the same first heading"
        assert text_a != text_b, "different names produced the same file"


def test_init_defaults_to_cwd_not_knowledge():
    with workspace() as ws:
        knowledge = ws.path / "knowledge"
        knowledge.mkdir()
        result = run_agents_init(ws, domain="legal")
        require_agents_success(result)
        assert path_is_file(ws.path / "AGENTS.md"), (
            "init did not write AGENTS.md in the current directory"
        )
        assert not path_is_file(knowledge / "AGENTS.md"), (
            "init wrote AGENTS.md under knowledge/ when the default root is cwd"
        )
        named = budget_safe_token("nr")
        named_result = run_agents_init(ws, named, domain="legal")
        require_agents_success(named_result)
        assert path_is_file(ws.path / named / "AGENTS.md"), (
            f"named-root init did not write under {named}"
        )


def test_second_init_without_overwrite_fails_overwrite_replaces():
    with workspace() as ws:
        root = budget_safe_token("ow")
        first = run_agents_init(ws, root, domain="software")
        require_agents_success(first)
        path = ws.path / root / "AGENTS.md"
        assert path_is_file(path), "first init did not write AGENTS.md"
        refused = run_agents_init(ws, root, domain="software")
        require_agents_failure(refused)


# ---------------------------------------------------------------------------
# H. Link four SSoT mappings
# ---------------------------------------------------------------------------


def _write_canonical_agents(ws, root: str | Path | None = None) -> Path:
    body, _token = unique_passing_agents()
    rel = Path(root) / "AGENTS.md" if root is not None else Path("AGENTS.md")
    return write_agents(ws, rel, body)


def test_link_creates_four_named_symlinks_and_github_dir():
    with workspace() as ws:
        _positive_symlink_control(ws)
        root = budget_safe_token("lk")
        _write_canonical_agents(ws, root)
        result = run_agents_link(ws, root)
        require_agents_success(result)
        base = ws.path / root
        assert_named_ssot_symlinks(base)
        assert path_is_dir(base / ".github"), (
            "link did not create .github/ for the copilot mapping"
        )
        copilot = base / ".github" / "copilot-instructions.md"
        agents = base / "AGENTS.md"
        resolved = copilot.resolve()
        print(
            f"[F10] copilot resolved={resolved} agents={agents.resolve()}",
            flush=True,
        )
        assert resolved.samefile(agents), (
            f"copilot mapping resolved to {resolved}, not root AGENTS.md"
        )


def test_link_is_symlink_not_a_copy():
    with workspace() as ws:
        _positive_symlink_control(ws)
        root = budget_safe_token("cp")
        agents_path = _write_canonical_agents(ws, root)
        result = run_agents_link(ws, root)
        require_agents_success(result)
        base = ws.path / root
        claude = base / "CLAUDE.md"
        assert path_is_symlink(claude), f"CLAUDE.md is not a symlink: {claude}"
        copy = base / "copy.md"
        copy.write_bytes(agents_path.read_bytes())
        assert not path_is_symlink(copy), (
            "a contents-equal regular file was classified as a symlink"
        )
        assert_ssot_mapping_state(base, "CLAUDE.md", kind="correct")


def test_link_leaves_correct_symlink_and_creates_the_rest():
    with workspace() as ws:
        root = budget_safe_token("rest")
        _write_canonical_agents(ws, root)
        base = ws.path / root
        os.symlink("AGENTS.md", base / "CLAUDE.md")
        assert_ssot_mapping_state(base, "CLAUDE.md", kind="correct")
        result = run_agents_link(ws, root)
        require_agents_success(result)
        assert_named_ssot_symlinks(base)
        all_root = budget_safe_token("all")
        _write_canonical_agents(ws, all_root)
        plant_ssot_links(ws.path / all_root)
        again = run_agents_link(ws, all_root)
        require_agents_success(again)
        assert_named_ssot_symlinks(ws.path / all_root)


def test_link_refuses_regular_or_wrong_target_unless_overwrite():
    with workspace() as ws:
        regular_root = budget_safe_token("rg")
        _write_canonical_agents(ws, regular_root)
        base = ws.path / regular_root
        unique_bytes = budget_safe_token("reg").encode("ascii") + b"\n"
        (base / "CLAUDE.md").write_bytes(unique_bytes)
        refused = run_agents_link(ws, regular_root)
        require_agents_failure(refused)
        assert_ssot_mapping_state(base, "CLAUDE.md", kind="regular")
        forced = run_agents_link(ws, regular_root, overwrite=True)
        require_agents_success(forced)
        assert_ssot_mapping_state(base, "CLAUDE.md", kind="correct")
        wrong_root = budget_safe_token("wr")
        _write_canonical_agents(ws, wrong_root)
        wbase = ws.path / wrong_root
        other = wbase / budget_safe_token("tgt")
        other.write_text("other\n", encoding="utf-8")
        os.symlink(other.name, wbase / "CLAUDE.md")
        assert_ssot_mapping_state(wbase, "CLAUDE.md", kind="wrong_target")
        refused_wrong = run_agents_link(ws, wrong_root)
        require_agents_failure(refused_wrong)
        assert_ssot_mapping_state(wbase, "CLAUDE.md", kind="wrong_target")
        forced_wrong = run_agents_link(ws, wrong_root, overwrite=True)
        require_agents_success(forced_wrong)
        assert_ssot_mapping_state(wbase, "CLAUDE.md", kind="correct")


def test_link_check_only_reports_without_creating_and_regular_file_is_invalid():
    with workspace() as ws:
        body, agents_token = unique_passing_agents()
        missing_root = budget_safe_token("ms")
        valid_root = budget_safe_token("vl")
        claude_root = budget_safe_token("cl")
        cursor_root = budget_safe_token("cu")
        write_agents(ws, Path(missing_root) / "AGENTS.md", body)
        write_agents(ws, Path(valid_root) / "AGENTS.md", body)
        write_agents(ws, Path(claude_root) / "AGENTS.md", body)
        write_agents(ws, Path(cursor_root) / "AGENTS.md", body)
        before = snapshot_tree(ws.path / missing_root)
        check_missing = run_agents_link(ws, missing_root, check_only=True)
        after = snapshot_tree(ws.path / missing_root)
        print(
            f"[F10] check-only missing created={after.keys() - before.keys()}",
            flush=True,
        )
        base = ws.path / missing_root
        for rel in ("CLAUDE.md", ".cursorrules", ".windsurfrules"):
            assert_ssot_mapping_state(base, rel, kind="missing")
        assert_ssot_mapping_state(
            base, ".github/copilot-instructions.md", kind="missing"
        )
        # One mapping line per link path (link_check_marks asserts each).
        link_check_marks(check_missing)
        create = run_agents_link(ws, missing_root)
        require_agents_success(create)
        assert_named_ssot_symlinks(base)
        plant_ssot_links(ws.path / valid_root)
        valid = run_agents_link(ws, valid_root, check_only=True)
        require_agents_success(valid)
        valid_marks = link_check_marks(valid)
        plant_ssot_links(ws.path / claude_root, regular="CLAUDE.md")
        plant_ssot_links(ws.path / cursor_root, regular=".cursorrules")
        claude_check = run_agents_link(ws, claude_root, check_only=True)
        cursor_check = run_agents_link(ws, cursor_root, check_only=True)
        assert_ssot_mapping_state(ws.path / claude_root, "CLAUDE.md", kind="regular")
        assert_ssot_mapping_state(
            ws.path / cursor_root, ".cursorrules", kind="regular"
        )
        claude_marks = link_check_marks(claude_check)
        cursor_marks = link_check_marks(cursor_check)
        print(
            f"[F10] valid={valid_marks!r} claude={claude_marks!r} "
            f"cursor={cursor_marks!r}",
            flush=True,
        )
        assert all(mark == "✓" for mark in valid_marks.values()), (
            f"all-valid check-only report marks a mapping invalid: {valid_marks!r}"
        )
        assert claude_marks["CLAUDE.md"] == "✗", (
            f"regular CLAUDE.md is not marked invalid: {claude_marks!r}"
        )
        assert claude_marks != valid_marks, (
            "regular CLAUDE.md check-only report matches the all-valid report"
        )
        assert cursor_marks[".cursorrules"] == "✗", (
            f"regular .cursorrules is not marked invalid: {cursor_marks!r}"
        )
        assert cursor_marks != claude_marks, (
            "regular .cursorrules and CLAUDE.md check-only reports mark the "
            "same mappings"
        )


def test_link_without_agents_md_does_not_succeed_and_creates_no_links():
    with workspace() as ws:
        _positive_symlink_control(ws)
        missing = budget_safe_token("na")
        (ws.path / missing).mkdir()
        result = run_agents_link(ws, missing)
        require_agents_failure(result)
        present = budget_safe_token("np")
        _write_canonical_agents(ws, present)
        live = run_agents_link(ws, present)
        require_agents_success(live)
        assert_named_ssot_symlinks(ws.path / present)


# ---------------------------------------------------------------------------
# I. Check = lint plus all four SSoT mappings
# ---------------------------------------------------------------------------


def test_agents_check_passes_only_when_lint_and_all_four_links_pass():
    with workspace() as ws:
        root = budget_safe_token("ck")
        body, _token = unique_passing_agents()
        write_agents(ws, Path(root) / "AGENTS.md", body)
        plant_ssot_links(ws.path / root)
        result = run_agents_check(ws, root)
        require_agents_success(result)
        no_links = budget_safe_token("nl")
        write_agents(ws, Path(no_links) / "AGENTS.md", body)
        missing_links = run_agents_check(ws, no_links)
        require_agents_failure(missing_links)


def test_agents_check_fails_on_lint_failure_even_with_links():
    with workspace() as ws:
        root = budget_safe_token("lf")
        token = budget_safe_token("bad")
        clean, _clean_token = unique_passing_agents()
        write_agents(ws, Path(root) / "AGENTS.md", clean)
        plant_ssot_links(ws.path / root)
        require_agents_success(run_agents_check(ws, root))
        write_agents(
            ws,
            Path(root) / "AGENTS.md",
            ascii_agents_body(extra=f"flow {token} ➔ next\n"),
        )
        result = run_agents_check(ws, root)
        require_agents_failure(result)


def test_agents_check_fails_when_a_mapping_is_missing_regular_or_wrong():
    mappings = (
        "CLAUDE.md",
        ".cursorrules",
        ".windsurfrules",
        ".github/copilot-instructions.md",
    )
    with workspace() as ws:
        body, _token = unique_passing_agents()
        for rel in mappings:
            missing_root = budget_safe_token("om")
            write_agents(ws, Path(missing_root) / "AGENTS.md", body)
            plant_ssot_links(ws.path / missing_root, omit=rel)
            require_agents_failure(run_agents_check(ws, missing_root))
            regular_root = budget_safe_token("rr")
            write_agents(ws, Path(regular_root) / "AGENTS.md", body)
            plant_ssot_links(ws.path / regular_root, regular=rel)
            require_agents_failure(run_agents_check(ws, regular_root))
            wrong_root = budget_safe_token("ww")
            write_agents(ws, Path(wrong_root) / "AGENTS.md", body)
            plant_ssot_links(ws.path / wrong_root)
            other = ws.path / wrong_root / budget_safe_token("wt")
            other.write_text("other\n", encoding="utf-8")
            dest = ws.path / wrong_root / rel
            if dest.exists() or dest.is_symlink():
                dest.unlink()
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(os.path.relpath(other, dest.parent), dest)
            require_agents_failure(run_agents_check(ws, wrong_root))
        good_root = budget_safe_token("gg")
        write_agents(ws, Path(good_root) / "AGENTS.md", body)
        plant_ssot_links(ws.path / good_root)
        require_agents_success(run_agents_check(ws, good_root))


def test_agents_check_fails_when_agents_md_is_missing_even_with_links():
    with workspace() as ws:
        root = budget_safe_token("dn")
        (ws.path / root).mkdir()
        plant_ssot_links(ws.path / root)
        result = run_agents_check(ws, root)
        require_agents_failure(result)
        body, _token = unique_passing_agents()
        write_agents(ws, Path(root) / "AGENTS.md", body)
        live = run_agents_check(ws, root)
        require_agents_success(live)


def test_agents_check_uses_that_roots_agents_md_not_the_parent():
    with workspace() as ws:
        parent = budget_safe_token("pr")
        child = f"{parent}/child"
        passing, _token = unique_passing_agents()
        failing = ascii_agents_body(extra="flow ➔ next\n")
        write_agents(ws, Path(parent) / "AGENTS.md", passing)
        plant_ssot_links(ws.path / parent)
        write_agents(ws, Path(child) / "AGENTS.md", failing)
        plant_ssot_links(ws.path / child)
        require_agents_success(run_agents_check(ws, parent))
        require_agents_failure(run_agents_check(ws, child))


# ---------------------------------------------------------------------------
# J. Validate's optional agents check is the same check
# ---------------------------------------------------------------------------


def test_validate_agents_option_agrees_with_agents_check_on_lint_and_ssot():
    with workspace() as ws:
        proj = budget_safe_token("pj")
        bundle = f"{proj}/knowledge"
        seed_validatable_bundle(ws, bundle, [])
        passing, _token = unique_passing_agents()
        write_agents(ws, Path(proj) / "AGENTS.md", passing)
        plant_ssot_links(ws.path / proj)
        require_agents_success(run_agents_check(ws, proj))
        require_cli_status_0(run_validate(ws, bundle, agents=True))
        failing = ascii_agents_body(extra="flow ➔ next\n")
        write_agents(ws, Path(proj) / "AGENTS.md", failing)
        plant_ssot_links(ws.path / proj)
        require_agents_failure(run_agents_check(ws, proj))
        require_cli_status_1(run_validate(ws, bundle, agents=True))
        require_cli_status_0(run_validate(ws, bundle, agents=False))
        write_agents(ws, Path(proj) / "AGENTS.md", passing)
        plant_ssot_links(ws.path / proj, omit="CLAUDE.md")
        require_agents_failure(run_agents_check(ws, proj))
        require_cli_status_1(run_validate(ws, bundle, agents=True))
        require_cli_status_0(run_validate(ws, bundle, agents=False))
