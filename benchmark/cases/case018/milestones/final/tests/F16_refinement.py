# feature: F16
"""Acceptance observations for native decompilation and persistent refinement."""
import asyncio

import pytest
from pycparser import c_ast
from _helpers import import_product
from F09_helpers import mcp_tool_record
from F16_helpers import (CObservation, ast_nodes, c_function, cli_decompile,
                         decompiled, parse_c, c_integer_type, refinement_program, rendered_identifiers,
                         symbol_address, refinement_session)
from velnora.analyses.decompiler.edits import (
    InvalidNameError, NameCollisionError,
    NotDecompiledError, TypeParseError, UnsupportedEditError, VariableNotFoundError,
    list_variable_names, rename_function, rename_global, rename_variable,
    require_cache, resolve_variable, set_comment, set_function_prototype, set_variable_type,
)


def test_c_computations_memory_calls_and_structured_control(tmp_path):
    project, _ = refinement_program(tmp_path)
    functions = {name: c_function(decompiled(project, name).text, name)
                 for name in ('arithmetic', 'memory', 'caller', 'structured')}
    for x, y in ((0, 0), (5, 12), (17, 3), (29, 41)):
        assert CObservation(functions['arithmetic']).run(x, y) == (x*3+y) ^ 19
    for before, increment in ((31, 4), (83, 12), (9, 0)):
        memory = {0x9000: before, 0x9004: 61}
        observation = CObservation(functions['memory'], memory=memory)
        assert observation.run(0x9000, increment) == before+increment-5
        assert memory == {0x9000: before+increment, 0x9004: 61}
    for x in (0, 3, 18):
        observation = CObservation(functions['caller'], callees={'arithmetic': lambda a, b: (a*3+b)^19})
        assert observation.run(x) == ((x*3+7)^19)+11
        assert observation.calls == [('arithmetic', (x, 7))]
    control = functions['structured']
    nodes = list(ast_nodes(control.body))
    assert any(isinstance(n, (c_ast.If, c_ast.TernaryOp, c_ast.Switch)) for n in nodes)
    assert any(isinstance(n, (c_ast.For, c_ast.While, c_ast.DoWhile)) for n in nodes)
    for n in (0, 1, 2, 5, 8, 13):
        assert CObservation(control).run(n) == sum(i if i & 1 else 2 for i in range(n))


def test_persistent_names_types_prototype_and_comments(tmp_path):
    project, _ = refinement_program(tmp_path)
    function = project.kb.functions['editing']
    codegen = decompiled(project, function)
    candidates = [resolve_variable(project.kb, function.addr, n)
                  for n in list_variable_names(codegen, project.kb, function.addr)]
    argument = next(v for v in candidates if v.kind == 'argument' and v.arg_index == 0)
    # Choose the stack local by public storage kind, not a generated name prefix.
    from velnora.sim_variable import SimStackVariable
    local = next(v for v in candidates if v.kind == 'local' and isinstance(v.unified, SimStackVariable))
    rename_variable(project, function, argument.name, 'incoming')
    rename_variable(project, function, local.name, 'retained')
    rename_variable(project, function, 'datum', 'world')
    rename_function(project, function, 'refined')
    set_variable_type(project, function, 'retained', 'long long')
    set_variable_type(project, function, 'incoming', 'unsigned int')
    set_variable_type(project, function, 'world', 'long long')
    text = decompiled(project, function, regen_clinic=True).text
    assert {'incoming', 'retained', 'world', 'refined'} <= rendered_identifiers(text)
    tree = c_function(text, 'refined')
    declaration = next(n for n in ast_nodes(tree) if isinstance(n, c_ast.Decl) and n.name == 'retained')
    assert c_integer_type(declaration.type.type.names) == (True, 64)
    assert c_integer_type(tree.decl.type.args.params[0].type.type.names) == (False, 32)
    assert c_integer_type(function.prototype.args[0].c_repr().split()) == (False, 32)
    # The new prototype names no argument, so the rename must survive on its own.
    set_function_prototype(project, function, 'long long refined(unsigned int)', redecompile=True)
    text = decompiled(project, function, regen_clinic=True).text
    assert {'incoming', 'retained', 'world', 'refined'} <= rendered_identifiers(text)
    tree = c_function(text, 'refined')
    declaration = next(n for n in ast_nodes(tree) if isinstance(n, c_ast.Decl) and n.name == 'retained')
    assert c_integer_type(declaration.type.type.names) == (True, 64)
    assert c_integer_type(tree.decl.type.type.type.names) == (True, 64)
    assert tree.decl.type.args.params[0].name == 'incoming'
    world = next(n for n in parse_c(text).ext if isinstance(n, c_ast.Decl) and n.name == 'world')
    assert c_integer_type(world.type.type.names) == (True, 64)
    assert project.kb.labels[symbol_address(project, 'datum')] == 'world'
    assert project.kb.functions[function.addr].name == 'refined'
    # Header and statement comments have different public locations.
    set_comment(project, function.addr, 'Header refinement note')
    statement_address = next(a for a, _ in require_cache(project.kb, function.addr).codegen.map_addr_to_pos.items()
                             if a != function.addr)
    set_comment(project, statement_address, 'Statement refinement note')
    text = require_cache(project.kb, function.addr).codegen.text
    assert 'Header refinement note' in text
    assert 'Statement refinement note' in text
    assert project.kb.comments[function.addr] == 'Header refinement note'
    set_comment(project, function.addr, '')
    set_comment(project, statement_address, '')
    text = require_cache(project.kb, function.addr).codegen.text
    assert function.addr not in project.kb.comments
    assert statement_address not in project.kb.comments
    assert 'Header refinement note' not in text and 'Statement refinement note' not in text


