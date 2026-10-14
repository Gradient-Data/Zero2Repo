# feature: F05
"""FP-05: construct TOML floats with a caller-supplied converter.

Assertions follow the PRD FP-05 plus the default
Python-float construction in FP-02, the same-converter rule
on the binary-file entry, and the table/array-structure
invariance in FP-01. Illegal converter results are a value error
that is not a decode error. Decode-error location fields
and non-UTF-8 bytes are other feature points.
"""

from __future__ import annotations

from decimal import Decimal

from tomlparse import TOMLDecodeError, load, loads  # noqa: F401 — public surface

from _harness import HarnessError, binary_buffer
from F01_helpers import (
    decode_error_type,
    is_mapping,
    is_sequence,
    parse_text,
    require_decode_failure,
    require_mapping,
    require_path,
    require_sequence,
    runtime_int,
    runtime_token,
)
from F02_helpers import (
    is_float,
    require_aware_datetime,
    require_bool,
    require_date,
    require_finite_float,
    require_inf,
    require_int,
    require_naive_datetime,
    require_str,
)
from F03_helpers import parse_binary, utf8_source
from F05_helpers import (
    always_returns,
    decimal_from_text,
    parse_binary_converted,
    parse_text_converted,
    recording_converter,
    require_decimal,
    require_decimal_equal,
    require_decimal_inf,
    require_decimal_nan,
    require_illegal_converter_failure,
)

_NAMED_PRECISION = "precision-matters = 0.982492"
_NAMED_PRECISION_KEY = "precision-matters"
_NAMED_PRECISION_CHARS = "0.982492"
_NAMED_SPECIALS = (
    "val=0.1\n"
    "biggest1=inf\n"
    "biggest2=+inf\n"
    "smallest=-inf\n"
    "notnum1=nan\n"
    "notnum2=-nan\n"
    "notnum3=+nan"
)
_NAMED_INT_THEN_FLOAT = "a = 1\nb = 1.0"
_NAMED_OFFSET_DATETIME = "1979-05-27T07:32:00-08:00"
_NAMED_LOCAL_DATETIME = "1988-10-27t01:01:01"
_NAMED_F01 = "f=0.1"
_NAMED_VAL_DOT = "val=."
_RESERVED_FINITE = frozenset({"0.982492", "0.1", "1.0", "3.14", "0.123"})


class _DictSubtype(dict):
    """dict subtype used as an illegal converter payload."""


class _ListSubtype(list):
    """list subtype used as an illegal converter payload."""


def _runtime_finite_spelling() -> str:
    """Process-local finite decimal text that is not a document literal."""
    spelling = f"0.{runtime_int()}"
    if spelling in _RESERVED_FINITE:
        spelling = f"0.{runtime_int()}7"
    return spelling


def _runtime_signed_finite() -> str:
    return f"-{_runtime_finite_spelling()}"


def _runtime_underscored_finite() -> str:
    a = runtime_int() % 80 + 10
    b = runtime_int() % 80 + 10
    c = runtime_int() % 80 + 10
    d = runtime_int() % 80 + 10
    return f"{a}_{b}.{c}_{d}"


def _runtime_exponent_token() -> str:
    """Finite exponent whose characters are not the public ``3e2`` / ``3E-2``."""
    n = 4 + (runtime_int() % 6)
    m = 4 + (runtime_int() % 8)
    if n == 3 or m == 2:
        n, m = 7, 11
    token = f"{n}E-{m}"
    if str(float(token)) == token:
        token = f"{n}E{m}"
    if str(float(token)) == token:
        raise HarnessError(
            f"exponent token {token!r} equals str(float(token)); "
            "cannot observe document-character binding"
        )
    return token


def _mark_from_text(text: Any) -> tuple[str, str]:
    if not isinstance(text, str):
        raise TypeError("converter requires the token text as str")
    return ("mark", text)


def _converted_mapping(source: str, converter):
    print(
        f"converted source={source!r} converter="
        f"{getattr(converter, '__qualname__', type(converter).__name__)}",
        flush=True,
    )
    result = parse_text_converted(source, converter)
    mapping = require_mapping(result)
    print(f"converted keys={list(mapping)}", flush=True)
    return mapping


def _default_mapping(source: str):
    print(f"default source={source!r}", flush=True)
    result = parse_text(source)
    mapping = require_mapping(result)
    print(f"default keys={list(mapping)}", flush=True)
    return mapping


