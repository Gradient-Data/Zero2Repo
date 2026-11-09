# feature: F09
"""Real preview1 filesystem guests and a public C embedding consumer.

The guest only forwards WASI calls and saves their ABI results. Python decodes
standard little-endian structures; it does not simulate filesystem operations.
Preopens are enumerated by the preview1 convention, without asserting fd values.
"""
import json
import os
import struct

import pytest

from F01_helpers import F01_BUILD, f01_driver
from F02_helpers import F02_C, F02_ZIG
from F03_helpers import F03_C, F03_ZIG
from F08_helpers import F08Driver
from _helpers import build_outputs, run_json_adapter

F09_C = r'''
#include <wasi.h>
int f09_main(int argc,char **argv) {
    NEED(argc>=4 && (argc-4)%2==0);
    wasm_byte_vec_t bytes=f3_bytes(argv[1]);
    wasm_engine_t *e=wasm_engine_new(); NEED(e);
    wasm_store_t *s=wasm_store_new(e); NEED(s);
    wasm_module_t *m=wasm_module_new(s,&bytes); NEED(m);
    navor_wasi_config_t *cfg=navor_wasi_config_new(); NEED(cfg);
    for(int i=4;i<argc;i+=2) {
        if(!navor_wasi_config_preopen_dir(cfg,argv[i],argv[i+1])) {
            printf("{\"instantiated\":false,\"configuration_refused\":true}");
            navor_store_set_wasi(s,cfg); wasm_module_delete(m); wasm_store_delete(s);
            wasm_engine_delete(e); wasm_byte_vec_delete(&bytes); return 0;
        }
    }
    navor_store_set_wasi(s,cfg);
    wasm_extern_vec_t imports={0,NULL}; wasm_trap_t *trap=NULL;
    F3Instance p=f3_instance(s,m,&imports,(int)number(argv[2]),&trap);
    printf("{\"instantiated\":%s",p.instance?"true":"false");
    if(trap) { printf(",\"setup_trap\":%d",navor_trap_kind(trap)); wasm_trap_delete(trap); }
    if(p.instance) {
        wasm_func_t *fn=wasm_extern_as_func(f3_export(&p,"run")); NEED(fn);
        wasm_val_vec_t av={0,NULL},rv={0,NULL}; trap=wasm_func_call(fn,&av,&rv);
        printf(",\"trapped\":%s",trap?"true":"false");
        if(trap) { printf(",\"trap\":%d",navor_trap_kind(trap)); wasm_trap_delete(trap); }
        wasm_memory_t *mem=wasm_extern_as_memory(f3_export(&p,"memory")); NEED(mem);
        size_t n=number(argv[3]); NEED(n<=wasm_memory_data_size(mem));
        const unsigned char *data=(const unsigned char*)wasm_memory_data(mem);
        fputs(",\"memory\":\"",stdout);
        for(size_t i=0;i<n;i++) printf("%02x",data[i]);
        putchar('"');
    }
    putchar('}'); f3_drop(&p); wasm_module_delete(m); wasm_store_delete(s);
    wasm_engine_delete(e); wasm_byte_vec_delete(&bytes); return 0;
}
'''


class F09Driver:
    def __init__(self, compiler, directory):
        self.compiler = compiler
        self.directory = directory
        self.executable = None
        self.guests = F08Driver(compiler, directory)

    def program(self):
        return self.compiler.plan.consumer('F09')

    def filesystem(self, guest, grants, *, engine='interp'):
        assert engine in ('interp', 'jit')
        path = self.guests.guest(guest.source())
        command = [self.program(), path, '1' if engine == 'jit' else '2', str(guest.end)]
        for host, name in grants:
            command.extend([str(host), name])
        observed = run_json_adapter(command, timeout=30)
        path.with_suffix('.json').write_bytes(observed.process.stdout)
        path.with_suffix('.stderr').write_bytes(observed.process.stderr)
        return observed.value


@pytest.fixture(scope='session')
def f09_driver(f01_driver, tmp_path_factory):
    return F09Driver(f01_driver, tmp_path_factory.mktemp('f09-consumer'))


