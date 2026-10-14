# feature: F07
"""Acceptance tests: opt-in lint-policy-effect plugin."""

from __future__ import annotations

import pytest

from _harness import DEFAULT_COPY_DEST, workspace
from F01_helpers import (
    EFFECT_RULE_NAMES,
    lint_policy_findings,
    copied_effect_entry,
    lint_generic,
    require_copied_layout,
    snippet_manual_tag_comparison,
)
from F07_helpers import (
    RULE_CONSTRUCT,
    RULE_ERR_TAG,
    RULE_MATCH,
    RULE_SVC,
    RULE_TAG_CMP,
    application_rel,
    assert_effect_classified_not_fired,
    assert_effect_fired,
    assert_effect_identifies_span,
    assert_only_effect_rule,
    assert_silent_f07,
    fire_application_make_import,
    fire_error_tag_only,
    fire_public_and_twin,
    fire_public_only,
    fire_spelled_catch_handler,
    fire_unique,
    generated_make_uppercase,
    lint_f07,
    lint_f07_source,
    next_effect_rule,
    run_effect_fix,
    silent_all,
    snippet_aliased_match_not,
    snippet_aliased_match_when,
    snippet_catch_error_comparison_expression,
    snippet_catch_tag_nested_reason,
    snippet_catch_tagged_error_construct,
    snippet_catch_tagged_reason_construct,
    snippet_chained_same_value,
    snippet_computed_tag_equality,
    snippet_default_make_import,
    snippet_different_names_ternary,
    snippet_effect_catch_error_comparison,
    snippet_effect_catch_function_error,
    snippet_effect_catch_reason_switch,
    snippet_effect_catch_tag,
    snippet_effect_catchall_error_comparison,
    snippet_effect_catchall_reason_comparison,
    snippet_effect_catchif_error_switch,
    snippet_false_chain_nested_true,
    snippet_import_make_alone,
    snippet_loose_inequality_chain,
    snippet_loose_numeric_chain,
    snippet_make_lowercase_import,
    snippet_make_uppercase_import,
    snippet_manual_tagged_object,
    snippet_match_not,
    snippet_match_when,
    snippet_match_when_plus_non_match_tagged,
    snippet_member_chain,
    snippet_neighbor_imports,
    snippet_new_not_found,
    snippet_non_literal_nested,
    snippet_package_make_import,
    snippet_path_alias_make_import,
    snippet_predicate_is_tagged,
    snippet_public_runtime_import,
    snippet_ready_make,
    snippet_renamed_effect_catch,
    snippet_renamed_effect_catchall_reason,
    snippet_reverse_named_alias,
    snippet_reversed_computed_inequality,
    snippet_reversed_identifier_tag_equality,
    snippet_reversed_string_chain,
    snippet_single_ternary,
    snippet_static_constructor_call,
    snippet_status_comparison,
    snippet_status_then_tag,
    snippet_switch_on_tag,
    snippet_tag_loose_equality,
    snippet_tag_loose_inequality,
    snippet_tag_member_equality,
    snippet_tag_then_status,
    snippet_tag_vs_non_string,
    snippet_tag_vs_template,
    snippet_tag_vs_variable,
    snippet_template_mixed_chain,
    snippet_template_same_order_chain,
    snippet_top_level_error_tag,
    snippet_true_branch_nest,
    snippet_variable_tag_in_catch,
    snippet_variable_tag_object,
    suffix_file_rel,
    unique_violator,
    write_f07_source,
)


@pytest.fixture(scope="module")
def copied_plugin():
    with workspace() as ws:
        result = ws.copy()
        generic = require_copied_layout(result, DEFAULT_COPY_DEST, cwd=ws.path)
        effect = str(copied_effect_entry(DEFAULT_COPY_DEST, cwd=ws.path).resolve())
        print(f"F07 copied generic={generic} effect={effect}", flush=True)
        yield ws, generic, effect


# ---------------------------------------------------------------------------
# A. Opt-in load and subset enablement
# ---------------------------------------------------------------------------


