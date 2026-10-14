# feature: F14
"""In-process testing runner (FP-14).

Assertions stay at the PRD's precision: invoke with a token list really
runs the command; the result exposes exit status, stdout text and bytes,
and separable stderr; subcommands are selected by tokens after a group
option; extra keywords become context settings (terminal width);
optional input, environment, and color; visible prompts echo the typed
line and hidden prompts do not; an optional mode echoes each stdin read
that actually happened; isolated filesystem always chdirs into a new
empty directory (removed when no parent, left under a supplied parent);
default capture records interpreter streams without a real descriptor,
and descriptor capture records OS writes to 1 and 2; standalone raises
become a returned result with an inspectable exception, unless the
runner is told not to catch. Message wording, exception types, CSI
opcodes, and process-cwd restoration are not pinned.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from optlyn import File, argument, command, echo, group, option, style, unstyle
from optlyn.testing import CliRunner

from _harness import workspace
from _helpers import (
    ansi_escape_present,
    failure_report_remainder,
    product_runner_bytes,
    product_runner_streams,
    require_failure_propagates,
    require_runner_exception_inspectable,
    require_runner_no_exception,
    require_runner_success_marker_present,
    require_runner_success_with_marker,
    require_runner_text_and_bytes_carry,
    runner_captured_text,
    styled_text_remainder,
    styled_text_suffix,
    unrelated_dispatch_token,
)

def _word() -> str:
    return "k" + uuid.uuid4().hex[:8]


def _letters(n: int = 8) -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyz"
    return "".join(alphabet[uuid.uuid4().int % len(alphabet)] for _ in range(n))


def _plain_name() -> str:
    """A capitalised alphabetic word, like an ordinary personal name."""
    return _letters(1).upper() + _letters(7)


def _greeting() -> str:
    return f"GREET:{uuid.uuid4().hex}:"


def _token() -> str:
    return f"T{uuid.uuid4().hex}"


def _ascii_mark(prefix: str = "M") -> str:
    return f"{prefix}{uuid.uuid4().hex}"


def _mark(value: str, salt: str) -> str:
    acc = len(value) * 17
    for i, ch in enumerate(value):
        acc += (ord(ch) + i + 1) * (ord(salt[i % len(salt)]) + 3)
    return f"K:{acc}"


def _cmd(callback, *param_decs, **command_kwargs):
    command_kwargs.setdefault("name", _word())
    decorated = callback
    for deco in reversed(param_decs):
        decorated = deco(decorated)
    return command(**command_kwargs)(decorated)


def _hello(prefix: str, *, description: str | None = None):
    def callback(name: str) -> None:
        print(f"{prefix}{name}", flush=True)

    kwargs: dict[str, str] = {"name": _word()}
    if description is not None:
        kwargs["help"] = description
    return _cmd(callback, argument("name"), **kwargs)


def _stdout_has_usable_fd() -> bool:
    fileno = getattr(sys.stdout, "fileno", None)
    if not callable(fileno):
        return False
    try:
        fd = fileno()
    except Exception:
        return False
    return isinstance(fd, int) and fd >= 0


def _observe(label: str, result) -> tuple[int, str, str]:
    code, stdout, stderr = product_runner_streams(result)
    print(
        f"{label} exit={code} stdout={stdout!r} stderr={stderr!r}",
        flush=True,
    )
    return code, stdout, stderr


# ---------------------------------------------------------------------------
# A. Invoke runs the command; result fields; subcommand tokens
# ---------------------------------------------------------------------------


def test_invoke_plain_name_token_greets_that_name():
    prefix = _greeting()
    plain_name = _plain_name()
    cli = _hello(prefix)
    result = CliRunner().invoke(cli, [plain_name])
    _observe("plain-name", result)
    require_runner_success_with_marker(result, prefix)
    _, stdout, _stderr = product_runner_streams(result)
    assert plain_name in stdout, (
        f"name token {plain_name!r} missing from greeting; "
        f"stdout={stdout!r}"
    )


def test_invoke_runtime_token_greets_that_token_not_another_name():
    prefix = _greeting()
    name = _token()
    other_name = _plain_name()
    while other_name in name or other_name in prefix:
        other_name = _plain_name()
    cli = _hello(prefix)
    result = CliRunner().invoke(cli, [name])
    _observe("runtime-name", result)
    require_runner_success_with_marker(result, prefix)
    _, stdout, _stderr = product_runner_streams(result)
    assert name in stdout, (
        f"runtime token {name!r} missing from greeting; stdout={stdout!r}"
    )
    assert other_name not in stdout, (
        f"runtime token run also greeted the unrelated name {other_name!r}; "
        f"stdout={stdout!r}"
    )


def test_result_exposes_stdout_text_and_bytes():
    marker = _ascii_mark()

    def callback() -> None:
        print(marker, flush=True)

    result = CliRunner().invoke(_cmd(callback), [])
    _observe("text-bytes", result)
    require_runner_text_and_bytes_carry(result, marker)
    code, stdout, _stderr = product_runner_streams(result)
    out_b, _err_b = product_runner_bytes(result)
    assert code == 0, (
        f"expected success exit 0, got {code}; stdout={stdout!r}"
    )
    assert marker in stdout, (
        f"stdout text missing marker {marker!r}; stdout={stdout!r}"
    )
    assert marker.encode("ascii") in out_b, (
        f"stdout bytes missing marker {marker!r}; stdout_bytes={out_b!r}"
    )


def test_invoke_help_exits_zero_shows_help_skips_callback():
    prefix = _greeting()
    description = f"DESC{_letters(12)}path."
    cli = _hello(prefix, description=description)
    runner = CliRunner()
    live = runner.invoke(cli, [_token()])
    helped = runner.invoke(cli, ["--help"])
    _observe("help-live", live)
    _observe("help", helped)
    require_runner_success_with_marker(live, prefix)
    code, stdout, stderr = product_runner_streams(helped)
    assert code == 0, (
        f"intentional help expected exit 0, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    captured = runner_captured_text(helped)
    assert captured.strip(), (
        f"help produced empty captured output; stderr={stderr!r}"
    )
    assert description in captured, (
        f"help missing description {description!r}; captured={captured!r}"
    )
    assert prefix not in captured, (
        f"help ran the callback; greeting {prefix!r} in capture; "
        f"captured={captured!r}"
    )


def test_result_exposes_stderr_separately_from_stdout():
    out_mark = _ascii_mark("OUT")
    err_mark = _ascii_mark("ERR")
    while out_mark in err_mark or err_mark in out_mark:
        out_mark = _ascii_mark("OUT")
        err_mark = _ascii_mark("ERR")

    def callback() -> None:
        echo(out_mark)
        echo(err_mark, err=True)

    result = CliRunner().invoke(_cmd(callback), [])
    _observe("stderr-split", result)
    code, stdout, stderr = product_runner_streams(result)
    assert code == 0, (
        f"expected success exit 0, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert out_mark in stdout, (
        f"stdout missing {out_mark!r}; stdout={stdout!r} stderr={stderr!r}"
    )
    assert err_mark not in stdout, (
        f"stderr mark leaked onto stdout; stdout={stdout!r}"
    )
    assert err_mark in stderr, (
        f"stderr missing {err_mark!r}; stdout={stdout!r} stderr={stderr!r}"
    )
    assert out_mark not in stderr, (
        f"stdout mark leaked onto stderr; stderr={stderr!r}"
    )


def test_subcommand_selected_by_tokens_after_group_option():
    group_mark = _greeting()
    leaf_mark = _ascii_mark("LEAF")
    dest = _word()
    flag = f"--{dest}"
    leaf_name = _word()
    other = unrelated_dispatch_token(leaf_name, dest)

    def root(**kwargs) -> None:
        if kwargs[dest]:
            print(group_mark, flush=True)

    cli = group(name=_word())(option(flag, dest, is_flag=True)(root))

    def leaf() -> None:
        print(leaf_mark, flush=True)

    cli.add_command(command(name=leaf_name)(leaf))

    runner = CliRunner()
    selected = runner.invoke(cli, [flag, leaf_name])
    missing = runner.invoke(cli, [flag])
    wrong = runner.invoke(cli, [flag, other])
    _observe("sub-selected", selected)
    _observe("sub-missing", missing)
    _observe("sub-wrong", wrong)
    require_runner_success_marker_present(selected, group_mark)
    require_runner_success_marker_present(selected, leaf_mark)
    for label, result in (("missing", missing), ("wrong", wrong)):
        captured = runner_captured_text(result)
        assert leaf_mark not in captured, (
            f"{label} argv still ran the leaf; capture={captured!r}"
        )
        assert group_mark not in captured, (
            f"{label} argv still ran the group callback; capture={captured!r}"
        )
        code, stdout, stderr = product_runner_streams(result)
        print(
            f"sub-{label} usage-class exit={code} "
            f"stdout={stdout!r} stderr={stderr!r}",
            flush=True,
        )
        assert code == 2, (
            f"{label} argv expected usage-class exit 2, got {code}; "
            f"stdout={stdout!r} stderr={stderr!r}"
        )
        assert stderr.strip(), (
            f"{label} argv usage-class report missing: stderr is empty; "
            f"stdout={stdout!r} stderr={stderr!r}"
        )


# ---------------------------------------------------------------------------
# B. Input, prompts, echo-every-read, environment
# ---------------------------------------------------------------------------


def test_invoke_input_is_fed_to_stdin():
    line = _ascii_mark("IN")
    salt = _ascii_mark("sal")
    derived = _mark(line, salt)
    empty_mark = _ascii_mark("EMPTY")

    def callback() -> None:
        raw = sys.stdin.readline().rstrip("\r\n")
        print(derived if raw == line else empty_mark, flush=True)
        print(f"SALT:{salt}", flush=True)

    cli = _cmd(callback)
    runner = CliRunner()
    fed = runner.invoke(cli, [], input=f"{line}\n")
    empty = runner.invoke(cli, [], input="")
    _observe("stdin-fed", fed)
    _observe("stdin-empty", empty)
    require_runner_success_marker_present(fed, derived)
    fed_cap = runner_captured_text(fed)
    assert line not in fed_cap.replace(derived, ""), (
        "callback echoed the raw stdin line; capture="
        f"{fed_cap!r}"
    )
    empty_cap = runner_captured_text(empty)
    assert derived not in empty_cap, (
        f"empty input still produced the fed derived mark; capture={empty_cap!r}"
    )
    require_runner_success_marker_present(empty, empty_mark)


def test_visible_prompt_echoes_typed_line_and_shows_prompt():
    greeting = _greeting()
    ask = f"ASK-{uuid.uuid4().hex}"
    secret = f"sec-{uuid.uuid4().hex}"
    salt = _ascii_mark("sal")
    derived = _mark(secret, salt)
    dest = _word()
    flag = f"--{dest}"

    def make(*, hidden: bool):
        def callback(**kwargs) -> None:
            print(greeting, flush=True)
            print(derived if kwargs[dest] == secret else "K:0", flush=True)
            print(f"SALT:{salt}", flush=True)

        return _cmd(callback, option(flag, dest, prompt=ask, hide_input=hidden))

    runner = CliRunner()
    visible = runner.invoke(make(hidden=False), [], input=f"{secret}\n")
    hidden = runner.invoke(make(hidden=True), [], input=f"{secret}\n")
    vis_cap = runner_captured_text(visible)
    hid_cap = runner_captured_text(hidden)
    print(
        f"visible-prompt vis_has_secret={secret in vis_cap} "
        f"hid_has_secret={secret in hid_cap}",
        flush=True,
    )
    _observe("visible", visible)
    _observe("visible-hidden-baseline", hidden)
    require_runner_success_marker_present(visible, greeting)
    require_runner_success_marker_present(visible, derived)
    require_runner_success_marker_present(hidden, derived)
    assert secret in vis_cap, (
        f"visible prompt did not echo {secret!r}; capture={vis_cap!r}"
    )
    assert secret not in hid_cap, (
        f"hidden baseline echoed {secret!r}; capture={hid_cap!r}"
    )


def test_hidden_prompt_does_not_echo_typed_line():
    greeting = _greeting()
    ask = f"ASK-{uuid.uuid4().hex}"
    secret = f"sec-{uuid.uuid4().hex}"
    salt = _ascii_mark("sal")
    derived = _mark(secret, salt)
    dest = _word()
    flag = f"--{dest}"

    def make(*, hidden: bool):
        def callback(**kwargs) -> None:
            print(greeting, flush=True)
            print(derived if kwargs[dest] == secret else "K:0", flush=True)
            print(f"SALT:{salt}", flush=True)

        return _cmd(callback, option(flag, dest, prompt=ask, hide_input=hidden))

    runner = CliRunner()
    visible = runner.invoke(make(hidden=False), [], input=f"{secret}\n")
    hidden = runner.invoke(make(hidden=True), [], input=f"{secret}\n")
    vis_cap = runner_captured_text(visible)
    hid_cap = runner_captured_text(hidden)
    print(
        f"hidden-prompt vis_has_secret={secret in vis_cap} "
        f"hid_has_secret={secret in hid_cap}",
        flush=True,
    )
    _observe("hidden-visible-baseline", visible)
    _observe("hidden", hidden)
    require_runner_success_marker_present(hidden, greeting)
    require_runner_success_marker_present(hidden, derived)
    require_runner_success_marker_present(visible, derived)
    assert secret in vis_cap, (
        f"visible baseline did not echo {secret!r}; capture={vis_cap!r}"
    )
    assert secret not in hid_cap, (
        f"hidden prompt echoed {secret!r}; capture={hid_cap!r}"
    )


def test_optional_mode_echoes_every_stdin_read_not_only_prompts():
    consumed = _ascii_mark("c")
    unread = _ascii_mark("u")
    while consumed in unread or unread in consumed:
        consumed = _ascii_mark("c")
        unread = _ascii_mark("u")
    salt = _ascii_mark("sal")
    derived = _mark(consumed, salt)
    payload = f"{consumed}\n{unread}\n"

    def callback() -> None:
        raw = sys.stdin.readline().rstrip("\r\n")
        print(derived if raw == consumed else "K:0", flush=True)
        print(f"SALT:{salt}", flush=True)

    cli = _cmd(callback)
    default = CliRunner().invoke(cli, [], input=payload)
    echoing = CliRunner(echo_stdin=True).invoke(cli, [], input=payload)
    _observe("echo-default", default)
    _observe("echo-every", echoing)
    require_runner_success_marker_present(default, derived)
    require_runner_success_marker_present(echoing, derived)
    default_cap = runner_captured_text(default)
    echo_cap = runner_captured_text(echoing)
    assert consumed not in default_cap, (
        f"default runner echoed the consumed stdin line; capture={default_cap!r}"
    )
    assert unread not in default_cap, (
        f"default runner captured unread remainder; capture={default_cap!r}"
    )
    assert consumed in echo_cap, (
        f"echo-every-read mode missing consumed line {consumed!r}; "
        f"capture={echo_cap!r}"
    )
    assert unread not in echo_cap, (
        f"echo-every-read mode copied unread remainder; capture={echo_cap!r}"
    )


def test_invoke_environment_is_applied_for_that_run():
    key = f"E{_letters(10).upper()}"
    value = _ascii_mark("v")
    salt = _ascii_mark("sal")
    derived = _mark(value, salt)
    miss = _ascii_mark("MISS")

    def callback() -> None:
        got = os.environ.get(key)
        print(derived if got == value else miss, flush=True)
        print(f"SALT:{salt}", flush=True)

    cli = _cmd(callback)
    runner = CliRunner()
    applied = runner.invoke(cli, [], env={key: value})
    baseline = runner.invoke(cli, [])
    _observe("env-applied", applied)
    _observe("env-baseline", baseline)
    require_runner_success_marker_present(applied, derived)
    require_runner_success_marker_present(baseline, miss)
    base_cap = runner_captured_text(baseline)
    assert derived not in base_cap, (
        f"baseline without env still produced the applied mark; "
        f"capture={base_cap!r}"
    )


# ---------------------------------------------------------------------------
# C. Isolated filesystem
# ---------------------------------------------------------------------------


def test_isolated_filesystem_new_empty_dir_removed_when_no_parent():
    origin = os.getcwd()
    fname = f"f{_ascii_mark()}.txt"
    content = _ascii_mark("body")
    salt = _ascii_mark("sal")
    derived = _mark(content, salt)
    greeting = _greeting()

    def reader(src) -> None:
        data = src.read()
        print(greeting, flush=True)
        print(derived if data == content else "K:0", flush=True)
        print(f"SALT:{salt}", flush=True)

    cli = _cmd(reader, argument("src", type=File("r")))
    runner = CliRunner()
    sandbox: str | None = None
    try:
        with runner.isolated_filesystem():
            sandbox = os.getcwd()
            print(
                f"no-parent origin={origin!r} sandbox={sandbox!r}",
                flush=True,
            )
            assert sandbox != origin, (
                f"isolated filesystem cwd was unchanged; cwd={sandbox!r}"
            )
            listing = os.listdir(sandbox)
            assert listing == [], (
                f"new isolated directory was not empty; listing={listing!r}"
            )
            Path(fname).write_text(content, encoding="utf-8")
            on_disk = Path(sandbox) / fname
            assert on_disk.is_file(), (
                f"relative write is not at recorded cwd {on_disk}"
            )
            assert on_disk.read_text(encoding="utf-8") == content
            assert not (Path(origin) / fname).exists(), (
                f"sandbox file leaked into original cwd {origin}"
            )
            result = runner.invoke(cli, [fname])
            _observe("sandbox-read", result)
            require_runner_success_marker_present(result, greeting)
            require_runner_success_marker_present(result, derived)
        assert sandbox is not None
        assert not Path(sandbox).exists(), (
            f"runner-created directory was left in place; path={sandbox!r}"
        )
        assert not (Path(sandbox) / fname).exists(), (
            f"sandbox file survived removal of {sandbox!r}"
        )
    finally:
        os.chdir(origin)


def test_isolated_filesystem_parent_gets_child_dir_left_in_place():
    origin = os.getcwd()
    fname = f"f{_ascii_mark()}.txt"
    content = _ascii_mark("body")
    greeting = _greeting()
    sentinel_name = f"sent-{_ascii_mark()}"
    sentinel_body = _ascii_mark("sent")

    def writer(dst) -> None:
        dst.write(content)
        dst.flush()
        print(greeting, flush=True)

    cli = _cmd(writer, argument("dst", type=File("w")))
    runner = CliRunner()
    sandbox: str | None = None
    with workspace() as ws:
        parent = ws.path / f"parent-{_ascii_mark()}"
        parent.mkdir()
        (parent / sentinel_name).write_text(sentinel_body, encoding="utf-8")
        try:
            with runner.isolated_filesystem(temp_dir=str(parent)):
                sandbox = os.getcwd()
                sandbox_path = Path(sandbox).resolve()
                parent_path = parent.resolve()
                print(
                    f"parent-arm origin={origin!r} parent={str(parent_path)!r} "
                    f"sandbox={str(sandbox_path)!r}",
                    flush=True,
                )
                assert sandbox_path != Path(origin).resolve(), (
                    f"isolated cwd stayed at origin; cwd={sandbox!r}"
                )
                assert sandbox_path != parent_path, (
                    f"isolated cwd was the parent path itself; cwd={sandbox!r}"
                )
                assert sandbox_path.is_relative_to(parent_path), (
                    f"isolated cwd {sandbox_path} is not under parent "
                    f"{parent_path}"
                )
                listing = os.listdir(sandbox)
                assert sentinel_name not in listing, (
                    f"chdir landed on the parent; listing={listing!r}"
                )
                result = runner.invoke(cli, [fname])
                _observe("sandbox-write", result)
                require_runner_success_marker_present(result, greeting)
                written = sandbox_path / fname
                assert written.is_file(), (
                    f"write-mode file parameter did not create {written}"
                )
                assert written.read_text(encoding="utf-8") == content
                assert not (Path(origin) / fname).exists(), (
                    f"sandbox file leaked into original cwd {origin}"
                )
            assert sandbox is not None
            left = Path(sandbox)
            assert left.is_dir(), (
                f"child directory under parent was removed; path={sandbox!r}"
            )
            assert (left / fname).is_file(), (
                f"written file missing from left-in-place child {left / fname}"
            )
            assert (left / fname).read_text(encoding="utf-8") == content
            assert parent.is_dir(), f"parent directory was removed; {parent}"
            assert (parent / sentinel_name).read_text(encoding="utf-8") == (
                sentinel_body
            )
            assert not (Path(origin) / fname).exists(), (
                f"sandbox file appeared in original cwd after exit; {origin}"
            )
        finally:
            os.chdir(origin)


# ---------------------------------------------------------------------------
# D. Capture modes, context keywords, exceptions
# ---------------------------------------------------------------------------


def _capture_probe_cmd(
    py_mark: str, fd_mark: str, fd_err_mark: str, nofd_mark: str
):
    def callback() -> None:
        echo(py_mark)
        if _stdout_has_usable_fd():
            os.write(1, f"{fd_mark}\n".encode("ascii"))
            os.write(2, f"{fd_err_mark}\n".encode("ascii"))
        else:
            echo(nofd_mark)

    return _cmd(callback)


def test_default_capture_records_interpreter_streams_without_real_fd():
    py_mark = _ascii_mark("PY")
    fd_mark = _ascii_mark("FD")
    fd_err_mark = _ascii_mark("FDE")
    nofd_mark = _ascii_mark("NOFD")
    cli = _capture_probe_cmd(py_mark, fd_mark, fd_err_mark, nofd_mark)
    result = CliRunner().invoke(cli, [])
    _observe("capture-default", result)
    code, stdout, stderr = product_runner_streams(result)
    assert code == 0, (
        f"expected success exit 0, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert py_mark in stdout, (
        f"default capture missed interpreter write {py_mark!r}; "
        f"stdout={stdout!r}"
    )
    captured = runner_captured_text(result)
    assert fd_mark not in captured, (
        f"default capture recorded an OS write to fd 1; capture={captured!r}"
    )
    assert fd_err_mark not in captured, (
        f"default capture recorded an OS write to fd 2; capture={captured!r}"
    )
    assert nofd_mark in captured, (
        f"default capture provided a usable descriptor; capture={captured!r}"
    )


def test_descriptor_capture_records_os_writes_to_fd_1_and_2():
    py_mark = _ascii_mark("PY")
    fd_mark = _ascii_mark("FD")
    fd_err_mark = _ascii_mark("FDE")
    nofd_mark = _ascii_mark("NOFD")
    cli = _capture_probe_cmd(py_mark, fd_mark, fd_err_mark, nofd_mark)
    default = CliRunner().invoke(cli, [])
    captured = CliRunner(capture="fd").invoke(cli, [])
    _observe("fd-default-baseline", default)
    _observe("fd-capture", captured)
    _code, def_out, def_err = product_runner_streams(default)
    assert py_mark in def_out, (
        f"default baseline missed interpreter write; stdout={def_out!r}"
    )
    assert fd_mark not in def_out + def_err, (
        f"default baseline already had the fd-1 mark; "
        f"stdout={def_out!r} stderr={def_err!r}"
    )
    code, stdout, stderr = product_runner_streams(captured)
    assert code == 0, (
        f"descriptor capture expected exit 0, got {code}; "
        f"stdout={stdout!r} stderr={stderr!r}"
    )
    assert fd_mark in stdout, (
        f"descriptor capture missed OS write to fd 1; stdout={stdout!r}"
    )
    _out_b, err_b = product_runner_bytes(captured)
    err_has = fd_err_mark in stderr or fd_err_mark.encode("ascii") in err_b
    assert err_has, (
        f"descriptor capture missed OS write to fd 2 on stderr; "
        f"stderr={stderr!r} stderr_bytes={err_b!r}"
    )
    cap_text = runner_captured_text(captured)
    assert nofd_mark not in cap_text, (
        f"descriptor capture still reported no usable descriptor; "
        f"capture={cap_text!r}"
    )


def test_extra_invoke_keywords_apply_as_context_settings_terminal_width():
    greeting = _greeting()
    narrow = 36
    wide = 100
    words: list[str] = []
    seen: set[str] = set()
    while len(words) < 48:
        word = _letters(5)
        if word in seen:
            continue
        if str(narrow) in word or str(wide) in word:
            continue
        seen.add(word)
        words.append(word)
    paragraph = " ".join(words)

    def callback() -> None:
        print(greeting, flush=True)

    cli = _cmd(callback, help=paragraph, name=_letters(10))
    runner = CliRunner()
    narrow_res = runner.invoke(cli, ["--help"], terminal_width=narrow)
    wide_res = runner.invoke(cli, ["--help"], terminal_width=wide)
    _observe("width-narrow", narrow_res)
    _observe("width-wide", wide_res)
    n_code, n_out, n_err = product_runner_streams(narrow_res)
    w_code, w_out, w_err = product_runner_streams(wide_res)
    assert n_code == 0 and w_code == 0, (
        f"help under terminal_width expected exit 0; "
        f"narrow={n_code} wide={w_code}; "
        f"n_err={n_err!r} w_err={w_err!r}"
    )
    n_cap = runner_captured_text(narrow_res)
    w_cap = runner_captured_text(wide_res)
    assert greeting not in n_cap and greeting not in w_cap, (
        f"help ran the callback; greeting={greeting!r}"
    )
    for word in words:
        assert word in n_out, (
            f"narrow help missing description word {word!r}; stdout={n_out!r}"
        )
        assert word in w_out, (
            f"wide help missing description word {word!r}; stdout={w_out!r}"
        )
    covariates = (*words, str(narrow), str(wide))
    n_rest = failure_report_remainder(n_out, *covariates)
    w_rest = failure_report_remainder(w_out, *covariates)
    print(f"width remainders narrow={n_rest!r} wide={w_rest!r}", flush=True)
    assert n_rest != w_rest, (
        "terminal_width did not change wrapping after stripping description "
        f"words and width digits; narrow_rest={n_rest!r} wide_rest={w_rest!r}"
    )


def test_invoke_color_setting_is_in_force():
    payload = _ascii_mark("PAY")
    plain = _ascii_mark("PLAIN")
    while payload in plain or plain in payload:
        payload = _ascii_mark("PAY")
        plain = _ascii_mark("PLAIN")

    def callback() -> None:
        echo(style(payload, fg="green"))
        echo(plain)

    cli = _cmd(callback)
    runner = CliRunner()
    omitted = runner.invoke(cli, [])
    forced = runner.invoke(cli, [], color=True)
    _observe("color-omitted", omitted)
    _observe("color-on", forced)
    _o_code, o_out, o_err = product_runner_streams(omitted)
    _f_code, f_out, f_err = product_runner_streams(forced)
    require_runner_success_marker_present(omitted, payload)
    require_runner_success_marker_present(forced, payload)
    assert payload in o_out and payload in f_out
    assert not ansi_escape_present(o_out), (
        f"omitted color still kept ANSI on a captured non-terminal; "
        f"stdout={o_out!r} stderr={o_err!r}"
    )
    omitted_payload_lines = [line for line in o_out.splitlines() if payload in line]
    forced_payload_lines = [line for line in f_out.splitlines() if payload in line]
    assert omitted_payload_lines, (
        f"styled payload {payload!r} missing from omitted-color stdout; "
        f"stdout={o_out!r}"
    )
    assert forced_payload_lines, (
        f"styled payload {payload!r} missing from forced-color stdout; "
        f"stdout={f_out!r}"
    )
    omitted_carrier = "\n".join(omitted_payload_lines)
    forced_carrier = "\n".join(forced_payload_lines)
    omitted_rest = styled_text_remainder(omitted_carrier, payload)
    forced_rest = styled_text_remainder(forced_carrier, payload)
    omitted_suffix = styled_text_suffix(omitted_carrier, payload)
    forced_suffix = styled_text_suffix(forced_carrier, payload)
    omitted_at = omitted_carrier.find(payload)
    forced_at = forced_carrier.find(payload)
    omitted_prefix = omitted_carrier[:omitted_at]
    forced_prefix = forced_carrier[:forced_at]
    omitted_visible = unstyle(omitted_carrier)
    forced_visible = unstyle(forced_carrier)
    print(
        f"color payload omitted_rest={omitted_rest!r} forced_rest={forced_rest!r} "
        f"omitted_prefix={omitted_prefix!r} forced_prefix={forced_prefix!r} "
        f"omitted_suffix={omitted_suffix!r} forced_suffix={forced_suffix!r} "
        f"omitted_visible={omitted_visible!r} forced_visible={forced_visible!r}",
        flush=True,
    )
    for line in omitted_payload_lines:
        assert not ansi_escape_present(line), (
            f"omitted-color payload still carries a style sequence; "
            f"line={line!r} stdout={o_out!r}"
        )
    for line in forced_payload_lines:
        assert ansi_escape_present(line), (
            f"forced color did not keep a style sequence on the styled "
            f"payload; line={line!r} stdout={f_out!r} stderr={f_err!r}"
        )
    assert omitted_visible == omitted_carrier, (
        "omitted-color payload still carried sequences unstyle would remove; "
        f"visible={omitted_visible!r} carrier={omitted_carrier!r}"
    )
    assert forced_carrier != omitted_carrier, (
        "forced-color styled payload matches the omitted-color payload; "
        "no style sequence was kept on the payload; "
        f"forced={forced_carrier!r} omitted={omitted_carrier!r}"
    )
    assert forced_visible == omitted_carrier, (
        "forced-color styled payload, after unstyle, does not match the "
        "omitted-color unstyled payload; the kept wrap must be sequences "
        f"unstyling removes; forced_visible={forced_visible!r} "
        f"omitted={omitted_carrier!r} forced={forced_carrier!r}"
    )
    assert forced_rest != omitted_rest, (
        "forced-color styled payload remainder matches the omitted-color "
        f"remainder after stripping {payload!r}; "
        f"forced={forced_rest!r} omitted={omitted_rest!r}"
    )
    assert ansi_escape_present(forced_rest), (
        "forced-color payload remainder has no style sequence after "
        f"stripping {payload!r}; remainder={forced_rest!r} stdout={f_out!r}"
    )
    assert not ansi_escape_present(omitted_prefix), (
        "omitted-color payload still carries a style sequence before the "
        f"payload; prefix={omitted_prefix!r} stdout={o_out!r}"
    )
    assert not ansi_escape_present(omitted_suffix), (
        "omitted-color payload still carries a style sequence after the "
        f"payload; suffix={omitted_suffix!r} stdout={o_out!r}"
    )
    assert ansi_escape_present(forced_prefix), (
        "forced color did not keep a style sequence before the styled "
        f"payload; prefix={forced_prefix!r} stdout={f_out!r} stderr={f_err!r}"
    )
    assert ansi_escape_present(forced_suffix), (
        "forced color did not keep a style sequence after the styled "
        f"payload; suffix={forced_suffix!r} stdout={f_out!r} stderr={f_err!r}"
    )
    assert unstyle(forced_prefix) != forced_prefix, (
        "forced-color wrap before the payload is not a sequence unstyle "
        f"removes; prefix={forced_prefix!r} stdout={f_out!r}"
    )
    assert unstyle(forced_suffix) != forced_suffix, (
        "forced-color wrap after the payload is not a sequence unstyle "
        f"removes; suffix={forced_suffix!r} stdout={f_out!r}"
    )
    assert plain in f_out, (
        f"unstyled mark {plain!r} missing from color-on stdout; "
        f"stdout={f_out!r}"
    )
    plain_lines = [line for line in f_out.splitlines() if plain in line]
    assert plain_lines, (
        f"unstyled mark {plain!r} not on its own line; stdout={f_out!r}"
    )
    for line in plain_lines:
        assert not ansi_escape_present(line), (
            f"unstyled mark line still carries ESC; line={line!r} "
            f"stdout={f_out!r}"
        )


def test_standalone_raise_returns_result_with_status_and_inspectable_exception():
    token = _ascii_mark("EXC")
    greeting = _greeting()

    def boom() -> None:
        raise RuntimeError(token)

    def ok() -> None:
        print(greeting, flush=True)

    runner = CliRunner()
    raised = runner.invoke(_cmd(boom), [])
    success = runner.invoke(_cmd(ok), [])
    print(f"standalone-raise returned type={type(raised)!r}", flush=True)
    _observe("standalone-raise", raised)
    _observe("standalone-ok", success)
    require_runner_exception_inspectable(raised, token)
    require_runner_success_with_marker(success, greeting)
    require_runner_no_exception(success)
    try:
        success_exc = success.exception
    except Exception as err:
        raise RuntimeError(f"failed to read success exception: {err}") from err
    if success_exc:
        shown = str(success_exc)
        assert token not in shown, (
            f"success result carried the raise token {token!r}; "
            f"exception={success_exc!r}"
        )


def test_runner_told_not_to_catch_propagates():
    token = _ascii_mark("EXC")

    def boom() -> None:
        raise RuntimeError(token)

    cli = _cmd(boom)
    runner = CliRunner()
    exc = require_failure_propagates(
        lambda: runner.invoke(cli, [], catch_exceptions=False)
    )
    print(f"propagated={type(exc).__name__}:{exc!r}", flush=True)
    shown = str(exc)
    pictured = repr(exc)
    assert token in shown or token in pictured, (
        f"propagated failure does not carry token {token!r}; "
        f"str={shown!r} repr={pictured!r}"
    )


def test_non_standalone_exposes_exception_on_result():
    token = _ascii_mark("EXC")

    def boom() -> None:
        raise RuntimeError(token)

    result = CliRunner().invoke(_cmd(boom), [], standalone_mode=False)
    print(f"non-standalone returned type={type(result)!r}", flush=True)
    _observe("non-standalone-raise", result)
    require_runner_exception_inspectable(result, token)
    try:
        exc = result.exception
    except Exception as err:
        raise RuntimeError(f"failed to read result exception: {err}") from err
    assert exc, (
        "non-standalone invoke returned without an inspectable exception; "
        f"got {exc!r}"
    )
    shown = str(exc)
    pictured = repr(exc)
    assert token in shown or token in pictured, (
        f"exception object does not carry token {token!r}; "
        f"str={shown!r} repr={pictured!r}"
    )
