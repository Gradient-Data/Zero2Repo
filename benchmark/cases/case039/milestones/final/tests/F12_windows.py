# feature: F12
"""Window analytics through public Rust SQL, with independent row expectations."""
import pytest
from F01_helpers import build_rust_client
from F02_helpers import SCALAR_CLIENT, scalar_rows
from F03_helpers import schema_run
from F12_helpers import WINDOW_SETUP, window_queries


@pytest.fixture(scope='module')
def window_client(tmp_path_factory):
    return build_rust_client(SCALAR_CLIENT, tmp_path_factory.mktemp('f12-rust'))


def test_partitioned_peer_ranking(window_client):
    w = 'PARTITION BY g ORDER BY k,h'
    rows = window_queries(window_client, {
        'rank': f'''SELECT id,ROW_NUMBER() OVER ({w}),RANK() OVER ({w}),
            DENSE_RANK() OVER ({w}),PERCENT_RANK() OVER ({w}),CUME_DIST() OVER ({w}),
            ROW_NUMBER() OVER (PARTITION BY h ORDER BY id DESC) FROM w ORDER BY id''',
    })['rank']
    assert [r[0] for r in rows] == list(range(1,10))
    assert all(len(r) == 7 for r in rows)
    # Only peer groups have freedom to assign row numbers to individual rows.
    for indices, numbers in [([0,1],[1,2]), ([2],[3]), ([3,4],[4,5]),
                              ([5],[1]), ([6,7],[1,2]), ([8],[3])]:
        assert sorted(rows[i][1] for i in indices) == numbers
    assert [[r[2],r[3],r[6]] for r in rows] == [
        [1,1,8],[1,1,7],[3,2,1],[4,3,6],[4,3,5],
        [1,1,4],[1,1,3],[1,1,2],[3,2,1],
    ]
    composite = window_queries(window_client, {
        'directions': 'SELECT id,ROW_NUMBER() OVER (PARTITION BY g,h ORDER BY id),ROW_NUMBER() OVER (PARTITION BY g,h ORDER BY id DESC) FROM w ORDER BY id',
    })['directions']
    assert composite == [[1,1,4],[2,2,3],[3,1,1],[4,3,2],[5,4,1],
                         [6,1,1],[7,1,3],[8,2,2],[9,3,1]]
    # Compare mathematical peer fractions with the specified absolute error.
    assert [r[4] for r in rows] == pytest.approx(
        [0,0,.5,.75,.75,0,0,0,1], rel=0, abs=1e-9)
    assert [r[5] for r in rows] == pytest.approx(
        [.4,.4,.6,1,1,1,2/3,2/3,1], rel=0, abs=1e-9)


def test_ordered_balanced_buckets(window_client):
    seven = schema_run(window_client, {
        'create': ('E', 'CREATE TABLE seven (id INTEGER)'),
        'seed': ('E', 'INSERT INTO seven VALUES (1),(2),(3),(4),(5),(6),(7)'),
        'buckets': ('Q', 'SELECT id,NTILE(5) OVER (ORDER BY id) FROM seven ORDER BY id'),
    })
    assert scalar_rows(seven['buckets']) == [[1,1],[2,1],[3,2],[4,2],[5,3],[6,4],[7,5]]
    rows = window_queries(window_client, {
        'buckets': '''SELECT id,NTILE(3) OVER (PARTITION BY g ORDER BY id),
            NTILE(8) OVER (PARTITION BY g ORDER BY id) FROM w ORDER BY id''',
    })['buckets']
    assert rows == [[1,1,1],[2,1,2],[3,2,3],[4,2,4],[5,3,5],
                    [6,1,1],[7,1,1],[8,2,2],[9,3,3]]


