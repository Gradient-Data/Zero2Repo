# feature: F09
"""F09 application observations; shared compilation and row checks are imported."""

import json
from statistics import median
from pathlib import Path

from _helpers import compile_java, run_java
from F01_helpers import MAP_CHECK_SUPPORT
from F05_helpers import QUERY_SUPPORT


INDEX_CHECKS = r'''
    static void checkIndexedState(QueryEngine engine, Map<String,JoinEntry> expected, Set<Object> history) {
        for (Object value : history) {
            var wanted = new ArrayList<Map<String,Object>>();
            expected.forEach((key,row) -> {
                if (Objects.equals(value,row.link()))
                    wanted.add(queryRow("id",key,"label",row.label(),"link",row.link()));
            });
            String sql = "SELECT _key AS id, label, link FROM records WHERE link = :value";
            eq(rowBag(wanted),rowBag(engine.query(sql,queryRow("value",value)).rows()));
            eq(rowBag(wanted),rowBag(engine.stream(sql,queryRow("value",value))));
        }
        // A second configured index on the same table follows the same completed changes.
        for (boolean value : List.of(true,false)) {
            var wanted = new ArrayList<Map<String,Object>>();
            expected.forEach((key,row) -> {
                if (row.included() == value) wanted.add(queryRow("id",key,"label",row.label()));
            });
            eq(rowBag(wanted),rowBag(engine.query(
                "SELECT _key AS id, label FROM records WHERE included = :value",
                Map.of("value",value)).rows()));
        }
    }
'''


