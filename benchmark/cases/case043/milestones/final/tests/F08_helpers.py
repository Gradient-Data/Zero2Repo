# feature: F08
"""Preview1 guests driven only through public C/Zig embedding and CLI entries.

The adapter writes observations to a separate JSON file so actual guest stdout
and stderr remain independent byte streams. Memory is read through public views;
the Python decoder implements the preview1 pointer/string ABI, not host logic.
Unavailable per-instance C input/capture controls are recorded in the ledger.
"""
import json
import os
import struct

import pytest

from F01_helpers import F01_BUILD, f01_driver
from F02_helpers import F02_C, F02_ZIG
from F03_helpers import F03_C, F03_ZIG
from _helpers import build_outputs, run_process, parse_json


F08_C = r'''
#include <wasi.h>
extern int f08_zig(const unsigned char*,size_t,int,int,char**);
extern int f08_capture(const unsigned char*,size_t,const unsigned char*,size_t,uint64_t,int);
static FILE *f8_report;
static int f8_first=1;
static int32_t f8_seen[64][4];
static size_t f8_nseen;
void f8_begin(void) { if(!f8_first) fputc(',',f8_report); f8_first=0; fputc('{',f8_report); }
void f8_error(const char *error) { fprintf(f8_report,"\"error\":\"%s\",",error); }
void f8_result(const int32_t *v,size_t n) {
    fputs("\"values\":[",f8_report);
    for(size_t i=0;i<n;i++) { if(i) fputc(',',f8_report); fprintf(f8_report,"%u",(uint32_t)v[i]); }
    fputs("],",f8_report);
}
void f8_end(const unsigned char *mem,size_t len,int has_code,uint32_t code) {
    fputs("\"exit\":",f8_report); if(has_code) fprintf(f8_report,"%u",code); else fputs("null",f8_report);
    fputs(",\"memory\":\"",f8_report);
    for(size_t i=0;i<len;i++) fprintf(f8_report,"%02x",mem[i]);
    fputs("\"}",f8_report);
}
void f8_captured(int code,const unsigned char *out,size_t nout,const unsigned char *err,size_t nerr) {
    fprintf(f8_report,"\"status\":%d,\"stdout\":\"",code);
    for(size_t i=0;i<nout;i++) fprintf(f8_report,"%02x",out[i]);
    fputs("\",\"stderr\":\"",f8_report);
    for(size_t i=0;i<nerr;i++) fprintf(f8_report,"%02x",err[i]);
    fputs("\"}",f8_report);
}
static wasm_trap_t *f8_override(const wasm_val_vec_t *a,wasm_val_vec_t *r) {
    NEED(a->size==4 && r->size==1 && f8_nseen<64);
    for(size_t i=0;i<4;i++) { NEED(a->data[i].kind==WASM_I32); f8_seen[f8_nseen][i]=a->data[i].of.i32; }
    f8_nseen++;
    r->data[0]=(wasm_val_t){.kind=WASM_I32,.of.i32=a->data[0].of.i32*11+a->data[2].of.i32};
    return NULL;
}
int f08_main(int argc,char **argv) {
    NEED(argc>=6); int mode=(int)number(argv[2]);
    wasm_byte_vec_t bytes=f3_bytes(argv[3]); f8_report=fopen(argv[4],"wb"); NEED(f8_report);
    fputs("{\"calls\":[",f8_report);
    if(!strcmp(argv[1],"capture")) {
        NEED(argc==7); wasm_byte_vec_t input=f3_bytes(argv[5]);
        NEED(f08_capture((const unsigned char*)bytes.data,bytes.size,(const unsigned char*)input.data,input.size,number(argv[6]),mode)==0);
        wasm_byte_vec_delete(&input);
    } else if(!strcmp(argv[1],"zig")) {
        NEED(f08_zig((const unsigned char*)bytes.data,bytes.size,mode,argc-5,argv+5)==0);
    } else {
        NEED(!strcmp(argv[1],"c"));
        wasm_engine_t *e=wasm_engine_new(); NEED(e); wasm_store_t *s=wasm_store_new(e); NEED(s);
        wasm_module_t *m=wasm_module_new(s,&bytes); NEED(m);
        F3Instance instances[8]={0}; size_t count=0; int pos=5;
        while(pos<argc) {
            const char *action=argv[pos++];
            if(!strcmp(action,"new")) {
                NEED(pos+2<=argc && count<8); int override=(int)number(argv[pos++]); size_t na=number(argv[pos++]);
                NEED(pos+(int)na<argc); const char **args=(const char**)argv+pos; pos+=(int)na;
                size_t ne=number(argv[pos++]); NEED(ne<=32 && pos+(int)(2*ne)<argc);
                const char *keys[32],*vals[32]; for(size_t i=0;i<ne;i++) { keys[i]=argv[pos++]; vals[i]=argv[pos++]; }
                navor_wasi_config_t *cfg=navor_wasi_config_new(); NEED(cfg);
                navor_wasi_config_set_args(cfg,na,args); navor_wasi_config_set_envs(cfg,ne,keys,vals);
                size_t nd=number(argv[pos++]); NEED(nd<=32 && pos+(int)(2*nd)<=argc);
                for(size_t i=0;i<nd;i++) {
                    const char *host=argv[pos++], *guest=argv[pos++];
                    NEED(navor_wasi_config_preopen_dir(cfg,host,guest));
                }
                navor_wasi_config_inherit_stdio(cfg); navor_store_set_wasi(s,cfg);
                wasm_extern_t **import_storage=NULL; wasm_extern_vec_t imports={0,NULL}; wasm_func_t *host=NULL;
                if(override) {
                    wasm_importtype_vec_t types; wasm_module_imports(m,&types);
                    import_storage=calloc(types.size ? types.size : 1,sizeof(*import_storage)); NEED(import_storage);
                    imports=(wasm_extern_vec_t){types.size,import_storage};
                    for(size_t i=0;i<types.size;i++) {
                        imports.data[i]=NULL;
                        if(named(wasm_importtype_name(types.data[i]),"fd_write")) {
                            NEED(!host); const wasm_functype_t *ft=wasm_externtype_as_functype_const(wasm_importtype_type(types.data[i])); NEED(ft);
                            host=wasm_func_new(s,ft,f8_override); NEED(host); imports.data[i]=wasm_func_as_extern(host);
                        }
                    }
                    NEED(host); wasm_importtype_vec_delete(&types);
                }
                wasm_trap_t *trap=NULL; instances[count]=f3_instance(s,m,&imports,mode,&trap); NEED(instances[count].instance && !trap); count++;
                free(import_storage); if(host) wasm_func_delete(host);
            } else {
                NEED(!strcmp(action,"call") && pos+4<=argc);
                size_t slot=number(argv[pos++]); const char *name=argv[pos++]; size_t na=number(argv[pos++]);
                NEED(slot<count && na<=16 && pos+(int)na<argc); wasm_val_t av[16]={0},rv[16]={0};
                for(size_t i=0;i<na;i++) av[i]=(wasm_val_t){.kind=WASM_I32,.of.i32=(int32_t)number(argv[pos++])};
                size_t nr=number(argv[pos++]); NEED(nr<=16);
                wasm_func_t *fn=wasm_extern_as_func(f3_export(&instances[slot],name)); NEED(fn);
                wasm_val_vec_t args={na,av},res={nr,rv}; wasm_trap_t *trap=wasm_func_call(fn,&args,&res);
                uint32_t code=0; int exited=navor_store_wasi_exit_code(s,&code);
                f8_begin(); fprintf(f8_report,"\"trapped\":%s,",trap?"true":"false");
                if(trap) { fprintf(f8_report,"\"trap\":%d,",navor_trap_kind(trap)); wasm_trap_delete(trap); }
                else { int32_t vals[16]; for(size_t i=0;i<nr;i++) { NEED(rv[i].kind==WASM_I32); vals[i]=rv[i].of.i32; } f8_result(vals,nr); }
                wasm_memory_t *mem=wasm_extern_as_memory(f3_export(&instances[slot],"memory")); NEED(mem && wasm_memory_data_size(mem)>=4096);
                f8_end((const unsigned char*)wasm_memory_data(mem),4096,exited,code);
            }
        }
        for(size_t i=0;i<count;i++) f3_drop(&instances[i]);
        wasm_module_delete(m); wasm_store_delete(s); wasm_engine_delete(e);
    }
    fputs("],\"callbacks\":[",f8_report);
    for(size_t i=0;i<f8_nseen;i++) { if(i) fputc(',',f8_report); fprintf(f8_report,"[%d,%d,%d,%d]",f8_seen[i][0],f8_seen[i][1],f8_seen[i][2],f8_seen[i][3]); }
    fputs("]}",f8_report); NEED(!fclose(f8_report)); wasm_byte_vec_delete(&bytes); return 0;
}
'''

