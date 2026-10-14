# feature: F01
"""Parse YAML documents (FP-01).

Assertions stay at the PRD's precision: constructed types and values
the sentences name, identity of aliases, the two parse entries on empty
and multi-document streams, duplicate-key policy, quoted folding,
eight-digit escapes, digit-containing tag handles, and failure reports
that carry a supplied source-path label and present line-break count
one versus zero. Exception class names, failure wording, field names,
and zero- vs one-based numbering of that count are not pinned.
"""

from __future__ import annotations

import pytest

from _harness import load, load_all
from F01_helpers import require_line_break_counts
from _helpers import (
    core_int_token,
    digit_tag_handle,
    distinct_core_ints,
    eight_hex_scalar,
    is_number_not_string,
    load_utf16_units,
    mapping_get,
    observer_visible_report,
    report_has_label,
    require_document,
    require_parse_failure,
    require_plain_mapping,
    same_identity,
    unique_token,
    with_json_compat,
    with_source_path_label,
)

ANSWER_42 = "answer: 42"
FOO_BAR = "foo: bar"
ONE_THEN_TWO = "1\n---\n2\n"
TWO_EMPTY_DOCS = "--- # first document\n--- # second document\n"
WS_COMMENT = "   \n# comment\n"
DUP_A_1_2 = "a: 1\na: 2"
PUBLIC_TAG_STREAM = "%TAG !a1! tag:yaml.org,2002:\n---\n!a1!str 123"
PUBLIC_TAG_WITHOUT_DIRECTIVE = "---\n!a1!str 123"
BARE_TWO_MARKERS = "---\n---\n"
OTHER_WHITESPACE = "\t\n"

_UTF16_MALFORMED = {
    "lone_surrogate_pair": (0xDC00, 0xD800),
    "unpaired_surrogate_other": (0xD800,),
}


# ---------------------------------------------------------------------------
# A. Single-document Core: mapping / scalar / sequence, BOM ignored
# ---------------------------------------------------------------------------


def test_answer_42_is_number_under_default_core():
    result = load(ANSWER_42)
    doc = require_document(result)
    require_plain_mapping(doc)
    answer = mapping_get(doc, "answer")
    print(f"answer={answer!r} type={type(answer).__name__}", flush=True)
    assert is_number_not_string(answer, 42), (
        f"answer must be the number 42, not a string; got {answer!r}"
    )


def test_runtime_mapping_value_is_number_not_string():
    key = unique_token()
    number = core_int_token()
    source = f"{key}: {number}"
    print(f"source={source!r}", flush=True)
    doc = require_document(load(source))
    value = mapping_get(doc, key)
    print(f"value={value!r} type={type(value).__name__}", flush=True)
    assert is_number_not_string(value, number), (
        f"{key} must be the number {number}, not a string; got {value!r}"
    )


def test_bare_scalar_and_sequence_single_document():
    hello = require_document(load("hello"))
    print(f"bare={hello!r}", flush=True)
    assert hello == "hello"
    assert isinstance(hello, str)
    seq = require_document(load("- a\n- b"))
    print(f"seq={seq!r}", flush=True)
    assert seq == ["a", "b"]


def test_runtime_bare_scalar_single_document():
    word = unique_token()
    print(f"word={word!r}", flush=True)
    value = require_document(load(word))
    assert value == word
    assert isinstance(value, str)
    number = core_int_token()
    print(f"bare-int={number!r}", flush=True)
    numeric = require_document(load(str(number)))
    assert is_number_not_string(numeric, number), (
        f"bare document {number} must be the number, not a string; got {numeric!r}"
    )


def test_runtime_sequence_items_in_order():
    first, second = unique_token(), unique_token()
    source = f"- {first}\n- {second}"
    print(f"source={source!r}", flush=True)
    seq = require_document(load(source))
    assert seq == [first, second]
    swapped = f"- {second}\n- {first}"
    print(f"swapped={swapped!r}", flush=True)
    assert require_document(load(swapped)) == [second, first]
    number = core_int_token()
    three = f"- {first}\n- {number}\n- {second}"
    print(f"three={three!r}", flush=True)
    got = require_document(load(three))
    assert got == [first, number, second]
    assert is_number_not_string(got[1], number), (
        f"sequence item {number} must be the number, not a string; got {got[1]!r}"
    )


