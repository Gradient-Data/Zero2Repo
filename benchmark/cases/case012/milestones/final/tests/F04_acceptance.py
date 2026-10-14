# feature: F04
"""Acceptance tests: reject unknown, object, and unsafe dictionary contracts."""

from __future__ import annotations

import pytest

from _harness import DEFAULT_COPY_DEST, workspace
from F01_helpers import (
    assert_fired,
    assert_only_rule,
    require_copied_layout,
    snippet_no_object_parameters,
    snippet_no_unknown_parameters,
    snippet_no_unknown_returns,
    snippet_no_unknown_type_aliases,
    snippet_no_unsafe_dictionary_type,
    snippet_same_file_unknown_alias,
)
from F02_helpers import assert_fix_preserves_source
from F03_helpers import assert_classified_not_fired
from F04_helpers import (
    RULE_DICT,
    RULE_OBJECT,
    RULE_UNKNOWN_ALIAS,
    RULE_UNKNOWN_PARAM,
    RULE_UNKNOWN_RETURN,
    assert_later_unknown_alias_span,
    assert_predicate_extra_relative_order,
    assert_silent_f04,
    assert_wrapper_of_unsafe_dictionary_reported,
    brand_only_dictionary_cases,
    lint_f04,
    lint_f04_source,
    predicate_extra_names,
    snippet_arrow_predicate_subject,
    snippet_arrow_unknown_return,
    snippet_assertion_function_subject,
    snippet_box_of_object_parameter,
    snippet_box_of_unknown_alias,
    snippet_cause_union_containing_unknown,
    snippet_cause_unknown_parameter,
    snippet_chained_unknown_alias,
    snippet_declared_predicate_subject,
    snippet_declared_unknown_return,
    snippet_defaulted_object_parameter,
    snippet_destructured_object_parameter,
    snippet_forward_object_alias_parameter,
    snippet_function_type_unknown_return,
    snippet_generic_extends_object_parameter,
    snippet_generic_function_explicit_unknown_return,
    snippet_generic_record_constraints,
    snippet_generic_return_of_own_type_parameter,
    snippet_generic_type_parameter,
    snippet_identity_of_object_parameter,
    snippet_identity_of_unknown_as_parameter,
    snippet_identity_of_unknown_as_return,
    snippet_identity_of_unknown_type_alias,
    snippet_index_of_named_command,
    snippet_index_signature_of_any,
    snippet_inferred_return,
    snippet_inner_object_alias_parameter,
    snippet_inner_unknown_alias_as_return,
    snippet_later_inner_object_alias_does_not_leak,
    snippet_map_readonly_map_weak_map,
    snippet_mapped_of_named_command,
    snippet_mapped_string_dictionary_of_unknown,
    snippet_method_predicate_subject,
    snippet_method_unknown_return,
    snippet_named_data_beside_optional_never,
    snippet_named_interface_parameter,
    snippet_named_object_return_with_unknown_field,
    snippet_named_object_type_parameter,
    snippet_nested_object_unknown_field_dictionary,
    snippet_non_cause_union_containing_unknown,
    snippet_non_cause_unknown_parameter,
    snippet_object_alias_on_unrelated_generic,
    snippet_object_function_type,
    snippet_object_method_parameter,
    snippet_omit_of_unsafe_dictionary,
    snippet_partial_of_unsafe_dictionary,
    snippet_pick_of_unsafe_dictionary,
    snippet_predicate_extra_before_subject,
    snippet_predicate_extra_later,
    snippet_predicate_extra_still_later,
    promise_named_type_names,
    snippet_promise_like_of_named_type,
    snippet_promise_like_unknown_return,
    snippet_promise_of_named_type,
    snippet_promise_unknown_function_return,
    snippet_promise_unknown_return,
    snippet_record_of_brand_only_empty,
    snippet_record_of_empty_interface,
    snippet_record_of_empty_object,
    snippet_record_of_named_command,
    snippet_record_of_non_nullable_unknown,
    snippet_record_of_object,
    snippet_record_of_readonly_unknown,
    snippet_record_of_union_unknown,
    snippet_record_of_unknown_alias,
    snippet_readonly_partial_required_of_record,
    snippet_required_of_unsafe_dictionary,
    snippet_same_file_object_alias_parameter,
    snippet_shadowed_non_language_record,
    snippet_string_alias,
    snippet_string_or_number_parameter,
    snippet_type_parameter_shadowing_object_alias,
    snippet_type_predicate_subject,
    snippet_undefined_return_type_name,
    snippet_union_containing_object_parameter,
    snippet_union_containing_unknown_parameter,
    snippet_union_containing_unknown_return,
    snippet_union_unknown_type_alias,
    snippet_unknown_alias_as_parameter,
    snippet_unused_object_alias,
    snippet_written_unknown_method_parameter,
    write_f04_source,
    write_imported_object_alias,
    write_imported_record,
)


@pytest.fixture(scope="module")
def copied_plugin():
    with workspace() as ws:
        result = ws.copy()
        specifier = require_copied_layout(result, DEFAULT_COPY_DEST, cwd=ws.path)
        print(f"F04 copied specifier={specifier}", flush=True)
        yield ws, specifier


