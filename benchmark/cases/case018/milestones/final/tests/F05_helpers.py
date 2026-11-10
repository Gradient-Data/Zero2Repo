# feature: F05
"""Public procedure calls and executable inputs for process I/O checks."""
from _helpers import run_command, require_tools
from F01_helpers import expression_api


def invoke_procedure(state, library, name, *arguments):
    velnora, _ = expression_api()
    procedure = velnora.SIM_PROCEDURES[library][name]()
    state.scratch.sim_procedure = procedure
    return procedure.execute(state, arguments=list(arguments)).ret_expr


def request_root(state, path):
    state.memory.store(0x620000, path + b"\0")
    return state.solver.eval(invoke_procedure(state, "posix", "chroot", 0x620000), signed=True)


def file_bytes(state, path):
    file = state.fs.get(path)
    assert file is not None, f"Expected simulated file at {path!r}"
    return file.concretize()


def build_io_program(directory, environment=False):
    compiler = require_tools("gcc")["gcc"]
    source = directory / "F05_process.S"
    if environment:
        body = '''
    lea present(%rip), %rdi
    call getenv
    mov %rax, results(%rip)
    lea empty(%rip), %rdi
    call getenv
    mov %rax, results+8(%rip)
    lea missing(%rip), %rdi
    call getenv
    mov %rax, results+16(%rip)
.global observed
observed:
    mov results(%rip), %rax
    movzbl (%rax), %edi
    call exit
getenv: ret
exit: ret
.data
present: .asciz "COLOR"
empty: .asciz "EMPTY"
missing: .asciz "ABSENT"
.global results
results: .quad 0,0,0
'''
    else:
        body = '''
    xor %eax, %eax
    xor %edi, %edi
    lea buffer(%rip), %rsi
    mov $3, %edx
    syscall
    xorb $32, buffer(%rip)
    mov $1, %eax
    mov $1, %edi
    lea buffer(%rip), %rsi
    mov $3, %edx
    syscall
    mov $1, %eax
    mov $2, %edi
    lea diagnostic(%rip), %rsi
    mov $4, %edx
    syscall
    mov $60, %eax
    mov $19, %edi
    syscall
.data
buffer: .space 8
diagnostic: .ascii "diag"
'''
    source.write_text('.text\n.global _start\n_start:\n' + body +
                      '\n.section .note.GNU-stack,"",@progbits\n')
    output = directory / "F05_process.elf"
    result = run_command([compiler, "-nostdlib", "-no-pie", "-o", output, source])
    assert result.returncode == 0, result.stderr.decode()
    return output


def finish_process(project, state):
    manager = project.factory.simulation_manager(state)
    manager.run(n=80)
    assert not manager.errored, [record.error for record in manager.errored]
    assert not manager.active, "Process did not terminate within the execution bound"
    assert len(manager.deadended) == 1
    return manager.deadended[0]
