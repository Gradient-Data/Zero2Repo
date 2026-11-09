# feature: F03
"""Acceptance coverage for the six planned schema and constraint entries."""
import pytest
from F01_helpers import build_rust_client, run_native_client
from F02_helpers import SCALAR_CLIENT, scalar_rows, utc_instant
from F03_helpers import schema_run


@pytest.fixture(scope='module')
def schema_client(tmp_path_factory):
    return build_rust_client(SCALAR_CLIENT, tmp_path_factory.mktemp('f03-rust'))


def test_definition_and_inspection(schema_client):
    definition = ('CREATE TABLE detail (id INTEGER PRIMARY KEY AUTO_INCREMENT, '
                  'code TEXT UNIQUE, qty INTEGER NOT NULL DEFAULT 6 CHECK (qty > 0), '
                  'active BOOLEAN DEFAULT TRUE, price FLOAT DEFAULT 2.5, '
                  'note TEXT DEFAULT NULL, born TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    result = schema_run(schema_client, {
        'create': ('E', definition),
        'tables': ('Q', 'SHOW TABLES'),
        'describe': ('Q', 'DESCRIBE detail'),
        'definition': ('Q', 'SHOW CREATE TABLE detail'),
    })
    assert scalar_rows(result['tables']) == [['detail']]
    expected = [['id', 'Integer', 'NO'], ['code', 'Text', 'YES'],
                ['qty', 'Integer', 'NO'], ['active', 'Boolean', 'YES'],
                ['price', 'Float', 'YES'], ['note', 'Text', 'YES'],
                ['born', 'Timestamp', 'YES']]
    assert [row[:3] for row in scalar_rows(result['describe'])] == expected
    ddl = scalar_rows(result['definition'])
    assert len(ddl) == 1 and ddl[0][0] == 'detail'
    # Execute both the declared and reconstructed definitions in fresh databases.
    # Expected outcomes are independent of the text returned by SHOW CREATE.
    for create in (definition, ddl[0][1]):
        r = schema_run(schema_client, {
            'create': ('E', create),
            'describe': ('Q', 'DESCRIBE detail'),
            'one': ('Q', "INSERT INTO detail (code) VALUES ('alpha')"),
            'two': ('E', "INSERT INTO detail (code) VALUES ('beta')"),
            'rows': ('Q', 'SELECT id,code,qty,active,price,note,born FROM detail ORDER BY code'),
            'duplicate_pk': ('X', "INSERT INTO detail (id,code) SELECT id,'gamma' FROM detail WHERE code='alpha'"),
            'duplicate_unique': ('X', "INSERT INTO detail (code) VALUES ('alpha')"),
            'null': ('X', "INSERT INTO detail (code,qty) VALUES ('delta',NULL)"),
            'check': ('X', "INSERT INTO detail (code,qty) VALUES ('epsilon',0)"),
            'after': ('Q', 'SELECT code,qty FROM detail ORDER BY code'),
            'describe_after': ('Q', 'DESCRIBE detail'),
        })
        assert [row[:3] for row in scalar_rows(r['describe'])] == expected
        rows = scalar_rows(r['rows'])
        assert [row[1:6] for row in rows] == [['alpha',6,True,2.5,None], ['beta',6,True,2.5,None]]
        assert rows[0][0] < rows[1][0]
        assert all(row[6][0] == 't' for row in r['rows']['rows'])
        lo, hi = r['one']['window']
        assert lo <= utc_instant(rows[0][6]).timestamp() <= hi
        assert scalar_rows(r['after']) == [['alpha',6],['beta',6]]
        assert scalar_rows(r['describe_after']) == scalar_rows(r['describe'])


