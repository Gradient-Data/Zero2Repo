# feature: F07
"""The five planned public observability and interpreter-diagnostic checks."""
from F07_helpers import (
    f01_driver, f07_driver, f02_arg, f02_values, f07_call,
    f07_normalized_events, f07_events, f07_identity, f07_assert_fault, f07_assert_growth,
    f07_locations, f07_location, f07_assert_trace, F07_GUEST,
)


def test_module_notifications_and_nonreused_instance_identity(f07_driver):
    good = f07_driver.binary(F07_GUEST)
    rejected = good[:4] + b'\x02\0\0\0'
    start = f07_driver.binary('(module (func $start unreachable) (start $start))')
    for engine in ('interp', 'jit'):
        observed = f07_driver.run([good, b'', start], [
            ('load',0,0), ('new',0,0,-1), ('drop',0), ('new',0,0,-1),
            ('load',1,1), ('validate',1,1), ('load',2,2), ('new-null',1,2,-1)], engine=engine)
        assert f07_identity(observed[1]) != f07_identity(observed[3]), observed
        for row in observed[4:6]:
            assert row == {'result': {'accepted': False}, 'events': [{'event':'compile','accepted':False}]}
        assert observed[7]['result']['created'] is False
        assert [e['kind'] for e in f07_events(observed[7], 'trap')] == [1]
    for api in ('c', 'zig'):
        for engine in ('interp', 'jit'):
            ops = [('load', 0, 0), ('load', 1, 1), ('load', 2, 2),
                   ('new', 0, 0, -1), ('new', 1, 0, -1),
                   f07_call(1, 'boom'), f07_call(0, 'divide'),
                   ('drop', 0), ('new', 2, 2, -1), ('new', 0, 0, -1),
                   f07_call(0, 'boom'), f07_call(1, 'divide')]
            if api == 'c':
                ops += [('validate', 3, 0), ('validate', 3, 1)]
            got = f07_driver.run([good, rejected, start], ops, api=api, engine=engine)
            for index, accepted in ((0, True), (1, False), (2, True)):
                assert got[index] == {'result': {'accepted': accepted},
                                      'events': [{'event': 'compile', 'accepted': accepted}]}, got[index]
            first, second, later = (f07_identity(got[i]) for i in (3, 4, 9))
            assert len({first, second, later}) == 3, got
            for index, identity, kind, error in ((5, second, 1, 'Unreachable'),
                                                (6, first, 2, 'DivByZero'),
                                                (10, later, 1, 'Unreachable'),
                                                (11, second, 2, 'DivByZero')):
                f07_assert_fault(got[index], api, kind, error)
                assert f07_events(got[index], 'trap') == [{'event': 'trap', 'id': identity, 'kind': kind}], got[index]
            assert got[8]['result']['created'] is False, got[8]
            if api == 'c':
                assert got[8]['result']['failure']['trap'] == 1, got[8]
            else:
                assert got[8]['result']['error'] == 'StartTrapped', got[8]
            assert f07_events(got[8], 'instance') == [], got[8]
            assert len(f07_events(got[8], 'trap')) == 1, got[8]
            assert f07_events(got[8], 'trap')[0]['kind'] == 1, got[8]
            if api == 'c':
                for observation, accepted in zip(got[12:], (True, False)):
                    assert observation == {'result': {'accepted': accepted},
                                           'events': [{'event': 'compile', 'accepted': accepted}]}, observation


