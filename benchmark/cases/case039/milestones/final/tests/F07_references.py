# feature: F07
"""The six planned public SQL acceptance checks for referential integrity."""
import pytest
from F01_helpers import build_rust_client
from F02_helpers import SCALAR_CLIENT, scalar_rows
from F03_helpers import schema_run
from F07_helpers import fk_pair_setup, fk_expect, fk_chain_setup, fk_chain_reads


@pytest.fixture(scope='module')
def reference_client(tmp_path_factory):
    return build_rust_client(SCALAR_CLIENT, tmp_path_factory.mktemp('f07-rust'))


def test_declarations_validate_and_enforce(reference_client):
    for key in ('id', 'code'):
        r = schema_run(reference_client, {
            'p': ('E', 'CREATE TABLE p (id INTEGER PRIMARY KEY, code INTEGER UNIQUE, ordinary INTEGER)'),
            'rows': ('E', 'INSERT INTO p VALUES (1,10,100),(2,20,200)'),
            'c': ('E', f'CREATE TABLE c (id INTEGER PRIMARY KEY, ref INTEGER REFERENCES p({key}))'),
            'valid': ('E', f'INSERT INTO c VALUES (7,{1 if key == "id" else 10}),(8,NULL)'),
            'invalid': ('X', 'INSERT INTO c VALUES (9,404)'),
            'kept': ('Q', 'SELECT * FROM c ORDER BY id'),
            'move': ('E', f'UPDATE c SET ref={2 if key == "id" else 20} WHERE id=7'),
            'moved': ('Q', 'SELECT * FROM c ORDER BY id'),
        })
        fk_expect(r, {'kept': [[7,1 if key == 'id' else 10],[8,None]],
                      'moved': [[7,2 if key == 'id' else 20],[8,None]]})
    multiple = schema_run(reference_client, {
        'p': ('E', 'CREATE TABLE p (id INTEGER PRIMARY KEY)'),
        'pi': ('E', 'INSERT INTO p VALUES (3),(7)'),
        'c': ('E', 'CREATE TABLE c (id INTEGER PRIMARY KEY, a INTEGER REFERENCES p(id), b INTEGER REFERENCES p(id))'),
        'valid': ('E', 'INSERT INTO c VALUES (1,3,7)'),
        'bad_insert': ('X', 'INSERT INTO c VALUES (2,3,999)'),
        'bad_update': ('X', 'UPDATE c SET b=999 WHERE id=1'),
        'rows': ('Q', 'SELECT * FROM c'),
    })
    fk_expect(multiple, {'rows': [[1,3,7]]})
    r = schema_run(reference_client, {
        'p': ('E', 'CREATE TABLE p (id INTEGER PRIMARY KEY, code INTEGER UNIQUE, ordinary INTEGER)'),
        'baseline': ('E', 'INSERT INTO p VALUES (1,10,100)'),
        'absent_table': ('X', 'CREATE TABLE bad_table (ref INTEGER REFERENCES absent(id))'),
        'absent_column': ('X', 'CREATE TABLE bad_column (ref INTEGER REFERENCES p(absent))'),
        'nonunique': ('X', 'CREATE TABLE bad_key (ref INTEGER REFERENCES p(ordinary))'),
        'delete_null': ('X', 'CREATE TABLE bad_delete (ref INTEGER NOT NULL REFERENCES p(id) ON DELETE SET NULL)'),
        'update_null': ('X', 'CREATE TABLE bad_update (ref INTEGER NOT NULL REFERENCES p(id) ON UPDATE SET NULL)'),
        'kept': ('Q', 'SELECT * FROM p'),
    })
    fk_expect(r, {'kept': [[1,10,100]]})


