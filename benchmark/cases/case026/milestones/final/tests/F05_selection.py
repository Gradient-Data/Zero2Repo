# feature: F05
"""The seven planned acceptance checks for table selection and predicates."""

from F05_helpers import run_query_scenario


def test_registered_tables_projection_and_completed_changes(tmp_path):
    run_query_scenario(tmp_path, r'''
        try (VelqoraMap<String,Entry> data = VelqoraMap.memory()) {
            data.put("k7", new Entry("cedar", 12, 3, true, null));
            data.put("k2", new Entry("birch", -4, 9, false, "memo"));
            Map<String,Entry> ordinary = new HashMap<>();
            ordinary.put("z", new Entry("other", 8, 1, true, null));
            var engine = new QueryEngine(new Catalog().add("items", data, entrySchema())
                .add("ordinary", ordinary, entrySchema()).add("empty", Map.<String,Entry>of(), entrySchema()));
            String sql = "SELECT _key AS id, name, amount AS stock, caption AS display FROM items";
            queryRows(engine, sql, Map.of(),
                queryRow("id","k7","name","cedar","stock",12,"display","cedar!"),
                queryRow("id","k2","name","birch","stock",-4,"display","birch!"));
            queryRows(engine, "SELECT * FROM items t", Map.of(),
                queryRow("t._key","k7","t.name","cedar","t.amount",12,"t.peer",3,
                         "t.active",true,"t.note",null,"t.caption","cedar!"),
                queryRow("t._key","k2","t.name","birch","t.amount",-4,"t.peer",9,
                         "t.active",false,"t.note","memo","t.caption","birch!"));
            queryRows(engine, "SELECT _key, name FROM ordinary", Map.of(), queryRow("_key","z","name","other"));
            var numericKeys = new QueryEngine(new Catalog().add("numbered",
                Map.of(901,new Entry("keyed",6,2,true,null)),entrySchema()));
            queryRows(numericKeys,"SELECT _key AS id, name FROM numbered",Map.of(),
                queryRow("id",901,"name","keyed"));
            queryRows(numericKeys,"SELECT * FROM numbered n",Map.of(),
                queryRow("n._key",901,"n.name","keyed","n.amount",6,"n.peer",2,
                         "n.active",true,"n.note",null,"n.caption","keyed!"));
            queryRows(engine, "SELECT name FROM items WHERE _key = 'k7'", Map.of(), queryRow("name","cedar"));
            ordinary.put("z", new Entry("revised", 8, 1, true, null));
            queryRows(engine, "SELECT name FROM ordinary", Map.of(), queryRow("name","revised"));
            queryRows(engine, "SELECT * FROM empty", Map.of());
            data.put("k7", new Entry("updated", 33, 3, true, null));
            data.remove("k2");
            data.put("k9", new Entry("updated", 33, 3, true, null));
            queryRows(engine, sql, Map.of(),
                queryRow("id","k7","name","updated","stock",33,"display","updated!"),
                queryRow("id","k9","name","updated","stock",33,"display","updated!"));
            queryRows(engine, "SELECT name FROM items WHERE _key = 'k7'", Map.of(), queryRow("name","updated"));
            queryRows(engine, "SELECT name FROM items WHERE _key = 'k2'", Map.of());
            // Projection must preserve duplicate rows after omitting the key.
            queryRows(engine, "SELECT name, amount FROM items", Map.of(),
                queryRow("name","updated","amount",33), queryRow("name","updated","amount",33));
            data.clear();
            queryRows(engine, sql, Map.of());
        }
    ''')


