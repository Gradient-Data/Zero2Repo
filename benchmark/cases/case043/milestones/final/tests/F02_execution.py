# feature: F02
"""Core execution acceptance through public embedding entries.

Oracles use https://webassembly.github.io/spec/core/exec/instructions.html
and concrete Core Specification evaluation vectors, checked against the
real reference. WAT is assembled and independently validated by wasm-tools.
Integer bits and exact binary fractions avoid accidental host rounding rules;
NaNs and relaxed multiply-add accept the standard's complete permitted sets.
Loops stay within test functions: each planned entry is one collected test.
"""
from F01_helpers import f01_driver
from F02_helpers import f02_driver, f02_arg, f02_values


def test_scalar_typed_computation(f02_driver):
    wat = '''(module
      (func (export "integer") (param i32 i32) (result i32)
        local.get 0 local.get 1 i32.add i32.const 3 i32.rotl)
      (func (export "wide") (param i64 i64) (result i64)
        local.get 0 local.get 1 i64.div_s i64.const 7 i64.xor)
      (func (export "single") (param f32 f32) (result f32)
        local.get 0 local.get 1 f32.mul f32.const 0.5 f32.sub)
      (func (export "double") (param f64 f64) (result f64)
        local.get 0 local.get 1 f64.div f64.sqrt)
      (func (export "less") (param f64 f64) (result i32)
        local.get 0 local.get 1 f64.lt)
      (func (export "convert") (param f64) (result i64)
        local.get 0 i64.trunc_f64_s)
      (func (export "rem32") (param i32 i32) (result i32) local.get 0 local.get 1 i32.rem_s)
      (func (export "rem64") (param i64 i64) (result i64) local.get 0 local.get 1 i64.rem_s)
      (func (export "unsigned32") (param i64) (result f32) local.get 0 f32.convert_i64_u)
      (func (export "unsigned64") (param i64) (result f64) local.get 0 f64.convert_i64_u)
      (func (export "nan") (param f32) (result f32) local.get 0 f32.sqrt))'''
    calls = [
        ('integer', [f02_arg(0, 0x7fffffff), f02_arg(0, 2)], 1),
        ('integer', [f02_arg(0, -10), f02_arg(0, 13)], 1),
        ('wide', [f02_arg(1, -100000000003), f02_arg(1, 9)], 1),
        ('wide', [f02_arg(1, 9876543210), f02_arg(1, -3)], 1),
        ('single', [f02_arg(2, 1.5), f02_arg(2, -4)], 1),
        ('single', [f02_arg(2, -2.25), f02_arg(2, -2)], 1),
        ('double', [f02_arg(3, 81), f02_arg(3, 4)], 1),
        ('double', [f02_arg(3, 2.25), f02_arg(3, 9)], 1),
        ('less', [f02_arg(3, -2), f02_arg(3, 0)], 1),
        ('less', [f02_arg(3, 4), f02_arg(3, -5)], 1),
        ('convert', [f02_arg(3, -123.75)], 1),
        ('convert', [f02_arg(3, 4294967297.5)], 1),
        ('nan', [f02_arg(2, -1)], 1),
        ('nan', [(2, 0x7fc00123)], 1),
    ]
    expected = [f02_values((0, 12)), f02_values((0, 24)),
                f02_values((1, -11111111106)), f02_values((1, -3292181067)),
                f02_values((2, -6.5)), f02_values((2, 4)),
                f02_values((3, 4.5)), f02_values((3, 0.5)),
                f02_values((0, 1)), f02_values((0, 0)),
                f02_values((1, -123)), f02_values((1, 4294967297))]
    numeric_calls, numeric_expected = [], []
    for kind, name in ((0, 'rem32'), (1, 'rem64')):
        for a, b, result in ((-17, 5, -2), (17, -5, 2), (-17, -5, -2)):
            numeric_calls.append((name, [f02_arg(kind, a), f02_arg(kind, b)], 1))
            numeric_expected.append(f02_values((kind, result)))
    for name, kind in (('unsigned32', 2), ('unsigned64', 3)):
        numeric_calls.append((name, [f02_arg(1, -1)], 1))
        numeric_expected.append(f02_values((kind, float(1 << 64))))
    calls[-2:-2] = numeric_calls
    expected += numeric_expected
    for engine in ('interp', 'jit'):
        for api in ('c', 'zig'):
            got = f02_driver.run(wat, calls, engine=engine, api=api, level='v1_0')
            assert got['created'] is True, got
            assert got['calls'][:-2] == expected, (engine, api, got)
            canonical = got['calls'][-2]['values'][0]
            assert canonical['kind'] == 2
            # With no NaN operand, Core requires a canonical NaN, either sign.
            assert canonical['bits'] & 0x7fffffff == 0x7fc00000, canonical
            nan = got['calls'][-1]['values'][0]
            assert nan['kind'] == 2
            # Core arithmetic NaN: either sign, any payload with the quiet bit.
            assert nan['bits'] & 0x7fc00000 == 0x7fc00000, nan


