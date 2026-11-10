# feature: F20
"""Real protocol calls, independent ELF metadata, and native session inputs."""
import asyncio
from contextlib import asynccontextmanager
from functools import wraps
from io import BytesIO
import socket
import sys

from elftools.elf.elffile import ELFFile
from _helpers import managed_server, require_tools, run_command, wait_until
from F09_helpers import mcp_tool_record
from F16_helpers import refinement_session


def session_program(directory):
    """Assemble a real linked image with imports, syscalls and data references."""
    source = directory / 'F20_session.S'
    text = '''.text
.global _start, compute, caller, string_user, sys_exit, data_ref
.type _start,@function
_start: call caller
 call string_user
 call puts@PLT
 call sys_exit
.size _start,.-_start
.type compute,@function
compute: lea 9(%rdi),%eax
 ret
.size compute,.-compute
.type caller,@function
caller: call compute
 add $7,%eax
 ret
.size caller,.-caller
.type sys_exit,@function
sys_exit: mov $60,%eax
 syscall
.size sys_exit,.-sys_exit
.type string_user,@function
string_user:
data_ref: lea message(%rip),%rax
 lea short_message(%rip),%rax
 lea four_message(%rip),%rax
'''
    for i in range(105):
        text += f' lea message_{i}(%rip),%rax\n'
    text += ' ret\n.size string_user,.-string_user\n'
    for i in range(105):
        text += f'.global sample_{i}\n.type sample_{i},@function\nsample_{i}: mov ${i},%eax\n ret\n.size sample_{i},.-sample_{i}\n'
    text += '''.section .rodata
.global message, short_message, four_message
message: .asciz "session referenced message"
short_message: .asciz "xyz"
four_message: .asciz "abcd"
'''
    for i in range(105):
        text += f'.global message_{i}\nmessage_{i}: .asciz "referenced message number {i}"\n'
    text += '''.section .unreferenced,"a"
.zero 128
.global hidden_message
hidden_message: .asciz "unreferenced isolated text"
.zero 128
.section .note.GNU-stack,"",@progbits
'''
    source.write_text(text)
    binary = source.with_suffix('.elf')
    result = run_command([require_tools('gcc')['gcc'], '-nostartfiles', '-no-pie',
                          '-Wl,--build-id=none', '-Wl,--export-dynamic', '-o', binary, source, '-lc'])
    assert result.returncode == 0, result.stderr
    elf = ELFFile(BytesIO(binary.read_bytes()))
    symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()
               if s.name and s['st_shndx'] != 'SHN_UNDEF'}
    return binary, symbols


async def tool_data(session, tool_name, **arguments):
    async with asyncio.timeout(90):
        result = await mcp_tool_record(session, tool_name, arguments)
    assert not result['isError'], result
    body = result['structuredContent']
    assert isinstance(body, dict), result
    return body


async def tool_refused(session, tool_name, **arguments):
    async with asyncio.timeout(90):
        result = await mcp_tool_record(session, tool_name, arguments)
    assert result['isError'], result
    # No stable structured error category is published by the baseline server.
    # Do not classify its free-text error message.
    return result


def protocol_case(function):
    """Run each planned scenario in its own real stdio server and temporary image."""
    @wraps(function)
    def run(tmp_path):
        binary, symbols = session_program(tmp_path)
        async def exercise():
            async with refinement_session() as session:
                loaded = await tool_data(session, 'load_binary', binary_path=str(binary))
                await function(session, loaded['project_id'], binary, symbols)
        asyncio.run(exercise())
    # The original coroutine's parameters are supplied here, not pytest fixtures.
    import inspect
    run.__signature__ = inspect.Signature([inspect.Parameter('tmp_path', inspect.Parameter.POSITIONAL_OR_KEYWORD)])
    return run


async def build_analysis(session, project_id):
    return await tool_data(session, 'get_cfg', project_id=project_id, data_references=True)


async def inspect_function(session, project_id, name=None, **options):
    if name is not None:
        options['name'] = name
    return await tool_data(session, 'get_function_info', project_id=project_id, **options)


def function_records(functions):
    """Read only the published fields, interpreting addresses numerically."""
    return [(int(function['address'], 16), function['name'],
             function['is_plt'], function['is_syscall']) for function in functions]


def rename_item(name, new_name):
    return {'kind': 'function', 'name': name, 'new_name': new_name}


def library_session_program(directory):
    """Build a native application with one locally available dependency."""
    library_source = directory / 'F20_library.S'
    library_source.write_text('''.text
.global session_dependency
.type session_dependency,@function
session_dependency: lea 13(%rdi),%eax
 ret
.size session_dependency,.-session_dependency
.section .note.GNU-stack,"",@progbits
''')
    application_source = directory / 'F20_library_app.S'
    application_source.write_text('''.text
.global _start
.type _start,@function
_start: call session_dependency@PLT
 jmp _start
.size _start,.-_start
.section .note.GNU-stack,"",@progbits
''')
    library = directory / 'libF20_session.so'
    application = application_source.with_suffix('.elf')
    compiler = require_tools('gcc')['gcc']
    for argv in ([compiler, '-shared', '-nostdlib', '-o', library, library_source],
                 [compiler, '-nostdlib', '-no-pie', '-o', application,
                  application_source, '-L' + str(directory), '-lF20_session',
                  '-Wl,-rpath,' + str(directory)]):
        result = run_command(argv)
        assert result.returncode == 0, result.stderr
    return application


def check_batch(body, statuses):
    assert [r['index'] for r in body['results']] == list(range(len(statuses)))
    assert [r['status'] for r in body['results']] == statuses
    assert body['total'] == len(statuses)
    for field, status in [('succeeded', 'ok'), ('unchanged', 'unchanged'),
                          ('failed', 'error'), ('skipped', 'skipped')]:
        assert body[field] == statuses.count(status)


@asynccontextmanager
async def network_session(transport):
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamable_http_client
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    command = [sys.executable, '-m', 'velnora.mcp', '--transport', transport,
               '--host', '127.0.0.1', '--port', str(port)]
    with managed_server(command) as (process, out, err):
        async def ready():
            if process.poll() is not None:
                err.seek(0)
                raise AssertionError(err.read().decode())
            probe = socket.socket()
            probe.settimeout(0.2)
            try:
                return probe.connect_ex(('127.0.0.1', port)) == 0
            finally:
                probe.close()
        await wait_until(ready, timeout=30)
        path = '/sse' if transport == 'sse' else '/mcp'
        client = sse_client if transport == 'sse' else streamable_http_client
        async with asyncio.timeout(90):
            async with client(f'http://127.0.0.1:{port}{path}') as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    yield session
