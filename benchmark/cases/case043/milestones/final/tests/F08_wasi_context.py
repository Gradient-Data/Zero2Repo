# feature: F08
"""Acceptance observations for configured preview1 context and byte streams."""
import os
import struct

from F01_helpers import f01_driver
from F08_helpers import (
    f08_driver, f08_new, f08_call, f08_ok, f08_context,
    F08_GUEST, F08_IMPORTS, F08_WRITE_ALL,
)


def test_configured_arguments_and_environment(f08_driver):
    # F08.T01: pointer arrays and byte counts are independent preview1 ABI data.
    contexts = [
        (['worker','', 'two words','--literal','λ'], [('Mode','batch'),('EMPTY',''),('Equal','a=b')]),
        ([], []),
        (['second','last'], [('ONLY','fresh')]),
    ]
    for api in ('c','zig'):
        for args,envs in contexts:
            seen,_ = f08_driver.run(F08_GUEST,
                [f08_new(args,envs), f08_call('context',results=1)], api=api)
            actual_args,actual_env = f08_context(seen['calls'][0])
            assert actual_args == [x.encode() for x in args]
            assert sorted(actual_env) == sorted((k+'='+v).encode() for k,v in envs)

    # CLI forwards a basename as argv[0]; remaining arguments stay literal.
    guest = '(module' + F08_IMPORTS + F08_WRITE_ALL + '''
      (memory 1)
      (func $emit (param i32 i32 i32)
        i32.const 32 local.get 1 i32.store
        i32.const 36 local.get 2 i32.store
        local.get 0 i32.const 32 i32.const 1 i32.const 40 call $write_all
        if unreachable end)
      (func $vector (param $fd i32) (param $table i32) (param $count i32)
        (local $i i32) (local $ptr i32) (local $len i32)
        block $done loop $next
          local.get $i local.get $count i32.ge_u br_if $done
          local.get $table local.get $i i32.const 4 i32.mul i32.add i32.load local.set $ptr
          i32.const 0 local.set $len
          block $end loop $scan
            local.get $len i32.const 4096 i32.ge_u if unreachable end
            local.get $ptr local.get $len i32.add i32.load8_u i32.eqz br_if $end
            local.get $len i32.const 1 i32.add local.set $len br $scan
          end end
          local.get $fd local.get $ptr local.get $len i32.const 1 i32.add call $emit
          local.get $i i32.const 1 i32.add local.set $i br $next
        end end)
      (func (export "_start")
        i32.const 0 i32.const 4 call $as if unreachable end
        i32.const 64 i32.const 512 call $ag if unreachable end
        i32.const 8 i32.const 12 call $es if unreachable end
        i32.const 256 i32.const 2048 call $eg if unreachable end
        i32.const 1 i32.const 64 i32.const 0 i32.load call $vector
        i32.const 2 i32.const 256 i32.const 8 i32.load call $vector))'''
    args,envs = contexts[0]
    path,result = f08_driver.cli(guest,args=args,envs=envs)
    assert result.returncode == 0, result.stderr
    actual = result.stdout.split(b'\0')
    assert actual[0] in (path.name.encode(), str(path).encode())
    assert actual[1:] == [*(x.encode() for x in args), b'']
    assert result.stderr.endswith(b'\0')
    assert sorted(result.stderr[:-1].split(b'\0')) == sorted((k+'='+v).encode() for k,v in envs)


