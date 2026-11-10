# feature: F16
"""Vector SQL clients, reusing the earlier native and index observation helpers."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct

import pytest
from _helpers import run_command, parse_json, parse_json_lines
from F01_helpers import build_rust_client, product_root
from F14_helpers import INDEX_SUPPORT

VECTOR_SUPPORT = INDEX_SUPPORT + r'''
fn vector_literal(v: &[f32]) -> String {
    format!("[{}]",v.iter().map(|x|x.to_string()).collect::<Vec<_>>().join(","))
}
fn vector_text_components(text: &str) -> Vec<f32> {
    // Public vector text is a bracketed, comma-separated list of decimal numbers.
    text.strip_prefix('[').unwrap().strip_suffix(']').unwrap()
        .split(',').map(|s|s.trim().parse::<f32>().unwrap()).collect()
}
fn vector_near(actual: f64, expected: f64) {
    assert!(actual.is_finite() && (actual-expected).abs()<=1e-4*expected.abs().max(1.0),
        "distance or magnitude: actual={actual}, expected={expected}");
}
fn vector_norm(v: &[f32]) -> f64 {
    v.iter().map(|&x|(x as f64).powi(2)).sum::<f64>().sqrt()
}
fn vector_distance(a: &[f32], b: &[f32], metric: &str) -> f64 {
    assert_eq!(a.len(),b.len());
    // Independent scalar f64 arithmetic over stored f32 inputs, per FP-16.03.
    let dot=a.iter().zip(b).map(|(&x,&y)|x as f64*y as f64).sum::<f64>();
    match metric {
        "l2"=>a.iter().zip(b).map(|(&x,&y)|(x as f64-y as f64).powi(2)).sum::<f64>().sqrt(),
        "cosine"=>1.0-dot/(vector_norm(a)*vector_norm(b)),
        "ip"=>-dot,
        _=>panic!("unknown metric {metric}"),
    }
}
fn vector_function(metric: &str) -> &'static str {
    match metric {"l2"=>"VEC_DISTANCE_L2","cosine"=>"VEC_DISTANCE_COSINE","ip"=>"VEC_DISTANCE_IP",_=>panic!("unknown metric")}
}
fn vector_input_rows() -> Vec<(i64,Option<Vec<f32>>,bool)> {
    vec![(1,Some(vec![0.5,0.25]),false),(2,Some(vec![0.5,0.5]),true),
         (3,Some(vec![-0.5,0.25]),true),(4,Some(vec![1.0,0.5]),true),
         (5,Some(vec![0.5,0.0]),true),(6,Some(vec![0.25,0.125]),true),
         (7,None,true),(8,Some(vec![0.75,-0.5]),false)]
}
fn vector_table(db: &Database) {
    exec(db,"CREATE TABLE points(id INTEGER PRIMARY KEY,v VECTOR(2),eligible BOOLEAN)");
    for (id,v,eligible) in vector_input_rows() {
        let value=match v {Some(v)=>format!("'{}'",vector_literal(&v)),None=>"NULL".into()};
        exec(db,&format!("INSERT INTO points VALUES({id},{value},{eligible})"));
    }
}
fn vector_query(metric: &str, query: &[f32], filter: &str, nulls: &str, limit: usize) -> String {
    format!("SELECT id,v,{}(v,'{}') AS distance FROM points {filter} ORDER BY distance ASC NULLS {nulls} LIMIT {limit}",
        vector_function(metric),vector_literal(query))
}
fn vector_check_rows(rows: &[ResultRow], expected: &[(i64,Option<Vec<f32>>,bool)], query: &[f32],
                     metric: &str, nulls: &str, limit: usize, exact: bool) {
    assert_eq!(rows.len(),limit.min(expected.len()));
    let mut seen=std::collections::HashSet::new();
    let mut previous:Option<f64>=None;
    let mut seen_null=false;
    let mut seen_value=false;
    let mut selected=Vec::new();
    for row in rows {
        let id:i64=row.get_by_name("id").unwrap();
        assert!(seen.insert(id),"duplicate candidate {id}");
        let (_,v,_)=expected.iter().find(|r|r.0==id).expect("candidate must be an eligible visible row");
        let d:Option<f64>=row.get_by_name("distance").unwrap();
        match v {
            Some(v)=>{
                assert_eq!(row.get_value(1).unwrap().as_vector_f32().unwrap(),*v);
                let actual=d.expect("present vector must have a distance");
                let truth=vector_distance(v,query,metric);vector_near(actual,truth);
                if let Some(p)=previous {assert!(p<=actual,"distance ordering");}
                if nulls=="LAST" {assert!(!seen_null,"NULLS LAST");}
                previous=Some(actual);seen_value=true;selected.push(truth);
            },
            None=>{
                assert!(row.get_value(1).unwrap().is_null());assert_eq!(d,None);
                if nulls=="FIRST" {assert!(!seen_value,"NULLS FIRST");}
                seen_null=true;
            }
        }
    }
    if exact {
        // Compare the distance multiset, not the identity at an interchangeable tie.
        let null_count=expected.iter().filter(|r|r.1.is_none()).count();
        let mut distances:Vec<f64>=expected.iter().filter_map(|r|r.1.as_ref())
            .map(|v|vector_distance(v,query,metric)).collect();
        distances.sort_by(|a,b|a.partial_cmp(b).unwrap());
        let finite_count=if nulls=="FIRST" {rows.len().saturating_sub(null_count)} else {rows.len().min(distances.len())};
        assert_eq!(selected.len(),finite_count);
        for (a,b) in selected.iter().zip(distances.iter().take(finite_count)) {vector_near(*a,*b);}
    }
    println!("validated {} candidates for {metric}, nulls={nulls}, exact={exact}",rows.len());
}
'''

VECTOR_CASES = r'''
fn vector_storage() {
    let db=Database::open_in_memory().unwrap();
    for (n,input) in [(1,vec![0.1f32]),(3,vec![0.1,-0.25,0.75]),(5,vec![-1.0,0.0,0.2,-0.3,1.0])] {
        exec(&db,&format!("CREATE TABLE stored{n}(id INTEGER PRIMARY KEY,v VECTOR({n}))"));
        // Bind native vectors and text separately through the public SQL entry.
        db.execute(&format!("INSERT INTO stored{n} VALUES(1,$1)"),[velnora::Value::vector(input.clone())]).unwrap();
        db.execute(&format!("INSERT INTO stored{n} VALUES(2,$1)"),[velnora::Value::from(vector_literal(&input))]).unwrap();
        let rows=read_rows(&db,&format!("SELECT v,VEC_DIMS(v),VEC_NORM(v),VEC_TO_TEXT(v),TYPEOF(v) FROM stored{n} ORDER BY id")).unwrap();
        assert_eq!(rows.len(),2);
        for row in rows {
            assert_eq!(row.get_value(0).unwrap().as_vector_f32().unwrap(),input);
            assert_eq!(row.get::<i64>(1).unwrap(),n);
            vector_near(row.get(2).unwrap(),vector_norm(&input));
            let text:String=row.get(3).unwrap();assert_eq!(vector_text_components(&text),input);
            assert_eq!(row.get::<String>(4).unwrap(),"VECTOR");
            println!("stored components={input:?}, text={text}");
        }
    }
    let precise=vec![0.12345679f32,-0.00012345679f32];
    exec(&db,"CREATE TABLE precise(id INTEGER PRIMARY KEY,v VECTOR(2))");
    db.execute("INSERT INTO precise VALUES(1,$1)",[velnora::Value::vector(precise.clone())]).unwrap();
    let row=read_rows(&db,"SELECT VEC_TO_TEXT(v) FROM precise").unwrap().remove(0);
    assert_eq!(vector_text_components(&row.get::<String>(0).unwrap()),precise);
}
fn vector_metrics() {
    let db=Database::open_in_memory().unwrap();
    for n in [1usize,3,31,128,1024] {
        let a:Vec<f32>=(0..n).map(|i|((i*17%101) as f32-50.0)/50.0).collect();
        let b:Vec<f32>=(0..n).map(|i|((i*29%97) as f32-48.0)/48.0).collect();
        exec(&db,&format!("CREATE TABLE pairs{n}(a VECTOR({n}),b VECTOR({n}))"));
        db.execute(&format!("INSERT INTO pairs{n} VALUES($1,$2)"),
            [velnora::Value::vector(a.clone()),velnora::Value::vector(b.clone())]).unwrap();
        let rows=read_rows(&db,&format!("SELECT a,b,VEC_NORM(a),VEC_NORM(b),VEC_DISTANCE_L2(a,b),VEC_DISTANCE_COSINE(a,b),VEC_DISTANCE_IP(a,b) FROM pairs{n}")).unwrap();
        assert_eq!(rows.len(),1);let r=&rows[0];
        assert_eq!(r.get_value(0).unwrap().as_vector_f32().unwrap(),a);
        assert_eq!(r.get_value(1).unwrap().as_vector_f32().unwrap(),b);
        vector_near(r.get(2).unwrap(),vector_norm(&a));vector_near(r.get(3).unwrap(),vector_norm(&b));
        for (i,metric) in ["l2","cosine","ip"].iter().enumerate() {
            let actual:f64=r.get(i+4).unwrap();let expected=vector_distance(&a,&b,metric);
            println!("n={n} metric={metric} actual={actual} expected={expected}");vector_near(actual,expected);
        }
    }
    // Zero and antiparallel vectors are distinct from the long mixed-sign cases.
    for (a,b) in [(vec![0.0,0.0],vec![0.6,0.8]),(vec![0.6,0.8],vec![-0.6,-0.8])] {
        for metric in ["l2","cosine","ip"] {
            if metric=="cosine" && vector_norm(&a)<0.01 {continue;}
            let sql=format!("SELECT {}('{}','{}')",vector_function(metric),vector_literal(&a),vector_literal(&b));
            let r=read_rows(&db,&sql).unwrap();vector_near(r[0].get(0).unwrap(),vector_distance(&a,&b,metric));
        }
    }
    let small=vec![0.02f32,0.0];
    let rows=read_rows(&db,"SELECT VEC_DISTANCE_COSINE('[0.02,0]','[0.02,0]')").unwrap();
    vector_near(rows[0].get(0).unwrap(),vector_distance(&small,&small,"cosine"));
}
fn vector_exact() {
    let db=Database::open_in_memory().unwrap();vector_table(&db);
    let all=vector_input_rows();let eligible:Vec<_>=all.iter().filter(|r|r.2).cloned().collect();
    let query=[0.5,0.25];
    for metric in ["l2","cosine","ip"] {
        for (filter,expected,nulls,limit) in [
            ("WHERE eligible=TRUE",&eligible,"LAST",3),
            ("WHERE eligible=TRUE",&eligible,"FIRST",3),
            ("",&all,"LAST",20),
            ("WHERE eligible=TRUE",&eligible,"LAST",1),
        ] {
            let sql=vector_query(metric,&query,filter,nulls,limit);
            vector_check_rows(&read_rows(&db,&sql).unwrap(),expected,&query,metric,nulls,limit,true);
        }
    }
    for metric in ["l2","cosine","ip"] {
        let sql=format!("SELECT id,{}(v,NULL) AS distance FROM points ORDER BY id",vector_function(metric));
        let rows=read_rows(&db,&sql).unwrap();
        assert!(rows.iter().all(|row| row.get_by_name::<Option<f64>>("distance").unwrap().is_none()));
    }
}
fn vector_indexed() {
    let all=vector_input_rows();let eligible:Vec<_>=all.iter().filter(|r|r.2).cloned().collect();
    let query=[0.5,0.25];
    // Metric omission is observed both alone and alongside unrelated options.
    for options in ["", " WITH(m=12,ef_construction=80)"] {
        let db=Database::open_in_memory().unwrap();vector_table(&db);
        exec(&db,&format!("CREATE INDEX default_vector ON points(v) USING HNSW{options}"));
        let rows=read_rows(&db,"SHOW INDEXES FROM points").unwrap();
        assert_eq!(rows.len(),1);
        let text:String=rows[0].get_by_name("options").unwrap();
        let fields:std::collections::BTreeMap<_,_>=text.split(',').map(|s| {
            let (k,v)=s.trim().split_once('=').unwrap();(k.trim(),v.trim())
        }).collect();
        assert_eq!(fields.get("metric"),Some(&"l2"));
        let sql=vector_query("l2",&query,"","LAST",3);
        vector_check_rows(&read_rows(&db,&sql).unwrap(),&all,&query,"l2","LAST",3,false);
    }
    for indexed_metric in ["l2","cosine","ip"] {
        let db=Database::open_in_memory().unwrap();vector_table(&db);
        exec(&db,&format!("CREATE INDEX by_vector ON points(v) USING HNSW WITH(metric='{indexed_metric}')"));
        assert_eq!(index_catalog(&db,"points"),vec![index_definition("points","by_vector","v","HNSW",false)]);
        // Each declared index metric is used, then a different requested metric is checked.
        let other=match indexed_metric {"l2"=>"ip","ip"=>"cosine",_=>"l2"};
        for metric in [indexed_metric,other] {
            for (filter,expected,nulls,limit) in [
                ("",&all,"LAST",3),("WHERE eligible=TRUE",&eligible,"LAST",3),
                ("WHERE eligible=TRUE",&eligible,"FIRST",3),("",&all,"LAST",20),
            ] {
                let sql=vector_query(metric,&query,filter,nulls,limit);
                vector_check_rows(&read_rows(&db,&sql).unwrap(),expected,&query,metric,nulls,limit,false);
            }
        }
    }
}
fn vector_saved_catalog(db: &Database) {
    assert_eq!(index_catalog(db,"points"),vec![index_definition("points","saved_vector","v","HNSW",false)]);
    let rows=read_rows(db,"SHOW INDEXES FROM points").unwrap();
    let options:String=rows[0].get_by_name("options").unwrap();
    // Options is a public comma-separated key=value field; order is irrelevant.
    let got:std::collections::BTreeMap<_,_>=options.split(',').map(|s|{
        let (k,v)=s.trim().split_once('=').unwrap();(k.trim(),v.trim())}).collect();
    assert_eq!(got.get("metric"),Some(&"cosine"));
    assert_eq!(got["m"].parse::<u64>().unwrap(),12);
    assert_eq!(got["ef_construction"].parse::<u64>().unwrap(),80);
}
fn vector_lifecycle(phase: &str,path: &str) {
    let db=index_open(path);let query=[0.5,0.25];
    let original=vector_input_rows();
    if phase=="seed" {
        vector_table(&db);exec(&db,"PRAGMA CHECKPOINT");db.close().unwrap();return;
    }
    if phase=="index" {
        exec(&db,"CREATE INDEX saved_vector ON points(v) USING HNSW WITH(metric='cosine',m=12,ef_construction=80,ef_search=80)");
    }
    // Observe the recovered definition before any operation can recreate an index.
    vector_saved_catalog(&db);
    let sql=vector_query("cosine",&query,"","LAST",7);
    if phase=="index" {
        vector_check_rows(&read_rows(&db,&sql).unwrap(),&original,&query,"cosine","LAST",7,true);
        exec(&db,"PRAGMA CHECKPOINT");db.close().unwrap();return;
    }
    let mut changed=original.clone();changed.iter_mut().find(|r|r.0==2).unwrap().1=Some(vec![-0.75,0.5]);
    changed.iter_mut().find(|r|r.0==3).unwrap().1=Some(vec![0.25,-0.75]);
    changed.iter_mut().find(|r|r.0==5).unwrap().1=Some(vec![0.75,0.25]);
    changed.retain(|r|r.0!=4);changed.push((9,Some(vec![0.1,-0.5]),true));
    if phase=="change" {
        vector_check_rows(&read_rows(&db,&sql).unwrap(),&original,&query,"cosine","LAST",7,true);
        let reader=Database::open(db.dsn()).unwrap();
        let mut tx=reader.begin_with_isolation(IsolationLevel::SnapshotIsolation).unwrap();
        let before=tx.query(&sql,()).and_then(|r|r.collect_vec()).unwrap();
        vector_check_rows(&before,&original,&query,"cosine","LAST",7,true);
        exec(&db,"UPDATE points SET v='[-0.75,0.5]' WHERE id=2");
        exec(&db,"BEGIN");
        exec(&db,"UPDATE points SET v='[0.25,-0.75]' WHERE id=3");
        exec(&db,"UPDATE points SET v='[0.75,0.25]' WHERE id=5");
        exec(&db,"COMMIT");
        exec(&db,"DELETE FROM points WHERE id=4");
        exec(&db,"INSERT INTO points VALUES(9,'[0.1,-0.5]',TRUE)");
        let after=tx.query(&sql,()).and_then(|r|r.collect_vec()).unwrap();
        vector_check_rows(&after,&original,&query,"cosine","LAST",7,true);
        tx.rollback().unwrap();drop(tx);drop(reader);
    }
    vector_check_rows(&read_rows(&db,&sql).unwrap(),&changed,&query,"cosine","LAST",7,true);
    let full=vector_query("cosine",&query,"","LAST",20);
    vector_check_rows(&read_rows(&db,&full).unwrap(),&changed,&query,"cosine","LAST",20,true);
    for id in [2,3,5,9] {
        let expected:Vec<_>=changed.iter().filter(|r|r.0==id).cloned().collect();
        let sql=vector_query("cosine",&query,&format!("WHERE id={id}"),"LAST",1);
        vector_check_rows(&read_rows(&db,&sql).unwrap(),&expected,&query,"cosine","LAST",1,false);
    }
    exec(&db,"PRAGMA CHECKPOINT");db.close().unwrap();
}
fn vector_errors() {
    let db=Database::open_in_memory().unwrap();vector_table(&db);
    let original=vector_input_rows();let query=[0.5,0.25];
    let check=vector_query("l2",&query,"","LAST",20);
    vector_check_rows(&read_rows(&db,&check).unwrap(),&original,&query,"l2","LAST",20,true);
    for sql in [
        "INSERT INTO points VALUES(20,'[1]',TRUE)",
        "INSERT INTO points VALUES(20,'[1,2,3]',TRUE)",
        "UPDATE points SET v='[1]' WHERE id=2",
        "UPDATE points SET v='[1,2,3]' WHERE id=2",
        "INSERT INTO points VALUES(20,'[bad,0]',TRUE)",
        "UPDATE points SET v='[1,broken]' WHERE id=2",
        "ALTER TABLE points MODIFY COLUMN v VECTOR(1)",
        "ALTER TABLE points MODIFY COLUMN v VECTOR(3)",
        "CREATE INDEX wrong ON points(eligible) USING HNSW",
    ] {
        reject(&db,sql);
        vector_check_rows(&read_rows(&db,&check).unwrap(),&original,&query,"l2","LAST",20,true);
    }
    let native=velnora::Value::vector(vec![1.0f32]);
    assert!(db.execute("INSERT INTO points VALUES(21,$1,TRUE)",[native]).is_err());
    vector_check_rows(&read_rows(&db,&check).unwrap(),&original,&query,"l2","LAST",20,true);
    // Invalid SQL distance operands produce a missing distance; malformed writes
    // are checked separately through the public error carrier.
    for metric in ["l2","cosine","ip"] {
        for invalid in ["[1]","[1,2,3]","[1,broken]"] {
            let sql=format!("SELECT {}(v,'{invalid}') AS distance FROM points WHERE id=2",vector_function(metric));
            let rows=read_rows(&db,&sql).unwrap();assert_eq!(rows.len(),1);
            assert_eq!(rows[0].get_by_name::<Option<f64>>("distance").unwrap(),None);
            println!("invalid distance returns NULL: {sql}");
        }
    }
    // Rejected schema changes must not silently change the accepted dimension.
    exec(&db,"INSERT INTO points VALUES(20,'[0.1,-0.5]',TRUE)");
    let mut expected=original;expected.push((20,Some(vec![0.1,-0.5]),true));
    vector_check_rows(&read_rows(&db,&check).unwrap(),&expected,&query,"l2","LAST",20,true);
    assert!(index_catalog(&db,"points").is_empty());
    exec(&db,"CREATE INDEX conversion_guard ON points(v) USING HNSW");
    reject(&db,"ALTER TABLE points MODIFY COLUMN v TEXT");
    vector_check_rows(&read_rows(&db,&check).unwrap(),&expected,&query,"l2","LAST",20,true);
    exec(&db,"DROP INDEX conversion_guard ON points");
    exec(&db,"ALTER TABLE points MODIFY COLUMN v TEXT");
    let rows=read_rows(&db,"SELECT id,v FROM points ORDER BY id").unwrap();
    assert_eq!(rows.len(),expected.len());
    for row in rows {
        let id:i64=row.get(0).unwrap();
        let original=&expected.iter().find(|r|r.0==id).unwrap().1;
        match original {
            Some(v)=>assert_eq!(vector_text_components(&row.get::<String>(1).unwrap()),*v),
            None=>assert!(row.get_value(1).unwrap().is_null()),
        }
    }
    assert_eq!(index_column_types(&db,"points"),vec![
        ("id".into(),"Integer".into()),("v".into(),"Text".into()),("eligible".into(),"Boolean".into())]);
    assert!(index_catalog(&db,"points").is_empty());
}

fn vector_fashion(train_path: &str, query_path: &str, options: &str, output_path: &str) {
    use std::io::Write;
    // The Python asset reader verifies the official archives and passes raw pixels.
    let train=std::fs::read(train_path).unwrap();
    let queries=std::fs::read(query_path).unwrap();
    assert_eq!(train.len(),60000*784);assert_eq!(queries.len(),10000*784);
    let db=Database::open_in_memory().unwrap();
    exec(&db,"CREATE TABLE fashion_images(id INTEGER PRIMARY KEY,embedding VECTOR(784))");
    exec(&db,"BEGIN");
    {
        let insert=db.prepare("INSERT INTO fashion_images VALUES($1,$2)").unwrap();
        for (id,pixels) in train.chunks_exact(784).enumerate() {
            let v:Vec<f32>=pixels.iter().map(|&p|p as f32).collect();
            insert.execute([velnora::Value::Integer(id as i64),velnora::Value::vector(v)]).unwrap();
        }
    }
    exec(&db,"COMMIT");
    let create=format!("CREATE INDEX fashion_vectors ON fashion_images(embedding) USING HNSW WITH(metric='l2'{options})");
    exec(&db,&create);
    let mut output=std::io::BufWriter::new(std::fs::File::create(output_path).unwrap());
    for (qi,pixels) in queries.chunks_exact(784).enumerate() {
        let query:Vec<f32>=pixels.iter().map(|&p|p as f32).collect();
        let sql=format!("SELECT id FROM fashion_images ORDER BY VEC_DISTANCE_L2(embedding,'{}') ASC LIMIT 10",vector_literal(&query));
        let rows=read_rows(&db,&sql).unwrap();
        assert_eq!(rows.len(),10,"query {qi}: wrong result count");
        let ids:Vec<i64>=rows.iter().map(|r|r.get_by_name::<i64>("id").unwrap()).collect();
        assert!(ids.iter().all(|&id|(0..60000).contains(&id)),"query {qi}: nonexistent candidate");
        assert_eq!(ids.iter().collect::<std::collections::HashSet<_>>().len(),10,"query {qi}: duplicate candidate");
        writeln!(output,"{ids:?}").unwrap();
    }
    output.flush().unwrap();db.close().unwrap();
}

fn main() {
    let args:Vec<String>=std::env::args().collect();
    match args[1].as_str() {
        "fashion"=>vector_fashion(&args[2],&args[3],&args[4],&args[5]),
        "storage"=>vector_storage(),"metrics"=>vector_metrics(),"exact"=>vector_exact(),
        "indexed"=>vector_indexed(),"errors"=>vector_errors(),
        "seed"|"index"|"change"|"reopen"=>vector_lifecycle(&args[1],&args[2]),
        other=>panic!("unknown scenario {other}"),
    }
}
'''


@pytest.fixture(scope="module")
def vector_client(tmp_path_factory):
    return build_rust_client(VECTOR_SUPPORT + VECTOR_CASES, tmp_path_factory.mktemp("f16-client"))


# Official Fashion-MNIST image archive checksums published by the dataset project:
# https://github.com/zalandoresearch/fashion-mnist#downloading-data
# These identify input assets, not expected neighbor identities or product output.
FASHION_ARCHIVES = (
    ("F16_FASHION_TRAIN", 60000, "8d4fb7e6c68d591d4c3dfef9ec88bf0d"),
    ("F16_FASHION_TEST", 10000, "bef4ecab320f06d8554ea6380940ec79"),
)


def fashion_inputs(directory):
    """Read the public corpus and the product's declared index configuration."""
    fixture_directory = Path(__file__).resolve().parent
    declaration_path = product_root() / "vector_search.json"
    try:
        declaration = declaration_path.read_bytes()
    except FileNotFoundError:
        # The public interface defines absence as selecting default index options.
        declaration = b"{}"
    config = parse_json(declaration)
    if not isinstance(config, dict) or set(config) - {"m", "ef_construction", "ef_search"}:
        raise ValueError("ANN configuration must be an object of public HNSW index options")
    if any(type(value) is not int or value <= 0 for value in config.values()):
        raise ValueError("ANN index option values must be positive integers")
    directory = Path(directory)
    (directory / "declared-ann-config.json").write_bytes(declaration)
    options = "".join(f",{name}={value}" for name, value in sorted(config.items()))
    paths = []
    for environment, count, digest in FASHION_ARCHIVES:
        fixture = "F16_fashion_train.gz" if environment == "F16_FASHION_TRAIN" else "F16_fashion_test.gz"
        path = fixture_directory / fixture
        compressed = path.read_bytes()
        actual = hashlib.md5(compressed, usedforsecurity=False).hexdigest()
        if actual != digest:
            raise ValueError(f"{environment}: not the official Fashion-MNIST image archive; MD5={actual}")
        raw = gzip.decompress(compressed)
        if len(raw) != 16 + count * 784 or struct.unpack(">4I", raw[:16]) != (2051, count, 28, 28):
            raise ValueError(f"{environment}: invalid complete IDX image corpus")
        payload = directory / (environment.lower() + ".pixels")
        payload.write_bytes(raw[16:])
        paths.append(payload)
    return paths[0], paths[1], options