def test_constraint_boundaries(schema_client):
    r = schema_run(schema_client, {
        'single': ('E', 'CREATE TABLE single_key (id INTEGER PRIMARY KEY, label TEXT NOT NULL, qty INTEGER CHECK (qty > 0))'),
        'single_ok': ('E', "INSERT INTO single_key VALUES (11,'first',1),(12,'second',NULL)"),
        'pk_duplicate': ('X', "INSERT INTO single_key VALUES (11,'third',2)"),
        'pk_repeated_input': ('X', "INSERT INTO single_key VALUES (13,'new',2),(14,'first duplicate',3),(14,'second duplicate',4)"),
        'pk_null': ('X', "INSERT INTO single_key VALUES (NULL,'third',2)"),
        'not_null': ('X', 'INSERT INTO single_key VALUES (13,NULL,2)'),
        'check': ('X', "INSERT INTO single_key VALUES (13,'third',-1)"),
        'omitted_required': ('X', 'INSERT INTO single_key (id,qty) VALUES (13,2)'),
        'single_rows': ('Q', 'SELECT * FROM single_key ORDER BY id'),
        'pair': ('E', 'CREATE TABLE pair_key (a INTEGER,b INTEGER,PRIMARY KEY(a,b))'),
        'pair_schema': ('Q', 'DESCRIBE pair_key'),
        'pair_ok': ('E', 'INSERT INTO pair_key VALUES (1,2),(1,3),(4,2)'),
        'pair_dup': ('X', 'INSERT INTO pair_key VALUES (1,3)'),
        'pair_null_a': ('X', 'INSERT INTO pair_key VALUES (NULL,8)'),
        'pair_null_b': ('X', 'INSERT INTO pair_key VALUES (8,NULL)'),
        'pair_rows': ('Q', 'SELECT * FROM pair_key ORDER BY a,b'),
        'unique': ('E', 'CREATE TABLE unique_keys (id INTEGER PRIMARY KEY, u TEXT UNIQUE, a INTEGER,b INTEGER, UNIQUE(a,b))'),
        'unique_ok': ('E', "INSERT INTO unique_keys VALUES (1,'a',1,2),(2,'b',1,3),(3,NULL,NULL,2),(4,NULL,NULL,2),(5,'e',3,NULL),(6,'f',3,NULL),(7,'g',4,2)"),
        'unique_single_dup': ('X', "INSERT INTO unique_keys VALUES (8,'a',8,9)"),
        'unique_pair_dup': ('X', "INSERT INTO unique_keys VALUES (8,'h',1,3)"),
        'unique_rows': ('Q', 'SELECT * FROM unique_keys ORDER BY id'),
        'bounded': ('E', 'CREATE TABLE bounded (v INTEGER CHECK(v BETWEEN 2 AND 6))'),
        'bounded_good': ('E', 'INSERT INTO bounded VALUES (2),(6)'),
        'bounded_bad': ('X', 'INSERT INTO bounded VALUES (7)'),
        'bounded_rows': ('Q', 'SELECT v FROM bounded ORDER BY v'),
    })
    assert [row[:3] for row in scalar_rows(r['pair_schema'])] == [['a','Integer','NO'],['b','Integer','NO']]
    assert scalar_rows(r['bounded_rows']) == [[2],[6]]
    assert scalar_rows(r['single_rows']) == [[11,'first',1],[12,'second',None]]
    assert scalar_rows(r['pair_rows']) == [[1,2],[1,3],[4,2]]
    assert scalar_rows(r['unique_rows']) == [[1,'a',1,2],[2,'b',1,3],[3,None,None,2],
                                          [4,None,None,2],[5,'e',3,None],[6,'f',3,None],[7,'g',4,2]]