def _lint(copied_plugin, source, *, prefix="f04", fix=False):
    ws, specifier = copied_plugin
    return lint_f04_source(ws, specifier, source, prefix=prefix, fix=fix)


def _lint_public_and_twin(copied_plugin, builder, *, prefix, rule_name):
    public = builder()
    twin = builder(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path, result = _lint(copied_plugin, source, prefix=f"{prefix}-{label}")
        print(f"{prefix} {label} path={path.name}", flush=True)
        assert_only_rule(result, rule_name)


# ---------------------------------------------------------------------------
# A. Object parameters report
# ---------------------------------------------------------------------------


def test_object_function_parameter_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_no_object_parameters,
        prefix="obj-fn",
        rule_name=RULE_OBJECT,
    )


def test_object_function_type_parameter_reports(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_object_parameters(twin=True), prefix="obj-fn-live"
    )
    assert_only_rule(baseline, RULE_OBJECT)
    _lint_public_and_twin(
        copied_plugin,
        snippet_object_function_type,
        prefix="obj-fn-type",
        rule_name=RULE_OBJECT,
    )


def test_object_method_parameter_reports(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_object_parameters(twin=True), prefix="obj-method-live"
    )
    assert_only_rule(baseline, RULE_OBJECT)
    _lint_public_and_twin(
        copied_plugin,
        snippet_object_method_parameter,
        prefix="obj-method",
        rule_name=RULE_OBJECT,
    )


def test_union_containing_object_parameter_reports(copied_plugin):
    _, silent = _lint(
        copied_plugin, snippet_string_or_number_parameter(), prefix="obj-union-silent"
    )
    assert_silent_f04(silent, RULE_OBJECT)
    _, baseline = _lint(
        copied_plugin, snippet_no_object_parameters(twin=True), prefix="obj-union-live"
    )
    assert_only_rule(baseline, RULE_OBJECT)
    _, result = _lint(
        copied_plugin, snippet_union_containing_object_parameter(), prefix="obj-union"
    )
    assert_only_rule(result, RULE_OBJECT)


def test_same_file_object_alias_parameter_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_same_file_object_alias_parameter,
        prefix="obj-alias",
        rule_name=RULE_OBJECT,
    )


def test_object_alias_parameter_on_unrelated_generic_still_reports(copied_plugin):
    _, shadow = _lint(
        copied_plugin,
        snippet_type_parameter_shadowing_object_alias(),
        prefix="obj-shadow-live",
    )
    assert_silent_f04(shadow, RULE_OBJECT)
    _, result = _lint(
        copied_plugin,
        snippet_object_alias_on_unrelated_generic(),
        prefix="obj-unrelated-generic",
    )
    assert_only_rule(result, RULE_OBJECT)
    _, twin = _lint(
        copied_plugin,
        snippet_object_alias_on_unrelated_generic(twin=True),
        prefix="obj-unrelated-generic-twin",
    )
    assert_only_rule(twin, RULE_OBJECT)


def test_identity_of_object_parameter_reports(copied_plugin):
    _, written = _lint(
        copied_plugin, snippet_no_object_parameters(twin=True), prefix="obj-id-live"
    )
    assert_only_rule(written, RULE_OBJECT)
    _lint_public_and_twin(
        copied_plugin,
        snippet_identity_of_object_parameter,
        prefix="obj-identity",
        rule_name=RULE_OBJECT,
    )


def test_defaulted_object_parameter_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_defaulted_object_parameter(), prefix="obj-default"
    )
    assert_only_rule(result, RULE_OBJECT)
    _, twin = _lint(
        copied_plugin,
        snippet_defaulted_object_parameter(twin=True),
        prefix="obj-default-twin",
    )
    assert_only_rule(twin, RULE_OBJECT)


def test_destructured_object_parameter_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_destructured_object_parameter(), prefix="obj-destruct"
    )
    assert_only_rule(result, RULE_OBJECT)
    _, twin = _lint(
        copied_plugin,
        snippet_destructured_object_parameter(twin=True),
        prefix="obj-destruct-twin",
    )
    assert_only_rule(twin, RULE_OBJECT)


# ---------------------------------------------------------------------------
# B. Object-parameter silence
# ---------------------------------------------------------------------------


def test_named_interface_parameter_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_object_parameters(twin=True), prefix="iface-live"
    )
    assert_only_rule(baseline, RULE_OBJECT)
    _, result = _lint(
        copied_plugin, snippet_named_interface_parameter(), prefix="iface"
    )
    assert_silent_f04(result, RULE_OBJECT)


def test_named_object_type_parameter_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_object_parameters(twin=True), prefix="named-obj-live"
    )
    assert_only_rule(baseline, RULE_OBJECT)
    _, result = _lint(
        copied_plugin, snippet_named_object_type_parameter(), prefix="named-obj"
    )
    assert_silent_f04(result, RULE_OBJECT)


def test_generic_type_parameter_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_object_parameters(twin=True), prefix="gen-live"
    )
    assert_only_rule(baseline, RULE_OBJECT)
    _, result = _lint(
        copied_plugin, snippet_generic_type_parameter(), prefix="gen-param"
    )
    assert_silent_f04(result, RULE_OBJECT)


