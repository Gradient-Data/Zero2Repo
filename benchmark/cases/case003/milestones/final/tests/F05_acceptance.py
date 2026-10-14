# feature: F05
"""Serialize JavaScript values to YAML (FP-05).

Assertions stay at the PRD's precision: dump-then-parse types, plain vs
quoted effect, presentation contrasts that differ in one named switch,
anchor/alias identity, and dump failure that yields no YAML text.
Exception types, failure wording, anchor names, fold markers, and
float spellings the PRD does not name are not pinned.
"""

from __future__ import annotations

from _harness import JsMap, dump, load
from F05_helpers import exponent_only_float_token, require_no_flow_square_inner_space
from _helpers import (
    YAML11_FALSE_WORDS,
    YAML11_TRUE_WORDS,
    anchor_tag_order_on_node,
    complex_key_map,
    core_int_token,
    dump_cycle,
    dump_identical_pair,
    dump_identical_set,
    dump_then_parse,
    flow_square_inner_space,
    function_value,
    has_float_marker_after_strip,
    has_nested_dash_on_following_line,
    has_same_line_nested_dashes,
    has_space_after_colon,
    has_space_after_comma,
    is_finite_number,
    is_js_null,
    is_nan_number,
    is_neg_inf,
    is_number_not_string,
    is_plain_scalar_dump,
    is_pos_inf,
    is_string_text,
    key_and_dash_indents,
    mapping_get,
    mapping_key_position,
    mapping_value_is_plain,
    merge_dump_options,
    quoted_token_present,
    regexp_value,
    relative_nested_indent,
    require_document,
    require_double_quoted_scalar,
    require_dump_failure,
    require_empty_yaml_text,
    require_flow_container,
    require_flow_mapping,
    require_plain_mapping,
    require_quoted_scalar_dump,
    require_real_map,
    require_sequence,
    require_single_quoted_scalar,
    require_yaml_text,
    same_identity,
    scalar_word_content_lines,
    undefined_value,
    unique_token,
    with_core_schema,
    with_double_quote_style,
    with_flow_bracket_padding,
    with_flow_depth,
    with_flow_no_colon_space,
    with_flow_no_comma_space,
    with_indent_width,
    with_json_schema,
    with_line_width,
    with_nested_sequence_next_line,
    with_no_extra_sequence_indent,
    with_no_reuse,
    with_quote_flow_keys,
    with_quote_non_key_strings,
    with_real_map_schema,
    with_single_quote_style,
    with_skip_unrepresentable,
    with_sort_keys,
    with_tag_before_anchor,
    with_yaml11_schema,
    zero_o_int_token,
)

NAMED_LONG_WORDS = (
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
)
NAMED_LONG_SCALAR = " ".join(NAMED_LONG_WORDS)
STRUCTURE_QUOTED = (
    "---",
    "...",
    "--- x",
    "... x",
    "- value",
    "? value",
    "foo: bar",
    "foo:",
    "foo #bar",
)
STRUCTURE_PLAIN = (
    "---x",
    "...x",
    "http://example.com",
    "foo#bar",
)
TYPE_COLLISION = ("true", "42", "99.9", "null")
COLON_FLOW = (":{", ":[", ":,", ":}", ":]", "x:{")
OTHER_COLON_FLOW = (":[", ":,", ":}", ":]")
YAML11_BOOL_WORDS = YAML11_TRUE_WORDS + YAML11_FALSE_WORDS
SET_TAG = "!!set"
INT_TAG = "!!int"


def _dumped(value, options=None) -> str:
    text = require_yaml_text(dump(value, options))
    print(f"dumped={text!r}", flush=True)
    return text


def _parse_string(text: str, options=None) -> str:
    value = require_document(load(text, options))
    print(f"parsed={value!r} type={type(value).__name__}", flush=True)
    return value


def _runtime_plain_word() -> str:
    word = unique_token()
    if word == "hello":
        word = unique_token()
    print(f"runtime_word={word!r}", flush=True)
    return word


def _distinct_runtime_ints() -> tuple[int, int]:
    left = core_int_token()
    right = core_int_token()
    guard = 0
    while right == left:
        right = core_int_token()
        guard += 1
        if guard > 32:
            right = left + 3
            break
    print(f"runtime_ints={left},{right}", flush=True)
    return left, right


def _lex_reversed_pair() -> tuple[str, str]:
    left, right = unique_token(), unique_token()
    guard = 0
    while left == right or left < right:
        left, right = unique_token(), unique_token()
        guard += 1
        if guard > 64:
            left, right = "zz" + unique_token(), "aa" + unique_token()
            break
    print(f"lex_reversed first={left!r} second={right!r}", flush=True)
    return left, right


def _assert_quoted_round_trip(scalar: str, dump_options=None, load_options=None) -> str:
    text = _dumped(scalar, dump_options)
    require_quoted_scalar_dump(text, scalar)
    parsed = _parse_string(text, load_options)
    assert is_string_text(parsed, scalar), (
        f"quoted dump of {scalar!r} must parse back as that string; "
        f"got {parsed!r}"
    )
    return text


# ---------------------------------------------------------------------------
# A. Default dump round-trip and schema-aware quoting
# ---------------------------------------------------------------------------


def test_dump_answer_42_round_trips_numeric():
    dumped = dump({"answer": 42})
    text = require_yaml_text(dumped)
    print(f"answer42_text={text!r}", flush=True)
    core_doc = require_document(load(text, with_core_schema()))
    yaml11_doc = require_document(load(text, with_yaml11_schema()))
    require_plain_mapping(core_doc)
    require_plain_mapping(yaml11_doc)
    core_answer = mapping_get(core_doc, "answer")
    yaml11_answer = mapping_get(yaml11_doc, "answer")
    print(
        f"core_answer={core_answer!r} yaml11_answer={yaml11_answer!r}",
        flush=True,
    )
    assert is_number_not_string(core_answer, 42), (
        f"Core parse of dumped answer must be the number 42; got {core_answer!r}"
    )
    assert is_number_not_string(yaml11_answer, 42), (
        f"YAML 1.1 parse of dumped answer must be the number 42; "
        f"got {yaml11_answer!r}"
    )


def test_dump_hello_is_plain_plus_newline():
    text = _dumped("hello")
    print(f"hello_plain={is_plain_scalar_dump(text, 'hello')}", flush=True)
    assert is_plain_scalar_dump(text, "hello"), (
        f"dump of hello must be the plain string plus a newline; got {text!r}"
    )


def test_dump_runtime_plain_word():
    yes_text = _dumped("yes")
    require_quoted_scalar_dump(yes_text, "yes")
    print(f"live_baseline_yes_quoted={yes_text!r}", flush=True)
    word = _runtime_plain_word()
    text = _dumped(word)
    assert is_plain_scalar_dump(text, word), (
        f"dump of {word!r} must be that word plus a newline; got {text!r}"
    )
    parsed = _parse_string(text)
    assert is_string_text(parsed, word), (
        f"plain dump of {word!r} must parse back as that string; got {parsed!r}"
    )


