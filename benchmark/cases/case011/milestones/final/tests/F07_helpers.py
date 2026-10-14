# feature: F07
"""Observation helpers for the finite built-in function set (FP-07).

New names only. Sealed F02–F06 helpers are imported, not copied.
A predecessor that is not sealed on this walk is not imported.
A helper that cannot classify its input raises; it never returns
``None``, ``False``, ``[]``, or ``0`` to mean "no function result".
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Any

from _harness import HarnessError
from F03_helpers import (
    bracket_ident,
    bracket_payload,
)

# Public-oracle tokens this slice must not reuse as process-local names.
_BUILTIN_NAMES = frozenset(
    {
        "abs",
        "avg",
        "ceil",
        "contains",
        "ends_with",
        "floor",
        "join",
        "keys",
        "length",
        "map",
        "max",
        "max_by",
        "merge",
        "min",
        "min_by",
        "not_null",
        "reverse",
        "sort",
        "sort_by",
        "starts_with",
        "sum",
        "to_array",
        "to_number",
        "to_string",
        "type",
        "values",
    }
)
_PUBLIC_IDENTS = frozenset(
    {
        "foo",
        "zero",
        "numbers",
        "array",
        "strings",
        "decimals",
        "str",
        "false",
        "empty_list",
        "empty_hash",
        "objects",
        "null_key",
        "people",
        "empty",
        "age",
        "order",
        "name",
        "extra",
        "bool",
        "a",
        "b",
        "c",
        "badkey",
        "unknown_function",
        "unknown_key",
        "all",
        "expressions",
        "are_null",
    }
) | _BUILTIN_NAMES
_PUBLIC_PAYLOADS = frozenset(
    {
        "bar",
        "baz",
        "Str",
        "a",
        "b",
        "c",
        "z",
        "yes1",
        "yes2",
        "hello world",
        "abc",
        "notanumber",
        "1e21",
        "dlrow olleh",
        "foo",
        "SStr",
        "String",
        "true",
        "null",
        "boolean",
        "number",
        "string",
        "object",
        "array",
    }
)
_PUBLIC_NUMBERS = frozenset(
    {
        -24,
        -1.5,
        -1,
        0,
        1,
        1.01,
        1.1,
        1.2,
        2,
        2.75,
        3,
        4,
        5,
        10,
        11,
        20,
        24,
        30,
        40,
        50,
        100,
        111,
    }
)


def fn_ident() -> str:
    """Process-local identifier that is not a published function-oracle token."""
    token = bracket_ident()
    if token in _PUBLIC_IDENTS:
        raise HarnessError(f"fn_ident collided with a reserved token: {token}")
    if token in _BUILTIN_NAMES:
        raise HarnessError(f"fn_ident reused a built-in name: {token}")
    print(f"fn_ident={token!r}", flush=True)
    return token


def fn_payload() -> str:
    """Process-local string payload that is not a published function-oracle token."""
    token = bracket_payload()
    if token in _PUBLIC_PAYLOADS:
        raise HarnessError(f"fn_payload collided with a reserved payload: {token}")
    print(f"fn_payload={token!r}", flush=True)
    return token


def fn_int(*, negative: bool = False, positive: bool = False) -> int:
    """Process-local integer that is not a published function-oracle number.

    ``positive=True`` requires ``n > 0``. ``negative=True`` requires ``n < 0``.
    Both flags together, or a generated value that misses the requested
    sign, is unclassifiable and raises — never a public ``-1`` / ``0`` /
    ``1`` fallback.
    """
    if negative and positive:
        raise HarnessError("fn_int cannot require both negative and positive")
    for _ in range(48):
        magnitude = 13 + (int(uuid.uuid4().hex[:4], 16) % 200)
        n = -magnitude if negative else magnitude
        if type(n) is not int:
            raise HarnessError(f"fn_int produced a non-int: {n!r}")
        if n in _PUBLIC_NUMBERS:
            continue
        if positive and n <= 0:
            raise HarnessError(f"fn_int(positive=True) produced non-positive {n!r}")
        if negative and n >= 0:
            raise HarnessError(f"fn_int(negative=True) produced non-negative {n!r}")
        print(f"fn_int={n}", flush=True)
        return n
    raise HarnessError(
        f"fn_int could not pick an int outside {_PUBLIC_NUMBERS!r}"
    )


def fn_float(*, in_open_neg_unit: bool = False) -> float:
    """Process-local non-integer float that is not a published oracle number.

    With ``in_open_neg_unit=True`` the value is in ``(-1, 0)``. A value
    that is an integer, outside that interval, or equal to a public
    sample raises — never a substitute where ``trunc`` equals ``floor``.
    """
    if in_open_neg_unit:
        for _ in range(48):
            numer = 1 + (int(uuid.uuid4().hex[:4], 16) % 1000)
            value = -float(numer) / 1001.0
            if type(value) is not float:
                raise HarnessError(f"fn_float produced a non-float: {value!r}")
            if value in _PUBLIC_NUMBERS:
                continue
            if not (-1.0 < value < 0.0):
                raise HarnessError(
                    f"fn_float(in_open_neg_unit=True) not in (-1, 0): {value!r}"
                )
            if value == int(value):
                raise HarnessError(
                    f"fn_float(in_open_neg_unit=True) is an integer: {value!r}"
                )
            if math.floor(value) == math.trunc(value):
                raise HarnessError(
                    f"fn_float(in_open_neg_unit=True) has floor==trunc: {value!r}"
                )
            print(f"fn_float_open_neg_unit={value!r}", flush=True)
            return value
        raise HarnessError("fn_float could not pick a value in (-1, 0)")
    for _ in range(48):
        whole = 13 + (int(uuid.uuid4().hex[:4], 16) % 200)
        frac = (1 + (int(uuid.uuid4().hex[:4], 16) % 900)) / 1000.0
        value = float(whole) + float(frac)
        if type(value) is not float:
            raise HarnessError(f"fn_float produced a non-float: {value!r}")
        if value in _PUBLIC_NUMBERS:
            continue
        if value == int(value):
            raise HarnessError(f"fn_float produced an integer-valued float: {value!r}")
        print(f"fn_float={value!r}", flush=True)
        return value
    raise HarnessError(
        f"fn_float could not pick a non-integer float outside {_PUBLIC_NUMBERS!r}"
    )


def fn_ordered_strings() -> tuple[str, str]:
    """Two distinct process-local strings ordered by the host ``<``.

    Returns ``(lesser, greater)``. Equal strings, a public token, or a
    pair the host cannot order raise.
    """
    left = fn_payload()
    right = fn_payload()
    if left in _PUBLIC_PAYLOADS or right in _PUBLIC_PAYLOADS:
        raise HarnessError(
            f"fn_ordered_strings reused a public token: {left!r}/{right!r}"
        )
    if left == right:
        raise HarnessError(f"fn_ordered_strings produced equal strings: {left!r}")
    if left < right:
        print(
            f"fn_ordered_strings lesser={left!r} greater={right!r}",
            flush=True,
        )
        return left, right
    if right < left:
        print(
            f"fn_ordered_strings lesser={right!r} greater={left!r}",
            flush=True,
        )
        return right, left
    raise HarnessError(
        f"fn_ordered_strings cannot classify {left!r} vs {right!r} under host <"
    )


def fn_ordered_floats() -> tuple[float, float]:
    """Two distinct process-local floats ordered by the host ``<``.

    Returns ``(lesser, greater)``. A public sample, equal floats, or a
    pair the host cannot order raise.
    """
    left = fn_float()
    right = fn_float()
    if left == right:
        raise HarnessError(f"fn_ordered_floats produced equal floats: {left!r}")
    if left < right:
        print(
            f"fn_ordered_floats lesser={left!r} greater={right!r}",
            flush=True,
        )
        return left, right
    if right < left:
        print(
            f"fn_ordered_floats lesser={right!r} greater={left!r}",
            flush=True,
        )
        return right, left
    raise HarnessError(
        f"fn_ordered_floats cannot classify {left!r} vs {right!r} under host <"
    )


def compact_json_text(value: Any) -> str:
    """Host compact JSON text: ``json.dumps(..., separators=(',', ':'))``.

    Encoding failure raises. An empty string is unclassifiable — never
    returned as a stand-in for "could not encode".
    """
    try:
        text = json.dumps(value, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise HarnessError(f"cannot compact-JSON-encode {value!r}: {exc}") from exc
    if not isinstance(text, str) or text == "":
        raise HarnessError(
            f"compact JSON of {value!r} is not a non-empty string: {text!r}"
        )
    print(f"compact_json_text={text!r}", flush=True)
    return text


def host_ordinary_text(value: Any) -> str:
    """Host ordinary text conversion: ``str(value)``.

    A result that is not a non-empty ``str`` raises.
    """
    try:
        text = str(value)
    except Exception as exc:
        raise HarnessError(f"host str() failed for {value!r}: {exc}") from exc
    if not isinstance(text, str) or text == "":
        raise HarnessError(
            f"host ordinary text of {value!r} is not a non-empty str: {text!r}"
        )
    print(f"host_ordinary_text={text!r}", flush=True)
    return text


def host_non_json_value(payload: str) -> Any:
    """A host object that is not a JSON type; ``str`` yields *payload*.

    *payload* must be a non-empty process-local string. ``Decimal`` is
    refused: L26 treats host decimals as numbers.
    """
    if not isinstance(payload, str) or payload == "":
        raise HarnessError(
            f"host_non_json_value requires a non-empty str payload, got {payload!r}"
        )
    if payload in _PUBLIC_PAYLOADS:
        raise HarnessError(
            f"host_non_json_value reused a public payload: {payload!r}"
        )

    class _HostCurrent:
        def __str__(self) -> str:
            return payload

        def __repr__(self) -> str:
            return f"HostCurrent({payload!r})"

    obj = _HostCurrent()
    print(f"host_non_json_value payload={payload!r}", flush=True)
    return obj


def function_kind_texts(*tokens: str) -> tuple[str, ...]:
    """Collect expression texts and function-name identifiers to strip.

    Names are covariates: leftover comparison must drop them or three
    failures look distinct only because the identifiers differ. Empty
    tokens raise rather than being silently dropped.
    """
    collected: list[str] = []
    for token in tokens:
        if not isinstance(token, str):
            raise HarnessError(
                f"function_kind_texts tokens must be str, got {type(token)!r}"
            )
        if token == "":
            raise HarnessError("function_kind_texts refuses an empty token")
        collected.append(token)
    if len(collected) < 2:
        raise HarnessError(
            "function_kind_texts needs at least an expression and a function name"
        )
    print(f"function_kind_texts n={len(collected)}", flush=True)
    return tuple(collected)


def _require_value_error_failure(exc: BaseException, *, label: str) -> BaseException:
    """Require *exc* is a captured kind of value error; never a sentinel."""
    if not isinstance(exc, BaseException):
        raise HarnessError(
            f"{label} must be a captured failure, got {type(exc)!r}"
        )
    if not isinstance(exc, ValueError):
        raise HarnessError(
            f"{label} must be a kind of value error, got "
            f"{type(exc).__name__}: {exc!r}"
        )
    return exc


def function_kind_marker(exc: BaseException) -> type:
    """Caller-visible kind marker of a captured function-call value error.

    The marker is the type object of the captured exception. It does
    not vary with the expression text, the function name, or leftover
    report wording. Does not name a product exception class, a fixed
    phrase, or leftover identity after stripping.
    """
    _require_value_error_failure(exc, label="function_kind_marker")
    marker = type(exc)
    print(f"function_kind_marker={marker.__name__}", flush=True)
    return marker


def _other_kind_representatives(canonical: BaseException) -> list[BaseException]:
    """Refusals of the Contract's other kinds, observed on the one-shot entry.

    Probes one refusal of every failure kind (empty, incomplete,
    grammar-level and token-level syntax, zero slice step, unknown
    function, invalid arity, invalid type). A probe that does not refuse
    is skipped (other tests grade that). A function-call probe related
    to *canonical* by subclassing (either way) is the canonical kind and
    is dropped; the FP-01 and zero-step probes are always other kinds.
    """
    from F03_helpers import oneshot_bracket_search

    unknown_name = "zz" + uuid.uuid4().hex[:12]
    probes = (
        ("", False),
        ("(", False),
        ("foo.", False),
        ("=", False),
        ("foo[::0]", False),
        (f"{unknown_name}(`1`)", True),
        ("abs()", True),
        ("abs('x')", True),
    )
    others: list[BaseException] = []
    for text, function_call in probes:
        result = oneshot_bracket_search(text, {"foo": [1, 2]})
        exc = result.exception
        if exc is None or not isinstance(exc, ValueError):
            continue
        if function_call and (
            isinstance(exc, type(canonical)) or isinstance(canonical, type(exc))
        ):
            continue
        others.append(exc)
    return others


def function_kind_class(canonical: BaseException) -> type:
    """The Contract refusal-kind class presented by *canonical*.

    The Contract gives each function-call kind its own type; a refusal
    of that kind is an instance of it (its exact type may be a subclass),
    and no refusal of any other kind is an instance of it. This returns
    the most general class on *canonical*'s type hierarchy that is a
    kind of value error and of which no refusal of another kind is an
    instance — i.e. the kind class, not the canonical example's exact
    type. Does not name a product class.
    """
    _require_value_error_failure(canonical, label="canonical")
    others = _other_kind_representatives(canonical)
    kind = type(canonical)
    for candidate in type(canonical).__mro__:
        if not (isinstance(candidate, type) and issubclass(candidate, ValueError)):
            break
        if candidate is ValueError:
            break
        if any(isinstance(other, candidate) for other in others):
            break
        kind = candidate
    print(
        f"function_kind_class canonical={type(canonical).__name__} kind={kind.__name__}",
        flush=True,
    )
    return kind


def assert_shares_function_kind(
    observed: BaseException, canonical: BaseException
) -> None:
    """*observed* presents the same Contract refusal kind as *canonical*.

    The kind is the Contract's kind class (``function_kind_class``): a
    refusal of the kind is an instance of that class or of a subclass,
    so neither *observed* nor *canonical* needs a particular exact type.
    """
    _require_value_error_failure(observed, label="observed")
    _require_value_error_failure(canonical, label="canonical")
    kind = function_kind_class(canonical)
    print(
        "shares_function_kind "
        f"observed={type(observed).__name__} kind={kind.__name__}",
        flush=True,
    )
    assert isinstance(observed, kind), (
        "observed failure must present the refusal kind of the canonical "
        "call (an instance of that kind's class or a subclass); "
        f"got {type(observed).__name__}, kind class is {kind.__name__}"
    )

def assert_does_not_use_function_kind(
    observed: BaseException, canonical: BaseException
) -> None:
    """*observed* does not present *canonical*'s kind marker.

    Does not treat leftover inequality as proof, and does not use
    'instance of a parent syntax type' as a substitute for not using
    this kind.
    """
    _require_value_error_failure(observed, label="observed")
    _require_value_error_failure(canonical, label="canonical")
    marker = function_kind_marker(canonical)
    print(
        "does_not_use_function_kind "
        f"observed={type(observed).__name__} canonical={marker.__name__}",
        flush=True,
    )
    assert not isinstance(observed, marker), (
        "observed failure must not present the canonical kind marker; "
        f"got {type(observed).__name__}, canonical kind is {marker.__name__}"
    )


def assert_function_kind_markers_differ(
    left: BaseException, right: BaseException
) -> None:
    """Two failures are different kinds: their kind markers differ.

    Markers differ when the type objects differ. Does not require
    leftover report text to differ. Does not use 'instance of a parent
    syntax type' as same-kind: a more specific form of one kind may
    still be an instance of another type in a given implementation.
    """
    left_marker = function_kind_marker(left)
    right_marker = function_kind_marker(right)
    print(
        "function_kind_markers_differ "
        f"left={left_marker.__name__} right={right_marker.__name__}",
        flush=True,
    )
    assert left_marker is not right_marker, (
        "function-call kind markers must differ; both are "
        f"{left_marker.__name__}"
    )


def assert_three_function_kind_markers_distinct(
    unknown: BaseException,
    arity: BaseException,
    typed: BaseException,
) -> None:
    """Unknown-function, invalid-arity, and invalid-type markers differ.

    Pairwise, the kind markers differ and neither failure presents the
    other's marker. A more specific form of one kind still counts as
    that kind, so exact type identity among same-kind examples is not
    required here. Does not grade leftover identity after stripping.
    """
    assert_function_kind_markers_differ(unknown, arity)
    assert_function_kind_markers_differ(unknown, typed)
    assert_function_kind_markers_differ(arity, typed)
    assert_does_not_use_function_kind(unknown, arity)
    assert_does_not_use_function_kind(unknown, typed)
    assert_does_not_use_function_kind(arity, unknown)
    assert_does_not_use_function_kind(arity, typed)
    assert_does_not_use_function_kind(typed, unknown)
    assert_does_not_use_function_kind(typed, arity)


def assert_function_kind_distinct_from_fp01(
    observed: BaseException,
    empty: BaseException,
    incomplete: BaseException,
    syntax: BaseException,
) -> None:
    """A function-call kind is distinct from the three FP-01 kinds.

    *observed* does not use the empty-expression marker of *empty* or
    the incomplete-expression marker of *incomplete*. Its kind marker
    differs from the syntax kind of *syntax* (``foo.``). Does not use
    'instance of foo.'s syntax type' as a substitute for not-invalid-arity:
    invalid-arity may be a more specific form of that type.
    """
    _require_value_error_failure(observed, label="observed")
    _require_value_error_failure(empty, label="empty")
    _require_value_error_failure(incomplete, label="incomplete")
    _require_value_error_failure(syntax, label="syntax")
    assert_does_not_use_function_kind(observed, empty)
    assert_does_not_use_function_kind(observed, incomplete)
    assert_function_kind_markers_differ(observed, syntax)


def assert_quoted_name_is_syntax_not_empty_incomplete_or_function_kind(
    observed: BaseException,
    empty: BaseException,
    incomplete: BaseException,
    syntax: BaseException,
    unknown: BaseException,
    arity: BaseException,
    typed: BaseException,
) -> None:
    """L332 carrier for a quoted identifier used as a function name.

    *observed* is already a kind of value error. It does not use the
    empty-expression kind of *empty* or the incomplete-expression kind
    of *incomplete*. A caller who already handles the syntax kind of
    *syntax* (``foo.`` on the same entry) also handles *observed*,
    including a more specific syntax form. It does not use the
    unknown-function, invalid-arity, or invalid-type kind markers.
    Does not compare leftover report text, does not require identical
    kind markers with ``foo.``, and does not name a product exception
    class or a fixed phrase.
    """
    _require_value_error_failure(observed, label="observed")
    _require_value_error_failure(empty, label="empty")
    _require_value_error_failure(incomplete, label="incomplete")
    _require_value_error_failure(syntax, label="syntax")
    _require_value_error_failure(unknown, label="unknown")
    _require_value_error_failure(arity, label="arity")
    _require_value_error_failure(typed, label="typed")
    empty_kind = type(empty)
    incomplete_kind = type(incomplete)
    syntax_kind = type(syntax)
    print(
        "quoted_name_carrier "
        f"observed={type(observed).__name__} "
        f"empty={empty_kind.__name__} "
        f"incomplete={incomplete_kind.__name__} "
        f"syntax={syntax_kind.__name__}",
        flush=True,
    )
    assert not isinstance(observed, empty_kind), (
        "quoted function name must not use the empty-expression kind "
        f"marker of a zero-length expression; got {type(observed).__name__}"
    )
    assert not isinstance(observed, incomplete_kind), (
        "quoted function name must not use the incomplete-expression "
        f"kind marker of unmatched '('; got {type(observed).__name__}"
    )
    assert isinstance(observed, syntax_kind), (
        "a caller who already handles the syntax kind of 'foo.' must "
        "also handle the quoted-name refusal, including a more specific "
        f"syntax form; got {type(observed).__name__}, "
        f"syntax kind is {syntax_kind.__name__}"
    )
    assert_does_not_use_function_kind(observed, unknown)
    assert_does_not_use_function_kind(observed, arity)
    assert_does_not_use_function_kind(observed, typed)


def require_document_field_unchanged(document: Any, key: str, before: Any) -> Any:
    """Require ``document[key] == before`` after a search (no write-back).

    A missing key, a non-mapping document, or an unreadable field raises
    — never treated as "unchanged". *before* must be a snapshot, not the
    live field object.
    """
    if not isinstance(key, str) or key == "":
        raise HarnessError(
            f"require_document_field_unchanged key must be a non-empty str, "
            f"got {key!r}"
        )
    if not isinstance(document, dict):
        raise HarnessError(
            f"require_document_field_unchanged requires a mapping document, "
            f"got {type(document)!r}"
        )
    try:
        present = key in document
    except Exception as exc:
        raise HarnessError(
            f"cannot probe document key {key!r}: {exc}"
        ) from exc
    if not present:
        raise HarnessError(
            f"document is missing key {key!r}; cannot observe write-back"
        )
    try:
        after = document[key]
    except Exception as exc:
        raise HarnessError(f"cannot read document[{key!r}]: {exc}") from exc
    print(
        f"document_field key={key!r} before={before!r} after={after!r}",
        flush=True,
    )
    assert after == before, (
        f"document[{key!r}] was rewritten: {after!r} vs snapshot {before!r}"
    )
    return after


__all__ = (
    "assert_does_not_use_function_kind",
    "assert_function_kind_distinct_from_fp01",
    "assert_function_kind_markers_differ",
    "assert_quoted_name_is_syntax_not_empty_incomplete_or_function_kind",
    "assert_shares_function_kind",
    "assert_three_function_kind_markers_distinct",
    "compact_json_text",
    "fn_float",
    "fn_ident",
    "fn_int",
    "fn_ordered_floats",
    "fn_ordered_strings",
    "fn_payload",
    "function_kind_marker",
    "function_kind_texts",
    "host_non_json_value",
    "host_ordinary_text",
    "require_document_field_unchanged",
)