def test_leading_bom_does_not_change_foo_bar():
    plain = require_document(load(FOO_BAR))
    bom = require_document(load("\ufeff" + FOO_BAR))
    print(f"plain={mapping_get(plain, 'foo')!r} bom={mapping_get(bom, 'foo')!r}", flush=True)
    assert mapping_get(plain, "foo") == "bar"
    assert mapping_get(bom, "foo") == "bar"
    assert mapping_get(plain, "foo") == mapping_get(bom, "foo")


def test_leading_bom_ignored_on_runtime_mapping():
    key, word = unique_token(), unique_token()
    body = f"{key}: {word}"
    print(f"body={body!r}", flush=True)
    plain = require_document(load(body))
    bom = require_document(load("\ufeff" + body))
    assert mapping_get(plain, key) == word
    assert mapping_get(bom, key) == word


# ---------------------------------------------------------------------------
# B. Multi-document: order, two empty docs, empty stream is []
# ---------------------------------------------------------------------------


def test_two_documents_one_then_two_in_order():
    docs = require_document(load_all(ONE_THEN_TWO))
    print(f"docs={docs!r}", flush=True)
    assert isinstance(docs, list)
    assert len(docs) == 2
    assert is_number_not_string(docs[0], 1)
    assert is_number_not_string(docs[1], 2)


def test_two_runtime_integers_order_follows_stream():
    left, right = distinct_core_ints(2)
    source = f"{left}\n---\n{right}\n"
    swapped = f"{right}\n---\n{left}\n"
    print(f"source={source!r} swapped={swapped!r}", flush=True)
    docs = require_document(load_all(source))
    assert docs == [left, right]
    assert is_number_not_string(docs[0], left)
    assert is_number_not_string(docs[1], right)
    swapped_docs = require_document(load_all(swapped))
    assert swapped_docs == [right, left]


def test_three_runtime_documents_in_order():
    first, second, third = distinct_core_ints(3)
    source = f"{first}\n---\n{second}\n---\n{third}\n"
    swapped_tail = f"{first}\n---\n{third}\n---\n{second}\n"
    print(f"source={source!r}", flush=True)
    docs = require_document(load_all(source))
    assert docs == [first, second, third]
    tail = require_document(load_all(swapped_tail))
    assert tail == [first, third, second]


def test_two_document_start_markers_are_two_nulls():
    docs = require_document(load_all(TWO_EMPTY_DOCS))
    print(f"two-empty={docs!r}", flush=True)
    assert isinstance(docs, list)
    assert len(docs) == 2
    assert docs[0] is None
    assert docs[1] is None


def test_two_document_start_markers_class_are_two_nulls():
    empty = require_document(load_all(""))
    print(f"empty-stream={empty!r}", flush=True)
    assert empty == []
    bare = require_document(load_all(BARE_TWO_MARKERS))
    print(f"bare-two-markers={bare!r}", flush=True)
    assert isinstance(bare, list)
    assert len(bare) == 2
    assert bare[0] is None
    assert bare[1] is None
    assert bare != empty
    first, second = unique_token(), unique_token()
    runtime = f"--- # {first}\n--- # {second}\n"
    print(f"runtime-two-markers={runtime!r}", flush=True)
    runtime_docs = require_document(load_all(runtime))
    assert isinstance(runtime_docs, list)
    assert len(runtime_docs) == 2
    assert runtime_docs[0] is None
    assert runtime_docs[1] is None
    assert runtime_docs != empty


def test_empty_text_load_all_empty_list():
    docs = require_document(load_all(""))
    print(f"empty-stream={docs!r}", flush=True)
    assert docs == []
    assert len(docs) == 0
    two_nulls = require_document(load_all(TWO_EMPTY_DOCS))
    assert two_nulls != docs


