# feature: F17
"""Public WASI 0.3 consumer and standard Canonical ABI guest inputs."""
import json
import os
import pytest
from F01_helpers import F01_BUILD, f01_driver
from F16_helpers import F16Driver, F16Guest, F16_ZIG, f16_load, f16_success
from F14_helpers import f14_bytes
from _helpers import build_outputs

class F17Driver(F16Driver):
    consumer_name = "F17"
    program_source = F16_ZIG.replace("runWasiP2Main", "runWasiP3Main")
    def program(self):
        return self.compiler.plan.consumer(self.consumer_name, source=self.program_source)

@pytest.fixture(scope='session')
def f17_driver(f01_driver, tmp_path_factory):
    return F17Driver(f01_driver,tmp_path_factory.mktemp('f17-consumer'))

class F17Guest(F16Guest):
    def __init__(self):
        self.groups, self.calls, self.body, self.data = {}, {}, [], []
        self.next = 4096
        self.types = ['(type $bytes (stream u8))']
        self.builtins = {}
        self.callback = '(i32.const 0)'
        self.ending = '(i32.const 0)'
        self.globals = ''
        self.builtin('outnew','stream.new $bytes','','q')
        self.builtin('outwrite','stream.write $bytes (memory $lib "memory")','iii','i')
        self.builtin('outdrop','stream.drop-writable $bytes','i','')
        self.builtin('outputset','waitable-set.new','','i')
        self.builtin('outputjoin','waitable.join','ii','')
        for key in ('stdout','stderr'):
            self.add(key,'wasi:cli/'+key, '(type $ec0 (enum "io" "illegal-byte-sequence" "pipe")) (export "error-code" (type $ec (eq $ec0)))')
            self.bind(key,key,'write-via-stream',[('data','(stream u8)')], '(future (result (error $ec)))','i','i')

    def builtin(self,name,operation,params,returns):
        self.builtins[name] = (operation,params,returns)

    def transfer(self,kind,typ):
        self.types.append(f'(type $payload ({kind} {typ}))')
        self.builtin('new',kind+'.new $payload','','q')
        for op in ('read','write'):
            self.builtin(op,kind+f'.{op} $payload (memory $lib "memory")','iii' if kind=='stream' else 'ii','i')
        for op in ('readable','writable'):
            self.builtin('drop'+op,kind+'.drop-'+op+' $payload','i','')
        self.builtin('cancel',kind+'.cancel-read $payload','i','i')
        self.builtin('setnew','waitable-set.new','','i')
        self.builtin('join','waitable.join','ii','')

    def source(self):
        imports, lowers, coreimports, exports = [], [], [], []
        for key,(interface,types,funcs) in self.groups.items():
            imports.append(f'(import "{interface}@0.3.0" (instance ${key} {types} '+''.join(funcs)+'))')
            if key=='fs': imports.append('(alias export $fs "descriptor" (type $desc)) (alias export $fs "error-code" (type $fs-error)) (alias export $fs "directory-entry" (type $fs-entry))')
        allcalls = {}
        for name,(group,public,params,ret) in self.calls.items():
            lowers.append(f'(core func ${name} (canon lower (func ${group} "{public}") (memory $lib "memory") (realloc $realloc)))')
            allcalls[name] = (params,ret)
        for name,(op,params,ret) in self.builtins.items():
            lowers.append(f'(core func ${name} (canon {op}))')
            allcalls[name] = (params,ret)
        deferred_returns, finish_returns = [], []
        for name,(params,ret) in allcalls.items():
            sig = '(param '+' '.join('i64' if k=='q' else 'i32' for k in params)+')' if params else ''
            if ret: sig += '(result '+('i64' if ret=='q' else 'i32')+')'
            is_return = name in self.builtins and self.builtins[name][0].startswith('task.return')
            imported_name = name + '-real' if is_return else name
            coreimports.append(f'(import "deps" "{name}" (func ${imported_name} {sig}))')
            if is_return:
                # Finish observation I/O before the guest declares its task complete.
                value_types = ['i64' if k == 'q' else 'i32' for k in params]
                deferred_returns.append(f'(global ${name}-pending (mut i32) (i32.const 0))')
                for i, typ in enumerate(value_types):
                    deferred_returns.append(f'(global ${name}-{i} (mut {typ}) ({typ}.const 0))')
                saves = ''.join(f'(global.set ${name}-{i} (local.get {i}))' for i in range(len(params)))
                args = ''.join(f'(global.get ${name}-{i})' for i in range(len(params)))
                deferred_returns.append(f'(func ${name} {sig} '
                    f'(if (global.get ${name}-pending) (then unreachable))'
                    f'{saves}(global.set ${name}-pending (i32.const 1)))')
                finish_returns.append(f'(if (global.get ${name}-pending) (then '
                    f'(global.set ${name}-pending (i32.const 0))(call ${imported_name} {args})))')
            exports.append(f'(export "{name}" (func ${name}))')
        return '(component\n'+'\n'.join(imports+self.types)+'''
(core module $lib (memory (export "memory") 16)
 (global $bump (mut i32) (i32.const 65536))
 (func (export "cabi_realloc") (param i32 i32 i32 i32) (result i32) (local $p i32)
  global.get $bump i32.const 7 i32.add i32.const -8 i32.and local.tee $p
  local.get 3 i32.add global.set $bump local.get $p))
(core instance $lib (instantiate $lib))
(alias core export $lib "cabi_realloc" (core func $realloc))
'''+ '\n'.join(lowers)+ '\n(core module $main\n'+ '\n'.join(coreimports)+'''
(import "lib" "memory" (memory 16))
(import "lib" "cabi_realloc" (func $output_alloc (param i32 i32 i32 i32) (result i32)))
(global $output (mut i32) (i32.const 0))
(global $output-reader (mut i32) (i32.const 0))
(global $output-future (mut i32) (i32.const 0))
(global $queue-head (mut i32) (i32.const 0))
(global $queue-tail (mut i32) (i32.const 0))
(global $output-set (mut i32) (i32.const 0))
(global $output-pending (mut i32) (i32.const 0))
(global $guest-state (mut i32) (i32.const 0))
'''+ '\n'.join(deferred_returns)+'''
;; Snapshot observations before later guest code can overwrite their memory.
(func $emit (param $p i32) (param $n i32) (local $node i32)
 (if (i32.eqz (local.get $n)) (then return))
 (local.set $node (call $output_alloc (i32.const 0) (i32.const 0) (i32.const 4)
  (i32.add (local.get $n) (i32.const 12))))
 (i32.store (local.get $node) (i32.const 0))
 (i32.store offset=4 (local.get $node) (i32.add (local.get $node) (i32.const 12)))
 (i32.store offset=8 (local.get $node) (local.get $n))
 (memory.copy (i32.add (local.get $node) (i32.const 12)) (local.get $p) (local.get $n))
 (if (global.get $queue-tail) (then
   (i32.store (global.get $queue-tail) (local.get $node)))
  (else (global.set $queue-head (local.get $node))))
 (global.set $queue-tail (local.get $node)))
(func $output-progress (param $code i32) (local $n i32) (local $node i32)
 (if (i32.and (local.get $code) (i32.const 15)) (then unreachable))
 (local.set $n (i32.shr_u (local.get $code) (i32.const 4)))
 (local.set $node (global.get $queue-head))
 (if (i32.or (i32.eqz (local.get $n))
  (i32.gt_u (local.get $n) (i32.load offset=8 (local.get $node)))) (then unreachable))
 (i32.store offset=4 (local.get $node) (i32.add (i32.load offset=4 (local.get $node)) (local.get $n)))
 (i32.store offset=8 (local.get $node) (i32.sub (i32.load offset=8 (local.get $node)) (local.get $n)))
 (if (i32.eqz (i32.load offset=8 (local.get $node))) (then
  (global.set $queue-head (i32.load (local.get $node)))
  (if (i32.eqz (global.get $queue-head)) (then (global.set $queue-tail (i32.const 0)))))))
(func $flush-output (result i32) (local $code i32)
 (block $done (loop $next
  (br_if $done (i32.eqz (global.get $queue-head)))
  (local.set $code (call $outwrite (global.get $output)
    (i32.load offset=4 (global.get $queue-head)) (i32.load offset=8 (global.get $queue-head))))
  (if (i32.eq (local.get $code) (i32.const -1)) (then
   (global.set $output-pending (i32.const 1))
   (return (i32.or (i32.shl (global.get $output-set) (i32.const 4)) (i32.const 2)))))
  (call $output-progress (local.get $code)) (br $next)))
'''+ '\n'.join(finish_returns)+'''
 (global.get $guest-state))
(func (export "run") (result i32)
 (global.set $guest-state (call $guest-run))
 (global.set $output-set (call $outputset))
 (call $outputjoin (global.get $output) (global.get $output-set))
 (call $flush-output))
(func (export "callback") (param $event i32) (param $handle i32) (param $payload i32) (result i32)
 (if (global.get $output-pending) (then
  (if (i32.or (i32.ne (local.get $event) (i32.const 3))
    (i32.ne (local.get $handle) (global.get $output))) (then unreachable))
  (global.set $output-pending (i32.const 0)) (call $output-progress (local.get $payload)))
 (else (global.set $guest-state (call $guest-callback (local.get $event) (local.get $handle) (local.get $payload)))))
 (call $flush-output))
'''+self.globals+'\n'.join(self.data)+'''
(func $guest-callback (param $event i32) (param $handle i32) (param $payload i32) (result i32)
'''+self.callback+''')
(func $guest-run (result i32)
 (local $dir i32) (local $file i32) (local $other i32) (local $s i32) (local $i i32) (local $p i32)
 (local $h i64) (local $r i32) (local $w i32) (local $set i32)
 (local.set $h (call $outnew))
 (global.set $output (i32.wrap_i64 (i64.shr_u (local.get $h) (i64.const 32))))
 (global.set $output-reader (i32.wrap_i64 (local.get $h)))
 (global.set $output-future (call $stdout (global.get $output-reader)))
'''+ '\n'.join(self.body)+'\n'+self.ending+'''))
(core instance $deps '''+''.join(exports)+''')
(core instance $m (instantiate $main (with "deps" (instance $deps)) (with "lib" (instance $lib))))
(func $run async (canon lift (core func $m "run") async (callback (func $m "callback"))))
(component $shim (import "run" (func $f async)) (export "run" (func $f)))
(instance $runinst (instantiate $shim (with "run" (func $run))))
(export "wasi:cli/run@0.3.0" (instance $runinst)))'''

    def record(self,expression,kind='i32'):
        ptr=self.alloc(bytes(8 if kind=='i64' else 4))
        self.body.append(f'({kind}.store (i32.const {ptr}) {expression})')
        self.emit(ptr,8 if kind=='i64' else 4)
        return ptr


