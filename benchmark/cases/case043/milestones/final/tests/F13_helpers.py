# feature: F13
"""Typed component consumers; all observations come from public embedder calls.

WAT is compiled/validated by the earlier feature's independent wasm-tools driver.
The adapter serializes public value/type trees without reconstructing ABI results.
All call results remain alive until the complete sequence has finished.
"""
import json
import os

import pytest
from F01_helpers import F01_BUILD, f01_driver
from _helpers import build_outputs, run_json_adapter

F13_ZIG = r'''
const std = @import("std");
const zw = @import("navor");
const cm = zw.feature.component.host;
const V = cm.ComponentValue;
const a = std.heap.c_allocator;
extern fn printf([*:0]const u8, ...) c_int;
fn emit(v: anytype) !void {
    const s = try std.json.Stringify.valueAlloc(a, v, .{});
    defer a.free(s);
    _ = printf("%.*s", @as(c_int, @intCast(s.len)), s.ptr);
}
const Call = struct { name: []const u8, args: []V };
const Request = struct { discover: bool = false, release: bool = false, diagnostics: bool = false, calls: []Call };
const Outcome = struct { value: ?V = null, err: ?[]const u8 = null };
pub export fn main(argc: c_int, argv: [*][*:0]u8) c_int {
    if (argc != 3) return 64;
    run(std.mem.span(argv[1]), std.mem.span(argv[2])) catch |err| {
        std.debug.print("Adapter failed: {s}\n", .{@errorName(err)});
        return 70;
    };
    return 0;
}
fn run(path: []const u8, request_path: []const u8) !void {
    var threaded = std.Io.Threaded.init(a, .{});
    defer threaded.deinit();
    const io = threaded.io();
    const bytes = try std.Io.Dir.cwd().readFileAlloc(io, path, a, .limited(1 << 24));
    var bytes_live = true;
    defer if (bytes_live) a.free(bytes);
    const request_bytes = try std.Io.Dir.cwd().readFileAlloc(io, request_path, a, .limited(1 << 24));
    defer a.free(request_bytes);
    const parsed = try std.json.parseFromSlice(Request, a, request_bytes, .{ .allocate = .alloc_always });
    defer parsed.deinit();
    const req = parsed.value;
    var engine = try zw.Engine.init(a, .{});
    defer engine.deinit();
    var host = try zw.wasi.host.Host.init(a);
    defer host.deinit();
    host.io = io;
    var opened = cm.open(&engine, a, bytes, &host, .{}) catch |err| {
        try emit(.{ .opened = false, .err = @errorName(err) });
        return;
    };
    defer opened.deinit();
    if (req.release) {
        // Overwrite while still owned, then release. No access to freed memory.
        @memset(bytes, 0xa5);
        a.free(bytes);
        bytes_live = false;
    }
    _ = printf("{\"opened\":true");
    if (req.discover) {
        const funcs = try opened.exportedFuncs(a);
        defer zw.feature.component.types.TypeInfo.freeExportedFuncs(a, funcs);
        var arena = std.heap.ArenaAllocator.init(a);
        defer arena.deinit();
        _ = printf(",\"exports\":[");
        for (funcs, 0..) |f, i| {
            if (i != 0) _ = printf(",");
            const sig = try opened.resolveFuncSig(arena.allocator(), f.name);
            try emit(.{ .name = f.name, .signature = sig });
        }
        _ = printf("]");
    }
    const results = try a.alloc(Outcome, req.calls.len);
    defer a.free(results);
    const messages = try a.alloc(?[]const u8, req.calls.len);
    @memset(messages, null);
    defer {
        for (messages) |message| if (message) |text| a.free(text);
        a.free(messages);
    }
    var count: usize = 0;
    defer for (results[0..count]) |r| { if (r.value) |v| v.deinit(a); };
    for (req.calls, results) |c, *r| {
        count += 1;
        r.* = .{};
        if (req.diagnostics) zw.diagnostic.clearDiag();
        r.value = opened.invokeTyped(c.name, c.args, a) catch |err| {
            r.err = @errorName(err);
            if (req.diagnostics) {
                if (zw.diagnostic.lastDiagnostic()) |diag| {
                    // The public diagnostic borrows a slot overwritten by the
                    // next call. Snapshot it before proceeding, without parsing.
                    messages[count - 1] = try a.dupe(u8, diag.message());
                }
            }
            continue;
        };
    }
    _ = printf(",\"calls\":");
    try emit(results);
    if (req.diagnostics) {
        _ = printf(",\"diagnostics\":");
        try emit(messages);
    }
    _ = printf("}");
}
'''