# Workload is fixed before observing the candidate: 20,000 / 200,000 rows,
# 8-character keys and tags, 64-character payloads, one match or five prefix rows.
# Independent full-input traversal must show >=4x growth and exceed timer/call
# overhead by >=20x, or the environment cannot support this measurement.
# Nine alternating samples follow warmup; all samples (including slow ones) stay.
# Reference calibration (fixed 768 MiB heap): 11.58x / 12.72x full-input growth;
# key/index/limit/stream median ratios: 0.879 / 0.915 / 0.987 / 1.018.
# Full-scan defects measured 11.46x / 11.14x; eager-prefix defects 13.06x / 12.94x.
# Raw samples and exact commands are retained in the F09 author evidence directory.
# Selective spellings (two reference runs, original product): all eight modes
# (String key and indexed text bound, literal, value-first operand order, indexed
# int value, application-record key) measured 0.92-1.03x. Defects that full-scan
# a single spelling measured 11.4-13.7x on that spelling (other modes 0.86-1.08x).
# These observations document reserve; the only product growth bound remains <4x.
ACCESS_MEASUREMENT = r'''
    record AccessRecord(String tag, int serial, String payload) {}
    record AccessId(String code) {}
    record AccessFixture(QueryEngine engine, Map<String,AccessRecord> reference) {}
    // Selective spellings: each is an equality query with one match (FP-09.02).
    static final List<String> SELECTIVE_MODES = List.of("key","index","key_literal","index_literal",
        "key_reversed","index_reversed","index_number","key_object");
    static volatile long accessSink;
    static String accessKey(int i) {
        String digits = Integer.toString(i);
        return "k" + "0".repeat(7-digits.length()) + digits;
    }
    static AccessFixture accessFixture(int size, boolean indexed) {
        var reference = new HashMap<String,AccessRecord>();
        for (int i=0;i<size;i++) {
            String key = accessKey(i);
            reference.put(key,new AccessRecord(key,i,"payload:"+key+"x".repeat(48)));
        }
        var data = new VelqoraMap<String,AccessRecord>(reference);
        var schema = Schema.<AccessRecord>builder().column("tag",AccessRecord::tag)
            .column("serial",AccessRecord::serial).column("payload",AccessRecord::payload).build();
        var catalog = new Catalog().add("records",data,schema);
        if (indexed) {
            catalog.index("records","tag").index("records","serial");
            // Same rows keyed by a non-String, non-numeric application key.
            var coded = new VelqoraMap<AccessId,AccessRecord>();
            reference.forEach((key,value) -> coded.put(new AccessId(key),value));
            catalog.add("coded",coded,schema);
        }
        return new AccessFixture(new QueryEngine(catalog),reference);
    }
    static long accessFullScan(AccessFixture fixture) {
        long total = 0;
        for (var entry : fixture.reference().entrySet()) {
            total += entry.getKey().charAt(7) + entry.getValue().tag().charAt(6)
                + entry.getValue().payload().charAt(63);
        }
        accessSink = total;
        return total;
    }
    static List<Map<String,Object>> accessRead(AccessFixture fixture, String mode, int iteration) {
        String select = "SELECT _key AS id, tag, payload FROM records";
        if (mode.equals("stream")) {
            var rows = new ArrayList<Map<String,Object>>();
            // Timing includes public call, iterator construction, and first next().
            var iterator = fixture.engine().stream(select,Map.of()).iterator();
            while (rows.size()<5 && iterator.hasNext()) rows.add(iterator.next());
            return rows;
        }
        if (mode.equals("limit")) return new ArrayList<>(fixture.engine().query(select+" LIMIT 5").rows());
        int number = iteration%2 == 0 ? 7 : 53;
        String wanted = accessKey(number);
        String where = switch (mode) {
            case "key", "key_object" -> " WHERE _key = :wanted";
            case "index" -> " WHERE tag = :wanted";
            case "key_literal" -> " WHERE _key = '"+wanted+"'";
            case "index_literal" -> " WHERE tag = '"+wanted+"'";
            case "key_reversed" -> " WHERE :wanted = _key";
            case "index_reversed" -> " WHERE :wanted = tag";
            case "index_number" -> " WHERE serial = :wanted";
            default -> throw new AssertionError("Unknown access mode "+mode);
        };
        Object bound = mode.equals("index_number") ? (Object)number
            : mode.equals("key_object") ? new AccessId(wanted) : wanted;
        String table = mode.equals("key_object") ? select.replace("FROM records","FROM coded") : select;
        return new ArrayList<>(fixture.engine().query(table+where,Map.of("wanted",bound)).rows());
    }
    static void accessValidate(AccessFixture fixture, String mode, int iteration,
                               List<Map<String,Object>> rows) {
        boolean selective = SELECTIVE_MODES.contains(mode);
        eq(selective ? 1 : 5,rows.size());
        var seen = new HashSet<Object>();
        for (var row : rows) {
            Object id = row.get("id");
            Object key = mode.equals("key_object") && id instanceof AccessId coded ? coded.code() : id;
            var expected = fixture.reference().get(key);
            if (expected == null || !seen.add(key)) throw new AssertionError("Invented or repeated row: "+row);
            eq(queryRow("id",id,"tag",expected.tag(),"payload",expected.payload()),row);
            if (selective) eq(accessKey(iteration%2 == 0 ? 7 : 53),key);
        }
    }
    static double accessSample(AccessFixture fixture, String mode) {
        final int repeats = 32;
        var results = new ArrayList<List<Map<String,Object>>>(repeats);
        long before = System.nanoTime();
        for (int i=0;i<repeats;i++) results.add(accessRead(fixture,mode,i));
        long elapsed = System.nanoTime()-before;
        for (int i=0;i<repeats;i++) accessValidate(fixture,mode,i,results.get(i));
        return elapsed/(double)repeats;
    }
    static double accessScanSample(AccessFixture fixture) {
        long start = System.nanoTime();
        for (int i=0;i<8;i++) accessFullScan(fixture);
        return (System.nanoTime()-start)/8.0;
    }
    static double accessMedian(double[] values) {
        var copy = values.clone(); Arrays.sort(copy); return copy[copy.length/2];
    }
    static String accessPair(String name, double[][] samples) {
        return "\""+name+"\":{\"small_ns\":"+Arrays.toString(samples[0])+
            ",\"large_ns\":"+Arrays.toString(samples[1])+"}";
    }
    static void measureAccess(String kind) throws Exception {
        boolean indexed = kind.equals("selective");
        var small = accessFixture(20000,indexed);
        var large = accessFixture(200000,indexed);
        // Product-independent traversal calibrates fixed input sizes, never tunes them.
        for (int i=0;i<24;i++) { accessFullScan(small); accessFullScan(large); }
        double[][] calibration = new double[2][9];
        double[] overhead = new double[9];
        for (int i=0;i<9;i++) {
            long start = System.nanoTime();
            for (int j=0;j<32;j++) accessSink++;
            overhead[i]=(System.nanoTime()-start)/32.0;
            for (int turn=0;turn<2;turn++) {
                int side=(i+turn)%2;
                calibration[side][i]=accessScanSample(side==0 ? small : large);
            }
        }
        StringBuilder report = new StringBuilder("{");
        report.append(accessPair("calibration",calibration));
        report.append(",\"overhead_ns\":").append(Arrays.toString(overhead));
        // Record calibration even if its environmental precondition fails.
        java.nio.file.Files.writeString(java.nio.file.Path.of("access-report.json"),report+"}");
        if (accessMedian(calibration[1]) < 4*accessMedian(calibration[0]))
            throw new AssertionError("Independent full-input traversal cannot resolve fourfold growth: "+report);
        if (accessMedian(calibration[0]) < 20*accessMedian(overhead))
            throw new AssertionError("Input traversal is obscured by measurement overhead: "+report);
        var warm = accessFixture(100,indexed);
        for (String mode : indexed ? SELECTIVE_MODES : List.of("limit","stream")) {
            for (int i=0;i<2500;i++) accessValidate(warm,mode,i,accessRead(warm,mode,i));
            for (int i=0;i<32;i++) {
                accessValidate(small,mode,i,accessRead(small,mode,i));
                accessValidate(large,mode,i,accessRead(large,mode,i));
            }
            double[][] samples = new double[2][9];
            for (int i=0;i<9;i++) for (int turn=0;turn<2;turn++) {
                int side=(i+turn)%2;
                samples[side][i]=accessSample(side==0 ? small : large,mode);
            }
            report.append(",").append(accessPair(mode,samples));
        }
        java.nio.file.Files.writeString(java.nio.file.Path.of("access-report.json"),report+"}");
    }
'''


