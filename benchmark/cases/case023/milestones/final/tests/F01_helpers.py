# feature: F01
"""Public matching drivers; reuse F00 for build and process observation."""

import json
from pathlib import Path

import pytest

from _helpers import (
    InterfaceUnavailable, build_c_driver, build_rust_driver, cargo_build,
    cargo_metadata, environment,
)


MATCHING_SOURCE = r'''
use rivexlib::{Error, Regex, RegexOptions};
use rivexlib_parser::ast::ErrorKind;
use serde_json::{json, Value};
use std::io::{self, Read};

fn error(e: Error) -> Value {
    let category = match &e {
        Error::Parse(p) => match p.kind {
            ErrorKind::UnsupportedBackreference |
            ErrorKind::UnsupportedLazyQuantifier |
            ErrorKind::UnsupportedRivexlibRegex => "unsupported",
            _ => "invalid_pattern",
        },
        _ => "other",
    };
    json!({"category": category, "diagnostic": format!("{e:?}")})
}
fn result<T: serde::Serialize>(r: Result<T, Error>) -> Value {
    match r {
        Ok(value) => json!({"ok": true, "value": value}),
        Err(e) => json!({"ok": false, "error": error(e)}),
    }
}
fn run(spec: &Value) -> Value {
    let pattern = spec["pattern"].as_str().unwrap();
    let compiled = match spec.get("unbounded") {
        None => Regex::new(pattern),
        Some(v) => Regex::with_options(pattern,
            RegexOptions::default().unbounded_size(v.as_bool().unwrap())),
    };
    let regex = match compiled {
        Ok(r) => r,
        Err(e) => return json!({"ok": false, "error": error(e)}),
    };
    let mut results = Vec::new();
    for action in spec["actions"].as_array().unwrap() {
        let bytes: Vec<u8> = serde_json::from_value(action["input"].clone()).unwrap();
        let value = match action["op"].as_str().unwrap() {
            "find_all" => result(regex.find_all(&bytes).map(|ms|
                ms.into_iter().map(|m| [m.start, m.end]).collect::<Vec<_>>())),
            "is_match" => result(regex.is_match(&bytes)),
            "find_anchored" => result(regex.find_anchored(&bytes)
                .map(|m| m.map(|m| [m.start, m.end]))),
            "is_full_match" => result(regex.is_full_match(&bytes)),
            op => panic!("Unknown driver operation: {op}"),
        };
        results.push(value);
    }
    json!({"ok": true, "results": results})
}
fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let specs: Vec<Value> = serde_json::from_str(&input).unwrap();
    // The public nesting limit is tested with ample stack, as in the upstream
    // public integration tests; stack size is driver infrastructure, not a verdict.
    let out = std::thread::Builder::new().stack_size(64 * 1024 * 1024)
        .spawn(move || specs.iter().map(run).collect::<Vec<_>>())
        .unwrap().join().unwrap();
    println!("{}", serde_json::to_string(&out).unwrap());
}
'''


C_API_SOURCE = r'''
import json
import sys

u8p = ctypes.POINTER(ctypes.c_uint8)
sizep = ctypes.POINTER(ctypes.c_size_t)
compile_pattern = bind_c_function(library, "rivexlib_compile",
    argtypes=[u8p, ctypes.c_size_t], restype=ctypes.c_void_p)
free_pattern = bind_c_function(library, "rivexlib_free",
    argtypes=[ctypes.c_void_p], restype=None)
find_all = bind_c_function(library, "rivexlib_find_all",
    argtypes=[ctypes.c_void_p, u8p, ctypes.c_size_t, sizep, ctypes.c_size_t],
    restype=ctypes.c_ssize_t)
last_error = bind_c_function(library, "rivexlib_last_error",
    argtypes=[u8p, ctypes.c_size_t], restype=ctypes.c_size_t)

def byte_buffer(data):
    return (ctypes.c_uint8 * max(1, len(data)))(*data)

def diagnostic():
    probe = byte_buffer([])
    length = last_error(probe, 0)
    buf = byte_buffer([0] * length)
    received = last_error(buf, length)
    assert received == length, (length, received)
    return list(buf)[:length]

'''


BOUNDED_SOURCE = C_API_SOURCE + r'''
output = []
for spec in json.load(sys.stdin):
    pattern = spec["pattern"].encode("utf-8")
    handle = compile_pattern(byte_buffer(pattern), len(pattern))
    if not handle:
        output.append({"ok": False, "diagnostic": diagnostic()})
        continue
    try:
        data = spec["input"]
        observations = []
        for capacity in spec["capacities"]:
            # Initialize caller-owned storage to observe unchanged incomplete
            # slots. No invalid pointer or out-of-bounds access is exercised.
            out = (ctypes.c_size_t * max(1, capacity))(
                *([spec["initial"]] * max(1, capacity)))
            count = find_all(handle, byte_buffer(data), len(data), out, capacity)
            observation = {"count": count, "storage": list(out)[:capacity]}
            if count < 0:
                observation["diagnostic"] = diagnostic()
            observations.append(observation)
        output.append({"ok": True, "results": observations})
    finally:
        free_pattern(handle)
json.dump(output, sys.stdout)
'''