def test_whitespace_and_comments_load_all_empty_list():
    docs = require_document(load_all(WS_COMMENT))
    print(f"ws-comment={docs!r}", flush=True)
    assert docs == []
    assert len(docs) == 0


def test_whitespace_and_comments_class_load_all_empty_list():
    comment = unique_token()
    runtime_comment = f"# {comment}\n"
    print(f"runtime-comment={runtime_comment!r}", flush=True)
    comment_docs = require_document(load_all(runtime_comment))
    assert comment_docs == []
    print(f"other-whitespace={OTHER_WHITESPACE!r}", flush=True)
    ws_docs = require_document(load_all(OTHER_WHITESPACE))
    assert ws_docs == []


# ---------------------------------------------------------------------------
# C. The two entries differ on empty streams and multi-document streams
# ---------------------------------------------------------------------------


def test_empty_text_fails_single_succeeds_multi():
    multi = require_document(load_all(""))
    print(f"multi empty={multi!r}", flush=True)
    assert multi == []
    require_parse_failure(load(""))


def test_whitespace_comments_fails_single_succeeds_multi():
    multi = require_document(load_all(WS_COMMENT))
    print(f"multi ws={multi!r}", flush=True)
    assert multi == []
    require_parse_failure(load(WS_COMMENT))


def test_whitespace_comments_class_fails_single_succeeds_multi():
    comment = unique_token()
    runtime_comment = f"# {comment}\n"
    print(f"runtime-comment={runtime_comment!r}", flush=True)
    comment_multi = require_document(load_all(runtime_comment))
    assert comment_multi == []
    require_parse_failure(load(runtime_comment))
    print(f"other-whitespace={OTHER_WHITESPACE!r}", flush=True)
    ws_multi = require_document(load_all(OTHER_WHITESPACE))
    assert ws_multi == []
    require_parse_failure(load(OTHER_WHITESPACE))


def test_two_documents_fail_single_succeed_multi():
    multi = require_document(load_all(TWO_EMPTY_DOCS))
    print(f"multi two-empty={multi!r}", flush=True)
    assert len(multi) == 2
    assert multi[0] is None and multi[1] is None
    require_parse_failure(load(TWO_EMPTY_DOCS))


def test_one_then_two_fails_single_document():
    multi = require_document(load_all(ONE_THEN_TWO))
    print(f"multi 1/2={multi!r}", flush=True)
    assert multi == [1, 2]
    require_parse_failure(load(ONE_THEN_TWO))


def test_three_runtime_documents_fail_single_document():
    first, second, third = distinct_core_ints(3)
    source = f"{first}\n---\n{second}\n---\n{third}\n"
    print(f"source={source!r}", flush=True)
    multi = require_document(load_all(source))
    assert multi == [first, second, third]
    require_parse_failure(load(source))


# ---------------------------------------------------------------------------
# D. Anchors and aliases share identity, including recursive defaults
# ---------------------------------------------------------------------------


def test_alias_shares_identity_with_anchor():
    source = "base: &base { a: 1 }\ncopy: *base"
    doc = require_document(load(source))
    base = mapping_get(doc, "base")
    copy = mapping_get(doc, "copy")
    print(f"base={base!r} copy={copy!r} same={same_identity(base, copy)}", flush=True)
    assert same_identity(copy, base)
    assert is_number_not_string(mapping_get(base, "a"), 1)


def test_runtime_alias_shares_identity():
    key, copy_key, third_key, anchor = (
        unique_token(),
        unique_token(),
        unique_token(),
        unique_token(),
    )
    number = core_int_token()
    source = (
        f"{key}: &{anchor} {{ a: {number} }}\n"
        f"{copy_key}: *{anchor}\n"
        f"{third_key}: *{anchor}"
    )
    print(f"source={source!r}", flush=True)
    doc = require_document(load(source))
    base = mapping_get(doc, key)
    copy = mapping_get(doc, copy_key)
    third = mapping_get(doc, third_key)
    assert same_identity(copy, base)
    assert same_identity(third, base)
    assert same_identity(third, copy)


