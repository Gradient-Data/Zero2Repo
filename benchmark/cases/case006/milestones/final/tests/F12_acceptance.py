# feature: F12
"""Shell completion (FP-12).

Assertions stay at the PRD's precision: the FP-12 complete-variable name,
the four built-in shells' source and complete instructions, suggestion
rules (visible names, dash-gated options including --help, choice prefix,
file/path carrying the incomplete token, directories-only distinguishable
from file and all-path complete), author/type completers, Zsh/Fish
help next to a value, match-nothing is not a usage error, and an
unrecognized instruction is neither a successful source nor a successful
complete. Registration-script syntax, frame separators, exception types,
and ``file``/``dir`` protocol tokens are not pinned.
"""

from __future__ import annotations

import importlib
import uuid
from typing import Sequence

from optlyn import (
    INT,
    STRING,
    Choice,
    File,
    ParamType,
    Path as PathType,
    argument,
    command,
    group,
    option,
)
from F06_helpers import _LookupGroup, _on_path, _write_leaf_module

from _harness import invoke, workspace
from _helpers import (
    assert_callback_skipped,
    assert_intentional_help,
    assert_not_usage_class,
    assert_success_marker_present,
    assert_usage_class,
    complete_variable_name,
    completion_instruction_env,
    completion_line_env,
    completion_stream_remainder,
    import_trace_present,
    require_usage_names_option,
)

SHELLS = ("bash", "zsh", "fish", "powershell")


def _word() -> str:
    return "k" + uuid.uuid4().hex[:8]


def _greeting() -> str:
    return f"GREET:{uuid.uuid4().hex}:"


def _desc(prefix: str = "D") -> str:
    return f"{prefix}{uuid.uuid4().hex}path."


def _exe() -> str:
    return f"{_word()}-{_word()}"


def _source(cli, exe: str, shell: str = "bash"):
    return invoke(
        cli,
        [],
        env=completion_instruction_env(exe, f"{shell}_source"),
        prog_name=exe,
    )


def _complete(
    cli,
    exe: str,
    shell: str = "bash",
    completed: Sequence[str] = (),
    incomplete: str = "",
):
    return invoke(
        cli,
        [],
        env=completion_line_env(shell, exe, completed, incomplete),
        prog_name=exe,
    )


def _run(cli, args, exe: str, env=None):
    return invoke(cli, args, env=env, prog_name=exe)


