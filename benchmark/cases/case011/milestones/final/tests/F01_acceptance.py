# feature: F01
"""FP-01: search an expression and compile it for reuse.

Assertions follow FP-01 of the PRD, the import-from-source-tree
layout of the Interface Contract, and the value-error / failure-kind
rules. Identifier spelling, index/slice beyond
``foo.bar[0]``, and evaluation options are later feature points.
"""

from __future__ import annotations

import pytest
from pathsel import compile, search  # noqa: F401 — public search/compile surface

from _harness import run_python
from F01_helpers import (
    assert_compile_is_value_error,
    assert_handled_as_more_specific_syntax_not_foo_marker,
    assert_kind_markers_differ,
    assert_positions_differ,
    assert_search_is_value_error,
    assert_shares_foo_syntax_kind_not_empty_or_incomplete,
    assert_shares_incomplete_kind_not_syntax_or_empty,
    assert_successful_null,
    compile_expression,
    oneshot_search,
    require_search_value,
    require_successful_null,
    runtime_ident,
    runtime_payload,
    search_parsed,
    sentinel_document,
)

_FOO_BAR_DOC = {"foo": {"bar": "baz"}}
_FOO_BAR_OTHER = {"foo": {"bar": "other"}}
_FOO_BAR_INDEX_DOC = {"foo": {"bar": ["one", "two"]}}
_CORRECT_DOC = {"foo": {"bar": {"baz": "correct"}}}
_EMPTY_OBJECT: dict = {}

_WHITESPACE_ONLY = (" ", "\t", "\n", "\r", " \t\n\r")
_LONE_OPEN = ("[", "{", "(")
_SAME_WAY_SYNTAX = (
    ".",
    "foo.",
    ".foo",
    "foo..bar",
    "]",
    "}",
    ")",
    "foo.1",
    "foo.-11",
    "foo[*]bar",
    "foo[8:2:0:1]",
)

_UNCLOSED_ID = runtime_ident()
_UNCLOSED_QUOTE = f'"{_UNCLOSED_ID}'
_UNCLOSED_BACKTICK = f"`{_UNCLOSED_ID}"
_UNCLOSED_RAW_STRING = f"'{_UNCLOSED_ID}"
_LONE_EQUALS = "="
_LONE_HYPHEN = "-"
_FOO_HYPHEN_BAR = "foo-bar"
_MORE_SPECIFIC_SYNTAX = frozenset(
    {
        _UNCLOSED_QUOTE,
        _UNCLOSED_BACKTICK,
        _UNCLOSED_RAW_STRING,
        _LONE_EQUALS,
        _LONE_HYPHEN,
        _FOO_HYPHEN_BAR,
    }
)
_ILLFORMED = _SAME_WAY_SYNTAX + (
    _UNCLOSED_QUOTE,
    _UNCLOSED_BACKTICK,
    _UNCLOSED_RAW_STRING,
    _LONE_EQUALS,
    _LONE_HYPHEN,
    _FOO_HYPHEN_BAR,
)

_SUBSTRATE_PROBE = (
    "from pathsel import search\n"
    "print(search('foo.bar', {'foo': {'bar': 'baz'}}))\n"
)


def _require_oneshot_equals(expression: str, document: object, expected: object) -> None:
    oneshot = require_search_value(oneshot_search(expression, document))
    parsed = require_search_value(compile_expression(expression))
    compiled = require_search_value(search_parsed(parsed, document))
    print(
        f"entry_pair expression={expression!r} oneshot={oneshot!r} compiled={compiled!r}",
        flush=True,
    )
    assert oneshot == expected, f"oneshot {oneshot!r} != {expected!r}"
    assert compiled == expected, f"compile-then-search {compiled!r} != {expected!r}"
    assert oneshot == compiled


# ---------------------------------------------------------------------------
# A. One-shot nested field
# ---------------------------------------------------------------------------


