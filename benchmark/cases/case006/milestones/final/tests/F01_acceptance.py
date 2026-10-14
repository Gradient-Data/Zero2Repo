# feature: F01
"""Command declaration, naming, and invocation (FP-01).

Assertions stay at the PRD's precision: mapped or explicit invoked names,
callback-once with converted destinations, deprecation distinguishable from
ordinary output and from usage failure, standalone exit classes versus
integrator propagation, leftover tokens, and ASCII-locale non-abort.
Wording of warnings and help marks is not pinned.
"""

from __future__ import annotations

import codecs
import uuid

import pytest
from optlyn import INT, command, group, option

from _harness import invoke, product_src_dir, workspace
from _helpers import (
    assert_deprecation_distinct,
    assert_failure_propagates,
    assert_help_page_mark_unlike,
    assert_success_marker_present,
    assert_success_with_marker,
    assert_usage_class,
    assert_usage_names_option,
    default_invoked_name,
    help_page_remainder,
    marker_occurs,
    unrelated_dispatch_token,
)

PROG = "app"


def _word() -> str:
    return "k" + uuid.uuid4().hex[:8]


def _greeting() -> str:
    return f"GREET:{uuid.uuid4().hex}:"


def _runtime_int() -> int:
    return 14 + uuid.uuid4().int % 80


def _leaf(func_name: str, greeting: str, **command_kwargs):
    def callback() -> None:
        print(greeting, flush=True)

    callback.__name__ = func_name
    return command(**command_kwargs)(callback)


def _attach(leaf):
    @group()
    def root() -> None:
        return None

    root.add_command(leaf)
    return root


def _dispatch(cli, args, **kwargs):
    kwargs.setdefault("prog_name", PROG)
    return invoke(cli, args, **kwargs)


# ---------------------------------------------------------------------------
# A. Default name and explicit name
# ---------------------------------------------------------------------------


def test_underscore_name_invoked_with_dash():
    left, right, greeting = _word(), _word(), _greeting()
    func_name = f"{left}_{right}"
    mapped = default_invoked_name(func_name)
    print(f"func={func_name!r} mapped={mapped!r}", flush=True)
    leaf = _leaf(func_name, greeting)
    cli = _attach(leaf)

    assert_success_marker_present(_dispatch(cli, [mapped]), greeting)

    forbidden = (
        mapped,
        func_name,
        func_name.lower(),
        f"{left}-{right}",
        f"{left}_{right}",
    )
    other = unrelated_dispatch_token(*forbidden)
    print(f"unrelated={other!r}", flush=True)
    assert_usage_class(_dispatch(cli, [other]), greeting)


def test_function_name_lowercased_before_dash_mapping():
    left, right, greeting = _word(), _word(), _greeting()
    func_name = f"{left.capitalize()}_{right.capitalize()}"
    mapped = default_invoked_name(func_name)
    print(f"func={func_name!r} mapped={mapped!r}", flush=True)
    assert mapped == f"{left}-{right}"
    leaf = _leaf(func_name, greeting)
    cli = _attach(leaf)
    assert_success_marker_present(_dispatch(cli, [mapped]), greeting)

    other = unrelated_dispatch_token(mapped, func_name, f"{left}-{right}")
    assert_usage_class(_dispatch(cli, [other]), greeting)


@pytest.mark.parametrize("suffix", ["_command", "_cmd", "_group", "_grp"])
def test_trailing_command_suffix_stripped_from_invoked_name(suffix: str):
    left, right, greeting = _word(), _word(), _greeting()
    func_name = f"{left}_{right}{suffix}"
    mapped = default_invoked_name(func_name)
    print(f"func={func_name!r} suffix={suffix!r} mapped={mapped!r}", flush=True)
    assert mapped == f"{left}-{right}"
    leaf = _leaf(func_name, greeting)
    cli = _attach(leaf)
    assert_success_marker_present(_dispatch(cli, [mapped]), greeting)

    unstripped = f"{left}-{right}-{suffix.lstrip('_')}"
    other = unrelated_dispatch_token(
        mapped, func_name, unstripped, func_name.replace("_", "-")
    )
    assert_usage_class(_dispatch(cli, [other]), greeting)


