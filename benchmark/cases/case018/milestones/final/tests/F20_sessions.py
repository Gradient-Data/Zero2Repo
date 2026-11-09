# feature: F20
"""Acceptance tests for local MCP sessions through real protocol exchanges."""
import shutil

from F16_helpers import (CObservation, c_function, c_integer_type, scalar_language_observation,
                         pseudocode_syntax, syntax_function)
from F20_helpers import (protocol_case, tool_data, tool_refused, build_analysis,
                         inspect_function, rename_item, function_records, check_batch, network_session,
                         library_session_program)


@protocol_case
async def test_sessions_isolate_analysis_edits_and_closure(s, pid, binary, symbols):
    # The second session loads a copy, so each listed image must be its own.
    second = binary.parent / 'F20_second.elf'
    shutil.copyfile(binary, second)
    other = (await tool_data(s, 'load_binary', binary_path=str(second)))['project_id']
    assert other != pid
    listing = await tool_data(s, 'list_projects')
    projects = {p['project_id']: p for p in listing['projects']}
    assert listing['count'] == 2
    for key, path in ((pid, binary), (other, second)):
        assert projects[key]['binary_path'] == str(path.resolve())
        assert projects[key]['has_cfg'] is False
    await build_analysis(s, pid)
    projects = {p['project_id']: p for p in (await tool_data(s, 'list_projects'))['projects']}
    assert projects[pid]['has_cfg'] is True
    assert projects[other]['has_cfg'] is False
    await build_analysis(s, other)
    for key, old, new in [(pid, 'compute', 'first_compute'), (other, 'caller', 'second_caller')]:
        check_batch(await tool_data(s, 'rename', project_id=key, items=[rename_item(old, new)]), ['ok'])
    assert int((await inspect_function(s, pid, 'first_compute'))['address'], 16) == symbols['compute']
    assert int((await inspect_function(s, other, 'compute'))['address'], 16) == symbols['compute']
    assert int((await inspect_function(s, pid, 'caller'))['address'], 16) == symbols['caller']
    assert int((await inspect_function(s, other, 'second_caller'))['address'], 16) == symbols['caller']
    assert (await tool_data(s, 'close_project', project_id=pid))['closed'] is True
    for closed_id in (pid, 'nonexistent-session'):
        assert (await tool_data(s, 'close_project', project_id=closed_id))['closed'] is False
    listing = await tool_data(s, 'list_projects')
    assert listing['count'] == 1
    assert {p['project_id'] for p in listing['projects']} == {other}
    await tool_refused(s, 'get_function_info', project_id=pid, name='first_compute')
    await tool_refused(s, 'get_cfg', project_id='nonexistent-session')
    for closed_id in (pid, 'nonexistent-session'):
        await tool_refused(s, 'rename', project_id=closed_id,
                           items=[rename_item('first_compute', 'after_close')])
    assert (await inspect_function(s, other, 'second_caller'))['name'] == 'second_caller'


@protocol_case
async def test_function_query_prerequisites_and_targets(s, pid, binary, symbols):
    await tool_refused(s, 'get_function_info', project_id=pid, name='compute')
    await tool_refused(s, 'list_functions', project_id=pid)
    await build_analysis(s, pid)
    assert int((await inspect_function(s, pid, 'compute'))['address'], 16) == symbols['compute']
    for selection in ({'name': 'absent_function'}, {'address': '0x123'}, {}):
        await tool_refused(s, 'get_function_info', project_id=pid, **selection)
    assert (await inspect_function(s, pid, address=hex(symbols['caller'])))['name'] == 'caller'


