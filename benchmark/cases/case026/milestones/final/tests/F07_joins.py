# feature: F07
"""The three planned acceptance checks for local inner equality joins."""

from F05_helpers import run_query_scenario
from F07_helpers import JOIN_TABLES


def test_join_combinations_operand_directions_and_unmatched_rows(tmp_path):
    run_query_scenario(tmp_path, r'''
        var left = Map.of(
            "a1", new JoinEntry("red", "same", true),
            "a2", new JoinEntry("red", "same", true),
            "a3", new JoinEntry("blue", "other", true),
            "a4", new JoinEntry("absent", "unmatched", true));
        var middle = new HashMap<>(Map.of(
            "b1", new JoinEntry("red", "m1", true),
            "b2", new JoinEntry("red", "m2", true),
            "b3", new JoinEntry("blue", "m3", true),
            "b4", new JoinEntry("lonely", "m4", true)));
        var last = Map.of(
            "c1", new JoinEntry("m1", "first", true),
            "c2", new JoinEntry("m1", "second", true),
            "c3", new JoinEntry("m3", "third", true),
            "c4", new JoinEntry("nowhere", "unmatched", true));
        var catalog = new Catalog().add("origins", left, joinSchema("label"))
            .add("bridges", middle, joinSchema("label"))
            .add("ends", last, joinSchema("label"))
            .add("empty_table", Map.<String,JoinEntry>of(), joinSchema("label"));
        var engine = new QueryEngine(catalog);
        // Explicit relation vectors preserve identity and repeated projected rows.
        for (String condition : List.of("a.link = b.link", "b.link = a.link")) {
            String from = " FROM origins a JOIN bridges b ON " + condition;
            queryRows(engine, "SELECT a._key AS origin, b._key AS bridge" + from, Map.of(),
                queryRow("origin","a1","bridge","b1"),
                queryRow("origin","a1","bridge","b2"),
                queryRow("origin","a2","bridge","b1"),
                queryRow("origin","a2","bridge","b2"),
                queryRow("origin","a3","bridge","b3"));
            queryRows(engine, "SELECT a.label AS label" + from, Map.of(),
                queryRow("label","same"), queryRow("label","same"),
                queryRow("label","same"), queryRow("label","same"), queryRow("label","other"));
        }
        for (String condition : List.of("b.label = c.link", "c.link = b.label")) {
            queryRows(engine, "SELECT a._key AS origin, b._key AS bridge, c._key AS finish "
                + "FROM origins a JOIN bridges b ON a.link = b.link JOIN ends c ON " + condition,
                Map.of(),
                queryRow("origin","a1","bridge","b1","finish","c1"),
                queryRow("origin","a1","bridge","b1","finish","c2"),
                queryRow("origin","a2","bridge","b1","finish","c1"),
                queryRow("origin","a2","bridge","b1","finish","c2"),
                queryRow("origin","a3","bridge","b3","finish","c3"));
        }
        queryRows(engine,"SELECT a._key AS origin, d.label AS finish FROM origins a "
            + "JOIN bridges b ON a.link = b.link JOIN ends c ON b.label = c.link "
            + "JOIN ends d ON c._key = d._key",Map.of(),
            queryRow("origin","a1","finish","first"),queryRow("origin","a1","finish","second"),
            queryRow("origin","a2","finish","first"),queryRow("origin","a2","finish","second"),
            queryRow("origin","a3","finish","third"));
        var distinct = new QueryEngine(new Catalog()
            .add("l",Map.of("collision",new JoinEntry("Aa","source",true),
                            "typed",new JoinEntry("1","text",true)),joinSchema("label"))
            .add("r",Map.of("same",new JoinEntry("Aa","match",true),
                            "upper",new JoinEntry("AA","upper",true),"lower",new JoinEntry("aa","lower",true),
                            "unequal",new JoinEntry("BB","other",true),
                            "number",new JoinEntry(1,"number",true)),joinSchema("label")));
        queryRows(distinct,"SELECT a._key AS source, b._key AS target FROM l a JOIN r b ON a.link = b.link",
            Map.of(),queryRow("source","collision","target","same"));
        // A later join may refer to the first table, not just the last table added.
        queryRows(engine, "SELECT a._key AS origin, b._key AS bridge, c._key AS finish "
            + "FROM origins a JOIN bridges b ON a.link = b.link "
            + "JOIN origins c ON a._key = c._key", Map.of(),
            queryRow("origin","a1","bridge","b1","finish","a1"),
            queryRow("origin","a1","bridge","b2","finish","a1"),
            queryRow("origin","a2","bridge","b1","finish","a2"),
            queryRow("origin","a2","bridge","b2","finish","a2"),
            queryRow("origin","a3","bridge","b3","finish","a3"));
        queryRows(engine,"SELECT c._key AS id FROM ends c JOIN bridges b ON c.link = b.label",Map.of(),
            queryRow("id","c1"),queryRow("id","c2"),queryRow("id","c3"));
        var direct = new QueryEngine(new Catalog().add("origins",Map.of("one","present","two","missing"),
                Schema.<String>builder().column("target",v->v).build())
            .add("targets",Map.of("present","value"),Schema.<String>builder().column("value",v->v).build()));
        queryRows(direct,"SELECT a._key AS id, b.value FROM origins a JOIN targets b ON a.target = b._key",
            Map.of(),queryRow("id","one","value","value"));
        queryRows(engine, "SELECT a._key FROM origins a JOIN ends c ON a.link = c.link", Map.of());
        queryRows(engine, "SELECT a._key FROM origins a JOIN empty_table e ON a.link = e.link", Map.of());
        queryRows(engine, "SELECT a._key FROM empty_table e JOIN origins a ON a.link = e.link", Map.of());
        middle.clear(); middle.put("new",new JoinEntry("red","current",true));
        queryRows(engine,"SELECT a._key AS origin, b._key AS bridge FROM origins a JOIN bridges b ON a.link = b.link",
            Map.of(),queryRow("origin","a1","bridge","new"),queryRow("origin","a2","bridge","new"));
    ''', members=JOIN_TABLES)


