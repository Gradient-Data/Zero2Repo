# feature: F08
"""Numeric-value observations and application tables for aggregate queries."""

AGGREGATE_SUPPORT = r'''
    record Measure(Object bucket, Object part, Object value, boolean included) {}
    static Schema<Measure> measureSchema() {
        return Schema.<Measure>builder().column("bucket", Measure::bucket)
            .column("part", Measure::part).column("value", Measure::value)
            .column("included", Measure::included).build();
    }
    static QueryEngine measures(Object... values) {
        Map<Integer,Measure> data = new LinkedHashMap<>();
        for (int i=0; i<values.length; i++) data.put(i,new Measure("one",null,values[i],true));
        return new QueryEngine(new Catalog().add("measures",data,measureSchema()));
    }
    static final String SUMMARIES = "COUNT(*) AS rows, COUNT(value) AS present, "
        + "SUM(value) AS total, AVG(value) AS mean, MIN(value) AS least, MAX(value) AS greatest";
    static Object numericValue(Object value) {
        if (value instanceof Number n) return exactNumber(n).stripTrailingZeros();
        return value;
    }
    static List<Map<String,Object>> numericRows(QueryEngine engine, String sql) {
        List<Map<String,Object>> result = new ArrayList<>();
        for (var row : engine.query(sql).rows()) {
            Map<String,Object> normalized = new HashMap<>();
            row.forEach((key,value) -> normalized.put(key,numericValue(value)));
            result.add(normalized);
        }
        return result;
    }
    record AggregateApproximation(java.math.BigDecimal value, java.math.BigDecimal bound) {}
    static AggregateApproximation near(Object value, double magnitude, int divisor) {
        var bound = java.math.BigDecimal.valueOf(magnitude).multiply(new java.math.BigDecimal("1e-9"))
            .divide(java.math.BigDecimal.valueOf(divisor),java.math.MathContext.DECIMAL128)
            .max(new java.math.BigDecimal("1e-12"));
        return new AggregateApproximation(new java.math.BigDecimal(value.toString()),bound);
    }
    static boolean aggregateMatch(Map<String,Object> expected, Map<String,Object> actual) {
        if (!expected.keySet().equals(actual.keySet())) return false;
        for (String field : expected.keySet()) {
            Object wanted = expected.get(field), got = actual.get(field);
            if (wanted instanceof AggregateApproximation approximation) {
                if (!(got instanceof Number n) || !Double.isFinite(n.doubleValue())) return false;
                if (exactNumber(n).subtract(approximation.value()).abs()
                    .compareTo(approximation.bound())>0) return false;
            } else if (!Objects.equals(numericValue(wanted),numericValue(got))) return false;
        }
        return true;
    }
    @SafeVarargs
    static void aggregateRows(QueryEngine engine, String sql, boolean ordered,
                              Map<String,Object>... expected) {
        var actual = numericRows(engine,sql);
        eq(expected.length,actual.size());
        for (var wanted : expected) {
            int match = -1;
            for (int i=0;i<(ordered ? Math.min(1,actual.size()) : actual.size());i++) {
                if (aggregateMatch(wanted,actual.get(i))) { match=i; break; }
            }
            if (match<0) throw new AssertionError(sql + "; expected " + wanted + "; remaining " + actual);
            actual.remove(match);
        }
    }
    static Map<String,Object> summary(long rows, long present, Object total, Object mean,
                                      Object least, Object greatest, double magnitude, boolean floating) {
        return queryRow("rows",rows,"present",present,
                        "total",total!=null && floating ? near(total,magnitude,1) : total,
                        "mean",mean==null ? null : near(mean,magnitude,(int)present),
                        "least",least,"greatest",greatest);
    }
    static void resultCategory(Object value, boolean floating) {
        boolean integral = value instanceof Byte || value instanceof Short || value instanceof Integer
            || value instanceof Long || value instanceof java.math.BigInteger;
        boolean fractional = value instanceof Float || value instanceof Double
            || value instanceof java.math.BigDecimal;
        if (!(floating ? fractional : integral))
            throw new AssertionError("Unexpected numeric category: " + value);
    }
    static void boundedError(Object value, java.math.BigDecimal expected, java.math.BigDecimal bound) {
        if (!(value instanceof Number n) || !Double.isFinite(n.doubleValue()))
            throw new AssertionError("Expected a finite numeric result: " + value);
        var error = exactNumber(n).subtract(expected).abs();
        if (error.compareTo(bound)>0)
            throw new AssertionError("Error " + error + " exceeds " + bound + "; result=" + value);
    }
    static void precisionQuery(Number[] values, boolean integral) {
        // Independent exact arithmetic over the actual binary floating inputs.
        var exact = java.math.BigDecimal.ZERO;
        var magnitude = java.math.BigDecimal.ZERO;
        int count = 0;
        for (Number n : values) {
            if (n == null) continue;
            var term = n instanceof Float || n instanceof Double
                ? new java.math.BigDecimal(n.doubleValue()) : exactNumber(n);
            exact = exact.add(term);
            magnitude = magnitude.add(term.abs());
            count++;
        }
        if (magnitude.compareTo(new java.math.BigDecimal(Long.MAX_VALUE))>0)
            throw new AssertionError("Fixture exceeds the documented magnitude domain");
        var result = measures((Object[])values).query(
            "SELECT SUM(value) AS total, AVG(value) AS mean FROM measures").rows();
        eq(1,result.size());
        eq(Set.of("total","mean"),result.get(0).keySet());
        var floor = new java.math.BigDecimal("1e-12");
        var scaled = magnitude.multiply(new java.math.BigDecimal("1e-9"));
        var divisor = java.math.BigDecimal.valueOf(count);
        var average = exact.divide(divisor,java.math.MathContext.DECIMAL128);
        var meanBound = scaled.divide(divisor,java.math.MathContext.DECIMAL128).max(floor);
        boundedError(result.get(0).get("total"),exact,integral ? java.math.BigDecimal.ZERO : scaled.max(floor));
        boundedError(result.get(0).get("mean"),average,meanBound);
        if (magnitude.signum()==0) {
            eq(numericValue(0),numericValue(result.get(0).get("total")));
            eq(numericValue(0),numericValue(result.get(0).get("mean")));
        }
    }
'''