F08_ZIG = r'''
extern fn f08_main(c_int,[*][*:0]u8) c_int;
extern fn f8_begin() void;
extern fn f8_error([*:0]const u8) void;
extern fn f8_result([*]const i32,usize) void;
extern fn f8_end([*]const u8,usize,c_int,u32) void;
extern fn f8_captured(c_int,[*]const u8,usize,[*]const u8,usize) void;
pub export fn f08_capture(data:[*]const u8,len:usize,input:[*]const u8,ninput:usize,cap:u64,mode:c_int) c_int {
    const alloc=std.heap.c_allocator;
    var threaded=std.Io.Threaded.init(alloc,.{}); defer threaded.deinit();
    var out:std.ArrayList(u8)=.empty; defer out.deinit(alloc);
    var err:std.ArrayList(u8)=.empty; defer err.deinit(alloc);
    f8_begin();
    const code=zw.cli.run.runWasmCapturedFull(alloc,threaded.io(),data[0..len],&.{},&out,&err,
        .{.bytes=input[0..ninput]},null,&.{},&.{},&.{},null,
        .{.max_output_bytes=cap,.engine=if(mode==1) .jit else .interp}) catch |failure| {
            f8_error(@errorName(failure)); f8_captured(-1,out.items.ptr,out.items.len,err.items.ptr,err.items.len); return 0;
        };
    f8_captured(code,out.items.ptr,out.items.len,err.items.ptr,err.items.len); return 0;
}
pub export fn f08_zig(data:[*]const u8,len:usize,mode:c_int,argc:c_int,argv:[*][*:0]u8) c_int {
    f8Zig(data[0..len],mode,@intCast(argc),argv) catch |err| { _=printf("Adapter error: %s\n",@as([*:0]const u8,@errorName(err))); return 70; }; return 0;
}
fn f8Zig(data:[]const u8,mode:c_int,argc:usize,argv:[*][*:0]u8) !void {
    var eng=try zw.Engine.init(std.heap.c_allocator,.{}); defer eng.deinit();
    var m=try eng.compile(data); defer m.deinit();
    var linker=zw.Linker.init(&eng); defer linker.deinit();
    if(argc<4 or !std.mem.eql(u8,std.mem.span(argv[0]),"new") or number(argv[1])!=0) return error.BadAdapterConfig;
    const Config=@typeInfo(@TypeOf(zw.Linker.defineWasi)).@"fn".params[1].type.?;
    var cfg:Config=.{}; var args:[32][]const u8=undefined; var envs:[32]std.meta.Elem(@FieldType(Config, "envs"))=undefined;
    const na:usize=@intCast(number(argv[2])); if(na>32 or 3+na>=argc) return error.BadAdapterArgs;
    for(0..na) |i| args[i]=std.mem.span(argv[3+i]); cfg.args=args[0..na];
    var pos=3+na; const ne:usize=@intCast(number(argv[pos])); pos+=1;
    if(ne>32 or pos+2*ne>argc) return error.BadAdapterEnv;
    for(0..ne) |i| { envs[i]=.{.name=std.mem.span(argv[pos]),.value=std.mem.span(argv[pos+1])}; pos+=2; } cfg.envs=envs[0..ne];
    if(pos>=argc) return error.BadAdapterPreopens;
    const nd:usize=@intCast(number(argv[pos])); pos+=1;
    // This adapter's Zig path only drives argument/environment configurations.
    // Consume the shared empty directory field; never ignore a supplied grant.
    if(nd!=0) return error.UnsupportedAdapterPreopens;
    try linker.defineWasi(cfg);
    var inst=try linker.instantiate(&m,.{.engine=if(mode==1) .jit else .interp}); defer inst.deinit();
    while(pos<argc) {
        if(!std.mem.eql(u8,std.mem.span(argv[pos]),"call") or number(argv[pos+1])!=0) return error.BadAdapterCall;
        const name=std.mem.span(argv[pos+2]); const n:usize=@intCast(number(argv[pos+3])); pos+=4;
        if(n>16 or pos+n>=argc) return error.BadAdapterArity;
        var av:[16]zw.Value=undefined; var rv:[16]zw.Value=undefined;
        for(0..n) |i| { av[i]=.{.i32=@bitCast(@as(u32,@truncate(number(argv[pos]))))}; pos+=1; }
        const nr:usize=@intCast(number(argv[pos])); pos+=1; if(nr>16) return error.BadAdapterArity;
        f8_begin(); var failed=false;
        inst.invoke(name,av[0..n],rv[0..nr]) catch |err| { failed=true; f8_error(@errorName(err)); };
        if(!failed) { var vals:[16]i32=undefined; for(0..nr) |i| vals[i]=rv[i].i32; f8_result(&vals,nr); }
        const mem=inst.memory() orelse return error.MissingMemory; const bytes=try mem.sliceAt(0,4096);
        const code=inst.wasiExitCode(); f8_end(bytes.ptr,bytes.len,if(code!=null) 1 else 0,code orelse 0);
    }
}
'''

