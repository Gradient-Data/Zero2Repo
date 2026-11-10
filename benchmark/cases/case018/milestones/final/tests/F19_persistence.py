# feature: F19
"""Acceptance checks for saved projects, reusable analyses and rollback."""
import json
import pickle
from pathlib import Path

from _helpers import import_product, run_python
from F07_helpers import symbol_address
from F09_helpers import knowledge_program, recovery_options
from F13_helpers import variable_program, recovered_variables
from F16_helpers import (refinement_program, decompiled, c_function, CObservation,
                         scalar_language_observation)


def test_saved_image_survives_missing_and_replaced_input(tmp_path):
    from velnora.velnoradb import VelnoraDB
    p = knowledge_program(tmp_path)
    original = Path(p.filename)
    address = symbol_address(p, 'worker')
    expected = {'arch': p.arch.name, 'entry': p.entry, 'address': address,
                'bytes': p.loader.memory.load(address, 10).hex()}
    db = tmp_path / 'image.adb'
    VelnoraDB(p, nullpool=True).dump(str(db))
    script = '''
import json, sys
from velnora.velnoradb import VelnoraDB
p = VelnoraDB(nullpool=True).load(sys.argv[1])
e = json.loads(sys.argv[2])
assert p.arch.name.casefold() == e['arch'].casefold()
assert p.entry == e['entry']
assert p.loader.memory.load(e['address'], 10).hex() == e['bytes']
s = p.factory.blank_state(addr=e['address'])
s.regs.rdi = 9
s.regs.rsp = 0x7fff0000
s.memory.store(0x7fff0000, (0x600000).to_bytes(8, 'little'))
r = p.factory.successors(s).flat_successors
assert len(r) == 1
assert r[0].addr == 0x600000
assert r[0].solver.eval_one(r[0].regs.eax) == 82
'''
    original.unlink()
    # The replacements include a loadable executable of the same architecture,
    # so reading whatever file now sits at the saved path is distinguishable.
    for replacement in (None, b'not the saved executable', Path(__file__).with_name('F02_dependent.elf').read_bytes()):
        if replacement is not None:
            original.write_bytes(replacement)
        result = run_python(script, args=[str(db), json.dumps(expected)], timeout=90)
        assert result.returncode == 0, result.stderr.decode()


def test_database_restores_functions_flow_calls_and_data_references(tmp_path):
    from velnora.velnoradb import VelnoraDB
    p = knowledge_program(tmp_path)
    addresses = {n: symbol_address(p, n) for n in
                 ('_start', 'call_a', 'call_b', 'worker', 'worker_read', 'datum',
                  'after_a', 'after_b', 'choose', 'choose_zero', 'choose_nonzero', 'message', 'string_ref')}
    p.analyses.CFGFast(normalize=True, **recovery_options(data_references=True, cross_references=True))
    db = tmp_path / 'knowledge.adb'
    VelnoraDB(p, nullpool=True).dump(str(db))
    # A separate process sees only what the saved database holds.
    fresh = run_python('''
import json, sys
from velnora.velnoradb import VelnoraDB
a = json.loads(sys.argv[2]).__getitem__
q = VelnoraDB(nullpool=True).load(sys.argv[1])
for name in ('_start', 'worker', 'choose'):
    assert q.kb.functions[a(name)].addr == a(name)
caller = q.kb.functions[a('_start')]
for site, continuation in [('call_a', 'after_a'), ('call_b', 'after_b')]:
    assert caller.get_call_target(a(site)) == a('worker')
    assert caller.get_call_return(a(site)) == a(continuation)
assert (a('_start'), a('worker')) in q.kb.callgraph.edges
cfg = q.kb.cfgs['CFGFast']
assert {a('choose_zero'), a('choose_nonzero')} == {
    n.addr for n in cfg.get_successors(cfg.get_any_node(a('choose')))}
for insn, target in [('worker_read', 'datum'), ('string_ref', 'message')]:
    assert (a(insn), a(target)) in {(r.ins_addr, r.dst) for r in q.kb.xrefs.get_xrefs_by_dst(a(target))}
assert cfg.memory_data[a('message')].content == b'control flow reference'
''', args=[str(db), json.dumps(addresses)], timeout=120)
    assert fresh.returncode == 0, fresh.stderr.decode()
    restored = VelnoraDB(nullpool=True).load(str(db))
    a = addresses.__getitem__
    cfg = restored.kb.cfgs['CFGFast']
    for name in ('_start', 'worker', 'choose'):
        assert restored.kb.functions[a(name)].addr == a(name)
    caller = restored.kb.functions[a('_start')]
    for site, continuation in [('call_a', 'after_a'), ('call_b', 'after_b')]:
        assert caller.get_call_target(a(site)) == a('worker')
        assert caller.get_call_return(a(site)) == a(continuation)
    assert (a('_start'), a('worker')) in restored.kb.callgraph.edges
    assert {a('choose_zero'), a('choose_nonzero')} == {
        n.addr for n in cfg.get_successors(cfg.get_any_node(a('choose')))}
    for insn, target in [('worker_read', 'datum'), ('string_ref', 'message')]:
        assert (a(insn), a(target)) in {(r.ins_addr, r.dst) for r in restored.kb.xrefs.get_xrefs_by_dst(a(target))}
    assert cfg.memory_data[a('message')].content == b'control flow reference'
    dec = restored.analyses.Decompiler(restored.kb.functions[a('choose')], cfg=cfg)
    assert dec.codegen is not None
    function = c_function(dec.codegen.text, 'choose')
    assert CObservation(function).run(0) == 29
    assert CObservation(function).run(4) == 17


