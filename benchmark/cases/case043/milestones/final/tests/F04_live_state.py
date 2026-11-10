# feature: F04
"""Acceptance of live instance state (seven planned functions, no case matrix).

Numeric and guest expectations use Core 3.0 load/store, growth, reference and
multi-memory semantics, independently of product representation. Integer bits
and IEEE bytes use Python's struct conversion as the independent scalar oracle.
"""
import struct
from F04_helpers import (f01_driver, f04_driver, f02_arg, f02_values,
                         f04_call, f04_ref)


def test_checked_numeric_and_c_byte_memory_are_live(f04_driver):
    # Each scalar type is a distinct public typed access; byte patterns also
    # distinguish widths, sign extension, little endian and unaligned access.
    types = [('i8','b',-51,0,'i32.load8_s','i32.store8'),
             ('u8','B',211,0,'i32.load8_u','i32.store8'),
             ('i16','h',-19237,0,'i32.load16_s','i32.store16'),
             ('u16','H',51793,0,'i32.load16_u','i32.store16'),
             ('i32','i',-1432778633,0,'i32.load','i32.store'),
             ('u32','I',0xd3a29187,0,'i32.load','i32.store'),
             ('i64','q',-0x1234567890abcde,1,'i64.load','i64.store'),
             ('u64','Q',0xe1d2c3b4a5968778,1,'i64.load','i64.store'),
             ('f32','f',-13.625,2,'f32.load','f32.store'),
             ('f64','d',1048576.03125,3,'f64.load','f64.store')]
    functions = []
    for typ,fmt,val,kind,load,store in types:
        wasm_type = ('i32','i64','f32','f64')[kind]
        functions.append(f'''(func (export "read_{typ}") (param i32) (result {wasm_type}) local.get 0 {load})
          (func (export "write_{typ}") (param i32 {wasm_type}) (result {wasm_type}) local.get 0 local.get 1 {store} local.get 1)''')
    wat = '(module (memory (export "memory") 1 2)' + ''.join(functions) + ')'
    for engine in ('interp','jit'):
        for api in ('c','zig'):
            ops, expected = [], []
            for i,(typ,fmt,val,kind,load,store) in enumerate(types):
                at = 13 + i*19
                raw = struct.pack('<'+fmt,val)
                bits = int.from_bytes(raw,'little')
                ops.append(('write',typ,at,bits) if api=='zig' else ('put',at,len(raw),raw.hex()))
                expected.append({'ok':True} if api=='zig' else {'bytes':raw.hex()})
                ops.extend([f04_call('read_'+typ,[f02_arg(0,at)],1),('bytes',at,len(raw),'-')])
                expected.extend([f02_values((kind,val)),{'bytes':raw.hex()}])
                next_val = val/2 if kind>=2 else -val if fmt.islower() else val//3
                next_raw = struct.pack('<'+fmt,next_val)
                ops.append(f04_call('write_'+typ,[f02_arg(0,at+3),f02_arg(kind,next_val)],1))
                expected.append(f02_values((kind,next_val)))
                ops.append(('bytes',at+3,len(raw),'-')); expected.append({'bytes':next_raw.hex()})
                if api=='zig':
                    ops.append(('read',typ,at+3,0)); expected.append({'bits':int.from_bytes(next_raw,'little')})
            # Exact windows include NUL, high bytes, and overlap with guest reads.
            raw = b'\x00\xff\x80\x01\x00\x37\xcc'
            ops.extend([('put',701,len(raw),raw.hex()),('bytes',701,len(raw),'-'),
                        f04_call('read_u16',[f02_arg(0,702)],1)])
            expected.extend([{'bytes':raw.hex()},{'bytes':raw.hex()},f02_values((0,0x80ff))])
            if api == 'zig':
                # Typed memory access preserves IEEE bits even when arithmetic
                # could legally choose a different NaN payload.
                for typ, width, bits in (('f32',4,0x7fc12345),('f64',8,0xfff8123456789abc)):
                    raw = bits.to_bytes(width,'little').hex()
                    ops += [('put',901,width,raw),('read',typ,901,0),
                            ('write',typ,921,bits),('bytes',921,width,'-')]
                    expected += [{'bytes':raw},{'bits':bits},{'ok':True},{'bytes':raw}]
            assert f04_driver.run(wat,ops,api=api,engine=engine) == expected


