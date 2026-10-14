# feature: F06
"""FP-06: read, write, and delete one named binding in a `.env` file.

Assertions stay at the PRD's precision: create-on-missing-write, replace
keeping other bindings and following blanks, quote modes and export prefix
as stored lines, read of text / empty string / no-value / missing name /
missing path, delete of a present name versus missing path / missing name,
default versus follow-links symlink handling, Unix permission bits, and a
named encoding. Success/failure booleans, None, and exception types are
not pinned; diagnostics are read as lines that name the key or path
(Interface Contract).
"""

from __future__ import annotations

import stat
from pathlib import Path

from envfile import get_key, set_key, unset_key  # noqa: F401 — public file-editing entries

from _harness import file_mode, path_is_file, path_is_symlink, workspace
from _helpers import (
    call_with_log_capture,
    delete_one,
    diagnostics_text,
    read_one,
    require_absent_independent_line,
    require_call_completed,
    require_edit_did_not_succeed,
    require_independent_line,
    require_no_text_value,
    require_owner_rw_only,
    require_text_value,
    require_utf8_text,
    diagnostic_lines,
    require_line_naming,
    require_no_line_naming,
    unique_token,
    write_one,
)


def _always_line(name: str, value: str) -> str:
    """Stored line under always: single quotes, interior quotes backslash-escaped."""
    return name + "='" + value.replace("'", "\\'") + "'"


def _file_text(ws, relpath: str, *, origin: str) -> str:
    return require_utf8_text(ws.read_bytes(relpath), origin=origin)


def _logged_read(path: str | Path, name: str, **kwargs):
    result, records = call_with_log_capture(get_key, str(path), name, **kwargs)
    return result, diagnostics_text(result, records)


def _logged_delete(path: str | Path, name: str, **kwargs):
    result, records = call_with_log_capture(unset_key, str(path), name, **kwargs)
    return result, diagnostics_text(result, records)


def _blank_after(text: str, line: str, *, origin: str) -> None:
    lines = text.splitlines()
    assert line in lines, (
        f"{origin} missing independent line {line!r}; lines={lines!r}"
    )
    idx = lines.index(line)
    assert any(i > idx and item == "" for i, item in enumerate(lines)), (
        f"{origin} no blank line after {line!r}; lines={lines!r}"
    )
    print(f"{origin} blank after {line!r}", flush=True)


def _success_delete(ws, name: str):
    path = ws.write(f"{unique_token()}.env", f"{name}={unique_token()}\n")
    result = delete_one(path, name)
    require_call_completed(result, origin="success delete")
    return result


# ---------------------------------------------------------------------------
# A. Create missing path; replace keeping others and blanks; append newline
# ---------------------------------------------------------------------------


def test_write_missing_path_creates_file_and_later_read_returns_value():
    with workspace() as ws:
        public_path = ws.resolve("public.env")
        public = write_one(public_path, "foo", "bar")
        require_call_completed(public, origin="public missing-path write")
        public_bytes = ws.read_bytes("public.env")
        print(f"public created bytes={public_bytes!r}", flush=True)
        assert public_bytes, "missing-path write did not create the file"
        assert require_text_value(
            read_one(public_path, "foo"),
            "bar",
            origin="public later read",
        ) == "bar"
        refused = write_one(
            ws.resolve("refused.env"),
            "foo",
            "bar",
            quote_mode="sometimes",
        )
        require_edit_did_not_succeed(
            refused, public, origin="public missing-path write reports success"
        )
        assert refused.exception is not None or refused.value != public.value, (
            "unknown-quote write is indistinguishable from a successful "
            "missing-path write"
        )

        name, value = unique_token(), unique_token()
        runtime_path = ws.resolve("runtime.env")
        runtime = write_one(runtime_path, name, value)
        require_call_completed(runtime, origin="runtime missing-path write")
        runtime_bytes = ws.read_bytes("runtime.env")
        assert runtime_bytes, "runtime missing-path write did not create the file"
        assert require_text_value(
            read_one(runtime_path, name),
            value,
            origin="runtime later read",
        ) == value
        print(f"success_report={public.value!r}", flush=True)


def test_write_replaces_existing_name_and_keeps_other_bindings():
    with workspace() as ws:
        public_path = ws.write("public.env", "a=b\nc=d\n")
        public = write_one(public_path, "a", "e")
        require_call_completed(public, origin="public replace")
        public_text = _file_text(ws, "public.env", origin="public replace file")
        assert require_text_value(
            read_one(public_path, "a"), "e", origin="public replaced a"
        ) == "e"
        assert require_text_value(
            read_one(public_path, "c"), "d", origin="public kept c"
        ) == "d"
        require_independent_line(public_text, "c=d", origin="public replace")
        require_absent_independent_line(public_text, "a=b", origin="public replace")
        assert "c=d" in public_text.splitlines(), (
            f"public replace dropped sibling line c=d; lines={public_text.splitlines()!r}"
        )
        assert "a=b" not in public_text.splitlines(), (
            f"public replace left original a=b; lines={public_text.splitlines()!r}"
        )

        keep_name, keep_value = unique_token(), unique_token()
        old_name, old_value = unique_token(), unique_token()
        new_value = unique_token()
        runtime_path = ws.write(
            "runtime.env",
            f"{old_name}={old_value}\n{keep_name}={keep_value}\n",
        )
        runtime = write_one(runtime_path, old_name, new_value)
        require_call_completed(runtime, origin="runtime replace")
        runtime_text = _file_text(ws, "runtime.env", origin="runtime replace file")
        assert require_text_value(
            read_one(runtime_path, old_name),
            new_value,
            origin="runtime replaced name",
        ) == new_value
        assert require_text_value(
            read_one(runtime_path, keep_name),
            keep_value,
            origin="runtime kept sibling",
        ) == keep_value
        require_absent_independent_line(
            runtime_text,
            f"{old_name}={old_value}",
            origin="runtime replace",
        )
        require_independent_line(
            runtime_text,
            f"{keep_name}={keep_value}",
            origin="runtime replace",
        )
        assert f"{old_name}={old_value}" not in runtime_text.splitlines(), (
            f"runtime replace left original {old_name}={old_value}; "
            f"lines={runtime_text.splitlines()!r}"
        )
        assert f"{keep_name}={keep_value}" in runtime_text.splitlines(), (
            f"runtime replace dropped sibling {keep_name}={keep_value}; "
            f"lines={runtime_text.splitlines()!r}"
        )