def test_join_types_keys_projection_wildcards_and_filtering(tmp_path):
    run_query_scenario(tmp_path, r'''
        // Each numeric pair has the same Java representation on both sides.
        Object[][] pairs = {{"copper","silver"}, {false,true},
            {(byte)-7,(byte)12}, {(short)-300,(short)500}, {-1700,2300},
            {-9000000000L,12000000000L}, {-1.5f,2.25f}, {-8.5d,16.25d}};
        for (Object[] pair : pairs) {
            Object low = pair[0], high = pair[1];
            var left = Map.of(low, new JoinEntry(high,"Llow",true),
                              high, new JoinEntry(low,"Lhigh",false));
            var right = Map.of(low, new JoinEntry(low,"Rlow",true),
                               high, new JoinEntry(high,"Rhigh",false));
            var engine = new QueryEngine(new Catalog()
                .add("sources",left,joinSchema("left_label"))
                .add("targets",right,joinSchema("right_label")));
            String select = "SELECT left_label, right_label FROM sources a JOIN targets b ON ";
            queryRows(engine, select + "a.link = b.link", Map.of(),
                queryRow("left_label","Llow","right_label","Rhigh"),
                queryRow("left_label","Lhigh","right_label","Rlow"));
            queryRows(engine, select + "a.link = b._key", Map.of(),
                queryRow("left_label","Llow","right_label","Rhigh"),
                queryRow("left_label","Lhigh","right_label","Rlow"));
            queryRows(engine, select + "b._key = a.link", Map.of(),
                queryRow("left_label","Llow","right_label","Rhigh"),
                queryRow("left_label","Lhigh","right_label","Rlow"));
            queryRows(engine, select + "a._key = b.link", Map.of(),
                queryRow("left_label","Llow","right_label","Rlow"),
                queryRow("left_label","Lhigh","right_label","Rhigh"));
            queryRows(engine, select + "a._key = b._key", Map.of(),
                queryRow("left_label","Llow","right_label","Rlow"),
                queryRow("left_label","Lhigh","right_label","Rhigh"));
            String from = " FROM sources a JOIN targets b ON a.link = b.link";
            queryRows(engine, "SELECT a._key AS source, b._key AS target, a.link AS value" + from,
                Map.of(), queryRow("source",low,"target",high,"value",high),
                          queryRow("source",high,"target",low,"value",low));
            queryRows(engine, "SELECT *" + from, Map.of(),
                queryRow("a._key",low,"a.link",high,"a.left_label","Llow","a.included",true,
                         "b._key",high,"b.link",high,"b.right_label","Rhigh","b.included",false),
                queryRow("a._key",high,"a.link",low,"a.left_label","Lhigh","a.included",false,
                         "b._key",low,"b.link",low,"b.right_label","Rlow","b.included",true));
            queryRows(engine, select + "a.link = b.link WHERE a.included = true AND b.link = :wanted",
                Map.of("wanted",high), queryRow("left_label","Llow","right_label","Rhigh"));
            queryRows(engine, select + "a.link = b.link WHERE a.included = true AND b.link = :wanted",
                Map.of("wanted",low));
            queryRows(engine, select + "a.link = b.link WHERE b._key = :wanted",
                Map.of("wanted",high), queryRow("left_label","Llow","right_label","Rhigh"));
            queryRows(engine, select + "a.link = b.link WHERE a._key = :wanted",
                Map.of("wanted",high), queryRow("left_label","Lhigh","right_label","Rlow"));
            queryRows(engine, select + "a.link = b.link WHERE b._key = :wanted AND a._key = :wanted",
                Map.of("wanted",high));
            queryRows(engine, select + "a.link = b.link WHERE right_label = 'Rhigh'",
                Map.of(), queryRow("left_label","Llow","right_label","Rhigh"));
            queryRows(engine, select + "a.link = b.link WHERE b.included = true",
                Map.of(), queryRow("left_label","Lhigh","right_label","Rlow"));
            queryRows(engine, select + "a.link = b.link WHERE a.included = true AND b.included = true",
                Map.of());
        }
        Map<String,JoinEntry> targets = new HashMap<>();
        targets.put("b",new JoinEntry("match","middle",true));
        var changing = new QueryEngine(new Catalog()
            .add("sources",Map.of("a",new JoinEntry("match","start",true)),joinSchema("label"))
            .add("targets",targets,joinSchema("label"))
            .add("ends",Map.of("c",new JoinEntry("middle","finish",true)),joinSchema("label")));
        String chain = " FROM sources a JOIN targets b ON a.link = b.link JOIN ends c ON b.label = c.link";
        queryRows(changing,"SELECT *"+chain,Map.of(),queryRow(
            "a._key","a","a.link","match","a.label","start","a.included",true,
            "b._key","b","b.link","match","b.label","middle","b.included",true,
            "c._key","c","c.link","middle","c.label","finish","c.included",true));
        queryRows(changing,"SELECT a.label AS start, c.label AS finish"+chain+" WHERE c.label = :wanted",
            Map.of("wanted","finish"),queryRow("start","start","finish","finish"));
        var typed = new QueryEngine(new Catalog()
            .add("lefts",Map.of("text",new JoinEntry("1","text",true)),joinSchema("label"))
            .add("rights",Map.of("number",new JoinEntry(1,"number",true),
                                "text",new JoinEntry("1","exact",true)),joinSchema("label")));
        queryRows(typed,"SELECT b.label FROM lefts a JOIN rights b ON a.link = b.link",Map.of(),
            queryRow("label","exact"));
    ''', members=JOIN_TABLES)