def test_oneshot_foo_bar_yields_baz():
    value = require_search_value(oneshot_search("foo.bar", _FOO_BAR_DOC))
    assert value == "baz"
    assert value is not _FOO_BAR_DOC
    assert value is not None


def test_oneshot_runtime_nested_path_yields_payload():
    k1 = runtime_ident()
    k2 = runtime_ident()
    payload = runtime_payload()
    document = {k1: {k2: payload}}
    expression = f"{k1}.{k2}"
    value = require_search_value(oneshot_search(expression, document))
    print(f"runtime_path {expression} -> {value!r}", flush=True)
    assert value == payload
    assert value is not document


# ---------------------------------------------------------------------------
# B. Compile once, search two documents
# ---------------------------------------------------------------------------


def test_compile_foo_bar_reused_on_second_document():
    compiled = compile_expression("foo.bar")
    parsed = require_search_value(compiled)
    print(f"parsed_id={id(parsed)}", flush=True)
    first = require_search_value(search_parsed(parsed, _FOO_BAR_DOC))
    assert first == "baz"
    print(f"reuse_parsed_id={id(parsed)}", flush=True)
    second = require_search_value(search_parsed(parsed, _FOO_BAR_OTHER))
    assert second == "other"


def test_compile_runtime_path_reused_on_second_document():
    k1 = runtime_ident()
    k2 = runtime_ident()
    v1 = runtime_payload()
    v2 = runtime_payload()
    expression = f"{k1}.{k2}"
    parsed = require_search_value(compile_expression(expression))
    first = require_search_value(search_parsed(parsed, {k1: {k2: v1}}))
    second = require_search_value(search_parsed(parsed, {k1: {k2: v2}}))
    print(f"runtime_reuse {v1!r} then {v2!r}", flush=True)
    assert first == v1
    assert second == v2
    assert first != second


# ---------------------------------------------------------------------------
# C. Two entries agree
# ---------------------------------------------------------------------------


def test_oneshot_equals_compile_then_search_foo_bar():
    _require_oneshot_equals("foo.bar", _FOO_BAR_DOC, "baz")


def test_oneshot_equals_compile_then_search_foo_bar_index_zero():
    _require_oneshot_equals("foo.bar[0]", _FOO_BAR_INDEX_DOC, "one")


def test_oneshot_equals_compile_then_search_runtime_path():
    k1 = runtime_ident()
    k2 = runtime_ident()
    payload = runtime_payload()
    _require_oneshot_equals(f"{k1}.{k2}", {k1: {k2: payload}}, payload)


def test_oneshot_equals_compile_then_search_runtime_index_zero():
    k1 = runtime_ident()
    k2 = runtime_ident()
    first = runtime_payload()
    second = runtime_payload()
    document = {k1: {k2: [first, second]}}
    _require_oneshot_equals(f"{k1}.{k2}[0]", document, first)


# ---------------------------------------------------------------------------
# D. Missing path is successful null
# ---------------------------------------------------------------------------


def test_missing_continuation_and_missing_field_are_successful_null():
    baseline = require_search_value(oneshot_search("foo.bar.baz", _CORRECT_DOC))
    assert baseline == "correct"
    require_successful_null(oneshot_search("foo.bar.baz.bad", _CORRECT_DOC))
    require_successful_null(oneshot_search("bad", _CORRECT_DOC))


def test_missing_on_empty_object_succeeds_as_null():
    result = oneshot_search("missing", _EMPTY_OBJECT)
    value = require_search_value(result)
    assert result.exception is None
    assert value is None
    assert_successful_null(result)


def test_identifier_on_array_is_null_not_an_element():
    found = require_search_value(oneshot_search("one", {"one": "found"}))
    assert found == "found"
    require_successful_null(oneshot_search("one", ["one", "two", "three"]))


def test_compiled_missing_path_is_successful_null():
    parsed = require_search_value(compile_expression("foo.bar.baz.bad"))
    result = search_parsed(parsed, _CORRECT_DOC)
    value = require_search_value(result)
    assert result.exception is None
    assert value is None
    assert_successful_null(result)


