# feature: F02
"""Acceptance tests: reject eager array pipelines, reducer copies, empty spreads."""

from __future__ import annotations

import pytest

from _harness import DEFAULT_COPY_DEST, workspace
from F01_helpers import (
    assert_fired,
    assert_only_rule,
    fresh_ident,
    require_copied_layout,
    snippet_no_array_filter_map,
    snippet_no_conditional_empty_object_spread,
    snippet_no_reduce_accumulator_copy,
)
from F02_helpers import (
    ARRAY_CHAIN_KEEPERS,
    ARRAY_COPY_METHODS,
    assert_more_rule_findings,
    assert_silent_f02,
    lint_f02,
    lint_source,
    run_fix_and_assert,
    snippet_annotated_binding_mixed_pair,
    snippet_annotated_param_mixed_pair,
    snippet_array_copy_on_init,
    snippet_array_from_accumulator,
    snippet_array_parent_empty_branch_spread,
    snippet_assign_accumulator_as_target,
    snippet_assign_inside_map,
    snippet_both_branches_non_empty_spread,
    snippet_computed_string_literal_methods,
    snippet_concat_string_init,
    snippet_concat_unknown_collection,
    snippet_const_alias_of_known_array,
    snippet_const_local_mixed_pair,
    snippet_custom_object_filter_map,
    snippet_empty_true_branch_spread,
    snippet_flatmap_then_filter_map,
    snippet_generic_array_annotation,
    snippet_item_copy,
    snippet_iterator_from_pipeline,
    snippet_iterator_typed_parameter,
    snippet_iterator_values_pipeline,
    snippet_keeper_then_mixed_pair,
    snippet_map_or_filter_chain_then_mixed_pair,
    snippet_l134_empty_false_spread,
    snippet_l134_object_assign,
    snippet_let_or_var_literal_mixed_pair,
    snippet_local_alias_of_global,
    snippet_map_then_filter_literal,
    snippet_mutating_accumulator,
    snippet_named_callback_outside,
    snippet_nested_function_copy,
    snippet_nested_property_copy,
    snippet_non_adjacent_filter_map,
    snippet_non_conditional_spread,
    snippet_non_literal_computed_method,
    snippet_non_null_assertion_mixed_pair,
    snippet_non_spread_conditional,
    snippet_object_assign_copy,
    snippet_object_without_spread_pattern,
    snippet_one_and_two_pairs,
    snippet_optional_chaining_mixed_pair,
    snippet_property_based_array_field,
    snippet_reassigned_accumulator_alias,
    snippet_reduce_right_concat,
    snippet_reducer_array_spread,
    snippet_reducer_object_spread,
    snippet_same_method_chain,
    snippet_separate_filter_and_map,
    snippet_shadowed_inner_accumulator,
    snippet_shadowed_object_or_array,
    snippet_single_flatmap,
    snippet_snapshot_closure_copy,
    snippet_syntactic_reduce_untyped_receiver,
    snippet_type_alias_binding,
    snippet_type_alias_param,
    write_imported_factory_mixed_pair,
)

RULE_FM = "no-array-filter-map"
RULE_RED = "no-reduce-accumulator-copy"
RULE_SPR = "no-conditional-empty-object-spread"


@pytest.fixture(scope="module")
def copied_plugin():
    with workspace() as ws:
        result = ws.copy()
        specifier = require_copied_layout(result, DEFAULT_COPY_DEST, cwd=ws.path)
        print(f"F02 copied specifier={specifier}", flush=True)
        yield ws, specifier


# ---------------------------------------------------------------------------
# A. Adjacent eager mixed pairs on a known array literal
# ---------------------------------------------------------------------------


