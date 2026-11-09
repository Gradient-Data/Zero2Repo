# feature: F18
"""Editable reconstruction judged by assembled program effects."""
from _helpers import run_command
from F07_helpers import symbol_address
from F18_helpers import (assemble_native, reconstruction_input, execute_reconstruction,
                         elf_symbol_region, inspected_instructions)


def test_named_reconstruction_native_family(tmp_path):
    for bits, cgc in [(64, False), (32, False), (32, True)]:
        directory = tmp_path / f'{bits}-{cgc}'
        directory.mkdir()
        project = reconstruction_input(directory, bits, cgc)
        reassembler = project.analyses.Reassembler(syntax='at&t')
        reassembler.symbolize()
        # Linking at a different code base means the output only works when its
        # code and data references are named rather than copied as raw addresses.
        relocated = ('-Wl,-Ttext=' + ('0x7400000' if bits == 64 else '0x9400000'),)
        _, results = execute_reconstruction(directory, reassembler.assembly(symbolized=True), bits,
                                            link_flags=relocated)
        for result, expected in zip(results, (41, 44)):
            assert result.returncode == expected, result.stderr
            assert result.stdout == b'recovered data!\n'


def test_instruction_and_procedure_edits(tmp_path):
    project = reconstruction_input(tmp_path)
    reassembler = project.analyses.Reassembler(syntax='at&t')
    _, baseline = execute_reconstruction(tmp_path, reassembler.assembly(), name='baseline')
    assert [r.returncode for r in baseline] == [41, 44]
    point = symbol_address(project, 'edit_point')
    reassembler.insert_asm(point, 'call added_bonus\n')
    reassembler.remove_instruction(point)
    reassembler.append_procedure('added_bonus', 'add $23,%eax\nret\n')
    _, results = execute_reconstruction(tmp_path, reassembler.assembly(), name='edited')
    for result, expected in zip(results, (53, 56)):
        assert result.returncode == expected, result.stderr
        assert result.stdout == b'recovered data!\n'


def test_appended_data_content_size_and_permissions(tmp_path):
    project = reconstruction_input(tmp_path)
    reassembler = project.analyses.Reassembler(syntax='at&t')
    # A following object bounds available storage; inter-object padding is allowed.
    entries = [('added_rw', b'\x00\xff\x7fRW\x81', 269, False),
               ('added_ro', b'RO\x00\xfe\x80!', 389, True)]
    for name, content, size, readonly in entries:
        reassembler.append_data(name, content, size, readonly=readonly)
        reassembler.append_data(name + '_end', b'Z', 1, readonly=readonly)
    reassembler.append_procedure('read_added', '''
 movzbl added_ro+3(%rip),%eax
 movb %al,added_rw(%rip)
 movzbl added_rw(%rip),%edi
 mov $60,%eax
 syscall
''')
    binary = assemble_native(tmp_path, 'data', reassembler.assembly(), entry='read_added')
    for name, content, size, readonly in entries:
        start, data, writable = elf_symbol_region(binary, name)
        end, _, _ = elf_symbol_region(binary, name + '_end')
        assert data[:len(content)] == content
        assert end - start >= size
        assert writable is not readonly
    executed = run_command([binary])
    assert executed.returncode == 254, executed.stderr


def test_colliding_labels_and_syntax_isolation(tmp_path):
    project = reconstruction_input(tmp_path)
    locations = [symbol_address(project, name) for name in ('compute', 'left', 'right', 'get_message')]
    before = [inspected_instructions(project, address) for address in locations]
    assert all(before)
    for syntax in ('at&t', 'intel'):
        reassembler = project.analyses.Reassembler(syntax=syntax)
        reassembler.symbolize()
        _, results = execute_reconstruction(tmp_path, reassembler.assembly(), name=syntax.replace('&', ''))
        for result, expected in zip(results, (41, 44)):
            assert result.returncode == expected, result.stderr
            assert result.stdout == b'recovered data!\n'
        assert [inspected_instructions(project, address) for address in locations] == before
