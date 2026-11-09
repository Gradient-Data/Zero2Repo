# feature: F03
"""Option-aware public adapter and independent Unicode 16.0.0 oracle."""

from pathlib import Path

import pytest

from _helpers import build_rust_driver, environment
from F01_helpers import operation, pattern_request


OPTIONS_SOURCE = r'''
use rivexlib::{Regex, RegexOptions, UnicodeMode};
use serde_json::{json, Value};
use std::io::{self, Read};
fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let specs: Vec<Value> = serde_json::from_str(&input).unwrap();
    let output: Vec<Value> = specs.iter().map(|spec| {
        let mut opts = RegexOptions::default();
        if let Some(mode) = spec.get("mode") {
            opts = opts.unicode(match mode.as_str().unwrap() {
                "Ascii" => UnicodeMode::Ascii,
                "Default" => UnicodeMode::Default,
                "Full" => UnicodeMode::Full,
                "Javascript" => UnicodeMode::Javascript,
                other => panic!("Unknown mode: {other}"),
            });
        }
        if let Some(v) = spec.get("case_insensitive") { opts = opts.case_insensitive(v.as_bool().unwrap()); }
        if let Some(v) = spec.get("dot_matches_new_line") { opts = opts.dot_matches_new_line(v.as_bool().unwrap()); }
        if let Some(v) = spec.get("multiline") { opts = opts.multiline(v.as_bool().unwrap()); }
        if let Some(v) = spec.get("ignore_whitespace") { opts = opts.ignore_whitespace(v.as_bool().unwrap()); }
        let regex = Regex::with_options(spec["pattern"].as_str().unwrap(), opts).unwrap();
        let results: Vec<Value> = spec["actions"].as_array().unwrap().iter().map(|action| {
            let bytes: Vec<u8> = serde_json::from_value(action["input"].clone()).unwrap();
            let value = match action["op"].as_str().unwrap() {
                "find_all" => json!(regex.find_all(&bytes).unwrap().into_iter()
                    .map(|m| [m.start, m.end]).collect::<Vec<_>>()),
                "is_full_match" => json!(regex.is_full_match(&bytes).unwrap()),
                op => panic!("Unknown operation: {op}"),
            };
            json!({"ok": true, "value": value})
        }).collect();
        json!({"ok": true, "results": results})
    }).collect();
    println!("{}", serde_json::to_string(&output).unwrap());
}
'''

# regex-syntax 0.8.10 ships Unicode 16.0.0 tables. This separately built
# executable uses only the registry dependency, never product tables or output.
# The exact dependency requirement below prevents a system Unicode upgrade
# silently changing the expected membership or simple-fold equivalence sets.
UNICODE_SOURCE = r'''
use regex_syntax::{ParserBuilder, hir::{HirKind, Class}};
use serde_json::{json, Value};
use std::io::{self, Read};
fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let patterns: Vec<String> = serde_json::from_str(&input).unwrap();
    let out: Vec<Value> = patterns.iter().map(|pattern| {
        let hir = ParserBuilder::new().build().parse(pattern).unwrap();
        match hir.kind() {
            HirKind::Class(Class::Unicode(class)) => json!(class.ranges().iter()
                .map(|r| [r.start() as u32, r.end() as u32]).collect::<Vec<_>>()),
            other => panic!("Expected a Unicode class, got {other:?}"),
        }
    }).collect();
    println!("{}", serde_json::to_string(&out).unwrap());
}
'''


@pytest.fixture(scope="session")
def option_matching(tmp_path_factory):
    return build_rust_driver(
        tmp_path_factory.mktemp("f03-options") / "driver", OPTIONS_SOURCE,
        product_manifest=Path.cwd() / "Cargo.toml", package="rivexlib",
        dependencies_toml='serde_json = "1"\n',
        env=environment({"CARGO_NET_OFFLINE": "true"}),
    )


@pytest.fixture(scope="session")
def unicode16(tmp_path_factory):
    return build_rust_driver(
        tmp_path_factory.mktemp("f03-unicode") / "driver", UNICODE_SOURCE,
        product_manifest=Path.cwd() / "Cargo.toml", package="rivexlib",
        dependencies_toml='serde_json = "1"\nregex-syntax = "=0.8.10"\n',
        env=environment({"CARGO_NET_OFFLINE": "true"}),
    )


MODES = ("Ascii", "Default", "Full", "Javascript")
ASCII_SETS = {
    "w": set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"),
    "d": set("0123456789"),
    "s": set(" \t\n\v\f\r"),
}
# All ASCII members and exclusions, limited-mode boundary, each word-set
# constituent, wider decimal/space members, supplementary and Unicode 16 additions.
CHARACTERS = "".join(map(chr, range(128))) + "".join(map(chr, range(0x7F0, 0x810))) + (
    "éΩЖאش\u0300\u0345\u0660\u06f9\u07c0\u0903क๙猫"
    "\u0085\u00a0\u1680\u2000\u2007\u2028\u2029\u202f\u205f\u3000"
    "\u200b\u200c\u200d\u203f\u2040\u2060\uff19\uff3f"
    "𐐀𝟠🦉\U00011f02\U0001e4f0\u1c89\U00010d40\U00016100\U0001e5d0"
    "\ud7ff\ue000\ufffd\U0010ffff"
)


def unicode_ranges(oracle, patterns):
    ranges = oracle.json(patterns).value
    assert len(ranges) == len(patterns)
    for table in ranges:
        assert table and all(0 <= lo <= hi <= 0x10FFFF for lo, hi in table)
    return ranges


def in_ranges(char, ranges):
    return any(lo <= ord(char) <= hi for lo, hi in ranges)


def boundary_text(ranges):
    """Sample every standard interval endpoint and its immediate outside values."""
    points = set(map(ord, CHARACTERS))
    for lo, hi in ranges:
        points.update((lo - 1, lo, hi, hi + 1))
    return "".join(chr(p) for p in sorted(points)
                   if 0 <= p <= 0x10FFFF and not 0xD800 <= p <= 0xDFFF)


def scalar_spans(text, accepts=lambda c: True):
    spans, offset = [], 0
    for char in text:
        end = offset + len(char.encode("utf-8"))
        if accepts(char):
            spans.append([offset, end])
        offset = end
    return spans


def byte_spans(text, accepts=lambda b: True):
    return [[i, i + 1] for i, byte in enumerate(text.encode("utf-8")) if accepts(byte)]


def option_request(pattern, actions, mode=None, **options):
    request = pattern_request(pattern, actions)
    if mode is not None:
        request["mode"] = mode
    request.update(options)
    return request


def class_case(pattern, text, accepts, mode=None, *, full=False, **options):
    actions = [operation("find_all", text.encode("utf-8"))]
    expected = [scalar_spans(text, accepts)]
    if full:
        # Consume results on both the search and whole-input public paths.
        for char in text:
            actions.append(operation("is_full_match", char.encode("utf-8")))
            expected.append(accepts(char))
        actions.extend([operation("is_full_match", b""),
                        operation("is_full_match", (text[:1] * 2).encode("utf-8"))])
        expected.extend([False, False])
    return option_request(pattern, actions, mode, **options), expected


def shorthand_predicate(kind, mode, ranges, *, combined=False):
    if mode in ("Ascii", "Javascript") or (mode == "Default" and kind != "w" and not combined):
        return lambda char: char in ASCII_SETS[kind]
    if mode == "Default" and not combined:
        return lambda char: ord(char) <= 2047 and in_ranges(char, ranges)
    return lambda char: in_ranges(char, ranges)
