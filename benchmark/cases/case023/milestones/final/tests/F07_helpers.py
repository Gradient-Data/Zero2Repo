# feature: F07
"""Public hardening observations and test-owned, bounded growth measurements."""

import json
from pathlib import Path

import pytest

from _helpers import HelperError, MeasurementBlocked, build_rust_driver, environment
from F03_helpers import OPTIONS_SOURCE


# Extend the earlier option adapter without duplicating its transport or reader.
_HARDENING_INSERT = 'let mut opts = RegexOptions::default();'
_DEFAULT_INSERT = 'json!({"ok": true, "results": results})'
assert OPTIONS_SOURCE.count(_HARDENING_INSERT) == 1
assert OPTIONS_SOURCE.count(_DEFAULT_INSERT) == 1
HARDENING_SOURCE = OPTIONS_SOURCE.replace(
    _HARDENING_INSERT,
    _HARDENING_INSERT + '\n        opts = opts.hardened(spec["hardened"].as_bool().unwrap());',
).replace(
    _DEFAULT_INSERT,
    'json!({"ok": true, "results": results, '
    '"default_hardened": RegexOptions::default().hardened})',
)


GROWTH_SOURCE = r'''
use rivexlib::{Match, Regex, RegexOptions};
use serde::Deserialize;
use serde_json::{json, Value};
use std::hint::black_box;
use std::io::{self, Read};

#[derive(Deserialize)]
struct Job {
    pattern: String,
    hardened: bool,
    operation: String,
    block: Vec<u8>,
    repeats: [usize; 2],
    expected_spans: [Vec<[usize; 2]>; 2],
    expected_exists: [bool; 2],
    controls: Vec<Control>,
}
#[derive(Deserialize)]
struct Control { input: Vec<u8>, expected: Value }
enum Answer { Spans(Vec<Match>), Exists(bool) }

fn now() -> u128 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    let status = unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) };
    assert_eq!(status, 0, "clock_gettime: {}", io::Error::last_os_error());
    ts.tv_sec as u128 * 1_000_000_000 + ts.tv_nsec as u128
}
fn median(values: &[u128]) -> u128 {
    let mut values = values.to_vec();
    values.sort_unstable();
    values[values.len() / 2]
}
fn observe(regex: &Regex, input: &[u8], operation: &str) -> Result<Answer, String> {
    match operation {
        "find_all" => regex.find_all(black_box(input))
            .map(Answer::Spans).map_err(|e| format!("{e:?}")),
        "is_match" => regex.is_match(black_box(input))
            .map(Answer::Exists).map_err(|e| format!("{e:?}")),
        _ => panic!("Unknown measurement operation"),
    }
}
fn verify(answer: &Result<Answer, String>, job: &Job, side: usize) -> Result<(), Value> {
    match answer {
        Ok(Answer::Spans(spans)) => {
            let want = &job.expected_spans[side];
            if spans.len() == want.len() && spans.iter().zip(want)
                .all(|(a, b)| [a.start, a.end] == *b) { return Ok(()); }
            Err(json!({"status": "semantic_error", "side": side,
                "actual_spans": spans.iter().map(|m| [m.start, m.end]).collect::<Vec<_>>() }))
        },
        Ok(Answer::Exists(found)) if *found == job.expected_exists[side] => Ok(()),
        Ok(Answer::Exists(found)) => Err(json!({"status": "semantic_error",
            "side": side, "actual_exists": found})),
        Err(error) => Err(json!({"status": "semantic_error", "error": error})),
    }
}
fn batch(regex: &Regex, input: &[u8], job: &Job, side: usize, count: usize)
    -> Result<(u128, u128), Value>
{
    // Reserve before the clock; retain every complete public result until after
    // it stops. Validation and result destruction are outside the measurement.
    let mut answers = Vec::new();
    answers.try_reserve_exact(count).map_err(|e|
        json!({"status": "blocked", "reason": format!("allocation: {e}")}))?;
    let start = now();
    for _ in 0..count { answers.push(observe(black_box(regex), input, &job.operation)); }
    let elapsed = now() - start;
    for answer in &answers { verify(answer, job, side)?; }
    // Measure the same loop/retention scaffolding with no product call. This is
    // diagnostic information only: never subtract it or require a minimum
    // product cost relative to it. Faster implementations remain eligible.
    answers.clear();
    let start = now();
    for _ in 0..count { answers.push(black_box(Ok(Answer::Exists(false)))); }
    let overhead = now() - start;
    Ok((elapsed, overhead))
}
fn run(job: &Job) -> Value {
    let regex = match Regex::with_options(&job.pattern,
        RegexOptions::default().hardened(job.hardened)) {
        Ok(r) => r,
        Err(e) => return json!({"status": "semantic_error", "error": format!("{e:?}")}),
    };
    for control in &job.controls {
        let actual = match observe(&regex, &control.input, &job.operation) {
            Ok(Answer::Spans(spans)) => json!(spans.iter().map(|m|
                [m.start, m.end]).collect::<Vec<_>>()),
            Ok(Answer::Exists(value)) => json!(value),
            Err(error) => return json!({"status": "semantic_error", "error": error}),
        };
        if actual != control.expected {
            return json!({"status": "semantic_error", "control": control.input,
                "actual": actual, "expected": control.expected});
        }
    }
    let inputs = [job.block.repeat(job.repeats[0]), job.block.repeat(job.repeats[1])];
    for side in 0..2 {
        if let Err(e) = verify(&observe(&regex, &inputs[side], &job.operation), job, side) {
            return e;
        }
    }
    let mut resolution = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    if unsafe { libc::clock_getres(libc::CLOCK_MONOTONIC, &mut resolution) } != 0 {
        return json!({"status": "blocked", "reason": io::Error::last_os_error().to_string()});
    }
    let published = resolution.tv_sec as u128 * 1_000_000_000 + resolution.tv_nsec as u128;
    let mut steps = Vec::new();
    let mut previous = now();
    for _ in 0..1024 {
        let next = now();
        if next < previous { return json!({"status": "blocked", "reason": "clock reversed"}); }
        if next > previous { steps.push(next - previous); }
        previous = next;
    }
    if steps.is_empty() { return json!({"status": "blocked", "reason": "clock did not advance"}); }
    let empirical = median(&steps);
    let minimum = 1_000_000u128.max(1000 * published.max(empirical));
    let mut records = Vec::new();
    let deadline = now() + 30_000_000_000u128;
    for level in 0..21 {
        let count = 1usize << level;
        let mut times = [Vec::new(), Vec::new()];
        let mut overheads = [Vec::new(), Vec::new()];
        for sample in 0..9 {
            // Alternate the first side too, avoiding a persistent order bias.
            for side in [sample % 2, 1 - sample % 2] {
                if now() >= deadline {
                    return json!({"status": "blocked", "reason": "calibration budget exhausted",
                        "records": records, "times_ns": times, "batch": count});
                }
                let (elapsed, overhead) = match batch(&regex, &inputs[side], job, side, count) {
                    Ok(pair) => pair,
                    Err(e) => return e,
                };
                times[side].push(elapsed);
                overheads[side].push(overhead);
                // Keep raw completed observations even if the process later dies.
                eprintln!("{}", json!({"batch": count, "sample": sample, "side": side,
                    "elapsed_ns": elapsed, "overhead_ns": overhead}));
            }
        }
        let medians = [median(&times[0]), median(&times[1])];
        let overhead = [median(&overheads[0]), median(&overheads[1])];
        let valid = medians.iter().min().unwrap() >= &minimum;
        records.push(json!({"batch": count, "times_ns": times, "overhead_ns": overheads}));
        if now() >= deadline {
            return json!({"status": "blocked", "reason": "calibration budget exhausted",
                "records": records});
        }
        if valid {
            return json!({"status": "measured", "records": records, "batch": count,
                "median_ns": medians, "overhead_median_ns": overhead,
                "minimum_ns": minimum, "published_resolution_ns": published,
                "positive_step_median_ns": empirical, "clock_steps_ns": steps,
                "ratio": medians[1] as f64 / medians[0] as f64});
        }
    }
    json!({"status": "blocked", "reason": "calibration levels exhausted", "records": records})
}
fn main() {
    let mut text = String::new();
    io::stdin().read_to_string(&mut text).unwrap();
    let job: Job = serde_json::from_str(&text).unwrap();
    println!("{}", run(&job));
}
'''