def test_name_validation_collisions_and_unchanged_edits(tmp_path):
    project, _ = refinement_program(tmp_path)
    function = project.kb.functions['arithmetic']
    codegen = decompiled(project, function)
    args = sorted((resolve_variable(project.kb, function.addr, n)
                   for n in list_variable_names(codegen, project.kb, function.addr)),
                  key=lambda v: -1 if v.arg_index is None else v.arg_index)
    args = [v for v in args if v.kind == 'argument']
    original = function.name
    for invalid in ('', '9start', 'has-dash', 'has space'):
        with pytest.raises(InvalidNameError):
            rename_function(project, function, invalid)
        with pytest.raises(InvalidNameError):
            rename_variable(project, function, args[0].name, invalid)
        assert function.name == original
    assert rename_function(project, function, '_Valid9').changed
    assert rename_function(project, function, '_Valid9').changed is False
    assert rename_function(project, function, 'qualified::operation', strict_names=False).changed
    assert function.name == 'qualified::operation'
    with pytest.raises(InvalidNameError):
        rename_function(project, function, 'white\tspace', strict_names=False)
    with pytest.raises(NameCollisionError):
        rename_function(project, function, 'memory', allow_overwrite=False)
    # Refusal applies only to names already taken.
    assert rename_function(project, function, 'unclaimed_name', allow_overwrite=False).changed
    assert rename_function(project, function, 'memory').changed
    assert project.kb.functions[function.addr].name == 'memory'
    assert rename_variable(project, function, args[0].name, '_input9', allow_overwrite=False).changed
    assert rename_variable(project, function, '_input9', '_input9').changed is False
    with pytest.raises(NameCollisionError):
        rename_variable(project, function, '_input9', args[1].name, allow_overwrite=False)
    assert rename_variable(project, function, '_input9', args[1].name).changed
    assert rename_variable(project, function, args[1].name, 'input::relaxed', strict_names=False).changed
    assert 'input::relaxed' in list_variable_names(require_cache(project.kb, function.addr).codegen, project.kb, function.addr)
    with pytest.raises(InvalidNameError):
        rename_variable(project, function, 'input::relaxed', 'bad\nname', strict_names=False)


