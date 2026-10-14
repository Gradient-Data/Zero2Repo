# feature: F03
"""Observation helpers for the four type-evidence checks.

Import side effects: none. Process spawn and filesystem writes happen only
when a caller invokes a function below.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Sequence

from _harness import (
    GENERIC_PLUGIN_NAME,
    HarnessError,
    RunResult,
    Workspace,
    diagnostics,
    generic_plugin,
    rule_key,
)
from F01_helpers import (
    lint_policy_findings,
    assert_no_plugin_findings,
    effect_plugin_findings,
    ensure_host_plugin_modules,
    fresh_ident,
    rule_fired,
)

F03_RULE_NAMES: tuple[str, ...] = (
    "no-chained-type-assertions",
    "no-known-value-widening",
    "no-widen-then-assert",
    "require-safety-comment-for-type-assertion",
)

RULE_CHAIN = "no-chained-type-assertions"
RULE_WIDEN = "no-known-value-widening"
RULE_THEN = "no-widen-then-assert"
RULE_SAFE = "require-safety-comment-for-type-assertion"


def rules_omitting(rule_name: str) -> tuple[str, ...]:
    """The four rules with *rule_name* left out of the consuming configuration.

    The plugin stays registered. The returned names are the rules that stay
    on. A name outside these four is not a configuration this feature builds.
    """
    if rule_name not in F03_RULE_NAMES:
        raise AssertionError(
            f"{rule_name!r} is not one of the four rules {F03_RULE_NAMES}"
        )
    kept = tuple(name for name in F03_RULE_NAMES if name != rule_name)
    if len(kept) != len(F03_RULE_NAMES) - 1 or rule_name in kept:
        raise AssertionError(
            f"omitting {rule_name!r} did not leave the other rules on; got {kept}"
        )
    return kept

PUBLIC_SAFETY_TEXT = "parsed before branding."


def safety_comment(*, marker: str = "SAFETY", text: str | None = None) -> str:
    body = PUBLIC_SAFETY_TEXT if text is None else text
    return f"// {marker}: {body}"


def generated_justification() -> str:
    return fresh_ident("why")


def with_safety(body: str, *, text: str | None = None, marker: str = "SAFETY") -> str:
    reason = generated_justification() if text is None else text
    return f"{safety_comment(marker=marker, text=reason)}\n{body}"


def lint_f03(
    ws: Workspace,
    files: Sequence[str | Path],
    specifier: str | Path,
    *,
    rules: Sequence[str] = F03_RULE_NAMES,
    markers: Sequence[str] | None = None,
    fix: bool = False,
) -> RunResult:
    """Register lint-policy; enable *rules* at error; optional markers and ``--fix``."""
    ensure_host_plugin_modules(ws)
    print(
        f"lint-f03 specifier={specifier} rules={list(rules)} "
        f"markers={None if markers is None else list(markers)} "
        f"fix={fix} files={list(files)}",
        flush=True,
    )
    plugin = generic_plugin(specifier=specifier, root=ws.root)
    mapping: dict[str, object] = {
        rule_key(GENERIC_PLUGIN_NAME, name): "error" for name in rules
    }
    if markers is not None:
        mapping[rule_key(GENERIC_PLUGIN_NAME, RULE_SAFE)] = [
            "error",
            {"markers": list(markers)},
        ]
    return ws.lint(files, plugins=[plugin], rules=mapping, fix=fix)


def write_f03_source(
    ws: Workspace,
    source: str,
    *,
    prefix: str = "f03",
) -> Path:
    rel = f"{prefix}-{fresh_ident('s')}.ts"
    print(f"write {rel}", flush=True)
    return ws.write(rel, source)


def lint_f03_source(
    ws: Workspace,
    specifier: str | Path,
    source: str,
    *,
    prefix: str = "f03",
    markers: Sequence[str] | None = None,
    fix: bool = False,
    rules: Sequence[str] = F03_RULE_NAMES,
) -> tuple[Path, RunResult]:
    path = write_f03_source(ws, source, prefix=prefix)
    result = lint_f03(
        ws, [path], specifier, rules=rules, markers=markers, fix=fix
    )
    print(f"lint {path.name} exit={result.returncode}", flush=True)
    return path, result


def f03_diagnostic_identity(result: RunResult) -> tuple[str, ...]:
    """Encounter-order rule names of one lint's classified diagnostics.

    Two runs are compared with each other. Only which rule reported is
    part of that identity. Message wording and the node that carries the
    span are not. A probe that cannot be classified raises.
    """
    found = diagnostics(result)
    return tuple(item.rule for item in found)


def assert_silent_f03(result: RunResult, rule_name: str) -> None:
    """Classified success and no finding from *rule_name* (F03 rules only)."""
    generic = lint_policy_findings(result)
    effect = effect_plugin_findings(result)
    print(
        f"assert-silent-f03 {rule_name} exit={result.returncode} "
        f"generic={generic} effect={effect}",
        flush=True,
    )
    if rule_fired(generic, rule_name):
        raise AssertionError(
            f"rule {rule_name} must not fire; got {generic}"
        )
    if result.returncode != 0:
        raise HarnessError(
            "silence with only F03 rules enabled requires classified success; "
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


def assert_classified_not_fired(result: RunResult, rule_name: str) -> None:
    """Named rule silent; JSON is classified. Other F03 rules may still fire."""
    classified = diagnostics(result)
    generic = lint_policy_findings(result)
    print(
        f"assert-classified-not-fired {rule_name} exit={result.returncode} "
        f"n={len(classified)} generic={generic}",
        flush=True,
    )
    if rule_fired(generic, rule_name):
        raise AssertionError(f"rule {rule_name} must not fire; got {generic}")


def command_parts(*, twin: bool = False) -> tuple[str, str, str, str, str]:
    command = "Command" if not twin else fresh_ident("Cmd")
    starter = "startCommand" if not twin else fresh_ident("run")
    key = "start" if not twin else fresh_ident("go")
    binding = "commands" if not twin else fresh_ident("table")
    header = f"type {command} = () => void;\n"
    return header, command, starter, key, binding


def known_object(key: str, starter: str) -> str:
    return f"{{ {key}: {starter} }}"


# ---------------------------------------------------------------------------
# A. Nested assertions
# ---------------------------------------------------------------------------


def snippet_parenthesized_chain(*, twin: bool = False) -> str:
    target = "User" if not twin else fresh_ident("Target")
    value = "input" if not twin else fresh_ident("val")
    return with_safety(f"void (({value} as unknown) as {target});\n")


def snippet_single_parenthesized_assertion(*, twin: bool = False) -> str:
    target = "User" if not twin else fresh_ident("Target")
    value = "input" if not twin else fresh_ident("val")
    return with_safety(f"void (({value} as {target}));\n")


def snippet_nested_angle_brackets(*, twin: bool = False) -> str:
    target = "User" if not twin else fresh_ident("Target")
    value = "input" if not twin else fresh_ident("val")
    return with_safety(f"void (<{target}>(<unknown>{value}));\n")


def snippet_nested_named_angle_brackets() -> str:
    """Parenthesized angle-bracket chain of two types, neither of them unknown.

    Same shape as ``<Target>(<unknown>value)``. A justification sits on the
    statement so a missing safety comment is not the failure. Both type names
    are fresh, so neither assertion type is the token ``unknown`` or ``const``.
    """
    outer = fresh_ident("Outer")
    inner = fresh_ident("Inner")
    value = fresh_ident("val")
    if outer in {"unknown", "const"} or inner in {"unknown", "const"} or outer == inner:
        raise AssertionError(
            "angle-bracket types must be two distinct names other than "
            f"unknown and const; outer={outer!r} inner={inner!r}"
        )
    source = with_safety(f"void (<{outer}>(<{inner}>{value}));\n")
    if "unknown" in source:
        raise AssertionError(
            "named angle-bracket chain must not contain the token unknown; "
            f"got {source!r}"
        )
    return source


def snippet_nested_angle_const_chain() -> str:
    """Parenthesized ``<const>(<const>…)`` chain with no comment.

    Both assertion types are the token const, written as angle brackets.
    The chain is not ``as const``. No justification is attached. The value
    name is fresh.
    """
    value = fresh_ident("val")
    if "const" in value or "unknown" in value or not value.isidentifier():
        raise AssertionError(
            f"the chained value must not be the token const; got {value!r}"
        )
    source = f"void (<const>(<const>{value}));\n"
    if "//" in source or "/*" in source or "*/" in source:
        raise AssertionError(
            "angle-bracket const chain must not contain a comment; "
            f"got {source!r}"
        )
    if " as " in source or "as const" in source:
        raise AssertionError(
            "angle-bracket const chain must not be an as const chain; "
            f"got {source!r}"
        )
    if source.count("<const>") != 2 or source.count("const") != 2:
        raise AssertionError(
            "angle-bracket const chain must be exactly two <const> "
            f"assertions; got {source!r}"
        )
    return source


def _two_non_const_types(left_prefix: str, right_prefix: str) -> tuple[str, str, str]:
    """Two fresh type names, neither ``const`` nor ``unknown``, plus a value."""
    left = fresh_ident(left_prefix)
    right = fresh_ident(right_prefix)
    value = fresh_ident("val")
    banned = {"unknown", "const"}
    if left in banned or right in banned or len({left, right, value}) < 3:
        raise AssertionError(
            "a nested chain needs two distinct types other than const and "
            f"unknown; left={left!r} right={right!r} value={value!r}"
        )
    return left, right, value


def _require_uncommented_non_const_chain(source: str, *, opens: str) -> str:
    """The chain has no comment and neither assertion type is const."""
    if "//" in source or "/*" in source or "*/" in source:
        raise AssertionError(
            f"uncommented chain must not contain a comment; got {source!r}"
        )
    if "const" in source or "unknown" in source:
        raise AssertionError(
            "uncommented chain must be two non-const types other than "
            f"unknown; got {source!r}"
        )
    if source.count(opens) != 2:
        raise AssertionError(
            f"uncommented chain must contain two {opens!r} assertions; "
            f"got {source!r}"
        )
    return source


def snippet_nested_as_without_comment() -> str:
    """Nested ``as`` chain of two non-const types and no justification.

    Same shape as ``value as Kind as Role``. Neither type is ``const`` or
    ``unknown``. No comment is attached, so the safety-comment rule applies
    to the chain as well as the chain rule.
    """
    first, second, value = _two_non_const_types("Kind", "Role")
    source = f"void ({value} as {first} as {second});\n"
    return _require_uncommented_non_const_chain(source, opens=" as ")


def snippet_nested_angle_without_comment() -> str:
    """Nested angle-bracket chain of two non-const types and no justification.

    Same shape as ``<Outer>(<Inner>value)``. Neither type is ``const`` or
    ``unknown``. No comment is attached, so the safety-comment rule applies
    to the chain as well as the chain rule.
    """
    outer, inner, value = _two_non_const_types("Outer", "Inner")
    source = f"void (<{outer}>(<{inner}>{value}));\n"
    return _require_uncommented_non_const_chain(source, opens="<")


def snippet_as_const_then_non_const(*, twin: bool = False) -> str:
    target = "User" if not twin else fresh_ident("Target")
    field = "id" if not twin else fresh_ident("slot")
    return with_safety(f"void (({{ {field}: 1 }} as const) as {target});\n")


def snippet_identifier_as_const_then_non_const() -> str:
    """Identifier ``as const as`` a non-const type, with a justification.

    The ``as const`` is not wrapped in parentheses. The second assertion is
    not ``const``. The comment sits on the statement so the safety-comment
    rule is not the failure. The parenthesized object mix stays a separate
    source.
    """
    value = fresh_ident("val")
    target = fresh_ident("Target")
    if (
        not value.isidentifier()
        or not target.isidentifier()
        or value == target
        or "const" in value
        or "const" in target
    ):
        raise AssertionError(
            "the chained value and the later type must be distinct "
            f"identifiers other than const; value={value!r} target={target!r}"
        )
    chain = f"{value} as const as {target}"
    source = with_safety(f"void ({chain});\n")
    if chain not in source:
        raise AssertionError(
            f"identifier chain must be written {chain!r}; got {source!r}"
        )
    if f"({value} as const)" in source or f"{value} as const)" in source:
        raise AssertionError(
            "as const must not sit inside parentheses; "
            f"got {source!r}"
        )
    if "as const as const" in source:
        raise AssertionError(
            "the assertion after as const must not be const; "
            f"got {source!r}"
        )
    if not source.startswith("// "):
        raise AssertionError(
            f"the chain needs a justification comment; got {source!r}"
        )
    return source


def snippet_nested_as_ending_in_as_const(*, twin: bool = False) -> str:
    target = "User" if not twin else fresh_ident("Target")
    value = "input" if not twin else fresh_ident("val")
    return with_safety(f"void ({value} as {target} as const);\n")


def snippet_nested_named_assertions(*, twin: bool = False) -> str:
    first = "User" if not twin else fresh_ident("Kind")
    second = "Admin" if not twin else fresh_ident("Role")
    value = "input" if not twin else fresh_ident("val")
    return with_safety(f"void ({value} as {first} as {second});\n")


def snippet_single_assertion(*, twin: bool = False) -> str:
    target = "User" if not twin else fresh_ident("Target")
    value = "input" if not twin else fresh_ident("val")
    return with_safety(f"void ({value} as {target});\n")


def snippet_const_only_chain(*, twin: bool = False) -> str:
    field = "id" if not twin else fresh_ident("slot")
    return f"void (({{ {field}: 1 }} as const) as const);\n"


# ---------------------------------------------------------------------------
# B / C. Known-value widening vehicles and silences
# ---------------------------------------------------------------------------


def snippet_known_assignment_to_open_record(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    return (
        header
        + f"let {binding}: Record<string, {command}>;\n"
        + f"{binding} = {known_object(key, starter)};\n"
    )


def snippet_known_return_to_open_record(*, twin: bool = False) -> str:
    header, command, starter, key, _binding = command_parts(twin=twin)
    fn = "create" if not twin else fresh_ident("make")
    return (
        header
        + f"function {fn}(): Record<string, {command}> {{\n"
        + f"  return {known_object(key, starter)};\n"
        + "}\n"
    )


def snippet_known_class_field_to_open_record(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    cls = "Registry" if not twin else fresh_ident("Bag")
    return (
        header
        + f"class {cls} {{\n"
        + f"  {binding}: Record<string, {command}> = {known_object(key, starter)};\n"
        + "}\n"
    )


def snippet_known_return_to_unknown(*, twin: bool = False) -> str:
    """Return the numeric literal used on the unknown variable annotation.

    The return type is the keyword unknown. The value is not passed to a
    type predicate, and the return type is not an alias.
    """
    fn = "create" if not twin else fresh_ident("make")
    return f"function {fn}(): unknown {{\n  return 1;\n}}\n"


def snippet_known_return_to_object(*, twin: bool = False) -> str:
    """Return the array literal used on the object variable annotation.

    The return type is the keyword object. The value is not passed to a
    type predicate, and the return type is not an alias.
    """
    fn = "create" if not twin else fresh_ident("make")
    return f"function {fn}(): object {{\n  return [];\n}}\n"


def snippet_known_return_to_anonymous_object(*, twin: bool = False) -> str:
    """Return the concrete-key object under the same inline object type.

    The return type is the inline object type used as the anonymous-object
    variable annotation, not a named alias. The value is not passed to a
    type predicate.
    """
    header, command, starter, key, _binding = command_parts(twin=twin)
    fn = "create" if not twin else fresh_ident("make")
    return (
        header
        + f"function {fn}(): {{ {key}: {command} }} {{\n"
        + f"  return {known_object(key, starter)};\n"
        + "}\n"
    )


def snippet_known_class_field_to_unknown(*, twin: bool = False) -> str:
    """Initialize a class field typed unknown with the numeric literal.

    The field type is the keyword unknown, not an alias. The value is not
    passed to a type predicate.
    """
    binding = "value" if not twin else fresh_ident("held")
    cls = "Registry" if not twin else fresh_ident("Bag")
    return f"class {cls} {{\n  {binding}: unknown = 1;\n}}\n"


def snippet_known_class_field_to_object(*, twin: bool = False) -> str:
    """Initialize a class field typed object with the array literal.

    The field type is the keyword object, not an alias. The value is not
    passed to a type predicate.
    """
    binding = "value" if not twin else fresh_ident("held")
    cls = "Registry" if not twin else fresh_ident("Bag")
    return f"class {cls} {{\n  {binding}: object = [];\n}}\n"


def snippet_known_class_field_to_anonymous_object(*, twin: bool = False) -> str:
    """Initialize a class field with the inline object type and object literal.

    The field type is the same inline object type used as the anonymous-object
    variable annotation, not a named alias. The value is not passed to a
    type predicate.
    """
    header, command, starter, key, binding = command_parts(twin=twin)
    cls = "Registry" if not twin else fresh_ident("Bag")
    return (
        header
        + f"class {cls} {{\n"
        + f"  {binding}: {{ {key}: {command} }} = {known_object(key, starter)};\n"
        + "}\n"
    )


def _require_shared_concrete_object_literal(literal: str) -> None:
    """The object literal already returned and initialized on the settled arms."""
    if (
        not literal.startswith("{")
        or not literal.endswith("}")
        or ":" not in literal[1:-1]
        or literal == "{}"
    ):
        raise AssertionError(
            "the shared value must be a concrete-key object literal; "
            f"got {literal!r}"
        )
    carriers = (
        ("anonymous return", snippet_known_return_to_anonymous_object()),
        ("open-record return", snippet_known_return_to_open_record()),
        ("anonymous field", snippet_known_class_field_to_anonymous_object()),
        ("open-record field", snippet_known_class_field_to_open_record()),
        ("unknown annotation", snippet_known_object_literal_into_unknown()),
        ("object annotation", snippet_known_object_literal_into_object()),
    )
    for label, source in carriers:
        if source.count(literal) != 1:
            raise AssertionError(
                f"{label} must still use this concrete-key object literal "
                f"once; got {source!r}"
            )
    numeric_return = snippet_known_return_to_unknown()
    array_return = snippet_known_return_to_object()
    numeric_field = snippet_known_class_field_to_unknown()
    array_field = snippet_known_class_field_to_object()
    if "return 1;" not in numeric_return or "(): unknown" not in numeric_return:
        raise AssertionError(
            "the unknown return must still return the numeric literal; "
            f"got {numeric_return!r}"
        )
    if "return [];" not in array_return or "(): object" not in array_return:
        raise AssertionError(
            "the object return must still return the array literal; "
            f"got {array_return!r}"
        )
    if ": unknown = 1;" not in numeric_field or ": object = [];" not in array_field:
        raise AssertionError(
            "class fields must still initialize unknown with the numeric "
            f"literal and object with the array literal; got {numeric_field!r} "
            f"{array_field!r}"
        )
    if literal in numeric_return or literal in array_return:
        raise AssertionError(
            "the keyword return arms must not already return this object literal"
        )
    if literal in numeric_field or literal in array_field:
        raise AssertionError(
            "the keyword field arms must not already initialize this object literal"
        )


def _keyword_object_literal_vehicle(
    kind: str,
    keyword: str,
    *,
    header: str,
    literal: str,
    binding: str,
) -> str:
    """Return or initialize *literal* under the written keyword *keyword*."""
    if keyword not in ("unknown", "object"):
        raise AssertionError(
            f"keyword target must be unknown or object; got {keyword!r}"
        )
    if kind == "return":
        source = (
            header
            + f"function create(): {keyword} {{\n"
            + f"  return {literal};\n"
            + "}\n"
        )
        if source.count(f"(): {keyword} {{") != 1:
            raise AssertionError(
                f"return type must be the keyword {keyword}; got {source!r}"
            )
        between = source.split("(): ", 1)[1].split(" {", 1)[0]
        if between != keyword or source.count(f"  return {literal};") != 1:
            raise AssertionError(
                f"return must yield this object literal as {keyword}; "
                f"got {source!r}"
            )
    elif kind == "field":
        source = (
            header
            + "class Registry {\n"
            + f"  {binding}: {keyword} = {literal};\n"
            + "}\n"
        )
        field_line = next(
            line for line in source.splitlines() if line.strip().startswith(f"{binding}:")
        )
        annotation = field_line.split(" = ", 1)[0].split(":", 1)[1].strip()
        if (
            annotation != keyword
            or source.count(f"{binding}: {keyword} = {literal};") != 1
        ):
            raise AssertionError(
                f"field must initialize this object literal as {keyword}; "
                f"got {source!r}"
            )
    else:
        raise AssertionError(f"unknown vehicle {kind}")
    if source.count(literal) != 1:
        raise AssertionError(
            f"{kind} {keyword} must write this object literal once; got {source!r}"
        )
    body = source[len(header):]
    if (
        "const " in source
        or "\nlet " in source
        or "\nvar " in source
        or " is " in source
        or " as " in body
        or "Record<" in body
        or f"({literal}" in source
    ):
        raise AssertionError(
            f"{kind} {keyword} must not use a const alias, a type predicate, "
            f"an assertion, or a Record; got {source!r}"
        )
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped.startswith("type "):
            continue
        rhs = stripped.split("=", 1)[-1].strip().rstrip(";")
        if rhs in ("unknown", "object") or "unknown" in rhs or "object" in rhs:
            raise AssertionError(
                f"{kind} {keyword} must not alias unknown or object; got {source!r}"
            )
    return source


def object_literal_keyword_return_and_field_sources() -> tuple[tuple[str, str], ...]:
    """That concrete-key object literal under keyword unknown and keyword object.

    A function returns the object literal already used on the inline-object
    and open-record arms, and its return type is the keyword unknown. A
    second function returns that same literal and its return type is the
    keyword object. Those two keywords are repeated as class field
    initializers of that same literal. The numeric return, the array return,
    the inline-object arms, and the open-record arms stay as they are. None
    of these four is a const alias, a type predicate, or an alias of unknown
    or object.
    """
    header, _command, starter, key, binding = command_parts(twin=False)
    literal = known_object(key, starter)
    _require_shared_concrete_object_literal(literal)
    built = (
        (
            "objlit-return-unknown",
            _keyword_object_literal_vehicle(
                "return", "unknown", header=header, literal=literal, binding=binding
            ),
        ),
        (
            "objlit-return-object",
            _keyword_object_literal_vehicle(
                "return", "object", header=header, literal=literal, binding=binding
            ),
        ),
        (
            "objlit-field-unknown",
            _keyword_object_literal_vehicle(
                "field", "unknown", header=header, literal=literal, binding=binding
            ),
        ),
        (
            "objlit-field-object",
            _keyword_object_literal_vehicle(
                "field", "object", header=header, literal=literal, binding=binding
            ),
        ),
    )
    settled = {
        snippet_known_return_to_unknown(),
        snippet_known_return_to_object(),
        snippet_known_return_to_anonymous_object(),
        snippet_known_return_to_open_record(),
        snippet_known_class_field_to_unknown(),
        snippet_known_class_field_to_object(),
        snippet_known_class_field_to_anonymous_object(),
        snippet_known_class_field_to_open_record(),
    }
    labels = [label for label, _source in built]
    if labels != [
        "objlit-return-unknown",
        "objlit-return-object",
        "objlit-field-unknown",
        "objlit-field-object",
    ]:
        raise AssertionError(f"unexpected keyword object-literal vehicles: {labels}")
    for label, source in built:
        if source in settled:
            raise AssertionError(
                f"{label} collapsed into a settled return or class-field arm"
            )
    return built


def _bare_return_keyword_and_literal(source: str) -> tuple[str, str, str]:
    """Function name, keyword return type, and the returned literal."""
    lines = [line.strip() for line in source.splitlines() if line.strip()]
    if len(lines) != 3:
        raise AssertionError(
            "a keyword return must be one signature, one return, and a close; "
            f"got {source!r}"
        )
    signature, returned, close = lines
    prefix = "function "
    if not signature.startswith(prefix) or not signature.endswith(" {"):
        raise AssertionError(
            f"a keyword return must open a function; got {signature!r}"
        )
    head = signature[len(prefix) : -len(" {")]
    marker = "(): "
    if marker not in head:
        raise AssertionError(
            f"a keyword return must annotate the return type; got {signature!r}"
        )
    name, keyword = head.split(marker, 1)
    if not name.isidentifier() or keyword not in ("unknown", "object"):
        raise AssertionError(
            "a keyword return must name a function returning the keyword "
            f"unknown or object; got {signature!r}"
        )
    ret_prefix = "return "
    if not returned.startswith(ret_prefix) or not returned.endswith(";"):
        raise AssertionError(
            f"a keyword return must return one expression; got {returned!r}"
        )
    literal = returned[len(ret_prefix) : -1].strip()
    if close != "}":
        raise AssertionError(
            f"a keyword return must close the function; got {source!r}"
        )
    return name, keyword, literal


def _bare_field_keyword_and_literal(source: str) -> tuple[str, str, str, str]:
    """Class name, field name, keyword type, and initializer literal."""
    lines = [line.strip() for line in source.splitlines() if line.strip()]
    if len(lines) != 3:
        raise AssertionError(
            "a keyword field must be one class, one field, and a close; "
            f"got {source!r}"
        )
    opened, field, close = lines
    prefix = "class "
    if not opened.startswith(prefix) or not opened.endswith(" {"):
        raise AssertionError(f"a keyword field must open a class; got {opened!r}")
    cls = opened[len(prefix) : -len(" {")].strip()
    if not cls.isidentifier():
        raise AssertionError(
            f"a keyword field class must be an identifier; got {cls!r}"
        )
    if " = " not in field or not field.endswith(";"):
        raise AssertionError(
            f"a keyword field must initialize one field; got {field!r}"
        )
    left, literal = field[:-1].split(" = ", 1)
    if ": " not in left:
        raise AssertionError(
            f"a keyword field must annotate the field; got {field!r}"
        )
    binding, keyword = (part.strip() for part in left.split(": ", 1))
    literal = literal.strip()
    if not binding.isidentifier() or keyword not in ("unknown", "object"):
        raise AssertionError(
            "a keyword field must annotate the keyword unknown or object; "
            f"got {field!r}"
        )
    if close != "}":
        raise AssertionError(
            f"a keyword field must close the class; got {source!r}"
        )
    return cls, binding, keyword, literal


def _numeric_literal(literal: str) -> bool:
    return bool(literal) and literal.isdigit()


def _array_literal(literal: str) -> bool:
    return (
        len(literal) >= 2
        and literal.startswith("[")
        and literal.endswith("]")
        and "{" not in literal
        and ":" not in literal
    )


def _reject_alias_predicate_or_const(label: str, source: str) -> None:
    if "const " in source or " is " in source or "type " in source or " as " in source:
        raise AssertionError(
            f"{label} must not use a const alias, a type predicate, an "
            f"assertion, or an alias of unknown or object; got {source!r}"
        )


def _crossed_keyword_return(name: str, keyword: str, literal: str) -> str:
    if keyword not in ("unknown", "object") or not name.isidentifier():
        raise AssertionError(
            "crossed return needs a named function and a keyword target; "
            f"got {name!r} {keyword!r}"
        )
    source = f"function {name}(): {keyword} {{\n  return {literal};\n}}\n"
    parsed_name, parsed_keyword, parsed_literal = _bare_return_keyword_and_literal(
        source
    )
    if (
        parsed_name != name
        or parsed_keyword != keyword
        or parsed_literal != literal
        or source.count(f"return {literal};") != 1
    ):
        raise AssertionError(
            f"crossed return must yield {literal!r} as the keyword {keyword}; "
            f"got {source!r}"
        )
    _reject_alias_predicate_or_const(f"return {keyword}", source)
    return source


def _crossed_keyword_field(cls: str, binding: str, keyword: str, literal: str) -> str:
    if (
        keyword not in ("unknown", "object")
        or not cls.isidentifier()
        or not binding.isidentifier()
    ):
        raise AssertionError(
            "crossed field needs a class, a field, and a keyword target; "
            f"got {cls!r} {binding!r} {keyword!r}"
        )
    source = f"class {cls} {{\n  {binding}: {keyword} = {literal};\n}}\n"
    parsed_cls, parsed_binding, parsed_keyword, parsed_literal = (
        _bare_field_keyword_and_literal(source)
    )
    if (
        parsed_cls != cls
        or parsed_binding != binding
        or parsed_keyword != keyword
        or parsed_literal != literal
        or source.count(f"= {literal};") != 1
    ):
        raise AssertionError(
            f"crossed field must initialize {literal!r} as the keyword "
            f"{keyword}; got {source!r}"
        )
    _reject_alias_predicate_or_const(f"field {keyword}", source)
    return source


def crossed_numeric_array_return_and_field_sources() -> tuple[tuple[str, str], ...]:
    """Cross the numeric and array literals on return and class field.

    The settled unknown return and unknown field still use one numeric
    literal. The settled object return and object field still use one array
    literal. This returns that array literal from a function whose return
    type is the keyword unknown, returns that numeric literal from a
    function whose return type is the keyword object, and repeats those two
    targets as class field initializers. None of the four is a const alias,
    a type predicate, or an alias of unknown or object. The settled pairings
    stay.
    """
    unknown_return = snippet_known_return_to_unknown()
    object_return = snippet_known_return_to_object()
    unknown_field = snippet_known_class_field_to_unknown()
    object_field = snippet_known_class_field_to_object()
    ret_name, ret_keyword, numeric = _bare_return_keyword_and_literal(unknown_return)
    obj_name, obj_keyword, array = _bare_return_keyword_and_literal(object_return)
    field_cls, field_binding, field_keyword, field_numeric = (
        _bare_field_keyword_and_literal(unknown_field)
    )
    obj_cls, obj_binding, obj_field_keyword, field_array = (
        _bare_field_keyword_and_literal(object_field)
    )
    if ret_keyword != "unknown" or not _numeric_literal(numeric):
        raise AssertionError(
            "the unknown return must still return a numeric literal; "
            f"got {unknown_return!r}"
        )
    if obj_keyword != "object" or not _array_literal(array):
        raise AssertionError(
            "the object return must still return an array literal; "
            f"got {object_return!r}"
        )
    if field_keyword != "unknown" or field_numeric != numeric:
        raise AssertionError(
            "the unknown field must still initialize the numeric literal "
            f"the unknown return yields; got {unknown_field!r}"
        )
    if obj_field_keyword != "object" or field_array != array:
        raise AssertionError(
            "the object field must still initialize the array literal "
            f"the object return yields; got {object_field!r}"
        )
    if numeric == array:
        raise AssertionError(
            "the numeric literal and the array literal must differ; "
            f"got {numeric!r}"
        )
    built = (
        (
            "array-return-unknown",
            _crossed_keyword_return(ret_name, "unknown", array),
        ),
        (
            "numeric-return-object",
            _crossed_keyword_return(obj_name, "object", numeric),
        ),
        (
            "array-field-unknown",
            _crossed_keyword_field(field_cls, field_binding, "unknown", array),
        ),
        (
            "numeric-field-object",
            _crossed_keyword_field(obj_cls, obj_binding, "object", numeric),
        ),
    )
    settled = {
        unknown_return,
        object_return,
        unknown_field,
        object_field,
        snippet_known_return_to_anonymous_object(),
        snippet_known_return_to_open_record(),
        snippet_known_class_field_to_anonymous_object(),
        snippet_known_class_field_to_open_record(),
    }
    settled.update(
        source for _label, source in object_literal_keyword_return_and_field_sources()
    )
    labels = [label for label, _source in built]
    if labels != [
        "array-return-unknown",
        "numeric-return-object",
        "array-field-unknown",
        "numeric-field-object",
    ]:
        raise AssertionError(
            f"unexpected crossed return and field vehicles: {labels}"
        )
    seen: set[str] = set()
    for label, source in built:
        if source in settled or source in seen:
            raise AssertionError(
                f"{label} collapsed into a settled return or class-field arm"
            )
        if label.startswith("array-"):
            if f"{array};" not in source or f"{numeric};" in source:
                raise AssertionError(
                    f"{label} must use the array literal already returned as "
                    f"object, not the numeric literal; got {source!r}"
                )
        elif f"{numeric};" not in source or f"{array};" in source:
            raise AssertionError(
                f"{label} must use the numeric literal already returned as "
                f"unknown, not the array literal; got {source!r}"
            )
        seen.add(source)
    return built


def snippet_known_assertion_to_open_record(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    return (
        header
        + with_safety(
            f"const {binding} = {known_object(key, starter)} "
            f"as Record<string, {command}>;\n"
        )
    )


def _require_literal_alias_assertion(
    label: str,
    source: str,
    alias: str,
    literal: str,
    resolved: str,
    *,
    block: bool,
) -> None:
    """The asserted expression is the object literal, and the assertion type is the alias."""
    needle = f"{literal} as {alias}"
    if needle not in source:
        raise AssertionError(
            f"{label} must assert the object literal to the alias; got {source!r}"
        )
    if f"type {alias} = {resolved};" not in source or f"type {alias}<" in source:
        raise AssertionError(
            f"{label} must declare a non-generic alias of {resolved}; got {source!r}"
        )
    if f": {alias}" in source:
        raise AssertionError(
            f"{label} must not store the value under the alias; got {source!r}"
        )
    for forbidden in (" as unknown", " as object", " as any", " as Record<"):
        if forbidden in source:
            raise AssertionError(
                f"{label} assertion type must be the alias, not a written "
                f"keyword or Record; got {source!r}"
            )
    if resolved == "any" or f"type {alias} = any" in source:
        raise AssertionError(f"{label} must not alias any; got {source!r}")
    if "SAFETY:" not in source:
        raise AssertionError(
            f"{label} assertion needs a justification; got {source!r}"
        )
    alias_at = source.index(f"type {alias} =")
    if alias_at > source.index(needle):
        raise AssertionError(
            f"{label} alias must be declared before the assertion; got {source!r}"
        )
    has_function = "function " in source
    if block:
        if not has_function or source.index("function ") > alias_at:
            raise AssertionError(
                f"{label} alias must be block-scoped inside the function "
                f"that contains the assertion; got {source!r}"
            )
    elif has_function:
        raise AssertionError(
            f"{label} alias must sit at file scope; got {source!r}"
        )


def assertion_alias_target_sources() -> tuple[tuple[str, str], ...]:
    """Assert a known object literal to a same-file non-generic alias.

    The asserted expression is the object literal the written-Record arm
    asserts. The assertion type is an alias of unknown, of object, or of
    that same open Record. The unknown alias is repeated inside the function
    that contains the assertion. Each assertion has a justification. The
    literal is not stored under the alias first, and no alias is any.
    """
    written = snippet_known_assertion_to_open_record()
    header, command, starter, key, _binding = command_parts(twin=False)
    literal = known_object(key, starter)
    record = f"Record<string, {command}>"
    if f"{literal} as {record}" not in written:
        raise AssertionError(
            "the written assertion must assert this object literal to this "
            f"open record; got {written!r}"
        )

    def one(label: str, resolved: str, *, block: bool) -> tuple[str, str]:
        alias = fresh_ident("Wide")
        binding = fresh_ident("table")
        statement = with_safety(f"const {binding} = {literal} as {alias};\n")
        if block:
            fn = fresh_ident("wrap")
            inner = f"type {alias} = {resolved};\n" + statement
            source = header + f"function {fn}() {{\n{_indent_lines(inner)}}}\n"
        else:
            source = header + f"type {alias} = {resolved};\n" + statement
        _require_literal_alias_assertion(
            label, source, alias, literal, resolved, block=block
        )
        if resolved == record and f"as {record}" in source:
            raise AssertionError(
                f"{label} must assert to the alias of the written record, "
                f"not to the written record; got {source!r}"
            )
        return label, source

    return (
        one("unknown", "unknown", block=False),
        one("object", "object", block=False),
        one("record", record, block=False),
        one("unknown-block", "unknown", block=True),
    )


def snippet_known_into_unknown(*, twin: bool = False) -> str:
    binding = "value" if not twin else fresh_ident("held")
    return f"const {binding}: unknown = 1;\n"


def snippet_known_into_object(*, twin: bool = False) -> str:
    binding = "value" if not twin else fresh_ident("held")
    return f"const {binding}: object = [];\n"


def snippet_known_numeric_into_object(*, twin: bool = False) -> str:
    """Annotate a numeric literal as the keyword object.

    The target is the keyword object. The value is written on the
    annotation, not stored in a const alias, not passed to a type
    predicate, and not aimed at a Record.
    """
    binding = "value" if not twin else fresh_ident("held")
    return f"const {binding}: object = 1;\n"


def snippet_known_assigned_into_unknown(*, twin: bool = False) -> str:
    binding = "value" if not twin else fresh_ident("held")
    return f"let {binding}: unknown;\n{binding} = 1;\n"


def snippet_known_assigned_into_object(*, twin: bool = False) -> str:
    """Assign the array literal the object annotation already flags.

    The binding is declared with the keyword object and then assigned
    ``[]``. The value is that literal, not a const alias. The target is
    not a Record and the value is not passed to a type predicate.
    """
    binding = "value" if not twin else fresh_ident("held")
    return f"let {binding}: object;\n{binding} = [];\n"


def _keyword_assignment_literal(source: str, keyword: str) -> tuple[str, str]:
    """Binding and assigned literal of a bare keyword assignment."""
    lines = [line.strip() for line in source.splitlines() if line.strip()]
    if len(lines) != 2:
        raise AssertionError(
            f"the {keyword} assignment must be one declaration and one write; "
            f"got {source!r}"
        )
    declared, written = lines
    suffix = f": {keyword};"
    if not declared.startswith("let ") or not declared.endswith(suffix):
        raise AssertionError(
            f"the {keyword} assignment must declare a let annotated {keyword} "
            f"and no initializer; got {declared!r}"
        )
    binding = declared[len("let ") : -len(suffix)].strip()
    write_prefix = f"{binding} = "
    if not written.startswith(write_prefix) or not written.endswith(";"):
        raise AssertionError(
            f"the {keyword} assignment must write that binding; got {written!r}"
        )
    literal = written[len(write_prefix) : -1].strip()
    if not binding.isidentifier():
        raise AssertionError(
            f"the {keyword} assignment binding must be an identifier; "
            f"got {binding!r}"
        )
    return binding, literal


def _settled_numeric_and_array_assignments() -> tuple[str, str, str, str]:
    """Bindings and literals of the settled unknown and object assignments.

    The unknown assignment still writes one numeric literal. The object
    assignment still writes one array literal. Those two literals differ.
    """
    unknown_binding, numeric = _keyword_assignment_literal(
        snippet_known_assigned_into_unknown(), "unknown"
    )
    object_binding, array = _keyword_assignment_literal(
        snippet_known_assigned_into_object(), "object"
    )
    if not numeric.isdigit():
        raise AssertionError(
            "the unknown assignment must still write a numeric literal; "
            f"got {numeric!r}"
        )
    if (
        len(array) < 2
        or not array.startswith("[")
        or not array.endswith("]")
        or "{" in array
    ):
        raise AssertionError(
            "the object assignment must still write an array literal; "
            f"got {array!r}"
        )
    if array == numeric:
        raise AssertionError(
            "the array literal assigned into object must differ from the "
            f"numeric literal assigned into unknown; got {array!r}"
        )
    return unknown_binding, numeric, object_binding, array


def _crossed_keyword_assignment(*, target: str, literal: str, binding: str) -> str:
    """Assign *literal* into a binding already annotated *target*.

    The value is that literal. Not a const alias, not a Record, not an
    inline object type, and not a type-predicate argument.
    """
    if target not in ("unknown", "object"):
        raise AssertionError(
            f"crossed assignment target must be unknown or object; got {target!r}"
        )
    if not binding.isidentifier():
        raise AssertionError(
            f"crossed assignment binding must be an identifier; got {binding!r}"
        )
    declaration = f"let {binding}: {target};"
    write = f"{binding} = {literal};"
    source = f"{declaration}\n{write}\n"
    if (
        "const " in source
        or "var " in source
        or " as " in source
        or " is " in source
        or "Record<" in source
        or "(" in source
        or "{" in declaration
    ):
        raise AssertionError(
            "crossed assignment must not use a const alias, a var alias, a "
            "Record, an inline object type, or a type predicate; "
            f"got {source!r}"
        )
    if source.count(write) != 1 or source.count(literal) != 1:
        raise AssertionError(
            "crossed assignment must write that literal once; "
            f"got {source!r}"
        )
    return source


def snippet_known_array_assigned_into_unknown() -> str:
    """Assign the array literal already assigned into object, into unknown.

    The binding is declared with the keyword unknown and then assigned the
    array literal already written into a binding annotated object. The value
    is that literal, not a const alias. The target is not a Record and not
    an inline object type, and the value is not passed to a type predicate.
    """
    unknown_binding, numeric, _object_binding, array = (
        _settled_numeric_and_array_assignments()
    )
    source = _crossed_keyword_assignment(
        target="unknown", literal=array, binding=unknown_binding
    )
    if source == snippet_known_assigned_into_unknown():
        raise AssertionError(
            "the unknown arm must assign the array literal, not the numeric "
            f"literal; got {source!r}"
        )
    if f"= {array};" not in source or f"= {numeric};" in source:
        raise AssertionError(
            "the unknown arm must assign the array literal already assigned "
            f"into object; got {source!r}"
        )
    return source


def snippet_known_numeric_assigned_into_object() -> str:
    """Assign the numeric literal already assigned into unknown, into object.

    The binding is declared with the keyword object and then assigned the
    numeric literal already written into a binding annotated unknown. The
    value is that literal, not a const alias. The target is not a Record and
    not an inline object type, and the value is not passed to a type predicate.
    """
    _unknown_binding, numeric, object_binding, array = (
        _settled_numeric_and_array_assignments()
    )
    source = _crossed_keyword_assignment(
        target="object", literal=numeric, binding=object_binding
    )
    if source == snippet_known_assigned_into_object():
        raise AssertionError(
            "the object arm must assign the numeric literal, not the array "
            f"literal; got {source!r}"
        )
    if f"= {numeric};" not in source or f"= {array};" in source:
        raise AssertionError(
            "the object arm must assign the numeric literal already assigned "
            f"into unknown; got {source!r}"
        )
    return source


def const_alias_numeric_array_vehicle_sources() -> tuple[tuple[str, str], ...]:
    """Const aliases of the numeric and array literals on three vehicles.

    The assignment writes a const alias of the numeric literal already
    assigned as 1 into a binding already annotated unknown. The return
    yields a const alias of the array literal already returned as [] from
    a function whose return type is object. The class field typed unknown
    is initialized with a const alias of that same numeric literal. The
    alias is not the initializer of an annotated variable, is not passed
    to a type predicate, and is not asserted afterward.
    """

    def nonempty(source: str) -> list[str]:
        return [line.strip() for line in source.splitlines() if line.strip()]

    assigned = snippet_known_assigned_into_unknown()
    assigned_lines = nonempty(assigned)
    if len(assigned_lines) != 2:
        raise AssertionError(
            "the unknown assignment must be one declaration and one write; "
            f"got {assigned!r}"
        )
    declared, written = assigned_lines
    if not declared.startswith("let ") or not declared.endswith(": unknown;"):
        raise AssertionError(
            "the unknown assignment must declare a let annotated unknown "
            f"and no initializer; got {declared!r}"
        )
    binding = declared[len("let ") : -len(": unknown;")].strip()
    write_prefix = f"{binding} = "
    if not written.startswith(write_prefix) or not written.endswith(";"):
        raise AssertionError(
            f"the unknown assignment must write that binding; got {written!r}"
        )
    numeric = written[len(write_prefix) : -1].strip()
    if not binding.isidentifier() or not numeric.isdigit():
        raise AssertionError(
            "the unknown assignment must write one numeric literal; "
            f"binding={binding!r} literal={numeric!r}"
        )

    returned = snippet_known_return_to_object()
    return_lines = nonempty(returned)
    if (
        len(return_lines) != 3
        or not return_lines[0].startswith("function ")
        or not return_lines[0].endswith("(): object {")
        or not return_lines[1].startswith("return ")
        or not return_lines[1].endswith(";")
        or return_lines[2] != "}"
    ):
        raise AssertionError(
            "the object return must yield one expression from a function "
            f"whose return type is object; got {returned!r}"
        )
    fn = return_lines[0][len("function ") : -len("(): object {")].strip()
    array = return_lines[1][len("return ") : -1].strip()
    if (
        not fn.isidentifier()
        or len(array) < 2
        or not array.startswith("[")
        or not array.endswith("]")
        or "{" in array
    ):
        raise AssertionError(
            "the object return must yield an array literal; "
            f"fn={fn!r} literal={array!r}"
        )

    fielded = snippet_known_class_field_to_unknown()
    field_lines = nonempty(fielded)
    if (
        len(field_lines) != 3
        or not field_lines[0].startswith("class ")
        or not field_lines[0].endswith(" {")
        or not field_lines[1].endswith(";")
        or field_lines[2] != "}"
    ):
        raise AssertionError(
            "the unknown class field must be one initializer; "
            f"got {fielded!r}"
        )
    cls = field_lines[0][len("class ") : -len(" {")].strip()
    field_stmt = field_lines[1][:-1].strip()
    field_marker = ": unknown = "
    if field_marker not in field_stmt or not cls.isidentifier():
        raise AssertionError(
            f"the class field must be typed unknown; got {fielded!r}"
        )
    field_name, field_numeric = field_stmt.split(field_marker, 1)
    field_name = field_name.strip()
    field_numeric = field_numeric.strip()
    if not field_name.isidentifier() or field_numeric != numeric:
        raise AssertionError(
            "the class field must initialize with the same numeric literal "
            f"the unknown assignment writes; field={field_numeric!r} "
            f"assignment={numeric!r}"
        )

    def one(label: str, literal: str, vehicle_for) -> tuple[str, str]:
        alias = fresh_ident("src")
        if not alias.isidentifier() or alias in {binding, fn, cls, field_name}:
            raise AssertionError(
                f"{label} needs an alias distinct from the vehicle names; "
                f"got {alias!r}"
            )
        vehicle = vehicle_for(alias)
        source = f"const {alias} = {literal};\n{vehicle}"
        declaration, rest = source.split("\n", 1)
        if declaration != f"const {alias} = {literal};" or rest != vehicle:
            raise AssertionError(
                f"{label} must alias the literal with const and no annotation; "
                f"got {source!r}"
            )
        if f"{alias}:" in source or f"= {literal}" in vehicle or f"return {literal}" in vehicle:
            raise AssertionError(
                f"{label} must use the alias as the value, not the literal, "
                f"and must not annotate the alias; got {source!r}"
            )
        if " as " in source or " is " in source or f"{alias}(" in source:
            raise AssertionError(
                f"{label} must not assert the alias or pass it to a call; "
                f"got {source!r}"
            )
        if source.count(alias) != 2:
            raise AssertionError(
                f"{label} must declare the alias once and use it once; "
                f"got {source!r}"
            )
        return label, source

    assign_source_label = "assign-unknown"
    return_source_label = "return-object"
    field_source_label = "field-unknown"
    built = (
        one(
            assign_source_label,
            numeric,
            lambda alias: f"let {binding}: unknown;\n{binding} = {alias};\n",
        ),
        one(
            return_source_label,
            array,
            lambda alias: f"function {fn}(): object {{\n  return {alias};\n}}\n",
        ),
        one(
            field_source_label,
            numeric,
            lambda alias: (
                f"class {cls} {{\n  {field_name}: unknown = {alias};\n}}\n"
            ),
        ),
    )
    seen: set[str] = set()
    for label, source in built:
        declaration = source.split("\n", 1)[0]
        alias = declaration.split(" ", 2)[1]
        if alias in seen:
            raise AssertionError(f"alias {alias!r} was reused")
        seen.add(alias)
        if label == assign_source_label:
            expect = (
                f"const {alias} = {numeric};\n"
                f"let {binding}: unknown;\n"
                f"{binding} = {alias};\n"
            )
            if "(" in source:
                raise AssertionError(
                    f"{label} must not call the alias; got {source!r}"
                )
        elif label == return_source_label:
            expect = (
                f"const {alias} = {array};\n"
                f"function {fn}(): object {{\n"
                f"  return {alias};\n"
                f"}}\n"
            )
            if source.count("(") != 1:
                raise AssertionError(
                    f"{label} must not call the alias; got {source!r}"
                )
        elif label == field_source_label:
            expect = (
                f"const {alias} = {numeric};\n"
                f"class {cls} {{\n"
                f"  {field_name}: unknown = {alias};\n"
                f"}}\n"
            )
            if "(" in source:
                raise AssertionError(
                    f"{label} must not call the alias; got {source!r}"
                )
        else:
            raise AssertionError(f"unexpected alias vehicle {label}")
        if source != expect:
            raise AssertionError(
                f"{label} drifted from the literal arm; got {source!r}"
            )
    if [label for label, _source in built] != [
        assign_source_label,
        return_source_label,
        field_source_label,
    ]:
        raise AssertionError(f"unexpected alias vehicles: {built!r}")
    return built


def snippet_known_object_literal_into_unknown(*, twin: bool = False) -> str:
    header, _command, starter, key, binding = command_parts(twin=twin)
    return (
        header
        + f"const {binding}: unknown = {known_object(key, starter)};\n"
    )


def _unknown_object_literal_parts() -> tuple[str, str, str]:
    """Prefix, binding, and concrete-key literal of the unknown annotation."""
    annotated = snippet_known_object_literal_into_unknown()
    statement = _lone_const_statement(annotated)
    name, target, literal = _split_const_annotation(statement)
    if target != "unknown":
        raise AssertionError(
            "the object-literal unknown annotation must still target unknown; "
            f"got {annotated!r}"
        )
    if (
        not literal.startswith("{")
        or not literal.endswith("}")
        or ":" not in literal[1:-1]
        or literal == "{}"
    ):
        raise AssertionError(
            "the unknown annotation must still initialize a concrete-key "
            f"object literal; got {annotated!r}"
        )
    prefix = annotated.split("const ", 1)[0]
    if prefix + statement + "\n" != annotated:
        raise AssertionError(
            "the unknown annotation must be one header plus one const; "
            f"got {annotated!r}"
        )
    if " as " in annotated or " is " in annotated or "Record<" in annotated:
        raise AssertionError(
            "the unknown annotation must not assert, call a predicate, or "
            f"use a Record; got {annotated!r}"
        )
    return prefix, name, literal


def snippet_known_object_literal_into_object() -> str:
    """Annotate that same concrete-key object literal as the keyword object.

    The initializer is the object literal already written on the unknown
    variable annotation. The annotation is the keyword object. The literal
    is that initializer: not a const alias, not a Record, not an inline
    object type, and not a type-predicate argument.
    """
    prefix, name, literal = _unknown_object_literal_parts()
    source = f"{prefix}const {name}: object = {literal};\n"
    if f": object = {literal};" not in source or source.count(literal) != 1:
        raise AssertionError(
            "object arm must annotate this object literal as the keyword "
            f"object; got {source!r}"
        )
    annotation = source.split("=", 1)[0]
    if "{" in annotation or "Record<" in source:
        raise AssertionError(
            "object arm must not use an inline object type or a Record; "
            f"got {source!r}"
        )
    if (
        "unknown" in source
        or " as " in source
        or " is " in source
        or source.count("const ") != 1
    ):
        raise AssertionError(
            "object arm must not keep the unknown annotation, assert the "
            f"literal, alias it, or pass it to a type predicate; got {source!r}"
        )
    return source


def _object_literal_assignment(keyword: str) -> str:
    """Assign the unknown-annotation object literal into a keyword binding.

    The binding is declared with *keyword* and no initializer, then assigned
    the concrete-key object literal already written on the unknown variable
    annotation. The value is that literal: not a const alias, not a Record,
    not an inline object type, and not a type-predicate argument.
    """
    if keyword not in ("unknown", "object"):
        raise AssertionError(
            f"assignment keyword must be unknown or object; got {keyword!r}"
        )
    prefix, name, literal = _unknown_object_literal_parts()
    source = f"{prefix}let {name}: {keyword};\n{name} = {literal};\n"
    body = source[len(prefix) :]
    declaration = f"let {name}: {keyword};"
    write = f"{name} = {literal};"
    if (
        not body.startswith(declaration + "\n")
        or body.count(declaration) != 1
        or body.count(write) != 1
        or body.count(literal) != 1
        or source.count(literal) != 1
    ):
        raise AssertionError(
            f"{keyword} assignment must declare that binding and then assign "
            f"this object literal once; got {source!r}"
        )
    other = "object" if keyword == "unknown" else "unknown"
    if other in source or "const " in source or "var " in source:
        raise AssertionError(
            f"{keyword} assignment must not use the other keyword, a const "
            f"alias, or a var alias; got {source!r}"
        )
    if (
        " as " in source
        or " is " in source
        or "Record<" in source
        or "function " in body
        or "(" in body
    ):
        raise AssertionError(
            f"{keyword} assignment must not assert the literal, pass it to a "
            f"type predicate, or aim it at a Record; got {source!r}"
        )
    declared = declaration.split(":", 1)[1].strip().rstrip(";")
    if declared != keyword or "{" in declaration:
        raise AssertionError(
            f"{keyword} assignment target must be that keyword, not an inline "
            f"object type; got {source!r}"
        )
    return source


def snippet_known_object_literal_assigned_into_unknown() -> str:
    """Assign that same concrete-key object literal into explicit unknown.

    The binding is declared with the keyword unknown and then assigned the
    object literal already written on the unknown variable annotation. The
    value is that literal, not a const alias. The target is not a Record and
    not an inline object type, and the value is not passed to a type predicate.
    """
    return _object_literal_assignment("unknown")


def snippet_known_object_literal_assigned_into_object() -> str:
    """Assign that same concrete-key object literal into the keyword object.

    The binding is declared with the keyword object and then assigned the
    object literal already written on the unknown variable annotation. The
    value is that literal, not a const alias. The target is not a Record and
    not an inline object type, and the value is not passed to a type predicate.
    """
    return _object_literal_assignment("object")


def snippet_known_object_literal_asserted_to_object() -> str:
    """Assert that same object literal directly to the keyword object.

    The asserted expression is the literal, not a const alias. The target
    is the keyword object, not a Record and not an inline object type. A
    justification sits on the assertion so the safety rule is not the failure.
    """
    prefix, name, literal = _unknown_object_literal_parts()
    source = prefix + with_safety(f"const {name} = {literal} as object;\n")
    needle = f"{literal} as object"
    if source.count(needle) != 1 or source.count(literal) != 1:
        raise AssertionError(
            "assertion must assert this object literal directly to the "
            f"keyword object, and nowhere else; got {source!r}"
        )
    if f"{name}:" in source or source.count("const ") != 1:
        raise AssertionError(
            "assertion must not annotate the binding or alias the literal; "
            f"got {source!r}"
        )
    if (
        "as {" in source
        or "as unknown" in source
        or "Record<" in source
        or " is " in source
        or "\nlet " in source
        or "\nvar " in source
    ):
        raise AssertionError(
            "assertion target must be the keyword object, not an inline "
            f"object type, unknown, Record, or a type predicate; got {source!r}"
        )
    comment, _statement = source.split("const ", 1)
    if "SAFETY:" not in comment or comment.split("SAFETY:", 1)[1].strip() == "":
        raise AssertionError(
            f"assertion needs a non-empty justification; got {source!r}"
        )
    return source


def snippet_known_into_anonymous_object(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    return (
        header
        + f"const {binding}: {{ {key}: {command} }} = {known_object(key, starter)};\n"
    )


def _split_const_annotation(statement: str) -> tuple[str, str, str]:
    """Name, annotation, and initializer of one ``const`` annotation."""
    stripped = statement.strip()
    if not stripped.startswith("const ") or not stripped.endswith(";"):
        raise AssertionError(
            f"expected one const annotation statement; got {statement!r}"
        )
    body = stripped[len("const ") : -1]
    if body.count("=") != 1 or ":" not in body.split("=", 1)[0]:
        raise AssertionError(
            f"const annotation must have one annotation and one initializer; "
            f"got {statement!r}"
        )
    name, rest = body.split(":", 1)
    annotation, initializer = rest.split("=", 1)
    name = name.strip()
    annotation = annotation.strip()
    initializer = initializer.strip()
    if not name.isidentifier() or annotation == "" or initializer == "":
        raise AssertionError(
            f"const annotation is incomplete; got {statement!r}"
        )
    return name, annotation, initializer


def _lone_const_statement(source: str) -> str:
    lines = [line for line in source.splitlines() if line.startswith("const ")]
    if len(lines) != 1:
        raise AssertionError(
            f"expected exactly one const annotation; got {source!r}"
        )
    return lines[0]


def snippet_known_numeric_into_anonymous_object() -> str:
    """Annotate the unknown-arm numeric literal as the inline object type.

    The initializer is the numeric literal already written on the unknown
    variable annotation. The annotation is the same inline object type the
    anonymous-object variable annotation already uses. The literal is that
    initializer: it is not passed to a type predicate and it is not stored
    under unknown.
    """
    annotated = snippet_known_into_anonymous_object()
    name, inline, object_literal = _split_const_annotation(
        _lone_const_statement(annotated)
    )
    _unknown_name, unknown_target, numeric = _split_const_annotation(
        _lone_const_statement(snippet_known_into_unknown())
    )
    if unknown_target != "unknown" or not numeric.isdigit():
        raise AssertionError(
            "the unknown annotation must still initialize a numeric literal; "
            f"got {snippet_known_into_unknown()!r}"
        )
    if not inline.startswith("{") or not inline.endswith("}"):
        raise AssertionError(
            "the anonymous-object annotation must still be an inline object "
            f"type; got {annotated!r}"
        )
    if not object_literal.startswith("{") or not object_literal.endswith("}"):
        raise AssertionError(
            "the anonymous-object annotation must still initialize an object "
            f"literal; got {annotated!r}"
        )
    prefix = annotated.split("const ", 1)[0]
    source = f"{prefix}const {name}: {inline} = {numeric};\n"
    if f": {inline} = {numeric};" not in source or object_literal in source:
        raise AssertionError(
            "numeric arm must keep the inline object type and replace only "
            f"the object-literal initializer; got {source!r}"
        )
    if "unknown" in source or " as " in source or " is " in source:
        raise AssertionError(
            "numeric arm must not store the literal under unknown, assert "
            f"it, or pass it to a type predicate; got {source!r}"
        )
    if source.count(numeric) != 1:
        raise AssertionError(
            f"the numeric literal must appear once, as the initializer; got {source!r}"
        )
    return source


def snippet_known_array_into_open_record() -> str:
    """Annotate the object-arm array literal as an open record.

    The initializer is the array literal already written on the object
    variable annotation. The annotation is ``Record<string, Command>``, the
    open record the object-literal arms already use. The literal is that
    initializer: it is not passed to a type predicate and it is not stored
    under unknown.
    """
    name, object_target, array = _split_const_annotation(
        _lone_const_statement(snippet_known_into_object())
    )
    if object_target != "object" or not (
        array.startswith("[") and array.endswith("]")
    ):
        raise AssertionError(
            "the object annotation must still initialize an array literal; "
            f"got {snippet_known_into_object()!r}"
        )
    header, command, _starter, _key, _binding = command_parts()
    record = f"Record<string, {command}>"
    open_record = snippet_known_assignment_to_open_record()
    if f": {record}" not in open_record:
        raise AssertionError(
            "open-record spelling must match the scored Record annotation; "
            f"got {open_record!r}"
        )
    source = f"{header}const {name}: {record} = {array};\n"
    if f": {record} = {array};" not in source:
        raise AssertionError(
            f"array arm must annotate this array literal as this open record; "
            f"got {source!r}"
        )
    if "unknown" in source or " as " in source or " is " in source or "{" in source:
        raise AssertionError(
            "array arm must not store the literal under unknown, assert it, "
            f"pass it to a type predicate, or use an object literal; got {source!r}"
        )
    if source.count(array) != 1:
        raise AssertionError(
            f"the array literal must appear once, as the initializer; got {source!r}"
        )
    return source


def _direct_keyword_assertion_literal(source: str, keyword: str) -> str:
    """Literal in one justified ``const name = literal as keyword``."""
    if keyword not in ("unknown", "object"):
        raise AssertionError(
            f"assertion keyword must be unknown or object; got {keyword!r}"
        )
    if source.count("const ") != 1:
        raise AssertionError(
            "the assertion must be one const statement, not a const alias; "
            f"got {source!r}"
        )
    comment, statement = source.split("const ", 1)
    if "SAFETY:" not in comment or comment.split("SAFETY:", 1)[1].strip() == "":
        raise AssertionError(
            f"the assertion needs a non-empty justification; got {source!r}"
        )
    statement = statement.strip()
    suffix = f" as {keyword};"
    if statement.count("=") != 1 or not statement.endswith(suffix):
        raise AssertionError(
            f"the assertion must assert one expression to the keyword {keyword}; "
            f"got {statement!r}"
        )
    binding, expr = statement.split("=", 1)
    binding = binding.strip()
    literal = expr[: -len(suffix)].strip()
    if not binding.isidentifier() or literal == "" or literal.isidentifier():
        raise AssertionError(
            "the asserted expression must be the literal, not an identifier; "
            f"got {source!r}"
        )
    other = "object" if keyword == "unknown" else "unknown"
    target = statement.split(" as ", 1)[-1]
    if (
        f"{binding}:" in source
        or "Record<" in source
        or " is " in source
        or "(" in statement
        or " as {" in source
        or "{" in target
        or f" as {other}" in source
    ):
        raise AssertionError(
            "the assertion must not annotate the binding, use a const alias, "
            "a Record, an inline object type, or a type predicate; "
            f"got {source!r}"
        )
    return literal


def non_predicate_widening_gap_sources() -> tuple[tuple[str, str], ...]:
    """Line 146 vehicles that are not a type-predicate call.

    Each file is one observation: an array literal annotated unknown; a const
    alias of a numeric literal annotated unknown; a const alias of an array
    literal annotated unknown; or one const alias of a concrete-key object
    literal flowing into unknown, object, or an inline anonymous object type.
    Six further files assert the literal itself: a numeric literal to
    unknown, the array literal already annotated as object to object, the
    same concrete-key object literal to unknown, that same literal to the
    keyword object, that same array literal to unknown, and that same
    numeric literal to object. Those six are not a const alias, not a
    Record target, not an inline object type, and not a type-predicate
    argument. Assertion files carry a justification so the safety rule is
    not the failure.
    """
    held = fresh_ident("held")
    array_unknown = f"const {held}: unknown = [1, 2];\n"
    number = fresh_ident("n")
    number_held = fresh_ident("held")
    numeric_alias = (
        f"const {number} = 1;\n"
        f"const {number_held}: unknown = {number};\n"
    )
    items = fresh_ident("xs")
    array_held = fresh_ident("held")
    array_alias = (
        f"const {items} = [1, 2];\n"
        f"const {array_held}: unknown = {items};\n"
    )
    rows: list[tuple[str, str]] = [
        ("array-unknown", array_unknown),
        ("num-alias-unknown", numeric_alias),
        ("arr-alias-unknown", array_alias),
    ]
    for label, target, asserted in (
        ("as-unknown", "unknown", True),
        ("as-object", "object", True),
        ("ann-anon", None, False),
        ("as-anon", None, True),
    ):
        header, command, starter, key, binding = command_parts(twin=True)
        source = fresh_ident("src")
        alias = f"const {source} = {known_object(key, starter)};\n"
        anonymous = f"{{ {key}: {command} }}"
        destination = target if target is not None else anonymous
        if asserted:
            comment = safety_comment(text=generated_justification())
            vehicle = (
                f"{comment}\nconst {binding} = {source} as {destination};\n"
            )
        else:
            vehicle = f"const {binding}: {destination} = {source};\n"
        rows.append((label, header + alias + vehicle))
    # The asserted expression is the literal, not an identifier. The binding
    # has no type annotation, so this is not the annotation vehicle.
    numeric_held = fresh_ident("held")
    rows.append(
        (
            "as-num-unknown",
            with_safety(f"const {numeric_held} = 1 as unknown;\n"),
        )
    )
    array_asserted = fresh_ident("held")
    rows.append(
        (
            "as-arr-object",
            with_safety(f"const {array_asserted} = [] as object;\n"),
        )
    )
    header, _command, starter, key, binding = command_parts(twin=True)
    rows.append(
        (
            "as-objlit-unknown",
            header
            + with_safety(
                f"const {binding} = {known_object(key, starter)} as unknown;\n"
            ),
        )
    )
    rows.append(
        (
            "as-objlit-object",
            snippet_known_object_literal_asserted_to_object(),
        )
    )
    # Cross the keyword pairings on the same literals. The asserted
    # expression is the array literal already asserted to object, now
    # asserted to unknown, and the numeric literal already asserted to
    # unknown, now asserted to object. A justification sits on each
    # assertion. Not a const alias, a Record, an inline object type, or
    # a type predicate.
    numeric_literal = _direct_keyword_assertion_literal(
        next(source for label, source in rows if label == "as-num-unknown"),
        "unknown",
    )
    array_literal = _direct_keyword_assertion_literal(
        next(source for label, source in rows if label == "as-arr-object"),
        "object",
    )
    if not numeric_literal.isdigit():
        raise AssertionError(
            "the unknown assertion must still assert a numeric literal; "
            f"got {numeric_literal!r}"
        )
    if (
        len(array_literal) < 2
        or not array_literal.startswith("[")
        or not array_literal.endswith("]")
        or "{" in array_literal
    ):
        raise AssertionError(
            "the object assertion must still assert an array literal; "
            f"got {array_literal!r}"
        )
    if array_literal == numeric_literal:
        raise AssertionError(
            "the array literal asserted to object must differ from the "
            f"numeric literal asserted to unknown; got {array_literal!r}"
        )
    # Written as the literals themselves. The array text is the same `[]`
    # already asserted to object, and the numeric text is the same `1`
    # already asserted to unknown. Not assembled from a const alias.
    if array_literal != "[]" or numeric_literal != "1":
        raise AssertionError(
            "crossed keyword assertions must use the array literal already "
            f"asserted to object ({array_literal!r}) and the numeric literal "
            f"already asserted to unknown ({numeric_literal!r})"
        )
    array_unknown_source = with_safety(
        f"const {fresh_ident('held')} = [] as unknown;\n"
    )
    numeric_object_source = with_safety(
        f"const {fresh_ident('held')} = 1 as object;\n"
    )
    if _direct_keyword_assertion_literal(array_unknown_source, "unknown") != array_literal:
        raise AssertionError(
            "array assertion to unknown must assert the same array literal "
            f"already asserted to object; got {array_unknown_source!r}"
        )
    if _direct_keyword_assertion_literal(numeric_object_source, "object") != numeric_literal:
        raise AssertionError(
            "numeric assertion to object must assert the same numeric literal "
            f"already asserted to unknown; got {numeric_object_source!r}"
        )
    rows.append(("as-arr-unknown", array_unknown_source))
    rows.append(("as-num-object", numeric_object_source))
    labels = [label for label, _source in rows]
    for required in (
        "as-object",
        "as-num-unknown",
        "as-arr-object",
        "as-arr-unknown",
        "as-num-object",
        "as-objlit-unknown",
        "as-objlit-object",
    ):
        if required not in labels:
            raise AssertionError(f"missing non-predicate widening arm {required}")
    return tuple(rows)


_PRODUCT_KINDS: tuple[str, ...] = (
    "object",
    "numeric",
    "array",
    "const-object",
    "const-numeric",
    "const-array",
)
_PRODUCT_CARRIERS: tuple[str, ...] = (
    "annotation",
    "assignment",
    "return",
    "field",
    "assertion",
)
_PRODUCT_TARGETS: tuple[str, ...] = (
    "unknown",
    "object",
    "anonymous",
    "record",
)


def _product_spellings() -> tuple[str, str, str, str, str, str]:
    """Header, object literal, numeric, array, inline object type, open record.

    The inline object type and the open record are the spellings the
    object-literal arms already use. The numeric and array literals are the
    ones already written on the keyword annotations.
    """
    header, command, _starter, _key, _binding = command_parts(twin=False)
    _prefix, _name, object_literal = _unknown_object_literal_parts()
    _unknown_name, unknown_target, numeric = _split_const_annotation(
        _lone_const_statement(snippet_known_into_unknown())
    )
    _object_name, object_target, array = _split_const_annotation(
        _lone_const_statement(snippet_known_into_object())
    )
    _anon_name, anonymous, _anon_literal = _split_const_annotation(
        _lone_const_statement(snippet_known_into_anonymous_object())
    )
    record = f"Record<string, {command}>"
    if unknown_target != "unknown" or not _numeric_literal(numeric):
        raise AssertionError(
            "the unknown annotation must still initialize a numeric literal"
        )
    if object_target != "object" or not _array_literal(array):
        raise AssertionError(
            "the object annotation must still initialize an array literal"
        )
    if not anonymous.startswith("{") or not anonymous.endswith("}") or ":" not in anonymous:
        raise AssertionError(
            "the anonymous-object arm must still use an inline object type "
            f"with a member; got {anonymous!r}"
        )
    if f": {record}" not in snippet_known_assignment_to_open_record():
        raise AssertionError(
            "the open-dictionary spelling must still be the scored open record"
        )
    if object_literal == "{}" or numeric == array:
        raise AssertionError(
            "the product must not use an empty dictionary, and the numeric "
            "and array literals must differ"
        )
    return header, object_literal, numeric, array, anonymous, record


def _product_value(kind: str, object_literal: str, numeric: str, array: str) -> tuple[str, str]:
    """Alias preamble (or empty) and the expression that flows into the target."""
    literals = {
        "object": object_literal,
        "numeric": numeric,
        "array": array,
        "const-object": object_literal,
        "const-numeric": numeric,
        "const-array": array,
    }
    if kind not in literals:
        raise AssertionError(f"unknown value kind {kind!r}")
    literal = literals[kind]
    if kind.startswith("const-"):
        return f"const known = {literal};\n", "known"
    return "", literal


def _product_vehicle(carrier: str, target_text: str, expr: str) -> str:
    """One of the five non-predicate carriers, aimed at *target_text*."""
    if carrier == "annotation":
        return f"const held: {target_text} = {expr};\n"
    if carrier == "assignment":
        return f"let held: {target_text};\nheld = {expr};\n"
    if carrier == "return":
        return f"function create(): {target_text} {{\n  return {expr};\n}}\n"
    if carrier == "field":
        return f"class Registry {{\n  value: {target_text} = {expr};\n}}\n"
    if carrier == "assertion":
        return with_safety(f"const held = {expr} as {target_text};\n")
    raise AssertionError(f"unknown carrier {carrier!r}")


def _reject_product_silence(label: str, source: str, expr: str) -> None:
    """Line 147 silences and type predicates stay out of the product."""
    if " is " in source or "satisfies " in source:
        raise AssertionError(
            f"{label} must not use a type predicate or satisfies; got {source!r}"
        )
    if "{}" in source or expr == "{}":
        raise AssertionError(
            f"{label} must not flow an empty dictionary; got {source!r}"
        )
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("let ") and ":" not in stripped.split("=", 1)[0]:
            raise AssertionError(
                f"{label} must not use a let alias of a literal; got {source!r}"
            )
        if stripped.startswith("var "):
            raise AssertionError(
                f"{label} must not use a var alias; got {source!r}"
            )
    # A local whose only evidence is a precise annotation has no literal
    # initializer. Every product value is a literal or a const of one.
    if expr.isidentifier():
        declaration = f"const {expr} ="
        if source.count(declaration) != 1 or f"const {expr}:" in source:
            raise AssertionError(
                f"{label} const alias must be one unannotated initializer; "
                f"got {source!r}"
            )
    elif source.count(expr) < 1:
        raise AssertionError(f"{label} must write its literal; got {source!r}")


def known_widening_product_sources() -> tuple[tuple[str, str], ...]:
    """Every line-146 value kind, non-predicate carrier, and target.

    Value kind is an object literal with concrete keys, a numeric literal,
    an array literal, or a const local alias of one of those three. Carrier
    is a variable annotation, an assignment, a return annotation, a class
    field initializer, or an assertion. Target is explicit unknown, object,
    the inline anonymous object the object-literal arms already use, or the
    open record those arms already use. Each cell is its own file. None of
    them is a type predicate, an empty dictionary into an open record, a
    let or var alias, or an annotation-only local.
    """
    header, object_literal, numeric, array, anonymous, record = _product_spellings()
    targets = {
        "unknown": "unknown",
        "object": "object",
        "anonymous": anonymous,
        "record": record,
    }
    rows: list[tuple[str, str]] = []
    for kind in _PRODUCT_KINDS:
        preamble, expr = _product_value(kind, object_literal, numeric, array)
        needs_header = (
            kind in ("object", "const-object")
            or "{" in expr
            or "startCommand" in preamble
        )
        for carrier in _PRODUCT_CARRIERS:
            for target_name in _PRODUCT_TARGETS:
                target_text = targets[target_name]
                label = f"{kind}__{carrier}__{target_name}"
                use_header = needs_header or target_name in ("anonymous", "record")
                source = (header if use_header else "") + preamble + _product_vehicle(
                    carrier, target_text, expr
                )
                _reject_product_silence(label, source, expr)
                if target_text not in source or expr not in source:
                    raise AssertionError(
                        f"{label} must write this value into this target; "
                        f"got {source!r}"
                    )
                rows.append((label, source))
    expected = len(_PRODUCT_KINDS) * len(_PRODUCT_CARRIERS) * len(_PRODUCT_TARGETS)
    labels = [label for label, _source in rows]
    if len(rows) != expected or len(set(labels)) != expected:
        raise AssertionError(
            f"widening product must be {expected} distinct cells; got {labels}"
        )
    return tuple(rows)


def snippet_known_assigned_into_anonymous_object(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    return (
        header
        + f"let {binding}: {{ {key}: {command} }};\n"
        + f"{binding} = {known_object(key, starter)};\n"
    )


def _require_direct_inline_object_assertion(
    source: str,
    *,
    literal: str,
    inline: str,
    binding: str,
    twin: bool,
) -> None:
    """The asserted expression is the object literal, and the target is inline."""
    needle = f"{literal} as {inline}"
    if source.count(needle) != 1 or source.count(literal) != 1:
        raise AssertionError(
            "assertion must assert this object literal directly to this "
            f"inline object type, and nowhere else; got {source!r}"
        )
    if not inline.startswith("{") or f" as {inline}" not in source:
        raise AssertionError(
            f"assertion target must be the inline object type; got {source!r}"
        )
    if f"{binding}:" in source:
        raise AssertionError(
            f"the binding must not carry the inline object type as an "
            f"annotation; got {source!r}"
        )
    for forbidden in (" as unknown", " as object", " as any", "Record<"):
        if forbidden in source:
            raise AssertionError(
                "assertion type must be the inline object type, not a "
                f"keyword or Record; got {source!r}"
            )
    comment, _statement = source.split("const ", 1)
    if "SAFETY:" not in comment or comment.split("SAFETY:", 1)[1].strip() == "":
        raise AssertionError(
            f"assertion needs a non-empty justification; got {source!r}"
        )
    if twin:
        return
    annotated = snippet_known_into_anonymous_object()
    assigned = snippet_known_assigned_into_anonymous_object()
    if f": {inline} = {literal};" not in annotated:
        raise AssertionError(
            "annotation arm must annotate this object literal as this "
            f"inline object type; got {annotated!r}"
        )
    if f": {inline};" not in assigned or f"{binding} = {literal};" not in assigned:
        raise AssertionError(
            "assignment arm must assign this object literal into this "
            f"inline object type; got {assigned!r}"
        )


def snippet_known_asserted_into_anonymous_object(*, twin: bool = False) -> str:
    """Assert the annotated object literal to that same inline object type.

    The asserted expression is the object literal, not a const alias. The
    assertion type is written inline, not a named alias, a Record, or a
    keyword. A justification sits on the assertion so the safety rule is
    not the failure.
    """
    header, command, starter, key, binding = command_parts(twin=twin)
    literal = known_object(key, starter)
    inline = f"{{ {key}: {command} }}"
    source = header + with_safety(f"const {binding} = {literal} as {inline};\n")
    _require_direct_inline_object_assertion(
        source,
        literal=literal,
        inline=inline,
        binding=binding,
        twin=twin,
    )
    return source


def snippet_known_into_index_signature(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    return (
        header
        + f"const {binding}: {{ [key: string]: {command} }} = "
        + f"{known_object(key, starter)};\n"
    )


def snippet_const_alias_to_open_record(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    source = "source" if not twin else fresh_ident("src")
    return (
        header
        + f"const {source} = {known_object(key, starter)};\n"
        + f"const {binding}: Record<string, {command}> = {source};\n"
    )


def snippet_precise_annotation_without_literal_init(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    named = "Cmd" if not twin else fresh_ident("Exact")
    fn = "take" if not twin else fresh_ident("accept")
    param = "known" if not twin else fresh_ident("got")
    return (
        header
        + f"type {named} = {{ {key}: {command} }};\n"
        + f"function {fn}({param}: {named}) {{\n"
        + f"  const {binding}: Record<string, {command}> = {param};\n"
        + "}\n"
    )


def snippet_empty_dict_on_open_record(*, twin: bool = False) -> str:
    header, command, _starter, _key, binding = command_parts(twin=twin)
    return header + f"const {binding}: Record<string, {command}> = {{}};\n"


def snippet_empty_dict_assigned_on_open_record(*, twin: bool = False) -> str:
    header, command, _starter, _key, binding = command_parts(twin=twin)
    return (
        header
        + f"let {binding}: Record<string, {command}>;\n"
        + f"{binding} = {{}};\n"
    )


def snippet_finite_key_literal_union(*, twin: bool = False) -> str:
    binding = "labels" if not twin else fresh_ident("map")
    a = "a" if not twin else fresh_ident("one")
    b = "b" if not twin else fresh_ident("two")
    return (
        f"const {binding}: Record<\"{a}\" | \"{b}\", number> = "
        f'{{ {a}: 1, {b}: 2 }};\n'
    )


def snippet_finite_key_named_alias(*, twin: bool = False) -> str:
    diet = "Diet" if not twin else fresh_ident("Kind")
    vegan = "vegan" if not twin else fresh_ident("left")
    omni = "omnivore" if not twin else fresh_ident("right")
    binding = "labels" if not twin else fresh_ident("map")
    return (
        f'type {diet} = "{vegan}" | "{omni}";\n'
        f"const {binding}: Record<{diet}, string> = "
        f'{{ {vegan}: "V", {omni}: "O" }};\n'
    )


def snippet_satisfies_open_record(*, twin: bool = False) -> str:
    header, command, starter, key, _binding = command_parts(twin=twin)
    return (
        header
        + f"void ({known_object(key, starter)} satisfies Record<string, {command}>);\n"
    )


def snippet_named_interface_with_keys(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    iface = "Commands" if not twin else fresh_ident("Table")
    return (
        header
        + f"interface {iface} {{ readonly {key}: {command} }}\n"
        + f"const {binding}: {iface} = {known_object(key, starter)};\n"
    )


def snippet_named_alias_with_keys(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    alias = "Commands" if not twin else fresh_ident("Table")
    return (
        header
        + f"type {alias} = {{ readonly {key}: {command} }};\n"
        + f"const {binding}: {alias} = {known_object(key, starter)};\n"
    )


def snippet_undefined_type_name(*, twin: bool = False) -> str:
    header, _command, starter, key, binding = command_parts(twin=twin)
    missing = "MissingName" if not twin else fresh_ident("Absent")
    return (
        header
        + f"const {binding}: {missing} = {known_object(key, starter)};\n"
    )


def snippet_let_alias_to_open_record(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    source = "source" if not twin else fresh_ident("src")
    return (
        header
        + f"let {source} = {known_object(key, starter)};\n"
        + f"const {binding}: Record<string, {command}> = {source};\n"
    )


def snippet_var_alias_to_open_record(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    source = "source" if not twin else fresh_ident("src")
    return (
        header
        + f"var {source} = {known_object(key, starter)};\n"
        + f"const {binding}: Record<string, {command}> = {source};\n"
    )


def write_imported_type_annotation(
    ws: Workspace,
    *,
    twin: bool = False,
) -> Path:
    header, _command, starter, key, binding = command_parts(twin=twin)
    mod = fresh_ident("types")
    exported = "Commands" if not twin else fresh_ident("Table")
    ws.write(
        f"{mod}.ts",
        f"export type {exported} = Record<string, () => void>;\n",
    )
    source = (
        f'import {{ {exported} }} from "./{mod}";\n'
        + header
        + f"const {binding}: {exported} = {known_object(key, starter)};\n"
    )
    return write_f03_source(ws, source, prefix="imp")


# ---------------------------------------------------------------------------
# D. Local unknown type predicates
# ---------------------------------------------------------------------------


def snippet_known_to_unknown_predicate(*, twin: bool = False) -> str:
    pred = "isString" if not twin else fresh_ident("isIt")
    param = "value" if not twin else fresh_ident("arg")
    lit = "known" if not twin else fresh_ident("token")
    return (
        f"function {pred}({param}: unknown): {param} is string {{ return true; }}\n"
        f'{pred}("{lit}");\n'
    )


def snippet_alias_unknown_predicate_parameter(*, block: bool = False) -> str:
    """Local type predicate whose parameter is a same-file alias of unknown.

    The argument is a string literal. ``block`` puts the alias, the predicate,
    and the call in one function, so the alias is block-scoped. Names are fresh
    so the parameter is never the token ``unknown``.
    """
    alias = fresh_ident("Wide")
    pred = fresh_ident("isIt")
    param = fresh_ident("arg")
    lit = fresh_ident("token")
    body = (
        f"type {alias} = unknown;\n"
        f"function {pred}({param}: {alias}): {param} is string {{ return true; }}\n"
        f'{pred}("{lit}");\n'
    )
    if not block:
        return body
    fn = fresh_ident("wrap")
    indented = "".join(f"  {line}\n" for line in body.splitlines())
    return f"function {fn}() {{\n{indented}}}\n"


def snippet_known_to_union_unknown_predicate(*, twin: bool = False) -> str:
    pred = "isString" if not twin else fresh_ident("isIt")
    param = "value" if not twin else fresh_ident("arg")
    lit = "known" if not twin else fresh_ident("token")
    return (
        f"function {pred}({param}: string | unknown): {param} is string "
        f"{{ return true; }}\n"
        f'{pred}("{lit}");\n'
    )


def snippet_known_to_unknown_or_string_predicate() -> str:
    """Local type predicate whose parameter is ``unknown | string``.

    Unknown is the left member, written as the keyword, not an alias of
    unknown. The call argument is a string literal. Names are fresh so the
    call is not one fixed sample.
    """
    pred = fresh_ident("isIt")
    param = fresh_ident("arg")
    lit = fresh_ident("token")
    return (
        f"function {pred}({param}: unknown | string): {param} is string "
        f"{{ return true; }}\n"
        f'{pred}("{lit}");\n'
    )


def snippet_alias_unknown_union_member_predicate(*, block: bool = False) -> str:
    """Local type predicate; one union member is a same-file alias of unknown.

    The parameter is not the alias alone and is not the keyword ``unknown``.
    The other member stays ``string``. The argument is a string literal.
    ``block`` puts the alias, the predicate, and the call in one function.
    """
    alias = fresh_ident("Wide")
    pred = fresh_ident("isIt")
    param = fresh_ident("arg")
    lit = fresh_ident("token")
    body = (
        f"type {alias} = unknown;\n"
        f"function {pred}({param}: string | {alias}): {param} is string "
        f"{{ return true; }}\n"
        f'{pred}("{lit}");\n'
    )
    if not block:
        return body
    fn = fresh_ident("wrap")
    indented = "".join(f"  {line}\n" for line in body.splitlines())
    return f"function {fn}() {{\n{indented}}}\n"


def snippet_const_alias_to_predicate(*, twin: bool = False) -> str:
    pred = "isString" if not twin else fresh_ident("isIt")
    param = "value" if not twin else fresh_ident("arg")
    alias = "known" if not twin else fresh_ident("held")
    lit = "known" if not twin else fresh_ident("token")
    return (
        f"function {pred}({param}: unknown): {param} is string {{ return true; }}\n"
        f'const {alias} = "{lit}";\n'
        f"{pred}({alias});\n"
    )


def snippet_precise_annotation_to_predicate(*, twin: bool = False) -> str:
    pred = "isString" if not twin else fresh_ident("isIt")
    param = "value" if not twin else fresh_ident("arg")
    fn = "check" if not twin else fresh_ident("probe")
    known = "known" if not twin else fresh_ident("got")
    return (
        f"function {pred}({param}: unknown): {param} is string {{ return true; }}\n"
        f"function {fn}({known}: string): boolean {{ return {pred}({known}); }}\n"
    )


def snippet_unknown_arg_to_predicate(*, twin: bool = False) -> str:
    pred = "isString" if not twin else fresh_ident("isIt")
    param = "value" if not twin else fresh_ident("arg")
    held = "input" if not twin else fresh_ident("raw")
    return (
        f"function {pred}({param}: unknown): {param} is string {{ return true; }}\n"
        f"declare const {held}: unknown;\n"
        f"{pred}({held});\n"
    )


def snippet_unparsed_unknown_result_to_predicate(*, twin: bool = False) -> str:
    pred = "isString" if not twin else fresh_ident("isIt")
    param = "value" if not twin else fresh_ident("arg")
    reader = "readInput" if not twin else fresh_ident("load")
    return (
        f"function {pred}({param}: unknown): {param} is string {{ return true; }}\n"
        f"declare function {reader}(): unknown;\n"
        f"{pred}({reader}());\n"
    )


def snippet_let_alias_to_predicate(*, twin: bool = False) -> str:
    pred = "isString" if not twin else fresh_ident("isIt")
    param = "value" if not twin else fresh_ident("arg")
    alias = "known" if not twin else fresh_ident("held")
    lit = "known" if not twin else fresh_ident("token")
    return (
        f"function {pred}({param}: unknown): {param} is string {{ return true; }}\n"
        f'let {alias} = "{lit}";\n'
        f"{pred}({alias});\n"
    )


# ---------------------------------------------------------------------------
# E. Same-file aliases as widening targets
# ---------------------------------------------------------------------------


def snippet_program_scope_open_dictionary(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    alias = "Open" if not twin else fresh_ident("Wide")
    return (
        header
        + f"type {alias} = Record<string, {command}>;\n"
        + f"const {binding}: {alias} = {known_object(key, starter)};\n"
    )


def snippet_block_scoped_open_dictionary(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    alias = "Open" if not twin else fresh_ident("Wide")
    fn = "outer" if not twin else fresh_ident("wrap")
    return (
        header
        + f"function {fn}() {{\n"
        + f"  type {alias} = Record<string, {command}>;\n"
        + f"  const {binding}: {alias} = {known_object(key, starter)};\n"
        + "}\n"
    )


def snippet_block_scoped_unknown(*, twin: bool = False) -> str:
    alias = "U" if not twin else fresh_ident("Wide")
    fn = "outer" if not twin else fresh_ident("wrap")
    binding = "value" if not twin else fresh_ident("held")
    return (
        f"function {fn}() {{\n"
        f"  type {alias} = unknown;\n"
        f"  const {binding}: {alias} = 1;\n"
        f"}}\n"
    )


def snippet_block_scoped_object(*, twin: bool = False) -> str:
    alias = "O" if not twin else fresh_ident("Wide")
    fn = "outer" if not twin else fresh_ident("wrap")
    binding = "value" if not twin else fresh_ident("held")
    return (
        f"function {fn}() {{\n"
        f"  type {alias} = object;\n"
        f"  const {binding}: {alias} = [];\n"
        f"}}\n"
    )


def _require_alias_flow(
    label: str,
    source: str,
    *,
    alias: str,
    resolved: str,
    kind: str,
    literal: str,
    block: bool,
) -> None:
    """The alias is the target of this vehicle, and the value is not asserted."""
    declaration = f"type {alias} = {resolved};"
    if declaration not in source or f"type {alias}<" in source:
        raise AssertionError(
            f"{label} must declare a non-generic alias of {resolved}; got {source!r}"
        )
    if resolved == "any" or " = any;" in source or ": any" in source:
        raise AssertionError(f"{label} must not alias any; got {source!r}")
    for forbidden in ("Record<string, unknown>", "Record<string, any>", " as "):
        if forbidden in source:
            raise AssertionError(
                f"{label} must not assert the value or stand in for a broad "
                f"record; got {source!r}"
            )
    vehicle_lines = [
        line
        for line in source.splitlines()
        if line.strip() != declaration
    ]
    written_target = f": {resolved}" if not resolved.startswith("Record<") else ": Record<"
    if any(written_target in line for line in vehicle_lines):
        raise AssertionError(
            f"{label} vehicle must name the alias, not the written target; "
            f"got {source!r}"
        )
    if kind == "return":
        if f"(): {alias} {{" not in source or f"return {literal};" not in source:
            raise AssertionError(
                f"{label} must return {literal} through the alias; got {source!r}"
            )
        if f": {alias} =" in source or f": {alias};" in source or "const " in source:
            raise AssertionError(
                f"{label} must not store the value under the alias; got {source!r}"
            )
    elif kind == "field":
        if f": {alias} = {literal};" not in source:
            raise AssertionError(
                f"{label} must initialize the field with {literal}; got {source!r}"
            )
        if "const " in source or "let " in source or "return " in source:
            raise AssertionError(
                f"{label} must be a class field, not a variable or a return; "
                f"got {source!r}"
            )
    elif kind == "assign":
        let_lines = [line for line in source.splitlines() if "let " in line]
        if let_lines != [f"let {line.split()[1].split(':')[0]}: {alias};" for line in let_lines]:
            raise AssertionError(
                f"{label} let must be declared with the alias and no initializer; "
                f"got {source!r}"
            )
        if len(let_lines) != 1 or f"{let_lines[0].split()[1].split(':')[0]} = {literal};" not in source:
            raise AssertionError(
                f"{label} must assign {literal} to that let; got {source!r}"
            )
        if "const " in source or "return " in source or "class " in source:
            raise AssertionError(
                f"{label} must be an assignment into the declared let; got {source!r}"
            )
    else:
        raise AssertionError(f"unknown alias vehicle {kind}")
    declared_on = next(line for line in source.splitlines() if declaration in line)
    if block:
        if source.count("function ") != 2 or not declared_on.startswith("  "):
            raise AssertionError(
                f"{label} alias must be block-scoped inside the enclosing "
                f"function; got {source!r}"
            )
        if source.index(declaration) > source.index(f"(): {alias}"):
            raise AssertionError(
                f"{label} alias must be declared before the return type; "
                f"got {source!r}"
            )
    elif declared_on != declaration:
        raise AssertionError(
            f"{label} alias must sit at file scope; got {source!r}"
        )


def alias_non_annotation_vehicle_sources() -> tuple[tuple[str, str], ...]:
    """Known literals flowing through a same-file alias on the other vehicles.

    The numeric literal is the one the unknown return already returns. The
    array literal is the one the object return already returns. The object
    literal and the open Record are the ones the program-scope variable
    annotation already uses. Those aliases are the return type and the class
    field type. The unknown alias is also the annotation of a let that is
    then assigned the numeric literal, and a block-scoped alias on the return
    type of the function that returns that literal. No arm stores the value
    and then asserts it. No arm aliases any, and the open record is not
    ``Record<string, unknown>`` or ``Record<string, any>``.
    """
    unknown_return = snippet_known_return_to_unknown()
    object_return = snippet_known_return_to_object()
    if "return 1;" not in unknown_return or "(): unknown" not in unknown_return:
        raise AssertionError(
            f"unknown return must return the numeric literal 1; got {unknown_return!r}"
        )
    if "return [];" not in object_return or "(): object" not in object_return:
        raise AssertionError(
            f"object return must return the array literal []; got {object_return!r}"
        )
    header, command, starter, key, _binding = command_parts(twin=False)
    record = f"Record<string, {command}>"
    literal = known_object(key, starter)
    written = snippet_program_scope_open_dictionary()
    if f"type Open = {record};" not in written or f"= {literal};" not in written:
        raise AssertionError(
            "the variable-annotation arm must alias this open record and "
            f"initialize it with this object literal; got {written!r}"
        )
    field_unknown = snippet_known_class_field_to_unknown()
    field_object = snippet_known_class_field_to_object()
    field_record = snippet_known_class_field_to_open_record()
    if ": unknown = 1;" not in field_unknown or ": object = [];" not in field_object:
        raise AssertionError(
            "class fields must still initialize unknown with 1 and object with []"
        )
    if f": {record} = {literal};" not in field_record:
        raise AssertionError(
            "the open-record class field must still initialize with this "
            f"object literal; got {field_record!r}"
        )
    assigned = snippet_known_assigned_into_unknown()
    if ": unknown;" not in assigned or "= 1;" not in assigned:
        raise AssertionError(
            f"the unknown assignment must assign 1; got {assigned!r}"
        )

    def one(
        label: str,
        resolved: str,
        kind: str,
        value: str,
        *,
        block: bool = False,
        prelude: str = "",
    ) -> tuple[str, str]:
        alias = fresh_ident("Wide")
        if kind == "return" and block:
            outer = fresh_ident("wrap")
            inner = fresh_ident("make")
            body = (
                f"type {alias} = {resolved};\n"
                f"function {inner}(): {alias} {{\n"
                f"  return {value};\n"
                f"}}\n"
            )
            source = f"function {outer}() {{\n{_indent_lines(body)}}}\n"
        elif kind == "return":
            fn = fresh_ident("make")
            source = (
                prelude
                + f"type {alias} = {resolved};\n"
                + f"function {fn}(): {alias} {{\n"
                + f"  return {value};\n"
                + "}\n"
            )
        elif kind == "field":
            cls = fresh_ident("Bag")
            field = fresh_ident("held")
            source = (
                prelude
                + f"type {alias} = {resolved};\n"
                + f"class {cls} {{\n"
                + f"  {field}: {alias} = {value};\n"
                + "}\n"
            )
        elif kind == "assign":
            binding = fresh_ident("held")
            source = (
                f"type {alias} = {resolved};\n"
                f"let {binding}: {alias};\n"
                f"{binding} = {value};\n"
            )
        else:
            raise AssertionError(f"unknown alias vehicle {kind}")
        _require_alias_flow(
            label,
            source,
            alias=alias,
            resolved=resolved,
            kind=kind,
            literal=value,
            block=block,
        )
        return label, source

    return (
        one("return-unknown", "unknown", "return", "1"),
        one("return-object", "object", "return", "[]"),
        one("return-record", record, "return", literal, prelude=header),
        one("field-unknown", "unknown", "field", "1"),
        one("field-object", "object", "field", "[]"),
        one("field-record", record, "field", literal, prelude=header),
        one("assign-unknown", "unknown", "assign", "1"),
        one("return-unknown-block", "unknown", "return", "1", block=True),
    )


def snippet_identity_open_dictionary(*, twin: bool = False) -> str:
    header, command, starter, key, binding = command_parts(twin=twin)
    ident = "Identity" if not twin else fresh_ident("Id")
    param = "T" if not twin else fresh_ident("P")
    return (
        header
        + f"type {ident}<{param}> = {param};\n"
        + f"const {binding}: {ident}<Record<string, {command}>> = "
        + f"{known_object(key, starter)};\n"
    )


# ---------------------------------------------------------------------------
# F. Widen then assert
# ---------------------------------------------------------------------------


def snippet_unknown_store_then_assert(*, twin: bool = False) -> str:
    source = "source" if not twin else fresh_ident("src")
    wide = "widened" if not twin else fresh_ident("wide")
    parsed = "parsed" if not twin else fresh_ident("got")
    field = "id" if not twin else fresh_ident("slot")
    return (
        f"const {source} = {{ {field}: \"second\" }};\n"
        f"const {wide}: unknown = {source};\n"
        + with_safety(
            f"const {parsed} = {wide} as {{ readonly {field}: string }};\n"
        )
    )


def snippet_literal_unknown_store_then_assert(kind: str) -> str:
    """Numeric or array literal stored under unknown, then asserted narrower.

    The initializer of the unknown binding is the literal itself, in one
    function, and the later assertion names that same binding. A justification
    sits on the assertion so a missing safety comment is not the failure.
    The literal is chosen at runtime; the observation is the known form.
    """
    if kind not in {"numeric", "array"}:
        raise ValueError(f"unknown literal kind {kind!r}")
    left = 2 + secrets.randbelow(8000)
    right = 2 + secrets.randbelow(8000)
    literal = str(left) if kind == "numeric" else f"[{left}, {right}]"
    narrower = "number" if kind == "numeric" else "number[]"
    wide = fresh_ident("wide")
    parsed = fresh_ident("got")
    fn = fresh_ident("load")
    body = (
        f"const {wide}: unknown = {literal};\n"
        + with_safety(f"const {parsed} = {wide} as {narrower};\n")
    )
    indented = "".join(f"  {line}\n" for line in body.splitlines())
    return f"function {fn}() {{\n{indented}  return {parsed};\n}}\n"


def alias_store_then_assert_sources() -> tuple[tuple[str, str], ...]:
    """Known store under a same-file non-generic alias, then a narrower assertion.

    The unknown arm stores a known object under an alias of ``unknown``. The
    object arm stores a known value under an alias of ``object``. The alias,
    the const, and the assertion of that same const sit in one function. The
    const annotation is the alias, not the keyword and not a written
    ``Record``. A justification sits on the assertion so a missing safety
    comment is not the failure. Neither arm is an alias of ``any``.
    """
    def one(
        label: str,
        resolved: str,
        store: str,
        narrower: str,
        *,
        alias: str,
        wide: str,
    ) -> str:
        parsed = fresh_ident("got")
        fn = fresh_ident("load")
        body = (
            f"type {alias} = {resolved};\n"
            f"{store}\n"
            + with_safety(f"const {parsed} = {wide} as {narrower};\n")
            + f"return {parsed};\n"
        )
        source_text = f"function {fn}() {{\n{_indent_lines(body)}}}\n"
        if f"const {wide}: {alias} =" not in source_text:
            raise AssertionError(
                f"{label} store must annotate the const with the alias; "
                f"got {source_text!r}"
            )
        if f": {resolved}" in source_text or ": any" in source_text:
            raise AssertionError(
                f"{label} store must not write the keyword as the const "
                f"annotation; got {source_text!r}"
            )
        if "Record<" in source_text:
            raise AssertionError(
                f"{label} store must not replace a written Record; "
                f"got {source_text!r}"
            )
        if f"{wide} as {narrower}" not in source_text:
            raise AssertionError(
                f"{label} must assert that same const to a narrower type; "
                f"got {source_text!r}"
            )
        return source_text

    field = fresh_ident("slot")
    source = fresh_ident("src")
    unknown_alias = fresh_ident("Wide")
    unknown_wide = fresh_ident("wide")
    unknown = one(
        "unknown",
        "unknown",
        f'const {source} = {{ {field}: "second" }};\n'
        f"const {unknown_wide}: {unknown_alias} = {source};",
        f"{{ readonly {field}: string }}",
        alias=unknown_alias,
        wide=unknown_wide,
    )
    left = 2 + secrets.randbelow(8000)
    right = 2 + secrets.randbelow(8000)
    object_alias = fresh_ident("Wide")
    object_wide = fresh_ident("wide")
    object_arm = one(
        "object",
        "object",
        f"const {object_wide}: {object_alias} = [{left}, {right}];",
        "number[]",
        alias=object_alias,
        wide=object_wide,
    )
    return (("unknown", unknown), ("object", object_arm))


def snippet_unknown_store_then_angle_assert(*, twin: bool = False) -> str:
    source = "source" if not twin else fresh_ident("src")
    wide = "widened" if not twin else fresh_ident("wide")
    parsed = "parsed" if not twin else fresh_ident("got")
    field = "id" if not twin else fresh_ident("slot")
    return (
        f"const {source} = {{ {field}: \"second\" }};\n"
        f"const {wide}: unknown = {source};\n"
        + with_safety(
            f"const {parsed} = <{{ readonly {field}: string }}>{wide};\n"
        )
    )


def _indent_lines(text: str, spaces: int = 2) -> str:
    pad = " " * spaces
    return "".join(f"{pad}{line}\n" for line in text.splitlines())


def snippet_store_then_assert(
    store: str,
    *,
    twin: bool = True,
    scope: str = "function",
    narrow: str = "named",
) -> str:
    source = fresh_ident("src") if twin else "source"
    wide = fresh_ident("wide") if twin else "widened"
    parsed = fresh_ident("got") if twin else "parsed"
    field = fresh_ident("slot") if twin else "id"
    named = fresh_ident("Parsed") if twin else "Parsed"
    fn = fresh_ident("load") if twin else "load"
    annotation = {
        "unknown": "unknown",
        "any": "any",
        "object": "object",
        "record": "Record<string, unknown>",
    }[store]
    target = (
        f"{{ readonly {field}: string }}"
        if narrow == "literal"
        else named
    )
    header = "" if narrow == "literal" else (
        f"type {named} = {{ readonly {field}: string }};\n"
    )
    store_and_assert = (
        f"const {source} = {{ {field}: \"second\" }};\n"
        f"const {wide}: {annotation} = {source};\n"
        + with_safety(f"const {parsed} = {wide} as {target};\n")
    )
    if scope == "top":
        return header + store_and_assert
    indented = "".join(f"  {line}\n" for line in store_and_assert.splitlines())
    return header + f"function {fn}() {{\n{indented}  return {parsed};\n}}\n"


def _any_named_store_lines() -> tuple[str, str, str, str, str]:
    """Fresh names, header, store lines, and the justified narrower assertion.

    The store annotation is ``any``, so a later narrower assertion is this
    rule alone. The assertion names a type alias, so the assertion itself
    is not an anonymous-object widening. The fifth item is the widened binding.
    """
    source = fresh_ident("src")
    wide = fresh_ident("wide")
    parsed = fresh_ident("got")
    field = fresh_ident("slot")
    named = fresh_ident("Parsed")
    header = f"type {named} = {{ readonly {field}: string }};\n"
    store = (
        f"const {source} = {{ {field}: \"second\" }};\n"
        f"const {wide}: any = {source};\n"
    )
    assertion = with_safety(f"const {parsed} = {wide} as {named};\n")
    return header, store, assertion, parsed, wide


def snippet_store_then_assert_after_statement() -> str:
    """Same function. One ordinary statement sits between store and assertion.

    The narrower assertion is not the next statement. A justification sits
    on the assertion so a missing safety comment is not the failure.
    """
    header, store, assertion, parsed, _wide = _any_named_store_lines()
    fn = fresh_ident("load")
    gap = f"void {2 + secrets.randbelow(8000)};\n"
    body = _indent_lines(store + gap + assertion + f"return {parsed};\n")
    return header + f"function {fn}() {{\n{body}}}\n"


def snippet_store_then_assert_in_nested_block() -> str:
    """The later assertion sits in a nested block of the storing function.

    The block is not itself the assertion. Both steps are still that function.
    """
    header, store, assertion, _parsed, wide = _any_named_store_lines()
    fn = fresh_ident("load")
    block = "{\n" + _indent_lines(assertion) + "}\n"
    body = _indent_lines(store + block + f"return {wide};\n")
    return header + f"function {fn}() {{\n{body}}}\n"


def snippet_assert_widened_const_in_nested_function() -> str:
    """Store a known value under unknown, then assert it in a nested function.

    The assertion is not in the same function, so no-widen-then-assert stays
    silent. The unknown store is still a known-value widening. The assertion
    names a type alias and carries a justification, so neither an anonymous
    object nor a missing safety comment is the failure.
    """
    source = fresh_ident("src")
    wide = fresh_ident("wide")
    parsed = fresh_ident("got")
    field = fresh_ident("slot")
    named = fresh_ident("Parsed")
    outer = fresh_ident("load")
    inner = fresh_ident("read")
    header = f"type {named} = {{ readonly {field}: string }};\n"
    assertion = with_safety(f"const {parsed} = {wide} as {named};\n")
    inner_fn = (
        f"function {inner}() {{\n"
        + _indent_lines(assertion + f"return {parsed};\n")
        + "}\n"
    )
    store = (
        f"const {source} = {{ {field}: \"second\" }};\n"
        f"const {wide}: unknown = {source};\n"
    )
    body = _indent_lines(store + inner_fn + f"return {inner};\n")
    return header + f"function {outer}() {{\n{body}}}\n"


def snippet_widen_without_later_assert(store: str = "unknown") -> str:
    source = fresh_ident("src")
    wide = fresh_ident("wide")
    field = fresh_ident("slot")
    annotation = {
        "unknown": "unknown",
        "any": "any",
        "object": "object",
        "record": "Record<string, unknown>",
    }[store]
    return (
        f"const {source} = {{ {field}: \"second\" }};\n"
        f"const {wide}: {annotation} = {source};\n"
    )


def snippet_assert_already_unknown(*, twin: bool = False) -> str:
    held = "input" if not twin else fresh_ident("raw")
    parsed = "parsed" if not twin else fresh_ident("got")
    field = "id" if not twin else fresh_ident("slot")
    return (
        f"declare const {held}: unknown;\n"
        + with_safety(
            f"const {parsed} = {held} as {{ readonly {field}: string }};\n"
        )
    )


def snippet_later_assert_different_binding(*, store: str = "unknown") -> str:
    source = fresh_ident("src")
    wide = fresh_ident("wide")
    other = fresh_ident("other")
    parsed = fresh_ident("got")
    field = fresh_ident("slot")
    annotation = {
        "unknown": "unknown",
        "any": "any",
        "object": "object",
        "record": "Record<string, unknown>",
    }[store]
    return (
        f"const {source} = {{ {field}: \"second\" }};\n"
        f"const {wide}: {annotation} = {source};\n"
        f"declare const {other}: unknown;\n"
        + with_safety(
            f"const {parsed} = {other} as {{ readonly {field}: string }};\n"
        )
    )


def snippet_later_assert_still_broad(*, store: str = "unknown", later: str = "unknown") -> str:
    source = fresh_ident("src")
    wide = fresh_ident("wide")
    parsed = fresh_ident("got")
    field = fresh_ident("slot")
    annotation = {
        "unknown": "unknown",
        "any": "any",
        "object": "object",
        "record": "Record<string, unknown>",
    }[store]
    asserted = {
        "unknown": "unknown",
        "any": "any",
        "object": "object",
        "record": "Record<string, unknown>",
    }[later]
    return (
        f"const {source} = {{ {field}: \"second\" }};\n"
        f"const {wide}: {annotation} = {source};\n"
        + with_safety(f"const {parsed} = {wide} as {asserted};\n")
    )


def still_broad_same_type_sources() -> tuple[tuple[str, str, str], ...]:
    """Same names and store. Only the later assertion type changes.

    The first source asserts that binding to a fresh object type, which is
    narrower. The second asserts it back to the same broad type it was stored
    under. ``any`` uses a named object type so the narrower assertion is not
    itself a widening target. ``object`` uses an inline object type. Both
    assertions carry one justification, so a missing comment is not the
    failure. The unknown arm stays on ``snippet_later_assert_still_broad``.
    """
    rows: list[tuple[str, str, str]] = []
    for label, annotation in (("any", "any"), ("object", "object")):
        source = fresh_ident("src")
        wide = fresh_ident("wide")
        parsed = fresh_ident("got")
        field = fresh_ident("slot")
        comment = safety_comment(text=generated_justification())
        header = ""
        if label == "any":
            named = fresh_ident("Parsed")
            header = f"type {named} = {{ readonly {field}: string }};\n"
            narrower = named
        else:
            narrower = f"{{ readonly {field}: string }}"
        store = (
            f"{header}"
            f'const {source} = {{ {field}: "second" }};\n'
            f"const {wide}: {annotation} = {source};\n"
        )
        narrow_arm = store + f"{comment}\nconst {parsed} = {wide} as {narrower};\n"
        same_arm = store + f"{comment}\nconst {parsed} = {wide} as {annotation};\n"
        rows.append((label, narrow_arm, same_arm))
    return tuple(rows)


def still_broad_record_same_type_sources() -> tuple[tuple[str, str], ...]:
    """Known object stored under a broad record, then asserted back to it.

    A broad record is the written ``Record`` utility with key ``string`` and
    value ``unknown`` or ``any``. Each arm asserts that same const binding
    back to the annotation it was stored under. One justification sits
    immediately above that assertion. The later type is not a fresh object
    type with a named field. The keyword same-type arms and the narrower
    named-field arms stay elsewhere.
    """
    rows: list[tuple[str, str]] = []
    for label, annotation in (
        ("unknown", "Record<string, unknown>"),
        ("any", "Record<string, any>"),
    ):
        source = fresh_ident("src")
        wide = fresh_ident("wide")
        parsed = fresh_ident("got")
        field = fresh_ident("slot")
        comment = safety_comment(text=generated_justification())
        body = (
            f'const {source} = {{ {field}: "second" }};\n'
            f"const {wide}: {annotation} = {source};\n"
            f"{comment}\n"
            f"const {parsed} = {wide} as {annotation};\n"
        )
        if f"const {wide}: {annotation} = {source};" not in body:
            raise AssertionError(
                "broad-record same-type arm must store the known object "
                f"under {annotation}; got {body!r}"
            )
        if f"{wide} as {annotation}" not in body:
            raise AssertionError(
                "broad-record same-type arm must assert that same const "
                f"binding back to {annotation}; got {body!r}"
            )
        if comment not in body or f"{comment}\nconst {parsed}" not in body:
            raise AssertionError(
                "broad-record same-type arm must justify the assertion; "
                f"got {body!r}"
            )
        if "readonly" in body or " as {" in body:
            raise AssertionError(
                "broad-record same-type arm must not narrow to a named field; "
                f"got {body!r}"
            )
        rows.append((label, body))
    return tuple(rows)


# ---------------------------------------------------------------------------
# G / H. Safety-comment justifications and markers
# ---------------------------------------------------------------------------


def snippet_non_const_as_without_comment(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    return f"const {held} = {value} as {target};\n"


def snippet_angle_without_comment(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    return f"const {held} = <{target}>{value};\n"


def snippet_export_without_comment(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    return f"export const {held} = {value} as {target};\n"


def snippet_comment_after_assertion(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    reason = generated_justification()
    return (
        f"const {held} = {value} as {target}; "
        f"// SAFETY: {reason}\n"
    )


def snippet_comment_on_earlier_sibling(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    other = fresh_ident("prev")
    reason = generated_justification()
    return (
        f"{safety_comment(text=reason)}\n"
        f"const {other} = 1;\n"
        f"const {held} = {value} as {target};\n"
    )


def snippet_non_marker_comment(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    note = fresh_ident("note")
    return (
        f"// {note}: {generated_justification()}\n"
        f"const {held} = {value} as {target};\n"
    )


def snippet_empty_after_colon(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    return f"// SAFETY:\nconst {held} = {value} as {target};\n"


def snippet_whitespace_after_colon(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    return f"// SAFETY:   \nconst {held} = {value} as {target};\n"


def snippet_block_comment_immediately_above(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    reason = generated_justification()
    return (
        f"/* SAFETY: {reason} */\n"
        f"const {held} = {value} as {target};\n"
    )


def snippet_safety_immediately_above(
    *,
    twin: bool = False,
    text: str | None = None,
    marker: str = "SAFETY",
) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    reason = PUBLIC_SAFETY_TEXT if text is None and not twin else (
        generated_justification() if text is None else text
    )
    return (
        f"{safety_comment(marker=marker, text=reason)}\n"
        f"const {held} = {value} as {target};\n"
    )


def snippet_inline_justification(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    reason = generated_justification()
    return (
        f"const {held} = /* SAFETY: {reason} */ {value} as {target};\n"
    )


def snippet_export_with_justification(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    reason = generated_justification()
    return (
        f"{safety_comment(text=reason)}\n"
        f"export const {held} = {value} as {target};\n"
    )


def snippet_angle_with_justification(*, twin: bool = False) -> str:
    target = "UserId" if not twin else fresh_ident("Brand")
    value = "value" if not twin else fresh_ident("raw")
    held = "id" if not twin else fresh_ident("got")
    reason = generated_justification()
    return (
        f"{safety_comment(text=reason)}\n"
        f"const {held} = <{target}>{value};\n"
    )


def snippet_as_const_no_comment(*, twin: bool = False) -> str:
    held = "values" if not twin else fresh_ident("tuple")
    return f"const {held} = [1, 2] as const;\n"


def snippet_angle_const_no_comment(*, twin: bool = False) -> str:
    held = "value" if not twin else fresh_ident("held")
    field = "id" if not twin else fresh_ident("slot")
    return f"const {held} = <const>{{ {field}: \"one\" }};\n"


def snippet_justification_with_marker(marker: str, *, twin: bool = True) -> str:
    target = fresh_ident("Brand") if twin else "UserId"
    value = fresh_ident("raw") if twin else "value"
    held = fresh_ident("got") if twin else "id"
    reason = generated_justification()
    return (
        f"{safety_comment(marker=marker, text=reason)}\n"
        f"const {held} = {value} as {target};\n"
    )


def _fresh_as_line() -> str:
    """One non-const ``as`` statement. Callers attach comments to this line."""
    target = fresh_ident("Brand")
    value = fresh_ident("raw")
    held = fresh_ident("got")
    return f"const {held} = {value} as {target};"


def _line_above(statement: str, comment: str) -> str:
    return f"{comment}\n{statement}\n"


# ---------------------------------------------------------------------------
# Paired contrasts: one statement, one binding, or one expression
# ---------------------------------------------------------------------------


def const_exemption_sources() -> tuple[str, str, str, str]:
    """Same literal and binding. The non-const target is a fresh name; only const changes."""
    held = fresh_ident("held")
    target = fresh_ident("Brand")
    array_report = f"const {held} = [1, 2] as {target};\n"
    array_const = f"const {held} = [1, 2] as const;\n"
    other = fresh_ident("held")
    object_target = fresh_ident("Brand")
    object_report = f'const {other} = <{object_target}>{{ id: "one" }};\n'
    object_const = f'const {other} = <const>{{ id: "one" }};\n'
    return array_report, array_const, object_report, object_const


def inline_justification_sources() -> tuple[str, str]:
    """Same assertion. The inline comment is the only difference."""
    target = fresh_ident("Brand")
    value = fresh_ident("raw")
    held = fresh_ident("got")
    reason = generated_justification()
    bare = f"const {held} = {value} as {target};\n"
    inline = f"const {held} = /* SAFETY: {reason} */ {value} as {target};\n"
    return bare, inline


def safety_above_sources() -> tuple[str, str, str, str, str, str, str]:
    """One non-const assertion. Markers omitted. Only the comment text changes.

    ``checked`` and ``leading`` put a word before the default marker. The
    marker is not the first token. The comment still contains that marker,
    a colon, and non-whitespace after the colon. ``before_colon`` puts one
    space between the default marker and the colon. The colon is not the
    next character after the marker. The comment still contains that marker,
    a colon, and non-whitespace after the colon.
    """
    statement = _fresh_as_line()
    other = generated_justification()
    foreign = fresh_ident("note")
    lead = fresh_ident("lead")
    bare = statement + "\n"
    oracle = _line_above(statement, f"// SAFETY: {PUBLIC_SAFETY_TEXT}")
    alternate = _line_above(statement, f"// SAFETY: {other}")
    checked = _line_above(statement, "// checked SAFETY: parsed before branding")
    leading = _line_above(statement, f"// {lead} SAFETY: {other}")
    before_colon = _line_above(statement, "// SAFETY : parsed before branding")
    not_safety = _line_above(statement, f"// {foreign}: {other}")
    return bare, oracle, alternate, checked, leading, not_safety, before_colon


def block_comment_sources() -> tuple[str, str, str, str, str, str, str, str]:
    """One non-const ``as``. The ``as`` arms differ only in the nearby comment.

    ``block`` is a block comment immediately above the statement: the default
    marker, a colon, and words. ``block_foreign`` is a block comment
    immediately above that is not that marker, but still has a colon and
    words. ``block_empty`` is that marker as a block comment with nothing
    after the colon. ``inline_valid`` puts the passing block text on the
    assertion. ``inline_foreign`` and ``inline_empty`` are the two failures
    as inline comments on that same assertion. ``angle_foreign`` is an inline
    comment that is not a justification on one angle-bracket assertion.
    A word before the marker, a glued colon, and a punctuation-only tail stay
    on the line-comment arms.
    """
    held = fresh_ident("got")
    value = fresh_ident("raw")
    target = fresh_ident("Brand")
    statement = f"const {held} = {value} as {target};"
    reason = generated_justification()
    foreign = fresh_ident("note")
    if (
        not reason
        or not foreign
        or foreign == "SAFETY"
        or "SAFETY" in foreign
        or "SAFETY" in reason
        or ":" in foreign
        or ":" in reason
    ):
        raise AssertionError(
            "a non-marker comment needs a fresh word that is not the default "
            f"marker; foreign={foreign!r} reason={reason!r}"
        )
    bare = statement + "\n"
    block = f"/* SAFETY: {reason} */\n{statement}\n"
    block_foreign = f"/* {foreign}: {reason} */\n{statement}\n"
    block_empty = f"/* SAFETY:*/\n{statement}\n"
    inline_valid = f"const {held} = /* SAFETY: {reason} */ {value} as {target};\n"
    inline_foreign = f"const {held} = /* {foreign}: {reason} */ {value} as {target};\n"
    inline_empty = f"const {held} = /* SAFETY:*/ {value} as {target};\n"
    angle_held = fresh_ident("got")
    angle_value = fresh_ident("raw")
    angle_target = fresh_ident("Brand")
    angle_foreign = (
        f"const {angle_held} = /* {foreign}: {reason} */ "
        f"<{angle_target}>{angle_value};\n"
    )
    as_arms = (
        ("bare", bare),
        ("block", block),
        ("block-foreign", block_foreign),
        ("block-empty", block_empty),
        ("inline-valid", inline_valid),
        ("inline-foreign", inline_foreign),
        ("inline-empty", inline_empty),
    )
    for label, text in as_arms:
        if statement not in text and f"{value} as {target}" not in text:
            raise AssertionError(
                f"{label} must be that same non-const as; got {text!r}"
            )
        if " as const" in text or "<const>" in text:
            raise AssertionError(f"{label} must not be a const assertion; got {text!r}")
    if "SAFETY" in block_foreign or "SAFETY" in inline_foreign or "SAFETY" in angle_foreign:
        raise AssertionError(
            "a non-marker comment must not contain the default marker; "
            f"block={block_foreign!r} inline={inline_foreign!r} "
            f"angle={angle_foreign!r}"
        )
    for label, text in (
        ("block-foreign", block_foreign),
        ("inline-foreign", inline_foreign),
        ("angle-foreign", angle_foreign),
    ):
        if f"{foreign}: {reason}" not in text:
            raise AssertionError(
                f"{label} must be a non-marker with a colon and words; got {text!r}"
            )
    for label, text in (("block-empty", block_empty), ("inline-empty", inline_empty)):
        if "/* SAFETY:*/" not in text or "SAFETY: " in text or reason in text:
            raise AssertionError(
                f"{label} must be the marker with nothing after the colon; "
                f"got {text!r}"
            )
    if not block.startswith(f"/* SAFETY: {reason} */\n") or "/*" not in inline_valid:
        raise AssertionError(
            "the passing comments must be a block comment above and an inline "
            f"comment on the assertion; block={block!r} inline={inline_valid!r}"
        )
    if "//" in angle_foreign or " as " in angle_foreign or "/*" not in angle_foreign:
        raise AssertionError(
            "the angle-bracket arm must be an inline comment on that assertion; "
            f"got {angle_foreign!r}"
        )
    if block_foreign.split("\n", 1)[1] != bare or block_empty.split("\n", 1)[1] != bare:
        raise AssertionError(
            "block-comment arms may differ only in the comment immediately above"
        )
    return (
        bare,
        block,
        block_foreign,
        block_empty,
        inline_valid,
        inline_foreign,
        inline_empty,
        angle_foreign,
    )


def comment_after_sources() -> tuple[str, str, str]:
    """One non-const ``as``. The first two arms share that statement and comment.

    ``above`` puts the comment immediately before the statement. ``after``
    puts that same comment on the statement's line, after the semicolon.
    ``following`` is that statement on one line and a configured
    justification on the next line, with no later statement.
    """
    statement = _fresh_as_line()
    comment = f"// SAFETY: {generated_justification()}"
    above = _line_above(statement, comment)
    after = f"{statement} {comment}\n"
    following = f"{statement}\n// SAFETY: {PUBLIC_SAFETY_TEXT}\n"
    return above, after, following


def comment_on_earlier_sibling_sources() -> tuple[str, str, str, str]:
    """Same ordinary statement, assertion, and comment.

    ``attached`` puts the comment on the line immediately above the assertion.
    ``earlier`` puts that comment on the line immediately above the ordinary
    statement. ``blank`` puts only a blank line between that comment and the
    assertion. ``gap_before`` puts a blank line before the comment, and the
    comment stays on the line immediately above the assertion.
    """
    statement = _fresh_as_line()
    comment = f"// SAFETY: {generated_justification()}"
    ordinary = f"const {fresh_ident('prev')} = 1;"
    attached = f"{ordinary}\n{comment}\n{statement}\n"
    earlier = f"{comment}\n{ordinary}\n{statement}\n"
    blank = f"{ordinary}\n{comment}\n\n{statement}\n"
    gap_before = f"{ordinary}\n\n{comment}\n{statement}\n"
    return attached, earlier, blank, gap_before


def export_justification_sources() -> tuple[str, str]:
    """One fresh export. The comment immediately above it is the only difference."""
    statement = (
        f"export const {fresh_ident('got')} = {fresh_ident('raw')} "
        f"as {fresh_ident('Brand')};"
    )
    bare = statement + "\n"
    justified = _line_above(statement, f"// SAFETY: {generated_justification()}")
    return bare, justified


def angle_justification_sources() -> tuple[str, str, str, str, str, str, str]:
    """Angle-bracket pairs. Each justified arm differs from its baseline only by the comment.

    ``bare`` / ``above`` is one non-exported const. The comment is a line
    comment immediately above that statement.

    ``block`` is that same non-exported statement. The comment immediately
    above it is a block comment: the default marker, a colon, and words.
    Foreign-marker and empty-after-colon block arms stay on the ``as`` test.

    ``export_bare`` / ``export_above`` is one export of an angle-bracket
    assertion. The comment sits immediately above that same export.

    ``inline_bare`` / ``inline`` is one non-exported const. The comment is
    inline on that assertion. Markers stay omitted, so the default marker
    is the configured one.
    """
    statement = (
        f"const {fresh_ident('got')} = <{fresh_ident('Brand')}>{fresh_ident('raw')};"
    )
    bare = statement + "\n"
    above_reason = generated_justification()
    above = _line_above(statement, f"// SAFETY: {above_reason}")
    block_reason = generated_justification()
    block = f"/* SAFETY: {block_reason} */\n{bare}"

    export_statement = (
        f"export const {fresh_ident('got')} = "
        f"<{fresh_ident('Brand')}>{fresh_ident('raw')};"
    )
    export_bare = export_statement + "\n"
    export_reason = generated_justification()
    export_above = _line_above(export_statement, f"// SAFETY: {export_reason}")

    inline_held = fresh_ident("got")
    inline_target = fresh_ident("Brand")
    inline_value = fresh_ident("raw")
    inline_reason = generated_justification()
    inline_bare = f"const {inline_held} = <{inline_target}>{inline_value};\n"
    inline = (
        f"const {inline_held} = /* SAFETY: {inline_reason} */ "
        f"<{inline_target}>{inline_value};\n"
    )

    if (
        not above_reason
        or not block_reason
        or not export_reason
        or not inline_reason
        or ":" in above_reason
        or ":" in block_reason
        or ":" in export_reason
        or ":" in inline_reason
        or "SAFETY" in above_reason
        or "SAFETY" in block_reason
        or "SAFETY" in export_reason
        or "SAFETY" in inline_reason
        or not block_reason.strip()
    ):
        raise AssertionError(
            "a justification tail must be non-empty and must not itself be "
            f"the marker; above={above_reason!r} block={block_reason!r} "
            f"export={export_reason!r} inline={inline_reason!r}"
        )
    if bare.startswith("export ") or " as " in bare or "<" not in bare:
        raise AssertionError(
            f"the line-comment pair must be a non-exported angle-bracket; got {bare!r}"
        )
    if above != f"// SAFETY: {above_reason}\n{bare}":
        raise AssertionError(
            "the line comment must sit immediately above that same "
            f"non-exported angle-bracket; above={above!r} bare={bare!r}"
        )
    if block != f"/* SAFETY: {block_reason} */\n{bare}":
        raise AssertionError(
            "the block comment must sit immediately above that same "
            f"non-exported angle-bracket; block={block!r} bare={bare!r}"
        )
    if "//" in block or " as " in block or block.startswith("export "):
        raise AssertionError(
            "the block arm must be a block comment on a non-exported "
            f"angle-bracket; got {block!r}"
        )
    if (
        not export_bare.startswith("export const ")
        or " as " in export_bare
        or "<" not in export_bare
    ):
        raise AssertionError(
            f"the export pair must be an exported angle-bracket; got {export_bare!r}"
        )
    if export_above != f"// SAFETY: {export_reason}\n{export_bare}":
        raise AssertionError(
            "the justification must sit immediately above that same export; "
            f"above={export_above!r} bare={export_bare!r}"
        )
    if inline_bare.startswith("export ") or " as " in inline_bare or "/*" in inline_bare:
        raise AssertionError(
            "the inline baseline must be a non-exported angle-bracket with "
            f"no comment; got {inline_bare!r}"
        )
    if inline != (
        f"const {inline_held} = /* SAFETY: {inline_reason} */ "
        f"<{inline_target}>{inline_value};\n"
    ):
        raise AssertionError(
            f"the inline arm must be that comment on the same assertion; got {inline!r}"
        )
    if inline.replace(f"/* SAFETY: {inline_reason} */ ", "", 1) != inline_bare:
        raise AssertionError(
            "the inline pair may differ only by the comment on the assertion; "
            f"inline={inline!r} bare={inline_bare!r}"
        )
    return bare, above, block, export_bare, export_above, inline_bare, inline


def explicit_marker_sources() -> tuple[str, str]:
    """One fresh non-const as. Callers pass the same single-marker list on both arms."""
    statement = _fresh_as_line()
    bare = statement + "\n"
    justified = _line_above(statement, f"// SAFETY: {generated_justification()}")
    return bare, justified


def invariant_marker_sources() -> tuple[str, str]:
    """One fresh non-const as. Only the marker word in the comment above it changes."""
    statement = _fresh_as_line()
    reason = generated_justification()
    accepted = _line_above(statement, f"// INVARIANT: {reason}")
    rejected = _line_above(statement, f"// SAFETY: {reason}")
    return accepted, rejected


def named_chain_sources() -> tuple[str, str, str, str]:
    """Each pair shares receiver, one type name, and comment. The chain adds one as of that name."""
    public_comment = safety_comment(text=generated_justification())
    public_single = f"{public_comment}\nvoid (input as User);\n"
    public_chain = f"{public_comment}\nvoid (input as User as User);\n"
    receiver = fresh_ident("val")
    first = fresh_ident("Kind")
    fresh_comment = safety_comment(text=generated_justification())
    fresh_single = f"{fresh_comment}\nvoid ({receiver} as {first});\n"
    fresh_chain = f"{fresh_comment}\nvoid ({receiver} as {first} as {first});\n"
    return public_single, public_chain, fresh_single, fresh_chain


def parenthesized_chain_sources() -> tuple[str, str]:
    """One parenthesized assertion and comment. The chain arm adds one as inside the parentheses."""
    receiver = fresh_ident("val")
    target = fresh_ident("Target")
    comment = safety_comment(text=generated_justification())
    single = f"{comment}\nvoid (({receiver} as {target}));\n"
    chain = f"{comment}\nvoid (({receiver} as {target} as {target}));\n"
    return single, chain


def bad_justification_sources() -> tuple[str, str, str, str, str, str, str, str, str]:
    """One non-const ``as``. Only the comment text changes.

    A justification needs the marker, a colon, and non-whitespace after the
    colon. ``no_colon`` is that marker plus trailing words and no colon.
    ``no_colon_fresh`` drops only the colon from the valid comment's words.
    ``glued`` puts a letter immediately after the colon.
    ``punctuation`` and ``punctuation_spaced`` put only a period after the
    colon: flush against it, or after one space. That period is not a letter.
    """
    statement = _fresh_as_line()
    reason = generated_justification()
    foreign = fresh_ident("note")
    good = _line_above(statement, f"// SAFETY: {reason}")
    non_marker = _line_above(statement, f"// {foreign}: {reason}")
    empty = _line_above(statement, "// SAFETY:")
    whitespace = _line_above(statement, "// SAFETY:   ")
    no_colon = _line_above(statement, "// SAFETY parsed before branding")
    no_colon_fresh = _line_above(statement, f"// SAFETY {reason}")
    glued = _line_above(statement, "// SAFETY:parsed")
    punctuation = _line_above(statement, "// SAFETY:.")
    punctuation_spaced = _line_above(statement, "// SAFETY: .")
    return (
        good,
        non_marker,
        empty,
        whitespace,
        no_colon,
        no_colon_fresh,
        glued,
        punctuation,
        punctuation_spaced,
    )


def omitted_marker_sources() -> tuple[str, str, str]:
    statement = _fresh_as_line()
    reason = generated_justification()
    foreign = fresh_ident("note")
    bare = statement + "\n"
    safety = _line_above(statement, f"// SAFETY: {reason}")
    other = _line_above(statement, f"// {foreign}: {reason}")
    return bare, safety, other


def alternative_marker_sources() -> tuple[list[str], str, str, str, str]:
    statement = _fresh_as_line()
    first = fresh_ident("mk").upper()
    second = fresh_ident("mk").upper()
    foreign = fresh_ident("mk").upper()
    reason = generated_justification()
    bare = statement + "\n"
    rejected = _line_above(statement, f"// {foreign}: {reason}")
    one = _line_above(statement, f"// {first}: {reason}")
    two = _line_above(statement, f"// {second}: {reason}")
    return [first, second], bare, rejected, one, two


def plus_marker_sources() -> tuple[str, str, str, str, str, str, str, str, str]:
    """One assertion. The configured marker is one string that contains a plus.

    ``whole`` uses that entire string as its own token, then a colon and
    nonempty text. ``left_only`` uses only the text before the plus.
    ``right_only`` uses only the text after the plus. ``glued`` is that
    entire string with one trailing letter and no break before the colon.
    ``safety`` is the default marker. ``decoy`` is a different string that
    also contains a plus. ``glued_default`` is the default marker with one
    trailing letter, for a run that omits the markers list.
    ``leading_default`` is a word, a space, and then that whole default
    marker, also for an omitted list. The marker is not required to be the
    first token. The match is not pinned to an expression.
    """
    statement = _fresh_as_line()
    left = fresh_ident("mk")
    right = fresh_ident("mk")
    marker = f"{left}+{right}"
    decoy = f"{fresh_ident('de')}+{fresh_ident('de')}"
    letter = secrets.choice("abcdefghjkmnpqrstuvwxyz")
    lead = fresh_ident("lead")
    reason = generated_justification()
    if (
        not left
        or not right
        or left == right
        or "+" in left
        or "+" in right
        or ":" in left
        or ":" in right
        or " " in left
        or " " in right
        or "SAFETY" in left
        or "SAFETY" in right
        or marker.count("+") != 1
        or marker != f"{left}+{right}"
        or "+" not in decoy
        or decoy.count("+") != 1
        or marker in decoy
        or decoy == marker
        or left in decoy
        or right in decoy
        or len(letter) != 1
        or not letter.isalpha()
        or not lead
        or lead == "SAFETY"
        or "SAFETY" in lead
        or "+" in lead
        or ":" in lead
        or " " in lead
        or not reason
        or "SAFETY" in reason
        or "+" in reason
        or ":" in reason
        or " " in reason
        or left in reason
        or right in reason
    ):
        raise AssertionError(
            "plus marker pieces must be distinct tokens around one plus; "
            f"marker={marker!r} decoy={decoy!r} letter={letter!r} "
            f"lead={lead!r} reason={reason!r}"
        )
    whole_comment = f"// {marker}: {reason}"
    safety_comment_line = f"// SAFETY: {reason}"
    decoy_comment = f"// {decoy}: {reason}"
    left_comment = f"// {left}: {reason}"
    right_comment = f"// {right}: {reason}"
    glued_comment = f"// {marker}{letter}: {reason}"
    glued_default_comment = f"// SAFETY{letter}: {reason}"
    leading_comment = f"// {lead} SAFETY: {reason}"
    comments = (
        ("whole", whole_comment),
        ("safety", safety_comment_line),
        ("decoy", decoy_comment),
        ("left", left_comment),
        ("right", right_comment),
        ("glued", glued_comment),
        ("glued-default", glued_default_comment),
        ("leading-default", leading_comment),
    )
    for label, comment in comments:
        if "\n" in comment or not comment.startswith("// "):
            raise AssertionError(
                f"{label} must be one line comment; got {comment!r}"
            )
    if marker not in whole_comment or f"{marker}:" not in whole_comment:
        raise AssertionError(
            f"the whole marker must stay intact; comment={whole_comment!r}"
        )
    if "+" in left_comment or marker in left_comment or right in left_comment:
        raise AssertionError(
            f"the left piece must not include the plus or the other piece; "
            f"got {left_comment!r}"
        )
    if "+" in right_comment or marker in right_comment or left in right_comment:
        raise AssertionError(
            f"the right piece must not include the plus or the other piece; "
            f"got {right_comment!r}"
        )
    if (
        f"{marker}{letter}:" not in glued_comment
        or f"{marker}:" in glued_comment
        or f"{marker} {letter}" in glued_comment
    ):
        raise AssertionError(
            "the trailing letter must be glued onto the whole plus marker; "
            f"got {glued_comment!r}"
        )
    if (
        f"SAFETY{letter}:" not in glued_default_comment
        or "SAFETY:" in glued_default_comment
        or f"SAFETY {letter}" in glued_default_comment
        or marker in glued_default_comment
    ):
        raise AssertionError(
            "the trailing letter must be glued onto the default marker; "
            f"got {glued_default_comment!r}"
        )
    if (
        f"{lead} SAFETY:" not in leading_comment
        or f"{lead}SAFETY" in leading_comment
        or marker in leading_comment
    ):
        raise AssertionError(
            "a word and a space must precede the whole default marker; "
            f"got {leading_comment!r}"
        )
    if marker in decoy_comment or "+" not in decoy_comment:
        raise AssertionError(
            f"the decoy must be a different plus-containing token; "
            f"got {decoy_comment!r}"
        )
    whole = _line_above(statement, whole_comment)
    safety = _line_above(statement, safety_comment_line)
    other_plus = _line_above(statement, decoy_comment)
    left_only = _line_above(statement, left_comment)
    right_only = _line_above(statement, right_comment)
    glued = _line_above(statement, glued_comment)
    glued_default = _line_above(statement, glued_default_comment)
    leading_default = _line_above(statement, leading_comment)
    for label, text in (
        ("whole", whole),
        ("safety", safety),
        ("decoy", other_plus),
        ("left", left_only),
        ("right", right_only),
        ("glued", glued),
        ("glued-default", glued_default),
        ("leading-default", leading_default),
    ):
        if not text.endswith(f"{statement}\n"):
            raise AssertionError(
                f"{label} must be that same assertion; got {text!r}"
            )
    return (
        marker,
        whole,
        safety,
        other_plus,
        left_only,
        right_only,
        glued,
        glued_default,
        leading_default,
    )


def const_only_chain_sources() -> tuple[str, str, str]:
    """Same object and the same SAFETY comment.

    ``mixed`` ends a parenthesized ``as const`` in a non-const assertion.
    ``const_only`` is that parenthesized ``as const`` followed by another
    ``as const``. ``plain`` is those two ``as const`` assertions with no
    parenthesis between them.
    """
    field = fresh_ident("slot")
    target = fresh_ident("Target")
    comment = safety_comment(text=generated_justification())
    literal = f"{{ {field}: 1 }}"
    mixed = f"{comment}\nvoid (({literal} as const) as {target});\n"
    const_only = f"{comment}\nvoid (({literal} as const) as const);\n"
    plain = f"{comment}\nvoid ({literal} as const as const);\n"
    return mixed, const_only, plain


def single_vs_chain_sources() -> tuple[str, str]:
    """Same receiver, target, and SAFETY comment. The chain adds one assertion."""
    receiver = fresh_ident("val")
    target = fresh_ident("Target")
    comment = safety_comment(text=generated_justification())
    single = f"{comment}\nvoid ({receiver} as {target});\n"
    chain = f"{comment}\nvoid ({receiver} as {target} as {target});\n"
    return single, chain


def empty_assignment_sources() -> tuple[str, str]:
    """One already-declared open-record binding. Only the assigned value changes."""
    header, command, starter, key, binding = command_parts(twin=True)
    declared = header + f"let {binding}: Record<string, {command}>;\n"
    concrete = declared + f"{binding} = {known_object(key, starter)};\n"
    empty = declared + f"{binding} = {{}};\n"
    return concrete, empty


def binding_keyword_alias_sources() -> tuple[str, str, str]:
    """One open-record target and one object literal. Only const, let, or var changes."""
    header, command, starter, key, binding = command_parts(twin=True)
    source = fresh_ident("src")
    obj = known_object(key, starter)
    destination = f"const {binding}: Record<string, {command}> = {source};\n"

    def arm(keyword: str) -> str:
        return header + f"{keyword} {source} = {obj};\n" + destination

    return arm("const"), arm("let"), arm("var")


def literal_keyword_alias_unknown_sources() -> tuple[tuple[str, str, str, str], ...]:
    """Same unknown annotation and the same literal. Only const, let, or var changes.

    One row stores ``1``. One row stores ``[1, 2]``. Each alias is read into
    an explicit ``unknown`` variable annotation and is not written again. The
    alias is not passed to a type predicate. The const arm is the known alias
    of that literal. The let and var arms are the unreassigned counterparts.
    """
    rows: list[tuple[str, str, str, str]] = []
    for label, literal in (("numeric", "1"), ("array", "[1, 2]")):
        source = fresh_ident("src")
        held = fresh_ident("held")
        if source == held or literal not in {"1", "[1, 2]"}:
            raise AssertionError(
                "a numeric or array literal alias needs two names and one of "
                f"those literals; source={source!r} held={held!r} literal={literal!r}"
            )
        destination = f"const {held}: unknown = {source};\n"

        def arm(keyword: str, *, _source: str = source, _literal: str = literal) -> str:
            return f"{keyword} {_source} = {_literal};\n{destination}"

        const_arm = arm("const")
        let_arm = arm("let")
        var_arm = arm("var")
        if const_arm.replace("const ", "let ", 1) != let_arm:
            raise AssertionError(
                f"{label} let arm must change only the alias keyword; "
                f"const={const_arm!r} let={let_arm!r}"
            )
        if const_arm.replace("const ", "var ", 1) != var_arm:
            raise AssertionError(
                f"{label} var arm must change only the alias keyword; "
                f"const={const_arm!r} var={var_arm!r}"
            )
        for keyword, text in (("const", const_arm), ("let", let_arm), ("var", var_arm)):
            if text.count(source) != 2 or f": unknown = {source};" not in text:
                raise AssertionError(
                    f"{label} {keyword} alias must be stored once under unknown; "
                    f"got {text!r}"
                )
            if text.count(f"{keyword} {source} = {literal};") != 1:
                raise AssertionError(
                    f"{label} {keyword} alias must be written once; got {text!r}"
                )
            if "Record<" in text or "(" in text or " is " in text or "function" in text:
                raise AssertionError(
                    f"{label} alias must not be an open record or a type-predicate "
                    f"argument; got {text!r}"
                )
        rows.append((label, const_arm, let_arm, var_arm))
    return tuple(rows)


def empty_dictionary_sources() -> tuple[str, str]:
    """Same type name and binding. Only the initializer changes."""
    header, command, starter, key, binding = command_parts(twin=True)
    concrete = (
        header
        + f"const {binding}: Record<string, {command}> = "
        + f"{known_object(key, starter)};\n"
    )
    empty = header + f"const {binding}: Record<string, {command}> = {{}};\n"
    return concrete, empty


def finite_key_sources() -> tuple[
    str, str, str, str, str, str, tuple[tuple[str, str], ...]
]:
    """One object, one binding, one value type. The key is the only fact.

    A written ``string`` key reports. A union of literal keys is silent.
    The same alias name is a finite union in one file and ``string`` in
    another, at program scope and inside one function. An alias of
    ``string`` is an open key. The finite-union alias is not.

    The same object and the same written union are also an assignment
    into an already-annotated binding, a return type, a class field, and
    a justified assertion. Those four are not variable annotations.
    """
    binding = fresh_ident("map")
    left = fresh_ident("one")
    right = fresh_ident("two")
    alias = fresh_ident("Key")
    fn = fresh_ident("wrap")
    obj = f"{{ {left}: 1, {right}: 2 }}"
    finite_body = f'"{left}" | "{right}"'
    open_record = f"const {binding}: Record<string, number> = {obj};\n"
    literal_keys = (
        f"const {binding}: Record<{finite_body}, number> = {obj};\n"
    )
    named_keys = (
        f"type {alias} = {finite_body};\n"
        f"const {binding}: Record<{alias}, number> = {obj};\n"
    )
    string_alias = (
        f"type {alias} = string;\n"
        f"const {binding}: Record<{alias}, number> = {obj};\n"
    )

    def block(body: str) -> str:
        return (
            f"function {fn}() {{\n"
            f"  type {alias} = {body};\n"
            f"  const {binding}: Record<{alias}, number> = {obj};\n"
            f"}}\n"
        )

    block_string = block("string")
    block_finite = block(finite_body)
    if "type " in open_record or "Record<string, number>" not in open_record:
        raise AssertionError(
            f"written string key must be the keyword, not an alias; "
            f"got {open_record!r}"
        )
    if "type " in literal_keys or finite_body not in literal_keys:
        raise AssertionError(
            f"literal-key union must be written in the record, not named; "
            f"got {literal_keys!r}"
        )
    for label, text, body in (
        ("finite-alias", named_keys, finite_body),
        ("string-alias", string_alias, "string"),
        ("block-string", block_string, "string"),
        ("block-finite", block_finite, finite_body),
    ):
        if (
            f"type {alias} = {body};" not in text
            or f"Record<{alias}, number>" not in text
            or "Record<string," in text
            or obj not in text
        ):
            raise AssertionError(
                f"{label} must use the alias as the record key; got {text!r}"
            )
    if "function " in string_alias or "function " in named_keys:
        raise AssertionError("program-scope key aliases must not be nested")
    if block_string.count("function ") != 1 or block_finite.count("function ") != 1:
        raise AssertionError("block-scoped key aliases need one function")
    if block_string.replace("string", finite_body, 1) != block_finite:
        raise AssertionError(
            "block arms may differ only in what the key alias resolves to; "
            f"string={block_string!r} finite={block_finite!r}"
        )
    if named_keys.replace(finite_body, "string", 1) != string_alias:
        raise AssertionError(
            "program-scope arms may differ only in what the key alias "
            f"resolves to; finite={named_keys!r} string={string_alias!r}"
        )
    vehicles = _finite_key_record_vehicles(binding, obj, finite_body)
    annotation_arms = {
        open_record,
        literal_keys,
        named_keys,
        string_alias,
        block_string,
        block_finite,
    }
    if any(source in annotation_arms for _label, source in vehicles):
        raise AssertionError(
            "finite-key assignment, return, field, and assertion must not "
            "collapse into a variable annotation"
        )
    return (
        open_record,
        literal_keys,
        named_keys,
        string_alias,
        block_string,
        block_finite,
        vehicles,
    )


def _finite_key_record_vehicles(
    binding: str, obj: str, finite_body: str
) -> tuple[tuple[str, str], ...]:
    """Same known object and the same union of literal keys, off a const annotation.

    The record key is that written union. It is not a single literal, an
    index signature, an alias of string, or an alias of unknown or any.
    """
    if "|" not in finite_body or '"' not in finite_body:
        raise AssertionError(
            f"finite-key vehicles need a union of literal keys; got {finite_body!r}"
        )
    record = f"Record<{finite_body}, number>"
    give = fresh_ident("give")
    owner = fresh_ident("Bag")
    assign = f"let {binding}: {record};\n{binding} = {obj};\n"
    returned = (
        f"function {give}(): {record} {{\n"
        f"  return {obj};\n"
        f"}}\n"
    )
    field = (
        f"class {owner} {{\n"
        f"  {binding}: {record} = {obj};\n"
        f"}}\n"
    )
    asserted = with_safety(f"const {binding} = {obj} as {record};\n")
    built = (
        ("assign", assign),
        ("return", returned),
        ("field", field),
        ("assert", asserted),
    )
    seen: set[str] = set()
    for label, source in built:
        if source in seen or obj not in source or record not in source:
            raise AssertionError(
                f"{label} must carry the same object and the same finite-key "
                f"record; got {source!r}"
            )
        if (
            "Record<string," in source
            or "type " in source
            or "[key:" in source
            or "unknown" in source
            or " any" in source
            or source.count("|") != 1
        ):
            raise AssertionError(
                f"{label} must be a written union of literal keys, not a "
                f"single key, an index signature, or an alias; got {source!r}"
            )
        seen.add(source)
    if not assign.startswith(f"let {binding}:") or "const " in assign:
        raise AssertionError(
            f"assignment must write into an already-annotated binding; got {assign!r}"
        )
    if f"function {give}(): {record}" not in returned or f"return {obj};" not in returned:
        raise AssertionError(
            f"return must use the finite-key record as the return type; got {returned!r}"
        )
    if not field.startswith(f"class {owner}") or f"{binding}: {record} = {obj};" not in field:
        raise AssertionError(
            f"class field must initialize the finite-key record; got {field!r}"
        )
    direct = f"{obj} as {record}"
    if not asserted.startswith("// ") or direct not in asserted or " as unknown" in asserted:
        raise AssertionError(
            "assertion must assert the object directly to the finite-key "
            f"record and carry a justification; got {asserted!r}"
        )
    return built


def satisfies_sources() -> tuple[str, str]:
    """One object literal and one binding. Annotation versus satisfies."""
    header, command, starter, key, binding = command_parts(twin=True)
    obj = known_object(key, starter)
    annotated = (
        header
        + f"const {binding}: Record<string, {command}> = {obj};\n"
    )
    satisfied = (
        header
        + f"const {binding} = {obj} satisfies Record<string, {command}>;\n"
    )
    return annotated, satisfied


def named_owner_sources(*, twin: bool = False) -> tuple[str, str, str]:
    """One object, binding, and key.

    The reporting annotation and the named-alias body are one object type.
    Readonly is not added on either side, or on the interface members.
    """
    header, command, starter, key, binding = command_parts(twin=twin)
    iface = "Commands" if not twin else fresh_ident("Table")
    alias = "Commands" if not twin else fresh_ident("Alias")
    obj = known_object(key, starter)
    members = f"{{ {key}: {command} }}"
    anonymous = header + f"const {binding}: {members} = {obj};\n"
    interface = (
        header
        + f"interface {iface} {{ {key}: {command} }}\n"
        + f"const {binding}: {iface} = {obj};\n"
    )
    named = (
        header
        + f"type {alias} = {members};\n"
        + f"const {binding}: {alias} = {obj};\n"
    )
    if (
        "readonly" in anonymous
        or "readonly" in interface
        or "readonly" in named
        or f"type {alias} = {members};" not in named
        or f": {members} = {obj};" not in anonymous
        or f"{{ {key}: {command} }}" not in interface
        or obj not in interface
        or obj not in named
    ):
        raise AssertionError(
            "the named alias body must be the same object type as the "
            "reporting inline annotation, and the interface must declare "
            f"those members; anonymous={anonymous!r} interface={interface!r} "
            f"alias={named!r}"
        )
    return anonymous, interface, named


def undefined_name_sources() -> tuple[str, str]:
    """Same binding and object. The annotation is the only difference."""
    header, command, starter, key, binding = command_parts(twin=True)
    missing = fresh_ident("Absent")
    obj = known_object(key, starter)
    record = (
        header
        + f"const {binding}: Record<string, {command}> = {obj};\n"
    )
    undefined = header + f"const {binding}: {missing} = {obj};\n"
    return record, undefined


def write_imported_annotation_pair(ws: Workspace) -> tuple[Path, Path]:
    """Same import, object, and binding. Annotation is Record versus the imported name."""
    header, command, starter, key, binding = command_parts(twin=True)
    mod = fresh_ident("types")
    exported = fresh_ident("Table")
    ws.write(
        f"{mod}.ts",
        f"export type {exported} = Record<string, () => void>;\n",
    )
    obj = known_object(key, starter)
    prefix = f'import {{ {exported} }} from "./{mod}";\n' + header
    record = prefix + f"const {binding}: Record<string, {command}> = {obj};\n"
    imported = prefix + f"const {binding}: {exported} = {obj};\n"
    return (
        write_f03_source(ws, record, prefix="imp-rec"),
        write_f03_source(ws, imported, prefix="imp-name"),
    )


def predicate_argument_sources() -> tuple[str, str, str]:
    """One local unknown type predicate. Both declarations stay; only the argument changes."""
    pred = fresh_ident("isIt")
    param = fresh_ident("arg")
    token = fresh_ident("token")
    held = fresh_ident("raw")
    reader = fresh_ident("load")
    header = (
        f"function {pred}({param}: unknown): {param} is string "
        f"{{ return true; }}\n"
        f"declare const {held}: unknown;\n"
        f"declare function {reader}(): unknown;\n"
    )
    literal = header + f'{pred}("{token}");\n'
    declared = header + f"{pred}({held});\n"
    called = header + f"{pred}({reader}());\n"
    return literal, declared, called


def let_predicate_sources() -> tuple[str, str, str]:
    """Same predicate and the same string literal.

    The direct call reports. An unreassigned let alias of that literal, and
    an unreassigned var alias of that same literal, each passed to that
    predicate, stay silent. Neither alias is annotated. The literal is a
    string, not a numeric, array, or object literal.
    """
    pred = fresh_ident("isIt")
    param = fresh_ident("arg")
    alias = fresh_ident("held")
    token = fresh_ident("token")
    header = (
        f"function {pred}({param}: unknown): {param} is string "
        f"{{ return true; }}\n"
    )
    direct = header + f'{pred}("{token}");\n'
    let_decl = f'let {alias} = "{token}";'
    var_decl = f'var {alias} = "{token}";'
    let_arm = header + f"{let_decl}\n{pred}({alias});\n"
    var_arm = header + f"{var_decl}\n{pred}({alias});\n"
    if let_decl not in let_arm or var_decl not in var_arm:
        raise AssertionError(
            "let and var predicate arms must alias the same string literal"
        )
    if f"let {alias}:" in let_arm or f"var {alias}:" in var_arm:
        raise AssertionError(
            "the unreassigned alias must not carry a type annotation"
        )
    if any(snippet in var_arm for snippet in (" = 1;", " = [];", " = {")):
        raise AssertionError(
            "the var predicate arm must not pass a numeric, array, or object literal"
        )
    return direct, let_arm, var_arm


def annotation_only_sources() -> tuple[tuple[str, str, str], ...]:
    """Per vehicle: const-alias report, then the same vehicle with annotation-only evidence.

    The later assignment writes into an already-declared open-dictionary binding.
    The assertion pair keeps one justification comment on both arms.
    """
    rows: list[tuple[str, str, str]] = []
    for label in ("variable", "assign", "return", "field", "assert"):
        header, command, starter, key, binding = command_parts(twin=True)
        source = fresh_ident("src")
        callee = fresh_ident("load")
        open_record = f"Record<string, {command}>"
        precise = f"{{ {key}: {command} }}"
        scaffold = header + f"function {callee}() {{ return; }}\n"
        report_evidence = f"const {source} = {known_object(key, starter)};\n"
        silent_evidence = f"const {source}: {precise} = {callee}();\n"
        if label == "variable":
            vehicle = f"const {binding}: {open_record} = {source};\n"
        elif label == "assign":
            vehicle = f"let {binding}: {open_record};\n{binding} = {source};\n"
        elif label == "return":
            fn = fresh_ident("make")
            vehicle = (
                f"function {fn}(): {open_record} {{\n"
                f"  return {source};\n"
                f"}}\n"
            )
        elif label == "field":
            cls = fresh_ident("Bag")
            vehicle = (
                f"class {cls} {{\n"
                f"  {binding}: {open_record} = {source};\n"
                f"}}\n"
            )
        else:
            comment = safety_comment(text=generated_justification())
            vehicle = f"{comment}\nconst {binding} = {source} as {open_record};\n"
        rows.append(
            (
                label,
                scaffold + report_evidence + vehicle,
                scaffold + silent_evidence + vehicle,
            )
        )
    return tuple(rows)


def record_any_store_sources() -> tuple[str, str]:
    """Known object stored under ``Record<string, any>``. The later assertion is the added fact.

    Both arms share names, the store annotation, and one justification comment
    on the store, so that comment is not itself a later assertion. The first
    arm asserts that same const binding to an object type with a named field
    and repeats the justification immediately above the assertion. The second
    arm is that store with no later assertion. The annotation is still an open
    string-key record, so a widening report may appear on either arm.
    """
    source = fresh_ident("src")
    wide = fresh_ident("wide")
    parsed = fresh_ident("got")
    field = fresh_ident("slot")
    comment = safety_comment(text=generated_justification())
    narrower = f"{{ readonly {field}: string }}"
    store = (
        f'const {source} = {{ {field}: "second" }};\n'
        f"{comment}\n"
        f"const {wide}: Record<string, any> = {source};\n"
    )
    with_later = store + f"{comment}\nconst {parsed} = {wide} as {narrower};\n"
    if "Record<string, any>" not in store or "Record<string, unknown>" in store:
        raise AssertionError(
            "record-any store must be the written Record<string, any> annotation; "
            f"got {store!r}"
        )
    if f"as {narrower}" not in with_later or " as " in store:
        raise AssertionError(
            "only the later arm may assert the stored binding; "
            f"later={with_later!r} store={store!r}"
        )
    return with_later, store


def named_value_record_then_assert_sources() -> tuple[tuple[str, str], ...]:
    """Known object stored as an open record of a named value type, then asserted.

    The value type argument is a same-file named type, not ``unknown`` or
    ``any``. Both rows assert that same const binding to an object type with
    a named field, and a justification sits immediately above that assertion.
    The first row uses the public name ``Command``; the second uses a fresh
    name. The store is still the open-record widening. Neither row is a
    broad-record store.
    """
    rows: list[tuple[str, str]] = []
    for label, twin in (("command", False), ("fresh", True)):
        header, command, _starter, _key, _binding = command_parts(twin=twin)
        source = "source" if not twin else fresh_ident("src")
        wide = "widened" if not twin else fresh_ident("wide")
        parsed = "parsed" if not twin else fresh_ident("got")
        field = "id" if not twin else fresh_ident("slot")
        fn = "load" if not twin else fresh_ident("load")
        narrower = f"{{ readonly {field}: string }}"
        annotation = f"Record<string, {command}>"
        store_and_assert = (
            f'const {source} = {{ {field}: "second" }};\n'
            f"const {wide}: {annotation} = {source};\n"
            + with_safety(f"const {parsed} = {wide} as {narrower};\n")
        )
        if annotation not in store_and_assert:
            raise AssertionError(
                "named-value record store must write the open record of that "
                f"named type; got {store_and_assert!r}"
            )
        if (
            "Record<string, unknown>" in store_and_assert
            or "Record<string, any>" in store_and_assert
        ):
            raise AssertionError(
                "named-value record store must not be a broad record; "
                f"got {store_and_assert!r}"
            )
        if f"{wide} as {narrower}" not in store_and_assert:
            raise AssertionError(
                "the later assertion must narrow that same const binding; "
                f"got {store_and_assert!r}"
            )
        indented = "".join(f"  {line}\n" for line in store_and_assert.splitlines())
        rows.append(
            (label, header + f"function {fn}() {{\n{indented}  return {parsed};\n}}\n")
        )
    return tuple(rows)


def later_assertion_sources() -> tuple[tuple[str, str, str], ...]:
    """Each store keeps one set of names. The later assertion is the added fact.

    The same justification comment sits on the store in both arms, so it is
    not itself a later assertion of that binding. The assertion arm repeats it
    immediately above the assertion. ``any`` asserts to a named object type so
    the assertion itself is not a widening target. The other stores assert to
    an inline object type, which is what makes the later assertion narrower
    than ``object`` or a broad record.
    """
    rows: list[tuple[str, str, str]] = []
    for label, annotation in (
        ("unknown", "unknown"),
        ("any", "any"),
        ("object", "object"),
        ("record", "Record<string, unknown>"),
    ):
        source = fresh_ident("src")
        wide = fresh_ident("wide")
        parsed = fresh_ident("got")
        field = fresh_ident("slot")
        comment = safety_comment(text=generated_justification())
        header = ""
        if label == "any":
            named = fresh_ident("Parsed")
            header = f"type {named} = {{ readonly {field}: string }};\n"
            asserted = named
        else:
            asserted = f"{{ readonly {field}: string }}"
        # The same comment text is on the store, which is not a later assertion
        # of that binding. The assertion arm repeats it immediately above the
        # assertion so a missing justification is not the failure.
        store = (
            f"{header}"
            f'const {source} = {{ {field}: "second" }};\n'
            f"{comment}\n"
            f"const {wide}: {annotation} = {source};\n"
        )
        with_later = store + f"{comment}\nconst {parsed} = {wide} as {asserted};\n"
        rows.append((label, with_later, store))
    return tuple(rows)


def provenance_sources() -> tuple[str, str]:
    """Same binding and narrower type. Provenance of that binding is the difference."""
    source = fresh_ident("src")
    held = fresh_ident("held")
    parsed = fresh_ident("got")
    field = fresh_ident("slot")
    narrow = f"{{ readonly {field}: string }}"
    comment = safety_comment(text=generated_justification())
    assertion = f"{comment}\nconst {parsed} = {held} as {narrow};\n"
    assigned = (
        f'const {source} = {{ {field}: "second" }};\n'
        f"const {held}: unknown = {source};\n"
        + assertion
    )
    declared = f"declare const {held}: unknown;\n" + assertion
    return assigned, declared


def asserted_binding_sources() -> tuple[str, str]:
    """Both bindings stay. Only which binding is asserted changes."""
    source = fresh_ident("src")
    wide = fresh_ident("wide")
    other = fresh_ident("other")
    parsed = fresh_ident("got")
    field = fresh_ident("slot")
    narrow = f"{{ readonly {field}: string }}"
    comment = safety_comment(text=generated_justification())
    prefix = (
        f'const {source} = {{ {field}: "second" }};\n'
        f"const {wide}: unknown = {source};\n"
        f"declare const {other}: unknown;\n"
    )
    assert_wide = prefix + f"{comment}\nconst {parsed} = {wide} as {narrow};\n"
    assert_other = prefix + f"{comment}\nconst {parsed} = {other} as {narrow};\n"
    return assert_wide, assert_other


def forward_alias_sources() -> tuple[str, str, str]:
    """Use of a non-generic alias, then its declaration, for the three widening targets."""
    unknown_alias = fresh_ident("Later")
    unknown_binding = fresh_ident("held")
    unknown = (
        f"const {unknown_binding}: {unknown_alias} = 1;\n"
        f"type {unknown_alias} = unknown;\n"
    )
    object_alias = fresh_ident("Later")
    object_binding = fresh_ident("held")
    object_arm = (
        f"const {object_binding}: {object_alias} = [];\n"
        f"type {object_alias} = object;\n"
    )
    header, command, starter, key, binding = command_parts(twin=True)
    open_alias = fresh_ident("Later")
    open_record = (
        header
        + f"const {binding}: {open_alias} = {known_object(key, starter)};\n"
        + f"type {open_alias} = Record<string, {command}>;\n"
    )
    return unknown, object_arm, open_record
