# feature: F04
"""Acceptance tests for projection, ordering, distinct rows and series relations."""
import datetime as dt
import secrets
import pytest
from _helpers import rows_equal, tied_rows_equal
from F01_helpers import build_rust_client
from F02_helpers import scalar_rows, sql_text, utc_instant
from F03_helpers import schema_run
from F04_helpers import (SELECTION_CLIENT, selection_columns, selection_json_array,
                         selection_instants)


@pytest.fixture(scope='module')
def selection_client(tmp_path_factory):
    return build_rust_client(SELECTION_CLIENT, tmp_path_factory.mktemp('f04-rust'))


def test_projection_filtering_and_aliases(selection_client):
    setup = [
        'CREATE TABLE samples (id INTEGER,label TEXT,qty INTEGER,enabled BOOLEAN)',
        "INSERT INTO samples VALUES (7,'seven',3,TRUE),(2,'two',8,FALSE),"
        "(9,'nine',NULL,TRUE),(4,'four',5,NULL),(6,'six',-2,TRUE)",
    ]
    projection = ('SELECT s.label AS title,s.qty*3+s.id AS score '
                  'FROM samples AS s WHERE s.enabled AND s.qty > 0')
    r = schema_run(selection_client, {
        'create': ('E', setup[0]), 'insert': ('E', setup[1]),
        'all': ('Q', 'SELECT * FROM samples'),
        'qualified': ('Q', 'SELECT s.* FROM samples AS s'),
        'projected': ('Q', projection),
        'boolean': ('Q', 'SELECT id FROM samples WHERE enabled'),
        'comparison': ('Q', 'SELECT id FROM samples WHERE qty > 0'),
        'none': ('Q', 'SELECT label FROM samples WHERE qty > 100'),
        'empty_create': ('E', 'CREATE TABLE empty_source (id INTEGER,label TEXT)'),
        'empty': ('Q', 'SELECT label,id+1 FROM empty_source'),
    })
    expected = [[7,'seven',3,True],[2,'two',8,False],[9,'nine',None,True],
                [4,'four',5,None],[6,'six',-2,True]]
    for name in ('all', 'qualified'):
        assert rows_equal(scalar_rows(r[name]), expected, ordered=False), r[name]
    assert scalar_rows(r['projected']) == [['seven',16]]
    assert rows_equal(scalar_rows(r['boolean']), [[7],[9],[6]], ordered=False)
    assert rows_equal(scalar_rows(r['comparison']), [[7],[2],[4]], ordered=False)
    assert scalar_rows(r['none']) == []
    assert scalar_rows(r['empty']) == []
    assert selection_columns(selection_client, setup, 'SELECT * FROM samples') == ['id','label','qty','enabled']
    assert selection_columns(selection_client, setup, projection) == ['title','score']


def test_ordering_pagination_and_missing_columns(selection_client):
    prefix = 'SELECT id FROM ranks WHERE id > 20 ORDER BY grp ASC,score DESC NULLS LAST,id ASC'
    r = schema_run(selection_client, {
        'create': ('E', 'CREATE TABLE ranks (id INTEGER,grp INTEGER,score INTEGER)'),
        'insert': ('E', 'INSERT INTO ranks VALUES (41,2,8),(12,1,3),(55,2,NULL),(23,1,9),(67,2,3),(34,1,NULL),(78,1,9)'),
        'ordered': ('Q', 'SELECT id,grp,score FROM ranks ORDER BY grp ASC,score DESC NULLS LAST,id ASC'),
        'reversed': ('Q', 'SELECT id FROM ranks ORDER BY grp DESC,score ASC NULLS FIRST,id DESC'),
        'expression': ('Q', 'SELECT id FROM ranks ORDER BY score * -1 ASC NULLS LAST,id DESC'),
        'ties': ('Q', 'SELECT id,grp,score FROM ranks ORDER BY grp ASC,score DESC NULLS LAST'),
        'page': ('Q', prefix + ' LIMIT 3 OFFSET 1'),
        'tail': ('Q', prefix + ' LIMIT 10 OFFSET 4'),
        'offset_only': ('Q', prefix + ' OFFSET 4'),
        'unordered_zero': ('Q', 'SELECT id FROM ranks LIMIT 0'),
        'unordered_page': ('Q', 'SELECT id FROM ranks LIMIT 10 OFFSET 3'),
        'zero': ('Q', prefix + ' LIMIT 0'),
        'past_end': ('Q', prefix + ' LIMIT 3 OFFSET 20'),
        'selected_missing': ('X', 'SELECT absent FROM ranks'),
        'after_error': ('Q', 'SELECT id FROM ranks ORDER BY id'),
    })
    ordered = [[23,1,9],[78,1,9],[12,1,3],[34,1,None],[41,2,8],[67,2,3],[55,2,None]]
    assert scalar_rows(r['ordered']) == ordered
    assert scalar_rows(r['reversed']) == [[55],[67],[41],[34],[12],[78],[23]]
    assert scalar_rows(r['expression']) == [[78],[23],[41],[67],[12],[55],[34]]
    assert tied_rows_equal(scalar_rows(r['ties']), ordered, key=lambda row: row[1:])
    assert scalar_rows(r['page']) == [[78],[34],[41]]
    assert scalar_rows(r['tail']) == [[67],[55]]
    assert scalar_rows(r['offset_only']) == [[67],[55]]
    assert scalar_rows(r['unordered_zero']) == []
    page = scalar_rows(r['unordered_page'])
    assert len(page) == 4 and len({row[0] for row in page}) == 4
    assert {row[0] for row in page} <= {12,23,34,41,55,67,78}
    assert scalar_rows(r['zero']) == []
    assert scalar_rows(r['past_end']) == []
    assert scalar_rows(r['after_error']) == [[12],[23],[34],[41],[55],[67],[78]]