def test_array_literal_filter_then_map_reports(copied_plugin):
    ws, specifier = copied_plugin
    public = snippet_no_array_filter_map()
    twin = snippet_no_array_filter_map(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path, result = lint_source(ws, specifier, source, prefix=f"fm-{label}")
        print(f"filter-then-map {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_FM)


def test_array_literal_map_then_filter_reports(copied_plugin):
    ws, specifier = copied_plugin
    _, result = lint_source(ws, specifier, snippet_map_then_filter_literal())
    assert_only_rule(result, RULE_FM)


def test_filter_then_map_reports_in_javascript_and_typescript(copied_plugin):
    ws, specifier = copied_plugin
    arms = (
        ("filter-map", snippet_no_array_filter_map(twin=True)),
        ("map-filter", snippet_map_then_filter_literal()),
    )
    for order, source in arms:
        for ext in ("js", "ts"):
            _, result = lint_source(
                ws, specifier, source, ext=ext, prefix=f"fm-{order}-{ext}"
            )
            print(f"mixed-pair order={order} language={ext}", flush=True)
            assert_only_rule(result, RULE_FM)


# ---------------------------------------------------------------------------
# B. Known-array evidence
# ---------------------------------------------------------------------------


def test_direct_array_parameter_annotation_reports(copied_plugin):
    ws, specifier = copied_plugin
    oracle = snippet_annotated_param_mixed_pair(twin=False)
    twin = snippet_annotated_param_mixed_pair(twin=True)
    for source in (oracle, twin):
        _, result = lint_source(ws, specifier, source, ext="ts", prefix="param")
        assert_only_rule(result, RULE_FM)


def test_direct_array_binding_from_factory_reports(copied_plugin):
    ws, specifier = copied_plugin
    oracle = snippet_annotated_binding_mixed_pair(kind="const", twin=False)
    twin = snippet_annotated_binding_mixed_pair(kind="const", twin=True)
    for source in (oracle, twin):
        _, result = lint_source(ws, specifier, source, ext="ts", prefix="bind")
        assert_only_rule(result, RULE_FM)


def test_let_binding_with_direct_array_annotation_reports(copied_plugin):
    ws, specifier = copied_plugin
    for twin, label in ((False, "oracle"), (True, "twin")):
        source = snippet_annotated_binding_mixed_pair(kind="let", twin=twin)
        _, result = lint_source(
            ws, specifier, source, ext="ts", prefix=f"letann-{label}"
        )
        print(f"let direct array annotation {label}", flush=True)
        assert_only_rule(result, RULE_FM)
    for kind in ("let", "var"):
        for form in ("array", "readonly", "Array", "ReadonlyArray", "tuple"):
            if kind == "let" and form == "array":
                continue
            source = snippet_annotated_binding_mixed_pair(
                kind=kind, twin=True, form=form
            )
            _, result = lint_source(
                ws, specifier, source, ext="ts", prefix=f"{kind}-{form}"
            )
            print(f"{kind} annotation form={form}", flush=True)
            assert_only_rule(result, RULE_FM)


@pytest.mark.parametrize(
    "kind",
    [
        "param_tuple",
        "binding_tuple",
        "param_readonly",
        "param_Array",
        "param_ReadonlyArray",
    ],
)
def test_tuple_and_generic_array_annotations_report(copied_plugin, kind):
    ws, specifier = copied_plugin
    _, untyped = lint_source(
        ws,
        specifier,
        snippet_generic_array_annotation(kind, annotated=False),
        ext="ts",
        prefix=f"{kind}-bare",
    )
    assert_silent_f02(untyped, RULE_FM)
    source = snippet_generic_array_annotation(kind)
    _, result = lint_source(ws, specifier, source, ext="ts", prefix=kind)
    print(f"annotation kind={kind}", flush=True)
    assert_only_rule(result, RULE_FM)


def test_const_local_alias_of_array_literal_reports(copied_plugin):
    ws, specifier = copied_plugin
    _, result = lint_source(ws, specifier, snippet_const_local_mixed_pair())
    assert_only_rule(result, RULE_FM)


def test_const_alias_of_known_array_reports(copied_plugin):
    ws, specifier = copied_plugin
    _, result = lint_source(ws, specifier, snippet_const_alias_of_known_array())
    assert_only_rule(result, RULE_FM)


@pytest.mark.parametrize("method", ARRAY_CHAIN_KEEPERS)
def test_array_preserving_chain_keeps_known_array(copied_plugin, method):
    ws, specifier = copied_plugin
    source = snippet_keeper_then_mixed_pair(method, order="filter_map")
    _, result = lint_source(ws, specifier, source, prefix=f"keep-{method}")
    print(f"keeper {method} filter-then-map", flush=True)
    assert_only_rule(result, RULE_FM)


def test_array_preserving_chain_map_then_filter_reports(copied_plugin):
    ws, specifier = copied_plugin
    filter_map = snippet_keeper_then_mixed_pair("slice", order="filter_map")
    map_filter = snippet_keeper_then_mixed_pair("slice", order="map_filter")
    _, baseline = lint_source(ws, specifier, filter_map, prefix="slice-fm")
    assert_only_rule(baseline, RULE_FM)
    _, result = lint_source(ws, specifier, map_filter, prefix="slice-mf")
    print("keeper slice map-then-filter", flush=True)
    assert_only_rule(result, RULE_FM)


def test_map_chain_keeps_known_array(copied_plugin):
    """A chain through map stays a known array; a later mixed pair on that result reports."""
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_const_local_mixed_pair())
    assert_only_rule(baseline, RULE_FM)
    inline = snippet_keeper_then_mixed_pair("map", order="map_filter")
    _, inline_result = lint_source(ws, specifier, inline, prefix="map-inline")
    print("map chain as mixed-pair receiver (map-then-filter)", flush=True)
    assert_only_rule(inline_result, RULE_FM)
    bound = snippet_map_or_filter_chain_then_mixed_pair("map", order="filter_map")
    _, bound_result = lint_source(ws, specifier, bound, prefix="map-bound")
    print("map chain result then later filter-then-map", flush=True)
    assert_only_rule(bound_result, RULE_FM)


def test_filter_chain_keeps_known_array(copied_plugin):
    """A chain through filter stays a known array; a later mixed pair on that result reports."""
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_const_local_mixed_pair())
    assert_only_rule(baseline, RULE_FM)
    inline = snippet_keeper_then_mixed_pair("filter", order="filter_map")
    _, inline_result = lint_source(ws, specifier, inline, prefix="filter-inline")
    print("filter chain as mixed-pair receiver (filter-then-map)", flush=True)
    assert_only_rule(inline_result, RULE_FM)
    bound = snippet_map_or_filter_chain_then_mixed_pair("filter", order="map_filter")
    _, bound_result = lint_source(ws, specifier, bound, prefix="filter-bound")
    print("filter chain result then later map-then-filter", flush=True)
    assert_only_rule(bound_result, RULE_FM)


