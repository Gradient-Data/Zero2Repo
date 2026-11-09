# feature: F01
"""Acceptance checks through Rust, C and WebAssembly public entry points."""
import pytest
from _helpers import parse_json
from F01_helpers import build_rust_client, run_native_client, run_c_client, run_wasm_client

RUST_CLIENT = r'''
use velnora::{Database, FromRow, ResultRow, Error, named_params};
fn read(db: &Database, sql: &str) -> velnora::Result<Vec<ResultRow>> {
    db.query(sql, ()).and_then(|rows| rows.collect_vec())
}
fn number(db: &Database, sql: &str) -> i64 { db.query_one(sql, ()).unwrap() }
fn t01() {
    let a = Database::open_in_memory().unwrap();
    let b = Database::open_in_memory().unwrap();
    a.execute("CREATE TABLE local_data (id INTEGER)", ()).unwrap();
    a.execute("INSERT INTO local_data VALUES (17)", ()).unwrap();
    assert!(read(&b, "SELECT * FROM local_data").is_err());
    b.execute("CREATE TABLE local_data (id INTEGER)", ()).unwrap();
    assert!(read(&b, "SELECT * FROM local_data").unwrap().is_empty());
    b.execute("INSERT INTO local_data VALUES (29)", ()).unwrap();
    assert_eq!(number(&a, "SELECT id FROM local_data"), 17);
    assert_eq!(number(&b, "SELECT id FROM local_data"), 29);
    drop(a); drop(b);
    let fresh = Database::open_in_memory().unwrap();
    assert!(read(&fresh, "SELECT * FROM local_data").is_err());
    assert_eq!(number(&fresh, "SELECT 31"), 31);
    let a = Database::open("memory://f01_sessions").unwrap();
    let b = Database::open("memory://f01_sessions").unwrap();
    a.execute("CREATE TABLE shared_data (id INTEGER)", ()).unwrap();
    a.execute("INSERT INTO shared_data VALUES (41)", ()).unwrap();
    assert_eq!(number(&b, "SELECT id FROM shared_data"), 41);
    a.execute("BEGIN", ()).unwrap();
    a.execute("INSERT INTO shared_data VALUES (53)", ()).unwrap();
    assert_eq!(read(&b, "SELECT * FROM shared_data").unwrap().len(), 1);
    assert_eq!(read(&a, "SELECT * FROM shared_data").unwrap().len(), 2);
    a.execute("COMMIT", ()).unwrap();
    assert_eq!(read(&b, "SELECT * FROM shared_data").unwrap().len(), 2);
    let other = Database::open("memory://f01_different").unwrap();
    assert!(read(&other, "SELECT * FROM shared_data").is_err());
    assert_eq!(number(&other, "SELECT 79"), 79);
    drop(a);
    assert_eq!(b.execute("INSERT INTO shared_data VALUES (67)", ()).unwrap(), 1);
    assert_eq!(number(&b, "SELECT id FROM shared_data WHERE id = 67"), 67);
    fresh.execute("CREATE TABLE local_data (id INTEGER)", ()).unwrap();
    fresh.execute("INSERT INTO local_data VALUES (31)", ()).unwrap();
    assert_eq!(number(&fresh,"SELECT id FROM local_data"),31);
    fresh.close().unwrap();
    assert!(read(&fresh, "SELECT * FROM local_data").is_err());
    assert!(fresh.execute("CREATE TABLE closed_data (id INTEGER)", ()).is_err());
}
fn t02() {
    let db = Database::open_in_memory().unwrap();
    db.execute("CREATE TABLE records (id INTEGER, label TEXT)", ()).unwrap();
    assert_eq!(db.execute("INSERT INTO records VALUES (0, ''), (8, NULL), (13, 'visible')", ()).unwrap(), 3);
    let rows = db.query("SELECT label, id FROM records ORDER BY id", ()).unwrap();
    assert_eq!(rows.columns(), &["label", "id"]);
    let rows = rows.collect_vec().unwrap();
    assert_eq!(rows.len(), 3);
    for (row, (text, id)) in rows.iter().zip([(Some(""),0), (None,8), (Some("visible"),13)]) {
        assert_eq!(row.get::<Option<String>>(0).unwrap().as_deref(), text);
        assert_eq!(row.get::<i64>(1).unwrap(), id);
    }
    assert_eq!(db.execute("UPDATE records SET label = 'changed' WHERE id > 0", ()).unwrap(), 2);
    assert_eq!(db.execute("DELETE FROM records WHERE id = 999", ()).unwrap(), 0);
    assert_eq!(db.execute("DELETE FROM records WHERE id = 8", ()).unwrap(), 1);
    let rows = read(&db, "SELECT label, id FROM records ORDER BY id").unwrap();
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[1].get::<String>(0).unwrap(), "changed");
    assert_eq!(rows[1].get::<i64>(1).unwrap(), 13);
}
#[derive(Debug, PartialEq)]
struct Record { id: i64, label: Option<String> }
impl FromRow for Record {
    fn from_row(row: &ResultRow) -> velnora::Result<Self> {
        Ok(Self { id: row.get_by_name("id")?, label: row.get_by_name("label")? })
    }
}
fn t03() {
    let db = Database::open_in_memory().unwrap();
    db.execute("CREATE TABLE records (id INTEGER, label TEXT)", ()).unwrap();
    db.execute("INSERT INTO records VALUES (4, 'four'), (9, NULL)", ()).unwrap();
    let rows = read(&db, "SELECT label, id FROM records ORDER BY id").unwrap();
    assert_eq!(rows[0].get::<i64>(1).unwrap(), 4);
    assert_eq!(rows[0].get_by_name::<String>("label").unwrap(), "four");
    let mapped: Vec<Record> = db.query_as("SELECT label, id FROM records ORDER BY id", ()).unwrap();
    assert_eq!(mapped, vec![Record{id:4,label:Some("four".into())},Record{id:9,label:None}]);
    assert_eq!(db.query_one::<i64,_>("SELECT id, label FROM records ORDER BY id", ()).unwrap(), 4);
    assert_eq!(db.query_opt::<i64,_>("SELECT id, label FROM records ORDER BY id DESC", ()).unwrap(), Some(9));
    let prepared = db.prepare("SELECT id, label FROM records ORDER BY id").unwrap();
    assert_eq!(prepared.query_one::<i64,_>(()).unwrap(),4);
    assert!(db.query_one::<i64,_>("SELECT id FROM records WHERE id = 99", ()).is_err());
    assert_eq!(db.query_opt::<Option<String>,_>("SELECT label FROM records WHERE id = 99", ()).unwrap(), None);
    assert_eq!(db.query_opt::<Option<String>,_>("SELECT label FROM records WHERE id = 9", ()).unwrap(), Some(None));
    assert_eq!(db.query_opt::<Option<String>,_>("SELECT label FROM records WHERE id = 4", ()).unwrap(), Some(Some("four".into())));
}
fn t04() {
    let db = Database::open_in_memory().unwrap();
    db.execute("CREATE TABLE bindings (id INTEGER, content TEXT)", ()).unwrap();
    let payload = "x'); DROP TABLE bindings; -- :id $1 ? Ω";
    assert_eq!(db.execute("INSERT INTO bindings VALUES ($1, $2)", (7,payload)).unwrap(), 1);
    assert_eq!(db.execute_named("INSERT INTO bindings VALUES (:id, :content)", named_params!{id: 11, content: "' OR 1=1 --"}).unwrap(),1);
    let rows = db.query("SELECT content FROM bindings WHERE id = $1", (7,)).unwrap().collect_vec().unwrap();
    assert_eq!(rows.len(),1);
    assert_eq!(rows[0].get::<String>(0).unwrap(),payload);
    let rows = db.query_named("SELECT content FROM bindings WHERE id = :id", named_params!{id: 11}).unwrap().collect_vec().unwrap();
    assert_eq!(rows.len(),1);
    assert_eq!(rows[0].get::<String>(0).unwrap(), "' OR 1=1 --");
    assert_eq!(number(&db,"SELECT COUNT(*) FROM bindings"),2);
}
fn t05() {
    let db = Database::open_in_memory().unwrap();
    db.execute("CREATE TABLE prepared_data (id INTEGER, label TEXT)", ()).unwrap();
    let insert = db.prepare("INSERT INTO prepared_data VALUES ($1, $2)").unwrap();
    let query = db.prepare("SELECT label FROM prepared_data WHERE id = $1").unwrap();
    assert_eq!(insert.execute((3,"before")).unwrap(),1);
    assert_eq!(insert.execute((6,"other")).unwrap(),1);
    for (id,label) in [(3,"before"),(6,"other")] {
        let rows = query.query((id,)).unwrap().collect_vec().unwrap();
        assert_eq!(rows.len(),1); assert_eq!(rows[0].get::<String>(0).unwrap(),label);
    }
    db.execute("UPDATE prepared_data SET label = 'after' WHERE id = 3", ()).unwrap();
    let rows = query.query((3,)).unwrap().collect_vec().unwrap();
    assert_eq!(rows.len(),1); assert_eq!(rows[0].get::<String>(0).unwrap(),"after");
    assert!(query.query((99,)).unwrap().collect_vec().unwrap().is_empty());
    assert_eq!(insert.execute((99,"new")).unwrap(),1);
    let rows = query.query((99,)).unwrap().collect_vec().unwrap();
    assert_eq!(rows.len(),1); assert_eq!(rows[0].get::<String>(0).unwrap(),"new");
}
fn t06() {
    let db = Database::open_in_memory().unwrap();
    db.execute("CREATE TABLE errors (id INTEGER, label TEXT)", ()).unwrap();
    assert!(read(&db,"SELECT * FROM errors").unwrap().is_empty());
    assert!(read(&db,"SELEC 17").is_err());
    assert!(db.query("SELEC 17", ()).and_then(|r|r.collect_vec()).is_err());
    let rows = read(&db,"SELECT 17 AS id, 'not-a-number' AS label").unwrap();
    assert_eq!(rows[0].get_by_name::<i64>("id").unwrap(),17);
    assert_eq!(rows[0].get_by_name::<String>("label").unwrap(),"not-a-number");
    assert!(rows[0].get::<i64>(2).is_err());
    assert!(rows[0].get::<Option<i64>>(2).is_err());
    assert!(rows[0].get_by_name::<Option<i64>>("missing").is_err());
    let prepared = db.prepare("SELECT id FROM errors WHERE id=$1").unwrap();
    assert!(prepared.query(()).and_then(|r|r.collect_vec()).is_err());
    assert!(prepared.query((7,)).unwrap().collect_vec().unwrap().is_empty());
    assert!(rows[0].get_by_name::<i64>("missing").is_err());
    assert!(rows[0].get_by_name::<i64>("label").is_err());
}
fn t07() {
    let db = Database::open_in_memory().unwrap();
    db.execute("CREATE TABLE work (id INTEGER)", ()).unwrap();
    let insert = db.prepare("INSERT INTO work VALUES ($1)").unwrap();
    let quick = db.query_with_timeout("SELECT 31", (), 60000).and_then(|r|r.collect_vec()).unwrap();
    assert_eq!(quick[0].get::<i64>(0).unwrap(),31);
    let sql = "SELECT a.id FROM work a WHERE (SELECT COUNT(*) FROM work b WHERE b.id < a.id) >= 0 ORDER BY a.id";
    let mut inserted = 0;
    let mut observed_cancellation = false;
    // Calibrate finite work in this environment; never assume a fixed input takes a millisecond.
    for size in [600,1200,2400,4800,9600] {
        for id in inserted..size { insert.execute((id,)).unwrap(); }
        inserted = size;
        let start = std::time::Instant::now();
        let complete = db.query_with_timeout(sql, (), 0).and_then(|r|r.collect_vec()).unwrap();
        assert_eq!(complete.len(),size as usize);
        if start.elapsed().as_millis() < 25 { continue; }
        let expired = db.query_with_timeout(sql, (), 1).and_then(|r|r.collect_vec());
        match expired {
            Err(Error::QueryCancelled) => { observed_cancellation = true; break; },
            Ok(rows) => assert_eq!(rows.len(),size as usize),
            Err(error) => panic!("Unexpected query error: {error:?}"),
        }
    }
    assert!(observed_cancellation, "Finite calibration did not observe deadline cancellation");
    assert_eq!(number(&db,"SELECT COUNT(*) FROM work"),inserted);

}
fn main() {
    match std::env::args().nth(1).unwrap().as_str() {
        "t01"=>t01(),"t02"=>t02(),"t03"=>t03(),"t04"=>t04(),
        "t05"=>t05(),"t06"=>t06(),"t07"=>t07(),_=>panic!("unknown case")
    }
}
'''

