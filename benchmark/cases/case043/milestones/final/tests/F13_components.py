# feature: F13
"""Acceptance of self-describing components through the public Zig embedder.

Oracles: explicit WAT declarations and guest computations, validated independently
by wasm-tools; scalar and memory layouts follow the Component Model Canonical ABI
(https://github.com/WebAssembly/component-model/blob/main/design/mvp/CanonicalABI.md).
Narrow signed guest parameters are interpreted at their declared value width.
No product conversion helper constructs an expected result. Finite dyadic float computations
are exact in IEEE 754; no NaN payload or unspecified rounding choice is pinned.
"""
from F01_helpers import f01_driver
from F13_helpers import (
    f13_driver, f13_call, f13_values, f13_component, f13_scalar_wat,
    f13_compound_wat, f13_record, f13_async_boundary_component,
    f13_wide_tuple_component, F13_STRING_BODY,
)


def test_discover_exports_and_named_types(f13_driver):
    """F13.T01 — names are compared as a set; declared member order is semantic."""
    funcs = [
        ('left', '(param "value" s32)', 's32',
         '(param i32) (result i32) local.get 0 i32.const 11 i32.add'),
        ('left-extra', '(param "value" s32)', 's32',
         '(param i32) (result i32) local.get 0 i32.const 4 i32.add'),
        ('right', '(param "value" s32)', 's32',
         '(param i32) (result i32) local.get 0 i32.const 3 i32.mul'),
        ('decorate', '(param "text" string)', 'string', F13_STRING_BODY),
    ]
    exports = '''
(instance $left (export "apply" (func $left)) (export "also" (func $left-extra)))
(export "left" (instance $left))
(instance $right (export "apply" (func $right)))
(export "right" (instance $right))
(export "decorate" (func $decorate))'''
    observed = f13_driver.observe(
        f13_driver.binary(f13_component(funcs, exports=exports)),
         [f13_call('left#apply', {'s32': 9}), f13_call('left#also', {'s32': 9}), f13_call('right#apply', {'s32': 9}),
         f13_call('decorate', {'string': 'inspect'})], discover=True,
    )
    assert f13_values(observed) == [{'s32': 20}, {'s32': 13}, {'s32': 27}, {'string': 'inspect!'}]
    assert len(observed['exports']) == 4
    scalar = {'params': [{'name': 'value', 'ty': {'prim': 's32'}}], 'result': {'prim': 's32'}}
    assert {e['name']: e['signature'] for e in observed['exports']} == {
        'left#apply': scalar, 'left#also': scalar, 'right#apply': scalar,
        'decorate': {'params': [{'name': 'text', 'ty': {'prim': 'string'}}], 'result': {'prim': 'string'}},
    }

    # Only binary bytes are given to the public entry; no WIT sidecar exists.
    rich = f13_driver.observe(f13_driver.binary(f13_compound_wat()), discover=True)
    assert rich['opened'] is True, rich
    u32, s16, string = {'prim': 'u32'}, {'prim': 's16'}, {'prim': 'string'}
    numbers = {'list': u32}
    rec = {'record': [
        {'name': 'point', 'ty': {'tuple': [s16, u32]}},
        {'name': 'samples', 'ty': numbers}, {'name': 'label', 'ty': string},
    ]}
    variant = {'variant': [
        {'name': 'empty', 'payload': None}, {'name': 'count', 'payload': u32},
        {'name': 'text', 'payload': string},
    ]}
    specs = [
        ('decorate', [('text', string)], string),
        ('shift', [('values', numbers)], numbers),
        ('adjust', [('payload', rec)], rec),
        ('choose', [('choice', variant)], variant),
        ('rotate', [('color', {'enum_': ['red', 'green', 'blue']})], {'enum_': ['red', 'green', 'blue']}),
        ('toggle', [('bits', {'flags': ['read', 'write', 'execute']})], {'flags': ['read', 'write', 'execute']}),
        ('maybe', [('value', {'option': {'prim': 's32'}})], {'option': {'prim': 's32'}}),
        ('answer', [('payload', rec), ('accept', {'prim': 'bool'})], {'result': {'ok': rec, 'err': string}}),
    ]
    expected = {name: {'params': [{'name': n, 'ty': t} for n, t in params], 'result': result}
                for name, params, result in specs}
    assert len(rich['exports']) == len(expected)
    assert {e['name']: e['signature'] for e in rich['exports']} == expected
    scalars = f13_driver.observe(f13_driver.binary(f13_scalar_wat()), discover=True)
    assert scalars['opened'] is True, scalars
    kinds = ('bool', 's8', 'u8', 's16', 'u16', 's32', 'u32', 's64', 'u64', 'f32', 'f64', 'char')
    assert len(scalars['exports']) == len(kinds)
    assert {e['name']: e['signature'] for e in scalars['exports']} == {
        'change-' + kind: {'params': [{'name': 'value', 'ty': {'prim': kind}}], 'result': {'prim': kind}}
        for kind in kinds
    }