# Signatures and bit values from the WASI snapshot-01 witx ABI.
F09_SIGNATURES = {
    'fd_prestat_get': 'ii', 'fd_prestat_dir_name': 'iii',
    'path_open': 'iiiiiqqii', 'fd_read': 'iiii', 'fd_write': 'iiii',
    'fd_pread': 'iiiqi', 'fd_pwrite': 'iiiqi', 'fd_seek': 'iqii',
    'fd_tell': 'ii', 'fd_close': 'i', 'fd_sync': 'i', 'fd_datasync': 'i',
    'fd_filestat_get': 'ii', 'fd_filestat_set_size': 'iq',
    'fd_fdstat_get': 'ii', 'fd_fdstat_set_rights': 'iqq',
    'fd_filestat_set_times': 'iqqi', 'path_filestat_set_times': 'iiiiqqi',
    'path_filestat_get': 'iiiii', 'path_create_directory': 'iii',
    'path_remove_directory': 'iii', 'path_unlink_file': 'iii',
    'path_rename': 'iiiiii', 'path_link': 'iiiiiii',
    'path_symlink': 'iiiii', 'path_readlink': 'iiiiii', 'fd_readdir': 'iiiqi',
}
F09_READ = 1 << 1
F09_WRITE = 1 << 6
F09_FILE_RIGHTS = sum(1 << n for n in (0, 1, 2, 4, 5, 6, 21, 22, 23))
F09_DIR_RIGHTS = sum(1 << n for n in (9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 23, 24, 25, 26))


