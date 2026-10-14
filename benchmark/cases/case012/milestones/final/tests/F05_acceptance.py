# feature: F05
"""Acceptance tests: reject runtime typeof, Reflect apply/get, and module mocking."""

from __future__ import annotations

import pytest

from _harness import DEFAULT_COPY_DEST, workspace
from F01_helpers import (
    assert_only_rule,
    fresh_ident,
    require_copied_layout,
    snippet_no_module_mocking,
    snippet_no_reflect_apply,
    snippet_no_reflect_get,
    snippet_no_runtime_typeof,
)
from F02_helpers import assert_fix_preserves_source
from F03_helpers import assert_classified_not_fired
from F05_helpers import (
    RULE_APPLY,
    RULE_GET,
    RULE_MOCK,
    RULE_TYPEOF,
    assert_nested_typeof_reported_direct_silent,
    assert_silent_f05,
    assert_typeof_finding_in_span,
    lint_f05,
    lint_f05_source,
    snippet_aliased_import_jest_from_jest_globals_mock,
    snippet_aliased_import_vi_from_vitest_mock,
    snippet_arrow_predicate_typeof,
    snippet_assertion_function_typeof,
    snippet_assertion_function_typeof_strict_inequality,
    snippet_both_existence_probes,
    snippet_computed_do_mock,
    snippet_computed_reflect_apply,
    snippet_computed_reflect_get,
    snippet_direct_and_nested_typeof_in_predicate,
    snippet_identifier_do_mock,
    snippet_in_memory_collaborator,
    snippet_jest_mock,
    snippet_jest_spy_on,
    snippet_jest_unstable_mock_module,
    snippet_local_object_named_vi_mock,
    snippet_named_import_jest_from_jest_globals_mock,
    snippet_named_import_vi_from_vitest_mock,
    snippet_nested_inner_typeof_in_predicate,
    snippet_non_predicate_parse_typeof,
    snippet_non_value_is_string_predicate,
    snippet_operation_apply,
    snippet_ordinary_property_access,
    snippet_parameter_named_jest_mock,
    snippet_parameter_named_reflect_apply,
    snippet_parameter_named_reflect_get,
    snippet_reflect_set,
    snippet_shadowed_reflect_apply,
    snippet_shadowed_reflect_get,
    snippet_type_predicate_typeof,
    snippet_typeof_compared_to_value_undefined,
    snippet_typeof_identifier_undefined,
    snippet_typeof_input_string,
    snippet_typeof_member_undefined,
    snippet_typeof_other_representation,
    snippet_typeof_other_representation_loose,
    snippet_typeof_other_representation_loose_inequality,
    snippet_typeof_other_representation_strict_inequality,
    snippet_typeof_string_if,
    snippet_typeof_string_reversed,
    snippet_typeof_undefined_loose,
    snippet_typeof_undefined_loose_inequality,
    snippet_typeof_undefined_reversed,
    snippet_typeof_undefined_strict_inequality,
    snippet_vi_spy_on,
    write_f05_source,
    write_project_module_helper_mock,
)


@pytest.fixture(scope="module")
def copied_plugin():
    with workspace() as ws:
        result = ws.copy()
        specifier = require_copied_layout(result, DEFAULT_COPY_DEST, cwd=ws.path)
        print(f"F05 copied specifier={specifier}", flush=True)
        yield ws, specifier


def _lint(
    copied_plugin,
    source,
    *,
    prefix="f05",
    ext="ts",
    allow_in_type_guards=None,
    fix=False,
):
    ws, specifier = copied_plugin
    return lint_f05_source(
        ws,
        specifier,
        source,
        prefix=prefix,
        ext=ext,
        allow_in_type_guards=allow_in_type_guards,
        fix=fix,
    )


def _lint_public_and_twin(copied_plugin, builder, *, prefix, rule_name, ext="ts"):
    public = builder()
    twin = builder(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path, result = _lint(
            copied_plugin, source, prefix=f"{prefix}-{label}", ext=ext
        )
        print(f"{prefix} {label} path={path.name}", flush=True)
        assert_only_rule(result, rule_name)


# ---------------------------------------------------------------------------
# A. Representation typeof reports
# ---------------------------------------------------------------------------


def test_typeof_string_representation_check_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_no_runtime_typeof,
        prefix="typeof-fn",
        rule_name=RULE_TYPEOF,
    )
    _lint_public_and_twin(
        copied_plugin,
        snippet_typeof_string_if,
        prefix="typeof-if",
        rule_name=RULE_TYPEOF,
    )


