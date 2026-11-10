# feature: F11
"""Source package acceptance through configured interpreters and real imports."""

import base64

from F11_helpers import (
    f11_packages, f01_eval, f01_success, f01_value, f01_undefined_at,
)


def test_cross_file_declarations_types_and_import_forms(f11_packages):
    files = {
        "fixture.test/graph/a.go": '''package graph
type First struct { Other *Second; Value Number }
type Alias = Second
var Initial = Later + 3
func Calculate(n Number) Number { return twice(n) + Initial }
''',
        "fixture.test/graph/z.go": '''package graph
type Number int
type Second struct { Other *First; Value Number }
var Later Number = 17
func twice(n Number) Number { return 2*n }
func Link(n Number) *First {
    a := &First{Value:n}; b := &Second{Other:a, Value:n+5}; a.Other = b; return a
}
''',
        "fixture.test/state/state.go": '''package state
var Message string
func ReadMessage() string { return Message }
''',
        "fixture.test/start/start.go": '''package start
import "fixture.test/state"
func init() { state.Message = "initialized by blank import" }
''',
        "fixture.test/plain/plain.go": 'package plain\nfunc Value() int { return 29 }\n',
    }
    source = '''package main
import (
    "fmt"
    g "fixture.test/graph"
    . "fixture.test/state"
    _ "fixture.test/start"
    "fixture.test/plain"
)
func main() {
    a := g.Link(11)
    b := g.Alias{Other:a, Value:31}
    fmt.Println(g.Initial, g.Calculate(7), a.Value, a.Other.Value,
        a.Other.Other == a, b.Other == a, b.Value, ReadMessage(), plain.Value())
}
'''
    f11_packages(files, [f01_eval(source)], compare_source=source)


def test_dependency_initialization_and_shared_imports(f11_packages):
    files = {
        "fixture.test/base/base.go": '''package base
import "fmt"
var Ready = seed()
var Count int
func seed() int { fmt.Println("base-variable"); return 7 }
func init() { Count++; Ready += 10; fmt.Println("base-init", Ready, Count) }
''',
        "fixture.test/left/a.go": '''package left
import ("fmt"; "fixture.test/base")
var First = Second + base.Ready
func init() { First++; fmt.Println("left-first-init", First, Second) }
''',
        "fixture.test/left/z.go": '''package left
import "fmt"
var Second = 23
func init() { First += 2; fmt.Println("left-second-init", First) }
''',
        "fixture.test/right/right.go": '''package right
import ("fmt"; "fixture.test/base"; "fixture.test/left")
var Observed = base.Ready + left.First
func init() { Observed += 5; fmt.Println("right-init", Observed, base.Count) }
''',
    }
    source = '''package main
import ("fmt"; "fixture.test/base"; "fixture.test/left"; "fixture.test/right")
var First = Last + right.Observed
var Last = base.Ready + left.First
func init() { First += 3; fmt.Println("main-init", First, Last, base.Count) }
func main() { fmt.Println("main-entry", First, Last, right.Observed, base.Count) }
'''
    f11_packages(files, [f01_eval(source)], compare_source=source)


def test_target_build_constraints_and_test_source_exclusion(f11_packages):
    # MatchFile is the independent Go standard-library oracle. Its input is
    # the same real source tree; the product result comes only from executing
    # the imported package, never from a product selection helper.
    headers = {
        "common.go": "",
        "os_linux.go": "", "os_windows.go": "", "os_darwin.go": "",
        "arch_amd64.go": "", "arch_arm64.go": "",
        "both_linux_amd64.go": "", "both_windows_arm64.go": "",
        "modern.go": "//go:build (linux || windows) && !extra\n\n",
        "legacy.go": "// +build linux,amd64 windows,arm64\n// +build !extra\n\n",
        "modernwins.go": "//go:build purego\n// +build never_added\n\n",
        "modernrejects.go": "//go:build never_added\n// +build purego\n\n",
        "unix.go": "//go:build unix\n\n",
        "notunix.go": "//go:build !unix\n\n",
        "release.go": "//go:build go1.26\n\n",
        "nextrelease.go": "//go:build go1.27\n\n",
        "pure.go": "//go:build purego\n\n",
        "safe.go": "//go:build safe\n\n",
        "http.go": "//go:build nethttpomithttp2\n\n",
        "optional.go": "//go:build extra\n\n",
        "platform.go": "//go:build windows && arm64\n\n",
        "ordinary_test.go": "",
    }
    files = {"fixture.test/selection/registry.go":
             "package selection\nvar Active = map[string]int{}\n"}
    identifiers = {}
    for index, (name, header) in enumerate(headers.items(), 1):
        identifiers[name] = index * 7
        files["fixture.test/selection/" + name] = (
            header + 'package selection\nfunc init() { Active["' + name + '"] = '
            + str(identifiers[name]) + ' }\n')
    for target, tags in ((None, ()), (("linux", "amd64"), ()),
                         (("linux", "amd64"), ("extra",)),
                         (("windows", "arm64"), ()), (("darwin", "arm64"), ())):
        records, selected = f11_packages(
            files, [f01_eval('import "fixture.test/selection"'),
                    f01_eval("selection.Active", read_value=True)],
            target=target, tags=tags, candidates=list(headers))
        f01_success(records)
        f01_value(records[-1], "map[string]int", {name: identifiers[name] for name in selected})


