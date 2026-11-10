# feature: F02
"""Binary fixtures for format-level loading checks."""

import struct
import zipfile


def native_file_regions(path):
    """Read stable file-backed regions from native headers independently of CLE.

    PE and Mach-O writable data may be relocated during loading, so sample
    executable regions for those formats.
    """
    data = path.read_bytes()
    mappings = []
    if data[:4] in (b"\x7fELF", b"\x7fCGC"):
        width = data[4]
        order = "<" if data[5] == 1 else ">"
        header = struct.unpack_from(order + ("HHIIIIIHHHHHH" if width == 1 else
                                              "HHIQQQIHHHHHH"), data, 16)
        _, _, _, entry, phoff, _, _, _, phsize, phnum, _, _, _ = header
        for index in range(phnum):
            fields = struct.unpack_from(order + ("IIIIIIII" if width == 1 else
                                                   "IIQQQQQQ"), data, phoff + index * phsize)
            if width == 1:
                kind, offset, address, _, size, _, _, _ = fields
            else:
                kind, _, offset, address, _, size, _, _ = fields
            if kind == 1 and size:
                mappings.append((address, offset, size))
        return mappings, entry if header[0] != 4 else None
    if data[:2] == b"MZ":
        peoff = struct.unpack_from("<I", data, 0x3c)[0]
        _, count, _, _, _, optional_size, _ = struct.unpack_from("<HHIIIHH", data, peoff + 4)
        optional = peoff + 24
        entry_rva = struct.unpack_from("<I", data, optional + 16)[0]
        image_base = struct.unpack_from("<I", data, optional + 28)[0]
        for index in range(count):
            _, _, rva, size, offset = struct.unpack_from("<8sIIII", data,
                                                        optional + optional_size + index * 40)
            flags = struct.unpack_from("<I", data,
                                       optional + optional_size + index * 40 + 36)[0]
            if size and flags & 0x20000000:
                mappings.append((image_base + rva, offset, size))
        return mappings, image_base + entry_rva
    if data[:4] == b"\xcf\xfa\xed\xfe":
        count = struct.unpack_from("<I", data, 16)[0]
        offset = 32
        for _ in range(count):
            command, size = struct.unpack_from("<II", data, offset)
            if command == 0x19:
                address, _, file_offset, file_size = struct.unpack_from("<QQQQ", data, offset + 24)
                protection = struct.unpack_from("<I", data, offset + 60)[0]
                if file_size and protection & 4:
                    mappings.append((address, file_offset, file_size))
            offset += size
        return mappings, None
    raise ValueError("Unsupported native fixture format")


def make_universal_macho(path):
    """Write a fat Mach-O containing minimal x86-64 and AArch64 executables."""
    slices = []
    for cpu_type, cpu_subtype, code in (
        (0x01000007, 3, b"\xc3"),
        (0x0100000C, 0, b"\xc0\x03\x5f\xd6"),
    ):
        slice_size = 32 + 72 + 24 + len(code)
        header = struct.pack("<IiiIIIII", 0xFEEDFACF, cpu_type, cpu_subtype,
                             2, 2, 96, 0x80, 0)
        segment = struct.pack("<II16sQQQQiiII", 0x19, 72, b"__TEXT",
                              0x100000000, 0x1000, 0, slice_size, 7, 5, 0, 0)
        main = struct.pack("<IIQQ", 0x80000028, 24, 128, 0)
        slices.append(header + segment + main + code)

    first_offset = 4096
    second_offset = 8192
    fat_header = struct.pack(">II", 0xCAFEBABE, len(slices))
    arch_table = b"".join((
        struct.pack(">iiIII", 0x01000007, 3, first_offset, len(slices[0]), 12),
        struct.pack(">iiIII", 0x0100000C, 0, second_offset, len(slices[1]), 12),
    ))
    content = bytearray(second_offset + len(slices[1]))
    content[:len(fat_header + arch_table)] = fat_header + arch_table
    content[first_offset:first_offset + len(slices[0])] = slices[0]
    content[second_offset:second_offset + len(slices[1])] = slices[1]
    path.write_bytes(content)
    return path


def make_java_archive(path):
    """Write a JAR containing a valid class with a constructor and main method."""
    pool = b"".join((
        b"\x01\x00\x08F02Entry", b"\x07\x00\x01",
        b"\x01\x00\x10java/lang/Object", b"\x07\x00\x03",
        b"\x01\x00\x06<init>", b"\x01\x00\x03()V",
        b"\x01\x00\x04Code", b"\x0c\x00\x05\x00\x06",
        b"\x0a\x00\x04\x00\x08", b"\x01\x00\x04main",
        b"\x01\x00\x16([Ljava/lang/String;)V",
        b"\x01\x00\x05probe", b"\x01\x00\x04(I)I",
    ))
    constant_pool = struct.pack(">H", 14) + pool
    constructor_code = b"\x2a\xb7\x00\x09\xb1"
    constructor = (
        struct.pack(">HHHH", 0x0001, 5, 6, 1)
        + struct.pack(">HI", 7, 12 + len(constructor_code))
        + struct.pack(">HHI", 1, 1, len(constructor_code)) + constructor_code
        + struct.pack(">HH", 0, 0)
    )
    main_code = b"\xb1"
    main = (
        struct.pack(">HHHH", 0x0009, 10, 11, 1)
        + struct.pack(">HI", 7, 12 + len(main_code))
        + struct.pack(">HHI", 0, 1, len(main_code)) + main_code
        + struct.pack(">HH", 0, 0)
    )
    probe_code = b"\x1a\x10\x07\x60\xac"
    probe = (
        struct.pack(">HHHH", 0x0009, 12, 13, 1)
        + struct.pack(">HI", 7, 12 + len(probe_code))
        + struct.pack(">HHI", 2, 1, len(probe_code)) + probe_code
        + struct.pack(">HH", 0, 0)
    )
    class_file = (
        struct.pack(">IHH", 0xCAFEBABE, 0, 52) + constant_pool
        + struct.pack(">HHHHH", 0x0021, 2, 4, 0, 0)
        + struct.pack(">H", 3) + constructor + main + probe + struct.pack(">H", 0)
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nMain-Class: F02Entry\n\n")
        archive.writestr("F02Entry.class", class_file)
    return path


def make_core_image(path):
    """Write a minimal ELF64 core with two complete memory segments."""
    ident = b"\x7fELF" + bytes((2, 1, 1, 0)) + bytes(8)
    header = ident + struct.pack("<HHIQQQIHHHHHH", 4, 62, 1, 0, 64, 0, 0,
                                 64, 56, 2, 0, 0, 0)
    pages = ((0x410000, b"\x90\xc3" + bytes(range(256))),
             (0x620000, b"Core memory snapshot\x00" + bytes(reversed(range(256)))))
    content = bytearray(0x3000)
    content[:64] = header
    for index, (address, payload) in enumerate(pages):
        file_offset = (index + 1) * 0x1000
        segment = struct.pack("<IIQQQQQQ", 1, 5 if index == 0 else 6,
                              file_offset, address, 0, len(payload), len(payload), 0x1000)
        content[64 + index * 56:64 + (index + 1) * 56] = segment
        content[file_offset:file_offset + len(payload)] = payload
    path.write_bytes(content)
    return path