def test_distinct_rows_and_ordered_representatives(selection_client):
    r = schema_run(selection_client, {
        'create': ('E', 'CREATE TABLE choices (id INTEGER,k TEXT,part INTEGER,score INTEGER,label TEXT)'),
        'insert': ('E', "INSERT INTO choices VALUES (1,'a',1,4,'low'),(2,'a',1,9,'high'),(3,'a',2,6,'other'),(4,'b',1,3,'early'),(5,'b',1,8,'late'),(6,NULL,1,2,'null_low'),(7,NULL,1,7,'null_high'),(8,'a',1,9,'tie')"),
        'baseline': ('Q', 'SELECT k,part FROM choices'),
        'distinct': ('Q', 'SELECT DISTINCT k,part FROM choices'),
        'ordered_distinct': ('Q', 'SELECT DISTINCT k,part FROM choices ORDER BY k NULLS LAST,part'),
        'limited_distinct': ('Q', 'SELECT DISTINCT k,part FROM choices LIMIT 4'),
        'interleaved': ('Q', 'SELECT DISTINCT ON (k) label FROM choices ORDER BY id'),
        'representative_page': ('Q', 'SELECT DISTINCT ON (k) label FROM choices ORDER BY k ASC NULLS LAST,score DESC,id ASC LIMIT 5 OFFSET 1'),
        'hidden_key': ('Q', 'SELECT DISTINCT ON (k) label FROM choices ORDER BY k ASC NULLS LAST,score DESC,id ASC'),
        'compound_key': ('Q', 'SELECT DISTINCT ON (k,part) label FROM choices ORDER BY k ASC NULLS LAST,part ASC,score DESC,id ASC'),
        'earliest': ('Q', 'SELECT DISTINCT ON (k) label FROM choices ORDER BY k ASC NULLS LAST,score ASC,id ASC'),
        'tied': ('Q', 'SELECT DISTINCT ON (k) k,label FROM choices ORDER BY k ASC NULLS LAST,score DESC'),
    })
    assert rows_equal(scalar_rows(r['baseline']), [['a',1],['a',1],['a',2],['b',1],['b',1],[None,1],[None,1],['a',1]], ordered=False)
    assert rows_equal(scalar_rows(r['distinct']), [['a',1],['a',2],['b',1],[None,1]], ordered=False)
    assert scalar_rows(r['ordered_distinct']) == [['a',1],['a',2],['b',1],[None,1]]
    assert rows_equal(scalar_rows(r['limited_distinct']), [['a',1],['a',2],['b',1],[None,1]], ordered=False)
    assert scalar_rows(r['interleaved']) == [['low'],['early'],['null_low']]
    assert scalar_rows(r['representative_page']) == [['late'],['null_high']]
    assert scalar_rows(r['hidden_key']) == [['high'],['late'],['null_high']]
    assert scalar_rows(r['compound_key']) == [['high'],['other'],['late'],['null_high']]
    assert scalar_rows(r['earliest']) == [['low'],['early'],['null_low']]
    tied = scalar_rows(r['tied'])
    assert len(tied) == 3
    assert tied[0] in [['a','high'],['a','tie']]
    assert tied[1:] == [['b','late'],[None,'null_high']]