def test_generic_plugin_alone_emits_no_effect_diagnostics_on_tag_comparison(
    copied_plugin,
):
    ws, generic, effect = copied_plugin
    public = snippet_manual_tag_comparison()
    twin = snippet_tag_member_equality(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path = write_f07_source(ws, source, prefix=f"generic-only-{label}")
        silent = lint_generic(ws, [path], [], generic)
        print(f"generic-only {label} exit={silent.returncode}", flush=True)
        assert_silent_f07(silent)
        fired = lint_f07(ws, [path], effect, rules=[RULE_TAG_CMP])
        assert_effect_fired(fired, RULE_TAG_CMP)


def test_effect_plugin_with_no_rules_enabled_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    path = write_f07_source(
        ws, snippet_manual_tag_comparison(), prefix="effect-no-rules"
    )
    silent = lint_f07(ws, [path], effect, rules=())
    assert_silent_f07(silent)
    fired = lint_f07(ws, [path], effect, rules=[RULE_TAG_CMP])
    assert_effect_fired(fired, RULE_TAG_CMP)


def test_only_no_manual_tag_comparison_enabled_reports_that_rule(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_manual_tag_comparison(),
        RULE_TAG_CMP,
        prefix="only-tag-cmp",
        rules=[RULE_TAG_CMP],
    )


def test_only_tagged_construction_enabled_is_silent_on_tag_comparison(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    source = snippet_manual_tag_comparison()
    fire_unique(
        ws,
        effect,
        source,
        RULE_TAG_CMP,
        prefix="wrong-subset-live",
        rules=[RULE_TAG_CMP],
    )
    silent_all_path, result = lint_f07_source(
        ws,
        effect,
        source,
        prefix="wrong-subset",
        rules=[RULE_CONSTRUCT],
    )
    print(f"wrong-subset path={silent_all_path}", flush=True)
    assert_silent_f07(result)


def test_all_five_enabled_reports_only_the_unique_rule(copied_plugin):
    ws, _generic, effect = copied_plugin
    for rule_name in EFFECT_RULE_NAMES:
        source, rel, ext = unique_violator(rule_name)
        fire_unique(
            ws,
            effect,
            source,
            rule_name,
            prefix=f"all-five-{rule_name}",
            ext=ext,
            rel=rel,
        )


def test_two_effect_rules_enabled_still_only_unique_rule(copied_plugin):
    ws, _generic, effect = copied_plugin
    for rule_name in EFFECT_RULE_NAMES:
        source, rel, ext = unique_violator(rule_name, twin=True)
        other = next_effect_rule(rule_name)
        fire_unique(
            ws,
            effect,
            source,
            rule_name,
            prefix=f"two-rules-{rule_name}",
            ext=ext,
            rel=rel,
            rules=[rule_name, other],
        )


def test_effect_finding_is_not_attributed_to_the_generic_plugin(copied_plugin):
    ws, generic, effect = copied_plugin
    source, rel, ext = unique_violator(RULE_TAG_CMP, twin=True)
    path, result = lint_f07_source(
        ws,
        effect,
        source,
        prefix="attr",
        ext=ext,
        rel=rel,
        generic_specifier=generic,
        generic_rules=["no-array-filter-map"],
    )
    print(f"attribution path={path}", flush=True)
    assert_only_effect_rule(result, RULE_TAG_CMP, allow_generic=True)
    generic_ids = lint_policy_findings(result)
    assert f"lint-policy/{RULE_TAG_CMP}" not in generic_ids, generic_ids


# ---------------------------------------------------------------------------
# B. no-manual-tag-comparison reports
# ---------------------------------------------------------------------------


def test_tag_member_strict_equality_to_string_literal_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_manual_tag_comparison(),
        snippet_tag_member_equality(twin=True),
        RULE_TAG_CMP,
        prefix="tag-eq",
    )
    print(f"tag-eq public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_TAG_CMP)
    assert_only_effect_rule(twin_result, RULE_TAG_CMP)


def test_reversed_inequality_against_computed_tag_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_reversed_computed_inequality(),
        snippet_reversed_computed_inequality(twin=True),
        RULE_TAG_CMP,
        prefix="tag-rev-computed",
    )
    print(f"tag-rev-computed public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_TAG_CMP)
    assert_only_effect_rule(twin_result, RULE_TAG_CMP)


def test_computed_tag_member_strict_equality_to_string_literal_reports(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_computed_tag_equality(),
        snippet_computed_tag_equality(twin=True),
        RULE_TAG_CMP,
        prefix="tag-computed-eq",
    )
    print(f"tag-computed-eq public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_TAG_CMP)
    assert_only_effect_rule(twin_result, RULE_TAG_CMP)


def test_reversed_identifier_tag_equality_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_reversed_identifier_tag_equality(),
        snippet_reversed_identifier_tag_equality(twin=True),
        RULE_TAG_CMP,
        prefix="tag-rev-ident",
    )
    print(f"tag-rev-ident public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_TAG_CMP)
    assert_only_effect_rule(twin_result, RULE_TAG_CMP)


def test_tag_member_loose_equality_to_string_literal_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_tag_loose_equality(),
        snippet_tag_loose_equality(twin=True),
        RULE_TAG_CMP,
        prefix="tag-loose",
    )
    print(f"tag-loose public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_TAG_CMP)
    assert_only_effect_rule(twin_result, RULE_TAG_CMP)


def test_tag_member_loose_inequality_to_string_literal_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_tag_loose_inequality(),
        snippet_tag_loose_inequality(twin=True),
        RULE_TAG_CMP,
        prefix="tag-neq",
    )
    print(f"tag-neq public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_TAG_CMP)
    assert_only_effect_rule(twin_result, RULE_TAG_CMP)


def test_switch_on_tag_member_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_switch_on_tag(),
        snippet_switch_on_tag(twin=True),
        RULE_TAG_CMP,
        prefix="tag-switch",
    )
    print(f"tag-switch public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_TAG_CMP)
    assert_only_effect_rule(twin_result, RULE_TAG_CMP)


def test_switch_on_computed_tag_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_switch_on_tag(computed=True),
        snippet_switch_on_tag(twin=True, computed=True),
        RULE_TAG_CMP,
        prefix="tag-switch-computed",
    )
    print(f"tag-switch-computed public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_TAG_CMP)
    assert_only_effect_rule(twin_result, RULE_TAG_CMP)


# ---------------------------------------------------------------------------
# C. no-manual-tag-comparison allowed counterparts
# ---------------------------------------------------------------------------


def test_predicate_is_tagged_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_TAG_CMP, prefix="pred-live")
    silent_all(ws, effect, snippet_predicate_is_tagged(), prefix="pred-public")
    silent_all(
        ws, effect, snippet_predicate_is_tagged(twin=True), prefix="pred-twin"
    )


def test_match_when_tag_handler_is_silent_for_comparison(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_TAG_CMP, prefix="match-when-cmp-tag")
    fire_public_only(ws, effect, RULE_CONSTRUCT, prefix="match-when-cmp-obj")
    silent_all(ws, effect, snippet_match_when(), prefix="match-when-cmp")


def test_status_member_comparison_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_TAG_CMP, prefix="status-live")
    silent_all(ws, effect, snippet_status_comparison(), prefix="status-public")
    silent_all(
        ws, effect, snippet_status_comparison(twin=True), prefix="status-twin"
    )


def test_tag_compared_to_variable_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_TAG_CMP, prefix="tag-var-live")
    silent_all(ws, effect, snippet_tag_vs_variable(), prefix="tag-var-public")
    silent_all(
        ws, effect, snippet_tag_vs_variable(twin=True), prefix="tag-var-twin"
    )


