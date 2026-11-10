# feature: F19
"""Read administration results through public SQL and named result columns."""
from F15_helpers import RUST_HISTORY_SUPPORT
from F08_snapshots import RUST_SNAPSHOT_SUPPORT


RUST_MAINTENANCE_SUPPORT = RUST_HISTORY_SUPPORT + RUST_SNAPSHOT_SUPPORT + r'''
fn diagnostic_sales_fixture() -> Database {
    let db=Database::open_in_memory().unwrap();
    exec(&db,"CREATE TABLE sales (id INTEGER PRIMARY KEY, dept INTEGER, amount INTEGER)");
    exec(&db,"INSERT INTO sales VALUES (1,1,7),(2,1,13),(3,2,19)");
    db
}

fn diagnostic_plan(db: &Database, sql: &str) -> Vec<String> {
    let rows=read_rows(db,sql).unwrap_or_else(|e|panic!("{sql}: {e}"));
    let lines:Vec<String>=rows.iter().map(|r|r.get_by_name::<String>("plan").unwrap()).collect();
    println!("{sql}: {lines:#?}");
    lines
}
fn diagnostic_field<'a>(lines: &'a [String], label: &str) -> &'a str {
    let fields:Vec<_>=lines.iter().filter_map(|line|line.trim().strip_prefix(label)).collect();
    assert_eq!(fields.len(),1,"Expected one {label} field: {lines:?}");
    fields[0].trim()
}
fn diagnostic_source(lines: &[String], table: &str) {
    // The access description is free; only the public 'on <table>' carrier is read.
    assert!(lines.iter().any(|line|line.trim().strip_prefix("-> ")
        .and_then(|node|node.split_once(" on "))
        .and_then(|(_,tail)|tail.split_whitespace().next())==Some(table)),
        "Missing source {table}: {lines:?}");
}
fn diagnostic_measurement(lines: &[String], statement: &str) -> (u64,f64) {
    let header=format!("{statement} (actual time=");
    let fields:Vec<_>=lines.iter().filter_map(|line|line.trim().strip_prefix(&header)).collect();
    assert_eq!(fields.len(),1,"Missing actual execution header: {lines:?}");
    let (duration,count)=fields[0].split_once(", rows=").expect("Actual time and row fields");
    // Parse the complete labelled duration, without fixing a precision or a speed.
    let (numeric,scale)=if let Some(n)=duration.strip_suffix("µs") {(n,1e-6)}
        else if let Some(n)=duration.strip_suffix("ms") {(n,1e-3)}
        else {(duration.strip_suffix('s').expect("Duration unit"),1.0)};
    let elapsed:f64=numeric.parse().expect("Numeric execution duration");
    assert!(elapsed.is_finite() && elapsed>=0.0,"Invalid execution duration");
    (count.strip_suffix(')').expect("Execution header closing delimiter").parse().unwrap(),elapsed*scale)
}
fn diagnostic_actual(lines: &[String], statement: &str) -> u64 {
    diagnostic_measurement(lines,statement).0
}
fn maintenance_integer(db: &Database, sql: &str, column: &str) -> i64 {
    let rows=read_rows(db,sql).unwrap_or_else(|e|panic!("{sql}: {e}"));
    assert_eq!(rows.len(),1,"{sql}: {rows:?}");
    let value=rows[0].get_by_name(column).unwrap();
    println!("{sql} [{column}]: {value}");
    value
}
fn maintenance_columns(db: &Database, table: &str,
    expected: Vec<(&str,i64,i64,Option<&str>,Option<&str>)>, numeric: &[(&str,bool)]) {
    let sql=format!("SELECT column_name,null_count,distinct_count,min_value,max_value FROM _sys_column_stats WHERE table_name='{table}'");
    let rows=read_rows(db,&sql).unwrap();
    let mut actual:Vec<(String,i64,i64,Option<String>,Option<String>)>=rows.iter().map(|r|(
        r.get_by_name("column_name").unwrap(),r.get_by_name("null_count").unwrap(),
        r.get_by_name("distinct_count").unwrap(),r.get_by_name("min_value").unwrap(),
        r.get_by_name("max_value").unwrap())).collect();
    actual.sort();
    let mut wanted:Vec<_>=expected.into_iter().map(|(c,n,d,lo,hi)|
        (c.to_string(),n,d,lo.map(str::to_string),hi.map(str::to_string))).collect();
    wanted.sort();
    println!("Column statistics {table}: {actual:?}");
    assert_eq!(actual.len(),wanted.len());
    for ((column,n,d,lo,hi),(wc,wn,wd,wlo,whi)) in actual.iter().zip(&wanted) {
        assert_eq!((column,n,d),(wc,wn,wd));
        for (observed,expected) in [(lo,wlo),(hi,whi)] {
            match (observed,expected,numeric.iter().find(|(name,_)|name==column)) {
                (Some(a),Some(b),Some((_,true)))=>assert_eq!(a.parse::<i64>().unwrap(),b.parse::<i64>().unwrap()),
                (Some(a),Some(b),Some((_,false)))=>assert_eq!(a.parse::<f64>().unwrap(),b.parse::<f64>().unwrap()),
                _=>assert_eq!(observed,expected),
            }
        }
    }
}
'''