def test_standard_input_consumption_and_separate_outputs(f08_driver):
    # F08.T02: C inherited output, CLI pipes and the public Zig captured-run entry.
    # C byte-input and capture configuration are unavailable in the public
    # API; configured byte input and capture use the public native runner.
    gather = F08_GUEST[:-1] + '''
      (func (export "gather") (param i32) (result i32 i32)
        i32.const 32 i32.const 128 i32.store
        i32.const 36 i32.const 7 i32.store
        i32.const 40 i32.const 160 i32.store
        i32.const 44 i32.const 6 i32.store
        local.get 0 i32.const 32 i32.const 2 i32.const 48 call $write_all
        i32.const 48 i32.load))'''
    for engine in ('interp','jit'):
        seen, result = f08_driver.run(gather, [f08_new(),
            f08_call('gather', [1], 2), f08_call('gather', [2], 2)], engine=engine)
        for call in seen['calls']:
            f08_ok(call, [0, 13])
        assert result.stdout == result.stderr == b'out\0\xff-Aerr\n-B'
        seen,result = f08_driver.run(F08_GUEST,[f08_new(),
            f08_call('write',[1,128,7],2), f08_call('write',[2,160,6],2),
            f08_call('write',[1,130,3],2)],engine=engine)
        for call,n in zip(seen['calls'],[7,6,3]):
            f08_ok(call,[0,n])
        assert result.stdout == b'out\x00\xff-A'+b't\x00\xff'
        assert result.stderr == b'err\n-B'

    guest = '(module' + F08_IMPORTS + F08_WRITE_ALL + '''
      (memory 1)
      (data (i32.const 128) "EOF!")
      (func $emit (param $fd i32) (param $ptr i32) (param $len i32)
        i32.const 32 local.get $ptr i32.store
        i32.const 36 local.get $len i32.store
        local.get $fd i32.const 32 i32.const 1 i32.const 44 call $write_all
        if unreachable end
        i32.const 44 i32.load local.get $len i32.ne if unreachable end)
      (func (export "_start") (local $n i32) (local $i i32) (local $steps i32)
        block $done loop $next
          local.get $steps i32.const 2048 i32.ge_u if unreachable end
          local.get $steps i32.const 1 i32.add local.set $steps
          i32.const 0 i32.const 512 i32.store
          i32.const 4 i32.const 5 i32.store
          i32.const 8 i32.const 517 i32.store
          i32.const 12 i32.const 8 i32.store
          i32.const 0 i32.const 0 i32.const 2 i32.const 40 call $read
          if unreachable end
          i32.const 40 i32.load local.tee $n i32.eqz br_if $done
          i32.const 2 i32.const 512 local.get $n call $emit
          i32.const 0 local.set $i
          block $transformed loop $transform
            local.get $i local.get $n i32.ge_u br_if $transformed
            i32.const 512 local.get $i i32.add
            i32.const 512 local.get $i i32.add i32.load8_u i32.const 90 i32.xor
            i32.store8
            local.get $i i32.const 1 i32.add local.set $i br $transform
          end end
          i32.const 1 i32.const 512 local.get $n call $emit
          br $next
        end end
        ;; A second read after EOF must still succeed with zero bytes.
        i32.const 40 i32.const 999 i32.store
        i32.const 0 i32.const 0 i32.const 2 i32.const 40 call $read
        if unreachable end
        i32.const 40 i32.load if unreachable end
        i32.const 2 i32.const 128 i32.const 4 call $emit))'''
    payload = bytes(range(256))*3+b'last\x00tail'
    for engine in ('interp','jit'):
        _,result = f08_driver.cli(guest,stdin=payload,engine=engine)
        assert result.returncode == 0, result.stderr
        assert result.stdout == bytes(x ^ 90 for x in payload)
        assert result.stderr == payload+b'EOF!'
        captured = f08_driver.capture(guest,stdin=payload,engine=engine)
        assert 'error' not in captured, captured
        assert captured['status'] == 0, captured
        assert bytes.fromhex(captured['stdout']) == bytes(x ^ 90 for x in payload)
        assert bytes.fromhex(captured['stderr']) == payload+b'EOF!'


def test_exit_status_is_for_the_current_call(f08_driver):
    # F08.T03: success after exit and fault after exit both clear stale status.
    actions = [f08_new(), f08_call('normal',[9]), f08_call('exit',[0],0),
        f08_call('normal',[17]), f08_call('exit',[37],0), f08_call('fault',results=0),
        f08_call('exit',[0x89abcdef],0), f08_call('normal',[23])]
    for api in ('c','zig'):
        for engine in ('interp','jit'):
            seen,_ = f08_driver.run(F08_GUEST,actions,api=api,engine=engine)
            calls = seen['calls']
            for index,value in [(0,27),(2,51),(6,69)]:
                f08_ok(calls[index],[value])
            for index,code in [(1,0),(3,37),(5,0x89abcdef)]:
                assert calls[index]['exit'] == code
                assert bytes.fromhex(calls[index]['memory'])[96:100] == bytes(4)
                if api == 'c':
                    assert calls[index]['trapped'] is True
                    assert calls[index]['trap'] == 18  # public NAVOR_TRAP_WASI_EXIT
                else:
                    assert calls[index]['error'] == 'ProcExit'
            fault = calls[4]
            assert fault['exit'] is None
            if api == 'c':
                assert fault['trapped'] is True and fault['trap'] == 1
            else:
                assert fault['error'] == 'Unreachable'


