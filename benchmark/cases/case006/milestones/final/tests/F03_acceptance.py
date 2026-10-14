# feature: F03
"""Option declaration, parsing, and fill (FP-03).

Assertions stay at the PRD's precision: optional/required options, long
and short forms, stacking, ``--`` ending option parsing, prefixes,
boolean and on/off flags, counting, repeatable and multi-value options,
optional values, named environment fill including file/path pathsep
split, four-tier fill order, command-line values never prompting,
feature-switch explicitness, parameter callbacks, hidden-from-callback,
deprecation, unknown options, and leaf versus group mixing. Wording of
usage sentences, ``None``, ``iterable``, and exception types are not
pinned.
"""

from __future__ import annotations

import os
import uuid

import pytest
from optlyn import (
    INT,
    STRING,
    BadParameter,
    File,
    Path,
    Tuple,
    argument,
    command,
    group,
    option,
)
from F03_helpers import (
    _bound_keys,
    _eager_finish,
    _emit_path_texts,
    _enc_of,
    _emit_enc,
    _emit_pairs,
    _option_env,
    _option_hi,
    _option_ident,
    _option_int,
    _option_leaf,
    _option_run,
    _print_arith,
    _print_seq,
    _require_leftover_extra,
    _shorts,
    _two_empty_file_paths,
    assert_activation_unlike_omitted,
    assert_declared_env_unmatched,
    assert_omitted_required_names_option,
    assert_parameter_callback_refused,
)

from _helpers import (
    assert_declaration_refused,
    assert_deprecation_distinct,
    assert_eager_identity,
    assert_intentional_help,
    assert_marker_absent,
    assert_success_marker_present,
    assert_usage_class,
    assert_usage_kinds_unlike,
    assert_usage_names_option,
    caller_visible_remainder,
    labeled_stdout_field,
    labeled_stdout_fields,
    marker_occurs,
    unrelated_dispatch_token,
)

_BOOL_ON = ("true", "1", "yes", "on", "t", "y")
_BOOL_OFF = ("false", "0", "no", "off", "f", "n")


# ---------------------------------------------------------------------------
# Public entry: option declaration on a command or group
# ---------------------------------------------------------------------------


def test_option_declared_on_command_or_group():
    greeting = _option_hi()
    flag_stem = _option_ident()
    flag = f"--{flag_stem}"
    dest = _option_ident()
    inferred = flag_stem.replace("-", "_")
    assert dest != inferred
    value = _option_ident()
    g_stem = _option_ident()
    gflag = f"--{g_stem}"
    gdest = _option_ident()
    g_inferred = g_stem.replace("-", "_")
    assert gdest != g_inferred
    gvalue = _option_ident()
    child_name = _option_ident()
    sub_hi = f"SUB:{uuid.uuid4().hex}:"

    def leaf_cb(**kwargs) -> None:
        received = kwargs[dest]
        print(greeting, flush=True)
        print(f"V:{received}", flush=True)

    leaf_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = command()(option(flag, dest)(leaf_cb))

    def grp_cb(**kwargs) -> None:
        received = kwargs[gdest]
        print(greeting, flush=True)
        print(f"G:{received}", flush=True)

    grp_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    grp = group()(option(gflag, gdest)(grp_cb))

    def child() -> None:
        print(sub_hi, flush=True)

    child.__name__ = f"{_option_ident()}_{_option_ident()}"
    grp.add_command(command(name=child_name)(child))

    on_command = _option_run(leaf, [flag, value])
    on_group = _option_run(grp, [gflag, gvalue, child_name])
    print(
        f"command={on_command.stdout_text!r} group={on_group.stdout_text!r} "
        f"dest={dest!r} inferred={inferred!r}",
        flush=True,
    )
    assert_success_marker_present(on_command, greeting)
    assert marker_occurs(on_command.stdout_text, f"V:{value}")
    assert_success_marker_present(on_group, greeting)
    assert marker_occurs(on_group.stdout_text, f"G:{gvalue}")
    assert sub_hi in on_group.stdout_text


# ---------------------------------------------------------------------------
# A. Optional, absent, default, type inference, callable default
# ---------------------------------------------------------------------------


def test_omitted_optional_without_default_is_absent():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    provided = _option_ident()
    defaulted = _option_ident()
    false_flag = f"--{_option_ident()}"
    false_dest = _option_ident()
    count_flag = f"--{_option_ident()}"
    count_dest = _option_ident()

    def optional_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[dest])

    optional_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    optional = _option_leaf(optional_cb, option(flag, dest))

    def default_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[dest])

    default_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    with_default = _option_leaf(default_cb, option(flag, dest, default=defaulted))

    def bool_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[false_dest])

    bool_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    boolean = _option_leaf(bool_cb, option(false_flag, false_dest, is_flag=True))

    def count_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[count_dest])

    count_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    counting = _option_leaf(count_cb, option(count_flag, count_dest, count=True))

    omitted = _option_run(optional, [])
    given = _option_run(optional, [flag, provided])
    used_default = _option_run(with_default, [])
    bool_omitted = _option_run(boolean, [])
    count_omitted = _option_run(counting, [])
    print(
        f"omit={omitted.stdout_text!r} given={given.stdout_text!r} "
        f"default={used_default.stdout_text!r} bool={bool_omitted.stdout_text!r} "
        f"count={count_omitted.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(omitted, greeting)
    assert_success_marker_present(given, greeting)
    assert_success_marker_present(used_default, greeting)
    assert_success_marker_present(bool_omitted, greeting)
    assert_success_marker_present(count_omitted, greeting)

    absent_enc = _enc_of(omitted, greeting)
    given_enc = _enc_of(given, greeting)
    default_enc = _enc_of(used_default, greeting)
    false_enc = _enc_of(bool_omitted, greeting)
    zero_enc = _enc_of(count_omitted, greeting)
    encodings = {
        "absent": absent_enc,
        "provided": given_enc,
        "default": default_enc,
        "false": false_enc,
        "zero": zero_enc,
    }
    print(f"encodings={encodings!r}", flush=True)
    unique = set(encodings.values())
    assert len(unique) == 5, (
        "absent / provided / declared-default / boolean-false / counting-zero "
        f"encodings are not all distinct; encodings={encodings!r}"
    )
    assert provided in given.stdout_text
    assert defaulted in used_default.stdout_text
    assert provided not in omitted.stdout_text


def test_declared_default_used_when_omitted():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    defaulted = _option_ident()
    provided = _option_ident()
    assert defaulted != provided

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, default=defaulted))

    omitted = _option_run(leaf, [])
    given = _option_run(leaf, [flag, provided])
    print(f"omit={omitted.stdout_text!r} given={given.stdout_text!r}", flush=True)
    assert_success_marker_present(omitted, greeting)
    assert_success_marker_present(given, greeting)
    assert marker_occurs(omitted.stdout_text, f"V:{defaulted}")
    assert marker_occurs(given.stdout_text, f"V:{provided}")
    assert_marker_absent(given.stdout_text, f"V:{defaulted}")


def test_type_inferred_from_integer_default():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    default_n = _option_int()
    provided = default_n + 3 + (uuid.uuid4().int % 9)
    expected = provided * 3 + 7
    str_flag = f"--{_option_ident()}"
    str_dest = _option_ident()
    str_default = str(_option_int())
    str_provided = str(_option_int())

    def int_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _print_arith(kwargs[dest])

    int_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    inferred = _option_leaf(int_cb, option(flag, dest, default=default_n))

    def str_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _print_arith(kwargs[str_dest])

    str_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    as_text = _option_leaf(str_cb, option(str_flag, str_dest, type=STRING, default=str_default))

    as_int = _option_run(inferred, [f"{flag}={provided}"])
    as_str = _option_run(as_text, [f"{str_flag}={str_provided}"])
    print(f"int={as_int.stdout_text!r} str={as_str.stdout_text!r}", flush=True)
    assert_success_marker_present(as_int, greeting)
    assert_success_marker_present(as_str, greeting)
    assert labeled_stdout_field(as_int, "T:") == str(expected), (
        f"integer default did not infer integer conversion; "
        f"stdout={as_int.stdout_text!r}"
    )
    assert labeled_stdout_field(as_str, "S:") == repr(str_provided), (
        f"explicit string type delivered an integer; stdout={as_str.stdout_text!r}"
    )
    assert labeled_stdout_fields(as_str, "T:") == []