def matching_driver(directory, product_manifest):
    """Build the real Rust public API adapter using Cargo package metadata."""
    env = environment({"CARGO_NET_OFFLINE": "true"})
    metadata = cargo_metadata(product_manifest, env=env)
    parsers = [p for p in metadata.value["packages"]
               if p["name"] == "rivexlib-parser"
               and p["id"] in metadata.value["workspace_members"]]
    if len(parsers) != 1:
        raise InterfaceUnavailable("Expected the public rivexlib-parser error types")
    parser_dir = str(Path(parsers[0]["manifest_path"]).parent)
    dependencies = (
        'serde = { version = "1", features = ["derive"] }\n'
        'serde_json = "1"\n'
        f'rivexlib-parser = {{ path = {json.dumps(parser_dir)} }}\n'
    )
    return build_rust_driver(directory, MATCHING_SOURCE,
                             product_manifest=product_manifest, package="rivexlib",
                             dependencies_toml=dependencies, env=env)


@pytest.fixture(scope="session")
def matching(tmp_path_factory):
    return matching_driver(tmp_path_factory.mktemp("f01-rust") / "driver",
                           Path.cwd() / "Cargo.toml")


@pytest.fixture(scope="session")
def matching_library(tmp_path_factory):
    root = tmp_path_factory.mktemp("f01-c")
    env = environment({"CARGO_NET_OFFLINE": "true"})
    build = cargo_build(Path.cwd() / "Cargo.toml", target_dir=root / "target",
                        package="rivexlib-ffi", env=env)
    return root, build.artifact("rivexlib-ffi", kind="cdylib"), env


@pytest.fixture(scope="session")
def bounded_matching(matching_library):
    root, library, env = matching_library
    return build_c_driver(root / "bounded", BOUNDED_SOURCE, library=library, env=env)


@pytest.fixture(scope="session")
def byte_compilation(matching_library):
    root, library, env = matching_library
    return build_c_driver(root / "compile", COMPILATION_SOURCE, library=library, env=env)


def operation(name, data):
    """Encode bytes without text conversion, replacement, or normalization."""
    return {"op": name, "input": list(data)}


def pattern_request(pattern, actions=(), *, unbounded=None):
    spec = {"pattern": pattern, "actions": list(actions)}
    if unbounded is not None:
        spec["unbounded"] = unbounded
    return spec


def successful_values(observation):
    """Read successful results; errors never become no-match sentinels."""
    assert observation["ok"] is True, observation
    results = []
    for item in observation["results"]:
        assert item["ok"] is True, item
        results.append(item["value"])
    return results


def assert_success_cases(driver, cases):
    """Run public requests and compare complete successful result values."""
    requests = [request for request, expected in cases]
    observations = driver.json(requests).value
    assert len(observations) == len(cases), observations
    for (request, expected), observation in zip(cases, observations):
        assert successful_values(observation) == expected, (request, observation, expected)


def assert_rejections(driver, patterns, category, *, unbounded=None):
    """Check the positive public failure carrier, collecting every mismatch."""
    requests = [pattern_request(p, unbounded=unbounded) for p in patterns]
    observations = driver.json(requests).value
    assert len(observations) == len(patterns), observations
    failures = []
    for pattern, observation in zip(patterns, observations):
        if observation["ok"] is not False:
            failures.append((pattern, observation))
        elif observation["error"]["category"] != category:
            failures.append((pattern, observation))
    assert not failures, failures


COMPILATION_SOURCE = C_API_SOURCE + r'''
output = []
for spec in json.load(sys.stdin):
    pattern = spec["pattern_bytes"]
    handle = compile_pattern(byte_buffer(pattern), len(pattern))
    if not handle:
        detail = diagnostic()
        output.append({"ok": False, "diagnostic": detail})
        continue
    try:
        data = spec["input"]
        storage = (ctypes.c_size_t * 2)()
        count = find_all(handle, byte_buffer(data), len(data), storage, 2)
        observation = {"ok": True, "count": count, "storage": list(storage)}
        if count < 0:
            observation["diagnostic"] = diagnostic()
        output.append(observation)
    finally:
        free_pattern(handle)
json.dump(output, sys.stdout)
'''
