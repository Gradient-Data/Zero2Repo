# feature: F17
"""Observe async Canonical ABI work through guest output and public failures."""
import struct
from F01_helpers import f01_driver
from F17_helpers import F17Guest, F17FsGuest, f17_driver, f17_pair, f17_completed_copy
from F16_helpers import f16_success, f16_load
from F17_helpers import f17_graph_driver, f17_transfer_graph, f17_integer_result_graph
from F14_helpers import f14_call, f14_values


def test_waitable_completion_and_peer_closure(f17_driver,f17_graph_driver):
    # F17.T03 (FP-17.04). Dependent output exists only after the callback receives the event.
    for read_first in (True,False):
        graph=f17_transfer_graph('stream','u16',bytes.fromhex('31e701a3'),2,2,read_first=read_first)
        got=f17_graph_driver.observe(graph,[f14_call('observe',-1),f14_call('observe-writer',-1),
                                           *[f14_call('observe',i) for i in range(4)]])
        assert got['run_error'] is None and f14_values(got)==[1,1,49,231,1,163],got
    for operation in ('closed-read','closed-write'):
        g=F17Guest(); g.transfer('stream','u8'); f17_pair(g)
        src=g.alloc(b'\xd3'); dst=g.alloc(b'\xa5')
        g.body += ['(local.set $set (call $setnew))']
        read=operation.endswith('read')
        endpoint='r' if read else 'w'
        g.body.append(f'(call $join (local.get ${endpoint}) (local.get $set))')
        first='read' if read else 'write'
        firstptr=dst if read else src
        g.record(f'(call ${first} (local.get ${endpoint}) (i32.const {firstptr}) (i32.const 1))')
        g.body.append('(call $dropwritable (local.get $w))' if read else '(call $dropreadable (local.get $r))')
        g.ending='(i32.or (i32.shl (local.get $set) (i32.const 4)) (i32.const 2))'
        g.callback=f'''(i32.store (i32.const 256) (local.get $event))
(i32.store (i32.const 260) (local.get $payload))
(call $emit (i32.const 256) (i32.const 8))
(call $emit (i32.const {dst}) (i32.const 1)) (i32.const 0)'''
        raw=f16_success(f17_driver.observe(g.source()))
        blocked,event,payload=struct.unpack('<III',raw[:12])
        assert blocked==0xffffffff and event==(2 if read else 3)
        assert raw[12:]==b'\xa5'
    g=F17Guest(); g.transfer('future','u32'); f17_pair(g)
    p=g.alloc(struct.pack('<I',98231))
    g.body.append('(call $dropreadable (local.get $r))')
    g.record(f'(call $write (local.get $w) (i32.const {p}))')
    assert f16_success(f17_driver.observe(g.source()))==struct.pack('<I',1)



def test_missing_values_invalid_and_finished_endpoints(f17_driver):
    # F17.T10 (FP-17.12). A working command precedes every classified product failure.
    good=F17Guest(); p=good.alloc(b'baseline'); good.emit(p,8)
    good.builtin('complete','task.return (result u32)','i','')
    good.body.append('(call $complete (i32.const 0))')
    source=good.source().replace('(func $run async (canon lift','(func $run async (result u32) (canon lift')
    source=source.replace('(func $f async))','(func $f async (result u32)))')
    assert f16_success(f17_driver.observe(source))==b'baseline'
    observations={}
    for defect in ('future-unwritten','stream-handle','set-handle','finished-stream','missing-result'):
        g=F17Guest(); g.transfer('future' if defect=='future-unwritten' else 'stream','u8')
        f17_pair(g)
        if defect=='future-unwritten': g.body.append('(call $dropwritable (local.get $w))')
        elif defect=='stream-handle':
            issued = ['(local.get $r)', '(local.get $w)', '(global.get $output)',
                      '(global.get $output-reader)', '(global.get $output-future)']
            g.body.append('(local.set $i (i32.const 0)) (loop $unused')
            for handle in issued:
                g.body.append(f'(if (i32.eq (local.get $i) {handle}) (then '
                              '(local.set $i (i32.add (local.get $i) (i32.const 1))) (br $unused)))')
            g.body.append(') (drop (call $read (local.get $i) (i32.const 512) (i32.const 1)))')
        elif defect=='set-handle': g.body.append('(call $join (local.get $r) (i32.const 1234567))')
        elif defect=='finished-stream':
            g.body += ['(call $dropwritable (local.get $w))',
                       '(drop (call $read (local.get $r) (i32.const 512) (i32.const 1)))',
                       '(drop (call $read (local.get $r) (i32.const 512) (i32.const 1)))']
        source=g.source()
        if defect=='missing-result':
            source=source.replace('(func $run async (canon lift','(func $run async (result u32) (canon lift')
            source=source.replace('(func $f async))','(func $f async (result u32)))')
        got=f17_driver.observe(source); observations[defect]=got
        assert got['err'] is not None,observations
    assert {key:value['err'] for key,value in observations.items()}=={
        'future-unwritten':'Unreachable','stream-handle':'Unreachable','set-handle':'Unreachable',
        'finished-stream':'Unreachable','missing-result':'Unreachable'},observations




