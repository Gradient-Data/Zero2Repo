# feature: F08
"""Native modeled-call inputs and public result observations."""
from _helpers import require_tools, run_command, import_product


def compile_procedure_program(directory, body, name='calls'):
    source = directory / ('F08_' + name + '.S')
    source.write_text('.text\n.global _start\n_start:\n' + body + '\n.section .note.GNU-stack,"",@progbits\n')
    binary = directory / ('F08_' + name + '.elf')
    result = run_command([require_tools('gcc')['gcc'], '-nostdlib', '-no-pie', '-o', binary, source])
    assert result.returncode == 0, result.stderr
    return import_product().Project(str(binary), auto_load_libs=False)


def memory_bytes(state, address, count):
    return state.solver.eval_one(state.memory.load(address, count), cast_to=bytes)


def assert_comparison(state, result, sign):
    condition = result == 0 if sign == 0 else (result.SLT(0) if sign < 0 else result.SGT(0))
    assert state.solver.satisfiable()
    assert not state.solver.satisfiable(extra_constraints=[~condition])


def termination_code(state):
    events = [event for event in state.history.events if event.type == 'terminate']
    assert len(events) == 1
    return state.solver.eval_one(events[0].objects['exit_code'])


def exclusion_binary(directory):
    compiler = require_tools('gcc')['gcc']
    source = directory / 'F08_library.S'
    source.write_text('.text\n.global strlen\n.type strlen,@function\nstrlen:\n mov $73,%eax\n ret\n.section .note.GNU-stack,"",@progbits\n')
    library = directory / 'libc.so.6'
    result = run_command([compiler, '-shared', '-nostdlib', '-Wl,-soname,libc.so.6', '-o', library, source])
    assert result.returncode == 0, result.stderr
    source = directory / 'F08_exclude.S'
    source.write_text('''.text
.global _start, observed
_start:
 lea text(%rip),%rdi
 call strlen@PLT
observed:
 jmp observed
.data
text: .asciz "kernel"
.section .note.GNU-stack,"",@progbits
''')
    binary = directory / 'F08_exclude.elf'
    result = run_command([compiler, '-nostdlib', '-no-pie', '-o', binary, source,
                          '-L'+str(directory), '-Wl,--no-as-needed', '-l:libc.so.6', '-Wl,-rpath,$ORIGIN'])
    assert result.returncode == 0, result.stderr
    return binary
