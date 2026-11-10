# feature: F13
"""Four planned acceptance checks for reusable, persistent, read-only views."""
import pytest

from _helpers import run_command
from F01_helpers import build_rust_client, run_native_client
from F13_helpers import VIEW_SUPPORT

VIEW_CASES = r'''
fn visible_views() {
    for (level,snapshot) in [(IsolationLevel::ReadCommitted,false),(IsolationLevel::SnapshotIsolation,true)] {
        // Each arm starts with identical data; only the isolation level differs.
        let dsn=if snapshot {"memory://f13_snapshot"} else {"memory://f13_committed"};
        let reader=Database::open(dsn).unwrap();
        let writer=Database::open(dsn).unwrap();
        view_base(&reader);view_definitions(&reader);
        let initial=vec![(1,"cedar".into(),16),(3,"birch".into(),25)];
        let changed=vec![(1,"cedar".into(),34),(4,"elm".into(),28),(5,"pine".into(),22)];
        let mut tx=reader.begin_with_isolation(level).unwrap();
        assert_eq!(view_tx_rows(&mut tx,"SELECT * FROM offers ORDER BY item","total"),initial);
        assert_eq!(view_tx_rows(&mut tx,"SELECT * FROM selected ORDER BY item","adjusted"),vec![(3,"birch".into(),23)]);
        exec(&writer,"BEGIN");
        exec(&writer,"UPDATE stock SET amount=11 WHERE id=1");
        exec(&writer,"DELETE FROM stock WHERE id=3");
        exec(&writer,"INSERT INTO stock VALUES (5,'pine',7,TRUE)");
        exec(&writer,"UPDATE stock SET enabled=TRUE WHERE id=4");
        assert_eq!(view_rows(&writer,"SELECT * FROM offers ORDER BY item","total"),changed);
        assert_eq!(view_tx_rows(&mut tx,"SELECT * FROM offers ORDER BY item","total"),initial);
        exec(&writer,"COMMIT");
        assert_eq!(view_tx_rows(&mut tx,"SELECT * FROM offers ORDER BY item","total"),
                   if snapshot {initial.clone()} else {changed.clone()});
        assert_eq!(view_tx_rows(&mut tx,"SELECT * FROM selected ORDER BY item","adjusted"),
                   if snapshot {vec![(3,"birch".into(),23)]}
                   else {vec![(1,"cedar".into(),32),(4,"elm".into(),26),(5,"pine".into(),20)]});
        tx.execute("UPDATE stock SET amount=6 WHERE id=2",()).unwrap();
        assert_eq!(view_tx_rows(&mut tx,"SELECT * FROM offers WHERE item=2","total"),vec![(2,"ash".into(),19)]);
        tx.rollback().unwrap();drop(tx);
        assert_eq!(view_rows(&reader,"SELECT * FROM offers ORDER BY item","total"),changed);
        // Read by ordinal as well as by name: projection order is caller-visible.
        let projected=read_rows(&reader,"SELECT title,item FROM offers ORDER BY item").unwrap();
        let observed:Vec<(String,i64)>=projected.iter().map(|r|(r.get(0).unwrap(),r.get(1).unwrap())).collect();
        assert_eq!(observed,vec![("cedar".into(),1),("elm".into(),4),("pine".into(),5)]);
        let bound=reader.query("SELECT item FROM offers WHERE item > $1 ORDER BY item",(3i64,)).unwrap().collect_vec().unwrap();
        let ids:Vec<i64>=bound.iter().map(|r|r.get(0).unwrap()).collect();
        assert_eq!(ids,vec![4,5]);
        exec(&reader,"CREATE VIEW top_offer AS SELECT item FROM offers ORDER BY total DESC LIMIT 1");
        assert_eq!(reader.query_one::<i64,_>("SELECT item FROM top_offer",()).unwrap(),1);
        assert_eq!(reader.query_one::<i64,_>("SELECT COUNT(*) FROM top_offer",()).unwrap(),1);
        // Projection, outer filtering and nested arithmetic all have independent values.
        assert_eq!(view_rows(&reader,"SELECT title,item,adjusted FROM selected WHERE adjusted>20 ORDER BY item DESC","adjusted"),
                   vec![(4,"elm".into(),26),(1,"cedar".into(),32)]);
    }
}
fn persistent_views(phase: &str,path: &str) {
    let close_mode=std::env::args().nth(3).unwrap();
    let db=Database::open(&format!("file://{path}?sync_mode=full&checkpoint_interval=0&checkpoint_on_close={close_mode}")).unwrap();
    if phase=="create" {
        view_base(&db);
        assert_eq!(view_catalog(&db),Vec::<String>::new());
        view_definitions(&db);
    }
    if phase=="dropped" {
        assert_eq!(view_catalog(&db),vec!["offers"]);
        reject(&db,"SELECT * FROM selected");
        assert_eq!(view_rows(&db,"SELECT * FROM offers ORDER BY item","total"),
                   vec![(2,"ash".into(),13),(3,"birch".into(),25),(4,"elm".into(),28)]);
        db.close().unwrap();return;
    }
    assert_eq!(view_catalog(&db),vec!["offers","selected"]);
    let offers=view_definition(&db,"offers");
    let selected=view_definition(&db,"selected");
    let original=vec![(1,"cedar".into(),16),(3,"birch".into(),25)];
    if phase=="again" {
        assert_eq!(view_rows(&db,"SELECT * FROM offers ORDER BY item","total"),
                   vec![(2,"ash".into(),13),(3,"birch".into(),25),(4,"elm".into(),28)]);
        assert_eq!(view_rows(&db,"SELECT * FROM selected ORDER BY item","adjusted"),
                   vec![(3,"birch".into(),23),(4,"elm".into(),26)]);
    } else {
        assert_eq!(view_rows(&db,"SELECT * FROM offers ORDER BY item","total"),original);
        assert_eq!(view_rows(&db,"SELECT * FROM selected ORDER BY item","adjusted"),vec![(3,"birch".into(),23)]);
    }
    if phase=="reopen" {
        // Treat inspected definitions as executable SQL, never compare their formatting.
        // Rebuild in an independent database with different rows to rule out row literals.
        let rebuilt=Database::open_in_memory().unwrap();view_base(&rebuilt);
        exec(&rebuilt,"UPDATE stock SET amount=4 WHERE id=2");
        exec(&rebuilt,"UPDATE stock SET enabled=TRUE WHERE id=4");
        exec(&rebuilt,"DELETE FROM stock WHERE id=1");
        exec(&rebuilt,&offers);exec(&rebuilt,&selected);
        assert_eq!(view_rows(&rebuilt,"SELECT * FROM offers ORDER BY item","total"),
                   vec![(2,"ash".into(),13),(3,"birch".into(),25),(4,"elm".into(),28)]);
        assert_eq!(view_rows(&rebuilt,"SELECT * FROM selected ORDER BY item","adjusted"),
                   vec![(3,"birch".into(),23),(4,"elm".into(),26)]);
        exec(&db,"UPDATE stock SET amount=4 WHERE id=2");
        exec(&db,"UPDATE stock SET enabled=TRUE WHERE id=4");
        exec(&db,"DELETE FROM stock WHERE id=1");
        assert_eq!(view_rows(&db,"SELECT * FROM offers ORDER BY item","total"),
                   vec![(2,"ash".into(),13),(3,"birch".into(),25),(4,"elm".into(),28)]);
    }
    if phase=="again" {exec(&db,"DROP VIEW selected");}
    db.close().unwrap();
}
fn view_conflicts() {
    let db=Database::open_in_memory().unwrap();view_base(&db);
    let base=vec![(1,"cedar".into(),5,true),(2,"ash".into(),2,true),
                  (3,"birch".into(),8,true),(4,"elm".into(),9,false)];
    assert_eq!(view_stock(&db),base);
    for sql in ["CREATE VIEW stock AS SELECT id FROM stock",
                "CREATE VIEW IF NOT EXISTS stock AS SELECT id FROM stock"] {
        reject(&db,sql);assert_eq!(view_stock(&db),base);
    }
    exec(&db,"CREATE VIEW IF NOT EXISTS kept AS SELECT id AS item,label AS title,amount+10 AS total FROM stock WHERE enabled=TRUE");
    let expected=vec![(1,"cedar".into(),15),(2,"ash".into(),12),(3,"birch".into(),18)];
    assert_eq!(view_rows(&db,"SELECT * FROM kept ORDER BY item","total"),expected);
    reject(&db,"CREATE VIEW kept AS SELECT id AS item,label AS title,amount*100 AS total FROM stock WHERE enabled=FALSE");
    assert_eq!(view_rows(&db,"SELECT * FROM kept ORDER BY item","total"),expected);
    exec(&db,"CREATE VIEW IF NOT EXISTS kept AS SELECT id AS item,label AS title,amount*100 AS total FROM stock WHERE enabled=FALSE");
    assert_eq!(view_rows(&db,"SELECT * FROM kept ORDER BY item","total"),expected);
    let definition=view_definition(&db,"kept");
    let rebuilt=Database::open_in_memory().unwrap();view_base(&rebuilt);
    exec(&rebuilt,&definition);
    assert_eq!(view_rows(&rebuilt,"SELECT * FROM kept ORDER BY item","total"),expected);
    exec(&db,"UPDATE stock SET amount=13 WHERE id=2");
    assert_eq!(view_rows(&db,"SELECT * FROM kept ORDER BY item","total"),
               vec![(1,"cedar".into(),15),(2,"ash".into(),23),(3,"birch".into(),18)]);
    assert_eq!(view_catalog(&db),vec!["kept"]);
}
fn readonly_and_drop() {
    let db=Database::open_in_memory().unwrap();view_base(&db);
    exec(&db,"CREATE VIEW readonly_stock AS SELECT * FROM stock");
    exec(&db,"CREATE VIEW survivor AS SELECT id AS item,label AS title,amount+1 AS total FROM stock");
    let base=vec![(1,"cedar".into(),5,true),(2,"ash".into(),2,true),
                  (3,"birch".into(),8,true),(4,"elm".into(),9,false)];
    assert_eq!(view_stock(&db),base);
    let query="SELECT id AS item,label AS title,amount AS total FROM readonly_stock ORDER BY item";
    let expected=vec![(1,"cedar".into(),5),(2,"ash".into(),2),(3,"birch".into(),8),(4,"elm".into(),9)];
    assert_eq!(view_rows(&db,query,"total"),expected);
    for sql in ["INSERT INTO readonly_stock VALUES (8,'fir',12,TRUE)",
                "UPDATE readonly_stock SET amount=77 WHERE id=1",
                "DELETE FROM readonly_stock WHERE id=3"] {
        reject(&db,sql);
        assert_eq!(view_stock(&db),base);
        assert_eq!(view_rows(&db,query,"total"),expected);
    }
    assert_eq!(view_catalog(&db),vec!["readonly_stock","survivor"]);
    exec(&db,"DROP VIEW readonly_stock");
    reject(&db,"SELECT * FROM readonly_stock");
    assert_eq!(view_catalog(&db),vec!["survivor"]);
    assert_eq!(view_stock(&db),base);
    assert_eq!(view_rows(&db,"SELECT * FROM survivor ORDER BY item","total"),
               vec![(1,"cedar".into(),6),(2,"ash".into(),3),(3,"birch".into(),9),(4,"elm".into(),10)]);
    exec(&db,"CREATE VIEW readonly_stock AS SELECT id AS item,label AS title,amount*2 AS total FROM stock WHERE enabled=FALSE");
    assert_eq!(view_rows(&db,"SELECT * FROM readonly_stock","total"),vec![(4,"elm".into(),18)]);
}
fn main() {
    let args:Vec<String>=std::env::args().collect();
    match args[1].as_str() {
        "visible"=>visible_views(),"conflicts"=>view_conflicts(),"readonly"=>readonly_and_drop(),
        "create"|"reopen"|"again"|"dropped"=>persistent_views(&args[1],&args[2]),
        other=>panic!("unknown scenario {other}")
    }
}
'''


@pytest.fixture(scope="module")
def view_client(tmp_path_factory):
    return build_rust_client(VIEW_SUPPORT + VIEW_CASES, tmp_path_factory.mktemp("f13-client"))


def test_visible_aliased_and_nested_views(view_client):
    run_native_client(view_client, "visible")


def test_view_definitions_survive_reopen(view_client, tmp_path):
    for close_mode in ("on", "off"):
        path = tmp_path / close_mode
        for phase in ("create", "reopen", "again", "dropped"):
            result = run_command([view_client, phase, path, close_mode], cwd=view_client.parent, timeout=120)
            assert result.returncode == 0, (close_mode, phase, result.stdout, result.stderr)


def test_namespace_conflicts_and_conditional_creation(view_client):
    run_native_client(view_client, "conflicts")


def test_readonly_views_and_drop_preserve_base_rows(view_client):
    run_native_client(view_client, "readonly")
