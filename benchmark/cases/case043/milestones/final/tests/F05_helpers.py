# feature: F05
"""Budget consumers; reuse earlier public invocation and state transports.

All observations come from public Zig APIs. Adapter failures are process failures,
not guest errors. A host callback synchronizes cancellation with live guest work.
"""
import json
import os
import pytest
from F01_helpers import F01_BUILD, f01_driver
from F02_helpers import F02_C, F02_ZIG, f02_arg, f02_values
from F03_helpers import F03_C, F03_ZIG
from F04_helpers import F04_C, F04_ZIG, f04_call
from _helpers import build_outputs, run_json_adapter

F05_C = r'''
extern int f05_zig(const unsigned char*,size_t,int,size_t,char**);
int f05_main(int argc,char **argv) {
    NEED(argc>=6);
    wasm_byte_vec_t bytes=f3_bytes(argv[2]);
    int rc=f05_zig((unsigned char*)bytes.data,bytes.size,(int)number(argv[1]),argc-3,argv+3);
    wasm_byte_vec_delete(&bytes); return rc;
}
'''

F05_ZIG = r'''
extern fn f05_main(c_int,[*][*:0]u8) c_int;
extern fn usleep(c_uint) c_int;
fn f5Budget(s:[*:0]const u8) zw.Module.Budget {
    return if(std.mem.eql(u8,std.mem.span(s),"none")) .unmetered else .{.limited=number(s)};
}
fn f5Remainder(inst:*zw.Instance) void {
    if(inst.fuelRemaining()) |n| { _=printf("{\"remaining\":%llu}",@as(c_ulonglong,n)); }
    else { _=printf("{\"remaining\":null}"); }
}
var f5Entered=std.atomic.Value(bool).init(false);
fn f5Pulse(_: *zw.Caller) void { f5Entered.store(true,.release); }
fn f5Cancel(inst:*zw.Instance) void {
    // A bound on host synchronization is a driving guard, never an outcome.
    for(0..5000) |_| {
        if(f5Entered.load(.acquire)) {
            if(usleep(20000)!=0) @panic("Cancellation host wait failed");
            inst.interrupt(); return;
        }
        if(usleep(1000)!=0) @panic("Cancellation synchronization failed");
    }
    @panic("Guest never reached the host synchronization callback");
}
fn f5Op(inst:*zw.Instance,argc:usize,argv:[*][*:0]u8,pos:*usize) !void {
    const op=std.mem.span(argv[pos.*]);
    if(std.mem.eql(u8,op,"fuel") or std.mem.eql(u8,op,"mcap") or std.mem.eql(u8,op,"tcap")) {
        const b=f5Budget(argv[pos.*+1]); pos.*+=2;
        const n:?u64=switch(b) { .unmetered=>null,.limited=>|v| v };
        if(std.mem.eql(u8,op,"fuel")) { inst.setFuel(n); f5Remainder(inst); }
        else { if(std.mem.eql(u8,op,"mcap")) inst.setMemoryPagesLimit(n) else inst.setTableElementsLimit(n); _=printf("{\"ok\":true}"); }
    } else if(std.mem.eql(u8,op,"remaining")) {
        pos.*+=1; f5Remainder(inst);
    } else if(std.mem.eql(u8,op,"clear")) {
        pos.*+=1; inst.clearInterrupt(); _=printf("{\"ok\":true}");
    } else if(std.mem.eql(u8,op,"cancel")) {
        pos.*+=1; f5Entered.store(false,.release);
        const thread=try std.Thread.spawn(.{},f5Cancel,.{inst});
        defer thread.join();
        // The invocation itself is observed by the existing public-call adapter.
        try f4Op(inst,argc,argv,pos);
    } else try f4Op(inst,argc,argv,pos);
}
pub export fn f05_zig(data:[*]const u8,len:usize,mode:c_int,argc:usize,argv:[*][*:0]u8) c_int {
    f5Run(data[0..len],mode,argc,argv) catch |err| {
        _=printf("adapter failure: %s",@as([*:0]const u8,@errorName(err))); return 70;
    }; return 0;
}
fn f5Run(data:[]const u8,mode:c_int,argc:usize,argv:[*][*:0]u8) !void {
    var eng=try zw.Engine.init(std.heap.c_allocator,.{}); defer eng.deinit();
    var mod=try eng.compile(data); defer mod.deinit();
    const opts:zw.Module.InstantiateOpts=.{.engine=if(mode==1) .jit else .interp,
        .fuel=f5Budget(argv[0]),.max_memory_pages=f5Budget(argv[1]),.max_table_elements=f5Budget(argv[2])};
    var linker=zw.Linker.init(&eng); defer linker.deinit();
    try linker.defineFunc("host","pulse",@TypeOf(f5Pulse),f5Pulse);
    // Use the module entry for creation-limit errors; the linker is only needed
    // for the explicitly requested cancellation callback.
    var inst=if(std.mem.eql(u8,std.mem.span(argv[3]),"linked"))
        linker.instantiate(&mod,opts) catch |err| {
            _=printf("{\"created\":false,\"error\":\"%s\"}",@as([*:0]const u8,@errorName(err))); return;
        }
    else mod.instantiate(opts) catch |err| {
        _=printf("{\"created\":false,\"error\":\"%s\"}",@as([*:0]const u8,@errorName(err))); return;
    };
    defer inst.deinit();
    _=printf("{\"created\":true,\"observations\":["); var pos:usize=4;
    while(pos<argc) {
        if(pos>4) _=printf(",");
        f5Op(&inst,argc,argv,&pos) catch |err| {
            switch(err) {
                error.AdapterArguments,error.AdapterType,error.AdapterOperation,
                error.MissingMemory,error.MissingGlobal,error.MissingTable,
                error.InvalidCharacter,error.Overflow => return err,
                else => _=printf("{\"error\":\"%s\"}",@as([*:0]const u8,@errorName(err))),
            }
        };
    }
    _=printf("]}");
}
'''