def f17_pair(g):
    g.body += ['(local.set $h (call $new))',
               '(local.set $r (i32.wrap_i64 (local.get $h)))',
               '(local.set $w (i32.wrap_i64 (i64.shr_u (local.get $h) (i64.const 32))))']

class F17FsGuest(F17Guest):
    """A continuation guest accepts eager or callback-completed filesystem calls."""
    def __init__(self):
        from F16_helpers import F16_FS_TYPES, F16_ERRORS
        super().__init__()
        errors='(variant '+''.join(f'(case "{x}")' for x in F16_ERRORS.split() if x!='would-block')+'(case "other" (option string)))'
        types=F16_FS_TYPES.replace('(enum '+ ' '.join('"'+x+'"' for x in F16_ERRORS.split())+')',errors)
        types=types.replace('(enum "unknown" "block-device" "character-device" "directory" "fifo" "symbolic-link" "regular-file" "socket")', '(variant (case "block-device") (case "character-device") (case "directory") (case "fifo") (case "symbolic-link") (case "regular-file") (case "socket") (case "other" (option string)))')
        types=types.replace('(field "seconds" u64)','(field "seconds" s64)')
        self.add('fs','wasi:filesystem/types',types)
        self.add('pre','wasi:filesystem/preopens','(alias outer 1 $desc (type $outer)) (export "descriptor" (type $d (eq $outer)))')
        self.bind('dirs','pre','get-directories',[],'(list (tuple (own $d) string))','i')
        ret=self.result('dirs',size=8)
        self.preopen_result=ret
        self.directory_handle=f'(i32.load {f16_load(ret)})'
        self.async_names=set()
        self.builtin('setnew','waitable-set.new','','i')
        self.builtin('join','waitable.join','ii','')
        self.globals='(global $pc (mut i32) (i32.const 0)) (global $set (mut i32) (i32.const 0))'

    def async_bind(self,name,public,params,result,core):
        self.bind(name,'fs','[method]descriptor.'+public,params,result,core,'i')
        self.groups['fs'][2][-1]=self.groups['fs'][2][-1].replace('(func ','(func async ')
        self.async_names.add(name)

    def async_result(self,name,*args,size=32):
        ptr=self.alloc(b'\xa5'*size)
        self.body.append(('await',self.call(name,*args,ptr)))
        return ptr

    def open(self,path,flags=0,rights=3):
        if 'open' not in self.calls:
            self.async_bind('open','open-at',[('self','(borrow $desc)'),('pf','$pf'),('path','string'),('of','$of'),('df','$df')], '(result (own $desc) (error $error))','ii')
        p=self.alloc(path.encode()); arg=self.alloc(bytes(24))
        self.body += [f'(i32.store (i32.const {arg}) {self.directory_handle})',
                      f'(i32.store (i32.const {arg+8}) (i32.const {p}))',
                      f'(i32.store (i32.const {arg+12}) (i32.const {len(path.encode())}))',
                      f'(i32.store8 (i32.const {arg+16}) (i32.const {flags}))',
                      f'(i32.store8 (i32.const {arg+17}) (i32.const {rights}))']
        ret=self.async_result('open',arg)
        self.emit(ret,1)
        return f16_load(ret+4)

    def source(self):
        statements=[]; phases=[]
        for instruction in self.body:
            if isinstance(instruction,tuple):
                phases.append((statements,instruction)); statements=[]
            else: statements.append(instruction)
        phases.append((statements,None))
        steps=[]
        for i,(body,call) in enumerate(phases):
            tail=''
            if call is not None:
                instruction=call; call=instruction[1]
                tail=f'''(local.set $status {call})
(global.set $pc (i32.const {i+1}))
(if (i32.ne (i32.and (local.get $status) (i32.const 15)) (i32.const 2)) (then
 (global.set $set (call $setnew))
 (call $join (i32.shr_u (local.get $status) (i32.const 4)) (global.get $set))
 (return (i32.or (i32.shl (global.get $set) (i32.const 4)) (i32.const 2)))))'''
            if call is not None and instruction[0]=='copy':
                _,call,endpoint,codeptr,event=instruction
                tail=f'''(local.set $status {call})
(i32.store (i32.const {codeptr}) (local.get $status))
(global.set $pc (i32.const {i+1}))
(if (i32.eq (local.get $status) (i32.const -1)) (then
 (global.set $set (call $setnew))
 (global.set $copy-result (i32.const {codeptr})) (global.set $copy-event (i32.const {event}))
 (call $join {endpoint} (global.get $set))
 (return (i32.or (i32.shl (global.get $set) (i32.const 4)) (i32.const 2)))))'''
            if call is not None and instruction[0]=='stream-all':
                _,name,endpoint,ptr,count,state,*element_width=instruction
                width=element_width[0] if element_width else 1
                event=3 if name=='outwrite' else 2
                tail=f'''(block $end-transfer (loop $transfer
(if (i32.eqz (i32.load (i32.const {state+8}))) (then
 (i32.store (i32.const {state+4}) (call ${name} {endpoint}
  (i32.add (i32.const {ptr}) (i32.mul (i32.load (i32.const {state})) (i32.const {width})))
  (i32.sub (i32.const {count}) (i32.load (i32.const {state})))))))
(local.set $status (i32.load (i32.const {state+4})))
(if (i32.eq (local.get $status) (i32.const -1)) (then
 (i32.store (i32.const {state+8}) (i32.const 1))
 (global.set $pc (i32.const {i})) (global.set $set (call $setnew))
 (global.set $copy-result (i32.const {state+4})) (global.set $copy-event (i32.const {event}))
 (call $join {endpoint} (global.get $set))
 (return (i32.or (i32.shl (global.get $set) (i32.const 4)) (i32.const 2)))))
(i32.store (i32.const {state+8}) (i32.const 0))
(if (i32.gt_u (i32.and (local.get $status) (i32.const 15)) (i32.const 1)) (then unreachable))
(local.set $s (i32.shr_u (local.get $status) (i32.const 4)))
(if (i32.gt_u (local.get $s) (i32.sub (i32.const {count}) (i32.load (i32.const {state})))) (then unreachable))
(i32.store (i32.const {state}) (i32.add (i32.load (i32.const {state})) (local.get $s)))
(br_if $end-transfer (i32.eq (i32.and (local.get $status) (i32.const 15)) (i32.const 1)))
(br_if $end-transfer (i32.eq (i32.load (i32.const {state})) (i32.const {count})))
(if (i32.eqz (local.get $s)) (then unreachable)) (br $transfer)))
(global.set $pc (i32.const {i+1}))'''
            prefix='\n'.join(body)
            if call is not None and instruction[0]=='stream-all':
                # A callback resumes the pending copy, not the operations that
                # originally obtained its stream or started its host request.
                prefix=f'(if (i32.eqz (i32.load (i32.const {state+8}))) (then {prefix}))'
            steps.append(f'(if (i32.le_u (global.get $pc) (i32.const {i})) (then '+prefix+tail+'))')
        oldbody,oldglobals=self.body,self.globals
        self.globals+='(global $copy-result (mut i32) (i32.const 0)) (global $copy-event (mut i32) (i32.const 0))\n(func $steps (result i32) (local $status i32) (local $h i64) (local $s i32) (local $i i32) (local $p i32)\n'+'\n'.join(steps)+' (i32.const 0))'
        self.body=[]; self.ending='(call $steps)'
        self.callback='''(if (global.get $copy-result) (then
 (if (i32.ne (local.get $event) (global.get $copy-event)) (then unreachable))
 (i32.store (global.get $copy-result) (local.get $payload))
 (global.set $copy-result (i32.const 0)) (return (call $steps))))
(if (i32.and (i32.eq (local.get $event) (i32.const 1))
 (i32.eq (local.get $payload) (i32.const 2))) (then (return (call $steps))))
(i32.or (i32.shl (global.get $set) (i32.const 4)) (i32.const 2))'''
        source=super().source()
        self.body,self.globals=oldbody,oldglobals
        for name in self.async_names:
            group,public,_,_=self.calls[name]
            source=source.replace(f'(canon lower (func ${group} "{public}")',f'(canon lower (func ${group} "{public}") async')
        return source

