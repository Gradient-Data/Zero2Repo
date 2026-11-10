# feature: F07
"""Passive public-API event recorder and independent Core binary locations.

Callbacks only append their arguments; each operation drains its own events.
The consumer never calls product internals and never derives an expected trace
from the product. Existing compilation, instance, scalar and process helpers
are imported from the preceding features.
"""
import json
import os
import sys
import pytest
from F01_helpers import F01_BUILD, F01BinaryReader, f01_driver
from F02_helpers import F02_C, F02_ZIG, f02_arg, f02_values
from F03_helpers import F03_C, F03_ZIG
from F04_helpers import F04_C, F04_ZIG, f04_call
from _helpers import build_outputs, run_json_adapter, HarnessError

F07_C = r'''
typedef struct { int tag, kind, accepted; uint64_t id, old, next; uint32_t memory; } F7Event;
static F7Event f7_events[512]; static size_t f7_count;
static F7Event *f7_event(int tag,void *ctx) {
    NEED(ctx==&f7_count && f7_count<512);
    F7Event *v=&f7_events[f7_count++]; memset(v,0,sizeof(*v)); v->tag=tag; return v;
}
void f7_compile(void *ctx,size_t len,bool accepted) { (void)len; f7_event(0,ctx)->accepted=accepted; }
void f7_instantiate(void *ctx,uint64_t id) { f7_event(1,ctx)->id=id; }
void f7_trap(void *ctx,uint64_t id,int32_t kind,const char *msg,size_t len) {
    (void)msg; (void)len; F7Event *v=f7_event(2,ctx); v->id=id; v->kind=kind;
}
void f7_fuel(void *ctx,uint64_t id) { f7_event(3,ctx)->id=id; }
void f7_growth(void *ctx,uint64_t id,uint32_t index,uint64_t old,uint64_t next) {
    F7Event *v=f7_event(4,ctx); v->id=id; v->memory=index; v->old=old; v->next=next;
}
void *f7_context(void) { return &f7_count; }
void f7_flush(void) {
    printf(",\"events\":[");
    for(size_t i=0;i<f7_count;i++) {
        F7Event *v=&f7_events[i]; if(i) putchar(',');
        switch(v->tag) {
        case 0: printf("{\"event\":\"compile\",\"accepted\":%s}",v->accepted?"true":"false"); break;
        case 1: printf("{\"event\":\"instance\",\"id\":%llu}",(unsigned long long)v->id); break;
        case 2: printf("{\"event\":\"trap\",\"id\":%llu,\"kind\":%d}",(unsigned long long)v->id,v->kind); break;
        case 3: printf("{\"event\":\"fuel\",\"id\":%llu}",(unsigned long long)v->id); break;
        case 4: printf("{\"event\":\"growth\",\"id\":%llu,\"memory\":%u,\"old\":%llu,\"new\":%llu}",
          (unsigned long long)v->id,v->memory,(unsigned long long)v->old,(unsigned long long)v->next); break;
        default: NEED(0);
        }
    }
    printf("]}"); f7_count=0;
}
static void f7_hook(wasm_engine_t *e,int slot,int enabled) {
    void *ctx=f7_context();
    switch(slot) {
    case 0: navor_engine_set_compile_hook(e,enabled?f7_compile:NULL,ctx); break;
    case 1: navor_engine_set_instantiate_hook(e,enabled?f7_instantiate:NULL,ctx); break;
    case 2: navor_engine_set_trap_hook(e,enabled?f7_trap:NULL,ctx); break;
    case 3: navor_engine_set_fuel_exhausted_hook(e,enabled?f7_fuel:NULL,ctx); break;
    case 4: navor_engine_set_memory_growth_hook(e,enabled?f7_growth:NULL,ctx); break;
    default: NEED(0);
    }
}
static void f7_frame(const wasm_frame_t *f) {
    if(!f) { printf("null"); return; }
    printf("{\"function\":%u,\"module_offset\":%zu,\"function_offset\":%zu}",
      wasm_frame_func_index(f),wasm_frame_module_offset(f),wasm_frame_func_offset(f));
}
static int f7_trace_enabled;
static void f7_failure(wasm_trap_t *t) {
    NEED(t);
    if(!f7_trace_enabled) { printf("{\"trap\":%d}",navor_trap_kind(t)); wasm_trap_delete(t); return; } printf("{\"trap\":%d,\"origin\":",navor_trap_kind(t));
    wasm_frame_t *origin=wasm_trap_origin(t); f7_frame(origin); if(origin) wasm_frame_delete(origin);
    wasm_frame_vec_t trace; wasm_trap_trace(t,&trace); printf(",\"trace\":[");
    for(size_t i=0;i<trace.size;i++) { if(i) putchar(','); f7_frame(trace.data[i]); }
    printf("]}"); wasm_frame_vec_delete(&trace); wasm_trap_delete(t);
}
extern int f07_zig(int,char**);
int f07_main(int argc,char **argv) {
    NEED(argc>=5); if(!strcmp(argv[1],"zig")) return f07_zig(argc,argv);
    NEED(!strcmp(argv[1],"c")); int mode=number(argv[2]),enabled=number(argv[3]); f7_trace_enabled=number(argv[4]);
    wasm_engine_t *e=wasm_engine_new(); NEED(e); wasm_store_t *s=wasm_store_new(e); NEED(s);
    for(int i=0;i<5;i++) f7_hook(e,i,enabled);
    wasm_module_t *modules[16]={0}; F3Instance inst[16]={0};
    printf("["); int pos=5,first=1;
    while(pos<argc) {
        const char *op=argv[pos++]; if(!first) putchar(','); first=0; printf("{\"result\":");
        if(!strcmp(op,"load") || !strcmp(op,"validate")) {
            int slot=number(argv[pos++]); NEED(slot<16 && !modules[slot]);
            wasm_byte_vec_t bytes=f3_bytes(argv[pos++]);
            bool ok;
            if(!strcmp(op,"load")) { modules[slot]=wasm_module_new(s,&bytes); ok=modules[slot]!=NULL; }
            else ok=wasm_module_validate(s,&bytes);
            printf("{\"accepted\":%s}",ok?"true":"false"); wasm_byte_vec_delete(&bytes);
        } else if(!strcmp(op,"hook")) {
            int slot=number(argv[pos++]),on=number(argv[pos++]); f7_hook(e,slot,on); printf("{}");
        } else if(!strcmp(op,"standalone")) {
            wasm_limits_t limits={1,3}; wasm_memorytype_t *ty=wasm_memorytype_new(&limits);
            NEED(ty); wasm_memory_t *memory=wasm_memory_new(s,ty); NEED(memory);
            bool ok=wasm_memory_grow(memory,1);
            printf("{\"ok\":%s,\"size\":%u}",ok?"true":"false",wasm_memory_size(memory));
            wasm_memory_delete(memory); wasm_memorytype_delete(ty);
        } else if(!strcmp(op,"new") || !strcmp(op,"new-null")) {
            int slot=number(argv[pos++]),m=number(argv[pos++]),provider=atoi(argv[pos++]);
            NEED(slot<16 && m<16 && !inst[slot].instance && modules[m]);
            wasm_extern_vec_t im={0,NULL}; if(provider>=0) { NEED(provider<16 && inst[provider].instance); im=f3_bind(&inst[provider],modules[m],0); }
            wasm_trap_t *t=NULL; inst[slot]=f3_instance(s,modules[m],&im,mode,!strcmp(op,"new-null")?NULL:&t);
            printf("{\"created\":%s,\"failure\":",inst[slot].instance?"true":"false");
            if(t) f7_failure(t); else printf("null"); printf("}"); wasm_extern_vec_delete(&im);
        } else if(!strcmp(op,"hosttrap")) {
            wasm_message_t msg; wasm_byte_vec_new(&msg,16,"embedder failure");
            wasm_trap_t *t=wasm_trap_new(s,&msg); wasm_byte_vec_delete(&msg);
            printf("{\"created\":%s}",t?"true":"false"); if(t) wasm_trap_delete(t);
        } else {
            int slot=number(argv[pos++]); NEED(slot<16 && inst[slot].instance); F3Instance *p=&inst[slot];
            if(!strcmp(op,"drop")) { f3_drop(p); printf("{}"); }
            else if(!strcmp(op,"fuel")) { navor_instance_set_fuel(p->instance,number(argv[pos++])); printf("{}"); }
            else if(!strcmp(op,"unfuel")) { navor_instance_disable_fuel(p->instance); printf("{}"); }
            else if(!strcmp(op,"grow") || !strcmp(op,"size")) {
                wasm_memory_t *m=wasm_extern_as_memory(f3_export(p,argv[pos++])); NEED(m);
                if(!strcmp(op,"grow")) { uint32_t delta=number(argv[pos++]); printf("{\"ok\":%s}",wasm_memory_grow(m,delta)?"true":"false"); }
                else printf("{\"size\":%u}",wasm_memory_size(m));
            } else if(!strcmp(op,"call")) {
                const char *name=argv[pos++]; size_t na=number(argv[pos++]),nr=number(argv[pos++]); NEED(na<=16 && nr<=16);
                wasm_val_t av[16]={0},rv[16]={0};
                for(size_t j=0;j<na;j++) { int kind=number(argv[pos++]); uint64_t bits=number(argv[pos++]); av[j]=f4_input(kind,bits,NULL); }
                wasm_func_t *fn=wasm_extern_as_func(f3_export(p,name)); NEED(fn);
                wasm_val_vec_t a={na,av},r={nr,rv}; wasm_trap_t *t=wasm_func_call(fn,&a,&r);
                if(t) f7_failure(t); else { printf("{\"values\":["); for(size_t j=0;j<nr;j++) { if(j) putchar(','); value(rv+j); wasm_val_delete(rv+j); } printf("]}"); }
            } else NEED(0);
        }
        f7_flush();
    }
    printf("]");
    for(int i=15;i>=0;i--) if(inst[i].instance) f3_drop(&inst[i]);
    for(int i=0;i<16;i++) if(modules[i]) wasm_module_delete(modules[i]);
    wasm_store_delete(s); wasm_engine_delete(e); return 0;
}
'''