def test_scalar_canonical_exchange(f13_driver):
    """F13.T02 — each specified scalar family computes, rather than echoes."""
    vectors = [
        ('bool', [False, True], [True, False]),
        ('s8', [-112, 106], [-105, 99]),
        ('u8', [250, 9], [95, 172]),
        ('s16', [-12000, 32000], [-11700, 31700]),
        ('u16', [60000, 123], [20282, 42273]),
        ('s32', [-123456789, 1987654321], [-123456806, 1987654304]),
        ('u32', [4294967294, 17], [2147483645, 2147483666]),
        ('s64', [-1125899906842611, 4503599627370513], [-1125899906842574, 4503599627370550]),
        ('u64', [18446744073709551614, 1125899906842629], [9223372036854775807, 9224497936761618436]),
        ('f32', [1.25, -7.5], [-2.5, 15.0]),
        ('f64', [1.0000000000000002, -10000000000.125], [-2.0000000000000004, 20000000000.25]),
        ('char', [128512, 20013], [128513, 20014]),
    ]
    calls = [f13_call('change-' + kind, {kind: n}) for kind, inputs, _ in vectors for n in inputs]
    expected = [{kind: n} for kind, _, outputs in vectors for n in outputs]
    observed = f13_driver.observe(f13_driver.binary(f13_scalar_wat()), calls)
    assert f13_values(observed) == expected