@pytest.fixture(scope="session")
def hardened_matching(tmp_path_factory):
    return build_rust_driver(
        tmp_path_factory.mktemp("f07-semantics") / "driver", HARDENING_SOURCE,
        product_manifest=Path.cwd() / "Cargo.toml", package="rivexlib",
        dependencies_toml='serde_json = "1"\n',
        env=environment({"CARGO_NET_OFFLINE": "true"}),
    )


@pytest.fixture(scope="session")
def growth_driver(tmp_path_factory):
    return build_rust_driver(
        tmp_path_factory.mktemp("f07-growth") / "driver", GROWTH_SOURCE,
        product_manifest=Path.cwd() / "Cargo.toml", package="rivexlib",
        dependencies_toml='serde = { version = "1", features = ["derive"] }\n'
                          'serde_json = "1"\nlibc = "0.2"\n',
        env=environment({"CARGO_NET_OFFLINE": "true"}),
    )


def assert_input_growth(driver, *, pattern, block, operation, hardened, dense=False,
                        match_width=1, controls=()):
    """Measure fixed settings, validating every full result before any verdict."""
    assert block and 20_000 % len(block) == 0
    sizes = [20_000, 200_000]
    assert match_width > 0 and all(size % match_width == 0 for size in sizes)
    request = {
        "pattern": pattern, "hardened": hardened, "operation": operation,
        "block": list(block), "repeats": [size // len(block) for size in sizes],
        "expected_spans": [[[i, i + match_width] for i in range(0, size, match_width)] if dense else []
                           for size in sizes],
        "expected_exists": [False, False],
        "controls": [{"input": list(data), "expected": expected}
                     for data, expected in controls],
    }
    try:
        observation = driver.json(request, timeout=40).value
    except HelperError as error:
        raise MeasurementBlocked(
            "Search measurement did not complete; no growth verdict is available",
            result=error.result, cause=error,
        ) from error
    evidence = {"pattern": pattern, "block": list(block), "sizes": sizes,
                "operation": operation, "hardened": hardened, "observation": observation}
    print("F07 measurement " + json.dumps(evidence, sort_keys=True))
    if observation["status"] == "blocked":
        raise MeasurementBlocked(json.dumps(evidence, sort_keys=True))
    assert observation["status"] == "measured", evidence
    small, large = observation["median_ns"]
    assert min(small, large) >= observation["minimum_ns"], evidence
    assert large < 30 * small, evidence
    return evidence
