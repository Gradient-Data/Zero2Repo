# feature: F06
"""Acceptance checks for disassembly and inspectable intermediate effects."""
from _helpers import capture_call, import_product
from F02_helpers import make_java_archive
from F06_helpers import evaluate_vex_effects, evaluate_pcode_effects, pcode_operations


def test_disassembly_extents_and_instruction_limits():
    velnora = import_product()
    from capstone import CS_OP_REG, CS_OP_IMM

    code = bytes.fromhex('b82a00000083c0058907c390')
    base = 0x4000
    project = velnora.load_shellcode(code, arch='AMD64', load_address=base)
    for options, sizes in (({}, [5, 3, 2, 1]), ({'size': 8}, [5, 3]), ({'size': 6}, [5]),
                           ({'num_inst': 1}, [5]), ({'num_inst': 2}, [5, 3])):
        block = project.factory.block(base, **options)
        instructions = block.capstone.insns
        assert [i.size for i in instructions] == sizes
        addresses = [base + sum(sizes[:index]) for index in range(len(sizes))]
        assert [i.address for i in instructions] == addresses
        assert list(block.instruction_addrs) == addresses
        assert block.size == sum(sizes)
        assert block.bytes == code[:sum(sizes)]
        first = instructions[0].insn
        assert first.mnemonic.lower() in ('mov', 'movabs')
        assert first.operands[0].type == CS_OP_REG
        assert first.reg_name(first.operands[0].reg).lower() == 'eax'
        assert first.operands[1].type == CS_OP_IMM
        assert first.operands[1].imm == 42
        if len(instructions) >= 2:
            second = instructions[1].insn
            assert second.mnemonic.lower() == 'add'
            assert second.reg_name(second.operands[0].reg).lower() == 'eax'
            assert second.operands[1].imm == 5
    supplied = project.factory.block(base + 0x80, byte_string=bytes.fromhex('b863000000'), size=5)
    assert supplied.instruction_addrs == [base + 0x80]
    assert supplied.capstone.insns[0].insn.operands[1].imm == 99


def test_undecodable_bytes_do_not_invent_instructions():
    velnora = import_product()
    base = 0x4200
    valid = bytes.fromhex('b82a000000')
    project = velnora.load_shellcode(valid + b'\x0f', arch='AMD64', load_address=base)
    baseline = project.factory.block(base, size=len(valid))
    assert baseline.size == 5
    assert len(baseline.capstone.insns) == 1
    assert baseline.capstone.insns[0].insn.operands[1].imm == 42

    def inspect(address, extent):
        block = project.factory.block(address, size=extent)
        ir = block.vex
        return block.size, block.bytes, [insn.address for insn in block.capstone.insns]

    for address, extent, prefix in ((base, 6, valid), (base + 5, 1, b'')):
        result = capture_call(inspect, address, extent)
        if result.exception is not None:
            assert isinstance(result.exception, velnora.errors.SimTranslationError), repr(result.exception)
        else:
            size, data, addresses = result.value
            assert size == len(prefix)
            assert data == prefix
            assert addresses == ([base] if prefix else [])


