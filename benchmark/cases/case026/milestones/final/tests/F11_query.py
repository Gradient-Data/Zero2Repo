# feature: F11
"""Acceptance tests for ordinary HTTP querying, using real public entries."""

from decimal import Decimal

import pytest

from F11_helpers import (
    assert_http_row_bag, http_query_error, http_query_rows, run_http_query_scenario,
)


def test_http_selection_join_aggregate_and_json_values(tmp_path):
    observations = run_http_query_scenario(tmp_path, r'''
        record Reading(String label, Object value, Boolean active, String note) {}
        var schema = Schema.<Reading>builder().column("label",Reading::label)
            .column("value",Reading::value).column("active",Reading::active)
            .column("note",Reading::note).build();
        try (var routeMap = VelqoraMap.<String,String>memory()) {
            Map<String,Reading> readings = new LinkedHashMap<>();
            readings.put("a",new Reading("zebra",12L,true,"汉字 🙂 \" \\ \b\f\n\r\t"+(char)1));
            readings.put("b",new Reading("apple",-2.5d,false,null));
            readings.put("c",new Reading("middle",null,null,"plain"));
            Map<String,String> links = Map.of("first","a","second","a","third","b","orphan","missing");
            var catalog = new Catalog().add("readings",readings,schema)
                .add("links",links,Schema.<String>builder().column("target",v->v).build());
            try (var server = VelqoraMapHttpServer.builder(routeMap,TEXT,TEXT)
                    .queries(new QueryEngine(catalog)).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                queryReport(server,"selection","SELECT _key AS id, label AS label, value AS value, "
                    +"active AS active, note AS note FROM readings");
                queryReport(server,"filter","SELECT _key AS id, value AS value FROM readings "
                    +"WHERE value >= :minimum ORDER BY value DESC LIMIT 1","minimum","-3.0");
                queryReport(server,"joined","SELECT r.label AS label, r.value AS value FROM readings r "
                    +"JOIN links l ON l.target = r._key");
                queryReport(server,"summaries","SELECT COUNT(*) AS count, COUNT(r.value) AS present, "
                    +"SUM(r.value) AS total, AVG(r.value) AS mean, MIN(r.value) AS least, "
                    +"MAX(r.value) AS greatest FROM readings r JOIN links l ON l.target = r._key");
                queryReport(server,"nullable_summaries","SELECT COUNT(*) AS count, COUNT(value) AS present, "
                    +"SUM(value) AS total, AVG(value) AS mean, MIN(value) AS least, MAX(value) AS greatest FROM readings");
                queryReport(server,"empty_summaries","SELECT COUNT(*) AS count, COUNT(value) AS present, "
                    +"SUM(value) AS total, AVG(value) AS mean, MIN(value) AS least, MAX(value) AS greatest "
                    +"FROM readings WHERE label = :missing","missing","absent");
                queryReport(server,"groups","SELECT r.label AS label, COUNT(*) AS count FROM readings r "
                    +"JOIN links l ON l.target = r._key GROUP BY r.label ORDER BY count DESC");
                queryReport(server,"text_extrema","SELECT MIN(label) AS least, MAX(label) AS greatest FROM readings");
                queryReport(server,"default_order","SELECT label AS label FROM readings ORDER BY label");
                queryReport(server,"ascending_prefix","SELECT _key AS id, value AS value FROM readings "
                    +"WHERE value >= :minimum ORDER BY value ASC LIMIT 1","minimum","-3.0");
                queryReport(server,"mixed_order","SELECT r.label AS label, l._key AS link FROM readings r "
                    +"JOIN links l ON l.target = r._key ORDER BY label ASC, link DESC");
                queryReport(server,"empty","SELECT _key AS id FROM readings WHERE label = :label","label","absent");
                readings.put("precise",new Reading("precision",1.0 + Math.scalb(1.0,-30),true,null));
                queryReport(server,"precise","SELECT value AS value FROM readings WHERE _key = 'precise'");
                readings.put("a",new Reading("updated",37L,false,"changed"));
                queryReport(server,"updated","SELECT label AS label, value AS value FROM readings WHERE _key = :key","key","a");
            }
        }
    ''')
    found = {item['tag']: http_query_rows(item) for item in observations}
    assert_http_row_bag(found['selection'], [
        {'id': 'a', 'label': 'zebra', 'value': 12, 'active': True,
         'note': '汉字 🙂 " \\ \b\f\n\r\t\x01'},
        {'id': 'b', 'label': 'apple', 'value': -2.5, 'active': False, 'note': None},
        {'id': 'c', 'label': 'middle', 'value': None, 'active': None, 'note': 'plain'},
    ])
    assert_http_row_bag(found['filter'], [{'id': 'a', 'value': 12}])
    assert_http_row_bag(found['joined'], [
        {'label': 'zebra', 'value': 12}, {'label': 'zebra', 'value': 12},
        {'label': 'apple', 'value': -2.5},
    ])
    assert len(found['summaries']) == 1
    summary = found['summaries'][0]
    assert set(summary) == {'count', 'present', 'total', 'mean', 'least', 'greatest'}
    assert_http_row_bag([{k: summary[k] for k in ('count', 'present', 'least', 'greatest')}],
                        [{'count': 3, 'present': 3, 'least': -2.5, 'greatest': 12}])
    # FP-08.04: absolute errors scale with the input magnitude, not JSON spelling.
    for field, expected, divisor in [('total', 21.5, 1), ('mean', 21.5 / 3, 3)]:
        assert type(summary[field]) in (int, float, Decimal)
        assert float(summary[field]) == pytest.approx(expected, rel=0, abs=max(1e-12, 26.5e-9 / divisor))
    nullable = found['nullable_summaries']
    assert len(nullable) == 1
    assert set(nullable[0]) == {'count', 'present', 'total', 'mean', 'least', 'greatest'}
    assert_http_row_bag([{k: nullable[0][k] for k in ('count', 'present', 'least', 'greatest')}],
                        [{'count': 3, 'present': 2, 'least': -2.5, 'greatest': 12}])
    for field, expected, divisor in [('total', 9.5, 1), ('mean', 4.75, 2)]:
        assert type(nullable[0][field]) in (int, float, Decimal)
        assert float(nullable[0][field]) == pytest.approx(expected, rel=0, abs=max(1e-12, 14.5e-9 / divisor))
    assert_http_row_bag(found['empty_summaries'], [
        {'count': 0, 'present': 0, 'total': None, 'mean': None, 'least': None, 'greatest': None}])
    assert_http_row_bag(found['groups'], [{'label': 'zebra', 'count': 2}, {'label': 'apple', 'count': 1}])
    assert [row['label'] for row in found['groups']] == ['zebra', 'apple']
    assert_http_row_bag(found['text_extrema'], [{'least': 'apple', 'greatest': 'zebra'}])
    # FP-06.01/06.04 carried by FP-11.01: ascending is the default and ASC; ordered limits take the prefix.
    assert [row['label'] for row in found['default_order']] == ['apple', 'middle', 'zebra']
    assert_http_row_bag(found['ascending_prefix'], [{'id': 'b', 'value': -2.5}])
    assert [(row['label'], row['link']) for row in found['mixed_order']] == [
        ('apple', 'third'), ('zebra', 'second'), ('zebra', 'first')]
    assert found['empty'] == []
    assert_http_row_bag(found['updated'], [{'label': 'updated', 'value': 37}])
    assert_http_row_bag(found['precise'], [{'value': 1.0 + 2.0**-30}])


