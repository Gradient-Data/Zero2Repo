# feature: F03
"""FP-03: load `.env` values into the process environment.

Assertions stay at the PRD's precision: write recognized values; default
do-not-override versus explicit override; no-value versus empty string;
path / stream / no-arg locate / FIFO source selection; success versus
failure reports; extra-reporting missing-file diagnostic; disable-switch
truthy spellings; caller-named encoding; expansion on by default versus
off leaving dollar-brace text literal. Return booleans, exception
types, and logger names are not pinned; the missing-file diagnostic is
read as the line that names the path (Interface Contract).
"""

from __future__ import annotations

from collections.abc import Mapping
from io import StringIO

from envfile import envfile_values, load_envfile

from _harness import call, product_package_name, workspace
from _helpers import (
    bindings_from_file,
    diagnostics_text,
    environ_value,
    load_reports_differ,
    load_with_log_capture,
    read_tracking_stream,
    require_binding,
    require_call_completed,
    require_environ_absent,
    require_labeled_line,
    require_script_success,
    require_line_naming,
    require_no_line_naming,
    unique_token,
)

DISABLE_SWITCH = "PYTHON_ENVFILE_DISABLED"
TRUTHY_SPELLINGS = (
    "1",
    "true",
    "t",
    "yes",
    "y",
    "TRUE",
    "True",
    "Yes",
    "Y",
    "T",
)
NON_TRUTHY_SPELLINGS = (
    "",
    "0",
    "false",
    "no",
    "f",
    "n",
)


def _empty_file_load(**kwargs):
    with workspace() as ws:
        path = ws.write("empty.env", "")
        return call(load_envfile, envfile_path=str(path), **kwargs)


def _empty_stream_load(**kwargs):
    return call(load_envfile, stream=StringIO(""), **kwargs)


def _no_arg_load_source(pkg: str, name: str, runtime_name: str) -> str:
    return (
        f"from {pkg} import load_envfile\n"
        "import os\n"
        "load_envfile()\n"
        f"print('HAS=' + ('1' if {name!r} in os.environ else '0'))\n"
        f"print('ENV=' + (os.environ[{name!r}] if {name!r} in os.environ else ''))\n"
        f"print('RT_HAS=' + ('1' if {runtime_name!r} in os.environ else '0'))\n"
        f"print('RT=' + (os.environ[{runtime_name!r}] if {runtime_name!r} in os.environ else ''))\n"
    )


def _no_arg_has_source(pkg: str, name: str) -> str:
    return (
        f"from {pkg} import load_envfile\n"
        "import os\n"
        "load_envfile()\n"
        f"print('HAS=' + ('1' if {name!r} in os.environ else '0'))\n"
        f"print('ENV=' + (os.environ[{name!r}] if {name!r} in os.environ else ''))\n"
    )


def _require_locatable_writes(ws, pkg: str, name: str, value: str, *, label: str) -> None:
    baseline = ws.run_script(
        _no_arg_has_source(pkg, name),
        relpath="baseline.py",
        cwd=ws.path,
    )
    stdout = require_script_success(baseline, label=label)
    has = require_labeled_line(stdout, "HAS", origin=label)
    recorded = require_labeled_line(stdout, "ENV", origin=label)
    assert has == "1", f"no-arg load did not write locatable {name!r}"
    assert recorded == value


# ---------------------------------------------------------------------------
# A. Write into the process environment; default no-override; explicit override
# ---------------------------------------------------------------------------


def test_file_a_equals_b_writes_and_reports_success():
    with workspace() as ws:
        path = ws.write("public.env", "a=b\n")
        success = call(load_envfile, envfile_path=str(path))
        failure = _empty_file_load()
    print("file a=b in empty process environment", flush=True)
    require_call_completed(success, origin="file a=b")
    assert environ_value(success, "a") == "b"
    load_reports_differ(success, failure, origin="file a=b")


class TestAbsentRuntimeBinding:
    def test_runtime_binding_written_when_absent(self):
        name, value = unique_token(), unique_token()
        stream_only = unique_token()
        with workspace() as ws:
            path = ws.write("runtime.env", f"{name}={value}\n")
            success = call(
                load_envfile,
                envfile_path=str(path),
                stream=StringIO(
                    f"{name}={unique_token()}\n{stream_only}={unique_token()}\n"
                ),
            )
            failure = _empty_file_load()
        print(f"runtime file {name}={value}", flush=True)
        require_call_completed(success, origin="runtime file")
        assert environ_value(success, name) == value
        require_environ_absent(success, stream_only)
        load_reports_differ(success, failure, origin="runtime file")


def test_default_does_not_override_existing():
    name, old, new = unique_token(), unique_token(), unique_token()
    with workspace() as ws:
        public_path = ws.write("public.env", "a=b\n")
        runtime_path = ws.write("runtime.env", f"{name}={new}\n")
        public = call(load_envfile, envfile_path=str(public_path), env={"a": "c"})
        runtime = call(
            load_envfile, envfile_path=str(runtime_path), env={name: old}
        )
        failure = _empty_file_load(env={"a": "c"})
    print("default omit override: a=c vs file a=b; runtime OLD vs NEW", flush=True)
    require_call_completed(public, origin="default no-override public")
    assert environ_value(public, "a") == "c"
    require_call_completed(runtime, origin="default no-override runtime")
    assert environ_value(runtime, name) == old
    load_reports_differ(public, failure, origin="default no-override")


