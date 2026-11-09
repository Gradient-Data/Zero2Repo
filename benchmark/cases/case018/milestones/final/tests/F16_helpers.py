# feature: F16
"""Real native inputs, C syntax parsing and bounded pseudocode observations."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
import operator
from pathlib import Path
import re
import shutil
import sys
import networkx
from pycparser import c_ast, c_parser
from _helpers import import_product, require_tools, run_command, temporary_environment
from F07_helpers import symbol_address
from F09_helpers import recovery_options


def refinement_program(directory):
    source = directory / 'F16_program.c'
    source.write_text('''
int datum = 37;
__attribute__((noinline)) int arithmetic(int x, int y) { return (x * 3 + y) ^ 19; }
__attribute__((noinline)) int memory(int *p, int x) { *p += x; return *p - 5; }
__attribute__((noinline)) int caller(int x) { return arithmetic(x, 7) + 11; }
__attribute__((noinline)) int structured(int x) {
    int s=0;
    for (int i=0;i<x;i++) { if (i & 1) s+=i; else s+=2; }
    return s;
}
__attribute__((noinline)) int editing(int x) { volatile int local=x+datum; return local+3; }
void _start(void) { for(;;) {} }
''')
    binary = directory / 'F16_program.elf'
    result = run_command([require_tools('gcc')['gcc'], '-O1', '-fno-stack-protector',
                          '-fno-pie', '-no-pie', '-nostdlib', '-o', binary, source])
    assert result.returncode == 0, result.stderr
    project = import_product().Project(str(binary), auto_load_libs=False)
    project.analyses.CFGFast(normalize=True, data_references=True, **recovery_options())
    project.analyses.CompleteCallingConventions(recover_variables=True, analyze_callsites=True)
    return project, binary


def decompiled(project, name, **options):
    function = project.kb.functions[name] if isinstance(name, str) else name
    result = project.analyses.Decompiler(function, **options)
    assert result.codegen is not None, result.errors
    return result.codegen


def strip_c_comments(text):
    # Preserve every coordinate and quoted literal while masking lexical trivia.
    pattern = r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|/\*.*?\*/|//[^\n]*"
    def mask(match):
        token = match.group()
        if token.startswith(('/*', '//')):
            return ''.join('\n' if char == '\n' else ' ' for char in token)
        return token
    return re.sub(pattern, mask, text, flags=re.S)


def parse_c(text):
    return c_parser.CParser().parse(strip_c_comments(text))


def c_integer_type(words):
    """Read the meaning of an AMD64 C integer type, not its optional spelling."""
    words = list(words)
    assert words and all(word in ('signed', 'unsigned', 'char', 'short', 'int', 'long')
                         for word in words), words
    assert not ('signed' in words and 'unsigned' in words), words
    width = 8 if 'char' in words else 16 if 'short' in words else 64 if 'long' in words else 32
    return 'unsigned' not in words, width


def ast_nodes(node):
    yield node
    for _, child in node.children():
        yield from ast_nodes(child)


def c_function(text, name):
    matches = [n for n in parse_c(text).ext if isinstance(n, c_ast.FuncDef) and n.decl.name == name]
    assert len(matches) == 1, (name, text)
    return matches[0]


class _Returned(Exception):
    def __init__(self, value):
        super().__init__()
        self.value = value


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class _Goto(Exception):
    def __init__(self, label):
        super().__init__()
        self.label = label


class CObservation:
    """Execute parsed scalar C with explicit memory/callees and a shared step bound.

    This is an outside interpreter of output syntax, not the product's AST or
    transform. Unsupported syntax and undefined reads fail visibly. Inputs avoid
    signed overflow and ambiguous C evaluation order.
    """
    def __init__(self, function, *, memory=None, globals_=None, callees=None, budget=10000):
        self.function = function
        self.memory = {} if memory is None else memory
        self.env = {} if globals_ is None else dict(globals_)
        self.callees = {} if callees is None else callees
        self.calls = []
        self.types = {}
        self.budget = budget

    def tick(self):
        self.budget -= 1
        assert self.budget >= 0, 'Pseudocode did not terminate within the observation bound'

    def type_of(self, node):
        if isinstance(node, c_ast.ID):
            return self.types.get(node.name)
        if isinstance(node, c_ast.Cast):
            return node.to_type.type
        if isinstance(node, c_ast.ArrayRef):
            return self.type_of(node.name).type
        if isinstance(node, c_ast.UnaryOp) and node.op == '*':
            return self.type_of(node.expr).type
        if isinstance(node, c_ast.BinaryOp) and node.op in ('+', '-'):
            if (node.op == '-' and isinstance(self.type_of(node.left), (c_ast.PtrDecl, c_ast.ArrayDecl))
                    and isinstance(self.type_of(node.right), (c_ast.PtrDecl, c_ast.ArrayDecl))):
                return None
            for operand in (node.left, node.right):
                typ = self.type_of(operand)
                if isinstance(typ, (c_ast.PtrDecl, c_ast.ArrayDecl)):
                    return typ
        return None

    def type_bytes(self, typ):
        if isinstance(typ, c_ast.PtrDecl):
            return 8  # These observations use AMD64 declarations.
        if isinstance(typ, c_ast.ArrayDecl):
            return self.type_bytes(typ.type) * self.expr(typ.dim)
        assert isinstance(typ, c_ast.TypeDecl), type(typ).__name__
        return c_integer_type(typ.type.names)[1] // 8

    def element_bytes(self, node):
        typ = self.type_of(node)
        assert isinstance(typ, (c_ast.PtrDecl, c_ast.ArrayDecl)), 'Subscript requires a pointer or array type'
        return self.type_bytes(typ.type)

    def store(self, node, value):
        if isinstance(node, c_ast.ID):
            self.env[node.name] = value
        elif isinstance(node, c_ast.UnaryOp) and node.op == '*':
            self.memory[self.expr(node.expr)] = value
        elif isinstance(node, c_ast.ArrayRef):
            self.memory[self.expr(node.name) + self.element_bytes(node.name)*self.expr(node.subscript)] = value
        else:
            raise AssertionError(f'Unsupported C lvalue: {type(node).__name__}')
        return value

    def expr(self, node):
        self.tick()
        if isinstance(node, c_ast.ID):
            return self.env[node.name]
        if isinstance(node, c_ast.ArrayRef):
            return self.memory[self.expr(node.name) + self.element_bytes(node.name)*self.expr(node.subscript)]
        if isinstance(node, c_ast.Constant):
            if node.type == 'char':
                import ast
                value = ast.literal_eval(node.value)
                assert isinstance(value, str) and len(value) == 1
                return ord(value)
            assert node.type in ('int', 'unsigned int', 'long int', 'unsigned long int',
                                 'long long int', 'unsigned long long int'), node.type
            literal = node.value.rstrip('uUlL')
            base = 16 if literal.lower().startswith('0x') else 8 if literal.startswith('0') else 10
            return int(literal, base)
        if isinstance(node, c_ast.Cast):
            value = self.expr(node.expr)
            typ = node.to_type.type
            if isinstance(typ, c_ast.PtrDecl):
                return value
            words = typ.type.names
            bits = 8 if 'char' in words else 16 if 'short' in words else 64 if 'long' in words else 32
            value &= (1 << bits) - 1
            if 'unsigned' not in words and value & (1 << (bits-1)):
                value -= 1 << bits
            return value
        if isinstance(node, c_ast.BinaryOp):
            a = self.expr(node.left)
            if node.op == '&&':
                return int(bool(a) and bool(self.expr(node.right)))
            if node.op == '||':
                return int(bool(a) or bool(self.expr(node.right)))
            b = self.expr(node.right)
            if node.op in ('+', '-'):
                left = self.type_of(node.left)
                right = self.type_of(node.right)
                if isinstance(left, (c_ast.PtrDecl, c_ast.ArrayDecl)):
                    scale = self.element_bytes(node.left)
                    if isinstance(right, (c_ast.PtrDecl, c_ast.ArrayDecl)):
                        assert node.op == '-'
                        return (a - b) // scale
                    b *= scale
                elif isinstance(right, (c_ast.PtrDecl, c_ast.ArrayDecl)):
                    assert node.op == '+'
                    a *= self.element_bytes(node.right)
            operations = {'+': operator.add, '-': operator.sub, '*': operator.mul,
                          '&': operator.and_, '|': operator.or_, '^': operator.xor,
                          '<<': operator.lshift, '>>': operator.rshift,
                          '==': operator.eq, '!=': operator.ne, '<': operator.lt,
                          '<=': operator.le, '>': operator.gt, '>=': operator.ge}
            if node.op == '/':
                return int(a / b)
            if node.op == '%':
                return a - int(a / b) * b
            return operations[node.op](a, b)
        if isinstance(node, c_ast.UnaryOp):
            if node.op == '*':
                return self.memory[self.expr(node.expr)]
            if node.op in ('p++', 'p--', '++', '--'):
                old = self.expr(node.expr)
                step = (self.element_bytes(node.expr)
                        if isinstance(self.type_of(node.expr), (c_ast.PtrDecl, c_ast.ArrayDecl)) else 1)
                new = old + (step if '+' in node.op else -step)
                self.store(node.expr, new)
                return old if node.op.startswith('p') else new
            value = self.expr(node.expr)
            return {'-': operator.neg, '+': operator.pos, '!': lambda v: int(not v),
                    '~': operator.invert}[node.op](value)
        if isinstance(node, c_ast.TernaryOp):
            return self.expr(node.iftrue if self.expr(node.cond) else node.iffalse)
        if isinstance(node, c_ast.ExprList):
            values = [self.expr(e) for e in node.exprs]
            return values[-1]
        if isinstance(node, c_ast.Assignment):
            value = self.expr(node.rvalue)
            if node.op != '=':
                old = self.expr(node.lvalue)
                if (node.op in ('+=', '-=')
                        and isinstance(self.type_of(node.lvalue), (c_ast.PtrDecl, c_ast.ArrayDecl))):
                    value *= self.element_bytes(node.lvalue)
                value = {'+=': operator.add, '-=': operator.sub, '*=': operator.mul,
                         '^=': operator.xor, '|=': operator.or_, '&=': operator.and_}[node.op](old, value)
            return self.store(node.lvalue, value)
        if isinstance(node, c_ast.FuncCall):
            assert isinstance(node.name, c_ast.ID)
            args = tuple(self.expr(a) for a in node.args.exprs) if node.args is not None else ()
            self.calls.append((node.name.name, args))
            return self.callees[node.name.name](*args)
        raise AssertionError(f'Unsupported C expression: {type(node).__name__}')

    def stmt(self, node):
        self.tick()
        if node is None or isinstance(node, c_ast.EmptyStatement):
            return
        if isinstance(node, c_ast.Compound):
            children = node.block_items or []
            labels = {child.name: index for index, child in enumerate(children) if isinstance(child, c_ast.Label)}
            index = 0
            while index < len(children):
                try:
                    self.stmt(children[index])
                except _Goto as jump:
                    if jump.label not in labels:
                        raise
                    index = labels[jump.label]
                    continue
                index += 1
        elif isinstance(node, c_ast.Decl):
            self.types[node.name] = node.type
            if node.init is not None:
                self.env[node.name] = self.expr(node.init)
        elif isinstance(node, c_ast.DeclList):
            for declaration in node.decls:
                self.stmt(declaration)
        elif isinstance(node, c_ast.Return):
            raise _Returned(self.expr(node.expr) if node.expr else None)
        elif isinstance(node, c_ast.If):
            self.stmt(node.iftrue if self.expr(node.cond) else node.iffalse)
        elif isinstance(node, (c_ast.For, c_ast.While, c_ast.DoWhile)):
            if isinstance(node, c_ast.For):
                self.stmt(node.init)
            first = True
            while True:
                self.tick()
                if not (first and isinstance(node, c_ast.DoWhile)):
                    if node.cond is not None and not self.expr(node.cond):
                        break
                first = False
                try:
                    self.stmt(node.stmt)
                except _Continue:
                    pass
                except _Break:
                    break
                if isinstance(node, c_ast.For) and node.next is not None:
                    self.expr(node.next)
        elif isinstance(node, c_ast.Switch):
            value = self.expr(node.cond)
            entries = []
            def labels(statement):
                if isinstance(statement, (c_ast.Case, c_ast.Default)):
                    entries.append(statement)
                    for child in statement.stmts or []:
                        labels(child)
                else:
                    entries.append(statement)
            for child in node.stmt.block_items or []:
                labels(child)
            matching = [i for i, entry in enumerate(entries)
                        if isinstance(entry, c_ast.Case) and self.expr(entry.expr) == value]
            defaults = [i for i, entry in enumerate(entries) if isinstance(entry, c_ast.Default)]
            if matching or defaults:
                start = matching[0] if matching else defaults[0]
                try:
                    for entry in entries[start + 1:]:
                        if not isinstance(entry, (c_ast.Case, c_ast.Default)):
                            self.stmt(entry)
                except _Break:
                    pass
        elif isinstance(node, c_ast.Label):
            self.stmt(node.stmt)
        elif isinstance(node, c_ast.Goto):
            raise _Goto(node.name)
        elif isinstance(node, c_ast.Break):
            raise _Break()
        elif isinstance(node, c_ast.Continue):
            raise _Continue()
        else:
            self.expr(node)

    def run(self, *arguments):
        params = self.function.decl.type.args.params if self.function.decl.type.args else []
        if len(params) == 1 and isinstance(params[0], c_ast.Typename):
            assert params[0].type.type.names == ['void']
            params = []
        assert len(params) == len(arguments)
        self.types.update((param.name, param.type) for param in params)
        self.env.update((param.name, value) for param, value in zip(params, arguments))
        try:
            self.stmt(self.function.body)
        except _Returned as result:
            return result.value
        raise AssertionError('Pseudocode completed without returning a value')


def rendered_identifiers(text):
    return {n.name for n in ast_nodes(parse_c(text)) if isinstance(n, (c_ast.ID, c_ast.Decl))}


def cli_decompile(binary, *arguments):
    return run_command([sys.executable, '-m', 'velnora', 'decompile', binary,
                        '--no-colors', *arguments], timeout=120)


@asynccontextmanager
async def refinement_session():
    """Use the SDK's stdio transport directly, bounded over the entire session."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    async with asyncio.timeout(120):
        async with stdio_client(StdioServerParameters(command=sys.executable, args=['-m', 'velnora.mcp'])) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                yield session