def test_native_ir_effects_widths_and_control_transfers():
    velnora = import_product()
    import archinfo
    base = 0x4000
    code = bytes.fromhex('b83412000089078b4f04')
    for pcode in (False, True):
        arch = archinfo.ArchPcode('x86:LE:64:default') if pcode else archinfo.ArchAMD64()
        options = {'engine': velnora.engines.UberEnginePcode} if pcode else {}

        def lift(data):
            project = velnora.load_shellcode(data, arch=arch, load_address=base, **options)
            return project.factory.block(base, size=len(data), opt_level=0).vex

        ir = lift(code)
        assert ir.jumpkind == 'Ijk_Boring'
        for address, loaded in ((0x8000, 0x87654321), (0x9200, 0x23456789)):
            memory = {address + i: byte for i, byte in enumerate(b'abcdefgh' + b'KEEP')}
            memory.update({address + 4 + i: byte for i, byte in enumerate(loaded.to_bytes(4, 'little'))})
            if pcode:
                registers, stored = evaluate_pcode_effects(ir, arch, {'RDI': address}, memory)
                assert registers['RAX'] == 0x1234
                assert registers['RCX'] == loaded
            else:
                registers, stored = evaluate_vex_effects(ir, {arch.registers['rdi'][0]: address}, memory)
                assert registers[arch.registers['rax'][0]] == 0x1234
                assert registers[arch.registers['rcx'][0]] == loaded
            expected = dict(memory)
            expected.update({address + i: byte for i, byte in enumerate(b'\x34\x12\0\0')})
            assert stored == expected

        branch = lift(bytes.fromhex('e305'))  # jrcxz: no architecture-specific flag helper.
        assert branch.jumpkind == 'Ijk_Boring'
        assert len(branch.exit_statements) == 1
        if pcode:
            for count, destination in ((0, base + 7), (5, base + 2)):
                assert evaluate_pcode_effects(branch, arch, {'RCX': count}, {},
                                              destination=True) == destination
        else:
            for count, destination in ((0, base + 7), (5, base + 2)):
                assert evaluate_vex_effects(branch, {arch.registers['rcx'][0]: count}, {},
                                            destination=True) == destination

        call = lift(bytes.fromhex('e810000000'))
        assert call.jumpkind == 'Ijk_Call'
        assert call.next.con.value == base + 0x15
        ret = lift(b'\xc3')
        assert ret.jumpkind == 'Ijk_Ret'
        for target in (0x12345678, 0x80402010):
            stack = {0xa000 + i: byte for i, byte in enumerate(target.to_bytes(8, 'little'))}
            if pcode:
                actual = evaluate_pcode_effects(ret, arch, {'RSP': 0xa000}, stack, destination=True)
            else:
                actual = evaluate_vex_effects(ret, {arch.registers['rsp'][0]: 0xa000}, stack,
                                              destination=True)
            assert actual == target
        syscall = lift(bytes.fromhex('0f05'))
        if pcode:
            assert 'syscall()' in pcode_operations(syscall)
            assert any(op.startswith('return ') for op in pcode_operations(ret))
            assert any(op.startswith('call ram[') for op in pcode_operations(call))
        else:
            assert syscall.jumpkind == 'Ijk_Sys_syscall'


def test_java_statements_and_locations(tmp_path):
    velnora = import_product()
    from archinfo.arch_soot import SootAddressDescriptor, SootMethodDescriptor
    archive = make_java_archive(tmp_path / 'inspection.jar')
    project = velnora.Project(str(archive), auto_load_libs=False,
                           main_opts={'entry_point': 'F02Entry.probe', 'entry_point_params': ('int',)})
    method = project.loader.main_object.get_soot_method('F02Entry.probe', params=('int',))
    descriptor = SootMethodDescriptor.from_string('F02Entry.probe(int)')
    assert project.entry.method == descriptor
    statements = []
    for block in method.blocks:
        address = SootAddressDescriptor(descriptor, block.idx, 0)
        inspected = project.factory.block(address)
        assert inspected.addr == address
        assert inspected.size == len(block.statements) > 0
        assert inspected.soot.statements == block.statements
        for index, statement in enumerate(inspected.soot.statements):
            location = SootAddressDescriptor(descriptor, block.idx, index)
            located = project.factory.block(location)
            tail = located.soot.statements
            assert tail[index] == statement
            assert located.addr.method == descriptor
            assert located.addr.block_idx == block.idx
            assert located.addr.stmt_idx == index
            statements.append(statement)
    assert any(statement.__class__.__name__ == 'IdentityStmt' for statement in statements)
    assert any(statement.__class__.__name__ == 'AssignStmt' for statement in statements)
    assert any(statement.__class__.__name__ == 'ReturnStmt' for statement in statements)
    # Check the represented addition and return, independently of temporary names.
    additions = [statement.right_op for statement in statements
                 if statement.__class__.__name__ == 'AssignStmt'
                 and statement.right_op.__class__.__name__ == 'SootBinopExpr']
    assert len(additions) == 1
    assert additions[0].op == 'add'
    assert additions[0].value2.value == 7
    parameters = [statement for statement in statements
                  if statement.__class__.__name__ == 'IdentityStmt'
                  and statement.right_op.__class__.__name__ == 'SootParamRef']
    assert len(parameters) == 1
    assert parameters[0].right_op.index == 0
    assert additions[0].value1 == parameters[0].left_op
    returns = [statement for statement in statements if statement.__class__.__name__ == 'ReturnStmt']
    assignment = next(statement for statement in statements
                      if statement.__class__.__name__ == 'AssignStmt'
                      and statement.right_op is additions[0])
    assert returns[0].value == assignment.left_op