def test_attributed_traps_paired_exhaustion_and_real_growth(f07_driver):
    binary = f07_driver.binary(F07_GUEST)
    standalone = f07_driver.run([], [('standalone',)])
    assert standalone[0]['result'] == {'ok': True, 'size': 2}
    events = f07_events(standalone[0], 'growth')
    assert len(events) == 1, standalone
    assert events[0]['old'] == 1 and events[0]['new'] == 2, standalone
    refused = f07_driver.run([binary], [('load',0,0), ('new',0,0,-1),
        ('grow',0,'memory',1), ('size',0,'memory'), ('grow',0,'memory',100),
        ('size',0,'memory')], engine='jit')
    assert refused[2]['result'] == {'ok':True}
    assert refused[3]['result'] == refused[5]['result'] == {'size':2}
    assert refused[4] == {'result':{'ok':False}, 'events':[]}
    for api in ('c', 'zig'):
        for engine in ('interp', 'jit'):
            ops = [('load', 0, 0), ('new', 0, 0, -1), ('new', 1, 0, -1),
                   ('size', 0, 'memory'), f07_call(0, 'grow', [f02_arg(0, 2)], 1), ('size', 0, 'memory'),
                   ('grow', 1, 'memory', 3), ('size', 1, 'memory'), ('size', 0, 'memory'),
                   f07_call(0, 'boom'), f07_call(1, 'divide'),
                   ('fuel', 1, 37), f07_call(1, 'spin'), ('unfuel', 1),
                   ('fuel', 0, 91), f07_call(0, 'spin'), ('unfuel', 0),
                   f07_call(1, 'step', [f02_arg(0, 19)], 1)]
            got = f07_driver.run([binary], ops, api=api, engine=engine)
            a, b = f07_identity(got[1]), f07_identity(got[2])
            assert a != b, got
            assert got[3]['result'] == {'size': 1}
            assert got[4]['result'] == f02_values((0, 1))
            assert got[5]['result'] == {'size': 3}
            assert got[6]['result'] == ({'ok': True} if api == 'c' else {'old': 1})
            assert got[7]['result'] == {'size': 4}
            assert got[8]['result'] == {'size': 3}
            f07_assert_growth(got[4], a, 0, 1, 3)
            f07_assert_growth(got[6], b, 0, 1, 4)
            for index, identity, kind, error in ((9, a, 1, 'Unreachable'), (10, b, 2, 'DivByZero'),
                                                (12, b, 17, 'OutOfFuel'), (15, a, 17, 'OutOfFuel')):
                f07_assert_fault(got[index], api, kind, error)
                assert f07_events(got[index], 'trap') == [{'event': 'trap', 'id': identity, 'kind': kind}], got[index]
                assert f07_events(got[index], 'fuel') == ([{'event': 'fuel', 'id': identity}] if kind == 17 else []), got[index]
            assert got[17]['result'] == f02_values((0, 19)), got
    # A second memory makes an always-zero memory identity observably wrong.
    multi = f07_driver.binary('''(module (memory (export "first") 1 8) (memory (export "second") 2 8)
      (func (export "grow") (param i32) (result i32) local.get 0 memory.grow 1)
      (func (export "size_second") (result i32) memory.size 1)
      (func (export "size_first") (result i32) memory.size 0))''')
    got = f07_driver.run([multi], [('load', 0, 0), ('new', 0, 0, -1),
        f07_call(0, 'grow', [f02_arg(0, 1)], 1), f07_call(0, 'size_second', results=1),
        ('grow', 0, 'first', 2), f07_call(0, 'size_second', results=1), f07_call(0, 'size_first', results=1)])
    identity = f07_identity(got[1])
    assert got[2]['result'] == f02_values((0, 2)), got
    assert got[3]['result'] == f02_values((0, 3)), got
    assert got[4]['result'] == {'ok': True}, got
    assert got[5]['result'] == got[6]['result'] == f02_values((0, 3)), got
    f07_assert_growth(got[2], identity, 1, 2, 3)
    f07_assert_growth(got[4], identity, 0, 1, 3)


