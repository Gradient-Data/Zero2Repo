# feature: F02
"""Acceptance tests for the planned scalar-expression capabilities."""
import datetime as dt
import hashlib
import json
import math
import zlib
import pytest
from F01_helpers import build_rust_client
from F02_helpers import (SCALAR_CLIENT, scalar_batch, scalar_rows, scalar_values,
                         assert_scalars, sql_text, utc_instant, utc_nanoseconds, assert_uniform)


@pytest.fixture(scope='module')
def scalar_client(tmp_path_factory):
    return build_rust_client(SCALAR_CLIENT, tmp_path_factory.mktemp('f02-rust'))


def test_typed_values_and_inspection(scalar_client):
    expressions = ['17', '2.75', "'星'", 'TRUE', "CAST('2024-05-06 07:08:09' AS TIMESTAMP)",
                   "CAST('{\"x\":7}' AS JSON)", 'NULL', 'CAST(17 AS TEXT)', 'CAST(2.75 AS INTEGER)']
    assert_scalars(scalar_client, list(zip(['TYPEOF('+x+')' for x in expressions],
                                         ['INTEGER','FLOAT','TEXT','BOOLEAN','TIMESTAMP','JSON','NULL','TEXT','INTEGER'])))
    ops = [('E', 'CREATE TABLE typed (i INTEGER, f FLOAT, s TEXT, b BOOLEAN, t TIMESTAMP, j JSON)', ())]
    integers = [-9223372036854775808, -9007199254740993, 0, 9007199254740993, 9223372036854775807]
    for i in integers:
        ops.append(('E', "INSERT INTO typed VALUES ($1, $2, $3, $4, CAST('2024-05-06 07:08:09' AS TIMESTAMP), CAST('{\"x\":7}' AS JSON))", (i, 2.75, '星', True)))
    ops += [('E', "UPDATE typed SET s = CONCAT(s, '!'), f = f + 0.5 WHERE i = $1", (0,)),
            ('Q', 'SELECT i, f, s, b, t, j FROM typed ORDER BY i', ())]
    results = scalar_batch(scalar_client, ops)
    for r in results[:-1]: assert 'affected' in r, r
    rows = results[-1]['rows']
    assert [r[0] for r in rows] == [('i', i) for i in integers]
    for row, i in zip(rows, integers):
        assert row[1:4] == [('f', 3.25 if i == 0 else 2.75), ('s', '星!' if i == 0 else '星'), ('b', True)]
        assert row[4][0] == 't' and utc_instant(row[4][1]) == dt.datetime(2024,5,6,7,8,9,tzinfo=dt.timezone.utc)
        assert row[5][0] == 'j' and json.loads(row[5][1]) == {'x':7}


def test_arithmetic_and_bits(scalar_client):
    cases = [('8 + 3',11), ('8 - 13',-5), ('-7 * 3',-21), ('-17 / 5',-3),
             ('17 / -5',-3), ('-17 % 5',-2), ('17 % -5',2), ('-(-9)',9),
             ('13 & 7',5), ('13 | 7',15), ('13 ^ 7',10), ('~13',-14),
             ('3 << 4',48), ('48 >> 3',6), ('2 + 3 * 4',14), ('(2 + 3) * 4',20),
             ('20 - 9 / 2 + 8 % 3',18),
             ('7.5 - 0.25',7.25),('2.5 * 2.5',6.25),('7.5 / 2',3.75),('-7.5 % 2',-1.5)]
    # Exact integer arithmetic and bit operations must retain bits above binary64/32-bit boundaries.
    big = 9007199254740993
    cases += [(f'{big} + 2', big+2),(f'{big} - 2',big-2),(f'{big} * 3',big*3)]
    word = (1 << 42) + 13
    cases += [(f'{word} & {word+2}',word & (word+2)),(f'{word} | 7',word | 7),
              (f'{word} ^ 7',word ^ 7),(f'~{word}',~word),
              ('3 << 40',3 << 40),(f'{word} >> 3',word >> 3)]
    cases += [(f'NULL {op} 3', None) for op in ['+','-','*','/','%']]
    cases += [(f'3 {op} NULL', None) for op in ['+','-','*','/','%']]
    assert_scalars(scalar_client, cases)


