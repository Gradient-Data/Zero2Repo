# feature: F10
"""Opaque persistence transport through real public Rust entries."""

from pathlib import Path

import pytest

from _helpers import build_rust_driver, environment
from F01_helpers import successful_values


PERSISTENCE_SOURCE = r'''
use rivexlib::{Error, Regex, RegexOptions, RegexSet, UnicodeMode};
use serde_json::{json, Value};
use std::io::{self, Read};

fn persistence_error(e: Error) -> Value {
    let category = match &e {
        Error::Serialize(_) => "serialize",
        _ => "other",
    };
    json!({"ok": false, "error": {
        "category": category, "diagnostic": format!("{e:?}")
    }})
}
fn persistence_actions(re: &Regex, actions: &Value) -> Vec<Value> {
    actions.as_array().unwrap().iter().map(|action| {
        let value = match action["op"].as_str().unwrap() {
            "metadata" => json!(re.capture_names()),
            "find_all" => {
                let bytes: Vec<u8> = serde_json::from_value(action["input"].clone()).unwrap();
                match re.find_all(&bytes) {
                    Ok(ms) => json!(ms.into_iter().map(|m| [m.start, m.end]).collect::<Vec<_>>()),
                    Err(e) => return persistence_error(e),
                }
            },
            "captures_all" => {
                let bytes: Vec<u8> = serde_json::from_value(action["input"].clone()).unwrap();
                match re.captures_all(&bytes) {
                    Ok(cs) => json!(cs.iter().map(|c| json!({
                        "spans": c.spans(),
                        "by_name": action["names"].as_array().unwrap().iter()
                            .map(|n| c.name(n.as_str().unwrap()).map(|m| [m.start, m.end]))
                            .collect::<Vec<_>>()
                    })).collect::<Vec<_>>()),
                    Err(e) => return persistence_error(e),
                }
            },
            other => panic!("Unknown persistence action: {other}"),
        };
        json!({"ok": true, "value": value})
    }).collect()
}
fn persistence_run(spec: &Value) -> Value {
    if spec["op"] == "load" {
        let bytes: Vec<u8> = serde_json::from_value(spec["saved"].clone()).unwrap();
        return match Regex::load(&bytes) {
            Ok(re) => json!({"ok": true, "results": persistence_actions(&re, &spec["actions"])}),
            Err(e) => persistence_error(e),
        };
    }
    if spec["op"] == "save_set" {
        let patterns: Vec<String> = serde_json::from_value(spec["patterns"].clone()).unwrap();
        let set = RegexSet::new(&patterns).unwrap();
        let results = persistence_actions(set.regex(), &spec["actions"]);
        let saved = match set.regex().dump() {
            Ok(bytes) => json!({"ok": true, "value": bytes}),
            Err(e) => persistence_error(e),
        };
        return json!({"ok": true, "results": results, "saved": saved});
    }
    assert_eq!(spec["op"], "save");
    let mut opts = RegexOptions::default().hardened(false);
    if let Some(mode) = spec.get("mode") {
        opts = opts.unicode(match mode.as_str().unwrap() {
            "Ascii" => UnicodeMode::Ascii,
            "Default" => UnicodeMode::Default,
            "Full" => UnicodeMode::Full,
            "Javascript" => UnicodeMode::Javascript,
            other => panic!("Unknown character mode: {other}"),
        });
    }
    if let Some(v) = spec.get("case_insensitive") {
        opts = opts.case_insensitive(v.as_bool().unwrap());
    }
    let re = Regex::with_options(spec["pattern"].as_str().unwrap(), opts).unwrap();
    let results = persistence_actions(&re, &spec["actions"]);
    let saved = match re.dump() {
        Ok(bytes) => json!({"ok": true, "value": bytes}),
        Err(e) => persistence_error(e),
    };
    json!({"ok": true, "results": results, "saved": saved})
}
fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let specs: Vec<Value> = serde_json::from_str(&input).unwrap();
    let out: Vec<Value> = specs.iter().map(persistence_run).collect();
    println!("{}", serde_json::to_string(&out).unwrap());
}
'''


@pytest.fixture(scope="session")
def persistence_api(tmp_path_factory):
    return build_rust_driver(
        tmp_path_factory.mktemp("f10-persistence") / "driver", PERSISTENCE_SOURCE,
        product_manifest=Path.cwd() / "Cargo.toml", package="rivexlib",
        features=("serialize", "experimental_capture_groups", "regex_set"),
        dependencies_toml='serde_json = "1"\n',
        env=environment({"CARGO_NET_OFFLINE": "true"}), timeout=900.0,
    )


def save_observed(driver, request, expected):
    """Observe the live pattern and return its unmodified save result."""
    observation = driver.json([dict(request, op="save")]).value
    assert len(observation) == 1, observation
    assert successful_values(observation[0]) == expected, observation
    return observation[0]["saved"]


def saved_bytes(saved):
    """Read a successful opaque Vec<u8>; never interpret its encoding."""
    assert saved["ok"] is True, saved
    data = saved["value"]
    assert isinstance(data, list) and all(type(b) is int and 0 <= b <= 255 for b in data)
    return data


def restore_observed(driver, data, actions, expected):
    """A fresh process receives only saved bytes and new observation actions."""
    observation = driver.json([{"op": "load", "saved": data, "actions": actions}]).value
    assert len(observation) == 1, observation
    assert successful_values(observation[0]) == expected, observation
