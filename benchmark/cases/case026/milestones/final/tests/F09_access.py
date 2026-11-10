# feature: F09
"""Observable index maintenance, incremental queries, and input-growth effects."""

from F05_helpers import run_query_scenario
from F07_helpers import JOIN_TABLES
from F09_helpers import INDEX_CHECKS, run_access_measurement


def test_indexed_equality_preserves_matches_and_remaining_predicates(tmp_path):
    run_query_scenario(tmp_path, r'''
        var data = new VelqoraMap<String,Entry>();
        data.put("a", new Entry("same", (byte)12, null, true, "east"));
        data.put("b", new Entry("same", 12L, null, false, "east"));
        data.put("c", new Entry("third", 12.0, "peer", true, "west"));
        data.put("d", new Entry("fourth", 25, "peer", false, "north"));
        var catalog = new Catalog().add("items", data, entrySchema())
            .index("items", "note").index("items", "amount").index("items", "peer");
        var engine = new QueryEngine(catalog);
        queryIds(engine, "note = 'east'", "a", "b");
        queryIds(engine, "'east' = note", "a", "b");
        queryIds(engine, "amount = 12", "a", "b", "c");
        queryIds(engine, "12.0 = amount", "a", "b", "c");
        queryBoundIds(engine, ":wanted = peer", queryRow("wanted",null), "a","b");
        queryIds(engine, "peer = NULL", "a","b");
        queryIds(engine, "note = 'absent'");
        queryRows(engine, "SELECT name FROM items WHERE note = 'east'", Map.of(),
            queryRow("name","same"), queryRow("name","same"));
        for (Object number : List.of((short)12, 12, 12L, 12.0f, 12.0))
            queryBoundIds(engine, "amount = :wanted", Map.of("wanted",number), "a","b","c");
        queryBoundIds(engine, "peer = :wanted", queryRow("wanted",null), "a","b");
        queryIds(engine, "peer = 'peer'", "c","d");
        queryIds(engine, "note = 'east' AND active = true", "a");
        queryIds(engine, "active = false AND note = 'east'", "b");
        queryIds(engine, "note = 'east' OR amount = 25", "a","b","d");
    ''')


def test_indexed_queries_follow_completed_mutations(tmp_path):
    run_query_scenario(tmp_path, r'''
        var data = new VelqoraMap<String,JoinEntry>();
        var expected = new HashMap<String,JoinEntry>();
        var history = new HashSet<Object>(Arrays.asList("old","new","last",null));
        // Two indexes on one table: each must follow every completed change.
        var engine = new QueryEngine(new Catalog().add("records",data,joinSchema("label"))
            .index("records","link").index("records","included"));
        List<java.util.function.Consumer<Map<String,JoinEntry>>> steps = List.of(
            m -> m.put("a", new JoinEntry("old","A",true)),
            m -> m.putAll(Map.of(
                "b",new JoinEntry("old","B",true),"c",new JoinEntry(null,"C",false))),
            m -> m.put("a",new JoinEntry("new","A2",false)),
            m -> m.putIfAbsent("d",new JoinEntry("old","D",true)),
            m -> m.putIfAbsent("a",new JoinEntry("last","ignored",true)),
            m -> m.replace("a",new JoinEntry("old","A3",true)),
            m -> m.replace("b",m.get("b"),new JoinEntry("new","B2",false)),
            m -> m.compute("c",(k,v)->new JoinEntry("new","C2",true)),
            m -> m.computeIfAbsent("e",k->new JoinEntry(null,"E",true)),
            m -> m.computeIfPresent("d",(k,v)->new JoinEntry("new","D2",true)),
            m -> m.merge("b",new JoinEntry("last","B3",true),(a,b)->b),
            m -> m.merge("f",new JoinEntry("last","F",true),(a,b)->b),
            m -> m.compute("a",(k,v)->null),
            m -> m.computeIfPresent("b",(k,v)->null),
            m -> m.merge("c",new JoinEntry("old","x",true),(a,b)->null),
            m -> m.replaceAll((k,v)->new JoinEntry("old",v.label(),v.included())),
            m -> m.remove("d",m.get("d")),
            m -> m.remove("e")
        );
        for (var step : steps) {
            step.accept(expected); step.accept(data);
            checkIndexedState(engine,expected,history);
        }
        data.removeAll(List.of("f","missing")); expected.remove("f");
        checkIndexedState(engine,expected,history);
        data.putAll(Map.of("x",new JoinEntry("new","X",true),"y",new JoinEntry(null,"Y",false)));
        data.clear(); expected.clear();
        checkIndexedState(engine,expected,history);
        // Concurrent writers share one key and also finish with deterministic private keys.
        for (int worker=0; worker<4; worker++) for (int i=0;i<80;i++) history.add("w"+worker+"-"+i);
        contend(4, worker -> {
            for (int i=0;i<80;i++) {
                var value = new JoinEntry("w"+worker+"-"+i,"writer"+worker,true);
                data.put("shared",value);
                data.put("private"+worker,value);
            }
            return true;
        });
        for (int worker=0;worker<4;worker++) expected.put("private"+worker,
            new JoinEntry("w"+worker+"-79","writer"+worker,true));
        // The winning writer is unspecified; the public map supplies the completed value.
        expected.put("shared",Objects.requireNonNull(data.get("shared")));
        checkIndexedState(engine,expected,history);
    ''', members=JOIN_TABLES + INDEX_CHECKS)