# ---------------------------------------------------------------------------
# C. Known-array silence
# ---------------------------------------------------------------------------


def test_iterator_values_pipeline_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(
        ws, specifier, snippet_iterator_values_pipeline(values=False), prefix="val-base"
    )
    assert_only_rule(baseline, RULE_FM)
    _, silent = lint_source(ws, specifier, snippet_iterator_values_pipeline())
    assert_silent_f02(silent, RULE_FM)


def test_iterator_from_and_iterator_typed_parameter_are_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(
        ws,
        specifier,
        snippet_iterator_from_pipeline(wrapped=False),
        prefix="from-base",
    )
    assert_only_rule(baseline, RULE_FM)
    _, from_arm = lint_source(ws, specifier, snippet_iterator_from_pipeline())
    assert_silent_f02(from_arm, RULE_FM)
    _, typed = lint_source(
        ws, specifier, snippet_iterator_typed_parameter(), ext="ts", prefix="iter-ty"
    )
    assert_silent_f02(typed, RULE_FM)


def test_single_flatmap_map_then_map_filter_then_filter_are_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_const_local_mixed_pair())
    assert_only_rule(baseline, RULE_FM)
    _, fired_flat = lint_source(ws, specifier, snippet_flatmap_then_filter_map())
    assert_only_rule(fired_flat, RULE_FM)
    for source, label in (
        (snippet_single_flatmap(), "flatmap"),
        (snippet_same_method_chain("map"), "map-map"),
        (snippet_same_method_chain("filter"), "filter-filter"),
    ):
        _, silent = lint_source(ws, specifier, source, prefix=label)
        print(f"same-method silence {label}", flush=True)
        assert_silent_f02(silent, RULE_FM)


def test_flatmap_then_map_is_not_a_mixed_pair(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_flatmap_then_filter_map())
    assert_only_rule(baseline, RULE_FM)
    _, silent = lint_source(
        ws, specifier, snippet_single_flatmap(), prefix="flat-one"
    )
    assert_silent_f02(silent, RULE_FM)


def test_filter_and_map_as_separate_statements_are_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_const_local_mixed_pair())
    assert_only_rule(baseline, RULE_FM)
    _, silent = lint_source(ws, specifier, snippet_separate_filter_and_map())
    assert_silent_f02(silent, RULE_FM)


def test_non_adjacent_filter_and_map_are_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_const_local_mixed_pair())
    assert_only_rule(baseline, RULE_FM)
    _, keeper = lint_source(
        ws, specifier, snippet_keeper_then_mixed_pair("slice", order="filter_map")
    )
    assert_only_rule(keeper, RULE_FM)
    _, silent = lint_source(ws, specifier, snippet_non_adjacent_filter_map())
    assert_silent_f02(silent, RULE_FM)


def test_custom_object_filter_map_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_const_local_mixed_pair())
    assert_only_rule(baseline, RULE_FM)
    _, silent = lint_source(ws, specifier, snippet_custom_object_filter_map())
    assert_silent_f02(silent, RULE_FM)