def _refuse_illegal(source: str, converter):
    print(
        f"illegal source={source!r} converter="
        f"{getattr(converter, '__qualname__', type(converter).__name__)}",
        flush=True,
    )
    result = parse_text_converted(source, converter)
    exc = require_illegal_converter_failure(result)
    print(f"illegal type={type(exc).__name__} value={result.value!r}", flush=True)
    return exc


def _decimal_neighbor(source: str, *path: str, spelling: str):
    mapping = _converted_mapping(source, decimal_from_text)
    require_decimal_equal(require_path(mapping, *path), spelling)
    return mapping


def _binary_converted_buffer(text: str, converter):
    data = utf8_source(text)
    print(f"binary buffer bytes={data!r}", flush=True)
    result = parse_binary_converted(binary_buffer(data), converter)
    mapping = require_mapping(result)
    print(f"binary buffer keys={list(mapping)}", flush=True)
    return mapping


def _binary_converted_disk(ws, relpath: str, text: str, converter):
    data = utf8_source(text)
    print(f"binary disk {relpath!r} bytes={data!r}", flush=True)
    with ws.binary_source(relpath, data) as fp:
        result = parse_binary_converted(fp, converter)
    mapping = require_mapping(result)
    print(f"binary disk keys={list(mapping)}", flush=True)
    return mapping


def _binary_refuse_illegal(text: str, converter):
    data = utf8_source(text)
    print(f"binary illegal bytes={data!r}", flush=True)
    result = parse_binary_converted(binary_buffer(data), converter)
    exc = require_illegal_converter_failure(result)
    print(f"binary illegal type={type(exc).__name__}", flush=True)
    return exc


def _binary_default_buffer(text: str):
    data = utf8_source(text)
    print(f"binary default buffer bytes={data!r}", flush=True)
    result = parse_binary(binary_buffer(data))
    mapping = require_mapping(result)
    print(f"binary default keys={list(mapping)}", flush=True)
    return mapping


# ---------------------------------------------------------------------------
# A / E — named finite decimal of characters; default is Python float
# ---------------------------------------------------------------------------


def test_named_precision_matters_is_decimal_of_characters():
    converted = _converted_mapping(_NAMED_PRECISION, decimal_from_text)
    value = require_path(converted, _NAMED_PRECISION_KEY)
    require_decimal_equal(value, _NAMED_PRECISION_CHARS)
    assert not is_float(value), f"converted value is still a float: {value!r}"

    default = _default_mapping(_NAMED_PRECISION)
    require_finite_float(
        require_path(default, _NAMED_PRECISION_KEY),
        float(_NAMED_PRECISION_CHARS),
    )
    print("precision-matters default is Python float; converted is decimal", flush=True)


def test_runtime_finite_float_is_decimal_of_characters():
    key = runtime_token()
    spelling = _runtime_finite_spelling()
    source = f"{key} = {spelling}"
    mapping = _converted_mapping(source, decimal_from_text)
    require_decimal_equal(require_path(mapping, key), spelling)
    assert not is_float(require_path(mapping, key))


def test_exponent_float_goes_through_decimal_converter():
    key = runtime_token()
    token = _runtime_exponent_token()
    print(f"exponent token={token!r} str_float={str(float(token))!r}", flush=True)
    mapping = _converted_mapping(f"{key} = {token}", decimal_from_text)
    require_decimal_equal(require_path(mapping, key), token)
    assert not is_float(require_path(mapping, key))


def test_signed_finite_float_is_decimal():
    key = runtime_token()
    spelling = _runtime_signed_finite()
    mapping = _converted_mapping(f"{key} = {spelling}", decimal_from_text)
    value = require_path(mapping, key)
    require_decimal(value)
    assert not is_float(value), f"signed finite stayed a float: {value!r}"
    print(f"signed spelling={spelling!r} type={type(value).__name__}", flush=True)


def test_underscored_finite_float_is_decimal():
    key = runtime_token()
    spelling = _runtime_underscored_finite()
    mapping = _converted_mapping(f"{key} = {spelling}", decimal_from_text)
    value = require_path(mapping, key)
    require_decimal(value)
    assert not is_float(value), f"underscored finite stayed a float: {value!r}"
    print(f"underscored spelling={spelling!r} type={type(value).__name__}", flush=True)


