# feature: F11
"""Terminal output and interaction helpers (FP-11).

Assertions stay at the PRD's precision: echo text/binary, newline,
standard error, Unicode on a misconfigured ASCII stream; strip/keep
styles on pipe vs tty and invocation force on/off; named/0-255/RGB
colors and independent switches; invalid colors fail the style call;
styled echo in one step; unstyling; pager string/chunks/writable
stream, non-interactive no-launch, flush, borrowed stdout stays open;
progress-bar visits, label-once vs hidden, tty snapshots, delta
update, known vs unknown length, remaining-time estimate when length
is known; getchar from the terminal; interrupt vs EOF; pause; editor
save/absent; application launch of a URL or filename; screen clear;
Linux, macOS, and Windows application directory.
CSI opcodes, exception types, pager color-flag spelling, ETA clock
wording, pause prompt text, opener executable names, and Python None
as the spelling of absent are not pinned. Default style reset is
observed as a sequence after the payload so a later unstyled write is
not still inside the wrap. Pager keep-styles is observed when the
destination supports styles.
"""

from __future__ import annotations

import codecs
import sys
import uuid
from pathlib import Path as FSPath

from optlyn import (
    clear,
    command,
    echo,
    echo_via_pager,
    edit,
    get_app_dir,
    get_pager_file,
    getchar,
    launch,
    pause,
    progressbar,
    secho,
    style,
    unstyle,
)

from _harness import invoke, workspace
from _helpers import (
    ansi_escape_present,
    application_launch_record,
    failure_report_remainder,
    labeled_stdout_field,
    posix_app_slug,
    recording_default_application,
    require_ansi_escape_absent,
    require_ansi_escape_present,
    require_completed_within,
    require_failure_propagates,
    require_success_marker_present,
    run_python_on_tty,
    run_python_on_tty_blocked_until_feed,
    run_python_pipe_stdin_controlling_tty,
    start_python_on_tty,
    styled_stdout_remainder,
    styled_text_remainder,
    styled_text_suffix,
    unrelated_dispatch_token,
)

PROG = "app"

NAMED_COLORS = (
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    "bright_black",
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
    "bright_white",
    "reset",
)

STYLE_SWITCHES = (
    "bold",
    "dim",
    "underline",
    "overline",
    "italic",
    "blink",
    "reverse",
    "strikethrough",
)

_PAGER_RECORDER = (
    "import sys\n"
    "path = sys.argv[1]\n"
    "with open(path, 'wb') as fh:\n"
    "    fh.write(b'LAUNCHED\\n')\n"
    "    fh.flush()\n"
    "    while True:\n"
    "        chunk = sys.stdin.buffer.read(1)\n"
    "        if not chunk:\n"
    "            break\n"
    "        fh.write(chunk)\n"
    "        fh.flush()\n"
)


def _word() -> str:
    return "k" + uuid.uuid4().hex[:8]


def _greeting() -> str:
    return f"GREET:{uuid.uuid4().hex}:"


def _payload() -> str:
    return f"P{uuid.uuid4().hex[:12]}"


def _cmd(callback, **command_kwargs):
    command_kwargs.setdefault("name", _word())
    return command(**command_kwargs)(callback)


def _dispatch(cli, args=None, **kwargs):
    kwargs.setdefault("prog_name", PROG)
    return invoke(cli, args if args is not None else [], **kwargs)


def _stdout(result) -> str:
    text = result.stdout_text
    if text is None:
        raise RuntimeError("stdout is None; cannot observe")
    return text


def _remainder(text: str, *covariates: str) -> str:
    if text is None:
        raise RuntimeError("text is None; cannot strip covariates")
    for item in covariates:
        if item:
            text = text.replace(item, "")
    return text