from F14_helpers import F14Driver, F14_ZIG

class F17GraphDriver(F14Driver):
    consumer_name = "F17_graph"
    program = F17Driver.program
    program_source = F14_ZIG.replace(
        ' const results = try a.alloc(Outcome, parsed.value.len);',
        ''' graph.driveAsyncMain("run") catch |err| {
  try emit(.{ .instantiated = true, .run_error = @errorName(err), .calls = .{} }); return;
 };
 const results = try a.alloc(Outcome, parsed.value.len);''').replace(
        '.instantiated = true, .calls = results', '.instantiated = true, .run_error = @as(?[]const u8, null), .calls = results')

@pytest.fixture(scope='session')
def f17_graph_driver(f01_driver,tmp_path_factory):
    return F17GraphDriver(f01_driver,tmp_path_factory.mktemp('f17-graph'))


def f17_transfer_graph(kind,typ,payload,count,width,*,fault=None,read_first=True):
    """Two callback guests, with a public byte getter on the actual reader.

    Both peers account for partial completions. No scheduler state or task ids
    are inspected. The getter also exposes whether the reader reached the end.
    """
    components=[]
    for reader in (True,False):
        child='B' if reader else 'A'; op='read' if reader else 'write'
        typedecl=f'(type $data ({kind} {typ}))'
        countarg=f'(i32.sub (i32.const {count}) (global.get $pos))' if kind=='stream' else ''
        progress='(i32.shr_u (local.get $code) (i32.const 4))' if kind=='stream' else '(i32.const 1)'
        callback_progress='(i32.shr_u (local.get 2) (i32.const 4))' if kind=='stream' else '(i32.const 1)'
        signature='(param i32 i32 i32)' if kind=='stream' else '(param i32 i32)'
        extra=''
        if not reader:
            extra=f'''(import "tick" (func $tick async (param "data" {'u32' if fault in ('ungranted','scalar-handle') else '$data'})))'''
        canons=f'''(core func $copy (canon {kind}.{op} $data (memory $mem "mem")))
(core func $setnew (canon waitable-set.new)) (core func $join (canon waitable.join))'''
        coreimports=''
        exports=''
        if not reader:
            canons+=f'''(core func $new (canon {kind}.new $data))
(core func $tick (canon lower (func $tick) async (memory $mem "mem")))'''
            coreimports='(import "deps" "new" (func $new (result i64))) (import "deps" "tick" (func $tick (param i32) (result i32)))'
            exports='(export "new" (func $new)) (export "tick" (func $tick))'
        init='(global.set $endpoint (local.get 0))' if reader else '''
(local.set $h (call $new))
(global.set $endpoint (i32.wrap_i64 (i64.shr_u (local.get $h) (i64.const 32))))
(drop (call $tick (i32.wrap_i64 (local.get $h))))'''
        if fault=='ungranted':
            if reader: init='(global.set $endpoint (i32.xor (local.get 0) (i32.const -1)))'
            else: init=init.replace('(call $tick (i32.wrap_i64 (local.get $h)))', '(call $tick (i32.xor (i32.wrap_i64 (local.get $h)) (i32.const -1)))')
        if not read_first and reader: init+='(return (i32.const 1))'
        if fault=='deadlock' and not reader: init+='(return (i32.const 0))'
        if fault=='cancel' and reader:
            canons+=f'(core func $cancel (canon {kind}.cancel-read $data))'
            coreimports+='(import "deps" "cancel" (func $cancel (param i32) (result i32)))'
            exports+='(export "cancel" (func $cancel))'
        cancel='(drop (call $cancel (global.get $endpoint)))' if fault=='cancel' and reader else ''
        data=b'\xa5'*len(payload) if reader else payload
        getter='''(func (export "observe") (param i32) (result i32)
 (if (result i32) (i32.eq (local.get 0) (i32.const -1))
 (then (global.get $finished)) (else (i32.load8_u (local.get 0)))))'''
        entry='tick' if reader else 'run'
        components.append(f'''(component ${child}
{typedecl} {extra}
(core module $Memory (memory (export "mem") 1)) (core instance $mem (instantiate $Memory))
{canons}
(core module $code
(import "mem" "mem" (memory 1))
(import "deps" "copy" (func $copy {signature} (result i32)))
(import "deps" "setnew" (func $setnew (result i32)))
(import "deps" "join" (func $join (param i32 i32))) {coreimports}
(data (i32.const 0) {f14_bytes(data)})
(global $endpoint (mut i32) (i32.const 0)) (global $set (mut i32) (i32.const 0))
(global $pos (mut i32) (i32.const 0)) (global $finished (mut i32) (i32.const 0))
(func $step (result i32) (local $code i32) (local $attempts i32)
 block $done loop $again
 (br_if $done (i32.ge_u (global.get $pos) (i32.const {count})))
 (local.set $attempts (i32.add (local.get $attempts) (i32.const 1)))
 (if (i32.gt_u (local.get $attempts) (i32.const 1024)) (then unreachable))
 (local.set $code (call $copy (global.get $endpoint)
   (i32.mul (global.get $pos) (i32.const {width})) {countarg}))
 (if (i32.eq (local.get $code) (i32.const -1)) (then
   {cancel}
   (call $join (global.get $endpoint) (global.get $set))
   (return (i32.or (i32.shl (global.get $set) (i32.const 4)) (i32.const 2)))))
 (if (i32.and (local.get $code) (i32.const 15)) (then unreachable))
 (global.set $pos (i32.add (global.get $pos) {progress})) br $again
 end end
 (global.set $finished (i32.const 1)) (i32.const 0))
(func (export "callback") (param i32 i32 i32) (result i32)
 { '(if (i32.eqz (local.get 0)) (then (return (call $step))))' if not read_first and reader else ''}
 (if (i32.ne (local.get 0) (i32.const {(4 if reader else 5) if kind=='future' else (2 if reader else 3)})) (then unreachable))
 (if (i32.and (local.get 2) (i32.const 15)) (then unreachable))
 (global.set $pos (i32.add (global.get $pos) {callback_progress})) (call $step))
(func (export "{entry}") {'(param i32)' if reader else ''} (result i32) (local $h i64)
 (global.set $set (call $setnew)) {init} (call $step)) {getter})
(core instance $deps (export "copy" (func $copy)) (export "setnew" (func $setnew)) (export "join" (func $join)) {exports})
(core instance $i (instantiate $code (with "deps" (instance $deps)) (with "mem" (instance $mem))))
(func (export "{entry}") async {('(param "data" u32)' if fault in ('ungranted','scalar-handle') else '(param "data" $data)') if reader else ''}
(canon lift (core func $i "{entry}") async (callback (func $i "callback"))))
(func (export "observe") (param "index" s32) (result u32) (canon lift (core func $i "observe")))
)''')
    return '(component '+''.join(components)+'''
(instance $b (instantiate $B)) (instance $a (instantiate $A (with "tick" (func $b "tick"))))
(export "run" (func $a "run")) (export "observe" (func $b "observe")) (export "observe-writer" (func $a "observe")))'''


