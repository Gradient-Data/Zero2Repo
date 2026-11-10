# feature: F09
"""Native host observations and whole-program comparisons for interoperability."""

from pathlib import Path

import pytest

from _helpers import build_go, isolated_workspace, parse_json, run_process, write_files
from F01_helpers import f01_driver, f01_eval, f01_success
from F02_helpers import F02_CAPTURE


@pytest.fixture(scope="module")
def f09_host():
    with isolated_workspace(overrides={"GOPROXY": "off", "ZELVIRO_DEBUG": None,
                                       "ZELVIRO_TRACE": None}) as workspace:
        serial = 0

        def run(declarations, body):
            nonlocal serial
            serial += 1
            source = '''package main
import ("encoding/json"; "os"; "reflect";
"github.com/zelviro-sh/zelviro/interp"; "github.com/zelviro-sh/zelviro/lang/golang")
''' + F02_CAPTURE + declarations + '''
func main() {
    engine := interp.NewInterpreter(golang.GoSpec)
    defer engine.Close()
    values := []scalar{}
    eval := func(source string, read bool) {
        v, err := engine.Eval("interop.go", source)
        if err != nil { panic(err) }
        if read { values = append(values, capture(v)) }
    }
''' + body + '\nemit(values)\n}\n'
            path = write_files(workspace.cwd, {f"host-{serial}.go": source})[f"host-{serial}.go"]
            binary = build_go(["go"], path, cwd=Path.cwd(),
                              output=workspace.root / f"host-{serial}",
                              env=workspace.env, timeout=240).artifact
            process = run_process([binary], cwd=workspace.cwd, env=workspace.env, timeout=45)
            assert process.returncode == 0, process
            return parse_json(process.stdout)

        yield run


@pytest.fixture(scope="module")
def f09_program_compare(f01_driver):
    """Execute real native libraries in both runs; compare explicit JSON results."""
    with isolated_workspace(overrides={"GOPROXY": "off"}) as workspace:
        serial = 0

        def compare(source):
            nonlocal serial
            serial += 1
            path = write_files(workspace.cwd, {f"oracle-{serial}.go": source})[f"oracle-{serial}.go"]
            binary = build_go(["go"], path, cwd=Path.cwd(),
                              output=workspace.root / f"oracle-{serial}",
                              env=workspace.env, timeout=240).artifact
            native = run_process([binary], cwd=workspace.cwd, env=workspace.env, timeout=45)
            assert native.returncode == 0, native
            expected = parse_json(native.stdout)
            records, _ = f01_driver([{"Op": "new", "Session": "a"}, f01_eval(source)])
            f01_success(records)
            actual = parse_json(records[-1]["output"])
            assert actual == expected, (actual, expected)
            return actual

        yield compare
