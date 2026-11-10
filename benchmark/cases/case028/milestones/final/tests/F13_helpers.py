# feature: F13
"""Offline archive observations and real Go-download preparation."""

import base64
import json
import os
from pathlib import Path

import pytest

from _helpers import build_go, isolated_workspace, parse_json, run_process, write_files
from F01_helpers import f01_success, f01_value
from F12_helpers import F12Proxy, f12_downloaded, f12_unavailable


F13_HOST = r'''package main
import (
    "bytes"
    "encoding/json"
    "errors"
    "io/fs"
    "os"
    "strings"
    "github.com/zelviro-sh/zelviro/goparser"
    "github.com/zelviro-sh/zelviro/interp"
    "github.com/zelviro-sh/zelviro/lang/golang"
    "github.com/zelviro-sh/zelviro/modfs"
    "github.com/zelviro-sh/zelviro/stdlib"
    "github.com/zelviro-sh/zelviro/stdlib/stdmod"
)
type Archive struct { Module, Version string; Data []byte }
type Action struct { Op, Path string; Sources []string; Archive Archive }
type Request struct {
    Proxy, CacheDir string
    Offline, Bundled bool
    ReadDirs []string
    Actions []Action
}
type Observation struct {
    Error *string `json:"error"`
    MissingPackage bool `json:"missing_package"`
    NotExist bool `json:"not_exist"`
    Valid bool `json:"valid"`
    Type string `json:"type"`
    Value any `json:"value"`
    Data []byte `json:"data"`
    Entries map[string]bool `json:"entries"`
    Output string `json:"output"`
    Diagnostic string `json:"diagnostic"`
}
func main() {
    var r Request
    if err := json.NewDecoder(os.Stdin).Decode(&r); err != nil { panic(err) }
    remote := modfs.New(modfs.Options{Proxy:r.Proxy, Offline:r.Offline,
        CacheDir:r.CacheDir, ReadDirs:r.ReadDirs})
    defer remote.CloseIdleConnections()
    if r.Bundled {
        if err := remote.Inject(stdmod.ModulePath, stdmod.Version, stdlib.EmbeddedStd()); err != nil { panic(err) }
    }
    result := []Observation{}
    for _, a := range r.Actions {
        o := Observation{}
        var err error
        switch a.Op {
        case "inject":
            err = remote.Inject(a.Archive.Module, a.Archive.Version, a.Archive.Data)
        case "read":
            o.Data, err = fs.ReadFile(remote, a.Path)
        case "directory":
            var entries []fs.DirEntry
            entries, err = remote.ReadDir(a.Path)
            o.Entries = map[string]bool{}
            for _, entry := range entries { o.Entries[entry.Name()] = entry.IsDir() }
        case "eval":
            engine := interp.NewInterpreter(golang.GoSpec)
            engine.SetPkgfs(".")
            if r.Bundled { engine.SetStdlibFS(stdmod.FS(remote)) } else { engine.SetStdlibFS(os.DirFS(".")) }
            engine.SetRemoteFS(remote)
            var output, diagnostic bytes.Buffer
            engine.SetIO(strings.NewReader(""), &output, &diagnostic)
            for _, source := range a.Sources {
                value, evalErr := engine.Eval("offline.go", source)
                err = evalErr
                if err != nil { break }
                o.Valid = value.IsValid()
                if o.Valid { o.Type, o.Value = value.Type().String(), value.Interface() }
            }
            o.Output, o.Diagnostic = output.String(), diagnostic.String()
            engine.Close()
        default: panic("unknown offline observation operation")
        }
        if err != nil { message := err.Error(); o.Error = &message }
        o.MissingPackage = errors.Is(err, goparser.ErrPkgNotFound)
        o.NotExist = errors.Is(err, fs.ErrNotExist)
        result = append(result, o)
    }
    if err := json.NewEncoder(os.Stdout).Encode(result); err != nil { panic(err) }
}
'''


@pytest.fixture(scope="module")
def f13_tools():
    with isolated_workspace(overrides={"GOPROXY": "off", "ZELVIROCACHE": None,
                                       "ZELVIRO_DEBUG": None, "ZELVIRO_TRACE": None}) as build:
        source = write_files(build.root, {"observer.go": F13_HOST})["observer.go"]
        observer = build_go(["go"], source, cwd=Path.cwd(), env=build.env,
                            output=build.root / "observer", timeout=240).artifact
        cli = build_go(["go"], ".", cwd=Path.cwd(), env=build.env,
                       output=build.root / "cli", flags=("-buildvcs=false",), timeout=240).artifact

        def observe(work, actions, **options):
            result = run_process([observer], cwd=work.cwd, env=work.env,
                                 input=json.dumps(dict(Actions=actions, **options)), timeout=60)
            assert result.returncode == 0, result
            rows = parse_json(result.stdout)
            assert len(rows) == len(actions), rows
            return rows

        def cli_run(work, proxy, target, *, cache=None):
            env = dict(work.env, GOPROXY=proxy)
            env.pop("ZELVIROCACHE", None)
            if cache is not None:
                env["ZELVIROCACHE"] = str(cache)
            return run_process([cli, "run", target], cwd=work.cwd, env=env, timeout=60)

        yield observe, cli_run


def f13_injection(proxy, module, version):
    archive = (proxy.root / module / "@v" / f"{version}.zip").read_bytes()
    return {"Op": "inject", "Archive": {"Module": module, "Version": version,
            "Data": base64.b64encode(archive).decode()}}


def f13_expression(package, expression):
    return {"Op": "eval", "Sources": [f'import "{package}"', expression]}


def f13_go_download(work, proxy, module, versions):
    """Populate the secondary source with the actual Go command, not a replica."""
    env = dict(work.env, GOPROXY=proxy.url, GOSUMDB="off")
    for version in versions:
        result = run_process(["go", "mod", "download", "-json", f"{module}@{version}"],
                             cwd=work.cwd, env=env, timeout=60)
        assert result.returncode == 0, result
        report = parse_json(result.stdout)
        assert "Error" not in report, report
        assert Path(report["Zip"]).is_file(), report


def f13_snapshot(root):
    """Read every file, propagating filesystem errors instead of hiding them."""
    root = Path(root)
    try:
        root.stat()
    except FileNotFoundError:
        return {}  # The storage root itself has not been created.

    def failed_scan(error):
        raise error

    files = {}
    for directory, _, names in os.walk(root, onerror=failed_scan):
        for name in names:
            path = Path(directory) / name
            files[str(path.relative_to(root))] = path.read_bytes()
    return files


def f13_cli_value(result, expected):
    assert result.returncode == 0, result
    assert result.stdout == expected, result


def f13_cli_missing(result):
    assert result.returncode == 1, result
    assert result.stderr, result