def test_override_replaces_existing():
    name, old, new = unique_token(), unique_token(), unique_token()
    with workspace() as ws:
        public_path = ws.write("public.env", "a=b\n")
        runtime_path = ws.write("runtime.env", f"{name}={new}\n")
        public = call(
            load_envfile,
            envfile_path=str(public_path),
            env={"a": "c"},
            override=True,
        )
        runtime = call(
            load_envfile,
            envfile_path=str(runtime_path),
            env={name: old},
            override=True,
        )
    print("override on: a=c vs file a=b; runtime OLD vs NEW", flush=True)
    require_call_completed(public, origin="override public")
    assert environ_value(public, "a") == "b"
    require_call_completed(runtime, origin="override runtime")
    assert environ_value(runtime, name) == new


def test_override_is_per_name_new_names_still_written():
    existing, old, new = unique_token(), unique_token(), unique_token()
    fresh, token = unique_token(), unique_token()
    source = f"{existing}={new}\n{fresh}={token}\n"
    with workspace() as ws:
        path = ws.write("per-name.env", source)
        off = call(
            load_envfile,
            envfile_path=str(path),
            env={existing: old},
        )
        on = call(
            load_envfile,
            envfile_path=str(path),
            env={existing: old},
            override=True,
        )
        failure = _empty_file_load(env={existing: old})
    print(
        f"per-name override existing={existing!r} fresh={fresh!r}",
        flush=True,
    )
    require_call_completed(off, origin="per-name override off")
    assert environ_value(off, existing) == old
    assert environ_value(off, fresh) == token
    load_reports_differ(off, failure, origin="per-name override off")
    require_call_completed(on, origin="per-name override on")
    assert environ_value(on, existing) == new
    assert environ_value(on, fresh) == token


# ---------------------------------------------------------------------------
# B. No-value line is not written; empty string is written as ""
# ---------------------------------------------------------------------------


def test_no_value_line_not_written_but_reports_success():
    with workspace() as ws:
        path = ws.write("novalue.env", "FOO\n")
        success = call(load_envfile, envfile_path=str(path))
        failure = _empty_file_load()
    print("no-value line FOO", flush=True)
    require_environ_absent(success, "FOO")
    load_reports_differ(success, failure, origin="no-value FOO")
    assert "FOO" not in success.environ, (
        f"no-value FOO was written {success.environ.get('FOO')!r}; "
        f"keys={sorted(success.environ)!r}"
    )
    assert success.value != failure.value, (
        f"no-value FOO success and empty-file failure are indistinguishable: "
        f"{success.value!r}"
    )


def test_empty_string_line_written_as_empty():
    with workspace() as ws:
        path = ws.write("empty-string.env", "FOO=\n")
        success = call(load_envfile, envfile_path=str(path))
        failure = _empty_file_load()
    print("empty-string line FOO=", flush=True)
    require_call_completed(success, origin="FOO=")
    assert environ_value(success, "FOO") == ""
    load_reports_differ(success, failure, origin="FOO=")


def test_runtime_no_value_vs_empty_vs_absent():
    name = unique_token()
    with workspace() as ws:
        no_value = call(
            load_envfile,
            envfile_path=str(ws.write("nv.env", f"{name}\n")),
        )
        empty = call(
            load_envfile,
            envfile_path=str(ws.write("es.env", f"{name}=\n")),
        )
        absent = call(
            load_envfile,
            envfile_path=str(ws.write("other.env", f"{unique_token()}={unique_token()}\n")),
        )
        failure = _empty_file_load()
    print(f"runtime three-way name={name!r}", flush=True)
    require_environ_absent(no_value, name)
    require_call_completed(empty, origin="runtime empty-string")
    assert environ_value(empty, name) == ""
    require_environ_absent(absent, name)
    load_reports_differ(no_value, failure, origin="runtime no-value success")
    load_reports_differ(empty, failure, origin="runtime empty-string success")


# ---------------------------------------------------------------------------
# C. Path, stream, no-arg locate, path preferred over stream, Unix FIFO
# ---------------------------------------------------------------------------


def test_stream_user_and_email():
    fromfile, fromfile_val = unique_token(), unique_token()
    pkg = product_package_name()
    with workspace() as ws:
        ws.write(".env", f"{fromfile}={fromfile_val}\n")
        _require_locatable_writes(
            ws, pkg, fromfile, fromfile_val, label="stream-user-email-baseline"
        )
        success = call(
            load_envfile,
            stream=StringIO("USER=foo\nEMAIL=foo@example.org\n"),
            cwd=str(ws.path),
            isolate=False,
            env={k: v for k, v in ws.env.items() if k not in ("USER", "EMAIL")},
        )
        failure = _empty_stream_load(env={"USER": None, "EMAIL": None})
    print("stream USER=foo EMAIL=foo@example.org", flush=True)
    require_call_completed(success, origin="stream USER/EMAIL")
    assert environ_value(success, "USER") == "foo"
    assert environ_value(success, "EMAIL") == "foo@example.org"
    require_environ_absent(success, fromfile)
    load_reports_differ(success, failure, origin="stream USER/EMAIL")


