# feature: F03
"""Acceptance checks for C declarations, architecture binding and conventions."""
import archinfo
from pycparser.c_parser import ParseError
from _helpers import import_product, capture_call
from F01_helpers import fresh_state
from F03_helpers import location_record


def test_declarations_and_reuse():
    velnora = import_product()
    t = velnora.types
    from velnora.sim_type import (SimTypeInt, SimTypeShort, SimTypeLong, SimTypeChar,
                               SimTypeFloat, SimTypeDouble, SimTypePointer,
                               SimTypeArray, SimStruct, SimUnion, SimTypeEnum,
                               SimTypeFunction)
    for spelling, cls in (("int", SimTypeInt), ("short", SimTypeShort),
                          ("long", SimTypeLong), ("char", SimTypeChar),
                          ("float", SimTypeFloat), ("double", SimTypeDouble)):
        assert isinstance(t.parse_type(spelling), cls)
    assert t.parse_type("unsigned int").signed is False
    assert t.parse_type("signed int").signed is True
    declarations, types = t.parse_file('''
        typedef struct F03Node {
            unsigned short codes[5]; double weight; struct F03Node *next;
        } F03Node;
        union F03Choice { int number; float fraction; };
        enum F03Mode { FIRST=3, SECOND, THIRD=11 };
        F03Node *head;
        double transform(F03Node *node, unsigned int count, float scale);
    ''')
    node = types["F03Node"]
    assert isinstance(node, SimStruct)
    assert set(node.fields) == {"codes", "weight", "next"}
    array = node.fields["codes"]
    assert isinstance(array, SimTypeArray) and array.length == 5
    assert isinstance(array.elem_type, SimTypeShort) and array.elem_type.signed is False
    assert isinstance(node.fields["weight"], SimTypeDouble)
    assert isinstance(node.fields["next"], SimTypePointer)
    assert node.fields["next"].pts_to.fields == node.fields
    choice = types["union F03Choice"]
    assert isinstance(choice, SimUnion)
    assert set(choice.members) == {"number", "fraction"}
    assert isinstance(choice.members["number"], SimTypeInt)
    assert isinstance(choice.members["fraction"], SimTypeFloat)
    mode = types["enum F03Mode"]
    assert isinstance(mode, SimTypeEnum)
    assert mode.members == {"FIRST": 3, "SECOND": 4, "THIRD": 11}
    assert isinstance(declarations["head"], SimTypePointer)
    assert declarations["head"].pts_to.fields == node.fields
    function = declarations["transform"]
    assert isinstance(function, SimTypeFunction)
    assert isinstance(function.returnty, SimTypeDouble)
    assert len(function.args) == 3
    assert isinstance(function.args[0], SimTypePointer)
    assert function.args[0].pts_to.fields == node.fields
    assert isinstance(function.args[1], SimTypeInt) and function.args[1].signed is False
    assert isinstance(function.args[2], SimTypeFloat)
    t.register_types(types)
    reused = t.parse_type("F03Node * (F03Node *, enum F03Mode)")
    assert reused.returnty.pts_to.fields == node.fields
    assert reused.args[0].pts_to.fields == node.fields
    assert reused.args[1].members == mode.members
    t.register_types(t.parse_type("struct F03Registered { int serial; char *text; }"))
    later = t.parse_type("struct F03Registered *")
    assert set(later.pts_to.fields) == {"serial", "text"}
    assert isinstance(later.pts_to.fields["text"].pts_to, SimTypeChar)
    for declaration in ("struct { int x;", "int (int, )"):
        outcome = capture_call(t.parse_type, declaration)
        assert isinstance(outcome.exception, ParseError)