F07_ZIG = r'''
extern fn f07_main(c_int,[*][*:0]u8) c_int;
extern fn f7_compile(?*anyopaque,usize,bool) void;
extern fn f7_instantiate(?*anyopaque,u64) void;
extern fn f7_trap(?*anyopaque,u64,i32,?[*]const u8,usize) void;
extern fn f7_fuel(?*anyopaque,u64) void;
extern fn f7_growth(?*anyopaque,u64,u32,u64,u64) void;
extern fn f7_context() ?*anyopaque;
extern fn f7_flush() void;
extern fn f3_bytes([*:0]const u8) f7c.wasm_byte_vec_t;
const f7c=@cImport({ @cInclude("wasm.h"); });
fn f7Hook(e:*zw.Engine,slot:u64,on:bool) void {
    const ctx=f7_context();
    switch(slot) {
      0=>e.setCompileHook(if(on) f7_compile else null,ctx),
      1=>e.setInstantiateHook(if(on) f7_instantiate else null,ctx),
      2=>e.setTrapHook(if(on) f7_trap else null,ctx),
      3=>e.setFuelExhaustedHook(if(on) f7_fuel else null,ctx),
      4=>e.setMemoryGrowthHook(if(on) f7_growth else null,ctx),
      else=>@panic("Invalid hook slot"),
    }
}
pub export fn f07_zig(argc:c_int,argv:[*][*:0]u8) c_int {
    f7Run(@intCast(argc),argv) catch |err| { _=printf("adapter failure: %s",@as([*:0]const u8,@errorName(err))); return 70; }; return 0;
}
fn f7Run(argc:usize,argv:[*][*:0]u8) !void {
    var eng=try zw.Engine.init(std.heap.c_allocator,.{}); defer eng.deinit();
    const mode=number(argv[2]); for(0..5) |i| f7Hook(&eng,i,number(argv[3])!=0);
    var mods:[16]?zw.Module=@splat(null); var instances:[16]?zw.Instance=@splat(null);
    defer { for(&instances) |*v| { if(v.*) |*p| p.deinit(); } for(&mods) |*v| { if(v.*) |*m| m.deinit(); } }
    var pos:usize=5; _=printf("[");
    while(pos<argc) {
        if(pos>5) _=printf(","); const op=std.mem.span(argv[pos]); pos+=1;
        _=printf("{\"result\":");
        if(std.mem.eql(u8,op,"load")) {
            const slot=number(argv[pos]); const path=argv[pos+1]; pos+=2;
            const b=f3_bytes(path); defer f7c.wasm_byte_vec_delete(@constCast(&b));
            mods[slot]=eng.compile(@as([*]const u8,@ptrCast(b.data))[0..b.size]) catch |err| {
                switch(err) { error.ParseFailed,error.ValidateFailed=>{},else=>return err }
                _=printf("{\"accepted\":false}"); f7_flush(); continue;
            };
            _=printf("{\"accepted\":true}");
        } else if(std.mem.eql(u8,op,"hook")) {
            f7Hook(&eng,number(argv[pos]),number(argv[pos+1])!=0); pos+=2; _=printf("{}");
        } else if(std.mem.eql(u8,op,"new")) {
            const slot=number(argv[pos]); const m=number(argv[pos+1]); if(!std.mem.eql(u8,std.mem.span(argv[pos+2]),"-1")) return error.AdapterArguments; pos+=3;
            instances[slot]=mods[m].?.instantiate(.{.engine=if(mode==1) .jit else .interp}) catch |err| {
                _=printf("{\"created\":false,\"error\":\"%s\"}",@as([*:0]const u8,@errorName(err))); f7_flush(); continue;
            };
            _=printf("{\"created\":true,\"failure\":null}");
        } else {
            const slot=number(argv[pos]); pos+=1; const inst=&instances[slot].?;
            if(std.mem.eql(u8,op,"drop")) { inst.deinit(); instances[slot]=null; _=printf("{}"); }
            else if(std.mem.eql(u8,op,"fuel")) { inst.setFuel(number(argv[pos])); pos+=1; _=printf("{}"); }
            else if(std.mem.eql(u8,op,"unfuel")) { inst.setFuel(null); _=printf("{}"); }
            else if(std.mem.eql(u8,op,"grow") or std.mem.eql(u8,op,"size")) {
                pos+=1; const m=inst.memory() orelse return error.MissingMemory;
                if(std.mem.eql(u8,op,"size")) { _=printf("{\"size\":%u}",m.size()); }
                else { const old=m.grow(@intCast(number(argv[pos]))); pos+=1; if(old) |v| { _=printf("{\"old\":%u}",v); } else { _=printf("{\"old\":null}"); } }
            } else if(std.mem.eql(u8,op,"call")) {
                // Reuse the existing public invocation operation and value transport.
                // Its argument list begins with "call"; the instance slot has
                // already been consumed, so provide a compact local view.
                var args:[40][*:0]u8=undefined; args[0]=@constCast("call");
                const na=number(argv[pos+1]); const n=3+2*na; if(n+1>args.len) return error.AdapterArguments;
                @memcpy(args[1..][0..n],argv[pos..][0..n]); pos+=n; var at:usize=0;
                f4Op(inst,n+1,&args,&at) catch |err| {
                    switch(err) { error.AdapterArguments,error.AdapterType,error.AdapterOperation,error.MissingMemory,error.MissingGlobal,error.MissingTable,error.InvalidCharacter,error.Overflow=>return err,else=>{} }
                    _=printf("{\"error\":\"%s\"}",@as([*:0]const u8,@errorName(err))); };
            } else return error.AdapterOperation;
        }
        f7_flush();
    }
    _=printf("]");
}
'''