def test_runtime_completed_sequence_alias_shares_identity():
    items_key, copy_key, anchor = unique_token(), unique_token(), unique_token()
    first, second = unique_token(), unique_token()
    source = (
        f"{items_key}: &{anchor} [{first}, {second}]\n"
        f"{copy_key}: *{anchor}"
    )
    print(f"source={source!r}", flush=True)
    doc = require_document(load(source))
    items = mapping_get(doc, items_key)
    copy = mapping_get(doc, copy_key)
    print(
        f"items={items!r} copy={copy!r} same={same_identity(copy, items)}",
        flush=True,
    )
    assert same_identity(copy, items)
    assert items == [first, second]


def test_recursive_alias_default_sequence_is_self():
    seq = require_document(load("&a [*a]"))
    print(f"seq type={type(seq).__name__} len={len(seq) if isinstance(seq, list) else 'n/a'}", flush=True)
    assert isinstance(seq, list)
    assert len(seq) == 1
    assert same_identity(seq[0], seq)


def test_recursive_alias_runtime_sequence_is_self():
    anchor = unique_token()
    source = f"&{anchor} [*{anchor}]"
    print(f"source={source!r}", flush=True)
    seq = require_document(load(source))
    assert isinstance(seq, list)
    assert len(seq) == 1
    assert same_identity(seq[0], seq)


def test_recursive_alias_default_mapping_is_self():
    anchor = unique_token()
    field = unique_token()
    source = f"&{anchor} {{ {field}: *{anchor} }}"
    print(f"source={source!r}", flush=True)
    doc = require_document(load(source))
    inner = mapping_get(doc, field)
    assert same_identity(inner, doc)


# ---------------------------------------------------------------------------
# E. Duplicate keys: default reject; JSON compat later pair wins
# ---------------------------------------------------------------------------


def test_duplicate_keys_rejected_by_default():
    failed = load(DUP_A_1_2)
    error = require_parse_failure(failed)
    print(
        f"dup-default ok={failed.ok!r} report={observer_visible_report(error)!r}",
        flush=True,
    )
    assert failed.ok is False


def test_json_compat_later_pair_wins():
    compat = require_document(load(DUP_A_1_2, with_json_compat()))
    later = mapping_get(compat, "a")
    print(f"compat a={later!r}", flush=True)
    assert is_number_not_string(later, 2)
    require_parse_failure(load(DUP_A_1_2))


def test_json_compat_later_smaller_wins():
    larger, smaller = sorted(distinct_core_ints(2), reverse=True)
    source = f"a: {larger}\na: {smaller}"
    print(f"source={source!r}", flush=True)
    doc = require_document(load(source, with_json_compat()))
    value = mapping_get(doc, "a")
    assert is_number_not_string(value, smaller)
    assert value != larger


def test_runtime_duplicate_later_wins_under_json_compat():
    key = unique_token()
    larger, smaller = sorted(distinct_core_ints(2), reverse=True)
    source = f"{key}: {larger}\n{key}: {smaller}"
    print(f"source={source!r}", flush=True)
    require_parse_failure(load(source))
    doc = require_document(load(source, with_json_compat()))
    assert is_number_not_string(mapping_get(doc, key), smaller)


def test_nested_mapping_duplicate_key_policy():
    outer = unique_token()
    inner = unique_token()
    larger, smaller = sorted(distinct_core_ints(2), reverse=True)
    source = f"{outer}:\n  {inner}: {larger}\n  {inner}: {smaller}\n"
    print(f"source={source!r}", flush=True)
    require_parse_failure(load(source))
    doc = require_document(load(source, with_json_compat()))
    nested = mapping_get(doc, outer)
    assert is_number_not_string(mapping_get(nested, inner), smaller)


def test_json_compat_third_pair_later_wins():
    key = unique_token()
    first_val, second_val, last = sorted(distinct_core_ints(3), reverse=True)
    source = f"{key}: {first_val}\n{key}: {second_val}\n{key}: {last}\n"
    print(f"source={source!r}", flush=True)
    doc = require_document(load(source, with_json_compat()))
    value = mapping_get(doc, key)
    assert is_number_not_string(value, last)
    assert value != first_val
    assert value != second_val
    assert value != max(first_val, second_val, last)
    require_parse_failure(load(source))


