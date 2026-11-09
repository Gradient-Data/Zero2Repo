# feature: F10
"""Subqueries and statement-scoped recursive relations through Rust SQL."""
import pytest
from _helpers import rows_equal
from F01_helpers import build_rust_client
from F02_helpers import scalar_rows, scalar_batch
from F03_helpers import schema_run
from F11_helpers import aggregate_rows_equal
from F04_helpers import SELECTION_CLIENT, selection_columns


@pytest.fixture(scope='module')
def subqueries_client(tmp_path_factory):
    return build_rust_client(SELECTION_CLIENT, tmp_path_factory.mktemp('f10-rust'))


def test_scalar_and_existence(subqueries_client):
    result = schema_run(subqueries_client, {
        'create': ('E', 'CREATE TABLE samples (v INTEGER)'),
        'insert': ('E', 'INSERT INTO samples VALUES (17),(NULL),(29)'),
        'single': ('Q', 'SELECT (SELECT v FROM samples WHERE v=17)'),
        'empty': ('Q', 'SELECT (SELECT v FROM samples WHERE v=99)'),
        'null': ('Q', 'SELECT (SELECT v FROM samples WHERE v IS NULL)'),
        'exists': ('Q', 'SELECT EXISTS (SELECT v FROM samples WHERE v IS NULL), EXISTS (SELECT v FROM samples WHERE v=99), NOT EXISTS (SELECT v FROM samples WHERE v IS NULL), NOT EXISTS (SELECT v FROM samples WHERE v=99)'),
        'multiple': ('X', 'SELECT (SELECT v FROM samples WHERE v IS NOT NULL)'),
    })
    for key, expected in {'single': [[17]], 'empty': [[None]], 'null': [[None]],
                          'exists': [[True,False,False,True]]}.items():
        assert rows_equal(scalar_rows(result[key]), expected, ordered=False), result[key]


def test_membership_and_quantified_truth(subqueries_client):
    setup = {
        'create': ('E', 'CREATE TABLE choices (v INTEGER)'),
        'insert': ('E', 'INSERT INTO choices VALUES (4),(9),(NULL)'),
    }
    # Each row covers a distinct decisive/unknown/empty truth-table branch.
    cases = [
        ('4 IN (SELECT v FROM choices)', True),
        ('7 IN (SELECT v FROM choices)', None),
        ('7 IN (SELECT v FROM choices WHERE v IS NOT NULL)', False),
        ('NULL IN (SELECT v FROM choices)', None),
        ('NULL IN (SELECT v FROM choices WHERE v<0)', False),
        ('4 NOT IN (SELECT v FROM choices)', False),
        ('7 NOT IN (SELECT v FROM choices)', None),
        ('7 NOT IN (SELECT v FROM choices WHERE v IS NOT NULL)', True),
        ('NULL NOT IN (SELECT v FROM choices)', None),
        ('NULL NOT IN (SELECT v FROM choices WHERE v<0)', True),
        ('7 > ANY (SELECT v FROM choices)', True),
        ('7 > ALL (SELECT v FROM choices)', False),
        ('9 >= ANY (SELECT v FROM choices)', True),
        ('4 <= ALL (SELECT v FROM choices WHERE v IS NOT NULL)', True),
        ('4 = ANY (SELECT v FROM choices)', True),
        ('7 <> ALL (SELECT v FROM choices WHERE v IS NOT NULL)', True),
        ('7 < ANY (SELECT v FROM choices)', True),
        ('12 < ANY (SELECT v FROM choices)', None),
        ('12 < ANY (SELECT v FROM choices WHERE v IS NOT NULL)', False),
        ('NULL < ANY (SELECT v FROM choices WHERE v<0)', False),
        ('7 < ALL (SELECT v FROM choices)', False),
        ('2 < ALL (SELECT v FROM choices)', None),
        ('2 < ALL (SELECT v FROM choices WHERE v IS NOT NULL)', True),
        ('NULL < ALL (SELECT v FROM choices WHERE v<0)', True),
        ('NULL = ANY (SELECT v FROM choices)', None),
        ('NULL = ALL (SELECT v FROM choices)', None),
    ]
    setup.update({str(i): ('Q', 'SELECT '+sql) for i,(sql,_) in enumerate(cases)})
    result = schema_run(subqueries_client, setup)
    for i,(sql, expected) in enumerate(cases):
        assert rows_equal(scalar_rows(result[str(i)]), [[expected]], ordered=False), (sql,result[str(i)])


