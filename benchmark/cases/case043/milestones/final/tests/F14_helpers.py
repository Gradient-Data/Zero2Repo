# feature: F14
"""Real composed guests and a public graph API consumer."""
import json
import os
import pytest
from F01_helpers import F01_BUILD, f01_driver
from F13_helpers import f13_component
from _helpers import build_outputs, run_json_adapter

F14_ZIG = r'''const std = @import("std");
const zw = @import("navor");
const a = std.heap.c_allocator;
extern fn printf([*:0]const u8, ...) c_int;
fn emit(v: anytype) !void {
 const s = try std.json.Stringify.valueAlloc(a, v, .{});
 defer a.free(s);
 _ = printf("%.*s", @as(c_int, @intCast(s.len)), s.ptr);
}
const Call = struct { name: []const u8, args: []i32 };
const Outcome = struct { value: ?i32 = null, err: ?[]const u8 = null };
pub export fn main(argc: c_int, argv: [*][*:0]u8) c_int {
 if (argc != 3) return 64;
 run(std.mem.span(argv[1]), std.mem.span(argv[2])) catch |err| {
  std.debug.print("Adapter failed: {s}\n", .{@errorName(err)}); return 70;
 }; return 0;
}
fn run(path: []const u8, request: []const u8) !void {
 var threaded = std.Io.Threaded.init(a, .{}); defer threaded.deinit();
 const io = threaded.io();
 const bytes = try std.Io.Dir.cwd().readFileAlloc(io, path, a, .limited(1 << 24)); defer a.free(bytes);
 const req = try std.Io.Dir.cwd().readFileAlloc(io, request, a, .limited(1 << 24)); defer a.free(req);
 const parsed = try std.json.parseFromSlice([]Call, a, req, .{ .allocate = .alloc_always }); defer parsed.deinit();
 var engine = try zw.Engine.init(a, .{}); defer engine.deinit();
 var graph = zw.feature.component.host.instantiateGraph(&engine, a, bytes, .{}) catch |err| {
  try emit(.{ .instantiated = false, .err = @errorName(err) }); return;
 }; defer graph.deinit();
 const results = try a.alloc(Outcome, parsed.value.len); defer a.free(results);
 for (parsed.value, results) |call, *out| {
  out.* = .{};
  const args = try a.alloc(zw.Value, call.args.len); defer a.free(args);
  for (args, call.args) |*arg, n| arg.* = .{ .i32 = n };
  var res = [_]zw.Value{.{ .i32 = -991 }};
  graph.invokeFlat(call.name, args, &res) catch |err| { out.err = @errorName(err); continue; };
  out.value = res[0].i32;
 }
 try emit(.{ .instantiated = true, .calls = results });
}
'''

class F14Driver:
    def __init__(self, compiler, directory):
        self.compiler, self.directory = compiler, directory
        self.executable = None
        self.serial = 0

    def program(self):
        return self.compiler.plan.consumer('F14')

    def observe(self, wat, calls=(), *, valid=True):
        self.serial += 1
        path = self.directory / f'graph-{self.serial}.wasm'
        path.with_suffix('.wat').write_text(wat)
        binary = self.compiler.wat(wat)
        assert self.compiler.standard_valid(binary) is valid, str(path)
        path.write_bytes(binary)
        req = path.with_suffix('.json')
        req.write_text(json.dumps(calls))
        observation = run_json_adapter([self.program(), path, req], timeout=30)
        path.with_suffix('.observation.json').write_bytes(observation.process.stdout)
        return observation.value

@pytest.fixture(scope='session')
def f14_driver(f01_driver, tmp_path_factory):
    return F14Driver(f01_driver, tmp_path_factory.mktemp('f14-consumer'))

def f14_call(name='evaluate', *args):
    return {'name':name, 'args':list(args)}

def f14_values(observed):
    assert observed['instantiated'] is True, observed
    assert all(c['err'] is None for c in observed['calls']), observed
    return [c['value'] for c in observed['calls']]

F14_MEMORY = '''(core module $memory-module
 (memory (export "mem") 2)
 (global $heap (mut i32) (i32.const 24000))
 (func (export "cabi_realloc") (param i32 i32 i32 i32) (result i32) (local $p i32)
  global.get $heap local.get 2 i32.const 1 i32.sub i32.add
  i32.const 0 local.get 2 i32.sub i32.and local.tee $p
  local.get 3 i32.add global.set $heap local.get $p))
(core instance $memory (instantiate $memory-module))'''