def test_write_keeps_blank_lines_after_replaced_binding():
    with workspace() as ws:
        public_path = ws.write("public.env", "a=b\n\n")
        write_one(public_path, "a", "e")
        public_text = _file_text(ws, "public.env", origin="public blank-after")
        require_absent_independent_line(public_text, "a=b", origin="public blank-after")
        _blank_after(public_text, "a='e'", origin="public blank-after")

        name, old_value, new_value = unique_token(), unique_token(), unique_token()
        runtime_path = ws.write("runtime.env", f"{name}={old_value}\n\n")
        write_one(runtime_path, name, new_value)
        runtime_text = _file_text(ws, "runtime.env", origin="runtime blank-after")
        require_absent_independent_line(
            runtime_text,
            f"{name}={old_value}",
            origin="runtime blank-after",
        )
        _blank_after(
            runtime_text,
            _always_line(name, new_value),
            origin="runtime blank-after",
        )


def test_write_inserts_newline_before_append_when_last_line_has_none():
    with workspace() as ws:
        public_path = ws.write("public.env", "a=b")
        write_one(public_path, "c", "d")
        public_text = _file_text(ws, "public.env", origin="public no-nl append")
        require_independent_line(public_text, "a=b", origin="public no-nl append")
        require_independent_line(public_text, "c='d'", origin="public no-nl append")
        assert "a=b" in public_text.splitlines(), (
            f"public no-nl append lost a=b; lines={public_text.splitlines()!r}"
        )
        assert "c='d'" in public_text.splitlines(), (
            f"public no-nl append did not start the new binding on its own line "
            f"as c='d'; lines={public_text.splitlines()!r}"
        )
        assert "a=bc" not in public_text, (
            f"public no-nl append glued the new binding onto the last line: "
            f"{public_text!r}"
        )

        existing_name, existing_value = unique_token(), unique_token()
        new_name, new_value = unique_token(), unique_token()
        runtime_path = ws.write("runtime.env", f"{existing_name}={existing_value}")
        write_one(runtime_path, new_name, new_value)
        runtime_text = _file_text(ws, "runtime.env", origin="runtime no-nl append")
        require_independent_line(
            runtime_text,
            f"{existing_name}={existing_value}",
            origin="runtime no-nl append",
        )
        require_independent_line(
            runtime_text,
            _always_line(new_name, new_value),
            origin="runtime no-nl append",
        )
        assert f"{existing_name}={existing_value}" in runtime_text.splitlines(), (
            f"runtime no-nl append lost the prior line; "
            f"lines={runtime_text.splitlines()!r}"
        )
        assert _always_line(new_name, new_value) in runtime_text.splitlines(), (
            f"runtime no-nl append did not store the new always-quoted line; "
            f"lines={runtime_text.splitlines()!r}"
        )
        assert f"{existing_value}{new_name}" not in runtime_text, (
            f"runtime no-nl append glued the new binding onto the last line: "
            f"{runtime_text!r}"
        )


# ---------------------------------------------------------------------------
# B. Quote modes always / never / auto (default always); export prefix
# ---------------------------------------------------------------------------


def test_quote_always_wraps_in_single_quotes_and_escapes_interior():
    interior_public = "a=" + "'" + "\\" + "'" + "b" + "\\" + "'" + "'"
    with workspace() as ws:
        created = ws.resolve("created.env")
        write_one(created, "a", "b", quote_mode="always")
        created_text = _file_text(ws, "created.env", origin="always create a=b")
        require_independent_line(created_text, "a='b'", origin="always create a=b")
        assert created_text.endswith("\n"), (
            f"always create stored {created_text!r} without a trailing newline"
        )

        quoted = ws.resolve("quoted.env")
        write_one(quoted, "a", "'b'", quote_mode="always")
        quoted_text = _file_text(ws, "quoted.env", origin="always create 'b'")
        require_independent_line(
            quoted_text, interior_public, origin="always create 'b'"
        )

        alnum_name, alnum_value = unique_token(), unique_token()
        alnum_path = ws.resolve("alnum.env")
        write_one(alnum_path, alnum_name, alnum_value, quote_mode="always")
        alnum_text = _file_text(ws, "alnum.env", origin="always create runtime")
        require_independent_line(
            alnum_text,
            _always_line(alnum_name, alnum_value),
            origin="always create runtime",
        )

        left, right = unique_token(), unique_token()
        interior_value = left + "'" + right
        assert interior_value != "'b'"
        interior_name = unique_token()
        interior_path = ws.resolve("interior.env")
        write_one(interior_path, interior_name, interior_value, quote_mode="always")
        interior_text = _file_text(ws, "interior.env", origin="always create interior")
        require_independent_line(
            interior_text,
            _always_line(interior_name, interior_value),
            origin="always create interior",
        )

        occupied = ws.write("occupied.env", "a=old\nz=keep\n")
        write_one(occupied, "a", "b", quote_mode="always")
        occupied_text = _file_text(ws, "occupied.env", origin="always replace a=b")
        require_independent_line(occupied_text, "a='b'", origin="always replace a=b")
        require_absent_independent_line(
            occupied_text, "a=old", origin="always replace a=b"
        )
        require_independent_line(occupied_text, "z=keep", origin="always replace a=b")

        occ_old, occ_keep_name, occ_keep_val = (
            unique_token(),
            unique_token(),
            unique_token(),
        )
        occ_left, occ_right = unique_token(), unique_token()
        occ_value = occ_left + "'" + occ_right
        occ_name = unique_token()
        occ_path = ws.write(
            "occ-interior.env",
            f"{occ_name}={occ_old}\n{occ_keep_name}={occ_keep_val}\n",
        )
        write_one(occ_path, occ_name, occ_value, quote_mode="always")
        occ_text = _file_text(ws, "occ-interior.env", origin="always replace interior")
        require_independent_line(
            occ_text,
            _always_line(occ_name, occ_value),
            origin="always replace interior",
        )
        require_absent_independent_line(
            occ_text,
            f"{occ_name}={occ_old}",
            origin="always replace interior",
        )
        require_independent_line(
            occ_text,
            f"{occ_keep_name}={occ_keep_val}",
            origin="always replace interior",
        )


