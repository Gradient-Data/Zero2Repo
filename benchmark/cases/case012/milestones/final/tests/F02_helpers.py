# feature: F02
"""Observation helpers for the three collection-construction checks.

Import side effects: none. Process spawn and filesystem writes happen only
when a caller invokes a function below.
"""

from __future__ import annotations

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
    ensure_host_plugin_modules,
    effect_plugin_findings,
    fresh_ident,
    lint_generic,
    published_rule_id,
    rule_fired,
)

F02_RULE_NAMES: tuple[str, ...] = (
    "no-array-filter-map",
    "no-reduce-accumulator-copy",
    "no-conditional-empty-object-spread",
)

ARRAY_CHAIN_KEEPERS: tuple[str, ...] = (
    "slice",
    "concat",
    "flatMap",
    "toSorted",
    "toReversed",
    "toSpliced",
)

ARRAY_COPY_METHODS: tuple[str, ...] = (
    "concat",
    "slice",
    "toSpliced",
    "toSorted",
    "toReversed",
    "with",
)


def lint_f02(
    ws: Workspace,
    files: Sequence[str | Path],
    specifier: str | Path,
    *,
    rules: Sequence[str] = F02_RULE_NAMES,
    fix: bool = False,
) -> RunResult:
    """Register lint-policy only; enable *rules* at error; optional host ``--fix``."""
    ensure_host_plugin_modules(ws)
    print(
        f"lint-f02 specifier={specifier} rules={list(rules)} "
        f"fix={fix} files={list(files)}",
        flush=True,
    )
    if not fix:
        return lint_generic(ws, files, rules, specifier)
    plugin = generic_plugin(specifier=specifier, root=ws.root)
    mapping = {rule_key(GENERIC_PLUGIN_NAME, name): "error" for name in rules}
    return ws.lint(files, plugins=[plugin], rules=mapping, fix=True)


def write_source(
    ws: Workspace,
    source: str,
    *,
    ext: str = "js",
    prefix: str = "f02",
) -> Path:
    rel = f"{prefix}-{fresh_ident('s')}.{ext}"
    print(f"write {rel}", flush=True)
    return ws.write(rel, source)


def lint_source(
    ws: Workspace,
    specifier: str | Path,
    source: str,
    *,
    ext: str = "js",
    prefix: str = "f02",
    fix: bool = False,
) -> tuple[Path, RunResult]:
    path = write_source(ws, source, ext=ext, prefix=prefix)
    result = lint_f02(ws, [path], specifier, fix=fix)
    print(f"lint {path.name} exit={result.returncode}", flush=True)
    return path, result


def count_rule_findings(result: RunResult, rule_name: str) -> int:
    """Count classified findings for *rule_name*. Raises if JSON is unclassified."""
    expected = rule_key(GENERIC_PLUGIN_NAME, rule_name)
    findings = lint_policy_findings(result)
    count = sum(1 for item in findings if published_rule_id(item) == expected)
    print(
        f"count-rule {rule_name}={count} generic={findings} "
        f"exit={result.returncode}",
        flush=True,
    )
    return count


def assert_more_rule_findings(
    more: RunResult,
    fewer: RunResult,
    rule_name: str,
) -> None:
    assert_fired(more, rule_name)
    assert_fired(fewer, rule_name)
    more_n = count_rule_findings(more, rule_name)
    fewer_n = count_rule_findings(fewer, rule_name)
    print(
        f"assert-more {rule_name} more={more_n} fewer={fewer_n}",
        flush=True,
    )
    if not more_n > fewer_n:
        raise AssertionError(
            f"an extra adjacent mixed pair must add a {rule_name} diagnostic; "
            f"more={more_n} fewer={fewer_n}"
        )


