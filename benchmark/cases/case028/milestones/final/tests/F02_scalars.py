# feature: F02
"""Scalar semantics through stateful evaluation, against native Go 1.26."""

from F01_helpers import f01_driver, f01_eval, f01_success, f01_value
from F02_helpers import f02_compare


def test_scalar_operators_types_and_conversions(f02_compare):
    # F02.T01: each block isolates a semantic family, not a Cartesian matrix.
    scenarios = [
        [("0b101101 + 0o17 + 0x2a + 1_000", True),
         ("17 - 5 - 3", True), ("2 + 3 * 5", True),
         ("(2 + 3) * 5", True), ("8 >> 1 + 1", True),
         ("0x1.8p+2", True), ("2.5e1", True),
         ("'界'", True), ('"a\\n\\u754c"', True), ('`a\\n`', True)],
        [("var a, b bool = true, false", False)] +
        [(expr, True) for expr in ("!a", "!b", "a && b", "a || b", "a == b", "a != b")],
        [("var x, y int = -29, 6", False)] +
        [(expr, True) for expr in ("+x", "-x", "x+y", "x-y", "x*y", "x/y", "x%y",
                                  "x < y", "x <= x", "y > x", "y >= y", "x == y", "x != y")],
        [("var u, v uint16 = 0x36, 0x1b; var shift uint = 3", False)] +
        [(expr, True) for expr in ("u & v", "u | v", "u ^ v", "u &^ v", "^u",
                                  "u << shift", "u >> shift", "u + v", "u - v", "u * v", "u / v", "u % v")],
        [("var x, y float32 = 7.5, 1.25; var z float64 = -12.75", False)] +
        [(expr, True) for expr in ("x+y", "x-y", "x*y", "x/y", "-z", "x < 8", "x == 7.5",
                                  "int(z)", "float64(x)", "float32(z)")],
        [("var a, b complex128 = 6+4i, 2-2i; var c complex64 = 3-1i", False)] +
        [(expr, True) for expr in ("a+b", "a-b", "a*b", "a/b", "-a", "a == b", "a != b",
                                  "complex128(c)", "complex64(a)")],
        [('var a, b string = "birch", "ash"; var r rune = \'λ\'', False)] +
        [(expr, True) for expr in ("a+b", "a < b", "a <= a", "a > b", "b >= b", "a == b", "a != b",
                                  "r + 2", "string(r)", "int32(r)")],
        [("var n int64 = 261; var negative int16 = -3; var f float64 = 12.75", False)] +
        [(expr, True) for expr in ("int(n)", "int8(n)", "int16(n)", "int32(n)", "int64(n)",
                                  "uint(n)", "uint8(n)", "uint16(n)", "uint32(n)", "uint64(n)",
                                  "uintptr(n)", "byte(n)", "rune(n)", "uint16(negative)",
                                  "float32(n)", "float64(n)", "uint64(f)")],
        # Results wrap and round in the operands' own type; comparisons read
        # the narrowed value itself, before any conversion at the result edge.
        [("var small, low int8 = 120, -100; var wide int16 = -3; "
          "var u, w uint16 = 0xfe36, 0x1b1b; var big uint32 = 4000000000; "
          "var count uint = 70; var negative int = -29", False)] +
        [(expr, True) for expr in ("small+10", "small+10 < 0", "low-small", "-low*2",
                                  "wide*12000", "wide*12000 > 0", "u+w", "u*w", "w-u",
                                  "w-u > w", "u<<3", "u<<3 < u", "^w", "big+big",
                                  "big*3 < big", "negative>>count", "negative<<count",
                                  "uint8(u)+250", "int32(big)")],
        [("var huge, one float32 = 1e8, 1; var tiny float32 = 1e-30; var third float32 = 1.0/3; "
          "var c complex64 = complex(1e8, 1e8)", False)] +
        # Go permits excess intermediate precision and fused operations.
        # Explicit conversions impose the rounding points used by this oracle.
        [(expr, True) for expr in ("float32(huge+one)-huge", "float32(huge+one) == huge", "huge*4",
                                  "float32(tiny*tiny)", "float64(float32(third))", "float64(float32(third*3))",
                                  "complex64(complex64(c+1)-c)")],
    ]
    f02_compare(scenarios, program=True)


def test_constants_precision_enumeration_and_refusal(f02_compare, f01_driver):
    # F02.T02: large intermediate values and context-dependent conversions.
    f02_compare([
        [("const huge = 1 << 100; const reduced = (huge + 37) - huge", False),
         ("reduced", True), ("huge >> 96", True),
         ("const fraction = 1.0/10; const exact = fraction*10 - 1", False),
         ("exact == 0", True),
         ("const shared = 6.0; var i int = shared; var f float64 = shared", False),
         ("i", True), ("f", True),
         ("const typed uint16 = 600; const derived = typed + 7", False),
         ("derived", True), ("const top = ^uint64(0)", False), ("top", True)],
        [("const (first uint8 = 2*iota; second; _; fourth; fifth = iota+10; sixth)", False)] +
        [(expr, True) for expr in ("first", "second", "fourth", "fifth", "sixth")],
        [("const (a, b = iota, 1<<iota; c, d = iota, 1<<iota; e, f = iota, 1<<iota); const (restart = iota)", False)] +
        [(expr, True) for expr in ("a", "b", "c", "d", "e", "f", "restart")],
    ], program=True)
    # Each rejected expression has a nearby accepted control, in a fresh session.
    # The baseline has no public uniform invalid-constant classification; see ledger.
    for good, bad, type_name, expected in [
        ("const x = uint8(255); x", "const x = uint8(256)", "uint8", 255),
        ("const x int8 = -128; var result = x; result", "const x int8 = -129", "int8", -128),
        ("21 / 3", "21 / 0", "int", 7),
    ]:
        records, _ = f01_driver([
            {"Op": "new", "Session": "good"},
            f01_eval(good, session="good", read_value=True),
            {"Op": "new", "Session": "bad"},
            f01_eval(bad, session="bad"),
        ])
        f01_value(records[1], type_name, expected)
        assert records[3]["error"] is not None, (bad, records[3])