def test_generic_extends_object_parameter_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_object_parameters(twin=True), prefix="extends-live"
    )
    assert_only_rule(baseline, RULE_OBJECT)
    _, result = _lint(
        copied_plugin,
        snippet_generic_extends_object_parameter(),
        prefix="extends-object",
    )
    assert_silent_f04(result, RULE_OBJECT)


def test_type_parameter_shadowing_object_alias_is_silent(copied_plugin):
    _, as_param = _lint(
        copied_plugin,
        snippet_same_file_object_alias_parameter(),
        prefix="shadow-alias-live",
    )
    assert_only_rule(as_param, RULE_OBJECT)
    _, unrelated = _lint(
        copied_plugin,
        snippet_object_alias_on_unrelated_generic(),
        prefix="shadow-unrelated-live",
    )
    assert_only_rule(unrelated, RULE_OBJECT)
    _, result = _lint(
        copied_plugin,
        snippet_type_parameter_shadowing_object_alias(),
        prefix="shadow",
    )
    assert_silent_f04(result, RULE_OBJECT)


def test_unused_object_alias_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin,
        snippet_same_file_object_alias_parameter(),
        prefix="unused-obj-live",
    )
    assert_only_rule(baseline, RULE_OBJECT)
    _, result = _lint(
        copied_plugin, snippet_unused_object_alias(), prefix="unused-obj"
    )
    assert_silent_f04(result, RULE_OBJECT)


def test_non_transparent_box_of_object_parameter_is_silent(copied_plugin):
    _, identity = _lint(
        copied_plugin,
        snippet_identity_of_object_parameter(),
        prefix="box-obj-live",
    )
    assert_only_rule(identity, RULE_OBJECT)
    _, result = _lint(
        copied_plugin, snippet_box_of_object_parameter(), prefix="box-obj"
    )
    assert_silent_f04(result, RULE_OBJECT)


# ---------------------------------------------------------------------------
# C. Unknown parameters report
# ---------------------------------------------------------------------------


def test_written_unknown_parameter_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_no_unknown_parameters,
        prefix="unk-param",
        rule_name=RULE_UNKNOWN_PARAM,
    )


def test_union_containing_unknown_parameter_reports(copied_plugin):
    _, number = _lint(
        copied_plugin, snippet_string_or_number_parameter(), prefix="unk-union-silent"
    )
    assert_silent_f04(number, RULE_UNKNOWN_PARAM)
    _, result = _lint(
        copied_plugin,
        snippet_union_containing_unknown_parameter(),
        prefix="unk-union",
    )
    assert_only_rule(result, RULE_UNKNOWN_PARAM)


def _predicate_extra_arms(copied_plugin, *, prefix):
    names = predicate_extra_names(twin=True)
    later = snippet_predicate_extra_later(names=names)
    still = snippet_predicate_extra_still_later(names=names)
    before = snippet_predicate_extra_before_subject(names=names)
    ws, specifier = copied_plugin
    _, later_result = lint_f04_source(
        ws, specifier, later.source, prefix=f"{prefix}-later"
    )
    _, still_result = lint_f04_source(
        ws, specifier, still.source, prefix=f"{prefix}-still"
    )
    _, before_result = lint_f04_source(
        ws, specifier, before.source, prefix=f"{prefix}-before"
    )
    return (later, later_result), (still, still_result), (before, before_result)


def test_additional_unknown_on_type_predicate_reports_only_the_extra(copied_plugin):
    _, subject_only = _lint(
        copied_plugin, snippet_type_predicate_subject(), prefix="pred-subject-live"
    )
    assert_silent_f04(subject_only, RULE_UNKNOWN_PARAM)
    later, still, before = _predicate_extra_arms(copied_plugin, prefix="pred-extra")
    assert_predicate_extra_relative_order(later, still, before)


def test_predicate_subject_not_slot_zero_extra_still_reports(copied_plugin):
    later, still, before = _predicate_extra_arms(copied_plugin, prefix="slot")
    assert_predicate_extra_relative_order(later, still, before)


def test_written_unknown_method_or_arrow_parameter_reports(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unknown_parameters(twin=True), prefix="unk-method-live"
    )
    assert_only_rule(baseline, RULE_UNKNOWN_PARAM)
    _, result = _lint(
        copied_plugin,
        snippet_written_unknown_method_parameter(),
        prefix="unk-method",
    )
    assert_only_rule(result, RULE_UNKNOWN_PARAM)


# ---------------------------------------------------------------------------
# D. Unknown-parameter exceptions and written-vs-resolved
# ---------------------------------------------------------------------------


def test_cause_unknown_parameter_is_silent(copied_plugin):
    _, named = _lint(
        copied_plugin, snippet_non_cause_unknown_parameter(), prefix="cause-named-live"
    )
    assert_only_rule(named, RULE_UNKNOWN_PARAM)
    _, result = _lint(
        copied_plugin, snippet_cause_unknown_parameter(), prefix="cause"
    )
    assert_silent_f04(result, RULE_UNKNOWN_PARAM)


def test_cause_union_containing_unknown_is_silent(copied_plugin):
    _, payload = _lint(
        copied_plugin,
        snippet_non_cause_union_containing_unknown(),
        prefix="cause-union-live",
    )
    assert_only_rule(payload, RULE_UNKNOWN_PARAM)
    _, result = _lint(
        copied_plugin, snippet_cause_union_containing_unknown(), prefix="cause-union"
    )
    assert_silent_f04(result, RULE_UNKNOWN_PARAM)