@protocol_case
async def test_cfg_blocks_conventions_and_decompiled_computation(s, pid, binary, symbols):
    cfg = await build_analysis(s, pid)
    assert cfg['status'] == 'success'
    info = await inspect_function(s, pid, 'compute', include_blocks=True)
    assert int(info['address'], 16) == symbols['compute']
    assert info['size'] == 4
    assert info['num_blocks'] == 1
    assert [int(address, 16) for address in info['block_addresses']] == [symbols['compute']]
    blocks = await tool_data(s, 'get_basic_blocks', project_id=pid, function_address=info['address'])
    assert blocks['block_count'] == 1
    instructions = blocks['blocks'][0]['instructions']
    assert [(int(i['address'], 16), bytes.fromhex(i['bytes'])) for i in instructions] == [
        (symbols['compute'], b'\x8d\x47\x09'), (symbols['compute']+3, b'\xc3')]
    assert [i['mnemonic'].lower() for i in instructions] == ['lea', 'ret']
    await tool_data(s, 'recover_calling_conventions', project_id=pid)
    info = await inspect_function(s, pid, 'compute')
    # A real prototype and convention must describe the single integer argument.
    assert info['calling_convention'] == '<SimCCSystemVAMD64>'
    assert info['prototype'].startswith('(') and '->' in info['prototype']
    arguments = info['prototype'][1:info['prototype'].index(')')]
    assert arguments.strip() and ',' not in arguments
    dec = await tool_data(s, 'decompile_function', project_id=pid, name='compute')
    function = c_function(dec['code'], 'compute')
    for value in (0, 5, 31):
        assert CObservation(function).run(value) == value+9


@protocol_case
async def test_imports_exports_xrefs_and_call_relationships(s, pid, binary, symbols):
    imports = await tool_data(s, 'get_imports', project_id=pid)
    assert 'puts' in {i['name'] for i in imports['imports']}
    exports = await tool_data(s, 'get_exports', project_id=pid)
    exported = {i['name']: int(i['address'], 16) for i in exports['exports']}
    for name in ('compute', 'caller', 'string_user'):
        assert exported[name] == symbols[name]
    await build_analysis(s, pid)
    for direction, address in [('to', symbols['message']), ('from', symbols['data_ref'])]:
        refs = await tool_data(s, 'get_xrefs', project_id=pid, address=hex(address), direction=direction)
        assert (symbols['data_ref'], symbols['message']) in {
            (int(r['from_address'], 16), int(r['to_address'], 16)) for r in refs['xrefs']}
    graph = await tool_data(s, 'get_callgraph', project_id=pid)
    assert (symbols['caller'], symbols['compute']) in {(int(e['from'], 16), int(e['to'], 16)) for e in graph['edges']}
    assert {symbols[n] for n in ('caller', 'compute')} <= {int(n['address'], 16) for n in graph['nodes']}


@protocol_case
async def test_function_filter_intersection_order_and_pagination(s, pid, binary, symbols):
    await build_analysis(s, pid)
    all_body = await tool_data(s, 'list_functions', project_id=pid, limit=1000)
    all_functions = all_body['functions']
    addresses = [int(f['address'], 16) for f in all_functions]
    assert addresses == sorted(addresses)
    assert {symbols[f'sample_{i}'] for i in range(105)} <= {int(f['address'], 16) for f in all_functions}
    assert any(f['name'] == 'puts' and f['is_plt'] for f in all_functions)
    ordinary_addresses = {symbols[n] for n in ('compute', 'caller', 'string_user')}
    ordinary_addresses.update(symbols[f'sample_{i}'] for i in range(105))
    for function in all_functions:
        if int(function['address'], 16) in ordinary_addresses:
            assert function['is_plt'] is False and function['is_syscall'] is False
    assert any(f['is_syscall'] for f in all_functions)
    default = await tool_data(s, 'list_functions', project_id=pid)
    assert (default['offset'], default['limit'], default['total']) == (0, 100, len(all_functions))
    assert function_records(default['functions']) == function_records(all_functions[:100])
    for field in ('filter_plt', 'filter_syscall'):
        flag = 'is_plt' if field == 'filter_plt' else 'is_syscall'
        for choice in (True, False):
            body = await tool_data(s, 'list_functions', project_id=pid, limit=1000, **{field: choice})
            expected = [f for f in all_functions if f[flag] == choice]
            assert function_records(body['functions']) == function_records(expected)
            assert body['total'] == len(expected)
    named = await tool_data(s, 'list_functions', project_id=pid, name_pattern='SaMpLe_', limit=1000)
    expected = [f for f in all_functions if 'sample_' in f['name'].lower()]
    assert function_records(named['functions']) == function_records(expected)
    # Exercise category intersections without assuming a generated syscall name.
    for pattern in ('T', 'SaMpLe_', ''):
        matching = [f for f in all_functions if pattern.lower() in f['name'].lower()
                    and not f['is_plt'] and not f['is_syscall']]
        body = await tool_data(s, 'list_functions', project_id=pid, name_pattern=pattern,
                               filter_plt=False, filter_syscall=False, offset=2, limit=3)
        assert (body['total'], body['offset'], body['limit']) == (len(matching), 2, 3)
        assert function_records(body['functions']) == function_records(matching[2:5])