def test_quote_never_writes_without_added_quotes():
    with workspace() as ws:
        created = ws.resolve("created.env")
        write_one(created, "a", "x", quote_mode="never")
        created_text = _file_text(ws, "created.env", origin="never create a=x")
        require_independent_line(created_text, "a=x", origin="never create a=x")

        name, value = unique_token(), unique_token()
        runtime = ws.resolve("runtime.env")
        write_one(runtime, name, value, quote_mode="never")
        runtime_text = _file_text(ws, "runtime.env", origin="never create runtime")
        require_independent_line(
            runtime_text, f"{name}={value}", origin="never create runtime"
        )

        always_path = ws.resolve("always.env")
        never_path = ws.resolve("never.env")
        write_one(always_path, "a", "x", quote_mode="always")
        write_one(never_path, "a", "x", quote_mode="never")
        always_text = _file_text(ws, "always.env", origin="never vs always")
        never_text = _file_text(ws, "never.env", origin="never vs always")
        assert always_text != never_text, (
            "always and never stored the same bytes for a=x"
        )

        occupied = ws.write("occupied.env", "a=old\nz=keep\n")
        write_one(occupied, "a", "x", quote_mode="never")
        occupied_text = _file_text(ws, "occupied.env", origin="never replace")
        require_independent_line(occupied_text, "a=x", origin="never replace")
        require_absent_independent_line(occupied_text, "a=old", origin="never replace")
        require_independent_line(occupied_text, "z=keep", origin="never replace")

        occ_name, occ_old, keep_name, keep_val = (
            unique_token(),
            unique_token(),
            unique_token(),
            unique_token(),
        )
        occ_value = unique_token()
        occ_path = ws.write(
            "occ-runtime.env",
            f"{occ_name}={occ_old}\n{keep_name}={keep_val}\n",
        )
        write_one(occ_path, occ_name, occ_value, quote_mode="never")
        occ_text = _file_text(ws, "occ-runtime.env", origin="never replace runtime")
        require_independent_line(
            occ_text, f"{occ_name}={occ_value}", origin="never replace runtime"
        )
        require_absent_independent_line(
            occ_text, f"{occ_name}={occ_old}", origin="never replace runtime"
        )
        require_independent_line(
            occ_text, f"{keep_name}={keep_val}", origin="never replace runtime"
        )


def test_quote_auto_omits_for_alnum_and_quotes_otherwise():
    with workspace() as ws:
        alnum = ws.resolve("alnum.env")
        write_one(alnum, "a", "x", quote_mode="auto")
        alnum_text = _file_text(ws, "alnum.env", origin="auto create x")
        require_independent_line(alnum_text, "a=x", origin="auto create x")

        spaced = ws.resolve("spaced.env")
        write_one(spaced, "a", "x y", quote_mode="auto")
        spaced_text = _file_text(ws, "spaced.env", origin="auto create spaced")
        require_independent_line(spaced_text, "a='x y'", origin="auto create spaced")

        dollar = ws.resolve("dollar.env")
        write_one(dollar, "a", "$", quote_mode="auto")
        dollar_text = _file_text(ws, "dollar.env", origin="auto create dollar")
        require_independent_line(dollar_text, "a='$'", origin="auto create dollar")

        rt_name, rt_value = unique_token(), unique_token()
        rt_alnum = ws.resolve("rt-alnum.env")
        write_one(rt_alnum, rt_name, rt_value, quote_mode="auto")
        rt_alnum_text = _file_text(ws, "rt-alnum.env", origin="auto create runtime alnum")
        require_independent_line(
            rt_alnum_text, f"{rt_name}={rt_value}", origin="auto create runtime alnum"
        )

        under_name = unique_token()
        under_value = unique_token() + "_" + unique_token()
        rt_under = ws.resolve("rt-under.env")
        write_one(rt_under, under_name, under_value, quote_mode="auto")
        rt_under_text = _file_text(ws, "rt-under.env", origin="auto create underscore")
        require_independent_line(
            rt_under_text,
            f"{under_name}='{under_value}'",
            origin="auto create underscore",
        )

        always_path = ws.resolve("pair-always.env")
        never_path = ws.resolve("pair-never.env")
        auto_path = ws.resolve("pair-auto.env")
        write_one(always_path, "a", "x", quote_mode="always")
        write_one(never_path, "a", "x", quote_mode="never")
        write_one(auto_path, "a", "x", quote_mode="auto")
        pair_always = _file_text(ws, "pair-always.env", origin="auto pairwise")
        pair_never = _file_text(ws, "pair-never.env", origin="auto pairwise")
        pair_auto = _file_text(ws, "pair-auto.env", origin="auto pairwise")
        assert pair_always != pair_never, "always and never not distinct for a=x"
        assert pair_always != pair_auto, "always and auto-alnum not distinct for a=x"

        never_space = ws.resolve("never-space.env")
        auto_space = ws.resolve("auto-space.env")
        write_one(never_space, "a", "x y", quote_mode="never")
        write_one(auto_space, "a", "x y", quote_mode="auto")
        assert _file_text(ws, "never-space.env", origin="auto space vs never") != (
            _file_text(ws, "auto-space.env", origin="auto space vs never")
        ), "auto and never stored the same bytes for a spaced value"

        occupied = ws.write("occupied.env", "a=old\nz=keep\n")
        write_one(occupied, "a", "x", quote_mode="auto")
        occupied_text = _file_text(ws, "occupied.env", origin="auto replace x")
        require_independent_line(occupied_text, "a=x", origin="auto replace x")
        require_absent_independent_line(occupied_text, "a=old", origin="auto replace x")
        require_independent_line(occupied_text, "z=keep", origin="auto replace x")

        occ_under = ws.write("occ-under.env", "a=old\nz=keep\n")
        write_one(occ_under, "a", under_value, quote_mode="auto")
        occ_under_text = _file_text(ws, "occ-under.env", origin="auto replace underscore")
        require_independent_line(
            occ_under_text,
            f"a='{under_value}'",
            origin="auto replace underscore",
        )
        require_absent_independent_line(
            occ_under_text, "a=old", origin="auto replace underscore"
        )
        require_independent_line(
            occ_under_text, "z=keep", origin="auto replace underscore"
        )

        occ_name, occ_old, keep_name, keep_val = (
            unique_token(),
            unique_token(),
            unique_token(),
            unique_token(),
        )
        occ_alnum_val = unique_token()
        occ_alnum_path = ws.write(
            "occ-rt-alnum.env",
            f"{occ_name}={occ_old}\n{keep_name}={keep_val}\n",
        )
        write_one(occ_alnum_path, occ_name, occ_alnum_val, quote_mode="auto")
        occ_alnum_text = _file_text(
            ws, "occ-rt-alnum.env", origin="auto replace runtime alnum"
        )
        require_independent_line(
            occ_alnum_text,
            f"{occ_name}={occ_alnum_val}",
            origin="auto replace runtime alnum",
        )
        require_absent_independent_line(
            occ_alnum_text,
            f"{occ_name}={occ_old}",
            origin="auto replace runtime alnum",
        )
        require_independent_line(
            occ_alnum_text,
            f"{keep_name}={keep_val}",
            origin="auto replace runtime alnum",
        )


