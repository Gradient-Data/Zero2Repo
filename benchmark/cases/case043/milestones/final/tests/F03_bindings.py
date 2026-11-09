# feature: F03
"""Import binding acceptance, one collected function per planned entry.

Core 3.0 external-type matching supplies the compatibility oracle:
https://webassembly.github.io/spec/core/valid/types.html#external-types
Scalar and state vectors below were also executed on the original runtime.
"""
from F03_helpers import f01_driver, f03_driver, f02_arg, f02_values


HOST = '''(module
  (import "env" "mix" (func $mix (param i32 i32 i64 f32 f64) (result f64)))
  (import "env" "wide" (func $wide (param i64 i64) (result i64)))
  (memory (export "memory") 1)
  (func (export "run") (param i32 i32 i64 f32 f64) (result f64 i64 i32)
    i32.const 9 local.get 0 i32.store8
    local.get 0 local.get 1 local.get 2 local.get 3 local.get 4 call $mix
    local.get 2 local.get 0 i64.extend_i32_s call $wide
    i32.const 9 i32.load8_u))'''

PROVIDER = r'''(module
  (global $sum (mut i32) (i32.const 11))
  (memory 1) (data (i32.const 0) "\03")
  (func (export "calc") (param i32 i32) (result i32)
    global.get $sum local.get 0 i32.add local.get 1 i32.sub global.set $sum
    global.get $sum i32.const 0 i32.load8_u i32.mul)
  (func (export "state") (result i32) global.get $sum))'''
CONSUMER = r'''(module
  (import "env" "calc" (func $calc (param i32 i32) (result i32)))
  (global (mut i32) (i32.const 900)) (memory 1) (data (i32.const 0) "\09")
  (func (export "run") (param i32 i32) (result i32)
    local.get 0 local.get 1 call $calc i32.const 2 i32.add))'''

ENTITIES = '''(module
  (type $unary (func (param i32) (result i32)))
  (import "env" "fn" (func $fn (type $unary)))
  (import "env" "memory" (memory 1 4))
  (import "env" "global" (global $g (mut i32)))
  (import "env" "table" (table 2 5 externref)) (export "table" (table 0))
  (func (export "read") (result i32 i32 i32 i32)
    i32.const 7 i32.load8_u global.get $g
    i32.const 0 table.get ref.is_null
    i32.const 6 call $fn)
  (func (export "write") (param i32 i32)
    i32.const 7 local.get 0 i32.store8 local.get 1 global.set $g
    i32.const 0 i32.const 1 table.get table.set))'''

STATE_EXPORTER = r'''(module
  (memory (export "memory") 1 3) (data (i32.const 7) "\0b")
  (global $g (export "global") (mut i32) (i32.const 7))
  (table (export "table") 2 4 externref)
  (func (export "read") (result i32 i32 i32)
    i32.const 7 i32.load8_u global.get $g i32.const 0 table.get ref.is_null)
  (func (export "write") (param i32 i32)
    i32.const 7 local.get 0 i32.store8 local.get 1 global.set $g
    i32.const 0 ref.null extern table.set))'''
STATE_IMPORTER = '''(module
  (import "env" "memory" (memory 1 4))
  (import "env" "global" (global $g (mut i32)))
  (import "env" "table" (table 2 5 externref))
  (func (export "read") (result i32 i32 i32)
    i32.const 7 i32.load8_u global.get $g i32.const 0 table.get ref.is_null)
  (func (export "write") (param i32 i32)
    i32.const 7 local.get 0 i32.store8 local.get 1 global.set $g
    i32.const 0 i32.const 1 ref.i31 extern.convert_any table.set))'''


