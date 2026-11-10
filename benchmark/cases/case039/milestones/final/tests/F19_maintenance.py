# feature: F19
"""Diagnosis and maintenance observations through the documented native and SQL shell."""
import pytest
from F01_helpers import build_rust_client, run_native_client
from F19_helpers import RUST_MAINTENANCE_SUPPORT
from _helpers import run_command


MAINTENANCE_CASES = r'''
fn explain_without_execution() {
    let db=diagnostic_sales_fixture();
    exec(&db,"CREATE TABLE departments (id INTEGER PRIMARY KEY, title TEXT)");
    exec(&db,"INSERT INTO departments VALUES (1,'a'),(2,'b')");
    for (predicate,limit,direction) in [(8,1,"DESC"),(15,2,"ASC")] {
        let sql=format!("EXPLAIN SELECT s.dept,SUM(s.amount) FROM sales s JOIN departments d ON s.dept=d.id WHERE s.amount>{predicate} GROUP BY s.dept ORDER BY s.dept {direction} LIMIT {limit}");
        let plan=diagnostic_plan(&db,&sql);
        diagnostic_source(&plan,"sales");diagnostic_source(&plan,"departments");
        assert_eq!(diagnostic_field(&plan,"Join Cond:"),"(s.dept = d.id)");
        assert_eq!(diagnostic_field(&plan,"Filter:"),format!("(s.amount > {predicate})"));
        assert_eq!(diagnostic_field(&plan,"Group By:"),"s.dept");
        assert_eq!(diagnostic_field(&plan,"Order By:"),format!("s.dept {direction}"));
        assert_eq!(diagnostic_field(&plan,"Limit:"),limit.to_string());
    }
    let plan=diagnostic_plan(&db,"EXPLAIN SELECT title FROM departments WHERE title='a'");
    diagnostic_source(&plan,"departments");
    assert_eq!(diagnostic_field(&plan,"Filter:"),"(title = 'a')");
    let expected=vec![history_row![1,1,7],history_row![2,1,13],history_row![3,2,19]];
    for (sql,changed) in [
        ("INSERT INTO sales VALUES (4,2,91)",vec![history_row![1,1,7],history_row![2,1,13],history_row![3,2,19],history_row![4,2,91]]),
        ("UPDATE sales SET amount=99 WHERE id=1",vec![history_row![1,1,99],history_row![2,1,13],history_row![3,2,19]]),
        ("DELETE FROM sales WHERE id=2",vec![history_row![1,1,7],history_row![3,2,19]]),
    ] {
        // Independent identical starting states and observation sequences; only
        // the EXPLAIN prefix differs between execution and nonexecution arms.
        for explain in [false,true] {
            let arm=diagnostic_sales_fixture();
            history_expect(&arm,"SELECT id,dept,amount FROM sales",expected.clone());
            let statement=if explain {format!("EXPLAIN {sql}")} else {sql.to_string()};
            // EXPLAIN yields rows; the bare statement yields an affected-row count.
            let rows=if explain {read_rows(&arm,&statement).unwrap()} else {exec(&arm,&statement);Vec::new()};
            if explain {
                assert!(!rows.is_empty(),"EXPLAIN must return its plan");
                let plan:Vec<String>=rows.iter().map(|r|r.get_by_name("plan").unwrap()).collect();
                if sql.starts_with("UPDATE") {assert_eq!(diagnostic_field(&plan,"Filter:"),"(id = 1)");}
                if sql.starts_with("DELETE") {assert_eq!(diagnostic_field(&plan,"Filter:"),"(id = 2)");}
            }
            history_expect(&arm,"SELECT id,dept,amount FROM sales",
                if explain {expected.clone()} else {changed.clone()});
        }
    }
}
fn explain_execution() {
    let db=Database::open_in_memory().unwrap();
    exec(&db,"CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)");
    exec(&db,"INSERT INTO t VALUES (1,7),(2,13),(3,19),(4,19),(5,31)");
    exec(&db,"CREATE TABLE tags (id INTEGER PRIMARY KEY)");
    exec(&db,"INSERT INTO tags VALUES (1),(2),(3),(4),(5)");
    let scenarios=[
        ("SELECT id FROM t WHERE v>10 ORDER BY id",vec![history_row![2],history_row![3],history_row![4],history_row![5]],4),
        ("SELECT id FROM t WHERE v>10 ORDER BY id LIMIT 2",vec![history_row![2],history_row![3]],2),
        ("SELECT v FROM t GROUP BY v ORDER BY v",vec![history_row![7],history_row![13],history_row![19],history_row![31]],4),
        ("SELECT id FROM t WHERE v<0",vec![],0),
        ("SELECT DISTINCT v FROM t ORDER BY v",vec![history_row![7],history_row![13],history_row![19],history_row![31]],4),
        ("SELECT t.id FROM t JOIN tags ON t.id=tags.id WHERE t.v>15 ORDER BY t.id LIMIT 1",vec![history_row![3]],1),
    ];
    for (sql,rows,count) in scenarios {
        history_expect(&db,sql,rows);
        let header=if sql.starts_with("SELECT DISTINCT ") {"SELECT DISTINCT"} else {"SELECT"};
        assert_eq!(diagnostic_actual(&diagnostic_plan(&db,&format!("EXPLAIN ANALYZE {sql}")),header),count);
    }
    let plan=diagnostic_plan(&db,"EXPLAIN SELECT t.id FROM t JOIN tags ON t.id=tags.id");
    // Estimates have the separate '(cost=<number> rows=<integer>)' carrier.
    // No estimate is used as the oracle for an actual count.
    let estimates:Vec<_>=plan.iter().filter_map(|s|s.split_once(" (cost=")).collect();
    assert_eq!(estimates.len(),1,"Expected join estimate: {plan:?}");
    let (cost,count)=estimates[0].1.split_once(" rows=").unwrap();
    let _:f64=cost.parse().unwrap();
    let _:u64=count.strip_suffix(')').unwrap().parse().unwrap();
    let plan=diagnostic_plan(&db,"EXPLAIN ANALYZE UPDATE t SET v=42 WHERE id=2");
    assert_eq!(diagnostic_actual(&plan,"UPDATE t"),0);
    assert_eq!(values(&db),vec![(1,7),(2,42),(3,19),(4,19),(5,31)]);
    exec(&db,"CREATE TABLE patterns(value TEXT, pattern TEXT)");
    exec(&db,"INSERT INTO patterns VALUES('abc','[')");
    reject(&db,"SELECT value FROM patterns WHERE value REGEXP pattern");
    reject(&db,"EXPLAIN ANALYZE SELECT value FROM patterns WHERE value REGEXP pattern");
    diagnostic_duration_relation();
    // Missing source and a mutation constraint error both propagate through the public API.
    reject(&db,"EXPLAIN ANALYZE SELECT * FROM nonexistent_source");
    reject(&db,"EXPLAIN ANALYZE SELECT (SELECT v FROM nonexistent_source) FROM t");
    reject(&db,"EXPLAIN ANALYZE INSERT INTO t VALUES (1,999)");
    assert_eq!(values(&db),vec![(1,7),(2,42),(3,19),(4,19),(5,31)]);
}
// Original case-image measurement: medians grew from 42 us to 7430 us
// reported (176.9x), and 50.523 us to 7991.465 us observed (158.2x).
// Three repetitions per side; the assertion only requires an increase.
fn diagnostic_duration_relation() {
    let mut medians=Vec::new();
    for size in [2000u64,200000u64] {
        let db=Database::open_in_memory().unwrap();
        exec(&db,"CREATE TABLE timing(v INTEGER)");
        exec(&db,&format!("INSERT INTO timing SELECT value FROM generate_series(1,{size})"));
        let mut reported=Vec::new();let mut observed=Vec::new();
        for _ in 0..3 {
            let start=std::time::Instant::now();
            let rows=read_rows(&db,"EXPLAIN ANALYZE SELECT v FROM timing WHERE v>=0").unwrap();
            let elapsed=start.elapsed().as_secs_f64();
            let lines:Vec<String>=rows.iter().map(|r|r.get_by_name("plan").unwrap()).collect();
            let (count,duration)=diagnostic_measurement(&lines,"SELECT");
            assert_eq!(count,size);reported.push(duration);observed.push(elapsed);
        }
        reported.sort_by(f64::total_cmp);observed.sort_by(f64::total_cmp);
        medians.push((reported[1],observed[1]));
    }
    println!("duration medians (reported seconds, observed seconds): {medians:?}");
    assert!(medians[1].0>medians[0].0,"reported duration must grow with scanned rows");
    assert!(medians[1].1>medians[0].1,"external elapsed time must independently grow");
}
fn analyze_statistics() {
    let db=Database::open_in_memory().unwrap();
    exec(&db,"CREATE TABLE measured (id INTEGER PRIMARY KEY, n INTEGER, word TEXT, absent INTEGER)");
    exec(&db,"CREATE TABLE empty_data (id INTEGER PRIMARY KEY, n INTEGER)");
    exec(&db,"INSERT INTO measured VALUES (1,-4,'z',NULL),(2,12,'a',NULL),(3,12,'z',NULL),(4,NULL,NULL,NULL)");
    assert_eq!(maintenance_integer(&db,"ANALYZE measured","tables_analyzed"),1);
    assert_eq!(maintenance_integer(&db,"SELECT row_count FROM _sys_table_stats WHERE table_name='measured'","row_count"),4);
    maintenance_columns(&db,"measured",vec![
        ("id",0,4,Some("1"),Some("4")),("n",1,2,Some("-4"),Some("12")),
        ("word",1,2,Some("a"),Some("z")),("absent",4,0,None,None)],&[("id",true),("n",true),("absent",true)]);
    assert_eq!(maintenance_integer(&db,"ANALYZE","tables_analyzed"),2);
    assert_eq!(maintenance_integer(&db,"SELECT row_count FROM _sys_table_stats WHERE table_name='empty_data'","row_count"),0);
    maintenance_columns(&db,"empty_data",vec![("id",0,0,None,None),("n",0,0,None,None)],&[("id",true),("n",true),("absent",true)]);
    exec(&db,"BEGIN");
    exec(&db,"INSERT INTO measured VALUES (5,30,'m',NULL),(6,NULL,'m',NULL)");
    exec(&db,"INSERT INTO empty_data VALUES (9,80)");exec(&db,"COMMIT");
    assert_eq!(maintenance_integer(&db,"ANALYZE","tables_analyzed"),2);
    assert_eq!(maintenance_integer(&db,"SELECT row_count FROM _sys_table_stats WHERE table_name='measured'","row_count"),6);
    assert_eq!(maintenance_integer(&db,"SELECT row_count FROM _sys_table_stats WHERE table_name='empty_data'","row_count"),1);
    maintenance_columns(&db,"empty_data",vec![("id",0,1,Some("9"),Some("9")),("n",0,1,Some("80"),Some("80"))],&[("id",true),("n",true),("absent",true)]);
    maintenance_columns(&db,"measured",vec![
        ("id",0,6,Some("1"),Some("6")),("n",2,3,Some("-4"),Some("30")),
        ("word",1,3,Some("a"),Some("z")),("absent",6,0,None,None)],&[("id",true),("n",true),("absent",true)]);
    exec(&db,"BEGIN");exec(&db,"DELETE FROM measured WHERE id IN (1,4,5)");exec(&db,"COMMIT");
    assert_eq!(maintenance_integer(&db,"ANALYZE measured","tables_analyzed"),1);
    assert_eq!(maintenance_integer(&db,"SELECT row_count FROM _sys_table_stats WHERE table_name='measured'","row_count"),3);
    maintenance_columns(&db,"measured",vec![
        ("id",0,3,Some("2"),Some("6")),("n",1,1,Some("12"),Some("12")),
        ("word",0,3,Some("a"),Some("z")),("absent",3,0,None,None)],&[("id",true),("n",true),("absent",true)]);
    exec(&db,"CREATE TABLE floating_values(v FLOAT)");
    exec(&db,"INSERT INTO floating_values VALUES(-2.5),(3.125),(3.125),(NULL)");
    assert_eq!(maintenance_integer(&db,"ANALYZE floating_values","tables_analyzed"),1);
    maintenance_columns(&db,"floating_values",vec![("v",1,2,Some("-2.5"),Some("3.125"))],&[("v",false)]);
    exec(&db,"CREATE TABLE boolean_values(flag BOOLEAN)");
    exec(&db,"INSERT INTO boolean_values VALUES(TRUE),(FALSE),(TRUE),(NULL)");
    assert_eq!(maintenance_integer(&db,"ANALYZE boolean_values","tables_analyzed"),1);
    let rows=read_rows(&db,"SELECT null_count,distinct_count,min_value,max_value FROM _sys_column_stats WHERE table_name='boolean_values' AND column_name='flag'").unwrap();
    assert_eq!(rows.len(),1);
    assert_eq!(rows[0].get::<i64>(0).unwrap(),1);
    assert_eq!(rows[0].get::<i64>(1).unwrap(),2);
    assert_eq!(rows[0].get::<String>(2).unwrap().to_ascii_lowercase(),"false");
    assert_eq!(rows[0].get::<String>(3).unwrap().to_ascii_lowercase(),"true");
    // The promised exact range must not silently become a small sample.
    exec(&db,"CREATE TABLE exact_range(n INTEGER,word TEXT)");
    exec(&db,"INSERT INTO exact_range SELECT value,CAST(value AS TEXT) FROM generate_series(1,10000)");
    assert_eq!(maintenance_integer(&db,"ANALYZE exact_range","tables_analyzed"),1);
    assert_eq!(maintenance_integer(&db,"SELECT row_count FROM _sys_table_stats WHERE table_name='exact_range'","row_count"),10000);
    maintenance_columns(&db,"exact_range",vec![
        ("n",0,10000,Some("1"),Some("10000")),
        ("word",0,10000,Some("1"),Some("9999"))],&[("n",true)]);
    // A missing analysis target reports zero analyzed tables and a warning.
    assert_eq!(maintenance_integer(&db,"ANALYZE missing_statistics_table","tables_analyzed"),0);
    assert_eq!(maintenance_integer(&db,"SELECT row_count FROM _sys_table_stats WHERE table_name='measured'","row_count"),3);
}
fn persistence_configuration(path: &str) {
    let default_db=Database::open(&format!("file://{path}-default")).unwrap();
    assert_eq!(maintenance_integer(&default_db,"PRAGMA keep_snapshots","keep_snapshots"),3);
    default_db.close().unwrap();
    let db=Database::open(&format!("file://{path}?sync_mode=full&wal_flush_trigger=65536&checkpoint_interval=3600&keep_snapshots=4")).unwrap();
    for (name,expected) in [("sync_mode",2),("wal_flush_trigger",65536),("checkpoint_interval",3600),("keep_snapshots",4)] {
        assert_eq!(maintenance_integer(&db,&format!("PRAGMA {name}"),name),expected);
    }
    for (name,choices) in [("keep_snapshots",[2,5])] {
        for choice in choices {
            assert_eq!(maintenance_integer(&db,&format!("PRAGMA {name}={choice}"),name),choice);
            assert_eq!(maintenance_integer(&db,&format!("PRAGMA {name}"),name),choice);
        }
    }
    for (name,value,original) in [("sync_mode",0,2),("wal_flush_trigger",8192,65536)] {
        reject(&db,&format!("PRAGMA {name}={value}"));
        assert_eq!(maintenance_integer(&db,&format!("PRAGMA {name}"),name),original);
    }
    exec(&db,"CREATE TABLE retained(id INTEGER PRIMARY KEY,v INTEGER)");
    exec(&db,"INSERT INTO retained VALUES(1,0)");
    exec(&db,"PRAGMA keep_snapshots=2");
    let mut identities=Vec::new();
    for value in [11,23,37,49] {
        exec(&db,&format!("UPDATE retained SET v={value} WHERE id=1"));
        let before=if identities.is_empty() {std::collections::BTreeSet::new()}
                   else {snapshot_ids(path,"retained")};
        std::thread::sleep(std::time::Duration::from_millis(20));
        exec(&db,"PRAGMA SNAPSHOT");
        let after=snapshot_ids(path,"retained");
        let added:Vec<_>=after.difference(&before).cloned().collect();
        assert_eq!(added.len(),1);identities.push((added[0].clone(),value));
    }
    for (index,(identity,value)) in identities.iter().enumerate() {
        let sql=format!("PRAGMA RESTORE = '{identity}'");
        if index<2 {reject(&db,&sql);}
        else {exec(&db,&sql);assert_eq!(db.query_one::<i64,_>("SELECT v FROM retained WHERE id=1",()).unwrap(),*value);}
    }
    exec(&db,"PRAGMA keep_snapshots=1");
    assert_eq!(maintenance_integer(&db,"PRAGMA keep_snapshots","keep_snapshots"),1);
    exec(&db,"UPDATE retained SET v=61 WHERE id=1");
    std::thread::sleep(std::time::Duration::from_millis(20));
    exec(&db,"PRAGMA SNAPSHOT");
    for (identity,_) in &identities {reject(&db,&format!("PRAGMA RESTORE = '{identity}'"));}
    exec(&db,"UPDATE retained SET v=72 WHERE id=1");
    exec(&db,"PRAGMA RESTORE");
    assert_eq!(db.query_one::<i64,_>("SELECT v FROM retained WHERE id=1",()).unwrap(),61);
    db.close().unwrap();
}
fn checkpoint_schedule_effect(path: &str) {
    // An explicit checkpoint makes committed rows recoverable on reopening without write synchronization.
    let sub=format!("{path}/explicit");
    let db=Database::open(&format!("file://{sub}?sync_mode=none&checkpoint_interval=0&checkpoint_on_close=off")).unwrap();
    exec(&db,"CREATE TABLE observed (id INTEGER PRIMARY KEY, value INTEGER)");
    exec(&db,"INSERT INTO observed SELECT value,value*101 FROM generate_series(1,70000)");
    exec(&db,"PRAGMA CHECKPOINT");
    db.close().unwrap();
    let reopened=Database::open(&format!("file://{sub}?sync_mode=none&checkpoint_interval=0&checkpoint_on_close=off")).unwrap();
    let rows=read_rows(&reopened,"SELECT id,value FROM observed ORDER BY id").unwrap();
    assert_eq!(rows.len(),70000);
    assert_eq!(rows[0].get::<i64>(0).unwrap(),1); assert_eq!(rows[0].get::<i64>(1).unwrap(),101);
    assert_eq!(rows[69999].get::<i64>(0).unwrap(),70000); assert_eq!(rows[69999].get::<i64>(1).unwrap(),7070000);
    reopened.close().unwrap();
}
fn vacuum_history() {
    let db=Database::open("memory://f19_cleanup").unwrap();
    exec(&db,"CREATE TABLE t (id INTEGER PRIMARY KEY,v INTEGER)");
    exec(&db,"CREATE TABLE other_data (id INTEGER PRIMARY KEY,v INTEGER)");
    let old=history_commit(&db,"INSERT INTO t VALUES (1,10),(2,20)");
    let other_old=history_commit(&db,"INSERT INTO other_data VALUES (8,80)");
    history_commit(&db,"UPDATE t SET v=30 WHERE id=1");
    history_commit(&db,"DELETE FROM t WHERE id=2");
    history_commit(&db,"UPDATE other_data SET v=90 WHERE id=8");
    let history=format!("SELECT id,v FROM t AS OF TRANSACTION {old}");
    let other_history=format!("SELECT id,v FROM other_data AS OF TRANSACTION {other_old}");
    history_expect(&db,&history,vec![history_row![1,10],history_row![2,20]]);
    history_expect(&db,&other_history,vec![history_row![8,80]]);
    for sql in ["VACUUM t","VACUUM"] {
        exec(&db,"BEGIN");
        reject(&db,sql);
        exec(&db,"ROLLBACK");
        history_expect(&db,&history,vec![history_row![1,10],history_row![2,20]]);
        assert_eq!(values(&db),vec![(1,30)]);
    }
    exec(&db,"VACUUM t");
    history_expect(&db,&history,vec![]);
    history_expect(&db,&other_history,vec![history_row![8,80]]);
    assert_eq!(values(&db),vec![(1,30)]);
    history_commit(&db,"UPDATE t SET v=40 WHERE id=1");
    let protected=history_commit(&db,"INSERT INTO t VALUES (2,60)");
    let protected_history=format!("SELECT id,v FROM t AS OF TRANSACTION {protected}");
    let reader=Database::open(db.dsn()).unwrap();
    let mut tx=reader.begin_with_isolation(IsolationLevel::SnapshotIsolation).unwrap();
    assert_eq!(tx_values(&mut tx),vec![(1,40),(2,60)]);
    history_commit(&db,"UPDATE t SET v=50 WHERE id=1");
    history_commit(&db,"DELETE FROM t WHERE id=2");
    history_commit(&db,"INSERT INTO t VALUES (3,70)");
    for sql in ["VACUUM t","VACUUM"] {
        exec(&db,sql);
        assert_eq!(tx_values(&mut tx),vec![(1,40),(2,60)]);
        assert_eq!(values(&db),vec![(1,50),(3,70)]);
        history_expect(&db,&protected_history,vec![history_row![1,40],history_row![2,60]]);
    }
    tx.commit().unwrap();drop(tx);drop(reader);
    exec(&db,"VACUUM");
    history_expect(&db,&protected_history,vec![]);
    history_expect(&db,&other_history,vec![]);
    assert_eq!(values(&db),vec![(1,50),(3,70)]);
    history_expect(&db,"SELECT id,v FROM other_data",vec![history_row![8,90]]);
    reject(&db,"VACUUM missing_cleanup_table");
    assert_eq!(values(&db),vec![(1,50),(3,70)]);
}
fn main() {
    match std::env::args().nth(1).as_deref().unwrap() {
        "explain"=>explain_without_execution(),
        "execution"=>explain_execution(),
        "statistics"=>analyze_statistics(),
        "configuration"=>persistence_configuration(&std::env::args().nth(2).unwrap()),
        "checkpoint_effect"=>checkpoint_schedule_effect(&std::env::args().nth(2).unwrap()),
        "cleanup"=>vacuum_history(),
        other=>panic!("Unknown maintenance scenario: {other}"),
    }
}
'''


