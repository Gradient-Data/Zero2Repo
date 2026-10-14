# feature: F04
"""Positional arguments (FP-04).

Assertions stay at the PRD's precision: required / optional / defaulted
positionals on a command or a group, fixed and variadic arity, ``--``
protection, named environment fill without an automatic prefix,
ignore-unknown consuming option-shaped tokens as arguments,
missing-required and extra-token usage errors, and deprecated arguments.
Message wording, ``None``, uppercase metavars, and exception types are
not pinned.
"""

from __future__ import annotations

import uuid

from optlyn import STRING, Path, argument, group, option
from F04_helpers import (
    _arg_hi,
    _arg_ident,
    _arg_int,
    _arg_leaf,
    _arg_run,
    _arg_stdout,
    _enc,
    _emit_bound,
    _env_name,
    _is_sequence_kind,
    _kind,
    _scalar,
    _seq_member,
    assert_omitted_required_names_argument,
)

from _helpers import (
    assert_declaration_refused,
    assert_deprecation_distinct,
    assert_marker_absent,
    assert_success_marker_present,
    assert_usage_class,
    caller_visible_remainder,
    marker_occurs,
    unrelated_dispatch_token,
)

PROG = "app"


# ---------------------------------------------------------------------------
# A. Minimal required, optional / default, two unary, type inference
# ---------------------------------------------------------------------------


def test_minimal_argument_is_required_positional_text():
    greeting = _arg_hi()
    dest = _arg_ident()
    value = _arg_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    leaf = _arg_leaf(callback, argument(dest))

    given = _arg_run(leaf, [value])
    omitted = _arg_run(leaf, [])
    print(f"given={given.stdout_text!r} omitted={omitted.stderr_text!r}", flush=True)
    assert_success_marker_present(given, greeting)
    assert _scalar(given) == value
    assert_usage_class(omitted, greeting)


