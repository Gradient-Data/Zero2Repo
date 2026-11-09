# feature: F05
"""Deferred calls and scoped recovery through the public evaluation API."""

from F01_helpers import f01_driver, f01_eval, f01_success, f01_value
from F03_helpers import f03_package_compare, f03_reads


def test_deferred_capture_order_and_named_results(f03_package_compare, f01_driver):
    # F05.T01: native Go independently supplies all return and state values.
    declarations = r'''
var trace string
var evaluations int
func argument(n int) int { evaluations++; trace += "E"; return n }
func record(n int) { trace += string(rune('a'+n)) }
func replacement(n int) { trace += "wrong" }
func delayed(seed int, early bool) (number int, text string) {
    trace, evaluations = "", 0
    local := seed
    defer func() { number = number*3+local; text += "last"; trace += "Z" }()
    defer func(n int) { number += n; text += "first"; trace += "Y" }(argument(local))
    for i := 0; i < 3; i++ { defer record(argument(i)) }
    trace += "B"
    local += 7
    if early { return seed+4, "early:" }
    number, text = seed+8, "normal:"
    return
}
func fallthroughReturn(seed int) {
    trace = ""
    f := record
    defer f(seed)
    f = replacement
    next := seed+1
    defer record(next)
    trace += "body:"
}
func unnamed(seed int) int {
    value := seed
    defer func() { value += 20; trace += "U" }()
    return value
}
func variadicRecord(base int, xs ...int) {
    record(base)
    for _, x := range xs { record(x) }
}
func variadicDeferred() {
    trace = ""
    xs := []int{2, 4}
    defer variadicRecord(1, xs...)
    defer variadicRecord(5, 6, 7)
    xs[0] = 3
}
'''
    steps = []
    for seed, early in ((2, False), (5, True)):
        steps += [(f'number, text := delayed({seed}, {str(early).lower()})'
                   if not steps else
                   f'number, text = delayed({seed}, {str(early).lower()})', False)]
        steps += f03_reads("number", "text", "trace", "evaluations")
    steps += [("fallthroughReturn(2)", False)] + f03_reads("trace", "unnamed(11)", "trace")
    steps += [("variadicDeferred()", False)] + f03_reads("trace")
    f03_package_compare(declarations, steps)

    # Actual deferred output, not merely an in-memory record of registrations.
    records, _ = f01_driver([
        {"Op": "new", "Session": "a"},
        f01_eval(r'''
func outputOnReturn() int {
    word := "first"
    defer print(word)
    word = "second"
    defer print(word, ":")
    print("body:")
    word = "unused"
    return 23
}
outputOnReturn()
''', read_value=True),
    ])
    f01_success(records)
    f01_value(records[1], "int", 23)
    assert records[1]["output"] == "body:second:first", records[1]


def test_panic_unwinding_direct_and_ineffective_recovery(f03_package_compare):
    # F05.T02: no cleanup replaces an active panic with another panic.
    declarations = r'''
var trace string
var caught any
var indirectWasNil, secondWasNil bool
func indirectRecover() any { return recover() }
func child(mode int, payload any) {
    defer func() { trace += "A" }()
    defer func() { trace += "B" }()
    if mode == 2 {
        defer func() { indirectWasNil = indirectRecover() == nil; trace += "I" }()
    }
    trace += "C"
    if mode != 0 { panic(payload) }
    trace += "D"
}
func parent(mode int, payload any) (result int) {
    trace, caught = "", nil
    indirectWasNil, secondWasNil = false, false
    result = 9
    defer func() { trace += "T"; result *= 2 }()
    defer func() {
        v := recover()
        if v != nil { caught = v; result += 17; trace += "R" } else { trace += "N" }
        secondWasNil = recover() == nil
    }()
    child(mode, payload)
    trace += "P"
    result = 53
    return
}
func unnamedRecovery(payload string) int {
    defer func() { caught = recover(); trace += "U" }()
    panic(payload)
    return 99
}
func deferredPanic(payload string) (result string) {
    defer func() { if r := recover(); r != nil { result = r.(string) } }()
    defer panic(payload)
    return "ordinary"
}
'''
    steps = f03_reads("recover() == nil", "indirectRecover() == nil")
    for mode, payload in ((0, '"quiet"'), (1, '"payload-a"'), (2, "81")):
        steps += f03_reads(f"parent({mode}, {payload})", "trace", "caught == nil",
                           f"caught == {payload}", "indirectWasNil", "secondWasNil")
        # This evaluation must be reached after unwinding has completed.
        steps += [('trace += ":continued"', False)]
        steps += f03_reads("trace", "recover() == nil")
    # Observe the function's result in its declared Go type, after assignment.
    steps += [('var zeroResult int = unnamedRecovery("payload-b")', False)]
    steps += f03_reads('zeroResult', 'caught == "payload-b"', "trace",
                       'deferredPanic("late-value")')
    f03_package_compare(declarations, steps)


def test_runtime_panics_recover_and_continue_with_valid_controls(f03_package_compare):
    # F05.T03: each invalid operation has the same operation with valid inputs.
    # Runtime error wording and implementation-specific concrete types are not read.
    # Negative capacity uses channels; the ledger records the unsupported slice case.
    declarations = r'''
var trace string
var panicked bool
var continued int
func operation(kind int, bad bool) int {
    index, upper, maximum := 1, 2, 3
    length, capacity := 2, 3
    divisor := 3
    value := 19
    pointer := &value
    var function func() int
    if !bad { function = func() int { return 31 } }
    if bad {
        index, upper, maximum = 5, 6, 7
        divisor = 0
        pointer = nil
    }
    array := [3]int{7, 11, 17}
    slice := []int{7, 11, 17}
    text := "elm"
    switch kind {
    case 0: return 27/divisor
    case 1: return array[index]
    case 2: return slice[index]
    case 3: slice[index] = 29; return slice[index]
    case 4: return int(text[index])
    case 5: return len(slice[0:upper])
    case 6: return cap(slice[0:1:maximum])
    case 7: return len(text[0:upper])
    case 8: return *pointer
    case 9: *pointer = 37; return value
    case 10: return function()
    case 11:
        if bad { length = -2 }
        return len(make([]int, length))
    case 12:
        if bad { capacity = -3 }
        return cap(make(chan int, capacity))
    case 13:
        if bad { length = capacity+1 }
        return len(make([]int, length, capacity))
    }
    panic("unknown operation")
}
func attempt(kind int, bad bool) (result int) {
    trace, panicked = "", false
    result = 43
    defer func() { trace += "cleanup" }()
    defer func() {
        if recover() != nil { panicked = true; result = 71; trace += "recovered:" }
    }()
    trace += "before:"
    result = operation(kind, bad)
    trace += "after:"
    return
}
'''
    steps = []
    for kind in range(14):
        for bad in (False, True):
            steps += f03_reads(f"attempt({kind}, {str(bad).lower()})", "panicked", "trace")
            steps += [("continued++", False)] + f03_reads("continued")
    f03_package_compare(declarations, steps)
