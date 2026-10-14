# feature: F04
"""FP-04: refuse invalid TOML and refuse the wrong Python input type.

Assertions follow the PRD FP-04 plus the string-parse
file-object refusal named FP-03. Structural and scalar success rules
are FP-01 / FP-02; text-mode on the binary-file entry is FP-03.
"""

from __future__ import annotations

from tomlparse import TOMLDecodeError, load, loads  # noqa: F401 — public surface

from _harness import binary_buffer, text_buffer
from F01_helpers import (
    decode_error_type,
    is_mapping,
    parse_text,
    require_decode_failure,
    require_mapping,
    require_path,
    runtime_int,
    runtime_token,
)
from F02_helpers import (
    require_bool,
    require_date,
    require_inf,
    require_int,
    require_nan,
    require_str,
    unclosed,
)
from F03_helpers import parse_binary, require_type_error, utf8_source
from F04_helpers import (
    call_string_parse,
    construct_decode_error,
    formatted_report,
    recover_column,
    recover_document,
    recover_line,
    recover_offset,
    recover_reason,
    require_end_distinct_from_interior,
    require_end_of_document_place,
    require_interior_place,
    require_same_recovered_place,
)

_NAMED_INVALID = "]] this is invalid TOML [["
_NAMED_VAL_DOT = "val=."
_NAMED_LONE_DOT = "."
_NAMED_FWFW = "fwfw="
_NAMED_UNCLOSED_BASIC = 'v = "abc'
_NAMED_UNCLOSED_ARRAY = "arr = [1"
_NAMED_UNCLOSED_INLINE = "t = { a = 1"
_NAMED_MISSING_COMMA_ARRAY = "arr = [1 2]"
_NAMED_MISSING_COMMA_INLINE = "{ a = 1 b = 2 }"
_NAMED_DUPLICATE = "a = 1\na = 2"
_NAMED_BYTES_TEXT = "v = 1"
_NAMED_CONSTRUCT_REASON = "error parsing"
_NAMED_CONSTRUCT_DOC = "v=1\n[table]\nv='val'"
_NAMED_CONSTRUCT_OFFSET = 13
_NAMED_CONSTRUCT_LINE = 3
_NAMED_CONSTRUCT_COLUMN = 2
_NAMED_OVERWRITE = "a = 1\n[a.b.c.d]"
_NAMED_FROZEN_MUTATION = "a = { b = 1 }\na.b = 2"
_NAMED_ILLEGAL_INT = "k = 01"
_NAMED_ILLEGAL_DATE = "k = 1988-02-30"
_NAMED_ILLEGAL_ESCAPE = 'k = "\\q"'


def _assert_no_mapping(result) -> None:
    if result.value is not None:
        assert not is_mapping(result.value), (
            f"invalid input still yielded a document mapping: {result.value!r}"
        )


def _refuse_invalid(source: str):
    print(f"refuse source={source!r}", flush=True)
    result = parse_text(source)
    exc = require_decode_failure(result)
    _assert_no_mapping(result)
    assert isinstance(exc, ValueError), (
        f"decode error is not a value error: {type(exc).__name__}: {exc!r}"
    )
    assert not isinstance(exc, TypeError), (
        f"decode error is a type error: {exc!r}"
    )
    assert not isinstance(exc, RecursionError), (
        f"decode error is a recursion error: {exc!r}"
    )
    print(
        f"decode error type={type(exc).__name__} report={formatted_report(exc)!r}",
        flush=True,
    )
    return exc


def _neighbor(source: str):
    print(f"neighbor source={source!r}", flush=True)
    mapping = require_mapping(parse_text(source))
    print(f"neighbor keys={list(mapping)}", flush=True)
    return mapping


def _assert_separate_from_report(exc) -> None:
    """Recover reason, document, offset, line, and column independently.

    The PRD requires those fields to be recoverable separately from the
    formatted report (independent access). They do not require the unformatted
    reason string to differ from ``str(exc)``.
    """
    reason = recover_reason(exc)
    document = recover_document(exc)
    offset = recover_offset(exc)
    line = recover_line(exc)
    column = recover_column(exc)
    report = formatted_report(exc)
    print(
        f"recovered reason={reason!r} document={document!r} offset={offset} "
        f"line={line} column={column} report={report!r}",
        flush=True,
    )


