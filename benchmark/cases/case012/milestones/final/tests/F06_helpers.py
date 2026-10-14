# feature: F06
"""Observation helpers for locally owned shape names and readable spacing.

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
    assert_no_plugin_findings,
    assert_only_rule,
    effect_plugin_findings,
    ensure_host_plugin_modules,
    fresh_ident,
    rule_fired,
    snippet_no_shape_in_symbol_names,
    snippet_require_readable_spacing,
)
from F02_helpers import assert_fix_preserves_source
from F03_helpers import assert_classified_not_fired
from F04_helpers import diagnostic_offset, rule_diagnostics

F06_RULE_NAMES: tuple[str, ...] = (
    "no-shape-in-symbol-names",
    "require-readable-spacing",
)

RULE_SHAPE = "no-shape-in-symbol-names"
RULE_SPACING = "require-readable-spacing"

_ALLOWED_EXTS = frozenset({"ts", "js", "tsx", "jsx"})


@dataclass(frozen=True)
class SpacingSnippet:
    """Source plus unique markers around a named insert or preserve site."""

    source: str
    left: str
    right: str


@dataclass(frozen=True)
class DocsSnippet:
    """Two declarations with a documentation comment attached to the later one."""

    source: str
    previous: str
    docs: str
    following: str


@dataclass(frozen=True)
class NeighborSnippet:
    """Already-spaced file with one allowed binding and one owned shape name."""

    source: str
    allowed_span: tuple[int, int]
    shape_span: tuple[int, int]


def lint_f06(
    ws: Workspace,
    files: Sequence[str | Path],
    specifier: str | Path,
    *,
    rules: Sequence[str] = F06_RULE_NAMES,
    fix: bool = False,
) -> RunResult:
    """Register lint-policy; enable *rules* at error; optional host ``--fix``.

    No options parameter. Local taste is outside the scored surface.
    """
    ensure_host_plugin_modules(ws)
    print(
        f"lint-f06 specifier={specifier} rules={list(rules)} "
        f"fix={fix} files={list(files)}",
        flush=True,
    )
    plugin = generic_plugin(specifier=specifier, root=ws.root)
    mapping = {rule_key(GENERIC_PLUGIN_NAME, name): "error" for name in rules}
    return ws.lint(files, plugins=[plugin], rules=mapping, fix=fix)


def write_f06_source(
    ws: Workspace,
    source: str,
    *,
    prefix: str = "f06",
    ext: str = "ts",
) -> Path:
    if ext not in _ALLOWED_EXTS:
        raise HarnessError(f"F06 source ext must be ts, js, tsx, or jsx; got {ext!r}")
    rel = f"{prefix}-{fresh_ident('s')}.{ext}"
    print(f"write {rel}", flush=True)
    return ws.write(rel, source)


def lint_f06_source(
    ws: Workspace,
    specifier: str | Path,
    source: str,
    *,
    prefix: str = "f06",
    ext: str = "ts",
    fix: bool = False,
    rules: Sequence[str] = F06_RULE_NAMES,
) -> tuple[Path, RunResult]:
    path = write_f06_source(ws, source, prefix=prefix, ext=ext)
    result = lint_f06(ws, [path], specifier, rules=rules, fix=fix)
    print(f"lint {path.name} exit={result.returncode}", flush=True)
    return path, result


def assert_silent_f06(result: RunResult, rule_name: str) -> None:
    """Classified success and no finding from *rule_name* (F06 rules only)."""
    generic = lint_policy_findings(result)
    effect = effect_plugin_findings(result)
    print(
        f"assert-silent-f06 {rule_name} exit={result.returncode} "
        f"generic={generic} effect={effect}",
        flush=True,
    )
    if rule_fired(generic, rule_name):
        raise AssertionError(
            f"rule {rule_name} must not fire; got {generic}"
        )
    if result.returncode != 0:
        raise HarnessError(
            "silence with only F06 rules enabled requires classified success; "
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


def read_source_bytes(path: str | Path) -> bytes:
    src = Path(path)
    try:
        return src.read_bytes()
    except OSError as exc:
        raise HarnessError(f"cannot read source after lint: {exc}") from exc


def read_source_text(path: str | Path) -> str:
    data = read_source_bytes(path)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HarnessError(f"source is not valid UTF-8: {exc}") from exc


def non_whitespace(text: str) -> str:
    return "".join(ch for ch in text if not ch.isspace())


def assert_whitespace_only_change(before: str, after: str) -> None:
    print(
        f"whitespace-only before_len={len(before)} after_len={len(after)} "
        f"changed={before != after}",
        flush=True,
    )
    if before == after:
        raise AssertionError(
            "host fix mode must insert a blank line; source bytes were unchanged"
        )
    if non_whitespace(before) != non_whitespace(after):
        raise AssertionError(
            "host fix mode must insert whitespace only; non-whitespace bytes changed"
        )


def _require_unique_marker(source: str, marker: str, *, label: str) -> int:
    start = source.find(marker)
    if start < 0:
        raise HarnessError(
            f"{label} marker {marker!r} is absent from source {source!r}"
        )
    again = source.find(marker, start + 1)
    if again >= 0:
        raise HarnessError(
            f"{label} marker {marker!r} is not unique in source {source!r}"
        )
    return start


def blank_lines_between(source: str, left: str, right: str) -> int:
    """Count empty or whitespace-only lines between unique *left* and *right*.

    Raises if a marker is absent or not unique. Never returns 0 to mean
    "the marker was missing".
    """
    left_at = _require_unique_marker(source, left, label="left")
    left_end = left_at + len(left)
    right_at = source.find(right, left_end)
    if right_at < 0:
        raise HarnessError(
            f"right marker {right!r} is absent after left {left!r} "
            f"in source {source!r}"
        )
    between = source[left_end:right_at]
    count = _count_blank_lines(between)
    print(
        f"blank-lines-between left={left!r} right={right!r} count={count} "
        f"between={between!r}",
        flush=True,
    )
    return count


def _count_blank_lines(between: str) -> int:
    if between.startswith("\r\n"):
        rest = between[2:]
    elif between.startswith("\n"):
        rest = between[1:]
    else:
        if "\n" not in between and "\r" not in between:
            return 0
        rest = between
    if not rest:
        return 0
    trailing_partial = not rest.endswith("\n") and not rest.endswith("\r\n")
    lines = rest.splitlines()
    if trailing_partial and lines:
        lines = lines[:-1]
    return sum(1 for line in lines if line.strip() == "")


def assert_blank_between(source: str, left: str, right: str) -> None:
    count = blank_lines_between(source, left, right)
    if count < 1:
        raise AssertionError(
            "expected a blank line at the named site; "
            f"left={left!r} right={right!r} count={count}"
        )


def assert_exactly_one_blank_between(source: str, left: str, right: str) -> None:
    count = blank_lines_between(source, left, right)
    if count != 1:
        raise AssertionError(
            "expected exactly one blank line between the two top-level "
            f"const declarations; left={left!r} right={right!r} count={count}"
        )


def assert_no_blank_between(source: str, left: str, right: str) -> None:
    count = blank_lines_between(source, left, right)
    if count != 0:
        raise AssertionError(
            "expected no blank line at the preserve site; "
            f"left={left!r} right={right!r} count={count}"
        )


def assert_docs_attached_after_fix(snippet: DocsSnippet, after: str) -> None:
    """Blank before the docs; none between the docs and the following declaration."""
    prev = snippet.previous
    docs = snippet.docs
    later = snippet.following
    i_prev = _require_unique_marker(after, prev, label="previous")
    i_docs = _require_unique_marker(after, docs, label="docs")
    i_later = _require_unique_marker(after, later, label="following")
    print(
        f"docs-order prev={i_prev} docs={i_docs} later={i_later}",
        flush=True,
    )
    if not (i_prev < i_docs < i_later):
        raise AssertionError(
            "expected earlier declaration, then documentation, then the "
            "later declaration"
        )
    assert_blank_between(after, prev, docs)
    assert_no_blank_between(after, docs, later)


def assert_second_pass_stable(
    ws: Workspace,
    specifier: str | Path,
    path: str | Path,
    expected: bytes,
    *,
    rules: Sequence[str] = F06_RULE_NAMES,
) -> None:
    """Second lint is silent for spacing; second ``--fix`` leaves bytes unchanged."""
    clean = lint_f06(ws, [path], specifier, rules=rules)
    print(
        f"second-lint {Path(path).name} exit={clean.returncode}",
        flush=True,
    )
    assert_classified_not_fired(clean, RULE_SPACING)
    assert_silent_f06(clean, RULE_SPACING)
    lint_f06(ws, [path], specifier, rules=rules, fix=True)
    after = read_source_bytes(path)
    print(
        f"second-fix {Path(path).name} equal={after == expected}",
        flush=True,
    )
    if after != expected:
        raise AssertionError(
            "a second fix pass must leave the file bytes unchanged; "
            f"path={path}"
        )


def assert_spacing_insert(
    ws: Workspace,
    specifier: str | Path,
    snippet: SpacingSnippet,
    *,
    prefix: str,
    ext: str = "ts",
    exactly_one: bool = False,
    rules: Sequence[str] = F06_RULE_NAMES,
    extra_sites: Sequence[tuple[str, str]] = (),
) -> tuple[Path, str]:
    """Report missing blank, insert whitespace only, then a clean second pass."""
    path = write_f06_source(ws, snippet.source, prefix=prefix, ext=ext)
    before_lint = lint_f06(ws, [path], specifier, rules=rules)
    print(f"insert-before {path.name} exit={before_lint.returncode}", flush=True)
    assert_only_rule(before_lint, RULE_SPACING)
    before = read_source_bytes(path)
    lint_f06(ws, [path], specifier, rules=rules, fix=True)
    after = read_source_text(path)
    assert_whitespace_only_change(before.decode("utf-8"), after)
    if exactly_one:
        assert_exactly_one_blank_between(after, snippet.left, snippet.right)
    else:
        assert_blank_between(after, snippet.left, snippet.right)
    for left, right in extra_sites:
        assert_blank_between(after, left, right)
    assert_second_pass_stable(
        ws, specifier, path, after.encode("utf-8"), rules=rules
    )
    return path, after


def assert_spacing_preserve(
    ws: Workspace,
    specifier: str | Path,
    source: str,
    *,
    prefix: str,
    ext: str = "ts",
    rules: Sequence[str] = F06_RULE_NAMES,
) -> Path:
    """Already-valid spacing: classified success and ``--fix`` leaves bytes."""
    path = write_f06_source(ws, source, prefix=prefix, ext=ext)
    silent = lint_f06(ws, [path], specifier, rules=rules)
    print(f"preserve-lint {path.name} exit={silent.returncode}", flush=True)
    assert_silent_f06(silent, RULE_SPACING)
    before = read_source_bytes(path)
    lint_f06(ws, [path], specifier, rules=rules, fix=True)
    after = read_source_bytes(path)
    print(
        f"preserve-fix {path.name} equal={after == before}",
        flush=True,
    )
    if after != before:
        raise AssertionError(
            "preserve arm must not rewrite the file under host fix mode; "
            f"path={path}"
        )
    return path


def run_shape_fix(
    ws: Workspace,
    specifier: str | Path,
    source: str,
    *,
    prefix: str,
    ext: str = "ts",
) -> RunResult:
    """``--fix`` leaves shape-name source bytes unchanged and the rule still fires."""
    path = write_f06_source(ws, source, prefix=prefix, ext=ext)
    before = read_source_bytes(path)
    result = lint_f06(ws, [path], specifier, fix=True)
    print(f"shape-fix {path.name}", flush=True)
    assert_fix_preserves_source(path, before, result, RULE_SHAPE)
    assert_only_rule(result, RULE_SHAPE)
    return result


def _span_holds(offset: int, span: tuple[int, int]) -> bool:
    start, end = span
    return start <= offset < end


def _binding_span(source: str, name: str) -> tuple[int, int]:
    fragment = f"const {name}"
    start = _require_unique_marker(source, fragment, label="binding")
    semi = source.find(";", start)
    if semi < 0:
        raise HarnessError(
            f"binding {name!r} has no terminating semicolon in {source!r}"
        )
    return start, semi + 1


def assert_shape_finding_on_owned_not_neighbor(
    source: str,
    result: RunResult,
    snippet: NeighborSnippet,
) -> int:
    """A shape finding sits in the owned-name span; none sits in the neighbor.

    Hard-fails when a finding is missing line/column. Returns the smallest
    sortable offset in the owned span. Does not pin a finding count.
    """
    assert_only_rule(result, RULE_SHAPE)
    items = rule_diagnostics(result, RULE_SHAPE)
    owned: list[int] = []
    for item in items:
        offset = diagnostic_offset(source, item)
        if _span_holds(offset, snippet.allowed_span):
            raise AssertionError(
                "no-shape-in-symbol-names must identify the owned name, not "
                f"the allowed neighbor; offset={offset} "
                f"allowed_span={snippet.allowed_span}"
            )
        if _span_holds(offset, snippet.shape_span):
            owned.append(offset)
    print(
        f"shape-owned-offsets={owned} shape_span={snippet.shape_span} "
        f"allowed_span={snippet.allowed_span}",
        flush=True,
    )
    if not owned:
        raise AssertionError(
            "no-shape-in-symbol-names must identify the owned shape name; "
            f"shape_span={snippet.shape_span} source={source!r}"
        )
    return min(owned)


def containing_shape_name(prefix: str = "payload") -> str:
    return f"{fresh_ident(prefix)}Shape"


# ---------------------------------------------------------------------------
# Shape snippets
# ---------------------------------------------------------------------------


def snippet_const_shape_binding(*, twin: bool = False) -> str:
    return snippet_no_shape_in_symbol_names(twin=twin)


def snippet_uppercase_shape_binding(*, twin: bool = False) -> str:
    if not twin:
        return "const SHAPE = 1;\n"
    return f"const {fresh_ident('payload')}SHAPE = 1;\n"


def snippet_function_shape_of(*, twin: bool = False) -> str:
    if not twin:
        return "function shapeOf() {}\n"
    return f"function {containing_shape_name('run')}() {{}}\n"


def snippet_class_shape(*, twin: bool = False) -> str:
    if not twin:
        return "class Shape {}\n"
    return f"class {containing_shape_name('Owner')} {{}}\n"


def snippet_interface_user_shape(*, twin: bool = False) -> str:
    if not twin:
        return "interface UserShape { id: string }\n"
    return f"interface {containing_shape_name('User')} {{ id: string }}\n"


def snippet_type_payload_shape(*, twin: bool = False) -> str:
    if not twin:
        return "type PayloadShape = { id: string };\n"
    return f"type {containing_shape_name('Payload')} = {{ id: string }};\n"


def snippet_type_property_named_shape(*, twin: bool = False) -> str:
    if not twin:
        return "type Payload = { shape: string };\n"
    alias = fresh_ident("Payload")
    field = containing_shape_name("field")
    return f"type {alias} = {{ {field}: string }};\n"


def snippet_object_property_named_shape(*, twin: bool = False) -> str:
    if not twin:
        return "const owner = { shape: 1 };\n"
    owner = fresh_ident("bag")
    field = containing_shape_name("field")
    return f"const {owner} = {{ {field}: 1 }};\n"


def snippet_class_field_named_shape(*, twin: bool = False) -> str:
    owner = "Owner" if not twin else fresh_ident("Owner")
    field = "shape" if not twin else containing_shape_name("field")
    return f"class {owner} {{ {field} = 1; }}\n"


def snippet_private_name_shape(*, twin: bool = False) -> str:
    owner = "Owner" if not twin else fresh_ident("Owner")
    field = "shape" if not twin else containing_shape_name("field")
    return f"class {owner} {{ #{field} = 1; }}\n"


def snippet_jsx_name_shape(*, twin: bool = False) -> str:
    tag = "Shape" if not twin else containing_shape_name("Tag")
    el = "el" if not twin else fresh_ident("node")
    return f"const {el} = <{tag} />;\n"


def snippet_local_binding_shape_as_computed_key(*, twin: bool = False) -> str:
    owner = "owner" if not twin else fresh_ident("bag")
    key = "shape" if not twin else containing_shape_name("key")
    value = "value" if not twin else fresh_ident("got")
    return (
        f"const {owner} = {{ id: 1 }};\n"
        f"\n"
        f"const {key} = \"id\";\n"
        f"\n"
        f"const {value} = {owner}[{key}];\n"
    )


def snippet_declared_external_schema_shape_id(*, twin: bool = False) -> str:
    schema = "schema" if not twin else fresh_ident("model")
    ext = "ExternalSchema" if not twin else fresh_ident("Ext")
    field = "field" if not twin else fresh_ident("got")
    return (
        f"declare const {schema}: {ext};\n"
        f"\n"
        f"const {field} = {schema}.shape.id;\n"
    )


def snippet_declared_external_outer_inner_shape(*, twin: bool = False) -> str:
    outer = "outer" if not twin else fresh_ident("root")
    ext = "External" if not twin else fresh_ident("Ext")
    value = "value" if not twin else fresh_ident("got")
    return (
        f"declare const {outer}: {ext};\n"
        f"\n"
        f"const {value} = {outer}.inner.shape;\n"
    )


def snippet_local_binding_member_shape(*, twin: bool = False) -> str:
    local = "local" if not twin else fresh_ident("holder")
    value = "value" if not twin else fresh_ident("got")
    return (
        f"const {local} = {{ id: 1 }};\n"
        f"\n"
        f"const {value} = {local}.shape;\n"
    )


def snippet_assignment_to_schema_shape(*, twin: bool = False) -> str:
    schema = "schema" if not twin else fresh_ident("model")
    ext = "ExternalSchema" if not twin else fresh_ident("Ext")
    return (
        f"declare const {schema}: {ext};\n"
        f"\n"
        f"{schema}.shape = 1;\n"
    )


def snippet_assignment_to_local_shape() -> str:
    local = fresh_ident("holder")
    return (
        f"const {local} = {{ id: 1 }};\n"
        f"\n"
        f"{local}.shape = 1;\n"
    )


def snippet_local_binding_member_containing_shape() -> str:
    local = fresh_ident("holder")
    member = containing_shape_name("payload")
    value = fresh_ident("got")
    return (
        f"const {local} = {{ id: 1 }};\n"
        f"\n"
        f"const {value} = {local}.{member};\n"
    )


def snippet_ordinary_property_owner_id(*, twin: bool = False) -> str:
    owner = "owner" if not twin else fresh_ident("bag")
    value = "value" if not twin else fresh_ident("got")
    return (
        f"const {owner} = {{ id: 1 }};\n"
        f"\n"
        f"const {value} = {owner}.id;\n"
    )


def snippet_neighbor_allowed_then_shape() -> NeighborSnippet:
    allowed = fresh_ident("kept")
    source = f"const {allowed} = 1;\n\nconst shape = 2;\n"
    return NeighborSnippet(
        source=source,
        allowed_span=_binding_span(source, allowed),
        shape_span=_binding_span(source, "shape"),
    )


def snippet_neighbor_shape_then_allowed() -> NeighborSnippet:
    allowed = fresh_ident("kept")
    source = f"const shape = 1;\n\nconst {allowed} = 2;\n"
    return NeighborSnippet(
        source=source,
        allowed_span=_binding_span(source, allowed),
        shape_span=_binding_span(source, "shape"),
    )


# ---------------------------------------------------------------------------
# Spacing snippets
# ---------------------------------------------------------------------------


def snippet_two_top_level_consts(*, twin: bool = False) -> SpacingSnippet:
    if not twin:
        source = snippet_require_readable_spacing(twin=False)
        return SpacingSnippet(
            source, "const firstValue = 1;", "const secondValue = 2;"
        )
    first = fresh_ident("one")
    second = fresh_ident("two")
    source = f"const {first} = 1;\nconst {second} = 2;\n"
    return SpacingSnippet(
        source, f"const {first} = 1;", f"const {second} = 2;"
    )


def snippet_export_const_then_documented_export_type(*, twin: bool = False) -> DocsSnippet:
    const_name = "a" if not twin else fresh_ident("first")
    type_name = "B" if not twin else fresh_ident("Second")
    docs = "B docs." if not twin else fresh_ident("note")
    source = (
        f"export const {const_name} = 1;\n"
        f"/** {docs} */\n"
        f"export type {type_name} = number;\n"
    )
    return DocsSnippet(
        source=source,
        previous=f"export const {const_name} = 1;",
        docs=f"/** {docs} */",
        following=f"export type {type_name} = number;",
    )


def snippet_docs_export_const_then_export_const(*, twin: bool = False) -> DocsSnippet:
    first = "a" if not twin else fresh_ident("first")
    second = "b" if not twin else fresh_ident("second")
    docs = "B docs." if not twin else fresh_ident("note")
    source = (
        f"export const {first} = 1;\n"
        f"/** {docs} */\n"
        f"export const {second} = 2;\n"
    )
    return DocsSnippet(
        source=source,
        previous=f"export const {first} = 1;",
        docs=f"/** {docs} */",
        following=f"export const {second} = 2;",
    )


def snippet_interface_then_class(*, twin: bool = False) -> SpacingSnippet:
    iface = "First" if not twin else fresh_ident("Iface")
    cls = "Second" if not twin else fresh_ident("Owner")
    source = f"interface {iface} {{}}\nclass {cls} {{}}\n"
    return SpacingSnippet(
        source, f"interface {iface} {{}}", f"class {cls} {{}}"
    )


def snippet_adjacent_type_declarations(*, twin: bool = False) -> SpacingSnippet:
    first = "First" if not twin else fresh_ident("Alpha")
    second = "Second" if not twin else fresh_ident("Beta")
    source = f"type {first} = string;\ntype {second} = number;\n"
    return SpacingSnippet(
        source, f"type {first} = string;", f"type {second} = number;"
    )


def snippet_adjacent_top_level_functions(*, twin: bool = False) -> SpacingSnippet:
    first = "first" if not twin else fresh_ident("alpha")
    second = "second" if not twin else fresh_ident("beta")
    source = f"function {first}() {{}}\nfunction {second}() {{}}\n"
    return SpacingSnippet(
        source, f"function {first}() {{}}", f"function {second}() {{}}"
    )


def snippet_import_then_const(*, twin: bool = False) -> SpacingSnippet:
    imported = "a" if not twin else fresh_ident("item")
    binding = "b" if not twin else fresh_ident("held")
    spec = "mod-a" if not twin else fresh_ident("mod")
    source = (
        f'import {{ {imported} }} from "{spec}";\n'
        f"const {binding} = {imported};\n"
    )
    return SpacingSnippet(
        source,
        f'import {{ {imported} }} from "{spec}";',
        f"const {binding} = {imported};",
    )


def snippet_import_then_function(*, twin: bool = False) -> SpacingSnippet:
    imported = "a" if not twin else fresh_ident("item")
    fn = "run" if not twin else fresh_ident("go")
    spec = "mod-a" if not twin else fresh_ident("mod")
    source = (
        f'import {{ {imported} }} from "{spec}";\n'
        f"function {fn}() {{}}\n"
    )
    return SpacingSnippet(
        source,
        f'import {{ {imported} }} from "{spec}";',
        f"function {fn}() {{}}",
    )


def snippet_unsorted_imports_then_const() -> SpacingSnippet:
    source = (
        'import { b } from "mod-b";\n'
        'import { a } from "mod-a";\n'
        "const c = 1;\n"
    )
    return SpacingSnippet(
        source,
        'import { a } from "mod-a";',
        "const c = 1;",
    )


def snippet_adjacent_imports_grouped() -> str:
    return (
        'import { a } from "mod-a";\n'
        'import { b } from "mod-b";\n'
        "\n"
        "const c = 1;\n"
    )


def snippet_extra_blanks_between_imports() -> str:
    return (
        'import { a } from "mod-a";\n'
        "\n"
        "\n"
        'import { b } from "mod-b";\n'
        "\n"
        "const c = 1;\n"
    )


def _fn_block(body: str, *, twin: bool) -> tuple[str, str]:
    fn = "run" if not twin else fresh_ident("go")
    start = "start" if not twin else fresh_ident("begin")
    source = f"function {fn}() {{\n{start}();\n{body}\n}}\n"
    return source, f"{start}();"


def snippet_blank_before_if(*, twin: bool = False) -> SpacingSnippet:
    source, left = _fn_block("if (a) go();", twin=twin)
    return SpacingSnippet(source, left, "if (a) go();")


def snippet_blank_before_switch(*, twin: bool = False) -> SpacingSnippet:
    source, left = _fn_block("switch (x) { default: go(); }", twin=twin)
    return SpacingSnippet(source, left, "switch (x)")


def snippet_blank_before_try(*, twin: bool = False) -> SpacingSnippet:
    source, left = _fn_block("try { go(); } catch { }", twin=twin)
    return SpacingSnippet(source, left, "try { go(); }")


def snippet_blank_before_for(*, twin: bool = False) -> SpacingSnippet:
    source, left = _fn_block(
        "for (let i = 0; i < 1; i += 1) go();", twin=twin
    )
    return SpacingSnippet(source, left, "for (let i = 0;")


def snippet_blank_before_while(*, twin: bool = False) -> SpacingSnippet:
    source, left = _fn_block("while (ok) go();", twin=twin)
    return SpacingSnippet(source, left, "while (ok) go();")


def snippet_blank_before_do(*, twin: bool = False) -> SpacingSnippet:
    source, left = _fn_block("do { go(); } while (ok);", twin=twin)
    return SpacingSnippet(source, left, "do { go(); }")


def snippet_compact_two_statement_body(*, twin: bool = False) -> SpacingSnippet:
    fn = "f" if not twin else fresh_ident("run")
    binding = "a" if not twin else fresh_ident("held")
    source = f"function {fn}() {{ const {binding} = 1; return {binding}; }}\n"
    return SpacingSnippet(
        source, f"const {binding} = 1;", f"return {binding};"
    )


def snippet_blank_before_return_in_nested_block(*, twin: bool = False) -> SpacingSnippet:
    fn = "run" if not twin else fresh_ident("go")
    inner = "foo" if not twin else fresh_ident("prep")
    result = "x" if not twin else fresh_ident("out")
    source = (
        f"function {fn}() {{\n"
        f"if (ok) {{\n"
        f"{inner}();\n"
        f"return {result};\n"
        f"}}\n"
        f"}}\n"
    )
    return SpacingSnippet(source, f"{inner}();", f"return {result};")


def snippet_blank_after_if_block(*, twin: bool = False) -> SpacingSnippet:
    fn = "run" if not twin else fresh_ident("go")
    act = "go" if not twin else fresh_ident("act")
    nxt = "stop" if not twin else fresh_ident("halt")
    source = (
        f"function {fn}() {{\n"
        f"if (ok) {{ {act}(); }}\n"
        f"{nxt}();\n"
        f"}}\n"
    )
    return SpacingSnippet(source, f"if (ok) {{ {act}(); }}", f"{nxt}();")


def snippet_blank_after_try_block(*, twin: bool = False) -> SpacingSnippet:
    fn = "run" if not twin else fresh_ident("go")
    act = "go" if not twin else fresh_ident("act")
    nxt = "stop" if not twin else fresh_ident("halt")
    source = (
        f"function {fn}() {{\n"
        f"try {{ {act}(); }} catch {{ }}\n"
        f"{nxt}();\n"
        f"}}\n"
    )
    return SpacingSnippet(
        source, f"try {{ {act}(); }} catch {{ }}", f"{nxt}();"
    )


def snippet_multiline_binding(
    kind: str, *, twin: bool = False
) -> tuple[SpacingSnippet, str, str]:
    fn = "run" if not twin else fresh_ident("go")
    start = "start" if not twin else fresh_ident("begin")
    stop = "stop" if not twin else fresh_ident("end")
    name = "value" if not twin else fresh_ident("held")
    keyword = {"const": "const", "let": "let", "var": "var", "using": "using"}[
        kind
    ]
    source = (
        f"function {fn}() {{\n"
        f"{start}();\n"
        f"{keyword} {name} = {{\n"
        f"  id: 1,\n"
        f"}};\n"
        f"{stop}();\n"
        f"}}\n"
    )
    snippet = SpacingSnippet(source, f"{start}();", f"{keyword} {name} = {{")
    extra = (f"}};", f"{stop}();")
    return snippet, extra[0], extra[1]


def snippet_nested_function_around_neighbors(*, twin: bool = False) -> tuple[SpacingSnippet, str, str]:
    outer = "outer" if not twin else fresh_ident("wrap")
    start = "start" if not twin else fresh_ident("begin")
    inner = "inner" if not twin else fresh_ident("kid")
    stop = "stop" if not twin else fresh_ident("end")
    source = (
        f"function {outer}() {{\n"
        f"{start}();\n"
        f"function {inner}() {{}}\n"
        f"{stop}();\n"
        f"}}\n"
    )
    snippet = SpacingSnippet(source, f"{start}();", f"function {inner}() {{}}")
    extra = (f"function {inner}() {{}}", f"{stop}();")
    return snippet, extra[0], extra[1]


def snippet_nested_class_around_neighbors(*, twin: bool = False) -> tuple[SpacingSnippet, str, str]:
    outer = "outer" if not twin else fresh_ident("wrap")
    start = "start" if not twin else fresh_ident("begin")
    inner = "Inner" if not twin else fresh_ident("Kid")
    stop = "stop" if not twin else fresh_ident("end")
    source = (
        f"function {outer}() {{\n"
        f"{start}();\n"
        f"class {inner} {{}}\n"
        f"{stop}();\n"
        f"}}\n"
    )
    snippet = SpacingSnippet(source, f"{start}();", f"class {inner} {{}}")
    extra = (f"class {inner} {{}}", f"{stop}();")
    return snippet, extra[0], extra[1]


def snippet_nested_interface_around_neighbors(*, twin: bool = False) -> tuple[SpacingSnippet, str, str]:
    outer = "outer" if not twin else fresh_ident("wrap")
    start = "start" if not twin else fresh_ident("begin")
    inner = "Inner" if not twin else fresh_ident("Kid")
    stop = "stop" if not twin else fresh_ident("end")
    source = (
        f"function {outer}() {{\n"
        f"{start}();\n"
        f"interface {inner} {{ id: string }}\n"
        f"{stop}();\n"
        f"}}\n"
    )
    snippet = SpacingSnippet(
        source, f"{start}();", f"interface {inner} {{ id: string }}"
    )
    extra = (f"interface {inner} {{ id: string }}", f"{stop}();")
    return snippet, extra[0], extra[1]


def snippet_nested_type_around_neighbors(*, twin: bool = False) -> tuple[SpacingSnippet, str, str]:
    outer = "outer" if not twin else fresh_ident("wrap")
    start = "start" if not twin else fresh_ident("begin")
    inner = "Inner" if not twin else fresh_ident("Kid")
    stop = "stop" if not twin else fresh_ident("end")
    source = (
        f"function {outer}() {{\n"
        f"{start}();\n"
        f"type {inner} = string;\n"
        f"{stop}();\n"
        f"}}\n"
    )
    snippet = SpacingSnippet(source, f"{start}();", f"type {inner} = string;")
    extra = (f"type {inner} = string;", f"{stop}();")
    return snippet, extra[0], extra[1]


def snippet_short_inner_consts_then_return(*, twin: bool = False) -> tuple[str, str, str, str]:
    fn = "f" if not twin else fresh_ident("run")
    first = "a" if not twin else fresh_ident("one")
    second = "b" if not twin else fresh_ident("two")
    source = (
        f"function {fn}() {{\n"
        f"const {first} = 1;\n"
        f"const {second} = 2;\n"
        f"return {first} + {second};\n"
        f"}}\n"
    )
    return (
        source,
        f"const {first} = 1;",
        f"const {second} = 2;",
        f"return {first} + {second};",
    )


def snippet_overload_signatures(*, twin: bool = False) -> str:
    name = "load" if not twin else fresh_ident("fetch")
    return (
        f"function {name}(item: string): string;\n"
        f"function {name}(item: number): number;\n"
        f"function {name}(item: string | number) {{ return item; }}\n"
    )


def snippet_extra_blank_lines_between_consts(*, twin: bool = False) -> str:
    first = "a" if not twin else fresh_ident("one")
    second = "b" if not twin else fresh_ident("two")
    return f"const {first} = 1;\n\n\nconst {second} = 2;\n"


def snippet_single_statement_compact_body(*, twin: bool = False) -> str:
    fn = "f" if not twin else fresh_ident("run")
    return f"function {fn}() {{ return 1; }}\n"


def snippet_adjacent_switch_case_clauses(*, twin: bool = False) -> str:
    fn = "run" if not twin else fresh_ident("go")
    act = "go" if not twin else fresh_ident("act")
    nxt = "stop" if not twin else fresh_ident("halt")
    return (
        f"function {fn}() {{\n"
        f"switch (x) {{\n"
        f"case 1:\n"
        f"case 2:\n"
        f"{act}();\n"
        f"break;\n"
        f"default:\n"
        f"{nxt}();\n"
        f"}}\n"
        f"}}\n"
    )


def snippet_long_initializer_two_consts() -> tuple[SpacingSnippet, str]:
    first = fresh_ident("one")
    second = fresh_ident("two")
    token = fresh_ident("payload")
    init = f'"{token}-{"x" * 40}"'
    statement = f"const {first} = {init};"
    source = f"{statement}\nconst {second} = 2;\n"
    snippet = SpacingSnippet(source, statement, f"const {second} = 2;")
    return snippet, statement
