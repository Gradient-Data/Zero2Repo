# feature: F07
"""Channel capability through Eval, real host communication, and native Go."""

from F01_helpers import f01_driver, f01_eval, f01_success
from F03_helpers import f03_package_compare, f03_reads
from F07_helpers import f07_host_compare


def test_goroutines_typed_channels_close_and_range(f07_host_compare, f03_package_compare):
    # F07.T01: an interpreted worker cannot finish until the host supplies data.
    f07_host_compare(
        'input := make(chan int32); output := make(chan int32); finished := make(chan string)',
        [("Input", "chan int32", "input"), ("Output", "chan int32", "output"),
         ("Finished", "chan string", "finished")],
        r'''
local := make(chan int32, 3)
go func() {
    for value := range bridge.Input { local <- value*3-2 }
    close(local)
}()
for value := range local { bridge.Output <- value }
close(bridge.Output)
bridge.Finished <- "complete"
''',
        r'''
go func() { for _, v := range []int32{7, -4, 0, 19, 2} { input <- v }; close(input) }()
for v := range output { values = append(values, capture(reflect.ValueOf(v))) }
values = append(values, capture(reflect.ValueOf(<-finished)))
''')
    f03_package_compare(r'''
func exchange(capacity int) string {
    ch := make(chan string, capacity)
    go func() { ch <- "elm"; ch <- "birch"; ch <- "oak"; close(ch) }()
    result := ""
    for v := range ch { result += v+":" }
    return result
}
func typed() int {
    ch := make(chan func(int) int, 1)
    offset := 6
    ch <- func(n int) int { return n+offset }
    f := <-ch
    pointers := make(chan *int, 1)
    pointers <- nil
    if <-pointers != nil { return -1 }
    return f(17)
}
''', f03_reads("exchange(0)", "exchange(3)", "typed()"))


def test_select_readiness_closed_nil_and_uniform_choice(f03_package_compare, f01_driver):
    # F07.T02: deterministic results use the independent language implementation.
    f03_package_compare(r'''
type selectionResult struct {
    defaultBranch string
    initialValue int
    sendBranch string
    bufferedBranch string
    bufferedValue int
    bufferedOpen bool
    drainedBranch string
    drainedValue int
    drainedOpen bool
    waitedBranch string
    waitedValue int
}
func selectCases() selectionResult {
    var result selectionResult
    var nilch chan int
    empty := make(chan int)
    full := make(chan int, 1); full <- 37
    branch := ""
    select {
    case <-nilch: branch = "nil receive"
    case nilch <- 1: branch = "nil send"
    case <-empty: branch = "empty receive"
    case full <- 2: branch = "full send"
    default: branch = "default"
    }
    result.defaultBranch, result.initialValue = branch, <-full
    select { case full <- 53: branch = "send"; default: branch = "default" }
    result.sendBranch = branch
    close(full)
    value, open := 0, false
    select { case value, open = <-full: branch = "receive"; default: branch = "default" }
    result.bufferedBranch, result.bufferedValue, result.bufferedOpen = branch, value, open
    select { case value, open = <-full: branch = "drained"; default: branch = "default" }
    result.drainedBranch, result.drainedValue, result.drainedOpen = branch, value, open
    go func() { empty <- 71 }()
    select { case <-nilch: branch = "nil"; case value = <-empty: branch = "waited" }
    result.waitedBranch, result.waitedValue = branch, value
    return result
}
''', [("selection := selectCases()", False)] + f03_reads(
        "selection.defaultBranch", "selection.initialValue", "selection.sendBranch",
        "selection.bufferedBranch", "selection.bufferedValue", "selection.bufferedOpen",
        "selection.drainedBranch", "selection.drainedValue", "selection.drainedOpen",
        "selection.waitedBranch", "selection.waitedValue"))
    # Each branch is ready on every draw. Sampling counts, never a fixed sequence.
    # Independent uniform draws also make "same branch as the previous draw" a
    # Bernoulli(1/branches) event, which rejects rotation schemes whose overall
    # frequencies are exactly even. Hoeffding plus a union bound over the five
    # frequencies and two repeat rates gives
    # <= 14*exp(-2*8191*0.05**2) = 2.3e-17 false rejection.
    for branches in (2, 3):
        declarations = "\n".join(f"c{i} := make(chan int); close(c{i})" for i in range(branches))
        cases = "\n".join(f"case <-c{i}: chosen = {i}" for i in range(branches))
        source = (f"func sample() ([]int, int) {{\n{declarations}\n"
                  f"counts := make([]int, {branches}); repeats, previous := 0, -1\n"
                  f"for i := 0; i < 8192; i++ {{ chosen := -1; select {{ {cases} }}; "
                  "counts[chosen]++; if chosen == previous { repeats++ }; previous = chosen }\n"
                  "return counts, repeats }\ncounts, repeats := sample()")
        actions = [{"Op": "new", "Session": "a"}, f01_eval(source)]
        actions += [f01_eval(f"counts[{i}]", read_value=True) for i in range(branches)]
        actions.append(f01_eval("repeats", read_value=True))
        records, _ = f01_driver(actions)
        f01_success(records)
        counts = []
        for record in records[2:]:
            assert record["valid"] and record["type"] == "int", record
            counts.append(record["value"])
        repeats = counts.pop()
        assert sum(counts) == 8192, counts
        assert all(abs(count / 8192 - 1 / branches) <= 0.05 for count in counts), counts
        assert abs(repeats / 8191 - 1 / branches) <= 0.05, (repeats, counts)