def test_compound_canonical_exchange(f13_driver):
    """F13.T03 — observe every value family, alternatives and ordered nesting."""
    calls, expected = [], []
    for text, output in [('', '!'), ('é猫\x00😀', 'é猫\x00😀!')]:
        calls.append(f13_call('decorate', {'string': text}))
        expected.append({'string': output})
    for numbers, output in [([], []), ([9], [16]), ([1, 4294967294, 33], [8, 5, 40])]:
        calls.append(f13_call('shift', {'list': [{'u32': x} for x in numbers]}))
        expected.append({'list': [{'u32': x} for x in output]})
    calls.append(f13_call('adjust', f13_record(-10, 41, [3, 9], '猫')))
    expected.append(f13_record(-12, 46, [3, 9], '猫'))
    for case, payload, out_case, label, out_payload in [
        (0, None, 2, 'text', {'string': 'branch'}),
        (1, {'u32': 29}, 1, 'count', {'u32': 36}),
        (2, {'string': '猫é'}, 1, 'count', {'u32': 5}),
        (2, {'string': ''}, 0, 'empty', None),
    ]:
        calls.append(f13_call('choose', {'variant': {'case': case, 'case_name': ('empty', 'count', 'text')[case], 'payload': payload}}))
        expected.append({'variant': {'case': out_case, 'case_name': label, 'payload': out_payload}})
    for before, after, label in [(0, 1, 'green'), (1, 2, 'blue'), (2, 0, 'red')]:
        calls.append(f13_call('rotate', {'enum': {'index': before, 'label': ('red', 'green', 'blue')[before]}}))
        expected.append({'enum': {'index': after, 'label': label}})
    for before, after in [(0, 5), (2, 7), (7, 2)]:
        calls.append(f13_call('toggle', {'flags': {'bits': before, 'labels': ['read', 'write', 'execute']}}))
        expected.append({'flags': {'bits': after, 'labels': ['read', 'write', 'execute']}})
    for before, after in [(None, {'s32': -91}), ({'s32': 7}, None), ({'s32': 100}, {'s32': 109})]:
        calls.append(f13_call('maybe', {'option': before}))
        expected.append({'option': after})
    calls.extend([
        f13_call('answer', f13_record(-10, 41, [3, 9], '猫'), {'bool': True}),
        f13_call('answer', f13_record(5, 8, [], 'error'), {'bool': False}),
    ])
    expected.extend([
        {'result': {'is_ok': True, 'payload': f13_record(-12, 46, [3, 9], '猫')}},
        {'result': {'is_ok': False, 'payload': {'string': 'error'}}},
    ])
    assert f13_values(f13_driver.observe(f13_driver.binary(f13_compound_wat()), calls)) == expected
    # Void calls must both update guest state and return no invented value.
    void = f13_component([
        ('remember', '(param "value" u32)', None, '(param i32) local.get 0 global.set $state'),
        ('read', '', 'u32', '(result i32) global.get $state'),
    ], core_extra='(global $state (mut i32) (i32.const 0))')
    assert f13_values(f13_driver.observe(f13_driver.binary(void), [
        f13_call('remember', {'u32': 71}), f13_call('read'),
        f13_call('remember', {'u32': 29}), f13_call('read')])) == [None, {'u32': 71}, None, {'u32': 29}]
    cleanup = f13_component([('sample', '', 'u32', '(result i32) global.get $state')],
        core_extra='(global $state (mut i32) (i32.const 23))\n        (func (export "post") (param i32)\n         global.get $state i32.const 7 i32.add global.set $state)')
    cleanup = cleanup.replace('(type $t0', '(alias core export $i "post" (core func $post)) (type $t0', 1)
    cleanup = cleanup.replace('string-encoding=utf8))', 'string-encoding=utf8 (post-return $post)))')
    assert f13_values(f13_driver.observe(f13_driver.binary(cleanup), [f13_call('sample') for _ in range(3)])) == [
        {'u32': 23}, {'u32': 30}, {'u32': 37}]
    # List elements themselves carry pointer/length pairs; returning their suffix
    # observes recursive lowering and lifting independently of primitive lists.
    types = '(type $texts-def (list string)) (export $texts "texts" (type $texts-def)) '
    types += '(type $nums-def (list u32)) (export $nums "nums" (type $nums-def)) '
    types += '(type $rows-def (list $nums)) (export $rows "rows" (type $rows-def))'
    body = '(param i32 i32) (result i32) i32.const 64 local.get 0 i32.const 8 i32.add i32.store '
    body += 'i32.const 68 local.get 1 i32.const 1 i32.sub i32.store i32.const 64'
    nested = f13_component([('tail-texts', '(param "items" $texts)', '$texts', body),
                           ('tail-rows', '(param "items" $rows)', '$rows', body)], types=types)
    texts = [{'string': s} for s in ('omit', '水é', '')]
    rows = [{'list': [{'u32': n} for n in row]} for row in ([4, 9], [], [73, 12])]
    assert f13_values(f13_driver.observe(f13_driver.binary(nested), [
        f13_call('tail-texts', {'list': texts}), f13_call('tail-rows', {'list': rows})])) == [
        {'list': texts[1:]}, {'list': rows[1:]}]
    # The earlier shapes fit direct arguments. This larger tuple is needed to
    # reject a flat-only bridge; reversing it also makes declaration order matter.
    wide = f13_driver.binary(f13_wide_tuple_component())
    calls = [f13_call('weighted', {'tuple': [{'u32': n} for n in numbers]})
             for numbers in (range(1, 21), range(20, 0, -1))]
    assert f13_values(f13_driver.observe(wide, calls)) == [{'u32': 2870}, {'u32': 1540}]