def test_variable_edit_prerequisites_and_distinct_errors(tmp_path):
    project, binary = refinement_program(tmp_path)
    function = project.kb.functions['arithmetic']
    with pytest.raises(NotDecompiledError):
        rename_variable(project, function, 'anything', 'incoming')
    codegen = decompiled(project, function)
    argument = next(resolve_variable(project.kb, function.addr, n)
                    for n in list_variable_names(codegen, project.kb, function.addr)
                    if resolve_variable(project.kb, function.addr, n).kind == 'argument')
    with pytest.raises(VariableNotFoundError):
        rename_variable(project, function, 'missing_variable', 'incoming')
    with pytest.raises(TypeParseError):
        set_variable_type(project, function, argument.name, 'not a type !!')

    async def exercise():
        async with refinement_session() as session:
            async def tool(tool_name, **arguments):
                result = await mcp_tool_record(session, tool_name, arguments)
                assert not result['isError'], result
                return result['structuredContent']
            loaded = await tool('load_binary', binary_path=str(binary), auto_load_libs=False)
            pid = loaded['project_id']
            await tool('get_cfg', project_id=pid)
            item = {'kind': 'variable', 'function': 'arithmetic', 'name': argument.name, 'new_name': 'incoming'}
            refused = await tool('rename', project_id=pid, items=[item], auto_decompile=False)
            assert refused['results'][0]['status'] == 'error'
            assert refused['results'][0]['error_kind'] == 'InvalidArgumentError'
            applied = await tool('rename', project_id=pid, items=[item], auto_decompile=True)
            assert applied['results'][0]['status'] == 'ok', applied
            rendered = await tool('decompile_function', project_id=pid, name='arithmetic')
            assert 'incoming' in rendered_identifiers(rendered['code'])
            await tool('rename', project_id=pid, items=[{'kind': 'function', 'name': 'arithmetic', 'new_name': 'ambiguous'},
                                                     {'kind': 'function', 'name': 'memory', 'new_name': 'ambiguous'}],
                       allow_overwrite=True)
            refused = await tool('rename', project_id=pid, items=[{'kind': 'function', 'name': 'ambiguous', 'new_name': 'unique'}])
            assert refused['results'][0]['status'] == 'error'
            assert refused['results'][0]['error_kind'] == 'AmbiguousFunctionError'
            for name in ('arithmetic', 'memory'):
                info = await tool('get_function_info', project_id=pid, address=hex(project.kb.functions[name].addr))
                assert info['name'] == 'ambiguous'
    asyncio.run(exercise())


def test_global_function_conflict_has_live_global_baseline(tmp_path):
    project, _ = refinement_program(tmp_path)
    decompiled(project, 'editing')
    address = symbol_address(project, 'datum')
    assert rename_global(project, address, 'renamed_data').changed
    assert project.kb.labels[address] == 'renamed_data'
    assert 'renamed_data' in rendered_identifiers(decompiled(project, 'editing', regen_clinic=True).text)
    function = project.kb.functions['arithmetic']
    old = function.name
    with pytest.raises(UnsupportedEditError):
        rename_global(project, function.addr, 'not_a_global')
    assert project.kb.functions[function.addr].name == old
    assert project.kb.labels[address] == 'renamed_data'


def test_mcp_function_edit_address_precedence_and_containing_extent(tmp_path):
    project, binary = refinement_program(tmp_path)
    first = project.kb.functions['arithmetic'].addr
    second = project.kb.functions['memory'].addr
    async def exercise():
        async with refinement_session() as session:
            async def tool(tool_name, **arguments):
                result = await mcp_tool_record(session, tool_name, arguments)
                assert not result['isError'], result
                return result['structuredContent']
            pid = (await tool('load_binary', binary_path=str(binary), auto_load_libs=False))['project_id']
            await tool('get_cfg', project_id=pid)
            for address, name, expected in ((first, 'memory', first), (second+1, 'address_wins', second)):
                new = 'address_wins' if expected == first else 'interior_wins'
                result = await tool('rename', project_id=pid, items=[{'kind': 'function', 'name': name,
                                                                 'address': hex(address), 'new_name': new}])
                entry = result['results'][0]
                assert entry['status'] == 'ok', entry
                assert int(entry['function_address'], 16) == expected
                info = await tool('get_function_info', project_id=pid, address=hex(expected))
                assert info['name'] == new
            result = await tool('rename', project_id=pid, items=[{'kind': 'function', 'name': 'address_wins',
                                                              'address': '0x123', 'new_name': 'wrong_target'}])
            assert result['results'][0]['status'] == 'error'
            assert result['results'][0]['error_kind'] == 'FunctionNotFoundError'
            info = await tool('get_function_info', project_id=pid, address=hex(first))
            assert info['name'] == 'address_wins'
    asyncio.run(exercise())