def test_existing_instances_keep_their_wasi_configuration(f08_driver, tmp_path):
    # F08.T04 / FP-08.05: one C store, three live configuration generations.
    # Directory scratch/records occupy [1536, 2048), between args and envs.
    directory_imports = """
      (import "wasi_snapshot_preview1" "fd_prestat_get" (func $prestat (param i32 i32) (result i32)))
      (import "wasi_snapshot_preview1" "fd_prestat_dir_name" (func $dirname (param i32 i32 i32) (result i32)))
      (import "wasi_snapshot_preview1" "path_open" (func $open (param i32 i32 i32 i32 i32 i64 i64 i32 i32) (result i32)))
      (import "wasi_snapshot_preview1" "fd_close" (func $close (param i32) (result i32)))
    """
    guest = F08_GUEST.replace('(module', '(module' + directory_imports, 1)[:-1] + """
      (data (i32.const 1580) "identity")
      (func (export "directories") (result i32 i32)
        (local $fd i32) (local $count i32) (local $errno i32)
        (local $record i32) (local $total i32) (local $n i32)
        ;; Clear observations on every call, so previous reads cannot pass.
        i32.const 1600 i32.const 0 i32.const 384 memory.fill
        i32.const 3 local.set $fd
        block $done loop $next
          local.get $fd i32.const 1552 call $prestat local.tee $errno
          i32.const 8 i32.eq br_if $done
          local.get $errno if unreachable end
          local.get $count i32.const 3 i32.ge_u if unreachable end
          i32.const 1552 i32.load8_u if unreachable end
          i32.const 1556 i32.load i32.const 48 i32.gt_u if unreachable end
          i32.const 1600 local.get $count i32.const 128 i32.mul i32.add local.set $record
          local.get $record i32.const 1556 i32.load i32.store
          local.get $fd local.get $record i32.const 8 i32.add i32.const 1556 i32.load
          call $dirname if unreachable end
          ;; Open by the descriptor just discovered, never an assumed identity.
          local.get $fd i32.const 0 i32.const 1580 i32.const 8 i32.const 0
          i64.const 2 i64.const 0 i32.const 0 i32.const 1572 call $open
          if unreachable end
          i32.const 0 local.set $total
          block $eof loop $read_next
            local.get $total i32.const 64 i32.ge_u if unreachable end
            i32.const 1560 local.get $record i32.const 64 i32.add local.get $total i32.add i32.store
            i32.const 1564 i32.const 64 local.get $total i32.sub i32.store
            i32.const 1572 i32.load i32.const 1560 i32.const 1 i32.const 1568 call $read
            if unreachable end
            i32.const 1568 i32.load local.tee $n
            i32.const 64 local.get $total i32.sub i32.gt_u if unreachable end
            local.get $n i32.eqz br_if $eof
            local.get $total local.get $n i32.add local.set $total
            br $read_next
          end end
          local.get $record i32.const 4 i32.add local.get $total i32.store
          i32.const 1572 i32.load call $close if unreachable end
          local.get $count i32.const 1 i32.add local.set $count
          local.get $fd i32.const 1 i32.add local.set $fd br $next
        end end
        local.get $count local.get $errno))"""
    token = os.urandom(6).hex()
    names = [[f'/shared-{token}', f'/old-{token}'],
             [f'/new-{token}', f'/shared-{token}']]
    grants, expected_directories = [], []
    for generation in range(2):
        mappings, expected = [], {}
        for index, name in enumerate(names[generation]):
            host = tmp_path / f'directory-{generation}-{index}'
            host.mkdir()
            payload = bytes([generation, index]) + os.urandom(15 + generation * 13 + index * 7)
            (host / 'identity').write_bytes(payload)
            mappings.append((host, name))
            expected[name.encode()] = (host / 'identity').read_bytes()
        grants.append(mappings)
        expected_directories.append(expected)
    expected_directories.append({})
    old_args,old_env = ['old','', 'retained'], [('OWNER','old'),('EMPTY','')]
    new_args,new_env = ['newer','replacement'], [('OWNER','new'),('FRESH','yes')]
    contexts = [(old_args,old_env), (new_args,new_env), (['third'], [('third','retained')])]
    actions, checks = [], []

    def observe(name, args=(), results=1, *, slot=0, expected=None):
        actions.append(f08_call(name,args,results,slot=slot))
        checks.append((name,slot,expected))

    actions.append(f08_new(old_args,old_env,preopens=grants[0]))
    observe('context')
    observe('directories',results=2)
    observe('first_arg_write',[1,3],2,expected=[0,3])
    actions.append(f08_new(new_args,new_env,preopens=grants[1]))
    for slot in (1,0,1,0):
        observe('context',slot=slot)
        observe('directories',results=2,slot=slot)
    actions.append(f08_new(*contexts[2],preopens=[]))
    for slot in (2,1,0,2,0,1):
        observe('context',slot=slot)
        observe('directories',results=2,slot=slot)
    observe('first_arg_write',[2,5],2,slot=1,expected=[0,5])
    observe('first_arg_write',[1,3],2,expected=[0,3])
    observe('exit',[73],0,expected=73)
    observe('exit',[19],0,slot=1,expected=19)
    observe('exit',[41],0,expected=41)
    observe('normal',[11],slot=1,expected=[33])
    observe('context',slot=1)
    observe('context')
    for engine in ('interp','jit'):
        seen,result = f08_driver.run(guest,actions,engine=engine)
        assert len(seen['calls']) == len(checks)
        for call,(name,slot,expected) in zip(seen['calls'],checks):
            detail = (engine,name,slot,call)
            if name == 'context':
                args,env = contexts[slot]
                actual_args,actual_env = f08_context(call)
                assert actual_args == [a.encode() for a in args], detail
                assert sorted(actual_env) == sorted((k+'='+v).encode() for k,v in env), detail
            elif name == 'directories':
                expected = expected_directories[slot]
                f08_ok(call,[len(expected),8])  # BADF positively terminates enumeration.
                mem = bytes.fromhex(call['memory'])
                actual = {}
                for index in range(call['values'][0]):
                    record = 1600 + index * 128
                    size,used = struct.unpack_from('<II',mem,record)
                    assert size <= 48 and used < 64, detail
                    grant = mem[record+8:record+8+size]
                    assert grant not in actual, detail
                    actual[grant] = mem[record+64:record+64+used]
                assert actual.keys() == expected.keys(), detail
                for grant,payload in expected.items():
                    assert len(actual[grant]) == len(payload), (detail,grant)
                    assert actual[grant] == payload, (detail,grant)
            elif name == 'exit':
                assert call['trapped'] is True and call['trap'] == 18, detail
                assert call['exit'] == expected, detail
            else:
                f08_ok(call,expected)
        assert result.stdout == b'oldold'
        assert result.stderr == b'newer'


