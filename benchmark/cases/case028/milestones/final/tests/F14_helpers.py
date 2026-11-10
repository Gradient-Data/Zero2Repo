# feature: F14
"""Real embedding observations and parsing of labeled runtime diagnostics."""

import json
from pathlib import Path
import re

import pytest

from _helpers import build_go, isolated_workspace, parse_json, read_bytes, run_process, write_files


F14_HOST = r'''package main
import (
    "bytes"
    "encoding/json"
    "errors"
    "os"
    "reflect"
    "sync"
    "github.com/zelviro-sh/zelviro/interp"
    "github.com/zelviro-sh/zelviro/lang/golang"
    "github.com/zelviro-sh/zelviro/stdlib"
    _ "github.com/zelviro-sh/zelviro/stdlib/all"
)
func main() {
    data, err := os.ReadFile(os.Args[1]); if err != nil { panic(err) }
    var request struct { Label, Source string }
    if err := json.Unmarshal(data, &request); err != nil { panic(err) }
    engine := interp.NewInterpreter(golang.GoSpec)
    defer engine.Close()
    engine.ImportPackageValues(stdlib.Values)
    var output, diagnostic bytes.Buffer
    engine.SetIO(nil, &output, &diagnostic)
    var mu sync.Mutex
    events := []string{}
    note := func(s string) { mu.Lock(); defer mu.Unlock(); events = append(events, s) }
    engine.ImportPackageValues(map[string]map[string]reflect.Value{
        "bridge": {
            "Note": reflect.ValueOf(note),
            "Call": reflect.ValueOf(func(callback func()) { callback() }),
        },
    })
    _, evalErr := engine.Eval(request.Label, request.Source)
    var errorText *string
    var exitCode *int
    if evalErr != nil {
        s := evalErr.Error(); errorText = &s
        var exit *interp.ExitError
        if errors.As(evalErr, &exit) { code := exit.Code; exitCode = &code }
    }
    // This native action only occurs after Eval returns to its embedding host.
    note("host-resumed")
    mu.Lock()
    result := struct {
        Error *string
        ExitCode *int
        Output, Diagnostic string
        Events []string
    }{errorText, exitCode, output.String(), diagnostic.String(), events}
    data, err = json.Marshal(result)
    mu.Unlock()
    if err != nil { panic(err) }
    if err := os.WriteFile(os.Args[2], data, 0600); err != nil { panic(err) }
}
'''


@pytest.fixture(scope="module")
def f14_host():
    product = Path.cwd()
    with isolated_workspace(overrides={"GOPROXY": "off", "ZELVIRO_DEBUG": None,
                                       "ZELVIRO_TRACE": None}) as workspace:
        path = write_files(workspace.cwd, {"host.go": F14_HOST})["host.go"]
        binary = build_go(["go"], path, cwd=product, env=workspace.env,
                          output=workspace.root / "host", timeout=240).artifact
        serial = 0

        def observe(source, label="diagnostics.go"):
            nonlocal serial
            serial += 1
            request = write_files(workspace.cwd, {
                f"request-{serial}.json": json.dumps({"Label": label, "Source": source})
            })[f"request-{serial}.json"]
            response = workspace.cwd / f"response-{serial}.json"
            process = run_process([binary, request, response], cwd=workspace.cwd,
                                  env=workspace.env, timeout=45)
            assert process.returncode == 0, process
            return parse_json(read_bytes(response))

        yield observe


@pytest.fixture(scope="module")
def f14_native():
    """Independent Go 1.26 standard-library oracle, with no product imports."""
    with isolated_workspace(overrides={"GOPROXY": "off"}) as workspace:
        serial = 0

        def run(source):
            nonlocal serial
            serial += 1
            path = write_files(workspace.cwd, {f"native-{serial}/runtime.go": source})[
                f"native-{serial}/runtime.go"]
            binary = build_go(["go"], path, cwd=Path.cwd(), env=workspace.env,
                              output=workspace.root / f"native-{serial}", timeout=240).artifact
            process = run_process([binary], cwd=workspace.cwd, env=workspace.env, timeout=45)
            assert process.returncode == 0, process
            return parse_json(process.stdout)

        yield run


def f14_diagnostic(text):
    """Read the panic header, labeled site, and stack rows, never message prose.

    The proposed shell has `panic: <cause>`, `at <function> (<source>:<line>:<column>)`
    and `zelviro stack:` followed by location/function rows. Snippets and native
    boundary decorations are not asserted. Numeric VM positions are not read.
    """
    lines = text.splitlines()
    assert lines and lines[0].startswith("panic: "), text
    site = re.fullmatch(r"\s+at (.+) \((.+):(\d+):(\d+)\)", lines[1])
    assert site is not None, text
    assert "zelviro stack:" in lines, text
    frames = []
    for line in lines[lines.index("zelviro stack:") + 1:]:
        if not line.strip():
            continue
        if re.fullmatch(r"\s+-- via .+ \[native\] --", line):
            continue
        row = re.fullmatch(r"\s+(.+):(\d+):(\d+)\s+(\S+)\s*", line)
        assert row is not None, (line, text)
        file, number, column, function = row.groups()
        # Package qualification is optional in diagnostic display names.
        # Source labels and positions still distinguish the observed calls.
        frames.append((function.rsplit(".", 1)[-1], file, int(number), int(column)))
    function, file, number, column = site.groups()
    return {"cause": lines[0][len("panic: "):],
            "site": (function.rsplit(".", 1)[-1], file, int(number), int(column)), "frames": frames}


def f14_source_frame(frame, function, label, source, line):
    assert frame[:3] == (function, label, line), frame
    # Only source attribution matters; do not pin the compiler's token choice.
    assert 1 <= frame[3] <= len(source.splitlines()[line - 1]) + 1, frame
