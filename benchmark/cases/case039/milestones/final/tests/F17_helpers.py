# feature: F17
"""Native embedding observations using bundled, verified offline model assets."""
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from _helpers import build_artifact, parse_json, parse_json_lines, run_command
from F01_helpers import build_rust_client
from F00_environment import openssl_environment, numerical_dependencies
from F17_reference import model_assets, reference_embeddings
from F06_helpers import RUST_TRANSACTION_SUPPORT
from F16_helpers import VECTOR_SUPPORT


EMBEDDING_DISABLED_CLIENT = RUST_TRANSACTION_SUPPORT + r'''
fn embedding_baseline(db: &Database) {
    let rows=read_rows(db,"SELECT id,body FROM documents ORDER BY id").unwrap();
    let got:Vec<(i64,String)>=rows.iter().map(|row|(
        row.get_by_name("id").unwrap(),row.get_by_name("body").unwrap())).collect();
    assert_eq!(got,vec![(11,"ordinary stored text".to_string())]);
}
fn main() {
    let db=Database::open_in_memory().unwrap();
    exec(&db,"CREATE TABLE documents(id INTEGER PRIMARY KEY,body TEXT,embedding VECTOR(384))");
    exec(&db,"INSERT INTO documents VALUES(11,'ordinary stored text',NULL)");
    embedding_baseline(&db);
    // Each observation captures query creation and complete result consumption.
    // Error prose and the internal error variant are not classification oracles.
    for sql in [
        "SELECT EMBED('A bird rests on a branch') AS embedding",
        "SELECT EMBED(NULL) AS embedding",
        "INSERT INTO documents VALUES(23,'another document',EMBED('another document'))",
    ] {
        reject(&db,sql);
        embedding_baseline(&db);
    }
}
'''


@pytest.fixture(scope="module")
def embedding_disabled_client(tmp_path_factory):
    # The existing public default + ffi/heap-profile build does not enable semantic.
    directory = tmp_path_factory.mktemp("f17-disabled-client")
    binary = build_rust_client(EMBEDDING_DISABLED_CLIENT, directory)
    # Other feature configurations may share CARGO_TARGET_DIR and its binary name.
    return Path(shutil.copy2(binary, directory / "disabled-client"))