def test_unknown_imported_unannotated_receivers_are_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, annotated = lint_source(
        ws,
        specifier,
        snippet_annotated_binding_mixed_pair(kind="const", twin=True),
        ext="ts",
        prefix="unk-base",
    )
    assert_only_rule(annotated, RULE_FM)
    _, unknown = lint_source(
        ws,
        specifier,
        snippet_annotated_binding_mixed_pair(kind="const", twin=True, call_receiver=True),
        ext="ts",
        prefix="unk-call",
    )
    assert_silent_f02(unknown, RULE_FM)
    imported_base = write_imported_factory_mixed_pair(ws, ext="ts", annotated=True)
    imported_base_result = lint_f02(ws, [imported_base], specifier)
    print(f"imported annotated path={imported_base.name}", flush=True)
    assert_only_rule(imported_base_result, RULE_FM)
    imported = write_imported_factory_mixed_pair(ws, ext="ts", annotated=False)
    imported_result = lint_f02(ws, [imported], specifier)
    print(f"imported factory path={imported.name}", flush=True)
    assert_silent_f02(imported_result, RULE_FM)
    _, param_base = lint_source(
        ws,
        specifier,
        snippet_annotated_param_mixed_pair(twin=True, annotated=True),
        ext="ts",
        prefix="param-base",
    )
    assert_only_rule(param_base, RULE_FM)
    _, untyped = lint_source(
        ws,
        specifier,
        snippet_annotated_param_mixed_pair(twin=True, annotated=False),
        ext="ts",
        prefix="param-bare",
    )
    assert_silent_f02(untyped, RULE_FM)


def test_unannotated_parameter_is_not_a_known_array(copied_plugin):
    """Unannotated parameter as receiver of an adjacent mixed pair does not report."""
    ws, specifier = copied_plugin
    annotated = snippet_annotated_param_mixed_pair(twin=True, annotated=True)
    untyped = snippet_annotated_param_mixed_pair(twin=True, annotated=False)
    _, baseline = lint_source(
        ws, specifier, annotated, ext="ts", prefix="unann-base"
    )
    assert_only_rule(baseline, RULE_FM)
    _, silent = lint_source(ws, specifier, untyped, ext="ts", prefix="unann")
    print("unannotated parameter mixed pair is silent", flush=True)
    assert_silent_f02(silent, RULE_FM)


def test_type_alias_of_array_type_parameter_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(
        ws, specifier, snippet_annotated_param_mixed_pair(twin=True), ext="ts"
    )
    assert_only_rule(baseline, RULE_FM)
    _, silent = lint_source(
        ws, specifier, snippet_type_alias_param(), ext="ts", prefix="alias-p"
    )
    assert_silent_f02(silent, RULE_FM)


def test_type_alias_of_array_type_binding_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(
        ws,
        specifier,
        snippet_annotated_binding_mixed_pair(kind="let", twin=True),
        ext="ts",
        prefix="alias-b-base",
    )
    assert_only_rule(baseline, RULE_FM)
    _, silent = lint_source(
        ws, specifier, snippet_type_alias_binding(), ext="ts", prefix="alias-b"
    )
    assert_silent_f02(silent, RULE_FM)


def test_unreassigned_let_and_var_array_literal_aliases_are_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_const_local_mixed_pair())
    assert_only_rule(baseline, RULE_FM)
    for kind in ("let", "var"):
        _, silent = lint_source(
            ws, specifier, snippet_let_or_var_literal_mixed_pair(kind), prefix=kind
        )
        print(f"unreassigned {kind} literal alias", flush=True)
        assert_silent_f02(silent, RULE_FM)


def test_reassigned_annotated_binding_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    fired = snippet_annotated_binding_mixed_pair(kind="let", twin=True)
    silent = snippet_annotated_binding_mixed_pair(
        kind="let", twin=True, extra_write="[]"
    )
    _, baseline = lint_source(ws, specifier, fired, ext="ts", prefix="re-base")
    assert_only_rule(baseline, RULE_FM)
    _, result = lint_source(ws, specifier, silent, ext="ts", prefix="re-write")
    assert_silent_f02(result, RULE_FM)


def test_property_based_array_field_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(
        ws, specifier, snippet_annotated_param_mixed_pair(twin=True), ext="ts"
    )
    assert_only_rule(baseline, RULE_FM)
    _, silent = lint_source(
        ws, specifier, snippet_property_based_array_field(), ext="ts", prefix="prop"
    )
    assert_silent_f02(silent, RULE_FM)


def test_non_literal_computed_method_name_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(
        ws,
        specifier,
        snippet_non_literal_computed_method(literal_key=True),
        prefix="comp-lit",
    )
    assert_only_rule(baseline, RULE_FM)
    _, silent = lint_source(ws, specifier, snippet_non_literal_computed_method())
    assert_silent_f02(silent, RULE_FM)


