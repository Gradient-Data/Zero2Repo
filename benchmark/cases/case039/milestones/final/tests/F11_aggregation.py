# feature: F11
"""Grouped SQL aggregation acceptance through the public Rust database API."""
import math
import pytest
from _helpers import rows_equal, parse_json
from F01_helpers import build_rust_client
from F02_helpers import SCALAR_CLIENT
from F11_helpers import aggregate_queries, aggregate_rows_equal


@pytest.fixture(scope='module')
def aggregation_client(tmp_path_factory):
    return build_rust_client(SCALAR_CLIENT, tmp_path_factory.mktemp('f11-rust'))


def test_group_expressions_and_having(aggregation_client):
    result = aggregate_queries(aggregation_client, {
        'groups': 'SELECT LOWER(g),h%2,COUNT(*),SUM(v) FROM a GROUP BY LOWER(g),h%2',
        'having': 'SELECT LOWER(g),h%2,COUNT(*),SUM(v) FROM a GROUP BY LOWER(g),h%2 HAVING SUM(v)>5',
        'unknown': 'SELECT g,COUNT(*) FROM a GROUP BY g HAVING SUM(v)=NULL',
        'empty': 'SELECT g,COUNT(*) FROM a WHERE seq<0 GROUP BY g',
    }, {'more': ('E', "INSERT INTO a VALUES (7,'a',1,4,'fig'),(8,'C',2,NULL,NULL)")})
    assert aggregate_rows_equal(result['groups'], [
        ['a',1,3,6], ['a',0,1,2], ['b',1,1,8], [None,1,2,14], ['c',0,1,None]
    ], numeric_columns=(3,), ordered=False)
    # Numeric SUM may be represented as integer or float on this query path.
    assert sorted(result['having'], key=lambda r: str(r[0])) == sorted([
        ['a',1,3,6], ['b',1,1,8], [None,1,2,14]
    ], key=lambda r: str(r[0]))
    assert result['unknown'] == []
    assert result['empty'] == []


def test_basic_distinct_and_missing(aggregation_client):
    expr = 'COUNT(*),COUNT(v),SUM(v),AVG(v),MIN(v),MAX(v),COUNT(DISTINCT v),SUM(DISTINCT v),AVG(DISTINCT v),MIN(DISTINCT v),MAX(DISTINCT v)'
    result = aggregate_queries(aggregation_client, {
        name: f'SELECT {expr} FROM a {where}' for name, where in
        [('all',''), ('empty','WHERE seq<0'), ('null','WHERE v IS NULL')]
    })
    assert aggregate_rows_equal(result['all'], [[6,4,26,6.5,2,14,3,24,8.0,2,14]], numeric_columns=(2,7), ordered=True)
    assert result['empty'] == [[0,0,None,None,None,None,0,None,None,None,None]]
    assert result['null'] == [[2,0,None,None,None,None,0,None,None,None,None]]
    dynamic = aggregate_queries(aggregation_client, {
        'counts': 'SELECT g,COUNT(v),COUNT(*),MEDIAN(v) FROM a GROUP BY g',
    })
    assert aggregate_rows_equal(dynamic['counts'], [['A',2,3,2],['B',1,1,8],[None,1,2,14]],
                                numeric_columns=(3,), ordered=False)


def test_statistics_and_distinct(aggregation_client):
    functions = ['MEDIAN','VAR_SAMP','VAR_POP','STDDEV_SAMP','STDDEV_POP']
    expr = ','.join(f'{fn}(v)' for fn in functions)
    distinct = ','.join(f'{fn}(DISTINCT v)' for fn in functions)
    result = aggregate_queries(aggregation_client, {
        'even': f'SELECT {expr} FROM a',
        'odd': f'SELECT {expr} FROM a WHERE seq<>3',
        'single': f'SELECT {expr} FROM a WHERE v=14',
        'empty': f'SELECT {expr} FROM a WHERE seq<0',
        'null': f'SELECT {expr} FROM a WHERE v IS NULL',
        'grouped_distinct': f'SELECT {distinct} FROM a GROUP BY h%1',
    })
    # Independent expectations from the specified mean squared deviations
    # for [2,2,8,14] and [2,8,14].
    expected = {'even': [5.0,33.0,24.75,math.sqrt(33),math.sqrt(24.75)],
                'odd': [8.0,36.0,24.0,6.0,math.sqrt(24)],
                'single': [14.0,None,0.0,None,0.0],
                'empty': [None]*5, 'null': [None]*5}
    expected['grouped_distinct'] = expected['odd']
    scattered = aggregate_queries(aggregation_client, {
        'all': 'SELECT MEDIAN(v) FROM a',
        'groups': 'SELECT g,MEDIAN(v) FROM a GROUP BY g',
    }, {'clear': ('E', 'DELETE FROM a'),
        'reseed': ('E', "INSERT INTO a VALUES (1,'P',0,19,NULL),(2,'P',0,2,NULL),(3,'P',0,7,NULL),(4,'P',0,4,NULL),(5,'Q',0,80,NULL),(6,'Q',0,20,NULL),(7,'Q',0,50,NULL)")})
    assert scattered['all'] == [[19]]
    assert aggregate_rows_equal(scattered['groups'], [['P',5.5],['Q',50]], numeric_columns=(1,), ordered=False)
    for name, values in expected.items():
        assert len(result[name]) == 1
        assert len(result[name][0]) == len(values)
        for actual, value in zip(result[name][0], values):
            if value is None:
                assert actual is None, (name, result[name])
            else:
                assert isinstance(actual, (int,float)) and not isinstance(actual,bool)
                assert actual == pytest.approx(value, rel=1e-9, abs=1e-9), (name, result[name])