def f17_completed_copy(g,name,endpoint,ptr,count=None):
    """Append a copy that records its result only after any pending completion."""
    codeptr=g.alloc(bytes(4))
    expr=f'(call ${name} {endpoint} (i32.const {ptr})'+(f' (i32.const {count})' if count is not None else '')+')'
    g.body.append(('copy',expr,endpoint,codeptr,4 if count is None else (3 if name=='outwrite' else 2)))
    g.emit(codeptr,4)
    return codeptr


def f17_integer_result_graph(value, yields):
    """A yielding caller consumes a no-argument async callee's integer result.

    The getter reads the caller's received value, never scheduler bookkeeping.
    The original public driver cannot return the main task's declared result.
    """
    return f'''(component
(component $Provider
 (core func $return (canon task.return (result u32)))
 (core module $code
  (import "deps" "return" (func $return (param i32)))
  (func (export "callback") (param i32 i32 i32) (result i32) (i32.const 0))
  (func (export "calculate") (result i32)
   (call $return (i32.const {value})) (i32.const 0)))
 (core instance $deps (export "return" (func $return)))
 (core instance $code (instantiate $code (with "deps" (instance $deps))))
 (func (export "calculate") async (result u32)
  (canon lift (core func $code "calculate") async (callback (func $code "callback")))))
(component $Consumer
 (import "calculate" (func $calculate async (result u32)))
 (core module $memory (memory (export "mem") 1))
 (core instance $memory (instantiate $memory))
 (core func $calculate (canon lower (func $calculate) async (memory $memory "mem")))
 (core func $return (canon task.return (result u32)))
 (core func $setnew (canon waitable-set.new))
 (core func $join (canon waitable.join))
 (core module $code
  (import "memory" "mem" (memory 1))
  (import "deps" "calculate" (func $calculate (param i32) (result i32)))
  (import "deps" "return" (func $return (param i32)))
  (import "deps" "setnew" (func $setnew (result i32)))
  (import "deps" "join" (func $join (param i32 i32)))
  (data (i32.const 64) "\\a5\\a5\\a5\\a5")
  (global $remaining (mut i32) (i32.const {yields}))
  (global $waiting (mut i32) (i32.const 0))
  (global $set (mut i32) (i32.const 0))
  (global $finished (mut i32) (i32.const 0))
  (func $finish (result i32)
   (call $return (i32.load (i32.const 64)))
   (global.set $finished (i32.const 1)) (i32.const 0))
  (func $step (result i32) (local $status i32)
   (if (global.get $remaining) (then
    (global.set $remaining (i32.sub (global.get $remaining) (i32.const 1)))
    (return (i32.const 1))))
   (local.set $status (call $calculate (i32.const 64)))
   (if (i32.eq (i32.and (local.get $status) (i32.const 15)) (i32.const 2))
    (then (return (call $finish))))
   (global.set $waiting (i32.const 1))
   (global.set $set (call $setnew))
   (call $join (i32.shr_u (local.get $status) (i32.const 4)) (global.get $set))
   (i32.or (i32.shl (global.get $set) (i32.const 4)) (i32.const 2)))
  (func (export "run") (result i32) (call $step))
  (func (export "callback") (param i32 i32 i32) (result i32)
   (if (global.get $waiting) (then
    (if (i32.and (i32.eq (local.get 0) (i32.const 1))
                (i32.eq (local.get 2) (i32.const 2)))
     (then (return (call $finish))))
    (return (i32.or (i32.shl (global.get $set) (i32.const 4)) (i32.const 2)))))
   (call $step))
  (func (export "observe") (param i32) (result i32)
   (if (result i32) (local.get 0)
    (then (global.get $finished)) (else (i32.load (i32.const 64))))))
 (core instance $deps (export "calculate" (func $calculate)) (export "return" (func $return))
  (export "setnew" (func $setnew)) (export "join" (func $join)))
 (core instance $code (instantiate $code (with "deps" (instance $deps)) (with "memory" (instance $memory))))
 (func (export "run") async (result u32)
  (canon lift (core func $code "run") async (callback (func $code "callback"))))
 (func (export "observe") (param "which" u32) (result u32)
  (canon lift (core func $code "observe"))))
(instance $provider (instantiate $Provider))
(instance $consumer (instantiate $Consumer (with "calculate" (func $provider "calculate"))))
(export "run" (func $consumer "run")) (export "observe" (func $consumer "observe")))'''


def consumer_sources():
    return {'F17': (F17Driver.program_source, '/* Public WASI 0.3 consumer. */\n', ('v3_0',)),
            'F17_graph': (F17GraphDriver.program_source, '/* Public async graph consumer. */\n', ('v3_0',))}
