# feature: F06
"""Public transaction observations, with fully consumed typed results.

Sequential calls on independent sessions are completion barriers: every write
finishes before the next observation. No sleeps or private engine state are used.
"""
RUST_TRANSACTION_SUPPORT = r'''
use velnora::{Database, IsolationLevel, ResultRow};
use velnora::api::Transaction;
fn sessions(name: &str) -> (Database, Database) {
    let dsn = format!("memory://{}", name);
    let a = Database::open(&dsn).unwrap();
    let b = Database::open(&dsn).unwrap();
    a.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)", ()).unwrap();
    a.execute("INSERT INTO t VALUES (1,10),(2,20)", ()).unwrap();
    (a,b)
}
fn exec(db: &Database, sql: &str) {
    db.execute(sql, ()).unwrap_or_else(|e| panic!("{sql}: {e}"));
}
fn read_rows(db: &Database, sql: &str) -> velnora::Result<Vec<ResultRow>> {
    db.query(sql, ()).and_then(|r| r.collect_vec())
}
fn values(db: &Database) -> Vec<(i64,i64)> {
    let rows = read_rows(db,"SELECT id,v FROM t ORDER BY id").unwrap();
    let values = rows.iter().map(|r| (r.get(0).unwrap(),r.get(1).unwrap())).collect();
    println!("session rows: {values:?}"); values
}
fn tx_values(tx: &mut Transaction) -> Vec<(i64,i64)> {
    let rows = tx.query("SELECT id,v FROM t ORDER BY id",()).and_then(|r|r.collect_vec()).unwrap();
    let values = rows.iter().map(|r| (r.get(0).unwrap(),r.get(1).unwrap())).collect();
    println!("transaction rows: {values:?}"); values
}
fn reject(db: &Database, sql: &str) {
    let outcome = db.query(sql, ()).and_then(|r|r.collect_vec());
    assert!(outcome.is_err(), "expected rejection for {sql}: {outcome:?}");
    println!("rejected {sql}: {:?}", outcome.unwrap_err());
}
fn identity(db: &Database) -> Option<i64> {
    let value = db.query_one("SELECT CURRENT_TRANSACTION_ID()",()).unwrap();
    println!("transaction identity: {value:?}"); value
}
'''

C_TRANSACTION_SUPPORT = r'''
#include "velnora.h"
#include <assert.h>
#include <stdio.h>
static void c_exec(VelnoraDB *db, const char *sql) {
    assert(velnora_exec(db,sql,NULL)==VELNORA_OK);
}
static int64_t consume_integer(VelnoraRows *rows) {
    assert(velnora_rows_next(rows)==VELNORA_ROW);
    assert(velnora_rows_column_type(rows,0)==VELNORA_TYPE_INTEGER);
    int64_t value=velnora_rows_column_int64(rows,0);
    assert(velnora_rows_next(rows)==VELNORA_DONE);
    velnora_rows_close(rows);
    printf("integer: %lld\n", (long long)value);
    return value;
}
static int64_t c_number(VelnoraDB *db, const char *sql) {
    VelnoraRows *rows=NULL;
    assert(velnora_query(db,sql,&rows)==VELNORA_OK);
    return consume_integer(rows);
}
static int64_t c_tx_number(VelnoraTx *tx, const char *sql) {
    VelnoraRows *rows=NULL;
    assert(velnora_tx_query(tx,sql,&rows)==VELNORA_OK);
    return consume_integer(rows);
}
'''