def test_locals_structured_control_and_calls(f02_driver):
    wat = '''(module
      (type $unary (func (param i32) (result i32)))
      (table 2 funcref) (elem (i32.const 0) $add $mul)
      (global $visits (mut i32) (i32.const 0))
      (func $add (type $unary) local.get 0 i32.const 3 i32.add)
      (func $mul (type $unary) local.get 0 i32.const 3 i32.mul)
      (func $double (type $unary)
        global.get $visits i32.const 1 i32.add global.set $visits
        local.get 0 i32.const 2 i32.mul)
      (func (export "run") (param $n i32) (param $target i32) (result i32)
        (local $sum i32)
        block $done loop $again
          local.get $n i32.eqz br_if $done
          local.get $sum local.get $n i32.add local.set $sum
          local.get $n i32.const 1 i32.sub local.tee $n drop br $again
        end end
        local.get $sum call $double local.get $target call_indirect (type $unary))
      (func (export "choose") (param i32) (result i32)
        block $outer block $inner
          local.get 0 br_table $inner $outer $inner
        end i32.const 31 return end i32.const 47)
      (func (export "branch") (param i32) (result i32)
        local.get 0 if (result i32) i32.const 19 else i32.const -6 end)
      (func (export "visits") (result i32) global.get $visits))'''
    calls = [('run', [f02_arg(0,n), f02_arg(0,t)], 1) for n,t in [(5,0),(8,1),(0,1)]]
    calls += [('choose', [f02_arg(0,n)], 1) for n in (0,1,9)]
    calls += [('branch',[f02_arg(0,n)],1) for n in (0,2)] + [('visits',[],1)]
    for engine in ('interp','jit'):
        got=f02_driver.run(wat,calls,engine=engine)
        assert got['created'] is True, got
        assert got['calls']==[f02_values((0,x)) for x in (33,216,0,31,47,31,-6,19,3)], got


def test_multivalue_sign_extension_and_saturating_conversion(f02_driver):
    wat='''(module
      (func (export "block") (param i32) (result i32 i64)
        block (result i32 i64) local.get 0 i32.const 9 i32.sub i64.const 4294967301 end)
      (func (export "signs32") (param i32) (result i32 i32)
        local.get 0 i32.extend8_s local.get 0 i32.extend16_s)
      (func (export "signs64") (param i64) (result i64 i64)
        local.get 0 i64.extend8_s local.get 0 i64.extend16_s)
      (func (export "wide-sign") (param i64) (result i64) local.get 0 i64.extend32_s)
      (func (export "sat") (param f64) (result i32 i64)
        local.get 0 i32.trunc_sat_f64_s local.get 0 i64.trunc_sat_f64_u))'''
    calls=[('block',[f02_arg(0,37)],2),('block',[f02_arg(0,-4)],2),
           ('signs32',[f02_arg(0,0x123480fe)],2),('signs64',[f02_arg(1,0x12345678800080fe)],2),
           ('wide-sign',[f02_arg(1,0x12345678800080fe)],1),
           ('signs32',[f02_arg(0,0x1234007f)],2),('signs64',[f02_arg(1,0xabcdef010000007f)],2),
           ('wide-sign',[f02_arg(1,0xabcdef010000007f)],1)]
    calls += [('sat',[f02_arg(3,x)],2) for x in (float('nan'),float('inf'),float('-inf'),-17.75,43.875)]
    expected=[f02_values((0,28),(1,4294967301)),f02_values((0,-13),(1,4294967301)),
              f02_values((0,-2),(0,-32514)),f02_values((1,-2),(1,-32514)),f02_values((1,-2147450626)),
              f02_values((0,127),(0,127)),f02_values((1,127),(1,127)),f02_values((1,127)),
              f02_values((0,0),(1,0)),f02_values((0,2147483647),(1,18446744073709551615)),
              f02_values((0,-2147483648),(1,0)),f02_values((0,-17),(1,0)),f02_values((0,43),(1,43))]
    for engine in ('interp','jit'):
        got=f02_driver.run(wat,calls,engine=engine,level='v2_0')
        assert got['created'] is True,got
        assert got['calls']==expected,got


