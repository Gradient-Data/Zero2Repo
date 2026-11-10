# feature: F08
"""Acceptance checks for execution replacements and modeled calls."""
from _helpers import import_product
from F01_helpers import expression_api
from F04_helpers import reach_address
from F05_helpers import invoke_procedure, finish_process
from F07_helpers import execution_program, symbol_address
from F08_helpers import (compile_procedure_program, memory_bytes, assert_comparison,
                         termination_code, exclusion_binary)


def test_address_symbol_hooks_and_removal(tmp_path):
    velnora = import_product()
    p = execution_program(tmp_path)
    address = symbol_address(p, 'compute')

    class Replace(velnora.SimProcedure):
        def run(self, a, b):
            self.state.memory.store(0x710000, a + b)
            return a * 3 + b

    for by_symbol in (False, True):
        hook = Replace(prototype='long f(long, long)')
        if by_symbol:
            p.hook_symbol('compute', hook)
        else:
            p.hook(address, hook)
        assert p.is_hooked(address)
        assert isinstance(p.hooked_by(address), Replace)
        f = p.factory.callable(address, prototype='long f(long, long)')
        value = f(5, 8)
        assert f.result_state.solver.eval_one(value) == 23
        assert f.result_state.solver.eval_one(f.result_state.memory.load(0x710000, 8)) == 13
        p.unhook(address)
        assert not p.is_hooked(address)
        original = p.factory.callable(address, prototype='long f(long, long)')
        value = original(5, 8)
        assert original.result_state.solver.eval_one(value) == 21


def test_typed_arguments_and_selected_conventions():
    velnora, claripy = expression_api()
    from velnora.calling_conventions import SimCCSystemVAMD64, SimCCMicrosoftAMD64
    p = velnora.load_shellcode(b'\xc3', arch='amd64', load_address=0x400000)

    class Arithmetic(velnora.SimProcedure):
        def run(self, a, b):
            return a * 5 - b

    for cc in (SimCCSystemVAMD64(p.arch), SimCCMicrosoftAMD64(p.arch)):
        p.hook(0x400000, Arithmetic(cc=cc, prototype='long f(long, long)'), replace=True)
        for a, b in ((7, 4), (19, 12)):
            s = p.factory.call_state(0x400000, a, b, prototype='long f(long, long)', cc=cc, ret_addr=0x500000)
            # The selected convention fixes the argument registers (FP-03.03).
            first, second = ('rcx', 'rdx') if isinstance(cc, SimCCMicrosoftAMD64) else ('rdi', 'rsi')
            assert s.solver.eval_one(s.registers.load(first)) == a
            assert s.solver.eval_one(s.registers.load(second)) == b
            out = reach_address(p, s, 0x500000)
            ty = velnora.types.parse_type('long f(long, long)').with_arch(p.arch)
            assert out.solver.eval_one(cc.return_val(ty).get_value(out)) == a*5-b
    # A floating-point prototype selects the floating argument and return carrier.
    class Floating(velnora.SimProcedure):
        def run(self, a):
            return a + claripy.FPV(1.5, claripy.FSORT_DOUBLE)
    p.hook(0x400000, Floating(prototype='double f(double)'), replace=True)
    f = p.factory.callable(0x400000, prototype='double f(double)')
    result = f(2.25)
    assert f.result_state.solver.eval_one(result) == 3.75


