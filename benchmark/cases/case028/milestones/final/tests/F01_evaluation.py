# feature: F01
"""Acceptance observations for stateful Go embedding (FP-01)."""

from F01_helpers import f01_driver, f01_eval, f01_success, f01_undefined_at, f01_value


def test_evaluation_results_and_source_forms(f01_driver):
    # F01.T01: inspect expression results, and statement/program effects.
    records, _ = f01_driver([
        {"Op": "new", "Session": "a"},
        f01_eval("// No expression in this source.\n"),
        f01_eval("6 * 9 - 4", read_value=True),
        f01_eval('"river" + "bank"', read_value=True),
        f01_eval("var total = 12"),
        f01_eval("total += 5"),
        f01_eval("total", read_value=True),
        f01_eval("8; 27", read_value=True),
        {"Op": "new", "Session": "program"},
        f01_eval("package main\nvar result int\n"
                 "func main() { result = 7 * 8; println(result) }",
                 session="program", label="program.go"),
    ])
    f01_success(records)
    assert records[1]["valid"] is False, records[1]
    f01_value(records[2], "int", 50)
    f01_value(records[3], "string", "riverbank")
    f01_value(records[6], "int", 17)
    f01_value(records[7], "int", 27)
    assert records[9]["output"] == "56\n", records[9]

    # Failed execution may leave a non-JSON scalar or function on the VM.
    # The public error must survive observation instead of being replaced by
    # an encoder failure for a leftover value.
    failed, _ = f01_driver([
        {"Op": "new", "Session": "a"},
        f01_eval('var residue complex128 = 3+4i; panic(17)', read_value=True),
    ])
    assert failed[1]["error"] is not None, failed[1]


def test_session_retains_declarations_and_initializes_once(f01_driver):
    # F01.T02: declarations and mutations survive unrelated evaluations.
    records, _ = f01_driver([
        {"Op": "new", "Session": "a"},
        f01_eval('import "strings"\nvar tally = 3\ntype Label string\n'
                 'func decorate(v Label) string { return strings.ToUpper(string(v)) }\n'
                 'var runs int\nfunc init() { runs++; tally += 10 }'),
        f01_eval("runs", read_value=True),
        f01_eval("tally", read_value=True),
        f01_eval('decorate(Label("pine"))', read_value=True),
        f01_eval("tally += 6"),
        f01_eval("var unrelated = 99"),
        f01_eval("tally", read_value=True),
        f01_eval("runs", read_value=True),
        f01_eval("func init() { runs += 10 }"),
        f01_eval("runs", read_value=True),
        f01_eval('decorate(Label("reed"))', read_value=True),
        f01_eval("runs", read_value=True),
        f01_eval('strings.ToLower("BIRCH")', read_value=True),
    ])
    f01_success(records)
    for index, expected in [(2, 1), (3, 13), (7, 19), (8, 1), (10, 11), (12, 11)]:
        f01_value(records[index], "int", expected)
    for index, expected in [(4, "PINE"), (11, "REED"), (13, "birch")]:
        f01_value(records[index], "string", expected)


def test_interpreters_keep_independent_declarations(f01_driver):
    # F01.T03: interleave sessions; no native mutable state is injected.
    records, _ = f01_driver([
        {"Op": "new", "Session": "a"},
        f01_eval("var shared = 11\nvar onlyA = 4\n"
                 "func signature() int { return 4 }\ntype Badge int"),
        {"Op": "new", "Session": "b"},
        f01_eval("var shared = 72\nfunc signature() int { return 9 }\n"
                 "type Badge string", session="b"),
        f01_eval("shared += 5"),
        f01_eval("shared", session="b", read_value=True),
        f01_eval("shared", read_value=True),
        f01_eval("shared -= 9", session="b"),
        f01_eval("shared", read_value=True),
        f01_eval("shared", session="b", read_value=True),
        f01_eval("onlyA", read_value=True),
        f01_eval("signature()", read_value=True),
        f01_eval("signature()", session="b", read_value=True),
        f01_eval("int(Badge(5))", read_value=True),
        f01_eval('string(Badge("blue"))', session="b", read_value=True),
        {"Op": "new", "Session": "c"},
        f01_eval("var absent = onlyA", session="c", label="third.go"),
        f01_eval("var absent = onlyA", session="b", label="second.go"),
    ])
    f01_success(records[:16])
    for index, expected in [(5, 72), (6, 16), (8, 16), (9, 63), (10, 4),
                            (11, 4), (12, 9), (13, 5)]:
        f01_value(records[index], "int", expected)
    f01_value(records[14], "string", "blue")
    # An actual returned error is required; missing success alone is not enough.
    for index in (16, 17):
        assert records[index]["error"] is not None, records[index]