def test_three_valued_predicates(scalar_client):
    cases = [('3 = 3',True),('3 <> 4',True),('3 < 4',True),('3 <= 3',True),
             ('4 > 3',True),('4 >= 4',True),('3 = 4',False), ('3 BETWEEN 3 AND 5',True),
             ('5 BETWEEN 3 AND 5',True), ('6 BETWEEN 3 AND 5',False),('3 IN (2,3,4)',True),
             ('3 IN (2,4)',False),('3 IN (2,NULL)',None),('3 NOT IN (2,NULL)',None),('2 IN (2,NULL)',True),('2.5 < 2.7',True),('2.2 >= 2.9',False),('NULL IS NULL',True),('3 IS NOT NULL',True),
             ('NULL IS NOT DISTINCT FROM NULL',True),('3 IS NOT DISTINCT FROM NULL',False),('NULL IS NOT DISTINCT FROM 3',False),('3 IS NOT DISTINCT FROM 3',True)]
    cases += [('4 < 3',False),('4 <= 3',False),('3 > 4',False),('3 >= 4',False),('3 <> 3',False)]
    cases += [(f'NULL {op} 3',None) for op in ['=','<>','<','<=','>','>=']]
    for a, av in [('TRUE',True),('FALSE',False),('NULL',None)]:
        for b, bv in [('TRUE',True),('FALSE',False),('NULL',None)]:
            and_value = False if av is False or bv is False else (None if av is None or bv is None else True)
            or_value = True if av is True or bv is True else (None if av is None or bv is None else False)
            xor_value = None if av is None or bv is None else av != bv
            cases += [(f'{a} AND {b}',and_value),(f'{a} OR {b}',or_value),(f'{a} XOR {b}',xor_value)]
        cases.append((f'NOT {a}',None if av is None else not av))
    assert_scalars(scalar_client,cases)
    results = scalar_batch(scalar_client,[('E','CREATE TABLE p (v INTEGER)',()),
        ('E','INSERT INTO p VALUES (NULL),(2),(3),(5),(7)',()),('Q','SELECT v FROM p WHERE v > 5',()),
        ('Q','SELECT v, v BETWEEN 3 AND 5 FROM p WHERE v IS NOT NULL ORDER BY v',())])
    assert scalar_rows(results[-2]) == [[7]]
    assert scalar_rows(results[-1]) == [[2,False],[3,True],[5,True],[7,False]]


def test_numeric_text_comparison(scalar_client):
    valid = [('17',17),('+17',17),('-17',-17),('17.25',17.25),('1.7e1',17),('170e-1',17)]
    invalid = ['-.5','+.5','1.e1',' 17','17 ','.5','17.','NaN','inf','1e999','0x11','17x','']
    assert_scalars(scalar_client,[(f'{number} = {sql_text(text)}',True) for text, number in valid] +
                   [(f'17 = {sql_text(text)}',None) for text in invalid] +
                   [("'10' < '2'",True),('9007199254740992 = 9007199254740993',False),
                    ("9007199254740993 = '9007199254740993'",True)])
    ops = [('E','CREATE TABLE compare_values (n INTEGER, s TEXT)',())]
    for text, number in valid[:3] + [(text,17) for text in invalid]:
        ops += [('E','INSERT INTO compare_values VALUES ($1,$2)',(number,text)),
                ('Q','SELECT $1 = $2',(number,text))]
    ops.append(('Q','SELECT n = s FROM compare_values',()))
    out=scalar_batch(scalar_client,ops)
    expected=[True]*3+[None]*len(invalid)
    assert [scalar_rows(r)[0][0] for r in out[2:-1:2]] == expected
    assert sorted(scalar_rows(out[-1]),key=lambda r:str(r)) == sorted([[x] for x in expected],key=lambda r:str(r))
    exact = scalar_batch(scalar_client,[('Q','SELECT $1 = $2, $1 < $2',(9007199254740992,9007199254740993))])
    assert scalar_rows(exact[0]) == [[False,True]]


