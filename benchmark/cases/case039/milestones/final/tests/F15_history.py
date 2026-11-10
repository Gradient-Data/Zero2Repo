# feature: F15
"""The three planned historical-query checks, scoped to retained memory history."""
import pytest
from F01_helpers import build_rust_client, run_native_client
from F15_helpers import RUST_HISTORY_SUPPORT


HISTORY_CASES = r'''
fn transaction_history() {
    let db=Database::open_in_memory().unwrap();
    exec(&db,"CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER, note TEXT)");
    let empty=history_commit(&db,"DELETE FROM t WHERE id=-1");
    let first=history_commit(&db,"INSERT INTO t VALUES (1,12,'seed'),(2,24,'steady')");
    let second=history_commit(&db,"UPDATE t SET v=37,note='middle' WHERE id=1");
    // A committed point with no new row version tests 'at or before', not equality.
    let between=history_commit(&db,"DELETE FROM t WHERE id=-1");
    let third=history_commit(&db,"UPDATE t SET v=-8,note='latest' WHERE id=1");
    let added=history_commit(&db,"INSERT INTO t VALUES (3,59,'late')");
    let deleted=history_commit(&db,"DELETE FROM t WHERE id=1");
    let after=history_commit(&db,"DELETE FROM t WHERE id=-1");
    let initial=vec![history_row![1,12,"seed"],history_row![2,24,"steady"]];
    let middle=vec![history_row![1,37,"middle"],history_row![2,24,"steady"]];
    let latest=vec![history_row![1,-8,"latest"],history_row![2,24,"steady"]];
    let expanded=vec![history_row![1,-8,"latest"],history_row![2,24,"steady"],history_row![3,59,"late"]];
    let current=vec![history_row![2,24,"steady"],history_row![3,59,"late"]];
    history_expect(&db,"SELECT id,v,note FROM t",current.clone());
    // Read nonchronologically so a moving cursor cannot masquerade as a selector.
    for (point,wanted) in [(second,middle.clone()),(empty,vec![]),(added,expanded),
        (first,initial),(deleted,current.clone()),(third,latest),
        (between,middle),(after,current.clone())] {
        history_expect(&db,&format!("SELECT id,v,note FROM t AS OF TRANSACTION {point}"),wanted);
    }
    history_expect(&db,"SELECT id,v,note FROM t",current);
}

fn timestamp_history() {
    let db=Database::open_in_memory().unwrap();
    exec(&db,"CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER, note TEXT)");
    let before=history_cut();
    history_commit(&db,"INSERT INTO t VALUES (1,12,'seed'),(2,24,'steady')");
    let timestamp_row=read_rows(&db,"SELECT CURRENT_TIMESTAMP").unwrap();
    let (text_point,numeric_point)=match timestamp_row[0].get_value(0).unwrap() {
        Value::Timestamp(timestamp)=>(timestamp.to_rfc3339(),timestamp.timestamp_nanos_opt().unwrap()),
        other=>panic!("expected current timestamp, got {other:?}"),
    };
    let first=history_cut();
    history_commit(&db,"UPDATE t SET v=37,note='middle' WHERE id=1");
    let second=history_cut();
    history_commit(&db,"UPDATE t SET v=-8,note='latest' WHERE id=1");
    history_commit(&db,"INSERT INTO t VALUES (3,59,'late')");
    let third=history_cut();
    assert!(before<first && first<second && second<third,"External clock moved backwards");
    let current=vec![history_row![1,-8,"latest"],history_row![2,24,"steady"],history_row![3,59,"late"]];
    history_expect(&db,"SELECT id,v,note FROM t",current.clone());
    for (point,wanted) in [
        (second,vec![history_row![1,37,"middle"],history_row![2,24,"steady"]]),
        (before,vec![]),
        (third,current.clone()),
        (first,vec![history_row![1,12,"seed"],history_row![2,24,"steady"]]),
    ] {
        // The public timestamp selector accepts integer Unix nanoseconds.
        history_expect(&db,&format!("SELECT id,v,note FROM t AS OF TIMESTAMP {point}"),wanted);
    }
    let initial=vec![history_row![1,12,"seed"],history_row![2,24,"steady"]];
    history_expect(&db,&format!("SELECT id,v,note FROM t AS OF TIMESTAMP {numeric_point}"),initial.clone());
    history_expect(&db,&format!("SELECT id,v,note FROM t AS OF TIMESTAMP '{text_point}'"),initial);
    history_expect(&db,"SELECT id,v,note FROM t",current);
}

fn composed_history_and_errors() {
    let db=Database::open_in_memory().unwrap();
    exec(&db,"CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER, note TEXT)");
    let before=history_cut();
    let first=history_commit(&db,"INSERT INTO t VALUES (1,12,'seed'),(2,24,'steady')");
    let first_timestamp=history_cut();
    let second=history_commit(&db,"UPDATE t SET v=37,note='middle' WHERE id=1");
    history_commit(&db,"UPDATE t SET v=-8,note='latest' WHERE id=1");
    let current=vec![history_row![1,-8,"latest"],history_row![2,24,"steady"]];
    history_expect(&db,"SELECT id,v,note FROM t",current.clone());
    history_expect(&db,&format!(
        "SELECT h.note,h.v FROM t AS OF TRANSACTION {second} AS h WHERE h.v>30"),
        vec![history_row!["middle",37]]);
    history_expect(&db,&format!(
        "SELECT h.id FROM t AS OF TRANSACTION {second} AS h WHERE h.v+1>30"),
        vec![history_row![1]]);
    history_expect(&db,&format!(
        "SELECT c.id,c.v,h.v,h.note FROM t AS c JOIN t AS OF TRANSACTION {first} AS h ON c.id=h.id WHERE c.v<>h.v"),
        vec![history_row![1,-8,12,"seed"]]);
    history_expect(&db,&format!(
        "SELECT h.id,h.v,c.v,c.note FROM t AS OF TRANSACTION {second} AS h JOIN t AS c ON h.id=c.id WHERE h.v<>c.v"),
        vec![history_row![1,37,-8,"latest"]]);
    history_expect(&db,&format!(
        "SELECT a.id,a.v,b.v,b.note FROM t AS OF TRANSACTION {first} AS a JOIN t AS OF TRANSACTION {second} AS b ON a.id=b.id"),
        vec![history_row![1,12,37,"middle"],history_row![2,24,24,"steady"]]);
    history_expect(&db,&format!(
        "SELECT c.id,c.v,h.v FROM t AS c JOIN t AS OF TIMESTAMP {first_timestamp} AS h ON c.id=h.id WHERE c.v<>h.v"),
        vec![history_row![1,-8,12]]);
    history_expect(&db,&format!(
        "SELECT a.id,a.v,b.v FROM t AS OF TIMESTAMP {first_timestamp} AS a JOIN t AS OF TRANSACTION {second} AS b ON a.id=b.id"),
        vec![history_row![1,12,37],history_row![2,24,24]]);
    // Empty history is a successful row result, unlike each malformed selector.
    history_expect(&db,&format!("SELECT id,v,note FROM t AS OF TIMESTAMP {before}"),vec![]);
    history_expect(&db,"SELECT id,v,note FROM t",current.clone());
    for sql in [
        "SELECT * FROM t AS OF TIMESTAMP 'bad-date'",
        "SELECT * FROM t AS OF TRANSACTION",
        "SELECT * FROM t AS OF TIMESTAMP",
        "SELECT * FROM t AS OF TRANSACTION 'abc'",
        "SELECT * FROM t AS OF TRANSACTION NULL",
    ] {
        reject(&db,sql);
        history_expect(&db,"SELECT id,v,note FROM t",current.clone());
    }
}
fn main() {
    match std::env::args().nth(1).as_deref().unwrap() {
        "transactions" => transaction_history(),
        "timestamps" => timestamp_history(),
        "composition" => composed_history_and_errors(),
        other => panic!("Unknown history case: {other}"),
    }
}
'''


@pytest.fixture(scope="module")
def history_client(tmp_path_factory):
    return build_rust_client(
        RUST_HISTORY_SUPPORT + HISTORY_CASES, tmp_path_factory.mktemp("f15-rust"))


def test_transaction_history_values_and_deletion(history_client):
    run_native_client(history_client, "transactions")


def test_timestamp_history_values_and_preinsert_empty(history_client):
    run_native_client(history_client, "timestamps")


def test_historical_relations_rejection_and_read_only(history_client):
    run_native_client(history_client, "composition")
