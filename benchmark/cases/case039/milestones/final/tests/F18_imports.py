# feature: F18
"""The four planned bulk file import acceptance checks through public Rust SQL."""
import json
from F02_helpers import utc_instant, scalar_batch
from F03_helpers import schema_run
from F07_helpers import fk_expect
from F18_helpers import (import_client, import_file, copy_statement, import_rows,
                         IMPORT_SCHEMA, IMPORT_READ, import_document, import_constraint_state)


def test_csv_mapping_options_quoted_contents_and_typed_rows(import_client, tmp_path):
    header = import_file(tmp_path, 'header.csv',
        'name|v|id|score|enabled|amount|stamp|doc\n'
        '"雪|hello\n""quoted"""|[1,-2,0.5]|11|1.25|true|17|2024-02-29T03:04:05Z|"{""k"":[1,true]}"\n'
        'plain|[0,4,-1]|12|-2.5|false|MISSING|2023-11-02T12:00:00Z|[2,3]\n')
    positional = import_file(tmp_path, 'positional.csv',
        '21,"comma,inside",8,3.5,true,2024-01-02T00:00:00Z,"{""x"":2}","[2,0,-4]"\n'
        '22,"  last  ",-7,0.5,false,2024-01-03T00:00:00Z,[],"[0,0,1]"\n')
    selected = import_file(tmp_path, 'selected.csv', '"chosen, first",24\nsecond,25\n')
    r = schema_run(import_client, {
        'create': ('E', IMPORT_SCHEMA),
        'header': ('E', copy_statement('items', header, "FORMAT CSV, HEADER true, DELIMITER '|', NULL 'MISSING'")),
        'position': ('E', copy_statement('items', positional, 'FORMAT CSV, HEADER false')),
        'selected': ('E', copy_statement('items', selected, 'FORMAT CSV, HEADER false', '(name,id)')),
        'rows': ('Q', IMPORT_READ),
    })
    for name in ('header', 'position', 'selected'):
        assert r[name]['affected'] == 2, (name, r[name])
    import_rows(r['rows'], [
        [11, '雪|hello\n"quoted"', 17, 1.25, True, utc_instant('2024-02-29T03:04:05Z'), {'k':[1,True]}, [1,-2,.5]],
        [12, 'plain', None, -2.5, False, utc_instant('2023-11-02T12:00:00Z'), [2,3], [0,4,-1]],
        [21, 'comma,inside', 8, 3.5, True, utc_instant('2024-01-02T00:00:00Z'), {'x':2}, [2,0,-4]],
        [22, '  last  ', -7, .5, False, utc_instant('2024-01-03T00:00:00Z'), [], [0,0,1]],
        [24, 'chosen, first', 23, None, None, None, None, None],
        [25, 'second', 23, None, None, None, None, None],
    ])


def test_json_array_lines_keys_defaults_and_selected_columns(import_client, tmp_path):
    array = import_file(tmp_path, 'array.json', json.dumps([
        {'ID':31, 'NaMe':'comma, [x]', 'amount':'41', 'score':2.5, 'enabled':True,
         'stamp':'2024-02-29T03:04:05Z', 'doc':{'k':[1,True]}, 'v':[1,-2,.5], 'ignored':{}},
        {'id':32, 'score':-1.25, 'enabled':False, 'v':[0,4,-1]},
        {'id':33, 'name':'', 'amount':None, 'doc':[]},
    ]))
    lines = import_file(tmp_path, 'lines.jsonl', '\n'.join(json.dumps(row) for row in [
        {'iD':41, 'NAME':'line\nbreak', 'amount':7, 'doc':{'nested':{'x':'a"b'}}, 'v':[2,0,-4]},
        {'id':42, 'name':'last', 'extra':[1,2]},
    ]) + '\n')
    selected = import_file(tmp_path, 'selected.json', json.dumps([
        {'ID':51, 'NAME':'selected', 'amount':99, 'score':8.5, 'extra':True},
        {'id':52, 'amount':11, 'enabled':True},
    ]))
    r = schema_run(import_client, {
        'create': ('E', IMPORT_SCHEMA),
        'defaults': ('E', "CREATE TABLE defaults (id INTEGER, note TEXT DEFAULT 'unprovided')"),
        'default_import': ('E', copy_statement('defaults', array, 'FORMAT JSON')),
        'default_rows': ('Q', 'SELECT id,note FROM defaults ORDER BY id'),
        'array': ('E', copy_statement('items', array, 'FORMAT JSON')),
        'lines': ('E', copy_statement('items', lines, 'FORMAT JSON')),
        'selected': ('E', copy_statement('items', selected, 'FORMAT JSON', '(name,id)')),
        'rows': ('Q', IMPORT_READ),
    })
    assert r['default_import']['affected'] == 3
    fk_expect(r, {'default_rows': [[31,'unprovided'],[32,'unprovided'],[33,'unprovided']]})
    for name, count in [('array',3), ('lines',2), ('selected',2)]:
        assert r[name]['affected'] == count, (name, r[name])
    import_rows(r['rows'], [
        [31, 'comma, [x]', 41, 2.5, True, utc_instant('2024-02-29T03:04:05Z'), {'k':[1,True]}, [1,-2,.5]],
        [32, None, 23, -1.25, False, None, None, [0,4,-1]],
        [33, '', None, None, None, None, [], None],
        [41, 'line\nbreak', 7, None, None, None, {'nested':{'x':'a"b'}}, [2,0,-4]],
        [42, 'last', 23, None, None, None, None, None],
        [51, 'selected', 23, None, None, None, None, None],
        [52, None, 23, None, None, None, None, None],
    ])


