# feature: F02
"""Observation helpers for identifier and dotted-subexpression selection (FP-02).

New names only. Observation of the two public entries lives here under
F02 names; a predecessor that is not sealed on this walk is not
imported. A helper that cannot classify its input raises; it never
returns an empty string or ``None`` to mean "no token" or "lookup failed".
"""

from __future__ import annotations

import json
import string
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
        "other",
        "correct",
        "missing",
        "one",
        "two",
        "three",
        "found",
        "bad",
        "dot",
        "space",
        "__L",
        "Y_1623",
        "foo.bar",
        "foo bar",
        "foo-bar",
        "1",
    }
)

# JSON string escape letters (and the quote / slash / backslash tokens).
_JSON_ESCAPE_LETTERS = frozenset('"\\/bfnrtu')
_ILLEGAL_ESCAPE_LETTERS = tuple(
    ch for ch in string.ascii_letters if ch not in _JSON_ESCAPE_LETTERS
)

# Public escape-oracle codepoints that a runtime \\u twin must not reuse.
_FORBIDDEN_UNICODE = frozenset({0xCEBB, 0x262F})

_UNQUOTED_BODY = frozenset(string.ascii_letters + string.digits + "_")

# Public search callable on a successful compile result (FP-01 entries).
_FIELD_SEARCH_ATTR = "search"


def _field_search_entry() -> Callable[..., Any]:
    """Return the public one-shot search callable from the package root."""
    from pathsel import search

    if not callable(search):
        raise HarnessError("search entry is not callable")
    return search


def _field_compile_entry() -> Callable[..., Any]:
    """Return the public compile callable from the package root."""
    from pathsel import compile as compile_entry

    if not callable(compile_entry):
        raise HarnessError("compile entry is not callable")
    return compile_entry


def oneshot_field_search(expression: str, document: Any) -> CallResult:
    """Search *expression* against *document* through the one-shot entry."""
    if not isinstance(expression, str):
        raise HarnessError(
            f"oneshot_field_search requires str expression, got {type(expression)!r}"
        )
    print(f"oneshot expression={expression!r}", flush=True)
    return call(_field_search_entry(), expression, document)


def compile_field_expression(expression: str) -> CallResult:
    """Compile *expression* through the compile entry."""
    if not isinstance(expression, str):
        raise HarnessError(
            f"compile_field_expression requires str expression, got {type(expression)!r}"
        )
    print(f"compile expression={expression!r}", flush=True)
    return call(_field_compile_entry(), expression)


def search_compiled_field(parsed: Any, document: Any) -> CallResult:
    """Search a compiled expression against *document* (no new compile)."""
    if parsed is None:
        raise HarnessError("search_compiled_field has no parsed expression to search")
    print("search_compiled_field", flush=True)
    return call_method(parsed, _FIELD_SEARCH_ATTR, document)


def require_field_value(result: CallResult) -> Any:
    """Return the value of a successful search or compile.

    A successful host none is returned as ``None``. A captured exception
    is a harness failure, never a silent none.
    """
    value = require_value(result)
    print(f"search_value={value!r}", flush=True)
    return value


def require_field_value_error(result: CallResult) -> ValueError:
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


def require_field_null(result: CallResult) -> None:
    """Require a successful search whose value is the host none."""
    value = require_field_value(result)
    assert result.exception is None, (
        "successful null must have no exception; "
        f"got {type(result.exception).__name__}: {result.exception!r}"
    )
    assert value is None, f"expected successful null, got {value!r}"


def assert_field_search_is_value_error(expression: str, document: Any) -> ValueError:
    """Assert that a one-shot search of *expression* is a value error.

    The call must not return *document* and must not succeed as none.
    """
    result = oneshot_field_search(expression, document)
    assert result.exception is not None, (
        f"search of {expression!r} must not succeed "
        f"(value={result.value!r})"
    )
    exc = require_field_value_error(result)
    assert result.value is not document, "failed search yielded the document"
    return exc


def assert_field_compile_is_value_error(expression: str) -> ValueError:
    """Assert that compile of *expression* is a value error.

    Compile must not return a searchable parsed object.
    """
    result = compile_field_expression(expression)
    assert result.exception is not None, (
        f"compile of {expression!r} must not succeed "
        f"(value={result.value!r})"
    )
    exc = require_field_value_error(result)
    assert result.value is None, (
        "compile returned a parsed object instead of a value error: "
        f"{result.value!r}"
    )
    return exc