def test_json_compat_applies_to_every_document():
    first_hi, first_lo, second_hi, second_lo = _two_later_smaller_pairs()
    source = (
        f"---\na: {first_hi}\na: {first_lo}\n"
        f"---\na: {second_hi}\na: {second_lo}\n"
    )
    print(f"source={source!r}", flush=True)
    docs = require_document(load_all(source, with_json_compat()))
    assert isinstance(docs, list)
    assert len(docs) == 2
    assert is_number_not_string(mapping_get(docs[0], "a"), first_lo)
    assert is_number_not_string(mapping_get(docs[1], "a"), second_lo)
    require_parse_failure(load_all(source))


def test_runtime_json_compat_every_document():
    key_a, key_b = unique_token(), unique_token()
    first_hi, first_lo, second_hi, second_lo = _two_later_smaller_pairs()
    source = (
        f"---\n{key_a}: {first_hi}\n{key_a}: {first_lo}\n"
        f"---\n{key_b}: {second_hi}\n{key_b}: {second_lo}\n"
    )
    print(f"source={source!r}", flush=True)
    docs = require_document(load_all(source, with_json_compat()))
    assert is_number_not_string(mapping_get(docs[0], key_a), first_lo)
    assert is_number_not_string(mapping_get(docs[1], key_b), second_lo)
    require_parse_failure(load_all(source))


def _two_later_smaller_pairs() -> tuple[int, int, int, int]:
    numbers = distinct_core_ints(4)
    first = sorted(numbers[:2], reverse=True)
    second = sorted(numbers[2:], reverse=True)
    return first[0], first[1], second[0], second[1]


# ---------------------------------------------------------------------------
# F. Quoted folding, eight-digit Unicode, digit-containing %TAG handles
# ---------------------------------------------------------------------------


def test_double_quoted_crlf_folds_to_space():
    value = require_document(load('"folded\r\nto a space"'))
    print(f"dq-crlf={value!r}", flush=True)
    assert value == "folded to a space"
    assert "\r" not in value
    assert value != "folded  to a space"


def test_double_quoted_lf_folds_same_as_crlf():
    crlf = require_document(load('"folded\r\nto a space"'))
    lf = require_document(load('"folded\nto a space"'))
    print(f"crlf={crlf!r} lf={lf!r}", flush=True)
    assert crlf == "folded to a space"
    assert lf == crlf


def test_double_quoted_backslash_joins_without_space():
    value = require_document(load('"folded\\\r\nto a space"'))
    print(f"dq-join={value!r}", flush=True)
    assert value == "foldedto a space"


def test_single_quoted_crlf_folds_to_space():
    value = require_document(load("'folded\r\nto a space'"))
    print(f"sq-crlf={value!r}", flush=True)
    assert value == "folded to a space"


def test_single_quoted_has_no_backslash_join():
    value = require_document(load("'folded\\\r\nto a space'"))
    print(f"sq-backslash={value!r}", flush=True)
    assert value != "foldedto a space"
    assert "\r" not in value
    assert "\n" not in value
    assert "folded" in value
    assert " to a space" in value


def test_quoted_folding_runtime_words():
    first, second = unique_token(), unique_token()
    folded = f"{first} {second}"
    joined = f"{first}{second}"
    dq = require_document(load(f'"{first}\r\n{second}"'))
    print(f"runtime dq={dq!r}", flush=True)
    assert dq == folded
    assert "\r" not in dq
    dq_join = require_document(load(f'"{first}\\\r\n{second}"'))
    assert dq_join == joined
    sq = require_document(load(f"'{first}\r\n{second}'"))
    assert sq == folded
    sq_bs = require_document(load(f"'{first}\\\r\n{second}'"))
    print(f"runtime sq-bs={sq_bs!r}", flush=True)
    assert sq_bs != joined
    assert "\r" not in sq_bs
    assert "\n" not in sq_bs
    assert first in sq_bs
    assert second in sq_bs
    assert f" {second}" in sq_bs