def test_explicit_name_overrides_mapped_name():
    left, right, greeting = _word(), _word(), _greeting()
    func_name = f"{left}_{right}"
    explicit = f"exp-{uuid.uuid4().hex[:8]}"
    mapped = default_invoked_name(func_name)
    print(f"func={func_name!r} explicit={explicit!r} mapped={mapped!r}", flush=True)
    assert explicit != mapped
    leaf = _leaf(func_name, greeting, name=explicit)
    cli = _attach(leaf)
    assert_success_marker_present(_dispatch(cli, [explicit]), greeting)

    mapped_refused = _dispatch(cli, [mapped])
    print(
        f"mapped-token dispatch exit={mapped_refused.exit_code} "
        f"stderr={mapped_refused.stderr_text!r}",
        flush=True,
    )
    assert_usage_class(mapped_refused, greeting)

    other = unrelated_dispatch_token(explicit, mapped, func_name)
    assert_usage_class(_dispatch(cli, [other]), greeting)


# ---------------------------------------------------------------------------
# B. Valid invocation runs the callback with converted parameters
# ---------------------------------------------------------------------------


def test_valid_args_run_callback_once_exit_zero():
    greeting = _greeting()
    leaf = _leaf(f"{_word()}_{_word()}", greeting)
    result = _dispatch(leaf, [])
    assert_success_with_marker(result, greeting)
    print(f"stdout={result.stdout_text!r}", flush=True)


def test_greeting_absent_when_callback_does_not_run():
    greeting = _greeting()
    leaf = _leaf(f"{_word()}_{_word()}", greeting)
    assert_success_marker_present(_dispatch(leaf, []), greeting)
    unknown = f"--{unrelated_dispatch_token()}"
    print(f"unknown={unknown!r}", flush=True)
    assert_usage_class(_dispatch(leaf, [unknown]), greeting)


def test_parameterless_command_runs_on_empty_args():
    greeting = _greeting()
    leaf = _leaf(f"{_word()}_{_word()}", greeting)
    assert_success_marker_present(_dispatch(leaf, []), greeting)


