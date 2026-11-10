# feature: F13
"""The seven planned acceptance checks for typed node-query interchange."""

import io
import math
import struct

from _helpers import parse_json
from F05_helpers import run_query_scenario
from F10_helpers import read_scalar_wire, read_rows_wire, run_http_scenario
from F13_helpers import (
    scalar_wire, rows_wire, java_wire, run_interchange, SCAN_OBSERVATIONS, read_typed_rows,
)


def test_scalar_types_values_and_independent_interchange(tmp_path):
    # Each supported type has an independent wire input and a typed Java value.
    vectors = [
        (0, None, 'null'),
        (1, '', '""'), (1, 'Nul\0水🧭\n', '"Nul\\u0000水🧭\\n"'),
        (2, False, 'false'), (2, True, 'true'),
        (3, -128, '(byte)-128'), (3, 127, '(byte)127'),
        (4, -32768, '(short)-32768'), (4, 32767, '(short)32767'),
        (5, -2147483648, 'Integer.MIN_VALUE'), (5, 2147483647, 'Integer.MAX_VALUE'),
        (6, -9223372036854775808, 'Long.MIN_VALUE'), (6, 9223372036854775807, 'Long.MAX_VALUE'),
        (7, -13.25, '-13.25f'), (7, -0.0, '-0.0f'),
        (7, float('inf'), 'Float.POSITIVE_INFINITY'), (7, float('nan'), 'Float.NaN'),
        (7, 0.1, '0.1f'), (7, 1.401298464324817e-45, 'Float.MIN_VALUE'),
        (8, 981.125, '981.125d'), (8, -0.0, '-0.0d'),
        # Finite doubles that no 32-bit float represents exactly.
        (8, 0.1, '0.1d'), (8, -1.0000000000000002, '-1.0000000000000002d'),
        (8, 1e300, '1.0E300d'), (8, 5e-324, 'Double.MIN_VALUE'),
        (8, float('-inf'), 'Double.NEGATIVE_INFINITY'), (8, float('nan'), 'Double.NaN'),
        (9, b'', 'new byte[0]'), (9, bytes([0, 255, 128, 7]), 'new byte[]{0,-1,-128,7}'),
        (10, '\0', "'\\u0000'"), (10, '水', "'水'"), (10, '\uffff', "'\\uffff'"),
    ]
    calls = []
    for index, (tag, value, java_value) in enumerate(vectors):
        calls.append('''{
            Object expected = %s;
            scalarEqual(expected,BinaryScalar.decode(%s));
            byte[] encoded = BinaryScalar.encode(expected);
            scalarEqual(expected,BinaryScalar.decode(encoded));
            wireReport("%s",encoded);
        }''' % (java_value, java_wire(scalar_wire(tag, value)), index))
    calls.append('''
        for (Object unsupported : List.of(new Object(),List.of(1),Map.of("x",1),new java.math.BigDecimal("2.1")))
            rejects(IllegalArgumentException.class,()->BinaryScalar.encode(unsupported));
    ''')
    observed = run_interchange(tmp_path, '\n'.join(calls))
    assert len(observed) == len(vectors)
    for index, item in enumerate(observed):
        assert item['tag'] == str(index)
        tag, expected, _ = vectors[index]
        if tag == 7 and isinstance(expected, float):
            expected = struct.unpack('>f', struct.pack('>f', expected))[0]
        assert item['body'][0] == tag
        stream = io.BytesIO(item['body'])
        actual = read_scalar_wire(stream)
        assert stream.read() == b''
        if isinstance(expected, float) and math.isnan(expected):
            assert math.isnan(actual)  # Any legal NaN payload is accepted.
        else:
            assert actual == expected
            if isinstance(expected, float) and expected == 0:
                assert math.copysign(1, actual) == math.copysign(1, expected)