def test_bulk_memory_table_and_imported_mutable_global(f02_driver):
    wat=r'''(module
      (type $answer (func (result i32)))
      (import "env" "counter" (global $counter (mut i32)))
      (memory (export "memory") 1) (data $bytes "abcdefgh")
      (table 6 funcref) (elem $functions func $a $b)
      (func $a (result i32) i32.const 13) (func $b (result i32) i32.const 29)
      (func (export "prepare") (param i32) (result i32)
        global.get $counter local.get 0 i32.add global.set $counter
        i32.const 2 i32.const 1 i32.const 6 memory.init $bytes
        i32.const 4 i32.const 2 i32.const 6 memory.copy
        i32.const 1 i32.const 90 i32.const 2 memory.fill
        i32.const 0 i32.const 0 i32.const 2 table.init $functions
        i32.const 2 ref.func $a i32.const 3 table.fill
        i32.const 1 i32.const 0 i32.const 4 table.copy
        global.get $counter)
      (func (export "lookup") (param i32) (result i32)
        local.get 0 call_indirect (type $answer))
      (func (export "null") (param i32) (result i32) local.get 0 table.get ref.is_null)
      (func (export "grow") (result i32) ref.func $b i32.const 2 table.grow)
      (func (export "overflow-fill") i32.const 65534 i32.const 77 i32.const 4 memory.fill)
      (func (export "edge") (result i32) i32.const 65534 i32.load16_u)
      (func (export "drop") data.drop $bytes elem.drop $functions)
      (func (export "data-again") i32.const 0 i32.const 0 i32.const 1 memory.init $bytes)
      (func (export "elem-again") i32.const 0 i32.const 0 i32.const 1 table.init $functions))'''
    calls=[('null',[f02_arg(0,0)],1),('prepare',[f02_arg(0,5)],1),('prepare',[f02_arg(0,-2)],1)]
    calls += [('lookup',[f02_arg(0,n)],1) for n in range(5)]
    calls += [('null',[f02_arg(0,n)],1) for n in (0,5)]
    calls += [('grow',[],1),('lookup',[f02_arg(0,7)],1),('overflow-fill',[],0),('edge',[],1)]
    calls += [('drop',[],0),('data-again',[],0),('elem-again',[],0)]
    for engine in ('interp','jit'):
        # Imported globals are in the interpreter's published execution scope.
        source = wat if engine == 'interp' else wat.replace(
            '(import "env" "counter" (global $counter (mut i32)))',
            '(global $counter (mut i32) (i32.const 11))')
        got=f02_driver.run(source,calls,engine=engine,level='v2_0',seed=11,memory=12)
        assert got['created'] is True,got
        assert got['calls']==[f02_values((0,x)) for x in (1,16,14,13,13,29,13,13,0,1,6,29)]+[{'trap':5},f02_values((0,0)),f02_values(),{'trap':5},{'trap':6}],got
        assert bytes.fromhex(got['memory'])==b'\0ZZcbcdefg\0\0',got