@protocol_case
async def test_function_name_search_modes_and_invalid_search(s, pid, binary, symbols):
    await build_analysis(s, pid)
    patterns = [('contains', 'MPLE_10', {f'sample_{i}' for i in range(10, 11)} | {f'sample_{i}' for i in range(100, 105)}),
                ('startswith', 'SaMpLe_10', {'sample_10', *(f'sample_{i}' for i in range(100, 105))}),
                ('endswith', 'PLE_10', {'sample_10'}),
                ('regex', '^SAMPLE_(2|3)$', {'sample_2', 'sample_3'})]
    for mode, pattern, expected in patterns:
        result = await tool_data(s, 'find_functions_by_pattern', project_id=pid, pattern=pattern, search_type=mode)
        assert {f['name'] for f in result['functions']} == expected
        assert result['count'] == len(expected)
    default = await tool_data(s, 'find_functions_by_pattern', project_id=pid, pattern='MPLE_10')
    assert default['search_type'] == 'contains'
    assert {f['name'] for f in default['functions']} == patterns[0][2]
    for arguments in ({'pattern': '[', 'search_type': 'regex'}, {'pattern': 'sample', 'search_type': 'unknown'}):
        await tool_refused(s, 'find_functions_by_pattern', project_id=pid, **arguments)


@protocol_case
async def test_referenced_ascii_strings_and_limits(s, pid, binary, symbols):
    await build_analysis(s, pid)
    complete = await tool_data(s, 'get_strings', project_id=pid, limit=1000)
    strings = {int(r['address'], 16): r['content'] for r in complete['strings']}
    assert strings[symbols['message']] == 'session referenced message'
    for i in range(105):
        assert strings[symbols[f'message_{i}']] == f'referenced message number {i}'
    assert symbols['hidden_message'] not in strings
    assert symbols['short_message'] not in strings
    # The four-character string sits exactly on the default minimum.
    assert strings[symbols['four_message']] == 'abcd'
    defaults = await tool_data(s, 'get_strings', project_id=pid)
    assert defaults['count'] == len(defaults['strings']) == 100
    assert all(len(r['content']) >= 4 for r in defaults['strings'])
    for options in ({'min_length': 3, 'limit': 1000}, {'min_length': 25, 'limit': 7}):
        body = await tool_data(s, 'get_strings', project_id=pid, **options)
        assert body['count'] == len(body['strings'])
        assert all(len(r['content']) >= options['min_length'] for r in body['strings'])
        if options['min_length'] == 3:
            assert (symbols['short_message'], 'xyz') in {(int(r['address'], 16), r['content']) for r in body['strings']}
        else:
            assert body['count'] == 7
    # Message lengths are 26 ('message'), 27 (numbers 0-9) and 28 (10-104),
    # so a selected minimum above four must actually remove candidates.
    for minimum, names in ((5, {'message', *(f'message_{i}' for i in range(105))}),
                           (28, {f'message_{i}' for i in range(10, 105)})):
        body = await tool_data(s, 'get_strings', project_id=pid, min_length=minimum, limit=1000)
        selected = {int(r['address'], 16) for r in body['strings']}
        assert {symbols[n] for n in names} <= selected
        assert symbols['four_message'] not in selected
        if minimum == 28:
            assert symbols['message'] not in selected
            assert not {symbols[f'message_{i}'] for i in range(10)} & selected


