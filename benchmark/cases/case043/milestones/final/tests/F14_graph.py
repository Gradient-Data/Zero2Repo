# feature: F14
"""Acceptance of declared component connections through the public graph API."""
import struct
from F01_helpers import f01_driver
from F14_helpers import (f14_driver, f14_graph, f14_call, f14_values,
                         f14_bytes, F14_HASH, f14_record_graphs, f14_refused)


def test_declared_connections_and_reexports(f14_driver):
    # F14.T01: guest declarations select providers through instance re-exports.
    # The public connection scope covers direct function imports.
    for name, service, reexport in [('evaluate','blend',False), ('inspect','combine',True)]:
        for alternate, expected in [(False,[40,201]), (True,[72,325])]:
            wat = f14_graph('(param "left" u32) (param "right" u32)', 'u32',
                '(param i32 i32) (result i32) local.get 0 i32.const 7 i32.mul local.get 1 i32.sub',
                '(param i32 i32) (result i32)',
                'local.get 0 i32.const 19 call $target i32.const 3 i32.add',
                caller_params='(param i32)', name=name, service=service, reexport=reexport,
                alternative='(param i32 i32) (result i32) local.get 0 i32.const 11 i32.mul local.get 1 i32.sub',
                choose_alternative=alternate, import_name="selected-function")
            assert f14_values(f14_driver.observe(wat, [f14_call(name,8),f14_call(name,31)])) == expected

    wat = f14_graph('(param "value" u32)', 'u32',
        '(param i32) (result i32) local.get 0 i32.const 5 i32.mul',
        '(param i32) (result i32)', 'i32.const 9 call $target i32.const 4 call $second i32.sub',
        extra_functions=[('other', '(param "value" u32)', 'u32',
                          '(param i32) (result i32) local.get 0 i32.const 13 i32.add')])
    wat = wat.replace('(component $Consumer', '(component $Consumer (import "second" (func $second (param "value" u32) (result u32)))', 1)
    wat = wat.replace('(core module $main', '(core func $lower-second (canon lower (func $second))) (core module $main', 1)
    wat = wat.replace('(import "storage"', '(import "dependency" "second" (func $second (param i32) (result i32))) (import "storage"', 1)
    wat = wat.replace('(core instance $deps', '(core instance $deps (export "second" (func $lower-second))', 1)
    wat = wat.replace('(instantiate $Consumer', '(instantiate $Consumer (with "second" (func $provider "other"))', 1)
    assert f14_values(f14_driver.observe(wat, [f14_call()])) == [28]


def test_scalar_sequences_and_recursive_values(f14_driver):
    # F14.T02: each promised scalar is both an argument and a result.
    vectors = [
        ('bool', 1, 0, 'i32.xor', 1), ('bool', 1, 1, 'i32.xor', 0),
        ('s8', -83, 21, 'i32.sub', -104), ('u8', 241, 19, 'i32.sub', 222),
        ('s16', -27000, 1234, 'i32.sub', -28234), ('u16', 62001, 171, 'i32.sub', 61830),
        ('s32', -123456789, 2345678, 'i32.sub', -125802467),
        ('u32', -268435455, 17, 'i32.sub', -268435472),
        ('char', 0x1f642, 2, 'i32.add', 0x1f644),
    ]
    for ty, left, right, op, expected in vectors:
        second = 'u32' if ty == 'char' else ty
        extend = {'s8':'i32.extend8_s','s16':'i32.extend16_s'}.get(ty,'')
        wat = f14_graph(f'(param "left" {ty}) (param "right" {second})', ty,
            f'(param i32 i32) (result i32) local.get 0 {extend} local.get 1 {extend} {op}',
            '(param i32 i32) (result i32)',
            f'i32.const {left} i32.const {right} call $target {extend}')
        assert f14_values(f14_driver.observe(wat, [f14_call()])) == [expected], ty
    types = [('pair','(tuple s16 char)'),
             ('inner','(record (field "enabled" bool) (field "point" $pair))'),
             ('outer','(tuple u8 $inner s32)')]
    wat = f14_graph('(param "payload" $outer) (param "tail" u32)', 's32',
        '(param i32 i32 i32 i32 i32 i32) (result i32) '
        'local.get 0 local.get 1 i32.const 3 i32.mul i32.add '
        'local.get 2 i32.extend16_s i32.const 5 i32.mul i32.add local.get 3 i32.const 7 i32.mul i32.add '
        'local.get 4 i32.const 11 i32.mul i32.add local.get 5 i32.const 13 i32.mul i32.add',
        '(param i32 i32 i32 i32 i32 i32) (result i32)',
        'i32.const 201 i32.const 1 i32.const -1234 i32.const 955 i32.const -8001 i32.const 19 call $target',
        types=types)
    assert f14_values(f14_driver.observe(wat, [f14_call()])) == [-87045]