def test_argument_declared_on_a_group_is_delivered_to_the_group_callback():
    greeting = _arg_hi()
    dest = _arg_ident()
    value = _arg_ident()
    child_name = f"c-{_arg_ident()}"
    assert value != child_name

    def group_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    group_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    cli = group()(argument(dest)(group_cb))

    def child_cb() -> None:
        return None

    child_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    cli.add_command(_arg_leaf(child_cb, name=child_name))

    result = _arg_run(cli, [value, child_name])
    print(f"group_arg={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert _scalar(result) == value


def test_argument_name_is_not_an_option_flag():
    greeting = _arg_hi()
    dest = _arg_ident()
    value = _arg_ident()
    as_option = f"--{dest}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    leaf = _arg_leaf(callback, argument(dest))

    positional = _arg_run(leaf, [value])
    flagged = _arg_run(leaf, [as_option])
    print(
        f"pos={positional.stdout_text!r} flagged={flagged.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(positional, greeting)
    assert _scalar(positional) == value
    assert_usage_class(flagged, greeting)
    assert value not in _arg_stdout(flagged)


def test_optional_or_defaulted_argument_may_be_omitted():
    greeting = _arg_hi()
    dest = _arg_ident()
    provided = _arg_ident()
    defaulted = _arg_ident()
    var_dest = _arg_ident()
    pair_dest = _arg_ident()
    pair_default_dest = _arg_ident()
    assert provided != defaulted

    def optional_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    optional_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    optional = _arg_leaf(optional_cb, argument(dest, required=False))

    def default_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    default_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    with_default = _arg_leaf(default_cb, argument(dest, default=defaulted))

    def var_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[var_dest])

    var_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    variadic = _arg_leaf(var_cb, argument(var_dest, nargs=-1))

    def pair_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print("PAIR_OK", flush=True)

    pair_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    optional_pair = _arg_leaf(pair_cb, argument(pair_dest, nargs=2, required=False))
    default_pair = _arg_leaf(
        pair_cb,
        argument(pair_default_dest, nargs=2, default=(_arg_ident(), _arg_ident())),
    )

    omitted = _arg_run(optional, [])
    given = _arg_run(optional, [provided])
    used_default = _arg_run(with_default, [])
    overridden = _arg_run(with_default, [provided])
    empty_var = _arg_run(variadic, [])
    omit_pair = _arg_run(optional_pair, [])
    omit_default_pair = _arg_run(default_pair, [])
    print(
        f"omit={omitted.stdout_text!r} given={given.stdout_text!r} "
        f"default={used_default.stdout_text!r} over={overridden.stdout_text!r} "
        f"empty_var={empty_var.stdout_text!r} pair={omit_pair.exit_code} "
        f"dpair={omit_default_pair.exit_code}",
        flush=True,
    )
    assert_success_marker_present(omitted, greeting)
    assert_success_marker_present(given, greeting)
    assert_success_marker_present(used_default, greeting)
    assert_success_marker_present(overridden, greeting)
    assert_success_marker_present(empty_var, greeting)
    assert_success_marker_present(omit_pair, greeting)
    assert_success_marker_present(omit_default_pair, greeting)
    assert "PAIR_OK" in omit_pair.stdout_text
    assert "PAIR_OK" in omit_default_pair.stdout_text

    encodings = {
        "absent": _enc(omitted),
        "provided": _enc(given),
        "default": _enc(used_default),
        "empty_seq": _enc(empty_var),
    }
    print(f"encodings={encodings!r}", flush=True)
    assert len(set(encodings.values())) == 4, (
        "omitted-optional / provided / declared-default / empty-variadic "
        f"encodings are not all distinct; encodings={encodings!r}"
    )
    assert _scalar(given) == provided
    assert _scalar(used_default) == defaulted
    assert _scalar(overridden) == provided
    assert _kind(empty_var) == "0"


def test_two_unary_arguments_each_deliver_a_scalar():
    greeting = _arg_hi()
    first = _arg_ident()
    second = _arg_ident()
    a = _arg_ident()
    b = _arg_ident()

    def both_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[first], "A")
        _emit_bound(kwargs[second], "B")

    both_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    required_pair = _arg_leaf(both_cb, argument(first), argument(second))
    required_then_optional = _arg_leaf(
        both_cb, argument(first), argument(second, required=False)
    )

    two = _arg_run(required_pair, [a, b])
    one_required = _arg_run(required_pair, [a])
    one_optional = _arg_run(required_then_optional, [a])
    two_optional = _arg_run(required_then_optional, [a, b])
    print(
        f"two={two.stdout_text!r} one_req={one_required.stderr_text!r} "
        f"one_opt={one_optional.stdout_text!r} two_opt={two_optional.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(two, greeting)
    assert _scalar(two, "A") == a
    assert _scalar(two, "B") == b
    assert_usage_class(one_required, greeting)
    assert_success_marker_present(one_optional, greeting)
    assert _scalar(one_optional, "A") == a
    assert_success_marker_present(two_optional, greeting)
    assert _scalar(two_optional, "A") == a
    assert _scalar(two_optional, "B") == b


def test_type_inferred_from_integer_default():
    greeting = _arg_hi()
    dest = _arg_ident()
    default_n = _arg_int()
    provided = default_n + 3 + (uuid.uuid4().int % 9)
    expected = provided * 3 + 7
    str_dest = _arg_ident()
    str_default = str(_arg_int())
    str_provided = str(_arg_int())

    def int_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    int_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    inferred = _arg_leaf(int_cb, argument(dest, default=default_n))

    def str_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[str_dest])

    str_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    as_text = _arg_leaf(
        str_cb, argument(str_dest, type=STRING, default=str_default)
    )

    as_int = _arg_run(inferred, [str(provided)])
    as_str = _arg_run(as_text, [str_provided])
    print(f"int={as_int.stdout_text!r} str={as_str.stdout_text!r}", flush=True)
    assert_success_marker_present(as_int, greeting)
    assert marker_occurs(as_int.stdout_text, f"T:{expected}")
    assert_success_marker_present(as_str, greeting)
    assert _scalar(as_str) == str_provided
    assert_marker_absent(as_str.stdout_text, f"T:{int(str_provided) * 3 + 7}")


# ---------------------------------------------------------------------------
# B. Fixed arity, variadic, at most one consume-rest
# ---------------------------------------------------------------------------


