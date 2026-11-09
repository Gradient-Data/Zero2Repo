# feature: F01
"""Build and drive a Go host observing the public embedding API."""

from pathlib import Path
import json

import pytest

from _helpers import build_go, isolated_workspace, parse_json, read_bytes, run_process, write_files


F01_OBSERVER_SOURCE = r'''package main

import (
    "bytes"
    "encoding/json"
    "errors"
    "os"
    "strings"

    "github.com/zelviro-sh/zelviro/goparser"
    "github.com/zelviro-sh/zelviro/interp"
    "github.com/zelviro-sh/zelviro/lang/golang"
    "github.com/zelviro-sh/zelviro/scan"
    "github.com/zelviro-sh/zelviro/stdlib"
    _ "github.com/zelviro-sh/zelviro/stdlib/all"
)

type Action struct {
    Op string
    Session string
    Label string
    Source string
    Input string
    HostStdio bool
    ReadValue bool
}
type Session struct {
    Interpreter *interp.Interp
    Input *strings.Reader
    Output, Diagnostic *bytes.Buffer
}
type Observation struct {
    Valid bool `json:"valid"`
    Type string `json:"type"`
    Value any `json:"value"`
    Error *string `json:"error"`
    Unfinished bool `json:"unfinished"`
    UndefinedLocation *string `json:"undefined_location"`
    Output string `json:"output"`
    Diagnostic string `json:"diagnostic"`
}

func main() {
    if len(os.Args) != 3 { panic("expected request and observation file paths") }
    data, err := os.ReadFile(os.Args[1]); if err != nil { panic(err) }
    var actions []Action
    if err := json.Unmarshal(data, &actions); err != nil { panic(err) }
    sessions := map[string]*Session{}
    observations := []Observation{}
    for _, a := range actions {
        s := sessions[a.Session]
        switch a.Op {
        case "new":
            if s != nil { panic("duplicate session") }
            s = &Session{Interpreter: interp.NewInterpreter(golang.GoSpec)}
            defer s.Interpreter.Close()
            s.Interpreter.ImportPackageValues(stdlib.Values)
            sessions[a.Session] = s
        case "set_io", "eval":
            if s == nil { panic("unknown session") }
        default:
            panic("unknown action")
        }
        if a.Op == "new" || a.Op == "set_io" {
            s.Input = strings.NewReader(a.Input)
            s.Output = &bytes.Buffer{}
            s.Diagnostic = &bytes.Buffer{}
            s.Interpreter.SetIO(s.Input, s.Output, s.Diagnostic)
            if a.Op == "new" && a.HostStdio { s.Interpreter.UseHostStdio() }
        }
        var o Observation
        if a.Op == "eval" {
            v, err := s.Interpreter.Eval(a.Label, a.Source)
            if err != nil {
                text := err.Error()
                o.Error = &text
                o.Unfinished = errors.Is(err, scan.ErrBlock)
                var undefined goparser.ErrUndefined
                if errors.As(err, &undefined) {
                    o.UndefinedLocation = &undefined.Loc
                }
            }
            o.Valid = err == nil && v.IsValid()
            if o.Valid && a.ReadValue {
                o.Type = v.Type().String()
                o.Value = v.Interface()
            }
        }
        o.Output = s.Output.String()
        o.Diagnostic = s.Diagnostic.String()
        observations = append(observations, o)
    }
    data, err = json.Marshal(observations); if err != nil { panic(err) }
    if err := os.WriteFile(os.Args[2], data, 0600); err != nil { panic(err) }
}
'''


@pytest.fixture(scope="module")
def f01_driver():
    """Compile once in the product module; each call runs a fresh Go host."""
    product = Path.cwd()
    assert (product / "go.mod").is_file(), "Run from the product module directory"
    with isolated_workspace(overrides={"GOPROXY": "off", "ZELVIRO_DEBUG": None,
                                       "ZELVIRO_TRACE": None}) as workspace:
        source = write_files(workspace.cwd, {"observer.go": F01_OBSERVER_SOURCE})["observer.go"]
        binary = build_go(["go"], source, cwd=product,
                          output=workspace.root / "observer", env=workspace.env,
                          timeout=240).artifact
        count = 0

        def observe(actions, *, host_input=b""):
            nonlocal count
            count += 1
            request = write_files(workspace.cwd, {
                f"request-{count}.json": json.dumps(actions)
            })[f"request-{count}.json"]
            response = workspace.cwd / f"response-{count}.json"
            process = run_process([binary, request, response], cwd=workspace.cwd,
                                  env=workspace.env, input=host_input, timeout=45)
            assert process.returncode == 0, process
            observations = parse_json(read_bytes(response))
            assert len(observations) == len(actions), observations
            return observations, process

        yield observe


def f01_eval(source, *, session="a", label="snippet.go", read_value=False):
    return {"Op": "eval", "Session": session, "Label": label, "Source": source,
            "ReadValue": read_value}


def f01_value(observation, type_name, value):
    assert observation["error"] is None, observation
    assert observation["valid"] is True, observation
    assert observation["type"] == type_name, observation
    assert observation["value"] == value, observation


def f01_success(observations):
    for observation in observations:
        assert observation["error"] is None, observation


def f01_undefined_at(observation, source_label, source, line_number):
    """Read the public ErrUndefined.Loc field, not the diagnostic prose."""
    assert observation["error"] is not None, observation
    assert observation["unfinished"] is False, observation
    location = observation["undefined_location"]
    assert location is not None, observation
    parts = location.rsplit(":", 2)
    assert len(parts) == 3, observation
    label, line, column = parts
    assert label == source_label, observation
    assert int(line) == line_number, observation
    affected_line = source.splitlines()[line_number - 1]
    first_column = len(affected_line) - len(affected_line.lstrip()) + 1
    # The baseline may locate the declaration or call, rather than the missing
    # identifier itself. Accept any position in the offending construct.
    assert first_column <= int(column) <= len(affected_line) + 1, observation