def test_dump_yes_quoted_under_default_schema():
    text = _dumped("yes")
    require_quoted_scalar_dump(text, "yes")
    parsed = _parse_string(text, with_yaml11_schema())
    assert is_string_text(parsed, "yes"), (
        f"YAML 1.1 parse of dumped yes must stay the string yes; got {parsed!r}"
    )
    plain_would_be_bool = require_document(load("yes\n", with_yaml11_schema()))
    print(f"plain_yes_yaml11={plain_would_be_bool!r}", flush=True)
    assert plain_would_be_bool is True, (
        "live baseline: plain yes under YAML 1.1 must be boolean true"
    )


def test_dump_yaml11_boolean_words_quoted():
    for word in YAML11_BOOL_WORDS:
        text = _dumped(word)
        print(f"bool_word={word!r} text={text!r}", flush=True)
        require_quoted_scalar_dump(text, word)
        parsed = _parse_string(text, with_yaml11_schema())
        assert is_string_text(parsed, word), (
            f"YAML 1.1 parse of dumped {word!r} must stay that string; "
            f"got {parsed!r}"
        )


def test_dump_yes_plain_under_json_schema():
    default_text = _dumped("yes")
    require_quoted_scalar_dump(default_text, "yes")
    json_text = _dumped("yes", with_json_schema())
    print(f"json_yes={json_text!r}", flush=True)
    assert is_plain_scalar_dump(json_text, "yes"), (
        f"JSON dump of yes must be the plain string plus a newline; "
        f"got {json_text!r}"
    )


def test_dump_type_collision_strings_quoted():
    for scalar in TYPE_COLLISION:
        _assert_quoted_round_trip(scalar, load_options=with_core_schema())


def test_dump_type_collision_strings_quoted_under_json():
    for scalar in TYPE_COLLISION:
        _assert_quoted_round_trip(
            scalar,
            dump_options=with_json_schema(),
            load_options=with_json_schema(),
        )


def test_dump_zero_o_and_exponent_float_quoted_under_default():
    public_octal = "0o123"
    _assert_quoted_round_trip(public_octal, load_options=with_core_schema())
    runtime_octal, _ = zero_o_int_token()
    print(f"runtime_octal={runtime_octal!r}", flush=True)
    _assert_quoted_round_trip(runtime_octal, load_options=with_core_schema())

    public_exp = "12e03"
    _assert_quoted_round_trip(public_exp, load_options=with_core_schema())
    runtime_exp = exponent_only_float_token()
    print(f"runtime_exp={runtime_exp!r}", flush=True)
    _assert_quoted_round_trip(runtime_exp, load_options=with_core_schema())


# ---------------------------------------------------------------------------
# B. Structure-like strings and leading / trailing spaces
# ---------------------------------------------------------------------------


def test_dump_structure_strings_quoted():
    for scalar in STRUCTURE_QUOTED:
        _assert_quoted_round_trip(scalar)

    quoted_marker = _dumped("---")
    plain_near = _dumped("---x")
    require_quoted_scalar_dump(quoted_marker, "---")
    assert is_plain_scalar_dump(plain_near, "---x")
    marker_left = quoted_marker.replace("x", "")
    near_left = plain_near.replace("x", "")
    print(
        f"marker_left={marker_left!r} near_left={near_left!r}",
        flush=True,
    )
    assert marker_left != near_left, (
        "after stripping the extra x, the quoted marker dump must still "
        "differ from the near-marker dump"
    )

    colon_space = _dumped("foo: bar")
    colon_url = _dumped("http://example.com")
    require_quoted_scalar_dump(colon_space, "foo: bar")
    assert is_plain_scalar_dump(colon_url, "http://example.com")
    hash_space = _dumped("foo #bar")
    hash_plain = _dumped("foo#bar")
    require_quoted_scalar_dump(hash_space, "foo #bar")
    assert is_plain_scalar_dump(hash_plain, "foo#bar")


def test_dump_near_structure_strings_stay_plain():
    quoted_marker = _dumped("---")
    require_quoted_scalar_dump(quoted_marker, "---")
    print(f"live_baseline_marker_quoted={quoted_marker!r}", flush=True)
    parsed_marker = _parse_string(quoted_marker)
    assert is_string_text(parsed_marker, "---"), (
        "live baseline: dump of --- must be quoted so a parse stays the string"
    )
    for scalar in STRUCTURE_PLAIN:
        text = _dumped(scalar)
        assert is_plain_scalar_dump(text, scalar), (
            f"dump of {scalar!r} must stay plain plus a newline; got {text!r}"
        )
        parsed = _parse_string(text)
        assert is_string_text(parsed, scalar), (
            f"plain dump of {scalar!r} must parse back as that string; "
            f"got {parsed!r}"
        )


def test_dump_leading_and_trailing_space_quoted():
    for scalar in (" leading space", "trailing space "):
        _assert_quoted_round_trip(scalar)


def test_dump_runtime_spaced_string_quoted():
    word = _runtime_plain_word()
    baseline = _dumped(word)
    assert is_plain_scalar_dump(baseline, word), (
        f"live baseline: {word!r} without spaces must dump plain"
    )
    spaced = f" {word} "
    _assert_quoted_round_trip(spaced)


# ---------------------------------------------------------------------------
# C. Quote style and quote-every-non-key-string
# ---------------------------------------------------------------------------


def test_dump_null_string_default_single_quotes():
    text = _dumped("null")
    require_quoted_scalar_dump(text, "null")
    require_single_quoted_scalar(text, "null")
    parsed = _parse_string(text)
    assert is_string_text(parsed, "null")


def test_dump_null_string_double_quote_style():
    default_text = _dumped("null")
    require_single_quoted_scalar(default_text, "null")
    text = _dumped("null", with_double_quote_style())
    require_double_quoted_scalar(text, "null")
    parsed = _parse_string(text)
    assert is_string_text(parsed, "null")


def test_dump_quote_style_on_other_quoted_string():
    scalar = "true"
    default_text = _dumped(scalar)
    require_quoted_scalar_dump(default_text, scalar)
    require_single_quoted_scalar(default_text, scalar)
    double_text = _dumped(scalar, with_double_quote_style())
    require_double_quoted_scalar(double_text, scalar)
    parsed = _parse_string(double_text)
    assert is_string_text(parsed, scalar)
    single_explicit = _dumped(scalar, with_single_quote_style())
    require_single_quoted_scalar(single_explicit, scalar)


def test_dump_quote_every_non_key_string():
    baseline = _dumped({"hello": "world"})
    print(f"hello_world_baseline={baseline!r}", flush=True)
    assert mapping_value_is_plain(baseline, "hello", "world"), (
        "live baseline: world must appear plain as the value"
    )
    assert not quoted_token_present(baseline, "hello")
    forced = _dumped({"hello": "world"}, with_quote_non_key_strings())
    print(f"hello_world_forced={forced!r}", flush=True)
    assert quoted_token_present(forced, "world"), (
        f"quote-every-non-key must quote world; got {forced!r}"
    )
    assert "hello:" in forced, f"key hello must remain present; got {forced!r}"
    assert not quoted_token_present(forced, "hello"), (
        f"key hello must stay unquoted; got {forced!r}"
    )
    parsed = require_document(load(forced))
    assert is_string_text(mapping_get(parsed, "hello"), "world")