def test_scalar_future_and_stream_transfers(f17_graph_driver):
    # F17.T02 (FP-17.03). Standard scalar byte encodings; reader completion and full content.
    vectors=[('bool','B',[1,0,1]),('s8','b',[-101,27,-1]),('u8','B',[201,17,254]),
             ('s16','h',[-23451,1234,-5]),('u16','H',[60001,321,54321]),
             ('s32','i',[-2000000001,1234567,-9]),('u32','I',[4000000001,123456789,7]),
             ('s64','q',[-8000000000000000001,9007199254740993,-27]),
             ('u64','Q',[18000000000000000001,9007199254740993,77]),
             ('f32','f',[-3.25,0.125,1024.5]),('f64','d',[-9.125,1.0/1024,1048576.25]),
             ('char','I',[0x3bb,0x1f642,0x6c34])]
    for kind in ('future','stream'):
        for typ,fmt,values in vectors:
            if kind == 'stream' and typ == 'char':
                continue
            sequences=([[v] for v in values] if kind=='future' else
                       ([values] if typ=='char' else [values,values+list(reversed(values))+values[:1]]))
            for sequence in sequences:
                payload=struct.pack('<'+fmt*len(sequence),*sequence)
                source=f17_transfer_graph(kind,typ,payload,len(sequence),struct.calcsize('<'+fmt),read_first=kind=='stream')
                got=f17_graph_driver.observe(source,[f14_call('observe',i) for i in [-1,*range(len(payload))]])
                assert got['run_error'] is None,got
                assert f14_values(got)==[1,*payload],(kind,typ,got)


def test_deadlock_and_ungranted_cross_component_handles(f17_graph_driver):
    # F17.T11 (FP-17.13). A real supplier transfers bytes on the same graph before refusal.
    for fault in (None,'deadlock','ungranted','scalar-handle'):
        source=f17_transfer_graph('stream','u8',b'\xd3\x27\x81',3,1,fault=fault)
        got=f17_graph_driver.observe(source,[f14_call('observe',i) for i in (-1,0,1,2)])
        assert got['instantiated'] is True,got
        if fault in (None,'scalar-handle'):
            assert got['run_error'] is None and f14_values(got)==[1,211,39,129],got
        else:
            assert got['run_error']==('AsyncDeadlock' if fault=='deadlock' else 'Unreachable'),got


def test_unsupported_callback_and_cross_component_cancellation(f17_driver,f17_graph_driver):
    # F17.T12 (FP-17.14). Local cancellation remains available; graph cancellation is refused.
    g=F17Guest(); p=g.alloc(b'callback'); g.emit(p,8)
    assert f16_success(f17_driver.observe(g.source()))==b'callback'
    unsupported=g.source().replace(' (callback (func $m "callback"))','').replace('(func (export "run") (result i32)', '(func (export "run")')
    unsupported=unsupported.replace(' (call $flush-output))\n(func (export "callback")',
                                    ' (drop (call $flush-output)))\n(func (export "callback")')
    assert f17_driver.observe(unsupported)['err']=='NoAsyncCallback'
    local=F17Guest(); local.transfer('stream','u8'); f17_pair(local)
    local.record('(call $read (local.get $r) (i32.const 512) (i32.const 1))')
    local.record('(call $cancel (local.get $r))')
    assert f16_success(f17_driver.observe(local.source()))==struct.pack('<II',0xffffffff,2)
    for kind in ('stream','future'):
        baseline=f17_graph_driver.observe(f17_transfer_graph(kind,'u8',b'\x95',1,1,read_first=kind=='stream'),[f14_call('observe',0)])
        assert baseline['run_error'] is None and f14_values(baseline)==[149],baseline
        got=f17_graph_driver.observe(f17_transfer_graph(kind,'u8',b'\x95',1,1,fault='cancel'))
        assert (got['run_error'] if got['instantiated'] else got['err'])=='UnsupportedBoundaryType',got
        source=f17_transfer_graph(kind,'u8',b'\x95',1,1,read_first=False)
        prefix,writer=source.split('(component $A',1)
        prefix=prefix.replace('(then (return (call $step)))','(then (global.set $finished (i32.const 1)) (return (i32.const 0)))')
        writer=writer.replace('(core module $code',f'(core func $cancel-write (canon {kind}.cancel-write $data)) (core module $code',1)
        writer=writer.replace('(core module $code\n','(core module $code\n(import "deps" "cancel-write" (func $cancel-write (param i32) (result i32)))\n',1)
        writer=writer.replace('(core instance $deps ','(core instance $deps (export "cancel-write" (func $cancel-write)) ',1)
        writer=writer.replace('(if (i32.eq (local.get $code) (i32.const -1)) (then',
            '(if (i32.eq (local.get $code) (i32.const -1)) (then (drop (call $cancel-write (global.get $endpoint))) (global.set $finished (i32.const 1)) (return (i32.const 0))',1)
        got=f17_graph_driver.observe(prefix+'(component $A'+writer,[f14_call('observe-writer',-1)])
        assert (got['run_error'] if got['instantiated'] else got['err'])=='UnsupportedBoundaryType',got