def test_correlation_shadowing_and_derived_columns(subqueries_client):
    setup = ['CREATE TABLE parents (id INTEGER)',
             'CREATE TABLE children (id INTEGER, parent_id INTEGER, amount INTEGER)',
             'INSERT INTO parents VALUES (2),(5),(8)',
             'INSERT INTO children VALUES (21,2,7),(22,2,11),(51,5,3)']
    queries = {
        'exists_wrapped': ('SELECT p.id, (SELECT EXISTS (SELECT c.id FROM children c WHERE c.parent_id=p.id)) FROM parents p', [[2,True],[5,True],[8,False]]),
        'exists_filter': ('SELECT p.id FROM parents p WHERE EXISTS (SELECT c.id FROM children c WHERE c.parent_id=p.id)', [[2],[5]]),
        'correlated': ('SELECT p.id AS parent, (SELECT SUM(c.amount) FROM children c WHERE c.parent_id=p.id) AS total FROM parents p', [[2,18.0],[5,3.0],[8,None]]),
        'qualified': ('SELECT p.id AS parent, (SELECT p.id FROM children c LIMIT 1) AS outer_value FROM parents p', [[2,2],[5,5],[8,8]]),
        'shadow': ('SELECT p.id AS parent, (SELECT MAX(p.id) FROM children p) AS local_value FROM parents p', [[2,51],[5,51],[8,51]]),
        'local_table': ('SELECT parents.id AS parent, (SELECT MAX(parents.id) FROM children parents) AS local_value FROM parents', [[2,51],[5,51],[8,51]]),
        'derived': ('SELECT d.owner,d.subtotal FROM (SELECT parent_id AS owner,SUM(amount) AS subtotal FROM children GROUP BY parent_id) d WHERE d.subtotal>5', [[2,18.0]]),
    }
    result = schema_run(subqueries_client, {
        **{str(i): ('E',sql) for i,sql in enumerate(setup)},
        **{name: ('Q',sql) for name,(sql,_) in queries.items()},
    })
    for name, (sql, expected) in queries.items():
        assert aggregate_rows_equal(scalar_rows(result[name]), expected,
                                    numeric_columns=(1,) if name in ('correlated','derived') else (),
                                    ordered=False), (name,result[name])
    assert selection_columns(subqueries_client, setup, queries['derived'][0]) == ['owner','subtotal']
    assert selection_columns(subqueries_client, setup, queries['correlated'][0]) == ['parent','total']


def test_cte_scope_names_and_writes(subqueries_client):
    named = 'WITH first(x,y) AS (SELECT id,amount FROM source), second AS (SELECT x,y+2 AS raised FROM first WHERE x<>3) '
    result = schema_run(subqueries_client, {
        'source': ('E', 'CREATE TABLE source (id INTEGER, amount INTEGER)'),
        'target': ('E', 'CREATE TABLE target (id INTEGER, amount INTEGER)'),
        'seed': ('E', 'INSERT INTO source VALUES (1,10),(2,20),(3,30)'),
        'read': ('Q', named+'SELECT x,raised FROM second'),
        'insert': ('E', named+'INSERT INTO target SELECT x,raised FROM second'),
        'inserted': ('Q', 'SELECT id,amount FROM target'),
        'update': ('E', 'WITH selected AS (SELECT id FROM source WHERE amount=20) UPDATE target SET amount=amount+5 WHERE id IN (SELECT id FROM selected)'),
        'updated': ('Q', 'SELECT id,amount FROM target'),
        'delete': ('E', 'WITH selected AS (SELECT id FROM source WHERE amount=10) DELETE FROM target WHERE id IN (SELECT id FROM selected)'),
        'deleted': ('Q', 'SELECT id,amount FROM target'),
        'scope_read': ('X', 'SELECT * FROM second'),
        'scope_write': ('X', 'SELECT * FROM selected'),
    })
    for name, expected in {'read': [[1,12],[2,22]], 'inserted': [[1,12],[2,22]],
                           'updated': [[1,12],[2,27]], 'deleted': [[2,27]]}.items():
        assert rows_equal(scalar_rows(result[name]), expected, ordered=False), result[name]
    for name, count in [('insert',2),('update',1),('delete',1)]:
        assert result[name]['affected'] == count, result[name]