def test_explicit_wasi_import_takes_precedence_on_both_engines(f08_driver):
    # F08.T05: NULL bindings retain real WASI behavior, while a supplied
    # compatible function changes the value the guest computes and returns.
    guest = F08_GUEST[:-1] + '''
      (func (export "computed") (param i32) (result i32)
        local.get 0 i32.const 32 i32.const 1 i32.const 40 call $write_all
        i32.const 7 i32.mul i32.const 3 i32.add))'''
    for engine in ('interp','jit'):
        for override in (False,True):
            seen,result = f08_driver.run(guest,[f08_new(override=override),
                f08_call('prepare',[128,7],0), f08_call('computed',[1]),
                f08_call('computed',[2])],engine=engine)
            f08_ok(seen['calls'][0],[])
            f08_ok(seen['calls'][1],[87 if override else 3])
            f08_ok(seen['calls'][2],[164 if override else 3])
            assert seen['callbacks'] == ([[1,32,1,40],[2,32,1,40]] if override else [])
            assert result.stdout == (b'' if override else b'out\0\xff-A')
            assert result.stderr == (b'' if override else b'out\0\xff-A')


def test_preview1_io_failure_categories(f08_driver):
    # F08.T06: WASI preview1 errno discriminants: success=0, badf=8,
    # fault=21. Unsupported operations and permission/capability refusals are
    # accepted for a disallowed direction on an existing descriptor.
    actions = [f08_new(), f08_call('write',[1,128,7],2),
        f08_call('prepare',[65534,4],0),
        f08_call('raw_write',[1,32,1,40]), f08_call('raw_read',[0,32,1,40]),
        f08_call('raw_write',[1,65532,1,40]), f08_call('raw_read',[0,65532,1,40]),
        f08_call('prepare',[128,7],0),
        f08_call('raw_write',[99,32,1,40]), f08_call('raw_read',[99,32,1,40]),
        f08_call('raw_write',[0,32,1,40]), f08_call('raw_read',[1,32,1,40]),
        f08_call('raw_read',[2,32,1,40]),
        f08_call('write',[2,160,6],2)]
    expected = [[0,7],[],[21],[21],[21],[21],[],[8],[8],{2,58,63,76},{2,58,63,76},{2,58,63,76},[0,6]]
    for engine in ('interp','jit'):
        seen,result = f08_driver.run(F08_GUEST,actions,engine=engine)
        assert len(seen['calls']) == len(expected)
        for call,value in zip(seen['calls'],expected):
            if isinstance(value,set):
                assert len(call['values']) == 1 and call['values'][0] in value, call
                f08_ok(call,call['values'])
            else:
                f08_ok(call,value)
        assert result.stdout == b'out\0\xff-A'
        assert result.stderr == b'err\n-B'


