# feature: F12
"""AOT production and the public container envelope; payloads stay opaque."""
import struct


F12_STATE = '''(module
 (type $step_type (func (param i32) (result i32)))
 (memory 1)
 (data (i32.const 0) "\\17\\00\\00\\00")
 (data $passive "\\07\\00\\00\\00")
 (global $total (mut i32) (i32.const 11))
 (func $initialize
   i32.const 4 i32.const 0 i32.const 4 memory.init $passive
   data.drop $passive
   global.get $total i32.const 5 i32.add global.set $total
   i32.const 0 i32.const 0 i32.load i32.const 4 i32.load i32.add i32.store)
 (start $initialize)
 (table 1 funcref) (elem (i32.const 0) $step)
 (func $step (type $step_type) (param $n i32) (result i32)
   global.get $total local.get $n i32.add global.set $total
   i32.const 0 i32.const 0 i32.load local.get $n i32.const 3 i32.mul i32.add i32.store
   global.get $total)
 (func (export "evolve") (param $n i32) (result i32 i32)
   local.get $n i32.const 0 call_indirect (type $step_type) drop
   local.get $n i32.const 1 i32.add call $step
   i32.const 0 i32.load))'''


def f12_compile(driver, source, destination):
    """Compile a real file with the same CLI used for subsequent runs."""
    assert not destination.exists(), destination
    result = driver.command(['compile', source, '-o', destination])
    assert result.returncode == 0, (result.returncode, result.stderr)
    assert destination.is_file(), destination
    return destination


# Public v0.5 envelope, in serialized order (little endian). Only version,
# architecture and declared ranges are interpreted; no payload is decoded.
F12_HEADER_FIELDS = (
    'version', 'arch', 'flags', 'n_funcs', 'n_types', 'n_imports',
    'code_offset', 'code_size', 'metadata_offset', 'metadata_size',
    'types_offset', 'types_size', 'relocs_offset', 'relocs_size',
    'exports_offset', 'exports_size', 'globals_offset', 'globals_size',
    'memory_min_pages', 'memory_max_pages', 'memory_init_offset', 'memory_init_size',
    'table0_size', 'elem_offset', 'elem_size', 'imports_offset', 'imports_size',
    'wasm_bytes_offset', 'wasm_bytes_size', 'func_extras_offset', 'func_extras_size',
    'eh_offset', 'eh_size',
)
F12_HEADER = struct.Struct('<4s' + 'I' * len(F12_HEADER_FIELDS))


def f12_artifact_variants(data):
    """Return single-field incompatibilities and actual declared truncations."""
    assert len(data) >= F12_HEADER.size, 'Producer returned an incomplete envelope'
    magic, *values = F12_HEADER.unpack_from(data)
    assert magic == b'CWAS', magic
    header = dict(zip(F12_HEADER_FIELDS, values))
    assert header['version'] == 0x00050000, header['version']
    assert header['arch'] in (1, 2), header['arch']
    ranges = [(header[name], header[name.removesuffix('_offset') + '_size'])
              for name in F12_HEADER_FIELDS if name.endswith('_offset')]
    for offset, size in ranges:
        assert offset + size <= len(data), (offset, size, len(data))
    variants = {}
    for field, replacement in (
        ('version', header['version'] ^ 0x80000000),
        ('arch', 2 if header['arch'] == 1 else 1),
    ):
        changed = dict(header, **{field: replacement})
        variants[field] = F12_HEADER.pack(magic, *(changed[n] for n in F12_HEADER_FIELDS)) + data[F12_HEADER.size:]
    variants['header'] = data[:F12_HEADER.size - 1]
    end = max(offset + size for offset, size in ranges if size)
    assert end > F12_HEADER.size, 'Artifact has no declared payload'
    variants['payload'] = data[:end - 1]
    return variants