def test_values_and_numeric_series(selection_client):
    shift = secrets.randbelow(129) - 64
    actions = {
        'values': ('Q', "SELECT * FROM (VALUES (4,'delta'),(1,'alpha'),(4,'delta'),(3,NULL)) AS t(n,name)"),
        'values_query': ('Q', "SELECT t.name,t.n*2 FROM (VALUES (4,'delta'),(1,'alpha'),(4,'delta'),(3,'gamma')) AS t(n,name) WHERE t.n>1 ORDER BY t.n DESC,t.name ASC LIMIT 2 OFFSET 1"),
    }
    # Binary-exact fractions avoid imposing an undocumented rounding tolerance.
    series = [
        ('-5,6,3', 'ASC', 'i', [-5,-2,1,4]),
        ('1,2,0.5', 'ASC', 'f', [1.0,1.5,2.0]),
        (f'{shift-7},{shift+18}', 'ASC', 'i', list(range(shift-7,shift+19))),
        ('8,-4,-3', 'DESC', 'i', [8,5,2,-1,-4]),
        # Omitted numeric steps follow endpoint direction and advance by one.
        (f'{shift+5},{shift+2}', 'DESC', 'i', [shift+5,shift+4,shift+3,shift+2]),
        (f'{shift+0.25},{shift+2.25}', 'ASC', 'f', [shift+0.25,shift+1.25,shift+2.25]),
        (f'{shift+2.25},{shift+0.25}', 'DESC', 'f', [shift+2.25,shift+1.25,shift+0.25]),
        (f'{shift+0.25},{shift+2.0}', 'ASC', 'f', [shift+0.25,shift+1.25]),
        (f'{shift+2.25},{shift+0.0}', 'DESC', 'f', [shift+2.25,shift+1.25,shift+0.25]),
        ('-2,-2,3', 'ASC', 'i', [-2]),
        ('-0.5,1.0,0.5', 'ASC', 'f', [-0.5,0.0,0.5,1.0]),
        ('1.25,-0.5,-0.5', 'DESC', 'f', [1.25,0.75,0.25,-0.25]),
        ('3,9,-2', 'ASC', 'i', []),
        ('9,3,2', 'ASC', 'i', []),
        ('1.0,3.0,-0.5', 'ASC', 'f', []),
        ('3.0,1.0,0.5', 'ASC', 'f', []),
    ]
    for index, (args, direction, _, _) in enumerate(series):
        actions[f'series_{index}'] = ('Q', f'SELECT value FROM generate_series({args}) ORDER BY value {direction}')
    actions.update({
        'relation': ('Q', 'SELECT n*2 FROM generate_series(-4,12,2) AS g(n) WHERE n > 0 ORDER BY n DESC LIMIT 3 OFFSET 1'),
        'offset': ('Q', 'SELECT n FROM generate_series(-4,12,2) AS g(n) ORDER BY n ASC LIMIT 3 OFFSET 2'),
        'unfiltered_page': ('Q', 'SELECT value FROM generate_series(1,10) LIMIT 3 OFFSET 2'),
        'inclusive_filter': ('Q', 'SELECT value FROM generate_series(1,10) WHERE value >= 3 AND value <= 5 ORDER BY value'),
        'unknown_values': ('Q', 'SELECT n FROM (VALUES (1,TRUE),(2,NULL),(3,FALSE)) AS v(n,f) WHERE f'),
        'integer_zero': ('X', 'SELECT * FROM generate_series(3,9,0)'),
        'float_zero': ('X', 'SELECT * FROM generate_series(1.0,3.0,0.0)'),
    })
    r = schema_run(selection_client, actions)
    assert rows_equal(scalar_rows(r['values']), [[4,'delta'],[1,'alpha'],[4,'delta'],[3,None]], ordered=False)
    assert scalar_rows(r['values_query']) == [['delta',8],['gamma',6]]
    for index, (_, _, tag, expected) in enumerate(series):
        assert r[f'series_{index}']['rows'] == [[(tag,value)] for value in expected]
    assert scalar_rows(r['relation']) == [[20],[16],[12]]
    assert scalar_rows(r['offset']) == [[0],[2],[4]]
    page = scalar_rows(r['unfiltered_page'])
    assert len(page) == 3 and len({row[0] for row in page}) == 3
    assert {row[0] for row in page} <= set(range(1,11))
    assert scalar_rows(r['inclusive_filter']) == [[3],[4],[5]]
    assert scalar_rows(r['unknown_values']) == [[1]]