def test_tag_compared_to_non_string_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_TAG_CMP, prefix="tag-nonstring-live")
    silent_all(ws, effect, snippet_tag_vs_non_string(), prefix="tag-nonstring")


def test_tag_compared_to_template_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_TAG_CMP, prefix="tag-template-live")
    silent_all(ws, effect, snippet_tag_vs_template(), prefix="tag-template")


def test_effect_catch_handler_is_silent_for_tag_comparison(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_TAG_CMP, prefix="catch-owned-tag-live")
    source = snippet_effect_catch_error_comparison()
    path, only_cmp = lint_f07_source(
        ws, effect, source, prefix="catch-owned-cmp", rules=[RULE_TAG_CMP]
    )
    assert_silent_f07(only_cmp)
    all_five = lint_f07(ws, [path], effect)
    assert_effect_classified_not_fired(all_five, RULE_TAG_CMP)
    assert_effect_fired(all_five, RULE_ERR_TAG)
    assert_only_effect_rule(all_five, RULE_ERR_TAG)


def test_effect_catchall_handler_is_silent_for_tag_comparison(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_TAG_CMP, prefix="catchall-owned-tag-live")
    source = snippet_effect_catchall_error_comparison()
    path, only_cmp = lint_f07_source(
        ws, effect, source, prefix="catchall-owned-cmp", rules=[RULE_TAG_CMP]
    )
    assert_silent_f07(only_cmp)
    all_five = lint_f07(ws, [path], effect)
    assert_effect_classified_not_fired(all_five, RULE_TAG_CMP)
    assert_effect_fired(all_five, RULE_ERR_TAG)
    assert_only_effect_rule(all_five, RULE_ERR_TAG)


