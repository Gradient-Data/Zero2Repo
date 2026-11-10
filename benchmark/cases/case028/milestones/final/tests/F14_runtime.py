# feature: F14
"""Acceptance of process exits, runtime diagnostics, inspection and termination."""

from _helpers import parse_json
from F01_helpers import f01_driver, f01_eval, f01_success
from F14_helpers import (
    f14_host, f14_native, f14_diagnostic, f14_source_frame,
)


def test_exit_status_host_survival_and_fatal_logging(f14_host):
    # A working control establishes that the host endpoint really is called.
    control = f14_host('import "bridge"\nbridge.Note("evaluated")')
    assert control["Error"] is None, control
    assert control["Events"] == ["evaluated", "host-resumed"], control
    for status in (0, 23, 79):
        source = '''import ("os"; "bridge")
func stop() {
    defer func() { recover() }()
    bridge.Note("before-exit")
    os.Exit(%d)
    bridge.Note("after-exit")
}
stop()
bridge.Note("after-call")
''' % status
        result = f14_host(source)
        assert result["Error"] is not None, result
        assert result["ExitCode"] == status, result
        assert result["Events"] == ["before-exit", "host-resumed"], result

    for fatal in ('log.Fatal("fatal work failed")',
                  'log.Fatalf("fatal work %s", "failed")'):
        source = '''import ("log"; "os"; "bridge")
log.SetOutput(os.Stderr)
log.SetFlags(0)
func stop() {
    defer func() { recover() }()
    bridge.Note("before-fatal")
    %s
    bridge.Note("after-fatal")
}
stop()
bridge.Note("after-call")
''' % fatal
        result = f14_host(source)
        assert result["Error"] is not None, result
        assert result["ExitCode"] is not None and result["ExitCode"] != 0, result
        assert result["Diagnostic"], result  # Logging carrier, not wording.
        assert result["Events"] == ["before-fatal", "host-resumed"], result


def test_panic_cause_locations_and_cross_native_call_chain(f14_host):
    scenarios = [
        ('pure.go', '''func leaf() {
    panic("calculation stopped")
}
func middle() {
    leaf()
}
func outer() {
    middle()
}
outer()
''', "calculation stopped", [("leaf", 2), ("middle", 5), ("outer", 8)]),
        ('cross.go', '''import "bridge"
func leaf() {
    panic("callback stopped")
}
func middle() {
    bridge.Call(leaf)
}
func outer() {
    bridge.Call(middle)
}
outer()
''', "callback stopped", [("leaf", 3), ("middle", 6), ("outer", 9)]),
    ]
    for label, source, cause, calls in scenarios:
        result = f14_host(source, label)
        assert result["Error"] is not None, result
        assert result["ExitCode"] is None, result
        assert result["Events"] == ["host-resumed"], result
        report = f14_diagnostic(result["Error"])
        assert report["cause"] == cause, report
        f14_source_frame(report["site"], calls[0][0], label, source, calls[0][1])
        names = [frame[0] for frame in report["frames"]]
        indices = []
        for name, line in calls:
            assert names.count(name) == 1, report
            index = names.index(name)
            indices.append(index)
            f14_source_frame(report["frames"][index], name, label, source, line)
        assert indices == sorted(indices), report


def test_goroutine_panic_fails_channel_wait_with_source_context(f14_host):
    # These two paths exercise receive and send waits, not elapsed-time guesses.
    for communication, worker in (("<-ch", "ch <- 7"), ("ch <- 7", "<-ch")):
        template = '''package main
import "bridge"
func worker(ch chan int) {
    BODY
}
func main() {
    ch := make(chan int)
    go worker(ch)
    COMMUNICATION
    bridge.Note("communication-completed")
}
'''.replace("COMMUNICATION", communication)
        control = f14_host(template.replace("BODY", worker), "worker.go")
        assert control["Error"] is None, control
        assert control["Events"] == ["communication-completed", "host-resumed"], control
        source = template.replace("BODY", 'panic("worker interrupted")')
        result = f14_host(source, "worker.go")
        assert result["Error"] is not None, result
        assert result["ExitCode"] is not None and result["ExitCode"] != 0, result
        assert result["Events"] == ["host-resumed"], result
        lines = result["Diagnostic"].splitlines()
        header = "-- panic in goroutine --"
        assert lines.count(header) == 1, result
        report = f14_diagnostic("\n".join(lines[lines.index(header) + 1:]))
        assert report["cause"] == "worker interrupted", report
        f14_source_frame(report["site"], "worker", "worker.go", source, 4)
        frames = [frame for frame in report["frames"] if frame[0] == "worker"]
        assert len(frames) == 1, report
        f14_source_frame(frames[0], "worker", "worker.go", source, 4)