def test_typeof_other_representation_string_reports(copied_plugin):
    _, baseline = _lint(
        copied_plugin, snippet_typeof_input_string(twin=True), prefix="typeof-str-live"
    )
    assert_only_rule(baseline, RULE_TYPEOF)
    _lint_public_and_twin(
        copied_plugin,
        snippet_typeof_other_representation,
        prefix="typeof-num",
        rule_name=RULE_TYPEOF,
    )


def test_typeof_compared_to_value_undefined_reports(copied_plugin):
    ident_src = snippet_typeof_identifier_undefined()
    _, silent = _lint(copied_plugin, ident_src, prefix="typeof-undef-str")
    assert_silent_f05(silent, RULE_TYPEOF)
    _lint_public_and_twin(
        copied_plugin,
        snippet_typeof_compared_to_value_undefined,
        prefix="typeof-undef-val",
        rule_name=RULE_TYPEOF,
    )


def test_typeof_string_representation_reversed_operands_reports(copied_plugin):
    _, silent = _lint(
        copied_plugin, snippet_typeof_undefined_reversed(), prefix="typeof-rev-undef"
    )
    assert_silent_f05(silent, RULE_TYPEOF)
    _, left = _lint(
        copied_plugin, snippet_typeof_input_string(twin=True), prefix="typeof-left-live"
    )
    assert_only_rule(left, RULE_TYPEOF)
    _lint_public_and_twin(
        copied_plugin,
        snippet_typeof_string_reversed,
        prefix="typeof-rev-str",
        rule_name=RULE_TYPEOF,
    )


# ---------------------------------------------------------------------------
# B. Existence probes are silent
# ---------------------------------------------------------------------------


def test_typeof_identifier_equals_string_undefined_is_silent(copied_plugin):
    ident = "input"
    fire_src = f'typeof {ident} === "string";\n'
    silent_src = f'typeof {ident} === "undefined";\n'
    _, fire = _lint(copied_plugin, fire_src, prefix="exist-id-fire")
    assert_only_rule(fire, RULE_TYPEOF)
    _, silent = _lint(copied_plugin, silent_src, prefix="exist-id-silent")
    assert_silent_f05(silent, RULE_TYPEOF)
    _, oracle = _lint(
        copied_plugin, snippet_typeof_identifier_undefined(), prefix="exist-id-oracle"
    )
    assert_silent_f05(oracle, RULE_TYPEOF)
    _, twin = _lint(
        copied_plugin,
        snippet_typeof_identifier_undefined(twin=True),
        prefix="exist-id-twin",
    )
    assert_silent_f05(twin, RULE_TYPEOF)


def test_typeof_member_equals_string_undefined_is_silent(copied_plugin):
    _, ident = _lint(
        copied_plugin, snippet_typeof_identifier_undefined(), prefix="exist-mem-ident"
    )
    assert_silent_f05(ident, RULE_TYPEOF)
    _, fire = _lint(
        copied_plugin, snippet_typeof_input_string(), prefix="exist-mem-fire"
    )
    assert_only_rule(fire, RULE_TYPEOF)
    _, silent = _lint(
        copied_plugin, snippet_typeof_member_undefined(), prefix="exist-mem-oracle"
    )
    assert_silent_f05(silent, RULE_TYPEOF)
    _, twin = _lint(
        copied_plugin, snippet_typeof_member_undefined(twin=True), prefix="exist-mem-twin"
    )
    assert_silent_f05(twin, RULE_TYPEOF)


def test_typeof_string_undefined_reversed_operands_is_silent(copied_plugin):
    ident = "document"
    fire_src = f'"string" === typeof {ident};\n'
    silent_src = f'"undefined" === typeof {ident};\n'
    _, fire = _lint(copied_plugin, fire_src, prefix="exist-rev-fire")
    assert_only_rule(fire, RULE_TYPEOF)
    _, silent = _lint(copied_plugin, silent_src, prefix="exist-rev-silent")
    assert_silent_f05(silent, RULE_TYPEOF)
    _, twin = _lint(
        copied_plugin,
        snippet_typeof_undefined_reversed(twin=True),
        prefix="exist-rev-twin",
    )
    assert_silent_f05(twin, RULE_TYPEOF)


def test_typeof_string_undefined_loose_equality_is_silent(copied_plugin):
    _, fire = _lint(
        copied_plugin,
        snippet_typeof_other_representation_loose(),
        prefix="exist-loose-fire",
    )
    assert_only_rule(fire, RULE_TYPEOF)
    _, silent = _lint(
        copied_plugin, snippet_typeof_undefined_loose(), prefix="exist-loose-oracle"
    )
    assert_silent_f05(silent, RULE_TYPEOF)
    twin_name = fresh_ident("binding")
    print(f"exist-loose twin_name={twin_name}", flush=True)
    _, twin_fire = _lint(
        copied_plugin,
        snippet_typeof_other_representation_loose(name=twin_name),
        prefix="exist-loose-fire-twin",
    )
    assert_only_rule(twin_fire, RULE_TYPEOF)
    _, twin = _lint(
        copied_plugin,
        snippet_typeof_undefined_loose(name=twin_name),
        prefix="exist-loose-twin",
    )
    assert_silent_f05(twin, RULE_TYPEOF)


