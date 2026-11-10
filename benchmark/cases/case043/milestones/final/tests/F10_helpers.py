# feature: F10
"""Preview1 service guests; all observations cross public embedding entries."""
import json
import os
import struct

import pytest

from F01_helpers import F01_BUILD, f01_driver
from F02_helpers import F02_C, F02_ZIG
from F03_helpers import F03_C, F03_ZIG
from F09_helpers import F09Guest, F09Driver, F09_C, f09_memory
from _helpers import build_outputs, run_json_adapter


F10_C = r'''
extern int f10_configured(const unsigned char*, size_t, size_t, int);
int f10_main(int argc, char **argv) {
    if (argc > 2 && !strcmp(argv[1], "repeat")) {
        f10_repetitions = number(argv[2]);
        NEED(f10_repetitions > 0);
        argc -= 2; argv += 2;
    }
    if (argc > 1 && !strcmp(argv[1], "configured-io")) {
        NEED(argc == 5);
        wasm_byte_vec_t bytes = f3_bytes(argv[2]);
        int code = f10_configured((const unsigned char*)bytes.data, bytes.size,
                                  number(argv[3]), (int)number(argv[4]));
        wasm_byte_vec_delete(&bytes);
        return code;
    }
    return f09_main(argc, argv);
}
'''

F10_ZIG = r'''
extern fn f10_main(c_int, [*][*:0]u8) c_int;
pub export fn f10_configured(data: [*]const u8, len: usize, size: usize, enabled: c_int) c_int {
    f10Configured(data[0..len], size, enabled) catch |err| {
        _ = printf("Adapter error: %s\n", @as([*:0]const u8, @errorName(err)));
        return 70;
    };
    return 0;
}
fn f10Configured(bytes: []const u8, size: usize, enabled: c_int) !void {
    const alloc = std.heap.c_allocator;
    var threaded: std.Io.Threaded = .init(alloc, .{});
    defer threaded.deinit();
    var engine = try zw.Engine.init(alloc, .{});
    defer engine.deinit();
    var module = try engine.compile(bytes);
    defer module.deinit();
    var linker = zw.Linker.init(&engine);
    defer linker.deinit();
    try linker.defineWasi(.{ .io = if (enabled == 1) threaded.io() else null });
    var instance = try linker.instantiate(&module, .{ .engine = .interp });
    defer instance.deinit();
    try instance.invoke("run", &.{}, &.{});
    const memory = instance.memory() orelse return error.MissingMemory;
    const observed = try memory.sliceAt(0, @intCast(size));
    _ = printf("{\"memory\":\"");
    for (observed) |byte| _ = printf("%02x", @as(c_uint, byte));
    _ = printf("\"}");
}
'''