def test_inferred_destination_receives_converted_value():
    greeting = _greeting()
    left, right = _word(), _word()
    dest = f"{left}_{right}"
    flag = f"--{left}-{right}"
    value = _runtime_int()
    expected = value * 3 + 7
    print(f"flag={flag} dest={dest} value={value} expected={expected}", flush=True)

    def callback(**kwargs) -> None:
        received = kwargs[dest]
        print(greeting, flush=True)
        print(f"T:{received * 3 + 7}", flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    decorated = option(flag, type=INT)(callback)
    leaf = command()(decorated)
    result = _dispatch(leaf, [f"{flag}={value}"])
    assert_success_marker_present(result, greeting)
    marker = f"T:{expected}"
    assert marker in result.stdout_text, (
        f"converted integer did not reach inferred destination {dest!r}; "
        f"stdout={result.stdout_text!r}"
    )


def test_declared_destination_receives_converted_value():
    greeting = _greeting()
    public_a, public_b = _word(), _word()
    dest = f"got_{_word()}"
    flag = f"--{public_a}-{public_b}"
    value = _runtime_int()
    expected = value * 3 + 7
    print(f"flag={flag} dest={dest} value={value}", flush=True)

    def callback(**kwargs) -> None:
        received = kwargs[dest]
        print(greeting, flush=True)
        print(f"T:{received * 3 + 7}", flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    decorated = option(flag, dest, type=INT)(callback)
    leaf = command()(decorated)
    result = _dispatch(leaf, [f"{flag}={value}"])
    assert_success_marker_present(result, greeting)
    marker = f"T:{expected}"
    assert marker in result.stdout_text, (
        f"converted integer did not reach declared destination {dest!r}; "
        f"stdout={result.stdout_text!r}"
    )
    inferred = f"{public_a}_{public_b}"
    assert inferred != dest


def test_script_program_invocation_runs_callback():
    greeting = _greeting()
    left, right = _word(), _word()
    dest = f"{left}_{right}"
    flag = f"--{left}-{right}"
    value = _runtime_int()
    expected = value * 3 + 7
    script = (
        "from optlyn import INT, command, option\n"
        "\n"
        f"@command()\n"
        f"@option({flag!r}, type=INT)\n"
        f"def cli({dest}):\n"
        f"    print({greeting!r}, flush=True)\n"
        f"    print('T:' + str({dest} * 3 + 7), flush=True)\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    cli.main()\n"
    )
    with workspace() as ws:
        path = ws.write("prog.py", script)
        result = ws.run_python(argv=[str(path), f"{flag}={value}"])
    print(f"script exit={result.returncode} stdout={result.stdout_text!r}", flush=True)
    assert_success_marker_present(result, greeting)
    assert marker_occurs(result.stdout_text, f"T:{expected}"), (
        f"script program entry did not deliver converted {value}; "
        f"stdout={result.stdout_text!r} stderr={result.stderr_text!r}"
    )


# ---------------------------------------------------------------------------
# C. Deprecated commands still run; warning is distinguishable
# ---------------------------------------------------------------------------


def test_deprecated_command_still_runs_and_exits_zero():
    greeting = _greeting()
    leaf = _leaf(f"{_word()}_{_word()}", greeting, deprecated=True)
    assert_success_marker_present(_dispatch(leaf, []), greeting)


def test_deprecation_warning_distinct_from_greeting_and_usage_failure():
    greeting = _greeting()
    func_name = f"{_word()}_{_word()}"
    deprecated = _leaf(func_name, greeting, deprecated=True)
    baseline = _leaf(func_name, greeting, deprecated=False)
    dep_result = _dispatch(deprecated, [])
    base_result = _dispatch(baseline, [])
    assert_deprecation_distinct(dep_result, base_result, greeting)

    unknown = f"--{unrelated_dispatch_token()}"
    usage = _dispatch(deprecated, [unknown])
    assert_usage_class(usage, greeting)
    print(
        f"deprecated exit={dep_result.exit_code} usage exit={usage.exit_code}",
        flush=True,
    )


def test_custom_deprecation_note_appears_in_warning():
    greeting = _greeting()
    note = f"retire-{uuid.uuid4().hex}"
    func_name = f"{_word()}_{_word()}"
    deprecated = _leaf(func_name, greeting, deprecated=note)
    baseline = _leaf(func_name, greeting, deprecated=False)
    print(f"note={note!r}", flush=True)
    assert_deprecation_distinct(
        _dispatch(deprecated, []),
        _dispatch(baseline, []),
        greeting,
        note=note,
    )


def test_help_marks_deprecated_unlike_nondeprecated_twin():
    greeting = _greeting()
    explicit = f"exp-{uuid.uuid4().hex[:8]}"
    description = f"Describe {uuid.uuid4().hex} path."
    func_name = f"{_word()}_{_word()}"

    def _twin(*, deprecated: bool):
        def callback() -> None:
            print(greeting, flush=True)

        callback.__name__ = func_name
        callback.__doc__ = description
        return command(name=explicit, deprecated=deprecated)(callback)

    deprecated = _twin(deprecated=True)
    baseline = _twin(deprecated=False)
    dep_help = _dispatch(deprecated, ["--help"], prog_name=explicit)
    base_help = _dispatch(baseline, ["--help"], prog_name=explicit)
    print(
        f"base_help exit={base_help.exit_code} stdout={base_help.stdout_text!r}",
        flush=True,
    )
    print(
        f"dep_help exit={dep_help.exit_code} stdout={dep_help.stdout_text!r}",
        flush=True,
    )
    assert base_help.exit_code == 0, (
        f"non-deprecated help expected success, got {base_help.exit_code}; "
        f"stderr={base_help.stderr_text!r}"
    )
    assert description in base_help.stdout_text, (
        f"non-deprecated help is not a live help page; missing {description!r}; "
        f"stdout={base_help.stdout_text!r}"
    )
    assert greeting not in base_help.stdout_text, (
        f"non-deprecated --help ran the callback; stdout={base_help.stdout_text!r}"
    )
    assert dep_help.exit_code == 0, (
        f"deprecated help expected success, got {dep_help.exit_code}; "
        f"stderr={dep_help.stderr_text!r}"
    )
    assert description in dep_help.stdout_text, (
        f"deprecated help is not a live help page; missing {description!r}; "
        f"stdout={dep_help.stdout_text!r}"
    )
    assert greeting not in dep_help.stdout_text, (
        f"deprecated --help ran the callback; stdout={dep_help.stdout_text!r}"
    )
    dep_rest = help_page_remainder(dep_help, explicit, description)
    base_rest = help_page_remainder(base_help, explicit, description)
    print(
        f"help-page stdout remainder dep={dep_rest!r} base={base_rest!r} "
        f"dep_stderr={dep_help.stderr_text!r} "
        f"dep_warning_count={len(dep_help.warnings)}",
        flush=True,
    )
    assert_help_page_mark_unlike(dep_help, base_help, explicit, description)


# ---------------------------------------------------------------------------
# D. Standalone program exit versus disabled standalone mode
# ---------------------------------------------------------------------------


def test_standalone_success_exits_zero_and_discards_return_value():
    greeting = _greeting()
    unique = f"rv-{uuid.uuid4().hex}"

    def callback() -> str:
        print(greeting, flush=True)
        return unique

    callback.__name__ = f"{_word()}_{_word()}"
    leaf = command()(callback)
    standalone = _dispatch(leaf, [], standalone_mode=True)
    assert_success_marker_present(standalone, greeting)
    assert standalone.return_value != unique, (
        f"standalone mode leaked the callback return {standalone.return_value!r}"
    )
    print(f"standalone return={standalone.return_value!r}", flush=True)


def test_non_standalone_success_returns_callback_value():
    greeting = _greeting()
    unique = f"rv-{uuid.uuid4().hex}"

    def callback() -> str:
        print(greeting, flush=True)
        return unique

    callback.__name__ = f"{_word()}_{_word()}"
    leaf = command()(callback)
    result = _dispatch(leaf, [], standalone_mode=True)
    assert_success_marker_present(result, greeting)
    assert result.return_value != unique

    integrated = _dispatch(leaf, [], standalone_mode=False)
    assert_success_marker_present(integrated, greeting)
    assert integrated.return_value == unique, (
        f"disabled standalone mode did not return callback value; "
        f"got {integrated.return_value!r}"
    )
    print(f"integrated return={integrated.return_value!r}", flush=True)


def test_standalone_usage_error_exits_class_two():
    greeting = _greeting()
    leaf = _leaf(f"{_word()}_{_word()}", greeting)
    unknown = f"--{unrelated_dispatch_token()}"
    result = _dispatch(leaf, [unknown], standalone_mode=True)
    assert_usage_class(result, greeting)


def test_non_standalone_failure_propagates_to_caller():
    greeting = _greeting()
    leaf = _leaf(f"{_word()}_{_word()}", greeting)
    unknown = f"--{unrelated_dispatch_token()}"
    assert_usage_class(
        _dispatch(leaf, [unknown], standalone_mode=True),
        greeting,
    )
    exc = assert_failure_propagates(
        lambda: _dispatch(leaf, [unknown], standalone_mode=False)
    )
    print(f"propagated {type(exc).__name__}: {exc}", flush=True)


# ---------------------------------------------------------------------------
# E. Usage failures do not run the callback; leftover tokens
# ---------------------------------------------------------------------------


def test_unknown_option_does_not_run_callback():
    greeting = _greeting()
    leaf = _leaf(f"{_word()}_{_word()}", greeting)
    unknown = f"--{unrelated_dispatch_token()}"
    assert_usage_class(_dispatch(leaf, [unknown]), greeting)


def test_missing_required_parameter_does_not_run_callback():
    greeting = _greeting()
    flag = f"--{_word()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    decorated = option(flag, required=True)(callback)
    leaf = command()(decorated)
    omitted = _dispatch(leaf, [])
    print(f"omitted flag={flag!r} stderr={omitted.stderr_text!r}", flush=True)
    assert_usage_class(omitted, greeting)
    assert_usage_names_option(omitted, greeting, flag)
    assert_success_marker_present(_dispatch(leaf, [flag, "x"]), greeting)


def test_conversion_failure_does_not_run_callback():
    greeting = _greeting()
    flag = f"--{_word()}"

    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    decorated = option(flag, type=INT)(callback)
    leaf = command()(decorated)
    bad = _dispatch(leaf, [f"{flag}=not-a-number"])
    print(f"bad-convert flag={flag!r} stderr={bad.stderr_text!r}", flush=True)
    assert_usage_class(bad, greeting)
    assert_usage_names_option(bad, greeting, flag)
    value = _runtime_int()
    assert_success_marker_present(_dispatch(leaf, [f"{flag}={value}"]), greeting)


def test_leftover_tokens_fail_unless_extra_arguments_allowed():
    greeting = _greeting()
    leftover = f"extra-{uuid.uuid4().hex[:8]}"
    refused = _leaf(f"{_word()}_{_word()}", greeting)
    assert_usage_class(_dispatch(refused, [leftover]), greeting)

    def callback() -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    allowed = command(context_settings={"allow_extra_args": True})(callback)
    assert_success_marker_present(_dispatch(allowed, [leftover]), greeting)
    print(f"leftover={leftover!r} allowed", flush=True)


# ---------------------------------------------------------------------------
# F. ASCII-only environment encoding does not abort
# ---------------------------------------------------------------------------


def _encoding_report(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("ENCREPORT:"):
            return line.split(":", 1)[1]
    raise AssertionError(f"child did not report environment encoding: {text!r}")


def _canonical_encoding(name: str) -> str:
    try:
        return codecs.lookup(name).name
    except LookupError as exc:
        raise AssertionError(
            f"child reported unknown encoding {name!r}"
        ) from exc


def test_ascii_environment_encoding_does_not_abort():
    greeting = "GREETASCII"
    left, right = _word(), _word()
    dest = f"{left}_{right}"
    flag = f"--{left}-{right}"
    value = _runtime_int()
    expected = value * 3 + 7
    script = (
        "import codecs\n"
        "import locale\n"
        "import sys\n"
        "enc = locale.getpreferredencoding(False)\n"
        "try:\n"
        "    name = codecs.lookup(enc).name\n"
        "except LookupError:\n"
        "    name = str(enc)\n"
        "print('ENCREPORT:' + name, flush=True)\n"
        "print('UTF8MODE:' + str(int(sys.flags.utf8_mode)), flush=True)\n"
        "from optlyn import INT, command, option\n"
        "\n"
        f"@command()\n"
        f"@option({flag!r}, type=INT)\n"
        f"def cli({dest}):\n"
        f"    print({greeting!r}, flush=True)\n"
        f"    print('T:' + str({dest} * 3 + 7), flush=True)\n"
        "\n"
        "cli.main()\n"
    )
    with workspace() as ws:
        path = ws.write("prog.py", script)
        unicode_run = ws.run_python(argv=[str(path), f"{flag}={value}"])
        print(
            f"unicode enc={_encoding_report(unicode_run.stdout_text)!r} "
            f"exit={unicode_run.returncode}",
            flush=True,
        )
        assert_success_marker_present(unicode_run, greeting)
        assert marker_occurs(unicode_run.stdout_text, f"T:{expected}")

        ascii_run = ws.run_python(
            argv=["-X", "utf8=0", str(path), f"{flag}={value}"],
            env={
                "LC_ALL": "C",
                "LANG": "C",
                "LC_CTYPE": "C",
                "PYTHONUTF8": "0",
                "PYTHONCOERCECLOCALE": "0",
            },
        )
    reported = _encoding_report(ascii_run.stdout_text)
    canonical = _canonical_encoding(reported)
    print(
        f"ascii enc={reported!r} canonical={canonical!r} "
        f"exit={ascii_run.returncode} stdout={ascii_run.stdout_text!r}",
        flush=True,
    )
    assert canonical == "ascii", (
        "child interpreter did not report an ASCII-only environment encoding; "
        f"got {reported!r} (canonical {canonical!r}); "
        f"stdout={ascii_run.stdout_text!r} stderr={ascii_run.stderr_text!r}"
    )
    assert_success_marker_present(ascii_run, greeting)
    assert marker_occurs(ascii_run.stdout_text, f"T:{expected}"), (
        f"ASCII locale run lost the converted marker; "
        f"stdout={ascii_run.stdout_text!r} stderr={ascii_run.stderr_text!r}"
    )


# ---------------------------------------------------------------------------
# G. Negative control: package not importable
# ---------------------------------------------------------------------------


def test_invocation_fails_when_package_not_importable():
    greeting = _greeting()
    script = (
        "from optlyn import command\n"
        "\n"
        "@command()\n"
        "def cli():\n"
        f"    print({greeting!r}, flush=True)\n"
        "\n"
        "cli.main()\n"
    )
    with workspace() as ws:
        path = ws.write("prog.py", script)
        src = product_src_dir()
        present = ws.run_python(
            argv=["-S", str(path)],
            env={"PYTHONPATH": str(src)},
        )
        assert_success_marker_present(present, greeting)

        empty = ws.resolve("no-pkgs")
        empty.mkdir()
        absent = ws.run_python(
            argv=["-S", str(path)],
            env={"PYTHONPATH": str(empty)},
        )
    print(
        f"absent exit={absent.returncode} stderr={absent.stderr_text!r}",
        flush=True,
    )
    assert absent.returncode != 0, (
        "invocation succeeded while the package was not importable; "
        f"stdout={absent.stdout_text!r} stderr={absent.stderr_text!r}"
    )
    assert greeting not in absent.stdout_text, (
        f"callback marker present without an importable package; "
        f"stdout={absent.stdout_text!r}"
    )
