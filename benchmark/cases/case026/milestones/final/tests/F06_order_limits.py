# feature: F06
"""The four planned public-query checks for ordering and result limits."""

from F05_helpers import run_query_scenario
from F06_helpers import ORDER_OBSERVATIONS


def test_lexicographic_order_directions_and_output_aliases(tmp_path):
    run_query_scenario(tmp_path, r'''
        Entry[] entries = {
            new Entry("south", 3, 4, true, null),
            new Entry("north", 9, 1, true, null),
            new Entry("north", 3, 4, true, null),
            new Entry("south", 9, 1, true, null),
            new Entry("north", 9, 4, true, null),
            new Entry("north", 9, 1, true, null),
            new Entry("south", 3, 1, true, null)
        };
        Map<String,Entry> data = new LinkedHashMap<>();
        for (int i=0; i<entries.length; i++) data.put("record" + i, entries[i]);
        var engine = entryEngine(data);
        orderedQueryRows(engine, "SELECT amount FROM items ORDER BY amount",
            queryRow("amount",3), queryRow("amount",3), queryRow("amount",3),
            queryRow("amount",9), queryRow("amount",9), queryRow("amount",9), queryRow("amount",9));
        String[] clauses = {
            "name, amount, peer",
            "region ASC, score DESC, tie",
            "region DESC, score ASC, tie DESC"
        };
        int[][] sequence = {{2,1,5,4,6,0,3}, {1,5,4,2,3,6,0}, {0,6,3,2,4,1,5}};
        for (int c=0; c<clauses.length; c++) {
            List<Map<String,Object>> expected = new ArrayList<>();
            for (int index : sequence[c]) {
                Entry entry = entries[index];
                expected.add(queryRow("region",entry.name(),"score",entry.amount(),"tie",entry.peer()));
            }
            // Fully tied entries project identical rows; their identity order is not judged.
            var actual = engine.query("SELECT name AS region, amount AS score, peer AS tie "
                + "FROM items ORDER BY " + clauses[c]).rows();
            orderedRows(expected, actual);
        }
    ''', members=ORDER_OBSERVATIONS)


def test_null_placement_numeric_domain_natural_order_and_refusal(tmp_path):
    run_query_scenario(tmp_path, r'''
        Object[] values = {null, 2.0f, -4L, (short)10, -0.5d, (byte)2, 2L,
                           (byte)-64, 9007199254740992L, (short)2, 2, 2.0d,
                           0.25f, -8192, null};
        String[] ids = {"a","b","c","d","e","f","g","h","i","j","k","l","m","n","o"};
        Map<String,Entry> data = new LinkedHashMap<>();
        for (int i=0; i<values.length; i++) data.put(ids[i],new Entry("value",values[i],1,true,null));
        var engine = entryEngine(data);
        String select = "SELECT _key AS id, amount FROM items ORDER BY amount";
        orderedQueryIds(engine, select + " ASC, id DESC",
            "n","h","c","e","m","l","k","j","g","f","b","d","i","o","a");
        orderedQueryIds(engine, select + " DESC, id ASC",
            "a","o","i","d","b","f","g","j","k","l","m","e","c","h","n");
        // Same-type natural ordering is exercised independently of numeric coercion.
        Object[][] natural = {{"birch","Zinc","amber"}, {false,true,false}, {'m','z','a'},
            {java.time.Duration.ofSeconds(9),java.time.Duration.ofSeconds(10),java.time.Duration.ofSeconds(2)}};
        String[][] ascending = {{"b","c","a"}, {"a","c","b"}, {"c","a","b"}, {"c","a","b"}};
        String[][] descending = {{"a","c","b"}, {"b","a","c"}, {"b","a","c"}, {"b","a","c"}};
        for (int i=0; i<natural.length; i++) {
            var ordered = entryEngine(Map.of(
                "a",new Entry("value",natural[i][0],1,true,null),
                "b",new Entry("value",natural[i][1],1,true,null),
                "c",new Entry("value",natural[i][2],1,true,null)));
            orderedQueryIds(ordered,select + " ASC, id ASC",ascending[i]);
            orderedQueryIds(ordered,select + " DESC, id ASC",descending[i]);
        }
        var precise = entryEngine(Map.of(
            "a",new Entry("upper",16777217d,1,true,null),
            "b",new Entry("lower",16777216d,1,true,null)));
        orderedQueryIds(precise,select + " ASC, id ASC","b","a");
        orderedQueryIds(precise,select + " DESC, id DESC","a","b");
        Object[][] incomparable = {{2,"text"}, {new Object(),new Object()}, {"true",true}};
        for (Object[] pair : incomparable) {
            var invalid = entryEngine(Map.of(
                "a",new Entry("left",pair[0],1,true,null),
                "b",new Entry("right",pair[1],1,true,null)));
            queryRows(invalid, "SELECT name FROM items", Map.of(),
                queryRow("name","left"),queryRow("name","right"));
            queryRefused(invalid,select + " ASC",Map.of());
            queryRefused(invalid,select + " DESC",Map.of());
        }
    ''', members=ORDER_OBSERVATIONS)