def test_strings_lists_and_records_cross_memories(f14_driver):
    # F14.T03: hash every byte in the receiving guest, including empty values.
    # The checksum is independently evaluated from the supplied bytes below.
    samples = [(b'',17), ('A\x00é水🙂z'.encode(), -1288906418),
               (bytes(33 + (i * 17) % 90 for i in range(769)), None)]
    for payload, expected in samples:
        value = 17
        for byte in payload: value = (value * 31 + byte) & 0xffffffff
        expected = value if value < 2**31 else value - 2**32
        wat = f14_graph('(param "text" string)', 'u32',
            '(param i32 i32) (result i32) local.get 0 local.get 1 call $hash',
            '(param i32 i32) (result i32)',
            f'i32.const 512 i32.const {len(payload)} call $target',
            data=f'(data (i32.const 512) {f14_bytes(payload)})', provider_data=F14_HASH)
        got = f14_values(f14_driver.observe(wat, [f14_call()]))
        assert got == [expected], ('string',got)
    # Each numeric width/signedness and bool/char list is an enumerated promise.
    lists = [
        ('bool','B',[1,0,1],507409), ('s8','b',[-127,3,91],630600),
        ('u8','B',[251,0,73],747731), ('s16','h',[-30001,17,27890],-333079691),
        ('u16','H',[65001,19,257],517535154), ('s32','i',[-123456789,0,7654321],488416530),
        ('u32','I',[0xf1234567,37,0x80000001],248778263),
        ('s64','q',[-0x123456789ab,17,0x76543210fedc],-862185621),
        ('u64','Q',[0xf123456789abcdef,0,0x8000000000000001],-396955048),
        ('f32','f',[-3.5,0.25,1024.5],-2090375293), ('f64','d',[-9.25,0.125,65536.5],-350458058),
        ('char','I',[0x3bb,0x1f642,0],-752570932),
    ]
    lists.append(('u16','H',[],17))
    for ty, fmt, values, expected in lists:
        payload = struct.pack('<'+fmt*len(values), *values)
        size = struct.calcsize('<'+fmt)
        wat = f14_graph('(param "values" $items)', 'u32',
            f'(param i32 i32) (result i32) local.get 0 local.get 1 i32.const {size} i32.mul call $hash',
            '(param i32 i32) (result i32)',
            f'i32.const 512 i32.const {len(values)} call $target',
            types=[('items', f'(list {ty})')],
            data=f'(data (i32.const 512) {f14_bytes(payload)})', provider_data=F14_HASH)
        got = f14_values(f14_driver.observe(wat, [f14_call()]))
        assert got == [expected], (ty,got)
    # Record results retain strings and lists within the public connection scope.
    for shape, wat in f14_record_graphs():
        assert f14_values(f14_driver.observe(wat,[f14_call(),f14_call()])) == ([1,2] if shape == 'scalar-record-result' else [1,1]), shape


def test_missing_unsupported_and_out_of_bounds_are_refused(f14_driver):
    # F14.T04: prove the same connection works before each rejected condition.
    base = dict(params='(param "value" u32)', result='u32',
        provider_body='(param i32) (result i32) local.get 0 i32.const 9 i32.add',
        lower_signature='(param i32) (result i32)', caller_body='i32.const 42 call $target')
    assert f14_values(f14_driver.observe(f14_graph(**base), [f14_call()])) == [51]
    missing = f14_driver.observe(f14_graph(**base, missing=True), [f14_call()], valid=False)
    f14_refused(missing, 'ImportUnsatisfied')
    for ty, core in [('s64','i64'),('u64','i64'),('f32','f32'),('f64','f64')]:
        wat = f14_graph(f'(param "value" {ty})', 'u32',
            f'(param {core}) (result i32) i32.const 67',
            f'(param {core}) (result i32)', f'{core}.const 42 call $target')
        observed = f14_driver.observe(wat,[f14_call()])
        f14_refused(observed, 'UnsupportedBoundaryType')
    for encoding in ('utf16','latin1+utf16'):
        observed = f14_driver.observe(f14_graph(**base, encoding=encoding),[f14_call()])
        f14_refused(observed, 'UnsupportedBoundaryType')
    for ty, types, count in [('string', [], 4), ('$items',[('items','(list u32)')],1)]:
        for ptr, fails in [(512,False),(131068,False),(131071,True)]:
            wat = f14_graph(f'(param "value" {ty})', 'u32',
                '(param i32 i32) (result i32) global.get $calls i32.const 1 i32.add global.set $calls local.get 0 i32.load',
                '(param i32 i32) (result i32)',
                f'local.get 0 i32.const {count} call $target', types=types, caller_params='(param i32)',
                data='(data (i32.const 512) "ABCD") (data (i32.const 131068) "ABCD")',
                provider_data='(global $calls (mut i32) (i32.const 0))',
                extra_functions=[('received','','u32','(result i32) global.get $calls')])
            observed = f14_driver.observe(wat,[f14_call('received'),f14_call('evaluate',ptr),f14_call('received')])
            if fails:
                assert observed == {'instantiated':True,'calls':[{'value':0,'err':None}, {'value':None,'err':'OutOfBoundsLoad'}, {'value':0,'err':None}]}
            else:
                assert f14_values(observed) == [0,1145258561,1]