def fashion_recall_counts(train, queries, candidates):
    """Compute exact nearest-set credit, including interchangeable boundary ties.

    Double-precision BLAS multiplies integer pixel values. Every product and sum
    here is an exactly representable integer below 2**53, so the squared-distance
    comparison has no numerical tolerance or product-defined distance oracle.
    Only a bounded query batch's full distance matrix is retained at a time.
    """
    import numpy as np

    assert train.shape == (60000, 784)
    assert queries.shape == (10000, 784)
    assert candidates.shape == (10000, 10)
    assert np.issubdtype(candidates.dtype, np.integer)
    assert np.all((candidates >= 0) & (candidates < 60000))
    assert np.all(np.diff(np.sort(candidates, axis=1), axis=1) != 0)
    base = train.astype(np.float64)
    norms = np.einsum("ij,ij->i", base, base)
    credits = []
    for start in range(0, 10000, 64):
        batch = queries[start:start + 64].astype(np.float64)
        squared = norms[None, :] + np.einsum("ij,ij->i", batch, batch)[:, None] - 2 * (batch @ base.T)
        assert np.all(squared >= 0)
        boundary = np.partition(squared, 9, axis=1)[:, 9]
        strictly_closer_count = np.count_nonzero(squared < boundary[:, None], axis=1)
        selected = np.take_along_axis(squared, candidates[start:start + len(batch)], axis=1)
        strict_hits = np.count_nonzero(selected < boundary[:, None], axis=1)
        boundary_hits = np.count_nonzero(selected == boundary[:, None], axis=1)
        # Merely accepting every distance <= the boundary would overcredit a
        # result that omits strict neighbors and fills their slots with tied rows.
        credit = strict_hits + np.minimum(boundary_hits, 10 - strictly_closer_count)
        credits.extend(int(value) for value in credit)
    assert len(credits) == 10000
    return credits


