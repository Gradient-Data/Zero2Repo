# feature: F01
"""Public C/Zig consumers for module acceptance tests.

Run pytest with the product checkout as cwd, or set NAVOR_ROOT explicitly.
The case image supplies Zig, a C toolchain, wasm-tools and pytest. Builds are
external path-dependency consumers, using the repository's public build options.
No installed library or previously compiled product output is reused.
"""
import json
import os
from pathlib import Path

import pytest

from _helpers import build_outputs, run_process, run_json_adapter


F01_BUILD = r'''
const std = @import("std");
pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});
    const level = b.option([]const u8, "wasm", "WebAssembly version").?;
    const zw = b.dependency("navor", .{
        .target = target, .optimize = optimize, .wasm = level, .wasi = "p3",
    });
    const exe = b.addExecutable(.{
        .name = "f01-probe",
        .root_module = b.createModule(.{
            .root_source_file = b.path("probe.zig"),
            .target = target, .optimize = optimize, .link_libc = true,
        }),
    });
    exe.root_module.addImport("navor", zw.module("navor"));
    exe.root_module.addIncludePath(zw.path("include"));
    exe.root_module.addCSourceFile(.{ .file = b.path("probe.c"), .flags = &.{"-std=c11", "-Wall", "-Werror"} });
    b.installArtifact(exe);
}
'''

F01_ZIG = r'''
const std = @import("std");
const zw = @import("navor");
extern fn f01_main(c_int, [*][*:0]u8) c_int;
extern fn f01_error([*:0]const u8, [*:0]const u8) c_int;
extern fn printf([*:0]const u8, ...) c_int;
extern fn f01_hex([*]const u8, usize) void;
pub export fn main(argc: c_int, argv: [*][*:0]u8) c_int {
    return f01_main(argc, argv);
}
pub export fn f01_zig_probe(ptr: [*]const u8, len: usize) c_int {
    var engine = zw.Engine.init(std.heap.c_allocator, .{}) catch |err| return f01_error("Engine.init", @errorName(err));
    defer engine.deinit();
    var module = engine.compile(ptr[0..len]) catch |err| {
        switch (err) {
            error.ParseFailed, error.ValidateFailed => {
                _ = printf("{\"loaded\":false,\"error\":\"%s\"}", @as([*:0]const u8, @errorName(err)));
                return 0;
            },
            else => return f01_error("Engine.compile", @errorName(err)),
        }
    };
    defer module.deinit();
    var imports = module.imports(std.heap.c_allocator) catch |err| return f01_error("Module.imports", @errorName(err));
    defer imports.deinit();
    var exports = module.exports(std.heap.c_allocator) catch |err| return f01_error("Module.exports", @errorName(err));
    defer exports.deinit();
    _ = printf("{\"loaded\":true,\"imports\":[");
    for (imports.items, 0..) |item, i| {
        if (i != 0) _ = printf(",");
        _ = printf("{\"module\":");
        f01_hex(item.module.ptr, item.module.len);
        _ = printf(",\"name\":");
        f01_hex(item.name.ptr, item.name.len);
        _ = printf(",\"kind\":\"%s\"}", @as([*:0]const u8, @tagName(item.kind)));
    }
    _ = printf("],\"exports\":[");
    for (exports.items, 0..) |item, i| {
        if (i != 0) _ = printf(",");
        _ = printf("{\"name\":");
        f01_hex(item.name.ptr, item.name.len);
        _ = printf(",\"kind\":\"%s\"}", @as([*:0]const u8, @tagName(item.kind)));
    }
    _ = printf("]}");
    return 0;
}
'''