def test_renamed_effect_binding_is_not_a_catch_handler_for_tag_comparison(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    fire_spelled_catch_handler(
        ws,
        effect,
        snippet_effect_catch_error_comparison(),
        prefix="renamed-catch-spelled",
    )
    fire_unique(
        ws,
        effect,
        snippet_renamed_effect_catch(),
        RULE_TAG_CMP,
        prefix="renamed-catch-public",
    )
    path, result = fire_unique(
        ws,
        effect,
        snippet_renamed_effect_catch(twin=True),
        RULE_TAG_CMP,
        prefix="renamed-catch-twin",
    )
    print(f"renamed-catch twin={path}", flush=True)
    assert_effect_classified_not_fired(result, RULE_ERR_TAG)


def test_renamed_effect_catchall_is_not_a_catch_handler_for_tag_comparison(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    fire_spelled_catch_handler(
        ws,
        effect,
        snippet_effect_catchall_reason_comparison(),
        prefix="renamed-catchall-spelled",
    )
    fire_unique(
        ws,
        effect,
        snippet_renamed_effect_catchall_reason(),
        RULE_TAG_CMP,
        prefix="renamed-catchall-public",
    )
    path, result = fire_unique(
        ws,
        effect,
        snippet_renamed_effect_catchall_reason(twin=True),
        RULE_TAG_CMP,
        prefix="renamed-catchall-twin",
    )
    print(f"renamed-catchall twin={path}", flush=True)
    assert_effect_classified_not_fired(result, RULE_ERR_TAG)


def test_aliased_effect_identifier_is_not_treated_as_effect(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_ERR_TAG, prefix="alias-effect-spelled")
    public = (
        'import { Effect as Eff } from "effect";\n'
        'Eff.catch((error) => error._tag === "NotFound" ? recover : fail);\n'
    )
    path, result = fire_unique(
        ws, effect, public, RULE_TAG_CMP, prefix="alias-effect-public"
    )
    print(f"aliased Effect public path={path}", flush=True)
    assert_effect_classified_not_fired(result, RULE_ERR_TAG)
    twin_path, twin_result = fire_unique(
        ws,
        effect,
        snippet_renamed_effect_catch(twin=True),
        RULE_TAG_CMP,
        prefix="alias-effect-twin",
    )
    print(f"aliased Effect twin path={twin_path}", flush=True)
    assert_effect_classified_not_fired(twin_result, RULE_ERR_TAG)


# ---------------------------------------------------------------------------
# D. no-manual-effect-error-tag reports
# ---------------------------------------------------------------------------


def test_effect_catch_error_tag_comparison_reports_error_case(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_effect_catch_error_comparison(),
        snippet_effect_catch_error_comparison(twin=True),
        RULE_ERR_TAG,
        prefix="catch-error",
    )
    print(f"catch-error public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_ERR_TAG)
    assert_only_effect_rule(twin_result, RULE_ERR_TAG)
    twin_path, twin_result = lint_f07_source(
        ws,
        effect,
        snippet_effect_catch_error_comparison(twin=True),
        prefix="catch-error-ownership",
    )
    print(f"catch-error ownership path={twin_path}", flush=True)
    assert_only_effect_rule(twin_result, RULE_ERR_TAG)
    assert_effect_classified_not_fired(twin_result, RULE_TAG_CMP)


def test_effect_catchall_reason_tag_comparison_reports_reason_case(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_effect_catchall_reason_comparison(),
        snippet_effect_catchall_reason_comparison(twin=True),
        RULE_ERR_TAG,
        prefix="catchall-reason",
    )
    print(f"catchall-reason public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_ERR_TAG)
    assert_only_effect_rule(twin_result, RULE_ERR_TAG)


def test_effect_catchall_error_tag_comparison_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_effect_catchall_error_comparison(),
        snippet_effect_catchall_error_comparison(twin=True),
        RULE_ERR_TAG,
        prefix="catchall-error",
    )
    print(f"catchall-error public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_ERR_TAG)
    assert_only_effect_rule(twin_result, RULE_ERR_TAG)


def test_effect_catch_function_expression_error_tag_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_effect_catch_function_error(),
        RULE_ERR_TAG,
        prefix="catch-fn-public",
    )


def test_effect_catch_error_tag_comparison_not_ternary_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_catch_error_comparison_expression(),
        snippet_catch_error_comparison_expression(twin=True),
        RULE_ERR_TAG,
        prefix="catch-cmp-expr",
    )
    print(f"catch-cmp-expr public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_ERR_TAG)
    assert_only_effect_rule(twin_result, RULE_ERR_TAG)
    assert_effect_classified_not_fired(public_result, RULE_TAG_CMP)
    assert_effect_classified_not_fired(twin_result, RULE_TAG_CMP)


def test_effect_catchif_error_tag_switch_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_effect_catchif_error_switch(),
        snippet_effect_catchif_error_switch(twin=True),
        RULE_ERR_TAG,
        prefix="catchif-switch",
    )
    print(f"catchif-switch public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_ERR_TAG)
    assert_only_effect_rule(twin_result, RULE_ERR_TAG)


def test_effect_catch_reason_tag_switch_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_effect_catch_reason_switch(),
        snippet_effect_catch_reason_switch(twin=True),
        RULE_ERR_TAG,
        prefix="catch-reason-switch",
    )
    print(f"catch-reason-switch public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_ERR_TAG)
    assert_only_effect_rule(twin_result, RULE_ERR_TAG)


def test_tagged_error_and_reason_findings_identify_their_constructs(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    error = snippet_catch_tagged_error_construct()
    reason = snippet_catch_tagged_reason_construct()
    _error_path, error_result = lint_f07_source(
        ws, effect, error.source, prefix="span-error"
    )
    _reason_path, reason_result = lint_f07_source(
        ws, effect, reason.source, prefix="span-reason"
    )
    error_off = assert_effect_identifies_span(
        error.source,
        error_result,
        RULE_ERR_TAG,
        error.construct_span,
        error.call_span,
    )
    reason_off = assert_effect_identifies_span(
        reason.source,
        reason_result,
        RULE_ERR_TAG,
        reason.construct_span,
        reason.call_span,
    )
    assert_only_effect_rule(error_result, RULE_ERR_TAG)
    assert_only_effect_rule(reason_result, RULE_ERR_TAG)
    print(
        f"tag-vs-reason error_off={error_off} reason_off={reason_off}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# E. no-manual-effect-error-tag allowed counterparts
# ---------------------------------------------------------------------------


def test_top_level_error_tag_is_silent_for_effect_error_tag(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_spelled_catch_handler(
        ws,
        effect,
        snippet_effect_catch_error_comparison(),
        prefix="top-error-tag-spelled",
    )
    path, result = lint_f07_source(
        ws, effect, snippet_top_level_error_tag(), prefix="top-error-tag"
    )
    print(f"top-level error tag path={path}", flush=True)
    assert_effect_classified_not_fired(result, RULE_ERR_TAG)
    assert_effect_fired(result, RULE_TAG_CMP)
    assert_only_effect_rule(result, RULE_TAG_CMP)


def test_effect_catch_tag_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_ERR_TAG, prefix="catch-tag-live")
    silent_all(ws, effect, snippet_effect_catch_tag(), prefix="catch-tag")
    silent_all(
        ws, effect, snippet_effect_catch_tag(twin=True), prefix="catch-tag-twin"
    )


def test_catch_tag_handler_nested_reason_tag_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_error_tag_only(
        ws,
        effect,
        snippet_effect_catchall_reason_comparison(),
        prefix="catch-tag-reason-spelled",
    )
    for source, label in (
        (snippet_catch_tag_nested_reason(), "public"),
        (snippet_catch_tag_nested_reason(twin=True), "twin"),
    ):
        path, result = lint_f07_source(
            ws, effect, source, prefix=f"catch-tag-reason-{label}"
        )
        print(f"catch-tag nested reason {label} path={path}", flush=True)
        assert_effect_classified_not_fired(result, RULE_ERR_TAG)
        assert_effect_fired(result, RULE_TAG_CMP)
        assert_only_effect_rule(result, RULE_TAG_CMP)


def test_variable_tag_inside_catch_is_silent_for_effect_error_tag(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_ERR_TAG, prefix="var-in-catch-live")
    silent_all(
        ws, effect, snippet_variable_tag_in_catch(), prefix="var-in-catch"
    )
    silent_all(
        ws,
        effect,
        snippet_variable_tag_in_catch(twin=True),
        prefix="var-in-catch-twin",
    )


def test_renamed_effect_binding_is_silent_for_effect_error_tag(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_spelled_catch_handler(
        ws,
        effect,
        snippet_effect_catch_error_comparison(),
        prefix="renamed-err-spelled",
    )
    path, result = lint_f07_source(
        ws, effect, snippet_renamed_effect_catch(twin=True), prefix="renamed-err"
    )
    print(f"renamed silent-for-error-tag path={path}", flush=True)
    assert_effect_classified_not_fired(result, RULE_ERR_TAG)
    assert_effect_fired(result, RULE_TAG_CMP)


# ---------------------------------------------------------------------------
# F. no-manual-tagged-construction
# ---------------------------------------------------------------------------


def test_object_literal_string_tag_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_manual_tagged_object(),
        snippet_manual_tagged_object(twin=True),
        RULE_CONSTRUCT,
        prefix="obj-ident",
    )
    print(f"obj-ident public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_CONSTRUCT)
    assert_only_effect_rule(twin_result, RULE_CONSTRUCT)


def test_computed_string_tag_property_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_manual_tagged_object(style="computed"),
        snippet_manual_tagged_object(twin=True, style="computed"),
        RULE_CONSTRUCT,
        prefix="obj-computed",
    )
    print(f"obj-computed public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_CONSTRUCT)
    assert_only_effect_rule(twin_result, RULE_CONSTRUCT)


def test_quoted_tag_property_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_manual_tagged_object(style="quoted"),
        snippet_manual_tagged_object(twin=True, style="quoted"),
        RULE_CONSTRUCT,
        prefix="obj-quoted",
    )
    print(f"obj-quoted public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_CONSTRUCT)
    assert_only_effect_rule(twin_result, RULE_CONSTRUCT)


def test_non_match_tagged_object_alongside_match_when_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    public = snippet_match_when_plus_non_match_tagged()
    twin = snippet_match_when_plus_non_match_tagged(twin=True)
    path, result = fire_unique(
        ws,
        effect,
        public.source,
        RULE_CONSTRUCT,
        prefix="match-plus-other-public",
    )
    print(f"match-plus-other public={path}", flush=True)
    assert_effect_identifies_span(
        public.source,
        result,
        RULE_CONSTRUCT,
        public.hit_span,
        public.miss_span,
    )
    twin_path, twin_result = fire_unique(
        ws,
        effect,
        twin.source,
        RULE_CONSTRUCT,
        prefix="match-plus-other-twin",
    )
    print(f"match-plus-other twin={twin_path}", flush=True)
    assert_effect_identifies_span(
        twin.source,
        twin_result,
        RULE_CONSTRUCT,
        twin.hit_span,
        twin.miss_span,
    )


def test_match_when_pattern_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_CONSTRUCT, prefix="match-when-live")
    silent_all(ws, effect, snippet_match_when(), prefix="match-when")
    silent_all(
        ws, effect, snippet_match_when(twin=True), prefix="match-when-twin"
    )


def test_match_not_pattern_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_CONSTRUCT, prefix="match-not-live")
    silent_all(ws, effect, snippet_match_not(), prefix="match-not")
    silent_all(
        ws, effect, snippet_match_not(twin=True), prefix="match-not-twin"
    )


def test_ready_make_constructor_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_CONSTRUCT, prefix="ready-make-live")
    silent_all(ws, effect, snippet_ready_make(), prefix="ready-make")
    silent_all(
        ws, effect, snippet_ready_make(twin=True), prefix="ready-make-twin"
    )


def test_new_not_found_constructor_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_CONSTRUCT, prefix="new-notfound-live")
    silent_all(ws, effect, snippet_new_not_found(), prefix="new-notfound")
    silent_all(
        ws, effect, snippet_new_not_found(twin=True), prefix="new-notfound-twin"
    )


def test_variable_tag_object_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_CONSTRUCT, prefix="var-tag-obj-live")
    silent_all(ws, effect, snippet_variable_tag_object(), prefix="var-tag-obj")
    silent_all(
        ws,
        effect,
        snippet_variable_tag_object(twin=True),
        prefix="var-tag-obj-twin",
    )


def test_aliased_match_when_is_not_a_match_pattern(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_aliased_match_when(),
        RULE_CONSTRUCT,
        prefix="alias-when-public",
    )
    fire_unique(
        ws,
        effect,
        snippet_aliased_match_when(twin=True),
        RULE_CONSTRUCT,
        prefix="alias-when-twin",
    )


def test_aliased_match_not_is_not_a_match_pattern(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_aliased_match_not(),
        RULE_CONSTRUCT,
        prefix="alias-not-public",
    )
    fire_unique(
        ws,
        effect,
        snippet_aliased_match_not(twin=True),
        RULE_CONSTRUCT,
        prefix="alias-not-twin",
    )


# ---------------------------------------------------------------------------
# G. prefer-effect-match
# ---------------------------------------------------------------------------


def test_false_branch_chained_same_value_literal_ternary_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_chained_same_value(),
        snippet_chained_same_value(twin=True),
        RULE_MATCH,
        prefix="chain-same",
    )
    print(f"chain-same public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_MATCH)
    assert_only_effect_rule(twin_result, RULE_MATCH)


def test_template_literal_operand_order_chained_ternary_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_template_mixed_chain(),
        snippet_template_mixed_chain(twin=True),
        RULE_MATCH,
        prefix="chain-tpl-mixed",
    )
    print(f"chain-tpl-mixed public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_MATCH)
    assert_only_effect_rule(twin_result, RULE_MATCH)


def test_template_literal_same_operand_order_chained_ternary_reports(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_template_same_order_chain(),
        snippet_template_same_order_chain(twin=True),
        RULE_MATCH,
        prefix="chain-tpl-same",
    )
    print(f"chain-tpl-same public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_MATCH)
    assert_only_effect_rule(twin_result, RULE_MATCH)


def test_reversed_string_literal_chained_ternary_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_reversed_string_chain(),
        snippet_reversed_string_chain(twin=True),
        RULE_MATCH,
        prefix="chain-rev-str",
    )
    print(f"chain-rev-str public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_MATCH)
    assert_only_effect_rule(twin_result, RULE_MATCH)


def test_loose_equality_numeric_chained_ternary_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_loose_numeric_chain(),
        RULE_MATCH,
        prefix="chain-numeric",
    )


def test_loose_inequality_chained_ternary_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_loose_inequality_chain(),
        snippet_loose_inequality_chain(twin=True),
        RULE_MATCH,
        prefix="chain-neq",
    )
    print(f"chain-neq public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_MATCH)
    assert_only_effect_rule(twin_result, RULE_MATCH)


def test_same_member_expression_chained_ternary_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_member_chain(),
        snippet_member_chain(twin=True),
        RULE_MATCH,
        prefix="chain-member",
    )
    print(f"chain-member public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_MATCH)
    assert_only_effect_rule(twin_result, RULE_MATCH)


def test_false_branch_chain_with_nested_true_branch_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    (public_path, public_result), (twin_path, twin_result) = fire_public_and_twin(
        ws,
        effect,
        snippet_false_chain_nested_true(),
        snippet_false_chain_nested_true(twin=True),
        RULE_MATCH,
        prefix="chain-true-nest",
    )
    print(f"chain-true-nest public={public_path} twin={twin_path}", flush=True)
    assert_only_effect_rule(public_result, RULE_MATCH)
    assert_only_effect_rule(twin_result, RULE_MATCH)


def test_single_ternary_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_MATCH, prefix="single-tern-live")
    silent_all(ws, effect, snippet_single_ternary(), prefix="single-tern")
    silent_all(
        ws, effect, snippet_single_ternary(twin=True), prefix="single-tern-twin"
    )