def test_stream_a_with_grave_a():
    fromfile, fromfile_val = unique_token(), unique_token()
    pkg = product_package_name()
    with workspace() as ws:
        ws.write(".env", f"{fromfile}={fromfile_val}\n")
        _require_locatable_writes(
            ws, pkg, fromfile, fromfile_val, label="stream-grave-a-baseline"
        )
        success = call(
            load_envfile,
            stream=StringIO("a=à\n"),
            cwd=str(ws.path),
            isolate=False,
            env=ws.env,
        )
        failure = _empty_stream_load()
    print("stream a=à", flush=True)
    require_call_completed(success, origin="stream a=à")
    assert environ_value(success, "a") == "à"
    require_environ_absent(success, fromfile)
    load_reports_differ(success, failure, origin="stream a=à")


def test_runtime_stream_bindings():
    n1, v1 = unique_token(), unique_token()
    n2, v2 = unique_token(), unique_token()
    n3, v3 = unique_token(), "\u2603" + unique_token()
    fromfile, fromfile_val = unique_token(), unique_token()
    pkg = product_package_name()
    text = f"{n1}={v1}\n{n2}={v2}\n{n3}={v3}\n"
    with workspace() as ws:
        ws.write(".env", f"{fromfile}={fromfile_val}\n")
        _require_locatable_writes(
            ws, pkg, fromfile, fromfile_val, label="runtime-stream-baseline"
        )
        success = call(
            load_envfile,
            stream=StringIO(text),
            cwd=str(ws.path),
            isolate=False,
            env=ws.env,
        )
        failure = _empty_stream_load()
    print(f"runtime stream {n1},{n2},{n3}", flush=True)
    require_call_completed(success, origin="runtime stream")
    assert environ_value(success, n1) == v1
    assert environ_value(success, n2) == v2
    assert environ_value(success, n3) == v3
    require_environ_absent(success, fromfile)
    load_reports_differ(success, failure, origin="runtime stream")


def test_readable_path_preferred_over_stream():
    other = unique_token()
    runtime_file, runtime_file_val = unique_token(), unique_token()
    runtime_stream, runtime_stream_val = unique_token(), unique_token()
    with workspace() as ws:
        path = ws.write(
            "fromfile.env",
            f"TOKEN=fromfile\n{runtime_file}={runtime_file_val}\n",
        )
        stream = StringIO(
            f"TOKEN=fromstream\nOTHER=fromstream\n"
            f"{other}=fromstream\n{runtime_stream}={runtime_stream_val}\n"
        )
        result = call(
            load_envfile,
            envfile_path=str(path),
            stream=stream,
        )
        failure = _empty_file_load()
    print("readable path preferred over stream", flush=True)
    require_call_completed(result, origin="path over stream")
    assert environ_value(result, "TOKEN") == "fromfile"
    require_environ_absent(result, "OTHER")
    require_environ_absent(result, other)
    require_environ_absent(result, runtime_stream)
    assert environ_value(result, runtime_file) == runtime_file_val
    load_reports_differ(result, failure, origin="path over stream")


def test_readable_fifo_preferred_over_stream():
    name, fifo_val, stream_val = unique_token(), unique_token(), unique_token()
    stream_only = unique_token()
    with workspace() as ws:
        with ws.fifo("pipe.env", f"{name}={fifo_val}\n") as fifo:
            result = call(
                load_envfile,
                envfile_path=str(fifo),
                stream=StringIO(
                    f"{name}={stream_val}\n{stream_only}={unique_token()}\n"
                ),
            )
    print(f"FIFO preferred over stream name={name!r}", flush=True)
    require_call_completed(result, origin="fifo over stream")
    assert environ_value(result, name) == fifo_val
    require_environ_absent(result, stream_only)


def test_empty_readable_file_does_not_fall_through_to_stream():
    fromstream, value = unique_token(), unique_token()
    with workspace() as ws:
        empty = ws.write("empty.env", "")
        result = call(
            load_envfile,
            envfile_path=str(empty),
            stream=StringIO(f"{fromstream}={value}\n"),
        )
        failure = _empty_file_load()
    print(f"empty file must not read stream {fromstream!r}", flush=True)
    require_environ_absent(result, fromstream)
    require_call_completed(result, origin="empty file + stream")
    stream_success = call(
        load_envfile, stream=StringIO(f"{fromstream}={value}\n")
    )
    load_reports_differ(
        stream_success,
        result,
        origin="empty selected source is failure",
    )
    load_reports_differ(
        stream_success,
        failure,
        origin="empty file failure baseline",
    )
    assert fromstream not in result.environ, (
        f"empty readable file fell through to the stream; "
        f"{fromstream!r}={result.environ.get(fromstream)!r}"
    )
    assert result.value != stream_success.value, (
        f"empty file + stream report {result.value!r} is not distinguishable "
        f"from loading that stream ({stream_success.value!r})"
    )