def test_child_writes_follow_transaction_visibility(reference_client):
    r = schema_run(reference_client, {
        'p': ('E', 'CREATE TABLE p (id INTEGER PRIMARY KEY)'),
        'c': ('E', 'CREATE TABLE c (id INTEGER PRIMARY KEY, ref INTEGER REFERENCES p(id))'),
        'parents': ('E', 'INSERT INTO p VALUES (1),(2)'),
        'children': ('E', 'INSERT INTO c VALUES (11,1),(12,NULL)'),
        'initial': ('Q', 'SELECT * FROM c ORDER BY id'),
        'begin': ('E', 'BEGIN'),
        'new_parent': ('E', 'INSERT INTO p VALUES (3)'),
        'new_child': ('E', 'INSERT INTO c VALUES (13,3)'),
        'move': ('E', 'UPDATE c SET ref=3 WHERE id=11'),
        'missing_insert': ('X', 'INSERT INTO c VALUES (14,404)'),
        'missing_update': ('X', 'UPDATE c SET ref=404 WHERE id=11'),
        'after_reject': ('Q', 'SELECT * FROM c ORDER BY id'),
        'null_update': ('E', 'UPDATE c SET ref=NULL WHERE id=13'),
        'after_null': ('Q', 'SELECT * FROM c ORDER BY id'),
        'valid_update': ('E', 'UPDATE c SET ref=3 WHERE id=13'),
        'delete_parent': ('E', 'DELETE FROM p WHERE id=2'),
        'deleted_insert': ('X', 'INSERT INTO c VALUES (15,2)'),
        'deleted_update': ('X', 'UPDATE c SET ref=2 WHERE id=12'),
        'inside_p': ('Q', 'SELECT * FROM p ORDER BY id'),
        'inside_c': ('Q', 'SELECT * FROM c ORDER BY id'),
        'commit': ('E', 'COMMIT'),
        'outside_p': ('Q', 'SELECT * FROM p ORDER BY id'),
        'outside_c': ('Q', 'SELECT * FROM c ORDER BY id'),
    })
    fk_expect(r, {
        'initial': [[11,1],[12,None]],
        'after_reject': [[11,3],[12,None],[13,3]],
        'after_null': [[11,3],[12,None],[13,None]],
        'inside_p': [[1],[3]], 'outside_p': [[1],[3]],
        'inside_c': [[11,3],[12,None],[13,3]],
        'outside_c': [[11,3],[12,None],[13,3]],
    })


def test_all_parent_actions_and_primary_key_guard(reference_client):
    # Each action is required for both independently configurable operations.
    for action in ('RESTRICT', 'NO ACTION', 'CASCADE', 'SET NULL'):
        for operation in ('DELETE', 'UPDATE'):
            blocked = action in ('RESTRICT', 'NO ACTION')
            other_action = 'CASCADE' if blocked else 'RESTRICT'
            delete_action = action if operation == 'DELETE' else other_action
            update_action = action if operation == 'UPDATE' else other_action
            sql = 'DELETE FROM p WHERE id=1' if operation == 'DELETE' else 'UPDATE p SET code=15 WHERE id=1'
            r = schema_run(reference_client, {
                **fk_pair_setup(delete_action, "id" if operation == "DELETE" else "code", update_action),
                'before': ('Q', 'SELECT * FROM c ORDER BY id'),
                'change': ('X' if blocked else 'E', sql),
                'p_after': ('Q', 'SELECT * FROM p ORDER BY id'),
                'c_after': ('Q', 'SELECT * FROM c ORDER BY id'),
                # Unreferenced rows remain mutable, even under restriction.
                'unreferenced': ('E', 'UPDATE p SET code=35 WHERE id=3'),
                'unreferenced_delete': ('E', 'DELETE FROM p WHERE id=3'),
                'p_final': ('Q', 'SELECT * FROM p ORDER BY id'),
                'c_final': ('Q', 'SELECT * FROM c ORDER BY id'),
            })
            parents = [[1,10,'a'],[2,20,'b'],[3,30,'c']]
            refs = (1,2) if operation == 'DELETE' else (10,20)
            children = [[11,refs[0],'x'],[12,refs[0],'y'],[13,refs[1],'z'],[14,None,'n']]
            expected_p = parents if blocked else ([[2,20,'b'],[3,30,'c']] if operation == 'DELETE' else [[1,15,'a'],[2,20,'b'],[3,30,'c']])
            expected_c = children
            if action == 'SET NULL':
                expected_c = [[11,None,'x'],[12,None,'y'],[13,refs[1],'z'],[14,None,'n']]
            elif action == 'CASCADE':
                expected_c = children[2:] if operation == 'DELETE' else [[11,15,'x'],[12,15,'y'],[13,20,'z'],[14,None,'n']]
            fk_expect(r, {'before': children, 'p_after': expected_p, 'c_after': expected_c,
                          'p_final': [row for row in expected_p if row[0] != 3], 'c_final': expected_c})
    r = schema_run(reference_client, {
        'p': ('E', 'CREATE TABLE p (id INTEGER PRIMARY KEY)'),
        'c': ('E', 'CREATE TABLE c (id INTEGER PRIMARY KEY, ref INTEGER REFERENCES p(id) ON UPDATE CASCADE)'),
        'parent': ('E', 'INSERT INTO p VALUES (1),(2)'),
        'child': ('E', 'INSERT INTO c VALUES (11,1)'),
        'refused': ('X', 'UPDATE p SET id=3 WHERE id=1'),
        'p_after': ('Q', 'SELECT * FROM p ORDER BY id'),
        'c_after': ('Q', 'SELECT * FROM c ORDER BY id'),
    })
    fk_expect(r, {'p_after': [[1],[2]], 'c_after': [[11,1]]})


    many = schema_run(reference_client, {
        'p': ('E', 'CREATE TABLE p (id INTEGER PRIMARY KEY)'),
        'c1': ('E', 'CREATE TABLE c1 (id INTEGER PRIMARY KEY, ref INTEGER REFERENCES p(id) ON DELETE CASCADE)'),
        'c2': ('E', 'CREATE TABLE c2 (id INTEGER PRIMARY KEY, ref INTEGER REFERENCES p(id) ON DELETE CASCADE)'),
        'pi': ('E', 'INSERT INTO p VALUES (1)'),
        'i1': ('E', 'INSERT INTO c1 VALUES (10,1)'),
        'i2': ('E', 'INSERT INTO c2 VALUES (20,1)'),
        'delete': ('E', 'DELETE FROM p WHERE id=1'),
        'left': ('Q', 'SELECT * FROM c1'), 'right': ('Q', 'SELECT * FROM c2'),
    })
    fk_expect(many, {'left': [], 'right': []})