@pytest.fixture(scope="module")
def rust_client(tmp_path_factory):
    return build_rust_client(RUST_CLIENT, tmp_path_factory.mktemp("f01-rust"))


def test_session_lifetimes(rust_client):
    run_native_client(rust_client, "t01")


def test_result_shapes_and_missing_values(rust_client):
    run_native_client(rust_client, "t02")


def test_typed_scalar_and_record_reads(rust_client):
    run_native_client(rust_client, "t03")


def test_bound_values_are_data(rust_client):
    run_native_client(rust_client, "t04")


def test_prepared_execution_refreshes(rust_client):
    run_native_client(rust_client, "t05")


def test_errors_are_not_empty_success(rust_client):
    run_native_client(rust_client, "t06")


def test_query_time_allowance(rust_client):
    run_native_client(rust_client, "t07")


def test_c_prepared_results(tmp_path):
    result = run_c_client(r'''
#include "velnora.h"
#include <assert.h>
#include <string.h>
static void text_equal(VelnoraRows *rows, int col, const char *expected) {
    int64_t size = -1;
    const char *value = velnora_rows_column_text(rows, col, &size);
    assert(value != NULL);
    assert(size == (int64_t)strlen(expected));
    assert(memcmp(value, expected, size) == 0);
}
int main(void) {
    VelnoraDB *db = NULL;
    VelnoraStmt *insert = NULL, *query = NULL;
    VelnoraRows *rows = NULL;
    int64_t count = -1;
    VelnoraDB *sibling = NULL;
    assert(velnora_open("memory://f01_c_shared", &db) == VELNORA_OK);
    assert(velnora_open("memory://f01_c_shared", &sibling) == VELNORA_OK);
    assert(velnora_exec(db, "CREATE TABLE native_data (id INTEGER, label TEXT)", &count) == VELNORA_OK);
    assert(velnora_prepare(db, "INSERT INTO native_data VALUES ($1, $2)", &insert) == VELNORA_OK);
    VelnoraValue params[2] = {0};
    params[0].value_type = VELNORA_TYPE_INTEGER;
    params[1].value_type = VELNORA_TYPE_TEXT;
    const char *texts[] = {"x'); DROP TABLE native_data; --", ""};
    for (int i = 0; i < 2; ++i) {
        params[0].v.integer = i + 21;
        params[1].v.text.ptr = texts[i]; params[1].v.text.len = strlen(texts[i]);
        assert(velnora_stmt_exec(insert, params, 2, &count) == VELNORA_OK);
        assert(count == 1);
    }
    assert(velnora_exec(db, "INSERT INTO native_data VALUES (23, NULL)", &count) == VELNORA_OK);
    assert(count == 1);
    assert(velnora_prepare(db, "SELECT label, id FROM native_data WHERE id >= $1 ORDER BY id", &query) == VELNORA_OK);
    for (int start = 21; start <= 23; ++start) {
        params[0].v.integer = start;
        assert(velnora_stmt_query(query, params, 1, &rows) == VELNORA_OK);
        assert(velnora_rows_column_count(rows) == 2);
        assert(strcmp(velnora_rows_column_name(rows, 0), "label") == 0);
        assert(strcmp(velnora_rows_column_name(rows, 1), "id") == 0);
        for (int id = start; id <= 23; ++id) {
            assert(velnora_rows_next(rows) == VELNORA_ROW);
            assert(velnora_rows_column_type(rows, 1) == VELNORA_TYPE_INTEGER);
            assert(velnora_rows_column_int64(rows, 1) == id);
            assert(velnora_rows_column_type(rows, 0) == (id == 23 ? VELNORA_TYPE_NULL : VELNORA_TYPE_TEXT));
            assert(velnora_rows_column_is_null(rows, 0) == (id == 23));
            if (id != 23) text_equal(rows, 0, texts[id - 21]);
        }
        assert(velnora_rows_next(rows) == VELNORA_DONE);
        velnora_rows_close(rows);
    }
    assert(velnora_exec(db, "UPDATE native_data SET label = 'new' WHERE id = 21", &count) == VELNORA_OK);
    assert(count == 1);
    params[0].v.integer = 21;
    assert(velnora_stmt_query(query, params, 1, &rows) == VELNORA_OK);
    assert(velnora_rows_next(rows) == VELNORA_ROW);
    text_equal(rows, 0, "new");
    assert(velnora_rows_next(rows) == VELNORA_ROW);
    assert(velnora_rows_next(rows) == VELNORA_ROW);
    assert(velnora_rows_next(rows) == VELNORA_DONE);
    velnora_rows_close(rows);
    velnora_stmt_finalize(query); velnora_stmt_finalize(insert);
    assert(velnora_exec(db, "CREATE TABLE native_numbers (f FLOAT,b BOOLEAN)", &count) == VELNORA_OK);
    VelnoraStmt *numbers = NULL;
    assert(velnora_prepare(db, "INSERT INTO native_numbers VALUES ($1,$2)", &numbers) == VELNORA_OK);
    params[0].value_type = VELNORA_TYPE_FLOAT;
    params[0].v.float64 = -2.75;
    params[1].value_type = VELNORA_TYPE_BOOLEAN;
    params[1].v.boolean = 1;
    assert(velnora_stmt_exec(numbers, params, 2, &count) == VELNORA_OK);
    assert(count == 1);
    velnora_stmt_finalize(numbers);
    assert(velnora_close(db) == VELNORA_OK);
    assert(velnora_prepare(sibling, "SELECT f,b FROM native_numbers", &numbers) == VELNORA_OK);
    assert(velnora_stmt_query(numbers, NULL, 0, &rows) == VELNORA_OK);
    assert(velnora_rows_next(rows) == VELNORA_ROW);
    assert(velnora_rows_column_type(rows, 0) == VELNORA_TYPE_FLOAT);
    assert(velnora_rows_column_double(rows, 0) == -2.75);
    assert(velnora_rows_column_type(rows, 1) == VELNORA_TYPE_BOOLEAN);
    assert(velnora_rows_column_bool(rows, 1) == 1);
    assert(velnora_rows_next(rows) == VELNORA_DONE);
    velnora_rows_close(rows);
    velnora_stmt_finalize(numbers);
    assert(velnora_close(sibling) == VELNORA_OK);
    return 0;
}
''', tmp_path)
    assert result.returncode == 0, (result.stdout, result.stderr)


