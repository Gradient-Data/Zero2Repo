# feature: F02
"""Thin public escaping driver; matching stays in the F01 driver."""

from pathlib import Path

import pytest

from _helpers import build_rust_driver, environment


ESCAPING_SOURCE = r'''
use serde_json::{json, Value};
use std::io::{self, Read};

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let specs: Vec<Value> = serde_json::from_str(&input).unwrap();
    let out: Vec<Value> = specs.iter().map(|spec| {
        let text = spec["text"].as_str().unwrap();
        let mut destination = spec["prefix"].as_str().unwrap().to_owned();
        let escaped = rivexlib::escape(text);
        rivexlib::escape_into(text, &mut destination);
        let appended = destination.clone();
        // A second append to the same buffer must add the fragment again.
        rivexlib::escape_into(text, &mut destination);
        json!({"escaped": escaped, "appended": appended, "appended_twice": destination})
    }).collect();
    println!("{}", serde_json::to_string(&out).unwrap());
}
'''


@pytest.fixture(scope="session")
def escaping(tmp_path_factory):
    return build_rust_driver(
        tmp_path_factory.mktemp("f02-rust") / "driver", ESCAPING_SOURCE,
        product_manifest=Path.cwd() / "Cargo.toml", package="rivexlib",
        dependencies_toml='serde_json = "1"\n',
        env=environment({"CARGO_NET_OFFLINE": "true"}),
    )