def f10_timed_consumer(source):
    """Add native observations around the public call in the reused consumer."""
    call = 'trap=wasm_func_call(fn,&av,&rv);'
    assert source.count(call) == 1
    timed = r'''
        struct timespec f10_rb, f10_mb, f10_ra, f10_ma, f10_pb, f10_tb, f10_pa, f10_ta;
        NEED(clock_gettime(CLOCK_REALTIME, &f10_rb)==0);
        NEED(clock_gettime(CLOCK_MONOTONIC, &f10_mb)==0);
        NEED(clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &f10_pb)==0);
        NEED(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &f10_tb)==0);
        trap=wasm_func_call(fn,&av,&rv);
        NEED(clock_gettime(CLOCK_THREAD_CPUTIME_ID, &f10_ta)==0);
        NEED(clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &f10_pa)==0);
        NEED(clock_gettime(CLOCK_MONOTONIC, &f10_ma)==0);
        NEED(clock_gettime(CLOCK_REALTIME, &f10_ra)==0);
        printf(",\"native_before\":[%llu,%llu,%llu,%llu],\"native_after\":[%llu,%llu,%llu,%llu]",
          (unsigned long long)f10_rb.tv_sec*1000000000ULL+(unsigned long long)f10_rb.tv_nsec,
          (unsigned long long)f10_mb.tv_sec*1000000000ULL+(unsigned long long)f10_mb.tv_nsec,
          (unsigned long long)f10_pb.tv_sec*1000000000ULL+(unsigned long long)f10_pb.tv_nsec,
          (unsigned long long)f10_tb.tv_sec*1000000000ULL+(unsigned long long)f10_tb.tv_nsec,
          (unsigned long long)f10_ra.tv_sec*1000000000ULL+(unsigned long long)f10_ra.tv_nsec,
          (unsigned long long)f10_ma.tv_sec*1000000000ULL+(unsigned long long)f10_ma.tv_nsec,
          (unsigned long long)f10_pa.tv_sec*1000000000ULL+(unsigned long long)f10_pa.tv_nsec,
          (unsigned long long)f10_ta.tv_sec*1000000000ULL+(unsigned long long)f10_ta.tv_nsec);
    '''
    source = source.replace(call, timed)
    # Repeated observations retain the same instance and hence the same clock
    # origin. Snapshot each call before the next one overwrites guest memory.
    source = source.replace('    if(p.instance) {', r'''
    printf(",\"samples\":[");
    for(size_t sample=0; p.instance && sample<f10_repetitions; sample++) {
        if(sample) {
            struct timespec delay={0,40000000}, remaining;
            while(nanosleep(&delay,&remaining)!=0) {
                NEED(errno==EINTR); delay=remaining;
            }
        }
        printf("%s{\"instantiated\":true",sample?",":"");''')
    source = source.replace("        putchar('\"');\n    }", "        putchar('\"'); putchar('}');\n    }")
    source = source.replace("    putchar('}'); f3_drop(&p);", '    printf("]}"); f3_drop(&p);')
    return ('#define _POSIX_C_SOURCE 200809L\n#include <time.h>\n#include <errno.h>\n'
            '#include <stddef.h>\nstatic size_t f10_repetitions = 1;\n'
            + F02_C + F03_C + source)


class F10Driver(F09Driver):
    def program(self):
        return self.compiler.plan.consumer('F10')


@pytest.fixture(scope='session')
def f10_driver(f01_driver, tmp_path_factory):
    return F10Driver(f01_driver, tmp_path_factory.mktemp('f10-consumer'))

F10_SIGNATURES = {
    'clock_time_get': 'iqi', 'clock_res_get': 'ii',
    'random_get': 'ii', 'poll_oneoff': 'iiii',
}


class F10Guest(F09Guest):
    def __init__(self):
        super().__init__()
        self.services = set()

    def service(self, label, operation, *args):
        """Save the actual errno, including failures, without stopping the probe."""
        signature = F10_SIGNATURES[operation]
        assert len(signature) == len(args)
        assert label not in self.statuses
        ptr = len(self.statuses) * 4
        assert ptr < 3072
        self.statuses[label] = ptr
        self.services.add(operation)
        terms = [f'i32.const {ptr}']
        for kind, arg in zip(signature, args, strict=True):
            terms.append(arg if isinstance(arg, str) else f'{"i64" if kind == "q" else "i32"}.const {arg}')
        self.body.append(' '.join(terms + [f'call ${operation}', 'i32.store']))
        return ptr

    def clock(self, label, clock_id, *, resolution=False):
        ptr = self.alloc(8, b'\xff' * 8)
        if resolution:
            self.service(label, 'clock_res_get', clock_id, ptr)
        else:
            self.service(label, 'clock_time_get', clock_id, 1, ptr)
        return ptr

    def poll(self, label, subscriptions):
        inputs = self.alloc(48 * len(subscriptions), b''.join(subscriptions))
        events = self.alloc(32 * len(subscriptions), b'\xff' * (32 * len(subscriptions)))
        count = self.alloc(4, b'\xff' * 4)
        self.service(label, 'poll_oneoff', inputs, events, len(subscriptions), count)
        return events, count, len(subscriptions)

    def source(self):
        declarations = []
        for name in sorted(self.services):
            types = ' '.join('i64' if k == 'q' else 'i32' for k in F10_SIGNATURES[name])
            declarations.append(f'(import "wasi_snapshot_preview1" "{name}" (func ${name} (param {types}) (result i32)))')
        return super().source().replace('(module\n', '(module\n' + '\n'.join(declarations) + '\n', 1)


def f10_fd(userdata, kind, fd):
    """Encode a snapshot-01 subscription, not a readiness prediction."""
    record = bytearray(48)
    struct.pack_into('<QB', record, 0, userdata, kind)
    struct.pack_into('<I', record, 16, fd)
    return bytes(record)


