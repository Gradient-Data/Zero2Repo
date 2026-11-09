# feature: F17
"""Build controlled native comparison inputs and read public block addresses."""
from _helpers import import_product, require_tools, run_command
from F07_helpers import symbol_address
from F09_helpers import recovery_options


def comparison_program(directory, revised):
    """Operations, constants, and relocation vary independently in real code."""
    source = directory / ('F17_new.S' if revised else 'F17_old.S')
    functions = {
        '_start': 'call caller\nret',
        'caller': 'call leaf\nadd $3,%eax\nret',
        'operation': ('test %edi,%edi\njz unchanged_arm\nchanged_arm:\n'
                      + ('sub' if revised else 'add') + ' %edi,%eax\nret\n'
                      'unchanged_arm:\nmov %edi,%eax\nret'),
        'constants': ('mov %edi,%eax\nconstant_site:\nadd $'
                      + ('83' if revised else '17') + ',%eax\nret'),
        'leaf': 'mov $11,%eax\nret',
    }
    if not revised:
        functions['removed'] = 'imul %edi,%eax\nxor %edx,%eax\nret'
    assembly = '.text\n.global unchanged_arm, changed_arm, constant_site\n'
    for name, body in functions.items():
        if name == 'leaf' and revised:
            assembly += '.space 32,0x90\n'
        assembly += (f'.global {name}\n.type {name},@function\n{name}:\n'
                     f'{body}\n.size {name},.-{name}\n')
    source.write_text(assembly + '.section .note.GNU-stack,"",@progbits\n')
    binary = source.with_suffix('.elf')
    result = run_command([require_tools('gcc')['gcc'], '-nostdlib', '-no-pie',
                          '-Wl,-Ttext=' + ('0x601000' if revised else '0x401000'),
                          '-o', binary, source])
    assert result.returncode == 0, result.stderr
    return import_product().Project(str(binary), auto_load_libs=False)


def comparison_pair(directory):
    left = comparison_program(directory, False)
    right = comparison_program(directory, True)
    cfg_left = left.analyses.CFGFast(**recovery_options())
    cfg_right = right.analyses.CFGFast(**recovery_options())
    diff = left.analyses.BinDiff(right, cfg_a=cfg_left.model, cfg_b=cfg_right.model)
    return left, right, diff


def address_pair(left, right, name):
    return symbol_address(left, name), symbol_address(right, name)


def block_address_pairs(matches):
    return {(a.addr, b.addr) for a, b in matches}