def f14_graph(params, result, provider_body, lower_signature, caller_body, *,
              types=(), data='', provider_data='', caller_params='',
              name='evaluate', service='calculate', interface=None, reexport=False,
              encoding='utf8', missing=False, alternative=None, choose_alternative=False,
              extra_functions=(), import_name=None):
    """Compose separate memories and real lifted/lowered connections.

    Type declarations and guest bodies are inputs, never inferred product answers.
    Core memory layouts used by guests are those of the published Canonical ABI.
    """
    pt, ct, aliases, bindings = [], [], [], []
    for t, definition in types:
        pt.append(f'(type ${t}-def {definition}) (export ${t} "{t}" (type ${t}-def))')
        ct.append(f'(type ${t}-def {definition}) (import "{t}" (type ${t} (eq ${t}-def)))')
        aliases.append(f'(alias export $provider "{t}" (type $outer-{t}))')
        bindings.append(f'(with "{t}" (type $outer-{t}))')
    provider = f13_component([(service, params, result, provider_body), *extra_functions],
                            types=' '.join(pt), core_extra=provider_data, encoding=encoding)
    provider = provider.replace('(component', '(component $Provider', 1).replace('\"realloc\"', '\"cabi_realloc\"')
    signature = f'{params} (result {result})'
    import_name = service if import_name is None else import_name
    if interface:
        imp = f'(import "{interface}" (instance $api (export "{service}" (func {signature})))) (alias export $api "{service}" (func $target))'
        bridge = f'(instance $api (export "{service}" (func $provider "{service}")))'
        binding = f'(with "{interface}" (instance $api))'
    else:
        imp = f'(import "{import_name}" (func $target {signature}))'
        bridge = ''
        binding = f'(with "{import_name}" (func $provider "{service}"))'
    if missing:
        binding = ''
    consumer = f'''(component $Consumer
 {' '.join(ct)} {imp}
 {F14_MEMORY}
 (core func $lower (canon lower (func $target) (memory $memory "mem")
  (realloc (func $memory "cabi_realloc")) string-encoding={encoding}))
 (core module $main
  (import "dependency" "apply" (func $target {lower_signature}))
  (import "storage" "mem" (memory 2))
  {data}
  (func (export "work") {caller_params} (result i32) {caller_body}))
 (core instance $deps (export "apply" (func $lower)))
 (core instance $main-instance (instantiate $main
  (with "dependency" (instance $deps)) (with "storage" (instance $memory))))
 (func (export "{name}") {''.join(f'(param "arg-{i}" u32)' for i in range(caller_params.count('i32')))} (result u32)
  (canon lift (core func $main-instance "work"))))'''
    alternative_component = ''
    if alternative is not None:
        alternative_component = f13_component([(service, params, result, alternative)],
            types=' '.join(pt), core_extra=provider_data, encoding=encoding)
        alternative_component = alternative_component.replace('(component', '(component $Alternative', 1)
    instances = '(instance $provider-origin (instantiate $Provider)) (export $provider "supplier" (instance $provider-origin))' if reexport else '(instance $provider (instantiate $Provider))'
    if alternative is not None:
        selected = '$two' if choose_alternative else '$one'
        instances = f'(instance $one (instantiate $Provider)) (instance $two (instantiate $Alternative)) (export $provider \"supplier\" (instance {selected}))'
    end = f'(export $consumer-export "client" (instance $consumer)) (export "{name}" (func $consumer-export "{name}"))' if reexport else f'(export "{name}" (func $consumer "{name}"))'
    end += ' '.join(f'(export \"{n}\" (func $provider \"{n}\"))' for n, *_ in extra_functions)
    return f'''(component {provider} {alternative_component} {consumer} {instances}
 {' '.join(aliases)} {bridge}
 (instance $consumer (instantiate $Consumer {' '.join(bindings)} {binding})) {end})'''

def f14_bytes(data):
    return '"' + ''.join('\\%02x' % b for b in data) + '"'

# Full-content polynomial checksum in guest code. This is the guest's workload,
# not a host reimplementation of any product transform.
F14_HASH = '''(func $hash (param $ptr i32) (param $len i32) (result i32)
 (local $i i32) (local $h i32)
 i32.const 17 local.set $h
 block $done loop $next
  local.get $i local.get $len i32.ge_u br_if $done
  local.get $h i32.const 31 i32.mul
  local.get $ptr local.get $i i32.add i32.load8_u i32.add local.set $h
  local.get $i i32.const 1 i32.add local.set $i br $next
 end end local.get $h)'''