# ---------------------------------------------------------------------------
# D. Each adjacent pair is its own diagnostic
# ---------------------------------------------------------------------------


def test_extra_trailing_filter_reports_an_additional_pair(copied_plugin):
    ws, specifier = copied_plugin
    one_src, two_src = snippet_one_and_two_pairs("filter")
    _, one = lint_source(ws, specifier, one_src, prefix="one-f")
    _, two = lint_source(ws, specifier, two_src, prefix="two-f")
    assert_more_rule_findings(two, one, RULE_FM)


def test_extra_trailing_map_reports_an_additional_pair(copied_plugin):
    ws, specifier = copied_plugin
    one_src, two_src = snippet_one_and_two_pairs("map")
    _, one = lint_source(ws, specifier, one_src, prefix="one-m")
    _, two = lint_source(ws, specifier, two_src, prefix="two-m")
    assert_more_rule_findings(two, one, RULE_FM)


# ---------------------------------------------------------------------------
# E. Optional chaining, non-null assertions, computed string names
# ---------------------------------------------------------------------------


def test_optional_chaining_mixed_pair_reports(copied_plugin):
    ws, specifier = copied_plugin
    _, result = lint_source(ws, specifier, snippet_optional_chaining_mixed_pair())
    assert_only_rule(result, RULE_FM)


def test_non_null_assertion_mixed_pair_reports(copied_plugin):
    ws, specifier = copied_plugin
    _, dotted = lint_source(ws, specifier, snippet_const_local_mixed_pair())
    assert_only_rule(dotted, RULE_FM)
    _, result = lint_source(
        ws, specifier, snippet_non_null_assertion_mixed_pair(), ext="ts", prefix="nn"
    )
    assert_only_rule(result, RULE_FM)


def test_computed_string_literal_method_names_report(copied_plugin):
    ws, specifier = copied_plugin
    _, result = lint_source(ws, specifier, snippet_computed_string_literal_methods())
    assert_only_rule(result, RULE_FM)


# ---------------------------------------------------------------------------
# F. Inline reducer accumulator copies
# ---------------------------------------------------------------------------


def test_object_assign_object_literal_target_copy_reports(copied_plugin):
    ws, specifier = copied_plugin
    public = snippet_no_reduce_accumulator_copy()
    twin = snippet_no_reduce_accumulator_copy(twin=True)
    oracle = snippet_l134_object_assign(twin=False)
    generated = snippet_l134_object_assign(twin=True)
    two_arg = snippet_object_assign_copy(two_arg=True)
    for source, label in (
        (public, "public"),
        (twin, "twin"),
        (oracle, "l134"),
        (generated, "l134-twin"),
        (two_arg, "two-arg"),
    ):
        _, result = lint_source(ws, specifier, source, prefix=f"asg-{label}")
        print(f"object-assign copy {label}", flush=True)
        assert_only_rule(result, RULE_RED)


def test_object_assign_accumulator_as_later_source_reports(copied_plugin):
    ws, specifier = copied_plugin
    source = snippet_object_assign_copy(later_source=True, function=True)
    _, result = lint_source(ws, specifier, source, prefix="later")
    assert_only_rule(result, RULE_RED)


def test_object_assign_copy_into_local_still_reports(copied_plugin):
    ws, specifier = copied_plugin
    _, returned = lint_source(
        ws, specifier, snippet_object_assign_copy(), prefix="ret"
    )
    assert_only_rule(returned, RULE_RED)
    source = snippet_object_assign_copy(copy_into_local=True)
    _, result = lint_source(ws, specifier, source, prefix="local")
    assert_only_rule(result, RULE_RED)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"method": "reduceRight"},
        {"index": True},
        {"defaulted": True},
        {"bracket": True},
        {"function": True},
    ],
)
def test_reduce_right_and_inline_callback_shapes_report(copied_plugin, kwargs):
    ws, specifier = copied_plugin
    _, reduce_arm = lint_source(
        ws, specifier, snippet_object_assign_copy(), prefix="shape-reduce"
    )
    assert_only_rule(reduce_arm, RULE_RED)
    source = snippet_object_assign_copy(**kwargs)
    _, result = lint_source(ws, specifier, source, prefix="shape")
    print(f"reducer shape {kwargs}", flush=True)
    assert_only_rule(result, RULE_RED)


def test_reduce_right_array_copy_reports(copied_plugin):
    ws, specifier = copied_plugin
    _, reduce_arm = lint_source(
        ws,
        specifier,
        snippet_array_copy_on_init("concat", init_kind="literal"),
        prefix="rrc-reduce",
    )
    assert_only_rule(reduce_arm, RULE_RED)
    _, result = lint_source(ws, specifier, snippet_reduce_right_concat(), prefix="rrc")
    assert_only_rule(result, RULE_RED)