class F13Driver:
    def __init__(self, compiler, directory):
        self.compiler = compiler
        self.directory = directory
        self.executable = None
        self.serial = 0

    def program(self):
        return self.compiler.plan.consumer('F13')

    def binary(self, wat, *, valid=True):
        binary = self.compiler.wat(wat)
        assert self.compiler.standard_valid(binary) is valid, 'Independent component validation disagrees'
        return binary

    def observe(self, binary, calls=(), *, discover=False, release=False, diagnostics=False):
        self.serial += 1
        path = self.directory / f'component-{self.serial}.wasm'
        path.write_bytes(binary)
        request = path.with_suffix('.json')
        request.write_text(json.dumps({'calls': calls, 'discover': discover, 'release': release,
                                       'diagnostics': diagnostics}))
        observed = run_json_adapter([self.program(), path, request], timeout=30)
        path.with_suffix('.observation.json').write_bytes(observed.process.stdout)
        return observed.value


@pytest.fixture(scope='session')
def f13_driver(f01_driver, tmp_path_factory):
    return F13Driver(f01_driver, tmp_path_factory.mktemp('f13-consumer'))


def f13_call(name, *args):
    return {'name': name, 'args': list(args)}


def f13_values(observation):
    assert observation['opened'] is True, observation
    assert all(c['err'] is None for c in observation['calls']), observation
    return [c['value'] for c in observation['calls']]


def f13_component(functions, *, types='', exports=None, encoding='utf8', core_extra=''):
    """Assemble declared WAT; tuples supply name, WIT params/result, core body.

    This creates guest inputs, not a product result oracle. The independent
    validator verifies each well-formed fixture before it reaches the product.
    """
    core = '\n'.join(f'(func (export "{name}") {body})' for name, _, _, body in functions)
    lifts = []
    for i, (name, params, result, _) in enumerate(functions):
        lifts.append(f'''(alias core export $i "{name}" (core func $f{i}))
(type $t{i} (func {params} {f'(result {result})' if result else ''}))
(func ${name} (type $t{i}) (canon lift (core func $f{i})
    (memory $memory) (realloc $realloc) string-encoding={encoding}))''')
    if exports is None:
        exports = '\n'.join(f'(export "{name}" (func ${name}))' for name, *_ in functions)
    return f'''(component
(core module $m
 (memory (export "memory") 2)
 (global $heap (mut i32) (i32.const 16384))
 (func (export "realloc") (param i32 i32 i32 i32) (result i32) (local $p i32)
  global.get $heap local.get 2 i32.const 1 i32.sub i32.add
  i32.const 0 local.get 2 i32.sub i32.and local.tee $p
  local.get 3 i32.add global.set $heap local.get $p)
 {core_extra}
 {core})
(core instance $i (instantiate $m))
(alias core export $i "memory" (core memory $memory))
(alias core export $i "realloc" (core func $realloc))
{types}
{' '.join(lifts)}
{exports})'''