def f10_timer(userdata, timeout, *, clock=1, absolute=False):
    record = bytearray(48)
    struct.pack_into('<QB', record, 0, userdata, 0)
    struct.pack_into('<I', record, 16, clock)
    struct.pack_into('<QQH', record, 24, timeout, 1, int(absolute))
    return bytes(record)


def f10_events(mem, region):
    ptr, count_ptr, capacity = region
    count, = struct.unpack_from('<I', mem, count_ptr)
    assert 0 < count <= capacity, (count, capacity)
    assert ptr + count * 32 <= len(mem)
    events = {}
    for i in range(count):
        base = ptr + i * 32
        userdata, error, kind = struct.unpack_from('<QHB', mem, base)
        assert userdata not in events, 'Duplicate subscription event'
        # Only fd events carry fd_readwrite; clock padding is not an observable.
        event = {'error': error, 'kind': kind}
        if kind in (1, 2):
            event['nbytes'], = struct.unpack_from('<Q', mem, base + 16)
        events[userdata] = event
    return events


def f10_run(driver, guest, grants=(), *, engine='interp'):
    """Read native call brackets, excluding process startup and instantiation."""
    return f10_samples(driver, guest, grants, engine=engine, repetitions=1)[0]


def f10_samples(driver, guest, grants=(), *, engine='interp', repetitions=3):
    """Invoke one live instance repeatedly, preserving the clock's epoch."""
    program = driver.program()
    path = driver.guests.guest(guest.source())
    command = [program, 'repeat', str(repetitions), path,
               '1' if engine == 'jit' else '2', str(guest.end)]
    for host, name in grants:
        command.extend([str(host), name])
    observed = run_json_adapter(command, timeout=20)
    path.with_suffix('.json').write_bytes(observed.process.stdout)
    path.with_suffix('.stderr').write_bytes(observed.process.stderr)
    assert observed.value['instantiated'] is True, observed.value
    samples = observed.value['samples']
    assert len(samples) == repetitions, observed.value
    return [(f09_memory(sample), sample['native_before'], sample['native_after'])
            for sample in samples]


def f10_run_configured_io(driver, guest, *, enabled):
    """Use the public optional host I/O configuration, without replacing clocks."""
    program = driver.program()
    path = driver.guests.guest(guest.source())
    observed = run_json_adapter(
        [program, 'configured-io', path, str(guest.end), str(int(enabled))], timeout=20)
    path.with_suffix('.json').write_bytes(observed.process.stdout)
    path.with_suffix('.stderr').write_bytes(observed.process.stderr)
    mem = bytes.fromhex(observed.value['memory'])
    assert len(mem) == guest.end
    return mem


def f10_capture_memory(driver, guest, stdin):
    """Transport guest memory via real captured stdout after configured input."""
    guest.imports.add('fd_write')
    source = guest.source().replace('(func (export "run")', '(func $run (export "run")', 1)
    source = source[:-1] + f'''
      (func (export "_start") (local $sent i32) (local $n i32)
        call $run
        block $done loop $next
          local.get $sent i32.const {guest.end} i32.ge_u br_if $done
          i32.const 3600 local.get $sent i32.store
          i32.const 3604 i32.const {guest.end} local.get $sent i32.sub i32.store
          i32.const 1 i32.const 3600 i32.const 1 i32.const 3608 call $fd_write
          if unreachable end
          i32.const 3608 i32.load local.tee $n i32.eqz if unreachable end
          local.get $n i32.const {guest.end} local.get $sent i32.sub i32.gt_u if unreachable end
          local.get $sent local.get $n i32.add local.set $sent
          br $next end end))'''
    result = driver.capture(source, stdin=stdin, allowance=guest.end)
    assert 'error' not in result, result
    assert result['status'] == 0, result
    mem = bytes.fromhex(result['stdout'])
    assert len(mem) == guest.end
    return mem


def consumer_sources():
    return {'F10': (F02_ZIG.replace('return f02_main(argc, argv);', 'return f10_main(argc, argv);')
                + F03_ZIG + F10_ZIG, f10_timed_consumer(F09_C) + F10_C, ('v3_0',))}