def test_const_accumulator_alias_copy_reports(copied_plugin):
    ws, specifier = copied_plugin
    source = snippet_object_assign_copy(const_alias=True)
    _, result = lint_source(ws, specifier, source, prefix="acc-const")
    assert_only_rule(result, RULE_RED)


def test_array_from_of_accumulator_reports(copied_plugin):
    ws, specifier = copied_plugin
    source = snippet_array_from_accumulator(init="{}")
    _, result = lint_source(ws, specifier, source, prefix="from-obj")
    assert_only_rule(result, RULE_RED)
    _, right = lint_source(
        ws,
        specifier,
        snippet_array_from_accumulator(init="{}", method="reduceRight"),
        prefix="from-right",
    )
    print("reduceRight Array.from of the accumulator", flush=True)
    assert_only_rule(right, RULE_RED)


def test_typescript_accumulator_copy_fails_lint_at_error(copied_plugin):
    ws, specifier = copied_plugin
    _, result = lint_source(
        ws,
        specifier,
        snippet_object_assign_copy(),
        ext="ts",
        prefix="ts-copy",
    )
    print("typescript accumulator copy at error", flush=True)
    assert_only_rule(result, RULE_RED)


@pytest.mark.parametrize("method", ARRAY_COPY_METHODS)
@pytest.mark.parametrize("init_kind", ["literal"])
def test_array_copy_methods_on_locally_evident_array_init_report(
    copied_plugin, method, init_kind
):
    ws, specifier = copied_plugin
    source = snippet_array_copy_on_init(method, init_kind=init_kind)
    _, result = lint_source(ws, specifier, source, prefix=f"copy-{method}")
    print(f"array copy method={method} init={init_kind}", flush=True)
    assert_only_rule(result, RULE_RED)


def test_array_copy_const_initial_alias_reports(copied_plugin):
    ws, specifier = copied_plugin
    source = snippet_array_copy_on_init("concat", init_kind="const")
    _, result = lint_source(ws, specifier, source, prefix="copy-const-init")
    assert_only_rule(result, RULE_RED)


def test_syntactic_reduce_on_untyped_receiver_still_reports(copied_plugin):
    ws, specifier = copied_plugin
    source = snippet_syntactic_reduce_untyped_receiver()
    _, result = lint_source(ws, specifier, source, ext="js", prefix="untyped")
    assert_only_rule(result, RULE_RED)


# ---------------------------------------------------------------------------
# G. Reducer-copy silence
# ---------------------------------------------------------------------------


def test_mutating_accumulator_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_l134_object_assign(twin=True))
    assert_only_rule(baseline, RULE_RED)
    _, silent = lint_source(ws, specifier, snippet_mutating_accumulator())
    assert_silent_f02(silent, RULE_RED)


def test_object_assign_accumulator_as_target_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_object_assign_copy(two_arg=True))
    assert_only_rule(baseline, RULE_RED)
    _, silent = lint_source(ws, specifier, snippet_assign_accumulator_as_target())
    assert_silent_f02(silent, RULE_RED)


def test_item_and_nested_property_copies_are_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_object_assign_copy())
    assert_only_rule(baseline, RULE_RED)
    _, item = lint_source(ws, specifier, snippet_item_copy(), prefix="item")
    assert_silent_f02(item, RULE_RED)
    _, nested = lint_source(
        ws, specifier, snippet_nested_property_copy(), prefix="nested"
    )
    assert_silent_f02(nested, RULE_RED)


def test_local_alias_of_object_assign_or_array_from_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, assign_base = lint_source(ws, specifier, snippet_object_assign_copy())
    assert_only_rule(assign_base, RULE_RED)
    _, from_base = lint_source(
        ws, specifier, snippet_array_from_accumulator(init="{}")
    )
    assert_only_rule(from_base, RULE_RED)
    _, assign_alias = lint_source(
        ws, specifier, snippet_local_alias_of_global("Object.assign"), prefix="oa"
    )
    assert_silent_f02(assign_alias, RULE_RED)
    _, from_alias = lint_source(
        ws, specifier, snippet_local_alias_of_global("Array.from"), prefix="af"
    )
    assert_silent_f02(from_alias, RULE_RED)


def test_concat_on_string_or_unknown_collection_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(
        ws, specifier, snippet_array_copy_on_init("concat", init_kind="literal")
    )
    assert_only_rule(baseline, RULE_RED)
    _, string_arm = lint_source(ws, specifier, snippet_concat_string_init())
    assert_silent_f02(string_arm, RULE_RED)
    _, unknown = lint_source(ws, specifier, snippet_concat_unknown_collection())
    assert_silent_f02(unknown, RULE_RED)


