# feature: F09
"""Real program inputs and public control-flow observations."""
from _helpers import import_product, require_tools, run_command
from F07_helpers import symbol_address


def knowledge_program(directory):
    source = directory / 'F09.S'
    source.write_text('''
.text
.global _start, call_a, call_b, after_a, after_b, done, worker, worker_read
.global choose, choose_zero, choose_nonzero, orphan
.global dispatch, table_jump, case0, case1, case2, default_case, unknown
.global normalized, inner, tail, no_return, after_no_return, exitproc, text_end
.type _start,@function
_start:
    test %edi,%edi
    jz call_b
call_a:
    call worker
after_a:
    jmp done
call_b:
    call worker
after_b:
    jmp done
done:
    jmp done
.size _start,.-_start
.type worker,@function
worker:
worker_read:
    mov datum(%rip),%eax
    add %edi,%eax
    ret
.size worker,.-worker
.type choose,@function
choose:
    test %edi,%edi
    jz choose_zero
choose_nonzero:
    mov $17,%eax
    ret
choose_zero:
    mov $29,%eax
    ret
.size choose,.-choose
.type orphan,@function
orphan:
    mov $41,%eax
    ret
.size orphan,.-orphan
.type dispatch,@function
dispatch:
    cmp $2,%edi
    ja default_case
table_jump:
    jmp *table(,%rdi,8)
case0:
    mov $13,%eax
    ret
case1:
    mov $23,%eax
    ret
case2:
    mov $37,%eax
    ret
default_case:
    xor %eax,%eax
    ret
.size dispatch,.-dispatch
.type unknown,@function
unknown:
    jmp *%rax
.size unknown,.-unknown
.type normalized,@function
normalized:
    xor %eax,%eax
inner:
    add $2,%eax
    test %edi,%edi
    jnz inner
    ret
.size normalized,.-normalized
.type tail,@function
tail:
    jmp worker
.size tail,.-tail
.type no_return,@function
no_return:
    call exitproc
after_no_return:
    mov $51,%eax
    ret
.size no_return,.-no_return
.type exitproc,@function
exitproc:
    mov $60,%eax
    syscall
.size exitproc,.-exitproc
.global string_user, string_ref
.type string_user,@function
string_user:
string_ref:
    lea message(%rip),%rax
    ret
.size string_user,.-string_user
text_end:
.section .rodata
.global table, message, datum
table:
    .quad case0,case1,case2
message:
    .asciz "control flow reference"
.balign 8
datum:
    .long 73
.section .note.GNU-stack,"",@progbits
''')
    binary = directory / 'F09.elf'
    built = run_command([require_tools('gcc')['gcc'], '-nostdlib', '-no-pie', '-o', binary, source])
    assert built.returncode == 0, built.stderr
    return import_product().Project(str(binary), auto_load_libs=False)


def recovery_options(**updates):
    options = dict(force_smart_scan=False, force_complete_scan=False,
                   function_prologues=False)
    options.update(updates)
    return options


def flow_edges(cfg):
    """Keep direction and public transfer kind, without object identity or order."""
    return {(src.addr, dst.addr, data['jumpkind'])
            for src, dst, data in cfg.model.graph.edges(data=True)}


def function_edges(function):
    return {(src.addr, dst.addr, data['type'])
            for src, dst, data in function.transition_graph.edges(data=True)}


def permission_image(directory, executable):
    source = directory / ('F09_exec.S' if executable else 'F09_data.S')
    source.write_text(('.text' if executable else '.data') + '''
.global _start
_start:
.byte 0xc3
.section .note.GNU-stack,"",@progbits
''')
    binary = source.with_suffix('.elf')
    built = run_command([require_tools('gcc')['gcc'], '-nostdlib', '-no-pie', '-o', binary, source])
    assert built.returncode == 0, built.stderr
    return import_product().Project(str(binary), auto_load_libs=False)