def test_fixed_arity_delivers_sequence_not_joined_string():
    greeting = _arg_hi()
    dest = _arg_ident()
    unary_dest = _arg_ident()
    left = _arg_ident()
    right = _arg_ident()
    unary_val = _arg_ident()

    def pair_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    pair_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    pair = _arg_leaf(pair_cb, argument(dest, nargs=2))

    def unary_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[unary_dest])

    unary_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    unary = _arg_leaf(unary_cb, argument(unary_dest))

    two = _arg_run(pair, [left, right])
    one = _arg_run(pair, [left])
    zero = _arg_run(pair, [])
    unary_run = _arg_run(unary, [unary_val])
    print(
        f"two={two.stdout_text!r} one={one.stderr_text!r} "
        f"zero={zero.stderr_text!r} unary={unary_run.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(two, greeting)
    assert _kind(two) == "2"
    assert _seq_member(two, 0) == left
    assert _seq_member(two, 1) == right
    assert f"{left}{right}" not in "".join(
        line for line in _arg_stdout(two).splitlines() if line.startswith("V:")
    )
    assert_usage_class(one, greeting)
    assert_usage_class(zero, greeting)
    assert_success_marker_present(unary_run, greeting)
    assert _scalar(unary_run) == unary_val
    assert _kind(unary_run) != "1"
    assert _kind(unary_run) != str(len(unary_val))


def test_unary_then_variadic_delivers_source_and_rest():
    greeting = _arg_hi()
    src_dest = _arg_ident()
    dst_dest = _arg_ident()
    src = _arg_ident()
    a = _arg_ident()
    b = _arg_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[src_dest], "S")
        _emit_bound(kwargs[dst_dest], "D")

    callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    leaf = _arg_leaf(callback, argument(src_dest), argument(dst_dest, nargs=-1))

    three = _arg_run(leaf, [src, a, b])
    only_src = _arg_run(leaf, [src])
    print(f"three={three.stdout_text!r} only={only_src.stdout_text!r}", flush=True)
    assert_success_marker_present(three, greeting)
    assert _scalar(three, "S") == src
    assert _kind(three, "D") == "2"
    assert _seq_member(three, 0, "D") == a
    assert _seq_member(three, 1, "D") == b
    assert_success_marker_present(only_src, greeting)
    assert _scalar(only_src, "S") == src
    assert _kind(only_src, "D") == "0"


def test_omitted_variadic_empty_unless_required():
    greeting = _arg_hi()
    dest = _arg_ident()
    token = _arg_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    optional = _arg_leaf(callback, argument(dest, nargs=-1))
    required = _arg_leaf(callback, argument(dest, nargs=-1, required=True))

    omit_opt = _arg_run(optional, [])
    omit_req = _arg_run(required, [])
    give_req = _arg_run(required, [token])
    print(
        f"omit_opt={omit_opt.stdout_text!r} omit_req={omit_req.stderr_text!r} "
        f"give={give_req.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(omit_opt, greeting)
    assert _kind(omit_opt) == "0"
    assert_usage_class(omit_req, greeting)
    assert_success_marker_present(give_req, greeting)
    kind = _kind(give_req)
    assert kind != "0", f"required variadic delivered an empty sequence; {kind!r}"
    assert _is_sequence_kind(kind)
    assert _seq_member(give_req, 0) == token


def test_two_variadics_are_not_independent_consume_rest():
    greeting = _arg_hi()
    dest_a = _arg_ident()
    dest_b = _arg_ident()
    src_dest = _arg_ident()
    rest_dest = _arg_ident()
    src = _arg_ident()
    a = _arg_ident()
    b = _arg_ident()

    def single_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[src_dest], "S")
        _emit_bound(kwargs[rest_dest], "R")

    single_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    baseline = _arg_leaf(
        single_cb, argument(src_dest), argument(rest_dest, nargs=-1)
    )
    baseline_run = _arg_run(baseline, [src, a, b])
    print(f"baseline={baseline_run.stdout_text!r}", flush=True)
    assert_success_marker_present(baseline_run, greeting)
    assert _scalar(baseline_run, "S") == src
    assert _kind(baseline_run, "R") == "2"

    def dual_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest_a], "A")
        _emit_bound(kwargs[dest_b], "B")

    dual_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    declared = None
    declaration_exc = None
    try:
        declared = _arg_leaf(
            dual_cb,
            argument(dest_a, nargs=-1),
            argument(dest_b, nargs=-1),
        )
    except Exception as exc:
        declaration_exc = exc
        print(f"dual declaration refused: {type(exc).__name__}", flush=True)

    if declaration_exc is not None:
        assert declared is None
    else:
        result = _arg_run(declared, [src, a, b])
        print(
            f"dual_code={result.exit_code} dual={result.stdout_text!r} "
            f"err={result.stderr_text!r}",
            flush=True,
        )
        assert result.exit_code != 0, (
            "two-variadic declaration was accepted and invoked as success; "
            "variadic arity may be used at most once on a command; "
            f"exit={result.exit_code} stdout={result.stdout_text!r}"
        )
        assert greeting not in _arg_stdout(result), (
            "dual-variadic non-success still ran the callback; "
            f"stdout={result.stdout_text!r}"
        )