def test_return_jump_exit_and_binary_call(tmp_path):
    velnora = import_product()
    p = execution_program(tmp_path)
    entry, target, stop = 0x710000, symbol_address(p, 'compute'), 0x720000

    class Return(velnora.SimProcedure):
        def run(self, x):
            self.ret(x + 9)

    class Jump(velnora.SimProcedure):
        def run(self, x):
            self.state.regs.rdi = x + 1
            self.state.regs.rsi = 4
            self.jump(target)

    class Exit(velnora.SimProcedure):
        NO_RET = True
        def run(self, x):
            self.exit(x)

    class Call(velnora.SimProcedure):
        local_vars = ('saved',)
        def run(self, x):
            self.saved = x + 17
            self.call(target, (x, 6), continue_at='resume', prototype='long f(long, long)')
        def resume(self, x):
            self.state.memory.store(0x730000, self.state.regs.rax)
            self.ret(self.state.regs.rax + self.saved)

    for procedure, expected in ((Return, 16), (Jump, 16), (Call, 43)):
        p.hook(entry, procedure(prototype='long f(long)'), replace=True)
        s = p.factory.call_state(entry, 7, prototype='long f(long)', ret_addr=stop)
        if procedure is Jump:
            s = reach_address(p, s, target)
            assert s.solver.eval_one(s.regs.rdi) == 8
            assert s.solver.eval_one(s.regs.rsi) == 4
        out = reach_address(p, s, stop)
        assert out.solver.eval_one(out.regs.rax) == expected
        if procedure is Call:
            assert out.solver.eval_one(out.memory.load(0x730000, 8)) == 19
    p.hook(entry, Exit(prototype='void f(long)'), replace=True)
    end = finish_process(p, p.factory.call_state(entry, 27, prototype='void f(long)', ret_addr=stop))
    assert termination_code(end) == 27


def test_region_replacement_continuation(tmp_path):
    p = execution_program(tmp_path)
    begin, end = symbol_address(p, 'limits'), symbol_address(p, 'stop2')
    s = p.factory.call_state(begin, prototype='long f(void)', ret_addr=0x720000)
    s.regs.rax = 13
    baseline = reach_address(p, s, 0x720000)
    assert baseline.solver.eval_one(baseline.regs.rax) == 62

    def replace(state):
        state.regs.rax = state.regs.rax * 3
    p.hook(begin, replace, length=end-begin)
    s = p.factory.call_state(begin, prototype='long f(void)', ret_addr=0x720000)
    s.regs.rax = 13
    continuation = reach_address(p, s, end)
    assert continuation.solver.eval_one(continuation.regs.rax) == 39
    out = reach_address(p, continuation, 0x720000)
    assert out.solver.eval_one(out.regs.rax) == 32


def test_byte_copy_move_and_fill():
    velnora, claripy = expression_api()
    p = velnora.load_shellcode(b'\xc3', arch='amd64')
    for name, dst, src, count, expected in (
        ('memcpy', 0x800002, 0x810000, 4, b'..WXYZ..'),
        ('memmove', 0x800003, 0x800001, 5, b'abcbcdef'),
        ('memmove', 0x800000, 0x800002, 5, b'cdefgfgh'),
        ('memset', 0x800002, 0xa6, 4, b'..\xa6\xa6\xa6\xa6..'),
        ('memcpy', 0x800002, 0x810000, 0, b'........'),
        ('memmove', 0x800002, 0x800000, 0, b'abcdefgh'),
        ('memset', 0x800002, 0xa6, 0, b'........')):
        s = p.factory.blank_state()
        s.memory.store(0x800000, b'abcdefgh' if name == 'memmove' else b'........')
        s.memory.store(0x810000, b'WXYZ')
        result = invoke_procedure(s, 'libc', name, claripy.BVV(dst, 64), claripy.BVV(src, 64), claripy.BVV(count, 64))
        assert s.solver.eval_one(result) == dst
        assert memory_bytes(s, 0x800000, 8) == expected
        if name == 'memcpy':
            assert memory_bytes(s, 0x810000, 4) == b'WXYZ'
    s = p.factory.blank_state()
    x = claripy.BVS('copied_bytes', 24)
    s.memory.store(0x810000, x)
    for name in ('memcpy', 'memmove'):
        invoke_procedure(s, 'libc', name, 0x820000, 0x810000, 3)
        assert not s.solver.satisfiable(extra_constraints=[s.memory.load(0x820000, 3) != x])
        assert s.solver.satisfiable(extra_constraints=[x == 0x193aef])
        assert s.solver.satisfiable(extra_constraints=[x == 0x274bc0])
    byte = claripy.BVS('fill_byte', 8)
    s.add_constraints(claripy.Or(byte == 0x17, byte == 0xe3))
    invoke_procedure(s, 'libc', 'memset', 0x830000, byte, claripy.BVV(3, 64))
    assert not s.solver.satisfiable(extra_constraints=[s.memory.load(0x830000, 3) != claripy.Concat(byte, byte, byte)])
    assert set(s.solver.eval_upto(byte, 3)) == {0x17, 0xe3}