def test_timestamp_units_and_scalar_series(selection_client):
    shift = secrets.randbelow(129) - 64
    start = dt.datetime(2024,2,28,tzinfo=dt.timezone.utc)
    # Every promised unit is measured against independent datetime arithmetic;
    # fixed-duration years/months cross leap years and calendar-month boundaries.
    units = [
        ('years', dt.timedelta(days=365)), ('months', dt.timedelta(days=30)),
        ('weeks', dt.timedelta(weeks=1)), ('days', dt.timedelta(days=1)),
        ('hours', dt.timedelta(hours=1)), ('minutes', dt.timedelta(minutes=1)),
        ('seconds', dt.timedelta(seconds=1)), ('milliseconds', dt.timedelta(milliseconds=1)),
        ('microseconds', dt.timedelta(microseconds=1)),
    ]
    actions = {}
    for unit, duration in units:
        args = ','.join([sql_text(start.isoformat()), sql_text((start+5*duration).isoformat()), sql_text('2 '+unit)])
        actions[unit+'_table'] = ('Q', f'SELECT value FROM generate_series({args}) ORDER BY value ASC')
        actions[unit+'_scalar'] = ('Q', f'SELECT generate_series({args})')
    descending = "'2024-03-05','2024-02-28','-2 days'"
    actions.update({
        'descending': ('Q', f'SELECT value FROM generate_series({descending}) ORDER BY value DESC'),
        'descending_scalar': ('Q', f'SELECT generate_series({descending})'),
        'relation': ('Q', "SELECT value FROM generate_series('2024-02-28','2024-03-05','1 day') WHERE value > '2024-02-29' ORDER BY value DESC LIMIT 2 OFFSET 1"),
        'zero_table': ('X', "SELECT * FROM generate_series('2024-01-01','2024-01-03','0 days')"),
        'away_table': ('Q', "SELECT * FROM generate_series('2024-01-01','2024-01-03','-1 day')"),
        'away_scalar': ('Q', "SELECT generate_series('2024-01-01','2024-01-03','-1 day')"),
        'away_reverse_table': ('Q', "SELECT * FROM generate_series('2024-01-03','2024-01-01','1 day')"),
        'away_reverse_scalar': ('Q', "SELECT generate_series('2024-01-03','2024-01-01','1 day')"),
    })
    scalar_cases = [
        ('-5,6,3', [-5,-2,1,4]), ('1,2,0.5',[1.0,1.5,2.0]), (f'{shift-7},{shift+18}',list(range(shift-7,shift+19))), ('8,-4,-3', [8,5,2,-1,-4]),
        # Keep the scalar oracle independent from the table relation oracle.
        (f'{shift+5},{shift+2}', [shift+5,shift+4,shift+3,shift+2]),
        (f'{shift+0.25},{shift+2.25}', [shift+0.25,shift+1.25,shift+2.25]), (f'{shift+2.25},{shift+0.25}', [shift+2.25,shift+1.25,shift+0.25]),
        (f'{shift+0.25},{shift+2.0}', [shift+0.25,shift+1.25]), (f'{shift+2.25},{shift+0.0}', [shift+2.25,shift+1.25,shift+0.25]),
        ('-0.5,1.0,0.5', [-0.5,0.0,0.5,1.0]),
        ('1.25,-0.5,-0.5', [1.25,0.75,0.25,-0.25]),
        ('3,9,-2', []), ('9,3,2', []), ('1.0,3.0,-0.5', []), ('3.0,1.0,0.5', []),
    ]
    for index, (args, _) in enumerate(scalar_cases):
        actions[f'numeric_{index}'] = ('Q', f'SELECT generate_series({args})')
    r = schema_run(selection_client, actions)
    for unit, duration in units:
        expected = [start,start+2*duration,start+4*duration]
        assert selection_instants(r[unit+'_table']) == expected, unit
        assert [utc_instant(value) for value in selection_json_array(r[unit+'_scalar'])] == expected, unit
    expected_descending = [dt.datetime(2024,3,5,tzinfo=dt.timezone.utc)-dt.timedelta(days=d) for d in (0,2,4,6)]
    assert selection_instants(r['descending']) == expected_descending
    assert [utc_instant(value) for value in selection_json_array(r['descending_scalar'])] == expected_descending
    assert selection_instants(r['relation']) == [dt.datetime(2024,3,d,tzinfo=dt.timezone.utc) for d in (4,3)]
    for name in ('away_table','away_reverse_table'):
        assert scalar_rows(r[name]) == []
    for name in ('away_scalar','away_reverse_scalar'):
        assert selection_json_array(r[name]) == []
    for index, (_, expected) in enumerate(scalar_cases):
        assert selection_json_array(r[f'numeric_{index}']) == expected
