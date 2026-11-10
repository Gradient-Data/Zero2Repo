# feature: F14
"""Native data-flow workloads and readers of public analysis results."""
from F08_helpers import compile_procedure_program
from F07_helpers import symbol_address
from F09_helpers import recovery_options


def dataflow_program(directory):
    return compile_procedure_program(directory, '''
.global reg_old, reg_patch, reg_use, stack_old, stack_patch, stack_use
.global mem_old, mem_patch, mem_use, finish
.type _start,@function
reg_old: mov $0x11223344,%eax
reg_patch: mov $0x55,%al
reg_use: mov %eax,%ebx
stack_old: movl $0x12345678,-8(%rsp)
stack_patch: movw $0x6677,-8(%rsp)
stack_use: mov -8(%rsp),%ecx
mem_old: movl $0x21324354,datum(%rip)
mem_patch: movw $0x7788,datum(%rip)
mem_use: mov datum(%rip),%edx
finish: ret
.size _start,.-_start
.global diamond, initial, branch, left, right, join, read_join, end_join
.type diamond,@function
diamond:
 mov $3,%eax
initial: mov $7,%eax
branch: test %edi,%edi
 jz right
left: mov $19,%eax
 jmp join
right: mov %eax,%ecx
 jmp join
join:
read_join: mov %eax,%ebx
end_join: ret
.size diamond,.-diamond
.global constants, const_old, const_new, const_add, const_store, const_reload, const_load, const_end
.type constants,@function
constants:
const_old: mov $11,%eax
const_new: mov $31,%eax
const_add: add $6,%eax
const_store: mov %eax,datum(%rip)
const_reload: mov datum(%rip),%edx
const_load: mov seed(%rip),%ecx
const_end: ret
.size constants,.-constants
.global deps, addr_def, data_def, dep_store, dep_load, dep_end
.type deps,@function
deps:
addr_def: lea datum(%rip),%rdi
 jmp data_def
data_def: mov $43,%eax
 jmp dep_store
dep_store: mov %eax,(%rdi)
 jmp dep_load
dep_load: mov (%rdi),%ecx
 jmp dep_end
dep_end: ret
.size deps,.-deps
.global flow, fork, arm_a, arm_b, merge, target, escape
.type flow,@function
flow:
fork: test %edi,%edi
 jz arm_b
arm_a: mov $17,%eax
 jmp merge
arm_b: mov $29,%eax
 jmp merge
merge: test %esi,%esi
 jz escape
target: add $3,%eax
 ret
escape: mov $71,%eax
 ret
.size flow,.-flow
.data
.global datum, seed
.balign 8
datum: .quad 5
seed: .long 83
''', name='F14_dataflow')


def dataflow_function(project, name):
    cfg = project.analyses.CFGFast(**recovery_options())
    return cfg.kb.functions[symbol_address(project, name)]


def reaching(project, name):
    return project.analyses.ReachingDefinitions(subject=dataflow_function(project, name),
                                                observe_all=True, dep_graph=True)


def before(rda, project, label):
    from velnora.knowledge_plugins.key_definitions.constants import OP_BEFORE
    return rda.observed_results['insn', symbol_address(project, label), OP_BEFORE]


def defining_instructions(definitions):
    return {definition.codeloc.ins_addr for definition in definitions}


def recorded_cfg(project, entry):
    import velnora
    return project.analyses.CFGEmulated(starts=[symbol_address(project, entry)],
        context_sensitivity_level=0, keep_state=True, state_add_options=velnora.options.refs)


def replacement_values(prop, address, variable):
    """All concrete replacements of an operand at a selected instruction."""
    return {value.concrete_value for location, replacements in prop.replacements.items()
            if location.ins_addr == address
            for operand, value in replacements.items() if operand == variable}


def destination_definition(rda, address, register_offset):
    from velnora.knowledge_plugins.key_definitions.atoms import Register
    matches = [definition for definition in rda.dep_graph.graph.nodes()
               if definition.codeloc.ins_addr == address
               and isinstance(definition.atom, Register)
               and definition.atom.reg_offset == register_offset]
    assert len(matches) == 1, matches
    return matches[0]