@protocol_case
async def test_language_defaults_overrides_and_language_scoped_edits(s, pid, binary, symbols):
    await build_analysis(s, pid)
    await tool_data(s, 'recover_calling_conventions', project_id=pid)
    assert (await tool_data(s, 'get_decompilation_flavor', project_id=pid))['flavor'] == 'pseudocode'
    for language in ('pseudocode', 'rust', 'go'):
        before = await tool_data(s, 'decompile_function', project_id=pid, name='compute', flavor=language)
        assert before['flavor'] == language
        for value in (0, 7):
            observed = (CObservation(c_function(before['code'], 'compute')).run(value) if language == 'pseudocode'
                        else scalar_language_observation(before['code'], language, (value,)))
            assert observed == value+9
        assert (await tool_data(s, 'get_decompilation_flavor', project_id=pid))['flavor'] == 'pseudocode'
    # After the per-request overrides, an unqualified request is still C-like.
    plain = await tool_data(s, 'decompile_function', project_id=pid, name='compute')
    assert plain['flavor'] == 'pseudocode'
    assert CObservation(c_function(plain['code'], 'compute')).run(11) == 20
    await tool_data(s, 'set_decompilation_flavor', project_id=pid, flavor='go')
    check_batch(await tool_data(s, 'set_type', project_id=pid, items=[
        {'kind': 'function', 'name': 'compute', 'type': 'int f(unsigned int go_seed)'}]), ['ok'])
    go = await tool_data(s, 'decompile_function', project_id=pid, name='compute')
    _, _, params, _, _ = syntax_function(pseudocode_syntax(go['code']), 'go')
    old_name = params.items[0]
    result = await tool_data(s, 'rename', project_id=pid, items=[
        {'kind': 'variable', 'function': 'compute', 'name': old_name, 'new_name': 'language_input'}])
    check_batch(result, ['ok'])
    typed = await tool_data(s, 'set_type', project_id=pid, redecompile=True, items=[
        {'kind': 'variable', 'function': 'compute', 'name': 'language_input', 'type': 'unsigned short'}])
    check_batch(typed, ['ok'])
    after = await tool_data(s, 'decompile_function', project_id=pid, name='compute')
    _, _, params, _, _ = syntax_function(pseudocode_syntax(after['code']), 'go')
    assert 'language_input' in params.items and 'uint16' in params.items
    c = await tool_data(s, 'decompile_function', project_id=pid, name='compute', flavor='pseudocode')
    c_compute = c_function(c['code'], 'compute')
    c_parameter = c_compute.decl.type.args.params[0]
    # The Go-view type edit does not become the C view's parameter type.
    assert c_integer_type(c_parameter.type.type.names)[1] != 16
    assert CObservation(c_compute).run(7) == 16
    assert (await tool_data(s, 'get_decompilation_flavor', project_id=pid))['flavor'] == 'go'
    await tool_data(s, 'set_decompilation_flavor', project_id=pid, flavor='rust')
    assert (await tool_data(s, 'decompile_function', project_id=pid, name='compute'))['flavor'] == 'rust'
    for tool, options in [('set_decompilation_flavor', {'flavor': 'cobol'}),
                          ('decompile_function', {'name': 'compute', 'flavor': 'cobol'})]:
        await tool_refused(s, tool, project_id=pid, **options)
    assert (await tool_data(s, 'get_decompilation_flavor', project_id=pid))['flavor'] == 'rust'