def test_passive_registration_removal_and_excluded_events(f07_driver):
    binary = f07_driver.binary(F07_GUEST)
    for api in ('c', 'zig'):
        for engine in ('interp', 'jit'):
            prefix = [('load', 0, 0), ('new', 0, 0, -1),
                      f07_call(0, 'step', [f02_arg(0, 23)], 1), f07_call(0, 'read', results=1),
                      f07_call(0, 'grow', [f02_arg(0, 2)], 1), ('grow', 0, 'memory', 1),
                      f07_call(0, 'boom'), ('fuel', 0, 31), f07_call(0, 'spin'), ('unfuel', 0)]
            suffix = [('load', 1, 0), ('new', 1, 1, -1),
                      f07_call(0, 'step', [f02_arg(0, 7)], 1), f07_call(0, 'read', results=1),
                      f07_call(0, 'grow', [f02_arg(0, 1)], 1), ('grow', 0, 'memory', 1),
                      f07_call(0, 'boom'), ('fuel', 0, 31), f07_call(0, 'spin'), ('unfuel', 0),
                      f07_call(0, 'grow', [f02_arg(0, 20)], 1),
                      ('size', 0, 'memory'), f07_call(0, 'read', results=1)]
            if api == 'c':
                suffix += [('hosttrap',)]
            ops = prefix + suffix
            live = f07_driver.run([binary], ops, api=api, engine=engine)
            off = f07_driver.run([binary], ops, api=api, engine=engine, enabled=False)
            assert [x['result'] for x in off] == [x['result'] for x in live], (live, off)
            assert all(x['events'] == [] for x in off), off
            assert live[2]['result'] == live[3]['result'] == f02_values((0, 23)), live
            assert live[12]['result'] == live[13]['result'] == f02_values((0, 30)), live
            assert live[20]['result'] == f02_values((0, -1)), live
            assert live[21]['result'] == {'size': 6} and live[22]['result'] == f02_values((0, 30)), live
            assert live[20]['events'] == [], live
            f07_assert_fault(live[6], api, 1, 'Unreachable')
            f07_assert_fault(live[8], api, 17, 'OutOfFuel')
            if api == 'c':
                assert live[23]['result'] == {'created': True}, live[23]
                assert live[23]['events'] == [], live[23]
            # Fresh processes and identical operation histories: the only
            # difference is which callback registration is removed.
            tags = ('compile', 'instance', 'trap', 'fuel', 'growth')
            for slot, tag in enumerate(tags):
                assert any(f07_events(x, tag) for x in live[:len(prefix)]), (tag, live)
                assert any(f07_events(x, tag) for x in live[len(prefix):]), (tag, live)
                cleared = f07_driver.run([binary], prefix + [('hook', slot, 0)] + suffix, api=api, engine=engine)
                aligned = cleared[:len(prefix)] + cleared[len(prefix)+1:]
                assert [x['result'] for x in aligned] == [x['result'] for x in live], (tag, cleared)
                reference_events = f07_normalized_events(live)
                actual_events = f07_normalized_events(aligned)
                assert actual_events[:len(prefix)] == reference_events[:len(prefix)], (tag, cleared)
                for reference, actual in zip(reference_events[len(prefix):], actual_events[len(prefix):]):
                    assert actual == [event for event in reference if event['event'] != tag], (tag, actual, reference)


def test_interpreter_fault_categories_have_binary_located_traces(f07_driver):
    repeated = f07_driver.binary('(module (func $leaf (param i32) local.get 0 if unreachable end unreachable) (func (export "run") i32.const 0 call $leaf))')
    locations = f07_locations(repeated)
    got = f07_driver.run([repeated], [('load',0,0), ('new',0,0,-1), f07_call(0,'run')], trace=True)
    f07_assert_trace(got[2], 1, [f07_location(locations,0,0x00,1), f07_location(locations,1,0x10)])
    prefix = '''(module
      (type $none (func)) (type $one (func (result i32)))
      (type $a (struct (field i32))) (type $b (struct (field i64)))
      (memory 1) (table 3 funcref) (elem (i32.const 0) $good $wrong)
      (func $good) (func $wrong (result i32) i32.const 2)
      (func $leaf (local i64) nop BODY)
      (func $middle (local i32 i32) nop call $leaf)
      (func (export "run") nop nop call $middle)
      (func (export "ok") (result i32) i32.const 43))'''
    # Distinct standard faults, including both arithmetic categories and both
    # invalid-indirect-target categories. No collected-case multiplication.
    faults = [
        ('unreachable', 1, 0x00),
        ('i32.const 17 i32.const 0 i32.div_s drop', 2, 0x6d),
        ('i64.const -9223372036854775808 i64.const -1 i64.div_s drop', 3, 0x7f),
        ('f64.const nan i32.trunc_f64_s drop', 4, 0xaa),
        ('i32.const 65535 i32.load drop', 5, 0x28),
        ('i32.const 65535 i64.const 13 i64.store', 5, 0x37),
        ('i32.const 3 table.get drop', 6, 0x25),
        ('i32.const 2 call_indirect (type $none)', 7, 0x11),
        ('i32.const 1 call_indirect (type $none)', 8, 0x11),
        ('ref.null $a struct.get $a 0 drop', 11, (0xfb, 2)),
        ('ref.null func ref.as_non_null drop', 11, 0xd4),
        ('i64.const 4 struct.new $b ref.cast (ref $a) drop', 12, (0xfb, 22)),
    ]
    for body, kind, opcode in faults:
        binary = f07_driver.binary(prefix.replace('BODY', body))
        locations = f07_locations(binary)
        frames = [f07_location(locations, 2, opcode), f07_location(locations, 3, 0x10), f07_location(locations, 4, 0x10)]
        got = f07_driver.run([binary], [('load', 0, 0), ('new', 0, 0, -1),
            f07_call(0, 'ok', results=1), f07_call(0, 'run')], trace=True)
        identity = f07_identity(got[1])
        assert got[2]['result'] == f02_values((0, 43)), got
        f07_assert_trace(got[3], kind, frames)
        assert f07_events(got[3], 'trap') == [{'event': 'trap', 'id': identity, 'kind': kind}], got[3]