# ---------------------------------------------------------------------------
# C. Double-dash protects option-shaped tokens
# ---------------------------------------------------------------------------


def test_double_dash_protects_option_shaped_tokens():
    greeting = _arg_hi()
    dest = _arg_ident()
    src_dest = _arg_ident()
    rest_dest = _arg_ident()
    flag_dest = _arg_ident()
    arg_dest = _arg_ident()
    short_shaped = f"-{_arg_ident()}.txt"
    long_shaped = f"--{_arg_ident()}"
    plain = f"{_arg_ident()}.dat"
    flag = f"--{_arg_ident()}"
    src = _arg_ident()
    flag_on = _arg_ident()

    def unary_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    unary_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    unary = _arg_leaf(unary_cb, argument(dest))

    def rest_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[src_dest], "S")
        _emit_bound(kwargs[rest_dest], "D")

    rest_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    copyish = _arg_leaf(
        rest_cb, argument(src_dest), argument(rest_dest, nargs=-1)
    )

    def files_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[rest_dest])

    files_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    files_only = _arg_leaf(files_cb, argument(rest_dest, nargs=-1))

    def flag_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"F:{kwargs[flag_dest]!r}", flush=True)
        _emit_bound(kwargs[arg_dest], "P")

    flag_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    with_flag = _arg_leaf(
        flag_cb, option(flag, flag_dest, is_flag=True), argument(arg_dest)
    )

    short_ok = _arg_run(unary, ["--", short_shaped])
    long_ok = _arg_run(unary, ["--", long_shaped])
    two_files = _arg_run(files_only, ["--", short_shaped, plain])
    mid = _arg_run(copyish, [src, "--", short_shaped])
    after_sep = _arg_run(with_flag, ["--", flag])
    before_sep = _arg_run(with_flag, [flag, flag_on])
    print(
        f"short={short_ok.stdout_text!r} long={long_ok.stdout_text!r} "
        f"two={two_files.stdout_text!r} mid={mid.stdout_text!r} "
        f"after={after_sep.stdout_text!r} before={before_sep.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(short_ok, greeting)
    assert _scalar(short_ok) == short_shaped
    assert "--" not in _scalar(short_ok)
    assert_success_marker_present(long_ok, greeting)
    assert _scalar(long_ok) == long_shaped
    assert_success_marker_present(two_files, greeting)
    assert _kind(two_files) == "2"
    assert _seq_member(two_files, 0) == short_shaped
    assert _seq_member(two_files, 1) == plain
    assert "--" not in (_seq_member(two_files, 0), _seq_member(two_files, 1))
    assert_success_marker_present(mid, greeting)
    assert _scalar(mid, "S") == src
    assert _kind(mid, "D") == "1"
    assert _seq_member(mid, 0, "D") == short_shaped
    assert "--" != _seq_member(mid, 0, "D")
    assert_success_marker_present(after_sep, greeting)
    assert _scalar(after_sep, "P") == flag
    assert marker_occurs(after_sep.stdout_text, f"F:{False!r}")
    assert_success_marker_present(before_sep, greeting)
    assert marker_occurs(before_sep.stdout_text, f"F:{True!r}")
    assert _scalar(before_sep, "P") == flag_on


def test_option_shaped_token_without_separator_is_unknown():
    greeting = _arg_hi()
    dest = _arg_ident()
    short_shaped = f"-{_arg_ident()}.txt"
    long_shaped = f"--{_arg_ident()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    leaf = _arg_leaf(callback, argument(dest))
    allowed = _arg_leaf(
        callback,
        argument(dest),
        context_settings={"allow_extra_args": True},
    )

    short_err = _arg_run(leaf, [short_shaped])
    long_err = _arg_run(leaf, [long_shaped])
    extra_short = _arg_run(allowed, [short_shaped])
    extra_long = _arg_run(allowed, [long_shaped])
    protected = _arg_run(leaf, ["--", short_shaped])
    print(
        f"short={short_err.stderr_text!r} long={long_err.stderr_text!r} "
        f"extra_s={extra_short.stderr_text!r} extra_l={extra_long.stderr_text!r} "
        f"prot={protected.stdout_text!r}",
        flush=True,
    )
    assert_usage_class(short_err, greeting)
    assert_usage_class(long_err, greeting)
    assert_usage_class(extra_short, greeting)
    assert_usage_class(extra_long, greeting)
    assert_success_marker_present(protected, greeting)
    assert _scalar(protected) == short_shaped


# ---------------------------------------------------------------------------
# D. Named environment, no automatic prefix, non-unary split
# ---------------------------------------------------------------------------


def test_named_env_fills_when_position_omitted():
    greeting = _arg_hi()
    dest = _arg_ident()
    env_name = _env_name()
    value = _arg_ident()
    req_dest = _arg_ident()
    req_env = _env_name()
    req_value = _arg_ident()

    def opt_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    opt_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    optional = _arg_leaf(
        opt_cb, argument(dest, required=False, envvar=env_name)
    )

    def req_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[req_dest])

    req_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    required = _arg_leaf(req_cb, argument(req_dest, envvar=req_env))

    filled = _arg_run(optional, [], env={env_name: value})
    required_filled = _arg_run(required, [], env={req_env: req_value})
    print(
        f"opt={filled.stdout_text!r} req={required_filled.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(filled, greeting)
    assert _scalar(filled) == value
    assert_success_marker_present(required_filled, greeting)
    assert _scalar(required_filled) == req_value


def test_empty_or_absent_env_does_not_supply():
    greeting = _arg_hi()
    dest = _arg_ident()
    env_name = _env_name()
    defaulted = _arg_ident()
    provided = _arg_ident()
    req_dest = _arg_ident()
    req_env = _env_name()
    opt_dest = _arg_ident()
    opt_env = _env_name()

    def default_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    default_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    with_default = _arg_leaf(
        default_cb, argument(dest, envvar=env_name, default=defaulted)
    )

    def req_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[req_dest])

    req_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    required = _arg_leaf(req_cb, argument(req_dest, envvar=req_env))

    def opt_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[opt_dest])

    opt_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    optional = _arg_leaf(
        opt_cb, argument(opt_dest, required=False, envvar=opt_env)
    )

    empty_default = _arg_run(with_default, [], env={env_name: ""})
    absent_default = _arg_run(with_default, [])
    empty_req = _arg_run(required, [], env={req_env: ""})
    absent_req = _arg_run(required, [])
    empty_opt = _arg_run(optional, [], env={opt_env: ""})
    absent_opt = _arg_run(optional, [])
    provided_opt = _arg_run(optional, [], env={opt_env: provided})
    print(
        f"empty_def={empty_default.stdout_text!r} "
        f"empty_req={empty_req.stderr_text!r} "
        f"empty_opt={empty_opt.stdout_text!r} "
        f"prov_opt={provided_opt.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(empty_default, greeting)
    assert_success_marker_present(absent_default, greeting)
    assert _scalar(empty_default) == defaulted
    assert _scalar(absent_default) == defaulted
    assert_usage_class(empty_req, greeting)
    assert_usage_class(absent_req, greeting)
    assert_success_marker_present(empty_opt, greeting)
    assert_success_marker_present(absent_opt, greeting)
    assert_success_marker_present(provided_opt, greeting)
    assert _enc(empty_opt) != _enc(provided_opt)
    assert _enc(absent_opt) != _enc(provided_opt)
    assert _scalar(provided_opt) == provided


def test_env_name_list_first_set_wins():
    greeting = _arg_hi()
    dest = _arg_ident()
    first = _env_name()
    second = _env_name()
    first_val = _arg_ident()
    second_val = _arg_ident()
    assert first_val != second_val

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    leaf = _arg_leaf(
        callback,
        argument(dest, required=False, envvar=[first, second]),
    )

    both = _arg_run(leaf, [], env={first: first_val, second: second_val})
    second_only = _arg_run(leaf, [], env={first: "", second: second_val})
    print(f"both={both.stdout_text!r} second={second_only.stdout_text!r}", flush=True)
    assert_success_marker_present(both, greeting)
    assert _scalar(both) == first_val
    assert_success_marker_present(second_only, greeting)
    assert _scalar(second_only) == second_val


def test_auto_prefix_does_not_fill_argument():
    greeting = _arg_hi()
    dest = _arg_ident()
    cmd_name = _arg_ident()
    prefix = _arg_ident().upper()
    named_env = _env_name()
    prefix_val = _arg_ident()
    named_val = _arg_ident()
    other_val = _arg_ident()
    ident_val = _arg_ident()
    defaulted = _arg_ident()
    key_plain = f"{prefix}_{dest.upper()}"
    key_cmd = f"{prefix}_{cmd_name.upper()}_{dest.upper()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    unnamed = _arg_leaf(
        callback,
        argument(dest, default=defaulted),
        name=cmd_name,
    )
    named = _arg_leaf(
        callback,
        argument(dest, envvar=named_env, default=defaulted),
        name=cmd_name,
    )

    prefix_only = _arg_run(
        unnamed,
        [],
        env={key_plain: prefix_val, key_cmd: prefix_val},
        auto_envvar_prefix=prefix,
    )
    named_ok = _arg_run(
        named,
        [],
        env={named_env: named_val},
        auto_envvar_prefix=prefix,
    )
    exhausted = _arg_run(
        named,
        [],
        env={named_env: "", key_plain: other_val, key_cmd: other_val},
        auto_envvar_prefix=prefix,
    )
    ident = _arg_run(
        unnamed,
        [],
        env={dest: ident_val, dest.upper(): ident_val},
        auto_envvar_prefix=prefix,
    )
    print(
        f"prefix={prefix_only.stdout_text!r} named={named_ok.stdout_text!r} "
        f"exh={exhausted.stdout_text!r} ident={ident.stdout_text!r} "
        f"keys={key_plain!r},{key_cmd!r}",
        flush=True,
    )
    assert_success_marker_present(prefix_only, greeting)
    assert _scalar(prefix_only) == defaulted
    assert prefix_val not in _arg_stdout(prefix_only)
    assert_success_marker_present(named_ok, greeting)
    assert _scalar(named_ok) == named_val
    assert_success_marker_present(exhausted, greeting)
    assert other_val not in _arg_stdout(exhausted)
    assert _scalar(exhausted) == defaulted
    assert_success_marker_present(ident, greeting)
    assert ident_val not in _arg_stdout(ident)
    assert _scalar(ident) == defaulted
    assert _enc(named_ok) != _enc(prefix_only)
    assert _enc(named_ok) != _enc(exhausted)