def test_limit_omission_zero_boundaries_and_invalid_values(tmp_path):
    run_query_scenario(tmp_path, r'''
        Map<String,Entry> data = new LinkedHashMap<>();
        List<Map<String,Object>> expected = new ArrayList<>();
        for (int i=0; i<1801; i++) {
            boolean qualifies = i % 3 != 0;
            data.put("row"+i,new Entry("item",i,1,qualifies,null));
            if (qualifies) expected.add(queryRow("id","row"+i,"amount",i));
        }
        var engine = entryEngine(data);
        String sql = "SELECT _key AS id, amount FROM items WHERE active = true";
        var complete = rowBag(expected);
        eq(complete, rowBag(engine.query(sql).rows()));
        for (int limit : new int[]{0,1,7,expected.size()-1,expected.size(),expected.size()+1,2147483647}) {
            var rows = engine.query(sql + " LIMIT " + limit).rows();
            eq(Math.min(limit,expected.size()), rows.size());
            var subset = rowBag(rows);
            for (var item : subset.entrySet()) {
                Integer available = complete.get(item.getKey());
                if (available == null || item.getValue() > available)
                    throw new AssertionError("Limited result is not a submultiset of qualifying rows");
            }
            if (limit >= expected.size()) eq(complete,subset);
        }
        queryRows(engine,"SELECT name, COUNT(*) AS n FROM items GROUP BY name LIMIT 0",Map.of());
        // Unordered limits over joined and grouped results also select a submultiset of the complete result.
        Map<String,Entry> groupedData = new HashMap<>();
        for (int i=0; i<12; i++) groupedData.put("g"+i,new Entry("group"+(i%4),i%3,1,true,null));
        var groupedEngine = new QueryEngine(new Catalog().add("items",groupedData,entrySchema())
            .add("links",Map.of("g1","g1","g2","g2","g5","g5","g6","g6","g9","g9"),
                Schema.<String>builder().column("target",v->v).build()));
        String[] unordered = {
            "SELECT name AS label, MIN(caption) AS first FROM items GROUP BY name",
            "SELECT name AS label FROM items GROUP BY name",
            "SELECT a._key AS id, b.target AS target FROM items a JOIN links b ON a._key = b.target"};
        @SuppressWarnings("unchecked") List<Map<String,Object>>[] full = new List[]{
            List.of(queryRow("label","group0","first","group0!"),queryRow("label","group1","first","group1!"),
                    queryRow("label","group2","first","group2!"),queryRow("label","group3","first","group3!")),
            List.of(queryRow("label","group0"),queryRow("label","group1"),
                    queryRow("label","group2"),queryRow("label","group3")),
            List.of(queryRow("id","g1","target","g1"),queryRow("id","g2","target","g2"),
                    queryRow("id","g5","target","g5"),queryRow("id","g6","target","g6"),
                    queryRow("id","g9","target","g9"))};
        for (int q=0; q<unordered.length; q++) {
            var whole = rowBag(full[q]);
            eq(whole, rowBag(groupedEngine.query(unordered[q]).rows()));
            for (int limit : new int[]{0,1,2,full[q].size(),full[q].size()+3}) {
                var rows = groupedEngine.query(unordered[q] + " LIMIT " + limit).rows();
                eq(Math.min(limit,full[q].size()), rows.size());
                for (var item : rowBag(rows).entrySet()) {
                    Integer available = whole.get(item.getKey());
                    if (available == null || item.getValue() > available)
                        throw new AssertionError("Limited result is not a submultiset: " + unordered[q]);
                }
            }
        }
        queryRows(engine,"SELECT COUNT(*) AS n FROM items LIMIT 0",Map.of());
        var empty = entryEngine(Map.of());
        queryRows(empty,"SELECT amount FROM items",Map.of());
        queryRows(empty,"SELECT amount FROM items LIMIT 2147483647",Map.of());
        queryRows(engine,"SELECT amount FROM items WHERE amount < -1 LIMIT 7",Map.of());
        for (String limit : List.of("-1","2147483648","1.5"))
            queryRefused(engine,sql + " LIMIT " + limit,Map.of());
        eq(complete, rowBag(engine.query(sql).rows()));
    ''')


def test_limit_is_prefix_of_complete_ordered_result(tmp_path):
    run_query_scenario(tmp_path, r'''
        // Explicit rank vectors give an independent oracle, not another product query.
        String[] rankIds = {"r6","r2","r7","r1","r4","r3","r0","r5"};
        int[] scores = {-11,-4,2,2,9,12,31,44};
        String[] labels = {"a","a","a","z","a","a","a","a"};
        int[][] insertionOrders = {{7,5,3,1,6,4,2,0}, {0,2,4,6,1,3,5,7}};
        for (int[] insertion : insertionOrders) {
            Map<String,Entry> data = new LinkedHashMap<>();
            data.put("excluded",new Entry("excluded",-100,1,false,null));
            for (int i : insertion) data.put(rankIds[i],new Entry(labels[i],scores[i],1,true,null));
            var engine = entryEngine(data);
            String sql = "SELECT _key AS id, amount AS score, name AS label FROM items WHERE active = true";
            for (int limit : new int[]{0,1,3,5,8,11}) {
                int count = Math.min(limit,rankIds.length);
                orderedQueryIds(engine,sql + " ORDER BY score ASC, label ASC LIMIT " + limit,
                    Arrays.copyOf(rankIds,count));
                String[] reverse = new String[count];
                for (int i=0; i<count; i++) reverse[i]=rankIds[rankIds.length-1-i];
                orderedQueryIds(engine,sql + " ORDER BY score DESC, label DESC LIMIT " + limit,reverse);
            }
        }
        var catalog = new Catalog().add("items",Map.of(
            "p",new Entry("p",9,1,true,null),"q",new Entry("q",2,1,true,null),
            "r",new Entry("r",5,1,true,null)),entrySchema())
            .add("links",Map.of("p","p","q","q","r","r"),
                Schema.<String>builder().column("target",v->v).build());
        var joined = new QueryEngine(catalog);
        orderedQueryIds(joined,"SELECT a._key AS id, a.amount AS score FROM items a "
            + "JOIN links b ON a._key = b.target ORDER BY score LIMIT 2","q","r");
    ''', members=ORDER_OBSERVATIONS)