def test_callable_default_runs_only_when_no_earlier_source():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    returned = _option_ident()
    cli_val = _option_ident()
    env_val = _option_ident()
    map_val = _option_ident()
    call_mark = f"CALL:{uuid.uuid4().hex}:"

    def factory() -> str:
        print(call_mark, flush=True)
        return returned

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, envvar=env_name, default=factory))

    none = _option_run(leaf, [])
    from_cli = _option_run(leaf, [flag, cli_val], env={env_name: env_val})
    from_env = _option_run(leaf, [], env={env_name: env_val})
    from_map = _option_run(leaf, [], default_map={dest: map_val})
    print(
        f"none={none.stdout_text!r} cli={from_cli.stdout_text!r} "
        f"env={from_env.stdout_text!r} map={from_map.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(none, greeting)
    assert_success_marker_present(from_cli, greeting)
    assert_success_marker_present(from_env, greeting)
    assert_success_marker_present(from_map, greeting)
    assert call_mark in none.stdout_text
    assert marker_occurs(none.stdout_text, f"V:{returned}")
    assert call_mark not in from_cli.stdout_text
    assert marker_occurs(from_cli.stdout_text, f"V:{cli_val}")
    assert call_mark not in from_env.stdout_text
    assert marker_occurs(from_env.stdout_text, f"V:{env_val}")
    assert call_mark not in from_map.stdout_text
    assert marker_occurs(from_map.stdout_text, f"V:{map_val}")


# ---------------------------------------------------------------------------
# B. Names, long/short forms, stacking, destination inference
# ---------------------------------------------------------------------------


def test_short_long_and_alias_set_same_destination():
    greeting = _option_hi()
    dest = _option_ident()
    short = _shorts(1)[0]
    long_name = _option_ident()
    alias = _option_ident()
    value = _option_ident()
    short_flag = f"-{short}"
    long_flag = f"--{long_name}"
    alias_flag = f"--{alias}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(short_flag, long_flag, alias_flag, dest))

    via_short = _option_run(leaf, [short_flag, value])
    via_long = _option_run(leaf, [long_flag, value])
    via_alias = _option_run(leaf, [alias_flag, value])
    print(
        f"short={via_short.stdout_text!r} long={via_long.stdout_text!r} "
        f"alias={via_alias.stdout_text!r}",
        flush=True,
    )
    for result in (via_short, via_long, via_alias):
        assert_success_marker_present(result, greeting)
        assert marker_occurs(result.stdout_text, f"V:{value}")


def test_long_option_equals_and_space_forms():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    value = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest))

    equals = _option_run(leaf, [f"{flag}={value}"])
    spaced = _option_run(leaf, [flag, value])
    print(f"equals={equals.stdout_text!r} spaced={spaced.stdout_text!r}", flush=True)
    assert_success_marker_present(equals, greeting)
    assert_success_marker_present(spaced, greeting)
    assert marker_occurs(equals.stdout_text, f"V:{value}")
    assert marker_occurs(spaced.stdout_text, f"V:{value}")


def test_short_value_next_token_or_attached():
    greeting = _option_hi()
    short = _shorts(1)[0]
    dest = _option_ident()
    value = _option_int()
    expected = value * 3 + 7
    flag = f"-{short}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _print_arith(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, type=INT))

    next_tok = _option_run(leaf, [flag, str(value)])
    attached = _option_run(leaf, [f"{flag}{value}"])
    print(f"next={next_tok.stdout_text!r} attached={attached.stdout_text!r}", flush=True)
    assert_success_marker_present(next_tok, greeting)
    assert_success_marker_present(attached, greeting)
    assert labeled_stdout_field(next_tok, "T:") == str(expected)
    assert labeled_stdout_field(attached, "T:") == str(expected)


def test_stacked_shorts_equivalent_to_separate_flags():
    greeting = _option_hi()
    a, b, c = _shorts(3)
    da, db, dc = _option_ident(), _option_ident(), _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"A:{kwargs[da]!r}", flush=True)
        print(f"B:{kwargs[db]!r}", flush=True)
        print(f"C:{kwargs[dc]!r}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(f"-{a}", da, is_flag=True),
        option(f"-{b}", db, is_flag=True),
        option(f"-{c}", dc, is_flag=True),
    )

    stacked = _option_run(leaf, [f"-{a}{b}{c}"])
    separate = _option_run(leaf, [f"-{a}", f"-{b}", f"-{c}"])
    print(f"stacked={stacked.stdout_text!r} separate={separate.stdout_text!r}", flush=True)
    for result in (stacked, separate):
        assert_success_marker_present(result, greeting)
        assert f"A:{True!r}" in result.stdout_text
        assert marker_occurs(result.stdout_text, f"B:{True!r}")
        assert f"C:{True!r}" in result.stdout_text


def test_stacked_last_flag_takes_attached_or_next_token():
    greeting = _option_hi()
    v, n = _shorts(2)
    flag_dest = _option_ident()
    num_dest = _option_ident()
    value = _option_int()
    expected = value * 3 + 7

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"F:{kwargs[flag_dest]!r}", flush=True)
        _print_arith(kwargs[num_dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(f"-{v}", flag_dest, is_flag=True),
        option(f"-{n}", num_dest, type=INT),
    )

    attached = _option_run(leaf, [f"-{v}{n}{value}"])
    next_tok = _option_run(leaf, [f"-{v}{n}", str(value)])
    print(
        f"attached={attached.stdout_text!r} next={next_tok.stdout_text!r}",
        flush=True,
    )
    for result in (attached, next_tok):
        assert_success_marker_present(result, greeting)
        assert marker_occurs(result.stdout_text, f"F:{True!r}")
        assert labeled_stdout_field(result, "T:") == str(expected)


def test_multichar_short_is_stacked_not_named_dbg():
    greeting = _option_hi()
    d, b, g = _shorts(3)
    dd, db, dg = _option_ident(), _option_ident(), _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"D:{kwargs[dd]!r}", flush=True)
        print(f"B:{kwargs[db]!r}", flush=True)
        print(f"G:{kwargs[dg]!r}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(f"-{d}", dd, is_flag=True),
        option(f"-{b}", db, is_flag=True),
        option(f"-{g}", dg, is_flag=True),
    )

    result = _option_run(leaf, [f"-{d}{b}{g}"])
    print(f"stack={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert f"D:{True!r}" in result.stdout_text
    assert marker_occurs(result.stdout_text, f"B:{True!r}")
    assert marker_occurs(result.stdout_text, f"G:{True!r}")


def test_destination_inferred_from_long_then_short():
    greeting = _option_hi()
    short = _shorts(1)[0]
    left, right = _option_ident(), _option_ident()
    long_flag = f"--{left}-{right}"
    long_dest = f"{left}_{right}"
    value = _option_ident()

    def only_short(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"S:{kwargs[short]}", flush=True)

    only_short.__name__ = f"{_option_ident()}_{_option_ident()}"
    short_only = _option_leaf(only_short, option(f"-{short}"))

    def long_and_short(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"L:{kwargs[long_dest]}", flush=True)
        assert short not in kwargs

    long_and_short.__name__ = f"{_option_ident()}_{_option_ident()}"
    both = _option_leaf(long_and_short, option(long_flag, f"-{short}"))

    via_short = _option_run(short_only, [f"-{short}", value])
    via_long = _option_run(both, [long_flag, value])
    print(f"short={via_short.stdout_text!r} long={via_long.stdout_text!r}", flush=True)
    assert_success_marker_present(via_short, greeting)
    assert_success_marker_present(via_long, greeting)
    assert marker_occurs(via_short.stdout_text, f"S:{value}")
    assert f"L:{value}" in via_long.stdout_text


def test_identifier_name_wins_inference_over_dashed_long():
    greeting = _option_hi()
    ident = _option_ident()
    left, right = _option_ident(), _option_ident()
    dashed = f"--{left}-{right}"
    underscored = f"{left}_{right}"
    value = _option_ident()
    assert ident != underscored

    def with_ident(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"KEYS:{','.join(sorted(kwargs))}", flush=True)
        assert underscored not in kwargs
        print(f"I:{kwargs[ident]}", flush=True)

    with_ident.__name__ = f"{_option_ident()}_{_option_ident()}"
    ident_cli = _option_leaf(with_ident, option(ident, dashed))

    def long_only(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"KEYS:{','.join(sorted(kwargs))}", flush=True)
        assert ident not in kwargs
        print(f"U:{kwargs[underscored]}", flush=True)

    long_only.__name__ = f"{_option_ident()}_{_option_ident()}"
    long_cli = _option_leaf(long_only, option(dashed))

    via_dashed = _option_run(ident_cli, [dashed, value])
    via_long = _option_run(long_cli, [dashed, value])
    print(
        f"ident={via_dashed.stdout_text!r} long={via_long.stdout_text!r} "
        f"underscored={underscored!r} dashed={dashed!r}",
        flush=True,
    )
    assert_success_marker_present(via_dashed, greeting)
    assert_success_marker_present(via_long, greeting)
    assert f"I:{value}" in via_dashed.stdout_text
    assert f"U:{value}" in via_long.stdout_text
    ident_keys = _bound_keys(via_dashed, greeting)
    long_keys = _bound_keys(via_long, greeting)
    assert ident in ident_keys
    assert underscored not in ident_keys
    assert underscored in long_keys
    assert ident not in long_keys


def test_double_dash_ends_option_parsing():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    extra_dest = _option_ident()
    value = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(flag, dest),
        argument(extra_dest, nargs=-1),
    )

    consumed = _option_run(leaf, [flag, value])
    ended = _option_run(leaf, ["--", flag, value])
    omitted = _option_run(leaf, [])
    print(
        f"consumed={consumed.stdout_text!r} ended={ended.stdout_text!r} "
        f"omitted={omitted.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(consumed, greeting)
    assert_success_marker_present(ended, greeting)
    assert_success_marker_present(omitted, greeting)
    consumed_enc = _enc_of(consumed, greeting)
    ended_enc = _enc_of(ended, greeting)
    omitted_enc = _enc_of(omitted, greeting)
    assert consumed_enc != omitted_enc
    assert ended_enc == omitted_enc
    assert ended_enc != consumed_enc
    assert value in consumed.stdout_text
    assert consumed_enc == repr(value)


# ---------------------------------------------------------------------------
# C. Leaf mixing and group option parsing ending at the subcommand
# ---------------------------------------------------------------------------


def test_leaf_mixes_option_after_argument():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    arg_dest = _option_ident()
    filename = f"{_option_ident()}.txt"
    value = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"F:{kwargs[arg_dest]}", flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest), argument(arg_dest))

    after = _option_run(leaf, [filename, flag, value])
    before = _option_run(leaf, [flag, value, filename])
    print(f"after={after.stdout_text!r} before={before.stdout_text!r}", flush=True)
    for result in (after, before):
        assert_success_marker_present(result, greeting)
        assert marker_occurs(result.stdout_text, f"F:{filename}")
        assert marker_occurs(result.stdout_text, f"V:{value}")