@pytest.fixture(scope="module")
def maintenance_client(tmp_path_factory):
    return build_rust_client(RUST_MAINTENANCE_SUPPORT + MAINTENANCE_CASES,
                             tmp_path_factory.mktemp("f19-native"))


def test_explain_operations_without_execution(maintenance_client):
    run_native_client(maintenance_client, "explain")


def test_explain_analyze_actual_rows_and_errors(maintenance_client):
    run_native_client(maintenance_client, "execution")


def test_analyze_statistics_refresh_and_missing_table(maintenance_client):
    result = run_command([maintenance_client, "statistics"],
                         cwd=maintenance_client.parent, timeout=120)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert any(line.startswith(b"Warning:") for line in result.stderr.splitlines()), result.stderr


def test_persistence_configuration_and_read_only_settings(maintenance_client, tmp_path):
    result = run_command([maintenance_client, "configuration", tmp_path / "database"],
                         cwd=maintenance_client.parent, timeout=120)
    assert result.returncode == 0, (result.stdout, result.stderr)


def test_checkpoint_interval_controls_periodic_effect_and_explicit_recovery(maintenance_client, tmp_path):
    result = run_command([maintenance_client, "checkpoint_effect", tmp_path / "database"],
                         cwd=maintenance_client.parent, timeout=120)
    assert result.returncode == 0, (result.stdout, result.stderr)


def test_vacuum_history_and_active_snapshot(maintenance_client):
    run_native_client(maintenance_client, "cleanup")