def test_dump_quote_every_non_key_runtime_pair():
    key = _runtime_plain_word()
    value = _runtime_plain_word()
    forced = _dumped({key: value}, with_quote_non_key_strings())
    print(f"runtime_forced={forced!r}", flush=True)
    assert quoted_token_present(forced, value), (
        f"runtime value {value!r} must be quoted; got {forced!r}"
    )
    assert f"{key}:" in forced
    assert not quoted_token_present(forced, key), (
        f"runtime key {key!r} must stay unquoted; got {forced!r}"
    )
    parsed = require_document(load(forced))
    assert is_string_text(mapping_get(parsed, key), value)


# ---------------------------------------------------------------------------
# D. Large integers as floats; special-float round trip
# ---------------------------------------------------------------------------


def _assert_large_int_as_float(number: float) -> None:
    text = _dumped(number)
    print(
        f"large_int={number!r} float_marker={has_float_marker_after_strip(text)} "
        f"has_int_tag={INT_TAG in text}",
        flush=True,
    )
    assert INT_TAG not in text, f"dump of {number} must not write {INT_TAG}: {text!r}"
    assert has_float_marker_after_strip(text), (
        f"dump of {number} must keep a float marker after stripping digits; "
        f"got {text!r}"
    )
    for opts in (with_json_schema(), with_core_schema(), with_yaml11_schema()):
        parsed = require_document(load(text, opts))
        print(f"parsed_{number}={parsed!r} schema={opts}", flush=True)
        assert is_finite_number(parsed, number), (
            f"parse of dumped {number} must be that number; got {parsed!r}"
        )


def _assert_large_int_as_decimal(number: float) -> None:
    text = _dumped(number)
    print(
        f"decimal_int={number!r} float_marker={has_float_marker_after_strip(text)} "
        f"has_int_tag={INT_TAG in text}",
        flush=True,
    )
    assert INT_TAG not in text, f"dump of {number} must not write {INT_TAG}: {text!r}"
    assert not has_float_marker_after_strip(text), (
        f"dump of {number} must be a decimal integer form; got {text!r}"
    )
    for opts in (with_json_schema(), with_core_schema(), with_yaml11_schema()):
        parsed = require_document(load(text, opts))
        assert is_finite_number(parsed, number), (
            f"parse of dumped {number} must be that number; got {parsed!r}"
        )


def test_dump_1e21_as_float_round_trips():
    _assert_large_int_as_float(1e21)


def test_dump_1e20_as_decimal_integer():
    _assert_large_int_as_decimal(1e20)


def test_dump_runtime_large_integers_threshold():
    _assert_large_int_as_float(2e21)
    _assert_large_int_as_decimal(5e20)


def test_dump_special_floats_round_trip_on_selected_schema():
    cases = (
        (float("nan"), is_nan_number, "nan"),
        (float("inf"), is_pos_inf, "+inf"),
        (float("-inf"), is_neg_inf, "-inf"),
    )
    schemas = (
        ("json", with_json_schema()),
        ("core", with_core_schema()),
        ("yaml11", with_yaml11_schema()),
    )
    for schema_name, opts in schemas:
        for value, predicate, label in cases:
            result = dump_then_parse(value, dump_options=opts, load_options=opts)
            parsed = require_document(result)
            print(
                f"special {label} schema={schema_name} parsed={parsed!r}",
                flush=True,
            )
            assert predicate(parsed), (
                f"{label} dump-then-parse on {schema_name} failed; "
                f"got {parsed!r}"
            )


def test_dump_1e7_and_runtime_small_exponent_round_trip():
    named = 1e-7
    text = _dumped(named)
    for opts in (with_json_schema(), with_core_schema(), with_yaml11_schema()):
        parsed = require_document(load(text, opts))
        print(f"1e-7 parsed={parsed!r} schema={opts}", flush=True)
        assert is_finite_number(parsed, named), (
            f"1e-7 must survive dump-then-parse; got {parsed!r}"
        )

    runtime = 3e-5
    runtime_text = _dumped(runtime)
    print(f"runtime_small={runtime!r} text={runtime_text!r}", flush=True)
    for opts in (with_json_schema(), with_core_schema(), with_yaml11_schema()):
        parsed = require_document(load(runtime_text, opts))
        assert is_finite_number(parsed, runtime), (
            f"{runtime} must survive dump-then-parse; got {parsed!r}"
        )


# ---------------------------------------------------------------------------
# E. Anchors, aliases, no-reuse, and anchor/tag order
# ---------------------------------------------------------------------------


def test_dump_shared_object_uses_anchor_and_alias():
    dumped = dump_identical_pair({"k": 1})
    text = require_yaml_text(dumped)
    print(f"shared_default={text!r}", flush=True)
    assert "&" in text, f"default shared dump must write an anchor; got {text!r}"
    assert "*" in text, f"default shared dump must write an alias; got {text!r}"
    doc = require_sequence(require_document(load(text)))
    assert len(doc) == 2, f"shared array must have two items; got {doc!r}"
    assert same_identity(doc[0], doc[1]), (
        "the two items must be the same constructed object"
    )
    assert is_number_not_string(mapping_get(doc[0], "k"), 1)


def test_dump_no_reuse_inlines_both():
    baseline = require_yaml_text(dump_identical_pair({"k": 1}))
    assert "&" in baseline and "*" in baseline
    dumped = dump_identical_pair({"k": 1}, with_no_reuse())
    text = require_yaml_text(dumped)
    print(f"shared_no_reuse={text!r}", flush=True)
    assert "&" not in text, f"no-reuse dump must not write an anchor; got {text!r}"
    assert "*" not in text, f"no-reuse dump must not write an alias; got {text!r}"
    doc = require_sequence(require_document(load(text)))
    assert len(doc) == 2
    assert is_number_not_string(mapping_get(doc[0], "k"), 1)
    assert is_number_not_string(mapping_get(doc[1], "k"), 1)
    assert not same_identity(doc[0], doc[1]), (
        "no-reuse items must be two separate objects"
    )


def test_dump_runtime_shared_object():
    key = _runtime_plain_word()
    number = core_int_token()
    dumped = dump_identical_pair({key: number})
    text = require_yaml_text(dumped)
    print(f"runtime_shared={text!r}", flush=True)
    assert "&" in text and "*" in text
    doc = require_sequence(require_document(load(text)))
    assert same_identity(doc[0], doc[1])
    assert is_number_not_string(mapping_get(doc[0], key), number)

    inlined = require_yaml_text(dump_identical_pair({key: number}, with_no_reuse()))
    print(f"runtime_no_reuse={inlined!r}", flush=True)
    assert "&" not in inlined and "*" not in inlined
    items = require_sequence(require_document(load(inlined)))
    assert not same_identity(items[0], items[1])
    assert is_number_not_string(mapping_get(items[0], key), number)
    assert is_number_not_string(mapping_get(items[1], key), number)


