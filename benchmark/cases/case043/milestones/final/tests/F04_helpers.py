# feature: F04
"""Live-state consumers using only public APIs, with lossless JSON observations.

Reuse prior build, WAT, scalar, instance and invocation mechanisms. Commands are
explicit operations; errors remain errors, and references are observed through
public identity comparison (C) or the opaque host token (Zig).
"""
import json
import os
import pytest
from F01_helpers import F01_BUILD, f01_driver
from F02_helpers import F02_C, F02_ZIG, f02_arg, f02_values
from F03_helpers import F03_C, F03_ZIG
from _helpers import build_outputs, run_json_adapter

F04_ZIG = r'''
extern fn f04_main(c_int, [*][*:0]u8) c_int;
fn f4Value(v: zw.Value) void {
    switch(v) {
        .externref => |r| { if(r) |n| { _=printf("{\"ref\":%llu}",@as(c_ulonglong,n)); } else { _=printf("{\"ref\":null}"); } },
        else => {
            const k:c_uint=switch(v) { .i32=>0,.i64=>1,.f32=>2,.f64=>3,else=>@panic("Unsupported value") };
            const bits:u64=switch(v) { .i32=>|x| @as(u32,@bitCast(x)),.i64=>|x| @bitCast(x),.f32=>|x| x,.f64=>|x| x,else=>unreachable };
            _=printf("{\"kind\":%u,\"bits\":%llu}",k,@as(c_ulonglong,bits));
        },
    }
}
fn f4Input(k:u64,b:u64) zw.Value {
    return switch(k) { 0=>.{.i32=@bitCast(@as(u32,@truncate(b)))},1=>.{.i64=@bitCast(b)},2=>.{.f32=@truncate(b)},3=>.{.f64=b},128=>.{.externref=if(b==0) null else b},else=>@panic("Invalid kind") };
}
fn f4Num(comptime T:type,mem:zw.Memory,addr:u32,write:bool,bits:u64) !void {
    const U=std.meta.Int(.unsigned,@bitSizeOf(T));
    if(write) {
        try mem.write(addr,@as(T,@bitCast(@as(U,@truncate(bits)))));
        _=printf("{\"ok\":true}");
    } else {
        const v=try mem.read(T,addr);
        _=printf("{\"bits\":%llu}",@as(c_ulonglong,@as(U,@bitCast(v))));
    }
}
fn f4Op(inst:*zw.Instance,argc:usize,argv:[*][*:0]u8,pos:*usize) !void {
    if(pos.*>=argc) return error.AdapterArguments;
    const op=std.mem.span(argv[pos.*]); pos.*+=1;
    if(std.mem.eql(u8,op,"call")) {
        const name=std.mem.span(argv[pos.*]); const na:usize=@intCast(number(argv[pos.*+1])); const nr:usize=@intCast(number(argv[pos.*+2])); pos.*+=3;
        if(na>16 or nr>16) return error.AdapterArguments;
        var a:[16]zw.Value=undefined; var r:[16]zw.Value=undefined;
        for(0..na) |i| { a[i]=f4Input(number(argv[pos.*]),number(argv[pos.*+1])); pos.*+=2; }
        try inst.invoke(name,a[0..na],r[0..nr]);
        _=printf("{\"values\":["); for(r[0..nr],0..) |v,i| { if(i>0) _=printf(","); f4Value(v); } _=printf("]}");
    } else if(std.mem.eql(u8,op,"read") or std.mem.eql(u8,op,"write")) {
        const typ=std.mem.span(argv[pos.*]); const addr:u32=@intCast(number(argv[pos.*+1])); const bits=number(argv[pos.*+2]); pos.*+=3;
        const mem=inst.memory() orelse return error.MissingMemory;
        inline for(.{i8,u8,i16,u16,i32,u32,i64,u64,f32,f64}) |T| {
            if(std.mem.eql(u8,typ,@typeName(T))) return f4Num(T,mem,addr,std.mem.eql(u8,op,"write"),bits);
        }
        return error.AdapterType;
    } else if(std.mem.eql(u8,op,"bytes") or std.mem.eql(u8,op,"put")) {
        const addr:u32=@intCast(number(argv[pos.*])); const n:u32=@intCast(number(argv[pos.*+1])); pos.*+=2;
        const text=std.mem.span(argv[pos.*]); pos.*+=1;
        const mem=inst.memory() orelse return error.MissingMemory;
        const bytes=try mem.sliceAt(addr,n);
        if(std.mem.eql(u8,op,"put")) {
            if(text.len!=n*2) return error.AdapterArguments;
            for(bytes,0..) |*v,i| v.*=try std.fmt.parseInt(u8,text[2*i..][0..2],16);
        }
        _=printf("{\"bytes\":\""); for(bytes) |v| { _=printf("%02x",@as(c_uint,v)); } _=printf("\"}");
    } else if(std.mem.eql(u8,op,"msize")) {
        const m=inst.memory() orelse return error.MissingMemory; _=printf("{\"size\":%u}",m.size());
    } else if(std.mem.eql(u8,op,"mgrow")) {
        const n:u32=@intCast(number(argv[pos.*])); pos.*+=1;
        const m=inst.memory() orelse return error.MissingMemory;
        if(m.grow(n)) |old| { _=printf("{\"old\":%u}",old); } else { _=printf("{\"old\":null}"); }
    } else if(std.mem.eql(u8,op,"global") or std.mem.eql(u8,op,"gset") or std.mem.eql(u8,op,"gfind")) {
        const name=std.mem.span(argv[pos.*]); pos.*+=1;
        const g=inst.global(name);
        if(std.mem.eql(u8,op,"gfind")) { _=printf("{\"present\":%s}",@as([*:0]const u8,if(g!=null) "true" else "false")); return; }
        const live=g orelse return error.MissingGlobal;
        if(std.mem.eql(u8,op,"gset")) { const v=f4Input(number(argv[pos.*]),number(argv[pos.*+1])); pos.*+=2; try live.set(v); }
        f4Value(live.get());
    } else {
        const name=std.mem.span(argv[pos.*]); pos.*+=1; const t=inst.table(name);
        if(std.mem.eql(u8,op,"tfind")) { _=printf("{\"present\":%s}",@as([*:0]const u8,if(t!=null) "true" else "false")); return; }
        const live=t orelse return error.MissingTable;
        if(std.mem.eql(u8,op,"tsize")) { _=printf("{\"size\":%u}",live.size()); return; }
        const idx:u32=@intCast(number(argv[pos.*])); pos.*+=1;
        if(std.mem.eql(u8,op,"tget")) { f4Value(try live.get(idx)); return; }
        if(std.mem.eql(u8,op,"tscan")) {
            const count:u32=@intCast(number(argv[pos.*])); pos.*+=1;
            const refs=try std.heap.c_allocator.alloc(zw.Value,count);
            defer std.heap.c_allocator.free(refs);
            for(refs,0..) |*v,j| v.*=try live.get(idx+@as(u32,@intCast(j)));
            _=printf("{\"refs\":[");
            for(refs,0..) |v,j| { if(j>0) _=printf(","); f4Value(v); }
            _=printf("]}"); return;
        }
        const v=f4Input(128,number(argv[pos.*])); pos.*+=1;
        if(std.mem.eql(u8,op,"tset")) { try live.set(idx,v); }
        else if(std.mem.eql(u8,op,"tgrow")) { try live.grow(idx,v); }
        else return error.AdapterOperation;
        _=printf("{\"ok\":true}");
    }
}
pub export fn f04_zig(data:[*]const u8,len:usize,mode:c_int,argc:usize,argv:[*][*:0]u8) c_int {
    f4Run(data[0..len],mode,argc,argv) catch |err| { _=printf("adapter failure: %s",@as([*:0]const u8,@errorName(err))); return 70; }; return 0;
}
fn f4Run(data:[]const u8,mode:c_int,argc:usize,argv:[*][*:0]u8) !void {
    var eng=try zw.Engine.init(std.heap.c_allocator,.{}); defer eng.deinit();
    var mod=try eng.compile(data); defer mod.deinit();
    var inst=try mod.instantiate(.{.engine=if(mode==1) .jit else .interp}); defer inst.deinit();
    _=printf("["); var pos:usize=0; var first=true;
    while(pos<argc) {
        if(!first) _=printf(","); first=false;
        f4Op(&inst,argc,argv,&pos) catch |err| {
            switch(err) {
                error.AdapterArguments, error.AdapterType, error.AdapterOperation,
                error.MissingMemory, error.MissingGlobal, error.MissingTable,
                error.InvalidCharacter, error.Overflow => return err,
                else => _=printf("{\"error\":\"%s\"}",@as([*:0]const u8,@errorName(err))),
            }
        };
    } _=printf("]");
}
'''

