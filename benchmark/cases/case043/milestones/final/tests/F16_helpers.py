# feature: F16
"""WASI 0.2 command consumers and independently validated component guests."""
import json
import os
import struct
from pathlib import Path
import pytest
from F01_helpers import F01_BUILD, f01_driver
from F13_helpers import F13Driver
from _helpers import build_outputs, run_json_adapter, trace_execution

F16_ZIG = r'''
const std = @import("std");
const zw = @import("navor");
const a = std.heap.c_allocator;
extern fn printf([*:0]const u8, ...) c_int;
const Request = struct {
 args: ?[]const []const u8 = null, keys: []const []const u8 = &.{},
 values: []const []const u8 = &.{}, stdin: []const u8 = "",
 directory: ?[]const u8 = null,
};
pub export fn main(argc: c_int, argv: [*][*:0]u8) c_int {
 if (argc != 3) return 64;
 run(std.mem.span(argv[1]), std.mem.span(argv[2])) catch |err| {
  std.debug.print("Consumer failed: {s}\n", .{@errorName(err)}); return 70;
 }; return 0;
}
fn run(path: []const u8, reqpath: []const u8) !void {
 var threaded = std.Io.Threaded.init(a, .{}); defer threaded.deinit();
 const io = threaded.io();
 const bytes = try std.Io.Dir.cwd().readFileAlloc(io, path, a, .limited(1 << 24)); defer a.free(bytes);
 const req = try std.Io.Dir.cwd().readFileAlloc(io, reqpath, a, .limited(1 << 24)); defer a.free(req);
 const parsed = try std.json.parseFromSlice(Request, a, req, .{ .allocate = .alloc_always }); defer parsed.deinit();
 var engine = try zw.Engine.init(a, .{}); defer engine.deinit();
 var host = try zw.wasi.host.Host.init(a); defer host.deinit(); host.io = io;
 if (parsed.value.args) |args| try host.setArgs(args);
 try host.setEnvs(parsed.value.keys, parsed.value.values);
 host.stdin_bytes = parsed.value.stdin;
 if (parsed.value.directory) |p| { try host.addPendingPreopen(p, "/sandbox"); try host.materializePendingPreopens(); }
 var out: std.ArrayList(u8) = .empty; defer out.deinit(a);
 var errout: std.ArrayList(u8) = .empty; defer errout.deinit(a);
 host.stdout_buffer = &out; host.stderr_buffer = &errout;
 var failure: ?[]const u8 = null;
 zw.feature.component.host.runWasiP2Main(&engine, a, bytes, &host, .{}) catch |err| { failure = @errorName(err); };
 const encoded = try std.json.Stringify.valueAlloc(a, .{
  .err = failure, .exit_code = host.exit_code, .stdout = out.items, .stderr = errout.items,
 }, .{ .emit_strings_as_arrays = true }); defer a.free(encoded);
 _ = printf("%.*s", @as(c_int, @intCast(encoded.len)), encoded.ptr);
}
'''

class F16Driver(F13Driver):
    def program(self):
        return self.compiler.plan.consumer('F16')

    def guest(self, source):
        self.serial += 1
        path = self.directory / f'command-{self.serial}.wasm'
        path.with_suffix('.wat').write_text(source)
        path.write_bytes(self.binary(source))
        return path

    def observe(self, source, **config):
        path = self.guest(source)
        request = path.with_suffix('.json')
        request.write_text(json.dumps(config))
        result = run_json_adapter([self.program(), path, request], timeout=30)
        path.with_suffix('.observation.json').write_bytes(result.process.stdout)
        value = result.value
        # Zig's byte-array encoding applies to error names as well.
        if value['err'] is not None:
            value['err'] = bytes(value['err']).decode()
        value['stdout'] = bytes(value['stdout'])
        value['stderr'] = bytes(value['stderr'])
        return value

@pytest.fixture(scope='session')
def f16_driver(f01_driver, tmp_path_factory):
    return F16Driver(f01_driver, tmp_path_factory.mktemp('f16-consumer'))