def test_host_scalar_order_results_and_caller_memory(f03_driver):
    inputs = [(19,7,1099511627785,1.5,-6.25), (83,11,-1099511627771,-2.25,9.5)]
    full = [[f02_arg(k,v) for k,v in zip((0,0,1,2,3),row)] for row in inputs]
    integer_guest = '''(module
      (import "env" "pair" (func $pair (param i32 i32) (result i32)))
      (import "env" "wide" (func $wide (param i64 i64) (result i64)))
      (memory (export "memory") 1)
      (func (export "run") (param i32 i32) (result i32)
        i32.const 9 local.get 0 i32.store8 local.get 0 local.get 1 call $pair)
      (func (export "byte") (result i32) i32.const 9 i32.load8_u)
      (func (export "wide") (param i64 i64) (result i64) local.get 0 local.get 1 call $wide))'''
    for engine in ('interp','jit'):
        for api in ('c','zig'):
            for variant, fractions in [(0,(-4.75,7.25)),(1,(-7.75,11.75))]:
                # C JIT supports at most two arguments when floating-point
                # arguments are present. Native Zig callbacks use integer returns
                # within the published callback scope.
                guest = integer_guest if engine=='jit' else HOST if api=='c' else HOST.replace('result f64','result i32')
                calls = [('run',row,3) for row in full]
                if engine=='jit':
                    calls = []
                    for row,values in zip(full,inputs):
                        calls.extend([('run',row[:2],1),('byte',[],1),('wide',[row[2],f02_arg(1,values[0])],1)])
                got = f03_driver.run(guest,calls,engine=engine,api=api,variant=variant)
                assert got['created'] is True, got
                received = [row[:2] for row in full] if engine=='jit' else full
                assert got['received'] == [[{'kind':k,'bits':b} for k,b in row] for row in received], got
                returns = [(3,v) for v in fractions] if api=='c' and engine=='interp' else [(0,v) for v in ((50,238) if variant==0 else (2,-50))]
                expected = [f02_values(returns[0],(1,1099511627766),(0,26)), f02_values(returns[1],(1,-1099511627854),(0,94))]
                if engine=='jit':
                    expected = [f02_values(returns[0]),f02_values((0,26)),f02_values((1,1099511627766)),
                                f02_values(returns[1]),f02_values((0,94)),f02_values((1,-1099511627854))]
                assert got['calls'] == expected, got
        floating_guest = '''(module
          (import "env" "float" (func $f (param f32 f64) (result f64)))
          (import "env" "single" (func $s (param f32) (result f32)))
          (memory (export "memory") 1)
          (func (export "run") (param f32 f64) (result f64) local.get 0 local.get 1 call $f)
          (func (export "single") (param f32) (result f32) local.get 0 call $s))'''
        float_calls = []
        for row in full: float_calls.extend([('run',row[3:],1),('single',[row[3]],1)])
        got = f03_driver.run(floating_guest,float_calls,engine=engine)
        assert got['created'] is True, got
        assert got['received'] == [[{'kind':k,'bits':b} for k,b in row[3:]] for row in full], got
        assert got['calls'] == [f02_values((3,-7.75)),f02_values((2,-3)),f02_values((3,11.75)),f02_values((2,4.5))], got
    # A callback with two results exercises host-to-guest result order, which
    # separate single-result callbacks cannot establish. C JIT multi-result
    # host imports are outside the published callback scope.
    multiple = '''(module
      (import "env" "multi" (func $f (param i32 i32) (result i64 i32)))
      (memory (export "memory") 1)
      (func (export "run") (param i32 i32) (result i64 i32) local.get 0 local.get 1 call $f))'''
    args = [[f02_arg(0,a),f02_arg(0,b)] for a,b in [(8,3),(-4,9)]]
    for api in ('c','zig'):
        got = f03_driver.run(multiple,[('run',row,2) for row in args],api=api)
        assert got['created'] is True, got
        assert got['received'] == [[{'kind':k,'bits':v} for k,v in row] for row in args], got
        assert got['calls'] == [f02_values((1,68719476739),(0,5)),f02_values((1,-34359738359),(0,-13))], got

    direct_guest = '(module (import "env" "linear" (func (param i32) (result i32))))'
    direct = f03_driver.run(direct_guest, action='host-direct')
    assert direct['created'] is True and direct['trap'] == -1, direct
    assert direct['direct'] == f02_values((0,124))['values'][0], direct


def test_same_store_guest_function_composition(f03_driver):
    calls = [('run',[f02_arg(0,a),f02_arg(0,b)],1) for a,b in [(8,3),(-4,9),(12,-2)]]
    for engine in ('interp','jit'):
        got = f03_driver.run(CONSUMER,calls,provider=PROVIDER,action='compose',engine=engine)
        assert got['created'] is True and got['trap'] == -1, got
        assert got['calls'] == [f02_values((0,n)) for n in (50,11,53)], got
        assert got['provider'] == f02_values((0,17)), got


