# feature: F09
"""File and path parameters (FP-09).

Assertions stay at the PRD's precision: file type delivers an open file;
``-`` is stdin/stdout; text, binary, and a declared encoding; immediate
read open; lazy write; atomic replace on close; path type checks;
filename formatting; the open helper uses the same ``-`` rule, opens
immediately unless the caller turns lazy on, and does not close process
stdio. Wording of file-open sentences, exception types, temporary names,
and replacement characters are not pinned.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path as FSPath

from optlyn import (
    STRING,
    File,
    Path,
    argument,
    command,
    format_filename,
    open_file,
    option,
)

from _harness import workspace
from _helpers import (
    is_readable_file_object,
    labeled_stdout_field,
    require_general_file_error_names_path,
    require_success_marker_present,
    require_usage_class,
    require_usage_names_argument,
    require_usage_names_option,
    require_usage_names_path,
    usage_stderr_remainder,
    write_strict_utf8_text,
)

PROG = "app"


def _word() -> str:
    return "k" + uuid.uuid4().hex[:8]


def _greeting() -> str:
    return f"GREET:{uuid.uuid4().hex}:"


def _opt() -> tuple[str, str]:
    dest = _word()
    return f"--{dest}", dest


def _payload() -> str:
    return f"P{uuid.uuid4().hex}"


def _payload_bytes() -> bytes:
    return b"B\x00\xff\xfe" + uuid.uuid4().bytes


def _salt() -> str:
    return f"S{uuid.uuid4().hex[:10]}"


def _payload_mark(data: str | bytes, salt: str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    acc = len(raw) * 17
    for i, byte in enumerate(raw):
        acc += (byte + i + 1) * (ord(salt[i % len(salt)]) + 3)
    return f"K:{acc}"


def _cmd(callback, *param_decs, **command_kwargs):
    command_kwargs.setdefault("name", _word())
    decorated = callback
    for deco in reversed(param_decs):
        decorated = deco(decorated)
    return command(**command_kwargs)(decorated)


def _invoke(ws, cli, args, **kwargs):
    kwargs.setdefault("prog_name", PROG)
    result = ws.invoke(cli, args, **kwargs)
    print(
        f"exit={result.exit_code} stdout={result.stdout_text!r} "
        f"stderr={result.stderr_text!r}",
        flush=True,
    )
    return result


def _field(result, label: str) -> str:
    return labeled_stdout_field(result, label)


def _mkdir(ws, name: str) -> str:
    dest = ws.path / name
    dest.mkdir()
    if not dest.is_dir():
        raise RuntimeError(f"failed to create directory {dest}")
    return name


def _require_access(path: str, flag: int, expected: bool) -> None:
    got = os.access(path, flag)
    if got is not expected:
        raise RuntimeError(
            f"os.access({path!r}, {flag}) is {got}, expected {expected}; "
            "cannot establish the permission fixture"
        )


def _unprivileged_uid() -> int:
    for uid in (65534, 99, 1, 1000, 100):
        if uid != 0:
            return uid
    raise RuntimeError("no unprivileged uid available")


def _run_path_option_as_uid(
    ws,
    *,
    uid: int,
    flag: str,
    dest: str,
    token: str,
    greeting: str,
    path_kwargs: dict,
):
    script = (
        "import os\n"
        "import sys\n"
        "from optlyn import Path, command, option\n"
        "from optlyn.formatting import wrap_text\n"
        "wrap_text('preload')\n"
        f"uid = {uid}\n"
        "try:\n"
        "    os.setuid(uid)\n"
        "except OSError as exc:\n"
        "    sys.stderr.write(f'setuid failed: {exc}\\n')\n"
        "    raise\n"
        f"greeting = {greeting!r}\n"
        f"flag = {flag!r}\n"
        f"dest = {dest!r}\n"
        f"token = {token!r}\n"
        f"path_kwargs = {path_kwargs!r}\n"
        "def callback(**kwargs):\n"
        "    print(greeting, flush=True)\n"
        "    print(f'P:{os.fspath(kwargs[dest])}', flush=True)\n"
        "callback.__name__ = 'leaf'\n"
        "cli = command()(option(flag, dest, type=Path(**path_kwargs))(callback))\n"
        "cli.main(args=[flag, token], standalone_mode=True, prog_name='app')\n"
    )
    result = ws.run_python(code=script)
    print(
        f"uid={uid} token={token!r} exit={result.returncode} "
        f"stdout={result.stdout_text!r} stderr={result.stderr_text!r}",
        flush=True,
    )
    return result


def _unlike_other_encoding(raw: bytes, text: str, other: str) -> None:
    try:
        decoded = raw.decode(other)
    except UnicodeError:
        print(f"other_encoding={other!r} refused the bytes", flush=True)
        return
    assert decoded != text, (
        f"bytes decoded as {other!r} still match the declared text; "
        f"text={text!r} decoded={decoded!r}"
    )


# ---------------------------------------------------------------------------
# A. File type, default read, dash as stdio
# ---------------------------------------------------------------------------


def test_file_type_default_read_delivers_open_file():
    greeting = _greeting()
    dest = _word()
    name = f"{_word()}.txt"
    payload = _payload()
    salt = _salt()
    expected = _payload_mark(payload, salt)

    def file_cb(**kwargs) -> None:
        print(greeting, flush=True)
        handle = kwargs[dest]
        data = handle.read()
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)
        print(f"KIND:{type(data).__name__}", flush=True)

    def path_cb(**kwargs) -> None:
        print(greeting, flush=True)
        value = kwargs[dest]
        print(f"P:{os.fspath(value)}", flush=True)
        print(f"OPEN:{is_readable_file_object(value)}", flush=True)
        with open(os.fspath(value), encoding="utf-8") as independent:
            print(f"DISK:{_payload_mark(independent.read(), salt)}", flush=True)

    file_cb.__name__ = f"{_word()}_{_word()}"
    path_cb.__name__ = f"{_word()}_{_word()}"
    file_cli = _cmd(file_cb, argument(dest, type=File()))
    path_cli = _cmd(path_cb, argument(dest, type=Path()))

    with workspace() as ws:
        ws.write(name, payload)
        file_result = _invoke(ws, file_cli, [name])
        path_result = _invoke(ws, path_cli, [name])
        leftover = ws.read(name)

    print(f"name={name!r} expected={expected!r}", flush=True)
    require_success_marker_present(file_result, greeting)
    require_success_marker_present(path_result, greeting)
    assert _field(file_result, "MARK:") == expected
    assert _field(file_result, "KIND:") == "str"
    assert leftover == payload, (
        f"default read mutated the file; leftover={leftover!r}"
    )
    assert _field(path_result, "P:") == name
    assert _field(path_result, "OPEN:") == "False"
    assert _field(path_result, "DISK:") == expected


def test_dash_means_stdin_on_read_and_stdout_on_write():
    greeting = _greeting()
    src_dest = _word()
    out_dest = _word()
    src_flag, src_opt = _opt()
    out_flag, out_opt = _opt()
    text = _payload()
    salt = _salt()
    expected = _payload_mark(text, salt)

    def read_cb(**kwargs) -> None:
        print(greeting, flush=True)
        data = kwargs[src_dest].read()
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)

    def write_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"MARK:{expected}", flush=True)
        kwargs[out_dest].write(text)

    def opt_read_cb(**kwargs) -> None:
        print(greeting, flush=True)
        data = kwargs[src_opt].read()
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)

    def opt_write_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"MARK:{expected}", flush=True)
        kwargs[out_opt].write(text)

    read_cb.__name__ = f"{_word()}_{_word()}"
    write_cb.__name__ = f"{_word()}_{_word()}"
    opt_read_cb.__name__ = f"{_word()}_{_word()}"
    opt_write_cb.__name__ = f"{_word()}_{_word()}"
    read_cli = _cmd(read_cb, argument(src_dest, type=File("r")))
    write_cli = _cmd(write_cb, argument(out_dest, type=File("w")))
    opt_read_cli = _cmd(opt_read_cb, option(src_flag, src_opt, type=File("r")))
    opt_write_cli = _cmd(opt_write_cb, option(out_flag, out_opt, type=File("w")))

    with workspace() as ws:
        arg_read = _invoke(ws, read_cli, ["-"], stdin=text)
        opt_read = _invoke(ws, opt_read_cli, [src_flag, "-"], stdin=text)
        arg_write = _invoke(ws, write_cli, ["-"])
        opt_write = _invoke(ws, opt_write_cli, [out_flag, "-"])

    print(f"text={text!r} expected={expected!r}", flush=True)
    for result in (arg_read, opt_read, arg_write, opt_write):
        require_success_marker_present(result, greeting)
        assert _field(result, "MARK:") == expected
    assert text in arg_write.stdout_text
    assert text in opt_write.stdout_text


def test_copy_dash_to_file_then_file_to_dash():
    greeting = _greeting()
    src_dest = _word()
    dst_dest = _word()
    name = f"{_word()}.bin"
    payload = _payload_bytes()
    salt = _salt()
    expected = _payload_mark(payload, salt)

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        data = kwargs[src_dest].read()
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)
        kwargs[dst_dest].write(data)

    callback.__name__ = f"{_word()}_{_word()}"
    cli = _cmd(
        callback,
        argument(src_dest, type=File("rb")),
        argument(dst_dest, type=File("wb")),
    )

    with workspace() as ws:
        to_file = _invoke(ws, cli, ["-", name], stdin=payload)
        on_disk = ws.read_bytes(name)
        to_dash = _invoke(ws, cli, [name, "-"])

    print(f"name={name!r} expected={expected!r} n={len(payload)}", flush=True)
    require_success_marker_present(to_file, greeting)
    require_success_marker_present(to_dash, greeting)
    assert _field(to_file, "MARK:") == expected
    assert _field(to_dash, "MARK:") == expected
    assert on_disk == payload
    assert payload in to_dash.stdout


# ---------------------------------------------------------------------------
# B. Text, binary, declared encoding
# ---------------------------------------------------------------------------


def test_text_and_binary_modes():
    greeting = _greeting()
    dest = _word()
    text_name = f"{_word()}.txt"
    bin_name = f"{_word()}.bin"
    text = _payload()
    binary = _payload_bytes()
    salt = _salt()
    text_mark = _payload_mark(text, salt)
    bin_mark = _payload_mark(binary, salt)

    def text_write(**kwargs) -> None:
        print(greeting, flush=True)
        kwargs[dest].write(text)

    def text_read(**kwargs) -> None:
        print(greeting, flush=True)
        data = kwargs[dest].read()
        print(f"KIND:{type(data).__name__}", flush=True)
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)

    def bin_write(**kwargs) -> None:
        print(greeting, flush=True)
        kwargs[dest].write(binary)

    def bin_read(**kwargs) -> None:
        print(greeting, flush=True)
        data = kwargs[dest].read()
        print(f"KIND:{type(data).__name__}", flush=True)
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)
        print(f"N:{len(data)}", flush=True)

    def bin_dash(**kwargs) -> None:
        print(greeting, flush=True)
        data = kwargs[dest].read()
        print(f"KIND:{type(data).__name__}", flush=True)
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)
        print(f"N:{len(data)}", flush=True)

    for fn in (text_write, text_read, bin_write, bin_read, bin_dash):
        fn.__name__ = f"{_word()}_{_word()}"

    with workspace() as ws:
        tw = _invoke(
            ws, _cmd(text_write, argument(dest, type=File("w"))), [text_name]
        )
        tr = _invoke(
            ws, _cmd(text_read, argument(dest, type=File("r"))), [text_name]
        )
        bw = _invoke(
            ws, _cmd(bin_write, argument(dest, type=File("wb"))), [bin_name]
        )
        br = _invoke(
            ws, _cmd(bin_read, argument(dest, type=File("rb"))), [bin_name]
        )
        bd = _invoke(
            ws,
            _cmd(bin_dash, argument(dest, type=File("rb"))),
            ["-"],
            stdin=binary,
        )
        text_disk = ws.read(text_name)
        bin_disk = ws.read_bytes(bin_name)

    print(f"text_mark={text_mark!r} bin_mark={bin_mark!r}", flush=True)
    for result in (tw, tr, bw, br, bd):
        require_success_marker_present(result, greeting)
    assert text_disk == text
    assert bin_disk == binary
    assert _field(tr, "KIND:") == "str"
    assert _field(tr, "MARK:") == text_mark
    assert _field(br, "KIND:") == "bytes"
    assert _field(br, "MARK:") == bin_mark
    assert _field(br, "N:") == str(len(binary))
    assert _field(bd, "KIND:") == "bytes"
    assert _field(bd, "MARK:") == bin_mark
    assert _field(bd, "N:") == str(len(binary))


def test_declared_text_encoding_is_used():
    greeting = _greeting()
    dest = _word()
    name = f"{_word()}.txt"
    text = f"caf\u00e9-{_word()}"
    salt = _salt()
    expected = _payload_mark(text, salt)
    raw_latin1 = text.encode("latin-1")

    def write_cb(**kwargs) -> None:
        print(greeting, flush=True)
        kwargs[dest].write(text)

    def read_cb(**kwargs) -> None:
        print(greeting, flush=True)
        data = kwargs[dest].read()
        print(f"KIND:{type(data).__name__}", flush=True)
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)

    write_cb.__name__ = f"{_word()}_{_word()}"
    read_cb.__name__ = f"{_word()}_{_word()}"
    write_cli = _cmd(write_cb, argument(dest, type=File("w", encoding="latin-1")))
    read_cli = _cmd(read_cb, argument(dest, type=File("r", encoding="latin-1")))

    with workspace() as ws:
        written = _invoke(ws, write_cli, [name])
        disk = ws.read_bytes(name)
        read_file = _invoke(ws, read_cli, [name])
        ws.write(name, raw_latin1)
        reread = _invoke(ws, read_cli, [name])
        dash = _invoke(ws, read_cli, ["-"], stdin=raw_latin1)

    print(f"text={text!r} expected={expected!r} disk={disk!r}", flush=True)
    require_success_marker_present(written, greeting)
    require_success_marker_present(read_file, greeting)
    require_success_marker_present(reread, greeting)
    require_success_marker_present(dash, greeting)
    assert disk == raw_latin1
    assert disk != text.encode("utf-8")
    assert disk.decode("latin-1") == text
    _unlike_other_encoding(disk, text, "utf-16")
    assert _field(read_file, "KIND:") == "str"
    assert _field(read_file, "MARK:") == expected
    assert _field(reread, "MARK:") == expected
    assert _field(dash, "MARK:") == expected


# ---------------------------------------------------------------------------
# C. Immediate read open; lazy write; forced lazy
# ---------------------------------------------------------------------------


def test_missing_read_target_is_usage_before_callback():
    greeting = _greeting()
    dest = _word()
    present = f"{_word()}.txt"
    missing = f"{_word()}.txt"
    payload = _payload()
    salt = _salt()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        data = kwargs[dest].read()
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    cli = _cmd(callback, argument(dest, type=File("r")))

    with workspace() as ws:
        ws.write(present, payload)
        ok = _invoke(ws, cli, [present])
        bad = _invoke(ws, cli, [missing])

    print(f"present={present!r} missing={missing!r}", flush=True)
    require_success_marker_present(ok, greeting)
    assert _field(ok, "MARK:") == _payload_mark(payload, salt)
    require_usage_names_path(bad, greeting, missing)


def test_default_write_does_not_truncate_until_used():
    greeting = _greeting()
    dest = _word()
    name = f"{_word()}.txt"
    original = _payload()
    replacement = _payload()
    salt = _salt()

    def unused(**kwargs) -> None:
        print(greeting, flush=True)

    def used(**kwargs) -> None:
        print(greeting, flush=True)
        kwargs[dest].write(replacement)
        print(f"MARK:{_payload_mark(replacement, salt)}", flush=True)

    unused.__name__ = f"{_word()}_{_word()}"
    used.__name__ = f"{_word()}_{_word()}"
    unused_cli = _cmd(unused, argument(dest, type=File("w")))
    used_cli = _cmd(used, argument(dest, type=File("w")))

    with workspace() as ws:
        ws.write(name, original)
        idle = _invoke(ws, unused_cli, [name])
        idle_disk = ws.read(name)
        ws.write(name, original)
        written = _invoke(ws, used_cli, [name])
        used_disk = ws.read(name)

    print(f"original={original!r} replacement={replacement!r}", flush=True)
    require_success_marker_present(idle, greeting)
    require_success_marker_present(written, greeting)
    assert idle_disk == original
    assert used_disk == replacement
    assert _field(written, "MARK:") == _payload_mark(replacement, salt)


def test_lazy_forced_off_opens_write_immediately():
    greeting = _greeting()
    dest = _word()
    name = f"{_word()}.txt"
    dirname = _word()
    original = _payload()

    def unused(**kwargs) -> None:
        print(greeting, flush=True)

    unused.__name__ = f"{_word()}_{_word()}"
    file_cli = _cmd(unused, argument(dest, type=File("w", lazy=False)))

    with workspace() as ws:
        ws.write(name, original)
        idle = _invoke(ws, file_cli, [name])
        idle_disk = ws.read(name)
        _mkdir(ws, dirname)
        on_dir = _invoke(ws, file_cli, [dirname])

    print(f"name={name!r} dirname={dirname!r} idle_disk={idle_disk!r}", flush=True)
    require_success_marker_present(idle, greeting)
    assert idle_disk != original
    require_usage_names_path(on_dir, greeting, dirname)


def test_lazy_forced_on_write_does_not_truncate_until_used():
    greeting = _greeting()
    dest = _word()
    name = f"{_word()}.txt"
    original = _payload()
    replacement = _payload()
    salt = _salt()

    def unused(**kwargs) -> None:
        print(greeting, flush=True)

    def used(**kwargs) -> None:
        print(greeting, flush=True)
        kwargs[dest].write(replacement)
        print(f"MARK:{_payload_mark(replacement, salt)}", flush=True)

    unused.__name__ = f"{_word()}_{_word()}"
    used.__name__ = f"{_word()}_{_word()}"
    unused_cli = _cmd(unused, argument(dest, type=File("w", lazy=True)))
    used_cli = _cmd(used, argument(dest, type=File("w", lazy=True)))

    with workspace() as ws:
        ws.write(name, original)
        idle = _invoke(ws, unused_cli, [name])
        idle_disk = ws.read(name)
        ws.write(name, original)
        written = _invoke(ws, used_cli, [name])
        used_disk = ws.read(name)

    print(f"original={original!r} replacement={replacement!r}", flush=True)
    require_success_marker_present(idle, greeting)
    require_success_marker_present(written, greeting)
    assert idle_disk == original
    assert used_disk == replacement
    assert _field(written, "MARK:") == _payload_mark(replacement, salt)


# ---------------------------------------------------------------------------
# D. Atomic write
# ---------------------------------------------------------------------------


def test_atomic_write_keeps_original_until_close_then_replaces():
    greeting = _greeting()
    dest = _word()
    name = f"{_word()}.txt"
    helper_name = f"{_word()}.txt"
    original = _payload()
    replacement = _payload()
    salt = _salt()
    orig_mark = _payload_mark(original, salt)
    new_mark = _payload_mark(replacement, salt)

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        handle = kwargs[dest]
        handle.write(replacement)
        handle.flush()
        with open(name, encoding="utf-8") as independent:
            seen = independent.read()
        print(f"INDEP:{_payload_mark(seen, salt)}", flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    atomic_cli = _cmd(callback, argument(dest, type=File("w", atomic=True)))
    plain_cli = _cmd(callback, argument(dest, type=File("w", atomic=False)))

    with workspace() as ws:
        ws.write(name, original)
        atomic = _invoke(ws, atomic_cli, [name])
        atomic_disk = ws.read(name)
        ws.write(name, original)
        plain = _invoke(ws, plain_cli, [name])
        plain_disk = ws.read(name)

        helper_path = ws.write(helper_name, original)
        with open_file(str(helper_path), "w", atomic=True) as handle:
            handle.write(replacement)
            handle.flush()
            helper_indep = helper_path.read_text(encoding="utf-8")
        helper_after = helper_path.read_text(encoding="utf-8")

    print(
        f"orig={orig_mark} new={new_mark} helper_indep={helper_indep!r}",
        flush=True,
    )
    require_success_marker_present(atomic, greeting)
    require_success_marker_present(plain, greeting)
    assert _field(atomic, "INDEP:") == orig_mark
    assert atomic_disk == replacement
    assert plain_disk == replacement
    assert helper_indep == original
    assert helper_after == replacement
    plain_indep = _field(plain, "INDEP:")
    if plain_indep != orig_mark:
        assert plain_indep != _field(atomic, "INDEP:")


# ---------------------------------------------------------------------------
# E. Usage vs general file-open; identify the path
# ---------------------------------------------------------------------------


def test_non_lazy_unopenable_write_is_usage():
    greeting = _greeting()
    dest = _word()
    dirname = _word()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    non_lazy_cli = _cmd(callback, argument(dest, type=File("w", lazy=False)))
    lazy_cli = _cmd(callback, argument(dest, type=File("w")))

    with workspace() as ws:
        _mkdir(ws, dirname)
        unused = _invoke(ws, lazy_cli, [dirname])
        result = _invoke(ws, non_lazy_cli, [dirname])

    print(f"dirname={dirname!r}", flush=True)
    require_success_marker_present(unused, greeting)
    require_usage_names_path(result, greeting, dirname)
    assert unused.exit_code == 0, (
        f"lazy unused write on an unopenable path must succeed; "
        f"exit={unused.exit_code} stdout={unused.stdout_text!r} "
        f"stderr={unused.stderr_text!r}"
    )
    assert greeting in unused.stdout_text
    assert result.exit_code == 2, (
        f"non-lazy unopenable write must be a usage-class exit 2; "
        f"exit={result.exit_code} stdout={result.stdout_text!r} "
        f"stderr={result.stderr_text!r}"
    )
    assert greeting not in result.stdout_text
    assert greeting not in result.stderr_text
    assert dirname in result.stderr_text
    assert unused.exit_code != result.exit_code


def test_lazy_unopenable_write_is_general_file_error():
    greeting = _greeting()
    dest = _word()
    dirname = _word()
    after = f"AFTER:{uuid.uuid4().hex}:"
    payload = _payload()

    def idle(**kwargs) -> None:
        print(greeting, flush=True)

    def writing(**kwargs) -> None:
        print(greeting, flush=True)
        kwargs[dest].write(payload)
        print(after, flush=True)

    idle.__name__ = f"{_word()}_{_word()}"
    writing.__name__ = f"{_word()}_{_word()}"
    idle_cli = _cmd(idle, argument(dest, type=File("w")))
    write_cli = _cmd(writing, argument(dest, type=File("w")))

    with workspace() as ws:
        _mkdir(ws, dirname)
        unused = _invoke(ws, idle_cli, [dirname])
        failed = _invoke(ws, write_cli, [dirname])

    print(f"dirname={dirname!r} after={after!r}", flush=True)
    require_success_marker_present(unused, greeting)
    require_general_file_error_names_path(failed, dirname, greeting)
    assert after not in failed.stdout_text
    assert after not in failed.stderr_text


def test_file_failures_identify_the_path():
    greeting = _greeting()
    dest = _word()
    missing_a = f"{_word()}.txt"
    missing_b = f"{_word()}.txt"
    dir_a = _word()
    dir_b = _word()
    after = f"AFTER:{uuid.uuid4().hex}:"

    def reader(**kwargs) -> None:
        print(greeting, flush=True)

    def writer(**kwargs) -> None:
        print(greeting, flush=True)
        kwargs[dest].write(_payload())
        print(after, flush=True)

    reader.__name__ = f"{_word()}_{_word()}"
    writer.__name__ = f"{_word()}_{_word()}"
    read_cli = _cmd(reader, argument(dest, type=File("r")))
    write_cli = _cmd(writer, argument(dest, type=File("w")))

    with workspace() as ws:
        miss_a = _invoke(ws, read_cli, [missing_a])
        miss_b = _invoke(ws, read_cli, [missing_b])
        _mkdir(ws, dir_a)
        _mkdir(ws, dir_b)
        lazy_a = _invoke(ws, write_cli, [dir_a])
        lazy_b = _invoke(ws, write_cli, [dir_b])

    print(
        f"missing=({missing_a!r},{missing_b!r}) dirs=({dir_a!r},{dir_b!r})",
        flush=True,
    )
    require_usage_names_path(miss_a, greeting, missing_a)
    require_usage_names_path(miss_b, greeting, missing_b)
    assert missing_a not in miss_b.stderr_text
    assert missing_b not in miss_a.stderr_text
    assert miss_a.stderr_text != miss_b.stderr_text
    require_general_file_error_names_path(lazy_a, dir_a, greeting)
    require_general_file_error_names_path(lazy_b, dir_b, greeting)
    assert lazy_a.stderr_text != lazy_b.stderr_text
    assert after not in lazy_a.stdout_text
    assert after not in lazy_b.stdout_text


# ---------------------------------------------------------------------------
# F. Path type
# ---------------------------------------------------------------------------


def test_path_type_delivers_path_not_open_file():
    greeting = _greeting()
    dest = _word()
    name = f"{_word()}.txt"
    payload = _payload()
    salt = _salt()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        value = kwargs[dest]
        print(f"P:{os.fspath(value)}", flush=True)
        print(f"OPEN:{is_readable_file_object(value)}", flush=True)
        with open(os.fspath(value), encoding="utf-8") as independent:
            print(f"DISK:{_payload_mark(independent.read(), salt)}", flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    cli = _cmd(callback, argument(dest, type=Path()))

    with workspace() as ws:
        ws.write(name, payload)
        result = _invoke(ws, cli, [name])

    print(f"name={name!r}", flush=True)
    require_success_marker_present(result, greeting)
    assert _field(result, "P:") == name
    assert _field(result, "OPEN:") == "False"
    assert _field(result, "DISK:") == _payload_mark(payload, salt)


def test_path_exists_accepts_present_rejects_missing_as_usage():
    greeting = _greeting()
    arg_dest = _word()
    present = f"{_word()}.txt"
    missing = f"{_word()}.txt"
    flag_a, dest_a = _opt()
    flag_b, dest_b = _opt()
    payload = _payload()

    def arg_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"P:{os.fspath(kwargs[arg_dest])}", flush=True)

    def opt_cb_a(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"P:{os.fspath(kwargs[dest_a])}", flush=True)

    def opt_cb_b(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"P:{os.fspath(kwargs[dest_b])}", flush=True)

    arg_cb.__name__ = f"{_word()}_{_word()}"
    opt_cb_a.__name__ = f"{_word()}_{_word()}"
    opt_cb_b.__name__ = f"{_word()}_{_word()}"
    arg_cli = _cmd(arg_cb, argument(arg_dest, type=Path(exists=True)))
    opt_a = _cmd(opt_cb_a, option(flag_a, dest_a, type=Path(exists=True)))
    opt_b = _cmd(opt_cb_b, option(flag_b, dest_b, type=Path(exists=True)))

    with workspace() as ws:
        ws.write(present, payload)
        ok = _invoke(ws, arg_cli, [present])
        missing_arg = _invoke(ws, arg_cli, [missing])
        miss_a = _invoke(ws, opt_a, [flag_a, missing])
        miss_b = _invoke(ws, opt_b, [flag_b, missing])

    print(f"present={present!r} missing={missing!r}", flush=True)
    require_success_marker_present(ok, greeting)
    assert _field(ok, "P:") == present
    require_usage_class(missing_arg, greeting)
    require_usage_names_argument(missing_arg, greeting, arg_dest)
    require_usage_names_option(miss_a, greeting, flag_a)
    require_usage_names_option(miss_b, greeting, flag_b)
    rest_a = usage_stderr_remainder(miss_a, missing)
    rest_b = usage_stderr_remainder(miss_b, missing)
    assert rest_a != rest_b, (
        f"option path-check remainders are not distinct after stripping "
        f"{missing!r}; a={rest_a!r} b={rest_b!r}"
    )


def test_path_file_and_directory_allowance_are_independent():
    greeting = _greeting()
    file_name = f"{_word()}.txt"
    dir_name = _word()
    flag, dest = _opt()
    payload = _payload()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"P:{os.fspath(kwargs[dest])}", flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    files_only = _cmd(
        callback,
        option(flag, dest, type=Path(exists=True, file_okay=True, dir_okay=False)),
    )
    dirs_only = _cmd(
        callback,
        option(flag, dest, type=Path(exists=True, file_okay=False, dir_okay=True)),
    )
    both = _cmd(
        callback,
        option(flag, dest, type=Path(exists=True, file_okay=True, dir_okay=True)),
    )

    with workspace() as ws:
        ws.write(file_name, payload)
        _mkdir(ws, dir_name)
        file_on_files = _invoke(ws, files_only, [flag, file_name])
        dir_on_files = _invoke(ws, files_only, [flag, dir_name])
        dir_on_dirs = _invoke(ws, dirs_only, [flag, dir_name])
        file_on_dirs = _invoke(ws, dirs_only, [flag, file_name])
        file_on_both = _invoke(ws, both, [flag, file_name])
        dir_on_both = _invoke(ws, both, [flag, dir_name])

    print(f"file={file_name!r} dir={dir_name!r} flag={flag!r}", flush=True)
    require_success_marker_present(file_on_files, greeting)
    assert _field(file_on_files, "P:") == file_name
    require_usage_names_option(dir_on_files, greeting, flag)
    require_success_marker_present(dir_on_dirs, greeting)
    assert _field(dir_on_dirs, "P:") == dir_name
    require_usage_names_option(file_on_dirs, greeting, flag)
    require_success_marker_present(file_on_both, greeting)
    require_success_marker_present(dir_on_both, greeting)
    assert _field(file_on_both, "P:") == file_name
    assert _field(dir_on_both, "P:") == dir_name


def test_path_executable_readable_writable_checks():
    greeting = _greeting()
    name = f"{_word()}.txt"
    flag, dest = _opt()
    payload = _payload()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"P:{os.fspath(kwargs[dest])}", flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    exec_cli = _cmd(
        callback,
        option(flag, dest, type=Path(exists=True, executable=True, readable=False)),
    )
    read_cli = _cmd(
        callback,
        option(flag, dest, type=Path(exists=True, readable=True)),
    )
    write_cli = _cmd(
        callback,
        option(flag, dest, type=Path(exists=True, writable=True, readable=False)),
    )
    read_only_exec_off = _cmd(
        callback,
        option(
            flag,
            dest,
            type=Path(exists=True, readable=True, executable=False),
        ),
    )

    with workspace() as ws:
        path = str(ws.write(name, payload))
        os.chmod(path, 0o644)
        _require_access(path, os.X_OK, False)
        _require_access(path, os.R_OK, True)
        exec_denied = _invoke(ws, exec_cli, [flag, name])
        read_ok_exec_off = _invoke(ws, read_only_exec_off, [flag, name])
        exec_ok_token = sys.executable
        if not exec_ok_token or not os.access(exec_ok_token, os.X_OK):
            raise RuntimeError(
                f"interpreter {exec_ok_token!r} is not executable; "
                "cannot observe an executable-check success"
            )
        exec_ok = _invoke(ws, exec_cli, [flag, exec_ok_token])

        os.chmod(path, 0o000)
        can_deny_read = not os.access(path, os.R_OK)
        print(f"can_deny_read={can_deny_read} euid={os.geteuid()}", flush=True)
        if can_deny_read:
            unread = _invoke(ws, read_cli, [flag, name])
            os.chmod(path, 0o644)
            _require_access(path, os.R_OK, True)
            read_ok = _invoke(ws, read_cli, [flag, name])
            os.chmod(path, 0o444)
            _require_access(path, os.W_OK, False)
            unwrite = _invoke(ws, write_cli, [flag, name])
            os.chmod(path, 0o644)
            _require_access(path, os.W_OK, True)
            write_ok = _invoke(ws, write_cli, [flag, name])
        else:
            uid = _unprivileged_uid()
            os.chmod(ws.path, 0o755)
            os.chmod(path, 0o000)
            unread = _run_path_option_as_uid(
                ws,
                uid=uid,
                flag=flag,
                dest=dest,
                token=name,
                greeting=greeting,
                path_kwargs={"exists": True, "readable": True},
            )
            os.chmod(path, 0o644)
            read_ok = _run_path_option_as_uid(
                ws,
                uid=uid,
                flag=flag,
                dest=dest,
                token=name,
                greeting=greeting,
                path_kwargs={"exists": True, "readable": True},
            )
            os.chmod(path, 0o444)
            unwrite = _run_path_option_as_uid(
                ws,
                uid=uid,
                flag=flag,
                dest=dest,
                token=name,
                greeting=greeting,
                path_kwargs={"exists": True, "writable": True, "readable": False},
            )
            os.chmod(path, 0o666)
            write_ok = _run_path_option_as_uid(
                ws,
                uid=uid,
                flag=flag,
                dest=dest,
                token=name,
                greeting=greeting,
                path_kwargs={"exists": True, "writable": True, "readable": False},
            )

    print(f"name={name!r} flag={flag!r}", flush=True)
    require_usage_names_option(exec_denied, greeting, flag)
    require_success_marker_present(read_ok_exec_off, greeting)
    assert _field(read_ok_exec_off, "P:") == name
    require_success_marker_present(exec_ok, greeting)
    require_usage_names_option(unread, greeting, flag)
    require_success_marker_present(read_ok, greeting)
    require_usage_names_option(unwrite, greeting, flag)
    require_success_marker_present(write_ok, greeting)


def test_missing_path_skips_further_checks_when_exists_not_required():
    greeting = _greeting()
    missing = f"{_word()}.txt"
    present = f"{_word()}.txt"
    flag, dest = _opt()
    payload = _payload()
    checks = Path(
        exists=False,
        readable=True,
        writable=True,
        executable=True,
    )

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"P:{os.fspath(kwargs[dest])}", flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    cli = _cmd(callback, option(flag, dest, type=checks))
    present_cli = _cmd(
        callback,
        option(
            flag,
            dest,
            type=Path(exists=True, readable=True, writable=True, executable=True),
        ),
    )

    with workspace() as ws:
        skipped = _invoke(ws, cli, [flag, missing])
        path = str(ws.write(present, payload))
        os.chmod(path, 0o644)
        _require_access(path, os.X_OK, False)
        denied = _invoke(ws, present_cli, [flag, present])

    print(f"missing={missing!r} present={present!r}", flush=True)
    require_success_marker_present(skipped, greeting)
    assert _field(skipped, "P:") == missing
    require_usage_names_option(denied, greeting, flag)


def test_path_resolve_absolute_follows_symlinks_without_expanding_tilde():
    greeting = _greeting()
    dest = _word()
    target = f"{_word()}.txt"
    link = f"{_word()}.lnk"
    relative = f"{_word()}.txt"
    tilde_name = _word()
    token = f"~/{tilde_name}"
    payload = _payload()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        value = os.fspath(kwargs[dest])
        print(f"P:{value}", flush=True)
        print(f"ABS:{os.path.isabs(value)}", flush=True)
        print(f"REAL:{os.path.realpath(value)}", flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    resolved = _cmd(callback, argument(dest, type=Path(resolve_path=True)))
    plain = _cmd(callback, argument(dest, type=Path(resolve_path=False)))

    with workspace() as ws:
        ws.write(target, payload)
        ws.write(relative, payload)
        (ws.path / link).symlink_to(target)
        expected_real = os.path.realpath(str(ws.path / link))
        expanded_real = os.path.realpath(str(ws.home / tilde_name))
        rel_ok = _invoke(ws, resolved, [relative])
        link_ok = _invoke(ws, resolved, [link])
        link_plain = _invoke(ws, plain, [link])
        tilde = _invoke(ws, resolved, [token])

    print(
        f"expected_real={expected_real!r} expanded={expanded_real!r} token={token!r}",
        flush=True,
    )
    require_success_marker_present(rel_ok, greeting)
    require_success_marker_present(link_ok, greeting)
    require_success_marker_present(link_plain, greeting)
    require_success_marker_present(tilde, greeting)
    assert _field(rel_ok, "ABS:") == "True"
    assert _field(link_ok, "P:") == expected_real
    assert _field(link_plain, "P:") != expected_real
    assert _field(tilde, "ABS:") == "True"
    assert _field(tilde, "REAL:") != expanded_real


def test_path_allow_dash_means_stream_token_without_opening():
    greeting = _greeting()
    dest = _word()
    file_dest = _word()
    stdin_text = _payload()
    file_text = _payload()
    salt = _salt()
    stdin_mark = _payload_mark(stdin_text, salt)
    file_mark = _payload_mark(file_text, salt)

    def path_cb(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"P:{os.fspath(kwargs[dest])}", flush=True)
        leftover = sys.stdin.read()
        print(f"STDIN:{_payload_mark(leftover, salt)}", flush=True)

    def file_cb(**kwargs) -> None:
        print(greeting, flush=True)
        data = kwargs[file_dest].read()
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)

    path_cb.__name__ = f"{_word()}_{_word()}"
    file_cb.__name__ = f"{_word()}_{_word()}"
    allowed = _cmd(
        path_cb, argument(dest, type=Path(exists=True, allow_dash=True))
    )
    denied = _cmd(
        path_cb, argument(dest, type=Path(exists=True, allow_dash=False))
    )
    file_cli = _cmd(file_cb, argument(file_dest, type=File("r")))

    with workspace() as ws:
        dash_ok = _invoke(ws, allowed, ["-"], stdin=stdin_text)
        missing_dash = _invoke(ws, denied, ["-"], stdin=stdin_text)
        ws.write("-", file_text)
        named_dash = _invoke(ws, denied, ["-"], stdin=stdin_text)
        file_twin = _invoke(ws, file_cli, ["-"], stdin=stdin_text)

    print(f"stdin_mark={stdin_mark!r} file_mark={file_mark!r}", flush=True)
    require_success_marker_present(dash_ok, greeting)
    assert _field(dash_ok, "P:") == "-"
    assert _field(dash_ok, "STDIN:") == stdin_mark
    require_usage_class(missing_dash, greeting)
    require_usage_names_argument(missing_dash, greeting, dest)
    require_success_marker_present(named_dash, greeting)
    assert _field(named_dash, "P:") == "-"
    assert _field(named_dash, "STDIN:") == stdin_mark
    require_success_marker_present(file_twin, greeting)
    assert _field(file_twin, "MARK:") == stdin_mark


def test_path_produced_as_requested_object_type():
    greeting = _greeting()
    dest = _word()
    name = f"{_word()}.txt"
    payload = _payload()

    def callback(**kwargs) -> None:
        print(greeting, flush=True)
        value = kwargs[dest]
        print(f"P:{os.fspath(value)}", flush=True)
        print(f"ISPATH:{isinstance(value, FSPath)}", flush=True)
        print(f"ISSTR:{isinstance(value, str)}", flush=True)

    callback.__name__ = f"{_word()}_{_word()}"
    as_path = _cmd(callback, argument(dest, type=Path(path_type=FSPath)))
    as_str = _cmd(callback, argument(dest, type=Path(path_type=str)))

    with workspace() as ws:
        ws.write(name, payload)
        path_result = _invoke(ws, as_path, [name])
        str_result = _invoke(ws, as_str, [name])

    print(f"name={name!r}", flush=True)
    require_success_marker_present(path_result, greeting)
    require_success_marker_present(str_result, greeting)
    assert _field(path_result, "P:") == name
    assert _field(path_result, "ISPATH:") == "True"
    assert _field(str_result, "P:") == name
    assert _field(str_result, "ISSTR:") == "True"


# ---------------------------------------------------------------------------
# G. File-type and path-type environment lists
# ---------------------------------------------------------------------------


def test_file_type_env_list_splits_on_os_pathsep():
    greeting = _greeting()
    flag, dest = _opt()
    env_name = f"E{_word().upper()}"
    left_name = f"{_word()}.txt"
    right_name = f"{_word()}.txt"
    left = _payload()
    right = _payload()
    salt = _salt()
    left_mark = _payload_mark(left, salt)
    right_mark = _payload_mark(right, salt)
    blob = f"{left_name}{os.pathsep}{right_name}"

    def file_cb(**kwargs) -> None:
        print(greeting, flush=True)
        values = kwargs[dest]
        print(f"N:{len(values)}", flush=True)
        marks = [_payload_mark(item.read(), salt) for item in values]
        print(f"MARKS:{','.join(marks)}", flush=True)

    def string_cb(**kwargs) -> None:
        print(greeting, flush=True)
        values = kwargs[dest]
        print(f"N:{len(values)}", flush=True)
        print(f"BLOB:{values[0] if values else ''}", flush=True)

    file_cb.__name__ = f"{_word()}_{_word()}"
    string_cb.__name__ = f"{_word()}_{_word()}"
    file_cli = _cmd(
        file_cb, option(flag, dest, multiple=True, type=File(), envvar=env_name)
    )
    string_cli = _cmd(
        string_cb,
        option(flag, dest, multiple=True, type=STRING, envvar=env_name),
    )

    with workspace() as ws:
        ws.write(left_name, left)
        ws.write(right_name, right)
        files = _invoke(ws, file_cli, [], env={env_name: blob})
        strings = _invoke(ws, string_cli, [], env={env_name: blob})

    print(f"blob={blob!r} left={left_mark} right={right_mark}", flush=True)
    require_success_marker_present(files, greeting)
    require_success_marker_present(strings, greeting)
    assert _field(files, "N:") == "2"
    marks = _field(files, "MARKS:")
    assert left_mark in marks
    assert right_mark in marks
    assert left_mark not in strings.stdout_text
    assert right_mark not in strings.stdout_text


def test_path_type_env_list_splits_on_os_pathsep():
    greeting = _greeting()
    flag, dest = _opt()
    env_name = f"E{_word().upper()}"
    left_name = f"{_word()}.txt"
    right_name = f"{_word()}.txt"
    left = _payload()
    right = _payload()
    salt = _salt()
    left_mark = _payload_mark(left, salt)
    right_mark = _payload_mark(right, salt)
    blob = f"{left_name}{os.pathsep}{right_name}"

    def path_cb(**kwargs) -> None:
        print(greeting, flush=True)
        values = kwargs[dest]
        print(f"N:{len(values)}", flush=True)
        for index, value in enumerate(values):
            print(f"P{index}:{os.fspath(value)}", flush=True)
            print(f"OPEN{index}:{is_readable_file_object(value)}", flush=True)
            with open(os.fspath(value), encoding="utf-8") as independent:
                print(
                    f"DISK{index}:{_payload_mark(independent.read(), salt)}",
                    flush=True,
                )

    path_cb.__name__ = f"{_word()}_{_word()}"
    path_cli = _cmd(
        path_cb, option(flag, dest, multiple=True, type=Path(), envvar=env_name)
    )

    with workspace() as ws:
        ws.write(left_name, left)
        ws.write(right_name, right)
        paths = _invoke(ws, path_cli, [], env={env_name: blob})

    print(f"blob={blob!r} left={left_mark} right={right_mark}", flush=True)
    require_success_marker_present(paths, greeting)
    assert _field(paths, "N:") == "2"
    delivered = {_field(paths, "P0:"), _field(paths, "P1:")}
    assert delivered == {left_name, right_name}, (
        f"path-typed env list did not deliver each split part as a path; "
        f"delivered={delivered!r} expected={left_name!r},{right_name!r} "
        f"blob={blob!r}"
    )
    assert _field(paths, "OPEN0:") == "False"
    assert _field(paths, "OPEN1:") == "False"
    disk = {_field(paths, "DISK0:"), _field(paths, "DISK1:")}
    assert disk == {left_mark, right_mark}


# ---------------------------------------------------------------------------
# H. Filename formatting
# ---------------------------------------------------------------------------


def test_filename_formatting_prints_non_unicode_without_failing():
    suffix = uuid.uuid4().hex
    stem = f"ST{_word()}"
    unicode_name = f"{stem}-{suffix}.dat"
    prefix_a = f"A{_word()}"
    prefix_b = f"B{_word()}"
    raw_a = prefix_a.encode("ascii") + b"\xff\xfe" + suffix.encode("ascii")
    raw_b = prefix_b.encode("ascii") + b"\xff\xfe" + suffix.encode("ascii")
    illegal_a = os.fsdecode(raw_a)
    illegal_b = os.fsdecode(raw_b)

    got_unicode = format_filename(unicode_name)
    got_a = format_filename(illegal_a)
    got_b = format_filename(illegal_b)
    print(
        f"unicode={got_unicode!r} a={got_a!r} b={got_b!r} suffix={suffix!r}",
        flush=True,
    )
    assert isinstance(got_unicode, str)
    assert stem in got_unicode.replace(suffix, "")
    assert isinstance(got_a, str)
    assert isinstance(got_b, str)
    encoded_a = write_strict_utf8_text(got_a)
    encoded_b = write_strict_utf8_text(got_b)
    assert encoded_a
    assert encoded_b
    assert got_a.replace(suffix, "") != got_b.replace(suffix, "")


# ---------------------------------------------------------------------------
# I. Open helper
# ---------------------------------------------------------------------------


def test_open_helper_dash_obeys_same_stdin_stdout_rule():
    greeting = _greeting()
    dest = _word()
    text = _payload()
    salt = _salt()
    expected = _payload_mark(text, salt)

    def helper_read() -> None:
        print(greeting, flush=True)
        with open_file("-", "r") as handle:
            data = handle.read()
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)

    def file_read(**kwargs) -> None:
        print(greeting, flush=True)
        data = kwargs[dest].read()
        print(f"MARK:{_payload_mark(data, salt)}", flush=True)

    def helper_write() -> None:
        print(greeting, flush=True)
        print(f"MARK:{expected}", flush=True)
        with open_file("-", "w") as handle:
            handle.write(text)

    def file_write(**kwargs) -> None:
        print(greeting, flush=True)
        print(f"MARK:{expected}", flush=True)
        kwargs[dest].write(text)

    helper_read.__name__ = f"{_word()}_{_word()}"
    file_read.__name__ = f"{_word()}_{_word()}"
    helper_write.__name__ = f"{_word()}_{_word()}"
    file_write.__name__ = f"{_word()}_{_word()}"
    helper_read_cli = _cmd(helper_read)
    file_read_cli = _cmd(file_read, argument(dest, type=File("r")))
    helper_write_cli = _cmd(helper_write)
    file_write_cli = _cmd(file_write, argument(dest, type=File("w")))

    with workspace() as ws:
        helper_in = _invoke(ws, helper_read_cli, [], stdin=text)
        file_in = _invoke(ws, file_read_cli, ["-"], stdin=text)
        helper_out = _invoke(ws, helper_write_cli, [])
        file_out = _invoke(ws, file_write_cli, ["-"])

    print(f"expected={expected!r}", flush=True)
    for result in (helper_in, file_in, helper_out, file_out):
        require_success_marker_present(result, greeting)
        assert _field(result, "MARK:") == expected
    assert text in helper_out.stdout_text
    assert text in file_out.stdout_text


def test_open_helper_keeps_stdio_open_and_closes_real_files():
    greeting = _greeting()
    name = f"{_word()}.txt"
    payload = _payload()
    after = f"AFTER:{uuid.uuid4().hex}:"
    first = f"F{uuid.uuid4().hex}"
    second = f"S{uuid.uuid4().hex}"
    salt = _salt()

    def write_dash() -> None:
        print(greeting, flush=True)
        with open_file("-", "w") as handle:
            handle.write(payload)
            handle.flush()
        print(after, flush=True)

    def read_dash() -> None:
        print(greeting, flush=True)
        with open_file("-", "r") as handle:
            head = handle.readline()
        print(f"FIRST:{_payload_mark(head.rstrip('\n'), salt)}", flush=True)
        rest = sys.stdin.read()
        print(f"REST:{_payload_mark(rest, salt)}", flush=True)
        print(f"CLOSED:{sys.stdin.closed}", flush=True)

    def real_file() -> None:
        print(greeting, flush=True)
        with open_file(name, "w") as handle:
            handle.write(payload)
            held = handle
        try:
            closed = held.closed
        except Exception as exc:
            raise RuntimeError(f"could not observe .closed: {exc}") from exc
        write_failed = False
        try:
            held.write("x")
            held.flush()
        except Exception:
            write_failed = True
        print(f"CLOSED:{closed}", flush=True)
        print(f"WRITEFAIL:{write_failed}", flush=True)

    write_dash.__name__ = f"{_word()}_{_word()}"
    read_dash.__name__ = f"{_word()}_{_word()}"
    real_file.__name__ = f"{_word()}_{_word()}"

    script = (
        "import sys\n"
        "from optlyn import File, argument, command\n"
        f"payload = {payload!r}\n"
        f"greeting = {greeting!r}\n"
        f"after = {after!r}\n"
        "def callback(out):\n"
        "    sys.stdout.write(greeting)\n"
        "    sys.stdout.write('\\n')\n"
        "    out.write(payload)\n"
        "    out.flush()\n"
        "callback.__name__ = 'leaf'\n"
        "cli = command()(argument('out', type=File('w'))(callback))\n"
        "cli.main(args=['-'], standalone_mode=False, prog_name='app')\n"
        "sys.stdout.write(after)\n"
        "sys.stdout.flush()\n"
    )

    with workspace() as ws:
        dash_write = _invoke(ws, _cmd(write_dash), [])
        dash_read = _invoke(
            ws, _cmd(read_dash), [], stdin=f"{first}\n{second}"
        )
        real = _invoke(ws, _cmd(real_file), [])
        disk = ws.read(name)
        after_main = ws.run_python(code=script)

    print(
        f"after={after!r} first={first!r} second={second!r} "
        f"child_exit={after_main.returncode}",
        flush=True,
    )
    require_success_marker_present(dash_write, greeting)
    assert after in dash_write.stdout_text
    assert payload in dash_write.stdout_text
    require_success_marker_present(dash_read, greeting)
    assert _field(dash_read, "FIRST:") == _payload_mark(first, salt)
    assert _field(dash_read, "REST:") == _payload_mark(second, salt)
    assert _field(dash_read, "CLOSED:") == "False"
    require_success_marker_present(real, greeting)
    closed = _field(real, "CLOSED:") == "True"
    write_failed = _field(real, "WRITEFAIL:") == "True"
    assert closed or write_failed
    assert disk == payload
    if after_main.returncode is None:
        raise RuntimeError("child ended without a return code")
    assert after_main.returncode == 0, (
        f"write after file-parameter dash invoke failed; "
        f"exit={after_main.returncode} stdout={after_main.stdout_text!r} "
        f"stderr={after_main.stderr_text!r}"
    )
    assert greeting in after_main.stdout_text
    assert payload in after_main.stdout_text
    assert after in after_main.stdout_text


def test_open_helper_lazy_forced_on_write_does_not_truncate_until_used():
    name = f"{_word()}.txt"
    original = _payload()
    replacement = _payload()

    with workspace() as ws:
        path = ws.write(name, original)
        abs_path = str(path)
        with open_file(abs_path, "w", lazy=True) as handle:
            print(f"lazy_on_unused handle={handle!r}", flush=True)
        lazy_on_disk = path.read_text(encoding="utf-8")
        path.write_text(original, encoding="utf-8")
        with open_file(abs_path, "w", lazy=False) as handle:
            print(f"lazy_off_unused handle={handle!r}", flush=True)
        lazy_off_disk = path.read_text(encoding="utf-8")
        path.write_text(original, encoding="utf-8")
        with open_file(abs_path, "w", lazy=True) as handle:
            handle.write(replacement)
        used_disk = path.read_text(encoding="utf-8")

    print(
        f"lazy_on={lazy_on_disk!r} lazy_off={lazy_off_disk!r} used={used_disk!r}",
        flush=True,
    )
    assert lazy_on_disk == original
    assert lazy_off_disk != original
    assert used_disk == replacement


def test_open_helper_opens_immediately_when_lazy_omitted():
    name = f"{_word()}.txt"
    original = _payload()

    with workspace() as ws:
        path = ws.write(name, original)
        abs_path = str(path)
        with open_file(abs_path, "w") as handle:
            print(f"lazy_omitted_unused handle={handle!r}", flush=True)
        omitted_disk = path.read_text(encoding="utf-8")

    print(
        f"original={original!r} omitted_disk={omitted_disk!r}",
        flush=True,
    )
    assert omitted_disk != original, (
        f"helper unused write with lazy omitted left the target unchanged; "
        f"original={original!r} disk={omitted_disk!r}"
    )