def test_single_file_embedding_all_destination_forms(f11_packages):
    files = {}
    contents = {"first": "cedar\n雪\x00\x01end\n", "second": "birch\tπ\x00different"}
    for package, payload in contents.items():
        files[f"fixture.test/{package}/data.txt"] = payload
        files[f"fixture.test/{package}/assets.go"] = f'''package {package}
import _ "embed"
type Text string
type Bytes []byte
//go:embed data.txt
var PlainText string
//go:embed data.txt
var PlainBytes []byte
//go:embed data.txt
var NamedText Text
//go:embed data.txt
var NamedBytes Bytes
'''
    # A same-named root file must not substitute for either package's asset.
    files["data.txt"] = "root is not the package directory"
    steps = [f01_eval('import ("fixture.test/first"; "fixture.test/second")')]
    expected = []
    for package, payload in contents.items():
        for name, type_name, value in (
            ("PlainText", "string", payload),
            ("PlainBytes", "[]uint8", base64.b64encode(payload.encode()).decode()),
            ("NamedText", f"{package}.Text", payload),
            ("NamedBytes", f"{package}.Bytes", base64.b64encode(payload.encode()).decode()),
        ):
            # Observe the actual destination, without requiring a separate
            # interpreted conversion. encoding/json carries byte slices as base64.
            steps.append(f01_eval(f"{package}.{name}", read_value=True))
            expected.append((type_name, value))
    records = f11_packages(files, steps)
    f01_success(records)
    for observation, (type_name, value) in zip(records[1:], expected):
        f01_value(observation, type_name, value)


def test_missing_packages_and_cross_file_error_locations(f11_packages):
    base = {"fixture.test/problem/a.go": "package problem\nvar Seed = 8\n",
            "fixture.test/problem/z.go": "package problem\nfunc Compute() int { return Seed + 3 }\n"}
    valid = f11_packages(base, [f01_eval('import "fixture.test/problem"'),
                               f01_eval("problem.Compute()", read_value=True)])
    f01_success(valid)
    f01_value(valid[-1], "int", 11)
    missing = f11_packages(base, [f01_eval('import "fixture.test/absent"')])[0]
    assert missing["error"] is not None, missing
    assert missing["missing_package"] is True, missing
    for source in ("package problem\nfunc Compute() int { return Missing(Seed) }\n",
                   "package problem\nvar Result = Missing + Seed\n"):
        files = dict(base)
        files["fixture.test/problem/z.go"] = source
        rejected = f11_packages(files, [f01_eval('import "fixture.test/problem"')])[0]
        f01_undefined_at(rejected, "fixture.test/problem/z.go", source, 2)
        assert rejected["missing_package"] is False, rejected


def test_native_and_source_location_precedence(f11_packages):
    source = lambda text: 'package choice\nvar Answer = "' + text + '"\n'
    path = "fixture.test/choice/choice.go"
    host = {path: source("host source")}
    bundled = {path: source("bundled source")}
    remote = {path: source("remote source")}
    stages = [
        (host, bundled, remote, {"fixture.test/choice": "native export"}, "native export"),
        (host, bundled, remote, {}, "host source"),
        ({}, bundled, remote, {}, "bundled source"),
        ({}, {}, remote, {}, "remote source"),
    ]
    for primary, library, modules, exports, expected in stages:
        records = f11_packages(
            primary, [f01_eval('import "fixture.test/choice"'),
                      f01_eval("choice.Answer", read_value=True)],
            bundled=library, remote=modules, native=exports)
        f01_success(records)
        f01_value(records[-1], "string", expected)