def test_imported_entities_share_state_without_aliasing_independent_entities(f03_driver):
    got = f03_driver.run(ENTITIES,action='entities')
    initial = f02_values((0,11),(0,7),(0,1),(0,19))
    host = f02_values((0,37),(0,-19),(0,0),(0,19))
    guest = f02_values((0,91),(0,53),(0,0),(0,19))
    assert got['initial'] == [initial]*3, got
    assert got['host_write'] == [host,host,initial], got
    assert got['write'] == f02_values(), got
    assert got['guest_write'] == [guest,guest,initial], got
    assert got['host_global'] == f02_values((0,53))['values'][0], got
    assert got['host_byte'] == 91, got
    assert got['host_table_same'] is True, got
    assert got['peer_table_same'] is True, got
    native = f03_driver.run(STATE_IMPORTER,
        [('read',[],3),('write',[f02_arg(0,91),f02_arg(0,53)],0)],
        provider=STATE_EXPORTER,action='state',api='zig')
    assert native['created'] is True, native
    assert native['calls'] == [f02_values((0,11),(0,7),(0,1)),f02_values()], native
    assert native['provider_before'] == f02_values((0,91),(0,53),(0,0)), native
    assert native['provider_write'] == f02_values(), native
    assert native['consumer_after'] == f02_values((0,46),(0,-17),(0,1)), native
    assert native['independent'] == f02_values((0,11),(0,7),(0,1)), native


def test_import_compatibility_and_missing_bindings(f03_driver):
    # Separate each type relation; no Cartesian product or engine-dependent
    # assumptions about unsupported state imports. Limits use Core subtyping.
    cases = [
        ('func exact','func (param i32 i64) (result f64)', '(func (export "x") (param i32 i64) (result f64) f64.const 2)',True),
        ('func parameter kind','func (param i64 i64) (result f64)', '(func (export "x") (param i32 i64) (result f64) f64.const 2)',False),
        ('func parameter count','func (param i32) (result f64)', '(func (export "x") (param i32 i64) (result f64) f64.const 2)',False),
        ('func result kind','func (param i32 i64) (result i64)', '(func (export "x") (param i32 i64) (result f64) f64.const 2)',False),
        ('func result count','func (param i32 i64)', '(func (export "x") (param i32 i64) (result f64) f64.const 2)',False),
        ('global mutable','global (mut i32)','(global (export "x") (mut i32) (i32.const 7))',True),
        ('global immutable','global i32','(global (export "x") i32 (i32.const 7))',True),
        ('global mutable to const','global i32','(global (export "x") (mut i32) (i32.const 7))',False),
        ('global const to mutable','global (mut i32)','(global (export "x") i32 (i32.const 7))',False),
        ('global value kind','global (mut i64)','(global (export "x") (mut i32) (i32.const 7))',False),
        ('global reference kind','global externref','(global (export "x") funcref (ref.null func))',False),
        ('global nullable reference','global (ref null i31)','(global (export "x") (ref null i31) (ref.null i31))',True),
        ('global non-null reference','global (ref i31)','(global (export "x") (ref i31) (ref.i31 (i32.const 5)))',True),
        ('global reference nullability','global (ref i31)','(global (export "x") (ref null i31) (ref.null i31))',False),
        ('memory narrower','memory 1 5','(memory (export "x") 2 3)',True),
        ('memory minimum','memory 2 5','(memory (export "x") 1 3)',False),
        ('memory maximum','memory 1 3','(memory (export "x") 2 5)',False),
        ('memory no declared maximum','memory 1','(memory (export "x") 2 3)',True),
        ('memory both unbounded','memory 1','(memory (export "x") 2)',True),
        ('memory supplied unbounded','memory 1 5','(memory (export "x") 2)',False),
        ('table narrower','table 1 5 funcref','(table (export "x") 2 3 funcref)',True),
        ('table minimum','table 2 5 funcref','(table (export "x") 1 3 funcref)',False),
        ('table maximum','table 1 3 funcref','(table (export "x") 2 5 funcref)',False),
        ('table no declared maximum','table 1 funcref','(table (export "x") 2 3 funcref)',True),
        ('table both unbounded','table 1 funcref','(table (export "x") 2 funcref)',True),
        ('table supplied unbounded','table 1 5 funcref','(table (export "x") 2 funcref)',False),
        ('table reference kind','table 1 5 externref','(table (export "x") 2 3 funcref)',False),
        ('table reference nullability','table 1 5 funcref','(func $f) (table (export "x") 2 3 (ref func) (ref.func $f))',False),
        ('function extern kind','func','(memory (export "x") 1)',False),
        ('memory extern kind','memory 1','(global (export "x") i32 (i32.const 7))',False),
        ('global extern kind','global i32','(table (export "x") 1 funcref)',False),
        ('table extern kind','table 1 funcref','(func (export "x"))',False),
    ]
    for api in ('c','zig'):
        for label, requested, supplied, compatible in cases:
            guest = f'(module (import "env" "x" ({requested})) (func (export "run") (result i32) i32.const 23))'
            got = f03_driver.run(guest,[('run',[],1)],provider=f'(module {supplied})',action='bind',api=api)
            assert got['created'] is compatible, (api,label,got)
            if compatible:
                assert got['calls'] == [f02_values((0,23))], (api,label,got)
                if api=='c': assert got['trap'] == -1, got
            elif api=='c':
                assert got['trap'] in (-1, 0), (label,got)
            else:
                expected = ('ImportKindMismatch' if label.endswith('extern kind') else
                            'InstantiateFailed' if label.startswith(('memory','table')) else 'SignatureMismatch')
                assert got['error'] == expected, (label,got)
        missing = f03_driver.run('(module (import "env" "x" (func)))',provider='(module (func (export "x")))',action='missing',api=api)
        assert missing['created'] is False, missing
        if api=='c': assert missing['trap'] in (-1, 0), missing
        else: assert missing['error'] == 'UnknownImport', missing
    # Host-created function types take a distinct public binding route from
    # exported guest functions; do not infer their validation from that route.
    for declaration,ok in [('(param i32) (result i32)',True),
                           ('(param i64) (result i32)',False),
                           ('(param i32 i32) (result i32)',False),
                           ('(param i32) (result i64)',False)]:
        guest = f'(module (import "env" "x" (func {declaration})) (func (export "run") (result i32) i32.const 23))'
        for engine in ('interp','jit'):
            got = f03_driver.run(guest,[('run',[],1)],action='host-bind',engine=engine)
            assert got['created'] is ok and got['trap'] in ((-1,) if ok else (-1, 0)), (declaration,got)
            if ok: assert got['calls']==[f02_values((0,23))],got
    for declaration,ok in [('(mut i32)',True),('(mut i64)',False),('i32',False)]:
        guest = f'(module (import "env" "x" (global {declaration})))'
        got = f03_driver.run(guest, action='host-bind')
        assert got['created'] is ok and got['trap'] in ((-1,) if ok else (-1, 0)), (declaration,got)
    for parameters,ok in [('i32 i32',True),('i32 i64',False),('i32',False)]:
        guest = f'(module (import "env" "pair" (func (param {parameters}) (result i32))) (func (export "run") (result i32) i32.const 23))'
        got = f03_driver.run(guest,[('run',[],1)],action='host',api='zig')
        assert got['created'] is ok, (parameters,got)
        if ok: assert got['calls']==[f02_values((0,23))],got
        else: assert got['error']=='SignatureMismatch',got


