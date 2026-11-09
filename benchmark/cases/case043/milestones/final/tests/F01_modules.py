# feature: F01
"""Acceptance of core modules through public C and native Zig embedding APIs.

The binary validity oracle is wasm-tools (the published Core specification).
Arithmetic vectors below were observed on the reference and independently
checked using Core integer/global/memory semantics; no product transform is
reimplemented. The declaration test covers the existing public type surface;
detailed GC subtypes and wide limits are outside FP-01.03. The
version test exercises the published memory64/table64 refusal boundary.
"""
from F01_helpers import f01_driver, f01_named, f01_decode_import_export_declarations


def test_accept_valid_core_modules_without_execution(f01_driver):
    # A start and an export that trap must still be inspectable before instantiation.
    cases = [
        ("v1_0", "(module)", [], []),
        ("v1_0", '''(module
            (import "runtime" "observe" (func (param i64)))
            (func $start unreachable) (start $start)
            (func (export "never-run") (result i32) unreachable)
            (memory (export "storage") 1 3))''',
         [("runtime", "observe", "func")], [("never-run", "func"), ("storage", "memory")]),
        ("v2_0", '''(module
            (func (export "pair") (param i32) (result i32 i64)
                local.get 0 i32.extend8_s i64.const 19))''', [], [("pair", "func")]),
        ("v3_0", '''(module
            (func $leaf (result i32) i32.const 23)
            (func (export "tail") (result i32) return_call $leaf))''', [], [("tail", "func")]),
    ]
    kinds = {"func": 0, "global": 1, "table": 2, "memory": 3, "tag": 4}
    for level, wat, imports, exports in cases:
        binary = f01_driver.wat(wat)
        assert f01_driver.standard_valid(binary), wat
        expected = f01_named(imports, exports)
        c = f01_driver.observe(binary, level=level)
        assert c["valid"] is True and c["loaded"] is True, (level, c)
        assert [{"module": i["module"], "name": i["name"], "kind": i["type"]["kind"]}
                for i in c["declarations"]["imports"]] == [dict(i, kind=kinds[i["kind"]]) for i in expected["imports"]]
        assert [{"name": e["name"], "kind": e["type"]["kind"]}
                for e in c["declarations"]["exports"]] == [dict(e, kind=kinds[e["kind"]]) for e in expected["exports"]]
        zig = f01_driver.observe(binary, level=level, mode="zig")
        assert zig == dict(expected, loaded=True), (level, zig)


def test_serialized_module_preserves_declarations_and_execution(f01_driver):
    binaries = [f01_driver.wat(source) for source in (STATEFUL_MODULE, SECOND_STATEFUL_MODULE)]
    for binary in binaries:
        assert f01_driver.standard_valid(binary)
    for seed, inputs, initial, vectors in [
        (7, (4, -9, 12), (18, 12), ((34, 66, 151), (24, 64, 123))),
        (-3, (0, 8, -2), (8, 22), ((10, 25, 45), (28, 45, 89))),
    ]:
        observed = f01_driver.serialize_many(binaries, seed=seed, inputs=inputs)
        expected = []
        for declarations, start, data, values in zip(
                (STATEFUL_DECLARATIONS, SECOND_STATEFUL_DECLARATIONS), initial, (5, 9), vectors):
            expected.append({"declarations": declarations, "execution": {
                "initial": {"global_kind": 0, "global": start, "memory": data},
                "steps": [{"kind": 0, "result": value, "global_kind": 0,
                           "global": value, "memory": value} for value in values],
            }})
        assert observed["originals"] == expected
        assert observed["restored"] == [*expected, expected[0]]


def test_shared_module_obtained_in_another_store(f01_driver):
    binary = f01_driver.wat(STATEFUL_MODULE)
    assert f01_driver.standard_valid(binary)
    for seed, inputs, initial, expected in [
        (7, (4, -9, 12), 18, (34, 66, 151)),
        (-3, (0, 8, -2), 8, (10, 25, 45)),
    ]:
        observed = f01_driver.observe(binary, mode="share", seed=seed, inputs=inputs)
        assert observed["valid"] is True and observed["loaded"] is True
        assert observed["declarations"] == STATEFUL_DECLARATIONS
        assert observed["copy_declarations"] == STATEFUL_DECLARATIONS
        states = {"initial": {"global_kind": 0, "global": initial, "memory": 5},
                  "steps": [{"kind": 0, "result": value, "global_kind": 0,
                             "global": value, "memory": value} for value in expected]}
        assert observed["original"] == states
        assert observed["copy"] == states