def mapping_program(directory):
    source = directory / 'F16_mapping.S'
    source.write_text('''
.text
.global _start, mapped, known, write_left, write_right, invoke_known, result_bias
.type _start,@function
_start: jmp _start
.size _start,.-_start
.type mapped,@function
mapped:
write_left: movl $17,left(%rip)
write_right: movl $29,right(%rip)
    mov $5,%edi
    mov $6,%esi
invoke_known: call known
result_bias: add $11,%eax
    ret
.size mapped,.-mapped
.type known,@function
known: lea 3(%rdi),%eax
    ret
.size known,.-known
.data
.global left,right
left: .long 0
right: .long 0
.section .note.GNU-stack,"",@progbits
''')
    binary = source.with_suffix('.elf')
    result = run_command([require_tools('gcc')['gcc'], '-nostdlib', '-no-pie', '-o', binary, source])
    assert result.returncode == 0, result.stderr
    project = import_product().Project(str(binary), auto_load_libs=False)
    project.analyses.CFGFast(normalize=True, data_references=True, **recovery_options())
    project.analyses.CompleteCallingConventions(analyze_callsites=True)
    return project


def c_offset(text, coord):
    return sum(len(line) for line in text.splitlines(keepends=True)[:coord.line-1]) + coord.column-1


def statement_interval(text, node):
    start = c_offset(text, node.coord)
    # These are semicolon-terminated assignment/call statements in the C grammar.
    end = strip_c_comments(text).index(';', start)+1
    return start, end