# Equality spellings timed for FP-09.02: bound and literal values, either operand
# order, a numeric indexed value, and a non-String non-numeric map key.
SELECTIVE_MODES = ("key", "index", "key_literal", "index_literal", "key_reversed",
                   "index_reversed", "index_number", "key_object")


def run_access_measurement(tmp_path, kind):
    """Measure warmed public operations in one JVM and retain every sample."""
    assert kind in ("selective", "prefix")
    product = Path("/app/target/classes")
    assert product.is_dir(), "Harness product classes are missing"
    parent = tmp_path / "F01MapCheck.java"
    parent.write_text(MAP_CHECK_SUPPORT + "\n}\n}\n", encoding="utf-8")
    query = tmp_path / "F05QueryCheck.java"
    query.write_text(QUERY_SUPPORT + "\n}\n", encoding="utf-8")
    source = tmp_path / "F09Measure.java"
    source.write_text(
        "import dev.velqoramap.VelqoraMap;\nimport dev.velqoramap.query.*;\nimport java.util.*;\n"
        + "public class F09Measure extends F05QueryCheck {\n" + ACCESS_MEASUREMENT
        + 'public static void main(String[] args) throws Exception { measureAccess(args[0]); }\n}\n',
        encoding="utf-8",
    )
    classes = tmp_path / "classes"
    compile_java([parent, query, source], javac="javac", classpath=[product],
                 output_dir=classes, cwd=tmp_path, timeout=60, options=["--release", "17"])
    # Fix the same ample JVM heap for both sizes, avoiding host-sized ergonomics.
    run_java("F09Measure", java="java", classpath=[classes, product], cwd=tmp_path,
             args=[kind], jvm_args=["-Xms768m", "-Xmx768m"], timeout=120, check=True)
    report = json.loads((tmp_path / "access-report.json").read_text(encoding="utf-8"))
    modes = SELECTIVE_MODES if kind == "selective" else ("limit", "stream")
    for mode in ("calibration", *modes):
        sample = report[mode]
        sample["small_median_ns"] = median(sample["small_ns"])
        sample["large_median_ns"] = median(sample["large_ns"])
        sample["growth"] = sample["large_median_ns"] / sample["small_median_ns"]
    print("F09 measurements " + json.dumps(report, sort_keys=True))
    (tmp_path / "access-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for mode in modes:
        assert report[mode]["growth"] < 4, f"{mode}: {report}"