def test_input_and_retained_result_lifetimes(f13_driver):
    """F13.T04 — all returned trees are read after later calls overwrite guest storage."""
    calls = [
        f13_call('decorate', {'string': 'first 猫'}),
        f13_call('shift', {'list': [{'u32': 25}, {'u32': 50}]}),
        f13_call('answer', f13_record(-4, 80, [9, 1], 'retained'), {'bool': True}),
        f13_call('decorate', {'string': 'replacement longer 😀'}),
        f13_call('shift', {'list': [{'u32': 100}, {'u32': 200}, {'u32': 300}]}),
        f13_call('answer', f13_record(18, 13, [], 'later'), {'bool': True}),
    ]
    binary = f13_driver.binary(f13_compound_wat())
    observed = f13_driver.observe(binary, calls, discover=True, release=True)
    assert f13_values(observed) == [
        {'string': 'first 猫!'}, {'list': [{'u32': 32}, {'u32': 57}]},
        {'result': {'is_ok': True, 'payload': f13_record(-6, 85, [9, 1], 'retained')}},
        {'string': 'replacement longer 😀!'}, {'list': [{'u32': 107}, {'u32': 207}, {'u32': 307}]},
        {'result': {'is_ok': True, 'payload': f13_record(16, 18, [], 'later')}},
    ]
    assert {e['name'] for e in observed['exports']} == {
        'decorate', 'shift', 'adjust', 'choose', 'rotate', 'toggle', 'maybe', 'answer',
    }
    graph = f13_component([('calculate', '(param "value" u32)', 'u32',
                           '(param i32) (result i32) local.get 0 i32.const 9 i32.mul')])
    graph = graph.replace('(core module $m', '(core module $extra) (core module $m', 1)
    calls = [f13_call('calculate', {'u32': n}) for n in (7, 41)]
    binary = f13_driver.binary(graph)
    for release in (False, True):
        observed = f13_driver.observe(binary, calls, discover=True, release=release)
        assert f13_values(observed) == [{'u32': 63}, {'u32': 369}]
        assert [e['name'] for e in observed['exports']] == ['calculate']


def test_open_and_validation_boundaries(f13_driver):
    """F13.T05 — validation failures with a live, independently valid baseline."""
    wat = f13_component([('inc', '(param "x" u32)', 'u32',
                         '(param i32) (result i32) local.get 0 i32.const 7 i32.add')])
    valid = f13_driver.binary(wat)
    assert f13_values(f13_driver.observe(valid, [f13_call('inc', {'u32': 42})])) == [{'u32': 49}]
    cases = [
        (f13_driver.binary('(module)'), 'NotAComponent'),
        (f13_driver.binary(wat.replace('(type $t0) (canon lift', '(type 999) (canon lift'), valid=False),
         'InvalidTypeIndex'),
        (f13_driver.binary(wat.replace('(export "inc" (func $inc))',
                                      '(export "inc" (func $inc)) (export "inc" (func $inc))'), valid=False),
         'InvalidName'),
    ]
    for binary, error in cases:
        assert f13_driver.observe(binary) == {'opened': False, 'err': error}

    duplicate_types = [
        '(type $dup (func (param "x" u32) (param "x" u32)))',
        '(type $dup (record (field "x" u32) (field "x" u32)))',
        '(type $dup (variant (case "x") (case "x")))',
        '(type $dup (enum "x" "x"))',
        '(type $dup (flags "x" "x"))',
    ]
    for definition in duplicate_types:
        malformed = f13_component(
            [('inc', '(param "x" u32)', 'u32',
              '(param i32) (result i32) local.get 0 i32.const 1 i32.add')],
            types=definition + ' (export "dup" (type $dup))')
        assert f13_driver.observe(f13_driver.binary(malformed, valid=False)) == {
            'opened': False, 'err': 'InvalidName'
        }