def test_recursive_actions_rollback_and_statement_atomicity(reference_client):
    for operation in ('DELETE', 'UPDATE'):
        initial = {'p': [[1,10,'a'],[2,20,'b']],
                   'c': [[11,1,'x'],[12,2,'y']] if operation == 'DELETE' else [[11,10,'x'],[12,20,'y']],
                   'g': [[21,11,'u'],[22,11,'v'],[23,12,'w']] if operation == 'DELETE' else [[21,10,'u'],[22,10,'v'],[23,20,'w']]}
        sql = 'DELETE FROM p WHERE id=1' if operation == 'DELETE' else 'UPDATE p SET code=15 WHERE id=1'
        r = schema_run(reference_client, {
            **fk_chain_setup('CASCADE', 'CASCADE', operation), **fk_chain_reads('before'),
            'begin': ('E', 'BEGIN'), 'change': ('E', sql), **fk_chain_reads('inside'),
            'rollback': ('E', 'ROLLBACK'), **fk_chain_reads('restored'),
            'again': ('E', sql), **fk_chain_reads('committed'),
        })
        for table, rows in initial.items():
            changed = [rows[-1]] if operation == 'DELETE' else [
                [row[0], 15 if row[1] == 10 else row[1], row[2]] for row in rows]
            fk_expect(r, {f'before_{table}': rows, f'inside_{table}': changed,
                          f'restored_{table}': rows, f'committed_{table}': changed})
        # A deep refusal must leave the current transaction intact before rollback.
        r = schema_run(reference_client, {
            **fk_chain_setup('CASCADE', 'RESTRICT', operation),
            'unblock_first': ('E', 'DELETE FROM g WHERE id IN (21,22)'),
            'begin': ('E', 'BEGIN'),
            'earlier_work': ('E', "UPDATE p SET note='kept' WHERE id=2"),
            'refused': ('X', 'DELETE FROM p' if operation == 'DELETE' else 'UPDATE p SET code=code+5'),
            **fk_chain_reads('inside'),
            'commit': ('E', 'COMMIT'), **fk_chain_reads('committed'),
        })
        for table, rows in initial.items():
            expected = [[1,10,'a'],[2,20,'kept']] if table == 'p' else ([rows[-1]] if table == 'g' else rows)
            fk_expect(r, {f'inside_{table}': expected, f'committed_{table}': expected})
    # Independent dependents and a recursive reference to a non-primary unique key.
    r = schema_run(reference_client, {
        'p': ('E', 'CREATE TABLE p (id INTEGER PRIMARY KEY)'),
        'c': ('E', 'CREATE TABLE c (id INTEGER PRIMARY KEY, ref INTEGER REFERENCES p(id) ON DELETE CASCADE, code INTEGER UNIQUE)'),
        'other': ('E', 'CREATE TABLE other (id INTEGER PRIMARY KEY, ref INTEGER REFERENCES p(id) ON DELETE CASCADE)'),
        'g': ('E', 'CREATE TABLE g (id INTEGER PRIMARY KEY, ref INTEGER REFERENCES c(code) ON DELETE CASCADE)'),
        'pi': ('E', 'INSERT INTO p VALUES (3),(7)'),
        'ci': ('E', 'INSERT INTO c VALUES (11,3,101),(12,7,102)'),
        'oi': ('E', 'INSERT INTO other VALUES (21,3),(22,7)'),
        'gi': ('E', 'INSERT INTO g VALUES (31,101),(32,102)'),
        'begin': ('E', 'BEGIN'),
        'delete': ('E', 'DELETE FROM p WHERE id=3'),
        'c_inside': ('Q', 'SELECT * FROM c ORDER BY id'),
        'other_inside': ('Q', 'SELECT * FROM other ORDER BY id'),
        'g_inside': ('Q', 'SELECT * FROM g ORDER BY id'),
        'rollback': ('E', 'ROLLBACK'),
        'c_restored': ('Q', 'SELECT * FROM c ORDER BY id'),
        'other_restored': ('Q', 'SELECT * FROM other ORDER BY id'),
        'g_restored': ('Q', 'SELECT * FROM g ORDER BY id'),
    })
    fk_expect(r, {'c_inside': [[12,7,102]], 'other_inside': [[22,7]], 'g_inside': [[32,102]],
                  'c_restored': [[11,3,101],[12,7,102]], 'other_restored': [[21,3],[22,7]],
                  'g_restored': [[31,101],[32,102]]})
    # Nullification is transactional, and a deeper restriction still applies.
    r = schema_run(reference_client, {
        **fk_pair_setup('SET NULL', 'id'), 'begin': ('E', 'BEGIN'),
        'delete': ('E', 'DELETE FROM p WHERE id=1'),
        'inside': ('Q', 'SELECT * FROM c ORDER BY id'),
        'rollback': ('E', 'ROLLBACK'),
        'parent_restored': ('Q', 'SELECT * FROM p ORDER BY id'),
        'child_restored': ('Q', 'SELECT * FROM c ORDER BY id'),
    })
    fk_expect(r, {'inside': [[11,None,'x'],[12,None,'y'],[13,2,'z'],[14,None,'n']],
                  'parent_restored': [[1,10,'a'],[2,20,'b'],[3,30,'c']],
                  'child_restored': [[11,1,'x'],[12,1,'y'],[13,2,'z'],[14,None,'n']]})
    r = schema_run(reference_client, {
        **fk_chain_setup('SET NULL', 'RESTRICT'), 'begin': ('E', 'BEGIN'),
        'refused': ('X', 'UPDATE p SET code=15 WHERE id=1'), **fk_chain_reads('inside'),
        'commit': ('E', 'COMMIT'), **fk_chain_reads('committed'),
    })
    for table, rows in initial.items():
        fk_expect(r, {f'inside_{table}': rows, f'committed_{table}': rows})