def test_defaults_and_generated_keys(schema_client, tmp_path):
    r = schema_run(schema_client, {
        'create': ('E', "CREATE TABLE defaults (id INTEGER PRIMARY KEY AUTO_INCREMENT, label TEXT, i INTEGER DEFAULT -9, f FLOAT DEFAULT 3.25, s TEXT DEFAULT 'seed', b BOOLEAN DEFAULT FALSE, n TEXT DEFAULT NULL, absent INTEGER, stamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
        'other': ('E', 'CREATE TABLE other (id INTEGER PRIMARY KEY AUTO_INCREMENT, label TEXT)'),
        'first': ('Q', "INSERT INTO defaults (label) VALUES ('first')"),
        'other_first': ('E', "INSERT INTO other (label) VALUES ('one')"),
        'second': ('E', "INSERT INTO defaults (label) VALUES ('second')"),
        'initial': ('Q', 'SELECT * FROM defaults ORDER BY id'),
        # The explicit key is computed from observed keys, not a fixed sequence origin.
        'explicit': ('E', "INSERT INTO defaults (id,label) SELECT MAX(id)+1000,'explicit' FROM defaults"),
        'high': ('Q', "SELECT id FROM defaults WHERE label='explicit'"),
        'generated': ('E', "INSERT INTO defaults (label) VALUES ('after')"),
        'after': ('Q', "SELECT id FROM defaults WHERE label='after'"),
        'delete': ('E', 'DELETE FROM defaults'),
        'low_explicit': ('E', "INSERT INTO defaults (id,label) VALUES (0,'low')"),
        'again': ('E', "INSERT INTO defaults (label) VALUES ('again')"),
        'last': ('Q', "SELECT id FROM defaults WHERE label='again'"),
        'other_second': ('E', "INSERT INTO other (label) VALUES ('two')"),
        'other_rows': ('Q', 'SELECT id FROM other ORDER BY id'),
    })
    rows = scalar_rows(r['initial'])
    assert [row[1:8] for row in rows] == [['first',-9,3.25,'seed',False,None,None], ['second',-9,3.25,'seed',False,None,None]]
    assert [tag for tag, _ in r['initial']['rows'][0]] == ['i','s','i','f','s','b','n','n','t']
    lo, hi = r['first']['window']
    assert lo <= utc_instant(rows[0][8]).timestamp() <= hi
    first, second = [row[0] for row in rows]
    high = scalar_rows(r['high'])[0][0]
    after = scalar_rows(r['after'])[0][0]
    last = scalar_rows(r['last'])[0][0]
    assert first < second < high < after < last
    other = scalar_rows(r['other_rows'])
    assert len(other) == 2 and other[0][0] < other[1][0]
    defaults = schema_run(schema_client, {
        'create': ('E', 'CREATE TABLE d (id INTEGER, qty INTEGER DEFAULT 17)'),
        'query_insert': ('E', 'INSERT INTO d (id) SELECT 7'),
        'rows': ('Q', 'SELECT * FROM d'),
    })
    assert scalar_rows(defaults['rows']) == [[7,17]]
    # Separate processes prevent an in-memory registry from satisfying reopen.
    # Only keys still stored bound the next generated key after reopening.
    reopen = build_rust_client(r'''
use velnora::{Database, Value};
fn main() {
    let phase = std::env::args().nth(1).unwrap();
    let db = Database::open("file://generated-keys").unwrap();
    if phase == "seed" {
        db.execute("CREATE TABLE persisted (id INTEGER PRIMARY KEY AUTO_INCREMENT, label TEXT)", ()).unwrap();
        db.execute("INSERT INTO persisted VALUES (731,'kept'),(947,'deleted')", ()).unwrap();
        db.execute("DELETE FROM persisted WHERE label='deleted'", ()).unwrap();
    } else {
        let before = db.query("SELECT id,label FROM persisted", ()).and_then(|r|r.collect_vec()).unwrap();
        assert_eq!(before.len(), 1);
        assert_eq!(before[0].get_value(0).unwrap(), &Value::Integer(731));
        assert_eq!(before[0].get_value(1).unwrap(), &Value::from("kept"));
        db.execute("INSERT INTO persisted (label) VALUES ('new')", ()).unwrap();
        let rows = db.query("SELECT id,label FROM persisted ORDER BY id", ()).and_then(|r|r.collect_vec()).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].get_value(0).unwrap(), &Value::Integer(731));
        match rows[1].get_value(0).unwrap() {
            Value::Integer(key) => assert!(*key > 731),
            value => panic!("Expected integer key, got {value:?}"),
        }
        assert_eq!(rows[1].get_value(1).unwrap(), &Value::from("new"));
    }
    db.close().unwrap();
}
''', tmp_path)
    run_native_client(reopen, "seed")
    run_native_client(reopen, "reopen")




def test_add_drop_and_rename(schema_client):
    r = schema_run(schema_client, {
        'create': ('E', 'CREATE TABLE old_table (id INTEGER PRIMARY KEY, text_value TEXT, spare INTEGER)'),
        'insert': ('E', "INSERT INTO old_table VALUES (3,'three',30),(8,'eight',80)"),
        'add_default': ('E', "ALTER TABLE old_table ADD COLUMN added TEXT DEFAULT 'fresh'"),
        'add_null': ('E', 'ALTER TABLE old_table ADD COLUMN optional FLOAT'),
        'required_table': ('E', 'CREATE TABLE added_required (id INTEGER)'),
        'required_add': ('E', 'ALTER TABLE added_required ADD COLUMN v INTEGER NOT NULL DEFAULT 12'),
        'required_good': ('E', 'INSERT INTO added_required (id) VALUES (1)'),
        'required_bad': ('X', 'INSERT INTO added_required VALUES (2,NULL)'),
        'required_rows': ('Q', 'SELECT * FROM added_required'),
        'required_schema': ('Q', 'DESCRIBE added_required'),
        'required_drop': ('E', 'DROP TABLE added_required'),
        'added': ('Q', 'SELECT * FROM old_table ORDER BY id'),
        'drop': ('E', 'ALTER TABLE old_table DROP COLUMN spare'),
        'dropped': ('X', 'SELECT spare FROM old_table'),
        'rename_column': ('E', 'ALTER TABLE old_table RENAME COLUMN text_value TO title'),
        'old_column': ('X', 'SELECT text_value FROM old_table'),
        'current_definition': ('Q', 'SHOW CREATE TABLE old_table'),
        'rename_table': ('E', 'ALTER TABLE old_table RENAME TO renamed'),
        'old_table': ('X', 'SELECT * FROM old_table'),
        'rows': ('Q', 'SELECT * FROM renamed ORDER BY id'),
        'describe': ('Q', 'DESCRIBE renamed'),
        'tables': ('Q', 'SHOW TABLES'),
        'write': ('E', "INSERT INTO renamed (id,title) VALUES (9,'nine')"),
        'new_row': ('Q', 'SELECT id,title,added,optional FROM renamed WHERE id=9'),
    })
    assert scalar_rows(r['required_rows']) == [[1,12]]
    assert [row[:3] for row in scalar_rows(r['required_schema'])] == [['id','Integer','YES'],['v','Integer','NO']]
    assert scalar_rows(r['added']) == [[3,'three',30,'fresh',None],[8,'eight',80,'fresh',None]]
    assert scalar_rows(r['rows']) == [[3,'three','fresh',None],[8,'eight','fresh',None]]
    assert [row[:3] for row in scalar_rows(r['describe'])] == [['id','Integer','NO'],['title','Text','YES'],['added','Text','YES'],['optional','Float','YES']]
    assert scalar_rows(r['tables']) == [['renamed']]
    assert scalar_rows(r['new_row']) == [[9,'nine','fresh',None]]
    ddl = scalar_rows(r['current_definition'])[0]
    assert ddl[0] == 'old_table'
    rebuilt = schema_run(schema_client, {
        'create': ('E', ddl[1]),
        'describe': ('Q', 'DESCRIBE old_table'),
        'insert': ('E', "INSERT INTO old_table (id,title) VALUES (14,'rebuilt')"),
        'rows': ('Q', 'SELECT * FROM old_table'),
    })
    assert [row[:3] for row in scalar_rows(rebuilt['describe'])] == [
        ['id','Integer','NO'],['title','Text','YES'],['added','Text','YES'],['optional','Float','YES']]
    assert scalar_rows(rebuilt['rows']) == [[14,'rebuilt','fresh',None]]


def test_type_conversion_and_atomic_refusal(schema_client):
    r = schema_run(schema_client, {
        'create': ('E', 'CREATE TABLE convert (id INTEGER PRIMARY KEY, v TEXT)'),
        'insert': ('E', "INSERT INTO convert VALUES (1,'27'),(2,'-4'),(3,'invalid'),(4,NULL)"),
        'convert': ('E', 'ALTER TABLE convert MODIFY COLUMN v INTEGER'),
        'converted': ('Q', 'SELECT * FROM convert ORDER BY id'),
        'describe': ('Q', 'DESCRIBE convert'),
        'write': ('E', 'INSERT INTO convert VALUES (5,18)'),
        'write_row': ('Q', 'SELECT v FROM convert WHERE id=5'),
        'required': ('E', 'CREATE TABLE required (id INTEGER PRIMARY KEY, v TEXT NOT NULL)'),
        'required_rows': ('E', "INSERT INTO required VALUES (1,'29'),(2,'bad')"),
        'required_fail': ('X', 'ALTER TABLE required MODIFY COLUMN v INTEGER NOT NULL'),
        'required_after': ('Q', 'SELECT * FROM required ORDER BY id'),
        'required_schema': ('Q', 'DESCRIBE required'),
        'required_still_rejects': ('X', 'INSERT INTO required VALUES (3,NULL)'),
        'unique': ('E', 'CREATE TABLE collision (v TEXT UNIQUE)'),
        'unique_rows': ('E', "INSERT INTO collision VALUES ('7'),('07')"),
        'unique_fail': ('X', 'ALTER TABLE collision MODIFY COLUMN v INTEGER'),
        'unique_after': ('Q', 'SELECT v FROM collision ORDER BY v'),
        'unique_schema': ('Q', 'DESCRIBE collision'),
        'unique_still_rejects': ('X', "INSERT INTO collision VALUES ('07')"),
        'pk_fail': ('X', 'ALTER TABLE convert MODIFY COLUMN id TEXT'),
        'pk_schema': ('Q', 'DESCRIBE convert'),
        'pk_rows': ('Q', 'SELECT * FROM convert ORDER BY id'),
        'nullable': ('E', 'CREATE TABLE nullable (id INTEGER, v INTEGER NOT NULL)'),
        'nullable_insert': ('E', 'INSERT INTO nullable VALUES (1,5)'),
        'null_rejected': ('X', 'INSERT INTO nullable VALUES (2,NULL)'),
        'relax': ('E', 'ALTER TABLE nullable MODIFY COLUMN v INTEGER'),
        'null_accepted': ('E', 'INSERT INTO nullable VALUES (2,NULL)'),
        'relaxed_rows': ('Q', 'SELECT * FROM nullable ORDER BY id'),
        'delete_null': ('E', 'DELETE FROM nullable WHERE id=2'),
        'tighten': ('E', 'ALTER TABLE nullable MODIFY COLUMN v INTEGER NOT NULL'),
        'reject_again': ('X', 'INSERT INTO nullable VALUES (3,NULL)'),
        'accept_again': ('E', 'INSERT INTO nullable VALUES (3,9)'),
        'tight_rows': ('Q', 'SELECT * FROM nullable ORDER BY id'),
        'float_retype': ('E', 'ALTER TABLE nullable MODIFY COLUMN v FLOAT NOT NULL'),
        'float_rows': ('Q', 'SELECT v FROM nullable ORDER BY id'),
        'present_null': ('E', 'CREATE TABLE has_null (v TEXT)'),
        'present_seed': ('E', "INSERT INTO has_null VALUES (NULL),('3')"),
        'present_refuse': ('X', 'ALTER TABLE has_null MODIFY COLUMN v INTEGER NOT NULL'),
        'present_after': ('Q', 'SELECT v FROM has_null ORDER BY v NULLS FIRST'),
        'unique_valid': ('E', 'CREATE TABLE distinct_values (v TEXT UNIQUE)'),
        'unique_valid_seed': ('E', "INSERT INTO distinct_values VALUES ('7'),('8')"),
        'unique_valid_retype': ('E', 'ALTER TABLE distinct_values MODIFY COLUMN v INTEGER'),
        'unique_valid_rows': ('Q', 'SELECT v FROM distinct_values ORDER BY v'),
    })
    assert r['converted']['rows'] == [[('i',1),('i',27)],[('i',2),('i',-4)],[('i',3),('n',None)],[('i',4),('n',None)]]
    assert r['write_row']['rows'] == [[('i',18)]]
    assert [row[:3] for row in scalar_rows(r['describe'])] == [['id','Integer','NO'],['v','Integer','YES']]
    assert scalar_rows(r['required_after']) == [[1,'29'],[2,'bad']]
    assert [row[:3] for row in scalar_rows(r['required_schema'])] == [['id','Integer','NO'],['v','Text','NO']]
    assert scalar_rows(r['unique_after']) == [['07'],['7']]
    assert [row[:3] for row in scalar_rows(r['unique_schema'])] == [['v','Text','YES']]
    assert [row[:3] for row in scalar_rows(r['pk_schema'])] == [['id','Integer','NO'],['v','Integer','YES']]
    assert scalar_rows(r['pk_rows']) == [[1,27],[2,-4],[3,None],[4,None],[5,18]]
    assert scalar_rows(r['relaxed_rows']) == [[1,5],[2,None]]
    assert scalar_rows(r['tight_rows']) == [[1,5],[3,9]]
    assert r['float_rows']['rows'] == [[('f',5.0)],[('f',9.0)]]
    assert scalar_rows(r['present_after']) == [[None],['3']]
    assert r['unique_valid_rows']['rows'] == [[('i',7)],[('i',8)]]


def test_table_lifecycle_errors(schema_client):
    r = schema_run(schema_client, {
        'create': ('E', 'CREATE TABLE kept (id INTEGER, label TEXT)'),
        'insert': ('E', "INSERT INTO kept VALUES (4,'keep')"),
        'duplicate': ('X', 'CREATE TABLE kept (other FLOAT)'),
        'conditional': ('E', 'CREATE TABLE IF NOT EXISTS kept (other FLOAT)'),
        'preserved': ('Q', 'SELECT * FROM kept'),
        'schema': ('Q', 'DESCRIBE kept'),
        'bad_columns': ('X', 'CREATE TABLE bad (v INTEGER, v TEXT)'),
        'missing_table': ('X', 'SELECT * FROM absent'),
        'missing_column': ('X', 'SELECT absent FROM kept'),
        'add_duplicate': ('X', 'ALTER TABLE kept ADD COLUMN label TEXT'),
        'drop_absent': ('X', 'ALTER TABLE kept DROP COLUMN absent'),
        'rename_absent': ('X', 'ALTER TABLE kept RENAME COLUMN absent TO fresh'),
        'modify_absent': ('X', 'ALTER TABLE kept MODIFY COLUMN absent INTEGER'),
        'alter_absent': ('X', 'ALTER TABLE absent ADD COLUMN v INTEGER'),
        'second': ('E', 'CREATE TABLE companion (v INTEGER)'),
        'tables_before': ('Q', 'SHOW TABLES'),
        'drop': ('E', 'DROP TABLE kept'),
        'missing_after': ('X', 'SELECT * FROM kept'),
        'schema_after': ('X', 'DESCRIBE kept'),
        'unconditional_missing_drop': ('X', 'DROP TABLE kept'),
        'conditional_drop': ('E', 'DROP TABLE IF EXISTS kept'),
        'drop_second': ('E', 'DROP TABLE companion'),
        'tables_after': ('Q', 'SHOW TABLES'),
        'recreate': ('E', 'CREATE TABLE IF NOT EXISTS kept (id INTEGER, label TEXT)'),
        'empty': ('Q', 'SELECT * FROM kept'),
        'new': ('E', "INSERT INTO kept VALUES (9,'new')"),
        'new_rows': ('Q', 'SELECT * FROM kept'),
        'conditional_existing_drop': ('E', 'DROP TABLE IF EXISTS kept'),
        'final': ('Q', 'SHOW TABLES'),
    })
    assert scalar_rows(r['preserved']) == [[4,'keep']]
    assert [row[:3] for row in scalar_rows(r['schema'])] == [['id','Integer','YES'],['label','Text','YES']]
    assert sorted(scalar_rows(r['tables_before'])) == [['companion'],['kept']]
    assert scalar_rows(r['tables_after']) == []
    assert scalar_rows(r['empty']) == []
    assert scalar_rows(r['new_rows']) == [[9,'new']]
    assert scalar_rows(r['final']) == []
