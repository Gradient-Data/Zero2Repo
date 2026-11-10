# feature: F05
"""Seven planned mutation acceptance tests through the public Rust SQL API."""
import pytest
from F01_helpers import build_rust_client
from F02_helpers import SCALAR_CLIENT, scalar_rows
from F03_helpers import schema_run
from _helpers import rows_equal


@pytest.fixture(scope="module")
def mutation_client(tmp_path_factory):
    return build_rust_client(SCALAR_CLIENT, tmp_path_factory.mktemp("f05-rust"))


def test_insert_values_and_queries(mutation_client):
    r = schema_run(mutation_client, {
        "create": ("E", "CREATE TABLE dst (id INTEGER PRIMARY KEY, label TEXT, qty INTEGER DEFAULT 17)"),
        "values": ("E", "INSERT INTO dst (label,id) VALUES ('birch',8),('ash',3)"),
        "heap": ("E", "CREATE TABLE heap (label TEXT, qty INTEGER DEFAULT 23, optional INTEGER)"),
        "heap_values": ("E", "INSERT INTO heap (label) VALUES ('elm'),('elm')"),
        "query": ("E", "INSERT INTO heap (qty,label) SELECT id+qty,label FROM dst WHERE id>3"),
        "query_pk": ("E", "INSERT INTO dst (qty,id,label) SELECT qty+1,id+10,label FROM dst WHERE id=3"),
        "query_default": ("E", "INSERT INTO dst (id,label) SELECT id+100,label FROM dst WHERE id=8"),
        "empty": ("E", "INSERT INTO heap (label) SELECT label FROM dst WHERE id<0"),
        "dst": ("Q", "SELECT * FROM dst ORDER BY id"),
        "rows": ("Q", "SELECT * FROM heap"),
    })
    for name, count in [("values",2),("heap_values",2),("query",1),("query_pk",1),("query_default",1),("empty",0)]:
        assert r[name]["affected"] == count
    assert scalar_rows(r["dst"]) == [[3,"ash",17],[8,"birch",17],[13,"ash",18],[108,"birch",17]]
    assert rows_equal(scalar_rows(r["rows"]), [["elm",23,None],["elm",23,None],["birch",25,None]], ordered=False)
    assert [tag for tag, _ in r["dst"]["rows"][0]] == ['i','s','i']

    # Creating a table from a query must materialize its expressions and schema.
    r = schema_run(mutation_client, {
        "source": ("E", "CREATE TABLE source (id INTEGER PRIMARY KEY, label TEXT NOT NULL DEFAULT 'new', qty INTEGER CHECK(qty>0))"),
        "seed": ("E", "INSERT INTO source VALUES (4,'cedar',7),(9,'maple',13),(12,'elm',21)"),
        "create": ("E", "CREATE TABLE copied AS SELECT label AS title,id AS code,qty*0.5 AS amount FROM source WHERE id<12"),
        "schema": ("Q", "DESCRIBE copied"),
        "rows": ("Q", "SELECT * FROM copied ORDER BY code"),
        "source_change": ("E", "UPDATE source SET label='changed',qty=30 WHERE id=4"),
        "source_delete": ("E", "DELETE FROM source WHERE id=9"),
        "independent": ("Q", "SELECT * FROM copied ORDER BY code"),
        "occupied": ("X", "CREATE TABLE copied AS SELECT label FROM source"),
        "still_present": ("Q", "SELECT * FROM copied ORDER BY code"),
        "duplicate": ("E", "INSERT INTO copied VALUES ('cedar',4,-2.5)"),
        "omitted": ("E", "INSERT INTO copied (code) VALUES (130)"),
        "mutable": ("Q", "SELECT * FROM copied ORDER BY code,amount"),
    })
    expected = [['cedar',4,3.5],['maple',9,6.5]]
    assert scalar_rows(r['rows']) == expected
    assert [row[:3] for row in scalar_rows(r['schema'])] == [
        ['title','Text','YES'],['code','Integer','YES'],['amount','Float','YES']]
    assert scalar_rows(r['independent']) == expected
    assert scalar_rows(r['still_present']) == expected
    assert r['duplicate']['affected'] == r['omitted']['affected'] == 1
    assert scalar_rows(r['mutable']) == [['cedar',4,-2.5],['cedar',4,3.5],
                                         ['maple',9,6.5],[None,130,None]]