def test_neighbors_and_frame_values(window_client):
    setup = {
        'create': ('E', 'CREATE TABLE n (id INTEGER,g TEXT,v INTEGER)'),
        'insert': ('E', "INSERT INTO n VALUES (1,'A',9),(2,'A',NULL),(3,'A',21),(4,'A',4),(5,'B',16),(6,'B',8)"),
    }
    w = 'PARTITION BY g ORDER BY id'
    frame = w + ' ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING'
    rows = window_queries(window_client, {
        'values': f'''SELECT id,LAG(v,2,-777) OVER ({w}),LEAD(v,2,-888) OVER ({w}),
            LAG(v) OVER ({w}),LEAD(v) OVER ({w}),FIRST_VALUE(v) OVER ({frame}),
            LAST_VALUE(v) OVER ({frame}),NTH_VALUE(v,2) OVER ({frame}),
            NTH_VALUE(v,4) OVER ({frame}) FROM n ORDER BY id''',
    }, setup)['values']
    assert rows == [
        [1,-777,21,None,None,9,None,None,None],
        [2,-777,4,9,21,9,21,None,None],
        [3,9,-888,None,4,None,4,21,None],
        [4,None,-888,21,None,21,4,4,None],
        [5,-777,-888,None,8,16,8,8,None],
        [6,-777,-888,16,None,16,8,8,None],
    ]


def test_rows_and_range_aggregates(window_client):
    setup = {
        'create': ('E', 'CREATE TABLE f (id INTEGER,g TEXT,k INTEGER,v INTEGER)'),
        'insert': ('E', "INSERT INTO f VALUES (1,'A',10,6),(2,'A',10,18),(3,'A',14,30),(4,'A',30,42),(5,'A',NULL,54),(6,'A',NULL,66),(7,'B',12,120)"),
    }
    missing = window_queries(window_client, {
        'counts': 'SELECT id,COUNT(v) OVER (PARTITION BY g ORDER BY id ROWS BETWEEN 1 PRECEDING AND CURRENT ROW),COUNT(*) OVER (PARTITION BY g ORDER BY id ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM f ORDER BY id',
    }, {**setup, 'missing': ('E', 'UPDATE f SET v=NULL WHERE id IN (2,3,7)')})['counts']
    assert missing == [[1,1,1],[2,1,2],[3,0,2],[4,1,2],[5,2,2],[6,2,2],[7,0,1]]
    clauses = {
        'moving': 'ORDER BY id ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING',
        'running': 'ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW',
        'tail': 'ORDER BY id ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING',
        'whole': 'ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING',
        'before': 'ORDER BY id ROWS BETWEEN 2 PRECEDING AND 1 PRECEDING',
        'after': 'ORDER BY id ROWS BETWEEN 1 FOLLOWING AND 2 FOLLOWING',
        'range_both': 'ORDER BY k RANGE BETWEEN 4 PRECEDING AND 4 FOLLOWING',
        'range_before': 'ORDER BY k RANGE BETWEEN 4 PRECEDING AND CURRENT ROW',
        'range_after': 'ORDER BY k RANGE BETWEEN CURRENT ROW AND 4 FOLLOWING',
        'range_running': 'ORDER BY k NULLS LAST RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW',
        'range_tail': 'ORDER BY k NULLS LAST RANGE BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING',
        'ordered_default': 'ORDER BY k NULLS LAST',
        'unordered_default': '',
        'start_only': 'ORDER BY id ROWS 2 PRECEDING',
    }
    queries = {name: 'SELECT id,' + ','.join(
        f'{function} OVER (PARTITION BY g {clause})'
        for function in ['COUNT(*)','SUM(v)','AVG(v)','MIN(v)','MAX(v)']
    ) + ' FROM f ORDER BY id' for name,clause in clauses.items()}
    results = window_queries(window_client, queries, setup)
    # Independent expectations from the rows belonging to each frame.
    # Every average here is exactly representable, so no tolerance is needed.
    expected = {
        'moving': [[2,24,12,6,18],[3,54,18,6,30],[3,90,30,18,42],
                   [3,126,42,30,54],[3,162,54,42,66],[2,120,60,54,66]],
        'running': [[1,6,6,6,6],[2,24,12,6,18],[3,54,18,6,30],
                    [4,96,24,6,42],[5,150,30,6,54],[6,216,36,6,66]],
        'tail': [[6,216,36,6,66],[5,210,42,18,66],[4,192,48,30,66],
                 [3,162,54,42,66],[2,120,60,54,66],[1,66,66,66,66]],
        'whole': [[6,216,36,6,66]] * 6,
        'before': [[0,None,None,None,None],[1,6,6,6,6],[2,24,12,6,18],
                   [2,48,24,18,30],[2,72,36,30,42],[2,96,48,42,54]],
        # Aggregate values are specified only while a following start remains
        # inside the partition. Row retention is still checked for every row.
        'after': [[2,48,24,18,30],[2,72,36,30,42],[2,96,48,42,54],
                  [2,120,60,54,66],[1,66,66,66,66]],
        'range_both': [[3,54,18,6,30],[3,54,18,6,30],[3,54,18,6,30],
                       [1,42,42,42,42],[2,120,60,54,66],[2,120,60,54,66]],
        'range_before': [[2,24,12,6,18],[2,24,12,6,18],[3,54,18,6,30],
                         [1,42,42,42,42],[2,120,60,54,66],[2,120,60,54,66]],
        'range_after': [[3,54,18,6,30],[3,54,18,6,30],[1,30,30,30,30],
                        [1,42,42,42,42],[2,120,60,54,66],[2,120,60,54,66]],
        'range_running': [[2,24,12,6,18],[2,24,12,6,18],[3,54,18,6,30],
                          [4,96,24,6,42],[6,216,36,6,66],[6,216,36,6,66]],
        'range_tail': [[6,216,36,6,66],[6,216,36,6,66],[4,192,48,30,66],
                       [3,162,54,42,66],[2,120,60,54,66],[2,120,60,54,66]],
    }
    expected['ordered_default'] = expected['range_running']
    expected['unordered_default'] = expected['whole']
    expected['start_only'] = [[1,6,6,6,6],[2,24,12,6,18],[3,54,18,6,30],
                              [3,90,30,18,42],[3,126,42,30,54],[3,162,54,42,66]]
    # No PARTITION BY means all source rows share one partition.
    global_rows = window_queries(window_client, {
        'global': 'SELECT id,COUNT(*) OVER (),SUM(v) OVER () FROM f ORDER BY id',
    }, setup)['global']
    assert global_rows == [[i,7,336] for i in range(1,8)]
    for name, values in expected.items():
        assert [row[0] for row in results[name]] == list(range(1,8)), name
        assert all(len(row) == 6 for row in results[name]), name
        if name != 'after':
            singleton = [0,None,None,None,None] if name == 'before' else [1,120,120,120,120]
            values = values + [singleton]
        expected_rows = [[i,*row] for i,row in enumerate(values,1)]
        assert results[name][:len(expected_rows)] == expected_rows, name


