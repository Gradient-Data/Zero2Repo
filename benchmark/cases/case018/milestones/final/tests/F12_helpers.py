# feature: F12
"""Real file inputs for recognition analyses."""
import io
import struct

from _helpers import import_product, require_tools, run_command, capture_call
from F07_helpers import symbol_address


def recognition_compile(directory, source, *, bits=32, suffix="program", c=False):
    path = directory / (suffix + (".c" if c else ".S"))
    path.write_text(source)
    binary = directory / (suffix + ".elf")
    argv = [require_tools("gcc")["gcc"], f"-m{bits}", "-nostdlib", "-no-pie",
            "-fno-pie", "-fno-stack-protector", "-fno-builtin", "-O1", "-fno-omit-frame-pointer",
            "-Wl,--build-id=none", "-o", binary, path]
    result = run_command(argv)
    assert result.returncode == 0, result.stderr
    return binary


def language_project(directory, language_code):
    # A DWARF v4 compile unit with name, compilation directory, language and address extent.
    source = f"""
.text
.global _start
_start: ret
endcode:
.section .debug_abbrev,"",@progbits
.byte 1,0x11,0, 0x03,0x08, 0x1b,0x08, 0x13,0x05, 0x11,0x01, 0x12,0x06, 0,0,0
.section .debug_info,"",@progbits
.long cuend-custart
custart:
.short 4
.long 0
.byte 4
.byte 1
.asciz "unit"
.asciz "/source"
.short {language_code}
.long _start
.long endcode-_start
cuend:
"""
    path = recognition_compile(directory, source, suffix=f"language_{language_code}")
    return import_product().Project(str(path), auto_load_libs=False, load_debug_info=True)


def zero_language_project():
    return import_product().Project(io.BytesIO(bytes(256)), auto_load_libs=False,
        main_opts={"backend": "blob", "arch": "X86", "base_addr": 0x400000,
                   "entry_point": 0x400000})


def local_signature(directory):
    # FLIRT v8: one exact seven-byte node and a callee-name condition.
    pattern = bytes.fromhex("5589e583ec08e8")
    header = struct.pack("<6sBBIHHHHH12sBH", b"IDASGN", 8, 0, 0, 0, 0,
                         0, 1, 0, bytes(12), 5, 0)
    header += struct.pack("<IH", 1, 32) + b"local"
    tree = bytes([1, len(pattern), 0]) + pattern
    tree += bytes([0, 0, 0, 0, 16, 0]) + b"recognized_wrapper" + bytes([4])
    tree += bytes([1, 7, 12]) + b"known_target"
    path = directory / "local.sig"
    path.write_bytes(header + tree)
    return path


def signature_project(directory):
    source = """
.text
.global _start, good, wrong_ref, wrong_byte, target, other
_start:
call good
call wrong_ref
call wrong_byte
ret
good:
push %ebp
mov %esp,%ebp
sub $8,%esp
call target
leave
ret
wrong_ref:
push %ebp
mov %esp,%ebp
sub $8,%esp
call other
leave
ret
wrong_byte:
push %ebp
mov %esp,%ebp
sub $12,%esp
call target
leave
ret
target: mov $7,%eax
ret
other: mov $9,%eax
ret
.space 512
"""
    path = recognition_compile(directory, source, suffix="signature")
    p = import_product().Project(str(path), auto_load_libs=False)
    addresses = {name: symbol_address(p, name) for name in
                 ("good", "wrong_ref", "wrong_byte", "target", "other")}
    result = run_command([require_tools("strip")["strip"], "--strip-all", path])
    assert result.returncode == 0, result.stderr
    p = import_product().Project(str(path), auto_load_libs=False)
    cfg = p.analyses.CFGFast(function_starts=list(addresses.values()), normalize=True)
    cfg.functions[addresses["target"]].name = "known_target"
    cfg.functions[addresses["other"]].name = "other_target"
    return p, cfg, addresses


COMPARISON_SOURCE = """
typedef unsigned char U;
int f0(const U *a,const U *b,unsigned n) {
  for(unsigned i=0;i<n;i++) if(a[i]!=b[i]) return (int)a[i]-b[i];
  return 0;
}
int f1(const U *a,const U *b) {
  while(*a && *a==*b) {a++;b++;} return (int)*a-*b;
}
int f2(const U *a,const U *b,unsigned n) {
  while(n) {if(*a!=*b) return (int)*a-*b; if(!*a) return 0; a++;b++;n--;}
  return 0;
}
int f3(const U *a,const U *b) {
  for(;;a++,b++) {
    unsigned x=*a,y=*b;
    if(x>=65 && x<=90) x+=32;
    if(y>=65 && y<=90) y+=32;
    if(x!=y) return (int)x-y;
    if(!x) return 0;
  }
}
int f4(int x) {return x*7+11;}
__attribute__((naked)) void _start(void) {
  __asm__("mov $2,%eax; xor %ebx,%ebx; mov %esp,%ecx; mov $1,%edx; xor %esi,%esi; int $0x80; 1: jmp 1b");
}
"""


def comparison_project(directory, total=None):
    # Build the requested workload from its observed recovered-function count.
    # Synthetic syscall entries need not have a fixed count across products.
    padding_count = 0
    if total is not None:
        _, initial_cfg, _ = comparison_project(directory)
        padding_count = total - len(initial_cfg.functions)
        assert padding_count >= 0, "Requested count is smaller than the base program"
    extra = "\n".join(
        f"int pad{i}(int x) {{return x+{i+100};}}" for i in range(padding_count))
    path = recognition_compile(directory, COMPARISON_SOURCE + extra,
                               suffix="comparisons", c=True)
    p = import_product().Project(str(path), auto_load_libs=False)
    addresses = {name: symbol_address(p, name) for name in
                 ["_start"] + [f"f{i}" for i in range(5)] +
                 [f"pad{i}" for i in range(padding_count)]}
    result = run_command([require_tools("strip")["strip"], "--strip-all", path])
    assert result.returncode == 0, result.stderr
    content = bytearray(path.read_bytes())
    content[:4] = b"\x7fCGC"
    content[7] = 0x43
    path.write_bytes(content)
    p = import_product().Project(str(path), auto_load_libs=False)
    cfg = p.analyses.CFGFast(function_starts=list(addresses.values()), normalize=True,
                            start_at_entry=False, force_complete_scan=False)
    return p, cfg, addresses


def comparison_matches(project, cfg, *, require_predecessors=False):
    identifier = project.analyses.Identifier(cfg=cfg,
        require_predecessors=require_predecessors,
        only_find={"memcmp", "strcmp", "strncmp", "strcasecmp"})
    result = capture_call(identifier.run, consume=list, timeout=180)
    if result.exception is not None:
        raise result.exception
    return dict(result.value)
