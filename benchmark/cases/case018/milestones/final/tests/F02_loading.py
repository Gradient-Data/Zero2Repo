# feature: F02
"""Acceptance checks for binary loading, mapping, and patches."""

from pathlib import Path
import shutil
import tempfile

from _helpers import capture_call, import_product
from F02_helpers import make_core_image, make_java_archive, make_universal_macho, native_file_regions


def test_native_image_metadata_and_raw_image(tmp_path):
    velnora = import_product()
    native = velnora.Project(str(Path(__file__).with_name("F02_dependent.elf")), auto_load_libs=False)
    image = native.loader.main_object
    assert image.arch.bits in (32, 64)
    assert image.entry == native.entry
    assert image.min_addr <= image.entry <= image.max_addr
    assert len(image.segments) > 0
    segment = next(segment for segment in image.segments
                   if segment.vaddr <= image.entry < segment.vaddr + segment.filesize)
    file_offset = image.entry - segment.vaddr + segment.offset
    with open(str(Path(__file__).with_name("F02_dependent.elf")), "rb") as binary:
        header = binary.read(6)
        binary.seek(file_offset)
        expected = binary.read(1)
    expected_endness = "Iend_LE" if header[5] == 1 else "Iend_BE"
    assert image.arch.bits == {1: 32, 2: 64}[header[4]]
    assert image.arch.memory_endness == expected_endness
    assert native.loader.memory.load(image.entry, 1) == expected
    assert len(image.sections) > 0

    raw = velnora.load_shellcode(b"\x90\xc3", arch="AMD64", load_address=0x710000, start_offset=0)
    blob = raw.loader.main_object
    assert (blob.min_addr, blob.max_addr) == (0x710000, 0x710001)
    assert raw.loader.memory.load(0x710000, 2) == b"\x90\xc3"

    fixtures = Path(__file__).parent
    core_path = make_core_image(tmp_path / "snapshot.core")
    for filename, architecture, width in (
        ("F02_pe.exe", "X86", 32),
        ("F02_macho.bin", "AMD64", 64),
        ("F02_cgc.bin", "X86", 32),
        (core_path, "AMD64", 64),
    ):
        path = fixtures / filename
        regions, entry = native_file_regions(path)
        project = velnora.Project(str(path), auto_load_libs=False)
        obj = project.loader.main_object
        assert (project.arch.name.casefold(), project.arch.bits, project.arch.memory_endness) == (
            architecture.casefold(), width, "Iend_LE")
        assert regions
        data = path.read_bytes()
        for address, offset, size in regions:
            sample_size = min(size, 16)
            assert project.loader.memory.load(address, sample_size) == data[offset:offset + sample_size], (
                filename, hex(address), hex(offset))
            owner = project.loader.find_object_containing(address)
            assert owner is not None
            assert owner.min_addr <= address <= owner.max_addr
        if entry is not None:
            assert project.entry == entry


def test_load_location_overrides_and_shellcode_entry():
    velnora = import_product()
    baseline = velnora.load_shellcode(b"\x90\xc3", arch="AMD64", load_address=0, start_offset=0)
    shifted = velnora.load_shellcode(b"\x90\xc3", arch="AMD64", load_address=0, start_offset=1)
    assert baseline.entry == 0
    assert shifted.entry == 1
    assert baseline.loader.main_object.min_addr == 0
    assert shifted.loader.main_object.min_addr == 0
    assert shifted.loader.memory.load(0, 2) == b"\x90\xc3"

    original = velnora.Project(str(Path(__file__).with_name("F02_dependent.elf")), auto_load_libs=False)
    old_base = original.loader.main_object.min_addr
    moved = velnora.Project(str(Path(__file__).with_name("F02_dependent.elf")), auto_load_libs=False,
                         main_opts={"base_addr": old_base + 0x200000})
    assert moved.loader.main_object.min_addr == old_base + 0x200000
    assert moved.loader.main_object.entry == original.loader.main_object.entry + 0x200000
    overridden = velnora.Project(str(Path(__file__).with_name("F02_dependent.elf")), auto_load_libs=False,
                              main_opts={"base_addr": 0, "entry_point": 0x1234})
    assert overridden.entry == overridden.loader.main_object.entry == 0x1234

    library_path = Path(__file__).parent / "F02_dependency.so"
    library = velnora.Project(str(library_path), auto_load_libs=False)
    relocated = velnora.Project(str(library_path), auto_load_libs=False,
                             main_opts={"base_addr": library.loader.main_object.min_addr + 0x300000})
    symbol = library.loader.main_object.get_symbol("f02_increment")
    shifted_symbol = relocated.loader.main_object.get_symbol("f02_increment")
    assert shifted_symbol.rebased_addr == symbol.rebased_addr + 0x300000
    assert relocated.loader.memory.load(shifted_symbol.rebased_addr, 8) == (
        library.loader.memory.load(symbol.rebased_addr, 8))