def test_nested_ternary_over_different_names_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_MATCH, prefix="diff-names-live")
    silent_all(
        ws, effect, snippet_different_names_ternary(), prefix="diff-names"
    )
    silent_all(
        ws,
        effect,
        snippet_different_names_ternary(twin=True),
        prefix="diff-names-twin",
    )


def test_true_branch_nested_ternary_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_MATCH, prefix="true-nest-live")
    silent_all(ws, effect, snippet_true_branch_nest(), prefix="true-nest")
    silent_all(
        ws, effect, snippet_true_branch_nest(twin=True), prefix="true-nest-twin"
    )


def test_non_literal_nested_ternary_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_MATCH, prefix="nonlit-live")
    silent_all(ws, effect, snippet_non_literal_nested(), prefix="nonlit")
    silent_all(
        ws, effect, snippet_non_literal_nested(twin=True), prefix="nonlit-twin"
    )


# ---------------------------------------------------------------------------
# H. no-service-constructor-imports
# ---------------------------------------------------------------------------


def test_relative_make_uppercase_import_in_application_file_reports(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_public_runtime_import(),
        RULE_SVC,
        prefix="svc-public",
        rel="src/runtime.ts",
    )
    fire_unique(
        ws,
        effect,
        snippet_make_uppercase_import(twin=True),
        RULE_SVC,
        prefix="svc-twin",
        rel=application_rel(),
    )