def test_import_failures_are_atomic_and_preserve_constraints(import_client, tmp_path):
    # Each rejected stream begins with a valid row, so partial insertion is visible.
    # Separate failures exercise conversion, dimensions, and each integrity rule.
    schema = ('CREATE TABLE child(id INTEGER PRIMARY KEY, code INTEGER UNIQUE, '
              'qty INTEGER CHECK(qty>0), label TEXT NOT NULL, '
              'ref INTEGER REFERENCES parent(id), v VECTOR(3))')
    baseline = [1,10,5,'kept',7,'[1,2,3]']
    valid = [2,20,6,'new',7,'[2,0,-1]']
    cases = [
        ('primary', [1,30,8,'bad',7,'[1,2,3]']),
        ('unique', [3,10,8,'bad',7,'[1,2,3]']),
        ('primary_in_batch', [2,30,8,'bad',7,'[1,2,3]']),
        ('unique_in_batch', [3,20,8,'bad',7,'[1,2,3]']),
        ('check', [3,30,-1,'bad',7,'[1,2,3]']),
        ('not_null', [3,30,8,None,7,'[1,2,3]']),
        ('foreign_key', [3,30,8,'bad',999,'[1,2,3]']),
        ('convert', [3,30,'not-an-integer','bad',7,'[1,2,3]']),
        ('short_vector', [3,30,8,'bad',7,'[1,2]']),
        ('long_vector', [3,30,8,'bad',7,'[1,2,3,4]']),
    ]
    keys = ('id','code','qty','label','ref','v')
    for fmt in ('CSV', 'JSON'):
        options = f'FORMAT {fmt}' + (', HEADER false' if fmt == 'CSV' else '')
        good = import_file(tmp_path, f'good-{fmt}', import_document(fmt, keys, [baseline]))
        attempts = [(name, import_file(tmp_path, f'{name}-{fmt}', import_document(fmt, keys, [valid, bad])))
                    for name, bad in cases]
        if fmt == 'CSV':
            attempts.append(('field_count', import_file(tmp_path, 'short.csv', import_document(fmt, keys, [valid])+'3,30\n')))
        else:
            attempts.append(('malformed', import_file(tmp_path, 'broken.jsonl', import_document(fmt, keys, [valid])+'{"id":3,"qty":oops}\n')))
        missing = tmp_path / f'absent-{fmt}'
        inaccessible = tmp_path / f'unopenable-{fmt}'
        inaccessible.symlink_to(inaccessible.name)
        attempts += [('missing',missing), ('unopenable',inaccessible)]
        actions = {
            'parent': ('E', 'CREATE TABLE parent(id INTEGER PRIMARY KEY)'),
            'parent_row': ('E', 'INSERT INTO parent VALUES(7)'),
            'child': ('E', schema),
            'baseline': ('E', copy_statement('child', good, options)),
            'before': ('Q', 'SELECT id,code,qty,label,ref,VEC_TO_TEXT(v) FROM child ORDER BY id'),
        }
        if fmt == 'CSV':
            short = import_file(tmp_path, 'uniform-short.csv', '3,30,8,short,7\n4,40,9,short,7\n')
            attempts.append(('uniform_short', short))
        for name, path in attempts:
            actions[name] = ('X', copy_statement('child', path, options))
            actions[name+'_state'] = ('Q', 'SELECT id,code,qty,label,ref,VEC_TO_TEXT(v) FROM child ORDER BY id')
        if fmt == 'JSON':
            selected_bad = import_file(tmp_path, 'selected-check.jsonl',
                                       import_document(fmt, ['id','code','qty','label','ref','v'], [valid,cases[4][1]]))
            actions['selected_check'] = ('X', copy_statement('child', selected_bad, options, '(id,code,qty,label,ref,v)'))
            actions['selected_check_state'] = ('Q', 'SELECT id,code,qty,label,ref,VEC_TO_TEXT(v) FROM child ORDER BY id')
        # The failed batches must not leave uniqueness reservations or dead sessions.
        recovery = import_file(tmp_path, f'recovery-{fmt}', import_document(fmt, keys, [valid]))
        actions['recovery'] = ('E', copy_statement('child', recovery, options))
        actions['after'] = ('Q', 'SELECT id,code,qty,label,ref,VEC_TO_TEXT(v) FROM child ORDER BY id')
        results = scalar_batch(import_client, [('Q' if mode == 'X' else mode, sql, ())
                                               for mode, sql in actions.values()])
        r = dict(zip(actions, results))
        for name in ('parent', 'parent_row', 'child'):
            assert 'affected' in r[name], (name, r[name])
        assert r['baseline'] == {'affected':1}, r['baseline']
        import_constraint_state(r['before'], [baseline])
        for name, _ in attempts:
            assert 'error' in r[name], (name, r[name])
            import_constraint_state(r[name+'_state'], [baseline])
        if fmt == 'JSON':
            assert 'error' in r['selected_check'], r['selected_check']
            import_constraint_state(r['selected_check_state'], [baseline])
        assert r['recovery'] == {'affected':1}, r['recovery']
        import_constraint_state(r['after'], [baseline, valid])

    # Different destination types have distinct conversion obligations. Exercise
    # textual CSV fields and JSON string values through the actual COPY entry.
    for fmt in ('CSV', 'JSON'):
        options = f'FORMAT {fmt}' + (', HEADER false' if fmt == 'CSV' else '')
        actions = {'create': ('E', IMPORT_SCHEMA),
                   'seed': ('E', "INSERT INTO items(id,name) VALUES(1,'kept')")}
        for column, good_value, bad_value in [
            ('score', 1.5, 'bad-float'), ('enabled', 'true', 'bad-bool'),
            ('stamp', '2024-01-01T00:00:00Z', 'bad-time'),
            ('doc', '{"x":1}', '{broken'), ('v', '[1,2,3]', '[broken]'),
        ]:
            data = import_file(tmp_path, f'conversion-{fmt}-{column}',
                               import_document(fmt, ['id',column], [[2,good_value],[3,bad_value]]))
            actions[column] = ('X', copy_statement('items',data,options,f'(id,{column})'))
            actions[column+'_state'] = ('Q', IMPORT_READ)
        r = schema_run(import_client, actions)
        for name in actions:
            if name.endswith('_state'):
                import_rows(r[name], [[1,'kept',23,None,None,None,None,None]])