def test_recursive_relations_and_invalid_definitions(subqueries_client):
    result = schema_run(subqueries_client, {
        'edges': ('E', 'CREATE TABLE edges (parent INTEGER, child INTEGER)'),
        'seed': ('E', 'INSERT INTO edges VALUES (1,2),(1,3),(2,4),(3,4),(4,5)'),
        'branches': ('Q', 'WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM seq WHERE n<3 UNION ALL SELECT n+1 FROM seq WHERE n<3) SELECT n FROM seq'),
        'depth': ('Q', 'WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM seq WHERE n<10000) SELECT COUNT(*),MAX(n) FROM seq'),
        'numbers': ('Q', 'WITH RECURSIVE seq(n,total) AS (SELECT 1,2 UNION ALL SELECT n+1,total*2 FROM seq WHERE n<5) SELECT n,total FROM seq'),
        'tree': ('Q', 'WITH RECURSIVE paths(node,depth) AS (SELECT 1,0 UNION ALL SELECT e.child,p.depth+1 FROM paths p JOIN edges e ON e.parent=p.node) SELECT node,depth FROM paths'),
        'no_member': ('X', 'WITH RECURSIVE seq(n) AS (SELECT 1) SELECT n FROM seq'),
        'distinct': ('X', 'WITH RECURSIVE seq(n) AS (SELECT 1 UNION SELECT n+1 FROM seq WHERE n<3) SELECT n FROM seq'),
    })
    assert scalar_rows(result['depth']) == [[10000,10000]]
    assert rows_equal(scalar_rows(result['branches']), [[1],[2],[2],[3],[3],[3],[3]], ordered=False)
    assert rows_equal(scalar_rows(result['numbers']), [[1,2],[2,4],[3,8],[4,16],[5,32]], ordered=False)
    assert rows_equal(scalar_rows(result['tree']), [[1,0],[2,1],[3,1],[4,2],[4,2],[5,3],[5,3]], ordered=False)


def test_subquery_errors_propagate_through_reads_and_writes(subqueries_client):
    operations = [
        ('E', 'CREATE TABLE target (id INTEGER, amount INTEGER)', ()),
        ('E', 'INSERT INTO target VALUES (1,10),(2,20)', ()),
        ('Q', 'SELECT (SELECT amount FROM target WHERE id=1)', ()),
        ('Q', 'SELECT (SELECT amount FROM absent_source)', ()),
        ('Q', 'SELECT EXISTS (SELECT amount FROM absent_source)', ()),
        ('Q', 'SELECT id FROM target WHERE id IN (SELECT amount FROM absent_source)', ()),
        ('E', 'INSERT INTO target SELECT 3,(SELECT amount FROM absent_source)', ()),
        ('E', 'UPDATE target SET amount=(SELECT amount FROM absent_source)', ()),
        ('E', 'DELETE FROM target WHERE id IN (SELECT amount FROM absent_source)', ()),
        ('Q', 'SELECT id,amount FROM target', ()),
    ]
    observed = scalar_batch(subqueries_client, operations)
    assert 'affected' in observed[0], observed[0]
    assert observed[1] == {'affected': 2}
    assert scalar_rows(observed[2]) == [[10]]
    for operation, result in zip(operations[3:9], observed[3:9]):
        assert 'error' in result, (operation,result)
    assert rows_equal(scalar_rows(observed[9]), [[1,10],[2,20]], ordered=False)

    lazy = schema_run(subqueries_client, {
        'create': ('E', 'CREATE TABLE patterns (pattern TEXT)'),
        'insert': ('E', "INSERT INTO patterns VALUES ('[')"),
        'control': ('Q', 'SELECT (SELECT 1 FROM patterns)'),
        'failure': ('X', "SELECT (SELECT 1 FROM patterns WHERE 'word' REGEXP pattern)"),
    })
    assert scalar_rows(lazy['control']) == [[1]]