def test_alias_resolution_and_immutable_results(tmp_path):
    run_query_scenario(tmp_path, r'''
        var engine = entryEngine(Map.of("p", new Entry("olive", 6, 2, true, "note")));
        queryRows(engine, "SELECT t.name AS label, amount, t._key AS id FROM items t", Map.of(),
            queryRow("label","olive","amount",6,"id","p"));
        queryRows(engine, "SELECT items.name, _key FROM items", Map.of(), queryRow("name","olive","_key","p"));
        var rows = engine.query("SELECT name, amount FROM items t").rows();
        eq(rowBag(List.of(queryRow("name","olive","amount",6))), rowBag(rows));
        rejects(UnsupportedOperationException.class, () -> rows.add(queryRow("name","new")));
        rejects(UnsupportedOperationException.class, () -> rows.remove(0));
        rejects(UnsupportedOperationException.class, () -> rows.clear());
        rejects(UnsupportedOperationException.class, () -> rows.addAll(List.of(queryRow("name","new"))));
        rejects(UnsupportedOperationException.class, () -> rows.set(0,queryRow("name","new")));
        rejects(UnsupportedOperationException.class, () -> rows.removeIf(value -> true));
        rejects(UnsupportedOperationException.class, () -> { var it=rows.iterator(); it.next(); it.remove(); });
        var empty = engine.query("SELECT name FROM items WHERE amount < 0").rows();
        eq(0,empty.size());
        rejects(UnsupportedOperationException.class, () -> empty.add(queryRow("name","new")));
        var row = rows.get(0);
        rejects(UnsupportedOperationException.class, () -> row.put("extra", 99));
        rejects(UnsupportedOperationException.class, () -> row.remove("amount"));
        rejects(UnsupportedOperationException.class, () -> row.clear());
        rejects(UnsupportedOperationException.class, () -> row.putAll(Map.of("extra",99)));
        rejects(UnsupportedOperationException.class, () -> row.replace("amount",99));
        rejects(UnsupportedOperationException.class, () -> row.entrySet().iterator().next().setValue(99));
        rejects(UnsupportedOperationException.class, () -> row.keySet().remove("amount"));
        rejects(UnsupportedOperationException.class, () -> row.values().remove("olive"));
        eq(rowBag(List.of(queryRow("name","olive","amount",6))), rowBag(rows));
        var several = entryEngine(Map.of("p", new Entry("olive", 6, 2, true, null),
            "q", new Entry("rowan", 9, 2, true, null), "s", new Entry("sage", 3, 2, true, null)));
        var many = several.query("SELECT name, amount FROM items").rows();
        eq(3, many.size());
        rejects(UnsupportedOperationException.class, () -> many.add(queryRow("name","new")));
        rejects(UnsupportedOperationException.class, () -> many.remove(1));
        rejects(UnsupportedOperationException.class, () -> many.set(2,queryRow("name","new")));
        rejects(UnsupportedOperationException.class, () -> many.get(1).put("extra", 99));
        rejects(UnsupportedOperationException.class, () -> many.get(2).remove("name"));
        eq(rowBag(List.of(queryRow("name","olive","amount",6),queryRow("name","rowan","amount",9),
            queryRow("name","sage","amount",3))), rowBag(many));
    ''')


def test_comparisons_operand_directions_and_literals(tmp_path):
    run_query_scenario(tmp_path, r'''
        var engine = entryEngine(Map.of(
            "lo", new Entry("alpha", -3L, 4L, false, null),
            "eq", new Entry("beta", 4L, 4L, true, "tag"),
            "hi", new Entry("gamma", 11L, 4L, false, "mark")));
        String[] operators = {"=", "!=", ">", ">=", "<", "<="};
        String[][] forward = {{"eq"},{"lo","hi"},{"hi"},{"eq","hi"},{"lo"},{"lo","eq"}};
        String[][] reverse = {{"eq"},{"lo","hi"},{"lo"},{"lo","eq"},{"hi"},{"eq","hi"}};
        for (int i=0; i<operators.length; i++) {
            queryIds(engine, "amount " + operators[i] + " 4", forward[i]);
            queryIds(engine, "4 " + operators[i] + " amount", reverse[i]);
            queryIds(engine, "amount " + operators[i] + " peer", forward[i]);
        }
        queryIds(engine, "name = 'beta'", "eq");
        queryIds(engine, "_key = 'eq'", "eq");
        queryIds(engine, "'hi' = _key", "hi");
        queryIds(engine, "_key != 'eq'", "lo","hi");
        queryIds(engine, "_key > 'hi'", "lo");
        queryIds(engine, "'gamma' = name", "hi");
        queryIds(engine, "active = true", "eq");
        queryIds(engine, "false = active", "lo","hi");
        queryIds(engine, "note = NULL", "lo");
        queryIds(engine, "amount = -3", "lo");
        queryIds(engine, "amount > 4.5", "hi");
        queryIds(engine, "amount = 4.5");
        queryIds(engine, "amount < 4.5", "lo","eq");
        eq(rowBag(List.of(queryRow("id","hi"))),rowBag(engine.query(
            "SELECT _key AS id FROM items WHERE amount > 4").rows()));
        var words = entryEngine(Map.of("phrase",new Entry("two words",1,1,true,null)));
        queryIds(words,"name = 'two words'","phrase");
        queryIds(engine, "-2.5 > amount", "lo");
        queryIds(engine, "3 < 4", "lo","eq","hi");
        queryIds(engine, "3 > 4");
        var fractions = entryEngine(Map.of(
            "negative", new Entry("fraction", -2.5, 1, true, null),
            "positive", new Entry("fraction", 4.5, 1, true, null)));
        queryIds(fractions, "amount = 4.5", "positive");
        queryIds(fractions, "-2.5 = amount", "negative");
        var limits = entryEngine(Map.of(
            "min", new Entry("minimum", Long.MIN_VALUE, 1, true, null),
            "max", new Entry("maximum", Long.MAX_VALUE, 1, true, null)));
        queryIds(limits, "amount = -9223372036854775808", "min");
        queryIds(limits, "amount = 9223372036854775807", "max");
    ''')


