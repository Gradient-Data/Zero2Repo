# feature: F09
"""Acceptance checks for recovered control flow and inspectable knowledge."""
import asyncio

from _helpers import import_product
from F07_helpers import symbol_address
from F09_helpers import (knowledge_program, recovery_options, flow_edges,
                         function_edges, permission_image, disassembly_session, java_flow_program)


def test_static_blocks_functions_and_queries(tmp_path):
    p = knowledge_program(tmp_path)
    a = lambda name: symbol_address(p, name)
    cfg = p.analyses.CFGFast(**recovery_options(function_starts=[a('choose')], retedges=True))
    edges = flow_edges(cfg)
    for src, dst, kind in [('_start', 'call_a', 'Ijk_Boring'), ('_start', 'call_b', 'Ijk_Boring'),
                           ('call_a', 'worker', 'Ijk_Call'), ('call_b', 'worker', 'Ijk_Call'),
                           ('worker', 'after_a', 'Ijk_Ret'), ('worker', 'after_b', 'Ijk_Ret'),
                           ('choose', 'choose_zero', 'Ijk_Boring'),
                           ('choose', 'choose_nonzero', 'Ijk_Boring')]:
        assert (a(src), a(dst), kind) in edges
    main, worker = cfg.kb.functions[p.entry], cfg.kb.functions[a('worker')]
    assert worker.returning is True
    assert {a('call_a'), a('call_b')} <= set(main.get_call_sites())
    for site, continuation in [('call_a', 'after_a'), ('call_b', 'after_b')]:
        assert main.get_call_target(a(site)) == a('worker')
        assert main.get_call_return(a(site)) == a(continuation)
    assert a('worker') in set(cfg.kb.functions.callgraph.successors(p.entry))
    assert p.entry in set(cfg.kb.functions.callgraph.predecessors(a('worker')))
    node = cfg.model.get_any_node(a('choose_zero'))
    assert node.function_address == a('choose')
    assert cfg.kb.functions.floor_func(a('choose_zero')).addr == a('choose')
    assert a('choose') in {n.addr for n in cfg.model.get_predecessors(node)}
    assert {a('choose_zero'), a('choose_nonzero')} <= {
        n.addr for n in cfg.model.get_successors(cfg.model.get_any_node(a('choose')))}


def test_scope_and_disabled_scanning_follow_direct_flow(tmp_path):
    p = knowledge_program(tmp_path)
    a = lambda name: symbol_address(p, name)
    cfg = p.analyses.CFGFast(**recovery_options(
        regions=[(a('choose'), a('dispatch'))], function_starts=[a('choose')],
        symbols=False, start_at_entry=False))
    assert {n.addr for n in cfg.model.graph} == {a('choose'), a('choose_zero'), a('choose_nonzero')}
    assert {(src, dst) for src, dst, _ in flow_edges(cfg)} == {
        (a('choose'), a('choose_zero')), (a('choose'), a('choose_nonzero'))}
    # The same scan controls still follow a direct call to a supplied-scope callee.
    cfg = p.analyses.CFGFast(**recovery_options(
        regions=[(p.entry, a('choose'))], function_starts=[p.entry],
        symbols=False, start_at_entry=False))
    assert (a('call_a'), a('worker'), 'Ijk_Call') in flow_edges(cfg)
    assert cfg.model.get_any_node(a('worker')).function_address == a('worker')
    assert all(p.entry <= n.addr < a('choose') for n in cfg.model.graph)


def test_image_without_executable_regions(tmp_path):
    live = permission_image(tmp_path, True)
    cfg = live.analyses.CFGFast(**recovery_options())
    assert cfg.model.get_any_node(live.entry).addr == live.entry
    p = permission_image(tmp_path, False)
    empty = p.analyses.CFGFast(**recovery_options())
    assert empty.regions == []
    assert list(empty.model.graph) == []
    assert list(empty.kb.functions.values()) == []


