# feature: F06
"""Run the same package-identity program through Eval and native Go."""

import json
from pathlib import Path

import pytest

from _helpers import build_go, isolated_workspace, parse_json, run_process, write_files
from F02_helpers import F02_CAPTURE


@pytest.fixture(scope="module")
def f06_package_identity_compare():
    """Use real source packages loaded by SetPkgfs, never substituted bindings."""
    product = Path.cwd()
    with isolated_workspace(overrides={"GOPROXY": "off", "ZELVIRO_DEBUG": None,
                                       "ZELVIRO_TRACE": None}) as workspace:
        serial = 0

        def compare(packages, declarations, steps):
            nonlocal serial
            serial += 1
            root = workspace.cwd / str(serial)
            module = root / "identity"
            imports = "\n".join(f'import {name} "identity/{name}"' for name in packages)
            files = {f"{name}/types.go": source for name, source in packages.items()}
            files["go.mod"] = "module identity\n\ngo 1.26\n"
            native_steps = [
                "values = append(values, capture(reflect.ValueOf(" + source + ")))"
                if expression else source for source, expression in steps
            ]
            files["main.go"] = ('package main\nimport ("encoding/json"; "os"; "reflect")\n' +
                                imports + "\n" + declarations + "\n" + F02_CAPTURE +
                                "\nfunc main() { values := []scalar{}\n" +
                                "\n".join(native_steps) + "\nemit(values) }\n")
            write_files(module, files)
            evaluations = [(imports + "\n" + declarations, False)] + steps
            calls = []
            for source, expression in evaluations:
                calls.append('v, err = engine.Eval("identity.go", ' + json.dumps(source) + ')\n' +
                             'if err != nil { panic(err) }\n' +
                             ('values = append(values, capture(v))\n' if expression else ''))
            observer = ('package main\nimport ("encoding/json"; "os"; "reflect"; '
                        '"github.com/zelviro-sh/zelviro/interp"; "github.com/zelviro-sh/zelviro/lang/golang")\n' +
                        F02_CAPTURE + '\nfunc main() {\n'
                        'engine := interp.NewInterpreter(golang.GoSpec); defer engine.Close()\n'
                        'engine.SetPkgfs(os.Args[1])\n'
                        'var v reflect.Value; var err error; values := []scalar{}\n' +
                        ''.join(calls) + 'emit(values)\n}\n')
            source = write_files(root, {"observer.go": observer})["observer.go"]
            values = {}
            for name, target, cwd, args in (
                ("native", ".", module, []),
                ("interpreted", source, product, [root]),
            ):
                binary = build_go(["go"], target, cwd=cwd, output=root / name,
                                  env=workspace.env, timeout=240).artifact
                process = run_process([binary, *args], cwd=root, env=workspace.env, timeout=45)
                assert process.returncode == 0, process
                values[name] = parse_json(process.stdout)
            expressions = [source for source, expression in steps if expression]
            assert len(values["native"]) == len(expressions), values
            assert len(values["interpreted"]) == len(expressions), values
            for expression, actual, expected in zip(expressions, values["interpreted"], values["native"]):
                assert actual == expected, (expression, actual, expected)

        yield compare