def test_dump_cycle_uses_alias():
    dumped = dump_cycle({"k": 1}, "self")
    text = require_yaml_text(dumped)
    print(f"cycle={text!r}", flush=True)
    assert "&" in text and "*" in text
    doc = require_plain_mapping(require_document(load(text)))
    assert is_number_not_string(mapping_get(doc, "k"), 1)
    assert same_identity(doc, mapping_get(doc, "self")), (
        "cycle dump-then-parse must restore the self reference"
    )


def test_dump_anchor_then_tag_by_default():
    dumped = dump_identical_set(["alpha"])
    text = require_yaml_text(dumped)
    print(f"set_default_order={text!r}", flush=True)
    order = anchor_tag_order_on_node(text, SET_TAG)
    assert order == "anchor_then_tag", (
        f"default order must be anchor then {SET_TAG}; got {order} text={text!r}"
    )


def test_dump_tag_then_anchor_switch():
    baseline = require_yaml_text(dump_identical_set(["alpha"]))
    assert anchor_tag_order_on_node(baseline, SET_TAG) == "anchor_then_tag"
    dumped = dump_identical_set(["alpha"], with_tag_before_anchor())
    text = require_yaml_text(dumped)
    print(f"set_reversed_order={text!r}", flush=True)
    order = anchor_tag_order_on_node(text, SET_TAG)
    assert order == "tag_then_anchor", (
        f"switch must put {SET_TAG} before the anchor; got {order} text={text!r}"
    )


def test_dump_runtime_set_anchor_tag_order():
    word = _runtime_plain_word()
    baseline = require_yaml_text(dump_identical_set([word]))
    print(f"runtime_set_default={baseline!r}", flush=True)
    assert anchor_tag_order_on_node(baseline, SET_TAG) == "anchor_then_tag"
    reversed_text = require_yaml_text(
        dump_identical_set([word], with_tag_before_anchor())
    )
    print(f"runtime_set_reversed={reversed_text!r}", flush=True)
    assert anchor_tag_order_on_node(reversed_text, SET_TAG) == "tag_then_anchor"


# ---------------------------------------------------------------------------
# F. Indent, line width, sequence indent, nested sequence, flow
# ---------------------------------------------------------------------------


def test_dump_default_indent_two_spaces():
    text = _dumped({"a": {"b": 1}})
    rel = relative_nested_indent(text, "a", "b")
    print(f"default_indent={rel}", flush=True)
    assert rel == 2, f"default indent must be two spaces; got {rel} text={text!r}"


def test_dump_indent_four_spaces():
    baseline = _dumped({"a": {"b": 1}})
    assert relative_nested_indent(baseline, "a", "b") == 2
    text = _dumped({"a": {"b": 1}}, with_indent_width(4))
    rel = relative_nested_indent(text, "a", "b")
    print(f"indent4={rel}", flush=True)
    assert rel == 4, f"indent 4 must use four spaces; got {rel} text={text!r}"


def test_dump_runtime_indent_four():
    parent = _runtime_plain_word()
    child = _runtime_plain_word()
    text = _dumped({parent: {child: 1}}, with_indent_width(4))
    rel = relative_nested_indent(text, parent, child)
    print(f"runtime_indent4={rel}", flush=True)
    assert rel == 4, f"runtime indent 4 must be four spaces; got {rel}"


def test_dump_line_width_20_folds_named_scalar():
    value = {"a": NAMED_LONG_SCALAR}
    default_text = _dumped(value)
    default_lines = scalar_word_content_lines(default_text, NAMED_LONG_WORDS)
    print(f"default_word_lines={default_lines} text={default_text!r}", flush=True)
    assert default_lines == 1, (
        f"default width must keep the named words on one content line; "
        f"got {default_lines} text={default_text!r}"
    )
    folded = _dumped(value, with_line_width(20))
    folded_lines = scalar_word_content_lines(folded, NAMED_LONG_WORDS)
    print(f"width20_word_lines={folded_lines} text={folded!r}", flush=True)
    assert folded_lines > 1, (
        f"width 20 must put the named words on more than one content line; "
        f"got {folded_lines} text={folded!r}"
    )


def test_dump_runtime_line_width_fold():
    # Four runtime tokens stay under the default width of 80 and still
    # exceed width 20, so the contrast is only the named line-width switch.
    words = [unique_token() for _ in range(4)]
    scalar = " ".join(words)
    key = _runtime_plain_word()
    value = {key: scalar}
    default_text = _dumped(value)
    default_lines = scalar_word_content_lines(default_text, words)
    print(f"runtime_default_lines={default_lines}", flush=True)
    assert default_lines == 1, (
        f"default width must keep runtime words on one content line; "
        f"got {default_lines} text={default_text!r}"
    )
    folded = _dumped(value, with_line_width(20))
    folded_lines = scalar_word_content_lines(folded, words)
    print(f"runtime_width20_lines={folded_lines} text={folded!r}", flush=True)
    assert folded_lines > 1, (
        f"width 20 must fold runtime words onto several content lines; "
        f"got {folded_lines} text={folded!r}"
    )


def test_dump_sequence_indented_under_key():
    text = _dumped({"a": [1]})
    key_indent, dash_indent = key_and_dash_indents(text, "a")
    print(f"seq_indents key={key_indent} dash={dash_indent}", flush=True)
    assert dash_indent > key_indent, (
        f"default sequence dash must sit under the key; text={text!r}"
    )
    doc = require_plain_mapping(require_document(load(text)))
    inner = require_sequence(mapping_get(doc, "a"))
    assert len(inner) == 1 and is_number_not_string(inner[0], 1), (
        f"default indented sequence must parse as [1]; got {inner!r}"
    )
    aligned = _dumped({"a": [1]}, with_no_extra_sequence_indent())
    aligned_key, aligned_dash = key_and_dash_indents(aligned, "a")
    print(
        f"seq_aligned key={aligned_key} dash={aligned_dash} text={aligned!r}",
        flush=True,
    )
    assert aligned_dash == aligned_key, (
        f"no-extra-sequence-indent must align the dash with the key; "
        f"text={aligned!r}"
    )


def test_dump_no_extra_sequence_indent():
    baseline = _dumped({"a": [1]})
    key_indent, dash_indent = key_and_dash_indents(baseline, "a")
    assert dash_indent > key_indent
    text = _dumped({"a": [1]}, with_no_extra_sequence_indent())
    key_indent, dash_indent = key_and_dash_indents(text, "a")
    print(f"aligned key={key_indent} dash={dash_indent} text={text!r}", flush=True)
    assert dash_indent == key_indent, (
        f"no-extra-sequence-indent must align the dash with the key; "
        f"text={text!r}"
    )
    doc = require_plain_mapping(require_document(load(text)))
    inner = require_sequence(mapping_get(doc, "a"))
    assert len(inner) == 1 and is_number_not_string(inner[0], 1), (
        f"aligned sequence must still parse as [1]; got {inner!r}"
    )


