# feature: F08
"""Prompts, confirmation, and hidden input (FP-08).

Assertions stay at the PRD's precision: omitted options read and convert
stdin; command-line and environment supply skip the prompt; declared and
default-map values still prompt, are shown, and an empty-line answer uses
that shown default; standalone prompt/confirm; hidden input; password and
confirmation options; re-ask; EOF is abort. Prompt punctuation, abort
sentence wording, and exception types are not pinned.
"""

from __future__ import annotations

import uuid

from optlyn import (
    INT,
    command,
    confirm,
    confirmation_option,
    option,
    password_option,
    prompt,
    style,
)
from optlyn.testing import CliRunner

from F08_helpers import _name_derived_prompt_tokens, _print_prompt_arith
from _harness import InvokeResult, invoke
from _helpers import (
    assert_abort_indication_unlike_usage,
    assert_abort_without_marker,
    assert_ansi_escape_absent,
    assert_ansi_escape_present,
    assert_declaration_refused,
    assert_success_marker_present,
    assert_usage_class,
    call_with_fed_stdin,
    caller_visible_remainder,
    labeled_stdout_field,
    require_usage_names_option,
    run_python_on_tty,
    unrelated_dispatch_token,
)

PROG = "app"


def _word() -> str:
    return "k" + uuid.uuid4().hex[:8]


def _greeting() -> str:
    return f"GREET:{uuid.uuid4().hex}:"


def _runtime_int() -> int:
    return 14 + uuid.uuid4().int % 80


def _opt() -> tuple[str, str]:
    dest = _word()
    return f"--{dest}", dest


def _unknown_flag() -> str:
    return f"--{unrelated_dispatch_token()}"


def _arith(value: int) -> int:
    return value * 3 + 7


def _secret_mark(secret: str, salt: str) -> str:
    acc = len(secret) * 17
    for i, ch in enumerate(secret):
        acc += (ord(ch) + i + 1) * (ord(salt[i % len(salt)]) + 3)
    return f"K:{acc}"


def _dispatch(cli, args, **kwargs):
    kwargs.setdefault("prog_name", PROG)
    return invoke(cli, args, **kwargs)


def _runner_dispatch(cli, args, *, stdin: str) -> InvokeResult:
    """Run *cli* through the product's own ``CliRunner`` (hidden input is fed
    the way the runner feeds it) and present the outcome in harness form."""
    got = CliRunner().invoke(cli, list(args), input=stdin, prog_name=PROG)
    return InvokeResult(
        exit_code=got.exit_code,
        stdout=got.stdout_bytes,
        stderr=got.stderr_bytes,
        output=got.output.encode("utf-8"),
        return_value=None,
        exception=got.exception,
        exc_info=None,
        args=tuple(args),
        cwd="",
    )


def _tty_styled_prompt_script(greeting: str, payload: str, typed: str) -> str:
    return (
        "import io\n"
        "import sys\n"
        "from optlyn import INT, command, prompt, style\n"
        f"GREET = {greeting!r}\n"
        f"PAYLOAD = {payload!r}\n"
        f"TYPED = {typed!r}\n"
        "def callback():\n"
        "    print(GREET, flush=True)\n"
        "    prompt(style(PAYLOAD, fg='cyan'), type=INT)\n"
        "leaf = command()(callback)\n"
        "sys.stdin = io.StringIO(TYPED + '\\n')\n"
        "leaf.main(args=[], standalone_mode=True, prog_name='app')\n"
    )


def _tty_styled_confirm_script(greeting: str, payload: str) -> str:
    return (
        "import io\n"
        "import sys\n"
        "from optlyn import command, confirm, style\n"
        f"GREET = {greeting!r}\n"
        f"PAYLOAD = {payload!r}\n"
        "def callback():\n"
        "    print(GREET, flush=True)\n"
        "    confirm(style(PAYLOAD, fg='cyan'))\n"
        "leaf = command()(callback)\n"
        "sys.stdin = io.StringIO('yes\\n')\n"
        "leaf.main(args=[], standalone_mode=True, prog_name='app')\n"
    )


def _cmd(callback, *param_decs, **command_kwargs):
    command_kwargs.setdefault("name", _word())
    decorated = callback
    for deco in reversed(param_decs):
        decorated = deco(decorated)
    return command(**command_kwargs)(decorated)


def _stdout(result) -> str:
    text = result.stdout_text
    if text is None:
        raise RuntimeError("stdout is None; cannot observe")
    return text


def _emit_str(value: object) -> None:
    print(f"\nV:{value}", flush=True)


def _int_leaf(greeting: str, flag: str, dest: str, **option_kw):
    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _print_prompt_arith(kwargs[dest])

    return _cmd(callback, option(flag, dest, type=INT, **option_kw))


def _str_leaf(greeting: str, flag: str, dest: str, **option_kw):
    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        _emit_str(kwargs[dest])

    return _cmd(callback, option(flag, dest, **option_kw))


def _runner_output(result) -> str:
    try:
        text = result.output
    except Exception as exc:
        raise RuntimeError(f"failed to read runner capture: {exc}") from exc
    if text is None:
        raise RuntimeError("runner capture is None; cannot observe")
    return text


def _require_arith(result, greeting: str, value: int) -> None:
    assert_success_marker_present(result, greeting)
    field = labeled_stdout_field(result, "T:")
    expected = str(_arith(value))
    assert field == expected, (
        f"converted integer mark {expected!r} missing; field={field!r} "
        f"stdout={result.stdout_text!r}"
    )