def test_database_retains_edits_variables_and_language_associations(tmp_path):
    from velnora.velnoradb import VelnoraDB
    from velnora.knowledge_plugins import CommentKind
    from velnora.analyses.decompiler.edits import (rename_function, rename_variable,
        list_variable_names, resolve_variable, set_function_prototype)
    p, _ = refinement_program(tmp_path)
    f = p.kb.functions['arithmetic']
    addr = f.addr
    code = decompiled(p, f)
    arguments = [resolve_variable(p.kb, addr, name)
                 for name in list_variable_names(code, p.kb, addr)]
    arg = next(v for v in arguments if v.kind == 'argument' and v.arg_index == 0)
    rename_variable(p, f, arg.name, 'incoming')
    rename_function(p, f, 'saved_arithmetic')
    set_function_prototype(p, f, 'int saved_arithmetic(int incoming, int other)', redecompile=True)
    for flavor in ('pseudocode', 'rust', 'go'):
        codegen = decompiled(p, f, flavor=flavor)
        codegen.stmt_comments = {addr: 'saved ' + flavor + ' note'}
    p.kb.comments[addr] = 'saved review note'
    p.kb.comments.set_kind(addr, CommentKind.REPEATABLE)
    p.kb.bookmarks.add_bookmark(addr, 'review arithmetic')
    db = tmp_path / 'edits.adb'
    VelnoraDB(p, nullpool=True).dump(str(db))
    fresh = run_python('''
import sys
from velnora.velnoradb import VelnoraDB
from velnora.knowledge_plugins import CommentKind
from velnora.analyses.decompiler.edits import list_variable_names
addr = int(sys.argv[2])
q = VelnoraDB(nullpool=True).load(sys.argv[1])
saved = q.kb.functions.function(name='saved_arithmetic')
assert saved.addr == addr
assert tuple(saved.prototype.arg_names) == ('incoming', 'other')
assert saved.prototype.returnty.size == 32 and saved.prototype.returnty.signed is True
assert all(t.size == 32 and t.signed is True for t in saved.prototype.args)
assert q.kb.comments[addr] == 'saved review note'
assert q.kb.comments.kind_of(addr) == CommentKind.REPEATABLE
assert q.kb.bookmarks.get_bookmark(addr).label == 'review arithmetic'
assert 'incoming' in list_variable_names(q.kb.decompilations[(addr, 'pseudocode')].codegen, q.kb, addr)
for flavor in ('pseudocode', 'rust', 'go'):
    assert q.kb.decompilations[(addr, flavor)].codegen.flavor == flavor
''', args=[str(db), str(addr)], timeout=120)
    assert fresh.returncode == 0, fresh.stderr.decode()
    q = VelnoraDB(nullpool=True).load(str(db))
    saved = q.kb.functions.function(name='saved_arithmetic')
    assert saved.addr == addr
    assert len(saved.prototype.args) == 2
    assert saved.prototype.returnty.size == 32
    assert tuple(saved.prototype.arg_names) == ('incoming', 'other')
    assert saved.prototype.returnty.signed is True
    assert all(t.size == 32 and t.signed is True for t in saved.prototype.args)
    assert q.kb.comments[addr] == 'saved review note'
    assert q.kb.comments.kind_of(addr) == CommentKind.REPEATABLE
    assert q.kb.bookmarks.get_bookmark(addr).label == 'review arithmetic'
    assert 'incoming' in list_variable_names(q.kb.decompilations[(addr, 'pseudocode')].codegen, q.kb, addr)
    for flavor in ('pseudocode', 'rust', 'go'):
        cache = q.kb.decompilations[(addr, flavor)]
        assert cache.codegen.flavor == flavor
        assert cache.codegen.stmt_comments == {addr: 'saved ' + flavor + ' note'}
        # Rust persistence stores language metadata, not a rendered cache.
        text = (decompiled(q, saved, flavor=flavor, use_cache=False).text
                if flavor == 'rust' else cache.codegen.text)
        for x, y in ((0, 1), (5, 13), (17, 8)):
            value = (CObservation(c_function(text, 'saved_arithmetic')).run(x, y)
                     if flavor == 'pseudocode' else scalar_language_observation(text, flavor, (x, y)))
            assert value == (x * 3 + y) ^ 19
    rename_function(q, saved, 'continued_arithmetic')
    assert q.kb.functions.function(name='continued_arithmetic').addr == addr
    q.kb.comments[addr] = 'review continued'
    q.kb.bookmarks.get_bookmark(addr).label = 'continued bookmark'
    VelnoraDB(q, nullpool=True).dump(str(db))
    again = VelnoraDB(nullpool=True).load(str(db))
    assert again.kb.functions.function(name='continued_arithmetic').addr == addr
    assert again.kb.comments[addr] == 'review continued'
    assert again.kb.bookmarks.get_bookmark(addr).label == 'continued bookmark'