def field_kind_marker(exc: BaseException) -> type:
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
            f"field_kind_marker expected an exception; got {type(exc)!r}"
        )
    if not isinstance(exc, ValueError):
        raise HarnessError(
            "field_kind_marker requires a kind of value error, got "
            f"{type(exc).__name__}: {exc!r}"
        )
    marker = type(exc)
    print(f"kind_marker={marker.__name__}", flush=True)
    return marker


def assert_field_kind_markers_match(
    left: BaseException, right: BaseException
) -> None:
    """Assert two value errors share the FP-01 kind marker.

    Same kind is exact marker identity. Subclassing is not same-kind:
    a more specific type is a different marker. Does not compare
    leftover report text.
    """
    left_m = field_kind_marker(left)
    right_m = field_kind_marker(right)
    print(
        f"kind_marker_match left={left_m.__name__} right={right_m.__name__}",
        flush=True,
    )
    assert left_m is right_m, (
        "failures must share a kind marker that does not vary with "
        "the expression text and is not report wording; "
        f"got {left_m.__name__} vs {right_m.__name__}"
    )


def assert_field_kind_markers_differ(
    left: BaseException, right: BaseException
) -> None:
    """Assert two value errors present different FP-01 kind markers."""
    left_m = field_kind_marker(left)
    right_m = field_kind_marker(right)
    print(
        f"kind_marker_differ left={left_m.__name__} right={right_m.__name__}",
        flush=True,
    )
    assert left_m is not right_m, (
        "kind markers must differ; both are "
        f"{left_m.__name__}"
    )