F04_C = r'''
extern int f04_zig(const unsigned char*,size_t,int,size_t,char**);
static void f4_ref(wasm_ref_t *r,wasm_foreign_t **tokens,F3Instance *p) {
    printf("{\"same\":["); for(int i=0;i<2;i++) { if(i) putchar(','); printf("%s",wasm_ref_same(r,wasm_foreign_as_ref(tokens[i]))?"true":"false"); } printf("],\"null\":");
    wasm_val_t arg={.kind=WASM_EXTERNREF,.of.ref=r}; f3_call(p,"isnull",&arg,1,1); putchar('}');
}
static wasm_val_t f4_input(int kind,uint64_t bits,wasm_foreign_t **tokens) {
    wasm_val_t v={.kind=kind}; uint32_t small=(uint32_t)bits;
    switch(kind) {
    case WASM_I32: memcpy(&v.of.i32,&small,4); break;
    case WASM_I64: memcpy(&v.of.i64,&bits,8); break;
    case WASM_F32: memcpy(&v.of.f32,&small,4); break;
    case WASM_F64: memcpy(&v.of.f64,&bits,8); break;
    case WASM_EXTERNREF: NEED(bits<=2); v.of.ref=bits?wasm_foreign_as_ref(tokens[bits-1]):NULL; break;
    default: NEED(0);
    } return v;
}
static void f4_call_ref(wasm_func_t *fn,wasm_val_t *args,size_t na,size_t nr) {
    NEED(fn && nr<=16); wasm_val_t out[16]={0}; wasm_val_vec_t av={na,args},rv={nr,out};
    wasm_trap_t *trap=wasm_func_call(fn,&av,&rv);
    if(trap) { printf("{\"trap\":%d}",navor_trap_kind(trap)); wasm_trap_delete(trap); }
    else { printf("{\"values\":["); for(size_t i=0;i<nr;i++) { if(i) putchar(','); value(&out[i]); wasm_val_delete(&out[i]); } printf("]}"); }
}
static void f4_refs(wasm_store_t *s,wasm_module_t *m,int mode,size_t arity,size_t count) {
    wasm_extern_vec_t im={0,NULL}; wasm_trap_t *trap=NULL;
    F3Instance a=f3_instance(s,m,&im,mode,&trap),b=f3_instance(s,m,&im,mode,&trap); NEED(a.instance && b.instance && !trap);
    F3Instance *instances[]={&a,&b}; wasm_ref_t *table_refs[2]; wasm_val_t out[2][2]={0};
    wasm_func_t *fns[2][2];
    printf("{\"seeds\":[");
    for(int j=0;j<2;j++) { if(j) putchar(','); wasm_val_t seed={.kind=WASM_I32,.of.i32=j?91:23}; f3_call(instances[j],"seed",&seed,1,0); }
    printf("],\"nulls\":[");
    for(int j=0;j<2;j++) {
        F3Instance *p=instances[j]; if(j) putchar(',');
        wasm_table_t *t=wasm_extern_as_table(f3_export(p,"functions")); NEED(t);
        table_refs[j]=wasm_table_get(t,0); wasm_ref_t *null_table=wasm_table_get(t,1);
        printf("{\"table_callable\":%s",wasm_ref_as_func(null_table)?"true":"false");
        wasm_func_t *get=wasm_extern_as_func(f3_export(p,"get")); NEED(get);
        wasm_val_vec_t av={0,NULL},rv={2,out[j]}; trap=wasm_func_call(get,&av,&rv);
        NEED(!trap && out[j][0].kind==WASM_FUNCREF && out[j][1].kind==WASM_FUNCREF);
        printf(",\"result_callable\":%s}",wasm_ref_as_func(out[j][1].of.ref)?"true":"false");
        fns[j][0]=wasm_ref_as_func(table_refs[j]); fns[j][1]=wasm_ref_as_func(out[j][0].of.ref);
        if(null_table) wasm_ref_delete(null_table);
    }
    printf("],\"calls\":[");
    for(int k=0;k<2;k++) for(int j=0;j<2;j++) {
        if(k || j) putchar(',');
        wasm_val_t args[]={{.kind=WASM_I32,.of.i32=7+k},{.kind=WASM_I64,.of.i64=8589934603LL+k},{.kind=WASM_F32,.of.f32=1.5f+k},{.kind=WASM_F64,.of.f64=-2.25-k}};
        f4_call_ref(fns[j][k],args,arity,count);
    }
    printf("],\"states\":[");
    for(int j=0;j<2;j++) { if(j) putchar(','); f3_call(instances[j],"state",NULL,0,1); }
    printf("]}");
    for(int j=0;j<2;j++) { wasm_ref_delete(table_refs[j]); wasm_val_delete(&out[j][0]); wasm_val_delete(&out[j][1]); }
    f3_drop(&b); f3_drop(&a);
}
int f04_main(int argc,char **argv) {
    NEED(argc>=4); int mode=(int)number(argv[2]); wasm_byte_vec_t bytes=f3_bytes(argv[3]);
    if(!strcmp(argv[1],"zig")) { int rc=f04_zig((unsigned char*)bytes.data,bytes.size,mode,argc-4,argv+4); wasm_byte_vec_delete(&bytes); return rc; }
    wasm_engine_t *e=wasm_engine_new(); NEED(e); wasm_store_t *s=wasm_store_new(e); NEED(s);
    wasm_module_t *m=wasm_module_new(s,&bytes); NEED(m); wasm_byte_vec_delete(&bytes);
    if(!strcmp(argv[1],"refs")) f4_refs(s,m,mode,number(argv[4]),number(argv[5]));
    else {
        NEED(!strcmp(argv[1],"c")); wasm_extern_vec_t im={0,NULL}; wasm_trap_t *trap=NULL; F3Instance p=f3_instance(s,m,&im,mode,&trap); NEED(p.instance && !trap);
        wasm_foreign_t *tokens[]={wasm_foreign_new(s),wasm_foreign_new(s)}; NEED(tokens[0] && tokens[1]);
        printf("["); int pos=4,first=1;
        while(pos<argc) {
            if(!first) putchar(','); first=0; const char *op=argv[pos++];
            if(!strcmp(op,"call")) {
                const char *name=argv[pos++]; size_t na=number(argv[pos++]),nr=number(argv[pos++]); NEED(na<=16 && nr<=16);
                wasm_val_t args[16]={0},out[16]={0};
                for(size_t i=0;i<na;i++) { int k=(int)number(argv[pos++]); uint64_t bits=number(argv[pos++]); args[i]=f4_input(k,bits,tokens); }
                wasm_func_t *fn=wasm_extern_as_func(f3_export(&p,name)); NEED(fn); wasm_val_vec_t av={na,args},rv={nr,out}; trap=wasm_func_call(fn,&av,&rv);
                if(trap) { printf("{\"trap\":%d}",navor_trap_kind(trap)); wasm_trap_delete(trap); trap=NULL; }
                else { printf("{\"values\":["); for(size_t i=0;i<nr;i++) { if(i) putchar(','); if(out[i].kind==WASM_EXTERNREF) f4_ref(out[i].of.ref,tokens,&p); else value(&out[i]); wasm_val_delete(&out[i]); } printf("]}"); }
            } else if(!strcmp(op,"bytes") || !strcmp(op,"put")) {
                size_t at=number(argv[pos++]),n=number(argv[pos++]); const char *hex=argv[pos++];
                wasm_memory_t *mem=wasm_extern_as_memory(f3_export(&p,"memory")); NEED(mem && at+n<=wasm_memory_data_size(mem));
                unsigned char *b=(unsigned char*)wasm_memory_data(mem)+at;
                if(!strcmp(op,"put")) { NEED(strlen(hex)==n*2); for(size_t i=0;i<n;i++) { unsigned x; NEED(sscanf(hex+2*i,"%2x",&x)==1); b[i]=(unsigned char)x; } }
                printf("{\"bytes\":\""); for(size_t i=0;i<n;i++) printf("%02x",b[i]); printf("\"}");
            } else if(!strcmp(op,"msize") || !strcmp(op,"mgrow")) {
                wasm_memory_t *mem=wasm_extern_as_memory(f3_export(&p,"memory")); NEED(mem);
                if(!strcmp(op,"msize")) printf("{\"size\":%u}",wasm_memory_size(mem));
                else { uint32_t n=number(argv[pos++]); printf("{\"ok\":%s}",wasm_memory_grow(mem,n)?"true":"false"); }
            } else if(!strcmp(op,"global") || !strcmp(op,"gset")) {
                wasm_global_t *g=wasm_extern_as_global(f3_export(&p,argv[pos++])); NEED(g);
                if(!strcmp(op,"gset")) { int k=(int)number(argv[pos++]); uint64_t b=number(argv[pos++]); wasm_val_t v=f4_input(k,b,tokens); wasm_global_set(g,&v); }
                wasm_val_t v; wasm_global_get(g,&v); value(&v); wasm_val_delete(&v);
            } else {
                wasm_table_t *t=wasm_extern_as_table(f3_export(&p,argv[pos++])); NEED(t);
                if(!strcmp(op,"tsize")) { printf("{\"size\":%u}",wasm_table_size(t)); continue; }
                uint32_t idx=number(argv[pos++]);
                if(!strcmp(op,"tscan")) {
                    uint32_t count=number(argv[pos++]); NEED((uint64_t)idx+count<=wasm_table_size(t));
                    printf("{\"refs\":[");
                    for(uint32_t j=0;j<count;j++) { if(j) putchar(','); wasm_ref_t *r=wasm_table_get(t,idx+j); f4_ref(r,tokens,&p); if(r) wasm_ref_delete(r); }
                    printf("]}"); continue;
                }
                if(!strcmp(op,"tget")) { wasm_ref_t *r=wasm_table_get(t,idx); f4_ref(r,tokens,&p); if(r) wasm_ref_delete(r); }
                else { uint64_t token=number(argv[pos++]); NEED(token<=2); wasm_ref_t *r=token?wasm_foreign_as_ref(tokens[token-1]):NULL;
                    bool ok; if(!strcmp(op,"tset")) ok=wasm_table_set(t,idx,r); else { NEED(!strcmp(op,"tgrow")); ok=wasm_table_grow(t,idx,r); }
                    printf("{\"ok\":%s}",ok?"true":"false"); }
            }
        } putchar(']'); f3_drop(&p); wasm_foreign_delete(tokens[0]); wasm_foreign_delete(tokens[1]);
    }
    wasm_module_delete(m); wasm_store_delete(s); wasm_engine_delete(e); return 0;
}
'''