def test_parent_table_removal_protection_and_cleanup(reference_client):
    for action in ('RESTRICT', 'NO ACTION', 'CASCADE', 'SET NULL'):
        r = schema_run(reference_client, {
            **fk_pair_setup(action),
            'drop_refused': ('X', 'DROP TABLE p'),
            'after_drop_p': ('Q', 'SELECT * FROM p ORDER BY id'),
            'after_drop_c': ('Q', 'SELECT * FROM c ORDER BY id'),
            'truncate_refused': ('X', 'TRUNCATE TABLE p'),
            'after_truncate_p': ('Q', 'SELECT * FROM p ORDER BY id'),
            'after_truncate_c': ('Q', 'SELECT * FROM c ORDER BY id'),
            'begin': ('E', 'BEGIN'),
            'delete_children': ('E', 'DELETE FROM c WHERE ref IS NOT NULL'),
            'remaining': ('Q', 'SELECT * FROM c ORDER BY id'),
            'drop_allowed': ('E', 'DROP TABLE p'),
            'commit': ('E', 'COMMIT'),
            'parent_absent': ('X', 'SELECT * FROM p'),
            'orphan_insert': ('E', "INSERT INTO c VALUES (15,999,'new')"),
            'orphan_update': ('E', 'UPDATE c SET ref=888 WHERE id=14'),
            'surviving': ('Q', 'SELECT * FROM c ORDER BY id'),
        })
        fk_expect(r, {
            'after_drop_p': [[1,10,'a'],[2,20,'b'],[3,30,'c']],
            'after_truncate_p': [[1,10,'a'],[2,20,'b'],[3,30,'c']],
            'after_drop_c': [[11,10,'x'],[12,10,'y'],[13,20,'z'],[14,None,'n']],
            'after_truncate_c': [[11,10,'x'],[12,10,'y'],[13,20,'z'],[14,None,'n']],
            'remaining': [[14,None,'n']], 'surviving': [[14,888,'n'],[15,999,'new']],
        })
    r = schema_run(reference_client, {
        **fk_pair_setup('CASCADE'),
        'clear': ('E', 'DELETE FROM c WHERE ref IS NOT NULL'),
        'truncate_allowed': ('E', 'TRUNCATE TABLE p'),
        'empty_parent': ('Q', 'SELECT * FROM p ORDER BY id'),
        'null_child': ('Q', 'SELECT * FROM c ORDER BY id'),
        'reference_retained': ('X', "INSERT INTO c VALUES (15,10,'bad')"),
        'repopulate': ('E', "INSERT INTO p VALUES (4,40,'d')"),
        'valid_child': ('E', "INSERT INTO c VALUES (15,40,'good')"),
        'after': ('Q', 'SELECT * FROM c ORDER BY id'),
    })
    fk_expect(r, {'empty_parent': [], 'null_child': [[14,None,'n']],
                  'after': [[14,None,'n'],[15,40,'good']]})