def test_runtime_missing_segment_is_successful_null():
    k1 = runtime_ident()
    k2 = runtime_ident()
    extra = runtime_ident()
    payload = runtime_payload()
    present = {k1: {k2: {extra: payload}}}
    absent = {k1: {k2: {}}}
    expression = f"{k1}.{k2}.{extra}"
    live = require_search_value(oneshot_search(expression, present))
    assert live == payload
    require_successful_null(oneshot_search(expression, absent))


# ---------------------------------------------------------------------------
# E. Zero-length is the empty-expression value error
# ---------------------------------------------------------------------------


def test_empty_expression_search_is_value_error():
    """Zero-length search is the empty-expression value error (F01-cap-05).

    The observer can tell this failure apart from a successful null
    (``missing`` on ``{}``), from a syntax failure on ``foo.``, and from
    an incomplete-expression failure on ``(``. Neither entry yields a
    document value or a successful none.
    """
    document = sentinel_document()
    result = oneshot_search("", document)
    print(
        f"empty_search exception={result.exception!r} value={result.value!r}",
        flush=True,
    )
    assert result.exception is not None, (
        "zero-length expression must not succeed "
        f"(value={result.value!r})"
    )
    assert result.value is not document
    empty = assert_search_is_value_error("", document)

    null_result = oneshot_search("missing", _EMPTY_OBJECT)
    null_value = require_search_value(null_result)
    assert null_result.exception is None
    assert null_value is None
    print("empty_vs_successful_null: missing on {} is successful none", flush=True)

    syntax = assert_search_is_value_error("foo.", document)
    incomplete = assert_search_is_value_error("(", document)
    assert_kind_markers_differ(empty, incomplete)
    assert_kind_markers_differ(empty, syntax)
    assert_kind_markers_differ(incomplete, syntax)


def test_empty_kind_distinct_from_null_syntax_and_incomplete():
    null_result = oneshot_search("missing", _EMPTY_OBJECT)
    null_value = require_search_value(null_result)
    assert null_result.exception is None
    assert null_value is None
    empty = assert_search_is_value_error("", _EMPTY_OBJECT)
    syntax = assert_search_is_value_error("foo.", _EMPTY_OBJECT)
    incomplete = assert_search_is_value_error("(", _EMPTY_OBJECT)
    assert_kind_markers_differ(empty, incomplete)
    assert_kind_markers_differ(empty, syntax)
    assert_kind_markers_differ(incomplete, syntax)


def test_zero_length_compile_is_empty_value_error():
    empty = assert_compile_is_value_error("")
    syntax = assert_compile_is_value_error("foo.")
    incomplete = assert_compile_is_value_error("(")
    assert_kind_markers_differ(empty, incomplete)
    assert_kind_markers_differ(empty, syntax)
    assert_kind_markers_differ(incomplete, syntax)


# ---------------------------------------------------------------------------
# F. Whitespace-only is not the empty kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("expression", _WHITESPACE_ONLY, ids=repr)
def test_whitespace_only_search_is_incomplete_not_empty(expression: str):
    document = sentinel_document()
    observed = assert_search_is_value_error(expression, document)
    empty = assert_search_is_value_error("", document)
    syntax = assert_search_is_value_error("foo.", document)
    incomplete = assert_search_is_value_error("(", document)
    assert_shares_incomplete_kind_not_syntax_or_empty(
        observed, empty, incomplete, syntax
    )

    compiled = assert_compile_is_value_error(expression)
    compile_empty = assert_compile_is_value_error("")
    compile_syntax = assert_compile_is_value_error("foo.")
    compile_incomplete = assert_compile_is_value_error("(")
    assert_shares_incomplete_kind_not_syntax_or_empty(
        compiled, compile_empty, compile_incomplete, compile_syntax
    )


def test_whitespace_only_compile_is_incomplete_not_empty():
    observed = assert_compile_is_value_error(" ")
    empty = assert_compile_is_value_error("")
    syntax = assert_compile_is_value_error("foo.")
    incomplete = assert_compile_is_value_error("(")
    assert_shares_incomplete_kind_not_syntax_or_empty(
        observed, empty, incomplete, syntax
    )