def test_quote_mode_omitted_is_always():
    with workspace() as ws:
        omitted = ws.resolve("omitted.env")
        named = ws.resolve("named.env")
        write_one(omitted, "a", "b")
        write_one(named, "a", "b", quote_mode="always")
        omitted_text = _file_text(ws, "omitted.env", origin="omitted quote")
        named_text = _file_text(ws, "named.env", origin="named always")
        require_independent_line(omitted_text, "a='b'", origin="omitted quote")
        require_independent_line(named_text, "a='b'", origin="named always")
        assert "a='b'" in omitted_text.splitlines(), (
            f"omitted quote did not store a='b'; lines={omitted_text.splitlines()!r}"
        )
        assert omitted_text == named_text, (
            f"omitted quote stored {omitted_text!r}, "
            f"named always stored {named_text!r}"
        )

        occupied = ws.write("occupied.env", "a=old\nz=keep\n")
        write_one(occupied, "a", "b")
        occupied_text = _file_text(ws, "occupied.env", origin="omitted replace")
        require_independent_line(occupied_text, "a='b'", origin="omitted replace")
        require_absent_independent_line(
            occupied_text, "a=old", origin="omitted replace"
        )
        require_independent_line(occupied_text, "z=keep", origin="omitted replace")
        assert "a='b'" in occupied_text.splitlines(), (
            f"omitted replace did not store a='b'; "
            f"lines={occupied_text.splitlines()!r}"
        )
        assert "a=old" not in occupied_text.splitlines(), (
            f"omitted replace left a=old; lines={occupied_text.splitlines()!r}"
        )
        assert "z=keep" in occupied_text.splitlines(), (
            f"omitted replace dropped sibling z=keep; "
            f"lines={occupied_text.splitlines()!r}"
        )

        name, old, keep_name, keep_val, new = (
            unique_token(),
            unique_token(),
            unique_token(),
            unique_token(),
            unique_token(),
        )
        rt_path = ws.write(
            "rt-occupied.env",
            f"{name}={old}\n{keep_name}={keep_val}\n",
        )
        write_one(rt_path, name, new)
        rt_text = _file_text(ws, "rt-occupied.env", origin="omitted replace runtime")
        require_independent_line(
            rt_text, _always_line(name, new), origin="omitted replace runtime"
        )
        require_absent_independent_line(
            rt_text, f"{name}={old}", origin="omitted replace runtime"
        )
        require_independent_line(
            rt_text, f"{keep_name}={keep_val}", origin="omitted replace runtime"
        )
        assert _always_line(name, new) in rt_text.splitlines(), (
            f"omitted runtime replace did not store the always-quoted line; "
            f"lines={rt_text.splitlines()!r}"
        )
        assert f"{name}={old}" not in rt_text.splitlines(), (
            f"omitted runtime replace left {name}={old}; "
            f"lines={rt_text.splitlines()!r}"
        )
        assert f"{keep_name}={keep_val}" in rt_text.splitlines(), (
            f"omitted runtime replace dropped sibling {keep_name}={keep_val}; "
            f"lines={rt_text.splitlines()!r}"
        )


def test_export_prefixes_stored_line_and_default_has_no_prefix():
    with workspace() as ws:
        on_path = ws.resolve("export-on.env")
        off_path = ws.resolve("export-off.env")
        write_one(on_path, "a", "x", export=True)
        write_one(off_path, "a", "x")
        on_text = _file_text(ws, "export-on.env", origin="export on create")
        off_text = _file_text(ws, "export-off.env", origin="export off create")
        require_independent_line(on_text, "export a='x'", origin="export on create")
        require_independent_line(off_text, "a='x'", origin="export off create")
        assert not any(
            line.startswith("export ") for line in off_text.splitlines()
        ), f"omitted export still stored a prefix: {off_text!r}"
        require_text_value(
            read_one(on_path, "a"), "x", origin="export on later read"
        )

        rt_name, rt_value = unique_token(), unique_token()
        rt_on = ws.resolve("rt-on.env")
        rt_off = ws.resolve("rt-off.env")
        write_one(rt_on, rt_name, rt_value, export=True)
        write_one(rt_off, rt_name, rt_value)
        rt_on_text = _file_text(ws, "rt-on.env", origin="export on runtime")
        rt_off_text = _file_text(ws, "rt-off.env", origin="export off runtime")
        require_independent_line(
            rt_on_text,
            "export " + _always_line(rt_name, rt_value),
            origin="export on runtime",
        )
        require_independent_line(
            rt_off_text,
            _always_line(rt_name, rt_value),
            origin="export off runtime",
        )
        require_text_value(
            read_one(rt_on, rt_name), rt_value, origin="export on runtime read"
        )

        occupied_on = ws.write("occ-on.env", "a=old\nz=keep\n")
        write_one(occupied_on, "a", "x", export=True)
        occ_on_text = _file_text(ws, "occ-on.env", origin="export on replace")
        require_independent_line(
            occ_on_text, "export a='x'", origin="export on replace"
        )
        require_absent_independent_line(occ_on_text, "a=old", origin="export on replace")
        require_independent_line(occ_on_text, "z=keep", origin="export on replace")

        occupied_off = ws.write("occ-off.env", "a=old\nz=keep\n")
        write_one(occupied_off, "a", "x")
        occ_off_text = _file_text(ws, "occ-off.env", origin="export off replace")
        require_independent_line(occ_off_text, "a='x'", origin="export off replace")
        assert not any(
            line.startswith("export ") for line in occ_off_text.splitlines()
        ), f"omitted export replace stored a prefix: {occ_off_text!r}"

        sibling_name, sibling_val, new_name, new_val = (
            unique_token(),
            unique_token(),
            unique_token(),
            unique_token(),
        )
        append_path = ws.write(
            "append-export.env",
            f"{sibling_name}={sibling_val}\n",
        )
        write_one(append_path, new_name, new_val, export=True)
        append_text = _file_text(ws, "append-export.env", origin="export append occupied")
        require_independent_line(
            append_text,
            "export " + _always_line(new_name, new_val),
            origin="export append occupied",
        )
        require_independent_line(
            append_text,
            f"{sibling_name}={sibling_val}",
            origin="export append occupied",
        )


# ---------------------------------------------------------------------------
# C. Read: text value, empty string, no-value line, missing name, missing path
# ---------------------------------------------------------------------------


def test_read_present_text_value():
    with workspace() as ws:
        public = ws.write("public.env", "foo=bar\n")
        assert require_text_value(
            read_one(public, "foo"), "bar", origin="public present"
        ) == "bar"

        name, value = unique_token(), unique_token()
        runtime = ws.write("runtime.env", f"{name}={value}\n")
        assert require_text_value(
            read_one(runtime, name), value, origin="runtime present"
        ) == value