EMBEDDING_ENABLED_CLIENT = VECTOR_SUPPORT + r'''
fn embedding_value(db: &Database, value: velnora::Value) -> Vec<f32> {
    let rows=db.query("SELECT EMBED($1) AS embedding",[value])
        .and_then(|r|r.collect_vec()).unwrap();
    assert_eq!(rows.len(),1);
    rows[0].get_value(0).unwrap().as_vector_f32()
        .expect("EMBED must produce a native vector for a present supported input")
}
fn embedding_unit(v: &[f32]) {
    assert_eq!(v.len(),384);
    assert!(v.iter().all(|x|x.is_finite()));
    assert!((vector_norm(v)-1.0).abs()<=0.0001,"embedding is not unit length");
}
fn embedding_same(a: &[f32],b: &[f32]) {
    assert_eq!(a.len(),b.len());
    for (x,y) in a.iter().zip(b) {
        assert!(x.is_finite() && y.is_finite() && (*x as f64-*y as f64).abs()<=0.0001,
                "equivalent text changed an embedding component: {x}, {y}");
    }
}
fn embedding_components(input: &str,output: &str) {
    use std::io::Write;
    let db=Database::open_in_memory().unwrap();
    let texts=std::fs::read_to_string(input).unwrap();
    let mut out=std::io::BufWriter::new(std::fs::File::create(output).unwrap());
    for text in texts.lines() {
        let first=embedding_value(&db,velnora::Value::from(text));
        embedding_unit(&first);
        // An intervening different input prevents a last-result-only cache from
        // satisfying the repeatability arm without respecting the supplied text.
        let other=embedding_value(&db,velnora::Value::from("An unrelated intervening sentence."));
        embedding_unit(&other);
        let repeated=embedding_value(&db,velnora::Value::from(text));
        embedding_unit(&repeated);embedding_same(&first,&repeated);
        // This is test-client transport of typed values, not product formatting.
        writeln!(out,"{:?}",first).unwrap();
    }
    out.flush().unwrap();
}
fn embedding_retrieval() {
    let db=Database::open_in_memory().unwrap();
    exec(&db,"CREATE TABLE semantic_documents(id INTEGER PRIMARY KEY,body TEXT,v VECTOR(384))");
    let documents=[
        (41,"A mechanic repairs a bicycle wheel."),
        (7,"Fresh apples grow in the orchard."),
        (29,"The telescope records distant stars."),
        (13,"A cyclist adjusts the brakes before a ride."),
        (53,"The baker kneads dough for bread."),
    ];
    for (id,text) in documents {
        db.execute("INSERT INTO semantic_documents VALUES($1,$2,EMBED($2))",
            [velnora::Value::Integer(id),velnora::Value::from(text)]).unwrap();
    }
    let stored=read_rows(&db,"SELECT id,body,v FROM semantic_documents ORDER BY id").unwrap();
    assert_eq!(stored.len(),documents.len());
    let mut expected=Vec::new();
    let mut seen=std::collections::HashSet::new();
    for row in stored {
        let id:i64=row.get_by_name("id").unwrap();
        assert!(seen.insert(id));
        let text=documents.iter().find(|d|d.0==id).unwrap().1;
        assert_eq!(row.get_by_name::<String>("body").unwrap(),text);
        let v=row.get_value(2).unwrap().as_vector_f32().expect("stored embedding");
        let direct=embedding_value(&db,velnora::Value::from(text));
        embedding_same(&v,&direct);
        expected.push((id,Some(v),true));
    }
    // Identities and input order deliberately do not encode relevance. Expected
    // distances come from the stored components, not subjective semantic ranks.
    for text in ["A mechanic repairs a bicycle wheel.","Looking at the night sky through a telescope."] {
        for metric in ["cosine","l2","ip"] {
            for limit in [2,documents.len()] {
                // Read the chosen query embedding from this very SQL execution.
                // Comparing to a separately embedded query would incorrectly pin
                // repeatability more tightly than FP-17.02 permits.
                let sql=format!("WITH query_embedding AS (SELECT EMBED($1) AS q) SELECT id,v,q,{}(v,q) AS distance FROM semantic_documents CROSS JOIN query_embedding ORDER BY distance ASC LIMIT {limit}",vector_function(metric));
                let rows=db.query(&sql,[velnora::Value::from(text)])
                    .and_then(|r|r.collect_vec()).unwrap();
                assert_eq!(rows.len(),limit);
                let query=rows[0].get_value(2).unwrap().as_vector_f32().expect("query embedding");
                vector_check_rows(&rows,&expected,&query,metric,"LAST",limit,true);
            }
        }
    }
}
fn embedding_coercion() {
    let db=Database::open_in_memory().unwrap();
    let live=embedding_value(&db,velnora::Value::from("Private text processed locally."));
    embedding_unit(&live);
    for (number,text) in [
        (velnora::Value::Integer(37),"37"),
        (velnora::Value::Integer(-208),"-208"),
        (velnora::Value::Float(3.125),"3.125"),
        (velnora::Value::Float(-0.75),"-0.75"),
    ] {
        let numeric=embedding_value(&db,number);
        let textual=embedding_value(&db,velnora::Value::from(text));
        embedding_unit(&numeric);embedding_unit(&textual);
        embedding_same(&numeric,&textual);
    }
    let rows=db.query("SELECT EMBED($1) AS embedding",[velnora::Value::null_unknown()])
        .and_then(|r|r.collect_vec()).unwrap();
    assert_eq!(rows.len(),1);
    assert!(rows[0].get_value(0).unwrap().is_null());
    let rows=read_rows(&db,"SELECT EMBED(NULL) AS embedding").unwrap();
    assert_eq!(rows.len(),1);
    assert!(rows[0].get_value(0).unwrap().is_null());
}
fn main() {
    let args:Vec<String>=std::env::args().collect();
    match args[1].as_str() {
        "components"=>embedding_components(&args[2],&args[3]),
        "retrieval"=>embedding_retrieval(),
        "coercion"=>embedding_coercion(),
        "unavailable"=>{
            let db=Database::open_in_memory().unwrap();
            assert_eq!(db.query_one::<i64,_>("SELECT 41",()).unwrap(),41);
            let result=read_rows(&db,"SELECT EMBED('A new local request.')");
            println!("model loading outcome: {result:?}");
            match result {
                Err(_)=>{},
                Ok(rows)=>{assert_eq!(rows.len(),1);assert!(rows[0].get_value(0).unwrap().is_null());},
            }
            assert_eq!(db.query_one::<i64,_>("SELECT 43",()).unwrap(),43);
        },
        _=>panic!("unknown embedding scenario"),
    }
}
'''


@pytest.fixture(scope="module")
def embedding_enabled_client(tmp_path_factory, openssl_environment):
    directory = tmp_path_factory.mktemp("f17-enabled-client")
    return build_rust_client(EMBEDDING_ENABLED_CLIENT, directory,
        features=("ffi", "heap-profile", "semantic"), environment=openssl_environment)


@pytest.fixture(scope="module")
def embedding_cache(tmp_path_factory):
    assets, declaration = model_assets()
    home = tmp_path_factory.mktemp("f17-home")
    cache = home / ".cache/huggingface"
    repository = cache / "hub/models--sentence-transformers--all-MiniLM-L6-v2"
    snapshot = repository / "snapshots" / declaration["revision"]
    snapshot.mkdir(parents=True)
    (repository / "refs").mkdir()
    (repository / "refs/main").write_text(declaration["revision"])
    for name in declaration["sha256"]:
        # Shipped ownership prefixes are not part of the model cache filenames.
        shutil.copyfile(assets / name, snapshot / name.removeprefix("F17_"))
    yield cache
    shutil.rmtree(repository)


def run_embedding_case(binary, cache, case, *arguments):
    # Isolate all model-cache writes inside this fixture's temporary home.
    environment = dict(os.environ, HOME=str(cache.parent.parent))
    result = run_command([binary, case, *arguments], cwd=binary.parent, timeout=180,
                         env=environment)
    assert result.returncode == 0, (result.stdout, result.stderr)
    return result


def embedding_model_reference(texts):
    return reference_embeddings(texts)


def read_embedding_components(path, count):
    rows = parse_json_lines(Path(path).read_bytes())
    assert len(rows) == count
    converted = []
    for row in rows:
        assert isinstance(row, list) and len(row) == 384
        values = [float(x) for x in row]
        assert all(math.isfinite(x) for x in values)
        assert abs(math.sqrt(sum(x*x for x in values)) - 1.0) <= 0.0001
        converted.append(values)
    return converted