def test_architecture_bound_layout():
    velnora = import_product()
    from velnora.sim_type import SimTypeChar, SimTypeDouble, SimTypeLong, SimTypePointer, SimTypeShort
    declaration = velnora.types.parse_type(
        "struct F03Layout {char tag; long count; int *link; short samples[3]; double weight; char end;}"
    )
    # The oracle uses the public scalar data model and declaration order.
    layouts = []
    for architecture in (archinfo.ArchX86(), archinfo.ArchAMD64()):
        bound = declaration.with_arch(architecture)
        assert set(bound.fields) == {"tag", "count", "link", "samples", "weight", "end"}
        assert isinstance(bound.fields["tag"], SimTypeChar)
        assert isinstance(bound.fields["count"], SimTypeLong)
        assert isinstance(bound.fields["link"], SimTypePointer)
        assert isinstance(bound.fields["samples"].elem_type, SimTypeShort)
        assert isinstance(bound.fields["weight"], SimTypeDouble)
        assert isinstance(bound.fields["end"], SimTypeChar)
        assert bound.fields["samples"].length == 3
        widths = {'char': 8, 'short': 16, 'int': 32, 'long': architecture.bits,
                  'long long': 64, 'unsigned long long': 64,
                  'float': 32, 'double': 64, 'int *': architecture.bits}
        for spelling, width in widths.items():
            assert velnora.types.parse_type(spelling).with_arch(architecture).size == width
        expected_widths = {'tag': 8, 'count': architecture.bits,
                           'link': architecture.bits, 'samples': 3 * 16,
                           'weight': 64, 'end': 8}
        assert {name: typ.size for name, typ in bound.fields.items()} == expected_widths
        offsets = bound.offsets
        extent = 0
        expected_offsets = {}
        member_order = ('tag', 'count', 'link', 'samples', 'weight', 'end')
        for name in member_order:
            alignment = (16 if name == 'samples' else expected_widths[name]) // 8
            extent = ((extent + alignment - 1) // alignment) * alignment
            expected_offsets[name] = extent
            extent += expected_widths[name] // 8
        assert offsets == expected_offsets
        assert bound.size == extent * 8
        assert set(offsets) == set(bound.fields)
        for left, right in zip(member_order, member_order[1:]):
            assert offsets[right] * architecture.byte_width >= (
                offsets[left] * architecture.byte_width + bound.fields[left].size)
        assert bound.size >= (offsets["end"] * architecture.byte_width
                              + bound.fields["end"].size)
        assert bound.fields["samples"].size == 3 * bound.fields["samples"].elem_type.size
        layouts.append((bound.fields["link"].size, offsets["samples"], bound.size))
    assert all(wide > narrow for narrow, wide in zip(layouts[0], layouts[1]))
    for read in (lambda: declaration.size, lambda: declaration.offsets):
        outcome = capture_call(read)
        assert isinstance(outcome.exception, ValueError)


def test_builtin_convention_locations():
    velnora = import_product()
    cc = velnora.calling_conventions
    # Each row covers a promised convention; two overflow arguments establish
    # both the register/stack boundary and the stack stride.
    rows = [
        ("X86", "SimCCCdecl", [], 4, 4, "eax", 4),
        ("X86", "SimCCStdcall", [], 4, 4, "eax", 4),
        ("X86", "SimCCMicrosoftFastcall", ["ecx", "edx"], 4, 4, "eax", 4),
        ("X86", "SimCCMicrosoftThiscall", ["ecx"], 4, 4, "eax", 4),
        ("AMD64", "SimCCSystemVAMD64", ["rdi", "rsi", "rdx", "rcx", "r8", "r9"], 8, 8, "rax", 8),
        ("AMD64", "SimCCMicrosoftAMD64", ["rcx", "rdx", "r8", "r9"], 40, 8, "rax", 8),
        ("ARMEL", "SimCCARM", ["r0", "r1", "r2", "r3"], 0, 4, "r0", 4),
        ("ARMHF", "SimCCARMHF", ["r0", "r1", "r2", "r3"], 0, 4, "r0", 4),
        ("AARCH64", "SimCCAArch64", ["x0", "x1", "x2", "x3", "x4", "x5", "x6", "x7"], 0, 8, "x0", 8),
        ("MIPS32", "SimCCO32", ["a0", "a1", "a2", "a3"], 16, 4, "v0", 4),
        ("MIPSN32", "SimCCN32", ["a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7"], 36, 8, "v0", 4),
        ("MIPS64", "SimCCN64", ["a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7"], 32, 8, "v0", 8),
        ("PPC32", "SimCCPowerPC", ["r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10"], 8, 4, "r3", 4),
        ("PPC64", "SimCCPowerPC64", ["r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10"], 112, 8, "r3", 8),
        ("S390X", "SimCCS390X", ["r2", "r3", "r4", "r5", "r6"], 160, 8, "r2", 8),
        ("RISCV64", "SimCCRISCV64", ["a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7"], 0, 8, "a0", 8),
    ]
    for architecture, name, registers, start, stride, result_register, width in rows:
        arch = archinfo.arch_from_id(architecture)
        convention = getattr(cc, name)(arch)
        for count in (1, len(registers) + 2):
            prototype = velnora.types.parse_type(
                "long (" + ", ".join(["long"] * count) + ")").with_arch(arch)
            expected = [("register", register, width) for register in registers[:count]]
            expected += [("stack", start + index * stride, width)
                         for index in range(max(0, count - len(registers)))]
            assert [location_record(loc) for loc in convention.arg_locs(prototype)] == expected, name
            assert location_record(convention.return_val(prototype.returnty)) == (
                "register", result_register, width), name
    for architecture, name, registers, result in (
        ("ARMEL", "SimCCARM", [f"r{i}" for i in range(4)], "r0"),
        ("ARMHF", "SimCCARMHF", [f"s{i}" for i in range(16)], "s0"),
    ):
        arch = archinfo.arch_from_id(architecture)
        convention = getattr(cc, name)(arch)
        for count in (2, len(registers) + 2):
            prototype = velnora.types.parse_type(
                "float (" + ", ".join(["float"] * count) + ")").with_arch(arch)
            expected = [("register", register, 4) for register in registers[:count]]
            expected += [("stack", index * 4, 4)
                         for index in range(max(0, count - len(registers)))]
            assert [location_record(loc) for loc in convention.arg_locs(prototype)] == expected
            assert location_record(convention.return_val(prototype.returnty)) == ("register", result, 4)


def test_custom_convention_locations_and_values():
    velnora = import_product()
    cc = velnora.calling_conventions
    # Two independent configurations ensure user locations, including stack
    # return locations, determine the result rather than an architecture default.
    for registers, offset, return_location in (
        (["r10", "r12"], 24, cc.SimRegArg("r14", 8)),
        (["r13", "r11"], 56, cc.SimStackArg(88, 8)),
    ):
        state = fresh_state()
        state.regs.rsp = 0x700000
        prototype = velnora.types.parse_type("long (long, long, long)").with_arch(state.arch)
        locations = [cc.SimRegArg(registers[0], 8), cc.SimStackArg(offset, 8),
                     cc.SimRegArg(registers[1], 8)]
        convention = cc.SimCCUsercall(state.arch, locations, return_location)
        expected = [("register", registers[0], 8), ("stack", offset, 8),
                    ("register", registers[1], 8)]
        assert [location_record(loc) for loc in convention.arg_locs(prototype)] == expected
        assert location_record(convention.return_val(prototype.returnty)) == location_record(return_location)
        values = [0x123456789, 0x2468ace0, 0x13579bdf]
        convention.setup_callsite(state, 0x401000, values, prototype, stack_base=0x700000)
        assert state.solver.eval(state.registers.load(registers[0])) == values[0]
        assert state.solver.eval(state.memory.load(0x700000 + offset, 8, endness=state.arch.memory_endness)) == values[1]
        assert state.solver.eval(state.registers.load(registers[1])) == values[2]
        # Seed independent raw carriers before extraction; this is not just a
        # round trip through the convention's own writer and reader.
        state.registers.store(registers[0], values[2])
        state.memory.store(0x700000 + offset, values[0], size=8, endness=state.arch.memory_endness)
        state.registers.store(registers[1], values[1])
        assert [state.solver.eval(value) for value in convention.get_args(state, prototype)] == [
            values[2], values[0], values[1]]
        convention.set_return_val(state, 0xabcdef12, prototype.returnty)
        if isinstance(return_location, cc.SimRegArg):
            result = state.registers.load(return_location.reg_name)
        else:
            result = state.memory.load(0x700000 + return_location.stack_offset, 8,
                                       endness=state.arch.memory_endness)
        assert state.solver.eval(result) == 0xabcdef12