def test_typeof_string_undefined_strict_inequality_is_silent(copied_plugin):
    _, fire = _lint(
        copied_plugin,
        snippet_typeof_other_representation_strict_inequality(),
        prefix="exist-ne-fire",
    )
    assert_only_rule(fire, RULE_TYPEOF)
    _, silent = _lint(
        copied_plugin,
        snippet_typeof_undefined_strict_inequality(),
        prefix="exist-ne-oracle",
    )
    assert_silent_f05(silent, RULE_TYPEOF)
    twin_name = fresh_ident("binding")
    print(f"exist-ne twin_name={twin_name}", flush=True)
    _, twin_fire = _lint(
        copied_plugin,
        snippet_typeof_other_representation_strict_inequality(name=twin_name),
        prefix="exist-ne-fire-twin",
    )
    assert_only_rule(twin_fire, RULE_TYPEOF)
    _, twin = _lint(
        copied_plugin,
        snippet_typeof_undefined_strict_inequality(name=twin_name),
        prefix="exist-ne-twin",
    )
    assert_silent_f05(twin, RULE_TYPEOF)


def test_typeof_string_undefined_loose_inequality_is_silent(copied_plugin):
    _, fire = _lint(
        copied_plugin,
        snippet_typeof_other_representation_loose_inequality(),
        prefix="exist-nloose-fire",
    )
    assert_only_rule(fire, RULE_TYPEOF)
    _, silent = _lint(
        copied_plugin,
        snippet_typeof_undefined_loose_inequality(),
        prefix="exist-nloose-oracle",
    )
    assert_silent_f05(silent, RULE_TYPEOF)
    twin_name = fresh_ident("binding")
    print(f"exist-nloose twin_name={twin_name}", flush=True)
    _, twin_fire = _lint(
        copied_plugin,
        snippet_typeof_other_representation_loose_inequality(name=twin_name),
        prefix="exist-nloose-fire-twin",
    )
    assert_only_rule(twin_fire, RULE_TYPEOF)
    _, twin = _lint(
        copied_plugin,
        snippet_typeof_undefined_loose_inequality(name=twin_name),
        prefix="exist-nloose-twin",
    )
    assert_silent_f05(twin, RULE_TYPEOF)


# ---------------------------------------------------------------------------
# C. allowInTypeGuards omit equals false
# ---------------------------------------------------------------------------


def test_omitted_allow_in_type_guards_matches_explicit_false(copied_plugin):
    arms = (
        (snippet_type_predicate_typeof(), "pred", True),
        (snippet_non_predicate_parse_typeof(), "parse", True),
        (snippet_typeof_input_string(), "repr", True),
        (snippet_both_existence_probes(), "exist", False),
    )
    for source, label, expect_fire in arms:
        _, omitted = _lint(
            copied_plugin, source, prefix=f"omit-{label}", allow_in_type_guards=None
        )
        _, explicit = _lint(
            copied_plugin, source, prefix=f"false-{label}", allow_in_type_guards=False
        )
        print(
            f"omit-vs-false {label} expect_fire={expect_fire} "
            f"omit_exit={omitted.returncode} false_exit={explicit.returncode}",
            flush=True,
        )
        if expect_fire:
            assert_only_rule(omitted, RULE_TYPEOF)
            assert_only_rule(explicit, RULE_TYPEOF)
        else:
            assert_silent_f05(omitted, RULE_TYPEOF)
            assert_silent_f05(explicit, RULE_TYPEOF)


def test_type_predicate_reports_when_option_omitted(copied_plugin):
    _, result = _lint(
        copied_plugin,
        snippet_type_predicate_typeof(),
        prefix="pred-omit",
        allow_in_type_guards=None,
    )
    assert_only_rule(result, RULE_TYPEOF)
    _, twin = _lint(
        copied_plugin,
        snippet_type_predicate_typeof(twin=True),
        prefix="pred-omit-twin",
    )
    assert_only_rule(twin, RULE_TYPEOF)


def test_assertion_function_reports_when_option_omitted(copied_plugin):
    _, result = _lint(
        copied_plugin,
        snippet_assertion_function_typeof(),
        prefix="assert-omit",
        allow_in_type_guards=None,
    )
    assert_only_rule(result, RULE_TYPEOF)
    _, explicit = _lint(
        copied_plugin,
        snippet_assertion_function_typeof(twin=True),
        prefix="assert-false",
        allow_in_type_guards=False,
    )
    assert_only_rule(explicit, RULE_TYPEOF)