F08_CLI_BUILD = r'''
const std = @import("std");
pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});
    const dependency = b.dependency("navor", .{
        .target = target, .optimize = optimize, .wasi = "p3",
        .wasm = "v3_0", .@"compiler-rt" = true,
    });
    b.installArtifact(dependency.artifact("navor"));
}
'''


class F08Driver:
    def __init__(self, compiler, directory):
        self.compiler = compiler
        self.directory = directory
        self.executable = None
        self.cli_executable = None
        self.serial = 0

    def program(self):
        return self.compiler.plan.consumer('F08')

    def guest(self, source):
        binary = self.compiler.wat(source)
        assert self.compiler.standard_valid(binary), source
        self.serial += 1
        path = self.directory / f'guest-{self.serial}.wasm'
        path.write_bytes(binary)
        return path

    def run(self, source, actions, *, api='c', engine='interp', stdin=b''):
        assert api in ('c','zig') and engine in ('interp','jit')
        path = self.guest(source)
        report = path.with_suffix('.json')
        command = [self.program(),api,'1' if engine=='jit' else '2',path,report]
        for action in actions:
            command.extend(map(str,action))
        result = run_process(command, input_bytes=stdin, timeout=30)
        path.with_suffix('.stdout').write_bytes(result.stdout)
        path.with_suffix('.stderr').write_bytes(result.stderr)
        assert result.returncode == 0, (result.returncode,result.stdout,result.stderr)
        return parse_json(report.read_bytes()), result

    def cli(self, source, *, args=(), envs=(), stdin=b'', engine='interp'):
        self.cli_executable = self.compiler.plan.cli(
            consumer='F08', wasm='v3_0', wasi='p3', engine='both', optimize='ReleaseSafe')[0]
        path = self.guest(source)
        command = [self.cli_executable,'run','--engine',engine]
        for key,value in envs:
            command.extend(['--env',key+'='+value])
        command.extend([path,*args])
        result = run_process(command,input_bytes=stdin,timeout=30)
        path.with_suffix('.stdout').write_bytes(result.stdout)
        path.with_suffix('.stderr').write_bytes(result.stderr)
        return path,result

    def capture(self, source, *, stdin=b'', allowance=4096, engine='interp'):
        assert engine in ('interp','jit') and allowance >= 0
        path = self.guest(source)
        input_path = path.with_suffix('.input')
        input_path.write_bytes(stdin)
        report = path.with_suffix('.json')
        result = run_process([self.program(),'capture','1' if engine=='jit' else '2',
                              path,report,input_path,str(allowance)],timeout=30)
        path.with_suffix('.stdout').write_bytes(result.stdout)
        path.with_suffix('.stderr').write_bytes(result.stderr)
        assert result.returncode == 0, (result.returncode,result.stdout,result.stderr)
        observed = parse_json(report.read_bytes())
        assert len(observed['calls']) == 1, observed
        return observed['calls'][0]


