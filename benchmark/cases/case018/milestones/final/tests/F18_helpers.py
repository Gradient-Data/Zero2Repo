# feature: F18
"""Real native inputs, external assembly and ELF observations."""
from io import BytesIO
from elftools.elf.elffile import ELFFile
from _helpers import import_product, require_tools, run_command


def assemble_native(directory, name, source, bits=64, entry='_start', link_flags=()):
    path = directory / (name + '.S')
    path.write_text(source)
    binary = directory / (name + '.elf')
    result = run_command([require_tools('gcc')['gcc'], f'-m{bits}', '-nostdlib',
                          '-no-pie', '-Wl,--build-id=none', f'-Wl,-e,{entry}',
                          *link_flags, '-o', binary, path])
    assert result.returncode == 0, result.stderr.decode()
    return binary


def reconstruction_input(directory, bits=64, cgc=False):
    """Two separately assembled objects deliberately have the same local name."""
    objects = []
    for name, value in [('left', 5), ('right', 17)]:
        operand = 'shared(%rip)' if bits == 64 else 'shared'
        source = directory / (name + '.S')
        source.write_text(f'''.text
.global {name}
.type {name},@function
{name}:
 mov {operand},%eax
 ret
.size {name},.-{name}
.data
.type shared,@object
shared: .long {value}
.size shared,4
''')
        obj = source.with_suffix('.o')
        result = run_command(['gcc', f'-m{bits}', '-c', '-o', obj, source])
        assert result.returncode == 0, result.stderr
        objects.append(obj)
    arg = '%edi' if bits == 64 else '%ecx'
    message = 'lea message(%rip),%rax' if bits == 64 else 'mov $message,%eax'
    source = directory / 'main.S'
    source.write_text(f'''.text
.global _start, compute, edit_point, get_message
.type _start,@function
_start:
 jmp compute
.size _start,.-_start
.type compute,@function
compute:
 imul $3,{arg},%ebx
 call left
 lea (%ebx,%eax,2),%ebx
 call right
 add %ebx,%eax
edit_point:
 add $11,%eax
 ret
.size compute,.-compute
.type get_message,@function
get_message:
 {message}
 ret
.size get_message,.-get_message
.section .rodata
.type message,@object
message: .ascii "recovered data!\\n"
.size message,16
.section .note.GNU-stack,"",@progbits
''')
    binary = directory / 'input.elf'
    result = run_command(['gcc', f'-m{bits}', '-nostdlib', '-no-pie',
                          '-Wl,--build-id=none', '-o', binary, source, *objects])
    assert result.returncode == 0, result.stderr
    if cgc:
        binary = directory / 'input.cgc'
        data = bytearray((directory / 'input.elf').read_bytes())
        data[:4] = b'\x7fCGC'
        binary.write_bytes(data)
    return import_product().Project(str(binary), auto_load_libs=False)


def linux_caller(bits):
    # The recovered functions are OS-independent. Supply a Linux caller even
    # for a CGC input, so only the represented computation/data are executed.
    if bits == 64:
        body = '''mov (%rsp),%edi
 call _start
 push %rax
 call get_message
 mov %rax,%rsi
 mov $16,%edx
 mov $1,%edi
 mov $1,%eax
 syscall
 pop %rdi
 mov $60,%eax
 syscall'''
    else:
        body = '''mov (%esp),%ecx
 call _start
 push %eax
 call get_message
 mov %eax,%ecx
 mov $16,%edx
 mov $1,%ebx
 mov $4,%eax
 int $0x80
 pop %ebx
 mov $1,%eax
 int $0x80'''
    return '\n.att_syntax prefix\n.text\n.global runner\nrunner:\n' + body + '\n'


def execute_reconstruction(directory, assembly, bits=64, name='rebuilt', link_flags=()):
    binary = assemble_native(directory, name, assembly + linux_caller(bits), bits, 'runner',
                             link_flags)
    results = [run_command([binary, *args]) for args in ([], ['argument'])]
    return binary, results


def elf_symbol_region(binary, name):
    elf = ELFFile(BytesIO(binary.read_bytes()))
    symbols = elf.get_section_by_name('.symtab').get_symbol_by_name(name)
    assert symbols and len(symbols) == 1, name
    symbol = symbols[0]
    section = elf.get_section(symbol['st_shndx'])
    offset = symbol['st_value'] - section['sh_addr']
    return symbol['st_value'], section.data()[offset:], bool(section['sh_flags'] & 1)


def inspected_instructions(project, address):
    block = project.factory.block(address)
    return [(ins.address, ins.size, ins.mnemonic, ins.op_str)
            for ins in block.capstone.insns]