def block_chain(count):
    # Each conditional transfer is an independently known two-byte block; both
    # outcomes go to the following block. The last block returns a known value.
    project = import_product().load_shellcode(b'\x74\x00'*(count-1)+b'\xb8\x2b\x00\x00\x00\xc3',
                                             arch='x86', load_address=0x400000)
    project.analyses.CFGFast(normalize=True, cross_references=False,
                            function_starts=[0x400000], **recovery_options())
    function = project.kb.functions[0x400000]
    from velnora.analyses.decompiler.edits import set_function_prototype
    set_function_prototype(project, function, 'int chain(void)')
    return project, function


@dataclass(frozen=True)
class SyntaxGroup:
    """Balanced syntax node; literals are decoded separately from identifiers."""
    opener: str
    items: tuple


@dataclass(frozen=True)
class SyntaxLiteral:
    value: object


def pseudocode_syntax(text):
    """Parse lexical atoms and nested (), [], {} with no ignored nontrivia input.

    Specific declarations, constructors, patterns and calls are read from these
    syntax nodes, never by searching text or interpreting comments as code.
    The grammar accepts arbitrary names, spacing and nested expressions.
    """
    pattern = re.compile(r'(?P<trivia>[ \t\r]+|//[^\n]*|/\*.*?\*/)|'
                         r'(?P<string>"(?:\\.|[^"\\])*")|'
                         r"(?P<char>'(?:\\.|[^'\\])')|"
                         r'(?P<atom>\n|[A-Za-z_][A-Za-z_0-9]*|0[xX][0-9a-fA-F]+|[0-9]+|'
                         r'::|->|:=|==|!=|<=|>=|&&|\|\||<<|>>|\+\+|--|[{}()[\],;:.+*/%&|^!~=?<>\-])', re.S)
    tokens = []
    pos = 0
    while pos < len(text):
        match = pattern.match(text, pos)
        assert match is not None, f'Unrecognized pseudocode syntax at {pos}: {text[pos:pos+30]!r}'
        pos = match.end()
        if match.lastgroup == 'trivia':
            continue
        token = match.group()
        if match.lastgroup == 'string':
            tokens.append(SyntaxLiteral(json.loads(token)))
        elif match.lastgroup == 'char':
            import ast
            tokens.append(SyntaxLiteral(ast.literal_eval(token)))
        else:
            tokens.append(token)
    def group(index, closer=None, opener=''):
        items = []
        pairs = {'(': ')', '[': ']', '{': '}'}
        while index < len(tokens):
            token = tokens[index]
            if token == '\n' and opener in ('(', '['):
                index += 1
                continue
            if isinstance(token, str) and token in (')', ']', '}'):
                assert token == closer, (token, closer)
                return SyntaxGroup(opener, tuple(items)), index+1
            if isinstance(token, str) and token in pairs:
                child, index = group(index+1, pairs[token], token)
                items.append(child)
            else:
                items.append(token)
                index += 1
        assert closer is None, f'Unclosed syntax group: {opener}'
        return SyntaxGroup(opener, tuple(items)), index
    return group(0)[0]