def f13_scalar_wat():
    specs = [
      ('bool','i32','i32.eqz'),
      ('s8','i32','i32.extend8_s local.tee 0 i32.const 0 i32.lt_s if (result i32) local.get 0 i32.const 7 i32.add else local.get 0 i32.const 7 i32.sub end'),
      ('u8','i32','i32.const 0 i32.lt_s if (result i32) i32.const 0 else local.get 0 i32.const 165 i32.xor end'),
      ('s16','i32','i32.extend16_s local.tee 0 i32.const 0 i32.lt_s if (result i32) local.get 0 i32.const 300 i32.add else local.get 0 i32.const 300 i32.sub end'),
      ('u16','i32','i32.const 0 i32.lt_s if (result i32) i32.const 0 else local.get 0 i32.const 42330 i32.xor end'),
      ('s32','i32','i32.const 17 i32.sub'),
      ('u32','i32','i32.const 2147483651 i32.xor'), ('s64','i64','i64.const 37 i64.add'),
      ('u64','i64','i64.const 9223372036854775809 i64.xor'),
      ('f32','f32','f32.const -2 f32.mul'), ('f64','f64','f64.const -2 f64.mul'),
      ('char','i32','i32.const 1 i32.add'),
    ]
    return f13_component([(f'change-{t}',f'(param "value" {t})',t,
                f'(param {c}) (result {c}) local.get 0 {op}') for t,c,op in specs])

F13_TYPES = '''
(type $list-def (list u32)) (export $list "numbers" (type $list-def))
(type $coords-def (tuple s16 u32)) (export $coords "coordinates" (type $coords-def))
(type $rec-def (record (field "point" $coords) (field "samples" $list) (field "label" string)))
(export $rec "payload" (type $rec-def))
(type $choice-def (variant (case "empty") (case "count" u32) (case "text" string)))
(export $choice "choice" (type $choice-def))
(type $color-def (enum "red" "green" "blue")) (export $color "color" (type $color-def))
(type $bits-def (flags "read" "write" "execute")) (export $bits "permissions" (type $bits-def))
(type $opt-def (option s32)) (export $opt "maybe-value" (type $opt-def))
(type $res-def (result $rec (error string))) (export $res "answer-value" (type $res-def))
'''
F13_STRING_BODY = '''(param i32 i32) (result i32)
 i32.const 1024 local.get 0 local.get 1 memory.copy
 i32.const 1024 local.get 1 i32.add i32.const 33 i32.store8
 i32.const 0 i32.const 1024 i32.store
 i32.const 4 local.get 1 i32.const 1 i32.add i32.store i32.const 0'''
F13_LIST_BODY = '''(param i32 i32) (result i32) (local $j i32)
 (block $done (loop $next
 local.get $j local.get 1 i32.ge_u br_if $done
 i32.const 4096 local.get $j i32.const 4 i32.mul i32.add
 local.get 0 local.get $j i32.const 4 i32.mul i32.add i32.load
 i32.const 7 i32.add i32.store
 local.get $j i32.const 1 i32.add local.set $j br $next))
 i32.const 0 i32.const 4096 i32.store
 i32.const 4 local.get 1 i32.store i32.const 0'''
F13_REC_BODY = '''(param i32 i32 i32 i32 i32 i32) (result i32)
 i32.const 256 local.get 0 i32.const 2 i32.sub i32.store16
 i32.const 260 local.get 1 i32.const 5 i32.add i32.store
 i32.const 264 local.get 2 i32.store i32.const 268 local.get 3 i32.store
 i32.const 272 local.get 4 i32.store i32.const 276 local.get 5 i32.store
 i32.const 256'''
F13_VAR_BODY = '''(param i32 i32 i32) (result i32)
 local.get 0 i32.eqz
 if
  i32.const 64 i32.const 2 i32.store i32.const 68 i32.const 8000 i32.store
  i32.const 72 i32.const 6 i32.store
 else local.get 0 i32.const 1 i32.eq
  if
   i32.const 64 i32.const 1 i32.store
   i32.const 68 local.get 1 i32.const 7 i32.add i32.store
  else
   i32.const 64 local.get 2 i32.eqz i32.eqz i32.store
   i32.const 68 local.get 2 i32.store
  end
 end i32.const 64'''
F13_OPT_BODY = '''(param i32 i32) (result i32)
 local.get 0 i32.eqz
 if
  i32.const 128 i32.const 1 i32.store i32.const 132 i32.const -91 i32.store
 else
  i32.const 128 local.get 1 i32.const 7 i32.ne i32.store
  i32.const 132 local.get 1 i32.const 9 i32.add i32.store
 end i32.const 128'''