def test_jit_simd_and_relaxed_results(f02_driver):
    wat=r'''(module
      (memory (export "memory") 1)
      (data (i32.const 0) "\01\00\00\00\0a\00\00\00\64\00\00\00\e8\03\00\00")
      (func (export "vector") (param i32) (result i32)
        (local $v v128)
        i32.const 0 v128.load local.get 0 i32x4.splat i32x4.add local.set $v
        i32.const 16 local.get $v v128.store
        local.get $v i32x4.extract_lane 2)
      (func (export "saturate") (param i32 i32) (result i32)
        local.get 0 i16x8.splat local.get 1 i16x8.splat i16x8.add_sat_s i16x8.extract_lane_s 0)
      (func (export "shuffle") (result i32)
        v128.const i32x4 1 2 3 4 v128.const i32x4 10 20 30 40
        i8x16.shuffle 28 29 30 31 0 1 2 3 20 21 22 23 8 9 10 11
        i32x4.extract_lane 0)
      (func (export "relaxed") (param f32) (result i32)
        local.get 0 f32x4.splat
        v128.const f32x4 0x1.000002p0 0 0 0
        v128.const f32x4 -0x1.000004p0 0 0 0
        f32x4.relaxed_madd f32x4.extract_lane 0 i32.reinterpret_f32))'''
    got=f02_driver.run(wat,[('vector',[f02_arg(0,7)],1),('vector',[f02_arg(0,-3)],1),('shuffle',[],1),
                             ('relaxed',[f02_arg(2,1.0000001192092896)],1),
                             ('relaxed',[f02_arg(2,2)],1),
                             ('saturate',[f02_arg(0,30000),f02_arg(0,10000)],1),
                             ('saturate',[f02_arg(0,-30000),f02_arg(0,-10000)],1)],engine='jit',memory=32)
    assert got['created'] is True,got
    assert got['calls'][:3]==[f02_values((0,x)) for x in (107,97,40)],got
    # Relaxed madd permits separately rounded or fused operations (Core 3.0).
    assert got['calls'][3] in [f02_values((0,0)),f02_values((0,0x28800000))],got
    assert got['calls'][4] == f02_values((0,0x3f800000)),got
    assert got['calls'][5:] == [f02_values((0,32767)),f02_values((0,-32768))],got
    assert bytes.fromhex(got['memory'])[16:32]==bytes.fromhex('feffffff0700000061000000e5030000'),got