def test_row_sequence_fields_and_empty_interchange(tmp_path):
    rows = [[('right', 9, b'\0\xff'), ('left', 1, 'first水'), ('empty', 0, None)],
            [], [('right', 5, -71), ('left', 1, 'last')],
            [('right', 5, -71), ('left', 1, 'last')],
            [('bool', 2, False), ('byte', 3, -17), ('short', 4, 4000),
             ('long', 6, 5000000001), ('float', 7, -1.25), ('double', 8, 0.1),
             ('character', 10, 'Ω')]]
    observed = run_interchange(tmp_path, r'''
        Map<String,Object> first = new LinkedHashMap<>();
        first.put("left","first水"); first.put("right",new byte[]{0,-1}); first.put("empty",null);
        var expected = List.of(first,Map.<String,Object>of(),
            Map.<String,Object>of("left","last","right",-71),Map.<String,Object>of("left","last","right",-71),
            Map.<String,Object>of("bool",false,"byte",(byte)-17,"short",(short)4000,
                "long",5000000001L,"float",-1.25f,"double",0.1d,"character",'Ω'));
        rowSequenceEqual(expected,consumeRows(INDEPENDENT));
        for (var sequence : List.of(expected,List.<Map<String,Object>>of())) {
            var output = new ByteArrayOutputStream();
            new BinaryRowStream().write(output,sequence);
            rowSequenceEqual(sequence,consumeRows(output.toByteArray()));
            wireReport("rows",output.toByteArray());
        }
        rowSequenceEqual(List.of(),consumeRows(new byte[]{0}));
        rejects(IOException.class,()->new BinaryRowStream().write(new ByteArrayOutputStream(),
            List.of(Map.of("unsupported",new Object()))));
    '''.replace('INDEPENDENT', java_wire(rows_wire(rows))))
    expected = [{name: value for name, _, value in row} for row in rows]
    assert len(observed) == 2
    assert read_rows_wire(observed[0]['body']) == expected
    assert read_rows_wire(observed[1]['body']) == []


def test_stream_failures_and_complete_scalar_size_boundary(tmp_path):
    complete = rows_wire([[('item', 1, 'complete')], [('count', 6, 10000000007)]])
    run_interchange(tmp_path, r'''
        byte[] complete = COMPLETE;
        eq(2,consumeRows(complete).size());
        eq(List.of(),consumeRows(new byte[]{0}));
        // Every truncation of this small valid stream is incomplete, including
        // the boundary immediately after a complete row but before the terminator.
        for (int end=0;end<complete.length;end++) rowReadFailure(Arrays.copyOf(complete,end),true);
        rowReadFailure(new byte[]{2},false);
        byte[] rowPrefix = join(new byte[]{1},join(integer(1),fields(utf("field"))));
        rowReadFailure(join(rowPrefix,new byte[]{99,0}),false);
        scalarReadFailure(new byte[]{99},false);
        for (byte[] valid : List.of(BinaryScalar.encode(null),BinaryScalar.encode("text"),BinaryScalar.encode(41L))) {
            scalarReadFailure(join(valid,new byte[]{0}),false);
            for (int end=0;end<valid.length;end++) {
                byte[] shortValue = Arrays.copyOf(valid,end);
                scalarReadFailure(shortValue,true);
            }
        }
        for (int tag : List.of(1,9,10)) for (int length : List.of(-1,256*1024*1024+1)) {
            byte[] badScalar = join(new byte[]{(byte)tag},integer(length));
            scalarReadFailure(badScalar,false);
            rowReadFailure(join(rowPrefix,badScalar),false);
        }
        // This direct input contains the ENTIRE legal payload, not only its header.
        // No HTTP body cap or coordinator heap constraint applies to this check.
        int size = 256*1024*1024;
        byte[] encoded = new byte[size+5];
        encoded[0] = 9; ByteBuffer.wrap(encoded,1,4).putInt(size);
        for (int i=0;i<size;i++) encoded[i+5]=(byte)(i*31+(i>>>17));
        Object decoded = BinaryScalar.decode(encoded);
        eq(byte[].class,decoded.getClass());
        byte[] data = (byte[])decoded; eq(size,data.length);
        for (int i=0;i<size;i++) if (data[i] != encoded[i+5])
            throw new AssertionError("Scalar content differs at "+i);
    '''.replace('COMPLETE', java_wire(complete)))


