# feature: F10
"""Library programs and independent native Go codec endpoints."""

import json
from pathlib import Path

import pytest

from _helpers import build_go, isolated_workspace, parse_json, run_process, write_files
from F01_helpers import f01_eval, f01_success
from F02_helpers import F02_CAPTURE


def f10_program(imports, body, declarations=""):
    imports = sorted(set(imports) | {"fmt", "encoding/json"})
    return ('package main\nimport (' + ';'.join(json.dumps(p) for p in imports) +
            ')\nfunc must(err error) { if err != nil { panic(err) } }\n'
            'func panics(f func()) (caught bool) { '
            'defer func() { if recover() != nil { caught = true } }(); f(); return }\n' +
            declarations + '\nfunc main() {\nout := map[string]any{}\n' + body +
            '\n{ payload, err := json.Marshal(out); must(err); fmt.Println(string(payload)) }\n}\n')


def f10_eval_json(driver, source):
    records, _ = driver([{"Op": "new", "Session": "a"}, f01_eval(source)])
    f01_success(records)
    return parse_json(records[-1]["output"])


def f10_cross_codec(native, driver, encode, decoder):
    """Neither side may substitute its own encoder for the other's input."""
    reference_bytes = native(encode)
    product_bytes = f10_eval_json(driver, encode)
    expected = native(decoder(reference_bytes))
    assert native(decoder(product_bytes)) == expected
    assert f10_eval_json(driver, decoder(reference_bytes)) == expected


def f10_encoded_inputs(encoded):
    return ('var encoded map[string][]byte; must(json.Unmarshal([]byte(' +
            json.dumps(json.dumps(encoded)) + '), &encoded))\n')


@pytest.fixture(scope="module")
def f10_native():
    """Run standalone standard-library programs without importing the product."""
    with isolated_workspace(overrides={"GOPROXY": "off"}) as workspace:
        serial = 0

        def run(source):
            nonlocal serial
            serial += 1
            path = write_files(workspace.cwd, {f"native-{serial}.go": source})[f"native-{serial}.go"]
            binary = build_go(["go"], path, cwd=Path.cwd(), env=workspace.env,
                              output=workspace.root / f"native-{serial}", timeout=240).artifact
            result = run_process([binary], cwd=workspace.cwd, env=workspace.env, timeout=45)
            assert result.returncode == 0, result
            return parse_json(result.stdout)

        yield run


@pytest.fixture(scope="module")
def f10_cli():
    with isolated_workspace(overrides={"GOPROXY": "off", "ZELVIROCACHE": "off",
                                       "ZELVIRO_DEBUG": None, "ZELVIRO_TRACE": None}) as workspace:
        binary = build_go(["go"], ".", cwd=Path.cwd(), env=workspace.env, flags=("-buildvcs=false",),
                          output=workspace.root / "zelviro", timeout=240).artifact
        yield binary, workspace


@pytest.fixture(scope="module")
def f10_library_host():
    """Host-side standard libraries and real peers need additional Go imports."""
    with isolated_workspace(overrides={"GOPROXY": "off", "ZELVIRO_DEBUG": None,
                                       "ZELVIRO_TRACE": None}) as workspace:
        serial = 0

        def run(imports, body):
            nonlocal serial
            serial += 1
            source = ('package main\nimport ("encoding/json";"os";"reflect";'
                      '"github.com/zelviro-sh/zelviro/interp";"github.com/zelviro-sh/zelviro/lang/golang")\n' +
                      imports + '\n' + F02_CAPTURE + '\nfunc main(){\n'
                      'engine:=interp.NewInterpreter(golang.GoSpec);defer engine.Close()\n'
                      'values:=[]scalar{}\n'
                      'eval:=func(source string,read bool){v,err:=engine.Eval("libraries.go",source);'
                      'if err!=nil{panic(err)};if read{values=append(values,capture(v))}}\n' +
                      body + '\nemit(values)\n}\n')
            path = write_files(workspace.cwd, {f"host-{serial}.go": source})[f"host-{serial}.go"]
            binary = build_go(["go"], path, cwd=Path.cwd(), env=workspace.env,
                              output=workspace.root / f"host-{serial}", timeout=240).artifact
            result = run_process([binary], cwd=workspace.cwd, env=workspace.env, timeout=45)
            assert result.returncode == 0, result
            return parse_json(result.stdout)

        yield run