def test_update_delete_predicates_and_defaults(mutation_client):
    r = schema_run(mutation_client, {
        "create": ("E", "CREATE TABLE t (id INTEGER PRIMARY KEY,a INTEGER,b INTEGER,note TEXT DEFAULT 'restored')"),
        "seed": ("E", "INSERT INTO t VALUES (1,4,9,'one'),(2,7,13,'two'),(3,11,18,'three')"),
        "update": ("E", "UPDATE t SET a=b+2,b=a+3 WHERE id<>2"),
        "updated": ("Q", "SELECT * FROM t ORDER BY id"),
        "default": ("E", "UPDATE t SET note=DEFAULT WHERE id=3"),
        "none": ("E", "UPDATE t SET a=99 WHERE id=9"),
        "before_delete": ("Q", "SELECT * FROM t ORDER BY id"),
        "delete": ("E", "DELETE FROM t WHERE a>10 AND id<>3"),
        "delete_none": ("E", "DELETE FROM t WHERE id=9"),
        "after": ("Q", "SELECT * FROM t ORDER BY id"),
        "key_update": ("E", "UPDATE t SET a=b+2,b=a+3 WHERE id=2"),
        "key_updated": ("Q", "SELECT * FROM t ORDER BY id"),
        "key_delete": ("E", "DELETE FROM t WHERE id=2"),
        "key_remaining": ("Q", "SELECT * FROM t ORDER BY id"),
    })
    for name,count in [("update",2),("default",1),("none",0),("delete",1),("delete_none",0)]:
        assert r[name]["affected"] == count
    assert scalar_rows(r["updated"]) == [[1,11,7,'one'],[2,7,13,'two'],[3,20,14,'three']]
    assert scalar_rows(r["before_delete"]) == [[1,11,7,'one'],[2,7,13,'two'],[3,20,14,'restored']]
    assert scalar_rows(r["after"]) == [[2,7,13,'two'],[3,20,14,'restored']]
    assert r["key_update"]["affected"] == r["key_delete"]["affected"] == 1
    assert scalar_rows(r["key_updated"]) == [[2,15,10,'two'],[3,20,14,'restored']]
    assert scalar_rows(r["key_remaining"]) == [[3,20,14,'restored']]


