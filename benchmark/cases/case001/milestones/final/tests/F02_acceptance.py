# feature: F02
"""FP-02: map TOML scalar types to native Python values.

Assertions follow the PRD FP-02. Illegal boolean,
integer, float, string, and date-time tokens fail as the
decode-error carrier in FP-04: a decode error that is a
kind of value error, with no document mapping. Table/array structure is
FP-01; the binary-file entry is FP-03; float converters are FP-05.
"""

from __future__ import annotations

import calendar
import copy
import math
from datetime import timedelta

from tomlparse import TOMLDecodeError, loads  # noqa: F401 — public string-parse surface

from F01_helpers import (
    parse_text,
    require_decode_failure,
    require_mapping,
    require_path,
    runtime_int,
    runtime_token,
)
from F02_helpers import (
    base_digit_string,
    is_bool,
    is_float,
    is_int,
    is_str,
    multiline_basic_document,
    require_aware_datetime,
    require_bool,
    require_date,
    require_finite_float,
    require_inf,
    require_int,
    require_nan,
    require_naive_datetime,
    require_str,
    require_time,
    require_utcoffset,
    unclosed,
)

_RESERVED_YMD = frozenset(
    {
        (1979, 5, 27),
        (1987, 7, 5),
        (1988, 10, 27),
        (2000, 2, 29),
        (2006, 1, 1),
        (2024, 2, 29),
        (2025, 4, 18),
    }
)
_RESERVED_HM = frozenset(
    {(1, 1), (7, 32), (10, 32), (13, 37), (17, 45), (20, 5)}
)
_LEAP_YEARS = (2004, 2008, 2012, 2016, 2028, 2032, 2036, 2040)
_NON_LEAP_YEARS = (2017, 2018, 2021, 2022, 2025, 2026, 2027, 2029)


def _scalar_mapping(source: str):
    print(f"parse source={source!r}", flush=True)
    result = parse_text(source)
    mapping = require_mapping(result)
    assert result.exception is None
    return mapping


def _refuse_scalar(source: str):
    print(f"refuse source={source!r}", flush=True)
    result = parse_text(source)
    exc = require_decode_failure(result)
    assert result.exception is not None
    return exc


def _succeeds_neighbor(source: str):
    print(f"neighbor source={source!r}", flush=True)
    result = parse_text(source)
    mapping = require_mapping(result)
    assert result.exception is None
    return mapping


def _refuse_near(bad: str, good: str):
    neighbor = _succeeds_neighbor(good)
    exc = _refuse_scalar(bad)
    assert exc is not None
    return neighbor


def _runtime_ymd():
    for _ in range(48):
        year = 1991 + (runtime_int() % 28)
        month = 1 + (runtime_int() % 12)
        day = 1 + (runtime_int() % calendar.monthrange(year, month)[1])
        if (year, month, day) not in _RESERVED_YMD:
            return year, month, day
    raise AssertionError("could not pick a runtime calendar day")


def _runtime_clock():
    for _ in range(24):
        hour = runtime_int() % 24
        minute = runtime_int() % 60
        if (hour, minute) not in _RESERVED_HM:
            return hour, minute
    raise AssertionError("could not pick a runtime clock")


