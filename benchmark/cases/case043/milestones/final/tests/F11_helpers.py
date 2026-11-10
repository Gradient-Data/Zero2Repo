# feature: F11
"""CLI consumers and guests; all product observations cross public entries."""
import json
import os
import re
import struct
from decimal import Decimal

import pytest
from _helpers import build_outputs, run_cli, run_process, parse_scalar_lines
from F01_helpers import f01_driver
from F08_helpers import f08_driver, F08_CLI_BUILD, F08_IMPORTS
from F09_helpers import F09Guest

F11_BUILD = F08_CLI_BUILD.replace(
    '.wasi = "p3",', '.wasi = b.option([]const u8, "wasi", "WASI level").?,').replace(
    '.wasm = "v3_0",', '.wasm = b.option([]const u8, "wasm", "Wasm level").?,\n        .engine = b.option([]const u8, "engine", "Enabled engines").?,').replace(
    'b.installArtifact(dependency.artifact("navor"));', '''b.installArtifact(dependency.artifact("navor"));
    const probe = b.addExecutable(.{
        .name = "f11-version",
        .root_module = b.createModule(.{
            .root_source_file = b.path("probe.zig"),
            .target = target, .optimize = optimize, .link_libc = true,
        }),
    });
    probe.root_module.addImport("navor", dependency.module("navor"));
    probe.root_module.addIncludePath(dependency.path("include"));
    probe.root_module.addCSourceFile(.{.file = b.path("probe.c"), .flags = &.{"-std=c11", "-Wall", "-Werror"}});
    b.installArtifact(probe);''')

F11_VERSION_C = '''#include <navor.h>
#include <stdio.h>
int f11_version(void) {
    const char *version = navor_version();
    if (!version) { fputs("Version query returned null\\n", stderr); return 70; }
    return puts(version) < 0 ? 70 : 0;
}
'''
F11_VERSION_ZIG = '''const zw = @import("navor");
comptime { _ = zw; }
extern fn f11_version() c_int;
pub export fn main() c_int { return f11_version(); }
'''


class F11Driver:
    def __init__(self, wasi, directory):
        self.wasi, self.directory = wasi, directory
        self.builds = {}
        self.serial = 0

    def build(self, *, wasm='v3_0', wasi='p3', engine='both', optimize='ReleaseSafe'):
        return self.wasi.compiler.plan.cli(consumer="F11", wasm=wasm, wasi=wasi, engine=engine, optimize=optimize)

    def command(self, arguments=(), *, stdin=b'', cli=None, timeout=30):
        if cli is None:
            cli = self.build()[0]
        result = run_cli(cli, arguments, input_bytes=stdin, timeout=timeout)
        self.serial += 1
        stem = self.directory / f'cli-{self.serial}'
        stem.with_suffix('.stdout').write_bytes(result.stdout)
        stem.with_suffix('.stderr').write_bytes(result.stderr)
        stem.with_suffix('.json').write_text(json.dumps({'argv':[str(x) for x in result.argv],
                                                       'returncode':result.returncode}))
        return result

    def run(self, source, *, options=(), args=(), stdin=b''):
        path = self.wasi.guest(source)
        return path, self.command(['run', *options, path, *args], stdin=stdin)


@pytest.fixture(scope='session')
def f11_driver(f08_driver, tmp_path_factory):
    return F11Driver(f08_driver, tmp_path_factory.mktemp('f11-cli'))


def f11_scalar_line(line):
    """Whole bare numeric line, accepting decimal and scientific spelling."""
    if re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?', line):
        return Decimal(line)
    raise ValueError(f'Invalid CLI scalar line: {line!r}')


def f11_values(result, expected):
    assert result.returncode == 0, (result.returncode, result.stderr)
    actual = parse_scalar_lines(result.stdout, f11_scalar_line)
    assert len(actual) == len(expected), result.stdout
    for value, wanted in zip(actual, expected):
        # Strings denote f64 and tagged tuples denote f32. Accept decimal
        # spelling that round-trips to the declared IEEE value; integer
        # results retain arbitrary precision rather than passing through float.
        if isinstance(wanted, tuple):
            kind, number = wanted
            assert kind == 'f32'
            assert struct.pack('<f', float(value)) == struct.pack('<f', float(number)), (value, wanted)
        elif isinstance(wanted, str):
            assert float(value) == float(wanted), (value, wanted)
        else:
            assert value == wanted, (value, wanted)


