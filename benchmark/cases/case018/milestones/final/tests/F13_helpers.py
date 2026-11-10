# feature: F13
"""Build real native inputs for variable and debug-information recovery."""
from _helpers import import_product, require_tools, run_command
from F07_helpers import symbol_address
from F09_helpers import recovery_options


def variable_program(directory, bits=64):
    if bits == 64:
        body = '''
    sub $32,%rsp
write_a: mov %edi,8(%rsp)
write_b: mov %rsi,16(%rsp)
read_a: mov 8(%rsp),%eax
read_b: mov 16(%rsp),%rdx
ref_a: lea 8(%rsp),%rcx
    add %edx,%eax
    add $32,%rsp
    ret
'''
        leaf = 'lea (%rdi,%rsi,2),%rax\n ret'
    else:
        body = '''
    sub $16,%esp
write_32: movl $1,4(%esp)
    mov 4(%esp),%eax
    add $16,%esp
    ret
'''
        leaf = 'mov 4(%esp),%eax\n mov 8(%esp),%edx\n lea (%eax,%edx,2),%eax\n ret'
    source = directory / f'F13_{bits}.S'
    source.write_text('''.text
.global _start, variables, leaf
.type _start,@function
_start: jmp _start
.size _start,.-_start
.type variables,@function
variables:
''' + body + '''
.size variables,.-variables
.type leaf,@function
leaf:
''' + leaf + '''
.size leaf,.-leaf
.section .note.GNU-stack,"",@progbits
''')
    # Export observation points as ordinary ELF symbols.
    if bits == 64:
        source.write_text('.global write_a,write_b,read_a,read_b,ref_a\n' + source.read_text())
    else:
        source.write_text('.global write_32\n' + source.read_text())
    output = source.with_suffix('.elf')
    result = run_command([require_tools('gcc')['gcc'], f'-m{bits}', '-nostdlib', '-no-pie', '-o', output, source])
    assert result.returncode == 0, result.stderr
    project = import_product().Project(str(output), auto_load_libs=False)
    project.analyses.CFGFast(normalize=True, **recovery_options())
    return project


def recovered_variables(project):
    function = project.kb.functions['variables']
    recovery = project.analyses.VariableRecoveryFast(function)
    return function, recovery, project.kb.variables[function.addr]


def debug_program(directory):
    source = directory / 'F13_debug.c'
    source.write_text('''
int global_value = 61;
struct Pair { int left; int right; };
int main(void) {
    int value = 17;
    int *pointer = &value;
    struct Pair pair = {23, 47};
    int items[3] = {5, 11, 29};
    __asm__ volatile(".global outer_point\\nouter_point: nop" ::: "memory");
    {
        int value = 83;
        __asm__ volatile(".global inner_point\\ninner_point: nop" ::: "memory");
        global_value += value;
    }
    __asm__ volatile(".global after_point\\nafter_point: nop" ::: "memory");
    return *pointer + pair.right + items[2];
}
''')
    output = source.with_suffix('.elf')
    result = run_command([require_tools('gcc')['gcc'], '-g', '-gdwarf-4', '-O0', '-fno-omit-frame-pointer',
                          '-fno-stack-protector', '-fPIE', '-pie', '-o', output, source])
    assert result.returncode == 0, result.stderr
    project = import_product().Project(str(output), auto_load_libs=False, load_debug_info=True)
    project.kb.dvars.load_from_dwarf()
    return project
