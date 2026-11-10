# feature: F11
"""HTTP query observations using the earlier feature's live server driver."""

import json
from decimal import Decimal

from _helpers import parse_json
from F10_helpers import run_http_scenario


HTTP_QUERY_MEMBERS = r'''
    record Cell(Object value) {}
    static Schema<Cell> cellSchema() {
        return Schema.<Cell>builder().column("value", Cell::value).build();
    }
    static void queryReport(VelqoraMapHttpServer<?,?> server, String tag, String sql,
                            String... bindings) throws Exception {
        if (bindings.length % 2 != 0) throw new AssertionError("Unpaired binding");
        StringJoiner parameters = new StringJoiner("&");
        for (int i=0; i<bindings.length; i+=2)
            parameters.add(URLEncoder.encode(bindings[i],StandardCharsets.UTF_8)+"="
                +URLEncoder.encode(bindings[i+1],StandardCharsets.UTF_8));
        String route = "/query" + (bindings.length == 0 ? "" : "?"+parameters);
        report(tag,status(server,"POST",route,utf(sql),200));
    }
'''


def run_http_query_scenario(tmp_path, body, *, members=''):
    return run_http_scenario(tmp_path, body, members=HTTP_QUERY_MEMBERS + members)


def http_query_rows(observation):
    assert observation['status'] == 200, observation
    # Reuse strict UTF-8/JSON validation, then retain exact decimal numbers.
    # A signed integer written with a decimal point must not lose precision.
    parse_json(observation['body'])
    rows = json.loads(observation['body'].decode('utf-8'), parse_float=Decimal)['rows']
    assert isinstance(rows, list), observation
    assert all(isinstance(row, dict) for row in rows), observation
    return rows


def http_query_error(observation):
    assert observation['status'] == 400, observation
    payload = parse_json(observation['body'])
    assert isinstance(payload['error'], str) and payload['error'], observation
    # The original has no category field; do not classify its diagnostic prose.


def _json_meaning_equal(actual, expected):
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and actual.keys() == expected.keys()
                and all(_json_meaning_equal(actual[k], v) for k, v in expected.items()))
    if isinstance(expected, bool) or expected is None:
        return actual is expected
    if isinstance(expected, float):
        return type(actual) in (int, float, Decimal) and float(actual) == expected
    if isinstance(expected, int):
        return type(actual) in (int, float, Decimal) and actual == expected
    return type(actual) is type(expected) and actual == expected


def assert_http_row_bag(actual, expected):
    """Compare JSON meanings and multiplicities without fixing row or field order."""
    remaining = list(actual)
    for wanted in expected:
        for index, row in enumerate(remaining):
            if _json_meaning_equal(row, wanted):
                remaining.pop(index)
                break
        else:
            raise AssertionError(f'Missing row {wanted!r}; remaining rows: {remaining!r}')
    assert not remaining, f'Unexpected rows: {remaining!r}'
