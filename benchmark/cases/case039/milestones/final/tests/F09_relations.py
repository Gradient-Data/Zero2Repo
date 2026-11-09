# feature: F09
"""Public SQL acceptance for joins and complete-row set operations."""
import pytest
from _helpers import rows_equal
from F01_helpers import build_rust_client
from F02_helpers import scalar_rows
from F03_helpers import schema_run
from F04_helpers import SELECTION_CLIENT, selection_columns, selection_result


@pytest.fixture(scope='module')
def relations_client(tmp_path_factory):
    return build_rust_client(SELECTION_CLIENT, tmp_path_factory.mktemp('f09-rust'))


def test_join_kinds_nulls_and_empty_inputs(relations_client):
    setup = {
        'left_create': ('E', 'CREATE TABLE l (k INTEGER, v TEXT)'),
        'right_create': ('E', 'CREATE TABLE r (k INTEGER, v TEXT)'),
        'left_insert': ('E', "INSERT INTO l VALUES (1,'a'),(1,'b'),(2,'c'),(NULL,'n')"),
        'right_insert': ('E', "INSERT INTO r VALUES (1,'x'),(1,'y'),(3,'z'),(NULL,'m')"),
    }
    matched = [[1,a,1,b] for a in ['a','b'] for b in ['x','y']]
    left_only = [[2,'c',None,None],[None,'n',None,None]]
    right_only = [[None,None,3,'z'],[None,None,None,'m']]
    expectations = {'INNER': matched, 'LEFT': matched+left_only,
                    'RIGHT': matched+right_only, 'FULL OUTER': matched+left_only+right_only,
                    'CROSS': [[*a,*b] for a in [[1,'a'],[1,'b'],[2,'c'],[None,'n']]
                              for b in [[1,'x'],[1,'y'],[3,'z'],[None,'m']]]}
    for kind in expectations:
        setup[kind] = ('Q', f'SELECT l.k,l.v,r.k,r.v FROM l {kind} JOIN r' +
                       ('' if kind == 'CROSS' else ' ON l.k=r.k'))
    result = schema_run(relations_client, setup)
    for kind, expected in expectations.items():
        assert rows_equal(scalar_rows(result[kind]), expected, ordered=False), (kind,result[kind])
    for empty in ['l','r']:
        actions = dict(list(setup.items())[:4])
        actions['empty'] = ('E', f'DELETE FROM {empty}')
        actions.update({kind: setup[kind] for kind in expectations})
        result = schema_run(relations_client, actions)
        preserved = ([[None,None,*row] for row in [[1,'x'],[1,'y'],[3,'z'],[None,'m']]]
                     if empty == 'l' else
                     [[*row,None,None] for row in [[1,'a'],[1,'b'],[2,'c'],[None,'n']]])
        for kind in expectations:
            expected = preserved if kind in ('FULL OUTER', 'RIGHT' if empty == 'l' else 'LEFT') else []
            assert rows_equal(scalar_rows(result[kind]), expected, ordered=False), (empty,kind,result[kind])


def test_composite_non_equality_self_and_chained_joins(relations_client):
    result = schema_run(relations_client, {
        'l': ('E','CREATE TABLE l (id INTEGER, k INTEGER, amount INTEGER)'),
        'r': ('E','CREATE TABLE r (id INTEGER, k INTEGER, amount INTEGER)'),
        't': ('E','CREATE TABLE t (rid INTEGER, label TEXT)'),
        'li': ('E','INSERT INTO l VALUES (1,7,2),(2,7,5),(3,8,4)'),
        'ri': ('E','INSERT INTO r VALUES (11,7,3),(12,7,6),(13,8,1)'),
        'ti': ('E',"INSERT INTO t VALUES (11,'first'),(12,'second'),(12,'again'),(99,'orphan')"),
        'composite': ('Q','SELECT l.id,r.id FROM l JOIN r ON l.k=r.k AND l.amount<r.amount'),
        'left_residual': ('Q','SELECT l.id,r.id FROM l LEFT JOIN r ON l.k=r.k AND l.amount<r.amount'),
        'right_residual': ('Q','SELECT l.id,r.id FROM l RIGHT JOIN r ON l.k=r.k AND l.amount<r.amount'),
        'full_residual': ('Q','SELECT l.id,r.id FROM l FULL OUTER JOIN r ON l.k=r.k AND l.amount<r.amount'),
        'non_equality': ('Q','SELECT l.id,r.id FROM l JOIN r ON l.amount<r.amount'),
        'self': ('Q','SELECT a.id,b.id FROM l a JOIN l b ON a.k=b.k AND a.id<b.id'),
        'chain': ('Q','SELECT l.id,r.id,t.label FROM l JOIN r ON l.k=r.k AND l.amount<r.amount JOIN t ON r.id=t.rid'),
        'missing_left': ('X','SELECT l.id FROM l JOIN r ON l.absent=r.k'),
        'missing_right': ('X','SELECT l.id FROM l JOIN r ON l.k=r.absent'),
    })
    expected = {
        'composite': [[1,11],[1,12],[2,12]],
        'left_residual': [[1,11],[1,12],[2,12],[3,None]],
        'right_residual': [[1,11],[1,12],[2,12],[None,13]],
        'full_residual': [[1,11],[1,12],[2,12],[3,None],[None,13]],
        'non_equality': [[1,11],[1,12],[2,12],[3,12]],
        'self': [[1,2]],
        'chain': [[1,11,'first'],[1,12,'second'],[1,12,'again'],[2,12,'second'],[2,12,'again']],
    }
    for name, rows in expected.items():
        assert rows_equal(scalar_rows(result[name]), rows, ordered=False), (name,result[name])