# ---------------------------------------------------------------------------
# B — special float tokens through the same converter
# ---------------------------------------------------------------------------


def test_named_special_float_tokens_are_decimals():
    from_chars = Decimal("0.1")
    from_binary = Decimal(float("0.1"))
    assert from_chars != from_binary, (
        "sample invariant failed: Decimal('0.1') equals Decimal(float('0.1'))"
    )

    mapping = _converted_mapping(_NAMED_SPECIALS, decimal_from_text)
    val = require_path(mapping, "val")
    require_decimal_equal(val, "0.1")
    assert val == from_chars
    assert val != from_binary, (
        f"val is a binary-float decimal, not the characters 0.1: {val!r}"
    )

    require_decimal_inf(require_path(mapping, "biggest1"), negative=False)
    require_decimal_inf(require_path(mapping, "biggest2"), negative=False)
    require_decimal_inf(require_path(mapping, "smallest"), negative=True)
    require_decimal_nan(require_path(mapping, "notnum1"))
    require_decimal_nan(require_path(mapping, "notnum2"))
    require_decimal_nan(require_path(mapping, "notnum3"))
    for key in (
        "val",
        "biggest1",
        "biggest2",
        "smallest",
        "notnum1",
        "notnum2",
        "notnum3",
    ):
        require_decimal(require_path(mapping, key))
        print(f"special {key} type={type(require_path(mapping, key)).__name__}", flush=True)


def test_specials_without_converter_are_python_floats():
    mapping = _default_mapping(_NAMED_SPECIALS)
    val = require_path(mapping, "val")
    require_finite_float(val, float("0.1"))
    assert is_float(val), (
        f"val without converter is not a Python float: {type(val)!r}"
    )
    biggest = require_path(mapping, "biggest1")
    require_inf(biggest, negative=False)
    assert is_float(biggest), (
        f"biggest1 without converter is not a Python float: {type(biggest)!r}"
    )
    print("specials without converter are Python floats", flush=True)


def test_runtime_special_float_token_is_decimal():
    key = runtime_token()
    mapping = _converted_mapping(f"{key} = inf", decimal_from_text)
    require_decimal_inf(require_path(mapping, key), negative=False)
    assert not is_float(require_path(mapping, key))


# ---------------------------------------------------------------------------
# C — integers are not passed through the converter
# ---------------------------------------------------------------------------


def test_named_integer_stays_int_float_becomes_decimal():
    wrapper, recorded = recording_converter(decimal_from_text)
    mapping = _converted_mapping(_NAMED_INT_THEN_FLOAT, wrapper)
    require_int(require_path(mapping, "a"), 1)
    require_decimal_equal(require_path(mapping, "b"), "1.0")
    print(f"named recorded len={len(recorded)} items={recorded!r}", flush=True)
    assert len(recorded) == 1, (
        f"expected one float token through the converter, got {len(recorded)}: "
        f"{recorded!r}"
    )


def test_runtime_integer_not_passed_through_converter():
    int_key = runtime_token()
    float_key = runtime_token()
    n = runtime_int()
    spelling = _runtime_finite_spelling()
    source = f"{int_key} = {n}\n{float_key} = {spelling}"
    wrapper, recorded = recording_converter(decimal_from_text)
    mapping = _converted_mapping(source, wrapper)
    require_int(require_path(mapping, int_key), n)
    require_decimal_equal(require_path(mapping, float_key), spelling)
    print(f"runtime recorded len={len(recorded)} items={recorded!r}", flush=True)
    assert len(recorded) == 1, (
        f"expected one float token through the converter, got {len(recorded)}: "
        f"{recorded!r}"
    )


# ---------------------------------------------------------------------------
# D — any legal callable: the bound value is the return value
# ---------------------------------------------------------------------------


def test_custom_callable_return_is_bound_value():
    key = runtime_token()
    spelling = _runtime_finite_spelling()
    source = f"{key} = {spelling}"
    mapping = _converted_mapping(source, _mark_from_text)
    bound = require_path(mapping, key)
    expected = _mark_from_text(spelling)
    print(f"bound={bound!r} expected={expected!r}", flush=True)
    assert bound == expected, (
        f"custom converter return was not bound: {bound!r} != {expected!r}"
    )


