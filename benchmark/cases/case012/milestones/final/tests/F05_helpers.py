# feature: F05
"""Observation helpers for runtime typeof, Reflect apply/get, and module mocking.

Import side effects: none. Process spawn and filesystem writes happen only
when a caller invokes a function below.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from _harness import (
    GENERIC_PLUGIN_NAME,
    HarnessError,
    RunResult,
    Workspace,
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
    rule_fired,
)
from F02_helpers import assert_fix_preserves_source
from F04_helpers import diagnostic_offset, rule_diagnostics

F05_RULE_NAMES: tuple[str, ...] = (
    "no-runtime-typeof",
    "no-reflect-apply",
    "no-reflect-get",
    "no-module-mocking",
)

RULE_TYPEOF = "no-runtime-typeof"
RULE_APPLY = "no-reflect-apply"
RULE_GET = "no-reflect-get"
RULE_MOCK = "no-module-mocking"


@dataclass(frozen=True)
class NestedTypeofSnippet:
    """Predicate file with a nested inner typeof, optionally a direct typeof too."""

    source: str
    nested_span: tuple[int, int]
    direct_span: tuple[int, int] | None = None


def lint_f05(
    ws: Workspace,
    files: Sequence[str | Path],
    specifier: str | Path,
    *,
    rules: Sequence[str] = F05_RULE_NAMES,
    allow_in_type_guards: bool | None = None,
    fix: bool = False,
) -> RunResult:
    """Register lint-policy; enable *rules* at error; optional flag and ``--fix``.

    ``allow_in_type_guards is None`` omits the option. ``True`` / ``False``
    set ``no-runtime-typeof`` to ``["error", {"allowInTypeGuards": <bool>}]``.
    Never pass ``{}`` as a stand-in for omit.
    """
    ensure_host_plugin_modules(ws)
    print(
        f"lint-f05 specifier={specifier} rules={list(rules)} "
        f"allow_in_type_guards={allow_in_type_guards} "
        f"fix={fix} files={list(files)}",
        flush=True,
    )
    plugin = generic_plugin(specifier=specifier, root=ws.root)
    mapping: dict[str, object] = {
        rule_key(GENERIC_PLUGIN_NAME, name): "error" for name in rules
    }
    if allow_in_type_guards is not None:
        mapping[rule_key(GENERIC_PLUGIN_NAME, RULE_TYPEOF)] = [
            "error",
            {"allowInTypeGuards": allow_in_type_guards},
        ]
    return ws.lint(files, plugins=[plugin], rules=mapping, fix=fix)


def write_f05_source(
    ws: Workspace,
    source: str,
    *,
    prefix: str = "f05",
    ext: str = "ts",
) -> Path:
    if ext not in ("ts", "js"):
        raise HarnessError(f"F05 source ext must be ts or js; got {ext!r}")
    rel = f"{prefix}-{fresh_ident('s')}.{ext}"
    print(f"write {rel}", flush=True)
    return ws.write(rel, source)


def lint_f05_source(
    ws: Workspace,
    specifier: str | Path,
    source: str,
    *,
    prefix: str = "f05",
    ext: str = "ts",
    allow_in_type_guards: bool | None = None,
    fix: bool = False,
    rules: Sequence[str] = F05_RULE_NAMES,
) -> tuple[Path, RunResult]:
    path = write_f05_source(ws, source, prefix=prefix, ext=ext)
    result = lint_f05(
        ws,
        [path],
        specifier,
        rules=rules,
        allow_in_type_guards=allow_in_type_guards,
        fix=fix,
    )
    print(f"lint {path.name} exit={result.returncode}", flush=True)
    return path, result


def assert_silent_f05(result: RunResult, rule_name: str) -> None:
    """Classified success and no finding from *rule_name* (F05 rules only)."""
    generic = lint_policy_findings(result)
    effect = effect_plugin_findings(result)
    print(
        f"assert-silent-f05 {rule_name} exit={result.returncode} "
        f"generic={generic} effect={effect}",
        flush=True,
    )
    if rule_fired(generic, rule_name):
        raise AssertionError(
            f"rule {rule_name} must not fire; got {generic}"
        )
    if result.returncode != 0:
        raise HarnessError(
            "silence with only F05 rules enabled requires classified success; "
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


def run_f05_fix(
    ws: Workspace,
    specifier: str | Path,
    source: str,
    rule_name: str,
    *,
    prefix: str = "fix",
    ext: str = "ts",
) -> RunResult:
    """Lint with host ``--fix``; require unchanged bytes and a firing diagnostic."""
    path = write_f05_source(ws, source, prefix=prefix, ext=ext)
    before = path.read_bytes()
    result = lint_f05(ws, [path], specifier, fix=True)
    print(f"fix-mode {path.name} rule={rule_name}", flush=True)
    assert_fix_preserves_source(path, before, result, rule_name)
    assert_only_rule(result, rule_name)
    return result


def _unique_span(source: str, fragment: str) -> tuple[int, int]:
    start = source.find(fragment)
    if start < 0:
        raise HarnessError(
            f"fragment {fragment!r} not found in source {source!r}"
        )
    again = source.find(fragment, start + 1)
    if again >= 0:
        raise HarnessError(
            f"fragment {fragment!r} is not unique in source {source!r}"
        )
    return start, start + len(fragment)


def _offset_in_span(offset: int, span: tuple[int, int]) -> bool:
    start, end = span
    return start <= offset < end


def assert_typeof_finding_in_span(
    source: str,
    result: RunResult,
    span: tuple[int, int],
) -> None:
    """``no-runtime-typeof`` fired and at least one finding sits in *span*."""
    assert_fired(result, RULE_TYPEOF)
    items = rule_diagnostics(result, RULE_TYPEOF)
    matched = []
    for item in items:
        offset = diagnostic_offset(source, item)
        if _offset_in_span(offset, span):
            matched.append(item)
    print(
        f"typeof-in-span matched={len(matched)} span={span}",
        flush=True,
    )
    if not matched:
        raise AssertionError(
            "no-runtime-typeof must identify the nested typeof construct; "
            f"span={span} source={source!r}"
        )


def assert_nested_typeof_reported_direct_silent(
    source: str,
    result: RunResult,
    *,
    direct_span: tuple[int, int],
    nested_span: tuple[int, int],
) -> None:
    """Combined predicate: nested typeof reported; direct typeof silent.

    Hard-fails when a diagnostic is missing line/column. Does not pin
    message text or a finding count. Nested is later in the source than
    direct, so a nested-span finding's offset is greater than the direct
    span's start.
    """
    assert_fired(result, RULE_TYPEOF)
    items = rule_diagnostics(result, RULE_TYPEOF)
    nested_offsets: list[int] = []
    for item in items:
        offset = diagnostic_offset(source, item)
        if _offset_in_span(offset, direct_span):
            raise AssertionError(
                "no-runtime-typeof must stay silent on the direct typeof "
                f"in the predicate; offset={offset} direct_span={direct_span} "
                f"source={source!r}"
            )
        if _offset_in_span(offset, nested_span):
            nested_offsets.append(offset)
    print(
        f"nested-direct nested_n={len(nested_offsets)} "
        f"direct_span={direct_span} nested_span={nested_span}",
        flush=True,
    )
    if not nested_offsets:
        raise AssertionError(
            "no-runtime-typeof must identify the nested inner typeof; "
            f"nested_span={nested_span} source={source!r}"
        )
    nested_key = min(nested_offsets)
    if nested_key <= direct_span[0]:
        raise AssertionError(
            "finding in the nested typeof must have a greater sortable "
            "offset than the earlier direct typeof span; "
            f"nested={nested_key} direct_start={direct_span[0]}"
        )


# ---------------------------------------------------------------------------
# A. Representation typeof
# ---------------------------------------------------------------------------


def snippet_typeof_string_if(*, twin: bool = False) -> str:
    param = "input" if not twin else fresh_ident("arg")
    use = "use" if not twin else fresh_ident("take")
    return f'if (typeof {param} === "string") {use}({param});\n'


def snippet_typeof_input_string(*, twin: bool = False) -> str:
    param = "input" if not twin else fresh_ident("arg")
    return f'typeof {param} === "string";\n'


def snippet_typeof_other_representation(*, twin: bool = False) -> str:
    param = "input" if not twin else fresh_ident("arg")
    return f'typeof {param} === "number";\n'


def snippet_typeof_compared_to_value_undefined(*, twin: bool = False) -> str:
    param = "input" if not twin else fresh_ident("arg")
    return f"typeof {param} === undefined;\n"


def snippet_typeof_string_reversed(*, twin: bool = False) -> str:
    param = "input" if not twin else fresh_ident("arg")
    return f'"string" === typeof {param};\n'


# ---------------------------------------------------------------------------
# B. Existence probes
# ---------------------------------------------------------------------------


def snippet_typeof_identifier_undefined(*, twin: bool = False) -> str:
    name = "document" if not twin else fresh_ident("binding")
    return f'typeof {name} === "undefined";\n'


def snippet_typeof_member_undefined(*, twin: bool = False) -> str:
    if not twin:
        return 'typeof globalThis.crypto === "undefined";\n'
    obj = fresh_ident("root")
    prop = fresh_ident("slot")
    return f'typeof {obj}.{prop} === "undefined";\n'


def snippet_typeof_undefined_reversed(*, twin: bool = False) -> str:
    name = "document" if not twin else fresh_ident("binding")
    return f'"undefined" === typeof {name};\n'


def snippet_typeof_undefined_loose(
    *, twin: bool = False, name: str | None = None
) -> str:
    ident = name if name is not None else (
        "document" if not twin else fresh_ident("binding")
    )
    return f'typeof {ident} == "undefined";\n'


def snippet_typeof_other_representation_loose(
    *, twin: bool = False, name: str | None = None
) -> str:
    """Live baseline for the loose existence probe: same operator, other string."""
    ident = name if name is not None else (
        "document" if not twin else fresh_ident("binding")
    )
    return f'typeof {ident} == "string";\n'


def snippet_typeof_undefined_strict_inequality(
    *, twin: bool = False, name: str | None = None
) -> str:
    ident = name if name is not None else (
        "localStorage" if not twin else fresh_ident("binding")
    )
    return f'typeof {ident} !== "undefined";\n'


def snippet_typeof_other_representation_strict_inequality(
    *, twin: bool = False, name: str | None = None
) -> str:
    """Live baseline for the strict-inequality existence probe."""
    ident = name if name is not None else (
        "localStorage" if not twin else fresh_ident("binding")
    )
    return f'typeof {ident} !== "string";\n'


def snippet_typeof_undefined_loose_inequality(
    *, twin: bool = False, name: str | None = None
) -> str:
    ident = name if name is not None else (
        "document" if not twin else fresh_ident("binding")
    )
    return f'typeof {ident} != "undefined";\n'


def snippet_typeof_other_representation_loose_inequality(
    *, twin: bool = False, name: str | None = None
) -> str:
    """Live baseline for the loose-inequality existence probe."""
    ident = name if name is not None else (
        "document" if not twin else fresh_ident("binding")
    )
    return f'typeof {ident} != "string";\n'


def snippet_both_existence_probes() -> str:
    return (
        'typeof document === "undefined";\n'
        'typeof globalThis.crypto === "undefined";\n'
        'typeof localStorage !== "undefined";\n'
    )


# ---------------------------------------------------------------------------
# C / D. allowInTypeGuards
# ---------------------------------------------------------------------------


def snippet_type_predicate_typeof(*, twin: bool = False) -> str:
    name = "isString" if not twin else fresh_ident("isKind")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"function {name}({param}: unknown): {param} is string {{\n"
        f'  return typeof {param} === "string";\n'
        f"}}\n"
    )


def snippet_non_predicate_parse_typeof(*, twin: bool = False) -> str:
    name = "parse" if not twin else fresh_ident("read")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"function {name}({param}: unknown): string {{\n"
        f'  if (typeof {param} === "string") return {param};\n'
        f'  throw new Error("bad");\n'
        f"}}\n"
    )


def snippet_assertion_function_typeof(*, twin: bool = False) -> str:
    name = "assertString" if not twin else fresh_ident("assertKind")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"function {name}({param}: unknown): asserts {param} is string {{\n"
        f'  if (typeof {param} === "string") return;\n'
        f'  throw new Error("bad");\n'
        f"}}\n"
    )


def snippet_assertion_function_typeof_strict_inequality(
    *, twin: bool = False
) -> str:
    name = "assertString" if not twin else fresh_ident("assertKind")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"function {name}({param}: unknown): asserts {param} is string {{\n"
        f'  if (typeof {param} !== "string") throw new Error("bad");\n'
        f"}}\n"
    )


def snippet_arrow_predicate_typeof(*, twin: bool = False) -> str:
    name = "isString" if not twin else fresh_ident("isKind")
    param = "value" if not twin else fresh_ident("arg")
    return (
        f"const {name} = ({param}: unknown): {param} is string => "
        f'typeof {param} === "string";\n'
    )


def snippet_non_value_is_string_predicate(*, twin: bool = False) -> str:
    name = "isNumber" if not twin else fresh_ident("isKind")
    subject = "input" if not twin else fresh_ident("item")
    target = "number" if not twin else "boolean"
    return (
        f"function {name}({subject}: unknown): {subject} is {target} {{\n"
        f'  return typeof {subject} === "{target}";\n'
        f"}}\n"
    )


def snippet_nested_inner_typeof_in_predicate() -> NestedTypeofSnippet:
    source = (
        "function isString(value: unknown): value is string {\n"
        '  const check = () => typeof value === "string";\n'
        "  return check();\n"
        "}\n"
    )
    nested = _unique_span(source, '() => typeof value === "string"')
    return NestedTypeofSnippet(source=source, nested_span=nested)


def snippet_direct_and_nested_typeof_in_predicate() -> NestedTypeofSnippet:
    source = (
        "function isString(value: unknown): value is string {\n"
        '  const seenDirect = typeof value === "string";\n'
        '  const nestedInner = () => typeof value === "string";\n'
        "  return seenDirect && nestedInner();\n"
        "}\n"
    )
    direct = _unique_span(source, 'const seenDirect = typeof value === "string"')
    nested = _unique_span(source, '() => typeof value === "string"')
    if nested[0] <= direct[0]:
        raise HarnessError(
            "combined predicate must place the nested typeof later than "
            f"the direct typeof; direct={direct} nested={nested}"
        )
    return NestedTypeofSnippet(
        source=source, nested_span=nested, direct_span=direct
    )


# ---------------------------------------------------------------------------
# E. Reflect.apply
# ---------------------------------------------------------------------------


def snippet_computed_reflect_apply(*, twin: bool = False) -> str:
    op = "operation" if not twin else fresh_ident("op")
    owner = "owner" if not twin else fresh_ident("own")
    args = "args" if not twin else fresh_ident("argv")
    return f'Reflect["apply"]({op}, {owner}, {args});\n'


def snippet_operation_apply(*, twin: bool = False) -> str:
    op = "operation" if not twin else fresh_ident("op")
    owner = "owner" if not twin else fresh_ident("own")
    args = "args" if not twin else fresh_ident("argv")
    return f"{op}.apply({owner}, {args});\n"


def snippet_shadowed_reflect_apply(*, twin: bool = False) -> str:
    result = "1" if not twin else "2"
    return (
        f"const Reflect = {{ apply() {{ return {result}; }} }}; "
        f"Reflect.apply();\n"
    )


def snippet_parameter_named_reflect_apply(*, twin: bool = False) -> str:
    name = "invoke" if not twin else fresh_ident("call")
    return f"function {name}(Reflect) {{ return Reflect.apply(); }}\n"


# ---------------------------------------------------------------------------
# F. Reflect.get
# ---------------------------------------------------------------------------


def snippet_computed_reflect_get(*, twin: bool = False) -> str:
    owner = "owner" if not twin else fresh_ident("own")
    key = "key" if not twin else fresh_ident("slot")
    return f'Reflect["get"]({owner}, {key});\n'


def snippet_ordinary_property_access(*, twin: bool = False) -> str:
    owner = "owner" if not twin else fresh_ident("own")
    key = "key" if not twin else fresh_ident("slot")
    prop = "property" if not twin else fresh_ident("field")
    return f"{owner}[{key}];\n{owner}.{prop};\n"


def snippet_reflect_set(*, twin: bool = False) -> str:
    owner = "owner" if not twin else fresh_ident("own")
    key = "key" if not twin else fresh_ident("slot")
    value = "value" if not twin else fresh_ident("put")
    return f"Reflect.set({owner}, {key}, {value});\n"


def snippet_shadowed_reflect_get(*, twin: bool = False) -> str:
    result = "1" if not twin else "2"
    return (
        f"const Reflect = {{ get() {{ return {result}; }} }}; "
        f"Reflect.get();\n"
    )


def snippet_parameter_named_reflect_get(*, twin: bool = False) -> str:
    name = "read" if not twin else fresh_ident("take")
    return f"function {name}(Reflect) {{ return Reflect.get(); }}\n"


# ---------------------------------------------------------------------------
# G. Module mocking fires
# ---------------------------------------------------------------------------


def _module_path(*, twin: bool) -> str:
    return "./user-store" if not twin else f"./{fresh_ident('mod')}"


def snippet_jest_mock(*, twin: bool = False) -> str:
    return f'jest.mock("{_module_path(twin=twin)}");\n'


def snippet_identifier_do_mock(*, twin: bool = False) -> str:
    return f'vi.doMock("{_module_path(twin=twin)}");\n'


def snippet_computed_do_mock(*, twin: bool = False) -> str:
    return f'vi["doMock"]("{_module_path(twin=twin)}");\n'


def snippet_jest_unstable_mock_module(*, twin: bool = False) -> str:
    return f'jest.unstable_mockModule("{_module_path(twin=twin)}");\n'


def snippet_named_import_vi_from_vitest_mock(*, twin: bool = False) -> str:
    return (
        'import { vi } from "vitest";\n'
        f'vi.mock("{_module_path(twin=twin)}");\n'
    )


def snippet_aliased_import_vi_from_vitest_mock(*, twin: bool = False) -> str:
    alias = "mockVi" if not twin else fresh_ident("api")
    return (
        f'import {{ vi as {alias} }} from "vitest";\n'
        f'{alias}.mock("{_module_path(twin=twin)}");\n'
    )


def snippet_named_import_jest_from_jest_globals_mock(*, twin: bool = False) -> str:
    return (
        'import { jest } from "@jest/globals";\n'
        f'jest.mock("{_module_path(twin=twin)}");\n'
    )


def snippet_aliased_import_jest_from_jest_globals_mock(*, twin: bool = False) -> str:
    alias = "mockJest" if not twin else fresh_ident("api")
    return (
        f'import {{ jest as {alias} }} from "@jest/globals";\n'
        f'{alias}.mock("{_module_path(twin=twin)}");\n'
    )


# ---------------------------------------------------------------------------
# H. Module mocking silences
# ---------------------------------------------------------------------------


def snippet_vi_spy_on(*, twin: bool = False) -> str:
    store = "store" if not twin else fresh_ident("svc")
    method = "save" if not twin else fresh_ident("write")
    return f'vi.spyOn({store}, "{method}");\n'


def snippet_jest_spy_on(*, twin: bool = False) -> str:
    store = "store" if not twin else fresh_ident("svc")
    method = "save" if not twin else fresh_ident("write")
    return f'jest.spyOn({store}, "{method}");\n'


def snippet_in_memory_collaborator(*, twin: bool = False) -> str:
    cls = "InMemoryUserStore" if not twin else fresh_ident("Store")
    return f"class {cls} {{}}\nnew {cls}();\n"


def snippet_local_object_named_vi_mock(*, twin: bool = False) -> str:
    extra = "" if not twin else f"const {fresh_ident('other')} = 1;\n"
    return f"{extra}const vi = {{ mock() {{}} }}; vi.mock();\n"


def snippet_parameter_named_jest_mock(*, twin: bool = False) -> str:
    name = "test" if not twin else fresh_ident("run")
    return f"function {name}(jest) {{ jest.mock(); }}\n"


def write_project_module_helper_mock(
    ws: Workspace,
    *,
    twin: bool = False,
) -> Path:
    """Write a project helper module and an importer that calls its ``mock``."""
    mod = fresh_ident("helpers")
    exported = "vi" if not twin else fresh_ident("api")
    local = "localVi" if not twin else fresh_ident("local")
    helper = f"export const {exported} = {{ mock() {{}} }};\n"
    helper_path = f"{mod}.js"
    print(f"write project-helper {helper_path} export={exported}", flush=True)
    ws.write(helper_path, helper)
    source = (
        f'import {{ {exported} as {local} }} from "./{mod}";\n'
        f'{local}.mock("{_module_path(twin=True)}");\n'
    )
    return write_f05_source(ws, source, prefix="proj-mock", ext="ts")