def test_dump_runtime_no_extra_sequence_indent():
    key = _runtime_plain_word()
    number = core_int_token()
    baseline = _dumped({key: [number]})
    key_indent, dash_indent = key_and_dash_indents(baseline, key)
    assert dash_indent > key_indent
    text = _dumped({key: [number]}, with_no_extra_sequence_indent())
    key_indent, dash_indent = key_and_dash_indents(text, key)
    print(f"runtime_aligned {key!r} key={key_indent} dash={dash_indent}", flush=True)
    assert dash_indent == key_indent, (
        f"runtime no-extra-sequence-indent must align the dash; text={text!r}"
    )
    doc = require_plain_mapping(require_document(load(text)))
    inner = require_sequence(mapping_get(doc, key))
    assert len(inner) == 1 and is_number_not_string(inner[0], number), (
        f"runtime aligned sequence must parse as [{number}]; got {inner!r}"
    )


def test_dump_nested_sequence_on_same_line():
    text = _dumped([[1]])
    print(f"nested_default={text!r}", flush=True)
    assert has_same_line_nested_dashes(text), (
        f"default nested sequence must start on the parent dash line; "
        f"got {text!r}"
    )
    assert text.lstrip().startswith("- -"), (
        f"default nested sequence must begin with stacked dashes; got {text!r}"
    )
    doc = require_sequence(require_document(load(text)))
    assert len(doc) == 1, (
        f"default nested sequence must still be a sequence of sequences; "
        f"got {doc!r}"
    )
    inner = require_sequence(doc[0])
    assert len(inner) == 1 and is_number_not_string(inner[0], 1), (
        f"default nested sequence must parse as [[1]]; got {doc!r}"
    )
    switched = _dumped([[1]], with_nested_sequence_next_line())
    print(f"nested_same_line_switch={switched!r}", flush=True)
    assert not has_same_line_nested_dashes(switched), (
        f"nested-next-line switch must split the dashes; got {switched!r}"
    )
    assert has_nested_dash_on_following_line(switched), (
        f"nested-next-line switch must put the child dash on the next line; "
        f"got {switched!r}"
    )


def test_dump_nested_sequence_next_line():
    baseline = _dumped([[1]])
    assert has_same_line_nested_dashes(baseline)
    text = _dumped([[1]], with_nested_sequence_next_line())
    print(f"nested_next={text!r}", flush=True)
    assert not has_same_line_nested_dashes(text), (
        f"nested-next-line switch must split the dashes; got {text!r}"
    )
    assert not text.lstrip().startswith("- -"), (
        f"switched nested sequence must not start with stacked dashes; "
        f"got {text!r}"
    )
    assert has_nested_dash_on_following_line(text), (
        f"nested-next-line switch must put the child dash on the next line; "
        f"got {text!r}"
    )
    doc = require_sequence(require_document(load(text)))
    assert len(doc) == 1, (
        f"switched nested sequence must still be a sequence of sequences; "
        f"got {doc!r}"
    )
    inner = require_sequence(doc[0])
    assert len(inner) == 1 and is_number_not_string(inner[0], 1), (
        f"switched nested sequence must parse as [[1]]; got {doc!r}"
    )


def test_dump_runtime_nested_sequence_next_line():
    number = core_int_token()
    baseline = _dumped([[number]])
    assert has_same_line_nested_dashes(baseline)
    assert baseline.lstrip().startswith("- -"), (
        f"runtime default nested sequence must begin with stacked dashes; "
        f"got {baseline!r}"
    )
    text = _dumped([[number]], with_nested_sequence_next_line())
    print(f"runtime_nested_next={text!r}", flush=True)
    assert not has_same_line_nested_dashes(text), (
        f"runtime nested-next-line must split the dashes; got {text!r}"
    )
    assert has_nested_dash_on_following_line(text), (
        f"runtime nested-next-line must put the child dash on the next line; "
        f"got {text!r}"
    )
    doc = require_sequence(require_document(load(text)))
    assert len(doc) == 1, (
        f"runtime switched nested sequence must still be a sequence of "
        f"sequences; got {doc!r}"
    )
    inner = require_sequence(doc[0])
    assert len(inner) == 1 and is_number_not_string(inner[0], number), (
        f"runtime switched nested sequence must parse as [[{number}]]; "
        f"got {doc!r}"
    )


def test_dump_flow_depth_0_whole_value_flow():
    text = _dumped({"a": [1, 2]}, with_flow_depth(0))
    print(f"flow0={text!r}", flush=True)
    require_flow_container(text)
    require_flow_mapping(text)
    assert "a:" in text, (
        f"depth 0 must dump a flow mapping that still has key a; got {text!r}"
    )
    assert "[" in text and "]" in text, (
        f"depth 0 must also write the inner sequence in flow; got {text!r}"
    )
    doc = require_plain_mapping(require_document(load(text)))
    inner = require_sequence(mapping_get(doc, "a"))
    assert len(inner) == 2, f"depth 0 key a must hold [1, 2]; got {inner!r}"
    assert is_number_not_string(inner[0], 1) and is_number_not_string(inner[1], 2), (
        f"depth 0 flow mapping key a must restore [1, 2]; got {inner!r}"
    )


def test_dump_flow_depth_1_root_block_nested_flow():
    depth0 = _dumped({"a": [1, 2]}, with_flow_depth(0))
    require_flow_container(depth0)
    text = _dumped({"a": [1, 2]}, with_flow_depth(1))
    print(f"flow1={text!r}", flush=True)
    body = text.strip()
    assert not (body.startswith("{") and body.endswith("}")), (
        f"depth 1 root must be a block mapping; got {text!r}"
    )
    assert "a:" in text, f"depth 1 must keep the block key; got {text!r}"
    assert "[" in text and "]" in text, (
        f"depth 1 nested sequence must be flow; got {text!r}"
    )
    doc = require_plain_mapping(require_document(load(text)))
    inner = require_sequence(mapping_get(doc, "a"))
    assert len(inner) == 2, f"depth 1 key a must hold two items; got {inner!r}"
    assert is_number_not_string(inner[0], 1) and is_number_not_string(
        inner[1], 2
    ), (
        f"depth 1 nested flow must restore numbers 1 and 2; got {inner!r}"
    )


def test_dump_default_never_switches_to_flow():
    text = _dumped({"a": [1, 2]})
    print(f"default_block={text!r}", flush=True)
    assert "[" not in text, (
        f"default depth must use block dashes, not flow brackets; got {text!r}"
    )
    _key_indent, dash_indent = key_and_dash_indents(text, "a")
    assert dash_indent >= 0


def test_dump_flow_bracket_padding():
    value = {"a": [1, 2]}
    baseline = _dumped(value, with_flow_depth(0))
    print(f"pad_baseline={baseline!r}", flush=True)
    require_flow_container(baseline)
    require_no_flow_square_inner_space(baseline)
    padded = _dumped(
        value,
        merge_dump_options(with_flow_depth(0), with_flow_bracket_padding()),
    )
    print(f"pad_on={padded!r}", flush=True)
    require_flow_container(padded)
    assert flow_square_inner_space(padded), (
        f"bracket padding must leave inner space in square brackets; "
        f"got {padded!r}"
    )