def test_row_field_count_and_name_length_boundaries(tmp_path):
    run_interchange(tmp_path, r'''
        for (int count : List.of(-1,100001))
            rowReadFailure(join(new byte[]{1},integer(count)),false);
        for (int length : List.of(-1,16*1024*1024+1))
            rowReadFailure(join(new byte[]{1},join(integer(1),integer(length))),false);
        // Construct complete legal upper-bound rows using the external byte shell.
        var buffer = new ByteArrayOutputStream(); var out = new DataOutputStream(buffer);
        out.writeByte(1); out.writeInt(100000);
        for (int i=0;i<100000;i++) {
            byte[] name = utf("field"+i); out.writeInt(name.length); out.write(name);
            out.writeByte(5); out.writeInt(-i);
        }
        out.writeByte(0); out.flush();
        var rows = consumeRows(buffer.toByteArray()); eq(1,rows.size()); eq(100000,rows.get(0).size());
        for (int i=0;i<100000;i++) scalarEqual(-i,rows.get(0).get("field"+i));
        buffer = new ByteArrayOutputStream(); out = new DataOutputStream(buffer);
        String name = "水".repeat((16*1024*1024)/3)+"x";
        byte[] encodedName = utf(name); eq(16*1024*1024,encodedName.length);
        out.writeByte(1); out.writeInt(1); out.writeInt(encodedName.length); out.write(encodedName);
        out.writeByte(2); out.writeBoolean(true); out.writeByte(0); out.flush();
        rows = consumeRows(buffer.toByteArray()); eq(List.of(Map.of(name,true)),rows);
        eq(List.of(Map.of()),consumeRows(new byte[]{1,0,0,0,0,0}));
    ''')


def test_embedded_scan_lookup_current_rows_and_qualifiers(tmp_path):
    run_query_scenario(tmp_path, r'''
        try (var data = VelqoraMap.<Object,String>memory(); var other = VelqoraMap.<Object,String>memory()) {
            Object[] keys = {"text",false,(byte)-7,(short)1234,901,5000000001L,1.5f,-2.25d,'水',new byte[]{3,9}};
            var schema = Schema.<String>builder().column("value",value->value).build();
            var engine = new QueryEngine(new Catalog().add("items",data,schema).add("other",other,schema));
            eq(Map.of(),typedBag(engine.scan("items","empty"))); eq(null,engine.lookup("items","q","absent"));
            for (int i=0;i<keys.length;i++) data.put(keys[i],"value"+i);
            other.put("text","separate");
            for (String alias : List.of("left","renamed")) {
                List<Map<String,Object>> expected = new ArrayList<>();
                for (int i=0;i<keys.length;i++) {
                    var row = queryRow(alias+"._key",keys[i],alias+".value","value"+i);
                    expected.add(row); eq(typedRow(row),typedRow(engine.lookup("items",alias,keys[i])));
                }
                eq(typedBag(expected),typedBag(engine.scan("items",alias)));
                eq(queryRow(alias+"._key","text",alias+".value","separate"),engine.lookup("other",alias,"text"));
                eq(null,engine.lookup("items",alias,"missing"));
            }
            data.put("text","updated"); data.remove(901);
            eq(queryRow("now._key","text","now.value","updated"),engine.lookup("items","now","text"));
            eq(null,engine.lookup("items","now",901));
            List<Map<String,Object>> expected = new ArrayList<>();
            for (var entry : data.entrySet()) expected.add(queryRow("now._key",entry.getKey(),"now.value",entry.getValue()));
            eq(typedBag(expected),typedBag(engine.scan("items","now")));
        }
    ''', members=SCAN_OBSERVATIONS)