def syntax_groups(root):
    yield root
    for item in root.items:
        if isinstance(item, SyntaxGroup):
            yield from syntax_groups(item)


def syntax_statements(root, *, newline_terminates=True):
    """Read statement boundaries, preserving expressions across legal line breaks."""
    items = tuple(i for i in root.items if i != '\n') if not newline_terminates else root.items
    current = []
    continuation = {',', '.', ':', '+', '-', '*', '/', '%', '&', '|', '^', '=', ':=',
                    '==', '!=', '<', '<=', '>', '>=', '&&', '||', '<<', '>>', '->'}
    for index, item in enumerate(items):
        if item == '\n':
            if current and current[-1] not in continuation:
                yield tuple(current)
                current = []
        elif item == ';':
            if current:
                yield tuple(current)
                current = []
        else:
            current.append(item)
            if isinstance(item, SyntaxGroup) and item.opener == '{' and current[0] in (
                    'if', 'for', 'while', 'loop', 'match', 'switch'):
                following = next((i for i in items[index+1:] if i != '\n'), None)
                if following != 'else':
                    yield tuple(current)
                    current = []
    if current:
        yield tuple(current)


def syntax_comma_items(group):
    """Read comma-delimited expressions, allowing a single trailing comma."""
    pieces, current = [], []
    for item in group.items:
        if item == '\n':
            continue
        if item == ',':
            assert current, 'Empty comma-delimited expression'
            pieces.append(tuple(current))
            current = []
        else:
            current.append(item)
    if current:
        pieces.append(tuple(current))
    return tuple(pieces)


