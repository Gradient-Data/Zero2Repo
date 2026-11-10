# feature: F13
"""Acceptance checks for variable, prototype, type and DWARF recovery."""
from _helpers import import_product
from F03_helpers import location_record
from F04_helpers import reach_address
from F07_helpers import symbol_address
from F13_helpers import variable_program, recovered_variables, debug_program


def test_variable_locations_and_accesses(tmp_path):
    from velnora.knowledge_plugins.variables.variable_access import VariableAccessSort
    from velnora.sim_variable import SimStackVariable
    project = variable_program(tmp_path)
    _, _, manager = recovered_variables(project)
    selected = []
    for write, read, offset, size in [('write_a', 'read_a', -16, 4), ('write_b', 'read_b', -8, 8)]:
        candidates = manager.find_variables_by_insn(symbol_address(project, write), 'memory')
        matches = [var for var, _ in candidates if isinstance(var, SimStackVariable)
                   and var.offset == offset and var.size == size]
        assert len(matches) == 1
        var = matches[0]
        selected.append(var)
        accesses = {(access.location.ins_addr, access.access_type) for access in manager.get_variable_accesses(var)}
        assert (symbol_address(project, write), VariableAccessSort.WRITE) in accesses
        assert (symbol_address(project, read), VariableAccessSort.READ) in accesses
    assert selected[0] != selected[1]
    accesses = {(a.location.ins_addr, a.access_type) for a in manager.get_variable_accesses(selected[0])}
    assert (symbol_address(project, 'ref_a'), VariableAccessSort.REFERENCE) in accesses
    for insn, register, size in [('write_a', 'rdi', 4), ('write_b', 'rsi', 8)]:
        variables = manager.find_variables_by_insn(symbol_address(project, insn), 'register')
        assert any(var.reg == project.arch.registers[register][0] and var.size == size for var, _ in variables)
    # On X86 the logical frame origin is one 4-byte word below the entry stack
    # pointer: entry-12 is displacement -8 there (an 8-byte origin would give -4).
    narrow = variable_program(tmp_path, 32)
    _, _, narrow_manager = recovered_variables(narrow)
    stack = [var for var, _ in narrow_manager.find_variables_by_insn(symbol_address(narrow, 'write_32'), 'memory')
             if isinstance(var, SimStackVariable)]
    assert [(var.offset, var.size) for var in stack] == [(-8, 4)]