def _require_str(result, greeting: str, value: str) -> None:
    assert_success_marker_present(result, greeting)
    field = labeled_stdout_field(result, "V:")
    assert field == value, (
        f"delivered string {value!r} missing; field={field!r} "
        f"stdout={result.stdout_text!r}"
    )


def _require_shown_default_in_prompt(result, greeting: str, shown: str) -> None:
    """*shown* remains after stripping the greeting and the V: delivery line.

    That remainder is the prompt. A skip-prompt fill that only prints the
    delivered default has an empty remainder here and cannot green.
    """
    rest = caller_visible_remainder(result, greeting)
    field = labeled_stdout_field(result, "V:")
    without_delivery = rest.replace(f"V:{field}", "", 1)
    assert shown in without_delivery, (
        f"shown default {shown!r} missing from the prompt remainder after "
        f"stripping the delivery line; remainder={without_delivery!r} "
        f"stdout={result.stdout_text!r}"
    )


# ---------------------------------------------------------------------------
# A. Omitted prompt reads stdin; command-line supply skips
# ---------------------------------------------------------------------------


def test_omitted_prompted_option_reads_converted_stdin():
    greeting = _greeting()
    flag, dest = _opt()
    number = _runtime_int()
    leaf = _int_leaf(greeting, flag, dest, prompt=True)

    result = _dispatch(leaf, [], stdin=f"{number}\n")
    print(f"omitted-prompt={result.stdout_text!r}", flush=True)
    _require_arith(result, greeting, number)


def test_command_line_value_skips_prompt():
    greeting = _greeting()
    flag, dest = _opt()
    cli_n = _runtime_int()
    stdin_n = cli_n + 11
    leaf = _int_leaf(greeting, flag, dest, prompt=True)

    baseline = _dispatch(leaf, [], stdin=f"{stdin_n}\n")
    eq_hang = _dispatch(leaf, [f"{flag}={cli_n}"], stdin=f"{stdin_n}\n")
    eq_empty = _dispatch(leaf, [f"{flag}={cli_n}"], stdin="")
    sp_hang = _dispatch(leaf, [flag, str(cli_n)], stdin=f"{stdin_n}\n")
    sp_empty = _dispatch(leaf, [flag, str(cli_n)], stdin="")
    print(
        f"baseline={baseline.stdout_text!r} eq_hang={eq_hang.stdout_text!r} "
        f"eq_empty={eq_empty.stdout_text!r} sp_hang={sp_hang.stdout_text!r} "
        f"sp_empty={sp_empty.stdout_text!r}",
        flush=True,
    )
    _require_arith(baseline, greeting, stdin_n)
    _require_arith(eq_hang, greeting, cli_n)
    _require_arith(eq_empty, greeting, cli_n)
    _require_arith(sp_hang, greeting, cli_n)
    _require_arith(sp_empty, greeting, cli_n)


# ---------------------------------------------------------------------------
# B. Custom prompt string replaces the name-derived prompt
# ---------------------------------------------------------------------------


def test_custom_prompt_string_replaces_name_derived_prompt():
    greeting = _greeting()
    flag_a, dest_a = _opt()
    flag_b, dest_b = _opt()
    typed = f"typ-{uuid.uuid4().hex}"
    ask = f"ASK-{uuid.uuid4().hex}"
    derived_a = _str_leaf(greeting, flag_a, dest_a, prompt=True)
    derived_b = _str_leaf(greeting, flag_b, dest_b, prompt=True)
    custom = _str_leaf(greeting, flag_a, dest_a, prompt=ask)

    first = _dispatch(derived_a, [], stdin=f"{typed}\n")
    second = _dispatch(derived_b, [], stdin=f"{typed}\n")
    replaced = _dispatch(custom, [], stdin=f"{typed}\n")
    print(
        f"derived_a={first.stdout_text!r} derived_b={second.stdout_text!r} "
        f"custom={replaced.stdout_text!r}",
        flush=True,
    )
    _require_str(first, greeting, typed)
    _require_str(second, greeting, typed)
    _require_str(replaced, greeting, typed)
    rest_a = caller_visible_remainder(first, greeting, typed)
    rest_b = caller_visible_remainder(second, greeting, typed)
    assert rest_a != rest_b, (
        "name-derived prompts are not distinct after stripping the typed "
        f"value; a={rest_a!r} b={rest_b!r}"
    )
    assert ask in _stdout(replaced), (
        f"author prompt string {ask!r} missing; stdout={replaced.stdout_text!r}"
    )
    custom_rest = caller_visible_remainder(replaced, greeting, typed, ask)
    derived_tokens = _name_derived_prompt_tokens(rest_a, rest_b)
    assert derived_tokens, (
        "name-derived prompt produced no distinctive text to check for "
        f"replacement; a={rest_a!r} b={rest_b!r}"
    )
    for token in derived_tokens:
        assert token not in custom_rest, (
            "name-derived prompt text still present after stripping the "
            "author string; replacement requires it to be gone "
            f"(token={token!r} remainder={custom_rest!r})"
        )


# ---------------------------------------------------------------------------
# C. Prompt-not-required-on-omit; required still skips when valued
# ---------------------------------------------------------------------------


def test_prompt_not_required_on_omit_uses_default_without_reading_stdin():
    greeting = _greeting()
    flag, dest = _opt()
    default_n = _runtime_int()
    stdin_n = default_n + 13
    leaf = _int_leaf(
        greeting, flag, dest, prompt=True, prompt_required=False, default=default_n
    )

    hanging = _dispatch(leaf, [], stdin=f"{stdin_n}\n")
    empty = _dispatch(leaf, [], stdin="")
    print(
        f"omit-hang={hanging.stdout_text!r} omit-empty={empty.stdout_text!r}",
        flush=True,
    )
    _require_arith(hanging, greeting, default_n)
    _require_arith(empty, greeting, default_n)


