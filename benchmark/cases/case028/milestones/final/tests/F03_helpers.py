# feature: F03
"""Package declarations and imports for independent native Go comparisons."""

from pathlib import Path

import pytest

from _helpers import build_go, isolated_workspace, parse_json, run_process, write_files
from F01_helpers import f01_driver, f01_eval, f01_success, f01_value
from F02_helpers import F02_CAPTURE


def f03_reads(*expressions):
    return [(expression, True) for expression in expressions]


@pytest.fixture(scope="module")
def f03_package_compare(f01_driver):
    """Extend the scalar comparison to package-level types and unsafe imports.

    Observations are scalar snapshots, never addresses or aggregate formatting.
    The native oracle imports only the standard library.
    """
    product = Path.cwd()
    with isolated_workspace(overrides={"GOPROXY": "off"}) as workspace:
        serial = 0

        def compare(declarations, steps, *, imports=()):
            nonlocal serial
            serial += 1
            import_source = "\n".join(f'import "{name}"' for name in imports)
            statements = []
            for source, expression in steps:
                statements.append(
                    "values = append(values, capture(reflect.ValueOf(" + source + ")))"
                    if expression else source)
            native_source = ('package main\nimport ("encoding/json"; "os"; "reflect")\n' +
                             import_source + "\n" + declarations + "\n" + F02_CAPTURE +
                             "\nfunc main() { values := []scalar{}\n" +
                             "\n".join(statements) + "\nemit(values) }\n")
            path = write_files(workspace.cwd, {f"native-{serial}.go": native_source})[f"native-{serial}.go"]
            binary = build_go(["go"], path, cwd=product,
                              output=workspace.root / f"native-{serial}",
                              env=workspace.env, timeout=240).artifact
            process = run_process([binary], cwd=workspace.cwd, env=workspace.env, timeout=45)
            assert process.returncode == 0, process
            expected = parse_json(process.stdout)
            actions = [{"Op": "new", "Session": "a"},
                       f01_eval(import_source + "\n" + declarations)]
            actions.extend(f01_eval(source, read_value=expression) for source, expression in steps)
            records, _ = f01_driver(actions)
            f01_success(records)
            values = [record for record, (_, expression) in zip(records[2:], steps) if expression]
            assert len(values) == len(expected), (values, expected)
            for actual, oracle in zip(values, expected):
                f01_value(actual, oracle["Type"], oracle["Value"])

        yield compare
