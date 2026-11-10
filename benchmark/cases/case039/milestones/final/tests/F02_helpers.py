# feature: F02
"""Scalar SQL observations through the public Rust API, with lossless transport."""
import datetime as dt
import math
from F01_helpers import build_rust_client
from _helpers import run_command

SCALAR_CLIENT = r'''
use velnora::{Database, Value, DataType};
use std::io::{self, BufRead};
fn hex(s: &str)->String { s.as_bytes().iter().map(|b|format!("{b:02x}")).collect() }
fn unhex(s: &str)->String { String::from_utf8((0..s.len()).step_by(2).map(|i|u8::from_str_radix(&s[i..i+2],16).unwrap()).collect()).unwrap() }
fn encode(v: &Value)->String {
    match v {
        Value::Null(_)=>"n".into(), Value::Integer(x)=>format!("i{x}"),
        Value::Float(x)=>format!("f{x}"), Value::Boolean(x)=>format!("b{x}"),
        Value::Text(x)=>format!("s{}",hex(x.as_str())),
        Value::Timestamp(x)=>format!("t{}",hex(&x.to_rfc3339())),
        Value::Extension(_)=>format!("j{}",hex(v.as_json().expect("JSON value"))),
    }
}
fn decode(s: &str)->Value {
    match &s[..1] {
        "n"=>Value::Null(DataType::Null),"i"=>Value::Integer(s[1..].parse().unwrap()),
        "f"=>Value::Float(s[1..].parse().unwrap()),"b"=>Value::Boolean(s[1..].parse().unwrap()),
        "s"=>Value::from(unhex(&s[1..])),_=>panic!("invalid parameter tag")
    }
}
fn main() {
    let db=Database::open_in_memory().unwrap();
    for line in io::stdin().lock().lines() {
        let line=line.unwrap(); let parts:Vec<_>=line.split('\t').collect();
        let sql=unhex(parts[1]); let params:Vec<Value>=parts[2..].iter().map(|x|decode(x)).collect();
        if parts[0]=="S" { std::thread::sleep(std::time::Duration::from_millis(sql.parse().unwrap())); println!("S"); continue; }
        let before=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs_f64();
        if parts[0]=="E" {
            match db.execute(&sql,params) {Ok(n)=>{
                let after=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs_f64();
                println!("A\t{n}\t{before}\t{after}")
            },Err(e)=>println!("ERR\t{}",hex(&e.to_string()))}
        } else {
            let result=db.query(&sql,params).and_then(|r|r.collect_vec());
            match result { Ok(rows)=> {
                let after=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs_f64();
                println!("ROWS\t{}\t{before}\t{after}",rows.len());
                for row in rows { println!("{}",(0..row.len()).map(|i|encode(row.get_value(i).unwrap())).collect::<Vec<_>>().join("\t")); }
            }, Err(e)=>println!("ERR\t{}",hex(&e.to_string())) }
        }
    }
}
'''

def sql_text(value):
    return "'" + value.replace("'", "''") + "'"


def scalar_parameter(value):
    if value is None:
        return 'n'
    if isinstance(value, bool):
        return 'b' + str(value).lower()
    if isinstance(value, int):
        return 'i' + str(value)
    if isinstance(value, float):
        return 'f' + str(value)
    return 's' + value.encode().hex()


def scalar_batch(binary, operations):
    """Fully consume each query inside Rust's Result, retaining error vs empty rows."""
    wire = ''.join('\t'.join([mode, sql.encode().hex(), *map(scalar_parameter, params)]) + '\n'
                   for mode, sql, params in operations)
    result = run_command([binary], cwd=binary.parent, timeout=120, input_bytes=wire.encode())
    assert result.returncode == 0, (result.stdout, result.stderr)
    lines = iter(result.stdout.decode().splitlines())
    observations = []
    for _ in operations:
        head = next(lines).split('\t')
        if head[0] == 'ERR':
            observations.append({'error': bytes.fromhex(head[1]).decode()})
        elif head[0] == 'S':
            observations.append({'slept': True})
        elif head[0] == 'A':
            observations.append({'affected': int(head[1]), 'window': (float(head[2]), float(head[3]))})
        else:
            assert head[0] == 'ROWS', head
            rows = []
            for _ in range(int(head[1])):
                row = []
                for cell in next(lines).split('\t'):
                    tag, raw = cell[0], cell[1:]
                    if tag == 'n': value = None
                    elif tag == 'i': value = int(raw)
                    elif tag == 'f': value = float(raw)
                    elif tag == 'b':
                        assert raw in ('true', 'false')
                        value = raw == 'true'
                    else:
                        assert tag in ('s', 't', 'j'), cell
                        value = bytes.fromhex(raw).decode()
                    row.append((tag, value))
                rows.append(row)
            observations.append({'rows': rows, 'window': (float(head[2]), float(head[3]))})
    assert list(lines) == [], 'Unexpected client output'
    return observations


def scalar_rows(observation):
    assert 'rows' in observation, observation
    return [[value for tag, value in row] for row in observation['rows']]


def scalar_values(binary, expressions):
    results = scalar_batch(binary, [('Q', 'SELECT ' + expr, ()) for expr in expressions])
    values = []
    for expr, result in zip(expressions, results):
        rows = scalar_rows(result)
        assert len(rows) == 1 and len(rows[0]) == 1, (expr, result)
        values.append(rows[0][0])
    return values


def assert_scalars(binary, cases):
    actual = scalar_values(binary, [expr for expr, _ in cases])
    for (expr, expected), value in zip(cases, actual):
        assert type(value) is type(expected) and value == expected, (expr, value, expected)


def utc_instant(text):
    value = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    assert value.tzinfo is not None, text
    return value.astimezone(dt.timezone.utc)


def assert_uniform(samples):
    # Hoeffding + union bound: 2*10*exp(-2*10000*.04**2) < 3e-13.
    # Ten disjoint bins also reject a constant, narrow range, or gross bias.
    assert len(samples) == 10000
    counts = [0] * 10
    for value in samples:
        assert math.isfinite(value) and 0 <= value < 1, value
        counts[int(value * 10)] += 1
    assert all(abs(count / len(samples) - .1) <= .04 for count in counts), counts
    # Also inspect the empirical CDF: a discrete set of bin-center constants
    # must not masquerade as continuous uniform samples. DKW adds <3e-14.
    ordered = sorted(samples)
    discrepancy = max(max(abs(i / len(samples) - value),
                          abs((i + 1) / len(samples) - value))
                      for i, value in enumerate(ordered))
    assert discrepancy <= .04, discrepancy


def utc_nanoseconds(text):
    """Read the RFC3339 UTC serialization of Rust's public nanosecond timestamp."""
    assert text.endswith('+00:00'), text
    main = text[:-6]
    whole, separator, fraction = main.partition('.')
    if separator:
        assert fraction.isdecimal() and len(fraction) <= 9, text
    seconds = int(dt.datetime.fromisoformat(whole).replace(tzinfo=dt.timezone.utc).timestamp())
    return seconds * 10**9 + (int(fraction.ljust(9, '0')) if separator else 0)