def test_eight_digit_unicode_escape():
    value = require_document(load('"\\U0001F600"'))
    print(f"u1f600={value!r}", flush=True)
    assert value == "\U0001f600"


def test_eight_digit_unicode_escape_runtime_codepoints():
    hex8, expected = eight_hex_scalar()
    source = f'"\\U{hex8}"'
    print(f"source={source!r} expected={expected!r}", flush=True)
    value = require_document(load(source))
    assert value == expected
    token = unique_token()
    code = 0x00A1 + (int(token[1:5], 16) % 0x0C5F)
    bmp_hex = f"{code:08X}"
    bmp_expected = chr(code)
    bmp_source = f'"\\U{bmp_hex}"'
    print(f"bmp-source={bmp_source!r} expected={bmp_expected!r}", flush=True)
    bmp_value = require_document(load(bmp_source))
    assert bmp_value == bmp_expected


def test_tag_handle_with_digits():
    value = require_document(load(PUBLIC_TAG_STREAM))
    print(f"tag-handle={value!r}", flush=True)
    assert value == "123"
    assert isinstance(value, str)
    assert value != 123


def test_tag_handle_without_directive_is_unknown():
    tagged = require_document(load(PUBLIC_TAG_STREAM))
    print(f"with directive={tagged!r}", flush=True)
    assert tagged == "123"
    print(f"without directive={PUBLIC_TAG_WITHOUT_DIRECTIVE!r}", flush=True)
    require_parse_failure(load(PUBLIC_TAG_WITHOUT_DIRECTIVE))


def test_tag_handle_with_digits_non_public():
    handle = digit_tag_handle()
    word = unique_token()
    source = f"%TAG {handle} tag:yaml.org,2002:\n---\n{handle}str {word}"
    print(f"source={source!r}", flush=True)
    value = require_document(load(source))
    assert value == word
    assert isinstance(value, str)
    without = f"---\n{handle}str {word}"
    print(f"without directive={without!r}", flush=True)
    require_parse_failure(load(without))


# ---------------------------------------------------------------------------
# G. Unknown tags, wrong kind, named malformed inputs
# ---------------------------------------------------------------------------


def test_unknown_explicit_tag_rejected():
    failed = load("!unknown_scalar_tag foo")
    error = require_parse_failure(failed)
    print(
        f"unknown-tag ok={failed.ok!r} report={observer_visible_report(error)!r}",
        flush=True,
    )
    assert failed.ok is False


def test_runtime_unknown_explicit_tag_rejected():
    tag = unique_token()
    word = unique_token()
    source = f"!{tag} {word}"
    print(f"source={source!r}", flush=True)
    failed = load(source)
    error = require_parse_failure(failed)
    print(
        f"runtime-unknown-tag ok={failed.ok!r} report={observer_visible_report(error)!r}",
        flush=True,
    )
    assert failed.ok is False


def test_explicit_tag_wrong_node_kind_rejected():
    failed = load("--- !!str [not a scalar]")
    error = require_parse_failure(failed)
    print(
        f"wrong-kind ok={failed.ok!r} report={observer_visible_report(error)!r}",
        flush=True,
    )
    assert failed.ok is False


def test_explicit_tag_wrong_kind_other_sequence_rejected():
    first, second = unique_token(), unique_token()
    source = f"!!str [{first}, {second}]"
    print(f"source={source!r}", flush=True)
    failed = load(source)
    error = require_parse_failure(failed)
    print(
        f"wrong-kind-other ok={failed.ok!r} report={observer_visible_report(error)!r}",
        flush=True,
    )
    assert failed.ok is False