class F07Driver:
    def __init__(self, compiler, directory):
        self.compiler, self.directory = compiler, directory
        self.executable = None
        self.serial = 0

    def program(self):
        return self.compiler.plan.consumer('F07')

    def binary(self, wat):
        binary = self.compiler.wat(wat)
        assert self.compiler.standard_valid(binary), wat
        return binary

    def run(self, binaries, operations, *, api='c', engine='interp', enabled=True, trace=False):
        assert api in ('c', 'zig') and engine in ('interp', 'jit')
        assert not trace or (api == 'c' and engine == 'interp')
        self.serial += 1
        paths = []
        for i, binary in enumerate(binaries):
            path = self.directory / f'guest-{self.serial}-{i}.wasm'
            path.write_bytes(binary)
            paths.append(path)
        command = [self.program(), api, '2' if engine == 'interp' else '1', str(int(enabled)), str(int(trace))]
        for op in operations:
            if op[0] in ('load', 'validate'):
                op = (*op[:2], paths[op[2]])
            command.extend(map(str, op))
        got = run_json_adapter(command, timeout=30)
        (self.directory / f'observation-{self.serial}.json').write_bytes(got.process.stdout)
        assert isinstance(got.value, list) and len(got.value) == len(operations), got.value
        return got.value


@pytest.fixture(scope='session')
def f07_driver(f01_driver, tmp_path_factory):
    return F07Driver(f01_driver, tmp_path_factory.mktemp('f07-consumer'))