def test_dump_flow_drop_comma_space():
    value = {"a": [1, 2]}
    baseline = _dumped(value, with_flow_depth(0))
    print(f"comma_baseline={baseline!r}", flush=True)
    assert has_space_after_comma(baseline), (
        f"live baseline must show a space after the comma; got {baseline!r}"
    )
    dropped = _dumped(
        value,
        merge_dump_options(with_flow_depth(0), with_flow_no_comma_space()),
    )
    print(f"comma_dropped={dropped!r}", flush=True)
    assert not has_space_after_comma(dropped), (
        f"drop-comma-space must remove the space after commas; got {dropped!r}"
    )


def test_dump_flow_drop_colon_space():
    value = {"a": [1, 2]}
    baseline = _dumped(value, with_flow_depth(0))
    print(f"colon_baseline={baseline!r}", flush=True)
    assert has_space_after_colon(baseline), (
        f"live baseline must show a space after the colon; got {baseline!r}"
    )
    dropped = _dumped(
        value,
        merge_dump_options(with_flow_depth(0), with_flow_no_colon_space()),
    )
    print(f"colon_dropped={dropped!r}", flush=True)
    assert not has_space_after_colon(dropped), (
        f"drop-colon-space must remove the space after colons; got {dropped!r}"
    )


def test_dump_quote_flow_keys():
    value = {"a": [1, 2]}
    baseline = _dumped(value, with_flow_depth(0))
    print(f"flowkey_baseline={baseline!r}", flush=True)
    assert "a:" in baseline and not quoted_token_present(baseline, "a"), (
        f"live baseline key a must be plain; got {baseline!r}"
    )
    quoted = _dumped(
        value,
        merge_dump_options(with_flow_depth(0), with_quote_flow_keys()),
    )
    print(f"flowkey_quoted={quoted!r}", flush=True)
    assert quoted_token_present(quoted, "a"), (
        f"quote-flow-keys must quote key a; got {quoted!r}"
    )


def test_dump_runtime_flow_depth():
    key = _runtime_plain_word()
    left, right = _distinct_runtime_ints()
    value = {key: [left, right]}
    depth0 = _dumped(value, with_flow_depth(0))
    print(f"runtime_flow0={depth0!r}", flush=True)
    require_flow_container(depth0)
    require_flow_mapping(depth0)
    assert f"{key}:" in depth0, (
        f"runtime depth 0 must keep the mapping key; got {depth0!r}"
    )
    assert "[" in depth0 and "]" in depth0, (
        f"runtime depth 0 must write the inner sequence in flow; got {depth0!r}"
    )
    doc0 = require_plain_mapping(require_document(load(depth0)))
    inner0 = require_sequence(mapping_get(doc0, key))
    assert len(inner0) == 2, (
        f"runtime depth 0 must keep both items; got {inner0!r}"
    )
    assert is_number_not_string(inner0[0], left) and is_number_not_string(
        inner0[1], right
    ), (
        f"runtime depth 0 must restore [{left}, {right}]; got {inner0!r}"
    )
    depth1 = _dumped(value, with_flow_depth(1))
    print(f"runtime_flow1={depth1!r}", flush=True)
    body = depth1.strip()
    assert not (body.startswith("{") and body.endswith("}"))
    assert f"{key}:" in depth1
    assert "[" in depth1 and "]" in depth1, (
        f"runtime depth 1 nested sequence must stay flow; got {depth1!r}"
    )
    doc1 = require_plain_mapping(require_document(load(depth1)))
    inner1 = require_sequence(mapping_get(doc1, key))
    assert len(inner1) == 2, (
        f"runtime depth 1 must keep both items; got {inner1!r}"
    )
    assert is_number_not_string(inner1[0], left) and is_number_not_string(
        inner1[1], right
    ), (
        f"runtime depth 1 must restore [{left}, {right}]; got {inner1!r}"
    )


def test_dump_runtime_default_never_flow():
    key = _runtime_plain_word()
    left, right = _distinct_runtime_ints()
    flow0 = _dumped({key: [left, right]}, with_flow_depth(0))
    print(f"runtime_never_flow_depth0={flow0!r}", flush=True)
    require_flow_container(flow0)
    assert "[" in flow0, (
        f"live baseline: flow depth 0 must write square brackets; got {flow0!r}"
    )
    text = _dumped({key: [left, right]})
    print(f"runtime_default_block={text!r}", flush=True)
    assert "[" not in text, (
        f"runtime default depth must stay in block style; got {text!r}"
    )
    key_indent, dash_indent = key_and_dash_indents(text, key)
    assert dash_indent > key_indent
    doc = require_plain_mapping(require_document(load(text)))
    inner = require_sequence(mapping_get(doc, key))
    assert len(inner) == 2, (
        f"runtime default block sequence must keep both items; got {inner!r}"
    )
    assert is_number_not_string(inner[0], left) and is_number_not_string(
        inner[1], right
    ), (
        f"runtime default block sequence must restore [{left}, {right}]; "
        f"got {inner!r}"
    )


def test_dump_runtime_flow_presentation_knobs():
    key = _runtime_plain_word()
    left, right = _distinct_runtime_ints()
    value = {key: [left, right]}
    baseline = _dumped(value, with_flow_depth(0))
    require_flow_container(baseline)
    require_no_flow_square_inner_space(baseline)
    print(f"runtime_knob_baseline={baseline!r}", flush=True)

    padded = _dumped(
        value,
        merge_dump_options(with_flow_depth(0), with_flow_bracket_padding()),
    )
    require_flow_container(padded)
    assert flow_square_inner_space(padded), (
        f"runtime bracket padding must leave inner square space; got {padded!r}"
    )

    assert has_space_after_comma(baseline)
    no_comma = _dumped(
        value,
        merge_dump_options(with_flow_depth(0), with_flow_no_comma_space()),
    )
    assert not has_space_after_comma(no_comma), (
        f"runtime drop-comma-space failed; got {no_comma!r}"
    )

    assert has_space_after_colon(baseline)
    no_colon = _dumped(
        value,
        merge_dump_options(with_flow_depth(0), with_flow_no_colon_space()),
    )
    assert not has_space_after_colon(no_colon), (
        f"runtime drop-colon-space failed; got {no_colon!r}"
    )

    assert f"{key}:" in baseline and not quoted_token_present(baseline, key)
    quoted = _dumped(
        value,
        merge_dump_options(with_flow_depth(0), with_quote_flow_keys()),
    )
    assert quoted_token_present(quoted, key), (
        f"runtime quote-flow-keys must quote {key!r}; got {quoted!r}"
    )


# ---------------------------------------------------------------------------
# G. Insertion order vs comparator-less sort; complex keys stay put
# ---------------------------------------------------------------------------


def test_dump_keys_keep_insertion_order():
    text = _dumped({"b": 1, "a": 2})
    print(f"insert_order={text!r}", flush=True)
    assert mapping_key_position(text, "b") < mapping_key_position(text, "a"), (
        f"default dump must keep b before a; got {text!r}"
    )