def syntax_calls(root):
    """Read call/macro operators and their parenthesized argument nodes."""
    for group in syntax_groups(root):
        items = group.items
        for i, item in enumerate(items):
            if not isinstance(item, SyntaxGroup) or item.opener != '(' or i == 0:
                continue
            previous = items[i-1]
            if previous == '!' and i >= 2 and isinstance(items[i-2], str):
                yield items[i-2]+'!', item
            elif isinstance(previous, str) and re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', previous):
                yield previous, item


def syntax_function(root, language, name=None):
    items = tuple(i for i in root.items if i != '\n')
    keyword = 'fn' if language == 'rust' else 'func'
    matches = []
    for i, item in enumerate(items):
        if item != keyword:
            continue
        cursor = i+1
        receiver = None
        if isinstance(items[cursor], SyntaxGroup):
            receiver = items[cursor]
            cursor += 1
        names = []
        while not isinstance(items[cursor], SyntaxGroup):
            names.append(items[cursor]); cursor += 1
        function_name = ''.join(names)
        parameters = items[cursor]
        assert parameters.opener == '('
        cursor += 1
        result = []
        while not (isinstance(items[cursor], SyntaxGroup) and items[cursor].opener == '{'):
            result.append(items[cursor]); cursor += 1
        if name is None or function_name == name:
            matches.append((receiver, function_name, parameters, tuple(result), items[cursor]))
    assert len(matches) == 1, (name, matches)
    return matches[0]