def test_reject_malformed_and_semantically_invalid_modules(f01_driver):
    baseline = f01_driver.wat('(module (func (export "answer") (result i32) i32.const 5))')
    assert f01_driver.standard_valid(baseline)
    # Each mutation changes a different validity condition enumerated by FP-01.06.
    # Type section following a function section violates the Core section order.
    bad_order = b"\x00asm\x01\x00\x00\x00\x03\x02\x01\x00\x01\x04\x01\x60\x00\x00\x0a\x04\x01\x02\x00\x0b"
    invalid = {
        "magic": b"\x01" + baseline[1:],
        "binary-version": baseline[:4] + b"\x02\x00\x00\x00" + baseline[8:],
        "truncated-section": baseline[:-1],
        "section-order": bad_order,
        "unknown-function": f01_driver.wat('(module (func call 3))'),
        "unknown-type": f01_driver.wat('(module (func (type 4)))'),
        "operand-type": f01_driver.wat('(module (func (result i32) i64.const 1 i32.const 2 i32.add))'),
        "operand-underflow": f01_driver.wat('(module (func (result i32) i32.add))'),
        "later-body-type": f01_driver.wat('(module (func) (func (result i32) i64.const 1))'),
        "memory-ceiling": f01_driver.wat('(module (memory 1 65537))'),
        "memory-limits": f01_driver.wat('(module (memory 3 2))'),
        "table-limits": f01_driver.wat('(module (table 4 2 funcref))'),
    }
    for mode in ("c", "zig"):
        good = f01_driver.observe(baseline, mode=mode)
        assert good["loaded"] is True
        if mode == "c":
            assert good["valid"] is True
        for label, binary in invalid.items():
            assert not f01_driver.standard_valid(binary), label
            observed = f01_driver.observe(binary, mode=mode)
            assert observed["loaded"] is False, (mode, label, observed)
            if mode == "c":
                assert observed["valid"] is False, (label, observed)
            else:
                # Both are public compile rejection carriers; wording is not graded.
                assert observed["error"] in {"ParseFailed", "ValidateFailed"}, (label, observed)



# Include an initialized data segment so restoring only code/global declarations is insufficient.
STATEFUL_MODULE = r'''(module
    (import "settings" "seed" (global $seed i32))
    (memory (export "bytes") 1 2)
    (data (i32.const 8) "\05\00\00\00")
    (global $total (export "total") (mut i32) (i32.const 11))
    (type $word (func (result i32)))
    (table 1 funcref) (elem (i32.const 0) $word)
    (func $word (result i32) i32.const 8 i32.load)
    (func $initialize
        global.get $total global.get $seed i32.add global.set $total)
    (start $initialize)
    (func (export "advance") (param $delta i32) (result i32)
        global.get $total local.get $delta i32.add global.get $seed i32.add i32.const 0 call_indirect (type $word) i32.add global.set $total
        i32.const 8 global.get $total i32.store
        global.get $total))'''
STATEFUL_DECLARATIONS = {
    "imports": [{"module": "settings".encode().hex(), "name": "seed".encode().hex(),
                 "type": {"kind": 1, "value": 0, "mutable": 0}}],
    "exports": [
        {"name": "bytes".encode().hex(), "type": {"kind": 3, "min": 1, "max": 2}},
        {"name": "total".encode().hex(), "type": {"kind": 1, "value": 0, "mutable": 1}},
        {"name": "advance".encode().hex(), "type": {"kind": 0, "params": [0], "results": [0]}},
    ],
}

# The second independent module has a different initialization, operation,
# data segment and memory declaration, but uses the same host binding protocol.
SECOND_STATEFUL_MODULE = r'''(module
    (import "settings" "seed" (global $seed i32))
    (memory (export "bytes") 2 4)
    (data (i32.const 8) "\09\00\00\00")
    (global $total (export "total") (mut i32) (i32.const 19))
    (func $initialize
        global.get $total global.get $seed i32.sub global.set $total)
    (start $initialize)
    (func (export "advance") (param $delta i32) (result i32)
        global.get $total local.get $delta i32.sub global.get $seed i32.add i32.const 8 i32.load i32.add global.set $total
        i32.const 8 global.get $total i32.store
        global.get $total))'''