def test_prompt_not_required_on_omit_asks_when_flag_has_no_value():
    greeting = _greeting()
    flag, dest = _opt()
    default_n = _runtime_int()
    stdin_n = default_n + 9
    cli_n = default_n + 21
    leaf = _int_leaf(
        greeting, flag, dest, prompt=True, prompt_required=False, default=default_n
    )

    bare = _dispatch(leaf, [flag], stdin=f"{stdin_n}\n")
    valued_hang = _dispatch(leaf, [f"{flag}={cli_n}"], stdin=f"{stdin_n}\n")
    valued_empty = _dispatch(leaf, [flag, str(cli_n)], stdin="")
    print(
        f"bare={bare.stdout_text!r} valued_hang={valued_hang.stdout_text!r} "
        f"valued_empty={valued_empty.stdout_text!r}",
        flush=True,
    )
    _require_arith(bare, greeting, stdin_n)
    _require_arith(valued_hang, greeting, cli_n)
    _require_arith(valued_empty, greeting, cli_n)


def test_required_prompt_asks_on_omit_and_on_bare_flag():
    greeting = _greeting()
    flag, dest = _opt()
    stdin_n = _runtime_int()
    off = _int_leaf(
        greeting, flag, dest, prompt=True, prompt_required=False, required=True
    )
    on = _int_leaf(greeting, flag, dest, prompt=True, required=True)

    omit_off = _dispatch(off, [], stdin=f"{stdin_n}\n")
    bare_off = _dispatch(off, [flag], stdin=f"{stdin_n}\n")
    omit_on = _dispatch(on, [], stdin=f"{stdin_n}\n")
    print(
        f"omit_off={omit_off.stdout_text!r} bare_off={bare_off.stdout_text!r} "
        f"omit_on={omit_on.stdout_text!r}",
        flush=True,
    )
    _require_arith(omit_off, greeting, stdin_n)
    _require_arith(bare_off, greeting, stdin_n)
    _require_arith(omit_on, greeting, stdin_n)


def test_required_prompt_still_skips_when_value_is_on_command_line():
    greeting = _greeting()
    flag, dest = _opt()
    cli_n = _runtime_int()
    stdin_n = cli_n + 8
    leaf = _int_leaf(greeting, flag, dest, prompt=True, required=True)

    eq_hang = _dispatch(leaf, [f"{flag}={cli_n}"], stdin=f"{stdin_n}\n")
    eq_empty = _dispatch(leaf, [f"{flag}={cli_n}"], stdin="")
    sp_hang = _dispatch(leaf, [flag, str(cli_n)], stdin=f"{stdin_n}\n")
    sp_empty = _dispatch(leaf, [flag, str(cli_n)], stdin="")
    print(
        f"eq_hang={eq_hang.stdout_text!r} eq_empty={eq_empty.stdout_text!r} "
        f"sp_hang={sp_hang.stdout_text!r} sp_empty={sp_empty.stdout_text!r}",
        flush=True,
    )
    _require_arith(eq_hang, greeting, cli_n)
    _require_arith(eq_empty, greeting, cli_n)
    _require_arith(sp_hang, greeting, cli_n)
    _require_arith(sp_empty, greeting, cli_n)


def test_required_prompt_eof_is_abort_not_usage():
    greeting = _greeting()
    flag, dest = _opt()
    asked = _int_leaf(greeting, flag, dest, prompt=True, required=True)
    silent = _int_leaf(greeting, flag, dest, required=True)
    unknown = _unknown_flag()

    aborted = _dispatch(asked, [], stdin="")
    missing = _dispatch(silent, [])
    usage = _dispatch(asked, [unknown], stdin=f"{_runtime_int()}\n")
    print(
        f"eof={aborted.exit_code}/{aborted.stderr_text!r} "
        f"missing={missing.exit_code}/{missing.stderr_text!r} "
        f"unknown={usage.exit_code}/{usage.stderr_text!r}",
        flush=True,
    )
    assert_abort_indication_unlike_usage(aborted, missing, greeting, flag, dest)
    assert_usage_class(missing, greeting)
    assert_usage_class(usage, greeting)


# ---------------------------------------------------------------------------
# D. Declared / map defaults still prompt; empty line uses shown default;
#    only environment skips
# ---------------------------------------------------------------------------


def test_environment_value_skips_prompt_even_on_eof():
    greeting = _greeting()
    flag, dest = _opt()
    env_name = f"E{_word().upper()}"
    ask = f"ASK-{uuid.uuid4().hex}"
    env_n = _runtime_int()
    stdin_n = env_n + 15
    leaf = _int_leaf(greeting, flag, dest, prompt=ask, envvar=env_name)

    baseline = _dispatch(leaf, [], stdin=f"{stdin_n}\n")
    hanging = _dispatch(
        leaf, [], stdin=f"{stdin_n}\n", env={env_name: str(env_n)}
    )
    empty = _dispatch(leaf, [], stdin="", env={env_name: str(env_n)})
    print(
        f"noenv={baseline.stdout_text!r} env_hang={hanging.stdout_text!r} "
        f"env_empty={empty.stdout_text!r}",
        flush=True,
    )
    _require_arith(baseline, greeting, stdin_n)
    _require_arith(hanging, greeting, env_n)
    _require_arith(empty, greeting, env_n)

    # Observe the author prompt string on the mixed streams after
    # stripping only the greeting. Do not strip the typed integer: a
    # two-digit stdin value can be a substring of the UUID in *ask*,
    # and replacing it would turn "prompt ran" into "prompt missing".
    noenv_rest = caller_visible_remainder(baseline, greeting)
    env_rest = caller_visible_remainder(hanging, greeting)
    assert ask in noenv_rest, (
        f"author prompt string {ask!r} missing from the no-environment "
        f"remainder {noenv_rest!r}"
    )
    assert ask not in env_rest, (
        f"author prompt string {ask!r} still present after an environment "
        f"skip; remainder={env_rest!r}"
    )