def test_guest_call_chains_recursion_cross_instance_start_and_cap(f07_driver):
    recursive_direct = f07_driver.binary('''(module
      (func $rec (export "run") (param i32)
        local.get 0 i32.eqz if unreachable end
        local.get 0 i32.const 1 i32.sub call $rec))''')
    locations = f07_locations(recursive_direct)
    expected = [f07_location(locations,0,0x00)] + [f07_location(locations,0,0x10)] * 7
    for enabled in (True,False):
        observed = f07_driver.run([recursive_direct], [('load',0,0), ('new',0,0,-1),
            f07_call(0,'run',[f02_arg(0,7)])], trace=True, enabled=enabled)
        f07_assert_trace(observed[2],1,expected)
    guest = f07_driver.binary('''(module (type $none (func))
      (table 1 funcref) (elem (i32.const 0) $leaf)
      (func $leaf (local i64) nop unreachable)
      (func $middle nop i32.const 0 call_indirect (type $none))
      (func (export "run") nop nop call $middle))''')
    loc = f07_locations(guest)
    inner = [f07_location(loc, 0, 0x00), f07_location(loc, 1, 0x11), f07_location(loc, 2, 0x10)]
    caller = f07_driver.binary('''(module (import "provider" "run" (func $remote))
      (func $bridge (local i32) nop call $remote)
      (func (export "run") nop nop call $bridge))''')
    cloc = f07_locations(caller)
    chain = inner + [f07_location(cloc, 0, 0x10), f07_location(cloc, 1, 0x10)]
    got = f07_driver.run([guest, caller], [('load', 0, 0), ('new', 0, 0, -1),
        f07_call(0, 'run'), ('load', 1, 1), ('new', 1, 1, 0), f07_call(1, 'run')], trace=True)
    f07_identity(got[1]); f07_identity(got[4])
    f07_assert_trace(got[2], 1, inner)
    f07_assert_trace(got[5], 1, chain)
    # Same indirect/direct chain reached through a declared module start.
    start = f07_driver.binary('''(module (import "provider" "run" (func $remote))
      (func $start (local f64) nop nop nop call $remote) (start $start))''')
    sloc = f07_locations(start)
    started = f07_driver.run([guest, start], [('load', 0, 0), ('new', 0, 0, -1),
        ('load', 1, 1), ('new', 1, 1, 0)], trace=True)
    assert started[3]['result']['created'] is False, started
    f07_assert_trace({'result': started[3]['result']['failure']}, 1, inner + [f07_location(sloc, 0, 0x10)])
    direct_start = f07_driver.binary('''(module (func $leaf (local i32) nop unreachable)
      (func $start nop nop call $leaf) (start $start))''')
    dloc = f07_locations(direct_start)
    got = f07_driver.run([direct_start], [('load', 0, 0), ('new', 0, 0, -1)], trace=True)
    assert got[1]['result']['created'] is False, got
    f07_assert_trace({'result': got[1]['result']['failure']}, 1,
                     [f07_location(dloc, 0, 0x00), f07_location(dloc, 1, 0x10)])
    # Alternating recursive functions distinguish reversed or wrong-end
    # truncation even when many frames repeat. Cover below/at/above the
    # guaranteed depth; implementations may retain more than that minimum.
    recursive = f07_driver.binary('''(module
      (func $a (param i32) (local i64)
        local.get 0 i32.eqz if unreachable end
        local.get 0 i32.const 1 i32.sub call $b)
      (func $b (param i32) (local i32 i32)
        nop local.get 0 i32.eqz if unreachable end
        local.get 0 i32.const 1 i32.sub call $a)
      (func (export "run") (param i32) local.get 0 call $a))''')
    rloc = f07_locations(recursive)
    for depth in (4, 61, 62, 63, 88):
        expected = [f07_location(rloc, depth % 2, 0x00)]
        expected += [f07_location(rloc, level % 2, 0x10) for level in range(depth-1, -1, -1)]
        expected += [f07_location(rloc, 2, 0x10)]
        got = f07_driver.run([recursive], [('load', 0, 0), ('new', 0, 0, -1),
            f07_call(0, 'run', [f02_arg(0, depth)])], trace=True)
        f07_identity(got[1])
        f07_assert_trace(got[2], 1, expected)
