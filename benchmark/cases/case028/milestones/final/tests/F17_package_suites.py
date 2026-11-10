# feature: F17
"""Acceptance tests for the package-test command (F17.T01–F17.T09)."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import re
import secrets

from F17_helpers import F12Proxy, f10_cli, f17_run, f17_sources


def test_suite_timeout_default_override_and_disabled(f17_run):
    # F17.T04. Configuration and real expiration are separate observations.
    # TestMain brackets suite startup; the read delay is measured rather than
    # accepting an arbitrary positive deadline. Actual default expiration is
    # intentionally not observed (it alone exceeds the replay budget).
    configuration = f17_sources('''package suite
import ("fmt"; "os"; "testing"; "time")
var started time.Time
func TestMain(m *testing.M) {
    started = time.Now()
    os.Exit(m.Run())
}
func TestDeadline(t *testing.T) {
    deadline, ok := t.Deadline()
    remaining := -int64(time.Since(deadline))
    observed := int64(time.Since(started))
    note(fmt.Sprintf("%t %d %d", ok, remaining, observed))
}
''')
    replacement = 17 + secrets.randbelow(13)
    for flags, seconds in (((), 600), ((f"-timeout={replacement}s",), replacement),
                           (("-timeout=0",), None)):
        suite = f17_run(configuration, ("-v", *flags))
        suite.passed(["TestDeadline"])
        assert len(suite.effects) == 1, suite
        enabled, remaining_ns, observed_ns = suite.effects[0].split()
        remaining_ns, observed_ns = int(remaining_ns), int(observed_ns)
        # Fail explicitly if scheduling prevents a discriminating observation.
        assert 0 <= observed_ns <= 2_000_000_000, suite
        if seconds is None:
            assert enabled == "false", suite
        else:
            assert enabled == "true", suite
            assert seconds * 1_000_000_000 - observed_ns <= remaining_ns <= seconds * 1_000_000_000, suite

    # Identical finite workloads; only the timeout differs. Independent host
    # monotonic intervals start at the execution marker, not process launch.
    workload_seconds = 5 + secrets.randbelow(3)
    finished = "clock-finished-" + secrets.token_hex(8)
    files = f17_sources('''package suite
import ("fmt"; "testing"; "time")
func TestClock(t *testing.T) {
    fmt.Println("clock-start")
    time.Sleep(WORKLOAD*time.Second)
    note("FINISHED")
}
'''.replace("WORKLOAD", str(workload_seconds)).replace("FINISHED", finished))
    options = {"short": ("-timeout=2s",), "long": ("-timeout=15s",),
               "disabled": ("-timeout=0",)}
    with ThreadPoolExecutor(max_workers=3) as executor:
        pending = {name: executor.submit(f17_run, files, ("-v", *flags),
                                        timeout=45, start_marker=b"clock-start\n")
                   for name, flags in options.items()}
        outcomes = {name: future.result() for name, future in pending.items()}
    suite = outcomes["short"]
    assert suite.process.returncode == 2, suite.process
    assert b"panic: test timed out after 2s\n" in suite.process.stderr, suite.process
    assert suite.cases("run") == ["TestClock"], suite.events
    assert suite.effects == [], suite
    # Half a second allows marker delivery/startup; up to two seconds allows
    # scheduling at termination, still strictly before the finite workload.
    assert 1.5 <= suite.suite_elapsed <= 4, suite
    for name in ("long", "disabled"):
        suite = outcomes[name]
        suite.passed(["TestClock"])
        assert suite.effects == [finished], suite
        assert workload_seconds - 0.5 <= suite.suite_elapsed <= workload_seconds + 5, suite


def test_local_default_import_targets_and_source_selection(f17_run, tmp_path):
    # F17.T01: calls cross two later declarations and requires build filtering.
    files = f17_sources('''package suite
import "testing"
func TestResolution(t *testing.T) {
    if Result() != 47 { t.Fatal(Result()) }
    note("resolved:47")
}
''', **{
        "a.go": "package suite\nfunc Result() int { return seed*4+3 }\n",
        "z.go": "package suite\nvar seed = 11\n",
        "excluded_test.go": '//go:build ignore\n\npackage suite\nimport "testing"\n'
                            'func TestExcluded(t *testing.T) { t.Fatal("excluded source ran") }\n',
        "excluded.go": '//go:build ignore\n\npackage suite\nvar seed = 999\n',
    })
    default = f17_run(files, target=None)
    default.passed(["TestResolution"])
    assert default.effects == ["resolved:47"], default
    # Rename the declaration files to reverse their read order.
    reversed_files = dict(files)
    reversed_files["a.go"], reversed_files["z.go"] = files["z.go"], files["a.go"]
    explicit = f17_run({"pkg/" + name: data for name, data in reversed_files.items()}, target="./pkg")
    explicit.passed(["TestResolution"])
    assert explicit.effects == ["resolved:47"], explicit
    proxy = F12Proxy(tmp_path / "proxy")
    proxy.publish("suite.test/resolution", "v1.0.0", files)
    with proxy.serving():
        imported = f17_run({}, target="suite.test/resolution", proxy=proxy.url)
    imported.passed(["TestResolution"])
    assert imported.effects == ["resolved:47"], imported
    # No source selected, despite the presence of an excluded test file.
    refused = f17_run({"plain.go": "package suite\nvar N = 1\n",
                      "excluded_test.go": files["excluded_test.go"]})
    assert refused.process.returncode == 1, refused.process
    assert refused.process.stderr.strip(), refused.process
    assert refused.cases("run") == [], refused.events


def test_case_kinds_declaration_order_and_unordered_examples(f17_run):
    # F17.T02. Lexical name order deliberately differs from declaration order.
    files = f17_sources('''package suite
import ("fmt"; "testing")
func TestZulu(t *testing.T) { note("zulu") }
func TestAlpha(t *testing.T) {
    t.Run("Child", func(t *testing.T) { note("child") })
}
func TestMiddle(t *testing.T) { note("middle") }
func BenchmarkCompute(b *testing.B) {
    sum := 0
    for i := 0; i < b.N; i++ { sum += 17 }
    if sum != 17*b.N { b.Fatal(sum) }
    note(fmt.Sprintf("bench:%d", sum))
}
func ExampleOrdered() {
    note("ordered")
    fmt.Println("north"); fmt.Println("south")
    // Output:
    // north
    // south
}
func ExampleUnordered() {
    note("unordered")
    fmt.Println("red"); fmt.Println("blue"); fmt.Println("red")
    // Unordered output:
    // blue
    // red
    // red
}
func ExampleNoOutput() { note("not executable") }
''')
    baseline = f17_run(files)
    baseline.passed(["TestZulu", "TestAlpha/Child", "TestAlpha", "TestMiddle",
                     "ExampleOrdered", "ExampleUnordered"])
    assert Counter(baseline.effects) == Counter(["zulu", "child", "middle", "ordered", "unordered"]), baseline
    assert [name for name in baseline.cases("run") if name.startswith("Test") and "/" not in name] == [
        "TestZulu", "TestAlpha", "TestMiddle"], baseline.events
    assert [effect for effect in baseline.effects if effect in ("zulu", "child", "middle")] == [
        "zulu", "child", "middle"], baseline
    selected = f17_run(files, ("-v", "-run=^$", "-bench=^BenchmarkCompute$", "-benchtime=1x"))
    assert selected.process.returncode == 0, selected.process
    assert selected.effects == ["bench:17"], selected
    # For three tests, each of the six permutations has probability 1/6.
    # With 128 independent fresh runs, the probability of missing any order
    # is at most 6*(5/6)**128 < 4.5e-10. The chance a bin reaches 64 is
    # at most 6*exp(-128*D(1/2 || 1/6)) < 3e-16. These wide bounds reject
    # fixed order and missing permutations without pinning a random seed.
    orders = Counter()
    for _ in range(128):
        shuffled = f17_run(files, ("-v", "-shuffle=on"))
        assert shuffled.process.returncode == 0, shuffled.process
        assert Counter(shuffled.cases("pass")) == Counter(baseline.cases("pass")), shuffled.events
        assert Counter(shuffled.effects) == Counter(baseline.effects), shuffled
        order = tuple(name for name in shuffled.cases("run")
                      if name.startswith("Test") and "/" not in name)
        assert set(order) == {"TestZulu", "TestAlpha", "TestMiddle"}, order
        orders[order] += 1
    assert len(orders) == 6 and max(orders.values()) < 64, orders


def test_selection_subtests_repetition_short_and_verbose(f17_run):
    # F17.T03. Every contrast uses a fresh package/process and identical input.
    files = f17_sources('''package suite
import ("fmt"; "testing")
func TestZulu(t *testing.T) { note("zulu") }
func TestGroup(t *testing.T) {
    t.Run("Alpha", func(t *testing.T) { note("alpha") })
    t.Run("Beta", func(t *testing.T) { note("beta") })
}
func TestMode(t *testing.T) {
    if testing.Short() { note("short"); t.Skip("short mode selected") }
    note("normal")
}
func BenchmarkFirst(b *testing.B) { note("first-benchmark") }
func BenchmarkSecond(b *testing.B) { note("second-benchmark") }
func ExampleSelected() {
    note("example"); fmt.Println("sample")
    // Output: sample
}
''')
    all_cases = ["TestZulu", "TestGroup/Alpha", "TestGroup/Beta", "TestGroup", "TestMode", "ExampleSelected"]
    baseline = f17_run(files)
    baseline.passed(all_cases)
    assert Counter(baseline.effects) == Counter(["zulu", "alpha", "beta", "normal", "example"]), baseline
    quiet = f17_run(files, ())
    assert quiet.process.returncode == 0, quiet.process
    assert Counter(quiet.effects) == Counter(baseline.effects), quiet
    assert quiet.cases("run") == [] and quiet.cases("pass") == [], quiet.events
    selected = f17_run(files, ("-v", "-run=^Test(Zulu|Group)$", "-skip=^TestZulu$"))
    selected.passed(["TestGroup/Alpha", "TestGroup/Beta", "TestGroup"])
    assert selected.effects == ["alpha", "beta"], selected
    child = f17_run(files, ("-v", "-run=^TestGroup$/^Beta$"))
    child.passed(["TestGroup/Beta", "TestGroup"])
    assert child.effects == ["beta"], child
    repeated = f17_run(files, ("-v", "-run=^TestZulu$", "-count=3"))
    repeated.passed(["TestZulu"] * 3)
    assert repeated.effects == ["zulu"] * 3, repeated
    short = f17_run(files, ("-v", "-short"))
    short.passed([name for name in all_cases if name != "TestMode"])
    assert short.cases("skip") == ["TestMode"], short.events
    assert Counter(short.effects) == Counter(["zulu", "alpha", "beta", "short", "example"]), short
    explicit_long = f17_run(files, ("-v", "-short=false"))
    explicit_long.passed(all_cases)
    assert Counter(explicit_long.effects) == Counter(baseline.effects), explicit_long
    bench = f17_run(files, ("-v", "-run=^$", "-bench=^BenchmarkSecond$", "-benchtime=1x"))
    assert bench.process.returncode == 0, bench.process
    assert bench.effects == ["second-benchmark"], bench
    # Top-level exclusion and subtest inclusion are measured above. The
    # original drops the entire parent for a subtest exclusion pattern;
    # that unsupported interaction is outside the specified matching scope.


def test_package_driver_setup_relative_data_and_exit(f17_run, tmp_path):
    # F17.T05. TestMain setup must affect a real test reading package data.
    source = '''package suite
import ("os"; "testing")
var prepared string
func TestFixture(t *testing.T) {
    data, err := os.ReadFile("testdata/input.txt")
    if err != nil { t.Fatal(err) }
    if prepared != "ready:cedar" || string(data) != "cedar" { t.Fatal(prepared, string(data)) }
    note(prepared + ":" + string(data))
    TEST_BODY
}
func TestMain(m *testing.M) {
    prepared = "ready:cedar"
    note("setup")
    code := m.Run()
    note("teardown")
    DRIVER_END
}
'''
    variants = [
        ("local", "", "os.Exit(code)", 0),
        ("imported", "", "os.Exit(code)", 0),
        ("returned", 't.Error("intentional assertion")', "_ = code", 1),
        ("controlled", "", "os.Exit(7)", 7),
    ]
    for mode, body, ending, status in variants:
        files = f17_sources(source.replace("TEST_BODY", body).replace("DRIVER_END", ending),
                            **{"testdata/input.txt": "cedar"})
        if mode in ("imported", "controlled"):
            proxy = F12Proxy(tmp_path / mode)
            proxy.publish("suite.test/driver", "v1.0.0", files)
            with proxy.serving():
                suite = f17_run({}, target="suite.test/driver", proxy=proxy.url)
        else:
            suite = f17_run({"pkg/" + name: content for name, content in files.items()}, target="./pkg")
        assert suite.process.returncode == status, suite.process
        assert suite.effects == ["setup", "ready:cedar:cedar", "teardown"], suite
        assert suite.cases("run") == ["TestFixture"], suite.events
        assert suite.cases("fail" if body else "pass") == ["TestFixture"], suite.events


def test_assertion_fatal_benchmark_example_failures_and_no_match(f17_run):
    # F17.T06. A live success baseline precedes each failure comparison.
    source = '''package suite
import "testing"
func TestAssert(t *testing.T) { note("assert"); ASSERT; note("after-assert") }
func TestFatal(t *testing.T) { note("fatal"); FATAL; note("after-fatal") }
func BenchmarkFailure(b *testing.B) { note("benchmark"); BENCH }
'''
    passing = source.replace("ASSERT", "").replace("FATAL", "").replace("BENCH", "")
    flags = ("-v", "-bench=^BenchmarkFailure$", "-benchtime=1x")
    baseline = f17_run(f17_sources(passing), flags)
    assert baseline.process.returncode == 0, baseline.process
    assert baseline.effects == ["assert", "after-assert", "fatal", "after-fatal", "benchmark"], baseline
    failing = source.replace("ASSERT", 't.Error("assertion failed")').replace(
        "FATAL", 't.Fatal("fatal assertion")').replace("BENCH", 'b.Fatal("benchmark assertion")')
    failure = f17_run(f17_sources(failing), flags)
    assert failure.process.returncode == 1, failure.process
    assert set(failure.cases("fail")) == {"TestAssert", "TestFatal"}, failure.events
    assert failure.effects == ["assert", "after-assert", "fatal"], failure
    # Go testing does not start benchmarks after ordinary tests have failed.
    bench_failure = f17_run(f17_sources(failing), (*flags, "-run=^$"))
    assert bench_failure.process.returncode == 1, bench_failure.process
    assert bench_failure.cases("fail") == ["BenchmarkFailure"], bench_failure.events
    assert bench_failure.effects == ["benchmark"], bench_failure

    # Go's Output is an ordered sequence; Unordered output is a multiset,
    # not a set (duplicates matter). Each source has both success and failure.
    for directive, expected, actual in (
        ("Output", ["east", "west"], ["west", "east"]),
        ("Unordered output", ["red", "blue", "red"], ["red", "green", "red"]),
        ("Unordered output", ["red", "blue", "red"], ["red", "blue"]),
    ):
        for lines, wanted_status in ((expected, 0), (actual, 1)):
            prints = "\n".join('fmt.Println(' + repr(line).replace("'", '"') + ')' for line in lines)
            comments = "\n".join("// " + line for line in expected)
            example = ('package suite\nimport "fmt"\nfunc ExampleCheck() {\n'
                       'note("example-ran")\n' + prints + '\n// ' + directive + ':\n' + comments + '\n}\n')
            suite = f17_run(f17_sources(example))
            assert suite.process.returncode == wanted_status, suite.process
            assert suite.cases("fail" if wanted_status else "pass") == ["ExampleCheck"], suite.events
            assert suite.effects == ["example-ran"], suite
    no_match_files = f17_sources('package suite\nimport "testing"\n'
                                 'func TestPresent(t *testing.T) { note("present") }\n')
    present = f17_run(no_match_files)
    present.passed(["TestPresent"])
    assert present.effects == ["present"], present
    empty = f17_run(no_match_files, ("-v", "-run=^Absent$"))
    assert empty.process.returncode == 0, empty.process
    reports = [line[len(b"testing: warning: "):]
               for line in empty.process.stderr.splitlines()
               if line.startswith(b"testing: warning: ")]
    assert reports and all(report.strip() for report in reports), empty.process
    assert empty.cases("run") == [] and empty.effects == [], empty


def test_internal_external_shared_package_and_dependency_exclusion(f17_run, tmp_path):
    # F17.T07: initialization changes the target; the external import must see
    # that same target instance. Dependency tests must not run or even load.
    proxy = F12Proxy(tmp_path / "proxy")
    proxy.publish("suite.test/shared", "v1.0.0", {
        "value.go": 'package suite\nimport "suite.test/shared/dependency"\n'
                    'var Value = dependency.Scale(3)\nfunc Add(n int) int { Value += n; return Value }\n'
                    'func Compute(n int) int { return dependency.Scale(n) }\n',
        "internal_test.go": '''package suite
import "testing"
func init() { Value = 41 }
func TestInternal(t *testing.T) {
    if Compute(4) != 28 { t.Fatal(Compute(4)) }
    note("internal:28")
}
''',
        "support_test.go": f17_sources("")["support_test.go"],
        "external_test.go": '''package suite_test
import ("os"; "testing"; suite "suite.test/shared")
func TestExternal(t *testing.T) {
    if suite.Value != 41 || suite.Add(5) != 46 { t.Fatal(suite.Value) }
    f, err := os.OpenFile(os.Getenv("F17_RECORD"), os.O_APPEND|os.O_WRONLY, 0600)
    if err != nil { t.Fatal(err) }
    if _, err := f.WriteString("external:46\\n"); err != nil { t.Fatal(err) }
    if err := f.Close(); err != nil { t.Fatal(err) }
}
''',
        "dependency/dep.go": "package dependency\nfunc Scale(n int) int { return n*7 }\n",
        "dependency/dep_test.go": 'package dependency\nimport "testing"\n'
                                  'func TestMustNotLoad(t *testing.T) { UndefinedDependencyTest() }\n',
    })
    with proxy.serving():
        suite = f17_run({}, target="suite.test/shared", proxy=proxy.url)
    assert suite.process.returncode == 0, suite.process
    assert set(suite.cases("pass")) == {"TestInternal", "TestExternal"}, suite.events
    assert Counter(suite.effects) == Counter(["internal:28", "external:46"]), suite


def test_import_path_partial_suite_and_unavailable_implementation(f17_run, tmp_path):
    # F17.T08: each omitted file is independently removable. All valid tests
    # have positive events/effects, so silent no-op or whole-suite omission fails.
    files = f17_sources('''package suite
import "testing"
func TestRemaining(t *testing.T) { if Compute(5) != 38 { t.Fatal(Compute(5)) }; note("remaining:38") }
''', **{
        "impl.go": "package suite\nfunc Compute(n int) int { return n*7+3 }\n",
        "call_test.go": 'package suite\nimport "testing"\n'
                        'func TestCall(t *testing.T) { MissingCall(); note("call") }\n',
        "init_test.go": 'package suite\nimport "testing"\nvar bad = MissingInitializer\n'
                        'func TestInit(t *testing.T) { note("initializer") }\n',
    })
    healthy = dict(files)
    healthy["call_test.go"] = healthy["call_test.go"].replace("MissingCall(); ", "")
    healthy["init_test.go"] = healthy["init_test.go"].replace("MissingInitializer", "17")
    broken = dict(files)
    broken["impl.go"] = "package suite\nfunc Compute(n int) int { return MissingImplementation(n) }\n"
    proxy = F12Proxy(tmp_path / "proxy")
    for name, sources in (("healthy", healthy), ("partial", files), ("unavailable", broken)):
        proxy.publish("suite.test/" + name, "v1.0.0", sources)
    with proxy.serving():
        baseline = f17_run({}, target="suite.test/healthy", proxy=proxy.url)
        partial = f17_run({}, target="suite.test/partial", proxy=proxy.url)
        unavailable = f17_run({}, target="suite.test/unavailable", proxy=proxy.url)
    assert baseline.process.returncode == 0, baseline.process
    assert set(baseline.cases("pass")) == {"TestRemaining", "TestCall", "TestInit"}, baseline.events
    assert Counter(baseline.effects) == Counter(["remaining:38", "call", "initializer"]), baseline
    partial.passed(["TestRemaining"])
    assert partial.effects == ["remaining:38"], partial
    # Read the actual public skipping record, not the plan's unimplemented JSON.
    reports = []
    for match in re.finditer(r"^zelviro test: skipping (\S+) \(([^\n]+)",
                             partial.process.stderr.decode(), re.MULTILINE):
        reports.append(match.groups())
    assert {path for path, reason in reports} == {
        "suite.test/partial/call_test.go", "suite.test/partial/init_test.go"}, reports
    assert all(reason.strip() for path, reason in reports), reports
    assert unavailable.process.returncode == 1, unavailable.process
    assert unavailable.process.stderr.strip(), unavailable.process
    assert b'suite.test/unavailable' in unavailable.process.stderr, unavailable.process
    assert unavailable.cases("run") == [] and unavailable.effects == [], unavailable


def test_goroutine_panic_reports_failure_and_continues(f17_run):
    # F17.T09: the later test's data result proves continuation beyond a log.
    # The host releases the test only after observing the worker's outcome.
    # No scheduler speed is inferred from a fixed sleep.
    source = '''package suite
import ("errors"; "fmt"; "os"; "testing"; "time")
var state int
func TestFault(t *testing.T) {
    go func() { FAULT }()
    for {
        if _, err := os.Stat("release"); err == nil { break } else if !errors.Is(err, os.ErrNotExist) { t.Fatal(err) }
        time.Sleep(time.Millisecond)
    }
    fmt.Println("host-released")
    note("fault-test-returned")
}
func TestAfter(t *testing.T) {
    state = 6*9-4
    if state != 50 { t.Fatal(state) }
    note("after:50")
}
'''
    baseline = f17_run(f17_sources(source.replace("FAULT", 'fmt.Println("worker-ready")')),
                       release_after=("stdout", b"worker-ready\n", "release"))
    baseline.passed(["TestFault", "TestAfter"])
    assert baseline.effects == ["fault-test-returned", "after:50"], baseline
    fault = f17_run(f17_sources(source.replace("FAULT", 'panic("worker-fault")')),
                    release_after=("stderr", b"panic: worker-fault\n", "release"))
    assert fault.process.returncode == 2, fault.process
    assert fault.cases("run") == ["TestFault", "TestAfter"], fault.events
    assert "TestAfter" in fault.cases("pass"), fault.events
    assert fault.effects == ["fault-test-returned", "after:50"], fault
    assert b"panic: worker-fault\n" in fault.process.stderr, fault.process