# ---------------------------------------------------------------------------
# D. allowInTypeGuards true: direct silent; nested and ordinary still report
# ---------------------------------------------------------------------------


def test_allow_in_type_guards_true_direct_predicate_is_silent(copied_plugin):
    source = snippet_type_predicate_typeof()
    _, omitted = _lint(
        copied_plugin, source, prefix="pred-true-live", allow_in_type_guards=None
    )
    assert_only_rule(omitted, RULE_TYPEOF)
    _, allowed = _lint(
        copied_plugin, source, prefix="pred-true", allow_in_type_guards=True
    )
    assert_silent_f05(allowed, RULE_TYPEOF)


def test_allow_in_type_guards_true_direct_assertion_is_silent(copied_plugin):
    source = snippet_assertion_function_typeof()
    _, omitted = _lint(
        copied_plugin, source, prefix="assert-true-live", allow_in_type_guards=None
    )
    assert_only_rule(omitted, RULE_TYPEOF)
    _, allowed = _lint(
        copied_plugin, source, prefix="assert-true", allow_in_type_guards=True
    )
    assert_silent_f05(allowed, RULE_TYPEOF)


def test_allow_in_type_guards_true_arrow_predicate_is_silent(copied_plugin):
    source = snippet_arrow_predicate_typeof()
    _, omitted = _lint(
        copied_plugin, source, prefix="arrow-true-live", allow_in_type_guards=None
    )
    assert_only_rule(omitted, RULE_TYPEOF)
    _, allowed = _lint(
        copied_plugin, source, prefix="arrow-true", allow_in_type_guards=True
    )
    assert_silent_f05(allowed, RULE_TYPEOF)
    _, twin = _lint(
        copied_plugin,
        snippet_arrow_predicate_typeof(twin=True),
        prefix="arrow-true-twin",
        allow_in_type_guards=True,
    )
    assert_silent_f05(twin, RULE_TYPEOF)


def test_allow_in_type_guards_true_non_value_is_string_predicate_is_silent(
    copied_plugin,
):
    oracle = snippet_type_predicate_typeof()
    _, oracle_allowed = _lint(
        copied_plugin, oracle, prefix="nonval-oracle", allow_in_type_guards=True
    )
    assert_silent_f05(oracle_allowed, RULE_TYPEOF)
    source = snippet_non_value_is_string_predicate()
    _, omitted = _lint(
        copied_plugin, source, prefix="nonval-live", allow_in_type_guards=None
    )
    assert_only_rule(omitted, RULE_TYPEOF)
    _, allowed = _lint(
        copied_plugin, source, prefix="nonval-true", allow_in_type_guards=True
    )
    assert_silent_f05(allowed, RULE_TYPEOF)
    _, twin = _lint(
        copied_plugin,
        snippet_non_value_is_string_predicate(twin=True),
        prefix="nonval-twin",
        allow_in_type_guards=True,
    )
    assert_silent_f05(twin, RULE_TYPEOF)


def test_allow_in_type_guards_true_ordinary_parse_still_reports(copied_plugin):
    pred = snippet_type_predicate_typeof()
    _, pred_allowed = _lint(
        copied_plugin, pred, prefix="parse-pred", allow_in_type_guards=True
    )
    assert_silent_f05(pred_allowed, RULE_TYPEOF)
    _, parse = _lint(
        copied_plugin,
        snippet_non_predicate_parse_typeof(),
        prefix="parse-true",
        allow_in_type_guards=True,
    )
    assert_only_rule(parse, RULE_TYPEOF)
    _, repr_check = _lint(
        copied_plugin,
        snippet_typeof_input_string(),
        prefix="parse-repr",
        allow_in_type_guards=True,
    )
    assert_only_rule(repr_check, RULE_TYPEOF)
    _, exist = _lint(
        copied_plugin,
        snippet_both_existence_probes(),
        prefix="parse-exist",
        allow_in_type_guards=True,
    )
    assert_silent_f05(exist, RULE_TYPEOF)


def test_allow_in_type_guards_true_nested_inner_typeof_reports(copied_plugin):
    _, direct = _lint(
        copied_plugin,
        snippet_type_predicate_typeof(),
        prefix="nested-direct",
        allow_in_type_guards=True,
    )
    assert_silent_f05(direct, RULE_TYPEOF)
    nested = snippet_nested_inner_typeof_in_predicate()
    _, result = _lint(
        copied_plugin, nested.source, prefix="nested-inner", allow_in_type_guards=True
    )
    print(f"nested-inner span={nested.nested_span}", flush=True)
    assert_only_rule(result, RULE_TYPEOF)
    assert_typeof_finding_in_span(nested.source, result, nested.nested_span)