@pytest.fixture(scope='session')
def f08_driver(f01_driver,tmp_path_factory):
    return F08Driver(f01_driver,tmp_path_factory.mktemp('f08-consumer'))


def f08_new(args=(), envs=(), *, preopens=(), override=False):
    return ['new',int(override),len(args),*args,len(envs),*(x for pair in envs for x in pair),
            len(preopens),*(x for pair in preopens for x in pair)]


def f08_call(name, args=(), results=1, *, slot=0):
    return ['call',slot,name,len(args),*(x & 0xffffffff for x in args),results]


def f08_ok(call, values):
    assert 'error' not in call and 'trap' not in call, call
    assert call['values'] == list(values), call
    assert call['exit'] is None, call


def f08_context(call):
    """Decode preview1 counts, byte sizes, pointer arrays and NUL strings."""
    f08_ok(call,[0])
    mem = bytes.fromhex(call['memory'])
    argc,abytes,envc,ebytes = struct.unpack_from('<4I',mem,0)
    def vector(count, size, pointers, start, end):
        assert count <= (start-pointers)//4 and size <= end-start
        strings = []
        for i in range(count):
            ptr, = struct.unpack_from('<I',mem,pointers+4*i)
            assert start <= ptr < start+size
            stop = mem.index(b'\0',ptr,start+size)
            strings.append(mem[ptr:stop])
        assert sum(len(x)+1 for x in strings) == size
        return strings
    return vector(argc,abytes,64,512,1536),vector(envc,ebytes,256,2048,4096)