def test_capture_allowance_refuses_further_output(f08_driver):
    # F08.T07: same guest and inputs, only the explicit allowance changes.
    # The guest transports fd_write's preview1 errno via proc_exit. It first
    # fills exactly the allowance, then attempts another write, avoiding any
    # assumption about partial retention of a write that crosses the boundary.
    guest = '(module' + F08_IMPORTS + F08_WRITE_ALL + '''
      (memory 1)
      (data (i32.const 128) "abcdefghZ")
      (func $emit (param $fd i32) (param $ptr i32) (param $len i32)
        (local $errno i32)
        i32.const 32 local.get $ptr i32.store
        i32.const 36 local.get $len i32.store
        local.get $fd i32.const 32 i32.const 1 i32.const 40 call $write_all
        local.tee $errno if local.get $errno call $exit end
        i32.const 40 i32.load local.get $len i32.ne if unreachable end)
      (func (export "_start")
        i32.const 1 i32.const 128 i32.const 4 call $emit
        i32.const 1 i32.const 132 i32.const 4 call $emit
        i32.const 1 i32.const 136 i32.const 1 call $emit))'''
    # Both destinations are promised byte streams; the allowance applies to
    # each independently. Change the destination in the guest, not the oracle.
    for fd in (1,2):
        source = guest.replace('i32.const 1 i32.const 128',f'i32.const {fd} i32.const 128')
        source = source.replace('i32.const 1 i32.const 132',f'i32.const {fd} i32.const 132')
        source = source.replace('i32.const 1 i32.const 136',f'i32.const {fd} i32.const 136')
        for engine,cap,code,payload in [('interp',32,0,b'abcdefghZ'),('interp',8,51,b'abcdefgh'),
                                        ('jit',32,0,b'abcdefghZ'),('jit',8,51,b'abcdefgh')]:
            seen = f08_driver.capture(source,allowance=cap,engine=engine)
            assert 'error' not in seen, seen
            assert seen['status'] == code, seen  # WASI ERRNO_NOSPC is 51.
            assert bytes.fromhex(seen['stdout']) == (payload if fd==1 else b'')
            assert bytes.fromhex(seen['stderr']) == (payload if fd==2 else b'')
        # A not-yet-full buffer must also reject a crossing write. Retaining
        # any fitting prefix of that failed write is deliberately unpinned.
        crossing = f08_driver.capture(source,allowance=6)
        assert 'error' not in crossing and crossing['status'] == 51, crossing
        payload = bytes.fromhex(crossing['stdout' if fd==1 else 'stderr'])
        assert 4 <= len(payload) <= 6 and b'abcdefgh'.startswith(payload)
        assert bytes.fromhex(crossing['stderr' if fd==1 else 'stdout']) == b''
