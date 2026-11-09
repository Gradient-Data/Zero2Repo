# feature: F09
"""Thin public collection adapter; builds and observations reuse earlier helpers."""

from pathlib import Path

import pytest

from _helpers import build_rust_driver, environment
from F01_helpers import operation


SET_SOURCE = r'''
use rivexlib::{Error, RegexSet, RegexOptions, UnicodeMode};
use serde_json::{json, Value};
use std::io::{self, Read};

fn set_error(e: Error) -> Value {
    let (category, index) = match &e {
        Error::SetMember(i, _) => ("set_member", Some(*i)),
        Error::Parse(_) => ("invalid_pattern", None),
        _ => ("other", None),
    };
    json!({"ok": false, "error": {
        "category": category, "index": index, "diagnostic": format!("{e:?}")
    }})
}
fn set_run(spec: &Value) -> Value {
    let patterns: Vec<String> = serde_json::from_value(spec["patterns"].clone()).unwrap();
    let compiled = if let Some(options) = spec.get("options") {
        let mut opts = RegexOptions::default();
        if let Some(v) = options.get("mode") {
            opts = opts.unicode(match v.as_str().unwrap() {
                "Ascii" => UnicodeMode::Ascii,
                "Default" => UnicodeMode::Default,
                "Full" => UnicodeMode::Full,
                "Javascript" => UnicodeMode::Javascript,
                other => panic!("Unknown character mode: {other}"),
            });
        }
        if let Some(v) = options.get("case_insensitive") { opts = opts.case_insensitive(v.as_bool().unwrap()); }
        if let Some(v) = options.get("dot_matches_new_line") { opts = opts.dot_matches_new_line(v.as_bool().unwrap()); }
        if let Some(v) = options.get("multiline") { opts = opts.multiline(v.as_bool().unwrap()); }
        if let Some(v) = options.get("ignore_whitespace") { opts = opts.ignore_whitespace(v.as_bool().unwrap()); }
        RegexSet::with_options(&patterns, opts)
    } else {
        RegexSet::new(&patterns)
    };
    let set = match compiled {
        Ok(set) => set,
        Err(e) => return set_error(e),
    };
    let results: Vec<Value> = spec["actions"].as_array().unwrap().iter().map(|action| {
        let bytes: Vec<u8> = serde_json::from_value(action["input"].clone()).unwrap();
        let value = match action["op"].as_str().unwrap() {
            "is_match" => set.is_match(&bytes).map(|v| json!(v)),
            "matched" => set.matched(&bytes).map(|v| json!(v)),
            "find_all" => set.find_all(&bytes).map(|ms| json!(ms.into_iter()
                .map(|m| [m.start, m.end]).collect::<Vec<_>>())),
            "categorize_all" => set.categorize_all(&bytes).map(|ms| json!(ms.into_iter()
                .map(|m| [m.start, m.end, m.tag]).collect::<Vec<_>>())),
            other => panic!("Unknown collection operation: {other}"),
        };
        match value {
            Ok(value) => json!({"ok": true, "value": value}),
            Err(e) => set_error(e),
        }
    }).collect();
    json!({"ok": true, "results": results})
}
fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let specs: Vec<Value> = serde_json::from_str(&input).unwrap();
    let out: Vec<Value> = specs.iter().map(set_run).collect();
    println!("{}", serde_json::to_string(&out).unwrap());
}
'''


@pytest.fixture(scope="session")
def collection_api(tmp_path_factory):
    return build_rust_driver(
        tmp_path_factory.mktemp("f09-set") / "driver", SET_SOURCE,
        product_manifest=Path.cwd() / "Cargo.toml", package="rivexlib",
        features=("regex_set", "experimental_capture_groups"),
        dependencies_toml='serde_json = "1"\n',
        env=environment({"CARGO_NET_OFFLINE": "true"}), timeout=900.0,
    )


def collection_request(patterns, actions=(), *, options=None):
    request = {"patterns": list(patterns), "actions": list(actions)}
    if options is not None:
        request["options"] = options
    return request


def collection_case(patterns, rows, *, options=None, classify=False):
    """Rows supply independent membership and spans, optionally tagged spans."""
    actions, expected = [], []
    for data, members, spans in rows:
        actions.extend(operation(op, data) for op in ("is_match", "matched", "find_all"))
        expected.extend([bool(members), members,
                         [span[:2] for span in spans] if classify else spans])
        if classify:
            actions.append(operation("categorize_all", data))
            expected.append(spans)
    return collection_request(patterns, actions, options=options), expected