def test_non_unary_env_splits_like_multivalue_option():
    greeting = _arg_hi()
    pair_dest = _arg_ident()
    unary_dest = _arg_ident()
    var_dest = _arg_ident()
    path_dest = _arg_ident()
    env_pair = _env_name()
    env_unary = _env_name()
    env_var = _env_name()
    env_path = _env_name()
    left = _arg_ident()
    right = _arg_ident()
    blob = f"{left} {right}"
    path_left = f"/tmp/{_arg_ident()}"
    path_right = f"/var/{_arg_ident()}"
    path_blob = f"{path_left}:{path_right}"

    def pair_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[pair_dest])

    pair_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    pair = _arg_leaf(
        pair_cb, argument(pair_dest, nargs=2, required=False, envvar=env_pair)
    )

    def unary_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[unary_dest])

    unary_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    unary = _arg_leaf(
        unary_cb, argument(unary_dest, required=False, envvar=env_unary)
    )

    def var_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[var_dest])

    var_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    variadic = _arg_leaf(var_cb, argument(var_dest, nargs=-1, envvar=env_var))

    def path_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[path_dest])

    path_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    paths = _arg_leaf(
        path_cb,
        argument(path_dest, nargs=-1, type=Path(), envvar=env_path),
    )

    paired = _arg_run(pair, [], env={env_pair: blob})
    whole = _arg_run(unary, [], env={env_unary: blob})
    split_var = _arg_run(variadic, [], env={env_var: blob})
    empty_var = _arg_run(variadic, [], env={env_var: ""})
    path_run = _arg_run(paths, [], env={env_path: path_blob})
    print(
        f"pair={paired.stdout_text!r} whole={whole.stdout_text!r} "
        f"var={split_var.stdout_text!r} empty={empty_var.stdout_text!r} "
        f"path={path_run.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(paired, greeting)
    assert _kind(paired) == "2"
    assert _seq_member(paired, 0) == left
    assert _seq_member(paired, 1) == right
    assert_success_marker_present(whole, greeting)
    assert _scalar(whole) == blob
    assert_success_marker_present(split_var, greeting)
    assert _kind(split_var) == "2"
    assert _seq_member(split_var, 0) == left
    assert _seq_member(split_var, 1) == right
    assert_success_marker_present(empty_var, greeting)
    assert _kind(empty_var) == "0"
    assert_success_marker_present(path_run, greeting)
    assert _kind(path_run) == "2"
    assert _seq_member(path_run, 0) == path_left
    assert _seq_member(path_run, 1) == path_right


def test_command_line_beats_argument_environment():
    greeting = _arg_hi()
    dest = _arg_ident()
    env_name = _env_name()
    env_val = _arg_ident()
    cli_val = _arg_ident()
    default_n = _arg_int()
    env_n = default_n + 5 + (uuid.uuid4().int % 9)
    expected = env_n * 3 + 7
    int_dest = _arg_ident()
    int_env = _env_name()
    assert env_val != cli_val

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    leaf = _arg_leaf(callback, argument(dest, envvar=env_name))

    def int_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[int_dest])

    int_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    as_int = _arg_leaf(
        int_cb, argument(int_dest, envvar=int_env, default=default_n)
    )

    beaten = _arg_run(leaf, [cli_val], env={env_name: env_val})
    env_int = _arg_run(as_int, [], env={int_env: str(env_n)})
    print(f"beaten={beaten.stdout_text!r} envint={env_int.stdout_text!r}", flush=True)
    assert_success_marker_present(beaten, greeting)
    assert _scalar(beaten) == cli_val
    assert env_val not in _arg_stdout(beaten)
    assert_success_marker_present(env_int, greeting)
    assert marker_occurs(env_int.stdout_text, f"T:{expected}")


