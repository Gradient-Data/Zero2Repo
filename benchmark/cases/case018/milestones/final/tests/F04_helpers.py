# feature: F04
"""Real executable inputs and bounded execution for execution-state checks."""
from _helpers import run_command, require_tools


def build_state_program(directory):
    compiler = require_tools("gcc")["gcc"]
    library = directory / "F04_init.c"
    library.write_text('''
unsigned long initialized = 0;
__attribute__((constructor)) static void initialize(void) { initialized = 0x6942; }
unsigned long get_initialized(void) { return initialized; }
''')
    assembly = directory / "F04_entry.S"
    assembly.write_text('''
.text
.global _start, observed, compute
_start:
    mov (%rsp), %rax
    mov 16(%rsp), %rdx
    movzbl (%rdx), %ebx
    mov 32(%rsp), %rdx
    movzbl 4(%rdx), %ecx
observed:
    jmp observed
compute:
    lea (%rdi,%rsi,2), %rax
    ret
.section .note.GNU-stack,"",@progbits
''')
    output = directory / "F04_process.elf"
    commands = (
        (compiler, "-shared", "-fPIC", "-nostdlib", "-o", directory / "libF04.so", library),
        (compiler, "-nostdlib", "-no-pie", "-o", output, assembly,
         "-L" + str(directory), "-Wl,--no-as-needed", "-lF04", "-Wl,-rpath,$ORIGIN"),
    )
    for command in commands:
        result = run_command(command)
        assert result.returncode == 0, result.stderr.decode()
    return output


def reach_address(project, state, address, limit=80):
    manager = project.factory.simulation_manager(state)
    manager.explore(find=address, n=limit)
    assert not manager.errored, [record.error for record in manager.errored]
    assert len(manager.found) == 1, "Execution did not reach the requested observation address"
    return manager.found[0]