def f07_call(slot, name, args=(), results=0):
    op = f04_call(name, args, results)
    return (op[0], slot, *op[1:])


def f07_locations(binary):
    """Decode fixture instruction boundaries using the Core 3 binary grammar.

    This is an input decoder, not a product trace reconstruction. The caller
    specifies the executed guest chain. Unsupported fixture grammar is an error.
    Offsets are from module start and from function-body start (locals included).
    """
    reader = F01BinaryReader(binary)
    assert reader.take(8) == b'\0asm\1\0\0\0'
    imports = 0
    functions = []
    while reader.position < len(binary):
        section = reader.byte()
        length = reader.unsigned()
        base = reader.position
        body = F01BinaryReader(reader.take(length))
        if section == 2:
            for _ in range(body.unsigned()):
                body.name(); body.name()
                assert body.byte() == 0, 'Trace fixtures import functions only'
                body.unsigned(); imports += 1
            body.end()
        elif section == 10:
            for i in range(body.unsigned()):
                size = body.unsigned()
                start = base + body.position
                code = F01BinaryReader(body.take(size))
                for _ in range(code.unsigned()):
                    code.unsigned(); code.byte()
                instructions = []
                while code.position < len(code.data):
                    offset = code.position
                    opcode = code.byte()
                    key = opcode
                    if opcode in (0x02, 0x03, 0x04, 0x0c, 0x0d, 0x10, 0x20, 0x21, 0x22,
                                  0x23, 0x24, 0x25, 0x26, 0x3f, 0x40, 0x41, 0x42, 0xd0, 0xd2):
                        code.unsigned()  # Signed immediates have the same byte boundary.
                    elif opcode == 0x11:
                        code.unsigned(); code.unsigned()
                    elif 0x28 <= opcode <= 0x3e:
                        code.unsigned(); code.unsigned()
                    elif opcode == 0x43:
                        code.take(4)
                    elif opcode == 0x44:
                        code.take(8)
                    elif opcode == 0xfb:
                        sub = code.unsigned(); key = (opcode, sub)
                        if sub in (0, 1, 6, 7, 16, 20, 21, 22, 23):
                            code.unsigned()
                        elif sub in (2, 3, 4, 5):
                            code.unsigned(); code.unsigned()
                        else:
                            raise ValueError(f'Unsupported fixture GC instruction: {sub}')
                    elif opcode not in (0x00, 0x01, 0x05, 0x0b, 0x0f, 0x1a, 0xd1, 0xd4) and not 0x45 <= opcode <= 0xc4:
                        raise ValueError(f'Unsupported fixture instruction: {opcode:#x}')
                    instructions.append((key, {'function': imports+i, 'module_offset': start+offset, 'function_offset': offset}))
                functions.append(instructions)
            body.end()
    return functions


