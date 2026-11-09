# feature: F15
"""History observations through public SQL, using earlier transaction helpers."""
from F06_helpers import RUST_TRANSACTION_SUPPORT

# The clock guards separate external historical points from writes; they are not
# product performance assertions. No cleanup or persistence is exercised.
RUST_HISTORY_SUPPORT = RUST_TRANSACTION_SUPPORT + r'''
use velnora::Value;
use std::time::{SystemTime, UNIX_EPOCH, Duration};
fn history_commit(db: &Database, sql: &str) -> i64 {
    exec(db,"BEGIN");
    let id = identity(db).expect("Active transaction identity");
    exec(db,sql);
    exec(db,"COMMIT");
    id
}
fn history_read(db: &Database, sql: &str) -> Vec<Vec<Value>> {
    let rows=read_rows(db,sql).unwrap_or_else(|e|panic!("{sql}: {e}"));
    let result=rows.iter().map(|r|(0..r.len()).map(|i|r.get_value(i).unwrap().clone()).collect()).collect();
    println!("{sql}: {result:?}");
    result
}
fn history_clock() -> i64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos().try_into().unwrap()
}
fn history_cut() -> i64 {
    std::thread::sleep(Duration::from_millis(20));
    let point=history_clock();
    std::thread::sleep(Duration::from_millis(20));
    assert!(history_clock()>point,"External clock must advance");
    point
}

fn history_expect(db: &Database, sql: &str, expected: Vec<Vec<Value>>) {
    let mut actual=history_read(db,sql);
    assert_eq!(actual.len(),expected.len(),"Row count for {sql}: {actual:?}");
    // Unordered multiset comparison retains duplicate multiplicity and value types.
    for wanted in expected {
        let index=actual.iter().position(|row| row.len()==wanted.len() &&
            row.iter().zip(&wanted).all(|(a,b)|
                std::mem::discriminant(a)==std::mem::discriminant(b) && a==b))
            .unwrap_or_else(||panic!("Missing {wanted:?} in {sql}: {actual:?}"));
        actual.remove(index);
    }
}
macro_rules! history_row {
    ($($value:expr),* $(,)?) => { vec![$(Value::from($value)),*] };
}
'''