def test_type_predicate_subject_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unknown_parameters(twin=True), prefix="pred-live"
    )
    assert_only_rule(baseline, RULE_UNKNOWN_PARAM)
    _, result = _lint(
        copied_plugin, snippet_type_predicate_subject(), prefix="pred-subject"
    )
    assert_silent_f04(result, RULE_UNKNOWN_PARAM)


def test_assertion_function_subject_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unknown_parameters(twin=True), prefix="assert-live"
    )
    assert_only_rule(baseline, RULE_UNKNOWN_PARAM)
    _, result = _lint(
        copied_plugin, snippet_assertion_function_subject(), prefix="assert-fn"
    )
    assert_silent_f04(result, RULE_UNKNOWN_PARAM)


def test_arrow_declared_and_method_predicate_subjects_are_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unknown_parameters(twin=True), prefix="pred-forms-live"
    )
    assert_only_rule(baseline, RULE_UNKNOWN_PARAM)
    for source, label in (
        (snippet_arrow_predicate_subject(), "arrow"),
        (snippet_declared_predicate_subject(), "declared"),
        (snippet_method_predicate_subject(), "method"),
    ):
        _, result = _lint(copied_plugin, source, prefix=f"pred-{label}")
        print(f"predicate-owner {label}", flush=True)
        assert_silent_f04(result, RULE_UNKNOWN_PARAM)


def test_string_or_number_parameter_is_silent(copied_plugin):
    _, unknown_union = _lint(
        copied_plugin,
        snippet_union_containing_unknown_parameter(),
        prefix="str-num-live",
    )
    assert_only_rule(unknown_union, RULE_UNKNOWN_PARAM)
    _, result = _lint(
        copied_plugin, snippet_string_or_number_parameter(), prefix="str-num"
    )
    assert_silent_f04(result, RULE_UNKNOWN_PARAM)


def test_same_file_unknown_alias_as_parameter_does_not_report_unknown_parameters(
    copied_plugin,
):
    _, written = _lint(
        copied_plugin, snippet_no_unknown_parameters(twin=True), prefix="alias-param-live"
    )
    assert_only_rule(written, RULE_UNKNOWN_PARAM)
    _, result = _lint(
        copied_plugin, snippet_unknown_alias_as_parameter(), prefix="alias-param"
    )
    assert_classified_not_fired(result, RULE_UNKNOWN_PARAM)
    assert_fired(result, RULE_UNKNOWN_ALIAS)


def test_identity_of_unknown_as_parameter_does_not_report_unknown_parameters(
    copied_plugin,
):
    _, written = _lint(
        copied_plugin, snippet_no_unknown_parameters(twin=True), prefix="id-param-live"
    )
    assert_only_rule(written, RULE_UNKNOWN_PARAM)
    _, result = _lint(
        copied_plugin,
        snippet_identity_of_unknown_as_parameter(),
        prefix="id-param",
    )
    assert_silent_f04(result, RULE_UNKNOWN_PARAM)


# ---------------------------------------------------------------------------
# E. Unknown returns report
# ---------------------------------------------------------------------------


def test_explicit_unknown_return_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_no_unknown_returns,
        prefix="unk-ret",
        rule_name=RULE_UNKNOWN_RETURN,
    )


def test_arrow_declared_method_and_function_type_unknown_returns_report(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unknown_returns(twin=True), prefix="ret-owners-live"
    )
    assert_only_rule(baseline, RULE_UNKNOWN_RETURN)
    for source, label in (
        (snippet_arrow_unknown_return(), "arrow"),
        (snippet_declared_unknown_return(), "declared"),
        (snippet_method_unknown_return(), "method"),
        (snippet_function_type_unknown_return(), "fn-type"),
    ):
        _, result = _lint(copied_plugin, source, prefix=f"ret-{label}")
        print(f"unknown-return-owner {label}", flush=True)
        assert_only_rule(result, RULE_UNKNOWN_RETURN)


def test_generic_function_with_explicit_unknown_return_still_reports(copied_plugin):
    _, own_param = _lint(
        copied_plugin,
        snippet_generic_return_of_own_type_parameter(),
        prefix="gen-ret-own-live",
    )
    assert_classified_not_fired(own_param, RULE_UNKNOWN_RETURN)
    assert_fired(own_param, RULE_UNKNOWN_ALIAS)
    _, result = _lint(
        copied_plugin,
        snippet_generic_function_explicit_unknown_return(),
        prefix="gen-ret-unknown",
    )
    assert_only_rule(result, RULE_UNKNOWN_RETURN)


def test_promise_unknown_return_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_promise_unknown_return(), prefix="promise-unk"
    )
    assert_only_rule(result, RULE_UNKNOWN_RETURN)


def test_promise_like_unknown_return_reports(copied_plugin):
    _, promise = _lint(
        copied_plugin, snippet_promise_unknown_return(), prefix="plike-live"
    )
    assert_only_rule(promise, RULE_UNKNOWN_RETURN)
    _, result = _lint(
        copied_plugin, snippet_promise_like_unknown_return(), prefix="plike-unk"
    )
    assert_only_rule(result, RULE_UNKNOWN_RETURN)