def test_remote_scan_lookup_selection_and_restricted_queries(tmp_path):
    observed = run_http_scenario(tmp_path, r"""
        try (var data = VelqoraMap.<Integer,String>memory(); var other = VelqoraMap.<Integer,String>memory();
             var typed = VelqoraMap.<Object,String>memory(); var many = VelqoraMap.<Integer,String>memory()) {
            data.putAll(Map.of(11,"violet",24,"amber",37,"violet")); other.put(11,"separate");
            Object[] typedKeys = {5000000001L,7L,(short)12,(byte)-3,2.5d,-0.75f,"text",true,'水'};
            for (int i=0;i<typedKeys.length;i++) typed.put(typedKeys[i],"typed"+i);
            for (int i=0;i<100;i++) many.put(i,i%10==3?"hit":"miss");
            var schema = Schema.<String>builder().column("value",value->value).build();
            var engine = new QueryEngine(new Catalog().add("items",data,schema).add("other",other,schema)
                .add("typed",typed,schema).add("many",many,schema));
            try (var server = VelqoraMapHttpServer.builder(data,KEYS,TEXT).clusterQueries(engine).address(new InetSocketAddress("127.0.0.1",0)).build().start()) {
                report("scan",status(server,"GET","/cluster/scan?table=items&alias=remote",new byte[0],200));
                report("other",status(server,"GET","/cluster/scan?table=other&alias=second",new byte[0],200));
                report("lookup",status(server,"POST","/cluster/lookup?table=items&alias=found",join(new byte[]{5},integer(24)),200));
                report("missing",status(server,"POST","/cluster/lookup?table=items&alias=found",join(new byte[]{5},integer(98)),200));
                for (int i=0;i<typedKeys.length;i++)
                    report("typed"+i,status(server,"POST","/cluster/lookup?table=typed&alias=t",BinaryScalar.encode(typedKeys[i]),200));
                report("typedMissing",status(server,"POST","/cluster/lookup?table=typed&alias=t",BinaryScalar.encode(5000000002L),200));
                String colorQuery = "SELECT i._key AS id, i.value AS shade FROM items i WHERE i.value = :color";
                report("selection",status(server,"POST","/cluster/stream?color=violet",utf(colorQuery),200));
                // The same query text with a new binding must apply the new binding.
                report("rebound",status(server,"POST","/cluster/stream?color=amber",utf(colorQuery),200));
                report("limit",status(server,"POST","/cluster/stream",utf("SELECT _key AS id FROM items LIMIT 2"),200));
                report("limitZero",status(server,"POST","/cluster/stream",utf("SELECT _key AS id FROM items LIMIT 0"),200));
                report("limitZeroFiltered",status(server,"POST","/cluster/stream",utf("SELECT _key AS id FROM items WHERE value = 'violet' LIMIT 0"),200));
                report("hitLimit",status(server,"POST","/cluster/stream",utf("SELECT _key AS id, value AS v FROM many WHERE value = 'hit' LIMIT 10"),200));
                report("missLimit",status(server,"POST","/cluster/stream",utf("SELECT _key AS id, value AS v FROM many WHERE value = 'miss' LIMIT 90"),200));
                report("hitPartial",status(server,"POST","/cluster/stream",utf("SELECT _key AS id FROM many WHERE value = 'hit' LIMIT 4"),200));
                String[][] filters = {
                    {"gt","_key > 11"},{"ge","_key >= 24"},{"lt","_key < 24"},{"le","_key <= 24"},
                    {"ne","_key != 24"},{"none","_key > 37"},{"textNe","value != 'violet'"},
                    {"and","value = 'violet' AND _key > 20"},{"andFirstFalse","_key > 20 AND value = 'amber'"},
                    {"or","_key > 30 OR value = 'amber'"},{"orLeft","value = 'amber' OR _key < 20"},
                    {"grouped","(value = 'amber' OR _key = 11) AND _key < 30"}};
                for (String[] filter : filters)
                    report("filter-"+filter[0],status(server,"POST","/cluster/stream",utf("SELECT _key AS id FROM items WHERE "+filter[1]),200));
                report("star",status(server,"POST","/cluster/stream",utf("SELECT * FROM items s"),200));
                report("starFiltered",status(server,"POST","/cluster/stream",utf("SELECT * FROM items s WHERE s.value = 'amber'"),200));
                report("empty",status(server,"POST","/cluster/stream",utf("SELECT value AS shade FROM items WHERE _key = 98"),200));
                data.put(24,"changed"); data.remove(11);
                report("changed",status(server,"GET","/cluster/scan?table=items&alias=current",new byte[0],200));
                for (String sql : List.of(
                    "SELECT i.value FROM items i JOIN other o ON i._key = o._key",
                    "SELECT value FROM items GROUP BY value",
                    "SELECT COUNT(*) AS n FROM items",
                    "SELECT value FROM items ORDER BY value"))
                    error(server,"POST","/cluster/stream",utf(sql),400);
            }
        }
    """)
    actual = {item['tag']: read_rows_wire(item['body']) for item in observed if item['tag'] != 'error'}
    typed = {item['tag']: read_typed_rows(item['body']) for item in observed if item['tag'] != 'error'}
    assert len(observed) == 42 and len(actual) == 38
    assert [item['tag'] for item in observed].count('error') == 4

    def ids(tag):
        return sorted(row['id'] for row in actual[tag])

    assert sorted(actual['scan'], key=lambda row: row['remote._key']) == [
        {'remote._key': 11, 'remote.value': 'violet'}, {'remote._key': 24, 'remote.value': 'amber'},
        {'remote._key': 37, 'remote.value': 'violet'}]
    assert actual['other'] == [{'second._key': 11, 'second.value': 'separate'}]
    assert actual['lookup'] == [{'found._key': 24, 'found.value': 'amber'}]
    assert actual['missing'] == []
    # Remote lookup by each scalar key type locates exactly that key and returns
    # it with its own scalar type (tag) and value.
    typed_keys = [(6, 5000000001), (6, 7), (4, 12), (3, -3), (8, 2.5), (7, -0.75),
                  (1, 'text'), (2, True), (10, '水')]
    for index, key in enumerate(typed_keys):
        assert typed['typed%d' % index] == [{'t._key': key, 't.value': (1, 'typed%d' % index)}], index
    assert actual['typedMissing'] == []
    assert sorted(actual['selection'], key=lambda row: row['id']) == [{'id': 11, 'shade': 'violet'}, {'id': 37, 'shade': 'violet'}]
    assert actual['rebound'] == [{'id': 24, 'shade': 'amber'}]
    assert len(actual['limit']) == 2
    assert all(set(row) == {'id'} for row in actual['limit'])
    assert len({row['id'] for row in actual['limit']}) == 2
    assert {row['id'] for row in actual['limit']} <= {11, 24, 37}
    assert actual['limitZero'] == [] and actual['limitZeroFiltered'] == []
    # A limit counts qualifying output rows: exactly enough matching rows exist.
    hits = list(range(3, 100, 10))
    assert sorted(row['id'] for row in actual['hitLimit']) == hits
    assert all(row['v'] == 'hit' for row in actual['hitLimit'])
    assert sorted(row['id'] for row in actual['missLimit']) == [i for i in range(100) if i % 10 != 3]
    assert all(row['v'] == 'miss' for row in actual['missLimit'])
    partial = ids('hitPartial')
    assert len(partial) == 4 and len(set(partial)) == 4 and set(partial) <= set(hits)
    expected_filters = {
        'gt': [24, 37], 'ge': [24, 37], 'lt': [11], 'le': [11, 24], 'ne': [11, 37], 'none': [],
        'textNe': [24], 'and': [37], 'andFirstFalse': [24], 'or': [24, 37], 'orLeft': [11, 24],
        'grouped': [11, 24]}
    for name, expected in expected_filters.items():
        assert ids('filter-' + name) == expected, name
    assert sorted(actual['star'], key=lambda row: row['s._key']) == [
        {'s._key': 11, 's.value': 'violet'}, {'s._key': 24, 's.value': 'amber'},
        {'s._key': 37, 's.value': 'violet'}]
    assert actual['starFiltered'] == [{'s._key': 24, 's.value': 'amber'}]
    assert actual['empty'] == []
    assert sorted(actual['changed'], key=lambda row: row['current._key']) == [
        {'current._key': 24, 'current.value': 'changed'}, {'current._key': 37, 'current.value': 'violet'}]