def test_static_declared_default_still_prompts():
    greeting = _greeting()
    flag, dest = _opt()
    default = f"def-{uuid.uuid4().hex}"
    typed = f"typ-{uuid.uuid4().hex}"
    cli_val = f"cli-{uuid.uuid4().hex}"
    leaf = _str_leaf(greeting, flag, dest, prompt=True, default=default)

    eof = _dispatch(leaf, [], stdin="")
    empty_line = _dispatch(leaf, [], stdin="\n")
    asked = _dispatch(leaf, [], stdin=f"{typed}\n")
    skipped = _dispatch(leaf, [f"{flag}={cli_val}"], stdin="")
    print(
        f"eof={eof.exit_code}/{eof.stderr_text!r} "
        f"empty_line={empty_line.stdout_text!r} asked={asked.stdout_text!r} "
        f"skipped={skipped.stdout_text!r}",
        flush=True,
    )
    assert_abort_without_marker(eof, greeting)
    _require_str(empty_line, greeting, default)
    _require_str(asked, greeting, typed)
    shown = caller_visible_remainder(asked, greeting, typed)
    assert default in shown, (
        f"declared default {default!r} was not shown; remainder={shown!r}"
    )
    _require_str(skipped, greeting, cli_val)
    skip_rest = caller_visible_remainder(skipped, greeting, cli_val)
    assert default not in skip_rest, (
        f"declared default {default!r} appeared without a prompt; "
        f"remainder={skip_rest!r}"
    )


def test_callable_default_still_prompts_and_is_invoked():
    greeting = _greeting()
    flag, dest = _opt()
    token = f"tok-{uuid.uuid4().hex}"
    typed = f"typ-{uuid.uuid4().hex}"
    cli_val = f"cli-{uuid.uuid4().hex}"
    box: list[str] = []

    def factory() -> str:
        box.append(token)
        return token

    leaf = _str_leaf(greeting, flag, dest, prompt=True, default=factory)
    box.clear()
    asked = _dispatch(leaf, [], stdin=f"{typed}\n")
    print(f"asked={asked.stdout_text!r} box={box!r}", flush=True)
    _require_str(asked, greeting, typed)
    assert box, "callable default was never invoked during the prompt"
    shown = caller_visible_remainder(asked, greeting, typed)
    assert token in shown, (
        f"callable default {token!r} was not shown; remainder={shown!r}"
    )

    box.clear()
    skipped = _dispatch(leaf, [f"{flag}={cli_val}"], stdin="")
    print(f"skipped={skipped.stdout_text!r}", flush=True)
    _require_str(skipped, greeting, cli_val)
    skip_rest = caller_visible_remainder(skipped, greeting, cli_val)
    assert token not in skip_rest, (
        f"callable default {token!r} appeared without a prompt; "
        f"remainder={skip_rest!r}"
    )

    box.clear()
    empty_line = _dispatch(leaf, [], stdin="\n")
    print(
        f"empty_line={empty_line.stdout_text!r} box={box!r}",
        flush=True,
    )
    assert box, "callable default was never invoked on an empty-line answer"
    _require_str(empty_line, greeting, token)

    box.clear()
    eof = _dispatch(leaf, [], stdin="")
    print(f"eof={eof.exit_code}/{eof.stderr_text!r}", flush=True)
    assert_abort_without_marker(eof, greeting)


def test_default_map_value_still_prompts():
    greeting = _greeting()
    flag, dest = _opt()
    mapped = f"map-{uuid.uuid4().hex}"
    typed = f"typ-{uuid.uuid4().hex}"
    cli_val = f"cli-{uuid.uuid4().hex}"
    other = f"oth-{uuid.uuid4().hex}"
    leaf = _str_leaf(greeting, flag, dest, prompt=True, default=other)

    eof = _dispatch(leaf, [], stdin="", default_map={dest: mapped})
    empty_line = _dispatch(leaf, [], stdin="\n", default_map={dest: mapped})
    asked = _dispatch(leaf, [], stdin=f"{typed}\n", default_map={dest: mapped})
    skipped = _dispatch(
        leaf, [f"{flag}={cli_val}"], stdin="", default_map={dest: mapped}
    )
    print(
        f"eof={eof.exit_code}/{eof.stderr_text!r} "
        f"empty_line={empty_line.stdout_text!r} asked={asked.stdout_text!r} "
        f"skipped={skipped.stdout_text!r}",
        flush=True,
    )
    assert_abort_without_marker(eof, greeting)
    _require_str(empty_line, greeting, mapped)
    empty_field = labeled_stdout_field(empty_line, "V:")
    assert empty_field != other, (
        f"empty-line used the declared default {other!r} instead of the "
        f"shown default-map value {mapped!r}; field={empty_field!r}"
    )
    _require_str(asked, greeting, typed)
    shown = caller_visible_remainder(asked, greeting, typed)
    assert mapped in shown, (
        f"default-map value {mapped!r} was not shown; remainder={shown!r}"
    )
    _require_str(skipped, greeting, cli_val)
    skip_rest = caller_visible_remainder(skipped, greeting, cli_val)
    assert mapped not in skip_rest, (
        f"default-map value {mapped!r} appeared without a prompt; "
        f"remainder={skip_rest!r}"
    )