def test_invalid_load_requests_are_rejected(tmp_path):
    import cle

    velnora = import_product()
    valid = velnora.Project(str(Path(__file__).with_name("F02_dependent.elf")), auto_load_libs=False,
                         main_opts={"base_addr": 0, "entry_point": 0})
    assert valid.loader.main_object.entry == valid.entry == 0

    missing = capture_call(velnora.Project, str(tmp_path / "missing"), auto_load_libs=False)
    assert isinstance(missing.exception, Exception)
    negative = capture_call(velnora.Project, str(Path(__file__).with_name("F02_dependent.elf")), auto_load_libs=False,
                            main_opts={"base_addr": 0, "entry_point": -1})
    assert isinstance(negative.exception, velnora.errors.VelnoraValueError)
    with tempfile.NamedTemporaryFile() as raw:
        raw.write(b"\x90\xc3")
        raw.flush()
        valid_raw = velnora.Project(raw.name, auto_load_libs=False,
                                 main_opts={"backend": "blob", "arch": "AMD64", "base_addr": 0})
        assert valid_raw.loader.memory.load(0, 2) == b"\x90\xc3"
        no_arch = capture_call(velnora.Project, raw.name, main_opts={"backend": "blob"})
    assert isinstance(no_arch.exception, cle.CLEError)


def test_libraries_symbols_and_object_ownership(tmp_path):
    import cle

    velnora = import_product()
    fixtures = Path(__file__).parent
    dependencies = tmp_path / "included_dependencies"
    dependencies.mkdir()
    shutil.copyfile(fixtures / "F02_dependency.so", dependencies / "libF02_dependency.so")
    with_libs = velnora.Project(str(fixtures / "F02_dependent.elf"), auto_load_libs=True,
                             ld_path=[str(dependencies)])
    without_libs = velnora.Project(str(Path(__file__).with_name("F02_dependent.elf")), auto_load_libs=False)
    loaded = with_libs.loader
    main = loaded.main_object
    assert main in loaded.all_objects
    assert loaded.find_object_containing(main.entry) is main
    assert loaded.find_object_containing(main.max_addr + 0x10000000) is None
    assert len(loaded.all_objects) > len(without_libs.loader.all_objects)

    relocation = main.imports["__libc_start_main"]
    assert relocation.symbol.name == "__libc_start_main"
    resolved = relocation.symbol.resolvedby
    assert resolved.name == "__libc_start_main"
    assert resolved.is_export
    owner = loaded.find_object_containing(resolved.rebased_addr)
    assert owner is resolved.owner
    assert owner is not main
    assert resolved in owner.symbols

    fixtures = Path(__file__).parent
    binary = tmp_path / "app"
    shutil.copyfile(fixtures / "F02_dependent.elf", binary)
    libraries = tmp_path / "libraries"
    libraries.mkdir()
    shutil.copyfile(fixtures / "F02_dependency.so", libraries / "libF02_dependency.so")
    included = velnora.Project(str(binary), auto_load_libs=True, ld_path=[str(libraries)],
                            except_missing_libs=True)
    dependency = included.loader.shared_objects["libF02_dependency.so"]
    assert Path(dependency.binary).resolve() == (libraries / "libF02_dependency.so").resolve()
    export = dependency.get_symbol("f02_increment")
    assert export.is_export
    imported = included.loader.main_object.imports["f02_increment"].symbol
    assert imported.resolvedby is export
    assert included.loader.find_object_containing(export.rebased_addr) is dependency

    excluded = velnora.Project(str(binary), auto_load_libs=False, ld_path=[str(libraries)])
    assert "libF02_dependency.so" not in excluded.loader.shared_objects
    libraries.rename(tmp_path / "hidden_libraries")
    missing = capture_call(velnora.Project, str(binary), auto_load_libs=True,
                           ld_path=[str(libraries)], except_missing_libs=True)
    assert isinstance(missing.exception, cle.CLEFileNotFoundError)


