# feature: F07
"""FP-07: envfile command — list, get, set, and unset.

Assertions stay at the PRD's precision: CLI extra required to run
subcommands; set/get/unset success text and file effects; four list
formats with sorted names and no-value / empty-string rules; global
--file / --quote / --export / --version; usage-style unopenable paths
versus missing-key empty output; set without both arguments does not
write; default set/unset do not follow symbolic links. Exit numbers,
Click exception types, and shlex.quote bytes are not pinned; reports are
read by the exit status, channel and usage label the Interface Contract
states.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from _harness import HarnessError, RunResult, Workspace, path_is_file, path_is_symlink
from _helpers import (
    cli_invoke,
    cli_streams,
    cli_without_extra,
    installed_distribution_version,
    posix_shell_value,
    require_absent_independent_line,
    require_cli_success,
    require_cli_unsuccessful,
    require_independent_line,
    require_utf8_text,
    EXIT_OPERATION_FAILURE,
    EXIT_USAGE_FAILURE,
    has_usage_label,
    require_exit,
    unique_token,
)

EXPORT_PREFIX = "export "
SIMPLE_FORMAT = "simple"
JSON_FORMAT = "json"
SHELL_FORMAT = "shell"
EXPORT_FORMAT = "export"


def _file_text(ws: Workspace, relpath: str, *, origin: str) -> str:
    return require_utf8_text(ws.read_bytes(relpath), origin=origin)


def _require_missing_file(ws: Workspace, relpath: str, *, origin: str) -> None:
    try:
        data = ws.read_bytes(relpath)
    except FileNotFoundError:
        print(f"{origin} still missing {relpath}", flush=True)
        return
    raise AssertionError(f"{origin} created {relpath}: {data!r}")


def _require_empty_output(result: RunResult, *, origin: str) -> None:
    assert result.stdout_text == "", (
        f"{origin} stdout is not empty: {result.stdout_text!r}"
    )
    assert result.stderr_text == "", (
        f"{origin} stderr is not empty: {result.stderr_text!r}"
    )
    print(f"{origin} empty output", flush=True)


def _require_nonempty_report(result: RunResult, *, origin: str) -> str:
    text = cli_streams(result)
    assert text, f"{origin} has empty operator-visible report"
    return text


def _assignment_rows(
    text: str, *, prefix: str = "", origin: str = "list"
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line:
            continue
        body = line
        if prefix:
            assert line.startswith(prefix), (
                f"{origin} line {line!r} does not start with {prefix!r}"
            )
            body = line[len(prefix) :]
        name, sep, _rest = body.partition("=")
        assert sep == "=", f"{origin} line is not NAME=value: {line!r}"
        rows.append((name, line))
    return rows


def _assignment_names(text: str, *, prefix: str = "", origin: str = "list") -> list[str]:
    return [name for name, _line in _assignment_rows(text, prefix=prefix, origin=origin)]


def _line_for_name(
    text: str, name: str, *, prefix: str = "", origin: str = "list"
) -> str:
    for recorded, line in _assignment_rows(text, prefix=prefix, origin=origin):
        if recorded == name:
            print(f"{origin} line for {name!r}={line!r}", flush=True)
            return line
    raise HarnessError(
        f"{origin} has no assignment for {name!r}; lines={text.splitlines()!r}"
    )


def _require_sorted_names(names: Sequence[str], *, origin: str) -> None:
    expected = sorted(names)
    assert list(names) == expected, (
        f"{origin} names {list(names)!r} are not sorted {expected!r}"
    )
    print(f"{origin} sorted names={list(names)!r}", flush=True)


# ---------------------------------------------------------------------------
# A. CLI extra required to run subcommands
# ---------------------------------------------------------------------------


def test_cli_without_extra_does_not_run_subcommands_and_identifies_extra(isolated_ws):
    ws = isolated_ws
    token, value = unique_token(), unique_token()
    ws.write(".env", f"USER=foo\n{token}={value}\n")

    baseline = cli_invoke(ws, ["list"])
    listed = require_cli_success(baseline, origin="extra-present list")
    require_independent_line(listed, "USER=foo", origin="extra-present list")
    require_independent_line(
        listed, f"{token}={value}", origin="extra-present runtime list"
    )

    extra_list = require_cli_unsuccessful(
        cli_without_extra(ws, ["list"]),
        origin="extra-less list",
    )
    extra_list_text = _require_nonempty_report(
        extra_list, origin="extra-less list"
    )
    assert "USER=foo" not in extra_list_text.splitlines(), (
        "extra-less list printed USER=foo; subcommand must not run"
    )
    assert f"{token}={value}" not in extra_list_text.splitlines(), (
        "extra-less list printed the runtime binding; subcommand must not run"
    )
    assert "USER=foo" not in extra_list.stdout_text, (
        f"extra-less stdout still contains USER=foo: {extra_list.stdout_text!r}"
    )
    assert f"{token}={value}" not in extra_list.stdout_text, (
        f"extra-less stdout still contains the runtime binding: "
        f"{extra_list.stdout_text!r}"
    )

    extra_get = require_cli_unsuccessful(
        cli_without_extra(ws, ["get", token]),
        origin="extra-less get",
    )
    extra_get_text = _require_nonempty_report(extra_get, origin="extra-less get")

    require_exit(extra_list, EXIT_OPERATION_FAILURE, origin="extra-less list")
    require_exit(extra_get, EXIT_OPERATION_FAILURE, origin="extra-less get")
    assert re.search(r"(?<![A-Za-z0-9_])cli(?![A-Za-z0-9_])", extra_list.stderr_text), (
        f"extra-less report does not name the cli extra: {extra_list.stderr_text!r}"
    )
    assert extra_list.stderr_text == extra_get.stderr_text, (
        "extra-less report differs between subcommands: "
        f"{extra_list.stderr_text!r} vs {extra_get.stderr_text!r}"
    )
    assert not has_usage_label(extra_list_text), "extra-less report carries the usage label"

    missing_name = unique_token()
    usage = require_cli_unsuccessful(
        cli_invoke(ws, ["set", missing_name]),
        origin="extra-present set name-only",
    )
    usage_text = _require_nonempty_report(usage, origin="extra-present set name-only")
    require_exit(usage, EXIT_USAGE_FAILURE, origin="extra-present set name-only")
    assert has_usage_label(usage.stderr_text), (
        f"missing-argument report has no usage label: {usage.stderr_text!r}"
    )

    missing_rel = f"missing-{unique_token()}.env"
    missing_path = ws.resolve(missing_rel)
    unopenable = require_cli_unsuccessful(
        cli_invoke(ws, ["--file", missing_rel, "list"]),
        origin="extra-present unopenable list",
    )
    unopenable_text = _require_nonempty_report(
        unopenable, origin="extra-present unopenable list"
    )
    require_exit(unopenable, EXIT_USAGE_FAILURE, origin="extra-present unopenable list")
    assert missing_rel in unopenable.stderr_text, (
        f"could-not-open report does not name the path: {unopenable.stderr_text!r}"
    )
    assert not has_usage_label(unopenable_text), (
        "could-not-open report carries the missing-argument usage label"
    )

    absent_dir = ws.mkdir(unique_token())
    set_name, set_value = unique_token(), unique_token()
    extra_set = require_cli_unsuccessful(
        cli_without_extra(ws, ["set", set_name, set_value], cwd=absent_dir),
        origin="extra-less set",
    )
    _require_nonempty_report(extra_set, origin="extra-less set")
    require_exit(extra_set, EXIT_OPERATION_FAILURE, origin="extra-less set")
    assert extra_set.stderr_text == extra_list.stderr_text, (
        "extra-less set report differs from extra-less list"
    )
    _require_missing_file(ws, f"{absent_dir.name}/.env", origin="extra-less set")


# ---------------------------------------------------------------------------
# B. set / get / unset success text and file effects
# ---------------------------------------------------------------------------


def test_set_prints_requested_binding_creates_file_and_list_shows_both(isolated_ws):
    ws = isolated_ws
    _require_missing_file(ws, ".env", origin="public set start")

    first = cli_invoke(ws, ["set", "USER", "foo"])
    first_out = require_cli_success(first, origin="set USER foo")
    require_independent_line(first_out, "USER=foo", origin="set USER stdout")
    require_absent_independent_line(
        first_out, "USER='foo'", origin="set USER stdout not disk form"
    )

    second = cli_invoke(ws, ["set", "EMAIL", "foo@example.org"])
    second_out = require_cli_success(second, origin="set EMAIL")
    require_independent_line(
        second_out, "EMAIL=foo@example.org", origin="set EMAIL stdout"
    )

    listed = require_cli_success(cli_invoke(ws, ["list"]), origin="list after two sets")
    require_independent_line(listed, "USER=foo", origin="list after set")
    require_independent_line(
        listed, "EMAIL=foo@example.org", origin="list after set EMAIL"
    )
    created = _file_text(ws, ".env", origin="public set created")
    print(f"public set disk={created!r}", flush=True)
    assert created, "set did not create the default .env"

    rt_a, rt_va = unique_token(), unique_token()
    rt_b, rt_vb = unique_token(), unique_token()
    rt_dir = ws.mkdir(unique_token())
    _require_missing_file(ws, f"{rt_dir.name}/.env", origin="runtime set start")
    rt_first = require_cli_success(
        cli_invoke(ws, ["set", rt_a, rt_va], cwd=rt_dir),
        origin="runtime set first",
    )
    require_independent_line(rt_first, f"{rt_a}={rt_va}", origin="runtime set first")
    rt_second = require_cli_success(
        cli_invoke(ws, ["set", rt_b, rt_vb], cwd=rt_dir),
        origin="runtime set second",
    )
    require_independent_line(rt_second, f"{rt_b}={rt_vb}", origin="runtime set second")
    rt_listed = require_cli_success(
        cli_invoke(ws, ["list"], cwd=rt_dir),
        origin="runtime list after two sets",
    )
    require_independent_line(
        rt_listed, f"{rt_a}={rt_va}", origin="runtime list first"
    )
    require_independent_line(
        rt_listed, f"{rt_b}={rt_vb}", origin="runtime list second"
    )

    always_dir = ws.mkdir(unique_token())
    always_out = require_cli_success(
        cli_invoke(ws, ["set", "a", "x"], cwd=always_dir),
        origin="omitted-quote set a x",
    )
    require_independent_line(always_out, "a=x", origin="omitted-quote stdout")
    always_disk = _file_text(ws, f"{always_dir.name}/.env", origin="omitted-quote disk")
    require_independent_line(always_disk, "a='x'", origin="omitted-quote disk")

    rt_name, rt_val = unique_token(), unique_token()
    rt_always = ws.mkdir(unique_token())
    rt_stdout = require_cli_success(
        cli_invoke(ws, ["set", rt_name, rt_val], cwd=rt_always),
        origin="runtime omitted-quote set",
    )
    require_independent_line(
        rt_stdout, f"{rt_name}={rt_val}", origin="runtime omitted-quote stdout"
    )
    rt_disk = _file_text(
        ws, f"{rt_always.name}/.env", origin="runtime omitted-quote disk"
    )
    require_independent_line(
        rt_disk, f"{rt_name}='{rt_val}'", origin="runtime omitted-quote disk"
    )


def test_get_prints_non_empty_value_followed_by_newline(isolated_ws):
    ws = isolated_ws
    ws.write(".env", "A=x\n")
    public = require_cli_success(cli_invoke(ws, ["get", "A"]), origin="get A")
    assert public == "x\n", f"get A stdout is {public!r}, not 'x\\n'"

    name, value = unique_token(), unique_token()
    rt_dir = ws.mkdir(unique_token())
    ws.write(f"{rt_dir.name}/.env", f"{name}={value}\n")
    runtime = require_cli_success(
        cli_invoke(ws, ["get", name], cwd=rt_dir),
        origin="runtime get",
    )
    assert runtime == f"{value}\n", (
        f"runtime get stdout is {runtime!r}, not {value!r} plus newline"
    )

    quoted = ws.mkdir(unique_token())
    ws.write(f"{quoted.name}/.env", "x='a b c'\n")
    spaced = require_cli_success(
        cli_invoke(ws, ["get", "x"], cwd=quoted),
        origin="get quoted stored value",
    )
    assert spaced == "a b c\n", (
        f"get of x='a b c' printed {spaced!r}, not the parsed stored value"
    )
    assert spaced != "'a b c'\n", "get printed the raw quoted slice"

    set_dir = ws.mkdir(unique_token())
    set_name, set_value = unique_token(), unique_token()
    require_cli_success(
        cli_invoke(ws, ["set", set_name, set_value], cwd=set_dir),
        origin="set before get",
    )
    after_set = require_cli_success(
        cli_invoke(ws, ["get", set_name], cwd=set_dir),
        origin="get after omitted-quote set",
    )
    assert after_set == f"{set_value}\n", (
        f"get after set printed {after_set!r}, not requested {set_value!r}"
    )
    disk = _file_text(ws, f"{set_dir.name}/.env", origin="disk after set")
    quoted_disk = f"{set_name}='{set_value}'"
    if quoted_disk in disk.splitlines():
        assert after_set != f"'{set_value}'\n", (
            "get printed the on-disk quoted spelling"
        )


def test_unset_removes_binding_and_identifies_removed_name(isolated_ws):
    ws = isolated_ws
    ws.write(".env", "a=b\n")
    public = require_cli_success(cli_invoke(ws, ["unset", "a"]), origin="unset a")
    assert len(public.splitlines()) == 1 and "a" in public, (
        f"unset confirmation is not one line naming a: {public!r}"
    )
    print(f"unset a confirmation={public!r}", flush=True)
    leftover = _file_text(ws, ".env", origin="after unset a")
    require_absent_independent_line(leftover, "a=b", origin="after unset a")
    missing = require_cli_unsuccessful(
        cli_invoke(ws, ["get", "a"]),
        origin="get a after unset",
    )
    _require_empty_output(missing, origin="get a after unset")

    n1, v1 = unique_token(), unique_token()
    n2, v2 = unique_token(), unique_token()
    d1 = ws.mkdir(unique_token())
    d2 = ws.mkdir(unique_token())
    ws.write(f"{d1.name}/.env", f"{n1}={v1}\n")
    ws.write(f"{d2.name}/.env", f"{n2}={v2}\n")
    r1 = require_cli_success(
        cli_invoke(ws, ["unset", n1], cwd=d1), origin="unset name-one"
    )
    r2 = require_cli_success(
        cli_invoke(ws, ["unset", n2], cwd=d2), origin="unset name-two"
    )
    for text, name, other in ((r1, n1, n2), (r2, n2, n1)):
        lines = text.splitlines()
        assert len(lines) == 1 and name in lines[0], (
            f"unset confirmation is not one line naming {name!r}: {text!r}"
        )
        assert other not in text, f"unset confirmation names {other!r}: {text!r}"

    keep_name, keep_val = unique_token(), unique_token()
    drop_name, drop_val = unique_token(), unique_token()
    pair = ws.mkdir(unique_token())
    ws.write(
        f"{pair.name}/.env",
        f"{keep_name}={keep_val}\n{drop_name}={drop_val}\n",
    )
    require_cli_success(
        cli_invoke(ws, ["unset", drop_name], cwd=pair),
        origin="unset one of two",
    )
    kept = require_cli_success(
        cli_invoke(ws, ["get", keep_name], cwd=pair),
        origin="sibling after unset",
    )
    assert kept == f"{keep_val}\n", (
        f"unset removed the sibling; get {keep_name!r} is {kept!r}"
    )
    dropped = require_cli_unsuccessful(
        cli_invoke(ws, ["get", drop_name], cwd=pair),
        origin="get dropped name",
    )
    _require_empty_output(dropped, origin="get dropped name")


# ---------------------------------------------------------------------------
# C. list formats
# ---------------------------------------------------------------------------


def _list_fixture_source(
    *,
    public_other: str,
    runtime_first: str,
    runtime_first_val: str,
    runtime_second: str,
    runtime_second_val: str,
    quoted_name: str,
    quoted_left: str,
    quoted_right: str,
) -> str:
    # Insert order is the reverse of sorted name order for the valued pair.
    # Interior single quote is stored in the always-quoted on-disk form.
    quoted_stored = quoted_name + "='" + quoted_left + "\\'" + quoted_right + "'"
    return (
        f"{public_other}=first-written\n"
        "x='a b c'\n"
        "FOO\n"
        "EMPTY=\n"
        "NONE\n"
        f"{runtime_first}={runtime_first_val}\n"
        f"{runtime_second}={runtime_second_val}\n"
        f"{quoted_stored}\n"
    )


def test_list_simple_default_is_unquoted_sorted_and_omits_no_value(isolated_ws):
    ws = isolated_ws
    public_other = "zzzpublic"
    rt_hi, rt_hi_val = "z" + unique_token(), unique_token()
    rt_lo, rt_lo_val = "a" + unique_token(), unique_token()
    qname = unique_token()
    qleft, qright = unique_token(), unique_token()
    qval = qleft + "'" + qright
    source = _list_fixture_source(
        public_other=public_other,
        runtime_first=rt_hi,
        runtime_first_val=rt_hi_val,
        runtime_second=rt_lo,
        runtime_second_val=rt_lo_val,
        quoted_name=qname,
        quoted_left=qleft,
        quoted_right=qright,
    )
    ws.write(".env", source)

    omitted = require_cli_success(cli_invoke(ws, ["list"]), origin="list default")
    explicit = require_cli_success(
        cli_invoke(ws, ["list", "--format", SIMPLE_FORMAT]),
        origin="list --format simple",
    )
    assert omitted == explicit, (
        "omitted --format and --format simple differ: "
        f"omitted={omitted!r} simple={explicit!r}"
    )
    require_independent_line(omitted, "x=a b c", origin="simple public spaced")
    require_absent_independent_line(
        omitted, "x='a b c'", origin="simple must not keep stored quotes"
    )
    require_independent_line(omitted, "EMPTY=", origin="simple empty string")
    names = _assignment_names(omitted, origin="simple")
    assert "FOO" not in names, f"simple listed no-value FOO; names={names!r}"
    assert "NONE" not in names, f"simple listed no-value NONE; names={names!r}"
    require_independent_line(
        omitted, f"{public_other}=first-written", origin="simple public other"
    )
    require_independent_line(
        omitted, f"{rt_lo}={rt_lo_val}", origin="simple runtime lo"
    )
    require_independent_line(
        omitted, f"{rt_hi}={rt_hi_val}", origin="simple runtime hi"
    )
    require_independent_line(
        omitted, f"{qname}={qval}", origin="simple interior quote unquoted"
    )
    valued = [n for n in names]
    _require_sorted_names(valued, origin="simple")
    assert names.index("x") < names.index(public_other), (
        f"simple did not reorder reverse-inserted public names: {names!r}"
    )
    assert names.index(rt_lo) < names.index(rt_hi), (
        f"simple did not reorder reverse-inserted runtime names: {names!r}"
    )


def test_list_json_is_pretty_sorted_with_null_for_no_value(isolated_ws):
    ws = isolated_ws
    public_other = "zzzpublic"
    rt_hi, rt_hi_val = "z" + unique_token(), unique_token()
    rt_lo, rt_lo_val = "a" + unique_token(), unique_token()
    qname = unique_token()
    qleft, qright = unique_token(), unique_token()
    qval = qleft + "'" + qright
    ws.write(
        ".env",
        _list_fixture_source(
            public_other=public_other,
            runtime_first=rt_hi,
            runtime_first_val=rt_hi_val,
            runtime_second=rt_lo,
            runtime_second_val=rt_lo_val,
            quoted_name=qname,
            quoted_left=qleft,
            quoted_right=qright,
        ),
    )
    raw = require_cli_success(
        cli_invoke(ws, ["list", "--format", JSON_FORMAT]),
        origin="list json",
    )
    obj = json.loads(raw)
    assert isinstance(obj, dict), f"json list is not an object: {obj!r}"
    stripped = raw.rstrip("\n")
    assert "\n" in stripped, f"json list is not pretty-printed: {raw!r}"
    compact = json.dumps(obj, separators=(",", ":"))
    assert stripped.strip() != compact, (
        f"json list equals compact encoding: {stripped!r}"
    )
    assert obj["x"] == "a b c", f"json x is {obj['x']!r}, not 'a b c'"
    assert obj["FOO"] is None, f"json FOO is {obj['FOO']!r}, not JSON null"
    assert obj["NONE"] is None, f"json NONE is {obj['NONE']!r}, not JSON null"
    assert obj["EMPTY"] == "", f"json EMPTY is {obj['EMPTY']!r}, not empty string"
    assert obj[public_other] == "first-written"
    assert obj[rt_lo] == rt_lo_val
    assert obj[rt_hi] == rt_hi_val
    assert obj[qname] == qval
    keys = list(obj.keys())
    _require_sorted_names(keys, origin="json keys")
    expected = sorted(
        ["x", public_other, "FOO", "EMPTY", "NONE", rt_hi, rt_lo, qname]
    )
    assert keys == expected, f"json keys {keys!r} are not {expected!r}"


def test_list_shell_and_export_are_posix_pasteable_and_omit_no_value(isolated_ws):
    ws = isolated_ws
    public_other = "zzzpublic"
    rt_hi, rt_hi_val = "z" + unique_token(), unique_token()
    rt_lo, rt_lo_val = "a" + unique_token(), unique_token()
    qname = unique_token()
    qleft, qright = unique_token(), unique_token()
    qval = qleft + "'" + qright
    ws.write(
        ".env",
        _list_fixture_source(
            public_other=public_other,
            runtime_first=rt_hi,
            runtime_first_val=rt_hi_val,
            runtime_second=rt_lo,
            runtime_second_val=rt_lo_val,
            quoted_name=qname,
            quoted_left=qleft,
            quoted_right=qright,
        ),
    )
    simple = require_cli_success(cli_invoke(ws, ["list"]), origin="shell contrast simple")
    shell = require_cli_success(
        cli_invoke(ws, ["list", "--format", SHELL_FORMAT]),
        origin="list shell",
    )
    export = require_cli_success(
        cli_invoke(ws, ["list", "--format", EXPORT_FORMAT]),
        origin="list export",
    )
    simple_x = _line_for_name(simple, "x", origin="simple x")
    shell_x = _line_for_name(shell, "x", origin="shell x")
    assert simple_x != shell_x, (
        f"shell line for spaced x is identical to simple: {shell_x!r}"
    )
    assert posix_shell_value(shell_x, "x") == "a b c"
    space_name, space_val = unique_token(), unique_token() + " " + unique_token()
    spaced_dir = ws.mkdir(unique_token())
    ws.write(f"{spaced_dir.name}/.env", f"{space_name}='{space_val}'\n")
    rt_shell = require_cli_success(
        cli_invoke(ws, ["list", "--format", SHELL_FORMAT], cwd=spaced_dir),
        origin="runtime spaced shell",
    )
    assert posix_shell_value(
        _line_for_name(rt_shell, space_name, origin="runtime spaced shell"),
        space_name,
    ) == space_val

    quoted_line = _line_for_name(shell, qname, origin="shell interior quote")
    assert posix_shell_value(quoted_line, qname) == qval

    shell_names = _assignment_names(shell, origin="shell")
    export_names = _assignment_names(export, prefix=EXPORT_PREFIX, origin="export")
    assert "FOO" not in shell_names, f"shell listed FOO: {shell_names!r}"
    assert "NONE" not in shell_names, f"shell listed NONE: {shell_names!r}"
    assert "FOO" not in export_names, f"export listed FOO: {export_names!r}"
    assert "NONE" not in export_names, f"export listed NONE: {export_names!r}"
    assert "EMPTY" in shell_names, f"shell omitted EMPTY: {shell_names!r}"
    assert "EMPTY" in export_names, f"export omitted EMPTY: {export_names!r}"
    empty_line = _line_for_name(shell, "EMPTY", origin="shell EMPTY")
    assert posix_shell_value(empty_line, "EMPTY") == ""
    export_empty = _line_for_name(
        export, "EMPTY", prefix=EXPORT_PREFIX, origin="export EMPTY"
    )
    assert posix_shell_value(export_empty[len(EXPORT_PREFIX) :], "EMPTY") == ""

    _require_sorted_names(shell_names, origin="shell")
    _require_sorted_names(export_names, origin="export")
    assert shell_names.index("x") < shell_names.index(public_other), (
        f"shell did not sort reverse-inserted public names: {shell_names!r}"
    )
    assert shell_names.index(rt_lo) < shell_names.index(rt_hi), (
        f"shell did not sort reverse-inserted runtime names: {shell_names!r}"
    )
    assert export_names == shell_names, (
        f"export names {export_names!r} differ from shell {shell_names!r}"
    )
    for name in shell_names:
        shell_line = _line_for_name(shell, name, origin="shell pair")
        export_line = _line_for_name(
            export, name, prefix=EXPORT_PREFIX, origin="export pair"
        )
        assert export_line == EXPORT_PREFIX + shell_line, (
            f"export line {export_line!r} is not {EXPORT_PREFIX!r} plus {shell_line!r}"
        )


# ---------------------------------------------------------------------------
# D. global --file / --quote / --export / --version
# ---------------------------------------------------------------------------


def test_file_flag_selects_path_and_omitted_file_reads_cwd_env(isolated_ws):
    ws = isolated_ws
    ws.write(".env", "A=x\nUSER=foo\n")
    omitted = require_cli_success(cli_invoke(ws, ["get", "A"]), origin="omitted --file get A")
    assert omitted == "x\n", f"omitted --file get A printed {omitted!r}"

    other_rel = f"other-{unique_token()}.env"
    cwd_name, cwd_val = unique_token(), unique_token()
    side_name, side_val = unique_token(), unique_token()
    drop_name, drop_val = unique_token(), unique_token()
    ws.write(".env", f"A=x\nUSER=foo\n{cwd_name}={cwd_val}\n")
    ws.write(other_rel, f"A=other\n{side_name}={side_val}\n{drop_name}={drop_val}\n")
    other_path = ws.resolve(other_rel)

    flagged = require_cli_success(
        cli_invoke(ws, ["--file", other_rel, "get", "A"]),
        origin="--file get A",
    )
    assert flagged == "other\n", f"--file get A printed {flagged!r}, not 'other\\n'"
    short = require_cli_success(
        cli_invoke(ws, ["-f", other_rel, "get", "A"]),
        origin="-f get A",
    )
    assert short == "other\n", f"-f get A printed {short!r}, not 'other\\n'"

    listed = require_cli_success(
        cli_invoke(ws, ["--file", other_rel, "list"]),
        origin="list --file sidecar",
    )
    require_independent_line(listed, "A=other", origin="list --file sidecar")
    names = _assignment_names(listed, origin="list --file")
    assert "USER" not in names, f"list --file showed cwd USER: {names!r}"
    assert cwd_name not in names, f"list --file showed cwd name {cwd_name!r}"
    require_independent_line(
        listed, f"{side_name}={side_val}", origin="list --file sidecar runtime"
    )

    cwd_before = ws.read_bytes(".env")
    new_name, new_val = unique_token(), unique_token()
    require_cli_success(
        cli_invoke(ws, ["--file", other_rel, "set", new_name, new_val]),
        origin="set --file sidecar",
    )
    got_new = require_cli_success(
        cli_invoke(ws, ["--file", other_rel, "get", new_name]),
        origin="get --file after set",
    )
    assert got_new == f"{new_val}\n", (
        f"set --file did not store on the sidecar; get printed {got_new!r}"
    )
    assert ws.read_bytes(".env") == cwd_before, (
        "set --file changed the working-directory .env"
    )
    cwd_listed = require_cli_success(cli_invoke(ws, ["list"]), origin="cwd list after set --file")
    cwd_names = _assignment_names(cwd_listed, origin="cwd after set --file")
    assert new_name not in cwd_names, (
        f"set --file wrote {new_name!r} into cwd .env; names={cwd_names!r}"
    )

    cwd_before = ws.read_bytes(".env")
    require_cli_success(
        cli_invoke(ws, ["--file", other_rel, "unset", drop_name]),
        origin="unset --file sidecar",
    )
    dropped = require_cli_unsuccessful(
        cli_invoke(ws, ["--file", other_rel, "get", drop_name]),
        origin="get --file after unset",
    )
    _require_empty_output(dropped, origin="get --file after unset")
    assert ws.read_bytes(".env") == cwd_before, (
        "unset --file changed the working-directory .env"
    )
    print(f"sidecar path={other_path}", flush=True)

    leaf = ws.mkdir("anc/leaf")
    ws.write("anc/.env", "A=x\n")
    walked = require_cli_unsuccessful(
        cli_invoke(ws, ["get", "A"], cwd=leaf),
        origin="get A in child without .env",
    )
    report = _require_nonempty_report(walked, origin="no-walk get")
    require_exit(walked, EXIT_USAGE_FAILURE, origin="no-walk get")
    assert walked.stdout_text != "x\n", (
        f"omitted --file walked to the ancestor and printed {walked.stdout_text!r}"
    )
    assert "x" not in walked.stdout_text.splitlines(), (
        "omitted --file printed ancestor value x"
    )
    key_dir = ws.mkdir(unique_token())
    ws.write(f"{key_dir.name}/.env", f"{unique_token()}={unique_token()}\n")
    missing_key = require_cli_unsuccessful(
        cli_invoke(ws, ["get", "A"], cwd=key_dir),
        origin="missing-key class for no-walk contrast",
    )
    _require_empty_output(missing_key, origin="missing-key class for no-walk")
    assert walked.returncode != 0 and missing_key.returncode != 0
    assert walked.returncode != missing_key.returncode, (
        "child-without-.env is not usage-class distinct from missing-key; "
        f"walk={walked.returncode} key={missing_key.returncode} report={report!r}"
    )


def test_quote_and_export_flags_on_set(isolated_ws):
    ws = isolated_ws
    never_rel = f"never-{unique_token()}.env"
    always_rel = f"always-{unique_token()}.env"
    require_cli_success(
        cli_invoke(ws, ["--file", never_rel, "--quote", "never", "set", "a", "x"]),
        origin="--quote never set a x",
    )
    never_disk = _file_text(ws, never_rel, origin="quote never disk")
    require_independent_line(never_disk, "a=x", origin="quote never disk")
    require_cli_success(
        cli_invoke(ws, ["--file", always_rel, "set", "a", "x"]),
        origin="omitted quote set a x",
    )
    always_disk = _file_text(ws, always_rel, origin="omitted quote disk")
    require_independent_line(always_disk, "a='x'", origin="omitted quote disk")
    assert never_disk != always_disk, (
        "quote never and omitted quote stored the same bytes"
    )

    short_rel = f"short-never-{unique_token()}.env"
    require_cli_success(
        cli_invoke(ws, ["--file", short_rel, "-q", "never", "set", "a", "x"]),
        origin="-q never set a x",
    )
    require_independent_line(
        _file_text(ws, short_rel, origin="-q never disk"),
        "a=x",
        origin="-q never disk",
    )

    auto_alnum = f"auto-alnum-{unique_token()}.env"
    auto_space = f"auto-space-{unique_token()}.env"
    require_cli_success(
        cli_invoke(ws, ["--file", auto_alnum, "--quote", "auto", "set", "a", "x"]),
        origin="quote auto alphanumeric",
    )
    require_independent_line(
        _file_text(ws, auto_alnum, origin="auto alnum disk"),
        "a=x",
        origin="auto alnum disk",
    )
    require_cli_success(
        cli_invoke(ws, ["--file", auto_space, "--quote", "auto", "set", "a", "x y"]),
        origin="quote auto spaced",
    )
    require_independent_line(
        _file_text(ws, auto_space, origin="auto space disk"),
        "a='x y'",
        origin="auto space disk",
    )

    export_rel = f"export-{unique_token()}.env"
    no_export_rel = f"no-export-{unique_token()}.env"
    require_cli_success(
        cli_invoke(ws, ["--file", export_rel, "--export", "true", "set", "a", "x"]),
        origin="--export true set a x",
    )
    export_disk = _file_text(ws, export_rel, origin="export true disk")
    export_lines = [ln for ln in export_disk.splitlines() if ln]
    assert export_lines, "export true stored no lines"
    for line in export_lines:
        assert line.startswith(EXPORT_PREFIX), (
            f"--export true line {line!r} does not start with {EXPORT_PREFIX!r}"
        )
    require_independent_line(
        export_disk, "export a='x'", origin="export true public form"
    )
    require_cli_success(
        cli_invoke(ws, ["--file", no_export_rel, "set", "a", "x"]),
        origin="omitted --export set a x",
    )
    no_export_disk = _file_text(ws, no_export_rel, origin="omitted export disk")
    for line in no_export_disk.splitlines():
        if line:
            assert not line.startswith(EXPORT_PREFIX), (
                f"omitted --export still prefixed {line!r}"
            )
    require_independent_line(no_export_disk, "a='x'", origin="omitted export disk")

    short_export = f"short-export-{unique_token()}.env"
    require_cli_success(
        cli_invoke(ws, ["--file", short_export, "-e", "true", "set", "a", "x"]),
        origin="-e true set a x",
    )
    short_disk = _file_text(ws, short_export, origin="-e true disk")
    assert any(ln.startswith(EXPORT_PREFIX) for ln in short_disk.splitlines()), (
        f"-e true stored no export-prefixed line: {short_disk!r}"
    )


def test_version_ends_with_installed_version_including_before_run(isolated_ws):
    ws = isolated_ws
    version = installed_distribution_version()
    shown = require_cli_success(cli_invoke(ws, ["--version"]), origin="--version")
    stripped = shown.rstrip("\n")
    assert stripped.endswith(version), (
        f"--version text {stripped!r} does not end with installed version {version!r}"
    )

    marker = f"ran-{unique_token()}.marker"
    _require_missing_file(ws, marker, origin="version-before-run marker start")
    before_run = require_cli_success(
        cli_invoke(ws, ["--version", "run", "touch", marker]),
        origin="--version before run",
    )
    before_stripped = before_run.rstrip("\n")
    assert before_stripped.endswith(version), (
        f"--version before run printed {before_stripped!r}, "
        f"not ending with {version!r}"
    )
    _require_missing_file(ws, marker, origin="--version before run must not start child")


# ---------------------------------------------------------------------------
# E. unopenable vs missing-key; set without both arguments
# ---------------------------------------------------------------------------


def test_unopenable_path_is_usage_class_distinct_from_missing_or_empty_key(isolated_ws):
    ws = isolated_ws
    present, present_val = unique_token(), unique_token()
    ws.write(".env", f"{present}={present_val}\n")

    missing_one = f"missing-{unique_token()}.env"
    missing_two = f"missing-{unique_token()}.env"
    miss_one_path = ws.resolve(missing_one)
    miss_two_path = ws.resolve(missing_two)

    list_miss = require_cli_unsuccessful(
        cli_invoke(ws, ["--file", missing_one, "list"]),
        origin="list missing file",
    )
    get_miss = require_cli_unsuccessful(
        cli_invoke(ws, ["--file", missing_one, "get", present]),
        origin="get missing file",
    )
    list_miss_two = require_cli_unsuccessful(
        cli_invoke(ws, ["--file", missing_two, "list"]),
        origin="list other missing file",
    )
    list_report = _require_nonempty_report(list_miss, origin="list missing file")
    get_report = _require_nonempty_report(get_miss, origin="get missing file")
    for result, rel, origin in (
        (list_miss, missing_one, "list missing file"),
        (get_miss, missing_one, "get missing file"),
        (list_miss_two, missing_two, "list other missing file"),
    ):
        require_exit(result, EXIT_USAGE_FAILURE, origin=origin)
        assert result.stdout_text == "", f"{origin} wrote stdout {result.stdout_text!r}"
        assert rel in result.stderr_text, (
            f"{origin} report does not name the path {rel!r}: {result.stderr_text!r}"
        )

    dir_rel = unique_token()
    dir_path = ws.mkdir(dir_rel)
    list_dir = require_cli_unsuccessful(
        cli_invoke(ws, ["--file", dir_rel, "list"]),
        origin="list directory",
    )
    get_dir = require_cli_unsuccessful(
        cli_invoke(ws, ["--file", dir_rel, "get", present]),
        origin="get directory",
    )
    dir_report = _require_nonempty_report(list_dir, origin="list directory")
    get_dir_report = _require_nonempty_report(get_dir, origin="get directory")
    for result, origin in ((list_dir, "list directory"), (get_dir, "get directory")):
        require_exit(result, EXIT_USAGE_FAILURE, origin=origin)
        assert dir_rel in result.stderr_text, (
            f"{origin} report does not name the path {dir_rel!r}: {result.stderr_text!r}"
        )

    present_get = require_cli_success(
        cli_invoke(ws, ["get", present]),
        origin="get present name",
    )
    assert present_get == f"{present_val}\n"

    other = unique_token()
    other_two = unique_token()
    miss_key = require_cli_unsuccessful(
        cli_invoke(ws, ["get", other]),
        origin="get missing name",
    )
    miss_key_two = require_cli_unsuccessful(
        cli_invoke(ws, ["get", other_two]),
        origin="get other missing name",
    )
    _require_empty_output(miss_key, origin="get missing name")
    _require_empty_output(miss_key_two, origin="get other missing name")
    assert present_val not in miss_key.stdout_text, (
        "missing-name get printed a present value"
    )
    assert miss_key.returncode == miss_key_two.returncode, (
        "two missing names are not the same missing-key class; "
        f"{miss_key.returncode} vs {miss_key_two.returncode}"
    )
    for usage in (list_miss, get_miss, list_dir, get_dir):
        assert usage.returncode != 0
        assert miss_key.returncode != 0
        assert usage.returncode != miss_key.returncode, (
            "unopenable exit is the missing-key class; "
            f"usage={usage.returncode} key={miss_key.returncode}"
        )
        assert cli_streams(usage) != "", "usage-class report is empty like missing-key"

    empty_name = unique_token()
    empty_dir = ws.mkdir(unique_token())
    ws.write(f"{empty_dir.name}/.env", f"{empty_name}=\n{present}={present_val}\n")
    empty_get = require_cli_unsuccessful(
        cli_invoke(ws, ["get", empty_name], cwd=empty_dir),
        origin="get empty stored value",
    )
    _require_empty_output(empty_get, origin="get empty stored value")
    assert empty_get.returncode == miss_key.returncode, (
        "empty stored value is not the missing-key class; "
        f"empty={empty_get.returncode} missing={miss_key.returncode}"
    )
    assert empty_get.returncode != list_miss.returncode, (
        "empty stored value is not distinct from missing-file usage class"
    )

    public_empty = ws.mkdir(unique_token())
    ws.write(f"{public_empty.name}/.env", "NAME=\n")
    public_empty_get = require_cli_unsuccessful(
        cli_invoke(ws, ["get", "NAME"], cwd=public_empty),
        origin="get public empty NAME=",
    )
    _require_empty_output(public_empty_get, origin="get public empty NAME=")
    assert public_empty_get.returncode == miss_key.returncode


def test_unset_missing_name_fails_and_leaves_file_unchanged(isolated_ws):
    ws = isolated_ws
    ws.write(".env", "a=b\n")
    before = ws.read_bytes(".env")
    require_cli_success(cli_invoke(ws, ["unset", "a"]), origin="unset present baseline")
    after_ok = _file_text(ws, ".env", origin="after successful unset")
    require_absent_independent_line(after_ok, "a=b", origin="baseline unset")

    occupied = f"{unique_token()}={unique_token()}\n"
    ws.write(".env", occupied)
    before = ws.read_bytes(".env")
    missing = unique_token()
    fail = require_cli_unsuccessful(
        cli_invoke(ws, ["unset", missing]),
        origin="unset missing name",
    )
    print(f"unset missing report={cli_streams(fail)!r}", flush=True)
    assert ws.read_bytes(".env") == before, (
        "unset of a missing name changed the file"
    )

    token, value = unique_token(), unique_token()
    other = unique_token()
    occ = ws.mkdir(unique_token())
    ws.write(f"{occ.name}/.env", f"{token}={value}\n")
    before_rt = ws.read_bytes(f"{occ.name}/.env")
    require_cli_unsuccessful(
        cli_invoke(ws, ["unset", other], cwd=occ),
        origin="runtime unset missing",
    )
    after_rt = _file_text(ws, f"{occ.name}/.env", origin="runtime after missing unset")
    require_independent_line(
        after_rt, f"{token}={value}", origin="runtime missing unset kept binding"
    )
    assert ws.read_bytes(f"{occ.name}/.env") == before_rt


def test_set_without_both_arguments_is_usage_failure(isolated_ws):
    ws = isolated_ws
    name, value = unique_token(), unique_token()
    baseline = require_cli_success(
        cli_invoke(ws, ["set", name, value]),
        origin="set both arguments baseline",
    )
    require_independent_line(baseline, f"{name}={value}", origin="baseline set stdout")
    listed = require_cli_success(cli_invoke(ws, ["list"]), origin="list after baseline set")
    require_independent_line(listed, f"{name}={value}", origin="list after baseline set")

    miss_key = require_cli_unsuccessful(
        cli_invoke(ws, ["get", unique_token()]),
        origin="missing-key contrast for set usage",
    )
    _require_empty_output(miss_key, origin="missing-key contrast for set usage")

    no_args = require_cli_unsuccessful(cli_invoke(ws, ["set"]), origin="set without args")
    no_value = require_cli_unsuccessful(
        cli_invoke(ws, ["set", name]),
        origin="set name without value",
    )
    for result, origin in ((no_args, "set without args"), (no_value, "set name only")):
        report = _require_nonempty_report(result, origin=origin)
        assert result.returncode != 0
        _require_nonempty_report(result, origin=origin)
        assert not (
            result.stdout_text == "" and result.stderr_text == ""
        ), f"{origin} is missing-key empty output"
        print(f"{origin} report={report!r}", flush=True)

    missing_rel = f"missing-{unique_token()}.env"
    missing_path = ws.resolve(missing_rel)
    unopenable = require_cli_unsuccessful(
        cli_invoke(ws, ["--file", missing_rel, "list"]),
        origin="unopenable contrast for set usage",
    )
    unopen_report = _require_nonempty_report(unopenable, origin="unopenable contrast")
    for result, origin in ((no_args, "set without args"), (no_value, "set name only")):
        require_exit(result, EXIT_USAGE_FAILURE, origin=origin)
        assert result.stdout_text == "", f"{origin} wrote stdout {result.stdout_text!r}"
        assert has_usage_label(result.stderr_text), (
            f"{origin} report has no usage label: {result.stderr_text!r}"
        )
    require_exit(unopenable, EXIT_USAGE_FAILURE, origin="unopenable contrast")
    assert not has_usage_label(unopen_report), (
        "could-not-open report carries the missing-argument usage label"
    )

    absent = ws.mkdir(unique_token())
    require_cli_unsuccessful(
        cli_invoke(ws, ["set"], cwd=absent),
        origin="set no args on missing path",
    )
    _require_missing_file(ws, f"{absent.name}/.env", origin="set no args")
    require_cli_unsuccessful(
        cli_invoke(ws, ["set", unique_token()], cwd=absent),
        origin="set name only on missing path",
    )
    _require_missing_file(ws, f"{absent.name}/.env", origin="set name only")

    occupied = ws.mkdir(unique_token())
    ws.write(f"{occupied.name}/.env", f"{name}={value}\n")
    before = ws.read_bytes(f"{occupied.name}/.env")
    require_cli_unsuccessful(
        cli_invoke(ws, ["set", unique_token()], cwd=occupied),
        origin="set name only on existing file",
    )
    assert ws.read_bytes(f"{occupied.name}/.env") == before, (
        "set NAME without a value rewrote the existing file"
    )


# ---------------------------------------------------------------------------
# F. set / unset default do not follow symbolic links
# ---------------------------------------------------------------------------


def test_set_and_unset_do_not_follow_symlinks(isolated_ws):
    ws = isolated_ws
    ws.write("target.env", "a=x\n")
    env_path = ws.symlink(".env", "target.env")
    require_cli_success(cli_invoke(ws, ["set", "a", "y"]), origin="set through symlink")
    target = _file_text(ws, "target.env", origin="set target")
    require_independent_line(target, "a=x", origin="set must not follow")
    assert not path_is_symlink(env_path), f"{env_path} is still a symlink after set"
    assert path_is_file(env_path), f"{env_path} is not a regular file after set"
    got = require_cli_success(cli_invoke(ws, ["get", "a"]), origin="get after symlink set")
    assert got == "y\n", f"get after symlink set printed {got!r}"
    disk = _file_text(ws, ".env", origin="new file after set")
    require_independent_line(disk, "a='y'", origin="new file stores a='y'")

    rt_name, rt_old, rt_new = unique_token(), unique_token(), unique_token()
    ws.write("rt-target.env", f"{rt_name}={rt_old}\n")
    rt_env = ws.symlink("rt.env", "rt-target.env")
    require_cli_success(
        cli_invoke(ws, ["--file", "rt.env", "set", rt_name, rt_new]),
        origin="runtime set through symlink",
    )
    require_independent_line(
        _file_text(ws, "rt-target.env", origin="runtime set target"),
        f"{rt_name}={rt_old}",
        origin="runtime set must not follow",
    )
    assert not path_is_symlink(rt_env), f"{rt_env} is still a symlink"
    rt_got = require_cli_success(
        cli_invoke(ws, ["--file", "rt.env", "get", rt_name]),
        origin="runtime get after symlink set",
    )
    assert rt_got == f"{rt_new}\n"

    unset_dir = ws.mkdir(unique_token())
    ws.write(f"{unset_dir.name}/target.env", "a=x\n")
    unset_env = ws.symlink(f"{unset_dir.name}/.env", "target.env")
    require_cli_success(
        cli_invoke(ws, ["unset", "a"], cwd=unset_dir),
        origin="unset through symlink",
    )
    require_independent_line(
        _file_text(ws, f"{unset_dir.name}/target.env", origin="unset target"),
        "a=x",
        origin="unset must not follow",
    )
    assert not path_is_symlink(unset_env), f"{unset_env} is still a symlink after unset"
    assert path_is_file(unset_env), f"{unset_env} is not a regular file after unset"
    gone = require_cli_unsuccessful(
        cli_invoke(ws, ["get", "a"], cwd=unset_dir),
        origin="get after symlink unset",
    )
    _require_empty_output(gone, origin="get after symlink unset")

    dang_set = ws.mkdir(unique_token())
    dang_set_target = "missing-target.env"
    dang_set_env = ws.symlink(f"{dang_set.name}/.env", dang_set_target)
    _require_missing_file(
        ws,
        f"{dang_set.name}/{dang_set_target}",
        origin="dangling set target start",
    )
    require_cli_success(
        cli_invoke(ws, ["set", "a", "y"], cwd=dang_set),
        origin="set through dangling symlink",
    )
    _require_missing_file(
        ws,
        f"{dang_set.name}/{dang_set_target}",
        origin="dangling set must not create missing target",
    )
    assert not path_is_symlink(dang_set_env), (
        f"{dang_set_env} is still a symlink after dangling set"
    )
    assert path_is_file(dang_set_env), (
        f"{dang_set_env} is not a regular file after dangling set"
    )
    dang_got = require_cli_success(
        cli_invoke(ws, ["get", "a"], cwd=dang_set),
        origin="get after dangling set",
    )
    assert dang_got == "y\n", f"get after dangling set printed {dang_got!r}"

    rt_dang_name, rt_dang_val = unique_token(), unique_token()
    rt_dang_set = ws.mkdir(unique_token())
    rt_dang_target = f"missing-{unique_token()}.env"
    rt_dang_env = ws.symlink(f"{rt_dang_set.name}/.env", rt_dang_target)
    require_cli_success(
        cli_invoke(ws, ["set", rt_dang_name, rt_dang_val], cwd=rt_dang_set),
        origin="runtime set through dangling symlink",
    )
    _require_missing_file(
        ws,
        f"{rt_dang_set.name}/{rt_dang_target}",
        origin="runtime dangling set must not create missing target",
    )
    assert not path_is_symlink(rt_dang_env), (
        f"{rt_dang_env} is still a symlink after runtime dangling set"
    )
    assert path_is_file(rt_dang_env), (
        f"{rt_dang_env} is not a regular file after runtime dangling set"
    )
    rt_dang_got = require_cli_success(
        cli_invoke(ws, ["get", rt_dang_name], cwd=rt_dang_set),
        origin="runtime get after dangling set",
    )
    assert rt_dang_got == f"{rt_dang_val}\n", (
        f"runtime get after dangling set printed {rt_dang_got!r}"
    )

    dang_unset = ws.mkdir(unique_token())
    dang_unset_env = ws.symlink(f"{dang_unset.name}/.env", "missing-target.env")
    require_cli_unsuccessful(
        cli_invoke(ws, ["unset", "a"], cwd=dang_unset),
        origin="unset through dangling symlink",
    )
    assert path_is_symlink(dang_unset_env), (
        f"{dang_unset_env} is no longer a symlink after dangling unset"
    )

    rt_dang_unset_name = unique_token()
    rt_dang_unset = ws.mkdir(unique_token())
    rt_dang_unset_env = ws.symlink(
        f"{rt_dang_unset.name}/.env", f"missing-{unique_token()}.env"
    )
    require_cli_unsuccessful(
        cli_invoke(ws, ["unset", rt_dang_unset_name], cwd=rt_dang_unset),
        origin="runtime unset through dangling symlink",
    )
    assert path_is_symlink(rt_dang_unset_env), (
        f"{rt_dang_unset_env} is no longer a symlink after runtime dangling unset"
    )