def test_read_empty_string_is_text_not_no_value():
    with workspace() as ws:
        empty = ws.write("empty.env", "foo=\n")
        no_eq = ws.write("no-eq.env", "foo\n")
        public_empty = require_text_value(
            read_one(empty, "foo"), "", origin="public empty string"
        )
        public_no_eq = require_no_text_value(
            read_one(no_eq, "foo"), origin="public no-equals"
        )
        assert public_empty == ""
        assert not isinstance(public_no_eq, str), (
            f"no-equals foo returned text {public_no_eq!r}, not no-value"
        )
        assert public_empty != public_no_eq, (
            "empty-string foo= and no-equals foo are indistinguishable"
        )

        name = unique_token()
        rt_empty = ws.write("rt-empty.env", f"{name}=\n")
        rt_no_eq = ws.write("rt-no-eq.env", f"{name}\n")
        runtime_empty = require_text_value(
            read_one(rt_empty, name), "", origin="runtime empty string"
        )
        runtime_no_eq = require_no_text_value(
            read_one(rt_no_eq, name), origin="runtime no-equals"
        )
        assert runtime_empty == ""
        assert not isinstance(runtime_no_eq, str), (
            f"runtime no-equals returned text {runtime_no_eq!r}, not no-value"
        )
        assert runtime_empty != runtime_no_eq, (
            "runtime empty-string and no-equals reads are indistinguishable"
        )


def test_read_missing_name_returns_no_value_and_identifies_key():
    with workspace() as ws:
        token, value = unique_token(), unique_token()
        occupied = ws.write("occupied.env", f"{token}={value}\n")
        missing_one = unique_token()
        missing_two = unique_token()
        miss1, diag1 = _logged_read(occupied, missing_one)
        miss2 = read_one(occupied, missing_two)
        present, present_diag = _logged_read(occupied, token)
        require_no_text_value(miss1, origin="occupied missing one")
        require_no_text_value(miss2, origin="occupied missing two")
        assert miss1.value != value, (
            f"missing name returned the present value {value!r}"
        )
        require_text_value(present, value, origin="occupied present baseline")
        require_line_naming(diag1, missing_one, origin="missing-name read")
        require_no_line_naming(present_diag, token, origin="present-name read")

        public = ws.write("public.env", "foo=bar\n")
        public_miss, _ = _logged_read(public, "absent")
        require_no_text_value(public_miss, origin="public missing name")
        assert public_miss.value != "bar", (
            "public missing name returned the present value bar"
        )


def test_read_no_value_line_returns_no_value():
    with workspace() as ws:
        no_value_path = ws.write("no-value.env", "foo\n")
        occupied = ws.write("occupied.env", "z=keep\n")
        public_no_value = require_no_text_value(
            read_one(no_value_path, "foo"), origin="public no-value line"
        )
        occupied_missing = require_no_text_value(
            read_one(occupied, "foo"), origin="occupied missing foo"
        )
        assert not isinstance(public_no_value, str), (
            f"no-value line foo returned text {public_no_value!r}"
        )
        assert not isinstance(occupied_missing, str), (
            f"occupied missing foo returned text {occupied_missing!r}"
        )

        name = unique_token()
        rt_no_value = ws.write("rt-no-value.env", f"{name}\n")
        rt_occupied = ws.write(
            "rt-occupied.env", f"{unique_token()}={unique_token()}\n"
        )
        runtime_no_value = require_no_text_value(
            read_one(rt_no_value, name), origin="runtime no-value line"
        )
        runtime_missing = require_no_text_value(
            read_one(rt_occupied, name), origin="runtime occupied missing"
        )
        assert not isinstance(runtime_no_value, str), (
            f"runtime no-value line returned text {runtime_no_value!r}"
        )
        assert not isinstance(runtime_missing, str), (
            f"runtime occupied missing returned text {runtime_missing!r}"
        )


def test_read_missing_path_returns_no_value_and_identifies_file_and_key():
    with workspace() as ws:
        missing_path = ws.resolve("missing.env")
        token, value = unique_token(), unique_token()
        occupied = ws.write("occupied.env", f"{token}={value}\n")
        missing_key = unique_token()

        miss_file, diag_file = _logged_read(missing_path, token)
        exist_miss, diag_exist = _logged_read(occupied, missing_key)
        present, present_diag = _logged_read(occupied, token)
        require_no_text_value(miss_file, origin="missing path")
        require_no_text_value(exist_miss, origin="existing file missing key")
        require_text_value(present, value, origin="present-name baseline")

        require_line_naming(diag_exist, missing_key, origin="existing file missing key")
        require_no_line_naming(
            diag_exist, occupied, without=missing_key, origin="existing file missing key"
        )
        require_line_naming(diag_file, missing_path, without=token, origin="missing path")
        require_line_naming(diag_file, token, origin="missing path")
        require_no_line_naming(present_diag, token, origin="present name")
        require_no_line_naming(present_diag, occupied, origin="present name")


# ---------------------------------------------------------------------------
# D. Delete present binding; refuse missing path and missing name
# ---------------------------------------------------------------------------


def test_delete_present_name_leaves_other_bindings():
    with workspace() as ws:
        public_path = ws.write("public.env", "a=b\nc=d\n")
        first = delete_one(public_path, "a")
        require_call_completed(first, origin="public delete a")
        public_text = _file_text(ws, "public.env", origin="public after delete a")
        require_independent_line(public_text, "c=d", origin="public after delete a")
        require_absent_independent_line(
            public_text, "a=b", origin="public after delete a"
        )
        require_absent_independent_line(
            public_text, "a", origin="public after delete a"
        )
        require_no_text_value(
            read_one(public_path, "a"), origin="public read a after delete"
        )
        require_text_value(read_one(public_path, "c"), "d", origin="public kept c")

        snapshot = ws.read_bytes("public.env")
        second, second_diag = _logged_delete(public_path, "a")
        require_edit_did_not_succeed(
            second, first, origin="public second delete a"
        )
        assert ws.read_bytes("public.env") == snapshot, (
            "second delete of a altered the file"
        )
        assert diagnostic_lines(second_diag), (
            "second delete of a produced no key-was-not-removed diagnostic"
        )

        keep_name, keep_val, gone_name, gone_val = (
            unique_token(),
            unique_token(),
            unique_token(),
            unique_token(),
        )
        runtime_path = ws.write(
            "runtime.env",
            f"{gone_name}={gone_val}\n{keep_name}={keep_val}\n",
        )
        rt_first = delete_one(runtime_path, gone_name)
        require_call_completed(rt_first, origin="runtime delete")
        rt_text = _file_text(ws, "runtime.env", origin="runtime after delete")
        require_independent_line(
            rt_text, f"{keep_name}={keep_val}", origin="runtime after delete"
        )
        require_absent_independent_line(
            rt_text,
            f"{gone_name}={gone_val}",
            origin="runtime after delete",
        )
        require_absent_independent_line(
            rt_text, gone_name, origin="runtime after delete"
        )
        require_no_text_value(
            read_one(runtime_path, gone_name), origin="runtime read after delete"
        )
        require_text_value(
            read_one(runtime_path, keep_name),
            keep_val,
            origin="runtime kept sibling",
        )

        rt_snapshot = ws.read_bytes("runtime.env")
        rt_second, rt_second_diag = _logged_delete(runtime_path, gone_name)
        require_edit_did_not_succeed(
            rt_second, rt_first, origin="runtime second delete"
        )
        assert ws.read_bytes("runtime.env") == rt_snapshot, (
            "runtime second delete altered the file"
        )
        require_line_naming(rt_second_diag, gone_name, origin="runtime second delete")