@protocol_case
async def test_edit_batches_apply_and_validation_preserves_state(s, pid, binary, symbols):
    await build_analysis(s, pid)
    await tool_data(s, 'recover_calling_conventions', project_id=pid)
    for dry_run in (True, False):
        result = await tool_data(s, 'rename', project_id=pid, dry_run=dry_run,
                                 items=[rename_item('compute', 'renamed_compute'), rename_item('sample_1', 'renamed_sample')])
        check_batch(result, ['ok', 'ok'])
        assert [r['target'] for r in result['results']] == ['compute', 'sample_1']
        for original, renamed in [('compute', 'renamed_compute'), ('sample_1', 'renamed_sample')]:
            info = await inspect_function(s, pid, address=hex(symbols[original]))
            assert info['name'] == (original if dry_run else renamed)
    baseline = (await tool_data(s, 'decompile_function', project_id=pid, name='renamed_compute'))['code']
    other_baseline = (await tool_data(s, 'decompile_function', project_id=pid, name='sample_2'))['code']
    for dry_run in (True, False):
        types = await tool_data(s, 'set_type', project_id=pid, dry_run=dry_run,
                                items=[{'kind': 'function', 'name': 'renamed_compute', 'type': 'unsigned short f(unsigned short x)'},
                                       {'kind': 'function', 'name': 'sample_2', 'type': 'short f(void)'}])
        check_batch(types, ['ok', 'ok'])
        assert [int(r['function_address'], 16) for r in types['results']] == [symbols['compute'], symbols['sample_2']]
        comments = await tool_data(s, 'set_comments', project_id=pid, dry_run=dry_run,
                                   items=[{'kind': 'function', 'function': 'renamed_compute', 'comment': 'reviewed computation'},
                                          {'kind': 'function', 'function': 'sample_2', 'comment': 'reviewed constant'}])
        check_batch(comments, ['ok', 'ok'])
        code = (await tool_data(s, 'decompile_function', project_id=pid, name='renamed_compute'))['code']
        other_code = (await tool_data(s, 'decompile_function', project_id=pid, name='sample_2'))['code']
        if dry_run:
            before_type = c_function(baseline, 'renamed_compute').decl.type.type.type.names
            after_type = c_function(code, 'renamed_compute').decl.type.type.type.names
            other_before_type = c_function(other_baseline, 'sample_2').decl.type.type.type.names
            other_after_type = c_function(other_code, 'sample_2').decl.type.type.type.names
            assert c_integer_type(after_type) == c_integer_type(before_type)
            assert c_integer_type(other_after_type) == c_integer_type(other_before_type)
            assert 'reviewed computation' not in code and 'reviewed constant' not in other_code
            assert CObservation(c_function(code, 'renamed_compute')).run(12) == 21
            assert CObservation(c_function(other_code, 'sample_2')).run() == 2
        else:
            function = c_function(code, 'renamed_compute')
            assert c_integer_type(function.decl.type.type.type.names) == (False, 16)
            assert 'reviewed computation' in code
            assert CObservation(function).run(12) == 21
            other_function = c_function(other_code, 'sample_2')
            assert c_integer_type(other_function.decl.type.type.type.names) == (True, 16)
            assert 'reviewed constant' in other_code
            assert CObservation(other_function).run() == 2


@protocol_case
async def test_collisions_continuation_and_stop_preserve_prefix(s, pid, binary, symbols):
    await build_analysis(s, pid)
    result = await tool_data(s, 'rename', project_id=pid, items=[rename_item('compute', 'caller')])
    check_batch(result, ['error'])
    assert result['results'][0]['error_kind'] == 'NameCollisionError'
    assert (await inspect_function(s, pid, address=hex(symbols['compute'])))['name'] == 'compute'
    result = await tool_data(s, 'rename', project_id=pid, allow_overwrite=True, items=[rename_item('compute', 'caller')])
    check_batch(result, ['ok'])
    assert (await inspect_function(s, pid, address=hex(symbols['compute'])))['name'] == 'caller'
    for stop in (False, True):
        # Fresh identical sessions differ only in the stopping option.
        project = (await tool_data(s, 'load_binary', binary_path=str(binary)))['project_id']
        await build_analysis(s, project)
        start = 10
        items = [rename_item(f'sample_{start}', f'prefix_{start}'),
                 rename_item('missing_function', 'cannot_apply'),
                 rename_item(f'sample_{start+1}', f'suffix_{start}')]
        options = {'stop_on_error': True} if stop else {}
        result = await tool_data(s, 'rename', project_id=project, items=items, **options)
        check_batch(result, ['ok', 'error', 'skipped' if stop else 'ok'])
        assert result['results'][1]['error_kind'] == 'FunctionNotFoundError'
        assert (await inspect_function(s, project, address=hex(symbols[f'sample_{start}'])))['name'] == f'prefix_{start}'
        assert (await inspect_function(s, project, address=hex(symbols[f'sample_{start+1}'])))['name'] == (
            f'sample_{start+1}' if stop else f'suffix_{start}')
    unchanged = await tool_data(s, 'rename', project_id=pid, items=[rename_item('sample_30', 'sample_30')])
    check_batch(unchanged, ['unchanged'])