def test_using_and_natural_shared_columns(relations_client):
    setup = ['CREATE TABLE l (k INTEGER, part TEXT, lv TEXT)',
             'CREATE TABLE r (k INTEGER, part TEXT, rv TEXT)',
             "INSERT INTO l VALUES (1,'a','L1'),(1,'b','L2'),(2,'c','L3')",
             "INSERT INTO r VALUES (1,'a','R1'),(1,'c','R2'),(3,'d','R3')"]
    matched = [[1,'a','L1','R1']]
    left_only = [[1,'b','L2',None],[2,'c','L3',None]]
    # Only the nonshared values are specified for right-only rows.
    right_only = [[None,None,None,'R2'],[None,None,None,'R3']]
    cases = {
        'JOIN r USING (k,part)': matched,
        'NATURAL JOIN r': matched,
        'LEFT JOIN r USING (k,part)': matched+left_only,
        'RIGHT JOIN r USING (k,part)': matched+right_only,
        'FULL OUTER JOIN r USING (k,part)': matched+left_only+right_only,
    }
    for clause, expected in cases.items():
        query = 'SELECT * FROM l ' + clause
        result = selection_result(relations_client, setup, query)
        columns = result['columns']
        assert sorted(columns) == ['k','l.lv','part','r.rv'], columns
        # Column positions and cells belong to the very same query result.
        rows = [[row[columns.index(name)] for name in ['k','part','l.lv','r.rv']]
                for row in scalar_rows(result)]
        assert rows_equal([row[2:] for row in rows], [row[2:] for row in expected],
                          ordered=False), (clause, rows)
        assert rows_equal([row for row in rows if row[2] is not None],
                          [row for row in expected if row[2] is not None],
                          ordered=False), (clause, rows)


def test_set_and_multiset_complete_rows(relations_client):
    setup = {
        'l': ('E','CREATE TABLE l (k INTEGER, v TEXT)'),
        'r': ('E','CREATE TABLE r (k INTEGER, v TEXT)'),
        'li': ('E',"INSERT INTO l VALUES (1,'a'),(1,'a'),(1,'a'),(1,'b'),(2,NULL),(2,NULL),(NULL,'n'),(8,'left'),(8,'left')"),
        'ri': ('E',"INSERT INTO r VALUES (1,'a'),(1,'a'),(1,'c'),(2,NULL),(NULL,'n'),(NULL,'n'),(9,'right')"),
    }
    a,b,c,n,z,left,right = [1,'a'],[1,'b'],[1,'c'],[2,None],[None,'n'],[8,'left'],[9,'right']
    expected = {
        'UNION': [a,b,c,n,z,left,right],
        'UNION ALL': [a]*5+[b,c]+[n]*3+[z]*3+[left,left,right],
        'INTERSECT': [a,n,z],
        'INTERSECT ALL': [a,a,n,z],
        'EXCEPT': [b,left],
        'EXCEPT ALL': [a,b,n,left,left],
    }
    for op in expected:
        setup[op] = ('Q', f'SELECT k,v FROM l {op} SELECT k,v FROM r')
    result = schema_run(relations_client, setup)
    for op, rows in expected.items():
        assert rows_equal(scalar_rows(result[op]), rows, ordered=False), (op,result[op])


def test_combined_order_pagination_names_and_width_error(relations_client):
    setup = ['CREATE TABLE l (k INTEGER, v TEXT)', 'CREATE TABLE r (k INTEGER, v TEXT)',
             "INSERT INTO l VALUES (9,'i'),(2,'b'),(7,'g')",
             "INSERT INTO r VALUES (1,'a'),(8,'h'),(4,'d')"]
    union = 'SELECT k AS item,v AS label FROM l UNION ALL SELECT k AS other,v AS text FROM r'
    query = union + ' ORDER BY item DESC LIMIT 3 OFFSET 2'
    assert selection_columns(relations_client, setup, query) == ['item','label']
    result = schema_run(relations_client, {
        **{str(i): ('E',sql) for i,sql in enumerate(setup)},
        'page': ('Q',query),
        'ascending': ('Q',union+' ORDER BY item LIMIT 2 OFFSET 1'),
        'offset': ('Q',union+' ORDER BY item OFFSET 4'),
        'chain': ('Q',union+" UNION ALL SELECT 12,'last' ORDER BY item"),
        **{'wide_'+op: ('X',f'SELECT k FROM l {op} SELECT k,v FROM r')
           for op in ['UNION','UNION ALL','INTERSECT','INTERSECT ALL','EXCEPT','EXCEPT ALL']},
        **{op: ('X',f'SELECT k,v FROM l {op} SELECT k FROM r')
           for op in ['UNION','UNION ALL','INTERSECT','INTERSECT ALL','EXCEPT','EXCEPT ALL']},
    })
    assert rows_equal(scalar_rows(result['page']), [[7,'g'],[4,'d'],[2,'b']], ordered=True)
    assert rows_equal(scalar_rows(result['ascending']), [[2,'b'],[4,'d']], ordered=True)
    assert rows_equal(scalar_rows(result['offset']), [[8,'h'],[9,'i']], ordered=True)
    assert rows_equal(scalar_rows(result['chain']),
                      [[1,'a'],[2,'b'],[4,'d'],[7,'g'],[8,'h'],[9,'i'],[12,'last']], ordered=True)