def test_leaf_mixing_can_be_disabled():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    arg_dest = _option_ident()
    filename = f"{_option_ident()}.txt"
    value = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)
        print(f"F:{kwargs[arg_dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    mixed = _option_leaf(callback, option(flag, dest), argument(arg_dest))
    blocked = _option_leaf(
        callback,
        option(flag, dest),
        argument(arg_dest),
        context_settings={"allow_interspersed_args": False},
    )

    live = _option_run(mixed, [filename, flag, value])
    disabled = _option_run(blocked, [filename, flag, value])
    option_first = _option_run(blocked, [flag, value, filename])
    print(
        f"live={live.stdout_text!r} disabled={disabled.stdout_text!r} "
        f"first={option_first.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(live, greeting)
    assert marker_occurs(live.stdout_text, f"V:{value}")
    assert_success_marker_present(option_first, greeting)
    assert marker_occurs(option_first.stdout_text, f"V:{value}")
    assert marker_occurs(option_first.stdout_text, f"F:{filename}")
    if disabled.exit_code == 0:
        assert greeting in disabled.stdout_text
        assert not marker_occurs(disabled.stdout_text, f"V:{value}"), (
            "disabled mixing still delivered the option value after the "
            f"argument; stdout={disabled.stdout_text!r}"
        )
    else:
        assert_usage_class(disabled, greeting)


def test_group_options_stop_at_subcommand_by_default():
    greeting = _option_hi()
    sub_hi = f"SUB:{uuid.uuid4().hex}:"
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    child_name = _option_ident()
    value = _option_ident()

    def grp_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"G:{kwargs[dest]!r}", flush=True)

    grp_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    grp = group()(option(flag, dest)(grp_cb))

    def child() -> None:
        print(sub_hi, flush=True)

    child.__name__ = f"{_option_ident()}_{_option_ident()}"
    grp.add_command(command(name=child_name)(child))

    before = _option_run(grp, [flag, value, child_name])
    after = _option_run(grp, [child_name, flag, value])
    print(f"before={before.stdout_text!r} after={after.stdout_text!r}", flush=True)
    assert_success_marker_present(before, greeting)
    assert sub_hi in before.stdout_text
    assert marker_occurs(before.stdout_text, f"G:{value!r}")
    assert not marker_occurs(after.stdout_text, f"G:{value!r}"), (
        "group option after the subcommand name was delivered to the group; "
        f"stdout={after.stdout_text!r} stderr={after.stderr_text!r}"
    )


def test_group_mixing_can_be_enabled():
    greeting = _option_hi()
    sub_hi = f"SUB:{uuid.uuid4().hex}:"
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    child_name = _option_ident()
    value = _option_ident()

    def grp_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"G:{kwargs[dest]}", flush=True)

    grp_cb.__name__ = f"{_option_ident()}_{_option_ident()}"

    def child_off() -> None:
        print(sub_hi, flush=True)

    child_off.__name__ = f"{_option_ident()}_{_option_ident()}"

    def child_on() -> None:
        print(sub_hi, flush=True)

    child_on.__name__ = f"{_option_ident()}_{_option_ident()}"

    off = group()(option(flag, dest)(grp_cb))
    off.add_command(command(name=child_name)(child_off))
    on = group(context_settings={"allow_interspersed_args": True})(
        option(flag, dest)(grp_cb)
    )
    on.add_command(command(name=child_name)(child_on))

    blocked = _option_run(off, [child_name, flag, value])
    enabled = _option_run(on, [child_name, flag, value])
    print(f"blocked={blocked.stdout_text!r} enabled={enabled.stdout_text!r}", flush=True)
    assert_marker_absent(blocked.stdout_text, f"G:{value}")
    assert_success_marker_present(enabled, greeting)
    assert marker_occurs(enabled.stdout_text, f"G:{value}")
    assert sub_hi in enabled.stdout_text


def test_child_option_after_subcommand_is_parsed():
    greeting = _option_hi()
    sub_hi = f"SUB:{uuid.uuid4().hex}:"
    gflag = f"--{_option_ident()}"
    gdest = _option_ident()
    cflag = f"--{_option_ident()}"
    cdest = _option_ident()
    child_name = _option_ident()
    value = _option_ident()

    def grp_cb(**kwargs) -> None:
        print(greeting, flush=True)

    grp_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    grp = group()(option(gflag, gdest)(grp_cb))

    def child(**kwargs) -> None:
        print(sub_hi, flush=True)
        print(f"C:{kwargs[cdest]}", flush=True)

    child.__name__ = f"{_option_ident()}_{_option_ident()}"
    grp.add_command(_option_leaf(child, option(cflag, cdest), name=child_name))

    result = _option_run(grp, [child_name, cflag, value])
    print(f"child={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert sub_hi in result.stdout_text
    assert f"C:{value}" in result.stdout_text


def test_help_before_subcommand_is_help_for_parent():
    greeting = _option_hi()
    sub_hi = f"SUB:{uuid.uuid4().hex}:"
    desc = f"Parent {uuid.uuid4().hex} tool."
    child_name = _option_ident()
    child_desc = f"Child {uuid.uuid4().hex} leaf."

    def grp_cb() -> None:
        print(greeting, flush=True)

    grp_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    grp_cb.__doc__ = desc
    grp = group()(grp_cb)

    def child() -> None:
        print(sub_hi, flush=True)

    child.__name__ = f"{_option_ident()}_{_option_ident()}"
    child.__doc__ = child_desc
    grp.add_command(command(name=child_name)(child))

    parent_help = _option_run(grp, ["--help", child_name])
    child_help = _option_run(grp, [child_name, "--help"])
    print(
        f"parent={parent_help.stdout_text!r} child={child_help.stdout_text!r}",
        flush=True,
    )
    assert_intentional_help(parent_help, greeting, desc)
    assert sub_hi not in parent_help.stdout_text
    assert_intentional_help(child_help, sub_hi, child_desc)
    assert child_desc in child_help.stdout_text
    assert parent_help.stdout_text != child_help.stdout_text


# ---------------------------------------------------------------------------
# D. Required option omitted is a usage error
# ---------------------------------------------------------------------------


def test_omitted_required_option_is_usage_error_naming_option():
    greeting = _option_hi()
    dest = _option_ident()
    value = _option_ident()
    flag_a = f"--{_option_ident()}"
    flag_b = f"--{_option_ident()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    first = _option_leaf(callback, option(flag_a, dest, required=True))
    second = _option_leaf(callback, option(flag_b, dest, required=True))

    missing_a = _option_run(first, [])
    missing_b = _option_run(second, [])
    given = _option_run(first, [flag_a, value])
    print(
        f"miss_a={missing_a.stderr_text!r} miss_b={missing_b.stderr_text!r} "
        f"given={given.stdout_text!r}",
        flush=True,
    )
    assert_omitted_required_names_option(missing_a, greeting, flag_a, flag_b)
    assert_omitted_required_names_option(missing_b, greeting, flag_b, flag_a)
    assert_success_marker_present(given, greeting)
    assert marker_occurs(given.stdout_text, f"V:{value}")


def test_required_option_satisfied_from_named_env():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    value = _option_int()
    expected = value * 3 + 7

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _print_arith(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback, option(flag, dest, required=True, type=INT, envvar=env_name)
    )

    filled = _option_run(leaf, [], env={env_name: str(value)})
    missing = _option_run(leaf, [])
    print(f"filled={filled.stdout_text!r} missing={missing.stderr_text!r}", flush=True)
    assert_success_marker_present(filled, greeting)
    assert labeled_stdout_field(filled, "T:") == str(expected)
    assert_omitted_required_names_option(missing, greeting, flag)


# ---------------------------------------------------------------------------
# E. Boolean flags, on/off pairs, prefixes, feature switches
# ---------------------------------------------------------------------------


def test_boolean_flag_omitted_false_unless_true_default():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    true_flag = f"--{_option_ident()}"
    true_dest = _option_ident()

    def off_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[dest])

    off_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    off = _option_leaf(off_cb, option(flag, dest, is_flag=True))

    def on_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[true_dest])

    on_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    on = _option_leaf(on_cb, option(true_flag, true_dest, is_flag=True, default=True))

    omitted = _option_run(off, [])
    present = _option_run(off, [flag])
    true_omit = _option_run(on, [])
    print(
        f"omit={omitted.stdout_text!r} present={present.stdout_text!r} "
        f"true_omit={true_omit.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(omitted, greeting)
    assert_success_marker_present(present, greeting)
    assert_success_marker_present(true_omit, greeting)
    omit_enc = _enc_of(omitted, greeting)
    present_enc = _enc_of(present, greeting)
    true_enc = _enc_of(true_omit, greeting)
    assert omit_enc != present_enc
    assert omit_enc != true_enc
    assert present_enc == true_enc


def test_on_off_pair_tokens():
    greeting = _option_hi()
    on_option_ident = _option_ident()
    off_option_ident = _option_ident()
    slash_name = _option_ident()
    plus_ch = _shorts(1)[0]
    dest_a, dest_b, dest_c = _option_ident(), _option_ident(), _option_ident()

    def make(*decls, dest_name: str):
        def inner(**kwargs) -> None:
            print(greeting, flush=True)
            _emit_enc(kwargs[dest_name])

        inner.__name__ = f"{_option_ident()}_{_option_ident()}"
        return _option_leaf(inner, option(*decls, dest_name))

    dashed = make(f"--{on_option_ident}/--{off_option_ident}", dest_name=dest_a)
    slashed = make(f"/{slash_name};/no-{slash_name}", dest_name=dest_b)
    plused = make(f"+{plus_ch}/-{plus_ch}", dest_name=dest_c)

    cases = (
        (dashed, f"--{on_option_ident}", f"--{off_option_ident}"),
        (slashed, f"/{slash_name}", f"/no-{slash_name}"),
        (plused, f"+{plus_ch}", f"-{plus_ch}"),
    )
    for cli, on_tok, off_tok in cases:
        on_run = _option_run(cli, [on_tok])
        off_run = _option_run(cli, [off_tok])
        omitted = _option_run(cli, [])
        print(
            f"on={on_run.stdout_text!r} off={off_run.stdout_text!r} "
            f"omit={omitted.stdout_text!r}",
            flush=True,
        )
        assert_success_marker_present(on_run, greeting)
        assert_success_marker_present(off_run, greeting)
        assert_success_marker_present(omitted, greeting)
        on_enc = _enc_of(on_run, greeting)
        off_enc = _enc_of(off_run, greeting)
        omit_enc = _enc_of(omitted, greeting)
        assert on_enc != off_enc
        assert off_enc == omit_enc


def test_slash_and_plus_prefixes():
    greeting = _option_hi()
    slash_name = _option_ident()
    plus_name = _option_ident()
    slash_dest = _option_ident()
    plus_dest = _option_ident()
    dashed_slash = f"--{slash_name}"
    dashed_plus = f"--{plus_name}"

    def slash_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[slash_dest])

    slash_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    slash_cli = _option_leaf(slash_cb, option(f"/{slash_name}", slash_dest, is_flag=True))

    def plus_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[plus_dest])

    plus_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    plus_cli = _option_leaf(plus_cb, option(f"+{plus_name}", plus_dest, is_flag=True))

    slash_ok = _option_run(slash_cli, [f"/{slash_name}"])
    slash_wrong = _option_run(slash_cli, [dashed_slash])
    plus_ok = _option_run(plus_cli, [f"+{plus_name}"])
    plus_wrong = _option_run(plus_cli, [dashed_plus])
    print(
        f"slash_ok={slash_ok.stdout_text!r} slash_wrong={slash_wrong.stdout_text!r} "
        f"plus_ok={plus_ok.stdout_text!r} plus_wrong={plus_wrong.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(slash_ok, greeting)
    assert _enc_of(slash_ok, greeting) != _enc_of(_option_run(slash_cli, []), greeting)
    if slash_wrong.exit_code == 0:
        assert greeting in slash_wrong.stdout_text
        assert _enc_of(slash_wrong, greeting) != _enc_of(slash_ok, greeting)
    else:
        assert_usage_class(slash_wrong, greeting)
    assert_success_marker_present(plus_ok, greeting)
    if plus_wrong.exit_code == 0:
        assert _enc_of(plus_wrong, greeting) != _enc_of(plus_ok, greeting)
    else:
        assert_usage_class(plus_wrong, greeting)


def test_feature_switch_explicit_default_beats_auto_false():
    greeting = _option_hi()
    dest = _option_ident()
    with_flag = f"--{_option_ident()}"
    without_flag = f"--{_option_ident()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(without_flag, dest, flag_value=False),
        option(with_flag, dest, flag_value=True, default=True),
    )
    twin = _option_leaf(
        callback,
        option(f"--{_option_ident()}", dest, is_flag=True),
    )

    omitted = _option_run(leaf, [])
    baseline = _option_run(twin, [])
    print(f"omit={omitted.stdout_text!r} baseline={baseline.stdout_text!r}", flush=True)
    assert_success_marker_present(omitted, greeting)
    assert_success_marker_present(baseline, greeting)
    assert _enc_of(omitted, greeting) != _enc_of(baseline, greeting)
    assert _enc_of(omitted, greeting) == _enc_of(_option_run(leaf, [with_flag]), greeting)