def test_tuple_return_is_allowed():
    key = runtime_token()
    spelling = _runtime_finite_spelling()
    payload = (runtime_token(), runtime_int())
    mapping = _converted_mapping(f"{key} = {spelling}", always_returns(payload))
    bound = require_path(mapping, key)
    print(f"tuple payload={payload!r} bound={bound!r}", flush=True)
    assert bound is payload, f"tuple return was not bound: {bound!r}"


def test_custom_callable_on_exponent_binds_document_text():
    key = runtime_token()
    token = _runtime_exponent_token()
    as_float = str(float(token))
    print(f"exponent token={token!r} str_float={as_float!r}", flush=True)
    assert as_float != token
    mapping = _converted_mapping(f"{key} = {token}", _mark_from_text)
    bound = require_path(mapping, key)
    expected = ("mark", token)
    print(f"bound={bound!r} expected={expected!r}", flush=True)
    assert bound == expected, (
        f"converter was not given the document characters {token!r}: {bound!r}"
    )


def test_custom_callable_on_special_token_is_bound_value():
    key = runtime_token()
    sentinel = object()

    def special_conv(text: Any) -> object:
        if not isinstance(text, str):
            raise TypeError("converter requires the token text as str")
        return sentinel

    mapping = _converted_mapping(f"{key} = inf", special_conv)
    bound = require_path(mapping, key)
    print(f"special sentinel bound={bound is sentinel}", flush=True)
    assert bound is sentinel, f"special-token converter return was not bound: {bound!r}"


# ---------------------------------------------------------------------------
# F — other scalars and table/array structure unchanged; nested floats convert
# ---------------------------------------------------------------------------


def test_non_float_scalars_and_structure_unchanged():
    float_key = runtime_token()
    spelling = _runtime_finite_spelling()
    source = (
        's = "hello"\n'
        "flag = true\n"
        "n = 1\n"
        "when = 1988-10-27\n"
        "point = { x = 1 }\n"
        "items = [1]\n"
        f"{float_key} = {spelling}"
    )
    mapping = _converted_mapping(source, decimal_from_text)
    require_str(require_path(mapping, "s"), "hello")
    require_bool(require_path(mapping, "flag"), True)
    require_int(require_path(mapping, "n"), 1)
    require_date(require_path(mapping, "when"), 1988, 10, 27)
    point = require_path(mapping, "point")
    assert is_mapping(point), f"inline table is not a mapping: {type(point)!r}"
    require_int(require_path(mapping, "point", "x"), 1)
    items = require_sequence(require_path(mapping, "items"))
    assert is_sequence(items), f"array is not a sequence: {type(items)!r}"
    assert len(items) == 1, f"array length {len(items)} != 1"
    require_int(items[0], 1)
    require_decimal_equal(require_path(mapping, float_key), spelling)
    print("non-float scalars and structure unchanged", flush=True)


def test_floats_inside_array_and_inline_table_are_converted():
    named = _converted_mapping("arr = [1, 1.0]\ninl = { x = 0.1 }", decimal_from_text)
    named_arr = require_sequence(require_path(named, "arr"))
    assert len(named_arr) == 2, f"named arr length {len(named_arr)} != 2"
    require_int(named_arr[0], 1)
    require_decimal_equal(named_arr[1], "1.0")
    assert is_mapping(require_path(named, "inl"))
    require_decimal_equal(require_path(named, "inl", "x"), "0.1")

    arr_key = runtime_token()
    inl_key = runtime_token()
    x_key = runtime_token()
    n = runtime_int()
    spelling = _runtime_finite_spelling()
    source = f"{arr_key} = [{n}, {spelling}]\n{inl_key} = {{ {x_key} = {spelling} }}"
    mapping = _converted_mapping(source, decimal_from_text)
    runtime_arr = require_sequence(require_path(mapping, arr_key))
    assert len(runtime_arr) == 2, f"runtime arr length {len(runtime_arr)} != 2"
    require_int(runtime_arr[0], n)
    require_decimal_equal(runtime_arr[1], spelling)
    assert is_mapping(require_path(mapping, inl_key))
    require_decimal_equal(require_path(mapping, inl_key, x_key), spelling)


def test_float_under_table_header_is_converted():
    header = runtime_token()
    key = runtime_token()
    spelling = _runtime_finite_spelling()
    source = f"[{header}]\n{key} = {spelling}"
    mapping = _converted_mapping(source, decimal_from_text)
    table = require_path(mapping, header)
    assert is_mapping(table), f"table header did not yield a mapping: {type(table)!r}"
    value = require_path(mapping, header, key)
    require_decimal_equal(value, spelling)
    assert not is_float(value)


