# feature: F05
"""Public local-query callers and order-independent, multiplicity-aware observations."""

from pathlib import Path

from _helpers import compile_java, run_java
from F01_helpers import MAP_CHECK_SUPPORT


QUERY_SUPPORT = r'''
import dev.velqoramap.VelqoraMap;
import dev.velqoramap.query.Catalog;
import dev.velqoramap.query.Schema;
import dev.velqoramap.query.QueryEngine;
import dev.velqoramap.query.QueryResult;
import java.util.*;

public class F05QueryCheck extends F01MapCheck {
    record Entry(String name, Object amount, Object peer, Boolean active, String note) {}
    static Schema<Entry> entrySchema() {
        return Schema.<Entry>builder().column("name", Entry::name)
            .column("amount", Entry::amount).column("peer", Entry::peer)
            .column("active", Entry::active).column("note", Entry::note)
            .column("caption", e -> e.name() + "!").build();
    }
    static QueryEngine entryEngine(Map<String,Entry> data) {
        return new QueryEngine(new Catalog().add("items", data, entrySchema()));
    }
    static Map<String,Object> queryRow(Object... fields) {
        if (fields.length % 2 != 0) throw new AssertionError("Unpaired row fields");
        Map<String,Object> result = new HashMap<>();
        for (int i=0; i<fields.length; i+=2) result.put((String)fields[i], fields[i+1]);
        return result;
    }
    static java.math.BigDecimal exactNumber(Number number) {
        // Binary carriers are measured by their value, never their display spelling.
        if (number instanceof Float || number instanceof Double)
            return new java.math.BigDecimal(number.doubleValue());
        return new java.math.BigDecimal(number.toString());
    }
    record ResultNumber(boolean integral, java.math.BigDecimal value) {}
    static Object resultValue(Object value) {
        if (!(value instanceof Number number)) return value;
        boolean integral = number instanceof Byte || number instanceof Short || number instanceof Integer
            || number instanceof Long || number instanceof java.math.BigInteger;
        return new ResultNumber(integral, exactNumber(number).stripTrailingZeros());
    }
    static Map<String,Object> resultRow(Map<String,Object> row) {
        Map<String,Object> result = new HashMap<>();
        row.forEach((field,value) -> result.put(field,resultValue(value)));
        return result;
    }
    static List<Map<String,Object>> rowSequence(Iterable<Map<String,Object>> rows) {
        List<Map<String,Object>> result = new ArrayList<>();
        for (var row : rows) result.add(resultRow(row));
        return result;
    }
    static void orderedRows(Iterable<Map<String,Object>> expected, Iterable<Map<String,Object>> actual) {
        eq(rowSequence(expected),rowSequence(actual));
    }
    static Map<Map<String,Object>,Integer> rowBag(Iterable<Map<String,Object>> rows) {
        Map<Map<String,Object>,Integer> bag = new HashMap<>();
        for (Map<String,Object> row : rows) bag.merge(resultRow(row), 1, Integer::sum);
        return bag;
    }
    @SafeVarargs
    static void queryRows(QueryEngine engine, String sql, Map<String,?> bindings,
                          Map<String,Object>... expected) {
        // Complete consumption stays inside the caller's exception capture.
        var actual = rowBag(engine.query(sql, bindings).rows());
        try { eq(rowBag(Arrays.asList(expected)), actual); }
        catch (AssertionError failure) { throw new AssertionError(sql, failure); }
    }
    static void queryIds(QueryEngine engine, String predicate, String... ids) {
        queryBoundIds(engine, predicate, Map.of(), ids);
    }
    static void queryBoundIds(QueryEngine engine, String predicate,
                              Map<String,?> bindings, String... ids) {
        List<Map<String,Object>> expected = new ArrayList<>();
        for (String id : ids) expected.add(queryRow("id", id));
        var actual = rowBag(engine.query("SELECT _key AS id FROM items WHERE " + predicate,
                                         bindings).rows());
        try { eq(rowBag(expected), actual); }
        catch (AssertionError failure) { throw new AssertionError(predicate + " / " + bindings, failure); }
    }
    static void queryRefused(QueryEngine engine, String sql, Map<String,?> bindings) throws Exception {
        // The original exposes IllegalArgumentException, not a structured error kind.
        // The shared refusal carrier does not distinguish diagnostic categories.
        rejects(IllegalArgumentException.class, () -> rowBag(engine.query(sql, bindings).rows()));
    }
'''


def run_query_scenario(tmp_path, body, *, members=''):
    """Compile and run a real Java application against the harness-built product."""
    product = Path('/app/target/classes')
    assert product.is_dir(), 'Harness product classes are missing at /app/target/classes'
    parent = tmp_path / 'F01MapCheck.java'
    parent.write_text(MAP_CHECK_SUPPORT + '\n}\n}\n', encoding='utf-8')
    source = tmp_path / 'F05QueryCheck.java'
    source.write_text(QUERY_SUPPORT + members +
                      '\npublic static void main(String[] args) throws Exception {\n' + body +
                      '\nSystem.out.println("F05 checks completed");\n}\n}\n', encoding='utf-8')
    classes = tmp_path / 'classes'
    compile_java([parent, source], javac='javac', classpath=[product], output_dir=classes,
                 cwd=tmp_path, timeout=60, options=['--release', '17'])
    result = run_java('F05QueryCheck', java='java', classpath=[classes, product],
                      cwd=tmp_path, timeout=100, check=True)
    assert result.stdout == b'F05 checks completed\n', result
