# feature: F03
"""Observation helpers for index, slice, and one-level flatten (FP-03).

New names only. Observation of the two public entries lives here under
F03 names; a predecessor that is not sealed on this walk is not
imported. A helper that cannot classify its input raises; it never
returns ``[]`` or ``None`` to mean "could not slice" or "flatten failed".
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from _harness import (
    CallResult,
    HarnessError,
    call,
    call_method,
    require_value,
    require_value_error,
)

# Public-oracle tokens this slice must not reuse as process-local names.
_RESERVED = frozenset(
    {
        "foo",
        "bar",
        "baz",
        "a",
        "b",
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "x",
        "notbar",
        "type",
        "object",
        "other",
        "correct",
        "missing",
        "found",
        "bad",
    }
)

# Public search callable on a successful compile result (FP-01 entries).
_BRACKET_SEARCH_ATTR = "search"


def _bracket_search_entry() -> Callable[..., Any]:
    """Return the public one-shot search callable from the package root."""
    from pathsel import search

    if not callable(search):
        raise HarnessError("search entry is not callable")
    return search


def _bracket_compile_entry() -> Callable[..., Any]:
    """Return the public compile callable from the package root."""
    from pathsel import compile as compile_entry

    if not callable(compile_entry):
        raise HarnessError("compile entry is not callable")
    return compile_entry


def oneshot_bracket_search(expression: str, document: Any) -> CallResult:
    """Search *expression* against *document* through the one-shot entry."""
    if not isinstance(expression, str):
        raise HarnessError(
            f"oneshot_bracket_search requires str expression, got {type(expression)!r}"
        )
    print(f"oneshot expression={expression!r}", flush=True)
    return call(_bracket_search_entry(), expression, document)


def compile_bracket_expression(expression: str) -> CallResult:
    """Compile *expression* through the compile entry."""
    if not isinstance(expression, str):
        raise HarnessError(
            f"compile_bracket_expression requires str expression, got {type(expression)!r}"
        )
    print(f"compile expression={expression!r}", flush=True)
    return call(_bracket_compile_entry(), expression)


def search_compiled_bracket(parsed: Any, document: Any) -> CallResult:
    """Search a compiled expression against *document* (no new compile)."""
    if parsed is None:
        raise HarnessError("search_compiled_bracket has no parsed expression to search")
    print("search_compiled_bracket", flush=True)
    return call_method(parsed, _BRACKET_SEARCH_ATTR, document)


def require_bracket_value(result: CallResult) -> Any:
    """Return the value of a successful search or compile.

    A successful host none is returned as ``None``. A captured exception
    is a harness failure, never a silent none.
    """
    value = require_value(result)
    print(f"search_value={value!r}", flush=True)
    return value


def require_bracket_value_error(result: CallResult) -> ValueError:
    """Return the captured exception when it is a kind of value error.

    Hard-fails if the call returned a value or raised something that is
    not a value error. The exception type and repr go in the message.
    """
    if result.exception is None:
        raise HarnessError(
            "call returned a value; expected a value error "
            f"(value={result.value!r}, type={type(result.value)!r})"
        )
    try:
        exc = require_value_error(result)
    except HarnessError:
        raise
    print(f"value_error={type(exc).__name__}: {exc!r}", flush=True)
    return exc


def require_bracket_null(result: CallResult) -> None:
    """Require a successful search whose value is the host none."""
    value = require_bracket_value(result)
    assert result.exception is None, (
        "successful null must have no exception; "
        f"got {type(result.exception).__name__}: {result.exception!r}"
    )
    assert value is None, f"expected successful null, got {value!r}"


def assert_bracket_search_is_value_error(expression: str, document: Any) -> ValueError:
    """Assert that a one-shot search of *expression* is a value error.

    The call must not return *document* and must not succeed as none.
    """
    result = oneshot_bracket_search(expression, document)
    assert result.exception is not None, (
        f"search of {expression!r} must not succeed "
        f"(value={result.value!r})"
    )
    exc = require_bracket_value_error(result)
    assert result.value is not document, "failed search yielded the document"
    return exc


def assert_bracket_compile_is_value_error(expression: str) -> ValueError:
    """Assert that compile of *expression* is a value error.

    Compile must not return a searchable parsed object.
    """
    result = compile_bracket_expression(expression)
    assert result.exception is not None, (
        f"compile of {expression!r} must not succeed "
        f"(value={result.value!r})"
    )
    exc = require_bracket_value_error(result)
    assert result.value is None, (
        "compile returned a parsed object instead of a value error: "
        f"{result.value!r}"
    )
    return exc


def bracket_kind_marker(exc: BaseException) -> type:
    """Caller-visible FP-01 kind marker of a captured value error.

    The marker is the type object of the captured exception. It does not
    vary with the expression text and is not the wording of any report.
    Two failures are the same kind exactly when they share this marker,
    and different kinds when the markers differ. Does not name a
    product exception class, a fixed phrase, or leftover identity after
    stripping.
    """
    if not isinstance(exc, BaseException):
        raise HarnessError(
            f"bracket_kind_marker expected an exception; got {type(exc)!r}"
        )
    if not isinstance(exc, ValueError):
        raise HarnessError(
            "bracket_kind_marker requires a kind of value error, got "
            f"{type(exc).__name__}: {exc!r}"
        )
    marker = type(exc)
    print(f"kind_marker={marker.__name__}", flush=True)
    return marker


def assert_bracket_kind_markers_match(
    left: BaseException, right: BaseException
) -> None:
    """Assert two value errors share the FP-01 kind marker.

    Same kind is exact marker identity. Subclassing is not same-kind:
    a more specific type is a different marker. Does not compare
    leftover report text.
    """
    left_m = bracket_kind_marker(left)
    right_m = bracket_kind_marker(right)
    print(
        f"kind_marker_match left={left_m.__name__} right={right_m.__name__}",
        flush=True,
    )
    assert left_m is right_m, (
        "failures must share a kind marker that does not vary with "
        "the expression text and is not report wording; "
        f"got {left_m.__name__} vs {right_m.__name__}"
    )


def assert_bracket_kind_markers_differ(
    left: BaseException, right: BaseException
) -> None:
    """Assert two value errors present different FP-01 kind markers."""
    left_m = bracket_kind_marker(left)
    right_m = bracket_kind_marker(right)
    print(
        f"kind_marker_differ left={left_m.__name__} right={right_m.__name__}",
        flush=True,
    )
    assert left_m is not right_m, (
        "kind markers must differ; both are "
        f"{left_m.__name__}"
    )


def bracket_ident() -> str:
    """Process-local Latin identifier that is not a public oracle token."""
    token = "k" + uuid.uuid4().hex[:12]
    if token in _RESERVED:
        raise HarnessError(f"bracket_ident collided with a reserved token: {token}")
    return token


def bracket_payload() -> str:
    """Process-local string payload that is not a public oracle token."""
    token = "v" + uuid.uuid4().hex
    if token in _RESERVED:
        raise HarnessError(f"bracket_payload collided with a reserved token: {token}")
    return token


def bracket_sentinel_document() -> dict[str, str]:
    """Mapping whose key and value are process-local, not public samples."""
    return {bracket_ident(): bracket_payload()}


def require_oneshot_equals(expression: str, document: object, expected: object) -> object:
    """Search *expression* once and require the value to equal *expected*.

    A new F03 name: F02 sealed ``_oneshot_equals`` as a local and did not
    export it, so this slice must not reuse that name.
    """
    value = require_bracket_value(oneshot_bracket_search(expression, document))
    print(
        f"oneshot_equals expression={expression!r} value={value!r} expected={expected!r}",
        flush=True,
    )
    assert value == expected, f"{expression!r} yielded {value!r}, expected {expected!r}"
    return value


def host_slice(sequence: Any, start: Any, stop: Any, step: Any) -> list:
    """Apply the host slice rules to a list and return a new list.

    *sequence* must be a ``list``. A step of ``0``, a string, a mapping,
    or any other non-list is unclassifiable and raises — never a
    character slice or ``[]`` standing in for "could not slice".
    """
    if isinstance(sequence, (str, dict)):
        raise HarnessError(
            f"host_slice refuses a non-list current value: {type(sequence)!r}"
        )
    if not isinstance(sequence, list):
        raise HarnessError(
            f"host_slice requires a list, got {type(sequence)!r}"
        )
    start_b = _slice_bound(start, label="start")
    stop_b = _slice_bound(stop, label="stop")
    if step == 0:
        raise HarnessError("host_slice refuses a step of 0")
    if step is None:
        sliced = sequence[start_b:stop_b]
    else:
        if type(step) is not int:
            raise HarnessError(f"host_slice step must be int or None, got {type(step)!r}")
        sliced = sequence[start_b:stop_b:step]
    if not isinstance(sliced, list):
        raise HarnessError(
            f"host slice of a list must yield a list, got {type(sliced)!r}"
        )
    result = list(sliced)
    print(
        f"host_slice start={start_b!r} stop={stop_b!r} step={step!r} -> {result!r}",
        flush=True,
    )
    return result


def slice_text(start: Any, stop: Any, step: Any) -> str:
    """Render an optional three-part slice as ``[...]`` text.

    A step of ``0`` is refused: a successful expression must not carry
    a zero step. Public oracles are written as the PRD spells them and
    do not go through this helper.
    """
    if step == 0:
        raise HarnessError("slice_text refuses a step of 0")
    start_s = _bound_text(start, label="start")
    stop_s = _bound_text(stop, label="stop")
    if step is None:
        text = f"[{start_s}:{stop_s}]"
    else:
        if type(step) is not int:
            raise HarnessError(f"slice_text step must be int or None, got {type(step)!r}")
        text = f"[{start_s}:{stop_s}:{step}]"
    print(f"slice_text={text!r}", flush=True)
    return text


def in_range_index(length: int) -> int:
    """Process-local index in ``[0, length)``.

    When *length* is greater than 1 the index is never ``0``, so a stub
    that only implements the first element cannot hide behind entropy.
    """
    if type(length) is not int:
        raise HarnessError(f"in_range_index requires int length, got {type(length)!r}")
    if length < 1:
        raise HarnessError(f"in_range_index requires length >= 1, got {length!r}")
    if length == 1:
        return 0
    idx = 1 + (int(uuid.uuid4().hex[:8], 16) % (length - 1))
    if idx <= 0 or idx >= length:
        raise HarnessError(f"in_range_index produced {idx!r} outside [1, {length})")
    print(f"in_range_index length={length} -> {idx}", flush=True)
    return idx


def from_end_index(length: int) -> int:
    """Process-local ``k`` in ``[2, length]`` so ``[-k]`` is not the last item."""
    if type(length) is not int:
        raise HarnessError(f"from_end_index requires int length, got {type(length)!r}")
    if length < 3:
        raise HarnessError(f"from_end_index requires length >= 3, got {length!r}")
    k = 2 + (int(uuid.uuid4().hex[:8], 16) % (length - 1))
    if k < 2 or k > length:
        raise HarnessError(f"from_end_index produced {k!r} outside [2, {length}]")
    position = length - k
    if position == length - 1:
        raise HarnessError(f"from_end_index k={k} still names the last element")
    print(f"from_end_index length={length} k={k} position={position}", flush=True)
    return k


def assert_step_zero_kind_unlike_syntax(
    step0: BaseException,
    four_part: BaseException,
    foo_syntax: BaseException,
) -> None:
    """L174: the step-0 kind marker differs from four-part and from ``foo.``.

    Kind is the FP-01 kind marker: it does not vary with the
    expression text and is not leftover report wording. Does not
    compare leftover stems after stripping.
    """
    for label, exc in (
        ("step0", step0),
        ("four_part", four_part),
        ("foo_syntax", foo_syntax),
    ):
        if not isinstance(exc, BaseException):
            raise HarnessError(
                f"{label} must be a captured failure, got {type(exc)!r}"
            )
        if not isinstance(exc, ValueError):
            raise HarnessError(
                f"{label} must be a kind of value error, got "
                f"{type(exc).__name__}: {exc!r}"
            )
    print(
        "step_zero_kind_unlike_syntax "
        f"step0={type(step0).__name__} "
        f"four_part={type(four_part).__name__} "
        f"foo_syntax={type(foo_syntax).__name__}",
        flush=True,
    )
    assert_bracket_kind_markers_differ(step0, four_part)
    assert_bracket_kind_markers_differ(step0, foo_syntax)


def require_step_zero_search_failure(expression: str, document: Any) -> ValueError:
    """One-shot search of a step-0 slice must be a value error.

    The call must not succeed as ``[]``, as host none, or by yielding
    *document*. Unclassifiable outcomes raise.
    """
    if not isinstance(expression, str):
        raise HarnessError(
            f"require_step_zero_search_failure requires str expression, "
            f"got {type(expression)!r}"
        )
    result = oneshot_bracket_search(expression, document)
    if result.exception is None:
        raise HarnessError(
            f"step-0 search of {expression!r} succeeded "
            f"(value={result.value!r}); expected a value error, not a "
            "successful empty array, successful null, or the document"
        )
    if result.value is document:
        raise HarnessError(
            f"step-0 search of {expression!r} yielded the input document"
        )
    exc = require_bracket_value_error(result)
    print(f"step_zero_failure expression={expression!r}", flush=True)
    return exc


def require_successful_empty_array(result: CallResult) -> list:
    """Return the value of a successful search that yielded ``[]``.

    Successful host none is a different outcome and raises. A captured
    exception is a harness failure, never ``[]``.
    """
    value = require_bracket_value(result)
    if result.exception is not None:
        raise HarnessError(
            "successful empty array must have no exception; "
            f"got {type(result.exception).__name__}: {result.exception!r}"
        )
    if value is None:
        raise HarnessError("expected a successful empty array; got successful null")
    if value != []:
        raise HarnessError(f"expected a successful empty array; got {value!r}")
    print("successful_empty_array=[]", flush=True)
    return value


def require_compile_then_search_step_zero_kind(
    expression: str,
    document: Any,
    *,
    canonical_step0: BaseException,
    four_part: BaseException,
    foo_syntax: BaseException,
) -> ValueError:
    """L174: compile-then-search of a step-0 slice presents the step-0 kind.

    Unconditional: compile may refuse, or search of the parsed object
    may refuse. Either way the captured failure shares the step-0 kind
    marker of *canonical_step0* and differs from the syntax kind marker
    of a four-part slice and of ``foo.``. Does not compare leftover stems
    after stripping, name an exception class, or pin a phrase.
    """
    compiled_exc = require_step_zero_compile_path_failure(expression, document)
    print(
        "compile_then_search_step_zero_kind "
        f"expression={expression!r} "
        f"compiled={type(compiled_exc).__name__}",
        flush=True,
    )
    assert_bracket_kind_markers_match(canonical_step0, compiled_exc)
    assert_step_zero_kind_unlike_syntax(compiled_exc, four_part, foo_syntax)
    return compiled_exc


def require_step_zero_compile_path_failure(
    expression: str, document: Any
) -> ValueError:
    """Refuse a step-0 slice on the compile-then-search path.

    Compile may itself be a value error (a legal shape). If compile
    returns a searchable object, searching that object must be a value
    error and must not succeed as ``[]``.
    """
    if not isinstance(expression, str):
        raise HarnessError(
            f"require_step_zero_compile_path_failure requires str, "
            f"got {type(expression)!r}"
        )
    compiled = compile_bracket_expression(expression)
    if compiled.exception is not None:
        exc = require_bracket_value_error(compiled)
        print(f"step_zero_compile_refused expression={expression!r}", flush=True)
        return exc
    parsed = require_bracket_value(compiled)
    searched = search_compiled_bracket(parsed, document)
    if searched.exception is None:
        raise HarnessError(
            f"search of compiled {expression!r} succeeded "
            f"(value={searched.value!r}); step 0 must not yield []"
        )
    exc = require_bracket_value_error(searched)
    print(f"step_zero_compiled_search_failed expression={expression!r}", flush=True)
    return exc


def _slice_bound(value: Any, *, label: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise HarnessError(f"host_slice {label} must be int or None, got {type(value)!r}")
    return value


def _bound_text(value: Any, *, label: str) -> str:
    if value is None:
        return ""
    if type(value) is not int:
        raise HarnessError(f"slice_text {label} must be int or None, got {type(value)!r}")
    return str(value)