def test_byte_comparison_order_limits_and_constraints():
    velnora, claripy = expression_api()
    p = velnora.load_shellcode(b'\xc3', arch='amd64')
    for a, b, n, sign in ((b'a\x00z', b'a\x00a', 3, 1), (b'a\xff', b'b\x00', 2, -1),
                            (b'\x80', b'\x7f', 1, 1), (b'abx', b'aby', 2, 0),
                            (b'abx', b'aby', 3, -1), (b'x', b'y', 0, 0)):
        s = p.factory.blank_state()
        s.memory.store(0x800000, a)
        s.memory.store(0x810000, b)
        assert_comparison(s, invoke_procedure(s, 'libc', 'memcmp', 0x800000, 0x810000, n), sign)
    s = p.factory.blank_state()
    x = claripy.BVS('compared_byte', 8)
    s.memory.store(0x800000, x)
    s.memory.store(0x810000, b'\x80')
    result = invoke_procedure(s, 'libc', 'memcmp', 0x800000, 0x810000, 1)
    for condition, allowed in ((result == 0, {128}), (result.SLT(0), set(range(128))),
                               (result.SGT(0), set(range(129, 256)))):
        assert set(s.solver.eval_upto(x, 257, extra_constraints=[condition])) == allowed


def test_modeled_process_libraries_and_syscalls(tmp_path):
    velnora = import_product()
    p = compile_procedure_program(tmp_path, '''
    lea path(%rip),%rdi
    xor %esi,%esi
    call open
    mov %rax,%rdi
    lea buffer(%rip),%rsi
    mov $3,%edx
    call read
    mov $1,%edi
    lea buffer(%rip),%rsi
    mov $3,%edx
    call write
    xor %eax,%eax
    xor %edi,%edi
    lea buffer(%rip),%rsi
    mov $2,%edx
    syscall
    mov $1,%eax
    mov $1,%edi
    lea buffer(%rip),%rsi
    mov $2,%edx
    syscall
    lea variable(%rip),%rdi
    call getenv
    movzbl (%rax),%ebx
    mov $8,%edi
    call malloc
    mov %rax,%r12
    mov %bl,(%r12)
    movb $33,1(%r12)
    mov $8,%edi
    call malloc
    mov %rax,%r13
    movb $63,(%r13)
    mov $1,%eax
    mov $2,%edi
    mov %r12,%rsi
    mov $2,%edx
    syscall
.global before_release
before_release:
    mov %r12,%rdi
    call free
    mov %r13,%rdi
    call free
    mov $23,%edi
    call exit
open: ret
read: ret
write: ret
getenv: ret
malloc: ret
free: ret
exit: ret
.data
path: .asciz "/input"
variable: .asciz "MODE"
buffer: .space 8
''')
    for name in ('open', 'read', 'write'):
        p.hook_symbol(name, velnora.SIM_PROCEDURES['posix'][name]())
    p.hook_symbol('getenv', velnora.SIM_PROCEDURES['posix']['getenv']())
    for name in ('malloc', 'free', 'exit'):
        p.hook_symbol(name, velnora.SIM_PROCEDURES['libc'][name]())
    # Neighbouring names share a prefix with the requested one, so only an
    # exact name lookup yields the expected value.
    s = p.factory.entry_state(env={'MOD': 'Quail', 'MODEX': 'Yak', 'MODE': 'Zebra'}, stdin=velnora.SimFileStream(name='stdin', content=b'Hi', has_end=True))
    s.fs.insert('/input', velnora.SimFile('/input', content=b'cat', size=3))
    live = reach_address(p, s, symbol_address(p, 'before_release'))
    allocated = live.solver.eval_one(live.regs.r12)
    other = live.solver.eval_one(live.regs.r13)
    assert allocated != 0 and other != 0
    assert memory_bytes(live, allocated, 2) == b'Z!'
    assert memory_bytes(live, other, 1) == b'?'
    end = finish_process(p, live)
    assert end.posix.dumps(1) == b'catHi'
    assert end.posix.dumps(2) == b'Z!'
    assert termination_code(end) == 23


