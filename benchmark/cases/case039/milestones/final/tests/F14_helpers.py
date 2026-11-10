# feature: F14
"""Index observations through public SQL and fully consumed native results."""
import pytest

from F01_helpers import build_rust_client
from F06_helpers import RUST_TRANSACTION_SUPPORT

INDEX_SUPPORT = RUST_TRANSACTION_SUPPORT + r'''
fn index_open(path: &str) -> Database {
    Database::open(&format!("file://{path}?sync_mode=full&checkpoint_interval=0&checkpoint_on_close=off")).unwrap()
}
fn index_catalog(db: &Database, table: &str) -> Vec<(String,String,String,String,bool)> {
    let rows=read_rows(db,&format!("SHOW INDEXES FROM {table}")).unwrap();
    let mut got:Vec<_>=rows.iter().map(|r|(
        r.get_by_name::<String>("table_name").unwrap(),
        r.get_by_name::<String>("index_name").unwrap(),
        r.get_by_name::<String>("column_name").unwrap(),
        r.get_by_name::<String>("index_type").unwrap(),
        r.get_by_name::<bool>("is_unique").unwrap())).collect();
    got.sort();println!("index definitions: {got:?}");got
}
fn index_definition(table: &str,name: &str,columns: &str,kind: &str,unique: bool)
    -> (String,String,String,String,bool) {
    (table.into(),name.into(),columns.into(),kind.into(),unique)
}
fn index_ids(db: &Database,sql: &str) -> Vec<i64> {
    let got=read_rows(db,sql).unwrap().iter().map(|r|r.get(0).unwrap()).collect();
    println!("{sql}: {got:?}");got
}
fn index_key_rows(db: &Database) -> Vec<(i64,Option<String>,Option<i64>)> {
    let got=read_rows(db,"SELECT id,code,n FROM keys ORDER BY id").unwrap().iter()
        .map(|r|(r.get(0).unwrap(),r.get(1).unwrap(),r.get(2).unwrap())).collect();
    println!("key rows: {got:?}");got
}
fn index_tx_numbers(tx: &mut Transaction) -> Vec<(i64,Option<i64>)> {
    let got=tx.query("SELECT id,n FROM items WHERE n>=0 OR n IS NULL ORDER BY id",())
        .and_then(|r|r.collect_vec()).unwrap().iter()
        .map(|r|(r.get(0).unwrap(),r.get(1).unwrap())).collect();
    println!("transaction numbers: {got:?}");got
}
fn index_predicates(db: &Database,changed: bool) {
    let cases:Vec<(&str,Vec<i64>,Vec<i64>)>=vec![
        ("WHERE n=20 ORDER BY id",vec![2,3],vec![2,7]),
        ("WHERE n BETWEEN 10 AND 30 ORDER BY id",vec![1,2,3],vec![1,2,4,7]),
        ("WHERE n IN (-5,20,40) ORDER BY id",vec![2,3,5,6],vec![2,5,6,7]),
        ("WHERE n IS NULL ORDER BY id",vec![4],vec![]),
        ("WHERE n IS NOT NULL ORDER BY id",vec![1,2,3,5,6],vec![1,2,4,5,6,7]),
        ("WHERE label='elm' ORDER BY id",vec![1,3],vec![7]),
        ("WHERE flag=TRUE ORDER BY id",vec![1,3,6],vec![4,6,7]),
        ("WHERE label='elm' AND n=20 ORDER BY id",vec![3],vec![7]),
        ("WHERE label IN ('ash','fir') ORDER BY id",vec![2,4,6],vec![1,2,4,6]),
        ("WHERE label IS NULL ORDER BY id",vec![5],vec![5]),
        ("WHERE flag IS NULL ORDER BY id",vec![4],vec![]),
        ("ORDER BY n DESC NULLS LAST,id",vec![5,2,3,1,6,4],vec![5,1,2,7,4,6]),
    ];
    for (suffix,before,after) in cases {
        assert_eq!(index_ids(db,&format!("SELECT id FROM items {suffix}")),
                   if changed {after} else {before},"{suffix}");
    }
}
fn index_saved_definitions(db: &Database) {
    assert_eq!(index_catalog(db,"saved"),vec![
        index_definition("saved","by_number","n","BTREE",false),
        index_definition("saved","by_region_number","(region, n)","MULTICOLUMN",true),
        index_definition("saved","by_token","token","HASH",true),
    ]);
}
fn index_saved_rows(db: &Database) -> Vec<(i64,String,i64,String)> {
    let got=read_rows(db,"SELECT id,token,n,region FROM saved ORDER BY id").unwrap().iter()
        .map(|r|(r.get(0).unwrap(),r.get(1).unwrap(),r.get(2).unwrap(),r.get(3).unwrap())).collect();
    println!("saved rows: {got:?}");got
}
fn index_saved_constraints(db: &Database) {
    for sql in [
        "INSERT INTO saved (id,token,n,region) VALUES (9,'cedar',8,'north')",
        "INSERT INTO saved (id,token,n,region) VALUES (9,'new',2,'north')",
        "UPDATE saved SET token='cedar' WHERE id=2",
        "UPDATE saved SET n=2,region='north' WHERE id=2",
    ] {
        reject(db,sql);
        assert_eq!(index_saved_rows(db),vec![(1,"cedar".into(),2,"north".into()),(2,"birch".into(),7,"south".into())]);
    }
}
fn index_column_types(db: &Database, table: &str) -> Vec<(String,String)> {
    let got=read_rows(db,&format!("DESCRIBE {table}")).unwrap().iter()
        .map(|r|(r.get_by_name("Field").unwrap(),r.get_by_name("Type").unwrap())).collect();
    println!("column definitions: {got:?}");got
}
'''