def test_current_bindings_null_and_missing_parameter(tmp_path):
    run_query_scenario(tmp_path, r'''
        var engine = entryEngine(Map.of(
            "a", new Entry("amber", 2, 1, true, null),
            "b", new Entry("blue", 7, 1, false, "north"),
            "c", new Entry("coral", 12, 1, true, "south")));
        queryBoundIds(engine, "amount > :cut", Map.of("cut", 3), "b","c");
        queryBoundIds(engine, "amount > :cut", Map.of("cut", 9), "c");
        queryBoundIds(engine, "amount > :cut", Map.of("cut", 1), "a","b","c");
        queryBoundIds(engine, "_key = :id", Map.of("id", "a"), "a");
        queryBoundIds(engine, "_key = :id", Map.of("id", "c"), "c");
        queryBoundIds(engine, "_key = :id", Map.of("id", "absent"));
        Map<String,Object> bindings = new HashMap<>();
        bindings.put("value", "north");
        queryBoundIds(engine, "note = :value", bindings, "b");
        bindings.put("value", null);
        queryBoundIds(engine, "note = :value", bindings, "a");
        bindings.put("value", "south");
        queryBoundIds(engine, "note = :value", bindings, "c");
        queryBoundIds(engine, ":value = active", Map.of("value", false), "b");
        queryBoundIds(engine, "amount = :value", Map.of("value", 7.0), "b");
        queryRefused(engine, "SELECT _key AS id FROM items WHERE note = :value", Map.of());
        queryRefused(engine, "SELECT _key AS id FROM items WHERE amount > :cut", Map.of());
        queryRefused(engine, "SELECT _key AS id FROM items WHERE amount > :cut LIMIT 2", Map.of());
        queryBoundIds(engine, "amount > :cut", Map.of("cut", 9), "c");
    ''')


def test_boolean_composition_and_parentheses(tmp_path):
    run_query_scenario(tmp_path, r'''
        var engine = entryEngine(Map.of(
            "a", new Entry("west", 2, 1, false, null),
            "b", new Entry("east", 8, 1, true, null),
            "c", new Entry("east", 3, 1, false, null),
            "d", new Entry("south", 9, 1, true, null)));
        queryIds(engine, "name = 'east' AND amount > 5", "b");
        queryIds(engine, "name = 'west' OR amount > 5", "a","b","d");
        queryIds(engine, "name = 'west' OR name = 'east' AND amount > 5", "a","b");
        queryIds(engine, "(name = 'west' OR name = 'east') AND amount > 5", "b");
        queryIds(engine, "amount > 5 AND name = 'east' OR name = 'west'", "a","b");
        queryIds(engine, "(name = 'west' OR (name = 'east' AND amount > 5)) AND active = true", "b");
        queryIds(engine, "amount > 0 AND name = 'east' AND active = true", "b");
        queryIds(engine, "name = 'west' OR name = 'east' OR name = 'south'", "a","b","c","d");
        queryIds(engine, "_key = 'b' AND amount > 5", "b");
        queryIds(engine, "_key = 'b' AND amount < 5");
        queryIds(engine, "amount < 5 AND _key = 'b'");
        queryIds(engine, "_key = 'b' OR name = 'west'", "a","b");
        queryIds(engine, "name = 'west' OR _key = 'b'", "a","b");
        queryIds(engine, "(_key = 'a' OR _key = 'c') AND name = 'east'", "c");
        queryRows(engine, "SELECT _key AS id FROM items WHERE _key = 'b' AND amount < 5 LIMIT 3", Map.of());
        queryRows(engine, "SELECT _key AS id FROM items WHERE _key = 'b' AND amount > 5 LIMIT 3", Map.of(),
            queryRow("id","b"));
    ''')