def assert_silent_f02(result: RunResult, rule_name: str) -> None:
    """Classified success and no finding from *rule_name* (F02 rules only)."""
    generic = lint_policy_findings(result)
    effect = effect_plugin_findings(result)
    print(
        f"assert-silent-f02 {rule_name} exit={result.returncode} "
        f"generic={generic} effect={effect}",
        flush=True,
    )
    if rule_fired(generic, rule_name):
        raise AssertionError(
            f"rule {rule_name} must not fire; got {generic}"
        )
    if result.returncode != 0:
        raise HarnessError(
            "silence with only F02 rules enabled requires classified success; "
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


def assert_fix_preserves_source(
    path: str | Path,
    before: bytes,
    result: RunResult,
    rule_name: str,
) -> None:
    """Source bytes unchanged under ``--fix`` and the named rule still fires."""
    src = Path(path)
    try:
        after = src.read_bytes()
    except OSError as exc:
        raise HarnessError(
            f"cannot read source after fix-mode lint: {exc}"
        ) from exc
    print(
        f"fix-preserve {src.name} before_len={len(before)} after_len={len(after)} "
        f"equal={after == before} exit={result.returncode}",
        flush=True,
    )
    if after != before:
        raise AssertionError(
            "host fix mode must leave the violating construct's source bytes "
            f"unchanged; path={src}"
        )
    assert_fired(result, rule_name)


def run_fix_and_assert(
    ws: Workspace,
    specifier: str | Path,
    source: str,
    rule_name: str,
    *,
    ext: str = "js",
    prefix: str = "fix",
) -> RunResult:
    """Lint with host ``--fix``; require unchanged bytes and a firing diagnostic."""
    path = write_source(ws, source, ext=ext, prefix=prefix)
    before = path.read_bytes()
    result = lint_f02(ws, [path], specifier, fix=True)
    print(f"fix-mode {path.name} rule={rule_name}", flush=True)
    assert_fix_preserves_source(path, before, result, rule_name)
    assert_only_rule(result, rule_name)
    return result


def _keep_pick() -> tuple[str, str]:
    return fresh_ident("keep"), fresh_ident("pick")


def _ts_item() -> tuple[str, str]:
    name = fresh_ident("Item")
    return name, f"type {name} = {{ id: string }};\n"


def mixed_pair_expr(
    receiver: str,
    *,
    order: str = "filter_map",
    keep: str | None = None,
    pick: str | None = None,
) -> str:
    keep = keep or fresh_ident("keep")
    pick = pick or fresh_ident("pick")
    if order == "filter_map":
        return f"{receiver}.filter({keep}).map({pick})"
    if order == "map_filter":
        return f"{receiver}.map({pick}).filter({keep})"
    raise ValueError(f"unknown mixed-pair order: {order}")


def keeper_expr(receiver: str, method: str) -> str:
    arg = fresh_ident("x")
    if method == "slice":
        return f"{receiver}.slice()"
    if method == "concat":
        return f"{receiver}.concat([])"
    if method == "flatMap":
        return f"{receiver}.flatMap({arg} => [{arg}])"
    if method == "map":
        return f"{receiver}.map({arg})"
    if method == "filter":
        return f"{receiver}.filter({arg})"
    if method == "toSorted":
        return f"{receiver}.toSorted()"
    if method == "toReversed":
        return f"{receiver}.toReversed()"
    if method == "toSpliced":
        return f"{receiver}.toSpliced(0, 0)"
    raise ValueError(f"unknown keeper: {method}")


def acc_copy_expr(acc: str, method: str, item: str) -> str:
    if method == "concat":
        return f"{acc}.concat([{item}])"
    if method == "slice":
        return f"{acc}.slice()"
    if method == "toSpliced":
        return f"{acc}.toSpliced({acc}.length, 0, {item})"
    if method == "toSorted":
        return f"{acc}.toSorted()"
    if method == "toReversed":
        return f"{acc}.toReversed()"
    if method == "with":
        return f"{acc}.with(0, {item})"
    raise ValueError(f"unknown copy method: {method}")


def snippet_map_then_filter_literal(*, twin: bool = True) -> str:
    keep, pick = ("active", "email") if not twin else _keep_pick()
    return f"[].map({pick}).filter({keep});\n"


def snippet_const_local_mixed_pair(
    *,
    order: str = "filter_map",
    receiver: str | None = None,
) -> str:
    rows = receiver or fresh_ident("rows")
    pair = mixed_pair_expr(rows, order=order)
    return f"const {rows} = [];\n{pair};\n"


def snippet_const_alias_of_known_array() -> str:
    rows = fresh_ident("rows")
    alias = fresh_ident("alias")
    pair = mixed_pair_expr(alias)
    return f"const {rows} = [];\nconst {alias} = {rows};\n{pair};\n"


def snippet_keeper_then_mixed_pair(
    method: str,
    *,
    order: str = "filter_map",
) -> str:
    rows = fresh_ident("rows")
    chain = keeper_expr(rows, method)
    pair = mixed_pair_expr(chain, order=order)
    return f"const {rows} = [];\n{pair};\n"


def snippet_map_or_filter_chain_then_mixed_pair(
    method: str,
    *,
    order: str = "filter_map",
) -> str:
    """Later mixed pair on the result of a map or filter chain (const-bound).

    Binding the chain result, then writing the mixed pair on that binding,
    keeps map/filter out of the adjacent pair itself. An inline
    ``.map().filter()`` / ``.filter().map()`` after the keeper would already
    report as a mixed pair on the original known array.
    """
    if method not in {"map", "filter"}:
        raise ValueError(f"expected map or filter keeper, got {method}")
    rows = fresh_ident("rows")
    chained = fresh_ident("chained")
    chain = keeper_expr(rows, method)
    pair = mixed_pair_expr(chained, order=order)
    return f"const {rows} = [];\nconst {chained} = {chain};\n{pair};\n"


def snippet_annotated_param_mixed_pair(
    *,
    twin: bool = True,
    annotated: bool = True,
) -> str:
    typ = "User" if not twin else fresh_ident("Item")
    fn = "collect" if not twin else fresh_ident("collect")
    param = "users" if not twin else fresh_ident("rows")
    keep = "active" if not twin else fresh_ident("keep")
    pick = "email" if not twin else fresh_ident("pick")
    ann = f": {typ}[]" if annotated else ""
    return (
        f"type {typ} = {{ id: string }};\n"
        f"function {fn}({param}{ann}) {{\n"
        f"  return {param}.filter({keep}).map({pick});\n"
        f"}}\n"
    )


def _binding_annotation(typ: str, form: str) -> str:
    """Direct array or tuple annotation text. *form* is the PRD shape, not a message."""
    if form == "array":
        return f"{typ}[]"
    if form == "readonly":
        return f"readonly {typ}[]"
    if form == "Array":
        return f"Array<{typ}>"
    if form == "ReadonlyArray":
        return f"ReadonlyArray<{typ}>"
    if form == "tuple":
        return f"[{typ}, {typ}]"
    raise ValueError(f"unknown annotation form: {form}")


def snippet_annotated_binding_mixed_pair(
    *,
    kind: str = "const",
    twin: bool = True,
    extra_write: str | None = None,
    form: str = "array",
    call_receiver: bool = False,
) -> str:
    if kind not in {"const", "let", "var"}:
        raise ValueError(f"unknown binding kind: {kind}")
    typ = "User" if not twin else fresh_ident("Item")
    factory = "loadUsers" if not twin else fresh_ident("load")
    rows = "users" if not twin else fresh_ident("rows")
    keep = "active" if not twin else fresh_ident("keep")
    pick = "email" if not twin else fresh_ident("pick")
    if call_receiver:
        return (
            f"type {typ} = {{ id: string }};\n"
            f"function {factory}() {{ return []; }}\n"
            f"{factory}().filter({keep}).map({pick});\n"
        )
    write = f"{rows} = {extra_write};\n" if extra_write is not None else ""
    ann = _binding_annotation(typ, form)
    return (
        f"type {typ} = {{ id: string }};\n"
        f"function {factory}() {{ return []; }}\n"
        f"{kind} {rows}: {ann} = {factory}();\n"
        f"{write}"
        f"{rows}.filter({keep}).map({pick});\n"
    )


def snippet_generic_array_annotation(kind: str, *, annotated: bool = True) -> str:
    """Same TypeScript snippet; *annotated* is the only array or tuple annotation."""
    typ, header = _ts_item()
    keep, pick = _keep_pick()
    fn = fresh_ident("collect")
    rows = fresh_ident("rows")
    if kind == "param_tuple":
        ann = f": [{typ}, {typ}]" if annotated else ""
        return (
            header
            + f"function {fn}({rows}{ann}) {{\n"
            + f"  return {rows}.filter({keep}).map({pick});\n"
            + "}\n"
        )
    if kind == "binding_tuple":
        factory = fresh_ident("load")
        ann = f": [{typ}, {typ}]" if annotated else ""
        return (
            header
            + f"function {factory}() {{ return []; }}\n"
            + f"const {rows}{ann} = {factory}();\n"
            + f"{rows}.filter({keep}).map({pick});\n"
        )
    if kind == "param_readonly":
        ann_text = f"readonly {typ}[]"
    elif kind == "param_Array":
        ann_text = f"Array<{typ}>"
    elif kind == "param_ReadonlyArray":
        ann_text = f"ReadonlyArray<{typ}>"
    else:
        raise ValueError(f"unknown annotation kind: {kind}")
    ann = f": {ann_text}" if annotated else ""
    return (
        header
        + f"function {fn}({rows}{ann}) {{\n"
        + f"  return {rows}.filter({keep}).map({pick});\n"
        + "}\n"
    )


def snippet_iterator_values_pipeline(*, values: bool = True) -> str:
    """Filter-then-map ending at toArray. *values* only inserts ``values()``."""
    rows = fresh_ident("rows")
    keep, pick = _keep_pick()
    receiver = f"{rows}.values()" if values else rows
    return (
        f"const {rows} = [];\n"
        f"{receiver}.filter({keep}).map({pick}).toArray();\n"
    )


def snippet_iterator_from_pipeline(*, wrapped: bool = True) -> str:
    """Filter-then-map on a const array. *wrapped* only changes the receiver."""
    rows = fresh_ident("rows")
    keep, pick = _keep_pick()
    receiver = f"Iterator.from({rows})" if wrapped else rows
    return (
        f"const {rows} = [];\n"
        f"{receiver}.filter({keep}).map({pick});\n"
    )


def snippet_iterator_typed_parameter() -> str:
    walk = fresh_ident("Walk")
    fn = fresh_ident("collect")
    param = fresh_ident("rows")
    keep, pick = _keep_pick()
    return (
        f"type {walk} = {{ next(): {{ done?: boolean }} }};\n"
        f"function {fn}({param}: {walk}) {{\n"
        f"  return {param}.filter({keep}).map({pick});\n"
        f"}}\n"
    )


def snippet_single_flatmap() -> str:
    rows = fresh_ident("rows")
    body = fresh_ident("x")
    return (
        f"const {rows} = [];\n"
        f"{rows}.flatMap({body} => [{body}]);\n"
    )


def snippet_flatmap_then_map() -> str:
    rows = fresh_ident("rows")
    body = fresh_ident("x")
    pick = fresh_ident("pick")
    return (
        f"const {rows} = [];\n"
        f"{rows}.flatMap({body} => [{body}]).map({pick});\n"
    )


def snippet_flatmap_then_filter_map() -> str:
    rows = fresh_ident("rows")
    body = fresh_ident("x")
    pair = mixed_pair_expr(f"{rows}.flatMap({body} => [{body}])")
    return f"const {rows} = [];\n{pair};\n"


def snippet_same_method_chain(method: str) -> str:
    rows = fresh_ident("rows")
    first = fresh_ident("one")
    second = fresh_ident("two")
    return (
        f"const {rows} = [];\n"
        f"{rows}.{method}({first}).{method}({second});\n"
    )


def snippet_separate_filter_and_map() -> str:
    rows = fresh_ident("rows")
    keep, pick = _keep_pick()
    return (
        f"const {rows} = [];\n"
        f"{rows}.filter({keep});\n"
        f"{rows}.map({pick});\n"
    )


def snippet_non_adjacent_filter_map() -> str:
    rows = fresh_ident("rows")
    keep, pick = _keep_pick()
    return (
        f"const {rows} = [];\n"
        f"{rows}.filter({keep}).slice().map({pick});\n"
    )


def snippet_custom_object_filter_map() -> str:
    obj = fresh_ident("custom")
    keep, pick = _keep_pick()
    return (
        f"const {obj} = {{ filter() {{ return this; }}, map() {{}} }};\n"
        f"{obj}.filter({keep}).map({pick});\n"
    )


def snippet_unknown_receiver() -> str:
    factory = fresh_ident("fetch")
    rows = fresh_ident("rows")
    keep, pick = _keep_pick()
    return (
        f"const {rows} = {factory}();\n"
        f"{rows}.filter({keep}).map({pick});\n"
    )


def snippet_unannotated_parameter() -> str:
    fn = fresh_ident("collect")
    param = fresh_ident("rows")
    keep, pick = _keep_pick()
    return (
        f"function {fn}({param}) {{\n"
        f"  return {param}.filter({keep}).map({pick});\n"
        f"}}\n"
    )


def write_imported_factory_mixed_pair(
    ws: Workspace,
    *,
    ext: str = "js",
    annotated: bool = False,
) -> Path:
    """Import a factory that returns an array. *annotated* is the only binding annotation."""
    if annotated and ext != "ts":
        raise ValueError("a direct array annotation requires a TypeScript file")
    mod = fresh_ident("mod")
    factory = fresh_ident("load")
    rows = fresh_ident("rows")
    typ = fresh_ident("Item")
    keep, pick = _keep_pick()
    ws.write(f"{mod}.{ext}", f"export function {factory}() {{ return []; }}\n")
    header = f"type {typ} = {{ id: string }};\n" if ext == "ts" else ""
    ann = f": {typ}[]" if annotated else ""
    source = (
        f'import {{ {factory} }} from "./{mod}.{ext}";\n'
        f"{header}"
        f"const {rows}{ann} = {factory}();\n"
        f"{rows}.filter({keep}).map({pick});\n"
    )
    return write_source(ws, source, ext=ext, prefix="imp")


def snippet_type_alias_param() -> str:
    typ, header = _ts_item()
    alias = fresh_ident("Rows")
    fn = fresh_ident("collect")
    param = fresh_ident("rows")
    keep, pick = _keep_pick()
    return (
        header
        + f"type {alias} = {typ}[];\n"
        + f"function {fn}({param}: {alias}) {{\n"
        + f"  return {param}.filter({keep}).map({pick});\n"
        + "}\n"
    )


def snippet_type_alias_binding() -> str:
    typ, header = _ts_item()
    alias = fresh_ident("Rows")
    factory = fresh_ident("load")
    rows = fresh_ident("rows")
    keep, pick = _keep_pick()
    return (
        header
        + f"type {alias} = {typ}[];\n"
        + f"function {factory}() {{ return []; }}\n"
        + f"let {rows}: {alias} = {factory}();\n"
        + f"{rows}.filter({keep}).map({pick});\n"
    )


def snippet_let_or_var_literal_mixed_pair(kind: str) -> str:
    if kind not in {"let", "var"}:
        raise ValueError(kind)
    rows = fresh_ident("rows")
    pair = mixed_pair_expr(rows)
    return f"{kind} {rows} = [];\n{pair};\n"


def snippet_property_based_array_field() -> str:
    typ, header = _ts_item()
    box = fresh_ident("Box")
    fn = fresh_ident("collect")
    param = fresh_ident("box")
    field = fresh_ident("rows")
    keep, pick = _keep_pick()
    return (
        header
        + f"type {box} = {{ {field}: {typ}[] }};\n"
        + f"function {fn}({param}: {box}) {{\n"
        + f"  return {param}.{field}.filter({keep}).map({pick});\n"
        + "}\n"
    )


def snippet_non_literal_computed_method(*, literal_key: bool = False) -> str:
    """Dotted second callee. *literal_key* only changes the first computed key."""
    rows = fresh_ident("rows")
    method = fresh_ident("method")
    keep, pick = _keep_pick()
    key = "'filter'" if literal_key else method
    return (
        f"const {method} = 'filter';\n"
        f"const {rows} = [];\n"
        f"{rows}[{key}]({keep}).map({pick});\n"
    )


def snippet_optional_chaining_mixed_pair() -> str:
    rows = fresh_ident("rows")
    keep, pick = _keep_pick()
    return (
        f"const {rows} = [];\n"
        f"{rows}?.filter({keep})?.map({pick});\n"
    )


def snippet_non_null_assertion_mixed_pair() -> str:
    rows = fresh_ident("rows")
    keep, pick = _keep_pick()
    return (
        f"const {rows} = [];\n"
        f"({rows}.filter({keep})!).map({pick});\n"
    )


def snippet_computed_string_literal_methods() -> str:
    rows = fresh_ident("rows")
    keep, pick = _keep_pick()
    return (
        f"const {rows} = [];\n"
        f"{rows}['filter']({keep})['map']({pick});\n"
    )


def snippet_mixed_pair_with_trailing(extra: str) -> str:
    rows = fresh_ident("rows")
    keep, pick = _keep_pick()
    tail = fresh_ident("more")
    if extra == "filter":
        chain = f"{rows}.filter({keep}).map({pick}).filter({tail})"
        one = f"{rows}.filter({keep}).map({pick})"
    elif extra == "map":
        chain = f"{rows}.map({pick}).filter({keep}).map({tail})"
        one = f"{rows}.map({pick}).filter({keep})"
    else:
        raise ValueError(extra)
    return one, chain, rows


def snippet_one_and_two_pairs(extra: str) -> tuple[str, str]:
    rows = fresh_ident("rows")
    keep, pick = _keep_pick()
    tail = fresh_ident("more")
    header = f"const {rows} = [];\n"
    if extra == "filter":
        one = header + f"{rows}.filter({keep}).map({pick});\n"
        two = header + f"{rows}.filter({keep}).map({pick}).filter({tail});\n"
    elif extra == "map":
        one = header + f"{rows}.map({pick}).filter({keep});\n"
        two = header + f"{rows}.map({pick}).filter({keep}).map({tail});\n"
    else:
        raise ValueError(extra)
    return one, two


def snippet_object_assign_copy(
    *,
    method: str = "reduce",
    later_source: bool = False,
    two_arg: bool = False,
    copy_into_local: bool = False,
    const_alias: bool = False,
    let_alias: bool = False,
    var_alias: bool = False,
    defaulted: bool = False,
    index: bool = False,
    bracket: bool = False,
    function: bool = False,
    items: str | None = None,
) -> str:
    recv = items or fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    key = fresh_ident("id")
    if later_source:
        copy = f"Object.assign({{}}, {item}, {acc})"
    elif two_arg:
        copy = f"Object.assign({{}}, {acc})"
    else:
        copy = f"Object.assign({{}}, {acc}, {{ [{item}.{key}]: {item} }})"
    params = acc
    if defaulted:
        params = f"{acc} = {{}}"
    if not (function and defaulted and not index):
        params = f"{params}, {item}"
        if index:
            params = f"{params}, {fresh_ident('index')}, {fresh_ident('arr')}"
    if const_alias or let_alias or var_alias:
        kind = "const" if const_alias else ("let" if let_alias else "var")
        alias = fresh_ident("alias")
        body = (
            f"{{ {kind} {alias} = {acc}; return Object.assign({{}}, {alias}); }}"
        )
        arrow = f"({params}) => {body}"
        func = f"function ({params}) {body}"
    elif copy_into_local:
        nxt = fresh_ident("next")
        body = f"{{ const {nxt} = {copy}; return {nxt}; }}"
        arrow = f"({params}) => {body}"
        func = f"function ({params}) {body}"
    else:
        arrow = f"({params}) => {copy}"
        func = f"function ({params}) {{ return {copy}; }}"
    cb = func if function else arrow
    call = f"{recv}['{method}']({cb}, {{}})" if bracket else f"{recv}.{method}({cb}, {{}})"
    return f"{call};\n"


def snippet_syntactic_reduce_untyped_receiver() -> str:
    factory = fresh_ident("fetch")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    return (
        f"{factory}().reduce(({acc}, {item}) => Object.assign({{}}, {acc}), {{}});\n"
    )


def snippet_array_from_accumulator(
    *,
    init: str = "{}",
    method: str = "reduce",
) -> str:
    if method not in {"reduce", "reduceRight"}:
        raise ValueError(f"unknown reducer method: {method}")
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    return (
        f"{recv}.{method}(({acc}, {item}) => Array.from({acc}), {init});\n"
    )


def snippet_array_copy_on_init(method: str, *, init_kind: str = "literal") -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    copy = acc_copy_expr(acc, method, item)
    if init_kind == "const":
        initial = fresh_ident("initial")
        return (
            f"const {initial} = [];\n"
            f"{recv}.reduce(({acc}, {item}) => {copy}, {initial});\n"
        )
    if init_kind == "literal":
        return f"{recv}.reduce(({acc}, {item}) => {copy}, []);\n"
    if init_kind == "object":
        return f"{recv}.reduce(({acc}, {item}) => {copy}, {{}});\n"
    raise ValueError(init_kind)


def snippet_reduce_right_concat() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    return (
        f"{recv}.reduceRight(({acc}, {item}) => {acc}.concat([{item}]), []);\n"
    )


def snippet_mutating_accumulator() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    return (
        f"{recv}.reduce(({acc}, {item}) => ({acc}.push({item}), {acc}), {{}});\n"
    )


def snippet_assign_accumulator_as_target() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    return (
        f"{recv}.reduce(({acc}, {item}) => Object.assign({acc}, {item}), {{}});\n"
    )


def snippet_item_copy() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    key = fresh_ident("id")
    return (
        f"{recv}.reduce(({acc}, {item}) => "
        f"Object.assign({{}}, {item}, {{ [{item}.{key}]: {item} }}), {{}});\n"
    )


def snippet_nested_property_copy() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    nested = fresh_ident("inner")
    key = fresh_ident("id")
    return (
        f"{recv}.reduce(({acc}, {item}) => "
        f"Object.assign({{}}, {acc}.{nested}, {{ [{item}.{key}]: {item} }}), {{}});\n"
    )


def snippet_local_alias_of_global(name: str) -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    alias = fresh_ident("copied")
    key = fresh_ident("id")
    if name == "Object.assign":
        return (
            f"const {alias} = Object.assign;\n"
            f"{recv}.reduce(({acc}, {item}) => "
            f"{alias}({{}}, {acc}, {{ [{item}.{key}]: {item} }}), {{}});\n"
        )
    if name == "Array.from":
        return (
            f"const {alias} = Array.from;\n"
            f"{recv}.reduce(({acc}, {item}) => {alias}({acc}), {{}});\n"
        )
    raise ValueError(name)


def snippet_concat_string_init() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    return (
        f"{recv}.reduce(({acc}, {item}) => {acc}.concat([{item}]), '');\n"
    )


def snippet_concat_unknown_collection() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    coll = fresh_ident("custom")
    return (
        f"{recv}.reduce(({acc}, {item}) => {acc}.concat([{item}]), {coll});\n"
    )


def _three_arg_assign(acc: str, item: str, key: str) -> str:
    return f"Object.assign({{}}, {acc}, {{ [{item}.{key}]: {item} }})"


def snippet_named_callback_outside() -> str:
    recv = fresh_ident("items")
    fn = fresh_ident("copy")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    key = fresh_ident("id")
    copy = _three_arg_assign(acc, item, key)
    return (
        f"function {fn}({acc}, {item}) {{ return {copy}; }}\n"
        f"{recv}.reduce({fn}, {{}});\n"
    )


def snippet_nested_function_copy() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    inner = fresh_ident("copy")
    key = fresh_ident("id")
    copy = _three_arg_assign(acc, item, key)
    return (
        f"{recv}.reduce(({acc}, {item}) => {{ "
        f"function {inner}() {{ return {copy}; }} "
        f"return {inner}(); }}, {{}});\n"
    )


def snippet_snapshot_closure_copy() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    snap = fresh_ident("snapshot")
    key = fresh_ident("id")
    copy = _three_arg_assign(acc, item, key)
    return (
        f"{recv}.reduce(({acc}, {item}) => {{ "
        f"const {snap} = () => {copy}; "
        f"return {snap}(); }}, {{}});\n"
    )


def snippet_shadowed_inner_accumulator() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    key = fresh_ident("id")
    copy = _three_arg_assign(acc, item, key)
    return (
        f"{recv}.reduce(({acc}, {item}) => {{ "
        f"{{ const {acc} = {{}}; return {copy}; }} }}, {{}});\n"
    )


def snippet_shadowed_object_or_array(which: str) -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    key = fresh_ident("id")
    if which == "Object":
        copy = _three_arg_assign(acc, item, key)
        return (
            f"const Object = {{ assign() {{ return {{}}; }} }};\n"
            f"{recv}.reduce(({acc}, {item}) => {copy}, {{}});\n"
        )
    if which == "Array":
        return (
            f"const Array = {{ from() {{ return []; }} }};\n"
            f"{recv}.reduce(({acc}, {item}) => Array.from({acc}), {{}});\n"
        )
    raise ValueError(which)


def snippet_reassigned_accumulator_alias() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    alias = fresh_ident("alias")
    return (
        f"{recv}.reduce(({acc}, {item}) => {{ "
        f"let {alias} = {acc}; {alias} = {item}; "
        f"return Object.assign({{}}, {alias}); }}, {{}});\n"
    )


def snippet_reducer_array_spread() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    return f"{recv}.reduce(({acc}, {item}) => [...{acc}], {{}});\n"


def snippet_reducer_object_spread() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    return (
        f"{recv}.reduce(({acc}, {item}) => ({{ ...{acc} }}), {{}});\n"
    )


def snippet_assign_inside_map() -> str:
    recv = fresh_ident("items")
    acc = fresh_ident("acc")
    item = fresh_ident("item")
    return f"{recv}.map(({acc}, {item}) => Object.assign({{}}, {acc}), {{}});\n"


def snippet_empty_true_branch_spread(*, twin: bool = True) -> str:
    cond = "condition" if not twin else fresh_ident("cond")
    field = "value" if not twin else fresh_ident("field")
    return f"void ({{ ...({cond} ? {{}} : {{ {field} }}) }});\n"


def snippet_non_spread_conditional() -> str:
    cond = fresh_ident("cond")
    field = fresh_ident("field")
    return f"void ({cond} ? {{ {field}: 1 }} : {{}});\n"


def snippet_non_conditional_spread() -> str:
    field = fresh_ident("field")
    return f"void ({{ ...{{ {field}: 1 }} }});\n"


def snippet_object_without_spread_pattern() -> str:
    field = fresh_ident("field")
    return f"void ({{ {field}: 1 }});\n"


def snippet_both_branches_non_empty_spread() -> str:
    cond = fresh_ident("cond")
    left = fresh_ident("a")
    right = fresh_ident("b")
    return f"void ({{ ...({cond} ? {{ {left}: 1 }} : {{ {right}: 2 }}) }});\n"


def snippet_array_parent_empty_branch_spread(*, value: str | None = None) -> str:
    return snippet_l134_empty_false_spread(twin=True, parent="array", value=value)


def snippet_l134_object_assign(*, twin: bool = True) -> str:
    recv = "items" if not twin else fresh_ident("items")
    acc = "acc" if not twin else fresh_ident("acc")
    item = "item" if not twin else fresh_ident("item")
    key = "id" if not twin else fresh_ident("id")
    return (
        f"{recv}.reduce(({acc}, {item}) => "
        f"Object.assign({{}}, {acc}, {{ [{item}.{key}]: {item} }}), {{}});\n"
    )


def snippet_l134_empty_false_spread(
    *,
    twin: bool = True,
    parent: str = "object",
    value: str | None = None,
) -> str:
    if value is None:
        value = "value" if not twin else fresh_ident("value")
    cond = f"{value} !== undefined ? {{ {value} }} : {{}}"
    if parent == "object":
        return f"void ({{ ...({cond}) }});\n"
    if parent == "array":
        return f"void ([...({cond})]);\n"
    raise ValueError(f"unknown spread parent: {parent}")