@pytest.mark.parametrize(
    "method", ["slice", "with", "toSpliced", "toSorted", "toReversed"]
)
def test_array_copy_method_without_array_init_is_silent(copied_plugin, method):
    ws, specifier = copied_plugin
    _, baseline = lint_source(
        ws, specifier, snippet_array_copy_on_init(method, init_kind="literal")
    )
    assert_only_rule(baseline, RULE_RED)
    _, silent = lint_source(
        ws, specifier, snippet_array_copy_on_init(method, init_kind="object")
    )
    print(f"copy method {method} without array init", flush=True)
    assert_silent_f02(silent, RULE_RED)


def test_named_nested_shadowed_and_reassigned_copies_are_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_object_assign_copy())
    assert_only_rule(baseline, RULE_RED)
    _, const_alias = lint_source(
        ws,
        specifier,
        snippet_object_assign_copy(const_alias=True),
        prefix="const-alias",
    )
    assert_only_rule(const_alias, RULE_RED)
    _, from_base = lint_source(
        ws,
        specifier,
        snippet_array_from_accumulator(init="{}"),
        prefix="from-global",
    )
    assert_only_rule(from_base, RULE_RED)
    arms = (
        ("named", snippet_named_callback_outside()),
        ("nested", snippet_nested_function_copy()),
        ("snap", snippet_snapshot_closure_copy()),
        ("shadow-acc", snippet_shadowed_inner_accumulator()),
        ("shadow-obj", snippet_shadowed_object_or_array("Object")),
        ("shadow-arr", snippet_shadowed_object_or_array("Array")),
        ("reassign", snippet_reassigned_accumulator_alias()),
    )
    for label, source in arms:
        _, silent = lint_source(ws, specifier, source, prefix=label)
        print(f"reducer silence {label}", flush=True)
        assert_silent_f02(silent, RULE_RED)


def test_unreassigned_let_and_var_accumulator_aliases_are_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(
        ws, specifier, snippet_object_assign_copy(const_alias=True)
    )
    assert_only_rule(baseline, RULE_RED)
    _, let_arm = lint_source(
        ws, specifier, snippet_object_assign_copy(let_alias=True), prefix="let-acc"
    )
    assert_silent_f02(let_arm, RULE_RED)
    _, var_arm = lint_source(
        ws, specifier, snippet_object_assign_copy(var_alias=True), prefix="var-acc"
    )
    assert_silent_f02(var_arm, RULE_RED)


def test_reducer_spreads_are_silent_for_this_rule(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_object_assign_copy(two_arg=True))
    assert_only_rule(baseline, RULE_RED)
    _, arr = lint_source(ws, specifier, snippet_reducer_array_spread(), prefix="sp-a")
    assert_silent_f02(arr, RULE_RED)
    _, obj = lint_source(ws, specifier, snippet_reducer_object_spread(), prefix="sp-o")
    assert_silent_f02(obj, RULE_RED)


def test_object_assign_copy_inside_map_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(ws, specifier, snippet_object_assign_copy(two_arg=True))
    assert_only_rule(baseline, RULE_RED)
    _, silent = lint_source(ws, specifier, snippet_assign_inside_map())
    assert_silent_f02(silent, RULE_RED)


# ---------------------------------------------------------------------------
# H. Conditional empty-object spread
# ---------------------------------------------------------------------------


def test_spread_of_conditional_empty_false_branch_reports(copied_plugin):
    ws, specifier = copied_plugin
    public = snippet_no_conditional_empty_object_spread()
    twin = snippet_no_conditional_empty_object_spread(twin=True)
    oracle = snippet_l134_empty_false_spread(twin=False)
    generated = snippet_l134_empty_false_spread(twin=True)
    for source, label, ext in (
        (public, "public", "js"),
        (twin, "twin", "js"),
        (oracle, "l134", "js"),
        (generated, "l134-twin", "ts"),
    ):
        _, result = lint_source(
            ws, specifier, source, ext=ext, prefix=f"spr-{label}"
        )
        print(f"empty-false spread {label} ext={ext}", flush=True)
        assert_only_rule(result, RULE_SPR)


def test_spread_of_conditional_empty_true_branch_reports(copied_plugin):
    ws, specifier = copied_plugin
    js_src = snippet_empty_true_branch_spread(twin=True)
    ts_src = snippet_empty_true_branch_spread(twin=True)
    _, js_result = lint_source(ws, specifier, js_src, ext="js", prefix="true-js")
    assert_only_rule(js_result, RULE_SPR)
    _, ts_result = lint_source(ws, specifier, ts_src, ext="ts", prefix="true-ts")
    assert_only_rule(ts_result, RULE_SPR)