def test_excluding_model_executes_loaded_code(tmp_path):
    binary = exclusion_binary(tmp_path)
    for excluded, expected in ((False, 6), (True, 73)):
        p = import_product().Project(str(binary), auto_load_libs=True,
            ld_path=[str(tmp_path)], exclude_sim_procedures_list=['strlen'] if excluded else [])
        end = reach_address(p, p.factory.entry_state(), symbol_address(p, 'observed'))
        assert end.solver.eval_one(end.regs.rax) == expected


def test_string_length_copy_comparison_and_constraints():
    velnora, claripy = expression_api()
    p = velnora.load_shellcode(b'\xc3', arch='amd64')
    for text, expected in ((b'\x00tail', 0), (b'xy\x00tail', 2), (b'\xc3\xa9!\x00', 3)):
        s = p.factory.blank_state()
        s.memory.store(0x800000, text)
        s.memory.store(0x810000, b'..........')
        length = invoke_procedure(s, 'libc', 'strlen', 0x800000)
        assert s.solver.eval_one(length) == expected
        result = invoke_procedure(s, 'libc', 'strcpy', 0x810002, 0x800000)
        assert s.solver.eval_one(result) == 0x810002
        assert memory_bytes(s, 0x810000, 10) == b'..' + text[:expected+1] + b'.'*(7-expected)
    for a, b, limit, sign in ((b'a\x00z', b'a\x00a', None, 0),
                               (b'a\xff\x00', b'b\x01\x00', None, -1),
                               (b'\x80\x00', b'\x7f\x00', None, 1),
                               (b'ab\x00', b'abc\x00', None, -1),
                               (b'abc\x00', b'ab\x00', None, 1),
                               (b'abx\x00', b'aby\x00', 2, 0),
                               (b'abx\x00', b'aby\x00', 3, -1),
                               (b'x\x00', b'y\x00', 0, 0),
                               (b'a\x00z', b'a\x00a', 3, 0)):
        s = p.factory.blank_state()
        s.memory.store(0x800000, a)
        s.memory.store(0x810000, b)
        name, args = ('strcmp', ()) if limit is None else ('strncmp', (claripy.BVV(limit, 64),))
        assert_comparison(s, invoke_procedure(s, 'libc', name, 0x800000, 0x810000, *args), sign)
    s = p.factory.blank_state()
    x = claripy.BVS('string_byte', 8)
    s.add_constraints(claripy.Or(x == 0, x == ord('q')))
    s.memory.store(0x800000, claripy.Concat(x, claripy.BVV(b'r\x00')))
    length = invoke_procedure(s, 'libc', 'strlen', 0x800000)
    assert set(s.solver.eval_upto(length, 3)) == {0, 2}
    assert not s.solver.satisfiable(extra_constraints=[(length == 0) != (x == 0)])
    for name, extra in (('strcmp', ()), ('strncmp', (claripy.BVV(2, 64),))):
        s = p.factory.blank_state()
        x = claripy.BVS('matching_byte', 8)
        s.add_constraints(claripy.Or(x == ord('m'), x == ord('n')))
        s.memory.store(0x800000, claripy.Concat(x, claripy.BVV(b'k\x00')))
        s.memory.store(0x810000, b'mk\x00')
        result = invoke_procedure(s, 'libc', name, 0x800000, 0x810000, *extra)
        assert set(s.solver.eval_upto(x, 3, extra_constraints=[result == 0])) == {ord('m')}
        assert set(s.solver.eval_upto(x, 3, extra_constraints=[result != 0])) == {ord('n')}