F01_C = r'''
#include <wasm.h>
#include <navor.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

extern int f01_zig_probe(const unsigned char *, size_t);
int f01_error(const char *stage, const char *reason) { fprintf(stderr,"%s: %s\n",stage,reason); return 70; }
#define NEED(x) do { if (!(x)) { fprintf(stderr, "Adapter prerequisite failed at line %d: %s\n", __LINE__, #x); exit(70); } } while (0)
void f01_hex(const unsigned char *p, size_t n) {
    putchar('"');
    for (size_t i=0; i<n; i++) printf("%02x", p[i]);
    putchar('"');
}
static void name(const wasm_name_t *n) { NEED(n); f01_hex((const unsigned char*)n->data,n->size); }
static void valtypes(const wasm_valtype_vec_t *v) {
    NEED(v); putchar('[');
    for (size_t i=0;i<v->size;i++) { NEED(v->data[i]); if(i) putchar(','); printf("%u",wasm_valtype_kind(v->data[i])); }
    putchar(']');
}
static void signature(const wasm_functype_t *t) {
    NEED(t); printf("\"params\":"); valtypes(wasm_functype_params(t));
    printf(",\"results\":"); valtypes(wasm_functype_results(t));
}
static void limits(const wasm_limits_t *l) {
    NEED(l); printf("\"min\":%u,\"max\":%u",l->min,l->max);
}
static void type(const wasm_externtype_t *t) {
    NEED(t); printf("{\"kind\":%u,",wasm_externtype_kind(t));
    switch(wasm_externtype_kind(t)) {
    case WASM_EXTERN_FUNC: signature(wasm_externtype_as_functype_const(t)); break;
    case WASM_EXTERN_GLOBAL: {
        const wasm_globaltype_t *g=wasm_externtype_as_globaltype_const(t); NEED(g);
        printf("\"value\":%u,\"mutable\":%u",wasm_valtype_kind(wasm_globaltype_content(g)),wasm_globaltype_mutability(g)); break;
    }
    case WASM_EXTERN_MEMORY: limits(wasm_memorytype_limits(wasm_externtype_as_memorytype_const(t))); break;
    case WASM_EXTERN_TABLE: {
        const wasm_tabletype_t *v=wasm_externtype_as_tabletype_const(t); NEED(v);
        printf("\"element\":%u,",wasm_valtype_kind(wasm_tabletype_element(v))); limits(wasm_tabletype_limits(v)); break;
    }
    case WASM_EXTERN_TAG: signature(wasm_tagtype_functype(wasm_externtype_as_tagtype_const(t))); break;
    default: NEED(0);
    }
    putchar('}');
}
static int stock_imports = 0;
static void declarations(const wasm_module_t *m) {
    wasm_importtype_vec_t im;
    if(stock_imports) wasm_module_imports(m,&im);
    else NEED(navor_module_imports_ex(m,&im));
    wasm_exporttype_vec_t ex; wasm_module_exports(m,&ex);
    printf("{\"imports\":[");
    for(size_t i=0;i<im.size;i++) {
        NEED(im.data[i]); if(i) putchar(','); printf("{\"module\":"); name(wasm_importtype_module(im.data[i]));
        printf(",\"name\":"); name(wasm_importtype_name(im.data[i]));
        printf(",\"type\":"); type(wasm_importtype_type(im.data[i])); putchar('}');
    }
    printf("],\"exports\":[");
    for(size_t i=0;i<ex.size;i++) {
        NEED(ex.data[i]); if(i) putchar(','); printf("{\"name\":"); name(wasm_exporttype_name(ex.data[i]));
        printf(",\"type\":"); type(wasm_exporttype_type(ex.data[i])); putchar('}');
    }
    printf("]}");
    wasm_importtype_vec_delete(&im); wasm_exporttype_vec_delete(&ex);
}
static int same_name(const wasm_name_t *name, const char *wanted) {
    return name->size==strlen(wanted) && !memcmp(name->data,wanted,name->size);
}
static void execute(wasm_store_t *s, wasm_module_t *m, int seed, int argc, char **argv) {
    wasm_valtype_t *vt=wasm_valtype_new(WASM_I32); NEED(vt);
    wasm_globaltype_t *gt=wasm_globaltype_new(vt,WASM_CONST); NEED(gt);
    wasm_val_t initial={.kind=WASM_I32,.of.i32=seed};
    wasm_global_t *host=wasm_global_new(s,gt,&initial); NEED(host); wasm_globaltype_delete(gt);
    wasm_extern_t *binding=wasm_global_as_extern(host); NEED(binding);
    wasm_extern_vec_t imports={1,&binding};
    wasm_trap_t *trap=NULL;
    wasm_instance_t *inst=wasm_instance_new(s,m,&imports,&trap);
    if(trap) { wasm_message_t msg; wasm_trap_message(trap,&msg); fwrite(msg.data,1,msg.size,stderr); wasm_byte_vec_delete(&msg); }
    NEED(inst && !trap);
    wasm_extern_vec_t exports; wasm_instance_exports(inst,&exports);
    wasm_exporttype_vec_t types; wasm_module_exports(m,&types); NEED(types.size==exports.size);
    wasm_func_t *fn=NULL; wasm_global_t *global=NULL; wasm_memory_t *memory=NULL;
    for(size_t i=0;i<types.size;i++) {
        const wasm_name_t *n=wasm_exporttype_name(types.data[i]);
        if(same_name(n,"advance")) fn=wasm_extern_as_func(exports.data[i]);
        if(same_name(n,"total")) global=wasm_extern_as_global(exports.data[i]);
        if(same_name(n,"bytes")) memory=wasm_extern_as_memory(exports.data[i]);
    }
    NEED(fn && global && memory);
    wasm_val_t before; wasm_global_get(global,&before);
    NEED(wasm_memory_data_size(memory)>=12);
    const unsigned char *initial_bytes=(const unsigned char*)wasm_memory_data(memory)+8;
    uint32_t initial_word=(uint32_t)initial_bytes[0]|((uint32_t)initial_bytes[1]<<8)|((uint32_t)initial_bytes[2]<<16)|((uint32_t)initial_bytes[3]<<24);
    printf("{\"initial\":{\"global_kind\":%u,\"global\":%d,\"memory\":%u},\"steps\":[",before.kind,before.of.i32,initial_word);
    for(int i=0;i<argc;i++) {
        char *end; long input=strtol(argv[i],&end,10); NEED(*end=='\0' && input>=INT32_MIN && input<=INT32_MAX);
        wasm_val_t arg={.kind=WASM_I32,.of.i32=(int32_t)input}, result={.kind=WASM_I32};
        wasm_val_vec_t args={1,&arg}, results={1,&result};
        trap=wasm_func_call(fn,&args,&results);
        if(trap) { wasm_message_t msg; wasm_trap_message(trap,&msg); fwrite(msg.data,1,msg.size,stderr); wasm_byte_vec_delete(&msg); }
        NEED(!trap);
        wasm_val_t state; wasm_global_get(global,&state);
        NEED(wasm_memory_data_size(memory)>=12); const unsigned char *p=(const unsigned char*)wasm_memory_data(memory)+8;
        uint32_t word=(uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
        if(i) putchar(','); printf("{\"kind\":%u,\"result\":%d,\"global_kind\":%u,\"global\":%d,\"memory\":%u}",result.kind,result.of.i32,state.kind,state.of.i32,word);
    }
    printf("]}");
    wasm_exporttype_vec_delete(&types); wasm_extern_vec_delete(&exports);
    wasm_instance_delete(inst); wasm_global_delete(host);
}

static wasm_byte_vec_t read_binary(const char *path) {
    FILE *file=fopen(path,"rb"); NEED(file);
    NEED(!fseek(file,0,SEEK_END)); long size=ftell(file); NEED(size>=0); rewind(file);
    char *data=malloc((size_t)size+1); NEED(data);
    NEED(fread(data,1,(size_t)size,file)==(size_t)size); NEED(!fclose(file));
    return (wasm_byte_vec_t){(size_t)size,data};
}
static int serialize_batch(int argc, char **argv) {
    NEED(argc>=6);
    char *end; long seed=strtol(argv[2],&end,10); NEED(!*end && seed>=INT32_MIN && seed<=INT32_MAX);
    long count=strtol(argv[3],&end,10); NEED(!*end && count>0 && count<argc-4);
    int arg_count=argc-4-(int)count; char **args=argv+4+count;
    wasm_engine_t *engine=wasm_engine_new(); NEED(engine);
    wasm_store_t *store=wasm_store_new(engine); NEED(store);
    wasm_byte_vec_t *blobs=calloc((size_t)count,sizeof(*blobs)); NEED(blobs);
    printf("{\"originals\":[");
    for(long i=0;i<count;i++) {
        wasm_byte_vec_t bytes=read_binary(argv[4+i]);
        bool valid=wasm_module_validate(store,&bytes);
        wasm_module_t *module=wasm_module_new(store,&bytes); free(bytes.data);
        NEED(valid && module);
        if(i) putchar(','); printf("{\"declarations\":"); declarations(module);
        printf(",\"execution\":"); execute(store,module,(int)seed,arg_count,args); putchar('}');
        wasm_module_serialize(module,&blobs[i]);
        wasm_module_delete(module);
    }
    printf("],\"restored\":[");
    /* Restore in insertion order after all serializations, then repeat the
       first blob: a single last-module slot cannot satisfy this lifecycle. */
    for(long i=0;i<=count;i++) {
        long index=i%count;
        wasm_module_t *module=wasm_module_deserialize(store,&blobs[index]); NEED(module);
        if(i) putchar(','); printf("{\"declarations\":"); declarations(module);
        printf(",\"execution\":"); execute(store,module,(int)seed,arg_count,args); putchar('}');
        wasm_module_delete(module);
    }
    printf("]}\n");
    for(long i=0;i<count;i++) wasm_byte_vec_delete(&blobs[i]);
    free(blobs); wasm_store_delete(store); wasm_engine_delete(engine); return 0;
}

int f01_main(int argc,char **argv) {
    NEED(argc>=3);
    stock_imports = !strcmp(argv[1],"stock");
    if(!strcmp(argv[1],"serialize-batch")) return serialize_batch(argc,argv);
    FILE *file=fopen(argv[2],"rb"); NEED(file); NEED(!fseek(file,0,SEEK_END)); long size=ftell(file); NEED(size>=0); rewind(file);
    char *data=malloc((size_t)size+1); NEED(data); NEED(fread(data,1,(size_t)size,file)==(size_t)size); NEED(!fclose(file));
    if(!strcmp(argv[1],"zig")) { int status=f01_zig_probe((const unsigned char*)data,(size_t)size); free(data); return status; }
    wasm_engine_t *e=wasm_engine_new(); NEED(e); wasm_store_t *s=wasm_store_new(e); NEED(s);
    wasm_byte_vec_t bytes={(size_t)size,data};
    bool valid=wasm_module_validate(s,&bytes); wasm_module_t *m=wasm_module_new(s,&bytes); free(data);
    printf("{\"valid\":%s,\"loaded\":%s",valid?"true":"false",m?"true":"false");
    if(m) { printf(",\"declarations\":"); declarations(m); }
    if(!strcmp(argv[1],"serialize") || !strcmp(argv[1],"share")) {
        NEED(m && argc>=5); char *end; long seed=strtol(argv[3],&end,10); NEED(!*end && seed>=INT32_MIN && seed<=INT32_MAX);
        printf(",\"original\":"); execute(s,m,(int)seed,argc-4,argv+4);
        wasm_store_t *other=NULL; wasm_module_t *copy=NULL;
        if(!strcmp(argv[1],"serialize")) {
            wasm_byte_vec_t blob; wasm_module_serialize(m,&blob);
            copy=wasm_module_deserialize(s,&blob); wasm_byte_vec_delete(&blob);
        } else {
            wasm_shared_module_t *shared=wasm_module_share(m); NEED(shared);
            other=wasm_store_new(e); NEED(other); copy=wasm_module_obtain(other,shared); wasm_shared_module_delete(shared);
        }
        NEED(copy); wasm_module_delete(m); m=NULL;
        if(other) { wasm_store_delete(s); s=NULL; }
        printf(",\"copy_declarations\":"); declarations(copy);
        printf(",\"copy\":"); execute(other?other:s,copy,(int)seed,argc-4,argv+4);
        wasm_module_delete(copy); if(other) wasm_store_delete(other);
    } else { NEED(!strcmp(argv[1],"c") || stock_imports); }
    printf("}\n");
    if(m) wasm_module_delete(m); if(s) wasm_store_delete(s); wasm_engine_delete(e); return 0;
}
'''