def test_emulated_context_depth_states_and_accesses(tmp_path):
    p = knowledge_program(tmp_path)
    velnora = import_product()
    a = lambda name: symbol_address(p, name)
    s = p.factory.blank_state(addr=p.entry)
    s.regs.rsp = 0x7fff0000
    s.regs.rdi = velnora.claripy.BVS('caller_branch', 64)
    s.add_constraints(velnora.claripy.Or(s.regs.rdi == 0, s.regs.rdi == 3))
    cfg = p.analyses.CFGEmulated(initial_state=s, starts=[p.entry], call_depth=3,
        context_sensitivity_level=1, keep_state=True,
        state_add_options={velnora.options.TRACK_MEMORY_ACTIONS}, max_iterations=2)
    workers = cfg.model.get_all_nodes(a('worker'))
    assert len(workers) == 2
    destinations = []
    for node in workers:
        assert node.input_state is not None
        assert node.final_states
        represented = set(node.input_state.solver.eval_upto(node.input_state.regs.rdi, 3))
        assert represented in ({0}, {3})
        returns = {dst.addr for _, dst, data in cfg.model.graph.out_edges(node, data=True)
                   if data['jumpkind'] == 'Ijk_Ret'}
        assert returns == {a('after_b') if represented == {0} else a('after_a')}
        destinations.append(returns)
        accesses = [action for state in node.final_states for action in state.history.actions
                    if action.type == 'mem' and action.action == 'read']
        assert any(state.solver.eval_one(action.addr.ast) == a('datum')
                   for state in node.final_states for action in accesses)
    assert destinations[0] != destinations[1]
    shallow = p.analyses.CFGEmulated(initial_state=s.copy(), starts=[p.entry], call_depth=0,
        context_sensitivity_level=1, keep_state=True, max_iterations=2)
    # A bounded analysis can keep a callee entry, but must not execute its body.
    assert not any(node.final_states for node in shallow.model.get_all_nodes(a('worker')))
    assert shallow.model.get_any_node(p.entry) is not None


def test_indirect_tables_and_unresolved_transfers(tmp_path):
    p = knowledge_program(tmp_path)
    a = lambda name: symbol_address(p, name)
    cfg = p.analyses.CFGFast(**recovery_options())
    table = cfg.jump_tables[a('table_jump')]
    targets = {a('case0'), a('case1'), a('case2')}
    assert table.jumptable_addr == a('table')
    assert table.jumptable_entries == [a('case0'), a('case1'), a('case2')]
    assert set(table.resolved_targets) == targets
    assert {dst for src, dst, _ in flow_edges(cfg) if src == a('table_jump')} == targets
    unresolved = cfg.indirect_jumps[a('unknown')]
    assert set(unresolved.resolved_targets) == set()
    assert a('unknown') in cfg.kb.unresolved_indirect_jumps
    assert a('table_jump') not in cfg.kb.unresolved_indirect_jumps


def test_normalization_and_function_transition_kinds(tmp_path):
    p = knowledge_program(tmp_path)
    a = lambda name: symbol_address(p, name)
    p.hook(a('exitproc'), import_product().SIM_PROCEDURES['libc']['exit']())
    cfg = p.analyses.CFGFast(**recovery_options(normalize=True, detect_tail_calls=True, retedges=True))
    node = cfg.model.get_any_node(a('inner'))
    assert node.addr == a('inner')
    assert (a('normalized'), a('inner'), 'Ijk_Boring') in flow_edges(cfg)
    assert (a('inner'), a('inner'), 'Ijk_Boring') in flow_edges(cfg)
    for source, target in cfg.model.graph.edges():
        assert not (source.addr < target.addr < source.addr + source.size)
    main = cfg.kb.functions[p.entry]
    assert (a('call_a'), a('worker'), 'call') in function_edges(main)
    assert (a('call_a'), a('after_a'), 'fake_return') in function_edges(main)
    assert (a('after_a'), a('done'), 'transition') in function_edges(main)
    worker = cfg.kb.functions[a('worker')]
    assert a('worker') in {n.addr for n in worker.ret_sites}
    tail = cfg.kb.functions[a('tail')]
    assert any(src == a('tail') and dst == a('worker') and kind == 'transition'
               for src, dst, kind in function_edges(tail))
    assert a('worker') not in tail.block_addrs_set
    nr = cfg.kb.functions[a('no_return')]
    assert cfg.kb.functions[a('exitproc')].returning is False
    assert nr.returning is False
    assert (a('no_return'), a('exitproc'), 'call') in function_edges(nr)
    assert not any(dst == a('after_no_return') for _, dst, _ in function_edges(nr))