async def mcp_tool_record(session, name, arguments):
    """Read the protocol field names through the SDK's alias serialization."""
    result = await session.call_tool(name, arguments)
    return result.model_dump(by_alias=True)


async def disassembly_session(binary, selections, expected):
    """Use the SDK's real stdio protocol client; all results consumed in context."""
    import sys
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=['-m', 'velnora.mcp'])
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            loaded = await mcp_tool_record(session, 'load_binary', {'binary_path': str(binary), 'auto_load_libs': False})
            assert not loaded['isError'], loaded
            project_id = loaded['structuredContent']['project_id']
            recovered = await mcp_tool_record(session, 'get_cfg', {'project_id': project_id})
            assert not recovered['isError'], recovered
            for selection, expected_address in selections:
                info = await mcp_tool_record(session, 'get_function_info', {'project_id': project_id, **selection})
                assert not info['isError'], info
                address = info['structuredContent']['address']
                assert int(address, 16) == expected_address
                result = await mcp_tool_record(session, 'get_basic_blocks',
                                                 {'project_id': project_id, 'function_address': address})
                assert not result['isError'], result
                body = result['structuredContent']
                observed = {int(instruction['address'], 16): instruction
                            for block in body['blocks'] for instruction in block['instructions']}
                assert set(observed) == set(expected[expected_address])
                for location, (encoding, mnemonics) in expected[expected_address].items():
                    assert bytes.fromhex(observed[location]['bytes']) == bytes.fromhex(encoding)
                    assert observed[location]['mnemonic'].lower() in mnemonics
            for selection in ({'name': 'absent_function'}, {'address': '0x123'}):
                result = await mcp_tool_record(session, 'get_function_info', {'project_id': project_id, **selection})
                assert result['isError'], result
                assert any(str(next(iter(selection.values()))) in item['text']
                           for item in result['content'] if item['type'] == 'text')
            result = await mcp_tool_record(session, 'get_basic_blocks',
                                             {'project_id': project_id, 'function_address': '0x123'})
            assert result['isError'], result
            assert any('0x123' in item['text'] for item in result['content'] if item['type'] == 'text')


def java_flow_program(directory):
    """A JVM class with a conditional method and a real static invocation.

    Java source equivalent: static int choose(int x) { if (x == 0) return 29;
    return 17; } public static void main(String[] args) { choose(1); }
    No native methods: CFGFastSoot cannot scan their missing Java bodies.
    """
    import struct
    import zipfile
    u2 = lambda n: struct.pack('>H', n)
    u4 = lambda n: struct.pack('>I', n)
    strings = ('F09Flow', 'java/lang/Object', 'Code', 'choose', '(I)I', 'main',
               '([Ljava/lang/String;)V')
    pool = [b'\x01' + u2(len(text)) + text.encode('ascii') for text in strings]
    pool += [b'\x07' + u2(1), b'\x07' + u2(2),
             b'\x0c' + u2(4) + u2(5), b'\x0a' + u2(8) + u2(10)]
    methods = []
    for name, signature, stack, locals_, code in [
        (4, 5, 1, 1, b'\x1a\x99\x00\x06\x10\x11\xac\x10\x1d\xac'),
        (6, 7, 1, 1, b'\x04\xb8\x00\x0b\x57\xb1'),
    ]:
        body = u2(stack) + u2(locals_) + u4(len(code)) + code + u2(0) + u2(0)
        methods.append(u2(9) + u2(name) + u2(signature) + u2(1)
                       + u2(3) + u4(len(body)) + body)
    data = (b'\xca\xfe\xba\xbe' + u2(0) + u2(49) + u2(len(pool)+1) + b''.join(pool)
            + u2(0x21) + u2(8) + u2(9) + u2(0) + u2(0)
            + u2(len(methods)) + b''.join(methods) + u2(0))
    archive = directory / 'F09Flow.jar'
    with zipfile.ZipFile(archive, 'w') as jar:
        jar.writestr('F09Flow.class', data)
        jar.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\nMain-Class: F09Flow\n\n')
    return archive
