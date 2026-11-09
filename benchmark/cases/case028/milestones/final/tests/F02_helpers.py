# feature: F02
"""Compare public Eval results with an independent Go 1.26 executable."""

import json
from pathlib import Path

import pytest

from _helpers import build_go, isolated_workspace, parse_json, run_process, write_files


F02_CAPTURE = r'''
type scalar struct {
    Type string
    Value any
}
func capture(v reflect.Value) scalar {
    if !v.IsValid() { panic("expression returned no value") }
    var value any
    switch v.Kind() {
    case reflect.Complex64, reflect.Complex128:
        c := v.Complex()
        value = []float64{real(c), imag(c)}
    default:
        value = v.Interface()
    }
    return scalar{v.Type().String(), value}
}
func emit(values []scalar) {
    if err := json.NewEncoder(os.Stdout).Encode(values); err != nil { panic(err) }
}
'''


@pytest.fixture(scope="module")
def f02_compare():
    """Steps are (source, is_expression); each scenario has independent state.

    The oracle contains only standard-library imports. Both programs capture
    scalar values immediately, so later assignment cannot change observations.
    No product transformation is reproduced in Python or in the Go observer.
    """
    product = Path.cwd()
    assert (product / "go.mod").is_file(), "Run from the product module directory"
    with isolated_workspace(overrides={"GOPROXY": "off", "ZELVIRO_DEBUG": None,
                                       "ZELVIRO_TRACE": None}) as workspace:
        serial = 0

        def compare(scenarios, *, program=False):
            nonlocal serial
            serial += 1
            native_blocks, interpreted_blocks, expressions = [], [], []
            for steps in scenarios:
                native, interpreted, body = [], [], []
                for source, expression in steps:
                    if expression:
                        native.append("values = append(values, capture(reflect.ValueOf(" + source + ")))\n")
                        expressions.append(source)
                        body.append("observer.Capture(" + source + ")\n")
                    else:
                        native.append(source + "\n")
                        body.append(source + "\n")
                    interpreted.append(
                        "v, err = engine.Eval(\"scalar.go\", " + json.dumps(source) + ")\n"
                        "if err != nil { panic(err) }\n" +
                        ("values = append(values, capture(v))\n" if expression else ""))
                native_blocks.append("{\n" + "".join(native) + "}\n")
                if program:
                    # Scalar semantics are exercised in an ordinary function;
                    # the separate stateful tests cover incremental evaluation.
                    text = 'package main\nimport observer "bench.local/observation"\nfunc main(){\n' + "".join(body) + '}\n'
                    interpreted_blocks.append(
                        '{\nengine := interp.NewInterpreter(golang.GoSpec)\n'
                        'engine.ImportPackageValues(map[string]map[string]reflect.Value{'
                        '"bench.local/observation": {"Capture": reflect.ValueOf(func(v any) {'
                        'values = append(values, capture(reflect.ValueOf(v))) })}})\n'
                        'if _, err := engine.Eval("scalar.go", ' + json.dumps(text) + '); err != nil { panic(err) }\n'
                        'engine.Close()\n}\n')
                else:
                    interpreted_blocks.append(
                        "{\nengine := interp.NewInterpreter(golang.GoSpec)\n"
                        "var v reflect.Value\nvar err error\n" + "".join(interpreted) +
                        "engine.Close()\n}\n")
            sources = {
                "native": 'package main\nimport ("encoding/json"; "os"; "reflect")\n' +
                          F02_CAPTURE + "func main() { values := []scalar{}\n" +
                          "".join(native_blocks) + "emit(values) }\n",
                "interpreted": 'package main\nimport ("encoding/json"; "os"; "reflect"; '
                               '"github.com/zelviro-sh/zelviro/interp"; '
                               '"github.com/zelviro-sh/zelviro/lang/golang")\n' +
                               F02_CAPTURE + "func main() { values := []scalar{}\n" +
                               "".join(interpreted_blocks) + "emit(values) }\n",
            }
            results = {}
            for name, source in sources.items():
                filename = f"{name}-{serial}.go"
                path = write_files(workspace.cwd, {filename: source})[filename]
                binary = build_go(["go"], path, cwd=product,
                                  output=workspace.root / f"{name}-{serial}",
                                  env=workspace.env, timeout=240).artifact
                process = run_process([binary], cwd=workspace.cwd, env=workspace.env,
                                      timeout=45)
                assert process.returncode == 0, process
                results[name] = parse_json(process.stdout)
            assert len(results["native"]) == len(expressions), results
            assert len(results["interpreted"]) == len(expressions), results
            for source, actual, expected in zip(expressions, results["interpreted"],
                                                 results["native"]):
                assert actual == expected, (source, actual, expected)
            return results

        yield compare