def test_allow_in_type_guards_true_direct_silent_nested_reports(copied_plugin):
    combined = snippet_direct_and_nested_typeof_in_predicate()
    if combined.direct_span is None:
        raise AssertionError("combined snippet must expose a direct typeof span")
    _, result = _lint(
        copied_plugin,
        combined.source,
        prefix="combined",
        allow_in_type_guards=True,
    )
    print(
        f"combined direct={combined.direct_span} nested={combined.nested_span}",
        flush=True,
    )
    assert_nested_typeof_reported_direct_silent(
        combined.source,
        result,
        direct_span=combined.direct_span,
        nested_span=combined.nested_span,
    )


def test_allow_in_type_guards_true_direct_assertion_strict_inequality_is_silent(
    copied_plugin,
):
    source = snippet_assertion_function_typeof_strict_inequality()
    _, omitted = _lint(
        copied_plugin, source, prefix="assert-ne-live", allow_in_type_guards=None
    )
    assert_only_rule(omitted, RULE_TYPEOF)
    _, allowed = _lint(
        copied_plugin, source, prefix="assert-ne-true", allow_in_type_guards=True
    )
    assert_silent_f05(allowed, RULE_TYPEOF)
    _, twin = _lint(
        copied_plugin,
        snippet_assertion_function_typeof_strict_inequality(twin=True),
        prefix="assert-ne-twin",
        allow_in_type_guards=True,
    )
    assert_silent_f05(twin, RULE_TYPEOF)


# ---------------------------------------------------------------------------
# E. Global Reflect.apply reports; shadows and operation.apply are silent
# ---------------------------------------------------------------------------


def test_global_reflect_apply_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_no_reflect_apply,
        prefix="apply-id",
        rule_name=RULE_APPLY,
    )


def test_computed_reflect_apply_reports(copied_plugin):
    _, ident = _lint(
        copied_plugin, snippet_no_reflect_apply(twin=True), prefix="apply-comp-live"
    )
    assert_only_rule(ident, RULE_APPLY)
    _lint_public_and_twin(
        copied_plugin,
        snippet_computed_reflect_apply,
        prefix="apply-comp",
        rule_name=RULE_APPLY,
    )


def test_operation_apply_is_silent_for_reflect_apply(copied_plugin):
    _, fire = _lint(
        copied_plugin, snippet_no_reflect_apply(), prefix="op-apply-live"
    )
    assert_only_rule(fire, RULE_APPLY)
    _, silent = _lint(
        copied_plugin, snippet_operation_apply(), prefix="op-apply-silent"
    )
    assert_silent_f05(silent, RULE_APPLY)
    _, twin = _lint(
        copied_plugin, snippet_operation_apply(twin=True), prefix="op-apply-twin"
    )
    assert_silent_f05(twin, RULE_APPLY)


def test_shadowed_reflect_apply_is_silent(copied_plugin):
    _, fire = _lint(
        copied_plugin, snippet_no_reflect_apply(), prefix="shadow-apply-live"
    )
    assert_only_rule(fire, RULE_APPLY)
    _, silent = _lint(
        copied_plugin, snippet_shadowed_reflect_apply(), prefix="shadow-apply"
    )
    assert_silent_f05(silent, RULE_APPLY)
    _, twin = _lint(
        copied_plugin,
        snippet_shadowed_reflect_apply(twin=True),
        prefix="shadow-apply-twin",
    )
    assert_silent_f05(twin, RULE_APPLY)


def test_parameter_named_reflect_apply_is_silent(copied_plugin):
    _, fire = _lint(
        copied_plugin, snippet_no_reflect_apply(), prefix="param-apply-live"
    )
    assert_only_rule(fire, RULE_APPLY)
    _, silent = _lint(
        copied_plugin, snippet_parameter_named_reflect_apply(), prefix="param-apply"
    )
    assert_silent_f05(silent, RULE_APPLY)
    _, twin = _lint(
        copied_plugin,
        snippet_parameter_named_reflect_apply(twin=True),
        prefix="param-apply-twin",
    )
    assert_silent_f05(twin, RULE_APPLY)


def test_reflect_get_does_not_report_reflect_apply(copied_plugin):
    _, apply_file = _lint(
        copied_plugin, snippet_no_reflect_apply(twin=True), prefix="get-vs-apply-live"
    )
    assert_only_rule(apply_file, RULE_APPLY)
    _, get_file = _lint(
        copied_plugin, snippet_no_reflect_get(), prefix="get-vs-apply"
    )
    assert_classified_not_fired(get_file, RULE_APPLY)
    assert_only_rule(get_file, RULE_GET)


