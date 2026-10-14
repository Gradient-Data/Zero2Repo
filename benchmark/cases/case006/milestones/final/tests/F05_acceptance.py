# feature: F05
"""Parameter types and conversion (FP-05).

Assertions stay at the PRD's precision: built-in conversions, inference
from a default (UUID never inferred), boolean used automatically for
flags, choice originals and first-registered delivery after a colliding
normalization, date-time formats, ranges and clamp, tuple positions,
pass-through, custom types,
prompt-time conversion, and conversion usage errors that identify the
parameter. Message wording, exception types, class names, and help
decoration are not pinned.
"""

from __future__ import annotations

import enum
import uuid

from optlyn import (
    BOOL,
    FLOAT,
    INT,
    STRING,
    UNPROCESSED,
    UUID,
    Choice,
    DateTime,
    FloatRange,
    IntRange,
    Tuple,
    argument,
    option,
    prompt,
)
from F05_helpers import (
    _MarkedType,
    _Tagged,
    _date_parts,
    _emit_arith,
    _emit_bool,
    _emit_calendar,
    _emit_choice,
    _emit_float,
    _emit_seq_choice,
    _emit_tagged,
    _emit_uuid,
    _runtime_bounds,
    _type_hi,
    _type_ident,
    _type_int,
    _type_leaf,
    _type_run,
    _type_stderr,
    _type_stdout,
)

from _helpers import (
    assert_declaration_refused,
    assert_intentional_help,
    assert_marker_absent,
    assert_success_marker_present,
    assert_usage_class,
    assert_usage_names_option,
    call_with_fed_stdin,
    marker_occurs,
    option_help_record,
    unrelated_dispatch_token,
)

_BOOL_ON = ("1", "true", "t", "yes", "y", "on")
_BOOL_OFF = ("0", "false", "f", "no", "n", "off")


# ---------------------------------------------------------------------------
# A. String, integer, float, boolean value type, inference
# ---------------------------------------------------------------------------