class F09Guest:
    """Assemble calls and reserve output regions; no expected outcomes here."""
    def __init__(self):
        self.end = 4096
        self.data = []
        self.body = []
        self.statuses = {}
        self.imports = set()
        self.locals = {'root', 'file', 'other', 'child'}

    def alloc(self, size, data=None):
        ptr = (self.end + 7) & ~7
        self.end = ptr + size
        assert self.end <= 65536
        if data is not None:
            assert len(data) <= size
            escaped = ''.join('\\%02x' % b for b in data)
            self.data.append(f'(data (i32.const {ptr}) "{escaped}")')
        return ptr

    def path(self, value):
        value = value.encode() if isinstance(value, str) else value
        return self.alloc(max(1, len(value)), value), len(value)

    def call(self, label, operation, *args, required=True):
        signature = F09_SIGNATURES[operation]
        assert len(args) == len(signature), (operation, args, signature)
        assert label not in self.statuses
        ptr = len(self.statuses) * 4
        assert ptr < 3072
        self.statuses[label] = ptr
        self.imports.add(operation)
        instructions = [f'i32.const {ptr}']
        for kind, arg in zip(signature, args):
            instructions.append(arg if isinstance(arg, str) else f'{"i64" if kind == "q" else "i32"}.const {arg}')
        instructions.extend([f'call ${operation}', 'i32.store'])
        if required:
            instructions.append(f'i32.const {ptr} i32.load if return end')
        self.body.append(' '.join(instructions))

    def open(self, label, path, *, parent='root', target='file', flags=0,
             rights=F09_FILE_RIGHTS, inheriting=0, required=True):
        p, n = self.path(path)
        out = self.alloc(4)
        self.call(label, 'path_open', f'local.get ${parent}', 1, p, n, flags,
                  rights, inheriting, 0, out, required=required)
        self.body.append(f'i32.const {out} i32.load local.set ${target}')
        return out

    def io(self, label, operation, data, *, fd='file', offset=None):
        """Complete a finite request, allowing standard short reads/writes."""
        if isinstance(data, int):
            length = data
            buf = self.alloc(length)
        else:
            chunks = data if isinstance(data, list) else [data]
            lengths = [len(part) for part in chunks]
            data = b''.join(chunks)
            length = len(data)
            buf = self.alloc(length, data)
        if isinstance(data, int):
            lengths = [length]
        vec = self.alloc(8 * len(lengths))
        count, total = self.alloc(4), self.alloc(4)
        self.body.append(f'''block $io_done loop $io_next
          i32.const {total} i32.load i32.const {length} i32.ge_u br_if $io_done
          ''')
        start = 0
        for index, size in enumerate(lengths):
            consumed = f"""i32.const {total} i32.load i32.const {start} i32.le_u
              if (result i32) i32.const 0 else
                i32.const {total} i32.load i32.const {start+size} i32.ge_u
                if (result i32) i32.const {size} else
                  i32.const {total} i32.load i32.const {start} i32.sub end end"""
            self.body.append(f"""i32.const {vec+index*8} i32.const {buf+start} {consumed} i32.add i32.store
              i32.const {vec+index*8+4} i32.const {size} {consumed} i32.sub i32.store""")
            start += size
        args = [f'local.get ${fd}', vec, len(lengths)]
        if offset is not None:
            args.append(f'i64.const {offset} i32.const {total} i32.load i64.extend_i32_u i64.add')
        self.call(label, operation, *args, count)
        self.body.append(f'''i32.const {count} i32.load
          i32.const {length} i32.const {total} i32.load i32.sub i32.gt_u if unreachable end
          i32.const {count} i32.load i32.eqz br_if $io_done
          i32.const {total} i32.const {total} i32.load i32.const {count} i32.load i32.add i32.store
          br $io_next end end''')
        return buf, total

    def readdir(self, label, *, fd='root'):
        """Follow returned cookies; retain only complete ABI records."""
        buf, total, used = self.alloc(4096), self.alloc(4), self.alloc(4)
        self.locals.update({'rd_steps', 'rd_pos', 'rd_end', 'rd_size', 'rd_before'})
        self.body.append('block $rd_done loop $rd_next local.get $rd_steps i32.const 64 i32.ge_u if unreachable end '
                         'local.get $rd_steps i32.const 1 i32.add local.set $rd_steps')
        self.call(label, 'fd_readdir', f'local.get ${fd}',
                  f'i32.const {buf} i32.const {total} i32.load i32.add',
                  96,
                  'local.get $rd_cookie', used)
        self.body.append(f'''i32.const {used} i32.load i32.eqz br_if $rd_done
          i32.const {used} i32.load i32.const 96
          i32.gt_u if unreachable end
          i32.const {buf} i32.const {total} i32.load i32.add local.tee $rd_pos local.set $rd_before
          local.get $rd_pos i32.const {used} i32.load i32.add local.set $rd_end
          block $rd_parsed loop $rd_parse
            local.get $rd_pos i32.const 24 i32.add local.get $rd_end i32.gt_u br_if $rd_parsed
            local.get $rd_pos i32.const 16 i32.add i32.load local.set $rd_size
            local.get $rd_size i32.const 4096 i32.gt_u if unreachable end
            local.get $rd_pos i32.const 24 i32.add local.get $rd_size i32.add
            local.get $rd_end i32.gt_u br_if $rd_parsed
            local.get $rd_pos i64.load local.set $rd_cookie
            local.get $rd_pos i32.const 24 i32.add local.get $rd_size i32.add local.set $rd_pos
            br $rd_parse end end
          local.get $rd_pos local.get $rd_before i32.eq if unreachable end
          i32.const {total} local.get $rd_pos i32.const {buf} i32.sub i32.store
          br $rd_next end end''')
        return buf, total

    def grant(self, name='/sandbox', target='root'):
        """Locate a configured name via standard preopen enumeration."""
        p, n = self.path(name)
        self.body.append(f'i32.const {p} i32.const {n} call $find local.set ${target}')

    def enumerate(self):
        table = self.alloc(16 * 264)
        count = self.alloc(4)
        final = self.alloc(4)
        self.locals.update({'scan', 'count', 'record', 'errno'})
        self.body.append(f'''i32.const 3 local.set $scan
          block $done loop $next
            local.get $count i32.const 16 i32.ge_u if unreachable end
            local.get $scan i32.const 3072 call $fd_prestat_get local.tee $errno
            i32.const 8 i32.eq br_if $done
            local.get $errno if unreachable end
            i32.const 3076 i32.load i32.const 256 i32.gt_u if unreachable end
            i32.const {table} local.get $count i32.const 264 i32.mul i32.add local.set $record
            local.get $record local.get $scan i32.store
            local.get $record i32.const 4 i32.add i32.const 3076 i32.load i32.store
            local.get $scan local.get $record i32.const 8 i32.add i32.const 256
            call $fd_prestat_dir_name if unreachable end
            local.get $count i32.const 1 i32.add local.set $count
            local.get $scan i32.const 1 i32.add local.set $scan br $next
          end end
          i32.const {count} local.get $count i32.store
          i32.const {final} local.get $errno i32.store''')
        return table, count, final

    def source(self):
        imports = self.imports | {'fd_prestat_get', 'fd_prestat_dir_name'}
        declarations = []
        for name in sorted(imports):
            types = ' '.join('i64' if k == 'q' else 'i32' for k in F09_SIGNATURES[name])
            declarations.append(f'(import "wasi_snapshot_preview1" "{name}" (func ${name} (param {types}) (result i32)))')
        # Scratch at 3072 is separate from recorded statuses and payload buffers.
        find = '''(func $find (param $name i32) (param $len i32) (result i32)
          (local $fd i32) (local $i i32) (local $equal i32) (local $err i32)
          i32.const 3 local.set $fd
          block $missing loop $next
            local.get $fd i32.const 1024 i32.ge_u if unreachable end
            local.get $fd i32.const 3072 call $fd_prestat_get local.tee $err
            i32.const 8 i32.eq br_if $missing
            local.get $err if unreachable end
            i32.const 3076 i32.load local.get $len i32.eq if
              local.get $len i32.const 512 i32.gt_u if unreachable end
              local.get $fd i32.const 3080 local.get $len call $fd_prestat_dir_name if unreachable end
              i32.const 0 local.set $i i32.const 1 local.set $equal
              block $done loop $compare
                local.get $i local.get $len i32.ge_u br_if $done
                local.get $name local.get $i i32.add i32.load8_u
                i32.const 3080 local.get $i i32.add i32.load8_u i32.ne
                if i32.const 0 local.set $equal end
                local.get $i i32.const 1 i32.add local.set $i br $compare
              end end
              local.get $equal if local.get $fd return end
            end
            local.get $fd i32.const 1 i32.add local.set $fd br $next
          end end i32.const -1)'''
        initial = ''.join('\\ff' for _ in range(4 * len(self.statuses)))
        return '(module\n' + '\n'.join(declarations) + '\n(memory (export "memory") 1)\n' + find + '\n' + '\n'.join(self.data) + f'\n(data (i32.const 0) "{initial}")\n(func (export "run") ' + ' '.join(f'(local ${x} i32)' for x in sorted(self.locals)) + ' (local $rd_cookie i64)\n' + '\n'.join(self.body) + '))'