def test_delete_no_value_line():
    with workspace() as ws:
        public = ws.write("public.env", "foo\n")
        public_del = delete_one(public, "foo")
        require_call_completed(public_del, origin="delete no-value foo")
        public_text = _file_text(ws, "public.env", origin="after delete no-value")
        require_absent_independent_line(public_text, "foo", origin="after delete no-value")
        after_public = require_no_text_value(
            read_one(public, "foo"), origin="read foo after deleting no-value"
        )
        assert "foo" not in public_text.splitlines(), (
            f"delete left the no-value line foo; lines={public_text.splitlines()!r}"
        )
        assert not isinstance(after_public, str), (
            f"read after deleting no-value foo returned text {after_public!r}"
        )

        name = unique_token()
        runtime = ws.write("runtime.env", f"{name}\n")
        runtime_del = delete_one(runtime, name)
        require_call_completed(runtime_del, origin="delete runtime no-value")
        runtime_text = _file_text(ws, "runtime.env", origin="after runtime no-value")
        require_absent_independent_line(
            runtime_text, name, origin="after runtime no-value"
        )
        after_runtime = require_no_text_value(
            read_one(runtime, name), origin="read runtime after deleting no-value"
        )
        assert name not in runtime_text.splitlines(), (
            f"delete left the runtime no-value line {name!r}; "
            f"lines={runtime_text.splitlines()!r}"
        )
        assert not isinstance(after_runtime, str), (
            f"read after deleting runtime no-value returned text {after_runtime!r}"
        )


def test_delete_missing_path_does_not_succeed_or_create():
    with workspace() as ws:
        key = unique_token()
        success = _success_delete(ws, key)
        missing_one = ws.resolve("missing-one.env")
        missing_two = ws.resolve("missing-two.env")
        fail_one, diag_one = _logged_delete(missing_one, key)
        fail_two, diag_two = _logged_delete(missing_two, key)
        require_edit_did_not_succeed(
            fail_one, success, origin="delete missing path one"
        )
        require_edit_did_not_succeed(
            fail_two, success, origin="delete missing path two"
        )
        created_one = True
        try:
            ws.read_bytes("missing-one.env")
        except FileNotFoundError:
            created_one = False
            print("missing-one.env still absent", flush=True)
        assert not created_one, "delete of a missing path created the file"
        created_two = True
        try:
            ws.read_bytes("missing-two.env")
        except FileNotFoundError:
            created_two = False
            print("missing-two.env still absent", flush=True)
        assert not created_two, "delete of a second missing path created the file"
        require_line_naming(diag_one, missing_one, origin="delete missing path one")
        require_line_naming(diag_two, missing_two, origin="delete missing path two")


def test_delete_missing_name_does_not_succeed_or_alter():
    with workspace() as ws:
        keep_name, keep_val = unique_token(), unique_token()
        occupied = ws.write("occupied.env", f"{keep_name}={keep_val}\n")
        original = ws.read_bytes("occupied.env")
        miss_one = unique_token()
        miss_two = unique_token()
        success = _success_delete(ws, miss_one)
        fail_one, diag_one = _logged_delete(occupied, miss_one)
        require_edit_did_not_succeed(
            fail_one, success, origin="delete missing name one"
        )
        assert ws.read_bytes("occupied.env") == original, (
            "delete of a missing name altered the occupied file"
        )
        fail_two, diag_two = _logged_delete(occupied, miss_two)
        success_two = _success_delete(ws, miss_two)
        require_edit_did_not_succeed(
            fail_two, success_two, origin="delete missing name two"
        )
        assert ws.read_bytes("occupied.env") == original, (
            "second missing-name delete altered the occupied file"
        )
        require_line_naming(diag_one, miss_one, origin="delete missing name one")
        require_line_naming(diag_two, miss_two, origin="delete missing name two")

        missing_path = ws.resolve("not-there.env")
        path_fail, path_diag = _logged_delete(missing_path, miss_one)
        require_edit_did_not_succeed(
            path_fail, success, origin="delete missing path contrast"
        )
        require_line_naming(path_diag, missing_path, origin="delete missing path contrast")
        require_no_line_naming(path_diag, miss_one, origin="delete missing path contrast")


# ---------------------------------------------------------------------------
# E. Symbolic links: default does not follow; follow updates the target
# ---------------------------------------------------------------------------


def test_default_write_replaces_symlink_and_leaves_target():
    with workspace() as ws:
        target = ws.write("target.env", "a=x\n")
        env_path = ws.symlink(".env", "target.env")
        write_one(env_path, "a", "y")
        target_text = _file_text(ws, "target.env", origin="default write target")
        require_independent_line(target_text, "a=x", origin="default write target")
        assert path_is_file(env_path), f"{env_path} is not a regular file"
        assert not path_is_symlink(env_path), f"{env_path} is still a symlink"
        env_text = _file_text(ws, ".env", origin="default write new file")
        require_independent_line(env_text, "a='y'", origin="default write new file")
        require_text_value(read_one(env_path, "a"), "y", origin="default write read")
        require_owner_rw_only(env_path)

        rt_name, rt_old, rt_new = unique_token(), unique_token(), unique_token()
        rt_target = ws.write("rt-target.env", f"{rt_name}={rt_old}\n")
        rt_env = ws.symlink("rt.env", "rt-target.env")
        write_one(rt_env, rt_name, rt_new)
        rt_target_text = _file_text(ws, "rt-target.env", origin="runtime default write")
        require_independent_line(
            rt_target_text, f"{rt_name}={rt_old}", origin="runtime default write"
        )
        assert path_is_file(rt_env), f"{rt_env} is not a regular file"
        rt_env_text = _file_text(ws, "rt.env", origin="runtime default write new")
        require_independent_line(
            rt_env_text,
            _always_line(rt_name, rt_new),
            origin="runtime default write new",
        )
        require_text_value(
            read_one(rt_env, rt_name), rt_new, origin="runtime default write read"
        )
        require_owner_rw_only(rt_env)
        print(f"left target={target} runtime_target={rt_target}", flush=True)