def test_configured_streams_replacement_and_host_stdio(f01_driver):
    # F01.T04: reuse a compiled function after replacing all three streams.
    records, process = f01_driver([
        {"Op": "new", "Session": "a", "Input": "willow 17\n"},
        f01_eval('import ("fmt"; "os")\nvar word string\nvar number int\n'
                 'func exchange() { fmt.Fscan(os.Stdin, &word, &number); '
                 'print("basic:"); println(word); fmt.Printf("formatted:%d\\n", number); '
                 'fmt.Fprintln(os.Stderr, "diagnostic:" + word) }'),
        f01_eval("exchange()"),
        f01_eval("word", read_value=True),
        f01_eval("number", read_value=True),
        {"Op": "set_io", "Session": "a", "Input": "cedar 29\n"},
        f01_eval("exchange()"),
        f01_eval("word", read_value=True),
        f01_eval("number", read_value=True),
    ])
    f01_success(records)
    assert records[2]["output"] == "basic:willow\nformatted:17\n", records[2]
    assert records[2]["diagnostic"] == "diagnostic:willow\n", records[2]
    assert records[6]["output"] == "basic:cedar\nformatted:29\n", records[6]
    assert records[6]["diagnostic"] == "diagnostic:cedar\n", records[6]
    f01_value(records[3], "string", "willow")
    f01_value(records[4], "int", 17)
    f01_value(records[7], "string", "cedar")
    f01_value(records[8], "int", 29)
    assert process.stdout == b"", process
    assert process.stderr == b"", process

    # Both arms use the same program, host stdin and configured streams.
    # Only UseHostStdio differs, and both arms must show real input/output.
    for host_stdio in (False, True):
        records, process = f01_driver([
            {"Op": "new", "Session": "a", "Input": "ignored 99\n",
             "HostStdio": host_stdio},
            f01_eval('import ("fmt"; "os")\nvar word string\nvar number int\n'
                     'fmt.Fscan(os.Stdin, &word, &number)\n'
                     'fmt.Fprintln(os.Stdout, word)\nfmt.Fprintln(os.Stderr, number)'),
            f01_eval("word", read_value=True),
            f01_eval("number", read_value=True),
        ], host_input=b"hostinput 41\n")
        f01_success(records)
        if host_stdio:
            f01_value(records[2], "string", "hostinput")
            f01_value(records[3], "int", 41)
            assert process.stdout == b"hostinput\n", process
            assert process.stderr == b"41\n", process
            assert records[3]["output"] == "", records[3]
            assert records[3]["diagnostic"] == "", records[3]
        else:
            f01_value(records[2], "string", "ignored")
            f01_value(records[3], "int", 99)
            assert records[3]["output"] == "ignored\n", records[3]
            assert records[3]["diagnostic"] == "99\n", records[3]
            assert process.stdout == b"", process
            assert process.stderr == b"", process



def test_source_positioned_failures_and_unfinished_input(f01_driver):
    # F01.T05: observe existing returned error fields and sentinel identity.
    # DescribeError is absent from the baseline; no replacement report is made.
    call_source = "// call boundary\n\n    absentCall()"
    initializer_source = "// declaration boundary\n\n\n  var result = unknownValue"
    call_label = "diagnostics/call.go"
    initializer_label = "diagnostics/initializer.go"
    records, _ = f01_driver([
        {"Op": "new", "Session": "valid_call"},
        f01_eval("func present() int { return 23 }; present()",
                 session="valid_call", read_value=True),
        {"Op": "new", "Session": "valid_initializer"},
        f01_eval("var bound = 31; var result = bound; result",
                 session="valid_initializer", read_value=True),
        {"Op": "new", "Session": "call"},
        f01_eval(call_source, session="call", label=call_label),
        {"Op": "new", "Session": "initializer"},
        f01_eval(initializer_source, session="initializer", label=initializer_label),
        {"Op": "new", "Session": "unfinished"},
        f01_eval(call_source[:-1], session="unfinished", label=call_label),
        {"Op": "new", "Session": "empty"},
        f01_eval("// successful without a value\n", session="empty"),
    ])
    f01_value(records[1], "int", 23)
    f01_value(records[3], "int", 31)
    f01_undefined_at(records[5], call_label, call_source, 3)
    f01_undefined_at(records[7], initializer_label, initializer_source, 4)
    assert records[9]["error"] is not None, records[9]
    assert records[9]["unfinished"] is True, records[9]
    assert records[11]["error"] is None, records[11]
    assert records[11]["valid"] is False, records[11]