def test_architecture_byte_order_and_project_isolation():
    velnora = import_product()
    import archinfo
    # Encodings set a general-purpose register to a known immediate. Every ISA has an
    # independent example; only ISAs with applicable alternate byte order repeat.
    vectors = [
        ('X86', 'Iend_LE', 'b82a000000', 'eax', False, 42, False),
        ('AMD64', 'Iend_LE', '48c7c02a000000', 'rax', False, 42, False),
        ('ARMEL', 'Iend_LE', '2a00a0e3', 'r0', False, 42, False),
        ('ARMEL', 'Iend_BE', 'e3a0002b', 'r0', False, 43, False),
        ('ARMEL', 'Iend_LE', '2a20', 'r0', True, 42, False),
        ('AARCH64', 'Iend_LE', '400580d2', 'x0', False, 42, False),
        ('MIPS32', 'Iend_BE', '2402002a', 'v0', False, 42, False),
        ('MIPS32', 'Iend_LE', '2a000224', 'v0', False, 42, False),
        ('MIPS64', 'Iend_BE', '6402002a', 'v0', False, 42, False),
        ('MIPS64', 'Iend_LE', '2a000264', 'v0', False, 42, False),
        ('PPC32', 'Iend_BE', '3860002a', 'r3', False, 42, False),
        ('PPC64', 'Iend_BE', '3860002a', 'r3', False, 42, False),
        ('PPC64', 'Iend_LE', '2a006038', 'r3', False, 42, False),
        ('S390X', 'Iend_BE', 'a729002a', 'r2', False, 42, False),
        ('RISCV64', 'Iend_LE', '1305a002', 'a0', False, 42, False),
    ]
    vectors.append(('AMD64', 'Iend_LE', '48c7c063000000', 'rax', False, 99, False))
    vectors.append(('PowerPC:LE:32:default', 'Iend_LE', '2a006038', 'r3', False, 42, True))
    projects = []
    for name, order, encoded, register, thumb, expected, pcode in vectors:
        arch = archinfo.ArchPcode(name) if pcode else archinfo.arch_from_id(name, endness=order)
        code = bytes.fromhex(encoded)
        options = {'engine': velnora.engines.UberEnginePcode} if pcode else {}
        project = velnora.load_shellcode(code, arch=arch, load_address=0x4000, **options)
        projects.append((project, code, register, thumb, expected, pcode))
    # Revisit all projects after lifting other architectures at the same address.
    for project, code, register, thumb, expected, pcode in projects + list(reversed(projects)):
        block = project.factory.block(0x4001 if thumb else 0x4000, size=len(code), opt_level=0)
        ir = block.vex
        assert block.size == len(code)
        assert len(block.instruction_addrs) == 1
        assert block.bytes == code
        assert len(block.disassembly.insns) == 1
        assert block.disassembly.insns[0].size == len(code)
        if pcode:
            registers, memory = evaluate_pcode_effects(ir, project.arch, {}, {})
            assert registers[register.upper()] == expected
        else:
            assert block.disassembly.insns[0].insn.operands[-1].imm == expected
            offset = project.arch.registers[register][0]
            initial = {offset: 0 for offset, _ in project.arch.registers.values()}
            registers, memory = evaluate_vex_effects(ir, initial, {}, only_offsets=[offset])
            assert registers[offset] == expected
        assert memory == {}