def test_invalid_channel_operations_recover_and_continue(f07_host_compare):
    # F07.T03: the host only invokes the supplied interpreted callback. All
    # channel operations and deferred recovery execute in the interpreted source.
    # The baseline supports recovery across this native callback boundary; direct
    # opcode recovery is a separate documented baseline/specification gap.
    f07_host_compare(
        'invoke := func(f func()) { f() }\n'
        'results := make(chan int); flags := make(chan bool); traces := make(chan string)',
        [("Invoke", "func(func())", "invoke"), ("Results", "chan int", "results"),
         ("Flags", "chan bool", "flags"), ("Traces", "chan string", "traces")],
        r'''
recovered, returned := false, false
trace := ""
attempt := func(kind int, invalid bool) (result int) {
    recovered, returned, trace = false, false, "before:"
    result = 11
    defer func() { trace += "cleanup" }()
    defer func() {
        if recover() != nil { recovered = true; result = 29; trace += "recovered:" }
    }()
    bridge.Invoke(func() {
        ch := make(chan int, 1)
        if kind == 0 { close(ch); if invalid { close(ch) } }
        if kind == 1 { if invalid { ch = nil }; close(ch) }
        if kind == 2 { if invalid { close(ch) }; ch <- 43; result = <-ch }
        returned = true
        trace += "after:"
    })
    trace += "returned:"
    return
}
continued := 0
for kind := 0; kind < 3; kind++ {
    for _, invalid := range []bool{false, true} {
        result := attempt(kind, invalid)
        bridge.Results <- result
        bridge.Flags <- recovered
        bridge.Flags <- returned
        bridge.Traces <- trace
        continued++
        bridge.Results <- continued
    }
}
''',
        r'''
for i := 0; i < 6; i++ {
    values = append(values, capture(reflect.ValueOf(<-results)))
    values = append(values, capture(reflect.ValueOf(<-flags)))
    values = append(values, capture(reflect.ValueOf(<-flags)))
    values = append(values, capture(reflect.ValueOf(<-traces)))
    values = append(values, capture(reflect.ValueOf(<-results)))
}
''')


def test_blocked_communications_resume_after_host_handshake(f07_host_compare):
    # F07.T04: readiness is host-controlled. Cooperative yields give the worker
    # opportunities to run, without using a sleep duration as a scheduling oracle.
    for operation, capacity, initial in (("send", 0, ""), ("send", 1, "data <- 13"),
                                         ("receive", 0, ""), ("select", 0, "")):
        instruction = {"send": "bridge.Data <- 47; value := 47",
                       "receive": "value := <-bridge.Data",
                       "select": "value := 0; select { case value = <-bridge.Data: }"}[operation]
        release = ('values = append(values, capture(reflect.ValueOf(<-data)))\n' +
                   ('values = append(values, capture(reflect.ValueOf(<-data)))\n' if capacity else '')) if operation == "send" else 'data <- 61\n'
        f07_host_compare(
            f'data := make(chan int, {capacity}); {initial}\n'
            'entered := make(chan bool); completed := make(chan int, 1)',
            [("Data", "chan int", "data"), ("Entered", "chan bool", "entered"),
             ("Completed", "chan int", "completed")],
            'bridge.Entered <- true\n' + instruction + '\nbridge.Completed <- value',
            r'''
values = append(values, capture(reflect.ValueOf(<-entered)))
for i := 0; i < 1024; i++ {
    runtime.Gosched()
    select {
    case v := <-completed: panic(v)
    case err := <-done: panic(err)
    default:
    }
}
values = append(values, capture(reflect.ValueOf(len(completed))))
''' + release +
            'values = append(values, capture(reflect.ValueOf(<-completed)))')