def test_wasm_batches_and_isolation(tmp_path):
    observations = parse_json(run_wasm_client(r'''
await api.default({module_or_path: wasmBytes});
const a = new api.VelnoraDB();
const b = new api.VelnoraDB();
const out = {};
try {
    out.batch = JSON.parse(a.execute_batch("CREATE TABLE items (id INTEGER, label TEXT); INSERT INTO items VALUES (3, 'first; value'); INSERT INTO items VALUES (8, 'second'); SELECT label, id FROM items ORDER BY id"));
    out.other_missing = JSON.parse(b.execute("SELECT * FROM items"));
    out.other_create = JSON.parse(b.execute("CREATE TABLE items (id INTEGER, label TEXT)"));
    out.other_empty = JSON.parse(b.execute("SELECT label, id FROM items"));
    out.write = JSON.parse(a.execute_batch("UPDATE items SET label = 'revised' WHERE id = 3; INSERT INTO items VALUES (12, NULL), (15, '')"));
    out.final = JSON.parse(a.execute("SELECT label, id FROM items ORDER BY id"));
    out.other_final = JSON.parse(b.execute("SELECT label, id FROM items"));
} finally { a.free(); b.free(); }
const fresh = new api.VelnoraDB();
try {
    out.fresh_missing = JSON.parse(fresh.execute("SELECT * FROM items"));
    out.fresh_control = JSON.parse(fresh.execute("SELECT 37 AS value"));
} finally { fresh.free(); }
console.log(JSON.stringify(out));
''', tmp_path))
    assert observations["batch"] == {
        "type": "rows", "columns": ["label", "id"],
        "rows": [["first; value", 3], ["second", 8]], "count": 2}
    assert observations["other_missing"]["type"] == "error"
    assert isinstance(observations["other_missing"]["message"], str)
    assert observations["other_create"]["type"] == "affected"
    assert observations["other_empty"] == {
        "type": "rows", "columns": ["label", "id"], "rows": [], "count": 0}
    assert observations["write"] == {"type": "affected", "affected": 2}
    assert observations["final"] == {
        "type": "rows", "columns": ["label", "id"],
        "rows": [["revised", 3], ["second", 8], [None, 12], ["", 15]],
        "count": 4}
    assert observations["other_final"] == {
        "type": "rows", "columns": ["label", "id"], "rows": [], "count": 0}
    assert observations["fresh_missing"]["type"] == "error"
    assert observations["fresh_control"] == {"type":"rows", "columns":["value"], "rows":[[37]], "count":1}
