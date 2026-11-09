# feature: F15
"""Stateful resource calls through the public component embedding surface."""
import json
import os

import pytest
from F01_helpers import F01_BUILD, f01_driver
from F13_helpers import F13Driver, f13_call, f13_component, f13_values
from _helpers import build_outputs, run_json_adapter

F15_ZIG = r'''
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
const Ref = union(enum) { call: usize, literal: u32, unused: void, unused_high: void };
const Arg = union(enum) { value: V, borrow: Ref };
const Step = struct { name: []const u8 = "", args: []Arg = &.{}, drop: ?Ref = null };
const Outcome = struct { value: ?V = null, err: ?[]const u8 = null };
fn handle(ref: Ref, previous: []const Outcome) !u32 {
 return switch (ref) {
  .literal => |n| n,
  .unused => blk: {
   // Input construction: choose a handle never returned by a constructor.
   // At most previous.len handles exist, so this bounded search must succeed.
   for (0..previous.len + 1) |candidate| {
    var seen = false;
    for (previous) |out| {
     if (out.value) |v| {
      if (v == .own and v.own == candidate) seen = true;
     }
    }
    if (!seen) break :blk @as(u32, @intCast(candidate));
   }
   return error.NoUnusedHandle;
  },
  .unused_high => blk: {
   for (0..previous.len + 1) |offset| {
    const candidate = std.math.maxInt(u32) - @as(u32, @intCast(offset));
    var seen = false;
    for (previous) |out| {
     if (out.value) |v| { if (v == .own and v.own == candidate) seen = true; }
    }
    if (!seen) break :blk candidate;
   }
   return error.NoUnusedHandle;
  },
  .call => |i| blk: {
   if (i >= previous.len) return error.BadResultReference;
   if (previous[i].err != null) return error.ReferencedCallFailed;
   const v = previous[i].value orelse return error.ReferencedCallHasNoValue;
   if (v != .own) return error.ReferencedCallIsNotOwner;
   break :blk v.own;
  },
 };
}
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
 const parsed = try std.json.parseFromSlice([]Step, a, req, .{ .allocate = .alloc_always }); defer parsed.deinit();
 var engine = try zw.Engine.init(a, .{}); defer engine.deinit();
 var host = try zw.wasi.host.Host.init(a); defer host.deinit(); host.io = io;
 var opened = cm.open(&engine, a, bytes, &host, .{}) catch |err| {
  try emit(.{ .opened = false, .err = @errorName(err) }); return;
 }; defer opened.deinit();
 const outcomes = try a.alloc(Outcome, parsed.value.len); defer a.free(outcomes);
 var count: usize = 0;
 defer for (outcomes[0..count]) |out| { if (out.value) |v| v.deinit(a); };
 for (parsed.value, outcomes, 0..) |step, *out, index| {
  out.* = .{}; count += 1;
  if (step.drop) |ref| {
   const h = try handle(ref, outcomes[0..index]);
   opened.dropResource(h) catch |err| { out.err = @errorName(err); };
  } else {
   const args = try a.alloc(V, step.args.len); defer a.free(args);
   for (step.args, args) |arg, *v| v.* = switch (arg) {
    .value => |val| val,
    .borrow => |ref| .{ .borrow = try handle(ref, outcomes[0..index]) },
   };
   out.value = opened.invokeTyped(step.name, args, a) catch |err| {
    out.err = @errorName(err); continue;
   };
  }
 }
 try emit(.{ .opened = true, .calls = outcomes });
}
'''


class F15Driver(F13Driver):
    def program(self):
        return self.compiler.plan.consumer('F15')

    def observe(self, wat, steps):
        self.serial += 1
        path = self.directory / f'resources-{self.serial}.wasm'
        path.with_suffix('.wat').write_text(wat)
        path.write_bytes(self.binary(wat))
        req = path.with_suffix('.json')
        req.write_text(json.dumps(steps))
        observed = run_json_adapter([self.program(), path, req], timeout=30)
        path.with_suffix('.observation.json').write_bytes(observed.process.stdout)
        return observed.value


@pytest.fixture(scope='session')
def f15_driver(f01_driver, tmp_path_factory):
    return F15Driver(f01_driver, tmp_path_factory.mktemp('f15-consumer'))


def f15_invoke(name, *args):
    """Literal values and explicit references to earlier own results."""
    return f13_call(name, *[arg if 'borrow' in arg else {'value': arg} for arg in args])


def f15_borrow(call_index):
    return {'borrow': {'call': call_index}}


def f15_drop(call_index):
    return {'drop': {'call': call_index}}