def test_default_write_dangling_symlink_creates_regular_file_not_target():
    with workspace() as ws:
        env_path = ws.symlink(".env", "missing-target.env")
        write_one(env_path, "a", "y")
        dangling_created = True
        try:
            ws.read_bytes("missing-target.env")
        except FileNotFoundError:
            dangling_created = False
            print("dangling write did not create the missing target", flush=True)
        assert not dangling_created, "dangling write created the missing target"
        assert path_is_file(env_path), f"{env_path} is not a regular file"
        assert not path_is_symlink(env_path), f"{env_path} is still a symlink"
        env_text = _file_text(ws, ".env", origin="dangling write new file")
        require_independent_line(env_text, "a='y'", origin="dangling write new file")
        require_owner_rw_only(env_path)

        rt_name, rt_value = unique_token(), unique_token()
        rt_env = ws.symlink("rt.env", "rt-missing-target.env")
        write_one(rt_env, rt_name, rt_value)
        rt_created = True
        try:
            ws.read_bytes("rt-missing-target.env")
        except FileNotFoundError:
            rt_created = False
            print("runtime dangling write did not create the target", flush=True)
        assert not rt_created, "runtime dangling write created the missing target"
        assert path_is_file(rt_env), f"{rt_env} is not a regular file"
        require_owner_rw_only(rt_env)


def test_default_delete_replaces_symlink_and_leaves_target():
    with workspace() as ws:
        target = ws.write("target.env", "a=x\n")
        env_path = ws.symlink(".env", "target.env")
        delete_one(env_path, "a")
        target_text = _file_text(ws, "target.env", origin="default delete target")
        require_independent_line(target_text, "a=x", origin="default delete target")
        assert path_is_file(env_path), f"{env_path} is not a regular file"
        assert not path_is_symlink(env_path), f"{env_path} is still a symlink"
        require_no_text_value(
            read_one(env_path, "a"), origin="default delete read a"
        )
        require_owner_rw_only(env_path)
        print(f"left target={target}", flush=True)

        rt_name, rt_value = unique_token(), unique_token()
        ws.write("rt-target.env", f"{rt_name}={rt_value}\n")
        rt_env = ws.symlink("rt.env", "rt-target.env")
        delete_one(rt_env, rt_name)
        rt_target_text = _file_text(ws, "rt-target.env", origin="runtime default delete")
        require_independent_line(
            rt_target_text, f"{rt_name}={rt_value}", origin="runtime default delete"
        )
        assert path_is_file(rt_env), f"{rt_env} is not a regular file"
        require_no_text_value(
            read_one(rt_env, rt_name), origin="runtime default delete read"
        )
        require_owner_rw_only(rt_env)


def test_default_delete_dangling_symlink_does_not_succeed():
    with workspace() as ws:
        success = _success_delete(ws, "a")
        env_path = ws.symlink(".env", "missing-target.env")
        fail = delete_one(env_path, "a")
        require_edit_did_not_succeed(
            fail, success, origin="dangling delete"
        )
        assert path_is_symlink(env_path), (
            f"{env_path} is no longer a symlink after dangling delete"
        )

        rt_name = unique_token()
        rt_success = _success_delete(ws, rt_name)
        rt_env = ws.symlink("rt.env", "rt-missing-target.env")
        rt_fail = delete_one(rt_env, rt_name)
        require_edit_did_not_succeed(
            rt_fail, rt_success, origin="runtime dangling delete"
        )
        assert path_is_symlink(rt_env), (
            f"{rt_env} is no longer a symlink after runtime dangling delete"
        )


def test_follow_links_write_updates_target_keeps_symlink():
    with workspace() as ws:
        sibling_name, sibling_val = unique_token(), unique_token()
        target = ws.write("target.env", f"a=x\n{sibling_name}={sibling_val}\n")
        preserved = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP
        ws.chmod("target.env", preserved)
        env_path = ws.symlink(".env", "target.env")
        write_one(env_path, "a", "y", follow_symlinks=True)
        assert path_is_symlink(env_path), f"{env_path} is no longer a symlink"
        target_text = _file_text(ws, "target.env", origin="follow write target")
        require_independent_line(target_text, "a='y'", origin="follow write target")
        require_independent_line(
            target_text,
            f"{sibling_name}={sibling_val}",
            origin="follow write sibling line",
        )
        require_text_value(
            read_one(target, sibling_name),
            sibling_val,
            origin="follow write sibling read",
        )
        assert file_mode(target) == preserved, (
            f"follow write changed target mode to {file_mode(target):o}"
        )

        rt_name, rt_old, rt_new = unique_token(), unique_token(), unique_token()
        rt_sib, rt_sib_val = unique_token(), unique_token()
        rt_target = ws.write(
            "rt-target.env",
            f"{rt_name}={rt_old}\n{rt_sib}={rt_sib_val}\n",
        )
        rt_env = ws.symlink("rt.env", "rt-target.env")
        write_one(rt_env, rt_name, rt_new, follow_symlinks=True)
        assert path_is_symlink(rt_env), f"{rt_env} is no longer a symlink"
        rt_text = _file_text(ws, "rt-target.env", origin="follow write runtime")
        require_independent_line(
            rt_text, _always_line(rt_name, rt_new), origin="follow write runtime"
        )
        require_text_value(
            read_one(rt_target, rt_sib),
            rt_sib_val,
            origin="follow write runtime sibling",
        )


def test_follow_links_delete_updates_target_keeps_symlink():
    with workspace() as ws:
        sibling_name, sibling_val = unique_token(), unique_token()
        target = ws.write("target.env", f"a=x\n{sibling_name}={sibling_val}\n")
        env_path = ws.symlink(".env", "target.env")
        delete_one(env_path, "a", follow_symlinks=True)
        assert path_is_symlink(env_path), f"{env_path} is no longer a symlink"
        require_no_text_value(read_one(target, "a"), origin="follow delete a")
        require_text_value(
            read_one(target, sibling_name),
            sibling_val,
            origin="follow delete sibling",
        )
        target_text = _file_text(ws, "target.env", origin="follow delete target")
        require_independent_line(
            target_text,
            f"{sibling_name}={sibling_val}",
            origin="follow delete sibling line",
        )

        rt_name, rt_val = unique_token(), unique_token()
        rt_sib, rt_sib_val = unique_token(), unique_token()
        rt_target = ws.write(
            "rt-target.env",
            f"{rt_name}={rt_val}\n{rt_sib}={rt_sib_val}\n",
        )
        rt_env = ws.symlink("rt.env", "rt-target.env")
        delete_one(rt_env, rt_name, follow_symlinks=True)
        assert path_is_symlink(rt_env), f"{rt_env} is no longer a symlink"
        require_no_text_value(
            read_one(rt_target, rt_name), origin="follow delete runtime"
        )
        require_text_value(
            read_one(rt_target, rt_sib),
            rt_sib_val,
            origin="follow delete runtime sibling",
        )