def _require_field_value_error_kinds(
    observed: BaseException,
    empty: BaseException,
    incomplete: BaseException,
    syntax: BaseException,
) -> None:
    """Hard-fail unless each argument is a captured kind of value error."""
    for label, exc in (
        ("observed", observed),
        ("empty", empty),
        ("incomplete", incomplete),
        ("syntax", syntax),
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


def assert_field_handled_as_more_specific_syntax(
    observed: BaseException,
    empty: BaseException,
    incomplete: BaseException,
    syntax: BaseException,
) -> None:
    """L134/L136 more-specific-form carrier for a syntax refusal that is not ``foo.``.

    *observed* is already a kind of value error. It does not use the
    empty-expression kind of *empty* (a zero-length expression) and
    does not use the incomplete-expression kind of *incomplete*
    (unmatched ``(``). A caller who already handles the syntax kind of
    *syntax* (``foo.`` on the same entry) also handles *observed*,
    including a more specific syntax form. The two syntax forms do
    not share identical kind markers. Does not compare leftover report
    text, does not name a product exception class, and does not pin
    a fixed phrase.
    """
    _require_field_value_error_kinds(observed, empty, incomplete, syntax)
    empty_kind = type(empty)
    incomplete_kind = type(incomplete)
    syntax_kind = type(syntax)
    print(
        "more_specific_syntax_carrier "
        f"observed={type(observed).__name__} "
        f"empty={empty_kind.__name__} "
        f"incomplete={incomplete_kind.__name__} "
        f"syntax={syntax_kind.__name__}",
        flush=True,
    )
    assert not isinstance(observed, empty_kind), (
        "this more-specific syntax form must not use the empty-expression "
        "kind marker of a zero-length expression; "
        f"got {type(observed).__name__}"
    )
    assert not isinstance(observed, incomplete_kind), (
        "this more-specific syntax form must not use the incomplete-"
        "expression kind marker of unmatched '('; "
        f"got {type(observed).__name__}"
    )
    if not isinstance(observed, syntax_kind):
        raise AssertionError(
            "a caller who already handles the syntax kind of 'foo.' must "
            "also handle this refusal, including a more specific syntax "
            f"form; got {type(observed).__name__}, "
            f"syntax kind is {syntax_kind.__name__}"
        )
    assert_field_kind_markers_differ(observed, syntax)


def field_ident() -> str:
    """Process-local Latin identifier that is not a public oracle token."""
    token = "k" + uuid.uuid4().hex[:12]
    if token in _RESERVED:
        raise HarnessError(f"field_ident collided with a reserved token: {token}")
    return token


def field_payload() -> str:
    """Process-local string payload that is not a public oracle token."""
    token = "v" + uuid.uuid4().hex
    if token in _RESERVED:
        raise HarnessError(f"field_payload collided with a reserved token: {token}")
    return token


def field_sentinel_document() -> dict[str, str]:
    """Mapping whose key and value are process-local, not public samples."""
    return {field_ident(): field_payload()}


def quoted_ident_text(key: str, *, ensure_ascii: bool = True) -> str:
    """Return *key* as a quoted-identifier token (a host JSON string).

    The return value includes the surrounding double quotes. With
    ``ensure_ascii=True``, every non-ASCII code point must appear as a
    ``\\uXXXX`` escape — never as a raw character inside the quotes.
    """
    if not isinstance(key, str):
        raise HarnessError(f"quoted_ident_text requires str key, got {type(key)!r}")
    try:
        text = json.dumps(key, ensure_ascii=ensure_ascii)
    except (TypeError, ValueError) as exc:
        raise HarnessError(f"cannot JSON-encode quoted identifier key {key!r}: {exc}") from exc
    if not (len(text) >= 2 and text[0] == '"' and text[-1] == '"'):
        raise HarnessError(
            f"host JSON encoding of {key!r} is not a double-quoted string: {text!r}"
        )
    if ensure_ascii:
        for ch in key:
            if ord(ch) > 127 and r"\u" not in text:
                raise HarnessError(
                    "ensure_ascii=True must emit a \\u escape for non-ASCII "
                    f"in {key!r}; got {text!r}"
                )
    print(f"quoted_ident_text={text!r}", flush=True)
    return text


def join_tokens(*parts: str, gap: str) -> str:
    """Join token spellings with *gap* between each neighbouring pair.

    Empty *parts* or a non-string *gap* is unclassifiable. An empty token
    is rejected rather than silently dropped (that would look like "no
    token was supplied").
    """
    if not parts:
        raise HarnessError("join_tokens requires at least one token")
    if not isinstance(gap, str):
        raise HarnessError(f"join_tokens gap must be str, got {type(gap)!r}")
    tokens: list[str] = []
    for part in parts:
        if not isinstance(part, str):
            raise HarnessError(f"join_tokens tokens must be str, got {type(part)!r}")
        if part == "":
            raise HarnessError("join_tokens tokens must be non-empty")
        tokens.append(part)
    joined = gap.join(tokens)
    print(f"join_tokens gap={gap!r} -> {joined!r}", flush=True)
    return joined


def _require_unquoted_ident(token: str, *, label: str) -> str:
    if not isinstance(token, str) or not token:
        raise HarnessError(f"{label} produced an empty or non-str identifier")
    first = token[0]
    if not (first == "_" or (first.isascii() and first.isalpha())):
        raise HarnessError(f"{label} must start with a Latin letter or '_': {token!r}")
    if any(ch not in _UNQUOTED_BODY for ch in token):
        raise HarnessError(f"{label} is not a legal unquoted identifier: {token!r}")
    if token in _RESERVED:
        raise HarnessError(f"{label} collided with a reserved token: {token}")
    return token


def runtime_leading_underscore_ident() -> str:
    """Process-local unquoted identifier that starts with ``_`` and is not ``__L``."""
    token = "_" + uuid.uuid4().hex[:12]
    if token == "__L":
        raise HarnessError("runtime leading-underscore ident collided with __L")
    if not token.startswith("_"):
        raise HarnessError(f"runtime leading-underscore ident does not start with '_': {token!r}")
    return _require_unquoted_ident(token, label="runtime_leading_underscore_ident")


def runtime_interior_underscore_ident() -> str:
    """Process-local unquoted identifier whose body contains ``_``, not ``Y_1623``."""
    token = "p_" + uuid.uuid4().hex[:10]
    if token == "Y_1623":
        raise HarnessError("runtime interior-underscore ident collided with Y_1623")
    if not (token[0].isascii() and token[0].isalpha()):
        raise HarnessError(
            f"runtime interior-underscore ident must start with a Latin letter: {token!r}"
        )
    if "_" not in token[1:]:
        raise HarnessError(
            f"runtime interior-underscore ident must contain '_' in the body: {token!r}"
        )
    return _require_unquoted_ident(token, label="runtime_interior_underscore_ident")


def quoted_ident_with_runtime_unicode_escape() -> tuple[str, str]:
    """Return ``(expression, decoded_key)`` for a process-local ``\\u`` escape.

    *expression* is ASCII JSON (``ensure_ascii=True``) and must contain
    ``\\u`` plus four hex digits of a BMP code point that is not U+CEBB
    and not U+262F. Missing ``\\u`` is a harness failure, not a fallback
    to a raw Unicode character.
    """
    n = int(uuid.uuid4().hex[:4], 16)
    codepoint = 0x4E00 + (n % 0x2000)
    if codepoint in _FORBIDDEN_UNICODE:
        codepoint = 0x4E00 + ((n + 17) % 0x2000)
    if codepoint in _FORBIDDEN_UNICODE:
        raise HarnessError(f"runtime unicode escape reused a public code point: {codepoint:#06x}")
    if codepoint > 0xFFFF:
        raise HarnessError(f"runtime unicode escape is not BMP: {codepoint:#x}")
    decoded_key = chr(codepoint)
    expression = quoted_ident_text(decoded_key, ensure_ascii=True)
    if r"\u" not in expression:
        raise HarnessError(
            "runtime unicode-escape expression must contain \\u and four hex "
            f"digits; got {expression!r}"
        )
    hex4 = f"{codepoint:04x}"
    if hex4 not in expression.lower():
        raise HarnessError(
            f"runtime unicode-escape expression {expression!r} does not "
            f"contain the four hex digits of U+{hex4.upper()}"
        )
    print(
        f"runtime_unicode_escape expr={expression!r} key={decoded_key!r} "
        f"u+{hex4}",
        flush=True,
    )
    return expression, decoded_key


def runtime_illegal_escape_letter() -> str:
    """ASCII letter that is not a JSON string-escape letter, chosen per process."""
    if not _ILLEGAL_ESCAPE_LETTERS:
        raise HarnessError("no ASCII letters remain outside the JSON escape set")
    idx = int(uuid.uuid4().hex[:2], 16) % len(_ILLEGAL_ESCAPE_LETTERS)
    letter = _ILLEGAL_ESCAPE_LETTERS[idx]
    if letter in _JSON_ESCAPE_LETTERS:
        raise HarnessError(f"illegal-escape letter {letter!r} is a JSON escape letter")
    if len(letter) != 1 or not letter.isascii() or not letter.isalpha():
        raise HarnessError(f"illegal-escape letter is not a single ASCII letter: {letter!r}")
    print(f"illegal_escape_letter={letter!r}", flush=True)
    return letter


def runtime_illegal_escape_expression() -> str:
    """Quoted identifier whose interior has a process-local illegal JSON escape."""
    letter = runtime_illegal_escape_letter()
    fragment = field_ident()
    expression = f'"{fragment}\\{letter}"'
    needle = "\\" + letter
    if needle not in expression:
        raise HarnessError(
            f"illegal-escape expression {expression!r} lacks \\{letter}"
        )
    print(f"illegal_escape_expression={expression!r}", flush=True)
    return expression


def runtime_dotted_field_key() -> tuple[str, str, str]:
    """Return ``(key, left, right)`` where *key* is ``left.right``.

    Neither side is a public-oracle token. The key itself contains a dot.
    """
    left = field_ident()
    right = field_ident()
    if left in _RESERVED or right in _RESERVED:
        raise HarnessError(f"dotted-field side collided with a reserved token: {left!r}/{right!r}")
    if left in {"foo", "bar"} or right in {"foo", "bar"}:
        raise HarnessError(f"dotted-field side reused foo/bar: {left!r}/{right!r}")
    key = f"{left}.{right}"
    if "." not in key:
        raise HarnessError(f"runtime dotted field key must contain a dot: {key!r}")
    print(f"runtime_dotted_key={key!r}", flush=True)
    return key, left, right


def runtime_unquotable_key() -> str:
    """A key an unquoted identifier cannot name, and that is not a dotted key.

    Shape is process-chosen among: a space, a hyphenated token, or a
    digit-leading name. Public ``foo bar`` / ``foo-bar`` / ``1`` are refused.
    """
    kinds = (
        lambda: f"{field_ident()} {field_ident()}",
        lambda: f"{field_ident()}-{field_ident()}",
        lambda: f"7{field_ident()}",
    )
    idx = int(uuid.uuid4().hex[:2], 16) % len(kinds)
    key = kinds[idx]()
    if key in {"foo bar", "foo-bar", "1", "foo.bar"}:
        raise HarnessError(f"unquotable key collided with a public sample: {key!r}")
    if "." in key:
        raise HarnessError(f"unquotable key must not be a dotted key: {key!r}")
    if key in _RESERVED:
        raise HarnessError(f"unquotable key collided with a reserved token: {key!r}")
    print(f"runtime_unquotable_key={key!r}", flush=True)
    return key


def compile_once_then_search(expression: str, document: Any) -> Any:
    """Compile *expression* once and search the same parsed object twice.

    The second search must use the object already in hand — a new compile
    is not performed. The two searches must agree.
    """
    parsed = require_field_value(compile_field_expression(expression))
    first = require_field_value(search_compiled_field(parsed, document))
    second = require_field_value(search_compiled_field(parsed, document))
    print(
        f"compile_once expression={expression!r} first={first!r} second={second!r}",
        flush=True,
    )
    assert first == second, (
        "second search of the same parsed expression disagreed with the first "
        f"({first!r} vs {second!r}); a new compile must not be required"
    )
    return first


def assert_search_shares_foo_syntax_kind(
    expression: str, document: Any
) -> ValueError:
    """Search *expression* shares the syntax kind marker of ``foo.``.

    Same kind is exact marker identity with a one-shot ``foo.`` on
    the same document. The marker differs from a zero-length
    expression and from unmatched ``(``. Does not compare leftover
    report text.
    """
    observed = assert_field_search_is_value_error(expression, document)
    empty = assert_field_search_is_value_error("", document)
    incomplete = assert_field_search_is_value_error("(", document)
    syntax = assert_field_search_is_value_error("foo.", document)
    print(
        f"search_shares_foo_syntax expression={expression!r}",
        flush=True,
    )
    assert_field_kind_markers_match(observed, syntax)
    assert_field_kind_markers_differ(observed, empty)
    assert_field_kind_markers_differ(observed, incomplete)
    return observed


def assert_compile_shares_foo_syntax_kind(expression: str) -> ValueError:
    """Compile *expression* shares the syntax kind marker of ``foo.``.

    Same kind is exact marker identity with compile of ``foo.``.
    The marker differs from compile of a zero-length expression and
    from compile of unmatched ``(``. Does not compare leftover report
    text.
    """
    observed = assert_field_compile_is_value_error(expression)
    empty = assert_field_compile_is_value_error("")
    incomplete = assert_field_compile_is_value_error("(")
    syntax = assert_field_compile_is_value_error("foo.")
    print(
        f"compile_shares_foo_syntax expression={expression!r}",
        flush=True,
    )
    assert_field_kind_markers_match(observed, syntax)
    assert_field_kind_markers_differ(observed, empty)
    assert_field_kind_markers_differ(observed, incomplete)
    return observed


def assert_search_handled_as_more_specific_syntax(
    expression: str, document: Any
) -> ValueError:
    """Search *expression* is the L134/L136 more-specific syntax kind.

    Value error; not the empty-expression kind of ``""``; not the
    incomplete-expression kind of unmatched ``(``; a caller who
    handles the syntax kind of ``foo.`` also handles this refusal,
    including a more specific syntax form. Does not require leftover
    identity or identical kind markers with ``foo.``.
    """
    observed = assert_field_search_is_value_error(expression, document)
    empty = assert_field_search_is_value_error("", document)
    incomplete = assert_field_search_is_value_error("(", document)
    syntax = assert_field_search_is_value_error("foo.", document)
    print(
        f"search_more_specific_syntax expression={expression!r}",
        flush=True,
    )
    assert_field_handled_as_more_specific_syntax(
        observed, empty, incomplete, syntax
    )
    return observed


def assert_compile_handled_as_more_specific_syntax(expression: str) -> ValueError:
    """Compile *expression* is the L134/L136 more-specific syntax kind.

    Value error; not compile of ``""``; not compile of unmatched
    ``(``; a caller who handles compile of ``foo.`` also handles this
    refusal, including a more specific syntax form. Does not require
    leftover identity or identical kind markers with ``foo.``.
    """
    observed = assert_field_compile_is_value_error(expression)
    empty = assert_field_compile_is_value_error("")
    incomplete = assert_field_compile_is_value_error("(")
    syntax = assert_field_compile_is_value_error("foo.")
    print(
        f"compile_more_specific_syntax expression={expression!r}",
        flush=True,
    )
    assert_field_handled_as_more_specific_syntax(
        observed, empty, incomplete, syntax
    )
    return observed