def language_corpus(directory):
    """Recover the real upstream corpus offline, including its actual signatures."""
    assets = Path(__file__).parent
    for asset, names in [('F16_go_basics.elf', ('main.main', 'main.parse', 'main.divmod', 'main.count', 'main.bump')),
                         ('F16_go_recv.elf', ('main.gitHubRecipientError.Error',))]:
        project = import_product().Project(str(assets/asset), auto_load_libs=False)
        roots = [symbol_address(project, n) for n in names]
        known = set(roots)
        kb = import_product().KnowledgeBase(project)
        project.analyses.CFGFast(kb=kb, normalize=True, start_at_entry=False,
                                function_starts=sorted(known), regions=[(a, a+0x2000) for a in known],
                                symbols=False, force_smart_scan=False)
        for root in roots:
            known.update(a for a in networkx.descendants(kb.functions.callgraph, root)
                         if project.loader.main_object.contains_addr(a))
        cfg = project.analyses.CFGFast(normalize=True, start_at_entry=False, function_starts=roots,
                                      regions=[(a, a+0x2000) for a in known], force_smart_scan=False)
        project.analyses.CompleteCallingConventions(prioritize_func_addrs=sorted(known), skip_other_funcs=True)
        yield 'go', {name: decompiled(project, project.kb.functions[address], cfg=cfg.model, flavor='go').text
                     for name, address in zip(names, roots)}
    cache = directory/'cache'
    base = cache/'velnora/flirt_signatures'
    signatures = base/'x86_64/linux/rust/inline'
    signatures.mkdir(parents=True)
    for opt in range(4):
        shutil.copyfile(assets/f'F16_rust_O{opt}.sig', signatures/f'1.88.0-O{opt}.sig')
    # This is the upstream install-completion marker, after real files are copied.
    (base/'.download_complete').touch()
    with temporary_environment({'XDG_CACHE_HOME': str(cache)}):
        project = import_product().Project(str(assets/'F16_rust_fmt.elf'), auto_load_libs=False)
        root = 0x496920
        regions = [(s.vaddr, s.vaddr+s.memsize) for s in project.loader.main_object.sections
                   if s.is_executable and s.memsize]
        project.analyses.CFGFast(normalize=True, regions=regions, start_at_entry=False,
                                function_starts=[root], force_smart_scan=False)
        known = set(networkx.single_source_shortest_path_length(project.kb.functions.callgraph, root, cutoff=4))
        project.analyses.CompleteCallingConventions(prioritize_func_addrs=known, skip_other_funcs=True)
        project.rustc_version = '1.88.0'  # Recorded compiler version of this upstream artifact.
        project.analyses.RustSymbolRecovery()
        project.analyses.TypeDBLoader()
        yield 'rust', {'fmt': decompiled(project, project.kb.functions[root], flavor='rust').text}


def syntax_text(item):
    if isinstance(item, SyntaxLiteral):
        return json.dumps(item.value)
    if isinstance(item, SyntaxGroup):
        closer = {'(': ')', '[': ']', '{': '}', '': ''}[item.opener]
        return item.opener+' '.join(syntax_text(i) for i in item.items)+closer
    return item


