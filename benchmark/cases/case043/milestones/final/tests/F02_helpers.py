# feature: F02
"""Execution consumers of public C and Zig APIs; no product internals.

Arguments and results use numeric kind plus unsigned IEEE/integer bits, so the
JSON transport loses neither i64 precision nor NaN information. All calls in an
observation use one instance. Tool/build/adapter failures raise, never become
product traps. WAT compilation and validation reuse the earlier feature driver.
"""
import json
import os
from pathlib import Path
import struct

import pytest
from F01_helpers import F01_BUILD, f01_driver
from _helpers import build_outputs, run_json_adapter

F02_ZIG = r'''
const std = @import("std");
const zw = @import("navor");
extern fn f02_main(c_int, [*][*:0]u8) c_int;
extern fn printf([*:0]const u8, ...) c_int;
pub export fn main(argc: c_int, argv: [*][*:0]u8) c_int { return f02_main(argc, argv); }
fn number(s: [*:0]const u8) u64 { return std.fmt.parseInt(u64, std.mem.span(s), 10) catch @panic("Invalid adapter integer"); }
pub export fn f02_zig(data: [*]const u8, len: usize, mode: c_int, argc: usize, argv: [*][*:0]u8) c_int {
    var engine = zw.Engine.init(std.heap.c_allocator, .{}) catch @panic("Engine allocation failed");
    defer engine.deinit();
    var module = engine.compile(data[0..len]) catch |err| { _ = printf("compile: %s\n", @as([*:0]const u8, @errorName(err))); return 70; };
    defer module.deinit();
    var inst = module.instantiate(.{ .engine = if (mode == 1) .jit else .interp }) catch |err| {
        _ = printf("{\"created\":false,\"error\":\"%s\"}", @as([*:0]const u8, @errorName(err))); return 0;
    };
    defer inst.deinit();
    _ = printf("{\"created\":true,\"calls\":[");
    var pos: usize = 0;
    var first = true;
    while (pos < argc) {
        const name = std.mem.span(argv[pos]);
        const na: usize = @intCast(number(argv[pos+1]));
        const nr: usize = @intCast(number(argv[pos+2]));
        pos += 3;
        var args: [16]zw.Value = undefined;
        var results: [16]zw.Value = undefined;
        if (na > 16 or nr > 16 or pos+2*na > argc) @panic("Invalid adapter call");
        for (0..na) |i| {
            const kind = number(argv[pos]); const bits = number(argv[pos+1]); pos += 2;
            args[i] = switch (kind) {
                0 => .{ .i32 = @bitCast(@as(u32, @truncate(bits))) },
                1 => .{ .i64 = @bitCast(bits) },
                2 => .{ .f32 = @truncate(bits) },
                3 => .{ .f64 = bits },
                4 => .{ .v128 = bits },
                else => @panic("Unsupported adapter input kind"),
            };
        }
        if (!first) _ = printf(","); first = false;
        inst.invoke(name, args[0..na], results[0..nr]) catch |err| {
            _ = printf("{\"error\":\"%s\"}", @as([*:0]const u8, @errorName(err))); continue;
        };
        _ = printf("{\"values\":[");
        for (results[0..nr], 0..) |v, i| {
            if (i > 0) _ = printf(",");
            const kind: c_uint = switch(v) { .i32 => 0, .i64 => 1, .f32 => 2, .f64 => 3, else => @panic("Non-scalar adapter result") };
            const bits: u64 = switch(v) { .i32 => |x| @as(u32,@bitCast(x)), .i64 => |x| @bitCast(x), .f32 => |x| x, .f64 => |x| x, else => unreachable };
            _ = printf("{\"kind\":%u,\"bits\":%llu}", kind, @as(c_ulonglong,bits));
        }
        _ = printf("]}");
    }
    _ = printf("]}"); return 0;
}
'''

