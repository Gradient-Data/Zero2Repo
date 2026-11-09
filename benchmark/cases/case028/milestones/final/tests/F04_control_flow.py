# feature: F04
"""Functions and control flow through Eval, with independent Go 1.26 oracles."""

from F01_helpers import f01_driver, f01_eval, f01_value
from F03_helpers import f03_package_compare, f03_reads


def test_function_calls_results_recursion_and_variadics(f03_package_compare):
    # F04.T01: each result and the call record are independently observed.
    declarations = r'''
var calls string
func record(n int) { calls += string(rune('a' + n)) }
func pair(n int) (int, string) { record(n); return n*n+1, string(rune('A'+n)) }
func named(n int) (value int, text string) {
    if n < 0 { return }
    value = n + 8
    text = "named"
    return
}
func recurse(n int) int {
    if n <= 1 { return 1 }
    return n * recurse(n-1)
}
func apply(f func(int) (int, string), n int) (int, string) { return f(n) }
func join(n int, text string) string { return text + string(rune('a'+n%26)) }
func variadic(base int, values ...int) int {
    total := base
    for i, v := range values { total += (i+1)*v }
    if len(values) > 0 { values[0] += base }
    return total
}
func aggregate(a [2]int, s []int) [2]int { a[0] += s[0]; s[1] += a[1]; return a }
'''
    steps = [("a, b := pair(3); c, d := apply(pair, 5); saved := pair", False)]
    steps += f03_reads("a", "b", "c", "d", "calls", "recurse(0)", "recurse(6)")
    steps += [("e, f := saved(7); g, h := named(4); z, empty := named(-1)", False)]
    steps += f03_reads("e", "f", "g", "h", "z", "empty", "join(pair(2))", "calls")
    steps += [("replacement := func(n int) (int, string) { return n-9, \"literal\" }; "
               "saved = replacement; x, y := apply(saved, 12)", False)]
    steps += f03_reads("x", "y", "variadic(13)", "variadic(2, 7)", "variadic(3, 5, 11, 17)")
    steps += [("arguments := []int{4, 9, 16}; result := variadic(6, arguments...); var absent []int", False)]
    steps += f03_reads("result", "arguments[0]", "arguments[1]", "arguments[2]", "variadic(19, absent...)")
    steps += [("array := [2]int{3, 8}; slice := []int{10, 20}; changed := aggregate(array, slice)", False)]
    steps += f03_reads("array", "changed", "slice[0]", "slice[1]")
    f03_package_compare(declarations, steps)


def test_closures_share_captures_and_isolate_calls(f03_package_compare):
    # F04.T02: the factory has returned before either closure is evaluated.
    declarations = r'''
func counter(start int) (func(int) int, func() int, func(int)) {
    value := start
    add := func(delta int) int { value += delta; return value }
    read := func() int { return value }
    set := func(next int) { value = next }
    return add, read, set
}
func nested(start int) func(int) func(int) int {
    value := start
    return func(step int) func(int) int {
        return func(times int) int { value += step*times; return value }
    }
}
// Since go1.22 each loop iteration declares fresh iteration variables.
func perIteration() [6]int {
    var fs []func() int
    for i := 0; i < 3; i++ { fs = append(fs, func() int { return i*10 }) }
    for _, v := range []int{7, 8} { fs = append(fs, func() int { return v }) }
    for k := range 1 { fs = append(fs, func() int { return k + 40 }) }
    var out [6]int
    for n, f := range fs { out[n] = f() }
    return out
}
'''
    steps = [("addA, readA, setA := counter(12); addB, readB, setB := counter(80)", False)]
    steps += f03_reads("perIteration()")
    steps += f03_reads("readA()", "readB()", "addA(5)", "readA()", "readB()")
    steps += [("setA(31)", False)] + f03_reads("readA()", "addA(-4)", "readA()", "addB(9)", "readB()")
    steps += [("alias := addA; setB(101)", False)]
    steps += f03_reads("alias(6)", "readA()", "addA(2)", "readB()")
    steps += [("outerA := nested(7); outerB := nested(50); "
               "twice := outerA(2); five := outerA(5); separate := outerB(3)", False)]
    steps += f03_reads("twice(4)", "five(2)", "twice(1)", "separate(2)", "five(0)")
    f03_package_compare(declarations, steps)