def test_union_containing_unknown_return_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_union_containing_unknown_return(), prefix="ret-union"
    )
    assert_only_rule(result, RULE_UNKNOWN_RETURN)


def test_same_file_unknown_alias_as_return_reports_returns_and_aliases(copied_plugin):
    public = snippet_same_file_unknown_alias()
    twin = snippet_same_file_unknown_alias(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        _, result = _lint(copied_plugin, source, prefix=f"alias-ret-{label}")
        print(f"alias-as-return {label}", flush=True)
        assert_fired(result, RULE_UNKNOWN_RETURN)
        assert_fired(result, RULE_UNKNOWN_ALIAS)


def test_identity_of_unknown_as_return_reports(copied_plugin):
    _, written = _lint(
        copied_plugin, snippet_no_unknown_returns(twin=True), prefix="id-ret-live"
    )
    assert_only_rule(written, RULE_UNKNOWN_RETURN)
    _, result = _lint(
        copied_plugin, snippet_identity_of_unknown_as_return(), prefix="id-ret"
    )
    assert_only_rule(result, RULE_UNKNOWN_RETURN)


def test_inner_unknown_alias_as_return_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_inner_unknown_alias_as_return(), prefix="inner-ret"
    )
    assert_fired(result, RULE_UNKNOWN_RETURN)
    assert_fired(result, RULE_UNKNOWN_ALIAS)


# ---------------------------------------------------------------------------
# F. Unknown-return silence
# ---------------------------------------------------------------------------


def test_inferred_return_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unknown_returns(twin=True), prefix="infer-live"
    )
    assert_only_rule(baseline, RULE_UNKNOWN_RETURN)
    _, result = _lint(copied_plugin, snippet_inferred_return(), prefix="infer")
    assert_silent_f04(result, RULE_UNKNOWN_RETURN)


def test_generic_return_of_own_type_parameter_is_silent_for_returns(copied_plugin):
    _, alias_ret = _lint(
        copied_plugin, snippet_same_file_unknown_alias(), prefix="own-param-alias-live"
    )
    assert_fired(alias_ret, RULE_UNKNOWN_RETURN)
    _, explicit = _lint(
        copied_plugin,
        snippet_generic_function_explicit_unknown_return(),
        prefix="own-param-unk-live",
    )
    assert_only_rule(explicit, RULE_UNKNOWN_RETURN)
    _, result = _lint(
        copied_plugin,
        snippet_generic_return_of_own_type_parameter(),
        prefix="own-param",
    )
    assert_classified_not_fired(result, RULE_UNKNOWN_RETURN)
    assert_fired(result, RULE_UNKNOWN_ALIAS)


def test_named_object_return_with_unknown_field_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unknown_returns(twin=True), prefix="named-ret-live"
    )
    assert_only_rule(baseline, RULE_UNKNOWN_RETURN)
    _, result = _lint(
        copied_plugin,
        snippet_named_object_return_with_unknown_field(),
        prefix="named-ret",
    )
    assert_silent_f04(result, RULE_UNKNOWN_RETURN)


def test_undefined_return_type_name_is_silent(copied_plugin):
    _, alias_ret = _lint(
        copied_plugin, snippet_same_file_unknown_alias(), prefix="undef-ret-live"
    )
    assert_fired(alias_ret, RULE_UNKNOWN_RETURN)
    _, result = _lint(
        copied_plugin, snippet_undefined_return_type_name(), prefix="undef-ret"
    )
    assert_silent_f04(result, RULE_UNKNOWN_RETURN)


def test_promise_of_named_type_is_silent(copied_plugin):
    names = promise_named_type_names(twin=True)
    live = snippet_promise_unknown_function_return(names=names)
    silent = snippet_promise_of_named_type(names=names)
    print(
        f"promise-named-type live-owner=function-declaration "
        f"silent-owner=function-declaration live={live!r} silent={silent!r}",
        flush=True,
    )
    _, unknown_arg = _lint(copied_plugin, live, prefix="puser-live")
    assert_only_rule(unknown_arg, RULE_UNKNOWN_RETURN)
    _, result = _lint(copied_plugin, silent, prefix="puser")
    assert_silent_f04(result, RULE_UNKNOWN_RETURN)


def test_promise_like_of_named_type_is_silent(copied_plugin):
    _, unknown_arg = _lint(
        copied_plugin, snippet_promise_like_unknown_return(), prefix="pluser-live"
    )
    assert_only_rule(unknown_arg, RULE_UNKNOWN_RETURN)
    _, result = _lint(
        copied_plugin, snippet_promise_like_of_named_type(), prefix="pluser"
    )
    assert_silent_f04(result, RULE_UNKNOWN_RETURN)


# ---------------------------------------------------------------------------
# G. Unknown type aliases report
# ---------------------------------------------------------------------------


def test_unknown_type_alias_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_no_unknown_type_aliases,
        prefix="unk-alias",
        rule_name=RULE_UNKNOWN_ALIAS,
    )


def test_union_unknown_type_alias_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_union_unknown_type_alias(), prefix="alias-union"
    )
    assert_only_rule(result, RULE_UNKNOWN_ALIAS)


