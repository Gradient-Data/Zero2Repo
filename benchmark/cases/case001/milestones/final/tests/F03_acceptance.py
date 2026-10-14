# feature: F03
"""FP-03: parse TOML from a binary file object.

Assertions follow the PRD FP-03. Structural and
scalar fine rules are FP-01 / FP-02; this feature proves those rules apply
to the UTF-8 text of a binary file, that text-mode is a type error (not a
decode error; FP-04), and that non-UTF-8 bytes do not succeed.
"""

from __future__ import annotations

from tomlparse import TOMLDecodeError, load  # noqa: F401 — public binary-file surface

from _harness import binary_buffer, text_buffer
from F01_helpers import (
    decode_error_type,
    is_mapping,
    parse_text,
    require_mapping,
    require_path,
    require_sequence,
    runtime_int,
    runtime_token,
)
from F02_helpers import require_int, require_str
from F03_helpers import (
    lax_success_invalid_utf8,
    parse_binary,
    require_type_error,
    require_unsuccessful,
    utf8_source,
)

_NAMED_ROOT = "one=1\ntwo='two'\narr=[]"
_NAMED_CRLF = "one=1\r\ntwo='two'"
_NAMED_LF = "one=1\ntwo='two'"
_PLAYERS = (
    "[[players]]\n"
    'name = "Lehtinen"\n'
    "number = 26\n"
    "[[players]]\n"
    'name = "Numminen"\n'
    "number = 27\n"
)
_NAMED_ESCAPE = 'k = "\\e"'
_NAMED_INLINE = "t = {\nc = 1,\n}\n"
_LATIN1_LETTERS = (
    tuple(range(0x00C0, 0x00D7))
    + tuple(range(0x00D8, 0x00F7))
    + tuple(range(0x00F8, 0x0100))
)


def _string_mapping(text: str):
    print(f"string source={text!r}", flush=True)
    mapping = require_mapping(parse_text(text))
    print(f"string keys={list(mapping)}", flush=True)
    return mapping


def _binary_mapping_disk(ws, relpath: str, content: str | bytes):
    data = content if isinstance(content, bytes) else utf8_source(content)
    print(f"binary disk {relpath!r} bytes={data!r}", flush=True)
    with ws.binary_source(relpath, data) as fp:
        result = parse_binary(fp)
    mapping = require_mapping(result)
    print(f"binary disk keys={list(mapping)}", flush=True)
    return mapping


def _binary_mapping_buffer(content: str | bytes):
    data = content if isinstance(content, bytes) else utf8_source(content)
    print(f"binary buffer bytes={data!r}", flush=True)
    result = parse_binary(binary_buffer(data))
    mapping = require_mapping(result)
    print(f"binary buffer keys={list(mapping)}", flush=True)
    return mapping


def _require_same_mapping(binary_map, string_map) -> None:
    assert binary_map == string_map, (
        f"binary mapping {binary_map!r} != string mapping {string_map!r}"
    )


def _assert_named_root(mapping) -> None:
    require_int(require_path(mapping, "one"), 1)
    require_str(require_path(mapping, "two"), "two")
    arr = require_sequence(require_path(mapping, "arr"))
    assert len(arr) == 0, f"arr is not empty: {arr!r}"


def _assert_text_mode_type_error(result) -> None:
    """type error, not decode error, and no document mapping."""
    exc = require_type_error(result)
    assert isinstance(exc, TypeError), (
        f"text-mode file must be a type error, got {type(exc).__name__}: {exc!r}"
    )
    assert not isinstance(exc, decode_error_type()), (
        f"text-mode file was a decode error, not a type error: {exc!r}"
    )
    if result.value is not None:
        assert not is_mapping(result.value), (
            f"text-mode file still yielded a document mapping: {result.value!r}"
        )


def _assert_non_utf8_unsuccessful(result) -> None:
    """no document mapping; the call does not succeed."""
    require_unsuccessful(result)
    has_mapping = False
    if result.value is not None:
        has_mapping = is_mapping(result.value)
    assert not has_mapping, (
        f"invalid UTF-8 yielded a document mapping: {result.value!r}"
    )
    succeeded = result.exception is None and has_mapping
    assert not succeeded, (
        f"invalid UTF-8 parse succeeded: {result.value!r}"
    )