def test_non_spread_conditional_and_non_conditional_spread_are_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(
        ws, specifier, snippet_no_conditional_empty_object_spread(twin=True)
    )
    assert_only_rule(baseline, RULE_SPR)
    _, non_spread = lint_source(ws, specifier, snippet_non_spread_conditional())
    assert_silent_f02(non_spread, RULE_SPR)
    _, non_cond = lint_source(ws, specifier, snippet_non_conditional_spread())
    assert_silent_f02(non_cond, RULE_SPR)
    _, plain = lint_source(ws, specifier, snippet_object_without_spread_pattern())
    assert_silent_f02(plain, RULE_SPR)


def test_both_branches_non_empty_conditional_spread_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, baseline = lint_source(
        ws, specifier, snippet_no_conditional_empty_object_spread(twin=True)
    )
    assert_only_rule(baseline, RULE_SPR)
    _, silent = lint_source(ws, specifier, snippet_both_branches_non_empty_spread())
    assert_silent_f02(silent, RULE_SPR)


def test_array_spread_of_empty_branch_conditional_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    value = fresh_ident("value")
    _, baseline = lint_source(
        ws,
        specifier,
        snippet_l134_empty_false_spread(twin=True, value=value),
        prefix="arr-base",
    )
    assert_only_rule(baseline, RULE_SPR)
    _, silent = lint_source(
        ws,
        specifier,
        snippet_array_parent_empty_branch_spread(value=value),
        prefix="arr-parent",
    )
    assert_silent_f02(silent, RULE_SPR)


# ---------------------------------------------------------------------------
# I. Host fix mode does not rewrite and still reports
# ---------------------------------------------------------------------------


def test_fix_mode_leaves_filter_map_chain_in_place_and_still_reports(copied_plugin):
    ws, specifier = copied_plugin
    source = snippet_no_array_filter_map()
    _, baseline = lint_source(ws, specifier, source, prefix="fix-fm-base")
    assert_only_rule(baseline, RULE_FM)
    run_fix_and_assert(ws, specifier, source, RULE_FM, prefix="fix-fm")


def test_fix_mode_leaves_reducer_copy_in_place_and_still_reports(copied_plugin):
    ws, specifier = copied_plugin
    run_fix_and_assert(
        ws,
        specifier,
        snippet_no_reduce_accumulator_copy(),
        RULE_RED,
        prefix="fix-red",
    )


def test_fix_mode_leaves_conditional_empty_spread_in_place_and_still_reports(
    copied_plugin,
):
    ws, specifier = copied_plugin
    run_fix_and_assert(
        ws,
        specifier,
        snippet_no_conditional_empty_object_spread(),
        RULE_SPR,
        prefix="fix-spr",
    )


def test_fix_mode_leaves_map_then_filter_in_place_and_still_reports(copied_plugin):
    ws, specifier = copied_plugin
    run_fix_and_assert(
        ws,
        specifier,
        snippet_map_then_filter_literal(),
        RULE_FM,
        prefix="fix-mf",
    )


def test_fix_mode_leaves_array_copy_reducer_in_place_and_still_reports(copied_plugin):
    ws, specifier = copied_plugin
    run_fix_and_assert(
        ws,
        specifier,
        snippet_array_from_accumulator(init="{}"),
        RULE_RED,
        prefix="fix-from",
    )


def test_fix_mode_leaves_empty_true_branch_spread_in_place_and_still_reports(
    copied_plugin,
):
    ws, specifier = copied_plugin
    run_fix_and_assert(
        ws,
        specifier,
        snippet_empty_true_branch_spread(twin=True),
        RULE_SPR,
        prefix="fix-true",
    )


# ---------------------------------------------------------------------------
# J. Attribution among the three rules
# ---------------------------------------------------------------------------


def test_each_unique_violator_attributes_only_its_rule(copied_plugin):
    ws, specifier = copied_plugin
    files = (
        (snippet_no_array_filter_map(twin=True), RULE_FM, "attr-fm"),
        (snippet_no_reduce_accumulator_copy(twin=True), RULE_RED, "attr-red"),
        (snippet_no_conditional_empty_object_spread(twin=True), RULE_SPR, "attr-spr"),
    )
    for source, rule_name, prefix in files:
        _, result = lint_source(ws, specifier, source, prefix=prefix)
        print(f"attribution {rule_name}", flush=True)
        assert_only_rule(result, rule_name)
        assert_fired(result, rule_name)