def test_yielded_completion_and_cross_component_integer_results(f17_driver,f17_graph_driver):
    # F17.T01 (FP-17.01, FP-17.02). The received integer is read from the caller, after continuation.
    # Main-task completion is observed through the command result.
    for value,yields in ((0,1),(0x13579bdf,3),(0xfedcba98,2)):
        source=f17_integer_result_graph(value,yields)
        got=f17_graph_driver.observe(source,[f14_call('observe',0),f14_call('observe',1)])
        assert got['run_error'] is None,got
        received,finished=f14_values(got)
        assert received & 0xffffffff == value and finished == 1,got
    # The command entry observes a declared result supplied only after yielding.
    # It exposes success/failure, not the arbitrary integer of invokeAsync.
    for status in (0,1):
        g=F17Guest()
        g.builtin('complete','task.return (result (result))','i','')
        p=g.alloc(b'continued')
        g.ending='(i32.const 1)'
        g.callback=f'''(call $complete (i32.const {status}))
(call $emit (i32.const {p}) (i32.const 9)) (i32.const 0)'''
        source=g.source().replace('(func $run async (canon lift','(func $run async (result (result)) (canon lift')
        source=source.replace('(func $f async))','(func $f async (result (result))))')
        got=f17_driver.observe(source)
        assert got['err'] is None and got['exit_code'] in ((None,0) if status==0 else (1,)),got
        assert got['stdout']==b'continued',got


def test_local_pending_read_cancellation_and_stream_reuse(f17_driver,tmp_path):
    # F17.T04 (FP-17.05). A pending write reaches a real file on the SAME stream, after
    # cancellation. The host-transfer baseline has the same initial file state.
    # The unavailable guest-to-guest destination baseline remains in the ledger.
    for payload in (b'\xd3',b'\x27'):
        for cancel in (False,True):
            (tmp_path/'target').write_bytes(b'')
            g=F17FsGuest(); handle=g.open('target'); g.transfer('stream','u8')
            g.globals+='(global $reader (mut i32) (i32.const 0)) (global $writer (mut i32) (i32.const 0))'
            g.body+=['(local.set $h (call $new))',
                     '(global.set $reader (i32.wrap_i64 (local.get $h)))',
                     '(global.set $writer (i32.wrap_i64 (i64.shr_u (local.get $h) (i64.const 32))))']
            src=g.alloc(payload); dst=g.alloc(b'\xa5')
            if cancel:
                g.record(f'(call $read (global.get $reader) (i32.const {dst}) (i32.const 1))')
                g.record('(call $cancel (global.get $reader))')
            # A stale cancelled reader would consume this write or cause a trap.
            status=g.record(f'(call $write (global.get $writer) (i32.const {src}) (i32.const 1))')
            g.bind('writefile','fs','[method]descriptor.write-via-stream',
                   [('self','(borrow $desc)'),('data','(stream u8)'),('offset','u64')],
                   '(future (result (error $error)))','iiq','i')
            future=g.alloc(bytes(4))
            g.body.append(f'(i32.store (i32.const {future}) {g.call("writefile",handle,"(global.get $reader)",0)})')
            # Await the already-issued write using its actual returned status.
            # A single element allows any legal completion batching.
            completed=g.alloc(bytes(4))
            g.body.append(('copy',f16_load(status),'(global.get $writer)',completed,3))
            g.emit(completed,4)
            g.body.append('(call $dropwritable (global.get $writer))')
            g.types.append('(type $done (future (result (error $fs-error))))')
            g.builtin('completion','future.read $done (memory $lib "memory") (realloc $realloc)','ii','i')
            result=g.alloc(bytes(20))
            f17_completed_copy(g,'completion',f16_load(future),result)
            g.emit(result,1); g.emit(dst,1)
            raw=f16_success(f17_driver.observe(g.source(),directory=str(tmp_path)))
            prefix=b'\0'+(struct.pack('<II',0xffffffff,2) if cancel else b'')
            assert raw==prefix+struct.pack('<III',0xffffffff,16,0)+b'\0\xa5',(cancel,raw)
            assert (tmp_path/'target').read_bytes()==payload
