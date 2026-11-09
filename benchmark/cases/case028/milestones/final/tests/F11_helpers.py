# feature: F11
"""Real directory-backed source imports and independent Go package oracles."""

import json
from pathlib import Path

import pytest

from _helpers import build_go, isolated_workspace, parse_json, run_process, write_files
from F01_helpers import f01_eval, f01_success, f01_value, f01_undefined_at


F11_OBSERVER = r'''package main
import (
    "bytes"
    "encoding/json"
    "errors"
    "go/build"
    "os"
    "reflect"
    "strings"
    "github.com/zelviro-sh/zelviro/goparser"
    "github.com/zelviro-sh/zelviro/interp"
    "github.com/zelviro-sh/zelviro/lang/golang"
    "github.com/zelviro-sh/zelviro/scan"
    "github.com/zelviro-sh/zelviro/stdlib"
    _ "github.com/zelviro-sh/zelviro/stdlib/all"
)
type Step struct { Label, Source string; ReadValue bool }
type Request struct {
    Host, Bundled, Remote, GOOS, GOARCH string
    Tags []string
    Native map[string]string
    Steps []Step
    SelectDir string
    Candidates []string
}
type Observation struct {
    Valid bool `json:"valid"`
    Type string `json:"type"`
    Value any `json:"value"`
    Error *string `json:"error"`
    Unfinished bool `json:"unfinished"`
    UndefinedLocation *string `json:"undefined_location"`
    MissingPackage bool `json:"missing_package"`
    Output string `json:"output"`
    Diagnostic string `json:"diagnostic"`
}
func main() {
    var r Request
    if err := json.NewDecoder(os.Stdin).Decode(&r); err != nil { panic(err) }
    if r.SelectDir != "" {
        ctx := build.Default
        if r.GOOS != "" { ctx.GOOS, ctx.GOARCH = r.GOOS, r.GOARCH }
        ctx.BuildTags = append([]string{"purego", "safe", "nethttpomithttp2"}, r.Tags...)
        selected := []string{}
        for _, name := range r.Candidates {
            ok, err := ctx.MatchFile(r.SelectDir, name)
            if err != nil { panic(err) }
            if ok && !strings.HasSuffix(name, "_test.go") { selected = append(selected, name) }
        }
        if err := json.NewEncoder(os.Stdout).Encode(selected); err != nil { panic(err) }
        return
    }
    engine := interp.NewInterpreter(golang.GoSpec)
    defer engine.Close()
    engine.ImportPackageValues(stdlib.Values)
    engine.SetPkgfs(r.Host)
    engine.SetStdlibFS(os.DirFS(r.Bundled))
    engine.SetRemoteFS(os.DirFS(r.Remote))
    if r.GOOS != "" { engine.SetBuildContext(r.GOOS, r.GOARCH) }
    engine.AddBuildTags(r.Tags...)
    for name, answer := range r.Native {
        engine.ImportPackageValues(map[string]map[string]reflect.Value{
            name: {"Answer": reflect.ValueOf(answer)},
        })
    }
    var output, diagnostic bytes.Buffer
    engine.SetIO(strings.NewReader(""), &output, &diagnostic)
    observations := []Observation{}
    for _, step := range r.Steps {
        v, err := engine.Eval(step.Label, step.Source)
        o := Observation{Valid: v.IsValid()}
        if err != nil {
            text := err.Error()
            o.Error = &text
            o.Unfinished = errors.Is(err, scan.ErrBlock)
            o.MissingPackage = errors.Is(err, goparser.ErrPkgNotFound)
            var undefined goparser.ErrUndefined
            if errors.As(err, &undefined) { o.UndefinedLocation = &undefined.Loc }
        }
        if o.Valid && step.ReadValue { o.Type, o.Value = v.Type().String(), v.Interface() }
        o.Output, o.Diagnostic = output.String(), diagnostic.String()
        // Encode now: a later Eval may mutate a map or slice returned earlier.
        data, err := json.Marshal(o); if err != nil { panic(err) }
        var snapshot Observation
        if err := json.Unmarshal(data, &snapshot); err != nil { panic(err) }
        observations = append(observations, snapshot)
    }
    if err := json.NewEncoder(os.Stdout).Encode(observations); err != nil { panic(err) }
}
'''


@pytest.fixture(scope="module")
def f11_packages():
    product = Path.cwd()
    with isolated_workspace(overrides={"GOPROXY": "off", "ZELVIRO_DEBUG": None,
                                       "ZELVIRO_TRACE": None}) as workspace:
        source = write_files(workspace.cwd, {"observer.go": F11_OBSERVER})["observer.go"]
        observer = build_go(["go"], source, cwd=product,
                            output=workspace.root / "observer", env=workspace.env,
                            timeout=240).artifact
        serial = 0

        def run(files, steps, *, bundled=None, remote=None, native=None,
                target=None, tags=(), compare_source=None, candidates=None):
            nonlocal serial
            serial += 1
            root = workspace.cwd / str(serial)
            locations = {}
            for name, content in (("Host", files), ("Bundled", bundled or {}),
                                  ("Remote", remote or {})):
                directory = root / name
                directory.mkdir(parents=True)
                write_files(directory, content)
                locations[name] = str(directory)
            request = dict(locations, Steps=steps, Tags=list(tags), Native=native or {})
            if target is not None:
                request.update(GOOS=target[0], GOARCH=target[1])
            process = run_process([observer], cwd=root, env=workspace.env,
                                  input=json.dumps(request), timeout=60)
            assert process.returncode == 0, process
            observations = parse_json(process.stdout)
            assert len(observations) == len(steps), observations
            if compare_source is not None:
                module = Path(locations["Host"]) / "fixture.test"
                write_files(module, {"go.mod": "module fixture.test\n\ngo 1.26\n",
                                     "main.go": compare_source})
                executable = build_go(["go"], ".", cwd=module,
                                      output=root / "native", env=workspace.env,
                                      timeout=240).artifact
                expected = run_process([executable], cwd=root, env=workspace.env, timeout=60)
                assert expected.returncode == 0, expected
                f01_success(observations)
                assert observations[-1]["output"].encode() == expected.stdout, (observations, expected)
            if candidates is not None:
                request.update(SelectDir=str(Path(locations["Host"]) / "fixture.test/selection"),
                               Candidates=candidates)
                selection = run_process([observer], cwd=root, env=workspace.env,
                                        input=json.dumps(request), timeout=60)
                assert selection.returncode == 0, selection
                return observations, parse_json(selection.stdout)
            return observations

        yield run
