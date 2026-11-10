# feature: F06
"""Nine planned acceptance checks for transaction boundaries and visibility."""
import pytest
from F01_helpers import build_rust_client, run_native_client, run_c_client
from F06_helpers import RUST_TRANSACTION_SUPPORT, C_TRANSACTION_SUPPORT

TRANSACTION_CASES = r'''
fn t01() {
    let (a,b)=sessions("f06_boundaries");
    assert_eq!(values(&b),vec![(1,10),(2,20)]);
    {
        let mut tx=a.begin().unwrap();
        tx.execute("UPDATE t SET v=31 WHERE id=1",()).unwrap();
        tx.execute("DELETE FROM t WHERE id=2",()).unwrap();
        tx.execute("INSERT INTO t VALUES (3,43)",()).unwrap();
        assert_eq!(tx_values(&mut tx),vec![(1,31),(3,43)]);
        assert_eq!(values(&b),vec![(1,10),(2,20)]);
        tx.commit().unwrap();
    }
    assert_eq!(values(&b),vec![(1,31),(3,43)]);
    for finish in ["rollback","drop"] {
        let mut tx=a.begin().unwrap();
        tx.execute("UPDATE t SET v=88",()).unwrap();
        tx.execute("INSERT INTO t VALUES (4,54)",()).unwrap();
        assert_eq!(tx_values(&mut tx),vec![(1,88),(3,88),(4,54)]);
        if finish=="rollback" { tx.rollback().unwrap(); }
        drop(tx);
        assert_eq!(values(&b),vec![(1,31),(3,43)]);
    }
    exec(&a,"BEGIN"); exec(&a,"UPDATE t SET v=61 WHERE id=1");
    exec(&a,"INSERT INTO t VALUES (5,75)");
    assert_eq!(values(&a),vec![(1,61),(3,43),(5,75)]);
    assert_eq!(values(&b),vec![(1,31),(3,43)]);
    exec(&a,"COMMIT"); assert_eq!(values(&b),vec![(1,61),(3,43),(5,75)]);
    exec(&a,"BEGIN"); exec(&a,"DELETE FROM t");
    assert_eq!(values(&a),vec![]); exec(&a,"ROLLBACK");
    assert_eq!(values(&b),vec![(1,61),(3,43),(5,75)]);
}
fn t02() {
    for (level,snapshot) in [(IsolationLevel::ReadCommitted,false),(IsolationLevel::SnapshotIsolation,true)] {
        let (a,b)=sessions(if snapshot {"f06_native_snapshot"} else {"f06_native_rc"});
        let mut tx=a.begin_with_isolation(level).unwrap();
        // First read occurs after the competing commit: the snapshot starts at BEGIN.
        exec(&b,"UPDATE t SET v=32 WHERE id=1");
        assert_eq!(tx_values(&mut tx),vec![(1,if snapshot {10}else{32}),(2,20)]);
        tx.execute("UPDATE t SET v=54 WHERE id=2",()).unwrap();
        exec(&b,"UPDATE t SET v=76 WHERE id=1");
        assert_eq!(tx_values(&mut tx),vec![(1,if snapshot {10}else{76}),(2,54)]);
        tx.rollback().unwrap();
    }
    let (a,b)=sessions("f06_session_defaults");
    let c=Database::open("memory://f06_session_defaults").unwrap();
    exec(&a,"SET ISOLATION_LEVEL = 'SNAPSHOT'");
    exec(&a,"BEGIN");
    exec(&c,"UPDATE t SET v=35 WHERE id=1");
    assert_eq!(values(&a),vec![(1,10),(2,20)]);
    exec(&c,"SET ISOLATION_LEVEL = 'READ COMMITTED'");
    exec(&c,"UPDATE t SET v=46 WHERE id=1");
    assert_eq!(values(&a),vec![(1,10),(2,20)]);
    exec(&a,"ROLLBACK");
    exec(&a,"BEGIN TRANSACTION ISOLATION LEVEL SNAPSHOT");
    exec(&c,"UPDATE t SET v=57 WHERE id=1");
    assert_eq!(values(&a),vec![(1,46),(2,20)]); exec(&a,"ROLLBACK");
    exec(&a,"SET ISOLATION_LEVEL = 'READ COMMITTED'");
    exec(&b,"SET ISOLATION_LEVEL = 'READ COMMITTED'");
    exec(&a,"BEGIN"); exec(&b,"BEGIN");
    exec(&c,"UPDATE t SET v=68 WHERE id=1");
    assert_eq!(values(&a),vec![(1,68),(2,20)]);
    assert_eq!(values(&b),vec![(1,68),(2,20)]);
    exec(&a,"ROLLBACK"); exec(&b,"ROLLBACK");

}
fn t03() {
    let (a,b)=sessions("f06_savepoints");
    for sql in ["SAVEPOINT p","ROLLBACK TO SAVEPOINT p","RELEASE SAVEPOINT p"] { reject(&a,sql); }
    exec(&a,"BEGIN"); exec(&a,"UPDATE t SET v=11 WHERE id=1");
    exec(&a,"SAVEPOINT p"); exec(&a,"UPDATE t SET v=22 WHERE id=2");
    exec(&a,"SAVEPOINT q"); exec(&a,"INSERT INTO t VALUES (3,33)");
    exec(&a,"ROLLBACK TO SAVEPOINT p");
    assert_eq!(values(&a),vec![(1,11),(2,20)]);
    reject(&a,"ROLLBACK TO SAVEPOINT q");
    exec(&a,"DELETE FROM t WHERE id=2"); exec(&a,"ROLLBACK TO SAVEPOINT p");
    assert_eq!(values(&a),vec![(1,11),(2,20)]);
    exec(&a,"UPDATE t SET v=24 WHERE id=2"); exec(&a,"SAVEPOINT p");
    exec(&a,"UPDATE t SET v=35 WHERE id=1"); exec(&a,"ROLLBACK TO SAVEPOINT p");
    assert_eq!(values(&a),vec![(1,11),(2,24)]);
    exec(&a,"SAVEPOINT later"); exec(&a,"RELEASE SAVEPOINT p");
    reject(&a,"RELEASE SAVEPOINT later");
    assert_eq!(values(&a),vec![(1,11),(2,24)]);
    assert_eq!(values(&b),vec![(1,10),(2,20)]);
    exec(&a,"ROLLBACK TO SAVEPOINT p");
    assert_eq!(values(&a),vec![(1,11),(2,20)]);
    exec(&a,"RELEASE SAVEPOINT p"); reject(&a,"RELEASE SAVEPOINT p");
    reject(&a,"ROLLBACK TO SAVEPOINT absent");
    exec(&a,"SAVEPOINT completed"); exec(&a,"COMMIT");
    assert_eq!(values(&b),vec![(1,11),(2,20)]);
    exec(&a,"BEGIN"); reject(&a,"ROLLBACK TO SAVEPOINT completed");
    exec(&a,"SAVEPOINT abandoned"); exec(&a,"ROLLBACK");
    exec(&a,"BEGIN"); reject(&a,"RELEASE SAVEPOINT abandoned"); exec(&a,"ROLLBACK");
    let mut tx=a.begin().unwrap();
    tx.execute("SAVEPOINT native",()).unwrap();
    tx.execute("UPDATE t SET v=72 WHERE id=2",()).unwrap();
    tx.execute("ROLLBACK TO SAVEPOINT native",()).unwrap();
    assert_eq!(tx_values(&mut tx),vec![(1,11),(2,20)]);
    tx.execute("DELETE FROM t WHERE id=2",()).unwrap();
    tx.execute("ROLLBACK TO SAVEPOINT native",()).unwrap();
    assert_eq!(tx_values(&mut tx),vec![(1,11),(2,20)]);
    tx.execute("RELEASE SAVEPOINT native",()).unwrap();
    assert!(tx.execute("ROLLBACK TO SAVEPOINT native",()).is_err());
    tx.rollback().unwrap();
}
fn t04() {
    let (a,b)=sessions("f06_disjoint");
    let mut x=a.begin_with_isolation(IsolationLevel::SnapshotIsolation).unwrap();
    let mut y=b.begin_with_isolation(IsolationLevel::SnapshotIsolation).unwrap();
    x.execute("UPDATE t SET v=31 WHERE id=1",()).unwrap();
    y.execute("UPDATE t SET v=42 WHERE id=2",()).unwrap();
    x.commit().unwrap(); y.commit().unwrap();
    assert_eq!(values(&a),vec![(1,31),(2,42)]);
    let mut x=a.begin_with_isolation(IsolationLevel::SnapshotIsolation).unwrap();
    let mut y=b.begin_with_isolation(IsolationLevel::SnapshotIsolation).unwrap();
    assert_eq!(tx_values(&mut x),vec![(1,31),(2,42)]);
    assert_eq!(tx_values(&mut y),vec![(1,31),(2,42)]);
    let wx=x.execute("UPDATE t SET v=53 WHERE id=1",());
    let wy=y.execute("UPDATE t SET v=64 WHERE id=1",());
    let cx=if wx.is_ok() {x.commit()} else {wx.map(|_|())};
    let cy=if wy.is_ok() {y.commit()} else {wy.map(|_|())};
    println!("conflict completion: {cx:?}, {cy:?}");
    assert_ne!(cx.is_ok(),cy.is_ok(),"exactly one contender must succeed");
    drop(x); drop(y);
    assert_eq!(values(&a),vec![(1,if cx.is_ok(){53}else{64}),(2,42)]);
}
fn t05() {
    let (a,b)=sessions("f06_statement_failure");
    exec(&a,"BEGIN"); exec(&a,"UPDATE t SET v=31 WHERE id=1");
    reject(&a,"INSERT INTO t VALUES (3,43),(1,99)");
    assert_eq!(values(&a),vec![(1,31),(2,20)]);
    assert_eq!(values(&b),vec![(1,10),(2,20)]);
    exec(&a,"COMMIT"); assert_eq!(values(&b),vec![(1,31),(2,20)]);
    let mut tx=a.begin().unwrap();
    tx.execute("UPDATE t SET v=29 WHERE id=2",()).unwrap();
    assert!(tx.execute("INSERT INTO t VALUES (9,90),(1,99)",()).is_err());
    assert_eq!(tx_values(&mut tx),vec![(1,31),(2,29)]);
    assert_eq!(values(&b),vec![(1,31),(2,20)]);
    tx.execute("UPDATE t SET v=20 WHERE id=2",()).unwrap();
    tx.commit().unwrap();
    assert_eq!(values(&b),vec![(1,31),(2,20)]);
    let mut x=a.begin_with_isolation(IsolationLevel::SnapshotIsolation).unwrap();
    let mut y=b.begin_with_isolation(IsolationLevel::SnapshotIsolation).unwrap();
    x.execute("INSERT INTO t VALUES (3,43)",()).unwrap();
    y.execute("INSERT INTO t VALUES (4,54)",()).unwrap();
    let wx=x.execute("UPDATE t SET v=65 WHERE id=1",());
    let wy=y.execute("UPDATE t SET v=76 WHERE id=1",());
    let cx=if wx.is_ok(){x.commit()}else{wx.map(|_|())};
    let cy=if wy.is_ok(){y.commit()}else{wy.map(|_|())};
    assert_ne!(cx.is_ok(),cy.is_ok());
    // Before rollback/drop of the loser, its earlier successful insert is private.
    assert_eq!(values(&a),if cx.is_ok(){vec![(1,65),(2,20),(3,43)]}else{vec![(1,76),(2,20),(4,54)]});
    drop(x); drop(y);
    assert_eq!(values(&b),if cx.is_ok(){vec![(1,65),(2,20),(3,43)]}else{vec![(1,76),(2,20),(4,54)]});
    exec(&a,"CREATE TABLE u (id INTEGER PRIMARY KEY, code INTEGER UNIQUE)");
    let mut x=a.begin().unwrap(); let mut y=b.begin().unwrap();
    x.execute("INSERT INTO u VALUES (1,91)",()).unwrap();
    y.execute("INSERT INTO t VALUES (8,88)",()).unwrap();
    let write=y.execute("INSERT INTO u VALUES (2,91)",());
    println!("competing unique insert: {write:?}");
    x.commit().unwrap();
    if write.is_ok() {
        let commit=y.commit(); println!("unique commit: {commit:?}");
        assert!(commit.is_err());
    } else {
        // Rejection may be eager; never commit the remaining successful work.
        assert!(write.is_err());
    }
    assert!(read_rows(&a,"SELECT * FROM t WHERE id=8").unwrap().is_empty());
    assert_eq!(a.query_one::<i64,_>("SELECT id FROM u",()).unwrap(),1);
    assert_eq!(a.query_one::<i64,_>("SELECT COUNT(*) FROM u",()).unwrap(),1);
    drop(y);
    assert!(read_rows(&b,"SELECT * FROM t WHERE id=8").unwrap().is_empty());

}
fn t06() {
    for (name,alter) in [("f06_add","ALTER TABLE t ADD COLUMN extra INTEGER"),("f06_drop","ALTER TABLE t DROP COLUMN extra")] {
        let (a,b)=sessions(name);
        if name=="f06_drop" {exec(&a,"ALTER TABLE t ADD COLUMN extra INTEGER");}
        let mut tx=a.begin().unwrap();
        tx.execute("UPDATE t SET v=31 WHERE id=1",()).unwrap();
        exec(&b,alter);
        let result=tx.commit(); println!("schema commit: {result:?}"); assert!(result.is_err());
        assert_eq!(values(&b),vec![(1,10),(2,20)]);
        drop(tx); assert_eq!(values(&b),vec![(1,10),(2,20)]);
    }
    let (a,b)=sessions("f06_truncate_conflict");
    let mut tx=a.begin().unwrap(); tx.execute("UPDATE t SET v=31 WHERE id=1",()).unwrap();
    reject(&b,"TRUNCATE TABLE t");
    assert_eq!(values(&b),vec![(1,10),(2,20)]);
    assert_eq!(tx_values(&mut tx),vec![(1,31),(2,20)]);
    tx.commit().unwrap(); assert_eq!(values(&b),vec![(1,31),(2,20)]);
    exec(&b,"TRUNCATE TABLE t"); assert_eq!(values(&b),vec![]);
}
fn t07() {
    let (a,b)=sessions("f06_ddl_rollback");
    exec(&a,"BEGIN"); exec(&a,"CREATE TABLE fresh (id INTEGER)");
    exec(&a,"INSERT INTO fresh VALUES (17)");
    assert_eq!(a.query_one::<i64,_>("SELECT id FROM fresh",()).unwrap(),17);
    exec(&a,"CREATE TABLE another (id INTEGER)");
    exec(&a,"INSERT INTO another VALUES (23)");
    assert_eq!(a.query_one::<i64,_>("SELECT id FROM another",()).unwrap(),23);
    exec(&a,"ROLLBACK");
    for table in ["fresh","another"] {
        reject(&a,&format!("SELECT * FROM {table}"));
        reject(&b,&format!("SELECT * FROM {table}"));
    }
    assert_eq!(values(&b),vec![(1,10),(2,20)]);
    exec(&a,"BEGIN"); exec(&a,"TRUNCATE TABLE t"); assert_eq!(values(&a),vec![]);
    exec(&a,"ROLLBACK"); assert_eq!(values(&b),vec![]);
    exec(&b,"INSERT INTO t VALUES (7,87)"); assert_eq!(values(&a),vec![(7,87)]);
}
fn t08() {
    let (a,b)=sessions("f06_identity");
    assert_eq!(identity(&a),None);
    exec(&a,"BEGIN"); let first=identity(&a).unwrap(); assert!(first>0);
    exec(&a,"UPDATE t SET v=31 WHERE id=1"); assert_eq!(identity(&a),Some(first));
    assert_eq!(values(&a),vec![(1,31),(2,20)]); assert_eq!(identity(&a),Some(first));
    assert_eq!(identity(&b),None);
    exec(&b,"BEGIN"); let other=identity(&b).unwrap(); assert!(other>0); assert_ne!(other,first);
    exec(&b,"ROLLBACK"); assert_eq!(identity(&b),None);
    exec(&a,"COMMIT"); assert_eq!(identity(&a),None);
    exec(&a,"BEGIN"); let second=identity(&a).unwrap(); assert!(second>0);
    assert_ne!(second,first); assert_ne!(second,other);
    exec(&a,"DELETE FROM t"); assert_eq!(identity(&a),Some(second));
    exec(&a,"ROLLBACK"); assert_eq!(identity(&a),None);
    assert_eq!(values(&a),vec![(1,31),(2,20)]);
}
fn main() {
    match std::env::args().nth(1).unwrap().as_str() {
        "t01"=>t01(),"t02"=>t02(),"t03"=>t03(),"t04"=>t04(),
        "t05"=>t05(),"t06"=>t06(),"t07"=>t07(),"t08"=>t08(),_=>panic!("unknown case")
    }
}
'''