# WIT types from wasi 0.2.0; canonical ABI layouts are standard, not host internals.
F16_ERRORS = 'access would-block already bad-descriptor busy deadlock quota exist file-too-large illegal-byte-sequence in-progress interrupted invalid io is-directory loop too-many-links message-size name-too-long no-device no-entry no-lock insufficient-memory insufficient-space not-directory not-empty not-recoverable unsupported no-tty no-such-device overflow not-permitted pipe read-only invalid-seek text-file-busy cross-device'
F16_FS_TYPES = '\n'.join([
    '(export "descriptor" (type $desc (sub resource)))',
    '(export "directory-entry-stream" (type $entries (sub resource)))',
] + [f'(type ${name}-def {body}) (export "{public}" (type ${name} (eq ${name}-def)))'
 for name, public, body in [
 ('pf','path-flags','(flags "symlink-follow")'),
 ('of','open-flags','(flags "create" "directory" "exclusive" "truncate")'),
 ('df','descriptor-flags','(flags "read" "write" "file-integrity-sync" "data-integrity-sync" "requested-write-sync" "mutate-directory")'),
 ('error','error-code','(enum '+' '.join('"'+x+'"' for x in F16_ERRORS.split())+')'),
 ('dt','descriptor-type','(enum "unknown" "block-device" "character-device" "directory" "fifo" "symbolic-link" "regular-file" "socket")'),
 ('time','datetime','(record (field "seconds" u64) (field "nanoseconds" u32))'),
 ('newtime','new-timestamp','(variant (case "no-change") (case "now") (case "timestamp" $time))'),
 ('stat','descriptor-stat','''(record (field "type" $dt) (field "link-count" u64) (field "size" u64)
 (field "data-access-timestamp" (option $time)) (field "data-modification-timestamp" (option $time))
 (field "status-change-timestamp" (option $time)))'''),
 ('hash','metadata-hash-value','(record (field "lower" u64) (field "upper" u64))'),
 ('entry','directory-entry','(record (field "type" $dt) (field "name" string))'),
]])

