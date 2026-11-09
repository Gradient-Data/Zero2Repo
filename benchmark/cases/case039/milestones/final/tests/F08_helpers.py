# feature: F08
"""Persistent public-API scenarios and bounded, owned process coordination."""
import contextlib
import os
import queue
import resource
import signal
import subprocess
import tempfile
import threading
import pytest

from F01_helpers import build_rust_client

from F06_helpers import RUST_TRANSACTION_SUPPORT
from F08_snapshots import RUST_SNAPSHOT_SUPPORT
from _helpers import run_command

PERSISTENCE_CLIENT = RUST_TRANSACTION_SUPPORT + RUST_SNAPSHOT_SUPPORT + r'''
use std::io::{self, Write, BufRead};
use velnora::{Value, DataType};
fn ack(label: &str) { println!("F08 {label}"); io::stdout().flush().unwrap(); }
fn barrier(label: &str) {
    ack(label);
    let mut command=String::new();
    assert!(io::stdin().lock().read_line(&mut command).unwrap()>0);
    assert_eq!(command.trim(),"continue");
}
fn open_file(path: &str, mode: &str)->Database {
    Database::open(&format!("file://{path}?sync_mode={mode}&checkpoint_interval=0&checkpoint_on_close=off")).unwrap()
}
fn pairs(db: &Database, sql: &str)->Vec<(i64,i64)> {
    let rows=read_rows(db,sql).unwrap();
    let answer=rows.iter().map(|r|(r.get(0).unwrap(),r.get(1).unwrap())).collect();
    println!("observed pairs: {answer:?}"); answer
}
fn base(db: &Database) {
    exec(db,"CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)");
    exec(db,"INSERT INTO t VALUES (1,10),(2,20),(3,30)");
}
fn committed(db: &Database) {
    exec(db,"BEGIN");
    exec(db,"UPDATE t SET v=47 WHERE id=1");
    exec(db,"DELETE FROM t WHERE id=2");
    exec(db,"INSERT INTO t VALUES (4,64)");
    exec(db,"COMMIT");
    assert_eq!(values(db),vec![(1,47),(3,30),(4,64)]);
}
fn pending(db: &Database) {
    exec(db,"BEGIN");
    exec(db,"UPDATE t SET v=901 WHERE id=1");
    exec(db,"DELETE FROM t WHERE id=3");
    exec(db,"INSERT INTO t VALUES (5,905)");
    assert_eq!(values(db),vec![(1,901),(4,64),(5,905)]);
}
fn scalar_definition(db: &Database) {
    exec(db,"CREATE TABLE scalars (id INTEGER PRIMARY KEY AUTO_INCREMENT, code TEXT UNIQUE NOT NULL, n INTEGER CHECK(n>0), f FLOAT, b BOOLEAN, note TEXT DEFAULT 'seed', stamp TIMESTAMP, doc JSON)");
    exec(db,"INSERT INTO scalars VALUES (40,'alpha',9007199254740993,3.25,TRUE,NULL,'2024-03-05T06:07:08Z','{\"x\":17,\"label\":\"kept\"}')");
    exec(db,"INSERT INTO scalars (code,n,f,b) VALUES ('beta',7,-0.5,FALSE)");
    exec(db,"DELETE FROM scalars WHERE code='beta'");
    exec(db,"CREATE TABLE refs (id INTEGER PRIMARY KEY, parent INTEGER REFERENCES scalars(id))");
    exec(db,"INSERT INTO refs VALUES (1,40)");
}
fn check_scalars(db: &Database) {
    let r=read_rows(db,"SELECT id,code,n,f,b,note,stamp,doc->>'label',CAST(doc->>'x' AS INTEGER),doc FROM scalars WHERE code='alpha'").unwrap();
    assert_eq!(r.len(),1);
    println!("stored scalar row: {:?}",r[0]);
    for (position,kind) in [(0,DataType::Integer),(1,DataType::Text),(2,DataType::Integer),
                          (3,DataType::Float),(4,DataType::Boolean),(6,DataType::Timestamp),(9,DataType::Json)] {
        assert_eq!(r[0].get_value(position).unwrap().data_type(),kind);
    }
    assert_eq!(r[0].get::<i64>(0).unwrap(),40);
    assert_eq!(r[0].get::<String>(1).unwrap(),"alpha");
    assert_eq!(r[0].get::<i64>(2).unwrap(),9007199254740993);
    assert_eq!(r[0].get::<f64>(3).unwrap(),3.25);
    assert!(r[0].get::<bool>(4).unwrap());
    assert!(matches!(r[0].get_value(5).unwrap(),Value::Null(_)));
    match r[0].get_value(6).unwrap() {
        Value::Timestamp(t)=>assert_eq!(t.to_rfc3339(),"2024-03-05T06:07:08+00:00"),
        x=>panic!("expected timestamp, got {x:?}")
    }
    assert_eq!(r[0].get::<String>(7).unwrap(),"kept");
    assert_eq!(r[0].get::<i64>(8).unwrap(),17);
    let existing_max:i64=db.query_one("SELECT MAX(id) FROM scalars",()).unwrap();
    exec(db,"INSERT INTO scalars (code,n,f,b) VALUES ('next',11,2.5,FALSE)");
    let r=read_rows(db,"SELECT id,n,f,b,note FROM scalars WHERE code='next'").unwrap();
    assert_eq!(r.len(),1); assert!(r[0].get::<i64>(0).unwrap()>existing_max);
    assert_eq!(r[0].get::<i64>(1).unwrap(),11);
    assert_eq!(r[0].get::<f64>(2).unwrap(),2.5);
    assert!(!r[0].get::<bool>(3).unwrap());
    assert_eq!(r[0].get::<String>(4).unwrap(),"seed");
    let before=read_rows(db,"SELECT id,code,n FROM scalars ORDER BY id").unwrap();
    for sql in ["INSERT INTO scalars (id,code,n) VALUES (40,'other',8)",
                "INSERT INTO scalars (code,n) VALUES ('alpha',8)",
                "INSERT INTO scalars (code,n) VALUES (NULL,8)",
                "INSERT INTO scalars (code,n) VALUES ('invalid',0)"] { reject(db,sql); }
    let after=read_rows(db,"SELECT id,code,n FROM scalars ORDER BY id").unwrap();
    let cells=|rows:Vec<ResultRow>|->Vec<(i64,String,i64)> {
        rows.iter().map(|r|(r.get(0).unwrap(),r.get(1).unwrap(),r.get(2).unwrap())).collect()
    };
    assert_eq!(cells(before),cells(after));
    reject(db,"INSERT INTO refs VALUES (2,999)");
    reject(db,"DELETE FROM scalars WHERE id=40");
    assert_eq!(pairs(db,"SELECT id,parent FROM refs ORDER BY id"),vec![(1,40)]);

}
fn backup_rows(db: &Database) {
    let rows=read_rows(db,"SELECT id,code,v FROM saved ORDER BY id").unwrap();
    let got:Vec<(i64,String,i64)>=rows.iter().map(|r|(r.get(0).unwrap(),r.get(1).unwrap(),r.get(2).unwrap())).collect();
    println!("restored rows: {got:?}");
    assert_eq!(got,vec![(1,"one".into(),15),(2,"two".into(),20),(3,"three".into(),30)]);
    assert_eq!(pairs(db,"SELECT id,v FROM extra ORDER BY id"),vec![(8,80)]);
    assert_eq!(pairs(db,"SELECT id,parent_id FROM saved_child ORDER BY id"),vec![(1,1)]);
}
fn backup_initial_rows(db: &Database) {
    assert_eq!(pairs(db,"SELECT id,v FROM saved ORDER BY id"),vec![(1,10),(2,20)]);
    assert_eq!(pairs(db,"SELECT id,v FROM extra ORDER BY id"),vec![(8,80)]);
    assert_eq!(pairs(db,"SELECT id,parent_id FROM saved_child ORDER BY id"),vec![(1,1)]);
}
fn backup_initial_constraints(db: &Database) {
    for sql in ["INSERT INTO saved VALUES (1,'new',40)","INSERT INTO saved VALUES (9,'one',40)",
                "INSERT INTO saved VALUES (9,NULL,40)","INSERT INTO saved VALUES (9,'new',-1)",
                "INSERT INTO saved_child VALUES (2,999)"] { reject(db,sql); }
    backup_initial_rows(db);
}
fn backup_constraints(db: &Database) {
    for sql in ["INSERT INTO saved VALUES (1,'new',40)","INSERT INTO saved VALUES (9,'one',40)",
                "INSERT INTO saved VALUES (9,NULL,40)","INSERT INTO saved VALUES (9,'new',-1)",
                "INSERT INTO saved_child VALUES (2,999)"] { reject(db,sql); }
    backup_rows(db);
}
fn schema_rows(db: &Database, expected: Vec<(i64,i64)>) {
    assert_eq!(pairs(db,"SELECT id,amount FROM evolved ORDER BY id"),expected);
    for row in read_rows(db,"SELECT amount FROM evolved").unwrap() {
        assert!(matches!(row.get_value(0).unwrap(),Value::Integer(_)));
    }
    let rows=read_rows(db,"SELECT title,added FROM evolved ORDER BY id").unwrap();
    let got:Vec<(String,String)>=rows.iter().map(|r|(r.get(0).unwrap(),r.get(1).unwrap())).collect();
    println!("evolved rows: {got:?}");
    assert_eq!(got,vec![("first".into(),"fresh".into()),("third".into(),"fresh".into())]);
    for sql in ["SELECT spare FROM evolved","SELECT old_name FROM evolved","SELECT * FROM rename_source"] {reject(db,sql);}
    assert_eq!(pairs(db,"SELECT id,v FROM rename_target ORDER BY id"),vec![(7,71),(8,83)]);
}
fn main() {
    let args:Vec<String>=std::env::args().collect();
    let phase=&args[1]; let path=&args[2];
    if phase=="open_rejected" {
        let opened=Database::open(&format!("file://{path}"));
        assert!(opened.is_err(),"concurrent open must return Err");
        ack("done"); return;
    }
    if phase=="unreadable_subdirectory" {
        let fault=&args[4];
        let error=std::fs::read_dir(fault).unwrap_err();
        assert_eq!(error.kind(),std::io::ErrorKind::PermissionDenied,
                   "the selected subdirectory must be inaccessible to this caller: {fault}");
        println!("inaccessible subdirectory: {fault}");
        match Database::open(&format!("file://{path}?sync_mode=full&checkpoint_interval=0&checkpoint_on_close=off")) {
            Err(e)=>println!("blocked open: {e}"),
            Ok(db)=>match read_rows(&db,"SELECT id,v FROM t ORDER BY id") {
                Err(e)=>println!("blocked row read: {e}"),
                Ok(rows)=>{
                    let got:Vec<(i64,i64)>=rows.iter()
                        .map(|r|(r.get(0).unwrap(),r.get(1).unwrap())).collect();
                    assert_eq!(got,vec![(1,10),(2,20),(3,30)],
                               "unreadable storage silently changed committed rows: {fault}");
                    println!("close with inaccessible subdirectory: {:?}",db.close());
                }
            }
        }
        ack("done"); return;
    }
    if phase=="unreadable_directory" {
        if phase=="unreadable_directory" { assert!(std::fs::read_dir(path).is_err(),"permission fault must be active"); }
        match Database::open(&format!("file://{path}")) {
            Err(e)=>println!("blocked open: {e}"),
            Ok(db)=>match read_rows(&db,"SHOW TABLES") {
                Err(e)=>println!("blocked catalog read: {e}"),
                Ok(tables)=>{
                    let names:Vec<String>=tables.iter().map(|r|r.get(0).unwrap()).collect();
                    assert!(names.iter().any(|n|n=="t"),"unreadable database became empty: {names:?}");
                    let result=read_rows(&db,"SELECT id,v FROM t ORDER BY id");
                    println!("blocked row read: {result:?}");
                    assert!(result.is_err(),"unreadable storage must return Err");
                }
            }
        }
        ack("done"); return;
    }
    let mode=args.get(3).map(String::as_str).unwrap_or("full");
    let db=open_file(path,mode);
    match phase.as_str() {
        "persist_create"=>{
            base(&db); scalar_definition(&db); committed(&db);
            pending(&db); exec(&db,"ROLLBACK");
            assert_eq!(values(&db),vec![(1,47),(3,30),(4,64)]);
            // Close while a transaction is unfinished; no explicit rollback.
            pending(&db); db.close().unwrap();
        },
        "persist_read"=>{
            assert_eq!(values(&db),vec![(1,47),(3,30),(4,64)]);
            check_scalars(&db); db.close().unwrap();
        },
        "persist_again"=>{
            assert_eq!(values(&db),vec![(1,47),(3,30),(4,64)]);
            let r=read_rows(&db,"SELECT id,n,note FROM scalars WHERE code='next'").unwrap();
            assert_eq!(r.len(),1);assert!(r[0].get::<i64>(0).unwrap()>40);
            assert_eq!(r[0].get::<i64>(1).unwrap(),11);
            assert_eq!(r[0].get::<String>(2).unwrap(),"seed");db.close().unwrap();
        },
        "crash_writer"|"checkpoint_writer"=>{
            base(&db); committed(&db);
            if phase=="checkpoint_writer" {exec(&db,"PRAGMA CHECKPOINT");}
            pending(&db); barrier("ready_to_kill");
            panic!("the parent must terminate this process without close or drop");
        },
        "committed_read"=>{assert_eq!(values(&db),vec![(1,47),(3,30),(4,64)]);db.close().unwrap();},
        "schema_create"=>{
            exec(&db,"CREATE TABLE evolved (id INTEGER PRIMARY KEY, old_name TEXT, amount TEXT, spare INTEGER)");
            exec(&db,"INSERT INTO evolved VALUES (1,'first','12',101),(2,'second','23',202)");
            exec(&db,"PRAGMA CHECKPOINT");
            exec(&db,"INSERT INTO evolved VALUES (3,'third','34',303)");
            exec(&db,"PRAGMA CHECKPOINT");
            exec(&db,"UPDATE evolved SET amount='56' WHERE id=1");
            exec(&db,"DELETE FROM evolved WHERE id=2");
            exec(&db,"ALTER TABLE evolved ADD COLUMN added TEXT DEFAULT 'fresh'");
            exec(&db,"ALTER TABLE evolved DROP COLUMN spare");
            exec(&db,"ALTER TABLE evolved RENAME COLUMN old_name TO title");
            exec(&db,"ALTER TABLE evolved MODIFY COLUMN amount INTEGER");
            exec(&db,"CREATE TABLE rename_source(id INTEGER PRIMARY KEY,v INTEGER)");
            exec(&db,"INSERT INTO rename_source VALUES(7,71),(8,83)");
            exec(&db,"ALTER TABLE rename_source RENAME TO rename_target");
            schema_rows(&db,vec![(1,56),(3,34)]);
            // Reopening below observes the rename through its committed log record.
            db.close().unwrap();
        },
        "schema_read"=>{
            schema_rows(&db,vec![(1,56),(3,34)]);
            exec(&db,"UPDATE evolved SET amount=78 WHERE id=1");
            exec(&db,"DELETE FROM evolved WHERE id=3");
            exec(&db,"INSERT INTO evolved (id,title,amount) VALUES (4,'fourth',90)");
            assert_eq!(pairs(&db,"SELECT id,amount FROM evolved ORDER BY id"),vec![(1,78),(4,90)]);
            exec(&db,"PRAGMA CHECKPOINT");db.close().unwrap();
        },
        "schema_again"=>{
            assert_eq!(pairs(&db,"SELECT id,amount FROM evolved ORDER BY id"),vec![(1,78),(4,90)]);
            let rows=read_rows(&db,"SELECT added FROM evolved WHERE id=4").unwrap();
            assert_eq!(rows[0].get::<String>(0).unwrap(),"fresh");db.close().unwrap();
        },
        "backup_create"=>{
            exec(&db,"CREATE TABLE saved (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, v INTEGER CHECK(v>0))");
            exec(&db,"CREATE TABLE extra (id INTEGER PRIMARY KEY, v INTEGER)");
            exec(&db,"CREATE TABLE saved_child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES saved(id))");
            exec(&db,"INSERT INTO saved VALUES (1,'one',10),(2,'two',20)");
            exec(&db,"INSERT INTO extra VALUES (8,80)");
            exec(&db,"INSERT INTO saved_child VALUES (1,1)");
            exec(&db,"PRAGMA CHECKPOINT");
            reject(&db,"PRAGMA RESTORE");
            backup_initial_rows(&db);
            exec(&db,"PRAGMA SNAPSHOT");
            db.close().unwrap();

            let db=open_file(path,mode);
            let identities=snapshot_ids(path,"saved");assert_eq!(identities.len(),1);
            let older_timestamp=identities.into_iter().next().unwrap();
            // Maintenance on the caller's own explicit transaction must fail.
            // The existing snapshot and populated table rule out an absent-target refusal.
            for operation in ["PRAGMA CHECKPOINT", "PRAGMA SNAPSHOT", "PRAGMA RESTORE"] {
                exec(&db,"BEGIN");
                exec(&db,"UPDATE saved SET v=99 WHERE id=1");
                reject(&db,operation);
                assert_eq!(pairs(&db,"SELECT id,v FROM saved ORDER BY id"),vec![(1,99),(2,20)]);
                exec(&db,"ROLLBACK");
                backup_initial_rows(&db);
            }
            exec(&db,"UPDATE saved SET v=15 WHERE id=1");
            exec(&db,"INSERT INTO saved VALUES (3,'three',30)");
            let other=Database::open(db.dsn()).unwrap();let mut tx=other.begin().unwrap();
            tx.execute("UPDATE saved SET v=999 WHERE id=1",()).unwrap();
            tx.execute("DELETE FROM saved WHERE id=2",()).unwrap();
            tx.execute("INSERT INTO saved VALUES (4,'dirty',444)",()).unwrap();
            let dirty=tx.query("SELECT id,v FROM saved ORDER BY id",()).and_then(|r|r.collect_vec()).unwrap();
            let dirty:Vec<(i64,i64)>=dirty.iter().map(|r|(r.get(0).unwrap(),r.get(1).unwrap())).collect();
            assert_eq!(dirty,vec![(1,999),(3,30),(4,444)]);
            backup_rows(&db);
            std::thread::sleep(std::time::Duration::from_millis(20));
            exec(&db,"PRAGMA SNAPSHOT");tx.rollback().unwrap();drop(tx);drop(other);

            // Select the older snapshot using its public API identity, not a file name.
            exec(&db,&format!("PRAGMA RESTORE = '{older_timestamp}'"));
            backup_initial_constraints(&db);
            exec(&db,"PRAGMA RESTORE");
            backup_constraints(&db);

            exec(&db,"DROP TABLE saved_child");
            exec(&db,"DROP TABLE saved");
            exec(&db,"DELETE FROM extra");
            exec(&db,"PRAGMA CHECKPOINT");
            exec(&db,"PRAGMA RESTORE");backup_rows(&db);backup_constraints(&db);
            reject(&db,"PRAGMA RESTORE = '19000101-000000.000'");backup_rows(&db);
            db.close().unwrap();
        },
        "backup_read"=>{backup_rows(&db);backup_constraints(&db);db.close().unwrap();},
        "lock_owner"=>{base(&db);barrier("owns_database");db.close().unwrap();},
        "plain_create"=>{base(&db);exec(&db,"PRAGMA CHECKPOINT");db.close().unwrap();},
        "plain_read"=>{assert_eq!(values(&db),vec![(1,10),(2,20),(3,30)]);db.close().unwrap();},
        "io_writer"=>{
            base(&db);barrier("limit_ready");
            reject(&db,"INSERT INTO t VALUES (9,90)");barrier("fault_observed");
            // An independent real file proves that the same process can write and sync again.
            let probe=std::path::Path::new(path).join("external-recovery-probe");
            {let mut f=std::fs::File::create(&probe).unwrap();f.write_all(b"storage restored").unwrap();f.sync_all().unwrap();}
            assert_eq!(std::fs::read(&probe).unwrap(),b"storage restored");std::fs::remove_file(probe).unwrap();
            for sql in ["INSERT INTO t VALUES (10,100)","UPDATE t SET v=77 WHERE id=1","DELETE FROM t WHERE id=2"] {reject(&db,sql);}
            // A poisoned database may also report its earlier error at close; the
            // requirement does not prescribe close's result on this path.
            println!("close after I/O failure: {:?}",db.close());drop(db);
            ack("done");return;
        },
        "io_reopen"=>{
            exec(&db,"INSERT INTO t VALUES (10,100)");
            exec(&db,"UPDATE t SET v=77 WHERE id=1");exec(&db,"DELETE FROM t WHERE id=2");
            assert_eq!(pairs(&db,"SELECT id,v FROM t WHERE id IN (1,2,3,10) ORDER BY id"),vec![(1,77),(3,30),(10,100)]);
            db.close().unwrap();
        },
        _=>panic!("unknown scenario {phase}")
    }
    ack("done");
}
'''



