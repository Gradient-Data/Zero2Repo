# feature: F05
"""Independent adjacency expectations at the boundaries promised by FP-05.03."""

import json
from pathlib import Path

import pytest

from _helpers import build_rust_driver, cargo_metadata, environment
from F01_helpers import operation
from F03_helpers import option_request, scalar_spans


BOUNDARY_COMPILATION_SOURCE = r'''
use rivexlib::{Error, Regex};
use rivexlib_algebra::RivexlibError;
use rivexlib_parser::ast::ErrorKind;
use serde_json::{json, Value};
use std::io::{self, Read};

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let specs: Vec<Value> = serde_json::from_str(&input).unwrap();
    let output: Vec<Value> = specs.iter().map(|spec| {
        match Regex::new(spec["pattern"].as_str().unwrap()) {
            Ok(regex) => {
                let results: Vec<Value> = spec["actions"].as_array().unwrap().iter().map(|action| {
                    assert_eq!(action["op"].as_str().unwrap(), "find_all");
                    let input: Vec<u8> = serde_json::from_value(action["input"].clone()).unwrap();
                    match regex.find_all(&input) {
                        Ok(matches) => json!({"ok": true, "value": matches.into_iter()
                            .map(|m| [m.start, m.end]).collect::<Vec<_>>()}),
                        Err(error) => json!({"ok": false, "error": {
                            "diagnostic": format!("{error:?}")
                        }}),
                    }
                }).collect();
                json!({"ok": true, "results": results})
            },
            Err(error) => {
                let category = match &error {
                    Error::Algebra(RivexlibError::UnsupportedPattern) => "unsupported",
                    Error::Parse(p) => match p.kind {
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
        }
    }).collect();
    println!("{}", serde_json::to_string(&output).unwrap());
}
'''


@pytest.fixture(scope="session")
def boundary_compilation(tmp_path_factory):
    """Observe the additional public algebra error carrier without parsing prose."""
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
        tmp_path_factory.mktemp("f05-compile") / "driver", BOUNDARY_COMPILATION_SOURCE,
        product_manifest=manifest, package="rivexlib", dependencies_toml=dependencies,
        env=env,
    )


def boundary_atom_cases(text, atom, accepts, mode, is_word):
    """Constrain one-unit atoms using independent membership and adjacency."""
    units = list(text.encode()) if mode == "Ascii" else list(text)
    spans = ([[i, i + 1] for i in range(len(units))] if mode == "Ascii"
             else scalar_spans(text))
    membership = ([is_word(chr(unit)) for unit in units] if mode == "Ascii"
                  else [is_word(unit) for unit in units])
    actions = [operation("find_all", text.encode())]
    for before, after in ((True, None), (False, None), (None, True),
                          (None, False), (True, True), (False, False)):
        pattern = (("\\b" if before else "\\B") if before is not None else "")
        pattern += atom
        pattern += (("\\b" if after else "\\B") if after is not None else "")
        expected = []
        for i, unit in enumerate(units):
            if not accepts(chr(unit) if mode == "Ascii" else unit):
                continue
            left = membership[i - 1] if i else False
            right = membership[i + 1] if i + 1 < len(units) else False
            begins = left != membership[i]
            ends = membership[i] != right
            if (before is None or begins == before) and (after is None or ends == after):
                expected.append(spans[i])
        yield option_request(pattern, actions, mode), [expected]