# ---------------------------------------------------------------------------
# F. Global Reflect.get reports; ordinary access, set, shadows are silent
# ---------------------------------------------------------------------------


def test_global_reflect_get_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_no_reflect_get,
        prefix="get-id",
        rule_name=RULE_GET,
    )


def test_computed_reflect_get_reports(copied_plugin):
    _, ident = _lint(
        copied_plugin, snippet_no_reflect_get(twin=True), prefix="get-comp-live"
    )
    assert_only_rule(ident, RULE_GET)
    _lint_public_and_twin(
        copied_plugin,
        snippet_computed_reflect_get,
        prefix="get-comp",
        rule_name=RULE_GET,
    )


def test_ordinary_property_access_is_silent_for_reflect_get(copied_plugin):
    _, fire = _lint(copied_plugin, snippet_no_reflect_get(), prefix="ordinary-live")
    assert_only_rule(fire, RULE_GET)
    _, silent = _lint(
        copied_plugin, snippet_ordinary_property_access(), prefix="ordinary"
    )
    assert_silent_f05(silent, RULE_GET)
    _, twin = _lint(
        copied_plugin,
        snippet_ordinary_property_access(twin=True),
        prefix="ordinary-twin",
    )
    assert_silent_f05(twin, RULE_GET)


def test_reflect_set_is_silent_for_reflect_get(copied_plugin):
    _, fire = _lint(copied_plugin, snippet_no_reflect_get(), prefix="set-live")
    assert_only_rule(fire, RULE_GET)
    _, silent = _lint(copied_plugin, snippet_reflect_set(), prefix="set-silent")
    assert_silent_f05(silent, RULE_GET)
    _, twin = _lint(
        copied_plugin, snippet_reflect_set(twin=True), prefix="set-twin"
    )
    assert_silent_f05(twin, RULE_GET)


def test_shadowed_reflect_get_is_silent(copied_plugin):
    _, fire = _lint(copied_plugin, snippet_no_reflect_get(), prefix="shadow-get-live")
    assert_only_rule(fire, RULE_GET)
    _, silent = _lint(
        copied_plugin, snippet_shadowed_reflect_get(), prefix="shadow-get"
    )
    assert_silent_f05(silent, RULE_GET)
    _, twin = _lint(
        copied_plugin, snippet_shadowed_reflect_get(twin=True), prefix="shadow-get-twin"
    )
    assert_silent_f05(twin, RULE_GET)


def test_parameter_named_reflect_get_is_silent(copied_plugin):
    _, fire = _lint(copied_plugin, snippet_no_reflect_get(), prefix="param-get-live")
    assert_only_rule(fire, RULE_GET)
    _, silent = _lint(
        copied_plugin, snippet_parameter_named_reflect_get(), prefix="param-get"
    )
    assert_silent_f05(silent, RULE_GET)
    _, twin = _lint(
        copied_plugin,
        snippet_parameter_named_reflect_get(twin=True),
        prefix="param-get-twin",
    )
    assert_silent_f05(twin, RULE_GET)


# ---------------------------------------------------------------------------
# G. Module mocking reports on the real testing namespace
# ---------------------------------------------------------------------------


def test_vi_mock_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_no_module_mocking,
        prefix="vi-mock",
        rule_name=RULE_MOCK,
    )


def test_jest_mock_reports(copied_plugin):
    _, vi_file = _lint(
        copied_plugin, snippet_no_module_mocking(twin=True), prefix="jest-mock-live"
    )
    assert_only_rule(vi_file, RULE_MOCK)
    _lint_public_and_twin(
        copied_plugin,
        snippet_jest_mock,
        prefix="jest-mock",
        rule_name=RULE_MOCK,
    )


def test_identifier_do_mock_reports(copied_plugin):
    _, mock_file = _lint(
        copied_plugin, snippet_no_module_mocking(twin=True), prefix="idomock-live"
    )
    assert_only_rule(mock_file, RULE_MOCK)
    _, computed = _lint(
        copied_plugin, snippet_computed_do_mock(twin=True), prefix="idomock-comp"
    )
    assert_only_rule(computed, RULE_MOCK)
    _lint_public_and_twin(
        copied_plugin,
        snippet_identifier_do_mock,
        prefix="idomock",
        rule_name=RULE_MOCK,
    )


def test_computed_do_mock_reports(copied_plugin):
    _, ident = _lint(
        copied_plugin, snippet_identifier_do_mock(twin=True), prefix="cdomock-live"
    )
    assert_only_rule(ident, RULE_MOCK)
    _lint_public_and_twin(
        copied_plugin,
        snippet_computed_do_mock,
        prefix="cdomock",
        rule_name=RULE_MOCK,
    )


