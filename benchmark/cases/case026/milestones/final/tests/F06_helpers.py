# feature: F06
"""Sequence observations for materialized public query results."""

ORDER_OBSERVATIONS = r'''
    @SafeVarargs
    static void orderedQueryRows(QueryEngine engine, String sql, Map<String,Object>... expected) {
        var actual = new ArrayList<>(engine.query(sql).rows());
        try { orderedRows(Arrays.asList(expected), actual); }
        catch (AssertionError failure) { throw new AssertionError(sql, failure); }
    }
    static void orderedQueryIds(QueryEngine engine, String sql, String... expected) {
        List<Object> actual = new ArrayList<>();
        for (var row : engine.query(sql).rows()) {
            if (!row.containsKey("id")) throw new AssertionError("Missing projected id field");
            actual.add(row.get("id"));
        }
        try { eq(Arrays.asList(expected), actual); }
        catch (AssertionError failure) { throw new AssertionError(sql, failure); }
    }
'''
