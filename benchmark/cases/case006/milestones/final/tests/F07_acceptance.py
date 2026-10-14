# feature: F07
"""Invocation context, defaults, environment prefix, and value sources (FP-07).

Assertions stay at the PRD's precision: parent-linked context and author
objects, automatic option environment-prefix construction, nested default
maps, distinguishable value sources, resource cleanup, token
normalization, invoke versus forward, thread-local current context, and
invocation color force on/off/autodetect. Source-enum spellings, exception
types, context attribute names, CSI opcodes, and usage-sentence wording
are not pinned.
"""

from __future__ import annotations

import tempfile
import threading
import uuid
from pathlib import Path as FSPath

from optlyn import (
    INT,
    Choice,
    Path,
    argument,
    command,
    echo,
    get_current_context,
    group,
    make_pass_decorator,
    option,
    pass_context,
    pass_obj,
    style,
)

from F05_helpers import _emit_arith

from _harness import invoke, run_python
from _helpers import (
    assert_ansi_escape_absent,
    assert_ansi_escape_present,
    assert_labeled_fields_unlike,
    assert_marker_absent,
    assert_success_marker_present,
    assert_usage_class,
    automatic_env_name,
    labeled_stdout_field,
    marker_occurs,
    require_usage_names_option,
    run_python_on_tty,
    styled_stdout_remainder,
    unrelated_dispatch_token,
)

PROG = "app"


def _word() -> str:
    return "k" + uuid.uuid4().hex[:8]


def _greeting() -> str:
    return f"GREET:{uuid.uuid4().hex}:"


def _runtime_int() -> int:
    return 14 + uuid.uuid4().int % 80


def _flag() -> str:
    return f"F{uuid.uuid4().hex}:"


def _dispatch(cli, args, **kwargs):
    kwargs.setdefault("prog_name", PROG)
    return invoke(cli, args, **kwargs)


def _cmd(callback, *param_decs, inject=None, **command_kwargs):
    decorated = callback
    if inject is not None:
        decorated = inject(decorated)
    for deco in reversed(param_decs):
        decorated = deco(decorated)
    return command(**command_kwargs)(decorated)


def _grp(callback, *param_decs, inject=None, **group_kwargs):
    decorated = callback
    if inject is not None:
        decorated = inject(decorated)
    for deco in reversed(param_decs):
        decorated = deco(decorated)
    return group(**group_kwargs)(decorated)


def _blank_group(**group_kwargs):
    def root() -> None:
        return None

    return _grp(root, **group_kwargs)


def _stdout(result) -> str:
    text = result.stdout_text
    if text is None:
        raise RuntimeError("stdout is None; cannot observe")
    return text


def _emit_seq(value: object) -> None:
    items = list(value)  # type: ignore[arg-type]
    print(f"N:{len(items)}", flush=True)
    for i, item in enumerate(items):
        print(f"V:{i}:{item}", flush=True)


def _identity(token: str) -> str:
    return token


def _lower(token: str) -> str:
    return token.lower()


# ---------------------------------------------------------------------------
# A. Parent chain, author object, three injections
# ---------------------------------------------------------------------------


def test_child_reads_parent_author_object_flag():
    outer_hi, child_hi = _greeting(), _greeting()
    child_name = _word()
    flag_a, flag_b = _flag(), _flag()

    def make(flag: str):
        def outer(ctx) -> None:
            print(outer_hi, flush=True)
            ctx.obj = flag

        def child(obj) -> None:
            print(child_hi, flush=True)
            print(f"FLAG:{obj}", flush=True)

        root = _grp(outer, inject=pass_context)
        root.add_command(_cmd(child, inject=pass_obj, name=child_name))
        return root

    first = _dispatch(make(flag_a), [child_name])
    second = _dispatch(make(flag_b), [child_name])
    print(f"first={first.stdout_text!r} second={second.stdout_text!r}", flush=True)
    assert_success_marker_present(first, outer_hi)
    assert_success_marker_present(first, child_hi)
    assert labeled_stdout_field(first, "FLAG:") == flag_a
    assert_success_marker_present(second, outer_hi)
    assert_success_marker_present(second, child_hi)
    assert labeled_stdout_field(second, "FLAG:") == flag_b
    text = _stdout(first)
    assert text.find(outer_hi) < text.find(child_hi)


def test_child_replaced_author_object_is_what_descendant_sees():
    outer_hi, mid_hi, leaf_hi = _greeting(), _greeting(), _greeting()
    mid_name, leaf_name = _word(), _word()
    outer_flag, mid_flag = _flag(), _flag()

    def tree(*, replace: bool):
        def outer(ctx) -> None:
            print(outer_hi, flush=True)
            ctx.obj = outer_flag

        def mid_cb(ctx) -> None:
            print(mid_hi, flush=True)
            if replace:
                ctx.obj = mid_flag

        def leaf(obj) -> None:
            print(leaf_hi, flush=True)
            print(f"FLAG:{obj}", flush=True)

        mid = _grp(mid_cb, inject=pass_context, name=mid_name)
        mid.add_command(_cmd(leaf, inject=pass_obj, name=leaf_name))
        root = _grp(outer, inject=pass_context)
        root.add_command(mid)
        return root

    replaced = _dispatch(tree(replace=True), [mid_name, leaf_name])
    kept = _dispatch(tree(replace=False), [mid_name, leaf_name])
    print(f"replaced={replaced.stdout_text!r} kept={kept.stdout_text!r}", flush=True)
    assert_success_marker_present(replaced, leaf_hi)
    assert labeled_stdout_field(replaced, "FLAG:") == mid_flag
    assert labeled_stdout_field(replaced, "FLAG:") != outer_flag
    assert_success_marker_present(kept, leaf_hi)
    assert labeled_stdout_field(kept, "FLAG:") == outer_flag


