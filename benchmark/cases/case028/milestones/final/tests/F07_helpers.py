# feature: F07
"""Native and interpreted channel programs with the same real host endpoints."""

import json
from pathlib import Path

import pytest

from _helpers import build_go, isolated_workspace, parse_json, run_process, write_files
from F02_helpers import F02_CAPTURE


@pytest.fixture(scope="module")
def f07_host_compare():
    product = Path.cwd()
    with isolated_workspace(overrides={"GOPROXY": "off", "ZELVIRO_DEBUG": None,
                                       "ZELVIRO_TRACE": None}) as workspace:
        serial = 0

        def compare(setup, bindings, source, observation):
            nonlocal serial
            serial += 1
            fields = "; ".join(f"{name} {kind}" for name, kind, value in bindings)
            initializers = ", ".join(value for name, kind, value in bindings)
            exports = ", ".join(f'{json.dumps(name)}: reflect.ValueOf({value})'
                                for name, kind, value in bindings)
            launches = {
                "native": (f"bridge := struct {{ {fields} }}{{ {initializers} }}\n"
                           "go func() {\n" + source + "\ndone <- nil\n}()\n"),
                "interpreted": (
                    "engine := interp.NewInterpreter(golang.GoSpec); defer engine.Close()\n"
                    'engine.ImportPackageValues(map[string]map[string]reflect.Value{'
                    '"bridge": {' + exports + '}})\n'
                    'go func() { _, err := engine.Eval("channels.go", ' +
                    json.dumps('import "bridge"\nfunc runChannels() {\n' + source + '\n}\nrunChannels()') + '); done <- err }()\n'),
            }
            results = {}
            for mode, launch in launches.items():
                imports = ('; "github.com/zelviro-sh/zelviro/interp"; '
                           '"github.com/zelviro-sh/zelviro/lang/golang"') if mode == "interpreted" else ""
                program = ('package main\nimport ("encoding/json"; "os"; "reflect"; "runtime"' +
                           imports + ')\n' + F02_CAPTURE + '\nfunc main() {\n'
                           'runtime.GOMAXPROCS(1)\nvalues := []scalar{}\ndone := make(chan error, 1)\n' +
                           setup + '\n' + launch + observation +
                           '\nif err := <-done; err != nil { panic(err) }\nemit(values)\n}\n')
                path = write_files(workspace.cwd, {f"{mode}-{serial}.go": program})[f"{mode}-{serial}.go"]
                binary = build_go(["go"], path, cwd=product, env=workspace.env,
                                  output=workspace.root / f"{mode}-{serial}", timeout=240).artifact
                process = run_process([binary], cwd=workspace.cwd, env=workspace.env, timeout=45)
                assert process.returncode == 0, process
                results[mode] = parse_json(process.stdout)
            assert results["native"], results
            assert results["interpreted"] == results["native"], results
            return results

        yield compare