def test_empty_line_answer_uses_shown_default():
    greeting = _greeting()

    flag_s, dest_s = _opt()
    static = f"def-{uuid.uuid4().hex}"
    leaf_s = _str_leaf(greeting, flag_s, dest_s, prompt=True, default=static)
    eof_s = _dispatch(leaf_s, [], stdin="")
    empty_s = _dispatch(leaf_s, [], stdin="\n")
    print(
        f"static_eof={eof_s.exit_code}/{eof_s.stderr_text!r} "
        f"static_empty={empty_s.stdout_text!r}",
        flush=True,
    )
    assert_abort_without_marker(eof_s, greeting)
    _require_str(empty_s, greeting, static)
    _require_shown_default_in_prompt(empty_s, greeting, static)

    flag_c, dest_c = _opt()
    token = f"tok-{uuid.uuid4().hex}"
    box: list[str] = []

    def factory() -> str:
        box.append(token)
        return token

    leaf_c = _str_leaf(greeting, flag_c, dest_c, prompt=True, default=factory)
    box.clear()
    eof_c = _dispatch(leaf_c, [], stdin="")
    print(f"callable_eof={eof_c.exit_code}/{eof_c.stderr_text!r}", flush=True)
    assert_abort_without_marker(eof_c, greeting)

    box.clear()
    empty_c = _dispatch(leaf_c, [], stdin="\n")
    print(
        f"callable_empty={empty_c.stdout_text!r} box={box!r}",
        flush=True,
    )
    assert box, "callable default was never invoked on an empty-line answer"
    _require_str(empty_c, greeting, token)
    _require_shown_default_in_prompt(empty_c, greeting, token)

    flag_m, dest_m = _opt()
    mapped = f"map-{uuid.uuid4().hex}"
    other = f"oth-{uuid.uuid4().hex}"
    leaf_m = _str_leaf(greeting, flag_m, dest_m, prompt=True, default=other)
    eof_m = _dispatch(leaf_m, [], stdin="", default_map={dest_m: mapped})
    empty_m = _dispatch(leaf_m, [], stdin="\n", default_map={dest_m: mapped})
    print(
        f"map_eof={eof_m.exit_code}/{eof_m.stderr_text!r} "
        f"map_empty={empty_m.stdout_text!r}",
        flush=True,
    )
    assert_abort_without_marker(eof_m, greeting)
    _require_str(empty_m, greeting, mapped)
    map_field = labeled_stdout_field(empty_m, "V:")
    assert map_field != other, (
        f"empty-line used the declared default {other!r} instead of the "
        f"shown default-map value {mapped!r}; field={map_field!r}"
    )
    _require_shown_default_in_prompt(empty_m, greeting, mapped)


# ---------------------------------------------------------------------------
# E. Standalone prompt and confirm
# ---------------------------------------------------------------------------


def test_standalone_prompt_converts_with_declared_type():
    greeting = _greeting()
    ask = f"ASK-{uuid.uuid4().hex}"
    number = _runtime_int()

    def callback() -> None:
        print(greeting, flush=True)
        received = prompt(ask, type=INT)
        _print_prompt_arith(received)

    leaf = _cmd(callback)
    result = _dispatch(leaf, [], stdin=f"{number}\n")
    direct = call_with_fed_stdin(f"{number}\n", lambda: prompt(ask, type=INT))
    print(
        f"invoked={result.stdout_text!r} direct={direct!r}",
        flush=True,
    )
    _require_arith(result, greeting, number)
    assert ask in _stdout(result), (
        f"author prompt message {ask!r} missing; stdout={result.stdout_text!r}"
    )
    try:
        mark = direct * 3 + 7
    except TypeError as exc:
        raise AssertionError(
            f"standalone prompt returned a non-integer {direct!r}"
        ) from exc
    assert mark == _arith(number), (
        f"direct prompt mark {mark!r} is not {_arith(number)} for {direct!r}"
    )


def test_standalone_prompt_infers_type_from_default():
    greeting = _greeting()
    ask = f"ASK-{uuid.uuid4().hex}"
    default_n = _runtime_int()
    typed = default_n + 19

    def callback() -> None:
        print(greeting, flush=True)
        received = prompt(ask, default=default_n)
        _print_prompt_arith(received)

    leaf = _cmd(callback)
    result = _dispatch(leaf, [], stdin=f"{typed}\n")
    direct = call_with_fed_stdin(
        f"{typed}\n", lambda: prompt(ask, default=default_n)
    )
    print(f"invoked={result.stdout_text!r} direct={direct!r}", flush=True)
    _require_arith(result, greeting, typed)
    try:
        mark = direct * 3 + 7
    except TypeError as exc:
        raise AssertionError(
            f"inferred-type prompt returned a non-integer {direct!r}"
        ) from exc
    assert mark == _arith(typed), (
        f"inferred-type mark {mark!r} is not {_arith(typed)} for {direct!r}"
    )


def test_standalone_confirm_returns_boolean_without_abort():
    greeting = _greeting()
    ask = f"ASK-{uuid.uuid4().hex}"

    def callback() -> None:
        print(greeting, flush=True)
        answered = confirm(ask)
        print(f"\nB:{1 if answered else 0}", flush=True)

    leaf = _cmd(callback)
    yes = _dispatch(leaf, [], stdin="yes\n")
    no = _dispatch(leaf, [], stdin="no\n")
    print(f"yes={yes.stdout_text!r} no={no.stdout_text!r}", flush=True)
    assert_success_marker_present(yes, greeting)
    assert_success_marker_present(no, greeting)
    yes_bit = labeled_stdout_field(yes, "B:")
    no_bit = labeled_stdout_field(no, "B:")
    assert yes_bit != no_bit, (
        f"yes/no confirm branches are not distinct; yes={yes_bit!r} "
        f"no={no_bit!r}"
    )
    assert yes_bit == "1", f"yes branch mark is {yes_bit!r}, not 1"
    assert no_bit == "0", f"no branch mark is {no_bit!r}, not 0"