def test_datetime_not_passed_through_converter():
    """A supplied converter leaves date-times as date-times.

    Offset and local date-times stay the FP-02 values. They are not built
    through the float converter. Integers, strings, booleans, tables, and
    arrays are already covered on other arms; this arm is date-times.
    """
    offset_key = runtime_token()
    local_key = runtime_token()
    float_key = runtime_token()
    spelling = _runtime_finite_spelling()
    source = (
        f"{offset_key} = {_NAMED_OFFSET_DATETIME}\n"
        f"{local_key} = {_NAMED_LOCAL_DATETIME}\n"
        f"{float_key} = {spelling}"
    )
    wrapper, recorded = recording_converter(decimal_from_text)
    converted = _converted_mapping(source, wrapper)
    default = _default_mapping(source)

    offset_converted = require_aware_datetime(require_path(converted, offset_key))
    offset_default = require_aware_datetime(require_path(default, offset_key))
    print(
        f"offset converted={offset_converted!r} default={offset_default!r}",
        flush=True,
    )
    assert offset_converted == offset_default, (
        f"supplied converter changed the offset date-time: "
        f"{offset_converted!r} != {offset_default!r}"
    )

    local_converted = require_naive_datetime(require_path(converted, local_key))
    local_default = require_naive_datetime(require_path(default, local_key))
    print(
        f"local converted={local_converted!r} default={local_default!r}",
        flush=True,
    )
    assert local_converted == local_default, (
        f"supplied converter changed the local date-time: "
        f"{local_converted!r} != {local_default!r}"
    )

    require_decimal_equal(require_path(converted, float_key), spelling)
    print(f"datetime recorded len={len(recorded)} items={recorded!r}", flush=True)
    assert len(recorded) == 1, (
        f"expected one float token through the converter, got {len(recorded)}: "
        f"{recorded!r}"
    )


# ---------------------------------------------------------------------------
# G — binary-file entry uses the same converter
# ---------------------------------------------------------------------------


def test_binary_precision_matters_is_decimal(isolated_ws):
    disk = _binary_converted_disk(
        isolated_ws, "precision.toml", _NAMED_PRECISION, decimal_from_text
    )
    disk_value = require_path(disk, _NAMED_PRECISION_KEY)
    require_decimal_equal(disk_value, _NAMED_PRECISION_CHARS)
    assert not is_float(disk_value), (
        f"binary disk precision-matters is still a float: {disk_value!r}"
    )

    buf = _binary_converted_buffer(_NAMED_PRECISION, decimal_from_text)
    buf_value = require_path(buf, _NAMED_PRECISION_KEY)
    require_decimal_equal(buf_value, _NAMED_PRECISION_CHARS)
    assert not is_float(buf_value), (
        f"binary buffer precision-matters is still a float: {buf_value!r}"
    )

    default_disk_data = utf8_source(_NAMED_PRECISION)
    with isolated_ws.binary_source("precision-default.toml", default_disk_data) as fp:
        default_result = parse_binary(fp)
    default_disk = require_mapping(default_result)
    default_disk_value = require_path(default_disk, _NAMED_PRECISION_KEY)
    require_finite_float(default_disk_value, float(_NAMED_PRECISION_CHARS))
    assert is_float(default_disk_value), (
        f"binary disk default is not a Python float: {type(default_disk_value)!r}"
    )
    default_buf = _binary_default_buffer(_NAMED_PRECISION)
    default_buf_value = require_path(default_buf, _NAMED_PRECISION_KEY)
    require_finite_float(default_buf_value, float(_NAMED_PRECISION_CHARS))
    assert is_float(default_buf_value), (
        f"binary buffer default is not a Python float: {type(default_buf_value)!r}"
    )
    print("binary precision-matters decimal vs default float", flush=True)


def test_binary_buffer_runtime_float_is_decimal():
    key = runtime_token()
    spelling = _runtime_finite_spelling()
    mapping = _binary_converted_buffer(f"{key} = {spelling}", decimal_from_text)
    value = require_path(mapping, key)
    require_decimal_equal(value, spelling)
    assert not is_float(value), (
        f"binary runtime float stayed a Python float: {value!r}"
    )