def test_recovered_prototypes_are_usable_and_replaceable(tmp_path):
    from velnora.sim_type import SimTypeFunction, SimTypeNum, SimTypeInt
    for bits in (32, 64):
        project = variable_program(tmp_path, bits)
        function = project.kb.functions['leaf']
        project.analyses.VariableRecoveryFast(function)
        analysis = project.analyses.CallingConvention(function, cfg=project.kb.cfgs.get_most_accurate())
        cc, prototype = analysis.cc, analysis.prototype
        assert cc is not None and prototype is not None
        assert len(prototype.args) == 2
        assert all(isinstance(arg, (SimTypeNum, SimTypeInt)) for arg in prototype.args)
        assert isinstance(prototype.returnty, (SimTypeNum, SimTypeInt))
        expected = [('stack', 4, 4), ('stack', 8, 4)] if bits == 32 else [('register', 'rdi', 8), ('register', 'rsi', 8)]
        assert [location_record(arg) for arg in cc.arg_locs(prototype)] == expected
        assert location_record(cc.return_val(prototype.returnty)) == ('register', 'eax' if bits == 32 else 'rax', bits // 8)
        function.calling_convention = cc
        function.prototype = prototype
        for first, second in [(7, 13), (31, 2)]:
            call = project.factory.callable(function.addr, cc=cc, prototype=function.prototype)
            assert call(first, second).concrete_value == first + 2 * second
        replacement = SimTypeFunction([SimTypeNum(bits, signed=False), SimTypeNum(bits, signed=False)],
                                      SimTypeNum(bits, signed=False)).with_arch(project.arch)
        function.prototype = replacement
        assert [arg.size for arg in function.prototype.args] == [bits, bits]
        assert all(arg.signed is False for arg in function.prototype.args)
        assert project.factory.callable(function.addr, cc=cc, prototype=function.prototype)(19, 23).concrete_value == 65


def test_type_constraints_preserve_widths_and_pointer_fields(tmp_path):
    from velnora.analyses.typehoon.typevars import TypeVariable, DerivedTypeVariable, Subtype, Load, Store, HasField
    from velnora.analyses.typehoon.typeconsts import Int8, Int32, Int64
    from velnora.sim_type import SimTypePointer, SimStruct
    project = variable_program(tmp_path)
    root = TypeVariable()
    scalar8, scalar64, pointer = TypeVariable(), TypeVariable(), TypeVariable()
    constraints = {root: {Subtype(scalar8, Int8()), Subtype(scalar64, Int64()),
                         Subtype(DerivedTypeVariable(pointer, None, labels=[Load(), HasField(32, 0)]), Int32()),
                         Subtype(DerivedTypeVariable(pointer, None, labels=[Store(), HasField(64, 8)]), Int64()),
                         Subtype(DerivedTypeVariable(pointer, None, labels=[Load(), HasField(64, 8)]), Int64())}}
    result = project.analyses.Typehoon(constraints, root, var_mapping={None: {scalar8, scalar64, pointer}})
    solution = result.simtypes_solution
    assert solution[scalar8].size == 8
    assert solution[scalar64].size == 64
    # A plain 64-bit scalar is not mistaken for the field-accessed pointer.
    assert not isinstance(solution[scalar64], SimTypePointer)
    ptr = solution[pointer]
    assert isinstance(ptr, SimTypePointer)
    assert isinstance(ptr.pts_to, SimStruct)
    fields = {ptr.pts_to.offsets[name]: typ.size for name, typ in ptr.pts_to.fields.items()}
    assert fields[0] == 32 and fields[8] == 64
    _, recovery, manager = recovered_variables(project)
    inferred = project.analyses.Typehoon(recovery.type_constraints, recovery.func_typevar,
                                         var_mapping=recovery.var_to_typevars)
    inferred.update_variable_types(project.kb.functions['variables'].addr, recovery.var_to_typevars)
    for label, width in [('write_a', 32), ('write_b', 64)]:
        variables = manager.find_variables_by_insn(symbol_address(project, label), 'memory')
        assert variables
        assert any(manager.get_variable_type(var).size == width for var, _ in variables)


def test_explicit_variable_type_survives_inference(tmp_path):
    from velnora.sim_type import SimTypePointer, SimTypeNum
    project = variable_program(tmp_path)
    function, recovery, manager = recovered_variables(project)
    candidates = manager.find_variables_by_insn(symbol_address(project, 'write_b'), 'memory')
    assert len(candidates) == 1
    variable = candidates[0][0]
    explicit = SimTypePointer(SimTypeNum(16, signed=False)).with_arch(project.arch)
    manager.set_variable_type(variable, explicit, mark_manual=True)
    result = project.analyses.Typehoon(recovery.type_constraints, recovery.func_typevar,
                                      var_mapping=recovery.var_to_typevars)
    result.update_variable_types(function.addr, recovery.var_to_typevars)
    retained = manager.get_variable_type(variable)
    assert isinstance(retained, SimTypePointer)
    assert retained.pts_to.size == 16 and retained.pts_to.signed is False
    state = project.factory.blank_state()
    state.memory.store(0x700000, 0x710000, size=8, endness=project.arch.memory_endness)
    state.memory.store(0x710000, b'\x35\xa2\x7e\x19')
    assert state.mem[0x700000].with_type(retained).deref.concrete == 0xa235


def test_dwarf_state_resolution_and_lexical_visibility(tmp_path):
    project = debug_program(tmp_path)
    state = project.factory.call_state(symbol_address(project, 'main'))
    outer = reach_address(project, state, symbol_address(project, 'outer_point'))
    assert outer.dvars['value'].mem.concrete == 17
    assert outer.dvars['global_value'].mem.concrete == 61
    assert outer.solver.eval(outer.dvars['global_value'].addr) == symbol_address(project, 'global_value')
    assert outer.solver.eval(outer.dvars['pointer'].mem.resolved) == outer.solver.eval(outer.dvars['value'].addr)
    assert outer.dvars['pointer'].deref.mem.concrete == 17
    assert outer.dvars['pair'].member('left').mem.concrete == 23
    assert outer.dvars['pair'].member('right').mem.concrete == 47
    assert [outer.dvars['items'].array(i).mem.concrete for i in range(3)] == [5, 11, 29]
    inner = reach_address(project, outer.copy(), symbol_address(project, 'inner_point'))
    assert inner.dvars['value'].mem.concrete == 83
    assert inner.dvars['pointer'].deref.mem.concrete == 17
    assert inner.solver.eval(inner.dvars['value'].addr) != inner.solver.eval(inner.dvars['pointer'].deref.addr)
    after = reach_address(project, inner.copy(), symbol_address(project, 'after_point'))
    assert after.dvars['value'].mem.concrete == 17
    assert after.dvars['global_value'].mem.concrete == 144