def test_missing_path_falls_back_to_stream():
    name, value = unique_token(), unique_token()
    with workspace() as ws:
        missing = ws.resolve(f"{unique_token()}.env")
        result = call(
            load_envfile,
            envfile_path=str(missing),
            stream=StringIO(f"{name}={value}\n"),
        )
        failure = _empty_stream_load()
    print(f"missing path falls back to stream {name!r}", flush=True)
    require_call_completed(result, origin="missing path + stream")
    assert environ_value(result, name) == value
    load_reports_differ(result, failure, origin="missing path + stream")


def test_directory_path_falls_back_to_stream():
    name, value = unique_token(), unique_token()
    with workspace() as ws:
        directory = ws.mkdir(unique_token())
        result = call(
            load_envfile,
            envfile_path=str(directory),
            stream=StringIO(f"{name}={value}\n"),
        )
        failure = _empty_stream_load()
    print(f"directory path falls back to stream {name!r}", flush=True)
    require_call_completed(result, origin="directory path + stream")
    assert environ_value(result, name) == value
    load_reports_differ(result, failure, origin="directory path + stream")


def test_stream_outranks_locatable_env():
    fromfile, fromfile_val = unique_token(), unique_token()
    fromstream, fromstream_val = unique_token(), unique_token()
    pkg = product_package_name()
    with workspace() as ws:
        ws.write(".env", f"{fromfile}={fromfile_val}\n")
        baseline = ws.run_script(
            _no_arg_has_source(pkg, fromfile),
            relpath="baseline.py",
            cwd=ws.path,
        )
        stdout = require_script_success(baseline, label="locate-baseline")
        has = require_labeled_line(stdout, "HAS", origin="locate-baseline")
        env = require_labeled_line(stdout, "ENV", origin="locate-baseline")
        assert has == "1", f"no-arg load did not write locatable {fromfile!r}"
        assert env == fromfile_val

        result = call(
            load_envfile,
            stream=StringIO(f"{fromstream}={fromstream_val}\n"),
            cwd=str(ws.path),
            isolate=False,
            env=ws.env,
        )
        failure = call(
            load_envfile,
            stream=StringIO(""),
            cwd=str(ws.path),
            isolate=False,
            env=ws.env,
        )
    print(
        f"stream {fromstream!r} outranks locatable {fromfile!r}",
        flush=True,
    )
    require_call_completed(result, origin="stream vs locate")
    assert environ_value(result, fromstream) == fromstream_val
    require_environ_absent(result, fromfile)
    load_reports_differ(result, failure, origin="stream vs locate")


def test_empty_stream_does_not_locate():
    fromfile, fromfile_val = unique_token(), unique_token()
    pkg = product_package_name()
    with workspace() as ws:
        ws.write(".env", f"{fromfile}={fromfile_val}\n")
        baseline = ws.run_script(
            _no_arg_has_source(pkg, fromfile),
            relpath="baseline.py",
            cwd=ws.path,
        )
        stdout = require_script_success(baseline, label="empty-stream-baseline")
        has = require_labeled_line(stdout, "HAS", origin="empty-stream-baseline")
        assert has == "1", f"no-arg load did not write locatable {fromfile!r}"

        result = call(
            load_envfile,
            stream=StringIO(""),
            cwd=str(ws.path),
            isolate=False,
            env=ws.env,
        )
        success = call(
            load_envfile,
            stream=StringIO(f"{unique_token()}={unique_token()}\n"),
            cwd=str(ws.path),
            isolate=False,
            env=ws.env,
        )
    print(f"empty stream must not locate {fromfile!r}", flush=True)
    require_environ_absent(result, fromfile)
    load_reports_differ(success, result, origin="empty stream does not locate")


def test_no_arg_load_adjacent_script_writes_env():
    pkg = product_package_name()
    name, value = unique_token(), unique_token()
    with workspace() as ws:
        folder = unique_token()
        ws.write(f"{folder}/.env", f"a=b\n{name}={value}\n")
        work = ws.resolve(folder)
        result = ws.run_script(
            _no_arg_load_source(pkg, "a", name),
            relpath=f"{folder}/caller.py",
            cwd=work,
        )
        stdout = require_script_success(result, label="no-arg-adjacent")
        has = require_labeled_line(stdout, "HAS", origin="no-arg-adjacent")
        env = require_labeled_line(stdout, "ENV", origin="no-arg-adjacent")
        rt_has = require_labeled_line(stdout, "RT_HAS", origin="no-arg-adjacent")
        rt = require_labeled_line(stdout, "RT", origin="no-arg-adjacent")
    print("no-arg load adjacent script a=b + runtime", flush=True)
    assert has == "1"
    assert env == "b"
    assert rt_has == "1"
    assert rt == value


