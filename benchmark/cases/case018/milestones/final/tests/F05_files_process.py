# feature: F05
"""Acceptance checks for simulated files, streams and process environment."""
from F01_helpers import expression_api, fresh_state
from F04_helpers import reach_address
from F05_helpers import (invoke_procedure, request_root, file_bytes,
                         build_io_program, finish_process)


def test_file_content_size_and_eof():
    velnora, c = expression_api()
    state = fresh_state()
    symbol = c.BVS("file_byte", 8)
    content = c.Concat(c.BVV(b"ab"), symbol, c.BVV(b"de"))
    file = velnora.SimFile("mixed", content=content, has_end=True)
    file.set_state(state)
    data, length, position = file.read(1, 8)
    assert state.solver.eval_one(length) == 4
    assert state.solver.eval_one(position) == 5
    assert not state.solver.satisfiable(extra_constraints=[data.get_bytes(0, 4) != content.get_bytes(1, 4)])
    assert state.solver.satisfiable(extra_constraints=[symbol == 17])
    assert state.solver.satisfiable(extra_constraints=[symbol == 231])
    _, length, position = file.read(5, 3)
    assert state.solver.eval_one(length) == 0
    assert state.solver.eval_one(position) == 5
    assert state.solver.eval_one(file.write(4, b"XYZ")) == 7
    state.solver.add(symbol == ord("Q"))
    assert file.concretize() == b"abQdXYZ"
    size = c.BVS("file_size", state.arch.bits)
    state.solver.add(c.Or(size == 2, size == 5))
    sized = velnora.SimFile("sized", content=b"ABCDE", size=size, has_end=True)
    sized.set_state(state)
    data, length, position = sized.read(1, 3)
    for end, actual in ((2, 1), (5, 3)):
        assert state.solver.eval_one(length, extra_constraints=[size == end]) == actual
        assert state.solver.eval_one(position, extra_constraints=[size == end]) == actual + 1
        assert state.solver.eval_one(data.get_bytes(0, actual), extra_constraints=[size == end], cast_to=bytes) == b"BCD"[:actual]
    endless = velnora.SimFile("endless", content=b"J", has_end=False)
    endless.set_state(state)
    data, length, position = endless.read(0, 4)
    assert state.solver.eval_one(length) == 4
    assert state.solver.eval_one(position) == 4
    assert state.solver.eval_one(endless.size) == 4
    assert state.solver.eval_one(data.get_byte(0)) == ord("J")
    for value in (0, 0x123456, 0xFFFFFF):
        assert state.solver.satisfiable(extra_constraints=[data.get_bytes(1, 3) == value])


def test_packet_streams_and_short_read_bounds():
    velnora, c = expression_api()
    state = fresh_state()
    for kind in (velnora.SimPackets, velnora.SimPacketsStream):
        stream = kind("input")
        stream.set_state(state)
        first, n1, next_pos = stream.read(0, 2, short_reads=False)
        second, n2, _ = stream.read(next_pos, 2, short_reads=False)
        state.solver.add(first == c.BVV(b"AX"), second == c.BVV(b"BY"))
        assert state.solver.satisfiable()
        assert state.solver.eval_one(n1) == state.solver.eval_one(n2) == 2
        assert stream.concretize() == [b"AX", b"BY"]
        output = kind("output")
        output.set_state(state)
        pos = output.write(0, b"one")
        output.write(pos, b"two")
        assert output.concretize() == [b"one", b"two"]
    for selected in (None, 37):
        for bound in (11, 400):
            state = fresh_state()
            if selected is not None:
                state.libc.max_packet_size = selected
            stream = velnora.SimPackets("short")
            stream.set_state(state)
            _, actual, _ = stream.read(0, bound, short_reads=True)
            maximum = min(bound, 256 if selected is None else selected)
            assert set(state.solver.eval_upto(actual, maximum + 2)) == set(range(maximum + 1))