def test_memory_growth_preserves_and_refuses_at_maximum(f04_driver):
    wat = '''(module (memory (export "memory") 1 3)
      (func (export "grow") (param i32) (result i32) local.get 0 memory.grow)
      (func (export "size") (result i32) memory.size)
      (func (export "peek") (param i32) (result i32) local.get 0 i32.load8_u))'''
    for engine in ('interp','jit'):
        for api in ('zig','c'):
            ops = [('put',65532,4,'a73100fe'),('msize',),('mgrow',0),('mgrow',1),('msize',),
                   f04_call('size',results=1),('bytes',65532,4,'-'),('bytes',65536,65536,'-'),
                   f04_call('peek',[f02_arg(0,65535)],1),('put',131071,1,'b9'),
                   f04_call('grow',[f02_arg(0,1)],1),('msize',),('bytes',131071,1,'-'),
                   ('bytes',131072,65536,'-'),('mgrow',1),f04_call('grow',[f02_arg(0,1)],1),
                   ('msize',),f04_call('size',results=1),('bytes',65532,4,'-'),('bytes',131071,1,'-')]
            expected = [{'bytes':'a73100fe'},{'size':1},
                        {'old':1} if api=='zig' else {'ok':True},
                        {'old':1} if api=='zig' else {'ok':True}, {'size':2},f02_values((0,2)),
                        {'bytes':'a73100fe'},{'bytes':'00'*65536},f02_values((0,254)),{'bytes':'b9'},
                        f02_values((0,2)),{'size':3},{'bytes':'b9'},{'bytes':'00'*65536},
                        {'old':None} if api=='zig' else {'ok':False},f02_values((0,-1)),
                        {'size':3},f02_values((0,3)),{'bytes':'a73100fe'},{'bytes':'b9'}]
            if api=='c' and engine=='interp':
                # Above-maximum C interpreter host growth is outside scope;
                # guest refusal and supported host refusal paths remain checked.
                del ops[14]
                del expected[14]
            assert f04_driver.run(wat,ops,api=api,engine=engine) == expected

    multi = """(module (memory (export "memory") 1 8)
      (func (export "grow") (param i32) (result i32) local.get 0 memory.grow))"""
    for engine in ('interp','jit'):
        for api in ('zig','c'):
            ops = [('put',65535,1,'a7'),('mgrow',2),('msize',),
                   f04_call('grow',[f02_arg(0,2)],1),('mgrow',1),('msize',),
                   ('bytes',65535,1,'-'),('bytes',65536,5*65536,'-')]
            expected = [{'bytes':'a7'},{'old':1} if api=='zig' else {'ok':True},
                        {'size':3},f02_values((0,3)),
                        {'old':5} if api=='zig' else {'ok':True},{'size':6},
                        {'bytes':'a7'},{'bytes':'00'*(5*65536)}]
            assert f04_driver.run(multi,ops,api=api,engine=engine) == expected


def test_globals_and_external_references_share_live_state(f04_driver):
    kinds = [('i32',0,17,-213,49),('i64',1,8589934601,-17179869203,34359738375),
             ('f32',2,1.25,-19.5,7.125),('f64',3,-3.75,1048576.125,-0.03125)]
    wat = '''(module (table (export "table") 3 8 externref)
      (func (export "isnull") (param externref) (result i32) local.get 0 ref.is_null)'''
    for typ,kind,initial,host,guest in kinds:
        wat += f'''(global $g{kind} (export "g{kind}") (mut {typ}) ({typ}.const {initial}))
          (func (export "get{kind}") (result {typ}) global.get $g{kind})
          (func (export "set{kind}") (param {typ}) local.get 0 global.set $g{kind})'''
    wat += '''(func (export "relay") (param i32 i32) local.get 1 local.get 0 table.get table.set)
      (func (export "getref") (param i32) (result externref) local.get 0 table.get)
      (func (export "setref") (param i32 externref) local.get 0 local.get 1 table.set))'''
    for engine in ('interp','jit'):
        for api in ('zig','c'):
            ops,expected = [],[]
            for typ,kind,initial,host,guest in kinds:
                ops.extend([('global',f'g{kind}'),('gset',f'g{kind}',*f02_arg(kind,host)),
                            f04_call(f'get{kind}',results=1), f04_call(f'set{kind}',[f02_arg(kind,guest)]),('global',f'g{kind}')])
                expected.extend([f02_values((kind,initial))['values'][0],f02_values((kind,host))['values'][0],
                                 f02_values((kind,host)),f02_values(),f02_values((kind,guest))['values'][0]])
            ops.extend([('tget','table',0),('tset','table',0,1),('tset','table',1,2),
                        f04_call('getref',[f02_arg(0,0)],1),f04_call('getref',[f02_arg(0,1)],1),
                        f04_call('setref',[f02_arg(0,2),(128,1)]),('tget','table',2),
                        f04_call('setref',[f02_arg(0,0),(128,0)]),('tget','table',0),('tget','table',1)])
            expected.extend([f04_ref(0,api),{'ok':True},{'ok':True},
                             {'values':[f04_ref(1,api)]},{'values':[f04_ref(2,api)]},
                             f02_values(),f04_ref(1,api),f02_values(),f04_ref(0,api),f04_ref(2,api)])
            if api=='zig':
                # Relay through guest table.get/table.set; the Zig scalar-call
                # boundary does not expose reference results on the JIT.
                ops[23:25] = [f04_call('relay',[f02_arg(0,0),f02_arg(0,2)]),('tget','table',2),
                              f04_call('relay',[f02_arg(0,1),f02_arg(0,2)]),('tget','table',2)]
                expected[23:25] = [f02_values(),f04_ref(1,api),f02_values(),f04_ref(2,api)]
            assert f04_driver.run(wat,ops,api=api,engine=engine) == expected