def test_feature_switch_last_declared_wins_when_tied():
    greeting = _option_hi()
    dest = _option_ident()
    first_flag = f"--{_option_ident()}"
    second_flag = f"--{_option_ident()}"
    first_val = f"F{_option_ident()}"
    second_val = f"S{_option_ident()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(first_flag, dest, flag_value=first_val, default=first_val),
        option(second_flag, dest, flag_value=second_val, default=second_val),
    )

    omitted = _option_run(leaf, [])
    print(f"omit={omitted.stdout_text!r}", flush=True)
    assert_success_marker_present(omitted, greeting)
    assert marker_occurs(omitted.stdout_text, f"V:{second_val}")
    assert_marker_absent(omitted.stdout_text, f"V:{first_val}")


# ---------------------------------------------------------------------------
# F. Counting options
# ---------------------------------------------------------------------------


def test_counting_option_zero_when_omitted_stacked_shorts_count():
    greeting = _option_hi()
    short = _shorts(1)[0]
    dest = _option_ident()
    long_flag = f"--{_option_ident()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"C:{kwargs[dest]!r}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(f"-{short}", long_flag, dest, count=True))

    omitted = _option_run(leaf, [])
    stacked = _option_run(leaf, [f"-{short}{short}{short}"])
    separate = _option_run(leaf, [f"-{short}", f"-{short}", f"-{short}"])
    twice = _option_run(leaf, [long_flag, long_flag])
    once = _option_run(leaf, [long_flag])
    print(
        f"omit={omitted.stdout_text!r} stacked={stacked.stdout_text!r} "
        f"sep={separate.stdout_text!r} twice={twice.stdout_text!r} "
        f"once={once.stdout_text!r}",
        flush=True,
    )
    for result in (omitted, stacked, separate, twice, once):
        assert_success_marker_present(result, greeting)
    assert f"C:{0!r}" in omitted.stdout_text
    assert f"C:{3!r}" in stacked.stdout_text
    assert f"C:{3!r}" in separate.stdout_text
    assert f"C:{2!r}" in twice.stdout_text
    assert f"C:{1!r}" in once.stdout_text
    omit_enc = omitted.stdout_text
    assert f"C:{0!r}" in omit_enc


# ---------------------------------------------------------------------------
# G. Repeatable, multi-value, optional value, illegal default
# ---------------------------------------------------------------------------