def test_c_bindings_survive_original_handle_release(f03_driver):
    got = f03_driver.run(ENTITIES,action='entities-release')
    initial = f02_values((0,11),(0,7),(0,1),(0,19))
    host = f02_values((0,37),(0,-19),(0,0),(0,19))
    guest = f02_values((0,91),(0,53),(0,0),(0,19))
    assert got['initial'] == [initial]*3, got
    assert got['host_write'] == [host,host,initial], got
    assert got['write'] == f02_values(), got
    assert got['guest_write'] == [guest,guest,initial], got
    assert got['peer_table_same'] is True, got
    calls = [('run',[f02_arg(0,a),f02_arg(0,b)],1) for a,b in [(8,3),(-4,9),(12,-2)]]
    for engine in ('interp','jit'):
        released = f03_driver.run(CONSUMER,calls,provider=PROVIDER,action='release',engine=engine)
        assert released['created'] is True and released['trap'] == -1, released
        assert released['calls'] == [f02_values((0,n)) for n in (50,11,53)], released
    host_function = '''(module (import "env" "x" (func $f (param i32) (result i32)))
      (func (export "run") (param i32) (result i32) local.get 0 call $f))'''
    for engine in ('interp','jit'):
        cleanup = f03_driver.run(host_function,action='lifetime',engine=engine)
        assert cleanup == {'lifetime':[{'result':66,'before':0,'after':1,'wrong_env':0}]*2},cleanup
        after = f03_driver.run(host_function,[('run',[f02_arg(0,n)],1) for n in (4,-7)],action='host-release',engine=engine)
        assert after['created'] is True and after['trap'] == -1, after
        assert after['calls'] == [f02_values((0,13)),f02_values((0,-20))], after