# ---------------------------------------------------------------------------
# E. Ignore-unknown consumes option-shaped tokens as declared arguments
# ---------------------------------------------------------------------------


def test_ignore_unknown_consumes_option_shaped_as_argument():
    greeting = _arg_hi()
    dest = _arg_ident()
    short_shaped = f"-{_arg_ident()}.txt"
    long_shaped = f"--{unrelated_dispatch_token()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    ignored = _arg_leaf(
        callback,
        argument(dest),
        context_settings={"ignore_unknown_options": True},
    )
    refused = _arg_leaf(callback, argument(dest))

    short_ok = _arg_run(ignored, [short_shaped])
    long_ok = _arg_run(ignored, [long_shaped])
    short_refused = _arg_run(refused, [short_shaped])
    long_refused = _arg_run(refused, [long_shaped])
    print(
        f"short={short_ok.stdout_text!r} long={long_ok.stdout_text!r} "
        f"sref={short_refused.stderr_text!r} lref={long_refused.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(short_ok, greeting)
    assert _scalar(short_ok) == short_shaped
    assert_success_marker_present(long_ok, greeting)
    assert _scalar(long_ok) == long_shaped
    assert_usage_class(short_refused, greeting)
    assert_usage_class(long_refused, greeting)


def test_ignore_unknown_leftover_option_shaped_beyond_arity_is_usage_error():
    greeting = _arg_hi()
    dest = _arg_ident()
    first = f"-{_arg_ident()}.txt"
    second = f"--{unrelated_dispatch_token()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    ignored = _arg_leaf(
        callback,
        argument(dest),
        context_settings={"ignore_unknown_options": True},
    )

    baseline = _arg_run(ignored, [first])
    leftover = _arg_run(ignored, [first, second])
    print(
        f"base={baseline.stdout_text!r} leftover={leftover.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(baseline, greeting)
    assert _scalar(baseline) == first
    assert_usage_class(leftover, greeting)


# ---------------------------------------------------------------------------
# F. Missing required and extra tokens
# ---------------------------------------------------------------------------


def test_missing_required_argument_is_usage_error_identifying_argument():
    greeting = _arg_hi()
    invoked = _arg_ident()
    decl_a = _arg_ident()
    decl_b = _arg_ident()
    value = _arg_ident()
    assert len({invoked, decl_a, decl_b, greeting, PROG}) == 5

    def make(decl: str):
        def callback(**kwargs) -> None:
            print(greeting, flush=True)
            _emit_bound(kwargs[decl])

        callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
        return _arg_leaf(callback, argument(decl), name=invoked)

    cmd_a = make(decl_a)
    cmd_b = make(decl_b)
    err_a = _arg_run(cmd_a, [])
    err_b = _arg_run(cmd_b, [])
    ok = _arg_run(cmd_a, [value])
    print(
        f"decl_a={decl_a!r} decl_b={decl_b!r} "
        f"a={err_a.stderr_text!r} b={err_b.stderr_text!r} ok={ok.stdout_text!r}",
        flush=True,
    )
    assert_usage_class(err_a, greeting)
    assert_usage_class(err_b, greeting)
    assert_omitted_required_names_argument(err_a, greeting, decl_a, decl_b)
    assert_omitted_required_names_argument(err_b, greeting, decl_b, decl_a)
    assert_success_marker_present(ok, greeting)
    assert _scalar(ok) == value


def test_extra_tokens_beyond_arity_are_usage_error_unless_allowed_or_variadic():
    greeting = _arg_hi()
    dest = _arg_ident()
    pair_dest = _arg_ident()
    src_dest = _arg_ident()
    rest_dest = _arg_ident()
    first = _arg_ident()
    second = _arg_ident()
    third = _arg_ident()
    assert first != second and second not in first

    def unary_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    unary_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    unary = _arg_leaf(unary_cb, argument(dest))
    allowed = _arg_leaf(
        unary_cb,
        argument(dest),
        context_settings={"allow_extra_args": True},
    )

    def pair_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[pair_dest])

    pair_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    pair = _arg_leaf(pair_cb, argument(pair_dest, nargs=2))

    def rest_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[src_dest], "S")
        _emit_bound(kwargs[rest_dest], "D")

    rest_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    with_var = _arg_leaf(
        rest_cb, argument(src_dest), argument(rest_dest, nargs=-1)
    )
    without_var = _arg_leaf(rest_cb, argument(src_dest))

    unary_extra = _arg_run(unary, [first, second])
    pair_extra = _arg_run(pair, [first, second, third])
    allowed_run = _arg_run(allowed, [first, second])
    var_ok = _arg_run(with_var, [first, second, third])
    no_var = _arg_run(without_var, [first, second, third])
    print(
        f"u={unary_extra.stderr_text!r} p={pair_extra.stderr_text!r} "
        f"allow={allowed_run.stdout_text!r} var={var_ok.stdout_text!r} "
        f"novar={no_var.stderr_text!r}",
        flush=True,
    )
    assert_usage_class(unary_extra, greeting)
    assert_usage_class(pair_extra, greeting)
    assert_success_marker_present(allowed_run, greeting)
    assert _scalar(allowed_run) == first
    assert second not in _scalar(allowed_run)
    assert_success_marker_present(var_ok, greeting)
    assert _scalar(var_ok, "S") == first
    assert _kind(var_ok, "D") == "2"
    assert_usage_class(no_var, greeting)