def _malformed_cases() -> list[tuple[str, str]]:
    word = unique_token()
    other = unique_token()
    alias = unique_token()
    at_len = 2 + (int(word[1], 16) % 5)
    return [
        ("at_only", "@"),
        ("at_only_longer", "@" * at_len),
        ("null_byte_foobar", "foo\x00bar"),
        ("null_byte_runtime", f"{word}\x00{other}"),
        ("unclosed_single", "'still-open"),
        ("unclosed_single_runtime", f"'{word}"),
        ("unclosed_double", '"still-open'),
        ("unclosed_double_runtime", f'"{word}'),
        ("alias_never_anchored", "*no_such_anchor"),
        ("alias_never_anchored_runtime", f"*{alias}"),
        ("yaml_2_0_directive", "%YAML 2.0\n---\nx\n"),
        ("flow_map_wrong_close", "{ foo: bar ]"),
        ("flow_map_runtime_keys", f"{{ {word}: {other} ]"),
        ("nonprintable_0x01", "\x01"),
        ("nonprintable_0x7f", "\x7f"),
        ("nonprintable_0x9f", "\x9f"),
        ("nonprintable_0x01_midstring", f"{word}\x01{other}"),
        ("lone_surrogate_pair", ""),
        ("unpaired_surrogate_other", ""),
        ("quoted_0x03_double", '"\x03"'),
        ("quoted_0x03_single", "'\x03'"),
        ("quoted_0x03_interior_double", f'"{word}\x03{other}"'),
        ("quoted_0x03_interior_single", f"'{word}\x03{other}'"),
    ]


_MALFORMED_CASES = _malformed_cases()


@pytest.mark.parametrize(
    "label,source",
    [pytest.param(name, text, id=name) for name, text in _MALFORMED_CASES],
)
def test_malformed_inputs_fail_both_entries(label, source):
    print(f"case={label!r} source={source!r}", flush=True)
    units = _UTF16_MALFORMED.get(label)
    if units is not None:
        # Unpaired UTF-16 units are not UTF-8; build them in-process, then parse.
        single = load_utf16_units(units)
        multi = load_utf16_units(units, multi=True)
    else:
        single = load(source)
        multi = load_all(source)
    require_parse_failure(single)
    require_parse_failure(multi)
    print(f"single.ok={single.ok!r} multi.ok={multi.ok!r}", flush=True)
    assert single.ok is False
    assert multi.ok is False


def test_failed_parse_not_usable_document():
    success = require_document(load(ANSWER_42))
    print(f"success answer={mapping_get(success, 'answer')!r}", flush=True)
    assert is_number_not_string(mapping_get(success, "answer"), 42)
    failed = load("@")
    require_parse_failure(failed)
    assert failed.ok is False


# ---------------------------------------------------------------------------
# H. Source-path label in the failure report; line-break count one vs zero
# ---------------------------------------------------------------------------


def test_source_path_label_in_failure_report():
    require_document(load(ANSWER_42))
    error = require_parse_failure(load("@", with_source_path_label("my.yml")))
    report = observer_visible_report(error)
    print(f"report={report!r}", flush=True)
    assert report_has_label(error, "my.yml")


def test_runtime_source_path_label_in_failure_report():
    label = unique_token() + ".yml"
    print(f"label={label!r}", flush=True)
    error = require_parse_failure(load("@", with_source_path_label(label)))
    report = observer_visible_report(error)
    print(f"report={report!r}", flush=True)
    assert report_has_label(error, label)


def test_source_path_label_on_other_failure_both_entries():
    label = unique_token() + ".path"
    source = f"'{unique_token()}"
    print(f"label={label!r} source={source!r}", flush=True)
    single = require_parse_failure(load(source, with_source_path_label(label)))
    multi = require_parse_failure(load_all(source, with_source_path_label(label)))
    assert report_has_label(single, label)
    assert report_has_label(multi, label)


def test_failure_report_identifies_later_line_not_first():
    label = unique_token() + ".src"
    later_src = "a: 1\r\n@"
    earlier_src = "@\r\na: 1"
    later_err = require_parse_failure(
        load(later_src, with_source_path_label(label))
    )
    earlier_err = require_parse_failure(
        load(earlier_src, with_source_path_label(label))
    )
    assert report_has_label(later_err, label)
    print(
        f"later_report={observer_visible_report(later_err)!r}",
        flush=True,
    )
    print(
        f"earlier_report={observer_visible_report(earlier_err)!r}",
        flush=True,
    )
    # mark.line counts the line breaks before the error site (CR/LF is
    # one break): one for the later line, zero for the first line.
    require_line_break_counts(later_err, earlier_err, label=label)