F02_C = r'''
#include <wasm.h>
#include <navor.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#define NEED(x) do { if (!(x)) { fprintf(stderr,"Adapter prerequisite failed at line %d: %s\n",__LINE__,#x); exit(70); } } while(0)
extern int f02_zig(const unsigned char*, size_t, int, size_t, char**);
static int32_t events[1024]; static size_t nevents;
static wasm_trap_t *observe(const wasm_val_vec_t *args, wasm_val_vec_t *results) {
    NEED(args->size==1 && args->data[0].kind==WASM_I32 && results->size==0 && nevents<1024);
    events[nevents++]=args->data[0].of.i32; return NULL;
}
static uint64_t number(const char *s) { char *end; uint64_t n=strtoull(s,&end,10); NEED(*s && !*end); return n; }
static int named(const wasm_name_t *n,const char *s) { return n->size==strlen(s) && !memcmp(n->data,s,n->size); }
static void value(const wasm_val_t *v) {
    uint64_t bits=0; uint32_t small=0;
    switch(v->kind) {
      case WASM_I32: bits=(uint32_t)v->of.i32; break;
      case WASM_I64: bits=(uint64_t)v->of.i64; break;
      case WASM_F32: memcpy(&small,&v->of.f32,4); bits=small; break;
      case WASM_F64: memcpy(&bits,&v->of.f64,8); break;
      default: NEED(0);
    }
    printf("{\"kind\":%u,\"bits\":%llu}",v->kind,(unsigned long long)bits);
}
int f02_main(int argc, char **argv) {
    NEED(argc>=6); int mode=(int)number(argv[2]); int32_t seed=(int32_t)number(argv[4]); size_t memlen=number(argv[5]);
    FILE *f=fopen(argv[3],"rb"); NEED(f); NEED(!fseek(f,0,SEEK_END)); long len=ftell(f); NEED(len>=0); rewind(f);
    unsigned char *data=malloc((size_t)len+1); NEED(data); NEED(fread(data,1,(size_t)len,f)==(size_t)len); NEED(!fclose(f));
    if(!strcmp(argv[1],"zig")) { int rc=f02_zig(data,(size_t)len,mode,(size_t)argc-6,argv+6); free(data); return rc; }
    NEED(!strcmp(argv[1],"c"));
    wasm_engine_t *e=wasm_engine_new(); NEED(e); wasm_store_t *s=wasm_store_new(e); NEED(s);
    wasm_byte_vec_t bytes={(size_t)len,(char*)data}; wasm_module_t *m=wasm_module_new(s,&bytes); NEED(m); free(data);
    wasm_importtype_vec_t types; wasm_module_imports(m,&types);
    wasm_extern_t **import_storage=calloc(types.size ? types.size : 1,sizeof(*import_storage)); NEED(import_storage);
    wasm_extern_vec_t imports={types.size,import_storage};
    for(size_t i=0;i<types.size;i++) {
        const wasm_externtype_t *t=wasm_importtype_type(types.data[i]);
        if(wasm_externtype_kind(t)==WASM_EXTERN_GLOBAL) {
            const wasm_globaltype_t *gt=wasm_externtype_as_globaltype_const(t);
            NEED(wasm_valtype_kind(wasm_globaltype_content(gt))==WASM_I32);
            wasm_val_t v={.kind=WASM_I32,.of.i32=seed}; wasm_global_t *g=wasm_global_new(s,gt,&v); NEED(g);
            imports.data[i]=wasm_global_as_extern(g);
        } else {
            NEED(wasm_externtype_kind(t)==WASM_EXTERN_FUNC);
            const wasm_functype_t *ft=wasm_externtype_as_functype_const(t);
            NEED(wasm_functype_params(ft)->size==1 && wasm_functype_results(ft)->size==0);
            NEED(wasm_valtype_kind(wasm_functype_params(ft)->data[0])==WASM_I32);
            wasm_func_t *fn=wasm_func_new(s,ft,observe); NEED(fn); imports.data[i]=wasm_func_as_extern(fn);
        }
    }
    wasm_trap_t *trap=NULL;
    wasm_instance_t *inst=navor_instance_new_ex(s,m,&imports,&trap,mode);
    printf("{\"created\":%s",inst?"true":"false");
    if(!inst) { printf(",\"trap\":%d",navor_trap_kind(trap)); if(trap) wasm_trap_delete(trap); }
    else {
        NEED(!trap);
        wasm_exporttype_vec_t names; wasm_module_exports(m,&names);
        wasm_extern_vec_t exports; wasm_instance_exports(inst,&exports); NEED(exports.size==names.size);
        printf(",\"start_events\":%zu,\"calls\":[",nevents);
        int pos=6,first=1;
        while(pos<argc) {
            NEED(pos+3<=argc); const char *name=argv[pos++]; size_t na=number(argv[pos++]),nr=number(argv[pos++]);
            NEED(na<=16 && nr<=16 && pos+(int)(na*2)<=argc);
            wasm_val_t av[16]={0},rv[16]={0};
            for(size_t i=0;i<na;i++) {
                av[i].kind=(wasm_valkind_t)number(argv[pos++]); uint64_t bits=number(argv[pos++]); uint32_t small=(uint32_t)bits;
                switch(av[i].kind) {
                  case WASM_I32: memcpy(&av[i].of.i32,&small,4); break;
                  case WASM_I64: memcpy(&av[i].of.i64,&bits,8); break;
                  case WASM_F32: memcpy(&av[i].of.f32,&small,4); break;
                  case WASM_F64: memcpy(&av[i].of.f64,&bits,8); break;
                  default: NEED(0);
                }
            }
            wasm_func_t *fn=NULL;
            for(size_t i=0;i<names.size;i++) if(named(wasm_exporttype_name(names.data[i]),name)) fn=wasm_extern_as_func(exports.data[i]);
            NEED(fn); wasm_val_vec_t args={na,av},results={nr,rv};
            trap=wasm_func_call(fn,&args,&results);
            if(!first) putchar(','); first=0;
            if(trap) { printf("{\"trap\":%d}",navor_trap_kind(trap)); wasm_trap_delete(trap); trap=NULL; }
            else { printf("{\"values\":["); for(size_t i=0;i<nr;i++) { if(i) putchar(','); value(&rv[i]); wasm_val_delete(&rv[i]); } printf("]}"); }
        }
        printf("]");
        if(memlen) {
            wasm_memory_t *memory=NULL;
            for(size_t i=0;i<names.size;i++) if(named(wasm_exporttype_name(names.data[i]),"memory")) memory=wasm_extern_as_memory(exports.data[i]);
            NEED(memory && wasm_memory_data_size(memory)>=memlen);
            const unsigned char *p=(const unsigned char*)wasm_memory_data(memory);
            printf(",\"memory\":\""); for(size_t i=0;i<memlen;i++) printf("%02x",p[i]); putchar('"');
        }
        wasm_extern_vec_delete(&exports); wasm_exporttype_vec_delete(&names); wasm_instance_delete(inst);
    }
    printf(",\"events\":["); for(size_t i=0;i<nevents;i++) { if(i) putchar(','); printf("%d",events[i]); } printf("]}");
    for(size_t i=0;i<imports.size;i++) {
        if(wasm_extern_kind(imports.data[i])==WASM_EXTERN_GLOBAL) wasm_global_delete(wasm_extern_as_global(imports.data[i]));
        else wasm_func_delete(wasm_extern_as_func(imports.data[i]));
    }
    free(import_storage); wasm_importtype_vec_delete(&types); wasm_module_delete(m); wasm_store_delete(s); wasm_engine_delete(e); return 0;
}
'''