def test_conditionals_switches_loops_labels_and_returns(f03_package_compare):
    # F04.T03: traces reveal skipped statements, ordering, and exit depth.
    declarations = r'''
func branches(n int) string {
    trace := ""
    if v := n+1; v < 0 { trace += "negative" } else if v == 0 { trace += "zero" } else { trace += "positive" }
    switch x := n; x {
    case -2, -1: trace += "L"
    case 0: trace += "Z"; fallthrough
    case 1: trace += "U"
    default: trace += "D"
    }
    switch {
    case n < 0: trace += "a"
    case n < 2: trace += "b"
    default: trace += "c"
    }
    return trace
}
func loops() string {
    trace := ""
    for i := 0; i < 5; i++ {
        if i == 1 { continue }
        trace += string(rune('a'+i))
        if i == 3 { break }
    }
    n := 3
    for n > 0 { trace += string(rune('0'+n)); n-- }
    for { trace += "!"; break }
    for false { trace += "wrong" }
    return trace
}
func labeled() string {
    trace := ""
Outer:
    for i := 0; i < 4; i++ {
        for j := 0; j < 3; j++ {
            if j == 1 { continue Outer }
            trace += string(rune('a'+i))
        }
        trace += "wrong"
    }
Stop:
    for i := 0; i < 4; i++ {
        for j := 0; j < 3; j++ {
            if i == 1 && j == 1 { break Stop }
            trace += string(rune('A'+i*3+j))
        }
        trace += "."
    }
    return trace
}
func jumps(n int) string {
    trace := ""
again:
    trace += "a"
    n--
    if n > 0 { goto again }
    goto end
    trace += "wrong"
end:
    return trace + "z"
}
func early(n int) string {
    trace := ""
    for i := 0; i < 4; i++ {
        switch i {
        case 0: trace += "a"; break; trace += "wrong"
        case n: return trace + "r"
        default: trace += "d"
        }
        trace += "."
    }
    return trace + "end"
}
'''
    expressions = [f"branches({n})" for n in (-2, -1, 0, 1, 7)]
    expressions += ["loops()", "labeled()", "jumps(1)", "jumps(3)", "early(2)", "early(8)"]
    f03_package_compare(declarations, f03_reads(*expressions))


def test_range_subjects_callback_stop_and_invalid_iteration(f03_package_compare, f01_driver):
    # F04.T04: no map ordering is observed; bounded producers expose callback results.
    declarations = r'''
var attempts, accepted, stopped, completed int
func sequence(yield func(int) bool) {
    for i := 0; i < 5; i++ {
        attempts++
        if !yield(i*3+2) { stopped++; return }
        accepted++
    }
    completed++
}
func pairs(yield func(string, int) bool) {
    for i := 0; i < 4; i++ {
        if !yield(string(rune('k'+i)), i*7+1) { return }
    }
}
func consume(mode int) int {
    attempts, accepted, stopped, completed = 0, 0, 0, 0
    sum := 0
    for v := range sequence {
        if mode == 1 && v == 8 { break }
        if mode == 2 && v == 8 { return sum }
        if mode == 3 && v == 5 { continue }
        sum += v
    }
    return sum
}
'''
    steps = [("var integers [5]int; for i := range 5 { integers[i] = i+10 }; "
               "zero := 0; for range 0 { zero++ }; negative := 0; for range -3 { negative++ }", False)]
    steps += f03_reads("integers", "zero", "negative")
    steps += [("array := [3]int{4, 9, 15}; var arraySeen [3]int; "
               "for i, v := range array { arraySeen[i] = v; array[2] = 70 }; "
               "slice := []int{6, 12, 18}; var sliceSeen [3]int; "
               "for i, v := range slice { sliceSeen[i] = v; slice[2] = 90 }", False)]
    steps += f03_reads("arraySeen", "array", "sliceSeen")
    steps += [('text := "Aé界Z"; var positions [4]int; var runes [4]int32; count := 0; '
               'for i, r := range text { positions[count] = i; runes[count] = r; count++ }', False)]
    steps += f03_reads("count", "positions", "runes")
    steps += [('mapping := map[string]int{"oak": 7, "elm": 13, "fir": 29}; '
               'seen := map[string]int{}; visits := 0; '
               'for k, v := range mapping { seen[k] = v; visits++ }; '
               'keys := map[string]bool{}; for k := range mapping { keys[k] = true }', False)]
    steps += f03_reads("visits", "len(seen)", 'seen["oak"]', 'seen["elm"]', 'seen["fir"]',
                      "len(keys)", 'keys["oak"]', 'keys["elm"]', 'keys["fir"]')
    steps += [("index, value := -1, -1; for index, value = range []int{22, 35} {}; "
               "countOnly := 0; for range array { countOnly++ }; "
               "var nilSlice []int; var nilMap map[string]int; "
               "emptyVisits := 0; for range nilSlice { emptyVisits++ }; for range nilMap { emptyVisits++ }", False)]
    steps += f03_reads("index", "value", "countOnly", "emptyVisits")
    for mode in range(4):
        steps += f03_reads(f"consume({mode})", "attempts", "accepted", "stopped", "completed")
    steps += [('pairValues := map[string]int{}; pairCount := 0; '
               'for k, v := range pairs { pairValues[k] = v; pairCount++ }; '
               'keyTrace := ""; for k := range pairs { keyTrace += k }', False)]
    steps += f03_reads("pairCount", 'pairValues["k"]', 'pairValues["l"]',
                      'pairValues["m"]', 'pairValues["n"]', "keyTrace")
    f03_package_compare(declarations, steps)

    # The original has no DescribeError classifier. Assert the real error
    # carrier, and record the unimplementable classification obligation in the ledger.
    invalid = [
        "for k := range struct{}{} { _ = k }",
        "for k := range true { _ = k }",
        "for k, v := range 4 { _ = k; _ = v }",
        "seq := func(yield func(int) bool) { yield(9) }; for k, v := range seq { _ = k; _ = v }",
    ]
    for source in invalid:
        records, _ = f01_driver([
            {"Op": "new", "Session": "a"},
            f01_eval("func live(n int) int { return n+3 }; live(8)", read_value=True),
            f01_eval(source, label="iteration.go"),
        ])
        f01_value(records[1], "int", 11)
        assert records[2]["error"] is not None, records[2]