def test_independent_query_enablement_and_authorization(tmp_path, coverage_observation):
    observed = run_http_scenario(tmp_path, r'''
        // Fresh equal states; route policy is the only difference between allow/deny/io arms.
        for (int enabled=0;enabled<4;enabled++) for (String mode : List.of("allow","deny","io")) {
            try (var map = VelqoraMap.<String,String>memory()) {
                map.put("present","visible");
                AtomicInteger readerCalls = new AtomicInteger();
                var schema = Schema.<String>builder().column("value",value -> {
                    readerCalls.incrementAndGet();
                    return value;
                }).build();
                var queries = new QueryEngine(new Catalog().add("items",map,schema));
                var builder = VelqoraMapHttpServer.builder(map,TEXT,TEXT).address(new InetSocketAddress("127.0.0.1",0));
                if ((enabled&1)!=0) builder.queries(queries);
                if ((enabled&2)!=0) builder.clusterQueries(queries);
                builder.authorize(exchange->{
                    String access = exchange.getRequestHeaders().getFirst("X-Application-Access");
                    if ("io".equals(access)) throw new IOException("Application policy unavailable");
                    return "allow".equals(access);
                });
                try (var server = builder.build().start()) {
                    String[] routes = {"/query","/cluster/stream","/cluster/scan?table=items&alias=q","/cluster/lookup?table=items&alias=q"};
                    for (int i=0;i<routes.length;i++) {
                        boolean active = (enabled&(i==0?1:2))!=0;
                        int expected = mode.equals("deny")?401:mode.equals("io")?500:active?200:i==0?400:404;
                        byte[] body = i==2?new byte[0]:i==3?scalarText("present"):utf("SELECT value AS result FROM items");
                        // Complete an allowed access first, permitting eager reads and cached rows.
                        // Data and query configuration stay unchanged during the refused access.
                        if (active && mode.equals("deny"))
                            status(server,i==2?"GET":"POST",routes[i],body,200,"X-Application-Access","allow");
                        int readsBefore = readerCalls.get();
                        var response = status(server,i==2?"GET":"POST",routes[i],body,expected,"X-Application-Access",mode);
                        if (mode.equals("deny") && readsBefore != readerCalls.get())
                            throw new AssertionError("Refused request invoked an application column reader: " + routes[i]);
                        if (expected==401) eq("VelqoraMap",response.headers().firstValue("WWW-Authenticate").orElseThrow());
                        report(expected==200?(i==0?"ordinary":i==1?"selection":"qualified"):"error",response);
                        contents(Map.of("present","visible"),map);
                    }
                }
            }
        }
    ''')
    assert len(observed) == 48
    successes = [item for item in observed if item['tag'] != 'error']
    assert len(successes) == 8
    for item in successes:
        if item['tag'] == 'ordinary':
            assert parse_json(item['body'])['rows'] == [{'result': 'visible'}]
        elif item['tag'] == 'selection':
            assert read_rows_wire(item['body']) == [{'result': 'visible'}]
        else:
            assert read_rows_wire(item['body']) == [{'q._key': 'present', 'q.value': 'visible'}]
    coverage_observation('FP-10.07', 'refused queries do not invoke application column readers', observed=True,
        reason='On unchanged tables, refused ordinary, selection-stream, scan and lookup requests '
               'leave application reader counts unchanged. Enabled routes first complete an allowed '
               'access; no timing or number of reads is required on the allowed path. '
               'This observes callback effects, not invisible internal query work.')