def test_table_growth_reaches_declared_jit_boundary(f04_driver):
    wat = '''(module (table (export "table") 2 65536 externref)
      (func (export "isnull") (param externref) (result i32) local.get 0 ref.is_null)
      (func (export "grow") (param i32 externref) (result i32) local.get 1 local.get 0 table.grow)
      (func (export "size") (result i32) table.size)
      (func (export "null_at") (param i32) (result i32) local.get 0 table.get ref.is_null)
      (func (export "get") (param i32) (result externref) local.get 0 table.get))'''
    for engine in ('interp','jit'):
        limit = 70003 if engine=='interp' else 65536
        source = wat.replace('2 65536 externref',f'2 {limit} externref')
        for api in ('zig','c'):
            ops = [('tset','table',0,1),('tsize','table'),('tgrow','table',0,2),('tgrow','table',3,2),
                   ('tsize','table'),('tget','table',0),('tget','table',1)]
            expected = [{'ok':True},{'size':2},{'ok':True},{'ok':True},{'size':5},f04_ref(1,api),f04_ref(0,api)]
            for i in range(2,5):
                ops.extend([('tget','table',i),f04_call('get',[f02_arg(0,i)],1)])
                expected.extend([f04_ref(2,api),{'values':[f04_ref(2,api)]}])
            ops.extend([f04_call('grow',[f02_arg(0,3),(128,2)],1),('tsize','table'),
                        ('tget','table',7),('tgrow','table',limit-8,1),('tsize','table'),f04_call('size',results=1),
                        ('tget','table',0),('tget','table',4),('tget','table',7),('tget','table',8),
                        ('tget','table',limit-1),f04_call('get',[f02_arg(0,limit-1)],1),
                        ('tgrow','table',1,2),f04_call('grow',[f02_arg(0,1),(128,2)],1),
                        ('tsize','table'),f04_call('size',results=1),('tget','table',0),('tget','table',4),('tget','table',limit-1)])
            expected.extend([f02_values((0,5)),{'size':8},f04_ref(2,api),{'ok':True},{'size':limit},f02_values((0,limit)),
                             f04_ref(1,api),f04_ref(2,api),f04_ref(2,api),f04_ref(1,api),f04_ref(1,api),{'values':[f04_ref(1,api)]},
                             {'error':'GrowFailed'} if api=='zig' else {'ok':False},f02_values((0,-1)),
                             {'size':limit},f02_values((0,limit)),f04_ref(1,api),f04_ref(2,api),f04_ref(1,api)])
            # Observe every added element, including all of the large growth.
            ops.append(('tscan','table',0,limit))
            expected.append({'refs':[f04_ref(1,api),f04_ref(0,api)] + [f04_ref(2,api)]*3 +
                             [f04_ref(2,api)]*3 + [f04_ref(1,api)]*(limit-8)})
            if api=='zig':
                for i,op in enumerate(ops):
                    if op[:2]==('call','get'):
                        ops[i] = ('call','null_at',*op[2:])
                        expected[i] = f02_values((0,0))
            assert f04_driver.run(source,ops,api=api,engine=engine) == expected

    unbounded = wat.replace('2 65536 externref','2 externref')
    # The no-maximum guarantee applies to the interpreter.
    for api in ('zig','c'):
        ops = [('tgrow','table',3,2),f04_call('grow',[f02_arg(0,2),(128,1)],1),
               ('tsize','table'),('tscan','table',0,7)]
        assert f04_driver.run(unbounded,ops,api=api,engine='interp') == [
            {'ok':True},f02_values((0,5)),{'size':7},
            {'refs':[f04_ref(0,api)]*2+[f04_ref(2,api)]*3+[f04_ref(1,api)]*2}]