def test_http_scalar_text_bindings(tmp_path):
    observations = run_http_query_scenario(tmp_path, r'''
        try (var routeMap = VelqoraMap.<String,String>memory()) {
            Map<String,Cell> cells = new LinkedHashMap<>();
            String[] names = {"null","true","false","positive","negative","zero","fraction","negative_fraction","precise_fraction"};
            String[] inputs = {"null","true","false","42","-17","0","3.125","-4.5","1.000000000931322574615478515625"};
            Object[] values = {null,true,false,42L,-17L,0L,3.125d,-4.5d,1.0 + Math.scalb(1.0,-30)};
            for (int i=0;i<names.length;i++) {
                cells.put(names[i],new Cell(values[i]));
                cells.put("text_"+names[i],new Cell(inputs[i]));
            }
            String[] text = {"", "hello 汉字 🙂 & = + %", "+42", "1e3", ".5", "5.", "NaN", "Infinity", "trueish"};
            for (int i=0;i<text.length;i++) cells.put("string_"+i,new Cell(text[i]));
            var engine = new QueryEngine(new Catalog().add("cells",cells,cellSchema()));
            try (var server = VelqoraMapHttpServer.builder(routeMap,TEXT,TEXT).queries(engine).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                String sql = "SELECT _key AS id, value AS value FROM cells WHERE value = :needle";
                for (int i=0;i<names.length;i++) queryReport(server,names[i],sql,"needle",inputs[i]);
                for (int i=0;i<text.length;i++) queryReport(server,"string_"+i,sql,"needle",text[i]);
                // Several named bindings in one request; every one is applied.
                String pair = "SELECT _key AS id, value AS value FROM cells WHERE _key = :name OR _key = :other";
                queryReport(server,"pair",pair,"name","positive","other","negative_fraction");
                queryReport(server,"pair_reversed",pair,"other","positive","name","negative_fraction");
                queryReport(server,"three","SELECT _key AS id, value AS value FROM cells "
                    +"WHERE _key = :first OR _key = :second OR value = :third",
                    "first","positive","second","zero","third","-4.5");
            }
        }
    ''')
    expected = dict(zip(
        ['null', 'true', 'false', 'positive', 'negative', 'zero', 'fraction', 'negative_fraction', 'precise_fraction'],
        [None, True, False, 42, -17, 0, 3.125, -4.5, 1.0 + 2.0**-30],
    ))
    expected.update({f'string_{i}': value for i, value in enumerate(
        ['', 'hello 汉字 🙂 & = + %', '+42', '1e3', '.5', '5.', 'NaN', 'Infinity', 'trueish'])})
    combined = {
        'pair': ['positive', 'negative_fraction'],
        'pair_reversed': ['positive', 'negative_fraction'],
        'three': ['positive', 'zero', 'negative_fraction'],
    }
    assert len(observations) == len(expected) + len(combined)
    for item in observations:
        if item['tag'] in combined:
            assert_http_row_bag(http_query_rows(item),
                                [{'id': name, 'value': expected[name]} for name in combined[item['tag']]])
        else:
            assert_http_row_bag(http_query_rows(item), [{'id': item['tag'], 'value': expected[item['tag']]}])


