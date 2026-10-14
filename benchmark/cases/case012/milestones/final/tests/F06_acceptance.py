# feature: F06
"""Acceptance tests: ban shape in locally owned names; require readable spacing."""

from __future__ import annotations

import pytest

from _harness import DEFAULT_COPY_DEST, workspace
from F01_helpers import assert_fired, assert_only_rule, require_copied_layout
from F06_helpers import (
    RULE_SHAPE,
    RULE_SPACING,
    SpacingSnippet,
    assert_blank_between,
    assert_docs_attached_after_fix,
    assert_no_blank_between,
    assert_second_pass_stable,
    assert_shape_finding_on_owned_not_neighbor,
    assert_silent_f06,
    assert_spacing_insert,
    assert_spacing_preserve,
    assert_whitespace_only_change,
    lint_f06,
    lint_f06_source,
    read_source_bytes,
    read_source_text,
    run_shape_fix,
    snippet_adjacent_imports_grouped,
    snippet_adjacent_switch_case_clauses,
    snippet_adjacent_top_level_functions,
    snippet_adjacent_type_declarations,
    snippet_assignment_to_local_shape,
    snippet_assignment_to_schema_shape,
    snippet_blank_after_if_block,
    snippet_blank_after_try_block,
    snippet_blank_before_do,
    snippet_blank_before_for,
    snippet_blank_before_if,
    snippet_blank_before_return_in_nested_block,
    snippet_blank_before_switch,
    snippet_blank_before_try,
    snippet_blank_before_while,
    snippet_class_field_named_shape,
    snippet_class_shape,
    snippet_compact_two_statement_body,
    snippet_const_shape_binding,
    snippet_declared_external_outer_inner_shape,
    snippet_declared_external_schema_shape_id,
    snippet_docs_export_const_then_export_const,
    snippet_export_const_then_documented_export_type,
    snippet_extra_blank_lines_between_consts,
    snippet_extra_blanks_between_imports,
    snippet_function_shape_of,
    snippet_import_then_const,
    snippet_import_then_function,
    snippet_interface_then_class,
    snippet_interface_user_shape,
    snippet_jsx_name_shape,
    snippet_local_binding_member_containing_shape,
    snippet_local_binding_member_shape,
    snippet_local_binding_shape_as_computed_key,
    snippet_long_initializer_two_consts,
    snippet_multiline_binding,
    snippet_neighbor_allowed_then_shape,
    snippet_neighbor_shape_then_allowed,
    snippet_nested_class_around_neighbors,
    snippet_nested_function_around_neighbors,
    snippet_nested_interface_around_neighbors,
    snippet_nested_type_around_neighbors,
    snippet_object_property_named_shape,
    snippet_ordinary_property_owner_id,
    snippet_overload_signatures,
    snippet_private_name_shape,
    snippet_short_inner_consts_then_return,
    snippet_single_statement_compact_body,
    snippet_two_top_level_consts,
    snippet_type_payload_shape,
    snippet_type_property_named_shape,
    snippet_uppercase_shape_binding,
    snippet_unsorted_imports_then_const,
    write_f06_source,
)


@pytest.fixture(scope="module")
def copied_plugin():
    with workspace() as ws:
        result = ws.copy()
        specifier = require_copied_layout(result, DEFAULT_COPY_DEST, cwd=ws.path)
        print(f"F06 copied specifier={specifier}", flush=True)
        yield ws, specifier


def _lint(
    copied_plugin,
    source,
    *,
    prefix="f06",
    ext="ts",
    fix=False,
    rules=None,
):
    ws, specifier = copied_plugin
    kwargs = {"prefix": prefix, "ext": ext, "fix": fix}
    if rules is not None:
        kwargs["rules"] = rules
    return lint_f06_source(ws, specifier, source, **kwargs)