def measure_fashion_recall(client, directory, train_path, query_path, options):
    """Run fresh full SQL retrieval and judge identities against independent distances."""
    import numpy as np

    directory = Path(directory)
    output = directory / "retrieved-identities.jsonl"
    result = run_command([client, "fashion", train_path, query_path, options, output],
                         cwd=client.parent, timeout=7200)
    assert result.returncode == 0, (result.stdout, result.stderr)
    # This file is written by the external native test client from typed SQL rows;
    # it is not a product self-report of recall or a previously computed answer.
    rows = parse_json_lines(output.read_bytes())
    assert len(rows) == 10000, "Every test image must have a fresh SQL result"
    assert all(isinstance(row, list) and len(row) == 10 for row in rows)
    assert all(type(value) is int for row in rows for value in row)
    candidates = np.asarray(rows, dtype=np.int64)
    train = np.frombuffer(Path(train_path).read_bytes(), dtype=np.uint8).reshape(60000, 784)
    queries = np.frombuffer(Path(query_path).read_bytes(), dtype=np.uint8).reshape(10000, 784)
    credits = fashion_recall_counts(train, queries, candidates)
    matches = sum(credits)
    report = {"queries": len(credits), "neighbors_per_query": 10,
              "credited_neighbors": matches, "mean_recall": matches / 100000}
    (directory / "independent-recall.json").write_text(json.dumps(report, indent=2) + "\n")
    assert matches >= 95000, report
    return report