def test_http_integer_binding_boundaries_and_refusal(tmp_path):
    observations = run_http_query_scenario(tmp_path, r'''
        try (var routeMap = VelqoraMap.<String,String>memory()) {
            Map<String,Cell> cells = Map.of("lower",new Cell(Long.MIN_VALUE),
                "upper",new Cell(Long.MAX_VALUE),"zero",new Cell(0L));
            var engine = new QueryEngine(new Catalog().add("cells",cells,cellSchema()));
            try (var server = VelqoraMapHttpServer.builder(routeMap,TEXT,TEXT).queries(engine).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                String sql = "SELECT _key AS id, value AS value FROM cells WHERE value = :value";
                queryReport(server,"lower",sql,"value","-9223372036854775808");
                queryReport(server,"upper",sql,"value","9223372036854775807");
                for (String value : List.of("-9223372036854775809","9223372036854775808"))
                    error(server,"POST","/query?value="+value,utf(sql),400);
                queryReport(server,"zero",sql,"value","0");
            }
        }
    ''')
    expected = {'lower': -(2**63), 'upper': 2**63 - 1, 'zero': 0}
    assert len(observations) == 5
    for item in observations:
        if item['tag'] == 'error':
            http_query_error(item)
        else:
            assert_http_row_bag(http_query_rows(item), [{'id': item['tag'], 'value': expected[item['tag']]}])