F15_RESOURCE_WAT = r'''(component
 (core module $storage
  (memory (export "memory") 1)
  (func (export "destroy-counter") (param $p i32)
   i32.const 0 i32.const 0 i32.load i32.const 10 i32.mul
   local.get $p i32.load i32.add i32.store)
  (func (export "destroy-token") (param $p i32)
   i32.const 4 i32.const 4 i32.load i32.const 10 i32.mul
   local.get $p i32.load i32.add i32.store)
  (func (export "counter-journal") (result i32) i32.const 0 i32.load)
  (func (export "token-journal") (result i32) i32.const 4 i32.load))
 (core instance $store (instantiate $storage))
 (alias core export $store "memory" (core memory $memory))
 (alias core export $store "destroy-counter" (core func $dc))
 (alias core export $store "destroy-token" (core func $dt))
 (type $counter (resource (rep i32) (dtor (func $dc))))
 (type $token (resource (rep i32) (dtor (func $dt))))
 (core func $nc (canon resource.new $counter))
 (core func $nt (canon resource.new $token))
 (core instance $builtins (export "new-counter" (func $nc)) (export "new-token" (func $nt)))
 (core module $guest
  (import "store" "memory" (memory 1))
  (import "builtins" "new-counter" (func $nc (param i32) (result i32)))
  (import "builtins" "new-token" (func $nt (param i32) (result i32)))
  (global $next (mut i32) (i32.const 64))
  (func $allocate (param $initial i32) (result i32) (local $p i32)
   global.get $next local.tee $p local.get $initial i32.store
   global.get $next i32.const 4 i32.add global.set $next local.get $p)
  (func (export "new-counter") (param i32) (result i32) local.get 0 call $allocate call $nc)
  (func (export "new-token") (param i32) (result i32) local.get 0 call $allocate call $nt)
  (func (export "read") (param i32) (result i32) local.get 0 i32.load)
  (func (export "add") (param $p i32) (param $n i32) (result i32)
   local.get $p local.get $p i32.load local.get $n i32.add i32.store
   local.get $p i32.load))
 (core instance $g (instantiate $guest (with "store" (instance $store)) (with "builtins" (instance $builtins))))
 (func $new-counter (param "initial" u32) (result (own $counter))
  (canon lift (core func $g "new-counter") (memory $memory)))
 (func $new-token (param "initial" u32) (result (own $token))
  (canon lift (core func $g "new-token") (memory $memory)))
 (func $read-counter (param "self" (borrow $counter)) (result u32)
  (canon lift (core func $g "read") (memory $memory)))
 (func $read-token (param "self" (borrow $token)) (result u32)
  (canon lift (core func $g "read") (memory $memory)))
 (func $add-counter (param "self" (borrow $counter)) (param "amount" u32) (result u32)
  (canon lift (core func $g "add") (memory $memory)))
 (func $counter-journal (result u32)
  (canon lift (core func $store "counter-journal") (memory $memory)))
 (func $token-journal (result u32)
  (canon lift (core func $store "token-journal") (memory $memory)))
 (instance $api (export "counter" (type $counter)) (export "token" (type $token))
  (export "new-counter" (func $new-counter))
  (export "new-token" (func $new-token))
  (export "read-counter" (func $read-counter))
  (export "read-token" (func $read-token))
  (export "add-counter" (func $add-counter))
  (export "counter-journal" (func $counter-journal))
  (export "token-journal" (func $token-journal)))
 (export "resources" (instance $api)))'''


def f15_resource_call(name, *args):
    return f15_invoke('resources#' + name, *args)


F15_EQUAL_REP_WAT = '(component\n (core module $journal\n  (memory (export "memory") 1)\n  (global $drops (mut i32) (i32.const 0))\n  (func (export "destroy") (param i32)\n   global.get $drops i32.const 1 i32.add global.set $drops)\n  (func (export "released") (result i32) global.get $drops))\n (core instance $j (instantiate $journal))\n (alias core export $j "memory" (core memory $memory))\n (alias core export $j "destroy" (core func $destroy))\n (type $ticket (resource (rep i32) (dtor (func $destroy))))\n (core func $new (canon resource.new $ticket))\n (core instance $builtins (export "mint" (func $new)))\n (core module $guest\n  (import "builtins" "mint" (func $new (param i32) (result i32)))\n  (func (export "mint") (param i32) (result i32) local.get 0 call $new)\n  (func (export "inspect") (param i32) (result i32) local.get 0))\n (core instance $g (instantiate $guest (with "builtins" (instance $builtins))))\n (func $mint (param "number" u32) (result (own $ticket))\n  (canon lift (core func $g "mint") (memory $memory)))\n (func $inspect (param "self" (borrow $ticket)) (result u32)\n  (canon lift (core func $g "inspect") (memory $memory)))\n (func $released (result u32)\n  (canon lift (core func $j "released") (memory $memory)))\n (instance $api\n  (export "ticket" (type $ticket))\n  (export "mint" (func $mint))\n  (export "inspect" (func $inspect))\n  (export "released" (func $released)))\n (export "tickets" (instance $api)))'


def consumer_sources():
    return {'F15': (F15_ZIG, '/* Public resource consumer. */\n', ('v3_0',))}