def test_store_ownership_refusal_and_obtained_module_control(f03_driver):
    entities = [
        ('func (result i32)','(func (export "x") (result i32) i32.const 17)','call 0'),
        ('memory 1','(memory (export "x") 1) (data (i32.const 0) "\\11")','i32.const 0 i32.load8_u'),
        ('global i32','(global (export "x") i32 (i32.const 17))','global.get 0'),
        ('table 2 externref','(table (export "x") 2 externref)','table.size'),
    ]
    for index,(declaration,definition,body) in enumerate(entities):
        guest = f'(module (import "env" "x" ({declaration})) (func (export "run") (result i32) {body}))'
        for action in ('bind','cross'):
            got = f03_driver.run(guest,[('run',[],1)],provider=f'(module {definition})',action=action)
            if action=='bind':
                assert got['created'] is True and got['trap'] == -1, got
                assert got['calls'] == [f02_values((0,2 if index==3 else 17))], got
            else:
                assert got['created'] is False and got['trap'] in (-1, 0), got
    host_entities = [
        ('func (param i32) (result i32)','i32.const 4 call 0',13),
        ('memory 1','i32.const 7 i32.load8_u',11),
        ('global (mut i32)','global.get 0',7),
        ('table 2 externref','table.size',2),
    ]
    for declaration,body,expected in host_entities:
        guest = f'(module (import "env" "x" ({declaration})) (func (export "run") (result i32) {body}))'
        for engine in (('interp','jit') if declaration.startswith('func') else ('interp',)):
            for action in ('host-bind','host-cross'):
                got = f03_driver.run(guest,[('run',[],1)],action=action,engine=engine)
                if action=='host-bind':
                    assert got['created'] is True and got['trap'] == -1, got
                    assert got['calls'] == [f02_values((0,expected))], got
                else:
                    assert got['created'] is False and got['trap'] in (-1, 0), got
    for engine in ('interp','jit'):
        provider = '(module (func (export "run") (param i32) (result i32) local.get 0 i32.const 9 i32.sub))'
        calls = [('run',[f02_arg(0,n)],1) for n in (31,-8)]
        refused = f03_driver.run('(module)',calls,provider=provider,action='module-cross',engine=engine)
        assert refused['created'] is False and refused['trap'] in (-1, 0), refused
        obtained = f03_driver.run('(module)',calls,provider=provider,action='share',engine=engine)
        assert obtained['created'] is True and obtained['trap'] == -1, obtained
        assert obtained['calls'] == [f02_values((0,22)),f02_values((0,-17))], obtained


F03_NOT_HOST_FAILURE = (-1, 2, 3, 4, 5)


def test_host_failure_origin_and_no_following_guest_effect(f03_driver):
    direct=f03_driver.run('(module)',action='direct-errors')
    assert direct['baseline']==25 and direct['refusals']==[0]*4, direct
    # A host-callback failure is a trap distinguishable from the guest arithmetic (2-4) and memory (5) categories.
    assert direct['failure'] not in F03_NOT_HOST_FAILURE and bytes(direct['message'])==b'host request abort\0',direct
    guest = '''(module (import "env" "fail" (func $fail))
      (memory (export "memory") 1)
      (global $g (mut i32) (i32.const 0))
      (func (export "host") i32.const 11 global.set $g call $fail i32.const 99 global.set $g)
      (func (export "arithmetic") i32.const 17 global.set $g i32.const 1 i32.const 0 i32.div_s drop i32.const 99 global.set $g)
      (func (export "memory_fault") i32.const 23 global.set $g i32.const 65536 i32.load drop i32.const 99 global.set $g)
      (func (export "state") (result i32) global.get $g))'''
    for engine in ('interp','jit'):
        for api in ('c','zig'):
            baseline = f03_driver.run(guest,[('host',[],0),('state',[],1)],engine=engine,api=api,variant=0)
            assert baseline['created'] is True, baseline
            assert baseline['calls'] == [f02_values(),f02_values((0,99))], baseline
            got = f03_driver.run(guest,[('host',[],0),('state',[],1),('arithmetic',[],0),('state',[],1),('memory_fault',[],0),('state',[],1)],
                                  engine=engine,api=api,variant=1)
            assert got['created'] is True, got
            if api=='c':
                host = got['calls'][0]
                assert set(host)=={'trap'} and host['trap'] not in F03_NOT_HOST_FAILURE, got
                errors = [host,{'trap':2},{'trap':5}]
            else:
                errors = [{'error':n} for n in ('HostTrap','DivByZero','OutOfBoundsLoad')]
            assert got['calls'] == [errors[0],f02_values((0,11)),errors[1],f02_values((0,17)),errors[2],f02_values((0,23))], got