def test_execution_state_serialization_preserves_meaning_and_execution(tmp_path):
    claripy = import_product().claripy
    p = import_product().load_shellcode(b'\x03\x03\x83\xc0\x05\x90', arch='amd64', load_address=0x400000)
    s = p.factory.blank_state(addr=0x400000)
    value = claripy.BVS('saved_operand', 32)
    s.regs.eax = value
    s.regs.rbx = 0x700000
    s.memory.store(0x700000, value + 2, endness='Iend_LE')
    s.add_constraints(claripy.Or(value == 3, value == 11))
    path = tmp_path / 'state.pkl'
    path.write_bytes(pickle.dumps(s))
    result = run_python('''
import pickle, sys
with open(sys.argv[1], 'rb') as stream:
    s = pickle.load(stream)
assert s.addr == 0x400000
assert s.solver.eval_one(s.regs.rbx) == 0x700000
assert set(s.solver.eval_upto(s.regs.eax, 3)) == {3, 11}
m = s.memory.load(0x700000, 4, endness='Iend_LE')
assert set(s.solver.eval_upto(m, 3)) == {5, 13}
assert not s.solver.satisfiable(extra_constraints=[m != s.regs.eax + 2])
r = s.project.factory.successors(s, num_inst=2).flat_successors
assert len(r) == 1
assert r[0].addr == 0x400005
assert set(r[0].solver.eval_upto(r[0].regs.eax, 3)) == {13, 29}
''', args=[str(path)], timeout=90)
    assert result.returncode == 0, result.stderr.decode()


def test_control_flow_serialization_preserves_nodes_edges_and_queries(tmp_path):
    from velnora.knowledge_plugins.cfg import CFGModel
    p = knowledge_program(tmp_path)
    a = lambda name: symbol_address(p, name)
    cfg = p.analyses.CFGFast(**recovery_options(
        regions=[(a('choose'), a('dispatch'))], function_starts=[a('choose')],
        symbols=False, start_at_entry=False))
    restored = CFGModel.parse(cfg.model.serialize())
    # Only the explicitly seeded function is reachable with scanning disabled.
    expected = {a('choose'), a('choose_zero'), a('choose_nonzero')}
    assert {n.addr for n in restored.graph.nodes} == expected
    assert {(s.addr, d.addr, e['jumpkind']) for s, d, e in restored.graph.edges(data=True)} == {
        (a('choose'), a('choose_zero'), 'Ijk_Boring'),
        (a('choose'), a('choose_nonzero'), 'Ijk_Boring')}
    root = restored.get_any_node(a('choose'))
    assert root.function_address == a('choose')
    assert {n.addr for n in restored.get_successors(root)} == {a('choose_zero'), a('choose_nonzero')}
    for name in ('choose_zero', 'choose_nonzero'):
        node = restored.get_any_node(a(name))
        assert {n.addr for n in restored.get_predecessors(node)} == {a('choose')}
        assert restored.get_any_node(node.addr + 1, anyaddr=True).addr == node.addr


def test_snapshots_repeatedly_restore_selected_information(tmp_path):
    from velnora import KnowledgeBaseSnapshot
    from velnora.sim_type import SimTypeFunction, SimTypeInt
    p = variable_program(tmp_path)
    f, _, manager = recovered_variables(p)
    variables = manager.get_variables()
    assert variables
    variables[0].name = 'saved_variable'
    p.kb.comments[f.addr] = 'saved comment'
    saved_proto = SimTypeFunction([SimTypeInt()], SimTypeInt()).with_arch(p.arch)
    f.prototype = saved_proto
    p.kb.bookmarks.add_bookmark(f.addr, 'initial bookmark')
    snapshot = KnowledgeBaseSnapshot(p.kb, included_plugins=('comments', 'variables'))
    for iteration in range(2):
        p.kb.comments[f.addr] = 'later comment'
        p.kb.variables[f.addr].get_variables()[0].name = 'later_variable'
        f.prototype = SimTypeFunction([], SimTypeInt()).with_arch(p.arch)
        p.kb.bookmarks.get_bookmark(f.addr).label = f'later bookmark {iteration}'
        snapshot.restore()
        assert p.kb.comments[f.addr] == 'saved comment'
        assert 'saved_variable' in {v.name for v in p.kb.variables[f.addr].get_variables()}
        assert f.prototype == saved_proto
        assert p.kb.bookmarks.get_bookmark(f.addr).label == f'later bookmark {iteration}'
    selected = KnowledgeBaseSnapshot(p.kb, included_plugins=('comments',))
    for iteration in range(2):
        p.kb.comments[f.addr] = 'changed again'
        p.kb.variables[f.addr].get_variables()[0].name = f'excluded_variable_{iteration}'
        selected.restore()
        assert p.kb.comments[f.addr] == 'saved comment'
        assert f'excluded_variable_{iteration}' in {v.name for v in p.kb.variables[f.addr].get_variables()}
