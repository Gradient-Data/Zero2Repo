# feature: F03
"""Acceptance tests: keep type evidence; justify remaining assertions."""

from __future__ import annotations

import pytest

from _harness import DEFAULT_COPY_DEST, workspace
from F01_helpers import (
    assert_fired,
    assert_not_fired,
    assert_only_rule,
    require_copied_layout,
    snippet_no_chained_type_assertions,
    snippet_no_known_value_widening,
    snippet_no_widen_then_assert,
    snippet_require_safety_comment_for_type_assertion,
)
from F02_helpers import assert_fix_preserves_source
from F03_helpers import (
    F03_RULE_NAMES,
    RULE_CHAIN,
    RULE_SAFE,
    RULE_THEN,
    RULE_WIDEN,
    alias_store_then_assert_sources,
    assertion_alias_target_sources,
    alternative_marker_sources,
    annotation_only_sources,
    assert_classified_not_fired,
    assert_silent_f03,
    asserted_binding_sources,
    bad_justification_sources,
    block_comment_sources,
    comment_after_sources,
    angle_justification_sources,
    comment_on_earlier_sibling_sources,
    const_exemption_sources,
    const_only_chain_sources,
    binding_keyword_alias_sources,
    literal_keyword_alias_unknown_sources,
    non_predicate_widening_gap_sources,
    empty_assignment_sources,
    empty_dictionary_sources,
    f03_diagnostic_identity,
    explicit_marker_sources,
    export_justification_sources,
    finite_key_sources,
    forward_alias_sources,
    inline_justification_sources,
    invariant_marker_sources,
    later_assertion_sources,
    named_chain_sources,
    let_predicate_sources,
    lint_f03,
    lint_f03_source,
    write_f03_source,
    named_owner_sources,
    crossed_numeric_array_return_and_field_sources,
    known_widening_product_sources,
    object_literal_keyword_return_and_field_sources,
    omitted_marker_sources,
    parenthesized_chain_sources,
    plus_marker_sources,
    predicate_argument_sources,
    provenance_sources,
    named_value_record_then_assert_sources,
    record_any_store_sources,
    rules_omitting,
    safety_above_sources,
    satisfies_sources,
    single_vs_chain_sources,
    snippet_alias_unknown_predicate_parameter,
    snippet_alias_unknown_union_member_predicate,
    snippet_angle_without_comment,
    snippet_as_const_then_non_const,
    snippet_identifier_as_const_then_non_const,
    snippet_block_scoped_object,
    snippet_block_scoped_open_dictionary,
    snippet_block_scoped_unknown,
    const_alias_numeric_array_vehicle_sources,
    snippet_const_alias_to_open_record,
    snippet_const_only_chain,
    snippet_export_without_comment,
    snippet_identity_open_dictionary,
    snippet_known_array_assigned_into_unknown,
    snippet_known_array_into_open_record,
    snippet_known_asserted_into_anonymous_object,
    snippet_known_assigned_into_anonymous_object,
    snippet_known_assigned_into_object,
    snippet_known_assigned_into_unknown,
    snippet_known_assignment_to_open_record,
    snippet_known_assertion_to_open_record,
    snippet_known_class_field_to_anonymous_object,
    snippet_known_class_field_to_object,
    snippet_known_class_field_to_open_record,
    snippet_known_class_field_to_unknown,
    snippet_known_into_anonymous_object,
    snippet_known_into_object,
    snippet_known_into_unknown,
    snippet_known_numeric_assigned_into_object,
    snippet_known_numeric_into_anonymous_object,
    snippet_known_numeric_into_object,
    snippet_known_object_literal_assigned_into_object,
    snippet_known_object_literal_assigned_into_unknown,
    snippet_known_object_literal_into_object,
    snippet_known_object_literal_into_unknown,
    snippet_known_return_to_anonymous_object,
    snippet_known_return_to_object,
    snippet_known_return_to_open_record,
    snippet_known_return_to_unknown,
    snippet_known_to_union_unknown_predicate,
    snippet_known_to_unknown_or_string_predicate,
    snippet_known_to_unknown_predicate,
    snippet_later_assert_still_broad,
    still_broad_record_same_type_sources,
    still_broad_same_type_sources,
    snippet_literal_unknown_store_then_assert,
    snippet_nested_angle_brackets,
    snippet_nested_angle_const_chain,
    snippet_nested_angle_without_comment,
    snippet_nested_as_ending_in_as_const,
    snippet_nested_as_without_comment,
    snippet_nested_named_angle_brackets,
    snippet_parenthesized_chain,
    snippet_precise_annotation_to_predicate,
    snippet_program_scope_open_dictionary,
    alias_non_annotation_vehicle_sources,
    snippet_assert_widened_const_in_nested_function,
    snippet_store_then_assert,
    snippet_store_then_assert_after_statement,
    snippet_store_then_assert_in_nested_block,
    snippet_unknown_store_then_angle_assert,
    snippet_unknown_store_then_assert,
    undefined_name_sources,
    write_imported_annotation_pair,
)


@pytest.fixture(scope="module")
def copied_plugin():
    with workspace() as ws:
        result = ws.copy()
        specifier = require_copied_layout(result, DEFAULT_COPY_DEST, cwd=ws.path)
        print(f"F03 copied specifier={specifier}", flush=True)
        yield ws, specifier


def _lint(copied_plugin, source, *, prefix="f03", markers=None, fix=False):
    ws, specifier = copied_plugin
    return lint_f03_source(
        ws, specifier, source, prefix=prefix, markers=markers, fix=fix
    )


# ---------------------------------------------------------------------------
# A. Nested assertions
# ---------------------------------------------------------------------------


def test_nested_as_assertions_report(copied_plugin):
    public = snippet_no_chained_type_assertions()
    twin = snippet_no_chained_type_assertions(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path, result = _lint(copied_plugin, source, prefix=f"chain-{label}")
        print(f"nested-as {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_CHAIN)
    # Two non-const types and no comment. Nesting does not excuse the
    # missing justification: both the chain rule and the safety-comment
    # rule report. The justified arms above stay chain-only.
    for source, label in (
        (snippet_nested_as_without_comment(), "as-bare-chain"),
        (snippet_nested_angle_without_comment(), "angle-bare-chain"),
    ):
        path, result = _lint(copied_plugin, source, prefix=label)
        print(f"uncommented nested chain {label} path={path.name}", flush=True)
        assert_fired(result, RULE_CHAIN)
        assert_fired(result, RULE_SAFE)
        assert_not_fired(result, RULE_WIDEN)
        assert_not_fired(result, RULE_THEN)


def test_parenthesized_assertion_chain_reports(copied_plugin):
    single, chain = parenthesized_chain_sources()
    _, baseline = _lint(copied_plugin, single, prefix="paren-one")
    assert_silent_f03(baseline, RULE_CHAIN)
    _, result = _lint(copied_plugin, chain, prefix="paren-chain")
    assert_only_rule(result, RULE_CHAIN)


def test_nested_angle_bracket_assertions_report(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_nested_angle_brackets(), prefix="angle-chain"
    )
    assert_only_rule(result, RULE_CHAIN)
    # Line 145 reports a nested angle-bracket chain of two types other than
    # unknown. The justification keeps the safety-comment rule silent.
    named = snippet_nested_named_angle_brackets()
    print("angle-named types are not unknown", flush=True)
    _, other = _lint(copied_plugin, named, prefix="angle-named")
    assert_only_rule(other, RULE_CHAIN)
    # Two angle-bracket const assertions, parenthesized, and no comment.
    # Neither the chain rule nor the safety-comment rule reports. A report
    # of either rule fails. Message text and the span node are not read.
    const_angles = snippet_nested_angle_const_chain()
    print("angle-bracket const chain, no comment", flush=True)
    _, const_chain = _lint(
        copied_plugin, const_angles, prefix="angle-const-chain"
    )
    assert_silent_f03(const_chain, RULE_CHAIN)
    assert_silent_f03(const_chain, RULE_SAFE)


def test_as_const_then_non_const_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_as_const_then_non_const(), prefix="const-then"
    )
    assert_only_rule(result, RULE_CHAIN)
    # Same mix, written as an identifier as const as a non-const type.
    # The as const is not wrapped in parentheses, and the second assertion
    # is not const. The justification keeps the safety-comment rule silent.
    # The parenthesized object mix above stays, as does the const-only chain.
    _, bare = _lint(
        copied_plugin,
        snippet_identifier_as_const_then_non_const(),
        prefix="const-then-ident",
    )
    print("identifier as const as a non-const type", flush=True)
    assert_only_rule(bare, RULE_CHAIN)


def test_nested_as_ending_in_as_const_still_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_nested_as_ending_in_as_const(), prefix="end-const"
    )
    assert_only_rule(result, RULE_CHAIN)