def test_cli_function_selection_and_explicit_error_continuation(tmp_path):
    project, binary = refinement_program(tmp_path)
    for selection in ('arithmetic', hex(project.kb.functions['arithmetic'].addr)):
        result = cli_decompile(binary, '--functions', selection)
        assert result.returncode == 0, result.stderr
        function = c_function(result.stdout.decode(), 'arithmetic')
        assert CObservation(function).run(8, 6) == (8*3+6)^19
    missing = 'unavailable_function'
    result = cli_decompile(binary, '--functions', missing, 'arithmetic')
    assert result.returncode == 1
    assert any(line.startswith('ValueError:') and missing in line
               for line in result.stderr.decode().splitlines())
    result = cli_decompile(binary, '--functions', missing, 'arithmetic', '--catch-exceptions')
    assert result.returncode == 0, result.stderr
    assert missing in result.stderr.decode()
    function = c_function(result.stdout.decode(), 'arithmetic')
    assert CObservation(function).run(9, 4) == (9*3+4)^19

    from F16_helpers import oversized_cli_program
    large_binary, address = oversized_cli_program(tmp_path)
    result = cli_decompile(large_binary, '--functions', hex(address), 'healthy', '--catch-exceptions')
    assert result.returncode == 0, result.stderr
    assert hex(address) in result.stderr.decode()
    assert 'max_function_blocks' in result.stderr.decode()
    assert CObservation(c_function(result.stdout.decode(), 'healthy')).run() == 9


def test_cli_raw_image_prerequisites_and_success(tmp_path):
    raw = tmp_path / 'F16_raw.bin'
    # lea eax,[rdi+9]; ret -- independently specified scalar computation.
    raw.write_bytes(bytes.fromhex('8d4709c3'))
    options = [('--arch', 'amd64'), ('--base-addr', '0x400000'), ('--entry-point', '0x400000')]
    result = cli_decompile(raw, '--blob', *(a for pair in options for a in pair), '--functions', '0x400000')
    assert result.returncode == 0, result.stderr
    functions = [n for n in parse_c(result.stdout.decode()).ext if isinstance(n, c_ast.FuncDef)]
    assert len(functions) == 1
    for x in (0, 7, 31):
        assert CObservation(functions[0]).run(x) == x+9
    for missing, _ in options:
        result = cli_decompile(raw, '--blob', *(a for pair in options if pair[0] != missing for a in pair),
                               '--functions', '0x400000')
        assert result.returncode == 2
        assert result.stdout == b''
        # Read argparse's error line and the option names it reports, not its prose.
        errors = [line.partition('error:')[2] for line in result.stderr.decode().splitlines() if 'error:' in line]
        assert len(errors) == 1
        assert '--blob' in errors[0].split() and missing in errors[0].split()