# ---------------------------------------------------------------------------
# G. Deprecated argument still parses and cannot be required
# ---------------------------------------------------------------------------


def test_deprecated_argument_warns_only_when_user_supplied():
    greeting = _arg_hi()
    dest = _arg_ident()
    defaulted = _arg_ident()
    provided = _arg_ident()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    callback.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    deprecated = _arg_leaf(
        callback, argument(dest, deprecated=True, default=defaulted)
    )
    baseline = _arg_leaf(callback, argument(dest, default=defaulted))

    supplied_dep = _arg_run(deprecated, [provided])
    supplied_base = _arg_run(baseline, [provided])
    omit_dep = _arg_run(deprecated, [])
    omit_base = _arg_run(baseline, [])
    print(
        f"sup_d={supplied_dep.stderr_text!r} omit_d={omit_dep.stderr_text!r}",
        flush=True,
    )
    assert_deprecation_distinct(supplied_dep, supplied_base, greeting)
    assert _scalar(supplied_dep) == provided
    assert_success_marker_present(omit_dep, greeting)
    assert_success_marker_present(omit_base, greeting)
    assert _scalar(omit_dep) == defaulted
    assert caller_visible_remainder(omit_dep, greeting) == caller_visible_remainder(
        omit_base, greeting
    )


def test_deprecated_argument_cannot_be_required():
    greeting = _arg_hi()
    dest = _arg_ident()
    value = _arg_ident()
    defaulted = _arg_ident()

    def required_decl():
        def cb(**kwargs) -> None:
            print(greeting, flush=True)

        cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
        return _arg_leaf(cb, argument(dest, required=True, deprecated=True))

    def minimal_decl():
        def cb(**kwargs) -> None:
            print(greeting, flush=True)

        cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
        return _arg_leaf(cb, argument(dest, deprecated=True))

    assert_declaration_refused(required_decl)
    assert_declaration_refused(minimal_decl)

    def ok_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_bound(kwargs[dest])

    ok_cb.__name__ = f"{_arg_ident()}_{_arg_ident()}"
    optional = _arg_leaf(ok_cb, argument(dest, required=False, deprecated=True))
    with_default = _arg_leaf(
        ok_cb, argument(dest, default=defaulted, deprecated=True)
    )
    supplied = _arg_run(optional, [value])
    default_ok = _arg_run(with_default, [value])
    print(
        f"opt={supplied.stdout_text!r} def={default_ok.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(supplied, greeting)
    assert _scalar(supplied) == value
    assert_success_marker_present(default_ok, greeting)
    assert _scalar(default_ok) == value