def test_tab_only_compile_is_incomplete_not_empty():
    observed = assert_compile_is_value_error("\t")
    empty = assert_compile_is_value_error("")
    syntax = assert_compile_is_value_error("foo.")
    incomplete = assert_compile_is_value_error("(")
    assert_shares_incomplete_kind_not_syntax_or_empty(
        observed, empty, incomplete, syntax
    )


# ---------------------------------------------------------------------------
# G. Ill-formed expressions are syntax value errors
# ---------------------------------------------------------------------------


def _illformed_row_id(expression: str) -> str:
    if expression == _UNCLOSED_QUOTE:
        return "unclosed-quote"
    if expression == _UNCLOSED_BACKTICK:
        return "unclosed-backtick"
    if expression == _UNCLOSED_RAW_STRING:
        return "unclosed-raw-string"
    if expression == _LONE_EQUALS:
        return "lone-equals"
    if expression == _LONE_HYPHEN:
        return "lone-hyphen"
    return repr(expression)


def _assert_illformed_kind(
    expression: str,
    observed: BaseException,
    empty: BaseException,
    incomplete: BaseException,
    syntax: BaseException,
) -> None:
    if expression in _MORE_SPECIFIC_SYNTAX:
        print(f"more_specific_syntax expression={expression!r}", flush=True)
        assert_handled_as_more_specific_syntax_not_foo_marker(
            observed, empty, incomplete, syntax
        )
        return
    print(f"same_way_syntax expression={expression!r}", flush=True)
    assert_shares_foo_syntax_kind_not_empty_or_incomplete(
        observed, empty, incomplete, syntax
    )


@pytest.mark.parametrize("expression", _ILLFORMED, ids=_illformed_row_id)
def test_illformed_search_is_value_error_not_successful_null(expression: str):
    document = sentinel_document()
    observed = assert_search_is_value_error(expression, document)
    empty = assert_search_is_value_error("", document)
    incomplete = assert_search_is_value_error("(", document)
    syntax = assert_search_is_value_error("foo.", document)
    _assert_illformed_kind(expression, observed, empty, incomplete, syntax)

    compiled = assert_compile_is_value_error(expression)
    compile_empty = assert_compile_is_value_error("")
    compile_incomplete = assert_compile_is_value_error("(")
    compile_syntax = assert_compile_is_value_error("foo.")
    _assert_illformed_kind(
        expression, compiled, compile_empty, compile_incomplete, compile_syntax
    )


def test_foo_bar_on_empty_object_is_successful_null_unlike_foo_dot():
    null_result = oneshot_search("foo.bar", _EMPTY_OBJECT)
    null_value = require_search_value(null_result)
    assert null_result.exception is None
    assert null_value is None
    fail = oneshot_search("foo.", _EMPTY_OBJECT)
    assert fail.exception is not None, (
        "foo. must not succeed as a search (value="
        f"{fail.value!r})"
    )
    assert_search_is_value_error("foo.", _EMPTY_OBJECT)


def test_foo_dot_and_dot_foo_are_different_places():
    document = sentinel_document()
    trailing = assert_search_is_value_error("foo.", document)
    leading = assert_search_is_value_error(".foo", document)
    empty = assert_search_is_value_error("", document)
    incomplete = assert_search_is_value_error("(", document)
    assert_shares_foo_syntax_kind_not_empty_or_incomplete(
        trailing, empty, incomplete, trailing
    )
    assert_shares_foo_syntax_kind_not_empty_or_incomplete(
        leading, empty, incomplete, trailing
    )
    assert_positions_differ(trailing, leading, "foo.", ".foo")