def test_jar_loads_and_selects_its_entry_method(tmp_path):
    velnora = import_product()
    archive = make_java_archive(tmp_path / "entry.jar")
    from archinfo.arch_soot import SootMethodDescriptor

    fixtures = Path(__file__).parent
    default = velnora.Project(str(archive), auto_load_libs=False,
                           main_opts={"entry_point": "F02Entry.main",
                                      "entry_point_params": ("java.lang.String[]",)})
    assert default.arch.name.casefold() == "soot"
    assert default.entry == SootMethodDescriptor.from_string(
        "F02Entry.main(java.lang.String[])").address()

    native_path = tmp_path / "native"
    native_path.mkdir()
    shutil.copyfile(fixtures / "F02_native.so", native_path / "libfauxware.so")
    project = velnora.Project(
        str(archive),
        auto_load_libs=True,
        main_opts={"entry_point": "F02Entry.probe", "entry_point_params": ("int",),
                   "jni_libs": ["libfauxware.so"],
                   "jni_libs_ld_path": [str(native_path)]},
    )
    assert project.arch.name.casefold() == "soot"
    assert project.entry == SootMethodDescriptor.from_string("F02Entry.probe(int)").address()
    image = project.loader.main_object
    for method_name, parameters, return_type in (
        ("main", ("java.lang.String[]",), "void"),
        ("probe", ("int",), "int"),
    ):
        method = image.get_soot_method("F02Entry." + method_name, params=parameters)
        assert (method.name, method.params, method.ret) == (method_name, parameters, return_type)
        assert method.blocks
    native = project.loader.shared_objects["libfauxware.so"]
    assert native in project.loader.all_objects
    assert Path(native.binary).resolve() == (native_path / "libfauxware.so").resolve()
    export = native.get_symbol("Java_Fauxware_authenticate")
    assert export.is_export
    assert project.loader.find_object_containing(export.rebased_addr) is native
    with (native_path / "libfauxware.so").open("rb") as binary:
        assert native.memory.load(0, 4) == binary.read(4)

    sdk = tmp_path / "platforms" / "android-16"
    sdk.mkdir(parents=True)
    shutil.copyfile(fixtures / "F02_android.jar", sdk / "android.jar")
    android = velnora.Project(
        str(fixtures / "F02_android.apk"), auto_load_libs=False,
        main_opts={"android_sdk": str(sdk.parent), "android_api_version": 16,
                   "entry_point": "com.example.antoniob.android1.MainActivity.onCreate",
                   "entry_point_params": ("android.os.Bundle",)},
    )
    assert android.arch.name.casefold() == "soot"
    assert android.entry == SootMethodDescriptor.from_string(
        "com.example.antoniob.android1.MainActivity.onCreate(android.os.Bundle)").address()
    activity = android.loader.main_object.get_soot_method(
        "com.example.antoniob.android1.MainActivity.onCreate", params=("android.os.Bundle",))
    assert activity.blocks