def _encoding_report(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("ENCREPORT:"):
            return line.split(":", 1)[1]
    raise AssertionError(f"child did not report environment encoding: {text!r}")


def _canonical_encoding(name: str) -> str:
    try:
        return codecs.lookup(name).name
    except LookupError as exc:
        raise AssertionError(f"child reported unknown encoding {name!r}") from exc


def _pager_cmd(recorder: FSPath, sentinel: FSPath) -> str:
    return f"{sys.executable} {recorder} {sentinel}"


def _style_tty_script(payload: str, greeting: str, color_expr: str, styled: bool) -> str:
    wrap = "echo(style(PAYLOAD, fg='green'))" if styled else "echo(PAYLOAD)"
    return (
        "from optlyn import command, echo, style\n"
        f"GREET = {greeting!r}\n"
        f"PAYLOAD = {payload!r}\n"
        "def callback():\n"
        "    print(GREET, flush=True)\n"
        f"    {wrap}\n"
        "leaf = command()(callback)\n"
        f"leaf.main(args=[], standalone_mode=True, prog_name='app', color={color_expr})\n"
    )


def _pager_tty_script(payload: str, greeting: str, styled: bool) -> str:
    wrap = (
        "echo_via_pager(style(PAYLOAD, fg='green'))"
        if styled
        else "echo_via_pager(PAYLOAD)"
    )
    return (
        "import os\n"
        "os.environ['TERM'] = 'xterm'\n"
        "os.environ['LESS'] = '-RFEX'\n"
        "from optlyn import echo_via_pager, style\n"
        f"GREET = {greeting!r}\n"
        f"PAYLOAD = {payload!r}\n"
        "print(GREET, flush=True)\n"
        f"{wrap}\n"
    )


# ---------------------------------------------------------------------------
# A. Echo: text/binary, newline, stderr, Unicode on ASCII
# ---------------------------------------------------------------------------


def test_echo_writes_text_to_stdout_with_trailing_newline():
    samples = ("Hello", _payload())
    for payload in samples:
        def callback(message=payload) -> None:
            echo(message)

        result = _dispatch(_cmd(callback), [])
        print(f"echo-nl payload={payload!r} stdout={result.stdout_text!r}", flush=True)
        assert result.exit_code == 0, (
            f"echo expected exit 0, got {result.exit_code}; "
            f"stderr={result.stderr_text!r}"
        )
        text = _stdout(result)
        assert text == payload + "\n", (
            f"echo of {payload!r} was not that line on stdout; stdout={text!r}"
        )


def test_echo_suppressed_newline_does_not_append_newline():
    payload = _payload()

    def with_nl() -> None:
        echo(payload)

    def without_nl() -> None:
        echo(payload, nl=False)

    default = _dispatch(_cmd(with_nl), [])
    suppressed = _dispatch(_cmd(without_nl), [])
    print(
        f"default={default.stdout_text!r} suppressed={suppressed.stdout_text!r}",
        flush=True,
    )
    assert default.exit_code == 0 and suppressed.exit_code == 0
    assert _stdout(default) == payload + "\n"
    assert _stdout(suppressed) == payload
    assert _stdout(default) != _stdout(suppressed)


def test_echo_error_stream_flag_writes_stderr_not_stdout():
    greeting = _greeting()
    payload = _payload()

    def callback() -> None:
        print(greeting, flush=True)
        echo(payload, err=True)

    result = _dispatch(_cmd(callback), [])
    print(
        f"err-flag stdout={result.stdout_text!r} stderr={result.stderr_text!r}",
        flush=True,
    )
    require_success_marker_present(result, greeting)
    assert payload not in _stdout(result), (
        f"error-stream echo leaked payload onto stdout; stdout={result.stdout_text!r}"
    )
    assert payload in result.stderr_text, (
        f"error-stream echo missing payload on stderr; stderr={result.stderr_text!r}"
    )


def test_echo_writes_binary_payload():
    payload = b"B\x00\xff\xfe" + uuid.uuid4().bytes

    def callback() -> None:
        echo(payload, nl=False)

    result = _dispatch(_cmd(callback), [])
    print(f"binary stdout={result.stdout!r}", flush=True)
    assert result.exit_code == 0, (
        f"binary echo expected exit 0, got {result.exit_code}; "
        f"stderr={result.stderr_text!r}"
    )
    assert payload in result.stdout, (
        f"binary payload missing from raw stdout; stdout={result.stdout!r}"
    )


def test_echo_unicode_survives_misconfigured_ascii_stream():
    greeting = "GREETUNI"
    payload = "雪" + uuid.uuid4().hex[:8] + "\u2603"
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
        "plain_failed = False\n"
        "try:\n"
        f"    sys.stdout.write({payload!r})\n"
        "    sys.stdout.flush()\n"
        "    print('PLAIN:OK', flush=True)\n"
        "except Exception:\n"
        "    plain_failed = True\n"
        "    print('PLAIN:FAIL', flush=True)\n"
        "from optlyn import command, echo\n"
        "\n"
        "@command()\n"
        "def cli():\n"
        f"    print({greeting!r}, flush=True)\n"
        f"    echo({payload!r})\n"
        "\n"
        "cli.main()\n"
    )
    with workspace() as ws:
        path = ws.write("uni.py", script)
        ascii_run = ws.run_python(
            argv=["-X", "utf8=0", str(path)],
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
    assert "PLAIN:FAIL" in ascii_run.stdout_text, (
        "ordinary write of the Unicode payload did not fail on the ASCII stream; "
        f"stdout={ascii_run.stdout_text!r}"
    )
    assert "PLAIN:OK" not in ascii_run.stdout_text
    require_success_marker_present(ascii_run, greeting)
    assert payload in ascii_run.stdout_text, (
        f"echo lost Unicode payload on ASCII stream; stdout={ascii_run.stdout_text!r}"
    )


# ---------------------------------------------------------------------------
# B. Echo strip/keep and invocation force color
# ---------------------------------------------------------------------------


def test_echo_autodetect_strips_styles_on_pipe():
    greeting = _greeting()
    payload = _payload()

    def callback() -> None:
        print(greeting, flush=True)
        echo(style(payload, fg="green"))

    leaf = _cmd(callback)
    forced = _dispatch(leaf, [], color=True)
    auto = _dispatch(leaf, [])
    print(f"forced={forced.stdout_text!r} auto={auto.stdout_text!r}", flush=True)
    require_success_marker_present(forced, greeting)
    require_ansi_escape_present(forced)
    require_success_marker_present(auto, greeting)
    assert payload in _stdout(auto)
    require_ansi_escape_absent(auto)


def test_echo_autodetect_keeps_styles_on_terminal():
    greeting = _greeting()
    payload = _payload()
    styled = run_python_on_tty(_style_tty_script(payload, greeting, "None", True))
    plain = run_python_on_tty(_style_tty_script(payload, greeting, "None", False))
    print(
        f"pty-styled={styled.stdout_text!r} pty-plain={plain.stdout_text!r} "
        f"rc={styled.returncode}/{plain.returncode}",
        flush=True,
    )
    assert styled.returncode == 0, f"pty styled echo failed; stdout={styled.stdout_text!r}"
    assert plain.returncode == 0, f"pty plain echo failed; stdout={plain.stdout_text!r}"
    assert greeting in styled.stdout_text and payload in styled.stdout_text
    require_ansi_escape_present(styled)
    assert payload in plain.stdout_text
    styled_rest = styled_stdout_remainder(styled, payload)
    plain_rest = styled_stdout_remainder(plain, payload)
    assert styled_rest != plain_rest, (
        f"tty autodetect styled and plain remainders match after stripping "
        f"{payload!r}; styled={styled_rest!r} plain={plain_rest!r}"
    )


def test_echo_force_color_on_keeps_named_style_on_pipe():
    greeting = _greeting()
    payload = _payload()

    def styled() -> None:
        print(greeting, flush=True)
        echo(style(payload, fg="green"))

    def plain() -> None:
        print(greeting, flush=True)
        echo(payload)

    on_styled = _dispatch(_cmd(styled), [], color=True)
    on_plain = _dispatch(_cmd(plain), [], color=True)
    print(
        f"on-styled={on_styled.stdout_text!r} on-plain={on_plain.stdout_text!r}",
        flush=True,
    )
    require_success_marker_present(on_styled, greeting)
    assert payload in _stdout(on_styled)
    require_ansi_escape_present(on_styled)
    require_success_marker_present(on_plain, greeting)
    styled_rest = styled_stdout_remainder(on_styled, payload)
    plain_rest = styled_stdout_remainder(on_plain, payload)
    assert styled_rest != plain_rest, (
        f"force-on styled and plain remainders match after stripping "
        f"{payload!r}; styled={styled_rest!r} plain={plain_rest!r}"
    )


def test_echo_force_color_off_strips_styles_on_terminal():
    greeting = _greeting()
    payload = _payload()
    auto = run_python_on_tty(_style_tty_script(payload, greeting, "None", True))
    off = run_python_on_tty(_style_tty_script(payload, greeting, "False", True))
    print(
        f"pty-auto={auto.stdout_text!r} pty-off={off.stdout_text!r}",
        flush=True,
    )
    assert auto.returncode == 0, f"pty autodetect failed; stdout={auto.stdout_text!r}"
    assert off.returncode == 0, f"pty force-off failed; stdout={off.stdout_text!r}"
    assert payload in auto.stdout_text
    require_ansi_escape_present(auto)
    assert payload in off.stdout_text
    require_ansi_escape_absent(off)


# ---------------------------------------------------------------------------
# C. Style, invalid colors, styled echo, unstyle
# ---------------------------------------------------------------------------


def test_named_foreground_colors_each_wrap_and_differ():
    payload = _payload()
    omitted = style(payload)
    remainders: list[str] = []
    for name in NAMED_COLORS:
        wrapped = style(payload, fg=name)
        print(f"fg {name} wrapped={wrapped!r}", flush=True)
        assert wrapped != payload
        assert ansi_escape_present(wrapped), (
            f"named foreground {name!r} produced no ANSI sequence; wrapped={wrapped!r}"
        )
        rest = styled_text_remainder(wrapped, payload)
        omitted_rest = styled_text_remainder(omitted, payload)
        assert rest != omitted_rest, (
            f"foreground {name!r} remainder matches omitted color; rest={rest!r}"
        )
        remainders.append(rest)
    assert any(
        remainders[i] != remainders[j]
        for i in range(len(remainders))
        for j in range(i + 1, len(remainders))
    ), f"all named foreground remainders are identical; remainders={remainders!r}"


def test_named_background_colors_each_wrap_unlike_foreground():
    payload = _payload()
    bg_remainders: list[str] = []
    for name in NAMED_COLORS:
        foreground = style(payload, fg=name)
        background = style(payload, bg=name)
        print(f"bg {name} wrapped={background!r}", flush=True)
        assert ansi_escape_present(background), (
            f"named background {name!r} produced no ANSI sequence; wrapped={background!r}"
        )
        bg_rest = styled_text_remainder(background, payload)
        fg_rest = styled_text_remainder(foreground, payload)
        assert bg_rest != fg_rest, (
            f"background {name!r} remainder matches same-name foreground; "
            f"bg={bg_rest!r} fg={fg_rest!r}"
        )
        bg_remainders.append(bg_rest)
    assert any(
        bg_remainders[i] != bg_remainders[j]
        for i in range(len(bg_remainders))
        for j in range(i + 1, len(bg_remainders))
    ), f"all named background remainders are identical; remainders={bg_remainders!r}"


def test_integer_and_rgb_colors_wrap_boundaries_valid():
    payload = _payload()
    omitted = styled_text_remainder(style(payload), payload)
    runtime = 1 + uuid.uuid4().int % 253
    rgb = (
        uuid.uuid4().int % 256,
        uuid.uuid4().int % 256,
        uuid.uuid4().int % 256,
    )
    for color in (0, 255, runtime):
        wrapped = style(payload, fg=color)
        print(f"int color={color} wrapped={wrapped!r}", flush=True)
        assert ansi_escape_present(wrapped)
        rest = styled_text_remainder(wrapped, payload)
        assert rest != omitted, (
            f"integer color {color} remainder matches omitted; rest={rest!r}"
        )
    rgb_wrapped = style(payload, fg=rgb)
    print(f"rgb color={rgb} wrapped={rgb_wrapped!r}", flush=True)
    assert ansi_escape_present(rgb_wrapped)
    rgb_rest = styled_text_remainder(rgb_wrapped, payload)
    assert rgb_rest != omitted, (
        f"RGB {rgb} remainder matches omitted; rest={rgb_rest!r}"
    )


def test_independent_style_switches_each_wrap_and_differ():
    payload = _payload()
    off_rest = styled_text_remainder(style(payload), payload)
    remainders: dict[str, str] = {}
    for switch in STYLE_SWITCHES:
        wrapped = style(payload, **{switch: True})
        print(f"switch {switch} wrapped={wrapped!r}", flush=True)
        rest = styled_text_remainder(wrapped, payload)
        assert rest != off_rest, (
            f"switch {switch} remainder matches all-off; rest={rest!r}"
        )
        remainders[switch] = rest
    assert any(
        remainders[a] != remainders[b]
        for i, a in enumerate(STYLE_SWITCHES)
        for b in STYLE_SWITCHES[i + 1 :]
    ), f"all switch remainders are identical; remainders={remainders!r}"
    combined = style(payload, bold=True, underline=True)
    combined_rest = styled_text_remainder(combined, payload)
    print(f"bold+underline wrapped={combined!r}", flush=True)
    assert combined_rest != remainders["bold"], (
        f"two-switch remainder matches bold-only; combined={combined_rest!r}"
    )
    assert combined_rest != remainders["underline"], (
        f"two-switch remainder matches underline-only; combined={combined_rest!r}"
    )


def test_invalid_colors_fail_the_style_call_not_as_omitted():
    payload = _payload()
    omitted = style(payload)
    bad_name = unrelated_dispatch_token(*NAMED_COLORS)
    cases = (
        lambda: style(payload, fg=bad_name),
        lambda: style(payload, fg=256),
        lambda: style(payload, fg=-1),
        lambda: style(payload, fg=(1, 2, 3, 4)),
        lambda: style(payload, fg=(1, 2, 256)),
    )
    for index, call in enumerate(cases):
        exc = require_failure_propagates(call)
        print(f"invalid[{index}] raised {type(exc).__name__}", flush=True)
    assert omitted == payload or payload in omitted
    plain = style(payload)
    assert plain is not None
    assert payload in plain


def test_two_integer_color_sequence_fails_the_style_call():
    payload = _payload()
    left = 10 + uuid.uuid4().int % 40
    right = 50 + uuid.uuid4().int % 40
    omitted = style(payload)
    exc = require_failure_propagates(lambda: style(payload, fg=(left, right)))
    print(
        f"two-int {(left, right)} raised {type(exc).__name__} omitted={omitted!r}",
        flush=True,
    )
    assert payload in omitted


def test_styled_echo_is_echo_plus_styling_in_one_step():
    greeting = _greeting()
    payload = _payload()

    def styled() -> None:
        print(greeting, flush=True)
        secho(payload, fg="green")

    def plain() -> None:
        print(greeting, flush=True)
        echo(payload)

    on_styled = _dispatch(_cmd(styled), [], color=True)
    on_plain = _dispatch(_cmd(plain), [], color=True)
    auto = _dispatch(_cmd(styled), [])
    print(
        f"secho-on={on_styled.stdout_text!r} secho-plain={on_plain.stdout_text!r} "
        f"secho-auto={auto.stdout_text!r}",
        flush=True,
    )
    require_success_marker_present(on_styled, greeting)
    assert payload in _stdout(on_styled)
    require_ansi_escape_present(on_styled)
    require_success_marker_present(on_plain, greeting)
    styled_rest = styled_stdout_remainder(on_styled, payload)
    plain_rest = styled_stdout_remainder(on_plain, payload)
    assert styled_rest != plain_rest, (
        f"one-step styled and plain remainders match; styled={styled_rest!r} "
        f"plain={plain_rest!r}"
    )
    require_success_marker_present(auto, greeting)
    assert payload in _stdout(auto)
    require_ansi_escape_absent(auto)


def test_unstyling_removes_ansi_sequences():
    payload = _payload()
    wrapped = style(payload, fg="green")
    print(f"wrapped={wrapped!r} unstyled={unstyle(wrapped)!r}", flush=True)
    assert wrapped != payload
    assert unstyle(wrapped) == payload
    assert unstyle(payload) == payload
    assert not ansi_escape_present(unstyle(wrapped))


def test_style_default_reset_does_not_leak_into_later_text():
    first = _payload()
    later = _payload()
    wrapped = style(first, fg="green")
    suffix = styled_text_suffix(wrapped, first)
    print(
        f"wrapped={wrapped!r} suffix={suffix!r} later={later!r}",
        flush=True,
    )
    assert ansi_escape_present(wrapped)
    assert ansi_escape_present(suffix), (
        "default style wrap did not append a reset after the payload; "
        f"suffix={suffix!r} wrapped={wrapped!r}"
    )
    combined = wrapped + later
    together = style(first + later, fg="green")
    assert combined != together, (
        "later unstyled text is still inside the same wrap as the styled "
        f"payload; combined={combined!r} together={together!r}"
    )
    assert unstyle(combined) == first + later
    assert styled_text_suffix(combined, first).endswith(later), (
        "later unstyled write is missing after the styled payload; "
        f"combined={combined!r}"
    )
    between = styled_text_suffix(combined, first).replace(later, "")
    assert ansi_escape_present(between), (
        "later unstyled write is still styled: no reset between the "
        f"payload and later text; between={between!r} combined={combined!r}"
    )

    def sequential() -> None:
        echo(wrapped, nl=False)
        echo(later, nl=False)

    result = _dispatch(_cmd(sequential), [], color=True)
    print(f"sequential stdout={result.stdout_text!r}", flush=True)
    assert result.exit_code == 0, (
        f"styled-then-later echo expected exit 0, got {result.exit_code}; "
        f"stderr={result.stderr_text!r}"
    )
    text = _stdout(result)
    assert first in text and later in text
    seq_between = styled_text_suffix(text, first).replace(later, "")
    assert ansi_escape_present(seq_between), (
        "later unstyled echo is still styled: no reset after the styled "
        f"payload; between={seq_between!r} stdout={text!r}"
    )


# ---------------------------------------------------------------------------
# D. Pager
# ---------------------------------------------------------------------------


def test_pager_noninteractive_writes_stdout_without_launching_pager():
    greeting = _greeting()
    payload = _payload()
    with workspace() as ws:
        recorder = ws.write("recorder.py", _PAGER_RECORDER)
        silent = ws.path / f"sent-off-{uuid.uuid4().hex}"
        live = ws.path / f"sent-on-{uuid.uuid4().hex}"

        def callback() -> None:
            print(greeting, flush=True)
            echo_via_pager(payload)

        dumped = ws.invoke(
            _cmd(callback), [], env={"PAGER": _pager_cmd(recorder, silent)}
        )
        print(
            f"nonint stdout={dumped.stdout_text!r} sentinel_exists={silent.exists()}",
            flush=True,
        )
        require_success_marker_present(dumped, greeting)
        assert payload in _stdout(dumped)
        assert not silent.exists(), (
            f"non-interactive pager launched; sentinel={silent} "
            f"bytes={silent.read_bytes() if silent.exists() else b''!r}"
        )

        code = (
            "import os\n"
            f"os.environ['PAGER'] = {_pager_cmd(recorder, live)!r}\n"
            "from optlyn import echo_via_pager\n"
            f"echo_via_pager({payload!r})\n"
        )
        launched = run_python_on_tty(code)
        print(
            f"int rc={launched.returncode} live_exists={live.exists()} "
            f"live={live.read_bytes() if live.exists() else b''!r}",
            flush=True,
        )
        assert launched.returncode == 0, (
            f"interactive pager run failed; stdout={launched.stdout_text!r}"
        )
        assert live.is_file(), "interactive pager did not launch the recording PAGER"
        live_bytes = live.read_bytes()
        assert payload.encode("utf-8") in live_bytes, (
            f"interactive pager sentinel missing payload; bytes={live_bytes!r}"
        )


def test_pager_string_chunk_iterator_and_writable_stream_deliver_text():
    greeting = _greeting()
    first, second = _payload(), _payload()

    def as_string() -> None:
        print(greeting, flush=True)
        echo_via_pager(first + second)

    def as_chunks() -> None:
        print(greeting, flush=True)
        echo_via_pager(iter((first, second)))

    def as_stream() -> None:
        print(greeting, flush=True)
        with get_pager_file() as pager:
            pager.write(first)
            pager.write(second)

    for label, factory in (
        ("string", as_string),
        ("chunks", as_chunks),
        ("stream", as_stream),
    ):
        result = _dispatch(_cmd(factory), [])
        print(f"{label} stdout={result.stdout_text!r}", flush=True)
        require_success_marker_present(result, greeting)
        text = _stdout(result)
        assert first in text and second in text, (
            f"{label} pager entry missing words; stdout={text!r}"
        )


def test_pager_writable_stream_launches_when_interactive():
    payload = _payload()
    with workspace() as ws:
        recorder = ws.write("recorder.py", _PAGER_RECORDER)
        sentinel = ws.path / f"sent-stream-{uuid.uuid4().hex}"
        code = (
            "import os\n"
            f"os.environ['PAGER'] = {_pager_cmd(recorder, sentinel)!r}\n"
            "from optlyn import get_pager_file\n"
            f"PAYLOAD = {payload!r}\n"
            "with get_pager_file() as pager:\n"
            "    pager.write(PAYLOAD)\n"
            "    pager.flush()\n"
        )
        result = run_python_on_tty(code)
        print(
            f"stream-int rc={result.returncode} exists={sentinel.exists()} "
            f"bytes={sentinel.read_bytes() if sentinel.exists() else b''!r}",
            flush=True,
        )
        assert result.returncode == 0, (
            f"writable-stream interactive pager failed; stdout={result.stdout_text!r}"
        )
        assert sentinel.is_file(), (
            "writable pager stream did not launch PAGER when interactive"
        )
        assert payload.encode("utf-8") in sentinel.read_bytes()


def test_pager_flushes_chunks_before_generator_finishes():
    first, second = _payload(), _payload()
    with workspace() as ws:
        recorder = ws.write("recorder.py", _PAGER_RECORDER)
        sentinel = ws.path / f"sent-flush-{uuid.uuid4().hex}"
        code = (
            "import os, time\n"
            f"SENTINEL = {str(sentinel)!r}\n"
            f"os.environ['PAGER'] = {_pager_cmd(recorder, sentinel)!r}\n"
            "from optlyn import echo_via_pager\n"
            f"A = {first!r}\n"
            f"B = {second!r}\n"
            "def chunks():\n"
            "    yield A\n"
            "    deadline = time.monotonic() + 8\n"
            "    while time.monotonic() < deadline:\n"
            "        try:\n"
            "            data = open(SENTINEL, 'rb').read()\n"
            "        except OSError:\n"
            "            data = b''\n"
            "        if A.encode('utf-8') in data:\n"
            "            break\n"
            "        time.sleep(0.05)\n"
            "    else:\n"
            "        raise SystemExit('chunk A never flushed')\n"
            "    yield B\n"
            "echo_via_pager(chunks())\n"
        )
        result = run_python_on_tty(code)
        print(
            f"flush rc={result.returncode} stdout={result.stdout_text!r} "
            f"sent={sentinel.read_bytes() if sentinel.exists() else b''!r}",
            flush=True,
        )
        assert result.returncode == 0, (
            f"chunked pager did not flush before the generator finished; "
            f"stdout={result.stdout_text!r} stderr={result.stderr_text!r}"
        )
        assert sentinel.is_file()
        body = sentinel.read_bytes()
        assert first.encode("utf-8") in body and second.encode("utf-8") in body


def test_pager_does_not_close_process_stdout():
    greeting = _greeting()
    first, second = _payload(), _payload()

    def after_string() -> None:
        print(greeting, flush=True)
        echo_via_pager(first)
        echo(second)

    def after_stream() -> None:
        print(greeting, flush=True)
        with get_pager_file() as pager:
            pager.write(first)
        echo(second)

    for label, factory in (("string", after_string), ("stream", after_stream)):
        result = _dispatch(_cmd(factory), [])
        print(f"keep-open {label} stdout={result.stdout_text!r}", flush=True)
        require_success_marker_present(result, greeting)
        text = _stdout(result)
        assert first in text and second in text, (
            f"pager {label} closed stdout or dropped the second write; stdout={text!r}"
        )


def test_pager_strips_styles_when_destination_is_not_a_terminal():
    greeting = _greeting()
    payload = _payload()
    wrapped = style(payload, fg="green")
    assert ansi_escape_present(wrapped)

    def callback() -> None:
        print(greeting, flush=True)
        echo_via_pager(wrapped)

    result = _dispatch(_cmd(callback), [])
    print(f"pager-strip stdout={result.stdout_text!r}", flush=True)
    require_success_marker_present(result, greeting)
    assert payload in _stdout(result)
    require_ansi_escape_absent(result)


def test_pager_keeps_styles_when_destination_supports_styles():
    greeting = _greeting()
    payload = _payload()
    wrapped = style(payload, fg="green")
    assert ansi_escape_present(wrapped)

    def unsupported() -> None:
        print(greeting, flush=True)
        echo_via_pager(wrapped)

    stripped = _dispatch(_cmd(unsupported), [])
    kept = run_python_on_tty(_pager_tty_script(payload, greeting, True))
    plain = run_python_on_tty(_pager_tty_script(payload, greeting, False))
    print(
        f"pager-unsupported={stripped.stdout_text!r} "
        f"pager-tty-styled={kept.stdout_text!r} "
        f"pager-tty-plain={plain.stdout_text!r} "
        f"rc={kept.returncode}/{plain.returncode}",
        flush=True,
    )
    require_success_marker_present(stripped, greeting)
    assert payload in _stdout(stripped)
    require_ansi_escape_absent(stripped)
    assert kept.returncode == 0, (
        f"tty pager styled run failed; stdout={kept.stdout_text!r}"
    )
    assert plain.returncode == 0, (
        f"tty pager plain run failed; stdout={plain.stdout_text!r}"
    )
    assert greeting in kept.stdout_text and payload in kept.stdout_text
    assert payload in plain.stdout_text
    keep_rest = styled_stdout_remainder(kept, payload)
    plain_rest = styled_stdout_remainder(plain, payload)
    strip_rest = styled_stdout_remainder(stripped, payload)
    assert keep_rest != plain_rest, (
        "style-supporting pager destination remainder matches the unstyled "
        f"twin after removing {payload!r}; "
        f"kept={keep_rest!r} plain={plain_rest!r}"
    )
    assert keep_rest != strip_rest, (
        "style-supporting pager destination remainder matches the stripped "
        f"destination after removing {payload!r}; "
        f"kept={keep_rest!r} stripped={strip_rest!r}"
    )


# ---------------------------------------------------------------------------
# E. Progress bar
# ---------------------------------------------------------------------------


def test_progress_bar_visits_every_item_without_a_terminal():
    greeting = _greeting()
    items = (_word(), _word(), _word())

    def callback() -> None:
        print(greeting, flush=True)
        seen = []
        with progressbar(items) as bar:
            for item in bar:
                seen.append(item)
        print(f"N:{len(seen)}", flush=True)
        for index, item in enumerate(seen):
            print(f"V:{index}:{item}", flush=True)

    result = _dispatch(_cmd(callback), [])
    print(f"visit stdout={result.stdout_text!r}", flush=True)
    require_success_marker_present(result, greeting)
    assert labeled_stdout_field(result, "N:") == "3"
    for index, item in enumerate(items):
        assert labeled_stdout_field(result, f"V:{index}:") == item


def test_progress_bar_visits_every_item_when_explicitly_hidden():
    greeting = _greeting()
    items = (_word(), _word(), _word())

    def callback() -> None:
        print(greeting, flush=True)
        seen = []
        with progressbar(items, hidden=True) as bar:
            for item in bar:
                seen.append(item)
        print(f"N:{len(seen)}", flush=True)
        for index, item in enumerate(seen):
            print(f"V:{index}:{item}", flush=True)

    result = _dispatch(_cmd(callback), [])
    print(f"hidden-visit stdout={result.stdout_text!r}", flush=True)
    require_success_marker_present(result, greeting)
    assert labeled_stdout_field(result, "N:") == "3"
    for index, item in enumerate(items):
        assert labeled_stdout_field(result, f"V:{index}:") == item


def test_progress_bar_label_once_without_terminal_hidden_prints_nothing():
    greeting = _greeting()
    label = f"LBL{uuid.uuid4().hex[:10]}"
    items = (_word(), _word(), _word())

    def shown() -> None:
        print(greeting, flush=True)
        seen = []
        with progressbar(items, label=label) as bar:
            for item in bar:
                seen.append(item)
        print(f"N:{len(seen)}", flush=True)

    def hidden() -> None:
        print(greeting, flush=True)
        seen = []
        with progressbar(items, label=label, hidden=True) as bar:
            for item in bar:
                seen.append(item)
        print(f"N:{len(seen)}", flush=True)

    live = _dispatch(_cmd(shown), [])
    quiet = _dispatch(_cmd(hidden), [])
    print(
        f"label-once={live.stdout_text!r} err={live.stderr_text!r} "
        f"hidden={quiet.stdout_text!r} hidden-err={quiet.stderr_text!r}",
        flush=True,
    )
    require_success_marker_present(live, greeting)
    require_success_marker_present(quiet, greeting)
    assert labeled_stdout_field(live, "N:") == "3"
    assert labeled_stdout_field(quiet, "N:") == "3"
    shown_text = _stdout(live)
    assert shown_text.count(label) == 1, (
        f"no-terminal label was not printed once on standard output; "
        f"stdout={shown_text!r} stderr={live.stderr_text!r}"
    )
    assert label not in (live.stderr_text or ""), (
        f"no-terminal label also reached standard error; stderr={live.stderr_text!r}"
    )
    assert label not in _stdout(quiet), (
        f"explicitly hidden bar still printed the label; stdout={quiet.stdout_text!r}"
    )
    assert label not in (quiet.stderr_text or ""), (
        f"explicitly hidden bar printed the label on standard error; "
        f"stderr={quiet.stderr_text!r}"
    )


def test_progress_bar_explicitly_hidden_on_terminal_prints_nothing():
    greeting = _greeting()
    label = f"LBL{uuid.uuid4().hex[:10]}"
    items = (_word(), _word(), _word())

    def _script(hidden_expr: str, use_bar: bool) -> str:
        body = (
            "with progressbar(ITEMS, label=LABEL, hidden=" + hidden_expr + ") as bar:\n"
            "    for item in bar:\n"
            "        pass\n"
            if use_bar
            else "pass\n"
        )
        return (
            "from optlyn import progressbar\n"
            f"GREET = {greeting!r}\n"
            f"LABEL = {label!r}\n"
            f"ITEMS = {list(items)!r}\n"
            "print(GREET, flush=True)\n"
            f"{body}"
        )

    advancing = run_python_on_tty(_script("False", True))
    hidden = run_python_on_tty(_script("True", True))
    never = run_python_on_tty(_script("False", False))
    print(
        f"adv={advancing.stdout_text!r} hid={hidden.stdout_text!r} "
        f"never={never.stdout_text!r}",
        flush=True,
    )
    assert advancing.returncode == 0 and hidden.returncode == 0 and never.returncode == 0
    cov = (greeting, label, *items)
    adv_rest = _remainder(advancing.stdout_text, *cov)
    hid_rest = _remainder(hidden.stdout_text, *cov)
    never_rest = _remainder(never.stdout_text, *cov)
    assert adv_rest != never_rest, (
        "unhidden tty bar remainder matches never-called after stripping; "
        f"adv={adv_rest!r} never={never_rest!r}"
    )
    assert hid_rest == never_rest, (
        "hidden tty bar still printed; "
        f"hidden={hid_rest!r} never={never_rest!r}"
    )
    assert hid_rest != adv_rest, (
        f"hidden tty remainder matches advancing; hidden={hid_rest!r} adv={adv_rest!r}"
    )


def test_progress_bar_irregular_advance_uses_delta_not_one_step_per_item():
    greeting = _greeting()
    label = f"LBL{uuid.uuid4().hex[:10]}"

    def _script(delta: int) -> str:
        return (
            "from optlyn import progressbar\n"
            f"print({greeting!r}, flush=True)\n"
            f"with progressbar(length=10, label={label!r}) as bar:\n"
            f"    bar.update({delta})\n"
        )

    three = run_python_on_tty(_script(3))
    one = run_python_on_tty(_script(1))
    print(f"delta3={three.stdout_text!r} delta1={one.stdout_text!r}", flush=True)
    assert three.returncode == 0 and one.returncode == 0
    rest3 = _remainder(three.stdout_text, greeting, label)
    rest1 = _remainder(one.stdout_text, greeting, label)
    assert rest3 != rest1, (
        "update(3) and update(1) remainders match after stripping the label; "
        f"d3={rest3!r} d1={rest1!r}"
    )


def test_progress_bar_on_terminal_snapshots_differ_as_it_advances():
    greeting = _greeting()
    label = f"LBL{uuid.uuid4().hex[:10]}"
    items = [_word(), _word(), _word()]
    code = (
        "import os, time\n"
        "from optlyn import progressbar\n"
        f"GREET = {greeting!r}\n"
        f"LABEL = {label!r}\n"
        f"ITEMS = {items!r}\n"
        "print(GREET, flush=True)\n"
        "with progressbar(ITEMS, length=len(ITEMS), label=LABEL) as bar:\n"
        "    iterator = iter(bar)\n"
        "    next(iterator)\n"
        "    next(iterator)\n"
        "    open('READY1', 'w').write('1')\n"
        "    deadline = time.monotonic() + 15\n"
        "    while not os.path.exists('GO1'):\n"
        "        if time.monotonic() > deadline:\n"
        "            raise SystemExit('gate timeout')\n"
        "        time.sleep(0.05)\n"
        "    list(iterator)\n"
    )
    never_code = (
        "from optlyn import progressbar\n"
        f"print({greeting!r}, flush=True)\n"
    )
    session = start_python_on_tty(code)
    try:
        session.wait_until(
            lambda: (session.cwd / "READY1").is_file(),
            message="progress snapshot gate",
        )
        snap1 = session.accumulated_text()
        (session.cwd / "GO1").write_text("1")
        finished = session.wait()
        snap2 = finished.stdout_text
    except Exception:
        session.close()
        raise
    never = run_python_on_tty(never_code)
    print(f"snap1={snap1!r} snap2={snap2!r} never={never.stdout_text!r}", flush=True)
    assert finished.returncode == 0, (
        f"tty progress snapshot run failed; stdout={snap2!r}"
    )
    assert never.returncode == 0
    cov = (greeting, label, *items)
    rest1 = _remainder(snap1, *cov)
    rest2 = _remainder(snap2, *cov)
    never_rest = _remainder(never.stdout_text, *cov)
    assert rest1 != rest2, (
        f"progress snapshots match after stripping; snap1={rest1!r} snap2={rest2!r}"
    )
    assert rest1 != never_rest, (
        "first snapshot matches never-started after stripping; "
        f"snap1={rest1!r} never={never_rest!r}"
    )


def test_progress_bar_known_length_terminal_unlike_unknown_length():
    greeting = _greeting()
    label = f"LBL{uuid.uuid4().hex[:10]}"
    items = [_word(), _word(), _word()]

    def _script(length_expr: str) -> str:
        return (
            "import sys, time\n"
            "from optlyn import progressbar\n"
            f"GREET = {greeting!r}\n"
            f"LABEL = {label!r}\n"
            f"ITEMS = {items!r}\n"
            "print(GREET, flush=True)\n"
            "print('ISATTY:' + str(int(sys.stdout.isatty())), flush=True)\n"
            "def gen():\n"
            "    for item in ITEMS:\n"
            "        yield item\n"
            f"with progressbar(gen(), length={length_expr}, label=LABEL) as bar:\n"
            "    for item in bar:\n"
            "        time.sleep(0.05)\n"
        )

    known = run_python_on_tty(_script("3"))
    unknown = run_python_on_tty(_script("None"))
    print(f"known={known.stdout_text!r} unknown={unknown.stdout_text!r}", flush=True)
    assert known.returncode == 0 and unknown.returncode == 0
    cov = (greeting, label, *items)
    known_rest = _remainder(known.stdout_text, *cov)
    unknown_rest = _remainder(unknown.stdout_text, *cov)
    assert known_rest != unknown_rest, (
        "known-length and unknown-length tty remainders match after stripping; "
        f"known={known_rest!r} unknown={unknown_rest!r}"
    )


def test_progress_bar_known_length_terminal_includes_remaining_time_estimate():
    greeting = _greeting()
    label = f"LBL{uuid.uuid4().hex[:10]}"
    items = [_word(), _word(), _word()]

    def _script(delay: float) -> str:
        return (
            "import os, time\n"
            "from optlyn import progressbar\n"
            f"GREET = {greeting!r}\n"
            f"LABEL = {label!r}\n"
            f"ITEMS = {items!r}\n"
            "print(GREET, flush=True)\n"
            "with progressbar(ITEMS, length=len(ITEMS), label=LABEL) as bar:\n"
            "    iterator = iter(bar)\n"
            f"    time.sleep({delay})\n"
            "    next(iterator)\n"
            "    next(iterator)\n"
            "    open('READY1', 'w').write('1')\n"
            "    deadline = time.monotonic() + 15\n"
            "    while not os.path.exists('GO1'):\n"
            "        if time.monotonic() > deadline:\n"
            "            raise SystemExit('gate timeout')\n"
            "        time.sleep(0.05)\n"
            "    list(iterator)\n"
        )

    def _snapshot(delay: float) -> str:
        session = start_python_on_tty(_script(delay))
        try:
            session.wait_until(
                lambda: (session.cwd / "READY1").is_file(),
                message="remaining-time snapshot gate",
            )
            snap = session.accumulated_text()
            (session.cwd / "GO1").write_text("1")
            finished = session.wait()
        except Exception:
            session.close()
            raise
        assert finished.returncode == 0, (
            f"known-length tty bar failed; delay={delay} stdout={snap!r}"
        )
        return snap

    slow = _snapshot(2.2)
    fast = _snapshot(1.1)
    print(f"slow={slow!r} fast={fast!r}", flush=True)
    cov = (greeting, label, *items)
    slow_rest = _remainder(slow, *cov)
    fast_rest = _remainder(fast, *cov)
    assert slow_rest != fast_rest, (
        "known-length terminal bar has no remaining-time estimate: "
        "same position after different elapsed time yielded the same "
        f"remainder; slow={slow_rest!r} fast={fast_rest!r}"
    )


# ---------------------------------------------------------------------------
# F. Application directory
# ---------------------------------------------------------------------------


def test_app_dir_unix_default_xdg_override_and_posix_forced():
    greeting = _greeting()
    fixed_name = "Rook Ivy"
    runtime_name = f"Ab {uuid.uuid4().hex[:6]} Cd"
    fixed_slug = posix_app_slug(fixed_name)
    runtime_slug = posix_app_slug(runtime_name)
    assert fixed_slug == "rook-ivy"

    def lookup(app_name: str, *, force_posix: bool = False):
        def callback() -> None:
            print(greeting, flush=True)
            print("DIR:" + get_app_dir(app_name, force_posix=force_posix), flush=True)

        return _cmd(callback)

    with workspace() as ws:
        default = ws.invoke(
            lookup(fixed_name),
            [],
            env={"XDG_CONFIG_HOME": None},
        )
        runtime = ws.invoke(
            lookup(runtime_name),
            [],
            env={"XDG_CONFIG_HOME": None},
        )
        xdg_root = ws.path / f"xdg-{uuid.uuid4().hex[:8]}"
        xdg_root.mkdir()
        xdg = ws.invoke(
            lookup(runtime_name),
            [],
            env={"XDG_CONFIG_HOME": str(xdg_root)},
        )
        posix = ws.invoke(
            lookup(runtime_name, force_posix=True),
            [],
            env={"XDG_CONFIG_HOME": str(xdg_root)},
        )
        default_path = labeled_stdout_field(default, "DIR:")
        runtime_path = labeled_stdout_field(runtime, "DIR:")
        xdg_path = labeled_stdout_field(xdg, "DIR:")
        posix_path = labeled_stdout_field(posix, "DIR:")
        print(
            f"default={default_path!r} runtime={runtime_path!r} "
            f"xdg={xdg_path!r} posix={posix_path!r}",
            flush=True,
        )
        require_success_marker_present(default, greeting)
        require_success_marker_present(runtime, greeting)
        require_success_marker_present(xdg, greeting)
        require_success_marker_present(posix, greeting)
        expected_default = str(ws.home / ".config" / fixed_slug)
        expected_runtime = str(ws.home / ".config" / runtime_slug)
        expected_xdg = str(xdg_root / runtime_slug)
        expected_posix = str(ws.home / f".{runtime_slug}")
        assert default_path == expected_default
        assert runtime_path == expected_runtime
        assert runtime_name not in runtime_path
        assert xdg_path == expected_xdg
        assert xdg_path != expected_runtime
        assert posix_path == expected_posix
        assert posix_path != expected_xdg


def test_app_dir_macos_layout():
    greeting = _greeting()
    fixed_name = "Rook Ivy"
    runtime_name = f"Ab {uuid.uuid4().hex[:6]} Cd"

    with workspace() as ws:
        darwin = ws.run_python(
            code=(
                "import sys\n"
                "sys.platform = 'darwin'\n"
                "from optlyn import get_app_dir\n"
                f"print({greeting!r}, flush=True)\n"
                f"print('FIXED:' + get_app_dir({fixed_name!r}), flush=True)\n"
                f"print('RUNTIME:' + get_app_dir({runtime_name!r}), flush=True)\n"
            )
        )
        print(
            f"darwin rc={darwin.returncode} stdout={darwin.stdout_text!r}",
            flush=True,
        )
        assert darwin.returncode == 0, (
            f"macOS application-directory lookup failed; "
            f"stdout={darwin.stdout_text!r} stderr={darwin.stderr_text!r}"
        )
        require_success_marker_present(darwin, greeting)
        darwin_fixed = labeled_stdout_field(darwin, "FIXED:")
        darwin_runtime = labeled_stdout_field(darwin, "RUNTIME:")
        expected_darwin_fixed = str(
            ws.home / "Library" / "Application Support" / fixed_name
        )
        expected_darwin_runtime = str(
            ws.home / "Library" / "Application Support" / runtime_name
        )
        assert darwin_fixed == expected_darwin_fixed, (
            "macOS application directory for a spaced mixed-case name is not "
            "~/Library/Application Support/<name as given>; "
            f"got={darwin_fixed!r} expected={expected_darwin_fixed!r}"
        )
        assert darwin_runtime == expected_darwin_runtime, (
            "macOS application directory did not keep the runtime application "
            f"name; got={darwin_runtime!r} expected={expected_darwin_runtime!r}"
        )
        unix_slug = posix_app_slug(fixed_name)
        assert unix_slug not in FSPath(darwin_fixed).name


# ---------------------------------------------------------------------------
# G. getchar, pause, editor, clear
# ---------------------------------------------------------------------------


def test_getchar_reads_terminal_even_when_stdin_is_a_pipe():
    greeting = "GREETCHAR"
    pipe_text = "abc" + uuid.uuid4().hex[:4]
    key = "x"
    assert key not in pipe_text
    code = (
        "from optlyn import getchar\n"
        f"print({greeting!r}, flush=True)\n"
        "ch = getchar()\n"
        "print('CHAR:' + ch, flush=True)\n"
    )
    result = run_python_pipe_stdin_controlling_tty(code, pipe_text, key)
    print(
        f"getchar rc={result.returncode} stdout={result.stdout_text!r} "
        f"stderr={result.stderr_text!r}",
        flush=True,
    )
    assert result.returncode == 0, (
        f"getchar child failed; stdout={result.stdout_text!r} stderr={result.stderr_text!r}"
    )
    assert greeting in result.stdout_text
    assert labeled_stdout_field(result, "CHAR:") == key
    assert labeled_stdout_field(result, "CHAR:") != pipe_text[:1]


def test_getchar_interrupt_and_eof_are_distinct_failures_not_raw_characters():
    greeting = "GREETCHAR"
    pipe_text = "abc" + uuid.uuid4().hex[:4]
    key = "x"
    assert key not in pipe_text
    success_code = (
        "from optlyn import getchar\n"
        f"print({greeting!r}, flush=True)\n"
        "try:\n"
        "    ch = getchar()\n"
        "    print('CHAR:' + ch, flush=True)\n"
        "except KeyboardInterrupt:\n"
        "    print('FAIL:interrupt', flush=True)\n"
        "except EOFError:\n"
        "    print('FAIL:eof', flush=True)\n"
        "except BaseException as exc:\n"
        "    print('FAIL:other-' + type(exc).__name__, flush=True)\n"
    )
    fail_code = success_code
    ok = run_python_pipe_stdin_controlling_tty(success_code, pipe_text, key)
    interrupt = run_python_pipe_stdin_controlling_tty(fail_code, pipe_text, "\x03")
    eof = run_python_pipe_stdin_controlling_tty(fail_code, pipe_text, "\x04")
    print(
        f"ok={ok.stdout_text!r} int={interrupt.stdout_text!r} eof={eof.stdout_text!r}",
        flush=True,
    )
    assert ok.returncode == 0
    assert labeled_stdout_field(ok, "CHAR:") == key
    assert "FAIL:" in interrupt.stdout_text, (
        "interrupt key sequence was not an interrupt failure; "
        f"stdout={interrupt.stdout_text!r}"
    )
    assert "FAIL:" in eof.stdout_text, (
        "end-of-file key sequence was not an end-of-file failure; "
        f"stdout={eof.stdout_text!r}"
    )
    assert "CHAR:" not in interrupt.stdout_text, (
        "interrupt key sequence delivered a character instead of an interrupt "
        f"failure; stdout={interrupt.stdout_text!r}"
    )
    assert "CHAR:" not in eof.stdout_text, (
        "end-of-file key sequence delivered a character instead of an "
        f"end-of-file failure; stdout={eof.stdout_text!r}"
    )
    interrupt_fail = labeled_stdout_field(interrupt, "FAIL:")
    eof_fail = labeled_stdout_field(eof, "FAIL:")
    assert interrupt_fail == "interrupt", (
        "interrupt key sequence did not raise KeyboardInterrupt; "
        f"int_fail={interrupt_fail!r}"
    )
    assert eof_fail == "eof", (
        "end-of-file key sequence did not raise EOFError; "
        f"eof_fail={eof_fail!r}"
    )


def test_pause_does_nothing_when_not_interactive():
    greeting = _greeting()

    def paused() -> None:
        print(greeting, flush=True)
        pause()

    def untouched() -> None:
        print(greeting, flush=True)

    paused_result = require_completed_within(
        lambda: _dispatch(_cmd(paused), []),
        2.0,
    )
    baseline = _dispatch(_cmd(untouched), [])
    print(
        f"pause-off={paused_result.stdout_text!r} baseline={baseline.stdout_text!r}",
        flush=True,
    )
    require_success_marker_present(paused_result, greeting)
    require_success_marker_present(baseline, greeting)
    assert _remainder(_stdout(paused_result), greeting) == _remainder(
        _stdout(baseline), greeting
    ), (
        "non-interactive pause was not a no-op; "
        f"paused={paused_result.stdout_text!r} baseline={baseline.stdout_text!r}"
    )


def test_pause_prints_and_waits_when_interactive():
    greeting = _greeting()
    ready = f"READY:{uuid.uuid4().hex[:8]}"
    done = f"DONE:{uuid.uuid4().hex[:8]}"
    code = (
        "from optlyn import pause\n"
        f"print({greeting!r}, flush=True)\n"
        f"print({ready!r}, flush=True)\n"
        "pause()\n"
        f"print({done!r}, flush=True)\n"
    )
    waited = run_python_on_tty_blocked_until_feed(code, ready, done, "k")
    skip = (
        f"print({greeting!r}, flush=True)\n"
        f"print({ready!r}, flush=True)\n"
        f"print({done!r}, flush=True)\n"
    )
    untouched = run_python_on_tty(skip)
    print(
        f"pause-tty={waited.stdout_text!r} untouched={untouched.stdout_text!r}",
        flush=True,
    )
    assert waited.returncode == 0, (
        f"interactive pause failed; stdout={waited.stdout_text!r}"
    )
    assert done in waited.stdout_text
    rest_pause = _remainder(waited.stdout_text, greeting, ready, done, "k")
    rest_skip = _remainder(untouched.stdout_text, greeting, ready, done, "k")
    assert rest_pause != rest_skip, (
        "interactive pause remainder matches never-called after stripping; "
        f"pause={rest_pause!r} skip={rest_skip!r}"
    )


def test_editor_on_string_returns_saved_text_or_absent():
    original = f"ORIG:{uuid.uuid4().hex}\n"
    saved = f"SAVED:{uuid.uuid4().hex}\n"
    assert original != saved
    with workspace() as ws:
        saver = ws.write(
            "save.py",
            "import os, sys\n"
            "path = [a for a in sys.argv[1:] if os.path.isfile(a)][-1]\n"
            f"open(path, 'w', encoding='utf-8').write({saved!r})\n",
        )
        quitter = ws.write("quit.py", "import sys\nsys.exit(0)\n")
        save_editor = f"{sys.executable} {saver}"
        quit_editor = f"{sys.executable} {quitter}"
        saved_value = edit(original, editor=save_editor)
        absent_value = edit(original, editor=quit_editor)
        print(
            f"saved_value={saved_value!r} absent_value={absent_value!r}",
            flush=True,
        )
        assert saved_value == saved, (
            f"editor save arm did not return the saved text; got={saved_value!r}"
        )
        assert absent_value != saved_value, (
            f"quit-without-save is not distinguishable from save; absent={absent_value!r}"
        )
        assert absent_value != saved, (
            f"quit-without-save returned the saved text; absent={absent_value!r}"
        )
        assert absent_value != original, (
            f"quit-without-save returned the unsaved original; absent={absent_value!r}"
        )


def test_editor_on_filename_returns_no_text():
    original = f"ORIG:{uuid.uuid4().hex}\n"
    saved = f"SAVED:{uuid.uuid4().hex}\n"
    written = f"FILE:{uuid.uuid4().hex}\n"
    with workspace() as ws:
        target = ws.write("doc.txt", original)
        saver = ws.write(
            "save.py",
            "import os, sys\n"
            "path = [a for a in sys.argv[1:] if os.path.isfile(a)][-1]\n"
            f"open(path, 'w', encoding='utf-8').write({saved!r})\n",
        )
        quitter = ws.write("quit.py", "import sys\nsys.exit(0)\n")
        writer = ws.write(
            "write.py",
            "import os, sys\n"
            "path = [a for a in sys.argv[1:] if os.path.isfile(a)][-1]\n"
            f"open(path, 'w', encoding='utf-8').write({written!r})\n",
        )
        absent_value = edit(original, editor=f"{sys.executable} {quitter}")
        saved_value = edit(original, editor=f"{sys.executable} {saver}")
        file_value = edit(filename=str(target), editor=f"{sys.executable} {writer}")
        on_disk = target.read_text(encoding="utf-8")
        print(
            f"file_value={file_value!r} absent={absent_value!r} "
            f"saved={saved_value!r} disk={on_disk!r}",
            flush=True,
        )
        assert file_value == absent_value, (
            "filename edit return is distinguishable from string-quit absent; "
            f"file={file_value!r} absent={absent_value!r}"
        )
        assert file_value != saved_value, (
            "filename edit return is not distinguishable from string-save; "
            f"file={file_value!r} saved={saved_value!r}"
        )
        assert written in on_disk, (
            f"edited file missing written text; disk={on_disk!r}"
        )


def test_application_launch_opens_url_or_filename_with_default_application():
    url = f"https://launch-{uuid.uuid4().hex}.example.invalid/item"
    with workspace() as ws:
        target = ws.write(f"doc-{uuid.uuid4().hex}.txt", _payload() + "\n")
        path = str(target)
        with recording_default_application(ws.path) as sentinel:
            url_record = application_launch_record(
                sentinel, lambda: launch(url, wait=True)
            )
            file_record = application_launch_record(
                sentinel, lambda: launch(path, wait=True)
            )
        print(
            f"url_record={url_record!r} file_record={file_record!r}",
            flush=True,
        )
    assert url in url_record, (
        f"default-application launch did not receive URL {url!r}; "
        f"record={url_record!r}"
    )
    assert path in file_record, (
        f"default-application launch did not receive filename {path!r}; "
        f"record={file_record!r}"
    )


def test_screen_clear_is_noop_off_terminal_and_unlike_on_terminal():
    greeting = _greeting()
    after = f"AFTER:{uuid.uuid4().hex[:8]}"

    def cleared() -> None:
        print(greeting, flush=True)
        clear()
        print(after, flush=True)

    def untouched() -> None:
        print(greeting, flush=True)
        print(after, flush=True)

    off_clear = _dispatch(_cmd(cleared), [])
    off_base = _dispatch(_cmd(untouched), [])
    print(
        f"off-clear={off_clear.stdout_text!r} off-base={off_base.stdout_text!r}",
        flush=True,
    )
    require_success_marker_present(off_clear, greeting)
    require_success_marker_present(off_base, greeting)
    assert _remainder(_stdout(off_clear), greeting, after) == _remainder(
        _stdout(off_base), greeting, after
    ), (
        "non-terminal clear was not a no-op; "
        f"cleared={off_clear.stdout_text!r} base={off_base.stdout_text!r}"
    )

    on_clear = run_python_on_tty(
        "from optlyn import clear\n"
        f"print({greeting!r}, flush=True)\n"
        "clear()\n"
        f"print({after!r}, flush=True)\n"
    )
    on_base = run_python_on_tty(
        f"print({greeting!r}, flush=True)\n"
        f"print({after!r}, flush=True)\n"
    )
    print(f"on-clear={on_clear.stdout_text!r} on-base={on_base.stdout_text!r}", flush=True)
    assert on_clear.returncode == 0 and on_base.returncode == 0
    clear_rest = _remainder(on_clear.stdout_text, greeting, after)
    base_rest = _remainder(on_base.stdout_text, greeting, after)
    assert clear_rest != base_rest, (
        "terminal clear remainder matches never-called; "
        f"clear={clear_rest!r} base={base_rest!r}"
    )