def test_bindings_assignment_scope_and_target_calls(f02_compare):
    # F02.T03: read each state separately; no checksum can mask a wrong member.
    steps = [("var i int; var u uint; var f float64; var c complex128; var b bool; var s string; var r rune", False)]
    steps += [(expr, True) for expr in ("i", "u", "f", "c", "b", "s", "r")]
    steps += [("var a, z int = 13, 29; inferred := 7", False),
              ("a", True), ("z", True), ("inferred", True),
              ("a, z = z, a", False), ("a", True), ("z", True),
              ("a, next := a%5, a*2", False), ("a", True), ("next", True),
              ("var inside int; { a, local := a+3, a+8; inside = a+local }; a = a+1", False),
              ("inside", True), ("a", True),
              ("_, z = a, next", False), ("z", True),
              ("a++", False), ("a", True), ("a--", False), ("a", True)]
    for statement in ("a += 12", "a -= 3", "a *= 4", "a /= 7", "a %= 5",
                      "a |= 18", "a &= 23", "a ^= 7", "a &^= 2", "a <<= 2", "a >>= 1"):
        steps.extend([(statement, False), ("a", True)])
    targets = [
        ("var log string; var cell = struct{ N int }{10}; var items = []int{20, 30}; "
         'get := func() *int { log += "p"; return &items[0] }; '
         'obj := func() *struct{ N int } { log += "s"; return &cell }; '
         'index := func() int { log += "i"; return 1 }; '
         'rhs := func() int { log += "r"; return 7 }', False),
    ]
    for statement, result in (("*get() += rhs()", "items[0]"),
                              ("obj().N |= rhs()", "cell.N"),
                              ("items[index()] = rhs()", "items[1]"),
                              ("items[index()] += rhs()", "items[1]"),
                              ("obj().N++", "cell.N")):
        targets.extend([(statement, False), (result, True), ("log", True)])
    f02_compare([steps, targets], program=True)


def test_boolean_short_circuit_calls_and_state(f01_driver):
    # F02.T04: identical initial state for each arm, including a live RHS.
    for operator, left, right, result, calls in [
        ("&&", False, True, False, 0), ("&&", True, False, False, 1),
        ("&&", True, True, True, 1), ("||", True, False, True, 0),
        ("||", False, True, True, 1), ("||", False, False, False, 1),
    ]:
        records, _ = f01_driver([
            {"Op": "new", "Session": "a"},
            f01_eval("var calls int; var state = 11; "
                     "func touch(v bool) bool { calls++; state += 7; return v }; "
                     f"var left = {str(left).lower()}"),
            f01_eval(f"left {operator} touch({str(right).lower()})", read_value=True),
            f01_eval("calls", read_value=True), f01_eval("state", read_value=True),
        ])
        f01_success(records)
        f01_value(records[2], "bool", result)
        f01_value(records[3], "int", calls)
        f01_value(records[4], "int", 11 + 7*calls)


def test_extrema_and_complex_components(f02_compare):
    # F02.T05: ordered categories and arities, plus both complex precisions.
    f02_compare([
        [("var a, b, c int = 9, -4, 17", False)] +
        [(expr, True) for expr in ("min(a)", "max(b)", "min(a,b)", "max(a,b)",
                                  "min(c,b,a)", "max(a,c,b)")],
        [("var a, b uint64 = 1<<63, 23", False), ("min(a,b)", True), ("max(a,b)", True)],
        [("var a, b float32 = 1.5, -2.25; var c float64 = 7.75", False)] +
        [(expr, True) for expr in ("min(a,b)", "max(a,b,float32(3))", "min(c,float64(8.5),float64(2.25))", "max(c,float64(8.5),float64(2.25))")],
        [('var a, b string = "zebra", "apple"; var r rune = \'λ\'', False)] +
        [(expr, True) for expr in ('min(a,b,"pear")', 'max(a,b,"pear")', "min(r,'界')", "max(r,'界')")],
        [("var x, y float32 = 2.5, -3.75; var a, b float64 = -6.25, 4.5", False)] +
        [(expr, True) for expr in ("complex(x,y)", "real(complex(x,y))", "imag(complex(x,y))",
                                  "complex(a,b)", "real(complex(a,b))", "imag(complex(a,b))",
                                  "complex(3, -5)", "real(7+9i)", "imag(7+9i)")],
    ], program=True)