def _binary_refuse_buffer(source: str):
    data = utf8_source(source)
    print(f"binary buffer refuse bytes={data!r}", flush=True)
    result = parse_binary(binary_buffer(data))
    exc = require_decode_failure(result)
    _assert_no_mapping(result)
    assert not isinstance(exc, TypeError), (
        f"binary invalid TOML was a type error: {exc!r}"
    )
    print(
        f"binary buffer decode error type={type(exc).__name__} "
        f"report={formatted_report(exc)!r}",
        flush=True,
    )
    return exc


def _binary_neighbor_buffer(source: str):
    print(f"binary buffer neighbor source={source!r}", flush=True)
    result = parse_binary(binary_buffer(utf8_source(source)))
    mapping = require_mapping(result)
    print(f"binary buffer neighbor keys={list(mapping)}", flush=True)
    return mapping


def _binary_refuse_disk(ws, relpath: str, source: str):
    data = utf8_source(source)
    print(f"binary disk {relpath!r} refuse bytes={data!r}", flush=True)
    with ws.binary_source(relpath, data) as fp:
        result = parse_binary(fp)
    exc = require_decode_failure(result)
    _assert_no_mapping(result)
    assert not isinstance(exc, TypeError), (
        f"binary invalid TOML was a type error: {exc!r}"
    )
    print(
        f"binary disk decode error type={type(exc).__name__} "
        f"report={formatted_report(exc)!r}",
        flush=True,
    )
    return exc


def _binary_neighbor_disk(ws, relpath: str, source: str):
    print(f"binary disk {relpath!r} neighbor source={source!r}", flush=True)
    with ws.binary_source(relpath, utf8_source(source)) as fp:
        result = parse_binary(fp)
    mapping = require_mapping(result)
    print(f"binary disk neighbor keys={list(mapping)}", flush=True)
    return mapping


def _assert_type_error(result):
    exc = require_type_error(result)
    _assert_no_mapping(result)
    assert isinstance(exc, TypeError), (
        f"expected a type error, got {type(exc).__name__}: {exc!r}"
    )
    assert not isinstance(exc, decode_error_type()), (
        f"type error is a decode error: {exc!r}"
    )
    print(f"type error type={type(exc).__name__}", flush=True)
    return exc


# ---------------------------------------------------------------------------
# A. Invalid document: decode error ∩ value error, no mapping
# ---------------------------------------------------------------------------