class F16Guest:
    """Build a command which transports actual canonical results through stdout."""
    def __init__(self):
        self.groups = {}
        self.calls = {}
        self.body = []
        self.data = []
        self.next = 4096
        self.add('ioerror','wasi:io/error','(export "error" (type $error (sub resource)))')
        self.add('streams', 'wasi:io/streams', '''
(export "output-stream" (type $os (sub resource)))
(export "input-stream" (type $ins (sub resource)))
(alias outer 1 $ioerror (type $outer-error))
(export "error" (type $error (eq $outer-error)))
(type $se0 (variant (case "last-operation-failed" (own $error)) (case "closed")))
(export "stream-error" (type $se (eq $se0)))''')
        self.bind('writeout', 'streams', '[method]output-stream.blocking-write-and-flush',
                  [('self','(borrow $os)'),('contents','(list u8)')], '(result (error $se))', 'iiii')
        for name in ('stdout', 'stderr', 'stdin'):
            resource, typ = ('input-stream', '$ins') if name == 'stdin' else ('output-stream', '$os')
            self.add(name, 'wasi:cli/'+name, f'''(alias outer 1 {typ} (type $outer))
(export "{resource}" (type $stream (eq $outer)))''')
            self.bind('get'+name, name, 'get-'+name, [], '(own $stream)', '', 'i')
        self.bind('readin', 'streams', '[method]input-stream.blocking-read',
                  [('self','(borrow $ins)'),('len','u64')], '(result (list u8) (error $se))', 'iqi')

    def add(self, key, interface, types=''):
        self.groups[key] = [interface, types, []]

    def bind(self, name, group, public, params, result, core, returns=''):
        decl = ''.join(f'(param "{n}" {t})' for n,t in params)
        if result: decl += f'(result {result})'
        self.groups[group][2].append(f'(export "{public}" (func {decl}))')
        self.calls[name] = (group, public, core, returns)

    def alloc(self, data):
        ptr = self.next
        self.next = (ptr + len(data) + 7) & ~7
        assert self.next < 32768
        self.data.append(f'(data (i32.const {ptr}) "'+''.join(f'\\{b:02x}' for b in data)+'")')
        return ptr

    def call(self, name, *args):
        signature = self.calls[name][2]
        assert len(args) == len(signature), (name, args, signature)
        return '(call $'+name+' '+ ' '.join(a if isinstance(a,str) else f'({"i64" if k=="q" else "i32"}.const {a})' for k,a in zip(signature,args)) + ')'

    def emit(self, ptr, size):
        p = ptr if isinstance(ptr,str) else f'(i32.const {ptr})'
        n = size if isinstance(size,str) else f'(i32.const {size})'
        self.body.append(f'(call $emit {p} {n})')

    def result(self, name, *args, size=32):
        ptr = self.alloc(b'\xa5'*size)
        self.body.append(self.call(name, *args, ptr))
        return ptr

    def filesystem(self):
        self.add('fs', 'wasi:filesystem/types', F16_FS_TYPES)
        self.add('pre', 'wasi:filesystem/preopens', '''(alias outer 1 $desc (type $outer))
(export "descriptor" (type $d (eq $outer)))''')
        self.bind('dirs','pre','get-directories',[], '(list (tuple (own $d) string))','i')
        definitions = [
          ('open','open-at',[('self','(borrow $desc)'),('path-flags','$pf'),('path','string'),('open-flags','$of'),('flags','$df')], '(own $desc)', 'iiiiiii'),
          ('read','read',[('self','(borrow $desc)'),('length','u64'),('offset','u64')], '(tuple (list u8) bool)', 'iqqi'),
          ('write','write',[('self','(borrow $desc)'),('buffer','(list u8)'),('offset','u64')], 'u64', 'iiiqi'),
          ('stat','stat',[('self','(borrow $desc)')], '$stat', 'ii'),
          ('statat','stat-at',[('self','(borrow $desc)'),('path-flags','$pf'),('path','string')], '$stat','iiiii'),
          ('hash','metadata-hash',[('self','(borrow $desc)')], '$hash','ii'),
          ('hashat','metadata-hash-at',[('self','(borrow $desc)'),('path-flags','$pf'),('path','string')], '$hash','iiiii'),
          ('type','get-type',[('self','(borrow $desc)')], '$dt','ii'),
          ('listing','read-directory',[('self','(borrow $desc)')], '(own $entries)','ii'),
          ('entry','read-directory-entry',[('self','(borrow $entries)')], '(option $entry)','ii'),
          ('readlink','readlink-at',[('self','(borrow $desc)'),('path','string')], 'string','iiii'),
        ]
        for n,p,args,res,core in definitions:
            prefix = 'directory-entry-stream.' if n == 'entry' else 'descriptor.'
            self.bind(n,'fs','[method]'+prefix+p,args, f'(result {res} (error $error))',core)
        for n,p,extra,core in [
          ('sync','sync',[],'ii'), ('syncdata','sync-data',[],'ii'),
          ('mkdir','create-directory-at',[('path','string')],'iiii'),
          ('rmdir','remove-directory-at',[('path','string')],'iiii'),
          ('unlink','unlink-file-at',[('path','string')],'iiii'),
          ('rename','rename-at',[('old','string'),('newdesc','(borrow $desc)'),('new','string')],'iiiiiii'),
          ('link','link-at',[('flags','$pf'),('old','string'),('newdesc','(borrow $desc)'),('new','string')],'iiiiiiii'),
          ('symlink','symlink-at',[('old','string'),('new','string')],'iiiiii'),
        ]:
            self.bind(n,'fs','[method]descriptor.'+p,[('self','(borrow $desc)')]+extra,'(result (error $error))',core)
        ret = self.result('dirs',size=8)
        self.body.append(f'(local.set $dir (i32.load (i32.load (i32.const {ret}))))')

    def source(self, *, status=0):
        imports, aliases, lowers, coreimports, exports = [], [], [], [], []
        for key,(interface,types,funcs) in self.groups.items():
            imports.append(f'(import "{interface}@0.2.0" (instance ${key} {types} '+''.join(funcs)+'))')
            if key == 'ioerror': imports.append('(alias export $ioerror "error" (type $ioerror))')
            if key == 'streams':
                imports.append('(alias export $streams "output-stream" (type $os)) (alias export $streams "input-stream" (type $ins))')
            if key == 'fs': imports.append('(alias export $fs "descriptor" (type $desc))')
            if key == 'poll': imports.append('(alias export $poll "pollable" (type $pollable))')
        for name,(group,public,params,ret) in self.calls.items():
            lowers.append(f'(core func ${name} (canon lower (func ${group} "{public}") (memory $lib "memory") (realloc $realloc)))')
            sig = ('(param '+' '.join('i64' if k=='q' else 'i32' for k in params)+')') if params else ''
            if ret: sig += '(result '+('i64' if ret=='q' else 'i32')+')'
            coreimports.append(f'(import "deps" "{name}" (func ${name} {sig}))')
            exports.append(f'(export "{name}" (func ${name}))')
        return '(component\n'+ '\n'.join(imports)+'''
(core module $lib (memory (export "memory") 16)
 (global $bump (mut i32) (i32.const 65536))
 (func (export "cabi_realloc") (param i32 i32 i32 i32) (result i32) (local $p i32)
  global.get $bump i32.const 7 i32.add i32.const -8 i32.and local.tee $p
  local.get 3 i32.add global.set $bump local.get $p))
(core instance $lib (instantiate $lib))
(alias core export $lib "cabi_realloc" (core func $realloc))
'''+ '\n'.join(lowers)+ '\n(core module $main\n'+ '\n'.join(coreimports)+'''
(import "lib" "memory" (memory 16))
(func $emit (param $p i32) (param $n i32)
 (call $writeout (call $getstdout) (local.get $p) (local.get $n) (i32.const 128))
 (if (i32.load8_u (i32.const 128)) (then unreachable)))
'''+ '\n'.join(self.data)+ '''
(func (export "run") (result i32)
 (local $dir i32) (local $file i32) (local $other i32) (local $s i32) (local $i i32) (local $p i32)
'''+ '\n'.join(self.body)+f' (i32.const {status})))\n'+ '(core instance $deps '+''.join(exports)+''')
(core instance $m (instantiate $main (with "deps" (instance $deps)) (with "lib" (instance $lib))))
(func $run (result (result)) (canon lift (core func $m "run")))
(component $shim (import "run" (func $f (result (result)))) (export "run" (func $f)))
(instance $runinst (instantiate $shim (with "run" (func $run))))
(export "wasi:cli/run@0.2.0" (instance $runinst)))'''


