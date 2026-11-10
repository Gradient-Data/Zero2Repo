# feature: F10
"""Real instrumentation workload and bounded public successor observations."""
from F08_helpers import compile_procedure_program
from F07_helpers import symbol_address


def instrumentation_program(directory):
    return compile_procedure_program(directory, '''
.global write_site, call_site, resumed, outer, inner, outer_resume, done
.global branch_start, left, right, modeled, modeled_end, syscall_start, syscall_end
    mov (%rdi),%rax
    add $7,%rax
write_site:
    mov %rax,(%rdi)
call_site:
    call outer
resumed:
    jmp done
outer:
    call inner
outer_resume:
    add $2,%rax
    ret
inner:
    add $3,%rax
    ret
done:
    jmp done
branch_start:
    test %rdi,%rdi
    jz left
right:
    mov $23,%eax
    jmp modeled
left:
    mov $17,%eax
    jmp modeled
modeled:
    .rept 5
    nop
    .endr
modeled_end:
    jmp done
syscall_start:
    mov $3,%eax
    mov $2,%edi
    syscall
syscall_end:
    jmp done
''', name='instrumentation')


def instrumentation_state(project, entry='_start', **kwargs):
    state = project.factory.blank_state(addr=symbol_address(project, entry), **kwargs)
    # Activate public frame tracking before execution so call/return events exist.
    state.get_plugin('callstack')
    state.regs.rsp = 0x7fff0000
    state.regs.rdi = 0x600000
    state.memory.store(0x600000, (11).to_bytes(8, 'little'))
    return state


def single_successor(project, state, **kwargs):
    result = project.factory.successors(state, **kwargs)
    assert len(result.flat_successors) == 1
    return result.flat_successors[0]


def walk_to(project, state, address, limit=12):
    for _ in range(limit):
        if state.addr == address:
            return state
        state = single_successor(project, state)
    raise AssertionError('Execution did not reach the observation address')


def concrete_value(state, expression):
    return expression if isinstance(expression, (int, str)) else state.solver.eval_one(expression)