def test_gc_typed_references_and_reachable_values(f02_driver):
    wat='''(module
      (type $packed (struct (field i8))) (type $shorts (array i16))
      (func (export "packed") (param i32) (result i32 i32)
        local.get 0 struct.new $packed struct.get_s $packed 0
        local.get 0 i32.const 1 array.new $shorts i32.const 0 array.get_s $shorts)
      (type $base (sub (struct (field (mut i32)))))
      (type $child (sub $base (struct (field (mut i32)) (field i64))))
      (type $array (array (mut i32)))
      (type $fn (func (param i32) (result i32)))
      (global $keep (mut (ref null $child)) (ref.null $child))
      (global $keep_array (mut (ref null $array)) (ref.null $array))
      (func $twice (type $fn) local.get 0 i32.const 2 i32.mul)
      (elem declare func $twice)
      (func (export "create") (param i32) (result i32)
        local.get 0 i64.const 4294967303 struct.new $child global.set $keep
        local.get 0 i32.const 1 i32.add i32.const 3 array.new $array global.set $keep_array
        global.get $keep ref.is_null)
      (func (export "churn") (param i32) (result i32)
        (local $i i32)
        loop $again
          local.get $i i64.const 9 struct.new $child drop
          local.get $i i32.const 1 i32.add local.tee $i local.get 0 i32.lt_u br_if $again
        end local.get $i)
      (func (export "read") (result i32 i64 i32)
        global.get $keep ref.cast (ref $base) struct.get $base 0
        global.get $keep ref.as_non_null struct.get $child 1
        global.get $keep_array i32.const 1 array.get $array)
      (func (export "refs") (result i32 i32 i32)
        global.get $keep global.get $keep ref.eq
        global.get $keep i32.const 5 i64.const 6 struct.new $child ref.eq
        ref.null $child ref.is_null)
      (func (export "casts") (result i32 i32 i32)
        global.get $keep ref.test (ref $base)
        i32.const 5 struct.new $base ref.test (ref $child)
        global.get $keep extern.convert_any any.convert_extern ref.cast (ref eq) global.get $keep ref.eq)
      (func (export "array") (param i32) (result i32 i32)
        (local $a (ref $array))
        local.get 0 i32.const 4 array.new $array local.set $a
        local.get $a i32.const 2 i32.const 31 array.set $array
        local.get $a i32.const 1 array.get $array
        local.get $a i32.const 2 array.get $array i32.add
        local.get $a array.len)
      (func (export "typed") (param i32) (result i32)
        local.get 0 ref.func $twice call_ref $fn))'''
    # Keep three-value computation inside the guest and expose scalar results.
    # This observes every value without requiring a three-result host JIT ABI.
    for name, kinds in [('read', ('i32','i64','i32')),
                        ('refs', ('i32','i32','i32')),
                        ('casts', ('i32','i32','i32'))]:
        wat = wat.replace(f'(func (export "{name}")', f'(func ${name}')
        wrappers = []
        for index, kind in enumerate(kinds):
            locals_ = ' '.join(f'(local $v{i} {k})' for i,k in enumerate(kinds))
            saves = ' '.join(f'local.set $v{i}' for i in reversed(range(len(kinds))))
            wrappers.append(f'(func (export "{name}-{index}") (result {kind}) '
                            f'{locals_} call ${name} {saves} local.get $v{index})')
        wat = wat[:-1] + ''.join(wrappers) + ')'
    calls=[('create',[f02_arg(0,73)],1),('churn',[f02_arg(0,4096)],1),('read',[],3),('refs',[],3),('casts',[],3),
           ('array',[f02_arg(0,-8)],2),('typed',[f02_arg(0,17)],1),
           ('create',[f02_arg(0,-19)],1),('churn',[f02_arg(0,257)],1),('read',[],3),('typed',[f02_arg(0,-6)],1)]
    expected=[f02_values((0,0)),f02_values((0,4096)),f02_values((0,73),(1,4294967303),(0,74)),
              f02_values((0,1),(0,0),(0,1)),f02_values((0,1),(0,0),(0,1)),f02_values((0,23),(0,4)),f02_values((0,34)),
              f02_values((0,0)),f02_values((0,257)),f02_values((0,-19),(1,4294967303),(0,-18)),f02_values((0,-12))]
    calls += [('packed',[f02_arg(0,n)],2) for n in (0xffff,0x807f)]
    expected += [f02_values((0,-1),(0,-1)),f02_values((0,127),(0,-32641))]
    scalar_calls, scalar_expected = [], []
    for call, result in zip(calls, expected, strict=True):
        if call[0] in ('read','refs','casts'):
            for i, value in enumerate(result['values']):
                scalar_calls.append((f'{call[0]}-{i}', [], 1))
                scalar_expected.append({'values':[value]})
        else:
            scalar_calls.append(call); scalar_expected.append(result)
    for engine in ('interp','jit'):
        run_calls, run_expected = list(scalar_calls), list(scalar_expected)
        if engine == 'jit':
            run_calls[1] = ('churn',[f02_arg(0,60000)],1)
            run_expected[1] = f02_values((0,60000))
        got=f02_driver.run(wat,run_calls,engine=engine)
        assert got['created'] is True,got
        assert got['calls']==run_expected,got


