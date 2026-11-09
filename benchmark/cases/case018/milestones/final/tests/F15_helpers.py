# feature: F15
"""Small native value-flow workloads and public analysis setup."""
from F08_helpers import compile_procedure_program
from F07_helpers import symbol_address
from F09_helpers import recovery_options


def valueflow_program(directory, bound=9):
    return compile_procedure_program(directory, '''
.type _start,@function
 call choose
.global after_choose
after_choose:
 add $3,%eax
 ret
.size _start,.-_start
.global choose, arm_zero, arm_one, joined
.type choose,@function
choose:
 test %edi,%edi
 jz arm_zero
arm_one:
 mov $19,%eax
 movl $41,datum(%rip)
 jmp joined
arm_zero:
 mov $7,%eax
 movl $23,datum(%rip)
 jmp joined
joined:
 add $5,%eax
 ret
.size choose,.-choose
.global reset_loop, loop_head, loop_body, loop_reset, loop_next, loop_exit
.type reset_loop,@function
reset_loop:
 xor %eax,%eax
 xor %ecx,%ecx
loop_head:
 cmp %edi,%ecx
 jae loop_exit
loop_body:
 add $1,%eax
 cmp $BOUND,%eax
 jbe loop_next
loop_reset:
 xor %eax,%eax
loop_next:
 add $1,%ecx
 jmp loop_head
loop_exit:
 ret
.size reset_loop,.-reset_loop
.data
.global datum
.balign 8
datum: .quad 0
'''.replace('BOUND', str(bound)), name='F15_valueflow')


def analyze_values(project, entry, depth, argument, **settings):
    address = symbol_address(project, entry)
    cfg = project.analyses.CFGFast(**recovery_options())
    state = project.factory.blank_state(addr=address, mode='static')
    from velnora import options
    state.options.discard(options.OPTIMIZE_IR)
    state.regs.rdi = argument.zero_extend(32)
    return project.analyses.VFG(cfg, start=address, function_start=address,
        initial_state=state, interfunction_level=depth,
        context_sensitivity_level=1, record_function_final_states=True, **settings)


def exit_values(analysis, address):
    states = list(analysis.function_final_states[address].values())
    assert states, 'No abstract function exits were recorded'
    return states