def test_dump_comparatorless_sort_emits_a_before_b():
    baseline = _dumped({"b": 1, "a": 2})
    assert mapping_key_position(baseline, "b") < mapping_key_position(baseline, "a")
    text = _dumped({"b": 1, "a": 2}, with_sort_keys())
    print(f"sorted={text!r}", flush=True)
    assert mapping_key_position(text, "a") < mapping_key_position(text, "b"), (
        f"comparator-less sort must emit a before b; got {text!r}"
    )


def test_dump_runtime_sort_vs_insertion():
    first, second = _lex_reversed_pair()
    assert first > second
    value = {first: 1, second: 2}
    inserted = _dumped(value)
    print(f"runtime_insert={inserted!r}", flush=True)
    assert mapping_key_position(inserted, first) < mapping_key_position(
        inserted, second
    )
    sorted_text = _dumped(value, with_sort_keys())
    print(f"runtime_sorted={sorted_text!r}", flush=True)
    assert mapping_key_position(sorted_text, second) < mapping_key_position(
        sorted_text, first
    ), (
        f"sort must put the lexicographically smaller key first; "
        f"got {sorted_text!r}"
    )


def _inner_mapping_key(value):
    """Sole string key of a one-entry mapping used as a Map key."""
    if isinstance(value, JsMap):
        assert len(value.entries) == 1, f"complex key Map must have one entry: {value!r}"
        key = value.entries[0][0]
        assert isinstance(key, str), f"inner Map key is not a string: {key!r}"
        return key
    mapping = require_plain_mapping(value)
    keys = list(mapping.keys())
    assert len(keys) == 1, f"complex key object must have one property: {keys!r}"
    key = keys[0]
    assert isinstance(key, str), f"inner object key is not a string: {key!r}"
    return key


def _assert_complex_key_order(mapping, first_inner: str, second_inner: str, dump_opts) -> None:
    restored = require_real_map(
        require_document(
            dump_then_parse(
                mapping,
                dump_options=dump_opts,
                load_options=with_real_map_schema(),
            )
        )
    )
    assert len(restored.entries) == 2, f"restored Map size: {restored!r}"
    got_first = _inner_mapping_key(restored.entries[0][0])
    got_second = _inner_mapping_key(restored.entries[1][0])
    print(
        f"complex_key_order first={got_first!r} second={got_second!r} "
        f"dump_opts={dump_opts!r}",
        flush=True,
    )
    assert got_first == first_inner and got_second == second_inner, (
        f"complex key order must stay {first_inner!r} then {second_inner!r}; "
        f"got {got_first!r} then {got_second!r}"
    )


def test_dump_complex_keys_not_reordered():
    mapping = JsMap(entries=[({"b": 2}, "y"), ({"a": 1}, "x")], object_id=-1)
    simple_sorted = _dumped({"b": 1, "a": 2}, with_sort_keys())
    print(f"simple_sorted_live={simple_sorted!r}", flush=True)
    assert mapping_key_position(simple_sorted, "a") < mapping_key_position(
        simple_sorted, "b"
    ), (
        f"live baseline: comparator-less sort must reorder simple keys; "
        f"got {simple_sorted!r}"
    )
    _assert_complex_key_order(mapping, "b", "a", with_real_map_schema())
    _assert_complex_key_order(
        mapping,
        "b",
        "a",
        merge_dump_options(with_real_map_schema(), with_sort_keys()),
    )


def test_dump_runtime_complex_keys_not_reordered():
    first, second = _lex_reversed_pair()
    simple_sorted = _dumped({first: 1, second: 2}, with_sort_keys())
    print(f"runtime_simple_sorted_live={simple_sorted!r}", flush=True)
    assert mapping_key_position(simple_sorted, second) < mapping_key_position(
        simple_sorted, first
    ), (
        f"live baseline: sort must reorder simple keys; got {simple_sorted!r}"
    )
    mapping = complex_key_map(first, "y", second, "x")
    _assert_complex_key_order(
        mapping,
        first,
        second,
        merge_dump_options(with_real_map_schema(), with_sort_keys()),
    )


# ---------------------------------------------------------------------------
# H. Unrepresentable values and undefined policy
# ---------------------------------------------------------------------------


def test_dump_function_fails_without_skip():
    root = dump(function_value())
    err = require_dump_failure(root)
    print(f"function_root_fail={err.name!r} ok={root.ok!r}", flush=True)
    assert root.ok is False, (
        "function root dump must fail and produce no YAML text"
    )
    mapped = dump({"a": function_value()})
    err_map = require_dump_failure(mapped)
    print(f"function_map_fail={err_map.name!r} ok={mapped.ok!r}", flush=True)
    assert mapped.ok is False, (
        "function mapping-value dump must fail and produce no YAML text"
    )


def test_dump_regexp_fails_without_skip():
    root = dump(regexp_value())
    err = require_dump_failure(root)
    print(f"regexp_root_fail={err.name!r} ok={root.ok!r}", flush=True)
    assert root.ok is False, (
        "regular-expression dump must fail and produce no YAML text"
    )


def test_dump_skip_omits_function_in_mapping_and_sequence():
    failing = {"a": function_value(), "b": 2}
    require_dump_failure(dump(failing))
    text = _dumped(failing, with_skip_unrepresentable())
    doc = require_plain_mapping(require_document(load(text)))
    print(f"skip_fn_map keys={list(doc.keys())}", flush=True)
    assert is_number_not_string(mapping_get(doc, "b"), 2)
    assert "a" not in doc, f"skipped function pair must be omitted; keys={list(doc)}"

    require_dump_failure(dump([function_value(), "a"]))
    seq_text = _dumped([function_value(), "a"], with_skip_unrepresentable())
    seq = require_sequence(require_document(load(seq_text)))
    print(f"skip_fn_seq={seq!r}", flush=True)
    assert seq == ["a"], f"skipped function item must leave only a; got {seq!r}"


def test_dump_runtime_skip_omits_function_in_sequence():
    word = _runtime_plain_word()
    failing = [function_value(), word]
    refused = dump(failing)
    require_dump_failure(refused)
    print(f"runtime_skip_seq_fail ok={refused.ok!r}", flush=True)
    assert refused.ok is False, (
        "function plus runtime word without skip must fail and produce "
        "no YAML text"
    )
    seq_text = _dumped(failing, with_skip_unrepresentable())
    seq = require_sequence(require_document(load(seq_text)))
    print(f"runtime_skip_fn_seq={seq!r}", flush=True)
    assert len(seq) == 1, f"skipped function must leave one item; got {seq!r}"
    assert is_string_text(seq[0], word), (
        f"skipped function must leave the runtime word; got {seq[0]!r}"
    )


def test_dump_skip_omits_regexp_in_mapping():
    failing = {"r": regexp_value(), "b": 2}
    require_dump_failure(dump(failing))
    text = _dumped(failing, with_skip_unrepresentable())
    doc = require_plain_mapping(require_document(load(text)))
    print(f"skip_re_map keys={list(doc.keys())}", flush=True)
    assert is_number_not_string(mapping_get(doc, "b"), 2)
    assert "r" not in doc, f"skipped regexp pair must be omitted; keys={list(doc)}"


