# feature: F07
"""Foreign-key scenario setup; observations reuse the earlier SQL transport."""
from F02_helpers import scalar_rows
from _helpers import rows_equal


def fk_pair_setup(action, parent_key="code", update_action=None):
    update_action = action if update_action is None else update_action
    refs = (1, 2) if parent_key == "id" else (10, 20)
    return {
        'parent': ('E', 'CREATE TABLE p (id INTEGER PRIMARY KEY, code INTEGER UNIQUE, note TEXT)'),
        'child': ('E', f'CREATE TABLE c (id INTEGER PRIMARY KEY, ref INTEGER REFERENCES p({parent_key}) ON DELETE {action} ON UPDATE {update_action}, note TEXT)'),
        'parents': ('E', "INSERT INTO p VALUES (1,10,'a'),(2,20,'b'),(3,30,'c')"),
        'children': ('E', f"INSERT INTO c VALUES (11,{refs[0]},'x'),(12,{refs[0]},'y'),(13,{refs[1]},'z'),(14,NULL,'n')"),
    }


def fk_expect(observed, expected):
    for name, rows in expected.items():
        actual = scalar_rows(observed[name])
        assert rows_equal(actual, rows, ordered=True), (name, actual, rows)


def fk_chain_setup(first_action, last_action, operation="UPDATE"):
    parent_key = "id" if operation == "DELETE" else "code"
    child_refs = (1, 2) if operation == "DELETE" else (10, 20)
    grandchild_refs = (11, 12) if operation == "DELETE" else (10, 20)
    return {
        'parent': ('E', 'CREATE TABLE p (id INTEGER PRIMARY KEY, code INTEGER UNIQUE, note TEXT)'),
        'child': ('E', f'CREATE TABLE c (id INTEGER PRIMARY KEY, code INTEGER UNIQUE REFERENCES p({parent_key}) ON DELETE {first_action} ON UPDATE {first_action}, note TEXT)'),
        'grandchild': ('E', f'CREATE TABLE g (id INTEGER PRIMARY KEY, code INTEGER REFERENCES c({parent_key}) ON DELETE {last_action} ON UPDATE {last_action}, note TEXT)'),
        'parents': ('E', "INSERT INTO p VALUES (1,10,'a'),(2,20,'b')"),
        'children': ('E', f"INSERT INTO c VALUES (11,{child_refs[0]},'x'),(12,{child_refs[1]},'y')"),
        'grandchildren': ('E', f"INSERT INTO g VALUES (21,{grandchild_refs[0]},'u'),(22,{grandchild_refs[0]},'v'),(23,{grandchild_refs[1]},'w')"),
    }


def fk_chain_reads(prefix):
    return {f'{prefix}_{table}': ('Q', f'SELECT * FROM {table} ORDER BY id')
            for table in ('p', 'c', 'g')}