def test_repeatable_option_collects_sequence():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    first = _option_ident()
    second = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _print_seq(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, multiple=True))

    result = _option_run(leaf, [flag, first, flag, second])
    print(f"rep={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert "N:2" in result.stdout_text
    assert f"V:0:{first}" in result.stdout_text
    assert f"V:1:{second}" in result.stdout_text
    joined = f"V:0:{first}{second}"
    assert joined not in result.stdout_text


def test_repeatable_omitted_no_default_is_empty_tuple():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        received = kwargs[dest]
        print(f"TUP:{isinstance(received, tuple)}", flush=True)
        _print_seq(received)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    repeatable = _option_leaf(callback, option(flag, dest, multiple=True))
    optional = _option_leaf(callback, option(flag, dest))

    omitted = _option_run(repeatable, [])
    absent = _option_run(optional, [])
    print(f"omit={omitted.stdout_text!r} absent={absent.stdout_text!r}", flush=True)
    assert_success_marker_present(omitted, greeting)
    assert_success_marker_present(absent, greeting)
    omit_tup = labeled_stdout_field(omitted, "TUP:")
    omit_n = labeled_stdout_field(omitted, "N:")
    omit_items = labeled_stdout_fields(omitted, "V:")
    assert omit_tup == "True"
    assert omit_n == "0"
    assert omit_items == []
    absent_tup = labeled_stdout_field(absent, "TUP:")
    absent_n = labeled_stdout_field(absent, "N:")
    assert (omit_tup, omit_n) != (absent_tup, absent_n)


def test_repeatable_omitted_default_delivered_as_tuple():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    a, b = _option_ident(), _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        received = kwargs[dest]
        print(f"TUP:{isinstance(received, tuple)}", flush=True)
        _print_seq(received)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    as_list = _option_leaf(callback, option(flag, dest, multiple=True, default=[a, b]))
    as_tuple = _option_leaf(callback, option(flag, dest, multiple=True, default=(a, b)))

    from_list = _option_run(as_list, [])
    from_tuple = _option_run(as_tuple, [])
    print(f"list={from_list.stdout_text!r} tuple={from_tuple.stdout_text!r}", flush=True)
    for result in (from_list, from_tuple):
        assert_success_marker_present(result, greeting)
        assert "TUP:True" in result.stdout_text
        assert "N:2" in result.stdout_text
        assert f"V:0:{a}" in result.stdout_text
        assert f"V:1:{b}" in result.stdout_text


def test_one_element_sequence_is_the_way_to_default_one_string():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    one = f"one{_option_ident()}"
    assert len(one) > 1

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        received = kwargs[dest]
        print(f"TUP:{isinstance(received, tuple)}", flush=True)
        _print_seq(received)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, multiple=True, default=(one,)))

    result = _option_run(leaf, [])
    print(f"one={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert "TUP:True" in result.stdout_text
    assert "N:1" in result.stdout_text
    assert f"V:0:{one}" in result.stdout_text
    assert "N:SCALAR" not in result.stdout_text
    assert f"V:1:" not in result.stdout_text


def test_multi_value_fixed_arity_not_consume_rest():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    rest_dest = _option_ident()
    a, b, c, d = _option_ident(), _option_ident(), _option_ident(), _option_ident()
    leftover = _option_ident()

    def once_cb(**kwargs) -> None:
        print(greeting, flush=True)
        pair = kwargs[dest]
        print(f"PAIR:{pair[0]}|{pair[1]}", flush=True)
        print(f"R:{kwargs[rest_dest]}", flush=True)

    once_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        once_cb,
        option(flag, dest, nargs=2),
        argument(rest_dest),
    )

    def twice_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_pairs(kwargs[dest])
        print(f"R:{kwargs[rest_dest]}", flush=True)

    twice_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    twice = _option_leaf(
        twice_cb,
        option(flag, dest, nargs=2, multiple=True),
        argument(rest_dest),
    )
    once = _option_run(leaf, [flag, a, b, leftover])
    two = _option_run(twice, [flag, a, b, flag, c, d, leftover])
    missing = _option_run(leaf, [flag, a])
    print(
        f"once={once.stdout_text!r} two={two.stdout_text!r} "
        f"missing={missing.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(once, greeting)
    assert f"PAIR:{a}|{b}" in once.stdout_text
    assert f"R:{leftover}" in once.stdout_text
    assert_success_marker_present(two, greeting)
    assert "N:2" in two.stdout_text
    assert f"P:0:2:{a}|{b}" in two.stdout_text
    assert f"P:1:2:{c}|{d}" in two.stdout_text
    assert f"R:{leftover}" in two.stdout_text
    assert_usage_class(missing, greeting)


def test_tuple_type_sets_arity_and_converts_positions():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    number = _option_int()
    text = _option_ident()
    expected = number * 3 + 7

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        pair = kwargs[dest]
        _print_arith(pair[0])
        print(f"S:{pair[1]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, type=Tuple([INT, STRING])))

    result = _option_run(leaf, [flag, str(number), text])
    print(f"tuple={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert labeled_stdout_field(result, "T:") == str(expected)
    assert marker_occurs(result.stdout_text, f"S:{text}")


def test_optional_value_flag_alone_token_or_default():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    flag_val = _option_ident()
    default_val = _option_ident()
    token = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(flag, dest, is_flag=False, flag_value=flag_val, default=default_val),
    )

    alone = _option_run(leaf, [flag])
    equals = _option_run(leaf, [f"{flag}={token}"])
    spaced = _option_run(leaf, [flag, token])
    omitted = _option_run(leaf, [])
    print(
        f"alone={alone.stdout_text!r} eq={equals.stdout_text!r} "
        f"sp={spaced.stdout_text!r} omit={omitted.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(alone, greeting)
    assert_success_marker_present(equals, greeting)
    assert_success_marker_present(spaced, greeting)
    assert_success_marker_present(omitted, greeting)
    assert marker_occurs(alone.stdout_text, f"V:{flag_val}")
    assert marker_occurs(equals.stdout_text, f"V:{token}")
    assert marker_occurs(spaced.stdout_text, f"V:{token}")
    assert marker_occurs(omitted.stdout_text, f"V:{default_val}")


def test_bare_string_default_on_repeatable_is_usage_error():
    greeting = _option_hi()
    dest = _option_ident()
    flag = f"--{_option_ident()}"
    bare = _option_ident()
    one = _option_ident()
    assert len(bare) > 1

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _print_seq(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    bare_cli = _option_leaf(callback, option(flag, dest, multiple=True, default=bare))
    int_cli = _option_leaf(callback, option(flag, dest, multiple=True, default=7))
    ok_cli = _option_leaf(callback, option(flag, dest, multiple=True, default=(one,)))
    required = _option_leaf(callback, option(flag, dest, required=True))

    bare_err = _option_run(bare_cli, [])
    int_err = _option_run(int_cli, [])
    ok = _option_run(ok_cli, [])
    missing = _option_run(required, [])
    print(
        f"bare={bare_err.stderr_text!r} int={int_err.stderr_text!r} "
        f"ok={ok.stdout_text!r} missing={missing.stderr_text!r}",
        flush=True,
    )
    assert_usage_names_option(bare_err, greeting, flag)
    assert_usage_names_option(int_err, greeting, flag)
    assert_success_marker_present(ok, greeting)
    assert "N:1" in ok.stdout_text
    assert f"V:0:{one}" in ok.stdout_text
    assert_usage_class(missing, greeting)
    assert_usage_kinds_unlike(bare_err, missing, greeting, flag)
    other = f"--{_option_ident()}"
    other_cli = _option_leaf(callback, option(other, dest, multiple=True, default=bare))
    other_err = _option_run(other_cli, [])
    assert_usage_names_option(other_err, greeting, other)
    assert flag not in other_err.stderr_text


# ---------------------------------------------------------------------------
# H. Environment fill
# ---------------------------------------------------------------------------


def test_named_env_fills_when_flag_omitted():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    value = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, envvar=env_name))

    filled = _option_run(leaf, [], env={env_name: value})
    print(f"filled={filled.stdout_text!r}", flush=True)
    assert_success_marker_present(filled, greeting)
    assert marker_occurs(filled.stdout_text, f"V:{value}")


def test_empty_env_is_unset_next_source_wins():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    defaulted = _option_ident()
    env_val = _option_ident()
    assert env_val != defaulted

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, envvar=env_name, default=defaulted))

    filled = _option_run(leaf, [], env={env_name: env_val})
    empty = _option_run(leaf, [], env={env_name: ""})
    absent = _option_run(leaf, [])
    print(
        f"filled={filled.stdout_text!r} empty={empty.stdout_text!r} "
        f"absent={absent.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(filled, greeting)
    assert_success_marker_present(empty, greeting)
    assert_success_marker_present(absent, greeting)
    assert marker_occurs(filled.stdout_text, f"V:{env_val}")
    assert_marker_absent(filled.stdout_text, f"V:{defaulted}")
    assert marker_occurs(empty.stdout_text, f"V:{defaulted}")
    assert marker_occurs(absent.stdout_text, f"V:{defaulted}")


def test_option_env_list_first_set_wins():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    first = _option_env()
    second = _option_env()
    v1, v2 = _option_ident(), _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, envvar=[first, second]))

    both = _option_run(leaf, [], env={first: v1, second: v2})
    second_only = _option_run(leaf, [], env={first: "", second: v2})
    print(f"both={both.stdout_text!r} second={second_only.stdout_text!r}", flush=True)
    assert_success_marker_present(both, greeting)
    assert_success_marker_present(second_only, greeting)
    assert marker_occurs(both.stdout_text, f"V:{v1}")
    assert_marker_absent(both.stdout_text, f"V:{v2}")
    assert marker_occurs(second_only.stdout_text, f"V:{v2}")


def test_option_env_exact_match_not_whitespace_trimmed():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    defaulted = _option_ident()
    other = _option_ident()
    assert defaulted != other
    assert env_name != env_name.lower()
    padded_name = f" {env_name} "
    assert padded_name != env_name

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, envvar=env_name, default=defaulted))

    wrong_case = _option_run(leaf, [], env={env_name.lower(): other})
    padded = _option_run(leaf, [], env={padded_name: other})
    exact = _option_run(leaf, [], env={env_name: other})
    print(
        f"case={wrong_case.stdout_text!r} pad={padded.stdout_text!r} "
        f"exact={exact.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(wrong_case, greeting)
    assert_success_marker_present(padded, greeting)
    assert_success_marker_present(exact, greeting)
    assert marker_occurs(wrong_case.stdout_text, f"V:{defaulted}")
    assert_marker_absent(wrong_case.stdout_text, f"V:{other}")
    assert marker_occurs(padded.stdout_text, f"V:{defaulted}")
    assert_marker_absent(padded.stdout_text, f"V:{other}")
    assert marker_occurs(exact.stdout_text, f"V:{other}")
    assert_marker_absent(exact.stdout_text, f"V:{defaulted}")

    def padded_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    padded_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    padded_decl = _option_leaf(
        padded_cb, option(flag, dest, envvar=padded_name, default=defaulted)
    )
    padded_exact = _option_run(padded_decl, [], env={padded_name: other})
    print(f"padded_exact={padded_exact.stdout_text!r}", flush=True)
    assert_success_marker_present(padded_exact, greeting)
    assert marker_occurs(padded_exact.stdout_text, f"V:{other}")
    assert_marker_absent(padded_exact.stdout_text, f"V:{defaulted}")

    live_flag = f"--{_option_ident()}"
    live_dest = _option_ident()

    def twin_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)
        print(f"L:{kwargs[live_dest]}", flush=True)

    twin_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    declared_pad_leaf = _option_leaf(
        twin_cb,
        option(flag, dest, envvar=padded_name, default=defaulted),
        option(live_flag, live_dest, envvar=env_name),
    )
    declared_pad = _option_run(declared_pad_leaf, [], env={env_name: other})
    print(f"declared_pad={declared_pad.stdout_text!r}", flush=True)
    assert_declared_env_unmatched(declared_pad, greeting, defaulted, other)