def test_conflict_actions_and_targets(mutation_client):
    r = schema_run(mutation_client, {
        "create": ("E", "CREATE TABLE t (id INTEGER PRIMARY KEY,u TEXT UNIQUE,v INTEGER)"),
        "seed": ("E", "INSERT INTO t VALUES (1,'a',10),(2,'b',20)"),
        "skip": ("E", "INSERT INTO t VALUES (1,'z',99),(3,'c',30) ON CONFLICT (id) DO NOTHING"),
        "untargeted": ("E", "INSERT INTO t VALUES (4,'b',99),(1,'q',99),(5,'e',50) ON CONFLICT DO NOTHING"),
        "wrong_skip": ("X", "INSERT INTO t VALUES (8,'a',88) ON CONFLICT (id) DO NOTHING"),
        "wrong_update": ("X", "INSERT INTO t VALUES (1,'h',88) ON CONFLICT (u) DO UPDATE SET v=excluded.v"),
        "update": ("E", "INSERT INTO t VALUES (9,'b',7),(6,'f',60) ON CONFLICT (u) DO UPDATE SET v=t.v+excluded.v"),
        "any_update": ("E", "INSERT INTO t VALUES (1,'z',4),(9,'c',5) ON CONFLICT DO UPDATE SET v=t.v+excluded.v"),
        "rows": ("Q", "SELECT * FROM t ORDER BY id"),
        "heap": ("E", "CREATE TABLE h (a TEXT,b INTEGER,v INTEGER,UNIQUE(a,b))"),
        "heap_seed": ("E", "INSERT INTO h VALUES ('x',1,10),('x',2,20),('y',1,30)"),
        "partial_key": ("X", "INSERT INTO h VALUES ('x',1,99) ON CONFLICT (a) DO NOTHING"),
        "extended_key": ("X", "INSERT INTO h VALUES ('x',1,99) ON CONFLICT (a,b,v) DO UPDATE SET v=excluded.v"),
        "src": ("E", "CREATE TABLE src (a TEXT,b INTEGER,v INTEGER)"),
        "src_seed": ("E", "INSERT INTO src VALUES ('x',1,3),('y',2,8)"),
        "query_skip": ("E", "INSERT INTO h SELECT * FROM src ON CONFLICT (a,b) DO NOTHING"),
        "skipped": ("Q", "SELECT * FROM h ORDER BY a,b"),
        "query_update": ("E", "INSERT INTO h SELECT a,b,v+1 FROM src ON CONFLICT (a,b) DO UPDATE SET v=h.v+excluded.v"),
        "heap_rows": ("Q", "SELECT * FROM h ORDER BY a,b"),
        "single": ("E", "CREATE TABLE single_u (u TEXT UNIQUE,v INTEGER)"),
        "single_seed": ("E", "INSERT INTO single_u VALUES ('s',6)"),
        "single_update": ("E", "INSERT INTO single_u VALUES ('s',4),('t',9) ON CONFLICT (u) DO UPDATE SET v=single_u.v+excluded.v"),
        "single_rows": ("Q", "SELECT * FROM single_u ORDER BY u"),
    })
    for name,count in [("skip",1),("untargeted",1),("update",2),("any_update",2),("query_skip",1),("query_update",2),("single_update",2)]:
        assert r[name]["affected"] == count
    assert scalar_rows(r["rows"]) == [[1,'a',14],[2,'b',27],[3,'c',35],[5,'e',50],[6,'f',60]]
    assert scalar_rows(r["skipped"]) == [['x',1,10],['x',2,20],['y',1,30],['y',2,8]]
    assert scalar_rows(r["heap_rows"]) == [['x',1,14],['x',2,20],['y',1,30],['y',2,17]]
    assert scalar_rows(r["single_rows"]) == [['s',10],['t',9]]


def test_conditional_conflict_update(mutation_client):
    # The same mixed candidates exercise both supported input sources.
    for source in ("VALUES (1,7),(2,4),(3,9),(4,2)", "SELECT * FROM incoming"):
        r = schema_run(mutation_client, {
            "create": ("E", "CREATE TABLE t (id INTEGER PRIMARY KEY,v INTEGER)"),
            "seed": ("E", "INSERT INTO t VALUES (1,3),(2,8),(3,NULL)"),
            "src": ("E", "CREATE TABLE incoming (id INTEGER,v INTEGER)"),
            "src_seed": ("E", "INSERT INTO incoming VALUES (1,7),(2,4),(3,9),(4,2)"),
            "mutate": ("E", f"INSERT INTO t {source} ON CONFLICT (id) DO UPDATE SET v=t.v+excluded.v WHERE excluded.v>t.v"),
            "rows": ("Q", "SELECT * FROM t ORDER BY id"),
            "false": ("E", "INSERT INTO t VALUES (1,100) ON CONFLICT (id) DO UPDATE SET v=excluded.v WHERE FALSE"),
            "unknown": ("E", "INSERT INTO t VALUES (2,100) ON CONFLICT (id) DO UPDATE SET v=excluded.v WHERE NULL"),
            "after": ("Q", "SELECT * FROM t ORDER BY id"),
        })
        assert r["mutate"]["affected"] == 2
        assert r["false"]["affected"] == r["unknown"]["affected"] == 0
        assert scalar_rows(r["rows"]) == [[1,10],[2,8],[3,None],[4,2]]
        assert scalar_rows(r["after"]) == [[1,10],[2,8],[3,None],[4,2]]