class TestInvalidDocument:
    """invalid TOML fails as the decode error, a kind of value error."""

    def test_named_invalid_brackets_are_decode_error(self):
        neighbor = _neighbor("one = 1")
        require_int(require_path(neighbor, "one"), 1)
        exc = _refuse_invalid(_NAMED_INVALID)
        assert isinstance(exc, decode_error_type())
        assert isinstance(exc, ValueError)
        bytes_result = call_string_parse(utf8_source(_NAMED_BYTES_TEXT))
        type_exc = _assert_type_error(bytes_result)
        assert not isinstance(type_exc, decode_error_type())
        assert type(exc) is not type(type_exc)
        caught_as_decode = isinstance(type_exc, decode_error_type())
        assert not caught_as_decode, (
            "a caller who handles only the decode error would catch this type error"
        )

    def test_runtime_invalid_statement_is_decode_error(self):
        token = runtime_token()
        n = runtime_int()
        neighbor = _neighbor(f"{token} = {n}")
        require_int(require_path(neighbor, token), n)
        exc = _refuse_invalid(f"]] {token} [[")
        assert isinstance(exc, decode_error_type())
        assert isinstance(exc, ValueError)
        print(
            f"runtime invalid statement token={token!r} "
            f"type={type(exc).__name__}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# B. Interior place: 1-based line/column; five fields vs formatted report
# ---------------------------------------------------------------------------


def test_val_dot_is_interior_decode_error():
    neighbor = _neighbor("val=1")
    require_int(require_path(neighbor, "val"), 1)
    exc = _refuse_invalid(_NAMED_VAL_DOT)
    require_interior_place(exc, _NAMED_VAL_DOT)
    _assert_separate_from_report(exc)


def test_interior_line_shifts_with_leading_newlines():
    base = _NAMED_VAL_DOT
    shifted = "\n\n" + base
    base_exc = _refuse_invalid(base)
    shifted_exc = _refuse_invalid(shifted)
    require_interior_place(base_exc, base)
    require_interior_place(shifted_exc, shifted)
    base_line = recover_line(base_exc)
    shifted_line = recover_line(shifted_exc)
    print(f"line base={base_line} shifted={shifted_line}", flush=True)
    assert base_line == 1, (
        f"expected line 1 for {_NAMED_VAL_DOT!r}, got {base_line}"
    )
    assert shifted_line == 3, (
        f"two leading line feeds must yield line 3, got {shifted_line}"
    )


def test_interior_column_shifts_with_leading_spaces():
    base = _NAMED_VAL_DOT
    shifted = "  " + base
    base_exc = _refuse_invalid(base)
    shifted_exc = _refuse_invalid(shifted)
    require_interior_place(base_exc, base)
    require_interior_place(shifted_exc, shifted)
    base_col = recover_column(base_exc)
    shifted_col = recover_column(shifted_exc)
    print(f"column base={base_col} shifted={shifted_col}", flush=True)
    assert shifted_col > base_col, (
        f"leading spaces did not increase column: {base_col} vs {shifted_col}"
    )


def test_lone_dot_is_interior_decode_error():
    neighbor = _neighbor("k = 1")
    require_int(require_path(neighbor, "k"), 1)
    exc = _refuse_invalid(_NAMED_LONE_DOT)
    require_interior_place(exc, _NAMED_LONE_DOT)


def test_runtime_dot_value_is_interior_decode_error():
    token = runtime_token()
    n = runtime_int()
    neighbor = _neighbor(f"{token} = {n}")
    require_int(require_path(neighbor, token), n)
    source = f"{token}=."
    exc = _refuse_invalid(source)
    require_interior_place(exc, source)
    _assert_separate_from_report(exc)


def test_runtime_dot_line_shifts_with_leading_newlines():
    token = runtime_token()
    base = f"{token}=."
    shifted = "\n\n" + base
    base_exc = _refuse_invalid(base)
    shifted_exc = _refuse_invalid(shifted)
    require_interior_place(base_exc, base)
    require_interior_place(shifted_exc, shifted)
    base_line = recover_line(base_exc)
    shifted_line = recover_line(shifted_exc)
    print(f"runtime line base={base_line} shifted={shifted_line}", flush=True)
    assert base_line == 1, (
        f"expected line 1 for {base!r}, got {base_line}"
    )
    assert shifted_line == 3, (
        f"two leading line feeds must yield line 3, got {shifted_line}"
    )


def test_runtime_dot_column_shifts_with_leading_spaces():
    token = runtime_token()
    base = f"{token}=."
    shifted = "  " + base
    base_exc = _refuse_invalid(base)
    shifted_exc = _refuse_invalid(shifted)
    require_interior_place(base_exc, base)
    require_interior_place(shifted_exc, shifted)
    base_col = recover_column(base_exc)
    shifted_col = recover_column(shifted_exc)
    print(f"runtime column base={base_col} shifted={shifted_col}", flush=True)
    assert shifted_col > base_col, (
        f"runtime leading spaces did not increase column: "
        f"{base_col} vs {shifted_col}"
    )


# ---------------------------------------------------------------------------
# C. End of document vs interior
# ---------------------------------------------------------------------------


def test_fwfw_equals_is_end_of_document():
    neighbor = _neighbor("fwfw = 1")
    require_int(require_path(neighbor, "fwfw"), 1)
    exc = _refuse_invalid(_NAMED_FWFW)
    require_end_of_document_place(exc, _NAMED_FWFW)
    assert recover_document(exc) == _NAMED_FWFW


def test_end_of_document_distinct_from_interior_dot():
    end_exc = _refuse_invalid(_NAMED_FWFW)
    interior_exc = _refuse_invalid(_NAMED_VAL_DOT)
    require_end_distinct_from_interior(
        end_exc, _NAMED_FWFW, interior_exc, _NAMED_VAL_DOT
    )
    prefixed_end = "\n\n" + _NAMED_FWFW
    prefixed_interior = "\n\n" + _NAMED_VAL_DOT
    prefixed_end_exc = _refuse_invalid(prefixed_end)
    prefixed_interior_exc = _refuse_invalid(prefixed_interior)
    require_end_distinct_from_interior(
        prefixed_end_exc, prefixed_end, prefixed_interior_exc, prefixed_interior
    )


# ---------------------------------------------------------------------------
# D. Caller-constructed decode error
# ---------------------------------------------------------------------------


def test_constructed_offset_13_is_line_3_column_2():
    exc = construct_decode_error(
        _NAMED_CONSTRUCT_REASON,
        _NAMED_CONSTRUCT_DOC,
        _NAMED_CONSTRUCT_OFFSET,
    )
    assert isinstance(exc, decode_error_type())
    assert isinstance(exc, ValueError)
    assert recover_reason(exc) == _NAMED_CONSTRUCT_REASON
    assert recover_document(exc) == _NAMED_CONSTRUCT_DOC
    assert recover_offset(exc) == _NAMED_CONSTRUCT_OFFSET
    line = recover_line(exc)
    column = recover_column(exc)
    print(f"constructed line={line} column={column}", flush=True)
    assert line == _NAMED_CONSTRUCT_LINE, (
        f"expected line {_NAMED_CONSTRUCT_LINE}, got {line}"
    )
    assert column == _NAMED_CONSTRUCT_COLUMN, (
        f"expected column {_NAMED_CONSTRUCT_COLUMN}, got {column}"
    )
    _assert_separate_from_report(exc)
    zero = construct_decode_error(
        _NAMED_CONSTRUCT_REASON, _NAMED_CONSTRUCT_DOC, 0
    )
    assert recover_reason(zero) == _NAMED_CONSTRUCT_REASON
    assert recover_document(zero) == _NAMED_CONSTRUCT_DOC
    assert recover_offset(zero) == 0
    zero_line = recover_line(zero)
    zero_column = recover_column(zero)
    print(
        f"constructed offset-0 line={zero_line} column={zero_column}",
        flush=True,
    )
    assert zero_line == 1, f"offset 0 must be line 1, got {zero_line}"
    assert zero_column == 1, f"offset 0 must be column 1, got {zero_column}"


def test_constructed_offset_zero_is_line_1_column_1():
    exc = construct_decode_error(
        _NAMED_CONSTRUCT_REASON, _NAMED_CONSTRUCT_DOC, 0
    )
    assert isinstance(exc, decode_error_type())
    assert recover_reason(exc) == _NAMED_CONSTRUCT_REASON
    assert recover_document(exc) == _NAMED_CONSTRUCT_DOC
    assert recover_offset(exc) == 0
    line = recover_line(exc)
    column = recover_column(exc)
    print(f"offset-zero line={line} column={column}", flush=True)
    assert line == 1, f"offset 0 must be line 1, got {line}"
    assert column == 1, f"offset 0 must be column 1, got {column}"


def test_constructed_offset_across_newline_increases_line():
    first = runtime_token()
    second = runtime_token()
    reason = runtime_token()
    document = f"{first}\n{second}"
    before_offset = len(first) - 1
    after_offset = len(first) + 1
    before = construct_decode_error(reason, document, before_offset)
    after = construct_decode_error(reason, document, after_offset)
    assert isinstance(before, decode_error_type())
    assert isinstance(after, decode_error_type())
    assert recover_reason(before) == reason
    assert recover_reason(after) == reason
    assert recover_document(before) == document
    assert recover_document(after) == document
    before_line = recover_line(before)
    after_line = recover_line(after)
    print(
        f"construct across newline before_line={before_line} "
        f"after_line={after_line} before_off={before_offset} "
        f"after_off={after_offset}",
        flush=True,
    )
    assert before_line == 1, (
        f"offset before the line feed must be line 1, got {before_line}"
    )
    assert after_line == 2, (
        f"offset after the line feed must be line 2, got {after_line}"
    )


# ---------------------------------------------------------------------------
# E. Named invalid constructs
# ---------------------------------------------------------------------------


def test_unclosed_basic_string_is_decode_error():
    neighbor = _neighbor('v = "abc"')
    require_str(require_path(neighbor, "v"), "abc")
    _refuse_invalid(_NAMED_UNCLOSED_BASIC)
    key = runtime_token()
    body = runtime_token()
    closed = _neighbor(f'{key} = "{body}"')
    require_str(require_path(closed, key), body)
    _refuse_invalid(unclosed("basic", body, key=key))


def test_unclosed_literal_string_is_decode_error():
    key = runtime_token()
    body = runtime_token()
    neighbor = _neighbor(f"{key} = '{body}'")
    require_str(require_path(neighbor, key), body)
    _refuse_invalid(unclosed("literal", body, key=key))


def test_unclosed_multiline_strings_are_decode_error():
    key_basic = runtime_token()
    body_basic = runtime_token()
    neighbor_basic = _neighbor(f'{key_basic} = """{body_basic}"""')
    require_str(require_path(neighbor_basic, key_basic), body_basic)
    _refuse_invalid(unclosed("multiline_basic", body_basic, key=key_basic))
    key_lit = runtime_token()
    body_lit = runtime_token()
    neighbor_lit = _neighbor(f"{key_lit} = '''{body_lit}'''")
    require_str(require_path(neighbor_lit, key_lit), body_lit)
    _refuse_invalid(unclosed("multiline_literal", body_lit, key=key_lit))


def test_unclosed_array_is_decode_error():
    neighbor = _neighbor("arr = [1]")
    seq = require_path(neighbor, "arr")
    assert len(seq) == 1, f"neighbor arr length {len(seq)}"
    require_int(seq[0], 1)
    _refuse_invalid(_NAMED_UNCLOSED_ARRAY)
    key = runtime_token()
    n = runtime_int()
    closed = _neighbor(f"{key} = [{n}]")
    require_int(require_path(closed, key)[0], n)
    _refuse_invalid(f"{key} = [{n}")


def test_unclosed_inline_table_is_decode_error():
    neighbor = _neighbor("t = { a = 1 }")
    require_int(require_path(neighbor, "t", "a"), 1)
    _refuse_invalid(_NAMED_UNCLOSED_INLINE)
    key = runtime_token()
    inner = runtime_token()
    n = runtime_int()
    closed = _neighbor(f"{key} = {{ {inner} = {n} }}")
    require_int(require_path(closed, key, inner), n)
    _refuse_invalid(f"{key} = {{ {inner} = {n}")


def test_missing_comma_in_array_is_decode_error():
    neighbor = _neighbor("arr = [1, 2]")
    seq = require_path(neighbor, "arr")
    require_int(seq[0], 1)
    require_int(seq[1], 2)
    named_exc = _refuse_invalid(_NAMED_MISSING_COMMA_ARRAY)
    require_interior_place(named_exc, _NAMED_MISSING_COMMA_ARRAY)
    key = runtime_token()
    left = runtime_token()
    right = runtime_token()
    closed = _neighbor(f'{key} = ["{left}", "{right}"]')
    require_str(require_path(closed, key)[0], left)
    require_str(require_path(closed, key)[1], right)
    runtime_source = f'{key} = ["{left}" "{right}"]'
    runtime_exc = _refuse_invalid(runtime_source)
    require_interior_place(runtime_exc, runtime_source)


def test_missing_comma_in_inline_table_is_decode_error():
    neighbor = _neighbor("t = { a = 1, b = 2 }")
    require_int(require_path(neighbor, "t", "a"), 1)
    require_int(require_path(neighbor, "t", "b"), 2)
    named_source = "t = " + _NAMED_MISSING_COMMA_INLINE
    named_exc = _refuse_invalid(named_source)
    require_interior_place(named_exc, named_source)
    key = runtime_token()
    left_k = runtime_token()
    right_k = runtime_token()
    left_v = runtime_token()
    right_v = runtime_token()
    closed = _neighbor(
        f'{key} = {{ {left_k} = "{left_v}", {right_k} = "{right_v}" }}'
    )
    require_str(require_path(closed, key, left_k), left_v)
    require_str(require_path(closed, key, right_k), right_v)
    runtime_source = (
        f'{key} = {{ {left_k} = "{left_v}" {right_k} = "{right_v}" }}'
    )
    runtime_exc = _refuse_invalid(runtime_source)
    require_interior_place(runtime_exc, runtime_source)


def test_unclosed_table_header_is_decode_error():
    neighbor = _neighbor("[tbl]\nk = 1")
    require_int(require_path(neighbor, "tbl", "k"), 1)
    _refuse_invalid("[tbl")
    token = runtime_token()
    n = runtime_int()
    closed = _neighbor(f"[{token}]\nk = {n}")
    require_int(require_path(closed, token, "k"), n)
    _refuse_invalid(f"[{token}")


def test_unclosed_array_of_tables_header_is_decode_error():
    neighbor = _neighbor("[[arr]]\nk = 1")
    require_int(require_path(neighbor, "arr")[0]["k"], 1)
    _refuse_invalid("[[arr")
    token = runtime_token()
    n = runtime_int()
    closed = _neighbor(f"[[{token}]]\nk = {n}")
    require_int(require_path(closed, token)[0]["k"], n)
    _refuse_invalid(f"[[{token}")


def test_form_feed_in_comment_is_decode_error():
    neighbor = _neighbor("k = 1 #\t")
    require_int(require_path(neighbor, "k"), 1)
    source = "k = 1 #\x0c"
    exc = _refuse_invalid(source)
    require_interior_place(exc, source)
    key = runtime_token()
    n = runtime_int()
    note = runtime_token()
    runtime_neighbor = _neighbor(f"{key} = {n} #\t{note}")
    require_int(require_path(runtime_neighbor, key), n)
    runtime_source = f"{key} = {n} #{note}\x0c"
    runtime_exc = _refuse_invalid(runtime_source)
    require_interior_place(runtime_exc, runtime_source)


def test_wrong_case_booleans_are_decode_error():
    true_n = _neighbor("k = true")
    require_bool(require_path(true_n, "k"), True)
    false_n = _neighbor("k = false")
    require_bool(require_path(false_n, "k"), False)
    true_exc = _refuse_invalid("k = True")
    require_interior_place(true_exc, "k = True")
    _refuse_invalid("k = FALSE")
    _refuse_invalid("k = False")
    key = runtime_token()
    runtime_n = _neighbor(f"{key} = true")
    require_bool(require_path(runtime_n, key), True)
    _refuse_invalid(f"{key} = True")


def test_mixed_case_inf_nan_are_decode_error():
    inf_n = _neighbor("k = inf")
    require_inf(require_path(inf_n, "k"), negative=False)
    nan_n = _neighbor("k = nan")
    require_nan(require_path(nan_n, "k"))
    plus_n = _neighbor("k = +inf")
    require_inf(require_path(plus_n, "k"), negative=False)
    minus_n = _neighbor("k = -nan")
    require_nan(require_path(minus_n, "k"))
    for token in ("Inf", "INF", "iNf", "NaN", "Nan", "+Inf"):
        _refuse_invalid(f"k = {token}")
    key = runtime_token()
    runtime_n = _neighbor(f"{key} = inf")
    require_inf(require_path(runtime_n, key), negative=False)
    _refuse_invalid(f"{key} = Inf")


def test_duplicate_keys_are_decode_error():
    neighbor = _neighbor("a = 1")
    require_int(require_path(neighbor, "a"), 1)
    _refuse_invalid(_NAMED_DUPLICATE)
    key = runtime_token()
    n = runtime_int()
    m = runtime_int()
    closed = _neighbor(f"{key} = {n}")
    require_int(require_path(closed, key), n)
    _refuse_invalid(f"{key} = {n}\n{key} = {m}")


# ---------------------------------------------------------------------------
# F. Binary-file entry: invalid UTF-8 TOML is decode error
# ---------------------------------------------------------------------------


def test_binary_val_dot_is_decode_error(isolated_ws):
    key = runtime_token()
    n = runtime_int()
    _binary_neighbor_disk(isolated_ws, "ok.toml", f"{key} = {n}")
    string_exc = _refuse_invalid(_NAMED_VAL_DOT)
    bin_exc = _binary_refuse_disk(isolated_ws, "val-dot.toml", _NAMED_VAL_DOT)
    require_interior_place(bin_exc, _NAMED_VAL_DOT)
    require_same_recovered_place(string_exc, bin_exc)
    assert recover_document(bin_exc) == _NAMED_VAL_DOT
    assert not isinstance(recover_document(bin_exc), (bytes, bytearray))


def test_binary_buffer_val_dot_is_decode_error():
    key = runtime_token()
    n = runtime_int()
    _binary_neighbor_buffer(f"{key} = {n}")
    string_exc = _refuse_invalid(_NAMED_VAL_DOT)
    bin_exc = _binary_refuse_buffer(_NAMED_VAL_DOT)
    require_interior_place(bin_exc, _NAMED_VAL_DOT)
    require_same_recovered_place(string_exc, bin_exc)


def test_binary_named_invalid_brackets_is_decode_error():
    key = runtime_token()
    n = runtime_int()
    _binary_neighbor_buffer(f"{key} = {n}")
    _binary_refuse_buffer(_NAMED_INVALID)


def test_binary_unclosed_basic_string_is_decode_error():
    key = runtime_token()
    n = runtime_int()
    _binary_neighbor_buffer(f"{key} = {n}")
    _binary_refuse_buffer(_NAMED_UNCLOSED_BASIC)


def test_binary_duplicate_keys_is_decode_error():
    key = runtime_token()
    n = runtime_int()
    _binary_neighbor_buffer(f"{key} = {n}")
    _binary_refuse_buffer(_NAMED_DUPLICATE)


def test_binary_runtime_dot_is_decode_error():
    token = runtime_token()
    n = runtime_int()
    _binary_neighbor_buffer(f"{token} = {n}")
    source = f"{token}=."
    exc = _binary_refuse_buffer(source)
    require_interior_place(exc, source)
    assert recover_document(exc) == source


def test_binary_interior_line_shifts_with_leading_newlines():
    token = runtime_token()
    n = runtime_int()
    _binary_neighbor_buffer(f"{token} = {n}")
    base = f"{token}=."
    shifted = "\n\n" + base
    base_exc = _binary_refuse_buffer(base)
    shifted_exc = _binary_refuse_buffer(shifted)
    require_interior_place(base_exc, base)
    require_interior_place(shifted_exc, shifted)
    base_line = recover_line(base_exc)
    shifted_line = recover_line(shifted_exc)
    print(
        f"binary line base={base_line} shifted={shifted_line}",
        flush=True,
    )
    assert base_line == 1, (
        f"expected line 1 for {base!r}, got {base_line}"
    )
    assert shifted_line == 3, (
        f"two leading line feeds must yield line 3, got {shifted_line}"
    )


# ---------------------------------------------------------------------------
# G. String-parse wrong Python type: type error, not decode error
# ---------------------------------------------------------------------------


def test_string_parse_bytes_is_type_error():
    neighbor = _neighbor(_NAMED_BYTES_TEXT)
    require_int(require_path(neighbor, "v"), 1)
    payload = utf8_source(_NAMED_BYTES_TEXT)
    print(f"string-parse bytes={payload!r}", flush=True)
    result = call_string_parse(payload)
    _assert_type_error(result)


def test_runtime_string_parse_bytes_is_type_error():
    key = runtime_token()
    n = runtime_int()
    text = f"{key} = {n}"
    neighbor = _neighbor(text)
    require_int(require_path(neighbor, key), n)
    result = call_string_parse(utf8_source(text))
    _assert_type_error(result)


def test_string_parse_boolean_is_type_error():
    neighbor = _neighbor(_NAMED_BYTES_TEXT)
    require_int(require_path(neighbor, "v"), 1)
    false_result = call_string_parse(False)
    _assert_type_error(false_result)
    true_result = call_string_parse(True)
    _assert_type_error(true_result)


def test_string_parse_file_object_is_type_error(isolated_ws):
    key = runtime_token()
    n = runtime_int()
    text = f"{key} = {n}"
    neighbor = _neighbor(text)
    require_int(require_path(neighbor, key), n)
    buffer_result = call_string_parse(text_buffer(text))
    _assert_type_error(buffer_result)
    with isolated_ws.text_source("probe.toml", text) as fp:
        disk_result = call_string_parse(fp)
    _assert_type_error(disk_result)


def test_binary_text_mode_file_is_type_error_not_decode_error(isolated_ws):
    key = runtime_token()
    n = runtime_int()
    text = f"{key} = {n}"
    neighbor = _binary_neighbor_buffer(text)
    require_int(require_path(neighbor, key), n)
    decode_exc = _binary_refuse_buffer(_NAMED_VAL_DOT)
    print(f"binary text-mode buffer source={text!r}", flush=True)
    buffer_result = parse_binary(text_buffer(text))
    type_exc = _assert_type_error(buffer_result)
    assert type(decode_exc) is not type(type_exc), (
        "text-mode type error is the same kind as a decode error"
    )
    _binary_neighbor_disk(isolated_ws, "ok.bin.toml", text)
    print(f"binary text-mode disk source={text!r}", flush=True)
    with isolated_ws.text_source("probe.txt", text) as fp:
        disk_result = parse_binary(fp)
    _assert_type_error(disk_result)


# ---------------------------------------------------------------------------
# H. Invalid TOML is the decode error, not a recursion error; extra depth unpinned
# ---------------------------------------------------------------------------


def test_recursion_error_distinct_from_decode_error():
    """``val=.`` fails as the decode error, a kind of value error.

    Nesting past the FP-01 depths is unspecified: how much farther a
    document may nest, and how a still-deeper document fails, is the
    implementer's. This test does not require RecursionError
    at extra depth.
    """
    decode_exc = _refuse_invalid(_NAMED_VAL_DOT)
    assert isinstance(decode_exc, decode_error_type())
    assert isinstance(decode_exc, ValueError)
    assert not isinstance(decode_exc, RecursionError)
    assert not isinstance(decode_exc, TypeError)


# ---------------------------------------------------------------------------
# I. FP-01 / FP-02 named conflicts fail the same way
# ---------------------------------------------------------------------------


def test_frozen_or_overwrite_is_decode_error_with_location():
    neighbor = _neighbor("a = 1")
    require_int(require_path(neighbor, "a"), 1)
    exc = _refuse_invalid(_NAMED_OVERWRITE)
    require_interior_place(exc, _NAMED_OVERWRITE)
    key = runtime_token()
    n = runtime_int()
    closed = _neighbor(f"{key} = {n}")
    require_int(require_path(closed, key), n)
    runtime_source = f"{key} = {n}\n[{key}.b.c.d]"
    runtime_exc = _refuse_invalid(runtime_source)
    require_interior_place(runtime_exc, runtime_source)
    # An array-of-tables header that would overwrite a value is placed
    # inside the document too, even as the last thing in it (FP-04).
    aot_key = runtime_token()
    aot_neighbor = _neighbor(f"{aot_key} = true")
    require_bool(require_path(aot_neighbor, aot_key), True)
    aot_source = f"{aot_key} = true\n[[{aot_key}]]"
    aot_exc = _refuse_invalid(aot_source)
    require_interior_place(aot_exc, aot_source)


def test_frozen_inline_table_mutated_afterwards_is_decode_error():
    neighbor = _neighbor("a = { b = 1 }")
    require_int(require_path(neighbor, "a", "b"), 1)
    _refuse_invalid(_NAMED_FROZEN_MUTATION)
    _refuse_invalid("a = { b = 1 }\na.c = 2")
    key = runtime_token()
    inner = runtime_token()
    extra = runtime_token()
    n = runtime_int()
    m = runtime_int()
    closed = _neighbor(f"{key} = {{ {inner} = {n} }}")
    require_int(require_path(closed, key, inner), n)
    _refuse_invalid(f"{key} = {{ {inner} = {n} }}\n{key}.{extra} = {m}")


def test_illegal_integer_is_decode_error():
    neighbor = _neighbor("k = 1")
    require_int(require_path(neighbor, "k"), 1)
    _refuse_invalid(_NAMED_ILLEGAL_INT)
    key = runtime_token()
    n = runtime_int()
    closed = _neighbor(f"{key} = {n}")
    require_int(require_path(closed, key), n)
    _refuse_invalid(f"{key} = 0{n}")


def test_illegal_date_is_decode_error():
    neighbor = _neighbor("k = 1988-02-28")
    require_date(require_path(neighbor, "k"), 1988, 2, 28)
    _refuse_invalid(_NAMED_ILLEGAL_DATE)
    key = runtime_token()
    year = 1990 + (runtime_int() % 20)
    if year == 1988:
        year = 1991
    closed = _neighbor(f"{key} = {year:04d}-02-28")
    require_date(require_path(closed, key), year, 2, 28)
    _refuse_invalid(f"{key} = {year:04d}-02-30")


def test_illegal_escape_is_decode_error():
    neighbor = _neighbor('k = "\\t"')
    require_str(require_path(neighbor, "k"), "\t")
    _refuse_invalid(_NAMED_ILLEGAL_ESCAPE)
    key = runtime_token()
    closed = _neighbor(f'{key} = "\\\\"')
    require_str(require_path(closed, key), "\\")
    _refuse_invalid(f'{key} = "\\z"')