def test_callback_may_request_context_as_first_argument():
    outer_hi, leaf_hi = _greeting(), _greeting()
    leaf_name = _word()
    flag = _flag()

    def outer(ctx) -> None:
        print(outer_hi, flush=True)
        ctx.obj = flag

    def leaf(ctx) -> None:
        print(leaf_hi, flush=True)
        print(f"FLAG:{ctx.obj}", flush=True)

    root = _grp(outer, inject=pass_context)
    root.add_command(_cmd(leaf, inject=pass_context, name=leaf_name))
    result = _dispatch(root, [leaf_name])
    print(f"ctx-first={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, outer_hi)
    assert_success_marker_present(result, leaf_hi)
    assert labeled_stdout_field(result, "FLAG:") == flag


def test_typed_object_is_found_on_parent_chain():
    class TypeA:
        def __init__(self, flag: str = "") -> None:
            self.flag = flag

    class TypeB:
        def __init__(self, flag: str = "") -> None:
            self.flag = flag

    outer_hi, mid_hi, leaf_hi = _greeting(), _greeting(), _greeting()
    mid_name, leaf_name = _word(), _word()
    flag = _flag()
    pass_a = make_pass_decorator(TypeA)

    def outer(ctx) -> None:
        print(outer_hi, flush=True)
        ctx.obj = TypeA(flag)

    def mid(ctx) -> None:
        print(mid_hi, flush=True)
        ctx.obj = TypeB()

    def leaf(obj) -> None:
        print(leaf_hi, flush=True)
        print(f"FLAG:{obj.flag}", flush=True)

    mid_g = _grp(mid, inject=pass_context, name=mid_name)
    mid_g.add_command(_cmd(leaf, inject=pass_a, name=leaf_name))
    root = _grp(outer, inject=pass_context)
    root.add_command(mid_g)
    result = _dispatch(root, [mid_name, leaf_name])
    print(f"typed={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, leaf_hi)
    assert labeled_stdout_field(result, "FLAG:") == flag


def test_ensure_creates_empty_typed_object_when_absent():
    class TypeA:
        def __init__(self, flag: str = "") -> None:
            self.flag = flag

    class TypeB:
        def __init__(self, flag: str = "") -> None:
            self.flag = flag

    outer_hi, leaf_hi = _greeting(), _greeting()
    leaf_name = _word()
    empty_mark = f"EMPTYB:{uuid.uuid4().hex}:"
    outer_flag = _flag()
    pass_b_ensure = make_pass_decorator(TypeB, ensure=True)
    pass_b = make_pass_decorator(TypeB)

    def tree(*, ensure: bool):
        def outer(ctx) -> None:
            print(outer_hi, flush=True)
            ctx.obj = TypeA(outer_flag)

        def leaf(obj) -> None:
            print(leaf_hi, flush=True)
            is_b = type(obj) is TypeB
            empty_slot = getattr(obj, "flag", None) == ""
            not_a = type(obj) is not TypeA
            if is_b and empty_slot and not_a:
                print(empty_mark, flush=True)

        inject = pass_b_ensure if ensure else pass_b
        root = _grp(outer, inject=pass_context)
        root.add_command(_cmd(leaf, inject=inject, name=leaf_name))
        return root

    created = _dispatch(tree(ensure=True), [leaf_name])
    absent = _dispatch(tree(ensure=False), [leaf_name])
    print(f"ensure={created.stdout_text!r} absent={absent.stdout_text!r}", flush=True)
    assert_success_marker_present(created, leaf_hi)
    assert empty_mark in _stdout(created)
    assert empty_mark not in _stdout(absent)


def test_ensure_reuses_typed_object_already_on_chain():
    class TypeA:
        def __init__(self, flag: str = "") -> None:
            self.flag = flag

    outer_hi, leaf_hi = _greeting(), _greeting()
    leaf_name = _word()
    flag = _flag()
    pass_a_ensure = make_pass_decorator(TypeA, ensure=True)

    def outer(ctx) -> None:
        print(outer_hi, flush=True)
        ctx.obj = TypeA(flag)

    def leaf(obj) -> None:
        print(leaf_hi, flush=True)
        print(f"FLAG:{obj.flag}", flush=True)

    root = _grp(outer, inject=pass_context)
    root.add_command(_cmd(leaf, inject=pass_a_ensure, name=leaf_name))
    result = _dispatch(root, [leaf_name])
    print(f"reuse={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, leaf_hi)
    assert labeled_stdout_field(result, "FLAG:") == flag


# ---------------------------------------------------------------------------
# B. Automatic environment prefix (options only) and opt-out
# ---------------------------------------------------------------------------


def test_toplevel_prefix_fills_omitted_option():
    greeting = _greeting()
    dest = _word()
    flag = f"--{dest}"
    prefix = _word().upper()
    value = _word()
    defaulted = _word()
    key = automatic_env_name(prefix, dest)

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    leaf = _cmd(callback, option(flag, dest, default=defaulted))
    filled = _dispatch(leaf, [], env={key: value}, auto_envvar_prefix=prefix)
    omitted = _dispatch(leaf, [], auto_envvar_prefix=prefix)
    print(f"filled={filled.stdout_text!r} omitted={omitted.stdout_text!r} key={key!r}", flush=True)
    assert_success_marker_present(filled, greeting)
    assert marker_occurs(_stdout(filled), f"V:{value}")
    assert_success_marker_present(omitted, greeting)
    assert marker_occurs(_stdout(omitted), f"V:{defaulted}")
    assert_marker_absent(_stdout(omitted), f"V:{value}")


def test_dashed_command_and_option_names_build_prefix_key():
    greeting = _greeting()
    cmd_name = f"{_word()}-{_word()}"
    opt_left, opt_right = _word(), _word()
    dest = f"{opt_left}_{opt_right}"
    flag = f"--{opt_left}-{opt_right}"
    prefix = _word().upper()
    value = _word()
    other = _word()
    defaulted = _word()
    key = automatic_env_name(prefix, cmd_name, dest)
    dashed_wrong = f"{prefix}_{cmd_name.upper()}_{dest.upper()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    def root() -> None:
        return None

    cli = _grp(root)
    cli.add_command(
        _cmd(callback, option(flag, dest, default=defaulted), name=cmd_name)
    )
    filled = _dispatch(
        cli, [cmd_name], env={key: value}, auto_envvar_prefix=prefix
    )
    wrong = _dispatch(
        cli, [cmd_name], env={dashed_wrong: other}, auto_envvar_prefix=prefix
    )
    print(
        f"dashed={filled.stdout_text!r} wrong={wrong.stdout_text!r} "
        f"key={key!r} dashed_wrong={dashed_wrong!r}",
        flush=True,
    )
    assert_success_marker_present(filled, greeting)
    assert marker_occurs(_stdout(filled), f"V:{value}")
    assert_success_marker_present(wrong, greeting)
    assert_marker_absent(_stdout(wrong), f"V:{other}")
    assert marker_occurs(_stdout(wrong), f"V:{defaulted}")


def test_each_command_name_is_in_the_prefix_key():
    greeting = _greeting()
    top_name, mid_name, leaf_name = _word(), _word(), _word()
    dest = _word()
    flag = f"--{dest}"
    prefix = _word().upper()
    value = _word()
    other = _word()
    defaulted = _word()
    key = automatic_env_name(prefix, mid_name, leaf_name, dest)
    short = automatic_env_name(prefix, mid_name, dest)

    def leaf_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    mid = _blank_group(name=mid_name)
    mid.add_command(
        _cmd(leaf_cb, option(flag, dest, default=defaulted), name=leaf_name)
    )
    root = _blank_group(name=top_name)
    root.add_command(mid)
    filled = _dispatch(
        root,
        [mid_name, leaf_name],
        env={key: value},
        auto_envvar_prefix=prefix,
        prog_name=top_name,
    )
    contrast = _dispatch(
        root,
        [mid_name, leaf_name],
        env={short: other},
        auto_envvar_prefix=prefix,
        prog_name=top_name,
    )
    print(
        f"nested={filled.stdout_text!r} short={contrast.stdout_text!r} "
        f"key={key!r} short_key={short!r}",
        flush=True,
    )
    assert_success_marker_present(filled, greeting)
    assert marker_occurs(_stdout(filled), f"V:{value}")
    assert_success_marker_present(contrast, greeting)
    assert_marker_absent(_stdout(contrast), f"V:{other}")


def test_dashed_prefix_is_normalized_in_the_key():
    greeting = _greeting()
    dest = _word()
    flag = f"--{dest}"
    prefix = f"{_word()}-{_word()}"
    value = _word()
    other = _word()
    defaulted = _word()
    key = automatic_env_name(prefix, dest)
    dashed_wrong = f"{prefix.upper()}_{dest.upper()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    leaf = _cmd(callback, option(flag, dest, default=defaulted))
    filled = _dispatch(leaf, [], env={key: value}, auto_envvar_prefix=prefix)
    wrong = _dispatch(
        leaf, [], env={dashed_wrong: other}, auto_envvar_prefix=prefix
    )
    print(
        f"norm={filled.stdout_text!r} dashed={wrong.stdout_text!r} "
        f"key={key!r} dashed_wrong={dashed_wrong!r}",
        flush=True,
    )
    assert_success_marker_present(filled, greeting)
    assert marker_occurs(_stdout(filled), f"V:{value}")
    assert_success_marker_present(wrong, greeting)
    assert_marker_absent(_stdout(wrong), f"V:{other}")


def test_option_may_opt_out_of_automatic_prefix():
    greeting = _greeting()
    keep_dest, out_dest = _word(), _word()
    keep_flag, out_flag = f"--{keep_dest}", f"--{out_dest}"
    prefix = _word().upper()
    keep_val, out_val = _word(), _word()
    keep_default, out_default = _word(), _word()
    keep_key = automatic_env_name(prefix, keep_dest)
    out_key = automatic_env_name(prefix, out_dest)

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"K:{kwargs[keep_dest]}", flush=True)
        print(f"O:{kwargs[out_dest]}", flush=True)

    leaf = _cmd(
        callback,
        option(keep_flag, keep_dest, default=keep_default),
        option(
            out_flag,
            out_dest,
            default=out_default,
            allow_from_autoenv=False,
        ),
    )
    result = _dispatch(
        leaf,
        [],
        env={keep_key: keep_val, out_key: out_val},
        auto_envvar_prefix=prefix,
    )
    print(f"optout={result.stdout_text!r} keep={keep_key!r} out={out_key!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert labeled_stdout_field(result, "K:") == keep_val
    assert labeled_stdout_field(result, "O:") != out_val
    assert labeled_stdout_field(result, "O:") == out_default


def test_opted_out_option_uses_prefix_key_only_if_explicitly_named():
    greeting = _greeting()
    dest = _word()
    flag = f"--{dest}"
    prefix = _word().upper()
    prefix_val, named_val = _word(), _word()
    defaulted = _word()
    key = automatic_env_name(prefix, dest)
    other_env = f"E{_word().upper()}"

    def _value_leaf(*, envvar: str):
        def callback(**kwargs) -> None:
            print(greeting, flush=True)
            print(f"V:{kwargs[dest]}", flush=True)

        return _cmd(
            callback,
            option(
                flag,
                dest,
                default=defaulted,
                allow_from_autoenv=False,
                envvar=envvar,
            ),
        )

    named = _value_leaf(envvar=key)
    other = _value_leaf(envvar=other_env)
    via_named = _dispatch(
        named, [], env={key: prefix_val}, auto_envvar_prefix=prefix
    )
    via_prefix_only = _dispatch(
        other, [], env={key: prefix_val}, auto_envvar_prefix=prefix
    )
    via_other = _dispatch(
        other, [], env={other_env: named_val, key: prefix_val}, auto_envvar_prefix=prefix
    )
    print(
        f"named={via_named.stdout_text!r} prefix_only={via_prefix_only.stdout_text!r} "
        f"other={via_other.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(via_named, greeting)
    assert marker_occurs(_stdout(via_named), f"V:{prefix_val}")
    assert_success_marker_present(via_prefix_only, greeting)
    assert_marker_absent(_stdout(via_prefix_only), f"V:{prefix_val}")
    assert marker_occurs(_stdout(via_prefix_only), f"V:{defaulted}")
    assert_success_marker_present(via_other, greeting)
    assert marker_occurs(_stdout(via_other), f"V:{named_val}")
    assert_marker_absent(_stdout(via_other), f"V:{prefix_val}")


def test_automatic_prefix_does_not_fill_sibling_argument():
    greeting = _greeting()
    opt_dest, arg_dest = _word(), _word()
    flag = f"--{opt_dest}"
    prefix = _word().upper()
    opt_val, invented_val = _word(), _word()
    arg_default = _word()
    opt_key = automatic_env_name(prefix, opt_dest)
    invented = automatic_env_name(prefix, arg_dest)

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"O:{kwargs[opt_dest]}", flush=True)
        print(f"A:{kwargs[arg_dest]}", flush=True)

    leaf = _cmd(
        callback,
        option(flag, opt_dest),
        argument(arg_dest, default=arg_default),
    )
    result = _dispatch(
        leaf,
        [],
        env={opt_key: opt_val, invented: invented_val},
        auto_envvar_prefix=prefix,
    )
    print(f"sibling={result.stdout_text!r} invented={invented!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert labeled_stdout_field(result, "O:") == opt_val
    assert labeled_stdout_field(result, "A:") != invented_val
    assert labeled_stdout_field(result, "A:") == arg_default


def test_command_line_beats_prefix_environment():
    greeting = _greeting()
    dest = _word()
    flag = f"--{dest}"
    prefix = _word().upper()
    env_val, cli_val = _word(), _word()
    key = automatic_env_name(prefix, dest)

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    leaf = _cmd(callback, option(flag, dest))
    result = _dispatch(
        leaf,
        [flag, cli_val],
        env={key: env_val},
        auto_envvar_prefix=prefix,
    )
    print(f"cli-beats={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert marker_occurs(_stdout(result), f"V:{cli_val}")
    assert_marker_absent(_stdout(result), f"V:{env_val}")


def test_required_option_satisfied_from_prefix_key():
    greeting = _greeting()
    dest = _word()
    flag = f"--{dest}"
    prefix = _word().upper()
    value = _runtime_int()
    key = automatic_env_name(prefix, dest)
    expected = value * 3 + 7

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    leaf = _cmd(callback, option(flag, dest, required=True, type=INT))
    filled = _dispatch(
        leaf, [], env={key: str(value)}, auto_envvar_prefix=prefix
    )
    missing = _dispatch(leaf, [], auto_envvar_prefix=prefix)
    print(f"req-prefix={filled.stdout_text!r} miss={missing.stderr_text!r}", flush=True)
    assert_success_marker_present(filled, greeting)
    assert marker_occurs(_stdout(filled), f"T:{expected}")
    assert_usage_class(missing, greeting)


# ---------------------------------------------------------------------------
# C. Nested default map, split, two hang methods
# ---------------------------------------------------------------------------


def test_nested_default_map_used_when_flag_omitted_and_beaten_by_cli():
    greeting = _greeting()
    child_name, other_name = _word(), _word()
    dest = _word()
    flag = f"--{dest}"
    map_val, cli_val, declared = _word(), _word(), _word()

    def child_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    def root() -> None:
        return None

    cli = _grp(root)
    cli.add_command(
        _cmd(child_cb, option(flag, dest, default=declared), name=child_name)
    )
    nested = {child_name: {dest: map_val}}
    omitted = _dispatch(cli, [child_name], default_map=nested)
    beaten = _dispatch(cli, [child_name, flag, cli_val], default_map=nested)
    print(f"map={omitted.stdout_text!r} cli={beaten.stdout_text!r}", flush=True)
    assert_success_marker_present(omitted, greeting)
    assert marker_occurs(_stdout(omitted), f"V:{map_val}")
    assert_marker_absent(_stdout(omitted), f"V:{declared}")
    assert_success_marker_present(beaten, greeting)
    assert marker_occurs(_stdout(beaten), f"V:{cli_val}")
    assert_marker_absent(_stdout(beaten), f"V:{map_val}")


def test_wrong_nested_key_does_not_fill_this_child():
    greeting = _greeting()
    child_name, other_name = _word(), _word()
    dest = _word()
    flag = f"--{dest}"
    map_val, declared = _word(), _word()

    def child_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    def root() -> None:
        return None

    cli = _grp(root)
    cli.add_command(
        _cmd(child_cb, option(flag, dest, default=declared), name=child_name)
    )
    right = _dispatch(
        cli, [child_name], default_map={child_name: {dest: map_val}}
    )
    wrong = _dispatch(
        cli, [child_name], default_map={other_name: {dest: map_val}}
    )
    print(
        f"right-key={right.stdout_text!r} wrong-key={wrong.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(right, greeting)
    assert marker_occurs(_stdout(right), f"V:{map_val}")
    assert_marker_absent(_stdout(right), f"V:{declared}")
    assert_success_marker_present(wrong, greeting)
    assert_marker_absent(_stdout(wrong), f"V:{map_val}")
    assert marker_occurs(_stdout(wrong), f"V:{declared}")


def test_default_map_from_command_declaration():
    greeting = _greeting()
    child_name = _word()
    dest = _word()
    flag = f"--{dest}"
    map_val, declared = _word(), _word()
    nested = {child_name: {dest: map_val}}

    def child_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    def root() -> None:
        return None

    cli = _grp(root, context_settings={"default_map": nested})
    cli.add_command(
        _cmd(child_cb, option(flag, dest, default=declared), name=child_name)
    )
    result = _dispatch(cli, [child_name])
    print(f"declared-map={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert marker_occurs(_stdout(result), f"V:{map_val}")
    assert_marker_absent(_stdout(result), f"V:{declared}")


def test_nested_default_map_fills_omitted_argument():
    greeting = _greeting()
    child_name, other_name = _word(), _word()
    dest = _word()
    map_n = _runtime_int()
    declared = map_n + 11
    expected = map_n * 3 + 7

    def child_cb(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    def root() -> None:
        return None

    cli = _grp(root)
    cli.add_command(
        _cmd(
            child_cb,
            argument(dest, default=declared, type=INT, required=False),
            name=child_name,
        )
    )
    filled = _dispatch(cli, [child_name], default_map={child_name: {dest: map_n}})
    wrong = _dispatch(
        cli, [child_name], default_map={other_name: {dest: map_n}}
    )
    print(f"arg-map={filled.stdout_text!r} wrong={wrong.stdout_text!r}", flush=True)
    assert_success_marker_present(filled, greeting)
    assert marker_occurs(_stdout(filled), f"T:{expected}")
    assert_success_marker_present(wrong, greeting)
    assert marker_occurs(_stdout(wrong), f"T:{declared * 3 + 7}")
    assert_marker_absent(_stdout(wrong), f"T:{expected}")


def test_default_map_string_splits_like_environment():
    greeting = _greeting()
    child_name = _word()
    dest = _word()
    flag = f"--{dest}"
    a, b = _word(), _word()
    blob = f"{a} {b}"

    def pair_cb(**kwargs) -> None:
        print(greeting, flush=True)
        pair = kwargs[dest]
        print(f"P:{pair[0]}|{pair[1]}", flush=True)

    def whole_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"W:{kwargs[dest]}", flush=True)

    paired = _blank_group()
    paired.add_command(
        _cmd(pair_cb, option(flag, dest, nargs=2), name=child_name)
    )
    single = _blank_group()
    single.add_command(_cmd(whole_cb, option(flag, dest), name=child_name))
    pair = _dispatch(
        paired, [child_name], default_map={child_name: {dest: blob}}
    )
    whole = _dispatch(
        single, [child_name], default_map={child_name: {dest: blob}}
    )
    print(f"pair={pair.stdout_text!r} whole={whole.stdout_text!r}", flush=True)
    assert_success_marker_present(pair, greeting)
    assert f"P:{a}|{b}" in _stdout(pair)
    assert_success_marker_present(whole, greeting)
    assert f"W:{blob}" in _stdout(whole)

    left = f"/tmp/{_word()}"
    right = f"/var/{_word()}"
    path_blob = f"{left}:{right}"
    path_dest = _word()
    path_flag = f"--{path_dest}"
    path_name = _word()

    def path_cb(**kwargs) -> None:
        print(greeting, flush=True)
        pair = kwargs[path_dest]
        print(f"Q:{pair[0]}|{pair[1]}", flush=True)

    path_cli = _blank_group()
    path_cli.add_command(
        _cmd(
            path_cb,
            option(path_flag, path_dest, nargs=2, type=Path()),
            name=path_name,
        )
    )
    paths = _dispatch(
        path_cli,
        [path_name],
        default_map={path_name: {path_dest: path_blob}},
    )
    print(f"path-map={paths.stdout_text!r}", flush=True)
    assert_success_marker_present(paths, greeting)
    assert f"Q:{left}|{right}" in _stdout(paths)


def test_default_map_sequence_is_used_as_is():
    greeting = _greeting()
    child_name = _word()
    dest = _word()
    flag = f"--{dest}"
    a, b = _word(), _word()
    blob = f"{a} {b}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_seq(kwargs[dest])

    def root() -> None:
        return None

    cli = _grp(root)
    cli.add_command(
        _cmd(callback, option(flag, dest, multiple=True), name=child_name)
    )
    as_seq = _dispatch(
        cli, [child_name], default_map={child_name: {dest: (blob,)}}
    )
    print(f"seq={as_seq.stdout_text!r}", flush=True)
    assert_success_marker_present(as_seq, greeting)
    assert "N:1" in _stdout(as_seq)
    assert f"V:0:{blob}" in _stdout(as_seq)


def test_arity1_repeatable_default_map_string_is_refused():
    greeting = _greeting()
    dest = _word()
    flag = f"--{dest}"
    a, b = _word(), _word()
    blob = f"{a} {b}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_seq(kwargs[dest])

    map_cli = _cmd(callback, option(flag, dest, multiple=True))
    declared_cli = _cmd(
        callback, option(flag, dest, multiple=True, default=blob)
    )
    from_map = _dispatch(map_cli, [], default_map={dest: blob})
    from_declared = _dispatch(declared_cli, [])
    print(
        f"map-string={from_map.stderr_text!r} "
        f"declared-string={from_declared.stderr_text!r}",
        flush=True,
    )
    assert_usage_class(from_map, greeting)
    require_usage_names_option(from_map, greeting, flag)
    assert_usage_class(from_declared, greeting)
    require_usage_names_option(from_declared, greeting, flag)


def test_nested_map_delivers_converted_integer():
    greeting = _greeting()
    child_name = _word()
    dest = _word()
    flag = f"--{dest}"
    map_n = _runtime_int()
    cli_n = map_n + 4
    declared = map_n + 9

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    def root() -> None:
        return None

    cli = _grp(root)
    cli.add_command(
        _cmd(callback, option(flag, dest, default=declared), name=child_name)
    )
    from_map = _dispatch(
        cli, [child_name], default_map={child_name: {dest: map_n}}
    )
    from_cli = _dispatch(
        cli,
        [child_name, f"{flag}={cli_n}"],
        default_map={child_name: {dest: map_n}},
    )
    print(f"imap={from_map.stdout_text!r} icli={from_cli.stdout_text!r}", flush=True)
    assert_success_marker_present(from_map, greeting)
    assert marker_occurs(_stdout(from_map), f"T:{map_n * 3 + 7}")
    assert_success_marker_present(from_cli, greeting)
    assert marker_occurs(_stdout(from_cli), f"T:{cli_n * 3 + 7}")


def test_required_option_satisfied_from_nested_map():
    greeting = _greeting()
    child_name = _word()
    dest = _word()
    flag = f"--{dest}"
    value = _runtime_int()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])

    def root() -> None:
        return None

    cli = _grp(root)
    cli.add_command(
        _cmd(callback, option(flag, dest, required=True, type=INT), name=child_name)
    )
    filled = _dispatch(
        cli, [child_name], default_map={child_name: {dest: value}}
    )
    missing = _dispatch(cli, [child_name], default_map={child_name: {}})
    print(f"req-map={filled.stdout_text!r} miss={missing.stderr_text!r}", flush=True)
    assert_success_marker_present(filled, greeting)
    assert marker_occurs(_stdout(filled), f"T:{value * 3 + 7}")
    assert_usage_class(missing, greeting)


# ---------------------------------------------------------------------------
# D. Five origins; undeclared keys are untracked
# ---------------------------------------------------------------------------


def _source_leaf(greeting: str, dest: str, flag: str, *, default, prompt: bool, env_name: str):
    def callback(ctx, **kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])
        src = ctx.get_parameter_source(dest)
        if src is None:
            print("SRC:NO_TRACKED_SOURCE", flush=True)
        else:
            print(f"SRC:{src}", flush=True)

    return _cmd(
        callback,
        option(flag, dest, type=INT, default=default, prompt=prompt, envvar=env_name),
        inject=pass_context,
    )


def test_source_distinguishes_five_origins_for_the_same_value():
    greeting = _greeting()
    dest = _word()
    flag = f"--{dest}"
    env_name = f"E{_word().upper()}"
    unused_env = f"E{_word().upper()}"
    unused_key = _word()
    number = _runtime_int()
    other_n = number + 17
    expected = number * 3 + 7
    unused_map = {unused_key: other_n}
    other_line = str(other_n)
    stdin_other = f"{other_line}\n"
    stdin_prompt = f"{number}\n"
    covariates = (
        str(number),
        str(other_n),
        flag,
        dest,
        env_name,
        unused_env,
        unused_key,
        other_line,
        stdin_other.strip(),
        stdin_prompt.strip(),
    )

    plain = _source_leaf(
        greeting, dest, flag, default=number, prompt=False, env_name=env_name
    )
    prompting = _source_leaf(
        greeting, dest, flag, default=None, prompt=True, env_name=env_name
    )

    cli = _dispatch(
        plain,
        [flag, str(number)],
        env={unused_env: str(other_n)},
        default_map=unused_map,
        stdin=stdin_other,
    )
    environ = _dispatch(
        plain,
        [],
        env={env_name: str(number), unused_env: str(other_n)},
        default_map=unused_map,
        stdin=stdin_other,
    )
    from_map = _dispatch(
        plain,
        [],
        env={unused_env: str(other_n)},
        default_map={dest: number, unused_key: other_n},
        stdin=stdin_other,
    )
    declared = _dispatch(
        plain,
        [],
        env={unused_env: str(other_n)},
        default_map=unused_map,
        stdin=stdin_other,
    )
    prompted = _dispatch(
        prompting,
        [],
        env={unused_env: str(other_n)},
        default_map=unused_map,
        stdin=stdin_prompt,
    )
    print(
        f"cli={cli.stdout_text!r} env={environ.stdout_text!r} "
        f"map={from_map.stdout_text!r} dec={declared.stdout_text!r} "
        f"prompt={prompted.stdout_text!r}",
        flush=True,
    )
    for result in (cli, environ, from_map, declared, prompted):
        assert_success_marker_present(result, greeting)
        assert marker_occurs(_stdout(result), f"T:{expected}")
        assert_marker_absent(_stdout(result), f"T:{other_n * 3 + 7}")
    assert_labeled_fields_unlike(
        cli, environ, from_map, declared, prompted, label="SRC:", covariates=covariates
    )


def test_command_line_source_does_not_consume_prompt_stdin():
    greeting = _greeting()
    dest = _word()
    flag = f"--{dest}"
    number = _runtime_int()
    other_n = number + 13
    unused_key = _word()

    def callback(ctx, **kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])
        src = ctx.get_parameter_source(dest)
        if src is None:
            print("SRC:NO_TRACKED_SOURCE", flush=True)
        else:
            print(f"SRC:{src}", flush=True)

    leaf = _cmd(
        callback,
        option(flag, dest, type=INT, prompt=True),
        inject=pass_context,
    )
    via_cli = _dispatch(
        leaf,
        [flag, str(number)],
        default_map={unused_key: other_n},
        stdin=f"{other_n}\n",
    )
    via_prompt = _dispatch(
        leaf,
        [],
        default_map={unused_key: other_n},
        stdin=f"{number}\n",
    )
    print(f"cli-stdin={via_cli.stdout_text!r} prompt={via_prompt.stdout_text!r}", flush=True)
    assert_success_marker_present(via_cli, greeting)
    assert marker_occurs(_stdout(via_cli), f"T:{number * 3 + 7}")
    assert_marker_absent(_stdout(via_cli), f"T:{other_n * 3 + 7}")
    assert_success_marker_present(via_prompt, greeting)
    assert marker_occurs(_stdout(via_prompt), f"T:{number * 3 + 7}")
    assert_labeled_fields_unlike(
        via_cli,
        via_prompt,
        label="SRC:",
        covariates=(str(number), str(other_n), flag, dest, unused_key),
    )


def test_source_distinguishes_cli_map_declared_for_argument():
    greeting = _greeting()
    child_name = _word()
    dest = _word()
    number = _runtime_int()
    unused_key = _word()
    expected = number * 3 + 7

    def child_cb(ctx, **kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])
        src = ctx.get_parameter_source(dest)
        if src is None:
            print("SRC:NO_TRACKED_SOURCE", flush=True)
        else:
            print(f"SRC:{src}", flush=True)

    def root() -> None:
        return None

    cli = _grp(root)
    cli.add_command(
        _cmd(
            child_cb,
            argument(dest, default=number, type=INT, required=False),
            inject=pass_context,
            name=child_name,
        )
    )
    via_cli = _dispatch(
        cli,
        [child_name, str(number)],
        default_map={unused_key: number},
    )
    via_map = _dispatch(
        cli,
        [child_name],
        default_map={child_name: {dest: number}, unused_key: number},
    )
    via_def = _dispatch(
        cli,
        [child_name],
        default_map={unused_key: number},
    )
    print(
        f"arg-cli={via_cli.stdout_text!r} arg-map={via_map.stdout_text!r} "
        f"arg-def={via_def.stdout_text!r}",
        flush=True,
    )
    for result in (via_cli, via_map, via_def):
        assert_success_marker_present(result, greeting)
        assert marker_occurs(_stdout(result), f"T:{expected}")
    assert_labeled_fields_unlike(
        via_cli,
        via_map,
        via_def,
        label="SRC:",
        covariates=(str(number), dest, child_name, unused_key),
    )


def test_undeclared_extra_key_is_not_converted_or_tracked():
    greeting = _greeting()
    dest = _word()
    flag = f"--{dest}"
    extra = _word()
    number = _runtime_int()
    extra_text = str(number + 21)
    unused_key = _word()

    def callback(ctx, **kwargs) -> None:
        print(greeting, flush=True)
        _emit_arith(kwargs[dest])
        src = ctx.get_parameter_source(dest)
        if src is None:
            print("SRC:NO_TRACKED_SOURCE", flush=True)
        else:
            print(f"SRC:{src}", flush=True)
        extra_src = ctx.get_parameter_source(extra)
        if extra_src is None:
            print("XSRC:NO_TRACKED_SOURCE", flush=True)
        else:
            print(f"XSRC:{extra_src}", flush=True)
        stuffed = kwargs.get(extra, "MISSING")
        print(f"EXTRA:{stuffed!r}", flush=True)
        try:
            mark = stuffed * 3 + 7  # type: ignore[operator]
        except TypeError:
            print("EXMARK:RAW", flush=True)
        else:
            print(f"EXMARK:INT:{mark}", flush=True)

    leaf = _cmd(
        callback,
        option(flag, dest, type=INT, default=number),
        inject=pass_context,
    )
    mapped = _dispatch(
        leaf,
        [],
        default_map={dest: number, extra: extra_text},
    )
    print(f"undeclared-map={mapped.stdout_text!r}", flush=True)
    assert_success_marker_present(mapped, greeting)
    assert marker_occurs(_stdout(mapped), f"T:{number * 3 + 7}")
    assert labeled_stdout_field(mapped, "XSRC:") == "NO_TRACKED_SOURCE"
    assert labeled_stdout_field(mapped, "SRC:") != labeled_stdout_field(mapped, "XSRC:")

    target_hi = _greeting()
    opt_dest = _word()
    opt_flag = f"--{opt_dest}"
    extra_name = _word()

    def target_cb(ctx, **kwargs) -> None:
        print(target_hi, flush=True)
        _emit_arith(kwargs[opt_dest])
        src = ctx.get_parameter_source(opt_dest)
        if src is None:
            print("TSRC:NO_TRACKED_SOURCE", flush=True)
        else:
            print(f"TSRC:{src}", flush=True)
        extra_src = ctx.get_parameter_source(extra_name)
        if extra_src is None:
            print("TXSRC:NO_TRACKED_SOURCE", flush=True)
        else:
            print(f"TXSRC:{extra_src}", flush=True)
        stuffed = kwargs.get(extra_name, "MISSING")
        print(f"TEXTRA:{stuffed!r}", flush=True)
        try:
            mark = stuffed * 3 + 7  # type: ignore[operator]
        except TypeError:
            print("TEXMARK:RAW", flush=True)
        else:
            print(f"TEXMARK:INT:{mark}", flush=True)

    target = _cmd(
        target_cb,
        option(opt_flag, opt_dest, type=INT),
        inject=pass_context,
    )

    def source_cb(ctx) -> None:
        print(greeting, flush=True)
        ctx.invoke(target, **{opt_dest: number, extra_name: extra_text})

    source = _cmd(source_cb, inject=pass_context)
    invoked = _dispatch(source, [])
    print(f"undeclared-invoke={invoked.stdout_text!r}", flush=True)
    assert_success_marker_present(invoked, greeting)
    assert_success_marker_present(invoked, target_hi)
    assert marker_occurs(_stdout(invoked), f"T:{number * 3 + 7}")
    assert labeled_stdout_field(invoked, "TXSRC:") == "NO_TRACKED_SOURCE"
    assert "TEXMARK:RAW" in _stdout(invoked)
    assert extra_text in labeled_stdout_field(invoked, "TEXTRA:")

    declared_run = _dispatch(target, [opt_flag, extra_text])
    print(f"declared-int={declared_run.stdout_text!r}", flush=True)
    assert_success_marker_present(declared_run, target_hi)
    assert marker_occurs(_stdout(declared_run), f"T:{int(extra_text) * 3 + 7}")
    assert labeled_stdout_field(declared_run, "TSRC:") != "NO_TRACKED_SOURCE"


# ---------------------------------------------------------------------------
# E. Group resources stay open through children and close after
# ---------------------------------------------------------------------------


class _Probe:
    def __init__(self) -> None:
        self.available = False
        self.closed = False

    def __enter__(self) -> _Probe:
        self.available = True
        self.closed = False
        return self

    def __exit__(self, *args: object) -> None:
        self.available = False
        self.closed = True


def test_group_resource_stays_open_through_child_and_closes_after_invoke():
    group_hi, child_hi = _greeting(), _greeting()
    child_name = _word()
    probe = _Probe()

    def outer(ctx) -> None:
        print(group_hi, flush=True)
        ctx.with_resource(probe)
        ctx.obj = probe

    def child(obj) -> None:
        print(child_hi, flush=True)
        print(f"OPEN:{int(bool(obj.available))}", flush=True)

    root = _grp(outer, inject=pass_context)
    root.add_command(_cmd(child, inject=pass_obj, name=child_name))
    result = _dispatch(root, [child_name])
    print(
        f"res={result.stdout_text!r} closed={probe.closed} avail={probe.available}",
        flush=True,
    )
    assert_success_marker_present(result, group_hi)
    assert_success_marker_present(result, child_hi)
    assert labeled_stdout_field(result, "OPEN:") == "1"
    assert probe.closed
    assert not probe.available
    text = _stdout(result)
    assert text.find(child_hi) < text.find("OPEN:") or "OPEN:" in text


def test_resource_cleanup_runs_on_standalone_process_exit():
    group_hi, child_hi = _greeting(), _greeting()
    child_name = _word()
    sentinel = FSPath(tempfile.mkdtemp(prefix="f07-res-")) / "closed.txt"
    closed_mark = f"CLOSED:{uuid.uuid4().hex}:"
    code = (
        "from pathlib import Path\n"
        "from optlyn import command, group, pass_context, pass_obj\n"
        f"SENT = Path({str(sentinel)!r})\n"
        f"CLOSED = {closed_mark!r}\n"
        f"GROUP_HI = {group_hi!r}\n"
        f"CHILD_HI = {child_hi!r}\n"
        f"CHILD_NAME = {child_name!r}\n"
        "class Probe:\n"
        "    def __enter__(self):\n"
        "        return self\n"
        "    def __exit__(self, *args):\n"
        "        SENT.write_text(CLOSED, encoding='utf-8')\n"
        "def outer(ctx):\n"
        "    print(GROUP_HI, flush=True)\n"
        "    ctx.with_resource(Probe())\n"
        "    ctx.obj = True\n"
        "def child(obj):\n"
        "    print(CHILD_HI, flush=True)\n"
        "    print('OPEN:1', flush=True)\n"
        "    if SENT.exists():\n"
        "        print('PRE:' + SENT.read_text(encoding='utf-8'), flush=True)\n"
        "    else:\n"
        "        print('PRE:', flush=True)\n"
        "root = group()(pass_context(outer))\n"
        "root.add_command(command(name=CHILD_NAME)(pass_obj(child)))\n"
        "root.main(args=[CHILD_NAME], standalone_mode=True, prog_name='app')\n"
    )
    result = run_python(code=code)
    print(f"proc={result.stdout_text!r} code={result.returncode}", flush=True)
    assert result.returncode == 0, (
        f"standalone resource process failed; stderr={result.stderr_text!r}"
    )
    assert child_hi in result.stdout_text
    assert "OPEN:1" in result.stdout_text
    pre = labeled_stdout_field(result, "PRE:")
    assert closed_mark not in pre
    try:
        after = sentinel.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"failed to read close sentinel {sentinel}: {exc}") from exc
    assert after == closed_mark, (
        f"sentinel was not closed after process exit; after={after!r}"
    )


def test_resource_cleanup_runs_after_child_usage_failure():
    group_hi, child_hi = _greeting(), _greeting()
    child_name = _word()
    unknown = f"--{unrelated_dispatch_token(child_name)}"
    probe = _Probe()

    def outer(ctx) -> None:
        print(group_hi, flush=True)
        ctx.with_resource(probe)

    def child() -> None:
        print(child_hi, flush=True)

    root = _grp(outer, inject=pass_context)
    root.add_command(_cmd(child, name=child_name))
    result = _dispatch(root, [child_name, unknown])
    print(
        f"usage-close={result.exit_code} stdout={result.stdout_text!r} "
        f"closed={probe.closed}",
        flush=True,
    )
    assert_usage_class(result, child_hi)
    assert probe.closed


# ---------------------------------------------------------------------------
# F. Token normalization for option names, choice values, command names
# ---------------------------------------------------------------------------


def test_lowercase_normalizer_matches_option_name():
    greeting = _greeting()
    dest = _word()
    flag = f"--{dest}"
    value = _word()
    upper = f"--{dest.upper()}={value}"
    other = f"--{unrelated_dispatch_token(dest)}={value}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    leaf = _cmd(callback, option(flag, dest))
    lowered = _dispatch(leaf, [upper], token_normalize_func=_lower)
    missing = _dispatch(leaf, [upper])
    identity = _dispatch(leaf, [upper], token_normalize_func=_identity)
    alien = _dispatch(leaf, [other], token_normalize_func=_lower)
    print(
        f"lower={lowered.stdout_text!r} miss={missing.exit_code} "
        f"ident={identity.exit_code} alien={alien.exit_code}",
        flush=True,
    )
    assert_success_marker_present(lowered, greeting)
    assert marker_occurs(_stdout(lowered), f"V:{value}")
    assert_usage_class(missing, greeting)
    assert_usage_class(identity, greeting)
    assert_usage_class(alien, greeting)


def test_lowercase_normalizer_matches_choice_value():
    greeting = _greeting()
    dest = _word()
    flag = f"--{dest}"
    member = _word()
    upper = member.upper()
    alien = unrelated_dispatch_token(member)

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"V:{kwargs[dest]}", flush=True)

    leaf = _cmd(callback, option(flag, dest, type=Choice([member])))
    lowered = _dispatch(leaf, [flag, upper], token_normalize_func=_lower)
    missing = _dispatch(leaf, [flag, upper])
    identity = _dispatch(leaf, [flag, upper], token_normalize_func=_identity)
    other = _dispatch(leaf, [flag, alien], token_normalize_func=_lower)
    print(
        f"choice={lowered.stdout_text!r} miss={missing.exit_code} "
        f"ident={identity.exit_code} alien={other.exit_code}",
        flush=True,
    )
    assert_success_marker_present(lowered, greeting)
    assert marker_occurs(_stdout(lowered), f"V:{member}") or marker_occurs(
        _stdout(lowered), f"V:{upper}"
    )
    assert_usage_class(missing, greeting)
    assert_usage_class(identity, greeting)
    assert_usage_class(other, greeting)