def f09_memory(observed):
    assert observed['instantiated'] is True, observed
    assert observed['trapped'] is False, observed
    return bytes.fromhex(observed['memory'])


def f09_uint(mem, ptr, bits=32):
    return struct.unpack_from('<Q' if bits == 64 else '<I', mem, ptr)[0]


def f09_statuses(guest, mem, failures=None):
    failures = {} if failures is None else failures
    for label, ptr in guest.statuses.items():
        assert f09_uint(mem, ptr) == failures.get(label, 0), (label, f09_uint(mem, ptr))


def f09_dirents(mem, ptr, used):
    """Decode complete WASI dirents without assuming directory order or inode."""
    end = ptr + used
    assert end <= len(mem)
    entries = {}
    while ptr < end:
        assert ptr + 24 <= end, 'Truncated dirent header'
        _, _, size, kind = struct.unpack_from('<QQIB', mem, ptr)
        ptr += 24
        assert ptr + size <= end, 'Truncated dirent name'
        name = mem[ptr:ptr+size]
        assert name not in entries
        entries[name] = kind
        ptr += size
    return entries


def consumer_sources():
    return {'F09': (F02_ZIG.replace('return f02_main(argc, argv);', 'return f09_main(argc, argv);')
                + F03_ZIG + '\nextern fn f09_main(c_int,[*][*:0]u8) c_int;\n', F02_C + F03_C + F09_C, ('v3_0',))}