# result<record, string> accepts the record plus a boolean selecting the result arm.
F13_RESULT_BODY = '''(param i32 i32 i32 i32 i32 i32 i32) (result i32)
 i32.const 320 local.get 6 i32.eqz i32.store
 local.get 6 if
 i32.const 324 local.get 0 i32.const 2 i32.sub i32.store16
 i32.const 328 local.get 1 i32.const 5 i32.add i32.store
 i32.const 332 local.get 2 i32.store i32.const 336 local.get 3 i32.store
 i32.const 340 local.get 4 i32.store i32.const 344 local.get 5 i32.store
 else
 i32.const 324 local.get 4 i32.store i32.const 328 local.get 5 i32.store
 end i32.const 320'''

def f13_compound_functions():
    return [
      ('decorate','(param "text" string)','string',F13_STRING_BODY),
      ('shift','(param "values" $list)','$list',F13_LIST_BODY),
      ('adjust','(param "payload" $rec)','$rec',F13_REC_BODY),
      ('choose','(param "choice" $choice)','$choice',F13_VAR_BODY),
      ('rotate','(param "color" $color)','$color','(param i32) (result i32) local.get 0 i32.const 1 i32.add i32.const 3 i32.rem_u'),
      ('toggle','(param "bits" $bits)','$bits','(param i32) (result i32) local.get 0 i32.const 5 i32.xor'),
      ('maybe','(param "value" $opt)','$opt',F13_OPT_BODY),
      ('answer','(param "payload" $rec) (param "accept" bool)','$res',F13_RESULT_BODY),
    ]

def f13_compound_wat():
    return f13_component(f13_compound_functions(), types=F13_TYPES, core_extra='(data (i32.const 8000) "branch")')

def f13_record(x,y,nums,label):
    return {'record':[{'name':'point','value':{'tuple':[{'s16':x},{'u32':y}]}},
                      {'name':'samples','value':{'list':[{'u32':n} for n in nums]}},
                      {'name':'label','value':{'string':label}}]}


def f13_async_boundary_component(family):
    """A real canonical stream/future producer, consumed via ordinary typed calls.

    Returning an actually minted handle avoids depending on how an implementation
    orders unsupported-type detection against invalid-handle detection.
    """
    assert family in ('stream', 'future')
    return f'''(component
 (type $h ({family} u32)) (export "handle" (type $h))
 (core func $new (canon {family}.new $h))
 (core module $support)
 (core module $m
  (import "async" "new" (func $new (result i64)))
  (memory (export "memory") 1)
  (func (export "baseline") (param i32) (result i32) local.get 0 i32.const 13 i32.add)
  (func (export "consume") (param i32) (result i32) local.get 0)
  (func (export "produce") (result i32) call $new i32.wrap_i64))
 (core instance $deps (export "new" (func $new)))
 (core instance $i (instantiate $m (with "async" (instance $deps))))
 (alias core export $i "memory" (core memory $mem))
 (func (export "baseline") (param "value" u32) (result u32)
  (canon lift (core func $i "baseline") (memory $mem)))
 (func (export "consume") (param "value" $h) (result u32)
  (canon lift (core func $i "consume") (memory $mem)))
 (func (export "produce") (result $h)
  (canon lift (core func $i "produce") (memory $mem))))'''


def f13_wide_tuple_component():
    """A large ordered argument exercises the Canonical ABI indirect-argument form."""
    terms = [f'local.get 0 i32.load offset={4*i} i32.const {i+1} i32.mul'
             for i in range(20)]
    body = '(param i32) (result i32) ' + terms[0] + ' ' + ' '.join(t + ' i32.add' for t in terms[1:])
    types = '(type $wide-def (tuple ' + ' '.join(['u32'] * 20) + ')) (export $wide "wide" (type $wide-def))'
    return f13_component([('weighted', '(param "values" $wide)', 'u32', body)], types=types)


def consumer_sources():
    return {'F13': (F13_ZIG, '/* The consumer is implemented in Zig. */\n', ('v3_0',))}