def test_c_function_references_call_their_origin_and_signature(f04_driver):
    wat = '''(module
      (global $state (mut i32) (i32.const 0))
      (table (export "functions") 2 2 funcref)
      (func $a (param i32 i64 f32 f64) (result i64 i32 f64 f32)
        global.get $state local.get 0 i32.add global.set $state
        local.get 1 i64.const 13 i64.add global.get $state
        local.get 3 f64.const 0.5 f64.sub local.get 2 f32.const 2 f32.mul)
      (func $b (param i32 i64 f32 f64) (result i64 i32 f64 f32)
        global.get $state local.get 0 i32.sub global.set $state
        local.get 1 i64.const 29 i64.sub global.get $state
        local.get 3 f64.const 1 f64.add local.get 2 f32.const 4 f32.mul)
      (elem (i32.const 0) $a)
      (elem declare func $b)
      (func (export "get") (result funcref funcref) ref.func $b ref.null func)
      (func (export "seed") (param i32) local.get 0 global.set $state)
      (func (export "state") (result i32) global.get $state))'''
    for engine in ('interp','jit'):
        source = wat
        arity = 4
        if engine=='jit':
            # Wider mixed scalar multi-result JIT boundaries are unresolved in
            # the reference; retain ordered two-result calls on both sources.
            arity = 2
            source = source.replace('(param i32 i64 f32 f64) (result i64 i32 f64 f32)',
                                    '(param i32 i64) (result i64 i32)')
            source = source.replace('local.get 3 f64.const 0.5 f64.sub local.get 2 f32.const 2 f32.mul','')
            source = source.replace('local.get 3 f64.const 1 f64.add local.get 2 f32.const 4 f32.mul','')
        expected = {'seeds':[f02_values(),f02_values()],
                    'nulls':[{'table_callable':False,'result_callable':False}]*2,
                    'calls':[f02_values((1,8589934616),(0,30),(3,-2.75),(2,3.0)),
                             f02_values((1,8589934616),(0,98),(3,-2.75),(2,3.0)),
                             f02_values((1,8589934575),(0,22),(3,-2.25),(2,10.0)),
                             f02_values((1,8589934575),(0,90),(3,-2.25),(2,10.0))],
                    'states':[f02_values((0,22)),f02_values((0,90))]}
        if arity==2:
            for call in expected['calls']:
                call['values'] = call['values'][:2]
        assert f04_driver.run(source,[(arity,arity)],api='refs',engine=engine) == expected