def test_repeatable_and_multivalue_env_splits_on_whitespace():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    a, b = _option_ident(), _option_ident()
    blob = f"{a} {b}"

    def seq_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _print_seq(kwargs[dest])

    seq_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    repeatable = _option_leaf(seq_cb, option(flag, dest, multiple=True, envvar=env_name))

    def whole_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"W:{kwargs[dest]}", flush=True)

    whole_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    single = _option_leaf(whole_cb, option(flag, dest, envvar=env_name))

    def pair_cb(**kwargs) -> None:
        print(greeting, flush=True)
        pair = kwargs[dest]
        print(f"P:{pair[0]}|{pair[1]}", flush=True)

    pair_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    multi = _option_leaf(pair_cb, option(flag, dest, nargs=2, envvar=env_name))

    split = _option_run(repeatable, [], env={env_name: blob})
    whole = _option_run(single, [], env={env_name: blob})
    paired = _option_run(multi, [], env={env_name: blob})
    print(
        f"split={split.stdout_text!r} whole={whole.stdout_text!r} "
        f"pair={paired.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(split, greeting)
    assert "N:2" in split.stdout_text
    assert f"V:0:{a}" in split.stdout_text
    assert f"V:1:{b}" in split.stdout_text
    assert_success_marker_present(whole, greeting)
    assert f"W:{blob}" in whole.stdout_text
    assert_success_marker_present(paired, greeting)
    assert f"P:{a}|{b}" in paired.stdout_text


def test_path_type_env_splits_on_os_pathsep():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    left = f"/tmp/{_option_ident()}"
    right = f"/var/{_option_ident()}"
    blob = os.pathsep.join((left, right))

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _print_seq(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(flag, dest, multiple=True, type=Path(), envvar=env_name),
    )

    result = _option_run(leaf, [], env={env_name: blob})
    print(f"path={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert "N:2" in result.stdout_text
    assert f"V:0:{left}" in result.stdout_text
    assert f"V:1:{right}" in result.stdout_text


def test_file_type_env_splits_on_os_pathsep():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    left, right = _two_empty_file_paths()
    blob = os.pathsep.join((left, right))

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_path_texts(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(flag, dest, multiple=True, type=File(), envvar=env_name),
    )

    result = _option_run(leaf, [], env={env_name: blob})
    print(f"file={result.stdout_text!r} left={left!r} right={right!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert labeled_stdout_field(result, "N:") == "2"
    assert labeled_stdout_field(result, "V:0:") == left
    assert labeled_stdout_field(result, "V:1:") == right


def test_env_delivers_converted_integer():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    default_n = _option_int()
    env_n = default_n + 5 + (uuid.uuid4().int % 9)
    expected = env_n * 3 + 7

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _print_arith(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback, option(flag, dest, envvar=env_name, default=default_n)
    )

    result = _option_run(leaf, [], env={env_name: str(env_n)})
    print(f"envint={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert labeled_stdout_field(result, "T:") == str(expected)


@pytest.mark.parametrize("token", _BOOL_ON)
def test_boolean_env_tokens_activate_and_deactivate(token: str):
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, is_flag=True, envvar=env_name))

    mixed = "TrUe"
    padded = f" {token} "
    omitted = _option_run(leaf, [])
    present = _option_run(leaf, [flag])
    on = _option_run(leaf, [], env={env_name: token})
    mixed_run = _option_run(leaf, [], env={env_name: mixed})
    padded_run = _option_run(leaf, [], env={env_name: padded})
    print(
        f"token={token!r} omit={omitted.stdout_text!r} present={present.stdout_text!r} "
        f"on={on.stdout_text!r} mixed={mixed_run.stdout_text!r} "
        f"pad={padded_run.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(omitted, greeting)
    assert_success_marker_present(present, greeting)
    assert_success_marker_present(on, greeting)
    assert_success_marker_present(mixed_run, greeting)
    assert_success_marker_present(padded_run, greeting)
    assert_activation_unlike_omitted(on, omitted, present, greeting)
    assert_activation_unlike_omitted(mixed_run, omitted, present, greeting)
    assert_activation_unlike_omitted(padded_run, omitted, present, greeting)


@pytest.mark.parametrize("token", _BOOL_OFF)
def test_boolean_env_off_tokens_deactivate(token: str):
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback, option(flag, dest, is_flag=True, default=True, envvar=env_name)
    )

    off = _option_run(leaf, [], env={env_name: token})
    padded = _option_run(leaf, [], env={env_name: f" {token} "})
    omitted = _option_run(leaf, [])
    print(f"off={off.stdout_text!r} pad={padded.stdout_text!r}", flush=True)
    assert_success_marker_present(off, greeting)
    assert_success_marker_present(padded, greeting)
    assert_success_marker_present(omitted, greeting)
    assert _enc_of(off, greeting) != _enc_of(omitted, greeting)
    assert _enc_of(padded, greeting) == _enc_of(off, greeting)


def test_unknown_boolean_env_is_usage_error_not_silent_off():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    unknown = unrelated_dispatch_token(*_BOOL_ON, *_BOOL_OFF)

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, is_flag=True, envvar=env_name))

    bad = _option_run(leaf, [], env={env_name: unknown})
    zero_one = _option_run(leaf, [], env={env_name: "01"})
    ten = _option_run(leaf, [], env={env_name: "10"})
    false_ok = _option_run(leaf, [], env={env_name: "false"})
    print(
        f"bad={bad.stderr_text!r} 01={zero_one.stderr_text!r} "
        f"10={ten.stderr_text!r} false={false_ok.stdout_text!r}",
        flush=True,
    )
    assert_usage_class(bad, greeting)
    assert_usage_class(zero_one, greeting)
    assert_usage_class(ten, greeting)
    assert_success_marker_present(false_ok, greeting)
    assert _enc_of(false_ok, greeting) == _enc_of(_option_run(leaf, []), greeting)


def test_whitespace_only_boolean_env_deactivates_empty_unset():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback, option(flag, dest, is_flag=True, default=True, envvar=env_name)
    )

    empty = _option_run(leaf, [], env={env_name: ""})
    spaces = _option_run(leaf, [], env={env_name: "   "})
    absent = _option_run(leaf, [])
    zero = _option_run(leaf, [], env={env_name: "0"})
    print(
        f"empty={empty.stdout_text!r} spaces={spaces.stdout_text!r} "
        f"absent={absent.stdout_text!r} zero={zero.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(empty, greeting)
    assert_success_marker_present(spaces, greeting)
    assert_success_marker_present(absent, greeting)
    assert_success_marker_present(zero, greeting)
    true_enc = _enc_of(absent, greeting)
    assert _enc_of(empty, greeting) == true_enc
    assert _enc_of(spaces, greeting) != true_enc
    assert _enc_of(zero, greeting) == _enc_of(spaces, greeting)
    assert _enc_of(spaces, greeting) == _enc_of(zero, greeting)


def test_nonboolean_flag_value_env_exact_or_bool_tokens():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    flag_val = _option_ident()
    default_val = _option_ident()
    unknown = unrelated_dispatch_token(flag_val, *_BOOL_ON, *_BOOL_OFF)

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(
            flag,
            dest,
            flag_value=flag_val,
            default=default_val,
            envvar=env_name,
        ),
    )

    exact = _option_run(leaf, [], env={env_name: flag_val})
    true_tok = _option_run(leaf, [], env={env_name: "true"})
    false_tok = _option_run(leaf, [], env={env_name: "false"})
    unknown_run = _option_run(leaf, [], env={env_name: unknown})
    empty = _option_run(leaf, [], env={env_name: ""})
    print(
        f"exact={exact.stdout_text!r} true={true_tok.stdout_text!r} "
        f"false={false_tok.stdout_text!r} unk={unknown_run.stdout_text!r} "
        f"empty={empty.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(exact, greeting)
    assert_success_marker_present(true_tok, greeting)
    assert_success_marker_present(false_tok, greeting)
    assert_success_marker_present(unknown_run, greeting)
    assert_success_marker_present(empty, greeting)
    exact_enc = _enc_of(exact, greeting)
    true_enc = _enc_of(true_tok, greeting)
    false_enc = _enc_of(false_tok, greeting)
    unknown_enc = _enc_of(unknown_run, greeting)
    empty_enc = _enc_of(empty, greeting)
    assert exact_enc == repr(flag_val)
    assert true_enc == repr(flag_val)
    assert false_enc != repr(flag_val)
    assert unknown_enc == repr(default_val)
    assert empty_enc == repr(default_val)


def test_paired_option_uses_only_attached_option_env():
    greeting = _option_hi()
    on_option_ident = _option_ident()
    off_option_ident = _option_ident()
    dest = _option_ident()
    attached = _option_env()
    derived = f"NO_{attached}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_enc(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(f"--{on_option_ident}/--{off_option_ident}", dest, envvar=attached),
    )

    via_derived = _option_run(leaf, [], env={derived: "true"})
    via_attached = _option_run(leaf, [], env={attached: "true"})
    omitted = _option_run(leaf, [])
    print(
        f"derived={via_derived.stdout_text!r} attached={via_attached.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(via_derived, greeting)
    assert_success_marker_present(via_attached, greeting)
    assert_success_marker_present(omitted, greeting)
    assert _enc_of(via_derived, greeting) == _enc_of(omitted, greeting)
    assert _enc_of(via_attached, greeting) != _enc_of(omitted, greeting)


def test_command_line_beats_environment():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    env_val = _option_ident()
    cli_val = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, envvar=env_name))

    result = _option_run(leaf, [flag, cli_val], env={env_name: env_val})
    print(f"cli={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert marker_occurs(result.stdout_text, f"V:{cli_val}")
    assert_marker_absent(result.stdout_text, f"V:{env_val}")


def test_command_line_value_must_never_prompt():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    cli_val = _option_ident()
    typed = _option_ident()
    assert cli_val != typed

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(flag, dest, prompt=True))

    equals = _option_run(leaf, [f"{flag}={cli_val}"], stdin=f"{typed}\n")
    spaced = _option_run(leaf, [flag, cli_val], stdin="")
    print(
        f"equals={equals.stdout_text!r} spaced={spaced.stdout_text!r} "
        f"typed={typed!r}",
        flush=True,
    )
    assert_success_marker_present(equals, greeting)
    assert_success_marker_present(spaced, greeting)
    assert marker_occurs(equals.stdout_text, f"V:{cli_val}")
    assert marker_occurs(spaced.stdout_text, f"V:{cli_val}")
    assert_marker_absent(equals.stdout_text, f"V:{typed}")
    assert_marker_absent(spaced.stdout_text, f"V:{typed}")


