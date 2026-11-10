# feature: F14
"""Acceptance observations for data flow, dependencies, and slicing."""
import networkx as nx
from F14_helpers import (dataflow_program, dataflow_function, reaching, before,
                         defining_instructions, recorded_cfg, replacement_values,
                         destination_definition)
from F07_helpers import symbol_address


def test_partial_overwrites_definitions_and_uses(tmp_path):
    p = dataflow_program(tmp_path)
    a = lambda label: symbol_address(p, label)
    rda = reaching(p, '_start')
    for use, kind, offset, patch_size, width, old, patch, dest in [
        ('reg_use', 'register', p.arch.registers['rax'][0], 1, 4, 'reg_old', 'reg_patch', 'rbx'),
        ('stack_use', 'stack', -8, 2, 4, 'stack_old', 'stack_patch', 'rcx'),
        ('mem_use', 'memory', a('datum'), 2, 4, 'mem_old', 'mem_patch', 'rdx'),
    ]:
        observation = before(rda, p, use)
        reader = getattr(observation, 'get_' + kind + '_definitions')
        overwritten = reader(offset, patch_size)
        retained = reader(offset + patch_size, width - patch_size)
        assert defining_instructions(overwritten) == {a(patch)}
        assert defining_instructions(retained) == {a(old)}
        used = rda.all_uses.get_uses_by_insaddr(a(use))
        assert overwritten | retained <= used
        destination = destination_definition(rda, a(use), p.arch.registers[dest][0])
        ancestors = rda.dep_graph.find_all_predecessors(destination)
        assert overwritten | retained <= set(ancestors)


def test_join_preserves_only_incoming_definitions(tmp_path):
    p = dataflow_program(tmp_path)
    a = lambda label: symbol_address(p, label)
    rda = reaching(p, 'diamond')
    offset = p.arch.registers['rax'][0]
    definitions = before(rda, p, 'read_join').get_register_definitions(offset, 4)
    assert defining_instructions(definitions) == {a('initial'), a('left')}
    assert rda.all_uses.get_uses_by_insaddr(a('read_join')) == definitions
    for definition in definitions:
        assert a('read_join') in {location.ins_addr for location in rda.all_uses.get_uses(definition)}
    dest = destination_definition(rda, a('read_join'), p.arch.registers['rbx'][0])
    assert defining_instructions(rda.dep_graph.find_all_predecessors(dest)) == {a('initial'), a('left')}


def test_constants_registers_memory_and_live_old_path(tmp_path):
    from velnora.analyses.propagator.vex_vars import VEXReg, VEXMemVar
    p = dataflow_program(tmp_path)
    a = lambda label: symbol_address(p, label)
    prop = p.analyses.Propagator(func=dataflow_function(p, 'constants'), only_consts=True)
    reg = lambda name: VEXReg(*p.arch.registers[name])
    assert replacement_values(prop, a('const_old'), reg('rax')) == {11}
    assert replacement_values(prop, a('const_new'), reg('rax')) == {31}
    assert replacement_values(prop, a('const_store'), reg('rax')) == {37}
    assert replacement_values(prop, a('const_store'), VEXMemVar(a('datum'), 4)) == {37}
    assert replacement_values(prop, a('const_load'), reg('rcx')) == {83}
    # The 37 store is not forwarded: the later load sees the image's datum.
    assert replacement_values(prop, a('const_reload'), reg('rdx')) == {5}
    prop = p.analyses.Propagator(func=dataflow_function(p, 'diamond'), only_consts=True)
    assert replacement_values(prop, a('right'), reg('rcx')) == {7}
    assert replacement_values(prop, a('left'), reg('rax')) == {19}


def test_recorded_data_and_address_dependencies(tmp_path):
    p = dataflow_program(tmp_path)
    a = lambda label: symbol_address(p, label)
    cfg = recorded_cfg(p, 'deps')
    graph = p.analyses.DDG(cfg, start=a('deps')).graph
    # Find the public memory edge, then follow its two classified inputs.
    memory_edges = [(src, dst) for src, dst, data in graph.edges(data=True)
                    if src.ins_addr == a('dep_store') and dst.ins_addr == a('dep_load')
                    and data['type'] == 'mem']
    assert len(memory_edges) == 1
    store, load = memory_edges[0]
    for destination, subtype, origin in [(store, 'mem_addr', 'addr_def'),
                                         (store, 'mem_data', 'data_def'),
                                         (load, 'mem_addr', 'addr_def')]:
        sources = [src for src, _, data in graph.in_edges(destination, data=True)
                   if subtype in data.get('subtype', ())]
        assert sources
        origins = {node.ins_addr for src in sources
                   for node in nx.ancestors(graph, src) | {src}}
        assert a(origin) in origins
        other = 'data_def' if origin == 'addr_def' else 'addr_def'
        assert a(other) not in origins


def test_branch_control_dependencies(tmp_path):
    p = dataflow_program(tmp_path)
    a = lambda label: symbol_address(p, label)
    cfg = recorded_cfg(p, 'flow')
    graph = p.analyses.CDG(cfg, start=a('flow')).graph
    assert {(src.addr, dst.addr) for src, dst in graph.edges()} == {
        (a('fork'), a('arm_a')), (a('fork'), a('arm_b')),
        (a('merge'), a('target')), (a('merge'), a('escape')),
    }


def test_target_control_flow_backward_slice(tmp_path):
    p = dataflow_program(tmp_path)
    a = lambda label: symbol_address(p, label)
    cfg = recorded_cfg(p, 'flow')
    target = cfg.model.get_any_node(a('target'))
    sliced = p.analyses.BackwardSlice(cfg, None, None, targets=[(target, -1)], control_flow_slice=True)
    expected = {a(label) for label in ('fork', 'arm_a', 'arm_b', 'merge', 'target')}
    assert set(sliced.runs_in_slice.nodes()) == expected
    assert set(sliced.runs_in_slice.edges()) == {
        (a('fork'), a('arm_a')), (a('fork'), a('arm_b')),
        (a('arm_a'), a('merge')), (a('arm_b'), a('merge')), (a('merge'), a('target')),
    }
    annotated = sliced.annotated_cfg()
    for address in expected:
        assert annotated.get_whitelisted_statements(address) is None
    assert annotated.get_whitelisted_statements(a('escape')) == []