def _runtime_bmp_letter() -> str:
    code = _LATIN1_LETTERS[runtime_int() % len(_LATIN1_LETTERS)]
    return chr(code)


def _non_ascii_document() -> tuple[str, str, str]:
    key = runtime_token()
    letter = _runtime_bmp_letter()
    assert ord(letter) > 127, f"expected non-ASCII scalar, got U+{ord(letter):04X}"
    src = f'{key} = "{letter}"\n'
    encoded = utf8_source(src)
    utf8_letter = letter.encode("utf-8")
    assert len(utf8_letter) >= 2, (
        f"{letter!r} is not a multi-byte UTF-8 scalar"
    )
    assert utf8_letter in encoded
    return src, key, letter


def _lax_invariant(raw: bytes):
    text = raw.decode("latin-1")
    print(f"latin-1 text={text!r}", flush=True)
    mapping = require_mapping(parse_text(text))
    print(f"latin-1 mapping keys={list(mapping)}", flush=True)
    return mapping


def _valid_utf8_baseline_disk(ws, relpath: str):
    key = runtime_token()
    n = runtime_int()
    src = f"{key} = {n}\n"
    mapping = _binary_mapping_disk(ws, relpath, src)
    require_int(require_path(mapping, key), n)
    return mapping


def _valid_utf8_baseline_buffer():
    key = runtime_token()
    n = runtime_int()
    src = f"{key} = {n}\n"
    mapping = _binary_mapping_buffer(src)
    require_int(require_path(mapping, key), n)
    return mapping


# ---------------------------------------------------------------------------
# A. Named root document: binary matches string
# ---------------------------------------------------------------------------


def test_named_one_two_arr_binary_matches_string(isolated_ws):
    mapping = _binary_mapping_disk(isolated_ws, "named.toml", _NAMED_ROOT)
    _assert_named_root(mapping)
    _require_same_mapping(mapping, _string_mapping(_NAMED_ROOT))


def test_runtime_root_pair_binary_matches_string():
    key = runtime_token()
    n = runtime_int()
    extra = runtime_token()
    src = f"{key} = {n}\n{extra} = '{extra}'\n"
    mapping = _binary_mapping_buffer(src)
    require_int(require_path(mapping, key), n)
    require_str(require_path(mapping, extra), extra)
    assert set(mapping) == {key, extra}
    _require_same_mapping(mapping, _string_mapping(src))


# ---------------------------------------------------------------------------
# B. Empty file is an empty mapping
# ---------------------------------------------------------------------------


def test_empty_binary_file_is_empty_mapping(isolated_ws):
    empty = _binary_mapping_disk(isolated_ws, "empty.toml", b"")
    assert len(empty) == 0, f"expected empty mapping, got {empty!r}"
    _require_same_mapping(empty, _string_mapping(""))

    key = runtime_token()
    n = runtime_int()
    baseline = _binary_mapping_disk(
        isolated_ws, "baseline.toml", f"{key} = {n}\n"
    )
    require_int(require_path(baseline, key), n)
    assert len(baseline) != 0

    buf_empty = _binary_mapping_buffer(b"")
    assert len(buf_empty) == 0, f"empty buffer is not empty: {buf_empty!r}"


# ---------------------------------------------------------------------------
# C. Bytes as UTF-8; CRLF is one line feed
# ---------------------------------------------------------------------------


def test_crlf_between_keys_binary(isolated_ws):
    crlf_map = _binary_mapping_disk(isolated_ws, "crlf.toml", _NAMED_CRLF)
    require_int(require_path(crlf_map, "one"), 1)
    require_str(require_path(crlf_map, "two"), "two")
    assert set(crlf_map) == {"one", "two"}
    _require_same_mapping(crlf_map, _string_mapping(_NAMED_CRLF))

    lf_map = _binary_mapping_disk(isolated_ws, "lf.toml", _NAMED_LF)
    require_int(require_path(lf_map, "one"), 1)
    require_str(require_path(lf_map, "two"), "two")
    _require_same_mapping(crlf_map, lf_map)