class F01Driver:
    def __init__(self, root, directory, session):
        self.root = root
        self.directory = directory
        self.programs = {}
        self.session = session
        self.serial = 0

    @property
    def plan(self):
        if not hasattr(self.session, '_consumer_build_plan'):
            from _helpers import BuildPlan
            from importlib import import_module
            sources = {}
            for feature in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 14, 15, 16, 17, 18):
                sources.update(import_module(f"F{feature:02d}_helpers").consumer_sources())
            from F11_helpers import F11_BUILD, F11_VERSION_C, F11_VERSION_ZIG
            self.session._consumer_build_plan = BuildPlan(self.root, self.directory / "build-plan", sources,
                                   (F11_BUILD, F11_VERSION_ZIG, F11_VERSION_C))
            self.session.addfinalizer(self.session._consumer_build_plan.close)
        if self.session._consumer_build_plan.root != self.root.resolve():
            raise AssertionError("Consumer checkout changed within the pytest session")
        return self.session._consumer_build_plan

    def program(self, level):
        return self.plan.consumer('F01', level=level)

    def wat(self, source):
        result = run_process(["wasm-tools", "parse", "-"], input_bytes=source.encode(), timeout=30)
        assert result.returncode == 0, result.stderr.decode()
        return result.stdout

    def standard_valid(self, binary, features="all"):
        result = run_process(["wasm-tools", "validate", f"--features={features}", "-"], input_bytes=binary)
        assert result.returncode in (0, 1), (result.returncode, result.stderr)
        return result.returncode == 0

    def serialize_many(self, binaries, *, seed, inputs):
        paths = []
        for binary in binaries:
            self.serial += 1
            path = self.directory / f"input-{self.serial}.wasm"
            path.write_bytes(binary)
            paths.append(path)
        command = [self.program("v3_0"), "serialize-batch", str(seed), str(len(paths)),
                   *paths, *map(str, inputs)]
        return run_json_adapter(command, timeout=30).value

    def observe(self, binary, *, level="v3_0", mode="c", seed=7, inputs=(4, -9, 12)):
        self.serial += 1
        path = self.directory / f"input-{self.serial}.wasm"
        path.write_bytes(binary)
        command = [self.program(level), mode, path]
        if mode in ("serialize", "share"):
            command.extend(map(str, (seed, *inputs)))
        result = run_json_adapter(command, timeout=30).value
        return result


