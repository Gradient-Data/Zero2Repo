# feature: F01
"""Observation helpers for create / clone / release of a klyvmap bitmap.

JSON fields emitted by a probe are test encoding, not a product output
contract. A compile or run that cannot be classified raises HarnessError
— never a sentinel that could pass for “empty” or “length 0”.
"""

from __future__ import annotations

import ctypes
import os
import platform
import secrets
import select
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from _helpers import (
    DEFAULT_TIMEOUT,
    HarnessError,
    PRODUCT_MODULE_NAME,
    RunResult,
    product_module_source,
    run_command,
    workspace,
    zig_executable,
)

# Fixed inputs used by the FP-01 tests. Random draws must not land here.
PUBLIC_U64_SAMPLES = frozenset({0, 42, 2999, 1 << 40, 1 << 50})

# Big-endian triple used to observe L57. Architecture spelling is the
# toolchain’s; the PRD names the property (big-endian refused), not the triple.
BIG_ENDIAN_TARGET = "aarch64_be-linux"

# Poison byte the tracking allocator writes on free. Test encoding only.
_POISON = 0xA5

# Probe-source files the test writes; not product I/O.
_PROBE_SOURCE_NAMES = frozenset({"probe.zig", "hello.zig"})


# ---------------------------------------------------------------------------
# Unpublished inputs
# ---------------------------------------------------------------------------