def test_dump_real_map_function_key_fails_or_omits():
    mapping = JsMap(entries=[(function_value(), "x"), ("b", 2)], object_id=-1)
    require_dump_failure(dump(mapping, with_real_map_schema()))
    text = _dumped(
        mapping,
        merge_dump_options(with_real_map_schema(), with_skip_unrepresentable()),
    )
    doc = require_document(load(text, with_real_map_schema()))
    print(f"realmap_skip={doc!r}", flush=True)
    if hasattr(doc, "entries"):
        keys = [key for key, _ in doc.entries]
        values = [value for _, value in doc.entries]
        print(f"realmap_keys={keys!r} values={values!r}", flush=True)
        assert keys == ["b"], f"only the string key must remain; keys={keys!r}"
        assert values == [2] or (
            len(values) == 1 and is_number_not_string(values[0], 2)
        )
    else:
        mapping_doc = require_plain_mapping(doc)
        assert "b" in mapping_doc
        assert is_number_not_string(mapping_get(mapping_doc, "b"), 2)
        assert "x" not in mapping_doc


def test_dump_undefined_sequence_item_is_null():
    text = _dumped([undefined_value()])
    seq = require_sequence(require_document(load(text)))
    print(f"undef_seq={seq!r}", flush=True)
    assert len(seq) == 1, f"[undefined] must dump one item; got {seq!r}"
    assert is_js_null(seq[0]), f"[undefined] item must be null; got {seq[0]!r}"


def test_dump_undefined_mapping_value_omits_pair():
    text = _dumped({"a": undefined_value(), "b": 2})
    doc = require_plain_mapping(require_document(load(text)))
    print(f"undef_map keys={list(doc.keys())}", flush=True)
    assert is_number_not_string(mapping_get(doc, "b"), 2)
    assert "a" not in doc, f"undefined mapping value must omit a; keys={list(doc)}"

    key = _runtime_plain_word()
    runtime_text = _dumped({key: undefined_value(), "kept": 2})
    runtime_doc = require_plain_mapping(require_document(load(runtime_text)))
    print(f"runtime_undef_map keys={list(runtime_doc.keys())}", flush=True)
    assert key not in runtime_doc, (
        f"undefined mapping value must omit runtime key {key!r}; "
        f"keys={list(runtime_doc)}"
    )
    assert is_number_not_string(mapping_get(runtime_doc, "kept"), 2)
    failing = dump({key: function_value(), "kept": 2})
    require_dump_failure(failing)
    print(f"function_map_contrast ok={failing.ok!r}", flush=True)
    assert failing.ok is False, (
        "a function mapping value must fail without skip; it must not "
        "share the omit-success of an undefined mapping value"
    )


def test_dump_undefined_root_is_empty_text():
    undef = dump(undefined_value())
    empty = require_empty_yaml_text(undef)
    print(f"undef_root chars={len(empty)} ok={undef.ok!r}", flush=True)
    assert undef.ok is True, "undefined root dump must succeed"
    assert len(empty) == 0, f"undefined root must be empty text; got {empty!r}"
    fn = dump(function_value())
    require_dump_failure(fn)
    print(f"function_root_contrast ok={fn.ok!r}", flush=True)
    assert fn.ok is False, (
        "function root dump must fail; it must not share the "
        "empty-text success of an undefined root"
    )


def test_dump_runtime_function_mapping_fail_or_omit():
    key = _runtime_plain_word()
    failing = {key: function_value(), "kept": 2}
    require_dump_failure(dump(failing))
    text = _dumped(failing, with_skip_unrepresentable())
    doc = require_plain_mapping(require_document(load(text)))
    print(f"runtime_fn_skip keys={list(doc.keys())}", flush=True)
    assert key not in doc, f"runtime function pair must be omitted; keys={list(doc)}"
    assert is_number_not_string(mapping_get(doc, "kept"), 2)


def test_dump_runtime_undefined_in_sequence_with_word():
    word = _runtime_plain_word()
    text = _dumped([undefined_value(), word])
    seq = require_sequence(require_document(load(text)))
    print(f"runtime_undef_seq={seq!r}", flush=True)
    assert len(seq) == 2, f"undefined plus word must keep length 2; got {seq!r}"
    assert is_js_null(seq[0]), f"undefined item must be null; got {seq[0]!r}"
    assert is_string_text(seq[1], word), (
        f"runtime word must remain; got {seq[1]!r}"
    )


# ---------------------------------------------------------------------------
# I. Colon + flow indicator quoted in flow style
# ---------------------------------------------------------------------------


def test_dump_colon_flow_indicator_quoted_in_flow():
    for scalar in COLON_FLOW:
        seq_text = _dumped([scalar], with_flow_depth(0))
        print(f"colon_seq {scalar!r} -> {seq_text!r}", flush=True)
        require_flow_container(seq_text)
        assert quoted_token_present(seq_text, scalar), (
            f"colon+flow-indicator {scalar!r} must be quoted in the flow dump; "
            f"got {seq_text!r}"
        )
        seq = require_sequence(require_document(load(seq_text)))
        assert len(seq) == 1 and is_string_text(seq[0], scalar), (
            f"flow dump of [{scalar!r}] must restore the string; got {seq!r}"
        )

        map_text = _dumped({"k": scalar}, with_flow_depth(0))
        print(f"colon_map {scalar!r} -> {map_text!r}", flush=True)
        require_flow_container(map_text)
        assert quoted_token_present(map_text, scalar), (
            f"colon+flow-indicator {scalar!r} must be quoted as a flow "
            f"mapping value; got {map_text!r}"
        )
        doc = require_plain_mapping(require_document(load(map_text)))
        assert is_string_text(mapping_get(doc, "k"), scalar), (
            f"flow dump of mapping value {scalar!r} must restore; "
            f"got {doc!r}"
        )


def test_dump_runtime_colon_flow_indicator_round_trip():
    word = _runtime_plain_word()
    baseline = _dumped([word], with_flow_depth(0))
    require_flow_container(baseline)
    seq = require_sequence(require_document(load(baseline)))
    assert is_string_text(seq[0], word), (
        f"live baseline: ordinary word must round-trip in flow; got {seq!r}"
    )

    indicator = OTHER_COLON_FLOW[core_int_token() % len(OTHER_COLON_FLOW)]
    scalar = word + indicator
    print(f"runtime_colon={scalar!r}", flush=True)
    text = _dumped([scalar], with_flow_depth(0))
    require_flow_container(text)
    assert quoted_token_present(text, scalar), (
        f"runtime colon+indicator {scalar!r} must be quoted in the flow dump; "
        f"got {text!r}"
    )
    parsed = require_sequence(require_document(load(text)))
    assert len(parsed) == 1 and is_string_text(parsed[0], scalar), (
        f"runtime colon+indicator must restore in flow; got {parsed!r}"
    )
    map_text = _dumped({"k": scalar}, with_flow_depth(0))
    require_flow_container(map_text)
    assert quoted_token_present(map_text, scalar), (
        f"runtime colon+indicator {scalar!r} must be quoted as a flow "
        f"mapping value; got {map_text!r}"
    )
    doc = require_plain_mapping(require_document(load(map_text)))
    assert is_string_text(mapping_get(doc, "k"), scalar)