def test_descriptor_io_positions_and_failures():
    velnora, _ = expression_api()
    from velnora.state_plugins.posix import Flags
    state = fresh_state()
    state.fs.insert(b"/data", velnora.SimFile("data", content=b"abcdef", has_end=True))
    fd = state.posix.open(b"/data", Flags.O_RDWR)
    assert state.solver.eval(fd) >= 0
    descriptor = state.posix.get_fd(fd)
    data, length = descriptor.read_data(2)
    assert state.solver.eval_one(length) == 2
    assert state.solver.eval_one(data, cast_to=bytes) == b"ab"
    assert state.solver.eval_one(descriptor.tell()) == 2
    assert state.solver.eval_one(descriptor.write_data(b"XY")) == 2
    assert state.solver.eval_one(descriptor.tell()) == 4
    assert file_bytes(state, b"/data") == b"abXYef"
    for offset, whence, expected in ((1, "start", 1), (2, "current", 3), (-1, "end", 5)):
        assert state.solver.is_true(descriptor.seek(offset, whence))
        assert state.solver.eval_one(descriptor.tell()) == expected
    data, length = descriptor.read_data(8)
    assert state.solver.eval_one(length) == 1
    assert state.solver.eval_one(data.get_byte(0)) == ord("f")
    assert state.solver.is_false(state.posix.get_fd(0).seek(0))
    assert state.solver.eval(invoke_procedure(state, "linux_kernel", "lseek", 0, 0, 0), signed=True) == -1
    assert state.solver.eval(invoke_procedure(state, "posix", "close", fd)) == 0
    for invalid in (fd, 9999):
        assert state.posix.get_fd(invalid) is None
        for operation in ("read", "write"):
            assert state.solver.eval(invoke_procedure(state, "posix", operation, invalid, 0x640000, 1), signed=True) == -1
        assert state.solver.eval(invoke_procedure(state, "posix", "close", invalid), signed=True) == -1
        assert state.solver.eval(invoke_procedure(state, "linux_kernel", "lseek", invalid, 0, 0), signed=True) == -1


def test_filesystem_operations_and_host_mount(tmp_path):
    velnora, _ = expression_api()
    from velnora import SimHostFilesystem
    state = fresh_state()
    state.fs.chdir(b"/work")
    assert state.fs.cwd == b"/work"
    assert state.fs.insert(b"item", velnora.SimFile("item", content=b"guest"))
    assert file_bytes(state, b"/work/item") == b"guest"
    assert file_bytes(state, b"./item") == b"guest"
    assert state.fs.delete(b"item")
    assert state.fs.get(b"/work/item") is None
    (tmp_path / "item").write_bytes(b"host-content")
    assert state.fs.get(b"/mounted/item") is None
    mount = SimHostFilesystem(str(tmp_path))
    mount.set_state(state)
    attach = state.fs.mount
    attach(b"/mounted", mount)
    assert file_bytes(state, b"/mounted/item") == b"host-content"


def test_root_reanchoring_composition_and_confinement():
    velnora, _ = expression_api()
    for cwd, expected in ((b"/a/b", b"/b"), (b"/outside", b"/")):
        state = fresh_state()
        for path, content in ((b"/a/b/c/item", b"inside"), (b"/secret", b"outside"), (b"/a/secret", b"middle")):
            state.fs.insert(path, velnora.SimFile("item", content=content))
        assert file_bytes(state, b"/secret") == b"outside"
        state.fs.chdir(cwd)
        state.fs.chroot(b"/a")
        assert state.fs.root == b"/a"
        assert state.fs.cwd == expected
        assert file_bytes(state, b"/b/c/item") == b"inside"
        assert file_bytes(state, b"/../../secret") == b"middle"
        if cwd == b"/a/b":
            assert file_bytes(state, b"c/item") == b"inside"
        state.fs.chroot(b"/b")
        assert state.fs.root == b"/a/b"
        assert state.fs.cwd == b"/"
        assert file_bytes(state, b"/../c/item") == b"inside"
        assert state.fs.get(b"/../../secret") is None
        state.fs.insert(b"new", velnora.SimFile("new", content=b"new-root"))
        assert file_bytes(state, b"/new") == b"new-root"


def test_program_root_changes_and_distinct_failures(tmp_path):
    velnora, _ = expression_api()
    from velnora import SimHostFilesystem
    (tmp_path / "jail").mkdir()
    (tmp_path / "jail" / "item").write_bytes(b"jailed")
    (tmp_path / "regular").write_bytes(b"regular")
    for host in (False, True):
        state = fresh_state()
        state.libc.errno_location = 0x650000
        if host:
            mount = SimHostFilesystem(str(tmp_path))
            mount.set_state(state)
            attach = state.fs.mount
            attach(b"/", mount)
        else:
            state.fs.insert(b"/regular", velnora.SimFile("regular", content=b"regular"))
            state.fs.insert(b"/jail/item", velnora.SimFile("item", content=b"jailed"))
        failures = [(b"", state.posix.ENOENT), (b"/regular", state.posix.ENOTDIR)]
        if host:
            failures.append((b"/missing", state.posix.ENOENT))
        for path, error in failures:
            assert request_root(state, path) == -1
            assert state.solver.eval_one(state.libc.errno) == error
            assert state.fs.root == b"/"
            assert file_bytes(state, b"/regular") == b"regular"
        assert request_root(state, b"/jail") == 0
        assert state.fs.root == b"/jail"
        assert file_bytes(state, b"/item") == b"jailed"
        if not host:
            assert request_root(state, b"/implicit") == 0
            assert state.fs.root == b"/jail/implicit"