def scalar_language_observation(text, language, arguments):
    """Read a foreign scalar function's typed signature and return expression."""
    root = pseudocode_syntax(text)
    receiver, name, params, result, body = syntax_function(root, language)
    assert receiver is None
    pieces = []
    current = []
    for token in params.items+(',',):
        if token == ',':
            pieces.append(current); current = []
        else:
            current.append(token)
    names = []
    for parameter in pieces:
        assert len(parameter) >= (3 if language == 'rust' else 2)
        if language == 'rust':
            assert parameter[1] == ':'
        else:
            assert ':' not in parameter
        names.append(parameter[0])
    if language == 'rust':
        assert result[0] == '->' and len(result) > 1
    else:
        assert result
    # Parse scalar statements through the independent C observer. Temporaries
    # and equivalent conditional expressions are accepted; no generated name or
    # requirement for a single return statement is imposed.
    def translate(block):
        output = []
        statements = list(syntax_statements(block, newline_terminates=language != 'rust'))
        for index, statement in enumerate(statements):
            parts = list(statement)
            if parts[0] in ('let', 'var'):
                keyword = parts.pop(0)
                if parts[0] == 'mut':
                    parts.pop(0)
                local = parts.pop(0)
                if keyword == 'let':
                    if parts and parts[0] == ':':
                        parts.pop(0)
                    else:
                        assert parts and parts[0] == '='
                if '=' in parts:
                    split = parts.index('=')
                    output.append('int '+local+' = '+' '.join(syntax_text(i) for i in parts[split+1:])+';')
                else:
                    output.append('int '+local+';')
            elif parts[0] == 'if':
                split = next(i for i, item in enumerate(parts) if isinstance(item, SyntaxGroup) and item.opener == '{')
                output.append('if ('+' '.join(syntax_text(i) for i in parts[1:split])+') {'+translate(parts[split])+'}')
                rest = parts[split+1:]
                if rest:
                    assert len(rest) == 2 and rest[0] == 'else' and isinstance(rest[1], SyntaxGroup)
                    output.append('else {'+translate(rest[1])+'}')
            else:
                expression = ' '.join('=' if i == ':=' else syntax_text(i) for i in parts)
                last = next((i for i in reversed(block.items) if i != '\n'), None)
                if (language == 'rust' and index == len(statements)-1 and last != ';'
                        and parts[0] != 'return' and '=' not in parts):
                    expression = 'return '+expression
                output.append(expression+';')
        return ' '.join(output)
    function = c_function('int observed('+','.join('int '+n for n in names)+') {'+translate(body)+'}', 'observed')
    return CObservation(function).run(*arguments)


def go_scalar_results(text, name, arguments):
    """Parse Go scalar statements into the independent bounded C observer.

    Syntax adaptation changes only declaration/conditional/return notation; the
    emitted operators, operands, assignments and conditions remain the oracle's
    input. Multiple results are observed as a tuple, not a C comma expression.
    """
    _, _, params, _, body = syntax_function(pseudocode_syntax(text), 'go', name)
    parameters = []
    current = []
    for token in params.items+(',',):
        if token == ',':
            assert len(current) >= 2
            parameters.append(current[0]); current = []
        else:
            current.append(token)
    def statements(group):
        return ' '.join(statement(list(s)) for s in syntax_statements(group))
    def expression(items):
        return ' '.join(syntax_text(i) for i in items)
    def statement(items):
        if items[0] == 'var':
            assert len(items) >= 3
            return 'int '+items[1]+(' = '+expression(items[4:]) if len(items) > 3 and items[3] == '=' else '')+';'
        if items[0] == 'if':
            split = next(i for i, item in enumerate(items) if isinstance(item, SyntaxGroup) and item.opener == '{')
            result = 'if ('+expression(items[1:split])+') {'+statements(items[split])+'}'
            rest = items[split+1:]
            if rest:
                assert rest[0] == 'else'
                if rest[1] == 'if':
                    result += ' else '+statement(rest[1:])
                else:
                    assert len(rest) == 2 and isinstance(rest[1], SyntaxGroup)
                    result += ' else {'+statements(rest[1])+'}'
            return result
        if items[0] == 'return':
            return 'return observed_results('+expression(items[1:])+');'
        return expression(['=' if item == ':=' else item for item in items])+';'
    c_text = 'int observed('+','.join('int '+p for p in parameters)+') {'+statements(body)+'}'
    return CObservation(c_function(c_text, 'observed'), callees={'observed_results': lambda *values: values}).run(*arguments)


def oversized_cli_program(directory):
    source = directory/'F16_cli_limit.S'
    source.write_text('''
.text
.global _start, oversized, healthy
.type _start,@function
_start: jmp _start
.size _start,.-_start
.type oversized,@function
oversized:
.rept 50000
    jz .+2
.endr
    mov $43,%eax
    ret
.size oversized,.-oversized
.type healthy,@function
healthy:
    mov $9,%eax
    ret
.size healthy,.-healthy
.section .note.GNU-stack,"",@progbits
''')
    binary = source.with_suffix('.elf')
    result = run_command([require_tools('gcc')['gcc'], '-nostdlib', '-no-pie', '-o', binary, source])
    assert result.returncode == 0, result.stderr
    project = import_product().Project(str(binary), auto_load_libs=False)
    return binary, symbol_address(project, 'oversized')