def test_identity_of_unknown_type_alias_reports(copied_plugin):
    _, written = _lint(
        copied_plugin, snippet_no_unknown_type_aliases(twin=True), prefix="id-alias-live"
    )
    assert_only_rule(written, RULE_UNKNOWN_ALIAS)
    _, result = _lint(
        copied_plugin, snippet_identity_of_unknown_type_alias(), prefix="id-alias"
    )
    assert_only_rule(result, RULE_UNKNOWN_ALIAS)


def test_alias_of_unknown_alias_reports(copied_plugin):
    earlier = snippet_no_unknown_type_aliases()
    later = snippet_chained_unknown_alias(twin=True)
    _, earlier_result = _lint(copied_plugin, earlier, prefix="chain-early")
    ws, specifier = copied_plugin
    _, later_result = lint_f04_source(
        ws, specifier, later.source, prefix="chain-later"
    )
    assert_later_unknown_alias_span(
        earlier, earlier_result, later, later_result
    )


# ---------------------------------------------------------------------------
# H. Unknown-alias silence
# ---------------------------------------------------------------------------


def test_string_alias_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unknown_type_aliases(twin=True), prefix="str-alias-live"
    )
    assert_only_rule(baseline, RULE_UNKNOWN_ALIAS)
    _, result = _lint(copied_plugin, snippet_string_alias(), prefix="str-alias")
    assert_silent_f04(result, RULE_UNKNOWN_ALIAS)


def test_non_transparent_box_of_unknown_is_silent(copied_plugin):
    _, identity = _lint(
        copied_plugin, snippet_identity_of_unknown_type_alias(), prefix="box-unk-live"
    )
    assert_only_rule(identity, RULE_UNKNOWN_ALIAS)
    _, result = _lint(
        copied_plugin, snippet_box_of_unknown_alias(), prefix="box-unk"
    )
    assert_silent_f04(result, RULE_UNKNOWN_ALIAS)


# ---------------------------------------------------------------------------
# I. Unsafe dictionary reports
# ---------------------------------------------------------------------------


def test_record_of_unknown_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_no_unsafe_dictionary_type,
        prefix="rec-unk",
        rule_name=RULE_DICT,
    )


def test_index_signature_of_any_reports(copied_plugin):
    _, record = _lint(
        copied_plugin, snippet_no_unsafe_dictionary_type(twin=True), prefix="idx-live"
    )
    assert_only_rule(record, RULE_DICT)
    _, result = _lint(
        copied_plugin, snippet_index_signature_of_any(), prefix="idx-any"
    )
    assert_only_rule(result, RULE_DICT)


def test_mapped_string_dictionary_of_unknown_reports(copied_plugin):
    _, record = _lint(
        copied_plugin, snippet_no_unsafe_dictionary_type(twin=True), prefix="mapped-live"
    )
    assert_only_rule(record, RULE_DICT)
    _lint_public_and_twin(
        copied_plugin,
        snippet_mapped_string_dictionary_of_unknown,
        prefix="mapped-unk",
        rule_name=RULE_DICT,
    )


def test_record_of_object_and_empty_object_report(copied_plugin):
    _, of_object = _lint(
        copied_plugin, snippet_record_of_object(), prefix="rec-object"
    )
    assert_only_rule(of_object, RULE_DICT)
    _, of_empty = _lint(
        copied_plugin, snippet_record_of_empty_object(), prefix="rec-empty"
    )
    assert_only_rule(of_empty, RULE_DICT)


def test_semantic_equivalent_dictionary_values_report(copied_plugin):
    unique_arms = (
        (snippet_record_of_non_nullable_unknown(), "nonnull"),
        (snippet_record_of_readonly_unknown(), "readonly-unk"),
        (snippet_record_of_empty_interface(), "empty-iface"),
        (snippet_record_of_brand_only_empty(), "brand"),
        (snippet_record_of_union_unknown(), "union-unk"),
    )
    for source, label in unique_arms:
        _, result = _lint(copied_plugin, source, prefix=f"semeq-{label}")
        print(f"semantic-equivalent {label}", flush=True)
        assert_only_rule(result, RULE_DICT)
    _, alias_value = _lint(
        copied_plugin, snippet_record_of_unknown_alias(), prefix="semeq-alias"
    )
    assert_fired(alias_value, RULE_DICT)
    assert_fired(alias_value, RULE_UNKNOWN_ALIAS)



def test_brand_only_empty_dictionary_values_report(copied_plugin):
    for case in brand_only_dictionary_cases():
        _, result = _lint(
            copied_plugin, case.source, prefix=f"brand-{case.label}"
        )
        print(f"brand-only {case.label}", flush=True)
        if case.writing == "record":
            # TEST-FIX(F04): upstream src/shared/dictionary-types.ts:272 shows Record reports its value, and src/shared/dictionary-types.ts:120 shows that value is empty when every member is an optional property of type never, with or without readonly and with no fixed property name.
            assert_only_rule(result, RULE_DICT)
        elif case.writing == "index":
            # TEST-FIX(F04): upstream src/shared/dictionary-types.ts:242 shows an index signature reports an optional-never object type, same-file alias, or same-file interface, with or without readonly.
            assert_only_rule(result, RULE_DICT)
        elif case.writing == "mapped":
            # TEST-FIX(F04): upstream src/shared/dictionary-types.ts:248 shows a mapped dictionary reports an optional-never object type, same-file alias, or same-file interface, with or without readonly.
            assert_only_rule(result, RULE_DICT)
        elif case.writing in {"readonly", "partial", "required"}:
            # TEST-FIX(F04): upstream src/shared/dictionary-types.ts:265 shows Readonly, Partial, and Required of a dictionary report an optional-never value, including a same-file alias of it.
            assert_wrapper_of_unsafe_dictionary_reported(result, case.wrapper)
        else:
            # TEST-FIX(F04): upstream src/shared/dictionary-types.ts:278 shows Pick and Omit of a dictionary report an optional-never value, including a same-file alias of it.
            assert_wrapper_of_unsafe_dictionary_reported(result, case.wrapper)