def test_bidirectional_instruction_mapping_and_known_call_prototype(tmp_path):
    from F16_helpers import mapping_program, statement_interval
    project = mapping_program(tmp_path)
    function = project.kb.functions[symbol_address(project, 'mapped')]
    rename_function(project, function, 'mapped')
    known = project.kb.functions['known']
    # The supplied two-argument prototype differs from the one-argument body.
    set_function_prototype(project, known, 'int known(int input_value, int extra)')
    set_function_prototype(project, function, 'int mapped(void)')
    codegen = decompiled(project, function)
    text = codegen.text
    tree = c_function(text, 'mapped')
    observation = CObservation(tree, globals_={'left': 0, 'right': 0}, callees={'known': lambda x, y: x+3})
    assert observation.run() == 19
    assert observation.env['left'] == 17 and observation.env['right'] == 29
    assert observation.calls == [('known', (5, 6))]
    intervals = []
    for target, instruction, expected in (('left', 'write_left', 17), ('right', 'write_right', 29)):
        statement = next(n for n in ast_nodes(tree) if isinstance(n, c_ast.Assignment)
                         and isinstance(n.lvalue, c_ast.ID) and n.lvalue.name == target)
        assert CObservation(tree).expr(statement.rvalue) == expected
        start, end = statement_interval(text, statement)
        address = symbol_address(project, instruction)
        position = codegen.map_addr_to_pos.get_nearest_pos(address)
        assert position is not None and start <= position < end, (instruction, position, text)
        # The forward source is read independently over that semantic statement.
        sources = {element.obj.tags['ins_addr'] for _, element in codegen.map_pos_to_addr.items()
                   if start <= element.start < end}
        assert address in sources
        intervals.append((start, end))
    assert intervals[0][1] <= intervals[1][0] or intervals[1][1] <= intervals[0][0]
    call = next(n for n in ast_nodes(tree) if isinstance(n, c_ast.FuncCall))
    assert call.name.name == 'known'
    assert len(call.args.exprs) == 2
    start, end = statement_interval(text, call)
    address = symbol_address(project, 'invoke_known')
    position = codegen.map_addr_to_pos.get_nearest_pos(address)
    assert position is not None and start <= position < end
    assert any(element.obj.tags['ins_addr'] == address for _, element in codegen.map_pos_to_addr.items()
               if start <= element.start < end)


def test_block_complexity_limits_boundaries_disable_and_cached_requests():
    from F16_helpers import block_chain
    velnora = import_product()
    project, function = block_chain(5)
    assert len(function.block_addrs_set) == 5
    def request(limit):
        return project.analyses[velnora.analyses.Decompiler].prep(fail_fast=False)(
            function, options=[('max_function_blocks', limit)])
    for limit in (5, 4, 0, 4, 6):
        result = request(limit)
        if limit == 4:
            assert result.codegen is None
            error = result.complexity_error
            assert error is not None
            assert error.limit_name == 'max_function_blocks'
            assert error.limit == limit and error.actual == 5
        else:
            assert result.complexity_error is None
            assert result.codegen is not None
            functions = [n for n in parse_c(result.codegen.text).ext if isinstance(n, c_ast.FuncDef)]
            assert len(functions) == 1
            assert CObservation(functions[0], callees={'__readeflags': lambda: 0}).run() == 43
    # A real recovered function exceeds the documented default by one block.
    # No private graph construction or reading an option's default substitutes
    # for exercising the default refusal path.
    large, large_function = block_chain(50001)
    assert len(large_function.block_addrs_set) == 50001
    result = large.analyses[velnora.analyses.Decompiler].prep(fail_fast=False)(large_function)
    assert result.codegen is None
    assert result.complexity_error.limit_name == 'max_function_blocks'
    assert result.complexity_error.limit == 50000
    assert result.complexity_error.actual == 50001