def test_runtime_trailing_and_leading_dot_are_different_places():
    ident = runtime_ident()
    trailing_text = f"{ident}."
    leading_text = f".{ident}"
    document = sentinel_document()
    trailing = assert_search_is_value_error(trailing_text, document)
    leading = assert_search_is_value_error(leading_text, document)
    empty = assert_search_is_value_error("", document)
    incomplete = assert_search_is_value_error("(", document)
    syntax = assert_search_is_value_error("foo.", document)
    assert_shares_foo_syntax_kind_not_empty_or_incomplete(
        trailing, empty, incomplete, syntax
    )
    assert_shares_foo_syntax_kind_not_empty_or_incomplete(
        leading, empty, incomplete, syntax
    )
    assert_positions_differ(trailing, leading, trailing_text, leading_text)


def test_compile_foo_dot_is_syntax_value_error():
    observed = assert_compile_is_value_error("foo.")
    empty = assert_compile_is_value_error("")
    incomplete = assert_compile_is_value_error("(")
    assert_kind_markers_differ(observed, empty)
    assert_kind_markers_differ(observed, incomplete)


def test_compile_foo_hyphen_bar_is_syntax_value_error():
    observed = assert_compile_is_value_error("foo-bar")
    empty = assert_compile_is_value_error("")
    incomplete = assert_compile_is_value_error("(")
    syntax = assert_compile_is_value_error("foo.")
    assert_handled_as_more_specific_syntax_not_foo_marker(
        observed, empty, incomplete, syntax
    )


# ---------------------------------------------------------------------------
# H. Incomplete expressions are not syntax or empty
# ---------------------------------------------------------------------------


def test_unmatched_open_paren_is_incomplete_not_syntax_or_empty():
    document = sentinel_document()
    observed = assert_search_is_value_error("(", document)
    syntax = assert_search_is_value_error("foo.", document)
    empty = assert_search_is_value_error("", document)
    assert_kind_markers_differ(observed, syntax)
    assert_kind_markers_differ(observed, empty)


@pytest.mark.parametrize("expression", _LONE_OPEN, ids=repr)
def test_lone_open_tokens_are_incomplete_not_syntax(expression: str):
    document = sentinel_document()
    observed = assert_search_is_value_error(expression, document)
    empty = assert_search_is_value_error("", document)
    syntax = assert_search_is_value_error("foo.", document)
    incomplete = assert_search_is_value_error("(", document)
    assert_shares_incomplete_kind_not_syntax_or_empty(
        observed, empty, incomplete, syntax
    )

    compiled = assert_compile_is_value_error(expression)
    compile_empty = assert_compile_is_value_error("")
    compile_syntax = assert_compile_is_value_error("foo.")
    compile_incomplete = assert_compile_is_value_error("(")
    assert_shares_incomplete_kind_not_syntax_or_empty(
        compiled, compile_empty, compile_incomplete, compile_syntax
    )


def test_compile_unmatched_open_paren_is_incomplete():
    observed = assert_compile_is_value_error("(")
    syntax = assert_compile_is_value_error("foo.")
    empty = assert_compile_is_value_error("")
    assert_kind_markers_differ(observed, syntax)
    assert_kind_markers_differ(observed, empty)


# ---------------------------------------------------------------------------
# I. Package imported from the source tree
# ---------------------------------------------------------------------------


def test_search_fails_when_package_not_importable():
    present = run_python(code=_SUBSTRATE_PROBE, include_product=True)
    print(
        f"present rc={present.returncode} stdout={present.stdout_text!r}",
        flush=True,
    )
    assert present.returncode == 0, (
        "search with the package on the import path must succeed: "
        f"rc={present.returncode} stderr={present.stderr_text!r}"
    )
    assert present.stdout_text.strip() == "baz"

    absent = run_python(code=_SUBSTRATE_PROBE, include_product=False)
    print(
        f"absent rc={absent.returncode} stdout={absent.stdout_text!r} "
        f"stderr={absent.stderr_text!r}",
        flush=True,
    )
    assert absent.returncode != 0, (
        "search must hard-fail when the package is not importable; "
        f"stdout={absent.stdout_text!r}"
    )
    assert "baz" not in absent.stdout_text