def test_runtime_caller_frames_and_skip_match_go(f01_driver, f14_native):
    # Native Go is the independent oracle for the standard named by FP-14.04.
    # Restrict capture to interpreted frames; the embedding host tail is free.
    source = '''package main
import ("encoding/json"; "os"; "runtime"; "path/filepath")
type Frame struct { Function, File string; Line int; More bool }
type Report struct { Callers []Frame; Stacks [][]Frame }
//go:noinline
func inner() Report {
    report := Report{}
    for skip := 0; skip < 3; skip++ {
        pc, file, line, ok := runtime.Caller(skip)
        if !ok { panic("caller unavailable") }
        fn := runtime.FuncForPC(pc)
        if fn == nil { panic("function unavailable") }
        fnFile, fnLine := fn.FileLine(pc)
        if fnFile != file || fnLine != line { panic("caller location mismatch") }
        report.Callers = append(report.Callers, Frame{fn.Name(), filepath.Base(file), line, false})
    }
    for skip := 1; skip <= 3; skip++ {
        pcs := make([]uintptr, 4-skip)
        n := runtime.Callers(skip, pcs)
        if n != len(pcs) { panic("missing call frames") }
        frames := runtime.CallersFrames(pcs[:n])
        stack := []Frame{}
        for index := 0; index < n; index++ {
            frame, more := frames.Next()
            stack = append(stack, Frame{frame.Function, filepath.Base(frame.File), frame.Line, more})
        }
        report.Stacks = append(report.Stacks, stack)
    }
    return report
}
//go:noinline
func middle() Report {
    return inner()
}
//go:noinline
func outer() Report {
    return middle()
}
func main() {
    report := outer()
    if err := json.NewEncoder(os.Stdout).Encode(report); err != nil { panic(err) }
}
'''
    expected = f14_native(source)
    observations, _ = f01_driver([
        {"Op": "new", "Session": "a"},
        f01_eval(source, label="main/runtime.go"),
    ])
    f01_success(observations)
    actual = parse_json(observations[-1]["output"])
    assert actual == expected, (actual, expected)


def test_goexit_runs_cleanup_without_recoverable_panic(f14_host, f14_native):
    # The same worker body runs natively and through Eval. All events reach
    # real host storage, and channel completion orders every read after writes.
    body = '''func terminate() {
    defer bridge.Note("inner-cleanup")
    runtime.Goexit()
    bridge.Note("after-goexit")
}
func worker(done chan bool) {
    defer func() { done <- true }()
    defer bridge.Note("outer-cleanup")
    defer func() {
        if recover() == nil { bridge.Note("recover-nil") } else { bridge.Note("recover-panic") }
    }()
    bridge.Note("started")
    terminate()
    bridge.Note("after-terminate")
}
func run() {
    done := make(chan bool)
    go worker(done)
    <-done
    other := make(chan int)
    go func() { other <- 6 * 7 }()
    bridge.Note(fmt.Sprint("other-result:", <-other))
}
'''
    native = '''package main
import ("encoding/json"; "os"; "runtime"; "fmt")
var events = []string{}
var bridge = struct{ Note func(string) }{func(s string) { events = append(events, s) }}
''' + body + '''func main() {
    run()
    if err := json.NewEncoder(os.Stdout).Encode(events); err != nil { panic(err) }
}
'''
    expected = f14_native(native)
    result = f14_host('import ("bridge"; "runtime"; "fmt")\n' + body + '\nrun()')
    assert result["Error"] is None, result
    assert result["ExitCode"] is None, result
    assert result["Events"] == expected + ["host-resumed"], (result, expected)