def test_fifo_my_password_pipe_secret():
    with workspace() as ws:
        with ws.fifo("pipe.env", "MY_PASSWORD=pipe-secret") as fifo:
            result = call(load_envfile, envfile_path=str(fifo))
    print("FIFO MY_PASSWORD=pipe-secret", flush=True)
    require_call_completed(result, origin="fifo public")
    assert environ_value(result, "MY_PASSWORD") == "pipe-secret"


def test_runtime_fifo_load():
    name, value = unique_token(), unique_token()
    with workspace() as ws:
        with ws.fifo("runtime.fifo", f"{name}={value}\n") as fifo:
            result = call(load_envfile, envfile_path=str(fifo))
        failure = _empty_file_load()
    print(f"runtime FIFO {name}={value}", flush=True)
    require_call_completed(result, origin="runtime fifo")
    assert environ_value(result, name) == value
    load_reports_differ(result, failure, origin="runtime fifo")


def test_fifo_default_does_not_override_existing():
    name, old, new = unique_token(), unique_token(), unique_token()
    with workspace() as ws:
        with ws.fifo("pipe.env", f"{name}={new}\n") as fifo:
            result = call(
                load_envfile,
                envfile_path=str(fifo),
                env={name: old},
            )
        failure = _empty_file_load(env={name: old})
    print(f"FIFO default no-override {name!r}", flush=True)
    require_call_completed(result, origin="fifo no-override")
    assert environ_value(result, name) == old
    load_reports_differ(result, failure, origin="fifo no-override")


def test_stream_default_does_not_override_existing():
    name, old, new = unique_token(), unique_token(), unique_token()
    result = call(
        load_envfile,
        stream=StringIO(f"{name}={new}\n"),
        env={name: old},
    )
    failure = _empty_stream_load(env={name: old})
    print(f"stream default no-override {name!r}", flush=True)
    require_call_completed(result, origin="stream no-override")
    assert environ_value(result, name) == old
    load_reports_differ(result, failure, origin="stream no-override")


# ---------------------------------------------------------------------------
# D. Success/failure reports; empty source; missing file; extra reporting
# ---------------------------------------------------------------------------


def test_override_off_unchanged_names_still_reports_success():
    with workspace() as ws:
        filled = ws.write("filled.env", "a=b\n")
        empty = ws.write("empty.env", "")
        success = call(load_envfile, envfile_path=str(filled), env={"a": "c"})
        failure = call(load_envfile, envfile_path=str(empty), env={"a": "c"})
    print("override off, a already c, still reports success", flush=True)
    require_call_completed(success, origin="unchanged still success")
    assert environ_value(success, "a") == "c"
    load_reports_differ(success, failure, origin="unchanged still success")


def test_no_value_only_source_reports_success():
    with workspace() as ws:
        path = ws.write("only-novalue.env", "FOO\n")
        success = call(load_envfile, envfile_path=str(path))
        failure = _empty_file_load()
    print("no-value-only source reports success", flush=True)
    require_environ_absent(success, "FOO")
    load_reports_differ(success, failure, origin="no-value-only success")
    assert "FOO" not in success.environ, (
        f"no-value-only FOO was written {success.environ.get('FOO')!r}; "
        f"keys={sorted(success.environ)!r}"
    )
    assert success.value != failure.value, (
        f"no-value-only success and empty-file failure are indistinguishable: "
        f"{success.value!r}"
    )


def test_empty_file_reports_failure():
    name, value = unique_token(), unique_token()
    with workspace() as ws:
        empty = ws.write("empty.env", "")
        filled = ws.write("filled.env", f"{name}={value}\n")
        failure = call(load_envfile, envfile_path=str(empty))
        success = call(load_envfile, envfile_path=str(filled))
    print("empty file reports failure", flush=True)
    require_environ_absent(failure, name)
    load_reports_differ(success, failure, origin="empty file")
    assert name not in failure.environ, (
        f"empty file wrote {name!r}={failure.environ.get(name)!r}; "
        f"keys={sorted(failure.environ)!r}"
    )
    assert success.value != failure.value, (
        f"filled-file success and empty-file failure are indistinguishable: "
        f"{success.value!r}"
    )


def test_comments_only_reports_failure():
    token, value = unique_token(), unique_token()
    with workspace() as ws:
        commented = ws.write("comments.env", f"# {token}={value}\n")
        live = ws.write("live.env", f"{token}={value}\n")
        failure = call(load_envfile, envfile_path=str(commented))
        success = call(load_envfile, envfile_path=str(live))
        empty = _empty_file_load()
    print(f"comments-only #{token}={value}", flush=True)
    require_environ_absent(failure, token)
    assert environ_value(success, token) == value
    load_reports_differ(success, failure, origin="comments-only")
    load_reports_differ(success, empty, origin="empty file failure class")