# ---------------------------------------------------------------------------
# F. Unix permissions; named encoding; unknown quote; unwritable file
# ---------------------------------------------------------------------------


def test_rewrite_preserves_unix_regular_file_permission_bits():
    with workspace() as ws:
        group_read = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP
        path = ws.write("keep.env", "a=b\n")
        ws.chmod("keep.env", group_read)
        before_keep = ws.read_bytes("keep.env")
        write_one(path, "a", "e")
        after_keep = ws.read_bytes("keep.env")
        print(
            f"group-read rewrite before={before_keep!r} after={after_keep!r}",
            flush=True,
        )
        assert after_keep != before_keep, (
            "rewrite left the occupied group-read file untouched"
        )
        require_text_value(
            read_one(path, "a"),
            "e",
            origin="rewrite group-read later read",
        )
        assert file_mode(path) == group_read, (
            f"rewrite changed mode to {file_mode(path):o}, expected {group_read:o}"
        )

        group_write = stat.S_IRUSR | stat.S_IWUSR | stat.S_IWGRP
        other_name, other_old, other_new = (
            unique_token(),
            unique_token(),
            unique_token(),
        )
        other = ws.write("other.env", f"{other_name}={other_old}\n")
        ws.chmod("other.env", group_write)
        before_other = ws.read_bytes("other.env")
        write_one(other, other_name, other_new)
        after_other = ws.read_bytes("other.env")
        print(
            f"group-write rewrite before={before_other!r} after={after_other!r}",
            flush=True,
        )
        assert after_other != before_other, (
            "rewrite left the occupied group-write file untouched"
        )
        require_text_value(
            read_one(other, other_name),
            other_new,
            origin="rewrite group-write later read",
        )
        assert file_mode(other) == group_write, (
            f"rewrite of a second mode changed it to {file_mode(other):o}"
        )


def test_new_regular_file_is_owner_read_write_only():
    owner_rw = stat.S_IRUSR | stat.S_IWUSR
    with workspace() as ws:
        path = ws.resolve("new.env")
        write_one(path, "foo", "bar")
        public_mode = require_owner_rw_only(path)
        assert public_mode == owner_rw, (
            f"{path} mode is {public_mode:o}, not owner-read/write only "
            f"({owner_rw:o})"
        )

        rt_path = ws.resolve("rt-new.env")
        write_one(rt_path, unique_token(), unique_token())
        runtime_mode = require_owner_rw_only(rt_path)
        assert runtime_mode == owner_rw, (
            f"{rt_path} mode is {runtime_mode:o}, not owner-read/write only "
            f"({owner_rw:o})"
        )


def test_named_latin1_write_and_read():
    with workspace() as ws:
        written = ws.resolve("write-lat.env")
        write_one(written, "a", "é", encoding="latin-1")
        lat_text = ws.read("write-lat.env", encoding="latin-1")
        print(f"latin-1 stored text={lat_text!r}", flush=True)
        assert "é" in lat_text, f"latin-1 write did not store é: {lat_text!r}"
        require_text_value(
            read_one(written, "a", encoding="latin-1"),
            "é",
            origin="latin-1 write then read",
        )

        utf_path = ws.resolve("write-utf.env")
        write_one(utf_path, "a", "é", encoding="utf-8")
        assert ws.read_bytes("write-lat.env") != ws.read_bytes("write-utf.env"), (
            "latin-1 and utf-8 writes of é stored the same bytes"
        )

        public = ws.write("public.env", "é=è\n", encoding="latin-1")
        require_text_value(
            read_one(public, "é", encoding="latin-1"),
            "è",
            origin="latin-1 public read",
        )
        utf_read = read_one(public, "é", encoding="utf-8")
        latin_read = read_one(public, "é", encoding="latin-1")
        require_text_value(latin_read, "è", origin="latin-1 contrast")
        if utf_read.exception is not None:
            print(f"utf-8 read aborted {utf_read.exception!r}", flush=True)
        else:
            print(f"utf-8 read completed value={utf_read.value!r}", flush=True)
        assert utf_read.exception is not None or utf_read.value != latin_read.value, (
            "utf-8 and latin-1 reads of the same latin-1 bytes are indistinguishable"
        )


def test_unknown_quote_mode_refused_without_writing():
    with workspace() as ws:
        occupied_valid = ws.write("occupied-valid.env", "a=b\n")
        before_valid = ws.read_bytes("occupied-valid.env")
        success = write_one(occupied_valid, "a", "z", quote_mode="always")
        require_call_completed(success, origin="valid quote occupied write")
        after_valid = ws.read_bytes("occupied-valid.env")
        print(
            f"valid occupied before={before_valid!r} after={after_valid!r}",
            flush=True,
        )
        assert after_valid != before_valid, (
            "valid quote mode did not write the occupied file"
        )

        occupied = ws.write("occupied.env", "a=b\n")
        original = ws.read_bytes("occupied.env")
        public = write_one(occupied, "a", "z", quote_mode="sometimes")
        require_edit_did_not_succeed(
            public, success, origin="unknown quote public"
        )
        assert ws.read_bytes("occupied.env") == original, (
            "unknown quote mode wrote the occupied file"
        )

        missing_valid = ws.resolve("created.env")
        success_missing = write_one(missing_valid, "a", "z", quote_mode="always")
        require_call_completed(success_missing, origin="valid quote missing write")
        created_bytes = ws.read_bytes("created.env")
        print(f"valid missing created bytes={created_bytes!r}", flush=True)

        missing = ws.resolve("missing.env")
        runtime_mode = unique_token()
        runtime = write_one(missing, "a", "z", quote_mode=runtime_mode)
        require_edit_did_not_succeed(
            runtime, success_missing, origin="unknown quote runtime"
        )
        created = True
        try:
            ws.read_bytes("missing.env")
        except FileNotFoundError:
            created = False
            print("unknown quote did not create the missing path", flush=True)
        assert not created, "unknown quote mode created the missing path"