def test_explicit_transaction_and_missing_destinations_are_rejected(import_client, tmp_path):
    source = import_file(tmp_path, 'valid.csv', 'id,note\n7,imported\n8,second\n')
    options = 'FORMAT CSV, HEADER true'
    r = schema_run(import_client, {
        'create': ('E', 'CREATE TABLE items(id INTEGER PRIMARY KEY,note TEXT)'),
        'baseline': ('E', copy_statement('items',source,options)),
        'before': ('Q', 'SELECT * FROM items ORDER BY id'),
        'target': ('E', 'CREATE TABLE target(id INTEGER PRIMARY KEY,note TEXT)'),
        'seed': ('E', "INSERT INTO target VALUES(1,'kept')"),
        'begin': ('E', 'BEGIN'),
        'untouched_transaction': ('X', copy_statement('target',source,options)),
        'untouched_state': ('Q', 'SELECT * FROM target ORDER BY id'),
        'pending': ('E', "INSERT INTO target VALUES(2,'pending')"),
        'change': ('E', "UPDATE target SET note='changed' WHERE id=1"),
        'in_transaction': ('X', copy_statement('target',source,options)),
        'still_pending': ('Q', 'SELECT * FROM target ORDER BY id'),
        'rollback': ('E', 'ROLLBACK'),
        'rolled_back': ('Q', 'SELECT * FROM target ORDER BY id'),
        'missing_table': ('X', copy_statement('absent',source,options)),
        'missing_column': ('X', copy_statement('target',source,options,'(id,absent)')),
        'unchanged': ('Q', 'SELECT * FROM target ORDER BY id'),
        'import_after': ('E', copy_statement('target',source,options)),
        'after': ('Q', 'SELECT * FROM target ORDER BY id'),
    })
    assert r['baseline']['affected'] == 2
    assert r['import_after']['affected'] == 2
    fk_expect(r, {
        'before': [[7,'imported'],[8,'second']],
        'untouched_state': [[1,'kept']],
        'still_pending': [[1,'changed'],[2,'pending']],
        'rolled_back': [[1,'kept']], 'unchanged': [[1,'kept']],
        'after': [[1,'kept'],[7,'imported'],[8,'second']],
    })