@pytest.fixture(scope="module")
def transaction_client(tmp_path_factory):
    return build_rust_client(RUST_TRANSACTION_SUPPORT + TRANSACTION_CASES,
                             tmp_path_factory.mktemp("f06-rust"))


def test_commit_rollback_and_drop(transaction_client):
    run_native_client(transaction_client, "t01")


def test_isolation_and_session_choices(transaction_client):
    run_native_client(transaction_client, "t02")


def test_savepoint_stack_and_lifetime(transaction_client):
    run_native_client(transaction_client, "t03")


def test_disjoint_writes_and_snapshot_conflicts(transaction_client):
    run_native_client(transaction_client, "t04")


def test_failed_work_does_not_publish(transaction_client):
    run_native_client(transaction_client, "t05")


def test_schema_conflicts_and_truncate_guard(transaction_client):
    run_native_client(transaction_client, "t06")


def test_create_and_truncate_rollback_boundaries(transaction_client):
    run_native_client(transaction_client, "t07")


def test_transaction_identity(transaction_client):
    run_native_client(transaction_client, "t08")


def test_c_transaction_visibility_and_completion(tmp_path):
    result = run_c_client(C_TRANSACTION_SUPPORT + r'''
int main(void) {
    for (int snapshot=0;snapshot<2;snapshot++) {
        VelnoraDB *a=NULL,*b=NULL; VelnoraTx *tx=NULL;
        assert(velnora_open_in_memory(&a)==VELNORA_OK);
        assert(velnora_clone(a,&b)==VELNORA_OK);
        c_exec(a,"CREATE TABLE t (id INTEGER PRIMARY KEY,v INTEGER)");
        c_exec(a,"INSERT INTO t VALUES (1,10),(2,20)");
        assert(velnora_begin_with_isolation(a,snapshot?VELNORA_ISOLATION_SNAPSHOT:VELNORA_ISOLATION_READ_COMMITTED,&tx)==VELNORA_OK);
        c_exec(b,"UPDATE t SET v=31 WHERE id=1");
        assert(c_tx_number(tx,"SELECT v FROM t WHERE id=1")== (snapshot?10:31));
        assert(velnora_tx_exec(tx,"UPDATE t SET v=42 WHERE id=2",NULL)==VELNORA_OK);
        assert(c_tx_number(tx,"SELECT v FROM t WHERE id=2")==42);
        assert(c_number(b,"SELECT v FROM t WHERE id=2")==20);
        c_exec(b,"UPDATE t SET v=53 WHERE id=1");
        assert(c_tx_number(tx,"SELECT v FROM t WHERE id=1")== (snapshot?10:53));
        assert(velnora_tx_commit(tx)==VELNORA_OK); tx=NULL;
        assert(c_number(b,"SELECT v FROM t WHERE id=2")==42);
        assert(c_number(b,"SELECT v FROM t WHERE id=1")==53);
        assert(velnora_begin(a,&tx)==VELNORA_OK);
        assert(velnora_tx_exec(tx,"DELETE FROM t",NULL)==VELNORA_OK);
        assert(c_tx_number(tx,"SELECT COUNT(*) FROM t")==0);
        assert(c_number(b,"SELECT COUNT(*) FROM t")==2);
        assert(velnora_tx_rollback(tx)==VELNORA_OK); tx=NULL;
        assert(c_number(b,"SELECT v FROM t WHERE id=1")==53);
        assert(c_number(b,"SELECT v FROM t WHERE id=2")==42);
        assert(velnora_close(b)==VELNORA_OK); assert(velnora_close(a)==VELNORA_OK);
    }
    return 0;
}
''', tmp_path)
    assert result.returncode == 0, (result.stdout, result.stderr)