F08_IMPORTS = '''
 (import "wasi_snapshot_preview1" "args_sizes_get" (func $as (param i32 i32) (result i32)))
 (import "wasi_snapshot_preview1" "args_get" (func $ag (param i32 i32) (result i32)))
 (import "wasi_snapshot_preview1" "environ_sizes_get" (func $es (param i32 i32) (result i32)))
 (import "wasi_snapshot_preview1" "environ_get" (func $eg (param i32 i32) (result i32)))
 (import "wasi_snapshot_preview1" "fd_write" (func $write (param i32 i32 i32 i32) (result i32)))
 (import "wasi_snapshot_preview1" "fd_read" (func $read (param i32 i32 i32 i32) (result i32)))
 (import "wasi_snapshot_preview1" "proc_exit" (func $exit (param i32)))
'''

F08_CONTEXT_BODY = '''
 (func (export "context") (result i32)
   i32.const 0 i32.const 4 call $as
   i32.const 64 i32.const 512 call $ag i32.or
   i32.const 8 i32.const 12 call $es i32.or
   i32.const 256 i32.const 2048 call $eg i32.or)
'''

F08_WRITE_ALL = '''
 (func $write_all (param $fd i32) (param $vec i32) (param $count i32) (param $out i32) (result i32)
  (local $errno i32) (local $n i32) (local $total i32) (local $size i32)
  (local $i i32) (local $v i32) (local $length i32)
  local.get $count i32.const 8 i32.mul local.set $size
  i32.const 60000 local.get $vec local.get $size memory.copy
  loop $next
   local.get $fd local.get $vec local.get $count local.get $out call $write
   local.tee $errno if local.get $errno return end
   local.get $out i32.load local.set $n
   local.get $total local.get $n i32.add local.set $total
   i32.const 60000 local.set $vec
   i32.const 0 local.set $i
   block $adjusted loop $adjust
    local.get $i local.get $count i32.ge_u br_if $adjusted
    local.get $vec local.get $i i32.const 8 i32.mul i32.add local.set $v
    local.get $v i32.load offset=4 local.set $length
    local.get $n local.get $length i32.lt_u if
      local.get $v local.get $v i32.load local.get $n i32.add i32.store
      local.get $v local.get $length local.get $n i32.sub i32.store offset=4
      i32.const 0 local.set $n br $adjusted
    end
    local.get $n local.get $length i32.sub local.set $n
    local.get $v i32.const 0 i32.store offset=4
    local.get $i i32.const 1 i32.add local.set $i br $adjust
   end end
   local.get $n if unreachable end
   local.get $i local.get $count i32.eq if
     local.get $out local.get $total i32.store i32.const 0 return
   end
   local.get $out i32.load i32.eqz if unreachable end
   br $next
  end unreachable)
'''

F08_GUEST = '(module' + F08_IMPORTS + '''
 (memory (export "memory") 1)
''' + F08_CONTEXT_BODY + F08_WRITE_ALL + '''
 (func (export "exit") (param i32) local.get 0 call $exit i32.const 96 i32.const 1 i32.store unreachable)
 (func (export "fault") unreachable)
 (func (export "normal") (param i32) (result i32) local.get 0 i32.const 3 i32.mul)
 (func (export "write") (param $fd i32) (param $ptr i32) (param $len i32) (result i32 i32)
   i32.const 32 local.get $ptr i32.store
   i32.const 36 local.get $len i32.store
   local.get $fd i32.const 32 i32.const 1 i32.const 40 call $write_all
   i32.const 40 i32.load)
 (func (export "first_arg_write") (param $fd i32) (param $len i32) (result i32 i32)
   i32.const 32 i32.const 64 i32.load i32.store
   i32.const 36 local.get $len i32.store
   local.get $fd i32.const 32 i32.const 1 i32.const 40 call $write_all
   i32.const 40 i32.load)
 (func (export "raw_write") (param i32 i32 i32 i32) (result i32)
   local.get 0 local.get 1 local.get 2 local.get 3 call $write)
 (func (export "raw_read") (param i32 i32 i32 i32) (result i32)
   local.get 0 local.get 1 local.get 2 local.get 3 call $read)
 (func (export "prepare") (param i32 i32)
   i32.const 32 local.get 0 i32.store i32.const 36 local.get 1 i32.store)
 (data (i32.const 128) "out\\00\\ff-A")
 (data (i32.const 160) "err\\0a-B")
)'''


def consumer_sources():
    return {'F08': (F02_ZIG.replace('return f02_main(argc, argv);', 'return f08_main(argc, argv);') + F03_ZIG + F08_ZIG, F02_C + F03_C + F08_C, ('v3_0',))}