def test_invalid_join_sides_and_ambiguous_selected_references(tmp_path):
    run_query_scenario(tmp_path, r'''
        var engine = new QueryEngine(new Catalog()
            .add("sources",Map.of("left",new JoinEntry("match","left label",true)),joinSchema("label"))
            .add("targets",Map.of("right",new JoinEntry("match","right label",true)),joinSchema("label")));
        String from = " FROM sources a JOIN targets b ON a.link = b.link";
        queryRows(engine, "SELECT a.label AS source, b.label AS target" + from, Map.of(),
            queryRow("source","left label","target","right label"));
        for (String condition : List.of("a.link = a.link", "b.link = b.link")) {
            queryRefused(engine, "SELECT a.label FROM sources a JOIN targets b ON " + condition, Map.of());
        }
        for (String column : List.of("label", "link", "_key")) {
            queryRefused(engine, "SELECT " + column + from, Map.of());
        }
        queryRefused(engine,"SELECT label FROM sources a JOIN sources b ON a.link = b.link",Map.of());
        queryRefused(engine,"SELECT a.label FROM sources a JOIN targets b ON a.link = b.link "
            + "JOIN sources c ON a.link = b.link",Map.of());
        var empty = new QueryEngine(new Catalog()
            .add("sources",Map.<String,JoinEntry>of(),joinSchema("label"))
            .add("targets",Map.of("right",new JoinEntry("match","right",true)),joinSchema("label")));
        queryRefused(empty,"SELECT a.label FROM sources a JOIN targets b ON a.link = a.link",Map.of());
        // The positive path still works after refusals; no diagnostic prose is parsed.
        queryRows(engine, "SELECT a._key AS source, b._key AS target" + from, Map.of(),
            queryRow("source","left","target","right"));
    ''', members=JOIN_TABLES)