# ---------------------------------------------------------------------------
# I. Four-tier fill order and feature-switch explicitness
# ---------------------------------------------------------------------------


def test_fill_order_command_line_env_map_declared():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    cli_val, env_val, map_val, def_val = _option_ident(), _option_ident(), _option_ident(), _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback, option(flag, dest, envvar=env_name, default=def_val)
    )

    cli_vs_env = _option_run(
        leaf, [flag, cli_val], env={env_name: env_val}, default_map={dest: map_val}
    )
    cli_vs_map = _option_run(leaf, [flag, cli_val], default_map={dest: map_val})
    env_vs_map = _option_run(
        leaf, [], env={env_name: env_val}, default_map={dest: map_val}
    )
    map_vs_def = _option_run(leaf, [], default_map={dest: map_val})
    only_def = _option_run(leaf, [])
    print(
        f"cli_env={cli_vs_env.stdout_text!r} cli_map={cli_vs_map.stdout_text!r} "
        f"env_map={env_vs_map.stdout_text!r} map={map_vs_def.stdout_text!r} "
        f"def={only_def.stdout_text!r}",
        flush=True,
    )
    for result in (cli_vs_env, cli_vs_map, env_vs_map, map_vs_def, only_def):
        assert_success_marker_present(result, greeting)
    assert marker_occurs(cli_vs_env.stdout_text, f"V:{cli_val}")
    assert marker_occurs(cli_vs_map.stdout_text, f"V:{cli_val}")
    assert marker_occurs(env_vs_map.stdout_text, f"V:{env_val}")
    assert marker_occurs(map_vs_def.stdout_text, f"V:{map_val}")
    assert marker_occurs(only_def.stdout_text, f"V:{def_val}")

    map_n = _option_int()
    cli_n = map_n + 4
    int_dest = _option_ident()
    int_flag = f"--{_option_ident()}"
    expected = cli_n * 3 + 7
    map_expected = map_n * 3 + 7

    def int_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _print_arith(kwargs[int_dest])

    int_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    int_leaf = _option_leaf(int_cb, option(int_flag, int_dest, default=_option_int()))
    from_map = _option_run(int_leaf, [], default_map={int_dest: map_n})
    from_cli = _option_run(
        int_leaf, [f"{int_flag}={cli_n}"], default_map={int_dest: map_n}
    )
    print(f"imap={from_map.stdout_text!r} icli={from_cli.stdout_text!r}", flush=True)
    assert_success_marker_present(from_map, greeting)
    assert_success_marker_present(from_cli, greeting)
    assert labeled_stdout_field(from_map, "T:") == str(map_expected)
    assert labeled_stdout_field(from_cli, "T:") == str(expected)


def test_feature_switch_more_explicit_source_wins():
    greeting = _option_hi()
    dest = _option_ident()
    left_flag = f"--{_option_ident()}"
    right_flag = f"--{_option_ident()}"
    left_val = f"L{_option_ident()}"
    right_val = f"R{_option_ident()}"
    env_name = _option_env()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(left_flag, dest, flag_value=left_val, envvar=env_name),
        option(right_flag, dest, flag_value=right_val, default=right_val),
    )

    cli_vs_env = _option_run(
        leaf, [right_flag], env={env_name: left_val}
    )
    cli_vs_map = _option_run(
        leaf, [right_flag], default_map={dest: left_val}
    )
    env_vs_map = _option_run(
        leaf, [], env={env_name: left_val}, default_map={dest: right_val}
    )
    map_vs_def = _option_run(leaf, [], default_map={dest: left_val})
    cli_vs_default = _option_run(leaf, [left_flag])
    print(
        f"cli_env={cli_vs_env.stdout_text!r} cli_map={cli_vs_map.stdout_text!r} "
        f"env_map={env_vs_map.stdout_text!r} map={map_vs_def.stdout_text!r} "
        f"cli_def={cli_vs_default.stdout_text!r}",
        flush=True,
    )
    for result in (cli_vs_env, cli_vs_map, env_vs_map, map_vs_def, cli_vs_default):
        assert_success_marker_present(result, greeting)
    assert marker_occurs(cli_vs_env.stdout_text, f"V:{right_val}")
    assert marker_occurs(cli_vs_map.stdout_text, f"V:{right_val}")
    assert marker_occurs(env_vs_map.stdout_text, f"V:{left_val}")
    assert marker_occurs(map_vs_def.stdout_text, f"V:{left_val}")
    assert marker_occurs(cli_vs_default.stdout_text, f"V:{left_val}")


# ---------------------------------------------------------------------------
# J. Parameter callbacks, hidden, deprecated
# ---------------------------------------------------------------------------


def test_parameter_callback_replaces_converted_value():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    default_n = _option_int()
    provided = default_n + 2
    replacement = _option_ident()

    def param_cb(ctx, param, value):
        if value != provided:
            raise BadParameter("unexpected")
        return replacement

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(flag, dest, default=default_n, callback=param_cb),
    )

    result = _option_run(leaf, [f"{flag}={provided}"])
    print(f"replace={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert marker_occurs(result.stdout_text, f"V:{replacement}")
    assert_marker_absent(result.stdout_text, f"V:{provided}")


def test_parameter_callback_may_refuse():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    default_n = _option_int()
    provided = default_n + 3

    def refuse_cb(ctx, param, value):
        raise BadParameter("refused")

    def accept_cb(ctx, param, value):
        return value

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    argv = [f"{flag}={provided}"]
    accepted_leaf = _option_leaf(
        callback,
        option(flag, dest, default=default_n, callback=accept_cb),
    )
    refused_leaf = _option_leaf(
        callback,
        option(flag, dest, default=default_n, callback=refuse_cb),
    )

    accepted = _option_run(accepted_leaf, argv)
    refused = _option_run(refused_leaf, argv)
    print(
        f"accept={accepted.exit_code!r} stdout={accepted.stdout_text!r} "
        f"refuse={refused.exit_code!r} stdout={refused.stdout_text!r} "
        f"stderr={refused.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(accepted, greeting)
    assert marker_occurs(accepted.stdout_text, f"V:{provided}")
    assert_usage_class(refused, greeting)
    assert_parameter_callback_refused(refused, greeting, f"V:{provided}")
    assert_marker_absent(refused.stdout_text, f"V:{provided}")


def test_parameter_callback_runs_for_env_and_map_sources():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    env_name = _option_env()
    env_raw = _option_ident()
    map_raw = _option_ident()
    replaced = _option_ident()

    def param_cb(ctx, param, value):
        if value in {env_raw, map_raw}:
            return replaced
        return value

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(flag, dest, envvar=env_name, callback=param_cb),
    )

    from_env = _option_run(leaf, [], env={env_name: env_raw})
    from_map = _option_run(leaf, [], default_map={dest: map_raw})
    print(f"env={from_env.stdout_text!r} map={from_map.stdout_text!r}", flush=True)
    assert_success_marker_present(from_env, greeting)
    assert_success_marker_present(from_map, greeting)
    assert marker_occurs(from_env.stdout_text, f"V:{replaced}")
    assert_marker_absent(from_env.stdout_text, f"V:{env_raw}")
    assert marker_occurs(from_map.stdout_text, f"V:{replaced}")
    assert_marker_absent(from_map.stdout_text, f"V:{map_raw}")


def test_parameter_callback_runs_for_prompt_source():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    typed = _option_ident()
    other = _option_ident()
    replaced = _option_ident()
    assert len({typed, other, replaced}) == 3

    def param_cb(ctx, param, value):
        if value == typed:
            return replaced
        return value

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(flag, dest, prompt=True, callback=param_cb),
    )

    from_cli = _option_run(leaf, [flag, other])
    from_prompt = _option_run(leaf, [], stdin=f"{typed}\n")
    print(
        f"cli={from_cli.stdout_text!r} prompt={from_prompt.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(from_cli, greeting)
    assert marker_occurs(from_cli.stdout_text, f"V:{other}")
    assert_marker_absent(from_cli.stdout_text, f"V:{replaced}")
    assert_success_marker_present(from_prompt, greeting)
    assert marker_occurs(from_prompt.stdout_text, f"V:{replaced}")
    assert_marker_absent(from_prompt.stdout_text, f"V:{typed}")


def test_eager_flag_finishes_when_required_non_eager_missing():
    greeting = _option_hi()
    req_flag = f"--{_option_ident()}"
    req_dest = _option_ident()
    eager_flag = f"--{_option_ident()}"
    mark = f"EAGER:{uuid.uuid4().hex}:"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(req_flag, req_dest, required=True),
        option(
            eager_flag,
            is_flag=True,
            is_eager=True,
            expose_value=False,
            callback=_eager_finish(mark),
        ),
    )

    missing = _option_run(leaf, [])
    finished = _option_run(leaf, [eager_flag])
    print(
        f"missing={missing.exit_code!r} stderr={missing.stderr_text!r} "
        f"finished={finished.exit_code!r} stdout={finished.stdout_text!r}",
        flush=True,
    )
    assert_omitted_required_names_option(missing, greeting, req_flag)
    assert mark not in missing.stdout_text
    assert_eager_identity(finished, greeting, mark)