def test_standalone_confirm_abort_on_no_is_abort_class():
    greeting = _greeting()
    work = f"WORK:{uuid.uuid4().hex}:"
    ask = f"ASK-{uuid.uuid4().hex}"
    unknown = _unknown_flag()

    def callback() -> None:
        answered = confirm(ask, abort=True)
        print(greeting, flush=True)
        if answered:
            print(work, flush=True)

    leaf = _cmd(callback)
    declined = _dispatch(leaf, [], stdin="no\n")
    accepted = _dispatch(leaf, [], stdin="yes\n")
    usage = _dispatch(leaf, [unknown], stdin="yes\n")
    print(
        f"declined={declined.exit_code}/{declined.stderr_text!r} "
        f"accepted={accepted.stdout_text!r} usage={usage.exit_code}",
        flush=True,
    )
    assert_abort_indication_unlike_usage(declined, usage, greeting, unknown, ask)
    assert work not in _stdout(declined) and work not in declined.stderr_text, (
        f"work mark {work!r} present after a declined abort; "
        f"stdout={declined.stdout_text!r}"
    )
    assert_success_marker_present(accepted, greeting)
    assert work in _stdout(accepted), (
        f"work mark {work!r} missing after a yes answer; "
        f"stdout={accepted.stdout_text!r}"
    )


def test_standalone_prompt_reasks_until_valid_or_eof():
    greeting = _greeting()
    ask = f"ASK-{uuid.uuid4().hex}"
    legal = _runtime_int()
    illegal = unrelated_dispatch_token()
    extra = legal + 6
    unknown = _unknown_flag()

    def callback() -> None:
        received = prompt(ask, type=INT)
        print(greeting, flush=True)
        _print_prompt_arith(received)

    leaf = _cmd(callback)
    recovered = _dispatch(leaf, [], stdin=f"{illegal}\n{legal}\n")
    only_bad = _dispatch(leaf, [], stdin=f"{illegal}\n")
    first_wins = _dispatch(leaf, [], stdin=f"{legal}\n{extra}\n")
    usage = _dispatch(leaf, [unknown], stdin=f"{legal}\n")
    print(
        f"recovered={recovered.stdout_text!r} only_bad={only_bad.exit_code} "
        f"first_wins={first_wins.stdout_text!r}",
        flush=True,
    )
    _require_arith(recovered, greeting, legal)
    assert_abort_indication_unlike_usage(
        only_bad, usage, greeting, unknown, illegal, ask
    )
    _require_arith(first_wins, greeting, legal)


# ---------------------------------------------------------------------------
# F. Prompt/confirm strip ANSI on a non-terminal, matching echo
# ---------------------------------------------------------------------------


def test_standalone_prompt_strips_ansi_when_stream_is_not_a_terminal():
    greeting = _greeting()
    payload = f"P{uuid.uuid4().hex[:10]}"
    number = _runtime_int()

    def callback() -> None:
        print(greeting, flush=True)
        received = prompt(style(payload, fg="cyan"), type=INT)
        _print_prompt_arith(received)

    leaf = _cmd(callback)
    auto = _dispatch(leaf, [], stdin=f"{number}\n")
    on_tty = run_python_on_tty(
        _tty_styled_prompt_script(greeting, payload, str(number))
    )
    print(
        f"auto={auto.stdout_text!r} tty={on_tty.stdout_text!r} "
        f"tty_rc={on_tty.returncode}",
        flush=True,
    )
    _require_arith(auto, greeting, number)
    assert payload in _stdout(auto)
    assert_ansi_escape_absent(auto)
    assert on_tty.returncode == 0, (
        f"terminal-stream prompt failed; stdout={on_tty.stdout_text!r}"
    )
    assert greeting in on_tty.stdout_text
    assert payload in on_tty.stdout_text
    assert_ansi_escape_present(on_tty)


def test_standalone_confirm_strips_ansi_when_stream_is_not_a_terminal():
    greeting = _greeting()
    payload = f"P{uuid.uuid4().hex[:10]}"

    def callback() -> None:
        print(greeting, flush=True)
        answered = confirm(style(payload, fg="cyan"))
        print(f"\nB:{1 if answered else 0}", flush=True)

    leaf = _cmd(callback)
    auto = _dispatch(leaf, [], stdin="yes\n")
    on_tty = run_python_on_tty(_tty_styled_confirm_script(greeting, payload))
    print(
        f"auto={auto.stdout_text!r} tty={on_tty.stdout_text!r} "
        f"tty_rc={on_tty.returncode}",
        flush=True,
    )
    assert_success_marker_present(auto, greeting)
    assert labeled_stdout_field(auto, "B:") == "1"
    assert payload in _stdout(auto)
    assert_ansi_escape_absent(auto)
    assert on_tty.returncode == 0, (
        f"terminal-stream confirm failed; stdout={on_tty.stdout_text!r}"
    )
    assert greeting in on_tty.stdout_text
    assert payload in on_tty.stdout_text
    assert_ansi_escape_present(on_tty)


# ---------------------------------------------------------------------------
# G / J. Hidden input, confirmation twice, password option, runner echo
# ---------------------------------------------------------------------------