def unpublished_u64(forbidden: set[int] | frozenset[int] | None = None) -> int:
    """Return a 64-bit value the public materials do not name.

    Draws from the open range above 2^32 so a 32-bit store cannot hold it.
    Drops a random prefix of that range (never “the next integer after the
    forbidden set”). Raises if a draw collides with *forbidden*.
    """
    blocked = set(PUBLIC_U64_SAMPLES)
    if forbidden is not None:
        blocked.update(forbidden)
    low = (1 << 32) + 1
    high = (1 << 63) - 1
    span = high - low
    # Discard a prefix so the draw is not “first legal integer”.
    prefix = 1 + secrets.randbelow(span // 4)
    start = low + prefix
    width = high - start
    for _ in range(32):
        value = start + secrets.randbelow(width)
        if value in blocked:
            raise HarnessError(
                f"unpublished draw collided with a forbidden value: {value}"
            )
        return value
    raise HarnessError("could not draw an unpublished u64")


# ---------------------------------------------------------------------------
# Zig 0.16 product invocation
#
# F00’s zig_argv emits `zig run probe.zig --dep klyvmap -Mklyvmap=…`. On Zig 0.16
# `-M` creates a module and the first `-M` is the main module, so that argv
# is rejected. The working form is `--dep klyvmap -Mroot=probe.zig -Mklyvmap=…`.
# New names below wrap that form; they do not redefine F00 symbols.
# ---------------------------------------------------------------------------


def product_module_path() -> Path:
    """Root source file of the product Zig module."""
    return product_module_source(name=PRODUCT_MODULE_NAME)


def product_run_argv(source: str | Path, *, extra: Sequence[str] = ()) -> list[str]:
    """Argv that ``zig run``s *source* with the product module attached."""
    src = Path(source).resolve()
    cmd = [
        zig_executable(),
        "run",
        "--dep",
        PRODUCT_MODULE_NAME,
        f"-Mroot={src}",
        f"-M{PRODUCT_MODULE_NAME}={product_module_path()}",
    ]
    cmd.extend(str(item) for item in extra)
    return cmd


def product_compile_argv(
    source: str | Path,
    output: str | Path,
    *,
    extra: Sequence[str] = (),
    target: str | None = None,
    include_product: bool = True,
) -> list[str]:
    """Argv that ``zig build-exe``s *source* to *output*.

    *target* is applied to every module (Zig 0.16 `-target` is per-module
    and resets after each `-M`).
    """
    src = Path(source).resolve()
    out = Path(output)
    name = out.name
    cmd: list[str] = [zig_executable(), "build-exe"]
    if target is not None:
        cmd.extend(["-target", target])
    if include_product:
        cmd.extend(["--dep", PRODUCT_MODULE_NAME])
    cmd.append(f"-Mroot={src}")
    if include_product:
        if target is not None:
            cmd.extend(["-target", target])
        cmd.append(f"-M{PRODUCT_MODULE_NAME}={product_module_path()}")
    cmd.append(f"-femit-bin={out}")
    if name:
        cmd.extend(["--name", name])
    cmd.extend(str(item) for item in extra)
    return cmd


def _fail_if_nonzero(result: RunResult, *, what: str) -> None:
    if result.returncode != 0:
        err = result.stderr
        try:
            text = result.stderr_text
        except HarnessError:
            text = f"<non-utf8 stderr, {len(err)} bytes>"
        raise HarnessError(
            f"{what} exited {result.returncode}\nstderr:\n{text}"
        )


def run_bitmap_probe(
    source: str,
    *,
    timeout: float | None = DEFAULT_TIMEOUT,
    env: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Write *source*, ``zig run`` it with klyvmap attached, parse one JSON object.

    Requires ``returncode == 0``. Empty stdout or non-object JSON is a
    harness failure, not an empty-bitmap observation.
    """
    with workspace(updates=env) as ws:
        relpath = "probe.zig"
        ws.write(relpath, source)
        result = ws.run_command(
            product_run_argv(ws.resolve(relpath)),
            timeout=timeout,
        )
        _fail_if_nonzero(result, what="bitmap probe")
        payload = result.stdout_json()
        if not isinstance(payload, dict):
            raise HarnessError(
                f"probe stdout is not a JSON object: {type(payload)!r}"
            )
        return payload


def compile_product_source(
    ws,
    source: str,
    *,
    relpath: str = "probe.zig",
    output: str = "probe",
    extra: Sequence[str] = (),
    target: str | None = None,
    include_product: bool = True,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> RunResult:
    """Write *source* under *ws* and compile it. Does not interpret the exit."""
    path = ws.write(relpath, source)
    out = ws.resolve(output)
    argv = product_compile_argv(
        path,
        out,
        extra=extra,
        target=target,
        include_product=include_product,
    )
    return ws.run_command(argv, timeout=timeout)


# ---------------------------------------------------------------------------
# Probe Zig (test encoding, not a product contract)
# ---------------------------------------------------------------------------

ZIG_PRELUDE = r"""
const std = @import("std");
const klyvmap = @import("klyvmap");

const Tracking = struct {
    parent: std.mem.Allocator,
    live: usize = 0,

    fn allocator(self: *Tracking) std.mem.Allocator {
        return .{
            .ptr = self,
            .vtable = &.{
                .alloc = alloc,
                .resize = resize,
                .remap = remap,
                .free = free,
            },
        };
    }

    fn alloc(ctx: *anyopaque, len: usize, alignment: std.mem.Alignment, ret_addr: usize) ?[*]u8 {
        const self: *Tracking = @ptrCast(@alignCast(ctx));
        const p = self.parent.vtable.alloc(self.parent.ptr, len, alignment, ret_addr) orelse return null;
        self.live += len;
        return p;
    }

    fn resize(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, new_len: usize, ret_addr: usize) bool {
        const self: *Tracking = @ptrCast(@alignCast(ctx));
        if (!self.parent.vtable.resize(self.parent.ptr, memory, alignment, new_len, ret_addr)) return false;
        self.live = self.live - memory.len + new_len;
        return true;
    }

    fn remap(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, new_len: usize, ret_addr: usize) ?[*]u8 {
        const self: *Tracking = @ptrCast(@alignCast(ctx));
        const p = self.parent.vtable.remap(self.parent.ptr, memory, alignment, new_len, ret_addr) orelse return null;
        self.live = self.live - memory.len + new_len;
        return p;
    }

    fn free(ctx: *anyopaque, memory: []u8, alignment: std.mem.Alignment, ret_addr: usize) void {
        const self: *Tracking = @ptrCast(@alignCast(ctx));
        @memset(memory, 0xa5);
        self.parent.vtable.free(self.parent.ptr, memory, alignment, ret_addr);
        self.live -= memory.len;
    }
};

fn writeStdout(init: std.process.Init, text: []const u8) !void {
    var buf: [8192]u8 = undefined;
    var w = std.Io.File.stdout().writerStreaming(init.io, &buf);
    try w.interface.writeAll(text);
    try w.interface.flush();
}

fn jsonBool(b: bool) []const u8 {
    return if (b) "true" else "false";
}

fn allPresent(bm: *const klyvmap.Bitmap, start: u64, end_inclusive: u64) bool {
    var x: u64 = start;
    while (x <= end_inclusive) : (x += 1) {
        if (!bm.contains(x)) return false;
    }
    return true;
}

fn emitJson(init: std.process.Init, allocator: std.mem.Allocator, comptime fmt: []const u8, args: anytype) !void {
    const text = try std.fmt.allocPrint(allocator, fmt, args);
    defer allocator.free(text);
    try writeStdout(init, text);
}

fn optU64Json(gpa: std.mem.Allocator, value: ?u64) ![]u8 {
    if (value) |v| return std.fmt.allocPrint(gpa, "{d}", .{v});
    return gpa.dupe(u8, "null");
}
"""


def wrap_probe_body(body: str) -> str:
    """Wrap a Zig `run` body with the tracking allocator and JSON writer."""
    return (
        ZIG_PRELUDE
        + "\nfn run(init: std.process.Init, allocator: std.mem.Allocator, track: *Tracking) !void {\n"
        + "    const alloc_anchor = allocator;\n"
        + "    _ = alloc_anchor;\n"
        + "    const live_anchor = track.live;\n"
        + "    _ = live_anchor;\n"
        + body
        + "\n}\n\n"
        + "pub fn main(init: std.process.Init) !void {\n"
        + "    var track: Tracking = .{ .parent = init.gpa };\n"
        + "    try run(init, track.allocator(), &track);\n"
        + "}\n"
    )


def fill_u64(template: str, **values: int | str) -> str:
    """Substitute ``__NAME__`` placeholders in a raw Zig body. Avoids f-string brace wars."""
    body = template
    for name, value in values.items():
        token = f"__{name.upper()}__"
        if token not in body:
            raise HarnessError(f"Zig body has no placeholder {token}")
        body = body.replace(token, str(value))
    return body


# ---------------------------------------------------------------------------
# Snapshot assertions (test encoding of PRD observables)
# ---------------------------------------------------------------------------


def _require_bool(report: Mapping[str, Any], key: str) -> bool:
    if key not in report:
        raise HarnessError(f"probe JSON missing {key!r}; have {sorted(report)}")
    value = report[key]
    if not isinstance(value, bool):
        raise HarnessError(f"probe field {key!r} is {type(value).__name__}, not bool")
    return value


def _require_int(report: Mapping[str, Any], key: str) -> int:
    if key not in report:
        raise HarnessError(f"probe JSON missing {key!r}; have {sorted(report)}")
    value = report[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise HarnessError(f"probe field {key!r} is {type(value).__name__}, not int")
    return value


def require_positive_buffer_length(n: object) -> int:
    """Assert *n* is an integer strictly greater than 0 (L101 “positive length”)."""
    if isinstance(n, bool) or not isinstance(n, int):
        raise HarnessError(f"buffer length is {type(n).__name__}, not int")
    if n <= 0:
        raise AssertionError(f"empty bitmap emitted a non-positive buffer length: {n}")
    return n


def require_empty_snapshot(report: Mapping[str, Any], *, prefix: str = "") -> None:
    """Assert the empty-bitmap observables of L100 / L112.

    Absence of min/max is encoded as JSON null. That encoding is the probe’s,
    not a product Optional spelling. Delivering the integer 0 is not absence.
    """
    p = prefix
    empty = _require_bool(report, f"{p}empty")
    card = _require_int(report, f"{p}cardinality")
    contains0 = _require_bool(report, f"{p}contains0")
    if f"{p}min" not in report or f"{p}max" not in report:
        raise HarnessError(
            f"probe JSON missing min/max under prefix {p!r}; have {sorted(report)}"
        )
    min_v = report[f"{p}min"]
    max_v = report[f"{p}max"]
    assert empty is True, f"fresh bitmap emptiness is {empty!r}, not true"
    assert card == 0, f"fresh bitmap cardinality is {card!r}, not 0"
    assert contains0 is False, "fresh bitmap reports membership of 0"
    assert min_v is None, (
        f"fresh bitmap delivered a minimum {min_v!r}; absence is not the integer 0"
    )
    assert max_v is None, (
        f"fresh bitmap delivered a maximum {max_v!r}; absence is not the integer 0"
    )


def require_extrema_absent_not_zero(
    empty_report: Mapping[str, Any],
    after_set_zero_report: Mapping[str, Any],
) -> None:
    """Empty extrema are absent, not 0; after set 0, membership and emptiness change.

    FP-01 (L100, L112–L113) witnesses the empty snapshot plus that 0 is a
    legal value simply not present yet. Present extrema on a non-empty
    bitmap is FP-03 (L150) and is not asserted here.
    """
    require_empty_snapshot(empty_report)
    contains0 = _require_bool(after_set_zero_report, "contains0")
    assert contains0 is True, "after set 0, membership of 0 is still false"
    empty_after = _require_bool(after_set_zero_report, "empty")
    assert empty_after is False, (
        "after set 0, emptiness is still the fresh-empty observation"
    )
    assert empty_report["min"] is None and empty_report["max"] is None


def require_borrowed_buffer_intact(report: Mapping[str, Any]) -> None:
    """Borrowed release neither frees nor overwrites the caller's buffer.

    FP-01 (L103, L112–L113): live bytes after borrowed release match the
    pre-open baseline, and the caller's bytes are unchanged. The overwrite
    and free arms are positive controls that this observer would have seen
    those events. Restoring membership by opening a populated emit is
    FP-04 (L182) and is not asserted here.
    """
    bytes_same = _require_bool(report, "bytes_same")
    live_before = _require_int(report, "live_before_open")
    live_after = _require_int(report, "live_after_release")
    overwrite_same = _require_bool(report, "overwrite_same")
    live_before_free = _require_int(report, "live_before_free")
    live_after_free = _require_int(report, "live_after_free")
    assert bytes_same is True, "borrowed release overwrote the caller's buffer"
    assert live_after == live_before, (
        "borrowed release changed caller-allocator live bytes"
    )
    assert overwrite_same is False, (
        "overwrite positive control did not change observed bytes"
    )
    assert live_after_free < live_before_free, (
        "free positive control did not drop live bytes"
    )


# ---------------------------------------------------------------------------
# Side-effect observers (outside the product)
# ---------------------------------------------------------------------------

# Ptrace request / option numbers from linux/ptrace.h. The observer is the
# kernel interface this Linux image already has (libc + /proc), not a
# userspace strace binary.
_PTRACE_TRACEME = 0
_PTRACE_SYSCALL = 24
_PTRACE_SETOPTIONS = 0x4200
_PTRACE_GETEVENTMSG = 0x4201
_PTRACE_GET_SYSCALL_INFO = 0x420E
_PTRACE_O_TRACESYSGOOD = 0x01
_PTRACE_O_TRACEFORK = 0x02
_PTRACE_O_TRACEVFORK = 0x04
_PTRACE_O_TRACECLONE = 0x08
_PTRACE_O_TRACEEXEC = 0x10
_PTRACE_SYSCALL_INFO_ENTRY = 1
_PTRACE_EVENT_FORK = 1
_PTRACE_EVENT_VFORK = 2
_PTRACE_EVENT_CLONE = 3
_WAIT_WALL = 0x40000000  # __WALL: wait for clone and non-clone children

# Socket-family syscall numbers, one table per architecture. x86_64 and
# aarch64 do not share these numbers: on x86_64, 200 is tkill, 201 is time,
# 202 is futex, and 203 is sched_setaffinity, none of which is network I/O.
# Only the table for the machine the tracee runs on is consulted.
# x86_64: arch/x86/entry/syscalls/syscall_64.tbl
_X86_64_NETWORK_SYSCALLS = {
    41: "socket",
    42: "connect",
    43: "accept",
    44: "sendto",
    45: "recvfrom",
    46: "sendmsg",
    47: "recvmsg",
    49: "bind",
    50: "listen",
    288: "accept4",
}
# aarch64: include/uapi/asm-generic/unistd.h
_AARCH64_NETWORK_SYSCALLS = {
    198: "socket",
    200: "bind",
    201: "listen",
    202: "accept",
    203: "connect",
    206: "sendto",
    207: "recvfrom",
    211: "sendmsg",
    212: "recvmsg",
    242: "accept4",
}


def _network_syscall_table() -> dict[int, str]:
    machine = platform.machine()
    if machine in {"x86_64", "amd64"}:
        return _X86_64_NETWORK_SYSCALLS
    if machine in {"aarch64", "arm64"}:
        return _AARCH64_NETWORK_SYSCALLS
    raise HarnessError(f"no network syscall table for {machine}")


class _SyscallEntry(ctypes.Structure):
    _fields_ = [("nr", ctypes.c_uint64), ("args", ctypes.c_uint64 * 6)]


class _SyscallInfoUnion(ctypes.Union):
    _fields_ = [("entry", _SyscallEntry)]


class _PtraceSyscallInfo(ctypes.Structure):
    """linux/ptrace.h struct ptrace_syscall_info (entry arm only)."""

    _fields_ = [
        ("op", ctypes.c_uint8),
        ("_pad", ctypes.c_uint8 * 3),
        ("arch", ctypes.c_uint32),
        ("instruction_pointer", ctypes.c_uint64),
        ("stack_pointer", ctypes.c_uint64),
        ("u", _SyscallInfoUnion),
    ]


def _libc() -> ctypes.CDLL:
    lib = ctypes.CDLL(None, use_errno=True)
    lib.ptrace.restype = ctypes.c_long
    lib.ptrace.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    return lib


def _ptrace(lib: ctypes.CDLL, request: int, pid: int = 0, addr: int = 0, data: int = 0) -> int:
    return int(
        lib.ptrace(
            request,
            pid,
            None if addr == 0 else ctypes.c_void_p(addr),
            None if data == 0 else ctypes.c_void_p(data),
        )
    )


def _ptrace_ptr(lib: ctypes.CDLL, request: int, pid: int, addr: int, data_ptr: ctypes.c_void_p) -> int:
    return int(
        lib.ptrace(
            request,
            pid,
            None if addr == 0 else ctypes.c_void_p(addr),
            data_ptr,
        )
    )


def _walk_regular_files(root: Path) -> set[Path]:
    found: set[Path] = set()
    try:
        if not root.exists():
            return found
    except OSError as exc:
        raise HarnessError(f"cannot stat {root}: {exc}") from exc
    for dirpath, dirnames, filenames in os.walk(root):
        # Compiler cache is not product I/O.
        dirnames[:] = [d for d in dirnames if d not in {".cache", "zig-cache"}]
        for name in filenames:
            path = Path(dirpath) / name
            try:
                if path.is_file() and not path.is_symlink():
                    found.add(path.resolve())
            except OSError as exc:
                raise HarnessError(f"cannot stat {path}: {exc}") from exc
    return found


def product_created_files(
    *,
    before: set[Path],
    roots: Sequence[Path],
    ignore_names: set[str] | None = None,
) -> set[Path]:
    """Regular files under *roots* that were not in *before*.

    Probe sources the test wrote are ignored. Everything else is attributed
    to the child that ran after the snapshot.
    """
    skip = set(ignore_names) if ignore_names is not None else set(_PROBE_SOURCE_NAMES)
    after: set[Path] = set()
    for root in roots:
        after |= _walk_regular_files(root)
    created = set()
    for path in after - before:
        if path.name in skip:
            continue
        created.add(path)
    return created


def _syscall_nr_at_stop(lib: ctypes.CDLL, pid: int) -> int | None:
    """Return the syscall number at a PTRACE_SYSCALL *entry* stop.

    Uses PTRACE_GET_SYSCALL_INFO when the kernel provides it. Exit stops
    are ignored so a single connect is not counted twice. Falls back to
    ``/proc/<pid>/syscall`` only when GET_SYSCALL_INFO itself fails —
    a missing file is a harness failure, not “no syscall”.
    """
    info = _PtraceSyscallInfo()
    rv = _ptrace_ptr(
        lib,
        _PTRACE_GET_SYSCALL_INFO,
        pid,
        ctypes.sizeof(info),
        ctypes.byref(info),
    )
    if rv != -1:
        if info.op == _PTRACE_SYSCALL_INFO_ENTRY:
            return int(info.u.entry.nr)
        return None
    path = Path(f"/proc/{pid}/syscall")
    try:
        text = path.read_text().strip()
    except OSError as exc:
        raise HarnessError(f"cannot read {path}: {exc}") from exc
    if text in {"running", ""}:
        return None
    first = text.split()[0]
    if first.startswith("-"):
        return None
    try:
        return int(first, 0)
    except ValueError as exc:
        raise HarnessError(f"{path} is not a syscall record: {text!r}") from exc


def _drain_pipe(fd: int, buckets: list[bytes]) -> None:
    try:
        chunk = os.read(fd, 65536)
    except (BlockingIOError, OSError):
        return
    if chunk:
        buckets.append(chunk)


def trace_network_syscalls(
    argv: Sequence[str],
    *,
    cwd: str | Path,
    env: Mapping[str, str],
    timeout: float | None = DEFAULT_TIMEOUT,
) -> tuple[RunResult, list[str]]:
    """Run *argv* under ptrace and return ``(result, network-syscall names)``.

    The observer is outside the product: the test process is the tracer,
    the compiled probe is the tracee. A silent tracer (no syscall stops
    at all) is a harness failure, not an empty-network pass. Does not
    require a strace binary.
    """
    if not argv:
        raise HarnessError("trace argv must be non-empty")
    table = _network_syscall_table()
    workdir = str(Path(cwd).resolve())
    child_env = dict(env)
    lib = _libc()
    timeout_s = DEFAULT_TIMEOUT if timeout is None else float(timeout)

    def _traceme() -> None:
        os.setpgid(0, 0)
        if _ptrace(lib, _PTRACE_TRACEME) == -1:
            os._exit(126)

    proc = subprocess.Popen(
        list(argv),
        cwd=workdir,
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        preexec_fn=_traceme,
    )
    if proc.stdout is None or proc.stderr is None:
        raise HarnessError("traced child has no stdout/stderr pipes")
    out_fd = proc.stdout.fileno()
    err_fd = proc.stderr.fileno()
    os.set_blocking(out_fd, False)
    os.set_blocking(err_fd, False)
    out_b: list[bytes] = []
    err_b: list[bytes] = []
    stop = threading.Event()

    def _drain_loop() -> None:
        while not stop.is_set():
            ready, _, _ = select.select([out_fd, err_fd], [], [], 0.05)
            for fd in ready:
                _drain_pipe(fd, out_b if fd == out_fd else err_b)

    reader = threading.Thread(target=_drain_loop, daemon=True)
    reader.start()

    pgid = proc.pid
    options = (
        _PTRACE_O_TRACESYSGOOD
        | _PTRACE_O_TRACEFORK
        | _PTRACE_O_TRACEVFORK
        | _PTRACE_O_TRACECLONE
        | _PTRACE_O_TRACEEXEC
    )
    hits: list[str] = []
    syscall_stops = 0
    returncode: int | None = None
    deadline = time.monotonic() + timeout_s

    def _resume(pid: int, sig: int = 0) -> None:
        _ptrace(lib, _PTRACE_SYSCALL, pid, 0, sig)

    def _kill_group() -> None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError:
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except OSError:
                pass

    try:
        try:
            wpid, status = os.waitpid(proc.pid, _WAIT_WALL)
        except ChildProcessError as exc:
            raise HarnessError(f"traced child {proc.pid} vanished before stop") from exc
        if os.WIFEXITED(status) or os.WIFSIGNALED(status):
            code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -os.WTERMSIG(status)
            raise HarnessError(
                f"traced child exited {code} before a ptrace stop "
                "(PTRACE_TRACEME is not available on this image)"
            )
        if not os.WIFSTOPPED(status):
            raise HarnessError(f"traced child status {status:#x} is not a stop")
        if _ptrace(lib, _PTRACE_SETOPTIONS, proc.pid, 0, options) == -1:
            err = ctypes.get_errno()
            raise HarnessError(
                f"PTRACE_SETOPTIONS failed errno={err} {os.strerror(err)}"
            )
        _resume(proc.pid)

        while returncode is None:
            if time.monotonic() > deadline:
                _kill_group()
                raise HarnessError(
                    f"network trace of {list(argv)!r} exceeded {timeout_s}s"
                )
            try:
                wpid, status = os.waitpid(-pgid, _WAIT_WALL)
            except ChildProcessError:
                break
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                if wpid == proc.pid:
                    returncode = (
                        os.WEXITSTATUS(status)
                        if os.WIFEXITED(status)
                        else -os.WTERMSIG(status)
                    )
                continue
            if not os.WIFSTOPPED(status):
                continue
            sig = os.WSTOPSIG(status)
            event = status >> 16
            if sig == (signal.SIGTRAP | 0x80):
                syscall_stops += 1
                nr = _syscall_nr_at_stop(lib, wpid)
                if nr is not None and nr in table:
                    hits.append(table[nr])
                _resume(wpid)
            elif sig == signal.SIGTRAP and event in (
                _PTRACE_EVENT_FORK,
                _PTRACE_EVENT_VFORK,
                _PTRACE_EVENT_CLONE,
            ):
                msg = ctypes.c_ulong(0)
                _ptrace_ptr(
                    lib,
                    _PTRACE_GETEVENTMSG,
                    wpid,
                    0,
                    ctypes.byref(msg),
                )
                newpid = int(msg.value)
                if newpid:
                    _ptrace(lib, _PTRACE_SETOPTIONS, newpid, 0, options)
                    _resume(newpid)
                _resume(wpid)
            elif sig in (signal.SIGSTOP, signal.SIGTRAP):
                _ptrace(lib, _PTRACE_SETOPTIONS, wpid, 0, options)
                _resume(wpid)
            else:
                _resume(wpid, sig)
    finally:
        stop.set()
        reader.join(timeout=1.0)
        if returncode is None and proc.poll() is None:
            _kill_group()
            try:
                os.waitpid(proc.pid, _WAIT_WALL)
            except ChildProcessError:
                pass
        for fd, bucket in ((out_fd, out_b), (err_fd, err_b)):
            _drain_pipe(fd, bucket)

    if returncode is None:
        raise HarnessError("traced child produced no exit status")
    if syscall_stops == 0:
        raise HarnessError(
            "ptrace observed no syscall stops; the network observer is silent"
        )
    result = RunResult(
        returncode=returncode,
        stdout=b"".join(out_b),
        stderr=b"".join(err_b),
        argv=tuple(str(item) for item in argv),
        cwd=workdir,
        environ=child_env,
        phase="run",
        binary=Path(argv[0]),
    )
    return result, hits


def run_traced_network(
    ws,
    argv: Sequence[str],
    *,
    timeout: float | None = DEFAULT_TIMEOUT,
) -> tuple[RunResult, list[str]]:
    """Trace *argv* in *ws* for socket/connect/bind/listen/accept-family calls."""
    return trace_network_syscalls(
        argv,
        cwd=ws.path,
        env=ws.env,
        timeout=timeout,
    )


def network_syscalls_in_trace(names: Sequence[str]) -> list[str]:
    """Keep names that are socket/connect/bind/listen/accept family.

    The tracer already filters; this is the same key set the strace
    parser used, so a later reader can still ask the question.
    """
    keys = frozenset(
        {
            "socket",
            "connect",
            "bind",
            "listen",
            "accept",
            "accept4",
            "sendto",
            "recvfrom",
            "sendmsg",
            "recvmsg",
        }
    )
    return [name for name in names if name in keys]