def test_direct_indirect_and_reference_tail_calls(f02_driver):
    noargs='''(module
      (type $target (func (result i64)))
      (table 2 funcref) (elem (i32.const 0) $a $b)
      (func $a (type $target) i64.const 4294967311)
      (func $b (type $target) i64.const -37)
      (func (export "direct") (result i64) return_call $a)
      (func (export "indirect") (result i64) i32.const 1 return_call_indirect (type $target))
      (func (export "reference") (result i64) ref.func $a return_call_ref $target))'''
    for engine in ('interp','jit'):
        got=f02_driver.run(noargs,[(name,[],1) for name in ('direct','indirect','reference')],engine=engine)
        assert got['created'] is True,got
        assert got['calls']==[f02_values((1,x)) for x in (4294967311,-37,4294967311)],got
    recursive = """(module
      (func $sum (export "sum") (param i32 i64) (result i64)
        local.get 0 i32.eqz if (result i64) local.get 1 else
          local.get 0 i32.const 1 i32.sub
          local.get 1 local.get 0 i64.extend_i32_u i64.add return_call $sum
        end))"""
    got = f02_driver.run(recursive, [('sum',[f02_arg(0,20000),f02_arg(1,7)],1)])
    assert got['created'] is True, got
    assert got['calls'] == [f02_values((1,200010007))], got
    arguments='''(module
      (type $target (func (param i32 f64) (result f64)))
      (table 1 funcref) (elem (i32.const 0) $target)
      (func $target (type $target)
        local.get 0 f64.convert_i32_s local.get 1 f64.const 2 f64.mul f64.add)
      (func (export "direct") (type $target) local.get 0 local.get 1 return_call $target)
      (func (export "indirect") (type $target) local.get 0 local.get 1 i32.const 0 return_call_indirect (type $target))
      (func (export "reference") (type $target) local.get 0 local.get 1 ref.func $target return_call_ref $target))'''
    calls=[(name,[f02_arg(0,a),f02_arg(3,b)],1) for name,a,b in [('direct',-3,2.5),('indirect',7,-.5),('reference',12,1.25)]]
    got=f02_driver.run(arguments,calls)
    assert got['created'] is True,got
    assert got['calls']==[f02_values((3,x)) for x in (2,6,14.5)],got


def test_guest_exception_payloads_handlers_and_unhandled(f02_driver):
    integers='''(module
      (tag $a (param i32)) (tag $b (param i32))
      (func $thrower (param i32) local.get 0 throw $b)
      (func (export "handled") (param i32) (result i32)
        block $outer (result i32)
          block $inner (result i32)
            try_table (catch $a $inner) (catch $b $outer)
              local.get 0 call $thrower
            end unreachable
          end i32.const 1000 i32.add return
        end i32.const 9 i32.add)
      (func (export "first") (param i32) (result i32)
        block $handler (result i32)
          try_table (catch $a $handler) local.get 0 throw $a end unreachable
        end i32.const 3 i32.mul)
      (func (export "unhandled") (param i32) local.get 0 throw $b))'''
    calls=[('handled',[f02_arg(0,12)],1),('handled',[f02_arg(0,-17)],1),('first',[f02_arg(0,7)],1),('unhandled',[f02_arg(0,5)],0)]
    for engine in ('interp','jit'):
        got=f02_driver.run(integers,calls,engine=engine)
        assert got['created'] is True,got
        assert got['calls']==[f02_values((0,x)) for x in (21,-8,21)]+[{'trap':13}],got
    other='''(module
      (type $box (struct (field i32)))
      (tag $float (param f64)) (tag $ref (param (ref $box)))
      (func (export "float") (param f64) (result f64)
        block $h (result f64)
          try_table (catch $float $h) local.get 0 throw $float end unreachable
        end f64.const 2 f64.mul)
      (func (export "ref") (param i32) (result i32)
        block $h (result (ref $box))
          try_table (catch $ref $h) local.get 0 struct.new $box throw $ref end unreachable
        end struct.get $box 0 i32.const 1 i32.add))'''
    got=f02_driver.run(other,[('float',[f02_arg(3,-3.75)],1),('ref',[f02_arg(0,83)],1)])
    assert got['created'] is True,got
    assert got['calls']==[f02_values((3,-7.5)),f02_values((0,84))],got