def test_output_languages_recover_language_constructs(tmp_path):
    from F16_helpers import (SyntaxGroup, SyntaxLiteral, language_corpus, pseudocode_syntax,
                             scalar_language_observation, syntax_calls, syntax_function, go_scalar_results,
                             syntax_groups, syntax_statements, syntax_comma_items)
    project, _ = refinement_program(tmp_path)
    for options in ({}, {'flavor': 'pseudocode'}):
        function = c_function(decompiled(project, 'arithmetic', **options).text, 'arithmetic')
        assert CObservation(function).run(11, 7) == (11*3+7)^19
    for language in ('rust', 'go'):
        text = decompiled(project, 'arithmetic', flavor=language).text
        for arguments in ((0, 1), (5, 13), (17, 8)):
            assert scalar_language_observation(text, language, arguments) == (arguments[0]*3+arguments[1])^19
    # Selecting another language for earlier requests does not change the default.
    function = c_function(decompiled(project, 'arithmetic').text, 'arithmetic')
    assert CObservation(function).run(4, 9) == (4*3+9)^19
    observed = []
    for language, texts in language_corpus(tmp_path):
        observed.append(language)
        trees = {name: pseudocode_syntax(text) for name, text in texts.items()}
        if language == 'rust':
            _, _, _, _, body = syntax_function(trees['fmt'], 'rust')
            groups = list(syntax_groups(body))
            statements = [s for group in groups for s in syntax_statements(group, newline_terminates=False)]
            # References must bind to real expressions, not just decorate a header.
            declarations = [s[2:] if s[1] == 'mut' else s[1:]
                            for s in statements if len(s) >= 2 and s[0] == 'let']
            reference_names = {s[0] for s in declarations if len(s) >= 4 and s[1:3] == (':', '&')}
            assert reference_names
            assert any('&' in args.items for _, args in syntax_calls(body))
            # Read nonempty aggregate field/value syntax without generated type or field names.
            assert any(any(len(s) >= 3 and s[1] == ':' for s in syntax_statements(group))
                       for group in groups if group.opener == '{')
            alternatives = {name for name, _ in syntax_calls(body) if name in ('Some', 'Ok')}
            assert 'Ok' in alternatives
            macros = [args for name, args in syntax_calls(body) if name == 'format!']
            assert any(args.items and args.items[0] == SyntaxLiteral('invalid width: {}')
                       and ',' in args.items and len(args.items) > 2 for args in macros)
        elif 'main.main' in trees:
            _, _, _, _, main = syntax_function(trees['main.main'], 'go', 'main.main')
            calls = list(syntax_calls(main))
            assert any(name == 'count' and args.items == (SyntaxLiteral('hello, world'), ',', SyntaxLiteral('l'))
                       for name, args in calls)
            slices = [args.items for name, args in calls if name == 'bump']
            assert any(len(items) == 3 and isinstance(items[0], SyntaxGroup) and items[0].opener == '['
                       and items[0].items == () and items[1] == 'int' and isinstance(items[2], SyntaxGroup)
                       and items[2].opener == '{'
                       and syntax_comma_items(items[2])[:3] == (('1',), ('2',), ('3',))
                       for items in slices)
            _, _, params, results, parse = syntax_function(trees['main.parse'], 'go', 'main.parse')
            assert len(params.items) == 2 and params.items[1] == 'string'
            assert len(results) == 1 and isinstance(results[0], SyntaxGroup)
            assert results[0].items == ('int', ',', 'error')
            parameter = params.items[0]
            assert any(name == 'Atoi' and args.items == (parameter,) for name, args in syntax_calls(parse))
            returns = [s for group in syntax_groups(parse) for s in syntax_statements(group)
                       if s and s[0] == 'return']
            assert any(len(s) == 4 and s[1:3] == ('0', ',') for s in returns)
            assert any(len(s) == 4 and s[2:] == (',', 'nil') for s in returns)
            _, _, _, result, division = syntax_function(trees['main.divmod'], 'go', 'main.divmod')
            assert len(result) == 1 and result[0].items == ('int', ',', 'int')
            division_returns = [s for group in syntax_groups(division) for s in syntax_statements(group)
                                if s and s[0] == 'return']
            assert any(len(s) == 4 and s[2] == ',' and s[1] != s[3] for s in division_returns)
            for arguments, expected in (((13, 5), (2, 3)), ((21, 4), (5, 1)),
                                        ((-13, 5), (-2, -3)), ((13, -5), (-2, 3))):
                assert go_scalar_results(texts['main.divmod'], 'main.divmod', arguments) == expected
        else:
            receiver, _, params, result, body = syntax_function(next(iter(trees.values())), 'go', 'Error')
            assert receiver is not None and receiver.opener == '(' and len(receiver.items) >= 2
            assert params.items == () and result == ('string',)
            returns = [s for s in syntax_statements(body) if s and s[0] == 'return']
            assert len(returns) == 1
            expression = returns[0][1:]
            assert expression[0] == SyntaxLiteral('github recipient ')
            assert expression[-1] == SyntaxLiteral(' has no public keys')
            assert receiver.items[0] in expression and expression.count('+') == 2
    assert observed == ['go', 'go', 'rust']