def test_missing_path_reports_failure_and_completes():
    name, value = unique_token(), unique_token()
    with workspace() as ws:
        missing = ws.resolve(f"{unique_token()}.env")
        filled = ws.write("filled.env", f"{name}={value}\n")
        failure = call(load_envfile, envfile_path=str(missing))
        success = call(load_envfile, envfile_path=str(filled))
    print(f"missing path {missing}", flush=True)
    require_call_completed(failure, origin="missing path")
    require_environ_absent(failure, name)
    load_reports_differ(success, failure, origin="missing path")
    assert failure.exception is None, (
        f"missing path aborted the caller: {failure.exception!r}"
    )
    assert name not in failure.environ, (
        f"missing path wrote {name!r}={failure.environ.get(name)!r}; "
        f"keys={sorted(failure.environ)!r}"
    )
    assert success.value != failure.value, (
        f"filled-file success and missing-path failure are indistinguishable: "
        f"{success.value!r}"
    )


def test_explicit_missing_path_does_not_locate():
    fromfile, fromfile_val = unique_token(), unique_token()
    pkg = product_package_name()
    with workspace() as ws:
        ws.write(".env", f"{fromfile}={fromfile_val}\n")
        missing = ws.resolve(f"{unique_token()}.env")
        baseline = ws.run_script(
            _no_arg_has_source(pkg, fromfile),
            relpath="baseline.py",
            cwd=ws.path,
        )
        stdout = require_script_success(baseline, label="missing-no-locate-baseline")
        has = require_labeled_line(
            stdout, "HAS", origin="missing-no-locate-baseline"
        )
        assert has == "1", f"no-arg load did not write locatable {fromfile!r}"

        result = call(
            load_envfile,
            envfile_path=str(missing),
            cwd=str(ws.path),
            isolate=False,
            env=ws.env,
        )
        success = call(
            load_envfile,
            envfile_path=str(ws.write("ok.env", f"{unique_token()}={unique_token()}\n")),
            cwd=str(ws.path),
            isolate=False,
            env=ws.env,
        )
    print(f"explicit missing path must not locate {fromfile!r}", flush=True)
    require_environ_absent(result, fromfile)
    load_reports_differ(success, result, origin="explicit missing does not locate")


def test_extra_reporting_missing_file_diagnostic_contrast():
    name, value = unique_token(), unique_token()
    with workspace() as ws:
        missing = ws.resolve(f"{unique_token()}.env")
        empty_path = ws.write("empty.env", "")
        filled = ws.write("filled.env", f"{name}={value}\n")

        on_result, on_records = load_with_log_capture(
            envfile_path=str(missing),
            verbose=True,
        )
        off_result, off_records = load_with_log_capture(
            envfile_path=str(missing),
        )
        empty_result, empty_records = load_with_log_capture(
            envfile_path=str(empty_path),
            verbose=True,
        )
        success = call(load_envfile, envfile_path=str(filled))

    print("extra reporting missing-file diagnostic contrast", flush=True)
    require_call_completed(on_result, origin="extra-on missing")
    require_call_completed(off_result, origin="extra-off missing")
    require_call_completed(empty_result, origin="extra-on empty")
    require_environ_absent(off_result, name)
    load_reports_differ(success, off_result, origin="extra-off missing failure")
    load_reports_differ(success, on_result, origin="extra-on missing failure")
    load_reports_differ(success, empty_result, origin="extra-on empty failure")

    on_text = diagnostics_text(on_result, on_records)
    off_text = diagnostics_text(off_result, off_records)
    empty_text = diagnostics_text(empty_result, empty_records)
    assert on_text.strip(), (
        "asking for extra reporting on a missing file produced no diagnostic"
    )
    assert on_text != off_text, (
        "extra reporting on/off for the same missing path are indistinguishable"
    )
    assert not off_text.strip(), (
        "without extra reporting, a missing file still emitted the "
        "missing-file diagnostic"
    )

    require_line_naming(on_text, missing, origin="extra-on missing")
    require_no_line_naming(empty_text, empty_path, origin="extra-on empty file")


# ---------------------------------------------------------------------------
# E. PYTHON_ENVFILE_DISABLED switch
# ---------------------------------------------------------------------------