def test_index_configuration_refuses_invalid_targets(tmp_path):
    run_query_scenario(tmp_path, r'''
        var data = new VelqoraMap<String,JoinEntry>(Map.of("one",new JoinEntry("group","visible",true)));
        var catalog = new Catalog().add("records",data,joinSchema("label"));
        catalog.index("records","link");
        queryRows(new QueryEngine(catalog),"SELECT label FROM records WHERE link = 'group'",Map.of(),
            queryRow("label","visible"));
        rejects(IllegalArgumentException.class, () -> catalog.index("records","unknown"));
        rejects(IllegalArgumentException.class, () -> catalog.index("records","_key"));
        var ordinary = new Catalog().add("records",new HashMap<>(data),joinSchema("label"));
        rejects(IllegalArgumentException.class, () -> ordinary.index("records","link"));
        queryRows(new QueryEngine(catalog),"SELECT label FROM records WHERE link = 'group'",Map.of(),
            queryRow("label","visible"));
        // A persistent embedded-store map is also an indexable backing that follows mutations.
        try (var stored = VelqoraMap.strings(java.nio.file.Path.of("indexed-store"))) {
            stored.put("p","red"); stored.put("q","red");
            var text = Schema.<String>builder().column("shade", v -> v).build();
            var persisted = new QueryEngine(new Catalog().add("shades",stored,text).index("shades","shade"));
            queryRows(persisted,"SELECT _key AS id FROM shades WHERE shade = 'red'",Map.of(),
                queryRow("id","p"),queryRow("id","q"));
            stored.put("q","blue"); stored.put("r","red"); stored.remove("p");
            queryRows(persisted,"SELECT _key AS id FROM shades WHERE shade = 'red'",Map.of(),queryRow("id","r"));
            queryRows(persisted,"SELECT _key AS id FROM shades WHERE shade = 'blue'",Map.of(),queryRow("id","q"));
        }
    ''', members=JOIN_TABLES)


def test_selective_query_tenfold_growth(tmp_path):
    run_access_measurement(tmp_path, "selective")