def f16_load(ptr, kind='i32'):
    return f'({kind}.load (i32.const {ptr}))'


def f16_success(observed):
    assert observed['err'] is None, observed
    assert observed['exit_code'] in (None, 0), observed
    return observed['stdout']


def f16_open(guest, path, *, flags=0, target='file'):
    p = guest.alloc(path.encode())
    ret = guest.result('open', '(local.get $dir)', 1, p, len(path.encode()), flags, 3)
    guest.body.append(f'(if (i32.load8_u (i32.const {ret})) (then unreachable))')
    guest.body.append(f'(local.set ${target} {f16_load(ret+4)})')
    return ret


def f16_poll_services(g):
    g.add('poll','wasi:io/poll','(export "pollable" (type $pollable (sub resource)))')
    g.groups = {'poll':g.groups['poll'], **{k:v for k,v in g.groups.items() if k!='poll'}}
    g.bind('poll','poll','poll',[('in','(list (borrow $pollable))')],'(list u32)','iii')
    g.bind('ready','poll','[method]pollable.ready',[('self','(borrow $pollable)')],'bool','i','i')
    g.add('mono','wasi:clocks/monotonic-clock','''(alias outer 1 $pollable (type $p))
(export "pollable" (type $pollable (eq $p)))''')
    g.bind('now','mono','now',[],'u64','','q')
    g.bind('duration','mono','subscribe-duration',[('when','u64')],'(own $pollable)','q','i')
    g.bind('instant','mono','subscribe-instant',[('when','u64')],'(own $pollable)','q','i')
    g.groups['streams'][1]+='''(alias outer 1 $pollable (type $p))
(export "pollable" (type $pollable (eq $p)))'''
    for n,typ in [('input','$ins'),('output','$os')]:
        g.bind(n+'sub','streams','[method]'+n+'-stream.subscribe',[('self','(borrow '+typ+')')],'(own $pollable)','i','i')