def test_conditional_and_missing_expressions(scalar_client):
    assert_scalars(scalar_client,[
        ('CASE WHEN FALSE THEN 1 WHEN NULL THEN 2 WHEN TRUE THEN 3 WHEN TRUE THEN 4 ELSE 5 END',3),
        ('CASE WHEN FALSE THEN 1 ELSE 7 END',7),('CASE WHEN NULL THEN 1 END',None),
        ('CASE 2 WHEN 1 THEN 8 WHEN 2 THEN 9 ELSE 10 END',9),
        ('CASE NULL WHEN NULL THEN 8 ELSE 10 END',10),('CASE 2 WHEN 2.0 THEN 1 ELSE 0 END',1),('NULLIF(7,7.0)',None),
        ("COALESCE(NULL, '', 'later')",''),('COALESCE(NULL, NULL, 7, 8)',7),('COALESCE(NULL,NULL)',None),
        ('NULLIF(7,7)',None),('NULLIF(7,8)',7),('NULLIF(7,NULL)',7),
        ('GREATEST(-7, 2, 9, 3)',9),('LEAST(-7, 2, 9, 3)',-7),
        ("GREATEST('a','z','m')",'z'),("LEAST('a','z','m')",'a'),
        ('GREATEST(7,NULL,9)',9),('LEAST(7,NULL,9)',7),
        ('GREATEST(NULL,NULL)',None),('LEAST(NULL,NULL)',None)])


def test_explicit_conversions(scalar_client):
    assert_scalars(scalar_client,[('CAST(7 AS FLOAT)',7.0),('CAST(2.75 AS INTEGER)',2),
        ('CAST(-2.75 AS INTEGER)',-2),("CAST('37' AS INTEGER)",37),("CAST('2.75' AS FLOAT)",2.75),
        ('CAST(37 AS TEXT)','37'),('CAST(0 AS BOOLEAN)',False),('CAST(-2 AS BOOLEAN)',True),
        ('CAST(0.5 AS BOOLEAN)',True),('CAST(-0.25 AS BOOLEAN)',True),
        ("CAST('9007199254740993' AS INTEGER)",9007199254740993),("CAST('0.1' AS FLOAT)",0.1),
        ('CAST(FALSE AS INTEGER)',0),('CAST(TRUE AS INTEGER)',1),
        ('CAST(FALSE AS FLOAT)',0.0),('CAST(TRUE AS FLOAT)',1.0),
        ("CAST('-419' AS INTEGER)",-419),("CAST('+206' AS INTEGER)",206),
        ("CAST('-1.25e2' AS FLOAT)",-125.0)] +
        [(f'CAST({sql_text(text)} AS BOOLEAN)', value)
         for text,value in [('TrUe',True),('yEs',True),('1',True),
                            ('FaLsE',False),('nO',False),('0',False)]] +
        [(f'CAST(NULL AS {kind})',None) for kind in ['INTEGER','FLOAT','TEXT','BOOLEAN','TIMESTAMP','JSON']])
    out=scalar_values(scalar_client,["CAST('2024-05-06 07:08:09' AS TIMESTAMP)","CAST('[7,true,null]' AS JSON)"])
    assert utc_instant(out[0]) == dt.datetime(2024,5,6,7,8,9,tzinfo=dt.timezone.utc)
    assert json.loads(out[1]) == [7,True,None]
    out=scalar_values(scalar_client,["CAST('2031-08-19' AS TIMESTAMP)",
        "CAST('2031-08-19T04:05:06+02:00' AS TIMESTAMP)",
        "CAST(-419 AS TEXT)","CAST(TRUE AS TEXT)","CAST(FALSE AS TEXT)",
        "CAST(CAST('2031-08-19 02:05:06' AS TIMESTAMP) AS TEXT)"])
    assert utc_instant(out[0]) == dt.datetime(2031,8,19,tzinfo=dt.timezone.utc)
    expected=dt.datetime(2031,8,19,2,5,6,tzinfo=dt.timezone.utc)
    assert utc_instant(out[1]) == expected
    assert isinstance(out[2],str) and int(out[2]) == -419
    assert all(isinstance(value,str) for value in out[3:])
    assert [value.casefold() for value in out[3:5]] == ['true','false']
    assert utc_instant(out[5]) == expected