def test_hidden_input_not_echoed_visible_prompt_is():
    greeting = _greeting()
    ask = f"ASK-{uuid.uuid4().hex}"
    secret = f"sec-{uuid.uuid4().hex}"
    salt = f"sal-{uuid.uuid4().hex}"
    mark = _secret_mark(secret, salt)
    flag, dest = _opt()

    def make(*, hidden: bool):
        def callback(**kwargs) -> None:
            print(greeting, flush=True)
            print(mark if kwargs[dest] == secret else "K:0", flush=True)
            print(f"SALT:{salt}", flush=True)

        return _cmd(
            callback, option(flag, dest, prompt=ask, hide_input=hidden)
        )

    runner = CliRunner()
    visible = runner.invoke(make(hidden=False), [], input=f"{secret}\n")
    hidden = runner.invoke(make(hidden=True), [], input=f"{secret}\n")
    vis_out = _runner_output(visible)
    hid_out = _runner_output(hidden)
    print(
        f"vis_exit={visible.exit_code} hid_exit={hidden.exit_code} "
        f"vis_has_secret={secret in vis_out} hid_has_secret={secret in hid_out}",
        flush=True,
    )
    assert visible.exit_code == 0, (
        f"visible prompt runner exit {visible.exit_code}; output={vis_out!r}"
    )
    assert hidden.exit_code == 0, (
        f"hidden prompt runner exit {hidden.exit_code}; output={hid_out!r}"
    )
    assert greeting in vis_out and greeting in hid_out
    assert mark in vis_out, (
        f"visible arm missing derived mark {mark!r}; output={vis_out!r}"
    )
    assert mark in hid_out, (
        f"hidden arm missing derived mark {mark!r}; output={hid_out!r}"
    )
    assert secret in vis_out, (
        f"visible prompt did not echo {secret!r}; output={vis_out!r}"
    )
    assert secret not in hid_out, (
        f"hidden prompt echoed {secret!r}; output={hid_out!r}"
    )


def test_confirmation_prompt_asks_twice_and_reasks_on_mismatch():
    greeting = _greeting()
    flag, dest = _opt()
    first = f"a-{uuid.uuid4().hex}"
    second = f"b-{uuid.uuid4().hex}"
    third = f"c-{uuid.uuid4().hex}"
    leaf = _str_leaf(greeting, flag, dest, prompt=True, confirmation_prompt=True)
    unknown = _unknown_flag()

    matched = _dispatch(leaf, [], stdin=f"{third}\n{third}\n")
    rematch = _dispatch(leaf, [], stdin=f"{first}\n{second}\n{third}\n{third}\n")
    one_eof = _dispatch(leaf, [], stdin=f"{first}\n")
    mismatch_eof = _dispatch(leaf, [], stdin=f"{first}\n{second}\n")
    usage = _dispatch(leaf, [unknown], stdin=f"{third}\n{third}\n")
    print(
        f"matched={matched.stdout_text!r} rematch={rematch.stdout_text!r} "
        f"one_eof={one_eof.exit_code} mismatch_eof={mismatch_eof.exit_code}",
        flush=True,
    )
    _require_str(matched, greeting, third)
    _require_str(rematch, greeting, third)
    rematch_field = labeled_stdout_field(rematch, "V:")
    assert rematch_field not in {first, second}, (
        f"rematch delivered a first-pair value {rematch_field!r}"
    )
    assert_abort_indication_unlike_usage(one_eof, usage, greeting, unknown, first)
    assert_abort_without_marker(mismatch_eof, greeting)


def test_password_option_accepts_matching_hidden_lines():
    greeting = _greeting()
    flag, dest = _opt()
    first = f"a-{uuid.uuid4().hex}"
    second = f"b-{uuid.uuid4().hex}"
    secret = f"c-{uuid.uuid4().hex}"
    salt = f"sal-{uuid.uuid4().hex}"
    mark = _secret_mark(secret, salt)
    unknown = _unknown_flag()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(mark if kwargs[dest] == secret else "K:0", flush=True)
        print(f"SALT:{salt}", flush=True)

    leaf = _cmd(callback, password_option(flag, dest))
    matched = _runner_dispatch(leaf, [], stdin=f"{secret}\n{secret}\n")
    rematch = _runner_dispatch(
        leaf, [], stdin=f"{first}\n{second}\n{secret}\n{secret}\n"
    )
    one_eof = _runner_dispatch(leaf, [], stdin=f"{secret}\n")
    usage = _runner_dispatch(leaf, [unknown], stdin=f"{secret}\n{secret}\n")
    print(
        f"matched={matched.stdout_text!r} rematch={rematch.stdout_text!r} "
        f"one_eof={one_eof.exit_code}",
        flush=True,
    )
    assert_success_marker_present(matched, greeting)
    assert mark in _stdout(matched), (
        f"matching password missing derived mark {mark!r}; "
        f"stdout={matched.stdout_text!r}"
    )
    assert_success_marker_present(rematch, greeting)
    assert mark in _stdout(rematch), (
        f"rematch password missing derived mark {mark!r}; "
        f"stdout={rematch.stdout_text!r}"
    )
    assert_abort_indication_unlike_usage(one_eof, usage, greeting, unknown, secret)

    runner = CliRunner()
    captured = runner.invoke(leaf, [], input=f"{secret}\n{secret}\n")
    out = _runner_output(captured)
    print(
        f"runner_exit={captured.exit_code} secret_in_out={secret in out}",
        flush=True,
    )
    assert captured.exit_code == 0, (
        f"password runner exit {captured.exit_code}; output={out!r}"
    )
    assert greeting in out and mark in out
    assert secret not in out, (
        f"password option echoed {secret!r} into runner capture; "
        f"output={out!r}"
    )