def test_parent_relative_make_uppercase_import_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    spec = f"../{generated_make_uppercase()[4:].lower()}.ts"
    fire_unique(
        ws,
        effect,
        snippet_make_uppercase_import(twin=True, specifier=spec),
        RULE_SVC,
        prefix="svc-parent",
        rel=application_rel(nested=True),
    )


def test_aliased_imported_make_uppercase_name_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_make_uppercase_import(local="createIssueService"),
        RULE_SVC,
        prefix="svc-alias-public",
        rel=application_rel(),
    )
    imported = generated_make_uppercase()
    local = "create" + imported[4:]
    fire_unique(
        ws,
        effect,
        snippet_make_uppercase_import(
            twin=True, imported=imported, local=local
        ),
        RULE_SVC,
        prefix="svc-alias-twin",
        rel=application_rel(),
    )


def test_application_tsx_make_uppercase_import_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_make_uppercase_import(twin=True),
        RULE_SVC,
        prefix="svc-tsx",
        ext="tsx",
        rel=application_rel(ext="tsx"),
    )


def test_application_cts_make_uppercase_import_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_make_uppercase_import(twin=True),
        RULE_SVC,
        prefix="svc-cts",
        ext="cts",
        rel=application_rel(ext="cts"),
    )


def test_same_import_in_test_file_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_SVC, prefix="svc-test-live")
    silent_all(
        ws,
        effect,
        snippet_public_runtime_import(),
        prefix="svc-test-public",
        rel="src/issue-service.test.ts",
    )
    silent_all(
        ws,
        effect,
        snippet_make_uppercase_import(twin=True),
        prefix="svc-test-twin",
        rel=suffix_file_rel(),
    )