SECOND_STATEFUL_DECLARATIONS = {
    "imports": STATEFUL_DECLARATIONS["imports"],
    "exports": [
        {"name": "bytes".encode().hex(), "type": {"kind": 3, "min": 2, "max": 4}},
        *STATEFUL_DECLARATIONS["exports"][1:],
    ],
}

def test_inspect_ordered_import_export_declarations(f01_driver):
    # Every external kind occurs in both lists. Different indices, repeated
    # kinds and reordered exports prevent treating either list as a type set.
    binary = f01_driver.wat(r'''(module
        (type $mix (func (param i32 f64 i64 f32 v128 funcref externref)
                         (result i64 f32 funcref)))
        (type $event (func (param f64 i32 externref)))
        (type $empty (func))
        (type $local-event (func (param i64 f64)))
        (import "state" "counter" (global $counter (mut i64)))
        (import "events" "same" (tag $event-tag (type $event)))
        (import "math" "same" (func $compute (type $mix)))
        (import "storage" "bounded" (memory $bounded 2 23))
        (import "tables" "functions" (table $functions 3 17 funcref))
        (import "state" "constant" (global $constant f64))
        (import "storage" "unbounded" (memory $unbounded 0))
        (import "tables" "external" (table $external 5 externref))
        (import "\ce\bb" "" (func $empty-func (type $empty)))
        (import "events" "empty" (tag $empty-tag (type $empty)))
        (tag $local-tag (type $local-event))
        (table $local-table 65539 70001 externref)
        (export "local-event" (tag $local-tag))
        (export "wide32" (table $local-table))
        (export "external" (table $external))
        (export "event" (tag $event-tag))
        (export "compute\00tail" (func $compute))
        (export "bounded" (memory $bounded))
        (export "constant" (global $constant))
        (export "functions" (table $functions))
        (export "counter" (global $counter))
        (export "unbounded" (memory $unbounded))
        (export "\ce\bb" (func $empty-func))
        (export "empty-event" (tag $empty-tag)))''')
    assert f01_driver.standard_valid(binary)
    expected = f01_decode_import_export_declarations(binary)
    observed = f01_driver.observe(binary)
    assert observed["valid"] is True and observed["loaded"] is True
    assert observed["declarations"] == expected
    stock = f01_driver.observe(binary, mode="stock")
    assert stock["valid"] is True and stock["loaded"] is True
    assert stock["declarations"] == expected
    native = f01_driver.observe(binary, mode="zig")
    names = {0: "func", 1: "global", 2: "table", 3: "memory", 4: "tag"}
    assert native == {
        "loaded": True,
        "imports": [{"module": entry["module"], "name": entry["name"],
                     "kind": names[entry["type"]["kind"]]} for entry in expected["imports"]],
        "exports": [{"name": entry["name"], "kind": names[entry["type"]["kind"]]}
                    for entry in expected["exports"]],
    }


def test_version_configuration_rejects_unsupported_modules(f01_driver):
    # These instructions address memory/table through i64 indices, so the same
    # module requires Core 3.0. No execution or inspection of private state is used.
    cases = [
        ("memory64", '(module (memory 1 2) (func (export "read") (param i32) (result i32) local.get 0 i32.load))',
         '(module (memory i64 1 2) (func (export "read") (param i64) (result i32) local.get 0 i32.load))'),
        ("table64", '(module (table 2 4 funcref) (func (export "ready") (result i32) i32.const 0))',
         '(module (table i64 2 4 funcref) (func (export "lookup") (param i64) (result funcref) local.get 0 table.get))'),
    ]
    for label, baseline_source, newer_source in cases:
        baseline = f01_driver.wat(baseline_source)
        newer = f01_driver.wat(newer_source)
        assert f01_driver.standard_valid(baseline, "wasm1"), label
        assert not f01_driver.standard_valid(newer, "wasm2"), label
        assert f01_driver.standard_valid(newer), label
        for level in ("v1_0", "v2_0", "v3_0"):
            for mode in ("c", "zig"):
                good = f01_driver.observe(baseline, level=level, mode=mode)
                assert good["loaded"] is True, (label, level, mode, good)
                if mode == "c":
                    assert good["valid"] is True, (label, level, good)
                observed = f01_driver.observe(newer, level=level, mode=mode)
                accepted = level == "v3_0"
                assert observed["loaded"] is accepted, (label, level, mode, observed)
                if mode == "c":
                    assert observed["valid"] is accepted, (label, level, observed)
                elif not accepted:
                    assert observed["error"] in {"ParseFailed", "ValidateFailed"}, (label, level, observed)