def test_http_query_configuration_and_malformed_requests(tmp_path):
    observations = run_http_query_scenario(tmp_path, r'''
        for (boolean configured : new boolean[]{false,true}) {
            try (var map = VelqoraMap.<String,String>memory()) {
                map.put("key","working");
                var builder = VelqoraMapHttpServer.builder(map,TEXT,TEXT).address(new InetSocketAddress("127.0.0.1",0));
                if (configured) builder.queries(textEngine(map));
                try (var server = builder.build().start()) {
                    String valid = "SELECT value AS result FROM items";
                    if (configured) queryReport(server,"live",valid);
                    else error(server,"POST","/query",utf(valid),400);
                    for (String invalid : List.of("not a query", "SELECT value FROM items WHERE value = 'unfinished"))
                        error(server,"POST","/query",utf(invalid),400);
                    if (configured) queryReport(server,"still_live",valid);
                    else {
                        // "Regardless of the query text": text whose analysis would be costly
                        // (deeply nested predicate), an empty body, and bindings are refused alike.
                        int depth = 15000; // about 30 KB of text
                        String nested = "SELECT value AS result FROM items WHERE "
                            +"(".repeat(depth)+"value = 'working'"+")".repeat(depth);
                        error(server,"POST","/query",utf(nested),400);
                        error(server,"POST","/query",new byte[0],400);
                        error(server,"POST","/query?wanted=working",
                            utf("SELECT value AS result FROM items WHERE value = :wanted"),400);
                    }
                }
            }
        }
    ''')
    assert len(observations) == 10
    for item in observations:
        if item['tag'] == 'error':
            http_query_error(item)
        else:
            assert_http_row_bag(http_query_rows(item), [{'result': 'working'}])
    # Missing configuration and malformed text share the same public carrier.
    # These are refusals through that carrier; diagnostic cause ordering is not asserted.


def test_http_map_routes_and_query_catalog_are_independent(tmp_path):
    observations = run_http_query_scenario(tmp_path, r'''
        try (var map = VelqoraMap.<String,String>memory(); var routeOnly = VelqoraMap.<String,String>memory()) {
            map.put("key","shared-data");
            routeOnly.put("key","route-only-data");
            var engine = new QueryEngine(new Catalog().add("catalog_name",map,
                Schema.<String>builder().column("value",v->v).build()));
            try (var server = VelqoraMapHttpServer.builder().map("record_name",map,TEXT,TEXT)
                    .map("route_only",routeOnly,TEXT,TEXT).queries(engine).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                bytes(utf("shared-data"),status(server,"GET",path("/maps/record_name",utf("key")),new byte[0],200).body());
                bytes(utf("route-only-data"),status(server,"GET",path("/maps/route_only",utf("key")),new byte[0],200).body());
                queryReport(server,"catalog","SELECT _key AS id, value AS value FROM catalog_name");
                for (String name : List.of("record_name","route_only"))
                    error(server,"POST","/query",utf("SELECT * FROM "+name),400);
                status(server,"PUT",path("/maps/record_name",utf("key")),utf("changed-via-http"),204);
                queryReport(server,"changed","SELECT _key AS id, value AS value FROM catalog_name");
            }
        }
    ''')
    assert len(observations) == 4
    for item in observations:
        if item['tag'] == 'error':
            http_query_error(item)
        else:
            value = 'shared-data' if item['tag'] == 'catalog' else 'changed-via-http'
            assert_http_row_bag(http_query_rows(item), [{'id': 'key', 'value': value}])
