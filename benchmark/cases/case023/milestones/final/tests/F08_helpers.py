# feature: F08
"""Capture API adapters; transport and basic assertions come from earlier features."""

import json
from pathlib import Path

import pytest

from _helpers import build_c_driver, build_rust_driver, cargo_build, cargo_metadata, environment
from F01_helpers import C_API_SOURCE, operation, pattern_request


CAPTURE_SOURCE = r'''
use rivexlib::{Error, Regex, RegexOptions};
use rivexlib_algebra::RivexlibError;
use rivexlib_parser::ast::ErrorKind;
use serde_json::{json, Value};
use std::io::{self, Read};

fn capture_error(error: Error) -> Value {
    let category = match &error {
        Error::Algebra(RivexlibError::UnsupportedPattern) => "unsupported",
        Error::Parse(p) => match p.kind {
            ErrorKind::CaptureGroupInLookaround |
            ErrorKind::UnsupportedBackreference |
            ErrorKind::UnsupportedLazyQuantifier |
            ErrorKind::UnsupportedRivexlibRegex => "unsupported",
            _ => "invalid_pattern",
        },
        _ => "other",
    };
    json!({"ok": false, "error": {
        "category": category, "diagnostic": format!("{error:?}")
    }})
}
fn capture_run(spec: &Value) -> Value {
    let pattern = spec["pattern"].as_str().unwrap();
    let compiled = match spec.get("implicit") {
        None => Regex::new(pattern),
        Some(v) => Regex::with_options(pattern,
            RegexOptions::default().implicit_captures(v.as_bool().unwrap())),
    };
    let re = match compiled {
        Ok(re) => re,
        Err(e) => return capture_error(e),
    };
    let results: Vec<Value> = spec["actions"].as_array().unwrap().iter().map(|action| {
        let value = match action["op"].as_str().unwrap() {
            "metadata" => {
                let names = action["names"].as_array().unwrap();
                json!({"names": re.capture_names(), "indices": names.iter()
                    .map(|name| re.capture_index_for_name(name.as_str().unwrap()))
                    .collect::<Vec<_>>()})
            },
            "captures_all" | "lookup" => {
                let bytes: Vec<u8> = serde_json::from_value(action["input"].clone()).unwrap();
                match re.captures_all(&bytes) {
                    Err(e) => return capture_error(e),
                    Ok(caps) => {
                        if action["op"] == "captures_all" {
                            json!(caps.iter().map(|c| c.spans()).collect::<Vec<_>>())
                        } else {
                            json!(caps.iter().map(|c| json!({
                                "by_index": action["indices"].as_array().unwrap().iter()
                                    .map(|i| c.get(i.as_u64().unwrap() as usize)
                                        .map(|m| [m.start, m.end])).collect::<Vec<_>>(),
                                "by_name": action["names"].as_array().unwrap().iter()
                                    .map(|n| c.name(n.as_str().unwrap())
                                        .map(|m| [m.start, m.end])).collect::<Vec<_>>()
                            })).collect::<Vec<_>>())
                        }
                    }
                }
            },
            other => panic!("Unknown capture operation: {other}"),
        };
        json!({"ok": true, "value": value})
    }).collect();
    json!({"ok": true, "results": results})
}
fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let specs: Vec<Value> = serde_json::from_str(&input).unwrap();
    let output: Vec<Value> = specs.iter().map(capture_run).collect();
    println!("{}", serde_json::to_string(&output).unwrap());
}
'''

BOUNDED_CAPTURE_SOURCE = C_API_SOURCE + r'''
capture_slots = bind_c_function(library, "rivexlib_capture_slots",
    argtypes=[ctypes.c_void_p], restype=ctypes.c_size_t)
captures_all = bind_c_function(library, "rivexlib_captures_all",
    argtypes=[ctypes.c_void_p, u8p, ctypes.c_size_t, sizep, ctypes.c_size_t],
    restype=ctypes.c_ssize_t)
output = []
for spec in json.load(sys.stdin):
    pattern = spec["pattern"].encode("utf-8")
    handle = compile_pattern(byte_buffer(pattern), len(pattern))
    if not handle:
        output.append({"ok": False, "diagnostic": diagnostic()})
        continue
    try:
        observations = []
        data = spec["input"]
        for capacity in spec["capacities"]:
            out = (ctypes.c_size_t * max(1, capacity))(
                *([spec["initial"]] * max(1, capacity)))
            count = captures_all(handle, byte_buffer(data), len(data), out, capacity)
            row = {"count": count, "storage": list(out)[:capacity]}
            if count < 0:
                row["diagnostic"] = diagnostic()
            observations.append(row)
        output.append({"ok": True, "slots": capture_slots(handle),
                       "absent": ctypes.c_size_t(-1).value, "results": observations})
    finally:
        free_pattern(handle)
json.dump(output, sys.stdout)
'''


@pytest.fixture(scope="session")
def capture_api(tmp_path_factory):
    manifest = Path.cwd() / "Cargo.toml"
    env = environment({"CARGO_NET_OFFLINE": "true"})
    metadata = cargo_metadata(manifest, env=env).value
    dependencies = 'serde_json = "1"\n'
    for name in ("rivexlib-algebra", "rivexlib-parser"):
        packages = [p for p in metadata["packages"] if p["name"] == name
                    and p["id"] in metadata["workspace_members"]]
        assert len(packages) == 1, (name, packages)
        directory = str(Path(packages[0]["manifest_path"]).parent)
        dependencies += f'{name} = {{ path = {json.dumps(directory)} }}\n'
    return build_rust_driver(
        tmp_path_factory.mktemp("f08-rust") / "driver", CAPTURE_SOURCE,
        product_manifest=manifest, package="rivexlib",
        features=("experimental_capture_groups",),
        dependencies_toml=dependencies, env=env, timeout=900.0,
    )


@pytest.fixture(scope="session")
def bounded_captures(tmp_path_factory):
    root = tmp_path_factory.mktemp("f08-c")
    env = environment({"CARGO_NET_OFFLINE": "true"})
    build = cargo_build(Path.cwd() / "Cargo.toml", target_dir=root / "target",
                        package="rivexlib-ffi", features=("experimental_capture_groups",),
                        env=env, timeout=900.0)
    return build_c_driver(root / "driver", BOUNDED_CAPTURE_SOURCE,
                          library=build.artifact("rivexlib-ffi", kind="cdylib"), env=env)


def capture_case(pattern, rows, *, implicit=None):
    """Use supplied expected spans; never derive them from another product call."""
    request = pattern_request(pattern, [operation("captures_all", data) for data, _ in rows])
    if implicit is not None:
        request["implicit"] = implicit
    return request, [spans for _, spans in rows]


def assert_capture_refusals(driver, patterns, category):
    """Accept a classified refusal at construction or capture evaluation."""
    requests = [pattern_request(p, [operation("captures_all", b"aab")]) for p in patterns]
    observed = driver.json(requests).value
    assert len(observed) == len(requests), observed
    for request, item in zip(requests, observed):
        if item["ok"] is True:
            assert len(item["results"]) == 1, item
            item = item["results"][0]
        assert item["ok"] is False, (request, item)
        assert item["error"]["category"] == category, (request, item)