def test_readonly_partial_required_of_unsafe_dictionary_report(copied_plugin):
    nested = snippet_readonly_partial_required_of_record()
    _, nested_result = _lint(
        copied_plugin, nested.source, prefix="wrap-rpr"
    )
    print("wrapper nested Readonly<Partial<Required<Record>>>", flush=True)
    assert_wrapper_of_unsafe_dictionary_reported(nested_result, nested)

    partial = snippet_partial_of_unsafe_dictionary()
    _, partial_result = _lint(
        copied_plugin, partial.source, prefix="wrap-partial"
    )
    print("wrapper Partial of Record", flush=True)
    assert_wrapper_of_unsafe_dictionary_reported(partial_result, partial)

    required = snippet_required_of_unsafe_dictionary()
    _, required_result = _lint(
        copied_plugin, required.source, prefix="wrap-required"
    )
    print("wrapper Required of Record", flush=True)
    assert_wrapper_of_unsafe_dictionary_reported(required_result, required)


def test_pick_and_omit_of_unsafe_dictionary_report(copied_plugin):
    picked = snippet_pick_of_unsafe_dictionary()
    _, picked_result = _lint(
        copied_plugin, picked.source, prefix="wrap-pick"
    )
    print("wrapper Pick of Source Record", flush=True)
    assert_wrapper_of_unsafe_dictionary_reported(picked_result, picked)

    omitted = snippet_omit_of_unsafe_dictionary()
    _, omitted_result = _lint(
        copied_plugin, omitted.source, prefix="wrap-omit"
    )
    print("wrapper Omit of Source Record", flush=True)
    assert_wrapper_of_unsafe_dictionary_reported(omitted_result, omitted)


# ---------------------------------------------------------------------------
# J. Dictionary silence
# ---------------------------------------------------------------------------


def test_optional_never_with_data_member_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin,
        snippet_record_of_brand_only_empty(),
        prefix="data-brand-live",
    )
    assert_only_rule(baseline, RULE_DICT)
    silent_arms = (
        ("alias", "record"),
        ("interface", "record"),
        ("alias", "index"),
        ("alias", "mapped"),
        ("alias", "readonly"),
    )
    for form, writing in silent_arms:
        source = snippet_named_data_beside_optional_never(
            form=form, writing=writing
        )
        _, result = _lint(
            copied_plugin, source, prefix=f"data-{form}-{writing}"
        )
        print(f"data-member {form} {writing}", flush=True)
        if form == "interface":
            # TEST-FIX(F04): upstream src/shared/dictionary-types.ts:140 shows an interface with a member that is not an optional property of type never is not an empty value, so this dictionary is not reported.
            assert_silent_f04(result, RULE_DICT)
        else:
            # TEST-FIX(F04): upstream src/shared/dictionary-types.ts:129 shows an object type with a member that is not an optional property of type never is not an empty value, so this dictionary is not reported.
            assert_silent_f04(result, RULE_DICT)


def test_record_of_named_command_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unsafe_dictionary_type(twin=True), prefix="cmd-live"
    )
    assert_only_rule(baseline, RULE_DICT)
    _, result = _lint(
        copied_plugin, snippet_record_of_named_command(), prefix="cmd-rec"
    )
    assert_silent_f04(result, RULE_DICT)


def test_index_and_mapped_of_named_command_are_silent(copied_plugin):
    _, idx_unsafe = _lint(
        copied_plugin, snippet_index_signature_of_any(), prefix="cmd-idx-live"
    )
    assert_only_rule(idx_unsafe, RULE_DICT)
    _, mapped_unsafe = _lint(
        copied_plugin,
        snippet_mapped_string_dictionary_of_unknown(),
        prefix="cmd-mapped-live",
    )
    assert_only_rule(mapped_unsafe, RULE_DICT)
    _, idx = _lint(
        copied_plugin, snippet_index_of_named_command(), prefix="cmd-idx"
    )
    assert_silent_f04(idx, RULE_DICT)
    _, mapped = _lint(
        copied_plugin, snippet_mapped_of_named_command(), prefix="cmd-mapped"
    )
    assert_silent_f04(mapped, RULE_DICT)


def test_nested_object_with_unknown_field_as_dictionary_value_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unsafe_dictionary_type(twin=True), prefix="nest-live"
    )
    assert_only_rule(baseline, RULE_DICT)
    _, result = _lint(
        copied_plugin,
        snippet_nested_object_unknown_field_dictionary(),
        prefix="nest",
    )
    assert_silent_f04(result, RULE_DICT)