def test_disable_truthy_spellings_block_file_and_stream():
    name, value = unique_token(), unique_token()
    source = f"a=b\n{name}={value}\n"
    enabled_stream = read_tracking_stream(source)
    enabled = call(load_envfile, stream=enabled_stream)
    print(
        f"disable live baseline consumed={enabled_stream.consumed}",
        flush=True,
    )
    require_call_completed(enabled, origin="disable live baseline")
    assert enabled_stream.consumed, (
        "tracking stream was not consumed when loading was enabled"
    )
    assert environ_value(enabled, "a") == "b"
    assert environ_value(enabled, name) == value

    with workspace() as ws:
        path = ws.write("blocked.env", source)
        file_enabled = call(load_envfile, envfile_path=str(path))
        require_call_completed(file_enabled, origin="disable file baseline")
        assert environ_value(file_enabled, "a") == "b"
        for spelling in TRUTHY_SPELLINGS:
            file_result = call(
                load_envfile,
                envfile_path=str(path),
                env={DISABLE_SWITCH: spelling},
            )
            print(f"disable file spelling={spelling!r}", flush=True)
            require_environ_absent(file_result, "a")
            require_environ_absent(file_result, name)
            assert environ_value(file_result, DISABLE_SWITCH) == spelling
            load_reports_differ(
                file_enabled, file_result, origin=f"disable file {spelling!r}"
            )

            tracked = read_tracking_stream(source)
            stream_result = call(
                load_envfile,
                stream=tracked,
                env={DISABLE_SWITCH: spelling},
            )
            print(
                f"disable stream spelling={spelling!r} consumed={tracked.consumed}",
                flush=True,
            )
            require_environ_absent(stream_result, "a")
            require_environ_absent(stream_result, name)
            assert environ_value(stream_result, DISABLE_SWITCH) == spelling
            assert not tracked.consumed, (
                f"truthy spelling {spelling!r} still consumed the stream"
            )
            load_reports_differ(
                enabled, stream_result, origin=f"disable stream {spelling!r}"
            )


def test_disable_other_values_still_load():
    name, value = unique_token(), unique_token()
    with workspace() as ws:
        path = ws.write("still.env", f"a=b\n{name}={value}\n")
        failure = _empty_file_load()
        for spelling in NON_TRUTHY_SPELLINGS:
            result = call(
                load_envfile,
                envfile_path=str(path),
                env={DISABLE_SWITCH: spelling},
            )
            print(f"non-truthy spelling={spelling!r} still loads", flush=True)
            require_call_completed(result, origin=f"still-load {spelling!r}")
            assert environ_value(result, "a") == "b"
            assert environ_value(result, name) == value
            load_reports_differ(result, failure, origin=f"still-load {spelling!r}")


def test_disable_absent_still_loads():
    name, value = unique_token(), unique_token()
    with workspace() as ws:
        path = ws.write("absent.env", f"a=b\n{name}={value}\n")
        result = call(load_envfile, envfile_path=str(path))
        failure = _empty_file_load()
    print("disable variable absent still loads", flush=True)
    require_call_completed(result, origin="disable absent")
    require_environ_absent(result, DISABLE_SWITCH)
    assert environ_value(result, "a") == "b"
    assert environ_value(result, name) == value
    load_reports_differ(result, failure, origin="disable absent")


def test_runtime_non_truthy_spelling_still_loads():
    spelling = unique_token()
    name, value = unique_token(), unique_token()
    with workspace() as ws:
        path = ws.write("runtime-flag.env", f"a=b\n{name}={value}\n")
        result = call(
            load_envfile,
            envfile_path=str(path),
            env={DISABLE_SWITCH: spelling},
        )
        failure = _empty_file_load()
    print(f"runtime non-truthy spelling={spelling!r} still loads", flush=True)
    require_call_completed(result, origin="runtime non-truthy")
    assert environ_value(result, "a") == "b"
    assert environ_value(result, name) == value
    load_reports_differ(result, failure, origin="runtime non-truthy")


def test_disable_line_inside_source_does_not_gate_that_load():
    name, value = unique_token(), unique_token()
    with workspace() as ws:
        path = ws.write(
            "inside.env",
            f"{DISABLE_SWITCH}=true\n{name}={value}\n",
        )
        result = call(load_envfile, envfile_path=str(path))
        failure = _empty_file_load()
    print("disable line inside source does not gate that load", flush=True)
    require_call_completed(result, origin="inside disable line")
    assert environ_value(result, DISABLE_SWITCH) == "true"
    assert environ_value(result, name) == value
    load_reports_differ(result, failure, origin="inside disable line")


def test_values_mapping_not_gated_by_disable_switch():
    name, value = unique_token(), unique_token()
    spelling = "1"
    with workspace() as ws:
        path = ws.write("mapping.env", f"a=b\n{name}={value}\n")
        mapping_result = call(
            envfile_values,
            envfile_path=str(path),
            interpolate=False,
            env={DISABLE_SWITCH: spelling},
        )
        load_result = call(
            load_envfile,
            envfile_path=str(path),
            env={DISABLE_SWITCH: spelling},
        )
        enabled_load = call(load_envfile, envfile_path=str(path))
        enabled_mapping = bindings_from_file(path)
    print("values-mapping is not gated by the disable switch", flush=True)
    require_call_completed(mapping_result, origin="mapping under disable")
    mapping = mapping_result.value
    assert isinstance(mapping, Mapping), (
        f"values-mapping under disable did not return a mapping; "
        f"got {type(mapping)!r}: {mapping!r}"
    )
    assert require_binding(mapping, "a") == "b"
    assert require_binding(mapping, name) == value
    require_environ_absent(mapping_result, "a")
    require_environ_absent(mapping_result, name)
    assert require_binding(enabled_mapping, name) == value
    require_environ_absent(load_result, "a")
    require_environ_absent(load_result, name)
    load_reports_differ(
        enabled_load,
        load_result,
        origin="load gated, mapping not",
    )