def test_unicode_text_basics(scalar_client):
    assert_scalars(scalar_client,[("UPPER('aéΩ')",'AÉΩ'),("LOWER('AÉΩ')",'aéω'),
        ("LENGTH('a星🙂é')",4),('CHAR(128578)','🙂'),("REVERSE('a星🙂é')",'é🙂星a'),
        ("STARTS_WITH('星abc','星a')",True),("STARTS_WITH('星abc','a')",False),
        ("ENDS_WITH('abc星','c星')",True),("ENDS_WITH('abc星','b')",False),
        ("CONTAINS('a星🙂é','星🙂')",True),("CONTAINS('a星🙂é','🙂星')",False)])


def test_substring_prefix_suffix_repeat(scalar_client):
    assert_scalars(scalar_client,[("SUBSTRING('a星🙂éz',2,3)",'星🙂é'),
        ("SUBSTRING('a星🙂éz',-2,2)",'éz'),("SUBSTRING('a星🙂éz',4,-2)",'星🙂'),
        ("SUBSTRING('a星🙂éz',4,99)",'éz'),("SUBSTRING('a星🙂éz',20,3)",''),
        ("SUBSTRING('a星🙂éz',-20,3)",''),("SUBSTRING('a星🙂éz',3)",'🙂éz'),
        ("SUBSTRING('a星🙂éz',0,3)",'a星'),("SUBSTRING('a星🙂éz',2,0)",'')]+
        [(f"{op}('a星🙂', {n})",v) for op,vals in [('LEFT',['','a星','a星🙂']),('RIGHT',['','星🙂','a星🙂'])]
         for n,v in zip([0,2,20],vals)]+[("REPEAT('星a',3)",'星a星a星a'),("REPEAT('星a',0)",'')])


def test_concat_trim_replace(scalar_client):
    assert_scalars(scalar_client,[("CONCAT('a',NULL,'','星','b')",'a星b'),('CONCAT(NULL,NULL)',''),
        ("CONCAT_WS('|','a',NULL,'','星')",'a||星'),("CONCAT_WS(NULL,'a','b')",None),
        ("CONCAT_WS('|',NULL,NULL)",''),("TRIM('  a b  ')",'a b'),
        ("LTRIM('  a b  ')",'a b  '),("RTRIM('  a b  ')",'  a b'),
        ("TRIM('xyaxbxy','xy')",'axb'),("LTRIM('xyaxbxy','xy')",'axbxy'),
        ("RTRIM('xyaxbxy','xy')",'xyaxb'),("REPLACE('aaaaa','aa','星')",'星星a'),
        ("REPLACE('a星a','','z')",'a星a')])


def test_split_search_padding(scalar_client):
    assert_scalars(scalar_client,[("SPLIT_PART('a||星|','|',2)",''),("SPLIT_PART('a||星|','|',3)",'星'),
        ("SPLIT_PART('a||星|','|',8)",''),("SPLIT_PART('a星','',1)",'a星'),
        ("LOCATE('星','a星b星',3)",4),("LOCATE('b','a星b星')",3),("LOCATE('x','a星b星')",0),("LOCATE('','a星b星',3)",3),
        ("LPAD('星',6,'ab')",'ababa星'),("RPAD('星',6,'ab')",'星ababa'),
        ("LPAD('a星🙂',2,'x')",'a星'),("RPAD('a星🙂',2,'x')",'a星'),
        ("LPAD('星',3,'')",'星'),("RPAD('星',3,'')",'星'),
        ("LPAD('星',0,'x')",''),("RPAD('星',0,'x')",'')])


