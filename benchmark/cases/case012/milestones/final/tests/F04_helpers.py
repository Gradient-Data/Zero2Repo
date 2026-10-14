# feature: F04
"""Observation helpers for the five explicit-contract checks.

Import side effects: none. Process spawn and filesystem writes happen only
when a caller invokes a function below.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from _harness import (
    GENERIC_PLUGIN_NAME,
    Diagnostic,
    HarnessError,
    RunResult,
    Workspace,
    diagnostics,
    generic_plugin,
    rule_key,
)
from F01_helpers import (
    lint_policy_findings,
    assert_fired,
    assert_no_plugin_findings,
    assert_only_rule,
    effect_plugin_findings,
    ensure_host_plugin_modules,
    fresh_ident,
    published_rule_id,
    rule_fired,
)
from F02_helpers import assert_fix_preserves_source

F04_RULE_NAMES: tuple[str, ...] = (
    "no-object-parameters",
    "no-unknown-parameters",
    "no-unknown-returns",
    "no-unknown-type-aliases",
    "no-unsafe-dictionary-type",
)

RULE_OBJECT = "no-object-parameters"
RULE_UNKNOWN_PARAM = "no-unknown-parameters"
RULE_UNKNOWN_RETURN = "no-unknown-returns"
RULE_UNKNOWN_ALIAS = "no-unknown-type-aliases"
RULE_DICT = "no-unsafe-dictionary-type"


@dataclass(frozen=True)
class PredicateExtraSnippet:
    """A type-predicate file with an extra unknown besides the subject."""

    source: str
    subject_span: tuple[int, int]
    extra_span: tuple[int, int]


@dataclass(frozen=True)
class LaterAliasSnippet:
    """Chained unknown aliases; later_decl_span is the non-keyword RHS alias."""

    source: str
    later_decl_span: tuple[int, int]


@dataclass(frozen=True)
class WrapperDictionarySnippet:
    """Wrapper writing of an unsafe dictionary, plus inner writings that cannot explain a pass."""

    source: str
    writing_spans: tuple[tuple[int, int], ...]
    inner_spans: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class BrandDictionaryCase:
    """One brand-only empty value written as one dictionary form.

    *wrapper* is set when the writing is Readonly, Partial, Required, Pick,
    or Omit. A finding that sits only on the inner dictionary does not
    satisfy that writing.
    """

    label: str
    writing: str
    source: str
    wrapper: WrapperDictionarySnippet | None = None


def lint_f04(
    ws: Workspace,
    files: Sequence[str | Path],
    specifier: str | Path,
    *,
    rules: Sequence[str] = F04_RULE_NAMES,
    fix: bool = False,
) -> RunResult:
    """Register lint-policy; enable *rules* at error; optional ``--fix``."""
    ensure_host_plugin_modules(ws)
    print(
        f"lint-f04 specifier={specifier} rules={list(rules)} "
        f"fix={fix} files={list(files)}",
        flush=True,
    )
    plugin = generic_plugin(specifier=specifier, root=ws.root)
    mapping = {rule_key(GENERIC_PLUGIN_NAME, name): "error" for name in rules}
    return ws.lint(files, plugins=[plugin], rules=mapping, fix=fix)


def write_f04_source(
    ws: Workspace,
    source: str,
    *,
    prefix: str = "f04",
) -> Path:
    rel = f"{prefix}-{fresh_ident('s')}.ts"
    print(f"write {rel}", flush=True)
    return ws.write(rel, source)


def lint_f04_source(
    ws: Workspace,
    specifier: str | Path,
    source: str,
    *,
    prefix: str = "f04",
    fix: bool = False,
    rules: Sequence[str] = F04_RULE_NAMES,
) -> tuple[Path, RunResult]:
    path = write_f04_source(ws, source, prefix=prefix)
    result = lint_f04(ws, [path], specifier, rules=rules, fix=fix)
    print(f"lint {path.name} exit={result.returncode}", flush=True)
    return path, result


def assert_silent_f04(result: RunResult, rule_name: str) -> None:
    """Classified success and no finding from *rule_name* (F04 rules only)."""
    generic = lint_policy_findings(result)
    effect = effect_plugin_findings(result)
    print(
        f"assert-silent-f04 {rule_name} exit={result.returncode} "
        f"generic={generic} effect={effect}",
        flush=True,
    )
    if rule_fired(generic, rule_name):
        raise AssertionError(
            f"rule {rule_name} must not fire; got {generic}"
        )
    if result.returncode != 0:
        raise HarnessError(
            "silence with only F04 rules enabled requires classified success; "
            f"non-success with empty findings is not silence; "
            f"exit={result.returncode} generic={generic} "
            f"stderr={result.stderr_text!r}"
        )
    if generic or effect:
        raise AssertionError(
            "expected no lint-policy findings on the silent arm; "
            f"generic={generic} effect={effect}"
        )
    assert_no_plugin_findings(result)


def run_f04_fix(
    ws: Workspace,
    specifier: str | Path,
    source: str,
    rule_name: str,
    *,
    prefix: str = "fix",
) -> RunResult:
    """Lint with host ``--fix``; require unchanged bytes and only that rule."""
    path = write_f04_source(ws, source, prefix=prefix)
    before = path.read_bytes()
    result = lint_f04(ws, [path], specifier, fix=True)
    print(f"fix-mode {path.name} rule={rule_name}", flush=True)
    assert_fix_preserves_source(path, before, result, rule_name)
    assert_only_rule(result, rule_name)
    return result


# ---------------------------------------------------------------------------
# Position helpers (Rule 1: missing line/column is not "not reported")
# ---------------------------------------------------------------------------


def _line_starts(source: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(source):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _offset_from_line_column(source: str, line: int, column: int) -> int:
    """Character offset of a 1-based ``line`` / ``column`` in *source*.

    The Interface Contract states the host report gives the reported
    position as 1-based line and column of the first label's span. No
    other base is tried.
    """
    starts = _line_starts(source)
    line_index = line - 1
    if 0 <= line_index < len(starts) and column >= 1:
        start = starts[line_index]
        end = starts[line_index + 1] if line_index + 1 < len(starts) else len(source)
        offset = start + column - 1
        if start <= offset <= end:
            return offset
    raise HarnessError(
        f"cannot place diagnostic at 1-based line={line} column={column} "
        f"in a {len(source)}-byte source"
    )


def _require_line_column(item: Diagnostic) -> tuple[int, int]:
    if item.line is None or item.column is None:
        raise HarnessError(
            f"diagnostic for {item.rule!r} is missing line/column; "
            "cannot identify the construct; "
            f"raw={item.raw!r}"
        )
    return item.line, item.column


def rule_diagnostics(result: RunResult, rule_name: str) -> tuple[Diagnostic, ...]:
    expected = rule_key(GENERIC_PLUGIN_NAME, rule_name)
    classified = diagnostics(result)
    matched = tuple(
        item
        for item in classified
        if published_rule_id(item.rule) == expected
    )
    print(
        f"rule-diagnostics {rule_name} n={len(matched)} "
        f"exit={result.returncode}",
        flush=True,
    )
    return matched


def diagnostic_offset(source: str, item: Diagnostic) -> int:
    line, column = _require_line_column(item)
    offset = _offset_from_line_column(source, line, column)
    print(
        f"diag-offset rule={item.rule} line={line} column={column} "
        f"offset={offset}",
        flush=True,
    )
    return offset


def diagnostic_sort_key(item: Diagnostic) -> tuple[int, int]:
    line, column = _require_line_column(item)
    return (line, column)


def _in_span(offset: int, span: tuple[int, int]) -> bool:
    start, end = span
    return start <= offset < end


def _span_of(source: str, fragment: str) -> tuple[int, int]:
    start = source.find(fragment)
    if start < 0:
        raise HarnessError(
            f"fragment {fragment!r} not found in source {source!r}"
        )
    return start, start + len(fragment)


def extra_unknown_finding(
    result: RunResult,
    source: str,
    *,
    subject_span: tuple[int, int],
    extra_span: tuple[int, int],
) -> Diagnostic:
    """Return the no-unknown-parameters finding that identifies the extra.

    Hard-fails on missing positions. A finding inside the subject span is
    a failure (the exact subject is allowed). A report that never lands in
    the extra span has not identified the extra parameter.
    """
    assert_fired(result, RULE_UNKNOWN_PARAM)
    findings = rule_diagnostics(result, RULE_UNKNOWN_PARAM)
    extra: Diagnostic | None = None
    for item in findings:
        offset = diagnostic_offset(source, item)
        if _in_span(offset, subject_span):
            raise AssertionError(
                "no-unknown-parameters must not report the predicate "
                f"subject; offset={offset} subject_span={subject_span} "
                f"source={source!r}"
            )
        if _in_span(offset, extra_span):
            extra = item
    if extra is None:
        raise AssertionError(
            "no-unknown-parameters must identify the extra unknown "
            f"parameter; extra_span={extra_span} source={source!r}"
        )
    return extra


def assert_predicate_extra_relative_order(
    later: tuple[PredicateExtraSnippet, RunResult],
    still_later: tuple[PredicateExtraSnippet, RunResult],
    before: tuple[PredicateExtraSnippet, RunResult],
) -> None:
    """Compare extra-unknown arms by relative diagnostic position.

    *later* has the extra after the subject. *still_later* inserts a
    non-unknown middle parameter so the extra moves further right.
    *before* places the extra before the subject (subject is not slot
    zero). Do not pin absolute line/column or the extra's identifier.
    """
    later_snip, later_result = later
    still_snip, still_result = still_later
    before_snip, before_result = before

    later_item = extra_unknown_finding(
        later_result,
        later_snip.source,
        subject_span=later_snip.subject_span,
        extra_span=later_snip.extra_span,
    )
    still_item = extra_unknown_finding(
        still_result,
        still_snip.source,
        subject_span=still_snip.subject_span,
        extra_span=still_snip.extra_span,
    )
    before_item = extra_unknown_finding(
        before_result,
        before_snip.source,
        subject_span=before_snip.subject_span,
        extra_span=before_snip.extra_span,
    )

    later_key = diagnostic_sort_key(later_item)
    still_key = diagnostic_sort_key(still_item)
    before_key = diagnostic_sort_key(before_item)
    print(
        f"predicate-extra-order later={later_key} still_later={still_key} "
        f"before={before_key}",
        flush=True,
    )
    if still_key <= later_key:
        raise AssertionError(
            "extra unknown that moved later must have a greater sortable "
            f"diagnostic position than the earlier extra; "
            f"still_later={still_key} later={later_key}"
        )
    if before_key >= later_key:
        raise AssertionError(
            "extra unknown placed before the subject must have a smaller "
            f"sortable diagnostic position than the extra-later arm; "
            f"before={before_key} later={later_key}"
        )


def assert_later_unknown_alias_span(
    earlier_source: str,
    earlier_result: RunResult,
    later: LaterAliasSnippet,
    later_result: RunResult,
) -> None:
    """A finding for the later alias sits in its declaration span, after earlier."""
    assert_fired(earlier_result, RULE_UNKNOWN_ALIAS)
    assert_fired(later_result, RULE_UNKNOWN_ALIAS)
    earlier_items = rule_diagnostics(earlier_result, RULE_UNKNOWN_ALIAS)
    if not earlier_items:
        raise AssertionError("earlier unknown-alias arm produced no findings")
    earlier_key = min(diagnostic_sort_key(item) for item in earlier_items)

    later_items = rule_diagnostics(later_result, RULE_UNKNOWN_ALIAS)
    in_later: list[tuple[tuple[int, int], Diagnostic]] = []
    for item in later_items:
        offset = diagnostic_offset(later.source, item)
        if _in_span(offset, later.later_decl_span):
            in_later.append((diagnostic_sort_key(item), item))
    if not in_later:
        raise AssertionError(
            "no-unknown-type-aliases must report the later alias whose "
            "RHS is not the unknown keyword; "
            f"later_decl_span={later.later_decl_span} source={later.source!r}"
        )
    later_key = min(key for key, _ in in_later)
    print(
        f"later-alias-span earlier={earlier_key} later={later_key} "
        f"span={later.later_decl_span}",
        flush=True,
    )
    if later_key <= earlier_key:
        raise AssertionError(
            "finding in the later alias declaration must have a greater "
            f"sortable position than the earlier = unknown arm; "
            f"later={later_key} earlier={earlier_key}"
        )


def assert_wrapper_of_unsafe_dictionary_reported(
    result: RunResult,
    snippet: WrapperDictionarySnippet,
) -> None:
    """Report the wrapper writing; an inner Record / Source write is not enough.

    Findings whose positions fall in *inner_spans* (the inner ``Record`` or
    ``type Source = Record<...>`` write) are covariates. A remaining finding
    must sit in a wrapper writing span (``Readonly`` / ``Partial`` /
    ``Required`` / ``Pick`` / ``Omit``). Do not pin message text or a count.
    """
    assert_fired(result, RULE_DICT)
    findings = rule_diagnostics(result, RULE_DICT)
    matched: list[Diagnostic] = []
    for item in findings:
        offset = diagnostic_offset(snippet.source, item)
        if any(_in_span(offset, inner) for inner in snippet.inner_spans):
            print(
                f"wrapper-dict inner-covariate offset={offset} "
                f"inner_spans={snippet.inner_spans}",
                flush=True,
            )
            continue
        if any(_in_span(offset, writing) for writing in snippet.writing_spans):
            matched.append(item)
    print(
        f"wrapper-dict matched={len(matched)} writing={snippet.writing_spans} "
        f"inner={snippet.inner_spans}",
        flush=True,
    )
    if not matched:
        raise AssertionError(
            "no-unsafe-dictionary-type must report the wrapper of the unsafe "
            "dictionary; a finding explained only by the inner dictionary "
            "write is not enough; "
            f"writing_spans={snippet.writing_spans} "
            f"inner_spans={snippet.inner_spans} source={snippet.source!r}"
        )


# ---------------------------------------------------------------------------
# A. Object-parameter fires
# ---------------------------------------------------------------------------


def snippet_object_function_type(*, twin: bool = False) -> str:
    alias = "F" if not twin else fresh_ident("Fn")
    param = "value" if not twin else fresh_ident("arg")
    return f"type {alias} = ({param}: object) => void;\n"


def snippet_object_method_parameter(*, twin: bool = False) -> str:
    owner = "Holder" if not twin else fresh_ident("Owner")
    method = "save" if not twin else fresh_ident("put")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"interface {owner} {{\n"
        f"  {method}({param}: object): void;\n"
        f"}}\n"
    )


def snippet_union_containing_object_parameter(*, twin: bool = False) -> str:
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return f"function {name}({param}: string | object) {{}}\n"


def snippet_same_file_object_alias_parameter(*, twin: bool = False) -> str:
    alias = "Alias" if not twin else fresh_ident("Obj")
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"type {alias} = object;\n"
        f"function {name}({param}: {alias}) {{}}\n"
    )


def snippet_object_alias_on_unrelated_generic(*, twin: bool = False) -> str:
    alias = "Alias" if not twin else fresh_ident("Obj")
    type_param = "T" if not twin else fresh_ident("Gen")
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"type {alias} = object;\n"
        f"function {name}<{type_param}>({param}: {alias}) {{}}\n"
    )


def snippet_identity_of_object_parameter(*, twin: bool = False) -> str:
    ident = "Identity" if not twin else fresh_ident("Id")
    type_param = "T" if not twin else fresh_ident("X")
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"type {ident}<{type_param}> = {type_param};\n"
        f"function {name}({param}: {ident}<object>) {{}}\n"
    )


def snippet_defaulted_object_parameter(*, twin: bool = False) -> str:
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return f"function {name}({param}: object = {{}}) {{}}\n"


def snippet_destructured_object_parameter(*, twin: bool = False) -> str:
    name = "accept" if not twin else fresh_ident("take")
    field = "id" if not twin else fresh_ident("slot")
    return f"function {name}({{ {field} }}: object) {{}}\n"


# ---------------------------------------------------------------------------
# B. Object-parameter silence
# ---------------------------------------------------------------------------


def snippet_named_interface_parameter(*, twin: bool = False) -> str:
    owner = "Owner" if not twin else fresh_ident("Iface")
    field = "id" if not twin else fresh_ident("slot")
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"interface {owner} {{ readonly {field}: string }}\n"
        f"function {name}({param}: {owner}) {{}}\n"
    )


def snippet_named_object_type_parameter(*, twin: bool = False) -> str:
    owner = "Owner" if not twin else fresh_ident("Named")
    field = "id" if not twin else fresh_ident("slot")
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"type {owner} = {{ {field}: string }};\n"
        f"function {name}({param}: {owner}) {{}}\n"
    )


def snippet_generic_type_parameter(*, twin: bool = False) -> str:
    type_param = "Value" if not twin else fresh_ident("Item")
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return f"function {name}<{type_param}>({param}: {type_param}) {{}}\n"


def snippet_generic_extends_object_parameter(*, twin: bool = False) -> str:
    type_param = "Value" if not twin else fresh_ident("Item")
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"function {name}<{type_param} extends object>"
        f"({param}: {type_param}) {{}}\n"
    )


def snippet_type_parameter_shadowing_object_alias(*, twin: bool = False) -> str:
    alias = "Alias" if not twin else fresh_ident("Obj")
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"type {alias} = object;\n"
        f"function {name}<{alias}>({param}: {alias}) {{}}\n"
    )


def snippet_unused_object_alias(*, twin: bool = False) -> str:
    alias = "Alias" if not twin else fresh_ident("Obj")
    return f"type {alias} = object;\n"


def snippet_box_of_object_parameter(*, twin: bool = False) -> str:
    box = "Box" if not twin else fresh_ident("Wrap")
    type_param = "T" if not twin else fresh_ident("X")
    field = "value" if not twin else fresh_ident("held")
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"type {box}<{type_param}> = {{ readonly {field}: {type_param} }};\n"
        f"function {name}({param}: {box}<object>) {{}}\n"
    )


# ---------------------------------------------------------------------------
# C / D. Unknown parameters
# ---------------------------------------------------------------------------


def snippet_union_containing_unknown_parameter(*, twin: bool = False) -> str:
    name = "parse" if not twin else fresh_ident("read")
    param = "value" if not twin else fresh_ident("arg")
    return f"function {name}({param}: string | unknown) {{}}\n"


def snippet_written_unknown_method_parameter(*, twin: bool = False) -> str:
    owner = "Store" if not twin else fresh_ident("Holder")
    method = "save" if not twin else fresh_ident("put")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"interface {owner} {{\n"
        f"  {method}({param}: unknown): void;\n"
        f"}}\n"
    )


def snippet_cause_unknown_parameter(*, twin: bool = False) -> str:
    name = "enrich" if not twin else fresh_ident("wrap")
    return f"function {name}(cause: unknown) {{}}\n"


def snippet_non_cause_unknown_parameter(*, twin: bool = False) -> str:
    name = "enrich" if not twin else fresh_ident("wrap")
    param = fresh_ident("arg")
    return f"function {name}({param}: unknown) {{}}\n"


def snippet_cause_union_containing_unknown(*, twin: bool = False) -> str:
    name = "enrich" if not twin else fresh_ident("wrap")
    return f"function {name}(cause: Error | unknown) {{}}\n"


def snippet_non_cause_union_containing_unknown(*, twin: bool = False) -> str:
    name = "enrich" if not twin else fresh_ident("wrap")
    param = fresh_ident("arg")
    return f"function {name}({param}: Error | unknown) {{}}\n"


def snippet_type_predicate_subject(*, twin: bool = False) -> str:
    name = "isString" if not twin else fresh_ident("isIt")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"function {name}({param}: unknown): {param} is string "
        f"{{ return true; }}\n"
    )


def snippet_assertion_function_subject(*, twin: bool = False) -> str:
    name = "assertString" if not twin else fresh_ident("assertIt")
    param = "value" if not twin else fresh_ident("arg")
    target = "string"
    return f"function {name}({param}: unknown): asserts {param} is {target} {{}}\n"


def snippet_arrow_predicate_subject(*, twin: bool = False) -> str:
    name = "isString" if not twin else fresh_ident("isIt")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"const {name} = ({param}: unknown): {param} is string => true;\n"
    )


def snippet_declared_predicate_subject(*, twin: bool = False) -> str:
    name = "isString" if not twin else fresh_ident("isIt")
    param = "value" if not twin else fresh_ident("arg")
    return f"declare function {name}({param}: unknown): {param} is string;\n"


def snippet_method_predicate_subject(*, twin: bool = False) -> str:
    owner = "Guards" if not twin else fresh_ident("Holder")
    method = "isString" if not twin else fresh_ident("isIt")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"interface {owner} {{\n"
        f"  {method}({param}: unknown): {param} is string;\n"
        f"}}\n"
    )


def snippet_string_or_number_parameter(*, twin: bool = False) -> str:
    name = "parse" if not twin else fresh_ident("read")
    param = "value" if not twin else fresh_ident("arg")
    return f"function {name}({param}: string | number) {{}}\n"


def snippet_unknown_alias_as_parameter(*, twin: bool = False) -> str:
    alias = "Alias" if not twin else fresh_ident("Unk")
    name = "parse" if not twin else fresh_ident("read")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"type {alias} = unknown;\n"
        f"function {name}({param}: {alias}) {{}}\n"
    )


def snippet_identity_of_unknown_as_parameter(*, twin: bool = False) -> str:
    ident = "Identity" if not twin else fresh_ident("Id")
    type_param = "T" if not twin else fresh_ident("X")
    name = "parse" if not twin else fresh_ident("read")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"type {ident}<{type_param}> = {type_param};\n"
        f"function {name}({param}: {ident}<unknown>) {{}}\n"
    )


def predicate_extra_names(*, twin: bool = False) -> tuple[str, str, str, str]:
    """Shared identifiers so extra-unknown arms differ only in extra position."""
    if not twin:
        return "isString", "value", "label", "context"
    return fresh_ident("isIt"), fresh_ident("arg"), fresh_ident("mid"), fresh_ident("more")


def _predicate_extra_snippet(
    name: str,
    subject: str,
    extra: str,
    *,
    middle: str | None = None,
    extra_first: bool = False,
) -> PredicateExtraSnippet:
    subject_frag = f"{subject}: unknown"
    extra_frag = f"{extra}: unknown"
    if extra_first:
        params = f"{extra_frag}, {subject_frag}"
    elif middle is not None:
        params = f"{subject_frag}, {middle}: string, {extra_frag}"
    else:
        params = f"{subject_frag}, {extra_frag}"
    source = (
        f"function {name}({params}): {subject} is string {{ return true; }}\n"
    )
    return PredicateExtraSnippet(
        source=source,
        subject_span=_span_of(source, subject_frag),
        extra_span=_span_of(source, extra_frag),
    )


def snippet_predicate_extra_later(
    *,
    twin: bool = False,
    names: tuple[str, str, str, str] | None = None,
) -> PredicateExtraSnippet:
    fn, subject, _middle, extra = names or predicate_extra_names(twin=twin)
    return _predicate_extra_snippet(fn, subject, extra)


def snippet_predicate_extra_still_later(
    *,
    twin: bool = False,
    names: tuple[str, str, str, str] | None = None,
) -> PredicateExtraSnippet:
    fn, subject, middle, extra = names or predicate_extra_names(twin=twin)
    return _predicate_extra_snippet(fn, subject, extra, middle=middle)


def snippet_predicate_extra_before_subject(
    *,
    twin: bool = False,
    names: tuple[str, str, str, str] | None = None,
) -> PredicateExtraSnippet:
    fn, subject, _middle, extra = names or predicate_extra_names(twin=twin)
    return _predicate_extra_snippet(fn, subject, extra, extra_first=True)


# ---------------------------------------------------------------------------
# E / F. Unknown returns
# ---------------------------------------------------------------------------


def snippet_arrow_unknown_return(*, twin: bool = False) -> str:
    name = "load" if not twin else fresh_ident("fetch")
    held = "input" if not twin else fresh_ident("raw")
    return f"const {name} = (): unknown => {held};\n"


def snippet_declared_unknown_return(*, twin: bool = False) -> str:
    name = "load" if not twin else fresh_ident("fetch")
    return f"declare function {name}(): unknown;\n"


def snippet_method_unknown_return(*, twin: bool = False) -> str:
    owner = "Loader" if not twin else fresh_ident("Holder")
    method = "load" if not twin else fresh_ident("fetch")
    return f"interface {owner} {{ {method}(): unknown }}\n"


def snippet_function_type_unknown_return(*, twin: bool = False) -> str:
    alias = "Loader" if not twin else fresh_ident("Fn")
    return f"type {alias} = () => unknown;\n"


def snippet_generic_function_explicit_unknown_return(*, twin: bool = False) -> str:
    name = "load" if not twin else fresh_ident("fetch")
    type_param = "T" if not twin else fresh_ident("Gen")
    held = "input" if not twin else fresh_ident("raw")
    return f"function {name}<{type_param}>(): unknown {{ return {held}; }}\n"


def snippet_promise_unknown_return(*, twin: bool = False) -> str:
    alias = "Loader" if not twin else fresh_ident("Fn")
    return f"type {alias} = () => Promise<unknown>;\n"


def promise_named_type_names(*, twin: bool = False) -> tuple[str, str, str, str]:
    """Shared identifiers so Promise unknown vs named-type arms differ only in the argument."""
    if not twin:
        return "User", "id", "load", "promise"
    return (
        fresh_ident("Entity"),
        fresh_ident("slot"),
        fresh_ident("fetch"),
        fresh_ident("job"),
    )


def snippet_promise_unknown_function_return(
    *,
    twin: bool = False,
    names: tuple[str, str, str, str] | None = None,
) -> str:
    """Function declaration whose same-file resolved return type is Promise of unknown."""
    user, field, name, held = names or promise_named_type_names(twin=twin)
    return (
        f"type {user} = {{ {field}: string }};\n"
        f"function {name}(): Promise<unknown> {{ return {held}; }}\n"
    )


def snippet_promise_like_unknown_return(*, twin: bool = False) -> str:
    name = "load" if not twin else fresh_ident("fetch")
    held = "promise" if not twin else fresh_ident("job")
    return f"function {name}(): PromiseLike<unknown> {{ return {held}; }}\n"


def snippet_union_containing_unknown_return(*, twin: bool = False) -> str:
    name = "load" if not twin else fresh_ident("fetch")
    held = "input" if not twin else fresh_ident("raw")
    return f"function {name}(): string | unknown {{ return {held}; }}\n"


def snippet_identity_of_unknown_as_return(*, twin: bool = False) -> str:
    ident = "Identity" if not twin else fresh_ident("Id")
    type_param = "T" if not twin else fresh_ident("X")
    name = "load" if not twin else fresh_ident("fetch")
    held = "input" if not twin else fresh_ident("raw")
    return (
        f"type {ident}<{type_param}> = {type_param};\n"
        f"function {name}(): {ident}<unknown> {{ return {held}; }}\n"
    )


def snippet_inner_unknown_alias_as_return(*, twin: bool = False) -> str:
    outer = "outer" if not twin else fresh_ident("wrap")
    alias = "Result" if not twin else fresh_ident("Out")
    name = "load" if not twin else fresh_ident("fetch")
    held = "input" if not twin else fresh_ident("raw")
    return (
        f"function {outer}() {{\n"
        f"  type {alias} = unknown;\n"
        f"  function {name}(): {alias} {{ return {held}; }}\n"
        f"}}\n"
    )


def snippet_inferred_return(*, twin: bool = False) -> str:
    name = "infer" if not twin else fresh_ident("guess")
    held = "input" if not twin else fresh_ident("raw")
    return f"function {name}() {{ return {held}; }}\n"


def snippet_generic_return_of_own_type_parameter(*, twin: bool = False) -> str:
    alias = "Value" if not twin else fresh_ident("Item")
    name = "generic" if not twin else fresh_ident("load")
    held = "value" if not twin else fresh_ident("raw")
    return (
        f"type {alias} = unknown;\n"
        f"function {name}<{alias}>(): {alias} {{ return {held}; }}\n"
    )


def snippet_named_object_return_with_unknown_field(*, twin: bool = False) -> str:
    alias = "Result" if not twin else fresh_ident("Out")
    field = "value" if not twin else fresh_ident("held")
    name = "load" if not twin else fresh_ident("fetch")
    held = "result" if not twin else fresh_ident("got")
    return (
        f"type {alias} = {{ {field}: unknown }};\n"
        f"function {name}(): {alias} {{ return {held}; }}\n"
    )


def snippet_undefined_return_type_name(*, twin: bool = False) -> str:
    name = "load" if not twin else fresh_ident("fetch")
    missing = "MissingType" if not twin else fresh_ident("Absent")
    held = "input" if not twin else fresh_ident("raw")
    return f"function {name}(): {missing} {{ return {held}; }}\n"


def snippet_promise_of_named_type(
    *,
    twin: bool = False,
    names: tuple[str, str, str, str] | None = None,
) -> str:
    user, field, name, held = names or promise_named_type_names(twin=twin)
    return (
        f"type {user} = {{ {field}: string }};\n"
        f"function {name}(): Promise<{user}> {{ return {held}; }}\n"
    )


def snippet_promise_like_of_named_type(*, twin: bool = False) -> str:
    user = "User" if not twin else fresh_ident("Entity")
    field = "id" if not twin else fresh_ident("slot")
    name = "load" if not twin else fresh_ident("fetch")
    held = "promise" if not twin else fresh_ident("job")
    return (
        f"type {user} = {{ {field}: string }};\n"
        f"function {name}(): PromiseLike<{user}> {{ return {held}; }}\n"
    )


# ---------------------------------------------------------------------------
# G / H. Unknown type aliases
# ---------------------------------------------------------------------------


def snippet_union_unknown_type_alias(*, twin: bool = False) -> str:
    alias = "Payload" if not twin else fresh_ident("Body")
    return f"type {alias} = string | unknown;\n"


def snippet_identity_of_unknown_type_alias(*, twin: bool = False) -> str:
    ident = "Identity" if not twin else fresh_ident("Id")
    type_param = "T" if not twin else fresh_ident("X")
    alias = "Payload" if not twin else fresh_ident("Body")
    return (
        f"type {ident}<{type_param}> = {type_param};\n"
        f"type {alias} = {ident}<unknown>;\n"
    )


def snippet_chained_unknown_alias(*, twin: bool = False) -> LaterAliasSnippet:
    inner = "UnknownValue" if not twin else fresh_ident("Inner")
    later = "Alias" if not twin else fresh_ident("Outer")
    first = f"type {inner} = unknown;\n"
    second = f"type {later} = {inner};\n"
    source = first + second
    return LaterAliasSnippet(
        source=source,
        later_decl_span=(len(first), len(source)),
    )


def snippet_string_alias(*, twin: bool = False) -> str:
    alias = "Alias" if not twin else fresh_ident("Name")
    return f"type {alias} = string;\n"


def snippet_box_of_unknown_alias(*, twin: bool = False) -> str:
    box = "Box" if not twin else fresh_ident("Wrap")
    type_param = "T" if not twin else fresh_ident("X")
    field = "value" if not twin else fresh_ident("held")
    alias = "Payload" if not twin else fresh_ident("Body")
    return (
        f"type {box}<{type_param}> = {{ readonly {field}: {type_param} }};\n"
        f"type {alias} = {box}<unknown>;\n"
    )


# ---------------------------------------------------------------------------
# I / J. Unsafe dictionaries
# ---------------------------------------------------------------------------


def snippet_index_signature_of_any(*, twin: bool = False) -> str:
    alias = "Open" if not twin else fresh_ident("Idx")
    key = "key" if not twin else fresh_ident("slot")
    return f"type {alias} = {{ [{key}: string]: any }};\n"


def snippet_mapped_string_dictionary_of_unknown(*, twin: bool = False) -> str:
    alias = "Open" if not twin else fresh_ident("Mapd")
    key = "K" if not twin else fresh_ident("Key")
    return f"type {alias} = {{ [{key} in string]: unknown }};\n"


def snippet_record_of_object(*, twin: bool = False) -> str:
    alias = "A" if not twin else fresh_ident("Dict")
    return f"type {alias} = Record<string, object>;\n"


def snippet_record_of_empty_object(*, twin: bool = False) -> str:
    alias = "A" if not twin else fresh_ident("Dict")
    return f"type {alias} = Record<string, {{}}>;\n"


def snippet_record_of_non_nullable_unknown(*, twin: bool = False) -> str:
    alias = "A" if not twin else fresh_ident("Dict")
    return f"type {alias} = Record<string, NonNullable<unknown>>;\n"


def snippet_record_of_readonly_unknown(*, twin: bool = False) -> str:
    alias = "A" if not twin else fresh_ident("Dict")
    return f"type {alias} = Record<string, Readonly<unknown>>;\n"


def snippet_record_of_empty_interface(*, twin: bool = False) -> str:
    iface = "Escape" if not twin else fresh_ident("Empty")
    alias = "A" if not twin else fresh_ident("Dict")
    return (
        f"interface {iface} {{}}\n"
        f"type {alias} = Record<string, {iface}>;\n"
    )


_BRAND_FORMS: tuple[str, ...] = ("inline", "alias", "interface")
_BRAND_WRITINGS: tuple[str, ...] = (
    "record",
    "index",
    "mapped",
    "readonly",
    "partial",
    "required",
    "pick",
    "omit",
)
_BRAND_WRAPPERS: tuple[str, ...] = (
    "readonly",
    "partial",
    "required",
    "pick",
    "omit",
)


def _optional_never_members(props: Sequence[tuple[str, bool]]) -> str:
    """Join optional ``never`` properties. *readonly* is per property, not required."""
    parts: list[str] = []
    for name, readonly in props:
        prefix = "readonly " if readonly else ""
        parts.append(f"{prefix}{name}?: never")
    return "; ".join(parts)


def _brand_value_text(
    *,
    form: str,
    members: str,
    type_name: str,
) -> tuple[str, str]:
    """Return ``(prelude, value expression)`` for one brand-only empty type."""
    if form == "inline":
        return "", "{ " + members + " }"
    if form == "alias":
        return f"type {type_name} = {{ {members} }};\n", type_name
    if form == "interface":
        return f"interface {type_name} {{ {members} }}\n", type_name
    raise ValueError(f"unknown brand form {form!r}")


def brand_dictionary_case(
    *,
    form: str,
    writing: str,
    readonly: bool = False,
    props: Sequence[tuple[str, bool]] | None = None,
    label: str | None = None,
) -> BrandDictionaryCase:
    """Dictionary whose value is a brand-only empty type.

    The property name is generated. ``readonly`` may be present on a
    property and is not required. ``form`` is an object type written at
    the value (``inline``), a same-file alias of that object type, or a
    same-file interface.
    """
    if props is None:
        props = ((fresh_ident("slot"), readonly),)
    type_name = fresh_ident("Brand")
    alias = fresh_ident("Dict")
    key = fresh_ident("key")
    mapped = fresh_ident("K")
    members = _optional_never_members(props)
    prelude, value = _brand_value_text(
        form=form, members=members, type_name=type_name
    )
    if label is None:
        modifier = "readonly" if readonly else "plain"
        label = f"{form}-{modifier}-{writing}"
    if writing == "record":
        source = prelude + f"type {alias} = Record<string, {value}>;\n"
        return BrandDictionaryCase(label, writing, source, None)
    if writing == "index":
        source = (
            prelude + f"type {alias} = {{ [{key}: string]: {value} }};\n"
        )
        return BrandDictionaryCase(label, writing, source, None)
    if writing == "mapped":
        source = (
            prelude + f"type {alias} = {{ [{mapped} in string]: {value} }};\n"
        )
        return BrandDictionaryCase(label, writing, source, None)
    if writing not in _BRAND_WRAPPERS:
        raise ValueError(f"unknown brand writing {writing!r}")
    inner = f"Record<string, {value}>"
    head = {
        "readonly": "Readonly",
        "partial": "Partial",
        "required": "Required",
        "pick": "Pick",
        "omit": "Omit",
    }[writing]
    if writing == "pick":
        body = f"Pick<{inner}, string>"
    elif writing == "omit":
        body = f"Omit<{inner}, never>"
    else:
        body = f"{head}<{inner}>"
    source = prelude + f"type {alias} = {body};\n"
    wrapper = WrapperDictionarySnippet(
        source=source,
        writing_spans=(_span_of(source, head),),
        inner_spans=(_span_of(source, inner),),
    )
    return BrandDictionaryCase(label, writing, source, wrapper)


def brand_only_dictionary_cases() -> tuple[BrandDictionaryCase, ...]:
    """Shape × writing matrix for a brand-only empty dictionary value.

    Shapes: optional property of type ``never``; property name generated;
    one arm with ``readonly`` and one without; an object type, a same-file
    alias of that object type, and a same-file interface. A further alias
    and interface arm uses two such members so every member, not a single
    fixed property, is the contract. Writings: Record, an index signature,
    a mapped dictionary, and Readonly, Partial, Required, Pick, and Omit.
    """
    cases: list[BrandDictionaryCase] = []
    for form in _BRAND_FORMS:
        for readonly in (True, False):
            for writing in _BRAND_WRITINGS:
                cases.append(
                    brand_dictionary_case(
                        form=form, writing=writing, readonly=readonly
                    )
                )
    mixed = (
        (fresh_ident("slot"), True),
        (fresh_ident("tag"), False),
    )
    for form in ("alias", "interface"):
        cases.append(
            brand_dictionary_case(
                form=form,
                writing="record",
                props=mixed,
                label=f"{form}-every-record",
            )
        )
    return tuple(cases)


def snippet_record_of_brand_only_empty(*, twin: bool = False) -> str:
    """Same-file alias of an optional-never object type, used as Record.

    The property name is generated. The public arm carries ``readonly``;
    the twin arm does not.
    """
    return brand_dictionary_case(
        form="alias",
        writing="record",
        readonly=not twin,
    ).source


def snippet_named_data_beside_optional_never(
    *,
    form: str,
    writing: str = "record",
) -> str:
    """Named data type that also has an optional ``never`` property.

    The extra member is a ``string`` field, so the value is not brand-only
    empty. Property names are generated.
    """
    data = fresh_ident("field")
    brand = fresh_ident("slot")
    type_name = fresh_ident("Row")
    alias = fresh_ident("Dict")
    key = fresh_ident("key")
    mapped = fresh_ident("K")
    members = f"{data}: string; {brand}?: never"
    if form == "alias":
        prelude = f"type {type_name} = {{ {members} }};\n"
    elif form == "interface":
        prelude = f"interface {type_name} {{ {members} }}\n"
    else:
        raise ValueError(f"unknown data form {form!r}")
    if writing == "record":
        body = f"Record<string, {type_name}>"
    elif writing == "index":
        body = f"{{ [{key}: string]: {type_name} }}"
    elif writing == "mapped":
        body = f"{{ [{mapped} in string]: {type_name} }}"
    elif writing == "readonly":
        body = f"Readonly<Record<string, {type_name}>>"
    else:
        raise ValueError(f"unknown data writing {writing!r}")
    return prelude + f"type {alias} = {body};\n"


def snippet_record_of_union_unknown(*, twin: bool = False) -> str:
    alias = "A" if not twin else fresh_ident("Dict")
    return f"type {alias} = Record<string, string | unknown>;\n"


def snippet_record_of_unknown_alias(*, twin: bool = False) -> str:
    escape = "Escape" if not twin else fresh_ident("Unk")
    alias = "A" if not twin else fresh_ident("Dict")
    return (
        f"type {escape} = unknown;\n"
        f"type {alias} = Record<string, {escape}>;\n"
    )


def snippet_readonly_partial_required_of_record(
    *, twin: bool = False
) -> WrapperDictionarySnippet:
    alias = "A" if not twin else fresh_ident("Dict")
    source = (
        f"type {alias} = Readonly<Partial<Required<(Record<string, unknown>)>>>;\n"
    )
    return WrapperDictionarySnippet(
        source=source,
        writing_spans=(_span_of(source, "Readonly"),),
        inner_spans=(_span_of(source, "Record<string, unknown>"),),
    )


def snippet_partial_of_unsafe_dictionary(
    *, twin: bool = False
) -> WrapperDictionarySnippet:
    alias = "A" if not twin else fresh_ident("Dict")
    source = f"type {alias} = Partial<Record<string, unknown>>;\n"
    return WrapperDictionarySnippet(
        source=source,
        writing_spans=(_span_of(source, "Partial"),),
        inner_spans=(_span_of(source, "Record<string, unknown>"),),
    )


def snippet_required_of_unsafe_dictionary(
    *, twin: bool = False
) -> WrapperDictionarySnippet:
    alias = "A" if not twin else fresh_ident("Dict")
    source = f"type {alias} = Required<Record<string, unknown>>;\n"
    return WrapperDictionarySnippet(
        source=source,
        writing_spans=(_span_of(source, "Required"),),
        inner_spans=(_span_of(source, "Record<string, unknown>"),),
    )


def snippet_pick_of_unsafe_dictionary(
    *, twin: bool = False
) -> WrapperDictionarySnippet:
    source_name = "Source" if not twin else fresh_ident("Base")
    alias = "A" if not twin else fresh_ident("Picked")
    first = f"type {source_name} = Record<string, unknown>;\n"
    second = f"type {alias} = Pick<{source_name}, string>;\n"
    source = first + second
    return WrapperDictionarySnippet(
        source=source,
        writing_spans=(_span_of(source, "Pick"),),
        inner_spans=((0, len(first)),),
    )


def snippet_omit_of_unsafe_dictionary(
    *, twin: bool = False
) -> WrapperDictionarySnippet:
    source_name = "Source" if not twin else fresh_ident("Base")
    alias = "A" if not twin else fresh_ident("Omitted")
    first = f"type {source_name} = Record<string, unknown>;\n"
    second = f"type {alias} = Omit<{source_name}, never>;\n"
    source = first + second
    return WrapperDictionarySnippet(
        source=source,
        writing_spans=(_span_of(source, "Omit"),),
        inner_spans=((0, len(first)),),
    )


def snippet_record_of_named_command(*, twin: bool = False) -> str:
    command = "Command" if not twin else fresh_ident("Op")
    alias = "Commands" if not twin else fresh_ident("Table")
    return (
        f"type {command} = () => void;\n"
        f"type {alias} = Record<string, {command}>;\n"
    )


def snippet_index_of_named_command(*, twin: bool = False) -> str:
    command = "Command" if not twin else fresh_ident("Op")
    alias = "Indexed" if not twin else fresh_ident("Idx")
    key = "key" if not twin else fresh_ident("slot")
    return (
        f"type {command} = () => void;\n"
        f"type {alias} = {{ [{key}: string]: {command} }};\n"
    )


def snippet_mapped_of_named_command(*, twin: bool = False) -> str:
    command = "Command" if not twin else fresh_ident("Op")
    alias = "Mapped" if not twin else fresh_ident("Mapd")
    key = "K" if not twin else fresh_ident("Key")
    return (
        f"type {command} = () => void;\n"
        f"type {alias} = {{ [{key} in string]: {command} }};\n"
    )


def snippet_nested_object_unknown_field_dictionary(*, twin: bool = False) -> str:
    alias = "Allowed" if not twin else fresh_ident("Nest")
    field = "payload" if not twin else fresh_ident("body")
    return f"type {alias} = Record<string, {{ {field}: unknown }}>;\n"


def snippet_map_readonly_map_weak_map(*, twin: bool = False) -> str:
    first = "A" if not twin else fresh_ident("One")
    second = "B" if not twin else fresh_ident("Two")
    third = "C" if not twin else fresh_ident("Three")
    return (
        f"type {first} = Map<string, unknown>;\n"
        f"type {second} = ReadonlyMap<string, unknown>;\n"
        f"type {third} = WeakMap<object, unknown>;\n"
    )


def snippet_generic_record_constraints(*, twin: bool = False) -> str:
    fn = "run" if not twin else fresh_ident("go")
    fn_param = "T" if not twin else fresh_ident("In")
    input_name = "input" if not twin else fresh_ident("arg")
    cls = "Store" if not twin else fresh_ident("Box")
    cls_param = "T" if not twin else fresh_ident("Held")
    alias = "Deep" if not twin else fresh_ident("Nest")
    alias_param = "T" if not twin else fresh_ident("Inner")
    return (
        f"function {fn}<{fn_param} extends Record<string, unknown>>"
        f"({input_name}: {fn_param}) {{}}\n"
        f"declare class {cls}<{cls_param} extends Record<string, unknown>> "
        f"{{ read(): {cls_param} }}\n"
        f"type {alias}<{alias_param} extends Record<string, unknown>> = "
        f"{alias_param};\n"
    )


def snippet_shadowed_non_language_record(*, twin: bool = False) -> str:
    key = "K" if not twin else fresh_ident("Key")
    val = "V" if not twin else fresh_ident("Val")
    field_k = "key" if not twin else fresh_ident("slot")
    field_v = "value" if not twin else fresh_ident("held")
    alias = "A" if not twin else fresh_ident("Dict")
    return (
        f"type Record<{key}, {val}> = {{ {field_k}: {key}; {field_v}: {val} }};\n"
        f"type {alias} = Record<string, unknown>;\n"
    )


def write_imported_record(ws: Workspace, *, twin: bool = False) -> Path:
    mod = fresh_ident("local")
    exported = "Record"
    ws.write(
        f"{mod}.ts",
        f"export type {exported}<K, V> = {{ key: K; value: V }};\n",
    )
    alias = "A" if not twin else fresh_ident("Dict")
    source = (
        f'import {{ {exported} }} from "./{mod}";\n'
        f"type {alias} = {exported}<string, unknown>;\n"
    )
    return write_f04_source(ws, source, prefix="imp-rec")


def write_imported_object_alias(ws: Workspace, *, twin: bool = False) -> Path:
    mod = fresh_ident("types")
    exported = "Payload" if not twin else fresh_ident("Obj")
    ws.write(f"{mod}.ts", f"export type {exported} = object;\n")
    name = "accept" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    source = (
        f'import {{ {exported} }} from "./{mod}";\n'
        f"function {name}({param}: {exported}) {{}}\n"
    )
    return write_f04_source(ws, source, prefix="imp-obj")


# ---------------------------------------------------------------------------
# K. Same-file resolution boundary
# ---------------------------------------------------------------------------


def snippet_inner_object_alias_parameter(*, twin: bool = False) -> str:
    outer = "outer" if not twin else fresh_ident("wrap")
    alias = "Payload" if not twin else fresh_ident("Body")
    name = "consume" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"function {outer}() {{\n"
        f"  type {alias} = object;\n"
        f"  function {name}({param}: {alias}) {{}}\n"
        f"}}\n"
    )


def snippet_forward_object_alias_parameter(*, twin: bool = False) -> str:
    alias = "Payload" if not twin else fresh_ident("Body")
    name = "consume" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"function {name}({param}: {alias}) {{}}\n"
        f"type {alias} = object;\n"
    )


def snippet_later_inner_object_alias_does_not_leak(*, twin: bool = False) -> str:
    first = "one" if not twin else fresh_ident("left")
    second = "two" if not twin else fresh_ident("right")
    alias = "Payload" if not twin else fresh_ident("Body")
    name = "consume" if not twin else fresh_ident("take")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"function {first}() {{ type {alias} = object; }}\n"
        f"function {second}() {{ function {name}({param}: {alias}) {{}} }}\n"
    )