def test_spec_tsx_file_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    source = snippet_make_uppercase_import(twin=True)
    fire_application_make_import(
        ws, effect, source, prefix="svc-spec-tsx-live", ext="tsx"
    )
    silent_all(
        ws,
        effect,
        source,
        prefix="svc-spec-tsx",
        ext="tsx",
        rel=suffix_file_rel(kind="spec", ext="tsx"),
    )


def test_spec_ts_file_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_SVC, prefix="svc-spec-ts-live")
    silent_all(
        ws,
        effect,
        snippet_make_uppercase_import(twin=True),
        prefix="svc-spec-ts",
        rel=suffix_file_rel(kind="spec", ext="ts"),
    )


def test_test_mjs_module_variant_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    source = snippet_make_uppercase_import(twin=True)
    fire_application_make_import(
        ws, effect, source, prefix="svc-test-mjs-live", ext="mjs"
    )
    silent_all(
        ws,
        effect,
        source,
        prefix="svc-test-mjs",
        ext="mjs",
        rel=suffix_file_rel(kind="test", ext="mjs"),
    )


def test_test_cts_module_variant_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    source = snippet_make_uppercase_import(twin=True)
    fire_application_make_import(
        ws, effect, source, prefix="svc-test-cts-live", ext="cts"
    )
    silent_all(
        ws,
        effect,
        source,
        prefix="svc-test-cts",
        ext="cts",
        rel=suffix_file_rel(kind="test", ext="cts"),
    )


def test_package_specifier_make_import_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_SVC, prefix="svc-pkg-live")
    silent_all(
        ws,
        effect,
        snippet_package_make_import(),
        prefix="svc-pkg-public",
        rel=application_rel(),
    )
    silent_all(
        ws,
        effect,
        snippet_package_make_import(twin=True),
        prefix="svc-pkg-twin",
        rel=application_rel(),
    )


def test_path_alias_make_import_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_SVC, prefix="svc-alias-path-live")
    silent_all(
        ws,
        effect,
        snippet_path_alias_make_import(),
        prefix="svc-alias-path",
        rel=application_rel(),
    )


def test_default_make_import_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_SVC, prefix="svc-default-live")
    silent_all(
        ws,
        effect,
        snippet_default_make_import(),
        prefix="svc-default",
        rel=application_rel(),
    )
    silent_all(
        ws,
        effect,
        snippet_default_make_import(twin=True),
        prefix="svc-default-twin",
        rel=application_rel(),
    )


def test_local_binding_make_uppercase_imported_name_mismatch_is_silent(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_SVC, prefix="svc-reverse-live")
    silent_all(
        ws,
        effect,
        snippet_reverse_named_alias(),
        prefix="svc-reverse",
        rel=application_rel(),
    )
    silent_all(
        ws,
        effect,
        snippet_reverse_named_alias(twin=True),
        prefix="svc-reverse-twin",
        rel=application_rel(),
    )


def test_make_followed_by_lowercase_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_SVC, prefix="svc-lower-live")
    silent_all(
        ws,
        effect,
        snippet_make_lowercase_import(),
        prefix="svc-lower",
        rel=application_rel(),
    )
    silent_all(
        ws,
        effect,
        snippet_make_lowercase_import(twin=True),
        prefix="svc-lower-twin",
        rel=application_rel(),
    )


def test_imported_name_make_alone_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_SVC, prefix="svc-make-alone-live")
    silent_all(
        ws,
        effect,
        snippet_import_make_alone(),
        prefix="svc-make-alone",
        rel=application_rel(),
    )