@trace_execution
def f16_terminal_command(cli, path, terminals=(True, True, True)):
    """Run on real PTYs in raw mode, preserving the guest observation bytes."""
    import pty
    import subprocess
    import tty
    master, slave = pty.openpty()
    tty.setraw(slave)
    try:
        with subprocess.Popen([str(cli),'run',str(path)],
                stdin=slave if terminals[0] else subprocess.DEVNULL,
                stdout=slave if terminals[1] else subprocess.PIPE,
                stderr=slave if terminals[2] else subprocess.PIPE) as process:
            try:
                process.wait(timeout=30)
            except BaseException:
                process.kill(); process.wait(); raise
            assert process.returncode==0, process.returncode
            # Guest emits exactly three option discriminants, below pipe capacity.
            import select
            fd = master if terminals[1] else process.stdout.fileno()
            assert select.select([fd],[],[],5)[0], 'Terminal guest produced no observation'
            data=os.read(fd,1024)
            assert len(data)==3, data
            return data
    finally:
        os.close(master); os.close(slave)


@trace_execution
def f16_pipe_readiness(cli, path, *, incoming):
    """Hold a real pipe open, with or without bytes, until the guest exits."""
    import subprocess
    read_fd, write_fd = os.pipe()
    try:
        if incoming:
            assert os.write(write_fd,incoming)==len(incoming)
        process=subprocess.Popen([str(cli),'run',str(path)],stdin=read_fd,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            out,err=process.communicate(timeout=30)
        except BaseException:
            process.kill(); process.communicate(); raise
        assert process.returncode==0,(process.returncode,err)
        return out
    finally:
        os.close(read_fd); os.close(write_fd)


@trace_execution
def f16_clock_interval(cli, path):
    """Bracket two guest clock samples around input withheld by the host."""
    import select
    import subprocess
    import time
    start = time.monotonic_ns()
    process = subprocess.Popen([str(cli), 'run', str(path)], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        first = bytearray()
        deadline = time.monotonic() + 10
        while len(first) < 8:
            remaining = deadline - time.monotonic()
            assert remaining > 0 and select.select([process.stdout], [], [], remaining)[0], 'Incomplete first clock sample'
            part = os.read(process.stdout.fileno(), 8-len(first))
            assert part, 'Guest closed stdout before completing the first clock sample'
            first.extend(part)
        received = time.monotonic_ns()
        time.sleep(0.06)
        released = time.monotonic_ns()
        process.stdin.write(b'x'); process.stdin.flush()
        rest, err = process.communicate(timeout=10)
        finish = time.monotonic_ns()
        assert process.returncode == 0 and len(rest) == 8, (process.returncode, rest, err)
        return released-received, finish-start, struct.unpack('<Q', first)[0], struct.unpack('<Q', rest)[0]
    finally:
        if process.poll() is None:
            process.kill(); process.communicate()


def consumer_sources():
    return {'F16': (F16_ZIG, '/* Public WASI component consumer. */\n', ('v3_0',))}