def _lint_public_and_twin(
    copied_plugin, builder, *, prefix, rule_name, ext="ts"
):
    public = builder()
    twin = builder(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path, result = _lint(
            copied_plugin, source, prefix=f"{prefix}-{label}", ext=ext
        )
        print(f"{prefix} {label} path={path.name}", flush=True)
        assert_only_rule(result, rule_name)


def _insert(
    copied_plugin,
    snippet: SpacingSnippet,
    *,
    prefix,
    ext="ts",
    exactly_one=False,
    extra_sites=(),
):
    ws, specifier = copied_plugin
    return assert_spacing_insert(
        ws,
        specifier,
        snippet,
        prefix=prefix,
        ext=ext,
        exactly_one=exactly_one,
        extra_sites=extra_sites,
    )


def _preserve(copied_plugin, source, *, prefix, ext="ts"):
    ws, specifier = copied_plugin
    return assert_spacing_preserve(
        ws, specifier, source, prefix=prefix, ext=ext
    )


def _live_shape_fire(copied_plugin, *, prefix):
    _, result = _lint(
        copied_plugin, snippet_const_shape_binding(), prefix=prefix
    )
    assert_only_rule(result, RULE_SHAPE)
    return result


def _insert_docs(copied_plugin, docs, *, prefix):
    ws, specifier = copied_plugin
    snippet = SpacingSnippet(docs.source, docs.previous, docs.docs)
    path, after = assert_spacing_insert(
        ws, specifier, snippet, prefix=prefix
    )
    assert_docs_attached_after_fix(docs, after)
    print(f"docs-attached {path.name}", flush=True)
    return path, after


# ---------------------------------------------------------------------------
# A. Locally owned shape substring reports
# ---------------------------------------------------------------------------


def test_const_shape_binding_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_const_shape_binding,
        prefix="const-shape",
        rule_name=RULE_SHAPE,
    )


def test_uppercase_SHAPE_binding_reports(copied_plugin):
    _live_shape_fire(copied_plugin, prefix="upper-live")
    _lint_public_and_twin(
        copied_plugin,
        snippet_uppercase_shape_binding,
        prefix="upper-shape",
        rule_name=RULE_SHAPE,
    )


def test_function_shapeOf_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_function_shape_of,
        prefix="fn-shape",
        rule_name=RULE_SHAPE,
    )


def test_class_Shape_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_class_shape,
        prefix="class-shape",
        rule_name=RULE_SHAPE,
    )


def test_interface_UserShape_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_interface_user_shape,
        prefix="iface-shape",
        rule_name=RULE_SHAPE,
    )


def test_type_PayloadShape_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_type_payload_shape,
        prefix="alias-shape",
        rule_name=RULE_SHAPE,
    )


def test_type_property_named_shape_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_type_property_named_shape,
        prefix="type-prop-shape",
        rule_name=RULE_SHAPE,
    )


def test_object_property_named_shape_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_object_property_named_shape,
        prefix="obj-prop-shape",
        rule_name=RULE_SHAPE,
    )


def test_class_field_named_shape_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_class_field_named_shape,
        prefix="class-field-shape",
        rule_name=RULE_SHAPE,
    )


def test_private_name_shape_reports(copied_plugin):
    _lint_public_and_twin(
        copied_plugin,
        snippet_private_name_shape,
        prefix="private-shape",
        rule_name=RULE_SHAPE,
    )