def test_extended_initializers_and_custom_annotations(f02_driver):
    wat=r'''(module
      (type $f (func (result i32)))
      (import "env" "seed" (global $seed i32))
      (global $wide i64 (i64.sub (i64.mul (i64.const 10000000001) (i64.const 3)) (i64.const 19)))
      (func (export "wide-init") (result i64) global.get $wide)
      (global $initial i32 (i32.add (i32.mul (global.get $seed) (i32.const 3)) (i32.const 2)))
      (memory (export "memory") 1)
      (data (i32.add (global.get $seed) (i32.const 3)) "QZ")
      (table 4 funcref)
      (elem (i32.sub (global.get $seed) (i32.const 6)) $leaf)
      (func $leaf (result i32) i32.const 37)
      (func (export "initial") (result i32) global.get $initial)
      (func (export "load") (result i32) global.get $seed i32.const 3 i32.add i32.load8_u)
      (func (export "table") (result i32) global.get $seed i32.const 6 i32.sub call_indirect (type $f))
      ANNOTATION)'''
    calls=[('initial',[],1),('load',[],1),('table',[],1),('wide-init',[],1)]
    for seed,initial in ((7,23),(8,26)):
        for engine in ('interp','jit'):
            for annotation in ('','(@custom "annotation" "not executable; unreachable")'):
                # Direct imported-global arithmetic offsets are refused by the
                # reference; constant arithmetic offsets remain executable.
                source = wat.replace('(import "env" "seed" (global $seed i32))',
                                     f'(global $seed i32 (i32.const {seed}))')
                source = source.replace('(global.get $seed)',f'(i32.const {seed})')
                got=f02_driver.run(source.replace('ANNOTATION',annotation),calls,seed=seed,engine=engine,memory=16)
                assert got['created'] is True,got
                assert got['calls']==[f02_values((0,x)) for x in (initial,81,37)]+[f02_values((1,29999999984))],got
                assert bytes.fromhex(got['memory'])==b'\0'*(seed+3)+b'QZ'+b'\0'*(11-seed),got


    imported = r'''(module
      (type $f (func (result i32)))
      (import "env" "seed" (global $seed i32))
      (global $initial i32 (i32.add (i32.mul (global.get $seed) (i32.const 3)) (i32.const 2)))
      (memory 1) (data (global.get $seed) "QZ")
      (func (export "initial") (result i32) global.get $initial)
      (func (export "load") (result i32) global.get $seed i32.load8_u))'''
    for seed, initial in ((7,23),(8,26)):
        got=f02_driver.run(imported,calls[:2],seed=seed)
        assert got['created'] is True,got
        assert got['calls']==[f02_values((0,x)) for x in (initial,81)],got


def test_start_effects_persistent_state_and_start_trap(f02_driver):
    wat='''(module
      (import "env" "observe" (func $observe (param i32)))
      (global $state (mut i32) (i32.const 0))
      (func $start i32.const 17 global.set $state global.get $state call $observe)
      (start $start)
      (func (export "advance") (param i32) (result i32)
        global.get $state local.get 0 i32.add global.set $state
        global.get $state call $observe global.get $state))'''
    for engine in ('interp','jit'):
        got=f02_driver.run(wat,[('advance',[f02_arg(0,n)],1) for n in (5,-9,2)],engine=engine)
        assert got['created'] is True,got
        assert got['start_events']==1,got
        assert got['calls']==[f02_values((0,x)) for x in (22,13,15)],got
        assert got['events']==[17,22,13,15],got
        trapped=wat.replace('global.get $state call $observe)', 'global.get $state call $observe unreachable)')
        got=f02_driver.run(trapped,[],engine=engine)
        assert got=={'created':False,'trap':1,'events':[17]},got
        native=f02_driver.run('(module (func $s unreachable) (start $s))',[],engine=engine,api='zig')
        assert native=={'created':False,'error':'StartTrapped'},native