class F04Driver:
    def __init__(self, compiler, directory):
        self.compiler, self.directory = compiler, directory
        self.executable = None
        self.serial = 0

    def program(self):
        return self.compiler.plan.consumer('F04')

    def run(self, wat, operations=(), *, api='zig', engine='interp'):
        assert api in ('c','zig','refs') and engine in ('interp','jit')
        binary = self.compiler.wat(wat)
        assert self.compiler.standard_valid(binary), wat
        self.serial += 1
        path = self.directory / f'guest-{self.serial}.wasm'
        path.write_bytes(binary)
        command = [self.program(),api,'1' if engine=='jit' else '2',path]
        for op in operations:
            command.extend(map(str,op))
        result = run_json_adapter(command,timeout=30)
        path.with_suffix('.observation.json').write_bytes(result.process.stdout)
        return result.value

@pytest.fixture(scope='session')
def f04_driver(f01_driver,tmp_path_factory):
    return F04Driver(f01_driver,tmp_path_factory.mktemp('f04-consumer'))


def f04_call(name, args=(), results=0):
    return ('call',name,len(args),results,*(x for pair in args for x in pair))


def f04_ref(token, api):
    if api=='zig':
        return {'ref': token or None}
    return {'same': [token==1,token==2], 'null': f02_values((0,int(token==0)))}


def consumer_sources():
    return {'F04': (F02_ZIG.replace('return f02_main(argc, argv);', 'return f04_main(argc, argv);') + F03_ZIG + F04_ZIG, F02_C + F03_C + F04_C, ('v3_0',))}