def test_pattern_predicates(scalar_client):
    assert_scalars(scalar_client,[("'a星c' LIKE 'a_c'",True),("'abxc' LIKE 'a_c'",False),
        ("'ac' LIKE 'a%c'",True),("'xxabcxx' LIKE 'abc'",False),
        ("'AbC' LIKE 'a%'",False),("'AbC' ILIKE 'a%'",True),("'AbC' ILIKE 'a_c'",True),("'AbCd' ILIKE 'a_c'",False),
        ("'a%c' LIKE 'a!%c' ESCAPE '!'",True),("'abc' LIKE 'a!%c' ESCAPE '!'",False),
        ("'a_c' LIKE 'a!_c' ESCAPE '!'",True),
        ("'cat7' GLOB 'c?t[0-9]'",True),("'catx' GLOB 'c?t[0-9]'",False),
        ("'cat7' GLOB 'c?t[37]'",True),("'cat7' GLOB 'c*'",True),("'Cat7' GLOB 'c*'",False),("'xcat7x' GLOB 'cat7'",False),
        ("'xxab123yy' REGEXP '(ab|cd)[0-9]+'",True),
        ("'xxab123yy' REGEXP '^(ab|cd)[0-9]+$'",False),
        ("'cd45' REGEXP '^(ab|cd)[0-9]+$'",True)])


def test_text_collations(scalar_client):
    assert_scalars(scalar_client,[("COLLATE('AbC','BINARY') = 'abc'",False),
        ("COLLATE('AbC','NOCASE') = COLLATE('abc','NOCASE')",True),
        ("COLLATE('É','NOACCENT') = COLLATE('e','NOACCENT')",False)]+
        [(f"COLLATE({sql_text(accent)},'NOACCENT') = {sql_text(plain)}",True)
         for accents,plain in [('ÀÁÂÃÄÅ','A'),('àáâãäå','a'),('ÈÉÊË','E'),('èéêë','e'),
            ('ÌÍÎÏ','I'),('ìíîï','i'),('ÒÓÔÕÖ','O'),('òóôõö','o'),('ÙÚÛÜ','U'),('ùúûü','u'),
            ('Ç','C'),('ç','c'),('Ñ','N'),('ñ','n'),('ÿ','y')]
         for accent in accents])


def test_mathematical_scalars(scalar_client):
    cases=[('ABS(-7.25)',7.25),('ROUND(2.5)',3),('ROUND(-2.5)',-3),('ROUND(1.25,1)',1.3),
           ('ROUND(-1.25,1)',-1.3),('ROUND(75,-1)',80),('TRUNCATE(-78.25,-1)',-70),
           ('TRUNCATE(7.89,1)',7.8),('FLOOR(-2.25)',-3),('CEILING(-2.25)',-2),('CEILING(2.25)',3),('POWER(9,0.5)',3),('POWER(9,1.5)',27),
           ('MOD(-17,5)',-2),('POWER(3,4)',81),('SQRT(7)',math.sqrt(7)),
           ('LOG10(7)',math.log10(7)),('LOG2(7)',math.log2(7)),('LN(7)',math.log(7)),
           ('LOG(3,7)',math.log(7,3)),('EXP(1.25)',math.exp(1.25)),('SIGN(-7)',-1),
           ('SIGN(0)',0),('SIGN(7)',1),('PI()',math.pi)]
    for x in [-1.25,0.4,2.0,40.0,-23.0]:
        for name,fun in [('SIN',math.sin),('COS',math.cos),('TAN',math.tan)]:
            cases.append((f'{name}({x})',fun(x)))
    actual=scalar_values(scalar_client,[x for x,_ in cases])
    for (expression,expected),value in zip(cases,actual):
        assert math.isfinite(value) and abs(value-expected) <= 1e-9*max(1,abs(expected)), (expression,value,expected)


def test_random_uniformity(scalar_client):
    values = scalar_values(scalar_client,['RANDOM()']*10000)
    assert_uniform(values)
    # Independent draws put consecutive pairs in each of 16 cells with probability 1/16.
    # With 5000 disjoint pairs, a 120-count deviation has a union-bound probability
    # below 1e-7 by the binomial Bernstein bound; the tolerance is deliberately broad.
    counts = [0]*16
    for a,b in zip(values[::2],values[1::2]):
        counts[int(a*4)*4+int(b*4)] += 1
    assert all(abs(n-312.5) < 120 for n in counts), counts
    fresh = scalar_values(scalar_client,['RANDOM()']*32)
    assert fresh != values[:32], 'Independent processes repeated the same random sequence'