def test_incremental_results_and_unsupported_operations(tmp_path):
    run_query_scenario(tmp_path, r'''
        var data = new VelqoraMap<String,JoinEntry>(Map.of(
            "a",new JoinEntry("east","first",true), "b",new JoinEntry("east","second",false),
            "c",new JoinEntry("west","third",true), "d",new JoinEntry("west","fourth",true)));
        var engine = new QueryEngine(new Catalog().add("records",data,joinSchema("label")));
        // Same map with a configured index: key and index access must keep remaining conditions.
        var indexed = new QueryEngine(new Catalog().add("records",data,joinSchema("label"))
            .index("records","link"));
        for (var candidate : List.of(engine,indexed)) {
            eq(rowBag(List.of(queryRow("text","first"))),rowBag(candidate.stream(
                "SELECT label AS text FROM records WHERE link = :region AND included = true",Map.of("region","east"))));
            eq(rowBag(List.of(queryRow("text","second"))),rowBag(candidate.stream(
                "SELECT label AS text FROM records WHERE included = false AND 'east' = link",Map.of())));
            eq(Map.of(),rowBag(candidate.stream(
                "SELECT label AS text FROM records WHERE link = 'west' AND included = false",Map.of())));
            eq(Map.of(),rowBag(candidate.stream(
                "SELECT label AS text FROM records WHERE _key = 'a' AND included = false",Map.of())));
            eq(rowBag(List.of(queryRow("text","third"))),rowBag(candidate.stream(
                "SELECT label AS text FROM records WHERE _key = :id AND link = 'west'",Map.of("id","c"))));
            eq(rowBag(List.of(queryRow("text","third"),queryRow("text","fourth"))),rowBag(candidate.stream(
                "SELECT label AS text FROM records WHERE link = 'west' LIMIT 5",Map.of())));
        }
        var all = List.of(queryRow("id","a","text","first"),queryRow("id","b","text","second"),
            queryRow("id","c","text","third"),queryRow("id","d","text","fourth"));
        eq(rowBag(all),rowBag(engine.stream("SELECT _key AS id, label AS text FROM records",Map.of())));
        eq(rowBag(List.of(queryRow("text","first"))),rowBag(engine.stream(
            "SELECT label AS text FROM records WHERE link = :region AND included = true",Map.of("region","east"))));
        eq(Map.of(),rowBag(engine.stream("SELECT label FROM records WHERE link = 'absent'",Map.of())));
        var active = List.of(all.get(0),all.get(2),all.get(3));
        for (int limit : List.of(0,2,9)) {
            var rows = new ArrayList<Map<String,Object>>();
            engine.stream("SELECT _key AS id, label AS text FROM records WHERE included = true LIMIT " + limit,Map.of()).forEach(rows::add);
            eq(Math.min(limit,active.size()),rows.size());
            eq(rows.size(),new HashSet<>(rows).size());
            if (!active.containsAll(rows)) throw new AssertionError("Prefix contains invented rows: " + rows);
        }
        for (String sql : List.of(
            "SELECT a.label FROM records a JOIN records b ON a.link = b.link",
            "SELECT link FROM records GROUP BY link",
            "SELECT COUNT(*) AS count FROM records",
            "SELECT label FROM records ORDER BY label")) {
            rejects(IllegalArgumentException.class, () -> rowBag(engine.stream(sql,Map.of())));
        }
        eq(rowBag(all),rowBag(engine.stream("SELECT _key AS id, label AS text FROM records",Map.of())));
    ''', members=JOIN_TABLES)


def test_prefix_query_tenfold_growth(tmp_path):
    run_access_measurement(tmp_path, "prefix")


def test_indexed_joins_follow_current_matching_rows(tmp_path):
    run_query_scenario(tmp_path, r'''
        var left = Map.of("a",new JoinEntry("east","L",true),"b",new JoinEntry("east","L",true),
            "c",new JoinEntry("west","W",true));
        var right = new VelqoraMap<String,JoinEntry>(Map.of("x",new JoinEntry("east","R",true),
            "y",new JoinEntry("east","R",true),"z",new JoinEntry("north","N",true)));
        var engine = new QueryEngine(new Catalog().add("sources",left,joinSchema("label"))
            .add("targets",right,joinSchema("label")).index("targets","link"));
        String sql = "SELECT a.label AS source, b.label AS target FROM sources a JOIN targets b ON a.link = b.link";
        queryRows(engine,sql,Map.of(),queryRow("source","L","target","R"),queryRow("source","L","target","R"),
            queryRow("source","L","target","R"),queryRow("source","L","target","R"));
        right.replace("x",new JoinEntry("west","moved",true));
        right.remove("y");
        right.put("new",new JoinEntry("east","added",true));
        right.compute("z",(k,v)->new JoinEntry("west","changed",true));
        for (String condition : List.of("a.link = b.link","b.link = a.link")) {
            queryRows(engine,"SELECT a.label AS source, b.label AS target FROM sources a JOIN targets b ON " + condition,
                Map.of(),queryRow("source","L","target","added"),queryRow("source","L","target","added"),
                queryRow("source","W","target","moved"),queryRow("source","W","target","changed"));
        }
        right.clear();
        queryRows(engine,sql,Map.of());
        right.put("again",new JoinEntry("east","reinserted",true));
        queryRows(engine,sql,Map.of(),queryRow("source","L","target","reinserted"),
            queryRow("source","L","target","reinserted"));
    ''', members=JOIN_TABLES)