def test_type_changes_reject_both_sides_without_changes(reference_client):
    r = schema_run(reference_client, {
        **fk_pair_setup('RESTRICT'),
        'ordinary': ('E', 'CREATE TABLE ordinary (v INTEGER)'),
        'ordinary_insert': ('E', 'INSERT INTO ordinary VALUES (17)'),
        'ordinary_change': ('E', 'ALTER TABLE ordinary MODIFY COLUMN v TEXT'),
        # The parent column is UNIQUE, not a primary key: only the FK guards it.
        'parent_refused': ('X', 'ALTER TABLE p MODIFY COLUMN code TEXT'),
        'parent_schema': ('Q', 'DESCRIBE p'),
        'parent_data': ('Q', 'SELECT * FROM p ORDER BY id'),
        'child_data_before': ('Q', 'SELECT * FROM c ORDER BY id'),
        'child_refused': ('X', 'ALTER TABLE c MODIFY COLUMN ref TEXT'),
        'child_schema': ('Q', 'DESCRIBE c'),
        'parent_data_after': ('Q', 'SELECT * FROM p ORDER BY id'),
        'child_data': ('Q', 'SELECT * FROM c ORDER BY id'),
        'still_rejects': ('X', "INSERT INTO c VALUES (15,404,'bad')"),
        'still_restricts': ('X', 'UPDATE p SET code=15 WHERE id=1'),
        'still_accepts': ('E', "INSERT INTO c VALUES (15,30,'good')"),
        'final': ('Q', 'SELECT * FROM c ORDER BY id'),
    })
    parents = [[1,10,'a'],[2,20,'b'],[3,30,'c']]
    children = [[11,10,'x'],[12,10,'y'],[13,20,'z'],[14,None,'n']]
    fk_expect(r, {'parent_data': parents, 'parent_data_after': parents,
                  'child_data_before': children, 'child_data': children,
                  'final': children + [[15,30,'good']]})
    assert [row[:3] for row in scalar_rows(r['parent_schema'])] == [
        ['id','Integer','NO'],['code','Integer','YES'],['note','Text','YES']]
    assert [row[:3] for row in scalar_rows(r['child_schema'])] == [
        ['id','Integer','NO'],['ref','Integer','YES'],['note','Text','YES']]

    empty = schema_run(reference_client, {
        'p': ('E', 'CREATE TABLE p (id INTEGER PRIMARY KEY, code INTEGER UNIQUE)'),
        'c': ('E', 'CREATE TABLE c (ref INTEGER REFERENCES p(code))'),
        'parent_before': ('Q', 'DESCRIBE p'), 'child_before': ('Q', 'DESCRIBE c'),
        'parent': ('X', 'ALTER TABLE p MODIFY COLUMN code TEXT'),
        'child': ('X', 'ALTER TABLE c MODIFY COLUMN ref TEXT'),
        'parent_after': ('Q', 'DESCRIBE p'), 'child_after': ('Q', 'DESCRIBE c'),
    })
    assert scalar_rows(empty['parent_before']) == scalar_rows(empty['parent_after'])
    assert scalar_rows(empty['child_before']) == scalar_rows(empty['child_after'])
