# feature: F18
"""Bulk-import fixtures using the earlier native SQL transport and observations."""
import csv
import io
import json
import pytest
from _helpers import parse_json, rows_equal
from F01_helpers import build_rust_client
from F02_helpers import SCALAR_CLIENT, sql_text, utc_instant, scalar_rows


@pytest.fixture(scope='module')
def import_client(tmp_path_factory):
    return build_rust_client(SCALAR_CLIENT, tmp_path_factory.mktemp('f18-rust'))


def import_file(directory, name, contents):
    path = directory / name
    path.write_text(contents, encoding='utf-8')
    return path


def copy_statement(table, path, options, columns=''):
    return f'COPY {table} {columns} FROM {sql_text(str(path))} WITH ({options})'


IMPORT_SCHEMA = ('CREATE TABLE items(id INTEGER PRIMARY KEY, name TEXT, '
                 'amount INTEGER DEFAULT 23, score FLOAT, enabled BOOLEAN, '
                 'stamp TIMESTAMP, doc JSON, v VECTOR(3))')
IMPORT_READ = ('SELECT id,name,amount,score,enabled,stamp,doc,VEC_TO_TEXT(v) '
               'FROM items ORDER BY id')


def import_rows(observation, expected):
    """Check native scalar types and compare parsed structured payloads, not layout."""
    assert 'rows' in observation, observation
    actual = []
    tags = ('i', 's', 'i', 'f', 'b', 't', 'j', 's')
    for row in observation['rows']:
        assert len(row) == len(tags), row
        decoded = []
        for position, ((tag, value), required_tag) in enumerate(zip(row, tags)):
            if tag == 'n':
                assert value is None
            else:
                assert tag == required_tag, (position, tag, required_tag)
                if position == 5:
                    value = utc_instant(value)
                elif position in (6, 7):
                    value = parse_json(value)
            decoded.append(value)
        actual.append(decoded)
    # JSON numeric spelling and vector text precision are not pinned.
    assert actual == expected, (actual, expected)
    for got, want in zip(actual, expected):
        assert rows_equal([got[:5]], [want[:5]], ordered=True), (got, want)
        assert json_semantic_key(got[6]) == json_semantic_key(parse_json(json.dumps(want[6]))), (got, want)


def import_document(fmt, keys, rows):
    """Serialize real input records without making any product observation."""
    if fmt == 'JSON':
        return '\n'.join(json.dumps(dict(zip(keys, row))) for row in rows) + '\n'
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue()


def import_constraint_state(observation, expected):
    rows = scalar_rows(observation)
    assert len(rows) == len(expected), (rows, expected)
    for actual, wanted in zip(rows, expected):
        assert rows_equal([actual[:5]], [wanted[:5]], ordered=True), (actual, wanted)
        assert parse_json(actual[5]) == parse_json(wanted[5]), (actual, wanted)


def json_semantic_key(value):
    """Preserve JSON families while treating equivalent numeric spellings alike."""
    from decimal import Decimal
    if value is None:
        return ('null',)
    if isinstance(value, bool):
        return ('boolean', value)
    if isinstance(value, (int, Decimal)):
        return ('number', value)
    if isinstance(value, str):
        return ('string', value)
    if isinstance(value, list):
        return ('array', tuple(json_semantic_key(item) for item in value))
    if isinstance(value, dict):
        return ('object', frozenset((key,json_semantic_key(item)) for key,item in value.items()))
    raise TypeError(f'Unexpected JSON value: {value!r}')