@pytest.fixture(scope="session")
def f01_driver(tmp_path_factory, request):
    root = Path(os.environ.get("NAVOR_ROOT", os.getcwd())).resolve()
    assert (root / "build.zig").is_file(), f"Set NAVOR_ROOT to the product checkout: {root}"
    return F01Driver(root, tmp_path_factory.mktemp("f01-consumer"), request.session)


def f01_named(module, exports):
    """Expected basic declarations, encoded like the observation transport."""
    return {
        "imports": [{"module": namespace.encode().hex(), "name": name.encode().hex(), "kind": kind}
                    for namespace, name, kind in module],
        "exports": [{"name": name.encode().hex(), "kind": kind} for name, kind in exports],
    }


class F01BinaryReader:
    """Bounded reader for the Core binary grammar, used only on test inputs."""

    def __init__(self, data):
        self.data = data
        self.position = 0

    def take(self, size):
        end = self.position + size
        if size < 0 or end > len(self.data):
            raise ValueError("Truncated independent WebAssembly input")
        result = self.data[self.position:end]
        self.position = end
        return result

    def byte(self):
        return self.take(1)[0]

    def unsigned(self):
        value = 0
        for shift in range(0, 70, 7):
            octet = self.byte()
            value |= (octet & 127) << shift
            if octet < 128:
                return value
        raise ValueError("Oversized unsigned LEB128 in independent input")

    def name(self):
        return self.take(self.unsigned()).hex()

    def end(self):
        if self.position != len(self.data):
            raise ValueError("Trailing bytes in independent declaration section")