def test_binary_illegal_dict_converter_is_value_error():
    neighbor = _binary_converted_buffer(_NAMED_F01, decimal_from_text)
    require_decimal_equal(require_path(neighbor, "f"), "0.1")
    exc = _binary_refuse_illegal(_NAMED_F01, always_returns({}))
    assert isinstance(exc, ValueError)
    assert not isinstance(exc, decode_error_type())


def test_binary_illegal_list_converter_is_value_error():
    neighbor = _binary_converted_buffer(_NAMED_F01, decimal_from_text)
    require_decimal_equal(require_path(neighbor, "f"), "0.1")
    exc = _binary_refuse_illegal(_NAMED_F01, always_returns([]))
    assert isinstance(exc, ValueError)
    assert not isinstance(exc, decode_error_type())


def test_binary_inf_is_decimal():
    mapping = _binary_converted_buffer("k = inf", decimal_from_text)
    value = require_path(mapping, "k")
    require_decimal_inf(value, negative=False)
    assert not is_float(value), f"binary inf stayed a Python float: {value!r}"


def test_binary_custom_callable_return_is_bound_value():
    key = runtime_token()
    spelling = _runtime_finite_spelling()
    mapping = _binary_converted_buffer(f"{key} = {spelling}", _mark_from_text)
    bound = require_path(mapping, key)
    expected = _mark_from_text(spelling)
    print(f"binary bound={bound!r} expected={expected!r}", flush=True)
    assert bound == expected, (
        f"binary custom converter return was not bound: {bound!r} != {expected!r}"
    )


def test_binary_integer_not_passed_through_converter():
    wrapper, recorded = recording_converter(decimal_from_text)
    mapping = _binary_converted_buffer(_NAMED_INT_THEN_FLOAT, wrapper)
    require_int(require_path(mapping, "a"), 1)
    require_decimal_equal(require_path(mapping, "b"), "1.0")
    print(f"binary recorded len={len(recorded)} items={recorded!r}", flush=True)
    assert len(recorded) == 1, (
        f"expected one float token through the converter, got {len(recorded)}: "
        f"{recorded!r}"
    )


def test_binary_datetime_not_passed_through_converter():
    """Binary-file entry: a supplied converter leaves date-times as date-times."""
    dt_key = runtime_token()
    float_key = runtime_token()
    spelling = _runtime_finite_spelling()
    source = f"{dt_key} = {_NAMED_OFFSET_DATETIME}\n{float_key} = {spelling}"
    wrapper, recorded = recording_converter(decimal_from_text)
    converted = _binary_converted_buffer(source, wrapper)
    default = _binary_default_buffer(source)

    converted_dt = require_aware_datetime(require_path(converted, dt_key))
    default_dt = require_aware_datetime(require_path(default, dt_key))
    print(
        f"binary offset converted={converted_dt!r} default={default_dt!r}",
        flush=True,
    )
    assert converted_dt == default_dt, (
        f"binary supplied converter changed the date-time: "
        f"{converted_dt!r} != {default_dt!r}"
    )
    require_decimal_equal(require_path(converted, float_key), spelling)
    print(
        f"binary datetime recorded len={len(recorded)} items={recorded!r}",
        flush=True,
    )
    assert len(recorded) == 1, (
        f"expected one float token through the converter, got {len(recorded)}: "
        f"{recorded!r}"
    )


# ---------------------------------------------------------------------------
# H — dict/list (including subtypes) are a value error, not a decode error
# ---------------------------------------------------------------------------


def test_empty_dict_converter_is_value_error_not_decode_error():
    _decimal_neighbor(_NAMED_F01, "f", spelling="0.1")
    exc = _refuse_illegal(_NAMED_F01, always_returns({}))
    assert isinstance(exc, ValueError)
    assert not isinstance(exc, decode_error_type())
    assert not isinstance(exc, TypeError)
    assert not isinstance(exc, RecursionError)


def test_empty_list_converter_is_value_error_not_decode_error():
    _decimal_neighbor(_NAMED_F01, "f", spelling="0.1")
    exc = _refuse_illegal(_NAMED_F01, always_returns([]))
    assert isinstance(exc, ValueError)
    assert not isinstance(exc, decode_error_type())
    assert not isinstance(exc, TypeError)
    assert not isinstance(exc, RecursionError)