def persistence_run(binary, phase, path, mode="full", *, demote=False, fault_path=None):
    if not demote:
        command = [binary, phase, path, mode]
        if fault_path is not None:
            command.append(fault_path)
        result = run_command(command, cwd=binary.parent, timeout=120)
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert b"F08 done\n" in result.stdout, result.stdout
        return result.stdout
    with persistence_process(binary, phase, path, mode, demote=True,
                             fault_path=fault_path) as child:
        child.wait_for("done")
        child.finish()


class PersistenceProcess:
    """A child-client protocol, not a parser for product diagnostics."""
    def __init__(self, binary, phase, path, mode, demote, fault_path):
        self.lines = queue.Queue()
        self.transcript = []
        self.errors = tempfile.TemporaryFile()
        def prepare():
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            if demote and os.geteuid() == 0:
                os.setgroups([])
                os.setgid(65534)
                os.setuid(65534)
        command = [str(binary), phase, str(path), mode]
        if fault_path is not None:
            command.append(str(fault_path))
        self.process = subprocess.Popen(command,
                                        cwd="/tmp", stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.errors,
                                        preexec_fn=prepare)
        def read_stdout():
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put(None)
        self.reader = threading.Thread(target=read_stdout, daemon=True)
        self.reader.start()

    def diagnostics(self):
        self.errors.flush()
        self.errors.seek(0)
        return b"".join(self.transcript), self.errors.read()

    def wait_for(self, label):
        import time
        deadline = time.monotonic() + 120
        wanted = f"F08 {label}\n".encode()
        while True:
            remaining = deadline - time.monotonic()
            assert remaining > 0, self.diagnostics()
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty as error:
                raise AssertionError(self.diagnostics()) from error
            assert line is not None, self.diagnostics()
            self.transcript.append(line)
            if line == wanted:
                return

    def proceed(self):
        self.process.stdin.write(b"continue\n")
        self.process.stdin.flush()

    def finish(self):
        self.process.wait(timeout=120)
        assert self.process.returncode == 0, self.diagnostics()

    def crash(self):
        assert self.process.poll() is None, self.diagnostics()
        self.process.kill()
        self.process.wait(timeout=10)
        assert self.process.returncode == -signal.SIGKILL, self.diagnostics()

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=10)
        self.reader.join(timeout=5)
        assert not self.reader.is_alive(), "Client output reader did not finish"
        self.process.stdin.close()
        self.process.stdout.close()
        self.errors.close()


@contextlib.contextmanager
def persistence_process(binary, phase, path, mode="full", *, demote=False, fault_path=None):
    child = PersistenceProcess(binary, phase, path, mode, demote, fault_path)
    try:
        yield child
    finally:
        child.close()


def persistence_limit(child, soft):
    current = resource.prlimit(child.process.pid, resource.RLIMIT_FSIZE)
    resource.prlimit(child.process.pid, resource.RLIMIT_FSIZE, (soft, current[1]))
    return current[0]


@pytest.fixture(scope="module")
def persistence_client(tmp_path_factory):
    return build_rust_client(PERSISTENCE_CLIENT, tmp_path_factory.mktemp("f08-client"))