def test_patch_registration_export_and_instruction_view():
    velnora = import_product()
    path = str(Path(__file__).with_name("F02_dependent.elf"))
    project = velnora.Project(path, auto_load_libs=False)
    original = open(path, "rb").read()
    image = project.loader.main_object
    file_offset = next(segment for segment in image.segments
                       if segment.vaddr <= image.entry < segment.vaddr + segment.filesize)
    offset = image.entry - file_offset.vaddr + file_offset.offset
    # Two non-overlapping multi-byte replacements inside the executable file
    # region; each must be honoured, not only the first or a single byte.
    address = image.entry
    second = image.entry + 0x10
    replacements = {address: b"\x48\x31\xc0", second: b"\x31\xd2"}
    assert second + 2 < file_offset.vaddr + file_offset.filesize
    assert all(original[offset + (at - address):offset + (at - address) + len(data)] != data
               for at, data in replacements.items())
    project.kb.patches.add_patch(address, b"\xcc")
    assert project.kb.patches.get_patch(address).new_bytes == b"\xcc"
    for at, data in replacements.items():
        project.kb.patches.add_patch(at, data)
    for at, data in replacements.items():
        assert project.kb.patches.get_patch(at).new_bytes == data

    def patched(selected):
        expected = bytearray(original)
        for at in selected:
            data = replacements[at]
            start = offset + (at - address)
            expected[start:start + len(data)] = data
        return bytes(expected)

    state = project.factory.blank_state(addr=address)
    project.kb.patches.apply_patches_to_state(state)
    for at, data in replacements.items():
        assert state.solver.eval(state.memory.load(at, len(data)), cast_to=bytes) == data

    exported = project.kb.patches.apply_patches_to_binary()
    assert exported == patched(replacements)
    for at, data in replacements.items():
        block = project.factory.block(at, size=len(data))
        assert block.bytes == data
        assert [insn.mnemonic.lower() for insn in block.capstone.insns] == ["xor"]

    project.kb.patches.remove_patch(address)
    assert project.kb.patches.get_patch(address) is None
    assert project.kb.patches.get_patch(second).new_bytes == replacements[second]
    assert project.kb.patches.apply_patches_to_binary() == patched([second])
    project.kb.patches.remove_patch(second)
    assert project.kb.patches.apply_patches_to_binary() == original


def test_universal_macho_lists_and_selects_available_architectures(tmp_path):
    import archinfo

    velnora = import_product()
    image_path = make_universal_macho(tmp_path / "universal")

    loaded = capture_call(velnora.Project, str(image_path), auto_load_libs=False, timeout=15)
    assert loaded.exception is None, f"Universal Mach-O loading failed: {loaded.exception!r}"
    container = loaded.value.loader.main_object
    assert {name.casefold() for name in container.available_arches} == {"amd64", "aarch64"}
    assert len(container.child_objects) == 2

    for selected, expected_arch, expected_code in (
        ("AMD64", "AMD64", b"\xc3"),
        ("AARCH64", "AARCH64", b"\xc0\x03\x5f\xd6"),
    ):
        result = capture_call(velnora.Project, str(image_path), auto_load_libs=False,
                              main_opts={"arch": archinfo.arch_from_id(selected)}, timeout=15)
        assert result.exception is None, f"Selected Mach-O slice failed to load: {result.exception!r}"
        project = result.value
        assert project.arch.name.casefold() == expected_arch.casefold()
        slices = project.loader.main_object.child_objects
        assert len(slices) == 1
        selected_slice = slices[0]
        assert selected_slice.arch.name.casefold() == expected_arch.casefold()
        assert project.loader.memory.load(selected_slice.min_addr + 128,
                                          len(expected_code)) == expected_code
        block = project.factory.block(selected_slice.min_addr + 128, size=len(expected_code))
        assert block.bytes == expected_code
        assert [instruction.mnemonic.lower() for instruction in block.capstone.insns] == ["ret"]

    rejected = capture_call(velnora.Project, str(image_path), auto_load_libs=False,
                            main_opts={"arch": archinfo.arch_from_id("MIPS32")})
    assert isinstance(rejected.exception, KeyError)