def test_data_references_and_knowledge_edits(tmp_path):
    p = knowledge_program(tmp_path)
    a = lambda name: symbol_address(p, name)
    cfg = p.analyses.CFGFast(**recovery_options(data_references=True, cross_references=True))
    for instruction, destination in [('worker_read', 'datum'), ('string_ref', 'message')]:
        source, target = a(instruction), a(destination)
        assert (source, target) in {(r.ins_addr, r.dst) for r in p.kb.xrefs.get_xrefs_by_dst(target)}
        assert (source, target) in {(r.ins_addr, r.dst) for r in p.kb.xrefs.get_xrefs_by_ins_addr(source)}
        assert target in cfg.model.memory_data
    data = cfg.model.memory_data[a('message')]
    assert data.content == b'control flow reference'
    function = p.kb.functions[a('choose')]
    function.name = 'selected_choice'
    assert p.kb.functions.function(name='selected_choice').addr == a('choose')
    assert p.kb.functions.function(name='choose') is None
    p.kb.labels[a('message')] = 'annotation_data'
    assert p.kb.labels.lookup('annotation_data') == a('message')
    assert p.kb.labels[a('message')] == 'annotation_data'
    assert p.kb.labels.lookup('message') is None
    p.kb.comments[a('choose')] = 'branch selection'
    assert p.kb.comments[a('choose')] == 'branch selection'
    del p.kb.comments[a('choose')]
    assert a('choose') not in p.kb.comments
    bookmark, _ = p.kb.bookmarks.add_bookmark(a('choose'), 'inspect branch')
    assert p.kb.bookmarks.get_bookmark(a('choose')).label == 'inspect branch'
    assert p.kb.bookmarks.get_bookmark(a('choose')).addr == a('choose')
    p.kb.bookmarks.remove_bookmark(bookmark)
    assert p.kb.bookmarks.get_bookmark(a('choose')) is None


def test_java_method_blocks_branches_calls_and_ownership(tmp_path):
    archive = java_flow_program(tmp_path)
    p = import_product().Project(str(archive), auto_load_libs=False,
        main_opts={'entry_point': 'F09Flow.main'})
    cfg = p.analyses.CFGFastSoot()
    methods = {f.name: f for f in cfg.kb.functions.values()}
    adjust = methods['F09Flow.choose(int)']
    run = methods['F09Flow.main(java.lang.String[])']
    nodes = [n for n in cfg.model.graph if n.function_address == adjust.addr]
    assert nodes
    assert all(n.addr.method == adjust.addr for n in nodes)
    assert any(len([dst for dst in cfg.model.graph.successors(node)
                    if dst.function_address == adjust.addr]) == 2 for node in nodes)
    assert any(src.function_address == run.addr and dst.function_address == adjust.addr
               and data['jumpkind'] == 'Ijk_Call'
               for src, dst, data in cfg.model.graph.edges(data=True))
    assert adjust.addr in set(cfg.kb.functions.callgraph.successors(run.addr))


def test_selected_function_disassembly_via_mcp(tmp_path):
    p = knowledge_program(tmp_path)
    choose, orphan = (symbol_address(p, name) for name in ('choose', 'orphan'))
    # Encodings of the assembled instructions; no expectations read from velnora.
    expected = {
        choose: {choose: ('85ff', {'test'}), choose+2: ('7406', {'je', 'jz'}),
                 choose+4: ('b811000000', {'mov'}), choose+9: ('c3', {'ret'}),
                 choose+10: ('b81d000000', {'mov'}), choose+15: ('c3', {'ret'})},
        orphan: {orphan: ('b829000000', {'mov'}), orphan+5: ('c3', {'ret'})},
    }
    selections = [({'name': 'choose'}, choose), ({'address': hex(choose)}, choose),
                  ({'name': 'orphan'}, orphan)]
    asyncio.run(asyncio.wait_for(disassembly_session(p.filename, selections, expected), timeout=120))