class F02Driver:
    def __init__(self, compiler, directory):
        self.compiler = compiler
        self.directory = directory
        self.programs = {}
        self.serial = 0

    def program(self, level):
        return self.compiler.plan.consumer('F02', level=level)

    def run(self, wat, calls, *, engine='interp', api='c', level='v3_0', seed=7, memory=0):
        assert engine in ('interp', 'jit'), engine
        assert api in ('c', 'zig'), api
        assert memory >= 0 and (not memory or api == 'c'), (api, memory)
        binary = self.compiler.wat(wat)
        assert self.compiler.standard_valid(binary), wat
        self.serial += 1
        path = self.directory / f'guest-{self.serial}.wasm'
        path.write_bytes(binary)
        command = [self.program(level), api, '1' if engine == 'jit' else '2', path, str(seed & 0xffffffff), str(memory)]
        for name, args, count in calls:
            command.extend([name, str(len(args)), str(count)])
            for kind, bits in args:
                command.extend([str(kind), str(bits)])
        observed = run_json_adapter(command, timeout=30)
        path.with_suffix('.observation.json').write_bytes(observed.process.stdout)
        return observed.value


@pytest.fixture(scope='session')
def f02_driver(f01_driver, tmp_path_factory):
    return F02Driver(f01_driver, tmp_path_factory.mktemp('f02-consumer'))


def f02_arg(kind, value):
    """Encode a host scalar into the public value representation."""
    if kind == 2:
        bits = int.from_bytes(struct.pack('<f', value), 'little')
    elif kind == 3:
        bits = int.from_bytes(struct.pack('<d', value), 'little')
    else:
        bits = value & ((1 << (32 if kind == 0 else 64)) - 1)
    return kind, bits


def f02_values(*pairs):
    return {'values': [{'kind': kind, 'bits': bits} for kind, bits in (f02_arg(k, v) for k, v in pairs)]}


def consumer_sources():
    return {'F02': (F02_ZIG, F02_C, ('v1_0', 'v2_0', 'v3_0'))}