def test_ordered_first_last_text_and_arrays(aggregation_client):
    result = aggregate_queries(aggregation_client, {
        'input_order': "SELECT STRING_AGG(s,'|' ORDER BY seq),ARRAY_AGG(v ORDER BY seq) FROM a",
        'first': 'SELECT FIRST(s),LAST(s) FROM (SELECT s FROM a ORDER BY seq) q',
        'reverse': 'SELECT FIRST(s),LAST(s) FROM (SELECT s FROM a ORDER BY seq DESC) q',
        'ascending': "SELECT STRING_AGG(s,'|' ORDER BY s),ARRAY_AGG(s ORDER BY s) FROM a",
        'descending': "SELECT STRING_AGG(s,' / ' ORDER BY s DESC),ARRAY_AGG(s ORDER BY s DESC) FROM a",
        'distinct': "SELECT STRING_AGG(DISTINCT s,'|' ORDER BY s),ARRAY_AGG(DISTINCT s ORDER BY s) FROM a",
        'empty': "SELECT FIRST(s),LAST(s),STRING_AGG(s,'|'),ARRAY_AGG(s) FROM a WHERE seq<0",
        'null': "SELECT FIRST(s),LAST(s),STRING_AGG(s,'|'),ARRAY_AGG(s) FROM a WHERE s IS NULL",
    })
    assert result['input_order'][0][0] == 'pear|pear|apple|plum'
    number_array = parse_json(result['input_order'][0][1])
    assert number_array == [2,2,8,14]
    assert all(not isinstance(value, (str,bool)) for value in number_array)
    assert result['first'] == [['pear','plum']]
    assert result['reverse'] == [['plum','pear']]
    assert len(result['ascending']) == len(result['descending']) == 1
    asc, array_asc = result['ascending'][0]
    desc, array_desc = result['descending'][0]
    assert asc == 'apple|pear|pear|plum'
    assert desc == 'plum / pear / pear / apple'
    assert parse_json(array_asc) == ['apple','pear','pear','plum']
    assert parse_json(array_desc) == ['plum','pear','pear','apple']
    assert len(result['distinct']) == 1 and len(result['distinct'][0]) == 2
    text, array = result['distinct'][0]
    assert text == 'apple|pear|plum'
    assert parse_json(array) == ['apple','pear','plum']
    assert result['empty'] == [[None]*4]
    assert result['null'] == [[None]*4]


def test_rollup_cube_and_grouping_sets(aggregation_client):
    result = aggregate_queries(aggregation_client, {
        name: 'SELECT g,h,SUM(v),COUNT(*),GROUPING(g),GROUPING(h) FROM a GROUP BY ' + grouping
        for name, grouping in [('rollup','ROLLUP(g,h)'), ('cube','CUBE(g,h)'),
                               ('sets','GROUPING SETS ((g,h),(h),())'),
                               ('no_total','GROUPING SETS ((g),(h))')]
    })
    detail = [['A',1,2,2,0,0],['A',2,2,1,0,0],['B',1,8,1,0,0],[None,1,14,2,0,0]]
    by_g = [['A',None,4,3,0,1],['B',None,8,1,0,1],[None,None,14,2,0,1]]
    by_h = [[None,1,24,5,1,0],[None,2,2,1,1,0]]
    total = [[None,None,26,6,1,1]]
    assert aggregate_rows_equal(result['rollup'], detail+by_g+total, numeric_columns=(2,), ordered=False)
    assert aggregate_rows_equal(result['cube'], detail+by_g+by_h+total, numeric_columns=(2,), ordered=False)
    assert aggregate_rows_equal(result['sets'], detail+by_h+total, numeric_columns=(2,), ordered=False)
    assert aggregate_rows_equal(result['no_total'], by_g+by_h, numeric_columns=(2,), ordered=False)