def f07_location(locations, function, opcode, occurrence=0):
    matches = [frame for op, frame in locations[function] if op == opcode]
    assert occurrence < len(matches), (function, opcode, matches)
    return matches[occurrence]


def f07_assert_trace(observation, kind, frames):
    """Accept any complete inner prefix meeting the promised depth coverage."""
    result = observation['result']
    assert result['trap'] == kind, result
    assert result['origin'] == frames[0], result
    trace = result['trace']
    assert min(len(frames), 64) <= len(trace) <= len(frames), result
    assert trace == frames[:len(trace)], result

F07_GUEST = '''(module
  (memory (export "memory") 1 9)
  (global $state (mut i32) (i32.const 0))
  (func (export "step") (param i32) (result i32)
    global.get $state local.get 0 i32.add global.set $state
    i32.const 0 global.get $state i32.store global.get $state)
  (func (export "read") (result i32) i32.const 0 i32.load)
  (func (export "grow") (param i32) (result i32) local.get 0 memory.grow)
  (func (export "boom") unreachable)
  (func (export "divide") i32.const 17 i32.const 0 i32.div_s drop)
  (func (export "spin") (loop br 0)))'''


def f07_events(observation, tag):
    return [event for event in observation['events'] if event['event'] == tag]


def f07_identity(observation):
    assert observation['result'] == {'created': True, 'failure': None}, observation
    events = f07_events(observation, 'instance')
    assert len(events) == 1, observation
    return events[0]['id']


def f07_assert_fault(observation, api, kind, error):
    if api == 'c':
        assert observation['result']['trap'] == kind, observation
    else:
        assert observation['result'] == {'error': error}, observation


def f07_assert_growth(observation, identity, index, old, new):
    assert f07_events(observation, 'growth') == [
        {'event': 'growth', 'id': identity, 'memory': index, 'old': old, 'new': new}
    ], observation


def f07_normalized_events(observations):
    """Compare event contents without fixing ID allocation or delivery order."""
    identities = {}
    normalized = []
    for observation in observations:
        for event in observation['events']:
            if event['event'] == 'instance':
                assert event['id'] not in identities, observations
                identities[event['id']] = len(identities)
        events = []
        for event in observation['events']:
            event = dict(event)
            if 'id' in event:
                assert event['id'] in identities, observation
                event['id'] = identities[event['id']]
            events.append(event)
        normalized.append(sorted(events, key=lambda item: json.dumps(item, sort_keys=True)))
    return normalized


def consumer_sources():
    return {'F07': (F02_ZIG.replace('return f02_main(argc, argv);', 'return f07_main(argc, argv);') + F03_ZIG + F04_ZIG + F07_ZIG, F02_C + F03_C.replace('static wasm_byte_vec_t f3_bytes', 'wasm_byte_vec_t f3_bytes') + F04_C + F07_C, ('v3_0',))}