def test_runtime_crlf_between_keys(isolated_ws):
    first, second = runtime_token(), runtime_token()
    a, b = runtime_int(), runtime_int()
    src = f"{first} = {a}\r\n{second} = {b}\n"
    mapping = _binary_mapping_disk(isolated_ws, "runtime-crlf.toml", src)
    require_int(require_path(mapping, first), a)
    require_int(require_path(mapping, second), b)
    assert set(mapping) == {first, second}
    _require_same_mapping(mapping, _string_mapping(src))


def test_non_ascii_utf8_bytes_match_string(isolated_ws):
    src, key, letter = _non_ascii_document()
    mapping = _binary_mapping_disk(isolated_ws, "non-ascii.toml", src)
    require_str(require_path(mapping, key), letter)
    _require_same_mapping(mapping, _string_mapping(src))


def test_non_ascii_utf8_via_binary_buffer():
    src, key, letter = _non_ascii_document()
    mapping = _binary_mapping_buffer(src)
    require_str(require_path(mapping, key), letter)
    _require_same_mapping(mapping, _string_mapping(src))


# ---------------------------------------------------------------------------
# D. FP-01 / FP-02 representative documents
# ---------------------------------------------------------------------------


def test_two_players_tables_binary_matches_string(isolated_ws):
    mapping = _binary_mapping_disk(isolated_ws, "players.toml", _PLAYERS)
    players = require_sequence(require_path(mapping, "players"))
    assert len(players) == 2, f"players length {len(players)} != 2"
    first, second = players[0], players[1]
    assert is_mapping(first) and is_mapping(second)
    require_str(require_path(first, "name"), "Lehtinen")
    require_int(require_path(first, "number"), 26)
    require_str(require_path(second, "name"), "Numminen")
    require_int(require_path(second, "number"), 27)
    _require_same_mapping(mapping, _string_mapping(_PLAYERS))


def test_runtime_array_of_tables_binary_matches_string(isolated_ws):
    table = runtime_token()
    key = runtime_token()
    a, b = runtime_int(), runtime_int()
    src = f"[[{table}]]\n{key} = {a}\n[[{table}]]\n{key} = {b}\n"
    mapping = _binary_mapping_disk(isolated_ws, "runtime-aot.toml", src)
    items = require_sequence(require_path(mapping, table))
    assert len(items) == 2, f"{table} length {len(items)} != 2"
    assert is_mapping(items[0]) and is_mapping(items[1])
    require_int(require_path(items[0], key), a)
    require_int(require_path(items[1], key), b)
    _require_same_mapping(mapping, _string_mapping(src))


def test_runtime_dotted_table_binary_matches_string(isolated_ws):
    prefix, leaf = runtime_token(), runtime_token()
    n = runtime_int()
    src = f"{prefix}.{leaf} = {n}\n"
    mapping = _binary_mapping_disk(isolated_ws, "runtime-dotted.toml", src)
    require_int(require_path(mapping, prefix, leaf), n)
    _require_same_mapping(mapping, _string_mapping(src))


def test_fp02_scalar_representative_binary_matches_string(isolated_ws):
    mapping = _binary_mapping_disk(isolated_ws, "escape-e.toml", _NAMED_ESCAPE)
    value = require_path(mapping, "k")
    require_str(value, chr(27))
    assert ord(value) == 27
    _require_same_mapping(mapping, _string_mapping(_NAMED_ESCAPE))


def test_runtime_fp02_scalar_binary_matches_string(isolated_ws):
    key = runtime_token()
    code = 0x41 + (runtime_int() % 26)
    assert code != 27
    src = f'{key} = "\\x{code:02x}"\n'
    mapping = _binary_mapping_disk(isolated_ws, "runtime-x.toml", src)
    require_str(require_path(mapping, key), chr(code))
    _require_same_mapping(mapping, _string_mapping(src))


def test_v11_inline_table_binary_matches_string(isolated_ws):
    mapping = _binary_mapping_disk(isolated_ws, "inline.toml", _NAMED_INLINE)
    table = require_path(mapping, "t")
    assert is_mapping(table)
    require_int(require_path(mapping, "t", "c"), 1)
    assert set(table) == {"c"}
    _require_same_mapping(mapping, _string_mapping(_NAMED_INLINE))