def test_static_constructor_call_is_silent(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_public_only(ws, effect, RULE_SVC, prefix="svc-static-call-live")
    silent_all(
        ws,
        effect,
        snippet_static_constructor_call(),
        prefix="svc-static-call",
        rel=application_rel(),
    )


def test_application_file_named_test_without_suffix_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_public_runtime_import(),
        RULE_SVC,
        prefix="svc-named-test",
        rel="src/test.ts",
    )


# ---------------------------------------------------------------------------
# I. No autofix
# ---------------------------------------------------------------------------


def test_fix_mode_does_not_rewrite_tag_comparison(copied_plugin):
    ws, _generic, effect = copied_plugin
    run_effect_fix(
        ws, effect, snippet_manual_tag_comparison(), RULE_TAG_CMP, prefix="fix-tag"
    )


def test_fix_mode_does_not_rewrite_effect_error_tag(copied_plugin):
    ws, _generic, effect = copied_plugin
    run_effect_fix(
        ws,
        effect,
        snippet_effect_catch_error_comparison(),
        RULE_ERR_TAG,
        prefix="fix-err",
    )


def test_fix_mode_does_not_rewrite_tagged_construction(copied_plugin):
    ws, _generic, effect = copied_plugin
    run_effect_fix(
        ws, effect, snippet_manual_tagged_object(), RULE_CONSTRUCT, prefix="fix-obj"
    )


def test_fix_mode_does_not_rewrite_chained_ternary(copied_plugin):
    ws, _generic, effect = copied_plugin
    run_effect_fix(
        ws, effect, snippet_chained_same_value(), RULE_MATCH, prefix="fix-chain"
    )


def test_fix_mode_does_not_rewrite_service_constructor_import(copied_plugin):
    ws, _generic, effect = copied_plugin
    run_effect_fix(
        ws,
        effect,
        snippet_public_runtime_import(),
        RULE_SVC,
        prefix="fix-svc",
        rel="src/runtime.ts",
    )


def test_fix_mode_does_not_rewrite_js_tagged_construction(copied_plugin):
    ws, _generic, effect = copied_plugin
    run_effect_fix(
        ws,
        effect,
        snippet_manual_tagged_object(twin=True),
        RULE_CONSTRUCT,
        prefix="fix-js-obj",
        ext="js",
    )


# ---------------------------------------------------------------------------
# J. Identifies the construct; TypeScript and JavaScript
# ---------------------------------------------------------------------------


def test_tag_comparison_finding_identifies_tag_not_status_when_status_comes_first(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    snippet = snippet_status_then_tag()
    path, result = lint_f07_source(
        ws, effect, snippet.source, prefix="ident-status-first"
    )
    print(f"ident status-first path={path}", flush=True)
    offset = assert_effect_identifies_span(
        snippet.source,
        result,
        RULE_TAG_CMP,
        snippet.hit_span,
        snippet.miss_span,
    )
    assert offset >= snippet.miss_span[1], (
        f"later _tag span must sort after the status span; "
        f"offset={offset} miss_end={snippet.miss_span[1]}"
    )
    assert_only_effect_rule(result, RULE_TAG_CMP)


def test_tag_comparison_finding_identifies_tag_not_status_when_tag_comes_first(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    snippet = snippet_tag_then_status()
    path, result = lint_f07_source(
        ws, effect, snippet.source, prefix="ident-tag-first"
    )
    print(f"ident tag-first path={path}", flush=True)
    offset = assert_effect_identifies_span(
        snippet.source,
        result,
        RULE_TAG_CMP,
        snippet.hit_span,
        snippet.miss_span,
    )
    assert offset < snippet.miss_span[0], (
        f"earlier _tag span must sort before the status span; "
        f"offset={offset} miss_start={snippet.miss_span[0]}"
    )
    assert_only_effect_rule(result, RULE_TAG_CMP)


def test_service_import_finding_identifies_make_uppercase_not_lowercase(
    copied_plugin,
):
    ws, _generic, effect = copied_plugin
    snippet = snippet_neighbor_imports()
    path, result = lint_f07_source(
        ws,
        effect,
        snippet.source,
        prefix="ident-import",
        rel="src/runtime.ts",
    )
    print(f"ident import path={path}", flush=True)
    assert_effect_identifies_span(
        snippet.source,
        result,
        RULE_SVC,
        snippet.hit_span,
        snippet.miss_span,
    )
    assert_only_effect_rule(result, RULE_SVC)


def test_js_tag_comparison_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_tag_member_equality(twin=True),
        RULE_TAG_CMP,
        prefix="js-tag",
        ext="js",
    )


def test_js_effect_catch_error_tag_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_effect_catch_error_comparison(twin=True),
        RULE_ERR_TAG,
        prefix="js-catch",
        ext="js",
    )


def test_js_tagged_construction_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_manual_tagged_object(twin=True),
        RULE_CONSTRUCT,
        prefix="js-obj",
        ext="js",
    )


def test_js_chained_ternary_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_chained_same_value(twin=True),
        RULE_MATCH,
        prefix="js-chain",
        ext="js",
    )


def test_js_application_make_import_reports(copied_plugin):
    ws, _generic, effect = copied_plugin
    fire_unique(
        ws,
        effect,
        snippet_make_uppercase_import(twin=True),
        RULE_SVC,
        prefix="js-svc",
        ext="js",
        rel=application_rel(ext="js"),
    )