def test_typed_invocation_failures_and_diagnostics(f13_driver):
    """F13.T06 — distinguish public failure kinds and require fresh diagnostics.

    Failure categories carry the machine-readable distinction; explanatory text
    is checked for presence without fixing its wording.
    """
    binary = f13_driver.binary(f13_compound_wat())
    payload = f13_record(-10, 41, [3, 9], 'checked')
    bad_nested = f13_record(-10, 41, [3, 9], 'checked')
    bad_nested['record'][0]['value']['tuple'][1] = {'bool': True}
    baseline = [
        f13_call('decorate', {'string': 'working'}),
        f13_call('shift', {'list': [{'u32': 12}]}),
        f13_call('answer', payload, {'bool': True}),
    ]
    rejected = [
        (f13_call('missing-transform'), 'ExportNotResolved'),
        (f13_call('decorate'), 'ArgArityMismatch'),
        (f13_call('answer', payload, {'bool': True}, {'bool': False}), 'ArgArityMismatch'),
        (f13_call('decorate', {'u32': 19}), 'ValueShapeMismatch'),
        (f13_call('answer', payload, {'u32': 1}), 'ValueShapeMismatch'),
        (f13_call('adjust', bad_nested), 'ValueShapeMismatch'),
        (f13_call('adjust', {'record': []}), 'ValueShapeMismatch'),
        (f13_call('shift', {'list': [{'string': 'wrong element'}]}), 'ValueShapeMismatch'),
        (f13_call('choose', {'variant': {'case': 1, 'case_name': 'count', 'payload': None}}), 'ValueShapeMismatch'),
        (f13_call('maybe', {'option': {'string': 'wrong payload'}}), 'ValueShapeMismatch'),
    ]
    observed = f13_driver.observe(binary, baseline + [call for call, _ in rejected], diagnostics=True)
    assert observed['opened'] is True, observed
    assert observed['calls'][:len(baseline)] == [
        {'value': {'string': 'working!'}, 'err': None},
        {'value': {'list': [{'u32': 19}]}, 'err': None},
        {'value': {'result': {'is_ok': True, 'payload': f13_record(-12, 46, [3, 9], 'checked')}}, 'err': None},
    ]
    assert observed['calls'][len(baseline):] == [
        {'value': None, 'err': error} for _, error in rejected
    ]
    assert len(observed['diagnostics']) == len(observed['calls'])
    for diagnostic in observed['diagnostics'][len(baseline):]:
        # Explanatory text is not a machine-readable attribution carrier.
        assert isinstance(diagnostic, str) and diagnostic, observed


def test_unsupported_typed_boundaries(f13_driver):
    """F13.T07 — unsupported typed values fail through the ordinary typed entry."""
    function = [('decorate', '(param "text" string)', 'string', F13_STRING_BODY)]
    baseline = f13_driver.observe(f13_driver.binary(f13_component(function)),
                                  [f13_call('decorate', {'string': '猫'})])
    assert f13_values(baseline) == [{'string': '猫!'}]
    for encoding in ('utf16', 'latin1+utf16'):
        observed = f13_driver.observe(f13_driver.binary(f13_component(function, encoding=encoding)),
                                      [f13_call('decorate', {'string': '猫'})])
        assert observed == {'opened': True, 'calls': [{'value': None, 'err': 'UnsupportedEncoding'}]}
    # Each direction has a supported call in the SAME component and run.
    for family in ('stream', 'future'):
        binary = f13_driver.binary(f13_async_boundary_component(family))
        observed = f13_driver.observe(binary, [f13_call('baseline', {'u32': 7}),
                                               f13_call('consume', {'u32': 7}), f13_call('produce')])
        assert observed == {'opened': True, 'calls': [
            {'value': {'u32': 20}, 'err': None},
            {'value': None, 'err': 'UnsupportedType'}, {'value': None, 'err': 'UnsupportedType'},
        ]}