def _ymd(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"


def _closed_string(form: str, text: str, *, key: str) -> str:
    if form == "basic":
        return f'{key} = "{text}"'
    if form == "literal":
        return f"{key} = '{text}'"
    if form == "multiline_basic":
        return f'{key} = """{text}"""'
    if form == "multiline_literal":
        return f"{key} = '''{text}'''"
    raise AssertionError(f"unknown string form {form!r}")


# ---------------------------------------------------------------------------
# A. Booleans
# ---------------------------------------------------------------------------


def test_true_is_boolean_not_int_or_str():
    doc = _scalar_mapping("k = true")
    value = require_path(doc, "k")
    print(f"true value={value!r} type={type(value)!r}", flush=True)
    require_bool(value, True)
    assert value is not 1
    assert not is_int(value)
    assert not is_str(value)
    assert value != "true"


def test_false_is_boolean_not_int_or_str():
    doc = _scalar_mapping("k = false")
    value = require_path(doc, "k")
    print(f"false value={value!r} type={type(value)!r}", flush=True)
    require_bool(value, False)
    assert value is not 0
    assert not is_int(value)
    assert not is_str(value)
    assert value != "false"


def test_true_contrasts_with_integer_one():
    as_bool = _scalar_mapping("k = true")
    as_int = _scalar_mapping("k = 1")
    flag = require_path(as_bool, "k")
    number = require_path(as_int, "k")
    require_bool(flag, True)
    require_int(number, 1)
    assert is_bool(flag) and not is_bool(number)
    assert is_int(number) and not is_int(flag)


def test_runtime_key_binds_booleans():
    key = runtime_token()
    yes = _scalar_mapping(f"{key} = true")
    no = _scalar_mapping(f"{key} = false")
    require_bool(require_path(yes, key), True)
    require_bool(require_path(no, key), False)
    assert key != "true" and key != "false"


# ---------------------------------------------------------------------------
# B. Four string forms
# ---------------------------------------------------------------------------


def test_basic_hello_is_string():
    doc = _scalar_mapping('k = "hello"')
    value = require_path(doc, "k")
    require_str(value, "hello")
    assert is_str(value)
    assert value == "hello"


def test_runtime_basic_string():
    token = runtime_token()
    other = runtime_token()
    assert token != "hello"
    assert other != token
    doc = _scalar_mapping(f'k = "{token}"')
    value = require_path(doc, "k")
    require_str(value, token)
    assert is_str(value)
    assert value == token
    other_doc = _scalar_mapping(f'k = "{other}"')
    other_val = require_path(other_doc, "k")
    require_str(other_val, other)
    assert other_val != value
    # Same token after a discarded opening line feed is still that token.
    multi = _scalar_mapping(multiline_basic_document("k", "\n" + token))
    multi_val = require_path(multi, "k")
    require_str(multi_val, token)
    assert multi_val == value
    assert not multi_val.startswith("\n")


def test_literal_string_keeps_backslash_sequences():
    spaced = _scalar_mapping(r"k = '\x20 \x09'")
    require_str(require_path(spaced, "k"), r"\x20 \x09")
    oracle = _scalar_mapping(r"k = '\x20'")
    require_str(require_path(oracle, "k"), "\\x20")
    four = require_path(oracle, "k")
    assert len(four) == 4
    assert list(four) == ["\\", "x", "2", "0"]


def test_basic_x20_space_vs_literal_x20_chars():
    basic = _scalar_mapping('k = "\\x20"')
    literal = _scalar_mapping(r"k = '\x20'")
    basic_val = require_path(basic, "k")
    literal_val = require_path(literal, "k")
    require_str(basic_val, " ")
    require_str(literal_val, "\\x20")
    assert basic_val != literal_val
    assert len(basic_val) == 1
    assert len(literal_val) == 4


def test_runtime_literal_keeps_interior():
    token = runtime_token()
    interior = "\\" + token
    doc = _scalar_mapping(f"k = '{interior}'")
    value = require_path(doc, "k")
    require_str(value, interior)
    assert is_str(value)
    assert "\\" in value
    assert value == interior
    # A sequence that basic would decode must stay characters in a literal.
    x_interior = token + "\\x20" + token
    x_doc = _scalar_mapping(f"k = '{x_interior}'")
    x_val = require_path(x_doc, "k")
    require_str(x_val, x_interior)
    assert x_val != token + " " + token
    assert "\\x20" in x_val
    assert list(x_val[len(token) : len(token) + 4]) == ["\\", "x", "2", "0"]


def test_multiline_basic_discards_opening_lf_keeps_later():
    token = runtime_token()
    dropped = _scalar_mapping(multiline_basic_document("k", f"\n{token}"))
    kept = _scalar_mapping(multiline_basic_document("k", f"\n\n{token}"))
    require_str(require_path(dropped, "k"), token)
    require_str(require_path(kept, "k"), "\n" + token)
    assert require_path(dropped, "k") != require_path(kept, "k")


def test_multiline_basic_keeps_first_non_lf_character():
    token = runtime_token()
    assert not token.startswith("\n")
    doc = _scalar_mapping(multiline_basic_document("k", token))
    value = require_path(doc, "k")
    require_str(value, token)
    assert value[:1] == token[:1]
    assert value != token[1:]
    assert len(value) == len(token)
    # Discarding applies only to an immediate opening line feed.
    dropped_lf = _scalar_mapping(multiline_basic_document("k", "\n" + token))
    dropped_val = require_path(dropped_lf, "k")
    require_str(dropped_val, token)
    assert dropped_val == value
    assert not dropped_val.startswith("\n")


def test_multiline_basic_line_join_backslash_lf():
    left, right = runtime_token(), runtime_token()
    joined = _scalar_mapping(multiline_basic_document("k", f"{left}\\\n{right}"))
    require_str(require_path(joined, "k"), left + right)
    kept = _scalar_mapping(multiline_basic_document("k", f"{left}\n{right}"))
    require_str(require_path(kept, "k"), left + "\n" + right)
    public = _scalar_mapping(multiline_basic_document("k", "hello\\\nworld"))
    require_str(require_path(public, "k"), "helloworld")
    assert require_path(joined, "k") != require_path(kept, "k")
    assert "\n" in require_path(kept, "k")
    assert "\n" not in require_path(joined, "k")


def test_multiline_basic_line_join_backslash_ws_lf():
    left, right = runtime_token(), runtime_token()
    body = f"{left}\\  \n{right}"
    doc = _scalar_mapping(multiline_basic_document("k", body))
    require_str(require_path(doc, "k"), left + right)
    assert " " not in require_path(doc, "k")
    assert "\n" not in require_path(doc, "k")


def test_multiline_basic_line_join_backslash_tab_lf():
    left, right = runtime_token(), runtime_token()
    body = f"{left}\\\t\n{right}"
    doc = _scalar_mapping(multiline_basic_document("k", body))
    value = require_path(doc, "k")
    require_str(value, left + right)
    between = body.split("\\", 1)[1].split("\n", 1)[0]
    assert "\t" in between
    assert " " not in between
    assert "\t" not in value
    assert "\n" not in value


def test_multiline_basic_line_join_strips_continuation_indent():
    left, right = runtime_token(), runtime_token()
    spaced = _scalar_mapping(
        multiline_basic_document("k", f"{left}\\\n    {right}")
    )
    tabbed = _scalar_mapping(
        multiline_basic_document("k", f"{left}\\\n\t{right}")
    )
    require_str(require_path(spaced, "k"), left + right)
    require_str(require_path(tabbed, "k"), left + right)
    assert " " not in require_path(spaced, "k")
    assert "\t" not in require_path(tabbed, "k")


def test_multiline_basic_trailing_ws_escape_before_lf_closer():
    token = runtime_token()
    spaces = _scalar_mapping(multiline_basic_document("k", f"{token}\\   \n"))
    require_str(require_path(spaces, "k"), token)
    padded = _scalar_mapping(
        multiline_basic_document("k", f"{token}\\   \n      ")
    )
    require_str(require_path(padded, "k"), token)
    tabs = _scalar_mapping(multiline_basic_document("k", f"{token}\\\t\t\n"))
    require_str(require_path(tabs, "k"), token)
    for value in (
        require_path(spaces, "k"),
        require_path(padded, "k"),
        require_path(tabs, "k"),
    ):
        assert value.endswith(token[-1])
        assert not value.endswith(" ")
        assert "\\" not in value


def test_multiline_basic_backslash_ws_without_lf_refused():
    token = runtime_token()
    neighbor = _succeeds_neighbor(
        multiline_basic_document("k", f"{token}\\   \n")
    )
    joined = require_path(neighbor, "k")
    require_str(joined, token)
    assert joined == token
    refused_spaces = _refuse_scalar(multiline_basic_document("k", token + "\\   "))
    refused_tab = _refuse_scalar(multiline_basic_document("k", token + "\\\t"))
    assert refused_spaces is not None
    assert refused_tab is not None


def test_multiline_literal_discards_opening_lf_no_escapes():
    token = runtime_token()
    src = f"k = '''\n\\x20{token}'''"
    doc = _scalar_mapping(src)
    kept = require_path(doc, "k")
    require_str(kept, "\\x20" + token)
    assert kept == "\\x20" + token
    later = _scalar_mapping(f"k = '''\n\n{token}'''")
    later_val = require_path(later, "k")
    require_str(later_val, "\n" + token)
    assert later_val == "\n" + token
    assert kept != later_val


def test_multiline_literal_interior_apostrophe_kept():
    left, right = runtime_token(), runtime_token()
    assert not left.startswith("\n")
    body = left + "'" + right
    doc = _scalar_mapping(f"k = '''{body}'''")
    value = require_path(doc, "k")
    require_str(value, body)
    assert value == left + "'" + right
    assert "'" in value
    assert value[len(left)] == "'"
    assert value[: len(left)] == left
    assert value[len(left) + 1 :] == right
    assert value != left + "'"
    # First content character is runtime text, not a discarded line feed.
    assert value[:1] == left[:1]
    assert value != body[1:]
    assert len(value) == len(body)
    first = _scalar_mapping(f"k = '''{left}'''")
    first_val = require_path(first, "k")
    require_str(first_val, left)
    assert first_val[:1] == left[:1]
    assert first_val != left[1:]
    # Opening line feed is discarded; the interior apostrophe is not a closer.
    dropped = _scalar_mapping(f"k = '''\n{body}'''")
    dropped_val = require_path(dropped, "k")
    require_str(dropped_val, body)
    assert dropped_val == value
    assert not dropped_val.startswith("\n")


def test_multiline_literal_four_and_five_apostrophe_close():
    token = runtime_token()
    four = _scalar_mapping(f"k = '''\n{token}''''")
    five = _scalar_mapping(f"k = '''\n{token}'''''")
    require_str(require_path(four, "k"), token + "'")
    require_str(require_path(five, "k"), token + "''")
    assert require_path(four, "k") != require_path(five, "k")


def test_multiline_basic_four_and_five_quote_close():
    token = runtime_token()
    four = _scalar_mapping(f'k = """\n{token}""""')
    five = _scalar_mapping(f'k = """\n{token}"""""')
    require_str(require_path(four, "k"), token + '"')
    require_str(require_path(five, "k"), token + '""')
    assert require_path(four, "k") != require_path(five, "k")


def test_multiline_literal_backslash_lf_is_not_a_join():
    left, right = runtime_token(), runtime_token()
    interior = f"{left}\\\n{right}"
    literal = _scalar_mapping(f"k = '''{interior}'''")
    basic = _scalar_mapping(multiline_basic_document("k", interior))
    lit_val = require_path(literal, "k")
    bas_val = require_path(basic, "k")
    require_str(lit_val, left + "\\" + "\n" + right)
    require_str(bas_val, left + right)
    print(
        f"literal keep={lit_val!r} basic join={bas_val!r}",
        flush=True,
    )
    assert "\\" in lit_val
    assert "\n" in lit_val
    assert "\n" not in bas_val
    assert "\\" not in bas_val
    assert lit_val != bas_val
    assert lit_val != left + right


# ---------------------------------------------------------------------------
# C. Basic-string escapes and quoted keys
# ---------------------------------------------------------------------------


def test_two_char_escapes_including_e():
    src = (
        'b = "\\b"\n'
        't = "\\t"\n'
        'n = "\\n"\n'
        'f = "\\f"\n'
        'r = "\\r"\n'
        'e = "\\e"\n'
        'q = "\\""\n'
        'bs = "\\\\"\n'
    )
    doc = _scalar_mapping(src)
    require_str(require_path(doc, "b"), chr(8))
    require_str(require_path(doc, "t"), chr(9))
    require_str(require_path(doc, "n"), chr(10))
    require_str(require_path(doc, "f"), chr(12))
    require_str(require_path(doc, "r"), chr(13))
    require_str(require_path(doc, "e"), chr(27))
    require_str(require_path(doc, "q"), '"')
    require_str(require_path(doc, "bs"), "\\")
    named = _scalar_mapping('k = "\\e"')
    require_str(require_path(named, "k"), chr(27))
    assert ord(require_path(named, "k")) == 27


def test_named_hex_escape_hello_lf():
    doc = _scalar_mapping('k = "\\x68\\x65\\x6c\\x6c\\x6f\\x0a"')
    value = require_path(doc, "k")
    require_str(value, "hello\n")
    assert value == "hello\n"
    assert value.endswith("\n")


def test_u_and_U_named_scalars():
    u_doc = _scalar_mapping('k = "\\u0061"')
    u8_doc = _scalar_mapping('k = "\\U00000063"')
    u_val = require_path(u_doc, "k")
    u8_val = require_path(u8_doc, "k")
    require_str(u_val, "a")
    require_str(u8_val, "c")
    assert u_val == "a"
    assert u8_val == "c"
    # Quoted keys use the same basic escapes: these are one-character keys.
    u_key = _scalar_mapping('"\\u0061" = 1\n\'\\u0061\' = 2\n')
    require_int(require_path(u_key, "a"), 1)
    require_int(require_path(u_key, "\\u0061"), 2)
    assert "a" in u_key and "\\u0061" in u_key
    u8_key = _scalar_mapping('"\\U00000063" = 1\n\'\\U00000063\' = 2\n')
    require_int(require_path(u8_key, "c"), 1)
    require_int(require_path(u8_key, "\\U00000063"), 2)


def test_hex_digits_case_insensitive():
    lower = _scalar_mapping('k = "\\x4a"')
    upper = _scalar_mapping('k = "\\x4A"')
    lower_val = require_path(lower, "k")
    upper_val = require_path(upper, "k")
    require_str(lower_val, "J")
    require_str(upper_val, "J")
    assert lower_val == upper_val == "J"
    n = 0x41 + (runtime_int() % 26)
    low = _scalar_mapping(f'k = "\\x{n:02x}"')
    high = _scalar_mapping(f'k = "\\x{n:02X}"')
    low_val = require_path(low, "k")
    high_val = require_path(high, "k")
    require_str(low_val, chr(n))
    require_str(high_val, chr(n))
    assert low_val == high_val == chr(n)


def test_u_U_hex_letter_case():
    u_upper = _scalar_mapping('k = "\\u004A"')
    u_lower = _scalar_mapping('k = "\\u004a"')
    u_upper_val = require_path(u_upper, "k")
    u_lower_val = require_path(u_lower, "k")
    require_str(u_upper_val, "J")
    require_str(u_lower_val, "J")
    assert u_upper_val == u_lower_val == "J"
    u8_upper = _scalar_mapping('k = "\\U0000004A"')
    u8_lower = _scalar_mapping('k = "\\U0000004a"')
    u8_upper_val = require_path(u8_upper, "k")
    u8_lower_val = require_path(u8_lower, "k")
    require_str(u8_upper_val, "J")
    require_str(u8_lower_val, "J")
    assert u8_upper_val == u8_lower_val == "J"
    # Hex letter case on a quoted key is the same one-character key.
    key_upper = _scalar_mapping('"\\u004A" = 1')
    key_lower = _scalar_mapping('"\\u004a" = 1')
    require_int(require_path(key_upper, "J"), 1)
    require_int(require_path(key_lower, "J"), 1)
    assert set(key_upper) == {"J"}
    assert set(key_lower) == {"J"}


def test_x_u_U_same_scalar():
    x_doc = _scalar_mapping('k = "\\x61"')
    u_doc = _scalar_mapping('k = "\\u0061"')
    u8_doc = _scalar_mapping('k = "\\U00000061"')
    require_str(require_path(x_doc, "k"), "a")
    require_str(require_path(u_doc, "k"), "a")
    require_str(require_path(u8_doc, "k"), "a")
    assert (
        require_path(x_doc, "k")
        == require_path(u_doc, "k")
        == require_path(u8_doc, "k")
    )


def test_runtime_x_escape():
    n = 0x41 + (runtime_int() % 26)
    doc = _scalar_mapping(f'k = "\\x{n:02x}"')
    value = require_path(doc, "k")
    require_str(value, chr(n))
    assert value == chr(n)


def test_runtime_U_escape():
    n = 0x42 + (runtime_int() % 24)
    assert chr(n) not in {"a", "c"}
    hex8 = f"{n:08x}"
    doc = _scalar_mapping(f'k = "\\U{hex8}"')
    require_str(require_path(doc, "k"), chr(n))
    assert require_path(doc, "k") == chr(n)
    # The same \\U scalar as a quoted basic key, distinct from the literal key.
    keys = _scalar_mapping(f'"\\U{hex8}" = 1\n\'\\U{hex8}\' = 2\n')
    require_int(require_path(keys, chr(n)), 1)
    require_int(require_path(keys, "\\U" + hex8), 2)
    assert chr(n) in keys
    assert "\\U" + hex8 in keys


def test_multiline_basic_escape_e_or_x():
    e_doc = _scalar_mapping(multiline_basic_document("k", "\\e"))
    e_val = require_path(e_doc, "k")
    require_str(e_val, chr(27))
    assert ord(e_val) == 27
    n = 0x41 + (runtime_int() % 26)
    x_doc = _scalar_mapping(multiline_basic_document("k", f"\\x{n:02x}"))
    x_val = require_path(x_doc, "k")
    require_str(x_val, chr(n))
    assert x_val == chr(n)
    nl = _scalar_mapping(multiline_basic_document("k", "a\\nb"))
    nl_val = require_path(nl, "k")
    require_str(nl_val, "a\nb")
    assert nl_val == "a\nb"


def test_null_basic_key_distinct_from_literal_u0000_key():
    src = '"\\u0000" = 1\n\'\\u0000\' = 2\n'
    doc = _scalar_mapping(src)
    null_key = chr(0)
    literal_key = "\\u0000"
    assert null_key in doc
    assert literal_key in doc
    assert null_key != literal_key
    require_int(require_path(doc, null_key), 1)
    require_int(require_path(doc, literal_key), 2)
    assert len(null_key) == 1
    assert len(literal_key) == 6
    assert set(doc) == {null_key, literal_key}


def test_runtime_escaped_quoted_key_distinct_from_literal():
    n = 0x41 + (runtime_int() % 26)
    hex4 = f"{n:04x}"
    src = f'"\\u{hex4}" = 1\n\'\\u{hex4}\' = 2\n'
    doc = _scalar_mapping(src)
    basic_key = chr(n)
    literal_key = "\\u" + hex4
    assert basic_key in doc
    assert literal_key in doc
    assert basic_key != literal_key
    require_int(require_path(doc, basic_key), 1)
    require_int(require_path(doc, literal_key), 2)


def test_quoted_key_e_or_x_distinct_from_literal():
    e_src = '"\\e" = 1\n\'\\e\' = 2\n'
    e_doc = _scalar_mapping(e_src)
    require_int(require_path(e_doc, chr(27)), 1)
    require_int(require_path(e_doc, "\\e"), 2)
    assert chr(27) != "\\e"
    n = 0x41 + (runtime_int() % 26)
    hex2 = f"{n:02x}"
    x_src = f'"\\x{hex2}" = 1\n\'\\x{hex2}\' = 2\n'
    x_doc = _scalar_mapping(x_src)
    require_int(require_path(x_doc, chr(n)), 1)
    require_int(require_path(x_doc, "\\x" + hex2), 2)


# ---------------------------------------------------------------------------
# D. Integers
# ---------------------------------------------------------------------------


def test_decimal_integers_and_signed_zeros():
    cases = (("42", 42), ("+42", 42), ("-42", -42), ("0", 0), ("+0", 0), ("-0", 0))
    for token, expected in cases:
        doc = _scalar_mapping(f"k = {token}")
        value = require_path(doc, "k")
        print(f"int token={token!r} value={value!r}", flush=True)
        require_int(value, expected)
        assert not is_float(value)


def test_runtime_decimal_integer():
    n = runtime_int()
    signed = -n if runtime_int() % 2 == 0 else n
    doc = _scalar_mapping(f"k = {signed}")
    value = require_path(doc, "k")
    require_int(value, signed)
    assert is_int(value)
    assert value == signed
    # Same magnitude as a hexadecimal integer: four bases, not a decimal-only table.
    hex_digits = format(abs(signed), "x")
    hex_doc = _scalar_mapping(f"h = 0x{hex_digits}")
    hex_val = require_path(hex_doc, "h")
    require_int(hex_val, abs(signed))
    assert is_int(hex_val)
    assert hex_val == abs(signed)


def test_hex_integers():
    cases = (
        ("0xDEADBEEF", int("DEADBEEF", 16)),
        ("0xdead_beef", int("deadbeef", 16)),
        ("0x0", 0),
    )
    for token, expected in cases:
        doc = _scalar_mapping(f"k = {token}")
        value = require_path(doc, "k")
        require_int(value, expected)
        assert is_int(value)
        assert value == expected


def test_octal_integers():
    cases = (("0o755", int("755", 8)), ("0o7_6_5", int("765", 8)))
    for token, expected in cases:
        doc = _scalar_mapping(f"k = {token}")
        value = require_path(doc, "k")
        require_int(value, expected)
        assert is_int(value)
        assert value == expected


def test_binary_integers():
    cases = (("0b11010110", int("11010110", 2)), ("0b1_0_1", int("101", 2)))
    for token, expected in cases:
        doc = _scalar_mapping(f"k = {token}")
        value = require_path(doc, "k")
        require_int(value, expected)
        assert is_int(value)
        assert value == expected


def test_runtime_hex_octal_binary_integers():
    prefixes = {16: "0x", 8: "0o", 2: "0b"}
    for base in (16, 8, 2):
        digits, expected = base_digit_string(base)
        token = prefixes[base] + digits
        print(f"runtime base={base} token={token} expected={expected}", flush=True)
        doc = _scalar_mapping(f"k = {token}")
        require_int(require_path(doc, "k"), expected)
        assert digits.lower() not in {"deadbeef", "755", "11010110"}


def test_underscores_in_integer_digits():
    hex_doc = _scalar_mapping("k = 0xdead_beef")
    hex_val = require_path(hex_doc, "k")
    require_int(hex_val, int("deadbeef", 16))
    assert is_int(hex_val)
    assert hex_val == int("deadbeef", 16)
    oct_doc = _scalar_mapping("k = 0o7_6_5")
    oct_val = require_path(oct_doc, "k")
    require_int(oct_val, int("765", 8))
    assert oct_val == int("765", 8)
    bin_doc = _scalar_mapping("k = 0b1_0_1")
    bin_val = require_path(bin_doc, "k")
    require_int(bin_val, int("101", 2))
    assert bin_val == int("101", 2)


def test_runtime_underscored_decimal():
    n = runtime_int()
    s = str(n)
    token = f"{s[0]}_{s[1:]}" if len(s) > 1 else f"{s}_0"
    expected = int(token.replace("_", ""), 10)
    doc = _scalar_mapping(f"k = {token}")
    value = require_path(doc, "k")
    require_int(value, expected)
    assert is_int(value)
    assert value == expected
    plain = _scalar_mapping(f"k = {expected}")
    require_int(require_path(plain, "k"), expected)
    assert require_path(plain, "k") == value
    # Process-local underscored hex is the every-base rule, not the public rows.
    digits, _plain_hex = base_digit_string(16)
    assert digits.lower() not in {"deadbeef", "765", "101"}
    if len(digits) == 1:
        hex_token = f"{digits}_0"
    else:
        cut = max(1, len(digits) // 2)
        hex_token = digits[:cut] + "_" + digits[cut:]
    hex_expected = int(hex_token.replace("_", ""), 16)
    assert "_" in hex_token
    assert hex_token not in {"dead_beef", "7_6_5", "1_0_1"}
    print(f"runtime underscored hex token=0x{hex_token}", flush=True)
    hex_doc = _scalar_mapping(f"h = 0x{hex_token}")
    hex_val = require_path(hex_doc, "h")
    require_int(hex_val, hex_expected)
    assert is_int(hex_val)
    assert hex_val == hex_expected


# ---------------------------------------------------------------------------
# E. Default floats
# ---------------------------------------------------------------------------


def test_fractional_and_exponent_floats():
    cases = (
        "3.14",
        "+3.14",
        "-3.14",
        "0.123",
        "3e2",
        "3E-2",
        "3.1e2",
    )
    for token in cases:
        doc = _scalar_mapping(f"k = {token}")
        value = require_path(doc, "k")
        print(f"float token={token!r} value={value!r}", flush=True)
        require_finite_float(value, float(token))
        assert not is_int(value)
        assert not is_str(value)


def test_exponent_float_is_not_int():
    as_float = _scalar_mapping("k = 3e2")
    as_int = _scalar_mapping("k = 300")
    fval = require_path(as_float, "k")
    ival = require_path(as_int, "k")
    require_finite_float(fval, float("3e2"))
    require_int(ival, 300)
    assert is_float(fval) and not is_int(fval)
    assert is_int(ival) and not is_float(ival)


def test_underscores_in_floats():
    frac = _scalar_mapping("k = 3_141.5927")
    frac_val = require_path(frac, "k")
    require_finite_float(frac_val, float("3141.5927"))
    assert is_float(frac_val)
    assert frac_val == float("3141.5927")
    exp = _scalar_mapping("k = 3e1_4")
    exp_val = require_path(exp, "k")
    require_finite_float(exp_val, float("3e14"))
    assert is_float(exp_val)
    assert exp_val == float("3e14")


def test_runtime_finite_float():
    n = runtime_int()
    m = 100 + (runtime_int() % 900)
    token = f"{n}.{m}"
    doc = _scalar_mapping(f"k = {token}")
    value = require_path(doc, "k")
    require_finite_float(value, float(token))
    assert is_float(value)
    assert value == float(token)
    signed_token = f"-{n}.{m}"
    signed_doc = _scalar_mapping(f"k = {signed_token}")
    signed_val = require_path(signed_doc, "k")
    require_finite_float(signed_val, float(signed_token))
    print(f"signed float token={signed_token!r} value={signed_val!r}", flush=True)
    assert signed_token.startswith("-")
    assert signed_val < 0
    assert signed_val == float(signed_token)
    assert signed_val != value


def test_runtime_exponent_and_underscored_float():
    mant = 10 + (runtime_int() % 90)
    exp = 1 + (runtime_int() % 5)
    exp_token = f"{mant}E{exp}"
    exp_doc = _scalar_mapping(f"k = {exp_token}")
    exp_val = require_path(exp_doc, "k")
    require_finite_float(exp_val, float(exp_token))
    print(f"capital-E token={exp_token!r} value={exp_val!r}", flush=True)
    assert "E" in exp_token
    assert "e" not in exp_token
    assert is_float(exp_val)
    assert exp_val == float(exp_token)
    n = runtime_int()
    s = str(n)
    us_token = f"{s[0]}_{s[1:]}.25" if len(s) > 1 else f"{s}_0.25"
    us_doc = _scalar_mapping(f"k = {us_token}")
    us_val = require_path(us_doc, "k")
    require_finite_float(us_val, float(us_token.replace("_", "")))
    assert is_float(us_val)
    assert us_val == float(us_token.replace("_", ""))
    exp_lo = runtime_int() % 10
    us_exp_token = f"{mant}e1_{exp_lo}"
    us_exp_doc = _scalar_mapping(f"k = {us_exp_token}")
    us_exp_val = require_path(us_exp_doc, "k")
    us_exp_expected = float(us_exp_token.replace("_", ""))
    require_finite_float(us_exp_val, us_exp_expected)
    print(f"exponent-underscore token={us_exp_token!r} value={us_exp_val!r}", flush=True)
    mantissa, exponent = us_exp_token.split("e", 1)
    assert "_" not in mantissa
    assert "_" in exponent
    assert us_exp_val == us_exp_expected
    # a number with a fractional part *and* an exponent, not the public 3.1e2.
    both_mant = 10 + (runtime_int() % 90)
    both_frac = 1 + (runtime_int() % 9)
    both_exp = 1 + (runtime_int() % 4)
    both_token = f"{both_mant}.{both_frac}e{both_exp}"
    assert both_token != "3.1e2"
    assert "." in both_token
    assert "e" in both_token
    both_doc = _scalar_mapping(f"k = {both_token}")
    both_val = require_path(both_doc, "k")
    require_finite_float(both_val, float(both_token))
    print(f"runtime fraction-and-exponent token={both_token!r} value={both_val!r}", flush=True)
    assert is_float(both_val)
    assert both_val == float(both_token)
    # a minus in the exponent, not the public 3E-2. Capital-E positive is a different arm.
    neg_mant = 11 + (runtime_int() % 89)
    neg_exp = 1 + (runtime_int() % 4)
    neg_token = f"{neg_mant}e-{neg_exp}"
    assert neg_token != "3E-2"
    assert "-" in neg_token.split("e", 1)[1]
    neg_doc = _scalar_mapping(f"k = {neg_token}")
    neg_val = require_path(neg_doc, "k")
    require_finite_float(neg_val, float(neg_token))
    print(f"runtime negative-exponent token={neg_token!r} value={neg_val!r}", flush=True)
    assert is_float(neg_val)
    assert neg_val == float(neg_token)
    assert neg_val != float(str(neg_mant))


def test_inf_plus_minus():
    pos = require_path(_scalar_mapping("k = inf"), "k")
    require_inf(pos, negative=False)
    assert is_float(pos)
    assert pos > 0
    plus = require_path(_scalar_mapping("k = +inf"), "k")
    require_inf(plus, negative=False)
    assert plus > 0
    neg = require_path(_scalar_mapping("k = -inf"), "k")
    require_inf(neg, negative=True)
    assert neg < 0


def test_nan_spellings_are_nan():
    for token in ("nan", "+nan", "-nan"):
        value = require_path(_scalar_mapping(f"k = {token}"), "k")
        print(f"nan token={token!r} value={value!r}", flush=True)
        require_nan(value)
        assert math.isnan(value)


# ---------------------------------------------------------------------------
# F. Date-times, dates, times, deepcopy
# ---------------------------------------------------------------------------


def test_offset_datetime_minus_eight():
    doc = _scalar_mapping("k = 1979-05-27T07:32:00-08:00")
    dt = require_aware_datetime(require_path(doc, "k"))
    require_utcoffset(dt, hours=-8)
    assert (dt.year, dt.month, dt.day) == (1979, 5, 27)
    assert (dt.hour, dt.minute, dt.second) == (7, 32, 0)


def test_z_and_z_suffix_are_utc():
    z_upper = _scalar_mapping("k = 1979-05-27T07:32:00Z")
    z_lower = _scalar_mapping("k = 1979-05-27T07:32:00z")
    upper = require_aware_datetime(require_path(z_upper, "k"))
    lower = require_aware_datetime(require_path(z_lower, "k"))
    require_utcoffset(upper, hours=0)
    require_utcoffset(lower, hours=0)
    assert upper == lower
    assert upper.utcoffset() == timedelta(0)


def test_datetime_separator_T_t_space_same_instant():
    space = _scalar_mapping("k = 1987-07-05 17:45:00Z")
    t_lower = _scalar_mapping("k = 1987-07-05t17:45:00z")
    a = require_aware_datetime(require_path(space, "k"))
    b = require_aware_datetime(require_path(t_lower, "k"))
    assert a == b
    assert (a.year, a.month, a.day, a.hour, a.minute, a.second) == (
        1987,
        7,
        5,
        17,
        45,
        0,
    )


def test_offset_datetime_omitted_seconds():
    omitted = _scalar_mapping("k = 1979-05-27 07:32Z")
    written = _scalar_mapping("k = 1979-05-27 07:32:00Z")
    a = require_aware_datetime(require_path(omitted, "k"))
    b = require_aware_datetime(require_path(written, "k"))
    assert a.second == 0
    assert a == b


def test_fractional_seconds_six_digits_and_truncated():
    named = _scalar_mapping("k = 1987-07-05T17:45:56.123Z")
    dt = require_aware_datetime(require_path(named, "k"))
    assert dt.microsecond == 123000
    extra = _scalar_mapping("k = 1987-07-05T17:45:56.1234569Z")
    truncated = require_aware_datetime(require_path(extra, "k"))
    assert truncated.microsecond == 123456
    assert truncated.microsecond != 123457
    year, month, day = _runtime_ymd()
    hour, minute = _runtime_clock()
    second = runtime_int() % 60
    assert (year, month, day) != (1987, 7, 5)
    assert (hour, minute, second) != (17, 45, 56)
    six_digits = f"{runtime_int() % 1000000:06d}"
    seventh = 5 + (runtime_int() % 5)
    frac = f"{six_digits}{seventh}"
    token = (
        f"{_ymd(year, month, day)}T{hour:02d}:{minute:02d}:{second:02d}.{frac}Z"
    )
    runtime = _scalar_mapping(f"k = {token}")
    runtime_dt = require_aware_datetime(require_path(runtime, "k"))
    print(f"runtime truncated token={token} us={runtime_dt.microsecond}", flush=True)
    assert runtime_dt.microsecond == int(six_digits)
    assert runtime_dt.microsecond != int(six_digits) + 1
    assert (runtime_dt.year, runtime_dt.month, runtime_dt.day) == (year, month, day)
    assert (runtime_dt.hour, runtime_dt.minute, runtime_dt.second) == (
        hour,
        minute,
        second,
    )
    # up to six fractional digits are microseconds. Width in {1,2,4,5}
    # (not the named three-digit .123, not six-or-more) pads those digits on
    # the right to six. int(frac) without padding is a different number.
    pad_widths = (1, 2, 4, 5)
    pad_width = pad_widths[runtime_int() % len(pad_widths)]
    frac_n = 1 + (runtime_int() % (10 ** pad_width - 1))
    frac_digits = f"{frac_n:0{pad_width}d}"
    padded_us = int(frac_digits + "0" * (6 - pad_width))
    assert pad_width not in (3, 6)
    assert len(frac_digits) == pad_width
    assert padded_us != int(frac_digits)
    pad_year, pad_month, pad_day = _runtime_ymd()
    pad_hour, pad_minute = _runtime_clock()
    pad_second = runtime_int() % 60
    assert (pad_year, pad_month, pad_day) != (1987, 7, 5)
    assert (pad_hour, pad_minute, pad_second) != (17, 45, 56)
    pad_token = (
        f"{_ymd(pad_year, pad_month, pad_day)}T"
        f"{pad_hour:02d}:{pad_minute:02d}:{pad_second:02d}.{frac_digits}Z"
    )
    pad_doc = _scalar_mapping(f"k = {pad_token}")
    pad_dt = require_aware_datetime(require_path(pad_doc, "k"))
    print(
        f"runtime padded frac token={pad_token} width={pad_width} "
        f"us={pad_dt.microsecond} expected={padded_us}",
        flush=True,
    )
    assert pad_dt.microsecond == padded_us
    assert (pad_dt.year, pad_dt.month, pad_dt.day) == (pad_year, pad_month, pad_day)
    assert (pad_dt.hour, pad_dt.minute, pad_dt.second) == (
        pad_hour,
        pad_minute,
        pad_second,
    )


def test_numeric_offset_contrast():
    wall = "1979-05-27T07:32:00"
    choices = (5, 6, 7, 9, 10, 11)
    other = choices[runtime_int() % len(choices)]
    eight = _scalar_mapping(f"k = {wall}-08:00")
    other_doc = _scalar_mapping(f"k = {wall}-{other:02d}:00")
    a = require_aware_datetime(require_path(eight, "k"))
    b = require_aware_datetime(require_path(other_doc, "k"))
    require_utcoffset(a, hours=-8)
    require_utcoffset(b, hours=-other)
    assert a.utcoffset() != b.utcoffset()
    assert (a.year, a.month, a.day, a.hour, a.minute, a.second) == (
        b.year,
        b.month,
        b.day,
        b.hour,
        b.minute,
        b.second,
    )


def test_runtime_offset_datetime():
    year, month, day = _runtime_ymd()
    hour, minute = _runtime_clock()
    token = f"{_ymd(year, month, day)}T{hour:02d}:{minute:02d}:00-08:00"
    doc = _scalar_mapping(f"k = {token}")
    dt = require_aware_datetime(require_path(doc, "k"))
    require_utcoffset(dt, hours=-8)
    assert (dt.year, dt.month, dt.day) == (year, month, day)
    assert (dt.hour, dt.minute, dt.second) == (hour, minute, 0)
    z_token = f"{_ymd(year, month, day)}T{hour:02d}:{minute:02d}:00Z"
    z_doc = _scalar_mapping(f"k = {z_token}")
    z_dt = require_aware_datetime(require_path(z_doc, "k"))
    require_utcoffset(z_dt, hours=0)


def test_runtime_omitted_seconds_offset_and_local():
    year, month, day = _runtime_ymd()
    hour, minute = _runtime_clock()
    stamp = f"{_ymd(year, month, day)} {hour:02d}:{minute:02d}"
    omitted = _scalar_mapping(f"k = {stamp}Z")
    written = _scalar_mapping(f"k = {stamp}:00Z")
    a = require_aware_datetime(require_path(omitted, "k"))
    b = require_aware_datetime(require_path(written, "k"))
    assert a.second == 0
    assert a == b
    local_stamp = f"{_ymd(year, month, day)}T{hour:02d}:{minute:02d}"
    local_omitted = _scalar_mapping(f"k = {local_stamp}")
    local_written = _scalar_mapping(f"k = {local_stamp}:00")
    na = require_naive_datetime(require_path(local_omitted, "k"))
    nb = require_naive_datetime(require_path(local_written, "k"))
    print(
        f"runtime local omitted={na!r} written={nb!r} source={local_stamp}",
        flush=True,
    )
    assert (hour, minute) != (1, 1)
    assert (hour, minute) != (20, 5)
    assert (na.year, na.month, na.day) == (year, month, day)
    assert (na.hour, na.minute) == (hour, minute)
    assert (nb.year, nb.month, nb.day) == (year, month, day)
    assert (nb.hour, nb.minute) == (hour, minute)
    assert na.second == 0
    assert nb.second == 0
    assert na == nb
    assert na.tzinfo is None
    assert nb.tzinfo is None


def test_local_datetime_naive():
    doc = _scalar_mapping("k = 1988-10-27t01:01:01")
    dt = require_naive_datetime(require_path(doc, "k"))
    assert (dt.year, dt.month, dt.day) == (1988, 10, 27)
    assert (dt.hour, dt.minute, dt.second) == (1, 1, 1)
    assert dt.tzinfo is None
    # Same wall clock with a Z/z suffix is timezone-aware UTC.
    z_upper = _scalar_mapping("k = 1988-10-27t01:01:01Z")
    z_lower = _scalar_mapping("k = 1988-10-27t01:01:01z")
    upper = require_aware_datetime(require_path(z_upper, "k"))
    lower = require_aware_datetime(require_path(z_lower, "k"))
    require_utcoffset(upper, hours=0)
    require_utcoffset(lower, hours=0)
    assert upper.tzinfo is not None
    assert lower.tzinfo is not None
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second) == (
        upper.year,
        upper.month,
        upper.day,
        upper.hour,
        upper.minute,
        upper.second,
    )


def test_local_datetime_omitted_seconds():
    doc = _scalar_mapping("k = 2025-04-18T20:05")
    dt = require_naive_datetime(require_path(doc, "k"))
    assert (dt.year, dt.month, dt.day) == (2025, 4, 18)
    assert (dt.hour, dt.minute, dt.second) == (20, 5, 0)


def test_naive_datetime_distinct_from_offset():
    naive = _scalar_mapping("k = 1988-10-27T01:01:01")
    aware = _scalar_mapping("k = 1988-10-27T01:01:01Z")
    n = require_naive_datetime(require_path(naive, "k"))
    a = require_aware_datetime(require_path(aware, "k"))
    require_utcoffset(a, hours=0)
    assert n.tzinfo is None
    assert a.tzinfo is not None
    assert (n.year, n.month, n.day, n.hour, n.minute, n.second) == (
        a.year,
        a.month,
        a.day,
        a.hour,
        a.minute,
        a.second,
    )


def test_local_date_and_leap_days():
    local = _scalar_mapping("k = 1988-10-27")
    local_val = require_path(local, "k")
    require_date(local_val, 1988, 10, 27)
    assert (local_val.year, local_val.month, local_val.day) == (1988, 10, 27)
    y2k = _scalar_mapping("k = 2000-02-29")
    y2k_val = require_path(y2k, "k")
    require_date(y2k_val, 2000, 2, 29)
    assert (y2k_val.year, y2k_val.month, y2k_val.day) == (2000, 2, 29)
    y2024 = _scalar_mapping("k = 2024-02-29")
    y2024_val = require_path(y2024, "k")
    require_date(y2024_val, 2024, 2, 29)
    assert (y2024_val.year, y2024_val.month, y2024_val.day) == (2024, 2, 29)


def test_runtime_leap_day():
    year = _LEAP_YEARS[runtime_int() % len(_LEAP_YEARS)]
    doc = _scalar_mapping(f"k = {year:04d}-02-29")
    value = require_path(doc, "k")
    require_date(value, year, 2, 29)
    assert (value.year, value.month, value.day) == (year, 2, 29)


def test_local_time_and_omitted_seconds():
    full = _scalar_mapping("k = 17:45:00")
    full_val = require_path(full, "k")
    require_time(full_val, 17, 45, 0)
    assert (full_val.hour, full_val.minute, full_val.second) == (17, 45, 0)
    omitted = _scalar_mapping("k = 13:37")
    omitted_val = require_path(omitted, "k")
    require_time(omitted_val, 13, 37, 0)
    assert omitted_val.second == 0
    assert (omitted_val.hour, omitted_val.minute) == (13, 37)


def test_fractional_local_time_differs_from_whole_seconds():
    frac = _scalar_mapping("k = 10:32:00.555")
    whole = _scalar_mapping("k = 10:32:00")
    t_frac = require_time(require_path(frac, "k"), 10, 32, 0)
    t_whole = require_time(require_path(whole, "k"), 10, 32, 0)
    assert t_frac != t_whole
    assert t_frac.hour == t_whole.hour == 10
    assert t_frac.minute == t_whole.minute == 32


def test_runtime_local_time():
    hour, minute = _runtime_clock()
    omitted = _scalar_mapping(f"k = {hour:02d}:{minute:02d}")
    written = _scalar_mapping(f"k = {hour:02d}:{minute:02d}:00")
    t0 = require_time(require_path(omitted, "k"), hour, minute, 0)
    t1 = require_time(require_path(written, "k"), hour, minute, 0)
    assert t0.second == 0
    assert t0 == t1


def test_date_vs_naive_dt_vs_aware_dt():
    as_date = _scalar_mapping("k = 1988-10-27")
    naive = _scalar_mapping("k = 1988-10-27T00:00:00")
    aware = _scalar_mapping("k = 1988-10-27T00:00:00Z")
    d = require_date(require_path(as_date, "k"), 1988, 10, 27)
    n = require_naive_datetime(require_path(naive, "k"))
    a = require_aware_datetime(require_path(aware, "k"))
    assert type(d) is not type(n)
    assert n.tzinfo is None
    assert a.tzinfo is not None
    assert (n.year, n.month, n.day) == (d.year, d.month, d.day)
    assert (n.hour, n.minute, n.second) == (0, 0, 0)


def test_deepcopy_mapping_with_offset_datetime():
    src = (
        "when = 1979-05-27T07:32:00-08:00\n"
        "day = 1988-10-27\n"
        "clock = 17:45:00\n"
    )
    original = _scalar_mapping(src)
    require_aware_datetime(require_path(original, "when"))
    require_date(require_path(original, "day"), 1988, 10, 27)
    require_time(require_path(original, "clock"), 17, 45, 0)
    copied = copy.deepcopy(original)
    print(f"deepcopy equal={copied == original}", flush=True)
    assert copied == original


# ---------------------------------------------------------------------------
# G. Illegal scalar spellings
# ---------------------------------------------------------------------------


def test_wrong_case_and_short_booleans_refused():
    cases = (
        ("k = True", "k = true"),
        ("k = FALSE", "k = false"),
        ("k = t", "k = true"),
        ("k = f", "k = false"),
    )
    for bad, good in cases:
        neighbor = _refuse_near(bad, good)
        flag = require_path(neighbor, "k")
        if "true" in good:
            require_bool(flag, True)
            assert flag is True
        else:
            require_bool(flag, False)
            assert flag is False
    key = runtime_token()
    yes = _refuse_near(f"{key} = True", f"{key} = true")
    require_bool(require_path(yes, key), True)
    assert require_path(yes, key) is True
    sibling = runtime_token()
    no = _refuse_near(f"{sibling} = False", f"{sibling} = false")
    require_bool(require_path(no, sibling), False)
    assert require_path(no, sibling) is False


def test_leading_zero_decimals_refused():
    cases = (
        ("k = 01", "k = 1"),
        ("k = +01", "k = +1"),
        ("k = -01", "k = -1"),
        ("k = 02", "k = 2"),
        ("k = 00", "k = 0"),
    )
    for bad, good in cases:
        neighbor = _refuse_near(bad, good)
        expected = int(good.split("=", 1)[1].strip(), 10)
        value = require_path(neighbor, "k")
        require_int(value, expected)
        assert is_int(value)
        assert value == expected
    zero = _succeeds_neighbor("k = 0")
    zero_val = require_path(zero, "k")
    require_int(zero_val, 0)
    assert zero_val == 0


def test_capital_base_prefixes_refused():
    cases = (
        ("k = 0X1", "k = 0x1"),
        ("k = 0O1", "k = 0o1"),
        ("k = 0B1", "k = 0b1"),
        ("k = 0X2", "k = 0x2"),
    )
    for bad, good in cases:
        neighbor = _refuse_near(bad, good)
        expected = int(good.split("=", 1)[1].strip(), 0)
        value = require_path(neighbor, "k")
        require_int(value, expected)
        assert is_int(value)
        assert value == expected


def test_illegal_integer_underscores_refused():
    cases = (
        ("k = _1", "k = 1"),
        ("k = 1_", "k = 1"),
        ("k = 1__2", "k = 1_2"),
        ("k = 0x_1", "k = 0x10"),
        ("k = 0x1_", "k = 0x10"),
        ("k = 0o_7", "k = 0o7"),
    )
    for bad, good in cases:
        neighbor = _refuse_near(bad, good)
        value = require_path(neighbor, "k")
        assert is_int(value)


def test_signed_nondecimal_integers_refused():
    cases = (
        ("k = +0x1", "k = 0x1"),
        ("k = -0o1", "k = 0o1"),
        ("k = +0b1", "k = 0b1"),
        ("k = -0x1", "k = 0x1"),
    )
    for bad, good in cases:
        neighbor = _refuse_near(bad, good)
        expected = int(good.split("=", 1)[1].strip(), 0)
        value = require_path(neighbor, "k")
        require_int(value, expected)
        assert is_int(value)
        assert value == expected


def test_digits_outside_base_refused():
    cases = (
        ("k = 0o8", "k = 0o7"),
        ("k = 0b2", "k = 0b1"),
        ("k = 0xG", "k = 0xF"),
        ("k = 0o9", "k = 0o7"),
    )
    for bad, good in cases:
        neighbor = _refuse_near(bad, good)
        expected = int(good.split("=", 1)[1].strip(), 0)
        value = require_path(neighbor, "k")
        require_int(value, expected)
        assert is_int(value)
        assert value == expected


def test_leading_zero_floats_refused():
    cases = (
        ("k = 03.14", "k = 3.14"),
        ("k = +03.14", "k = +3.14"),
        ("k = -03.14", "k = -3.14"),
        ("k = 04.5", "k = 4.5"),
        ("k = 00.123", "k = 0.123"),
        ("k = -00.123", "k = -0.123"),
    )
    for bad, good in cases:
        neighbor = _refuse_near(bad, good)
        token = good.split("=", 1)[1].strip()
        value = require_path(neighbor, "k")
        require_finite_float(value, float(token))
        assert is_float(value)
        assert value == float(token)
    single_zero = _succeeds_neighbor("k = 0.123")
    zero_val = require_path(single_zero, "k")
    require_finite_float(zero_val, float("0.123"))
    assert zero_val == float("0.123")


def test_leading_dot_floats_refused():
    cases = (
        ("k = .12345", "k = 0.12345"),
        ("k = +.12345", "k = 0.12345"),
        ("k = -.12345", "k = -0.12345"),
        ("k = .5", "k = 0.5"),
    )
    for bad, good in cases:
        neighbor = _refuse_near(bad, good)
        token = good.split("=", 1)[1].strip()
        value = require_path(neighbor, "k")
        require_finite_float(value, float(token))
        assert is_float(value)
        assert value == float(token)


def test_dot_only_and_trailing_dot_floats_refused():
    cases = (
        ("val=.", "val=0.123"),
        ("k = 1.", "k = 1.0"),
        ("k = 2.", "k = 2.0"),
    )
    for bad, good in cases:
        neighbor = _refuse_near(bad, good)
        key = good.split("=", 1)[0].strip()
        token = good.split("=", 1)[1].strip()
        value = require_path(neighbor, key)
        require_finite_float(value, float(token))
        assert is_float(value)
        assert value == float(token)


def test_surrogate_escape_refused():
    neighbor = _succeeds_neighbor('k = "\\u0061"')
    require_str(require_path(neighbor, "k"), "a")
    assert require_path(neighbor, "k") == "a"
    refused_d800 = _refuse_scalar('k = "\\uD800"')
    refused_dfff = _refuse_scalar('k = "\\uDFFF"')
    refused_u8 = _refuse_scalar('k = "\\U0000D800"')
    assert refused_d800 is not None
    assert refused_dfff is not None
    assert refused_u8 is not None
    # The rule is the surrogate *class*, not the D800/DFFF spellings. A sibling
    # inside U+D801..U+DFFE kills a cheat that only blocklists those samples.
    code = 0xD801 + (runtime_int() % (0xDFFE - 0xD801 + 1))
    assert 0xD800 < code < 0xDFFF
    hex4 = f"{code:04X}"
    hex8 = f"{code:08X}"
    print(f"runtime surrogate U+{hex4}", flush=True)
    refused_runtime_u = _refuse_scalar(f'k = "\\u{hex4}"')
    refused_runtime_U = _refuse_scalar(f'k = "\\U{hex8}"')
    assert refused_runtime_u is not None
    assert refused_runtime_U is not None


def test_incomplete_hex_escapes_refused():
    cases = (
        ('k = "\\x6"', 'k = "\\x61"'),
        ('k = "\\u006"', 'k = "\\u0061"'),
        ('k = "\\U0000006"', 'k = "\\U00000063"'),
        ('k = "\\x"', 'k = "\\x61"'),
    )
    for bad, good in cases:
        neighbor = _refuse_near(bad, good)
        assert is_str(require_path(neighbor, "k"))


def test_non_hex_digits_in_advertised_hex_escape_refused():
    # \x plus two hex digits. A backslash that is not a listed
    # escape fails. Advertised width filled with non-hex is not a short run.
    hex_alphabet = "0123456789abcdef"
    non_hex_alphabet = "ghijklmnopqrstuvwxyz"
    h0 = hex_alphabet[runtime_int() % 16]
    h1 = hex_alphabet[runtime_int() % 16]
    n0 = non_hex_alphabet[runtime_int() % len(non_hex_alphabet)]
    n1 = non_hex_alphabet[runtime_int() % len(non_hex_alphabet)]
    good_digits = h0 + h1
    bad_digits = n0 + n1
    assert len(good_digits) == 2
    assert len(bad_digits) == 2
    assert all(c in hex_alphabet for c in good_digits)
    assert all(c not in hex_alphabet and c not in hex_alphabet.upper() for c in bad_digits)
    neighbor = _refuse_near(f'k = "\\x{bad_digits}"', f'k = "\\x{good_digits}"')
    expected = chr(int(good_digits, 16))
    value = require_path(neighbor, "k")
    require_str(value, expected)
    print(
        f"full-width non-hex \\x{bad_digits} refused; neighbor \\x{good_digits}={expected!r}",
        flush=True,
    )
    assert value == expected
    assert is_str(value)


def test_unknown_basic_escape_refused():
    neighbor = _succeeds_neighbor('k = "\\n"')
    require_str(require_path(neighbor, "k"), "\n")
    assert require_path(neighbor, "k") == "\n"
    # A listed two-character escape is the live baseline.
    e_neighbor = _succeeds_neighbor('k = "\\e"')
    require_str(require_path(e_neighbor, "k"), chr(27))
    assert ord(require_path(e_neighbor, "k")) == 27
    slash_neighbor = _succeeds_neighbor('k = "\\\\"')
    require_str(require_path(slash_neighbor, "k"), "\\")
    assert require_path(slash_neighbor, "k") == "\\"
    refused_q = _refuse_scalar('k = "\\q"')
    refused_p = _refuse_scalar('k = "\\p"')
    assert refused_q is not None
    assert refused_p is not None


def test_oneline_basic_backslash_space_not_an_escape():
    neighbor = _succeeds_neighbor('k = "a\\tb"')
    require_str(require_path(neighbor, "k"), "a\tb")
    assert require_path(neighbor, "k") == "a\tb"
    refused = _refuse_scalar('k = "a\\t\\ b"')
    assert refused is not None
    slash = _succeeds_neighbor('k = "a\\\\b"')
    require_str(require_path(slash, "k"), "a\\b")
    assert require_path(slash, "k") == "a\\b"


def test_raw_formfeed_in_oneline_string_refused():
    neighbor = _succeeds_neighbor(f'k = "pre{chr(9)}post"')
    require_str(require_path(neighbor, "k"), "pre\tpost")
    assert require_path(neighbor, "k") == "pre\tpost"
    refused = _refuse_scalar(f'k = "pre{chr(12)}post"')
    assert refused is not None


def test_raw_formfeed_in_oneline_literal_refused():
    neighbor = _succeeds_neighbor(f"k = 'pre{chr(9)}post'")
    require_str(require_path(neighbor, "k"), "pre\tpost")
    assert require_path(neighbor, "k") == "pre\tpost"
    refused = _refuse_scalar(f"k = 'pre{chr(12)}post'")
    assert refused is not None


def test_raw_tab_in_oneline_string_allowed():
    basic = _scalar_mapping(f'k = "pre{chr(9)}post"')
    basic_val = require_path(basic, "k")
    require_str(basic_val, "pre\tpost")
    assert basic_val == "pre\tpost"
    literal = _scalar_mapping(f"k = 'pre{chr(9)}post'")
    literal_val = require_path(literal, "k")
    require_str(literal_val, "pre\tpost")
    assert literal_val == "pre\tpost"
    # Opening line feed discarded; the raw tab is still in the value.
    multi = _scalar_mapping(multiline_basic_document("k", "\npre\tpost"))
    multi_val = require_path(multi, "k")
    require_str(multi_val, "pre\tpost")
    assert multi_val == basic_val
    assert not multi_val.startswith("\n")
    # Same position with a raw form-feed is refused.
    refused = _refuse_scalar(f'k = "pre{chr(12)}post"')
    assert refused is not None


def test_raw_control_sibling_in_oneline_string_refused():
    neighbor = _succeeds_neighbor(f'k = "pre{chr(9)}post"')
    require_str(require_path(neighbor, "k"), "pre\tpost")
    assert require_path(neighbor, "k") == "pre\tpost"
    refused_vt = _refuse_scalar(f'k = "pre{chr(11)}post"')
    refused_nul = _refuse_scalar(f'k = "pre{chr(0)}post"')
    assert refused_vt is not None
    assert refused_nul is not None


def test_bare_cr_in_multiline_basic_refused():
    neighbor_lf = _succeeds_neighbor(multiline_basic_document("k", "\npre\npost"))
    assert is_str(require_path(neighbor_lf, "k"))
    neighbor_crlf = _succeeds_neighbor('k = """\r\npre\r\npost"""')
    assert is_str(require_path(neighbor_crlf, "k"))
    refused = _refuse_scalar('k = """\npre\rpost"""')
    assert refused is not None


def test_unclosed_four_string_forms_refused():
    body = runtime_token()
    for form in ("basic", "literal", "multiline_basic", "multiline_literal"):
        key = runtime_token()
        neighbor = _succeeds_neighbor(_closed_string(form, body, key=key))
        value = require_path(neighbor, key)
        require_str(value, body)
        assert value == body
        refused = _refuse_scalar(unclosed(form, body, key=key))
        assert refused is not None


def test_impossible_local_date_refused():
    neighbor = _succeeds_neighbor("k = 1988-02-28")
    feb28 = require_path(neighbor, "k")
    require_date(feb28, 1988, 2, 28)
    assert (feb28.year, feb28.month, feb28.day) == (1988, 2, 28)
    refused_feb = _refuse_scalar("k = 1988-02-30")
    assert refused_feb is not None
    april = _succeeds_neighbor("k = 2021-04-30")
    apr30 = require_path(april, "k")
    require_date(apr30, 2021, 4, 30)
    assert (apr30.year, apr30.month, apr30.day) == (2021, 4, 30)
    refused_apr = _refuse_scalar("k = 2021-04-31")
    assert refused_apr is not None


def test_non_leap_feb29_refused():
    leap = _succeeds_neighbor("k = 2024-02-29")
    leap_val = require_path(leap, "k")
    require_date(leap_val, 2024, 2, 29)
    assert (leap_val.year, leap_val.month, leap_val.day) == (2024, 2, 29)
    refused_2019 = _refuse_scalar("k = 2019-02-29")
    assert refused_2019 is not None
    year = _NON_LEAP_YEARS[runtime_int() % len(_NON_LEAP_YEARS)]
    refused_runtime = _refuse_scalar(f"k = {year:04d}-02-29")
    assert refused_runtime is not None


def test_hour_24_refused():
    neighbor = _succeeds_neighbor("k = 2006-01-01T23:00:00Z")
    hour23 = require_aware_datetime(require_path(neighbor, "k"))
    assert hour23.hour == 23
    midnight = _succeeds_neighbor("k = 2006-01-01T00:00:00Z")
    hour0 = require_aware_datetime(require_path(midnight, "k"))
    assert hour0.hour == 0
    refused_24 = _refuse_scalar("k = 2006-01-01T24:00:00Z")
    refused_25 = _refuse_scalar("k = 2006-01-01T25:00:00Z")
    assert refused_24 is not None
    assert refused_25 is not None


def test_minute_60_and_second_60_refused():
    minute_ok = _succeeds_neighbor("k = 17:59:00")
    t_min = require_time(require_path(minute_ok, "k"), 17, 59, 0)
    assert t_min.minute == 59
    refused_min60 = _refuse_scalar("k = 17:60:00")
    refused_min61 = _refuse_scalar("k = 17:61:00")
    assert refused_min60 is not None
    assert refused_min61 is not None
    second_ok = _succeeds_neighbor("k = 17:45:59")
    t_sec = require_time(require_path(second_ok, "k"), 17, 45, 59)
    assert t_sec.second == 59
    refused_sec60 = _refuse_scalar("k = 17:45:60")
    refused_sec61 = _refuse_scalar("k = 12:30:61")
    assert refused_sec60 is not None
    assert refused_sec61 is not None