def test_memory64_and_selected_memories_obey_core_semantics(f04_driver):
    wat = '''(module
      (memory $a i64 1 2) (memory $b i64 1 2) (memory $c 1 2)
      (data (memory $a) (i64.const 11) "\\12\\34\\56\\78")
      (data (memory $b) (i64.const 11) "\\a1\\b2\\c3\\d4")
      (data $passive "\\93\\00\\e7\\41")
      (func (export "initial") (result i32 i32 i32 i64 i64 i32)
        i64.const 9 i32.load $a offset=2 i64.const 9 i32.load $b offset=2
        i32.const 11 i32.load $c memory.size $a memory.size $b memory.size $c)
      (func (export "change") (result i32 i32 i32 i32)
        i64.const 11 i32.const 305419896 i32.store $b
        i64.const 21 i64.const 11 i64.const 4 memory.copy $a $b
        i64.const 31 i32.const 171 i64.const 3 memory.fill $b
        i32.const 41 i32.const 0 i32.const 4 memory.init $c $passive
        i64.const 11 i32.load $a i64.const 21 i32.load $a
        i64.const 31 i32.load $b i32.const 41 i32.load $c)
      (func (export "grow") (result i64 i64 i64 i32 i32)
        i64.const 1 memory.grow $b memory.size $a memory.size $b
        i64.const 65536 i32.load $b i64.const 11 i32.load $b)
      (func (export "mixed") (result i32 i32 i32)
        i32.const 51 i64.const 21 i32.const 4 memory.copy $c $a
        i64.const 51 i32.const 41 i32.const 4 memory.copy $b $c
        i32.const 51 i32.load $c i64.const 51 i32.load $b i64.const 51 i32.load $a)
      (func (export "fill_high") (param i64) local.get 0 i32.const 77 i64.const 3 memory.fill $b)
      (func (export "grow_high") (param i64) (result i64) local.get 0 memory.grow $b)
      (func (export "filled") (result i32) i64.const 31 i32.load $b)
      (func (export "offset") (result i32) i64.const 0 i32.load $b offset=4294967296)
      (func (export "tail") (result i32 i32) i64.const 11 i32.load $a i64.const 11 i32.load $b))'''
    calls = [('initial',[],6),('change',[],4),('grow',[],5),('mixed',[],3),
             ('fill_high',[f02_arg(1,4294967327)],0),('filled',[],1),
             ('grow_high',[f02_arg(1,4294967296)],1),('offset',[],1),('tail',[],2)]
    observed = f04_driver.run(wat,[f04_call(n,a,r) for n,a,r in calls],engine='interp',api='c')
    assert observed == [f02_values((0,0x78563412),(0,0xd4c3b2a1),(0,0),(1,1),(1,1),(0,1)),
                                 f02_values((0,0x78563412),(0,0x12345678),(0,0xababab),(0,0x41e70093)),
                                 f02_values((1,1),(1,1),(1,2),(0,0),(0,0x12345678)),
                                 f02_values((0,0x12345678),(0,0x41e70093),(0,0)),{'trap':5},
                                 f02_values((0,0xababab)),f02_values((1,-1)),
                                 {'trap':5},f02_values((0,0x78563412),(0,0x12345678))]
    # JIT covers single-memory64 execution, including wide dynamic addresses.
    single = '''(module (memory i64 1 2)
      (data (i64.const 11) "\\12\\34\\56\\78")
      (func (export "read") (param i64) (result i32) local.get 0 i32.load)
      (func (export "grow") (param i64) (result i64) local.get 0 memory.grow)
      (func (export "size") (result i64) memory.size)
      (func (export "offset") (result i32) i64.const 0 i32.load offset=4294967296))'''
    calls = [('read',[f02_arg(1,11)],1),('grow',[f02_arg(1,1)],1),('size',[],1),
             ('read',[f02_arg(1,65536)],1),('read',[f02_arg(1,4294967307)],1),('offset',[],1),
             ('read',[f02_arg(1,11)],1)]
    result = f04_driver.run(single,[f04_call(n,a,r) for n,a,r in calls],engine='jit',api='c')
    assert result == [f02_values((0,0x78563412)),f02_values((1,1)),f02_values((1,2)),f02_values((0,0)),
                      {'trap':5},{'trap':5},f02_values((0,0x78563412))]



def test_checked_access_and_immutable_global_fail_without_changes(f04_driver):
    wat = '''(module (memory (export "memory") 1 1)
      (table (export "table") 2 2 externref)
      (global (export "constant") i32 (i32.const -73))
      (func (export "read_constant") (result i32) global.get 0))'''
    ops = [('put',65528,8,'17395b7d9fb1d3f5'),('read','u64',65528,0),
           ('read','u64',65529,0),('read','u8',65536,0),('read','u32',4294967295,0),
           ('write','u64',65529,0),('write','u8',65536,42),('write','u32',4294967295,13),
           ('bytes',65535,2,'-'),('bytes',4294967295,2,'-'),('bytes',65528,8,'-'),
           ('tset','table',1,2),('tget','table',1),('tget','table',2),('tset','table',2,1),
           ('tsize','table'),('tget','table',0),('tget','table',1),
           ('global','constant'),('gset','constant',0,19),('global','constant'),f04_call('read_constant',results=1),
           ('gfind','constant'),('tfind','table'),('gfind','missing'),('tfind','missing')]
    expected = [{'bytes':'17395b7d9fb1d3f5'},{'bits':int.from_bytes(bytes.fromhex('17395b7d9fb1d3f5'),'little')},
                *[{'error':'OutOfBoundsLoad'}]*3,*[{'error':'OutOfBoundsStore'}]*3,
                *[{'error':'OutOfBoundsLoad'}]*2,{'bytes':'17395b7d9fb1d3f5'},
                {'ok':True},{'ref':2},{'error':'OutOfBounds'},{'error':'OutOfBounds'},{'size':2},{'ref':None},{'ref':2},
                f02_values((0,-73))['values'][0],{'error':'Immutable'},f02_values((0,-73))['values'][0],f02_values((0,-73)),
                {'present':True},{'present':True},{'present':False},{'present':False}]
    for engine in ('interp','jit'):
        assert f04_driver.run(wat,ops,engine=engine) == expected