@protocol_case
async def test_malformed_batches_refused_without_losing_session(s, pid, binary, symbols):
    await build_analysis(s, pid)
    for tool in ('rename', 'set_type', 'set_comments'):
        for items in ([], ['not an object']):
            await tool_refused(s, tool, project_id=pid, items=items)
            assert int((await inspect_function(s, pid, 'compute'))['address'], 16) == symbols['compute']
    valid = await tool_data(s, 'rename', project_id=pid, items=[rename_item('compute', 'still_working')])
    check_batch(valid, ['ok'])
    assert int((await inspect_function(s, pid, 'still_working'))['address'], 16) == symbols['compute']


@protocol_case
async def test_raw_loader_architecture_and_unsupported_dos(s, pid, binary, symbols):
    raw = binary.parent / 'F20_raw.bin'
    raw.write_bytes(b'\xb8\x2b\x00\x00\x00\xc3')
    await tool_refused(s, 'load_binary', binary_path=str(raw), backend='blob')
    loaded = await tool_data(s, 'load_binary', binary_path=str(raw), backend='blob', arch='x86')
    assert loaded['bits'] == 32 and loaded['arch'].casefold() == 'x86'
    await build_analysis(s, loaded['project_id'])
    blocks = await tool_data(s, 'get_basic_blocks', project_id=loaded['project_id'], function_address=loaded['entry_point'])
    assert b''.join(bytes.fromhex(i['bytes']) for b in blocks['blocks'] for i in b['instructions']) == raw.read_bytes()
    dos = binary.parent / 'F20_dos.exe'
    dos.write_bytes(b'MZ'+bytes(126))
    await tool_refused(s, 'load_binary', binary_path=str(dos))
    assert (await tool_data(s, 'list_projects'))['count'] == 2
    dependency_app = library_session_program(binary.parent)
    for options, modeled in (({}, True), ({'auto_load_libs': True}, False)):
        project = (await tool_data(s, 'load_binary', binary_path=str(dependency_app), **options))['project_id']
        await build_analysis(s, project)
        functions = await tool_data(s, 'list_functions', project_id=project,
                                    name_pattern='session_dependency', filter_plt=False)
        assert len(functions['functions']) == 1
        info = await inspect_function(s, project, address=functions['functions'][0]['address'])
        assert info['is_simprocedure'] is modeled
        if not modeled:
            blocks = await tool_data(s, 'get_basic_blocks', project_id=project,
                                     function_address=info['address'])
            assert b''.join(bytes.fromhex(i['bytes']) for block in blocks['blocks']
                            for i in block['instructions']) == b'\x8d\x47\x0d\xc3'


@protocol_case
async def test_stdio_sse_http_protocol_and_analysis(s, pid, binary, symbols):
    # The decorator already initialized the default transport without a flag.
    for client, project in [(s, pid)]:
        await build_analysis(client, project)
        assert int((await inspect_function(client, project, 'compute'))['address'], 16) == symbols['compute']
    for transport in ('sse', 'http'):
        async with network_session(transport) as client:
            loaded = await tool_data(client, 'load_binary', binary_path=str(binary))
            project = loaded['project_id']
            await build_analysis(client, project)
            info = await inspect_function(client, project, 'compute')
            assert int(info['address'], 16) == symbols['compute']
            dec = await tool_data(client, 'decompile_function', project_id=project, name='compute')
            assert CObservation(c_function(dec['code'], 'compute')).run(13) == 22