def test_named_windows_empty_and_undefined(window_client):
    sql = '''SELECT id,SUM(v) OVER narrow,COUNT(*) OVER narrow,FIRST_VALUE(v) OVER narrow,
        MAX(v) OVER narrow
        FROM w {where} WINDOW narrow AS
        (PARTITION BY g ORDER BY id DESC ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) ORDER BY id'''
    results = schema_run(window_client, {
        **WINDOW_SETUP,
        'named': ('Q', sql.format(where='')),
        'attached': ('Q', 'SELECT id,SUM(v) OVER (narrow ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) FROM w WINDOW narrow AS (PARTITION BY g ORDER BY id DESC) ORDER BY id'),
        'empty': ('Q', sql.format(where='WHERE id<0')),
        'undefined': ('X', 'SELECT SUM(v) OVER absent_window FROM w'),
    })
    assert scalar_rows(results['named']) == [
        [1,10,2,2,8],[2,14,2,12,12],[3,16,2,4,12],[4,18,2,14,14],
        [5,14,1,14,14],[6,20,1,20,20],[7,16,2,10,10],[8,28,2,18,18],[9,18,1,18,18],
    ]
    assert scalar_rows(results['attached']) == [[1,10],[2,14],[3,16],[4,18],[5,14],[6,20],[7,16],[8,28],[9,18]]
    # Successful empty rows and a public query/consumption Err are distinct.
    assert scalar_rows(results['empty']) == []
    assert 'error' in results['undefined']