def test_nested_named_assertions_without_unknown_report(copied_plugin):
    public_single, public_chain, fresh_single, fresh_chain = named_chain_sources()
    for single, chain, label in (
        (public_single, public_chain, "public"),
        (fresh_single, fresh_chain, "fresh"),
    ):
        _, baseline = _lint(copied_plugin, single, prefix=f"named-one-{label}")
        print(f"named-one {label}", flush=True)
        assert_silent_f03(baseline, RULE_CHAIN)
        path, result = _lint(copied_plugin, chain, prefix=f"named-{label}")
        print(f"named-named {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_CHAIN)


def test_single_assertion_is_silent(copied_plugin):
    single, chain = single_vs_chain_sources()
    _, result = _lint(copied_plugin, single, prefix="single-as")
    assert_silent_f03(result, RULE_CHAIN)
    _, baseline = _lint(copied_plugin, chain, prefix="chain-live")
    assert_only_rule(baseline, RULE_CHAIN)


def test_const_only_assertion_chain_is_silent(copied_plugin):
    mixed, const_only, plain = const_only_chain_sources()
    _, baseline = _lint(copied_plugin, mixed, prefix="mix-live")
    assert_only_rule(baseline, RULE_CHAIN)
    _, result = _lint(copied_plugin, const_only, prefix="const-only")
    assert_silent_f03(result, RULE_CHAIN)
    _, plain_result = _lint(copied_plugin, plain, prefix="const-plain")
    assert_silent_f03(plain_result, RULE_CHAIN)


# ---------------------------------------------------------------------------
# B. Known flowing into a forbidden target
# ---------------------------------------------------------------------------


def test_known_object_annotated_as_open_record_reports(copied_plugin):
    public = snippet_no_known_value_widening()
    twin = snippet_no_known_value_widening(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path, result = _lint(copied_plugin, source, prefix=f"ann-{label}")
        print(f"known-open-record {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_WIDEN)


def test_known_assignment_return_and_class_field_to_open_record_report(copied_plugin):
    # Open Record stays on assignment, return, and class field. Return and
    # class field also take unknown, object, and the inline object type.
    # The keyword unknown arm still returns the numeric literal. The keyword
    # object arm still returns the array literal. The inline object type and
    # the open Record still use the concrete-key object literal. Four more
    # arms return that same literal from a function whose return type is the
    # keyword unknown and from a function whose return type is the keyword
    # object, and initialize class fields of those two keywords with that
    # literal. The types are written directly. The values are not const
    # aliases and are not passed to a type predicate.
    for source, label in (
        (snippet_known_assignment_to_open_record(), "assign"),
        (snippet_known_return_to_open_record(), "return"),
        (snippet_known_class_field_to_open_record(), "field"),
        (snippet_known_return_to_unknown(), "return-unknown"),
        (snippet_known_return_to_object(), "return-object"),
        (snippet_known_return_to_anonymous_object(), "return-anon"),
        (snippet_known_class_field_to_unknown(), "field-unknown"),
        (snippet_known_class_field_to_object(), "field-object"),
        (snippet_known_class_field_to_anonymous_object(), "field-anon"),
    ):
        path, result = _lint(copied_plugin, source, prefix=label)
        print(f"known vehicle={label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_WIDEN)
    keyword_arms = object_literal_keyword_return_and_field_sources()
    assert [label for label, _source in keyword_arms] == [
        "objlit-return-unknown",
        "objlit-return-object",
        "objlit-field-unknown",
        "objlit-field-object",
    ]
    for label, source in keyword_arms:
        path, result = _lint(copied_plugin, source, prefix=label)
        print(f"known vehicle={label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_WIDEN)
    # The array literal already returned as object, returned from a function
    # whose return type is the keyword unknown. The numeric literal already
    # returned as unknown, returned from a function whose return type is the
    # keyword object. Those two targets are repeated as class field
    # initializers. Not a const alias, a type predicate, or an alias of
    # unknown or object. The numeric-into-unknown, array-into-object,
    # object-literal, inline-object, and open-record arms above stay.
    crossed = crossed_numeric_array_return_and_field_sources()
    assert [label for label, _source in crossed] == [
        "array-return-unknown",
        "numeric-return-object",
        "array-field-unknown",
        "numeric-field-object",
    ]
    for label, source in crossed:
        path, result = _lint(copied_plugin, source, prefix=label)
        print(f"known vehicle={label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_WIDEN)


def test_known_assertion_to_open_record_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_known_assertion_to_open_record(), prefix="as-record"
    )
    assert_only_rule(result, RULE_WIDEN)
    # The assertion type is a same-file non-generic alias of unknown, of
    # object, or of the open Record the written arm asserts to. The unknown
    # alias is also declared inside the function that contains the assertion.
    # The asserted expression is the object literal, with a justification.
    for label, source in assertion_alias_target_sources():
        path, result = _lint(
            copied_plugin, source, prefix=f"as-alias-{label}"
        )
        print(f"assertion alias target {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_WIDEN)


def test_known_into_unknown_and_object_reports(copied_plugin):
    _, unknown = _lint(
        copied_plugin, snippet_known_into_unknown(), prefix="num-unknown"
    )
    assert_only_rule(unknown, RULE_WIDEN)
    _, obj = _lint(copied_plugin, snippet_known_into_object(), prefix="arr-object")
    assert_only_rule(obj, RULE_WIDEN)
    # Numeric literal annotated as the keyword object. Not a const alias,
    # a type predicate, or a Record target.
    _, numeric_object = _lint(
        copied_plugin,
        snippet_known_numeric_into_object(),
        prefix="num-object",
    )
    assert_only_rule(numeric_object, RULE_WIDEN)
    # Binding already annotated object, then the same array literal the
    # object annotation flags. Not a const alias, a type predicate, or Record.
    _, assigned_object = _lint(
        copied_plugin,
        snippet_known_assigned_into_object(),
        prefix="arr-object-asg",
    )
    assert_only_rule(assigned_object, RULE_WIDEN)


def test_known_assigned_into_unknown_or_object_reports(copied_plugin):
    _, annotated = _lint(
        copied_plugin, snippet_known_into_unknown(), prefix="ann-unknown"
    )
    assert_only_rule(annotated, RULE_WIDEN)
    _, assigned = _lint(
        copied_plugin, snippet_known_assigned_into_unknown(), prefix="asg-unknown"
    )
    assert_only_rule(assigned, RULE_WIDEN)
    # The same concrete-key object literal already annotated as unknown,
    # assigned into a binding already annotated unknown, and into a binding
    # already annotated object. Not a const alias, a Record, an inline
    # object type, or a type predicate. The numeric assignment above stays.
    _, object_unknown = _lint(
        copied_plugin,
        snippet_known_object_literal_assigned_into_unknown(),
        prefix="obj-asg-unknown",
    )
    assert_only_rule(object_unknown, RULE_WIDEN)
    _, object_object = _lint(
        copied_plugin,
        snippet_known_object_literal_assigned_into_object(),
        prefix="obj-asg-object",
    )
    assert_only_rule(object_object, RULE_WIDEN)
    # The array literal already assigned into object, written into a binding
    # already annotated unknown. The numeric literal already assigned into
    # unknown, written into a binding already annotated object. Not a const
    # alias, a Record, an inline object type, or a type predicate. The
    # numeric-into-unknown assignment, the array-into-object assignment, and
    # the object-literal assignments stay.
    _, array_unknown = _lint(
        copied_plugin,
        snippet_known_array_assigned_into_unknown(),
        prefix="arr-asg-unknown",
    )
    assert_only_rule(array_unknown, RULE_WIDEN)
    _, numeric_object = _lint(
        copied_plugin,
        snippet_known_numeric_assigned_into_object(),
        prefix="num-asg-object",
    )
    assert_only_rule(numeric_object, RULE_WIDEN)
    # A const alias of the numeric literal already assigned as 1, written
    # into a binding already annotated unknown. A const alias of the array
    # literal already returned as [] from a function whose return type is
    # object. A class field typed unknown initialized with a const alias of
    # that same numeric literal. Not a variable annotation of the alias, not
    # a type predicate, and not a later assertion. The literal arms above
    # stay, as does the object-literal const alias into the open record.
    arms = const_alias_numeric_array_vehicle_sources()
    assert [label for label, _source in arms] == [
        "assign-unknown",
        "return-object",
        "field-unknown",
    ]
    for label, source in arms:
        path, result = _lint(copied_plugin, source, prefix=f"alias-{label}")
        print(f"const alias vehicle={label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_WIDEN)


def test_known_object_literal_into_unknown_or_object_reports(copied_plugin):
    _, numeric = _lint(
        copied_plugin, snippet_known_into_unknown(), prefix="objunk-num"
    )
    assert_only_rule(numeric, RULE_WIDEN)
    _, result = _lint(
        copied_plugin, snippet_known_object_literal_into_unknown(), prefix="obj-unknown"
    )
    assert_only_rule(result, RULE_WIDEN)
    # The same concrete-key object literal, annotated as the keyword object.
    # Not a const alias, a Record, an inline object type, or a type predicate.
    _, object_ann = _lint(
        copied_plugin,
        snippet_known_object_literal_into_object(),
        prefix="obj-object",
    )
    assert_only_rule(object_ann, RULE_WIDEN)


def test_known_into_anonymous_object_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_known_into_anonymous_object(), prefix="anon-ann"
    )
    assert_only_rule(result, RULE_WIDEN)
    # The numeric literal already annotated as unknown, now annotated as
    # that same inline object type. Not a type predicate, and not stored
    # under unknown. The object-literal arm above stays.
    _, numeric_anon = _lint(
        copied_plugin,
        snippet_known_numeric_into_anonymous_object(),
        prefix="num-anon",
    )
    assert_only_rule(numeric_anon, RULE_WIDEN)
    # The array literal already annotated as object, now annotated as
    # Record<string, Command>. Not a type predicate, and not stored under
    # unknown.
    _, array_record = _lint(
        copied_plugin,
        snippet_known_array_into_open_record(),
        prefix="arr-record",
    )
    assert_only_rule(array_record, RULE_WIDEN)


def test_known_assigned_or_asserted_into_anonymous_object_reports(copied_plugin):
    _, annotated = _lint(
        copied_plugin, snippet_known_into_anonymous_object(), prefix="anon-live"
    )
    assert_only_rule(annotated, RULE_WIDEN)
    _, assigned = _lint(
        copied_plugin,
        snippet_known_assigned_into_anonymous_object(),
        prefix="anon-asg",
    )
    assert_only_rule(assigned, RULE_WIDEN)
    # The asserted expression is the object literal already annotated as
    # this inline object type. The target is that same inline type, with a
    # justification. Not a const alias, a named alias, a keyword, or Record.
    _, asserted = _lint(
        copied_plugin,
        snippet_known_asserted_into_anonymous_object(),
        prefix="anon-as",
    )
    assert_only_rule(asserted, RULE_WIDEN)


def test_array_literal_and_const_alias_non_predicate_widenings_report(copied_plugin):
    # Annotation arms and const-alias assertions stay in the same list.
    # Four arms assert the literal itself, with a justification: numeric to
    # unknown, the array literal already annotated as object to object, the
    # concrete-key object literal to unknown, and that same literal to the
    # keyword object. Two further arms cross those keyword pairings, each
    # with a justification: that same array literal asserted to unknown, and
    # that same numeric literal asserted to object. Not a predicate, a
    # Record, an inline object type, or a const alias.
    for label, source in non_predicate_widening_gap_sources():
        path, result = _lint(copied_plugin, source, prefix=f"gap-{label}")
        print(f"non-predicate widening {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_WIDEN)


def test_known_value_kind_carrier_target_product_reports(copied_plugin):
    # One cell per value kind, non-predicate carrier, and target on line 146.
    # Each file is linted alone, so a missing report for that combination
    # fails this assertion. The named arms above stay.
    cells = known_widening_product_sources()
    assert len(cells) == 6 * 5 * 4
    for label, source in cells:
        path, result = _lint(copied_plugin, source, prefix=f"cell-{label}")
        print(f"widening product {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_WIDEN)


def test_known_into_index_signature_open_dictionary_reports(copied_plugin):
    # Open Record is the scored open-dictionary spelling. An index-signature
    # type literal is not that spelling and is not required to report.
    print("open-dictionary target is Record<string, …>", flush=True)
    _, result = _lint(
        copied_plugin, snippet_no_known_value_widening(twin=True), prefix="open-record"
    )
    assert_only_rule(result, RULE_WIDEN)


def test_const_alias_of_known_object_assigned_to_open_record_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_const_alias_to_open_record(), prefix="const-alias"
    )
    assert_only_rule(result, RULE_WIDEN)


# ---------------------------------------------------------------------------
# C. Widening silence
# ---------------------------------------------------------------------------


def test_empty_dictionary_accumulator_on_open_record_is_silent(copied_plugin):
    concrete, empty = empty_dictionary_sources()
    _, baseline = _lint(copied_plugin, concrete, prefix="empty-live")
    assert_only_rule(baseline, RULE_WIDEN)
    _, result = _lint(copied_plugin, empty, prefix="empty-const")
    assert_silent_f03(result, RULE_WIDEN)


def test_empty_dictionary_assigned_or_returned_on_open_record_is_silent(copied_plugin):
    concrete, empty = empty_assignment_sources()
    _, baseline = _lint(copied_plugin, concrete, prefix="asg-live")
    assert_only_rule(baseline, RULE_WIDEN)
    _, result = _lint(copied_plugin, empty, prefix="empty-asg")
    assert_silent_f03(result, RULE_WIDEN)


def test_finite_key_record_targets_are_silent(copied_plugin):
    (
        open_record,
        literal_keys,
        named_keys,
        string_alias,
        block_string,
        block_finite,
        vehicles,
    ) = finite_key_sources()
    _, baseline = _lint(copied_plugin, open_record, prefix="fin-live")
    print("written string key reports", flush=True)
    assert_only_rule(baseline, RULE_WIDEN)
    _, literal = _lint(copied_plugin, literal_keys, prefix="fin-lit")
    print("union of literal keys is silent", flush=True)
    assert_silent_f03(literal, RULE_WIDEN)
    _, named = _lint(copied_plugin, named_keys, prefix="fin-named")
    print("named alias of a finite union is silent", flush=True)
    assert_silent_f03(named, RULE_WIDEN)
    _, aliased = _lint(copied_plugin, string_alias, prefix="fin-str-alias")
    print("same-file alias of string is an open record key", flush=True)
    assert_only_rule(aliased, RULE_WIDEN)
    _, blocked = _lint(copied_plugin, block_string, prefix="fin-str-block")
    print("block-scoped alias of string is an open record key", flush=True)
    assert_only_rule(blocked, RULE_WIDEN)
    _, blocked_finite = _lint(copied_plugin, block_finite, prefix="fin-block-finite")
    print("block-scoped alias of a finite union is silent", flush=True)
    assert_silent_f03(blocked_finite, RULE_WIDEN)
    # Same object and the same written union as the reporting open-string
    # annotation. The record is an assignment target, a return type, a class
    # field, or a justified assertion, not a const annotation.
    assert [label for label, _source in vehicles] == [
        "assign",
        "return",
        "field",
        "assert",
    ]
    for label, source in vehicles:
        path, result = _lint(copied_plugin, source, prefix=f"fin-{label}")
        print(f"finite-key vehicle={label} path={path.name}", flush=True)
        assert_silent_f03(result, RULE_WIDEN)


def test_satisfies_open_record_is_silent(copied_plugin):
    annotated, satisfied = satisfies_sources()
    _, baseline = _lint(copied_plugin, annotated, prefix="sat-live")
    assert_only_rule(baseline, RULE_WIDEN)
    _, result = _lint(copied_plugin, satisfied, prefix="satisfies")
    assert_silent_f03(result, RULE_WIDEN)


def test_named_interface_and_named_alias_with_those_keys_are_silent(copied_plugin):
    for twin, label in ((False, "public"), (True, "twin")):
        anonymous, interface, alias = named_owner_sources(twin=twin)
        _, baseline = _lint(
            copied_plugin, anonymous, prefix=f"named-live-{label}"
        )
        print(f"named-owner baseline {label}", flush=True)
        assert_only_rule(baseline, RULE_WIDEN)
        _, iface = _lint(copied_plugin, interface, prefix=f"iface-{label}")
        assert_silent_f03(iface, RULE_WIDEN)
        _, named = _lint(copied_plugin, alias, prefix=f"named-alias-{label}")
        assert_silent_f03(named, RULE_WIDEN)


def test_imported_type_name_annotation_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    record_path, imported_path = write_imported_annotation_pair(ws)
    baseline = lint_f03(ws, [record_path], specifier)
    print(
        f"imported-type record path={record_path.name} exit={baseline.returncode}",
        flush=True,
    )
    assert_only_rule(baseline, RULE_WIDEN)
    result = lint_f03(ws, [imported_path], specifier)
    print(
        f"imported-type name path={imported_path.name} exit={result.returncode}",
        flush=True,
    )
    assert_silent_f03(result, RULE_WIDEN)


def test_unreassigned_let_and_var_literal_aliases_are_silent(copied_plugin):
    const_arm, let_arm, var_arm = binding_keyword_alias_sources()
    _, baseline = _lint(copied_plugin, const_arm, prefix="let-live")
    assert_only_rule(baseline, RULE_WIDEN)
    _, let_result = _lint(copied_plugin, let_arm, prefix="let-alias")
    assert_silent_f03(let_result, RULE_WIDEN)
    _, var_result = _lint(copied_plugin, var_arm, prefix="var-alias")
    assert_silent_f03(var_result, RULE_WIDEN)
    # Same unknown variable annotation and the same literal. Only the alias
    # keyword changes. The alias is not passed to a type predicate.
    for kind, const_src, let_src, var_src in literal_keyword_alias_unknown_sources():
        _, known = _lint(copied_plugin, const_src, prefix=f"{kind}-const")
        print(f"const alias of {kind} literal into unknown", flush=True)
        assert_only_rule(known, RULE_WIDEN)
        _, let_silent = _lint(copied_plugin, let_src, prefix=f"{kind}-let")
        print(f"unreassigned let alias of {kind} literal into unknown", flush=True)
        assert_silent_f03(let_silent, RULE_WIDEN)
        _, var_silent = _lint(copied_plugin, var_src, prefix=f"{kind}-var")
        print(f"unreassigned var alias of {kind} literal into unknown", flush=True)
        assert_silent_f03(var_silent, RULE_WIDEN)


def test_undefined_type_name_is_not_an_open_dictionary_target(copied_plugin):
    record, undefined = undefined_name_sources()
    _, baseline = _lint(copied_plugin, record, prefix="undef-live")
    assert_only_rule(baseline, RULE_WIDEN)
    _, result = _lint(copied_plugin, undefined, prefix="undef")
    assert_silent_f03(result, RULE_WIDEN)


def test_precise_annotation_without_literal_init_on_non_predicate_vehicle_is_silent(
    copied_plugin,
):
    for label, report, silent in annotation_only_sources():
        _, baseline = _lint(copied_plugin, report, prefix=f"annonly-{label}-live")
        print(f"annotation-only report vehicle={label}", flush=True)
        assert_only_rule(baseline, RULE_WIDEN)
        _, result = _lint(copied_plugin, silent, prefix=f"annonly-{label}")
        print(f"annotation-only silence vehicle={label}", flush=True)
        assert_silent_f03(result, RULE_WIDEN)


# ---------------------------------------------------------------------------
# D. Local unknown type predicates
# ---------------------------------------------------------------------------


def test_known_argument_to_local_unknown_type_predicate_reports(copied_plugin):
    public = snippet_known_to_unknown_predicate()
    twin = snippet_known_to_unknown_predicate(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path, result = _lint(copied_plugin, source, prefix=f"pred-{label}")
        print(f"predicate-known {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_WIDEN)
    # Same-file non-generic alias of unknown, including a block-scoped alias.
    # The parameter is not the token unknown. The widening rule stays silent.
    # The written unknown parameter above still has to report. A report of
    # the widening rule on the alias parameter fails.
    for block, label in ((False, "alias"), (True, "block-alias")):
        path, result = _lint(
            copied_plugin,
            snippet_alias_unknown_predicate_parameter(block=block),
            prefix=f"pred-{label}",
        )
        print(f"predicate-alias block={block} path={path.name}", flush=True)
        assert_silent_f03(result, RULE_WIDEN)


def test_known_argument_to_union_containing_unknown_predicate_reports(copied_plugin):
    _, result = _lint(
        copied_plugin,
        snippet_known_to_union_unknown_predicate(),
        prefix="pred-union",
    )
    assert_only_rule(result, RULE_WIDEN)
    # The parameter is unknown | string: unknown is a member, not the last
    # member. The argument is a string literal. The written string | unknown
    # arm above stays, as do the alias-member arms below.
    _, leading = _lint(
        copied_plugin,
        snippet_known_to_unknown_or_string_predicate(),
        prefix="pred-union-leading",
    )
    print("predicate unknown | string string-literal argument", flush=True)
    assert_only_rule(leading, RULE_WIDEN)
    # A same-file alias of unknown, and a block-scoped alias of unknown,
    # each used as one member of the union. The written string | unknown
    # arm above stays and still has to report. The alias-member parameter
    # stays silent for the widening rule. A report of that rule fails.
    for block, label in ((False, "alias-union"), (True, "block-alias-union")):
        path, result = _lint(
            copied_plugin,
            snippet_alias_unknown_union_member_predicate(block=block),
            prefix=f"pred-{label}",
        )
        print(
            f"predicate-alias-union block={block} path={path.name}",
            flush=True,
        )
        assert_silent_f03(result, RULE_WIDEN)


def test_const_alias_and_precise_annotation_to_unknown_predicate_report(copied_plugin):
    _, const_arm = _lint(
        copied_plugin,
        snippet_const_alias_to_open_record(twin=True),
        prefix="pred-const",
    )
    assert_only_rule(const_arm, RULE_WIDEN)
    _, annotated = _lint(
        copied_plugin,
        snippet_precise_annotation_to_predicate(twin=True),
        prefix="pred-ann",
    )
    assert_only_rule(annotated, RULE_WIDEN)


def test_non_string_known_argument_to_unknown_predicate_reports(copied_plugin):
    # Line 146 scores a predicate only for a string literal and an
    # annotation-only local. Numeric, array, and object literals are known
    # on the five non-predicate vehicles, not on this call.
    for label in ("a", "b"):
        _, result = _lint(
            copied_plugin,
            snippet_known_to_unknown_predicate(twin=True),
            prefix=f"nonstr-{label}",
        )
        print(f"predicate string literal {label}", flush=True)
        assert_only_rule(result, RULE_WIDEN)


def test_unknown_argument_to_local_type_predicate_is_silent(copied_plugin):
    literal, declared, called = predicate_argument_sources()
    _, baseline = _lint(copied_plugin, literal, prefix="unk-live")
    assert_only_rule(baseline, RULE_WIDEN)
    _, unknown = _lint(copied_plugin, declared, prefix="pred-unk")
    assert_silent_f03(unknown, RULE_WIDEN)
    _, reader = _lint(copied_plugin, called, prefix="pred-read")
    assert_silent_f03(reader, RULE_WIDEN)


def test_let_alias_argument_to_type_predicate_is_silent(copied_plugin):
    direct, let_arm, var_arm = let_predicate_sources()
    _, baseline = _lint(copied_plugin, direct, prefix="plet-live")
    assert_only_rule(baseline, RULE_WIDEN)
    _, result = _lint(copied_plugin, let_arm, prefix="pred-let")
    assert_silent_f03(result, RULE_WIDEN)
    # Same predicate and the same string literal. Only the binding keyword
    # changes. The alias is not annotated, and it is not a numeric, array,
    # or object literal.
    _, var_result = _lint(copied_plugin, var_arm, prefix="pred-var")
    print(
        "unreassigned var alias of the same string literal into the predicate",
        flush=True,
    )
    assert_silent_f03(var_result, RULE_WIDEN)


# ---------------------------------------------------------------------------
# E. Same-file aliases as widening targets
# ---------------------------------------------------------------------------


def test_program_scope_non_generic_alias_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_program_scope_open_dictionary(), prefix="prog-open"
    )
    assert_only_rule(result, RULE_WIDEN)
    # The variable annotation above stays. These arms use that same open
    # Record, and aliases of unknown and object, as a return type, a class
    # field type, and an assignment into an already-declared let. The unknown
    # alias is also block-scoped on the return type of the function that
    # returns the numeric literal. The values are that literal, the array
    # literal, and the concrete-key object. None of them is stored and then
    # asserted.
    for label, source in alias_non_annotation_vehicle_sources():
        path, result = _lint(copied_plugin, source, prefix=f"alias-{label}")
        print(f"alias vehicle {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_WIDEN)


def test_block_scoped_open_dictionary_alias_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_block_scoped_open_dictionary(), prefix="block-open"
    )
    assert_only_rule(result, RULE_WIDEN)


def test_block_scoped_unknown_or_object_alias_reports(copied_plugin):
    _, unknown = _lint(
        copied_plugin, snippet_block_scoped_unknown(), prefix="block-unk"
    )
    assert_only_rule(unknown, RULE_WIDEN)
    _, obj = _lint(
        copied_plugin, snippet_block_scoped_object(), prefix="block-obj"
    )
    print("block-scoped object alias used as object widening target", flush=True)
    assert_only_rule(obj, RULE_WIDEN)


def test_transparent_generic_alias_of_open_dictionary_reports(copied_plugin):
    _, open_arm = _lint(
        copied_plugin, snippet_identity_open_dictionary(), prefix="id-open"
    )
    assert_only_rule(open_arm, RULE_WIDEN)


def test_forward_reference_non_generic_alias_reports(copied_plugin):
    unknown, object_arm, open_record = forward_alias_sources()
    for source, label in (
        (unknown, "unknown"),
        (object_arm, "object"),
        (open_record, "open"),
    ):
        path, result = _lint(copied_plugin, source, prefix=f"fwd-{label}")
        print(f"forward-alias {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_WIDEN)


# ---------------------------------------------------------------------------
# F. Widen then assert
# ---------------------------------------------------------------------------


def test_const_known_stored_as_unknown_then_asserted_reports(copied_plugin):
    public = snippet_unknown_store_then_assert()
    twin = snippet_unknown_store_then_assert(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path, result = _lint(copied_plugin, source, prefix=f"wta-{label}")
        print(f"store-unknown-then-assert {label} path={path.name}", flush=True)
        assert_fired(result, RULE_THEN)
        assert_fired(result, RULE_WIDEN)
    for kind in ("numeric", "array"):
        source = snippet_literal_unknown_store_then_assert(kind)
        path, result = _lint(copied_plugin, source, prefix=f"wta-{kind}")
        print(f"store-unknown-then-assert {kind} path={path.name}", flush=True)
        assert_fired(result, RULE_THEN)
        assert_fired(result, RULE_WIDEN)
    # Same-file non-generic alias of unknown or object. The store still
    # widens, so the widening rule has to report. no-widen-then-assert stays
    # silent. The keyword arms above stay. These arms are not an alias of
    # any and are not a stand-in for a written Record.
    for label, source in alias_store_then_assert_sources():
        path, result = _lint(copied_plugin, source, prefix=f"wta-alias-{label}")
        print(f"store-alias-then-assert {label} path={path.name}", flush=True)
        assert_classified_not_fired(result, RULE_THEN)
        assert_only_rule(result, RULE_WIDEN)


def test_const_known_stored_as_any_object_or_broad_record_then_asserted_reports(
    copied_plugin,
):
    _, any_arm = _lint(
        copied_plugin, snippet_no_widen_then_assert(), prefix="wta-any"
    )
    assert_only_rule(any_arm, RULE_THEN)
    for store in ("object", "record"):
        _, result = _lint(
            copied_plugin,
            snippet_store_then_assert(store, scope="function", narrow="literal"),
            prefix=f"wta-{store}",
        )
        print(f"store-then-assert store={store}", flush=True)
        assert_fired(result, RULE_THEN)
    # Record<string, any> is the other broad-record value argument. The store
    # is still an open string-key record, so widening may also report. Require
    # this rule only on the arm that asserts narrower, and require it to stay
    # silent when that assertion is absent. Do not demand a fully silent lint.
    with_later, without = record_any_store_sources()
    _, later = _lint(copied_plugin, with_later, prefix="wta-record-any")
    print("store-then-assert store=record-any", flush=True)
    assert_fired(later, RULE_THEN)
    _, bare = _lint(copied_plugin, without, prefix="wta-record-any-bare")
    print("store-without-assert store=record-any", flush=True)
    assert_classified_not_fired(bare, RULE_THEN)
    # A dictionary of a named type, including Record<string, Command>, is not
    # the broad-record store. The later narrower assertion of that same const
    # stays silent for this rule. The open-record store still widens. Do not
    # demand a fully silent lint. The Record<string, unknown> arms stay above.
    for label, source in named_value_record_then_assert_sources():
        _, named = _lint(copied_plugin, source, prefix=f"wta-named-{label}")
        print(f"named-value record then assert {label}", flush=True)
        assert_classified_not_fired(named, RULE_THEN)
        assert_only_rule(named, RULE_WIDEN)


def test_widen_then_assert_at_top_level_and_in_a_function_reports(copied_plugin):
    _, top = _lint(
        copied_plugin,
        snippet_store_then_assert("any", scope="top"),
        prefix="wta-top",
    )
    assert_only_rule(top, RULE_THEN)
    _, inner = _lint(
        copied_plugin,
        snippet_store_then_assert("any", scope="function"),
        prefix="wta-fn",
    )
    assert_only_rule(inner, RULE_THEN)
    # The later assertion is still in that function. It is not the next
    # statement, and it may sit in a nested block.
    for source, label in (
        (snippet_store_then_assert_after_statement(), "gap"),
        (snippet_store_then_assert_in_nested_block(), "block"),
    ):
        path, result = _lint(copied_plugin, source, prefix=f"wta-{label}")
        print(f"later-assertion {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_THEN)
    # A nested function is not the same function. The unknown store still widens.
    _, nested = _lint(
        copied_plugin,
        snippet_assert_widened_const_in_nested_function(),
        prefix="wta-nested-fn",
    )
    assert_classified_not_fired(nested, RULE_THEN)
    assert_only_rule(nested, RULE_WIDEN)


def test_const_known_stored_then_angle_bracket_asserted_reports(copied_plugin):
    _, as_arm = _lint(
        copied_plugin, snippet_unknown_store_then_assert(twin=True), prefix="wta-as"
    )
    assert_fired(as_arm, RULE_THEN)
    assert_fired(as_arm, RULE_WIDEN)
    _, result = _lint(
        copied_plugin, snippet_unknown_store_then_angle_assert(), prefix="wta-angle"
    )
    # Line 148 does not name angle-bracket assertions. The unknown store
    # still widens. Do not require or forbid no-widen-then-assert here.
    assert_fired(result, RULE_WIDEN)
    assert_not_fired(result, RULE_SAFE)


def test_widening_without_later_assertion_is_silent_for_this_rule(copied_plugin):
    for label, with_later, without in later_assertion_sources():
        _, later = _lint(copied_plugin, with_later, prefix=f"nolater-{label}-as")
        print(f"later-assertion store={label}", flush=True)
        if label == "any":
            assert_only_rule(later, RULE_THEN)
        else:
            assert_fired(later, RULE_THEN)
            assert_fired(later, RULE_WIDEN)
            assert_not_fired(later, RULE_SAFE)
        _, bare = _lint(copied_plugin, without, prefix=f"nolater-{label}")
        if label == "any":
            assert_silent_f03(bare, RULE_THEN)
        else:
            assert_classified_not_fired(bare, RULE_THEN)
            assert_only_rule(bare, RULE_WIDEN)


def test_asserting_already_unknown_binding_is_silent(copied_plugin):
    assigned, declared = provenance_sources()
    _, baseline = _lint(copied_plugin, assigned, prefix="already-live")
    assert_fired(baseline, RULE_THEN)
    _, result = _lint(copied_plugin, declared, prefix="already")
    assert_silent_f03(result, RULE_THEN)


def test_later_assertion_of_a_different_binding_is_silent_for_this_rule(
    copied_plugin,
):
    assert_wide, assert_other = asserted_binding_sources()
    _, baseline = _lint(copied_plugin, assert_wide, prefix="diff-live")
    assert_fired(baseline, RULE_THEN)
    _, result = _lint(copied_plugin, assert_other, prefix="diff-bind")
    assert_classified_not_fired(result, RULE_THEN)
    assert_only_rule(result, RULE_WIDEN)


def test_later_assertion_still_broad_is_silent_for_this_rule(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_unknown_store_then_assert(twin=True), prefix="broad-live"
    )
    assert_fired(baseline, RULE_THEN)
    _, result = _lint(
        copied_plugin, snippet_later_assert_still_broad(), prefix="still-broad"
    )
    assert_classified_not_fired(result, RULE_THEN)
    assert_fired(result, RULE_WIDEN)
    # Same store, same names. A later assertion back to any or object is not
    # a narrower type. The paired arm still asserts that binding to a fresh
    # object type, which is narrower.
    for label, narrower, same in still_broad_same_type_sources():
        _, narrow = _lint(
            copied_plugin, narrower, prefix=f"broad-{label}-narrow"
        )
        print(f"still-broad narrower store={label}", flush=True)
        if label == "any":
            assert_only_rule(narrow, RULE_THEN)
        else:
            assert_fired(narrow, RULE_THEN)
            assert_fired(narrow, RULE_WIDEN)
            assert_not_fired(narrow, RULE_SAFE)
        _, held = _lint(copied_plugin, same, prefix=f"still-{label}")
        print(f"still-broad same-type store={label}", flush=True)
        if label == "any":
            assert_silent_f03(held, RULE_THEN)
        else:
            assert_classified_not_fired(held, RULE_THEN)
            assert_fired(held, RULE_WIDEN)
            assert_not_fired(held, RULE_SAFE)
    # Same broad-record store. A later assertion back to that record is not a
    # narrower named-field type, so this rule stays silent. The store is still
    # an open string-key record, so widening may report. Do not demand a fully
    # silent lint, and do not treat this rule as the only finding.
    for label, source in still_broad_record_same_type_sources():
        _, held = _lint(
            copied_plugin, source, prefix=f"still-record-{label}"
        )
        print(f"still-broad same record store={label}", flush=True)
        assert_classified_not_fired(held, RULE_THEN)


# ---------------------------------------------------------------------------
# G. Nearby non-empty justification
# ---------------------------------------------------------------------------


def test_non_const_as_without_comment_reports(copied_plugin):
    public = snippet_require_safety_comment_for_type_assertion()
    twin = snippet_require_safety_comment_for_type_assertion(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path, result = _lint(copied_plugin, source, prefix=f"safe-{label}")
        print(f"no-comment {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_SAFE)


def test_angle_bracket_assertion_without_comment_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_angle_without_comment(), prefix="angle-bare"
    )
    assert_only_rule(result, RULE_SAFE)


def test_export_assertion_without_comment_reports(copied_plugin):
    _, result = _lint(
        copied_plugin, snippet_export_without_comment(), prefix="export-bare"
    )
    assert_only_rule(result, RULE_SAFE)


def test_comment_after_assertion_does_not_count(copied_plugin):
    above, after, following = comment_after_sources()
    _, baseline = _lint(copied_plugin, above, prefix="after-live")
    assert_silent_f03(baseline, RULE_SAFE)
    _, result = _lint(copied_plugin, after, prefix="after")
    assert_only_rule(result, RULE_SAFE)
    _, next_line = _lint(copied_plugin, following, prefix="after-next")
    assert_only_rule(next_line, RULE_SAFE)


def test_comment_on_earlier_sibling_does_not_count(copied_plugin):
    above, between, blank, gap_before = comment_on_earlier_sibling_sources()
    _, baseline = _lint(copied_plugin, above, prefix="sib-live")
    assert_silent_f03(baseline, RULE_SAFE)
    _, result = _lint(copied_plugin, between, prefix="sibling")
    assert_only_rule(result, RULE_SAFE)
    _, spaced = _lint(copied_plugin, blank, prefix="blank-line")
    print("only a blank line between the comment and the assertion", flush=True)
    assert_silent_f03(spaced, RULE_SAFE)
    _, earlier_gap = _lint(copied_plugin, gap_before, prefix="gap-before")
    print("blank line is before the comment, not before the assertion", flush=True)
    assert_silent_f03(earlier_gap, RULE_SAFE)


def test_non_marker_empty_and_whitespace_justifications_report(copied_plugin):
    (
        good,
        non_marker,
        empty,
        whitespace,
        no_colon,
        no_colon_fresh,
        glued,
        punctuation,
        punctuation_spaced,
    ) = bad_justification_sources()
    _, ok = _lint(copied_plugin, good, prefix="just-ok")
    assert_silent_f03(ok, RULE_SAFE)
    _, attached = _lint(copied_plugin, glued, prefix="just-glued")
    print("glued non-whitespace immediately after the colon", flush=True)
    assert_silent_f03(attached, RULE_SAFE)
    for source, label in (
        (punctuation, "punct"),
        (punctuation_spaced, "punct-space"),
    ):
        path, result = _lint(copied_plugin, source, prefix=label)
        print(
            f"punctuation is the only non-whitespace after the colon {label} "
            f"path={path.name}",
            flush=True,
        )
        assert_silent_f03(result, RULE_SAFE)
    for source, label in (
        (non_marker, "non-marker"),
        (empty, "empty-colon"),
        (whitespace, "ws-colon"),
        (no_colon, "no-colon"),
        (no_colon_fresh, "no-colon-fresh"),
    ):
        path, result = _lint(copied_plugin, source, prefix=label)
        print(f"bad-justification {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_SAFE)


def test_safety_comment_immediately_above_is_silent(copied_plugin):
    (
        bare,
        oracle,
        alternate,
        checked,
        leading,
        not_safety,
        before_colon,
    ) = safety_above_sources()
    _, baseline = _lint(copied_plugin, bare, prefix="above-live")
    assert_only_rule(baseline, RULE_SAFE)
    for source, label in (
        (oracle, "oracle"),
        (alternate, "other"),
        (checked, "checked"),
        (leading, "leading"),
        (before_colon, "before-colon"),
    ):
        path, result = _lint(copied_plugin, source, prefix=f"above-{label}")
        print(f"safety-above {label} path={path.name}", flush=True)
        assert_silent_f03(result, RULE_SAFE)
    _, rejected = _lint(copied_plugin, not_safety, prefix="above-other-marker")
    assert_only_rule(rejected, RULE_SAFE)


def test_block_comment_immediately_above_is_silent(copied_plugin):
    (
        bare,
        block,
        block_foreign,
        block_empty,
        inline_valid,
        inline_foreign,
        inline_empty,
        angle_foreign,
    ) = block_comment_sources()
    _, baseline = _lint(copied_plugin, bare, prefix="block-live")
    assert_only_rule(baseline, RULE_SAFE)
    _, result = _lint(copied_plugin, block, prefix="block-above")
    assert_silent_f03(result, RULE_SAFE)
    _, inline = _lint(copied_plugin, inline_valid, prefix="block-inline-ok")
    assert_silent_f03(inline, RULE_SAFE)
    for source, label in (
        (block_foreign, "block-foreign"),
        (block_empty, "block-empty"),
        (inline_foreign, "inline-foreign"),
        (inline_empty, "inline-empty"),
        (angle_foreign, "angle-inline-foreign"),
    ):
        path, rejected = _lint(copied_plugin, source, prefix=label)
        print(
            f"comment is not a justification {label} path={path.name}",
            flush=True,
        )
        assert_only_rule(rejected, RULE_SAFE)


def test_inline_and_export_justifications_are_silent(copied_plugin):
    bare, inline_source = inline_justification_sources()
    _, inline_baseline = _lint(copied_plugin, bare, prefix="inline-live")
    assert_only_rule(inline_baseline, RULE_SAFE)
    _, inline = _lint(copied_plugin, inline_source, prefix="inline")
    assert_silent_f03(inline, RULE_SAFE)
    export_bare, export_ok = export_justification_sources()
    _, export_baseline = _lint(copied_plugin, export_bare, prefix="export-live")
    assert_only_rule(export_baseline, RULE_SAFE)
    _, exported = _lint(copied_plugin, export_ok, prefix="export-ok")
    assert_silent_f03(exported, RULE_SAFE)


def test_angle_bracket_with_safety_comment_above_is_silent(copied_plugin):
    (
        bare,
        justified,
        block,
        export_bare,
        export_above,
        inline_bare,
        inline,
    ) = angle_justification_sources()
    _, baseline = _lint(copied_plugin, bare, prefix="ang-live")
    assert_only_rule(baseline, RULE_SAFE)
    _, result = _lint(copied_plugin, justified, prefix="ang-ok")
    assert_silent_f03(result, RULE_SAFE)
    _, block_ok = _lint(copied_plugin, block, prefix="ang-block-ok")
    print(
        "block justification immediately above a non-exported angle-bracket assertion",
        flush=True,
    )
    assert_silent_f03(block_ok, RULE_SAFE)
    _, exported = _lint(copied_plugin, export_bare, prefix="ang-export-bare")
    print("exported angle-bracket assertion with no comment", flush=True)
    assert_only_rule(exported, RULE_SAFE)
    _, export_ok = _lint(copied_plugin, export_above, prefix="ang-export-ok")
    print("justification immediately above that same export", flush=True)
    assert_silent_f03(export_ok, RULE_SAFE)
    _, inline_base = _lint(copied_plugin, inline_bare, prefix="ang-inline-live")
    assert_only_rule(inline_base, RULE_SAFE)
    _, inline_ok = _lint(copied_plugin, inline, prefix="ang-inline-ok")
    print("inline justification on a non-exported angle-bracket assertion", flush=True)
    assert_silent_f03(inline_ok, RULE_SAFE)


def test_as_const_and_angle_bracket_const_need_no_comment(copied_plugin):
    array_report, array_const, object_report, object_const = const_exemption_sources()
    _, array_bad = _lint(copied_plugin, array_report, prefix="arr-as")
    assert_only_rule(array_bad, RULE_SAFE)
    _, as_const = _lint(copied_plugin, array_const, prefix="as-const")
    assert_silent_f03(as_const, RULE_SAFE)
    _, object_bad = _lint(copied_plugin, object_report, prefix="obj-as")
    assert_only_rule(object_bad, RULE_SAFE)
    _, angle_const = _lint(copied_plugin, object_const, prefix="angle-const")
    assert_silent_f03(angle_const, RULE_SAFE)
    _, const_chain = _lint(
        copied_plugin,
        snippet_const_only_chain(twin=True),
        prefix="const-chain-bare",
    )
    assert_silent_f03(const_chain, RULE_CHAIN)
    assert_silent_f03(const_chain, RULE_SAFE)


# ---------------------------------------------------------------------------
# H. Markers list
# ---------------------------------------------------------------------------


def test_omitted_markers_default_to_safety(copied_plugin):
    bare, safety, other = omitted_marker_sources()
    _, missing = _lint(copied_plugin, bare, prefix="omit-miss")
    assert_only_rule(missing, RULE_SAFE)
    _, ok = _lint(copied_plugin, safety, prefix="omit-ok")
    assert_silent_f03(ok, RULE_SAFE)
    _, rejected = _lint(copied_plugin, other, prefix="omit-other")
    assert_only_rule(rejected, RULE_SAFE)


def test_explicit_safety_markers_match_the_omitted_default(copied_plugin):
    bare, justified = explicit_marker_sources()
    _, missing = _lint(
        copied_plugin, bare, prefix="exp-miss", markers=["SAFETY"]
    )
    assert_only_rule(missing, RULE_SAFE)
    _, ok = _lint(
        copied_plugin, justified, prefix="exp-ok", markers=["SAFETY"]
    )
    assert_silent_f03(ok, RULE_SAFE)


def test_invariant_only_markers_accept_invariant_and_reject_safety(copied_plugin):
    markers = ["INVARIANT"]
    accepted, rejected = invariant_marker_sources()
    _, ok = _lint(copied_plugin, accepted, prefix="inv-ok", markers=markers)
    assert_silent_f03(ok, RULE_SAFE)
    _, bad = _lint(copied_plugin, rejected, prefix="inv-reject", markers=markers)
    assert_only_rule(bad, RULE_SAFE)


def test_multiple_markers_are_alternatives(copied_plugin):
    markers, bare, rejected, one, two = alternative_marker_sources()
    _, missing = _lint(
        copied_plugin, bare, prefix="multi-miss", markers=markers
    )
    assert_only_rule(missing, RULE_SAFE)
    _, foreign = _lint(
        copied_plugin, rejected, prefix="multi-foreign", markers=markers
    )
    assert_only_rule(foreign, RULE_SAFE)
    _, first = _lint(copied_plugin, one, prefix="multi-a", markers=markers)
    assert_silent_f03(first, RULE_SAFE)
    _, second = _lint(copied_plugin, two, prefix="multi-b", markers=markers)
    assert_silent_f03(second, RULE_SAFE)


def test_plus_containing_marker_is_recognized_as_a_whole_marker(copied_plugin):
    (
        marker,
        whole,
        safety,
        decoy,
        left_only,
        right_only,
        glued,
        glued_default,
        leading_default,
    ) = plus_marker_sources()
    markers = [marker]
    _, ok = _lint(copied_plugin, whole, prefix="plus-ok", markers=markers)
    assert_silent_f03(ok, RULE_SAFE)
    _, other = _lint(copied_plugin, safety, prefix="plus-other", markers=markers)
    assert_only_rule(other, RULE_SAFE)
    _, plus_decoy = _lint(copied_plugin, decoy, prefix="plus-decoy", markers=markers)
    assert_only_rule(plus_decoy, RULE_SAFE)
    for source, label in (
        (left_only, "plus-left"),
        (right_only, "plus-right"),
        (glued, "plus-glued"),
    ):
        path, result = _lint(copied_plugin, source, prefix=label, markers=markers)
        print(f"plus piece {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_SAFE)
    _, glued_safety = _lint(copied_plugin, glued_default, prefix="safety-glued")
    print("default marker with one trailing letter", flush=True)
    assert_only_rule(glued_safety, RULE_SAFE)
    _, leading = _lint(copied_plugin, leading_default, prefix="safety-leading")
    print("word, space, then the whole default marker", flush=True)
    assert_silent_f03(leading, RULE_SAFE)


# ---------------------------------------------------------------------------
# I. Host fix mode does not rewrite and still reports
# ---------------------------------------------------------------------------


def test_fix_mode_leaves_chained_assertion_in_place_and_still_reports(copied_plugin):
    ws, specifier = copied_plugin
    path, _probe = lint_f03_source(
        ws, specifier, snippet_no_chained_type_assertions(twin=True), prefix="fix-ch"
    )
    before = path.read_bytes()
    result = lint_f03(ws, [path], specifier, fix=True)
    assert_fix_preserves_source(path, before, result, RULE_CHAIN)
    assert_only_rule(result, RULE_CHAIN)


def test_fix_mode_leaves_known_widening_in_place_and_still_reports(copied_plugin):
    ws, specifier = copied_plugin
    path, _probe = lint_f03_source(
        ws, specifier, snippet_no_known_value_widening(twin=True), prefix="fix-w"
    )
    before = path.read_bytes()
    result = lint_f03(ws, [path], specifier, fix=True)
    assert_fix_preserves_source(path, before, result, RULE_WIDEN)
    assert_only_rule(result, RULE_WIDEN)


def test_fix_mode_leaves_widen_then_assert_in_place_and_still_reports(copied_plugin):
    ws, specifier = copied_plugin
    path, _probe = lint_f03_source(
        ws, specifier, snippet_no_widen_then_assert(twin=True), prefix="fix-t"
    )
    before = path.read_bytes()
    result = lint_f03(ws, [path], specifier, fix=True)
    assert_fix_preserves_source(path, before, result, RULE_THEN)
    assert_only_rule(result, RULE_THEN)


def test_fix_mode_leaves_unjustified_assertion_in_place_and_still_reports(
    copied_plugin,
):
    ws, specifier = copied_plugin
    path, _probe = lint_f03_source(
        ws,
        specifier,
        snippet_require_safety_comment_for_type_assertion(twin=True),
        prefix="fix-s",
    )
    before = path.read_bytes()
    result = lint_f03(ws, [path], specifier, fix=True)
    assert_fix_preserves_source(path, before, result, RULE_SAFE)
    assert_only_rule(result, RULE_SAFE)


def test_fix_mode_leaves_further_chained_widening_widen_and_safety_violators_in_place(
    copied_plugin,
):
    ws, specifier = copied_plugin
    cases = (
        (snippet_parenthesized_chain(), RULE_CHAIN, "fix-paren"),
        (snippet_known_into_unknown(), RULE_WIDEN, "fix-unk"),
        (snippet_store_then_assert("object", scope="top", narrow="literal"), RULE_THEN, "fix-obj"),
        (snippet_angle_without_comment(), RULE_SAFE, "fix-ang"),
    )
    for source, rule_name, prefix in cases:
        path, _probe = lint_f03_source(ws, specifier, source, prefix=prefix)
        before = path.read_bytes()
        result = lint_f03(ws, [path], specifier, fix=True)
        print(f"fix-non-oracle rule={rule_name} path={path.name}", flush=True)
        assert_fix_preserves_source(path, before, result, rule_name)


# ---------------------------------------------------------------------------
# Determinism: same source, same four rules, same markers list
# ---------------------------------------------------------------------------


def test_same_source_rules_and_markers_yield_the_same_diagnostics(copied_plugin):
    ws, specifier = copied_plugin
    source = snippet_require_safety_comment_for_type_assertion(twin=True)
    markers = ["INVARIANT"]
    path = write_f03_source(ws, source, prefix="det")
    first = lint_f03(
        ws, [path], specifier, rules=F03_RULE_NAMES, markers=markers
    )
    second = lint_f03(
        ws, [path], specifier, rules=F03_RULE_NAMES, markers=markers
    )
    assert_fired(first, RULE_SAFE)
    left = f03_diagnostic_identity(first)
    right = f03_diagnostic_identity(second)
    print(f"determinism diagnostics {left} vs {right}", flush=True)
    assert left == right
    assert left


def test_omitted_rule_reports_nothing_on_its_violator(copied_plugin):
    """Same violator, plugin registered. Only whether that rule is enabled changes.

    With the four rules on, lint fails and only that rule is attributed.
    With that rule left out and the other three still on, the rule reports
    nothing and the lint succeeds.
    """
    ws, specifier = copied_plugin
    cases = (
        (snippet_no_chained_type_assertions(twin=True), RULE_CHAIN, "omit-chain"),
        (snippet_no_known_value_widening(twin=True), RULE_WIDEN, "omit-widen"),
        (snippet_no_widen_then_assert(twin=True), RULE_THEN, "omit-then"),
        (
            snippet_require_safety_comment_for_type_assertion(twin=True),
            RULE_SAFE,
            "omit-safe",
        ),
    )
    for source, rule_name, prefix in cases:
        path = write_f03_source(ws, source, prefix=prefix)
        enabled = lint_f03(ws, [path], specifier, rules=F03_RULE_NAMES)
        print(f"rule-on {rule_name} path={path.name} exit={enabled.returncode}", flush=True)
        assert_only_rule(enabled, rule_name)
        disabled = lint_f03(
            ws, [path], specifier, rules=rules_omitting(rule_name)
        )
        print(
            f"rule-off {rule_name} path={path.name} exit={disabled.returncode}",
            flush=True,
        )
        assert_silent_f03(disabled, rule_name)


# ---------------------------------------------------------------------------
# J. Unique attribution among the four
# ---------------------------------------------------------------------------


def test_each_unique_violator_attributes_only_its_rule(copied_plugin):
    cases = (
        (snippet_no_chained_type_assertions(twin=True), RULE_CHAIN, "only-chain"),
        (snippet_no_known_value_widening(twin=True), RULE_WIDEN, "only-widen"),
        (snippet_no_widen_then_assert(twin=True), RULE_THEN, "only-then"),
        (
            snippet_require_safety_comment_for_type_assertion(twin=True),
            RULE_SAFE,
            "only-safe",
        ),
    )
    for source, rule_name, prefix in cases:
        path, result = _lint(copied_plugin, source, prefix=prefix)
        print(f"unique {rule_name} path={path.name}", flush=True)
        assert_only_rule(result, rule_name)