def test_program_root_does_not_mount_host(tmp_path):
    velnora, c = expression_api()
    host = tmp_path / "host"
    host.mkdir()
    (host / "probe").write_bytes(b"HOST")
    state = fresh_state()
    state.fs.insert(str(host).encode() + b"/known", velnora.SimFile("known", content=b"guest"))
    assert request_root(state, str(host).encode()) == 0
    assert file_bytes(state, b"/known") == b"guest"
    fd = state.posix.open(b"/probe", 0)
    assert state.solver.eval(fd) >= 0
    data, length = state.posix.get_fd(fd).read_data(4)
    assert state.solver.satisfiable(extra_constraints=[length == 4])
    for value in (b"HOST", b"ELSE", b"\0" * 4):
        assert state.solver.satisfiable(extra_constraints=[length == 4, data == c.BVV(value)])
    assert (host / "probe").read_bytes() == b"HOST"


def test_process_standard_streams_pipes_and_sockets(tmp_path):
    velnora, _ = expression_api()
    from velnora import SimFileDescriptorDuplex
    path = build_io_program(tmp_path)
    project = velnora.Project(str(path), auto_load_libs=False)
    for input_bytes, expected in ((b"Abc", b"abc"), (b"Z19", b"z19")):
        for channel in ("standard", "pipe", "socket"):
            state = project.factory.entry_state(stdin=velnora.SimFileStream("stdin", content=input_bytes, has_end=True))
            if channel != "standard":
                incoming = velnora.SimPacketsStream("incoming", content=[input_bytes])
                outgoing = velnora.SimPacketsStream("outgoing")
                if channel == "pipe":
                    descriptor = SimFileDescriptorDuplex(incoming, outgoing)
                    descriptor.set_state(state)
                else:
                    ident = ("socket", 2, 1, 0, 1)
                    state.posix.sockets[ident] = (incoming, outgoing)
                    descriptor = state.posix.get_fd(state.posix.open_socket(ident))
                state.posix.fd[0] = descriptor
            result = finish_process(project, state)
            if channel == "standard":
                assert result.posix.dumps(0) == input_bytes
            assert result.posix.dumps(1) == expected
            assert result.posix.dumps(2) == b"diag"
    state = fresh_state()
    pipe_read = velnora.SimPacketsStream("pipe-input", content=[b"pipe"])
    pipe_write = velnora.SimPacketsStream("pipe-output")
    pipe = SimFileDescriptorDuplex(pipe_read, pipe_write)
    pipe.set_state(state)
    data, length = pipe.read_data(4)
    assert state.solver.eval_one(length) == 4
    assert state.solver.eval_one(data, cast_to=bytes) == b"pipe"
    pipe.write_data(b"PIPE!")
    assert pipe.write_storage.concretize() == [b"PIPE!"]
    ident = ("socket", 2, 1, 0, 1)
    state.posix.sockets[ident] = (velnora.SimPacketsStream("incoming", content=[b"request"]),
                                 velnora.SimPacketsStream("outgoing"))
    fd = state.posix.open_socket(ident)
    socket = state.posix.get_fd(fd)
    data, length = socket.read_data(7)
    assert state.solver.eval_one(length) == 7
    assert state.solver.eval_one(data, cast_to=bytes) == b"request"
    socket.write_data(b"response")
    assert socket.write_storage.concretize() == [b"response"]


def test_program_environment_and_termination(tmp_path):
    velnora, _ = expression_api()
    path = build_io_program(tmp_path, environment=True)
    project = velnora.Project(str(path), auto_load_libs=False)
    project.hook_symbol("getenv", velnora.SIM_PROCEDURES["posix"]["getenv"]())
    project.hook_symbol("exit", velnora.SIM_PROCEDURES["libc"]["exit"]())
    for value in (b"Green", b"Violet"):
        state = project.factory.entry_state(env={b"COLOR": value, b"EMPTY": b""})
        observed = reach_address(project, state, project.loader.find_symbol("observed").rebased_addr)
        address = project.loader.find_symbol("results").rebased_addr
        pointers = [observed.solver.eval_one(observed.memory.load(address + offset, 8, endness=observed.arch.memory_endness))
                    for offset in (0, 8, 16)]
        assert pointers[0] != 0
        assert observed.solver.eval_one(observed.memory.load(pointers[0], len(value) + 1), cast_to=bytes) == value + b"\0"
        assert pointers[1] != 0
        assert observed.solver.eval_one(observed.memory.load(pointers[1], 1)) == 0
        assert pointers[2] == 0
        result = finish_process(project, observed)
        events = [event for event in result.history.events if event.type == "terminate"]
        assert len(events) == 1
        assert result.solver.eval_one(events[0].objects["exit_code"]) == value[0]