def test_jest_unstable_mock_module_reports(copied_plugin):
    _, mock_file = _lint(
        copied_plugin, snippet_jest_mock(twin=True), prefix="unstable-live"
    )
    assert_only_rule(mock_file, RULE_MOCK)
    _lint_public_and_twin(
        copied_plugin,
        snippet_jest_unstable_mock_module,
        prefix="unstable",
        rule_name=RULE_MOCK,
    )


def test_named_import_vi_from_vitest_mock_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_named_import_vi_from_vitest_mock,
        prefix="imp-vi",
        rule_name=RULE_MOCK,
    )


def test_aliased_import_vi_from_vitest_mock_reports(copied_plugin):
    _, named = _lint(
        copied_plugin,
        snippet_named_import_vi_from_vitest_mock(twin=True),
        prefix="alias-vi-live",
    )
    assert_only_rule(named, RULE_MOCK)
    _lint_public_and_twin(
        copied_plugin,
        snippet_aliased_import_vi_from_vitest_mock,
        prefix="alias-vi",
        rule_name=RULE_MOCK,
    )


def test_named_import_jest_from_jest_globals_mock_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_named_import_jest_from_jest_globals_mock,
        prefix="imp-jest",
        rule_name=RULE_MOCK,
    )


def test_aliased_import_jest_from_jest_globals_mock_reports(copied_plugin):
    _, named = _lint(
        copied_plugin,
        snippet_named_import_jest_from_jest_globals_mock(twin=True),
        prefix="alias-jest-live",
    )
    assert_only_rule(named, RULE_MOCK)
    _lint_public_and_twin(
        copied_plugin,
        snippet_aliased_import_jest_from_jest_globals_mock,
        prefix="alias-jest",
        rule_name=RULE_MOCK,
    )


# ---------------------------------------------------------------------------
# H. Module mocking silences
# ---------------------------------------------------------------------------


def test_vi_spy_on_is_silent(copied_plugin):
    _, fire = _lint(
        copied_plugin, snippet_no_module_mocking(), prefix="spy-vi-live"
    )
    assert_only_rule(fire, RULE_MOCK)
    _, silent = _lint(copied_plugin, snippet_vi_spy_on(), prefix="spy-vi")
    assert_silent_f05(silent, RULE_MOCK)
    _, twin = _lint(
        copied_plugin, snippet_vi_spy_on(twin=True), prefix="spy-vi-twin"
    )
    assert_silent_f05(twin, RULE_MOCK)


def test_jest_spy_on_is_silent(copied_plugin):
    _, fire = _lint(copied_plugin, snippet_jest_mock(), prefix="spy-jest-live")
    assert_only_rule(fire, RULE_MOCK)
    _, silent = _lint(copied_plugin, snippet_jest_spy_on(), prefix="spy-jest")
    assert_silent_f05(silent, RULE_MOCK)
    _, twin = _lint(
        copied_plugin, snippet_jest_spy_on(twin=True), prefix="spy-jest-twin"
    )
    assert_silent_f05(twin, RULE_MOCK)


def test_in_memory_collaborator_is_silent(copied_plugin):
    _, fire = _lint(
        copied_plugin, snippet_no_module_mocking(twin=True), prefix="mem-live"
    )
    assert_only_rule(fire, RULE_MOCK)
    _, silent = _lint(
        copied_plugin, snippet_in_memory_collaborator(), prefix="mem"
    )
    assert_silent_f05(silent, RULE_MOCK)
    _, twin = _lint(
        copied_plugin, snippet_in_memory_collaborator(twin=True), prefix="mem-twin"
    )
    assert_silent_f05(twin, RULE_MOCK)


def test_local_object_named_vi_mock_is_silent(copied_plugin):
    _, fire = _lint(
        copied_plugin, snippet_no_module_mocking(), prefix="local-vi-live"
    )
    assert_only_rule(fire, RULE_MOCK)
    _, silent = _lint(
        copied_plugin, snippet_local_object_named_vi_mock(), prefix="local-vi"
    )
    assert_silent_f05(silent, RULE_MOCK)
    _, twin = _lint(
        copied_plugin,
        snippet_local_object_named_vi_mock(twin=True),
        prefix="local-vi-twin",
    )
    assert_silent_f05(twin, RULE_MOCK)


def test_parameter_named_jest_mock_is_silent(copied_plugin):
    _, fire = _lint(copied_plugin, snippet_jest_mock(), prefix="param-jest-live")
    assert_only_rule(fire, RULE_MOCK)
    _, silent = _lint(
        copied_plugin, snippet_parameter_named_jest_mock(), prefix="param-jest"
    )
    assert_silent_f05(silent, RULE_MOCK)
    _, twin = _lint(
        copied_plugin,
        snippet_parameter_named_jest_mock(twin=True),
        prefix="param-jest-twin",
    )
    assert_silent_f05(twin, RULE_MOCK)