def test_returning_row_versions(mutation_client):
    r = schema_run(mutation_client, {
        "create": ("E", "CREATE TABLE t (id INTEGER PRIMARY KEY,v INTEGER DEFAULT 12)"),
        "insert": ("Q", "INSERT INTO t (id) VALUES (3),(8) RETURNING id,v,v+1"),
        "inserted": ("Q", "SELECT * FROM t ORDER BY id"),
        "update": ("Q", "UPDATE t SET v=v+id RETURNING id,v,v*2"),
        "updated": ("Q", "SELECT * FROM t ORDER BY id"),
        "no_update": ("Q", "UPDATE t SET v=0 WHERE id=99 RETURNING *"),
        "delete": ("Q", "DELETE FROM t WHERE id=3 RETURNING id,v,v-1"),
        "deleted": ("Q", "SELECT * FROM t ORDER BY id"),
        "no_delete": ("Q", "DELETE FROM t WHERE id=99 RETURNING *"),
        "no_insert": ("Q", "INSERT INTO t SELECT id+100,v FROM t WHERE id=99 RETURNING *"),
        "upsert": ("Q", "INSERT INTO t VALUES (8,7),(12,30) ON CONFLICT(id) DO UPDATE SET v=t.v+excluded.v RETURNING id,v"),
        "skip": ("Q", "INSERT INTO t VALUES (8,99),(15,41) ON CONFLICT(id) DO NOTHING RETURNING id,v"),
        "conditional_skip": ("Q", "INSERT INTO t VALUES (8,100) ON CONFLICT(id) DO UPDATE SET v=excluded.v WHERE FALSE RETURNING id,v"),
        "final": ("Q", "SELECT * FROM t ORDER BY id"),
    })
    assert rows_equal(scalar_rows(r["insert"]), [[3,12,13],[8,12,13]], ordered=False)
    assert rows_equal(scalar_rows(r["upsert"]), [[8,27],[12,30]], ordered=False)
    assert scalar_rows(r["skip"]) == [[15,41]]
    assert scalar_rows(r["conditional_skip"]) == []
    assert scalar_rows(r["final"]) == [[8,27],[12,30],[15,41]]
    assert scalar_rows(r["inserted"]) == [[3,12],[8,12]]
    assert rows_equal(scalar_rows(r["update"]), [[3,15,30],[8,20,40]], ordered=False)
    assert scalar_rows(r["updated"]) == [[3,15],[8,20]]
    assert scalar_rows(r["delete"]) == [[3,15,14]]
    assert scalar_rows(r["deleted"]) == [[8,20]]
    for name in ("no_update","no_delete","no_insert"):
        assert scalar_rows(r[name]) == []