class F05Driver:
    def __init__(self, compiler, directory):
        self.compiler, self.directory = compiler, directory
        self.executable = None
        self.serial = 0

    def program(self):
        return self.compiler.plan.consumer('F05')

    def run(self, wat, operations=(), *, engine='interp', fuel='none', memory='none', table='none', linked=False):
        assert engine in ('interp','jit')
        binary = self.compiler.wat(wat)
        assert self.compiler.standard_valid(binary), wat
        self.serial += 1
        path = self.directory / f'guest-{self.serial}.wasm'
        path.write_bytes(binary)
        command = [self.program(),'1' if engine=='jit' else '2',path,str(fuel),str(memory),str(table),
                   'linked' if linked else 'module']
        for op in operations:
            command.extend(map(str,op))
        result = run_json_adapter(command,timeout=15)
        path.with_suffix('.observation.json').write_bytes(result.process.stdout)
        return result.value

@pytest.fixture(scope='session')
def f05_driver(f01_driver,tmp_path_factory):
    return F05Driver(f01_driver,tmp_path_factory.mktemp('f05-consumer'))

F05_WORK = '''(module
 (memory (export "memory") 1 8)
 (global $runs (export "runs") (mut i32) (i32.const 0))
 (func (export "work") (param $n i32) (result i32) (local $sum i32)
   global.get $runs i32.const 1 i32.add global.set $runs
   (loop $loop local.get $sum local.get $n i32.add local.set $sum
     local.get $n i32.const 1 i32.sub local.tee $n br_if $loop)
   i32.const 0 local.get $sum i32.store local.get $sum)
 (func (export "spin") (loop $forever br $forever))
 (func (export "divide") (result i32) i32.const 1 i32.const 0 i32.div_s)
 (func (export "fault") (result i32) i32.const 65536 i32.load))'''


def f05_completed_work(driver, engine, n):
    """Find a completion with a bounded search, without fixing charging units.

    Each allowance gets a fresh instance. Product exhaustion is explicitly
    checked; every other failure propagates. No timeout is a search result.
    """
    for budget in [1 << power for power in range(0,61,4)] + [(1<<63)-2]:
        got = driver.run(F05_WORK,[('remaining',),f04_call('work',[f02_arg(0,n)],1),
            ('remaining',),('global','runs'),('bytes',0,4,'-')],engine=engine,fuel=budget)
        assert got['created'] is True, got
        obs = got['observations']
        assert obs[0] == {'remaining':budget}, obs
        if 'values' in obs[1]:
            assert 0 <= obs[2]['remaining'] < budget, obs
            return budget,obs
        assert obs[1:3] == [{'error':'OutOfFuel'},{'remaining':0}], obs
    raise AssertionError('Finite deterministic work did not complete within the bounded allowance search')


def consumer_sources():
    return {'F05': (F02_ZIG.replace('return f02_main(argc, argv);','return f05_main(argc, argv);') + F03_ZIG + F04_ZIG + F05_ZIG, F02_C + F03_C + F04_C + F05_C, ('v3_0',))}
