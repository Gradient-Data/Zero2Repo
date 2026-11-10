# feature: F11
"""Native exploration inputs and observable state relations."""
import velnora

# The documented expression namespace is the velnora.claripy attribute.
claripy = velnora.claripy
from F08_helpers import compile_procedure_program
from F07_helpers import symbol_address


def exploration_program(directory):
    return compile_procedure_program(directory, '''
.global branch, left, right, join, finish, chain, chain1, chain2, chain3
.global loop_start, header, body, loop_exit, bad, indirect, terminate
    jmp branch
.type branch,@function
branch:
    test %edi,%edi
    jz left
right:
    mov $23,%eax
    movq $202,(%rsi)
    jmp join
left:
    mov $17,%eax
    movq $101,(%rsi)
    jmp join
join:
    add $3,%eax
    jmp finish
finish:
    jmp finish
.size branch,.-branch
.type chain,@function
chain:
    add $1,%eax
    nop
    nop
    jmp chain1
chain1:
    add $2,%eax
    nop
    nop
    jmp chain2
chain2:
    add $4,%eax
    nop
    nop
    jmp chain3
chain3:
    jmp chain3
.size chain,.-chain
.type loop_start,@function
loop_start:
    xor %eax,%eax
    jmp header
header:
    cmp %edi,%eax
    jae loop_exit
body:
    inc %eax
    jmp header
loop_exit:
    jmp finish
.size loop_start,.-loop_start
bad:
    ud2
indirect:
    jmp *%rax
terminate:
    mov $60,%eax
    xor %edi,%edi
    syscall
''', name='exploration')


def exploration_state(project, label='branch'):
    state = project.factory.blank_state(addr=symbol_address(project, label))
    state.regs.rsp = 0x7fff0000
    state.regs.rsi = 0x600000
    state.regs.rax = 0
    return state


def branch_input(project):
    state = exploration_state(project)
    value = claripy.BVS('exploration_input', 64)
    state.regs.rdi = value
    state.add_constraints(claripy.Or(value == 0, value == 4, value == 9))
    return state, value


def assert_branch_results(states, value, increment=0):
    assert states, 'No feasible branch result survived'
    inputs = set()
    for state in states:
        assert state.solver.satisfiable()
        inputs.update(state.solver.eval_upto(value, 4))
        stored = state.memory.load(0x600000, 8, endness=state.arch.memory_endness)
        for x, register, memory in ((0, 17 + increment, 101),
                                     (4, 23 + increment, 202),
                                     (9, 23 + increment, 202)):
            if state.solver.satisfiable(extra_constraints=[value == x]):
                assert not state.solver.satisfiable(extra_constraints=[
                    value == x, claripy.Or(state.regs.rax != register, stored != memory)])
    assert inputs == {0, 4, 9}