def test_mutation_failure_atomicity(mutation_client):
    statements = [
        "INSERT INTO t VALUES (3,30),(1,40)",
        "INSERT INTO t VALUES (3,30),(4,20)",
        "INSERT INTO t VALUES (3,30),(4,NULL)",
        "INSERT INTO t SELECT 3,30 UNION ALL SELECT 4,-1",
        "UPDATE t SET v=CASE WHEN id=1 THEN 30 ELSE -1 END",
        "UPDATE t SET v=30",
        "UPDATE t SET id=id+10",
        "UPDATE t SET id=9 WHERE id=1",
        "UPDATE t SET v=-1 WHERE id=1",
        "INSERT INTO t VALUES (3,30),(2,-1) ON CONFLICT(id) DO UPDATE SET v=excluded.v",
        "INSERT INTO t VALUES (3,30),(2,40) ON CONFLICT(id) DO UPDATE SET v=excluded.v WHERE 'x' REGEXP CASE WHEN excluded.id=2 THEN '[' ELSE 'x' END",
    ]
    for mutation in [
        "INSERT INTO t VALUES (3,30),(4,40)",
        "INSERT INTO t SELECT id+2,v+20 FROM t ORDER BY id",
        "INSERT INTO t VALUES (1,30),(2,40) ON CONFLICT(id) DO UPDATE SET v=excluded.v",
        "INSERT INTO t SELECT id,v+20 FROM t ORDER BY id ON CONFLICT(id) DO UPDATE SET v=excluded.v",
        "UPDATE t SET v=v+20",
        "DELETE FROM t",
    ]:
        statements.append(mutation + " RETURNING 'x' REGEXP CASE WHEN id IN (2,4) THEN '[' ELSE 'x' END")
    for statement in statements:
        r = schema_run(mutation_client, {
            "create": ("E", "CREATE TABLE t (id INTEGER PRIMARY KEY,v INTEGER NOT NULL UNIQUE CHECK(v>0))"),
            "seed": ("E", "INSERT INTO t VALUES (1,10),(2,20)"),
            "before": ("Q", "SELECT * FROM t ORDER BY id"),
            "failure": ("X", statement),
            "after": ("Q", "SELECT * FROM t ORDER BY id"),
            "usable": ("E", "INSERT INTO t VALUES (5,50)"),
            "final": ("Q", "SELECT * FROM t ORDER BY id"),
        })
        assert scalar_rows(r["before"]) == [[1,10],[2,20]], statement
        assert scalar_rows(r["after"]) == [[1,10],[2,20]], (statement,r)
        assert r["usable"]["affected"] == 1
        assert scalar_rows(r["final"]) == [[1,10],[2,20],[5,50]], statement



    # Explicit transactions must roll back just the failed statement, preserving earlier work.
    for statement in [
        "INSERT INTO t VALUES (3,30),(4,20)",
        "INSERT INTO t VALUES (3,30),(2,-1) ON CONFLICT(id) DO UPDATE SET v=excluded.v",
    ]:
        r = schema_run(mutation_client, {
            "create": ("E", "CREATE TABLE t (id INTEGER PRIMARY KEY,v INTEGER UNIQUE CHECK(v>0))"),
            "seed": ("E", "INSERT INTO t VALUES (1,10),(2,20)"),
            "begin": ("E", "BEGIN"),
            "prior": ("E", "INSERT INTO t VALUES (6,60)"),
            "failure": ("X", statement),
            "after": ("Q", "SELECT * FROM t ORDER BY id"),
            "continue": ("E", "INSERT INTO t VALUES (5,50)"),
            "commit": ("E", "COMMIT"),
            "final": ("Q", "SELECT * FROM t ORDER BY id"),
        })
        assert scalar_rows(r["after"]) == [[1,10],[2,20],[6,60]], statement
        assert scalar_rows(r["final"]) == [[1,10],[2,20],[5,50],[6,60]], statement


def test_truncate_retains_usable_schema(mutation_client):
    r = schema_run(mutation_client, {
        "create": ("E", "CREATE TABLE t (id INTEGER PRIMARY KEY,label TEXT NOT NULL UNIQUE,qty INTEGER DEFAULT 19 CHECK(qty>0))"),
        "seed": ("E", "INSERT INTO t VALUES (3,'old',5),(7,'older',9)"),
        "before": ("Q", "SELECT * FROM t ORDER BY id"),
        "schema_before": ("Q", "DESCRIBE t"),
        "truncate": ("E", "TRUNCATE TABLE t"),
        "empty": ("Q", "SELECT * FROM t"),
        "schema_after": ("Q", "DESCRIBE t"),
        "insert": ("E", "INSERT INTO t (id,label) VALUES (3,'new'),(11,'old')"),
        "rows": ("Q", "SELECT * FROM t ORDER BY id"),
        "pk": ("X", "INSERT INTO t VALUES (3,'duplicate',1)"),
        "unique": ("X", "INSERT INTO t VALUES (8,'old',1)"),
        "null": ("X", "INSERT INTO t VALUES (8,NULL,1)"),
        "check": ("X", "INSERT INTO t VALUES (8,'invalid',0)"),
        "final": ("Q", "SELECT * FROM t ORDER BY id"),
    })
    assert scalar_rows(r["before"]) == [[3,'old',5],[7,'older',9]]
    assert scalar_rows(r["empty"]) == []
    assert scalar_rows(r["schema_before"]) == scalar_rows(r["schema_after"])
    assert r["insert"]["affected"] == 2
    assert scalar_rows(r["rows"]) == [[3,'new',19],[11,'old',19]]
    assert scalar_rows(r["final"]) == [[3,'new',19],[11,'old',19]]
