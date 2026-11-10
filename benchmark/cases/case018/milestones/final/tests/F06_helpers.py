# feature: F06
"""Small independent readers for the public IR carriers used by F06."""
import re


def evaluate_vex_effects(ir, registers, memory, *, destination=False, only_offsets=None):
    """Interpret straight-line integer IR, failing on unsupported expressions."""
    registers, memory, temporaries = dict(registers), dict(memory), {}

    exits = []

    def expression(node, environment=None, image=None):
        environment = registers if environment is None else environment
        image = memory if image is None else image
        tag = node.tag
        width = node.result_size(ir.tyenv)
        mask = (1 << width) - 1
        if tag == 'Iex_Const':
            return node.con.value
        if tag == 'Iex_RdTmp':
            return temporaries[node.tmp]()
        if tag == 'Iex_Get':
            value = environment[node.offset]
            return (value() if callable(value) else value) & mask
        if tag == 'Iex_ITE':
            return expression(node.iftrue if expression(node.cond, environment, image) else node.iffalse, environment, image)
        if tag == 'Iex_Load':
            address = expression(node.addr, environment, image)
            return int.from_bytes(bytes(image[address + i] for i in range(width // 8)),
                                  'little' if node.end == 'Iend_LE' else 'big')
        if tag in ('Iex_Unop', 'Iex_Binop'):
            arguments = [expression(arg, environment, image) for arg in node.args]
            operation = node.op.removeprefix('Iop_')
            if operation.startswith('Add'):
                return sum(arguments) & mask
            if operation.startswith('Sub'):
                return (arguments[0] - arguments[1]) & mask
            if operation.startswith('CmpEQ'):
                return int(arguments[0] == arguments[1])
            if operation.startswith('CmpNE'):
                return int(arguments[0] != arguments[1])
            if operation.startswith('And'):
                return arguments[0] & arguments[1]
            if operation.startswith('Xor'):
                return arguments[0] ^ arguments[1]
            if operation.startswith('Or'):
                return arguments[0] | arguments[1]
            if operation.startswith('Shr'):
                return arguments[0] >> arguments[1]
            conversion = re.fullmatch(r'(\d+)([US]?)to(\d+)', operation)
            if conversion:
                source_width, signed, _ = conversion.groups()
                value = arguments[0]
                if signed == 'S' and value & (1 << (int(source_width) - 1)):
                    value -= 1 << int(source_width)
                return value & mask
        raise AssertionError(f'Unsupported public VEX expression: {node}')

    for statement in ir.statements:
        if statement.tag == 'Ist_WrTmp':
            temporaries[statement.tmp] = lambda node=statement.data, env=dict(registers), image=dict(memory): expression(node, env, image)
        elif statement.tag == 'Ist_Put':
            registers[statement.offset] = lambda node=statement.data, env=dict(registers), image=dict(memory): expression(node, env, image)
        elif statement.tag == 'Ist_Store':
            address = expression(statement.addr)
            width = statement.data.result_size(ir.tyenv) // 8
            data = expression(statement.data).to_bytes(width, 'little' if statement.end == 'Iend_LE' else 'big')
            memory.update({address + i: byte for i, byte in enumerate(data)})
        elif statement.tag == 'Ist_Exit':
            if expression(statement.guard):
                exits.append(statement.dst.value)
        elif statement.tag not in ('Ist_IMark', 'Ist_NoOp', 'Ist_AbiHint'):
            raise AssertionError(f'Unsupported public VEX statement: {statement}')
    if destination:
        return exits[0] if exits else expression(ir.next)
    selected = registers if only_offsets is None else only_offsets
    return {offset: registers[offset]() if callable(registers[offset]) else registers[offset]
            for offset in selected}, memory


def pcode_operations(ir):
    """Read numbered operation lines from the public IRSB text grammar."""
    operations = []
    for line in str(ir).splitlines():
        match = re.fullmatch(r'\s*\d+ \| (.*)', line)
        if match and not match[1].startswith('------'):
            operations.append(match[1])
    assert operations, 'P-Code representation contains no operations'
    return operations


def evaluate_pcode_effects(ir, arch, registers, memory, *, destination=False):
    """Interpret assignment/load/store text, including published operand widths."""
    registers = {name.upper(): value for name, value in registers.items()}
    memory, temporaries = dict(memory), {}
    widths = {name.upper(): size for name, (_, size) in arch.registers.items()}

    def value(token):
        if token.startswith('0x'):
            return int(token, 16), None
        if token.startswith('unique['):
            return temporaries[token], int(token.rsplit(':', 1)[1][:-1])
        token = token.upper()
        if token in registers:
            return registers[token], widths[token]
        # x86 subregisters are aliases, not independent input values.
        if token.startswith('E') and 'R' + token[1:] in registers:
            return registers['R' + token[1:]] & 0xffffffff, 4
        raise AssertionError(f'Unknown P-Code operand: {token}')

    for operation in pcode_operations(ir):
        if operation.startswith('return '):
            assert destination, 'Return requires a destination observation'
            return value(operation[7:])[0]
        branch = re.fullmatch(r'if \(([^)]+)\) goto ram\[([0-9a-f]+):(\d+)\]', operation)
        if branch:
            if value(branch[1])[0]:
                return int(branch[2], 16)
            continue
        left, right = operation.split(' = ', 1)
        if right.startswith('*[ram]'):
            address, _ = value(right[6:])
            width = int(left.rsplit(':', 1)[1][:-1]) if left.startswith('unique[') else widths[left.upper()]
            result = int.from_bytes(bytes(memory[address + i] for i in range(width)), 'little')
        elif right.startswith('zext(') and right.endswith(')'):
            result, _ = value(right[5:-1])
        elif ' == ' in right or ' != ' in right:
            first, comparison, second = right.split(' ')
            result = int(value(first)[0] == value(second)[0])
            if comparison == '!=':
                result = 1 - result
        elif ' + ' in right:
            first, second = right.split(' + ')
            result = value(first)[0] + value(second)[0]
        else:
            result, _ = value(right)
        if left.startswith('*[ram]'):
            address, _ = value(left[6:])
            _, width = value(right)
            assert width is not None, 'Store width must be observable in its operand'
            memory.update({address + i: byte for i, byte in enumerate(result.to_bytes(width, 'little'))})
        elif left.startswith('unique['):
            temporaries[left] = result
        else:
            left = left.upper()
            registers[left] = result
            if left.startswith('E') and 'R' + left[1:] in widths:
                registers['R' + left[1:]] = result & 0xffffffff
    if destination:
        return ir.next.con.value
    return registers, memory