def test_null_numeric_and_non_numeric_comparison_semantics(tmp_path):
    run_query_scenario(tmp_path, r'''
        var nulls = entryEngine(Map.of(
            "nil", new Entry("alpha", null, 2, false, null),
            "two", new Entry("middle", 2, null, true, "present"),
            "ten", new Entry("zulu", 10, 10, true, "present")));
        queryIds(nulls, "amount = NULL", "nil");
        queryIds(nulls, "NULL = amount", "nil");
        queryIds(nulls, "amount != NULL", "two","ten");
        queryIds(nulls, "NULL != amount", "two","ten");
        queryIds(nulls, "NULL = NULL", "nil","two","ten");
        queryIds(nulls, "NULL != NULL");
        for (String op : List.of(">", ">=", "<", "<=")) {
            queryIds(nulls, "amount " + op + " NULL");
            queryIds(nulls, "NULL " + op + " amount");
        }
        queryIds(nulls, "amount > 2", "ten");
        queryIds(nulls, "amount < 10", "two");
        queryIds(nulls, "name < 'middle'", "nil");
        queryIds(nulls, "name >= 'middle'", "two","ten");
        queryIds(nulls, "active > false", "two","ten");
        var precise = entryEngine(Map.of(
            "lower",new Entry("value",16777216d,1,true,null),
            "upper",new Entry("value",16777217d,1,true,null)));
        queryIds(precise,"amount = 16777217","upper");
        queryIds(precise,"amount < 16777217","lower");
        var text = entryEngine(Map.of(
            "upper",new Entry("Beta",1,1,true,"null"),
            "lower",new Entry("beta",1,1,false,null)));
        queryIds(text,"name = 'Beta'","upper");
        queryIds(text,"name < 'alpha'","upper");
        queryIds(text,"note = NULL","lower");
        queryIds(text,"active = 'true'");
        Map<String,Entry> data = new HashMap<>();
        Number[] values = {(byte)2, (short)2, 2, 2L, 2.0f, 2.0d};
        String[] all = {"n0","n1","n2","n3","n4","n5"};
        for (int i=0; i<values.length; i++) data.put(all[i], new Entry("number",values[i],1,false,null));
        data.put("small", new Entry("small", -4, 1, false, null));
        data.put("large", new Entry("large", 10.0, 1, false, null));
        var numbers = entryEngine(data);
        for (Number value : values) queryBoundIds(numbers, "amount = :n", Map.of("n",value), all);
        queryIds(numbers, "amount > 2", "large");
        queryIds(numbers, "amount < 2", "small");
        queryIds(numbers, "amount != 2", "small","large");
        queryIds(numbers, "amount >= 2", "n0","n1","n2","n3","n4","n5","large");
        queryIds(numbers, "amount <= 2", "n0","n1","n2","n3","n4","n5","small");
        Map<Object,Entry> numericKeys = new HashMap<>();
        Object[] keyValues = {(byte)3, (short)300, 70000, 5000000000L, 2.5f, -0.75d};
        String[] keyLiterals = {"3", "300", "70000", "5000000000", "2.5", "-0.75"};
        Object[] otherCarriers = {3L, 300, 70000L, 5000000000d, 2.5d, -0.75f};
        for (int i=0; i<keyValues.length; i++) numericKeys.put(keyValues[i], new Entry("k"+i,i,1,true,null));
        var keyed = new QueryEngine(new Catalog().add("items", numericKeys, entrySchema()));
        for (int i=0; i<keyValues.length; i++) {
            queryRows(keyed, "SELECT name FROM items WHERE _key = " + keyLiterals[i], Map.of(), queryRow("name","k"+i));
            queryRows(keyed, "SELECT name FROM items WHERE _key = :k", Map.of("k",otherCarriers[i]),
                queryRow("name","k"+i));
        }
        queryRefused(nulls, "SELECT name FROM items WHERE name > 2", Map.of());
        queryRefused(nulls, "SELECT name FROM items WHERE active < 'true'", Map.of());
        var objects = entryEngine(Map.of("o",new Entry("object",new Object(),new Object(),true,null)));
        queryRefused(objects, "SELECT name FROM items WHERE amount > peer", Map.of());
        queryIds(nulls, "name = 'middle'", "two");
    ''')


def test_malformed_queries_unknown_tables_and_invalid_references(tmp_path):
    run_query_scenario(tmp_path, r'''
        var engine = entryEngine(Map.of("r", new Entry("valid", 5, 2, true, null)));
        queryRows(engine, "SELECT name FROM items", Map.of(), queryRow("name","valid"));
        for (String sql : List.of(
                "SELECT FROM items",
                "SELECT name FROM items WHERE name = 'unfinished",
                "SELECT name FROM items; extra",
                "SELECT name FROM items WHERE amount = 5 extra",
                "SELECT name FROM items WHERE (amount = 5",
                "SELECT name FROM items WHERE amount = 5)",
                "SELECT name FROM items WHERE amount = 5 AND",
                "SELECT name FROM items WHERE amount = 5 OR",
                "SELECT name FROM items WHERE amount =",
                "SELECT name FROM absent",
                "SELECT missing FROM items",
                "SELECT nowhere.name FROM items",
                "SELECT missing FROM items WHERE amount = 5 LIMIT 1",
                "SELECT nowhere.name FROM items WHERE amount = 5 LIMIT 1")) {
            queryRefused(engine, sql, Map.of());
        }
        queryRows(engine, "SELECT name FROM items WHERE amount = 5", Map.of(), queryRow("name","valid"));
    ''')