def f14_check_bytes(name, payload):
    """Guest equality against supplied content, not a product oracle algorithm."""
    checks = ['local.get 1 i32.const %d i32.eq' % len(payload)]
    checks += [f'local.get 0 i32.load8_u offset={i} i32.const {b} i32.eq i32.and'
               for i, b in enumerate(payload)]
    return f'(func ${name} (param i32 i32) (result i32) ' + ' '.join(checks) + ')'


def f14_record_graphs():
    text = 'A\x00é水🙂z'.encode()
    numbers = bytes.fromhex('0102feff3412')
    types = [('items','(list u16)'),
             ('content','(record (field "text" string) (field "samples" $items))'),
             ('packet','(record (field "code" s16) (field "content" $content) (field "flag" bool) (field "symbol" char))')]
    checks = f14_check_bytes('text',text) + f14_check_bytes('numbers',numbers)
    data = f'(data (i32.const 512) {f14_bytes(text)}) (data (i32.const 1024) {f14_bytes(numbers)})'
    body = ('(param i32 i32 i32 i32 i32 i32 i32) (result i32) '
            'local.get 0 i32.extend16_s i32.const -1234 i32.eq '
            'local.get 1 local.get 2 call $text i32.and '
            'local.get 3 local.get 4 i32.const 2 i32.mul call $numbers i32.and '
            'local.get 5 i32.const 1 i32.eq i32.and '
            'local.get 6 i32.const 128578 i32.eq i32.and')
    param = f14_graph('(param "packet" $packet)','bool', body,
        '(param i32 i32 i32 i32 i32 i32 i32) (result i32)',
        f'i32.const -1234 i32.const 512 i32.const {len(text)} i32.const 1024 i32.const 3 i32.const 1 i32.const 128578 call $target',
        types=types,data=data,provider_data=checks)
    # Canonical record memory: s16@0, nested string@4/list@12, bool@20, char@24.
    stores = ('i32.const 64 i32.const -1234 i32.store16 '
              'i32.const 68 i32.const 512 i32.store '
              f'i32.const 72 i32.const {len(text)} i32.store '
              'i32.const 76 i32.const 1024 i32.store i32.const 80 i32.const 3 i32.store '
              'i32.const 84 i32.const 1 i32.store8 i32.const 88 i32.const 128578 i32.store ')
    read = ('i32.const 128 call $target '
            'i32.const 128 i32.load16_s i32.const -1234 i32.eq '
            'i32.const 132 i32.load i32.const 136 i32.load call $text i32.and '
            'i32.const 140 i32.load i32.const 144 i32.load i32.const 2 i32.mul call $numbers i32.and '
            'i32.const 148 i32.load8_u i32.const 1 i32.eq i32.and '
            'i32.const 152 i32.load i32.const 128578 i32.eq i32.and')
    result = f14_graph('', '$packet', '(result i32) '+stores+'i32.const 64',
        '(param i32)',read,types=types,data=checks,provider_data=data)
    # A pointer-free record also exercises wide numeric fields and nested layout.
    flat_types = [('numbers','(record (field "wide" u64) (field "ratio" f64))'),
                  ('summary','(record (field "small" s8) (field "flag" bool) (field "symbol" char) (field "data" $numbers))')]
    flat = f14_graph('', '$summary', '(result i32) '
        'i32.const 64 i32.const -93 i32.store8 i32.const 65 i32.const 1 i32.store8 '
        'global.get $generation i32.const 1 i32.add global.set $generation '
        'i32.const 68 global.get $generation i32.store '
        'i32.const 72 i64.const 17375808098319191535 i64.store '
        'i32.const 80 f64.const -9.25 f64.store i32.const 64', '(param i32)',
        'i32.const 128 call $target '
        'i32.const 128 i32.load8_s i32.const -93 i32.eq '
        'i32.const 129 i32.load8_u i32.const 1 i32.eq i32.and '
        'i32.const 132 i32.load i32.mul '
        'i32.const 136 i64.load i64.const 17375808098319191535 i64.eq i32.mul '
        'i32.const 144 f64.load f64.const -9.25 f64.eq i32.mul', types=flat_types,
        provider_data='(global $generation (mut i32) (i32.const 0))')
    return [('record-argument',param),('record-result',result),('scalar-record-result',flat)]


def f14_refused(observed, error):
    """A declared refusal may surface during construction or invocation."""
    if observed['instantiated']:
        assert observed['calls'] == [{'value':None, 'err':error}], observed
    else:
        assert observed['err'] == error, observed


def consumer_sources():
    return {'F14': (F14_ZIG, '/* Public Zig consumer. */\n', ('v3_0',))}