# ---------------------------------------------------------------------------
# H. Confirmation option
# ---------------------------------------------------------------------------


def test_confirmation_option_yes_flag_skips_question():
    greeting = _greeting()

    def callback() -> None:
        print(greeting, flush=True)

    leaf = _cmd(callback, confirmation_option())
    declined = _dispatch(leaf, [], stdin="no\n")
    empty = _dispatch(leaf, ["--yes"], stdin="")
    hanging = _dispatch(leaf, ["--yes"], stdin="no\n")
    print(
        f"declined={declined.exit_code} empty={empty.stdout_text!r} "
        f"hanging={hanging.stdout_text!r}",
        flush=True,
    )
    assert_abort_without_marker(declined, greeting)
    assert_success_marker_present(empty, greeting)
    assert_success_marker_present(hanging, greeting)


def test_confirmation_option_omit_and_decline_aborts_without_callback():
    greeting = _greeting()
    unknown = _unknown_flag()

    def callback() -> None:
        print(greeting, flush=True)

    leaf = _cmd(callback, confirmation_option())
    declined = _dispatch(leaf, [], stdin="no\n")
    usage = _dispatch(leaf, [unknown], stdin="yes\n")
    print(
        f"declined={declined.exit_code}/{declined.stderr_text!r} "
        f"usage={usage.exit_code}/{usage.stderr_text!r}",
        flush=True,
    )
    assert_abort_indication_unlike_usage(
        declined, usage, greeting, unknown, "--yes"
    )


def test_confirmation_option_omit_and_accept_runs_callback():
    greeting = _greeting()

    def callback() -> None:
        print(greeting, flush=True)

    leaf = _cmd(callback, confirmation_option())
    accepted = _dispatch(leaf, [], stdin="yes\n")
    print(f"accepted={accepted.stdout_text!r}", flush=True)
    assert_success_marker_present(accepted, greeting)


def test_confirmation_option_eof_is_abort():
    greeting = _greeting()
    unknown = _unknown_flag()

    def callback() -> None:
        print(greeting, flush=True)

    leaf = _cmd(callback, confirmation_option())
    eof = _dispatch(leaf, [], stdin="")
    usage = _dispatch(leaf, [unknown])
    print(f"eof={eof.exit_code}/{eof.stderr_text!r}", flush=True)
    assert_abort_indication_unlike_usage(eof, usage, greeting, unknown, "--yes")


def test_confirmation_option_custom_flag_name():
    greeting = _greeting()
    flag, _dest = _opt()

    def callback() -> None:
        print(greeting, flush=True)

    leaf = _cmd(callback, confirmation_option(flag))
    empty = _dispatch(leaf, [flag], stdin="")
    declined = _dispatch(leaf, [], stdin="no\n")
    print(
        f"custom_empty={empty.stdout_text!r} declined={declined.exit_code}",
        flush=True,
    )
    assert_success_marker_present(empty, greeting)
    assert_abort_without_marker(declined, greeting)


# ---------------------------------------------------------------------------
# I. Option prompt re-asks on conversion failure; EOF is abort
# ---------------------------------------------------------------------------


def test_option_prompt_reasks_on_conversion_failure():
    greeting = _greeting()
    flag, dest = _opt()
    legal = _runtime_int()
    extra = legal + 4
    illegal = unrelated_dispatch_token()
    leaf = _int_leaf(greeting, flag, dest, prompt=True)

    recovered = _dispatch(leaf, [], stdin=f"{illegal}\n{legal}\n")
    first_wins = _dispatch(leaf, [], stdin=f"{legal}\n{extra}\n")
    print(
        f"recovered={recovered.stdout_text!r} first_wins={first_wins.stdout_text!r}",
        flush=True,
    )
    _require_arith(recovered, greeting, legal)
    _require_arith(first_wins, greeting, legal)


def test_option_prompt_eof_after_invalid_is_abort_not_usage():
    greeting = _greeting()
    flag, dest = _opt()
    illegal = unrelated_dispatch_token()
    asked = _int_leaf(greeting, flag, dest, prompt=True)
    silent = _int_leaf(greeting, flag, dest)

    aborted = _dispatch(asked, [], stdin=f"{illegal}\n")
    usage = _dispatch(silent, [flag, illegal])
    print(
        f"aborted={aborted.exit_code}/{aborted.stderr_text!r} "
        f"usage={usage.exit_code}/{usage.stderr_text!r}",
        flush=True,
    )
    assert_abort_indication_unlike_usage(
        aborted, usage, greeting, flag, dest, illegal
    )
    require_usage_names_option(usage, greeting, flag)


# ---------------------------------------------------------------------------
# K. Combining deprecated with prompt is refused
# ---------------------------------------------------------------------------


def test_deprecated_plus_prompt_declaration_is_refused():
    greeting = _greeting()
    flag, dest = _opt()
    typed = f"typ-{uuid.uuid4().hex}"

    def combo():
        def callback(**kwargs) -> None:
            print(greeting, flush=True)
            _emit_str(kwargs[dest])

        return _cmd(callback, option(flag, dest, prompt=True, deprecated=True))

    refused = assert_declaration_refused(combo)
    print(f"combo_refused={refused!r}", flush=True)

    ok = _str_leaf(greeting, flag, dest, prompt=True)
    result = _dispatch(ok, [], stdin=f"{typed}\n")
    print(f"prompt_only={result.stdout_text!r}", flush=True)
    _require_str(result, greeting, typed)