# ---------------------------------------------------------------------------
# F. Caller-named encoding (including latin-1)
# ---------------------------------------------------------------------------


def test_latin1_named_encoding_public_pair():
    payload = "é=è".encode("latin-1")
    with workspace() as ws:
        path = ws.write("latin1.env", payload)
        result = call(
            load_envfile,
            envfile_path=str(path),
            encoding="latin-1",
        )
        failure = _empty_file_load(encoding="latin-1")
    print("latin-1 named encoding public é=è", flush=True)
    require_call_completed(result, origin="latin-1 public")
    assert environ_value(result, "é") == "è"
    load_reports_differ(result, failure, origin="latin-1 public")


def test_latin1_named_encoding_runtime_pair():
    name, value = "ñ", "ö"
    payload = f"{name}={value}".encode("latin-1")
    with workspace() as ws:
        path = ws.write("latin1-rt.env", payload)
        result = call(
            load_envfile,
            envfile_path=str(path),
            encoding="latin-1",
        )
        failure = _empty_file_load(encoding="latin-1")
    print("latin-1 named encoding runtime ñ=ö", flush=True)
    require_call_completed(result, origin="latin-1 runtime")
    assert environ_value(result, name) == value
    load_reports_differ(result, failure, origin="latin-1 runtime")


def test_named_encoding_changes_decoded_bindings():
    runtime_name, runtime_value = "\u00f1", "\u00f6" + unique_token()
    text = f"é=è\n{runtime_name}={runtime_value}\n"
    payload = text.encode("utf-8")
    with workspace() as ws:
        path = ws.write("dual.env", payload)
        utf8 = call(
            load_envfile,
            envfile_path=str(path),
            encoding="utf-8",
        )
        latin1 = call(
            load_envfile,
            envfile_path=str(path),
            encoding="latin-1",
        )
        failure = _empty_file_load(encoding="utf-8")
    print("named encoding utf-8 vs latin-1 on the same UTF-8 bytes", flush=True)
    require_call_completed(utf8, origin="named utf-8")
    require_call_completed(latin1, origin="named latin-1")
    load_reports_differ(utf8, failure, origin="named utf-8")
    load_reports_differ(latin1, failure, origin="named latin-1")
    assert environ_value(utf8, "é") == "è"
    assert environ_value(utf8, runtime_name) == runtime_value
    utf8_bindings = {
        key: utf8.environ[key]
        for key in ("é", runtime_name)
        if key in utf8.environ
    }
    latin1_bindings = {
        key: latin1.environ[key]
        for key in ("é", runtime_name)
        if key in latin1.environ
    }
    assert utf8_bindings != latin1_bindings, (
        "naming utf-8 versus latin-1 on the same bytes produced the same "
        f"bindings {utf8_bindings!r}"
    )


# ---------------------------------------------------------------------------
# G. Expansion on by default; off leaves dollar-brace text literal
# ---------------------------------------------------------------------------


def test_expansion_on_by_default_writes_expanded_strings():
    token_name, token_val = unique_token(), unique_token()
    public = call(
        load_envfile,
        stream=StringIO("a=${b}\n"),
        env={"b": "c"},
    )
    runtime = call(
        load_envfile,
        stream=StringIO("a=${" + token_name + "}\n"),
        env={token_name: token_val},
    )
    failure = _empty_stream_load(env={"b": "c", token_name: token_val})
    print(
        f"default expansion on: a=${{b}} with b=c; a=${{{token_name}}}",
        flush=True,
    )
    require_call_completed(public, origin="expansion default public")
    assert environ_value(public, "a") == "c"
    assert environ_value(public, "a") != "${b}"
    require_call_completed(runtime, origin="expansion default runtime")
    assert environ_value(runtime, "a") == token_val
    assert environ_value(runtime, "a") != "${" + token_name + "}"
    load_reports_differ(public, failure, origin="expansion default")


def test_expansion_off_leaves_dollar_brace_literal():
    token_name, token_val = unique_token(), unique_token()
    public = call(
        load_envfile,
        stream=StringIO("a=${b}\n"),
        env={"b": "c"},
        interpolate=False,
    )
    runtime = call(
        load_envfile,
        stream=StringIO("a=${" + token_name + "}\n"),
        env={token_name: token_val},
        interpolate=False,
    )
    on_public = call(
        load_envfile,
        stream=StringIO("a=${b}\n"),
        env={"b": "c"},
    )
    print(
        f"expansion off: public ${{b}}; runtime ${{{token_name}}}",
        flush=True,
    )
    require_call_completed(public, origin="expansion off public")
    assert environ_value(public, "a") == "${b}"
    require_call_completed(runtime, origin="expansion off runtime")
    assert environ_value(runtime, "a") == "${" + token_name + "}"
    require_call_completed(on_public, origin="expansion on baseline")
    assert environ_value(on_public, "a") == "c"
    assert environ_value(on_public, "a") != environ_value(public, "a")