def test_jsx_name_Shape_reports(copied_plugin):
    public = snippet_jsx_name_shape()
    twin = snippet_jsx_name_shape(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path, result = _lint(
            copied_plugin, source, prefix=f"jsx-shape-{label}", ext="tsx"
        )
        print(f"jsx-shape {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_SHAPE)


def test_local_binding_shape_as_computed_key_reports(copied_plugin):
    public = snippet_local_binding_shape_as_computed_key()
    twin = snippet_local_binding_shape_as_computed_key(twin=True)
    for source, label in ((public, "public"), (twin, "twin")):
        path, result = _lint(
            copied_plugin, source, prefix=f"computed-key-{label}"
        )
        print(f"computed-key {label} path={path.name}", flush=True)
        assert_only_rule(result, RULE_SHAPE)


# ---------------------------------------------------------------------------
# B. Static members and ordinary properties are silent
# ---------------------------------------------------------------------------


def test_declared_external_schema_shape_id_is_silent(copied_plugin):
    _live_shape_fire(copied_plugin, prefix="ext-schema-live")
    _, silent = _lint(
        copied_plugin,
        snippet_declared_external_schema_shape_id(),
        prefix="ext-schema",
    )
    assert_silent_f06(silent, RULE_SHAPE)
    _, twin = _lint(
        copied_plugin,
        snippet_declared_external_schema_shape_id(twin=True),
        prefix="ext-schema-twin",
    )
    assert_silent_f06(twin, RULE_SHAPE)


def test_declared_external_outer_inner_shape_is_silent(copied_plugin):
    _live_shape_fire(copied_plugin, prefix="outer-inner-live")
    _, silent = _lint(
        copied_plugin,
        snippet_declared_external_outer_inner_shape(),
        prefix="outer-inner",
    )
    assert_silent_f06(silent, RULE_SHAPE)
    _, twin = _lint(
        copied_plugin,
        snippet_declared_external_outer_inner_shape(twin=True),
        prefix="outer-inner-twin",
    )
    assert_silent_f06(twin, RULE_SHAPE)


def test_local_binding_member_shape_is_silent(copied_plugin):
    _live_shape_fire(copied_plugin, prefix="local-member-live")
    _, fire_prop = _lint(
        copied_plugin,
        snippet_object_property_named_shape(),
        prefix="local-member-prop-live",
    )
    assert_only_rule(fire_prop, RULE_SHAPE)
    _, silent = _lint(
        copied_plugin,
        snippet_local_binding_member_shape(),
        prefix="local-member",
    )
    assert_silent_f06(silent, RULE_SHAPE)
    _, twin = _lint(
        copied_plugin,
        snippet_local_binding_member_shape(twin=True),
        prefix="local-member-twin",
    )
    assert_silent_f06(twin, RULE_SHAPE)


def test_assignment_to_schema_shape_is_silent(copied_plugin):
    _live_shape_fire(copied_plugin, prefix="assign-schema-live")
    _, read = _lint(
        copied_plugin,
        snippet_declared_external_schema_shape_id(),
        prefix="assign-schema-read",
    )
    assert_silent_f06(read, RULE_SHAPE)
    _, silent = _lint(
        copied_plugin,
        snippet_assignment_to_schema_shape(),
        prefix="assign-schema",
    )
    assert_silent_f06(silent, RULE_SHAPE)
    _, twin = _lint(
        copied_plugin,
        snippet_assignment_to_schema_shape(twin=True),
        prefix="assign-schema-twin",
    )
    assert_silent_f06(twin, RULE_SHAPE)


def test_assignment_to_local_shape_is_silent(copied_plugin):
    _live_shape_fire(copied_plugin, prefix="assign-local-live")
    _, local_read = _lint(
        copied_plugin,
        snippet_local_binding_member_shape(),
        prefix="assign-local-read",
    )
    assert_silent_f06(local_read, RULE_SHAPE)
    _, ext_assign = _lint(
        copied_plugin,
        snippet_assignment_to_schema_shape(),
        prefix="assign-local-ext",
    )
    assert_silent_f06(ext_assign, RULE_SHAPE)
    _, silent = _lint(
        copied_plugin,
        snippet_assignment_to_local_shape(),
        prefix="assign-local",
    )
    assert_silent_f06(silent, RULE_SHAPE)


def test_local_binding_member_containing_shape_is_silent(copied_plugin):
    _, fn_fire = _lint(
        copied_plugin, snippet_function_shape_of(), prefix="member-contains-live"
    )
    assert_only_rule(fn_fire, RULE_SHAPE)
    _, silent = _lint(
        copied_plugin,
        snippet_local_binding_member_containing_shape(),
        prefix="member-contains",
    )
    assert_silent_f06(silent, RULE_SHAPE)


def test_ordinary_property_owner_id_is_silent(copied_plugin):
    _, type_prop = _lint(
        copied_plugin,
        snippet_type_property_named_shape(),
        prefix="ordinary-type-live",
    )
    assert_only_rule(type_prop, RULE_SHAPE)
    _, obj_prop = _lint(
        copied_plugin,
        snippet_object_property_named_shape(),
        prefix="ordinary-obj-live",
    )
    assert_only_rule(obj_prop, RULE_SHAPE)
    _, silent = _lint(
        copied_plugin,
        snippet_ordinary_property_owner_id(),
        prefix="ordinary-id",
    )
    assert_silent_f06(silent, RULE_SHAPE)
    _, twin = _lint(
        copied_plugin,
        snippet_ordinary_property_owner_id(twin=True),
        prefix="ordinary-id-twin",
    )
    assert_silent_f06(twin, RULE_SHAPE)


# ---------------------------------------------------------------------------
# C. Diagnostic identifies the shape name, not a neighbor
# ---------------------------------------------------------------------------


def test_shape_finding_identifies_the_owned_name_not_a_neighbor(copied_plugin):
    later = snippet_neighbor_allowed_then_shape()
    earlier = snippet_neighbor_shape_then_allowed()
    later_path, later_result = _lint(
        copied_plugin, later.source, prefix="neighbor-later"
    )
    earlier_path, earlier_result = _lint(
        copied_plugin, earlier.source, prefix="neighbor-earlier"
    )
    print(
        f"neighbor later={later_path.name} earlier={earlier_path.name}",
        flush=True,
    )
    later_off = assert_shape_finding_on_owned_not_neighbor(
        later.source, later_result, later
    )
    earlier_off = assert_shape_finding_on_owned_not_neighbor(
        earlier.source, earlier_result, earlier
    )
    print(f"neighbor-offsets later={later_off} earlier={earlier_off}", flush=True)
    if later_off <= earlier_off:
        raise AssertionError(
            "when the owned shape name comes later, its finding's sortable "
            "position must be greater than when it comes first; "
            f"later={later_off} earlier={earlier_off}"
        )


def test_shape_finding_identifies_the_owned_name_when_it_comes_first(
    copied_plugin,
):
    later = snippet_neighbor_allowed_then_shape()
    earlier = snippet_neighbor_shape_then_allowed()
    _, later_result = _lint(
        copied_plugin, later.source, prefix="neighbor-first-later"
    )
    _, earlier_result = _lint(
        copied_plugin, earlier.source, prefix="neighbor-first-earlier"
    )
    later_off = assert_shape_finding_on_owned_not_neighbor(
        later.source, later_result, later
    )
    earlier_off = assert_shape_finding_on_owned_not_neighbor(
        earlier.source, earlier_result, earlier
    )
    if earlier_off >= later_off:
        raise AssertionError(
            "when the owned shape name comes first, its finding's sortable "
            "position must be smaller than when it comes later; "
            f"earlier={earlier_off} later={later_off}"
        )


# ---------------------------------------------------------------------------
# D. no-shape-in-symbol-names does not autofix
# ---------------------------------------------------------------------------


def test_fix_mode_does_not_rename_const_shape(copied_plugin):
    ws, specifier = copied_plugin
    run_shape_fix(
        ws,
        specifier,
        snippet_const_shape_binding(),
        prefix="fix-const-shape",
    )


def test_fix_mode_does_not_rename_interface_UserShape(copied_plugin):
    ws, specifier = copied_plugin
    run_shape_fix(
        ws,
        specifier,
        snippet_interface_user_shape(),
        prefix="fix-iface-shape",
    )


def test_fix_mode_does_not_rename_function_shapeOf(copied_plugin):
    ws, specifier = copied_plugin
    run_shape_fix(
        ws,
        specifier,
        snippet_function_shape_of(),
        prefix="fix-fn-shape",
    )


# ---------------------------------------------------------------------------
# E. Top-level adjacent non-import blanks
# ---------------------------------------------------------------------------


def test_top_level_const_then_const_reports_and_fix_inserts_one_blank(
    copied_plugin,
):
    public = snippet_two_top_level_consts()
    _insert(
        copied_plugin,
        public,
        prefix="two-const",
        exactly_one=True,
    )
    twin = snippet_two_top_level_consts(twin=True)
    _insert(
        copied_plugin,
        twin,
        prefix="two-const-twin",
        exactly_one=True,
    )


def test_export_const_then_documented_export_type_reports_and_fix(
    copied_plugin,
):
    _insert_docs(
        copied_plugin,
        snippet_export_const_then_documented_export_type(),
        prefix="docs-type",
    )
    _insert_docs(
        copied_plugin,
        snippet_export_const_then_documented_export_type(twin=True),
        prefix="docs-type-twin",
    )


def test_interface_then_class_reports_and_fix(copied_plugin):
    _insert(
        copied_plugin, snippet_interface_then_class(), prefix="iface-class"
    )
    _insert(
        copied_plugin,
        snippet_interface_then_class(twin=True),
        prefix="iface-class-twin",
    )


def test_adjacent_type_declarations_report_and_fix(copied_plugin):
    _insert(
        copied_plugin,
        snippet_adjacent_type_declarations(),
        prefix="adj-types",
    )
    _insert(
        copied_plugin,
        snippet_adjacent_type_declarations(twin=True),
        prefix="adj-types-twin",
    )


def test_adjacent_top_level_functions_report_and_fix(copied_plugin):
    _insert(
        copied_plugin,
        snippet_adjacent_top_level_functions(),
        prefix="adj-fns",
    )
    _insert(
        copied_plugin,
        snippet_adjacent_top_level_functions(twin=True),
        prefix="adj-fns-twin",
    )


# ---------------------------------------------------------------------------
# F. After imports before the first non-import
# ---------------------------------------------------------------------------


def test_blank_after_imports_before_first_non_import_reports_and_fix(
    copied_plugin,
):
    _insert(copied_plugin, snippet_import_then_const(), prefix="import-const")
    _insert(
        copied_plugin,
        snippet_import_then_const(twin=True),
        prefix="import-const-twin",
    )


def test_blank_after_imports_before_first_function_reports_and_fix(
    copied_plugin,
):
    _insert(
        copied_plugin, snippet_import_then_function(), prefix="import-fn"
    )
    _insert(
        copied_plugin,
        snippet_import_then_function(twin=True),
        prefix="import-fn-twin",
    )


# ---------------------------------------------------------------------------
# G. Before return / if / switch / try / for / while / do in a block
# ---------------------------------------------------------------------------


def test_blank_before_if_after_statement_reports_and_fix(copied_plugin):
    path, after = _insert(
        copied_plugin, snippet_blank_before_if(), prefix="before-if"
    )
    if "if (a) go();" not in after:
        raise AssertionError(
            "fix must not wrap the unbraced consequent; "
            f"path={path} after={after!r}"
        )
    _insert(
        copied_plugin,
        snippet_blank_before_if(twin=True),
        prefix="before-if-twin",
    )


def test_blank_before_switch_after_statement_reports_and_fix(copied_plugin):
    _insert(
        copied_plugin, snippet_blank_before_switch(), prefix="before-switch"
    )
    _insert(
        copied_plugin,
        snippet_blank_before_switch(twin=True),
        prefix="before-switch-twin",
    )


def test_blank_before_try_after_statement_reports_and_fix(copied_plugin):
    _insert(copied_plugin, snippet_blank_before_try(), prefix="before-try")
    _insert(
        copied_plugin,
        snippet_blank_before_try(twin=True),
        prefix="before-try-twin",
    )


def test_blank_before_for_after_statement_reports_and_fix(copied_plugin):
    _insert(copied_plugin, snippet_blank_before_for(), prefix="before-for")
    _insert(
        copied_plugin,
        snippet_blank_before_for(twin=True),
        prefix="before-for-twin",
    )


def test_blank_before_while_after_statement_reports_and_fix(copied_plugin):
    _insert(
        copied_plugin, snippet_blank_before_while(), prefix="before-while"
    )
    _insert(
        copied_plugin,
        snippet_blank_before_while(twin=True),
        prefix="before-while-twin",
    )


def test_blank_before_do_after_statement_reports_and_fix(copied_plugin):
    _insert(copied_plugin, snippet_blank_before_do(), prefix="before-do")
    _insert(
        copied_plugin,
        snippet_blank_before_do(twin=True),
        prefix="before-do-twin",
    )


def test_compact_two_statement_body_still_gets_blank_before_return(
    copied_plugin,
):
    _insert(
        copied_plugin,
        snippet_compact_two_statement_body(),
        prefix="compact-two",
    )
    _insert(
        copied_plugin,
        snippet_compact_two_statement_body(twin=True),
        prefix="compact-two-twin",
    )


def test_blank_before_return_in_nested_block_reports_and_fix(copied_plugin):
    _insert(
        copied_plugin,
        snippet_blank_before_return_in_nested_block(),
        prefix="nested-return",
    )
    _insert(
        copied_plugin,
        snippet_blank_before_return_in_nested_block(twin=True),
        prefix="nested-return-twin",
    )


# ---------------------------------------------------------------------------
# H. After a block-like statement before the next statement
# ---------------------------------------------------------------------------


def test_blank_after_block_like_before_next_statement_reports_and_fix(
    copied_plugin,
):
    _insert(copied_plugin, snippet_blank_after_if_block(), prefix="after-if")
    _insert(
        copied_plugin,
        snippet_blank_after_if_block(twin=True),
        prefix="after-if-twin",
    )


def test_blank_after_try_block_before_next_statement_reports_and_fix(
    copied_plugin,
):
    _insert(copied_plugin, snippet_blank_after_try_block(), prefix="after-try")
    _insert(
        copied_plugin,
        snippet_blank_after_try_block(twin=True),
        prefix="after-try-twin",
    )


# ---------------------------------------------------------------------------
# I. Around multiline const / let / var / using
# ---------------------------------------------------------------------------


def test_multiline_const_around_neighbors_reports_and_fix(copied_plugin):
    snippet, extra_left, extra_right = snippet_multiline_binding("const")
    _insert(
        copied_plugin,
        snippet,
        prefix="ml-const",
        extra_sites=((extra_left, extra_right),),
    )
    twin, t_left, t_right = snippet_multiline_binding("const", twin=True)
    _insert(
        copied_plugin,
        twin,
        prefix="ml-const-twin",
        extra_sites=((t_left, t_right),),
    )


def test_multiline_let_around_neighbors_reports_and_fix(copied_plugin):
    snippet, extra_left, extra_right = snippet_multiline_binding("let")
    _insert(
        copied_plugin,
        snippet,
        prefix="ml-let",
        extra_sites=((extra_left, extra_right),),
    )
    twin, t_left, t_right = snippet_multiline_binding("let", twin=True)
    _insert(
        copied_plugin,
        twin,
        prefix="ml-let-twin",
        extra_sites=((t_left, t_right),),
    )


def test_multiline_var_around_neighbors_reports_and_fix(copied_plugin):
    snippet, extra_left, extra_right = snippet_multiline_binding("var")
    _insert(
        copied_plugin,
        snippet,
        prefix="ml-var",
        extra_sites=((extra_left, extra_right),),
    )
    twin, t_left, t_right = snippet_multiline_binding("var", twin=True)
    _insert(
        copied_plugin,
        twin,
        prefix="ml-var-twin",
        extra_sites=((t_left, t_right),),
    )


def test_multiline_using_around_neighbors_reports_and_fix(copied_plugin):
    snippet, extra_left, extra_right = snippet_multiline_binding("using")
    _insert(
        copied_plugin,
        snippet,
        prefix="ml-using",
        extra_sites=((extra_left, extra_right),),
    )
    twin, t_left, t_right = snippet_multiline_binding("using", twin=True)
    _insert(
        copied_plugin,
        twin,
        prefix="ml-using-twin",
        extra_sites=((t_left, t_right),),
    )


# ---------------------------------------------------------------------------
# J. Around nested function / class / interface / type
# ---------------------------------------------------------------------------


def test_nested_function_around_neighbors_reports_and_fix(copied_plugin):
    snippet, extra_left, extra_right = snippet_nested_function_around_neighbors()
    _insert(
        copied_plugin,
        snippet,
        prefix="nested-fn",
        extra_sites=((extra_left, extra_right),),
    )
    twin, t_left, t_right = snippet_nested_function_around_neighbors(twin=True)
    _insert(
        copied_plugin,
        twin,
        prefix="nested-fn-twin",
        extra_sites=((t_left, t_right),),
    )


def test_nested_class_around_neighbors_reports_and_fix(copied_plugin):
    snippet, extra_left, extra_right = snippet_nested_class_around_neighbors()
    _insert(
        copied_plugin,
        snippet,
        prefix="nested-class",
        extra_sites=((extra_left, extra_right),),
    )
    twin, t_left, t_right = snippet_nested_class_around_neighbors(twin=True)
    _insert(
        copied_plugin,
        twin,
        prefix="nested-class-twin",
        extra_sites=((t_left, t_right),),
    )


def test_nested_interface_around_neighbors_reports_and_fix(copied_plugin):
    snippet, extra_left, extra_right = (
        snippet_nested_interface_around_neighbors()
    )
    _insert(
        copied_plugin,
        snippet,
        prefix="nested-iface",
        extra_sites=((extra_left, extra_right),),
    )
    twin, t_left, t_right = snippet_nested_interface_around_neighbors(
        twin=True
    )
    _insert(
        copied_plugin,
        twin,
        prefix="nested-iface-twin",
        extra_sites=((t_left, t_right),),
    )


def test_nested_type_around_neighbors_reports_and_fix(copied_plugin):
    snippet, extra_left, extra_right = snippet_nested_type_around_neighbors()
    _insert(
        copied_plugin,
        snippet,
        prefix="nested-type",
        extra_sites=((extra_left, extra_right),),
    )
    twin, t_left, t_right = snippet_nested_type_around_neighbors(twin=True)
    _insert(
        copied_plugin,
        twin,
        prefix="nested-type-twin",
        extra_sites=((t_left, t_right),),
    )


# ---------------------------------------------------------------------------
# K. Preserves
# ---------------------------------------------------------------------------


def test_adjacent_imports_stay_grouped(copied_plugin):
    _, fire = _lint(
        copied_plugin,
        snippet_import_then_const().source,
        prefix="imports-grouped-live",
    )
    assert_only_rule(fire, RULE_SPACING)
    _, fire_fn = _lint(
        copied_plugin,
        snippet_import_then_function().source,
        prefix="imports-grouped-fn-live",
    )
    assert_only_rule(fire_fn, RULE_SPACING)
    _preserve(
        copied_plugin,
        snippet_adjacent_imports_grouped(),
        prefix="imports-grouped",
    )


def test_short_inner_consts_stay_grouped_and_blank_before_return(
    copied_plugin,
):
    ws, specifier = copied_plugin
    top = snippet_two_top_level_consts()
    _, top_fire = _lint(
        copied_plugin, top.source, prefix="short-inner-top-live"
    )
    assert_only_rule(top_fire, RULE_SPACING)

    def _run(source, first, second, ret, prefix):
        path = write_f06_source(ws, source, prefix=prefix)
        before_lint = lint_f06(ws, [path], specifier)
        assert_only_rule(before_lint, RULE_SPACING)
        before = read_source_bytes(path)
        lint_f06(ws, [path], specifier, fix=True)
        after = read_source_text(path)
        assert_whitespace_only_change(before.decode("utf-8"), after)
        assert_no_blank_between(after, first, second)
        assert_blank_between(after, second, ret)
        assert_second_pass_stable(ws, specifier, path, after.encode("utf-8"))
        print(f"short-inner {path.name}", flush=True)

    public = snippet_short_inner_consts_then_return()
    _run(*public, "short-inner")
    twin = snippet_short_inner_consts_then_return(twin=True)
    _run(*twin, "short-inner-twin")


def test_overload_signatures_stay_grouped_with_implementation(copied_plugin):
    _, fire = _lint(
        copied_plugin,
        snippet_adjacent_top_level_functions().source,
        prefix="overload-live",
    )
    assert_only_rule(fire, RULE_SPACING)
    _preserve(
        copied_plugin, snippet_overload_signatures(), prefix="overload"
    )
    _preserve(
        copied_plugin,
        snippet_overload_signatures(twin=True),
        prefix="overload-twin",
    )


def test_docs_blank_goes_before_documentation_not_between(copied_plugin):
    _insert_docs(
        copied_plugin,
        snippet_docs_export_const_then_export_const(),
        prefix="docs-const",
    )
    _insert_docs(
        copied_plugin,
        snippet_docs_export_const_then_export_const(twin=True),
        prefix="docs-const-twin",
    )


def test_extra_blank_lines_are_not_removed(copied_plugin):
    missing = snippet_two_top_level_consts()
    _, fire = _lint(
        copied_plugin, missing.source, prefix="extra-blank-live"
    )
    assert_only_rule(fire, RULE_SPACING)
    _preserve(
        copied_plugin,
        snippet_extra_blank_lines_between_consts(),
        prefix="extra-blank",
    )
    _preserve(
        copied_plugin,
        snippet_extra_blank_lines_between_consts(twin=True),
        prefix="extra-blank-twin",
    )


def test_extra_blank_lines_between_imports_are_not_removed(copied_plugin):
    _, fire = _lint(
        copied_plugin,
        snippet_import_then_const().source,
        prefix="extra-import-live",
    )
    assert_only_rule(fire, RULE_SPACING)
    _preserve(
        copied_plugin,
        snippet_extra_blanks_between_imports(),
        prefix="extra-import",
    )


def test_single_statement_compact_body_stays_on_one_line(copied_plugin):
    _, fire = _lint(
        copied_plugin,
        snippet_compact_two_statement_body().source,
        prefix="compact-one-live",
    )
    assert_only_rule(fire, RULE_SPACING)
    _preserve(
        copied_plugin,
        snippet_single_statement_compact_body(),
        prefix="compact-one",
    )
    _preserve(
        copied_plugin,
        snippet_single_statement_compact_body(twin=True),
        prefix="compact-one-twin",
    )


def test_adjacent_switch_case_clauses_stay_compact(copied_plugin):
    _, fire = _lint(
        copied_plugin,
        snippet_blank_before_switch().source,
        prefix="case-live",
    )
    assert_only_rule(fire, RULE_SPACING)
    _preserve(
        copied_plugin,
        snippet_adjacent_switch_case_clauses(),
        prefix="case-compact",
    )
    _preserve(
        copied_plugin,
        snippet_adjacent_switch_case_clauses(twin=True),
        prefix="case-compact-twin",
    )


# ---------------------------------------------------------------------------
# L. Idempotent second pass; only-spacing two-declaration files
# ---------------------------------------------------------------------------


def test_two_declaration_files_fail_then_fix_then_succeed_and_second_pass_stable(
    copied_plugin,
):
    ws, specifier = copied_plugin
    docs = snippet_docs_export_const_then_export_const(twin=True)
    inner_src, inner_first, inner_second, inner_ret = (
        snippet_short_inner_consts_then_return(twin=True)
    )
    docs_path = write_f06_source(ws, docs.source, prefix="twofile-docs")
    inner_path = write_f06_source(ws, inner_src, prefix="twofile-inner")
    files = [docs_path, inner_path]
    only = (RULE_SPACING,)
    before = lint_f06(ws, files, specifier, rules=only)
    print(f"two-file before exit={before.returncode}", flush=True)
    assert_fired(before, RULE_SPACING)
    docs_before = read_source_bytes(docs_path)
    inner_before = read_source_bytes(inner_path)
    lint_f06(ws, files, specifier, rules=only, fix=True)
    docs_after = read_source_text(docs_path)
    inner_after = read_source_text(inner_path)
    assert_whitespace_only_change(docs_before.decode("utf-8"), docs_after)
    assert_whitespace_only_change(inner_before.decode("utf-8"), inner_after)
    assert_docs_attached_after_fix(docs, docs_after)
    assert_no_blank_between(inner_after, inner_first, inner_second)
    assert_blank_between(inner_after, inner_second, inner_ret)
    clean = lint_f06(ws, files, specifier, rules=only)
    print(f"two-file after exit={clean.returncode}", flush=True)
    assert_silent_f06(clean, RULE_SPACING)
    lint_f06(ws, files, specifier, rules=only, fix=True)
    if read_source_bytes(docs_path) != docs_after.encode("utf-8"):
        raise AssertionError("second fix pass rewrote the docs file")
    if read_source_bytes(inner_path) != inner_after.encode("utf-8"):
        raise AssertionError("second fix pass rewrote the inner-const file")

    pair = snippet_two_top_level_consts(twin=True)
    pair_path, pair_after = _insert(
        copied_plugin, pair, prefix="twofile-consts", exactly_one=True
    )
    print(
        f"two-file consts {pair_path.name} after_len={len(pair_after)}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# M. Inserts whitespace only
# ---------------------------------------------------------------------------


def test_fix_does_not_add_braces_or_wrap_or_sort_imports(copied_plugin):
    ws, specifier = copied_plugin
    if_path, if_after = _insert(
        copied_plugin, snippet_blank_before_if(), prefix="m-braces"
    )
    if "if (a) go();" not in if_after:
        raise AssertionError(
            "fix must not add braces around the unbraced consequent; "
            f"path={if_path} after={if_after!r}"
        )

    long_snip, statement = snippet_long_initializer_two_consts()
    long_path, long_after = _insert(
        copied_plugin, long_snip, prefix="m-wrap", exactly_one=True
    )
    if statement not in long_after:
        raise AssertionError(
            "fix must not wrap a long one-line initializer; "
            f"path={long_path} statement={statement!r} after={long_after!r}"
        )
    if "\n" in statement:
        raise AssertionError("fixture initializer was not one line")

    unsorted = snippet_unsorted_imports_then_const()
    path = write_f06_source(ws, unsorted.source, prefix="m-sort")
    before_lint = lint_f06(ws, [path], specifier)
    assert_only_rule(before_lint, RULE_SPACING)
    before = read_source_bytes(path)
    lint_f06(ws, [path], specifier, fix=True)
    after = read_source_text(path)
    assert_whitespace_only_change(before.decode("utf-8"), after)
    b_at = after.find('import { b } from "mod-b";')
    a_at = after.find('import { a } from "mod-a";')
    print(f"import-order b={b_at} a={a_at}", flush=True)
    if b_at < 0 or a_at < 0 or b_at >= a_at:
        raise AssertionError(
            "fix must not sort imports; "
            f"b_at={b_at} a_at={a_at} after={after!r}"
        )
    assert_blank_between(
        after, 'import { a } from "mod-a";', "const c = 1;"
    )
    assert_second_pass_stable(ws, specifier, path, after.encode("utf-8"))


# ---------------------------------------------------------------------------
# O. JavaScript as well as TypeScript
# ---------------------------------------------------------------------------


def test_javascript_shape_and_spacing_match_typescript(copied_plugin):
    js_fires = (
        (snippet_const_shape_binding(twin=True), "js-const", RULE_SHAPE),
        (snippet_function_shape_of(twin=True), "js-fn", RULE_SHAPE),
        (snippet_class_shape(twin=True), "js-class", RULE_SHAPE),
        (snippet_private_name_shape(twin=True), "js-private", RULE_SHAPE),
        (snippet_object_property_named_shape(twin=True), "js-obj", RULE_SHAPE),
    )
    for source, prefix, rule_name in js_fires:
        path, result = _lint(
            copied_plugin, source, prefix=prefix, ext="js"
        )
        print(f"{prefix} path={path.name} rule={rule_name}", flush=True)
        assert_only_rule(result, rule_name)

    pair = snippet_two_top_level_consts(twin=True)
    _insert(
        copied_plugin,
        pair,
        prefix="js-two-const",
        ext="js",
        exactly_one=True,
    )
    _insert(
        copied_plugin,
        snippet_blank_before_while(twin=True),
        prefix="js-while",
        ext="js",
    )
