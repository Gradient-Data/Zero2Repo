# feature: F01
"""Observation helpers for string-parse of TOML document structure (FP-01).

Helpers classify outcomes of the public string-parse entry. They never return
an empty mapping or ``None`` to mean "the call could not be classified".
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from _harness import CallResult, HarnessError, call

_RESERVED_INTS = frozenset({1, 26, 27, 1234, 100000000})


def string_parse_entry() -> Callable[..., Any]:
    """Return the public string-parse callable from the package root.

    The product is imported here, not at module import time, so this helper
    module still loads when the product is absent from ``sys.path``.
    """
    from tomlparse import loads

    if not callable(loads):
        raise HarnessError("string-parse entry is not callable")
    return loads


def decode_error_type() -> type[BaseException]:
    """Return the public decode-error type from the package root."""
    from tomlparse import TOMLDecodeError

    if not isinstance(TOMLDecodeError, type):
        raise HarnessError(
            f"decode error type is not a class: {TOMLDecodeError!r}"
        )
    return TOMLDecodeError


def parse_text(text: str) -> CallResult:
    """Parse *text* through the public string-parse entry.

    Harness failures (timeout, isolation) propagate. A product exception is a
    classified ``CallResult``, not a sentinel mapping.
    """
    if not isinstance(text, str):
        raise HarnessError(f"parse_text requires str, got {type(text)!r}")
    return call(string_parse_entry(), text)


def is_mapping(obj: Any) -> bool:
    """Return whether *obj* is a document/table mapping."""
    if obj is None:
        raise HarnessError("cannot classify None as a mapping")
    return isinstance(obj, Mapping)


def is_sequence(obj: Any) -> bool:
    """Return whether *obj* is an array/table-array sequence (not a string)."""
    if obj is None:
        raise HarnessError("cannot classify None as a sequence")
    if isinstance(obj, (str, bytes, bytearray)):
        return False
    return isinstance(obj, Sequence)


def require_str_keys(mapping: Any) -> None:
    """Assert every key on this layer is a ``str``."""
    if not is_mapping(mapping):
        raise HarnessError(
            f"require_str_keys expected a mapping, got {type(mapping)!r}"
        )
    for key in mapping:
        if not isinstance(key, str):
            raise AssertionError(
                f"document key {key!r} has type {type(key).__name__}, not str"
            )


def require_mapping(result: CallResult) -> Mapping[str, Any]:
    """Return the document mapping, or fail. Never returns ``{}`` on error."""
    if result.exception is not None:
        raise AssertionError(
            "parse failed; expected a document mapping, got "
            f"{type(result.exception).__name__}: {result.exception!r}"
        )
    value = result.value
    if not is_mapping(value):
        raise AssertionError(
            f"parse returned non-mapping {type(value)!r}: {value!r}"
        )
    require_str_keys(value)
    return value


def require_sequence(obj: Any) -> Sequence[Any]:
    """Return *obj* if it is a sequence; otherwise fail the observation."""
    if not is_sequence(obj):
        raise AssertionError(f"expected a sequence, got {type(obj)!r}: {obj!r}")
    return obj


def require_path(mapping: Mapping[str, Any], *keys: str) -> Any:
    """Walk *keys* through nested mappings. Missing/non-mapping raises."""
    current: Any = mapping
    walked: list[str] = []
    for key in keys:
        if not is_mapping(current):
            raise AssertionError(
                f"path {walked!r} is not a mapping; got {type(current)!r}"
            )
        require_str_keys(current)
        if key not in current:
            raise AssertionError(
                f"missing key {key!r} under {walked!r}; have {list(current)}"
            )
        current = current[key]
        walked.append(key)
    return current


def require_nested_empty_except_chain(
    mapping: Mapping[str, Any], *parts: str
) -> None:
    """Assert omitted super-tables along *parts* are empty except that chain.

    The document mapping contains only the first part. Each intermediate table
    contains only the next part. The innermost table has no keys. Missing
    parts, non-mappings, and extra keys fail out loud — never as absence.
    """
    if not parts:
        raise HarnessError(
            "require_nested_empty_except_chain needs at least one part"
        )
    if not is_mapping(mapping):
        raise AssertionError(
            f"expected a mapping at the omitted-chain root, got {type(mapping)!r}"
        )
    require_str_keys(mapping)
    first = parts[0]
    if set(mapping) != {first}:
        raise AssertionError(
            f"omitted-chain root keys {set(mapping)!r} are not only {first!r}"
        )
    for i, _part in enumerate(parts):
        node = require_path(mapping, *parts[: i + 1])
        if not is_mapping(node):
            raise AssertionError(
                f"omitted-chain table {parts[: i + 1]!r} is not a mapping: "
                f"{type(node)!r}"
            )
        require_str_keys(node)
        if i + 1 == len(parts):
            if len(node) != 0:
                raise AssertionError(
                    f"innermost omitted table {parts!r} has extra keys {list(node)}"
                )
        else:
            nxt = parts[i + 1]
            if set(node) != {nxt}:
                raise AssertionError(
                    f"omitted-chain table {parts[: i + 1]!r} keys {set(node)!r} "
                    f"are not only the next part {nxt!r}"
                )


def require_sequence_mappings_contain(obj: Any, key: str) -> Sequence[Any]:
    """Assert *obj* is a sequence of mappings that each contain *key*.

    The nested value under *key* is not inspected here: callers that need a
    pair bound on that current item (for example ``val`` on ``subtab``)
    walk the sub-table themselves. A non-sequence, a non-mapping item,
    or a missing *key* fails out loud — never as absence.
    """
    if not isinstance(key, str):
        raise HarnessError(
            f"require_sequence_mappings_contain key must be str, got {type(key)!r}"
        )
    seq = require_sequence(obj)
    for i, item in enumerate(seq):
        if not is_mapping(item):
            raise AssertionError(
                f"sequence item {i} is not a mapping: {type(item)!r}"
            )
        require_str_keys(item)
        if key not in item:
            raise AssertionError(
                f"sequence item {i} keys {list(item)} do not contain {key!r}"
            )
    return seq


def require_decode_failure(result: CallResult) -> BaseException:
    """Require a decode error (a value error) that is not a recursion error.

    Unclassified exceptions raise :class:`HarnessError` rather than being
    treated as the documented decode failure.
    """
    if result.exception is None:
        raise AssertionError(
            f"parse succeeded with {result.value!r}; expected a decode error"
        )
    exc = result.exception
    if isinstance(exc, RecursionError):
        raise HarnessError(
            f"expected decode error, got recursion error: {exc!r}"
        )
    decode_type = decode_error_type()
    if not isinstance(exc, decode_type):
        raise HarnessError(
            f"unclassified exception {type(exc).__name__}: {exc!r}"
        )
    if not isinstance(exc, ValueError):
        raise HarnessError(
            "decode error is not a value error: "
            f"{type(exc).__name__}: {exc!r}"
        )
    return exc


def require_recursion_failure(result: CallResult) -> BaseException:
    """Require a recursion error that is not a decode error, and no mapping.

    FP-01 does not score extra nesting depth. Later feature points that do
    name a recursion-error carrier still import this helper.
    """
    if result.exception is None:
        raise AssertionError(
            f"parse succeeded with {result.value!r}; expected a recursion error"
        )
    exc = result.exception
    decode_type = decode_error_type()
    if isinstance(exc, decode_type):
        raise HarnessError(
            f"expected recursion error, got decode error: {exc!r}"
        )
    if not isinstance(exc, RecursionError):
        raise HarnessError(
            f"unclassified exception {type(exc).__name__}: {exc!r}"
        )
    return exc


def nested_array_source(depth: int) -> str:
    """TOML whose ``arr`` value is an inline array nested *depth* levels."""
    if not isinstance(depth, int) or depth < 1:
        raise HarnessError(f"nested_array_source depth must be >= 1, got {depth!r}")
    return "arr = " + "[" * depth + "]" * depth


def nested_inline_table_source(depth: int) -> str:
    """TOML whose ``key`` value is an inline table nested *depth* levels."""
    if not isinstance(depth, int) or depth < 1:
        raise HarnessError(
            f"nested_inline_table_source depth must be >= 1, got {depth!r}"
        )
    return "key = {" * depth + "}" * depth


def dotted_key_source(parts: int) -> str:
    """TOML assigning ``1`` through a dotted key of *parts* ``a`` segments."""
    if not isinstance(parts, int) or parts < 1:
        raise HarnessError(f"dotted_key_source parts must be >= 1, got {parts!r}")
    return "a." * (parts - 1) + "a = 1"


def runtime_token() -> str:
    """Process-local alphanumeric token valid as a TOML bare key."""
    return "k" + uuid.uuid4().hex[:12]


def runtime_int() -> int:
    """Process-local positive integer away from the document literals."""
    n = int(uuid.uuid4().hex[:8], 16) % 900000 + 10000
    if n in _RESERVED_INTS:
        n += 17
    return n


def runtime_depth(*, low: int = 8, high: int = 20) -> int:
    """Pick a nesting depth in ``[low, high]`` that is not 310 or 470."""
    if high < low:
        raise HarnessError(f"runtime_depth range inverted: {low}..{high}")
    span = high - low + 1
    depth = low + (int(uuid.uuid4().hex[:4], 16) % span)
    if depth in {310, 470}:
        raise HarnessError(f"runtime_depth produced a stated nesting depth {depth}")
    return depth