def test_utc_and_timestamp_components(scalar_client):
    stamp="CAST('2021-01-03T23:04:05.123456+02:00' AS TIMESTAMP)"
    values=scalar_values(scalar_client,[stamp,"CAST('2021-01-03 21:04:05.123456' AS TIMESTAMP)"])
    expected=dt.datetime(2021,1,3,21,4,5,123456,tzinfo=dt.timezone.utc)
    assert [utc_instant(x) for x in values] == [expected,expected]
    components={'YEAR':2021,'QUARTER':1,'MONTH':1,'WEEK':53,'DAY':3,'DOW':0,'ISODOW':7,
                'DOY':3,'HOUR':21,'MINUTE':4,'SECOND':5,'MILLISECONDS':123,
                'MICROSECONDS':123456,'EPOCH':int(expected.timestamp())}
    actual=scalar_values(scalar_client,[f'EXTRACT({unit} FROM {stamp})' for unit in components])
    for unit,value in zip(components,actual):
        assert value == components[unit],(unit,value,components[unit])
    later = dt.datetime(2024,10,6,tzinfo=dt.timezone.utc)
    assert_scalars(scalar_client,[("EXTRACT(QUARTER FROM CAST('2024-10-06' AS TIMESTAMP))",4),
        ("EXTRACT(DOY FROM CAST('2024-10-06' AS TIMESTAMP))",later.timetuple().tm_yday)])


def test_current_clock_refresh(scalar_client):
    sql='SELECT CURRENT_DATE, CURRENT_TIME, CURRENT_TIMESTAMP'
    out=scalar_batch(scalar_client,[('Q',sql,()),('S','1200',()),('Q',sql,())])
    for observation in (out[0],out[2]):
        date,time,timestamp=scalar_rows(observation)[0]
        before,after=observation['window']
        low=dt.datetime.fromtimestamp(before,dt.timezone.utc)
        high=dt.datetime.fromtimestamp(after,dt.timezone.utc)
        assert low.date() <= utc_instant(date).date() <= high.date()
        clock=dt.time.fromisoformat(time)
        candidates=[dt.datetime.combine(day,clock,tzinfo=dt.timezone.utc).timestamp() for day in [low.date(),high.date()]]
        assert any(math.floor(before) <= value <= after for value in candidates), observation
        assert math.floor(before * 1e6) / 1e6 <= utc_instant(timestamp).timestamp() <= after, observation