def test_guest_traps_stop_following_instructions(f02_driver):
    prefix='''(module
      (type $none (func)) (type $one (func (result i32)))
      (type $a (struct (field i32))) (type $b (struct (field i64)))
      (memory 1) (table 3 funcref) (elem (i32.const 0) $good $wrong)
      (func $good) (func $wrong (result i32) i32.const 2)
      (global $state (mut i32) (i32.const 0))
      (func (export "state") (result i32) global.get $state)
      (func (export "run") i32.const 11 global.set $state BODY i32.const 99 global.set $state))'''
    # Every FP-02.10 member has an explicit positive failure carrier and an
    # observable pre-trap write; a swallowed trap or continued body fails.
    cases=[('unreachable',1),('i32.const 17 i32.const 0 i32.div_s drop',2),
           ('i64.const -9223372036854775808 i64.const -1 i64.div_s drop',3),
           ('f64.const nan i32.trunc_f64_s drop',4),
           ('f64.const 3e9 i32.trunc_f64_s drop',(3,4)),
           ('f64.const inf i64.trunc_f64_u drop',(3,4)),
           ('i32.const 65535 i32.load drop',5),('i32.const 3 table.get drop',6),
           ('i32.const 2 call_indirect (type $none)',7),('i32.const 1 call_indirect (type $none)',8),
           ('i64.const 4 struct.new $b ref.cast (ref $a) drop',12)]
    for engine in ('interp','jit'):
        baseline=f02_driver.run(prefix.replace('BODY','i32.const 0 call_indirect (type $none)'),[('run',[],0),('state',[],1)],engine=engine)
        assert baseline['created'] is True,baseline
        assert baseline['calls']==[f02_values(),f02_values((0,99))],baseline
        for body,kind in cases:
            got=f02_driver.run(prefix.replace('BODY',body),[('state',[],1),('run',[],0),('state',[],1)],engine=engine)
            assert got['created'] is True,got
            kinds = kind if isinstance(kind, tuple) else (kind,)
            assert got['calls'][1] in [{'trap':k} for k in kinds], (engine,body,got)
            assert got['calls'][::2] == [f02_values((0,0)),f02_values((0,11))], (engine,body,got)
            assert len(got['calls']) == 3, got


def test_binding_failures_distinct_from_guest_faults(f02_driver):
    wat='''(module (memory (export "memory") 1)
      (func (export "divide") (param i32 i32) (result i32)
        local.get 0 local.get 1 i32.div_s))'''
    good=[f02_arg(0,42),f02_arg(0,6)]
    calls=[('divide',good,1),('missing',[],0),('memory',[],0),
           ('divide',good[:1],1),('divide',good+[f02_arg(0,9)],1),
           ('divide',good,0),('divide',good,2),('divide',[f02_arg(0,42),f02_arg(0,0)],1)]
    for engine in ('interp','jit'):
        native=f02_driver.run(wat,calls,engine=engine,api='zig')
        assert native['created'] is True,native
        assert native['calls'][2] in ({'error':'ExportNotFound'}, {'error':'NotAFunc'}),native
        assert native['calls'][:2] + native['calls'][3:] == [f02_values((0,7))]+[{'error':x} for x in (
                       'ExportNotFound','ArgArityMismatch','ArgArityMismatch',
                       'ResultArityMismatch','ResultArityMismatch','DivByZero')],native
        c=f02_driver.run(wat,[calls[i] for i in (0,3,4,5,6,7)],engine=engine)
        assert c['created'] is True,c
        assert c['calls']==[f02_values((0,7)),{'trap':0},{'trap':0},{'trap':0},{'trap':0},{'trap':2}],c


def test_unsupported_simd_execution_and_vector_boundary(f02_driver):
    wat='''(module
      (func (export "scalar") (param i32) (result i32) local.get 0 i32.const 3 i32.mul)
      (func (export "simd") (result i32) v128.const i32x4 2 3 5 7 i32x4.extract_lane 2)
      (func (export "vector") (param v128) (result i32) local.get 0 i32x4.extract_lane 0))'''
    interp=f02_driver.run(wat,[('scalar',[f02_arg(0,11)],1),('simd',[],1)])
    assert interp['created'] is True,interp
    assert interp['calls'][0]==f02_values((0,33)),interp
    # Interpreter SIMD only has to fail; no category is assigned to it.
    assert len(interp['calls'])==2 and set(interp['calls'][1])=={'trap'} and interp['calls'][1]['trap']!=-1,interp
    jit=f02_driver.run(wat,[('scalar',[f02_arg(0,-4)],1),('simd',[],1),('vector',[(4,19)],1),('vector',[],1)],engine='jit',api='zig')
    assert jit['created'] is True,jit
    assert jit['calls']==[f02_values((0,-12)),f02_values((0,5)),{'error':'UnsupportedEngineSignature'},{'error':'ArgArityMismatch'}],jit