def test_string_is_default_unicode_text():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    text = f"café-δ-{_type_ident()}"
    number = _type_int()
    token = str(number)
    expected = number * 3 + 7

    def as_text(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"S:{kwargs[dest]}", flush=True)
        _emit_arith(kwargs[dest])

    def as_int(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    as_text.__name__ = f"{_type_ident()}_{_type_ident()}"
    as_int.__name__ = f"{_type_ident()}_{_type_ident()}"
    text_cli = _type_leaf(as_text, option(flag, dest))
    int_cli = _type_leaf(as_int, option(flag, dest, type=INT))

    uni = _type_run(text_cli, [flag, text])
    numeric_as_text = _type_run(text_cli, [flag, token])
    numeric_as_int = _type_run(int_cli, [flag, token])
    print(
        f"uni={uni.stdout_text!r} textn={numeric_as_text.stdout_text!r} "
        f"intn={numeric_as_int.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(uni, greeting)
    assert marker_occurs(_type_stdout(uni), f"S:{text}")
    assert_marker_absent(_type_stdout(uni), f"T:{expected}")
    assert_success_marker_present(numeric_as_text, greeting)
    assert marker_occurs(_type_stdout(numeric_as_text), f"S:{token}")
    assert_marker_absent(_type_stdout(numeric_as_text), f"T:{expected}")
    assert_success_marker_present(numeric_as_int, greeting)
    assert marker_occurs(_type_stdout(numeric_as_int), f"T:{expected}")


def test_integer_type_or_integer_default_delivers_int():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    default_n = _type_int()
    given = default_n + 5 + uuid.uuid4().int % 9
    expected = given * 3 + 7
    letters = unrelated_dispatch_token()
    dotted = f"{given}.5"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    typed = _type_leaf(callback, option(flag, dest, type=INT))
    inferred = _type_leaf(callback, option(flag, dest, default=default_n))

    typed_ok = _type_run(typed, [flag, str(given)])
    inferred_ok = _type_run(inferred, [flag, str(given)])
    bad_word = _type_run(typed, [flag, letters])
    bad_dot = _type_run(typed, [flag, dotted])
    print(
        f"typed={typed_ok.stdout_text!r} inferred={inferred_ok.stdout_text!r} "
        f"word={bad_word.stderr_text!r} dot={bad_dot.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(typed_ok, greeting)
    assert marker_occurs(_type_stdout(typed_ok), f"T:{expected}")
    assert_success_marker_present(inferred_ok, greeting)
    assert marker_occurs(_type_stdout(inferred_ok), f"T:{expected}")
    assert_usage_class(bad_word, greeting)
    assert_usage_class(bad_dot, greeting)


def test_float_type_or_float_default_delivers_float():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    whole = 3 + uuid.uuid4().int % 20
    token = f"{whole}.5"
    expected = (whole + 0.5) * 2
    default_f = (whole + 3) + 0.5
    letters = unrelated_dispatch_token()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_float(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    typed = _type_leaf(callback, option(flag, dest, type=FLOAT))
    inferred = _type_leaf(callback, option(flag, dest, default=default_f))
    as_text = _type_leaf(callback, option(flag, dest, type=STRING))

    typed_ok = _type_run(typed, [flag, token])
    inferred_ok = _type_run(inferred, [flag, token])
    text_twin = _type_run(as_text, [flag, token])
    bad = _type_run(typed, [flag, letters])
    print(
        f"typed={typed_ok.stdout_text!r} inferred={inferred_ok.stdout_text!r} "
        f"text={text_twin.stdout_text!r} bad={bad.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(typed_ok, greeting)
    assert marker_occurs(_type_stdout(typed_ok), f"F:{expected!r}")
    assert_success_marker_present(inferred_ok, greeting)
    assert marker_occurs(_type_stdout(inferred_ok), f"F:{expected!r}")
    assert_success_marker_present(text_twin, greeting)
    assert_marker_absent(_type_stdout(text_twin), f"F:{expected!r}")
    assert marker_occurs(_type_stdout(text_twin), f"S:{token}")
    assert_usage_class(bad, greeting)


def test_boolean_value_type_tokens_case_insensitive():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    default_on = True

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bool(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    typed = _type_leaf(callback, option(flag, dest, type=BOOL))
    inferred = _type_leaf(callback, option(flag, dest, default=default_on))
    as_text = _type_leaf(callback, option(flag, dest, type=STRING))

    for token in _BOOL_ON:
        result = _type_run(typed, [flag, token])
        print(f"on {token!r} -> {result.stdout_text!r}", flush=True)
        assert_success_marker_present(result, greeting)
        assert "BOOL:YES" in _type_stdout(result)
        assert "BOOL:NO" not in _type_stdout(result)

    for token in _BOOL_OFF:
        result = _type_run(typed, [flag, token])
        print(f"off {token!r} -> {result.stdout_text!r}", flush=True)
        assert_success_marker_present(result, greeting)
        assert "BOOL:NO" in _type_stdout(result)
        assert "BOOL:YES" not in _type_stdout(result)

    case_true = _type_run(typed, [flag, "True"])
    case_off = _type_run(typed, [flag, "OFF"])
    print(
        f"True={case_true.stdout_text!r} OFF={case_off.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(case_true, greeting)
    assert "BOOL:YES" in _type_stdout(case_true)
    assert_success_marker_present(case_off, greeting)
    assert "BOOL:NO" in _type_stdout(case_off)

    unknown = unrelated_dispatch_token(*_BOOL_ON, *_BOOL_OFF)
    bad = _type_run(typed, [flag, unknown])
    print(f"unknown={bad.stderr_text!r}", flush=True)
    assert_usage_class(bad, greeting)

    inferred_off = _type_run(inferred, [flag, "off"])
    text_off = _type_run(as_text, [flag, "off"])
    print(
        f"inf={inferred_off.stdout_text!r} text={text_off.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(inferred_off, greeting)
    assert "BOOL:NO" in _type_stdout(inferred_off)
    assert_success_marker_present(text_off, greeting)
    assert f"S:off" in _type_stdout(text_off)
    assert "BOOL:NO" not in _type_stdout(text_off)
    assert "BOOL:YES" not in _type_stdout(text_off)


def test_boolean_used_automatically_for_flags():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bool(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(callback, option(flag, dest, is_flag=True))

    present = _type_run(leaf, [flag])
    omitted = _type_run(leaf, [])
    print(
        f"present={present.stdout_text!r} omitted={omitted.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(present, greeting)
    assert "BOOL:YES" in _type_stdout(present)
    assert "BOOL:NO" not in _type_stdout(present)
    assert_success_marker_present(omitted, greeting)
    assert "BOOL:NO" in _type_stdout(omitted)
    assert "BOOL:YES" not in _type_stdout(omitted)


def test_argument_uses_attached_integer_type():
    greeting = _type_hi()
    dest_a = _type_ident()
    dest_b = _type_ident()
    shared = _type_ident()
    number = _type_int()
    expected = number * 3 + 7
    letters = unrelated_dispatch_token()

    def cb_a(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest_a])

    def cb_b(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest_b])

    cb_a.__name__ = f"{_type_ident()}_{_type_ident()}"
    cb_b.__name__ = f"{_type_ident()}_{_type_ident()}"
    cli_a = _type_leaf(cb_a, argument(dest_a, type=INT), name=shared)
    cli_b = _type_leaf(cb_b, argument(dest_b, type=INT), name=shared)

    ok = _type_run(cli_a, [str(number)])
    bad_a = _type_run(cli_a, [letters])
    bad_b = _type_run(cli_b, [letters])
    print(
        f"ok={ok.stdout_text!r} a={bad_a.stderr_text!r} b={bad_b.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(ok, greeting)
    assert marker_occurs(_type_stdout(ok), f"T:{expected}")
    assert_usage_class(bad_a, greeting)
    assert_usage_class(bad_b, greeting)
    named_a = _type_stderr(bad_a)
    named_b = _type_stderr(bad_b)
    assert dest_a.lower() in named_a.lower(), (
        f"argument conversion failure did not identify {dest_a!r}; "
        f"stderr={named_a!r}"
    )
    assert dest_b.lower() in named_b.lower(), (
        f"argument conversion failure did not identify {dest_b!r}; "
        f"stderr={named_b!r}"
    )
    assert dest_a.lower() not in named_b.lower(), (
        f"failure for {dest_b!r} also named {dest_a!r}; stderr={named_b!r}"
    )
    assert dest_b.lower() not in named_a.lower(), (
        f"failure for {dest_a!r} also named {dest_b!r}; stderr={named_a!r}"
    )


# ---------------------------------------------------------------------------
# B. UUID attached vs never inferred
# ---------------------------------------------------------------------------


def test_uuid_type_converts_text_and_is_never_inferred():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    default_obj = uuid.uuid4()
    token_obj = uuid.uuid4()
    token = str(token_obj)
    expected_hex = token_obj.hex
    bogus = f"not-uuid-{_type_ident()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_uuid(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    typed = _type_leaf(callback, option(flag, dest, type=UUID, default=default_obj))
    inferred = _type_leaf(callback, option(flag, dest, default=default_obj))

    converted = _type_run(typed, [flag, token])
    as_text = _type_run(inferred, [flag, token])
    bad = _type_run(typed, [flag, bogus])
    print(
        f"conv={converted.stdout_text!r} text={as_text.stdout_text!r} "
        f"bad={bad.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(converted, greeting)
    assert marker_occurs(_type_stdout(converted), f"UID:{expected_hex}")
    assert_marker_absent(_type_stdout(converted), f"S:{token}")
    assert_success_marker_present(as_text, greeting)
    assert_marker_absent(_type_stdout(as_text), f"UID:{expected_hex}")
    assert marker_occurs(_type_stdout(as_text), f"S:{token}")
    assert_usage_class(bad, greeting)


# ---------------------------------------------------------------------------
# C. Date-time formats, order, replacement, naive
# ---------------------------------------------------------------------------


def test_default_datetime_formats_parse_naive_values():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    year, month, day, hour, minute, second = _date_parts()
    date_tok = f"{year:04d}-{month:02d}-{day:02d}"
    t_tok = f"{date_tok}T{hour:02d}:{minute:02d}:{second:02d}"
    space_tok = f"{date_tok} {hour:02d}:{minute:02d}:{second:02d}"
    cal = f"CAL:{year:04d}-{month:02d}-{day:02d}"
    clk = f"CLK:{hour:02d}:{minute:02d}:{second:02d}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_calendar(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    typed = _type_leaf(callback, option(flag, dest, type=DateTime()))
    as_text = _type_leaf(callback, option(flag, dest, type=STRING))

    date_run = _type_run(typed, [flag, date_tok])
    t_run = _type_run(typed, [flag, t_tok])
    space_run = _type_run(typed, [flag, space_tok])
    text_twin = _type_run(as_text, [flag, t_tok])
    print(
        f"date={date_run.stdout_text!r} t={t_run.stdout_text!r} "
        f"space={space_run.stdout_text!r} twin={text_twin.stdout_text!r}",
        flush=True,
    )
    for result, expect_clock in (
        (date_run, False),
        (t_run, True),
        (space_run, True),
    ):
        assert_success_marker_present(result, greeting)
        assert cal in _type_stdout(result)
        assert "NAIVE:1" in _type_stdout(result)
        if expect_clock:
            assert clk in _type_stdout(result)
    assert_success_marker_present(text_twin, greeting)
    assert cal not in _type_stdout(text_twin)
    assert clk not in _type_stdout(text_twin)
    assert marker_occurs(_type_stdout(text_twin), f"S:{t_tok}")


def test_datetime_rejects_non_matching_token():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    bogus = f"not-a-date-{_type_ident()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_calendar(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(callback, option(flag, dest, type=DateTime()))
    result = _type_run(leaf, [flag, bogus])
    print(f"bad={result.stderr_text!r}", flush=True)
    assert_usage_class(result, greeting)


def test_author_replaces_datetime_format_list():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    year, month, day, hour, minute, second = _date_parts()
    replaced = f"{day:02d}/{month:02d}/{year:04d}"
    default_shape = f"{year:04d}-{month:02d}-{day:02d}"
    cal = f"CAL:{year:04d}-{month:02d}-{day:02d}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_calendar(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(
        callback, option(flag, dest, type=DateTime(formats=["%d/%m/%Y"]))
    )
    ok = _type_run(leaf, [flag, replaced])
    old = _type_run(leaf, [flag, default_shape])
    print(f"ok={ok.stdout_text!r} old={old.stderr_text!r}", flush=True)
    assert_success_marker_present(ok, greeting)
    assert cal in _type_stdout(ok)
    assert_usage_class(old, greeting)


def test_datetime_formats_tried_in_order_first_success_wins():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    year = 1995 + uuid.uuid4().int % 30
    token = f"02-01-{year:04d}"
    first_cal = f"CAL:{year:04d}-01-02"
    second_cal = f"CAL:{year:04d}-02-01"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_calendar(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    a_then_b = _type_leaf(
        callback,
        option(flag, dest, type=DateTime(formats=["%d-%m-%Y", "%m-%d-%Y"])),
    )
    b_then_a = _type_leaf(
        callback,
        option(flag, dest, type=DateTime(formats=["%m-%d-%Y", "%d-%m-%Y"])),
    )
    first = _type_run(a_then_b, [flag, token])
    second = _type_run(b_then_a, [flag, token])
    print(f"first={first.stdout_text!r} second={second.stdout_text!r}", flush=True)
    assert_success_marker_present(first, greeting)
    assert first_cal in _type_stdout(first)
    assert second_cal not in _type_stdout(first)
    assert_success_marker_present(second, greeting)
    assert second_cal in _type_stdout(second)
    assert first_cal not in _type_stdout(second)


# ---------------------------------------------------------------------------
# D. Tuple positions and pass-through
# ---------------------------------------------------------------------------


def test_tuple_converts_each_position_with_inner_type():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    number = _type_int()
    whole = 3 + uuid.uuid4().int % 20
    float_tok = f"{whole}.5"
    expected_int = number * 3 + 7
    expected_float = (whole + 0.5) * 2
    letters = unrelated_dispatch_token()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        pair = kwargs[dest]
        _emit_arith(pair[0])
        _emit_float(pair[1])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(callback, option(flag, dest, type=Tuple([INT, FLOAT])))

    ok = _type_run(leaf, [flag, str(number), float_tok])
    bad = _type_run(leaf, [flag, letters, float_tok])
    print(f"ok={ok.stdout_text!r} bad={bad.stderr_text!r}", flush=True)
    assert_success_marker_present(ok, greeting)
    assert marker_occurs(_type_stdout(ok), f"T:{expected_int}")
    assert marker_occurs(_type_stdout(ok), f"F:{expected_float!r}")
    assert_usage_class(bad, greeting)


def test_passthrough_does_not_convert_token():
    greeting = _type_hi()
    dest = _type_ident()
    number = _type_int()
    token = str(number)
    expected = number * 3 + 7

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        items = kwargs[dest]
        print(f"N:{len(items)}", flush=True)
        _emit_arith(items[0])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    raw = _type_leaf(callback, argument(dest, nargs=-1, type=UNPROCESSED))
    as_int = _type_leaf(callback, argument(dest, nargs=-1, type=INT))

    passed = _type_run(raw, [token])
    converted = _type_run(as_int, [token])
    print(f"raw={passed.stdout_text!r} int={converted.stdout_text!r}", flush=True)
    assert_success_marker_present(passed, greeting)
    assert marker_occurs(_type_stdout(passed), f"S:{token}")
    assert_marker_absent(_type_stdout(passed), f"T:{expected}")
    assert_success_marker_present(converted, greeting)
    assert marker_occurs(_type_stdout(converted), f"T:{expected}")


# ---------------------------------------------------------------------------
# E. Choice originals, repeatable default, help listing
# ---------------------------------------------------------------------------


def test_choice_returns_original_list_entry_case_insensitive():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    first = f"Ab{_type_ident()}"
    second = f"Cd{_type_ident()}"
    folded = first.swapcase()
    assert folded != first

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_choice(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(
        callback,
        option(flag, dest, type=Choice([first, second], case_sensitive=False)),
    )
    exact = _type_run(leaf, [flag, first])
    folded_run = _type_run(leaf, [flag, folded])
    print(f"exact={exact.stdout_text!r} fold={folded_run.stdout_text!r}", flush=True)
    assert_success_marker_present(exact, greeting)
    assert marker_occurs(_type_stdout(exact), f"ORIG:{first}")
    assert_success_marker_present(folded_run, greeting)
    assert marker_occurs(_type_stdout(folded_run), f"ORIG:{first}")
    assert_marker_absent(_type_stdout(folded_run), f"ORIG:{folded}")


def test_choice_returns_original_enum_member_case_insensitive():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    left = f"L{_type_ident()}"
    right = f"R{_type_ident()}"
    left_val = _type_ident()
    right_val = _type_ident()
    Kind = enum.Enum("Kind", {left: left_val, right: right_val})
    folded = left.swapcase()
    assert folded != left

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_choice(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(
        callback,
        option(flag, dest, type=Choice(Kind, case_sensitive=False)),
    )
    result = _type_run(leaf, [flag, folded])
    print(f"enum={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert f"MEM:{left}|{left_val}" in _type_stdout(result)
    assert_marker_absent(_type_stdout(result), f"S:{folded}")
    assert_marker_absent(_type_stdout(result), f"ORIG:{folded}")


def test_unknown_choice_is_usage_error():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    first = f"Ab{_type_ident()}"
    second = f"Cd{_type_ident()}"
    unknown = unrelated_dispatch_token(first, second)

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_choice(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(callback, option(flag, dest, type=Choice([first, second])))
    result = _type_run(leaf, [flag, unknown])
    print(f"unknown={result.stderr_text!r}", flush=True)
    assert_usage_class(result, greeting)


def test_choice_must_be_unique_after_normalization():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    first = f"Ab{_type_ident()}"
    second = f"Cd{_type_ident()}"
    stem = f"Xy{_type_ident()}"
    folded = stem.swapcase()
    assert first.casefold() != second.casefold()
    assert folded != stem
    assert folded.casefold() == stem.casefold()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_choice(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    unique = _type_leaf(
        callback,
        option(flag, dest, type=Choice([first, second], case_sensitive=False)),
    )
    first_run = _type_run(unique, [flag, first])
    second_run = _type_run(unique, [flag, second])
    print(
        f"unique_first={first_run.stdout_text!r} "
        f"unique_second={second_run.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(first_run, greeting)
    assert marker_occurs(_type_stdout(first_run), f"ORIG:{first}")
    assert_success_marker_present(second_run, greeting)
    assert marker_occurs(_type_stdout(second_run), f"ORIG:{second}")

    colliding = _type_leaf(
        callback,
        option(flag, dest, type=Choice([stem, folded], case_sensitive=False)),
    )
    for token in (stem, folded):
        result = _type_run(colliding, [flag, token])
        print(
            f"colliding token={token!r} code={result.exit_code!r} "
            f"out={result.stdout_text!r}",
            flush=True,
        )
        assert_success_marker_present(result, greeting)
        text = _type_stdout(result)
        assert marker_occurs(text, f"ORIG:{stem}"), (
            "a token that collides after normalization must deliver the "
            f"first registered original {stem!r}; stdout={text!r}"
        )
        assert not marker_occurs(text, f"ORIG:{folded}"), (
            "a token that collides after normalization delivered the "
            f"last registered original {folded!r} instead of the first; "
            f"stdout={text!r}"
        )


def test_repeatable_choice_default_is_sequence_of_originals():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    first = f"Ab{_type_ident()}"
    second = f"Cd{_type_ident()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_seq_choice(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(
        callback,
        option(
            flag,
            dest,
            multiple=True,
            type=Choice([first, second]),
            default=(first, second),
        ),
    )
    omitted = _type_run(leaf, [])
    twice = _type_run(leaf, [flag, first, flag, second])
    print(f"omit={omitted.stdout_text!r} twice={twice.stdout_text!r}", flush=True)
    assert_success_marker_present(omitted, greeting)
    assert "N:2" in _type_stdout(omitted)
    assert f"C:0:ORIG:{first}" in _type_stdout(omitted)
    assert f"C:1:ORIG:{second}" in _type_stdout(omitted)
    assert_success_marker_present(twice, greeting)
    assert "N:2" in _type_stdout(twice)
    assert f"C:0:ORIG:{first}" in _type_stdout(twice)
    assert f"C:1:ORIG:{second}" in _type_stdout(twice)


def test_help_lists_choice_values():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    help_s = f"hs-{uuid.uuid4().hex}"
    a, b = f"ca{_type_ident()}", f"cb{_type_ident()}"
    c, d = f"cc{_type_ident()}", f"cd{_type_ident()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    ab = _type_leaf(callback, option(flag, dest, type=Choice([a, b]), help=help_s))
    cd = _type_leaf(callback, option(flag, dest, type=Choice([c, d]), help=help_s))
    text = _type_leaf(callback, option(flag, dest, type=STRING, help=help_s))

    ab_page = _type_run(ab, ["--help"])
    cd_page = _type_run(cd, ["--help"])
    text_page = _type_run(text, ["--help"])
    print(
        f"ab={ab_page.stdout_text!r} cd={cd_page.stdout_text!r} "
        f"text={text_page.stdout_text!r}",
        flush=True,
    )
    assert_intentional_help(ab_page, greeting)
    assert_intentional_help(cd_page, greeting)
    assert_intentional_help(text_page, greeting)

    ab_rest = option_help_record(_type_stdout(ab_page), flag, "--help")
    ab_rest = ab_rest.replace(flag, "").replace(help_s, "")
    cd_rest = option_help_record(_type_stdout(cd_page), flag, "--help")
    cd_rest = cd_rest.replace(flag, "").replace(help_s, "")
    text_rest = option_help_record(_type_stdout(text_page), flag, "--help")
    text_rest = text_rest.replace(flag, "").replace(help_s, "")

    assert a in ab_rest and b in ab_rest, (
        f"choice values missing from option record remainder {ab_rest!r}"
    )
    assert c in cd_rest and d in cd_rest
    assert a not in cd_rest and b not in cd_rest
    assert ab_rest != cd_rest
    assert a not in text_rest and b not in text_rest, (
        f"string twin remainder unexpectedly lists choice values; "
        f"rest={text_rest!r}"
    )


# ---------------------------------------------------------------------------
# F. Integer / float ranges, clamp, open / omitted bounds
# ---------------------------------------------------------------------------


def test_integer_range_closed_bounds_without_clamp():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    lo, hi = _runtime_bounds()
    mid = lo + 3
    below = lo - 4
    above = hi + 4

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(callback, option(flag, dest, type=IntRange(min=lo, max=hi)))

    lo_ok = _type_run(leaf, [flag, str(lo)])
    hi_ok = _type_run(leaf, [flag, str(hi)])
    mid_ok = _type_run(leaf, [flag, str(mid)])
    lo_bad = _type_run(leaf, [flag, str(below)])
    hi_bad = _type_run(leaf, [flag, str(above)])
    print(
        f"lo={lo_ok.stdout_text!r} hi={hi_ok.stdout_text!r} "
        f"mid={mid_ok.stdout_text!r} below={lo_bad.stderr_text!r} "
        f"above={hi_bad.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(lo_ok, greeting)
    assert marker_occurs(_type_stdout(lo_ok), f"T:{lo * 3 + 7}")
    assert_success_marker_present(hi_ok, greeting)
    assert marker_occurs(_type_stdout(hi_ok), f"T:{hi * 3 + 7}")
    assert_success_marker_present(mid_ok, greeting)
    assert marker_occurs(_type_stdout(mid_ok), f"T:{mid * 3 + 7}")
    assert_usage_class(lo_bad, greeting)
    assert_usage_class(hi_bad, greeting)


def test_integer_range_clamp_replaces_with_nearest_included_bound():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    lo, hi = _runtime_bounds()
    mid = lo + 3
    below = lo - 7
    above = hi + 9

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    clamped = _type_leaf(
        callback, option(flag, dest, type=IntRange(min=lo, max=hi, clamp=True))
    )
    open_range = _type_leaf(callback, option(flag, dest, type=IntRange(min=lo, max=hi)))

    high = _type_run(clamped, [flag, str(above)])
    low = _type_run(clamped, [flag, str(below)])
    inner = _type_run(clamped, [flag, str(mid)])
    baseline = _type_run(open_range, [flag, str(above)])
    print(
        f"high={high.stdout_text!r} low={low.stdout_text!r} "
        f"inner={inner.stdout_text!r} base={baseline.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(high, greeting)
    assert marker_occurs(_type_stdout(high), f"T:{hi * 3 + 7}")
    assert_success_marker_present(low, greeting)
    assert marker_occurs(_type_stdout(low), f"T:{lo * 3 + 7}")
    assert_success_marker_present(inner, greeting)
    assert marker_occurs(_type_stdout(inner), f"T:{mid * 3 + 7}")
    assert_usage_class(baseline, greeting)


def test_integer_range_open_or_omitted_bounds():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    lo, hi = _runtime_bounds()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    min_open = _type_leaf(
        callback, option(flag, dest, type=IntRange(min=lo, max=hi, min_open=True))
    )
    max_open = _type_leaf(
        callback, option(flag, dest, type=IntRange(min=lo, max=hi, max_open=True))
    )
    only_max = _type_leaf(callback, option(flag, dest, type=IntRange(max=hi)))
    only_min = _type_leaf(callback, option(flag, dest, type=IntRange(min=lo)))

    min_edge = _type_run(min_open, [flag, str(lo)])
    min_in = _type_run(min_open, [flag, str(lo + 1)])
    max_edge = _type_run(max_open, [flag, str(hi)])
    max_in = _type_run(max_open, [flag, str(hi - 1)])
    far_low = -(hi + 40)
    far_high = hi + 80
    only_max_ok = _type_run(only_max, [flag, str(far_low)])
    only_max_bad = _type_run(only_max, [flag, str(hi + 1)])
    only_min_ok = _type_run(only_min, [flag, str(far_high)])
    only_min_bad = _type_run(only_min, [flag, str(lo - 1)])
    print(
        f"min_edge={min_edge.stderr_text!r} min_in={min_in.stdout_text!r} "
        f"max_edge={max_edge.stderr_text!r} max_in={max_in.stdout_text!r} "
        f"omax_ok={only_max_ok.stdout_text!r} omax_bad={only_max_bad.stderr_text!r} "
        f"omin_ok={only_min_ok.stdout_text!r} omin_bad={only_min_bad.stderr_text!r}",
        flush=True,
    )
    assert_usage_class(min_edge, greeting)
    assert_success_marker_present(min_in, greeting)
    assert marker_occurs(_type_stdout(min_in), f"T:{(lo + 1) * 3 + 7}")
    assert_usage_class(max_edge, greeting)
    assert_success_marker_present(max_in, greeting)
    assert marker_occurs(_type_stdout(max_in), f"T:{(hi - 1) * 3 + 7}")
    assert_success_marker_present(only_max_ok, greeting)
    assert marker_occurs(_type_stdout(only_max_ok), f"T:{far_low * 3 + 7}")
    assert_usage_class(only_max_bad, greeting)
    assert_success_marker_present(only_min_ok, greeting)
    assert marker_occurs(_type_stdout(only_min_ok), f"T:{far_high * 3 + 7}")
    assert_usage_class(only_min_bad, greeting)


def test_integer_open_bound_clamp_uses_nearest_included():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    lo, hi = _runtime_bounds()
    included = lo + 1

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"

    def build():
        return _type_leaf(
            callback,
            option(
                flag,
                dest,
                type=IntRange(min=lo, max=hi, min_open=True, clamp=True),
            ),
        )

    leaf = build()
    result = _type_run(leaf, [flag, str(lo)])
    print(f"open_clamp={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert marker_occurs(_type_stdout(result), f"T:{included * 3 + 7}")


def test_float_range_same_rules_and_closed_clamp():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    lo = 2 + uuid.uuid4().int % 5
    hi = lo + 6
    lo_f = float(lo)
    hi_f = float(hi)
    mid_tok = f"{lo + 2}.5"
    mid_val = lo + 2.5
    below_tok = f"{lo - 1}.5"
    above_tok = f"{hi + 1}.5"
    inner_open = f"{lo}.5"
    inner_open_val = lo + 0.5
    inner_max = f"{hi - 1}.5"
    inner_max_val = hi - 0.5
    far_low = f"-{hi + 40}.5"
    far_low_val = -(hi + 40.5)
    far_high = f"{hi + 80}.5"
    far_high_val = hi + 80.5

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_float(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    closed = _type_leaf(
        callback, option(flag, dest, type=FloatRange(min=lo_f, max=hi_f))
    )
    clamped = _type_leaf(
        callback,
        option(flag, dest, type=FloatRange(min=lo_f, max=hi_f, clamp=True)),
    )
    min_open = _type_leaf(
        callback,
        option(flag, dest, type=FloatRange(min=lo_f, max=hi_f, min_open=True)),
    )
    max_open = _type_leaf(
        callback,
        option(flag, dest, type=FloatRange(min=lo_f, max=hi_f, max_open=True)),
    )
    only_max = _type_leaf(callback, option(flag, dest, type=FloatRange(max=hi_f)))
    only_min = _type_leaf(callback, option(flag, dest, type=FloatRange(min=lo_f)))

    closed_lo = _type_run(closed, [flag, f"{lo}.0"])
    closed_hi = _type_run(closed, [flag, f"{hi}.0"])
    closed_mid = _type_run(closed, [flag, mid_tok])
    closed_below = _type_run(closed, [flag, below_tok])
    closed_above = _type_run(closed, [flag, above_tok])
    clamp_high = _type_run(clamped, [flag, above_tok])
    clamp_low = _type_run(clamped, [flag, below_tok])
    clamp_mid = _type_run(clamped, [flag, mid_tok])
    min_edge = _type_run(min_open, [flag, f"{lo}.0"])
    min_in = _type_run(min_open, [flag, inner_open])
    max_edge = _type_run(max_open, [flag, f"{hi}.0"])
    max_in = _type_run(max_open, [flag, inner_max])
    omax_ok = _type_run(only_max, [flag, far_low])
    omax_bad = _type_run(only_max, [flag, above_tok])
    omin_ok = _type_run(only_min, [flag, far_high])
    omin_bad = _type_run(only_min, [flag, below_tok])
    print(
        f"cl_lo={closed_lo.stdout_text!r} cl_hi={closed_hi.stdout_text!r} "
        f"cl_mid={closed_mid.stdout_text!r} cl_lo_bad={closed_below.stderr_text!r} "
        f"clamp_h={clamp_high.stdout_text!r} clamp_l={clamp_low.stdout_text!r} "
        f"min_e={min_edge.stderr_text!r} min_i={min_in.stdout_text!r} "
        f"max_e={max_edge.stderr_text!r} omax_ok={omax_ok.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(closed_lo, greeting)
    assert marker_occurs(_type_stdout(closed_lo), f"F:{(lo_f * 2)!r}")
    assert_success_marker_present(closed_hi, greeting)
    assert marker_occurs(_type_stdout(closed_hi), f"F:{(hi_f * 2)!r}")
    assert_success_marker_present(closed_mid, greeting)
    assert marker_occurs(_type_stdout(closed_mid), f"F:{(mid_val * 2)!r}")
    assert_usage_class(closed_below, greeting)
    assert_usage_class(closed_above, greeting)
    assert_success_marker_present(clamp_high, greeting)
    assert marker_occurs(_type_stdout(clamp_high), f"F:{(hi_f * 2)!r}")
    assert_success_marker_present(clamp_low, greeting)
    assert marker_occurs(_type_stdout(clamp_low), f"F:{(lo_f * 2)!r}")
    assert_success_marker_present(clamp_mid, greeting)
    assert marker_occurs(_type_stdout(clamp_mid), f"F:{(mid_val * 2)!r}")
    assert_usage_class(min_edge, greeting)
    assert_success_marker_present(min_in, greeting)
    assert marker_occurs(_type_stdout(min_in), f"F:{(inner_open_val * 2)!r}")
    assert_usage_class(max_edge, greeting)
    assert_success_marker_present(max_in, greeting)
    assert marker_occurs(_type_stdout(max_in), f"F:{(inner_max_val * 2)!r}")
    assert_success_marker_present(omax_ok, greeting)
    assert marker_occurs(_type_stdout(omax_ok), f"F:{(far_low_val * 2)!r}")
    assert_usage_class(omax_bad, greeting)
    assert_success_marker_present(omin_ok, greeting)
    assert marker_occurs(_type_stdout(omin_ok), f"F:{(far_high_val * 2)!r}")
    assert_usage_class(omin_bad, greeting)


def test_float_range_refuses_clamp_when_bound_open():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    lo, hi = 1.5, 8.5

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_float(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"

    def open_min():
        return _type_leaf(
            callback,
            option(
                flag,
                dest,
                type=FloatRange(min=lo, max=hi, min_open=True, clamp=True),
            ),
        )

    def open_max():
        return _type_leaf(
            callback,
            option(
                flag,
                dest,
                type=FloatRange(min=lo, max=hi, max_open=True, clamp=True),
            ),
        )

    def closed_clamp():
        return _type_leaf(
            callback,
            option(flag, dest, type=FloatRange(min=lo, max=hi, clamp=True)),
        )

    assert_declaration_refused(open_min)
    assert_declaration_refused(open_max)
    built = closed_clamp()
    above = _type_run(built, [flag, "12.5"])
    print(f"closed_clamp={above.stdout_text!r}", flush=True)
    assert_success_marker_present(above, greeting)
    assert marker_occurs(_type_stdout(above), f"F:{(hi * 2)!r}")


# ---------------------------------------------------------------------------
# G. Custom type, conversion function, prompt-time, identify parameter
# ---------------------------------------------------------------------------


def test_custom_type_converts_string_and_passes_through_ready_value():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    prefix = f"px-{uuid.uuid4().hex[:10]}"
    token = f"tok-{_type_ident()}"
    ready = _Tagged(f"ready-{_type_ident()}", f"READY:{prefix}")
    marked = _MarkedType(prefix)

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_tagged(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(callback, option(flag, dest, type=marked, default=ready))

    converted = _type_run(leaf, [flag, token])
    omitted = _type_run(leaf, [])
    print(
        f"conv={converted.stdout_text!r} omit={omitted.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(converted, greeting)
    assert f"TAG:STRCONV:{prefix}" in _type_stdout(converted)
    assert f"PAY:{token}" in _type_stdout(converted)
    assert_success_marker_present(omitted, greeting)
    assert f"TAG:READY:{prefix}" in _type_stdout(omitted)
    assert f"TAG:STRCONV:{prefix}" not in _type_stdout(omitted)
    assert f"PAY:{ready.payload}" in _type_stdout(omitted)


def test_conversion_function_is_accepted_as_type():
    greeting = _type_hi()
    flag = f"--{_type_ident()}"
    dest = _type_ident()
    prefix = f"fn-{uuid.uuid4().hex[:10]}"
    legal = f"ok-{_type_ident()}"
    illegal = unrelated_dispatch_token(legal)

    def convert_fn(value):
        if isinstance(value, _Tagged):
            return value
        if value == legal:
            return _Tagged(value, f"FNCONV:{prefix}")
        raise ValueError("rejected")

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_tagged(kwargs[dest])

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(callback, option(flag, dest, type=convert_fn))

    ok = _type_run(leaf, [flag, legal])
    bad = _type_run(leaf, [flag, illegal])
    print(f"ok={ok.stdout_text!r} bad={bad.stderr_text!r}", flush=True)
    assert_success_marker_present(ok, greeting)
    assert f"TAG:FNCONV:{prefix}" in _type_stdout(ok)
    assert f"PAY:{legal}" in _type_stdout(ok)
    assert_usage_class(bad, greeting)
    assert bad.exit_code == 2
    assert greeting not in _type_stdout(bad)


def test_conversion_works_at_prompt_without_parameter():
    greeting = _type_hi()
    prefix = f"pr-{uuid.uuid4().hex[:10]}"
    token = f"zxq-{uuid.uuid4().hex}"
    marked = _MarkedType(prefix)
    ask = f"ask-{_type_ident()}"
    flag = f"--{_type_ident()}"
    dest = _type_ident()

    def callback() -> None:
        print(greeting, flush=True)
        received = prompt(ask, type=marked)
        _emit_tagged(received)

    callback.__name__ = f"{_type_ident()}_{_type_ident()}"
    leaf = _type_leaf(callback)

    prompted = _type_run(leaf, [], stdin=f"{token}\n")
    print(f"prompted={prompted.stdout_text!r}", flush=True)
    assert_success_marker_present(prompted, greeting)
    assert f"TAG:STRCONV:{prefix}" in _type_stdout(prompted)
    assert f"PAY:{token}" in _type_stdout(prompted)

    def int_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    int_cb.__name__ = f"{_type_ident()}_{_type_ident()}"
    int_cli = _type_leaf(int_cb, option(flag, dest, type=INT))
    int_bad = _type_run(int_cli, [flag, token])
    print(f"int_bad={int_bad.stderr_text!r}", flush=True)
    assert_usage_class(int_bad, greeting)

    returned = call_with_fed_stdin(f"{token}\n", lambda: prompt(ask, type=marked))
    print(
        f"direct via={getattr(returned, 'via', None)!r} "
        f"payload={getattr(returned, 'payload', None)!r}",
        flush=True,
    )
    via = getattr(returned, "via", None)
    payload = getattr(returned, "payload", None)
    if via is None or payload is None:
        raise AssertionError(
            f"direct prompt did not return a converted value; got {returned!r}"
        )
    assert via == f"STRCONV:{prefix}", (
        f"direct prompt missing custom mark; via={via!r} value={returned!r}"
    )
    assert payload == token, (
        f"direct prompt payload {payload!r} is not token {token!r}"
    )


def test_conversion_failure_is_usage_error_identifying_parameter():
    greeting = _type_hi()
    flag_a = f"--{_type_ident()}"
    flag_b = f"--{_type_ident()}"
    dest = _type_ident()
    dest_ok = _type_ident()
    dest_bad = _type_ident()
    illegal = unrelated_dispatch_token()
    good_n = _type_int()
    bad_n = unrelated_dispatch_token()

    def typed_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    typed_cb.__name__ = f"{_type_ident()}_{_type_ident()}"
    cli_a = _type_leaf(typed_cb, option(flag_a, dest, type=INT))
    cli_b = _type_leaf(typed_cb, option(flag_b, dest, type=INT))
    fail_a = _type_run(cli_a, [flag_a, illegal])
    fail_b = _type_run(cli_b, [flag_b, illegal])
    print(f"a={fail_a.stderr_text!r} b={fail_b.stderr_text!r}", flush=True)
    assert_usage_names_option(fail_a, greeting, flag_a)
    assert_usage_names_option(fail_b, greeting, flag_b)
    assert flag_a not in _type_stderr(fail_b)
    assert flag_b not in _type_stderr(fail_a)

    def half_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest_ok])
        _emit_arith(kwargs[dest_bad])

    half_cb.__name__ = f"{_type_ident()}_{_type_ident()}"
    half = _type_leaf(
        half_cb,
        option(flag_a, dest_ok, type=INT),
        option(flag_b, dest_bad, type=INT),
    )
    half_fail = _type_run(half, [flag_a, str(good_n), flag_b, bad_n])
    print(f"half={half_fail.stderr_text!r} out={half_fail.stdout_text!r}", flush=True)
    assert_usage_class(half_fail, greeting)