def test_project_module_helper_mock_is_silent(copied_plugin):
    ws, specifier = copied_plugin
    _, fire = _lint(
        copied_plugin,
        snippet_aliased_import_vi_from_vitest_mock(),
        prefix="proj-live",
    )
    assert_only_rule(fire, RULE_MOCK)
    path = write_project_module_helper_mock(ws)
    result = lint_f05(ws, [path], specifier)
    print(f"project-helper path={path.name} exit={result.returncode}", flush=True)
    assert_silent_f05(result, RULE_MOCK)
    twin_path = write_project_module_helper_mock(ws, twin=True)
    twin = lint_f05(ws, [twin_path], specifier)
    print(f"project-helper twin={twin_path.name} exit={twin.returncode}", flush=True)
    assert_silent_f05(twin, RULE_MOCK)


# ---------------------------------------------------------------------------
# I. No rewrite under host fix mode
# ---------------------------------------------------------------------------


def test_fix_mode_does_not_rewrite_unique_violators(copied_plugin):
    ws, specifier = copied_plugin
    arms = (
        (snippet_no_runtime_typeof(twin=True), RULE_TYPEOF, "fix-typeof"),
        (snippet_no_reflect_apply(twin=True), RULE_APPLY, "fix-apply"),
        (snippet_no_reflect_get(twin=True), RULE_GET, "fix-get"),
        (snippet_no_module_mocking(twin=True), RULE_MOCK, "fix-mock"),
        (snippet_computed_reflect_apply(twin=True), RULE_APPLY, "fix-apply-comp"),
        (snippet_computed_reflect_get(twin=True), RULE_GET, "fix-get-comp"),
        (snippet_aliased_import_vi_from_vitest_mock(twin=True), RULE_MOCK, "fix-alias"),
    )
    for source, rule_name, prefix in arms:
        print(f"fix-arm {prefix} rule={rule_name}", flush=True)
        path = write_f05_source(ws, source, prefix=prefix)
        before = path.read_bytes()
        result = lint_f05(ws, [path], specifier, fix=True)
        print(f"fix-mode {path.name} rule={rule_name}", flush=True)
        assert_fix_preserves_source(path, before, result, rule_name)
        assert_only_rule(result, rule_name)


# ---------------------------------------------------------------------------
# J. Unique attribution
# ---------------------------------------------------------------------------


def test_each_unique_violator_attributes_only_its_rule(copied_plugin):
    arms = (
        (snippet_no_runtime_typeof(twin=True), RULE_TYPEOF),
        (snippet_no_reflect_apply(twin=True), RULE_APPLY),
        (snippet_no_reflect_get(twin=True), RULE_GET),
        (snippet_no_module_mocking(twin=True), RULE_MOCK),
    )
    for source, rule_name in arms:
        _, result = _lint(copied_plugin, source, prefix=f"unique-{rule_name}")
        print(f"unique {rule_name}", flush=True)
        assert_only_rule(result, rule_name)


# ---------------------------------------------------------------------------
# K. JavaScript as well as TypeScript
# ---------------------------------------------------------------------------


def test_javascript_runtime_constructs_match_typescript(copied_plugin):
    js_fires = (
        (snippet_typeof_string_if(twin=True), RULE_TYPEOF, "js-typeof"),
        (snippet_no_reflect_apply(twin=True), RULE_APPLY, "js-apply"),
        (snippet_no_reflect_get(twin=True), RULE_GET, "js-get"),
        (snippet_no_module_mocking(twin=True), RULE_MOCK, "js-mock"),
    )
    for source, rule_name, prefix in js_fires:
        path, result = _lint(
            copied_plugin, source, prefix=prefix, ext="js"
        )
        print(f"{prefix} path={path.name} rule={rule_name}", flush=True)
        assert_only_rule(result, rule_name)

    ident = "document"
    fire_src = f'typeof {ident} === "string";\n'
    silent_src = f'typeof {ident} === "undefined";\n'
    _, js_fire = _lint(
        copied_plugin, fire_src, prefix="js-exist-fire", ext="js"
    )
    assert_only_rule(js_fire, RULE_TYPEOF)
    _, js_silent = _lint(
        copied_plugin, silent_src, prefix="js-exist-silent", ext="js"
    )
    assert_silent_f05(js_silent, RULE_TYPEOF)
    _, member = _lint(
        copied_plugin,
        snippet_typeof_member_undefined(),
        prefix="js-exist-member",
        ext="js",
    )
    assert_silent_f05(member, RULE_TYPEOF)