def f11_failure(result, status=1, *, trap=None):
    assert result.returncode == status, (result.returncode, result.stdout, result.stderr)
    assert result.stdout == b'', result.stdout
    assert result.stderr, 'Refusal must report on stderr'
    if trap is not None:
        # Fixed trap label and kind token; the human message remains free.
        matches = re.findall(rb'^navor: trap kind=([a-z_]+)(?: msg=[^\n]*)?$', result.stderr, re.M)
        assert matches == [trap.encode()], result.stderr


def f11_identity(result, *, banner=False):
    assert result.returncode == 0, result.stderr
    if banner:
        pattern = (rb'navor v([^\s]+)\n'
                   rb'  wasm-level: ([^,\s]+), wasi-level: ([^,\s]+), engine: ([^\s]+)\n')
    else:
        pattern = (rb'navor v([^\s]+) \(wasm: ([^,\s]+), wasi: ([^,\s]+), '
                   rb'engine: ([^,\s]+), mode: ([^\s)]+)\)\n')
    match = re.fullmatch(pattern, result.stdout)
    assert match, result.stdout
    return tuple(x.decode() for x in match.groups())


F11_CONTEXT = '(module' + F08_IMPORTS + '''
 (memory 1)
 (func $write_all (param $fd i32) (param $ptr i32) (param $len i32)
   (local $done i32) (local $n i32)
   block $end loop $next
     local.get $done local.get $len i32.ge_u br_if $end
     i32.const 32 local.get $ptr local.get $done i32.add i32.store
     i32.const 36 local.get $len local.get $done i32.sub i32.store
     local.get $fd i32.const 32 i32.const 1 i32.const 40 call $write if unreachable end
     i32.const 40 i32.load local.tee $n i32.eqz if unreachable end
     local.get $n local.get $len local.get $done i32.sub i32.gt_u if unreachable end
     local.get $done local.get $n i32.add local.set $done br $next
   end end)
 (func $vector (param $fd i32) (param $table i32) (param $count i32)
   (local $index i32) (local $ptr i32) (local $length i32)
   block $done loop $next
     local.get $index local.get $count i32.ge_u br_if $done
     local.get $table local.get $index i32.const 4 i32.mul i32.add i32.load local.set $ptr
     i32.const 0 local.set $length
     block $end loop $scan
       local.get $length i32.const 4096 i32.ge_u if unreachable end
       local.get $ptr local.get $length i32.add i32.load8_u i32.eqz br_if $end
       local.get $length i32.const 1 i32.add local.set $length br $scan
     end end
     local.get $fd local.get $ptr local.get $length i32.const 1 i32.add call $write_all
     local.get $index i32.const 1 i32.add local.set $index br $next
   end end)
 (func (export "_start")
   i32.const 0 i32.const 4 call $as if unreachable end
   i32.const 64 i32.const 512 call $ag if unreachable end
   i32.const 8 i32.const 12 call $es if unreachable end
   i32.const 256 i32.const 2048 call $eg if unreachable end
   i32.const 1 i32.const 64 i32.const 0 i32.load call $vector
   i32.const 2 i32.const 256 i32.const 8 i32.load call $vector))'''

F11_IO = '(module' + F08_IMPORTS + '''
 (memory 1)
 (data (i32.const 128) "\\7f")
 (func (export "_start") (local $n i32)
   i32.const 32 i32.const 128 i32.store i32.const 36 i32.const 1 i32.store
   i32.const 2 i32.const 32 i32.const 1 i32.const 44 call $write if unreachable end
   i32.const 44 i32.load i32.const 1 i32.ne if unreachable end
   loop $read_next
     i32.const 32 i32.const 512 i32.store i32.const 36 i32.const 1 i32.store
     i32.const 0 i32.const 32 i32.const 1 i32.const 40 call $read if unreachable end
     i32.const 40 i32.load local.tee $n
     if
       local.get $n i32.const 1 i32.ne if unreachable end
       i32.const 1 i32.const 32 i32.const 1 i32.const 44 call $write if unreachable end
       i32.const 44 i32.load i32.const 1 i32.ne if unreachable end
       i32.const 2 i32.const 32 i32.const 1 i32.const 44 call $write if unreachable end
       i32.const 44 i32.load i32.const 1 i32.ne if unreachable end
       br $read_next
     end
   end
   i32.const 23 call $exit unreachable))'''