def f01_decode_import_export_declarations(binary):
    """Decode fixture declarations independently using Core binary sections.

    This oracle reads the input, never serialized product output or product
    source. The fixture uses function types, imports, tables, tags and exports; unsupported
    grammar raises instead of projecting or dropping unrepresentable details.
    The final integer codes are the public wasm.h representation, not binary
    opcode values. Core binary grammar: sections 1, 2, 4, 7, 13 and external types.
    """
    reader = F01BinaryReader(binary)
    if reader.take(8) != b"\x00asm\x01\x00\x00\x00":
        raise ValueError("Expected a Core binary module")
    value_kinds = {0x7f: 0, 0x7e: 1, 0x7d: 2, 0x7c: 3, 0x7b: 4, 0x70: 129, 0x6f: 128}
    extern_kinds = {0: 0, 1: 2, 2: 3, 3: 1, 4: 4}
    types = []
    indices = {kind: [] for kind in extern_kinds}
    imports = []
    exports = []

    def value(section):
        return value_kinds[section.byte()]

    def limits(section):
        flags = section.byte()
        if flags not in (0, 1):
            raise ValueError("This declaration fixture requires 32-bit non-shared limits")
        minimum = section.unsigned()
        maximum = section.unsigned() if flags else 0xffffffff
        if minimum > 0xffffffff or maximum > 0xffffffff:
            raise ValueError("Fixture limit cannot be represented by wasm_limits_t")
        return {"min": minimum, "max": maximum}

    while reader.position < len(binary):
        section_id = reader.byte()
        section = F01BinaryReader(reader.take(reader.unsigned()))
        if section_id == 0:
            # Custom metadata is outside the declaration grammar and has no type meaning.
            continue
        if section_id == 1:
            for _ in range(section.unsigned()):
                if section.byte() != 0x60:
                    raise ValueError("Expected an independent fixture function type")
                params = [value(section) for _ in range(section.unsigned())]
                results = [value(section) for _ in range(section.unsigned())]
                types.append({"params": params, "results": results})
        elif section_id == 2:
            for _ in range(section.unsigned()):
                namespace, name, kind = section.name(), section.name(), section.byte()
                descriptor = {"kind": extern_kinds[kind]}
                if kind == 0:
                    descriptor.update(types[section.unsigned()])
                elif kind == 1:
                    descriptor["element"] = value(section)
                    descriptor.update(limits(section))
                elif kind == 2:
                    descriptor.update(limits(section))
                elif kind == 3:
                    descriptor.update(value=value(section), mutable=section.byte())
                elif kind == 4:
                    if section.byte() != 0:
                        raise ValueError("Unknown exception tag attribute")
                    descriptor.update(types[section.unsigned()])
                indices[kind].append(descriptor)
                imports.append({"module": namespace, "name": name, "type": descriptor})
        elif section_id == 4:
            for _ in range(section.unsigned()):
                descriptor = {"kind": 2, "element": value(section)}
                descriptor.update(limits(section))
                indices[1].append(descriptor)
        elif section_id == 13:
            for _ in range(section.unsigned()):
                if section.byte() != 0:
                    raise ValueError("Unknown exception tag attribute")
                indices[4].append({"kind": 4, **types[section.unsigned()]})
        elif section_id == 7:
            for _ in range(section.unsigned()):
                name, kind, index = section.name(), section.byte(), section.unsigned()
                exports.append({"name": name, "type": indices[kind][index]})
        else:
            raise ValueError(f"Unexpected section in independent declaration fixture: {section_id}")
        section.end()
    return {"imports": imports, "exports": exports}


def consumer_sources():
    return {'F01': (F01_ZIG, F01_C, ('v1_0', 'v2_0', 'v3_0'))}