def test_missing_parameter_still_runs_its_callback():
    greeting = _option_hi()
    a_flag = f"--{_option_ident()}"
    b_flag = f"--{_option_ident()}"
    a_dest = _option_ident()
    b_dest = _option_ident()
    a_val = _option_ident()
    b_val = _option_ident()
    mark = f"ONLYB:{uuid.uuid4().hex}:"
    derived_prefix = f"D:{uuid.uuid4().hex}:"

    def b_cb(ctx, param, value):
        print(mark, flush=True)
        if value == b_val:
            return value
        return f"{derived_prefix}{ctx.params[a_dest]}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"B:{kwargs[b_dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(a_flag, a_dest),
        option(b_flag, b_dest, callback=b_cb),
    )

    omitted = _option_run(leaf, [a_flag, a_val])
    provided = _option_run(leaf, [a_flag, a_val, b_flag, b_val])
    print(f"omit={omitted.stdout_text!r} given={provided.stdout_text!r}", flush=True)
    assert_success_marker_present(omitted, greeting)
    assert mark in omitted.stdout_text
    assert marker_occurs(omitted.stdout_text, f"B:{derived_prefix}{a_val}")
    assert_success_marker_present(provided, greeting)
    assert marker_occurs(provided.stdout_text, f"B:{b_val}")
    assert_marker_absent(provided.stdout_text, f"B:{derived_prefix}{a_val}")


def test_repeatable_parameter_callback_fires_once_with_all_values():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    first, second = _option_ident(), _option_ident()
    token = uuid.uuid4().hex
    fired = []

    def param_cb(ctx, param, value):
        fired.append(value)
        print(f"CB:{token}:{len(fired)}", flush=True)
        return value

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _print_seq(kwargs[dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(flag, dest, multiple=True, callback=param_cb),
    )

    result = _option_run(leaf, [flag, first, flag, second])
    print(f"once={result.stdout_text!r} fired={fired!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert result.stdout_text.count(f"CB:{token}:") == 1
    assert f"CB:{token}:1" in result.stdout_text
    assert "N:2" in result.stdout_text
    assert f"V:0:{first}" in result.stdout_text
    assert f"V:1:{second}" in result.stdout_text


def test_hidden_from_callback_still_parsed():
    greeting = _option_hi()
    hidden_flag = f"--{_option_ident()}"
    unknown = f"--{unrelated_dispatch_token()}"
    value = _option_ident()

    def callback() -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback, option(hidden_flag, expose_value=False))

    hidden_ok = _option_run(leaf, [hidden_flag, value])
    unknown_run = _option_run(leaf, [unknown])
    print(
        f"hidden={hidden_ok.stdout_text!r} unknown={unknown_run.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(hidden_ok, greeting)
    assert_usage_class(unknown_run, greeting)


def test_deprecated_option_warns_only_when_user_supplied():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    defaulted = _option_ident()
    provided = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    deprecated = _option_leaf(
        callback, option(flag, dest, deprecated=True, default=defaulted)
    )
    baseline = _option_leaf(callback, option(flag, dest, default=defaulted))

    supplied_dep = _option_run(deprecated, [flag, provided])
    supplied_base = _option_run(baseline, [flag, provided])
    omit_dep = _option_run(deprecated, [])
    omit_base = _option_run(baseline, [])
    print(
        f"sup_d={supplied_dep.stderr_text!r} omit_d={omit_dep.stderr_text!r}",
        flush=True,
    )
    assert_deprecation_distinct(supplied_dep, supplied_base, greeting)
    assert marker_occurs(supplied_dep.stdout_text, f"V:{provided}")
    assert_success_marker_present(omit_dep, greeting)
    assert_success_marker_present(omit_base, greeting)
    assert marker_occurs(omit_dep.stdout_text, f"V:{defaulted}")
    assert caller_visible_remainder(omit_dep, greeting) == caller_visible_remainder(
        omit_base, greeting
    )


def test_deprecated_option_cannot_be_required_or_prompted():
    greeting = _option_hi()
    req_flag = f"--{_option_ident()}"
    prompt_flag = f"--{_option_ident()}"
    ok_flag = f"--{_option_ident()}"
    dest = _option_ident()
    value = _option_ident()

    def required_decl():
        def cb(**kwargs) -> None:
            print(greeting, flush=True)

        cb.__name__ = f"{_option_ident()}_{_option_ident()}"
        return _option_leaf(cb, option(req_flag, dest, required=True, deprecated=True))

    def prompt_decl():
        def cb(**kwargs) -> None:
            print(greeting, flush=True)

        cb.__name__ = f"{_option_ident()}_{_option_ident()}"
        return _option_leaf(cb, option(prompt_flag, dest, prompt=True, deprecated=True))

    assert_declaration_refused(required_decl)
    assert_declaration_refused(prompt_decl)

    def ok_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    ok_cb.__name__ = f"{_option_ident()}_{_option_ident()}"
    ok = _option_leaf(ok_cb, option(ok_flag, dest, deprecated=True))
    result = _option_run(ok, [ok_flag, value])
    print(f"ok={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert marker_occurs(result.stdout_text, f"V:{value}")


# ---------------------------------------------------------------------------
# K. Unknown options, ignore-unknown, missing value
# ---------------------------------------------------------------------------


def test_unknown_option_is_usage_error_without_ignore():
    greeting = _option_hi()
    unknown_long = f"--{unrelated_dispatch_token()}"
    unknown_short = f"-{_shorts(1)[0]}"

    def callback() -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(callback)

    long_err = _option_run(leaf, [unknown_long])
    short_err = _option_run(leaf, [unknown_short])
    print(f"long={long_err.stderr_text!r} short={short_err.stderr_text!r}", flush=True)
    assert_usage_class(long_err, greeting)
    assert_usage_class(short_err, greeting)


def test_ignore_unknown_leaves_long_option_intact_as_extra():
    greeting = _option_hi()
    extra_dest = _option_ident()
    unknown = f"--{unrelated_dispatch_token()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _print_seq(kwargs[extra_dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    ignored = _option_leaf(
        callback,
        argument(extra_dest, nargs=-1),
        context_settings={"ignore_unknown_options": True},
    )
    refused = _option_leaf(callback, argument(extra_dest, nargs=-1))

    kept = _option_run(ignored, [unknown])
    refused_run = _option_run(refused, [unknown])
    print(f"kept={kept.stdout_text!r} refused={refused_run.stderr_text!r}", flush=True)
    assert_success_marker_present(kept, greeting)
    assert unknown in kept.stdout_text
    assert_usage_class(refused_run, greeting)


def test_ignore_unknown_may_split_short_stack():
    greeting = _option_hi()
    v = _shorts(1)[0]
    unknown = _shorts(1, v)[0]
    dest = _option_ident()
    extra_dest = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"C:{kwargs[dest]!r}", flush=True)
        _print_seq(kwargs[extra_dest])

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    leaf = _option_leaf(
        callback,
        option(f"-{v}", dest, count=True),
        argument(extra_dest, nargs=-1),
        context_settings={"ignore_unknown_options": True},
    )

    leftover = f"-{unknown}"
    result = _option_run(leaf, [f"-{v}{unknown}"])
    print(f"split={result.stdout_text!r} leftover={leftover!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert f"C:{1!r}" in result.stdout_text
    _require_leftover_extra(result, leftover)


def test_missing_value_for_required_value_option_is_usage_error():
    greeting = _option_hi()
    flag = f"--{_option_ident()}"
    dest = _option_ident()
    opt_flag = f"--{_option_ident()}"
    opt_dest = _option_ident()
    flag_val = _option_ident()
    default_val = _option_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs.get(dest, kwargs.get(opt_dest))}", flush=True)

    callback.__name__ = f"{_option_ident()}_{_option_ident()}"
    needed = _option_leaf(callback, option(flag, dest))
    optional = _option_leaf(
        callback,
        option(
            opt_flag,
            opt_dest,
            is_flag=False,
            flag_value=flag_val,
            default=default_val,
        ),
    )

    missing = _option_run(needed, [flag])
    optional_ok = _option_run(optional, [opt_flag])
    print(f"missing={missing.stderr_text!r} opt={optional_ok.stdout_text!r}", flush=True)
    assert_usage_class(missing, greeting)
    assert_success_marker_present(optional_ok, greeting)
    assert marker_occurs(optional_ok.stdout_text, f"V:{flag_val}")