def test_runtime_v11_inline_table_binary_matches_string(isolated_ws):
    key, inner = runtime_token(), runtime_token()
    n = runtime_int()
    src = f"{key} = {{\n{inner} = {n},\n}}\n"
    mapping = _binary_mapping_disk(isolated_ws, "runtime-inline.toml", src)
    table = require_path(mapping, key)
    assert is_mapping(table)
    require_int(require_path(mapping, key, inner), n)
    assert set(table) == {inner}
    _require_same_mapping(mapping, _string_mapping(src))


# ---------------------------------------------------------------------------
# E. Text-mode file object: type error, not decode error
# ---------------------------------------------------------------------------


def test_text_mode_file_refused_as_type_error(isolated_ws):
    baseline = _binary_mapping_disk(isolated_ws, "named.bin.toml", _NAMED_ROOT)
    _assert_named_root(baseline)

    print(f"text disk source={_NAMED_ROOT!r}", flush=True)
    with isolated_ws.text_source("named.txt", _NAMED_ROOT) as fp:
        result = parse_binary(fp)
    print(
        f"text disk exception={type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    require_type_error(result)


def test_runtime_text_mode_file_refused_as_type_error(isolated_ws):
    key = runtime_token()
    n = runtime_int()
    src = f"{key} = {n}\n"
    baseline = _binary_mapping_disk(isolated_ws, "runtime.bin.toml", src)
    require_int(require_path(baseline, key), n)

    print(f"text disk source={src!r}", flush=True)
    with isolated_ws.text_source("runtime.txt", src) as fp:
        result = parse_binary(fp)
    print(
        f"text disk exception={type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    _assert_text_mode_type_error(result)


def test_text_buffer_refused_as_type_error():
    baseline = _binary_mapping_buffer(_NAMED_ROOT)
    _assert_named_root(baseline)

    print(f"text buffer source={_NAMED_ROOT!r}", flush=True)
    result = parse_binary(text_buffer(_NAMED_ROOT))
    print(
        f"text buffer exception={type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    require_type_error(result)


def test_runtime_text_buffer_refused_as_type_error():
    key = runtime_token()
    n = runtime_int()
    src = f"{key} = {n}\n"
    baseline = _binary_mapping_buffer(src)
    require_int(require_path(baseline, key), n)

    print(f"text buffer source={src!r}", flush=True)
    result = parse_binary(text_buffer(src))
    print(
        f"text buffer exception={type(result.exception).__name__ if result.exception else None}",
        flush=True,
    )
    _assert_text_mode_type_error(result)


# ---------------------------------------------------------------------------
# F. Non-UTF-8 bytes: call does not succeed, no mapping
# ---------------------------------------------------------------------------


def test_invalid_utf8_does_not_succeed(isolated_ws):
    _valid_utf8_baseline_disk(isolated_ws, "valid.toml")

    prefix = runtime_token()
    raw = lax_success_invalid_utf8(key_prefix=prefix, kind="high_byte")
    print(f"invalid utf8 high_byte={raw!r}", flush=True)
    _lax_invariant(raw)

    with isolated_ws.binary_source("invalid.toml", raw) as fp:
        result = parse_binary(fp)
    _assert_non_utf8_unsuccessful(result)


def test_invalid_utf8_sibling_does_not_succeed(isolated_ws):
    _valid_utf8_baseline_disk(isolated_ws, "valid-sibling.toml")

    prefix = runtime_token()
    raw = lax_success_invalid_utf8(key_prefix=prefix, kind="incomplete_c3")
    print(f"invalid utf8 incomplete_c3={raw!r}", flush=True)
    _lax_invariant(raw)

    with isolated_ws.binary_source("invalid-c3.toml", raw) as fp:
        result = parse_binary(fp)
    _assert_non_utf8_unsuccessful(result)


def test_invalid_utf8_via_binary_buffer():
    _valid_utf8_baseline_buffer()

    prefix = runtime_token()
    raw = lax_success_invalid_utf8(key_prefix=prefix, kind="high_byte")
    print(f"invalid utf8 buffer={raw!r}", flush=True)
    _lax_invariant(raw)

    result = parse_binary(binary_buffer(raw))
    _assert_non_utf8_unsuccessful(result)