def test_dict_and_list_subtype_converters_are_value_error():
    _decimal_neighbor(_NAMED_F01, "f", spelling="0.1")
    dict_exc = _refuse_illegal(_NAMED_F01, always_returns(_DictSubtype()))
    list_exc = _refuse_illegal(_NAMED_F01, always_returns(_ListSubtype()))
    for exc in (dict_exc, list_exc):
        assert isinstance(exc, ValueError)
        assert not isinstance(exc, decode_error_type())


def test_decimal_converter_succeeds_where_dict_fails():
    ok = _converted_mapping(_NAMED_F01, decimal_from_text)
    ok_val = require_path(ok, "f")
    require_decimal_equal(ok_val, "0.1")
    assert not is_float(ok_val), f"decimal converter left f as a float: {ok_val!r}"
    exc = _refuse_illegal(_NAMED_F01, always_returns({}))
    assert isinstance(exc, ValueError)
    assert not isinstance(exc, decode_error_type()), (
        "dict converter failure is a decode error; observer cannot tell it "
        "from invalid TOML"
    )
    print("decimal converter succeeds; dict converter fails", flush=True)


def test_illegal_converter_distinct_from_invalid_toml():
    illegal_exc = _refuse_illegal(_NAMED_F01, always_returns({}))
    print(f"refuse invalid TOML source={_NAMED_VAL_DOT!r}", flush=True)
    decode_result = parse_text(_NAMED_VAL_DOT)
    decode_exc = require_decode_failure(decode_result)
    print(
        f"illegal type={type(illegal_exc).__name__} "
        f"decode type={type(decode_exc).__name__}",
        flush=True,
    )
    assert not isinstance(illegal_exc, decode_error_type()), (
        "illegal converter failure is a decode error; observer cannot tell "
        "it from invalid TOML"
    )
    assert isinstance(decode_exc, decode_error_type())
    assert isinstance(decode_exc, ValueError)
    assert decode_result.value is None or not is_mapping(decode_result.value)


def test_runtime_illegal_dict_converter_is_value_error():
    key = runtime_token()
    spelling = _runtime_finite_spelling()
    source = f"{key} = {spelling}"
    _decimal_neighbor(source, key, spelling=spelling)
    exc = _refuse_illegal(source, always_returns({}))
    assert isinstance(exc, ValueError)
    assert not isinstance(exc, decode_error_type())


def test_runtime_nonempty_dict_and_list_converters_are_value_error():
    key = runtime_token()
    spelling = _runtime_finite_spelling()
    source = f"{key} = {spelling}"
    _decimal_neighbor(source, key, spelling=spelling)
    dict_exc = _refuse_illegal(
        source, always_returns({runtime_token(): runtime_int()})
    )
    list_exc = _refuse_illegal(source, always_returns([runtime_int()]))
    for exc in (dict_exc, list_exc):
        assert isinstance(exc, ValueError)
        assert not isinstance(exc, decode_error_type())


def test_illegal_converter_inside_array_and_inline_table_is_value_error():
    arr_source = "arr = [0.1]"
    arr_ok = _converted_mapping(arr_source, decimal_from_text)
    arr = require_sequence(require_path(arr_ok, "arr"))
    assert len(arr) == 1
    require_decimal_equal(arr[0], "0.1")
    arr_exc = _refuse_illegal(arr_source, always_returns({}))
    assert isinstance(arr_exc, ValueError)
    assert not isinstance(arr_exc, decode_error_type())

    inl_source = "t = { x = 0.1 }"
    inl_ok = _converted_mapping(inl_source, decimal_from_text)
    require_decimal_equal(require_path(inl_ok, "t", "x"), "0.1")
    assert is_mapping(require_path(inl_ok, "t"))
    inl_exc = _refuse_illegal(inl_source, always_returns([]))
    assert isinstance(inl_exc, ValueError)
    assert not isinstance(inl_exc, decode_error_type())

    key = runtime_token()
    spelling = _runtime_finite_spelling()
    runtime_arr = f"{key} = [{spelling}]"
    runtime_ok = _converted_mapping(runtime_arr, decimal_from_text)
    require_decimal_equal(require_sequence(require_path(runtime_ok, key))[0], spelling)
    runtime_exc = _refuse_illegal(runtime_arr, always_returns({}))
    assert isinstance(runtime_exc, ValueError)
    assert not isinstance(runtime_exc, decode_error_type())