def _leaf(greeting: str, *decorators, doc: str | None = None, **command_kwargs):
    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        for key, value in kwargs.items():
            if value is not None:
                print(f"P:{key}:{value}", flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    if doc is not None:
        callback.__doc__ = doc
    fn = callback
    for dec in reversed(decorators):
        fn = dec(fn)
    return command(**command_kwargs)(fn)


def _root(
    greeting: str,
    *decorators,
    doc: str | None = None,
    invoke_without_command: bool = True,
    **group_kwargs,
):
    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    if doc is not None:
        callback.__doc__ = doc
    fn = callback
    for dec in reversed(decorators):
        fn = dec(fn)
    return group(
        invoke_without_command=invoke_without_command, **group_kwargs
    )(fn)


class _Suggest:
    """Declaration-side suggestion fixture. Not an output oracle."""

    def __init__(self, value: str, help: str | None = None) -> None:
        self.value = value
        self.help = help
        self.type = "plain"


class _MarkedCompleteType(ParamType):
    name = "markedc"

    def __init__(self, mark: str) -> None:
        self.mark = mark

    def convert(self, value, param=None, ctx=None):
        return value

    def shell_complete(self, ctx, param, incomplete):
        return [_Suggest(self.mark)]


def _require_name(stream: str, name: str, *, present: bool) -> None:
    if present:
        assert name in stream, (
            f"expected {name!r} in suggestion stream; stream={stream!r}"
        )
    else:
        assert name not in stream, (
            f"unexpected {name!r} in suggestion stream; stream={stream!r}"
        )


# ---------------------------------------------------------------------------
# A. Entry variable, install form, ignore (FP-12)
# ---------------------------------------------------------------------------


def test_matching_complete_variable_enters_source_mode():
    greeting = _greeting()
    exe = _exe()
    assert "-" in exe
    cli = _leaf(greeting)
    sourced = _source(cli, exe, "bash")
    baseline = _run(cli, [], exe)
    print(
        f"exe={exe!r} source_exit={sourced.exit_code} "
        f"source_stdout={sourced.stdout_text!r} "
        f"baseline_stdout={baseline.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(baseline, greeting)
    assert_callback_skipped(sourced, greeting)
    assert sourced.stdout_text.strip(), (
        f"bash_source produced empty stdout; stderr={sourced.stderr_text!r}"
    )


def test_wrong_complete_variable_name_runs_command():
    greeting = _greeting()
    exe = _exe()
    cli = _leaf(greeting)
    matching = complete_variable_name(exe)
    dashed = f"_{exe.upper()}_COMPLETE"
    assert dashed != matching
    wrong = _run(cli, [], exe, env={dashed: "bash_source"})
    sourced = _source(cli, exe, "bash")
    print(
        f"matching={matching!r} dashed={dashed!r} "
        f"wrong_stdout={wrong.stdout_text!r} "
        f"source_stdout={sourced.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(wrong, greeting)
    assert_callback_skipped(sourced, greeting)
    wrong_rest = completion_stream_remainder(wrong, exe, matching, dashed)
    source_rest = completion_stream_remainder(sourced, exe, matching, dashed)
    assert wrong_rest != source_rest, (
        "wrong-name run is not distinct from matching bash_source; "
        f"wrong={wrong_rest!r} source={source_rest!r}"
    )


def test_python_script_run_ignores_installed_complete_variable():
    greeting = _greeting()
    installed = _exe()
    var = complete_variable_name(installed)
    script = (
        "from optlyn import command\n"
        "\n"
        "@command()\n"
        "def cli():\n"
        f"    print({greeting!r}, flush=True)\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    cli.main()\n"
    )
    with workspace() as ws:
        path = ws.write(f"zxq{_word()}.py", script)
        python_run = ws.run_python(
            argv=[str(path)],
            env={var: "bash_source"},
        )
        cli = _leaf(greeting)
        installed_source = ws.invoke(
            cli,
            [],
            env={var: "bash_source"},
            prog_name=installed,
        )
    print(
        f"installed={installed!r} var={var!r} "
        f"python_stdout={python_run.stdout_text!r} "
        f"invoke_stdout={installed_source.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(python_run, greeting)
    assert_callback_skipped(installed_source, greeting)
    assert installed_source.stdout_text.strip(), (
        "matching invoke bash_source produced empty stdout; "
        f"stderr={installed_source.stderr_text!r}"
    )
    py_rest = completion_stream_remainder(python_run, installed, var, greeting)
    src_rest = completion_stream_remainder(
        installed_source, installed, var, greeting
    )
    assert py_rest != src_rest, (
        "python-script run with the installed complete variable is not "
        "distinct from a matching invoke source run; "
        f"python={py_rest!r} source={src_rest!r}"
    )


# ---------------------------------------------------------------------------
# B. Four source modes: shell-specific script, not command output
# ---------------------------------------------------------------------------


def test_bash_source_prints_script_skips_callback():
    greeting = _greeting()
    exe = _exe()
    cli = _leaf(greeting)
    sourced = _source(cli, exe, "bash")
    live = _run(cli, [], exe)
    print(
        f"bash_source stdout={sourced.stdout_text!r} "
        f"live stdout={live.stdout_text!r} "
        f"stderr={sourced.stderr_text!r}",
        flush=True,
    )
    assert_success_marker_present(live, greeting)
    assert_callback_skipped(sourced, greeting)
    assert sourced.stdout_text.strip(), (
        f"bash_source produced empty stdout; stderr={sourced.stderr_text!r}"
    )
    live_rest = completion_stream_remainder(live, exe, greeting)
    source_rest = completion_stream_remainder(sourced, exe, greeting)
    assert source_rest != live_rest, (
        "bash_source is not distinct from a live unset-variable run of the "
        f"same command; source={source_rest!r} live={live_rest!r}"
    )


def test_four_source_modes_are_shell_specific():
    greeting = _greeting()
    exe = _exe()
    var = complete_variable_name(exe)
    cli = _leaf(greeting)
    source_instructions = tuple(f"{shell}_source" for shell in SHELLS)
    results = {shell: _source(cli, exe, shell) for shell in SHELLS}
    remainders = {
        shell: completion_stream_remainder(
            result, exe, var, *source_instructions
        )
        for shell, result in results.items()
    }
    preview = {shell: remainder[:80] for shell, remainder in remainders.items()}
    print(f"exe={exe!r} remainders={preview!r}", flush=True)
    for shell, result in results.items():
        assert_callback_skipped(result, greeting)
        assert remainders[shell].strip() or result.stdout_text.strip(), (
            f"{shell}_source produced empty stdout; "
            f"stderr={result.stderr_text!r}"
        )
    names = list(SHELLS)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            assert remainders[left] != remainders[right], (
                f"{left}_source and {right}_source are not distinct after "
                f"stripping executable, variable name, and source "
                f"instruction strings {source_instructions!r}; "
                f"left={remainders[left]!r} right={remainders[right]!r}"
            )


def test_source_mode_is_not_the_help_page():
    greeting = _greeting()
    desc = _desc("S")
    exe = _exe()
    cli = _leaf(greeting, doc=desc)
    helped = _run(cli, ["--help"], exe)
    sourced = _source(cli, exe, "bash")
    print(
        f"help={helped.stdout_text!r} source={sourced.stdout_text!r}",
        flush=True,
    )
    assert_intentional_help(helped, greeting, desc)
    assert_callback_skipped(sourced, greeting)
    assert desc not in sourced.stdout_text, (
        f"source mode contained the help-page description {desc!r}; "
        f"stdout={sourced.stdout_text!r}"
    )


# ---------------------------------------------------------------------------
# C. Four complete modes: read the incomplete line, write suggestions
# ---------------------------------------------------------------------------


def test_bash_complete_at_group_prints_suggestions_skips_callback():
    greeting = _greeting()
    exe = _exe()
    vis_a = f"va{_word()}"
    vis_b = f"zb{_word()}"
    cli = _root(greeting)
    cli.add_command(_leaf(_greeting(), name=vis_a))
    cli.add_command(_leaf(_greeting(), name=vis_b))
    completed = _complete(cli, exe, "bash")
    baseline = _run(cli, [], exe)
    print(
        f"complete={completed.stdout_text!r} baseline={baseline.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(baseline, greeting)
    assert_callback_skipped(completed, greeting)
    _require_name(completed.stdout_text, vis_a, present=True)
    _require_name(completed.stdout_text, vis_b, present=True)


def test_complete_stream_unlike_source_and_unlike_normal_run():
    greeting = _greeting()
    exe = _exe()
    var = complete_variable_name(exe)
    vis_a = f"va{_word()}"
    vis_b = f"zb{_word()}"
    cli = _root(greeting)
    cli.add_command(_leaf(_greeting(), name=vis_a))
    cli.add_command(_leaf(_greeting(), name=vis_b))
    normal = _run(cli, [], exe)
    sourced = _source(cli, exe, "bash")
    completed = _complete(cli, exe, "bash")
    print(
        f"normal={normal.stdout_text!r} source={sourced.stdout_text!r} "
        f"complete={completed.stdout_text!r}",
        flush=True,
    )
    assert_success_marker_present(normal, greeting)
    assert_callback_skipped(sourced, greeting)
    assert_callback_skipped(completed, greeting)
    _require_name(completed.stdout_text, vis_a, present=True)
    source_rest = completion_stream_remainder(
        sourced, exe, var, "bash_source", "bash_complete"
    )
    complete_rest = completion_stream_remainder(
        completed, exe, var, "bash_source", "bash_complete"
    )
    assert source_rest != complete_rest, (
        "source and complete remainders are not distinct after stripping "
        f"executable, variable, and instruction strings; "
        f"source={source_rest!r} complete={complete_rest!r}"
    )


def test_four_complete_modes_all_suggest_visible_subcommand_names():
    greeting = _greeting()
    exe = _exe()
    vis_a = f"va{_word()}"
    vis_b = f"zb{_word()}"
    cli = _root(greeting)
    cli.add_command(_leaf(_greeting(), name=vis_a))
    cli.add_command(_leaf(_greeting(), name=vis_b))
    for shell in SHELLS:
        result = _complete(cli, exe, shell)
        print(
            f"{shell}_complete stdout={result.stdout_text!r}",
            flush=True,
        )
        assert_callback_skipped(result, greeting)
        _require_name(result.stdout_text, vis_a, present=True)
        _require_name(result.stdout_text, vis_b, present=True)


def test_four_complete_modes_honour_nonempty_prefix():
    greeting = _greeting()
    exe = _exe()
    vis_a = f"va{_word()}"
    vis_b = f"zb{_word()}"
    prefix = vis_a[:3]
    assert not vis_b.startswith(prefix)
    cli = _root(greeting)
    cli.add_command(_leaf(_greeting(), name=vis_a))
    cli.add_command(_leaf(_greeting(), name=vis_b))
    for shell in SHELLS:
        result = _complete(cli, exe, shell, incomplete=prefix)
        print(
            f"{shell} prefix={prefix!r} stdout={result.stdout_text!r}",
            flush=True,
        )
        assert_callback_skipped(result, greeting)
        _require_name(result.stdout_text, vis_a, present=True)
        _require_name(result.stdout_text, vis_b, present=False)


# ---------------------------------------------------------------------------
# D. Subcommand suggestions, nesting, prefix, hidden, custom groups
# ---------------------------------------------------------------------------


def test_empty_token_lists_visible_subcommands_not_hidden():
    greeting = _greeting()
    exe = _exe()
    vis_a = f"va{_word()}"
    vis_b = f"zb{_word()}"
    hidden = f"hd{_word()}"
    cli = _root(greeting)
    cli.add_command(_leaf(_greeting(), name=vis_a))
    cli.add_command(_leaf(_greeting(), name=vis_b))
    cli.add_command(_leaf(_greeting(), name=hidden, hidden=True))
    result = _complete(cli, exe, "bash")
    print(f"empty-token stdout={result.stdout_text!r}", flush=True)
    assert_callback_skipped(result, greeting)
    _require_name(result.stdout_text, vis_a, present=True)
    _require_name(result.stdout_text, vis_b, present=True)
    _require_name(result.stdout_text, hidden, present=False)


def test_hidden_command_not_suggested_even_as_full_token():
    greeting = _greeting()
    exe = _exe()
    vis = f"va{_word()}"
    hidden = f"hd{_word()}"
    cli = _root(greeting)
    cli.add_command(_leaf(_greeting(), name=vis))
    cli.add_command(_leaf(_greeting(), name=hidden, hidden=True))
    empty = _complete(cli, exe, "bash")
    full = _complete(cli, exe, "bash", incomplete=hidden)
    print(
        f"empty={empty.stdout_text!r} full={full.stdout_text!r}",
        flush=True,
    )
    _require_name(empty.stdout_text, vis, present=True)
    _require_name(empty.stdout_text, hidden, present=False)
    assert_callback_skipped(full, greeting)
    _require_name(full.stdout_text, hidden, present=False)


def test_subcommand_prefix_excludes_nonmatching_sibling():
    greeting = _greeting()
    exe = _exe()
    vis_a = f"va{_word()}"
    vis_b = f"zb{_word()}"
    prefix = vis_a[:3]
    assert not vis_b.startswith(prefix)
    cli = _root(greeting)
    cli.add_command(_leaf(_greeting(), name=vis_a))
    cli.add_command(_leaf(_greeting(), name=vis_b))
    result = _complete(cli, exe, "bash", incomplete=prefix)
    print(f"prefix={prefix!r} stdout={result.stdout_text!r}", flush=True)
    assert_callback_skipped(result, greeting)
    _require_name(result.stdout_text, vis_a, present=True)
    _require_name(result.stdout_text, vis_b, present=False)


def test_nested_group_completes_immediate_child_not_grandchild():
    greeting = _greeting()
    exe = _exe()
    child = f"ch{_word()}"
    uncle = f"un{_word()}"
    grand = f"gd{_word()}"
    parent = _root(greeting)
    mid = _root(_greeting(), invoke_without_command=True)
    mid.add_command(_leaf(_greeting(), name=grand))
    parent.add_command(mid, name=child)
    parent.add_command(_leaf(_greeting(), name=uncle))
    at_parent = _complete(parent, exe, "bash")
    at_child = _complete(parent, exe, "bash", completed=(child,))
    print(
        f"parent={at_parent.stdout_text!r} child={at_child.stdout_text!r}",
        flush=True,
    )
    assert_callback_skipped(at_parent, greeting)
    _require_name(at_parent.stdout_text, child, present=True)
    _require_name(at_parent.stdout_text, uncle, present=True)
    _require_name(at_parent.stdout_text, grand, present=False)
    assert_callback_skipped(at_child, greeting)
    _require_name(at_child.stdout_text, grand, present=True)
    _require_name(at_child.stdout_text, uncle, present=False)


def test_hidden_command_still_runs_when_fully_typed():
    greeting = _greeting()
    hidden_hi = _greeting()
    exe = _exe()
    vis = f"va{_word()}"
    hidden = f"hd{_word()}"
    cli = _root(greeting)
    cli.add_command(_leaf(_greeting(), name=vis))
    cli.add_command(_leaf(hidden_hi, name=hidden, hidden=True))
    omitted = _complete(cli, exe, "bash")
    ran = _run(cli, [hidden], exe)
    print(
        f"omitted={omitted.stdout_text!r} ran={ran.stdout_text!r}",
        flush=True,
    )
    assert_callback_skipped(omitted, greeting)
    _require_name(omitted.stdout_text, vis, present=True)
    _require_name(omitted.stdout_text, hidden, present=False)
    assert_success_marker_present(ran, hidden_hi)
    assert_success_marker_present(ran, greeting)
    assert ran.stdout_text.find(greeting) < ran.stdout_text.find(hidden_hi), (
        "group callback did not run before the hidden child; "
        f"stdout={ran.stdout_text!r}"
    )


def test_complete_lists_custom_group_immediate_children():
    greeting = _greeting()
    exe = _exe()
    name_a = f"va{_word()}"
    name_b = f"zb{_word()}"
    hi_a = _greeting()
    hi_b = _greeting()
    mod_a = f"zxqa{uuid.uuid4().hex}"
    mod_b = f"zxqb{uuid.uuid4().hex}"

    with workspace() as ws:
        trace_a = ws.path / f"{mod_a}.loaded"
        trace_b = ws.path / f"{mod_b}.loaded"
        _write_leaf_module(ws, mod_a, hi_a, name_a, trace_a)
        _write_leaf_module(ws, mod_b, hi_b, name_b, trace_b)

        def resolve(name: str):
            if name == name_a:
                return importlib.import_module(mod_a).cli
            if name == name_b:
                return importlib.import_module(mod_b).cli
            return None

        cli = group(cls=_LookupGroup, invoke_without_command=True)(
            _root(greeting).callback
        )
        assert isinstance(cli, _LookupGroup)
        cli.configure([name_a, name_b], resolve)
        with _on_path(ws.path, mod_a, mod_b):
            result = ws.invoke(
                cli,
                [],
                env=completion_line_env("bash", exe, (), ""),
                prog_name=exe,
            )
        print(
            f"custom-list stdout={result.stdout_text!r} "
            f"a={import_trace_present(trace_a)} "
            f"b={import_trace_present(trace_b)}",
            flush=True,
        )
        assert_callback_skipped(result, greeting)
        _require_name(result.stdout_text, name_a, present=True)
        _require_name(result.stdout_text, name_b, present=True)


def test_complete_does_not_load_grandchild():
    greeting = _greeting()
    exe = _exe()
    mid_name = f"md{_word()}"
    leaf_name = f"lf{_word()}"
    mid_mod = f"zxqm{uuid.uuid4().hex}"
    leaf_mod = f"zxql{uuid.uuid4().hex}"
    mid_hi = _greeting()
    leaf_hi = _greeting()

    with workspace() as ws:
        mid_trace = ws.path / f"{mid_mod}.loaded"
        leaf_trace = ws.path / f"{leaf_mod}.loaded"
        _write_leaf_module(ws, leaf_mod, leaf_hi, leaf_name, leaf_trace)
        mid_body = (
            "from optlyn import Group, group\n"
            "from pathlib import Path as _Trace\n"
            f"_Trace({str(mid_trace)!r}).write_text('loaded', encoding='utf-8')\n"
            f"class _Mid(Group):\n"
            f"    def list_commands(self, ctx):\n"
            f"        return [{leaf_name!r}]\n"
            f"    def get_command(self, ctx, cmd_name):\n"
            f"        if cmd_name == {leaf_name!r}:\n"
            f"            import {leaf_mod} as _leafmod\n"
            f"            return _leafmod.cli\n"
            f"        return None\n"
            f"def _mid():\n"
            f"    print({mid_hi!r}, flush=True)\n"
            f"_mid.__name__ = {_word()!r}\n"
            f"cli = group(cls=_Mid, name={mid_name!r})(_mid)\n"
        )
        dest = ws.write(f"{mid_mod}.py", mid_body)
        if not dest.is_file():
            raise RuntimeError(f"failed to write middle module at {dest}")

        def resolve(name: str):
            if name == mid_name:
                return importlib.import_module(mid_mod).cli
            return None

        outer = group(cls=_LookupGroup, invoke_without_command=True)(
            _root(greeting).callback
        )
        assert isinstance(outer, _LookupGroup)
        outer.configure([mid_name], resolve)
        with _on_path(ws.path, mid_mod, leaf_mod):
            completed = ws.invoke(
                outer,
                [],
                env=completion_line_env("bash", exe, (), ""),
                prog_name=exe,
            )
            print(
                f"complete stdout={completed.stdout_text!r} "
                f"mid={import_trace_present(mid_trace)} "
                f"leaf={import_trace_present(leaf_trace)}",
                flush=True,
            )
            assert_callback_skipped(completed, greeting)
            _require_name(completed.stdout_text, mid_name, present=True)
            assert not import_trace_present(leaf_trace), (
                f"grandchild module {leaf_mod!r} was loaded during parent "
                f"complete; stdout={completed.stdout_text!r}"
            )
            dispatched = ws.invoke(outer, [mid_name, leaf_name], prog_name=exe)
            print(
                f"dispatch stdout={dispatched.stdout_text!r} "
                f"leaf={import_trace_present(leaf_trace)}",
                flush=True,
            )
            assert_success_marker_present(dispatched, leaf_hi)
            assert import_trace_present(leaf_trace), (
                "baseline dispatch never produced the grandchild load trace"
            )


# ---------------------------------------------------------------------------
# E. Options after a dash, --help, hidden options
# ---------------------------------------------------------------------------


def test_options_listed_only_after_a_dash():
    greeting = _greeting()
    exe = _exe()
    vis = f"va{_word()}"
    flag = f"--o{_word()}"
    dest = _word()
    cli = _root(greeting, option(flag, dest))
    cli.add_command(_leaf(_greeting(), name=vis))
    empty = _complete(cli, exe, "bash")
    letter = _complete(cli, exe, "bash", incomplete=vis[:3])
    dashed = _complete(cli, exe, "bash", incomplete="-")
    print(
        f"empty={empty.stdout_text!r} letter={letter.stdout_text!r} "
        f"dash={dashed.stdout_text!r}",
        flush=True,
    )
    assert_callback_skipped(empty, greeting)
    assert_callback_skipped(letter, greeting)
    _require_name(dashed.stdout_text, flag, present=True)
    _require_name(dashed.stdout_text, "--help", present=True)
    _require_name(empty.stdout_text, flag, present=False)
    _require_name(empty.stdout_text, "--help", present=False)
    _require_name(letter.stdout_text, flag, present=False)
    _require_name(letter.stdout_text, "--help", present=False)


def test_dash_lists_visible_options_including_help_not_hidden():
    greeting = _greeting()
    exe = _exe()
    vis_flag = f"--v{_word()}"
    hid_flag = f"--h{_word()}"
    vis_dest = _word()
    hid_dest = _word()
    cli = _leaf(
        greeting,
        option(vis_flag, vis_dest),
        option(hid_flag, hid_dest, hidden=True),
    )
    dashed = _complete(cli, exe, "bash", incomplete="-")
    print(f"dash={dashed.stdout_text!r}", flush=True)
    assert_callback_skipped(dashed, greeting)
    _require_name(dashed.stdout_text, vis_flag, present=True)
    _require_name(dashed.stdout_text, "--help", present=True)
    _require_name(dashed.stdout_text, hid_flag, present=False)


def test_option_prefix_excludes_nonmatching_option():
    greeting = _greeting()
    exe = _exe()
    flag_a = f"--a{_word()}"
    flag_b = f"--b{_word()}"
    dest_a = _word()
    dest_b = _word()
    prefix = flag_a[:4]
    assert not flag_b.startswith(prefix)
    cli = _leaf(
        greeting,
        option(flag_a, dest_a),
        option(flag_b, dest_b),
    )
    result = _complete(cli, exe, "bash", incomplete=prefix)
    print(f"prefix={prefix!r} stdout={result.stdout_text!r}", flush=True)
    assert_callback_skipped(result, greeting)
    _require_name(result.stdout_text, flag_a, present=True)
    _require_name(result.stdout_text, flag_b, present=False)


def test_hidden_option_not_suggested_as_prefix_or_full_token():
    greeting = _greeting()
    exe = _exe()
    vis_flag = f"--v{_word()}"
    hid_flag = f"--h{_word()}"
    vis_dest = _word()
    hid_dest = _word()
    cli = _leaf(
        greeting,
        option(vis_flag, vis_dest),
        option(hid_flag, hid_dest, hidden=True),
    )
    dashed = _complete(cli, exe, "bash", incomplete="-")
    prefix = _complete(cli, exe, "bash", incomplete=hid_flag[:4])
    full = _complete(cli, exe, "bash", incomplete=hid_flag)
    print(
        f"dash={dashed.stdout_text!r} prefix={prefix.stdout_text!r} "
        f"full={full.stdout_text!r}",
        flush=True,
    )
    _require_name(dashed.stdout_text, vis_flag, present=True)
    _require_name(dashed.stdout_text, hid_flag, present=False)
    assert_callback_skipped(prefix, greeting)
    assert_callback_skipped(full, greeting)
    _require_name(prefix.stdout_text, hid_flag, present=False)
    _require_name(full.stdout_text, hid_flag, present=False)


def test_hidden_option_still_accepted_when_fully_typed():
    greeting = _greeting()
    exe = _exe()
    vis_flag = f"--v{_word()}"
    hid_flag = f"--h{_word()}"
    vis_dest = _word()
    hid_dest = _word()
    value = f"val{_word()}"
    cli = _leaf(
        greeting,
        option(vis_flag, vis_dest),
        option(hid_flag, hid_dest, hidden=True),
    )
    omitted = _complete(cli, exe, "bash", incomplete="-")
    ran = _run(cli, [hid_flag, value], exe)
    print(
        f"omitted={omitted.stdout_text!r} ran={ran.stdout_text!r}",
        flush=True,
    )
    assert_callback_skipped(omitted, greeting)
    _require_name(omitted.stdout_text, vis_flag, present=True)
    _require_name(omitted.stdout_text, "--help", present=True)
    _require_name(omitted.stdout_text, hid_flag, present=False)
    assert_success_marker_present(ran, greeting)
    assert f"P:{hid_dest}:{value}" in ran.stdout_text, (
        f"hidden option value {value!r} was not delivered; "
        f"stdout={ran.stdout_text!r}"
    )


# ---------------------------------------------------------------------------
# F. Choice type: only allowed values matching the prefix
# ---------------------------------------------------------------------------


def test_choice_suggests_only_allowed_values_matching_prefix():
    greeting = _greeting()
    exe = _exe()
    flag = f"--c{_word()}"
    dest = _word()
    first = f"aa{_word()}"
    second = f"zz{_word()}"
    prefix = first[:3]
    assert not second.startswith(prefix)
    cli = _leaf(greeting, option(flag, dest, type=Choice([first, second])))
    result = _complete(cli, exe, "bash", completed=(flag,), incomplete=prefix)
    print(f"prefix={prefix!r} stdout={result.stdout_text!r}", flush=True)
    assert_callback_skipped(result, greeting)
    _require_name(result.stdout_text, first, present=True)
    _require_name(result.stdout_text, second, present=False)


def test_choice_empty_incomplete_lists_all_allowed_values():
    greeting = _greeting()
    exe = _exe()
    flag = f"--c{_word()}"
    dest = _word()
    first = f"aa{_word()}"
    second = f"bb{_word()}"
    third = f"cc{_word()}"
    cli = _leaf(
        greeting, option(flag, dest, type=Choice([first, second, third]))
    )
    result = _complete(cli, exe, "bash", completed=(flag,), incomplete="")
    print(f"empty-choice stdout={result.stdout_text!r}", flush=True)
    assert_callback_skipped(result, greeting)
    _require_name(result.stdout_text, first, present=True)
    _require_name(result.stdout_text, second, present=True)
    _require_name(result.stdout_text, third, present=True)


def test_choice_argument_completes_without_a_dash():
    greeting = _greeting()
    exe = _exe()
    first = f"aa{_word()}"
    second = f"zz{_word()}"
    prefix = first[:3]
    assert not second.startswith(prefix)
    cli = _leaf(
        greeting, argument("item", type=Choice([first, second]))
    )
    empty = _complete(cli, exe, "bash")
    pref = _complete(cli, exe, "bash", incomplete=prefix)
    print(
        f"empty={empty.stdout_text!r} prefix={pref.stdout_text!r}",
        flush=True,
    )
    assert_callback_skipped(empty, greeting)
    assert_callback_skipped(pref, greeting)
    _require_name(empty.stdout_text, first, present=True)
    _require_name(empty.stdout_text, second, present=True)
    _require_name(pref.stdout_text, first, present=True)
    _require_name(pref.stdout_text, second, present=False)


# ---------------------------------------------------------------------------
# G. File / path: carry the incomplete token, do not list directory entries
# ---------------------------------------------------------------------------


def test_file_type_carries_incomplete_token_not_directory_entries():
    greeting = _greeting()
    exe = _exe()
    flag = f"--f{_word()}"
    dest = _word()
    prefix = f"px{_word()[:6]}"
    bait = f"{prefix}{_word()}"
    choice_flag = f"--c{_word()}"
    choice_dest = _word()
    file_cli = _leaf(greeting, option(flag, dest, type=File()))
    choice_cli = _leaf(
        greeting, option(choice_flag, choice_dest, type=Choice([bait]))
    )
    with workspace() as ws:
        bait_path = ws.write(bait, "bait-body")
        if not bait_path.is_file():
            raise RuntimeError(f"failed to write bait file at {bait_path}")
        file_run = ws.invoke(
            file_cli,
            [],
            env=completion_line_env("bash", exe, (flag,), prefix),
            prog_name=exe,
        )
        choice_run = ws.invoke(
            choice_cli,
            [],
            env=completion_line_env("bash", exe, (choice_flag,), prefix),
            prog_name=exe,
        )
    print(
        f"file={file_run.stdout_text!r} choice={choice_run.stdout_text!r} "
        f"bait={bait!r} prefix={prefix!r}",
        flush=True,
    )
    assert_callback_skipped(choice_run, greeting)
    _require_name(choice_run.stdout_text, bait, present=True)
    assert_callback_skipped(file_run, greeting)
    _require_name(file_run.stdout_text, prefix, present=True)
    _require_name(file_run.stdout_text, bait, present=False)


def test_path_type_carries_incomplete_token_not_directory_entries():
    greeting = _greeting()
    exe = _exe()
    any_flag = f"--p{_word()}"
    any_dest = _word()
    dir_flag = f"--d{_word()}"
    dir_dest = _word()
    prefix = f"px{_word()[:6]}"
    bait = f"{prefix}{_word()}"
    any_cli = _leaf(greeting, option(any_flag, any_dest, type=PathType()))
    dir_cli = _leaf(
        greeting,
        option(dir_flag, dir_dest, type=PathType(file_okay=False)),
    )
    with workspace() as ws:
        bait_path = ws.write(bait, "bait-body")
        if not bait_path.is_file():
            raise RuntimeError(f"failed to write bait file at {bait_path}")
        any_run = ws.invoke(
            any_cli,
            [],
            env=completion_line_env("bash", exe, (any_flag,), prefix),
            prog_name=exe,
        )
        dir_run = ws.invoke(
            dir_cli,
            [],
            env=completion_line_env("bash", exe, (dir_flag,), prefix),
            prog_name=exe,
        )
    print(
        f"any={any_run.stdout_text!r} dir={dir_run.stdout_text!r} "
        f"bait={bait!r}",
        flush=True,
    )
    assert_callback_skipped(any_run, greeting)
    assert_callback_skipped(dir_run, greeting)
    _require_name(any_run.stdout_text, prefix, present=True)
    _require_name(any_run.stdout_text, bait, present=False)
    _require_name(dir_run.stdout_text, prefix, present=True)
    _require_name(dir_run.stdout_text, bait, present=False)


def test_directories_only_path_asks_shell_for_directories_only():
    greeting = _greeting()
    exe = _exe()
    flag = f"--p{_word()}"
    dest = _word()
    prefix = f"px{_word()[:6]}"
    bait = f"{prefix}{_word()}"
    dirs_cli = _leaf(
        greeting, option(flag, dest, type=PathType(file_okay=False))
    )
    files_cli = _leaf(greeting, option(flag, dest, type=File()))
    files_path_cli = _leaf(
        greeting, option(flag, dest, type=PathType(dir_okay=False))
    )
    all_cli = _leaf(greeting, option(flag, dest, type=PathType()))
    with workspace() as ws:
        bait_path = ws.write(bait, "bait-body")
        if not bait_path.is_file():
            raise RuntimeError(f"failed to write bait file at {bait_path}")
        dirs_run = ws.invoke(
            dirs_cli,
            [],
            env=completion_line_env("bash", exe, (flag,), prefix),
            prog_name=exe,
        )
        files_run = ws.invoke(
            files_cli,
            [],
            env=completion_line_env("bash", exe, (flag,), prefix),
            prog_name=exe,
        )
        files_path_run = ws.invoke(
            files_path_cli,
            [],
            env=completion_line_env("bash", exe, (flag,), prefix),
            prog_name=exe,
        )
        all_run = ws.invoke(
            all_cli,
            [],
            env=completion_line_env("bash", exe, (flag,), prefix),
            prog_name=exe,
        )
    print(
        f"dirs={dirs_run.stdout_text!r} files={files_run.stdout_text!r} "
        f"files_path={files_path_run.stdout_text!r} "
        f"all_paths={all_run.stdout_text!r} bait={bait!r} prefix={prefix!r}",
        flush=True,
    )
    for result in (dirs_run, files_run, files_path_run, all_run):
        assert_callback_skipped(result, greeting)
        _require_name(result.stdout_text, prefix, present=True)
        _require_name(result.stdout_text, bait, present=False)
    dirs_rest = completion_stream_remainder(
        dirs_run, prefix, exe, flag, dest
    )
    files_rest = completion_stream_remainder(
        files_run, prefix, exe, flag, dest
    )
    files_path_rest = completion_stream_remainder(
        files_path_run, prefix, exe, flag, dest
    )
    all_rest = completion_stream_remainder(all_run, prefix, exe, flag, dest)
    print(
        f"dirs_rest={dirs_rest!r} files_rest={files_rest!r} "
        f"files_path_rest={files_path_rest!r} all_rest={all_rest!r}",
        flush=True,
    )
    assert dirs_rest != files_rest, (
        "directories-only path complete is not distinguishable from "
        "file-type complete after stripping the incomplete token; "
        f"dirs={dirs_rest!r} files={files_rest!r}"
    )
    assert dirs_rest != files_path_rest, (
        "directories-only path complete is not distinguishable from "
        "files-only path complete after stripping the incomplete token; "
        f"dirs={dirs_rest!r} files_path={files_path_rest!r}"
    )
    assert dirs_rest != all_rest, (
        "directories-only path complete is not distinguishable from "
        "all-path complete after stripping the incomplete token; "
        f"dirs={dirs_rest!r} all_paths={all_rest!r}"
    )


def test_bash_file_completion_registers_and_lists_directory_candidates():
    greeting = _greeting()
    exe = _exe()
    flag = f"--f{_word()}"
    dest = _word()
    prefix = f"px{_word()[:6]}"
    file_a = f"{prefix}a{_word()[:4]}"
    file_b = f"{prefix}b{_word()[:4]}"
    cli = _leaf(greeting, option(flag, dest, type=File()))
    sourced = _source(cli, exe, "bash")
    script = sourced.stdout_text
    assert script.strip(), (
        f"bash_source produced empty stdout; stderr={sourced.stderr_text!r}"
    )
    with workspace() as ws:
        ws.write(file_a, "a")
        ws.write(file_b, "b")
        wrapper = ws.write(
            exe,
            "#!/usr/bin/env python3\n"
            "from optlyn import File, command, option\n"
            f"def _cb(**kwargs):\n"
            f"    print({greeting!r}, flush=True)\n"
            f"cli = command()(option({flag!r}, {dest!r}, type=File())(_cb))\n"
            "if __name__ == '__main__':\n"
            "    cli.main()\n",
        )
        wrapper.chmod(wrapper.stat().st_mode | 0o111)
        src = ws.write("complete.bash", script)
        probe = ws.write(
            "probe.sh",
            "#!/bin/bash\n"
            "set +e\n"
            f"export PATH={str(ws.path)!r}:$PATH\n"
            f"source {str(src)!r}\n"
            f"if ! complete -p {exe} >/dev/null 2>&1; then\n"
            "  echo NO_COMPLETE_REGISTRATION\n"
            "  exit 1\n"
            "fi\n"
            f'reg="$(complete -p {exe})"\n'
            'printf "REGISTRATION:%s\\n" "$reg"\n'
            # Registration-script syntax is not pinned (Contract §8 / F12
            # header). Accept -F, -C, or options-only such as -o default.
            r"""fn=$(printf '%s\n' "$reg" | awk '{for(i=1;i<=NF;i++) if($i=="-F") print $(i+1)}' | sed "s/^[\"']//;s/[\"']$//")"""
            "\n"
            r"""cmd=$(printf '%s\n' "$reg" | awk '{for(i=1;i<=NF;i++) if($i=="-C") print $(i+1)}' | sed "s/^[\"']//;s/[\"']$//")"""
            "\n"
            # Outside a live readline completion the ``compopt`` builtin
            # refuses to run, so record what the function asks for instead.
            # Print args one by one: the caller may have set IFS to newline.
            'compopt() { printf "COMPOPT:"; printf " %s" "$@"; printf "\\n"; }\n'
            f"COMP_WORDS=({exe} {flag} {prefix})\n"
            "COMP_CWORD=2\n"
            f"COMP_LINE='{exe} {flag} {prefix}'\n"
            "COMP_POINT=${#COMP_LINE}\n"
            "COMPREPLY=()\n"
            "export COMP_WORDS COMP_CWORD COMP_LINE COMP_POINT\n"
            'if [ -n "$fn" ]; then\n'
            f'  "$fn" {exe} {prefix} {flag}\n'
            '  printf "REPLY:%s\\n" "${COMPREPLY[@]}"\n'
            'elif [ -n "$cmd" ]; then\n'
            # bash man complete -C: command exe word prev
            '  while IFS= read -r line; do\n'
            '    [ -n "$line" ] && printf "REPLY:%s\\n" "$line"\n'
            f'  done < <("$cmd" {exe} {prefix} {flag})\n'
            "fi\n",
        )
        probe.chmod(probe.stat().st_mode | 0o111)
        result = ws.run_command(["bash", str(probe)])
    text = result.stdout_text
    print(f"bash_file_complete out={text!r} code={result.returncode}", flush=True)
    assert (
        "NO_COMPLETE_REGISTRATION" not in text
        and result.returncode == 0
    ), f"bash did not register completion for {exe!r}; out={text!r}"
    listed = file_a in text or file_b in text
    # Either the function asks readline for filename completion at call time
    # (``compopt -o default``) or registration itself carries that option.
    _fs_opts = ("default", "filenames", "dirnames", "plusdirs")
    defaulted = any(
        line.startswith(("COMPOPT:", "REGISTRATION:"))
        and any(f"-o {opt}" in line or f"-o{opt}" in line for opt in _fs_opts)
        for line in text.splitlines()
    )
    assert listed or defaulted, (
        "real bash file completion neither listed directory candidates "
        f"nor enabled default filename completion; out={text!r}"
    )


def test_file_argument_carries_incomplete_token_not_directory_entries():
    greeting = _greeting()
    exe = _exe()
    prefix = f"px{_word()[:6]}"
    bait = f"{prefix}{_word()}"
    cli = _leaf(greeting, argument("src", type=File()))
    with workspace() as ws:
        bait_path = ws.write(bait, "bait-body")
        if not bait_path.is_file():
            raise RuntimeError(f"failed to write bait file at {bait_path}")
        result = ws.invoke(
            cli,
            [],
            env=completion_line_env("bash", exe, (), prefix),
            prog_name=exe,
        )
    print(f"arg-file={result.stdout_text!r} bait={bait!r}", flush=True)
    assert_callback_skipped(result, greeting)
    _require_name(result.stdout_text, prefix, present=True)
    _require_name(result.stdout_text, bait, present=False)


# ---------------------------------------------------------------------------
# H. Author completers, custom types, help strings
# ---------------------------------------------------------------------------


def test_parameter_completer_sees_context_parameter_and_incomplete_token():
    greeting = _greeting()
    exe = _exe()
    mark = f"MK{uuid.uuid4().hex}"
    ctx_flag = f"--n{_word()}"
    ctx_dest = _word()
    flag_a = f"--a{_word()}"
    flag_b = f"--b{_word()}"
    dest_a = _word()
    dest_b = _word()
    meta_a = f"MA{uuid.uuid4().hex}"
    meta_b = f"MB{uuid.uuid4().hex}"
    token_x = f"tx{_word()}"
    token_y = f"ty{_word()}"
    count_left = 14 + uuid.uuid4().int % 40
    count_right = count_left + 11
    transformed_left = str(count_left * 3 + 7)
    transformed_right = str(count_right * 3 + 7)
    assert mark not in token_x and mark not in token_y
    assert mark not in str(count_left) and mark not in transformed_left

    def completer(ctx, param, incomplete):
        meta = param.metavar or "nometa"
        raw = ctx.params.get(ctx_dest)
        transformed = ""
        if isinstance(raw, int):
            transformed = str(raw * 3 + 7)
        token_part = incomplete if incomplete else "emptytok"
        return [f"{mark}:{meta}:{transformed}:{token_part}"]

    cli = _leaf(
        greeting,
        option(ctx_flag, ctx_dest, type=INT),
        option(flag_a, dest_a, metavar=meta_a, shell_complete=completer),
        option(flag_b, dest_b, metavar=meta_b, shell_complete=completer),
    )
    at_a_left = _complete(
        cli,
        exe,
        "bash",
        completed=(ctx_flag, str(count_left), flag_a),
        incomplete=token_x,
    )
    at_a_right_ctx = _complete(
        cli,
        exe,
        "bash",
        completed=(ctx_flag, str(count_right), flag_a),
        incomplete=token_x,
    )
    at_a_token = _complete(
        cli,
        exe,
        "bash",
        completed=(ctx_flag, str(count_left), flag_a),
        incomplete=token_y,
    )
    at_a_empty = _complete(
        cli,
        exe,
        "bash",
        completed=(ctx_flag, str(count_left), flag_a),
        incomplete="",
    )
    at_b = _complete(
        cli,
        exe,
        "bash",
        completed=(ctx_flag, str(count_left), flag_b),
        incomplete=token_x,
    )
    print(
        f"a_left={at_a_left.stdout_text!r} a_ctx={at_a_right_ctx.stdout_text!r} "
        f"a_tok={at_a_token.stdout_text!r} a_empty={at_a_empty.stdout_text!r} "
        f"b={at_b.stdout_text!r}",
        flush=True,
    )
    for result in (at_a_left, at_a_right_ctx, at_a_token, at_a_empty, at_b):
        assert_callback_skipped(result, greeting)
        _require_name(result.stdout_text, mark, present=True)
    _require_name(at_a_left.stdout_text, meta_a, present=True)
    _require_name(at_a_left.stdout_text, transformed_left, present=True)
    _require_name(at_a_left.stdout_text, token_x, present=True)
    assert at_a_left.stdout_text != at_a_right_ctx.stdout_text, (
        "completer ignored the filled context value; "
        f"left={at_a_left.stdout_text!r} right={at_a_right_ctx.stdout_text!r}"
    )
    _require_name(at_a_right_ctx.stdout_text, transformed_right, present=True)
    assert at_a_left.stdout_text != at_a_token.stdout_text, (
        "completer ignored the incomplete token; "
        f"x={at_a_left.stdout_text!r} y={at_a_token.stdout_text!r}"
    )
    assert at_a_empty.stdout_text.strip(), (
        f"empty incomplete token produced no suggestion; "
        f"stdout={at_a_empty.stdout_text!r}"
    )
    _require_name(at_b.stdout_text, meta_b, present=True)
    assert at_a_left.stdout_text != at_b.stdout_text, (
        "same completer on two parameters did not distinguish them; "
        f"a={at_a_left.stdout_text!r} b={at_b.stdout_text!r}"
    )


def test_custom_type_completion_unlike_string_sibling():
    greeting = _greeting()
    exe = _exe()
    mark = f"TM{uuid.uuid4().hex}"
    flag = f"--t{_word()}"
    dest = _word()
    prefix = f"px{_word()[:4]}"
    typed = _leaf(
        greeting, option(flag, dest, type=_MarkedCompleteType(mark))
    )
    sibling = _leaf(greeting, option(flag, dest, type=STRING))
    typed_run = _complete(
        typed, exe, "bash", completed=(flag,), incomplete=prefix
    )
    sibling_run = _complete(
        sibling, exe, "bash", completed=(flag,), incomplete=prefix
    )
    print(
        f"typed={typed_run.stdout_text!r} sibling={sibling_run.stdout_text!r}",
        flush=True,
    )
    assert_callback_skipped(typed_run, greeting)
    assert_callback_skipped(sibling_run, greeting)
    _require_name(typed_run.stdout_text, mark, present=True)
    _require_name(sibling_run.stdout_text, mark, present=False)


def test_zsh_and_fish_include_author_help_next_to_value():
    greeting = _greeting()
    exe = _exe()
    flag = f"--v{_word()}"
    dest = _word()
    val_a = f"va{_word()}"
    val_b = f"vb{_word()}"
    help_a = f"HA{uuid.uuid4().hex}"
    help_b = f"HB{uuid.uuid4().hex}"
    assert help_a not in val_a and help_a not in val_b
    assert help_b not in val_a and help_b not in val_b
    assert help_a not in help_b and help_b not in help_a

    def with_help(ctx, param, incomplete):
        return [_Suggest(val_a, help=help_a), _Suggest(val_b, help=help_b)]

    def without_help(ctx, param, incomplete):
        return [_Suggest(val_a), _Suggest(val_b)]

    def swapped(ctx, param, incomplete):
        return [_Suggest(val_a, help=help_b), _Suggest(val_b, help=help_a)]

    helped_cli = _leaf(greeting, option(flag, dest, shell_complete=with_help))
    bare_cli = _leaf(greeting, option(flag, dest, shell_complete=without_help))
    swap_cli = _leaf(greeting, option(flag, dest, shell_complete=swapped))
    for shell in ("zsh", "fish"):
        helped = _complete(
            helped_cli, exe, shell, completed=(flag,), incomplete=""
        )
        bare = _complete(
            bare_cli, exe, shell, completed=(flag,), incomplete=""
        )
        swapped_run = _complete(
            swap_cli, exe, shell, completed=(flag,), incomplete=""
        )
        print(
            f"{shell} helped={helped.stdout_text!r} bare={bare.stdout_text!r} "
            f"swap={swapped_run.stdout_text!r}",
            flush=True,
        )
        assert_callback_skipped(helped, greeting)
        assert_callback_skipped(bare, greeting)
        _require_name(helped.stdout_text, val_a, present=True)
        _require_name(helped.stdout_text, val_b, present=True)
        helped_rest = completion_stream_remainder(helped, val_a, val_b)
        bare_rest = completion_stream_remainder(bare, val_a, val_b)
        swap_rest = completion_stream_remainder(swapped_run, val_a, val_b)
        assert helped_rest != bare_rest, (
            f"{shell}: help next to value is not distinguishable after "
            f"stripping values; helped={helped_rest!r} bare={bare_rest!r}"
        )
        assert helped_rest != swap_rest, (
            f"{shell}: swapped help pairing is not distinguishable after "
            f"stripping values; helped={helped_rest!r} swap={swap_rest!r}"
        )


def test_bash_and_powershell_suggest_value_without_requiring_help():
    greeting = _greeting()
    exe = _exe()
    flag = f"--v{_word()}"
    dest = _word()
    val = f"vv{_word()}"
    help_s = f"HP{uuid.uuid4().hex}"

    def with_help(ctx, param, incomplete):
        return [_Suggest(val, help=help_s)]

    cli = _leaf(greeting, option(flag, dest, shell_complete=with_help))
    for shell in ("bash", "powershell"):
        result = _complete(cli, exe, shell, completed=(flag,), incomplete="")
        print(f"{shell} stdout={result.stdout_text!r}", flush=True)
        assert_callback_skipped(result, greeting)
        _require_name(result.stdout_text, val, present=True)


# ---------------------------------------------------------------------------
# I. Match-nothing is not a usage error
# ---------------------------------------------------------------------------


def test_unmatched_subcommand_token_is_empty_suggestions_not_usage_error():
    greeting = _greeting()
    exe = _exe()
    vis_a = f"va{_word()}"
    vis_b = f"zb{_word()}"
    unmatched = f"qq{_word()}"
    assert not vis_a.startswith(unmatched) and not vis_b.startswith(unmatched)
    cli = _root(greeting)
    cli.add_command(_leaf(_greeting(), name=vis_a))
    cli.add_command(_leaf(_greeting(), name=vis_b))
    completed = _complete(cli, exe, "bash", incomplete=unmatched)
    usage = _run(cli, [unmatched], exe)
    print(
        f"complete={completed.stdout_text!r} usage={usage.stdout_text!r} "
        f"usage_err={usage.stderr_text!r} complete_exit={completed.exit_code}",
        flush=True,
    )
    assert_callback_skipped(completed, greeting)
    assert_not_usage_class(completed, greeting)
    _require_name(completed.stdout_text, vis_a, present=False)
    _require_name(completed.stdout_text, vis_b, present=False)
    assert_usage_class(usage, greeting)


def test_unmatched_choice_prefix_is_empty_suggestions_not_usage_error():
    greeting = _greeting()
    exe = _exe()
    flag = f"--c{_word()}"
    dest = _word()
    first = f"aa{_word()}"
    second = f"bb{_word()}"
    unmatched = f"zz{_word()}"
    assert not first.startswith(unmatched) and not second.startswith(unmatched)
    cli = _leaf(greeting, option(flag, dest, type=Choice([first, second])))
    completed = _complete(
        cli, exe, "bash", completed=(flag,), incomplete=unmatched
    )
    usage = _run(cli, [flag, unmatched], exe)
    print(
        f"complete={completed.stdout_text!r} usage_exit={usage.exit_code} "
        f"usage_err={usage.stderr_text!r} complete_exit={completed.exit_code}",
        flush=True,
    )
    assert_callback_skipped(completed, greeting)
    assert_not_usage_class(completed, greeting)
    _require_name(completed.stdout_text, first, present=False)
    _require_name(completed.stdout_text, second, present=False)
    assert_usage_class(usage, greeting)
    require_usage_names_option(usage, greeting, flag)


# ---------------------------------------------------------------------------
# J. Unrecognized instruction
# ---------------------------------------------------------------------------


def test_unrecognized_instruction_skips_callback_and_is_neither_source_nor_complete():
    greeting = _greeting()
    exe = _exe()
    var = complete_variable_name(exe)
    vis = f"va{_word()}"
    garbage = f"zxq{uuid.uuid4().hex}"
    cli = _root(greeting)
    cli.add_command(_leaf(_greeting(), name=vis))
    unknown_env = dict(completion_line_env("bash", exe, (), ""))
    unknown_env[var] = garbage
    unknown = _run(cli, [], exe, env=unknown_env)
    sourced = {shell: _source(cli, exe, shell) for shell in SHELLS}
    completed = {shell: _complete(cli, exe, shell) for shell in SHELLS}
    wrong_name = _run(
        cli, [], exe, env={f"_{exe.upper()}_COMPLETE": "bash_source"}
    )
    print(
        f"unknown={unknown.stdout_text!r} wrong={wrong_name.stdout_text!r}",
        flush=True,
    )
    for shell, result in sourced.items():
        print(f"{shell}_source={result.stdout_text!r}", flush=True)
    for shell, result in completed.items():
        print(f"{shell}_complete={result.stdout_text!r}", flush=True)
    assert_callback_skipped(unknown, greeting)
    assert_success_marker_present(wrong_name, greeting)
    unknown_rest = completion_stream_remainder(unknown, exe, var, garbage)
    for shell, result in sourced.items():
        assert_callback_skipped(result, greeting)
        source_rest = completion_stream_remainder(result, exe, var, garbage)
        assert unknown_rest != source_rest, (
            f"unrecognized instruction is not distinct from {shell}_source "
            f"after stripping executable name; unknown={unknown_rest!r} "
            f"source={source_rest!r}"
        )
    for shell, result in completed.items():
        assert_callback_skipped(result, greeting)
        _require_name(result.stdout_text, vis, present=True)
        complete_rest = completion_stream_remainder(result, exe, var, garbage)
        assert unknown_rest != complete_rest, (
            f"unrecognized instruction is not distinct from {shell}_complete "
            f"suggestion stream after stripping executable name; "
            f"unknown={unknown_rest!r} complete={complete_rest!r}"
        )
    _require_name(unknown.stdout_text, vis, present=False)