INDEX_CASES = r'''
fn index_lifecycle() {
    let db=Database::open_in_memory().unwrap();
    exec(&db,"CREATE TABLE catalog (id INTEGER PRIMARY KEY,n INTEGER,label TEXT,flag BOOLEAN,spare INTEGER)");
    exec(&db,"INSERT INTO catalog VALUES (1,9,'oak',TRUE,6),(2,2,'ash',FALSE,8),(3,9,'ash',NULL,4)");
    assert!(index_catalog(&db,"catalog").is_empty());
    for sql in [
        "CREATE INDEX by_n ON catalog(n) USING BTREE",
        "CREATE INDEX by_label ON catalog(label) USING HASH",
        "CREATE INDEX by_flag ON catalog(flag) USING BITMAP",
        "CREATE UNIQUE INDEX by_pair ON catalog(label,n)",
    ] {exec(&db,sql);}
    let expected=vec![
        index_definition("catalog","by_flag","flag","BITMAP",false),
        index_definition("catalog","by_label","label","HASH",false),
        index_definition("catalog","by_n","n","BTREE",false),
        index_definition("catalog","by_pair","(label, n)","MULTICOLUMN",true),
    ];
    assert_eq!(index_catalog(&db,"catalog"),expected);
    for sql in [
        "CREATE INDEX missing_table ON absent(n)",
        "CREATE INDEX missing_column ON catalog(absent)",
        "CREATE INDEX by_n ON catalog(spare)",
    ] {
        reject(&db,sql);assert_eq!(index_catalog(&db,"catalog"),expected);
        assert_eq!(index_ids(&db,"SELECT id FROM catalog ORDER BY id"),vec![1,2,3]);
    }
    for (sql,ids) in [
        ("SELECT id FROM catalog WHERE n=9 ORDER BY id",vec![1,3]),
        ("SELECT id FROM catalog WHERE label='ash' ORDER BY id",vec![2,3]),
        ("SELECT id FROM catalog WHERE flag=FALSE",vec![2]),
        ("SELECT id FROM catalog WHERE label='ash' AND n=9",vec![3]),
    ] {assert_eq!(index_ids(&db,sql),ids);}
    for name in ["by_flag","by_label","by_n","by_pair"] {
        exec(&db,&format!("DROP INDEX {name} ON catalog"));
    }
    assert!(index_catalog(&db,"catalog").is_empty());
    assert_eq!(index_ids(&db,"SELECT id FROM catalog ORDER BY id"),vec![1,2,3]);
    exec(&db,"CREATE INDEX by_pair ON catalog(n,label)");
    assert_eq!(index_catalog(&db,"catalog"),vec![index_definition("catalog","by_pair","(n, label)","MULTICOLUMN",false)]);
    exec(&db,"DROP INDEX by_pair ON catalog");
    exec(&db,"CREATE INDEX by_triple ON catalog(label,n,flag)");
    assert_eq!(index_catalog(&db,"catalog"),vec![index_definition("catalog","by_triple","(label, n, flag)","MULTICOLUMN",false)]);
    assert_eq!(index_ids(&db,"SELECT id FROM catalog WHERE label='ash' AND n=9 AND flag IS NULL"),vec![3]);
}
fn index_uniqueness(_path: &str) {
    for composite in [false,true] {
        let db=Database::open_in_memory().unwrap();
        exec(&db,"CREATE TABLE keys (id INTEGER PRIMARY KEY,code TEXT,n INTEGER)");
        exec(&db,"INSERT INTO keys VALUES (1,'ash',3),(2,'ash',3)");
        let columns=if composite {"code,n"} else {"code"};
        let create=format!("CREATE UNIQUE INDEX guarded ON keys({columns})");
        reject(&db,&create);
        assert_eq!(index_key_rows(&db),vec![(1,Some("ash".into()),Some(3)),(2,Some("ash".into()),Some(3))]);
        exec(&db,"DELETE FROM keys WHERE id=2");
        exec(&db,"INSERT INTO keys VALUES (3,'birch',3),(4,NULL,3),(5,NULL,3)");
        exec(&db,&create);
        exec(&db,"INSERT INTO keys VALUES (6,NULL,3),(7,NULL,NULL),(8,NULL,NULL)");
        let mut expected=vec![(1,Some("ash".into()),Some(3)),(3,Some("birch".into()),Some(3)),
            (4,None,Some(3)),(5,None,Some(3)),(6,None,Some(3)),(7,None,None),(8,None,None)];
        if composite {
            exec(&db,"INSERT INTO keys VALUES (9,'ash',NULL),(10,'ash',NULL),(11,'ash',4)");
            expected.extend([(9,Some("ash".into()),None),(10,Some("ash".into()),None),(11,Some("ash".into()),Some(4))]);
        }
        assert_eq!(index_key_rows(&db),expected);
        for sql in ["INSERT INTO keys VALUES (12,'ash',3)","UPDATE keys SET code='ash' WHERE id=3"] {
            reject(&db,sql);assert_eq!(index_key_rows(&db),expected);
        }
        if composite {
            reject(&db,"UPDATE keys SET n=3 WHERE id=11");
            assert_eq!(index_key_rows(&db),expected);
        }
        // An accepted update releases the former key; a delete releases its key too.
        exec(&db,"UPDATE keys SET code='elm' WHERE id=1");
        exec(&db,"INSERT INTO keys VALUES (12,'ash',3)");
        exec(&db,"DELETE FROM keys WHERE id=3");
        exec(&db,"INSERT INTO keys VALUES (13,'birch',3)");
        expected[0].1=Some("elm".into());expected.remove(1);
        expected.extend([(12,Some("ash".into()),Some(3)),(13,Some("birch".into()),Some(3))]);
        assert_eq!(index_key_rows(&db),expected);
        exec(&db,"DROP INDEX guarded ON keys");
        exec(&db,"INSERT INTO keys VALUES (14,'ash',3)");
        exec(&db,"UPDATE keys SET code='ash' WHERE id=13");
        expected.last_mut().unwrap().1=Some("ash".into());expected.push((14,Some("ash".into()),Some(3)));
        assert_eq!(index_key_rows(&db),expected);
        assert!(index_catalog(&db,"keys").is_empty());
    }
}
fn index_wide_uniqueness() {
    let db=Database::open_in_memory().unwrap();
    exec(&db,"CREATE TABLE wide_keys(id INTEGER PRIMARY KEY,a INTEGER,b TEXT,c INTEGER)");
    exec(&db,"INSERT INTO wide_keys VALUES(1,5,'elm',9),(2,5,'elm',9)");
    reject(&db,"CREATE UNIQUE INDEX guarded ON wide_keys(a,b,c)");
    assert_eq!(index_ids(&db,"SELECT id FROM wide_keys ORDER BY id"),vec![1,2]);
    exec(&db,"DELETE FROM wide_keys WHERE id=2");
    exec(&db,"CREATE UNIQUE INDEX guarded ON wide_keys(a,b,c)");
    // Each component participates: sharing any two must remain legal.
    exec(&db,"INSERT INTO wide_keys VALUES(3,6,'elm',9),(4,5,'oak',9),(5,5,'elm',10)");
    for sql in ["INSERT INTO wide_keys VALUES(6,5,'elm',9)",
                "UPDATE wide_keys SET c=9 WHERE id=5"] {
        reject(&db,sql);
        assert_eq!(index_ids(&db,"SELECT id FROM wide_keys ORDER BY id"),vec![1,3,4,5]);
        assert_eq!(index_ids(&db,"SELECT c FROM wide_keys WHERE id=5"),vec![10]);
    }
    exec(&db,"DROP INDEX guarded ON wide_keys");
    exec(&db,"INSERT INTO wide_keys VALUES(6,5,'elm',9)");
    assert_eq!(index_ids(&db,"SELECT id FROM wide_keys WHERE a=5 AND b='elm' AND c=9 ORDER BY id"),vec![1,6]);
}
fn index_persisted_and_bitmap_uniqueness(path: &str) {
    let db=index_open(path);
    exec(&db,"CREATE TABLE persisted(id INTEGER PRIMARY KEY, n INTEGER)");
    exec(&db,"INSERT INTO persisted VALUES(1,17),(2,17),(3,23)");
    exec(&db,"PRAGMA CHECKPOINT");
    reject(&db,"CREATE UNIQUE INDEX guarded ON persisted(n)");
    assert_eq!(index_ids(&db,"SELECT n FROM persisted ORDER BY id"),vec![17,17,23]);
    assert!(index_catalog(&db,"persisted").is_empty());
    exec(&db,"DELETE FROM persisted WHERE id=2");
    exec(&db,"CREATE UNIQUE INDEX guarded ON persisted(n)");
    reject(&db,"INSERT INTO persisted VALUES(4,17)");
    assert_eq!(index_ids(&db,"SELECT n FROM persisted ORDER BY id"),vec![17,23]);
    exec(&db,"CREATE TABLE flags(id INTEGER PRIMARY KEY, flag BOOLEAN)");
    exec(&db,"INSERT INTO flags VALUES(1,TRUE),(2,FALSE),(3,NULL)");
    exec(&db,"CREATE UNIQUE INDEX flag_guard ON flags(flag) USING BITMAP");
    for sql in ["INSERT INTO flags VALUES(4,TRUE)","UPDATE flags SET flag=TRUE WHERE id=2"] {
        reject(&db,sql);
        assert_eq!(index_ids(&db,"SELECT id FROM flags ORDER BY id"),vec![1,2,3]);
        assert_eq!(index_ids(&db,"SELECT id FROM flags WHERE flag=FALSE"),vec![2]);
    }
    exec(&db,"INSERT INTO flags VALUES(4,NULL)");
    assert_eq!(index_ids(&db,"SELECT id FROM flags WHERE flag IS NULL ORDER BY id"),vec![3,4]);
    db.close().unwrap();
}
fn index_consistency(path: &str,snapshot: bool) {
    let db=index_open(path);
    exec(&db,"CREATE TABLE items (id INTEGER PRIMARY KEY,n INTEGER,label TEXT,flag BOOLEAN)");
    exec(&db,"INSERT INTO items VALUES (1,10,'elm',TRUE),(2,20,'ash',FALSE),(3,20,'elm',TRUE),(4,NULL,'ash',NULL),(5,40,NULL,FALSE),(6,-5,'fir',TRUE)");
    exec(&db,"PRAGMA CHECKPOINT");index_predicates(&db,false);
    for sql in ["CREATE INDEX by_n ON items(n) USING BTREE","CREATE INDEX by_label ON items(label) USING HASH",
                "CREATE INDEX by_flag ON items(flag) USING BITMAP","CREATE INDEX by_pair ON items(label,n)"] {exec(&db,sql);}
    index_predicates(&db,false);
    let reader=Database::open(db.dsn()).unwrap();
    let level=if snapshot {IsolationLevel::SnapshotIsolation} else {IsolationLevel::ReadCommitted};
    let mut tx=reader.begin_with_isolation(level).unwrap();
    let before=vec![(1,Some(10)),(2,Some(20)),(3,Some(20)),(4,None),(5,Some(40))];
    let after=vec![(1,Some(30)),(2,Some(20)),(4,Some(15)),(5,Some(40)),(7,Some(20))];
    assert_eq!(index_tx_numbers(&mut tx),before);
    exec(&db,"BEGIN");
    exec(&db,"UPDATE items SET n=30,label='fir',flag=FALSE WHERE id=1");
    exec(&db,"DELETE FROM items WHERE id=3");
    exec(&db,"UPDATE items SET n=15,flag=TRUE WHERE id=4");
    exec(&db,"INSERT INTO items VALUES (7,20,'elm',TRUE)");
    index_predicates(&db,true);assert_eq!(index_tx_numbers(&mut tx),before);
    exec(&db,"COMMIT");
    assert_eq!(index_tx_numbers(&mut tx),if snapshot {before.clone()} else {after.clone()});
    tx.execute("INSERT INTO items VALUES (8,70,'willow',FALSE)",()).unwrap();
    let mut own=if snapshot {before} else {after};own.push((8,Some(70)));
    assert_eq!(index_tx_numbers(&mut tx),own);
    tx.rollback().unwrap();drop(tx);drop(reader);
    index_predicates(&db,true);
    assert_eq!(index_ids(&db,"SELECT id FROM items ORDER BY id"),vec![1,2,4,5,6,7]);
    exec(&db,"PRAGMA CHECKPOINT");index_predicates(&db,true);
    for name in ["by_n","by_label","by_flag","by_pair"] {exec(&db,&format!("DROP INDEX {name} ON items"));}
    index_predicates(&db,true);
    // Exercise another table before its first checkpoint as well as the checkpointed table.
    exec(&db,"CREATE TABLE prefix_items(id INTEGER PRIMARY KEY,label TEXT,n INTEGER)");
    exec(&db,"INSERT INTO prefix_items VALUES(11,'cedar',10),(22,'ash',20),(33,'cedar',30)");
    exec(&db,"CREATE INDEX prefix_only ON prefix_items(label,n)");
    let prefix="SELECT id FROM prefix_items WHERE label='cedar' ORDER BY id";
    assert_eq!(index_ids(&db,prefix),vec![11,33]);
    exec(&db,"INSERT INTO prefix_items VALUES(44,'cedar',40)");
    assert_eq!(index_ids(&db,"SELECT id FROM prefix_items ORDER BY id"),vec![11,22,33,44]);
    assert_eq!(index_ids(&db,prefix),vec![11,33,44]);
    exec(&db,"UPDATE prefix_items SET label='cedar' WHERE id=22");
    assert_eq!(index_ids(&db,prefix),vec![11,22,33,44]);
    exec(&db,"DELETE FROM prefix_items WHERE id=11");
    assert_eq!(index_ids(&db,prefix),vec![22,33,44]);
    assert_eq!(index_ids(&db,"SELECT id FROM prefix_items WHERE label IN ('cedar','missing') ORDER BY id"),vec![22,33,44]);
    db.close().unwrap();
}
fn index_persistence(phase: &str,path: &str) {
    let db=index_open(path);
    if phase=="save" {
        exec(&db,"CREATE TABLE saved (id INTEGER PRIMARY KEY,code TEXT,n INTEGER,label TEXT)");
        exec(&db,"INSERT INTO saved VALUES (1,'cedar',2,'north'),(2,'birch',7,'south')");
        exec(&db,"CREATE UNIQUE INDEX by_token ON saved(code) USING HASH");
        exec(&db,"CREATE UNIQUE INDEX by_region_number ON saved(label,n)");
        exec(&db,"CREATE INDEX by_number ON saved(n) USING BTREE");
        exec(&db,"ALTER TABLE saved RENAME COLUMN code TO token");
        exec(&db,"ALTER TABLE saved RENAME COLUMN label TO region");
        exec(&db,"ALTER TABLE saved ADD COLUMN code TEXT");
        exec(&db,"ALTER TABLE saved ADD COLUMN label TEXT");
        exec(&db,"UPDATE saved SET code='same',label='same'");
        index_saved_definitions(&db);index_saved_constraints(&db);
        exec(&db,"PRAGMA SNAPSHOT");
        for name in ["by_token","by_region_number","by_number"] {exec(&db,&format!("DROP INDEX {name} ON saved"));}
        exec(&db,"UPDATE saved SET token='cedar',n=2,region='north' WHERE id=2");
        assert_eq!(index_saved_rows(&db),vec![(1,"cedar".into(),2,"north".into()),(2,"cedar".into(),2,"north".into())]);
        assert!(index_catalog(&db,"saved").is_empty());
        exec(&db,"PRAGMA CHECKPOINT");exec(&db,"PRAGMA RESTORE");
    }
    index_saved_definitions(&db);index_saved_constraints(&db);
    assert_eq!(index_ids(&db,"SELECT id FROM saved WHERE token='cedar'"),vec![1]);
    assert_eq!(index_ids(&db,"SELECT id FROM saved WHERE region='south' AND n=7"),vec![2]);
    assert_eq!(index_ids(&db,"SELECT id FROM saved WHERE code='same' AND label='same' ORDER BY id"),vec![1,2]);
    // The renamed indexed columns, not newly added columns under the old names, impose uniqueness.
    exec(&db,"INSERT INTO saved VALUES (3,'elm',2,'west','same','same')");
    assert_eq!(index_saved_rows(&db),vec![(1,"cedar".into(),2,"north".into()),(2,"birch".into(),7,"south".into()),(3,"elm".into(),2,"west".into())]);
    exec(&db,"DELETE FROM saved WHERE id=3");db.close().unwrap();
}
fn index_schema_errors() {
    // Identical starting tables isolate the extra restriction imposed by the index.
    for indexed in [false,true] {
        let db=Database::open_in_memory().unwrap();
        exec(&db,"CREATE TABLE vectors (id INTEGER PRIMARY KEY,v VECTOR(3))");
        exec(&db,"INSERT INTO vectors VALUES (1,'[1,2,3]'),(2,'[4,5,6]')");
        if indexed {exec(&db,"CREATE INDEX by_vector ON vectors(v) USING HNSW");}
        if indexed {
            reject(&db,"ALTER TABLE vectors MODIFY COLUMN v TEXT");
            assert_eq!(index_column_types(&db,"vectors"),vec![("id".into(),"Integer".into()),("v".into(),"Vector".into())]);
            let rows=read_rows(&db,"SELECT id,v FROM vectors ORDER BY id").unwrap();
            let got:Vec<_>=rows.iter().map(|r|(r.get::<i64>(0).unwrap(),r.get_value(1).unwrap().as_vector_f32().unwrap())).collect();
            assert_eq!(got,vec![(1,vec![1.0,2.0,3.0]),(2,vec![4.0,5.0,6.0])]);
            let expected=vec![index_definition("vectors","by_vector","v","HNSW",false)];
            assert_eq!(index_catalog(&db,"vectors"),expected);
            reject(&db,"DROP INDEX absent ON vectors");
            assert_eq!(index_catalog(&db,"vectors"),expected);
            assert_eq!(index_ids(&db,"SELECT id FROM vectors ORDER BY id"),vec![1,2]);
            exec(&db,"DROP INDEX by_vector ON vectors");
            reject(&db,"DROP INDEX by_vector ON vectors");
        }
        exec(&db,"ALTER TABLE vectors MODIFY COLUMN v TEXT");
        assert_eq!(index_column_types(&db,"vectors"),vec![("id".into(),"Integer".into()),("v".into(),"Text".into())]);
        assert!(index_catalog(&db,"vectors").is_empty());
        assert_eq!(index_ids(&db,"SELECT id FROM vectors ORDER BY id"),vec![1,2]);
    }
}
fn main() {
    let args:Vec<String>=std::env::args().collect();
    match args[1].as_str() {
        "lifecycle"=>index_lifecycle(),"uniqueness"=>{index_uniqueness(&args[2]);index_wide_uniqueness();index_persisted_and_bitmap_uniqueness(&args[2]);},
        "committed"=>index_consistency(&args[2],false),"snapshot"=>index_consistency(&args[2],true),
        "save"|"reopen"=>index_persistence(&args[1],&args[2]),
        "schema_errors"=>index_schema_errors(),
        other=>panic!("unknown scenario {other}")
    }
}
'''


@pytest.fixture(scope="module")
def index_client(tmp_path_factory):
    return build_rust_client(INDEX_SUPPORT + INDEX_CASES, tmp_path_factory.mktemp("f14-client"))