def f11_files_guest(length):
    guest = F09Guest()
    _, count, final = guest.enumerate()
    # Report standard preopen count and final errno, without deriving answers.
    report = guest.alloc(8)
    guest.body.append(f'i32.const {report} i32.const {count} i32.load i32.store '
                      f'i32.const {report+4} i32.const {final} i32.load i32.store')
    guest.body.append('i32.const 1 local.set $file')
    start = len(guest.body)
    destination, _ = guest.io('count', 'fd_write', 8)
    guest.body.insert(start, f'i32.const {destination} i32.const {report} i32.const 8 memory.copy')
    guest.body.append(f'i32.const {count} i32.load i32.eqz if return end')
    guest.grant('/granted')
    guest.open('input', 'input.bin')
    buf, total = guest.io('read', 'fd_read', length)
    guest.open('output', 'output.bin', flags=9)
    guest.body.append(f'i32.const {total} i32.load i32.const {length} i32.ne if unreachable end')
    start = len(guest.body)
    dest, _ = guest.io('write', 'fd_write', length)
    guest.body.insert(start, f'i32.const {dest} i32.const {buf} i32.const {length} memory.copy')
    guest.call('close', 'fd_close', 'local.get $file')
    return guest.source()

F11_SCALARS = '''(module
 (func (export "int32") (param i32) (result i32) local.get 0 i32.const 5 i32.sub)
 (func (export "int64") (param i64) (result i64) local.get 0 i64.const 7 i64.add)
 (func (export "float32") (param f32) (result f32) local.get 0 f32.const 2 f32.mul)
 (func (export "float64") (param f64) (result f64) local.get 0 f64.const 0.125 f64.add)
 (func (export "pair") (param i32 i32) (result i32 i32) local.get 1 i32.const 2 i32.mul local.get 0 i32.const 3 i32.sub)
 (func (export "mix") (param i32 i64 f32 f64) (result f64 i32 f32 i64)
   local.get 3 f64.const 0.125 f64.add local.get 0 i32.const 5 i32.sub
   local.get 2 f32.const 2 f32.mul local.get 1 i64.const 7 i64.add)
 (func (export "nothing")))'''

F11_MEMORY = '''(module
 (memory 1 8) (data (i32.const 0) "Z")
 (func (export "grow") (result i32 i32)
   i32.const 1 memory.grow i32.const 1 i32.ne if unreachable end
   i32.const 65536 i32.load8_u if unreachable end
   i32.const 65536 i32.const 61 i32.store8
   i32.const 2 memory.grow
   i32.const 0 i32.load8_u i32.const 90 i32.ne if unreachable end
   i32.const 65536 i32.load8_u i32.const 61 i32.ne if unreachable end
   memory.size))'''
F11_TABLE = '''(module
 (type $t (func (result i32)))
 (table 2 10 funcref) (elem (i32.const 0) $value)
 (func $value (result i32) i32.const 93)
 (func (export "grow") (result i32 i32)
   ref.null func i32.const 2 table.grow
   i32.const 0 call_indirect (type $t) i32.const 93 i32.ne if unreachable end
   table.size))'''
F11_INITIAL_TABLES = '''(module (table 3 funcref) (table 4 funcref)
 (func (export "main") (result i32) i32.const 71))'''
F11_SIMD = '''(module
 (func (export "scalar") (param i32) (result i32) local.get 0 i32.const 3 i32.mul)
 (func (export "simd") (param i32) (result i32)
   local.get 0 i32x4.splat v128.const i32x4 2 5 11 17 i32x4.add i32x4.extract_lane 2))'''


def f11_fuel_completion(driver, path, options):
    """Find sufficient fuel without assuming either engine's charging units."""
    for budget in [1 << power for power in range(0, 61, 8)] + [(1 << 63)-2]:
        result = driver.command(['run', *options, '--fuel', str(budget), path])
        if result.returncode == 0:
            return budget, result
        f11_failure(result, trap='out_of_fuel')
    raise AssertionError('Finite guest did not finish within the bounded fuel search')