def test_calendar_and_duration_truncation(scalar_client):
    stamp="CAST('2024-05-19 17:38:49.123456' AS TIMESTAMP)"
    expected=['2024-01-01','2024-04-01','2024-05-01','2024-05-13','2024-05-19',
              '2024-05-19T17:00:00','2024-05-19T17:38:00','2024-05-19T17:38:49']
    values=scalar_values(scalar_client,[f'DATE_TRUNC({sql_text(unit)}, {stamp})' for unit in
                          ['year','quarter','month','week','day','hour','minute','second']])
    for value,target in zip(values,expected):
        assert utc_instant(value) == dt.datetime.fromisoformat(target).replace(tzinfo=dt.timezone.utc)
    epoch=dt.datetime(1970,1,1,tzinfo=dt.timezone.utc)
    source=dt.datetime(2024,5,19,17,38,49,123456,tzinfo=dt.timezone.utc)
    ns=((source-epoch).days*86400+(source-epoch).seconds)*10**9+source.microsecond*1000
    buckets=[('1h',3600*10**9),('17m',1020*10**9),('13s',13*10**9),('7ms',7000000),
             ('11us',11000),('1000ns',1000),('1h2m3s4ms5us',3723004005000),('24h',86400*10**9)]
    values=scalar_values(scalar_client,[f'TIME_TRUNC({sql_text(text)}, {stamp})' for text,_ in buckets])
    for value,(text,size) in zip(values,buckets):
        # These supplied buckets are microsecond-exact; compare instants, not formatting.
        target=epoch+dt.timedelta(microseconds=(ns//size*size)//1000)
        assert utc_instant(value)==target,(text,value,target)
    for stamp, ns in [('1970-01-01 00:00:00.000000019',19),
                      ('2099-12-31 23:59:59.123456789',4102444799123456789)]:
        sizes=[('1ns',1),('17ns',17),('2s3ms5us7ns',2003005007)]
        actual=scalar_values(scalar_client,[f"TIME_TRUNC('{unit}',CAST('{stamp}' AS TIMESTAMP))" for unit,_ in sizes])
        for value,(_,size) in zip(actual,sizes):
            assert utc_nanoseconds(value)==ns//size*size



def test_calendar_arithmetic_and_intervals(scalar_client):
    cases=[("DATE_ADD('2024-03-31',1,'month')",'2024-04-30'),
           ("DATE_ADD('2024-01-31',1,'month')",'2024-02-29'),
           ("DATE_SUB('2024-03-31',1,'month')",'2024-02-29'),
           ("DATE_ADD('2024-02-29',1,'year')",'2025-02-28'),
           ("DATE_SUB('2024-02-29',1,'year')",'2023-02-28')]
    base=dt.datetime(2024,1,15,12,34,56,tzinfo=dt.timezone.utc)
    for unit,seconds in [('week',604800),('day',86400),('hour',3600),('minute',60),('second',1)]:
        for function,sign in [('DATE_ADD',1),('DATE_SUB',-1)]:
            cases.append((f"{function}('2024-01-15 12:34:56',2,'{unit}')",(base+dt.timedelta(seconds=sign*2*seconds)).isoformat()))
    for unit,seconds in [('second',1),('minute',60),('hour',3600),('day',86400),('week',604800)]:
        for op,sign in [('+',1),('-',-1)]:
            target = base + dt.timedelta(seconds=sign*2*seconds)
            cases.append((f"CAST('2024-01-15 12:34:56' AS TIMESTAMP) {op} INTERVAL '2 {unit}'",target.isoformat()))
    for unit in ['month', 'year']:
        for op, sign in [('+', 1), ('-', -1)]:
            target = (base.replace(year=2024 if sign == 1 else 2023, month=3 if sign == 1 else 11)
                      if unit == 'month' else base.replace(year=2024 + sign*2))
            cases.append((f"CAST('2024-01-15 12:34:56' AS TIMESTAMP) {op} INTERVAL '2 {unit}'", target.isoformat()))
    cases += [("CAST('2024-01-31 12:34:56' AS TIMESTAMP) + INTERVAL '1 month'", '2024-02-29T12:34:56'),
              ("CAST('2024-02-29 12:34:56' AS TIMESTAMP) + INTERVAL '1 year'", '2025-02-28T12:34:56')]
    values=scalar_values(scalar_client,[x for x,_ in cases])
    for (expr,target),value in zip(cases,values):
        parsed=dt.datetime.fromisoformat(target)
        if parsed.tzinfo is None: parsed=parsed.replace(tzinfo=dt.timezone.utc)
        assert utc_instant(value)==parsed,(expr,value,target)
    assert_scalars(scalar_client,[("DATEDIFF('2024-05-03 11:00:00','2024-05-01 12:00:00')",1),
                                 ("DATEDIFF('2024-05-01 12:00:00','2024-05-03 11:00:00')",-1)])


def test_json_values_and_paths(scalar_client):
    document='{"items":["星",7,true,null,{"k":"v"}],"empty":[],"obj":{"a":1,"b":2}}'
    d=sql_text(document)
    values=scalar_values(scalar_client,["JSON_ARRAY('星',7,TRUE,NULL)","JSON_OBJECT('z',7,'a','星')",
        f"JSON_EXTRACT({d},'$.items[4]')",f"CAST({d} AS JSON) -> 'items' -> 0",
        f"JSON_KEYS({d})"])
    assert [json.loads(x) for x in values[:4]] == [['星',7,True,None],{'z':7,'a':'星'},{'k':'v'},'星']
    assert set(json.loads(values[4])) == {'items','empty','obj'}
    extracted=scalar_batch(scalar_client,[('Q',f"SELECT CAST({d} AS JSON) -> 'items' -> 3, CAST({d} AS JSON) -> 'missing'",())])[0]
    assert extracted['rows'][0][0][0] == 'j'
    assert json.loads(extracted['rows'][0][0][1]) is None
    assert extracted['rows'][0][1] == ('n',None)
    cases=[(f"(CAST({d} AS JSON) -> 'items') ->> 0",'星'),(f"JSON_EXTRACT({d},'$.absent')",None),
           (f"JSON_ARRAY_LENGTH({d},'$.items')",5),("JSON_ARRAY_LENGTH('[1,null,3]')",3),
           (f"JSON_VALID({d})",1),("JSON_VALID('{bad')",0),("JSON_VALID('{bad}')",0),("JSON_VALID('[1,,2]')",0),
           ("JSON_EXTRACT('{\"a\":{\"b\":{\"c\":{\"value\":19}}}}', '$.a.b.c')",'{\"value\":19}')]
    deep = cases.pop()
    assert json.loads(scalar_values(scalar_client,[deep[0]])[0]) == {'value':19}
    for path,kind in [('$','object'),('$.items','array'),('$.items[0]','string'),
                      ('$.items[1]','number'),('$.items[2]','boolean'),('$.items[3]','null')]:
        cases.append((f'JSON_TYPE({d},{sql_text(path)})',kind))
    assert_scalars(scalar_client,cases)


def test_standard_text_digests(scalar_client):
    cases=[]
    for text in ['', 'abc', '星🙂é\norder', 'x'*257+'end']:
        for sql_name, algorithm in [('MD5','md5'),('SHA1','sha1'),('SHA256','sha256'),('SHA384','sha384'),('SHA512','sha512')]:
            cases.append((f'{sql_name}({sql_text(text)})',hashlib.new(algorithm,text.encode('utf-8')).hexdigest()))
        cases.append((f'CRC32({sql_text(text)})',zlib.crc32(text.encode('utf-8'))))
    cases += [(name+'(NULL)',None) for name in ['MD5','SHA1','SHA256','SHA384','SHA512','CRC32']]
    assert_scalars(scalar_client,cases)


def test_caller_selected_formatting(scalar_client):
    assert_scalars(scalar_client,[("TO_CHAR(12345.678,'999999.99')",'12345.68'),
        ("TO_CHAR(12345.678,'999999.9')",'12345.7'),("TO_CHAR(1234567,'9,999,999')",'1,234,567'),
        ("TO_CHAR('2024-03-15 14:30:45.123','YYYY-MM-DD HH24:MI:SS.MS')",'2024-03-15 14:30:45.123'),
        ("TO_CHAR('2024-03-15 14:30:45','DD MON YYYY HH12:MI AM')",'15 MAR 2024 02:30 PM'),
        ("TO_CHAR('2024-03-15','MONTH DAY DY')",'MARCH FRIDAY FRI'),
        ("TO_CHAR('2024-03-15 12:30:00','HH12:MI AM')",'12:30 PM'),
        ("TO_CHAR(NULL,'YYYY-MM-DD')",None),("TO_CHAR(NULL,'999.99')",None)])


def test_invalid_scalar_operations(scalar_client):
    value = scalar_values(scalar_client, ['ABS(-3)'])[0]
    assert type(value) in (int, float) and abs(value - 3) <= 3e-9, value
    assert_scalars(scalar_client,[("'abc' REGEXP 'a.*'",True),
        ('CAST(3 AS TEXT)','3'),("COLLATE('a','BINARY')",'a')])
    for result in scalar_batch(scalar_client,[('Q',sql,()) for sql in [
        "SELECT 'abc' REGEXP '['",'SELECT nonexistent_scalar(3)']]):
        assert 'error' in result, result


def test_invalid_conversions_and_json_writes(scalar_client):
    out=scalar_batch(scalar_client,[('E','CREATE TABLE documents (id INTEGER, body JSON)',()),
        ('E','INSERT INTO documents VALUES (1,$1)',('{"ok":7}',)),
        ('E','INSERT INTO documents VALUES (2,$1)',('{broken}',)),
        ('E','UPDATE documents SET body = $1 WHERE id = 1',('[1,,2]',)),
        ('Q','SELECT id, body FROM documents',())])
    assert 'affected' in out[0] and out[1].get('affected') == 1,out
    assert 'error' in out[2] and 'error' in out[3],out
    rows=scalar_rows(out[4]); assert len(rows)==1 and rows[0][0]==1
    assert json.loads(rows[0][1]) == {'ok':7}