def test_lowercase_normalizer_matches_command_name():
    child_hi = _greeting()
    child_name = _word()
    upper = child_name.upper()
    alien = unrelated_dispatch_token(child_name)

    def child() -> None:
        print(child_hi, flush=True)

    def root() -> None:
        return None

    cli = _grp(root)
    cli.add_command(_cmd(child, name=child_name))
    lowered = _dispatch(cli, [upper], token_normalize_func=_lower)
    missing = _dispatch(cli, [upper])
    identity = _dispatch(cli, [upper], token_normalize_func=_identity)
    other = _dispatch(cli, [alien], token_normalize_func=_lower)
    print(
        f"cmd={lowered.stdout_text!r} miss={missing.exit_code} "
        f"ident={identity.exit_code} alien={other.exit_code}",
        flush=True,
    )
    assert_success_marker_present(lowered, child_hi)
    assert_usage_class(missing, child_hi)
    assert_usage_class(identity, child_hi)
    assert_usage_class(other, child_hi)


# ---------------------------------------------------------------------------
# G. Invoke supplies chosen values; forward fills current values
# ---------------------------------------------------------------------------


def test_invoke_supplies_caller_chosen_values():
    source_hi, target_hi = _greeting(), _greeting()
    opt_dest, arg_dest = _word(), _word()
    flag = f"--{opt_dest}"
    flag_mark = _flag()
    a, b = _runtime_int(), _runtime_int()
    c, d = a + 5, b + 6

    def target_cb(obj, **kwargs) -> None:
        print(target_hi, flush=True)
        print(f"FLAG:{obj}", flush=True)
        print(f"TO:{kwargs[opt_dest] * 3 + 7}", flush=True)
        print(f"TA:{kwargs[arg_dest] * 3 + 7}", flush=True)

    target = _cmd(
        target_cb,
        option(flag, opt_dest, type=INT),
        argument(arg_dest, type=INT),
        inject=pass_obj,
    )

    def source_cb(ctx, **kwargs) -> None:
        print(source_hi, flush=True)
        ctx.obj = flag_mark
        ctx.invoke(target, **{opt_dest: c, arg_dest: d})

    source = _cmd(
        source_cb,
        option(flag, opt_dest, type=INT),
        argument(arg_dest, type=INT),
        inject=pass_context,
    )
    result = _dispatch(source, [flag, str(a), str(b)])
    print(f"invoke={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, source_hi)
    assert_success_marker_present(result, target_hi)
    assert labeled_stdout_field(result, "FLAG:") == flag_mark
    assert labeled_stdout_field(result, "TO:") == str(c * 3 + 7)
    assert labeled_stdout_field(result, "TA:") == str(d * 3 + 7)
    assert labeled_stdout_field(result, "TO:") != str(a * 3 + 7)
    assert labeled_stdout_field(result, "TA:") != str(b * 3 + 7)


def test_forward_fills_from_current_command_values():
    source_hi, target_hi = _greeting(), _greeting()
    opt_dest, arg_dest = _word(), _word()
    flag = f"--{opt_dest}"
    flag_mark = _flag()
    a, b = _runtime_int(), _runtime_int()
    c, d = a + 5, b + 6

    def target_cb(obj, **kwargs) -> None:
        print(target_hi, flush=True)
        print(f"FLAG:{obj}", flush=True)
        print(f"TO:{kwargs[opt_dest] * 3 + 7}", flush=True)
        print(f"TA:{kwargs[arg_dest] * 3 + 7}", flush=True)

    target = _cmd(
        target_cb,
        option(flag, opt_dest, type=INT),
        argument(arg_dest, type=INT),
        inject=pass_obj,
    )

    def source_cb(ctx, **kwargs) -> None:
        print(source_hi, flush=True)
        ctx.obj = flag_mark
        ctx.forward(target)

    source = _cmd(
        source_cb,
        option(flag, opt_dest, type=INT),
        argument(arg_dest, type=INT),
        inject=pass_context,
    )
    result = _dispatch(source, [flag, str(a), str(b)])
    print(f"forward={result.stdout_text!r} unused={c},{d}", flush=True)
    assert_success_marker_present(result, source_hi)
    assert_success_marker_present(result, target_hi)
    assert labeled_stdout_field(result, "FLAG:") == flag_mark
    assert labeled_stdout_field(result, "TO:") == str(a * 3 + 7)
    assert labeled_stdout_field(result, "TA:") == str(b * 3 + 7)
    assert labeled_stdout_field(result, "TO:") != str(c * 3 + 7)
    assert labeled_stdout_field(result, "TA:") != str(d * 3 + 7)


# ---------------------------------------------------------------------------
# H. Current context is thread-local unless entered
# ---------------------------------------------------------------------------


def test_current_context_is_thread_local_unless_entered():
    greeting = _greeting()
    flag = _flag()

    def callback(ctx) -> None:
        print(greeting, flush=True)
        ctx.obj = flag
        print(f"HERE:{get_current_context().obj}", flush=True)

        def unentered() -> None:
            print("URAN:1", flush=True)
            try:
                print(f"USEEN:{get_current_context().obj}", flush=True)
            except Exception:
                print("USEEN:", flush=True)

        def entered() -> None:
            print("ERAN:1", flush=True)
            with ctx:
                print(f"ESEEN:{get_current_context().obj}", flush=True)

        t1 = threading.Thread(target=unentered)
        t1.start()
        t1.join(5)
        assert not t1.is_alive(), "unentered thread did not finish"
        t2 = threading.Thread(target=entered)
        t2.start()
        t2.join(5)
        assert not t2.is_alive(), "entered thread did not finish"

    leaf = _cmd(callback, inject=pass_context)
    result = _dispatch(leaf, [])
    print(f"thread={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert labeled_stdout_field(result, "HERE:") == flag
    assert labeled_stdout_field(result, "URAN:") == "1"
    assert labeled_stdout_field(result, "USEEN:") != flag
    assert labeled_stdout_field(result, "ERAN:") == "1"
    assert labeled_stdout_field(result, "ESEEN:") == flag


def test_echo_inherits_color_flag_only_on_entered_thread():
    greeting = _greeting()
    payload = f"P{uuid.uuid4().hex[:10]}"

    def unentered_cb(ctx) -> None:
        print(greeting, flush=True)

        def work() -> None:
            print("URAN:1", flush=True)
            echo(style(payload, fg="cyan"))

        t = threading.Thread(target=work)
        t.start()
        t.join(5)
        assert not t.is_alive(), "unentered color thread did not finish"

    def entered_cb(ctx) -> None:
        print(greeting, flush=True)

        def work() -> None:
            print("ERAN:1", flush=True)
            with ctx:
                echo(style(payload, fg="cyan"))

        t = threading.Thread(target=work)
        t.start()
        t.join(5)
        assert not t.is_alive(), "entered color thread did not finish"

    unentered = _dispatch(
        _cmd(unentered_cb, inject=pass_context), [], color=True
    )
    entered = _dispatch(
        _cmd(entered_cb, inject=pass_context), [], color=True
    )
    print(f"echo-u={unentered.stdout_text!r} echo-e={entered.stdout_text!r}", flush=True)
    assert_success_marker_present(unentered, greeting)
    assert labeled_stdout_field(unentered, "URAN:") == "1"
    assert payload in _stdout(unentered)
    assert_ansi_escape_absent(unentered)
    assert_success_marker_present(entered, greeting)
    assert labeled_stdout_field(entered, "ERAN:") == "1"
    assert payload in _stdout(entered)
    assert_ansi_escape_present(entered)


# ---------------------------------------------------------------------------
# I. Invocation-level force color on / off / autodetect
# ---------------------------------------------------------------------------


def test_invocation_force_color_on_keeps_styles_on_pipe():
    greeting = _greeting()
    payload = f"P{uuid.uuid4().hex[:10]}"

    def styled() -> None:
        print(greeting, flush=True)
        echo(style(payload, fg="cyan"))

    def plain() -> None:
        print(greeting, flush=True)
        echo(payload)

    on_styled = _dispatch(_cmd(styled), [], color=True)
    on_plain = _dispatch(_cmd(plain), [], color=True)
    print(f"on-styled={on_styled.stdout_text!r} on-plain={on_plain.stdout_text!r}", flush=True)
    assert_success_marker_present(on_styled, greeting)
    assert payload in _stdout(on_styled)
    assert_ansi_escape_present(on_styled)
    assert_success_marker_present(on_plain, greeting)
    assert payload in _stdout(on_plain)
    styled_rest = styled_stdout_remainder(on_styled, payload)
    plain_rest = styled_stdout_remainder(on_plain, payload)
    assert styled_rest != plain_rest, (
        f"force-on styled and plain remainders match after stripping "
        f"{payload!r}; styled={styled_rest!r} plain={plain_rest!r}"
    )


def test_invocation_autodetect_strips_styles_on_pipe():
    greeting = _greeting()
    payload = f"P{uuid.uuid4().hex[:10]}"

    def callback() -> None:
        print(greeting, flush=True)
        echo(style(payload, fg="cyan"))

    leaf = _cmd(callback)
    forced = _dispatch(leaf, [], color=True)
    auto = _dispatch(leaf, [])
    print(f"forced={forced.stdout_text!r} auto={auto.stdout_text!r}", flush=True)
    assert_success_marker_present(forced, greeting)
    assert_ansi_escape_present(forced)
    assert_success_marker_present(auto, greeting)
    assert payload in _stdout(auto)
    assert_ansi_escape_absent(auto)


def test_invocation_force_color_off_strips_styles_on_terminal():
    greeting = _greeting()
    payload = f"P{uuid.uuid4().hex[:10]}"

    def _tty_script(color_expr: str) -> str:
        return (
            "from optlyn import command, echo, style\n"
            f"GREET = {greeting!r}\n"
            f"PAYLOAD = {payload!r}\n"
            "def callback():\n"
            "    print(GREET, flush=True)\n"
            "    echo(style(PAYLOAD, fg='cyan'))\n"
            "leaf = command()(callback)\n"
            f"leaf.main(args=[], standalone_mode=True, prog_name='app', color={color_expr})\n"
        )

    auto = run_python_on_tty(_tty_script("None"))
    off = run_python_on_tty(_tty_script("False"))
    print(
        f"pty-auto={auto.stdout_text!r} pty-off={off.stdout_text!r} "
        f"auto_rc={auto.returncode} off_rc={off.returncode}",
        flush=True,
    )
    assert auto.returncode == 0, (
        f"pty autodetect failed; stdout={auto.stdout_text!r}"
    )
    assert off.returncode == 0, (
        f"pty force-off failed; stdout={off.stdout_text!r}"
    )
    assert greeting in auto.stdout_text
    assert payload in auto.stdout_text
    assert_ansi_escape_present(auto)
    assert greeting in off.stdout_text
    assert payload in off.stdout_text
    assert_ansi_escape_absent(off)
