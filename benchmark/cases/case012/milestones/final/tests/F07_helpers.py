# feature: F07
"""Observation helpers for the opt-in lint-policy-effect plugin.

Import side effects: none. Process spawn and filesystem writes happen only
when a caller invokes a function below.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from _harness import (
    EFFECT_PLUGIN_NAME,
    GENERIC_PLUGIN_NAME,
    Diagnostic,
    HarnessError,
    RunResult,
    Workspace,
    diagnostics,
    effect_plugin,
    generic_plugin,
    rule_key,
)
from F01_helpers import (
    EFFECT_RULE_NAMES,
    lint_policy_findings,
    assert_no_plugin_findings,
    effect_plugin_findings,
    ensure_host_plugin_modules,
    fresh_ident,
    published_rule_id,
    snippet_manual_tag_comparison,
)
from F04_helpers import diagnostic_offset

RULE_TAG_CMP = "no-manual-tag-comparison"
RULE_ERR_TAG = "no-manual-effect-error-tag"
RULE_CONSTRUCT = "no-manual-tagged-construction"
RULE_MATCH = "prefer-effect-match"
RULE_SVC = "no-service-constructor-imports"


@dataclass(frozen=True)
class IdentifiedNeighbor:
    """One allowed construct and one violating construct in the same file."""

    source: str
    hit_span: tuple[int, int]
    miss_span: tuple[int, int]


@dataclass(frozen=True)
class CatchConstructSnippet:
    """A catch-handler comparison whose construct span is unique in the file."""

    source: str
    construct_span: tuple[int, int]
    call_span: tuple[int, int]


def next_effect_rule(rule_name: str) -> str:
    index = EFFECT_RULE_NAMES.index(rule_name)
    return EFFECT_RULE_NAMES[(index + 1) % len(EFFECT_RULE_NAMES)]


def generated_make_uppercase() -> str:
    return "make" + fresh_ident("Cap")


def generated_make_lowercase() -> str:
    return "make" + fresh_ident("cap")


def application_rel(*, ext: str = "ts", nested: bool = False) -> str:
    name = fresh_ident("app")
    if nested:
        return f"src/{fresh_ident('dir')}/{name}.{ext}"
    return f"src/{name}.{ext}"


def suffix_file_rel(*, kind: str = "test", ext: str = "ts") -> str:
    return f"src/{fresh_ident('file')}.{kind}.{ext}"


# ---------------------------------------------------------------------------
# Lint / write
# ---------------------------------------------------------------------------


def lint_f07(
    ws: Workspace,
    files: Sequence[str | Path],
    effect_specifier: str | Path,
    *,
    rules: Sequence[str] = EFFECT_RULE_NAMES,
    fix: bool = False,
    generic_specifier: str | Path | None = None,
    generic_rules: Sequence[str] = (),
) -> RunResult:
    """Register lint-policy-effect; enable *rules* at error; optional ``--fix``.

    Pass *generic_specifier* to also register the generic plugin. Do not
    pass rule options — none of the five Effect rules takes options.
    """
    ensure_host_plugin_modules(ws)
    print(
        f"lint-f07 effect={effect_specifier} rules={list(rules)} "
        f"fix={fix} generic={generic_specifier} generic_rules={list(generic_rules)} "
        f"files={list(files)}",
        flush=True,
    )
    plugins = [effect_plugin(specifier=effect_specifier, root=ws.root)]
    mapping = {rule_key(EFFECT_PLUGIN_NAME, name): "error" for name in rules}
    if generic_specifier is not None:
        plugins.insert(0, generic_plugin(specifier=generic_specifier, root=ws.root))
        for name in generic_rules:
            mapping[rule_key(GENERIC_PLUGIN_NAME, name)] = "error"
    return ws.lint(files, plugins=plugins, rules=mapping, fix=fix)


def write_f07_source(
    ws: Workspace,
    source: str,
    *,
    prefix: str = "f07",
    ext: str = "ts",
    rel: str | None = None,
) -> Path:
    """Write *source* under the workspace, creating parents."""
    if rel is None:
        rel = f"{prefix}-{fresh_ident('s')}.{ext}"
    print(f"write {rel}", flush=True)
    return ws.write(rel, source)


def lint_f07_source(
    ws: Workspace,
    effect_specifier: str | Path,
    source: str,
    *,
    prefix: str = "f07",
    ext: str = "ts",
    rel: str | None = None,
    rules: Sequence[str] = EFFECT_RULE_NAMES,
    fix: bool = False,
    generic_specifier: str | Path | None = None,
    generic_rules: Sequence[str] = (),
) -> tuple[Path, RunResult]:
    path = write_f07_source(ws, source, prefix=prefix, ext=ext, rel=rel)
    result = lint_f07(
        ws,
        [path],
        effect_specifier,
        rules=rules,
        fix=fix,
        generic_specifier=generic_specifier,
        generic_rules=generic_rules,
    )
    print(f"lint {path} exit={result.returncode}", flush=True)
    return path, result


# ---------------------------------------------------------------------------
# Effect-plugin observers (Rule 1: unclassified failure raises)
# ---------------------------------------------------------------------------


def effect_rule_fired(findings: Sequence[str], rule_name: str) -> bool:
    return rule_key(EFFECT_PLUGIN_NAME, rule_name) in findings


def effect_rule_diagnostics(result: RunResult, rule_name: str) -> tuple[Diagnostic, ...]:
    expected = rule_key(EFFECT_PLUGIN_NAME, rule_name)
    classified = diagnostics(result)
    matched = tuple(
        item
        for item in classified
        if published_rule_id(item.rule) == expected
    )
    print(
        f"effect-rule-diagnostics {rule_name} n={len(matched)} "
        f"exit={result.returncode}",
        flush=True,
    )
    return matched


def assert_effect_fired(
    result: RunResult,
    rule_name: str,
    *,
    allow_generic: bool = False,
) -> None:
    """Unsuccessful lint and an attributable lint-policy-effect/*rule* finding."""
    generic = lint_policy_findings(result)
    effect = effect_plugin_findings(result)
    print(
        f"assert-effect-fired {rule_name} exit={result.returncode} "
        f"generic={generic} effect={effect}",
        flush=True,
    )
    if result.returncode == 0:
        raise AssertionError(
            f"enabled Effect rule {rule_name} at error must fail lint; "
            f"exit={result.returncode}"
        )
    expected = rule_key(EFFECT_PLUGIN_NAME, rule_name)
    if expected not in effect:
        raise AssertionError(
            f"expected diagnostic {expected}; got {effect}"
        )
    if not allow_generic and generic:
        raise AssertionError(
            f"unexpected {GENERIC_PLUGIN_NAME} findings {generic}"
        )


def assert_only_effect_rule(
    result: RunResult,
    rule_name: str,
    *,
    allow_generic: bool = False,
) -> None:
    """Unsuccessful lint; among Effect findings, only *rule_name*."""
    generic = lint_policy_findings(result)
    effect = effect_plugin_findings(result)
    expected = rule_key(EFFECT_PLUGIN_NAME, rule_name)
    print(
        f"assert-only-effect {rule_name} exit={result.returncode} "
        f"ids={effect} generic={generic}",
        flush=True,
    )
    if result.returncode == 0:
        raise AssertionError(
            f"enabled Effect rule {rule_name} at error must fail lint; exit=0"
        )
    unique = tuple(dict.fromkeys(effect))
    if unique != (expected,):
        raise AssertionError(f"expected only {expected}; got {effect}")
    if not allow_generic and generic:
        raise AssertionError(
            f"unexpected {GENERIC_PLUGIN_NAME} findings {generic}"
        )


def assert_silent_f07(result: RunResult) -> None:
    """Classified success and no lint-policy-effect findings (all enabled Effect rules)."""
    generic = lint_policy_findings(result)
    effect = effect_plugin_findings(result)
    print(
        f"assert-silent-f07 exit={result.returncode} "
        f"generic={generic} effect={effect}",
        flush=True,
    )
    if effect:
        raise AssertionError(
            f"expected no lint-policy-effect findings; got {effect}"
        )
    if result.returncode != 0:
        raise HarnessError(
            "silence with only Effect rules enabled requires classified success; "
            "non-success with empty findings is not silence; "
            f"exit={result.returncode} generic={generic} "
            f"stderr={result.stderr_text!r}"
        )
    if generic:
        raise AssertionError(
            f"expected no lint-policy findings on the silent arm; generic={generic}"
        )
    assert_no_plugin_findings(result)


def assert_effect_classified_not_fired(result: RunResult, rule_name: str) -> None:
    """Named Effect rule silent; JSON is classified. Other Effect rules may fire."""
    classified = diagnostics(result)
    effect = effect_plugin_findings(result)
    print(
        f"assert-effect-classified-not-fired {rule_name} "
        f"exit={result.returncode} n={len(classified)} effect={effect}",
        flush=True,
    )
    if effect_rule_fired(effect, rule_name):
        raise AssertionError(
            f"Effect rule {rule_name} must not fire; got {effect}"
        )


def _read_source_bytes(path: str | Path) -> bytes:
    src = Path(path)
    try:
        return src.read_bytes()
    except OSError as exc:
        raise HarnessError(f"cannot read source bytes {src}: {exc}") from exc


def assert_effect_fix_preserves_source(
    path: str | Path,
    before: bytes,
    result: RunResult,
    rule_name: str,
) -> None:
    """Source bytes unchanged under ``--fix`` and the named Effect rule still fires.

    The byte observer sits outside the product. A deliberate rewrite in
    the test process must be visible to the same reader (positive control).
    """
    src = Path(path)
    after = _read_source_bytes(src)
    print(
        f"effect-fix-preserve {src.name} before_len={len(before)} "
        f"after_len={len(after)} equal={after == before} "
        f"exit={result.returncode}",
        flush=True,
    )
    if after != before:
        raise AssertionError(
            "host fix mode must leave the violating construct's source bytes "
            f"unchanged; path={src}"
        )
    assert_effect_fired(result, rule_name)
    control = src.with_name(src.name + ".observer-control")
    try:
        control.write_bytes(b"marker-a")
        first = _read_source_bytes(control)
        control.write_bytes(b"marker-b")
        second = _read_source_bytes(control)
    except OSError as exc:
        raise HarnessError(
            f"cannot exercise byte observer on {control}: {exc}"
        ) from exc
    if first == second:
        raise AssertionError(
            "byte observer did not detect a deliberate rewrite in the test process"
        )


def fire_unique(
    ws: Workspace,
    effect_specifier: str | Path,
    source: str,
    rule_name: str,
    *,
    prefix: str,
    ext: str = "ts",
    rel: str | None = None,
    rules: Sequence[str] = EFFECT_RULE_NAMES,
) -> tuple[Path, RunResult]:
    path, result = lint_f07_source(
        ws,
        effect_specifier,
        source,
        prefix=prefix,
        ext=ext,
        rel=rel,
        rules=rules,
    )
    print(f"fire-unique {rule_name} path={path}", flush=True)
    assert_only_effect_rule(result, rule_name)
    return path, result


def silent_all(
    ws: Workspace,
    effect_specifier: str | Path,
    source: str,
    *,
    prefix: str,
    ext: str = "ts",
    rel: str | None = None,
) -> tuple[Path, RunResult]:
    path, result = lint_f07_source(
        ws,
        effect_specifier,
        source,
        prefix=prefix,
        ext=ext,
        rel=rel,
    )
    print(f"silent-all path={path}", flush=True)
    assert_silent_f07(result)
    return path, result


def run_effect_fix(
    ws: Workspace,
    effect_specifier: str | Path,
    source: str,
    rule_name: str,
    *,
    prefix: str,
    ext: str = "ts",
    rel: str | None = None,
) -> tuple[Path, RunResult]:
    """Lint with host ``--fix``; require unchanged bytes and only that Effect rule."""
    path = write_f07_source(ws, source, prefix=prefix, ext=ext, rel=rel)
    before = _read_source_bytes(path)
    result = lint_f07(ws, [path], effect_specifier, fix=True)
    print(f"effect-fix {rule_name} path={path}", flush=True)
    assert_effect_fix_preserves_source(path, before, result, rule_name)
    assert_only_effect_rule(result, rule_name)
    return path, result


def fire_public_and_twin(
    ws: Workspace,
    effect_specifier: str | Path,
    public_source: str,
    twin_source: str,
    rule_name: str,
    *,
    prefix: str,
    ext: str = "ts",
    rel_public: str | None = None,
    rel_twin: str | None = None,
) -> tuple[tuple[Path, RunResult], tuple[Path, RunResult]]:
    """Lint the public oracle and its generated twin; both must fire only *rule_name*."""
    public_path, public_result = fire_unique(
        ws,
        effect_specifier,
        public_source,
        rule_name,
        prefix=f"{prefix}-public",
        ext=ext,
        rel=rel_public,
    )
    twin_path, twin_result = fire_unique(
        ws,
        effect_specifier,
        twin_source,
        rule_name,
        prefix=f"{prefix}-twin",
        ext=ext,
        rel=rel_twin,
    )
    assert_only_effect_rule(public_result, rule_name)
    assert_only_effect_rule(twin_result, rule_name)
    return (public_path, public_result), (twin_path, twin_result)


def fire_public_only(
    ws: Workspace,
    effect_specifier: str | Path,
    rule_name: str,
    *,
    prefix: str,
) -> tuple[Path, RunResult]:
    """Live baseline: the public violator fails lint with only *rule_name* enabled."""
    if rule_name == RULE_TAG_CMP:
        source = snippet_manual_tag_comparison()
        rel = None
    elif rule_name == RULE_ERR_TAG:
        source = snippet_effect_catch_error_comparison()
        rel = None
    elif rule_name == RULE_CONSTRUCT:
        source = snippet_manual_tagged_object()
        rel = None
    elif rule_name == RULE_MATCH:
        source = snippet_chained_same_value()
        rel = None
    elif rule_name == RULE_SVC:
        source = snippet_public_runtime_import()
        rel = "src/runtime.ts"
    else:
        raise HarnessError(f"unknown Effect rule {rule_name!r}")
    return fire_unique(
        ws,
        effect_specifier,
        source,
        rule_name,
        prefix=prefix,
        rel=rel,
        rules=[rule_name],
    )


def fire_spelled_catch_handler(
    ws: Workspace,
    effect_specifier: str | Path,
    source: str,
    *,
    prefix: str,
) -> tuple[Path, RunResult]:
    """Spelled Effect.catch / catchAll / catchIf is a catch handler.

    All five Effect rules on: ``no-manual-effect-error-tag`` fires and
    ``no-manual-tag-comparison`` does not. Identifier spelling is the
    condition (L253, L265); do not resolve aliases here.
    """
    path, result = fire_unique(
        ws,
        effect_specifier,
        source,
        RULE_ERR_TAG,
        prefix=prefix,
    )
    print(f"spelled-catch-handler path={path}", flush=True)
    assert_effect_classified_not_fired(result, RULE_TAG_CMP)
    return path, result


def fire_error_tag_only(
    ws: Workspace,
    effect_specifier: str | Path,
    source: str,
    *,
    prefix: str,
) -> tuple[Path, RunResult]:
    """Live baseline: spelled catch-handler ``_tag`` fails with only error-tag on.

    Only ``no-manual-effect-error-tag`` is enabled. A plugin that dumps every
    ``_tag``-to-string comparison onto ``no-manual-tag-comparison`` cannot
    satisfy this arm, because that rule is not enabled.
    """
    path, result = fire_unique(
        ws,
        effect_specifier,
        source,
        RULE_ERR_TAG,
        prefix=prefix,
        rules=[RULE_ERR_TAG],
    )
    print(f"error-tag-only path={path}", flush=True)
    return path, result


def fire_application_make_import(
    ws: Workspace,
    effect_specifier: str | Path,
    source: str,
    *,
    prefix: str,
    ext: str,
) -> tuple[Path, RunResult]:
    """Live baseline: named relative make+uppercase import in an application file of *ext*.

    Only ``no-service-constructor-imports`` is enabled. The path has no
    ``.test.`` / ``.spec.`` suffix, so L258's exemption does not apply.
    Holds *ext* fixed so a plugin that only reports ``.ts`` cannot pass a
    later silent arm on ``.spec.`` / ``.test.`` of the same extension.
    """
    path, result = fire_unique(
        ws,
        effect_specifier,
        source,
        RULE_SVC,
        prefix=prefix,
        ext=ext,
        rel=application_rel(ext=ext),
        rules=[RULE_SVC],
    )
    print(f"application-make-import ext={ext} path={path}", flush=True)
    return path, result


# ---------------------------------------------------------------------------
# Spans (Rule 1: missing / duplicated fragment is not silence)
# ---------------------------------------------------------------------------


def unique_span(source: str, fragment: str) -> tuple[int, int]:
    start = source.find(fragment)
    if start < 0:
        raise HarnessError(
            f"fragment {fragment!r} not found in source {source!r}"
        )
    if source.find(fragment, start + 1) >= 0:
        raise HarnessError(
            f"fragment {fragment!r} occurs more than once in source {source!r}"
        )
    return start, start + len(fragment)


def assert_effect_identifies_span(
    source: str,
    result: RunResult,
    rule_name: str,
    hit_span: tuple[int, int],
    miss_span: tuple[int, int],
) -> int:
    """A finding for *rule_name* sits in *hit_span* and none sits in *miss_span*.

    Hard-fails on missing line/column. Does not pin a finding count.
    Returns the smallest sortable offset in the hit span.
    """
    assert_effect_fired(result, rule_name)
    items = effect_rule_diagnostics(result, rule_name)
    hits: list[int] = []
    for item in items:
        offset = diagnostic_offset(source, item)
        miss_start, miss_end = miss_span
        if miss_start <= offset < miss_end:
            raise AssertionError(
                f"{rule_name} must not identify the allowed construct; "
                f"offset={offset} miss_span={miss_span}"
            )
        hit_start, hit_end = hit_span
        if hit_start <= offset < hit_end:
            hits.append(offset)
    print(
        f"identify-span rule={rule_name} hits={hits} "
        f"hit_span={hit_span} miss_span={miss_span}",
        flush=True,
    )
    if not hits:
        raise AssertionError(
            f"{rule_name} must identify the offending construct; "
            f"hit_span={hit_span} source={source!r}"
        )
    return min(hits)


# ---------------------------------------------------------------------------
# Unique violators (one construct class per Effect rule)
# ---------------------------------------------------------------------------


def unique_violator(
    rule_name: str, *, twin: bool = False
) -> tuple[str, str | None, str]:
    """Return ``(source, rel_or_none, ext)`` unique among the five Effect rules."""
    if rule_name == RULE_TAG_CMP:
        source = (
            snippet_manual_tag_comparison()
            if not twin
            else snippet_tag_member_equality(twin=True)
        )
        return source, None, "ts"
    if rule_name == RULE_ERR_TAG:
        return snippet_effect_catch_error_comparison(twin=twin), None, "ts"
    if rule_name == RULE_CONSTRUCT:
        return snippet_manual_tagged_object(twin=twin), None, "ts"
    if rule_name == RULE_MATCH:
        return snippet_chained_same_value(twin=twin), None, "ts"
    if rule_name == RULE_SVC:
        return snippet_make_uppercase_import(twin=twin), application_rel(), "ts"
    raise HarnessError(f"unknown Effect rule {rule_name!r}")


# ---------------------------------------------------------------------------
# Tag-comparison snippets
# ---------------------------------------------------------------------------


def snippet_tag_member_equality(
    *,
    twin: bool = False,
    computed: bool = False,
    op: str = "===",
    reversed_ops: bool = False,
) -> str:
    tag = "Ready" if not twin else fresh_ident("Tag")
    recv = "value" if not twin else fresh_ident("v")
    member = f'{recv}["_tag"]' if computed else f"{recv}._tag"
    literal = f'"{tag}"'
    expr = f"{literal} {op} {member}" if reversed_ops else f"{member} {op} {literal}"
    return f"void ({expr});\n"


def snippet_reversed_computed_inequality(*, twin: bool = False) -> str:
    if not twin:
        return 'void ("Ready" !== value["_tag"]);\n'
    return snippet_tag_member_equality(twin=True, computed=True, op="!==", reversed_ops=True)


def snippet_computed_tag_equality(*, twin: bool = False) -> str:
    if not twin:
        return 'void (value["_tag"] === "Ready");\n'
    return snippet_tag_member_equality(twin=True, computed=True)


def snippet_reversed_identifier_tag_equality(*, twin: bool = False) -> str:
    if not twin:
        return 'void ("Ready" === value._tag);\n'
    return snippet_tag_member_equality(twin=True, reversed_ops=True)


def snippet_tag_loose_equality(*, twin: bool = False) -> str:
    return snippet_tag_member_equality(twin=twin, op="==")


def snippet_tag_loose_inequality(*, twin: bool = False) -> str:
    return snippet_tag_member_equality(twin=twin, op="!=")


def snippet_switch_on_tag(*, twin: bool = False, computed: bool = False) -> str:
    if not twin and not computed:
        return 'switch (value._tag) { case "Ready": handleReady(value); }\n'
    if not twin and computed:
        return 'switch (value["_tag"]) { case "Ready": handleReady(value); }\n'
    tag = fresh_ident("Tag")
    recv = fresh_ident("v")
    handle = fresh_ident("h")
    disc = f'{recv}["_tag"]' if computed else f"{recv}._tag"
    return f'switch ({disc}) {{ case "{tag}": {handle}({recv}); }}\n'


def snippet_predicate_is_tagged(*, twin: bool = False) -> str:
    tag = "Ready" if not twin else fresh_ident("Tag")
    recv = "value" if not twin else fresh_ident("v")
    return f'Predicate.isTagged("{tag}")({recv});\n'


def snippet_status_comparison(*, twin: bool = False) -> str:
    member = "status" if not twin else fresh_ident("m")
    tag = "Ready" if not twin else fresh_ident("Tag")
    recv = "value" if not twin else fresh_ident("v")
    return f'void ({recv}.{member} === "{tag}");\n'


def snippet_tag_vs_variable(*, twin: bool = False) -> str:
    recv = "value" if not twin else fresh_ident("v")
    var = "tag" if not twin else fresh_ident("t")
    return f"void ({recv}._tag === {var});\n"


def snippet_tag_vs_non_string() -> str:
    return "void (value._tag === 1);\n"


def snippet_tag_vs_template() -> str:
    return "void (value._tag === `Ready`);\n"


def snippet_status_then_tag() -> IdentifiedNeighbor:
    status = 'void (value.status === "Ready");'
    tag = 'void (value._tag === "Ready");'
    source = f"{status}\n{tag}\n"
    return IdentifiedNeighbor(
        source=source,
        hit_span=unique_span(source, tag),
        miss_span=unique_span(source, status),
    )


def snippet_tag_then_status() -> IdentifiedNeighbor:
    tag = 'void (value._tag === "Ready");'
    status = 'void (value.status === "Ready");'
    source = f"{tag}\n{status}\n"
    return IdentifiedNeighbor(
        source=source,
        hit_span=unique_span(source, tag),
        miss_span=unique_span(source, status),
    )


# ---------------------------------------------------------------------------
# Catch-handler snippets
# ---------------------------------------------------------------------------


def snippet_effect_catch_error_comparison(*, twin: bool = False) -> str:
    if not twin:
        return (
            'Effect.catch((error) => error._tag === "NotFound" ? recover : fail);\n'
        )
    param = fresh_ident("err")
    tag = fresh_ident("Tag")
    recover = fresh_ident("ok")
    fail = fresh_ident("no")
    return (
        f'Effect.catch(({param}) => {param}._tag === "{tag}" '
        f"? {recover} : {fail});\n"
    )


def snippet_effect_catchall_reason_comparison(*, twin: bool = False) -> str:
    if not twin:
        return (
            "Effect.catchAll(function (error) { "
            'return error.reason._tag === "Timeout" ? retry : fail; });\n'
        )
    param = fresh_ident("err")
    tag = fresh_ident("Tag")
    retry = fresh_ident("again")
    fail = fresh_ident("no")
    return (
        f"Effect.catchAll(function ({param}) {{ "
        f'return {param}.reason._tag === "{tag}" ? {retry} : {fail}; }});\n'
    )


def snippet_effect_catchall_error_comparison(*, twin: bool = False) -> str:
    if not twin:
        return (
            'Effect.catchAll((error) => error._tag === "NotFound" '
            "? recover : fail);\n"
        )
    param = fresh_ident("err")
    tag = fresh_ident("Tag")
    recover = fresh_ident("ok")
    fail = fresh_ident("no")
    return (
        f'Effect.catchAll(({param}) => {param}._tag === "{tag}" '
        f"? {recover} : {fail});\n"
    )


def snippet_effect_catch_function_error(*, twin: bool = False) -> str:
    if not twin:
        return (
            "Effect.catch(function (error) { "
            'return error._tag === "NotFound" ? recover : fail; });\n'
        )
    param = fresh_ident("err")
    tag = fresh_ident("Tag")
    recover = fresh_ident("ok")
    fail = fresh_ident("no")
    return (
        f"Effect.catch(function ({param}) {{ "
        f'return {param}._tag === "{tag}" ? {recover} : {fail}; }});\n'
    )


def snippet_catch_error_comparison_expression(*, twin: bool = False) -> str:
    if not twin:
        return 'Effect.catch((error) => error._tag === "NotFound");\n'
    param = fresh_ident("err")
    tag = fresh_ident("Tag")
    return f'Effect.catch(({param}) => {param}._tag === "{tag}");\n'


def snippet_effect_catchif_error_switch(*, twin: bool = False) -> str:
    pred = fresh_ident("pred")
    if not twin:
        return (
            f"Effect.catchIf({pred}, (error) => {{ "
            'switch (error._tag) { case "NotFound": return recover; } });\n'
        )
    param = fresh_ident("err")
    tag = fresh_ident("Tag")
    recover = fresh_ident("ok")
    return (
        f"Effect.catchIf({pred}, ({param}) => {{ "
        f'switch ({param}._tag) {{ case "{tag}": return {recover}; }} }});\n'
    )


def snippet_effect_catch_reason_switch(*, twin: bool = False) -> str:
    if not twin:
        return (
            "Effect.catch((error) => { "
            'switch (error.reason._tag) { case "Timeout": return retry; } });\n'
        )
    param = fresh_ident("err")
    tag = fresh_ident("Tag")
    retry = fresh_ident("again")
    return (
        f"Effect.catch(({param}) => {{ "
        f'switch ({param}.reason._tag) {{ case "{tag}": return {retry}; }} }});\n'
    )


def snippet_renamed_effect_catch(*, twin: bool = False) -> str:
    alias = "Eff" if not twin else fresh_ident("Bind")
    param = "error" if not twin else fresh_ident("err")
    tag = "NotFound" if not twin else fresh_ident("Tag")
    recover = "recover" if not twin else fresh_ident("ok")
    fail = "fail" if not twin else fresh_ident("no")
    return (
        f'import {{ Effect as {alias} }} from "effect";\n'
        f"{alias}.catch(({param}) => {param}._tag === \"{tag}\" "
        f"? {recover} : {fail});\n"
    )


def snippet_renamed_effect_catchall_reason(*, twin: bool = False) -> str:
    alias = "Eff" if not twin else fresh_ident("Bind")
    param = "error" if not twin else fresh_ident("err")
    tag = "Timeout" if not twin else fresh_ident("Tag")
    retry = "retry" if not twin else fresh_ident("again")
    fail = "fail" if not twin else fresh_ident("no")
    return (
        f'import {{ Effect as {alias} }} from "effect";\n'
        f"{alias}.catchAll(function ({param}) {{ "
        f'return {param}.reason._tag === "{tag}" ? {retry} : {fail}; }});\n'
    )


def snippet_top_level_error_tag(*, twin: bool = False) -> str:
    if not twin:
        return 'error._tag === "NotFound";\n'
    param = fresh_ident("err")
    tag = fresh_ident("Tag")
    return f'{param}._tag === "{tag}";\n'


def snippet_effect_catch_tag(*, twin: bool = False) -> str:
    if not twin:
        return 'Effect.catchTag("NotFound", recover);\n'
    tag = fresh_ident("Tag")
    recover = fresh_ident("ok")
    return f'Effect.catchTag("{tag}", {recover});\n'


def snippet_catch_tag_nested_reason(*, twin: bool = False) -> str:
    if not twin:
        return (
            'Effect.catchTag("Wrapper", (error) => '
            'error.reason._tag === "Timeout" ? retry : fail);\n'
        )
    outer = fresh_ident("Tag")
    inner = fresh_ident("Why")
    param = fresh_ident("err")
    retry = fresh_ident("again")
    fail = fresh_ident("no")
    return (
        f'Effect.catchTag("{outer}", ({param}) => '
        f'{param}.reason._tag === "{inner}" ? {retry} : {fail});\n'
    )


def snippet_variable_tag_in_catch(*, twin: bool = False) -> str:
    if not twin:
        return "Effect.catch((error) => error._tag === tag ? recover : fail);\n"
    param = fresh_ident("err")
    var = fresh_ident("t")
    recover = fresh_ident("ok")
    fail = fresh_ident("no")
    return (
        f"Effect.catch(({param}) => {param}._tag === {var} "
        f"? {recover} : {fail});\n"
    )


def snippet_catch_tagged_error_construct() -> CatchConstructSnippet:
    construct = 'error._tag === "NotFound"'
    source = f"Effect.catch((error) => {construct} ? recover : fail);\n"
    return CatchConstructSnippet(
        source,
        unique_span(source, construct),
        unique_span(source, "Effect.catch"),
    )


def snippet_catch_tagged_reason_construct() -> CatchConstructSnippet:
    construct = 'error.reason._tag === "NotFound"'
    source = f"Effect.catch((error) => {construct} ? recover : fail);\n"
    return CatchConstructSnippet(
        source,
        unique_span(source, construct),
        unique_span(source, "Effect.catch"),
    )


# ---------------------------------------------------------------------------
# Tagged-construction snippets
# ---------------------------------------------------------------------------


def snippet_manual_tagged_object(*, twin: bool = False, style: str = "ident") -> str:
    tag = "Ready" if not twin else fresh_ident("Tag")
    extra = "payload" if not twin else fresh_ident("field")
    if style == "ident":
        body = f'_tag: "{tag}", {extra}'
    elif style == "computed":
        body = f'["_tag"]: "{tag}"'
    elif style == "quoted":
        body = f'"_tag": "{tag}"'
    else:
        raise HarnessError(f"unknown tagged-object style {style!r}")
    return f"const value = {{ {body} }};\n"


def snippet_match_when(*, twin: bool = False) -> str:
    tag = "Ready" if not twin else fresh_ident("Tag")
    handle = "handleReady" if not twin else fresh_ident("h")
    return f'Match.when({{ _tag: "{tag}" }}, {handle});\n'


def snippet_match_when_plus_non_match_tagged(
    *, twin: bool = False
) -> IdentifiedNeighbor:
    tag = "Ready" if not twin else fresh_ident("Tag")
    handle = "handleReady" if not twin else fresh_ident("h")
    extra = "payload" if not twin else fresh_ident("field")
    other = "other" if not twin else fresh_ident("fn")
    match_obj = f'{{ _tag: "{tag}" }}'
    other_obj = f'{{ _tag: "{tag}", {extra} }}'
    match_call = f"Match.when({match_obj}, {handle})"
    other_call = f"{other}({other_obj})"
    source = f"{match_call};\n{other_call};\n"
    return IdentifiedNeighbor(
        source=source,
        hit_span=unique_span(source, other_obj),
        miss_span=unique_span(source, match_call),
    )


def snippet_match_not(*, twin: bool = False) -> str:
    tag = "Pending" if not twin else fresh_ident("Tag")
    return f'Match.not({{ _tag: "{tag}" }});\n'


def snippet_ready_make(*, twin: bool = False) -> str:
    ctor = "Ready" if not twin else fresh_ident("Ctor")
    field = "value" if not twin else fresh_ident("v")
    return f"{ctor}.make({{ {field} }});\n"


def snippet_new_not_found(*, twin: bool = False) -> str:
    ctor = "NotFound" if not twin else fresh_ident("Err")
    field = "id" if not twin else fresh_ident("k")
    return f"new {ctor}({{ {field} }});\n"


def snippet_variable_tag_object(*, twin: bool = False) -> str:
    tag = "tag" if not twin else fresh_ident("t")
    extra = "value" if not twin else fresh_ident("v")
    return f"const built = {{ _tag: {tag}, {extra} }};\n"


def snippet_aliased_match_when(*, twin: bool = False) -> str:
    alias = "M" if not twin else fresh_ident("Mat")
    tag = "Ready" if not twin else fresh_ident("Tag")
    handle = "handleReady" if not twin else fresh_ident("h")
    return (
        f'import {{ Match as {alias} }} from "effect";\n'
        f'{alias}.when({{ _tag: "{tag}" }}, {handle});\n'
    )


def snippet_aliased_match_not(*, twin: bool = False) -> str:
    alias = "M" if not twin else fresh_ident("Mat")
    tag = "Pending" if not twin else fresh_ident("Tag")
    return (
        f'import {{ Match as {alias} }} from "effect";\n'
        f'{alias}.not({{ _tag: "{tag}" }});\n'
    )


# ---------------------------------------------------------------------------
# prefer-effect-match snippets
# ---------------------------------------------------------------------------


def snippet_chained_same_value(*, twin: bool = False) -> str:
    if not twin:
        return 'kind === "a" ? first : kind === "b" ? second : fallback;\n'
    ident = fresh_ident("k")
    a = fresh_ident("a")
    b = fresh_ident("b")
    first = fresh_ident("x")
    second = fresh_ident("y")
    fallback = fresh_ident("z")
    return (
        f'{ident} === "{a}" ? {first} : {ident} === "{b}" '
        f"? {second} : {fallback};\n"
    )


def snippet_template_mixed_chain(*, twin: bool = False) -> str:
    if not twin:
        return "`a` !== kind ? first : `b` === kind ? second : fallback;\n"
    ident = fresh_ident("k")
    a = fresh_ident("a")
    b = fresh_ident("b")
    first = fresh_ident("x")
    second = fresh_ident("y")
    fallback = fresh_ident("z")
    return (
        f"`{a}` !== {ident} ? {first} : `{b}` === {ident} "
        f"? {second} : {fallback};\n"
    )


def snippet_template_same_order_chain(*, twin: bool = False) -> str:
    if not twin:
        return "kind === `a` ? first : kind === `b` ? second : fallback;\n"
    ident = fresh_ident("k")
    a = fresh_ident("a")
    b = fresh_ident("b")
    first = fresh_ident("x")
    second = fresh_ident("y")
    fallback = fresh_ident("z")
    return (
        f"{ident} === `{a}` ? {first} : {ident} === `{b}` "
        f"? {second} : {fallback};\n"
    )


def snippet_reversed_string_chain(*, twin: bool = False) -> str:
    if not twin:
        return '"a" === kind ? first : "b" === kind ? second : fallback;\n'
    ident = fresh_ident("k")
    a = fresh_ident("a")
    b = fresh_ident("b")
    first = fresh_ident("x")
    second = fresh_ident("y")
    fallback = fresh_ident("z")
    return (
        f'"{a}" === {ident} ? {first} : "{b}" === {ident} '
        f"? {second} : {fallback};\n"
    )


def snippet_loose_numeric_chain() -> str:
    ident = fresh_ident("n")
    first = fresh_ident("x")
    second = fresh_ident("y")
    fallback = fresh_ident("z")
    return f"{ident} == 1 ? {first} : {ident} == 2 ? {second} : {fallback};\n"


def snippet_loose_inequality_chain(*, twin: bool = False) -> str:
    if not twin:
        return 'kind != "a" ? first : kind != "b" ? second : fallback;\n'
    ident = fresh_ident("k")
    a = fresh_ident("a")
    b = fresh_ident("b")
    first = fresh_ident("x")
    second = fresh_ident("y")
    fallback = fresh_ident("z")
    return (
        f'{ident} != "{a}" ? {first} : {ident} != "{b}" '
        f"? {second} : {fallback};\n"
    )


def snippet_member_chain(*, twin: bool = False) -> str:
    obj = "foo" if not twin else fresh_ident("o")
    prop = "bar" if not twin else fresh_ident("p")
    a = "a" if not twin else fresh_ident("a")
    b = "b" if not twin else fresh_ident("b")
    first = "first" if not twin else fresh_ident("x")
    second = "second" if not twin else fresh_ident("y")
    fallback = "fallback" if not twin else fresh_ident("z")
    recv = f"{obj}.{prop}"
    return (
        f'{recv} === "{a}" ? {first} : {recv} === "{b}" '
        f"? {second} : {fallback};\n"
    )


def snippet_false_chain_nested_true(*, twin: bool = False) -> str:
    if not twin:
        return (
            'kind === "a" ? (other === "x" ? second : fallback) : '
            'kind === "b" ? third : last;\n'
        )
    kind = fresh_ident("k")
    other = fresh_ident("o")
    a = fresh_ident("a")
    x = fresh_ident("x")
    b = fresh_ident("b")
    second = fresh_ident("s")
    fallback = fresh_ident("f")
    third = fresh_ident("t")
    last = fresh_ident("l")
    return (
        f'{kind} === "{a}" ? ({other} === "{x}" ? {second} : {fallback}) : '
        f'{kind} === "{b}" ? {third} : {last};\n'
    )


def snippet_single_ternary(*, twin: bool = False) -> str:
    if not twin:
        return 'kind === "a" ? first : fallback;\n'
    ident = fresh_ident("k")
    a = fresh_ident("a")
    first = fresh_ident("x")
    fallback = fresh_ident("z")
    return f'{ident} === "{a}" ? {first} : {fallback};\n'


def snippet_different_names_ternary(*, twin: bool = False) -> str:
    if not twin:
        return 'kind === "a" ? first : other === "b" ? second : fallback;\n'
    kind = fresh_ident("k")
    other = fresh_ident("o")
    a = fresh_ident("a")
    b = fresh_ident("b")
    first = fresh_ident("x")
    second = fresh_ident("y")
    fallback = fresh_ident("z")
    return (
        f'{kind} === "{a}" ? {first} : {other} === "{b}" '
        f"? {second} : {fallback};\n"
    )


def snippet_true_branch_nest(*, twin: bool = False) -> str:
    if not twin:
        return 'kind === "a" ? (kind === "b" ? second : fallback) : other;\n'
    ident = fresh_ident("k")
    a = fresh_ident("a")
    b = fresh_ident("b")
    second = fresh_ident("y")
    fallback = fresh_ident("z")
    other = fresh_ident("o")
    return (
        f'{ident} === "{a}" ? ({ident} === "{b}" ? {second} : {fallback}) '
        f": {other};\n"
    )


def snippet_non_literal_nested(*, twin: bool = False) -> str:
    if not twin:
        return "condition ? first : otherCondition ? second : fallback;\n"
    cond = fresh_ident("c")
    other = fresh_ident("d")
    first = fresh_ident("x")
    second = fresh_ident("y")
    fallback = fresh_ident("z")
    return f"{cond} ? {first} : {other} ? {second} : {fallback};\n"


# ---------------------------------------------------------------------------
# Service-constructor import snippets
# ---------------------------------------------------------------------------


def snippet_make_uppercase_import(
    *,
    twin: bool = False,
    specifier: str | None = None,
    imported: str | None = None,
    local: str | None = None,
) -> str:
    name = imported if imported is not None else (
        "makeIssueService" if not twin else generated_make_uppercase()
    )
    spec = specifier if specifier is not None else (
        "./issue-service.ts" if not twin else f"./{fresh_ident('mod')}.ts"
    )
    if local is None:
        return f'import {{ {name} }} from "{spec}";\n'
    return f'import {{ {name} as {local} }} from "{spec}";\n'


def snippet_public_runtime_import() -> str:
    return 'import { makeIssueService } from "./issue-service.ts";\n'


def snippet_package_make_import(*, twin: bool = False) -> str:
    if not twin:
        return 'import { makeExecutionMemo } from "alchemy/Runtime/ExecutionMemo";\n'
    name = generated_make_uppercase()
    spec = f"{fresh_ident('pkg')}/{fresh_ident('Mod')}"
    return f'import {{ {name} }} from "{spec}";\n'


def snippet_path_alias_make_import() -> str:
    return 'import { makeIssueService } from "#services/issue";\n'


def snippet_default_make_import(*, twin: bool = False) -> str:
    name = "makeIssueService" if not twin else generated_make_uppercase()
    spec = "./issue-service.ts" if not twin else f"./{fresh_ident('mod')}.ts"
    return f'import {name} from "{spec}";\n'


def snippet_reverse_named_alias(*, twin: bool = False) -> str:
    imported = "createIssueService" if not twin else fresh_ident("create")
    local = "makeIssueService" if not twin else generated_make_uppercase()
    spec = "./issue-service.ts" if not twin else f"./{fresh_ident('mod')}.ts"
    return f'import {{ {imported} as {local} }} from "{spec}";\n'


def snippet_make_lowercase_import(*, twin: bool = False) -> str:
    if not twin:
        return 'import { makeissueService } from "./issue-service.ts";\n'
    name = generated_make_lowercase()
    spec = f"./{fresh_ident('mod')}.ts"
    return f'import {{ {name} }} from "{spec}";\n'


def snippet_import_make_alone() -> str:
    return 'import { make } from "./factory.ts";\n'


def snippet_static_constructor_call() -> str:
    other = generated_make_lowercase()
    spec = f"./{fresh_ident('mod')}.ts"
    return (
        f'import {{ {other} }} from "{spec}";\n'
        'WorkspaceName.make("name");\n'
    )


def snippet_neighbor_imports() -> IdentifiedNeighbor:
    hit = 'import { makeIssueService } from "./issue-service.ts";'
    miss = 'import { makeissueService } from "./other.ts";'
    source = f"{hit}\n{miss}\n"
    return IdentifiedNeighbor(
        source=source,
        hit_span=unique_span(source, "makeIssueService"),
        miss_span=unique_span(source, "makeissueService"),
    )