def test_map_readonly_map_weak_map_are_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unsafe_dictionary_type(twin=True), prefix="map-live"
    )
    assert_only_rule(baseline, RULE_DICT)
    _, result = _lint(
        copied_plugin, snippet_map_readonly_map_weak_map(), prefix="maps"
    )
    assert_silent_f04(result, RULE_DICT)


def test_generic_record_constraint_on_function_class_and_alias_is_silent(
    copied_plugin,
):
    _, baseline = _lint(
        copied_plugin, snippet_no_unsafe_dictionary_type(twin=True), prefix="constraint-live"
    )
    assert_only_rule(baseline, RULE_DICT)
    _, result = _lint(
        copied_plugin, snippet_generic_record_constraints(), prefix="constraint"
    )
    assert_silent_f04(result, RULE_DICT)


def test_shadowed_non_language_record_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unsafe_dictionary_type(twin=True), prefix="shadow-rec-live"
    )
    assert_only_rule(baseline, RULE_DICT)
    _, result = _lint(
        copied_plugin, snippet_shadowed_non_language_record(), prefix="shadow-rec"
    )
    assert_silent_f04(result, RULE_DICT)


def test_imported_record_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_no_unsafe_dictionary_type(twin=True), prefix="imp-rec-live"
    )
    assert_only_rule(baseline, RULE_DICT)
    ws, specifier = copied_plugin
    path = write_imported_record(ws, twin=True)
    result = lint_f04(ws, [path], specifier)
    print(f"imported-record path={path.name} exit={result.returncode}", flush=True)
    assert_silent_f04(result, RULE_DICT)


# ---------------------------------------------------------------------------
# K. Same-file resolution boundary
# ---------------------------------------------------------------------------


def test_inner_object_alias_parameter_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_inner_object_alias_parameter(), prefix="inner-obj"
    )
    assert_only_rule(result, RULE_OBJECT)


def test_forward_object_alias_parameter_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_forward_object_alias_parameter(), prefix="fwd-obj"
    )
    assert_only_rule(result, RULE_OBJECT)


def test_later_inner_object_alias_does_not_leak(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_inner_object_alias_parameter(), prefix="leak-live"
    )
    assert_only_rule(baseline, RULE_OBJECT)
    _, result = _lint(
        copied_plugin,
        snippet_later_inner_object_alias_does_not_leak(),
        prefix="leak",
    )
    assert_silent_f04(result, RULE_OBJECT)


def test_imported_object_alias_parameter_is_silent(copied_plugin):
    _, baseline = _lint(
        copied_plugin,
        snippet_same_file_object_alias_parameter(),
        prefix="imp-obj-live",
    )
    assert_only_rule(baseline, RULE_OBJECT)
    ws, specifier = copied_plugin
    path = write_imported_object_alias(ws, twin=True)
    result = lint_f04(ws, [path], specifier)
    print(f"imported-object-alias path={path.name} exit={result.returncode}", flush=True)
    assert_silent_f04(result, RULE_OBJECT)


# ---------------------------------------------------------------------------
# L. No rewrite under fix mode
# ---------------------------------------------------------------------------


def test_fix_mode_does_not_rewrite_unique_violators(copied_plugin):
    ws, specifier = copied_plugin
    arms = (
        (snippet_no_object_parameters(twin=True), RULE_OBJECT, "fix-obj"),
        (snippet_no_unknown_parameters(twin=True), RULE_UNKNOWN_PARAM, "fix-unk-p"),
        (snippet_no_unknown_returns(twin=True), RULE_UNKNOWN_RETURN, "fix-unk-r"),
        (snippet_no_unknown_type_aliases(twin=True), RULE_UNKNOWN_ALIAS, "fix-unk-a"),
        (snippet_no_unsafe_dictionary_type(twin=True), RULE_DICT, "fix-dict"),
        (snippet_object_function_type(twin=True), RULE_OBJECT, "fix-fn-type"),
        (
            snippet_mapped_string_dictionary_of_unknown(twin=True),
            RULE_DICT,
            "fix-mapped",
        ),
    )
    for source, rule_name, prefix in arms:
        print(f"fix-arm {prefix} rule={rule_name}", flush=True)
        path = write_f04_source(ws, source, prefix=prefix)
        before = path.read_bytes()
        result = lint_f04(ws, [path], specifier, fix=True)
        print(f"fix-mode {path.name} rule={rule_name}", flush=True)
        assert_fix_preserves_source(path, before, result, rule_name)
        assert_only_rule(result, rule_name)


# ---------------------------------------------------------------------------
# M. Unique attribution
# ---------------------------------------------------------------------------


def test_each_unique_violator_attributes_only_its_rule(copied_plugin):
    arms = (
        (snippet_no_object_parameters(twin=True), RULE_OBJECT),
        (snippet_no_unknown_parameters(twin=True), RULE_UNKNOWN_PARAM),
        (snippet_no_unknown_returns(twin=True), RULE_UNKNOWN_RETURN),
        (snippet_no_unknown_type_aliases(twin=True), RULE_UNKNOWN_ALIAS),
        (snippet_no_unsafe_dictionary_type(twin=True), RULE_DICT),
    )
    for source, rule_name in arms:
        _, result = _lint(copied_plugin, source, prefix=f"unique-{rule_name}")
        print(f"unique {rule_name}", flush=True)
        assert_only_rule(result, rule_name)
